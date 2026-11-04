"""V306/GÜNCELLEME bekçileri — Mac uygulama içi güncelleme deneyimi.

Kalemler (docs/scofield/raw/OH/V306/ana-model/brif_02kas/GUNCELLEME.md):
1. güncelleme kilidi (betik yazar, her çıkışta kaldırır; açılış kilidi okur,
   bayat kilit açılışı engellemez),
2. gerçek ilerleme (yalnız gerçek adım ve ``du`` ölçümü),
3. ``ditto --noqtn`` + hızlı karantina denetimi,
4. açılış doğrulaması (güncelleme sırasında açılmış ESKİ süreç "yeni sürüm
   açıldı" sayılmaz),
5. bildirim ve bekleme penceresi kullanıcının dilinde.

GERÇEK KURULU UYGULAMAYA DOKUNULMAZ. Uçtan uca senaryolar test başına açılan
geçici dizinde küçük sahte ``.app`` paketleri ve ``hdiutil create`` ile
üretilen küçük bir test DMG'siyle koşar. ``open`` ve ``osascript`` PATH
gölgelemesiyle sahte komutlara yönlenir: ekranda bildirim ya da pencere
açılmaz, çağrılar dosyaya yazılır ve denetlenir. Sahte ``open`` bir ``.app``
için LaunchServices davranışını taklit eder: aynı paket kimliğiyle çalışan
bir süreç varsa YENİSİNİ BAŞLATMAZ, çalışanı öne getirir (gerçek ``open``
belgelenmiş davranışı); ``-n`` verilirse her durumda yeni süreç açar.
"""

import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAKETLEME = os.path.join(KOK, "packaging")

MAC_E2E = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("hdiutil") is None
    or shutil.which("ditto") is None,
    reason="uçtan uca güncelleme senaryoları yalnız macOS'ta (hdiutil + ditto)")


# ---------------------------------------------------------------------------
# Uçtan uca düzenek (önce/sonra ölçüm betiği de bunu kullanır)
# ---------------------------------------------------------------------------

SAHTE_OPEN = r"""#!/bin/bash
# Sahte open: cagrilari kaydeder. .app icin LaunchServices taklidi: ayni
# paket kimligiyle calisan surec varsa YENISINI BASLATMAZ, one getirir.
ALAN='@@ALAN@@'
echo "$(date +%s) open $*" >> "$ALAN/open.log"
YENI=""
if [ "$1" = "-n" ]; then YENI=1; shift; fi
case "$1" in
  *.app|*.app/)
    if [ -z "$YENI" ] && ps ax -o command= | grep -F "$ALAN/" \
         | grep -F "sahte_baslatici.py" | grep -v grep >/dev/null; then
        echo "$(date +%s) open: calisan HRMA one getirildi (yeni surec yok)" >> "$ALAN/open.log"
        exit 0
    fi
    HOME="$ALAN/home" nohup "$1/Contents/MacOS/HRMA" >>"$ALAN/uygulama_cikti.log" 2>&1 &
    echo "$(date +%s) open: baslatildi pid=$!" >> "$ALAN/open.log"
    ;;
esac
exit 0
"""

SAHTE_OSASCRIPT = r"""#!/bin/bash
ALAN='@@ALAN@@'
{ printf '%s osascript' "$(date +%s)"; for a in "$@"; do printf ' |%s' "$a"; done; printf '\n'; } >> "$ALAN/osascript.log"
exit 0
"""

# Kopyayı yavaşlatan ditto sarmalayıcısı: gerçek ditto'yu çağırır, sonra
# bekler (ilerleme yoklaması tamamlanmış boyutu görebilsin). Çıkış kodu
# gerçek ditto'nunkidir.
YAVAS_DITTO = r"""#!/bin/bash
/usr/bin/ditto "$@"; rc=$?
sleep @@SURE@@
exit $rc
"""

BOZUK_DITTO = r"""#!/bin/bash
echo "sahte ditto: kopya hatasi" >&2
exit 1
"""

SAHTE_BASLATICI = r'''
import os, sys, time, signal
ALAN = @@ALAN@@
KIP = @@KIP@@
COKME = @@COKME@@
OMUR_S = @@OMUR@@
TERM_YOKSAY = @@TERMYOKSAY@@
UYG = os.path.dirname(os.path.abspath(__file__))
SURUM = open(os.path.join(UYG, "surum.txt")).read().strip()


def olay(m):
    with open(os.path.join(ALAN, "olaylar.log"), "a") as f:
        f.write("%.3f pid=%d surum=%s %s\n" % (time.time(), os.getpid(), SURUM, m))


olay("basladi yol=" + os.path.abspath(__file__))
if COKME:
    olay("cokme")
    sys.exit(3)
if TERM_YOKSAY:
    signal.signal(signal.SIGTERM, lambda *a: olay("sigterm yok sayildi"))
else:
    signal.signal(signal.SIGTERM, lambda *a: (olay("sigterm"), os._exit(0)))
if KIP == "kilitli":
    sys.path.insert(0, @@PAKETLEME@@)
    sys.path.insert(0, @@KOK@@)
    import launcher
    karar = launcher._guncelleme_kilidi_karari()
    olay("karar=" + karar)
    if karar == "wait":
        son = launcher._guncelleme_bitene_kadar_bekle(aralik_s=0.2)
        olay("bekleme bitti: " + son)
        sys.exit(0)
    if karar == "exit":
        olay("cikis (kapanis adimi)")
        sys.exit(0)
olay("hazir")
bitis = time.time() + OMUR_S
while time.time() < bitis:
    time.sleep(0.1)
olay("omur doldu")
'''


def _yaz(yol, icerik, calistirilabilir=False):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(icerik)
    if calistirilabilir:
        os.chmod(yol, os.stat(yol).st_mode | stat.S_IXUSR | stat.S_IXGRP
                 | stat.S_IXOTH)


def sahte_app(yol, alan, surum, kip="kilitli", cokme=False, omur_s=12.0,
              hrma_dizini=True, term_yoksay=False):
    """Küçük sahte HRMA.app: Info.plist + MacOS/HRMA + sahte başlatıcı.

    ``MacOS/HRMA`` gerçek paketteki gibi kendi paketindeki başlatıcıyı
    ``exec`` eder; süreç komut satırı paket yolunu taşır (gerçek HRMA:
    ``…/HRMA.app/Contents/Resources/python/bin/python3.12 …/launcher.py``).
    """
    _yaz(os.path.join(yol, "Contents", "Info.plist"),
         '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
         '<key>CFBundleIdentifier</key><string>test.hrma.sahte</string>'
         '<key>CFBundleShortVersionString</key><string>%s</string>'
         '<key>CFBundleExecutable</key><string>HRMA</string>'
         '</dict></plist>\n' % surum)
    _yaz(os.path.join(yol, "Contents", "MacOS", "HRMA"),
         '#!/bin/bash\nAPP="$(cd "$(dirname "$0")/../.." && pwd)"\n'
         'exec %s "$APP/Contents/Resources/app/sahte_baslatici.py"\n'
         % sys.executable, calistirilabilir=True)
    uyg = os.path.join(yol, "Contents", "Resources", "app")
    if hrma_dizini:
        os.makedirs(os.path.join(uyg, "hrma"), exist_ok=True)
    _yaz(os.path.join(uyg, "surum.txt"), surum + "\n")
    _yaz(os.path.join(uyg, "sahte_baslatici.py"),
         SAHTE_BASLATICI.replace("@@ALAN@@", repr(alan))
         .replace("@@KIP@@", repr(kip)).replace("@@COKME@@", repr(cokme))
         .replace("@@OMUR@@", repr(omur_s))
         .replace("@@TERMYOKSAY@@", repr(term_yoksay))
         .replace("@@PAKETLEME@@", repr(PAKETLEME))
         .replace("@@KOK@@", repr(KOK)))
    return yol


def dmg_uret(alan, kaynak_dizin, ad="HRMA-Setup-test.dmg"):
    dmg = os.path.join(alan, ad)
    subprocess.run(["hdiutil", "create", "-quiet", "-volname", "HRMA Setup",
                    "-srcfolder", kaynak_dizin, "-ov", "-format", "UDZO", dmg],
                   check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    return dmg


class Duzenek:
    """Bir senaryonun alanı: sahte ev dizini, Applications, fakebin, günlükler."""

    def __init__(self, alan):
        self.alan = alan
        self.home = os.path.join(alan, "home")
        self.apps = os.path.join(alan, "Applications")
        self.hedef = os.path.join(self.apps, "HRMA.app")
        self.fakebin = os.path.join(alan, "fakebin")
        self.tmp = os.path.join(alan, "tmp")
        for d in (self.home, os.path.join(self.home, "Documents", "HRMA"),
                  self.apps, self.fakebin, self.tmp):
            os.makedirs(d, exist_ok=True)
        _yaz(os.path.join(self.fakebin, "open"),
             SAHTE_OPEN.replace("@@ALAN@@", alan), calistirilabilir=True)
        _yaz(os.path.join(self.fakebin, "osascript"),
             SAHTE_OSASCRIPT.replace("@@ALAN@@", alan), calistirilabilir=True)
        self.log = os.path.join(self.home, "Documents", "HRMA",
                                "hrma_update_log.txt")
        self.kilit = os.path.join(self.home, "Documents", "HRMA",
                                  "hrma_update.lock")

    def ortam(self):
        env = dict(os.environ)
        env["HOME"] = self.home
        env["TMPDIR"] = self.tmp
        env["PATH"] = self.fakebin + ":/usr/bin:/bin:/usr/sbin:/sbin"
        return env

    def ditto_golge(self, icerik):
        _yaz(os.path.join(self.fakebin, "ditto"), icerik,
             calistirilabilir=True)

    def uygulama_baslat(self):
        """Güncellemeyi isteyen, çalışan uygulama (PID betiğe verilir)."""
        return subprocess.Popen(
            [os.path.join(self.hedef, "Contents", "MacOS", "HRMA")],
            env=dict(self.ortam(), PATH="/usr/bin:/bin:/usr/sbin:/sbin"),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)

    def kullanici_acar(self):
        """Kullanıcı Finder'dan HRMA'yı açar (sahte open → LaunchServices)."""
        subprocess.run([os.path.join(self.fakebin, "open"), self.hedef],
                       env=self.ortam(), check=True, timeout=10)

    def betik_baslat(self, betik_icerik, pid, dmg, kilit=True):
        yol = os.path.join(self.alan, "updater", "hrma_update.sh")
        _yaz(yol, betik_icerik)
        arg = ["/bin/bash", yol, str(pid), dmg, self.hedef, self.log]
        if kilit:
            arg.append(self.kilit)
        return subprocess.Popen(arg, env=self.ortam(),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True, cwd="/")

    def oku(self, ad):
        yol = os.path.join(self.alan, ad) if not os.path.isabs(ad) else ad
        if not os.path.isfile(yol):
            return ""
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()

    def olaylar(self):
        """[(pid, surum, olay)] — sahte uygulamaların günlüğü."""
        out = []
        for satir in self.oku("olaylar.log").splitlines():
            m = re.match(r"\S+ pid=(\d+) surum=(\S+) (.*)$", satir)
            if m:
                out.append((int(m.group(1)), m.group(2), m.group(3)))
        return out

    def calisan_pidler(self):
        """Alan altındaki paketlerden çalışan sahte uygulama süreçleri."""
        r = subprocess.run(["ps", "ax", "-o", "pid=", "-o", "command="],
                           capture_output=True, text=True)
        pidler = []
        for satir in r.stdout.splitlines():
            satir = satir.strip()
            if self.alan + "/" in satir and "sahte_baslatici.py" in satir:
                pidler.append(int(satir.split(None, 1)[0]))
        return pidler

    def temizle(self):
        """Alanla ilgili kalan bütün süreçleri (betik + sahte uygulama) kapat."""
        r = subprocess.run(["ps", "ax", "-o", "pid=", "-o", "command="],
                           capture_output=True, text=True)
        for satir in r.stdout.splitlines():
            satir = satir.strip()
            if self.alan + "/" in satir:
                pid = int(satir.split(None, 1)[0])
                if pid == os.getpid():
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        # Bağlı kalmış test görüntüsü (betik öldürüldüyse) ayrılır
        r = subprocess.run(["hdiutil", "info"], capture_output=True, text=True)
        for satir in r.stdout.splitlines():
            if self.tmp in satir:
                yol = satir.split("\t")[-1].strip()
                subprocess.run(["hdiutil", "detach", yol, "-force"],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)


def surum_oku(app_yolu):
    p = os.path.join(app_yolu, "Contents", "Resources", "app", "surum.txt")
    if not os.path.isfile(p):
        return None
    with open(p) as f:
        return f.read().strip()


def eski_kopyalar(duzenek):
    """Hedefin yanında kalan .HRMA.app.old.* / .update.* dizinleri."""
    return sorted(a for a in os.listdir(duzenek.apps)
                  if a.startswith(".HRMA.app."))


def bekle(kosul, sure_s, aralik_s=0.1):
    bitis = time.time() + sure_s
    while time.time() < bitis:
        if kosul():
            return True
        time.sleep(aralik_s)
    return kosul()


# ---------------------------------------------------------------------------
# Ortak senaryo koşucusu
# ---------------------------------------------------------------------------

def senaryo(alan, betik, *, kip="kilitli", yeni_cokme=False,
            kullanici_acar=False, ditto=None, kit_hrma_dizini=True,
            dmg_bos=False, beklenen_sure_s=90, betigi_oldur_adimda=None,
            kit_ek_mb=0, eski_kip=None, eski_term_yoksay=False):
    """Bir güncelleme senaryosunu koşar; gözlemleri sözlük olarak döndürür.

    ``betigi_oldur_adimda``: kilitte bu adım görülünce betiğe SIGTERM.
    """
    dz = Duzenek(alan)
    sahte_app(dz.hedef, alan, "1.0.0", kip=eski_kip or kip, omur_s=40,
              term_yoksay=eski_term_yoksay)
    kit = os.path.join(alan, "kit")
    os.makedirs(kit, exist_ok=True)
    if not dmg_bos:
        sahte_app(os.path.join(kit, "HRMA.app"), alan, "2.0.0", kip=kip,
                  cokme=yeni_cokme, omur_s=40, hrma_dizini=kit_hrma_dizini)
        if kit_ek_mb:
            # Sıkıştırılamaz veri: kısmi kopya ölçülebilsin
            with open(os.path.join(kit, "HRMA.app", "Contents", "Resources",
                                   "veri.bin"), "wb") as f:
                f.write(os.urandom(int(kit_ek_mb * 1024 * 1024)))
    else:
        _yaz(os.path.join(kit, "BENIOKU.txt"), "uygulama yok\n")
    dmg = dmg_uret(alan, kit)
    if ditto:
        dz.ditto_golge(ditto)
    gozlem = {"kilit_goruntuleri": []}
    try:
        a = dz.uygulama_baslat()
        # İsteyen uygulama açılış kararını VERMİŞ ve çalışıyor olmalı
        bekle(lambda: any(o[2] == "hazir" for o in dz.olaylar()), 15)
        b = dz.betik_baslat(betik, a.pid, dmg)
        bekle(lambda: os.path.exists(dz.kilit), 10)
        time.sleep(0.5)
        a.kill()      # schedule_app_exit taklidi (gerçekte os._exit(0))
        a.wait(timeout=10)
        if kullanici_acar:
            time.sleep(0.3)
            dz.kullanici_acar()
        bitis = time.time() + beklenen_sure_s
        while b.poll() is None and time.time() < bitis:
            try:
                with open(dz.kilit, encoding="utf-8") as f:
                    icerik = f.read()
                if not gozlem["kilit_goruntuleri"] or \
                        gozlem["kilit_goruntuleri"][-1] != icerik:
                    gozlem["kilit_goruntuleri"].append(icerik)
                if betigi_oldur_adimda and \
                        ("\nstep=%s\n" % betigi_oldur_adimda) in icerik:
                    b.send_signal(signal.SIGTERM)
                    betigi_oldur_adimda = None
            except OSError:
                pass
            time.sleep(0.05)
        assert b.poll() is not None, "betik %d sn içinde bitmedi" % beklenen_sure_s
        gozlem["rc"] = b.returncode
        time.sleep(0.3)
        gozlem["calisan"] = {p: s for p, s, _ in dz.olaylar()
                             if p in dz.calisan_pidler()}
        gozlem["hedef_surum"] = surum_oku(dz.hedef)
        gozlem["yaninda"] = eski_kopyalar(dz)
        gozlem["kilit_var"] = os.path.exists(dz.kilit)
        gozlem["log"] = dz.oku(dz.log)
        gozlem["open"] = dz.oku("open.log")
        gozlem["osascript"] = dz.oku("osascript.log")
        gozlem["olaylar"] = dz.olaylar()
        gozlem["dmg"] = dmg
        gozlem["duzenek"] = dz
    finally:
        dz.temizle()
    return gozlem


def _betik(**kw):
    from hrma.utils import self_install as si
    return si.build_mac_helper(**kw)


# ---------------------------------------------------------------------------
# Kalem 1 — kilit: biçim, karar, bayatlık (birim)
# ---------------------------------------------------------------------------

def _kilit_yaz(yol, pid, started, step="copying", phase="wait", done="",
               total="", lang="", target="/Applications/HRMA.app"):
    with open(yol, "w", encoding="utf-8") as f:
        f.write("hrma-update-lock 1\npid=%s\nstarted=%s\nstep=%s\nphase=%s\n"
                "done_kb=%s\ntotal_kb=%s\nlang=%s\ntarget=%s\n"
                % (pid, started, step, phase, done, total, lang, target))


def test_kilit_okuma_hedef_satir_sonu_icerse_bile(tmp_path):
    from hrma.utils import self_install as si
    yol = str(tmp_path / "k.lock")
    _kilit_yaz(yol, 4242, 1000, done="12", total="34", lang="tr",
               target="/A/HR\nMA.app")
    k = si.read_update_lock(yol)
    assert k == {"pid": 4242, "started": 1000, "step": "copying",
                 "phase": "wait", "done_kb": 12, "total_kb": 34,
                 "lang": "tr", "target": "/A/HR\nMA.app"}


@pytest.mark.parametrize("icerik", [
    b"", b"baska bir dosya\n", b"hrma-update-lock 9\npid=1\n",
    b"hrma-update-lock 1\n" + b"x" * (70 * 1024)])
def test_bozuk_kilit_bayattir(tmp_path, icerik):
    from hrma.utils import self_install as si
    yol = tmp_path / "k.lock"
    yol.write_bytes(icerik)
    karar = si.update_lock_decision(str(yol), helper_alive=lambda p: (True, ""))
    assert karar["decision"] == "stale", karar


def test_kilit_karari_asamalar(tmp_path):
    from hrma.utils import self_install as si
    yol = str(tmp_path / "k.lock")
    canli = lambda p: (True, "helper alive")  # noqa: E731
    simdi = 10_000
    for faz, beklenen in (("wait", "wait"), ("closing", "exit"),
                          ("launch", "normal"), ("gelecekte-eklenen", "wait")):
        _kilit_yaz(yol, 4242, simdi - 30, phase=faz)
        assert si.update_lock_decision(yol, now=simdi, helper_alive=canli)[
            "decision"] == beklenen, faz
    assert si.update_lock_decision(str(tmp_path / "yok"))["decision"] == "none"


def test_kilit_yas_siniri_ve_gelecek_zaman(tmp_path):
    from hrma.utils import self_install as si
    yol = str(tmp_path / "k.lock")
    canli = lambda p: (True, "helper alive")  # noqa: E731
    simdi = 100_000
    _kilit_yaz(yol, 4242, simdi - si.UPDATE_LOCK_MAX_AGE_S + 5)
    assert si.update_lock_decision(yol, now=simdi, helper_alive=canli)[
        "decision"] == "wait"
    _kilit_yaz(yol, 4242, simdi - si.UPDATE_LOCK_MAX_AGE_S - 5)
    k = si.update_lock_decision(yol, now=simdi, helper_alive=canli)
    assert k["decision"] == "stale" and "older" in k["reason"]
    _kilit_yaz(yol, 4242, simdi + si.UPDATE_LOCK_FUTURE_SLACK_S + 5)
    assert si.update_lock_decision(yol, now=simdi, helper_alive=canli)[
        "decision"] == "stale"


@pytest.mark.skipif(os.name != "posix", reason="PID denetimi yalnız POSIX")
def test_olu_pid_ve_yeniden_kullanilan_pid_bayat(tmp_path):
    from hrma.utils import self_install as si
    yol = str(tmp_path / "k.lock")
    p = subprocess.Popen(["/bin/sleep", "0"])
    p.wait()
    _kilit_yaz(yol, p.pid, int(time.time()))
    k = si.update_lock_decision(yol)
    assert k["decision"] == "stale" and "not running" in k["reason"], k
    # Yaşayan ama yardımcı betik OLMAYAN süreç (bu pytest süreci): PID
    # yeniden kullanımı sayılır, kilit açılışı engellemez.
    _kilit_yaz(yol, os.getpid(), int(time.time()))
    k = si.update_lock_decision(yol)
    assert k["decision"] == "stale" and "another program" in k["reason"], k


@pytest.mark.skipif(sys.platform != "darwin", reason="kilit yalnız macOS")
def test_canli_yardimci_kilidi_acilisi_bekletir(tmp_path):
    from hrma.utils import self_install as si
    betik = tmp_path / ("%s.sh" % si.HELPER_SCRIPT_STEM)
    betik.write_text("sleep 20\n")
    p = subprocess.Popen(["/bin/bash", str(betik)])
    try:
        yol = str(tmp_path / "k.lock")
        _kilit_yaz(yol, p.pid, int(time.time()))
        assert si.update_lock_decision(yol)["decision"] == "wait"
    finally:
        p.kill()
        p.wait()


@pytest.mark.skipif(sys.platform != "darwin", reason="kilit yalnız macOS")
def test_acilis_bayat_kilidi_kaldirir_gunluge_yazar_normal_acar(
        tmp_path, monkeypatch):
    """Fail-safe: ölü PID'li kilit uygulamayı engellemez, kaldırılır, loglanır."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Documents").mkdir()
    sys.path.insert(0, PAKETLEME)
    try:
        import launcher
    finally:
        sys.path.remove(PAKETLEME)
    from hrma.utils import self_install as si
    p = subprocess.Popen(["/bin/sleep", "0"])
    p.wait()
    _kilit_yaz(si.update_lock_path(), p.pid, int(time.time()))
    assert launcher._guncelleme_kilidi_karari() == "normal"
    assert not os.path.exists(si.update_lock_path())
    with open(si.update_log_path(), encoding="utf-8") as f:
        gunluk = f.read()
    assert "stale update lock removed" in gunluk and "not running" in gunluk


def test_betik_bash_gecerli_ve_ascii(tmp_path):
    for lang in (None, "en", "tr"):
        s = _betik(lang=lang) if lang else _betik()
        s.encode("ascii")
        yol = tmp_path / "h.sh"
        yol.write_text(s, encoding="ascii")
        r = subprocess.run(["bash", "-n", str(yol)], capture_output=True,
                           text=True)
        assert r.returncode == 0, r.stderr
        assert "@@AYARLAR@@" not in s


# ---------------------------------------------------------------------------
# Kalem 1 — kilit her çıkış yolunda kalkar (uçtan uca)
# ---------------------------------------------------------------------------

@MAC_E2E
def test_e2e_basari_kilit_kalkar_yeni_surum_calisir(tmp_path):
    g = senaryo(str(tmp_path), _betik())
    assert g["rc"] == 0, g["log"]
    assert g["kilit_var"] is False
    assert g["hedef_surum"] == "2.0.0"
    assert g["yaninda"] == []
    assert sorted(g["calisan"].values()) == ["2.0.0"], g
    assert "update lock removed" in g["log"]
    # Kilit, betik çalışırken gerçekten yazıldı ve aşamaları taşıdı
    fazlar = re.findall(r"\nphase=(\w+)\n", "".join(g["kilit_goruntuleri"]))
    assert "wait" in fazlar and "launch" in fazlar


@MAC_E2E
def test_e2e_kopya_hatasi_kilit_kalkar_hedef_saglam(tmp_path):
    g = senaryo(str(tmp_path), _betik(), ditto=BOZUK_DITTO)
    assert g["rc"] == 1
    assert g["kilit_var"] is False
    assert g["hedef_surum"] == "1.0.0"
    assert g["yaninda"] == []
    assert "FALLBACK: copy (ditto) failed" in g["log"]
    assert "open %s" % g["dmg"] in g["open"]        # elle kurulum yedeği


@MAC_E2E
def test_e2e_dmg_bos_kilit_kalkar(tmp_path):
    g = senaryo(str(tmp_path), _betik(), dmg_bos=True)
    assert g["rc"] == 1 and g["kilit_var"] is False
    assert g["hedef_surum"] == "1.0.0"
    assert "no .app found inside the dmg" in g["log"]


@MAC_E2E
def test_e2e_yeni_surum_acilmazsa_geri_yukleme_kilit_kalkar(tmp_path):
    g = senaryo(str(tmp_path), _hizli(), yeni_cokme=True)
    assert g["rc"] == 1
    assert g["kilit_var"] is False
    assert g["hedef_surum"] == "1.0.0"
    assert g["yaninda"] == []
    assert "restoring the previous version" in g["log"]
    assert "update failed, previous version restored" in g["log"]


@MAC_E2E
def test_e2e_betik_sonlandirilirsa_kilit_ve_staging_kalkar(tmp_path):
    yavas = YAVAS_DITTO.replace("@@SURE@@", "4")
    g = senaryo(str(tmp_path), _betik(), ditto=yavas,
                betigi_oldur_adimda="copying")
    assert g["rc"] != 0
    assert g["kilit_var"] is False
    assert g["hedef_surum"] == "1.0.0"
    assert g["yaninda"] == [], g["yaninda"]   # staging temizlendi


# ---------------------------------------------------------------------------
# Kalem 2 — gerçek ilerleme
# ---------------------------------------------------------------------------

# İki aşamalı ditto: önce Resources (büyük dosya), 2,5 sn ara, sonra kalan.
# Ölçüm aralığı 1 sn olduğundan ara sırasında KISMİ kopya ölçülür.
IKI_ASAMALI_DITTO = r"""#!/bin/bash
KAYNAK="${@: -2:1}"; HEDEF="${@: -1}"
/usr/bin/ditto --noqtn "$KAYNAK/Contents/Resources" "$HEDEF/Contents/Resources" || exit $?
sleep 2.5
/usr/bin/ditto "$@"
"""


def test_gorunum_ilerleme_yalniz_olculen_degerden():
    from hrma.utils import self_install as si
    k = {"pid": 1, "started": 1000, "step": "copying", "phase": "wait",
         "done_kb": 524288, "total_kb": 1380045, "lang": "tr", "target": "/x"}
    v = si.update_waiting_view(k, now=1125)
    assert v["step"] == "Yeni sürüm kopyalanıyor"
    assert v["progress"] == "Kopyalanan: 512 MB / 1.348 MB"
    assert v["elapsed"] == "Geçen süre: 2 dk 05 sn"
    assert v["fraction"] == pytest.approx(524288 / 1380045)
    v = si.update_waiting_view(dict(k, lang="en"), now=1125)
    assert v["progress"] == "Copied 512 MB of 1,348 MB"
    assert v["elapsed"] == "Elapsed: 2 min 05 s"
    # Ölçülemeyen adım: yalnız adıyla; çubuk yok
    for step in ("mounting", "verifying", "quarantine", "closing"):
        v = si.update_waiting_view(dict(k, step=step), now=1125)
        assert v["fraction"] is None and v["progress"] == "", step
    # Kopyalanan henüz ölçülmediyse oran yok, yalnız toplam
    v = si.update_waiting_view(dict(k, done_kb=None), now=1125)
    assert v["fraction"] is None
    assert v["progress"] == "Kopyalanacak boyut: 1.348 MB"
    # Kopyalanan > toplam (dosya sistemi farkı): oran kırpılmaz, verilmez
    v = si.update_waiting_view(dict(k, done_kb=1400000), now=1125)
    assert v["fraction"] is None
    # Bilinmeyen adım genel adla
    assert si.update_waiting_view(dict(k, step="zzz"), now=1125)[
        "step"] == "Güncelleme sürüyor"


def test_bekleme_penceresi_zamana_bagli_ilerleme_icermez():
    """Sahte ilerleme yasağı: pencerede zamanlayıcı yok, çubuğu yalnız
    görünümdeki ``fraction`` sürer; betikte kopyalanan yalnız du'dan."""
    with open(os.path.join(PAKETLEME, "launcher.py"), encoding="utf-8") as f:
        src = f.read()
    bas = src.index('BEKLEME_HTML = """')
    html = src[bas:src.index('</html>"""', bas)]
    assert "setInterval" not in html and "setTimeout" not in html
    assert "requestAnimationFrame" not in html and "@keyframes" not in html
    from hrma.utils import self_install as si
    atamalar = re.findall(r'DONE_KB=("[^"\n]*"|\S*)', si.MAC_HELPER)
    assert set(atamalar) <= {'""', '"$D"'}, atamalar
    # D yalnız du çıktısından atanır
    for m in re.finditer(r'^\s*D="\$\((.*)\)"$', si.MAC_HELPER, re.M):
        assert m.group(1).startswith("du -sk "), m.group(0)
    assert re.search(r'^\s*T="\$\(du -sk "\$SRC"', si.MAC_HELPER, re.M)


@MAC_E2E
def test_e2e_ilerleme_gercek_du_olcumu(tmp_path):
    g = senaryo(str(tmp_path), _betik(progress_interval_s=1),
                ditto=IKI_ASAMALI_DITTO, kit_ek_mb=6)
    assert g["rc"] == 0, g["log"]
    kopya = [k for k in g["kilit_goruntuleri"] if "\nstep=copying\n" in k]
    assert kopya, "kopya adımında kilit görülmedi"
    toplamlar = {int(m) for k in kopya
                 for m in re.findall(r"\ntotal_kb=(\d+)\n", k)}
    assert len(toplamlar) == 1, toplamlar
    toplam = toplamlar.pop()
    assert toplam >= 6 * 1024
    yapilan = [int(m) for k in kopya
               for m in re.findall(r"\ndone_kb=(\d+)\n", k)]
    assert yapilan, "ilerleme ölçümü yazılmadı"
    assert yapilan == sorted(yapilan), yapilan
    assert all(0 <= d <= toplam for d in yapilan), (yapilan, toplam)
    # Kopyanın ara durumu ölçüldü (yalnız Resources kopyalanmışken)
    assert min(yapilan) < toplam
    # Günlükte her ölçüm satırı var ve kilitteki değerlerle aynı
    gunluk = [int(m) for m in re.findall(r"progress: copied (\d+) KB of (?:\d+) KB",
                                         g["log"])]
    assert set(yapilan) <= set(gunluk)
    son = re.search(r"copied \(\S+\): (\d+) KB \(source (\d+) KB\)", g["log"])
    assert son and int(son.group(2)) == toplam


# ---------------------------------------------------------------------------
# Kalem 3 — ditto --noqtn + karantina savunması
# ---------------------------------------------------------------------------

KARANTINA_EKLEYEN_DITTO = r"""#!/bin/bash
/usr/bin/ditto "$@" || exit $?
xattr -w com.apple.quarantine "0083;00000000;;" "${@: -1}/Contents/MacOS/HRMA"
"""


def _karantina(yol):
    r = subprocess.run(["xattr", "-p", "com.apple.quarantine", yol],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


@MAC_E2E
def test_e2e_karantinali_dmg_noqtn_ile_temiz_kopya(tmp_path, monkeypatch):
    """Karantinalı DMG'den ditto varsayılanı karantinayı kopyaya taşır
    (ölçüldü: '0083;00000000;;'); --noqtn taşımaz, xattr -dr adımı koşmaz."""
    orijinal = dmg_uret

    def karantinali_dmg(alan, kaynak, ad="HRMA-Setup-test.dmg"):
        dmg = orijinal(alan, kaynak, ad)
        subprocess.run(["xattr", "-w", "com.apple.quarantine",
                        "0083;%x;Safari;" % int(time.time()), dmg], check=True)
        return dmg

    monkeypatch.setitem(globals(), "dmg_uret", karantinali_dmg)
    g = senaryo(str(tmp_path), _betik())
    assert g["rc"] == 0, g["log"]
    assert _karantina(g["dmg"]) is not None          # DMG gerçekten karantinalı
    assert "quarantine check: clean" in g["log"], g["log"]
    assert "removing it recursively" not in g["log"]
    dz = g["duzenek"]
    assert _karantina(dz.hedef) is None
    assert _karantina(os.path.join(dz.hedef, "Contents", "MacOS", "HRMA")) is None


@MAC_E2E
def test_e2e_karantina_kalmissa_eski_adim_uygulanir(tmp_path):
    g = senaryo(str(tmp_path), _betik(), ditto=KARANTINA_EKLEYEN_DITTO)
    assert g["rc"] == 0, g["log"]
    assert "quarantine check: found on" in g["log"]
    assert "quarantine removed" in g["log"]
    dz = g["duzenek"]
    assert _karantina(os.path.join(dz.hedef, "Contents", "MacOS", "HRMA")) is None
    # Karantina takastan ÖNCE kaldırıldı (staging üzerinde)
    log = g["log"]
    assert log.index("quarantine removed") < log.index("step: swapping")


# ---------------------------------------------------------------------------
# Kalem 4 — açılış doğrulaması: güncelleme sırasında açılan ESKİ süreç
# ---------------------------------------------------------------------------

def _hizli(**kw):
    """Testte kısa bekleme süreleriyle betik (mantık aynı, yalnız süreler)."""
    ayar = dict(close_wait_s=2, term_wait_s=2, launch_verify_s=8,
                reopen_after_s=4)
    ayar.update(kw)
    return _betik(**ayar)


@MAC_E2E
def test_e2e_kullanici_eski_surumu_acarsa_bekler_yeni_surum_acilir(tmp_path):
    """15 Eki olayı: güncelleme sürerken HRMA açılır. Açılış kilidi görüp
    bekler (eski sürüm AÇILMAZ), kapanış adımında kendiliğinden çıkar; betik
    yeni sürümü açar ve doğrulama yeni süreci bulur."""
    g = senaryo(str(tmp_path), _hizli(), kullanici_acar=True)
    assert g["rc"] == 0, g["log"]
    assert g["hedef_surum"] == "2.0.0" and g["yaninda"] == []
    olay = g["olaylar"]
    kullanici = [p for p, s, o in olay if s == "1.0.0" and o == "karar=wait"]
    assert len(kullanici) == 1, olay              # açılış bekledi
    assert any(p == kullanici[0] and o.startswith("bekleme bitti: phase: exit")
               for p, s, o in olay), olay
    assert sorted(g["calisan"].values()) == ["2.0.0"], g["calisan"]
    yeni = [p for p, s in g["calisan"].items() if s == "2.0.0"]
    assert ("new version running: pid=%d" % yeni[0]) in g["log"]
    assert "calisan HRMA one getirildi" not in g["open"]


@MAC_E2E
def test_e2e_kilidi_bilmeyen_eski_surec_kapatilir(tmp_path):
    """Kilidi bilmeyen (bayat kilitle açılmış) eski süreç kapanış adımında
    SIGTERM ile kapatılır; doğrulama yalnız 'open' sonrası yeni süreci sayar."""
    g = senaryo(str(tmp_path), _hizli(), kullanici_acar=True, eski_kip="eski")
    assert g["rc"] == 0, g["log"]
    assert "sending SIGTERM" in g["log"]
    assert any(s == "1.0.0" and o == "sigterm" for p, s, o in g["olaylar"])
    assert sorted(g["calisan"].values()) == ["2.0.0"], g["calisan"]
    assert g["hedef_surum"] == "2.0.0"


@MAC_E2E
def test_e2e_kapanmayan_eski_surec_varken_basari_denmez(tmp_path):
    """Eski süreç SIGTERM'i yok sayıyorsa takas YAPILMAZ, başarı denmez,
    eski paket silinmez; kilit kalkar ve elle kurulum açılır."""
    g = senaryo(str(tmp_path), _hizli(), kullanici_acar=True, eski_kip="eski",
                eski_term_yoksay=True)
    assert g["rc"] == 1, g["log"]
    assert "another HRMA instance from the target is still running" in g["log"]
    assert "update complete" not in g["log"].lower().replace(
        "helper exit", "")
    assert g["hedef_surum"] == "1.0.0" and g["yaninda"] == []
    assert g["kilit_var"] is False


def _dogrulama_islevleri():
    from hrma.utils import self_install as si
    s = si.build_mac_helper()
    parcalar = [re.search(r'^UID_SELF=.*$', s, re.M).group(0)]
    for ad in ("bundle_pids", "etime_s", "new_bundle_pid"):
        parcalar.append(re.search(r"^%s\(\) \{\n.*?^\}\n" % ad, s,
                                  re.M | re.S).group(0))
    return "\n".join(parcalar)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS ps biçimi")
def test_dogrulama_open_oncesi_ve_eski_sureci_yeni_saymaz(tmp_path):
    """Doğrulama kuralı tek başına: hedef paketten çalışan ama 'open'
    ÖNCESİ listede olan ya da 'open'dan önce başlamış süreç yeni sayılmaz."""
    hedef = tmp_path / "Applications" / "HRMA.app"
    exe = hedef / "Contents" / "MacOS" / "HRMA"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/bash\nwhile :; do sleep 1; done\n")
    exe.chmod(0o755)
    islev = tmp_path / "islev.sh"
    islev.write_text(_dogrulama_islevleri())
    eski = subprocess.Popen([str(exe)], start_new_session=True)
    try:
        # etime saniye çözünürlüklü: 'open'dan ≥ 4 sn önce başlamış olsun
        time.sleep(4)

        def koş(before, open_t):
            r = subprocess.run(
                ["/bin/bash", "-c",
                 'source "$1"; BEFORE="$2"; OPEN_T="$3"; new_bundle_pid',
                 "x", str(islev), before, str(open_t)],
                env=dict(os.environ, TARGET=str(hedef)), capture_output=True,
                text=True)
            return r.stdout.split()

        simdi = int(time.time())
        # İki kanıt AYRI AYRI sınanır (biri bozulursa bekçi kırmızı olsun):
        # (a) 'open' öncesi listede olan süreç, başlama zamanı uysa bile
        #     (open 10 sn önce sayıldı) yeni sayılmaz,
        assert koş(" %d " % eski.pid, simdi - 10) == []
        # (b) listede olmayan ama 'open'dan önce başlamış süreç yeni sayılmaz.
        assert koş(" ", simdi) == []
        yeni = subprocess.Popen([str(exe)], start_new_session=True)
        try:
            time.sleep(0.3)
            assert koş(" %d " % eski.pid, simdi) == [str(yeni.pid)]
        finally:
            yeni.kill()
            yeni.wait()
    finally:
        eski.kill()
        eski.wait()


# ---------------------------------------------------------------------------
# Kalem 5 — dil: bildirim ve bekleme penceresi kullanıcının dilinde
# ---------------------------------------------------------------------------

@pytest.fixture
def _dil_sifirla():
    from hrma.utils import self_install as si
    si.set_ui_language(None)
    yield
    si.set_ui_language(None)


@pytest.mark.parametrize("govde,beklenen", [
    ({"json": {"lang": "tr"}}, "tr"),
    ({"json": {"lang": "en"}}, "en"),
    ({"json": {}}, None),
    ({"json": {"lang": ""}}, None),
    ({}, None),                                   # eski arayüz: gövdesiz
])
def test_install_ucu_dili_alir(govde, beklenen, _dil_sifirla):
    from hrma.app import app
    from hrma.utils import self_install as si
    si.set_ui_language("en" if beklenen is None else None)   # eski değer kalmasın
    r = app.test_client().post("/api/update/install", **govde)
    assert r.status_code == 200
    assert r.get_json()["started"] is False      # indirme yok: kurulum yok
    assert si._ui_lang == beklenen


@pytest.mark.parametrize("deger", ["de", ["tr"], {"a": 1}, "tr; rm -rf /"])
def test_install_ucu_liste_disi_dili_adiyla_reddeder(deger, _dil_sifirla):
    """Liste dışı dil DEĞER kapısında 400 (input_not_accepted); kurulum
    başlamaz, dil değişmez, 500 yok."""
    from hrma.app import app
    from hrma.utils import self_install as si
    si.set_ui_language("tr")
    r = app.test_client().post("/api/update/install", json={"lang": deger})
    assert r.status_code == 400
    j = r.get_json()
    assert j["started"] is False and j["error_code"] == "input_not_accepted"
    assert "'lang' must be one of: en, tr" in j["error"]
    assert si._ui_lang == "tr"


def test_install_ucu_bozuk_json_govdesi_400_kurulum_baslamaz(_dil_sifirla):
    """JSON taşıyıcısıyla gelen dizi gövde, gövde kapısında 400 alır (500
    yok); uç hiç çalışmaz, dil değişmez."""
    from hrma.app import app
    from hrma.utils import self_install as si
    si.set_ui_language("tr")
    r = app.test_client().post("/api/update/install", data=b"[1,2]",
                               headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert si._ui_lang == "tr"


def test_launch_helper_dili_ve_kilidi_betige_aktarir(tmp_path, monkeypatch,
                                                     _dil_sifirla):
    from hrma.utils import self_install as si
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Documents").mkdir()
    monkeypatch.setattr(si, "_helper_dir", lambda plan: str(tmp_path))
    cagri = {}
    monkeypatch.setattr(si.subprocess, "Popen",
                        lambda arg, **kw: cagri.setdefault("arg", arg))
    si.set_ui_language("tr")
    res = si.launch_helper({"platform": "darwin",
                            "target": "/Applications/HRMA.app"},
                           "/x/HRMA.dmg", pid=4242)
    assert res["launched"] is True
    arg = cagri["arg"]
    assert arg[2:] == ["4242", "/x/HRMA.dmg", "/Applications/HRMA.app",
                       si.update_log_path(), si.update_lock_path()]
    with open(arg[1], encoding="ascii") as f:
        betik = f.read()
    assert "UI_LANG=$'tr'" in betik
    assert "MSG_START=$'G\\xc3\\xbcncelleme kuruluyor." in betik


def test_arayuz_install_istegine_dili_koyar():
    yol = os.path.join(KOK, "hrma", "static", "js", "update_check.js")
    with open(yol, encoding="utf-8") as f:
        js = f.read()
    bas = js.index("function startInstall(")
    govde = js[bas:js.index(".then(", bas)]
    assert "fetch('/api/update/install'" in govde
    assert "window.I18N.lang" in govde
    assert "JSON.stringify(govde)" in govde
    assert "'Content-Type': 'application/json'" in govde
    assert re.search(r"dil === 'tr' \|\| dil === 'en'", govde)


def test_bekleme_gorunumu_dil_bilinmiyorsa_iki_dil():
    from hrma.utils import self_install as si
    k = {"pid": 1, "started": 1000, "step": "mounting", "phase": "wait",
         "done_kb": None, "total_kb": None, "lang": None, "target": "/x"}
    v = si.update_waiting_view(k, now=1010)
    assert v["lang"] is None
    assert v["heading"] == "Updating HRMA\nHRMA güncelleniyor"
    assert v["step"] == ("Opening the installer image\n"
                         "Kurulum görüntüsü açılıyor")
    assert v["title"] == "HRMA — update in progress / HRMA — güncelleme sürüyor"
    v = si.update_waiting_view(dict(k, lang="tr"), now=1010)
    assert v["heading"] == "HRMA güncelleniyor" and v["lang"] == "tr"
    assert "Updating" not in json_dump(v)


def json_dump(v):
    import json
    return json.dumps(v, ensure_ascii=False)


def test_metinler_iki_dilde_eksiksiz_ve_yasakli_ifade_yok():
    from hrma.utils import self_install as si
    assert set(si.UPDATE_TEXTS["en"]) == set(si.UPDATE_TEXTS["tr"])
    tum = json_dump(si.UPDATE_TEXTS).lower()
    for yasak in ("uydurma", "invented", "http 4", "/api/", "lock", "kilit"):
        assert yasak not in tum, yasak
    tr = json_dump(si.UPDATE_TEXTS["tr"])
    for harf in "çğıöşü":
        assert harf in tr                       # ASCII'ye kaçılmadı


@MAC_E2E
@pytest.mark.parametrize("dil", ["tr", "en", None])
def test_e2e_bildirimler_kullanicinin_dilinde(tmp_path, dil):
    from hrma.utils import self_install as si
    g = senaryo(str(tmp_path), _betik(lang=dil))
    assert g["rc"] == 0, g["log"]
    bild = g["osascript"]
    for anahtar in ("notify.start", "notify.done"):
        if dil:
            assert si.UPDATE_TEXTS[dil][anahtar] in bild, (anahtar, bild)
        else:
            assert si.UPDATE_TEXTS["en"][anahtar] in bild
            assert si.UPDATE_TEXTS["tr"][anahtar] in bild
    if dil == "en":
        assert "Güncelleme" not in bild
    kilit_dili = set(re.findall(r"\nlang=(\w*)\n",
                                "".join(g["kilit_goruntuleri"])))
    assert kilit_dili == {dil or ""}


# ---------------------------------------------------------------------------
# Açılış entegrasyonu (pencere AÇILMAZ: webview test modülüyle değiştirilir)
# ---------------------------------------------------------------------------

def _launcher_yukle():
    sys.path.insert(0, PAKETLEME)
    try:
        import launcher
    finally:
        sys.path.remove(PAKETLEME)
    return launcher


@pytest.mark.skipif(sys.platform != "darwin", reason="kilit yalnız macOS")
def test_bekleme_penceresi_gercek_kilidi_basar_asama_degisince_kapanir(
        tmp_path, monkeypatch):
    import threading
    import types
    launcher = _launcher_yukle()
    from hrma.utils import self_install as si
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Documents").mkdir()
    monkeypatch.delenv("HRMA_NO_WINDOW", raising=False)
    betik = tmp_path / ("%s.sh" % si.HELPER_SCRIPT_STEM)
    betik.write_text("sleep 30\n")
    yardimci = subprocess.Popen(["/bin/bash", str(betik)])
    kayit = {"js": [], "destroy": 0}
    try:
        _kilit_yaz(si.update_lock_path(), yardimci.pid, int(time.time()) - 5,
                   step="copying", done="1024", total="4096", lang="tr")

        class Pencere:
            def evaluate_js(self, kod):
                kayit["js"].append(kod)

            def destroy(self):
                kayit["destroy"] += 1

        sahte = types.ModuleType("webview")

        def create_window(baslik, html=None, **kw):
            kayit["baslik"], kayit["html"], kayit["kw"] = baslik, html, kw
            return Pencere()

        def start(func=None, *a, **kw):
            def asamayi_degistir():
                time.sleep(0.6)
                _kilit_yaz(si.update_lock_path(), yardimci.pid,
                           int(time.time()) - 5, step="closing",
                           phase="closing", lang="tr")
            threading.Thread(target=asamayi_degistir).start()
            func()

        sahte.create_window, sahte.start = create_window, start
        monkeypatch.setitem(sys.modules, "webview", sahte)
        monkeypatch.setattr(launcher, "_macos_app_identity", lambda v: None)
        launcher._guncelleme_bekleme_penceresi()
    finally:
        yardimci.kill()
        yardimci.wait()
    assert kayit["baslik"] == "HRMA — güncelleme sürüyor"
    assert kayit["kw"]["height"] == launcher.BEKLEME_YUKSEKLIK_TEK_DIL
    assert '"Kopyalanan: 1 MB / 4 MB"' in kayit["html"]
    assert kayit["js"] and "Yeni sürüm kopyalanıyor" in kayit["js"][0]
    assert kayit["destroy"] == 1


@pytest.mark.skipif(sys.platform != "darwin", reason="kilit yalnız macOS")
@pytest.mark.parametrize("karar,pencere", [("exit", 0), ("wait", 1)])
def test_main_kilitte_sunucu_baslatmaz(karar, pencere, monkeypatch):
    launcher = _launcher_yukle()
    cagri = {"pencere": 0}

    class Cikis(Exception):
        pass

    monkeypatch.setattr(launcher, "_setup_console", lambda: None)
    monkeypatch.setattr(launcher, "_setup_paths", lambda: None)
    monkeypatch.setattr(launcher, "_guncelleme_kilidi_karari", lambda: karar)
    monkeypatch.setattr(launcher, "_guncelleme_bekleme_penceresi",
                        lambda: cagri.__setitem__("pencere",
                                                  cagri["pencere"] + 1))
    monkeypatch.setattr(launcher, "_pick_port",
                        lambda: pytest.fail("güncelleme sürerken port seçildi"))
    monkeypatch.setattr(launcher.os, "_exit",
                        lambda kod: (_ for _ in ()).throw(Cikis(kod)))
    with pytest.raises(Cikis):
        launcher.main()
    assert cagri["pencere"] == pencere
