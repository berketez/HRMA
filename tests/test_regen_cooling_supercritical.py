"""
Tests for the supercritical methane / hydrogen coolant path of the 1D
regenerative-cooling module (regen_cooling).

Independent anchors (sources cited per test):
  - CoolProp (Bell et al. 2014): CH4 EOS Setzmann & Wagner (1991),
    hydrogen as PARA-hydrogen (Leachman et al. 2009). CH4 liquid density at
    150 K / 100 bar ~ 376 kg/m^3 (CoolProp 6.8; the classical engineering
    band is ~380-420 — the EOS value is taken as the reference here, the
    test asserts module<->CoolProp consistency plus a generous band).
  - Pseudo-critical cp peak: CH4 at 100 bar has T_pc ~ 218 K (cp maximum);
    hence cp(300 K) < cp(250 K) at 100 bar (past the peak).
  - Jackson correlation (Jackson & Hall 1979; Jackson 2013, NED 264):
        Nu = 0.0183 Re^0.82 Pr^0.5 (rho_w/rho_b)^0.3 (cp_bar/cp_b)^n
    with the piecewise n exponent — regime values and continuity are
    hand-checkable.
  - Fin area ratio (Incropera 6th ed. Ch. 3.6; Huzel & Huang Ch. 4):
        eta = tanh(mL)/(mL), m = sqrt(2 h_c/(k_w t_land)),
        A_ratio = (w + 2 eta h)/pitch.
  - Acceleration pressure drop (Collier & Thome 3rd ed. Ch. 2):
        dP_acc = G^2 (1/rho_out - 1/rho_in);
    G=1000, rho 500->250 gives exactly 2000 Pa.
  - Energy conservation: with the enthalpy march, total heat must equal
    mdot*(h_out - h_in) to machine precision.

Run:
    cd <depo kökü>
    MPLBACKEND=Agg python3 -m pytest tests/test_regen_cooling_supercritical.py -v
"""

import math

import numpy as np
import pytest

pytest.importorskip('CoolProp')
from CoolProp.CoolProp import PropsSI

from hrma.analysis.regen_cooling import (
    RegenCooling,
    jackson_nu,
    jackson_exponent_n,
    pseudocritical_temperature,
    acceleration_dp,
    fin_area_ratio,
    SUPERCRITICAL_COOLANT_FLUIDS,
)


# ======================================================================
# Ortak fikstürler
# ======================================================================
def make_methane(**overrides):
    """Orta ölçekli, hızlı çözülen süperkritik metan temel durumu."""
    kwargs = dict(
        chamber_pressure=100e5,
        chamber_temperature=3400.0,
        gamma=1.17,
        molecular_weight=22.0,
        throat_diameter=0.05,
        expansion_ratio=6.0,
        coolant='methane',
        coolant_mdot=6.0,
        coolant_inlet_temp=110.0,
        coolant_inlet_pressure=150e5,
        n_channels=80,
        channel_width=1.5e-3,
        channel_height=3.0e-3,
        wall_thickness=0.8e-3,
        wall_material='cucrzr',
        n_stations=30,
    )
    kwargs.update(overrides)
    return RegenCooling(**kwargs)


def make_raptor(**overrides):
    """Raptor mertebesi senaryo: Pc=300 bar, boğaz 0.22 m, tam yakıt debisi.

    Soğutucu debisi 120 kg/s: Raptor sınıfı bir motorda TÜM yakıt akışı
    (~140 kg/s CH4, mdot_toplam ~650 / (1+O/F 3.6)) ceketten geçer — 600
    kg/s değil. Giriş basıncı 600 bar: denetim raporunun kendisi Raptor
    pompa çıkışını 700-800 bar olarak verir (rejeneratif ΔP zinciri);
    kanal boyunca basınç ~300-600 bar bandında kalır. Ceket ε=6'ya kadar
    (rejeneratif bölüm; büyük ε bölgesi ayrı devre/ışınım sorunu).
    """
    kwargs = dict(
        chamber_pressure=300e5,
        chamber_temperature=3600.0,
        gamma=1.15,
        molecular_weight=23.0,
        throat_diameter=0.22,
        expansion_ratio=6.0,
        coolant='methane',
        coolant_mdot=120.0,
        coolant_inlet_temp=110.0,
        coolant_inlet_pressure=600e5,
        n_channels=320,
        channel_width=1.5e-3,
        channel_height=5.0e-3,
        wall_thickness=0.5e-3,
        wall_material='cucrzr',
        n_stations=40,
    )
    kwargs.update(overrides)
    return RegenCooling(**kwargs)


# ======================================================================
# 1) CoolProp akıl sağlığı çapaları (görev şartındaki doğrulamalar)
# ======================================================================
class TestCoolPropSanity:

    def test_ch4_liquid_density_150K_100bar(self):
        # Setzmann & Wagner EOS (CoolProp): ~376 kg/m^3. Modül CoolProp ile
        # BİREBİR tutarlı olmalı; bant genel mühendislik aralığı.
        r = make_methane()
        p = r._coolant_properties(150.0, 100e5)
        ref = PropsSI('D', 'T', 150.0, 'P', 100e5, 'Methane')
        assert p['density'] == pytest.approx(ref, rel=1e-9)
        assert 350.0 < p['density'] < 430.0
        assert p['source'] == 'coolprop'

    def test_ch4_cp_past_pseudocritical_peak(self):
        # 100 bar'da T_pc ~ 218 K: cp(300 K) tepe SONRASI, cp(250 K)'den küçük.
        r = make_methane()
        cp_250 = r._coolant_properties(250.0, 100e5)['cp']
        cp_300 = r._coolant_properties(300.0, 100e5)['cp']
        assert cp_300 < cp_250
        # Değerler CoolProp'la birebir
        assert cp_250 == pytest.approx(
            PropsSI('C', 'T', 250.0, 'P', 100e5, 'Methane'), rel=1e-9)

    def test_pseudocritical_temperature_ch4(self):
        # cp maksimumu: 100 bar'da ~218 K (ölçüldü); basınçla artar.
        t_pc_100 = pseudocritical_temperature('Methane', 100e5)
        assert 200.0 < t_pc_100 < 240.0
        t_pc_60 = pseudocritical_temperature('Methane', 60e5)
        assert t_pc_60 < t_pc_100

    def test_pseudocritical_requires_supercritical_pressure(self):
        # Kritik altı basınçta T_pc tanımsız — açık hata (Tsat kullanılmalı).
        with pytest.raises(ValueError):
            pseudocritical_temperature('Methane', 30e5)

    def test_enthalpy_in_properties(self):
        r = make_methane()
        p = r._coolant_properties(200.0, 150e5)
        assert p['enthalpy'] == pytest.approx(
            PropsSI('Hmass', 'T', 200.0, 'P', 150e5, 'Methane'), rel=1e-9)


# ======================================================================
# 2) Girdi doğrulama ve açık-hata politikası
# ======================================================================
class TestValidation:

    def test_methane_rejects_table_source(self):
        # Dahili tablo YOK — sabit değer uydurulamaz, açık hata.
        with pytest.raises(ValueError):
            make_methane(coolant_props_source='table')

    def test_unknown_coolant_message_lists_options(self):
        with pytest.raises(ValueError) as exc:
            make_methane(coolant='mercury')
        assert 'methane' in str(exc.value)

    def test_coolant_aliases(self):
        assert make_methane(coolant='CH4').coolant == 'methane'
        assert make_methane(coolant='lch4').coolant == 'methane'
        h2 = make_methane(coolant='LH2', coolant_inlet_temp=40.0,
                          coolant_inlet_pressure=300e5)
        assert h2.coolant == 'hydrogen'

    def test_parahydrogen_fluid_mapping(self):
        # Roket LH2'si para-hidrojendir (Leachman 2009) — normal H2 değil.
        assert SUPERCRITICAL_COOLANT_FLUIDS['hydrogen'] == 'ParaHydrogen'
        assert SUPERCRITICAL_COOLANT_FLUIDS['methane'] == 'Methane'

    def test_inlet_temp_outside_eos_raises(self):
        # CH4 EOS tabanı ~90.7 K — 50 K açık hata (sessiz klamp yok).
        with pytest.raises(ValueError):
            make_methane(coolant_inlet_temp=50.0)


# ======================================================================
# 3) Jackson / fin / ivmelenme yardımcıları — el hesabı çapaları
# ======================================================================
class TestCorrelationHelpers:

    def test_jackson_exponent_regimes(self):
        t_pc = 220.0
        # Cidar T_pc altında -> 0.4
        assert jackson_exponent_n(150.0, 200.0, t_pc) == pytest.approx(0.4)
        # Yığın 1.2*T_pc üstünde -> 0.4
        assert jackson_exponent_n(300.0, 500.0, t_pc) == pytest.approx(0.4)
        # T_b <= T_pc < T_w: n = 0.4 + 0.2*(T_w/T_pc - 1)
        n = jackson_exponent_n(200.0, 260.0, t_pc)
        assert n == pytest.approx(0.4 + 0.2 * (260.0 / 220.0 - 1.0), rel=1e-12)

    def test_jackson_exponent_continuity(self):
        t_pc = 220.0
        # T_b = T_pc sınırında 2. ve 3. bölge aynı değeri vermeli
        n_lo = jackson_exponent_n(t_pc - 1e-9, 300.0, t_pc)
        n_hi = jackson_exponent_n(t_pc + 1e-9, 300.0, t_pc)
        assert n_lo == pytest.approx(n_hi, abs=1e-6)
        # T_b = 1.2*T_pc sınırında 3. bölge 0.4'e iner
        n_edge = jackson_exponent_n(1.2 * t_pc - 1e-9, 300.0, t_pc)
        assert n_edge == pytest.approx(0.4, abs=1e-6)

    def test_jackson_nu_hand_anchor(self):
        # Nu = 0.0183 * Re^0.82 * Pr^0.5 * ratio_rho^0.3 * ratio_cp^n
        re, pr, rr, rc, n = 1.0e6, 1.2, 0.5, 1.5, 0.4
        hand = 0.0183 * re ** 0.82 * pr ** 0.5 * rr ** 0.3 * rc ** n
        assert jackson_nu(re, pr, rr, rc, n) == pytest.approx(hand, rel=1e-12)

    def test_jackson_nu_invalid(self):
        with pytest.raises(ValueError):
            jackson_nu(-1.0, 1.0, 1.0, 1.0, 0.4)
        with pytest.raises(ValueError):
            jackson_nu(1e6, 1.0, 0.0, 1.0, 0.4)

    def test_fin_area_ratio_hand_anchor(self):
        # w=1.5, h=5, pitch=2.2, land=0.7 mm; h_c=1e5, k=320:
        # m = sqrt(2e5/(320*7e-4)); eta = tanh(m*h)/(m*h)
        w, h, p, land, hc, kw = 1.5e-3, 5.0e-3, 2.2e-3, 0.7e-3, 1.0e5, 320.0
        m = math.sqrt(2.0 * hc / (kw * land))
        eta = math.tanh(m * h) / (m * h)
        hand = (w + 2.0 * eta * h) / p
        assert fin_area_ratio(w, h, p, land, hc, kw) == pytest.approx(
            hand, rel=1e-12)
        assert hand > 1.0   # fin alanı gaz alanından büyük

    def test_fin_area_ratio_low_h_limit(self):
        # h_c -> 0: eta -> 1, oran -> (w + 2h)/pitch (tam ıslak çevre)
        w, h, p = 1.0e-3, 4.0e-3, 2.0e-3
        ratio = fin_area_ratio(w, h, p, 1.0e-3, 1.0e-2, 320.0)
        assert ratio == pytest.approx((w + 2.0 * h) / p, rel=1e-3)

    def test_acceleration_dp_hand_anchor(self):
        # G=1000, rho 500 -> 250: dP = 1e6*(1/250 - 1/500) = 2000 Pa
        assert acceleration_dp(1000.0, 500.0, 250.0) == pytest.approx(
            2000.0, rel=1e-12)

    def test_acceleration_dp_sign_and_invalid(self):
        # Yoğunlaşan akış -> negatif (basınç geri kazanımı)
        assert acceleration_dp(1000.0, 250.0, 500.0) < 0.0
        with pytest.raises(ValueError):
            acceleration_dp(1000.0, 0.0, 250.0)


# ======================================================================
# 4) Enerji korunumu (entalpi marşı)
# ======================================================================
class TestEnergyConservation:

    def test_total_heat_equals_enthalpy_rise(self):
        # Q_toplam = mdot * (h_out - h_in) — entalpi marşında makine hassasiyeti
        r = make_methane()
        s = r.solve()['summary']
        q = s['total_heat_W']
        dh = s['coolant_exit_enthalpy_J_kg'] - s['coolant_inlet_enthalpy_J_kg']
        assert q == pytest.approx(6.0 * dh, rel=1e-9)

    def test_surface_integral_reconstruction(self):
        # Q_toplam'ı q(x) ve ıslak alandan BAĞIMSIZ yeniden kur (counterflow).
        r = make_methane()
        res = r.solve()
        n = res['n_stations']
        x_m = np.array(res['x_mm']) / 1e3
        r_m = np.array(res['r_mm']) / 1e3
        q = np.array(res['q_MW_m2']) * 1e6
        order = list(range(n - 1, -1, -1))
        Q = 0.0
        for k in range(len(order) - 1):
            i, j = order[k], order[k + 1]
            ds = math.hypot(x_m[j] - x_m[i], r_m[j] - r_m[i])
            Q += q[i] * 2.0 * math.pi * 0.5 * (r_m[i] + r_m[j]) * ds
        assert Q == pytest.approx(res['summary']['total_heat_W'], rel=1e-9)

    def test_exit_state_roundtrip(self):
        # T_out, (P_out, h_out) durumundan türetildi — CoolProp ile kapanmalı.
        r = make_methane()
        s = r.solve()['summary']
        t_rt = PropsSI('T', 'P', s['coolant_exit_pressure_bar'] * 1e5,
                       'Hmass', s['coolant_exit_enthalpy_J_kg'],
                       'Methane')
        assert t_rt == pytest.approx(s['coolant_exit_temp_K'], rel=1e-6)

    def test_inlet_enthalpy_matches_coolprop(self):
        r = make_methane()
        s = r.solve()['summary']
        h_ref = PropsSI('Hmass', 'T', 110.0, 'P', 150e5, 'Methane')
        assert s['coolant_inlet_enthalpy_J_kg'] == pytest.approx(h_ref, rel=1e-9)

    def test_enthalpy_array_monotonic_along_flow(self):
        # Counterflow: soğutucu x=çıkıştan girer; entalpi x ile AZALMALI.
        res = make_methane().solve()
        h = np.array(res['coolant_enthalpy_kJ_kg'])
        assert np.all(np.diff(h) < 0.0)


# ======================================================================
# 5) Cidar sıcaklığı çözümü
# ======================================================================
class TestWallSolution:

    def test_series_circuit_identity(self):
        # q = h_g*(Taw - T_hot) ve q = h_c*A_fin*(T_cold - T_bulk) her istasyonda
        res = make_methane().solve()
        fin = res['fin_area_ratio']
        for i in range(res['n_stations']):
            q = res['q_MW_m2'][i] * 1e6
            assert q == pytest.approx(
                res['h_gas_W_m2K'][i]
                * (res['T_recovery_K'][i] - res['T_wall_hot_K'][i]), rel=1e-6)
            assert q == pytest.approx(
                res['h_coolant_W_m2K'][i] * fin[i]
                * (res['T_wall_cold_K'][i] - res['T_coolant_K'][i]), rel=1e-6)

    def test_temperature_ordering(self):
        res = make_methane().solve()
        for i in range(res['n_stations']):
            assert (res['T_coolant_K'][i] <= res['T_wall_cold_K'][i]
                    <= res['T_wall_hot_K'][i] <= res['T_recovery_K'][i])

    def test_wall_temp_increases_with_heat_flux(self):
        # Oda sıcaklığı (dolayısıyla akı) arttıkça cidar tepe sıcaklığı artar.
        tw = [make_methane(chamber_temperature=tc).solve()
              ['summary']['max_wall_hot_K'] for tc in (3200.0, 3400.0, 3600.0)]
        assert tw[0] < tw[1] < tw[2]

    def test_wall_temp_decreases_with_mdot(self):
        # Soğutucu debisi arttıkça cidar tepe sıcaklığı düşer.
        tw = [make_methane(coolant_mdot=md).solve()
              ['summary']['max_wall_hot_K'] for md in (4.0, 6.0, 9.0)]
        assert tw[0] > tw[1] > tw[2]

    def test_fin_effect_reduces_wall_temperature(self):
        # Fin modeli soğutucu tarafı iletkenliği artırır -> cidar soğur.
        t_fin = make_methane().solve()['summary']['max_wall_hot_K']
        t_nofin = make_methane(fin_effect=False).solve()['summary']['max_wall_hot_K']
        assert t_fin < t_nofin

    def test_jackson_correlation_reported(self):
        s = make_methane().solve()['summary']
        assert s['coolant_correlation'] == 'jackson'
        assert s['supercritical_pressure'] is True


# ======================================================================
# 6) Kritik-altı basınç: kaynama riski bayrakları
# ======================================================================
class TestSubcriticalBoiling:

    def make_subcritical(self, **overrides):
        kwargs = dict(
            chamber_pressure=20e5, chamber_temperature=3000.0, gamma=1.2,
            molecular_weight=24.0, throat_diameter=0.03, expansion_ratio=6.0,
            coolant='methane', coolant_mdot=0.8, coolant_inlet_temp=120.0,
            coolant_inlet_pressure=30e5,   # < P_crit(CH4)=46 bar
            n_channels=60, channel_width=1.5e-3, channel_height=3.0e-3,
            wall_thickness=1.0e-3, wall_material='cucrzr', n_stations=30)
        kwargs.update(overrides)
        return RegenCooling(**kwargs)

    def test_subcritical_pressure_warning(self):
        s = self.make_subcritical().solve()['summary']
        assert any('SUBCRITICAL' in w for w in s['warnings'])
        assert s['supercritical_pressure'] is False

    def test_dittus_boelter_fallback(self):
        s = self.make_subcritical().solve()['summary']
        assert 'dittus_boelter' in s['coolant_correlation']

    def test_boiling_risk_flagged(self):
        # Cidar Tsat üstüne çıkar -> kaynama riski uyarısı (BOILING içerir)
        s = self.make_subcritical().solve()['summary']
        assert any('BOILING' in w for w in s['warnings'])


# ======================================================================
# 7) Hidrojen (para-H2) yolu
# ======================================================================
class TestHydrogen:

    def make_h2(self, **overrides):
        kwargs = dict(
            chamber_pressure=200e5, chamber_temperature=3550.0, gamma=1.14,
            molecular_weight=13.5, throat_diameter=0.26, expansion_ratio=6.0,
            coolant='hydrogen', coolant_mdot=30.0, coolant_inlet_temp=40.0,
            coolant_inlet_pressure=450e5, n_channels=400,
            channel_width=1.5e-3, channel_height=4.0e-3,
            wall_thickness=0.7e-3, wall_material='cucrzr', n_stations=40)
        kwargs.update(overrides)
        return RegenCooling(**kwargs)

    def test_hydrogen_solves_supercritical(self):
        s = self.make_h2().solve()['summary']
        assert s['coolant_correlation'] == 'jackson'
        assert s['coolant_exit_temp_K'] > 40.0
        assert s['coolant_exit_pressure_bar'] < 450.0
        # Cidar fiziksel bantta (bakır alaşımı, RS-25 mertebesi)
        assert 600.0 < s['max_wall_hot_K'] < 1200.0

    def test_hydrogen_energy_conservation(self):
        s = self.make_h2().solve()['summary']
        dh = s['coolant_exit_enthalpy_J_kg'] - s['coolant_inlet_enthalpy_J_kg']
        assert s['total_heat_W'] == pytest.approx(30.0 * dh, rel=1e-9)

    def test_hydrogen_properties_match_parahydrogen(self):
        r = self.make_h2()
        p = r._coolant_properties(40.0, 450e5)
        assert p['density'] == pytest.approx(
            PropsSI('D', 'T', 40.0, 'P', 450e5, 'ParaHydrogen'), rel=1e-9)


# ======================================================================
# 8) Raptor mertebesi senaryo (görev doğrulaması)
# ======================================================================
class TestRaptorScale:

    @pytest.fixture(scope='class')
    def raptor(self):
        return make_raptor().solve()

    def test_converged_everywhere(self, raptor):
        # Kuple cidar dengesi tüm istasyonlarda yakınsadı (uyarı yok).
        assert not any('CONVERGENCE' in w
                       for w in raptor['summary']['warnings'])

    def test_throat_heat_flux_order(self, raptor):
        # Raptor boğaz akısı literatür mertebesi ~80-120 MW/m^2 (denetim
        # raporu); Bartz + soğuk cidar ile ~110-135 çıkar — bant 60-140.
        q_peak = raptor['summary']['peak_heat_flux_MW_m2']
        assert 60.0 < q_peak < 140.0
        # Tepe akı boğaz civarında
        q = np.array(raptor['q_MW_m2'])
        assert abs(int(np.argmax(q)) - raptor['throat_index']) <= 2

    def test_wall_temperature_physical_band(self, raptor):
        # Bakır alaşımı astar için fiziksel bant (görev şartı: 700-1100 K).
        t_wall = raptor['summary']['max_wall_hot_K']
        assert 700.0 <= t_wall <= 1100.0

    def test_pressure_budget(self, raptor):
        s = raptor['summary']
        # Basınç düşer ama kanal süperkritik kalır (P_out > P_crit = 46 bar)
        assert s['coolant_exit_pressure_bar'] < 600.0
        assert s['coolant_exit_pressure_bar'] * 1e5 > 46e5
        # Sürtünme + ivmelenme ayrışımı tutarlı ve pozitif
        assert s['pressure_drop_friction_bar'] > 0.0
        assert s['pressure_drop_acceleration_bar'] > 0.0
        assert s['total_pressure_drop_bar'] == pytest.approx(
            s['pressure_drop_friction_bar']
            + s['pressure_drop_acceleration_bar'], rel=1e-9)

    def test_exit_temperature_within_eos(self, raptor):
        # Çıkış sıcaklığı fiziksel ve EOS içinde (CH4 Tmax = 625 K).
        t_out = raptor['summary']['coolant_exit_temp_K']
        assert 150.0 < t_out < 625.0

    def test_velocity_engineering_band(self, raptor):
        # Kanal hızı mühendislik bandında (süperkritik yoğun akış, < 400 m/s)
        assert raptor['summary']['max_coolant_velocity_m_s'] < 400.0

    def test_fin_ratio_reported(self, raptor):
        fin = np.array(raptor['fin_area_ratio'])
        assert np.all(fin >= 1.0)
        assert raptor['summary']['fin_area_ratio_max'] == pytest.approx(
            float(np.max(fin)), rel=1e-12)


# ======================================================================
# 9) Eski (su/RP-1) yol regresyonu — API kararlılığı
# ======================================================================
class TestLegacyPathUnchanged:

    def make_water(self, **overrides):
        kwargs = dict(
            chamber_pressure=20e5, chamber_temperature=3000.0, gamma=1.2,
            molecular_weight=24.0, throat_diameter=0.03, expansion_ratio=6.0,
            coolant='water', coolant_mdot=6.0, coolant_inlet_temp=300.0,
            coolant_inlet_pressure=40e5, n_channels=60, channel_width=1.5e-3,
            channel_height=3.0e-3, wall_thickness=1.0e-3,
            wall_material='cucrzr', n_stations=30,
            coolant_props_source='table')
        kwargs.update(overrides)
        return RegenCooling(**kwargs)

    def test_water_summary_new_keys_are_none(self):
        s = self.make_water().solve()['summary']
        assert s['coolant_correlation'] == 'dittus_boelter'
        assert s['coolant_critical_pressure_bar'] is None
        assert s['coolant_pseudocritical_T_K'] is None
        assert s['coolant_inlet_enthalpy_J_kg'] is None
        assert s['supercritical_pressure'] is None
        assert s['fin_effect'] is None

    def test_water_no_acceleration_term(self):
        # Eski yol: ivmelenme terimi uygulanmaz; sürtünme = toplam.
        s = self.make_water().solve()['summary']
        assert s['pressure_drop_acceleration_bar'] == 0.0
        assert s['pressure_drop_friction_bar'] == pytest.approx(
            s['total_pressure_drop_bar'], rel=1e-9)

    def test_water_no_supercritical_arrays(self):
        res = self.make_water().solve()
        assert 'coolant_enthalpy_kJ_kg' not in res
        assert 'fin_area_ratio' not in res

    def test_fin_effect_flag_does_not_touch_water(self):
        # Su yolunda fin_effect parametresi sonucu DEĞİŞTİRMEZ (sözleşme).
        s_on = self.make_water(fin_effect=True).solve()['summary']
        s_off = self.make_water(fin_effect=False).solve()['summary']
        assert s_on['total_heat_W'] == pytest.approx(
            s_off['total_heat_W'], rel=1e-12)
        assert s_on['max_wall_hot_K'] == pytest.approx(
            s_off['max_wall_hot_K'], rel=1e-12)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
