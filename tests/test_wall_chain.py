"""
Isı -> yapısal cidar sıcaklığı zinciri testleri (Dalga 0, 2026-07-14).

Eski durum: Isı modülünün hesapladığı gerçek cidar sıcaklıkları yapısal
modüle AKMIYORDU; yapısal modül chamber_temperature'tan hayali bir gradyan
tahmin ediyordu (iki modül aynı motor için farklı cidar sıcaklığı
varsayıyordu). Artık hybrid_rocket_engine, wall_analysis.inner/outer
sıcaklıklarını 'wall_temperature_hot/cold' anahtarlarıyla yapısal modüle
geçirir; structural_analysis._estimate_wall_delta_T bu anahtarları birinci
öncelikle okur.

Ayrıca iki SF raporu doğrulanır:
  safety_factor_pressure : yalnız basınç hoop (birincil yük)
  safety_factor_total    : basınç + termal (mevcut hoop_safety_factor'a eşit)
Sıcak motorda daima SF_pressure > SF_total olmalıdır (termal gerilme > 0).
"""

import warnings

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer

warnings.filterwarnings('ignore')

HOT_MOTOR = {
    'chamber_pressure': 20.0,      # bar
    'chamber_temperature': 3200.0,  # K
    'chamber_diameter': 0.1,       # m
    'chamber_length': 0.5,         # m
    'throat_diameter': 0.03,       # m
    'nozzle_type': 'conical',
    'burn_time': 10.0,
    'mdot_total': 1.0,
}


@pytest.fixture
def struct():
    return StructuralAnalyzer()


@pytest.fixture
def heat():
    return HeatTransferAnalyzer()


class TestWallTemperatureHandoff:
    """wall_temperature_hot/cold anahtarları yapısal modülde 1. öncelik."""

    def test_explicit_wall_temps_override_chamber_estimate(self, struct):
        md = dict(HOT_MOTOR)
        md['wall_temperature_hot'] = 900.0
        md['wall_temperature_cold'] = 400.0
        res = struct.analyze_structure(md, material='steel_4130')
        ta = res['thermal_analysis']
        assert ta['wall_temperature_inner_K'] == pytest.approx(900.0)
        assert ta['wall_temperature_outer_K'] == pytest.approx(400.0)

    def test_without_wall_temps_falls_back_to_chamber_estimate(self, struct):
        res = struct.analyze_structure(dict(HOT_MOTOR), material='steel_4130')
        ta = res['thermal_analysis']
        # Konservatif tahmin: iç yüz malzeme servis sınırında kapanır (811 K)
        assert ta['wall_temperature_inner_K'] == pytest.approx(811.0)

    def test_heat_module_output_feeds_structural_module(self, heat, struct):
        """Uçtan uca birim zincir: ısı analizi cidar T'leri -> yapısal girdi."""
        h = heat.analyze_heat_transfer(
            dict(HOT_MOTOR), material='steel_4130',
            wall_thickness=0.005, cooling_type='natural')
        wall = h['wall_analysis']
        md = dict(HOT_MOTOR)
        md['wall_temperature_hot'] = wall['inner_temperature']
        md['wall_temperature_cold'] = wall['outer_temperature']
        res = struct.analyze_structure(md, material='steel_4130')
        ta = res['thermal_analysis']
        assert ta['wall_temperature_inner_K'] == pytest.approx(
            wall['inner_temperature'], rel=1e-9)
        assert ta['wall_temperature_outer_K'] == pytest.approx(
            wall['outer_temperature'], rel=1e-9)


class TestTwoSafetyFactorReport:
    """SF_pressure (yalnız basınç) ve SF_total (basınç+termal) raporu."""

    def test_fields_present_at_both_levels(self, struct):
        res = struct.analyze_structure(dict(HOT_MOTOR), material='steel_4130')
        ca = res['chamber_analysis']
        for key in ('safety_factor_pressure', 'safety_factor_total'):
            assert key in ca
            assert key in res
        # Üst seviye alanlar chamber_analysis ile tutarlı
        assert res['safety_factor_pressure'] == ca['safety_factor_pressure']
        assert res['safety_factor_total'] == ca['safety_factor_total']
        # Geriye dönük tek-SF alanı total'a eşit
        assert res['safety_factor'] == ca['safety_factor_total']

    def test_total_equals_existing_hoop_safety_factor(self, struct):
        res = struct.analyze_structure(dict(HOT_MOTOR), material='steel_4130')
        ca = res['chamber_analysis']
        assert ca['safety_factor_total'] == pytest.approx(
            ca['hoop_safety_factor'], rel=1e-12)

    def test_pressure_sf_exceeds_total_sf_on_hot_motor(self, struct):
        """Sıcak motorda termal gerilme > 0 => SF_pressure > SF_total."""
        res = struct.analyze_structure(dict(HOT_MOTOR), material='steel_4130')
        ca = res['chamber_analysis']
        assert ca['thermal_hoop_stress'] > 0.0
        assert ca['safety_factor_pressure'] > ca['safety_factor_total']

    def test_cold_motor_pressure_equals_total(self, struct):
        """Sıcaklık bilgisi olmayan motor: termal gerilme 0, iki SF eşit."""
        md = {k: v for k, v in HOT_MOTOR.items()
              if k != 'chamber_temperature'}
        res = struct.analyze_structure(md, material='steel_4130')
        ca = res['chamber_analysis']
        assert ca['thermal_hoop_stress'] == pytest.approx(0.0)
        assert ca['safety_factor_pressure'] == pytest.approx(
            ca['safety_factor_total'], rel=1e-12)

    def test_unsafe_hot_motor_flagged_thermal_dominated(self, struct):
        res = struct.analyze_structure(dict(HOT_MOTOR), material='steel_4130')
        sa = res['safety_analysis']
        assert sa['status'] == 'UNSAFE'
        assert sa['explanation'] == 'thermal-dominated'

    def test_safe_motor_has_empty_explanation(self, struct):
        """UNSAFE olmayan durumda açıklama alanı boş kalır."""
        md = {'chamber_pressure': 10.0, 'chamber_diameter': 0.08,
              'chamber_length': 0.4, 'throat_diameter': 0.02,
              'nozzle_type': 'conical', 'burn_time': 5.0}
        res = struct.analyze_structure(md, material='steel_4130')
        sa = res['safety_analysis']
        if sa['status'] != 'UNSAFE':
            assert sa['explanation'] == ''


class TestEngineLevelChain:
    """Motor hesabı uçtan uca: ısı sonuçları yapısal girdiye akar."""

    @pytest.fixture(scope='class')
    def engine_results(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        engine = HybridRocketEngine(
            thrust=1000, burn_time=10, of_ratio=6.0, chamber_pressure=20.0)
        return engine.calculate()

    def test_structural_uses_heat_wall_temperatures(self, engine_results):
        r = engine_results
        wall = r['heat_transfer_analysis']['wall_analysis']
        ta = r['structural_analysis']['thermal_analysis']
        assert ta['wall_temperature_inner_K'] == pytest.approx(
            wall['inner_temperature'], rel=1e-6)
        assert ta['wall_temperature_outer_K'] == pytest.approx(
            wall['outer_temperature'], rel=1e-6)

    def test_two_sf_report_in_engine_output(self, engine_results):
        st = engine_results['structural_analysis']
        assert st['safety_factor_pressure'] > st['safety_factor_total']
        assert np.isfinite(st['safety_factor_pressure'])
        assert np.isfinite(st['safety_factor_total'])

    def test_gamma_and_mw_at_top_level(self, engine_results):
        r = engine_results
        assert 'gamma' in r and 'molecular_weight' in r
        assert 1.05 < r['gamma'] < 1.45, r['gamma']
        assert 10.0 < r['molecular_weight'] < 60.0, r['molecular_weight']

    def test_gamma_mw_consistent_with_combustion_chamber(self, engine_results):
        r = engine_results
        chamber = r['combustion_analysis']['compositions'].get('chamber', {})
        if 'gamma' in chamber:
            assert r['gamma'] == pytest.approx(chamber['gamma'], rel=1e-9)
        if 'molecular_weight' in chamber:
            assert r['molecular_weight'] == pytest.approx(
                chamber['molecular_weight'], rel=1e-9)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
