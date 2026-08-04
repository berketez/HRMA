"""C kulvarı bileşen modülleri (C2/C3/C4) doğrulama testleri.

Bekçi çapaları — doğrulamasız fizik modülü teslim edilmez:

(a) Birim ve boyut bekçileri: psi çevrimi deponun KENDİ birim
    tablosuyla (hrma/validation/record_adapters.py) karşılaştırılır;
    Kv/Cv oranı birim tanımlarından bağımsız türetilir; yerel kayıp
    terimi hızda tam ikinci derecedir.
(b) Kapalı-form karşılaştırmalar:
      * Darcy-Weisbach laminer dalı f = 64/Re ile TAM eşleşir;
      * Haaland türbülans dalı, testin İÇİNDE iterasyonla çözülen
        kapalı-form Colebrook denklemiyle %2 içinde uyuşur;
      * Crane TP-410'un yayımlanmış f_T tablosu, tam-pürüzlü limitten
        türetilerek yeniden üretilir (Sch-40 iç çapları, ASME B36.10M);
      * Cv boyutlandırması tersine çözümle kendini kapatır;
      * gimbal aktüatör kuvveti basit kaldıraç dengesiyle (M = F*e,
        F_akt = M/r_a) doğrulanır;
      * cıvata dairesi formülü F_maks = 4M/(nD), n cıvata üzerinden
        doğrudan moment toplamıyla bağımsız kurulur;
      * ateşleyici enerjisi ve piroteknik şarj kütlesi enerji/ideal gaz
        korunumuyla gidiş-dönüş kapanır.
(c) Monotonluk: her modülde fiziksel yön testleri (uzun hat -> yüksek
    dP, büyük kol -> küçük aktüatör kuvveti, büyük serbest hacim ->
    büyük şarj vb.).
(d) Sözleşme: valve_feedline'ın ürettiği su koçu girdisi GERÇEKTEN
    WaterHammerAnalyzer.analyze(**kwargs) çağrısına giriyor.
(e) Dürüstlük: geçersiz aralıkta sessiz ekstrapolasyon YOK (sert
    aralıkta ValueError, yumuşak bantta `validity` kaydı); hesaplanamayan
    kalem için sayı UYDURULMAZ (`not_modelled`/`not_evaluated`); her
    modül NOT_MODELLED beyanını çıktısına koyar.

Bu testler kusuru KİLİTLEMEZ: sabit sayıya bağlanan tek yer yayımlanmış
kaynak değerleridir (Crane f_T tablosu) ve orada tolerans gerekçesiyle
birlikte verilmiştir. Diğer her şey analitik bağıntı, yön ya da
tutarlılık sınamasıdır — bir kalem gerçekten modellenirse testler
kırılmadan geçmeye devam eder.
"""

import math

import pytest

from hrma.analysis.valve_feedline import (
    PSI_PA,
    LB_KG,
    KV_PER_CV,
    SG_REFERENCE_DENSITY_KG_M3,
    CRANE_FT_ROUGHNESS_M,
    FITTING_LD,
    REL_ROUGHNESS_VALID,
    VALVE_FL_VALID,
    crane_ft,
    fitting_loss_coefficient,
    line_velocity,
    reynolds_number,
    flow_regime,
    line_pressure_drop,
    valve_cv_required,
    flow_from_cv,
    cv_to_kv,
    kv_to_cv,
    liquid_critical_pressure_ratio_factor,
    choked_pressure_drop,
    cavitation_status,
    size_valve,
    minimum_closure_time_s,
    water_hammer_inputs,
    analyze_valve_feedline,
    NOT_MODELLED as VALVE_NOT_MODELLED,
)
from hrma.analysis.gimbal_mount import (
    GIMBAL_ANGLE_VALID_DEG,
    GIMBAL_ANGLE_PRACTICE_BAND_DEG,
    BOLT_COUNT_MIN,
    thrust_components,
    resultant_gimbal_angle_deg,
    actuator_stroke,
    bolt_circle_max_load,
    slew_angular_acceleration,
    actuator_load,
    mount_ring_loads,
    analyze_gimbal_mount,
    NOT_MODELLED as GIMBAL_NOT_MODELLED,
)
from hrma.analysis.igniter_sizing import (
    IGNITER_TYPES,
    TRANSFER_EFFICIENCY_VALID,
    IGNITION_PRESSURE_FRACTION_VALID,
    specific_gas_constant,
    ignition_energy_required,
    hard_start_pressure,
    safe_ignition_window_s,
    torch_propellant_flow,
    pyrotechnic_charge_mass,
    size_igniter,
    NOT_MODELLED as IGNITER_NOT_MODELLED,
)
from hrma.analysis.regen_cooling import haaland_friction_factor
from hrma.constants import G_0, R_UNIVERSAL

# Testin İÇİNDE bağımsız kurulan kesin tanımlar (modüldeki bir yazım
# hatası kendi kendini doğrulamasın diye buraya ayrıca yazılır).
INCH_M = 0.0254                    # 1 in [m], kesin tanım
POUND_KG = 0.45359237              # 1 lb [kg], kesin tanım
GALLON_M3 = 231.0 * INCH_M ** 3    # 1 ABD galonu [m^3], kesin tanım


# ===========================================================================
# (a) Birim ve boyut bekçileri
# ===========================================================================
class TestBirimVeBoyut:
    def test_psi_cevrimi_deponun_kendi_tablosuyla_ayni(self):
        """PSI_PA tanımdan türetilir ve deponun birim tablosuyla uyuşur.

        valve_feedline psi'yi 1 lbf/in^2 = lb*g_0/in^2 tanımından kurar.
        Depoda hrma/validation/record_adapters.py'de NIST değeri zaten
        tablodadır; iki kaynak birbirini tutmalıdır, yoksa aynı fiziksel
        büyüklük iki farklı sayıyla dolaşıyor demektir.
        """
        from hrma.validation.record_adapters import UNIT_TO_SI

        beklenen = POUND_KG * G_0 / INCH_M ** 2
        assert PSI_PA == pytest.approx(beklenen, rel=1e-12)
        assert LB_KG == POUND_KG
        assert PSI_PA == pytest.approx(UNIT_TO_SI['psi'], rel=1e-9)

    def test_kv_cv_orani_birim_tanimlarindan_turetilir(self):
        """Kv/Cv = 0.865 birim tanımlarının sonucudur, keyfi bir sabit değil.

        Cv: 1 psi'de geçen ABD gpm; Kv: 1 bar'da geçen m^3/h. Aynı vana,
        aynı akışkan, aynı dP için:
            Cv = Q_gpm / sqrt(dP_psi/SG),  Kv = Q_m3h / sqrt(dP_bar/SG)
        Q_gpm = Q_m3h / (gpm->m^3/h) ve dP_psi = dP_bar / (psi->bar)
        yerine konursa   Kv/Cv = (gpm->m^3/h) / sqrt(psi->bar).
        """
        gpm_to_m3h = GALLON_M3 * 60.0            # m^3/h per gpm
        psi_to_bar = PSI_PA / 1.0e5              # bar per psi
        oran = gpm_to_m3h / math.sqrt(psi_to_bar)
        # Standart 0.865'e yuvarlanır; tanımdan gelen değer 0.8650...
        assert oran == pytest.approx(KV_PER_CV, abs=5e-4)
        # Gidiş-dönüş özdeşliği
        assert kv_to_cv(cv_to_kv(7.3)) == pytest.approx(7.3, rel=1e-12)

    def test_yerel_kayip_hizda_tam_ikinci_derece(self):
        """dP_yerel = K*rho*V^2/2: hız iki katına çıkınca kayıp tam 4 katı.

        Sürtünme terimi f(Re) yüzünden tam kuadratik DEĞİLDİR; yerel terim
        ise tanımı gereği tam kuadratiktir. Boyut bekçisi budur.
        """
        ortak = dict(density_kg_m3=1000.0, viscosity_Pa_s=1.0e-3,
                     line_id_m=0.02, line_length_m=1.0,
                     fittings={'elbow_90_standard': 3})
        a = line_pressure_drop(mass_flow_kg_s=1.0, **ortak)
        b = line_pressure_drop(mass_flow_kg_s=2.0, **ortak)
        assert b['flow']['velocity_m_s'] == pytest.approx(
            2.0 * a['flow']['velocity_m_s'], rel=1e-12)
        assert b['minor_losses']['dp_Pa'] == pytest.approx(
            4.0 * a['minor_losses']['dp_Pa'], rel=1e-12)
        # K aynı kalmalı (hızdan bağımsız, yalnız geometriye bağlı)
        assert b['minor_losses']['k_total'] == pytest.approx(
            a['minor_losses']['k_total'], rel=1e-12)

    def test_sg_referans_yogunlugu_standarda_bagli(self):
        """SG referansı IEC 60534'ün tanımladığı değere sabitlenir.

        NEDEN AYRI TEST: Cv gidiş-dönüş testleri referans yoğunluğu
        DENKLEMİN İKİ YANINDA da kullandığı için, bu sabitin sessizce
        değişmesini yakalayamaz (mutasyon denemesinde 999 -> 1000
        değişikliği tüm testlerden geçti). Referans, standardın tanımıdır:
        IEC 60534-2-1 / ISA-75.01.01 bağıl yoğunluğu 15.6 C'deki suya
        göre alır, rho_0 = 999.0 kg/m^3. Yayımlanmış bir kaynak değeri
        olduğu için sabite bağlanması meşrudur; fizik bandıyla da
        çapraz kontrol edilir.
        """
        assert SG_REFERENCE_DENSITY_KG_M3 == pytest.approx(999.0, abs=1e-9)
        # Fizik bandı: suyun 15.6 C'deki yoğunluğu 999 kg/m^3 civarındadır
        assert 998.0 <= SG_REFERENCE_DENSITY_KG_M3 <= 1000.0
        # 20 C suyu (998 kg/m^3) için SG pratikte 1'e çok yakın olmalı
        sg_su = 998.0 / SG_REFERENCE_DENSITY_KG_M3
        assert sg_su == pytest.approx(1.0, abs=2e-3)

    def test_ozgul_gaz_sabiti_merkezi_sabitten(self):
        """R = R_evrensel/MW; merkezî CODATA sabiti kullanılır."""
        assert specific_gas_constant(28.0134) == pytest.approx(
            R_UNIVERSAL / 28.0134, rel=1e-12)
        # Havanın R'si ~287 J/(kg.K) mertebesinde olmalı (boyut kontrolü)
        assert 280.0 < specific_gas_constant(28.9644) < 292.0


# ===========================================================================
# (b) Kapalı-form karşılaştırmalar — C2
# ===========================================================================
class TestC2KapaliForm:
    def test_laminer_dal_64_bolu_re_ile_tam_eslesir(self):
        """Laminer rejimde f = 64/Re kapalı formuyla TAM eşleşme.

        Hagen-Poiseuille (White 7. baskı Eş. 6.12). Girdiler laminer
        kalacak biçimde seçilir (yüksek viskozite).
        """
        rho, mu, d = 900.0, 0.5, 0.02
        mdot = 0.5
        v = line_velocity(mdot, rho, d)
        re = reynolds_number(rho, v, d, mu)
        assert flow_regime(re) == 'laminar'
        out = line_pressure_drop(mass_flow_kg_s=mdot, density_kg_m3=rho,
                                 viscosity_Pa_s=mu, line_id_m=d,
                                 line_length_m=3.0)
        f_beklenen = 64.0 / re
        assert out['friction']['darcy_friction_factor'] == pytest.approx(
            f_beklenen, rel=1e-12)
        # Kapalı form: dP = f*(L/D)*rho*V^2/2
        dp_beklenen = f_beklenen * (3.0 / d) * 0.5 * rho * v * v
        assert out['friction']['dp_Pa'] == pytest.approx(dp_beklenen,
                                                         rel=1e-12)

    @pytest.mark.parametrize('re,eps_d', [
        (1.0e4, 0.0), (1.0e5, 1.0e-4), (1.0e6, 1.0e-3), (1.0e7, 1.0e-2),
    ])
    def test_haaland_kapali_form_colebrook_ile_uyusur(self, re, eps_d):
        """Haaland, testin içinde çözülen Colebrook ile %2 içinde uyuşur.

        Colebrook örtük denklemi burada BAĞIMSIZ olarak sabit nokta
        iterasyonuyla çözülür:
            1/sqrt(f) = -2*log10(eps/D/3.7 + 2.51/(Re*sqrt(f)))
        Haaland'ın yayımlanmış doğruluk iddiası Re > ~4000 için ~%2'dir
        (White 7. baskı Eş. 6.49); tolerans bu iddiadan gelir.
        """
        f = 0.02
        for _ in range(200):
            f_yeni = 1.0 / (-2.0 * math.log10(
                eps_d / 3.7 + 2.51 / (re * math.sqrt(f)))) ** 2
            if abs(f_yeni - f) < 1e-15:
                f = f_yeni
                break
            f = f_yeni
        assert haaland_friction_factor(re, eps_d) == pytest.approx(
            f, rel=0.02)

    def test_crane_ft_yayimlanmis_tabloyu_yeniden_uretir(self):
        """Türetilen f_T, Crane TP-410'un yayımlanmış tablosunu verir.

        Crane f_T'yi ticari çelik boru için boyuta göre tablolar; bu modül
        onu tam-pürüzlü Haaland limitinden TÜRETİR. İç çaplar Schedule 40
        anma ölçüleridir (ASME B36.10M). Tolerans %5: türetim ile tablo
        arasındaki en büyük ölçülen sapma ~%4'tür (1/2" ve 4"), ve Crane'in
        kendi değerleri iki haneye yuvarlanmıştır.
        """
        # (anma, Sch-40 iç çap [m], Crane f_T)
        crane_tablosu = [
            ('1/2"', 0.01580, 0.027),
            ('1"', 0.02664, 0.023),
            ('2"', 0.05250, 0.019),
            ('4"', 0.10226, 0.017),
            ('6"', 0.15405, 0.015),
            ('8"', 0.20272, 0.014),
        ]
        for anma, d, ft_yayin in crane_tablosu:
            ft = crane_ft(d)
            assert ft == pytest.approx(ft_yayin, rel=0.05), (
                f'{anma}: türetilen f_T={ft:.5f}, Crane tablosu {ft_yayin}')
        # f_T çapla monoton azalır (büyük boru -> düşük bağıl pürüzlülük)
        capla = [crane_ft(d) for _, d, _ in crane_tablosu]
        assert all(capla[i] > capla[i + 1] for i in range(len(capla) - 1))

    def test_crane_k_esdeger_uzunluk_tanimini_izler(self):
        """K = f_T*(L/D)_eş özdeşliği tablodaki her kalem için sağlanır."""
        d = 0.0254
        ft = crane_ft(d, CRANE_FT_ROUGHNESS_M)
        for isim, ld in FITTING_LD.items():
            assert fitting_loss_coefficient(isim, d) == pytest.approx(
                ft * ld, rel=1e-12)
        # Globe vana, tam açık küresel vanadan çok daha dirençlidir
        assert (fitting_loss_coefficient('globe_valve_open', d)
                > 50.0 * fitting_loss_coefficient('ball_valve_full_bore', d))

    def test_cv_tersine_cozum_tutarliligi(self):
        """Cv boyutlandırması tersine çözümle kendini kapatır.

        Cv = Q*sqrt(SG/dP) ile Q = Cv*sqrt(dP/SG) birbirinin tersidir;
        zincir herhangi bir birim çevriminde kaymışsa bu test kırılır.
        """
        for q, dp, rho in [(0.01, 2.0e5, 998.0), (0.25, 5.0e5, 1141.0),
                           (1.0e-3, 3.0e4, 810.0)]:
            cv = valve_cv_required(q, dp, rho)
            assert flow_from_cv(cv, dp, rho) == pytest.approx(q, rel=1e-12)

    def test_cv_tanimi_referans_suda_birim_degeri_verir(self):
        """Cv tanımı: 1 psi'de 1 gpm su -> Cv = 1.

        ISA-75.01.01 tanımının kendisi. Referans yoğunlukta (SG = 1)
        1 galon/dakika akış 1 psi düşümle geçiyorsa Cv tam 1 olmalıdır.
        """
        q_1gpm = GALLON_M3 / 60.0            # m^3/s
        cv = valve_cv_required(q_1gpm, PSI_PA, SG_REFERENCE_DENSITY_KG_M3)
        assert cv == pytest.approx(1.0, rel=1e-12)

    def test_ff_faktoru_iec_kapali_formu(self):
        """F_F = 0.96 - 0.28*sqrt(pv/pc) kapalı formu ve uç değerleri."""
        assert liquid_critical_pressure_ratio_factor(0.0, 22.064e6) == (
            pytest.approx(0.96, rel=1e-12))
        # pv = pc -> 0.96 - 0.28 = 0.68
        assert liquid_critical_pressure_ratio_factor(
            22.064e6, 22.064e6) == pytest.approx(0.68, rel=1e-12)
        # Su, 20 C: pv = 2339 Pa
        ff = liquid_critical_pressure_ratio_factor(2339.0, 22.064e6)
        assert ff == pytest.approx(0.96 - 0.28 * math.sqrt(2339.0 / 22.064e6),
                                   rel=1e-12)

    def test_bogulma_basinci_kapali_formu(self):
        """dP_boğuk = F_L^2*(p1 - F_F*pv) kapalı formu."""
        p1, pv, pc, fl = 30.0e5, 2339.0, 22.064e6, 0.60
        ff = liquid_critical_pressure_ratio_factor(pv, pc)
        assert choked_pressure_drop(p1, pv, pc, fl) == pytest.approx(
            fl * fl * (p1 - ff * pv), rel=1e-12)

    def test_su_kocu_minimum_kapanma_suresi_michaud_tersi(self):
        """t_min = 2*rho*L*dv/dP_izin, Michaud bağıntısının tam tersi."""
        rho, L, dv, dp = 998.0, 12.0, 3.0, 4.0e5
        t = minimum_closure_time_s(density_kg_m3=rho, line_length_m=L,
                                   delta_velocity_m_s=dv,
                                   allowable_pressure_rise_Pa=dp)
        assert t == pytest.approx(2.0 * rho * L * dv / dp, rel=1e-12)
        # Geri koy: dP_yavaş = 2*rho*L*dv/t -> tam olarak izin verilen değer
        assert 2.0 * rho * L * dv / t == pytest.approx(dp, rel=1e-12)


# ===========================================================================
# (b) Kapalı-form karşılaştırmalar — C3
# ===========================================================================
class TestC3KapaliForm:
    def test_basit_kaldirac_dengesi(self):
        """M = F*e ve F_akt = M/r_a basit kaldıraç dengesiyle doğrulanır."""
        f, e, r_a = 1.0e6, 0.012, 0.45
        out = actuator_load(thrust_N=f, gimbal_angle_deg=5.0,
                            actuator_arm_m=r_a, thrust_offset_m=e)
        assert out['moment_budget']['thrust_offset_N_m'] == pytest.approx(
            f * e, rel=1e-12)
        assert out['moment_budget']['total_N_m'] == pytest.approx(
            f * e, rel=1e-12)
        assert out['actuator']['force_total_N'] == pytest.approx(
            f * e / r_a, rel=1e-12)

    def test_moment_terimleri_ayri_ayri_kapali_form(self):
        """Hat yayı ve atalet terimleri kapalı formlarıyla eşleşir."""
        k_duct, i_eng, omega, t_rev = 30000.0, 900.0, 12.0, 0.25
        aci = 8.0
        out = actuator_load(thrust_N=5.0e5, gimbal_angle_deg=aci,
                            actuator_arm_m=0.5, thrust_offset_m=0.0,
                            duct_torsional_stiffness_N_m_rad=k_duct,
                            engine_inertia_kg_m2=i_eng,
                            slew_rate_deg_s=omega,
                            slew_reversal_time_s=t_rev)
        mb = out['moment_budget']
        assert mb['flex_duct_N_m'] == pytest.approx(
            k_duct * math.radians(aci), rel=1e-12)
        # alfa = 2*omega/t_tersinme
        alfa = 2.0 * math.radians(omega) / t_rev
        assert mb['inertia_N_m'] == pytest.approx(i_eng * alfa, rel=1e-12)
        assert mb['total_N_m'] == pytest.approx(
            mb['flex_duct_N_m'] + mb['inertia_N_m'], rel=1e-12)

    def test_civata_dairesi_dogrudan_toplamla_kurulur(self):
        """F_maks = 4M/(nD), n cıvata üzerinden moment toplamıyla doğrulanır.

        F_i = F_maks*cos(th_i) ve kol y_i = (D/2)*cos(th_i) alınırsa
        M = sum F_i*y_i özdeşliği sağlanmalıdır (Shigley Böl. 8).
        """
        for n in (3, 4, 6, 8, 12, 20):
            m, d = 7500.0, 0.75
            f_maks = bolt_circle_max_load(m, d, n)
            m_geri = sum(
                f_maks * math.cos(2.0 * math.pi * i / n)
                * (d / 2.0) * math.cos(2.0 * math.pi * i / n)
                for i in range(n))
            assert m_geri == pytest.approx(m, rel=1e-9), f'n={n}'

    def test_itki_bilesenleri_pisagor_kimligini_saglar(self):
        """Eksenel^2 + yanal^2 = itki^2 (dik bileşenler)."""
        for aci in (0.5, 3.0, 6.0, 10.5, 20.0):
            tc = thrust_components(2.0e6, aci)
            assert math.hypot(tc['axial_N'], tc['side_N']) == pytest.approx(
                2.0e6, rel=1e-12)
            assert tc['thrust_loss_N'] == pytest.approx(
                2.0e6 - tc['axial_N'], rel=1e-12)

    def test_strok_kiris_ve_yay_arasinda_sikisir(self):
        """kiriş <= gerçek strok <= yay; küçük açıda ikisi birleşir."""
        for aci in (1.0, 5.0, 15.0, 30.0):
            s = actuator_stroke(0.4, aci)
            assert s['stroke_chord_m'] <= s['stroke_arc_m']
            assert s['stroke_arc_m'] == pytest.approx(
                0.4 * math.radians(aci), rel=1e-12)
        # 1 derecede kiriş ile yay birbirine %0.01'den yakın
        kucuk = actuator_stroke(0.4, 1.0)
        assert kucuk['stroke_chord_m'] == pytest.approx(
            kucuk['stroke_arc_m'], rel=1e-4)

    def test_iki_eksen_bileske_kucuk_acida_karekok_toplama_gider(self):
        """cos(bileşke) = cos(p)*cos(y); küçük açıda sqrt(p^2+y^2)."""
        r = resultant_gimbal_angle_deg(0.5, 0.5)
        assert r == pytest.approx(0.5 * math.sqrt(2.0), rel=1e-3)
        # Kesin bağıntı
        r2 = resultant_gimbal_angle_deg(8.0, 6.0)
        assert math.cos(math.radians(r2)) == pytest.approx(
            math.cos(math.radians(8.0)) * math.cos(math.radians(6.0)),
            rel=1e-12)

    def test_halka_kesit_zorlamalari_serbest_cisim(self):
        """N, V, M serbest cisim dengesiyle eşleşir."""
        f, aci, h = 8.0e5, 7.0, 0.35
        r = mount_ring_loads(thrust_N=f, gimbal_angle_deg=aci,
                             ring_offset_m=h)
        s = r['section_loads']
        assert s['axial_N'] == pytest.approx(
            f * math.cos(math.radians(aci)), rel=1e-12)
        assert s['shear_N'] == pytest.approx(
            f * math.sin(math.radians(aci)), rel=1e-12)
        assert s['bending_moment_N_m'] == pytest.approx(
            s['shear_N'] * h, rel=1e-12)


# ===========================================================================
# (b) Kapalı-form karşılaştırmalar — C4
# ===========================================================================
class TestC4KapaliForm:
    def test_atesleme_enerjisi_duyulur_isi_dengesi(self):
        """E = mdot*t*cp*dT/eta kapalı formu."""
        mdot, t, cp, t_ign, t_0, eta = 4.0, 0.15, 1800.0, 750.0, 290.0, 0.35
        e = ignition_energy_required(
            main_mass_flow_kg_s=mdot, ignition_window_s=t,
            specific_heat_J_kg_K=cp, ignition_temperature_K=t_ign,
            initial_temperature_K=t_0, transfer_efficiency=eta)
        assert e['heated_mass_kg'] == pytest.approx(mdot * t, rel=1e-12)
        assert e['energy_ideal_J'] == pytest.approx(
            mdot * t * cp * (t_ign - t_0), rel=1e-12)
        assert e['energy_J'] == pytest.approx(
            e['energy_ideal_J'] / eta, rel=1e-12)

    def test_torc_enerji_korunumu_gidis_donus(self):
        """Torç: mdot*Q*eta*t, gereken enerjiyi TAM karşılar.

        Enerji korunumu bekçisi: boyutlandırılan debi, tanımı gereği
        gereken enerjiyi pencere içinde teslim etmelidir.
        """
        e_req, t_win, q, eta = 2.5e6, 0.2, 12.0e6, 0.9
        mdot = torch_propellant_flow(
            required_energy_J=e_req, ignition_window_s=t_win,
            torch_heat_release_J_kg=q, combustion_efficiency=eta)
        assert mdot * q * eta * t_win == pytest.approx(e_req, rel=1e-12)

    def test_piroteknik_ideal_gaz_gidis_donus(self):
        """Şarj gazı, serbest hacimde tam hedef basıncı üretir.

        m_gaz*R*T/V = P_ateş özdeşliği (ideal gaz korunumu) ve
        m_şarj*(1-X) = m_gaz kütle bölüşümü.
        """
        p_ign, v_free, mw, t_gas, x = 7.5e5, 0.02, 35.0, 2500.0, 0.56
        out = pyrotechnic_charge_mass(
            ignition_pressure_Pa=p_ign, free_volume_m3=v_free,
            gas_molecular_weight_g_mol=mw, gas_temperature_K=t_gas,
            condensed_mass_fraction=x)
        r = specific_gas_constant(mw)
        assert out['gas_mass_kg'] * r * t_gas / v_free == pytest.approx(
            p_ign, rel=1e-12)
        assert out['charge_mass_kg'] * (1.0 - x) == pytest.approx(
            out['gas_mass_kg'], rel=1e-12)

    def test_guvenli_pencere_sert_baslangic_tersine_cozum(self):
        """t_maks, birikmiş kütlenin tam izin verilen basıncı vermesi.

        safe_ignition_window_s ile hard_start_pressure birbirinin tersidir.
        """
        mdot, v_free, mw, t_flame, p_allow = 5.0, 0.02, 22.0, 3400.0, 50e5
        t_max = safe_ignition_window_s(
            main_mass_flow_kg_s=mdot, free_volume_m3=v_free,
            gas_molecular_weight_g_mol=mw, flame_temperature_K=t_flame,
            allowable_pressure_Pa=p_allow)
        p_geri = hard_start_pressure(
            main_mass_flow_kg_s=mdot, ignition_delay_s=t_max,
            free_volume_m3=v_free, gas_molecular_weight_g_mol=mw,
            flame_temperature_K=t_flame)
        assert p_geri == pytest.approx(p_allow, rel=1e-12)


# ===========================================================================
# (c) Monotonluk ve ölçekleme
# ===========================================================================
class TestMonotonluk:
    ORTAK_HAT = dict(mass_flow_kg_s=2.0, density_kg_m3=998.0,
                     viscosity_Pa_s=1.0e-3, line_id_m=0.0254)

    def test_uzun_hat_daha_cok_dusurur(self):
        kisa = line_pressure_drop(line_length_m=2.0, **self.ORTAK_HAT)
        uzun = line_pressure_drop(line_length_m=8.0, **self.ORTAK_HAT)
        assert uzun['friction']['dp_Pa'] > kisa['friction']['dp_Pa']
        # Sabit f'te dP uzunlukla doğrusal; f aynı kaldığı için oran tam 4
        assert uzun['friction']['dp_Pa'] == pytest.approx(
            4.0 * kisa['friction']['dp_Pa'], rel=1e-12)

    def test_buyuk_cap_daha_az_dusurur(self):
        dar = line_pressure_drop(mass_flow_kg_s=2.0, density_kg_m3=998.0,
                                 viscosity_Pa_s=1.0e-3, line_id_m=0.02,
                                 line_length_m=5.0)
        genis = line_pressure_drop(mass_flow_kg_s=2.0, density_kg_m3=998.0,
                                   viscosity_Pa_s=1.0e-3, line_id_m=0.04,
                                   line_length_m=5.0)
        assert genis['total']['dp_Pa'] < dar['total']['dp_Pa']
        assert genis['flow']['velocity_m_s'] < dar['flow']['velocity_m_s']

    def test_daha_cok_baglanti_daha_cok_kayip(self):
        az = line_pressure_drop(line_length_m=5.0,
                                fittings={'elbow_90_standard': 2},
                                **self.ORTAK_HAT)
        cok = line_pressure_drop(line_length_m=5.0,
                                 fittings={'elbow_90_standard': 6},
                                 **self.ORTAK_HAT)
        assert cok['minor_losses']['dp_Pa'] == pytest.approx(
            3.0 * az['minor_losses']['dp_Pa'], rel=1e-12)

    def test_cv_debiyle_artar_dusumle_azalir(self):
        temel = valve_cv_required(0.01, 2.0e5, 998.0)
        assert valve_cv_required(0.02, 2.0e5, 998.0) > temel
        assert valve_cv_required(0.01, 8.0e5, 998.0) < temel
        # Q ile doğrusal, sqrt(dP) ile ters
        assert valve_cv_required(0.02, 2.0e5, 998.0) == pytest.approx(
            2.0 * temel, rel=1e-12)
        assert valve_cv_required(0.01, 8.0e5, 998.0) == pytest.approx(
            temel / 2.0, rel=1e-12)

    def test_dusum_buyudukce_kavitasyon_kotulesir(self):
        """sigma dP ile azalır; durum sırayla kötüye gider."""
        p1, pv = 20.0e5, 2339.0
        onceki = None
        for p2 in (18.0e5, 12.0e5, 6.0e5, 1.0e5):
            c = cavitation_status(p1, p2, pv)
            if onceki is not None:
                assert c['sigma'] < onceki
            onceki = c['sigma']
        # Çıkış buhar basıncının altına inerse flashing
        assert cavitation_status(p1, 1000.0, pv)['status'] == 'flashing'

    def test_buyuk_kol_kucuk_aktuator_kuvveti(self):
        kisa = actuator_load(thrust_N=1.0e6, gimbal_angle_deg=6.0,
                             actuator_arm_m=0.3, thrust_offset_m=0.01)
        uzun = actuator_load(thrust_N=1.0e6, gimbal_angle_deg=6.0,
                             actuator_arm_m=0.6, thrust_offset_m=0.01)
        assert uzun['actuator']['force_total_N'] == pytest.approx(
            kisa['actuator']['force_total_N'] / 2.0, rel=1e-12)

    def test_buyuk_aci_daha_cok_yanal_kuvvet_ve_kayip(self):
        onceki_yanal, onceki_kayip = -1.0, -1.0
        for aci in (1.0, 4.0, 8.0, 12.0):
            tc = thrust_components(1.0e6, aci)
            assert tc['side_N'] > onceki_yanal
            assert tc['thrust_loss_N'] > onceki_kayip
            onceki_yanal, onceki_kayip = tc['side_N'], tc['thrust_loss_N']

    def test_daha_cok_civata_daha_az_yuk(self):
        az = bolt_circle_max_load(5000.0, 0.6, 6)
        cok = bolt_circle_max_load(5000.0, 0.6, 12)
        assert cok == pytest.approx(az / 2.0, rel=1e-12)
        # Büyük cıvata dairesi de yükü azaltır
        assert bolt_circle_max_load(5000.0, 1.2, 6) == pytest.approx(
            az / 2.0, rel=1e-12)

    def test_atesleyici_enerjisi_girdilerle_dogrusal(self):
        temel = ignition_energy_required(
            main_mass_flow_kg_s=4.0, ignition_window_s=0.1,
            specific_heat_J_kg_K=2000.0, ignition_temperature_K=700.0,
            initial_temperature_K=300.0, transfer_efficiency=0.3)['energy_J']
        iki_kat_debi = ignition_energy_required(
            main_mass_flow_kg_s=8.0, ignition_window_s=0.1,
            specific_heat_J_kg_K=2000.0, ignition_temperature_K=700.0,
            initial_temperature_K=300.0, transfer_efficiency=0.3)['energy_J']
        assert iki_kat_debi == pytest.approx(2.0 * temel, rel=1e-12)
        # eta artarsa gereken enerji azalır (1/eta)
        yuksek_eta = ignition_energy_required(
            main_mass_flow_kg_s=4.0, ignition_window_s=0.1,
            specific_heat_J_kg_K=2000.0, ignition_temperature_K=700.0,
            initial_temperature_K=300.0, transfer_efficiency=0.6)['energy_J']
        assert yuksek_eta == pytest.approx(temel / 2.0, rel=1e-12)

    def test_buyuk_serbest_hacim_buyuk_sarj(self):
        ortak = dict(ignition_pressure_Pa=7.5e5,
                     gas_molecular_weight_g_mol=35.0,
                     gas_temperature_K=2500.0, condensed_mass_fraction=0.5)
        kucuk = pyrotechnic_charge_mass(free_volume_m3=0.01, **ortak)
        buyuk = pyrotechnic_charge_mass(free_volume_m3=0.04, **ortak)
        assert buyuk['charge_mass_kg'] == pytest.approx(
            4.0 * kucuk['charge_mass_kg'], rel=1e-12)

    def test_buyuk_debi_kisa_guvenli_pencere(self):
        ortak = dict(free_volume_m3=0.02, gas_molecular_weight_g_mol=22.0,
                     flame_temperature_K=3400.0, allowable_pressure_Pa=50e5)
        yavas = safe_ignition_window_s(main_mass_flow_kg_s=2.0, **ortak)
        hizli = safe_ignition_window_s(main_mass_flow_kg_s=8.0, **ortak)
        assert hizli == pytest.approx(yavas / 4.0, rel=1e-12)


# ===========================================================================
# (d) Sözleşme: su koçu girdisi gerçekten çalışıyor
# ===========================================================================
class TestSuKocuSozlesmesi:
    def test_uretilen_girdi_water_hammer_tarafindan_kabul_edilir(self):
        """valve_feedline'ın ürettiği kwargs GERÇEKTEN analyze()'a giriyor.

        Bu bekçi, iki modül arasındaki sözleşmenin kağıt üstünde değil
        fiilen kurulduğunu sınar: anahtar adı veya birim kayarsa test
        kırılır.
        """
        from hrma.analysis.water_hammer import WaterHammerAnalyzer

        wh_in = water_hammer_inputs(
            fluid='water', mass_flow_kg_s=2.0, density_kg_m3=998.0,
            line_id_m=0.0254, wall_thickness_m=0.0015, line_length_m=5.0,
            working_pressure_Pa=25.0e5, bulk_modulus_Pa=2.19e9,
            pipe_youngs_modulus_Pa=193.0e9,
            allowable_pressure_rise_Pa=5.0e5, vapor_pressure_Pa=2339.0)
        out = WaterHammerAnalyzer().analyze(**wh_in['analyzer_kwargs'])
        assert out['status'] in ('SAFE', 'MARGINAL', 'UNSAFE')
        # Hız ve uzunluk gerçekten taşınmış olmalı
        assert wh_in['analyzer_kwargs']['flow_velocity_m_s'] == (
            pytest.approx(wh_in['flow_velocity_m_s'], rel=1e-12))
        assert wh_in['analyzer_kwargs']['line_id_mm'] == pytest.approx(
            25.4, rel=1e-12)
        # Kritik süre water_hammer'ın kendi tanımıyla: t_c = 2L/a
        assert wh_in['critical_closure_time_s'] == pytest.approx(
            2.0 * 5.0 / wh_in['wave_speed_m_s'], rel=1e-12)
        # Esnek boru dalga hızı rijit değerin altında kalmalı
        assert wh_in['wave_speed_m_s'] < wh_in['wave_speed_rigid_m_s']

    def test_dalga_hizi_verilmeyince_uydurulmaz(self):
        """Young modülü yoksa dalga hızı HESAPLANMAZ, sayı uydurulmaz."""
        wh_in = water_hammer_inputs(
            fluid='water', mass_flow_kg_s=2.0, density_kg_m3=998.0,
            line_id_m=0.0254, wall_thickness_m=0.0015, line_length_m=5.0,
            working_pressure_Pa=25.0e5)
        assert wh_in['wave_speed_m_s'] is None
        assert wh_in['critical_closure_time_s'] is None
        assert any('NOT computed' in n for n in wh_in['notes'])

    def test_cok_siki_surge_izni_zamanlamayla_saglanamaz(self):
        """t_min <= t_c ise kapanma zamanlaması TEK BAŞINA yetmez, denir."""
        wh_in = water_hammer_inputs(
            fluid='water', mass_flow_kg_s=2.0, density_kg_m3=998.0,
            line_id_m=0.0254, wall_thickness_m=0.0015, line_length_m=5.0,
            working_pressure_Pa=25.0e5, bulk_modulus_Pa=2.19e9,
            pipe_youngs_modulus_Pa=193.0e9,
            allowable_pressure_rise_Pa=200.0e5)
        assert wh_in['closure_time']['status'] == 'unreachable_by_scheduling'
        assert 'Joukowsky' in wh_in['closure_time']['message']


# ===========================================================================
# (e) Dürüstlük: geçersiz aralık, uydurma yok, NOT_MODELLED
# ===========================================================================
class TestDurustluk:
    def test_sert_aralik_disi_valuerror_uretir(self):
        """Sert geçerlilik aralığı dışında sessiz ekstrapolasyon YOK."""
        # F_L bandı dışı
        with pytest.raises(ValueError, match='validity range'):
            choked_pressure_drop(20e5, 2339.0, 22.064e6,
                                 VALVE_FL_VALID[1] + 0.1)
        # Gimbal açısı sert aralık dışı
        with pytest.raises(ValueError, match='validity range'):
            thrust_components(1.0e6, GIMBAL_ANGLE_VALID_DEG[1] + 1.0)
        # Cıvata sayısı formülün geçerli olmadığı bölgede
        with pytest.raises(ValueError, match='below the minimum'):
            bolt_circle_max_load(1000.0, 0.5, BOLT_COUNT_MIN - 1)
        # Aktarım verimi bandı dışı
        with pytest.raises(ValueError, match='validity range'):
            ignition_energy_required(
                main_mass_flow_kg_s=1.0, ignition_window_s=0.1,
                specific_heat_J_kg_K=2000.0, ignition_temperature_K=700.0,
                initial_temperature_K=300.0,
                transfer_efficiency=TRANSFER_EFFICIENCY_VALID[1] + 0.5)
        # Ateşleme basıncı kesri bandı dışı
        with pytest.raises(ValueError, match='validity range'):
            size_igniter(
                igniter_type='pyrotechnic', chamber_free_volume_m3=0.02,
                main_mass_flow_kg_s=5.0, ignition_window_s=0.05,
                propellant_specific_heat_J_kg_K=2000.0,
                propellant_ignition_temperature_K=700.0,
                chamber_pressure_Pa=50e5,
                ignition_pressure_fraction=(
                    IGNITION_PRESSURE_FRACTION_VALID[1] + 0.2),
                charge_gas_molecular_weight_g_mol=35.0,
                charge_flame_temperature_K=2500.0,
                charge_condensed_mass_fraction=0.5)

    def test_gecis_rejimi_acikca_beyan_edilir(self):
        """Re 2300-4000 arasında geçerlilik beyanı konur, sessizce geçilmez."""
        # Geçiş bandına düşecek girdi seç
        rho, mu, d = 1000.0, 0.02, 0.05
        mdot = 3000.0 * mu * math.pi * d / 4.0   # Re ~ 3000
        out = line_pressure_drop(mass_flow_kg_s=mdot, density_kg_m3=rho,
                                 viscosity_Pa_s=mu, line_id_m=d,
                                 line_length_m=2.0)
        assert out['flow']['regime'] == 'transitional'
        alanlar = [v['field'] for v in out['validity']]
        assert 'friction_factor' in alanlar
        kayit = [v for v in out['validity']
                 if v['field'] == 'friction_factor'][0]
        assert kayit['status'] == 'out_of_validity'
        assert 'no silent extrapolation' in kayit['message']

    def test_asiri_puruzluluk_gecerlilik_disi_beyani(self):
        """eps/D Colebrook zarfını aşarsa açık beyan konur."""
        out = line_pressure_drop(
            mass_flow_kg_s=2.0, density_kg_m3=998.0, viscosity_Pa_s=1.0e-3,
            line_id_m=0.02, line_length_m=2.0,
            roughness_m=0.02 * (REL_ROUGHNESS_VALID[1] + 0.02))
        assert any(v['field'] == 'relative_roughness'
                   and v['status'] == 'out_of_validity'
                   for v in out['validity'])

    def test_kavitasyon_verisi_yoksa_hukum_verilmez(self):
        """Buhar/kritik basınç yoksa 'güvenli' denmez, 'değerlendirilmedi' denir."""
        out = size_valve(mass_flow_kg_s=2.0, density_kg_m3=998.0,
                         inlet_pressure_Pa=20.0e5,
                         pressure_drop_Pa=5.0e5)
        assert out['cavitation'] is None
        kayit = [v for v in out['validity'] if v['field'] == 'cavitation']
        assert kayit and kayit[0]['status'] == 'not_evaluated'
        assert 'No safe/unsafe verdict is implied' in kayit[0]['message']

    def test_moment_kaynagi_yoksa_sifir_kuvvet_isaretlenir(self):
        """Hiç moment kaynağı yoksa '0 N aktüatör' sessizce verilmez."""
        out = actuator_load(thrust_N=1.0e6, gimbal_angle_deg=6.0,
                            actuator_arm_m=0.5)
        assert out['actuator']['force_total_N'] == 0.0
        kayit = [v for v in out['validity']
                 if v['field'] == 'actuator_force_N']
        assert kayit and kayit[0]['status'] == 'not_evaluated'
        assert 'NOT a design load' in kayit[0]['message']
        assert out['warnings']

    def test_yonelim_hizi_tek_basina_ivme_uretmez(self):
        """Yalnız yönelim hızı verilirse açısal ivme UYDURULMAZ."""
        s = slew_angular_acceleration(slew_rate_deg_s=10.0)
        assert s['status'] == 'not_computed'
        assert s['angular_acceleration_rad_s2'] is None
        assert 'does not determine an acceleration' in s['message']
        # Atalet momenti de bütçeye girmemeli
        out = actuator_load(thrust_N=1.0e6, gimbal_angle_deg=6.0,
                            actuator_arm_m=0.5, thrust_offset_m=0.01,
                            engine_inertia_kg_m2=900.0,
                            slew_rate_deg_s=10.0)
        assert out['moment_budget']['inertia_N_m'] == 0.0
        assert out['inertia']['status'] == 'not_computed'

    def test_piroteknik_girdi_eksikse_sayi_uretilmez(self):
        """Şarj kataloğu yoksa şarj kütlesi uydurulmaz."""
        out = size_igniter(
            igniter_type='pyrotechnic', chamber_free_volume_m3=0.02,
            main_mass_flow_kg_s=5.0, ignition_window_s=0.05,
            propellant_specific_heat_J_kg_K=2000.0,
            propellant_ignition_temperature_K=700.0)
        assert out['pyrotechnic']['status'] == 'not_modelled'
        assert 'will not invent one' in out['pyrotechnic']['reason']
        assert 'charge_mass_kg' not in out['pyrotechnic']

    def test_torc_isi_salimi_zorunlu(self):
        """Torç için ısı salımı verilmezse varsayılan UYDURULMAZ."""
        with pytest.raises(ValueError, match='No default is assumed'):
            size_igniter(
                igniter_type='torch', chamber_free_volume_m3=0.02,
                main_mass_flow_kg_s=5.0, ignition_window_s=0.05,
                propellant_specific_heat_J_kg_K=2000.0,
                propellant_ignition_temperature_K=700.0)

    def test_sert_baslangic_penceresi_asilirsa_uyarilir(self):
        """Pencere sert başlangıç sınırını aşarsa açık uyarı üretilir."""
        out = size_igniter(
            igniter_type='torch', chamber_free_volume_m3=0.02,
            main_mass_flow_kg_s=5.0, ignition_window_s=0.5,
            propellant_specific_heat_J_kg_K=2000.0,
            propellant_ignition_temperature_K=700.0,
            chamber_pressure_Pa=50e5,
            main_gas_molecular_weight_g_mol=22.0,
            main_flame_temperature_K=3400.0,
            torch_heat_release_J_kg=10.0e6)
        assert out['safe_window']['verdict'] == 'exceeds_window'
        assert out['safe_window']['margin_ratio'] < 1.0
        assert any('hard-start bound' in w for w in out['warnings'])

    def test_pratik_bandi_disi_gimbal_acisi_beyan_edilir(self):
        """Pratik bandı dışı açı ValueError DEĞİL, beyan üretir."""
        aci = GIMBAL_ANGLE_PRACTICE_BAND_DEG[1] + 5.0
        assert aci < GIMBAL_ANGLE_VALID_DEG[1]
        out = actuator_load(thrust_N=1.0e6, gimbal_angle_deg=aci,
                            actuator_arm_m=0.5, thrust_offset_m=0.01)
        assert any(v['field'] == 'gimbal_angle_deg'
                   and v['status'] == 'outside_practice_band'
                   for v in out['validity'])
        # Yine de sayı üretilmiş olmalı (sert aralık içinde)
        assert out['actuator']['force_total_N'] > 0.0

    @pytest.mark.parametrize('nm', [
        VALVE_NOT_MODELLED, GIMBAL_NOT_MODELLED, IGNITER_NOT_MODELLED])
    def test_not_modelled_beyanlari_dolu_ve_aciklayici(self, nm):
        """Her modül NOT_MODELLED sözlüğünü doldurur ve 'NOT' der."""
        assert len(nm) >= 5
        for anahtar, metin in nm.items():
            assert isinstance(metin, str) and len(metin) > 60
            assert 'NOT ' in metin, anahtar

    def test_ciktilar_not_modelled_tasir(self):
        """Ana giriş noktalarının çıktısı NOT_MODELLED beyanını taşır."""
        hat = line_pressure_drop(mass_flow_kg_s=2.0, density_kg_m3=998.0,
                                 viscosity_Pa_s=1.0e-3, line_id_m=0.0254,
                                 line_length_m=5.0)
        assert hat['not_modelled'] == VALVE_NOT_MODELLED
        gim = analyze_gimbal_mount(thrust_N=1.0e6, gimbal_angle_deg=6.0,
                                   actuator_arm_m=0.5, thrust_offset_m=0.01)
        assert gim['not_modelled'] == GIMBAL_NOT_MODELLED
        ate = size_igniter(
            igniter_type='torch', chamber_free_volume_m3=0.02,
            main_mass_flow_kg_s=5.0, ignition_window_s=0.05,
            propellant_specific_heat_J_kg_K=2000.0,
            propellant_ignition_temperature_K=700.0,
            torch_heat_release_J_kg=10.0e6)
        assert ate['not_modelled'] == IGNITER_NOT_MODELLED

    def test_bilinmeyen_anahtarlar_reddedilir(self):
        """Bilinmeyen malzeme/eleman/vana/tip sessizce varsayılana düşmez."""
        with pytest.raises(ValueError, match='unknown pipe_material'):
            line_pressure_drop(mass_flow_kg_s=1.0, density_kg_m3=998.0,
                               viscosity_Pa_s=1.0e-3, line_id_m=0.02,
                               line_length_m=1.0, pipe_material='peynir')
        with pytest.raises(ValueError, match='unknown fitting'):
            fitting_loss_coefficient('warp_drive', 0.02)
        with pytest.raises(ValueError, match='unknown valve_style'):
            size_valve(mass_flow_kg_s=1.0, density_kg_m3=998.0,
                       inlet_pressure_Pa=20e5, pressure_drop_Pa=2e5,
                       valve_style='kapak')
        with pytest.raises(ValueError, match='unknown igniter_type'):
            size_igniter(igniter_type='mum', chamber_free_volume_m3=0.02,
                         main_mass_flow_kg_s=5.0, ignition_window_s=0.05,
                         propellant_specific_heat_J_kg_K=2000.0,
                         propellant_ignition_temperature_K=700.0)

    def test_fiziksel_olarak_imkansiz_girdiler_reddedilir(self):
        """Negatif/sıfır girdiler ve ters sıcaklıklar reddedilir."""
        with pytest.raises(ValueError):
            line_velocity(-1.0, 998.0, 0.02)
        with pytest.raises(ValueError):
            actuator_load(thrust_N=1.0e6, gimbal_angle_deg=6.0,
                          actuator_arm_m=0.0)
        with pytest.raises(ValueError, match='must exceed'):
            ignition_energy_required(
                main_mass_flow_kg_s=1.0, ignition_window_s=0.1,
                specific_heat_J_kg_K=2000.0, ignition_temperature_K=300.0,
                initial_temperature_K=400.0)
        # Vana düşümü giriş basıncını aşamaz
        with pytest.raises(ValueError, match='must stay below'):
            size_valve(mass_flow_kg_s=1.0, density_kg_m3=998.0,
                       inlet_pressure_Pa=5.0e5, pressure_drop_Pa=6.0e5)
        # Buhar basıncı kritik basıncı aşamaz
        with pytest.raises(ValueError, match='not a subcritical liquid'):
            liquid_critical_pressure_ratio_factor(3.0e7, 2.2e7)


# ===========================================================================
# Uçtan uca akış: zincirin bütünü çalışıyor ve JSON-güvenli
# ===========================================================================
class TestUctanUca:
    def test_valve_feedline_tam_zincir(self):
        import json

        out = analyze_valve_feedline(
            mass_flow_kg_s=2.0, density_kg_m3=998.0, viscosity_Pa_s=1.0e-3,
            line_id_m=0.0254, line_length_m=5.0, inlet_pressure_Pa=25.0e5,
            valve_pressure_drop_Pa=2.0e5, wall_thickness_m=0.0015,
            fluid='water',
            fittings={'elbow_90_long_radius': 4,
                      'ball_valve_full_bore': 1, 'entrance_sharp': 1},
            vapor_pressure_Pa=2339.0, critical_pressure_Pa=22.064e6,
            bulk_modulus_Pa=2.19e9, pipe_youngs_modulus_Pa=193.0e9,
            allowable_pressure_rise_Pa=5.0e5)
        # Bütçe kapanıyor mu
        b = out['budget']
        assert b['total_dp_Pa'] == pytest.approx(
            b['line_dp_Pa'] + b['valve_dp_Pa'], rel=1e-12)
        assert b['delivery_pressure_Pa'] == pytest.approx(
            b['inlet_pressure_Pa'] - b['total_dp_Pa'], rel=1e-9)
        assert out['valve']['capacity']['cv_required'] > 0.0
        assert out['water_hammer']['analyzer_kwargs']
        json.dumps(out)   # JSON-güvenli olmalı

    def test_gimbal_tam_zincir(self):
        import json

        out = analyze_gimbal_mount(
            thrust_N=1.0e6, gimbal_angle_deg=6.0, actuator_arm_m=0.5,
            ring_offset_m=0.4, thrust_offset_m=0.01,
            duct_torsional_stiffness_N_m_rad=25000.0,
            engine_inertia_kg_m2=1200.0, slew_rate_deg_s=10.0,
            slew_reversal_time_s=0.2, bolt_circle_diameter_m=0.8,
            bolt_count=12, yaw_angle_deg=6.0)
        assert out['actuator']['force_total_N'] > 0.0
        assert out['bolts']['moment_induced_max_N'] > 0.0
        assert out['two_axis']['resultant_angle_deg'] > 6.0
        json.dumps(out)

    def test_igniter_iki_tip_de_calisir(self):
        import json

        ortak = dict(chamber_free_volume_m3=0.02, main_mass_flow_kg_s=5.0,
                     propellant_specific_heat_J_kg_K=2000.0,
                     propellant_ignition_temperature_K=700.0,
                     chamber_pressure_Pa=50e5,
                     main_gas_molecular_weight_g_mol=22.0,
                     main_flame_temperature_K=3400.0)
        t = size_igniter(igniter_type='torch', ignition_window_s=0.01,
                         torch_heat_release_J_kg=10.0e6, **ortak)
        assert t['torch']['mass_flow_kg_s'] > 0.0
        assert t['safe_window']['verdict'] == 'within_window'
        p = size_igniter(igniter_type='pyrotechnic', ignition_window_s=0.01,
                         charge_gas_molecular_weight_g_mol=35.0,
                         charge_flame_temperature_K=2500.0,
                         charge_condensed_mass_fraction=0.56,
                         charge_heat_of_explosion_J_kg=3.0e6,
                         charge_density_kg_m3=1700.0,
                         charge_burn_time_s=0.3, **ortak)
        assert p['pyrotechnic']['status'] == 'sized'
        assert p['pyrotechnic']['charge_mass_kg'] > 0.0
        assert set(IGNITER_TYPES) == {'torch', 'pyrotechnic'}
        json.dumps(t)
        json.dumps(p)
