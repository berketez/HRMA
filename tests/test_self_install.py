"""Sessiz otomatik kurulum (self_install) testleri.

Gerçek kurulum YAPILMAZ: hedef tespiti sahte dizin ağaçlarıyla, yardımcı
betikler içerik asertleriyle, uç durumlar monkeypatch ile doğrulanır.
"""

import os
import shutil
import pytest

from hrma.utils import self_install as si
from hrma.utils import update_checker as uc


# ---------------- macOS hedef tespiti ----------------

def _sahte_mac_bundle(root, ad="HRMA.app"):
    app = root / ad
    (app / "Contents" / "MacOS").mkdir(parents=True)
    hrma_pkg = app / "Contents" / "Resources" / "app" / "hrma"
    hrma_pkg.mkdir(parents=True)
    return app, hrma_pkg


def test_find_mac_bundle_bulur(tmp_path):
    app, pkg = _sahte_mac_bundle(tmp_path)
    assert si.find_mac_bundle(start_path=str(pkg)) == str(app)


def test_find_mac_bundle_kaynak_kodda_none(tmp_path):
    d = tmp_path / "repo" / "hrma"
    d.mkdir(parents=True)
    assert si.find_mac_bundle(start_path=str(d)) is None


def test_find_mac_bundle_contents_macos_sart(tmp_path):
    # .app uzantılı ama gerçek paket olmayan dizin kabul edilmez
    sahte = tmp_path / "Sahte.app" / "Resources" / "app" / "hrma"
    sahte.mkdir(parents=True)
    assert si.find_mac_bundle(start_path=str(sahte)) is None


# ---------------- Windows hedef tespiti ----------------

def _sahte_win_kurulum(root):
    inst = root / "HRMA"
    (inst / "python").mkdir(parents=True)
    (inst / "python" / "pythonw.exe").write_bytes(b"")
    (inst / "app" / "hrma").mkdir(parents=True)
    (inst / "app" / "launcher.py").write_text("", encoding="utf-8")
    (inst / "uninstall.exe").write_bytes(b"")
    return inst, inst / "app" / "hrma"


def test_find_win_install_dir_bulur(tmp_path):
    inst, pkg = _sahte_win_kurulum(tmp_path)
    assert si.find_win_install_dir(start_path=str(pkg)) == str(inst)


def test_find_win_install_dir_uninstall_yoksa_none(tmp_path):
    inst, pkg = _sahte_win_kurulum(tmp_path)
    os.remove(str(inst / "uninstall.exe"))
    assert si.find_win_install_dir(start_path=str(pkg)) is None


# ---------------- plan_install kararları ----------------

def test_plan_mac_auto(tmp_path):
    app, pkg = _sahte_mac_bundle(tmp_path)
    dmg = tmp_path / "HRMA-2.9.9.dmg"
    dmg.write_bytes(b"x" * 1024)
    plan = si.plan_install(str(dmg), platform="darwin", start_path=str(pkg),
                           installer_size=1024)
    assert plan["mode"] == "auto"
    assert plan["target"] == str(app)


def test_plan_mac_kaynak_kod_manual(tmp_path):
    d = tmp_path / "repo" / "hrma"
    d.mkdir(parents=True)
    dmg = tmp_path / "a.dmg"
    dmg.write_bytes(b"x")
    plan = si.plan_install(str(dmg), platform="darwin", start_path=str(d))
    assert plan["mode"] == "manual"
    assert "bundle" in plan["reason"]


def test_plan_mac_yanlis_uzanti_manual(tmp_path):
    app, pkg = _sahte_mac_bundle(tmp_path)
    exe = tmp_path / "Setup.exe"
    exe.write_bytes(b"x")
    assert si.plan_install(str(exe), platform="darwin",
                           start_path=str(pkg))["mode"] == "manual"


def test_plan_mac_translocation_manual(tmp_path, monkeypatch):
    app, pkg = _sahte_mac_bundle(tmp_path)
    dmg = tmp_path / "a.dmg"
    dmg.write_bytes(b"x")
    # Gatekeeper kopyasından çalışma: gerçek yol AppTranslocation altında
    monkeypatch.setattr(os.path, "realpath",
                        lambda p: "/private/var/AppTranslocation/X/d/HRMA.app")
    plan = si.plan_install(str(dmg), platform="darwin", start_path=str(pkg))
    assert plan["mode"] == "manual"
    assert "translocated" in plan["reason"]


def test_plan_mac_dmg_icinden_calisma_manual(tmp_path, monkeypatch):
    app, pkg = _sahte_mac_bundle(tmp_path)
    dmg = tmp_path / "a.dmg"
    dmg.write_bytes(b"x")
    monkeypatch.setattr(os.path, "realpath", lambda p: "/Volumes/HRMA/HRMA.app")
    assert si.plan_install(str(dmg), platform="darwin",
                           start_path=str(pkg))["mode"] == "manual"


def test_plan_mac_disk_alani_yetersiz_manual(tmp_path, monkeypatch):
    app, pkg = _sahte_mac_bundle(tmp_path)
    dmg = tmp_path / "a.dmg"
    dmg.write_bytes(b"x" * 100)
    Usage = type("Usage", (), {})
    fake = Usage()
    fake.free = 10  # bariz yetersiz
    monkeypatch.setattr(shutil, "disk_usage", lambda p: fake)
    plan = si.plan_install(str(dmg), platform="darwin", start_path=str(pkg),
                           installer_size=100)
    assert plan["mode"] == "manual"
    assert "disk space" in plan["reason"]


def test_plan_win_auto(tmp_path):
    inst, pkg = _sahte_win_kurulum(tmp_path)
    exe = tmp_path / "HRMA-Setup-2.9.9.exe"
    exe.write_bytes(b"x")
    plan = si.plan_install(str(exe), platform="win32", start_path=str(pkg))
    assert plan["mode"] == "auto"
    assert plan["target"] == str(inst)


def test_plan_win_kaynak_kod_manual(tmp_path):
    d = tmp_path / "repo" / "hrma"
    d.mkdir(parents=True)
    exe = tmp_path / "Setup.exe"
    exe.write_bytes(b"x")
    assert si.plan_install(str(exe), platform="win32",
                           start_path=str(d))["mode"] == "manual"


def test_plan_win_cmd_guvensiz_karakter_manual(tmp_path):
    # cmd.exe'ye gömülemeyecek karakterli yol → otomatik moda girilmez
    kok = tmp_path / "a&b"
    kok.mkdir()
    inst, pkg = _sahte_win_kurulum(kok)
    exe = tmp_path / "Setup.exe"
    exe.write_bytes(b"x")
    plan = si.plan_install(str(exe), platform="win32", start_path=str(pkg))
    assert plan["mode"] == "manual"
    assert "unsafe" in plan["reason"]


def test_plan_desteklenmeyen_platform_manual():
    assert si.plan_install("/tmp/a.dmg", platform="linux")["mode"] == "manual"


# ---------------- yardımcı betik içerikleri ----------------

def test_mac_helper_kritik_adimlar():
    s = si.MAC_HELPER
    # DMG bağlama + kopyalama + atomik takas + geri alma + doğrulama zinciri
    assert "hdiutil attach -nobrowse -noverify" in s
    assert "ditto" in s
    assert 'mv "$TARGET" "$OLD"' in s
    assert 'mv "$STAGING" "$TARGET"' in s
    assert 'mv "$OLD" "$TARGET"' in s          # başarısızlıkta geri yükleme
    assert "Contents/MacOS" in s               # staging bütünlük kontrolü
    assert "xattr -dr com.apple.quarantine" in s
    assert 'open "$TARGET"' in s
    assert 'open "$DMG"' in s                  # her hata yolunda manuel akış
    # Eski sürüm, yeni sürümün AÇILDIĞI doğrulanmadan silinmemeli
    assert s.index('rm -rf "$OLD"') > s.index('open "$TARGET"')
    # ASCII (batch/bash betikleri Türkçe karakter içermez)
    s.encode("ascii")


def test_win_helper_icerigi():
    bat = si.build_win_helper(1234, r"C:\Users\u\Downloads\Setup.exe",
                              r"C:\Users\u\AppData\Local\HRMA")
    # NSIS sessiz kurulum: /D= son parametre ve TIRNAKSIZ; start kullanılmaz
    #
    # Faz 5 / H5-7 düzeltmesi — ÖLÜ ASSERTION: bu satır eskiden
    #     assert '"C:\\Users\\u\\Downloads\\Setup.exe" /S '
    # yazıyordu; ``in bat`` unutulmuştu, yani boş olmayan bir dize her zaman
    # doğru sayılıyordu (ölçüm: bool(dize) is True). Dize bugün gerçekten
    # ``bat`` içinde var, o yüzden gizlenen aktif bir kusur yoktu; fakat exe
    # yolunun TIRNAKLANMASINI başka hiçbir assertion sınamıyordu — boşluklu
    # bir indirme yolunda tırnağın kaybolması sessizce geçerdi.
    assert '"C:\\Users\\u\\Downloads\\Setup.exe" /S ' in bat
    satirlar = [l for l in bat.splitlines() if "/S /D=" in l]
    assert len(satirlar) == 1
    assert satirlar[0].rstrip().endswith(r"/D=C:\Users\u\AppData\Local\HRMA")
    assert '/D="' not in bat
    assert "Wait-Process -Id 1234" in bat
    assert r"pythonw.exe" in bat and "launcher.py" in bat
    # Sessiz kurulum başarısızsa normal kurucuya düşülür
    assert "if not exist" in bat
    bat.encode("ascii")


def test_win_helper_bosluklu_yolu_tirnaklar():
    """Boşluklu indirme yolu tırnak içinde kalmalı; /D= yine tırnaksız.

    Ölü assertion'ın (yukarıdaki H5-7 notu) örttüğü GERÇEK boşluk buydu:
    exe yolunun tırnaklanması hiçbir yerde sınanmıyordu. Windows'ta indirme
    dizini neredeyse her zaman boşluk içerir (``C:\\Users\\Ad Soyad\\...``);
    tırnak düşerse cmd.exe yolu iki argümana böler ve sessiz kurulum
    çalışmaz. NSIS kuralı gereği ``/D=`` argümanı tam tersine TIRNAKSIZ
    olmak zorundadır — ikisi aynı satırda birlikte doğrulanır.
    """
    bat = si.build_win_helper(99, r"C:\Users\ad soyad\Downloads\HRMA Setup.exe",
                              r"C:\Program Files\HRMA")
    satirlar = [l for l in bat.splitlines() if "/S /D=" in l]
    assert len(satirlar) == 1, satirlar
    satir = satirlar[0].rstrip()
    assert '"C:\\Users\\ad soyad\\Downloads\\HRMA Setup.exe" /S ' in satir, (
        f'boşluklu exe yolu tırnaksız kalmış: {satir!r}')
    assert satir.endswith(r"/D=C:\Program Files\HRMA"), satir
    assert '/D="' not in bat, 'NSIS /D= tırnaklanamaz'
    bat.encode("ascii")


def test_helper_dosyasi_yazilir(tmp_path, monkeypatch):
    monkeypatch.setattr(si, "_helper_dir", lambda plan: str(tmp_path))
    p = si._write_helper({"platform": "darwin"}, si.MAC_HELPER, ".sh")
    assert os.path.isfile(p) and p.endswith(".sh")
    icerik = open(p, encoding="ascii").read()
    assert icerik.startswith("#!/bin/bash")


# ---------------- start_install / endpoint ----------------

@pytest.fixture(autouse=True)
def _temiz_download_state():
    with uc._download_lock:
        uc._download.update(state="idle", pct=0, path="", error="")
    yield
    with uc._download_lock:
        uc._download.update(state="idle", pct=0, path="", error="")


def test_install_indirme_yokken_baslamaz():
    from hrma.app import app
    r = app.test_client().post("/api/update/install")
    assert r.status_code == 200
    data = r.get_json()
    assert data["started"] is False
    assert "no downloaded installer" in data["reason"]


def test_install_dosya_silinmisse_baslamaz(tmp_path):
    with uc._download_lock:
        uc._download.update(state="done", pct=100,
                            path=str(tmp_path / "yok.dmg"))
    assert uc.start_install()["started"] is False


def test_install_kaynak_kod_ortaminda_manuel_moda_duser(tmp_path, monkeypatch):
    # Depodan çalışırken plan "manual" döner → kurulum dosyası açılır,
    # uygulama KAPANMAZ (schedule_app_exit çağrılmaz).
    dmg = tmp_path / "HRMA-9.9.9.dmg"
    dmg.write_bytes(b"x" * 64)
    with uc._download_lock:
        uc._download.update(state="done", pct=100, path=str(dmg))

    acilan = {}
    monkeypatch.setattr(uc, "_open_installer",
                        lambda p: acilan.setdefault("path", p))
    from hrma.utils import self_install
    monkeypatch.setattr(self_install, "schedule_app_exit",
                        lambda *a, **k: pytest.fail(
                            "manuel modda uygulama kapatılmamalı"))

    res = uc.start_install()
    assert res["started"] is True
    assert res["mode"] == "manual"
    assert acilan["path"] == str(dmg)


def test_install_auto_modda_helper_ve_kapanis(tmp_path, monkeypatch):
    dmg = tmp_path / "HRMA-9.9.9.dmg"
    dmg.write_bytes(b"x" * 64)
    with uc._download_lock:
        uc._download.update(state="done", pct=100, path=str(dmg))

    from hrma.utils import self_install
    cagrilar = {}
    monkeypatch.setattr(self_install, "plan_install",
                        lambda *a, **k: {"mode": "auto", "platform": "darwin",
                                         "target": "/Applications/HRMA.app"})
    def sahte_helper(plan, path, pid=None):
        cagrilar["helper"] = (plan, path)
        return {"launched": True, "log": "/tmp/log"}
    monkeypatch.setattr(self_install, "launch_helper", sahte_helper)
    monkeypatch.setattr(self_install, "schedule_app_exit",
                        lambda *a, **k: cagrilar.setdefault("exit", True))
    monkeypatch.setattr(uc, "_open_installer",
                        lambda p: pytest.fail("auto modda installer açılmamalı"))

    res = uc.start_install()
    assert res["started"] is True and res["mode"] == "auto"
    assert cagrilar["helper"][1] == str(dmg)
    assert cagrilar.get("exit") is True


def test_install_helper_baslatilamazsa_manuel_yedek(tmp_path, monkeypatch):
    dmg = tmp_path / "HRMA-9.9.9.dmg"
    dmg.write_bytes(b"x" * 64)
    with uc._download_lock:
        uc._download.update(state="done", pct=100, path=str(dmg))

    from hrma.utils import self_install
    monkeypatch.setattr(self_install, "plan_install",
                        lambda *a, **k: {"mode": "auto", "platform": "darwin",
                                         "target": "/Applications/HRMA.app"})
    monkeypatch.setattr(self_install, "launch_helper",
                        lambda *a, **k: {"launched": False, "error": "boom"})
    monkeypatch.setattr(self_install, "schedule_app_exit",
                        lambda *a, **k: pytest.fail(
                            "helper başlamadıysa uygulama kapatılmamalı"))
    acilan = {}
    monkeypatch.setattr(uc, "_open_installer",
                        lambda p: acilan.setdefault("path", p))

    res = uc.start_install()
    assert res["started"] is True and res["mode"] == "manual"
    assert acilan["path"] == str(dmg)
