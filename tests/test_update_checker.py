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
    assert r["asset"] is not None
    beklenen = ".dmg" if sys.platform == "darwin" else ".exe"
    assert r["asset"]["name"].endswith(beklenen)


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


def test_check_ag_hatasi_sessiz(monkeypatch):
    def patla(**kw):
        raise OSError("ağ yok")
    monkeypatch.setattr(uc, "_fetch_latest_release", patla)
    r = uc.check_for_update(force=True)
    assert r["available"] is False
    assert "OSError" in r["error"]


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
