"""V301/FİZİK-2 kalem 6 (KABUL 13-14) — CAD ⟷ yanıt ⟷ uçuş aracı ölçüleri tek kaynak.

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/V301/fizik-2/k6_olcu_once.json, KABUL
K3 yardımcılarıyla STEP/STL): katı lüle arka ucu 547,646 ⟷ yayımlanan boy
547,183 mm, kapaklı boy (557,088) yayımlanmıyordu; uçuş aracı çapı lüle
çıkışının İÇ çapından ya da kasadan: katı 89 ⟷ çizilen 91, sıvı 189,555 ⟷
200,555, hibrit 93,797 ⟷ 127,91 mm. Sonra (k6_olcu_sonra.json): boylar STEP
ile aynı (CAD-2'nin tek tanımı), araç zarfı çizilen dış zarf, araç boyu
kapaklı toplam.
"""
import contextlib
import copy
import io

import pytest

from hrma.analysis import flight_vehicle as FV
from hrma.engines.nozzle_design import sample_nozzle_inner_contour
from hrma.export import cad_visualization as CV
from hrma.export.motor_geometry import normalise_export_geometry
from tests.support import kabul

H = {'Host': '127.0.0.1:8080'}
UC = {'solid': '/calculate_solid', 'liquid': '/calculate_liquid',
      'hybrid': '/calculate'}


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def sonuclar(client):
    out = {}
    for mt, uc in UC.items():
        r = _sessiz(client.post, uc, json=kabul.sayfa_yuku(mt), headers=H)
        assert r.status_code == 200, (mt, r.status_code)
        out[mt] = r.get_json()
    return out


def _motor(mt, s):
    return s['motor'] if mt == 'hybrid' else s


def _cizilen_lule_dis_cap_mm(motor):
    md, _ = normalise_export_geometry(copy.deepcopy(motor))
    prof = CV.nozzle_wall_profile(md, unit='mm', require_solved_length=True)
    return 2.0 * max(r for _z, r in prof['outer'])


def _arac(client, mt, s):
    r = _sessiz(client.post, '/api/flight-vehicle', json={
        'motor_type': mt, 'source': 'results', 'results': s}, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    j = r.get_json()
    return j.get('vehicle') or j


def test_kati_boy_cizilen_lule_ve_kapak(sonuclar):
    s = sonuclar['solid']
    kd = s['design_summary']['key_dimensions']
    md, _ = normalise_export_geometry(copy.deepcopy(s))
    _pts, meta = sample_nozzle_inner_contour(md)
    kapak = CV._front_cap_design(md)['thickness_mm']
    assert kd['nozzle_drawn_length_mm'] == pytest.approx(meta['z_exit'],
                                                         rel=1e-12)
    assert kd['total_length_mm'] == pytest.approx(
        kd['motor_length_mm'] + meta['z_exit'], rel=1e-12)
    assert kd['forward_closure_length_mm'] == pytest.approx(kapak, rel=1e-12)
    assert kd['total_length_with_closure_mm'] == pytest.approx(
        kd['total_length_mm'] + kapak, rel=1e-12)


@pytest.mark.parametrize('mt', ['solid', 'liquid', 'hybrid'])
def test_arac_zarfi_cizilen_dis_zarf(client, sonuclar, mt):
    s = sonuclar[mt]
    v = _arac(client, mt, s)
    lule = _cizilen_lule_dis_cap_mm(_motor(mt, s))
    assert v['engine_od_m'] * 1000.0 >= lule * (1.0 - 1e-12)
    # Bu üç örnekte en geniş çizilen parça lüledir (STEP ölçümü:
    # k6_olcu_sonra.json) — araç zarfı onun çapıdır.
    assert v['engine_od_m'] * 1000.0 == pytest.approx(lule, rel=1e-12)
    assert v['engine_od_unit_source'].startswith(
        FV.DRAWN_NOZZLE_ENVELOPE_SOURCE)


@pytest.mark.parametrize('mt, alan', [
    ('solid', 'total_length_with_closure_mm'),
    ('liquid', 'overall_length_with_closure_mm'),
    ('hybrid', 'total_motor_length_with_caps_mm')])
def test_arac_boyu_kapakli_toplam(client, sonuclar, mt, alan):
    s = sonuclar[mt]
    kd = _motor(mt, s)['design_summary']['key_dimensions']
    v = _arac(client, mt, s)
    assert v['engine_length_m'] == pytest.approx(kd[alan] / 1000.0,
                                                 rel=1e-12)


def test_profil_cozulemezse_eski_kural_beyanla():
    v = FV.normalize('liquid', {
        'chamber_diameter': 109.4, 'length_units': {'chamber_diameter': 'mm'},
        'design_summary': {'key_dimensions': {'nozzle_exit_mm': 189.5545}}})
    assert v['engine_od_m'] == pytest.approx(0.1895545)
    assert 'nozzle exit' in v['engine_od_unit_source']
