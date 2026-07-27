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
    ETA_TURBINE_CLOSED_DEFAULT,
    ETA_TURBINE_OPEN_DEFAULT,
    STAGED_PR_TYPICAL,
    solve_cycle,
    solve_preburner_of,
)

RESIDUAL_TOL = 1e-6


def _codes(items):
    """Uyarı/varsayım listesinden kod kümesi çıkarır.

    v2.6.2'de uyarı sözleşmesi düz metinden ``{code, params, severity}``
    sözlüğüne geçti (``_w()``); eski düz metin biçimi de kabul edilir.
    """
    out = set()
    for w in items or []:
        if isinstance(w, dict) and w.get('code'):
            out.add(w['code'])
        elif isinstance(w, str):
            out.add(w)
    return out


def _params_of(items, code):
    """Belirli bir kodun parametre sözlüğünü döndürür (yoksa boş sözlük)."""
    for w in items or []:
        if isinstance(w, dict) and w.get('code') == code:
            return w.get('params') or {}
    return {}

# Görev doğrulama çapaları için sabit yoğunluklar (NBP; NIST WebBook).
RHO_LOX = 1141.0
RHO_CH4 = 422.0
RHO_LH2 = 70.85


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
        """Büyük motor + yetersiz ısı alımı: expander doğal güç sınırı.

        v2.6.2 uyarı sözleşmesi güncellemesi: eskiden ``'power limit' in w``
        şeklinde İngilizce metin aranıyordu; uyarılar artık
        ``{code, params, severity}`` sözlüğü. Metin yerine KOD ve sayısal
        parametreler sınanır (metin frontend'de i18n ile kurulur).
        """
        sol = solve_cycle('expander', 200.0, 600.0, 3.6, 'methane',
                          regen_dp_bar=40.0, regen_heat_kw=20000.0)
        assert not sol.converged
        assert 'power_balance' in sol.not_modelled
        code = 'warn.cycle.expander_power_balance_infeasible'
        assert code in _codes(sol.warnings)
        p = _params_of(sol.warnings, code)
        # Güç açığı sayıyla raporlanmalı (sahte yakınsama değil).
        assert p['deficit_mw'] > 0.0
        assert p['pump_power_mw'] > 0.0
        assert p['regen_heat_kw'] == pytest.approx(20000.0)

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
        assert any(w['code'] == 'warn.cycle.pressure_fed_infeasible'
                   for w in sol.warnings)

    def test_pressure_fed_positive_margin_converges(self):
        sol = solve_cycle('pressure_fed', 20.0, 5.0, 2.1, 'rp1',
                          tank_pressure_bar=35.0)
        assert sol.converged
        assert sol.tank_pressure_margin_bar > 0.0
        assert sol.pump_power_total_W == 0.0

    def test_excessive_tit_warns(self):
        sol = solve_cycle('gas_generator', 97.0, 305.0, 2.36, 'rp1',
                          tit_K=1250.0, isp_main_s=282.0)
        assert any(w['code'] == 'warn.cycle.tit_exceeds_uncooled'
                   for w in sol.warnings)

    def test_ox_rich_lh2_warns(self):
        sol = solve_cycle('staged_combustion', 200.0, 500.0, 6.0, 'lh2',
                          preburner_mode='ox_rich')
        assert any(w['code'] == 'warn.cycle.ox_rich_lh2_no_precedent'
                   for w in sol.warnings)

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


class TestTurbineEfficiencyDefault:
    """Türbin verimi çevrim SINIFINA göre varsayılmalı (NASA SP-8110).

    Açık çevrim (yüksek PR, kısmi-giriş impuls) 0.65; kapalı çevrim (düşük PR,
    tam-giriş reaksiyon) 0.78. Tek bir 0.65 değeri kapalı yüksek-Pc çevrimde
    türbin gücünü eksik hesaplar ve dengeyi yalancı olarak açık bırakırdı.
    """

    def test_closed_default_above_open_default(self):
        # Fiziksel sıralama: kapalı çevrim türbini açık çevrimden verimli.
        assert ETA_TURBINE_CLOSED_DEFAULT > ETA_TURBINE_OPEN_DEFAULT
        # RS-25 ölçülen bandı (HPOTP 0.746 - HPFTP 0.811) içinde.
        assert 0.746 <= ETA_TURBINE_CLOSED_DEFAULT <= 0.811

    def test_open_cycle_uses_open_default_when_unset(self):
        """v2.6.2: varsayım metni yerine KOD sınanır (uyarı sözleşmesi)."""
        sol = solve_cycle('gas_generator', 97.0, 305.0, 2.36, 'rp1',
                          isp_main_s=282.0)
        assert sol.converged
        assert (sol.shafts[0]['turbine']['efficiency']
                == pytest.approx(ETA_TURBINE_OPEN_DEFAULT))
        code = 'warn.cycle.turbine_eff_open_assumed'
        assert code in _codes(sol.assumptions)
        assert _params_of(sol.assumptions, code)['eta'] == pytest.approx(
            ETA_TURBINE_OPEN_DEFAULT)

    def test_closed_cycle_uses_closed_default_when_unset(self):
        """v2.6.2: varsayım metni yerine KOD sınanır (uyarı sözleşmesi)."""
        sol = solve_cycle('staged_combustion', 206.0, 470.0, 6.0, 'lh2',
                          rho_ox=RHO_LOX, rho_fuel=RHO_LH2)
        assert sol.converged
        assert (sol.shafts[0]['turbine']['efficiency']
                == pytest.approx(ETA_TURBINE_CLOSED_DEFAULT))
        code = 'warn.cycle.turbine_eff_closed_assumed'
        assert code in _codes(sol.assumptions)
        assert _params_of(sol.assumptions, code)['eta'] == pytest.approx(
            ETA_TURBINE_CLOSED_DEFAULT)

    def test_explicit_efficiency_is_honoured(self):
        # Kullanıcı değeri varsayılanı EZMELİ (sessizce değiştirilmez).
        sol = solve_cycle('staged_combustion', 206.0, 470.0, 6.0, 'lh2',
                          rho_ox=RHO_LOX, rho_fuel=RHO_LH2, eta_turbine=0.60)
        assert sol.shafts[0]['turbine']['efficiency'] == pytest.approx(0.60)


class TestHighPcConvergence:
    """Görev senaryosu: yüksek oda basıncında (300 bar) çevrim dengesi.

    Raptor sınıfı FFSC (metan/LOX, Pc=300 bar) fiziksel olarak KAPANMALI ve
    pompa çıkışları literatür bandında (600-850 bar) SONUÇ olarak çıkmalı.
    Tek ön yakıcılı staged combustion aynı noktada fiziksel olarak kapanmaz
    (türbinden geçen debi sınırlı) — bu durumda sahte sayı değil, dürüst
    'not_modelled' dönmeli.
    """

    def test_ffsc_methane_300bar_converges_bare_defaults(self):
        # Görevin birebir yeniden üretim çağrısı (eta_turbine verilmez).
        sol = solve_cycle('full_flow_staged_combustion', 300.0, 700.0, 3.6,
                          'methane', 'lox', rho_ox=RHO_LOX, rho_fuel=RHO_CH4)
        assert sol.converged
        assert sol.power_residual_rel < RESIDUAL_TOL
        # Pompa çıkışları Raptor bandında (SONUÇ, hardcode değil).
        assert 600.0 <= sol.pump_discharge_ox_bar <= 850.0
        assert 600.0 <= sol.pump_discharge_fuel_bar <= 850.0
        # İki mil, iki ön yakıcı, tüm debi türbinlerden geçer.
        assert {s['name'] for s in sol.shafts} == {'fuel', 'ox'}
        assert sol.turbine_mdot_total_kg_s == pytest.approx(700.0, rel=1e-6)

    def test_ffsc_methane_300bar_shaft_balance_closes(self):
        sol = solve_cycle('full_flow_staged_combustion', 300.0, 700.0, 3.6,
                          'methane', 'lox', rho_ox=RHO_LOX, rho_fuel=RHO_CH4)
        for shaft in sol.shafts:
            assert shaft['power_residual_rel'] < RESIDUAL_TOL
            assert shaft['turbine']['efficiency'] == pytest.approx(
                ETA_TURBINE_CLOSED_DEFAULT)

    def test_single_preburner_staged_methane_300bar_honest_not_modelled(self):
        """Tek fuel-rich ön yakıcı 300 bar metanı kapatamaz — bu FIZIKSEL.

        Sahte yakınsama YASAK; dürüst 'not_modelled' + sayısal gerekçe.
        v2.6.2 uyarı sözleşmesi: eskiden ``' '.join(sol.warnings)`` ile
        İngilizce metinde 'does not close' / 'MW' / 'full-flow' aranıyordu;
        uyarılar artık sözlük olduğu için join TypeError veriyordu. Aynı
        gerekçe artık KOD + sayısal parametrelerle sınanır: sınırlı türbin
        debisi (mdot_turb < mdot_total) ve güç açığı (deficit_mw).
        """
        sol = solve_cycle('staged_combustion', 300.0, 700.0, 3.6, 'methane',
                          'lox', rho_ox=RHO_LOX, rho_fuel=RHO_CH4)
        assert not sol.converged
        assert 'power_balance' in sol.not_modelled
        assert sol.pump_discharge_ox_bar is None
        assert sol.pump_discharge_fuel_bar is None
        code = 'warn.cycle.staged_power_balance_infeasible'
        assert code in _codes(sol.warnings)
        p = _params_of(sol.warnings, code)
        # Sayısal gerekçe: güç açığı + türbinden geçen SINIRLI debi payı.
        assert p['deficit_mw'] > 0.0
        assert p['mdot_total'] == pytest.approx(700.0, rel=1e-9)
        assert 0.0 < p['mdot_turb'] < p['mdot_total']
        assert p['turb_frac'] == pytest.approx(
            p['mdot_turb'] / p['mdot_total'], rel=1e-9)
        assert p['preburner_mode'] == 'fuel_rich'

    def test_open_cycle_unaffected_by_closed_default(self):
        # GG (açık çevrim) yeni kapalı-çevrim varsayılanından ETKİLENMEZ.
        sol = solve_cycle('gas_generator', 97.0, 305.0, 2.36, 'rp1',
                          isp_main_s=282.0)
        assert sol.converged
        assert sol.shafts[0]['turbine']['efficiency'] == pytest.approx(
            ETA_TURBINE_OPEN_DEFAULT)


class TestHighPcRegressionAnchors:
    """Düşük/orta Pc durumları yakınsamaya DEVAM etmeli (regresyon çapası).

    Verim düzeltmesi sadece kapanmayan yüksek-Pc durumu açar; çalışan
    durumları BOZMAMALI. Sayılar hafifçe değişir (doğru, daha yüksek türbin
    verimi -> biraz düşük basınç oranı) ama makul bantta kalır.
    """

    ANCHORS = [
        ('staged_combustion', 50.0, 120.0, 3.6, 'methane', RHO_CH4, 60.0, 90.0),
        ('full_flow_staged_combustion', 50.0, 120.0, 3.6, 'methane', RHO_CH4,
         55.0, 90.0),
        ('staged_combustion', 100.0, 250.0, 3.6, 'methane', RHO_CH4, 130.0,
         200.0),
        ('full_flow_staged_combustion', 100.0, 250.0, 3.6, 'methane', RHO_CH4,
         120.0, 190.0),
    ]

    @pytest.mark.parametrize('cyc,pc,mdot,mr,fuel,rho_f,lo,hi', ANCHORS)
    def test_low_mid_pc_still_converges(self, cyc, pc, mdot, mr, fuel, rho_f,
                                        lo, hi):
        sol = solve_cycle(cyc, pc, mdot, mr, fuel, 'lox', rho_ox=RHO_LOX,
                          rho_fuel=rho_f)
        assert sol.converged
        assert sol.power_residual_rel < RESIDUAL_TOL
        assert lo <= sol.pump_discharge_ox_bar <= hi
        assert lo <= sol.pump_discharge_fuel_bar <= hi

    def test_rs25_like_206bar_stays_in_band(self):
        # 206 bar LH2 staged (RS-25 çapası) yakınsamaya devam eder ve gerçek
        # HPFTP çıkışı (~410 bar, 5950 psia) bandında kalır. Doğru türbin
        # verimiyle (0.78) değer 419 -> ~378 bar'a iner; ikisi de gerçek
        # 410 bar'ın ±%15'i içindedir.
        sol = solve_cycle('staged_combustion', 206.0, 470.0, 6.0, 'lh2',
                          'lox', rho_ox=RHO_LOX, rho_fuel=RHO_LH2)
        assert sol.converged
        assert 350.0 <= sol.pump_discharge_fuel_bar <= 480.0
        pr = sol.shafts[0]['turbine']['pressure_ratio']
        assert STAGED_PR_TYPICAL[0] <= pr <= STAGED_PR_TYPICAL[1]

    def test_rs25_explicit_efficiency_test_anchor_unchanged(self):
        # Test paketinin RS-25 çapası eta_turbine=0.75 AÇIKÇA geçtiği için
        # varsayılan değişiminden ETKİLENMEZ (fuel çıkışı band içinde kalır).
        sol = solve_cycle('staged_combustion', 206.4, 512.0, 6.03, 'lh2',
                          preburner_mode='fuel_rich', regen_dp_bar=30.0,
                          eta_pump_ox=0.75, eta_pump_fuel=0.75,
                          eta_turbine=0.75, tit_K=1000.0)
        assert sol.converged
        assert 450.0 * 0.7 <= sol.pump_discharge_fuel_bar <= 480.0 * 1.3


class TestExpanderRealGasTurbine:
    """v2.6.2 fizik denetimi, bulgu F010: expander türbini GERÇEK GAZ işi.

    Expander çevriminde türbin akışkanı yoğun süperkritik itici buharıdır
    (CH4 ~277 K / 133 bar; H2 40-130 K / 45-70 bar). Termik mükemmel gaz
    bağıntısı γ = cp/(cp−R) bu rejimde geçersizdir; türbin işi izentropik
    entalpi düşümünden (CoolProp 6.8.0, NIST REFPROP tabanlı EOS'lar)
    alınmalıdır. Sayısal çapalar denetim kataloğunun ölçümleridir.
    """

    # Katalog noktası: metan expander çözüm noktası (TIT=276.8 K,
    # p_in=132.7 bar, PR=1.923, eta_t=0.78).
    CH4_T, CH4_P, CH4_PR, ETA = 276.8, 132.7e5, 1.923, 0.78

    @staticmethod
    def _perfect_gas_dh(fluid, mw, t_K, p_Pa, pr, eta):
        """Eski (hatalı) termik mükemmel gaz işi — karşılaştırma tabanı."""
        import CoolProp.CoolProp as CP
        from hrma.constants import R_UNIVERSAL
        from hrma.engines.cycle_power_balance import _turbine_specific_work
        cp = float(CP.PropsSI('C', 'T', t_K, 'P', p_Pa, fluid))
        r_sp = R_UNIVERSAL / mw
        gas = {'cp_J_kgK': cp, 'gamma': cp / (cp - r_sp)}
        return _turbine_specific_work(gas, t_K, pr, eta)

    def test_dense_methane_real_gas_work_matches_audit_anchor(self):
        # Katalog ölçümü: gerçek gaz izentropik düşüm ~48.8 kJ/kg.
        from hrma.engines.cycle_power_balance import _turbine_work_real_gas
        dh, t_exit = _turbine_work_real_gas('Methane', self.CH4_T, self.CH4_P,
                                            self.CH4_PR, self.ETA)
        assert dh == pytest.approx(48.8e3, rel=0.02)
        # Genişleme soğutur; çıkış girişten düşük ama fiziksel bantta.
        assert 200.0 < t_exit < self.CH4_T

    def test_perfect_gas_formula_overestimates_dense_methane(self):
        # Katalog ölçümü: eski bağıntı aynı noktada ~69.8 kJ/kg -> +%43 FAZLA.
        from hrma.engines.cycle_power_balance import _turbine_work_real_gas
        dh_perfect = self._perfect_gas_dh('Methane', 16.043, self.CH4_T,
                                          self.CH4_P, self.CH4_PR, self.ETA)
        dh_real, _ = _turbine_work_real_gas('Methane', self.CH4_T, self.CH4_P,
                                            self.CH4_PR, self.ETA)
        assert dh_perfect == pytest.approx(69.8e3, rel=0.02)
        assert (dh_perfect - dh_real) / dh_real > 0.35

    def test_real_gamma_far_from_thermally_perfect_in_dense_regime(self):
        # Katalog ölçümü: gamma_kod=1.17 vs gerçek cp/cv=2.02 (CH4 133 bar).
        import CoolProp.CoolProp as CP
        from hrma.constants import R_UNIVERSAL
        cp = CP.PropsSI('C', 'T', self.CH4_T, 'P', self.CH4_P, 'Methane')
        cv = CP.PropsSI('O', 'T', self.CH4_T, 'P', self.CH4_P, 'Methane')
        r_sp = R_UNIVERSAL / 16.043
        assert cp / (cp - r_sp) == pytest.approx(1.17, abs=0.02)
        assert cp / cv == pytest.approx(2.02, abs=0.05)

    def test_real_gas_reduces_to_perfect_gas_in_ideal_limit(self):
        # Doğrulama: ideal gaz zarfında (CH4 800 K / 5 bar, Tr~4.2) iki
        # formül aynı sonucu vermeli (<%0.5 fark). Yanma gazı dallarının
        # mükemmel gaz bağıntısını korumasının gerekçesi de budur.
        from hrma.engines.cycle_power_balance import _turbine_work_real_gas
        dh_perfect = self._perfect_gas_dh('Methane', 16.043, 800.0, 5e5,
                                          1.9, self.ETA)
        dh_real, _ = _turbine_work_real_gas('Methane', 800.0, 5e5, 1.9,
                                            self.ETA)
        assert dh_real == pytest.approx(dh_perfect, rel=0.005)

    def test_exit_temperature_energy_consistent(self):
        # Δh_gerçek = h(T_in,p_in) − h(T_exit,p_out) birebir kapanmalı.
        import CoolProp.CoolProp as CP
        from hrma.engines.cycle_power_balance import _turbine_work_real_gas
        dh, t_exit = _turbine_work_real_gas('Methane', self.CH4_T, self.CH4_P,
                                            self.CH4_PR, self.ETA)
        h1 = CP.PropsSI('H', 'T', self.CH4_T, 'P', self.CH4_P, 'Methane')
        h2 = CP.PropsSI('H', 'T', t_exit, 'P', self.CH4_P / self.CH4_PR,
                        'Methane')
        assert h1 - h2 == pytest.approx(dh, rel=1e-6)

    def test_expander_solution_reports_real_gamma_and_flag(self):
        # Çözüm çıktısında gamma GERÇEK cp/cv olmalı ve gerçek gaz modeli
        # varsayım koduyla beyan edilmeli (dürüstlük etiketi).
        sol = _rl10()
        assert sol.converged
        codes = _codes(sol.assumptions)
        assert 'warn.cycle.expander_real_gas_turbine' in codes
        p = _params_of(sol.assumptions, 'warn.cycle.expander_real_gas_turbine')
        gas = sol.shafts[0]['turbine']['gas']
        assert gas['gamma'] == pytest.approx(
            gas['cp_J_kgK'] / gas['cv_J_kgK'], rel=1e-9)
        assert p['gamma_real'] == pytest.approx(gas['gamma'], abs=5e-3)
        # Termik mükemmel değer yalnız karşılaştırma için saklanır.
        assert 'gamma_thermally_perfect' in gas

    def test_marginal_methane_expander_now_honestly_infeasible(self):
        # Eski bağıntı bu noktada işi %43 fazla hesapladığı için denge
        # YALANCI kapanıyordu; gerçek gazla açık kalmalı ve açık sayısal
        # gerekçeyle raporlanmalı (asla-uydurma ilkesi).
        sol = solve_cycle('expander', 60.0, 50.0, 3.4, 'methane',
                          regen_dp_bar=15.0, regen_heat_kw=8000.0,
                          eta_turbine=0.78)
        assert not sol.converged
        assert 'power_balance' in sol.not_modelled
        code = 'warn.cycle.expander_power_balance_infeasible'
        assert code in _codes(sol.warnings)
        assert _params_of(sol.warnings, code)['deficit_mw'] > 0.0
