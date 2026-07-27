"""Cıvatalı bağlantı + Goodman yorulma doğrulama testleri (Dalga 3).

BÖLÜM 1 — BoltedJointAnalyzer (Shigley 10th ed. Ch. 8) el hesabı çapaları:

  M8 sınıf 8.8 (ISO 898-1: A_t = 36.6 mm², S_p = 580 MPa, d ≤ 16 mm):
    F_p = A_t·S_p = 36.6e-6 · 580e6 = 21 228 N
    F_i = 0.75·F_p = 15 921 N                     (Shigley Eq. 8-31)
    T_kuru  = K·F_i·d = 0.20·15921·0.008 = 25.47 N·m   (Eq. 8-27)
    T_yağlı = 0.15·15921·0.008 = 19.11 N·m

  Rijitlik (M8, l = 20 mm, çelik üyeler, E = 200 GPa — materials_db 'steel'):
    k_b = A_t·E/l = 36.6e-6·200e9/0.020 = 366.0 MN/m
    k_m = E·d·A·exp(B·d/l) = 200e9·0.008·0.78715·exp(0.62873·0.4)
        = 1.2594e9 · 1.28594 = 1.6196e9 N/m        (Wileman, Eq. 8-23)
    C   = 366.0/(366.0+1619.6) = 0.1843

  Basınç yükü: 20 bar × π/4×(0.120 m)² = 22 619.5 N; 8 cıvata → 2827.4 N/cıvata.

BÖLÜM 2 — Goodman yorulma (structural_analysis._analyze_fatigue).

  DAVRANIŞSAL BEKLENTİ GÜNCELLEMESİ GEREKÇESİ: Eski sürüm (a) MPa gelen
  gerilmeyi Pa'lık fatigue_limit ile oranlıyordu (SF ~1e6 kat şişik),
  (b) tam σ_max'ı genlik sayıp ortalama gerilmeyi ihmal ediyordu,
  (c) dayanaksız 'b=10' Basquin sabiti kullanıyordu. Yeni fizik:
  R≈0 basınç çevrimi → σ_a = σ_m = σ_max/2 ve düzeltilmiş Goodman
  (Shigley Eq. 6-46): 1/n_f = σ_a/S_e + σ_m/S_u.

  El hesabı (steel_4130: S_e = 230 MPa, S_u = 730 MPa — materials_db):
    σ_max = 200 MPa → σ_a = σ_m = 100:
       1/n = 100/230 + 100/730 = 0.43478 + 0.13699 = 0.57177 → n = 1.7490
    σ_max = 500 MPa → σ_a = σ_m = 250:
       1/n = 250/230 + 250/730 = 1.42901 → n = 0.6998 (sonlu ömür)
       σ_ar = 250/(1−250/730) = 380.21 MPa

  SONLU ÖMÜR ÇAPASI GÜNCELLENDİ (v2.6.2, fizik denetimi bulgusu F181):
  Basquin çapası f (Shigley Fig. 6-18, 10^3 çevrimdeki dayanım kesri) daha
  önce SABİT 0.9 alınıyordu; oysa f, S_ut ile düşer. v2.6.2 bunu
  _shigley_fatigue_strength_fraction(S_u) ile eğriye bağladı. steel_4130
  (S_u = 730 MPa) için el hesabı:
       f = 0.82 + (730−689)/(1034−689)·(0.79−0.82) = 0.82 − 0.003565
         = 0.81643            (Fig. 6-18 çapaları: 689 MPa→0.82, 1034→0.79)
       f·S_u = 595.997 MPa
       a = 595.997²/230 = 1544.40 MPa                     (Shigley Eq. 6-14)
       b = −log10(595.997/230)/3 = −0.41352/3 = −0.137839 (Shigley Eq. 6-15)
       N = (380.21/1544.40)^(1/b) = 0.246185^(−7.25485) = 2.608e4 çevrim
  Eski f = 0.9 sabitiyle aynı hesap 3.66e4 veriyordu; aradaki 1.40 kat, f'in
  üstel konumundan gelir (N ∝ (σ_ar/a)^(1/b)). Yeni değer KONSERVATİF yöndedir
  (daha kısa ömür), eski test çapası bu yüzden güncellendi — eşik gevşetilmedi.
"""

import numpy as np
import pytest

from hrma.analysis.bolted_joint import (
    BoltedJointAnalyzer, analyze_bolted_joint, THREAD_STRESS_AREA_MM2)
from hrma.analysis.structural_analysis import (
    StructuralAnalyzer, _shigley_fatigue_strength_fraction)
from hrma.data.materials_db import get_material


# ---------------------------------------------------------------------------
# Diş alanları ve sınıf dayanımları (ISO 898-1)
# ---------------------------------------------------------------------------

class TestTablesISO:
    def test_stress_areas_match_iso_898_1(self):
        """ISO 898-1:2013 Table A.1 (= Shigley Table 8-1) örnek değerleri."""
        assert THREAD_STRESS_AREA_MM2['M4'] == pytest.approx(8.78)
        assert THREAD_STRESS_AREA_MM2['M8'] == pytest.approx(36.6)
        assert THREAD_STRESS_AREA_MM2['M10'] == pytest.approx(58.0)
        assert THREAD_STRESS_AREA_MM2['M12'] == pytest.approx(84.3)
        assert THREAD_STRESS_AREA_MM2['M24'] == pytest.approx(353.0)

    def test_class_88_diameter_split(self):
        """ISO 898-1: 8.8 için S_p = 580 MPa (d≤16), 600 MPa (d>16)."""
        a8 = BoltedJointAnalyzer(size='M8', property_class='8.8')
        a20 = BoltedJointAnalyzer(size='M20', property_class='8.8')
        assert a8.props['S_p'] == pytest.approx(580e6)
        assert a20.props['S_p'] == pytest.approx(600e6)

    def test_class_109_129_strengths(self):
        a10 = BoltedJointAnalyzer(size='M10', property_class='10.9')
        a12 = BoltedJointAnalyzer(size='M12', property_class='12.9')
        assert a10.props['S_p'] == pytest.approx(830e6)
        assert a10.props['S_u'] == pytest.approx(1040e6)
        assert a12.props['S_p'] == pytest.approx(970e6)
        assert a12.props['S_u'] == pytest.approx(1220e6)

    def test_a2_70_stainless(self):
        """ISO 3506-1 sınıf 70: R_m ≥ 700, R_p0.2 ≥ 450 MPa."""
        a = BoltedJointAnalyzer(size='M8', property_class='A2-70')
        assert a.props['S_u'] == pytest.approx(700e6)
        assert a.props['S_y'] == pytest.approx(450e6)
        assert a.props['stainless'] is True

    def test_invalid_inputs_rejected(self):
        with pytest.raises(ValueError):
            BoltedJointAnalyzer(size='M7')
        with pytest.raises(ValueError):
            BoltedJointAnalyzer(property_class='9.9')
        with pytest.raises(ValueError):
            BoltedJointAnalyzer(bolt_count=0)
        with pytest.raises(ValueError):
            BoltedJointAnalyzer(grip_length_mm=-5.0)


# ---------------------------------------------------------------------------
# Ön-yük, tork — M8 8.8 el hesabı (Shigley örneği tarzı)
# ---------------------------------------------------------------------------

class TestPreloadAndTorque:
    @pytest.fixture
    def m8(self):
        return BoltedJointAnalyzer(size='M8', property_class='8.8',
                                   bolt_count=8, grip_length_mm=20.0,
                                   member_material='steel')

    def test_proof_load_hand_calc(self, m8):
        """F_p = A_t·S_p = 36.6e-6·580e6 = 21 228 N."""
        assert m8.preload()['proof_load_N'] == pytest.approx(21228, rel=1e-3)

    def test_preload_hand_calc_reusable(self, m8):
        """F_i = 0.75·F_p = 15 921 N (Shigley Eq. 8-31, yeniden kullanım)."""
        assert m8.preload()['preload_N'] == pytest.approx(15921, rel=1e-3)

    def test_preload_permanent_fraction(self):
        a = BoltedJointAnalyzer(size='M8', property_class='8.8',
                                reusable=False)
        assert a.preload()['preload_fraction'] == pytest.approx(0.90)

    def test_torque_dry_hand_calc(self, m8):
        """T = 0.20·15921·0.008 = 25.47 N·m."""
        tq = m8.torque()
        assert tq['K_nut_factor'] == pytest.approx(0.20)
        assert tq['recommended_torque_Nm'] == pytest.approx(25.47, rel=1e-3)

    def test_torque_lubricated_hand_calc(self):
        """T = 0.15·15921·0.008 = 19.11 N·m."""
        a = BoltedJointAnalyzer(size='M8', property_class='8.8',
                                lubricated=True)
        tq = a.torque()
        assert tq['K_nut_factor'] == pytest.approx(0.15)
        assert tq['recommended_torque_Nm'] == pytest.approx(19.11, rel=1e-3)

    def test_preload_uncertainty_reported(self, m8):
        """Tork kontrollü sıkmada ±%25 ön-yük saçılımı raporda olmalı."""
        tq = m8.torque()
        assert tq['preload_uncertainty_pct'] == pytest.approx(25.0)
        F_i = m8.preload()['preload_N']
        assert tq['preload_scatter_band_N'][0] == pytest.approx(0.75 * F_i)
        assert tq['preload_scatter_band_N'][1] == pytest.approx(1.25 * F_i)


# ---------------------------------------------------------------------------
# Rijitlik, yük paylaşımı, ayrılma
# ---------------------------------------------------------------------------

class TestStiffnessAndLoadSharing:
    def test_joint_constant_hand_calc_steel(self):
        """C = 366.0/(366.0+1619.6) = 0.1843 (Wileman, Shigley Eq. 8-23)."""
        a = BoltedJointAnalyzer(size='M8', property_class='8.8',
                                grip_length_mm=20.0, member_material='steel')
        st = a.stiffness()
        assert st['k_bolt_N_per_m'] == pytest.approx(366.0e6, rel=1e-3)
        assert st['k_member_N_per_m'] == pytest.approx(1.6196e9, rel=1e-3)
        assert st['joint_constant_C'] == pytest.approx(0.1843, rel=2e-3)

    def test_aluminum_member_uses_aluminum_constants(self):
        a = BoltedJointAnalyzer(member_material='aluminum_6061')
        st = a.stiffness()
        assert st['member_constants'] == 'aluminum'
        # E_al < E_çelik → k_m daha düşük → C daha yüksek olmalı
        st_steel = BoltedJointAnalyzer(member_material='steel').stiffness()
        assert st['joint_constant_C'] > st_steel['joint_constant_C']

    def test_load_sharing_relations_exact(self):
        """F_b = F_i + C·P ve F_m = F_i − (1−C)·P (Shigley Eq. 8-24/8-25)."""
        a = BoltedJointAnalyzer(size='M8', property_class='8.8',
                                bolt_count=8, member_material='steel')
        res = a.analyze(pressure_bar=20.0, seal_diameter_mm=120.0)
        F_i = res['preload']['preload_N']
        C = res['stiffness']['joint_constant_C']
        P = res['loads']['external_load_per_bolt_N']
        assert res['loads']['bolt_total_load_N'] == pytest.approx(
            F_i + C * P, rel=1e-12)
        assert res['loads']['member_clamp_load_N'] == pytest.approx(
            F_i - (1.0 - C) * P, rel=1e-12)

    def test_pressure_load_hand_calc(self):
        """20 bar · π/4·(0.12 m)² = 22 619.5 N; 8 cıvata → 2827.4 N."""
        res = analyze_bolted_joint(pressure_bar=20.0, seal_diameter_mm=120.0,
                                   bolt_count=8, size='M8',
                                   property_class='8.8',
                                   member_material='steel')
        assert res['loads']['total_external_load_N'] == pytest.approx(
            22619.5, rel=1e-4)
        assert res['loads']['external_load_per_bolt_N'] == pytest.approx(
            2827.4, rel=1e-4)

    def test_no_separation_at_moderate_load(self):
        res = analyze_bolted_joint(pressure_bar=20.0, seal_diameter_mm=120.0,
                                   bolt_count=8, member_material='steel')
        assert res['separation']['separated'] is False
        assert res['safety_factors']['separation_factor_n0'] > 1.5
        assert res['safety_factors']['proof_SF'] > 1.0

    def test_separation_detected_under_excess_load(self):
        """Cıvata başına dış yük F_i/(1−C)'yi aşarsa bağlantı ayrılır."""
        a = BoltedJointAnalyzer(size='M8', property_class='8.8',
                                bolt_count=4, member_material='steel')
        # F_i ≈ 15.9 kN, C ≈ 0.18 → ayrılma ~19.5 kN/cıvata; 25 kN yükle
        res = a.analyze(external_axial_load_n=4 * 25000.0)
        assert res['separation']['separated'] is True
        assert res['safety_factors']['separation_factor_n0'] < 1.0
        assert any('SEPARATION' in w for w in res['warnings'])

    def test_a2_70_large_size_warning(self):
        res = BoltedJointAnalyzer(size='M24', property_class='A2-70') \
            .analyze(pressure_bar=10.0, seal_diameter_mm=100.0)
        assert any('A2-70' in w for w in res['warnings'])
        res_m8 = BoltedJointAnalyzer(size='M8', property_class='A2-70') \
            .analyze(pressure_bar=10.0, seal_diameter_mm=100.0)
        assert not any('A2-70' in w for w in res_m8['warnings'])

    def test_preload_scatter_applied_to_safety_factors(self):
        """F031: ±%25 ön-yük saçılımı SF'lere fiilen uygulanmalı.

        Denetim referans vakası (ölçüldü): M10 8.8, l=30 mm, çelik üye,
        8 cıvata, 60 bar x 160 mm sızdırmazlık çapı. A_t=58 mm²,
        S_p·A_t=33.64 kN, F_i=25.23 kN, C=0.16609, P_cıvata=15.08 kN.
        Eski sürüm nominal n_proof=1.213 raporluyor, +%25 ön-yükte cıvatanın
        proof dayanımını AŞTIĞINI (n=0.988) hiç görmüyordu.
        Kaynak: NASA-STD-5020A Sec. 6.2; Shigley 10th ed. Sec. 8-8.
        """
        a = BoltedJointAnalyzer(size='M10', property_class='8.8',
                                bolt_count=8, grip_length_mm=30.0,
                                member_material='steel')
        res = a.analyze(pressure_bar=60.0, seal_diameter_mm=160.0)
        pre, sf = res['preload'], res['safety_factors']
        F_i = pre['preload_N']
        assert pre['preload_max_N'] == pytest.approx(1.25 * F_i, rel=1e-12)
        assert pre['preload_min_N'] == pytest.approx(0.75 * F_i, rel=1e-12)
        # Nominal değerler korunuyor (geriye dönük alanlar):
        assert sf['proof_SF'] == pytest.approx(1.213, rel=2e-3)
        assert sf['separation_factor_n0'] == pytest.approx(2.006, rel=2e-3)
        # Yöneten (saçılım ucu) değerler:
        assert sf['proof_SF_min'] == pytest.approx(0.988, rel=2e-3)
        assert sf['separation_factor_n0_min'] == pytest.approx(1.505, rel=2e-3)
        # ...ve proof aşımı artık uyarı üretiyor.
        assert any('proof strength at maximum preload' in w
                   for w in res['warnings'])

    def test_scatter_factors_bracket_nominal(self):
        """Saçılım uçları nominali doğru yönde sıkıştırmalı."""
        res = analyze_bolted_joint(pressure_bar=20.0, seal_diameter_mm=120.0,
                                   bolt_count=8, member_material='steel')
        sf = res['safety_factors']
        assert sf['proof_SF_min'] < sf['proof_SF']
        assert sf['separation_factor_n0_min'] < sf['separation_factor_n0']
        assert sf['overload_factor_nL_min'] < sf['overload_factor_nL']
        # 0.75 ön-yükle ayrılma faktörü tam 0.75 katına inmeli (F_i lineer).
        assert sf['separation_factor_n0_min'] == pytest.approx(
            0.75 * sf['separation_factor_n0'], rel=1e-12)

    def test_separation_decision_uses_minimum_preload(self):
        """Ayrılma kararı MİNİMUM ön-yükte verilmeli (F031)."""
        a = BoltedJointAnalyzer(size='M8', property_class='8.8',
                                bolt_count=4, member_material='steel')
        # F_i = 15.921 kN, C = 0.1843 -> nominal ayrılma yükü 19.52 kN/cıvata,
        # minimum ön-yükte 14.64 kN/cıvata. Aradaki 17 kN nominalde 'ayrılmadı'
        # görünür, saçılım altında ayrılır.
        res = a.analyze(external_axial_load_n=4 * 17000.0)
        assert res['separation']['separated_nominal_preload'] is False
        assert res['separation']['separated'] is True
        assert res['safety_factors']['separation_factor_n0'] > 1.0
        assert res['safety_factors']['separation_factor_n0_min'] < 1.0
        assert any('SEPARATION' in w for w in res['warnings'])

    def test_result_structure_json_friendly(self):
        res = analyze_bolted_joint(pressure_bar=30.0, seal_diameter_mm=150.0,
                                   bolt_count=12, size='M10',
                                   property_class='10.9')
        for key in ('bolt', 'preload', 'torque', 'stiffness', 'loads',
                    'safety_factors', 'separation', 'warnings',
                    'assumptions', 'source'):
            assert key in res
        assert res['bolt']['strength_source'].startswith('ISO')


# ---------------------------------------------------------------------------
# Goodman yorulma düzeltmesi
# ---------------------------------------------------------------------------

class TestGoodmanFatigue:
    """_analyze_fatigue Goodman düzeltmesi (Dalga 3).

    Bu testler ESKİ davranışın (birim hatası + genlik=tepe + b=10) yerine
    fiziksel Goodman modelini doğrular; gerekçe modül docstring'inde.
    """

    @pytest.fixture
    def analyzer(self):
        return StructuralAnalyzer()

    @pytest.fixture
    def mat(self):
        # steel_4130: S_e = 230 MPa, S_u = 730 MPa (materials_db, kaynaklı)
        return get_material('steel_4130')

    def test_goodman_hand_calc_infinite_life(self, analyzer, mat):
        """σ_max = 200 MPa → n_f = 1/(100/230 + 100/730) = 1.7490 (SAFE)."""
        res = analyzer._analyze_fatigue(200.0, 10.0, mat)
        assert res['fatigue_safety_factor'] == pytest.approx(1.7490, rel=1e-3)
        assert res['stress_amplitude'] == pytest.approx(100.0)  # σ_max/2
        assert res['mean_stress'] == pytest.approx(100.0)
        assert res['estimated_life'] == 'Infinite'
        assert res['fatigue_status'] == 'SAFE'

    def test_goodman_marginal_band(self, analyzer, mat):
        """σ_max = 300 MPa → n_f = 1/(150/230+150/730) = 1.166 → MARGINAL."""
        res = analyzer._analyze_fatigue(300.0, 10.0, mat)
        assert res['fatigue_safety_factor'] == pytest.approx(1.1660, rel=1e-3)
        assert res['fatigue_status'] == 'MARGINAL'
        assert res['estimated_life'] == 'Infinite'  # Goodman doğrusu altında

    def test_goodman_finite_life_hand_calc(self, analyzer, mat):
        """σ_max = 500 MPa → n_f = 0.6998; Basquin N ≈ 2.61e4 çevrim.

        El hesabı (v2.6.2 F181 sonrası — f artık S_ut'ye bağlı):
          σ_a = σ_m = 250 MPa; σ_ar = 250/(1−250/730) = 380.21 MPa
          f   = 0.82 + (730−689)/(1034−689)·(0.79−0.82) = 0.81643
                (Shigley Fig. 6-18 çapaları arasında doğrusal enterpolasyon)
          a   = (0.81643·730)²/230 = 595.997²/230 = 1544.40 MPa   (Eq. 6-14)
          b   = −log10(595.997/230)/3 = −0.137839                 (Eq. 6-15)
          N   = (380.21/1544.40)^(1/b) = 0.246185^(−7.25485) = 26 080

        ESKİ ÇAPA 3.67e4 İDİ: f SABİT 0.9 alındığında a = 1876.73 MPa,
        b = −0.151946 ve N = 36 589 çıkıyordu. v2.6.2 f'i eğriye bağladı
        (bulgu F181, konservatif yön: ömür 1.40 kat KISALDI); test çapası
        koda değil EL HESABINA göre yenilendi, tolerans (rel=0.05)
        DEĞİŞTİRİLMEDİ.
        """
        res = analyzer._analyze_fatigue(500.0, 10.0, mat)
        assert res['fatigue_safety_factor'] == pytest.approx(0.6998, rel=1e-3)
        # Ömrü hangi çapanın sürüklediği tek bakışta görünsün: f eğrisi
        # değişirse önce BU assert patlar, ömür assert'i değil.
        assert _shigley_fatigue_strength_fraction(
            mat['ultimate_strength']) == pytest.approx(0.81643, rel=1e-4)
        assert isinstance(res['estimated_life'], float)
        assert res['estimated_life'] == pytest.approx(2.608e4, rel=0.05)
        # 25 tasarım çevrimine karşı bol marj → sonlu ömür ama MARGINAL
        assert res['cycle_margin'] == pytest.approx(
            res['estimated_life'] / res['design_cycles'], rel=1e-9)
        assert res['fatigue_status'] == 'MARGINAL'

    def test_r_zero_relation(self, analyzer, mat):
        """R≈0 basınç çevrimi: σ_a = σ_m = σ_max/2 kimliği."""
        res = analyzer._analyze_fatigue(240.0, 5.0, mat)
        assert res['stress_amplitude'] == pytest.approx(res['max_stress'] / 2)
        assert res['mean_stress'] == pytest.approx(res['max_stress'] / 2)
        assert res['stress_ratio_R'] == 0.0

    def test_cycle_count_parameter(self, analyzer, mat):
        """Çevrim sayısı parametresi (test kampanyası + uçuş) çalışmalı."""
        res_default = analyzer._analyze_fatigue(500.0, 10.0, mat)
        res_100 = analyzer._analyze_fatigue(500.0, 10.0, mat,
                                            design_cycles=100)
        assert res_default['design_cycles'] == 25
        assert res_100['design_cycles'] == 100
        assert res_100['cycle_margin'] == pytest.approx(
            res_default['cycle_margin'] * 25.0 / 100.0, rel=1e-9)

    def test_zero_stress_safe(self, analyzer, mat):
        res = analyzer._analyze_fatigue(0.0, 10.0, mat)
        assert res['fatigue_safety_factor'] == float('inf')
        assert res['fatigue_status'] == 'SAFE'

    def test_unit_bug_fixed_in_full_pipeline(self, analyzer):
        """Tam boru hattında SF artık fiziksel mertebede (birim hatası yok).

        ESKİ hata: MPa/Pa karışımı SF'yi ~1e6 katına şişiriyordu. Yeni SF
        makul mühendislik bandında (0.05–100) olmalı ve eski sözleşme
        anahtarları korunmalı.
        """
        motor = {
            'chamber_pressure': 50.0,   # bar
            'chamber_diameter': 0.15,   # m
            'chamber_length': 0.6,      # m
            'throat_diameter': 0.04,    # m
            'nozzle_type': 'conical',
            'burn_time': 10.0,
        }
        res = analyzer.analyze_structure(motor, material='steel_4130')
        fa = res['fatigue_analysis']
        for key in ('fatigue_status', 'estimated_cycles', 'estimated_life',
                    'fatigue_safety_factor', 'fatigue_limit',
                    'stress_amplitude'):
            assert key in fa
        assert 0.05 < fa['fatigue_safety_factor'] < 100.0
        assert fa['model'].startswith('Modified Goodman')


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
