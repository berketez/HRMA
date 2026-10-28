"""V301/FİZİK-2 kalem 2-3 — güvenlik bölümü: hüküm ve toplam impuls tek kaynaktan.

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/V301/fizik-2/k2_k3_pdf_guvenlik_once.json):
aynı PDF'te katı tablo "Total Impulse 2956,9 N·s" (çözücünün itki integrali)
⟷ güvenlik bölümü "total impulse ns: 3411,51" (tepe itki × süre); hibrit
29930,2 ⟷ 30000 (3000 N × 10 s). Güverte GÜVENLİK sekmesi de itki × süre
basıyordu (katı 3411,50). Sonra (k2_k3_pdf_guvenlik_sonra.json): tablo =
PDF güvenlik bölümü = sekme; kaynak ``motor_total_impulse``.
Kural: motorun yayımladığı impuls kayıt olarak, tohumlandığı itki ve süreyle
gider; istek bunlardan ayrışırsa kayıt benimsenmez (yapısal hükmün deseni).
"""
import copy
import json

import pytest

from hrma.analysis.safety_analysis import (
    MOTOR_VERDICT_INPUT_REL_TOL, TOTAL_IMPULSE_SOURCE_MOTOR,
    TOTAL_IMPULSE_SOURCE_THRUST_X_TIME, SafetyAnalyzer)
from tests.test_d37_panel_js_t5_guvenlik_sinifi import (  # noqa: F401
    _sessiz, client, katalog_json, needs_node)
from tests.test_v301_panel_guvenlik_hukmu import (  # noqa: F401
    VAKALAR, _pdf, sekme, sonuclar)

IMPULSLU = ('hibrit_ornek', 'hibrit_ince_cidar_1mm', 'kati_ornek')


def _um(s):
    return s['explosive_hazards']['fragment_hazards']['unrestrained_motor']


def _motor_impulsu(ad, sonuc):
    m = sonuc['motor'] if VAKALAR[ad] == 'hybrid' else sonuc
    return m['total_impulse']


@pytest.mark.parametrize('ad', IMPULSLU)
def test_pdf_guvenlik_impulsu_motorun_sayisi(sonuclar, ad):
    pdf = _pdf(sonuclar[ad], VAKALAR[ad])
    um = _um(pdf)
    assert um['total_impulse_source'] == TOTAL_IMPULSE_SOURCE_MOTOR
    assert um['total_impulse_ns'] == pytest.approx(
        _motor_impulsu(ad, sonuclar[ad]), rel=1e-12)
    assert um['burnout_velocity_ms'] == pytest.approx(
        um['total_impulse_ns'] / um['mean_flight_mass_kg'], rel=1e-12)
    assert pdf['report_provenance']['inputs_resolved']['total_impulse'] == \
        'report_performance:total_impulse'


@needs_node
@pytest.mark.parametrize('ad', IMPULSLU)
def test_sekme_impulsu_pdf_ile_ayni(sonuclar, sekme, ad):
    um_s = _um(sekme[ad]['j']['safety_analysis'])
    um_p = _um(_pdf(sonuclar[ad], VAKALAR[ad]))
    assert um_s['total_impulse_source'] == TOTAL_IMPULSE_SOURCE_MOTOR
    assert um_s['total_impulse_ns'] == pytest.approx(
        um_p['total_impulse_ns'], rel=1e-12)
    ctx = sekme[ad]['govde']['motor_total_impulse']
    assert ctx['total_impulse_ns'] == pytest.approx(
        _motor_impulsu(ad, sonuclar[ad]), rel=1e-12)


@needs_node
def test_duzenlenmis_sure_motor_impulsunu_kazanmaz(client, sekme):
    govde = copy.deepcopy(sekme['kati_ornek']['govde'])
    govde['burn_time'] = govde['burn_time'] * 2.0
    r = _sessiz(client.post, '/analyze_safety', json=govde)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    um = _um(r.get_json()['safety_analysis'])
    assert um['total_impulse_source'] == TOTAL_IMPULSE_SOURCE_THRUST_X_TIME
    assert um['total_impulse_ns'] == pytest.approx(
        govde['thrust'] * govde['burn_time'], rel=1e-12)
    red = um['motor_total_impulse_not_adopted']
    assert red['reason'] == 'impulse_inputs_differ_from_motor_result'
    assert [f['field'] for f in red['fields']] == ['burn_time']


@needs_node
def test_yuvarlama_toleransi_icinde_benimsenir(sekme):
    """Güverte toPrecision(6) yazar: tohum ⟷ form farkı 1e-5'in içinde."""
    govde = sekme['kati_ornek']['govde']
    ctx = govde['motor_total_impulse']['inputs']
    for ad in ('thrust', 'burn_time'):
        assert abs(govde[ad] - ctx[ad]) <= MOTOR_VERDICT_INPUT_REL_TOL * ctx[ad]


def test_kayitsiz_istek_eskisi_gibi():
    """Kayıt gelmeyen istek: itki × süre, kaynak alanı EKLENMEZ (bit-aynı)."""
    md = {'chamber_pressure': 40.0, 'chamber_diameter': 0.106,
          'wall_thickness': 0.0022, 'burn_time': 3.0, 'thrust': 1500.0}
    um = _um(SafetyAnalyzer().analyze_comprehensive_safety(
        motor_data=md, propellant_mass=5.0, propellant_type='apcp',
        motor_type='solid'))
    assert um['total_impulse_ns'] == pytest.approx(4500.0, rel=1e-12)
    assert 'total_impulse_source' not in um
    assert 'motor_total_impulse_not_adopted' not in um


@pytest.mark.parametrize('deger, neden', [
    (-5.0, 'must_be_positive'), (0.0, 'must_be_positive'),
    ('abc', 'not_a_number'), (True, 'not_a_number')])
def test_fizik_disi_impuls_adli_422(client, deger, neden):
    govde = {'motor_type': 'solid', 'chamber_pressure': 40.0,
             'chamber_diameter': 0.106, 'wall_thickness': 0.0022,
             'propellant_mass': 5.0, 'thrust': 1500.0, 'burn_time': 3.0,
             'motor_total_impulse': {'total_impulse_ns': deger,
                                     'inputs': {'thrust': 1500.0,
                                                'burn_time': 3.0}}}
    r = _sessiz(client.post, '/analyze_safety', json=govde)
    assert r.status_code == 422, r.get_data(as_text=True)[:300]
    alan = r.get_json()['invalid_fields'][0]
    assert alan['field'] == 'motor_total_impulse.total_impulse_ns'
    assert alan['reason'] == neden


def test_nesne_olmayan_baglam_tip_reddi(client):
    govde = {'motor_type': 'solid', 'chamber_pressure': 40.0,
             'chamber_diameter': 0.106, 'wall_thickness': 0.0022,
             'propellant_mass': 5.0, 'thrust': 1500.0, 'burn_time': 3.0,
             'motor_total_impulse': [1, 2, 3]}
    r = _sessiz(client.post, '/analyze_safety', json=govde)
    assert r.status_code in (400, 422), r.get_data(as_text=True)[:300]
    assert 'motor_total_impulse' in json.dumps(r.get_json())


def test_sivi_impuls_yayimlamiyor_kayit_gitmez(sonuclar):
    """V3.0.5 SIVI-CIDAR kalem 4 (FİZİK-2 DEVİR 2) — BEKLENTİ DEĞİŞTİ.

    Eskiden sıvı çözücü toplam impulsu üst düzeyde yayımlamıyordu (tablo
    N/A, kayıt gitmiyor, güvenlik bölümü kendi itki × süresi). Artık çözücü
    KENDİ tanımıyla tek sayıyı yayımlıyor (total_impulse = thrust ×
    burn_time); PDF tablosu onu basar, güvenlik bölümü kaydı motorun sayısı
    olarak benimser ve OpenRocket özetiyle aynı sayıdır. Ölçüm:
    docs/scofield/raw/OH/V301/sivi-cidar/olcum/k4_once.json ⟷ k4_sonra.json.
    (Düğüm adı korunur; iddia: tek sayı, her tüketicide aynı.)"""
    s = sonuclar['sivi_ornek']
    assert s.get('total_impulse') == pytest.approx(
        float(s['thrust']) * float(s['burn_time']), rel=1e-12)
    um = _um(_pdf(s, 'liquid'))
    assert um['total_impulse_source'] == TOTAL_IMPULSE_SOURCE_MOTOR
    assert um['total_impulse_ns'] == pytest.approx(s['total_impulse'],
                                                   rel=1e-12)
    assert um['total_impulse_ns'] == pytest.approx(
        s['openrocket']['motor_summary']['total_impulse'], rel=1e-12)
