"""
Termal koruma modülü doğrulama testleri (Dalga 3).

Kapsam:
  1) Ablasyon Seviye 1 (Q* modeli) — el hesabı referanslarıyla
     (ṡ = q/(rho*Q*), NASA SP-8091 sınıfı / Sutton & Biblarz 9th ed. Ch. 8.5)
  2) 1D transient heat-sink explicit FD:
     - yarı-sonsuz cisim analitik çözümüyle karşılaştırma (taşınımlı yüzey
       erfc çözümü, Incropera & DeWitt 6th ed. Eq. 5.63; tolerans %10)
     - enerji korunumu (ayrık şema tam korunumlu olmalı)
     - CFL kararlılığı (Fo*(1+Bi) <= 1/2, Incropera Table 5.3)
     - lumped-capacitance limitinde (Bi << 0.1) üstel çözümle karşılaştırma
     - Fourier doğrulaması: 10 s / 5 mm çelik — iç yüzey ısınır ama denge
       (T_recovery) değerinin ALTINDA kalır
  3) Radyatif denge: el hesabı (tam çözümlü vaka), enerji dengesi artığı,
     malzeme limit kıyası, monotonluk
  4) Kenar durumlar ve sözlük şeması (endpoint kontratı)
  5) v2.6.27 — ablasyon yüzey enerji dengesi (opt-in ikinci yol) ve
     geçerlilik kapısı:
     - eski yol BİREBİR korunuyor mu (üç motorun bağlaması buna dayanıyor)
     - yeni yol ölçülmüş ablasyon mertebesini tutturuyor mu (NASA TM-107041
       sınıfı silika-fenolik ölçüm bandı)
     - kapı: modelin varsayım zarfı dışında sayı üretmek yerine
       NOT_MODELLED diyor mu
"""

import math

import numpy as np
import pytest

from hrma.analysis.thermal_protection import (
    ABLATIVE_MATERIALS,
    BLOWING_GAS_FRACTION_BAND,
    BLOWING_LAMBDA,
    RADIATION_EXTENSION_MATERIALS,
    RECESSION_VALID_MAX_MM_S,
    STEFAN_BOLTZMANN,
    TM107041_TABLE2_ALL_MM_S,
    TM107041_TABLE2_MX2600_MM_S,
    ThermalProtectionAnalyzer,
    _blowing_reduction,
    _solve_blown_surface_balance,
    list_ablative_materials,
)
from hrma.data.materials_db import get_material


@pytest.fixture
def tp():
    return ThermalProtectionAnalyzer()


# =========================================================================
# 1) ABLASYON — Q* MODELİ
# =========================================================================
class TestAblation:

    def test_hand_calc_silica_phenolic(self, tp):
        """El hesabı: ṡ = q/(rho*Q*); kalınlık = ṡ*t*margin.

        q=2 MW/m^2, rho merkezi DB'den, Q*=8 MJ/kg (konservatif uç),
        t=20 s, margin=1.5.
        """
        rho = get_material('ablative')['density']
        q = 2.0e6
        t = 20.0
        out = tp.ablative_thickness(q, burn_time_s=t,
                                    material='silica_phenolic')

        sdot_expected = q / (rho * 8.0e6)             # m/s
        thick_expected = sdot_expected * t * 1.5      # m
        assert out['recession_rate_mm_s'] == pytest.approx(
            sdot_expected * 1e3, rel=1e-12)
        assert out['required_thickness_m'] == pytest.approx(
            thick_expected, rel=1e-12)
        # Sayısal büyüklük mantıklı mı (mm mertebesi)?
        assert 1.0 < out['required_thickness_mm'] < 20.0

    def test_design_margin_parameter(self, tp):
        """Tasarım payı parametresi kalınlığı lineer ölçeklemeli."""
        base = tp.ablative_thickness(1.0e6, burn_time_s=10.0,
                                     design_margin=1.0)
        doubled = tp.ablative_thickness(1.0e6, burn_time_s=10.0,
                                        design_margin=2.0)
        assert doubled['required_thickness_m'] == pytest.approx(
            2.0 * base['required_thickness_m'], rel=1e-12)
        # margin=1 → kalınlık = toplam gerileme
        assert base['required_thickness_m'] == pytest.approx(
            base['total_recession_m'], rel=1e-12)

    def test_conservative_default_is_low_band_edge(self):
        """Varsayılan Q* her malzemede bandın DÜŞÜK (konservatif) ucu."""
        for key, rec in ABLATIVE_MATERIALS.items():
            lo, hi = rec['q_star_band_MJ_kg']
            assert lo < hi
            assert rec['q_star_default_MJ_kg'] == pytest.approx(lo), key

    def test_band_values_match_task_sources(self):
        """Literatür bantları görev/kaynak değerleriyle aynı olmalı."""
        assert ABLATIVE_MATERIALS['silica_phenolic']['q_star_band_MJ_kg'] \
            == (8.0, 12.0)
        assert ABLATIVE_MATERIALS['carbon_phenolic']['q_star_band_MJ_kg'] \
            == (25.0, 30.0)
        assert ABLATIVE_MATERIALS['epdm']['q_star_band_MJ_kg'] == (4.0, 6.0)

    def test_carbon_phenolic_less_recession_than_epdm(self, tp):
        """Q* sırası: karbon-fenolik EPDM'den çok daha az gerilemeli."""
        cp_ = tp.ablative_thickness(3.0e6, burn_time_s=10.0,
                                    material='carbon_phenolic')
        ep = tp.ablative_thickness(3.0e6, burn_time_s=10.0, material='epdm')
        assert cp_['total_recession_mm'] < ep['total_recession_mm']

    def test_time_varying_flux_trapezoid(self, tp):
        """Dizi akı: sabit dizi skaler sonuçla, rampa ortalamayla eşleşir."""
        t = np.linspace(0.0, 10.0, 101)
        q_const = np.full_like(t, 2.0e6)
        out_arr = tp.ablative_thickness(q_const, time_s=t)
        out_scalar = tp.ablative_thickness(2.0e6, burn_time_s=10.0)
        assert out_arr['total_recession_m'] == pytest.approx(
            out_scalar['total_recession_m'], rel=1e-9)

        # Lineer rampa 0→2 MW: ortalama 1 MW ile aynı toplam gerileme
        q_ramp = 2.0e6 * t / 10.0
        out_ramp = tp.ablative_thickness(q_ramp, time_s=t)
        out_mean = tp.ablative_thickness(1.0e6, burn_time_s=10.0)
        assert out_ramp['total_recession_m'] == pytest.approx(
            out_mean['total_recession_m'], rel=1e-9)

    def test_q_star_and_density_override(self, tp):
        """Q* ve yoğunluk override edilebilmeli (el hesabıyla)."""
        out = tp.ablative_thickness(1.0e6, burn_time_s=5.0,
                                    q_star_J_kg=10.0e6,
                                    density_kg_m3=2000.0,
                                    design_margin=1.0)
        expected = 1.0e6 * 5.0 / (2000.0 * 10.0e6)
        assert out['required_thickness_m'] == pytest.approx(expected,
                                                            rel=1e-12)
        assert out['q_star_MJ_kg'] == pytest.approx(10.0)

    def test_model_note_contains_simplified_model(self, tp):
        """Panel 'simplified model' etiketi için model_note zorunlu."""
        out = tp.ablative_thickness(1.0e6, burn_time_s=5.0)
        assert 'simplified model' in out['model_note'].lower()

    def test_density_from_central_db(self, tp):
        """Silika-fenolik yoğunluğu merkezi materials_db'den gelmeli."""
        out = tp.ablative_thickness(1.0e6, burn_time_s=5.0,
                                    material='silica_phenolic')
        assert out['density_kg_m3'] == pytest.approx(
            get_material('ablative')['density'])

    def test_zero_flux_zero_thickness(self, tp):
        out = tp.ablative_thickness(0.0, burn_time_s=10.0)
        assert out['required_thickness_m'] == 0.0
        assert out['recession_rate_mm_s'] == 0.0

    def test_invalid_inputs_raise(self, tp):
        with pytest.raises(ValueError):
            tp.ablative_thickness(-1.0, burn_time_s=10.0)      # negatif akı
        with pytest.raises(ValueError):
            tp.ablative_thickness(1e6, burn_time_s=0.0)        # sıfır süre
        with pytest.raises(ValueError):
            tp.ablative_thickness(1e6, burn_time_s=10.0,
                                  design_margin=0.5)           # pay < 1
        with pytest.raises(ValueError):
            tp.ablative_thickness(1e6, burn_time_s=10.0,
                                  material='unobtainium')      # bilinmeyen
        with pytest.raises(ValueError):
            # dizi akı ama time_s yok
            tp.ablative_thickness([1e6, 2e6], burn_time_s=10.0)


# =========================================================================
# 2) 1D TRANSIENT HEAT-SINK
# =========================================================================

def _semi_infinite_convective(x, t, alpha, k, h, T_i, T_inf):
    """Yarı-sonsuz cisim, taşınımlı yüzey analitik çözümü.

    Kaynak: Incropera & DeWitt 6th ed. Eq. 5.63; Carslaw & Jaeger §2.7.
    (T - Ti)/(Tinf - Ti) = erfc(eta) - exp(h*x/k + h^2*alpha*t/k^2)
                            * erfc(eta + h*sqrt(alpha*t)/k)
    """
    eta = x / (2.0 * math.sqrt(alpha * t))
    beta = h * math.sqrt(alpha * t) / k
    theta = math.erfc(eta) - math.exp(h * x / k + beta * beta) \
        * math.erfc(eta + beta)
    return T_i + theta * (T_inf - T_i)


class TestHeatSink:

    def test_cfl_stability_criterion(self, tp):
        """Fo*(1+Bi) <= 1/2 (Incropera Table 5.3, taşınımlı yüzey)."""
        out = tp.heat_sink_transient(h_gas_W_m2K=2000.0, T_recovery_K=2500.0,
                                     burn_time_s=2.0, wall_thickness_m=0.01,
                                     wall_material='steel')
        assert out['cfl_ok'] is True
        assert out['Fo'] * (1.0 + out['Bi']) <= 0.5 + 1e-12
        # Çözüm fiziksel sınırlar içinde (kararsızlık salınımı yok)
        Tarr = np.array(out['T_profile_K'])
        assert np.all(Tarr <= out['T_recovery_K'] + 1e-9)
        assert np.all(Tarr >= out['T_initial_K'] - 1e-9)

    def test_semi_infinite_erfc_profile(self, tp):
        """FD, yarı-sonsuz analitik erfc profiliyle %10 içinde eşleşmeli.

        Kalın cidar (L=8 cm) + kısa süre (2 s) → arka yüzey etkilenmez,
        yarı-sonsuz varsayımı geçerli (4*sqrt(alpha*t) ≈ 2.1 cm << L).
        """
        mat = get_material('steel')
        alpha = mat['thermal_conductivity'] / (
            mat['density'] * mat['specific_heat'])
        h, Tr, Ti, t_end, L = 2000.0, 2500.0, 300.0, 2.0, 0.08

        out = tp.heat_sink_transient(h_gas_W_m2K=h, T_recovery_K=Tr,
                                     burn_time_s=t_end, wall_thickness_m=L,
                                     wall_material='steel', T_initial_K=Ti,
                                     n_nodes=161)
        x = np.array(out['x_m'])
        T_fd = np.array(out['T_profile_K'])
        k = mat['thermal_conductivity']

        # Yüzey + ısınmanın belirgin olduğu iç noktalar karşılaştırılır
        for xi in [0.0, 0.002, 0.005, 0.008]:
            idx = int(np.argmin(np.abs(x - xi)))
            T_an = _semi_infinite_convective(x[idx], t_end, alpha, k, h,
                                             Ti, Tr)
            rise_an = T_an - Ti
            rise_fd = T_fd[idx] - Ti
            if rise_an > 0.02 * (Tr - Ti):
                # Bağıl tolerans %10 (sıcaklık ARTIŞI üzerinden)
                assert rise_fd == pytest.approx(rise_an, rel=0.10), \
                    f"x={xi} m: FD={rise_fd:.1f} K, analytic={rise_an:.1f} K"
            else:
                # Çok küçük artışlarda mutlak tolerans
                assert abs(rise_fd - rise_an) < 0.02 * (Tr - Ti)

    def test_energy_conservation(self, tp):
        """Depolanan enerji == yüzeyden giren enerji (ayrık şema tam).

        Yarım-hücre sınır düğümlü explicit şema ayrık düzeyde TAM enerji
        korunumludur (iç akı terimleri teleskopik toplanır) → sıkı tolerans.
        """
        out = tp.heat_sink_transient(h_gas_W_m2K=1500.0, T_recovery_K=2000.0,
                                     burn_time_s=3.0, wall_thickness_m=0.008,
                                     wall_material='copper', n_nodes=41)
        assert out['absorbed_energy_J_m2'] > 0.0
        assert out['stored_energy_J_m2'] == pytest.approx(
            out['absorbed_energy_J_m2'], rel=1e-6)

    def test_fourier_10s_5mm_steel_below_equilibrium(self, tp):
        """Görev doğrulaması: 10 s / 5 mm çelik — iç yüzey ısınmalı ama
        denge (T_recovery) değerinin ALTINDA kalmalı."""
        out = tp.heat_sink_transient(h_gas_W_m2K=1000.0, T_recovery_K=2400.0,
                                     burn_time_s=10.0, wall_thickness_m=0.005,
                                     wall_material='steel', T_initial_K=300.0)
        assert out['T_inner_K'] > 600.0           # belirgin ısınma var
        assert out['T_inner_K'] < 2400.0          # denge değerinin altında
        # Lumped tahmin (Bi_L = h*L/k = 0.1): T ≈ Tr - (Tr-Ti)exp(-t/tau)
        mat = get_material('steel')
        tau = mat['density'] * mat['specific_heat'] * 0.005 / 1000.0
        T_lumped = 2400.0 - 2100.0 * math.exp(-10.0 / tau)
        assert out['T_inner_K'] == pytest.approx(T_lumped, rel=0.10)

    def test_outer_face_adiabatic_short_time(self, tp):
        """Kalın cidar + kısa süre → dış yüzey başlangıçta kalmalı."""
        out = tp.heat_sink_transient(h_gas_W_m2K=2000.0, T_recovery_K=2500.0,
                                     burn_time_s=1.0, wall_thickness_m=0.08,
                                     wall_material='steel', T_initial_K=300.0,
                                     n_nodes=81)
        assert out['T_outer_K'] == pytest.approx(300.0, abs=1.0)
        # Profil sıcak yüzeyden dışa doğru monoton azalmalı
        Tarr = np.array(out['T_profile_K'])
        assert np.all(np.diff(Tarr) <= 1e-9)

    def test_lumped_capacitance_aluminum(self, tp):
        """Bi = h*L/k << 0.1 → lumped üstel çözümle %5 içinde eşleşmeli.

        Al 6061: h=1500, L=3 mm → Bi_L = 1500*0.003/167 ≈ 0.027.
        T(t) = Tr - (Tr - Ti)*exp(-t/tau), tau = rho*cp*L/h
        (Incropera & DeWitt Ch. 5.1, lumped capacitance).
        """
        mat = get_material('aluminum_6061')
        h, L, Ti, Tr, t_end = 1500.0, 0.003, 300.0, 3000.0, 1.0
        tau = mat['density'] * mat['specific_heat'] * L / h
        T_expected = Tr - (Tr - Ti) * math.exp(-t_end / tau)

        out = tp.heat_sink_transient(h_gas_W_m2K=h, T_recovery_K=Tr,
                                     burn_time_s=t_end, wall_thickness_m=L,
                                     wall_material='aluminum_6061',
                                     T_initial_K=Ti, n_nodes=31)
        rise_fd = out['T_inner_K'] - Ti
        rise_expected = T_expected - Ti
        assert rise_fd == pytest.approx(rise_expected, rel=0.05)
        # Cidar içi gradyan yarı-kararlı değere yaklaşmalı:
        # dT ≈ q*L/(2k) (parabolik profil, sabit hacimsel ısınma).
        q_now = h * (Tr - out['T_inner_K'])
        dT_expected = q_now * L / (2.0 * mat['thermal_conductivity'])
        dT_fd = out['T_inner_K'] - out['T_outer_K']
        assert dT_fd == pytest.approx(dT_expected, rel=0.2)

    def test_time_to_limit_hand_calc(self, tp):
        """time_to_limit lumped el hesabıyla eşleşmeli (Bi << 0.1).

        t_limit = -tau * ln((Tr - T_limit)/(Tr - Ti));
        Al 6061 limiti materials_db max_service_temp = 477 K.
        """
        mat = get_material('aluminum_6061')
        limit = mat['max_service_temp']
        h, L, Ti, Tr = 1500.0, 0.003, 300.0, 3000.0
        tau = mat['density'] * mat['specific_heat'] * L / h
        t_expected = -tau * math.log((Tr - limit) / (Tr - Ti))

        out = tp.heat_sink_transient(h_gas_W_m2K=h, T_recovery_K=Tr,
                                     burn_time_s=1.0, wall_thickness_m=L,
                                     wall_material='aluminum_6061',
                                     T_initial_K=Ti, n_nodes=31)
        assert out['exceeds_limit'] is True
        assert out['time_to_limit_s'] is not None
        assert out['time_to_limit_s'] == pytest.approx(t_expected, rel=0.15)
        assert out['max_service_temp_K'] == pytest.approx(limit)

    def test_limit_not_reached(self, tp):
        """Zayıf ısı yükünde limit aşılmamalı; time_to_limit None."""
        out = tp.heat_sink_transient(h_gas_W_m2K=50.0, T_recovery_K=800.0,
                                     burn_time_s=2.0, wall_thickness_m=0.01,
                                     wall_material='steel', T_initial_K=300.0)
        assert out['exceeds_limit'] is False
        assert out['time_to_limit_s'] is None
        assert out['margin_to_limit_K'] > 0.0

    def test_h_zero_wall_stays_initial(self, tp):
        """h=0 → ısı girmez, cidar başlangıç sıcaklığında kalır."""
        out = tp.heat_sink_transient(h_gas_W_m2K=0.0, T_recovery_K=2500.0,
                                     burn_time_s=5.0, wall_thickness_m=0.005,
                                     wall_material='steel', T_initial_K=300.0)
        assert out['T_inner_K'] == pytest.approx(300.0, abs=1e-9)
        assert out['absorbed_energy_J_m2'] == pytest.approx(0.0, abs=1e-9)

    def test_material_props_from_central_db(self, tp):
        """k, rho, cp, limit merkezi materials_db kaydıyla aynı olmalı."""
        mat = get_material('steel_4130')
        out = tp.heat_sink_transient(h_gas_W_m2K=1000.0, T_recovery_K=2000.0,
                                     burn_time_s=1.0, wall_thickness_m=0.005,
                                     wall_material='steel_4130')
        assert out['thermal_conductivity_W_mK'] == pytest.approx(
            mat['thermal_conductivity'])
        assert out['density_kg_m3'] == pytest.approx(mat['density'])
        assert out['specific_heat_J_kgK'] == pytest.approx(
            mat['specific_heat'])
        assert out['max_service_temp_K'] == pytest.approx(
            mat['max_service_temp'])

    def test_history_output(self, tp):
        """store_history → iç yüzey sıcaklık geçmişi monoton artmalı."""
        out = tp.heat_sink_transient(h_gas_W_m2K=1000.0, T_recovery_K=2000.0,
                                     burn_time_s=1.0, wall_thickness_m=0.005,
                                     wall_material='steel',
                                     store_history=True)
        hist = out['history']
        assert len(hist['t_s']) == len(hist['T_inner_K']) == out['n_steps'] + 1
        Tw = np.array(hist['T_inner_K'])
        assert np.all(np.diff(Tw) >= -1e-9)   # ısınma monoton

    def test_invalid_inputs_raise(self, tp):
        with pytest.raises(ValueError):
            tp.heat_sink_transient(1000.0, 2000.0, 1.0, 0.0)   # kalınlık 0
        with pytest.raises(ValueError):
            tp.heat_sink_transient(1000.0, 2000.0, -1.0, 0.005)  # süre < 0
        with pytest.raises(ValueError):
            tp.heat_sink_transient(1000.0, 2000.0, 1.0, 0.005,
                                   n_nodes=2)                  # az düğüm
        with pytest.raises(KeyError):
            tp.heat_sink_transient(1000.0, 2000.0, 1.0, 0.005,
                                   wall_material='vibranium')  # bilinmeyen


# =========================================================================
# 3) RADYASYON-SOĞUTMALI DENGE
# =========================================================================
class TestRadiationEquilibrium:

    def test_exact_hand_calc(self, tp):
        """Tam çözümlü el hesabı vakası.

        T_w = 1000 K, eps = 0.8 seçilir → q_rad = eps*sigma*1000^4.
        h = 100 → T_r = 1000 + q_rad/h olarak kurulur; çözücü 1000 K
        bulmak zorundadır.
        """
        eps, h, Tw_true = 0.8, 100.0, 1000.0
        q_rad = eps * STEFAN_BOLTZMANN * Tw_true ** 4
        Tr = Tw_true + q_rad / h
        out = tp.radiation_equilibrium(h_gas_W_m2K=h, T_recovery_K=Tr,
                                       emissivity=eps)
        assert out['T_wall_eq_K'] == pytest.approx(Tw_true, abs=0.5)

    def test_energy_balance_residual(self, tp):
        """Çözümde q_conv == q_rad (enerji dengesi) sağlanmalı."""
        out = tp.radiation_equilibrium(h_gas_W_m2K=300.0, T_recovery_K=2800.0,
                                       emissivity=0.85)
        Tw = out['T_wall_eq_K']
        q_conv = 300.0 * (2800.0 - Tw)
        q_rad = 0.85 * STEFAN_BOLTZMANN * Tw ** 4
        assert q_conv == pytest.approx(q_rad, rel=1e-4)
        assert out['q_conv_W_m2'] == pytest.approx(q_conv, rel=1e-6)
        # Denge sıcaklığı fiziksel aralıkta
        assert 0.0 < Tw < 2800.0

    def test_c103_within_limit_moderate_load(self, tp):
        """Orta yük: C-103 (1640 K limit) sınır içinde kalmalı."""
        out = tp.radiation_equilibrium(h_gas_W_m2K=150.0, T_recovery_K=2000.0,
                                       material='niobium_c103')
        assert out['service_limit_K'] == pytest.approx(1640.0)
        assert out['T_wall_eq_K'] < 1640.0
        assert out['within_limit'] is True
        assert out['margin_K'] > 0.0

    def test_c103_exceeds_limit_high_load(self, tp):
        """Yüksek yük: C-103 limiti aşılmalı, within_limit False."""
        out = tp.radiation_equilibrium(h_gas_W_m2K=600.0, T_recovery_K=3400.0,
                                       material='niobium_c103')
        assert out['T_wall_eq_K'] > 1640.0
        assert out['within_limit'] is False
        assert out['margin_K'] < 0.0

    def test_ss316_limit_from_central_db(self, tp):
        """Merkezi DB malzemesi: limit allowable_temperature'dan gelmeli
        (ss_316 → 1073 K ≈ görevdeki '316 ~1070 K')."""
        mat = get_material('ss_316')
        out = tp.radiation_equilibrium(h_gas_W_m2K=200.0, T_recovery_K=2500.0,
                                       material='ss_316')
        assert out['service_limit_K'] == pytest.approx(
            mat['allowable_temperature'])
        assert out['emissivity'] == pytest.approx(mat['emissivity'])

    def test_carbon_carbon_higher_limit_than_c103(self):
        """Kaynaklı limit sırası: C-C (~1920 K) > C-103 (~1640 K)."""
        cc = RADIATION_EXTENSION_MATERIALS['carbon_carbon']
        nb = RADIATION_EXTENSION_MATERIALS['niobium_c103']
        assert cc['service_limit_K'] > nb['service_limit_K']
        assert nb['service_limit_K'] == pytest.approx(1640.0)
        assert cc['service_limit_K'] >= 1920.0

    def test_higher_emissivity_lower_wall_temp(self, tp):
        """Monotonluk: yayıcılık artarsa denge sıcaklığı düşmeli."""
        low = tp.radiation_equilibrium(h_gas_W_m2K=250.0, T_recovery_K=2600.0,
                                       emissivity=0.4)
        high = tp.radiation_equilibrium(h_gas_W_m2K=250.0,
                                        T_recovery_K=2600.0, emissivity=0.9)
        assert high['T_wall_eq_K'] < low['T_wall_eq_K']

    def test_invalid_inputs_raise(self, tp):
        with pytest.raises(ValueError):
            tp.radiation_equilibrium(0.0, 2000.0, emissivity=0.8)  # h<=0
        with pytest.raises(ValueError):
            tp.radiation_equilibrium(100.0, 2000.0, emissivity=1.5)
        with pytest.raises(ValueError):
            tp.radiation_equilibrium(100.0, 2000.0, emissivity=0.0)
        with pytest.raises(ValueError):
            # Ne malzeme ne yayıcılık verilmiş
            tp.radiation_equilibrium(100.0, 2000.0)


# =========================================================================
# 4) KONTRAT / ŞEMA (endpoint için)
# =========================================================================
class TestContract:

    def test_ablative_result_schema(self, tp):
        out = tp.ablative_thickness(1.0e6, burn_time_s=10.0)
        for key in ('material', 'material_name', 'recession_rate_mm_s',
                    'total_recession_mm', 'required_thickness_mm',
                    'required_thickness_m', 'q_star_MJ_kg',
                    'q_star_band_MJ_kg', 'density_kg_m3', 'design_margin',
                    'model_note', 'source',
                    # v2.6.27 — akı tabanı ve geçerlilik hükmü ESKİ yolda da
                    # yayımlanmak ZORUNDA: panel/endpoint hangi fizikle
                    # hesaplandığını okuyabilmeli.
                    'flux_basis', 'recession_regime', 'model_valid',
                    'validity_note', 'thickness_status',
                    # v2.6.27 blokaj denetimi — çözülmüş psi türetimiyle
                    # birlikte yayımlanır ('blowing_blockage_band' alanı
                    # sözleşmeden KALKTI, geri gelmemeli).
                    'blowing_blockage', 'b_prime', 'blowing_lambda',
                    'blowing_gas_fraction', 'blockage_basis',
                    'blockage_iterations', 'gas_cp_J_kgK'):
            assert key in out, key
        assert 'blowing_blockage_band' not in out, (
            'sabit blokaj bandı alanı sözleşmeye geri gelmiş')

    def test_heat_sink_result_schema(self, tp):
        out = tp.heat_sink_transient(1000.0, 2000.0, 1.0, 0.005)
        for key in ('x_m', 'T_profile_K', 'T_inner_K', 'T_outer_K',
                    'max_service_temp_K', 'exceeds_limit', 'time_to_limit_s',
                    'absorbed_energy_J_m2', 'stored_energy_J_m2', 'dt_s',
                    'Fo', 'Bi', 'cfl_ok', 'model_note'):
            assert key in out, key
        assert len(out['x_m']) == len(out['T_profile_K']) == out['n_nodes']

    def test_radiation_result_schema(self, tp):
        out = tp.radiation_equilibrium(200.0, 2500.0, emissivity=0.8)
        for key in ('T_wall_eq_K', 'q_conv_W_m2', 'q_rad_W_m2', 'emissivity',
                    'service_limit_K', 'within_limit', 'margin_K',
                    'model_note'):
            assert key in out, key

    def test_analyze_dispatcher(self, tp):
        """Endpoint dağıtıcısı üç modu da çağırabilmeli."""
        a = tp.analyze('ablative', q_net_W_m2=1e6, burn_time_s=5.0)
        assert 'required_thickness_mm' in a
        h = tp.analyze('heat_sink', h_gas_W_m2K=1000.0, T_recovery_K=2000.0,
                       burn_time_s=1.0, wall_thickness_m=0.005)
        assert 'T_inner_K' in h
        r = tp.analyze('radiation_equilibrium', h_gas_W_m2K=200.0,
                       T_recovery_K=2500.0, emissivity=0.8)
        assert 'T_wall_eq_K' in r
        with pytest.raises(ValueError):
            tp.analyze('warp_drive')

    def test_list_ablative_materials_is_copy(self):
        """Tablo kopyası döndürülmeli (merkezi tabloyu mutasyondan korur)."""
        view = list_ablative_materials()
        view['silica_phenolic']['q_star_default_MJ_kg'] = 999.0
        assert ABLATIVE_MATERIALS['silica_phenolic'][
            'q_star_default_MJ_kg'] == pytest.approx(8.0)


# =========================================================================
# 5) v2.6.27 — YÜZEY ENERJİ DENGESİ (opt-in) + GEÇERLİLİK KAPISI
# =========================================================================
# Teşhis: Q* bağıntısına SOĞUK-CİDAR Bartz akısı besleniyordu, yüzeyin
# yeniden ışıması ve piroliz gazı üfleme blokajı yoktu, geometrik denetim
# yoktu. Düzeltme İKİ YOLLUDUR (bkz. ablative_thickness docstring):
#   ESKİ YOL  (h_gas/T_recovery verilmez) → sayısal çıktı BİREBİR korunur;
#             üç motorun (sıvı/hibrit/katı) bugünkü bağlaması buna dayanır.
#   YENİ YOL  (h_gas + T_recovery verilir) → net akı burada çözülür ve
#             geçerlilik kapısı BAĞLAYICIDIR.
# Aşağıdaki testler bu iki yolun ikisini de kilitler.
# =========================================================================

# NASA TM-107041 Tablo 2 ölçüm bandları artık MODÜLDEN import edilir
# (TM107041_TABLE2_ALL_MM_S / TM107041_TABLE2_MX2600_MM_S) — tek tanım
# noktası. Buradaki eski yerel sabit TM107041_RECESSION_BAND_MM_S=(0.0045,
# 0.082) SİLİNDİ: 0.082 üst ucu raporun Tablo 2 sütunundaki x10^-2
# çarpanının atlanmasıyla oluşmuş 10 KAT yanlış bir okumaydı (gerçek üst uç
# 0.00822 mm/s = 0.323 mil/s; tüm örnekler bandı 0.00017-0.0601 mm/s).

# Mertebe kilidi toleransı: ölçülen bandın (tüm örnekler) ÜST ucunun kaç
# katına kadar kabul edilir. ESKİ değer 5.0'dı ve 10x şişik banda göre
# kurulmuştu (fiilî tavan 0.41 mm/s). Band düzeltilince kilit yeniden
# ÖLÇÜLDÜ: raporun gerçek koşulunda (aşağıdaki test) model 0.0779 mm/s
# veriyor = bandın üst ucunun 1.30 katı. 2.0, ölçülen 1.30'a pay bırakan
# ama eski kilidin 3.4 katı sıkı bir mertebe kilididir — nokta doğrulaması
# hâlâ DEĞİLDİR (T_c bir varsayımdır, bkz. test docstring'i).
TM107041_ORDER_TOLERANCE = 2.0

# ---------------------------------------------------------------------------
# T3-1 (parti 31) — MERTEBE KİLİDİ İKİ YÖNLÜ OLMALI
#
# Ölçülen kusur: yukarıdaki kilit yalnız YUKARI bakıyordu
# (rate <= band_hi * 2.0) ve alt uç ayrı, çok gevşek bir sabite
# (MX2600 tabanı 0.00452) bağlıydı. Bu yüzden TARİHÎ KUSURUN KENDİSİ —
# Tablo 2 sütunundaki x10^-2 çarpanının unutulması, yani bandın TAMAMININ
# 10 kat yukarı kayması — geri geldiğinde dosya 48/48 YEŞİL kalıyordu:
#   band x10 -> tavan 0.0601*10*2 = 1.202 (0.0779 geçer)
#              taban 0.00452*10   = 0.0452 (0.0779 yine geçer)
# Ölçüldü, sayı budur.
#
# İki yönlü kilit iki ayaklıdır:
#   (1) SABİTLERİN KENDİSİ bir ONDALIK KUŞAKTA kilitlenir (aşağıdaki
#       kuşaklar birincil kaynağın okunmuş değerlerini içerir, x10 ya da
#       x0.1 kayma kuşağın dışına çıkar).
#   (2) MODELİN SAYISI ile bandın üst ucu arasındaki ORAN iki yönlü
#       kilitlenir. Oran, bandın uniform kaymasına DUYARLIDIR: ölçülen
#       0.0779/0.0601 = 1.296; band x10 kayarsa oran 0.1296'ya düşer ve
#       aynı TM107041_ORDER_TOLERANCE eşiği aşağıdan kırılır.
# ---------------------------------------------------------------------------

#: Birincil kaynağın (NASA TM-107041 Tablo 2, sütun çarpanı x10^-2) okunmuş
#: değerlerini içeren ondalık kuşaklar [mm/s]. Ölçülen değerler:
#: tüm örnekler 0.00017-0.0601; yüksek yoğunluklu uçuş sınıfı 0.00452-0.00822.
TM107041_DECADE_ALL_MM_S = (1e-4, 1e-1)
TM107041_DECADE_MX2600_MM_S = (1e-3, 1e-2)


def test_tm107041_bandlari_ondalik_kusakta():
    """Tarihî 10x okuma hatası GERİ GELİRSE bu bekçi kırılır (T3-1).

    Bant sabitleri modülde tek tanım noktasındadır; buradaki kilit onların
    BÜYÜKLÜK MERTEBESİNİ birincil kaynağın okumasına çapalar. x10 kayma
    (çarpanın unutulması) da x0.1 kayma (iki kez uygulanması) da kuşağın
    dışına çıkar.
    """
    kusaklar = (
        ('TM107041_TABLE2_ALL_MM_S', TM107041_TABLE2_ALL_MM_S,
         TM107041_DECADE_ALL_MM_S),
        ('TM107041_TABLE2_MX2600_MM_S', TM107041_TABLE2_MX2600_MM_S,
         TM107041_DECADE_MX2600_MM_S),
    )
    for ad, bant, (k_lo, k_hi) in kusaklar:
        for uc in bant:
            assert k_lo <= uc <= k_hi, (
                f'{ad} ucu {uc} mm/s, birincil kaynağın ondalık kuşağı '
                f'[{k_lo}, {k_hi}] dışında — Tablo 2 sütunundaki x10^-2 '
                'çarpanı atlanmış (ya da iki kez uygulanmış) olabilir')
    # İç tutarlılık: uçuş sınıfı bandı tüm-örnekler bandının İÇİNDE.
    assert (TM107041_TABLE2_ALL_MM_S[0] <= TM107041_TABLE2_MX2600_MM_S[0]
            <= TM107041_TABLE2_MX2600_MM_S[1]
            <= TM107041_TABLE2_ALL_MM_S[1]), (
        'MX2600 bandı tüm-örnekler bandının içinde değil — bantlardan biri '
        'kaymış olabilir')


class TestAblationSurfaceEnergyBalance:

    # ------------------------------------------------------------------
    # (a) GERİ UYUMLULUK — eski yol kılı kıpırdamamalı
    # ------------------------------------------------------------------
    def test_legacy_path_is_bit_identical(self, tp):
        """Eski imza → eski sayı (278.773 mm sınıfı), BİLİNEREK korunuyor.

        Bu, "doğru sonuç" testi DEĞİLDİR: 278 mm'lik bir boğaz astarı
        fiziksel değildir (v2.6.27 teşhisinin konusu tam da budur). Bu test
        eski yolun DEĞİŞMEDİĞİNİ kilitler, çünkü üç motorun termal koruma
        bağlaması ve onların beyan testleri bugün bu sayıyı yayımlıyor.
        Yeni yola geçiş motor motor yapılacaktır; o gün bu test, yerini
        yeni yolun beklentisine bırakmalıdır.

        Akı, teşhiste ölçülen gerilemeden geri çözülür (uydurma sabit
        değil): ṡ = q/(rho*Q*)  →  q = ṡ*rho*Q*.
        """
        rho = get_material('ablative')['density']          # 1400 kg/m^3
        q_star = 8.0e6                                     # konservatif uç
        sdot_measured_m_s = 0.6195e-3                      # teşhis ölçümü
        q = sdot_measured_m_s * rho * q_star               # ~6.94 MW/m^2
        burn_s = 300.0

        out = tp.ablative_thickness(q, burn_time_s=burn_s,
                                    material='silica_phenolic')

        assert out['recession_rate_mm_s'] == pytest.approx(0.6195, abs=1e-4)
        assert out['required_thickness_mm'] == pytest.approx(278.773, abs=0.1)
        assert out['flux_basis'] == 'caller_supplied_no_energy_balance'
        assert out['recession_regime'] == 'caller_supplied_flux'
        # Enerji dengesi alanları eski yolda UYDURULMAZ.
        assert out['T_surface_K'] is None
        assert out['q_conv_blocked_W_m2'] is None
        assert out['q_reradiated_W_m2'] is None
        assert out['q_caller_W_m2'] == pytest.approx(q, rel=1e-12)

    def test_legacy_path_keeps_sized_status_even_when_gate_trips(self, tp):
        """GEÇİCİ İKİLİK: eski yolda kapı statü DÜŞÜRMEZ, bilgi verir.

        Motor bağlama testleri (sıvı/hibrit/katı beyan testleri) bugün
        thickness_status='sized' ve sayısal bir kalınlık bekliyor. Kapı bu
        yolda yalnız model_valid/validity_note ile konuşur. Bu ikilik
        BİLİNÇLİDİR ve motorların tamamı yeni yola geçtiğinde kalkmalıdır —
        bu test o günü fark etmemizi sağlar (kalktığında kırılır).
        """
        rho = get_material('ablative')['density']
        q = 0.6195e-3 * rho * 8.0e6
        out = tp.ablative_thickness(q, burn_time_s=300.0,
                                    station_radius_m=0.0496)

        assert out['recession_rate_mm_s'] > RECESSION_VALID_MAX_MM_S
        assert out['model_valid'] is False
        assert out['validity_note'] is not None
        assert 'FOR INFORMATION ONLY' in out['validity_note']
        # ... ama kalınlık HÂLÂ yayımlanıyor:
        assert out['thickness_status'] == 'sized'
        assert out['required_thickness_mm'] == pytest.approx(278.773, abs=0.1)

    # ------------------------------------------------------------------
    # (b) YENİ YOL — ölçülmüş ablasyon mertebesi
    # ------------------------------------------------------------------
    def test_new_path_matches_measured_recession_order(self, tp):
        """NASA TM-107041 GERÇEK koşulunda gerileme ÖLÇÜLEN mertebede.

        DEĞİŞİKLİK GEREKÇESİ (v2.6.27 blokaj denetimi): testin eski hâli
        (a) 0.082 mm/s bandını kullanıyordu — raporun Tablo 2'sinin x10^-2
        çarpanı atlanmış 10 KAT yanlış okumasıydı (gerçek üst uç 0.00822;
        tüm örnekler 0.00017-0.0601); (b) boğazı 50 mm ve T_c'yi 3000 K
        VARSAYIYORDU — rapor okununca ikisi de rapordan geldi: boğaz çapı
        25.4 mm, Pc = 11.38 bar (165 psia), GH2/GOX, birikimli süre 164 s.

        Girdi türetimi (belgeli, uydurma yok):
          - Boğaz 25.4 mm, Pc 11.38 bar, 164 s: raporun kendi test koşulu.
          - T_c = 2450 K: raporun boğaz gaz sıcaklığı ölçümlerinden
            (tüm koşuların ortalaması ~2456 K; tekil değer ~2386 K) —
            rapor T_c'yi ayrıca vermez, bu hâlâ bir VARSAYIMDIR ama artık
            ölçüme dayalıdır. Bu yüzden hüküm nokta doğrulaması değil
            MERTEBE KİLİDİDİR.
          - h_g, T_recovery ve c_p EL İLE yazılmaz: deponun kendi Bartz
            zinciri (HeatTransferAnalyzer) hesaplar — motorların bağlamada
            izlediği zincirin aynısı. c_p artık geçirilir ki blokaj B'
            üzerinden ÖZ-TUTARLI çözülsün (yeni sözleşme).

        Hüküm (kilit yazılırken ÖLÇÜLDÜ: 0.0779 mm/s = üst ucun 1.30 katı):
        gerileme, tüm-örnekler bandının üst ucunun (0.0601 mm/s) 2 katını
        AŞMAZ ve uçuş sınıfı bandın alt ucunun (0.00452) ALTINA İNMEZ —
        alt kilit, eski sabit-0.5 blokaj kusuru geri gelirse (bu noktada
        q_net'i negatife çevirip 0 mm/s verirdi) yakalar.
        """
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer

        motor = {
            'chamber_pressure': 11.38,      # bar — 165 psia, raporun koşulu
            'chamber_temperature': 2450.0,  # K  — rapor ölçüm ort. ~2456 K
            'throat_diameter': 0.0254,      # m  — raporun boğaz çapı
            'burn_time': 164.0,             # s  — raporun birikimli süresi
            'mdot_total': 0.3,              # kg/s (h_g'ye girmez)
            # Kamara geometrisi ARTIK ZORUNLU (parti 31, ısı zinciri girdi
            # kapısı: chamber_diameter/chamber_length varsayılanları
            # kaldırıldı). Aşağıdaki 0,1 m / 0,5 m, kaldırılan örtük
            # varsayılanların TAM kendisidir — bu testin ölçüm çapası
            # (h_g = 4637 W/m²K) böylece bit-aynı kalır.
            # DİKKAT: bunlar TM-107041 test motorunun kamara ölçüleri DEĞİL;
            # rapor bu testte kullanılmıyor. Boğaz Bartz zinciri bu ikisine
            # DUYARSIZ — ölçüldü (D = 0,05 / 0,0762 / 0,1 / 0,2 m taramasında
            # h_g, T_aw ve c_p 6 anlamlı hanede AYNI; boğaz akısı yalnız
            # %1,7 oynadı, cidar sıcaklığı çözümü üzerinden).
            'chamber_diameter': 0.1,        # m — eski örtük varsayılan
            'chamber_length': 0.5,          # m — eski örtük varsayılan
        }
        ht = HeatTransferAnalyzer().analyze_heat_transfer(
            motor, material='ablative', wall_thickness=0.010)
        h_g = float(ht['heat_transfer_coefficients']['gas_side'])
        gas_cp = float(ht['heat_transfer_coefficients']['gas_cp'])
        T_aw = float(ht['gas_side_analysis']['adiabatic_wall_temperature'])
        q_bartz = float(ht['gas_side_analysis']['throat_heat_flux'])

        # Zincir sağlığı: Bartz mertebesi bu çalışma noktasında beklenen
        # aralıkta mı (kilit kırılırsa suçlu kim, ayırt edilebilsin).
        # Ölçülen: h_g = 4637 W/m2K, T_aw = 2436 K, cp = 2079 J/kgK.
        assert 1.0e3 < h_g < 1.0e4, h_g
        assert 2200.0 < T_aw < 2450.0, T_aw
        assert 1.0e3 < gas_cp < 4.0e3, gas_cp

        out = tp.ablative_thickness(
            q_net_W_m2=q_bartz,
            burn_time_s=motor['burn_time'],
            material='silica_phenolic',
            h_gas_W_m2K=h_g,
            T_recovery_K=T_aw,
            gas_cp_J_kgK=gas_cp)

        assert out['flux_basis'] == 'surface_energy_balance'
        assert out['recession_regime'] == 'steady_ablation'
        assert out['model_valid'] is True
        assert out['thickness_status'] == 'sized'

        band_hi = TM107041_TABLE2_ALL_MM_S[1]
        oran = out['recession_rate_mm_s'] / band_hi
        # İKİ YÖNLÜ mertebe kilidi (T3-1): ölçülen oran 1.296. Aynı tolerans
        # hem yukarı hem aşağı uygulanır; bandın 10x kayması oranı 0.1296'ya
        # düşürür ve alt eşik kırılır (tek yönlü eski kilit bunu göremiyordu).
        assert oran <= TM107041_ORDER_TOLERANCE, (
            f"new path recession {out['recession_rate_mm_s']:.4f} mm/s is more "
            f"than {TM107041_ORDER_TOLERANCE:g}x the measured band top "
            f"{band_hi} mm/s")
        assert oran >= 1.0 / TM107041_ORDER_TOLERANCE, (
            f"new path recession {out['recession_rate_mm_s']:.4f} mm/s is "
            f"less than 1/{TM107041_ORDER_TOLERANCE:g} of the measured band "
            f"top {band_hi} mm/s (ölçülen oran 1.296; bu kadar düşmesi ya "
            f"fiziğin ya da BANDIN kaydığını söyler — TM-107041 Tablo 2 "
            f"x10^-2 çarpanı hatası tam olarak böyle görünür)")
        # Alt mertebe kilidi: uçuş sınıfı (MX2600) bandın alt ucu. Sabit
        # psi=0.5 kusuru bu noktada no_net_heating/0 mm/s verirdi — ölçülen
        # 0.0779 mm/s bu alt ucun 17 katı, kırılırsa fizik değişmiş demektir.
        assert out['recession_rate_mm_s'] >= TM107041_TABLE2_MX2600_MM_S[0], (
            f"new path recession {out['recession_rate_mm_s']:.5f} mm/s fell "
            f"below the flight-class measured band floor "
            f"{TM107041_TABLE2_MX2600_MM_S[0]} mm/s")

        # Yeni yol, aynı Bartz akısını HAM besleyen eski yoldan DAHA AZ
        # gerileme verir: üfleme blokajı + yeniden ışıma net akıyı düşürür.
        # (Ölçülen: 0.0779 mm/s yeni yol, 0.2104 mm/s eski yol.)
        legacy = tp.ablative_thickness(q_net_W_m2=q_bartz,
                                       burn_time_s=motor['burn_time'],
                                       material='silica_phenolic')
        assert out['recession_rate_mm_s'] < legacy['recession_rate_mm_s']

    def test_new_path_energy_balance_is_self_consistent(self, tp):
        """Dönen değerler yüzey enerji dengesi denklemini SAĞLAMALI.

        DEĞİŞİKLİK GEREKÇESİ: testin eski hâli sabit blokaj katsayısıyla
        (rec['blowing_blockage'] = 0.5) el hesabıydı. Sabit 0.5 yanlış
        rejimin katsayısıydı (psi=0.5 ⇒ B'≈1.6-2.5 atmosferik giriş; roket
        noktalarında B'≈0.02-0.25 ⇒ psi 0.90-1.0) ve v2.6.27'de KALDIRILDI;
        'blowing_blockage_band' alanı ve BLOWING_BLOCKAGE_BAND sabiti de
        sözleşmeden çıktı. Blokaj artık ÇÖZÜLDÜĞÜ için el hesabı yerine
        öz-tutarlılık denetlenir:

            sdot == (psi*h_g*(T_aw - T_s) - eps*sigma*T_s^4) / (rho*Q*)
            psi  == _blowing_reduction(b_prime)
            b'   == f_gas * sdot * rho * c_p / h_g
        """
        h_g, T_r, cp = 4000.0, 3300.0, 2000.0
        out = tp.ablative_thickness(1.0e6, burn_time_s=20.0,
                                    material='silica_phenolic',
                                    h_gas_W_m2K=h_g, T_recovery_K=T_r,
                                    gas_cp_J_kgK=cp)
        assert out['recession_regime'] == 'steady_ablation'
        psi = out['blowing_blockage']
        b_prime = out['b_prime']
        T_s = out['T_surface_K']
        eps = out['emissivity']
        rho = out['density_kg_m3']
        rho_qstar = rho * out['q_star_MJ_kg'] * 1e6
        sdot_m_s = out['recession_rate_mm_s'] / 1e3

        # (1) Enerji dengesi: sdot = q_net / (rho*Q*), 1e-6 bağıl hassasiyet.
        q_conv = psi * h_g * (T_r - T_s)
        q_rad = eps * STEFAN_BOLTZMANN * T_s ** 4
        assert sdot_m_s == pytest.approx((q_conv - q_rad) / rho_qstar,
                                         rel=1e-6)
        # (2) psi, yayımlanan B'nin Aerotherm indirgemesi olmalı.
        assert psi == pytest.approx(_blowing_reduction(b_prime), rel=1e-6)
        # (3) B' tanımı: f_gas * sdot * rho * c_p / h_g.
        f_gas = out['blowing_gas_fraction']
        assert b_prime == pytest.approx(f_gas * sdot_m_s * rho * cp / h_g,
                                        rel=1e-6)
        # (4) Yayımlanan akı bileşenleri aynı denklemin parçaları olmalı.
        assert out['q_conv_blocked_W_m2'] == pytest.approx(q_conv, rel=1e-9)
        assert out['q_reradiated_W_m2'] == pytest.approx(q_rad, rel=1e-9)
        assert out['q_mean_W_m2'] == pytest.approx(q_conv - q_rad, rel=1e-6)
        # Çağıranın akısı yeni yolda KULLANILMAZ ama raporlanır.
        assert out['q_caller_W_m2'] == pytest.approx(1.0e6)
        assert out['emissivity'] == pytest.approx(
            get_material('ablative')['emissivity'])
        assert out['blowing_lambda'] == pytest.approx(BLOWING_LAMBDA)
        assert out['blockage_iterations'] > 0

    def test_psi_solved_only_when_gas_cp_supplied(self, tp):
        """gas_cp verilince psi ÇÖZÜLÜR (0<psi<1, B'>0); verilmezse psi=1.

        Yeni sözleşme (v2.6.27 blokaj denetimi): B' tanımı c_p ister;
        c_p verilmezse katsayı UYDURULMAZ — psi=1 (blokajsız, konservatif)
        alınır ve blockage_basis bunu 'NOT solved' diye beyan eder.
        """
        # h_g = 3500: iki hâl de hız tavanının (0.35 mm/s) ALTINDA kalsın
        # diye ölçülerek seçildi (çözülmüş 0.292, blokajsız 0.310 mm/s) —
        # kalınlık karşılaştırması ancak ikisi de 'sized' iken anlamlı.
        kwargs = dict(burn_time_s=20.0, material='silica_phenolic',
                      h_gas_W_m2K=3500.0, T_recovery_K=3300.0)
        solved = tp.ablative_thickness(1.0e6, gas_cp_J_kgK=2000.0, **kwargs)
        assert solved['thickness_status'] == 'sized'
        assert 0.0 < solved['blowing_blockage'] < 1.0
        assert solved['b_prime'] > 0.0
        assert 'SOLVED' in solved['blockage_basis']
        assert solved['gas_cp_J_kgK'] == pytest.approx(2000.0)

        unsolved = tp.ablative_thickness(1.0e6, **kwargs)
        assert unsolved['thickness_status'] == 'sized'
        assert unsolved['blowing_blockage'] == pytest.approx(1.0)
        assert unsolved['b_prime'] is None
        assert 'NOT solved' in unsolved['blockage_basis']
        assert unsolved['gas_cp_J_kgK'] is None
        # psi=1 konservatif YÖN demektir: blokajsız akı daha büyük, gerileme
        # ve kalınlık çözülmüş hâlden AZ OLAMAZ.
        assert (unsolved['recession_rate_mm_s']
                >= solved['recession_rate_mm_s'])
        assert (unsolved['required_thickness_mm']
                >= solved['required_thickness_mm'])

    def test_physics_direction_h_gas_and_emissivity(self, tp):
        """Fizik yönü: h_g artınca sdot AZALMAZ; eps=0 sınırı eps=0.9'dan az
        gerileme veremez (yeniden ışıma tek başına soğutucu terimdir)."""
        prev = -1.0
        for h in (1000.0, 2000.0, 4000.0, 8000.0):
            out = tp.ablative_thickness(1.0e6, burn_time_s=20.0,
                                        h_gas_W_m2K=h, T_recovery_K=3300.0,
                                        gas_cp_J_kgK=2000.0)
            assert out['recession_rate_mm_s'] >= prev, (
                f'h_g={h}: sdot düştü')
            prev = out['recession_rate_mm_s']

        # eps yönü çözücü seviyesinde denetlenir (ablative_thickness yüzey
        # yayıcılığını malzeme kaydından okur, parametreleştirmez).
        rho = get_material('ablative')['density']
        kw = dict(h_gas_W_m2K=4000.0, T_recovery_K=3300.0,
                  T_surface_K=2050.0, rho_qstar=rho * 8.0e6,
                  density_kg_m3=rho, gas_cp_J_kgK=2000.0, gas_fraction=0.5)
        s_eps0 = _solve_blown_surface_balance(emissivity=0.0, **kw)
        s_eps9 = _solve_blown_surface_balance(emissivity=0.9, **kw)
        assert s_eps0['recession_rate_m_s'] >= s_eps9['recession_rate_m_s']
        assert s_eps0['q_reradiated_W_m2'] == pytest.approx(0.0)

    # ------------------------------------------------------------------
    # (c) KAPI + q_net <= 0 dalı + flux_basis her iki yolda
    # ------------------------------------------------------------------
    def test_gate_marks_not_modelled_on_extreme_input(self, tp):
        """Uç girdi: kapı sayı üretmek yerine NOT_MODELLED demeli."""
        # Çok yüksek h_g: gerileme tavanın (0.35 mm/s) çok üstüne çıkar.
        out = tp.ablative_thickness(1.0e6, burn_time_s=100.0,
                                    h_gas_W_m2K=5.0e4, T_recovery_K=3500.0)
        assert out['recession_rate_mm_s'] > RECESSION_VALID_MAX_MM_S
        assert out['thickness_status'] == 'NOT_MODELLED'
        assert out['model_valid'] is False
        assert out['required_thickness_mm'] is None
        assert out['required_thickness_m'] is None
        assert 'MODEL OUT OF ENVELOPE' in out['validity_note']
        assert 'validity ceiling' in out['validity_note']
        # Gerekçenin kanıtı (gerileme) yayımlanmaya DEVAM eder.
        assert out['recession_rate_mm_s'] > 0.0

    def test_gate_catches_liner_thicker_than_passage(self, tp):
        """Geometrik hüküm: astar, astarladığı geçitten kalın olamaz."""
        # Kapıyı YALNIZ geometriden tetikle: gerileme hızı tavanın altında
        # kalsın, ama uzun yanma toplam gerilemeyi yarıçapın üstüne taşısın.
        out = tp.ablative_thickness(1.0e6, burn_time_s=600.0,
                                    h_gas_W_m2K=3.0e3, T_recovery_K=3200.0,
                                    station_radius_m=0.010)
        assert out['recession_rate_mm_s'] <= RECESSION_VALID_MAX_MM_S
        assert out['thickness_status'] == 'NOT_MODELLED'
        assert out['required_thickness_mm'] is None
        assert 'station radius' in out['validity_note']
        # Burada İKİ geometrik gerekçe birden geçerli: astar geçitten kalın
        # (ölçülen 136.5 mm gerileme > 10 mm yarıçap → istasyon delinir;
        # eski yorumdaki 68.8 mm, sabit 0.5 blokaj + T_s=1900 K dönemine
        # aitti — v2.6.27'de ikisi de değişti).
        assert 'burn through' in out['validity_note']

        # AYRI DURUM: yalnız (b) — gereken kalınlık yarıçapı aşıyor ama
        # toplam gerileme aşmıyor (tasarım payı yüzünden). Kapı yine kapalı,
        # ama delinme gerekçesi KURULMAMALI (yanlış gerekçe de bir yalandır).
        # SAYI AYARI (v2.6.27 blokaj denetimi): sabit 0.5 blokaj kalkıp
        # silika T_s 1900→2050 K olunca bu noktadaki sdot 0.115→0.228 mm/s
        # değişti; pencereyi (total < r < 1.5*total) korumak için süre
        # 350→190 s çekildi (ölçülen: total = 43.2 mm, 1.5x = 64.9 mm).
        only_thickness = tp.ablative_thickness(
            1.0e6, burn_time_s=190.0, h_gas_W_m2K=3.0e3,
            T_recovery_K=3200.0, station_radius_m=0.050)
        assert only_thickness['total_recession_mm'] < 50.0
        assert only_thickness['total_recession_mm'] * 1.5 > 50.0
        assert only_thickness['thickness_status'] == 'NOT_MODELLED'
        assert 'is larger than the station radius' in \
            only_thickness['validity_note']
        assert 'burn through' not in only_thickness['validity_note']

        # Aynı koşul, yarıçap VERİLMEZSE geometrik hüküm kurulamaz —
        # kapı sessizce "geçti" demez, yalnız denetlemediğini bildirir.
        no_geom = tp.ablative_thickness(1.0e6, burn_time_s=600.0,
                                        h_gas_W_m2K=3.0e3,
                                        T_recovery_K=3200.0)
        assert no_geom['station_radius_m'] is None
        assert no_geom['thickness_status'] == 'sized'

    def test_no_net_heating_publishes_no_thickness(self, tp):
        """no_net_heating rejimi artık kalınlık YAYIMLAMAZ.

        DEĞİŞİKLİK GEREKÇESİ: testin eski hâli bu rejimde
        required_thickness_mm == 0.0 ve (dolaylı) 'sized' bekliyordu.
        0.0 mm bir tasarım değildir — gerileme sıfır olsa bile astar
        kalınlığını kasa/bond hattı sıcaklık sınırı (iletim + char payı,
        NASA SP-8093 pratiği) belirler ve bu Seviye-1 Q* modülü o iletim
        boyutlandırmasını YAPMIYOR. 0.0 mm'yi 'sized' basmak sessiz
        tehlikeydi; v2.6.27'de sözleşme NOT_MODELLED + None + gerekçeye
        çevrildi.
        """
        # T_recovery yüzey sıcaklığının (silika T_s = 2050 K) hemen üstünde:
        # blokajsız konvektif akı bile (1000*50 = 5e4 W/m^2) yeniden ışımayı
        # (0.9*sigma*2050^4 ≈ 9.0e5 W/m^2) karşılamaz.
        out = tp.ablative_thickness(9.9e6, burn_time_s=50.0,
                                    h_gas_W_m2K=1.0e3, T_recovery_K=2100.0,
                                    gas_cp_J_kgK=2000.0)
        assert out['q_conv_blocked_W_m2'] < out['q_reradiated_W_m2']
        assert out['recession_regime'] == 'no_net_heating'
        assert out['q_mean_W_m2'] == 0.0
        assert out['recession_rate_mm_s'] == 0.0
        assert out['total_recession_mm'] == 0.0
        # Kalınlık YOK — sıfır değil, None + NOT_MODELLED + gerekçe.
        assert out['required_thickness_mm'] is None
        assert out['required_thickness_m'] is None
        assert out['thickness_status'] == 'NOT_MODELLED'
        assert out['validity_note'].startswith('NO NET HEATING')
        assert 'case/bond-line' in out['validity_note']
        # Üfleme yoksa blokaj da yoktur: psi=1, B'=0 (limit davranışı).
        assert out['blowing_blockage'] == pytest.approx(1.0)
        assert out['b_prime'] == pytest.approx(0.0)
        # Hız tavanı ihlal edilmedi: model_valid kapısı ayrı bir hükümdür.
        assert out['model_valid'] is True

        # Gaz zaten ablasyon sıcaklığının ALTINDA (T_recovery < T_s):
        # aynı sözleşme.
        cold = tp.ablative_thickness(9.9e6, burn_time_s=50.0,
                                     h_gas_W_m2K=5.0e3, T_recovery_K=1500.0,
                                     gas_cp_J_kgK=2000.0)
        assert cold['recession_regime'] == 'no_net_heating'
        assert cold['recession_rate_mm_s'] == 0.0
        assert cold['total_recession_mm'] == 0.0
        assert cold['required_thickness_mm'] is None
        assert cold['thickness_status'] == 'NOT_MODELLED'
        assert cold['validity_note'].startswith('NO NET HEATING')
        assert cold['blowing_blockage'] == pytest.approx(1.0)

    def test_flux_basis_present_on_both_paths(self, tp):
        """flux_basis HER İKİ yolda da bulunmalı ve birbirinden farklı."""
        legacy = tp.ablative_thickness(1.0e6, burn_time_s=10.0)
        modern = tp.ablative_thickness(1.0e6, burn_time_s=10.0,
                                       h_gas_W_m2K=2.0e3,
                                       T_recovery_K=3000.0)
        assert legacy['flux_basis'] == 'caller_supplied_no_energy_balance'
        assert modern['flux_basis'] == 'surface_energy_balance'
        for out in (legacy, modern):
            for key in ('flux_basis', 'recession_regime', 'model_valid',
                        'validity_note', 'thickness_status',
                        'q_caller_W_m2'):
                assert key in out, key

    def test_half_given_energy_balance_raises(self, tp):
        """Yarım verilen enerji dengesi SESSİZCE yok sayılamaz."""
        with pytest.raises(ValueError, match='TOGETHER'):
            tp.ablative_thickness(1.0e6, burn_time_s=10.0,
                                  h_gas_W_m2K=2.0e3)
        with pytest.raises(ValueError, match='TOGETHER'):
            tp.ablative_thickness(1.0e6, burn_time_s=10.0,
                                  T_recovery_K=3000.0)
        with pytest.raises(ValueError):
            tp.ablative_thickness(1.0e6, burn_time_s=10.0,
                                  station_radius_m=0.0)

    def test_surface_table_fields_are_sourced(self):
        """Yüzey sıcaklığı/gaz payı alanları künyesiz eklenemez.

        DEĞİŞİKLİK GEREKÇESİ (v2.6.27 blokaj denetimi): tablodaki
        'blowing_blockage' (sabit psi) alanı KALDIRILDI — sabit katsayı
        yanlış rejimin katsayısıydı, psi artık B' üzerinden çözülüyor.
        Yerine gazlaşan kütle payı 'blowing_gas_fraction' geldi (karbon
        0.3 / silika 0.5 / EPDM 0.7, BLOWING_GAS_FRACTION_BAND içinde).
        Eski sıralama iddiası 'karbon > silika > EPDM' de kalktı: EPDM'nin
        800 K değeri piroliz BAŞLANGICIydı, yüzey sıcaklığı değil; ölçülen
        char yüzeyi (2300 K) silika eriyik platosunun (2050 K) ÜSTÜNDEdir.
        """
        for key, rec in ABLATIVE_MATERIALS.items():
            assert rec['T_ablation_K'] > 0, key
            lo, hi = rec['T_ablation_band_K']
            assert lo <= rec['T_ablation_K'] <= hi, key
            f_lo, f_hi = BLOWING_GAS_FRACTION_BAND
            assert f_lo <= rec['blowing_gas_fraction'] <= f_hi, key
            assert 'blowing_blockage' not in rec, (
                f'{key}: sabit blokaj katsayısı tabloya geri gelmiş')
            assert len(rec['surface_source']) > 80, key
        # Fizik sırası (v2.6.27): karbon char yüzeyi (3000 K) > EPDM char
        # yüzeyi (2300 K) > silika eriyik platosu (2050 K).
        assert (ABLATIVE_MATERIALS['carbon_phenolic']['T_ablation_K']
                > ABLATIVE_MATERIALS['epdm']['T_ablation_K']
                > ABLATIVE_MATERIALS['silica_phenolic']['T_ablation_K'])
        # Gaz payı sırası kaynak zinciriyle tutarlı: karbon-fenolikte gaz
        # payı en küçük, dolgulu EPDM'de en büyük.
        assert (ABLATIVE_MATERIALS['carbon_phenolic']['blowing_gas_fraction']
                < ABLATIVE_MATERIALS['silica_phenolic']['blowing_gas_fraction']
                < ABLATIVE_MATERIALS['epdm']['blowing_gas_fraction'])
