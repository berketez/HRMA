# -*- coding: utf-8 -*-
"""ÖH Dalga-23 / yapisal-sistem aşama 2 — bekçiler.

Ölçüm betiği: ``docs/scofield/raw/OH/D23/yapisal-sistem/a2/olcum.py``
(çıktılar ``once.json`` / ``sonra.json``, taban ef527ae).
Ters mutasyon kanıtı: aynı dizinde ``mutasyon.json``.

Kapsanan kalemler:
  P5B4-10  regresyon: yakıt akısı serileri yayımlanır; ``total_flux`` =
           ``oxidizer_flux`` eşitliği 'ox' kipinde ADIYLA gerekçelendirilir
  P5B4-11  ``port_diameter_final`` kapıdan geçer ve geri bildirilir; artık
           işe yaramayan 0,05 m varsayılanı UYDURULMAZ
  P5B4-12  port yarıçapı ODE'si açık Euler yerine RK4 ile çözülür; 'ox'
           kipinde kapalı çözüme oturur, şema adıyla yayımlanır
  P5B4-13  ``flux_mode='total'`` iken uydurma grain boyuyla eğri
           üretilmez (fail-closed)
  P5B4-14  torç akı oranı ateşleme penceresinden bağımsızdır; mesajlar
           artık pencereye yönlendirmez
  P5B4-15  piroteknik şarj: gaz sıcaklığı knob'u + alev sıcaklığı
           ikamesinin ADIYLA ve YÖNÜYLE beyanı
  P5B4-16  ``_require_positive`` TEK KAYNAK ve ``bool``u reddeder
  P5B4-20  ``bolt_count`` kesirli girdide kırpılmaz, reddedilir
  P5B4-21  negatif sapma açısı kabul edilir (bant BÜYÜKLÜĞE uygulanır)
  P5B4-22  iki eksen bileşkesi sert bandı aşarsa hüküm üretilmez
  P5B4-23  ``max_tension_*`` alanları negatif sayı taşımaz; işaretli net
           yük kendi adıyla yayımlanır
"""
import math

import pytest

from hrma.analysis import gimbal_mount as gm
from hrma.analysis import igniter_sizing as ig
from hrma.analysis import valve_feedline as vf
from hrma.analysis._input_guards import (require_positive,
                                         require_whole_number)
from hrma.analysis.gimbal_mount import (GIMBAL_ANGLE_VALID_DEG,
                                        analyze_gimbal_mount,
                                        resultant_gimbal_angle_deg)
from hrma.analysis.igniter_sizing import size_igniter
from hrma.analysis.regression_analysis import (CHAMBER_LENGTH_FALLBACK_M,
                                               GRAIN_TO_CHAMBER_LENGTH_RATIO,
                                               GrainLengthGovernsInTotalMode,
                                               INTEGRATION_SCHEME,
                                               NonPhysicalRegressionInput,
                                               RegressionAnalyzer)
from hrma.data.propellant_database import HYBRID_REGRESSION_COEFFICIENTS


# ===========================================================================
# Ortak çalışma noktaları — ölçüm betiğiyle BİREBİR aynı
# ===========================================================================
REG_GOVDE = {'fuel_type': 'htpb', 'burn_time': 10.0, 'mdot_ox': 0.7,
             'port_diameter_initial': 0.05, 'grain_length': 0.5}

TORC = dict(igniter_type='torch', chamber_free_volume_m3=0.05,
            main_mass_flow_kg_s=10.0, ignition_window_s=0.20,
            propellant_specific_heat_J_kg_K=2000.0,
            propellant_ignition_temperature_K=700.0,
            initial_temperature_K=293.15,
            torch_heat_release_J_kg=2.0e6)

PIRO = dict(igniter_type='pyrotechnic', chamber_free_volume_m3=0.05,
            main_mass_flow_kg_s=10.0, ignition_window_s=0.20,
            propellant_specific_heat_J_kg_K=2000.0,
            propellant_ignition_temperature_K=700.0,
            initial_temperature_K=293.15,
            chamber_pressure_Pa=70.0e5,
            charge_gas_molecular_weight_g_mol=25.0,
            charge_flame_temperature_K=2473.0,
            charge_condensed_mass_fraction=0.30)

GIM = dict(thrust_N=800000.0, gimbal_angle_deg=6.0, actuator_arm_m=1.0,
           ring_offset_m=0.5, bolt_circle_diameter_m=1.0, bolt_count=12)


def _kapali_cozum_mm(yuk):
    """'ox' kipinde port çapının KAPALI çözümü [mm].

    dr/dt = a (mdot_ox/pi)^n r^(-2n) =>
        r(t) = [ r0^(2n+1) + (2n+1) a (mdot_ox/pi)^n t ]^(1/(2n+1))
    Katsayılar merkezi tablodan okunur (yeni sayı tanımlanmaz).
    """
    a = HYBRID_REGRESSION_COEFFICIENTS[yuk['fuel_type']]['a']
    n = HYBRID_REGRESSION_COEFFICIENTS[yuk['fuel_type']]['n']
    k = 2.0 * n + 1.0
    r0 = yuk['port_diameter_initial'] / 2.0
    return 2000.0 * ((r0 ** k
                      + k * a * (yuk['mdot_ox'] / math.pi) ** n
                      * yuk['burn_time']) ** (1.0 / k))


# ===========================================================================
# P5B4-10 — yakıt akısı yayımlanır
# ===========================================================================
class TestP5B410YakitAkisiYayimlanir:
    """ÖLÇÜLDÜ (``once.json`` P5B4-10; varsayılan kip 'ox', 100 nokta):
    ``total_flux`` ile ``oxidizer_flux`` arasındaki en büyük fark
    0,000e+00 (birebir kopya) ve yakıt kaynaklı TEK alan
    ``fuel_flux_station`` — bir sayı değil, kip adı.
    """

    def test_yakit_akisi_serileri_var_ve_gercek(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(REG_GOVDE))
        for ad in ('fuel_flux', 'fuel_flux_exit', 'fuel_mass_flow'):
            assert ad in d, f'{ad} yayımlanmıyor'
            assert len(d[ad]) == len(d['oxidizer_flux'])
        # 'ox' kipinde akı tabanına giren yakıt akısı SIFIRDIR (F018) ...
        assert all(v == 0.0 for v in d['fuel_flux'])
        # ... ama grain yakıt ÜRETİR: tanı serileri sıfır olamaz.
        assert all(v > 0.0 for v in d['fuel_flux_exit'])
        assert all(v > 0.0 for v in d['fuel_mass_flow'])

    def test_yakit_debisi_taniml_bagintiyla_ortusur(self):
        """mdot_f = rho_f * pi * D_port * L_grain * r_dot (t=0)."""
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(REG_GOVDE))
        rho = HYBRID_REGRESSION_COEFFICIENTS  # yalnız içe aktarım kanıtı
        assert rho is not None
        from hrma.data.propellant_database import HYBRID_FUEL_DENSITY_KG_M3
        beklenen = (HYBRID_FUEL_DENSITY_KG_M3['htpb'] * math.pi
                    * REG_GOVDE['port_diameter_initial']
                    * REG_GOVDE['grain_length']
                    * d['regression_rate'][0] / 1000.0)
        assert abs(d['fuel_mass_flow'][0] - beklenen) < 1e-12

    def test_total_ox_esitligi_gerekcelendirilir(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(REG_GOVDE))
        assert max(abs(a - b) for a, b in
                   zip(d['oxidizer_flux'], d['total_flux'])) == 0.0
        kunye = d.get('flux_series_basis') or ''
        assert 'total_flux = oxidizer_flux + fuel_flux' in kunye
        assert 'fuel_mass_flow' in kunye


# ===========================================================================
# P5B4-11 — gönderilen son çap yutulmaz
# ===========================================================================
class TestP5B411SonCapYutulmaz:
    """ÖLÇÜLDÜ (``once.json`` P5B4-11): 200 mm gönderilince eğri BİT-AYNI
    (D_final 66,261309 mm) ve alan yanıtın hiçbir yerinde geri
    bildirilmiyordu; −1,0 m bile sessizce kabul ediliyordu.
    """

    def test_gonderilen_deger_geri_bildirilir(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(
            dict(REG_GOVDE, port_diameter_final=0.200))
        k = d.get('port_diameter_final_check')
        assert k is not None, 'gönderilen son çap geri bildirilmiyor'
        assert k['submitted_m'] == 0.200
        assert abs(k['computed_m'] - d['port_diameter'][-1] / 1000.0) < 1e-15
        assert k['difference_m'] == pytest.approx(
            0.200 - d['port_diameter'][-1] / 1000.0, rel=1e-12)

    def test_fizik_disi_son_cap_reddedilir(self):
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer().analyze_regression_vs_time(
                dict(REG_GOVDE, port_diameter_final=-1.0))
        assert 'port_diameter_final' in str(ex.value)

    def test_verilmeyince_sayi_uydurulmaz(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(REG_GOVDE))
        assert 'port_diameter_final_check' not in d
        # Eskiden 0,05 m uydurulup "varsayılan uygulandı" diye beyan
        # ediliyordu; hiçbir işe yaramayan sayı artık hiç doğmuyor.
        assert 'port_diameter_final' not in (d.get('defaults_applied') or {})


# ===========================================================================
# P5B4-12 — entegrasyon şeması
# ===========================================================================
class TestP5B412EntegrasyonSemasi:
    """ÖLÇÜLDÜ (``once.json`` P5B4-12): modül 66,261309 mm veriyordu,
    kapalı çözüm 66,239099 mm (+%0,0335); t_b = 60 s'de +%0,186. Kod
    yorumundaki '66,239 mm' iddiası dört kip kombinasyonunun HİÇBİRİNDE
    yeniden üretilmiyordu.
    """

    def test_sema_adiyla_yayimlanir(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(REG_GOVDE))
        assert d['integration_scheme'] == INTEGRATION_SCHEME
        assert d['integration_scheme'] == 'runge_kutta_4'
        assert d['integration_steps'] == len(d['time'])

    def test_ox_kipinde_kapali_cozume_oturur(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(REG_GOVDE))
        tam = _kapali_cozum_mm(REG_GOVDE)
        assert abs(d['port_diameter'][-1] - tam) / tam < 1e-9, (
            f"şema kapalı çözümden ayrıştı: {d['port_diameter'][-1]} != {tam}")

    def test_uzun_yanmada_da_oturur(self):
        yuk = dict(REG_GOVDE, burn_time=60.0)
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(yuk))
        tam = _kapali_cozum_mm(yuk)
        assert abs(d['port_diameter'][-1] - tam) / tam < 1e-9

    def test_euler_hatasi_geri_gelmez(self):
        """Açık Euler bu noktada +%0,0335 sapıyordu; eşik onun ALTINDA."""
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(REG_GOVDE))
        tam = _kapali_cozum_mm(REG_GOVDE)
        assert abs(d['port_diameter'][-1] - tam) / tam < 1e-5


# ===========================================================================
# P5B4-13 — uydurma grain boyu 'total' kipinde eğriyi yönetemez
# ===========================================================================
class TestP5B413UydurmaGrainBoyu:
    """ÖLÇÜLDÜ (``once.json`` P5B4-13): iki alan da yokken 0,3 x 0,8 =
    0,24 m uyduruluyor ve 'total' kipinde r_dot[0] 0,959943 -> 0,972714
    mm/s, D_final 66,261309 -> 66,445215 mm olacak şekilde eğriyi
    ölçekliyordu.
    """

    def _govde(self, **ek):
        y = {k: v for k, v in REG_GOVDE.items() if k != 'grain_length'}
        y.update(ek)
        return y

    def test_total_kipinde_reddedilir(self):
        with pytest.raises(GrainLengthGovernsInTotalMode) as ex:
            RegressionAnalyzer().analyze_regression_vs_time(
                self._govde(flux_mode='total'))
        assert ex.value.missing == ['grain_length']
        assert 'GOVERNS' in str(ex.value)

    def test_ox_kipinde_kalir_ama_beyan_edilir(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(
            self._govde(flux_mode='ox'))
        uygulanan = d['defaults_applied']
        assert uygulanan['chamber_length'] == CHAMBER_LENGTH_FALLBACK_M
        assert uygulanan['grain_length_from_chamber_length'] == (
            CHAMBER_LENGTH_FALLBACK_M * GRAIN_TO_CHAMBER_LENGTH_RATIO)

    def test_kamara_boyu_verilmisse_total_calisir(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(
            self._govde(chamber_length=0.6, flux_mode='total'))
        assert d['inputs_used']['grain_length_m'] == (
            0.6 * GRAIN_TO_CHAMBER_LENGTH_RATIO)

    def test_sabitler_ciplak_yazilmaz(self):
        """TEK KAYNAK: 0,3 ve 0,8 modül sabitlerinden gelir."""
        assert CHAMBER_LENGTH_FALLBACK_M == 0.3
        assert GRAIN_TO_CHAMBER_LENGTH_RATIO == 0.8


# ===========================================================================
# P5B4-14 — torç akı oranı pencereden bağımsızdır
# ===========================================================================
class TestP5B414PencereSadelesir:
    """ÖLÇÜLDÜ (``once.json`` P5B4-14): pencere 0,2 ms'ten 1,0 s'ye
    (5000 kat) taranınca oranın bağıl yayılımı 1,637e-16 — yani sıfır.
    Buna rağmen hem ``validity`` hem ``warnings`` "check the ignition
    window" diyordu.
    """

    def test_oran_gercekten_bagimsiz(self):
        oranlar = [size_igniter(**dict(TORC, ignition_window_s=t))[
            'torch']['flow_fraction_of_main']
            for t in (2e-4, 2e-3, 2e-2, 2e-1, 1.0)]
        yayilim = (max(oranlar) - min(oranlar)) / (sum(oranlar)
                                                   / len(oranlar))
        assert yayilim < 1e-12

    def test_mesajlar_pencereye_yonlendirmez(self):
        r = size_igniter(**dict(TORC, torch_heat_release_J_kg=2.0e4))
        val = [v['message'] for v in r['validity']
               if v['field'].startswith('torch')]
        assert val, 'bant dışı hâl validity üretmedi'
        for m in val:
            assert 'ignition window, the transfer efficiency' not in m, (
                'validity hâlâ pencereyi suçluyor')
        uyari = [w for w in r['warnings'] if 'torch flow fraction' in w]
        assert uyari, 'bant dışı hâl uyarı üretmedi'
        for w in uyari:
            assert 'check the ignition window' not in w

    def test_sadelesme_kunyede_yazili(self):
        r = size_igniter(**dict(TORC, torch_heat_release_J_kg=2.0e4))
        t = r['torch']
        assert t['flow_fraction_independent_of'] == ['ignition_window_s']
        assert 'ignition_window_s' not in t['flow_fraction_governed_by']
        assert 'ALGEBRAICALLY INDEPENDENT' in t['_basis']


# ===========================================================================
# P5B4-15 — şarj gaz sıcaklığı
# ===========================================================================
class TestP5B415SarjGazSicakligi:
    """ÖLÇÜLDÜ (``once.json`` P5B4-15; V_free 0,05 m3, P_c 70 bar,
    frac 0,15, MW 25, X_cond 0,30): T = 2473 K -> 91,189109 g;
    1500 K -> 150,340444 g (1,6487 kat); 1000 K -> 225,510666 g
    (2,4730 kat). Alev sıcaklığı gaz sıcaklığı yerine konuyor,
    kullanılan sayı yayımlanmıyor, beyan yoktu.
    """

    def test_kullanilan_gaz_sicakligi_yayimlanir(self):
        r = size_igniter(**PIRO)
        p = r['pyrotechnic']
        assert p['gas_temperature_K'] == PIRO['charge_flame_temperature_K']
        assert 'charge_flame_temperature_K substituted' in (
            p['gas_temperature_source'])

    def test_ikame_adiyla_ve_yonuyle_beyan_edilir(self):
        r = size_igniter(**PIRO)
        kayit = [v for v in r['validity']
                 if v['field'] == 'pyrotechnic.gas_temperature_K']
        assert kayit, 'ikame beyan edilmiyor'
        m = kayit[0]['message']
        assert 'UPPER bound' in m
        assert 'unsafe' in m

    def test_ayri_knob_hukmu_yonetir(self):
        r = size_igniter(**dict(PIRO, charge_gas_temperature_K=1500.0))
        p = r['pyrotechnic']
        assert p['gas_temperature_K'] == 1500.0
        assert p['gas_temperature_source'] == (
            'user-supplied charge_gas_temperature_K')
        # knob verilince ikame beyanı KONMAZ
        assert not [v for v in r['validity']
                    if v['field'] == 'pyrotechnic.gas_temperature_K']
        # ve şarj gerçekten büyür (1/T ölçeklemesi)
        taban = size_igniter(**PIRO)['pyrotechnic']['charge_mass_kg']
        assert p['charge_mass_kg'] > taban


# ===========================================================================
# P5B4-16 — girdi kapısı TEK KAYNAK ve bool'u reddeder
# ===========================================================================
class TestP5B416BoolSayiDegildir:
    """ÖLÇÜLDÜ (``once.json`` P5B4-16): ``size_igniter(
    main_mass_flow_kg_s=True)`` -> energy_J = 542466,67 J (mdot 1,0 kg/s);
    ``analyze_gimbal_mount(thrust_N=True)`` -> axial_N = 0,9945 N. İki
    yardımcının kaynağı BİREBİR aynıydı ama iki ayrı nesneydi.
    """

    def test_tek_kaynak(self):
        assert (ig._require_positive is gm._require_positive
                is vf._require_positive is require_positive)
        assert require_positive.__module__ == 'hrma.analysis._input_guards'

    def test_igniter_bool_reddi(self):
        with pytest.raises(ValueError) as ex:
            size_igniter(**dict(TORC, main_mass_flow_kg_s=True))
        assert 'boolean' in str(ex.value)

    def test_gimbal_bool_reddi(self):
        with pytest.raises(ValueError) as ex:
            analyze_gimbal_mount(thrust_N=True, gimbal_angle_deg=6.0,
                                 actuator_arm_m=1.0)
        assert 'boolean' in str(ex.value)

    def test_saglikli_sayi_gecer(self):
        assert require_positive(2.5, 'x') == 2.5
        assert require_positive('2.5', 'x') == 2.5


# ===========================================================================
# P5B4-20 — kesirli cıvata sayısı
# ===========================================================================
class TestP5B420KesirliCivataSayisi:
    """ÖLÇÜLDÜ (``once.json`` P5B4-20; F 800 kN, delta 6 deg, h 0,5 m,
    D_bc 1 m): 11,4 -> 11 cıvata ve moment_induced_max_N 13937,128436 ->
    15204,140112 N (**+%9,09**); 12,9 -> 12, uyarı YOK.
    """

    def test_kesirli_reddedilir(self):
        for kesirli in (11.4, 12.9):
            with pytest.raises(ValueError) as ex:
                analyze_gimbal_mount(**dict(GIM, bolt_count=kesirli))
            assert 'whole number' in str(ex.value)
            assert 'NOT truncated' in str(ex.value)

    def test_bool_reddedilir(self):
        with pytest.raises(ValueError) as ex:
            analyze_gimbal_mount(**dict(GIM, bolt_count=True))
        assert 'boolean' in str(ex.value)

    def test_tam_sayi_ve_tam_degerli_dize_gecer(self):
        a = analyze_gimbal_mount(**dict(GIM, bolt_count=12))
        b = analyze_gimbal_mount(**dict(GIM, bolt_count='12'))
        assert a['bolts']['bolt_count'] == b['bolts']['bolt_count'] == 12
        assert (a['bolts']['moment_induced_max_N']
                == b['bolts']['moment_induced_max_N'])

    def test_yardimci_dogrudan(self):
        assert require_whole_number(12.0, 'n') == 12
        with pytest.raises(ValueError):
            require_whole_number(11.4, 'n')


# ===========================================================================
# P5B4-21 — negatif sapma açısı
# ===========================================================================
class TestP5B421NegatifAci:
    """ÖLÇÜLDÜ (``once.json`` P5B4-21): −6, −10,5 ve −46 derecenin ÜÇÜ de
    ValueError; oysa hata metninin KENDİ künyesi donanımı ± ile anlatıyor
    (F-1 ~±6 deg, SSME ±10,5 deg).
    """

    def test_negatif_aci_kabul_edilir(self):
        for a in (-6.0, -10.5, -45.0):
            r = analyze_gimbal_mount(**dict(GIM, gimbal_angle_deg=a))
            assert r['thrust']['gimbal_angle_deg'] == abs(a)
            assert r['thrust']['gimbal_angle_input_deg'] == a

    def test_yukler_isarette_simetrik(self):
        art = analyze_gimbal_mount(**dict(GIM, gimbal_angle_deg=6.0))
        eks = analyze_gimbal_mount(**dict(GIM, gimbal_angle_deg=-6.0))
        assert art['mount_ring'] == eks['mount_ring']
        assert art['bolts'] == eks['bolts']
        assert art['actuator'] == eks['actuator']

    def test_pozitif_govde_bit_ayni_kalir(self):
        r = analyze_gimbal_mount(**dict(GIM, gimbal_angle_deg=6.0))
        assert 'gimbal_angle_input_deg' not in r['thrust']

    def test_bant_buyukluge_uygulanir(self):
        for a in (-46.0, 46.0):
            with pytest.raises(ValueError) as ex:
                analyze_gimbal_mount(**dict(GIM, gimbal_angle_deg=a))
            assert 'DEFLECTION MAGNITUDE' in str(ex.value)


# ===========================================================================
# P5B4-22 — iki eksen bileşkesi
# ===========================================================================
class TestP5B422BileskeBant:
    """ÖLÇÜLDÜ (``once.json`` P5B4-22): pitch = yaw = 45 deg ->
    resultant_angle_deg 59,99999999999999 ve HTTP 200; pitch 40 / yaw 30
    -> 48,439237; tek eksende 46 deg -> HTTP 400.
    """

    def test_bandi_asan_bileske_reddedilir(self):
        for p, y in ((45.0, 45.0), (40.0, 30.0)):
            with pytest.raises(ValueError) as ex:
                analyze_gimbal_mount(**dict(GIM, gimbal_angle_deg=p,
                                            yaw_angle_deg=y))
            assert 'two-axis resultant' in str(ex.value)
            assert 'each axis on its own is inside it' in str(ex.value)

    def test_band_ici_bileske_gecer(self):
        r = analyze_gimbal_mount(**dict(GIM, gimbal_angle_deg=6.0,
                                        yaw_angle_deg=6.0))
        ta = r['two_axis']
        assert ta['resultant_angle_deg'] <= GIMBAL_ANGLE_VALID_DEG[1]
        assert ta['resultant_angle_deg'] == pytest.approx(8.477512185929957)

    def test_pratik_bant_disi_bileske_beyan_edilir(self):
        r = analyze_gimbal_mount(**dict(GIM, gimbal_angle_deg=12.0,
                                        yaw_angle_deg=12.0))
        alanlar = [v['field'] for v in r['validity']]
        assert 'two_axis.resultant_angle_deg' in alanlar

    def test_tek_eksen_ile_ayni_esik(self):
        """Aynı sapma tek eksende reddediliyorsa iki eksende de reddedilir."""
        with pytest.raises(ValueError):
            analyze_gimbal_mount(**dict(GIM, gimbal_angle_deg=46.0))
        assert resultant_gimbal_angle_deg(30.0, 30.0) < (
            GIMBAL_ANGLE_VALID_DEG[1])
        with pytest.raises(ValueError):
            resultant_gimbal_angle_deg(45.0, 45.0)


# ===========================================================================
# P5B4-23 — 'max_tension' negatif taşımaz
# ===========================================================================
class TestP5B423MaxTensionNegatifDegil:
    """ÖLÇÜLDÜ (``once.json`` P5B4-23; aynı çalışma noktası):
    moment_induced_max_N 13937,128436 N, axial_share_per_bolt_N
    66301,459691 N ve max_tension_if_axial_is_compressive_N
    **−52364,331256 N** — 'çekme' adlı alanda negatif sayı; panel bunu
    aynen basıyordu.
    """

    def test_cekme_alani_negatif_olamaz(self):
        b = analyze_gimbal_mount(**GIM)['bolts']
        assert b['max_tension_if_axial_is_compressive_N'] >= 0.0
        assert b['max_tension_if_axial_is_tensile_N'] >= 0.0

    def test_isaretli_net_yuk_kendi_adiyla_yayimlanir(self):
        b = analyze_gimbal_mount(**GIM)['bolts']
        net = b['net_bolt_load_if_axial_is_compressive_N']
        assert net == pytest.approx(b['moment_induced_max_N']
                                    - b['axial_share_per_bolt_N'])
        assert net < 0.0
        assert b['if_axial_is_compressive_verdict'] == 'net_compression'

    def test_net_basi_hali_beyan_edilir(self):
        r = analyze_gimbal_mount(**GIM)
        kayit = [v for v in r['validity']
                 if v['field'] == (
                     'bolts.max_tension_if_axial_is_compressive_N')]
        assert kayit, 'net bası hâli beyan edilmiyor'
        assert 'no bolt sees net tension' in kayit[0]['message']

    def test_net_cekme_halinde_alanlar_ortusur(self):
        """Moment payı eksenel payı aşarsa iki alan AYNI sayıyı taşır."""
        b = analyze_gimbal_mount(**dict(GIM, ring_offset_m=5.0))['bolts']
        assert b['if_axial_is_compressive_verdict'] == 'net_tension'
        assert (b['max_tension_if_axial_is_compressive_N']
                == b['net_bolt_load_if_axial_is_compressive_N'] > 0.0)

    def test_kunye_negatifligi_soyluyor(self):
        b = analyze_gimbal_mount(**GIM)['bolts']
        assert 'never negative' in b['_basis']
        assert 'net_bolt_load_if_axial_is_compressive_N' in b['_basis']
