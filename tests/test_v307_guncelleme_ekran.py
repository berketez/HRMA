"""V307/GÜNCELLEME-EKRAN bekçileri — kurulum sürerken görünen güncelleme penceresi.

Kusur (Berke, 10 Kas 2026): güncelleme kurulurken uygulama kapanıyor, yeni
sürüm açılana kadar (~3,5 dk) ekranda hiçbir şey yoktu. Yardımcı betik artık
uygulama paketinden bağımsız bir pencere açar (macOS: osascript JXA +
AppKit; Windows: PowerShell + WinForms) ve her adımda durum dosyasını yazar;
pencere YALNIZ bu dosyayı ve gerçek saati okur.

GERÇEK KURULU UYGULAMAYA DOKUNULMAZ ve EKRANDA PENCERE AÇILMAZ:
- çizim testleri pencere betiğini ``--render`` kipinde koşar (etkinleştirme
  ilkesi *Prohibited*: Dock simgesi yok, pencere ekrana gelmez);
- uçtan uca testler V306 düzeneğini (sahte ``.app`` + test DMG'si + PATH
  gölgesi) kullanır; sahte ``osascript`` pencere çağrısını gerçek
  ``/usr/bin/osascript``'e ``--offscreen --record`` ekleyerek iletir.
Windows betikleri burada çalıştırılamaz: metin/sözleşme testleri; canlı
deneme paketi docs/scofield/raw/OH/V307/guncelleme-ekran/windows_deneme/.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time

import pytest

from tests import test_v306_guncelleme_kilidi as v306

KOK = v306.KOK
MAC = sys.platform == "darwin" and os.path.exists("/usr/bin/osascript")
MAC_PENCERE = pytest.mark.skipif(
    not MAC, reason="pencere çizimi yalnız macOS'ta (osascript JXA + AppKit)")
MAC_E2E = pytest.mark.skipif(
    not MAC or v306.shutil.which("hdiutil") is None,
    reason="uçtan uca pencere senaryoları yalnız macOS'ta")


def _si():
    from hrma.utils import self_install
    return self_install


def _uw():
    from hrma.utils import update_window
    return update_window


def durum_metni(**kw):
    """Durum dosyası metni (sözleşme: self_install.UPDATE_STATUS_*)."""
    alanlar = {"pid": "4242", "started": "1000", "step": "copying",
               "phase": "wait", "done_kb": "", "total_kb": "", "lang": "tr",
               "from_version": "3.0.6", "to_version": "3.0.7",
               "result": "running", "error": ""}
    alanlar.update({k: str(v) for k, v in kw.items()})
    satirlar = [_si().UPDATE_STATUS_HEADER]
    satirlar += ["%s=%s" % (k, alanlar[k]) for k in (
        "pid", "started", "step", "phase", "done_kb", "total_kb", "lang",
        "from_version", "to_version", "result", "error")]
    satirlar.append("end=1")
    return "\n".join(satirlar) + "\n"


def ciz(tmp_path, metin, now=1065, alive=True, log="/Users/x/Documents/HRMA/hrma_update_log.txt",
        installer="/Users/x/Downloads/HRMA-Setup-3.0.7-macOS.dmg", ad="d"):
    """Pencere betiğini --render kipinde koşar (ekrana pencere gelmez)."""
    js = tmp_path / "w.js"
    if not js.exists():
        js.write_text(_uw().build_mac_window(), encoding="ascii")
    st = tmp_path / ("%s.txt" % ad)
    if metin is not None:
        st.write_bytes(metin.encode("utf-8") if isinstance(metin, str) else metin)
    png = tmp_path / ("%s.png" % ad)
    r = subprocess.run(
        ["/usr/bin/osascript", "-l", "JavaScript", str(js), "--render", str(png),
         "--now", str(now), "--alive", "1" if alive else "0", str(st), "4242",
         log, installer], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert png.exists() and png.stat().st_size > 1000
    return out


def yerlesim_denetle(out):
    """Yazı çakışması yok, metin kırpılmıyor, en küçük yazı 12 px, alan içinde."""
    m = out["metrics"]
    for x in m:
        assert x["h"] >= x["need_h"], ("kırpılan metin", x)
        if x["font_px"] is not None:
            assert x["font_px"] >= 12, x
        assert x["x"] >= 0 and x["x"] + x["w"] <= out["content_w"], x
        assert x["y"] >= 0 and x["y"] + x["h"] <= out["content_h"], x
    for i, a in enumerate(m):
        for b in m[i + 1:]:
            ust_uste = (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
                        and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])
            assert not ust_uste, ("çakışma", a, b)


# ---------------------------------------------------------------------------
# Sözleşme: kodlar, adımlar, metinler (platform bağımsız)
# ---------------------------------------------------------------------------

def _fallback_kodlari(betik):
    return set(re.findall(r'fallback "[^"\n]*" ([a-z_]+)', betik))


def test_her_hata_dalinin_kodu_ve_metni_var():
    si = _si()
    betik = si.MAC_HELPER
    cagrilar = re.findall(r'\bfallback "[^"\n]*"( [a-z_]+)?', betik)
    assert cagrilar and all(c.strip() for c in cagrilar), (
        "kodsuz fallback çağrısı var: pencere nedeni yazamaz")
    kodlar = _fallback_kodlari(betik) | {"interrupted", "unexpected",
                                          "helper_gone", "silent_install_failed"}
    assert kodlar <= set(si.UPDATE_ERROR_ACTIONS), kodlar - set(si.UPDATE_ERROR_ACTIONS)
    for dil in ("en", "tr"):
        t = si.UPDATE_TEXTS[dil]
        for kod, eylem in si.UPDATE_ERROR_ACTIONS.items():
            assert t.get("window.reason." + kod), (dil, kod)
            assert t.get("window.action." + eylem), (dil, eylem)


def test_betik_adimlari_pencere_asamalarinda_ve_metinli():
    si, uw = _si(), _uw()
    mac_adim = set(re.findall(r'set_step "([a-z_]+)"', si.MAC_HELPER)) | {"start"}
    win_adim = set(re.findall(r'set "HRMA_STEP=([a-z_]+)"', si.WIN_HELPER))
    mac_asama = {a for _, adimlar in uw.MAC_STAGES for a in adimlar}
    win_asama = {a for _, adimlar in uw.WIN_STAGES for a in adimlar}
    assert mac_adim <= mac_asama, mac_adim - mac_asama
    assert win_adim <= win_asama, win_adim - win_asama
    for dil in ("en", "tr"):
        for adim in (mac_adim | win_adim) - {"start", "done"}:
            assert si.UPDATE_TEXTS[dil].get("step." + adim), (dil, adim)
        for ad, _ in uw.MAC_STAGES + uw.WIN_STAGES:
            assert si.UPDATE_TEXTS[dil].get("step." + ad), (dil, ad)


def test_pencere_metinleri_iki_dilde_yasakli_ifadesiz():
    si = _si()
    en = {k for k in si.UPDATE_TEXTS["en"] if k.startswith("window.")}
    tr = {k for k in si.UPDATE_TEXTS["tr"] if k.startswith("window.")}
    assert en == tr and len(en) >= 30
    tum = json.dumps({k: si.UPDATE_TEXTS[d][k] for d in ("en", "tr") for k in en},
                     ensure_ascii=False).lower()
    for yasak in ("uydurma", "invented", "http 4", "/api/", "endpoint", "lock",
                  "kilit", "status file", "durum dosyas"):
        assert yasak not in tum, yasak
    tr_metin = json.dumps({k: si.UPDATE_TEXTS["tr"][k] for k in tr}, ensure_ascii=False)
    for harf in "çğıöşü":
        assert harf in tr_metin


def test_surum_alani_izinli_bicim_disini_gommez():
    si = _si()
    assert si.safe_version("3.0.7") == "3.0.7"
    assert si.safe_version("3.0.7-rc.8+abc") == "3.0.7-rc.8+abc"
    for kotu in ("3.0.7'; touch /tmp/x; '", "$(id)", "3.0.7\nresult=ok", "",
                 None, 3.07, "a" * 40, "-3.0.7", "3.0.7 & calc", "3.0.7%PATH%"):
        assert si.safe_version(kotu) == "", kotu
    b = si.build_mac_helper("tr", from_version="$(id)", to_version="3.0.7\nend=1")
    assert "FROM_VERSION=$''" in b and "TO_VERSION=$''" in b
    w = si.build_win_helper(1, r"C:\U\Setup.exe", r"C:\HRMA", lang="tr",
                            from_version="3.0.6 & calc", to_version="3.0.7")
    assert "echo from_version=\r\n" in w and "echo to_version=3.0.7\r\n" in w


def test_mac_betigi_durum_yaziyor_pencereyi_basatiyor_ascii_bash_gecerli(tmp_path):
    si = _si()
    for dil in (None, "en", "tr"):
        b = si.build_mac_helper(dil, from_version="3.0.6", to_version="3.0.7")
        b.encode("ascii")
        yol = tmp_path / "h.sh"
        yol.write_text(b, encoding="ascii")
        r = subprocess.run(["bash", "-n", str(yol)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    # Pencere sistem osascript'iyle, yollar ARGÜMAN olarak (kaynağa gömülmez)
    assert ('osascript -l JavaScript "$WIN_JS" "$STATUS" "$$" "$LOG" "$DMG"'
            in si.MAC_HELPER)
    # Adım değişimi ve kopya ölçümü kilit + durum dosyasına birlikte yazılır
    assert "publish() { write_lock; write_status; }" in si.MAC_HELPER
    assert 'echo "step: $STEP phase=$PHASE' in si.MAC_HELPER
    assert ('echo "progress: copied ${DONE_KB} KB of ${TOTAL_KB:-?} KB"\n'
            '    publish\n') in si.MAC_HELPER                    # kopya ölçümü
    assert "TOTAL_KB=\"$T\"\npublish\n" in si.MAC_HELPER
    govde = si.MAC_HELPER.split("set_step() {", 1)[1].split("}", 1)[0]
    assert "publish" in govde and "write_lock" not in govde
    # Başarı yalnız yeni süreç doğrulandıktan sonra
    assert si.MAC_HELPER.index('RESULT="ok"') > si.MAC_HELPER.index("new version running")
    # Pencere açıkken bildirim gitmez
    assert "if window_alive; then return 0; fi" in si.MAC_HELPER
    # Yardımcı çağrı sözleşmesi değişmedi (5 argüman; V306 kilidi)
    assert 'PID="$1"; DMG="$2"; TARGET="$3"; LOG="$4"; LOCK="${5:-}"' in si.MAC_HELPER


def test_win_betigi_durum_ve_pencere_sozlesmesi():
    si = _si()
    bat = si.build_win_helper(1234, r"C:\Users\ad soyad\Downloads\HRMA Setup.exe",
                              r"C:\Users\ad soyad\AppData\Local\HRMA", lang="tr",
                              from_version="3.0.6", to_version="3.0.7")
    bat.encode("ascii")
    # CRLF: LF'li batch'te 'call :etiket' etiket aramasında şaşabilir
    assert "\r\n" in bat and "\n" not in bat.replace("\r\n", "")
    satirlar = bat.split("\r\n")
    assert satirlar.count(":hrma_status") == 1
    assert bat.count("call :hrma_status") == 6
    # NSIS satırı V3 sözleşmesiyle aynı (tırnaklı exe, tırnaksız /D=)
    nsis = [s for s in satirlar if "/S /D=" in s]
    assert nsis == ['"C:\\Users\\ad soyad\\Downloads\\HRMA Setup.exe" /S '
                    '/D=C:\\Users\\ad soyad\\AppData\\Local\\HRMA']
    durum = r"C:\Users\ad soyad\AppData\Local\HRMA\updater\hrma_update_status.txt"
    pencere = r"C:\Users\ad soyad\AppData\Local\HRMA\updater\hrma_update_window.ps1"
    assert 'set "HRMA_STATUS=%s"' % durum in satirlar
    bas = [s for s in satirlar if "-File" in s]
    assert bas == ['if exist "%s" start "" /min powershell -NoProfile '
                   '-ExecutionPolicy Bypass -WindowStyle Hidden -File "%s" '
                   '-Status "%s" -Installer "C:\\Users\\ad soyad\\Downloads\\HRMA Setup.exe"'
                   % (pencere, pencere, durum)]
    # Pencere, uygulama kapanmasını beklemeden ÖNCE başlar
    assert bat.index("-File") < bat.index("Wait-Process")
    assert "Wait-Process -Id 1234 -Timeout %d" % si.HELPER_EXIT_WAIT_S in bat
    # Durum bloğu sözleşmeyi taşır; son satır end=1
    blok = bat[bat.index(":hrma_status"):]
    for alan in ("echo hrma-update-status 1", "echo step=%HRMA_STEP%",
                 "echo lang=tr", "echo from_version=3.0.6", "echo to_version=3.0.7",
                 "echo result=%HRMA_RESULT%", "echo error=%HRMA_ERROR%"):
        assert alan in blok, alan
    assert blok.index("echo end=1") > blok.index("echo error=")
    assert ') 2>nul 1>"%HRMA_STATUS%"' in blok
    # Sessiz kurulum hatası: sonuç ve kod YAZILDIKTAN sonra normal kurucu
    hata = bat[bat.index("if not exist"):bat.index("exit /b 1")]
    assert hata.index('set "HRMA_RESULT=failed"') < hata.index("call :hrma_status")
    assert 'set "HRMA_ERROR=silent_install_failed"' in hata
    assert hata.index("call :hrma_status") < hata.index('start "" "C:')
    # Başarı: yeni sürüm başlatıldıktan sonra ok
    assert bat.index('set "HRMA_RESULT=ok"') > bat.index("pythonw.exe\" \"")
    # Dil bilinmiyorsa boş
    bos = si.build_win_helper(1, r"C:\U\S.exe", r"C:\HRMA", lang="de")
    assert "echo lang=\r\n" in bos


def test_win_pencere_betigi_statik():
    uw = _uw()
    ps = uw.build_win_window()
    ps.encode("ascii")
    assert "\n" not in ps.replace("\r\n", "")
    govde = ps.replace("\r\n", "\n")
    cfg_metni = govde.split("$CFG = @'\n", 1)[1].split("\n'@", 1)[0]
    assert json.loads(cfg_metni) == uw.window_config(uw.WIN_STAGES)
    # Yalnız durum dosyasını okur; kabuk/ağ/kod yürütme yok
    for yasak in ("Invoke-Expression", "iex ", "DownloadString", "Invoke-WebRequest",
                  "Start-Process", "Net.WebClient", "Remove-Item"):
        assert yasak not in govde, yasak
    assert "[System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete" in govde
    assert "if (-not $end) { return $null }" in govde
    assert "ParentProcessId" in govde
    assert re.search(r"(?m)^param\(", govde)


def test_mac_pencere_betigi_statik_izin_istemez():
    uw = _uw()
    js = uw.build_mac_window()
    js.encode("ascii")
    cfg = json.loads(js.split("var CFG = ", 1)[1].split(";\n", 1)[0])
    assert cfg == uw.window_config(uw.MAC_STAGES)
    # Otomasyon/Erişilebilirlik izni tetikleyebilecek hiçbir köprü yok
    for yasak in ("Application(", "System Events", "doShellScript", "$.system(",
                  "NSAppleScript", "NSTask", "popen"):
        assert yasak not in js, yasak
    assert "NSApplicationActivationPolicyAccessory" in js


# ---------------------------------------------------------------------------
# Çizim (macOS, --render: ekrana pencere gelmez)
# ---------------------------------------------------------------------------

@MAC_PENCERE
def test_kopya_adimi_yalniz_olculen_degerden(tmp_path):
    si = _si()
    out = ciz(tmp_path, durum_metni(done_kb=524288, total_kb=1551988))
    v = out["view"]
    assert v["final"] == "running" and v["lang"] == "tr"
    assert v["heading"] == si.UPDATE_TEXTS["tr"]["window.heading"]
    assert v["versions"] == "3.0.6 → 3.0.7"
    assert v["detail"] == "Kopyalanan: 512 MB / 1.516 MB"
    assert abs(v["fraction"] - 524288 / 1551988) < 1e-12
    assert [s["mark"] for s in v["stages"]] == ["done", "done", "current",
                                                "pending", "pending", "pending"]
    assert v["elapsed"] == "Geçen süre: 1 dk 05 sn"           # now - started
    assert v["hint"] == si.UPDATE_TEXTS["tr"]["window.hint"]
    assert v["log"] == "Ayrıntılar: /Users/x/Documents/HRMA/hrma_update_log.txt"
    assert v["reason"] == v["action"] == v["installer"] == ""
    yerlesim_denetle(out)
    assert any(m["name"] == "bar" for m in out["metrics"])


@MAC_PENCERE
@pytest.mark.parametrize("alanlar", [
    {"done_kb": "", "total_kb": "1551988"},          # toplam var, ölçüm yok
    {"done_kb": "2000000", "total_kb": "1551988"},   # ölçüm toplamı aşmış
    {"done_kb": "1000", "total_kb": ""},             # toplam ölçülemedi
    {"step": "verifying", "done_kb": "1000", "total_kb": "2000"},  # kopya bitti
])
def test_olculmeyen_oran_cizilmez(tmp_path, alanlar):
    out = ciz(tmp_path, durum_metni(**alanlar))
    v = out["view"]
    assert v["fraction"] is None
    assert not any(m["name"] == "bar" for m in out["metrics"])
    if alanlar.get("step") == "verifying":
        assert v["detail"] == ""
    elif alanlar["total_kb"] and not alanlar["done_kb"]:
        assert v["detail"] == "Kopyalanacak boyut: 1.516 MB"


@MAC_PENCERE
def test_alt_adim_kendi_adiyla_yazilir(tmp_path):
    si = _si()
    out = ciz(tmp_path, durum_metni(step="closing", phase="closing", lang="en"))
    v = out["view"]
    assert v["stages"][4] == {"mark": "current",
                              "text": si.UPDATE_TEXTS["en"]["step.closing"]}
    assert v["stages"][3]["text"] == si.UPDATE_TEXTS["en"]["step.verifying"]


@MAC_PENCERE
@pytest.mark.parametrize("kod,adim,eylem", [
    ("copy_failed", "copying", "mac_opened"),
    ("mount_failed", "mounting", "redownload"),
    ("app_not_closed", "waiting_exit", "mac_opened"),
    ("instance_running", "closing", "mac_opened"),
    ("interrupted", "copying", "manual"),
])
def test_hata_nedeni_ne_yapilacagi_ve_kurucu_yeri(tmp_path, kod, adim, eylem):
    si = _si()
    t = si.UPDATE_TEXTS["tr"]
    out = ciz(tmp_path, durum_metni(step=adim, result="failed", error=kod))
    v = out["view"]
    assert v["final"] == "failed"
    assert v["title"] == t["window.title.failed"]
    assert v["heading"] == t["window.heading.failed"]
    assert v["reason"] == t["window.reason." + kod].format(
        exit_wait=si.HELPER_EXIT_WAIT_S, verify=si.HELPER_LAUNCH_VERIFY_S)
    assert v["action"] == t["window.action." + eylem]
    assert v["installer"] == "Kurulum dosyası: /Users/x/Downloads/HRMA-Setup-3.0.7-macOS.dmg"
    assert "error" in [s["mark"] for s in v["stages"]]
    assert v["hint"] == "" and v["fraction"] is None
    yerlesim_denetle(out)
    assert any(m["name"] == "button" for m in out["metrics"])


@MAC_PENCERE
def test_geri_yukleme_ve_basari(tmp_path):
    si = _si()
    t = si.UPDATE_TEXTS["tr"]
    out = ciz(tmp_path, durum_metni(step="restored", phase="launch", result="restored",
                                    error="new_version_not_started"), ad="r")
    v = out["view"]
    assert v["reason"] == "Yeni sürüm %d saniye içinde açılmadı." % si.HELPER_LAUNCH_VERIFY_S
    assert v["action"] == t["window.action.mac_restored"]
    assert v["stages"][5] == {"mark": "error", "text": t["step.opening"]}
    out = ciz(tmp_path, durum_metni(step="done", phase="launch", result="ok"), ad="ok")
    v = out["view"]
    assert v["final"] == "ok" and v["heading"] == t["window.heading.ok"]
    assert v["title"] == t["window.title.ok"]
    assert all(s["mark"] == "done" for s in v["stages"])
    assert v["ok"] == t["window.ok"] and v["log"] == "" and v["reason"] == ""
    assert not any(m["name"] == "button" for m in out["metrics"])
    yerlesim_denetle(out)


@MAC_PENCERE
def test_yardimci_olu_ve_sonuc_yoksa_nedenini_yazar(tmp_path):
    si = _si()
    out = ciz(tmp_path, durum_metni(lang="en"), alive=False)
    v = out["view"]
    assert v["final"] == "failed"
    assert v["reason"] == si.UPDATE_TEXTS["en"]["window.reason.helper_gone"]
    assert v["action"] == si.UPDATE_TEXTS["en"]["window.action.manual"]
    # Sonuç yazılmışsa ölü yardımcı "helper_gone" değildir
    out = ciz(tmp_path, durum_metni(lang="en", step="done", result="ok"), alive=False,
              ad="ok")
    assert out["view"]["final"] == "ok"


@MAC_PENCERE
@pytest.mark.parametrize("bozuk", [
    "hrma-update-status 1\nstep=copying\nresult=ok\n",          # end=1 yok (yarım)
    "hrma-update-lock 1\nstep=copying\nend=1\n",                # yabancı başlık
    b"\xff\xfe" + b"x" * 10,                                      # çöp
])
def test_okunamayan_durum_yalniz_suruyor_ve_gecen_sure(tmp_path, bozuk):
    si = _si()
    out = ciz(tmp_path, bozuk)
    v = out["view"]
    assert v["final"] == "running"
    assert v["fraction"] is None and v["versions"] == ""
    assert all(s["mark"] == "pending" for s in v["stages"])
    assert v["detail"] == (si.UPDATE_TEXTS["en"]["step.unknown"] + "\n"
                           + si.UPDATE_TEXTS["tr"]["step.unknown"])
    assert v["elapsed"].startswith("Elapsed: 0 min 00 s")


@MAC_PENCERE
def test_buyuk_ve_saldirgan_durum_okunmaz_alanlar_suzulur(tmp_path):
    si = _si()
    buyuk = durum_metni() + "x=" + "a" * (si.UPDATE_STATUS_MAX_BYTES + 10) + "\n"
    out = ciz(tmp_path, buyuk, ad="b")
    assert out["view"]["versions"] == "" and out["view"]["detail"]
    saldirgan = durum_metni(step="copying;rm", from_version="<b>x</b>",
                            to_version="3.0.7", result="hacked", error="$(id)",
                            lang="de", done_kb="-5", total_kb="1e9")
    out = ciz(tmp_path, saldirgan, ad="s")
    v = out["view"]
    assert v["final"] == "running"                     # bilinmeyen sonuç
    assert v["versions"].endswith("3.0.7") and "<b>" not in json.dumps(v)
    assert v["fraction"] is None and v["lang"] is None


@MAC_PENCERE
def test_dil_bilinmiyorsa_iki_dil_ayni_satir_tek(tmp_path):
    si = _si()
    out = ciz(tmp_path, durum_metni(lang="", step="mounting"))
    v = out["view"]
    assert v["heading"] == (si.UPDATE_TEXTS["en"]["window.heading"] + "\n"
                            + si.UPDATE_TEXTS["tr"]["window.heading"])
    assert v["versions"] == "3.0.6 → 3.0.7"               # bir kez
    assert v["stages"][1]["text"] == "Opening the installer image / Kurulum görüntüsü açılıyor"
    yerlesim_denetle(out)


@MAC_PENCERE
def test_uzun_suren_guncelleme_satiri(tmp_path):
    si = _si()
    sinir = si.UPDATE_LOCK_MAX_AGE_S
    out = ciz(tmp_path, durum_metni(step="copying"), now=1000 + sinir + 1)
    assert out["view"]["long"] == si.UPDATE_TEXTS["tr"]["window.long"].format(
        min=sinir // 60)
    out = ciz(tmp_path, durum_metni(step="copying"), now=1000 + sinir, ad="e")
    assert out["view"]["long"] == ""


# ---------------------------------------------------------------------------
# launch_helper / update_checker / arayüz iletisi
# ---------------------------------------------------------------------------

def test_launch_helper_pencere_betigini_yaninda_yazar(tmp_path, monkeypatch):
    si = _si()
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Documents").mkdir()
    monkeypatch.setattr(si, "_helper_dir", lambda plan: str(tmp_path))
    cagri = {}
    monkeypatch.setattr(si.subprocess, "Popen",
                        lambda arg, **kw: cagri.setdefault("arg", arg))
    res = si.launch_helper({"platform": "darwin", "target": "/Applications/HRMA.app"},
                           "/x/HRMA.dmg", pid=4242, versions=("3.0.6", "3.0.7"))
    assert res["launched"] is True
    assert cagri["arg"][2:] == ["4242", "/x/HRMA.dmg", "/Applications/HRMA.app",
                                si.update_log_path(), si.update_lock_path()]
    pencere = tmp_path / si.UPDATE_WINDOW_MAC_NAME
    assert pencere.read_text(encoding="ascii") == _uw().build_mac_window()
    betik = (tmp_path / "hrma_update.sh").read_text(encoding="ascii")
    assert "FROM_VERSION=$'3.0.6'" in betik and "TO_VERSION=$'3.0.7'" in betik


def test_pencere_yazilamazsa_guncelleme_yine_baslar(tmp_path, monkeypatch):
    si, uw = _si(), _uw()
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Documents").mkdir()
    monkeypatch.setattr(si, "_helper_dir", lambda plan: str(tmp_path))
    monkeypatch.setattr(si.subprocess, "Popen", lambda arg, **kw: None)
    monkeypatch.setattr(uw, "build_mac_window",
                        lambda: (_ for _ in ()).throw(RuntimeError("x")))
    res = si.launch_helper({"platform": "darwin", "target": "/A/HRMA.app"},
                           "/x/HRMA.dmg", pid=1)
    assert res["launched"] is True
    assert not (tmp_path / si.UPDATE_WINDOW_MAC_NAME).exists()
    assert (tmp_path / "hrma_update.sh").exists()


def test_launch_helper_windows_pencere_ve_betik(tmp_path, monkeypatch):
    si = _si()
    monkeypatch.setattr(si, "_helper_dir", lambda plan: str(tmp_path))
    cagri = {}

    def sahte_popen(arg, **kw):
        cagri["arg"] = arg

    monkeypatch.setattr(si.subprocess, "Popen", sahte_popen)
    monkeypatch.setattr(si.subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)
    monkeypatch.setattr(si.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    monkeypatch.setattr(si, "_ui_lang", "tr")
    res = si.launch_helper({"platform": "win32", "target": r"C:\HRMA"},
                           r"C:\U\Setup.exe", pid=7, versions=("3.0.6", "3.0.7"))
    assert res["launched"] is True and cagri["arg"][0] == "cmd.exe"
    ps = (tmp_path / si.UPDATE_WINDOW_WIN_NAME).read_text(encoding="ascii")
    assert ps.replace("\r\n", "\n") == _uw().build_win_window().replace("\r\n", "\n")
    with open(tmp_path / "hrma_update.bat", encoding="ascii", newline="") as f:
        bat = f.read()
    assert "echo lang=tr\r\n" in bat and "echo to_version=3.0.7\r\n" in bat


def test_indirme_surumu_kaydedilir_kuruluma_gider(monkeypatch, tmp_path):
    from hrma.utils import update_checker as uc
    monkeypatch.setattr(uc, "check_for_update", lambda force=False: {
        "available": True, "latest": "v3.0.7", "page_url": "x",
        "asset": {"name": "HRMA-Setup-3.0.7-macOS.dmg", "url": "https://x/y.dmg",
                  "size": 10, "digest": ""}})
    monkeypatch.setattr(uc, "_downloads_dir", lambda: str(tmp_path))

    monkeypatch.setattr(uc, "_run_download", lambda *a, **k: None)
    try:
        with uc._download_lock:
            uc._download.update(state="idle", pct=0, path="", error="", version="")
        assert uc.start_download()["started"] is True
        assert uc.download_status()["version"] == "3.0.7"
    finally:
        with uc._download_lock:
            uc._download.update(state="idle", pct=0, path="", error="", version="")


def test_arayuz_iletisi_pencereyi_soyler_iki_dilde():
    yol = os.path.join(KOK, "hrma", "static", "js", "i18n_common.js")
    with open(yol, encoding="utf-8") as f:
        i18n = f.read()
    degerler = re.findall(r"'update\.autoClose': '((?:[^'\\]|\\.)*)'", i18n)
    assert len(degerler) == 2
    en, tr = degerler
    assert "Updating HRMA" in en and "elapsed time" in en
    assert "HRMA güncelleniyor" in tr and "geçen süreyi" in tr
    assert "elle açmayın" not in tr and "do not open HRMA yourself" not in en
    with open(os.path.join(KOK, "hrma", "static", "js", "update_check.js"),
              encoding="utf-8") as f:
        js = f.read()
    bas = js.index("T('update.autoClose',")
    yedek = "".join(re.findall(r"'((?:[^'\\]|\\.)*)'", js[bas:js.index(");", bas)])[1:])
    assert yedek == en


# ---------------------------------------------------------------------------
# Uçtan uca (macOS; sahte .app + test DMG; pencere --offscreen)
# ---------------------------------------------------------------------------

SAHTE_OSASCRIPT_PENCERE = r"""#!/bin/bash
ALAN='@@ALAN@@'
{ printf '%s osascript' "$(date +%s)"; for a in "$@"; do printf ' |%s' "$a"; done; printf '\n'; } >> "$ALAN/osascript.log"
if [ "$1" = "-l" ] && [ "$2" = "JavaScript" ]; then
    exec /usr/bin/osascript -l JavaScript "$3" --offscreen --record "$ALAN/pencere" "${@:4}"
fi
exit 0
"""


def pencereli_senaryo(alan, *, dil="tr", yeni_cokme=False, ditto=None,
                      dmg_bos=False, oldur=None, pencere_betigi=True,
                      kit_ek_mb=0, **sure):
    """V306 düzeneğiyle güncelleme; betiğin yanında pencere betiği.

    ``oldur``: (adım, sinyal) — durum dosyasında adım görülünce betiğe sinyal.
    Dönüş: betik çıkışı, durum dosyası görüntüleri, pencere kayıtları.
    """
    si = _si()
    dz = v306.Duzenek(alan)
    v306._yaz(os.path.join(dz.fakebin, "osascript"),
              SAHTE_OSASCRIPT_PENCERE.replace("@@ALAN@@", alan), calistirilabilir=True)
    os.makedirs(os.path.join(alan, "pencere"))
    updater = os.path.join(alan, "updater")
    os.makedirs(updater)
    if pencere_betigi:
        v306._yaz(os.path.join(updater, si.UPDATE_WINDOW_MAC_NAME),
                  _uw().build_mac_window())
    durum_yolu = os.path.join(updater, si.UPDATE_STATUS_NAME)
    v306.sahte_app(dz.hedef, alan, "1.0.0", omur_s=40)
    kit = os.path.join(alan, "kit")
    os.makedirs(kit)
    if dmg_bos:
        v306._yaz(os.path.join(kit, "BENIOKU.txt"), "uygulama yok\n")
    else:
        v306.sahte_app(os.path.join(kit, "HRMA.app"), alan, "2.0.0",
                       cokme=yeni_cokme, omur_s=40)
        if kit_ek_mb:     # sıkıştırılamaz veri: kısmi kopya ölçülebilsin
            with open(os.path.join(kit, "HRMA.app", "Contents", "Resources",
                                   "veri.bin"), "wb") as f:
                f.write(os.urandom(int(kit_ek_mb * 1024 * 1024)))
    dmg = v306.dmg_uret(alan, kit)
    if ditto:
        dz.ditto_golge(ditto)
    betik = si.build_mac_helper(dil, from_version="1.0.0", to_version="2.0.0", **sure)
    g = {"durumlar": []}
    try:
        a = dz.uygulama_baslat()
        v306.bekle(lambda: any(o[2] == "hazir" for o in dz.olaylar()), 15)
        b = dz.betik_baslat(betik, a.pid, dmg)
        v306.bekle(lambda: os.path.exists(dz.kilit), 10)
        time.sleep(0.5)
        a.kill()
        a.wait(timeout=10)
        bitis = time.time() + 90
        while b.poll() is None and time.time() < bitis:
            try:
                with open(durum_yolu, encoding="utf-8") as f:
                    icerik = f.read()
                if not g["durumlar"] or g["durumlar"][-1] != icerik:
                    g["durumlar"].append(icerik)
                if oldur and ("\nstep=%s\n" % oldur[0]) in icerik:
                    b.send_signal(oldur[1])
                    oldur = None
            except OSError:
                pass
            time.sleep(0.05)
        assert b.poll() is not None, "betik bitmedi"
        g["rc"] = b.returncode
        # Betik çıkmadan hemen önce yazılan son durum yoklama döngüsünden
        # kaçabilir; dosya kalıcıdır, bir kez daha okunur.
        son = dz.oku(durum_yolu)
        if son and (not g["durumlar"] or g["durumlar"][-1] != son):
            g["durumlar"].append(son)
        kayit = os.path.join(alan, "pencere", "window_states.jsonl")
        if pencere_betigi:
            v306.bekle(lambda: '"exit":true' in dz.oku(kayit), 20, 0.2)
        g["pencere"] = [json.loads(s) for s in dz.oku(kayit).splitlines() if s]
        g["son_durum"] = dz.oku(durum_yolu)
        g["log"] = dz.oku(dz.log)
        g["osascript"] = dz.oku("osascript.log")
        g["open"] = dz.oku("open.log")
        g["hedef_surum"] = v306.surum_oku(dz.hedef)
        g["dmg"] = dmg
    finally:
        dz.temizle()
    return g


def _alan(durum, ad):
    m = re.search(r"(?m)^%s=(.*)$" % ad, durum)
    return m.group(1) if m else None


def _pencere_gorunumleri(g):
    return [k["view"] for k in g["pencere"] if "view" in k]


@MAC_E2E
def test_e2e_pencere_adimlari_izler_basarida_kendiliginden_kapanir(tmp_path):
    si = _si()
    yavas = v306.IKI_ASAMALI_DITTO
    g = pencereli_senaryo(str(tmp_path), ditto=yavas, kit_ek_mb=6,
                          progress_interval_s=1)
    assert g["rc"] == 0, g["log"]
    assert g["hedef_surum"] == "2.0.0"
    assert "update window started: pid=" in g["log"]
    # Her durum görüntüsü sözleşmeye uyar (başlık + end=1), sonuç sırası doğru
    for d in g["durumlar"]:
        assert d.startswith(si.UPDATE_STATUS_HEADER + "\n") and d.endswith("\nend=1\n")
    sonuclar = [_alan(d, "result") for d in g["durumlar"]]
    assert sonuclar[0] == "running" and _alan(g["son_durum"], "result") == "ok"
    adimlar = []
    for d in g["durumlar"]:
        s = _alan(d, "step")
        if not adimlar or adimlar[-1] != s:
            adimlar.append(s)
    # Sıra betiğin sırasıdır (yoklama yük altında kısa bir adımı kaçırabilir:
    # görülenler beklenen sıranın alt dizisi olmalı; kopya ve sonuç görülür).
    sira = ["waiting_exit", "mounting", "copying", "verifying", "quarantine_check",
            "closing", "swapping", "opening", "done"]
    assert [a for a in sira if a in adimlar] == adimlar, adimlar
    assert "copying" in adimlar and adimlar[-1] == "done", adimlar
    assert _alan(g["son_durum"], "from_version") == "1.0.0"
    assert _alan(g["son_durum"], "to_version") == "2.0.0"
    # Pencere: adımları sırayla gösterdi, kopyada GERÇEK ölçüm, sonda tamam
    gor = _pencere_gorunumleri(g)
    assert gor[-1]["final"] == "ok"
    asama_izi = [next((i for i, s in enumerate(v["stages"]) if s["mark"] == "current"), None)
                 for v in gor if v["final"] == "running"]
    gorulen = [i for i in asama_izi if i is not None]
    assert gorulen == sorted(gorulen) and 2 in gorulen, asama_izi
    oranli = [v for v in gor if v["fraction"] is not None]
    assert oranli and all(0 <= v["fraction"] <= 1 for v in oranli)
    for v in oranli:
        assert v["detail"].startswith("Kopyalanan: ")
    assert '"exit":true' in json.dumps(g["pencere"][-1], separators=(",", ":"))
    # Pencere açıkken bildirim gitmedi
    assert "display notification" not in g["osascript"]


@MAC_E2E
def test_e2e_kopya_hatasi_pencere_nedeni_ve_kurucuyu_yazar(tmp_path):
    si = _si()
    g = pencereli_senaryo(str(tmp_path), ditto=v306.BOZUK_DITTO)
    assert g["rc"] == 1 and g["hedef_surum"] == "1.0.0"
    assert _alan(g["son_durum"], "result") == "failed"
    assert _alan(g["son_durum"], "error") == "copy_failed"
    son = _pencere_gorunumleri(g)[-1]
    t = si.UPDATE_TEXTS["tr"]
    assert son["reason"] == t["window.reason.copy_failed"]
    assert son["action"] == t["window.action.mac_opened"]
    assert son["installer"] == t["window.installer"].format(path=g["dmg"])
    assert "open %s" % g["dmg"] in g["open"]                  # elle kurulum yedeği


@MAC_E2E
def test_e2e_bos_dmg_yeniden_indirme_der(tmp_path):
    g = pencereli_senaryo(str(tmp_path), dil="en", dmg_bos=True)
    assert g["rc"] == 1
    assert _alan(g["son_durum"], "error") == "no_app_in_dmg"
    son = _pencere_gorunumleri(g)[-1]
    assert son["action"] == _si().UPDATE_TEXTS["en"]["window.action.redownload"]


@MAC_E2E
def test_e2e_yeni_surum_acilmazsa_geri_yukleme_penceresi(tmp_path):
    g = pencereli_senaryo(str(tmp_path), yeni_cokme=True, launch_verify_s=6,
                          reopen_after_s=3, close_wait_s=2, term_wait_s=2)
    assert g["rc"] == 1 and g["hedef_surum"] == "1.0.0"
    assert _alan(g["son_durum"], "result") == "restored"
    assert _alan(g["son_durum"], "error") == "new_version_not_started"
    son = _pencere_gorunumleri(g)[-1]
    # Metindeki süre ürün sabitidir (pencere betiğe gömülü süreleri değil
    # sabiti bilir); testteki kısa süre yalnız testi hızlandırır.
    assert son["reason"] == "Yeni sürüm %d saniye içinde açılmadı." % \
        _si().HELPER_LAUNCH_VERIFY_S
    assert son["action"] == _si().UPDATE_TEXTS["tr"]["window.action.mac_restored"]


@MAC_E2E
def test_e2e_betik_sonlandirilirsa_kesinti_olarak_yazilir(tmp_path):
    yavas = v306.YAVAS_DITTO.replace("@@SURE@@", "4")
    g = pencereli_senaryo(str(tmp_path), ditto=yavas, oldur=("copying", signal.SIGTERM))
    assert g["rc"] != 0 and g["hedef_surum"] == "1.0.0"
    assert _alan(g["son_durum"], "result") == "failed"
    assert _alan(g["son_durum"], "error") == "interrupted"
    assert _pencere_gorunumleri(g)[-1]["reason"] == \
        _si().UPDATE_TEXTS["tr"]["window.reason.interrupted"]


@MAC_E2E
def test_e2e_betik_oldurulurse_pencere_kendisi_anlar(tmp_path):
    yavas = v306.YAVAS_DITTO.replace("@@SURE@@", "4")
    g = pencereli_senaryo(str(tmp_path), ditto=yavas, oldur=("copying", signal.SIGKILL))
    assert _alan(g["son_durum"], "result") == "running"       # betik yazamadı
    son = _pencere_gorunumleri(g)[-1]
    assert son["final"] == "failed"
    assert son["reason"] == _si().UPDATE_TEXTS["tr"]["window.reason.helper_gone"]


@MAC_E2E
def test_e2e_pencere_betigi_yoksa_bildirimlere_duser(tmp_path):
    g = pencereli_senaryo(str(tmp_path), pencere_betigi=False)
    assert g["rc"] == 0
    assert "update window: not available" in g["log"]
    t = _si().UPDATE_TEXTS["tr"]
    assert t["notify.start"] in g["osascript"] and t["notify.done"] in g["osascript"]
