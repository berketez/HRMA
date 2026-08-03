"""Two-phase (particle-laden) flow Isp-loss estimator for solid rocket motors.

Scope (docs/YOL_HARITASI_2.7_VE_SONRASI.md, F4 foundation): metallized solid
propellants (Al -> Al2O3 in the exhaust) lose delivered specific impulse
because condensed-phase particles lag the gas both in velocity and in
temperature. This module provides an HONEST engineering estimate built
exclusively from published empirical relations, each carried with its source
and validity window. Full multi-phase CFD is NOT modelled here (see
``NOT_MODELLED`` below), and inputs outside the published data windows return
an explicit invalid-range declaration instead of a silently extrapolated
number.

Model structure
---------------
1. Mean particle diameter d43 (mass-averaged). Either supplied by the caller
   or estimated with the industry-standard Hermsen correlation::

       d43 [um] = 3.6304 * Dt[in]^0.2932 * (1 - exp(-0.0008163 * zeta_c * Pc[psia] * tau[ms]))

   Source: Hermsen, R. W., "Aluminum Oxide Particle Size for Solid Rocket
   Motor Performance Prediction", J. Spacecraft and Rockets, Vol. 18, No. 6,
   1981, pp. 483-490; formula, units and worked parameter values reproduced
   in Sambamurthi, J. K., "Plume Particle Collection and Sizing from Static
   Firing of Solid Rocket Motors", AIAA 96-2779 (NASA NTRS 19960016118):
   Dt in INCHES, zeta_c = chamber Al2O3 concentration in g-mol per 100 g of
   products, Pc in PSIA, tau = mean chamber residence time in MILLISECONDS.
   Published anchor reproduced by this implementation: RSRM Dt = 53.86 in,
   zeta_c = 0.262, tau ~ 350 ms (saturated regime) -> d43 = 11.68 um.
   zeta_c is derived here from the condensed mass fraction assuming full
   Al -> Al2O3 conversion (zeta_c = 100*beta/101.96); AIAA 96-2779 quotes the
   slightly smaller chamber-equilibrium value for RSRM (0.262 vs 0.297
   stoichiometric) — in the saturated exponential regime the difference has a
   negligible effect on d43, and this assumption is declared in the output.

2. Lag-loss central estimate (velocity lag + thermal lag combined)::

       loss_pct = 100 * K * beta * g(x),     g(x) = 2x / (1 + x)

   with x = (d43/D43_REF)^2 * (D_THROAT_REF/Dt) a Stokes-number RATIO
   (Stokes velocity relaxation time tau_v = rho_p*d^2/(18*mu) — Stokes drag
   CD = 24/Re, NASA SP-8039 "Solid Rocket Motor Performance Analysis and
   Prediction", 1971, Table I, first row — divided by a nozzle flow time
   proportional to Dt; gas viscosity and sonic speed cancel in the ratio,
   which assumes anchor-like combustion-gas states and is declared
   approximate).

   Published anchors of the linear coefficient K (loss per unit condensed
   mass fraction beta, in the frame "delivered Isp relative to
   equilibrium-two-phase theoretical Isp"):

   * K central = 0.12 — identical to ``TWO_PHASE_LOSS_COEFF`` in
     hrma/engines/solid_rocket_engine.py (single definition point; imported
     lazily when available) which anchors eta_2phase = 1 - K*X_p.
   * K low = 0.106 — AFRPL rule of thumb, "1% of Isp for every 5% mass of
     aluminum added" (quoted in US Patent 8,051,640), converted with the
     Al -> Al2O3 mass ratio 1.8895: 0.2 %/wt%Al / 1.8895 = 0.106 per unit
     beta.
   * K high = 0.20 — steepest family of NASA SP-8039 Figure 8 ("Typical
     effect of condensed metal oxide in exhaust on test motor Isp_d
     efficiency", ref. 27 therein): efficiency drops ~8 points over
     0 -> 40 wt% oxide (figure read, approximate).

   Shape anchors of g(x): loss grows with particle diameter and shrinks with
   motor (throat) size — Sutton & Biblarz, "Rocket Propulsion Elements",
   9th ed., Sec. 3.5 (small particles ride with the gas; particles over
   0.015 mm violate the small-lag regime, Isp deficit can reach 10-20%) and
   NASA SP-8039 Fig. 19 (larger motors show higher vacuum-Isp efficiency).
   D43_REF = 5 um is the limiting mean droplet diameter of the vapor
   condensation/agglomeration models reviewed in NASA SP-8039, p. 23
   (Cheung & Cohen). The g(x) interpolant itself and D_THROAT_REF are
   order-of-magnitude calibration choices: g(1) = 1 reproduces the linear
   anchor law at the reference state and g(inf) = 2 bounds the estimator at
   twice the linear anchor. APPROXIMATE — calibration against static-fire
   data recommended; the reported band carries the K-anchor spread.

   Emergent consistency checks (not fitted, fall out of the model): with the
   Hermsen path, net loss DECREASES with throat diameter
   (loss ~ Dt^-0.41), matching SP-8039 Fig. 19; typical Al-loaded APCP
   (16-18% Al, beta = 0.30-0.34) lands at ~3.8-4.9%, inside the 2-6%
   band spanned by the AFRPL rule (3.2-3.6% at 16-18% Al) and the SP-8039
   Fig. 8 slope family (see tests/test_iki_faz_kayip.py).

3. Effective-property (equilibrium two-phase) correction suggestion —
   Sutton & Biblarz, 9th ed., Sec. 3.5 "Multiphase Flow", Eqs. 3-35..3-39,
   pp. 83-85 (their Refs. 3-13 Williams/Barrere/Huang AGARDograph 116 and
   3-14 Barrere et al., "Rocket Propulsion")::

       cp_mix  = (1-beta)*cp_g + beta*cs          (Eq. 3-35 coefficient)
       R_mix   = (1-beta)*R_g                     (Eq. 3-38)
       k_mix   = ((1-beta)*cp_g + beta*cs)
                 / ((1-beta)*cv_g + beta*cs)      (Eq. 3-39)
       M_eff   = M_g / (1-beta)                   (from R_mix = R_u/M_eff)

   Validity per Sutton: particles small enough to stay in velocity and
   thermal equilibrium with the gas — "less than 0.01 mm" (10 um). For
   d43 > 10 um the correction is NOT evaluated (no silent extrapolation);
   the output says so.

   Default particle specific heat: liquid Al2O3, NIST-JANAF Thermochemical
   Tables (Al2O3 cr,l table): Cp = 192.464 J/(mol K), constant above the
   2327 K melting point -> 1887.6 J/(kg K).

NOT_MODELLED (declared in every result):
    * particle size distribution — a single mass-averaged d43 is used;
    * agglomeration / breakup along the nozzle;
    * nozzle wall impingement of particles;
    * solidification (freezing) lag and latent-heat release of Al2O3.

Output schema of :meth:`TwoPhaseLoss.evaluate`::

    {
        'valid': bool,                    # False -> out-of-range declaration
        'validity': {'violations': [...], 'ranges': {...}},
        'two_phase_loss_pct': float|None, # None when invalid (no silent number)
        'two_phase_loss_band_pct': [lo, hi]|None,
        'loss_mechanism': 'velocity_and_thermal_lag',
        'loss_reference_frame': str,      # what the loss is measured against
        'particle_diameter_um': float|None,
        'particle_diameter_basis': str,   # 'user_input' | 'hermsen_1981' | reason
        'effective_properties': dict|None,# Sutton Eqs. 3-35..3-39 suggestion
        'not_modelled': [ ... ],
        'diagnostics': { ... },
        'model_note': str,
        '_basis': str,
    }
"""

import math
from typing import Dict, List, Optional

from hrma.constants import R_UNIVERSAL

# ---------------------------------------------------------------------------
# Al2O3 sabitleri — motor tarafındaki AL_TO_AL2O3_MASS_RATIO ile aynı 101.96
# değeri (solid_rocket_engine.py bu molar kütleden 1.8895 oranını türetir;
# bekçi testi iki değerin tutarlılığını kilitler).
# ---------------------------------------------------------------------------
AL2O3_MOLAR_MASS_KG_KMOL = 101.96
#: NIST-JANAF, Al2O3 (cr,l) tablosu: sıvı faz Cp = 192.464 J/(mol K),
#: 2327 K ergime noktası üstünde sabit. Kütlesel: 192.464/0.10196 kg/mol.
AL2O3_LIQUID_CP_J_KG_K = 192.464 / (AL2O3_MOLAR_MASS_KG_KMOL / 1000.0)

# Birim çevrimleri (Hermsen bağıntısı inch/psia/ms ister)
_M_TO_INCH = 1000.0 / 25.4
_BAR_TO_PSIA = 14.503773773

# ---------------------------------------------------------------------------
# Geçerlilik pencereleri — her satırın künyesi yanında. Pencere DIŞI girdi
# sessizce ekstrapole EDİLMEZ: sonuç 'geçersiz aralık' beyanıyla döner.
# ---------------------------------------------------------------------------
VALIDITY_RANGES = {
    'condensed_mass_fraction': {
        'range': (0.0, 0.40),
        'source': ("NASA SP-8039 (1971) Fig. 8 data window: 0-40 wt% "
                   "condensed metal oxide in exhaust"),
    },
    'chamber_pressure_bar': {
        'range': (4.83, 137.9),
        'source': ("NASA SP-8039 (1971) Fig. 9 measurement window: "
                   "70-2000 psia chamber pressure"),
    },
    'throat_diameter_m': {
        'range': (0.0254, 1.372),
        'source': ("NASA SP-8039 (1971) Fig. 11 axis (1-100 in, data to "
                   "~60 in) and AIAA 96-2779 RSRM throat 53.86 in"),
    },
    'particle_diameter_um': {
        'range': (0.0, 15.0),
        'source': ("Sutton & Biblarz 9th ed. Sec. 3.5: over 0.015 mm "
                   "(15 um) the small-lag theory does not apply"),
    },
    'residence_time_ms': {
        'range': (2.0, 350.0),
        'source': ("NASA SP-8039 (1971) Fig. 10 data (~2-70 ms) plus "
                   "AIAA 96-2779 quoted values (MNASA ~120 ms, RSRM "
                   "~350 ms)"),
    },
}

#: Her sonuçla birlikte beyan edilen modellenmemiş fizik.
NOT_MODELLED = (
    'particle_size_distribution',   # tek d43 kullanılır, dağılım yok
    'agglomeration_breakup',        # lüle boyunca birleşme/kırılma yok
    'nozzle_wall_impingement',      # tanecik-duvar çarpması yok
    'solidification_lag',           # donma gecikmesi + gizli ısı geri kazanımı yok
)


class TwoPhaseLoss:
    """Particle-lag Isp-loss estimator (see module docstring for sources).

    API-independent by design: no engine object is required; the caller
    supplies scalar motor parameters using the solid-motor schema names
    (``condensed_mass_fraction`` as in ``SOLID_CONDENSED_MASS_FRACTION``,
    ``throat_diameter`` in metres, ``chamber_pressure`` in bar). Wiring into
    the solid-motor pipeline is a later wave.
    """

    # Hermsen (1981) bağıntı sabitleri — AIAA 96-2779'daki yeniden basımdan.
    HERMSEN_COEFF = 3.6304
    HERMSEN_DT_EXP = 0.2932
    HERMSEN_EXP_COEFF = 0.0008163

    #: Doğrusal kayıp katsayısı bandı (birim beta başına kayıp kesri):
    #: alt = AFRPL kuralı (0.2 %/wt%Al / 1.8895), üst = SP-8039 Şek. 8'in en
    #: dik ailesi (şekil okuması, yaklaşık).
    K_BAND = (0.106, 0.20)
    #: Merkez katsayı — motor tarafındaki TWO_PHASE_LOSS_COEFF ile aynı
    #: (tembel import; motor modülü yüklenemezse bu yedek kullanılır ve
    #: bekçi testi eşitliği kilitler).
    K_CENTRAL_FALLBACK = 0.12

    #: Boyut çarpanı referansları. D43_REF: NASA SP-8039 s. 23, Cheung &
    #: Cohen sınır damla çapı ~5 um. D_THROAT_REF: mertebe çapası
    #: (yaklaşık, kalibrasyon önerilir).
    D43_REF_UM = 5.0
    D_THROAT_REF_M = 0.10

    #: Sutton Böl. 3.5: denge (etkin özellik) varsayımı "0.01 mm'den küçük"
    #: tanecikler için geçerli.
    EQUILIBRIUM_D43_MAX_UM = 10.0

    def __init__(self):
        self._k_central = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def evaluate(self,
                 condensed_mass_fraction: float,
                 throat_diameter: float,
                 chamber_pressure: float,
                 particle_diameter_um: Optional[float] = None,
                 residence_time_ms: Optional[float] = None,
                 gamma_gas: Optional[float] = None,
                 molecular_weight_gas: Optional[float] = None,
                 particle_specific_heat: Optional[float] = None) -> Dict:
        """Estimate the two-phase (particle-lag) Isp loss.

        Parameters
        ----------
        condensed_mass_fraction : float
            beta = condensed-phase (Al2O3 etc.) mass fraction of the
            combustion products, same quantity as the values tabulated in
            ``hrma.engines.solid_rocket_engine.SOLID_CONDENSED_MASS_FRACTION``.
        throat_diameter : float
            Nozzle throat diameter [m] (engine-internal convention).
        chamber_pressure : float
            Chamber pressure [bar] (engine convention).
        particle_diameter_um : float, optional
            Mass-averaged particle diameter d43 [um]. Omitted -> estimated
            with the Hermsen (1981) correlation, which then requires
            ``residence_time_ms``.
        residence_time_ms : float, optional
            Mean chamber residence time [ms] for the Hermsen estimate
            (AIAA 96-2779 anchors: MNASA ~120 ms, RSRM ~350 ms; small
            research motors ~2-70 ms per NASA SP-8039 Fig. 10).
        gamma_gas, molecular_weight_gas : float, optional
            Gas-only specific-heat ratio [-] and molecular weight [kg/kmol].
            Both given -> the Sutton Eqs. 3-35..3-39 effective-property
            correction is evaluated (d43 <= 10 um only).
        particle_specific_heat : float, optional
            Particle specific heat cs [J/(kg K)]. Default: liquid Al2O3,
            NIST-JANAF 192.464 J/(mol K) -> 1887.6 J/(kg K).

        Raises
        ------
        ValueError
            For nonsensical inputs (negative sizes/pressures, beta outside
            [0, 1)). Out-of-published-window but physically meaningful
            inputs do NOT raise — they return ``valid=False`` with the
            violation list (no silent extrapolation).
        """
        beta = self._require_finite('condensed_mass_fraction',
                                    condensed_mass_fraction)
        if not 0.0 <= beta < 1.0:
            raise ValueError(
                f"condensed_mass_fraction must be in [0, 1), got {beta}")
        d_t = self._require_finite('throat_diameter', throat_diameter)
        if d_t <= 0:
            raise ValueError(f"throat_diameter must be positive, got {d_t}")
        p_c = self._require_finite('chamber_pressure', chamber_pressure)
        if p_c <= 0:
            raise ValueError(f"chamber_pressure must be positive, got {p_c}")
        if particle_diameter_um is not None and particle_diameter_um <= 0:
            raise ValueError("particle_diameter_um must be positive when given")
        if residence_time_ms is not None and residence_time_ms <= 0:
            raise ValueError("residence_time_ms must be positive when given")

        cs = (particle_specific_heat if particle_specific_heat is not None
              else AL2O3_LIQUID_CP_J_KG_K)
        if cs <= 0:
            raise ValueError("particle_specific_heat must be positive")

        # --- Sıfır tanecik kısa devresi: kayıp TANIM GEREĞİ sıfır --------
        if beta == 0.0:
            return self._zero_particle_result(
                gamma_gas, molecular_weight_gas, cs)

        violations: List[str] = []
        self._check_range('condensed_mass_fraction', beta, violations)
        self._check_range('chamber_pressure_bar', p_c, violations)
        self._check_range('throat_diameter_m', d_t, violations)

        # --- Tanecik çapı: girdi ya da Hermsen ---------------------------
        d43_um = None
        if particle_diameter_um is not None:
            d43_um = float(particle_diameter_um)
            d43_basis = 'user_input'
        elif residence_time_ms is not None:
            self._check_range('residence_time_ms', residence_time_ms,
                              violations)
            d43_um = self._hermsen_d43_um(beta, d_t, p_c, residence_time_ms)
            d43_basis = (
                "hermsen_1981 (Hermsen, J. Spacecraft & Rockets 18(6), 1981; "
                "as reproduced in AIAA 96-2779; zeta_c from full Al->Al2O3 "
                "conversion, zeta_c = 100*beta/101.96)")
        else:
            d43_basis = (
                "unavailable: supply particle_diameter_um or "
                "residence_time_ms (Hermsen correlation input)")
            violations.append(
                "particle diameter unknown — neither particle_diameter_um "
                "nor residence_time_ms was provided; the Hermsen estimate "
                "needs the mean chamber residence time")

        if d43_um is not None:
            lo, hi = VALIDITY_RANGES['particle_diameter_um']['range']
            if not lo < d43_um <= hi:
                violations.append(
                    f"particle_diameter_um={d43_um:.2f} outside ({lo}, {hi}] "
                    f"— {VALIDITY_RANGES['particle_diameter_um']['source']}")

        # --- Etkin özellik önerisi (kayıptan bağımsız raporlanır) --------
        effective = self._effective_properties(
            beta, gamma_gas, molecular_weight_gas, cs, d43_um)

        if violations:
            return self._invalid_result(violations, d43_um, d43_basis,
                                        effective)

        # --- Kayıp tahmini ----------------------------------------------
        k_central = self._central_loss_coeff()
        stokes_ratio = ((d43_um / self.D43_REF_UM) ** 2
                        * (self.D_THROAT_REF_M / d_t))
        size_factor = 2.0 * stokes_ratio / (1.0 + stokes_ratio)
        loss_pct = 100.0 * k_central * beta * size_factor
        band = [100.0 * self.K_BAND[0] * beta * size_factor,
                100.0 * self.K_BAND[1] * beta * size_factor]

        note = (
            "Velocity+thermal particle-lag loss relative to the "
            "equilibrium-two-phase theoretical Isp: 100*K*beta*g(x) with "
            "the K anchors and the Stokes-ratio size factor g documented in "
            "the module docstring (Sutton 9th ed. Sec. 3.5; NASA SP-8039 "
            "Figs. 8/19, Table I; AFRPL rule via US 8,051,640; Hermsen 1981 "
            "for d43). The size-factor calibration is approximate — "
            "calibration against static-fire data recommended. The band "
            "carries the published K-anchor spread only; d43 scatter is not "
            "folded in."
        )

        return {
            'valid': True,
            'validity': {'violations': [], 'ranges': self._ranges_summary()},
            'two_phase_loss_pct': float(loss_pct),
            'two_phase_loss_band_pct': [float(band[0]), float(band[1])],
            'loss_mechanism': 'velocity_and_thermal_lag',
            'loss_reference_frame': (
                'delivered Isp deficit relative to equilibrium-two-phase '
                'theoretical Isp (same frame as the SP-8039 Fig. 8 test '
                'data and the engine-side eta_2phase = 1 - K*X_p)'),
            'particle_diameter_um': float(d43_um),
            'particle_diameter_basis': d43_basis,
            'effective_properties': effective,
            'not_modelled': list(NOT_MODELLED),
            'diagnostics': {
                'k_central': k_central,
                'k_band': list(self.K_BAND),
                'stokes_ratio': float(stokes_ratio),
                'size_factor': float(size_factor),
                'size_factor_reference': {
                    'd43_ref_um': self.D43_REF_UM,
                    'throat_ref_m': self.D_THROAT_REF_M,
                },
            },
            'model_note': note,
            '_basis': (
                "Sutton & Biblarz, Rocket Propulsion Elements, 9th ed., "
                "Sec. 3.5 (Eqs. 3-35..3-39, small/large-particle regime "
                "statements); Hermsen 1981 via AIAA 96-2779; NASA SP-8039 "
                "(1971) Figs. 8-11, 19, Table I; AFRPL rule quoted in "
                "US Patent 8,051,640; NIST-JANAF Al2O3(l) Cp"),
        }

    # ------------------------------------------------------------------ #
    # Hermsen (1981) tanecik çapı
    # ------------------------------------------------------------------ #

    def _hermsen_d43_um(self, beta: float, throat_diameter_m: float,
                        chamber_pressure_bar: float,
                        residence_time_ms: float) -> float:
        """d43 [um] = 3.6304 * Dt[in]^0.2932 * (1 - exp(-0.0008163*zeta*Pc*tau)).

        Units per AIAA 96-2779: Dt inches, Pc psia, tau milliseconds,
        zeta_c g-mol Al2O3 per 100 g products. zeta_c here assumes full
        Al -> Al2O3 conversion: zeta_c = 100*beta / 101.96.
        """
        d_t_in = throat_diameter_m * _M_TO_INCH
        p_c_psia = chamber_pressure_bar * _BAR_TO_PSIA
        zeta_c = 100.0 * beta / AL2O3_MOLAR_MASS_KG_KMOL
        saturation = 1.0 - math.exp(
            -self.HERMSEN_EXP_COEFF * zeta_c * p_c_psia * residence_time_ms)
        return (self.HERMSEN_COEFF * d_t_in ** self.HERMSEN_DT_EXP
                * saturation)

    # ------------------------------------------------------------------ #
    # Sutton Eş. 3-35..3-39 etkin özellik önerisi
    # ------------------------------------------------------------------ #

    def _effective_properties(self, beta: float, gamma_gas: Optional[float],
                              mw_gas: Optional[float], cs: float,
                              d43_um: Optional[float]) -> Optional[Dict]:
        basis = (
            "Sutton & Biblarz, Rocket Propulsion Elements, 9th ed., "
            "Sec. 3.5 'Multiphase Flow', Eqs. 3-35..3-39 (pp. 83-85): "
            "R_mix = (1-beta)*R_g; k_mix = ((1-beta)*cp+beta*cs)/"
            "((1-beta)*cv+beta*cs); M_eff = M_g/(1-beta). Assumes particles "
            "in velocity and thermal equilibrium with the gas (valid below "
            "0.01 mm = 10 um), negligible particle volume, no mass "
            "exchange. cs default: liquid Al2O3, NIST-JANAF 192.464 "
            "J/(mol K) = 1887.6 J/(kg K).")
        if gamma_gas is None or mw_gas is None:
            return {
                'applicable': False,
                'reason': ('gas properties not provided (gamma_gas and '
                           'molecular_weight_gas are both required)'),
                '_basis': basis,
            }
        if not gamma_gas > 1.0:
            raise ValueError(f"gamma_gas must exceed 1, got {gamma_gas}")
        if not mw_gas > 0:
            raise ValueError(f"molecular_weight_gas must be positive, "
                             f"got {mw_gas}")
        if d43_um is not None and d43_um > self.EQUILIBRIUM_D43_MAX_UM:
            # Sutton'un denge varsayımı bozulur: değer ÜRETME (sessiz
            # ekstrapolasyon yasağı), nedenini söyle.
            return {
                'applicable': False,
                'reason': (
                    f"d43 = {d43_um:.2f} um exceeds the Sutton Sec. 3.5 "
                    f"equilibrium bound of {self.EQUILIBRIUM_D43_MAX_UM:.0f} "
                    "um ('less than 0.01 mm'); the equal-velocity/"
                    "equal-temperature mixture relations would be an "
                    "extrapolation and are not evaluated"),
                '_basis': basis,
            }

        r_gas = R_UNIVERSAL / mw_gas                       # J/(kg K)
        cp_gas = gamma_gas * r_gas / (gamma_gas - 1.0)     # J/(kg K)
        cv_gas = r_gas / (gamma_gas - 1.0)                 # J/(kg K)
        cp_mix = (1.0 - beta) * cp_gas + beta * cs         # Eş. 3-35
        cv_mix = (1.0 - beta) * cv_gas + beta * cs
        gamma_mix = cp_mix / cv_mix                        # Eş. 3-39
        r_mix = (1.0 - beta) * r_gas                       # Eş. 3-38
        mw_eff = mw_gas / (1.0 - beta)                     # R_u/R_mix

        return {
            'applicable': True,
            'gamma_mixture': float(gamma_mix),
            'effective_molecular_weight': float(mw_eff),   # kg/kmol
            'effective_gas_constant': float(r_mix),        # J/(kg K)
            'mixture_cp': float(cp_mix),                   # J/(kg K)
            'gas_only': {'gamma': float(gamma_gas),
                         'molecular_weight': float(mw_gas)},
            'particle_specific_heat': float(cs),
            'suggestion': (
                'use gamma_mixture / effective_molecular_weight in place of '
                'the gas-only pair in isentropic nozzle relations when the '
                'upstream thermochemistry did NOT already include the '
                'condensed phase; skip if it did (double counting)'),
            '_basis': basis,
        }

    # ------------------------------------------------------------------ #
    # Yardımcılar
    # ------------------------------------------------------------------ #

    def _central_loss_coeff(self) -> float:
        """Motor tarafındaki TWO_PHASE_LOSS_COEFF ile TEK tanım noktası.

        solid_rocket_engine tembel import edilir; yüklenemezse belgelenmiş
        yedek (aynı değer) kullanılır. Bekçi testi eşitliği kilitler.
        """
        if self._k_central is None:
            try:
                from hrma.engines.solid_rocket_engine import (
                    TWO_PHASE_LOSS_COEFF)
                self._k_central = float(TWO_PHASE_LOSS_COEFF)
            except Exception:  # pragma: no cover - motor modülü kurulamazsa
                self._k_central = self.K_CENTRAL_FALLBACK
        return self._k_central

    @staticmethod
    def _require_finite(name: str, value) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a real number, got {value!r}")
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite, got {value}")
        return value

    @staticmethod
    def _check_range(key: str, value: float, violations: List[str]) -> None:
        lo, hi = VALIDITY_RANGES[key]['range']
        if not lo <= value <= hi:
            violations.append(
                f"{key}={value:.4g} outside [{lo}, {hi}] — "
                f"{VALIDITY_RANGES[key]['source']}")

    @staticmethod
    def _ranges_summary() -> Dict:
        return {k: {'range': list(v['range']), 'source': v['source']}
                for k, v in VALIDITY_RANGES.items()}

    def _zero_particle_result(self, gamma_gas, mw_gas, cs) -> Dict:
        effective = self._effective_properties(0.0, gamma_gas, mw_gas, cs,
                                               None)
        return {
            'valid': True,
            'validity': {'violations': [], 'ranges': self._ranges_summary()},
            'two_phase_loss_pct': 0.0,
            'two_phase_loss_band_pct': [0.0, 0.0],
            'loss_mechanism': 'velocity_and_thermal_lag',
            'loss_reference_frame': (
                'no condensed phase: single-phase flow, two-phase loss is '
                'zero by definition'),
            'particle_diameter_um': None,
            'particle_diameter_basis': ('not_applicable: zero condensed '
                                        'mass fraction'),
            'effective_properties': effective,
            'not_modelled': list(NOT_MODELLED),
            'diagnostics': {'k_central': self._central_loss_coeff(),
                            'k_band': list(self.K_BAND),
                            'stokes_ratio': 0.0,
                            'size_factor': 0.0},
            'model_note': ('Zero condensed mass fraction — no particles, no '
                           'velocity/thermal lag, loss identically zero.'),
            '_basis': ('limit case of loss_pct = 100*K*beta*g(x) at '
                       'beta = 0'),
        }

    def _invalid_result(self, violations: List[str], d43_um, d43_basis,
                        effective) -> Dict:
        return {
            'valid': False,
            'validity': {'violations': list(violations),
                         'ranges': self._ranges_summary()},
            # Sessiz ekstrapolasyon yasağı: aralık dışı girdiye SAYI dönmez.
            'two_phase_loss_pct': None,
            'two_phase_loss_band_pct': None,
            'loss_mechanism': 'velocity_and_thermal_lag',
            'loss_reference_frame': 'not_evaluated: out-of-range inputs',
            'particle_diameter_um': (float(d43_um) if d43_um is not None
                                     else None),
            'particle_diameter_basis': d43_basis,
            'effective_properties': effective,
            'not_modelled': list(NOT_MODELLED),
            'diagnostics': {},
            'model_note': (
                'GEÇERSİZ ARALIK: one or more inputs fall outside the '
                'published data windows of the underlying correlations; no '
                'loss number is produced because that would be a silent '
                'extrapolation. See validity.violations.'),
            '_basis': 'validity guard (module docstring, VALIDITY_RANGES)',
        }


# Modül seviyesinde hazır örnek — repo genelindeki desen (kurulum ucuz,
# motor importu tembel olduğundan yük yok).
two_phase_loss = TwoPhaseLoss()
