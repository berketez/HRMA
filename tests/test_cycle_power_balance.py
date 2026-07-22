"""Çevrim güç dengesi çözücüsü testleri (cycle_power_balance).

Doğrulama çapaları:

* RS-25 benzeri (LOX/LH2, Pc=206.4 bar, yakıtça zengin staged combustion):
  HPFTP çıkışı ~450-480 bar, gücü ~46 MW (NASA RS-25/SSME verileri;
  Sutton 9th ed. Table 10-3). Bantlar ±%30.
* Merlin 1D benzeri (LOX/RP1, Pc=97 bar, gaz jeneratörü): GG debi oranı
  tarihsel %2-5 bandında, açık çevrim Isp kaybı 1-4 s (Sutton Ch. 6 çevrim
  karşılaştırması).
* Raptor benzeri (LOX/CH4, Pc=300 bar, FFSC): pompa çıkışları 600-850 bar,
  iki mil toplam gücü 50-80 MW (SpaceX Raptor kamuya açık verileri) — bu
  sayılar modele YAZILMAZ, basınç zinciri + güç dengesinden ÇIKMALIDIR.
* Enerji korunumu: her çevrimde türbin gücü = pompa gücü, göreli artık
  < 1e-6.
"""

import pytest

from hrma.engines.cycle_power_balance import (
    CycleSolution,
    STAGED_PR_TYPICAL,
    solve_cycle,
    solve_preburner_of,
)

RESIDUAL_TOL = 1e-6


def _rs25():
    # RS-25: Pc = 206.4 bar, toplam debi ~512 kg/s, MR = 6.03 (NASA verisi).
    # Pompa/türbin verimleri Sutton Table 10-3 aralığından (0.75).
    return solve_cycle('staged_combustion', 206.4, 512.0, 6.03, 'lh2',
                       preburner_mode='fuel_rich', regen_dp_bar=30.0,
                       eta_pump_ox=0.75, eta_pump_fuel=0.75,
                       eta_turbine=0.75, tit_K=1000.0)


def _merlin():
    # Merlin 1D: Pc ~97 bar, deniz seviyesi debisi ~305 kg/s, MR ~2.36.
    # GG türbini kısmi giriş/tek kademe: verim 0.55 (Sutton Table 10-3
    # GG türbinleri 0.5-0.65 bandı).
    return solve_cycle('gas_generator', 97.0, 305.0, 2.36, 'rp1',
                       regen_dp_bar=10.0, eta_turbine=0.55,
                       isp_main_s=282.0)


def _raptor():
    # Raptor: Pc = 300 bar, MR = 3.6, toplam ~700 kg/s. Modern yüksek güçlü
    # turbopompa verimleri 0.8 / türbin 0.75 (Sutton Table 10-3 üst bandı).
    return solve_cycle('full_flow_staged_combustion', 300.0, 700.0, 3.6,
                       'methane', regen_dp_bar=50.0, eta_pump_ox=0.80,
                       eta_pump_fuel=0.80, eta_turbine=0.75)


def _rl10():
    # RL10 benzeri: Pc = 32.75 bar, ~16.85 kg/s, MR = 5.5; rejeneratif ısı
    # alımı ~6.5 MW (H2 20 K -> ~210 K; RL10 literatürü, Sutton Ch. 6).
    return solve_cycle('expander', 32.75, 16.85, 5.5, 'lh2',
                       regen_dp_bar=10.0, regen_heat_kw=6500.0,
                       eta_turbine=0.75)


class TestEnergyConservation:
    """Her çevrimde mil başına türbin gücü = pompa gücü kapanmalı."""

    @pytest.mark.parametrize('make', [_rs25, _merlin, _raptor, _rl10],
                             ids=['staged', 'gg', 'ffsc', 'expander'])
    def test_power_balance_closes(self, make):
        sol = make()
        assert sol.converged
        assert sol.power_residual_rel < RESIDUAL_TOL
        for shaft in sol.shafts:
            assert shaft['power_residual_rel'] < RESIDUAL_TOL
            assert shaft['turbine_power_W'] == pytest.approx(
                shaft['pump_power_W'], rel=RESIDUAL_TOL)

    def test_tap_off_balance_closes(self):
        sol = solve_cycle('tap_off', 70.0, 250.0, 2.3, 'rp1',
                          regen_dp_bar=8.0, isp_main_s=265.0)
        assert sol.converged
        assert sol.power_residual_rel < RESIDUAL_TOL

    def test_ox_rich_staged_balance_closes(self):
        # RD-180 benzeri ORSC: LOX/RP1, Pc = 257 bar, MR = 2.72.
        sol = solve_cycle('staged_combustion', 257.0, 1200.0, 2.72, 'rp1',
                          preburner_mode='ox_rich', regen_dp_bar=40.0,
                          eta_turbine=0.75)
        assert sol.converged
        assert sol.power_residual_rel < RESIDUAL_TOL
        # Ox-zengin ön yakıcıdan TÜM oksitleyici geçer.
        pb = sol.preburners[0]
        assert pb['mode'] == 'ox_rich'
        m_ox_total = 1200.0 * 2.72 / 3.72
        assert pb['mdot_ox_kg_s'] == pytest.approx(m_ox_total, rel=1e-9)


class TestRS25Like:
    """RS-25 benzeri FRSC çapası (NASA verileri, ±%30 bandı)."""

    def test_fuel_pump_discharge_band(self):
        sol = _rs25()
        # ~450-480 bar (NASA RS-25 HPFTP), ±%30 bandı.
        assert 450.0 * 0.7 <= sol.pump_discharge_fuel_bar <= 480.0 * 1.3

    def test_fuel_pump_power_band(self):
        sol = _rs25()
        # HPFTP ~46 MW (NASA RS-25), ±%30 bandı.
        assert 46e6 * 0.7 <= sol.pump_power_fuel_W <= 46e6 * 1.3

    def test_turbine_pr_in_physical_range(self):
        sol = _rs25()
        pr = sol.shafts[0]['turbine']['pressure_ratio']
        assert STAGED_PR_TYPICAL[0] <= pr <= STAGED_PR_TYPICAL[1]

    def test_all_fuel_passes_through_preburner(self):
        sol = _rs25()
        pb = sol.preburners[0]
        m_fuel_total = 512.0 / (1.0 + 6.03)
        assert pb['mdot_fuel_kg_s'] == pytest.approx(m_fuel_total, rel=1e-9)
        # Ön yakıcı sıcaklığı kısıttan çözülür.
        assert pb['temperature_K'] == pytest.approx(1000.0, abs=1.0)

    def test_closed_cycle_has_no_isp_loss(self):
        sol = _rs25()
        assert sol.isp_mode == 'closed_cycle_no_loss'
        assert sol.isp_loss_s == 0.0


class TestMerlinLikeGG:
    """Merlin benzeri gaz jeneratörü çapası."""

    def test_gg_flow_fraction_band(self):
        sol = _merlin()
        frac = sol.turbine_mdot_total_kg_s / 305.0
        assert 0.02 <= frac <= 0.05

    def test_isp_loss_band(self):
        sol = _merlin()
        assert 1.0 <= sol.isp_loss_s <= 4.0
        assert sol.isp_mode == 'open_cycle_mixture_average'
        # Egzoz Isp'si ana odadan belirgin düşük ama sıfır değil.
        assert 0.0 < sol.secondary_exhaust_isp_s < 282.0

    def test_gg_of_solved_from_temperature(self):
        sol = _merlin()
        pb = sol.preburners[0]
        # Yakıtça zengin: O/F stokiyometrinin çok altında olmalı.
        assert 0.05 <= pb['of_ratio'] <= 0.6
        assert pb['temperature_K'] == pytest.approx(1000.0, abs=1.0)

    def test_bleed_subtracted_from_main_chamber(self):
        sol = _merlin()
        assert (sol.main_chamber['mdot_kg_s']
                + sol.turbine_mdot_total_kg_s) == pytest.approx(305.0,
                                                                rel=1e-9)
        # Kayıp, karışım ortalaması tanımıyla tutarlı olmalı.
        frac = sol.turbine_mdot_total_kg_s / 305.0
        expected = frac * (282.0 - sol.secondary_exhaust_isp_s)
        assert sol.isp_loss_s == pytest.approx(expected, rel=1e-9)

    def test_isp_loss_not_fabricated_without_main_isp(self):
        sol = solve_cycle('gas_generator', 97.0, 305.0, 2.36, 'rp1')
        assert sol.isp_loss_s is None
        assert 'isp_loss' in sol.not_modelled


class TestRaptorLikeFFSC:
    """Raptor benzeri FFSC: sayılar SONUÇ olmalı, hardcode değil."""

    def test_two_shafts_two_preburners(self):
        sol = _raptor()
        assert sol.converged
        assert {s['name'] for s in sol.shafts} == {'fuel', 'ox'}
        modes = {p['mode'] for p in sol.preburners}
        assert modes == {'fuel_rich', 'ox_rich'}

    def test_pump_discharges_emerge_in_raptor_band(self):
        sol = _raptor()
        # Pc=300 bar için ~700-800 bar sınıfı çıkış doğal SONUÇ olmalı.
        assert 600.0 <= sol.pump_discharge_fuel_bar <= 850.0
        assert 600.0 <= sol.pump_discharge_ox_bar <= 850.0

    def test_total_shaft_power_band(self):
        sol = _raptor()
        assert 50e6 <= sol.pump_power_total_W <= 80e6

    def test_all_flow_passes_through_turbines(self):
        sol = _raptor()
        assert sol.turbine_mdot_total_kg_s == pytest.approx(700.0, rel=1e-6)

    def test_main_chamber_receives_two_gas_streams(self):
        sol = _raptor()
        streams = sol.main_chamber['inlet_streams']
        assert len(streams) == 2
        assert all(s['phase'] == 'gas' for s in streams)
        assert all(s['temperature_K'] > 500.0 for s in streams)
        total = sum(s['mdot_kg_s'] for s in streams)
        assert total == pytest.approx(700.0, rel=1e-6)

    def test_turbine_prs_in_physical_range(self):
        sol = _raptor()
        for shaft in sol.shafts:
            pr = shaft['turbine']['pressure_ratio']
            assert STAGED_PR_TYPICAL[0] <= pr <= STAGED_PR_TYPICAL[1]

    def test_preburner_temperatures_respect_limits(self):
        sol = _raptor()
        by_mode = {p['mode']: p for p in sol.preburners}
        assert by_mode['fuel_rich']['temperature_K'] <= 1100.0 + 1.0
        assert by_mode['ox_rich']['temperature_K'] <= 850.0 + 1.0


class TestExpander:
    def test_rl10_like_converges(self):
        sol = _rl10()
        assert sol.converged
        assert sol.isp_mode == 'closed_cycle_no_loss'
        # Türbin gazı yakıtın kendisidir: debi = toplam yakıt debisi.
        m_fuel = 16.85 / 6.5
        assert sol.turbine_mdot_total_kg_s == pytest.approx(m_fuel, rel=1e-9)
        # Isınmış yakıt ana odaya gaz olarak girer.
        labels = [s['label'] for s in sol.main_chamber['inlet_streams']]
        assert any('heated fuel' in lab for lab in labels)

    def test_power_limit_reported_not_faked(self):
        # Büyük motor + yetersiz ısı alımı: expander doğal güç sınırı.
        sol = solve_cycle('expander', 200.0, 600.0, 3.6, 'methane',
                          regen_dp_bar=40.0, regen_heat_kw=20000.0)
        assert not sol.converged
        assert 'power_balance' in sol.not_modelled
        assert any('power limit' in w for w in sol.warnings)

    def test_missing_heat_input_is_not_modelled(self):
        sol = solve_cycle('expander', 30.0, 15.0, 5.5, 'lh2')
        assert not sol.converged
        assert 'turbine_inlet_state' in sol.not_modelled


class TestBoundaries:
    def test_pressure_fed_negative_margin_warns(self):
        sol = solve_cycle('pressure_fed', 30.0, 5.0, 2.1, 'rp1',
                          tank_pressure_bar=20.0)
        assert not sol.converged
        assert sol.tank_pressure_margin_bar < 0.0
        assert any('infeasible' in w for w in sol.warnings)

    def test_pressure_fed_positive_margin_converges(self):
        sol = solve_cycle('pressure_fed', 20.0, 5.0, 2.1, 'rp1',
                          tank_pressure_bar=35.0)
        assert sol.converged
        assert sol.tank_pressure_margin_bar > 0.0
        assert sol.pump_power_total_W == 0.0

    def test_excessive_tit_warns(self):
        sol = solve_cycle('gas_generator', 97.0, 305.0, 2.36, 'rp1',
                          tit_K=1250.0, isp_main_s=282.0)
        assert any('uncooled-blade' in w for w in sol.warnings)

    def test_ox_rich_lh2_warns(self):
        sol = solve_cycle('staged_combustion', 200.0, 500.0, 6.0, 'lh2',
                          preburner_mode='ox_rich')
        assert any('no flight precedent' in w for w in sol.warnings)

    def test_unknown_cycle_rejected(self):
        with pytest.raises(ValueError):
            solve_cycle('warp_drive', 100.0, 100.0, 2.5, 'rp1')

    def test_unknown_fuel_rejected(self):
        with pytest.raises(ValueError):
            solve_cycle('gas_generator', 100.0, 100.0, 2.5, 'unobtainium')

    def test_solution_serialisable(self):
        sol = _merlin()
        d = sol.to_dict()
        assert isinstance(d, dict)
        assert d['cycle_type'] == 'gas_generator'
        assert 'assumptions' in d and d['assumptions']


class TestPreburnerSolver:
    def test_fuel_rich_roundtrip(self):
        pb = solve_preburner_of('methane', 'lox', 500.0, 900.0, 'fuel_rich')
        assert pb['status'] == 'solved'
        assert pb['gas']['temperature_K'] == pytest.approx(900.0, abs=0.5)
        assert 0.05 < pb['mr'] < 1.0

    def test_ox_rich_roundtrip(self):
        pb = solve_preburner_of('methane', 'lox', 500.0, 750.0, 'ox_rich')
        assert pb['status'] == 'solved'
        assert pb['gas']['temperature_K'] == pytest.approx(750.0, abs=0.5)
        assert pb['mr'] > 10.0

    def test_unreachable_temperature_clamps_with_warning(self):
        pb = solve_preburner_of('methane', 'lox', 100.0, 200.0, 'fuel_rich')
        assert pb['status'] == 'clamped'
        assert pb['warnings']

    def test_frozen_gas_properties_are_consistent(self):
        pb = solve_preburner_of('rp1', 'lox', 100.0, 1000.0, 'fuel_rich')
        gas = pb['gas']
        # γ = cp/(cp − R/MW) tutarlılığı (termik mükemmel gaz bağıntısı).
        from hrma.constants import R_UNIVERSAL
        r_sp = R_UNIVERSAL / gas['molecular_weight']
        assert gas['gamma'] == pytest.approx(
            gas['cp_J_kgK'] / (gas['cp_J_kgK'] - r_sp), rel=1e-9)
        assert 1.05 < gas['gamma'] < 1.45


class TestDataclassContract:
    def test_defaults_are_honest(self):
        sol = CycleSolution(cycle_type='gas_generator')
        assert not sol.converged
        assert sol.isp_mode == 'not_modelled'
        assert sol.isp_loss_s is None
