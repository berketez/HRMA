"""Otomatik güncelleme denetleyicisi testleri.

Ağa ÇIKILMAZ: GitHub API çağrısı monkeypatch ile sahte yanıtlarla beslenir.
"""

import sys
import pytest

from hrma import __version__
from hrma.utils import update_checker as uc


# ---------------- sürüm ayrıştırma / karşılaştırma ----------------

@pytest.mark.parametrize("text,expected", [
    ("v2.3.0", (2, 3, 0)),
    ("2.3", (2, 3, 0)),
    ("HRMA-2.10.1-beta", (2, 10, 1)),
    ("v10.0.0", (10, 0, 0)),
    ("", (0, 0, 0)),
    (None, (0, 0, 0)),
])
def test_parse_version(text, expected):
    assert uc.parse_version(text) == expected


def test_is_newer_semver_degil_metin_karsilastirmasi():
    # "2.10" > "2.9" — metin karşılaştırması olsaydı yanlış çıkardı
    assert uc.is_newer("v2.10.0", "2.9.0")
    assert not uc.is_newer("v2.9.0", "2.10.0")
    assert not uc.is_newer(__version__, __version__)


# ---------------- platform asset seçimi ----------------

ASSETS = [
    {"name": "HRMA-Kurulum-2.4.0.exe", "browser_download_url": "u1", "size": 1},
    {"name": "HRMA-Kurulum-2.4.0-macOS.dmg", "browser_download_url": "u2", "size": 2},
    {"name": "kaynak.zip", "browser_download_url": "u3", "size": 3},
]


def test_pick_asset_mac():
    a = uc.pick_asset(ASSETS, platform="darwin")
    assert a["name"].endswith(".dmg") and a["url"] == "u2"


def test_pick_asset_windows():
    a = uc.pick_asset(ASSETS, platform="win32")
    assert a["name"].endswith(".exe") and a["url"] == "u1"


def test_pick_asset_linux_yok():
    assert uc.pick_asset(ASSETS, platform="linux") is None


def test_pick_asset_bos():
    assert uc.pick_asset([], platform="darwin") is None
    assert uc.pick_asset(None, platform="darwin") is None


def test_pick_asset_digest_tasinir():
    varlik = [{"name": "a.dmg", "browser_download_url": "u",
               "size": 5, "digest": "sha256:abc123"}]
    assert uc.pick_asset(varlik, platform="darwin")["digest"] == "sha256:abc123"
    # digest alanı yoksa boş string (eski release'ler)
    assert uc.pick_asset(ASSETS, platform="darwin")["digest"] == ""


# ---------------- indirme bütünlüğü (sahte ağ) ----------------

class _SahteYanit:
    """urllib yanıtı taklidi: verilen içeriği tek chunk'ta döndürür."""
    def __init__(self, icerik):
        self._icerik = icerik
        self.headers = {"Content-Length": str(len(icerik))}
        self._verildi = False

    def read(self, n=-1):
        if self._verildi:
            return b""
        self._verildi = True
        return self._icerik

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _indirme_calistir(monkeypatch, tmp_path, icerik, digest):
    monkeypatch.setattr(uc, "_downloads_dir", lambda: str(tmp_path))
    monkeypatch.setattr(uc.urllib.request, "urlopen",
                        lambda req, timeout=30: _SahteYanit(icerik))
    with uc._download_lock:
        uc._download.update(state="downloading", pct=0, path="", error="")
    uc._run_download("http://x/a.dmg", "a.dmg", len(icerik), digest)
    return uc.download_status()


def test_download_sha256_dogru_ise_done(monkeypatch, tmp_path):
    import hashlib
    icerik = b"hrma-installer-verisi"
    dogru = "sha256:" + hashlib.sha256(icerik).hexdigest()
    st = _indirme_calistir(monkeypatch, tmp_path, icerik, dogru)
    assert st["state"] == "done"
    assert st["path"].endswith("a.dmg")


def test_download_sha256_uyusmazsa_error(monkeypatch, tmp_path):
    st = _indirme_calistir(monkeypatch, tmp_path, b"bozuk-icerik",
                           "sha256:" + "0" * 64)
    assert st["state"] == "error"
    assert "sha256 mismatch" in st["error"]
    # yarım/bozuk dosya Downloads'ta bırakılmaz
    assert not (tmp_path / "a.dmg").exists()


def test_download_digest_yoksa_boyut_yeterli(monkeypatch, tmp_path):
    st = _indirme_calistir(monkeypatch, tmp_path, b"veri", "")
    assert st["state"] == "done"


# ---------------- check_for_update (sahte API) ----------------

@pytest.fixture(autouse=True)
def _temiz_cache():
    with uc._cache_lock:
        uc._cache["checked_at"] = 0.0
        uc._cache["result"] = None
    yield


def test_check_yeni_surum_var(monkeypatch):
    monkeypatch.setattr(uc, "_fetch_latest_release", lambda **kw: {
        "tag_name": "v99.0.0",
        "body": "notlar",
        "html_url": "https://github.com/berketez/HRMA/releases/tag/v99.0.0",
        "draft": False, "prerelease": False,
        "assets": ASSETS,
    })
    r = uc.check_for_update(force=True)
    assert r["available"] is True
    assert r["latest"] == "v99.0.0"
    assert r["current"] == __version__
    # Kurulum paketi YALNIZ macOS (.dmg) ve Windows (.exe) icin yayimlanir;
    # Linux kaynaktan calisir ve pick_asset orada BILEREK None doner (arayuz
    # o durumda Releases sayfasini acar, bkz. update_checker.pick_asset).
    # Eski hali "darwin degilse Windows'tur" varsayiyordu ve Linux CI'da
    # kiriliyordu (2026-07-23).
    if sys.platform == "darwin":
        assert r["asset"] is not None
        assert r["asset"]["name"].endswith(".dmg")
    elif sys.platform in ("win32", "cygwin"):
        assert r["asset"] is not None
        assert r["asset"]["name"].endswith(".exe")
    else:
        assert r["asset"] is None


def test_check_ayni_surum_guncelleme_yok(monkeypatch):
    monkeypatch.setattr(uc, "_fetch_latest_release",
                        lambda **kw: {"tag_name": "v" + __version__,
                                      "draft": False, "prerelease": False,
                                      "assets": ASSETS})
    r = uc.check_for_update(force=True)
    assert r["available"] is False


def test_check_prerelease_gosterilmez(monkeypatch):
    monkeypatch.setattr(uc, "_fetch_latest_release",
                        lambda **kw: {"tag_name": "v99.0.0", "draft": False,
                                      "prerelease": True, "assets": ASSETS})
    r = uc.check_for_update(force=True)
    assert r["available"] is False


def _ag_yok(monkeypatch, api_exc=None):
    """Hem API hem de yedek sayfa yolunu kapatır (test ağa çıkmaz)."""
    def patla_api(**kw):
        raise api_exc or OSError("ağ yok")

    def patla_sayfa(*a, **kw):
        raise OSError("ağ yok")
    monkeypatch.setattr(uc, "_fetch_latest_release", patla_api)
    monkeypatch.setattr(uc, "_fetch_tag_via_page", patla_sayfa)
    monkeypatch.setattr(uc, "_fetch_assets_via_page", patla_sayfa)


def test_check_ag_hatasi_sessiz(monkeypatch):
    _ag_yok(monkeypatch)
    r = uc.check_for_update(force=True)
    assert r["available"] is False
    assert "OSError" in r["error"]
    assert r["error_kind"] == "network"
    assert r["source"] is None


# ---------------- API kotası dolduğunda yedek sayfa yolu ----------------
# 2026-07-24 saha hatası: api.github.com anonim istemciye saatte 60 istek
# verir ve limit IP başınadır; kota dolunca güncelleme tamamen ölüyordu.

ASSET_HTML = """
<div>
  <a href="/berketez/HRMA/releases/download/v9.9.0/HRMA-Setup-9.9.0-macOS.dmg">dmg</a>
  <a href="/berketez/HRMA/releases/download/v9.9.0/HRMA-Setup-9.9.0.exe">exe</a>
  <a href="/berketez/HRMA/releases/download/v9.9.0/HRMA-Setup-9.9.0.exe">exe tekrar</a>
  <a href="https://github.com/kotu/zararli/releases/download/v1/virus.dmg">yabancı</a>
</div>
"""


def test_asset_baglantilari_ayristirilir():
    assets = uc.parse_asset_links(ASSET_HTML)
    adlar = [a["name"] for a in assets]
    assert adlar == ["HRMA-Setup-9.9.0-macOS.dmg", "HRMA-Setup-9.9.0.exe"]  # tekrar yok
    assert all(a["browser_download_url"].startswith(uc.DOWNLOAD_PREFIX) for a in assets)


def test_baska_depo_baglantisi_reddedilir():
    """Sayfaya karışan yabancı depo bağlantısı indirme adresi olamaz."""
    kotu = '<a href="https://github.com/kotu/zararli/releases/download/v1/x.dmg">x</a>'
    assert uc.parse_asset_links(kotu) == []


def test_kota_asiminda_sayfa_yoluna_dusulur(monkeypatch):
    """API 403 verse bile güncelleme sayfa yolundan bulunur."""
    import sys as _sys
    import urllib.error

    # pick_asset platforma göre .dmg/.exe seçer; Linux'ta (CI) ikisi de yok
    # ve asset None döner. Bu test yedek yolun asset ÜRETTİĞİNİ doğruladığı
    # için platformu darwin'e sabitliyoruz (yoksa Linux runner'da r["asset"]
    # None olur — 2026-07-24 CI kırılması).
    monkeypatch.setattr(_sys, "platform", "darwin")

    def kota_dolu(**kw):
        raise urllib.error.HTTPError(uc.RELEASES_API, 403, "rate limit exceeded",
                                     {}, None)
    monkeypatch.setattr(uc, "_fetch_latest_release", kota_dolu)
    monkeypatch.setattr(uc, "_fetch_tag_via_page", lambda **kw: "v99.0.0")
    monkeypatch.setattr(uc, "_fetch_assets_via_page",
                        lambda tag, **kw: uc.parse_asset_links(ASSET_HTML))
    monkeypatch.setattr(uc, "_fetch_notes_via_atom", lambda tag, **kw: "notlar")

    r = uc.check_for_update(force=True)
    assert r["available"] is True
    assert r["latest"] == "v99.0.0"
    assert r["source"] == "page"
    assert r["error"] is None          # kullanıcı hata görmez, güncelleme görür
    assert r["notes"] == "notlar"      # notlar Atom akışından tamamlanır
    assert r["asset"]["url"].startswith(uc.DOWNLOAD_PREFIX)
    assert r["page_url"].endswith("/releases/tag/v99.0.0")


def test_kota_asimi_ve_sayfa_da_olurse_tur_bildirilir(monkeypatch):
    import urllib.error
    _ag_yok(monkeypatch, api_exc=urllib.error.HTTPError(
        uc.RELEASES_API, 403, "rate limit exceeded", {}, None))
    r = uc.check_for_update(force=True)
    assert r["available"] is False
    assert r["error_kind"] == "rate_limit"   # arayüz doğru cümleyi kurabilsin
    assert "error_fallback" in r             # teşhis için ikinci hata da taşınır


def test_sayfa_yolunda_platform_disi_asset_secilmez(monkeypatch):
    """Yalnız .dmg olan bir yayında Windows'a asset verilmez (tarayıcıya düşer)."""
    sadece_dmg = ('<a href="/berketez/HRMA/releases/download/v9.9.0/'
                  'HRMA-Setup-9.9.0-macOS.dmg">dmg</a>')
    assert uc.pick_asset(uc.parse_asset_links(sadece_dmg), platform="win32") is None


def test_check_cache_kullanilir(monkeypatch):
    sayac = {"n": 0}

    def sahte(**kw):
        sayac["n"] += 1
        return {"tag_name": "v99.0.0", "draft": False, "prerelease": False,
                "assets": ASSETS}
    monkeypatch.setattr(uc, "_fetch_latest_release", sahte)
    uc.check_for_update(force=True)
    uc.check_for_update()
    uc.check_for_update()
    assert sayac["n"] == 1


# ---------------- Flask endpoint'leri ----------------

def test_endpointler(monkeypatch):
    from hrma.app import app
    monkeypatch.setattr(uc, "_fetch_latest_release",
                        lambda **kw: {"tag_name": "v99.0.0", "draft": False,
                                      "prerelease": False, "assets": ASSETS})
    c = app.test_client()

    r = c.get("/api/update/check")
    assert r.status_code == 200
    data = r.get_json()
    assert data["available"] is True and data["latest"] == "v99.0.0"

    r = c.get("/api/update/status")
    assert r.status_code == 200
    assert r.get_json()["state"] in ("idle", "downloading", "done", "error")


def test_download_uygun_asset_yoksa_baslatmaz(monkeypatch):
    from hrma.app import app
    # asset listesi boş → indirme başlamamalı, Releases sayfası önerilmeli
    monkeypatch.setattr(uc, "_fetch_latest_release",
                        lambda **kw: {"tag_name": "v99.0.0", "draft": False,
                                      "prerelease": False, "assets": []})
    c = app.test_client()
    r = c.post("/api/update/download")
    assert r.status_code == 200
    data = r.get_json()
    assert data["started"] is False
    assert "page_url" in data
