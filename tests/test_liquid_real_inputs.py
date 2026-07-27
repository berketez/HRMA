"""Sıvı motor girdi bağlantısı bekçisi (2026-07-19 uydurma denetimi).

Denetimin en ağır bulgusu: ``/calculate_liquid`` formundaki ~55 sayısal
alanın HİÇBİRİ ``LiquidRocketEngine``'e ulaşmıyordu. Kullanıcı L*, genişleme
oranı, kanal sayısı, enjektör ΔP, emniyet katsayısı, malzeme, yanma süresi
giriyor; sonuç imzasının tek hanesi bile değişmiyordu. Ayrıca üç blok
tamamen sabit sözlük döndürüyordu:

  * ``_calculate_thermal_protection_system`` -> 180 kanal / 2x3 mm / 15 m/s /
    800 K / 50 MW/m2 / 8 bar / 150 K (aynı motorun GERÇEK Bartz hesabı
    80 kanal / ~81 MW/m2 / 0.035 bar / 390 K diyordu),
  * ``_generate_performance_optimization_maps`` -> gömülü tepe değerlere
    (RP-1/LOX 353/1823, diğer HER çift 350/1800) uydurma parabol,
  * ``_calculate_efficiency_breakdown`` -> sabit 7 kalem, her motorda %90.

Bu dosya o sınıfın geri gelmesini engeller. Ölçüt tektir:

    "Kullanıcı bu sayının kendi girdisinden hesaplandığına inanır mı?
     İnanıyorsa, girdiyi değiştirince sayı DEĞİŞMELİDİR."

Not: motor kurucusuna ``propellant_data`` enjekte edilir — testler ağa
çıkmaz (v2.5.0 çevrimdışı garantisi).
"""

import io
import contextlib
import warnings

import pytest

from hrma.engines.liquid_rocket_engine import (
    LiquidRocketEngine,
    NOZZLE_TYPE_GEOMETRY,
    BURN_TIME_DEFAULT_S,
)

warnings.filterwarnings('ignore')

PROPELLANT_DATA = {'rp1': {}, 'lox': {}, 'methane': {}}

# liquid.html collectAllParameters() ile aynı varsayılan değerler.
FORM_DEFAULTS = dict(
    fuel_density=815, oxidizer_density=1141, fuel_viscosity=0.0012,
    oxidizer_viscosity=0.00019, fuel_heat_capacity=2090,
    fuel_thermal_conductivity=0.145, fuel_boiling_point=500,
    combustion_efficiency=97, of_max_isp=2.577, of_max_thrust=2.27,
    of_min=2.0, of_max=3.2, feed_pressure=130, turbopump_efficiency=75,
    generator_gas_temp=1000, turbine_inlet_pressure=150,
    turbine_expansion_ratio=4, injector_elements=100,
    fuel_injection_velocity=25, oxidizer_injection_velocity=40,
    fuel_orifice_diameter=2.0, oxidizer_orifice_diameter=2.5,
    injector_pressure_drop=20, discharge_coefficient=0.7,
    characteristic_length=1.2, contraction_ratio=4,
    chamber_wall_thickness=5, chamber_material='steel_304',
    chamber_roughness=3.2, nozzle_expansion_ratio=50, nozzle_type='bell_80',
    cooling_channels=80, coolant_flow_percent=100, coolant_inlet_temp=300,
    max_wall_temp=800, max_burn_duration=400, safety_factor=2.5,
    engine_life_cycles=10, engine_cycle='gas_generator',
)


def run_engine(overrides=None, **ctor):
    """Sessiz koşu: motor bol miktarda tanı çıktısı basıyor."""
    params = dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
                  fuel_type='rp1', oxidizer_type='lox',
                  propellant_data=PROPELLANT_DATA)
    params.update(ctor)
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(overrides=overrides, **params)
        return engine, engine.calculate_performance()


def signature(result):
    """Kullanıcının ekranda gördüğü sayıların düz imzası."""
    tp = result['thermal_protection']
    st = result['structural_analysis']['chamber_structure']
    eb = result['efficiency_breakdown']
    ds = result['design_summary']['masses']
    fs = result['feed_system']['pressure_drops']
    pump = result['detailed_feed_system']['turbopump_analysis']['oxidizer_pump']
    turbine = result['detailed_feed_system']['turbopump_analysis']['turbine']
    inj = result['injection_system']
    return {
        'isp_sl': result['isp_sea_level'], 'isp_vac': result['isp_vacuum'],
        'c_star': result['c_star'], 'expansion_ratio': result['expansion_ratio'],
        'throat_d': result['throat_diameter'], 'exit_d': result['exit_diameter'],
        'chamber_d': result['chamber_diameter'],
        'chamber_l': result['chamber_length'],
        'channels': tp['cooling_channels'],
        'coolant_velocity': tp['coolant_velocity'],
        'heat_flux': tp['heat_flux'], 'coolant_dp': tp['pressure_drop'],
        'coolant_dT': tp['temperature_rise'],
        'coolant_exit_T': tp['coolant_exit_temperature'],
        'wall_temp': tp['wall_temperature'],
        'wall_thickness': st['wall_thickness'], 'hoop': st['hoop_stress'],
        'margin': st['stress_margin'], 'safety_factor': st['safety_factor'],
        'material': st['material'],
        'cycles': result['structural_analysis']['design_requirements']['thermal_cycles'],
        'efficiency': eb['overall_efficiency'],
        'divergence_loss': eb['loss_breakdown']['divergence_loss'],
        'heat_loss': eb['loss_breakdown']['heat_transfer_loss'],
        'engine_mass': ds['engine_mass_kg'],
        'propellant_mass': ds['propellant_mass_kg'],
        'twr': ds['thrust_to_weight'],
        'feed_total': fs['total_ox'], 'feed_lines': fs['feed_lines'],
        'feed_injector': fs['injector'],
        'pump_head': pump['design_head'], 'pump_rpm': pump['rotational_speed'],
        'pump_eta': pump['design_efficiency'],
        'pump_power': pump['design_power'],
        'turbine_T': turbine['inlet_temperature'],
        'turbine_pr': turbine['pressure_ratio'],
        'turbine_tip': turbine['blade_tip_speed'],
        'elements': inj['number_of_elements'],
        'injector_dp': inj['ox_pressure_drop'],
        'orifice_d': inj['ox_orifice_diameter'],
        'map_isp_first': result['performance_maps'][
            'mixture_ratio_optimization']['isp_vs_mr'][0],
        'map_mr_first': result['performance_maps'][
            'mixture_ratio_optimization']['mr_range'][0],
        'vacuum_optimised_isp': result['isp_vacuum_optimized'],
        'burn_time': result['burn_time'],
        'tank_volume': result['propellant_tanks']['system_summary']['total_volume'],
    }


def differences(base, other):
    diff = []
    for key, value in base.items():
        new = other[key]
        if isinstance(value, str):
            if value != new:
                diff.append(key)
        elif abs(float(value) - float(new)) > 1e-9:
            diff.append(key)
    return diff


@pytest.fixture(scope='module')
def baseline():
    _, result = run_engine(dict(FORM_DEFAULTS))
    return signature(result)


# ---------------------------------------------------------------------------
# 1) Her bağlanan girdi çıktıyı GERÇEKTEN değiştirmeli
# ---------------------------------------------------------------------------

SENSITIVITY_CASES = [
    ('characteristic_length', 3.0),
    ('contraction_ratio', 12),
    ('nozzle_expansion_ratio', 12),
    ('nozzle_type', 'conical'),
    ('injector_pressure_drop', 40),
    ('discharge_coefficient', 0.4),
    ('injector_elements', 400),
    ('cooling_channels', 300),
    ('coolant_flow_percent', 50),
    ('coolant_inlet_temp', 120),
    ('max_wall_temp', 1100),
    ('chamber_roughness', 50.0),
    ('chamber_material', 'inconel_718'),
    ('chamber_wall_thickness', 12),
    ('safety_factor', 6.0),
    ('max_burn_duration', 40),
    ('turbopump_efficiency', 55),
    ('generator_gas_temp', 800),
    ('turbine_expansion_ratio', 12),
    ('combustion_efficiency', 80),
    ('fuel_density', 1100),
    ('oxidizer_density', 900),
    ('fuel_viscosity', 0.02),
    ('oxidizer_viscosity', 0.004),
    ('fuel_heat_capacity', 3500),
    # ('of_max_isp', 3.6) KALDIRILDI (2026-07-23): optimum karışım oranı artık
    # GİRDİ değil, ÇIKTI. Çözücü gerçek Pc'de CEA taraması yapıp maksimum
    # vakum Isp'sini veren O/F'yi hesaplıyor (RP-1/LOX 2.62, LH2/LOX 4.09,
    # metan/LOX 3.23 — literatürle uyumlu). Elle girilen değer hesabı
    # etkileyemez, bu yüzden formdan da kaldırıldı ve sonuç panelinde
    # hesaplanmış değer gösteriliyor. Ölü girdi bırakmak yerine girdiyi
    # kaldırmak: bkz. liquid.html "Optimal O/F (computed)".
    ('of_min', 1.0),
    ('engine_life_cycles', 900),
]


@pytest.mark.parametrize('field,value', SENSITIVITY_CASES)
def test_form_input_changes_the_result(baseline, field, value):
    """Formdaki her bağlı alan sonucu değiştirmeli (ölü girdi yasak)."""
    overrides = dict(FORM_DEFAULTS)
    overrides[field] = value
    _, result = run_engine(overrides)
    changed = differences(baseline, signature(result))
    assert changed, (
        f"'{field}' girdisi {value} yapildiginda sonuc imzasinin HICBIR "
        f"hanesi degismedi — girdi yine cope gidiyor.")


def test_pressure_fed_uses_the_feed_pressure_input():
    """Basınç beslemeli çevrimde 'feed pressure' tank basıncıdır."""
    overrides = dict(FORM_DEFAULTS, engine_cycle='pressure_fed')
    _, low = run_engine(dict(overrides, feed_pressure=130))
    _, high = run_engine(dict(overrides, feed_pressure=300))
    low_feed = low['detailed_feed_system']
    high_feed = high['detailed_feed_system']
    assert low_feed['tank_pressure_bar'] == 130
    assert high_feed['tank_pressure_bar'] == 300
    assert high_feed['tank_pressure_margin_bar'] > \
        low_feed['tank_pressure_margin_bar']


def test_no_overrides_keeps_the_reference_chain():
    """Override YOKKEN Isp/c* zinciri sabit kalmalı (taban kilidi).

    Korelasyon koşucusu ve UQ adaptörü motoru override'sız kurar; bu testin
    kırılması korelasyon istatistiklerinin kaydığı anlamına gelir.

    TABAN GÜNCELLENDİ (2026-07-23, v2.6.0 CEA entegrasyonu). Eski değerler
    (isp_sl 311.758, isp_vac 353.153, c* 1823.16) Pc=100 bar'a demirli statik
    tablodan ve SABİT eps=200 vakum referansından geliyordu; yani hiçbir
    gerçek lüleye ait değildi. Yeni zincir yanmayı GERÇEK (Pc, O/F) noktasında
    RocketCEA ile çözüyor ve Isp'yi motorun KENDİ genişleme oranında veriyor.

    Varsayılan motor: RP-1/LOX, Pc=100 bar, O/F=2.5, F=10 kN, ortam-eşlenik
    lüle -> eps=13.22, T_c=3707 K, gamma=1.148. Bu değerler literatürle
    tutarlıdır (RP-1/LOX c* ~1780-1830 m/s; Merlin-1D deniz seviyesi teslim
    Isp 282 s @ eps=16, ideal ~300 s — Sutton & Biblarz 9. baskı Böl. 5).
    c* yalnız %0.8 kaydı (1823 -> 1809); asıl fark Isp'nin artık gerçek
    lülede çözülmesinden geliyor. Değişimin doğruluğa etkisi ölçüldü:
    gerçek motorlara karşı vakum Isp medAPE %8.9 -> %1.0
    (bkz. tests/test_correlation_guards.py).
    """
    _, plain = run_engine(None)
    assert plain['isp_sea_level'] == pytest.approx(298.371, abs=1e-2)
    assert plain['isp_vacuum'] == pytest.approx(323.590, abs=1e-2)
    assert plain['c_star'] == pytest.approx(1808.88, abs=1e-1)
    assert plain['burn_time_source'].startswith('assumed')
    assert plain['burn_time'] == BURN_TIME_DEFAULT_S


def test_out_of_range_input_warns_instead_of_silent_fallback():
    """Aralık dışı girdi sessizce yutulmaz; uyarı üretir."""
    _, result = run_engine(dict(FORM_DEFAULTS, safety_factor=99.0))
    assert result['structural_analysis']['chamber_structure'][
        'safety_factor'] != 99.0
    # v2.6.2 D-track: input_warnings artik {code, params, severity} sozlugu.
    # Metin yerine KOD + parametre sinanir (dilden bagimsiz, saglam).
    warns = result['input_warnings']
    hit = [w for w in warns
           if isinstance(w, dict)
           and w.get('code') == 'warn.liquid.input_out_of_range'
           and (w.get('params') or {}).get('field') == 'safety_factor']
    assert hit, warns


def test_unwired_inputs_are_declared():
    """Bağlanmayan alanlar açıkça listelenmeli (UI orada devre dışı bırakır)."""
    _, result = run_engine(dict(FORM_DEFAULTS))
    unwired = result['unwired_inputs']
    assert 'throat_diameter' in unwired['reported_for_comparison']
    assert 'engine_start_time' in unwired['transient_not_modelled']
    # Bağlanan bir alan listede kalmamalı
    flat = {name for group in unwired.values() for name in group}
    for wired in ('characteristic_length', 'cooling_channels',
                  'safety_factor', 'nozzle_expansion_ratio',
                  'injector_pressure_drop', 'chamber_material'):
        assert wired not in flat, f"{wired} artik bagli, listeden cikarilmali"


# ---------------------------------------------------------------------------
# 2) Soğutma tasarımı sabit sözlük olamaz
# ---------------------------------------------------------------------------

def test_cooling_design_tracks_thrust_and_pressure():
    """Isıl koruma kartı itki/basınçla değişmeli (eski hali bire bir sabitti)."""
    _, small = run_engine(dict(FORM_DEFAULTS), thrust=10000,
                          chamber_pressure=100)
    _, big = run_engine(dict(FORM_DEFAULTS), thrust=250000,
                        chamber_pressure=200)
    a = small['thermal_protection']
    b = big['thermal_protection']
    assert a['heat_flux'] != b['heat_flux']
    assert a['coolant_velocity'] != b['coolant_velocity']
    assert a['pressure_drop'] != b['pressure_drop']
    assert a['temperature_rise'] != b['temperature_rise']
    # Eski sabitler geri gelmemeli
    assert a['cooling_channels'] != 180 or b['cooling_channels'] != 180
    assert a['heat_flux'] != 50


def test_thermal_protection_agrees_with_the_cooling_solver():
    """Isıl koruma kartı ile soğutma çözümü AYNI sayıları göstermeli."""
    engine, result = run_engine(dict(FORM_DEFAULTS))
    cooling = result['cooling_system']
    tps = result['thermal_protection']
    assert tps['cooling_channels'] == cooling['cooling_channels']
    assert tps['coolant_velocity'] == pytest.approx(
        cooling['coolant_velocity'])
    assert tps['pressure_drop'] == pytest.approx(
        cooling['cooling_pressure_drop'])
    assert tps['temperature_rise'] == pytest.approx(
        cooling['coolant_temperature_rise'])
    # kW/m2 -> MW/m2
    assert tps['heat_flux'] == pytest.approx(
        cooling['peak_heat_flux'] / 1000.0)


# ---------------------------------------------------------------------------
# 3) Performans haritaları gerçek çözücüden gelmeli
# ---------------------------------------------------------------------------

def test_optimisation_map_follows_the_propellant_pair():
    """Harita yakıt çiftine göre değişmeli (eski kod 350/1800 sabitine düşüyordu)."""
    _, rp1 = run_engine(dict(FORM_DEFAULTS), fuel_type='rp1')
    _, methane = run_engine(dict(FORM_DEFAULTS), fuel_type='methane')
    a = rp1['performance_maps']['mixture_ratio_optimization']
    b = methane['performance_maps']['mixture_ratio_optimization']
    assert max(a['isp_vs_mr']) != pytest.approx(max(b['isp_vs_mr']), rel=1e-3)
    assert max(a['cstar_vs_mr']) != pytest.approx(max(b['cstar_vs_mr']),
                                                  rel=1e-3)


def test_optimisation_map_matches_the_reported_design_point():
    """Haritanın tepesi sayfanın üstündeki Isp ile çelişemez."""
    for fuel in ('rp1', 'methane'):
        _, result = run_engine(dict(FORM_DEFAULTS), fuel_type=fuel)
        maps = result['performance_maps']['mixture_ratio_optimization']
        peak = max(v for v in maps['isp_vs_mr'] if v is not None)
        assert peak == pytest.approx(result['isp_vacuum'], rel=0.05), (
            f"{fuel}: harita tepesi {peak:.1f} s ile raporlanan vakum Isp "
            f"{result['isp_vacuum']:.1f} s celisiyor")


def test_chamber_pressure_map_is_a_real_scan():
    """Pc haritası sabit bir çarpandan değil, yeniden koşulan çözücüden gelmeli."""
    _, result = run_engine(dict(FORM_DEFAULTS))
    pc_map = result['performance_maps']['chamber_pressure_optimization']
    assert len(set(pc_map['throat_diameter_vs_pc_mm'])) > 1
    assert pc_map['thrust_vs_pc'][0] != pc_map['thrust_vs_pc'][-1]


# ---------------------------------------------------------------------------
# 4) Verim dökümü türetilmiş olmalı
# ---------------------------------------------------------------------------

def test_efficiency_breakdown_follows_the_nozzle_contour():
    """Sapma kaybı nozul tipiyle (çıkış açısıyla) değişmeli."""
    losses = {}
    for nozzle in ('conical', 'bell_80', 'bell_60'):
        _, result = run_engine(dict(FORM_DEFAULTS, nozzle_type=nozzle))
        losses[nozzle] = result['efficiency_breakdown'][
            'loss_breakdown']['divergence_loss']
    assert len(set(losses.values())) == 3, losses
    # lambda = (1+cos theta)/2 -> daha büyük çıkış açısı daha büyük kayıp
    assert losses['conical'] > losses['bell_60'] > losses['bell_80']


def test_efficiency_breakdown_is_not_the_old_fixed_table():
    """Eski sabit tablo (2.5/1.5/1.0/2.0/1.5/0.5/1.0 -> %90) geri gelmemeli."""
    _, small = run_engine(dict(FORM_DEFAULTS), thrust=10000,
                          chamber_pressure=100)
    _, big = run_engine(dict(FORM_DEFAULTS), thrust=250000,
                        chamber_pressure=200)
    a = small['efficiency_breakdown']
    b = big['efficiency_breakdown']
    assert a['loss_breakdown'] != b['loss_breakdown']
    assert a['overall_efficiency'] != 90.0
    assert a['loss_sources']  # her kalem kaynağını beyan etmeli
    assert set(a['loss_sources']) == set(a['loss_breakdown'])


# ---------------------------------------------------------------------------
# 5) Yapısal analiz: malzeme kütüphanesi + gerçek marj
# ---------------------------------------------------------------------------

def test_structural_material_label_matches_the_used_strength():
    """Etiket ile kullanılan akma dayanımı aynı kayıttan gelmeli."""
    from hrma.data.materials_db import get_material
    _, result = run_engine(dict(FORM_DEFAULTS, chamber_material='inconel_718'))
    chamber = result['structural_analysis']['chamber_structure']
    record = get_material('inconel_718')
    assert chamber['material'] == record['name']
    assert chamber['yield_strength'] == pytest.approx(
        record['yield_strength'] / 1e6)
    # 250 MPa'lik eski sahte deger geri gelmemeli
    assert chamber['yield_strength'] > 900.0


def test_stress_margin_is_not_tautologically_zero():
    """Marj artık tanım gereği 0 değil (kalınlık standarda yuvarlanıyor)."""
    _, result = run_engine(dict(FORM_DEFAULTS, chamber_material='inconel_718',
                                chamber_wall_thickness=None))
    chamber = result['structural_analysis']['chamber_structure']
    assert chamber['stress_margin'] != 0.0
    assert chamber['wall_thickness'] >= chamber['required_wall_thickness']


def test_safety_factor_input_reaches_the_wall():
    """Emniyet katsayısı kalınlığı ve marjı gerçekten değiştirmeli."""
    overrides = dict(FORM_DEFAULTS)
    overrides.pop('chamber_wall_thickness')
    _, low = run_engine(dict(overrides, safety_factor=1.5))
    _, high = run_engine(dict(overrides, safety_factor=6.0))
    a = low['structural_analysis']['chamber_structure']
    b = high['structural_analysis']['chamber_structure']
    assert b['allowable_stress'] < a['allowable_stress']
    assert b['required_wall_thickness'] > a['required_wall_thickness']


# ---------------------------------------------------------------------------
# 6) Kütle ve yanma süresi
# ---------------------------------------------------------------------------

def test_engine_mass_comes_from_geometry_not_a_50_kg_floor():
    _, small = run_engine(dict(FORM_DEFAULTS), thrust=2000)
    _, big = run_engine(dict(FORM_DEFAULTS), thrust=200000)
    m_small = small['design_summary']['masses']['engine_mass_kg']
    m_big = big['design_summary']['masses']['engine_mass_kg']
    assert m_small != 50
    assert m_big > m_small
    # Tek kaynak: bileşen dökümüyle birebir aynı olmalı
    assert m_small == pytest.approx(
        small['component_sizing']['component_masses']['total_dry_mass'])


def test_propellant_mass_uses_the_entered_burn_time():
    _, short = run_engine(dict(FORM_DEFAULTS, max_burn_duration=25))
    _, long = run_engine(dict(FORM_DEFAULTS, max_burn_duration=250))
    a = short['design_summary']['masses']
    b = long['design_summary']['masses']
    assert a['burn_time_s'] == 25
    assert b['propellant_mass_kg'] == pytest.approx(
        a['propellant_mass_kg'] * 10.0, rel=1e-6)
    assert a['burn_time_source'].startswith('user input')


def test_missing_burn_time_is_labelled_as_an_assumption():
    overrides = dict(FORM_DEFAULTS)
    overrides.pop('max_burn_duration')
    _, result = run_engine(overrides)
    assert result['design_summary']['masses']['burn_time_source'].startswith(
        'assumed')


# ---------------------------------------------------------------------------
# 7) Besleme sistemi
# ---------------------------------------------------------------------------

def test_feed_line_drops_are_computed_from_the_flow():
    """Hat kayıpları debi/çap/yoğunlukla değişmeli (eski hali sabitti)."""
    _, small = run_engine(dict(FORM_DEFAULTS), thrust=5000)
    _, big = run_engine(dict(FORM_DEFAULTS), thrust=250000)
    a = small['feed_system']['pressure_drops']
    b = big['feed_system']['pressure_drops']
    assert a['feed_lines'] != b['feed_lines']
    assert a['tank_outlet'] != b['tank_outlet']
    # Eski sabitler
    assert a['feed_lines'] != 1.2 and a['tank_outlet'] != 0.1


def test_feed_injector_drop_matches_the_injector_design():
    """Enjektör ΔP tek kaynaktan gelmeli (eskiden 3.0 bar vs 22 bar)."""
    _, result = run_engine(dict(FORM_DEFAULTS))
    drops = result['feed_system']['pressure_drops']
    assert drops['injector'] == pytest.approx(
        result['injection_system']['ox_pressure_drop'])


def test_turbopump_curves_scale_with_the_engine():
    """Pompa devri/uç hızı motor boyutuyla değişmeli (25000 rpm sabiti gitti)."""
    _, small = run_engine(dict(FORM_DEFAULTS), thrust=5000)
    _, big = run_engine(dict(FORM_DEFAULTS), thrust=500000)
    a = small['detailed_feed_system']['turbopump_analysis']
    b = big['detailed_feed_system']['turbopump_analysis']
    assert a['oxidizer_pump']['impeller_tip_speed'] != \
        b['oxidizer_pump']['impeller_tip_speed']
    assert a['oxidizer_pump']['rotational_speed'] != \
        b['oxidizer_pump']['rotational_speed']
    assert b['oxidizer_pump']['design_power'] > \
        a['oxidizer_pump']['design_power']
    assert a['oxidizer_pump']['head_curve'] != b['oxidizer_pump']['head_curve']


# ---------------------------------------------------------------------------
# 8) Vakum optimize Isp: dayanaksız 1.05 çarpanı gitti
# ---------------------------------------------------------------------------

def test_vacuum_optimised_isp_is_re_solved():
    _, result = run_engine(dict(FORM_DEFAULTS))
    assert result['isp_vacuum_optimized'] != pytest.approx(
        result['isp_vacuum'] * 1.05, rel=1e-6)
    assert 're-solved' in result['vacuum_optimized_isp_method']
    # Daha büyük vakum lülesi daha yüksek Isp vermeli
    assert result['isp_vacuum_optimized'] > result['isp_vacuum']


def test_expansion_ratio_input_moves_the_performance():
    """Genişleme oranı Isp'yi gerçekten değiştirmeli (eskiden etkisizdi)."""
    _, small = run_engine(dict(FORM_DEFAULTS, nozzle_expansion_ratio=8))
    _, large = run_engine(dict(FORM_DEFAULTS, nozzle_expansion_ratio=60))
    assert small['expansion_ratio'] == 8
    assert large['expansion_ratio'] == 60
    assert large['isp_vacuum'] > small['isp_vacuum']
    assert small['isp_sea_level'] != large['isp_sea_level']


def test_nozzle_type_geometry_table_is_complete():
    """Form seçenekleri ile motorun tanıdığı nozul tipleri aynı olmalı."""
    form_options = {'conical', 'bell_80', 'bell_60', 'aerospike', 'dual_bell'}
    assert form_options == set(NOZZLE_TYPE_GEOMETRY)
    # Modellenmeyen konturlar açıkça işaretlenmeli
    assert NOZZLE_TYPE_GEOMETRY['aerospike']['modelled'] is False
    assert NOZZLE_TYPE_GEOMETRY['bell_80']['modelled'] is True
