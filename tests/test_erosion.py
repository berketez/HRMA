"""Boğaz erozyonu doğrulama testleri (Dalga 3).

Kapsam:
  1. ThroatErosionModel birim testleri — el hesabı çapaları:
       ṙ = a_ref·(Pc/70 bar)^0.8
     Grafit varsayılanı a_ref = 0.15 mm/s (bandın konservatif üst ucu;
     Thakre & Yang 2008, Geisler bandı). 35 bar'da beklenen:
       0.15 · (35/70)^0.8 = 0.15 · 0.5743 = 0.08615 mm/s
  2. Transient kuplaj — erozyon AÇIK: d_t monoton artar, Pc ve F baseline'a
     göre düşer; daha agresif a_ref daha çok erozyon → daha düşük Pc.
  3. Geriye dönük uyum — erozyon KAPALI (varsayılan): boğaz çapı sabit,
     yarı-kararlı kimlik Pc·Cd·At_tasarım = ṁ·c* her adımda tutar,
     varsayılan çağrı ile erosion_enabled=False çağrısı bit-özdeş sonuç verir.
  4. SolidRocketEngine nozul tasarımı: eski sabit '0.001 mm/s' metni yerine
     ampirik modelden hesaplanan değer (40 bar varsayılanında el hesabı:
     0.15·(40/70)^0.8 = 0.15·0.63906 = 0.09586 mm/s).
"""

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.engines.solid_rocket_engine import SolidRocketEngine
from hrma.analysis.transient_ballistics import (
    TransientBallistics, ThroatErosionModel, THROAT_EROSION_MATERIALS)
from hrma.data.materials_db import get_material


# ---------------------------------------------------------------------------
# Model birim testleri
# ---------------------------------------------------------------------------

class TestThroatErosionModel:
    def test_graphite_reference_rate_at_70_bar(self):
        """El hesabı: Pc = Pc_ref = 70 bar → ṙ = a_ref = 0.15 mm/s."""
        m = ThroatErosionModel.for_material('graphite')
        assert m.rate_mm_s(70.0) == pytest.approx(0.15, rel=1e-12)

    def test_pressure_scaling_exponent(self):
        """El hesabı: 35 bar → 0.15·(0.5)^0.8 = 0.086147 mm/s."""
        m = ThroatErosionModel.for_material('graphite')
        assert m.rate_mm_s(35.0) == pytest.approx(0.15 * 0.5 ** 0.8, rel=1e-12)
        assert m.rate_mm_s(35.0) == pytest.approx(0.086147, abs=1e-5)

    def test_unit_conversion_m_s(self):
        """rate_m_s(Pa) = rate_mm_s(bar)/1000 aynı basınçta."""
        m = ThroatErosionModel.for_material('graphite')
        assert m.rate_m_s(70e5) == pytest.approx(0.15e-3, rel=1e-12)

    def test_zero_or_negative_pressure_gives_zero(self):
        m = ThroatErosionModel.for_material('graphite')
        assert m.rate_mm_s(0.0) == 0.0
        assert m.rate_mm_s(-5.0) == 0.0

    def test_default_is_conservative_band_upper_end(self):
        """Varsayılan a_ref bandın ÜST (konservatif) ucudur."""
        for key in ('graphite', 'carbon_carbon'):
            rec = THROAT_EROSION_MATERIALS[key]
            assert rec['a_ref_default_mm_s'] == rec['a_ref_band_mm_s'][1]

    def test_carbon_carbon_lower_than_graphite(self):
        """C-C bulk grafitten daha yavaş erozyona uğrar (Thakre & Yang)."""
        g = ThroatErosionModel.for_material('graphite')
        cc = ThroatErosionModel.for_material('carbon_carbon')
        assert cc.a_ref_mm_s < g.a_ref_mm_s
        assert cc.rate_mm_s(70.0) < g.rate_mm_s(70.0)

    def test_steel_and_copper_not_recommended(self):
        """Soğutmasız çelik/bakır: a_ref verilmeden model kurulamaz."""
        for mat in ('steel', 'copper'):
            with pytest.raises(ValueError, match='NOT RECOMMENDED'):
                ThroatErosionModel.for_material(mat)

    def test_steel_with_explicit_coefficient_carries_warning(self):
        """Test-verisi a_ref'iyle zorlanırsa model kurulur ama uyarı taşır."""
        m = ThroatErosionModel.for_material('steel', a_ref_mm_s=0.3)
        assert m.a_ref_mm_s == pytest.approx(0.3)
        assert any('NOT RECOMMENDED' in w for w in m.warnings)

    def test_material_aliases(self):
        assert ThroatErosionModel.for_material('C-C').material == 'carbon_carbon'
        with pytest.raises(ValueError, match='NOT RECOMMENDED'):
            ThroatErosionModel.for_material('ss_304')  # → steel

    def test_unknown_material_rejected(self):
        with pytest.raises(ValueError, match='No throat erosion data'):
            ThroatErosionModel.for_material('unobtainium')

    def test_invalid_coefficient_rejected(self):
        with pytest.raises(ValueError):
            ThroatErosionModel(a_ref_mm_s=0.0)
        with pytest.raises(ValueError):
            ThroatErosionModel(a_ref_mm_s=-1.0)

    def test_display_name_from_central_materials_db(self):
        """Görünen ad merkezi materials_db kaydından gelir (tek kaynak)."""
        m = ThroatErosionModel.for_material('graphite')
        assert m.material_display == get_material('graphite')['name']

    def test_describe_is_json_friendly(self):
        d = ThroatErosionModel.for_material('graphite').describe()
        for key in ('model', 'a_ref_mm_s', 'pc_ref_bar', 'exponent',
                    'material', 'a_ref_band_mm_s', 'source', 'warnings'):
            assert key in d
        assert d['source']  # kaynak atfı boş olamaz
        assert d['exponent'] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Transient kuplaj testleri
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def engine():
    """3 kN N₂O/parafin, 20 bar (test_transient_ballistics ile aynı vaka)."""
    e = HybridRocketEngine(
        thrust=3000, burn_time=10, of_ratio=7.96,
        chamber_pressure=20, atmospheric_pressure=1.01325,
        fuel_type='paraffin', oxidizer_type='n2o',
        fuel_density=900, regression_a=1.17e-4, regression_n=0.62,
        l_star=1.0, expansion_ratio=0, nozzle_type='conical')
    e.calculate()
    return e


@pytest.fixture(scope='module')
def baseline(engine):
    """Erozyon KAPALI (varsayılan) referans çözüm."""
    return TransientBallistics(engine, feed_mode='regulated').solve()


@pytest.fixture(scope='module')
def eroded(engine):
    """Erozyon AÇIK (grafit, varsayılan konservatif a_ref) çözüm."""
    return TransientBallistics(
        engine, feed_mode='regulated',
        erosion_enabled=True, throat_material='graphite').solve()


class TestErosionCoupling:
    def test_throat_diameter_monotonically_increases(self, eroded):
        d = eroded['throat_diameter']
        assert len(d) > 10
        assert np.all(np.diff(d) > 0)

    def test_first_step_matches_baseline(self, baseline, eroded):
        """Erozyon kayıttan SONRA uygulanır → ilk adım baseline ile özdeş."""
        assert eroded['chamber_pressure'][0] == pytest.approx(
            baseline['chamber_pressure'][0], rel=1e-9)
        assert eroded['thrust'][0] == pytest.approx(
            baseline['thrust'][0], rel=1e-9)

    def test_pc_drops_below_baseline(self, baseline, eroded):
        """Büyüyen boğaz: Pc = ṁ·c*/(Cd·At) her adımda baseline'ın altında."""
        n = min(len(baseline['chamber_pressure']),
                len(eroded['chamber_pressure']))
        assert n > 20
        pcb = baseline['chamber_pressure'][10:n]
        pce = eroded['chamber_pressure'][10:n]
        assert np.all(pce < pcb)
        # Yanma sonunda fark belirgin olmalı (≈%5-7 alan büyümesi sınıfı)
        assert pce[-1] < 0.995 * pcb[-1]

    def test_thrust_drops_below_baseline(self, baseline, eroded):
        n = min(len(baseline['thrust']), len(eroded['thrust']))
        assert eroded['thrust'][n - 1] < baseline['thrust'][n - 1]

    def test_erosion_report_fields(self, eroded):
        ero = eroded['erosion']
        assert ero['enabled'] is True
        assert ero['total_recession_mm'] > 0.0
        assert (ero['final_throat_diameter_mm']
                > ero['initial_throat_diameter_mm'])
        assert ero['model']['material'] == 'graphite'
        # Kayıtlı diziyle tutarlılık: son ilerletme kayıttan sonra olabilir,
        # rapor edilen toplam gerileme dizidekinden küçük olamaz.
        d = eroded['throat_diameter']
        rec_from_array = (d[-1] - d[0]) / 2.0 * 1000.0
        assert ero['total_recession_mm'] >= rec_from_array - 1e-12

    def test_recession_magnitude_hand_check(self, eroded):
        """El hesabı bandı: ṙ(20 bar) = 0.15·(20/70)^0.8 = 0.05513 mm/s.

        Pc yanma boyunca 20 bar civarından aşağı süründüğünden toplam
        gerileme ≈ ṙ·t_yanma'nın biraz altında kalmalı ama aynı mertebede
        olmalı: 10 s için ~0.4–0.6 mm bandı.
        """
        r_design = 0.15 * (20.0 / 70.0) ** 0.8       # mm/s
        t_burn = eroded['burn_duration']
        upper = r_design * t_burn                     # sabit-Pc üst sınırı
        rec = eroded['erosion']['total_recession_mm']
        assert 0.5 * upper < rec <= upper * 1.001

    def test_more_aggressive_model_erodes_more(self, engine, eroded):
        """Model-değiştirilebilir API: özel a_ref → daha düşük Pc sonu."""
        hot = TransientBallistics(
            engine, feed_mode='regulated',
            erosion_model=ThroatErosionModel(
                a_ref_mm_s=0.30, material='custom_hot')).solve()
        assert hot['erosion']['enabled'] is True
        assert (hot['erosion']['total_recession_mm']
                > eroded['erosion']['total_recession_mm'])
        n = min(len(hot['chamber_pressure']), len(eroded['chamber_pressure']))
        assert (hot['chamber_pressure'][n - 1]
                < eroded['chamber_pressure'][n - 1])


class TestBackwardCompatibility:
    """Erozyon KAPALIYKEN eski davranış aynen korunmalı (424 test sözü)."""

    def test_disabled_by_default(self, baseline):
        assert baseline['erosion']['enabled'] is False
        assert baseline['erosion']['total_recession_mm'] == 0.0

    def test_throat_constant_and_equals_design(self, engine, baseline):
        d = baseline['throat_diameter']
        d_design = 2.0 * np.sqrt(float(engine.At) / np.pi)
        assert np.all(d == d[0])
        assert d[0] == pytest.approx(d_design, rel=1e-12)

    def test_quasi_steady_identity_with_design_throat(self, engine, baseline):
        """Pc·Cd·At_tasarım = ṁ·c* her adımda → At hiç sürüklenmemiş."""
        for i in range(0, len(baseline['time']), 40):
            mdot = baseline['mdot_ox'][i] + baseline['mdot_fuel'][i]
            cstar, _ = engine._instantaneous_performance(
                baseline['of_ratio'][i])
            lhs = baseline['chamber_pressure'][i] * 0.98 * engine.At
            assert lhs == pytest.approx(mdot * cstar, rel=0.02)

    def test_default_call_identical_to_explicit_false(self, engine, baseline):
        """Varsayılan çağrı ile erosion_enabled=False bit-özdeş olmalı."""
        res = TransientBallistics(
            engine, feed_mode='regulated', erosion_enabled=False).solve()
        assert np.array_equal(res['chamber_pressure'],
                              baseline['chamber_pressure'])
        assert np.array_equal(res['thrust'], baseline['thrust'])
        assert np.array_equal(res['port_diameter'],
                              baseline['port_diameter'])
        assert res['end_event'] == baseline['end_event']

    def test_design_point_anchor_preserved(self, engine, baseline):
        """t=0 tasarım noktası çapası (mevcut test paketiyle aynı tolerans)."""
        assert baseline['chamber_pressure'][0] == pytest.approx(
            engine.P_c * 1e5, rel=0.08)


# ---------------------------------------------------------------------------
# SolidRocketEngine nozul erozyon alanı
# ---------------------------------------------------------------------------

class TestSolidEngineErosionField:
    def test_placeholder_text_replaced(self):
        eng = SolidRocketEngine()  # varsayılan Pc = 40 bar
        perf = eng._design_nozzle_geometry()['performance']
        assert perf['erosion_rate'] != '0.001 mm/s'
        assert perf['erosion_rate'].endswith('mm/s')
        assert 'erosion_estimate' in perf

    def test_rate_hand_calculation_40_bar(self):
        """El hesabı: 0.15·(40/70)^0.8 = 0.15·0.63906 = 0.09586 mm/s."""
        eng = SolidRocketEngine(chamber_pressure=40)
        est = eng._design_nozzle_geometry()['performance']['erosion_estimate']
        assert est['rate_mm_s'] == pytest.approx(0.09586, abs=2e-4)
        assert est['chamber_pressure_bar'] == pytest.approx(40.0)
        assert est['material'] == 'graphite'
        # Varsayılan katsayı bandın üst ucu → tahmin bandın üst ucuna eşit
        assert est['rate_mm_s'] == pytest.approx(est['band_mm_s'][1], abs=1e-3)
        assert est['band_mm_s'][0] < est['band_mm_s'][1]

    def test_rate_scales_with_chamber_pressure(self):
        est_40 = SolidRocketEngine(chamber_pressure=40) \
            ._design_nozzle_geometry()['performance']['erosion_estimate']
        est_70 = SolidRocketEngine(chamber_pressure=70) \
            ._design_nozzle_geometry()['performance']['erosion_estimate']
        assert est_70['rate_mm_s'] > est_40['rate_mm_s']
        assert est_70['rate_mm_s'] == pytest.approx(0.15, abs=1e-3)

    def test_source_and_note_present(self):
        est = SolidRocketEngine() \
            ._design_nozzle_geometry()['performance']['erosion_estimate']
        assert est['source']
        assert 'approximate' in est['note'].lower() or \
               'Empirical' in est['note']


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
