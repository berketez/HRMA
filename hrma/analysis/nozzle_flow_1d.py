"""
Quasi-1D Compressible Nozzle Flow Module (successor of the mock CFD panel).

Fast, physically honest quasi-one-dimensional nozzle gas dynamics for the
Fast Screening / Engineering fidelity levels (docs/ANALIZ_PLATFORM_PLANI.md,
Wave 4). No CFD claims are made: the model is inviscid quasi-1D isentropic
flow with a normal-shock branch, a literature separation criterion, and an
axial Bartz heat-transfer coupling. Viscous losses are simple engineering
estimates and are explicitly tagged ``'approximate'``.

Physics and references
----------------------
Isentropic core (station marching):
  - Area-Mach relation, T/T0, P/P0, rho/rho0:
      Anderson, "Modern Compressible Flow", 3rd ed., Eqs. 3.28-3.31 & 5.20;
      NASA GRC "Isentropic Flow Equations"; Sutton & Biblarz 9th ed. Eq. 3-14.
  - The subsonic branch is used in the convergent section, the supersonic
    branch in the divergent section; both are solved with Brent's method
    via ``HeatTransferAnalyzer._mach_from_area_ratio`` (single shared
    implementation — parameter-consistency rule, no copies).

Normal shock branch:
  - Rankine-Hugoniot normal-shock relations (M2, P2/P1, P02/P01):
      Anderson, "Modern Compressible Flow", 3rd ed., Eqs. 3.51, 3.57, 3.63;
      NACA Report 1135 (1953), Eqs. 93-99.
  - Shock position found by matching the post-shock subsonic isentropic
    diffusion to the ambient back pressure (classic quasi-1D matching,
    Anderson Ch. 5.4).

Flow separation:
  - Summerfield criterion: the boundary layer in an overexpanded nozzle
    separates where the wall pressure falls below roughly 0.35-0.40 of the
    ambient pressure.
      Summerfield, M., Foster, C.R., Swan, W.C., "Flow Separation in
      Overexpanded Supersonic Exhaust Nozzles", Jet Propulsion 24 (1954);
      Sutton & Biblarz, 9th ed., Ch. 3 (separation discussion).
    Default factor 0.40 (conservative end of the band); the separation
    station and the effective exit pressure are reported.

Thrust / CF:
  - Momentum + pressure-difference thrust, F = mdot*u_e + (P_e - P_a)*A_e,
    and ideal thrust coefficient: Sutton & Biblarz 9th ed. Eqs. 2-14, 3-29,
    3-30. A wall-pressure integral over the divergent section is reported
    as a numerical cross-check of the exit-plane formula.
  - Divergence factor, conical: lambda = (1 + cos(alpha))/2
    (Malina 1940; Sutton & Biblarz 9th ed. Eq. 3-34). For bell nozzles the
    conical formula is evaluated at the mean of the initial and exit wall
    angles — the standard engineering approximation (Huzel & Huang,
    "Modern Engineering for Design of Liquid-Propellant Rocket Engines",
    Ch. 1 bell-nozzle equivalent-cone treatment). Tagged 'approximate'.
  - Friction / boundary-layer thrust loss: typically 0.5-2 % in well
    designed nozzles (Sutton & Biblarz 9th ed. Sec. 3.5 nozzle losses;
    Huzel & Huang Ch. 1). Modeled as a single user-adjustable fraction
    (default 1.5 %), tagged 'approximate' — this is NOT a boundary-layer
    solution, only a bookkeeping estimate.

Axial heat-transfer coupling:
  - Bartz gas-side coefficient h_g(x) is computed by IMPORTING
    ``HeatTransferAnalyzer._bartz_coefficient`` (Bartz 1957; Sutton &
    Biblarz 9th ed. Eq. 8-22, SI-consistent form) at every station —
    the correlation is NOT re-implemented here (single source of truth,
    same convention as ``HeatTransferAnalyzer.analyze_axial_profile``).
  - q(x) = h_g(x) * (Taw(x) - Tw_ref) is the CONVECTIVE design flux only;
    radiation and wall energy balance belong to the heat-transfer module.

Geometry:
  - The nozzle inner contour comes from the single shared sampler
    ``hrma.engines.nozzle_design.sample_nozzle_inner_contour`` (same
    geometry as 2D/3D/CAD outputs — no duplicated contour math).

Units: SI throughout the class API (Pa, K, m, kg/s). The repo-style
``motor_data`` dictionaries (chamber_pressure in bar) are supported via
``NozzleFlow1D.from_motor_data``.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple

from scipy.optimize import brentq

# Tek kaynak: Bartz korelasyonu, gaz özellik modeli, alan-Mach çözücü ve
# evrensel gaz sabiti heat_transfer_analysis'ten İTHAL edilir (kopya yok).
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer, R_UNIVERSAL

__all__ = [
    'NozzleFlow1D',
    'isentropic_ratios',
    'area_ratio_from_mach',
    'normal_shock_relations',
    'ideal_thrust_coefficient',
]

# ---------------------------------------------------------------------------
# İstasyon sayısı sınırları (Dalga 4 planı: 30-60 istasyon)
# ---------------------------------------------------------------------------
N_STATIONS_MIN = 30
N_STATIONS_MAX = 60

# Summerfield ayrılma katsayısı literatür bandı (Summerfield 1954: 0.35-0.40)
SEPARATION_FACTOR_DEFAULT = 0.40
SEPARATION_FACTOR_MIN = 0.20   # geniş güvenlik bandı (kullanıcı deneyleri için)
SEPARATION_FACTOR_MAX = 0.60

# "Perfectly expanded" sınıflandırma toleransı: |Pe - Pa| <= tol * Pe.
# Mühendislik toleransı (tam eşitlik sayısal olarak anlamsız).
PERFECT_EXPANSION_REL_TOL = 0.01


# ===========================================================================
# Modül-düzeyi gaz dinamiği yardımcıları (analitik, birim testli)
# ===========================================================================
def isentropic_ratios(mach: float, gamma: float) -> Tuple[float, float, float]:
    """Isentropic static/stagnation ratios (T/T0, P/P0, rho/rho0).

    Anderson, "Modern Compressible Flow", 3rd ed., Eqs. 3.28-3.31;
    NASA GRC Isentropic Flow Equations:
        T/T0   = [1 + (g-1)/2 * M^2]^-1
        P/P0   = (T/T0)^(g/(g-1))
        rho/rho0 = (T/T0)^(1/(g-1))
    """
    t_ratio = 1.0 / (1.0 + 0.5 * (gamma - 1.0) * mach * mach)
    p_ratio = t_ratio ** (gamma / (gamma - 1.0))
    rho_ratio = t_ratio ** (1.0 / (gamma - 1.0))
    return t_ratio, p_ratio, rho_ratio


def area_ratio_from_mach(mach: float, gamma: float) -> float:
    """A/A* from Mach number (forward area-Mach relation).

    Anderson, "Modern Compressible Flow", 3rd ed., Eq. 5.20;
    Sutton & Biblarz 9th ed. Eq. 3-14:
        A/A* = (1/M) * [ (2/(g+1)) * (1 + (g-1)/2 M^2) ]^((g+1)/(2(g-1)))
    """
    if mach <= 0.0:
        raise ValueError("Mach number must be positive for the area-Mach relation.")
    exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))
    return (1.0 / mach) * ((2.0 / (gamma + 1.0))
                           * (1.0 + 0.5 * (gamma - 1.0) * mach * mach)) ** exponent


def normal_shock_relations(mach1: float, gamma: float) -> Tuple[float, float, float]:
    """Normal-shock jump relations: returns (M2, P2/P1, P02/P01).

    Anderson, "Modern Compressible Flow", 3rd ed., Eqs. 3.51, 3.57, 3.63;
    NACA Report 1135 (1953), Eqs. 93-99:
        M2^2     = [1 + (g-1)/2 M1^2] / [g M1^2 - (g-1)/2]
        P2/P1    = 1 + 2g/(g+1) (M1^2 - 1)
        P02/P01  = [ ((g+1)/2 M1^2) / (1 + (g-1)/2 M1^2) ]^(g/(g-1))
                   * [ (g+1) / (2g M1^2 - (g-1)) ]^(1/(g-1))
    """
    if mach1 <= 1.0:
        raise ValueError("Normal shock requires an upstream Mach number > 1.")
    m1sq = mach1 * mach1
    m2 = np.sqrt((1.0 + 0.5 * (gamma - 1.0) * m1sq)
                 / (gamma * m1sq - 0.5 * (gamma - 1.0)))
    p2_p1 = 1.0 + 2.0 * gamma / (gamma + 1.0) * (m1sq - 1.0)
    p02_p01 = ((0.5 * (gamma + 1.0) * m1sq / (1.0 + 0.5 * (gamma - 1.0) * m1sq))
               ** (gamma / (gamma - 1.0))
               * ((gamma + 1.0) / (2.0 * gamma * m1sq - (gamma - 1.0)))
               ** (1.0 / (gamma - 1.0)))
    return float(m2), float(p2_p1), float(p02_p01)


def ideal_thrust_coefficient(gamma: float, pe_over_pc: float,
                             pa_over_pc: float, expansion_ratio: float) -> float:
    """Ideal thrust coefficient CF (Sutton & Biblarz 9th ed. Eq. 3-30):

        CF = sqrt( 2g^2/(g-1) * (2/(g+1))^((g+1)/(g-1))
                   * [1 - (Pe/Pc)^((g-1)/g)] )
             + (Pe/Pc - Pa/Pc) * (Ae/At)
    """
    momentum_term = (2.0 * gamma * gamma / (gamma - 1.0)
                     * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
                     * (1.0 - pe_over_pc ** ((gamma - 1.0) / gamma)))
    return float(np.sqrt(max(momentum_term, 0.0))
                 + (pe_over_pc - pa_over_pc) * expansion_ratio)


# ===========================================================================
# Ana sınıf
# ===========================================================================
class NozzleFlow1D:
    """Quasi-1D compressible nozzle flow solver (Engineering fidelity).

    Parameters
    ----------
    chamber_pressure : float
        Chamber (stagnation) pressure [Pa].
    chamber_temperature : float
        Chamber (stagnation) temperature [K].
    gamma : float
        Ratio of specific heats (frozen), 1.05 < gamma < 1.67.
    molecular_weight : float
        Combustion-gas molecular weight [g/mol] (same convention as
        ``HeatTransferAnalyzer``; default 24 g/mol typical hybrid mix).
    throat_diameter, exit_diameter : float
        Nozzle throat / exit diameters [m]. ``expansion_ratio`` may be given
        instead of ``exit_diameter``.
    ambient_pressure : float
        Ambient back pressure [Pa]; 0 selects vacuum.
    n_stations : int
        Number of axial stations, clamped to [30, 60] (Wave-4 plan).
    separation_factor : float
        Summerfield separation factor k in P_wall < k * P_ambient
        (literature band 0.35-0.40; default 0.40, conservative end).
    wall_temperature : float or None
        Reference cooled-wall temperature [K] for the reported convective
        flux q = h_g*(Taw - Tw). Default 800 K — representative actively
        cooled metallic wall (Huzel & Huang Ch. 4 regenerative designs run
        gas-side wall temperatures of a few hundred to ~900 K). Pass your
        own value for a material-specific flux map.
    friction_loss_fraction : float
        Approximate friction / boundary-layer thrust loss fraction
        (default 0.015 = 1.5 %; typical 0.5-2 %, Sutton 9th ed. Sec. 3.5).
    motor_data : dict, optional
        Repo-style motor dictionary; forwarded to the shared contour
        sampler (chamber diameter, nozzle type, bell angles, ...) and to
        the gas-property resolver (transport-property overrides).
    """

    REGIME_UNDEREXPANDED = 'underexpanded'
    REGIME_PERFECT = 'perfectly_expanded'
    REGIME_OVEREXPANDED = 'overexpanded'
    REGIME_SHOCK = 'normal_shock_in_nozzle'
    REGIME_SEPARATED = 'separated'
    REGIME_UNCHOKED = 'unchoked'   # roket dışı kenar durumu (uyarıyla döner)

    def __init__(self,
                 chamber_pressure: float,
                 chamber_temperature: float,
                 gamma: float = 1.2,
                 molecular_weight: float = 24.0,
                 throat_diameter: Optional[float] = None,
                 exit_diameter: Optional[float] = None,
                 expansion_ratio: Optional[float] = None,
                 ambient_pressure: float = 101325.0,
                 n_stations: int = 45,
                 separation_factor: float = SEPARATION_FACTOR_DEFAULT,
                 wall_temperature: Optional[float] = 800.0,
                 friction_loss_fraction: float = 0.015,
                 motor_data: Optional[Dict] = None):
        # --- doğrulamalar (İngilizce hata metinleri: kullanıcıya görünür) ---
        if not (chamber_pressure > 0.0):
            raise ValueError("chamber_pressure must be positive [Pa].")
        if not (chamber_temperature > 0.0):
            raise ValueError("chamber_temperature must be positive [K].")
        if not (1.05 < gamma < 1.67):
            raise ValueError("gamma must be within (1.05, 1.67) — same guard "
                             "band as the heat-transfer module.")
        if not (molecular_weight > 0.0):
            raise ValueError("molecular_weight must be positive [g/mol].")
        if ambient_pressure < 0.0:
            raise ValueError("ambient_pressure must be >= 0 [Pa].")
        if ambient_pressure >= chamber_pressure:
            raise ValueError("ambient_pressure must be below chamber_pressure "
                             "— otherwise there is no nozzle flow.")
        if not (SEPARATION_FACTOR_MIN <= separation_factor <= SEPARATION_FACTOR_MAX):
            raise ValueError(
                f"separation_factor must be within "
                f"[{SEPARATION_FACTOR_MIN}, {SEPARATION_FACTOR_MAX}] "
                f"(Summerfield literature band is 0.35-0.40).")
        if not (0.0 <= friction_loss_fraction < 0.2):
            raise ValueError("friction_loss_fraction must be within [0, 0.2).")

        self.motor_data = dict(motor_data or {})

        # --- geometri çözümü: boğaz/çıkış çapı veya genişleme oranı ---
        if throat_diameter is None:
            throat_diameter = self.motor_data.get('throat_diameter')
        if throat_diameter is None or not (float(throat_diameter) > 0.0):
            raise ValueError("throat_diameter must be provided and positive [m].")
        throat_diameter = float(throat_diameter)

        if exit_diameter is None:
            if expansion_ratio is not None:
                if not (float(expansion_ratio) > 1.0):
                    raise ValueError("expansion_ratio must be > 1.")
                exit_diameter = throat_diameter * float(np.sqrt(float(expansion_ratio)))
            else:
                exit_diameter = self.motor_data.get('exit_diameter')
        if exit_diameter is None or not (float(exit_diameter) > throat_diameter):
            raise ValueError("exit_diameter must exceed throat_diameter "
                             "(supersonic nozzle, expansion ratio > 1).")
        exit_diameter = float(exit_diameter)

        self.chamber_pressure = float(chamber_pressure)       # Pa
        self.chamber_temperature = float(chamber_temperature)  # K
        self.gamma = float(gamma)
        self.molecular_weight = float(molecular_weight)        # g/mol
        self.throat_diameter = throat_diameter                 # m
        self.exit_diameter = exit_diameter                     # m
        self.ambient_pressure = float(ambient_pressure)        # Pa
        self.n_stations = int(min(max(int(n_stations), N_STATIONS_MIN),
                                  N_STATIONS_MAX))
        self.separation_factor = float(separation_factor)
        self.wall_temperature = (None if wall_temperature is None
                                 else float(wall_temperature))
        self.friction_loss_fraction = float(friction_loss_fraction)

        # Isı transferi yardımcıları (Bartz + alan-Mach çözücü) — tek kaynak.
        self._hta = HeatTransferAnalyzer()

    # ------------------------------------------------------------------
    # Yapıcı yardımcıları
    # ------------------------------------------------------------------
    @classmethod
    def from_motor_data(cls, motor_data: Dict,
                        ambient_pressure: float = 101325.0,
                        **kwargs) -> 'NozzleFlow1D':
        """Build from a repo-style motor dictionary.

        Repo convention (see ``HeatTransferAnalyzer.analyze_heat_transfer``):
        ``chamber_pressure`` in bar, temperatures in K, diameters in m.
        """
        md = dict(motor_data or {})
        return cls(
            chamber_pressure=float(md.get('chamber_pressure', 20.0)) * 1e5,
            chamber_temperature=float(md.get('chamber_temperature', 3000.0)),
            gamma=float(md.get('gamma', md.get('gamma_avg', 1.2))),
            molecular_weight=float(md.get('molecular_weight', 24.0)),
            throat_diameter=md.get('throat_diameter'),
            exit_diameter=md.get('exit_diameter'),
            expansion_ratio=md.get('expansion_ratio'),
            ambient_pressure=ambient_pressure,
            motor_data=md,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Geometri: ortak kontur örnekleyiciden istasyon ızgarası
    # ------------------------------------------------------------------
    def _build_stations(self) -> Dict:
        """Sample the shared nozzle contour and build the axial station grid.

        The throat station is ALWAYS on the grid (M=1 anchored exactly).
        Returns x [mm], r [mm], area ratio A/A_t (>=1) and section indices.
        """
        # Tembel import: hrma.engines.__init__ -> hybrid_rocket_engine ->
        # analysis zinciri modül-üstü importta döngü riski taşır (aynı
        # gerekçe analyze_axial_profile içinde belgelidir).
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour

        md_geo = dict(self.motor_data)
        md_geo['throat_diameter'] = self.throat_diameter
        md_geo['exit_diameter'] = self.exit_diameter
        # Kamara çapı verilmemişse NozzleDesigner geleneğiyle uyumlu
        # varsayılan: r_kamara ~ 1.5 * r_boğaz (sample_nozzle_inner_contour
        # docstring'inde belgelenen daralma kabulü).
        md_geo.setdefault('chamber_diameter', 1.5 * self.throat_diameter)

        contour_pts, contour_meta = sample_nozzle_inner_contour(md_geo)
        z_pts = np.array([p[0] for p in contour_pts], dtype=float)  # mm
        r_pts = np.array([p[1] for p in contour_pts], dtype=float)  # mm
        z_throat = float(contour_meta['z_throat'])
        z_exit = float(contour_meta['z_exit'])
        r_throat = float(contour_meta['r_throat'])

        # Boğaz istasyonu garantili ızgara (analyze_axial_profile ile aynı
        # bölüşüm ilkesi: uzunlukla orantılı pay, boğaz ortak uç).
        n = self.n_stations
        frac_conv = z_throat / z_exit if z_exit > 0 else 0.5
        n_conv = int(round(n * frac_conv))
        n_conv = min(max(n_conv, 2), n - 2)
        n_div = n - n_conv + 1  # boğaz istasyonu paylaşılır
        x_conv = np.linspace(0.0, z_throat, n_conv)
        x_div = np.linspace(z_throat, z_exit, n_div)[1:]
        x_mm = np.concatenate([x_conv, x_div])
        throat_index = n_conv - 1

        r_mm = np.interp(x_mm, z_pts, r_pts)
        area_ratio = np.maximum((r_mm / r_throat) ** 2, 1.0)
        area_ratio[throat_index] = 1.0  # interp toleransına karşı kesin boğaz

        # Diverjan cidar açıları (viskoz/dağılma kaybı için):
        # eğimler ham kontur noktalarından (istasyon interp'inden değil).
        div_mask = z_pts >= z_throat - 1e-9
        zd, rd = z_pts[div_mask], r_pts[div_mask]
        dz = np.diff(zd)
        dr = np.diff(rd)
        valid = dz > 1e-12
        slopes = np.arctan2(dr[valid], dz[valid])  # rad
        theta_exit = float(slopes[-1]) if slopes.size else 0.0
        theta_max = float(np.max(slopes)) if slopes.size else 0.0

        return {
            'x_mm': x_mm,
            'r_mm': r_mm,
            'area_ratio': area_ratio,
            'throat_index': throat_index,
            'x_throat_mm': z_throat,
            'x_exit_mm': z_exit,
            'nozzle_type': contour_meta.get('noz_type', 'conical'),
            'theta_exit_rad': theta_exit,
            'theta_n_rad': theta_max,
        }

    # ------------------------------------------------------------------
    # Rejim eşikleri ve sınıflandırma
    # ------------------------------------------------------------------
    def _mach_from_area(self, area_ratio: float, supersonic: bool) -> float:
        # Tek kaynak çözücü (Sutton Eq. 3-14, Brent) — kopya yok.
        return HeatTransferAnalyzer._mach_from_area_ratio(
            float(area_ratio), self.gamma, supersonic)

    def _classify_regime(self, eps_exit: float) -> Dict:
        """Classify the operating regime from the exit/ambient pressures.

        Decision ladder in increasing back pressure (classic quasi-1D,
        Anderson Ch. 5.4, with the Summerfield separation overlay):

          Pa < Pe(1-tol)                       -> underexpanded
          |Pa - Pe| <= tol*Pe                  -> perfectly expanded
          Pe(1+tol) < Pa <= Pe/k               -> overexpanded (attached)
          Pe/k < Pa <= P_shock_at_exit         -> SEPARATED (Summerfield)
          P_shock_at_exit < Pa < P_exit_subsonic -> normal shock in nozzle
          Pa >= P_exit_subsonic                -> unchoked (edge case, warn)

        Note: in the normal-shock band real nozzle flows also separate;
        the pure normal-shock solution is the textbook quasi-1D limit and
        is labeled as such in the description.
        """
        g = self.gamma
        pc = self.chamber_pressure
        pa = self.ambient_pressure

        mach_exit_sup = self._mach_from_area(eps_exit, supersonic=True)
        _, p_ratio_sup, _ = isentropic_ratios(mach_exit_sup, g)
        p_exit_isentropic = pc * p_ratio_sup

        mach_exit_sub = self._mach_from_area(eps_exit, supersonic=False)
        _, p_ratio_sub, _ = isentropic_ratios(mach_exit_sub, g)
        p_exit_subsonic = pc * p_ratio_sub

        _, p2_p1_exit, _ = normal_shock_relations(mach_exit_sup, g)
        p_shock_at_exit = p_exit_isentropic * p2_p1_exit

        thresholds = {
            'perfect_expansion_low_Pa': p_exit_isentropic * (1.0 - PERFECT_EXPANSION_REL_TOL),
            'perfect_expansion_high_Pa': p_exit_isentropic * (1.0 + PERFECT_EXPANSION_REL_TOL),
            'separation_onset_Pa': p_exit_isentropic / self.separation_factor,
            'shock_at_exit_Pa': p_shock_at_exit,
            'unchoked_above_Pa': p_exit_subsonic,
        }

        if pa >= p_exit_subsonic:
            regime = self.REGIME_UNCHOKED
            description = ("Back pressure exceeds the fully subsonic exit "
                           "pressure: the nozzle is not choked. This is not "
                           "a rocket operating point; results are limited "
                           "to the classification.")
        elif pa > p_shock_at_exit:
            regime = self.REGIME_SHOCK
            description = ("Back pressure is high enough to push a normal "
                           "shock inside the divergent section (textbook "
                           "quasi-1D solution; real flows also show "
                           "boundary-layer separation in this band).")
        elif p_exit_isentropic < self.separation_factor * pa:
            regime = self.REGIME_SEPARATED
            description = (f"Overexpanded flow separates from the nozzle "
                           f"wall (Summerfield criterion: wall pressure < "
                           f"{self.separation_factor:.2f} x ambient).")
        elif pa > thresholds['perfect_expansion_high_Pa']:
            regime = self.REGIME_OVEREXPANDED
            description = ("Overexpanded: exit pressure below ambient, flow "
                           "attached (oblique shocks outside the nozzle).")
        elif pa >= thresholds['perfect_expansion_low_Pa']:
            regime = self.REGIME_PERFECT
            description = ("Perfectly expanded: exit pressure matches the "
                           "ambient pressure (within the classification "
                           "tolerance).")
        else:
            regime = self.REGIME_UNDEREXPANDED
            description = ("Underexpanded: exit pressure above ambient; "
                           "expansion continues outside the nozzle "
                           "(vacuum operation is the limiting case).")

        return {
            'type': regime,
            'description': description,
            'exit_mach_supersonic': mach_exit_sup,
            'exit_pressure_isentropic_Pa': p_exit_isentropic,
            'exit_pressure_subsonic_Pa': p_exit_subsonic,
            'ambient_pressure_Pa': pa,
            'pressure_ratio_Pe_over_Pa': (p_exit_isentropic / pa) if pa > 0 else None,
            'separation_criterion': (
                f"Summerfield (1954): separation where P_wall < "
                f"{self.separation_factor:.2f} * P_ambient "
                f"(literature band 0.35-0.40)"),
            'classification_tolerance': PERFECT_EXPANSION_REL_TOL,
            'thresholds_Pa': thresholds,
        }

    # ------------------------------------------------------------------
    # Ayrılma istasyonu (Summerfield)
    # ------------------------------------------------------------------
    def _solve_separation(self, geo: Dict) -> Dict:
        """Locate the Summerfield separation station in the divergent section.

        Solves P_wall(eps) = k * P_ambient on the supersonic isentropic
        branch (wall pressure decreases monotonically along the divergent),
        then interpolates the axial location from the station grid.
        """
        g = self.gamma
        pc = self.chamber_pressure
        target = self.separation_factor * self.ambient_pressure

        def wall_pressure_minus_target(eps):
            m = self._mach_from_area(eps, supersonic=True)
            _, p_ratio, _ = isentropic_ratios(m, g)
            return pc * p_ratio - target

        eps_exit = float(geo['area_ratio'][-1])
        eps_sep = float(brentq(wall_pressure_minus_target,
                               1.0 + 1e-9, eps_exit, xtol=1e-12, maxiter=200))

        i_t = geo['throat_index']
        eps_div = geo['area_ratio'][i_t:]
        x_div = geo['x_mm'][i_t:]
        x_sep_mm = float(np.interp(eps_sep, eps_div, x_div))

        mach_sep = self._mach_from_area(eps_sep, supersonic=True)
        t_ratio, p_ratio, _ = isentropic_ratios(mach_sep, g)
        r_gas = R_UNIVERSAL / self.molecular_weight  # J/(kg*K)
        temp_sep = self.chamber_temperature * t_ratio
        u_sep = mach_sep * float(np.sqrt(g * r_gas * temp_sep))

        return {
            'station_x_mm': x_sep_mm,
            'area_ratio': eps_sep,
            'mach': mach_sep,
            'wall_pressure_Pa': pc * p_ratio,       # = k * Pa (kriter gereği)
            'effective_exit_pressure_Pa': pc * p_ratio,
            'effective_expansion_ratio': eps_sep,
            'velocity_m_s': u_sep,
            'criterion_factor': self.separation_factor,
            'downstream_wall_pressure_Pa': self.ambient_pressure,
            'note': ("Downstream of separation the wall pressure is modeled "
                     "as the ambient-pressure plateau (first-order "
                     "Summerfield treatment); the separation plane acts as "
                     "the effective nozzle exit for thrust."),
        }

    # ------------------------------------------------------------------
    # Lüle içi normal şok konumu (klasik quasi-1D eşleme)
    # ------------------------------------------------------------------
    def _solve_normal_shock(self, geo: Dict, regime: Dict) -> Dict:
        """Find the normal-shock station matching the ambient back pressure.

        Standard quasi-1D matching (Anderson Ch. 5.4): for a shock at
        upstream Mach M1, the stagnation pressure drops by P02/P01 and the
        effective sonic area grows (A2* = A1* * P01/P02); the post-shock
        subsonic isentropic diffusion to the exit must deliver P_exit = Pa.
        """
        g = self.gamma
        pc = self.chamber_pressure
        pa = self.ambient_pressure
        eps_exit = float(geo['area_ratio'][-1])
        mach_exit_sup = regime['exit_mach_supersonic']

        def exit_pressure_error(m1):
            _, _, p02_p01 = normal_shock_relations(m1, g)
            eps_exit_2 = eps_exit * p02_p01   # A_e / A2*
            m_exit = self._mach_from_area(eps_exit_2, supersonic=False)
            _, p_ratio, _ = isentropic_ratios(m_exit, g)
            return pc * p02_p01 * p_ratio - pa

        mach1 = float(brentq(exit_pressure_error, 1.0 + 1e-6, mach_exit_sup,
                             xtol=1e-10, maxiter=200))
        mach2, p2_p1, p02_p01 = normal_shock_relations(mach1, g)
        eps_shock = area_ratio_from_mach(mach1, g)

        i_t = geo['throat_index']
        eps_div = geo['area_ratio'][i_t:]
        x_div = geo['x_mm'][i_t:]
        x_shock_mm = float(np.interp(eps_shock, eps_div, x_div))

        eps_exit_2 = eps_exit * p02_p01
        mach_exit = self._mach_from_area(eps_exit_2, supersonic=False)
        _, p_ratio_e, _ = isentropic_ratios(mach_exit, g)

        return {
            'station_x_mm': x_shock_mm,
            'area_ratio': eps_shock,
            'upstream_mach': mach1,
            'downstream_mach': mach2,
            'static_pressure_jump_ratio': p2_p1,
            'stagnation_pressure_ratio': p02_p01,
            'exit_mach': mach_exit,
            'exit_pressure_Pa': pc * p02_p01 * p_ratio_e,
        }

    # ------------------------------------------------------------------
    # Ana çözüm
    # ------------------------------------------------------------------
    def solve(self, include_bartz: bool = True) -> Dict:
        """Run the quasi-1D analysis and return a JSON-safe result dict.

        Returns
        -------
        dict with keys: 'stations', 'throat', 'regime', 'performance',
        'losses', 'inputs', 'assumptions'. All arrays share one length;
        see the module docstring for the physics references.
        """
        g = self.gamma
        pc = self.chamber_pressure
        tc = self.chamber_temperature
        pa = self.ambient_pressure
        r_gas = R_UNIVERSAL / self.molecular_weight   # J/(kg*K)

        geo = self._build_stations()
        area_ratio = geo['area_ratio']
        i_t = geo['throat_index']
        n = len(area_ratio)

        # --- gaz özellikleri + boğaz koşulları (heat modülüyle TEK kaynak) ---
        md_props = dict(self.motor_data)
        md_props.update({
            'gamma': g,
            'molecular_weight': self.molecular_weight,
            'throat_diameter': self.throat_diameter,
        })
        gas = self._hta._get_gas_properties(md_props, tc)
        throat = self._hta._resolve_throat_conditions(
            md_props, pc, tc, gas, mdot_total=0.0)
        # Bartz için ısı modülünün c* çözümü kullanılır (kullanıcı override'ı
        # dahil); gaz dinamiği debisi ise İZANTROPİK boğaz hâlinden analitik
        # hesaplanır — istasyon dizileriyle bire bir tutarlı kalır.
        c_star_bartz = float(throat['c_star'])
        a_throat_area = float(throat['throat_area'])
        t_star, p_star_ratio, rho_star_ratio = isentropic_ratios(1.0, g)
        rho_star = (pc / (r_gas * tc)) * rho_star_ratio
        a_star = float(np.sqrt(g * r_gas * tc * t_star))
        mdot = rho_star * a_star * a_throat_area   # boğulmuş debi (M=1)
        c_star = pc * a_throat_area / mdot         # analitik c* (Sutton Eq. 3-32)

        # --- izantropik çekirdek: istasyon dizileri ---
        rho0 = pc / (r_gas * tc)
        mach = np.empty(n)
        pressure = np.empty(n)
        temperature = np.empty(n)
        density = np.empty(n)
        velocity = np.empty(n)
        for i in range(n):
            m = self._mach_from_area(area_ratio[i], supersonic=(i > i_t))
            t_ratio, p_ratio, rho_ratio = isentropic_ratios(m, g)
            mach[i] = m
            temperature[i] = tc * t_ratio
            pressure[i] = pc * p_ratio
            density[i] = rho0 * rho_ratio
            velocity[i] = m * np.sqrt(g * r_gas * temperature[i])

        # --- rejim sınıflandırması ---
        regime = self._classify_regime(float(area_ratio[-1]))
        # v2.6.2 fizik denetimi, bulgu F144: boğulmamış (unchoked) lülede
        # boğazda M < 1'dir; alan-Mach bağıntısının SÜPERSONİK dalı geçersizdir
        # ve debi yalnız P_c'den belirlenemez (çıkış koşulu gerekir).
        # Kaynak: Anderson, "Modern Compressible Flow", 3. baskı, Böl. 5.4.
        # _classify_regime dokümantasyonu bu durumda "results are limited to
        # the classification" diyordu ama solve() yine de tam süpersonik
        # çözümü üretip performans bloğunu dolduruyordu.
        # ÖLÇÜLDÜ (P_c = 1.0 bar, P_a = 0.9999 bar, ε = 25): rejim etiketi
        # 'unchoked' doğru çıkarken aynı çıktı exit_M = 3.913,
        # mdot = 0.1196 kg/s ve thrust = −4546.5 N (NEGATİF İTKİ) raporluyordu.
        # Artık performans/kayıp sayıları None döner; istasyon dizileri
        # yalnızca varsayımsal boğulmuş referans olarak, açık etiketle kalır.
        unchoked = (regime['type'] == self.REGIME_UNCHOKED)
        separation = None
        shock = None
        # İzantropik (tam akışlı) çıkış hâli — itki karşılaştırmaları için sakla
        p_exit_isen = float(pressure[-1])
        u_exit_isen = float(velocity[-1])

        if regime['type'] == self.REGIME_SEPARATED:
            separation = self._solve_separation(geo)
        elif regime['type'] == self.REGIME_SHOCK:
            shock = self._solve_normal_shock(geo, regime)
            # Şok sonrası istasyonlar: subsonik dal, P0 kaybı işlenmiş.
            p02 = pc * shock['stagnation_pressure_ratio']
            rho02 = p02 / (r_gas * tc)   # T0 şokta değişmez (adyabatik)
            for i in range(i_t + 1, n):
                if geo['x_mm'][i] >= shock['station_x_mm'] - 1e-9:
                    eps2 = area_ratio[i] * shock['stagnation_pressure_ratio']
                    m = self._mach_from_area(max(eps2, 1.0), supersonic=False)
                    t_ratio, p_ratio, rho_ratio = isentropic_ratios(m, g)
                    mach[i] = m
                    temperature[i] = tc * t_ratio
                    pressure[i] = p02 * p_ratio
                    density[i] = rho02 * rho_ratio
                    velocity[i] = m * np.sqrt(g * r_gas * temperature[i])
        regime['separation'] = separation
        regime['normal_shock'] = shock

        # --- cidar basıncı dizisi (ayrılmada Summerfield platosu) ---
        wall_pressure = pressure.copy()
        if separation is not None:
            sep_x = separation['station_x_mm']
            wall_pressure[geo['x_mm'] > sep_x] = pa

        # --- kütle korunumu teşhisi (istasyon bazında, analitik olmalı) ---
        area = area_ratio * a_throat_area
        mdot_stations = density * velocity * area
        mass_flux_error = float(np.max(np.abs(mdot_stations - mdot)) / mdot)

        # --- itki: momentum + basınç terimi ---
        a_exit = float(area[-1])
        eps_exit = float(area_ratio[-1])
        # Tam akışlı (attached) izantropik itki — referans
        thrust_full_flow = mdot * u_exit_isen + (p_exit_isen - pa) * a_exit
        # Momentum ve basınç terimleri AYRI tutulur: dağılma/sürtünme
        # düzeltmeleri yalnız momentum terimine uygulanır (bulgu F143).
        if separation is not None:
            # Etkin çıkış = ayrılma düzlemi (Summerfield):
            a_sep = separation['area_ratio'] * a_throat_area
            momentum_thrust = mdot * separation['velocity_m_s']
            pressure_thrust = (separation['effective_exit_pressure_Pa'] - pa) * a_sep
            thrust = momentum_thrust + pressure_thrust
            exit_state = {
                'pressure_Pa': separation['effective_exit_pressure_Pa'],
                'velocity_m_s': separation['velocity_m_s'],
                'mach': separation['mach'],
            }
        else:
            momentum_thrust = mdot * float(velocity[-1])
            pressure_thrust = (float(pressure[-1]) - pa) * a_exit
            thrust = momentum_thrust + pressure_thrust
            exit_state = {
                'pressure_Pa': float(pressure[-1]),
                'velocity_m_s': float(velocity[-1]),
                'mach': float(mach[-1]),
            }

        # Cidar basıncı integrali (sayısal çapraz doğrulama; trapez):
        #   F = mdot*u_t + (P_t - Pa)*A_t + integral[(P_w - Pa) dA]
        thrust_wall_integral = (
            mdot * float(velocity[i_t])
            + (float(wall_pressure[i_t]) - pa) * float(area[i_t])
            + float(np.trapz(wall_pressure[i_t:] - pa, area[i_t:]))
        )

        cf = thrust / (pc * a_throat_area)
        cf_ideal = ideal_thrust_coefficient(
            g, p_exit_isen / pc, pa / pc if pc > 0 else 0.0, eps_exit)

        # --- viskoz / dağılma kayıpları ('approximate' etiketli) ---
        theta_exit = geo['theta_exit_rad']
        theta_n = geo['theta_n_rad']
        if geo['nozzle_type'] == 'conical':
            # Sutton & Biblarz 9th ed. Eq. 3-34 (Malina 1940)
            lambda_div = 0.5 * (1.0 + np.cos(theta_exit))
            lambda_note = ("Conical divergence factor lambda=(1+cos(alpha))/2 "
                           "(Sutton & Biblarz 9th ed. Eq. 3-34; Malina 1940).")
        else:
            # Bell: konik formül, başlangıç/çıkış cidar açılarının ortalamasında
            # (Huzel & Huang Ch. 1 eşdeğer-koni yaklaşımı) — 'approximate'.
            lambda_div = 0.5 * (1.0 + np.cos(0.5 * (theta_n + theta_exit)))
            lambda_note = ("Bell nozzle: conical divergence formula evaluated "
                           "at the mean of the initial and exit wall angles "
                           "(Huzel & Huang Ch. 1 equivalent-cone treatment) "
                           "— approximate.")
        # v2.6.2 fizik denetimi, bulgu F143: dağılma (divergence) ve sürtünme
        # düzeltmeleri YALNIZCA momentum terimine uygulanır —
        #     F = lambda·(1 − f)·mdot·v_e + (P_e − P_a)·A_e
        # Kaynak: Sutton & Biblarz, "Rocket Propulsion Elements", 9. baskı,
        # Eş. 3-34 (lambda = (1+cos α)/2 konik dağılma düzeltmesi momentum
        # itkisine uygulanır); aynı konvansiyon Huzel & Huang, NASA SP-125,
        # Böl. 1.
        # ESKİ DAVRANIŞ: thrust_effective = thrust·lambda·(1 − f), yani basınç
        # terimi de ölçekleniyordu. Basınç terimi negatifken (aşırı genişleme)
        # bu kayıp yerine SAHTE KAZANÇ üretiyordu.
        # ÖLÇÜLDÜ (P_c = 70 bar, T_c = 3500 K, γ = 1.2, D_t = 0.10 m, ε = 25,
        # konik 15°): vakumda 98071.2 -> 98237.0 N (+%0.169), deniz
        # seviyesinde (ayrılmış rejim) 82434.8 -> 82160.7 N (−%0.333).
        thrust_effective = (lambda_div * (1.0 - self.friction_loss_fraction)
                            * momentum_thrust) + pressure_thrust

        losses = {
            'method': 'approximate',
            'divergence_factor': float(lambda_div),
            'divergence_loss_fraction': float(1.0 - lambda_div),
            'divergence_half_angle_deg': float(np.degrees(theta_exit)),
            'initial_wall_angle_deg': float(np.degrees(theta_n)),
            'friction_loss_fraction': self.friction_loss_fraction,
            # Ayrık terimler (bulgu F143 dürüstlük alanları)
            'momentum_thrust_N': float(momentum_thrust),
            'pressure_thrust_N': float(pressure_thrust),
            'correction_applies_to': 'momentum_term_only',
            'thrust_effective_N': float(thrust_effective),
            'CF_effective': float(thrust_effective / (pc * a_throat_area)),
            'note': (lambda_note + " Friction/boundary-layer loss is a "
                     "single bookkeeping fraction (typical 0.5-2 %, Sutton "
                     "9th ed. Sec. 3.5; Huzel & Huang Ch. 1), NOT a "
                     "boundary-layer solution. Both corrections scale the "
                     "MOMENTUM thrust only: F_eff = lambda*(1-f)*mdot*v_e "
                     "+ (Pe-Pa)*Ae (Sutton & Biblarz 9th ed. Eq. 3-34); the "
                     "pressure-thrust term is left untouched."),
        }

        # --- eksenel Bartz coupling (ithal korelasyon; kopya yok) ---
        h_g_list: List[float] = []
        q_list: List[float] = []
        taw_list: List[float] = []
        if include_bartz:
            throat_d = float(throat['throat_diameter'])
            rc_over_dt = float(throat['rc_over_dt'])
            for i in range(n):
                m_i = float(mach[i])
                taw = self._hta._adiabatic_wall_temperature(tc, gas, m_i)
                tw = self.wall_temperature if self.wall_temperature is not None \
                    else 0.8 * taw
                tw = min(tw, taw - 1.0)   # q >= 0 garantisi (Tw < Taw)
                h_i = self._hta._bartz_coefficient(
                    throat_d, pc, c_star_bartz, gas, tc, tw, rc_over_dt,
                    area_ratio_local=1.0 / float(area_ratio[i]),
                    mach_local=m_i,
                )
                h_g_list.append(float(h_i))
                q_list.append(float(h_i * (taw - tw)))
                taw_list.append(float(taw))

        # --- çıktı (JSON-güvenli) ---
        result = {
            'model': 'quasi_1d_compressible',
            'stations': {
                'x_mm': geo['x_mm'].tolist(),
                'radius_mm': geo['r_mm'].tolist(),
                'area_ratio': area_ratio.tolist(),
                'mach': mach.tolist(),
                'pressure_Pa': pressure.tolist(),
                'wall_pressure_Pa': wall_pressure.tolist(),
                'temperature_K': temperature.tolist(),
                'density_kg_m3': density.tolist(),
                'velocity_m_s': velocity.tolist(),
                'h_g_W_m2K': h_g_list,
                'q_conv_W_m2': q_list,
                'T_recovery_K': taw_list,
            },
            'throat': {
                'index': int(i_t),
                'x_mm': geo['x_throat_mm'],
                'mach': float(mach[i_t]),
                'pressure_Pa': float(pressure[i_t]),
                'temperature_K': float(temperature[i_t]),
                'diameter_m': float(throat['throat_diameter']),
                'area_m2': a_throat_area,
            },
            'regime': regime,
            'performance': {
                'mass_flow_kg_s': float(mdot),
                'c_star_m_s': c_star,
                'thrust_N': float(thrust),
                'thrust_full_flow_N': float(thrust_full_flow),
                'thrust_wall_integral_N': float(thrust_wall_integral),
                'wall_integral_residual_rel': float(
                    abs(thrust_wall_integral - thrust) / abs(thrust))
                    if thrust != 0 else None,
                'separation_thrust_gain_N': (
                    float(thrust - thrust_full_flow)
                    if separation is not None else 0.0),
                'CF': float(cf),
                'CF_ideal': float(cf_ideal),
                'exit': exit_state,
                'expansion_ratio': eps_exit,
                'mass_conservation_max_rel_error': mass_flux_error,
            },
            'losses': losses,
            'inputs': {
                'chamber_pressure_Pa': pc,
                'chamber_temperature_K': tc,
                'gamma': g,
                'molecular_weight_g_mol': self.molecular_weight,
                'throat_diameter_m': self.throat_diameter,
                'exit_diameter_m': self.exit_diameter,
                'ambient_pressure_Pa': pa,
                'n_stations': self.n_stations,
                'separation_factor': self.separation_factor,
                'wall_temperature_K': self.wall_temperature,
                'nozzle_type': geo['nozzle_type'],
            },
            'assumptions': [
                "Quasi-1D, steady, adiabatic, calorically perfect gas "
                "(frozen gamma); isentropic except across the normal shock.",
                "Shared nozzle contour sampler (same geometry as 2D/3D/CAD).",
                "Separation: Summerfield wall-pressure criterion with an "
                "ambient-pressure plateau downstream (first order).",
                "Bartz h_g(x) imported from the heat-transfer module; "
                "q is the convective design flux only (no radiation here).",
                "Viscous/divergence losses are approximate bookkeeping "
                "estimates, not boundary-layer solutions.",
                "In the separated regime the core station arrays keep the "
                "attached isentropic values (conservative for heat loads); "
                "wall_pressure_Pa carries the separated wall state.",
            ],
        }
        return result
