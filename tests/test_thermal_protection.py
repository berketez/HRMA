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
"""

import math

import numpy as np
import pytest

from hrma.analysis.thermal_protection import (
    ABLATIVE_MATERIALS,
    RADIATION_EXTENSION_MATERIALS,
    STEFAN_BOLTZMANN,
    ThermalProtectionAnalyzer,
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
                    'model_note', 'source'):
            assert key in out, key

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
