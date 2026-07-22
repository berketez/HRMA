"""Çevrimdışı propellant önbelleği testleri.

Ağa ÇIKILMAZ: tüm requests çağrıları monkeypatch ile ConnectionError
fırlatır ya da hiç tetiklenmez. Kullanıcı-veri dizini HRMA_USER_DATA_DIR
ortam değişkeniyle tmp_path'e yönlendirilir; gerçek kullanıcı cache'ine
dokunulmaz.
"""

import json
import os
import pickle
from datetime import datetime, timedelta

import pytest
import requests

from hrma.data import offline_store
from hrma.data.open_source_propellant_api import propellant_api
from hrma.data.web_propellant_api import web_api


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    """Kullanıcı cache dizinini test başına izole tmp dizine yönlendir."""
    d = tmp_path / "userdata"
    monkeypatch.setenv("HRMA_USER_DATA_DIR", str(d))
    return d


def _raise_connection_error(*args, **kwargs):
    raise requests.ConnectionError("simulated offline")


# ---------------- offline_store: anahtar üretimi ----------------

def test_make_key_float_yuvarlama():
    k1 = offline_store.make_key("webapi", "rp1", "lox", 20.0, 2.5)
    k2 = offline_store.make_key("webapi", "rp1", "lox", 20.0000001, 2.5000001)
    assert k1 == k2 == "webapi:rp1|lox|20|2.5"


def test_make_key_kucuk_harf_ve_kirpma():
    assert offline_store.make_key("pubchem", " RP-1 ") == "pubchem:rp-1"


# ---------------- offline_store: put/get gidiş-dönüş ----------------

def test_put_get_gidis_donus(user_dir):
    key = offline_store.make_key("pubchem", "test-compound")
    assert offline_store.get(key) is None

    data = {"density": 815.0, "count": 3, "nested": {"a": [1, 2.5], "b": "x"}}
    assert offline_store.put(key, data) is True
    assert offline_store.get(key) == data

    # Dosya gerçekten kullanıcı dizinine, geçerli JSON olarak yazıldı
    cache_file = user_dir / "propellant_cache.json"
    assert cache_file.exists()
    doc = json.loads(cache_file.read_text(encoding="utf-8"))
    assert key in doc["entries"]
    assert "timestamp" in doc["entries"][key]


def test_put_numpy_degerleri_json_uyumlu(user_dir):
    np = pytest.importorskip("numpy")
    key = offline_store.make_key("pubchem", "numpy-test")
    offline_store.put(key, {
        "d": np.float64(1.5),
        "i": np.int32(7),
        "arr": np.array([1.0, 2.0]),
    })
    out = offline_store.get(key)
    assert out["d"] == 1.5
    assert out["i"] == 7
    assert out["arr"] == [1.0, 2.0]


# ---------------- offline_store: snapshot okuma ----------------

def test_snapshot_okuma_ve_kullanici_cache_onceligi(user_dir, tmp_path, monkeypatch):
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({
        "_meta": {"generated": "2026-07-16", "note": "test"},
        "entries": {"pubchem:foo": {"data": {"x": 1}, "timestamp": "t"}},
    }), encoding="utf-8")
    monkeypatch.setattr(offline_store, "SNAPSHOT_PATH", str(snap))

    # Kullanıcı cache boşken snapshot'tan okunur
    assert offline_store.get("pubchem:foo") == {"x": 1}

    # Kullanıcı cache'i snapshot'ı ezer
    offline_store.put("pubchem:foo", {"x": 2})
    assert offline_store.get("pubchem:foo") == {"x": 2}


def test_paketli_snapshot_gecerli():
    """Repo ile gelen offline_snapshot.json geçerli ve dolu olmalı."""
    with open(offline_store.SNAPSHOT_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    assert "_meta" in doc
    assert isinstance(doc.get("entries"), dict)
    assert len(doc["entries"]) > 0
    # Her giriş data + timestamp taşımalı
    for key, entry in doc["entries"].items():
        assert "data" in entry, key
        assert "timestamp" in entry, key


# ---------------- ağ kapalı: get_propellant_for_ui ----------------

def test_ag_kapali_get_propellant_for_ui(user_dir, monkeypatch):
    """requests ConnectionError fırlatırken UI verisi yine dict dönmeli."""
    monkeypatch.setattr(requests, "get", _raise_connection_error)
    monkeypatch.setattr(requests, "post", _raise_connection_error)
    propellant_api.cache.clear()

    combos = [
        ("hybrid_fuel", "htpb"),
        ("oxidizer", "n2o"),
        ("liquid_fuel", "rp1"),
        ("solid_propellant", "apcp"),
    ]
    for ptype, pname in combos:
        ui = propellant_api.get_propellant_for_ui(ptype, pname)
        assert isinstance(ui, dict), (ptype, pname)
        assert ui.get("density", 0) > 0, (ptype, pname)
        assert "data_source" in ui, (ptype, pname)


# ---------------- web_api: stale-if-error yolu ----------------

def test_web_api_stale_if_error(user_dir, tmp_path, monkeypatch):
    """TTL dolmuş pickle cache, ağ hatasında yaş sınırsız servis edilmeli."""
    pkl_dir = tmp_path / "pkl"
    pkl_dir.mkdir()
    monkeypatch.setattr(web_api, "cache_dir", str(pkl_dir))
    monkeypatch.setattr(web_api.session, "get", _raise_connection_error)
    monkeypatch.setattr(web_api.session, "post", _raise_connection_error)

    # 5 saat önce yazılmış (TTL=1 saat dolmuş) cache girişi hazırla;
    # density kasıtlı olarak statik fallback'ten farklı: bayat yolun kanıtı
    seeded = {"compound": "lox", "density": 999.9, "status": "success",
              "source": "NIST API (Live)"}
    cache_key = web_api._get_cache_key("nist", "lox")
    with open(pkl_dir / f"{cache_key}.pkl", "wb") as f:
        pickle.dump({"data": seeded,
                     "timestamp": datetime.now() - timedelta(hours=5)}, f)

    out = web_api.fetch_nist_data("lox")
    assert out["density"] == 999.9


def test_web_api_offline_store_yolu(user_dir, tmp_path, monkeypatch):
    """Pickle cache yokken kalıcı depo (kullanıcı cache) devreye girmeli."""
    pkl_dir = tmp_path / "pkl"
    pkl_dir.mkdir()
    monkeypatch.setattr(web_api, "cache_dir", str(pkl_dir))

    # Bilinmeyen bileşik ağ isteği atılmadan ValueError üretir;
    # akış bayat cache -> kalıcı depo sırasıyla düşer
    key = offline_store.make_key("webapi", "nist", "testfuelx")
    offline_store.put(key, {"compound": "testfuelx", "density": 123.4,
                            "status": "success"})
    out = web_api.fetch_nist_data("testfuelx")
    assert out["density"] == 123.4


def test_web_api_ag_yok_cache_yok_yine_dict(user_dir, tmp_path, monkeypatch):
    """Hiçbir katman yokken bile exception değil dict dönmeli (statik fallback)."""
    pkl_dir = tmp_path / "pkl"
    pkl_dir.mkdir()
    empty_snap = tmp_path / "empty_snap.json"
    monkeypatch.setattr(web_api, "cache_dir", str(pkl_dir))
    monkeypatch.setattr(offline_store, "SNAPSHOT_PATH", str(empty_snap))
    monkeypatch.setattr(web_api.session, "get", _raise_connection_error)
    monkeypatch.setattr(web_api.session, "post", _raise_connection_error)

    out = web_api.fetch_nist_data("lox")
    assert isinstance(out, dict)
    assert out.get("density", 0) > 0
