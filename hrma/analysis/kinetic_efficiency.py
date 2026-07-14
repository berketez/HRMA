"""Tiered nozzle kinetic-efficiency model (successor of the legacy kinetic_analysis).

Architecture (docs/ANALIZ_PLATFORM_PLANI.md, Wave 4 — Berke + GPT-5.6 decision):
instead of a pseudo finite-rate solver with invented rate constants, three
explicit fidelity levels are offered, each honest about its own accuracy:

  * ``fast``          — chemical-equilibrium reference. Reuses the frozen /
                        shifting Isp pair already produced by
                        :class:`hrma.engines.combustion_analysis.CombustionAnalyzer`
                        (NASA CEA-style, Cantera backend). Kinetic loss is
                        REPORTED AS ZERO by definition (equilibrium reference);
                        the frozen/shifting gap is returned as the loss band.
  * ``engineering``   — JANNAF-style correlation. The true one-dimensional
                        kinetics answer always lies BETWEEN the frozen and the
                        shifting (local-equilibrium) expansion limits
                        (Bray, J. Fluid Mech. 6, 1959 — sudden-freezing
                        analysis; Vincenti & Kruger, "Introduction to Physical
                        Gas Dynamics", Ch. 8, nonequilibrium nozzle flows).
                        The blend fraction is a log-sigmoid of a Damköhler-like
                        parameter built from the chamber stay time
                        t_res = L*·rho_c·c*/P_c (Sutton & Biblarz, "Rocket
                        Propulsion Elements", 9th ed., Eq. 8-9) and a
                        termolecular-recombination chemical time that scales
                        as P^-2 (three-body recombination rate ∝ [M]^2).
                        The calibration constants are order-of-magnitude
                        anchors, NOT precise values — see the
                        "approximate, calibration recommended" notes below.
  * ``high_fidelity`` — finite-rate species integration (Cantera, BDF) along a
                        prescribed nozzle T(x), P(x) path (e.g. the output of
                        the quasi-1D nozzle-flow model). Falls back to
                        ``engineering`` gracefully when Cantera or the profile
                        is unavailable; the response always carries
                        ``fidelity_used`` so the caller knows what it got.

Typical magnitude check (used to anchor — not tune — the correlation):
kinetic (finite-rate) nozzle losses are typically ~0.1-3 % of Isp, largest for
small, low-pressure motors and negligible for large high-pressure engines
(NASA SP-8120, "Liquid Rocket Engine Nozzles", 1976, kinetics-loss discussion;
JANNAF performance-prediction methodology, CPIA Publ. 246 / TDK program).

Output schema of :meth:`KineticEfficiency.evaluate` (all fidelity levels)::

    {
        'fidelity_requested': str,   # what the caller asked for
        'fidelity_used':      str,   # what was actually computed
        'isp_frozen':         float, # s
        'isp_shifting':       float, # s
        'isp_predicted':      float, # s, frozen <= predicted <= shifting
        'kinetic_loss_pct':   float, # (isp_shifting - isp_predicted)/isp_shifting * 100
        'loss_band_pct':      [lo, hi],  # honest uncertainty band on the loss
        'model_note':         str,   # provenance + caveats (English, user-facing)
        'diagnostics':        dict,  # level-specific extras (Damköhler, mechanism, ...)
    }
"""

import logging
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.integrate import solve_ivp

from hrma.constants import G_0, R_UNIVERSAL

# Cantera opsiyonel bağımlılık — combustion_analysis ile aynı desen.
# Kurulu değilse modül import edilebilir kalır; high_fidelity isteği
# 'engineering' seviyesine zarif düşer (fidelity_used alanı bunu raporlar).
try:
    import cantera as ct
    CANTERA_AVAILABLE = True
except ImportError:  # pragma: no cover - CI ortamına bağlı
    ct = None
    CANTERA_AVAILABLE = False

logger = logging.getLogger(__name__)

VALID_FIDELITY_LEVELS = ('fast', 'engineering', 'high_fidelity')


class HighFidelityUnavailable(RuntimeError):
    """Raised internally when the finite-rate path cannot run.

    evaluate() bunu yakalar ve 'engineering' seviyesine düşer — kullanıcıya
    hata değil, fidelity_used='engineering' + açıklayıcı not döner.
    """


class KineticEfficiency:
    """Tiered kinetic-efficiency estimator for nozzle expansion losses.

    Parameters
    ----------
    analyzer : CombustionAnalyzer, optional
        Reused equilibrium backend. Created lazily on first use when the
        caller does not hand in precomputed ``combustion_results`` — so the
        (comparatively expensive) Cantera setup is skipped entirely when the
        caller already has an ``analyze_combustion`` output.
    mechanism : str, optional
        Explicit Cantera mechanism file for the finite-rate path (e.g.
        ``'h2o2.yaml'``). Defaults to the same mechanism family the
        equilibrium backend uses, minus the thermo-only ``nasa_gas.yaml``
        (that file carries NO reactions, hence cannot drive finite-rate
        chemistry).
    """

    # ------------------------------------------------------------------
    # Engineering-correlation calibration constants.
    # HEPSİ "approximate, calibration recommended" statüsündedir: literatür
    # yalnızca ölçekleme YASALARINI (t_res biçimi, P^-2 rekombinasyon,
    # frozen<->shifting sınırları, tipik %0.1-3 kayıp bandı) sabitler;
    # geçiş noktasının tam yeri motor ailesine göre statik ateşleme
    # verisiyle kalibre edilmelidir. Bant raporu (loss_band_pct) bu
    # belirsizliği açıkça taşır.
    # ------------------------------------------------------------------

    #: Default chamber characteristic length L* [m] when the caller gives
    #: none. Typical L* spans ~0.6-3 m across propellant families
    #: (Sutton & Biblarz 9th ed., Table 8-1). Approximate default.
    DEFAULT_L_STAR_M = 1.0

    #: Reference chamber pressure [bar] at which TAU_CHEM_REF_S applies.
    P_REF_BAR = 20.0

    #: Chemical (recombination) relaxation time at P_REF_BAR [s].
    #: Chosen so that a representative small hybrid (L* ~ 1 m, Pc ~ 20 bar)
    #: sits mid-transition between frozen and shifting, which reproduces the
    #: reported ~0.5-3 % kinetic-loss band for small motors while large
    #: high-pressure engines land near shifting (NASA SP-8120; JANNAF/TDK
    #: practice). Order-of-magnitude anchor — approximate, calibration
    #: recommended.
    TAU_CHEM_REF_S = 1.5e-3

    #: Pressure exponent of the chemical time: termolecular (three-body)
    #: recombination rate ∝ [M]^2  =>  tau_chem ∝ P^-2 (Bray 1959;
    #: Vincenti & Kruger Ch. 8). Exact only for ideal three-body kinetics —
    #: approximate for real multi-reaction pools.
    PRESSURE_EXPONENT = 2.0

    #: Optional nozzle-size factor reference throat diameter [m]. Larger
    #: throats expand more slowly (expansion timescale ∝ nozzle length scale,
    #: Bray sudden-freezing argument), keeping the flow near equilibrium
    #: longer. Linear scaling assumed — approximate, calibration recommended.
    D_THROAT_REF_M = 0.05

    #: Log-sigmoid slope: blend fraction f = Da^n / (1 + Da^n). n = 1 is the
    #: gentlest physically monotone choice — approximate.
    SIGMOID_EXPONENT = 1.0

    #: Multiplicative Damköhler uncertainty used for the reported loss band
    #: (band = losses at Da/U and Da·U). Reflects the order-of-magnitude
    #: nature of TAU_CHEM_REF_S.
    DA_UNCERTAINTY_FACTOR = 5.0

    #: Relative half-band applied to the high-fidelity loss (mechanism /
    #: rate-constant uncertainty; JANNAF quotes rate-data uncertainty as the
    #: dominant TDK error source). Approximate.
    HF_BAND_REL = 0.3

    #: Mechanism candidates for the finite-rate path. Same family the
    #: equilibrium backend tries (combustion_analysis), except nasa_gas.yaml
    #: which is thermo-only (0 reactions -> cannot integrate kinetics).
    DEFAULT_KINETIC_MECHANISMS = ('gri30.yaml', 'h2o2.yaml')

    #: Lower clamp on the local flow speed when deriving residence time from
    #: the enthalpy defect (guards the near-stagnation chamber end of a
    #: profile; chemistry there is near-equilibrium anyway, so the clamp
    #: does not bias the freezing location).
    U_MIN_M_S = 10.0

    def __init__(self, analyzer=None, mechanism: Optional[str] = None):
        self._analyzer = analyzer
        self.mechanism = mechanism
        self._kin_gas = None
        self._kin_mech_name = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def evaluate(self,
                 fuel_composition: Optional[Dict] = None,
                 oxidizer_type: Optional[str] = None,
                 of_ratio: Optional[float] = None,
                 chamber_pressure: Optional[float] = None,
                 fidelity: str = 'engineering',
                 characteristic_length: Optional[float] = None,
                 throat_diameter: Optional[float] = None,
                 combustion_results: Optional[Dict] = None,
                 nozzle_profile: Optional[Dict] = None) -> Dict:
        """Evaluate the kinetic efficiency at the requested fidelity level.

        Parameters
        ----------
        fuel_composition, oxidizer_type, of_ratio, chamber_pressure
            Passed straight to ``CombustionAnalyzer.analyze_combustion`` when
            ``combustion_results`` is not supplied. ``chamber_pressure`` in bar.
        fidelity : {'fast', 'engineering', 'high_fidelity'}
        characteristic_length : float, optional
            Chamber L* [m] for the engineering correlation
            (default :attr:`DEFAULT_L_STAR_M`).
        throat_diameter : float, optional
            Throat diameter [m]; enables the nozzle-size factor of the
            engineering correlation. Omitted -> factor 1.
        combustion_results : dict, optional
            An existing ``analyze_combustion`` output. Providing it skips the
            equilibrium recomputation entirely (fast level literally reuses
            the numbers in it).
        nozzle_profile : dict, optional
            High-fidelity input: ``{'x': [m], 'T': [K], 'P': [Pa],
            'u': [m/s] (optional)}`` along the nozzle (e.g. quasi-1D
            nozzle-flow output). Arrays must share length >= 2 and 'x' must be
            strictly increasing.
        """
        if fidelity not in VALID_FIDELITY_LEVELS:
            raise ValueError(
                f"fidelity must be one of {VALID_FIDELITY_LEVELS}, got {fidelity!r}"
            )

        cres = combustion_results
        if cres is None:
            if None in (fuel_composition, oxidizer_type, of_ratio, chamber_pressure):
                raise ValueError(
                    "Either combustion_results or the full propellant definition "
                    "(fuel_composition, oxidizer_type, of_ratio, chamber_pressure) "
                    "must be provided"
                )
            cres = self._get_analyzer().analyze_combustion(
                fuel_composition, oxidizer_type, of_ratio, chamber_pressure
            )

        state = self._extract_state(cres, chamber_pressure)

        if fidelity == 'fast':
            return self._evaluate_fast(state)
        if fidelity == 'engineering':
            return self._evaluate_engineering(
                state, characteristic_length, throat_diameter
            )

        # high_fidelity — zarif düşüş garantili
        try:
            return self._evaluate_high_fidelity(cres, state, nozzle_profile)
        except HighFidelityUnavailable as exc:
            logger.warning(
                "High-fidelity kinetic path unavailable (%s); "
                "falling back to engineering correlation.", exc
            )
            result = self._evaluate_engineering(
                state, characteristic_length, throat_diameter
            )
            result['fidelity_requested'] = 'high_fidelity'
            result['fidelity_used'] = 'engineering'
            result['model_note'] = (
                f"High-fidelity finite-rate path unavailable ({exc}); "
                "fell back to the engineering correlation. "
                + result['model_note']
            )
            return result

    # ------------------------------------------------------------------ #
    # State extraction from a combustion_analysis result
    # ------------------------------------------------------------------ #

    def _get_analyzer(self):
        # Tembel kurulum: Cantera Solution inşası pahalı; combustion_results
        # verildiğinde hiç yapılmasın.
        if self._analyzer is None:
            from hrma.engines.combustion_analysis import CombustionAnalyzer
            self._analyzer = CombustionAnalyzer()
        return self._analyzer

    def _extract_state(self, cres: Dict, chamber_pressure: Optional[float]) -> Dict:
        """Pull the quantities the correlations need out of an
        ``analyze_combustion`` result, with documented fallbacks."""
        perf = cres.get('performance', {})
        conditions = cres.get('conditions', {})
        chamber_cond = conditions.get('chamber', {})
        chamber_comp = cres.get('compositions', {}).get('chamber', {}) or {}

        p_c_bar = chamber_pressure if chamber_pressure is not None \
            else chamber_cond.get('P')
        t_c = chamber_cond.get('T')
        if p_c_bar is None or t_c is None:
            raise ValueError(
                "combustion_results must carry conditions['chamber'] with "
                "'P' (bar) and 'T' (K)"
            )
        if p_c_bar <= 0 or t_c <= 0:
            raise ValueError("Chamber pressure and temperature must be positive")

        mw = chamber_comp.get('molecular_weight') \
            or perf.get('molecular_weights', {}).get('chamber') \
            or 26.0  # tipik yanma gazı MW'si (Sutton 9. baskı Böl. 3 mertebesi)

        rho_c = chamber_comp.get('density')
        if rho_c is None or rho_c <= 0:
            # İdeal gaz: rho = P / (R_spesifik * T)
            rho_c = (p_c_bar * 1e5) / ((R_UNIVERSAL / mw) * t_c)

        c_star = perf.get('c_star')
        if c_star is None or c_star <= 0:
            raise ValueError("combustion_results['performance'] must carry a "
                             "positive 'c_star'")

        note_parts: List[str] = []
        isp_frozen = perf.get('isp_frozen')
        isp_shifting = perf.get('isp_shifting')

        if isp_frozen is None or isp_shifting is None:
            # Cantera'sız yol: frozen/shifting ayrımı tek-gamma bağıntısıyla
            # TAHMİN edilir (Sutton & Biblarz 9. baskı, Eş. 3-15b), yalnız
            # gamma farkı kullanılarak: shifting -> denge (SP-pertürbasyon)
            # gamma'sı, frozen -> frozen cp/cv gamma'sı. Fallback bileşim
            # modelinde iki gamma eşitse ayrım çözülemez -> gap = 0.
            gamma_eq = chamber_comp.get('gamma')
            gamma_fr = chamber_comp.get('gamma_frozen')
            p_e_bar = conditions.get('exit', {}).get('P', 1.0)
            if (gamma_eq and gamma_fr and gamma_fr > 1.0 and gamma_eq > 1.0
                    and p_e_bar and 0 < p_e_bar < p_c_bar):
                r_spec = R_UNIVERSAL / mw
                isp_shifting = self._single_gamma_isp(
                    gamma_eq, r_spec, t_c, p_e_bar / p_c_bar)
                isp_frozen = self._single_gamma_isp(
                    gamma_fr, r_spec, t_c, p_e_bar / p_c_bar)
                # gamma_eq <= gamma_fr olduğundan shifting >= frozen çıkar;
                # sayısal sürprizlere karşı yine de sırala.
                if isp_frozen > isp_shifting:
                    isp_frozen, isp_shifting = isp_shifting, isp_frozen
                note_parts.append(
                    "frozen/shifting split estimated from the single-gamma "
                    "relation (equilibrium vs frozen gamma; Cantera "
                    "frozen/shifting energy solution unavailable)"
                )
            else:
                isp = perf.get('isp')
                if isp is None or isp <= 0:
                    raise ValueError(
                        "combustion_results['performance'] carries neither "
                        "frozen/shifting Isp nor a positive 'isp'"
                    )
                isp_frozen = isp_shifting = float(isp)
                note_parts.append(
                    "frozen/shifting split unresolved (no Cantera data and no "
                    "distinct gamma pair); kinetic loss cannot be resolved and "
                    "is reported as zero with a zero band"
                )

        if not (0 < isp_frozen <= isp_shifting):
            raise ValueError(
                f"Inconsistent Isp pair: frozen={isp_frozen}, shifting={isp_shifting}"
            )

        return {
            'p_c_bar': float(p_c_bar),
            't_c': float(t_c),
            'rho_c': float(rho_c),
            'c_star': float(c_star),
            'mw': float(mw),
            'isp_frozen': float(isp_frozen),
            'isp_shifting': float(isp_shifting),
            'note_parts': note_parts,
        }

    @staticmethod
    def _single_gamma_isp(gamma: float, r_specific: float, t_c: float,
                          pressure_ratio_e_c: float) -> float:
        """Single-gamma ideal exit velocity / g0.

        v_e = sqrt( 2*gamma/(gamma-1) * R * T_c * [1 - (Pe/Pc)^((gamma-1)/gamma)] )
        (Sutton & Biblarz, 9th ed., Eq. 3-15b). Used only to ESTIMATE the
        frozen/shifting split when the energy-method pair is unavailable.
        """
        exponent = (gamma - 1.0) / gamma
        v_e = np.sqrt(
            2.0 * gamma / (gamma - 1.0) * r_specific * t_c
            * (1.0 - pressure_ratio_e_c ** exponent)
        )
        return float(v_e / G_0)

    # ------------------------------------------------------------------ #
    # Level 1 — fast (equilibrium reference)
    # ------------------------------------------------------------------ #

    def _evaluate_fast(self, state: Dict) -> Dict:
        isp_fr = state['isp_frozen']
        isp_sh = state['isp_shifting']
        gap_pct = self._gap_pct(isp_fr, isp_sh)
        note = (
            "Equilibrium (shifting) reference: kinetic loss neglected by "
            "definition. The reported band upper bound is the fully frozen "
            "expansion limit (NASA CEA frozen/equilibrium bracket)."
        )
        note = self._join_notes(state['note_parts'], note)
        return self._build_result(
            fidelity_requested='fast', fidelity_used='fast',
            isp_frozen=isp_fr, isp_shifting=isp_sh, isp_predicted=isp_sh,
            loss_band_pct=[0.0, gap_pct], model_note=note,
            diagnostics={'frozen_shifting_gap_pct': gap_pct},
        )

    # ------------------------------------------------------------------ #
    # Level 2 — engineering (Damköhler log-sigmoid correlation)
    # ------------------------------------------------------------------ #

    def _evaluate_engineering(self, state: Dict,
                              characteristic_length: Optional[float],
                              throat_diameter: Optional[float]) -> Dict:
        l_star = characteristic_length if characteristic_length is not None \
            else self.DEFAULT_L_STAR_M
        if l_star <= 0:
            raise ValueError("characteristic_length must be positive")
        if throat_diameter is not None and throat_diameter <= 0:
            raise ValueError("throat_diameter must be positive")

        p_c_pa = state['p_c_bar'] * 1e5

        # Oda kalış (stay) süresi: t_res = V_c*rho_c/mdot = L*·rho_c·c*/P_c
        # (mdot = P_c·A_t/c*; Sutton & Biblarz 9. baskı, Eş. 8-9).
        t_res = l_star * state['rho_c'] * state['c_star'] / p_c_pa

        # Kimyasal (rekombinasyon) zamanı: tau ∝ P^-2 (üç-cisimli
        # rekombinasyon; Bray 1959, Vincenti & Kruger Böl. 8).
        tau_chem = self.TAU_CHEM_REF_S * (
            self.P_REF_BAR / state['p_c_bar']) ** self.PRESSURE_EXPONENT

        # Opsiyonel boyut faktörü: genişleme zaman ölçeği ∝ lüle boyutu.
        size_factor = 1.0
        if throat_diameter is not None:
            size_factor = throat_diameter / self.D_THROAT_REF_M

        damkohler = (t_res / tau_chem) * size_factor
        f_blend = self._blend_fraction(damkohler)

        isp_fr = state['isp_frozen']
        isp_sh = state['isp_shifting']
        gap = isp_sh - isp_fr
        gap_pct = self._gap_pct(isp_fr, isp_sh)
        isp_pred = isp_fr + f_blend * gap
        loss_pct = (1.0 - f_blend) * gap_pct

        # Bant: Da'yı belirsizlik çarpanı kadar iki yöne oynat.
        u = self.DA_UNCERTAINTY_FACTOR
        loss_lo = (1.0 - self._blend_fraction(damkohler * u)) * gap_pct
        loss_hi = (1.0 - self._blend_fraction(damkohler / u)) * gap_pct

        note = (
            "JANNAF-style engineering correlation: kinetic loss taken as a "
            "log-sigmoid blend between the frozen and shifting expansion "
            "limits, driven by a Damköhler-like parameter "
            "(t_res = L*.rho_c.c*/P_c, Sutton 9th ed. Eq. 8-9; "
            "tau_chem ~ P^-2, three-body recombination). Calibration "
            "constants are approximate — calibration against static-fire "
            "data recommended; the loss band reflects a x"
            f"{u:.0f} Damköhler uncertainty."
        )
        if gap <= 0:
            note = self._join_notes(
                ["frozen/shifting gap is zero, so the correlation has no "
                 "loss to distribute"], note)
        note = self._join_notes(state['note_parts'], note)

        return self._build_result(
            fidelity_requested='engineering', fidelity_used='engineering',
            isp_frozen=isp_fr, isp_shifting=isp_sh, isp_predicted=isp_pred,
            loss_band_pct=[loss_lo, loss_hi], model_note=note,
            diagnostics={
                'residence_time_s': t_res,
                'chemical_time_s': tau_chem,
                'damkohler': damkohler,
                'blend_fraction': f_blend,
                'size_factor': size_factor,
                'characteristic_length_m': l_star,
                'frozen_shifting_gap_pct': gap_pct,
            },
        )

    def _blend_fraction(self, damkohler: float) -> float:
        """Log-sigmoid blend: f = Da^n / (1 + Da^n) = 1/(1+exp(-n ln Da)).

        f -> 0 (frozen) küçük Da'da, f -> 1 (shifting) büyük Da'da; ln(Da)
        ekseninde simetrik sigmoid. n = SIGMOID_EXPONENT.
        """
        if damkohler <= 0:
            return 0.0
        dan = damkohler ** self.SIGMOID_EXPONENT
        return float(dan / (1.0 + dan))

    # ------------------------------------------------------------------ #
    # Level 3 — high fidelity (Cantera finite-rate along T(x), P(x))
    # ------------------------------------------------------------------ #

    def _evaluate_high_fidelity(self, cres: Dict, state: Dict,
                                nozzle_profile: Optional[Dict]) -> Dict:
        if not CANTERA_AVAILABLE or ct is None:
            raise HighFidelityUnavailable("Cantera is not installed")
        x, t_arr, p_arr, u_arr = self._validate_profile(nozzle_profile)

        gas = self._get_kinetics_gas()

        elements = cres.get('elemental_composition')
        if not elements:
            raise HighFidelityUnavailable(
                "combustion_results lacks 'elemental_composition'")
        comp_str = self._elements_to_mass_fraction_string(elements, gas)

        p_c_pa = state['p_c_bar'] * 1e5
        p_e_pa = float(p_arr[-1])

        try:
            # Oda dengesi: h0 (durağan entalpi), s0 ve referans bileşim.
            gas.TPY = state['t_c'], p_c_pa, comp_str
            gas.equilibrate('TP')
            h_0 = gas.enthalpy_mass
            s_0 = gas.entropy_mass
            t_0 = gas.T
            y_chamber = np.array(gas.Y)

            # İç-tutarlı frozen/shifting çifti — combustion_analysis'in
            # enerji yöntemiyle AYNI fizik (Sutton Eş. 3-15b, NASA RP-1311),
            # ama BU mekanizma ve BU profilin çıkış basıncında. Böylece
            # sonlu-hız tahmini garanti aynı çerçevede köşelenir.
            gas.SP = s_0, p_e_pa
            gas.equilibrate('SP')
            h_e_shift = gas.enthalpy_mass
            t_e_shift = gas.T
            v_sh = float(np.sqrt(2.0 * max(h_0 - h_e_shift, 0.0)))
            isp_sh = v_sh / G_0

            gas.TPY = t_0, p_c_pa, y_chamber
            gas.SP = s_0, p_e_pa  # equilibrate YOK -> frozen bileşim
            isp_fr = float(np.sqrt(2.0 * max(h_0 - gas.enthalpy_mass, 0.0)) / G_0)
        except Exception as exc:
            raise HighFidelityUnavailable(
                f"chamber equilibrium / bracket solution failed: {exc}")

        if not (0 < isp_fr <= isp_sh):
            raise HighFidelityUnavailable(
                f"non-physical frozen/shifting bracket "
                f"(frozen={isp_fr:.1f}, shifting={isp_sh:.1f})")

        # x -> t dönüşümü: hız verilmişse doğrudan; yoksa entalpi açığından
        # (frozen bileşimle) u = sqrt(2 max(h0 - h(T,P,Y_oda), 0)).
        if u_arr is None:
            u_arr = np.empty_like(x)
            for i in range(len(x)):
                gas.TPY = t_arr[i], p_arr[i], y_chamber
                u_arr[i] = np.sqrt(2.0 * max(h_0 - gas.enthalpy_mass, 0.0))
        u_arr = np.maximum(u_arr, self.U_MIN_M_S)
        inv_u = 1.0 / u_arr
        t_grid = np.concatenate(
            ([0.0], np.cumsum(np.diff(x) * 0.5 * (inv_u[1:] + inv_u[:-1]))))
        t_end = float(t_grid[-1])
        if t_end <= 0:
            raise HighFidelityUnavailable("profile residence time is zero")

        mw_species = np.array(gas.molecular_weights)

        def rhs(t, y):
            # Tür korunumu: dY_k/dt = wdot_k * W_k / rho, T(t), P(t) profilden
            # dayatılır (quasi-1D reaksiyon-izli genişleme).
            y_loc = np.clip(y, 0.0, None)
            total = y_loc.sum()
            if total > 0:
                y_loc = y_loc / total
            temp = np.interp(t, t_grid, t_arr)
            pres = np.interp(t, t_grid, p_arr)
            gas.TPY = temp, pres, y_loc
            return gas.net_production_rates * mw_species / gas.density

        try:
            sol = solve_ivp(rhs, (0.0, t_end), y_chamber, method='BDF',
                            rtol=1e-6, atol=1e-12)
        except Exception as exc:
            raise HighFidelityUnavailable(f"BDF integration raised: {exc}")
        if not sol.success:
            raise HighFidelityUnavailable(
                f"BDF integration failed: {sol.message}")

        y_exit = np.clip(sol.y[:, -1], 0.0, None)
        y_exit = y_exit / y_exit.sum()

        # Kinetik kayıp = rekombine OLAMAYAN radikallerde kilitli kalan
        # kimyasal (oluşum) entalpisi. Aynı (T, P) noktasında kinetik ve
        # denge bileşimlerinin entalpi FARKI alınır ki dayatılan T(x)
        # profilinin keyfî duyulur-ısı içeriği kaybı kirletmesin (profil
        # T'si doğrudan h_çıkış olarak kullanılsaydı enerji dengesi çift
        # sayılırdı). v_pred² = v_shifting² - 2·Δh_chem; Δh_chem >= 0
        # (süper-denge rekombinasyonu fiziksel değil -> 0'a kırpılır).
        # Bray ani-donma limitleri: Y_exit -> Y_denge iken Δh_chem -> 0
        # (shifting), Y_exit -> Y_oda iken v_pred -> frozen (cp farkı
        # mertebesinde küçük bir artıkla; köşeleme garantisi bunu örter).
        gas.TPY = t_e_shift, p_e_pa, y_exit
        h_kin_at_t_shift = gas.enthalpy_mass
        dh_chem = max(h_kin_at_t_shift - h_e_shift, 0.0)
        v_pred = float(np.sqrt(max(v_sh ** 2 - 2.0 * dh_chem, 0.0)))
        isp_pred = v_pred / G_0

        gap_pct = self._gap_pct(isp_fr, isp_sh)
        loss_pct = max(0.0, (isp_sh - isp_pred) / isp_sh * 100.0)
        loss_lo = max(0.0, loss_pct * (1.0 - self.HF_BAND_REL))
        loss_hi = min(gap_pct, loss_pct * (1.0 + self.HF_BAND_REL)) \
            if gap_pct > 0 else 0.0
        loss_hi = max(loss_hi, loss_lo)

        note = (
            "Finite-rate species integration (Cantera BDF) along the "
            "prescribed nozzle T(x), P(x) path; frozen/shifting bracket "
            "recomputed with the same mechanism at the profile exit pressure "
            "(energy method, Sutton 9th ed. Eq. 3-15b / NASA RP-1311). "
            "Kinetic loss taken as the chemical-enthalpy defect of the "
            "unrecombined species relative to shifting equilibrium at the "
            "exit state, so an approximate imposed T(x) profile cannot "
            "corrupt the energy balance. Loss band reflects rate-constant "
            "uncertainty (dominant TDK error source per JANNAF practice)."
        )
        note = self._join_notes(state['note_parts'], note)

        return self._build_result(
            fidelity_requested='high_fidelity', fidelity_used='high_fidelity',
            isp_frozen=isp_fr, isp_shifting=isp_sh, isp_predicted=isp_pred,
            loss_band_pct=[loss_lo, loss_hi], model_note=note,
            diagnostics={
                'mechanism': self._kin_mech_name,
                'n_species': int(gas.n_species),
                'n_reactions': int(gas.n_reactions),
                'residence_time_s': t_end,
                'exit_pressure_pa': p_e_pa,
                'frozen_shifting_gap_pct': gap_pct,
            },
        )

    def _get_kinetics_gas(self):
        """Return (and cache) a Cantera Solution WITH finite-rate reactions.

        combustion_analysis ile aynı mekanizma ailesi denenir; nasa_gas.yaml
        bilinçli olarak atlanır çünkü yalnız termodinamik veri taşır
        (n_reactions == 0) ve sonlu-hız entegrasyonunu süremez.
        """
        if self._kin_gas is not None:
            return self._kin_gas
        candidates = (self.mechanism,) if self.mechanism \
            else self.DEFAULT_KINETIC_MECHANISMS
        for mech in candidates:
            try:
                gas = ct.Solution(mech)
            except Exception:
                continue
            if gas.n_reactions > 0:
                self._kin_gas = gas
                self._kin_mech_name = mech
                return gas
        raise HighFidelityUnavailable(
            "no Cantera mechanism with finite-rate reactions available "
            f"(tried: {', '.join(str(c) for c in candidates)})"
        )

    @staticmethod
    def _elements_to_mass_fraction_string(elements: Dict, gas) -> str:
        """Elemental mass fractions -> Cantera atomic-species Y string.

        combustion_analysis._elements_to_cantera_composition ile aynı desen:
        atomik tür mekanizmada yoksa (örn. AL, gri30'da yok) zarif düşüş
        için HighFidelityUnavailable yükseltilir.
        """
        species_names = set(gas.species_names)
        parts = []
        for element, mass_frac in elements.items():
            if mass_frac and mass_frac > 1e-10:
                if element not in species_names:
                    raise HighFidelityUnavailable(
                        f"mechanism lacks atomic species '{element}'")
                parts.append(f"{element}:{mass_frac:.6f}")
        if not parts:
            raise HighFidelityUnavailable("empty elemental composition")
        return ",".join(parts)

    @staticmethod
    def _validate_profile(nozzle_profile: Optional[Dict]):
        if not nozzle_profile:
            raise HighFidelityUnavailable(
                "nozzle_profile (x [m], T [K], P [Pa]) not provided")
        try:
            x = np.asarray(nozzle_profile['x'], dtype=float)
            t_arr = np.asarray(nozzle_profile['T'], dtype=float)
            p_arr = np.asarray(nozzle_profile['P'], dtype=float)
        except (KeyError, TypeError, ValueError) as exc:
            raise HighFidelityUnavailable(
                f"nozzle_profile must carry numeric 'x', 'T', 'P' arrays ({exc})")
        if not (len(x) == len(t_arr) == len(p_arr)) or len(x) < 2:
            raise HighFidelityUnavailable(
                "profile arrays must share a common length >= 2")
        if not np.all(np.diff(x) > 0):
            raise HighFidelityUnavailable("'x' must be strictly increasing")
        if np.any(t_arr <= 0) or np.any(p_arr <= 0):
            raise HighFidelityUnavailable("'T' and 'P' must be positive")
        u_arr = None
        if 'u' in nozzle_profile and nozzle_profile['u'] is not None:
            u_arr = np.asarray(nozzle_profile['u'], dtype=float)
            if len(u_arr) != len(x) or np.any(u_arr <= 0):
                raise HighFidelityUnavailable(
                    "'u' must be positive and match the profile length")
        return x, t_arr, p_arr, u_arr

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _gap_pct(isp_frozen: float, isp_shifting: float) -> float:
        if isp_shifting <= 0:
            return 0.0
        return max(0.0, (isp_shifting - isp_frozen) / isp_shifting * 100.0)

    @staticmethod
    def _join_notes(parts: Sequence[str], base: str) -> str:
        extra = "; ".join(p for p in parts if p)
        return f"{base} [{extra}]" if extra else base

    def _build_result(self, fidelity_requested: str, fidelity_used: str,
                      isp_frozen: float, isp_shifting: float,
                      isp_predicted: float, loss_band_pct: List[float],
                      model_note: str, diagnostics: Dict) -> Dict:
        # Fiziksel köşeleme: frozen <= predicted <= shifting her seviyede
        # garanti edilir (Bray sınırları); kırpma diagnostics'e işlenir.
        clamped = not (isp_frozen <= isp_predicted <= isp_shifting)
        isp_predicted = float(np.clip(isp_predicted, isp_frozen, isp_shifting))
        loss_pct = self._gap_pct(isp_predicted, isp_shifting)
        lo, hi = float(min(loss_band_pct)), float(max(loss_band_pct))
        lo = max(0.0, min(lo, loss_pct))
        hi = max(hi, loss_pct)
        diagnostics = dict(diagnostics)
        diagnostics['prediction_clamped_to_bracket'] = clamped
        return {
            'fidelity_requested': fidelity_requested,
            'fidelity_used': fidelity_used,
            'isp_frozen': float(isp_frozen),
            'isp_shifting': float(isp_shifting),
            'isp_predicted': float(isp_predicted),
            'kinetic_loss_pct': float(loss_pct),
            'loss_band_pct': [lo, hi],
            'model_note': model_note,
            'diagnostics': diagnostics,
        }


# Modül seviyesinde hazır örnek (repo genelindeki desen; kurulum tembel
# olduğundan import maliyeti yoktur).
kinetic_efficiency = KineticEfficiency()
