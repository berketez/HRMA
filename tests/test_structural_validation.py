"""
Structural analysis validation tests (DENETIM DUZELTMESI 2026-06).

Bu test paketi, yapisal modulun ESKI tehlikeli davranisini (termal gerilme,
sicaklik derating'i ve burkulmanin tamamen ihmal edilmesi) artik yapmadigini
ve emniyet faktorunun GERCEKCI-KONSERVATIF hesaplandigini dogrular.

Kapsanan duzeltmeler:
  1) Termal hoop gerilme : sigma_th = E*alpha*dT/(1-nu)
     Kaynak: Timoshenko & Goodier "Theory of Elasticity"; Boley & Weiner
     "Theory of Thermal Stresses" Ch.10-11; Roark's Formulas for Stress &
     Strain 9th ed. Ch.16. Klasik yuzey degeri E*alpha*dT/(2(1-nu)); biz
     2 faktorunu KONSERVATIF olarak dusurmuyoruz.
  2) Sicaklik derating  : yield/ultimate cidar sicakligiyla duser.
     Kaynak: MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 (AISI dusuk-alasimli celik).
  3) Burkulma (buckling) : NASA SP-8007 "Buckling of Thin-Walled Circular
     Cylinders" (revised 1968, NTRS 19680026348).
  4) Kalin-cidar (Lame)  : t/r >= 0.1 oldugunda ince-cidar tepe gerilmeyi az
     gosterir; Lame ic-yuzey tepe degeri kullanilir.
     Kaynak: Lame (1833); Timoshenko & Goodier Art.28; Roark's Tablo 13.5.

Referans vaka (gorev tanimi): 4130 celik, Pc=50 bar, Tc=3000 K cidar.
"""

import math
import numpy as np
import pytest

from hrma.analysis.structural_analysis import StructuralAnalyzer


# --- Ortak referans motor verileri --------------------------------------
REF_MOTOR = {
    'chamber_pressure': 50.0,      # bar
    'chamber_diameter': 0.15,      # m
    'chamber_length': 0.6,         # m
    'throat_diameter': 0.04,       # m
    'nozzle_type': 'conical',
    'burn_time': 10.0,
    'chamber_temperature': 3000.0,  # K -> termal gerilme + derating tetikler
}

# Sicaklik bilgisi YOK (eski/izotermal davranis: termal etki kapali)
REF_MOTOR_NO_TEMP = {k: v for k, v in REF_MOTOR.items()
                     if k != 'chamber_temperature'}


@pytest.fixture
def analyzer():
    return StructuralAnalyzer()


class TestThermalHoopStress:
    """Termal hoop gerilme formulu ve isaret/buyukluk dogrulamasi."""

    def test_thermal_formula_matches_E_alpha_dT_over_1_minus_nu(self, analyzer):
        # Kaynak: gorev tanimi sigma = E*alpha*dT/(1-nu) (konservatif).
        mat = analyzer.materials['steel_4130']
        dT = 500.0
        out = analyzer._thermal_hoop_stress(mat, dT)
        expected = (mat['elastic_modulus'] * mat['thermal_expansion'] * dT
                    / (1.0 - mat['poisson_ratio']))
        assert out['thermal_hoop_stress'] == pytest.approx(expected, rel=1e-9)

    def test_thermal_is_conservative_double_classic_surface_value(self, analyzer):
        # Klasik yuzey degeri E*alpha*dT/(2(1-nu)); bizimki tam 2 kati olmali.
        mat = analyzer.materials['steel_4130']
        dT = 511.0
        out = analyzer._thermal_hoop_stress(mat, dT)
        classic = (mat['elastic_modulus'] * mat['thermal_expansion'] * dT
                   / (2.0 * (1.0 - mat['poisson_ratio'])))
        assert out['thermal_hoop_stress'] == pytest.approx(2.0 * classic, rel=1e-9)

    def test_negative_or_zero_gradient_gives_zero_thermal(self, analyzer):
        # Sogutmasiz/izotermal cidar (dT<=0) -> termal gerilme 0.
        mat = analyzer.materials['steel_4130']
        assert analyzer._thermal_hoop_stress(mat, -50.0)['thermal_hoop_stress'] == 0.0
        assert analyzer._thermal_hoop_stress(mat, 0.0)['thermal_hoop_stress'] == 0.0


class TestTemperatureDerating:
    """Sicakliga bagli mukavemet derating'i (MMPDS egrisi interpolasyonu)."""

    def test_room_temperature_no_derating(self, analyzer):
        mat = analyzer.materials['steel_4130']
        d = analyzer._derate_strength(mat, 293.15)  # 20 C
        assert d['strength_retention_factor'] == pytest.approx(1.0, abs=1e-6)
        assert d['derated_yield_strength'] == pytest.approx(mat['yield_strength'], rel=1e-6)

    def test_4130_loses_about_half_strength_near_500C(self, analyzer):
        # Gorev tanimi: AISI 4130 @500 C ~%50 kayip. Egri 500C -> 0.44.
        mat = analyzer.materials['steel_4130']
        d = analyzer._derate_strength(mat, 500.0 + 273.15)
        assert d['strength_retention_factor'] == pytest.approx(0.44, abs=0.02)
        # "yaklasik yari" -> retention 0.4-0.6 bandinda olmali (gorev ifadesi).
        assert 0.40 <= d['strength_retention_factor'] <= 0.60

    def test_interpolation_between_curve_points(self, analyzer):
        # 538 C ~= 811 K: interp(500->0.44, 600->0.29) ~ 0.383.
        mat = analyzer.materials['steel_4130']
        d = analyzer._derate_strength(mat, 811.0)
        expected = float(np.interp(811.0 - 273.15, [500, 600], [0.44, 0.29]))
        assert d['strength_retention_factor'] == pytest.approx(expected, abs=1e-3)

    def test_above_curve_clamps_to_lowest_factor_conservative(self, analyzer):
        # Egri ustunde (cok sicak) -> en dusuk faktorde sabitlenir (konservatif).
        mat = analyzer.materials['steel_4130']
        last_temp = max(mat['derating_curve'].keys())
        last_fac = mat['derating_curve'][last_temp]
        d = analyzer._derate_strength(mat, 2000.0)  # cok yuksek
        assert d['strength_retention_factor'] == pytest.approx(last_fac, abs=1e-9)

    def test_derating_monotonic_decreasing_with_temperature(self, analyzer):
        mat = analyzer.materials['steel_4130']
        temps_K = [300, 500, 700, 900, 1100]
        rets = [analyzer._derate_strength(mat, t)['strength_retention_factor']
                for t in temps_K]
        assert all(rets[i] >= rets[i + 1] for i in range(len(rets) - 1))


class TestBuckling:
    """NASA SP-8007 ince-cidarli silindir burkulma kontrolu."""

    def test_classical_axial_buckling_stress_formula(self, analyzer):
        mat = analyzer.materials['steel_4130']
        E, nu = mat['elastic_modulus'], mat['poisson_ratio']
        t, r = 0.001, 0.5
        out = analyzer._check_buckling(5e5, r, t, 2.0, mat)
        sigma_cl = E / math.sqrt(3.0 * (1.0 - nu**2)) * (t / r)
        assert out['classical_axial_buckling_stress_MPa'] == pytest.approx(
            sigma_cl / 1e6, rel=1e-6)

    def test_knockdown_factor_in_physical_range(self, analyzer):
        # SP-8007 knockdown gamma ince kabuklarda ~0.2-0.6 mertebesinde.
        mat = analyzer.materials['steel_4130']
        out = analyzer._check_buckling(5e5, 0.5, 0.001, 2.0, mat)  # r/t=500
        assert 0.15 < out['knockdown_factor_gamma'] < 0.65
        # Knockdown daima klasik degeri DUSURUR (konservatif).
        assert (out['critical_axial_buckling_stress_MPa']
                <= out['classical_axial_buckling_stress_MPa'])

    def test_thin_wall_buckling_flagged_critical(self, analyzer):
        # Cok ince + uzun + buyuk capli kabuk: burkulma kritik olmali.
        mat = analyzer.materials['steel_4130']
        out = analyzer._check_buckling(5e5, 0.5, 0.001, 2.0, mat)
        assert out['axial_buckling_safety_factor'] < 1.0
        assert out['buckling_status'] == 'CRITICAL'

    def test_external_pressure_buckling_present(self, analyzer):
        mat = analyzer.materials['steel_4130']
        out = analyzer._check_buckling(5e5, 0.5, 0.001, 2.0, mat)
        assert out['critical_external_pressure_bar'] > 0.0
        assert math.isfinite(out['critical_external_pressure_bar'])


class TestThinWallValidityAndLame:
    """Ince-cidar gecerlilik kontrolu + kalin-cidar (Lame) konservatif duzeltme."""

    def test_thin_wall_case_uses_thin_model(self, analyzer):
        res = analyzer.analyze_structure(
            {'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
             'chamber_length': 0.5, 'throat_diameter': 0.02,
             'nozzle_type': 'conical', 'burn_time': 10.0},
            material='steel_4130', design_pressure_factor=1.5)
        ca = res['chamber_analysis']
        assert ca['thin_wall_valid'] is True
        assert ca['thin_wall_ratio_t_over_r'] < 0.1
        assert ca['pressure_hoop_model'] == 'thin_wall'

    def test_thick_wall_uses_lame_and_is_conservative(self, analyzer):
        # Kalin cidar (t/r>0.1) vakasi: senaryo-ayrimli termal modelde
        # (2026-07-12) referans vaka ince cidara dustugu icin kalin rejim
        # yuksek tasarim faktoruyle zorlanir. Lame tepe >= ince-cidar.
        res = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                         design_pressure_factor=4.0)
        ca = res['chamber_analysis']
        assert ca['thin_wall_valid'] is False
        assert ca['pressure_hoop_model'] == 'lame_thick_wall'
        # Konservatiflik: kullanilan basinc hoop >= ince-cidar degeri.
        assert ca['pressure_hoop_stress'] >= ca['thin_wall_pressure_hoop_MPa'] - 1e-6
        assert ca['lame_peak_pressure_hoop_MPa'] >= ca['thin_wall_pressure_hoop_MPa']

    def test_lame_peak_matches_closed_form(self, analyzer):
        # Lame ic-yuzey tepe: sigma = p*(b^2+a^2)/(b^2-a^2).
        res = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                         design_pressure_factor=1.5)
        ca = res['chamber_analysis']
        p = 50.0 * 1e5 * 1.5  # design pressure Pa
        a = (REF_MOTOR['chamber_diameter'] / 2.0)
        t = ca['recommended_thickness'] / 1000.0
        b = a + t
        expected = p * (b**2 + a**2) / (b**2 - a**2) / 1e6
        assert ca['lame_peak_pressure_hoop_MPa'] == pytest.approx(expected, rel=1e-3)


class TestThermalEffectOnSafetyFactor:
    """ANA DOGRULAMA: termal+derating dahil edilince SF ciddi duser."""

    def test_pressure_only_appears_safe_but_thermal_is_unsafe(self, analyzer):
        """Gorev kanıtı: sadece-basinc SF guvenli gorunur, gercek SF<1.

        Bu, modulun ESKI tehlikesinin kapatildiginin kanitidir.
        """
        res_noT = analyzer.analyze_structure(
            REF_MOTOR_NO_TEMP, material='steel_4130', design_pressure_factor=1.5)
        res_T = analyzer.analyze_structure(
            REF_MOTOR, material='steel_4130', design_pressure_factor=1.5)

        sf_noT = res_noT['chamber_analysis']['hoop_safety_factor']
        sf_T = res_T['chamber_analysis']['hoop_safety_factor']

        # Sadece-basinc: yuksek (guvenli gorunur) SF.
        assert sf_noT > 3.0, f"pressure-only SF should look safe, got {sf_noT}"
        # Termal+derating: SF DRAMATIK duser, hatta 1 altina iner (TEHLIKE).
        assert sf_T < 1.0, f"thermal+derate SF must reveal danger, got {sf_T}"
        # Termal etki SF'yi en az 3 kat dusurmeli (buyuklugu kanitla).
        assert sf_T < sf_noT / 3.0
        # Genel durum UNSAFE olarak isaretlenmeli.
        assert res_T['safety_analysis']['status'] == 'UNSAFE'

    def test_thermal_stress_dominates_pressure(self, analyzer):
        # 3000 K cidarda termal hoop, basinc hoop'undan cok buyuk olmali.
        res = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                         design_pressure_factor=1.5)
        ca = res['chamber_analysis']
        assert ca['thermal_hoop_stress'] > ca['pressure_hoop_stress']
        # Toplam = basinc + termal (lineer superpozisyon).
        assert ca['hoop_stress'] == pytest.approx(
            ca['pressure_hoop_stress'] + ca['thermal_hoop_stress'], rel=1e-6)

    def test_derated_yield_below_room_temperature(self, analyzer):
        """Senaryo-ayrimli termal model (Opus denetimi 2026-07-12):
        eski kod sicak-soak deratingini soguk-gradyan gerilmesiyle
        YIGIYORDU (fiziksel celiski). Artik iki tutarli senaryo ayri
        cozulur; yoneten senaryonun yield'i raporlanir."""
        res = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                         design_pressure_factor=1.5)
        mat = analyzer.materials['steel_4130']
        ca = res['chamber_analysis']
        used = ca['yield_strength_used_MPa']
        room = mat['yield_strength'] / 1e6
        # Yoneten senaryo yield'i: oda-sicakligindan dusuk, tam-sicak (0.383)
        # deratinginden yuksek (ortalama-cidar sicakliginda derate edilir).
        assert used < room
        assert used > room * 0.383
        # Iki senaryo da raporlanmali; hot_soak derating ic-yuz sicakliginda.
        scen = ca['thermal_scenarios']
        assert set(scen) == {'hot_soak', 'cooled_gradient'}
        assert scen['hot_soak']['derating_temp_K'] == pytest.approx(811.0, abs=1.0)
        # Yoneten senaryo, dusuk von Mises SF'li oland ir.
        gov = ca['governing_thermal_scenario']
        assert scen[gov]['von_mises_safety_factor'] == pytest.approx(
            min(s['von_mises_safety_factor'] for s in scen.values()), rel=1e-9)
        # Guvenlik ozelligi korunur: sicak sogutmasiz motor hala UNSAFE (<1).
        assert ca['von_mises_safety_factor'] < 1.0

    def test_recommendations_flag_thermal_and_thin_wall(self, analyzer):
        res = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                         design_pressure_factor=1.5)
        recs = ' '.join(res['safety_analysis']['recommendations']).lower()
        assert 'thermal' in recs            # termal gerilme uyarisi
        # Kalin-cidar uyarisi kalin rejimde gelmeli (senaryo-ayrimli modelde
        # referans vaka ince cidara dustugunden 4x faktorle zorlanir)
        res4 = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                          design_pressure_factor=4.0)
        recs4 = ' '.join(res4['safety_analysis']['recommendations']).lower()
        assert 'thin-wall' in recs4 or 'thick-wall' in recs4

    def test_buckling_included_in_minimum_safety_factor(self, analyzer):
        res = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                         design_pressure_factor=1.5)
        assert 'buckling_axial' in res['safety_analysis']['safety_factors']
        # minimum SF, aday SF'lerin gercekten minimumudur.
        sfs = res['safety_analysis']['safety_factors'].values()
        assert res['safety_analysis']['minimum_safety_factor'] == pytest.approx(
            min(sfs), rel=1e-9)


class TestApiPreservation:
    """Public imza ve donen sozluk anahtarlarinin korundugunu dogrula."""

    def test_top_level_keys_present(self, analyzer):
        res = analyzer.analyze_structure(REF_MOTOR_NO_TEMP)
        for k in ('chamber_analysis', 'nozzle_analysis', 'end_cap_analysis',
                  'fastener_analysis', 'fatigue_analysis', 'weight_analysis',
                  'safety_analysis', 'material_properties', 'design_parameters'):
            assert k in res
        # Yeni eklenenler de mevcut olmali (eski anahtarlari kaldirmadan).
        assert 'thermal_analysis' in res
        assert 'buckling_analysis' in res

    def test_chamber_analysis_legacy_keys_present(self, analyzer):
        res = analyzer.analyze_structure(REF_MOTOR_NO_TEMP)
        ca = res['chamber_analysis']
        for k in ('minimum_thickness', 'recommended_thickness', 'hoop_stress',
                  'longitudinal_stress', 'von_mises_stress', 'hoop_safety_factor',
                  'von_mises_safety_factor', 'allowable_stress', 'diameter', 'length'):
            assert k in ca

    def test_default_signature_call_works(self, analyzer):
        # Varsayilan material + design_pressure_factor ile cagrilabilmeli.
        res = analyzer.analyze_structure(REF_MOTOR_NO_TEMP)
        assert res['design_parameters']['material'] == 'steel_4130'
        assert res['design_parameters']['design_pressure_factor'] == 1.5


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
