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

    def test_thermal_formula_matches_classic_surface_value(self, analyzer):
        # v2.5.2: klasik yuzey degeri sigma = E*alpha*dT/(2(1-nu)).
        # Eski surum 2 faktorunu "konservatiflik" adina dusurmuyordu; bu
        # muhafazakarlik degil 2x sisirmeydi (her sicak motor SF<1 cikiyordu).
        mat = analyzer.materials['steel_4130']
        dT = 500.0
        out = analyzer._thermal_hoop_stress(mat, dT)
        expected = (mat['elastic_modulus'] * mat['thermal_expansion'] * dT
                    / (2.0 * (1.0 - mat['poisson_ratio'])))
        assert out['thermal_hoop_stress'] == pytest.approx(expected, rel=1e-9)

    def test_thermal_is_half_of_fully_restrained_bound(self, analyzer):
        # Tam-kisitli ust sinir E*alpha*dT/(1-nu); yuzey gradyan degeri onun yarisi.
        mat = analyzer.materials['steel_4130']
        dT = 511.0
        out = analyzer._thermal_hoop_stress(mat, dT)
        restrained = (mat['elastic_modulus'] * mat['thermal_expansion'] * dT
                      / (1.0 - mat['poisson_ratio']))
        assert out['thermal_hoop_stress'] == pytest.approx(0.5 * restrained, rel=1e-9)

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
        # ÖH D19 · P13B3-05 — BANT GEREKÇESİ (ölçülen, D19): bugün fark = 0
        # (bit-özdeş), bant sınanmadı. KALIYOR: 0,44 eğrinin 500 °C
        # düğümüdür ve ±0,02 görev tanımının "~%50 kayıp" ifadesinin
        # sayısal karşılığıdır; hemen altındaki 0,40-0,60 iddiası zaten
        # geniş bandı ayrıca kilitliyor. Kimlik denetimi eğrinin meşru
        # yeniden ölçümünü kırardı.
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

    def test_pure_internal_pressure_does_not_buckle(self, analyzer):
        # DENETIM #203: ic basinc boylamsal CEKME uretir — kabuk burkulmaz,
        # stabilize olur. Basma yuku yokken SF sonsuz ve durum SAFE olmali.
        # (Eski surum p*r/2t cekmesini burkulma yuku sanip CRITICAL diyordu.)
        mat = analyzer.materials['steel_4130']
        out = analyzer._check_buckling(5e5, 0.5, 0.001, 2.0, mat)
        assert out['axial_buckling_safety_factor'] == float('inf')
        # ÖH D31 / P5B1-15 — BEKÇİ ÇEVRİLDİ. Bu satır eskiden
        # ``buckling_status == 'SAFE'`` bekliyordu ve kusuru KORUYORDU:
        # aynı koşumda kritik dış basınç 0,004315 bar (1 atm'in ~1/235'i)
        # yayımlanıyor, dış basınç modu hiçbir uygulanan basınçla
        # karşılaştırılmıyor, ama hüküm 'SAFE' basılıyordu. Bu testin
        # KONUSU eksenel moddur (#203: iç basınç çekmesi burkulma yükü
        # değildir), o yüzden iddia eksenel modun KENDİ adına taşındı.
        # Birleşik hüküm artık dış basınç yük durumu beyan edilmediği için
        # NOT_EVALUATED'dır (kazanılmamış onay yayımlanmaz).
        assert out['axial_buckling_status'] == 'SAFE'
        assert out['buckling_status'] == 'NOT_EVALUATED'
        assert out['applied_axial_stress_MPa'] == 0.0
        assert out['pressure_stabilizing_stress_MPa'] > 0.0

    def test_thin_wall_buckling_flagged_critical(self, analyzer):
        # Cok ince + uzun + buyuk capli kabuk, GERCEK eksenel BASMA altinda
        # (basincsiz, F kritik yukun ~3 kati): burkulma kritik olmali.
        mat = analyzer.materials['steel_4130']
        r, t = 0.5, 0.001
        probe = analyzer._check_buckling(0.0, r, t, 2.0, mat)
        sigma_cr = probe['critical_axial_buckling_stress_MPa'] * 1e6  # Pa
        F_critical = sigma_cr * 2.0 * math.pi * r * t                 # N
        out = analyzer._check_buckling(0.0, r, t, 2.0, mat,
                                       axial_compression_force=3.0 * F_critical)
        assert out['axial_buckling_safety_factor'] == pytest.approx(1.0 / 3.0, rel=1e-6)
        # P5B1-15: en kötü mod birleşik hükmü yönetir; eksenel mod kendi
        # adıyla da CRITICAL der.
        assert out['axial_buckling_status'] == 'CRITICAL'
        assert out['buckling_status'] == 'CRITICAL'

    def test_pressure_tension_credit_reduces_net_compression(self, analyzer):
        """Ic basinc kredisi BASINCLI yuk durumunda net basmayi azaltir.

        TEST GUNCELLENDI (F075, 2026-07-25): eski surum krediyi RAPORLANAN
        (yoneten) emniyet faktorunde ariyordu — yani ustteki
        'axial_buckling_safety_factor' alaninda. Bu, modulun yalnizca
        BASINCLI durumu degerlendirdigi eski davranisti. Burkulma gercekte
        BASINCSIZ durumda (nakliye, montaj on-yuku, atesleme oncesi/kapanis,
        ucus atalet yuku) kritiktir; artik iki yuk durumu da hesaplaniyor ve
        YONETEN (dusuk SF'li) olan raporlaniyor. Kredi yalnizca yardim ettigi
        icin yoneten durum daima basincsizdir ve iki cagrinin raporlanan
        SF'si esittir — eski iddia (wet > dry) artik YANLIS davranisi
        kodluyordu. Kredi etkisi 'pressurized' tani alanlarindan sinanir.
        """
        mat = analyzer.materials['steel_4130']
        r, t, F = 0.5, 0.001, 4.0e5
        dry = analyzer._check_buckling(0.0, r, t, 2.0, mat,
                                       axial_compression_force=F)
        wet = analyzer._check_buckling(5e5, r, t, 2.0, mat,
                                       axial_compression_force=F)
        # Kredi basincli durumda net basmayi dusurur -> SF yukselir.
        assert (wet['axial_buckling_safety_factor_pressurized']
                > dry['axial_buckling_safety_factor_pressurized'])
        assert (wet['applied_axial_stress_pressurized_MPa']
                < dry['applied_axial_stress_pressurized_MPa'])
        # Basincsiz durumda kredi YOKTUR: iki cagri ayni.
        assert (wet['axial_buckling_safety_factor_unpressurized']
                == pytest.approx(
                    dry['axial_buckling_safety_factor_unpressurized']))
        # Yoneten (raporlanan) durum daima basincsizdir.
        assert wet['governing_load_case'] == 'unpressurized'
        assert (wet['axial_buckling_safety_factor']
                == pytest.approx(
                    wet['axial_buckling_safety_factor_unpressurized']))

    def test_buckling_credit_uses_meop_not_design_pressure(self, analyzer):
        """F075(b): stabilize kredi MEOP'tan alinir, 1.5*Pc'den DEGIL.

        Kredi net basmadan CIKARILDIGI icin tasarim basinciyla hesaplamak
        konservatif degildir (daha yuksek basinc net basmayi azaltir).
        analyze_structure artik _check_buckling'e chamber_pressure gecer.
        """
        Pc_bar = 50.0
        res = analyzer.analyze_structure(
            {'chamber_pressure': Pc_bar, 'chamber_diameter': 0.15,
             'chamber_length': 0.5, 'throat_diameter': 0.05,
             'burn_time': 10.0, 'thrust': 5.0e5},
            material='steel_4130', design_pressure_factor=1.5)
        b = res['buckling_analysis']
        assert b['stabilizing_pressure_bar'] == pytest.approx(Pc_bar)
        # Tasarim basinci (1.5*Pc) DEGIL:
        assert b['stabilizing_pressure_bar'] < 1.5 * Pc_bar

    def test_external_pressure_buckling_present(self, analyzer):
        mat = analyzer.materials['steel_4130']
        out = analyzer._check_buckling(5e5, 0.5, 0.001, 2.0, mat)
        assert out['critical_external_pressure_bar'] > 0.0
        assert math.isfinite(out['critical_external_pressure_bar'])

    # ÖH D31 / P5B1-15 — BORÇ İMİ KALDIRILDI (14 Eylül 2026).
    # İmin taşıdığı kusur onarıldı: ``_check_buckling`` artık
    # ``external_pressure`` / ``internal_pressure_min`` zarfını
    # (max(p_dış − p_iç, 0)) kabul eder, ``external_buckling_safety_factor``
    # ve ``external_buckling_status`` yayımlar; yük durumu beyan
    # edilmediğinde hüküm ``NOT_EVALUATED``dır (SAFE + inf kalktı).
    # Ölçüm: docs/scofield/raw/OH/D31/yapisal-sistem/a1/{once,sonra}.json
    # (K1) — t = 0,5/1,0/5,0 mm için karşılaştırma alanı sayısı 0 -> 4,
    # buckling_status 'SAFE' -> 'NOT_EVALUATED'. Kilit bekçi:
    # tests/test_d31_yapisal_sistem_a1.py::TestP5B1_15DisBasincZarfi.
    @pytest.mark.parametrize('t', (0.0005, 0.001, 0.005))
    def test_external_pressure_mode_is_compared_with_an_applied_pressure(
            self, analyzer, t):
        """Yayımlanan kritik dış basınç bir HÜKME bağlanmalı.

        Taşınan bekçi (kardeş düğüm ``:221``): eski iddia yalnız sayının
        POZİTİF ve SONLU olduğunu sınıyordu — 0,0005 bar da pozitiftir.
        Sözleşme: ya dış basınç modu bir uygulanan basınçla karşılaştırılıp
        kendi emniyet katsayısını yayımlar, ya da genel ``buckling_status``
        bu modu kapsamadığını söyleyerek koşulsuz 'SAFE' dememelidir.
        """
        mat = analyzer.materials['steel_4130']
        out = analyzer._check_buckling(5e5, 0.5, t, 2.0, mat)
        p_cr = float(out['critical_external_pressure_bar'])
        assert p_cr > 0.0
        if p_cr >= 1.01325:          # 1 atm'in üstündeyse bu vaka konu dışı
            return
        karsilastirma = [k for k in out
                         if 'external' in k.lower()
                         and ('applied' in k.lower() or 'safety' in k.lower()
                              or 'margin' in k.lower()
                              or 'status' in k.lower())]
        assert karsilastirma or out['buckling_status'] != 'SAFE', (
            f'kritik dış basınç {p_cr:.4f} bar (1 atm altı) yayımlanırken '
            f"buckling_status = '{out['buckling_status']}': dış basınç modu "
            'hiçbir uygulanan basınçla karşılaştırılmıyor, hüküm yalnız '
            f'eksenel moddan geliyor (bloktaki alanlar: {sorted(out)})')


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

    def test_pressure_only_appears_safe_but_thermal_is_flagged(self, analyzer):
        """Sicaklik hesaba katilinca tasarim ARTIK guvenli gorunmemeli.

        v2.5.2 MODEL DEGISIKLIGI: eski surum sogutmasiz cidarda ic yuzu
        sicak, dis yuzu ORTAM sayip ~430 K'lik hayali bir gradyan uretiyor
        ve SF'yi 1'in altina dusuruyordu. Ince metal cidarda iletim direnci
        (t/k) dis yuzey kayip direncinin yaninda ihmal edilebilir; gercek
        gradyan ~2 K'dir (bkz. _estimate_wall_delta_T). Yani eski "tehlike"
        sinyali dogru sonuca yanlis yoldan variyordu.

        Sogutmasiz sicak motorun GERCEK tehlikesi gradyan gerilmesi degil,
        cidarin butun olarak malzeme servis sinirina yaklasmasidir. Test
        artik bunu dogrular: derating SF'yi belirgin dusurur ve sicaklik
        marji durumu SAFE olmaktan cikarir.
        """
        res_noT = analyzer.analyze_structure(
            REF_MOTOR_NO_TEMP, material='steel_4130', design_pressure_factor=1.5)
        res_T = analyzer.analyze_structure(
            REF_MOTOR, material='steel_4130', design_pressure_factor=1.5)

        sf_noT = res_noT['chamber_analysis']['hoop_safety_factor']
        sf_T = res_T['chamber_analysis']['hoop_safety_factor']

        # Sadece-basinc: yuksek (guvenli gorunur) SF.
        assert sf_noT > 3.0, f"pressure-only SF should look safe, got {sf_noT}"
        # V3 yapi-sf (7 Eki 2026) — BEKLENTİ ÇEVİRİSİ. Eski satır
        # ``sf_T < sf_noT`` idi: boyutlandırma kipinde sıcaklığın etkisi SF
        # düşüşü olarak görünüyordu, çünkü boyutlandırma yalnız basınç
        # hoop'unu hedefe oturtuyor, yayımlanan SF ise ısıl gerilmeyi de
        # taşıyordu (boyutlandırılmış cidar kendi hedefini tutturmuyordu —
        # düzeltilen kusur). Artık boyutlandırma toplam hoop'u (basınç +
        # ısıl, derate edilmiş akma) hedefe oturtur: sıcaklığın etkisi DAHA
        # KALIN cidardır ve iki koşu da hedef x imalat payını geri okur.
        # Kâhin: ısıl gerilme > 0 ve akma düşürmesi < 1 iken aynı hedefi
        # sağlayan cidar kalınlaşmak ZORUNDADIR (P·r/t + σ_th = S_y,der/SF).
        t_noT = res_noT['chamber_analysis']['recommended_thickness']
        t_T = res_T['chamber_analysis']['recommended_thickness']
        assert t_T > t_noT, (
            f"derating + thermal stress must thicken the sized wall: "
            f"{t_T} vs {t_noT} mm")
        assert sf_T == pytest.approx(sf_noT, rel=1e-12), (
            f"both sized walls must read back target x allowance: "
            f"{sf_T} vs {sf_noT}")
        # Sicaklik marji: cidar servis sinirinin %85'ini asiyor.
        sa = res_T['safety_analysis']
        assert sa['thermal_margin_ratio'] > 0.85
        # ...ve bu durumu SAFE olmaktan cikariyor.
        assert sa['status'] in ('MARGINAL', 'UNSAFE')
        # D-track: öneriler artık {code,params,severity}; metin frontend'de.
        assert any(r['code'] == 'warn.structural.thermal_margin_service_limit'
                   for r in sa['recommendations'])

    # ÇEVİRİ (ÖH D15 fix-3 / taban geçişi) — BORÇ İMİ KALKTI.
    # Bu bekçi P5B1-02 borcunu ``xfail(strict=True)`` ile taşıyordu.
    # Kusur ÖH Z5S / PK6 (hüküm damgası kulvarı, commit f8269a5)
    # tarafından ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta
    # test GEÇİYOR ve strict im XPASS(strict) ile KIRMIZI veriyordu.
    # İm kaldırıldı; iddia artık CANLI bekçidir — onarım geri alınırsa
    # burası kırmızı verir.
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/structural_analysis.py:745 "ÖH
    # ONARIMI (defter P5B1-02, YÜKSEK): SERVİS SINIRI EKSENİ"; :769-793
    # ölçülmüş cidar verilmediğinde ``T_peak_service = float(_T_alev)``
    # (asimetrik T_aw doktrini) ve sayının ÜST SINIR olduğu :772/:781
    # ``peak_wall_temperature_basis`` künyesiyle ADIYLA yayımlanıyor
    # (:2775-2776). Gradyan/derating ekseni bilerek kendi soğutmasız
    # ince-cidar tahmininde bırakıldı ve AYRI adla yayımlanıyor.
    def test_estimated_wall_temperature_follows_the_flame(self, analyzer):
        """Taşınan bekçi (kardeş düğüm ``:271``).

        Kardeş iddia ``thermal_margin_ratio > 0.85`` diyor; bu yolda oran
        HER ZAMAN tam 0,9000 olduğu için iddia tanım gereği geçiyor ve
        kusuru koruyor. Kilitlenen sözleşme: tahmin edilen cidar sıcaklığı
        ALEVE tepki vermeli — 1000 K ile 10 000 K aynı cidarı üretemez.
        """
        # Kontrol: gerçek cidar sıcaklığı verilen yol ÇALIŞIYOR (bu dosyanın
        # test_service_limit_uses_peak_wall_temperature ölçümü).
        bagli = analyzer.analyze_structure(
            dict(REF_MOTOR_NO_TEMP, wall_temperature_hot=860.0,
                 wall_temperature_cold=560.0),
            material='steel_4130',
            design_pressure_factor=1.5)['safety_analysis']
        assert bagli['peak_wall_temperature_K'] == pytest.approx(860.0)

        tahminler = {}
        for T_flame in (1000.0, 3000.0, 10000.0):
            sa = analyzer.analyze_structure(
                dict(REF_MOTOR, chamber_temperature=T_flame),
                material='steel_4130',
                design_pressure_factor=1.5)['safety_analysis']
            tahminler[T_flame] = (sa['peak_wall_temperature_K'],
                                  sa['thermal_margin_ratio'])
        soguk = tahminler[1000.0][0]
        sicak = tahminler[10000.0][0]
        assert sicak > soguk + 1.0, (
            'tahmin edilen tepe cidar sıcaklığı alevi görmüyor: '
            f'{ {k: (round(v[0], 2), round(v[1], 6)) for k, v in tahminler.items()} } '
            '(alev 10 kat arttı, cidar kıpırdamadı)')

    def test_thermal_stress_superposition_and_cooled_gradient(self, analyzer):
        """Termal gerilme lineer superpozisyonla eklenir.

        v2.5.2: sogutmasiz cidarda gradyan ~2 K oldugundan termal hoop
        basinc hoop'unu ARTIK asmaz (eski test bunu bekliyordu, ama o
        beklenti fiziksel olmayan 430 K gradyan varsayimindan geliyordu).
        Gercek sogutma verisi girildiginde termal terim beklendigi gibi
        buyur ve baskin hale gelir; ikinci blok bunu dogrular.
        """
        res = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                         design_pressure_factor=1.5)
        ca = res['chamber_analysis']
        # Toplam = basinc + termal (lineer superpozisyon) her durumda gecerli.
        assert ca['hoop_stress'] == pytest.approx(
            ca['pressure_hoop_stress'] + ca['thermal_hoop_stress'], rel=1e-6)
        # Sogutmasiz: gradyan kucuk -> termal terim basinci asmaz.
        assert ca['thermal_hoop_stress'] < ca['pressure_hoop_stress']

        # Gercek sogutma verisi (isi transferi modulunden gelen cidar T'leri)
        # verildiginde termal terim baskin hale gelir.
        md_cooled = dict(REF_MOTOR)
        md_cooled['wall_temperature_hot'] = 900.0
        md_cooled['wall_temperature_cold'] = 400.0
        ca_cooled = analyzer.analyze_structure(
            md_cooled, material='steel_4130',
            design_pressure_factor=1.5)['chamber_analysis']
        assert ca_cooled['thermal_hoop_stress'] > ca_cooled['pressure_hoop_stress']

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
        # v2.5.2: cidar sicakligi verilmeyen fallback'te ic yuz, servis
        # sinirinin WALL_TEMP_SERVICE_FRACTION kati kadar isinir varsayilir
        # (811 K * 0.9 = 729.9 K) — eski surum her motoru tam servis
        # sinirinda varsayip her sicak tasarimi CRITICAL yapiyordu.
        from hrma.analysis.structural_analysis import WALL_TEMP_SERVICE_FRACTION
        scen = ca['thermal_scenarios']
        assert set(scen) == {'hot_soak', 'cooled_gradient'}
        assert scen['hot_soak']['derating_temp_K'] == pytest.approx(
            811.0 * WALL_TEMP_SERVICE_FRACTION, abs=1.0)
        # Yoneten senaryo, dusuk von Mises SF'li oland ir.
        gov = ca['governing_thermal_scenario']
        assert scen[gov]['von_mises_safety_factor'] == pytest.approx(
            min(s['von_mises_safety_factor'] for s in scen.values()), rel=1e-9)
        # v2.5.2: guvenlik sinyali korunur ama DOGRU mekanizmadan gelir.
        # Gerilme SF'si artik makul (sogutmasiz cidarda gradyan ~2 K), buna
        # karsilik cidar servis sinirinin %85'ini astigi icin durum SAFE
        # degildir. Eski test SF<1 bekliyordu; o deger hayali gradyandan
        # geliyordu (bkz. test_pressure_only_appears_safe_but_thermal_is_flagged).
        sa = res['safety_analysis']
        assert sa['thermal_margin_ratio'] > 0.85
        assert sa['status'] in ('MARGINAL', 'UNSAFE')

    def test_service_limit_uses_peak_wall_temperature(self, analyzer):
        """F074: servis siniri TEPE (ic yuz) sicaklikta sinanmali.

        'cooled_gradient' senaryosu yonettiginde derating sicakligi ORTALAMA
        cidar sicakligidir (0.5*(T_ic+T_dis)); servis sinirinin asilmasi ise
        SICAK yuzde olur. Eski surum servis kontrolunu de ortalamayla yapiyor,
        sicak yuz limiti astiginda bile exceeds=False raporluyordu.
        OLCULDU (steel_4130, servis siniri 811 K): T_ic=860 K, T_dis=560 K ->
        eski oran 0.8755 / exceeds False; dogru deger 860/811 = 1.0604 ve
        exceeds True. Kaynak: MMPDS kisa-sureli maruziyet sinirlari (tepe
        metal sicakligina uygulanir).
        """
        md = {'chamber_pressure': 50.0, 'chamber_diameter': 0.15,
              'chamber_length': 0.5, 'throat_diameter': 0.05,
              'burn_time': 10.0,
              'wall_temperature_hot': 860.0, 'wall_temperature_cold': 560.0}
        res = analyzer.analyze_structure(md, material='steel_4130',
                                         design_pressure_factor=1.5)
        sa = res['safety_analysis']
        T_service = analyzer.materials['steel_4130']['max_service_temp']
        assert sa['peak_wall_temperature_K'] == pytest.approx(860.0)
        # Derating tabani ORTALAMA kalmali (tasima kapasitesi kesit ortalamasi).
        assert sa['derating_wall_temperature_K'] == pytest.approx(710.0)
        assert sa['thermal_margin_ratio'] == pytest.approx(860.0 / T_service,
                                                           rel=1e-9)
        assert sa['thermal_margin_ratio'] > 1.0
        assert sa['exceeds_max_service_temp_peak'] is True
        assert sa['status'] == 'UNSAFE'
        # Rapor katmani da tepe-tabanli bayragi gormeli.
        assert res['thermal_analysis']['exceeds_max_service_temp_peak'] is True

        # Ikinci olcum noktasi (katalog): 790/740 K -> 0.9741 (sinir bandi).
        md2 = dict(md, wall_temperature_hot=790.0, wall_temperature_cold=740.0)
        sa2 = analyzer.analyze_structure(
            md2, material='steel_4130',
            design_pressure_factor=1.5)['safety_analysis']
        assert sa2['thermal_margin_ratio'] == pytest.approx(790.0 / T_service,
                                                            rel=1e-9)
        assert sa2['exceeds_max_service_temp_peak'] is False

    def test_recommendations_flag_thermal_and_thin_wall(self, analyzer):
        res = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                         design_pressure_factor=1.5)
        # D-track: öneriler artık {code,params,severity}; metin frontend'de.
        codes = {r['code'] for r in res['safety_analysis']['recommendations']}
        # v2.5.2: sogutmasiz cidarda uyari 'termal gerilme baskin' degil,
        # 'cidar servis sinirina yakin' seklinde gelir (dogru mekanizma).
        assert ('warn.structural.thermal_margin_service_limit' in codes
                or 'warn.structural.severe_derating' in codes)
        # Kalin-cidar uyarisi kalin rejimde gelmeli (senaryo-ayrimli modelde
        # referans vaka ince cidara dustugunden 4x faktorle zorlanir)
        res4 = analyzer.analyze_structure(REF_MOTOR, material='steel_4130',
                                          design_pressure_factor=4.0)
        codes4 = {r['code'] for r in res4['safety_analysis']['recommendations']}
        assert 'warn.structural.thin_wall_invalid' in codes4

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
