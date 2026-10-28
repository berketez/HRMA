"""V301/PANEL kalem 3 (C-7, Grafik G1) — regüleli kipte tank durumu beyanı.

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/V301/panel/tank_rozeti_once.json``):
örnek N2O/HTPB'de tank 293,15 → 250 K toplam impulsu +%0,0060 değiştiriyor
ve eğri md5'i farklı; ``transient.tank_state_role`` ise
``used_by_this_model: false`` ("bit-identical") diyor, rozet "TANK DURUMU
KULLANILMADI" basıyordu. Kök: motor N2O'yu bu sıcaklıkta giriş durumu olarak
yakar. Doluluk oranı ve LOX'ta sıcaklık gerçekten hiçbir sayıyı değiştirmez.

Bekçi ÖLÇÜMDÜR: sıcaklık değiştirilir; impuls değişiyorsa beyan "kullanıldı",
değişmiyorsa "kullanılmadı". Doluluk oranı her durumda "kullanılmadı".
"""
import contextlib
import io
import pathlib

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
ORNEK = KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma'


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


def _taban():
    # V301/T-ÇAPA-D: örnek dosya ÖRNEK kulvarından (5fa435893) beri sayfanın
    # boş alanlarını '' olarak taşıyor; sayfa onları göndermez (ölçüm:
    # tests/support/ornek_alanlari.py).
    from tests.support.ornek_alanlari import ornek_alanlari
    alan = ornek_alanlari(ORNEK)
    return dict(alan, feed_mode='regulated')


def _kos(client, govde):
    r = _sessiz(client.post, '/api/transient-analysis', json=govde)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['transient']


VAKALAR = {
    # ad: (taban güncellemesi, sıcaklık A, sıcaklık B)
    'n2o': ({}, 293.15, 250.0),
    'lox': ({'oxidizer_type': 'lox', 'of_ratio': 2.3,
             'oxidizer_density': 1141.0, 'oxidizer_viscosity': 1.9e-4},
            85.0, 95.0),
}


@pytest.mark.parametrize('ad', sorted(VAKALAR))
def test_beyan_olculen_davranisla_ayni(client, ad):
    ek, ta, tb = VAKALAR[ad]
    govde = dict(_taban(), **ek)
    a = _kos(client, dict(govde, tank_temperature=ta, oxidizer_temp=ta))
    b = _kos(client, dict(govde, tank_temperature=tb, oxidizer_temp=tb))
    degisti = a['total_impulse'] != b['total_impulse']
    for tr in (a, b):
        rol = tr['tank_state_role']
        assert rol['used_by_this_model'] is degisti, (ad, rol)
        assert rol['drives_feed'] is False
        assert rol['liquid_fill_fraction_used'] is False
        if degisti:
            assert rol['used_as'] == 'motor_oxidizer_inlet_state'
            assert 'bit-identical' not in rol['reason']
    # Ölçülen sonuç: N2O'da değişir (giriş durumu), LOX'ta değişmez.
    assert degisti is (ad == 'n2o')


def test_doluluk_orani_hicbir_sayiyi_degistirmez(client):
    govde = dict(_taban(), tank_temperature=293.15)
    a = _kos(client, dict(govde, liquid_fill_fraction=0.85))
    b = _kos(client, dict(govde, liquid_fill_fraction=0.60))
    assert a['total_impulse'] == b['total_impulse']
    assert a['tank_state_role']['liquid_fill_fraction_used'] is False


def test_motor_baska_sicaklikla_kurulduysa_kullanilmadi():
    """Çözücüye verilen sıcaklık motorun giriş sıcaklığı değilse beyan
    "kullanılmadı" kalır ve motorun sıcaklığını adıyla söyler."""
    from hrma.analysis.transient_ballistics import TransientBallistics
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    motor = HybridRocketEngine(thrust=1000.0, burn_time=10.0, of_ratio=6.0,
                               chamber_pressure=20.0, fuel_type='htpb',
                               oxidizer_type='n2o')
    _sessiz(motor.calculate)
    rol = TransientBallistics(motor, feed_mode='regulated',
                              tank_temperature=250.0)._tank_state_role
    assert rol['used_by_this_model'] is False
    assert '293.15 K' in rol['reason']


def test_rozet_anahtarlari_iki_dilde():
    metin = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    for anahtar in ('transient.badgeTankTempInletOnly',
                    'transient.tankTempInletOnlyTip'):
        assert metin.count("'%s':" % anahtar) == 2, anahtar
    assert 'TANK SICAKLIĞI KULLANILDI (regüleli)' in metin
