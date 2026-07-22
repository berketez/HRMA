"""v2.5.2 fizik düzeltmeleri doğrulama testleri.

Kapsanan düzeltmeler (D1 dalgası):

  1. TERMAL -3115 K BUGI (heat_transfer_analysis._analyze_wall_temperature)
     Cidar iletim düşümü, MUHAFAZAKÂR TASARIM akısıyla (boğazda ~35 MW/m²)
     hesaplanıp DENGE cidar sıcaklığından çıkarılıyordu. İki büyüklük farklı
     termal duruma ait olduğundan dış cidar mutlak sıfırın altına düşüyordu
     (Pc=60 bar, 8 mm çelik -> -3076 K). Artık düşüm, denge çözümünün fiilen
     taşıdığı akıdan hesaplanır: q_eq = (T_iç - T_ortam)/R_toplam.

  2. TERMAL GERİLME (heat_transfer_analysis._analyze_thermal_safety)
     Sabit çelik değerleri (alpha=12e-6, E=200e9, akma=250e6) ve tam-kısıtlı
     E·alpha·(T-293) formu yerine, SEÇİLEN malzemenin özellikleriyle klasik
     cidar-içi gradyan formu: sigma = E·alpha·dT/(2(1-nu)).

  3. YAPISAL TERMAL HOOP (structural_analysis._thermal_hoop_stress)
     "Konservatiflik" adına düşürülmeyen 2 faktörü geri kondu; cidar sıcaklığı
     bilinmediğinde iç yüz artık servis sınırının tamamında değil
     WALL_TEMP_SERVICE_FRACTION katında varsayılır.

  4. L* GEOMETRİYE YANSIYOR (hybrid_rocket_engine)
     Kamara boyu = L_grain + ön-yanma + art-yanma; art-yanma L* hacminden
     çözülür. Ayrıca gerçekleşen L* raporlanır (hibritte port hacmi büyük
     olduğundan düşük L* istekleri geometrik olarak sağlanamaz).

  5. OPTİMUM O/F SESSİZ VARSAYILANI (utils/optimum_of_ratio)
     Tabloda olmayan yakıt/oksitleyici çiftinde sessiz 7.0 yerine ValueError.

  6. PLOTLY bdata (regression_analysis, trajectory_analysis)
     Plotly 6.x numpy dizisini base64 'bdata' olarak yazıyor; uygulamadaki
     plotly.js 1.58.5 bunu çizemiyor (boş grafik). Diziler listeye çevrildi.

  7. ISA TEKİLLEŞTİRME (constants.isa_pressure / isa_temperature)

Koşum:
    cd <depo kökü>
    MPLBACKEND=Agg python3 -m pytest tests/test_v252_physics.py -q
"""

import json
import warnings

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.regression_analysis import RegressionAnalyzer
from hrma.analysis.structural_analysis import (StructuralAnalyzer,
                                               WALL_TEMP_SERVICE_FRACTION)
from hrma.constants import ISA_LAYERS, isa_pressure, isa_temperature
from hrma.utils.optimum_of_ratio import OptimumOFRatioFinder

AMBIENT = 293.15


@pytest.fixture(scope='module')
def heat():
    return HeatTransferAnalyzer()


@pytest.fixture(scope='module')
def struct():
    return StructuralAnalyzer()


# ----------------------------------------------------------------------
# 1. Cidar sıcaklığı fiziksel bantta (negatif Kelvin YOK)
# ----------------------------------------------------------------------
# (Pc [bar], cidar kalınlığı [m], malzeme, soğutma)
WALL_CASES = [
    (60.0, 0.008, 'steel_4130', 'natural'),    # rapor edilen -3076 K vakası
    (20.0, 0.005, 'steel_4130', 'natural'),
    (20.0, 0.010, 'steel', 'forced'),
    (100.0, 0.003, 'copper', 'regenerative'),
    (206.0, 0.001, 'copper', 'regenerative'),
    (5.0, 0.002, 'aluminum_6061', 'natural'),
    (50.0, 0.015, 'inconel_718', 'forced'),
]


class TestWallTemperatureBounded:

    @pytest.mark.parametrize('pc,thickness,material,cooling', WALL_CASES)
    def test_outer_wall_between_ambient_and_inner(self, heat, pc, thickness,
                                                  material, cooling):
        md = {
            'chamber_pressure': pc, 'chamber_temperature': 3200,
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'burn_time': 10, 'mdot_total': 1.0,
        }
        r = heat.analyze_heat_transfer(md, material=material,
                                       wall_thickness=thickness,
                                       ambient_temp=AMBIENT,
                                       cooling_type=cooling)
        w = r['wall_analysis']
        T_in, T_out = w['inner_temperature'], w['outer_temperature']
        assert np.isfinite(T_in) and np.isfinite(T_out)
        assert T_out > 0.0, f"Non-physical (<=0 K) outer wall: {T_out:.0f} K"
        assert AMBIENT - 1e-6 <= T_out <= T_in + 1e-6, (
            f"Outer wall {T_out:.0f} K outside [{AMBIENT:.0f}, {T_in:.0f}] K")

    def test_reported_bug_case_no_longer_negative(self, heat):
        """Bildirilen vaka: Pc=60 bar, 8 mm çelik -> eskiden -3076 K."""
        md = {
            'chamber_pressure': 60.0, 'chamber_temperature': 3200,
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'burn_time': 10, 'mdot_total': 1.0,
        }
        r = heat.analyze_heat_transfer(md, material='steel_4130',
                                       wall_thickness=0.008,
                                       ambient_temp=AMBIENT,
                                       cooling_type='natural')
        w = r['wall_analysis']
        assert w['outer_temperature'] > AMBIENT
        # Eski hata: tasarım akısı * R_iletim = 3000+ K düşüş.
        assert w['temperature_drops']['conduction'] < (
            w['inner_temperature'] - AMBIENT + 1e-6)

    def test_conduction_drop_uses_equilibrium_flux_not_design_flux(self, heat):
        """Denge akısı tasarım akısından KÜÇÜK; tasarım akısı korunmalı."""
        md = {
            'chamber_pressure': 60.0, 'chamber_temperature': 3200,
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'burn_time': 10, 'mdot_total': 1.0,
        }
        r = heat.analyze_heat_transfer(md, material='steel_4130',
                                       wall_thickness=0.008,
                                       cooling_type='natural')
        w = r['wall_analysis']
        assert w['equilibrium_heat_flux'] < w['design_heat_flux']
        # Tasarım (boğaz) akısı raporlarda AYNEN kalır — yanma-delinmesi
        # tehlikesi maskelenmemeli.
        assert r['gas_side_analysis']['throat_heat_flux'] == pytest.approx(
            w['design_heat_flux'], rel=1e-12)
        R = w['thermal_resistance']
        assert w['temperature_drops']['conduction'] == pytest.approx(
            w['equilibrium_heat_flux'] * R['conduction'], rel=1e-9)


# ----------------------------------------------------------------------
# 2. Termal gerilme malzemeden gelir ve makul bantta
# ----------------------------------------------------------------------
class TestThermalStressFromMaterial:

    def _run(self, heat, material):
        md = {
            'chamber_pressure': 20.0, 'chamber_temperature': 3200,
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'burn_time': 10, 'mdot_total': 1.0,
        }
        return heat.analyze_heat_transfer(md, material=material,
                                          wall_thickness=0.005,
                                          cooling_type='regenerative')

    def test_material_properties_are_reported_and_material_specific(self, heat):
        steel = self._run(heat, 'steel_4130')['safety_analysis']
        copper = self._run(heat, 'copper')['safety_analysis']
        ps, pc_ = steel['thermal_stress_properties'], copper['thermal_stress_properties']
        assert ps['elastic_modulus_GPa'] != pytest.approx(pc_['elastic_modulus_GPa'])
        assert ps['thermal_expansion_per_K'] != pytest.approx(
            pc_['thermal_expansion_per_K'])
        # Eski sabitler (çelik) artık her malzemeye uygulanmıyor.
        assert pc_['elastic_modulus_GPa'] != pytest.approx(200.0, abs=1e-6)

    def test_stress_matches_gradient_formula(self, heat):
        r = self._run(heat, 'steel_4130')
        s = r['safety_analysis']
        p = s['thermal_stress_properties']
        w = r['wall_analysis']
        dT = w['inner_temperature'] - w['outer_temperature']
        expected = (p['elastic_modulus_GPa'] * 1e9
                    * p['thermal_expansion_per_K'] * dT
                    / (2.0 * (1.0 - p['poisson_ratio']))) / 1e6
        assert s['thermal_stress'] == pytest.approx(expected, rel=1e-9)
        assert s['thermal_stress_delta_T_K'] == pytest.approx(dT, rel=1e-9)

    def test_stress_no_longer_absurd(self, heat):
        """Eski tam-kısıtlı form GPa mertebesi veriyordu (SF ~ 0.04)."""
        s = self._run(heat, 'steel_4130')['safety_analysis']
        assert s['thermal_stress'] < 2000.0, 'thermal stress still absurd (GPa)'
        assert s['stress_safety_factor'] > 0.1


class TestStructuralThermalHoop:

    def test_classic_surface_formula_restored(self, struct):
        mat = struct.materials['steel_4130']
        out = struct._thermal_hoop_stress(mat, 400.0)
        expected = (mat['elastic_modulus'] * mat['thermal_expansion'] * 400.0
                    / (2.0 * (1.0 - mat['poisson_ratio'])))
        assert out['thermal_hoop_stress'] == pytest.approx(expected, rel=1e-12)

    def test_wall_temperature_contract_is_honoured(self, struct):
        md = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
              'chamber_diameter': 0.1, 'chamber_length': 0.5,
              'throat_diameter': 0.03, 'nozzle_type': 'conical',
              'burn_time': 10.0,
              'wall_temperature_hot': 900.0, 'wall_temperature_cold': 400.0}
        res = struct.analyze_structure(md, material='steel_4130')
        ta = res['thermal_analysis']
        assert ta['wall_temperature_inner_K'] == pytest.approx(900.0)
        assert ta['wall_temperature_outer_K'] == pytest.approx(400.0)

    def test_fallback_wall_temperature_uses_service_fraction(self, struct):
        md = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
              'chamber_diameter': 0.1, 'chamber_length': 0.5,
              'throat_diameter': 0.03, 'nozzle_type': 'conical',
              'burn_time': 10.0}
        res = struct.analyze_structure(md, material='steel_4130')
        expected = (struct.materials['steel_4130']['max_service_temp']
                    * WALL_TEMP_SERVICE_FRACTION)
        assert res['thermal_analysis']['wall_temperature_inner_K'] == pytest.approx(
            expected, abs=1.0)

    def test_ordinary_hybrid_with_real_wall_temperatures_is_not_critical(
            self, heat, struct):
        """Isı modülünden gelen GERÇEK cidar sıcaklıklarıyla 20 bar sıradan
        hibrit çelik kamara makul SF bandına döner (eski: her sıcak motor
        SF<1 -> CRITICAL)."""
        md = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
              'chamber_diameter': 0.1, 'chamber_length': 0.5,
              'throat_diameter': 0.03, 'nozzle_type': 'conical',
              'burn_time': 10.0, 'mdot_total': 1.0}
        h = heat.analyze_heat_transfer(dict(md), material='steel_4130',
                                       wall_thickness=0.005,
                                       cooling_type='natural')
        w = h['wall_analysis']
        md['wall_temperature_hot'] = w['inner_temperature']
        md['wall_temperature_cold'] = w['outer_temperature']
        res = struct.analyze_structure(md, material='steel_4130')
        sf = res['chamber_analysis']['von_mises_safety_factor']
        assert sf > 1.0, f"von Mises SF {sf:.2f} still below 1"
        assert sf < 50.0, f"von Mises SF {sf:.2f} implausibly optimistic"


# ----------------------------------------------------------------------
# 3. L* geometriye yansıyor
# ----------------------------------------------------------------------
def _engine(**kwargs):
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    params = dict(thrust=1000, burn_time=10, of_ratio=6.0,
                  chamber_pressure=20.0, track_performance=False,
                  uq_mode=True)
    params.update(kwargs)
    return HybridRocketEngine(**params)


class TestLStarGeometry:

    def test_chamber_length_is_sum_of_sections(self):
        e = _engine(l_star=4.0)
        r = e.calculate()
        assert r['chamber_length'] == pytest.approx(
            r['grain_length'] + r['pre_chamber_length']
            + r['post_chamber_length'], rel=1e-9)

    def test_chamber_length_grows_with_l_star(self):
        """L* etkin bantta (geometrik tabanın üstünde) boyu ARTIRIR."""
        base = _engine(l_star=4.0).calculate()
        taller = _engine(l_star=6.0).calculate()
        assert taller['chamber_length'] > base['chamber_length'] * 1.02
        assert taller['post_chamber_length'] > base['post_chamber_length']

    def test_low_l_star_reports_achieved_value(self):
        """Hibritte port hacmi büyüktür: düşük L* isteği sağlanamaz ve
        SESSİZ kalınmaz — gerçekleşen L* ve not raporlanır."""
        r = _engine(l_star=1.0).calculate()
        assert r['l_star'] == pytest.approx(1.0)
        assert r['l_star_achieved'] > r['l_star']
        assert 'achieved' in r['l_star_note'].lower()

    def test_l_star_1_to_2_changes_chamber_volume_reporting(self):
        """1.0 -> 2.0 aralığı geometrik tabanın altında kalabilir; bu durumda
        boy sabit kalır ama istenen/gerçekleşen L* farkı raporlanır."""
        a = _engine(l_star=1.0).calculate()
        b = _engine(l_star=2.0).calculate()
        assert b['chamber_length'] >= a['chamber_length']
        assert b['l_star_achieved'] == pytest.approx(a['l_star_achieved'],
                                                     rel=1e-6)
        assert b['l_star_note'] and a['l_star_note']


class TestEngineInputWiring:

    def test_initial_port_diameter_is_used_directly(self):
        e = _engine(initial_port_diameter=0.04)
        e.calculate()
        assert e.D_port_initial == pytest.approx(0.04, rel=1e-12)

    def test_injector_type_reaches_injector_design(self):
        r = _engine(injector_type='pintle').calculate()
        assert r['injector_design']['injector_type'] == 'pintle'

    def test_tank_temperature_changes_injector_sizing(self):
        cold = _engine(tank_temperature=263.15).calculate()['injector_design']
        warm = _engine(tank_temperature=303.15).calculate()['injector_design']
        assert cold['total_injector_area_mm2'] != pytest.approx(
            warm['total_injector_area_mm2'], rel=1e-3)


# ----------------------------------------------------------------------
# 4. Optimum O/F: sessiz varsayılan yok
# ----------------------------------------------------------------------
class TestOptimumOFNoSilentDefault:

    def test_unknown_pair_raises(self):
        finder = OptimumOFRatioFinder()
        with pytest.raises(ValueError) as exc:
            finder.find_optimum_hybrid('n2o', 'abs')
        msg = str(exc.value)
        assert 'No optimum O/F data' in msg
        assert 'N2O' in msg and 'ABS' in msg

    def test_unknown_liquid_pair_raises(self):
        finder = OptimumOFRatioFinder()
        with pytest.raises(ValueError):
            finder.find_optimum_liquid('n2o4', 'ethanol')

    def test_known_pair_still_works(self):
        finder = OptimumOFRatioFinder()
        out = finder.find_optimum_hybrid('n2o', 'htpb')
        assert 6.0 < out['optimum_of_ratio'] < 9.0

    def test_combustion_analyzer_reports_english_error(self):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        with pytest.raises(ValueError) as exc:
            CombustionAnalyzer().find_optimum_of_ratio(
                {'unobtainium': 100.0}, 'n2o', 20.0)
        assert 'Unsupported fuel key' in str(exc.value)


# ----------------------------------------------------------------------
# 5. Plotly JSON'unda bdata yok (numpy -> liste)
# ----------------------------------------------------------------------
class TestPlotlyNoBdata:

    @pytest.fixture(scope='class')
    def regression_data(self):
        ra = RegressionAnalyzer()
        return ra, ra.analyze_regression_vs_time({
            'burn_time': 10.0, 'mdot_ox': 0.5, 'chamber_length': 0.4,
            'port_diameter_initial': 0.03, 'fuel_type': 'htpb'})

    def test_regression_plot_has_no_bdata(self, regression_data):
        ra, data = regression_data
        payload = json.loads(ra.create_regression_plot(data))
        assert 'bdata' not in json.dumps(payload)
        for trace in payload['data']:
            assert isinstance(trace['x'], list)
            assert isinstance(trace['y'], list)

    def test_regression_plot_has_no_fixed_width(self, regression_data):
        ra, data = regression_data
        payload = json.loads(ra.create_regression_plot(data))
        assert 'width' not in payload['layout']

    def test_fuel_comparison_plot_has_no_bdata(self, regression_data):
        ra, _ = regression_data
        payload = ra.compare_fuel_types({
            'burn_time': 10.0, 'mdot_ox': 0.5, 'chamber_length': 0.4})
        assert 'bdata' not in payload

    def test_trajectory_plot_has_no_bdata(self):
        from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
        t = TrajectoryAnalyzer()
        motor = {'thrust': 2000, 'burn_time': 8, 'total_impulse': 16000,
                 'isp': 220, 'propellant_mass_total': 8.0}
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            res = t.calculate_trajectory(motor, {'launch_angle': 85})
            payload = t.create_trajectory_plots(res)
        assert 'bdata' not in payload
        # Sabit figür genişliği kaldırıldı (template içindeki iz-seviyesi
        # 'width' anahtarları sayılmaz; yalnız üst seviye bakılır).
        assert 'width' not in json.loads(payload)['layout']

    def test_regression_plot_labels_are_english(self, regression_data):
        ra, data = regression_data
        payload = ra.create_regression_plot(data)
        for turkish in ('Regresyon', 'Port Çapı', 'Zaman', 'Yakıt Türleri'):
            assert turkish not in payload


# ----------------------------------------------------------------------
# 6. ISA yardımcıları
# ----------------------------------------------------------------------
class TestISAHelpers:

    def test_sea_level_reference(self):
        assert isa_pressure(0.0) == pytest.approx(101325.0, rel=1e-9)
        assert isa_temperature(0.0) == pytest.approx(288.15, rel=1e-9)

    def test_layer_base_values_reproduced(self):
        for h_base, T_base, _lapse, P_base in ISA_LAYERS:
            assert isa_temperature(h_base) == pytest.approx(T_base, rel=1e-9)
            assert isa_pressure(h_base) == pytest.approx(P_base, rel=1e-3)

    def test_pressure_monotonically_decreases(self):
        alts = [0, 1000, 5000, 11000, 20000, 32000, 50000, 71000, 84852, 90000]
        p = [isa_pressure(h) for h in alts]
        assert all(p[i] > p[i + 1] for i in range(len(p) - 1))
        assert all(v > 0 for v in p)

    def test_combustion_module_uses_helpers(self):
        """calculate_altitude_performance artık satır-içi ISA kopyası
        kullanmıyor: raporlanan basınç isa_pressure ile birebir."""
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        from hrma.constants import BAR_PER_PA
        analyzer = CombustionAnalyzer()
        motor = {
            'chamber_pressure': 20.0,
            'gas_constants': {'exit': 300.0},
            'conditions': {'exit': {'P': 1.0, 'T': 1500.0}},
            'performance': {'velocities': {'exit': 2000.0}, 'c_star': 1500.0},
            'gamma_avg': 1.2,
            'mdot_total': 1.0,
        }
        out = analyzer.calculate_altitude_performance(motor, [0, 5000, 15000])
        for row in out['altitude_performance']:
            assert row['pressure'] == pytest.approx(
                isa_pressure(row['altitude']) * BAR_PER_PA, rel=1e-12)
            assert row['temperature'] == pytest.approx(
                isa_temperature(row['altitude']), rel=1e-12)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
