"""V306 (6 Kas 2026, ana model) — hibrit doğrulayıcının kaynaksız hüküm bantları.

Kaynak: HİBRİT-SAYI RAPOR "AÇIK KALANLAR" (Isp 180-250 s / port 5-100 mm
kaynaksız; GERÇEK ölçülmüş Carmicino t01 motoru 147,4 s ile "beklenen aralık
dışında" uyarısı alıyordu) + ÖLÇÜT gözlemleri + ana model denetimi. Bant
künyesi ``validation_system.ValidationSystem.__init__``'te.

İlke (SAYI emsali ``test_kaynaksiz_hukum_bandi_YOK``): kaynaksız "beklenen
aralık" hükmü kalkar; kalan hükümler kaynaklıdır ya da fiziksel
imkânsızlıktır (port zarfı > oda, ε <= 1, CF > CF_sonsuz(γ)).
"""
import re
from pathlib import Path

import pytest

from hrma.analysis.nozzle_flow_1d import ideal_thrust_coefficient
from hrma.validation.validation_system import ValidationSystem

KOK = Path(__file__).resolve().parents[1]
SOZLUK = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'

KALKAN_KODLAR = (
    'isp_out_of_range', 'gamma_out_of_range', 'port_initial_out_of_range',
    'port_growth_low', 'port_growth_high', 'cf_too_low', 'lstar_low',
    'lstar_high', 'regression_low', 'regression_high', 'reynolds_high',
    'reynolds_laminar', 'exit_velocity_out_of_range',
)


def _kodlar(uyarilar):
    return {w['code'] for w in uyarilar}


@pytest.fixture()
def vs():
    return ValidationSystem()


def test_kaynaksiz_bantlar_tanimli_degil(vs):
    for ad in ('specific_impulse', 'gamma', 'chamber_pressure',
               'gas_constant', 'temperature'):
        assert ad not in vs.performance_limits, ad
    for ad in ('port_diameter_initial', 'port_diameter_final',
               'chamber_length'):
        assert ad not in vs.geometry_limits, ad
    for ad in ('reynolds_number', 'exit_velocity'):
        assert ad not in vs.injector_limits, ad
    # Fiziksel taban kalır (yakınsak-ıraksak nozulda ses-üstü çıkış).
    assert vs.geometry_limits['expansion_ratio_supersonic_floor'] == 1.0


def test_gercek_olculmus_motorun_isp_si_uyari_almaz(vs):
    """Carmicino t01: ölçülmüş 147,4 s — eski bant (180-250) uyarıyordu."""
    uyarilar = vs.validate_performance_data({'isp': 147.4}, 'n2o_htpb')
    assert not _kodlar(uyarilar) & {'warn.validation.isp_out_of_range',
                                    'warn.validation.gamma_out_of_range'}


def test_buyuk_motorun_portu_uyari_almaz_zarf_hukmu_kalir(vs):
    """100 kN hibrit: ilk port 100,3 mm — eski bant (5-100 mm) uyarıyordu."""
    kodlar = _kodlar(vs.validate_geometry_data({
        'port_diameter_initial': 0.1003, 'port_diameter_final': 0.40,
        'chamber_diameter': 0.50, 'port_count': 1}))
    assert 'warn.validation.port_initial_out_of_range' not in kodlar
    assert not {k for k in kodlar if 'port_growth' in k}
    # Fiziksel imkânsızlık (port zarfı > oda) hâlâ KRİTİK.
    kritik = vs.validate_geometry_data({
        'port_diameter_initial': 0.05, 'port_diameter_final': 0.60,
        'chamber_diameter': 0.50, 'port_count': 1})
    assert 'warn.validation.port_exceeds_chamber' in _kodlar(kritik)


@pytest.mark.parametrize('gamma, cf, kirmizi', [
    (1.15, 2.40, False),   # CF_sonsuz(1,15) ~ 2,50: fiziksel olarak mümkün
    (1.25, 2.40, True),    # CF_sonsuz(1,25) ~ 2,08: imkânsız
    (1.20, 2.20, False),   # CF_sonsuz(1,20) ~ 2,247
])
def test_cf_ust_siniri_kosunun_gamma_sindan(vs, gamma, cf, kirmizi):
    pc_bar, at = 20.0, 1e-4
    thrust = cf * pc_bar * 1e5 * at
    uyarilar = vs.check_sutton_biblarz_criteria({
        'thrust': thrust, 'throat_area': at, 'chamber_pressure': pc_bar,
        'gamma': gamma})
    cf_uyari = [w for w in uyarilar if w['code'] == 'warn.validation.cf_too_high']
    assert bool(cf_uyari) is kirmizi
    if kirmizi:
        beklenen = ideal_thrust_coefficient(gamma, 0.0, 0.0, 1.0)
        assert cf_uyari[0]['severity'] == 'critical'
        assert cf_uyari[0]['params']['limit'] == pytest.approx(beklenen, abs=5e-4)
        assert cf_uyari[0]['params']['gamma'] == pytest.approx(gamma)


def test_gamma_yoksa_cf_ekseninde_hukum_yok(vs):
    """Sabit γ varsayılmaz: γ okunamıyorsa CF üst sınır hükmü verilmez."""
    uyarilar = vs.check_sutton_biblarz_criteria({
        'thrust': 3.0 * 20.0 * 1e5 * 1e-4, 'throat_area': 1e-4,
        'chamber_pressure': 20.0})
    assert 'warn.validation.cf_too_high' not in _kodlar(uyarilar)


def test_lstar_ve_regresyon_bandi_hukum_vermez(vs):
    kodlar = _kodlar(vs.check_sutton_biblarz_criteria({
        'l_star': 0.2, 'regression_rate': 0.009}))
    assert not kodlar & {'warn.validation.lstar_low', 'warn.validation.lstar_high',
                         'warn.validation.regression_low',
                         'warn.validation.regression_high'}


def test_enjektor_reynolds_ve_hiz_bandi_hukum_vermez(vs):
    kodlar = _kodlar(vs.validate_injector_data(
        {'reynolds_number': 5e5, 'exit_velocity': 150.0,
         'pressure_drop': 6.0}, chamber_pressure=20.0))
    assert not kodlar & {'warn.validation.reynolds_high',
                         'warn.validation.reynolds_laminar',
                         'warn.validation.exit_velocity_out_of_range'}


def test_kalkan_kodlarin_sozluk_anahtari_yok_cf_metni_gammayi_tasir():
    metin = SOZLUK.read_text(encoding='utf-8')
    for kod in KALKAN_KODLAR:
        assert f"'warn.validation.{kod}':" not in metin, kod
    cf = re.findall(r"'warn\.validation\.cf_too_high': '([^\n]*)',", metin)
    assert len(cf) == 2, 'EN + TR beklenir'
    for satir in cf:
        assert '{gamma}' in satir and '{limit}' in satir and '{cf}' in satir
        assert '1.2)' not in satir and '1,2)' not in satir, (
            'sabit γ = 1,2 iddiası metinde kalmış')
