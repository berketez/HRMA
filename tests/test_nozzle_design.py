"""Lüle tasarımı — v2.6.2 fizik denetimi düzeltmelerinin kalıcı testleri.

Kapsanan bulgular (docs/v262_specs/PHYSICS_AUDIT.md):
  F049  `_calculate_nozzle_geometry` — cidar kalınlığı boğaz çapının %10'u
        değil, ince cidarlı basınç kabı bağıntısından (t = SF·p·r/σ) gelmeli;
        yoğunluk 7850 sabiti değil malzeme kaydından okunmalı.
  F050  `_calculate_nozzle_performance` — çıkış statik basıncı bağımsız bir
        girdi değil, ε ve γ'dan izentropik alan-Mach bağıntısıyla türetilmeli.
  F051  `_design_bell_nozzle` — Rao %80 bell açıları (θn, θe) genişleme
        oranının fonksiyonudur; sabit (30°, 8°) yalnız ε ≈ 50-100 için doğru.

Referanslar:
  Sutton & Biblarz, "Rocket Propulsion Elements" 9. baskı
      Eş. 3-7 (izentropik basınç), Eş. 3-14 (alan-Mach), Eş. 3-30 (CF),
      Eş. 3-32 (c*), Eş. 3-34 (diverjans verimi), Fig. 3-14 (Rao %80 bell),
      Böl. 3 ve 20 (aşırı genişleme / akış ayrılması), Böl. 8 (cidar).
  Rao, G.V.R., Jet Propulsion 28(6), 1958.
  Huzel & Huang, NASA SP-125, Böl. 4, Eş. 4-7, Fig. 4-15.
  Summerfield, Foster & Swan, Jet Propulsion 24, 1954 (ayrılma ölçütü).

NOT (test_nozzle_validation.py ile ilişki): o dosyadaki
`test_bell_lambda_range` (λ ≈ 0.9951) ve `test_default_reproduces_legacy_098`
(η ≈ 0.98) iddiaları F051 ÖNCESİ sabit θe = 8° davranışını kodluyordu. ε = 10
için doğru Rao açısı θe ≈ 14°, dolayısıyla λ = 0.9851 ve η = 0.9704'tür.
Aşağıdaki testler yeni (doğru) değerleri sabitler.
"""

import numpy as np
import pytest

from hrma.engines.nozzle_design import NozzleDesigner


PC = 40.0          # bar
GAMMA = 1.20
AT = 0.001         # m²


@pytest.fixture(scope="module")
def designer():
    return NozzleDesigner()


# ---------------------------------------------------------------------------
# F050 — çıkış basıncı geometriden türer
# ---------------------------------------------------------------------------
class TestExitPressureFromGeometry:

    def test_exit_pressure_matches_isentropic_relation(self, designer):
        """p_e, alan-Mach + izentropik basınç bağıntısıyla birebir tutarlı."""
        eps = 16.0
        res = designer.design_nozzle(AT, eps, PC, 1.01325, 'conical',
                                     gamma=GAMMA)
        p = res['performance']
        M_e = designer.mach_from_area_ratio(eps, GAMMA)
        p_ref = PC / ((1.0 + 0.5 * (GAMMA - 1.0) * M_e ** 2)
                      ** (GAMMA / (GAMMA - 1.0)))
        assert p['exit_pressure'] == pytest.approx(p_ref, rel=1e-9)
        assert p['exit_pressure_basis'] == 'isentropic_area_ratio'

    def test_isp_no_longer_constant_across_expansion_ratio(self, designer):
        """F050'nin ana belirtisi: ε değişirken Isp SABİT kalıyordu (252.53 s).

        Katalogda ölçülen doğru değerler (γ=1.20, R=350, Tc=3400 K, Pc=40 bar,
        konik, deniz seviyesi): ε=8 -> 250.9 s, ε=16 -> 231.2 s. ε=16 zaten
        ayrılma bandındadır (bkz. TestFlowSeparation); bu yüzden burada
        ayrılma modeli devre dışı bırakılmadan tam-akan CF üzerinden
        karşılaştırma yapılır.
        """
        isps = {}
        for eps in (4.0, 8.0, 16.0, 40.0):
            res = designer.design_nozzle(AT, eps, PC, 1.01325, 'conical',
                                         gamma=GAMMA, R_specific=350.0,
                                         T_chamber=3400.0)
            p = res['performance']
            cf_full = p['thrust_coefficient_full_flowing'] * p['nozzle_efficiency']
            isps[eps] = cf_full * p['characteristic_velocity'] / designer.g0
        assert isps[8.0] == pytest.approx(250.9, abs=1.0)
        assert isps[16.0] == pytest.approx(231.2, abs=1.0)
        # Hepsi birbirinden FARKLI olmalı (eski davranışta hepsi 252.53 idi)
        assert len(set(round(v, 2) for v in isps.values())) == len(isps)

    def test_vacuum_isp_increases_with_expansion_ratio(self, designer):
        """Vakumda (p_a = 0) Isp genişleme oranıyla monoton artmalı."""
        prev = 0.0
        for eps in (4.0, 10.0, 25.0, 60.0, 100.0):
            res = designer.design_nozzle(AT, eps, PC, 1.01325, 'conical',
                                         gamma=GAMMA, R_specific=350.0,
                                         T_chamber=3400.0, ambient_pressure=0.0)
            isp = res['performance']['specific_impulse']
            assert isp > prev, f"eps={eps} Isp artmadı ({isp:.2f} <= {prev:.2f})"
            prev = isp

    def test_caller_exit_pressure_is_back_pressure(self, designer):
        """4. konumsal argüman ortam basıncı gibi davranır (hybrid çağrısı)."""
        res = designer.design_nozzle(AT, 6.0, PC, 1.01325, 'conical',
                                     gamma=GAMMA)
        p = res['performance']
        assert p['ambient_pressure'] == pytest.approx(1.01325)
        assert p['exit_pressure_input'] == pytest.approx(1.01325)
        # Çıkış statik basıncı ε'dan gelir, argümandan DEĞİL
        assert p['exit_pressure'] != pytest.approx(1.01325, rel=1e-3)

    def test_ambient_overrides_positional_exit_pressure(self, designer):
        res = designer.design_nozzle(AT, 10.0, PC, 1.01325, 'conical',
                                     gamma=GAMMA, ambient_pressure=0.0)
        assert res['performance']['ambient_pressure'] == pytest.approx(0.0)


class TestFlowSeparation:
    """Aşırı genişlemede Summerfield ayrılma sınırı (F050 tamamlayıcısı)."""

    def test_no_negative_thrust_when_grossly_overexpanded(self, designer):
        """Eski (sınırsız) ideal formül ε=100'de NEGATİF itki veriyordu."""
        res = designer.design_nozzle(AT, 100.0, PC, 1.01325, 'conical',
                                     gamma=GAMMA, R_specific=350.0,
                                     T_chamber=3400.0)
        p = res['performance']
        assert p['thrust_coefficient_full_flowing'] < 0.0  # sınırsız formül
        assert p['flow_separated'] is True
        assert p['thrust_coefficient_actual'] > 0.0        # fiziksel sonuç
        assert p['specific_impulse'] > 0.0

    def test_separation_criterion_is_summerfield(self, designer):
        res = designer.design_nozzle(AT, 40.0, PC, 1.01325, 'conical',
                                     gamma=GAMMA)
        p = res['performance']
        assert p['separation_pressure'] == pytest.approx(0.4 * 1.01325, rel=1e-9)
        assert p['exit_pressure'] < p['separation_pressure']
        assert p['effective_expansion_ratio'] < p['expansion_ratio']
        assert p['thrust_coefficient_basis'] == 'separated_summerfield'
        assert p['warnings'] and p['warnings'][0]['code'] == 'warn.nozzle.flow_separation'

    def test_adapted_nozzle_is_not_separated(self, designer):
        """p_e = p_a (adapte) durumunda ayrılma olmamalı, uyarı üretilmemeli."""
        eps = 10.0
        p_e = NozzleDesigner.exit_pressure_from_expansion(eps, GAMMA, PC)
        res = designer.design_nozzle(AT, eps, PC, p_e, 'conical', gamma=GAMMA)
        p = res['performance']
        assert p['flow_separated'] is False
        assert p['warnings'] == []
        assert p['thrust_coefficient_basis'] == 'full_flowing'
        # Adapte genleşmede basınç-itki terimi sıfır -> CF = momentum terimi
        assert p['thrust_coefficient_ideal'] == pytest.approx(
            p['thrust_coefficient_momentum'], rel=1e-9)

    def test_separated_cf_beats_unbounded_ideal(self, designer):
        """Ayrılma KAYBI azaltır: sınırlı CF, sınırsız CF'ten büyük olmalı."""
        res = designer.design_nozzle(AT, 40.0, PC, 1.01325, 'conical',
                                     gamma=GAMMA)
        p = res['performance']
        assert p['thrust_coefficient_ideal'] > p['thrust_coefficient_full_flowing']


# ---------------------------------------------------------------------------
# F051 — Rao %80 bell açıları genişleme oranının fonksiyonu
# ---------------------------------------------------------------------------
class TestRaoBellAngles:

    @pytest.mark.parametrize("eps,theta_n,theta_e", [
        (10.0, 23.5, 14.0),
        (25.0, 27.0, 11.0),
        (50.0, 30.0, 9.0),
        (100.0, 32.0, 7.5),
    ])
    def test_table_anchor_points(self, designer, eps, theta_n, theta_e):
        """Çapa noktalarında tablo değerleri birebir dönmeli (Sutton Fig. 3-14)."""
        res = designer.design_nozzle(AT, eps, PC, 1.01325, 'bell', gamma=GAMMA)
        div = res['contour']['divergent']
        assert div['throat_angle'] == pytest.approx(theta_n, abs=1e-9)
        assert div['exit_angle'] == pytest.approx(theta_e, abs=1e-9)

    def test_angles_are_monotonic_in_expansion_ratio(self, designer):
        """θn ε ile ARTAR, θe ε ile AZALIR (Rao grafiğinin temel eğilimi)."""
        prev_n, prev_e = -1.0, 1e9
        for eps in (10.0, 15.0, 25.0, 40.0, 60.0, 100.0):
            div = designer.design_nozzle(AT, eps, PC, 1.01325, 'bell',
                                         gamma=GAMMA)['contour']['divergent']
            assert div['throat_angle'] >= prev_n
            assert div['exit_angle'] <= prev_e
            prev_n, prev_e = div['throat_angle'], div['exit_angle']

    def test_out_of_band_is_reported_not_silent(self, designer):
        """Tablo bandı dışında sessiz ekstrapolasyon YOK; dayanak bildirilir."""
        low = designer.design_nozzle(AT, 4.0, PC, 1.01325, 'bell',
                                     gamma=GAMMA)['contour']['divergent']
        high = designer.design_nozzle(AT, 250.0, PC, 1.01325, 'bell',
                                      gamma=GAMMA)['contour']['divergent']
        mid = designer.design_nozzle(AT, 25.0, PC, 1.01325, 'bell',
                                     gamma=GAMMA)['contour']['divergent']
        assert low['angle_basis'] == 'rao80_clamped_low'
        assert high['angle_basis'] == 'rao80_clamped_high'
        assert mid['angle_basis'] == 'rao80_interpolated'

    def test_divergence_efficiency_follows_exit_angle(self, designer):
        """λ = ½(1 + cos θe); ε=10 -> 0.9851 (eski sabit θe=8° -> 0.9951)."""
        res = designer.design_nozzle(AT, 10.0, PC, 1.01325, 'bell', gamma=GAMMA)
        p = res['performance']
        theta_e = res['contour']['divergent']['exit_angle']
        assert p['divergence_efficiency'] == pytest.approx(
            0.5 * (1.0 + np.cos(np.radians(theta_e))), rel=1e-12)
        assert p['divergence_efficiency'] == pytest.approx(0.9851, abs=1e-4)

    def test_nozzle_efficiency_tracks_expansion_ratio(self, designer):
        """Toplam ayrık-kayıp çarpımı artık ε'ya duyarlı (eski: sabit 0.980)."""
        eta10 = designer.design_nozzle(AT, 10.0, PC, 1.01325, 'bell',
                                       gamma=GAMMA)['performance']['nozzle_efficiency']
        eta100 = designer.design_nozzle(AT, 100.0, PC, 1.01325, 'bell',
                                        gamma=GAMMA)['performance']['nozzle_efficiency']
        assert eta10 == pytest.approx(0.9704, abs=1e-3)
        assert eta100 > eta10

    def test_divergent_length_includes_throat_arc_term(self, designer):
        """Ld = 0.8·[ (re−rt) + R1(sec15°−1) ] / tan15°,  R1 = 1.5·rt."""
        eps = 10.0
        res = designer.design_nozzle(AT, eps, PC, 1.01325, 'bell', gamma=GAMMA)
        rt = res['basic_dimensions']['throat_diameter'] / 2.0     # mm
        re = res['basic_dimensions']['exit_diameter'] / 2.0       # mm
        t15 = np.tan(np.radians(15.0))
        sec15 = 1.0 / np.cos(np.radians(15.0))
        expected = 0.8 * ((re - rt) + 1.5 * rt * (sec15 - 1.0)) / t15
        assert res['contour']['divergent']['length'] == pytest.approx(
            expected, rel=1e-9)
        # Eksik terimli eski formülden UZUN olmalı
        old = 0.8 * (re - rt) / t15
        assert res['contour']['divergent']['length'] > old

    def test_bell_still_beats_conical(self, designer):
        """Fiziksel sıralama korunmalı: bell diverjans kaybı konikten az."""
        bell = designer.design_nozzle(AT, 10.0, PC, 1.01325, 'bell', gamma=GAMMA)
        con = designer.design_nozzle(AT, 10.0, PC, 1.01325, 'conical', gamma=GAMMA)
        assert (bell['performance']['divergence_efficiency'] >
                con['performance']['divergence_efficiency'])


# ---------------------------------------------------------------------------
# F049 — cidar kalınlığı basınçtan, kütle malzemeden
# ---------------------------------------------------------------------------
class TestWallThicknessAndMass:

    def test_thickness_matches_thin_wall_hoop(self, designer):
        """t = SF·p·r_t/σ_akma (Huzel & Huang SP-125 Böl. 4)."""
        At = 0.05
        res = designer.design_nozzle(At, 25.0, PC, 1.01325, 'bell', gamma=GAMMA)
        g = res['geometry']
        rt = np.sqrt(At / np.pi)                      # m
        expected = (g['wall_safety_factor'] * PC * 1e5 * rt
                    / g['wall_yield_strength']) * 1000.0
        assert g['wall_thickness'] == pytest.approx(expected, rel=1e-9)
        assert g['wall_thickness_basis'] == 'thin_wall_hoop'

    def test_old_ten_percent_rule_is_gone(self, designer):
        """Eski kural: t = maks(3 mm, 0.1·d_t) -> At=0.05 m² için 25.2 mm."""
        res = designer.design_nozzle(0.05, 25.0, PC, 1.01325, 'bell',
                                     gamma=GAMMA)
        g = res['geometry']
        dt_mm = res['basic_dimensions']['throat_diameter']
        assert g['wall_thickness'] < 0.5 * (0.1 * dt_mm)
        assert g['wall_thickness'] == pytest.approx(8.07, abs=0.05)

    def test_thickness_scales_with_pressure_not_only_size(self, designer):
        """Kalınlık oda basıncıyla DOĞRUSAL büyümeli (eski kural görmüyordu)."""
        low = designer.design_nozzle(0.01, 25.0, 20.0, 1.01325, 'bell',
                                     gamma=GAMMA)['geometry']['wall_thickness']
        high = designer.design_nozzle(0.01, 25.0, 80.0, 1.01325, 'bell',
                                      gamma=GAMMA)['geometry']['wall_thickness']
        assert high == pytest.approx(4.0 * low, rel=1e-9)

    def test_material_density_is_not_hardcoded(self, designer):
        """Yoğunluk artık 7850 sabiti değil, malzeme kaydından okunuyor."""
        steel = designer.design_nozzle(0.01, 25.0, PC, 1.01325, 'bell',
                                       gamma=GAMMA)['geometry']
        graph = designer.design_nozzle(0.01, 25.0, PC, 1.01325, 'bell',
                                       gamma=GAMMA,
                                       wall_material='graphite')['geometry']
        assert steel['wall_material_density'] == pytest.approx(7850.0)
        assert graph['wall_material_density'] == pytest.approx(1800.0)
        assert graph['estimated_mass'] != pytest.approx(steel['estimated_mass'],
                                                        rel=1e-3)

    def test_manufacturing_minimum_applies_to_tiny_motors(self, designer):
        """Çok küçük/alçak basınçlı motorda üretilebilirlik tabanı devreye girer."""
        g = designer.design_nozzle(1e-5, 10.0, 5.0, 1.01325, 'bell',
                                   gamma=GAMMA)['geometry']
        assert g['wall_thickness'] == pytest.approx(1.0, rel=1e-9)  # 1 mm
        assert g['wall_thickness_basis'] == 'manufacturing_minimum'

    def test_mass_is_surface_times_thickness_times_density(self, designer):
        g = designer.design_nozzle(0.01, 25.0, PC, 1.01325, 'bell',
                                   gamma=GAMMA)['geometry']
        expected = (g['surface_area'] / 1e6) * (g['wall_thickness'] / 1000.0) \
            * g['wall_material_density']
        assert g['estimated_mass'] == pytest.approx(expected, rel=1e-9)

    def test_unknown_material_falls_back_to_default(self, designer):
        g = designer.design_nozzle(0.01, 25.0, PC, 1.01325, 'bell', gamma=GAMMA,
                                   wall_material='unobtainium')['geometry']
        assert g['wall_material'] == 'steel'


# ---------------------------------------------------------------------------
# API korunumu — hybrid/solid/liquid bu anahtarları okuyor
# ---------------------------------------------------------------------------
class TestApiPreservation:

    def test_legacy_positional_call_still_works(self, designer):
        res = designer.design_nozzle(0.001, 10.0, 40.0, 0.5, 'bell')
        assert {'basic_dimensions', 'geometry', 'contour', 'performance',
                'nozzle_type'}.issubset(res.keys())
        assert {'wall_thickness', 'estimated_mass', 'surface_area',
                'volume'}.issubset(res['geometry'].keys())

    def test_new_performance_keys_are_additive(self, designer):
        res = designer.design_nozzle(0.001, 10.0, 40.0, 0.5, 'bell')
        p = res['performance']
        assert {'characteristic_velocity', 'thrust_coefficient_momentum',
                'thrust_coefficient_ideal', 'thrust_coefficient_actual',
                'specific_impulse', 'exit_velocity', 'nozzle_efficiency',
                'pressure_ratio', 'expansion_ratio'}.issubset(p.keys())
        assert {'exit_pressure', 'exit_mach', 'flow_separated',
                'effective_expansion_ratio'}.issubset(p.keys())

    def test_flow_properties_shares_the_same_mach_solver(self, designer):
        res = designer.design_nozzle(0.001, 10.0, 40.0, 0.5, 'bell', gamma=GAMMA)
        fp = designer.calculate_nozzle_flow_properties(
            res, 1.0, {'gamma': GAMMA, 'gas_constant': 350.0,
                       'temperature': 3400.0, 'pressure': PC})
        assert fp['exit']['mach_number'] > 1.0
        assert fp['exit']['pressure'] == pytest.approx(
            NozzleDesigner.exit_pressure_from_expansion(10.0, GAMMA, PC),
            rel=1e-6)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
