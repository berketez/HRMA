"""Validation tests for the cylindrical-tank slosh model.

Hand-computed anchors (NASA SP-106 / Dodge 2000):

Reference case R=0.5 m, h=1.0 m, g_eff=9.81 m/s^2, lambda_1=1.8412:
    lambda_1*h/R = 3.6824,  tanh(3.6824) = 0.998733
    omega_1^2 = (1.8412*9.81/0.5)*0.998733 = 36.0786  -> omega_1 = 6.00655 rad/s
    f_1 = 6.00655/(2*pi) = 0.95597 Hz
    m1/m_liq = (2*0.5/(1.8412*1.0*(1.8412^2-1)))*0.998733 = 0.226959
    l_1 = 9.81/36.0786 = 0.271906 m

Asymptotes of the slosh-mass fraction:
    h/R -> 0  :  m1/m_liq -> 2/(lambda_1^2-1) = 0.836814
    h/R -> inf:  m1/m_liq -> 0
"""

import math

import numpy as np
import pytest

from hrma.analysis.slosh_analysis import (
    CylindricalTankSlosh, analyze_slosh, LAMBDA_1, SLOSH_ROOTS, G0,
)


REF = dict(radius=0.5, fill_height=1.0, g_eff=9.81)


class TestFundamentalRelations:
    def test_natural_frequency_hand_calc(self):
        m = CylindricalTankSlosh(**REF)
        omega, f = m.natural_frequency(1)
        assert omega == pytest.approx(6.00655, rel=1e-4)
        assert f == pytest.approx(0.95597, rel=1e-4)

    def test_frequency_matches_closed_form(self):
        m = CylindricalTankSlosh(**REF)
        lam, R, h, g = LAMBDA_1, REF['radius'], REF['fill_height'], REF['g_eff']
        omega_expected = math.sqrt((lam * g / R) * math.tanh(lam * h / R))
        omega, _ = m.natural_frequency(1)
        assert omega == pytest.approx(omega_expected, rel=1e-12)

    def test_slosh_mass_ratio_hand_calc(self):
        m = CylindricalTankSlosh(**REF)
        assert m.slosh_mass_ratio() == pytest.approx(0.226959, rel=1e-4)

    def test_pendulum_length_hand_calc(self):
        m = CylindricalTankSlosh(**REF)
        assert m.pendulum_length() == pytest.approx(0.271906, rel=1e-4)

    def test_pendulum_length_equals_g_over_omega2(self):
        m = CylindricalTankSlosh(**REF)
        omega, _ = m.natural_frequency(1)
        assert m.pendulum_length() == pytest.approx(REF['g_eff'] / omega ** 2,
                                                    rel=1e-12)

    def test_absolute_slosh_mass_with_density(self):
        m = CylindricalTankSlosh(fluid_density=1000.0, **REF)
        m_liq = 1000.0 * math.pi * 0.5 ** 2 * 1.0
        assert m.liquid_mass == pytest.approx(m_liq, rel=1e-9)
        assert m.slosh_mass() == pytest.approx(0.226959 * m_liq, rel=1e-4)

    def test_slosh_mass_none_without_density(self):
        m = CylindricalTankSlosh(**REF)
        assert m.slosh_mass() is None


class TestAsymptotes:
    def test_shallow_limit_mass_ratio(self):
        """h/R -> 0 : m1/m_liq -> 2/(lambda_1^2 - 1) = 0.836814."""
        expected = 2.0 / (LAMBDA_1 ** 2 - 1.0)
        m = CylindricalTankSlosh(radius=0.5, fill_height=1e-4, g_eff=9.81)
        assert m.slosh_mass_ratio() == pytest.approx(expected, rel=1e-3)
        assert expected == pytest.approx(0.836814, rel=1e-4)

    def test_deep_limit_mass_ratio_goes_to_zero(self):
        """h/R -> inf : slosh mass fraction of total liquid -> 0."""
        m = CylindricalTankSlosh(radius=0.5, fill_height=50.0, g_eff=9.81)
        assert m.slosh_mass_ratio() < 0.02

    def test_deep_limit_frequency_independent_of_depth(self):
        """Deep tank: omega^2 -> lambda_1 g / R (tanh -> 1), depth-independent."""
        R, g = 0.5, 9.81
        expected = math.sqrt(LAMBDA_1 * g / R)
        for h in (20.0, 40.0):
            m = CylindricalTankSlosh(radius=R, fill_height=h, g_eff=g)
            omega, _ = m.natural_frequency(1)
            assert omega == pytest.approx(expected, rel=1e-3)

    def test_slosh_mass_always_less_than_liquid(self):
        """m_slosh < m_liquid for every fill level (ratio < 1)."""
        for h in np.linspace(1e-3, 10.0, 40):
            m = CylindricalTankSlosh(radius=0.5, fill_height=float(h), g_eff=9.81)
            assert 0.0 < m.slosh_mass_ratio() < 1.0


class TestMonotonicity:
    def test_frequency_increases_with_fill(self):
        heights = np.linspace(0.05, 3.0, 30)
        freqs = [CylindricalTankSlosh(0.5, float(h), 9.81).natural_frequency(1)[1]
                 for h in heights]
        assert np.all(np.diff(freqs) > 0.0)

    def test_mass_ratio_decreases_with_fill(self):
        heights = np.linspace(0.05, 3.0, 30)
        ratios = [CylindricalTankSlosh(0.5, float(h), 9.81).slosh_mass_ratio()
                  for h in heights]
        assert np.all(np.diff(ratios) < 0.0)

    def test_higher_modes_have_higher_frequency(self):
        m = CylindricalTankSlosh(**REF)
        freqs = [m.natural_frequency(k)[1] for k in range(1, len(SLOSH_ROOTS) + 1)]
        assert np.all(np.diff(freqs) > 0.0)


class TestGEffScaling:
    def test_frequency_scales_with_sqrt_g(self):
        m1 = CylindricalTankSlosh(0.5, 1.0, g_eff=9.81)
        m4 = CylindricalTankSlosh(0.5, 1.0, g_eff=4 * 9.81)
        # omega ~ sqrt(g_eff) -> quadrupling g doubles omega
        assert m4.natural_frequency(1)[0] == pytest.approx(
            2.0 * m1.natural_frequency(1)[0], rel=1e-9)

    def test_default_g_is_standard_gravity(self):
        assert G0 == pytest.approx(9.80665, rel=1e-9)
        m = CylindricalTankSlosh(0.5, 1.0)
        assert m.g_eff == pytest.approx(9.80665, rel=1e-9)


class TestBaffleDamping:
    def test_damping_decreases_with_depth(self):
        m = CylindricalTankSlosh(**REF)
        shallow = m.baffle_damping(width_ratio=0.15, depth_ratio=0.05)
        deep = m.baffle_damping(width_ratio=0.15, depth_ratio=0.5)
        assert shallow['damping_ratio'] > deep['damping_ratio']

    def test_damping_increases_with_width(self):
        m = CylindricalTankSlosh(**REF)
        narrow = m.baffle_damping(width_ratio=0.10, depth_ratio=0.1)
        wide = m.baffle_damping(width_ratio=0.25, depth_ratio=0.1)
        assert wide['damping_ratio'] > narrow['damping_ratio']

    def test_damping_hand_calc(self):
        """Miles Eq. 4: 2.83*exp(-4.60*d)*A^1.5*sqrt(eta/R), A=1-(1-w)^2."""
        m = CylindricalTankSlosh(**REF)
        w, d, eta = 0.2, 0.1, 0.05
        area = 1.0 - (1.0 - w) ** 2
        expected = 2.83 * math.exp(-4.60 * d) * area ** 1.5 * math.sqrt(eta)
        res = m.baffle_damping(width_ratio=w, depth_ratio=d, amplitude_ratio=eta)
        assert res['damping_ratio'] == pytest.approx(expected, rel=1e-9)
        assert res['blocked_area_ratio'] == pytest.approx(area, rel=1e-12)
        assert res['amplitude_ratio'] == pytest.approx(eta)
        assert res['confidence'] == 'approximate'

    def test_amplitude_factor_present(self):
        """sqrt(eta/R) terimi atlanırsa yakalansın — v2.6.2 regresyon bekçisi.

        Terim eksikken kod örtük olarak eta/R = 1 (dalga genligi = tank
        yaricapi) varsayiyordu; bu, modulun ilan ettigi dogrusal kucuk-genlik
        teorisiyle celisir ve sonumlemeyi HER ZAMAN fazla tahmin ediyordu.
        Slosh kararliliginda fazla sonumleme KONSERVATIF DEGILDIR.
        """
        m = CylindricalTankSlosh(**REF)
        lo = m.baffle_damping(0.2, 0.1, amplitude_ratio=0.01)['damping_ratio']
        hi = m.baffle_damping(0.2, 0.1, amplitude_ratio=0.04)['damping_ratio']
        # 4x genlik -> 2x sonumleme (karekok bagimliligi)
        assert hi / lo == pytest.approx(2.0, rel=1e-9)

    def test_single_baffle_damping_physically_plausible(self):
        """Tek halka bafl sonumlemesi olculen banda (~%1-10) dusmeli.

        Genlik terimi eksikken w/R=0.2, d/R=0.1 icin %38.6 cikiyordu.
        """
        m = CylindricalTankSlosh(**REF)
        z = m.baffle_damping(0.2, 0.1)['damping_ratio']
        assert 0.005 <= z <= 0.15, f'tek bafl icin {z:.3f} fiziksel degil'

    def test_amplitude_envelope_flagged(self):
        """Dogrusal teori zarfi disindaki genlik isaretlenmeli."""
        m = CylindricalTankSlosh(**REF)
        assert m.baffle_damping(0.2, 0.1, amplitude_ratio=0.05).get(
            'amplitude_out_of_envelope') is None
        assert m.baffle_damping(0.2, 0.1, amplitude_ratio=0.9).get(
            'amplitude_out_of_envelope') is True

    def test_damping_band_brackets_nominal(self):
        m = CylindricalTankSlosh(**REF)
        res = m.baffle_damping(width_ratio=0.2, depth_ratio=0.1)
        assert res['damping_ratio_low'] < res['damping_ratio'] < res['damping_ratio_high']

    def test_recommend_baffle_reaches_target(self):
        m = CylindricalTankSlosh(**REF)
        target, depth = 0.02, 0.05
        rec = m.recommend_baffle(target_damping=target, depth_ratio=depth)
        # Feed the recommended width back in -> should reproduce the target.
        check = m.baffle_damping(rec['recommended_width_ratio'], depth)
        assert check['damping_ratio'] == pytest.approx(target, rel=1e-6)
        assert rec['achievable_with_single_baffle']

    def test_recommend_baffle_round_trips_at_any_amplitude(self):
        """Oneri ile degerlendirme AYNI genlikte tutarli olmali.

        Genlik terimi yalnizca birinde bulunursa oneri sessizce dar cikar
        (eta/R=0.05'te ~2.8x). Bu test iki yonu birbirine kilitler.
        """
        m = CylindricalTankSlosh(**REF)
        for eta in (0.01, 0.05, 0.1):
            rec = m.recommend_baffle(target_damping=0.02, depth_ratio=0.05,
                                     amplitude_ratio=eta)
            back = m.baffle_damping(rec['recommended_width_ratio'], 0.05,
                                    amplitude_ratio=eta)
            assert back['damping_ratio'] == pytest.approx(0.02, rel=1e-6)
            assert rec['amplitude_ratio'] == pytest.approx(eta)

    def test_smaller_amplitude_needs_wider_baffle(self):
        """Kucuk genlikte ayni sonumleme icin DAHA GENIS bafl gerekir."""
        m = CylindricalTankSlosh(**REF)
        wide = m.recommend_baffle(0.02, 0.05, amplitude_ratio=0.01)
        narrow = m.recommend_baffle(0.02, 0.05, amplitude_ratio=0.10)
        assert wide['recommended_width_ratio'] > narrow['recommended_width_ratio']


class TestFrequencyCoincidence:
    def test_warns_when_control_frequency_near_slosh(self):
        m = CylindricalTankSlosh(**REF)
        f1 = m.natural_frequency(1)[1]  # ~0.956 Hz
        res = m.analyze(control_frequencies=[f1 * 1.05], coincidence_margin=0.20)
        assert res['coincidence_warnings']

    def test_no_warning_when_frequencies_far(self):
        m = CylindricalTankSlosh(**REF)
        res = m.analyze(control_frequencies=[10.0], structural_frequencies=[25.0],
                        coincidence_margin=0.10)
        assert res['coincidence_warnings'] == []


class TestAnalyzeOutput:
    def test_analyze_keys_and_sweep(self):
        res = analyze_slosh(radius=0.5, fill_height=1.0, g_eff=9.81,
                            fluid_density=1000.0)
        for key in ('f1_hz', 'omega1', 'slosh_mass_ratio', 'slosh_mass_kg',
                    'pendulum_length', 'modes', 'fill_sweep', 'baffle',
                    'coincidence_warnings', 'model_note'):
            assert key in res
        sweep = res['fill_sweep']
        assert len(sweep['f1_hz']) == len(sweep['fill_height']) > 0
        assert len(sweep['slosh_mass_ratio']) == len(sweep['fill_height'])

    def test_fill_sweep_skips_nonpositive(self):
        m = CylindricalTankSlosh(**REF)
        sweep = m.fill_sweep([-1.0, 0.0, 0.5, 1.0])
        assert len(sweep['fill_height']) == 2
        assert np.all(sweep['fill_height'] > 0)


class TestValidation:
    @pytest.mark.parametrize("kw", [
        dict(radius=-1.0, fill_height=1.0),
        dict(radius=0.5, fill_height=0.0),
        dict(radius=0.5, fill_height=1.0, g_eff=-9.81),
    ])
    def test_invalid_inputs_raise(self, kw):
        with pytest.raises(ValueError):
            CylindricalTankSlosh(**kw)

    def test_bad_mode_raises(self):
        m = CylindricalTankSlosh(**REF)
        with pytest.raises(ValueError):
            m.natural_frequency(mode=99)

    def test_bad_width_ratio_raises(self):
        m = CylindricalTankSlosh(**REF)
        with pytest.raises(ValueError):
            m.baffle_damping(width_ratio=1.5, depth_ratio=0.1)
