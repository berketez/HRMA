"""v3.0.1 (Ayberk tur 1) — port ⟷ kamara doğrulama hükmü motorun zarfından.

Port kulvarı grain dış çapını yanma sonu portlarından boyutladı (artık et 0
iken D_son = D_kamara, tasarım gereği) ve motordaki kaynaksız 0,8·D_ch
kırpmasını söktü. ``validation_system`` ise aynı 0,8 kuralının ikinci
kopyasını taşıyordu: ``d_port_final > 0.8 * d_chamber`` -> 'kritik'.
Birleşik ağaçta ÖLÇÜLDÜ: her varsayılan hibrit tasarım (1 kN, O/F 6)
``warn.validation.port_exceeds_chamber`` kritik uyarısı alıyordu, yani
kullanıcıya yanlış bir "tane delinir" hükmü gidiyordu.

Sözleşme: hüküm yalnız gerçek delinmede (son port zarfı k(N)·D_son +
2·t_artık kamara iç çapını AŞARSA) verilir.
"""

import io
import contextlib

import pytest

from hrma.app import app
from hrma.validation.validation_system import validator

KOD = 'warn.validation.port_exceeds_chamber'

PORT_DOGRULAMA_HIBRIT_GOVDESI = {
    'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
    'chamber_pressure': 20.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'include_plots': False,
}


def _kodlar(veri):
    sonuc = validator.validate_geometry_data(veri)
    return [w.get('code') for w in sonuc if isinstance(w, dict)]


@pytest.fixture(scope='module')
def varsayilan():
    with contextlib.redirect_stdout(io.StringIO()):
        r = app.test_client().post('/calculate',
                                   json=PORT_DOGRULAMA_HIBRIT_GOVDESI)
    assert r.status_code == 200
    return r.get_json()


def test_varsayilan_tasarim_yanlis_kritik_almaz(varsayilan):
    m = varsayilan['motor']
    assert m['port_diameter_final'] == pytest.approx(m['chamber_diameter'])
    kritik = [w.get('code') for w in
              (varsayilan.get('validation') or {}).get('critical_warnings')
              or []]
    assert KOD not in kritik, (
        'artık et 0 iken D_son = D_kamara tasarım gereğidir; '
        '"port kamarayı aşıyor" kritik hükmü yanlış')


def test_tek_port_gercek_delinme_kritik():
    veri = {'port_diameter_initial': 0.03, 'port_diameter_final': 0.0601,
            'chamber_diameter': 0.060, 'port_count': 1,
            'residual_web_mm': 0.0}
    assert KOD in _kodlar(veri)


def test_artik_et_zarfa_eklenir():
    # D_son 58 mm + 2·1,5 mm = 61 mm > 60 mm kamara -> delinme.
    veri = {'port_diameter_initial': 0.03, 'port_diameter_final': 0.058,
            'chamber_diameter': 0.060, 'port_count': 1,
            'residual_web_mm': 1.5}
    assert KOD in _kodlar(veri)
    veri['residual_web_mm'] = 0.5     # 58 + 1 = 59 mm, sığar
    assert KOD not in _kodlar(veri)


def test_cok_port_halka_zarfi():
    # N = 4: k = 1 + 1/sin(π/4) = 2,4142; 25 mm port -> 60,36 mm zarf.
    veri = {'port_diameter_initial': 0.015, 'port_diameter_final': 0.025,
            'chamber_diameter': 0.060, 'port_count': 4,
            'residual_web_mm': 0.0}
    assert KOD in _kodlar(veri)
    veri['chamber_diameter'] = 0.0605
    assert KOD not in _kodlar(veri)
