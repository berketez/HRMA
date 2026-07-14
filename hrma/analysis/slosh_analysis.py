"""Propellant slosh (tank sloshing) analysis for upright circular cylindrical tanks.

Linear free-surface slosh dynamics of the propellant in a rigid, vertical
(axis parallel to the acceleration vector) circular cylindrical tank, following
the classical NASA reference literature:

    - Abramson, H.N. (ed.), "The Dynamic Behavior of Liquids in Moving
      Containers", NASA SP-106, 1966, Chapter 2 (Abramson & Bauer, lateral
      sloshing in cylindrical tanks).
    - Dodge, F.T., "The New Dynamic Behavior of Liquids in Moving Containers",
      Southwest Research Institute, 2000 (the SP-106 update), Chapters 1-2, 4.
    - Miles, J.W., "Ring Damping of Free Surface Oscillations in a Circular
      Tank", J. Applied Mechanics 25 (1958) 274-276 (ring-baffle damping).
    - NASA SP-8009, "Propellant Slosh Loads", 1968 (design guidance).

Governing relations (upright circular cylinder, radius R, static liquid depth h,
axial/effective gravity g_eff, first antisymmetric mode).  ``lambda_1 = 1.8412``
is the first root of J1'(x) = 0 (derivative of the first-order Bessel function).

Natural frequency of the n-th antisymmetric slosh mode (SP-106 Eq. 2.4 /
Dodge Eq. 1.13):

    omega_n^2 = (lambda_n * g_eff / R) * tanh(lambda_n * h / R)          (1)

Fundamental-mode (n=1) sloshing-mass fraction of the total liquid mass
(SP-106 equivalent-mechanical-model, Dodge Eq. 1.20; cross-checked against the
Dodge fill-level chart: h/R = 1 -> m1/m_liq ~ 0.43):

    m_1 / m_liquid = (2 R / (lambda_1 * h * (lambda_1^2 - 1)))
                     * tanh(lambda_1 * h / R)                            (2)

Equivalent-pendulum length of the slosh mass (a simple pendulum whose swing
frequency equals the slosh frequency, l = g / omega^2):

    l_1 = g_eff / omega_1^2                                             (3)

Ring-baffle damping (Miles 1958; Dodge Eq. 4.12 / SP-8009), damping ratio
supplied by a single flat rigid ring baffle of radial width w at depth d_s
below the undisturbed free surface, in a tank of radius R:

    gamma_baffle ~ 2.83 * exp(-4.60 * d_s / R) * (A_baffle / A_tank)^1.5 (4)

with A_baffle / A_tank = 1 - (1 - w/R)^2.  Equation (4) is a semi-empirical
engineering estimate: reported values are tagged ``'approximate'`` and returned
with an uncertainty band (roughly a factor of two), consistent with the scatter
noted in the slosh literature.

Limitations
-----------
- Linear (small-amplitude) free-surface theory; no propellant vortexing,
  breaking waves, or large-amplitude non-linear effects.
- Rigid, upright, right-circular-cylinder geometry.  Domed heads, oblate
  bulkheads and non-cylindrical sections are not modelled (they mainly shift
  the slosh mass by a few percent for a nearly full tank).
- Constant effective axial acceleration ``g_eff`` per evaluation.  For a
  varying flight acceleration, sweep ``g_eff``/fill level with ``fill_sweep``.
- Baffle damping is an order-estimate (Eq. 4), not a CFD result.
"""

from __future__ import annotations

import numpy as np

# Merkezi sabitlerden import (magic-number tutarsızlığını önlemek için).
from hrma.constants import G_0

# ---------------------------------------------------------------------------
# Modal constants: roots of J1'(x) = 0 (antisymmetric slosh modes, SP-106).
# ---------------------------------------------------------------------------
#: First root of J1'(x)=0 -> dominant (fundamental) lateral slosh mode.
LAMBDA_1 = 1.8412
#: First four roots of J1'(x)=0 (SP-106 Table 2.1) for higher-mode reporting.
SLOSH_ROOTS = (1.8412, 5.3314, 8.5363, 11.7060)

#: Standard gravity (BIPM / ISO 80000) as the default axial acceleration.
G0 = G_0

# Miles ring-baffle correlation constants (Eq. 4), Miles 1958 / Dodge Eq. 4.12.
_MILES_C = 2.83
_MILES_DECAY = 4.60
#: +/- factor applied to the Miles damping estimate to form the reported band.
_MILES_BAND_FACTOR = 2.0


class CylindricalTankSlosh:
    """Linear slosh model of an upright circular cylindrical propellant tank.

    Parameters
    ----------
    radius : float
        Tank internal radius R [m].
    fill_height : float
        Static (undisturbed) liquid depth h [m], measured from the tank floor.
    g_eff : float, optional
        Effective axial acceleration [m/s^2].  On the ground this is 9.80665;
        in powered flight it is the longitudinal thrust acceleration
        (T/m, which already includes overcoming gravity).  Default ``G0``.
    fluid_density : float, optional
        Liquid density [kg/m^3].  If given (or ``liquid_mass``), absolute slosh
        masses are returned; otherwise only the dimensionless ratio is given.
    liquid_mass : float, optional
        Total liquid mass [kg].  Overrides ``fluid_density`` if both are given.
    """

    def __init__(self, radius, fill_height, g_eff=G0,
                 fluid_density=None, liquid_mass=None):
        radius = float(radius)
        fill_height = float(fill_height)
        g_eff = float(g_eff)
        if radius <= 0.0:
            raise ValueError("radius must be positive")
        if fill_height <= 0.0:
            raise ValueError("fill_height must be positive")
        if g_eff <= 0.0:
            raise ValueError("g_eff must be positive (axial acceleration)")

        self.radius = radius
        self.fill_height = fill_height
        self.g_eff = g_eff
        self.fluid_density = None if fluid_density is None else float(fluid_density)

        if liquid_mass is not None:
            self.liquid_mass = float(liquid_mass)
        elif self.fluid_density is not None:
            self.liquid_mass = self.fluid_density * np.pi * radius ** 2 * fill_height
        else:
            self.liquid_mass = None

    # -- fundamental relations (single liquid depth) ------------------------

    def natural_frequency(self, mode=1):
        """Slosh natural frequency of ``mode`` (1-indexed).  Returns (omega, f).

        Uses Eq. (1): omega_n^2 = (lambda_n g / R) tanh(lambda_n h / R).
        """
        if mode < 1 or mode > len(SLOSH_ROOTS):
            raise ValueError(f"mode must be 1..{len(SLOSH_ROOTS)}")
        lam = SLOSH_ROOTS[mode - 1]
        omega2 = (lam * self.g_eff / self.radius) * np.tanh(
            lam * self.fill_height / self.radius)
        omega = float(np.sqrt(omega2))
        return omega, omega / (2.0 * np.pi)

    def slosh_mass_ratio(self):
        """Fundamental-mode slosh mass as a fraction of total liquid (Eq. 2)."""
        lam = LAMBDA_1
        R, h = self.radius, self.fill_height
        ratio = (2.0 * R / (lam * h * (lam ** 2 - 1.0))) * np.tanh(lam * h / R)
        return float(ratio)

    def slosh_mass(self):
        """Absolute fundamental-mode slosh mass [kg], or ``None`` if the liquid
        mass is unknown (no density / mass supplied)."""
        if self.liquid_mass is None:
            return None
        return float(self.slosh_mass_ratio() * self.liquid_mass)

    def pendulum_length(self):
        """Equivalent-pendulum length of the fundamental slosh mass [m] (Eq. 3)."""
        omega, _ = self.natural_frequency(mode=1)
        return float(self.g_eff / omega ** 2)

    # -- ring-baffle damping (Miles, Eq. 4) ---------------------------------

    def baffle_damping(self, width_ratio, depth_ratio):
        """Estimated damping ratio of a single flat ring baffle (Miles, Eq. 4).

        Parameters
        ----------
        width_ratio : float
            Radial baffle width as a fraction of tank radius, w/R in (0, 1].
        depth_ratio : float
            Baffle depth below the undisturbed free surface as a fraction of
            radius, d_s/R (>= 0).

        Returns
        -------
        dict with the nominal damping ratio, a low/high band (factor of two),
        the blocked-area ratio, and an ``'approximate'`` confidence flag.
        """
        w = float(width_ratio)
        d = float(depth_ratio)
        if not (0.0 < w <= 1.0):
            raise ValueError("width_ratio must be in (0, 1]")
        if d < 0.0:
            raise ValueError("depth_ratio must be >= 0")
        area_ratio = 1.0 - (1.0 - w) ** 2  # A_baffle / A_tank
        gamma = _MILES_C * np.exp(-_MILES_DECAY * d) * area_ratio ** 1.5
        return {
            'damping_ratio': float(gamma),
            'damping_ratio_low': float(gamma / _MILES_BAND_FACTOR),
            'damping_ratio_high': float(gamma * _MILES_BAND_FACTOR),
            'blocked_area_ratio': float(area_ratio),
            'width_ratio': w,
            'depth_ratio': d,
            'confidence': 'approximate',
        }

    def recommend_baffle(self, target_damping=0.01, depth_ratio=0.05):
        """Recommend a ring-baffle width to reach a target damping ratio.

        Inverts Eq. (4) for the blocked-area ratio, then the radial width.
        The default target (1% of critical) is a common slosh-stability goal
        (NASA SP-8009).  Result is ``'approximate'``.
        """
        target = float(target_damping)
        d = float(depth_ratio)
        base = _MILES_C * np.exp(-_MILES_DECAY * d)
        area_ratio = float(np.clip((target / base) ** (2.0 / 3.0), 0.0, 1.0))
        width_ratio = float(1.0 - np.sqrt(max(0.0, 1.0 - area_ratio)))
        achievable = area_ratio < 1.0
        return {
            'target_damping_ratio': target,
            'recommended_width_ratio': width_ratio,
            'recommended_width_m': width_ratio * self.radius,
            'depth_ratio': d,
            'blocked_area_ratio': area_ratio,
            'achievable_with_single_baffle': achievable,
            'note': (
                "Single flat ring baffle near the free surface, Miles (1958) "
                "estimate; add baffles spaced ~1 radius apart down the tank to "
                "keep damping as the level drains. Values are approximate."
                if achievable else
                "Target damping exceeds a single surface baffle; use multiple "
                "baffles or wider rings. Estimate is approximate."),
            'confidence': 'approximate',
        }

    # -- fill-level sweep ---------------------------------------------------

    def fill_sweep(self, heights):
        """Sweep the liquid depth and return modal quantities vs fill level.

        Parameters
        ----------
        heights : array_like
            Liquid depths h [m] (e.g. a draining profile).  Values <= 0 are
            skipped as invalid.

        Returns
        -------
        dict of numpy arrays: ``fill_height``, ``fill_ratio`` (h/R),
        ``f1_hz``, ``omega1``, ``slosh_mass_ratio``, ``pendulum_length``,
        and (if the liquid mass/density is known) ``slosh_mass_kg``.
        """
        heights = np.asarray(heights, dtype=float)
        mask = heights > 0.0
        h = heights[mask]
        lam = LAMBDA_1
        R = self.radius
        omega2 = (lam * self.g_eff / R) * np.tanh(lam * h / R)
        omega = np.sqrt(omega2)
        f1 = omega / (2.0 * np.pi)
        ratio = (2.0 * R / (lam * h * (lam ** 2 - 1.0))) * np.tanh(lam * h / R)
        l1 = self.g_eff / omega2
        out = {
            'fill_height': h,
            'fill_ratio': h / R,
            'omega1': omega,
            'f1_hz': f1,
            'slosh_mass_ratio': ratio,
            'pendulum_length': l1,
        }
        if self.fluid_density is not None:
            m_liq = self.fluid_density * np.pi * R ** 2 * h
            out['slosh_mass_kg'] = ratio * m_liq
        return out

    # -- frequency-coincidence check ----------------------------------------

    @staticmethod
    def _coincidence(f_slosh, frequencies, margin, label):
        warns = []
        for f in frequencies:
            f = float(f)
            if f <= 0.0:
                continue
            if abs(f_slosh - f) <= margin * f:
                warns.append(
                    f"Slosh f1={f_slosh:.3f} Hz is within {margin*100:.0f}% of "
                    f"a {label} frequency {f:.3f} Hz (coupling risk).")
        return warns

    # -- top-level analysis -------------------------------------------------

    def analyze(self, control_frequencies=None, structural_frequencies=None,
                coincidence_margin=0.20, baffle_width_ratio=None,
                baffle_depth_ratio=0.10, sweep_heights=None):
        """Full slosh assessment for the current geometry.

        Optional inputs
        ---------------
        control_frequencies, structural_frequencies : list of float
            Frequencies [Hz] to check against the slosh frequency for a
            coincidence (coupling) warning.
        coincidence_margin : float
            Fractional band for the coincidence check (default 0.20 = +/-20%).
        baffle_width_ratio : float, optional
            If given, evaluate a specific ring baffle (w/R); otherwise a target
            damping recommendation is returned instead.
        baffle_depth_ratio : float
            Baffle depth below the free surface as a fraction of radius.
        sweep_heights : array_like, optional
            Liquid depths for the fill sweep; defaults to 25 points over
            (0.02..1.0) * fill_height.
        """
        omega1, f1 = self.natural_frequency(mode=1)
        ratio = self.slosh_mass_ratio()

        modal = []
        for m in range(1, len(SLOSH_ROOTS) + 1):
            om, fm = self.natural_frequency(mode=m)
            modal.append({'mode': m, 'omega': om, 'f_hz': fm})

        if sweep_heights is None:
            sweep_heights = np.linspace(0.02, 1.0, 25) * self.fill_height
        sweep = self.fill_sweep(sweep_heights)

        warnings = []
        if control_frequencies:
            warnings += self._coincidence(
                f1, control_frequencies, coincidence_margin, "control")
        if structural_frequencies:
            warnings += self._coincidence(
                f1, structural_frequencies, coincidence_margin, "structural")

        if baffle_width_ratio is not None:
            baffle = self.baffle_damping(baffle_width_ratio, baffle_depth_ratio)
        else:
            baffle = self.recommend_baffle(depth_ratio=baffle_depth_ratio)

        result = {
            'radius': self.radius,
            'fill_height': self.fill_height,
            'fill_ratio': self.fill_height / self.radius,
            'g_eff': self.g_eff,
            'omega1': omega1,
            'f1_hz': f1,
            'slosh_mass_ratio': ratio,
            'slosh_mass_kg': self.slosh_mass(),
            'liquid_mass_kg': self.liquid_mass,
            'pendulum_length': self.pendulum_length(),
            'modes': modal,
            'fill_sweep': {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                           for k, v in sweep.items()},
            'baffle': baffle,
            'coincidence_warnings': warnings,
            'model_note': (
                "Linear small-amplitude slosh (NASA SP-106 / Dodge 2000, "
                "upright rigid cylinder). Frequency and slosh-mass are "
                "analytic; baffle damping (Miles 1958) is approximate."),
            'confidence': 'medium',
        }
        return result


def analyze_slosh(radius, fill_height, g_eff=G0, fluid_density=None,
                  liquid_mass=None, **kwargs):
    """Convenience wrapper: build :class:`CylindricalTankSlosh` and analyze."""
    model = CylindricalTankSlosh(
        radius=radius, fill_height=fill_height, g_eff=g_eff,
        fluid_density=fluid_density, liquid_mass=liquid_mass)
    return model.analyze(**kwargs)
