"""
Tests for the quasi-1D compressible nozzle flow module (nozzle_flow_1d).

Analytic anchors (hand-checkable, independent of the implementation):
  - Area-Mach table values, gamma = 1.4 (Anderson, "Modern Compressible
    Flow", 3rd ed., Appendix A):
        A/A* = 5.0  -> M ~ 3.175 (supersonic)
        A/A* = 2.0  -> M ~ 0.3059 (subsonic) / ~ 2.197 (supersonic)
  - Sonic-station ratios, gamma = 1.4 (Anderson App. A):
        P*/P0 = 0.5283,  T*/T0 = 0.8333
  - Sonic pressure ratio, gamma = 1.2: (2/2.2)^6 = 0.564474
  - Normal shock, M1 = 2.0, gamma = 1.4 (Anderson App. B / NACA 1135):
        M2 = 0.5774,  P2/P1 = 4.50,  P02/P01 = 0.7209
  - Ideal CF at optimum expansion, gamma = 1.4, Pc/Pa = 10 (Sutton &
    Biblarz 9th ed. Eq. 3-30, hand evaluation): CF ~ 1.2578

Run:
    cd <depo kökü>
    MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/test_nozzle_flow_1d.py -v
"""

import json
import math

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer, R_UNIVERSAL
from hrma.analysis.nozzle_flow_1d import (
    NozzleFlow1D,
    area_ratio_from_mach,
    ideal_thrust_coefficient,
    isentropic_ratios,
    normal_shock_relations,
)

SEA_LEVEL = 101325.0  # Pa


def make_solver(**overrides):
    """Ortak hibrit-benzeri temel durum; testler alanları ezerek türetir."""
    kwargs = dict(
        chamber_pressure=20e5,        # Pa
        chamber_temperature=3200.0,   # K
        gamma=1.2,
        molecular_weight=24.0,        # g/mol
        throat_diameter=0.02,         # m
        expansion_ratio=5.0,
        ambient_pressure=0.0,         # vakum
        n_stations=60,
    )
    kwargs.update(overrides)
    return NozzleFlow1D(**kwargs)


# ======================================================================
# 1) İzantropik çekirdek — analitik çapalar
# ======================================================================
class TestIsentropicCore:

    def test_area_mach_supersonic_anderson_eps5(self):
        # Anderson App. A: A/A* = 5 -> M ~ 3.175 (gamma = 1.4)
        m = HeatTransferAnalyzer._mach_from_area_ratio(5.0, 1.4, supersonic=True)
        assert abs(m - 3.175) < 0.01
        # İleri bağıntıyla kapanış: A/A*(M) = 5 (bağımsız formül)
        assert abs(area_ratio_from_mach(m, 1.4) - 5.0) < 1e-8

    def test_area_mach_subsonic_anderson_eps2(self):
        # Anderson App. A: A/A* = 2 -> M ~ 0.3059 (subsonik dal)
        m = HeatTransferAnalyzer._mach_from_area_ratio(2.0, 1.4, supersonic=False)
        assert abs(m - 0.3059) < 2e-3

    def test_area_mach_supersonic_anderson_eps2(self):
        # Anderson App. A: A/A* = 2 -> M ~ 2.197 (süpersonik dal)
        m = HeatTransferAnalyzer._mach_from_area_ratio(2.0, 1.4, supersonic=True)
        assert abs(m - 2.197) < 2e-3

    def test_sonic_ratios_gamma14(self):
        t, p, _ = isentropic_ratios(1.0, 1.4)
        assert abs(p - 0.5283) < 1e-4   # P*/P0, Anderson App. A
        assert abs(t - 0.8333) < 1e-4   # T*/T0

    def test_throat_mach_is_unity(self):
        res = make_solver().solve(include_bartz=False)
        assert res['throat']['mach'] == pytest.approx(1.0, abs=1e-9)

    def test_throat_pressure_ratio_gamma12(self):
        # P*/Pc = (2/(g+1))^(g/(g-1)) = (2/2.2)^6 = 0.564474 (el hesabı)
        res = make_solver().solve(include_bartz=False)
        ratio = res['throat']['pressure_Pa'] / 20e5
        assert ratio == pytest.approx((2.0 / 2.2) ** 6, rel=1e-9)
        assert ratio == pytest.approx(0.564474, abs=1e-6)

    def test_mach_monotonic_and_pressure_decreasing(self):
        res = make_solver().solve(include_bartz=False)
        i_t = res['throat']['index']
        mach = np.array(res['stations']['mach'])
        pres = np.array(res['stations']['pressure_Pa'])
        # Konverjanda subsonik, diverjanda süpersonik; M monoton artar
        assert np.all(mach[:i_t] < 1.0)
        assert np.all(mach[i_t + 1:] > 1.0)
        assert np.all(np.diff(mach) > -1e-12)
        # Basınç lüle boyunca monoton düşer
        assert np.all(np.diff(pres) < 1e-9)

    def test_mass_conservation_between_stations(self):
        # İstasyonlar arası bağıl kütle korunum hatası < 1e-6 (görev şartı)
        res = make_solver().solve(include_bartz=False)
        assert res['performance']['mass_conservation_max_rel_error'] < 1e-6

    def test_mass_flow_matches_cstar_definition(self):
        # mdot = Pc * A_t / c*  (c* tanımı; Sutton Eq. 3-32 kapanışı)
        res = make_solver().solve(include_bartz=False)
        perf = res['performance']
        a_t = res['throat']['area_m2']
        assert perf['mass_flow_kg_s'] == pytest.approx(
            20e5 * a_t / perf['c_star_m_s'], rel=1e-9)

    def test_exit_velocity_closed_form(self):
        # Sutton Eq. 3-16: u_e = sqrt(2gRTc/(g-1) * (1 - (Pe/Pc)^((g-1)/g)))
        res = make_solver().solve(include_bartz=False)
        g, mw, tc, pc = 1.2, 24.0, 3200.0, 20e5
        r_gas = R_UNIVERSAL / mw
        pe = res['stations']['pressure_Pa'][-1]
        u_ref = math.sqrt(2 * g * r_gas * tc / (g - 1)
                          * (1 - (pe / pc) ** ((g - 1) / g)))
        assert res['stations']['velocity_m_s'][-1] == pytest.approx(u_ref, rel=1e-9)


# ======================================================================
# 2) Normal şok bağıntıları — Anderson App. B / NACA 1135 çapaları
# ======================================================================
class TestNormalShockRelations:

    def test_shock_m1_2_gamma14(self):
        m2, p2_p1, p02_p01 = normal_shock_relations(2.0, 1.4)
        assert abs(m2 - 0.5774) < 1e-4
        assert abs(p2_p1 - 4.50) < 1e-6
        assert abs(p02_p01 - 0.7209) < 1e-4

    def test_weak_shock_limit(self):
        # M1 -> 1+ : şok kaybolur (tüm oranlar 1'e gider)
        m2, p2_p1, p02_p01 = normal_shock_relations(1.0 + 1e-6, 1.4)
        assert abs(m2 - 1.0) < 1e-4
        assert abs(p2_p1 - 1.0) < 1e-4
        assert abs(p02_p01 - 1.0) < 1e-8

    def test_subsonic_input_raises(self):
        with pytest.raises(ValueError):
            normal_shock_relations(0.8, 1.4)


# ======================================================================
# 3) Rejim sınıflandırması
# ======================================================================
class TestRegimeClassification:

    def test_vacuum_is_underexpanded(self):
        res = make_solver(ambient_pressure=0.0).solve(include_bartz=False)
        assert res['regime']['type'] == 'underexpanded'
        assert res['regime']['separation'] is None
        assert res['regime']['normal_shock'] is None

    def test_perfectly_expanded_when_pa_equals_pe(self):
        base = make_solver().solve(include_bartz=False)
        pe = base['regime']['exit_pressure_isentropic_Pa']
        res = make_solver(ambient_pressure=pe).solve(include_bartz=False)
        assert res['regime']['type'] == 'perfectly_expanded'

    def test_perfect_band_boundaries(self):
        base = make_solver().solve(include_bartz=False)
        pe = base['regime']['exit_pressure_isentropic_Pa']
        # Tolerans bandı ±%1: 0.98 Pe -> under, 1.005 Pe -> perfect, 1.02 Pe -> over
        r_under = make_solver(ambient_pressure=0.98 * pe).solve(include_bartz=False)
        r_perf = make_solver(ambient_pressure=1.005 * pe).solve(include_bartz=False)
        r_over = make_solver(ambient_pressure=1.02 * pe).solve(include_bartz=False)
        assert r_under['regime']['type'] == 'underexpanded'
        assert r_perf['regime']['type'] == 'perfectly_expanded'
        assert r_over['regime']['type'] == 'overexpanded'

    def test_separation_onset_boundary(self):
        # Summerfield eşiği: Pa = Pe/k sınırının iki yanı
        base = make_solver().solve(include_bartz=False)
        pe = base['regime']['exit_pressure_isentropic_Pa']
        onset = pe / 0.40
        r_attached = make_solver(ambient_pressure=0.99 * onset).solve(include_bartz=False)
        r_separated = make_solver(ambient_pressure=1.01 * onset).solve(include_bartz=False)
        assert r_attached['regime']['type'] == 'overexpanded'
        assert r_separated['regime']['type'] == 'separated'

    def test_high_expansion_sea_level_is_separated(self):
        # Görev senaryosu: yüksek genişleme oranı + deniz seviyesi -> SEPARATED
        res = make_solver(expansion_ratio=15.0,
                          ambient_pressure=SEA_LEVEL).solve(include_bartz=False)
        assert res['regime']['type'] == 'separated'

    def test_normal_shock_regime_low_pc(self):
        # Pc = 3 atm, eps = 4, gamma = 1.4, deniz seviyesi:
        # el hesabı — Pe/Pc ~ 0.0298, şok-çıkışta basınç ~ 0.295 Pc = 0.886 atm
        # < 1 atm  =>  şok lüle İÇİNDE olmalı.
        res = make_solver(chamber_pressure=3 * SEA_LEVEL,
                          chamber_temperature=2000.0, gamma=1.4,
                          molecular_weight=28.0, expansion_ratio=4.0,
                          ambient_pressure=SEA_LEVEL).solve(include_bartz=False)
        assert res['regime']['type'] == 'normal_shock_in_nozzle'
        assert res['regime']['normal_shock'] is not None

    def test_shock_at_exit_boundary(self):
        # Şok-çıkışta eşiğinin iki yanı: altı separated, üstü shock-in-nozzle
        probe = make_solver(chamber_pressure=3 * SEA_LEVEL,
                            chamber_temperature=2000.0, gamma=1.4,
                            molecular_weight=28.0, expansion_ratio=4.0,
                            ambient_pressure=SEA_LEVEL).solve(include_bartz=False)
        p_shock_exit = probe['regime']['thresholds_Pa']['shock_at_exit_Pa']
        common = dict(chamber_pressure=3 * SEA_LEVEL, chamber_temperature=2000.0,
                      gamma=1.4, molecular_weight=28.0, expansion_ratio=4.0)
        r_below = make_solver(ambient_pressure=0.99 * p_shock_exit,
                              **common).solve(include_bartz=False)
        r_above = make_solver(ambient_pressure=1.01 * p_shock_exit,
                              **common).solve(include_bartz=False)
        assert r_below['regime']['type'] == 'separated'
        assert r_above['regime']['type'] == 'normal_shock_in_nozzle'

    def test_unchoked_edge_case(self):
        # Pa, tam-subsonik çıkış basıncını da aşarsa lüle boğulmaz
        res = make_solver(chamber_pressure=1.02e5, chamber_temperature=2000.0,
                          gamma=1.4, molecular_weight=28.0, expansion_ratio=4.0,
                          ambient_pressure=SEA_LEVEL).solve(include_bartz=False)
        assert res['regime']['type'] == 'unchoked'

    def test_thresholds_are_ordered(self):
        # Eşikler artan sırt basıncıyla monoton sıralı olmalı
        res = make_solver().solve(include_bartz=False)
        th = res['regime']['thresholds_Pa']
        assert (th['perfect_expansion_low_Pa']
                < th['perfect_expansion_high_Pa']
                < th['separation_onset_Pa']
                < th['shock_at_exit_Pa']
                < th['unchoked_above_Pa'])


# ======================================================================
# 4) Ayrılma (Summerfield) ayrıntıları
# ======================================================================
class TestSeparation:

    @pytest.fixture()
    def separated(self):
        return make_solver(expansion_ratio=15.0,
                           ambient_pressure=SEA_LEVEL).solve(include_bartz=False)

    def test_separation_station_inside_divergent(self, separated):
        sep = separated['regime']['separation']
        x_t = separated['throat']['x_mm']
        x_e = separated['stations']['x_mm'][-1]
        assert x_t < sep['station_x_mm'] < x_e
        assert 1.0 < sep['area_ratio'] < separated['performance']['expansion_ratio']
        assert sep['mach'] > 1.0

    def test_separation_wall_pressure_matches_criterion(self, separated):
        # Kriter: P_wall(x_sep) = k * P_amb (k = 0.40 varsayılan)
        sep = separated['regime']['separation']
        assert sep['wall_pressure_Pa'] == pytest.approx(0.40 * SEA_LEVEL, rel=1e-6)
        assert sep['effective_exit_pressure_Pa'] == pytest.approx(
            0.40 * SEA_LEVEL, rel=1e-6)
        assert sep['criterion_factor'] == pytest.approx(0.40)

    def test_wall_pressure_plateau_downstream(self, separated):
        # Ayrılma sonrası cidar basıncı ortam platosuna oturur
        sep_x = separated['regime']['separation']['station_x_mm']
        x = np.array(separated['stations']['x_mm'])
        wall_p = np.array(separated['stations']['wall_pressure_Pa'])
        downstream = x > sep_x
        assert downstream.any()
        assert np.allclose(wall_p[downstream], SEA_LEVEL)

    def test_separated_thrust_exceeds_full_flow_prediction(self, separated):
        # Ayrılma, aşırı-genişlemiş tam akışın itki cezasını sınırlar:
        # F_sep > F_full_flow (bu yüzden rapor edilir)
        perf = separated['performance']
        assert perf['thrust_N'] > perf['thrust_full_flow_N']
        assert perf['separation_thrust_gain_N'] > 0.0

    def test_custom_separation_factor(self):
        # k = 0.35 (bandın diğer ucu) ile eşik kayar ama kriter tutarlı kalır
        res = make_solver(expansion_ratio=15.0, ambient_pressure=SEA_LEVEL,
                          separation_factor=0.35).solve(include_bartz=False)
        sep = res['regime']['separation']
        assert sep['wall_pressure_Pa'] == pytest.approx(0.35 * SEA_LEVEL, rel=1e-6)


# ======================================================================
# 5) Lüle içi normal şok ayrıntıları
# ======================================================================
class TestNormalShockInNozzle:

    @pytest.fixture()
    def shocked(self):
        return make_solver(chamber_pressure=3 * SEA_LEVEL,
                           chamber_temperature=2000.0, gamma=1.4,
                           molecular_weight=28.0, expansion_ratio=4.0,
                           ambient_pressure=SEA_LEVEL).solve(include_bartz=False)

    def test_shock_between_throat_and_exit(self, shocked):
        sh = shocked['regime']['normal_shock']
        assert shocked['throat']['x_mm'] < sh['station_x_mm'] \
            < shocked['stations']['x_mm'][-1]
        assert sh['upstream_mach'] > 1.0
        assert sh['downstream_mach'] < 1.0

    def test_exit_pressure_matches_ambient(self, shocked):
        # Quasi-1D eşleme: şok sonrası subsonik difüzyon Pa'ya oturmalı
        sh = shocked['regime']['normal_shock']
        assert sh['exit_pressure_Pa'] == pytest.approx(SEA_LEVEL, rel=1e-6)
        assert shocked['performance']['exit']['pressure_Pa'] == pytest.approx(
            SEA_LEVEL, rel=1e-3)

    def test_mass_conserved_across_shock(self, shocked):
        # Şok kütleyi korur: istasyon debileri şok sonrasında da sabit
        assert shocked['performance']['mass_conservation_max_rel_error'] < 1e-6

    def test_exit_subsonic_after_shock(self, shocked):
        assert shocked['performance']['exit']['mach'] < 1.0
        mach = np.array(shocked['stations']['mach'])
        # Şok istasyonundan sonra akış subsonik kalmalı
        x = np.array(shocked['stations']['x_mm'])
        sh_x = shocked['regime']['normal_shock']['station_x_mm']
        assert np.all(mach[x > sh_x] < 1.0)


# ======================================================================
# 6) İtki ve CF
# ======================================================================
class TestThrust:

    def test_cf_matches_ideal_formula_perfect_expansion(self):
        # Tam genişlemede momentum formülü Sutton Eq. 3-30 ile özdeş olmalı
        base = make_solver().solve(include_bartz=False)
        pe = base['regime']['exit_pressure_isentropic_Pa']
        res = make_solver(ambient_pressure=pe).solve(include_bartz=False)
        perf = res['performance']
        assert perf['CF'] == pytest.approx(perf['CF_ideal'], rel=1e-9)

    def test_cf_hand_anchor_optimum_gamma14(self):
        # El hesabı çapası (Sutton Eq. 3-30): gamma=1.4, Pc/Pa=10, optimum
        # genişleme -> CF = sqrt(9.8*(2/2.4)^6*(1-0.1^(0.4/1.4))) ~ 1.2578
        g, pc = 1.4, 10 * SEA_LEVEL
        # Pe/Pc = 0.1 -> (1 + 0.2 M^2)^3.5 = 10 -> M_e = 2.1572 (el hesabı)
        m_e = math.sqrt((10 ** (1 / 3.5) - 1) / 0.2)
        eps = area_ratio_from_mach(m_e, g)
        d_t = 0.02
        res = NozzleFlow1D(chamber_pressure=pc, chamber_temperature=2500.0,
                           gamma=g, molecular_weight=28.0,
                           throat_diameter=d_t,
                           exit_diameter=d_t * math.sqrt(eps),
                           ambient_pressure=SEA_LEVEL,
                           n_stations=60).solve(include_bartz=False)
        assert res['regime']['type'] == 'perfectly_expanded'
        assert res['performance']['CF'] == pytest.approx(1.2578, abs=1e-3)

    def test_vacuum_cf_exceeds_sea_level_cf(self):
        r_vac = make_solver(ambient_pressure=0.0).solve(include_bartz=False)
        base_pe = r_vac['regime']['exit_pressure_isentropic_Pa']
        r_amb = make_solver(ambient_pressure=base_pe).solve(include_bartz=False)
        assert r_vac['performance']['CF'] > r_amb['performance']['CF']

    def test_wall_integral_cross_check(self):
        # Cidar basıncı integrali momentum formülünü %2 içinde doğrulamalı
        for overrides in (
            {},  # vakum, attached
            {'expansion_ratio': 15.0, 'ambient_pressure': SEA_LEVEL},  # separated
        ):
            res = make_solver(**overrides).solve(include_bartz=False)
            assert res['performance']['wall_integral_residual_rel'] < 0.02

    def test_effective_thrust_below_ideal(self):
        # Kayıplar itkiyi düşürmeli: F_eff < F, ve lambda < 1
        res = make_solver().solve(include_bartz=False)
        assert res['losses']['thrust_effective_N'] < res['performance']['thrust_N']
        assert 0.9 < res['losses']['divergence_factor'] < 1.0

    def test_losses_tagged_approximate(self):
        res = make_solver().solve(include_bartz=False)
        assert res['losses']['method'] == 'approximate'
        assert 0.0 <= res['losses']['friction_loss_fraction'] < 0.2


# ======================================================================
# 7) Eksenel Bartz coupling (ithal korelasyon)
# ======================================================================
class TestBartzCoupling:

    @pytest.fixture()
    def solved(self):
        return make_solver(ambient_pressure=0.0).solve(include_bartz=True)

    def test_h_g_peaks_at_throat(self, solved):
        h_g = solved['stations']['h_g_W_m2K']
        assert int(np.argmax(h_g)) == solved['throat']['index']
        assert all(h > 0 for h in h_g)

    def test_h_g_matches_direct_bartz_call_at_throat(self, solved):
        # Modül, korelasyonu KOPYALAMAYIP ısı modülünden çağırmalı:
        # boğazda birebir aynı değeri üretmeli.
        hta = HeatTransferAnalyzer()
        md = {'gamma': 1.2, 'molecular_weight': 24.0, 'throat_diameter': 0.02}
        gas = hta._get_gas_properties(md, 3200.0)
        throat = hta._resolve_throat_conditions(md, 20e5, 3200.0, gas, 0.0)
        taw = hta._adiabatic_wall_temperature(3200.0, gas, 1.0)
        tw = min(800.0, taw - 1.0)
        h_ref = hta._bartz_coefficient(
            throat['throat_diameter'], 20e5, throat['c_star'], gas,
            3200.0, tw, throat['rc_over_dt'],
            area_ratio_local=1.0, mach_local=1.0)
        i_t = solved['throat']['index']
        assert solved['stations']['h_g_W_m2K'][i_t] == pytest.approx(h_ref, rel=1e-9)

    def test_recovery_temperature_physical(self, solved):
        taw = np.array(solved['stations']['T_recovery_K'])
        assert np.all(taw < 3200.0)      # Taw < T0 (r < 1)
        assert np.all(taw > 0.75 * 3200.0)

    def test_convective_flux_positive(self, solved):
        q = np.array(solved['stations']['q_conv_W_m2'])
        assert np.all(q > 0.0)

    def test_fast_mode_skips_bartz(self):
        res = make_solver().solve(include_bartz=False)
        assert res['stations']['h_g_W_m2K'] == []
        assert res['stations']['q_conv_W_m2'] == []


# ======================================================================
# 8) API sözleşmesi, girdi doğrulama, JSON güvenliği
# ======================================================================
class TestApiContract:

    def test_output_is_json_serializable(self):
        res = make_solver().solve(include_bartz=True)
        json.dumps(res)  # numpy tipi sızarsa TypeError fırlatır

    def test_station_arrays_share_length(self):
        res = make_solver().solve(include_bartz=True)
        st = res['stations']
        n = len(st['x_mm'])
        for key in ('radius_mm', 'area_ratio', 'mach', 'pressure_Pa',
                    'wall_pressure_Pa', 'temperature_K', 'density_kg_m3',
                    'velocity_m_s', 'h_g_W_m2K', 'q_conv_W_m2', 'T_recovery_K'):
            assert len(st[key]) == n, key

    def test_station_count_clamped_to_wave4_band(self):
        # Dalga 4 planı: 30-60 istasyon
        lo = make_solver(n_stations=5).solve(include_bartz=False)
        hi = make_solver(n_stations=500).solve(include_bartz=False)
        assert len(lo['stations']['x_mm']) == 30
        assert len(hi['stations']['x_mm']) == 60

    def test_from_motor_data_bar_convention(self):
        # Repo motor_data sözleşmesi: chamber_pressure [bar]
        md = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
              'gamma': 1.2, 'molecular_weight': 24.0,
              'throat_diameter': 0.02, 'exit_diameter': 0.02 * math.sqrt(5.0)}
        nf = NozzleFlow1D.from_motor_data(md, ambient_pressure=0.0)
        res = nf.solve(include_bartz=False)
        assert res['inputs']['chamber_pressure_Pa'] == pytest.approx(20e5)
        assert res['performance']['expansion_ratio'] == pytest.approx(5.0, rel=1e-6)

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            make_solver(gamma=1.7)                       # gamma bandı dışı
        with pytest.raises(ValueError):
            make_solver(ambient_pressure=30e5)           # Pa >= Pc: akış yok
        with pytest.raises(ValueError):
            make_solver(expansion_ratio=0.8)             # eps <= 1
        with pytest.raises(ValueError):
            make_solver(separation_factor=0.7)           # Summerfield bandı dışı
        with pytest.raises(ValueError):
            NozzleFlow1D(chamber_pressure=20e5, chamber_temperature=3200.0,
                         throat_diameter=None, exit_diameter=0.08)

    def test_ideal_cf_helper_hand_value(self):
        # Sutton Eq. 3-30 yardımcı fonksiyonu — bağımsız el hesabı:
        # gamma=1.4, Pe/Pc=0.1, Pa=Pe (optimum, basınç terimi sıfır)
        # CF = sqrt(9.8 * (2/2.4)^6 * (1 - 0.1^(0.4/1.4))) ~ 1.2578
        m_e = math.sqrt((10 ** (1 / 3.5) - 1) / 0.2)
        eps = area_ratio_from_mach(m_e, 1.4)
        cf = ideal_thrust_coefficient(1.4, 0.1, 0.1, eps)
        assert cf == pytest.approx(1.2578, abs=1e-3)
