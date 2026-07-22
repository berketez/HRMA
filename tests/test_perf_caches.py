"""v2.5.5 performans önbellekleri — davranış koruma (bit-aynılık) testleri.

Kapsam:
  1. Katı motor shapely geometri önbellekleri (_cached_case_disk /
     _cached_case_ring / _cached_star_polygon / _cached_wagon_polygon /
     _cached_slot_quads): soğuk (önbellek boş) ve sıcak (önbellek dolu)
     koşular BİT-AYNI itki eğrisi üretmeli.
  2. _propellant_volume memoizasyonu: tekrar çağrı aynı değeri döndürür,
     geometri değişince anahtar değişir ve yeniden hesaplanır.
  3. Slotted ofset memoizasyonu: memo'lu değerler taze motorunkiyle aynı.
  4. Optimum O/F arama önbelleği (combustion_analysis._OPTIMUM_OF_CACHE):
     isabet, taze hesapla bit-aynı sonuç verir; dönen kopyanın mutasyonu
     önbelleği bozmaz; farklı girdi farklı anahtara gider.
  5. JS tarafı sözleşme: analysis_dock purgePlots tanımlar ve yeniden
     çizim yollarında kullanılır; aynı div'e tekrar çizen paneller
     Plotly.react kullanır (plotly 1.58.5'te mevcut, 1.34+).
"""

import copy
from pathlib import Path

import numpy as np
import pytest

from hrma.engines import solid_rocket_engine as sre
from hrma.engines.solid_rocket_engine import SolidRocketEngine, SHAPELY_AVAILABLE
import hrma.engines.combustion_analysis as ca
from hrma.engines.combustion_analysis import CombustionAnalyzer

STATIC_JS = Path(__file__).resolve().parents[1] / 'hrma' / 'static' / 'js'

CURVE_KEYS = ('time', 'thrust', 'pressure', 'burn_area', 'mass_flow',
              'burn_rate')

SHAPELY_GRAINS = ('star', 'wagon_wheel', 'finocyl', 'slotted')


def _clear_geometry_caches():
    sre._cached_case_disk.cache_clear()
    sre._cached_case_ring.cache_clear()
    sre._cached_star_polygon.cache_clear()
    sre._cached_wagon_polygon.cache_clear()
    sre._cached_slot_quads.cache_clear()


def _curve_arrays(grain_type):
    eng = SolidRocketEngine(grain_type=grain_type, propellant_type='apcp')
    curve = eng.calculate_thrust_curve()
    return {k: np.asarray(curve[k]) for k in CURVE_KEYS}


# ---------------------------------------------------------------------------
# 1. Shapely geometri önbellekleri: soğuk == sıcak (bit-aynı)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason='shapely kurulu değil')
@pytest.mark.parametrize('grain_type', SHAPELY_GRAINS)
def test_thrust_curve_bit_identical_cold_vs_warm(grain_type):
    _clear_geometry_caches()
    cold = _curve_arrays(grain_type)     # önbellek boş — her poligon kurulur
    warm = _curve_arrays(grain_type)     # önbellek dolu — poligonlar paylaşılır
    for key in CURVE_KEYS:
        np.testing.assert_array_equal(
            cold[key], warm[key],
            err_msg=f'{grain_type}/{key}: önbellekli koşu soğuk koşudan saptı')


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason='shapely kurulu değil')
def test_geometry_cache_no_collision_between_geometries():
    """Farklı geometri parametreleri farklı önbellek anahtarına gitmeli."""
    # Kasa diski: yarıçap anahtarın parçası
    d1 = sre._cached_case_disk(0.05)
    d2 = sre._cached_case_disk(0.06)
    assert d1.area != d2.area
    # Star poligonu: uç sayısı / yarıçap / derinlik anahtarın parçası
    s1 = sre._cached_star_polygon(6, 0.02, 0.010)
    s2 = sre._cached_star_polygon(8, 0.02, 0.010)
    s3 = sre._cached_star_polygon(6, 0.02, 0.012)
    assert s1.area != s2.area and s1.area != s3.area
    # Yuva dörtgenleri: genişlik anahtarın parçası
    q1 = sre._cached_slot_quads(0.02, 4, 0.006, 0.015)
    q2 = sre._cached_slot_quads(0.02, 4, 0.008, 0.015)
    assert q1[0].area != q2[0].area


# ---------------------------------------------------------------------------
# 2. _propellant_volume memoizasyonu
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason='shapely kurulu değil')
def test_propellant_volume_memo_consistency():
    eng = SolidRocketEngine(grain_type='slotted', propellant_type='apcp')
    v1 = eng._propellant_volume()
    v2 = eng._propellant_volume()        # memo isabeti
    assert v1 == v2
    assert v1 == eng._propellant_volume_uncached()

    # Geometri değişince anahtar değişmeli ve değer yeniden hesaplanmalı
    eng.D_chamber *= 1.2
    v3 = eng._propellant_volume()
    assert v3 != v1, 'geometri değişti ama memo eski değeri döndürdü'
    assert v3 == eng._propellant_volume_uncached()


# ---------------------------------------------------------------------------
# 3. Slotted ofset memoizasyonu (çift çağrı — burn area + port akış kesiti)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason='shapely kurulu değil')
def test_slotted_offset_memo_matches_fresh_engine():
    web = 0.004
    eng = SolidRocketEngine(grain_type='slotted', propellant_type='apcp')
    # Aynı web ile ardışık iki tüketici (itki eğrisi adımının deseni)
    area_burn = eng.calculate_burn_area(web)
    area_flow = eng._port_flow_area(web)

    fresh = SolidRocketEngine(grain_type='slotted', propellant_type='apcp')
    assert area_flow == fresh._port_flow_area(web)
    assert area_burn == fresh.calculate_burn_area(web)


# ---------------------------------------------------------------------------
# 4. Optimum O/F arama önbelleği
# ---------------------------------------------------------------------------
def _flat_equal(x, y, path=''):
    """İç içe dict/list yapıyı TAM eşitlikle karşılaştırır (tolerans yok)."""
    assert type(x) is type(y), f'{path}: tip farkı {type(x)} != {type(y)}'
    if isinstance(x, dict):
        assert set(x) == set(y), f'{path}: anahtar kümeleri farklı'
        for k in x:
            _flat_equal(x[k], y[k], f'{path}.{k}')
    elif isinstance(x, (list, tuple)):
        assert len(x) == len(y), f'{path}: uzunluk farkı'
        for i, (xi, yi) in enumerate(zip(x, y)):
            _flat_equal(xi, yi, f'{path}[{i}]')
    elif isinstance(x, np.ndarray):
        np.testing.assert_array_equal(x, y, err_msg=path)
    else:
        assert x == y, f'{path}: {x!r} != {y!r}'


def test_optimum_of_cache_bit_identical_and_isolated():
    fuel = {'htpb': 100.0}
    ca._OPTIMUM_OF_CACHE.clear()

    an1 = CombustionAnalyzer()
    fresh = an1.find_optimum_of_ratio(fuel, 'n2o', 20.0)   # soğuk — gerçek arama
    assert len(ca._OPTIMUM_OF_CACHE) == 1

    an2 = CombustionAnalyzer()
    hit = an2.find_optimum_of_ratio(fuel, 'n2o', 20.0)     # isabet — kopya döner
    _flat_equal(fresh, hit, 'optimum_of')

    # Dönen kopyanın mutasyonu önbelleği BOZMAMALI
    hit['optimum_of_ratio'] = -1.0
    hit['analysis']['performance']['isp'] = -1.0
    again = an2.find_optimum_of_ratio(fuel, 'n2o', 20.0)
    _flat_equal(fresh, again, 'optimum_of_after_mutation')

    # Farklı Pc farklı anahtara gitmeli (yuvarlama YOK, tam eşleşme)
    an2.find_optimum_of_ratio(fuel, 'n2o', 25.0)
    assert len(ca._OPTIMUM_OF_CACHE) == 2

    ca._OPTIMUM_OF_CACHE.clear()


def test_optimum_of_cache_bounded():
    """Önbellek sınırı aşılınca en eski kayıt atılır (bellek büyümez)."""
    fuel = {'htpb': 100.0}
    ca._OPTIMUM_OF_CACHE.clear()
    analyzer = CombustionAnalyzer()
    for i in range(ca._OPTIMUM_OF_CACHE_MAX + 3):
        analyzer.find_optimum_of_ratio(fuel, 'n2o', 15.0 + 0.001 * i)
    assert len(ca._OPTIMUM_OF_CACHE) <= ca._OPTIMUM_OF_CACHE_MAX
    ca._OPTIMUM_OF_CACHE.clear()


# ---------------------------------------------------------------------------
# 5. Sıvı motor web-verisi süreç içi memo'su
# ---------------------------------------------------------------------------
def _fake_web_data(density):
    return {
        'fuel_properties': {'density': density, 'status': 'success'},
        'oxidizer_properties': {'density': 1141.0, 'status': 'success'},
        'combustion_data': {'status': 'fallback'},
        'flight_validation': {},
        'summary': {'confidence': 'high'},
    }


def test_liquid_web_data_memo_avoids_refetch(monkeypatch):
    import time as _time
    from hrma.engines import liquid_rocket_engine as lre
    from hrma.data.web_propellant_api import web_api

    eng = lre.LiquidRocketEngine(thrust=5000, chamber_pressure=50)
    key = (str(eng.fuel_type), str(eng.oxidizer_type),
           float(eng.P_c), float(eng.MR))

    # TTL içindeki memo girdisi varken ağa ÇIKILMAMALI
    lre._WEB_DATA_MEMO.clear()
    lre._WEB_DATA_MEMO[key] = (_time.time(), _fake_web_data(810.0))

    def boom(*args, **kwargs):
        raise AssertionError('memo isabetinde get_comprehensive_data '
                             'çağrılmamalı (ağ isteği tekrarı)')

    monkeypatch.setattr(web_api, 'get_comprehensive_data', boom)
    data = eng.web_propellant_data          # tembel property fetch tetikler
    assert data[eng.fuel_type]['density'] == 810.0
    lre._WEB_DATA_MEMO.clear()


def test_liquid_web_data_memo_respects_ttl(monkeypatch):
    import time as _time
    from hrma.engines import liquid_rocket_engine as lre
    from hrma.data.web_propellant_api import web_api

    eng = lre.LiquidRocketEngine(thrust=5000, chamber_pressure=50)
    key = (str(eng.fuel_type), str(eng.oxidizer_type),
           float(eng.P_c), float(eng.MR))

    # TTL DIŞI memo girdisi: taze veri çekilmeli (tazelik sözleşmesi korunur)
    lre._WEB_DATA_MEMO.clear()
    stale_ts = _time.time() - float(web_api.cache_ttl) - 1.0
    lre._WEB_DATA_MEMO[key] = (stale_ts, _fake_web_data(810.0))
    monkeypatch.setattr(web_api, 'get_comprehensive_data',
                        lambda **kw: _fake_web_data(925.0))
    data = eng.web_propellant_data
    assert data[eng.fuel_type]['density'] == 925.0, (
        'TTL geçmiş memo girdisi kullanılmamalıydı')
    lre._WEB_DATA_MEMO.clear()


# ---------------------------------------------------------------------------
# 6. JS sözleşme bekçileri — panel yeniden çizim sızıntı korumaları
# ---------------------------------------------------------------------------
def _js(name):
    return (STATIC_JS / name).read_text(encoding='utf-8')


def test_analysis_dock_defines_and_uses_purge():
    src = _js('analysis_dock.js')
    assert 'function purgePlots(' in src, 'purgePlots yardımcısı kaldırılmış'
    assert 'purgePlots: purgePlots' in src, 'purgePlots ui üzerinden paylaşılmalı'
    # runPanel / rerenderAll içindeki innerHTML sıfırlamalarından önce purge
    assert src.count('purgePlots(root)') >= 2, (
        'runPanel/rerenderAll innerHTML sıfırlamadan önce purgePlots çağırmalı '
        '(plotly 1.58.5 responsive resize dinleyicisi ancak purge ile kalkar)')


@pytest.mark.parametrize('name, needle', [
    ('panels/feed_panel.js', 'U.purgePlots(result)'),
    ('panels/comparative_panel.js', 'U.purgePlots(root)'),
    ('panels/validation_panel.js', 'U.purgePlots(root)'),
    ('panels/uncertainty_panel.js', 'U.purgePlots(root)'),
    ('panels/thermal_panel.js', 'U.purgePlots(charts)'),
])
def test_panels_purge_before_wipe(name, needle):
    assert needle in _js(name), (
        f'{name}: kendi innerHTML sıfırlaması öncesi {needle} çağrısı '
        'kaldırılmış — Plotly resize dinleyicisi sızar')


@pytest.mark.parametrize('name', ['transient_panel.js',
                                  'panels/uncertainty_panel.js'])
def test_repeat_draw_panels_use_react(name):
    src = _js(name)
    assert 'Plotly.react(' in src, (
        f'{name}: aynı div\'e tekrar çizim Plotly.react ile yapılmalı '
        '(newPlot her seferinde tam yıkım+kurulum yapar)')
