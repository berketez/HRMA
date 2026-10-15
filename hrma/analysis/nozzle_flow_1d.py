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
    as a numerical cross-check of the exit-plane formula. The check is
    ACTUALLY EVALUATED against WALL_INTEGRAL_CROSS_CHECK_TOL and its verdict
    is published as performance.wall_integral_cross_check (residual_rel /
    tolerance_rel / agrees); where the two formulations disagree the
    published thrust is explicitly NOT cross-checked. (OH D19 / P15B4-09:
    the 231 % residuals previously measured in the normal-shock regime were
    an artefact of that regime being entered while the Summerfield
    separation criterion was met - the attached shock solution's post-shock
    wall pressure is not the real wall state. With the criterion given
    precedence in the ladder those cases are solved as separated and the
    residuals fall to ~2-3 %.) Non-positive fully-expanded reference quantities
    (CF_ideal, thrust_full_flow_N) are withheld rather than published.
  - Divergence factor, conical: lambda = (1 + cos(alpha))/2
    (Malina 1940; Sutton & Biblarz 9th ed. Eq. 3-34). For bell nozzles the
    conical formula is evaluated at the mean of the initial and exit wall
    angles — an HRMA engineering approximation (KU-K1/SP-H1 K42: the old
    citation "Huzel & Huang, Modern Engineering..., Ch. 1 bell-nozzle
    equivalent-cone treatment" does not hold for NASA SP-125 (1967), whose
    Ch. I has no equivalent cone or mean angle - the SP-125 bell lambda is
    Fig. 4-12, p. 91; the AIAA 1992 edition was not read). Tagged
    'approximate'.
  - Friction / boundary-layer thrust loss: typically 0.5-2 % in well
    designed nozzles (Sutton & Biblarz 9th ed. Sec. 3.5 nozzle losses;
    KU-K1/SP-H1 K43: this band is NOT in NASA SP-125 Ch. I, which lists
    thrust-coefficient correction factors 0.92-1.00 next to Table 1-3, p. 16).
    v2.6.27 (V5): a REAL momentum-integral boundary-layer solution is
    computed by ``hrma.flow.boundary_layer`` (Thwaites / Head /
    Ludwieg-Tillmann closures with the Eckert reference-temperature
    compressibility transformation) from THIS module's own edge arrays.
    MIGRATION, 16 Aug 2026 (Berke's decision "whatever is correct wins";
    declared-change policy of docs/mimari/f2-yanma-tepkisi-tasarimi.md
    Sec. 8.1 decision 8): the published ``losses.friction_loss_fraction``
    is now the MEASURED boundary-layer value whenever it can be published;
    the 1.5 % bookkeeping constant
    (``hrma.constants.NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT``) is only a
    FALLBACK for the cases where no measurement exists (in-nozzle normal
    shock, unchoked flow, boundary layer switched off or failed). Which
    one was used is always declared in
    ``losses.friction_loss_fraction_source`` ('integral_bl_measured' /
    'user' / 'legacy_constant') and the legacy number stays published
    next to it (``friction_loss_fraction_legacy_constant``,
    ``thrust_effective_legacy_constant_N``) so that the migration is
    auditable leaf by leaf. An explicit ``friction_loss_fraction=...``
    argument always wins (source 'user'), which is also the way back to
    the pre-migration numbers. Migration manifest (9 measured cases,
    changed-leaf radius, mutation proofs): ``tests/flow/test_surtunme_gocu.py``.

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
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid
from typing import Dict, List, Optional, Tuple

from scipy.optimize import brentq

# Tek kaynak: Bartz korelasyonu, gaz özellik modeli, alan-Mach çözücü ve
# evrensel gaz sabiti heat_transfer_analysis'ten İTHAL edilir (kopya yok).
from hrma.analysis.heat_transfer_analysis import (
    HeatTransferAnalyzer, R_UNIVERSAL,
    GAMMA_REPO_DEFAULT, _guard_gamma_band)

# Sürtünme kaybı kesrinin TEK TANIM YERİ hrma.constants'tır (CLAUDE.md
# kural 11). v2.6.27'ye kadar bu dosya 0.015'i AYRICA yazıyordu; sabitin
# künyesindeki "hem nozzle_flow_1d hem sıvı zinciri bu değeri kullanır"
# beyanı fiilen kırıktı. Değer aynıdır (0.015) — davranış bit-özdeş.
from hrma.constants import (NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT,
                            P_SEA_LEVEL_PA)
# Entegral sınır tabakası (V5): yarı-1B katmanın YANINA ölçülen sürtünme
# kaybını koyar; varsayılanı DEĞİŞTİRMEZ.
from hrma.flow import boundary_layer as _bl

__all__ = [
    'NozzleFlow1D',
    'isentropic_ratios',
    'area_ratio_from_mach',
    'normal_shock_relations',
    'ideal_thrust_coefficient',
    'NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT',
]

def _ozgul_isi_orani(md):
    """(γ, γ'nın geldiği alan) — ÖH D21 / B3-13(c).

    Okuma sırası ``gamma`` -> ``gamma_avg`` -> depo varsayılanıdır; üç
    tüketici modül (bu dosya, ``regen_cooling``, ``heat_transfer_analysis``)
    aynı sırayı kullanır ve aynı künyeyi üretir.
    """
    ham = md.get('gamma')
    if ham is not None:
        return float(ham), 'gamma'
    ham = md.get('gamma_avg')
    if ham is not None:
        return float(ham), (
            "gamma_avg (producer: combustion_analysis performance.gamma_avg "
            "— this is the CHAMBER gamma, not an average)")
    return GAMMA_REPO_DEFAULT, 'repo_default'


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

#: Cidar basıncı integrali ⟷ çıkış düzlemi itkisi ÇAPRAZ DOĞRULAMA EŞİĞİ
#: (bağıl kalıntı). Modül künyesi (:42-44) cidar integralini "a numerical
#: cross-check of the exit-plane formula" diye ilan eder; bu eşik o iddianın
#: SAYISAL karşılığıdır (ÖH D15 / P4B2-06).
#:
#: ÖLÇÜLDÜ (31 Ağustos 2026, taban e88d096; Pc = 70 bar, Tc = 3500 K,
#: Dt = 0,10 m, eps = 25, konik) — iki formülasyonun bağıl ayrışması:
#:     overexpanded (Pa = 0,5 bar)   %0,64
#:     separated    (Pa = 1 atm)     %0,89
#:     normal şok   (Pa = 10 bar)    %8,75
#:     normal şok   (Pa = 30 bar)  %129,47
#:     normal şok   (Pa = 60 bar)  %231,05
#: Ekli (attached) rejimlerde ayrışma bu istasyon ızgarasının trapez
#: kuadratür hatası mertebesindedir (<%1); %5 o bandın rahat üstünde,
#: şok rejiminin ölçülen en küçük değerinin (%8,75) ise altındadır. Yani
#: eşik "kuadratür gürültüsü" ile "iki formülasyon aynı akışı ANLATMIYOR"
#: hâllerini ayırır.
WALL_INTEGRAL_CROSS_CHECK_TOL = 0.05

#: Kullanıcı c*'ı ⟷ çözümün ima ettiği analitik c* TUTARLILIK TOLERANSI.
#: ÖH D15 / P4B2-08. Bu bir mühendislik bandı değil, SAYISAL kimlik
#: toleransıdır: iki değer aynı fiziksel büyüklüğü göstermek zorundadır ve
#: fark yalnız kayan nokta yuvarlamasından gelebilir. 1e-9, ``c_star =
#: pc*A_t/mdot`` zincirindeki (sqrt, üs alma) yuvarlama birikiminin rahat
#: üstündedir.
C_STAR_CONSISTENCY_REL_TOL = 1.0e-9


def _json_safe(obj):
    """numpy dizilerini listeye, sonlu olmayan sayıları None'a çevirir.

    Sınır tabakası bloğu marşın ULAŞMADIĞI istasyonlarda NaN taşır (bu
    bilinçli bir beyandır: "burada değer yok"). NaN geçerli JSON değildir;
    uçta ``null`` olarak görünmesi için burada dönüştürülür.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_json_safe(v) for v in obj.tolist()]
    if isinstance(obj, (np.floating, float)):
        value = float(obj)
        return value if np.isfinite(value) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


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
        Ratio of specific heats (frozen). The accepted band is the
        single-source ``GAMMA_BAND_MIN`` / ``GAMMA_BAND_MAX`` pair
        exported by ``heat_transfer_analysis`` (do not restate the
        numbers here — ÖH D21 / P4B1-16, doctrine 4).
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
    friction_loss_fraction : float or None
        Friction / boundary-layer thrust loss fraction. ``None`` (default)
        selects the MEASURED momentum-integral boundary-layer value when
        it can be published, and the 1.5 % bookkeeping constant
        (``hrma.constants.NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT``, typical
        band 0.5-2 %, Sutton 9th ed. Sec. 3.5) only as a declared fallback
        — see the module docstring (migration, 16 Aug 2026). Passing a
        number pins the fraction to it (source 'user'); passing 0.015
        explicitly reproduces the pre-migration numbers bit for bit.
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
                 ambient_pressure: float = P_SEA_LEVEL_PA,
                 n_stations: int = 45,
                 separation_factor: float = SEPARATION_FACTOR_DEFAULT,
                 wall_temperature: Optional[float] = 800.0,
                 friction_loss_fraction: Optional[float] = None,
                 motor_data: Optional[Dict] = None):
        # --- doğrulamalar (İngilizce hata metinleri: kullanıcıya görünür) ---
        if not (chamber_pressure > 0.0):
            raise ValueError("chamber_pressure must be positive [Pa].")
        if not (chamber_temperature > 0.0):
            raise ValueError("chamber_temperature must be positive [K].")
        # ÖH D21 / P4B1-16 (doktrin-4 TEK KAYNAK): bandın sayısı artık
        # ısı-transferi modülünden İTHAL EDİLİR, burada yeniden yazılmaz.
        # Reddin cümlesi de ortaktır — üç modül aynı girdide aynı hükmü
        # kurar (kardeş ısı-transferi modülü v2.6.27'ye kadar aynı girdiyi
        # sessizce 1,20'ye kelepçeliyordu).
        _guard_gamma_band(gamma)
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
        if friction_loss_fraction is not None:
            if not (0.0 <= friction_loss_fraction < 0.2):
                raise ValueError("friction_loss_fraction must be within [0, 0.2).")
        # ÖH D15 / P4B2-04 — CİDAR SICAKLIĞI KAPISI (kardeş modülle eşitlendi).
        # Yukarıdaki blok chamber_pressure/temperature, gamma,
        # molecular_weight, ambient_pressure, separation_factor ve
        # friction_loss_fraction'ı kapılıyordu; ``wall_temperature`` KAPISIZDI.
        # ÖLÇÜLDÜ (31 Ağustos 2026, taban e88d096; Pc=70 bar, Tc=3500 K,
        # Dt=0,10 m, eps=25, vakum):
        #   T_w =  800 K -> q_conv[0] = 20,986 MW/m²  (h_g0 =  7777,2)
        #   T_w =    0 K -> q_conv[0] = 31,325 MW/m²  (h_g0 =  8954,2)
        #   T_w = −500 K -> q_conv[0] = 39,793 MW/m²  (h_g0 =  9952,2) = ×1,90
        # ve POST /api/flow-analysis {'wall_temperature': −500} HTTP 200 ile
        # 39 792 966,12 W/m² yayımlıyordu. Negatif MUTLAK sıcaklık bir girdi
        # değildir; Bartz korelasyonu T_w'yi mutlak ölçekte kullanır
        # (sigma düzeltmesi T_w/T_c oranıyla kurulur). Kardeş RegenCooling
        # aynı sınıf büyüklükler için ``> 0`` kapısı taşıyor
        # (regen_cooling.py: coolant_inlet_temp / chamber_temperature) —
        # ölçüldü: coolant_inlet_temp=−500 -> "must be positive [K]".
        # İki modül arasındaki kapı politikası tutarsızlığı burada kapandı.
        if wall_temperature is not None:
            if not (float(wall_temperature) > 0.0):
                raise ValueError(
                    "'wall_temperature' must be positive [K]: temperature "
                    "enters the Bartz correlation on the ABSOLUTE scale "
                    "(the sigma correction is built on T_w/T_c), so a zero "
                    "or negative wall temperature has no physical meaning "
                    "and inflates the convective flux. This is the same "
                    "'> 0' gate the sibling regenerative-cooling module "
                    "applies to its temperatures.")

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
        # GÖÇ (16 Ağu 2026): tek bir "friction_loss_fraction" alanı artık
        # yetmiyor — hangi sayının KULLANILDIĞI ile hangi sayının YEDEK
        # olduğu ayrı tutulur. Eski tek isim BİLEREK kaldırıldı: adı
        # koruyup anlamını değiştirmek, okuyanı "kullanılan kesir bu"
        # sanmaya iten sessiz bir tuzak olurdu (kullanılan kesir artık
        # çözüme, yani sınır tabakası marşına bağlıdır).
        #: Kullanıcının AÇIKÇA verdiği kesir (None = vermedi).
        self.friction_loss_fraction_user = (
            None if friction_loss_fraction is None
            else float(friction_loss_fraction))
        #: Ölçüm yayımlanamadığında kullanılacak yedek: kullanıcı değeri
        #: varsa o, yoksa hrma.constants'taki 1,5 % defter sabiti.
        self.friction_loss_fraction_fallback = (
            NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT
            if self.friction_loss_fraction_user is None
            else self.friction_loss_fraction_user)

        # Isı transferi yardımcıları (Bartz + alan-Mach çözücü) — tek kaynak.
        self._hta = HeatTransferAnalyzer()

    # ------------------------------------------------------------------
    # Yapıcı yardımcıları
    # ------------------------------------------------------------------
    @classmethod
    def from_motor_data(cls, motor_data: Dict,
                        ambient_pressure: float = P_SEA_LEVEL_PA,
                        **kwargs) -> 'NozzleFlow1D':
        """Build from a repo-style motor dictionary.

        Repo convention (see ``HeatTransferAnalyzer.analyze_heat_transfer``):
        ``chamber_pressure`` in bar, temperatures in K, diameters in m.
        """
        md = dict(motor_data or {})
        return cls(
            chamber_pressure=float(md.get('chamber_pressure', 20.0)) * 1e5,
            chamber_temperature=float(md.get('chamber_temperature', 3000.0)),
            # ÖH D21 / B3-13(c) — SESSİZ 1,2 YEDEĞİ KALKTI, KÜNYE GELDİ.
            # Eski satır ``float(md.get('gamma', md.get('gamma_avg',
            # 1.2)))`` idi: γ hiç yokken 1,2 sessizce konuyor, üstelik
            # sayı kardeş iki modülde ayrı ayrı yazılıyordu. Sayı artık
            # ``GAMMA_REPO_DEFAULT`` tek kaynağından gelir ve nereden
            # geldiği ``gamma_source`` ile taşınır. ``gamma_avg`` adının
            # kendisi yalan söylüyor (üretici ``combustion_analysis``
            # oraya ODA gamma'sını koyar, ortalama değil); adın
            # düzeltilmesi üretici dosyayı gerektirir (hibrit kulvarı).
            gamma=_ozgul_isi_orani(md)[0],
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
        Anderson Ch. 5.4, with the Summerfield separation criterion given
        PRECEDENCE over the inviscid normal-shock branch):

          Pa < Pe(1-tol)                       -> underexpanded
          |Pa - Pe| <= tol*Pe                  -> perfectly expanded
          Pe(1+tol) < Pa <= Pe/k               -> overexpanded (attached)
          Pe/k < Pa < P_exit_subsonic          -> SEPARATED (Summerfield)
          P_shock_at_exit < Pa < P_exit_subsonic -> normal shock in nozzle,
                                                  ONLY where the Summerfield
                                                  criterion is not met
          Pa >= P_exit_subsonic                -> unchoked (edge case, warn)

        ÖH D19 / P15B4-09 — SUMMERFIELD ÖNCELİKLİDİR.

        Eski merdiven şok bandını ayrılma bandının ÜSTÜNE koyuyordu, yani
        artan geri basınçta akış önce ayrılıyor sonra "yeniden yapışıp"
        lüle içinde normal şok yapıyordu. Bu sıra fiziksel değildir:
        ayrılma bir kez başladıktan sonra geri basınç ARTTIKÇA ayrılma
        düzlemi boğaza doğru YÜRÜR, cidara geri yapışmaz.

        Cebirsel olarak da iki bant iç içedir: şok-çıkışta koşulu
        Pa > Pe*(P2/P1) iken ayrılma ölçütü Pa > Pe/k'dır; P2/P1 > 1/k
        olan her çıkış Mach'ında (k = 0,40 icin M_e > ~1,53, gamma = 1,2
        için eps > ~1,23) şok bandının TAMAMI ayrılma bandının içinde
        kalır. Eski sırada bu kesişimde ayrılma ölçütü sağlanmasına
        rağmen SHOCK etiketi kazanıyor, ``separation`` anahtarı boş
        kalıyordu — kalemin ta kendisi.

        Kaynak: Summerfield, Foster & Swan, "Flow Separation in
        Overexpanded Supersonic Exhaust Nozzles", Jet Propulsion 24(9),
        1954, s. 319-321 (P_wall,sep ~ 0,4 P_a); Sutton & Biblarz,
        Rocket Propulsion Elements 9. baskı Böl. 3.3 ("the flow separates
        from the wall ... the normal shock predicted by one-dimensional
        theory is not observed"); Anderson, Modern Compressible Flow 3.
        baskı Böl. 5.4 (quasi-1D şok çözümü inviskiddir, sınır tabakası
        yoktur). Şok dalı KALDIRILMAZ: ölçütün sağlanmadığı düşük
        genişleme oranlarında (eps < ~1,23) klasik çözüm hâlâ geçerlidir
        ve orada koşulur.
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

        # ÖH D17 / P15B4-09 — SUMMERFIELD ÖLÇÜTÜ MERDİVENDEN BAĞIMSIZ
        # ÖLÇÜLÜR. Ölçüt burada TEK KEZ değerlendirilir ve rejim ne olursa
        # olsun yayımlanır. ÖH D19: artık merdivende de ÖNCELİKLİDİR.
        separation_criterion_met = bool(
            pa > 0.0 and p_exit_isentropic < self.separation_factor * pa)

        if pa >= p_exit_subsonic:
            regime = self.REGIME_UNCHOKED
            description = ("Back pressure exceeds the fully subsonic exit "
                           "pressure: the nozzle is not choked. This is not "
                           "a rocket operating point; results are limited "
                           "to the classification.")
        elif separation_criterion_met:
            # ÖH D19 / P15B4-09: ayrılma ölçütü şok dalından ÖNCE gelir.
            regime = self.REGIME_SEPARATED
            description = (f"Overexpanded flow separates from the nozzle "
                           f"wall (Summerfield criterion: wall pressure < "
                           f"{self.separation_factor:.2f} x ambient). The "
                           f"criterion takes precedence over the inviscid "
                           f"normal-shock branch: where both would apply "
                           f"the boundary layer detaches upstream of the "
                           f"shock station, so the attached quasi-1D shock "
                           f"solution does not describe the flow.")
        elif pa > p_shock_at_exit:
            regime = self.REGIME_SHOCK
            description = ("Back pressure is high enough to push a normal "
                           "shock inside the divergent section (textbook "
                           "quasi-1D solution). The Summerfield separation "
                           "criterion is NOT met here, so the attached "
                           "inviscid solution stands; this only happens at "
                           "low expansion ratios, where the normal-shock "
                           "pressure rise stays below 1/k.")
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
            # ÖH D17 / P15B4-09: ölçütün HÜKMÜ, rejim etiketinden ayrı.
            'separation_criterion_met': separation_criterion_met,
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
    # Entegral sınır tabakası köprüsü (V5) — ÖLÇÜLEN sürtünme kaybı
    # ------------------------------------------------------------------
    def _solve_boundary_layer(self, geo: Dict, gas: Dict,
                              mach: np.ndarray, pressure: np.ndarray,
                              temperature: np.ndarray,
                              separation: Optional[Dict],
                              shock: Optional[Dict]) -> Dict:
        """Momentum-integral sınır tabakasını istasyon dizileri üstünde çözer.

        Kenar (edge) koşulları bu modülün YAYIMLADIĞI dizilerdir (M, p, T)
        — sınır tabakası katmanı ayrı bir akış çözümü kurmaz. Marş, lüle
        içinde şok ya da ayrılma varsa o istasyonda DURDURULUR: ikisinin
        de ötesi ``BOUNDARY_LAYER_NOT_MODELLED`` kapsamındadır.

        Cidar sıcaklığı geleneği Bartz bloğuyla AYNIDIR: kullanıcı değeri
        yoksa 0.8·T_aw, her hâlükârda T_w ≤ T_aw − 1 K.
        """
        x_m = np.asarray(geo['x_mm'], dtype=float) / 1000.0
        r_m = np.asarray(geo['r_mm'], dtype=float) / 1000.0

        # Kurtarma sıcaklığı ve cidar sıcaklığı — tek kaynak (ısı modülü).
        taw = np.array([self._hta._adiabatic_wall_temperature(
            self.chamber_temperature, gas, float(m)) for m in mach])
        # ÖH D15 / P4B2-05: kırpma yerine TEK KAYNAK + fail-closed kapı.
        t_wall, _tw_kaynagi = self._wall_temperature_field(taw)

        # μ(T): depodaki TEK viskozite kaynağından (Bartz üs yasası ya da
        # kullanıcı/Cantera override'ı) — sınır tabakası modülü kendi
        # yasasını yazmaz.
        md_props = dict(self.motor_data)
        md_props.update({'gamma': self.gamma,
                         'molecular_weight': self.molecular_weight,
                         'throat_diameter': self.throat_diameter})

        def resolve_viscosity(t_kelvin: float) -> float:
            return float(self._hta._get_gas_properties(
                md_props, float(t_kelvin))['gas_viscosity'])

        # Sıcaklığa bağlı mı, yoksa çağıranın sabiti mi? ÖLÇÜLÜR, beyan edilir.
        # Sabitse çözücüye sabit kapanış verilir: aynı sayı, ama binlerce
        # gereksiz özellik çözümü (Cantera dahil) yapılmaz.
        mu_low = resolve_viscosity(0.5 * self.chamber_temperature)
        mu_high = resolve_viscosity(self.chamber_temperature)
        if abs(mu_high - mu_low) > 1e-12 * max(mu_high, 1e-30):
            viscosity_fn = resolve_viscosity
            viscosity_basis = (
                'μ(T) heat_transfer_analysis._get_gas_properties üzerinden '
                'sıcaklığa bağlı çözüldü (Bartz 1957 üs yasası: '
                'μ = 1.184e-7·MW^0.5·T^0.6).')
        else:
            viscosity_fn = lambda t_kelvin: mu_high   # noqa: E731 (sabit)
            viscosity_basis = (
                'μ çağıranın SABİT değeri (motor_data gas_viscosity/'
                'cantera_gas override); sıcaklık ölçeklemesi UYGULANMADI.')

        stop_x = None
        stop_reason = None
        if separation is not None:
            stop_x = float(separation['station_x_mm']) / 1000.0
            stop_reason = ('Summerfield ayrılma istasyonu: ayrılma sonrası '
                           'sınır tabakası entegral yöntemle modellenmez.')
        elif shock is not None:
            stop_x = float(shock['station_x_mm']) / 1000.0
            stop_reason = ('Lüle içi normal şok istasyonu: şok-sınır tabaka '
                           'etkileşimi modellenmedi.')

        result = _bl.solve_boundary_layer(
            x_m, r_m, mach, pressure, temperature,
            gamma=self.gamma,
            gas_constant_J_kgK=float(gas['gas_constant']),
            prandtl=float(gas['prandtl']),
            viscosity_fn=viscosity_fn,
            wall_temperature_K=t_wall,
            specific_heat_J_kgK=float(gas['gas_cp']),
            transition=_bl.TRANSITION_TURBULENT_FROM_START,
            stop_x_m=stop_x,
            stop_reason=stop_reason,
        )
        result['viscosity_basis'] = viscosity_basis
        return result

    # ------------------------------------------------------------------
    # Cidar sıcaklığı alanı — TEK KAYNAK (Bartz bloğu + sınır tabakası)
    # ------------------------------------------------------------------
    def _wall_temperature_field(self, taw):
        """İstasyon başına FİİLEN KULLANILAN cidar sıcaklığı [K] + kaynağı.

        ÖH D15 / P4B2-05 — SESSİZ KIRPMA KALDIRILDI.

        Eski davranış: her iki tüketici de (Bartz eksenel bloğu ve sınır
        tabakası marşı) ``T_w = min(T_w, T_aw − 1)`` kırpması uyguluyor,
        çıktı ise ``inputs.wall_temperature_K`` alanında kullanıcının HAM
        değerini yankılıyordu. İki sayı arasında hiçbir bağ, uyarı ya da
        beyan yoktu.

        ÖLÇÜLDÜ (31 Ağustos 2026, taban e88d096; Pc = 70 bar, Tc = 3500 K,
        Dt = 0,10 m, eps = 25, vakum; T_aw[0] = 3498,403 K):
            girdi  3 000 K -> yayımlanan  3 000,0 / fiilen  3 000,000 K,
                              q[0] = 2,9226 MW/m²          (ayrışma 0 K)
            girdi  5 000 K -> yayımlanan  5 000,0 / fiilen  3 497,403 K,
                              q[0] = 0,005576 MW/m²        (ayrışma 1502,6 K)
            girdi 20 000 K -> yayımlanan 20 000,0 / fiilen  3 497,403 K,
                              q[0] = 0,005576 MW/m²        (ayrışma 16502,6 K)
        Yön TEHLİKELİ: kırpma akıyı 21,9 MW/m² sınıfından 0,006 MW/m²'ye
        (≈%0,03) indirip "ısı yükü yok" görüntüsü veriyordu.

        Yeni davranış (fail-closed): kullanıcının verdiği cidar sıcaklığı
        HERHANGİ bir istasyonda kurtarma sıcaklığına eşit/ondan büyükse
        sayı ÜRETİLMEZ — o hâlde taşınım yönü tersine döner (gaz cidardan
        ısınır) ve Bartz korelasyonu geçerli değildir. Alan adı ve iki sayı
        gerekçeyle söylenir. Kullanıcı değeri kabul edildiğinde artık
        yayımlanan değer ile kullanılan değer AYNIDIR.

        Varsayılan yol (kullanıcı değeri yok -> 0,8·T_aw) BİT-AYNIDIR:
        0,8·T_aw < T_aw − 1 eşitsizliği T_aw > 5 K olan her hâlde doğrudur,
        yani eski ``min`` hiçbir zaman bu kolda etkin değildi.
        """
        taw = np.asarray(taw, dtype=float)
        if self.wall_temperature is None:
            return 0.8 * taw, 'model_default_0.8_T_aw'
        tw = float(self.wall_temperature)
        i_min = int(np.argmin(taw))
        taw_min = float(taw[i_min])
        if tw >= taw_min:
            raise ValueError(
                "'wall_temperature' ({tw:.1f} K) is not below the adiabatic "
                "wall (recovery) temperature at every station: the minimum "
                "recovery temperature on this contour is {taw:.1f} K at "
                "station {idx}. Above it the convective heat flux changes "
                "sign (the gas would be heated BY the wall) and the Bartz "
                "correlation no longer applies. This solver previously "
                "clamped the value silently to T_aw − 1 K while echoing the "
                "raw input back in inputs.wall_temperature_K, which reported "
                "an almost-zero heat load; no number is published for an "
                "unusable wall temperature.".format(
                    tw=tw, taw=taw_min, idx=i_min))
        return np.full(taw.shape, tw), 'user_supplied'

    # ------------------------------------------------------------------
    # Ana çözüm
    # ------------------------------------------------------------------
    def solve(self, include_bartz: bool = True,
              include_boundary_layer: bool = True) -> Dict:
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

        # --- ÖH D15 / P4B2-08 — İKİ c* AYNI YANITTA OLAMAZ (fail-closed) ---
        # ÖLÇÜLDÜ (31 Ağustos 2026, taban e88d096; Pc = 70 bar, Tc = 3500 K,
        # Dt = 0,10 m, De = 0,50 m):
        #   motor_data c*'sız        -> performance.c_star_m_s = 1697,910,
        #                               h_g(boğaz) = 15 782,54 W/m²K
        #   motor_data={'c_star':1650}-> performance.c_star_m_s = 1697,910
        #                               (DEĞİŞMEDİ) ama Bartz'a 1650,0 girdi,
        #                               h_g(boğaz) = 16 148,10 (+%2,32),
        #                               q_conv(boğaz) aynı oranda arttı.
        # Yani kullanıcının verdiği c* akıyı SESSİZCE değiştiriyor, yanıtta
        # yayımlanan c* ise analitik ideal değer olarak kalıyordu — aynı
        # yanıtta iki farklı c*, biri gizli. Sözleşme tuzağı gerçek:
        # ``from_motor_data`` künyesi "depo motor sözlüğünü ver" diyor ve
        # depo sözlükleri üst düzeyde ``c_star`` TAŞIYOR
        # (hybrid_rocket_engine.py, liquid_rocket_engine.py,
        # solid_rocket_engine.py); bugünkü çağıranların hiçbiri geçirmiyor,
        # yani bu kol BUGÜN ÖLÜ ve kapının davranışa etkisi yok.
        #
        # Bu modülde ölçülen c* KABUL EDİLEMEZ, çünkü gaz dinamiğinin
        # tamamı (debi, hız, istasyon dizileri) izantropik boğaz hâlinden
        # kurulur ve o hâl analitik c*'ı İMA EDER (c* = Pc·A_t/mdot). Ölçülen
        # bir c* (yanma verimini içerir) yalnız Bartz'a girerse çözüm kendi
        # içinde tutarsız olur. Sayı üretilmez; alan adı ve iki değer
        # gerekçesiyle söylenir.
        _cs_kaynak = throat.get('c_star_source')
        if _cs_kaynak == 'user_supplied' and c_star > 0.0:
            if abs(c_star_bartz / c_star - 1.0) > C_STAR_CONSISTENCY_REL_TOL:
                raise ValueError(
                    "motor_data['c_star'] = {u:.3f} m/s conflicts with the "
                    "characteristic velocity implied by this solution, "
                    "{a:.3f} m/s (c* = Pc*A_t/mdot at the isentropic choked "
                    "throat, Sutton & Biblarz 9th ed. Eq. 3-32). The whole "
                    "gas-dynamic solution — mass flow, station velocities, "
                    "thrust — is built on the analytic value, so a supplied "
                    "c* would silently change ONLY the Bartz heat flux "
                    "(measured: +2.32 % on h_g at the throat) while the "
                    "response kept publishing the analytic number. Two "
                    "different c* in one answer is not a solution: drop "
                    "motor_data['c_star'], or adjust gamma / "
                    "molecular_weight / chamber_temperature so the analytic "
                    "c* matches your measurement.".format(
                        u=float(c_star_bartz), a=float(c_star)))

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

        # --- ÖH D17+D19 / P15B4-09 — İKİ UÇ AYNI SORUYA TERS CEVAP VEREMEZ -
        # ÖLÇÜLDÜ (once.json K2 + a1 ölçümü): P_c = 10 bar, eps = 25,
        # P_a = 101 325 Pa -> rejim 'normal_shock_in_nozzle',
        # ``separation = None``, yani /api/flow-analysis "ayrılma yok"
        # diyor; oysa çözücünün KENDİ Summerfield ölçütü sağlanıyor
        # (P_e = 3 804,3 Pa < 0,40 x 101 325 = 40 530 Pa) ve kardeş uç
        # /api/cfd/nozzle aynı vakaya "ayrılma var" diyor. Rejim
        # açıklaması "real flows also show boundary-layer separation in
        # this band" diye YAZIYORDU ama VERİ bunun tersini söylüyordu.
        #
        # BİR iş yapılır:
        #  (1) Ayrılma düzlemi AYNI Summerfield çözücüsüyle bulunur ve
        #      ayrı bir adla yayımlanır.
        #
        # TARİHÇE (Fable-D17 ŞART / ÖH D20 ile hizalandı) — bu blokta bir
        # zamanlar İKİNCİ bir madde daha yazıyordu: "şok bandının performans
        # sayıları GERİ ÇEKİLİR ... performance_withheld_because". O adım
        # DENENDİ ve ölçümle GERİ ALINDI: geri çekme, aynı dosyanın
        # ``if unchoked:`` bloğundaki notta (bkz. aşağıda, "SAYILAR GERİ
        # ÇEKİLİR, alan adları ve künyeler kalır") tarif edildiği üzere
        # YALNIZ boğulmamış rejimde uygulanır; şok bandında sayılar
        # hesaplanabilirdir ve mevcut bekçiler onları kilitler. Kod kendisi
        # hakkında yapmadığı bir işi iddia edemediği için madde kaldırıldı;
        # sayfada kalan tek iş (1)'dir.
        #
        # ÖH D17'de ``separation`` anahtarı (itki zincirinin okuduğu alan)
        # BİLEREK None bırakılmıştı: onu doldurmak itki modelini değiştirmek
        # demekti ve o dalgada ÖK-06 kilidi vardı.
        #
        # ÖH D19 (ÖK-06 bu kulvar için KALKTI) — HÜKÜM DEĞİL SAYI DA
        # DÜZELTİLDİ. Merdivende Summerfield ölçütü artık şok dalından
        # ÖNCE geliyor (bkz. ``_classify_regime``), yani ölçütün sağlandığı
        # her vaka REGIME_SEPARATED'a düşer, ``separation`` DOLDURULUR ve
        # itki ayrılma düzleminden (efektif çıkış) hesaplanır. Ölçülen
        # etki (P_c = 10 bar, eps = 25, P_a = 101 325 Pa, D_t = 50 mm):
        #     ÖNCE : rejim 'normal_shock_in_nozzle', separation = None,
        #            itki    324,25 N   (yapışık şok + subsonik difüzyon)
        #     SONRA: rejim 'separated', separation dolu (eps_sep = 4,208,
        #            x_sep = 120,95 mm), itki 2 335,65 N
        # Yapışık çözüm itkiyi ~7,2 kat DÜŞÜK veriyordu. Süreklilik sınaması
        # (itki/P_c, N/bar): ÖNCE 6 bar 19,5 | 10 bar 32,4 | 20 bar 263,3 |
        # 70 bar 304,1 — 10->20 bar arasında 8 katlık SIÇRAMA, çünkü 20 bar
        # zaten 'separated' bandındaydı. SONRA 206,8 | 233,6 | 263,3 | 304,1
        # — tek eğri, monoton (P_c arttıkça ayrılma düzlemi çıkışa yürür).
        #
        # Anahtarlar HER koşuda vardır (yanıt şekli rejimle değişmez, panel
        # ve sözleşme bekçileri sabit bir şema görür); uygulanmadığında
        # değerleri null'dur — "alan yok" ile "hüküm yok" karışmaz.
        # ``separation_expected`` artık DOĞRUDAN ölçütün kendisidir: rejim
        # etiketiyle çelişemez, çünkü etiket ölçütten türüyor.
        ayrilma_beklenen = bool(regime.get('separation_criterion_met'))
        regime['separation_expected'] = ayrilma_beklenen
        regime['separation_station_summerfield'] = None
        regime['separation_expected_because'] = None
        if ayrilma_beklenen:
            regime['separation_station_summerfield'] = (
                separation if separation is not None
                else self._solve_separation(geo))
            regime['separation_expected_because'] = (
                "SEPARATION IS EXPECTED AND MODELLED. This solver's "
                f"Summerfield criterion is met at the exit (P_e = "
                f"{p_exit_isen:.6g} Pa < {self.separation_factor:.2f} x "
                f"P_ambient = {self.separation_factor * pa:.6g} Pa), so the "
                "boundary layer detaches upstream of the exit plane. Since "
                "the criterion takes precedence over the inviscid "
                "normal-shock branch, the regime is classified as separated "
                "and the separation plane is the effective nozzle exit for "
                "thrust (see regime.separation). The CFD endpoint "
                "(/api/cfd/nozzle) reports the same case as separated.")

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
            + float(_trapezoid(wall_pressure[i_t:] - pa, area[i_t:]))
        )

        cf = thrust / (pc * a_throat_area)
        cf_ideal = ideal_thrust_coefficient(
            g, p_exit_isen / pc, pa / pc if pc > 0 else 0.0, eps_exit)

        # --- viskoz / dağılma kayıpları ('approximate' etiketli) ---
        theta_exit = geo['theta_exit_rad']
        theta_n = geo['theta_n_rad']
        # ÖH D22 / P4B2-12 — lambda'YI ÜRETEN AÇI ARTIK ADIYLA YAYIMLANIYOR.
        # ÖLÇÜLDÜ (taban b84b10a, ``once.json`` P4B2-12; Pc = 70 bar,
        # Tc = 3500 K, Dt = 0,10 m, eps = 25, çan konturu):
        #   divergence_factor           = 0,973695
        #   divergence_half_angle_deg   = 8,1965   (ÇIKIŞ cidar açısı)
        #   0,5·(1+cos 8,1965°)         = 0,994892 → lambda'da +%2,1771
        # Yani alan adına bakıp lambda'yı yeniden üreten okuyucu momentum
        # itkisinde %2,18 sapıyordu. Sayı DOĞRUYDU (eşdeğer-koni açısı
        # kullanılıyor), yanlış olan yayımlanan ikilinin kendi içinde
        # tutarsız olmasıydı. Konikte iki açı zaten aynıdır (sapma 0).
        # TEK KAYNAK: aşağıdaki ``theta_lambda`` hem lambda'yı üretir hem
        # de ``divergence_factor_angle_deg`` alanına basılır; ikinci bir
        # formül yazılmaz.
        if geo['nozzle_type'] == 'conical':
            # Sutton & Biblarz 9th ed. Eq. 3-34 (Malina 1940)
            theta_lambda = theta_exit
            lambda_basis = 'exit_wall_angle'
            lambda_note = ("Conical divergence factor lambda=(1+cos(alpha))/2 "
                           "(Sutton & Biblarz 9th ed. Eq. 3-34; Malina 1940).")
        else:
            # Bell: konik formül, başlangıç/çıkış cidar açılarının ortalamasında
            # (HRMA eşdeğer-koni yaklaşımı; KU-K1/SP-H1 K42: SP-125 Böl. I'de
            # yok, eski künye "Huzel & Huang Ch. 1" idi) — 'approximate'.
            theta_lambda = 0.5 * (theta_n + theta_exit)
            lambda_basis = 'mean_of_initial_and_exit_wall_angles'
            lambda_note = ("Bell nozzle: conical divergence formula evaluated "
                           "at the mean of the initial and exit wall angles "
                           "(HRMA equivalent-cone approximation; not in NASA "
                           "SP-125 Ch. I) — approximate. NOTE: lambda is evaluated at "
                           "divergence_factor_angle_deg (the equivalent-cone "
                           "angle), NOT at divergence_half_angle_deg, which "
                           "is the EXIT wall angle; for a bell contour the "
                           "two differ.")
        lambda_div = 0.5 * (1.0 + np.cos(theta_lambda))
        # v2.6.2 fizik denetimi, bulgu F143: dağılma (divergence) ve sürtünme
        # düzeltmeleri YALNIZCA momentum terimine uygulanır —
        #     F = lambda·(1 − f)·mdot·v_e + (P_e − P_a)·A_e
        # Kaynak: Sutton & Biblarz, "Rocket Propulsion Elements", 9. baskı,
        # Eş. 3-34 (lambda = (1+cos α)/2 konik dağılma düzeltmesi momentum
        # itkisine uygulanır); aynı konvansiyon Huzel & Huang, NASA SP-125,
        # Eş. 4-8 (s. 90, "çıkış gaz momentumu" oranı) — KU-K1/SP-H1 K44:
        # eski künye "Böl. 1" idi, tanım Böl. IV'tedir.
        # ESKİ DAVRANIŞ: thrust_effective = thrust·lambda·(1 − f), yani basınç
        # terimi de ölçekleniyordu. Basınç terimi negatifken (aşırı genişleme)
        # bu kayıp yerine SAHTE KAZANÇ üretiyordu.
        # ÖLÇÜLDÜ (P_c = 70 bar, T_c = 3500 K, γ = 1.2, D_t = 0.10 m, ε = 25,
        # konik 15°): vakumda 98071.2 -> 98237.0 N (+%0.169), deniz
        # seviyesinde (ayrılmış rejim) 82434.8 -> 82160.7 N (−%0.333).
        #
        # GÖÇ (16 Ağu 2026): thrust_effective ARTIK sabitten değil, ölçülen
        # sürtünme kesrinden hesaplanır. Bu yüzden sınır tabakası bloğu
        # thrust_effective'in ÜSTÜNE alındı — sıra değişikliği kasıtlıdır,
        # aşağıdaki hesap kesri bilmeden yapılamaz.

        # --- V5 + göç: ÖLÇÜLEN sürtünme kaybı (momentum-integral sınır tab.) --
        bl_result: Optional[Dict] = None
        bl_error: Optional[str] = None
        if include_boundary_layer and not unchoked:
            try:
                bl_result = self._solve_boundary_layer(
                    geo, gas, mach, pressure, temperature, separation, shock)
            except Exception as exc:   # beyanlı başarısızlık, sessiz değil
                bl_error = f'{type(exc).__name__}: {exc}'
        # Kesir, ancak sürtünme integraliyle momentum itkisi AYNI yüzeye
        # ait olduğunda anlamlıdır:
        #  - ayrılmış rejimde ikisi de ayrılma düzlemine kadardır (tutarlı),
        #  - lüle içi şok rejiminde marş şokta durur ama momentum itkisi
        #    şok ARDI ses-altı çıkıştan gelir → kesir yanıltıcı olur
        #    (ÖLÇÜLDÜ: 6 bar/ε=25 vakasında %27,4 çıkıyor). O yüzden kesir
        #    yayımlanmaz, kuvvet (N) yayımlanır ve gerekçe beyan edilir.
        bl_fraction: Optional[float] = None
        bl_fraction_note: Optional[str] = None
        if bl_result is not None:
            if shock is not None:
                bl_fraction_note = (
                    "Normal-shock regime: the boundary-layer march stops at "
                    "the shock while the momentum thrust comes from the "
                    "post-shock subsonic exit — the two do not share a "
                    "reference surface, so no loss FRACTION is published. "
                    "friction_drag_integral_bl_N (up to the shock) is still "
                    "a measurement.")
            elif not (momentum_thrust > 0.0):
                bl_fraction_note = ("Momentum thrust is not positive; the "
                                    "loss fraction is undefined.")
            elif (bl_result.get('march', {}).get('status')
                    == _bl.MARCH_NUMERICAL_FAILURE):
                # P6B3-09 (fail-closed): the march reports its own outcome in
                # ``march.status`` and this consumer never read it. Measured
                # (D25 a2, once_a2.json -> "P6B3-09"): a march that fails
                # numerically still returns friction_drag_N = 0.0, and that
                # zero was published as 'integral_bl_measured' -- i.e. a
                # FAILED measurement was presented as a frictionless wall.
                # Separation / caller-stop / shock statuses are legitimate
                # PARTIAL marches and keep their fraction (the drag really
                # was integrated over the surface reached); only a numerical
                # failure has no measurement behind it.
                bl_fraction_note = (
                    "The boundary-layer march ended in numerical failure "
                    f"(march.status = {_bl.MARCH_NUMERICAL_FAILURE!r}); its "
                    "friction integral is not a measurement, so no loss "
                    "FRACTION is published from it and the published "
                    "fraction falls back to the declared bookkeeping "
                    "constant (friction_loss_fraction_source = "
                    "'legacy_constant').")
            else:
                bl_fraction = float(bl_result['friction_drag_N']
                                    / momentum_thrust)

        # --- GÖÇ: hangi kesir YAYIMLANIYOR? (16 Ağu 2026) ------------------
        # Sıra sabittir ve beyanlıdır:
        #   1) kullanıcı açıkça verdiyse       -> 'user'
        #   2) sınır tabakası kesri geçerliyse -> 'integral_bl_measured'
        #   3) aksi hâlde defter sabiti        -> 'legacy_constant'
        # (3) yalnız ÖLÇÜM YOKKEN devreye girer: lüle içi normal şok
        # (kesir tanımsız — iki sayı aynı yüzeye ait değil), boğulmamış
        # akış, sınır tabakası kapalı ya da marş başarısız.
        legacy_fraction = NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT
        if self.friction_loss_fraction_user is not None:
            friction_fraction = self.friction_loss_fraction_user
            friction_source = 'user'
            friction_basis = (
                "Caller-supplied friction_loss_fraction; the measured "
                "boundary-layer value is reported alongside but NOT used "
                "(explicit input always wins). Passing 0.015 here "
                "reproduces the pre-migration published numbers.")
        elif bl_fraction is not None:
            friction_fraction = bl_fraction
            friction_source = 'integral_bl_measured'
            friction_basis = (
                "MEASURED: compressible momentum-integral boundary layer "
                "(hrma.flow.boundary_layer — Thwaites 1949 / Head 1958 / "
                "Ludwieg-Tillmann 1950 closures, Eckert 1956 reference "
                "temperature), f = integral(2*pi*r*tau_w dx)/momentum_thrust "
                "over the same surface the momentum thrust is taken on. "
                "Migration 16 Aug 2026: this replaced the 1.5 % bookkeeping "
                "constant as the published default (Berke's decision; "
                "declared-change policy of docs/mimari/"
                "f2-yanma-tepkisi-tasarimi.md Sec. 8.1 decision 8; manifest "
                "tests/flow/test_surtunme_gocu.py). "
                "MODEL VALIDATION BAND (measured in the V5 batch, "
                "tests/flow/test_sinir_tabakasi.py): laminar flat plate vs "
                "Blasius c_f +0.90 %, theta +1.01 %, delta* +1.75 %, H "
                "+0.78 %; turbulent flat plate vs Schultz-Grunow (NACA TM "
                "986) c_f -2.6 % to -3.9 % (the known systematic sign of "
                "the Ludwieg-Tillmann closure). The nozzle number carries "
                "that model uncertainty plus everything in "
                "boundary_layer.not_modelled (wall roughness and "
                "relaminarization are the two that push in opposite "
                "directions).")
        else:
            friction_fraction = legacy_fraction
            friction_source = 'legacy_constant'
            friction_basis = (
                "NO MEASUREMENT AVAILABLE, legacy constant used: "
                "hrma.constants.NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT = "
                f"{legacy_fraction} (typical band 0.5-2 %, Sutton & Biblarz "
                "9th ed. Sec. 3.5; band not in NASA SP-125). This is a "
                "bookkeeping estimate, NOT a boundary-layer solution. "
                "Reason it was used: "
                + (bl_fraction_note if bl_fraction_note else
                   (f"boundary-layer solver failed ({bl_error})"
                    if bl_error else
                    "the boundary-layer solution was not computed "
                    "(include_boundary_layer=False or unchoked flow)."))
                + " Since 16 Aug 2026 the constant is only a fallback "
                  "(migration manifest: tests/flow/test_surtunme_gocu.py).")

        thrust_effective = (lambda_div * (1.0 - friction_fraction)
                            * momentum_thrust) + pressure_thrust
        # Göçün denetlenebilirliği: eski sabitin ürettiği sayı da yayımlanır
        # (kullanıcı "sayı neden değişti" diye sorduğunda karşılaştıracağı
        # taban budur; kaynak 'legacy_constant' iken beyanlı yankıdır).
        thrust_effective_legacy = (lambda_div * (1.0 - legacy_fraction)
                                   * momentum_thrust) + pressure_thrust

        losses = {
            'method': 'approximate',
            'divergence_factor': float(lambda_div),
            'divergence_loss_fraction': float(1.0 - lambda_div),
            'divergence_half_angle_deg': float(np.degrees(theta_exit)),
            'initial_wall_angle_deg': float(np.degrees(theta_n)),
            # P4B2-12: lambda_div'i FİİLEN üreten açı ve onun kaynağı.
            # Değişmez: divergence_factor == 0.5*(1+cos(bu açı)).
            'divergence_factor_angle_deg': float(np.degrees(theta_lambda)),
            'divergence_factor_angle_basis': lambda_basis,
            'friction_loss_fraction': float(friction_fraction),
            # Ayrık terimler (bulgu F143 dürüstlük alanları)
            'momentum_thrust_N': float(momentum_thrust),
            'pressure_thrust_N': float(pressure_thrust),
            'correction_applies_to': 'momentum_term_only',
            'thrust_effective_N': float(thrust_effective),
            'CF_effective': float(thrust_effective / (pc * a_throat_area)),
            'note': (lambda_note + " Since 16 Aug 2026 the friction loss is "
                     "the MEASURED momentum-integral boundary-layer value "
                     "whenever it can be published (see "
                     "friction_loss_fraction_source and "
                     "friction_loss_fraction_basis); the 1.5 % bookkeeping "
                     "constant is only a declared fallback. Both "
                     "corrections scale the MOMENTUM thrust only: F_eff = "
                     "lambda*(1-f)*mdot*v_e + (Pe-Pa)*Ae (Sutton & Biblarz "
                     "9th ed. Eq. 3-34); the pressure-thrust term is left "
                     "untouched."),
            # --- V5 ölçümü + 16 Ağu 2026 göçü ------------------------------
            'friction_loss_fraction_source': friction_source,
            'friction_loss_fraction_basis': friction_basis,
            'friction_loss_fraction_legacy_constant': float(legacy_fraction),
            'thrust_effective_legacy_constant_N': float(thrust_effective_legacy),
            'CF_effective_legacy_constant': float(
                thrust_effective_legacy / (pc * a_throat_area)),
            'friction_loss_fraction_integral_bl': bl_fraction,
            # Tanım göçten SONRA da SABİTE göredir (ölçüm − 0.015): kaynak
            # 'integral_bl_measured' iken "kullanılan kesre göre fark" sıfır
            # olurdu ve alan bilgi taşımazdı. Sayı göç öncesiyle aynıdır.
            'friction_loss_delta_vs_default': (
                None if bl_fraction is None
                else float(bl_fraction - legacy_fraction)),
            'friction_drag_integral_bl_N': (
                None if bl_result is None
                else float(bl_result['friction_drag_N'])),
            # Kaynak 'integral_bl_measured' iken aşağıdaki iki alan
            # thrust_effective_N / CF_effective'in BEYANLI YANKISIDIR
            # (bit-aynı); 'user' ve 'legacy_constant' kaynaklarında ise
            # "ölçüm kullanılsaydı ne olurdu" sayısıdır.
            'thrust_effective_integral_bl_N': (
                None if bl_fraction is None
                else float(lambda_div * (1.0 - bl_fraction) * momentum_thrust
                           + pressure_thrust)),
            'CF_effective_integral_bl': (
                None if bl_fraction is None
                else float((lambda_div * (1.0 - bl_fraction) * momentum_thrust
                            + pressure_thrust) / (pc * a_throat_area))),
            'boundary_layer': (None if bl_result is None
                               else _json_safe(bl_result)),
            'boundary_layer_error': bl_error,
            'friction_loss_fraction_bl_note': bl_fraction_note,
            'friction_comparison_basis': (
                "MIGRATION 16 Aug 2026 (loud, not silent): "
                "friction_loss_fraction is now the value actually USED for "
                "thrust_effective_N, and its origin is declared in "
                "friction_loss_fraction_source ('integral_bl_measured' = "
                "measured boundary layer, 'user' = explicit argument, "
                "'legacy_constant' = 1.5 % bookkeeping fallback when no "
                "measurement can be published). "
                "friction_loss_fraction_integral_bl is the MEASUREMENT from "
                "hrma.flow.boundary_layer (Thwaites/Head/Ludwieg-Tillmann + "
                "Eckert reference temperature), defined as "
                "F_friction/momentum_thrust with "
                "F_friction = integral(2*pi*r*tau_w dx) taken over the same "
                "surface as the momentum thrust; it is None where that "
                "surface identity breaks (in-nozzle normal shock). "
                "friction_loss_fraction_legacy_constant and "
                "thrust_effective_legacy_constant_N keep the PRE-migration "
                "numbers visible so the change is auditable; "
                "delta = integral_bl - legacy_constant. Manifest with the "
                "measured per-case table: tests/flow/test_surtunme_gocu.py "
                "(policy: docs/mimari/f2-yanma-tepkisi-tasarimi.md Sec. 8.1 "
                "decision 8)."),
        }

        # --- eksenel Bartz coupling (ithal korelasyon; kopya yok) ---
        h_g_list: List[float] = []
        q_list: List[float] = []
        taw_list: List[float] = []
        tw_list: List[float] = []
        wall_temperature_source = None
        if include_bartz:
            throat_d = float(throat['throat_diameter'])
            rc_over_dt = float(throat['rc_over_dt'])
            taw_arr = np.array([
                self._hta._adiabatic_wall_temperature(tc, gas, float(mach[i]))
                for i in range(n)])
            # ÖH D15 / P4B2-05: sessiz ``min(tw, taw − 1)`` kırpması yerine
            # TEK KAYNAK alan çözümü + fail-closed kapı (bkz.
            # ``_wall_temperature_field`` künyesi). Yayımlanan değer ile
            # kullanılan değer artık AYNIDIR.
            tw_arr, wall_temperature_source = \
                self._wall_temperature_field(taw_arr)
            for i in range(n):
                m_i = float(mach[i])
                taw = float(taw_arr[i])
                tw = float(tw_arr[i])
                h_i = self._hta._bartz_coefficient(
                    throat_d, pc, c_star_bartz, gas, tc, tw, rc_over_dt,
                    area_ratio_local=1.0 / float(area_ratio[i]),
                    mach_local=m_i,
                )
                h_g_list.append(float(h_i))
                q_list.append(float(h_i * (taw - tw)))
                taw_list.append(float(taw))
                tw_list.append(tw)

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
                # ÖH D15 / P4B2-05 — akının FİİLEN kurulduğu cidar sıcaklığı.
                # Kullanıcı değeri verildiyse sabit dizi (ve o değer artık
                # ``inputs.wall_temperature_K`` ile birebir aynıdır),
                # verilmediyse istasyon başına 0,8·T_aw.
                'T_wall_used_K': tw_list,
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
                # ÖH D15 / P4B2-08: yayımlanan c*'ın kaynağı. Bu modülde
                # yalnız 'ideal_theory' olabilir — kullanıcı c*'ı yukarıdaki
                # tutarlılık kapısında reddedilir (aynı yanıtta iki c* yok).
                'c_star_source': throat.get('c_star_source'),
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
                # ÖH D15 / P4B2-05: yankılanan değerin NEREDEN geldiği.
                # 'user_supplied' -> yukarıdaki sayı istasyonların hepsinde
                # AYNEN kullanıldı (kırpma yok, kapı ``_wall_temperature_field``
                # içinde). 'model_default_0.8_T_aw' -> kullanıcı vermedi,
                # istasyon başına 0,8·T_aw kullanıldı ve yayımlanan alan
                # ``stations.T_wall_used_K`` dizisidir. None -> Bartz bloğu
                # koşmadı (include_bartz=False / fast fidelity).
                'wall_temperature_source': wall_temperature_source,
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
                "Divergence loss is an approximate bookkeeping estimate "
                "(equivalent-cone lambda). The friction loss is the "
                "MEASURED momentum-integral boundary layer when "
                "losses.friction_loss_fraction_source == "
                "'integral_bl_measured' (migration 16 Aug 2026), and the "
                "1.5 % bookkeeping constant when it says 'legacy_constant' "
                "— the source field is the only honest answer to 'is this "
                "a solution or an estimate?'.",
                "In the separated regime the core station arrays keep the "
                "attached isentropic values (conservative for heat loads); "
                "wall_pressure_Pa carries the separated wall state.",
            ],
        }

        # ------------------------------------------------------------------
        # ÖH D15 / P4B2-06 — (a) ÇAPRAZ DOĞRULAMANIN HÜKMÜ, (b) FİZİK DIŞI
        # "referans" sayıların GERİ ÇEKİLMESİ.
        #
        # (a) Modül künyesi (:42-44) cidar basıncı integralini "a numerical
        #     cross-check of the exit-plane formula" diye satıyordu ama
        #     tutmadığında hiçbir hüküm/bayrak alanı YOKTU. ÖLÇÜLDÜ
        #     (31 Ağustos 2026, taban e88d096; Pc = 70 bar, eps = 25, konik):
        #       Pa = 0,5 bar  overexpanded   -> bağıl kalıntı %0,64
        #       Pa = 1 atm    separated      -> %0,89
        #       Pa = 10 bar   normal şok     -> %8,75
        #       Pa = 30 bar   normal şok     -> %129,47
        #       Pa = 60 bar   normal şok     -> %231,05   (3,3 kat ayrışma)
        #     Rejim test ediliyordu, çapraz test ediliyordu, ikisi HİÇ
        #     kesişmiyordu. Kalıntı artık ADLI BİR EŞİĞE karşı hükme
        #     bağlanır ve hüküm yayımlanır.
        #
        # (b) Aynı koşularda ürünün KABUL ETTİĞİ alt sınırda (Pc = 10 bar,
        #     deniz seviyesi, /api/flow-analysis HTTP 200) şunlar
        #     yayımlanıyordu: CF_ideal = −0,6907 ve thrust_full_flow_N =
        #     −5425,07 N. ``CF_ideal`` flow_panel.js:243'te "CF IDEAL" stat
        #     kartı olarak EKRANDA. "İdeal" (tam genişlemiş referans) bir
        #     itki katsayısı NEGATİF olamaz; negatif çıkması, referans hâlin
        #     formülün zarfı dışında olduğunu gösterir — sayının kendisi
        #     hükümsüzdür. Aynı şey "tam akışlı" referans itki için geçerli
        #     (şok rejiminde ölçülen: −95 059 / −487 758 / −1 076 807 N).
        #     Bu iki alan (ve tamamen ondan türeyen ayrılma kazancı) fizik
        #     dışı işaret aldığında GERİ ÇEKİLİR: ad ve künye kalır, sayı
        #     None olur, gerekçe adıyla yayımlanır — bu modülün P4B2-02'de
        #     kurulan geri çekme deseninin aynısı.
        _perf = result['performance']
        _resid = _perf['wall_integral_residual_rel']
        _perf['wall_integral_cross_check'] = {
            'residual_rel': _resid,
            'tolerance_rel': WALL_INTEGRAL_CROSS_CHECK_TOL,
            'agrees': (None if _resid is None
                       else bool(_resid <= WALL_INTEGRAL_CROSS_CHECK_TOL)),
            'basis': (
                "Wall-pressure integral F = mdot*u_t + (P_t - Pa)*A_t + "
                "int[(P_w - Pa) dA] compared with the exit-plane formula "
                "F = mdot*u_e + (P_e - Pa)*A_e. Agreement within "
                f"{WALL_INTEGRAL_CROSS_CHECK_TOL * 100:.0f} % is the "
                "quadrature band of this station grid; a larger residual "
                "means the two formulations do NOT describe the same flow "
                "and the published thrust is therefore NOT "
                "cross-checked. Deep overexpansion is solved as separated "
                "(Summerfield), where the wall-pressure plateau and the "
                "effective-exit momentum describe the same flow; residuals "
                "there are a few per cent. They grow again once the "
                "separation plane approaches the throat, where the "
                "first-order plateau model stops holding."),
        }
        _fizik_disi = [ad for ad in ('CF_ideal', 'thrust_full_flow_N')
                       if isinstance(_perf.get(ad), float)
                       and not (_perf[ad] > 0.0)]
        if _fizik_disi:
            _gerekce_ref = (
                "NON-PHYSICAL REFERENCE STATE: "
                + ' and '.join(_fizik_disi)
                + " came out non-positive. Both are FULLY-EXPANDED / "
                  "FULL-FLOWING reference quantities (Sutton & Biblarz 9th "
                  "ed. Eq. 3-30 for CF_ideal): a negative 'ideal' thrust "
                  "coefficient or reference thrust means the reference state "
                  "is outside the envelope of that formula for this ambient "
                  "pressure, not that the nozzle produces negative thrust. "
                  "The numbers are withheld rather than published; the "
                  "actual solution is thrust_N / CF. Lower the ambient "
                  "pressure or raise the chamber pressure for a case where "
                  "the fully-expanded reference exists.")
            for ad in _fizik_disi:
                _perf[ad] = None
            if 'thrust_full_flow_N' in _fizik_disi:
                # Ayrılma kazancı TAMAMEN geri çekilen referanstan türer.
                _perf['separation_thrust_gain_N'] = None
            _perf['reference_withheld_fields'] = list(_fizik_disi)
            _perf['reference_withheld_because'] = _gerekce_ref

        # ÖH D15 / P4B2-02 — F144'ün GERİ ALINMIŞ ayağı yeniden bağlandı.
        #
        # Yukarıdaki :811-823 yorumu "artık performans/kayıp sayıları None
        # döner" diye YAZILMIŞTI ama teli çekilmemişti: ``unchoked`` bayrağı
        # yalnız sınır tabakası bloğunu atlıyordu, performance/losses
        # sözlükleri dolmaya devam ediyordu. ÖLÇÜLDÜ (P_c = 1,0 bar,
        # P_a = 0,9999 bar, eps = 25): rejim 'unchoked' iken thrust_N =
        # −727,44 N (NEGATİF İTKİ), CF = −23,155, CF_ideal = −23,155,
        # losses.thrust_effective_N = −729,18 N yayımlanıyordu ve
        # flow_panel.js:241-250 bu sayıları CF / THRUST / EFFECTIVE THRUST
        # stat kartlarına basıyordu.
        #
        # Fizik: boğulmamış lülede boğazda M < 1'dir; alan-Mach bağıntısının
        # SÜPERSONİK dalı geçersizdir ve debi yalnız P_c'den belirlenemez
        # (çıkış koşulu gerekir) — Anderson, "Modern Compressible Flow",
        # 3. baskı, Böl. 5.4. Dolayısıyla bu rejimde itki, CF, debi, c* ve
        # kayıp dökümü HESAPLANAMAZ; sıfır ya da işaretli bir sayı koymak
        # uydurmadır. Sayılar GERİ ÇEKİLİR, alan adları ve künyeler kalır
        # (tüketiciler ``KeyError`` almaz, ``fmt(null)`` "—" çizer) ve
        # geri çekme gerekçesi ADIYLA yayımlanır.
        #
        # İstisna: ``expansion_ratio`` saf GEOMETRİDİR (A_e/A_t) ve akış
        # rejiminden bağımsızdır — geri çekilmez (figür altyazısı onu okur).
        if unchoked:
            _gerekce = (
                "UNCHOKED NOZZLE: the throat is not sonic, so the supersonic "
                "branch of the area-Mach relation does not apply and the "
                "mass flow is not fixed by the chamber pressure alone (an "
                "exit condition is required) — Anderson, Modern Compressible "
                "Flow, 3rd ed., Sec. 5.4. Thrust, CF, mass flow, c* and the "
                "loss breakdown CANNOT be computed from these inputs and are "
                "therefore withheld: this solver previously published a "
                "NEGATIVE thrust here. The station arrays are kept only as "
                "the hypothetical CHOKED reference (see stations_basis); "
                "raise the chamber pressure above the choking limit "
                "(regime.pressure_ratio_required) for a solvable case.")
            result['performance'] = self._withhold_numbers(
                result['performance'], keep=('expansion_ratio',))
            result['performance']['withheld_because'] = _gerekce
            # ÖH D15 / P4B2-06 ⟷ P4B2-02 KESİŞİMİ: geri çekilen bir sayının
            # ÜSTÜNDE hüküm duramaz. ``_withhold_numbers`` bool'ları bilerek
            # koruyor, bu yüzden ``wall_integral_cross_check.agrees`` (True)
            # ayakta kalırken dayandığı ``residual_rel``/``tolerance_rel``
            # None'a düşüyordu — "çapraz tutuyor" diyen ama hangi sayıyla
            # tuttuğunu söyleyemeyen bir hüküm (çapa koşumu B2/B3'te ölçüldü).
            # Boğulmamış rejimde itki zaten yayımlanmıyor; çapraz doğrulanacak
            # bir sayı da yoktur, dolayısıyla HÜKÜM DE geri çekilir. Aynı
            # gerekçeyle "referans geri çekildi" notu da kaldırılır: bu rejimde
            # geri çekme sebebi TEKTİR (boğulmamış lüle) ve iki ayrı gerekçe
            # ikinci bir sebep gibi okunur.
            _cc = result['performance'].get('wall_integral_cross_check')
            if isinstance(_cc, dict):
                _cc['agrees'] = None
            result['performance'].pop('reference_withheld_because', None)
            result['performance'].pop('reference_withheld_fields', None)
            result['losses'] = self._withhold_numbers(result['losses'])
            result['losses']['withheld_because'] = _gerekce
            result['performance_withheld_because'] = _gerekce
            result['stations_basis'] = (
                "HYPOTHETICAL CHOKED REFERENCE, not a solution: the flow is "
                "unchoked, so these station values describe the choked case "
                "the same geometry WOULD produce. Do not read them as the "
                "actual flow field.")
            result['assumptions'].append(
                "Unchoked regime: no performance or loss number is "
                "published (see performance_withheld_because); the station "
                "arrays are a labelled hypothetical choked reference.")
        # NOT (ÖH D19 / P15B4-09 — D17'nin AÇILMAYAN yarısı KAPANDI):
        # D17'de şok bandının ``performance``/``losses`` sayılarını GERİ
        # ÇEKMEK denenmiş, 12 bekçiyi kırdığı için geri alınmıştı. Geri
        # çekme zaten yanlış araçtı: sayı hesaplanamadığı için değil, YANLIŞ
        # AKIŞ için hesaplandığı için kusurluydu. D19'da kök sebep
        # düzeltildi — Summerfield ölçütü rejim merdiveninde normal-şok
        # dalının ÖNÜNE alındı (bkz. ``_classify_regime``), böylece ölçütün
        # sağlandığı vakalar ayrılma çözümüyle çözülüyor ve yayımlanan sayı
        # GERÇEKLEŞEN akışı tarif ediyor. Geri çekmeye gerek kalmadı:
        # ``friction_drag_integral_bl_N`` (sınır tabakası integralinden
        # ÖLÇÜLEN cidar sürtünme kuvveti) ve sürtünme göçü manifestosunun
        # sözleşmesi aynen ayakta; cidar-integrali çapraz hükmü ise
        # DÜZELDİ.
        #
        # ÖH D25 / P15B4-09 (Fable-D19 ŞART) — yukarıdaki eşleme bir satır
        # KAYMIŞTI ("%129,47/%231,05 -> %1,9668/%2,7437"): %129,47 ve
        # %231,05 sırasıyla 30 ve 60 barın ÖNCE değerleridir, 10 ve 30
        # barın değil. Ölçülen doğru eşleme (LULE: P_c = 70 bar, eps = 25,
        # D_t = 100 mm; bkz. :174-179 ve :1592-1594 aynı üç sayı):
        #     kalıntı 10 bar %8,751 / 30 bar %129,47 / 60 bar %231,05
        #          -> %1,9668 / %2,7437 / %10,2385
        #     (60 bar HÂLÂ uyuşmuyor: ayrılma düzlemi boğaza çok yakın,
        #      birinci-derece Summerfield platosu yetersiz; hüküm
        #      dürüstçe ``agrees = False`` kalır — fail-closed.)
        return result

    @staticmethod
    def _withhold_numbers(blok, keep=()):
        """Sözlükteki her SAYIYI ``None`` yapar; adları ve künyeleri korur.

        Geri çekme, anahtarı SİLMEKTEN yeğdir: tüketiciler (panel, figür,
        ihraç) alan adını arıyor ve eksik anahtarı "eski sürüm" sanabiliyor;
        ``None`` ise "bu koşuda hesaplanamadı" demektir ve ``fmt`` onu "—"
        çizer. Dizeler (künye/kaynak/not alanları) DOKUNULMAZ — geri çekme
        gerekçesinin okunabilmesi onlara bağlıdır.

        Args:
            blok: performance ya da losses sözlüğü.
            keep: rejimden BAĞIMSIZ (geometrik) alan adları — korunur.
        """
        if not isinstance(blok, dict):
            return blok
        cikti = {}
        for ad, deger in blok.items():
            if ad in keep:
                cikti[ad] = deger
            elif isinstance(deger, bool) or deger is None:
                cikti[ad] = deger
            elif isinstance(deger, (int, float)):
                cikti[ad] = None
            elif isinstance(deger, dict):
                cikti[ad] = NozzleFlow1D._withhold_numbers(deger, keep=keep)
            elif isinstance(deger, (list, tuple)):
                cikti[ad] = None if deger else deger
            else:
                cikti[ad] = deger
        return cikti
