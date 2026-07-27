# -*- coding: utf-8 -*-
"""GIBS karo önbelleği (hrma/analysis/tile_cache.py) birim testleri.

Ağa ÇIKMAZ: HTTP getirici (_http_bytes) monkeypatch ile sahtelenir. Cache
dizini HRMA_TILE_CACHE_DIR ile tmp_path'e yönlendirilir; gerçek kullanıcı
önbelleğine dokunulmaz.

Kapsam:
  * Karo matris geometrisi (matrix_size, tile<->bbox, lonlat_to_tile) —
    canlı WMTSCapabilities.xml (2026-07-24) ile birebir.
  * URL kurucu z/y/x segment sırası (OSM'nin z/x/y'si DEĞİL).
  * Güvenlik kapıları: layer allowlist reddi, z/x/y aralık, date regex,
    path traversal reddi (realpath önek).
  * Cache HIT/MISS + atomik yazım + LRU süpürme + status/clear.
"""

import os

import pytest

from hrma.analysis import tile_cache as tc


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Karo önbellek dizinini test başına izole tmp dizine yönlendir."""
    d = tmp_path / "tiles"
    monkeypatch.setenv("HRMA_TILE_CACHE_DIR", str(d))
    return d


# ---------------------------------------------------------------------------
# Karo matris geometrisi — canlı GIBS Capabilities (500m/250m) ile birebir
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("z,mw,mh", [
    (0, 2, 1), (1, 3, 2), (2, 5, 3), (3, 10, 5), (4, 20, 10),
    (5, 40, 20), (6, 80, 40), (7, 160, 80), (8, 320, 160),
])
def test_matrix_size_capabilities(z, mw, mh):
    assert tc.matrix_size(z) == (mw, mh)


def test_tile_span():
    # tileSpan(°) = 288/2^z; z7 = 2.25°, z4 = 18°
    assert tc.tile_span_deg(7) == pytest.approx(2.25)
    assert tc.tile_span_deg(4) == pytest.approx(18.0)


def test_tile_bbox_roundtrip_mahia():
    # Mahia (Rocket Lab LC-1): 177.86°E, -39.05° — tarih çizgisi yakını, gerçek vaka
    z = 7
    tx, ty = tc.lonlat_to_tile(z, 177.86, -39.05)
    assert (tx, ty) == (159, 57)
    lon_w, lat_s, lon_e, lat_n = tc.tile_to_bbox(z, tx, ty)
    assert lon_w <= 177.86 <= lon_e
    assert lat_s <= -39.05 <= lat_n
    # Karo derecesi kareseldir
    assert (lon_e - lon_w) == pytest.approx(2.25)
    assert (lat_n - lat_s) == pytest.approx(2.25)


def test_dateline_wrap_and_pole_clamp():
    z = 7
    mw, mh = tc.matrix_size(z)
    # +180 sarmalanır (0..mw-1 dışına taşmaz)
    tx, _ = tc.lonlat_to_tile(z, 180.0, 0.0)
    assert 0 <= tx < mw
    # kutup: y [0, mh) içinde kırpılır (singularity yok)
    _, ty_n = tc.lonlat_to_tile(z, 0.0, 89.999)
    _, ty_s = tc.lonlat_to_tile(z, 0.0, -89.999)
    assert 0 <= ty_n < mh and 0 <= ty_s < mh


# ---------------------------------------------------------------------------
# URL kurucu — z/y/x sırası TEK yerde kilitli
# ---------------------------------------------------------------------------

def test_url_order_zyx_static():
    cfg = tc.layer_config('bluemarble')
    # x=159, y=79 -> URL .../{z}/{y}/{x} = 7/79/159 (satır önce!)
    url = tc._gibs_url(cfg, 7, 159, 79, 'default')
    assert url == ('https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/'
                   'BlueMarble_ShadedRelief_Bathymetry/default/500m/7/79/159.jpg')
    assert tc.GIBS_HOST in url


def test_url_order_zyx_timed():
    cfg = tc.layer_config('viirs')
    url = tc._gibs_url(cfg, 5, 3, 4, '2024-01-15')
    assert url == ('https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/'
                   'VIIRS_SNPP_CorrectedReflectance_TrueColor/default/'
                   '2024-01-15/250m/5/4/3.jpg')


# ---------------------------------------------------------------------------
# Güvenlik kapıları
# ---------------------------------------------------------------------------

def test_layer_allowlist_rejects():
    assert tc.layer_config('bluemarble') is not None
    assert tc.layer_config('BlueMarble') is None      # büyük harf
    assert tc.layer_config('../etc') is None           # traversal karakteri
    assert tc.layer_config('foo bar') is None          # boşluk
    assert tc.layer_config('nope') is None             # allowlist dışı


def test_resolve_unknown_layer_404(cache_dir):
    r = tc.resolve_tile('nope', 5, 1, 1)
    assert r['ok'] is False and r['code'] == 404


def test_resolve_out_of_range_400(cache_dir):
    assert tc.resolve_tile('bluemarble', 9, 1, 1)['code'] == 400    # z > max_zoom
    assert tc.resolve_tile('bluemarble', 7, 999, 1)['code'] == 400  # x aralık dışı
    assert tc.resolve_tile('bluemarble', 7, 1, 999)['code'] == 400  # y aralık dışı
    assert tc.resolve_tile('bluemarble', 4, -1, 1)['code'] == 400   # negatif


def test_resolve_time_layer_requires_date(cache_dir):
    assert tc.resolve_tile('viirs', 5, 1, 1)['code'] == 400
    assert tc.resolve_tile('viirs', 5, 1, 1, date='2020/1/1')['code'] == 400
    assert tc.resolve_tile('viirs', 5, 1, 1, date='not-a-date')['code'] == 400


def test_path_traversal_rejected(cache_dir):
    root = tc.tiles_root()
    # date bileşeni traversal denemesi -> realpath önek kapısı None döner (403)
    assert tc._tile_path(root, 'bluemarble', '../../../../etc', 7, 1, 1, 'jpg') is None
    # meşru bileşenler kök içinde kalır
    ok = tc._tile_path(root, 'bluemarble', 'default', 7, 159, 57, 'jpg')
    assert ok is not None
    assert os.path.realpath(ok).startswith(os.path.realpath(root) + os.sep)


# ---------------------------------------------------------------------------
# Cache HIT/MISS + LRU + status/clear (ağ sahtelenerek)
# ---------------------------------------------------------------------------

_FAKE_JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 4096   # JPEG magic + dolgu


def test_cache_miss_then_hit(cache_dir, monkeypatch):
    calls = {'n': 0}

    def fake_fetch(url, timeout=tc.HTTP_TIMEOUT_S):
        calls['n'] += 1
        assert url.startswith('https://%s/' % tc.GIBS_HOST)   # SABİT host
        return _FAKE_JPEG

    monkeypatch.setattr(tc, '_http_bytes', fake_fetch)

    r1 = tc.resolve_tile('bluemarble', 7, 159, 57)
    assert r1['ok'] and r1['cached'] is False
    assert os.path.exists(r1['path'])
    assert os.path.getsize(r1['path']) == len(_FAKE_JPEG)

    r2 = tc.resolve_tile('bluemarble', 7, 159, 57)
    assert r2['ok'] and r2['cached'] is True
    assert calls['n'] == 1        # 2. çağrı diske gitmedi (HIT)


def test_fetch_fail_returns_503_no_fake_tile(cache_dir, monkeypatch):
    monkeypatch.setattr(tc, '_http_bytes', lambda url, timeout=tc.HTTP_TIMEOUT_S: None)
    r = tc.resolve_tile('bluemarble', 6, 10, 10)
    assert r['ok'] is False and r['code'] == 503
    assert r['available'] is False
    # Sahte doku ÜRETİLMEDİ — diske hiçbir şey yazılmadı
    assert tc.cache_status()['tiles'] == 0


def test_status_and_clear(cache_dir, monkeypatch):
    monkeypatch.setattr(tc, '_http_bytes', lambda url, timeout=tc.HTTP_TIMEOUT_S: _FAKE_JPEG)
    tc.resolve_tile('bluemarble', 6, 10, 10)
    tc.resolve_tile('bluemarble', 6, 11, 10)
    st = tc.cache_status()
    assert st['tiles'] == 2 and st['bytes'] == 2 * len(_FAKE_JPEG)
    assert st['dir'] == tc.tiles_root()
    cl = tc.cache_clear()
    assert cl['cleared'] == 2
    assert tc.cache_status()['tiles'] == 0


def test_lru_evicts_oldest(cache_dir, monkeypatch):
    monkeypatch.setattr(tc, '_http_bytes', lambda url, timeout=tc.HTTP_TIMEOUT_S: _FAKE_JPEG)
    # Cap'i küçült: 3 karo sığar, 4. yazımda LRU süpürsün.
    tile_bytes = len(_FAKE_JPEG)
    monkeypatch.setattr(tc, 'TILE_CACHE_MAX_BYTES', tile_bytes * 3)
    monkeypatch.setattr(tc, '_LRU_LOW_WATER', 0.60)   # süpürme hedefi ~1.8 tile

    import time as _t
    coords = [(6, 10, 10), (6, 11, 10), (6, 12, 10), (6, 13, 10)]
    for i, (z, x, y) in enumerate(coords):
        tc.resolve_tile('bluemarble', z, x, y)
        _t.sleep(0.01)   # mtime ayrımı için

    st = tc.cache_status()
    # Cap 3 tile; 4. yazım LRU tetikler → toplam <= 3 tile kalır, en eski gitmiş
    assert st['tiles'] <= 3
    first = tc._tile_path(tc.tiles_root(), 'bluemarble', 'default', 6, 10, 10, 'jpg')
    assert not os.path.exists(first)   # en eski süpürüldü
