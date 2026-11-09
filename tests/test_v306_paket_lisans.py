"""3.0.6 CI-SÜREÇ kalem 1 (S1 lisans) — paketler HRMA LICENSE'ını ve üçüncü
taraf lisans bildirimlerini taşır.

Ölçülen kusur: yayınlanan v3.0.5 macOS paketi (köken 0a138ff6a) açıldı;
``Contents/Resources/app`` altında ``LICENSE`` YOK. Paket RocketCEA 1.2.1
(GPLv3) ve lisans dosyası taşımayan Open CASCADE (LGPL-2.1 + istisna),
FreeImage, LibRaw, FreeType yerel kütüphanelerini taşıyor (kanıt:
``docs/scofield/raw/OH/V306/ci-surec/lisans_envanteri_v305_mac.json``).
Kaynak ağaç 3.0.6'dan itibaren GPL-3.0-or-later.

Yerelde TAM PAKET DERLENMEZ; bekçiler betik/spec düzeyindedir:
- ``packaging/lisans_paketle.py`` sahte libs/app ağacında GERÇEKTEN koşar
  (dosyaları koyar; RocketCEA lisanssızsa, bildirimsiz copyleft dağıtım
  varsa ya da LICENSE GPLv3 değilse paketi DURDURUR);
- iki derleme betiği onu libs/ ve app/ hazır olduktan sonra, imza ve
  ön-derlemeden önce çağırır;
- yayın kapısının ``manifest_denetle`` işlevi (betikten çıkarılır) LICENSE
  ve bildirim yoksa KALDI der; ``release.yml`` gerçek paketi aynı ölçütle
  denetler.
Gerçek paket aday CI'da (release.yml) ve yayın kapısı 8/10'da doğrulanır.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DEPO = Path(__file__).resolve().parents[1]
PAKET = DEPO / "packaging"
PAKETLEYICI = PAKET / "lisans_paketle.py"
LISANS_DIZINI = PAKET / "licenses"
BILDIRIM = LISANS_DIZINI / "THIRD_PARTY_NOTICES.txt"
MAC_BETIK = PAKET / "build_mac_app.sh"
WIN_BETIK = PAKET / "build_win_payload.sh"
NSI = PAKET / "hrma.nsi"
KAPI = PAKET / "release_gate.sh"
RELEASE_YML = DEPO / ".github" / "workflows" / "release.yml"


def _kod(metin):
    """Kabuk yorumlarını atar — açıklama metni kod sayılmasın."""
    return "\n".join(s for s in metin.splitlines()
                     if not s.lstrip().startswith(("#", ";")))


def _dist_info(libs, ad, surum, lisans, lisans_dosyasi=None, siniflandirici=None):
    di = libs / f"{ad}-{surum}.dist-info"
    di.mkdir(parents=True)
    satirlar = ["Metadata-Version: 2.1", f"Name: {ad}", f"Version: {surum}"]
    if lisans:
        satirlar.append(f"License: {lisans}")
    if siniflandirici:
        satirlar.append(f"Classifier: {siniflandirici}")
    (di / "METADATA").write_text("\n".join(satirlar) + "\n\ngövde\n", encoding="utf-8")
    if lisans_dosyasi:
        hedef = di / lisans_dosyasi
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text("lisans metni\n", encoding="utf-8")
    return di


def _paket_agaci(tmp_path, rocketcea_lisansli=True, ek=None):
    """Gerçek pakete benzeyen libs/ + app/ (metaveri biçimi v3.0.5'ten)."""
    libs = tmp_path / "libs"
    app = tmp_path / "app"
    app.mkdir(parents=True)
    _dist_info(libs, "rocketcea", "1.2.1", "GNU GENERAL PUBLIC LICENSE",
               "LICENSE.txt" if rocketcea_lisansli else None)
    _dist_info(libs, "certifi", "2026.10.23", "MPL-2.0", "licenses/LICENSE",
               "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)")
    _dist_info(libs, "flask", "3.1.0", None, "licenses/LICENSE.txt",
               "License :: OSI Approved :: BSD License")
    _dist_info(libs, "coolprop", "6.8.0", None)  # v3.0.5'te lisans dosyasız
    for argumanlar in (ek or ()):
        _dist_info(libs, *argumanlar)
    return libs, app


def _paketle(kaynak, app, libs, paketleyici=PAKETLEYICI):
    return subprocess.run(
        [sys.executable, str(paketleyici), "--kaynak", str(kaynak),
         "--app", str(app), "--libs", str(libs)],
        capture_output=True, text=True, timeout=120)


# ---------------------------------------------------------------------------
# 1) lisans_paketle.py — davranış
# ---------------------------------------------------------------------------

def test_paketleyici_lisans_ve_bildirimleri_koyar(tmp_path):
    libs, app = _paket_agaci(tmp_path)
    p = _paketle(DEPO, app, libs)
    assert p.returncode == 0, p.stdout + p.stderr

    assert (app / "LICENSE").read_bytes() == (DEPO / "LICENSE").read_bytes()
    for kaynak in LISANS_DIZINI.iterdir():
        assert (app / "licenses" / kaynak.name).read_bytes() == kaynak.read_bytes()
    liste = (app / "licenses" / "PYTHON_PACKAGES.txt").read_text(encoding="utf-8")
    assert re.search(r"^rocketcea 1\.2\.1 — GNU GENERAL PUBLIC LICENSE\s+\[copyleft\]$",
                     liste, re.M), liste
    assert "rocketcea-1.2.1.dist-info/LICENSE.txt" in liste
    assert "certifi-2026.10.23.dist-info/licenses/LICENSE" in liste
    # Lisans dosyası taşımayan dağıtım gizlenmez, adıyla söylenir.
    assert re.search(r"^coolprop 6\.8\.0 — .*\n\s+\(the distribution ships no licence file\)",
                     liste, re.M), liste


def test_paketleyici_rocketcea_lisanssizsa_durur(tmp_path):
    libs, app = _paket_agaci(tmp_path, rocketcea_lisansli=False)
    p = _paketle(DEPO, app, libs)
    assert p.returncode == 1, p.stdout
    assert "rocketcea" in p.stdout and not (app / "LICENSE").exists()


def test_paketleyici_rocketcea_yoksa_durur(tmp_path):
    libs, app = _paket_agaci(tmp_path)
    shutil.rmtree(libs / "rocketcea-1.2.1.dist-info")
    p = _paketle(DEPO, app, libs)
    assert p.returncode == 1 and "rocketcea" in p.stdout


def test_paketleyici_bildirimsiz_copyleft_dagitimda_durur(tmp_path):
    """Yeni bir GPL/LGPL bağımlılık bildirime girmeden pakete giremez."""
    libs, app = _paket_agaci(tmp_path, ek=[
        ("gizli-gpl-paket", "0.1", None, "LICENSE",
         "License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)")])
    p = _paketle(DEPO, app, libs)
    assert p.returncode == 1, p.stdout
    assert "gizli-gpl-paket" in p.stdout and "beyan" in p.stdout


def test_paketleyici_gpl3_olmayan_lisansi_reddeder(tmp_path):
    """Kaynak ağaçta LICENSE GPLv3 değilse (ör. eski MIT) paket ÜRETİLMEZ."""
    kaynak = tmp_path / "kaynak"
    kaynak.mkdir()
    (kaynak / "LICENSE").write_text("MIT License\n\nCopyright (c) ...\n", encoding="utf-8")
    libs, app = _paket_agaci(tmp_path)
    p = _paketle(kaynak, app, libs)
    assert p.returncode == 1 and "GPL" in p.stdout
    assert not (app / "LICENSE").exists()


def test_bildirim_ile_lisans_metinleri_tutarli():
    """Bildirimin andığı her metin var; dizindeki her metin bildirimde anılıyor."""
    metin = BILDIRIM.read_text(encoding="utf-8")
    anilan = set(re.findall(r"licenses/([A-Za-z0-9_.\-]+\.txt)", metin))
    anilan.discard("PYTHON_PACKAGES.txt")  # derlemede üretilir
    mevcut = {p.name for p in LISANS_DIZINI.iterdir() if p.is_file()}
    mevcut.discard("THIRD_PARTY_NOTICES.txt")
    assert anilan == mevcut, (anilan - mevcut, mevcut - anilan)
    assert re.search(r"^Distribution: rocketcea$", metin, re.M)
    assert "GPL-3.0-or-later" in metin
    # Lisans metinleri boş yer tutucu değil (en kısası OCCT istisnası ~660 B).
    for p in LISANS_DIZINI.iterdir():
        assert p.stat().st_size > 500, p.name


# ---------------------------------------------------------------------------
# 2) Derleme betikleri ve kurucu — spec düzeyi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("betik, app_kok, libs_kok, sonraki", [
    (MAC_BETIK, '"$RES/app"', '"$RES/libs"', "codesign --force"),
    (WIN_BETIK, '"$W/app"', '"$W/libs"', "-m compileall"),
])
def test_derleme_betigi_paketleyiciyi_dogru_yerde_cagirir(betik, app_kok, libs_kok, sonraki):
    kod = _kod(betik.read_text(encoding="utf-8"))
    satirlar = kod.splitlines()
    cagri = [i for i, s in enumerate(satirlar) if "lisans_paketle.py" in s]
    assert len(cagri) == 1, "%s lisans_paketle.py'yi çağırmıyor" % betik.name
    satir = satirlar[cagri[0]]
    assert "--app " + app_kok in satir and "--libs " + libs_kok in satir, satir
    assert '--kaynak "$SRC"' in satir, satir
    # Sessiz geçiş yok: betik set -e ile koşar, çağrı `|| true` ile yutulmaz.
    assert "set -euo pipefail" in kod and "||" not in satir
    # Sıra: rocketcea libs'e girdikten ve app/ kopyalandıktan SONRA,
    # imza / ön-derlemeden ÖNCE (yoksa dist-info taranamaz ya da mühür bozulur).
    rocketcea = max(i for i, s in enumerate(satirlar) if "rocketcea" in s)
    app_kopya = max(i for i, s in enumerate(satirlar) if '"$SRC/hrma"' in s)
    son = min(i for i, s in enumerate(satirlar) if sonraki in s)
    assert rocketcea < cagri[0] and app_kopya < cagri[0] < son, (
        rocketcea, app_kopya, cagri[0], son)


def test_kurucu_app_agacini_tasir_ve_kaldirirken_siler():
    """Windows: LICENSE payload/app altında; kurucu o ağacı $INSTDIR\\app'e açar."""
    kod = _kod(NSI.read_text(encoding="utf-8"))
    assert 'File /r "win/payload/app"' in kod
    assert 'RMDir /r "$INSTDIR\\app"' in kod


def test_dmg_paketi_app_agacini_tasir():
    """macOS: DMG, LICENSE'ı içeren HRMA.app'in kopyasını taşır."""
    kod = _kod((PAKET / "build_dmg.sh").read_text(encoding="utf-8"))
    assert 'cp -R "$B/mac/build.noindex/HRMA.app" "$STAGE/"' in kod


# ---------------------------------------------------------------------------
# 3) Yayın kapısı 8/10 + release.yml — gerçek paketi denetleyen ölçüt
# ---------------------------------------------------------------------------

def _bash_fonksiyonu(metin, ad):
    satirlar = metin.splitlines()
    bas = next(i for i, s in enumerate(satirlar)
               if re.match(r"^%s\s*\(\)\s*\{" % re.escape(ad), s))
    son = next(j for j in range(bas + 1, len(satirlar)) if satirlar[j] == "}")
    return "\n".join(satirlar[bas:son + 1])


def _manifest(kok):
    govde = _bash_fonksiyonu(KAPI.read_text(encoding="utf-8"), "manifest_denetle")
    betik = "\n".join([
        "set -uo pipefail", "REPO_ORNEK=1", "REPO_DATA=1",
        'basarili() { echo "GECTI|$1"; }', 'basarisiz() { echo "KALDI|$1"; }',
        'atlandi() { echo "ATLANDI|$1"; }', govde,
        'manifest_denetle "%s" "sahte paket"' % kok])
    p = subprocess.run(["bash", "-c", betik], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


def _lisansli_app(tmp_path):
    libs, app = _paket_agaci(tmp_path / "kaynak_agac")
    assert _paketle(DEPO, app, libs).returncode == 0
    kok = tmp_path / "paket"
    shutil.copytree(app, kok / "app")
    return kok


def test_kapi_manifesti_lisansli_paketi_gecirir(tmp_path):
    cikti = _manifest(_lisansli_app(tmp_path))
    assert "GECTI|sahte paket: LICENSE (GNU GPL v3 metni) pakette" in cikti, cikti
    assert "GECTI|sahte paket: üçüncü taraf lisans bildirimi" in cikti, cikti


def test_kapi_manifesti_lisanssiz_paketi_kapatir(tmp_path):
    """v3.0.5 paketinin durumu: app/LICENSE ve app/licenses/ yok."""
    kok = _lisansli_app(tmp_path)
    (kok / "app" / "LICENSE").unlink()
    shutil.rmtree(kok / "app" / "licenses")
    cikti = _manifest(kok)
    assert "KALDI|sahte paket: LICENSE yok" in cikti, cikti
    assert "KALDI|sahte paket: app/licenses/ eksik" in cikti, cikti


def test_kapi_manifesti_mit_lisansli_paketi_kapatir(tmp_path):
    kok = _lisansli_app(tmp_path)
    (kok / "app" / "LICENSE").write_text("MIT License\n" + "x" * 200, encoding="utf-8")
    assert "KALDI|sahte paket: LICENSE yok, boş ya da GNU GPL v3" in _manifest(kok)


def test_release_is_akisi_gercek_paketlerde_lisansi_denetler():
    """Aday CI'daki gerçek DMG ve Windows payload'u aynı ölçütle denetlenir."""
    metin = RELEASE_YML.read_text(encoding="utf-8")
    kod = _kod(metin)
    assert kod.count("*'GNU GENERAL PUBLIC LICENSE'*'Version 3'*)") == 2, (
        "release.yml DMG ve payload adımlarının ikisi de app/LICENSE'ı denetlemeli")
    assert '$MNT/HRMA.app/Contents/Resources/app' in kod
    assert 'LIS_APP="packaging/win/payload/app"' in kod
    assert kod.count("^Distribution: rocketcea") == 2
