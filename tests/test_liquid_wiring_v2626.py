"""Sıvı motorda DONMUŞ çıktı yapraklarına karşı bekçi (v2.6.26, parti P1).

Kusur sınıfı tek cümleyle: *kullanıcı girdiyi değiştiriyor, ekrandaki sayı
kıpırdamıyor.* v2.6.26 denetiminde ``/calculate_liquid`` yanıtında 47 yaprak
bu durumdaydı — itkiyi 25 kN'den 60 kN'ye, oda basıncını 70 bar'dan 110 bar'a,
O/F'i 2.3'ten 2.9'a çektiğinizde hepsi BİT DÜZEYİNDE aynı kalıyordu:

    tank giriş ağzı 100 mm, çıkış 150 mm, difüzör 200 mm, sump 50 mm,
    emniyet vanası 25 mm, bafl deliği 50 mm, iç yapı kütlesi 23.5 kg,
    karışma süresi 2 ms, yanma verimi %90, momentum optimumu 2.0,
    debi marjı %50, güç marjı %53.846, kinetik kayıp %1.0,
    sprey açısı 30°, O/F verimi %100, optimum irtifa 100 km,
    tank emniyet katsayısı 2.5, film soğutma bloğunun beş yaprağı 0.0

Bu dosya o yaprakların bir daha çivilenmemesini sağlar. Ölçüt §2'deki ile
aynıdır: aynı yaprak, iki FARKLI girdide farklı değer vermelidir. Ayrıca eski
sabitlerin kendisi ADIYLA yasaklanır — bir gün biri "geçici olarak" geri
koyarsa test kırmızıya döner.

Testler motoru DOĞRUDAN kurar (HTTP katmanı ``test_liquid_input_wiring.py``
tarafından zaten ölçülüyor) ve ağa çıkmaz: ``propellant_data`` enjekte edilir.
Şablon sözleşmesi ayrıca kaynak taramasıyla kilitlenir, çünkü film soğutma
girdisinin ölü doğmasının nedeni tam olarak "arka uç okuyor, sayfa
göndermiyor" boşluğuydu.
"""

import contextlib
import io
import pathlib
import re
import warnings

import pytest

from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

warnings.filterwarnings('ignore')

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'

# Ağ yok: motor kurucusuna boş ama VAR olan itici verisi enjekte edilir.
# Ad bilerek bu dosyaya özgüdür: depoda 'PROPELLANT_DATA' adıyla iki farklı
# içerik zaten dolaşıyor (test_liquid_real_inputs.py metan da içeriyor,
# test_liquid_manufacturing_honesty.py içermiyor); üçüncü bir tanım açmak
# yerine bu bekçinin kendi çevrimdışı zeminine ayrı ad verilir.
OFFLINE_PROPELLANTS = {'rp1': {}, 'lox': {}}

# liquid.html varsayılanlarıyla uyumlu taban yük.
BASE = dict(
    fuel_density=810, oxidizer_density=1141,
    mixture_ratio=2.3, combustion_efficiency=97,
    engine_cycle='gas_generator', feed_pressure=105,
    generator_gas_temp=900, turbine_expansion_ratio=4,
    injector_type='impinging', injector_pressure_drop=20,
    discharge_coefficient=0.7, contraction_ratio=4,
    characteristic_length=1.2, chamber_material='inconel_718',
    cooling_type='regenerative', nozzle_expansion_ratio=12,
    nozzle_type='bell_80', safety_factor=2.5,
)

CTOR = dict(thrust=25000, chamber_pressure=70, mixture_ratio=2.3,
            fuel_type='rp1', oxidizer_type='lox',
            propellant_data=OFFLINE_PROPELLANTS)


def _run(**delta):
    """Motoru taban yükün üstüne ``delta`` ile koşar; tam sonucu döner."""
    overrides = dict(BASE)
    ctor = dict(CTOR)
    for key, value in delta.items():
        overrides[key] = value
        if key in ('thrust', 'chamber_pressure', 'mixture_ratio',
                   'cooling_type', 'injector_type'):
            ctor[key] = value
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(overrides=overrides, **ctor)
        return engine.calculate_performance()


# Koşular pahalı (her biri gerçek bir tasarım çözümü); modül başına bir kez.
@pytest.fixture(scope='module')
def base():
    return _run()


@pytest.fixture(scope='module')
def big():
    return _run(thrust=250000)


@pytest.fixture(scope='module')
def rich():
    return _run(mixture_ratio=2.9)


@pytest.fixture(scope='module')
def wide_nozzle():
    return _run(nozzle_expansion_ratio=60)


@pytest.fixture(scope='module')
def coax():
    return _run(injector_type='coaxial')


@pytest.fixture(scope='module')
def filmed():
    return _run(film_cooling_percent=6)


def _leaf(result, path):
    node = result
    for part in path.split('.'):
        if part.endswith(']'):
            part, index = part[:-1].split('[')
            node = node[part][int(index)]
        else:
            node = node[part]
    return node


def _assert_moved(a, b, path, tol=1e-9):
    va, vb = _leaf(a, path), _leaf(b, path)
    assert va is not None and vb is not None, f'{path} boş: {va} / {vb}'
    assert abs(float(va) - float(vb)) > tol * max(abs(float(va)), 1.0), (
        f'{path} iki farklı girdide de {va} — yaprak yine donmuş')


# ---------------------------------------------------------------------------
# 1) Tank iç yapıları: ağızlar, bafllar, kütleler
# ---------------------------------------------------------------------------
TANK_LEAVES = [
    'internal_structures.inlet_configuration.diameter',
    'internal_structures.outlet_configuration.diameter',
    'internal_structures.slosh_baffles[0].hole_diameter',
    'internal_structures.instrumentation.relief_valve.diameter',
    'internal_structures.mass_breakdown.anti_vortex',
    'internal_structures.mass_breakdown.baffles',
    'internal_structures.mass_breakdown.plumbing',
    'internal_structures.mass_breakdown.total_mass',
]


@pytest.mark.parametrize('tank', ['oxidizer_tank', 'fuel_tank'])
@pytest.mark.parametrize('leaf', TANK_LEAVES)
def test_tank_internal_leaf_follows_thrust(base, big, tank, leaf):
    """Tank iç yapısının her kalemi debiyle ölçeklenmeli.

    25 kN ile 250 kN aynı tank ağzını, aynı bafl deliğini ve aynı iç yapı
    kütlesini göremez; eskiden tam olarak öyleydi (100/150/50 mm, 23.5 kg).
    """
    _assert_moved(base, big, f'propellant_tanks.{tank}.{leaf}')


def test_tank_port_diameters_come_from_the_feed_line_model(base):
    """Ağız çapları motorun KENDİ hat modelinden gelmeli (tek kaynak)."""
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(overrides=dict(BASE), **CTOR)
        engine.calculate_nozzle_geometry()
        d_line = engine._calculate_line_diameter(engine.mdot_ox, 'oxidizer')
    outlet = _leaf(base, 'propellant_tanks.oxidizer_tank.internal_structures'
                         '.outlet_configuration.diameter')
    # Tank ağzı hat çapının etiketli katıdır; hattan bağımsız bir sayı değil.
    assert outlet == pytest.approx(d_line * 1000.0 * 1.30, rel=1e-6)
    basis = _leaf(base, 'propellant_tanks.oxidizer_tank.internal_structures'
                        '.outlet_configuration.diameter_basis')
    assert '_calculate_line_diameter' in basis


def test_diffuser_length_is_a_consequence_not_a_choice(base, big):
    """L = (D_çıkış − D_giriş)/(2·tanθ) — eski 200 mm sabiti geri gelmemeli."""
    path = ('propellant_tanks.oxidizer_tank.internal_structures'
            '.inlet_configuration')
    import math
    for result in (base, big):
        inlet = _leaf(result, path)
        expected = ((inlet['diffuser_exit_diameter_mm'] - inlet['diameter'])
                    / 2.0 / math.tan(math.radians(inlet['diffuser_angle'])))
        assert inlet['diffuser_length'] == pytest.approx(expected, rel=1e-9)
        assert inlet['diffuser_length'] != 200
    _assert_moved(base, big, path + '.diffuser_length')


def test_baffle_hole_count_is_dimensionally_consistent(base):
    """Delik sayısı ALAN oranından gelmeli (eski bağıntı [m]/[m²] idi)."""
    import math
    baffle = _leaf(base, 'propellant_tanks.oxidizer_tank.internal_structures'
                         '.slosh_baffles[0]')
    ring = math.pi / 4.0 * ((baffle['outer_diameter'] / 1000.0) ** 2
                            - (baffle['inner_diameter'] / 1000.0) ** 2)
    hole = math.pi / 4.0 * (baffle['hole_diameter'] / 1000.0) ** 2
    achieved = baffle['hole_count'] * hole / ring * 100.0
    assert baffle['open_area_ratio_achieved'] == pytest.approx(achieved,
                                                              rel=1e-9)
    # Hedef ile GERÇEKLENEN artık aynı sayı değil; ikisi de ayrı raporlanıyor.
    assert baffle['open_area_ratio_is_target'] is True
    assert abs(achieved - baffle['open_area_ratio']) < 3.0


def test_internal_structure_mass_is_geometry_times_density(base):
    """Kütleler geometri × materials_db yoğunluğu; sabit pay değil."""
    import math
    from hrma.data.materials_db import get_material_safe
    record, _ = get_material_safe('aluminum_6061')
    rho = float(record['density'])
    internals = _leaf(base, 'propellant_tanks.oxidizer_tank'
                            '.internal_structures')
    breakdown = internals['mass_breakdown']
    assert breakdown['density_kg_m3'] == pytest.approx(rho)

    device = internals['anti_vortex_device']
    expected_av = (device['vane_count'] * device['height']
                   * device['vane_radial_length_mm'] / 1000.0
                   * device['vane_thickness'] / 1000.0 * rho)
    assert breakdown['anti_vortex'] == pytest.approx(expected_av, rel=1e-9)

    baffles = internals['slosh_baffles']
    ring = math.pi / 4.0 * ((baffles[0]['outer_diameter'] / 1000.0) ** 2
                            - (baffles[0]['inner_diameter'] / 1000.0) ** 2)
    solid = ring * (1.0 - baffles[0]['open_area_ratio_achieved'] / 100.0)
    expected_b = (len(baffles) * solid * baffles[0]['thickness'] / 1000.0
                  * rho)
    assert breakdown['baffles'] == pytest.approx(expected_b, rel=1e-9)
    assert breakdown['total_mass'] == pytest.approx(
        breakdown['anti_vortex'] + breakdown['baffles']
        + breakdown['plumbing'], rel=1e-12)

    # Eski sabit döküm (2.5 / 6.0 / 15.0 / 23.5 kg) geri gelmemeli.
    assert breakdown['anti_vortex'] != 2.5
    assert breakdown['plumbing'] != 15.0
    assert breakdown['total_mass'] != 23.5


def test_plate_thicknesses_are_declared_as_gauge_not_load_sized(base):
    """Kalınlıklar SABİT kalıyorsa nedeni açıkça yazmalı (sahte 'boyutlandı' yok).

    Çalkantı yükü (NASA SP-8031) araç eksenel ivmesi ister; bu çözücüde yok.
    Bu yüzden kanat/bafl kalınlığı asgari imalat gauge'idir ve öyle beyan
    edilir — kullanıcı sayının nereden geldiğini görebilmeli.
    """
    internals = _leaf(base, 'propellant_tanks.oxidizer_tank'
                            '.internal_structures')
    device = internals['anti_vortex_device']
    assert device['vane_thickness_load_sized'] is False
    assert 'gauge' in device['vane_thickness_basis']
    baffle = internals['slosh_baffles'][0]
    assert baffle['thickness_load_sized'] is False
    assert 'gauge' in baffle['thickness_basis']
    assert any('SP-8031' in item for item in internals['not_modelled'])


def test_relief_valve_declares_its_sizing_case(base, big):
    """Emniyet vanası çapı bir hesabın sonucu olmalı ve durumu yazmalı."""
    for result in (base, big):
        valve = _leaf(result, 'propellant_tanks.oxidizer_tank'
                              '.internal_structures.instrumentation'
                              '.relief_valve')
        assert valve['diameter'] != 25
        assert valve['required_area_mm2'] > 0
        assert 'API RP 520' in valve['method']
        assert 'not modelled' in valve['sizing_case'].lower() or \
               'NOT modelled' in valve['sizing_case']
        # Ayar basıncı TANK basıncından; eski hâli 1.5 × ODA basıncıydı
        # (3 bar'lık NPSH tankına 105 bar'lık ayar).
        tank_bar = _leaf(result, 'propellant_tanks.oxidizer_tank.structural'
                                 '.pressure_rating')
        assert valve['set_pressure'] == pytest.approx(tank_bar * 1.10,
                                                      rel=1e-6)


def test_tank_safety_factor_follows_the_user_input():
    """Form emniyet katsayısı tank tasarımına ULAŞMALI (eskiden hep 2.5)."""
    soft = _run(safety_factor=1.6)
    hard = _run(safety_factor=3.5)
    for tank in ('oxidizer_tank', 'fuel_tank'):
        assert _leaf(soft, f'propellant_tanks.{tank}.structural'
                           '.safety_factor') == pytest.approx(1.6)
        assert _leaf(hard, f'propellant_tanks.{tank}.structural'
                           '.safety_factor') == pytest.approx(3.5)
        # Katsayı gerçekten cidara gitmeli, yalnız etikete değil.
        t_soft = _leaf(soft, f'propellant_tanks.{tank}.dimensions'
                             '.wall_thickness')
        t_hard = _leaf(hard, f'propellant_tanks.{tank}.dimensions'
                             '.wall_thickness')
        assert t_hard > t_soft or t_soft == t_hard == pytest.approx(3.0)
        assert 'user input' in _leaf(
            soft, f'propellant_tanks.{tank}.structural.safety_factor_source')


# ---------------------------------------------------------------------------
# 2) Yanma odası: karışma süresi, Damköhler, momentum ölçütü, yanma verimi
# ---------------------------------------------------------------------------
def test_mixing_time_is_solved_from_the_injector_jet(base, rich, big):
    """Karışma süresi sabit 2 ms olamaz; jet çapı/hızı ile değişmeli."""
    path = 'combustion_analysis.combustion_analysis.mixing_time'
    assert _leaf(base, path) != 2.0
    _assert_moved(base, rich, path)
    _assert_moved(base, big, path)
    basis = _leaf(base, 'combustion_analysis.combustion_analysis'
                        '.mixing_time_basis')
    assert 'Pilch' in basis and 'injector design model' in basis


def test_damkohler_uses_the_solved_times(base):
    """Da = kalış süresi / atomizasyon süresi — ikisi de gerçek hesap."""
    comb = _leaf(base, 'combustion_analysis.combustion_analysis')
    assert comb['damkohler_number'] == pytest.approx(
        comb['residence_time'] / comb['mixing_time'], rel=1e-9)


def test_combustion_response_time_follows_the_mixing_time(base, rich):
    """Kararlılık bloğundaki tepki süresi de aynı çözümden gelmeli."""
    for result in (base, rich):
        assert _leaf(result, 'combustion_analysis.stability_analysis'
                             '.combustion_response_time') == pytest.approx(
            _leaf(result, 'combustion_analysis.combustion_analysis'
                          '.mixing_time'))
    _assert_moved(base, rich, 'combustion_analysis.stability_analysis'
                              '.combustion_response_time')
    # n-tau modelinin n'i çözülmüyor; bu açıkça söylenmeli.
    assert _leaf(base, 'combustion_analysis.stability_analysis'
                       '.pressure_interaction_index_n') == 'not_modelled'


def test_momentum_criterion_has_a_single_source(base, coax):
    """Hazne analizi kendi momentum 'optimum'unu tanımlamamalı.

    Eskiden hazne 2.0, enjektör paneli 1.0 diyordu — aynı yanıtta iki
    çelişen hedef. Artık ikisi de injector_design momentum düğümünden.
    """
    comb = _leaf(base, 'combustion_analysis.combustion_analysis')
    detail = _leaf(base, 'injection_system.injector_design_detail')
    assert comb['optimal_momentum_ratio'] == pytest.approx(
        detail['momentum']['target'])
    assert comb['momentum_ratio'] == pytest.approx(
        detail['momentum']['momentum_ratio'])
    assert comb['optimal_momentum_ratio'] != 2.0
    assert 'Rupe' in comb['momentum_criterion_basis']
    # Momentum ölçütü olmayan eleman tipinde SAYI UYDURULMAZ.
    coax_comb = _leaf(coax, 'combustion_analysis.combustion_analysis')
    assert coax_comb['optimal_momentum_ratio'] is None
    assert coax_comb['mixing_efficiency'] is None
    assert 'not_modelled' in coax_comb['momentum_criterion_basis']


def test_combustion_efficiency_is_the_user_value_not_a_clamp():
    """Yanma verimi [0.90,0.99] kelepçesine değil, η_c* zincirine bağlı."""
    low = _run(combustion_efficiency=88)
    high = _run(combustion_efficiency=99)
    path = 'combustion_analysis.combustion_analysis.combustion_efficiency'
    assert _leaf(low, path) == pytest.approx(88.0)
    assert _leaf(high, path) == pytest.approx(99.0)
    assert 'user input' in _leaf(
        low, 'combustion_analysis.combustion_analysis'
             '.combustion_efficiency_source')


# ---------------------------------------------------------------------------
# 3) Besleme sistemi marjları ve türbin giriş basıncı
# ---------------------------------------------------------------------------
def test_feed_margins_are_not_algebraic_echoes(base, big):
    """%50 (tarama bandı) ve %53.846 (1/η−1) artefaktları geri gelmemeli."""
    margins = _leaf(base, 'detailed_feed_system.performance_margins')
    assert margins['flow_margin'] != 50.0
    assert margins['power_margin'] != pytest.approx(53.846, abs=1e-2)
    assert 'feed-line' in margins['flow_margin_basis']
    assert 'tip speed' in margins['power_margin_basis']
    _assert_moved(base, big,
                  'detailed_feed_system.performance_margins.flow_margin')


def test_power_margin_follows_the_turbine_work():
    """Güç marjı türbin özgül işiyle değişmeli (TIT ve PR ile)."""
    cool = _run(generator_gas_temp=700)
    hot = _run(generator_gas_temp=1600)
    path = 'detailed_feed_system.performance_margins.power_margin'
    _assert_moved(cool, hot, path)
    # Daha sıcak gaz -> daha büyük özgül iş -> daha AZ marj.
    assert _leaf(hot, path) < _leaf(cool, path)


def test_turbine_inlet_pressure_comes_from_the_cycle_solution(base):
    """İma edilen giriş basıncı çözücünün KENDİ değeri olmalı.

    Eskiden PR × P_atmosfer yazılıyordu: aynı koşuda çevrim çözücüsü 78.8 bar
    derken bu yaprak 4.05 bar diyordu ve arayüz kullanıcının 150 bar'lık
    girdisini o 4.05 bar ile karşılaştırıyordu. Bir gaz jeneratörü türbini
    100 bar'lık pompaları 4 bar'lık gazla süremez.
    """
    turbine = _leaf(base, 'detailed_feed_system.turbopump_analysis.turbine')
    solved = _leaf(base, 'detailed_feed_system.engine_cycle_solution'
                         '.shafts[0].turbine.inlet_pressure_bar')
    assert turbine['inlet_pressure_implied_bar'] == pytest.approx(solved)
    assert turbine['inlet_pressure_implied_bar'] != pytest.approx(
        turbine['pressure_ratio'] * 1.01325)
    # Türbin ana odadan yüksek basınçla beslenmeli.
    assert turbine['inlet_pressure_implied_bar'] > _leaf(base,
                                                         'chamber_pressure')
    # Karşılaştırma tabanı da atmosfer değil, türbinin kendi çıkışı.
    assert turbine['exhaust_pressure_bar'] > 1.5


# ---------------------------------------------------------------------------
# 4) Verim dökümü, sprey açısı, O/F verimi, tasarım irtifası
# ---------------------------------------------------------------------------
def test_kinetic_loss_has_one_source(base, big):
    """Kinetik kayıp teslim zincirinin çözümünden; 0.99/0.96 bayrağı değil."""
    eta = _leaf(base, 'efficiency_breakdown.efficiency_breakdown.kinetic_loss')
    assert eta not in (99.0, 96.0)
    assert 'chain kinetic efficiency' in _leaf(
        base, 'efficiency_breakdown.loss_sources.kinetic_loss')
    _assert_moved(base, big,
                  'efficiency_breakdown.efficiency_breakdown.kinetic_loss')
    # Verim ve kayıp aynı sayının iki yüzü olmalı.
    loss = _leaf(base, 'efficiency_breakdown.loss_breakdown.kinetic_loss')
    assert loss == pytest.approx(100.0 - eta, rel=1e-9)


def test_spray_angle_comes_from_the_injector_model(base, coax):
    """Sprey açısı enjektör tipine göre çözülmeli; her tipte 30° olamaz."""
    assert _leaf(base, 'injector_design.spray_angle_deg') != _leaf(
        coax, 'injector_design.spray_angle_deg')
    assert 'injector design model' in _leaf(
        coax, 'injector_design.spray_angle_source')
    # Swirl elemanda açı modülün kendi koni çözümü.
    assert _leaf(coax, 'injector_design.spray_angle_deg') == pytest.approx(
        _leaf(coax, 'injection_system.injector_design_detail.atomization'
                    '.spray_cone_half_angle_deg'))


def test_impinging_resultant_angle_follows_the_momentum_balance(base, rich):
    """Çarpışmalı elemanda bileşke sprey ekseni momentum dengesiyle sapmalı."""
    import math
    _assert_moved(base, rich, 'injector_design.spray_resultant_angle_deg')
    half = _leaf(base, 'injector_design.spray_angle_deg')
    ratio = _leaf(base, 'injection_system.injector_design_detail.momentum.momentum_ratio')
    expected = math.degrees(math.atan(
        math.tan(math.radians(half)) * (1.0 - ratio) / (1.0 + ratio)))
    assert _leaf(base, 'injector_design.spray_resultant_angle_deg') == \
        pytest.approx(expected, rel=1e-9)


def test_mixture_ratio_efficiency_comes_from_the_real_scan(base, rich):
    """O/F verimi %100'e çivili olamaz; taramanın tepesine göre ölçülmeli."""
    for result in (base, rich):
        maps = _leaf(result, 'performance_maps.mixture_ratio_optimization')
        isp = [v for v in maps['isp_vs_mr'] if isinstance(v, (int, float))]
        expected = maps['current_isp_vac'] / max(isp) * 100.0
        assert maps['mr_efficiency'] == pytest.approx(expected, rel=1e-9)
        # Aynı sayı üst düzeyde de yayımlanmalı (tek kaynak).
        assert _leaf(result, 'mixture_ratio_efficiency') == pytest.approx(
            maps['mr_efficiency'])
    _assert_moved(base, rich, 'mixture_ratio_efficiency')


def test_design_altitude_is_solved_from_the_exit_pressure(base, wide_nozzle):
    """Optimum irtifa P_çıkış = P_ortam çözümü; tarama tavanı (100 km) değil."""
    for result in (base, wide_nozzle):
        alt = _leaf(result, 'performance_maps.altitude_performance'
                            '.optimal_altitude')
        assert alt != 100000.0
        assert 'ISA ambient pressure equals the nozzle exit pressure' in \
            _leaf(result, 'performance_maps.altitude_performance'
                          '.optimal_altitude_basis')
    # Daha büyük genişleme oranı -> daha düşük çıkış basıncı -> daha yüksek
    # tasarım irtifası.
    assert _leaf(wide_nozzle, 'performance_maps.altitude_performance'
                              '.optimal_altitude') > \
        _leaf(base, 'performance_maps.altitude_performance.optimal_altitude')


# ---------------------------------------------------------------------------
# 5) Film soğutma: arayüz -> çözücü -> beş yaprak
# ---------------------------------------------------------------------------
FILM_LEAVES = ['film_cooling_percent', 'film_cooling_flow_kg_s',
               'film_heat_absorbed_w', 'film_covered_length_mm',
               'film_coverage_fraction_of_chamber']


@pytest.mark.parametrize('leaf', FILM_LEAVES)
def test_film_cooling_leaf_responds_to_the_input(base, filmed, leaf):
    """Film bloğunun her yaprağı girdiyle uyanmalı (eskiden hepsi 0.0)."""
    assert _leaf(base, f'cooling_system.film_cooling.{leaf}') == 0.0
    assert _leaf(filmed, f'cooling_system.film_cooling.{leaf}') > 0.0


def test_film_flow_is_the_requested_fraction_of_the_fuel(filmed):
    """ṁ_film = %·ṁ_yakıt; üst düzey özet de aynı sayıyı taşımalı."""
    flow = _leaf(filmed, 'cooling_system.film_cooling.film_cooling_flow_kg_s')
    assert flow == pytest.approx(0.06 * _leaf(filmed, 'fuel_flow'), rel=1e-9)
    assert _leaf(filmed, 'cooling_system.film_cooling_flow') == pytest.approx(
        flow)
    assert 'user input' in _leaf(
        filmed, 'cooling_system.film_cooling.film_cooling_percent_source')


def test_film_cooling_choice_is_not_a_no_op():
    """'Film Cooling' seçmek hiçbir şeyi değiştirmiyor olamaz.

    Kullanıcı soğutma tipini film seçip debi girmezse çözücü etiketli
    literatür varsayılanını uygular ve kaynağını SÖYLER — sessiz sıfır yok.
    """
    result = _run(cooling_type='film_cooling')
    film = _leaf(result, 'cooling_system.film_cooling')
    assert film['film_cooling_percent'] > 0.0
    assert film['film_cooling_flow_kg_s'] > 0.0
    assert 'Huzel' in film['film_cooling_percent_source']
    assert 'not supplied' in film['film_cooling_percent_source']


def test_liquid_page_sends_the_film_cooling_input():
    """Arka uç okuyor + sayfa göndermiyor boşluğu kapanmış olmalı.

    Bu alanın ölü doğmasının nedeni tam olarak buydu: motor
    'film_cooling_percent' override'ını 2026-07-22'den beri okuyordu, ama
    liquid.html hiç göndermiyordu.
    """
    html = LIQUID_HTML.read_text(encoding='utf-8')
    assert 'id="film_cooling_percent"' in html, 'girdi alanı yok'
    body = re.search(r'function collectAllParameters\(\).*?\n        \}',
                     html, re.S)
    assert body, 'collectAllParameters() bulunamadı'
    assert 'film_cooling_percent:' in body.group(0), \
        'alan var ama toplayıcı göndermiyor'
    # Sıfır MEŞRU bir değerdir; `|| 0` kalıbı onu yedek değere düşürürdü.
    assert re.search(r"film_cooling_percent:\s*isFinite\(", body.group(0)), \
        'sıfır güvenli okuma kalıbı yok'
    assert "document.getElementById('film_cooling_percent').value = '0'" in html, \
        'formu sıfırlama alanı unutmuş'


# ---------------------------------------------------------------------------
# 6) Beyan dürüstlüğü: ölçeklenmeyen kalem 'ölçekleniyor' diye yazılmamalı
# ---------------------------------------------------------------------------
def test_controls_mass_is_declared_as_a_fixed_allowance(base, big):
    """Kontrol/aviyonik kütlesi sabit; beyanı da öyle demeli.

    Eski 'mass_method' bu kalemi besleme hattıyla birlikte "empirical scaling
    with mass flow" diye bildiriyordu, oysa değer hiçbir girdiyle değişmiyor.
    Sayının sabit olması sorun değil; SABİT olduğu hâlde 'ölçekleniyor'
    demek beyan çürümesidir.
    """
    method = _leaf(base, 'component_sizing.mass_method')
    assert 'feed_and_controls' not in method, 'iki kalem hâlâ tek satırda'
    assert 'FIXED allowance' in method['controls_avionics']
    assert 'NOT scaled' in method['controls_avionics']
    assert 'scaling with mass flow' in method['feed_system']
    # Beyan gerçeği yansıtmalı: kontrol sabit, besleme hattı ölçekleniyor.
    path = 'component_sizing.component_masses'
    assert _leaf(base, path + '.controls_avionics') == \
        _leaf(big, path + '.controls_avionics')
    _assert_moved(base, big, path + '.feed_system')
