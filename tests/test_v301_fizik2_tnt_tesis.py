"""V301/FİZİK-2 kalem 8 — sıvı TNT eşdeğeri kaynaklı; tesis gereği motor hükmü değil.

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/V301/fizik-2/k8_guvenlik_once.json,
ÖRNEK'in yeni sıvı örneği 5fa435893): LOX/RP-1 25 kN, 30 s, itici 297,45 kg
→ TNT = 0,35 (kaynaksız) × 297,45 = 104,1 kg > 100 kg → patlayıcı ekseni
5,0 → UNACCEPTABLE → ``do_not_proceed`` + ``redesign_required`` (KRİTİK),
yapısal blok SAFE iken.

(a) KAYNAK: 14 CFR Part 420 Appendix E, Table E-5 (CFR 2024 baskısı):
LO2/RP-1 statik test standı %10, fırlatma rampası %20 (500 000 lb'ye kadar)
+ üstü %10; LO2/LH2 büyüğü(8·W^(2/3) lb, %14·W); N2O4/UDMH+N2H4 %5 / %10.
Tabloda olmayan çift/senaryoda eski katsayı "kaynaksız HRMA seçimi" diye.
(b) Patlayıcı/toksik/yangın eksenleri itici MİKTARININ tesis gereğidir:
"güvenlik mesafesi / tesis önlemi gerekli" (uyarı) der, motor hükmünden
ayrı durur; kritik yalnız motorun kendi eksenlerinden (yapısal, basınçlı
kap, termal).
"""
import pathlib

import pytest

from hrma.analysis.safety_analysis import (
    FACILITY_HAZARD_AXES, FACILITY_REQUIREMENT_MEASURES, KG_PER_LB,
    LIQUID_TNT_SOURCE, MOTOR_DESIGN_RISK_AXES, SafetyAnalyzer,
    liquid_biprop_tnt_equivalent)

KOK = pathlib.Path(__file__).resolve().parents[1]
ESKI = 0.35


def _lb(kg):
    return kg / KG_PER_LB


@pytest.mark.parametrize('ox, fu, senaryo, oran', [
    ('lox', 'rp1', 'test_stand', 0.10),
    ('LOX', 'RP-1', 'test_stand', 0.10),
    ('n2o4', 'udmh', 'test_stand', 0.05),
    ('n2o4', 'mmh', 'launch', 0.10),
    ('nto', 'a50', 'launch', 0.10),
])
def test_tablo_e5_sabit_oranli_satirlar(ox, fu, senaryo, oran):
    d = liquid_biprop_tnt_equivalent(ox, fu, senaryo, 300.0, ESKI)
    assert d['status'] == 'sourced'
    assert d['source'] == LIQUID_TNT_SOURCE
    assert d['tnt_equivalent_kg'] == pytest.approx(300.0 * oran, rel=1e-12)


def test_lox_rp1_firlatma_rampasi_kademeli():
    m = 300000.0                       # 661 387 lb > 500 000 lb
    d = liquid_biprop_tnt_equivalent('lox', 'rp1', 'launch', m, ESKI)
    beklenen_lb = 0.20 * 500000.0 + 0.10 * (_lb(m) - 500000.0)
    assert d['tnt_equivalent_kg'] == pytest.approx(beklenen_lb * KG_PER_LB,
                                                   rel=1e-12)
    kucuk = liquid_biprop_tnt_equivalent('lox', 'rp1', 'launch', 300.0, ESKI)
    assert kucuk['tnt_equivalent_kg'] == pytest.approx(60.0, rel=1e-12)


@pytest.mark.parametrize('m_kg', [100.0, 1.0e6])
def test_lox_lh2_not_3(m_kg):
    w = _lb(m_kg)
    beklenen = max(8.0 * w ** (2.0 / 3.0), 0.14 * w) * KG_PER_LB
    for senaryo in ('test_stand', 'launch'):
        d = liquid_biprop_tnt_equivalent('lox', 'lh2', senaryo, m_kg, ESKI)
        assert d['status'] == 'sourced'
        assert d['tnt_equivalent_kg'] == pytest.approx(beklenen, rel=1e-12)


@pytest.mark.parametrize('ox, fu, senaryo', [
    ('lox', 'ch4', 'test_stand'), ('lox', 'kerosene', 'test_stand'),
    ('h2o2', 'rp1', 'test_stand'), (None, None, 'test_stand'),
    ('lox', 'rp1', 'manufacturing'), ('lox', 'rp1', 'transport')])
def test_tabloda_olmayan_kaynaksiz_beyan(ox, fu, senaryo):
    d = liquid_biprop_tnt_equivalent(ox, fu, senaryo, 300.0, ESKI)
    assert d['status'] == 'unsourced_hrma_choice'
    assert d['effective_factor'] == ESKI
    assert d['tnt_equivalent_kg'] == pytest.approx(300.0 * ESKI)
    assert d['reason'] and d['source'] is None


def _analiz(**ek):
    md = {'chamber_pressure': 40.0, 'chamber_diameter': 0.2,
          'wall_thickness': 0.02, 'thrust': 25000.0, 'burn_time': 30.0}
    md.update(ek.pop('md', {}))
    return SafetyAnalyzer().analyze_comprehensive_safety(
        motor_data=md, propellant_type='liquid_biprop', motor_type='liquid',
        material='steel_4130', **ek)


def _kodlar(s, siddet=None):
    return [r['code'] for r in s['recommendations']
            if siddet is None or r.get('severity') == siddet]


def test_buyuk_envanter_tesis_gerekcesi_motor_hukmu_degil():
    s = _analiz(propellant_mass=5000.0, oxidizer_type='lox', fuel_type='rp1')
    ex = s['explosive_hazards']
    assert ex['tnt_equivalent_basis']['status'] == 'sourced'
    assert ex['tnt_equivalent_kg'] == pytest.approx(500.0, rel=1e-12)
    ra = s['risk_assessment']
    assert ra['individual_risks']['explosive'] == 5.0
    fh = ra['facility_hazard']
    assert fh['risk_level'] == 'CRITICAL'
    assert fh['requirement'] == FACILITY_REQUIREMENT_MEASURES
    assert fh['axes_in_highest_class'] == ['explosive']
    # Motor hükmü yalnız motor eksenlerinden; kritik öneri yok.
    motor = [ra['individual_risks'][a] for a in MOTOR_DESIGN_RISK_AXES
             if ra['individual_risks'][a] is not None]
    assert ra['overall_risk_score'] == max(motor)
    assert ra['risk_level'] != 'CRITICAL'
    assert _kodlar(s, 'critical') == []
    assert 'warn.safety.facility_measures_required' in _kodlar(s, 'warning')


def test_motorun_kendi_kusuru_hala_kritik():
    """İnce cidar: yapısal eksen kritik → do_not_proceed yerinde kalır."""
    s = _analiz(propellant_mass=50.0, oxidizer_type='lox', fuel_type='rp1',
                md={'wall_thickness': 0.0002, 'chamber_pressure': 80.0})
    assert s['risk_assessment']['acceptability'] == 'UNACCEPTABLE'
    assert _kodlar(s, 'critical') == ['warn.safety.do_not_proceed',
                                      'warn.safety.redesign_required']


def test_eksen_gruplari_ayrik_ve_tam():
    assert set(MOTOR_DESIGN_RISK_AXES).isdisjoint(FACILITY_HAZARD_AXES)
    s = _analiz(propellant_mass=50.0)
    assert set(s['risk_assessment']['individual_risks']) == set(
        MOTOR_DESIGN_RISK_AXES) | set(FACILITY_HAZARD_AXES)


def test_kimliksiz_sivi_eski_katsayi_kaynaksiz_beyanli():
    s = _analiz(propellant_mass=100.0)
    d = s['explosive_hazards']['tnt_equivalent_basis']
    assert d['status'] == 'unsourced_hrma_choice'
    assert s['explosive_hazards']['tnt_equivalent_kg'] == pytest.approx(35.0)


def test_ekran_anahtarlari_iki_dilde():
    i18n = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    for k in ('warn.safety.facility_measures_required',
              'panel.safety.motorDesignRisk', 'panel.safety.facilityHazard',
              'panel.safety.facilityRequirement', 'panel.safety.tntSourced',
              'panel.safety.tntUnsourced',
              'panel.safety.scenario.static_test_stand',
              'panel.safety.scenario.launch_pad'):
        assert i18n.count("'%s':" % k) == 2, k
    assert 'motor tasarım kusuru değildir' in i18n
