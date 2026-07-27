"""Basınçlı kap + kopma modülü doğrulama testleri.

El hesabı referans vakası (tüm sayılar elle / bağımsız hesapla türetildi):
    MEOP = 60 bar (6 MPa), iç çap D = 150 mm (R = 75 mm), AISI 4130
    (σ_y = 460 MPa, σ_u = 730 MPa, oda sıcaklığı), t = 5 mm, E = 1.0.

  ASME VIII (S = min(730/3.5, 460/1.5) = 208.571 MPa):
    UG-27  t_req = 6·75/(208.571 − 0.6·6)        = 2.1954 mm
    MAWP        = 208.571·5/(75 + 0.6·5)         = 13.3700 MPa = 133.70 bar
    UG-99 hidro = 1.3·MAWP (oda sıcaklığı)       = 173.81 bar
    UG-32 elips = 6·150/(2·208.571 − 0.2·6)      = 2.1638 mm
    UG-32 tori  = 0.885·6·150/(208.571 − 0.1·6)  = 3.8299 mm
    UG-32 yarım = 6·75/(2·208.571 − 0.2·6)       = 1.0819 mm

  AIAA S-080 (F149, v2.6.2 — ORTALAMA yarıçap membran formu):
    proof = 90 bar, gerekli burst = 120 bar
    σ = P·(r + t/2)/t  ⇒  t = P·r/(σ − 0.5·P)
    t_req = max(1.5·6·75/(460 − 0.75·6), 2.0·6·75/(730 − 1.0·6))
          = max(675/455.5, 900/724) = max(1.481888, 1.243094) = 1.4819 mm
    Referans (tam Lamé, σ_θ(a) = P(b²+a²)/(b²−a²)): proof 1.482031 mm,
    burst 1.243179 mm → ortalama yarıçap formu %0.01 sapıyor. Eski iç
    yarıçap formu (1.4674 mm) %0.99 İNCE kalıyordu: o cidarda proof
    basıncında gerçek çeper gerilmesi 464.5 MPa > σ_y = 460 MPa (akma).

  Kopma (t = 5 mm):
    Faupel   = (2/√3)·460·(2 − 460/730)·ln(80/75) = 46.959 MPa = 469.59 bar
    İnce cid.= 2·730·5/155                        = 47.097 MPa = 471.0 bar
    actual   = min                                = 469.59 bar
    burst_margin (S-080) = 469.59/120 = 3.913 → PASS
"""

import math

import pytest

from hrma.analysis.pressure_vessel import (
    PressureVesselAnalyzer,
    AIAA_PROOF_FACTOR, AIAA_BURST_FACTOR,
    ALLOWED_WELD_EFFICIENCIES, MARGINAL_BURST_MARGIN,
)


# Referans vaka parametreleri
CASE = dict(meop_bar=60.0, inner_diameter_mm=150.0,
            material='steel_4130', wall_thickness_mm=5.0)


@pytest.fixture
def pv():
    return PressureVesselAnalyzer()  # varsayılan aiaa_s080


@pytest.fixture
def asme(pv):
    def run(**kw):
        args = dict(CASE)
        args.update(kw)
        return pv.analyze(code_mode='asme_viii', **args)
    return run


@pytest.fixture
def aiaa(pv):
    def run(**kw):
        args = dict(CASE)
        args.update(kw)
        return pv.analyze(code_mode='aiaa_s080', **args)
    return run


# ---------------------------------------------------------------------------
# ASME VIII — el hesabı referansları
# ---------------------------------------------------------------------------
class TestASMEHandCalcs:
    def test_cylinder_required_thickness_ug27(self, asme):
        # t = P·R/(S·E − 0.6P) = 6·75/(208.571 − 3.6) = 2.1954 mm
        out = asme()
        assert out['required_thickness_mm'] == pytest.approx(2.1954, rel=1e-3)

    def test_mawp_back_calculation_ug27(self, asme):
        # MAWP = S·E·t/(R + 0.6t) = 208.571·5/78 = 133.70 bar
        out = asme()
        assert out['mawp_bar'] == pytest.approx(133.70, rel=1e-3)

    def test_mawp_roundtrip_consistency(self, pv):
        """Gerekli kalınlıkla MAWP geri hesabı MEOP'u vermeli (UG-27 tersinirliği).

        F021 (2026-07-25) GÜNCELLEMESİ: test eskiden otomatik boyutlandırma
        çıktısını kullanıyordu ve örtük olarak "kullanılan kalınlık = kod
        minimumu" varsayıyordu. Otomatik boyutlandırma artık kabul kriterinin
        istediği 1.2 kopma marjına göre daha KALIN cidar seçtiği için MAWP de
        MEOP'un üstüne çıkar (bu doğrudur: MAWP as-built cidarın kapasitesidir).
        UG-27 tersinirliği bu yüzden required_thickness_mm doğrudan verilerek
        sınanır — sınanan özdeşlik aynıdır.
        """
        sized = pv.analyze(meop_bar=60.0, inner_diameter_mm=150.0,
                           material='steel_4130', wall_thickness_mm=None,
                           code_mode='asme_viii')
        out = pv.analyze(meop_bar=60.0, inner_diameter_mm=150.0,
                         material='steel_4130',
                         wall_thickness_mm=sized['required_thickness_mm'],
                         code_mode='asme_viii')
        assert out['mawp_bar'] == pytest.approx(60.0, rel=1e-6)
        # Otomatik boyutlandırma kod minimumundan ince olamaz.
        assert (sized['wall_thickness_used_mm']
                >= sized['required_thickness_mm'] - 1e-12)

    def test_head_thicknesses_ug32(self, asme):
        out = asme()
        heads = out['head_thicknesses_mm']
        assert heads['ellipsoidal_2_1'] == pytest.approx(2.1638, rel=1e-3)
        assert heads['torispherical'] == pytest.approx(3.8299, rel=1e-3)
        assert heads['hemispherical'] == pytest.approx(1.0819, rel=1e-3)

    def test_hemispherical_is_thinnest_torispherical_thickest(self, asme):
        """Fiziksel sıra: yarımküre < elips < torisferik (aynı P, D, S, E)."""
        heads = asme()['head_thicknesses_mm']
        assert (heads['hemispherical'] < heads['ellipsoidal_2_1']
                < heads['torispherical'])

    def test_hydrostatic_test_ug99_room_temp(self, asme):
        # Oda sıcaklığında S_test/S_tasarım = 1 → hidro = 1.3·MAWP = 173.81 bar
        out = asme()
        assert out['hydrostatic_test_pressure_bar'] == pytest.approx(
            1.3 * out['mawp_bar'], rel=1e-9)
        assert out['hydrostatic_test_pressure_bar'] == pytest.approx(
            173.81, rel=1e-3)

    def test_hydrostatic_test_stress_ratio_cancels_derating(self, asme):
        """UG-99(b): hidro = 1.3·MAWP·(S_test/S_tasarım).

        300 C'de MAWP, koruma oranı (0.82) kadar düşer ama S_test/S_tasarım
        oranı bunu tam geri alır → hidro test basıncı oda vakasıyla AYNI
        kalmalı (1.3·S_oda·t/(R+0.6t) = 173.81 bar). MAWP ise düşmeli:
        133.70·0.82 = 109.63 bar.
        """
        hot = asme(temperature_K=573.15)   # 300 C
        assert hot['mawp_bar'] == pytest.approx(133.70 * 0.82, rel=1e-3)
        assert hot['hydrostatic_test_pressure_bar'] == pytest.approx(
            173.81, rel=1e-3)

    def test_weld_efficiency_increases_thickness(self, asme):
        """E=0.7 (radyografisiz) gerekli kalınlığı E=1.0'a göre artırmalı."""
        t_full = asme(weld_efficiency=1.0)['required_thickness_mm']
        t_no_rt = asme(weld_efficiency=0.7)['required_thickness_mm']
        assert t_no_rt > t_full
        # Yaklaşık ölçek: t ∝ 1/(S·E − 0.6P) → elle: 6·75/(146.0 − 3.6) = 3.1601 mm
        assert t_no_rt == pytest.approx(3.1601, rel=1e-3)

    def test_ug27_validity_warning_high_pressure(self, pv):
        """P > 0.385·S·E (≈ 803 bar burada) → UG-27 geçerlilik uyarısı."""
        out = pv.analyze(meop_bar=900.0, inner_diameter_mm=150.0,
                         material='steel_4130', wall_thickness_mm=60.0,
                         code_mode='asme_viii')
        assert any('UG-27' in w and '0.385' in w for w in out['warnings'])


# ---------------------------------------------------------------------------
# AIAA S-080 — uçuş donanımı faktörleri
# ---------------------------------------------------------------------------
class TestAIAAS080:
    def test_default_mode_is_aiaa(self, pv):
        out = pv.analyze(**CASE)
        assert out['code_mode'] == 'aiaa_s080'

    def test_proof_and_burst_factors(self, aiaa):
        # proof = 1.5×60 = 90 bar; gerekli burst = 2.0×60 = 120 bar
        out = aiaa()
        assert AIAA_PROOF_FACTOR == 1.5 and AIAA_BURST_FACTOR == 2.0
        assert out['proof_pressure_bar'] == pytest.approx(90.0, rel=1e-9)
        assert out['required_burst_pressure_bar'] == pytest.approx(
            120.0, rel=1e-9)

    def test_required_thickness_hand_calc(self, aiaa):
        """El hesabı: ortalama yarıçap membran formu (F149, v2.6.2).

        σ = P·(r + t/2)/t  ⇒  t = P·r/(σ − 0.5·P):
            proof: 1.5·6·75/(460 − 0.75·6) = 675/455.5 = 1.481888 mm
            burst: 2.0·6·75/(730 − 1.00·6) = 900/724   = 1.243094 mm
            t_req = max(...) = 1.4819 mm (proof-akma yönetir)

        Beklenen değer 2026-07-27'de 1.4674 → 1.4819 güncellendi. Eski değer
        iç yarıçap formundan (t = P·r/σ) geliyordu; bağımsız kalın-cidar
        çözümü onu ÇÜRÜTÜR: tam Lamé σ_θ(a) = P(b²+a²)/(b²−a²) ile proof
        kriteri t = 1.482031 mm ister. Ortalama yarıçap %0.010 sapar,
        iç yarıçap %0.99 İNCE kalır ve o cidarda proof basıncında gerçek
        çeper gerilmesi 464.54 MPa olur — σ_y = 460 MPa aşılır, yani eski
        beklenti akan bir cidarı 'gerekli kalınlık' sayıyordu.
        """
        out = aiaa()
        assert out['required_thickness_mm'] == pytest.approx(1.4819, rel=1e-3)
        # Lamé referansına yakınlık (bu formun VARLIK sebebi) — %0.05 içinde:
        assert out['required_thickness_mm'] == pytest.approx(1.482031,
                                                             rel=5e-4)

    def test_mode_difference_asme_thicker_here(self, asme, aiaa):
        """Bu vakada ASME (3.5 marjlı S) S-080'den kalın cidar ister."""
        assert (asme()['required_thickness_mm']
                > aiaa()['required_thickness_mm'])


# ---------------------------------------------------------------------------
# Gerçek kopma basıncı (Faupel + ince cidar)
# ---------------------------------------------------------------------------
class TestBurstPressure:
    def test_faupel_hand_calc(self, aiaa):
        # (2/√3)·460·(2 − 0.63014)·ln(80/75) = 469.59 bar
        out = aiaa()
        assert out['burst_faupel_bar'] == pytest.approx(469.59, rel=1e-3)

    def test_thin_wall_plastic_hand_calc(self, aiaa):
        # 2·730·5/155 = 47.097 MPa = 470.97 bar
        out = aiaa()
        assert out['burst_thin_wall_bar'] == pytest.approx(470.97, rel=1e-3)

    def test_actual_burst_is_minimum(self, aiaa):
        out = aiaa()
        assert out['actual_burst_pressure_bar'] == pytest.approx(
            min(out['burst_faupel_bar'], out['burst_thin_wall_bar']), rel=1e-12)
        # 4130'da Faupel yönetir:
        assert out['actual_burst_pressure_bar'] == pytest.approx(
            469.59, rel=1e-3)

    def test_thin_wall_governs_for_low_hardening_material(self, pv):
        """6061-T6 (σ_y/σ_u = 275/310) için ince cidar limiti yönetmeli.

        Elle: Faupel = (2/√3)·275·(2 − 0.8871)·ln(80/75) = 22.81 MPa;
        ince cidar = 2·310·5/155 = 20.0 MPa = 200 bar → min = 200 bar.
        """
        out = pv.analyze(meop_bar=30.0, inner_diameter_mm=150.0,
                         material='aluminum_6061', wall_thickness_mm=5.0)
        assert out['burst_thin_wall_bar'] == pytest.approx(200.0, rel=1e-3)
        assert out['burst_faupel_bar'] == pytest.approx(228.08, rel=1e-3)
        assert out['actual_burst_pressure_bar'] == pytest.approx(
            200.0, rel=1e-3)

    def test_burst_margin_and_pass(self, aiaa):
        # 469.59/120 = 3.913 → PASS
        out = aiaa()
        assert out['burst_margin'] == pytest.approx(3.913, rel=1e-3)
        assert out['status'] == 'PASS'

    def test_burst_scales_with_derating(self, aiaa):
        """300 C'de (koruma 0.82) Faupel ve ince cidar 0.82 ile ölçeklenmeli."""
        cold = aiaa()
        hot = aiaa(temperature_K=573.15)
        assert hot['actual_burst_pressure_bar'] == pytest.approx(
            cold['actual_burst_pressure_bar'] * 0.82, rel=1e-6)
        assert hot['derating']['strength_retention_factor'] == pytest.approx(
            0.82, abs=1e-9)


# ---------------------------------------------------------------------------
# Durum kararları (PASS / MARGINAL / FAIL)
# ---------------------------------------------------------------------------
class TestStatus:
    def test_fail_when_wall_too_thin(self, aiaa):
        """t = 0.5 mm → burst ≈ 48.3 bar < 120 bar gerekli → FAIL."""
        out = aiaa(wall_thickness_mm=0.5)
        assert out['status'] == 'FAIL'
        assert out['burst_margin'] < 1.0
        assert out['actual_burst_pressure_bar'] == pytest.approx(
            48.35, rel=2e-3)

    def test_marginal_band(self, aiaa):
        """t = 1.49 mm → burst_margin ≈ 1.193 ∈ [1, 1.2) → MARGINAL.

        MARGINAL bandına düşmek için cidarın İKİ koşulu birden sağlaması
        gerekir; bu vakada band elle şöyle türetilir:
          alt sınır: kod minimumu t_req = 1.481888 mm (altında durum FAIL,
              çünkü cidar S-080 proof/burst membran gereğini karşılamıyor)
          üst sınır: marj = 1.2 veren kalınlık. min(Faupel, ince cidar) =
              1.2·120 = 144 bar kökü → t* = 1.499077 mm (üstünde PASS).
        Band = [1.481888, 1.499077) mm; seçilen t = 1.49 mm tam ortasında.

        t = 1.49 mm'de el hesabı:
          Faupel = (2/√3)·460·(2 − 460/730)·ln(76.49/75) = 14.3137 MPa
          ince   = 2·730·1.49/(150 + 1.49)               = 14.3600 MPa
          actual = min = 143.137 bar ;  marj = 143.137/120 = 1.19280

        2026-07-27: eski değer t = 1.47 mm idi (marj 1.177, doğru) ama F149
        kod minimumu 1.4674 → 1.481888 mm'ye çıkınca 1.47 mm kod
        minimumunun ALTINA düştü; modül haklı olarak FAIL veriyordu
        (kabul kriteri: t < t_req → FAIL, kopma marjı ne olursa olsun).
        """
        out = aiaa(wall_thickness_mm=1.49)
        # Kod minimumunun üstünde (yoksa kalınlık kuralından FAIL gelirdi):
        assert out['wall_thickness_used_mm'] >= out['required_thickness_mm']
        assert 1.0 <= out['burst_margin'] < MARGINAL_BURST_MARGIN
        assert out['burst_margin'] == pytest.approx(1.1928, rel=2e-3)
        assert out['actual_burst_pressure_bar'] == pytest.approx(143.137,
                                                                 rel=2e-3)
        assert out['status'] == 'MARGINAL'

    def test_fail_above_max_service_temperature(self, aiaa):
        """900 K > 811 K (4130 yapısal sınır) → FAIL + uyarı."""
        out = aiaa(temperature_K=900.0)
        assert out['status'] == 'FAIL'
        assert out['derating']['exceeds_max_service_temp'] is True
        assert any('service temperature' in w for w in out['warnings'])

    def test_fail_when_thinner_than_code_minimum(self, asme):
        """ASME: t = 2.0 mm < gerekli 2.195 mm → FAIL (burst yüksek olsa da)."""
        out = asme(wall_thickness_mm=2.0)
        assert out['wall_thickness_used_mm'] < out['required_thickness_mm']
        assert out['status'] == 'FAIL'


# ---------------------------------------------------------------------------
# Otomatik boyutlandırma ve zarafet (graceful) davranışları
# ---------------------------------------------------------------------------
class TestAutoSizingAndRobustness:
    def test_auto_thickness_when_not_given(self, pv):
        """F021 (2026-07-25): otomatik boyutlandırma KENDİ kabul kriterini geçmeli.

        Eski test "kullanılan kalınlık = kod minimumu" ve "FAIL değil" diyordu;
        bu, modülün kendi ürettiği cidarı MARGINAL/FAIL bırakan tutarsızlığı
        (ölçüldü: asme_viii 20 bar margin=0.9977 FAIL) kodluyordu. Boyutlandırma
        artık kabul kriteriyle aynı fonksiyonun kökünden geldiği için sonuç
        PASS ve marj tam olarak MARGINAL_BURST_MARGIN'dir.
        """
        out = pv.analyze(meop_bar=60.0, inner_diameter_mm=150.0,
                         material='steel_4130', wall_thickness_mm=None)
        assert out['auto_sized'] is True
        # Kod minimumundan ince olamaz:
        assert (out['wall_thickness_used_mm']
                >= out['required_thickness_mm'] - 1e-12)
        # ...ve kabul kriterini kendi kendine sağlar:
        assert out['status'] == 'PASS'
        assert out['burst_margin'] == pytest.approx(MARGINAL_BURST_MARGIN,
                                                    rel=1e-6)
        assert any('not supplied' in w for w in out['warnings'])

    def test_auto_sizing_passes_across_pressures_and_modes(self, pv):
        """F021 regresyon bekçisi: hiçbir basınç/mod bileşiminde FAIL/MARGINAL yok.

        Denetimde ölçülen kırılma: asme_viii oto-boyut 20 bar -> 0.9977 FAIL,
        60 bar -> 0.9997 FAIL, 120/200/400 bar -> MARGINAL; aiaa_s080 ise her
        basınçta MARGINAL. Artık hepsi PASS olmalı.
        """
        for mode in ('asme_viii', 'aiaa_s080'):
            for meop in (20.0, 60.0, 120.0, 200.0, 400.0):
                out = pv.analyze(meop_bar=meop, inner_diameter_mm=150.0,
                                 material='steel_4130',
                                 wall_thickness_mm=None, code_mode=mode)
                assert out['status'] == 'PASS', (mode, meop, out['status'])
                assert out['burst_margin'] >= MARGINAL_BURST_MARGIN - 1e-9

    def test_burst_sizing_root_matches_acceptance_function(self, pv):
        """Boyutlandırma kökü ile kabul kriteri AYNI fonksiyondan gelmeli."""
        sy = 460e6 * 1.0
        su = 730e6 * 1.0
        R = 0.075
        target = 1.2 * 2.0 * 60e5           # 1.2 x (2.0 x 60 bar)
        t = pv.thickness_for_burst_target(sy, su, R, target)
        assert pv.actual_burst_pressure(sy, su, R, t) == pytest.approx(
            target, rel=1e-6)
        # Ulaşılamaz hedef (ince cidar limiti 2*UTS'ye doyar) -> sonsuz.
        assert not math.isfinite(
            pv.thickness_for_burst_target(sy, su, R, 3.0 * su))

    def test_thick_wall_transition_warning(self, aiaa):
        """t/r = 20/75 = 0.267 > 0.1 → ince cidar geçerlilik uyarısı."""
        out = aiaa(wall_thickness_mm=20.0)
        assert any('t/r' in w for w in out['warnings'])
        # Kalın cidarda Faupel hâlâ tanımlı ve pozitif:
        assert out['burst_faupel_bar'] > 0

    def test_no_thick_wall_warning_when_thin(self, aiaa):
        out = aiaa()  # t/r = 5/75 = 0.067 < 0.1
        assert not any('t/r' in w for w in out['warnings'])

    @pytest.mark.parametrize('bad_kwargs', [
        dict(meop_bar=-5.0),
        dict(meop_bar=0.0),
        dict(meop_bar=float('nan')),
        dict(inner_diameter_mm=0.0),
        dict(inner_diameter_mm=-150.0),
        dict(wall_thickness_mm=-1.0),
        dict(temperature_K=-10.0),
        dict(weld_efficiency=0.9),       # UW-12 kümesinde yok
        dict(head_type='flat'),
        dict(material='unobtainium'),
    ])
    def test_invalid_inputs_raise_value_error(self, pv, bad_kwargs):
        args = dict(CASE)
        args.update(bad_kwargs)
        with pytest.raises(ValueError):
            pv.analyze(**args)

    def test_invalid_code_mode_raises(self, pv):
        with pytest.raises(ValueError):
            pv.analyze(code_mode='asme_div2', **CASE)
        with pytest.raises(ValueError):
            PressureVesselAnalyzer(code_mode='bogus')

    def test_weld_efficiency_set_matches_uw12(self):
        assert set(ALLOWED_WELD_EFFICIENCIES) == {0.70, 0.85, 1.00}

    def test_output_schema_keys(self, aiaa):
        out = aiaa()
        for key in ('code_mode', 'material', 'required_thickness_mm',
                    'wall_thickness_used_mm', 'mawp_bar',
                    'proof_pressure_bar', 'hydrostatic_test_pressure_bar',
                    'required_burst_pressure_bar', 'burst_faupel_bar',
                    'burst_thin_wall_bar', 'actual_burst_pressure_bar',
                    'burst_margin', 'head_thicknesses_mm', 'status',
                    'warnings', 'assumptions', 'derating',
                    'thickness_margin', 'allowable_stress_MPa'):
            assert key in out, key
        assert out['status'] in ('PASS', 'MARGINAL', 'FAIL')
        assert set(out['head_thicknesses_mm']) == {
            'ellipsoidal_2_1', 'torispherical', 'hemispherical'}
        # Tüm basınçlar pozitif ve sonlu olmalı:
        for key in ('mawp_bar', 'proof_pressure_bar',
                    'hydrostatic_test_pressure_bar',
                    'actual_burst_pressure_bar'):
            assert math.isfinite(out[key]) and out[key] > 0
