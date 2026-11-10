"""3.0.6 ana model (NK3-S-10, S1, 9 Kas rc.1 son kullanıcı turu).

Serbest kalan motorun ortalama uçuş kütlesi "kasa + itici/2" KATI motor
bağıntısıdır: itici motorun kendi kasasındadır. Sıvı motorda itici aracın
tanklarındadır; kopan motorun kütlesi motor kuru kütlesi + bağlı kalan besleme
donanımıdır ve bu model onu çözmez. ÖLÇÜLDÜ (örnek sıvı proje, rc.1): kamara
kabuğu 6,716 kg + tank iticisinin yarısı 150,08 kg = 156,8 kg → "yanma sonu hızı
4783 m/s, kinetik enerji 1,79 GJ" yayımlanıyordu. Sıvıda bu üç sayı adıyla geri
çekilir; toplam impuls ve bağlama kuvveti kalır. Katı ve hibrit bit-aynı.
"""
import pytest

from hrma.analysis import safety_analysis as sa


def _serbest(motor_type):
    an = sa.SafetyAnalyzer()
    sonuc = an._calculate_fragment_hazards(
        300.0, 25000.0, 30.0, {'motor_type': motor_type}, 'steel_4130',
        motor_type=motor_type)
    return sonuc['unrestrained_motor']


def test_sivida_hiz_enerji_ve_ortalama_kutle_yayimlanmaz():
    s = _serbest('liquid')
    for ad in sa.UNRESTRAINED_LIQUID_FIELDS:
        assert s[ad] is None, (ad, s[ad])
    assert s['status'] == sa.BURN_TIME_NOT_EVALUATED
    assert s['reason'] == sa.LIQUID_PROJECTILE_MASS_NOT_MODELLED_REASON
    assert s['not_evaluated'] == list(sa.UNRESTRAINED_LIQUID_FIELDS)
    # motor tipinden bağımsız iki sayı kalır
    assert s['total_impulse_ns'] == pytest.approx(25000.0 * 30.0)
    assert s['required_restraint_force_n'] and s['required_restraint_force_n'] > 0


@pytest.mark.parametrize('motor_type', ['solid', 'hybrid'])
def test_kati_ve_hibritte_bagintinin_sayilari_kalir(motor_type):
    s = _serbest(motor_type)
    assert s['mean_flight_mass_kg'] and s['mean_flight_mass_kg'] > 0
    assert s['burnout_velocity_ms'] == pytest.approx(
        s['total_impulse_ns'] / s['mean_flight_mass_kg'])
    assert 'status' not in s
