"""P2 BEKÇİSİ: hibrit çıktısındaki sabitlenmiş yapraklar bir daha donmasın.

Bu dosya vaka listelemez, ÖLÇER: her testi bir girdiyi İKİ farklı değerde
koşup çıktının gerçekten değiştiğini doğrular. v2.6.26 denetiminde P2
partisinde ölçülen ve burada kilitlenen kusur sınıfı şudur: **kullanıcı
girdiyi değiştiriyor, çıktı yaprağı kıpırdamıyor.**

Kilitlenen kalemler (ÖNCE -> SONRA, hepsi ölçülmüştür):

* ``nozzle_design.geometry.wall_safety_factor`` 4,0 SABİT -> kullanıcının
  emniyet katsayısı (SF=2 -> 2,0; SF=6 -> 6,0). Cidar kalınlığı da onunla
  ölçekleniyor: 7,791 mm -> 3,895 / 11,686 mm.
* ``nozzle_design.performance.kinetic_efficiency`` 0,995 SABİT (imza
  varsayılanı) -> KineticEfficiency 'engineering' korelasyonu
  (0,9805 taban; ε=16'da 0,9698). Aynı büyüklük sıvı motorda zaten
  hesaplanıyordu; hibritte hiç çağrılmıyordu.
* ``optimum_analysis.analysis.conditions.exit.P`` 1,01325 bar SABİT (deniz
  seviyesi çapası) -> ε'dan çözülen çıkış basıncı (ε=4 -> 0,9567 bar;
  ε=16 -> 0,1613 bar). Aynı kök neden üç yaprağı daha canlandırdı
  (compositions.exit.pressure, stations.exit.pressure,
  isentropic_efficiency 1,0 -> 0,9890/0,9918).
* ``structural_analysis.nozzle_analysis.safety_factor`` ve
  ``end_cap_analysis.head_safety_factor`` malzeme tablosunda kilitliydi ->
  kullanıcının tasarım emniyet katsayısını izliyor.
* ``fastener_analysis.bolt_allowable_stress_MPa`` kaynaksız 400 MPa SABİT ->
  ISO 898-1:2013 Table 3 proof gerilmesi (8.8 -> 580/600 MPa, 12.9 -> 970).
* ``fatigue_analysis.estimated_cycles`` tasarım GİRDİSİNİ (25) geri
  döndürüyordu -> hesaplanan ömür (Pc=80 bar -> 108.146 çevrim;
  Pc=120 bar -> 1.121 çevrim).
* ``cooling_analysis.heat_sink_delta_T_K`` 200 K SABİT -> malzeme sıcaklık
  sınırı eksi başlangıç sıcaklığı (steel_4130 517,85 K; inconel_718
  683,85 K; alüminyum 183,85 K).
* ``injector_design_detail.ox_circuit.cd`` 0,78 SABİT -> orifis L/D'den
  (plaka kalınlığı / çözülen delik çapı) 0,63-0,90 bandında.

NOT (kapsam): plaka kalınlığı ve ortam sıcaklığı motor SINIFINA bağlandı;
``app.py`` bu iki alanı henüz motora geçirmediği için o iki kalem uçtan uca
değil MOTOR SEVİYESİNDE ölçülür (aşağıdaki ilgili testler HybridRocketEngine
üstünden koşar).
"""

import contextlib
import io

import pytest

from tests.test_field_wiring_layer_b import HYBRID_BASE


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------

def _silent(fn, *args, **kwargs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return fn(*args, **kwargs)


def leaf(payload, path):
    """'.a.b.c' yolundaki yaprağı döndürür; yoksa testi anlamlı hatayla düşürür."""
    cur = payload
    for part in path.strip('.').split('.'):
        assert isinstance(cur, dict) and part in cur, f'yol kırık: {path} ({part})'
        cur = cur[part]
    return cur


ENGINE_KW = dict(
    thrust=5000, burn_time=10, chamber_pressure=20, of_ratio=2.5,
    atmospheric_pressure=1.013, l_star=1.0, expansion_ratio=4.0,
    nozzle_type='conical', fuel_type='htpb', oxidizer_type='n2o',
    chamber_material='steel_4130', wall_thickness=0.005, cooling_type='none',
    safety_factor=4.0, nozzle_material='graphite',
    injector_type='showerhead', tank_temperature=293,
)


def run_engine(**overrides):
    """Motor sınıfını doğrudan koşar (HTTP katmanı olmadan, hızlı)."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine

    def _go():
        return HybridRocketEngine(**dict(ENGINE_KW, **overrides)).calculate()

    return _silent(_go)


@pytest.fixture(scope='module')
def calc():
    """/calculate koşularını paylaşan önbellekli koşucu (koşu pahalıdır)."""
    from hrma.app import app

    client = app.test_client()
    cache = {}

    def _run(**overrides):
        key = tuple(sorted(overrides.items()))
        if key not in cache:
            response = _silent(
                client.post, '/calculate',
                json=dict(HYBRID_BASE, **overrides),
                headers={'Host': '127.0.0.1:8080'},
            )
            assert response.status_code == 200, \
                f'/calculate HTTP {response.status_code}: {response.get_json()}'
            cache[key] = response.get_json()
        return cache[key]

    return _run


# Aynı lüle sözlüğünün yanıtta sergilendiği DÖRT yol. Bir onarım dördünü de
# kapatmalıdır; biri kopar ve fark edilmezse kusur geri gelir.
NOZZLE_GEOMETRY_PATHS = (
    '.motor.nozzle_design.geometry',
    '.motor.nozzle_geometry',
    '.openrocket.flight_profile.motor_data.nozzle_design.geometry',
    '.openrocket.flight_profile.motor_data.nozzle_geometry',
)
NOZZLE_PERFORMANCE_PATHS = (
    '.motor.nozzle_design.performance',
    '.openrocket.flight_profile.motor_data.nozzle_design.performance',
    '.trajectory.motor_data.nozzle_design.performance',
)


# ---------------------------------------------------------------------------
# Lüle cidarı: emniyet katsayısı ve malzeme
# ---------------------------------------------------------------------------

class TestNozzleWall:

    def test_wall_safety_factor_follows_user_input(self, calc):
        """Kullanıcının emniyet katsayısı lüle cidarına ULAŞMALI (4 yaprakta)."""
        low = calc(safety_factor=2.0)
        high = calc(safety_factor=6.0)
        for path in NOZZLE_GEOMETRY_PATHS:
            assert leaf(low, path + '.wall_safety_factor') == pytest.approx(2.0), path
            assert leaf(high, path + '.wall_safety_factor') == pytest.approx(6.0), path

    def test_wall_thickness_scales_with_safety_factor(self, calc):
        """t = SF·p·r/σ olduğundan SF üç katına çıkınca kalınlık üç katına çıkar."""
        low = calc(safety_factor=2.0)
        high = calc(safety_factor=6.0)
        for path in NOZZLE_GEOMETRY_PATHS:
            t_low = leaf(low, path + '.wall_thickness')
            t_high = leaf(high, path + '.wall_thickness')
            assert t_high == pytest.approx(3.0 * t_low, rel=1e-6), (
                f'{path}: SF 2->6 kalınlığı {t_low:.4f} -> {t_high:.4f} mm '
                f'yaptı, 3 kat bekleniyordu')

    def test_wall_material_reaches_the_nozzle(self, calc):
        """Lüle malzemesi yoğunluk ve akma dayanımını gerçekten değiştirmeli."""
        graphite = calc()
        tungsten = calc(nozzle_material='tungsten')
        for path in NOZZLE_GEOMETRY_PATHS:
            rho_g = leaf(graphite, path + '.wall_material_density')
            rho_w = leaf(tungsten, path + '.wall_material_density')
            sig_g = leaf(graphite, path + '.wall_yield_strength')
            sig_w = leaf(tungsten, path + '.wall_yield_strength')
            assert rho_w > rho_g * 5, f'{path}: {rho_g} -> {rho_w} kg/m3'
            assert sig_w != sig_g, f'{path}: akma dayanımı {sig_g} sabit kaldı'
        assert leaf(tungsten, NOZZLE_GEOMETRY_PATHS[0] + '.wall_material_source') \
            == 'caller'


# ---------------------------------------------------------------------------
# Kinetik verim: sıvı motorla aynı model hibritte de koşmalı
# ---------------------------------------------------------------------------

class TestKineticEfficiency:

    SIGNATURE_DEFAULT = 0.995   # design_nozzle imza varsayılanı (eski sabit)

    def test_kinetic_efficiency_is_computed_not_defaulted(self, calc):
        base = calc()
        for path in NOZZLE_PERFORMANCE_PATHS:
            eta = leaf(base, path + '.kinetic_efficiency')
            assert eta != pytest.approx(self.SIGNATURE_DEFAULT), (
                f'{path}: imza varsayılanı 0,995 geri geldi — kinetik model '
                f'çağrılmıyor')
            assert 0.9 < eta <= 1.0, f'{path}: eta={eta} fiziksel bantta değil'
        diag = leaf(base, '.motor.nozzle_design.performance.kinetic')
        assert diag['model'].startswith('kinetic_efficiency'), diag
        assert diag['isp_frozen_s'] < diag['isp_predicted_s'] <= diag['isp_shifting_s']

    def test_kinetic_efficiency_responds_to_expansion_ratio(self, calc):
        """Genişleme oranı büyüdükçe kinetik kayıp artar (donmuşa yaklaşılır)."""
        small = calc()                       # eps = 4
        large = calc(expansion_ratio=16.0)   # eps = 16
        for path in NOZZLE_PERFORMANCE_PATHS:
            eta_small = leaf(small, path + '.kinetic_efficiency')
            eta_large = leaf(large, path + '.kinetic_efficiency')
            assert eta_large != pytest.approx(eta_small), (
                f'{path}: ε 4->16 kinetik verimi {eta_small} değiştirmedi')


# ---------------------------------------------------------------------------
# Optimum O/F araması: genişleme oranını görmeli
# ---------------------------------------------------------------------------

class TestOptimumSearchSeesExpansionRatio:

    SEA_LEVEL_BAR = 1.01325

    EXIT_PRESSURE_PATHS = (
        '.motor.optimum_analysis.analysis.conditions.exit.P',
        '.motor.optimum_analysis.analysis.compositions.exit.pressure',
        '.motor.optimum_analysis.analysis.performance.'
        'thermodynamic_properties.stations.exit.pressure',
    )

    def test_exit_pressure_is_not_anchored_to_sea_level(self, calc):
        base = calc()
        for path in self.EXIT_PRESSURE_PATHS:
            value = leaf(base, path)
            assert value != pytest.approx(self.SEA_LEVEL_BAR, rel=1e-9), (
                f'{path}: optimum O/F araması hâlâ deniz seviyesine çapalı')

    def test_exit_pressure_and_efficiency_follow_expansion_ratio(self, calc):
        small = calc()
        large = calc(expansion_ratio=16.0)
        for path in self.EXIT_PRESSURE_PATHS:
            p_small = leaf(small, path)
            p_large = leaf(large, path)
            assert p_large < 0.5 * p_small, (
                f'{path}: ε 4->16 çıkış basıncını {p_small} -> {p_large} '
                f'yaptı; büyük genişlemede belirgin düşüş beklenir')
        eta_path = ('.motor.optimum_analysis.analysis.performance.'
                    'thermodynamic_properties.isentropic_efficiency')
        assert leaf(small, eta_path) < 1.0
        assert leaf(large, eta_path) != pytest.approx(leaf(small, eta_path))


# ---------------------------------------------------------------------------
# Yapısal: tek tasarım emniyet katsayısı
# ---------------------------------------------------------------------------

class TestStructuralSafetyFactorWiring:

    SF_PATHS = (
        '.motor.structural_analysis.nozzle_analysis.safety_factor',
        '.motor.structural_analysis.end_cap_analysis.head_safety_factor',
        '.motor.structural_analysis.safety_analysis.safety_factors.nozzle',
        '.motor.structural_analysis.safety_analysis.safety_factors.end_cap',
        '.motor.structural_analysis.fastener_analysis.bolt_safety_factor',
    )

    def test_one_design_safety_factor_for_every_component(self, calc):
        low = calc(safety_factor=2.0)
        high = calc(safety_factor=6.0)
        for path in self.SF_PATHS:
            assert leaf(low, path) == pytest.approx(2.0), path
            assert leaf(high, path) == pytest.approx(6.0), path

    def test_thrust_reaches_the_buckling_check(self, calc):
        small = calc()
        big = calc(thrust=30000)
        path = '.motor.structural_analysis.buckling_analysis'
        assert leaf(small, path + '.axial_compression_force_N') == pytest.approx(5000.0)
        assert leaf(big, path + '.axial_compression_force_N') == pytest.approx(30000.0)
        s_small = leaf(small, path + '.applied_axial_stress_unpressurized_MPa')
        s_big = leaf(big, path + '.applied_axial_stress_unpressurized_MPa')
        assert s_small > 0.0 and s_big > s_small, (
            f'itki 5 -> 30 kN eksenel gerilmeyi {s_small} -> {s_big} yaptı')


class TestFastenerAllowableFromStandard:
    """Cıvata izin verilen gerilmesi ISO 898-1 tablosundan gelmeli."""

    def test_allowable_is_the_iso_proof_stress(self, calc):
        from hrma.analysis.bolted_joint import _bolt_class_props

        base = calc()
        fa = leaf(base, '.motor.structural_analysis.fastener_analysis')
        expected = _bolt_class_props(fa['bolt_property_class'],
                                     fa['required_bolt_diameter'])['S_p'] / 1e6
        assert fa['bolt_allowable_stress_MPa'] == pytest.approx(expected)
        assert fa['bolt_allowable_stress_MPa'] != pytest.approx(400.0), \
            'kaynaksız 400 MPa sabiti geri geldi'
        assert 'ISO 898-1' in fa['bolt_allowable_stress_basis']

    def test_allowable_follows_the_bolt_class(self):
        """Sınıf değişince izin verilen gerilme ve gerekli çap değişmeli."""
        from hrma.analysis.structural_analysis import StructuralAnalyzer

        analyzer = StructuralAnalyzer()
        motor = dict(chamber_pressure=20.0, chamber_diameter=0.1526,
                     chamber_length=0.6, throat_diameter=0.0487,
                     nozzle_type='conical', burn_time=10.0,
                     chamber_temperature=1900.0, thrust=5000.0)
        seen = {}
        for bolt_class in ('8.8', '10.9', '12.9', 'A2-70'):
            result = analyzer.analyze_structure(
                dict(motor, bolt_property_class=bolt_class),
                material='steel_4130', design_safety_factor=4.0)
            fa = result['fastener_analysis']
            seen[bolt_class] = (fa['bolt_allowable_stress_MPa'],
                                round(fa['required_bolt_diameter'], 4))
        assert len({v[0] for v in seen.values()}) == 4, seen
        assert seen['12.9'][1] < seen['8.8'][1] < seen['A2-70'][1], seen


class TestFatigueEstimatedCycles:
    """'Tahmini çevrim' alanı tasarım girdisini değil, hesabı taşımalı."""

    def _fatigue(self, pressure, thickness):
        from hrma.analysis.structural_analysis import StructuralAnalyzer

        motor = dict(chamber_pressure=pressure, chamber_diameter=0.1526,
                     chamber_length=0.6, throat_diameter=0.0487,
                     nozzle_type='conical', burn_time=10.0,
                     chamber_temperature=1900.0, thrust=5000.0)
        return StructuralAnalyzer().analyze_structure(
            motor, material='steel_4130', design_safety_factor=4.0,
            actual_wall_thickness=thickness)['fatigue_analysis']

    def test_estimated_cycles_is_the_computed_life(self):
        mild = self._fatigue(20.0, 0.005)
        harsh = self._fatigue(150.0, 0.002)
        assert mild['estimated_cycles'] == mild['estimated_life']
        assert harsh['estimated_cycles'] == harsh['estimated_life']
        assert mild['estimated_cycles'] != harsh['estimated_cycles'], (
            'yorulma ömrü basınçla değişmedi — alan yine girdiyi yansıtıyor')
        assert isinstance(harsh['estimated_cycles'], float)
        # Tasarım girdisi ayrı alanda durmalı (karıştırılmasın)
        assert mild['design_cycles'] == 25

    def test_design_cycles_input_no_longer_leaks_into_the_estimate(self):
        """design_cycles değişince 'tahmin' DEĞİŞMEMELİ (artık tahmin çünkü)."""
        from hrma.analysis.structural_analysis import StructuralAnalyzer

        analyzer = StructuralAnalyzer()
        args = dict(stress=200.0, burn_time=10.0,
                    mat_props=analyzer.materials['steel_4130'])
        few = analyzer._analyze_fatigue(design_cycles=5, **args)
        many = analyzer._analyze_fatigue(design_cycles=500, **args)
        assert few['estimated_cycles'] == many['estimated_cycles']
        assert few['design_cycles'] != many['design_cycles']


# ---------------------------------------------------------------------------
# Isı yutucu: izin verilen sıcaklık artışı malzemeden gelmeli
# ---------------------------------------------------------------------------

class TestHeatSinkDeltaT:

    def _cooling(self, material, ambient):
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer

        motor = dict(chamber_pressure=20.0, chamber_temperature=1900.0,
                     chamber_diameter=0.1526, chamber_length=0.6,
                     burn_time=10.0, mdot_total=1.5, throat_diameter=0.0487,
                     c_star=1325.0, gamma=1.2378, molecular_weight=20.94)
        return HeatTransferAnalyzer().analyze_heat_transfer(
            motor, material=material, wall_thickness=0.005,
            ambient_temp=ambient, cooling_type='natural')['cooling_analysis']

    def test_delta_T_follows_material_temperature_limit(self):
        steel = self._cooling('steel_4130', 293.15)
        inconel = self._cooling('inconel_718', 293.15)
        aluminium = self._cooling('aluminum_6061', 293.15)
        values = {steel['heat_sink_delta_T_K'], inconel['heat_sink_delta_T_K'],
                  aluminium['heat_sink_delta_T_K']}
        assert len(values) == 3, f'ΔT malzemeyle değişmedi: {values}'
        assert 200.0 not in values, 'sabit 200 K geri geldi'
        # Sıcaklığa daha dayanıklı malzeme daha HAFİF ısı yutucu ister
        assert inconel['heat_sink_mass'] < steel['heat_sink_mass'] \
            < aluminium['heat_sink_mass']
        assert 'material record' in steel['heat_sink_delta_T_basis']

    def test_delta_T_follows_initial_temperature(self):
        cold = self._cooling('steel_4130', 233.15)
        warm = self._cooling('steel_4130', 313.15)
        assert cold['heat_sink_delta_T_K'] > warm['heat_sink_delta_T_K']
        assert cold['heat_sink_mass'] < warm['heat_sink_mass']

    def test_missing_limit_falls_back_and_declares_it(self):
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer

        delta_t, limit, basis = HeatTransferAnalyzer()._heat_sink_delta_T(
            {'specific_heat': 500.0}, 293.15)
        assert delta_t == 200.0
        assert 'declared default' in basis
        assert limit != limit          # NaN: sınır yok, uydurulmadı


# ---------------------------------------------------------------------------
# Enjektör: Cd geometriden, buhar basıncı akışkandan
# ---------------------------------------------------------------------------

class TestInjectorDischargeCoefficient:
    """Cd, orifis L/D'sinden çözülmeli (plaka kalınlığı / delik çapı)."""

    def test_cd_follows_plate_thickness(self):
        thin = run_engine(plate_thickness=0.001)['injector_design_detail']
        thick = run_engine(plate_thickness=0.020)['injector_design_detail']
        cd_thin = thin['ox_circuit']['cd']
        cd_thick = thick['ox_circuit']['cd']
        assert cd_thin < cd_thick, (
            f'plaka 1 mm -> 20 mm Cd {cd_thin} -> {cd_thick} (artmalıydı: '
            f'kısa orifiste vena contracta hakim)')
        assert thin['ox_circuit']['l_over_d'] < thick['ox_circuit']['l_over_d']
        assert 'orifice length' in thick['ox_circuit']['l_over_d_basis']
        # Cd doğrudan enjeksiyon alanına girer: A = mdot/(Cd*sqrt(2 rho dP))
        assert thin['ox_circuit']['total_area_mm2'] > \
            thick['ox_circuit']['total_area_mm2']

    def test_cd_follows_inlet_geometry(self):
        sharp = run_engine(plate_thickness=0.003)['injector_design_detail']
        radiused = run_engine(plate_thickness=0.003,
                              orifice_inlet='radiused')['injector_design_detail']
        assert radiused['ox_circuit']['cd'] > sharp['ox_circuit']['cd']

    def test_vapour_pressure_is_fluid_specific(self):
        from hrma.engines.injector_design import liquid_vapor_pressure

        lox, lox_basis = liquid_vapor_pressure('lox', 90.19)
        rp1, _ = liquid_vapor_pressure('rp1', 293.15)
        generic, generic_basis = liquid_vapor_pressure('generic', None)
        assert lox == pytest.approx(1.01325)      # NBP'de doymuş depolama
        assert rp1 < 0.01                          # düşük uçuculuk
        assert generic == 0.05 and 'generic' in generic_basis
        assert 'table value' in lox_basis

    def test_vapour_pressure_reaches_the_cavitation_number(self):
        """P_v, Nurick K_c = (P1-Pv)/(P1-P2) üzerinden çıktıya girmeli."""
        from hrma.engines.injector_design import design_injector

        spec = dict(motor_type='liquid', injector_type='impinging_doublet',
                    mdot_ox=2.0, mdot_fuel=1.0, rho_ox=1140.0, rho_fuel=800.0,
                    Pc_bar=20.0, dp_ratio_ox=0.2, dp_ratio_fuel=0.2)
        unknown = design_injector(spec)['ox_circuit']
        lox = design_injector(dict(spec, fluid_ox='lox'))['ox_circuit']
        assert unknown['vapor_pressure_bar'] == 0.05
        assert lox['vapor_pressure_bar'] == pytest.approx(1.01325)
        assert lox['cavitation_number'] < unknown['cavitation_number'], (
            'LOX doyma basıncı kavitasyon sayısını DÜŞÜRMELİ (risk artar)')


# ---------------------------------------------------------------------------
# Ortam sıcaklığı: iki modül aynı sayıyı görmeli
# ---------------------------------------------------------------------------

class TestAmbientTemperatureSingleSource:

    def _captured_struct_input(self, **overrides):
        """Yapısal modüle giden sözlüğü yakalar (motor koşusu sırasında)."""
        from hrma.analysis.structural_analysis import StructuralAnalyzer

        captured = {}
        original = StructuralAnalyzer.analyze_structure

        def spy(self, motor_data, *args, **kwargs):
            captured['motor_data'] = dict(motor_data)
            return original(self, motor_data, *args, **kwargs)

        StructuralAnalyzer.analyze_structure = spy
        try:
            result = run_engine(**overrides)
        finally:
            StructuralAnalyzer.analyze_structure = original
        return result, captured['motor_data']

    def test_heat_and_structural_see_the_same_ambient(self):
        result, struct_input = self._captured_struct_input()
        heat_ambient = leaf(
            result, '.heat_transfer_analysis.design_parameters.ambient_temperature')
        assert struct_input['ambient_temperature'] == pytest.approx(heat_ambient), (
            f'ısı modülü {heat_ambient} K, yapısal modül '
            f'{struct_input["ambient_temperature"]} K görüyor')

    def test_user_ambient_reaches_both_modules(self):
        result, struct_input = self._captured_struct_input(
            ambient_temperature=233.15)
        heat_ambient = leaf(
            result, '.heat_transfer_analysis.design_parameters.ambient_temperature')
        assert heat_ambient == pytest.approx(233.15)
        assert struct_input['ambient_temperature'] == pytest.approx(233.15)
        # Isı yutucu kütlesi de bu sıcaklıktan etkilenir (aynı zincir)
        assert leaf(result, '.heat_transfer_analysis.cooling_analysis'
                            '.heat_sink_initial_temperature_K') == \
            pytest.approx(233.15)


# ---------------------------------------------------------------------------
# Daralma oranı: kullanıcının değeri yakınsak kontura ulaşmalı
# ---------------------------------------------------------------------------

def test_contraction_ratio_reaches_the_contour(calc):
    """Aynı yanıtta iki farklı daralma oranı bulunmamalı."""
    user = calc(combustion_type='finite', contraction_ratio=8.0)
    for path in ('.motor.nozzle_design.contour.convergent.contraction_ratio',
                 '.motor.nozzle_contour.convergent.contraction_ratio'):
        assert leaf(user, path) == pytest.approx(8.0, rel=1e-6), path
    auto = calc()
    assert leaf(auto, '.motor.nozzle_contour.convergent.contraction_ratio') \
        != pytest.approx(2.25), 'eski A_c/A_t = 2.25 varsayımı geri geldi'
