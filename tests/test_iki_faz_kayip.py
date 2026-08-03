"""İki-faz (tanecik yüklü) akış kayıp modülünün bekçi testleri (F4 temeli).

El hesabı çapaları:

* Hermsen (1981) — AIAA 96-2779'daki yayımlanmış RSRM örneği:
  Dt = 53.86 in, zeta_c = 0.262 mol/100 g, tau ~ 350 ms, Pc 630-880 psia
  (doymuş üstel bölge) -> d43 = 3.6304 * 53.86^0.2932 = 11.68 um.
  Kaynak metin: "The Hermsen correlation d43 for the FSM-4 conditions was
  calculated to be 11.68 um" (NASA NTRS 19960016118). Bu test aynı zamanda
  birim NEGATİF kontrolüdür: bağıntı inch/psia/ms yerine SI ile yazılırsa
  53.86 in = 1.368 m için 3.6304 * 1.368^0.2932 = 4.0 um çıkar ve test kırar.

* Sutton 9. baskı Eş. 3-35..3-39 el hesabı (gamma=1.20, MW=25 kg/kmol,
  beta=0.34, cs=1887.64 J/(kg K)):
    R_g  = 8314.462618/25 = 332.5785 J/(kg K)
    cp_g = 1.2*332.5785/0.2 = 1995.471 ; cv_g = 1662.893
    cp_mix = 0.66*1995.471 + 0.34*1887.64 = 1958.81  (Eş. 3-35)
    cv_mix = 0.66*1662.893 + 0.34*1887.64 = 1739.31
    k_mix  = 1958.81/1739.31 = 1.12620                (Eş. 3-39)
    R_mix  = 0.66*332.5785  = 219.502                 (Eş. 3-38)
    M_eff  = 25/0.66        = 37.879 kg/kmol
  Mayer bağıntısı bekçisi: cp_mix - cv_mix = R_mix (tam, boyut tutarlılığı).

* Tipik Al-yüklü APCP bandı (%16-18 Al -> beta = 0.302-0.340; Al -> Al2O3
  kütle oranı motorla aynı 101.96/(2*26.98) tabanından):
  kayıp tahmini %2-6 bandında kalmalı.
  Bandın künyesi: AFRPL kuralı "her %5 Al kütlesi için %1 Isp kaybı"
  (US Patent 8,051,640'ta aktarılır; %16-18 Al -> %3.2-3.6) ve NASA SP-8039
  (1971) Şek. 8 test-motoru Isp_d verim ailesi (40 wt% okside kadar
  ~%4.5-8 düşüş -> beta başına 0.11-0.20). Sutton 9. baskı Böl. 12
  (s. 459-460) alüminyumlu yakıt hız düzeltme katsayısını 0.90-0.96 verir.
"""

import math

import pytest

from hrma.analysis.two_phase_loss import (
    AL2O3_LIQUID_CP_J_KG_K,
    AL2O3_MOLAR_MASS_KG_KMOL,
    NOT_MODELLED,
    TwoPhaseLoss,
    VALIDITY_RANGES,
    two_phase_loss,
)
from hrma.constants import R_UNIVERSAL

# Motor şemasıyla aynı dönüşüm: %Al kütle kesri -> Al2O3 kütle kesri
AL_TO_AL2O3 = 101.96 / (2 * 26.98)

REQUIRED_KEYS = {
    'valid', 'validity', 'two_phase_loss_pct', 'two_phase_loss_band_pct',
    'loss_mechanism', 'loss_reference_frame', 'particle_diameter_um',
    'particle_diameter_basis', 'effective_properties', 'not_modelled',
    'diagnostics', 'model_note', '_basis',
}

# Tipik orta boy motor (geçerlilik pencerelerinin ortası)
TYPICAL = dict(condensed_mass_fraction=0.34, throat_diameter=0.05,
               chamber_pressure=50.0, residence_time_ms=20.0)


def evaluate(**overrides):
    args = dict(TYPICAL)
    args.update(overrides)
    return two_phase_loss.evaluate(**args)


# --------------------------------------------------------------------- #
# Şema ve girdi doğrulama
# --------------------------------------------------------------------- #

class TestSchemaAndValidation:
    def test_schema_keys(self):
        res = evaluate()
        assert REQUIRED_KEYS <= set(res.keys())
        assert res['valid'] is True
        assert res['loss_mechanism'] == 'velocity_and_thermal_lag'

    def test_nonsense_inputs_raise(self):
        with pytest.raises(ValueError, match="condensed_mass_fraction"):
            evaluate(condensed_mass_fraction=-0.1)
        with pytest.raises(ValueError, match="condensed_mass_fraction"):
            evaluate(condensed_mass_fraction=1.2)
        with pytest.raises(ValueError, match="throat_diameter"):
            evaluate(throat_diameter=-0.05)
        with pytest.raises(ValueError, match="chamber_pressure"):
            evaluate(chamber_pressure=0.0)
        with pytest.raises(ValueError, match="finite"):
            evaluate(chamber_pressure=float('nan'))
        with pytest.raises(ValueError, match="particle_diameter_um"):
            evaluate(particle_diameter_um=-3.0)

    def test_singleton_and_class_agree(self):
        res_a = evaluate()
        res_b = TwoPhaseLoss().evaluate(**TYPICAL)
        assert res_a['two_phase_loss_pct'] == pytest.approx(
            res_b['two_phase_loss_pct'])


# --------------------------------------------------------------------- #
# (a) Sıfır tanecik -> sıfır kayıp
# --------------------------------------------------------------------- #

class TestZeroParticle:
    def test_zero_beta_zero_loss(self):
        res = evaluate(condensed_mass_fraction=0.0)
        assert res['valid'] is True
        assert res['two_phase_loss_pct'] == 0.0
        assert res['two_phase_loss_band_pct'] == [0.0, 0.0]

    def test_zero_beta_needs_no_particle_inputs(self):
        # Dumansız (çift baz) durum: çap da kalış süresi de gerekmez.
        res = two_phase_loss.evaluate(
            condensed_mass_fraction=0.0, throat_diameter=0.05,
            chamber_pressure=50.0)
        assert res['two_phase_loss_pct'] == 0.0

    def test_zero_beta_effective_props_reduce_to_gas(self):
        res = evaluate(condensed_mass_fraction=0.0, gamma_gas=1.22,
                       molecular_weight_gas=26.0)
        eff = res['effective_properties']
        assert eff['applicable'] is True
        assert eff['gamma_mixture'] == pytest.approx(1.22)
        assert eff['effective_molecular_weight'] == pytest.approx(26.0)


# --------------------------------------------------------------------- #
# (b) Monotonluk
# --------------------------------------------------------------------- #

class TestMonotonicity:
    def test_loss_increases_with_mass_fraction_fixed_diameter(self):
        losses = [evaluate(condensed_mass_fraction=b,
                           particle_diameter_um=5.0)['two_phase_loss_pct']
                  for b in (0.05, 0.15, 0.25, 0.35)]
        assert all(b > a for a, b in zip(losses, losses[1:]))

    def test_loss_increases_with_mass_fraction_hermsen_path(self):
        # Hermsen yolunda beta hem katsayıyı hem d43'ü büyütür.
        losses = [evaluate(condensed_mass_fraction=b)['two_phase_loss_pct']
                  for b in (0.05, 0.15, 0.25, 0.35)]
        assert all(b > a for a, b in zip(losses, losses[1:]))

    def test_loss_increases_with_particle_diameter(self):
        losses = [evaluate(particle_diameter_um=d)['two_phase_loss_pct']
                  for d in (1.0, 3.0, 5.0, 8.0, 12.0)]
        assert all(b > a for a, b in zip(losses, losses[1:]))

    def test_band_increases_with_particle_diameter(self):
        bands = [evaluate(particle_diameter_um=d)['two_phase_loss_band_pct']
                 for d in (2.0, 6.0, 10.0)]
        assert bands[0][0] < bands[1][0] < bands[2][0]
        assert bands[0][1] < bands[1][1] < bands[2][1]

    def test_loss_decreases_with_motor_size_hermsen(self):
        # SP-8039 Şek. 19 eğilimi: büyük motor daha verimli. Hermsen yolunda
        # Dt^0.2932 (çap büyür) ile 1/Dt (akış süresi uzar) yarışır; net
        # kayıp Dt^-0.41 ile DÜŞMELİ.
        small = evaluate(throat_diameter=0.03)['two_phase_loss_pct']
        mid = evaluate(throat_diameter=0.06)['two_phase_loss_pct']
        large = evaluate(throat_diameter=0.12)['two_phase_loss_pct']
        assert small > mid > large


# --------------------------------------------------------------------- #
# (c) Tipik Al-yüklü APCP -> literatür bandı %2-6
# --------------------------------------------------------------------- #

class TestApcpLiteratureBand:
    @pytest.mark.parametrize("al_pct,d_t,p_c,tau", [
        (16.0, 0.030, 40.0, 10.0),   # küçük motor
        (17.0, 0.050, 50.0, 20.0),   # orta motor
        (18.0, 0.150, 70.0, 80.0),   # büyükçe motor
    ])
    def test_loss_in_2_to_6_percent_band(self, al_pct, d_t, p_c, tau):
        beta = (al_pct / 100.0) * AL_TO_AL2O3
        res = two_phase_loss.evaluate(
            condensed_mass_fraction=beta, throat_diameter=d_t,
            chamber_pressure=p_c, residence_time_ms=tau)
        assert res['valid'] is True
        assert 2.0 <= res['two_phase_loss_pct'] <= 6.0

    def test_band_brackets_central(self):
        res = evaluate()
        lo, hi = res['two_phase_loss_band_pct']
        assert lo <= res['two_phase_loss_pct'] <= hi

    def test_afrpl_anchor_within_band(self):
        # AFRPL kuralı boyut bağımsız DOĞRUSAL kuraldır: %17 Al -> %3.4 kayıp
        # (0.2 %/wt%Al). Karşılaştırma aynı çerçevede yapılmalı: referans
        # boyut durumu g(x)=1 (d43 = D43_REF = 5 um, Dt = D_THROAT_REF =
        # 0.10 m). Orada bandın alt kenarı kuralın TA KENDİSİDİR — tek fark
        # K = 0.2/1.8895 = 0.10585'in modülde 0.106'ya yuvarlanması.
        beta = 0.17 * AL_TO_AL2O3
        res = two_phase_loss.evaluate(
            condensed_mass_fraction=beta, throat_diameter=0.10,
            chamber_pressure=50.0, particle_diameter_um=5.0)
        assert res['valid'] is True
        assert res['diagnostics']['size_factor'] == pytest.approx(1.0)
        lo, hi = res['two_phase_loss_band_pct']
        afrpl_pct = 0.2 * 17.0            # kuralın doğrudan uygulaması: %3.4
        assert lo == pytest.approx(afrpl_pct, rel=2e-3)
        assert afrpl_pct <= hi


# --------------------------------------------------------------------- #
# (d) Birim/boyut tutarlılığı
# --------------------------------------------------------------------- #

class TestUnitsAndDimensions:
    def test_hermsen_reproduces_published_rsrm_value(self):
        """AIAA 96-2779: RSRM için Hermsen d43 = 11.68 um.

        Negatif birim kontrolü: bağıntı inch yerine metre ile çalışsaydı
        3.6304 * 1.368^0.2932 = 4.0 um çıkardı — 11.68'e asla ulaşamazdı.
        """
        # zeta_c = 0.262 mol/100 g -> beta = 0.262*101.96/100
        beta = 0.262 * AL2O3_MOLAR_MASS_KG_KMOL / 100.0
        d_t = 53.86 * 0.0254                      # 53.86 in -> m
        p_c = 880.0 / 14.503773773                # 880 psia -> bar
        res = two_phase_loss.evaluate(
            condensed_mass_fraction=beta, throat_diameter=d_t,
            chamber_pressure=p_c, residence_time_ms=350.0)
        assert res['particle_diameter_um'] == pytest.approx(11.68, abs=0.02)
        assert 'hermsen_1981' in res['particle_diameter_basis']

    def test_hermsen_hand_calculation_midrange(self):
        """Doymamış bölgede bağımsız el hesabı (formül değişirse kırar).

        Dt=0.05 m = 1.9685 in; Pc=50 bar = 725.19 psia; beta=0.34 ->
        zeta_c = 34/101.96 = 0.33346; tau=20 ms:
          üstel arg = 0.0008163*0.33346*725.19*20 = 3.94836
          d43 = 3.6304 * 1.9685^0.2932 * (1-exp(-3.94836)) = 4.3436 um
        """
        res = evaluate()
        expected = (3.6304 * (0.05 * 1000 / 25.4) ** 0.2932
                    * (1.0 - math.exp(-0.0008163 * (34.0 / 101.96)
                                      * (50.0 * 14.503773773) * 20.0)))
        assert res['particle_diameter_um'] == pytest.approx(expected,
                                                            rel=1e-12)
        assert res['particle_diameter_um'] == pytest.approx(4.3436, abs=0.01)

    def test_effective_properties_hand_calculation(self):
        res = evaluate(gamma_gas=1.20, molecular_weight_gas=25.0,
                       particle_diameter_um=5.0)
        eff = res['effective_properties']
        assert eff['applicable'] is True
        assert eff['gamma_mixture'] == pytest.approx(1.12620, abs=2e-5)
        assert eff['effective_molecular_weight'] == pytest.approx(
            37.879, abs=1e-3)
        assert eff['effective_gas_constant'] == pytest.approx(219.502,
                                                              abs=1e-2)
        assert eff['mixture_cp'] == pytest.approx(1958.81, abs=0.1)

    def test_mixture_mayer_relation_and_gas_constant_consistency(self):
        # Boyut bekçileri: R_mix*M_eff = R_u ve cp_mix - cv_mix = R_mix.
        res = evaluate(gamma_gas=1.25, molecular_weight_gas=28.0,
                       particle_diameter_um=4.0)
        eff = res['effective_properties']
        assert (eff['effective_gas_constant']
                * eff['effective_molecular_weight']) == pytest.approx(
                    R_UNIVERSAL, rel=1e-12)
        beta = TYPICAL['condensed_mass_fraction']
        r_gas = R_UNIVERSAL / 28.0
        cv_mix = eff['mixture_cp'] / eff['gamma_mixture']
        assert eff['mixture_cp'] - cv_mix == pytest.approx(
            (1 - beta) * r_gas, rel=1e-12)

    def test_effective_gamma_decreases_with_beta(self):
        gammas = [evaluate(condensed_mass_fraction=b, gamma_gas=1.22,
                           molecular_weight_gas=26.0,
                           particle_diameter_um=5.0)
                  ['effective_properties']['gamma_mixture']
                  for b in (0.0, 0.1, 0.2, 0.34)]
        assert all(b < a for a, b in zip(gammas, gammas[1:]))
        assert all(g > 1.0 for g in gammas)

    def test_al2o3_cp_constant_matches_janaf(self):
        # NIST-JANAF Al2O3(l): 192.464 J/(mol K) / 0.10196 kg/mol
        assert AL2O3_LIQUID_CP_J_KG_K == pytest.approx(1887.64, abs=0.1)

    def test_loss_is_a_percentage(self):
        res = evaluate()
        assert 0.0 < res['two_phase_loss_pct'] < 100.0


# --------------------------------------------------------------------- #
# Geçerlilik bekçisi: aralık dışı -> beyanlı ret, sessiz ekstrapolasyon yok
# --------------------------------------------------------------------- #

class TestValidityGuard:
    @pytest.mark.parametrize("overrides,needle", [
        (dict(condensed_mass_fraction=0.5), 'condensed_mass_fraction'),
        (dict(chamber_pressure=2.0), 'chamber_pressure_bar'),
        (dict(chamber_pressure=200.0), 'chamber_pressure_bar'),
        (dict(throat_diameter=0.01), 'throat_diameter_m'),
        (dict(throat_diameter=2.0), 'throat_diameter_m'),
        (dict(particle_diameter_um=20.0), 'particle_diameter_um'),
        (dict(residence_time_ms=500.0), 'residence_time_ms'),
    ])
    def test_out_of_range_returns_declared_invalid(self, overrides, needle):
        res = evaluate(**overrides)
        assert res['valid'] is False
        # Sessiz ekstrapolasyon yasağı: sayı ÜRETİLMEZ.
        assert res['two_phase_loss_pct'] is None
        assert res['two_phase_loss_band_pct'] is None
        assert any(needle in v for v in res['validity']['violations'])
        assert 'GEÇERSİZ ARALIK' in res['model_note']

    def test_missing_diameter_and_residence_time_declared(self):
        res = two_phase_loss.evaluate(
            condensed_mass_fraction=0.34, throat_diameter=0.05,
            chamber_pressure=50.0)
        assert res['valid'] is False
        assert res['two_phase_loss_pct'] is None
        assert any('residence_time_ms' in v
                   for v in res['validity']['violations'])

    def test_ranges_carry_sources(self):
        res = evaluate()
        ranges = res['validity']['ranges']
        assert set(ranges) == set(VALIDITY_RANGES)
        for entry in ranges.values():
            assert entry['source']  # her pencerenin künyesi var

    def test_large_d43_blocks_equilibrium_correction_only(self):
        # 10-15 um arası: kayıp tahmini hâlâ geçerli (Sutton 15 um sınırı),
        # ama denge (etkin özellik) önerisi 10 um üstünde ÜRETİLMEZ.
        res = evaluate(particle_diameter_um=12.0, gamma_gas=1.20,
                       molecular_weight_gas=25.0)
        assert res['valid'] is True
        assert res['two_phase_loss_pct'] is not None
        eff = res['effective_properties']
        assert eff['applicable'] is False
        assert 'gamma_mixture' not in eff


# --------------------------------------------------------------------- #
# NOT_MODELLED beyanı ve tutarlılık bekçileri
# --------------------------------------------------------------------- #

class TestDeclarations:
    def test_not_modelled_declaration_present(self):
        expected = {'particle_size_distribution', 'agglomeration_breakup',
                    'nozzle_wall_impingement', 'solidification_lag'}
        assert set(NOT_MODELLED) == expected
        for res in (evaluate(), evaluate(condensed_mass_fraction=0.0),
                    evaluate(condensed_mass_fraction=0.5)):
            assert set(res['not_modelled']) == expected

    def test_basis_fields_present(self):
        res = evaluate()
        assert 'Sutton' in res['_basis']
        assert 'Hermsen' in res['_basis'] or 'hermsen' in res['_basis']
        assert 'SP-8039' in res['_basis']

    def test_engine_coefficient_single_definition_point(self):
        # Magic-number bekçisi: merkez katsayı motor tarafındaki
        # TWO_PHASE_LOSS_COEFF'in TA KENDİSİ olmalı (tembel import).
        engine = pytest.importorskip('hrma.engines.solid_rocket_engine')
        res = evaluate()
        assert res['diagnostics']['k_central'] == pytest.approx(
            engine.TWO_PHASE_LOSS_COEFF)
        # Al -> Al2O3 dönüşüm tabanı da motorla aynı 101.96/2x26.98.
        assert AL_TO_AL2O3 == pytest.approx(engine.AL_TO_AL2O3_MASS_RATIO)

    def test_band_anchor_ordering(self):
        k_lo, k_hi = TwoPhaseLoss.K_BAND
        assert k_lo < TwoPhaseLoss.K_CENTRAL_FALLBACK < k_hi
