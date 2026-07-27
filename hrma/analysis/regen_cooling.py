"""
Regenerative Cooling 1D Station-Marching Module.

Analysis-mode (NOT auto-sizing) one-dimensional regenerative cooling model for
liquid / hybrid rocket thrust chambers and nozzles. The channel geometry
(number of channels, width, height) and the inner-liner thickness are USER
INPUTS — this module solves the coupled gas-side / wall / coolant thermal and
hydraulic problem for the geometry you give it; it does not iterate the channel
dimensions to hit a target (that is a separate design-optimization concern, an
R&D decision left to the engineer).

Physics and references
----------------------
Gas side (hot wall convection):
  - Bartz convective coefficient h_g(x) is IMPORTED from
    ``HeatTransferAnalyzer._bartz_coefficient`` (Bartz 1957; Sutton & Biblarz,
    "Rocket Propulsion Elements", 9th ed., Eq. 8-22, SI-consistent form). The
    correlation is NOT re-implemented here — single source of truth, same
    convention as ``HeatTransferAnalyzer.analyze_axial_profile`` and
    ``nozzle_flow_1d``.
  - Driving temperature is the adiabatic-wall (recovery) temperature Taw(x)
    (``HeatTransferAnalyzer._adiabatic_wall_temperature``), NOT the stagnation
    temperature. Huzel & Huang, "Modern Engineering for Design of
    Liquid-Propellant Rocket Engines", AIAA, Ch. 4 (Eq. 4-10 ff.);
    Sutton & Biblarz 9th ed. Ch. 8.

Coolant side (forced convection in the channels):
  - Dittus-Boelter correlation for turbulent forced convection in ducts,
    HEATING of the fluid (exponent n = 0.4):
        Nu = 0.023 * Re^0.8 * Pr^0.4
    Validity band (Incropera & DeWitt, "Fundamentals of Heat and Mass
    Transfer", 6th ed., Eq. 8.60): fully-developed turbulent flow,
    Re >= 1e4, 0.6 <= Pr <= 160, L/D >= 10. The correlation is applied per
    station with local bulk properties; a warning is raised where Re drops
    below the turbulent floor. Rectangular-channel hydraulic diameter
    D_h = 4*A_c / P_wet = 2*w*h/(w+h) (Incropera Ch. 8).
  - This is the classic first-cut regenerative-cooling coolant correlation
    (Huzel & Huang Ch. 4). More elaborate curved-channel / high-heat-flux
    corrections (e.g. wall-to-bulk viscosity ratio, entrance, curvature
    enhancement) are NOT applied; the bulk Dittus-Boelter value is a mildly
    conservative estimate and is tagged 'approximate' in the model note.

Wall conduction (radial, thin-liner flat-plate approximation):
  - The inner liner is treated as a flat plate of thickness t_w and
    conductivity k_w (from ``hrma.data.materials_db``). The series thermal
    circuit per unit gas-side area is
        q = (Taw - T_coolant) / ( 1/h_g + t_w/k_w + 1/h_c )
    with the hot- and cold-wall temperatures back-computed from q:
        T_wall_hot  = Taw       - q / h_g
        T_wall_cold = T_coolant + q / h_c
    (Huzel & Huang Ch. 4 one-dimensional wall model; Sutton & Biblarz 9th ed.
    Ch. 8). The thin-wall flat-plate approximation is valid when t_w << r_wall
    and neglects channel-land (fin) conduction spreading — coolant-side heat
    transfer area is taken equal to the gas-side area (fin efficiency ~ 1),
    which is the standard analysis-mode assumption and tagged 'approximate'.

Coolant temperature march (station-to-station enthalpy balance):
  - Steady thin-wall energy balance: all gas-side heat over a wall segment is
    absorbed by the coolant, dQ = q * dA (dA = local circumference * slant
    length). The coolant bulk temperature is advanced by
        dT = dQ / (mdot * cp(T_bulk)).
    Default flow arrangement is COUNTERFLOW: the coolant enters at the nozzle
    exit and flows toward the throat and chamber (opposite the combustion gas),
    the standard regenerative arrangement (Huzel & Huang Ch. 4). Co-flow is
    also selectable.

Coolant pressure drop (Darcy-Weisbach + Haaland friction factor):
  - dP = f * (ds / D_h) * (rho * V^2 / 2)   (Darcy-Weisbach; White, "Fluid
    Mechanics", 7th ed., Eq. 6.10).
  - Turbulent friction factor from the Haaland (1983) explicit approximation
    to the Colebrook equation:
        1/sqrt(f) = -1.8 * log10[ (6.9/Re) + (eps/D_h/3.7)^1.11 ]
    (White 7th ed. Eq. 6.49; accurate to ~2 % vs Colebrook over the turbulent
    range). Laminar (Re < 2300) uses f = 64/Re (White Eq. 6.12).

Coolant properties:
  - RP-1 and water are supported via small temperature-dependent property
    tables (density, cp, thermal conductivity, viscosity). Water values are
    saturated-liquid data from Incropera & DeWitt 6th ed. Table A.6. RP-1
    values are approximate engineering compilations (Huzel & Huang App.;
    NASA RP-1 property data; NIST). RP-1 numbers carry a stated uncertainty
    band and are tagged 'approximate'.
  - If CoolProp is installed it is used for WATER (fluid 'Water') at the local
    (T, P) state; RP-1 is a multi-component fuel not represented as a single
    CoolProp fluid, so its internal table is always used. Property source is
    selectable and can be forced to the internal table for reproducibility.

Supercritical methane / hydrogen coolants (added 2026-07-22):
  - ``coolant='methane'`` and ``coolant='hydrogen'`` are supported with FULL
    (T, P)-dependent properties from CoolProp (Bell et al. 2014, Ind. Eng.
    Chem. Res. 53(6)): methane EOS Setzmann & Wagner (1991, J. Phys. Chem.
    Ref. Data 20), hydrogen as PARA-hydrogen (Leachman et al. 2009, J. Phys.
    Chem. Ref. Data 38 — rocket-grade LH2 is >99 % para at NBP). CoolProp is
    MANDATORY for these coolants: there is no internal table and no constant
    fallback (fabricated-value guard); an out-of-range state raises an
    explicit ValueError.
  - The coolant march for these fluids is ENTHALPY based:
        h2 = h1 + dQ/mdot,   T = T(P, h)
    instead of dT = dQ/(mdot*cp). Near the pseudo-critical temperature the
    cp(T) peak (e.g. CH4: T_pc ~ 199-252 K for 60-300 bar) makes the cp form
    inaccurate; the enthalpy form is exact for steady single-phase flow.
  - Coolant-side heat transfer at supercritical pressure uses the Jackson
    forced-convection correlation with wall-to-bulk property-ratio
    corrections (Jackson & Hall 1979, in Kakac & Spalding eds., "Turbulent
    Forced Convection in Channels and Bundles", Vol. 2; restated in Jackson
    2013, Nucl. Eng. Des. 264):
        Nu_b = 0.0183 Re_b^0.82 Pr_b^0.5 (rho_w/rho_b)^0.3 (cp_bar/cp_b)^n
    with cp_bar = (h_w - h_b)/(T_w - T_b) and the piecewise n exponent based
    on T_b, T_w and the pseudo-critical temperature T_pc (cp-maximum at the
    local pressure). This correlation family is the standard engineering
    model for supercritical-methane rocket cooling channels (e.g. Urbano &
    Nasuti 2013, J. Thermophys. Heat Transfer 27(2)). Because Nu depends on
    the cold-wall temperature, the station wall balance solves the coupled
    (h_g, h_c, T_wall_hot, T_wall_cold) fixed point with damping.
  - Coolant-side area on this path uses the channel-land EXTENDED-SURFACE
    (fin) model (``fin_area_ratio``, default on via ``fin_effect=True``):
    the two channel side walls act as straight rectangular fins,
    eta_f = tanh(mL)/(mL), m = sqrt(2 h_c/(k_w t_land)) (Incropera &
    DeWitt 6th ed. Ch. 3.6; lands-as-fins treatment per Huzel & Huang
    Ch. 4). The legacy water/RP-1 path keeps its original coolant-side
    area = gas-side area assumption unchanged.
  - Channel pressure drop adds the ACCELERATION (momentum) term to the
    Darcy-Weisbach friction term:
        dP_acc = G^2 * (1/rho_out - 1/rho_in)
    (1D steady momentum balance, constant-area duct; Collier & Thome,
    "Convective Boiling and Condensation", 3rd ed., Ch. 2).
  - If the local channel pressure is BELOW the coolant critical pressure the
    solver falls back to Dittus-Boelter and checks the local saturation
    temperature: bulk or cold-wall temperatures at/near T_sat raise explicit
    boiling-risk warnings (the model itself remains single phase — boiling
    is NOT modelled, it is flagged).

Integration API (for the liquid-engine chain; kept module-local here):
  - Inputs: coolant + coolant_mdot [kg/s] + coolant_inlet_temp [K] +
    coolant_inlet_pressure [Pa], channel geometry (n_channels, width, height,
    wall_thickness, wall_material, roughness), nozzle geometry (throat/exit
    diameter or expansion ratio) and the gas-side state (chamber P/T, gamma,
    MW or a full ``motor_data`` dict — Bartz flux is computed internally from
    the shared HeatTransferAnalyzer single source).
  - Call ``RegenCooling(...).solve()``. Outputs: ``summary`` block with
    coolant_exit_temp_K (T_out), coolant_exit_pressure_bar (P_out),
    max_wall_hot_K (Twall_max), pressure-drop split
    (friction/acceleration), warnings list; plus per-station arrays
    (x_mm, T_wall_hot_K, T_wall_cold_K, T_coolant_K, P_coolant_bar, q_MW_m2,
    velocity_m_s, coolant enthalpy for methane/hydrogen).

Coking:
  - RP-1 begins to coke (form carbon deposits) when the fuel-side (cold) wall
    temperature exceeds ~561 K. A warning is raised when any station's
    coolant-side wall temperature exceeds this threshold. Huzel & Huang Ch. 4.

Units: SI throughout the class API (Pa, K, m, kg/s). Repo-style ``motor_data``
dictionaries (chamber_pressure in bar) are supported via ``from_motor_data``.
User-visible strings are English; inline comments may be Turkish.
"""

import math
from typing import Dict, List, Optional

import numpy as np

# Tek kaynak: Bartz korelasyonu + gaz özellikleri + alan-Mach çözücü
# heat_transfer_analysis'ten İTHAL edilir (kopya yok — parametre tutarlılığı).
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.data.materials_db import get_material

# CoolProp opsiyoneldir (bundle'da var); yoksa dahili tablolara düşülür.
try:  # pragma: no cover - ortam bağımlı
    from CoolProp.CoolProp import PropsSI as _CP_PropsSI
    _HAS_COOLPROP = True
except Exception:  # pragma: no cover
    _CP_PropsSI = None
    _HAS_COOLPROP = False

__all__ = [
    'RegenCooling',
    'dittus_boelter_nu',
    'hydraulic_diameter_rect',
    'haaland_friction_factor',
    'darcy_weisbach_dp',
    'water_properties',
    'rp1_properties',
    'RP1_COKING_TEMP_K',
    'jackson_nu',
    'jackson_exponent_n',
    'pseudocritical_temperature',
    'acceleration_dp',
    'fin_area_ratio',
    'SUPERCRITICAL_COOLANT_FLUIDS',
    'BOILING_MARGIN_K',
]

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
# RP-1 koklaşma (coking) eşiği: yakıt tarafı cidar sıcaklığı bu değeri aşınca
# karbon birikimi başlar. Huzel & Huang, "Modern Engineering for Design of
# Liquid-Propellant Rocket Engines", Böl. 4.
RP1_COKING_TEMP_K = 561.0

# Laminer/türbülan geçiş Reynolds sayısı (boru akışı, White 7. baskı Böl. 6).
RE_LAMINAR_MAX = 2300.0
# Dittus-Boelter türbülan geçerlilik tabanı (Incropera 6. baskı Eq. 8.60).
RE_TURBULENT_FLOOR = 1.0e4

# Rejeneratif soğutma marşının kendi istasyon klampı (testlerle çapalı 20/50).
# nozzle_flow_1d'nin 30/60 klampından BİLEREK farklı — ayrı modül, ayrı
# ayrıklaştırma politikası; ad çakışması olmasın diye REGEN_ önekiyle.
REGEN_N_STATIONS_MIN = 20
REGEN_N_STATIONS_MAX = 50

FLOW_COUNTERFLOW = 'counterflow'  # soğutucu çıkış -> boğaz -> kamara (varsayılan)
FLOW_COFLOW = 'coflow'            # soğutucu kamara -> boğaz -> çıkış

# Süperkritik-yetenekli soğutucular -> CoolProp akışkan adları.
# Metan: Setzmann & Wagner (1991) EOS. Hidrojen: PARA-hidrojen
# (Leachman ve ark. 2009) — roket LH2'si NBP'de >%99 para izomeridir;
# normal (%75 orto) hidrojen değil.
SUPERCRITICAL_COOLANT_FLUIDS = {
    'methane': 'Methane',
    'hydrogen': 'ParaHydrogen',
}

# Kaynama-riski tarama marjı [K]: kritik-altı basınçta yığın sıcaklığı yerel
# Tsat'a bu kadar yaklaşınca uyarı üretilir. Mühendislik tarama eşiğidir
# (fiziksel sabit değil); uyarı metninde açıkça belirtilir.
BOILING_MARGIN_K = 10.0

# Pseudo-kritik sıcaklık önbelleği: (akışkan, 0.5 bar kovalı basınç) -> T_pc.
_PSEUDOCRITICAL_CACHE: Dict = {}

# ---------------------------------------------------------------------------
# Soğutucu özellik tabloları (sıcaklığa bağlı, doğrusal interpolasyon)
# ---------------------------------------------------------------------------
# Su — doymuş sıvı (Incropera & DeWitt 6. baskı, Tablo A.6).
# Sıra: T[K], rho[kg/m^3], cp[J/kg/K], k[W/m/K], mu[Pa*s]
_WATER_TABLE = np.array([
    [280.0, 1000.0, 4198.0, 0.582, 1.422e-3],
    [300.0,  997.0, 4179.0, 0.613, 0.855e-3],
    [320.0,  989.0, 4180.0, 0.640, 0.577e-3],
    [340.0,  979.0, 4188.0, 0.660, 0.420e-3],
    [360.0,  967.0, 4203.0, 0.674, 0.324e-3],
    [380.0,  953.0, 4226.0, 0.683, 0.260e-3],
    [400.0,  937.0, 4256.0, 0.688, 0.217e-3],
])

# RP-1 — YAKLAŞIK mühendislik derlemesi (Huzel & Huang App.; NASA RP-1 veri
# derlemeleri; NIST). Bant: rho +/-2 %, cp +/-8 %, k +/-15 %, mu +/-25 %.
# Tek kaynaklı, kesin değil — 'approximate' etiketli.
_RP1_TABLE = np.array([
    [290.0, 806.0, 1880.0, 0.140, 1.70e-3],
    [320.0, 784.0, 1980.0, 0.135, 1.00e-3],
    [350.0, 762.0, 2075.0, 0.130, 0.68e-3],
    [400.0, 724.0, 2245.0, 0.122, 0.42e-3],
    [450.0, 686.0, 2415.0, 0.114, 0.30e-3],
    [500.0, 648.0, 2585.0, 0.106, 0.23e-3],
])


def _interp_table(table: np.ndarray, temperature: float) -> Dict[str, float]:
    """Bir özellik tablosunda (uçlarda klamplı) doğrusal interpolasyon."""
    t_col = table[:, 0]
    t = float(min(max(temperature, t_col[0]), t_col[-1]))
    rho = float(np.interp(t, t_col, table[:, 1]))
    cp = float(np.interp(t, t_col, table[:, 2]))
    k = float(np.interp(t, t_col, table[:, 3]))
    mu = float(np.interp(t, t_col, table[:, 4]))
    return {
        'density': rho,
        'cp': cp,
        'conductivity': k,
        'viscosity': mu,
        'prandtl': cp * mu / k,
        'clamped': bool(temperature < t_col[0] or temperature > t_col[-1]),
        # DÜZELTME (v2.6.2, fizik denetimi F057): tablo bandı da döndürülür.
        # 'clamped' bayrağı tek başına üretiliyordu ama solve() içinde HİÇ
        # okunmuyordu; klamplanan istasyonlar için uyarı üretilebilsin diye
        # bandın uçları da çağırana taşınıyor.
        'table_t_min_K': float(t_col[0]),
        'table_t_max_K': float(t_col[-1]),
    }


def water_properties(temperature: float) -> Dict[str, float]:
    """Liquid-water transport properties [SI] at ``temperature`` [K].

    Saturated-liquid data, Incropera & DeWitt 6th ed. Table A.6, linearly
    interpolated over 280-400 K and clamped outside that range. Returns
    density [kg/m^3], cp [J/kg/K], conductivity [W/m/K], viscosity [Pa*s],
    Prandtl number and a ``clamped`` flag.
    """
    return _interp_table(_WATER_TABLE, temperature)


def rp1_properties(temperature: float) -> Dict[str, float]:
    """RP-1 transport properties [SI] at ``temperature`` [K] (APPROXIMATE).

    Engineering compilation (Huzel & Huang App.; NASA RP-1 data; NIST),
    interpolated over 290-500 K and clamped outside. Property uncertainty is
    material (see module table banding); use for screening, not certification.
    """
    return _interp_table(_RP1_TABLE, temperature)


# ---------------------------------------------------------------------------
# Modül-düzeyi hidrolik/ısı yardımcıları (analitik, birim testli)
# ---------------------------------------------------------------------------
def dittus_boelter_nu(reynolds: float, prandtl: float,
                      heating: bool = True) -> float:
    """Dittus-Boelter Nusselt number for turbulent duct flow.

        Nu = 0.023 * Re^0.8 * Pr^n,   n = 0.4 (heating) / 0.3 (cooling)

    Incropera & DeWitt 6th ed. Eq. 8.60. Validity: Re >= 1e4,
    0.6 <= Pr <= 160, L/D >= 10 (fully-developed turbulent flow).
    """
    if reynolds <= 0.0:
        raise ValueError("Reynolds number must be positive.")
    if prandtl <= 0.0:
        raise ValueError("Prandtl number must be positive.")
    n = 0.4 if heating else 0.3
    return 0.023 * reynolds ** 0.8 * prandtl ** n


#: Dittus-Boelter geçerlilik zarfı (Incropera & DeWitt 6. baskı Eq. 8.60).
#: Korelasyonun kendi bildirilen saçılımı yaklaşık +/-%25'tir.
DB_RE_MIN = 1.0e4
DB_PR_MIN, DB_PR_MAX = 0.6, 160.0
DB_LD_MIN = 10.0
DB_REPORTED_SCATTER_PCT = 25.0


def dittus_boelter_envelope(reynolds: float, prandtl: float,
                            length_over_diameter: float = None) -> dict:
    """Dittus-Boelter geçerlilik zarfını tarar (v2.6.2 fizik denetimi, F154).

    Kodda yalnız Reynolds taranıyordu; Prandtl bandı ve giriş-uzunluğu
    (L/D >= 10, tam gelişmiş türbülanslı akış) koşulu hiç denetlenmiyordu.
    Zarf dışında korelasyon hâlâ bir sayı üretir ama o sayının bildirilen
    +/-%25 saçılımı geçerli değildir — kullanıcı bunu bilmeden ısı akısına
    güvenemez.

    Ayrıca büyük cidar/yığın özellik farkında Dittus-Boelter'in bilinen
    sapması için Sieder-Tate (mu_b/mu_w)^0.14 düzeltmesi UYGULANMAZ; bu da
    burada niceliksel olarak beyan edilir.

    Dönüş: ``{'in_envelope': bool, 'violations': [...], 'scatter_pct': 25.0}``
    """
    violations = []
    if reynolds < DB_RE_MIN:
        violations.append(
            f'Re={reynolds:.3g} < {DB_RE_MIN:.0g} (tam türbülanslı değil; '
            'geçiş rejiminde korelasyon geçersizdir)')
    if not (DB_PR_MIN <= prandtl <= DB_PR_MAX):
        violations.append(
            f'Pr={prandtl:.3g} bandın [{DB_PR_MIN}, {DB_PR_MAX}] dışında')
    if length_over_diameter is not None and length_over_diameter < DB_LD_MIN:
        violations.append(
            f'L/D={length_over_diameter:.3g} < {DB_LD_MIN:.0f} (giriş bölgesi; '
            'yerel Nu tam gelişmiş değerin üzerindedir)')
    return {
        'in_envelope': not violations,
        'violations': violations,
        'scatter_pct': DB_REPORTED_SCATTER_PCT,
        'sieder_tate_correction_applied': False,
        'note': ('Dittus-Boelter reported scatter is about '
                 f'+/-{DB_REPORTED_SCATTER_PCT:.0f}%; the Sieder-Tate '
                 '(mu_b/mu_w)^0.14 correction for large wall-to-bulk property '
                 'differences is NOT applied.'),
    }


def hydraulic_diameter_rect(width: float, height: float) -> float:
    """Hydraulic diameter of a rectangular channel [m].

        D_h = 4*A_c / P_wet = 2*w*h/(w+h)

    Incropera & DeWitt 6th ed. Ch. 8 (non-circular ducts).
    """
    if width <= 0.0 or height <= 0.0:
        raise ValueError("Channel width and height must be positive [m].")
    return 2.0 * width * height / (width + height)


def haaland_friction_factor(reynolds: float, rel_roughness: float) -> float:
    """Darcy friction factor from the Haaland explicit approximation.

        1/sqrt(f) = -1.8 * log10[ (6.9/Re) + (eps/D/3.7)^1.11 ]   (turbulent)
        f = 64/Re                                                  (laminar)

    Haaland (1983); White, "Fluid Mechanics", 7th ed., Eqs. 6.12, 6.49.
    Accurate to ~2 % vs the implicit Colebrook equation for Re > ~4000.
    """
    if reynolds <= 0.0:
        raise ValueError("Reynolds number must be positive.")
    if rel_roughness < 0.0:
        raise ValueError("Relative roughness must be non-negative.")
    if reynolds < RE_LAMINAR_MAX:
        return 64.0 / reynolds
    inv_sqrt_f = -1.8 * math.log10((6.9 / reynolds)
                                   + (rel_roughness / 3.7) ** 1.11)
    return 1.0 / (inv_sqrt_f * inv_sqrt_f)


def darcy_weisbach_dp(friction_factor: float, length: float,
                      hydraulic_diameter: float, density: float,
                      velocity: float) -> float:
    """Darcy-Weisbach pressure drop [Pa] over a duct length.

        dP = f * (L / D_h) * (rho * V^2 / 2)

    White, "Fluid Mechanics", 7th ed., Eq. 6.10.
    """
    if hydraulic_diameter <= 0.0:
        raise ValueError("Hydraulic diameter must be positive [m].")
    return (friction_factor * (length / hydraulic_diameter)
            * 0.5 * density * velocity * velocity)


def fin_area_ratio(channel_width: float, channel_height: float,
                   pitch: float, land_thickness: float,
                   h_coolant: float, k_wall: float) -> float:
    """Coolant-side extended-surface (fin) area ratio A_eff/A_gas.

    Milled-channel regen liners expose the channel bottom PLUS the two side
    walls (lands) to the coolant; the lands act as straight rectangular fins
    of thickness t_land and height h_ch. Standard treatment (Huzel & Huang,
    "Modern Engineering for Design of Liquid-Propellant Rocket Engines",
    Ch. 4 — channel lands as fins; Incropera & DeWitt 6th ed. Ch. 3.6):

        eta_f = tanh(m*h_ch) / (m*h_ch),   m = sqrt(2*h_c / (k_w * t_land))
        A_eff/A_gas = (w + 2*eta_f*h_ch) / pitch

    (adiabatic fin tip, Incropera Eq. 3.86; m from Eq. 3.85 with
    P/A_c ~ 2/t for a thin rectangular fin). Each land is shared by two
    neighbouring channels, so per channel-pitch exactly one land (two half
    sides) is counted: w + 2*eta*h over the pitch.
    """
    if pitch <= 0.0 or channel_width <= 0.0 or channel_height <= 0.0:
        raise ValueError("pitch, channel width and height must be positive.")
    if h_coolant <= 0.0 or k_wall <= 0.0:
        raise ValueError("h_coolant and k_wall must be positive.")
    t_land = max(land_thickness, 1.0e-5)   # sayısal taban (kanallar sığmıyorsa
    #                                        ayrı GEOMETRY uyarısı zaten var)
    m_fin = math.sqrt(2.0 * h_coolant / (k_wall * t_land))
    m_l = m_fin * channel_height
    eta_f = math.tanh(m_l) / m_l if m_l > 1.0e-9 else 1.0
    return (channel_width + 2.0 * eta_f * channel_height) / pitch


def acceleration_dp(mass_flux: float, rho_in: float, rho_out: float) -> float:
    """Acceleration (momentum) pressure drop [Pa] in a constant-area duct.

        dP_acc = G^2 * (1/rho_out - 1/rho_in),   G = mdot/A_c  [kg/m^2/s]

    One-dimensional steady momentum balance for a constant-area channel
    (Collier & Thome, "Convective Boiling and Condensation", 3rd ed., Ch. 2,
    acceleration pressure-gradient term). Positive when the heated fluid
    expands (rho_out < rho_in) — significant for supercritical coolants whose
    density changes strongly along the channel.
    """
    if rho_in <= 0.0 or rho_out <= 0.0:
        raise ValueError("Densities must be positive [kg/m^3].")
    return mass_flux * mass_flux * (1.0 / rho_out - 1.0 / rho_in)


def jackson_exponent_n(t_bulk: float, t_wall: float, t_pc: float) -> float:
    """Jackson property-ratio exponent n for the (cp_bar/cp_b)^n term.

    Piecewise form (Jackson & Hall 1979; Jackson 2013, Nucl. Eng. Des. 264):

        n = 0.4                                    T_w <= T_pc  or  T_b >= 1.2*T_pc
        n = 0.4 + 0.2*(T_w/T_pc - 1)               T_b <= T_pc < T_w
        n = 0.4 + 0.2*(T_w/T_pc - 1)
                * (1 - 5*(T_b/T_pc - 1))           T_pc < T_b < 1.2*T_pc, T_b < T_w

    Continuous across the regime boundaries (checked in tests).
    """
    if t_pc <= 0.0 or t_bulk <= 0.0 or t_wall <= 0.0:
        raise ValueError("Temperatures must be positive [K].")
    if t_wall <= t_pc or t_bulk >= 1.2 * t_pc:
        return 0.4
    if t_bulk <= t_pc:
        return 0.4 + 0.2 * (t_wall / t_pc - 1.0)
    return (0.4 + 0.2 * (t_wall / t_pc - 1.0)
            * (1.0 - 5.0 * (t_bulk / t_pc - 1.0)))


def jackson_nu(reynolds: float, prandtl: float, rho_wall_over_bulk: float,
               cp_bar_over_bulk: float, n_exponent: float) -> float:
    """Jackson supercritical forced-convection Nusselt number.

        Nu_b = 0.0183 * Re_b^0.82 * Pr_b^0.5
               * (rho_w/rho_b)^0.3 * (cp_bar/cp_b)^n

    Jackson & Hall (1979), in Kakac & Spalding (eds.), "Turbulent Forced
    Convection in Channels and Bundles", Vol. 2; restated in Jackson (2013),
    Nucl. Eng. Des. 264. cp_bar = (h_w - h_b)/(T_w - T_b) is the integrated
    mean specific heat between bulk and wall. Standard engineering model for
    supercritical-pressure cooling channels (applied to CH4 rocket cooling in
    e.g. Urbano & Nasuti 2013, J. Thermophys. Heat Transfer 27(2)).
    """
    if reynolds <= 0.0:
        raise ValueError("Reynolds number must be positive.")
    if prandtl <= 0.0:
        raise ValueError("Prandtl number must be positive.")
    if rho_wall_over_bulk <= 0.0 or cp_bar_over_bulk <= 0.0:
        raise ValueError("Property ratios must be positive.")
    return (0.0183 * reynolds ** 0.82 * prandtl ** 0.5
            * rho_wall_over_bulk ** 0.3 * cp_bar_over_bulk ** n_exponent)


def pseudocritical_temperature(fluid: str, pressure: float) -> float:
    """Pseudo-critical temperature T_pc(P) [K] at a supercritical pressure.

    Defined as the temperature of the isobaric cp maximum at P > P_crit
    (standard definition; Jackson 2013, Nucl. Eng. Des. 264), searched over
    the band [T_crit, min(2*T_crit, T_max)]: a coarse grid locates the
    maximum (cp(T) is NOT globally unimodal — the ideal-gas cp rise at high
    T creates a second branch, so a bare golden-section can walk to the
    wrong side), then a golden-section refinement narrows it to ~0.05 K.
    If the maximum sits at the band edge the edge value is returned: at very
    high reduced pressures the pseudo-critical line fades out and the
    Jackson regime classification then degenerates to the plain n = 0.4
    form — a bounded, documented behaviour. Results are cached per (fluid,
    0.5-bar pressure bin). Raises for P <= P_crit (pseudo-critical
    temperature is undefined there; use T_sat) and without CoolProp.
    """
    if not _HAS_COOLPROP:
        raise RuntimeError("CoolProp is required for "
                           "pseudocritical_temperature().")
    p_crit = float(_CP_PropsSI('Pcrit', fluid))
    if pressure <= p_crit:
        raise ValueError(
            f"Pseudo-critical temperature is defined only above the critical "
            f"pressure ({p_crit / 1e5:.2f} bar for {fluid}); "
            f"got {pressure / 1e5:.2f} bar.")
    key = (fluid, int(round(pressure / 5.0e4)))  # 0.5 bar kova
    if key in _PSEUDOCRITICAL_CACHE:
        return _PSEUDOCRITICAL_CACHE[key]
    t_crit = float(_CP_PropsSI('Tcrit', fluid))
    t_max = float(_CP_PropsSI('Tmax', fluid))
    lo = t_crit
    hi = min(2.0 * t_crit, t_max)

    def _cp(t: float) -> float:
        return float(_CP_PropsSI('C', 'T', t, 'P', pressure, fluid))

    # 1) Kaba ızgara: global maksimumun komşuluğunu bul (bimodal koruması).
    grid = np.linspace(lo, hi, 96)
    cp_grid = np.array([_cp(t) for t in grid])
    i_max = int(np.argmax(cp_grid))
    if i_max == 0 or i_max == len(grid) - 1:
        # İç maksimum yok — pseudo-kritik çizgi bu basınçta silinmiş.
        t_pc = float(grid[i_max])
        _PSEUDOCRITICAL_CACHE[key] = t_pc
        return t_pc
    a = float(grid[i_max - 1])
    b = float(grid[i_max + 1])

    # 2) Altın-oran incelmesi (~0.05 K hassasiyet), tek tepeli aralıkta.
    invphi = (math.sqrt(5.0) - 1.0) / 2.0
    c = b - invphi * (b - a)
    d = a + invphi * (b - a)
    fc, fd = _cp(c), _cp(d)
    while (b - a) > 0.05:
        if fc > fd:
            b, d, fd = d, c, fc
            c = b - invphi * (b - a)
            fc = _cp(c)
        else:
            a, c, fc = c, d, fd
            d = a + invphi * (b - a)
            fd = _cp(d)
    t_pc = 0.5 * (a + b)
    _PSEUDOCRITICAL_CACHE[key] = t_pc
    return t_pc


# ===========================================================================
# Ana sınıf
# ===========================================================================
class RegenCooling:
    """1D regenerative-cooling station-marching solver (analysis mode).

    The nozzle inner contour is sampled from the single shared sampler
    (``hrma.engines.nozzle_design.sample_nozzle_inner_contour``) and split into
    20-50 axial stations with the throat station always on the grid. At each
    station the gas-side Bartz coefficient and the coolant-side Dittus-Boelter
    coefficient are combined through the liner conduction resistance to give
    the local heat flux and the hot / cold wall temperatures. The coolant bulk
    temperature and pressure are marched station-to-station.

    Parameters
    ----------
    chamber_pressure : float
        Chamber (stagnation) pressure [Pa].
    chamber_temperature : float
        Chamber (stagnation) temperature [K].
    gamma : float
        Ratio of specific heats (frozen), 1.05 < gamma < 1.67.
    molecular_weight : float
        Combustion-gas molecular weight [g/mol] (default 24, typical hybrid).
    throat_diameter : float
        Nozzle throat diameter [m].
    exit_diameter, expansion_ratio : float, optional
        Nozzle exit diameter [m], or the area expansion ratio (>1) instead.
    coolant : str
        'water', 'rp1', 'methane' (aliases ch4/lch4) or 'hydrogen' (aliases
        h2/lh2). Methane/hydrogen REQUIRE CoolProp and use full
        (T, P)-dependent properties with an enthalpy-based march and the
        Jackson supercritical coolant-side correlation (module docstring).
    coolant_mdot : float
        Total coolant mass flow rate through all channels [kg/s].
    coolant_inlet_temp : float
        Coolant inlet (bulk) temperature [K].
    coolant_inlet_pressure : float
        Coolant inlet static pressure [Pa].
    n_channels : int
        Number of parallel cooling channels (>= 1).
    channel_width, channel_height : float
        Rectangular channel width and height [m] (constant along the length —
        analysis mode, no tapering).
    wall_thickness : float
        Inner-liner (hot wall) thickness [m].
    wall_material : str
        Liner material key (``hrma.data.materials_db``: copper, cucrzr,
        steel, inconel_718, ...). Sets k_w and the temperature limits.
    n_stations : int
        Number of axial stations, clamped to [20, 50].
    flow_direction : str
        'counterflow' (default, coolant enters at the exit) or 'coflow'
        (coolant enters at the chamber).
    wall_roughness : float
        Channel absolute surface roughness [m] (default 5e-6, machined metal;
        'approximate'). Only affects the turbulent friction factor.
    coolant_props_source : str
        'auto' (default: CoolProp for water if available, else table; table
        for RP-1), 'table' (force internal tables), or 'coolprop'. 'table'
        is INVALID for methane/hydrogen (no table exists).
    fin_effect : bool
        Apply the coolant-side extended-surface (channel-land fin) area model
        (``fin_area_ratio``; Huzel & Huang Ch. 4, Incropera Ch. 3.6). Applies
        ONLY to the methane/hydrogen path; the water/RP-1 legacy path always
        keeps coolant-side area = gas-side area (behaviour contract).
    motor_data : dict, optional
        Repo-style motor dictionary forwarded to the contour sampler and the
        gas-property resolver (chamber diameter, nozzle type, bell angles,
        transport-property overrides).
    """

    def __init__(self,
                 chamber_pressure: float,
                 chamber_temperature: float,
                 gamma: float = 1.2,
                 molecular_weight: float = 24.0,
                 throat_diameter: Optional[float] = None,
                 exit_diameter: Optional[float] = None,
                 expansion_ratio: Optional[float] = None,
                 coolant: str = 'water',
                 coolant_mdot: float = 1.0,
                 coolant_inlet_temp: float = 300.0,
                 coolant_inlet_pressure: float = 30.0e5,
                 n_channels: int = 64,
                 channel_width: float = 2.0e-3,
                 channel_height: float = 3.0e-3,
                 wall_thickness: float = 1.0e-3,
                 wall_material: str = 'copper',
                 n_stations: int = 40,
                 flow_direction: str = FLOW_COUNTERFLOW,
                 wall_roughness: float = 5.0e-6,
                 coolant_props_source: str = 'auto',
                 fin_effect: bool = True,
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

        coolant = str(coolant).lower().replace('-', '').replace('_', '')
        if coolant in ('rp1', 'kerosene', 'rp'):
            coolant = 'rp1'
        elif coolant in ('water', 'h2o'):
            coolant = 'water'
        elif coolant in ('methane', 'ch4', 'lch4'):
            coolant = 'methane'
        elif coolant in ('hydrogen', 'h2', 'lh2'):
            coolant = 'hydrogen'
        else:
            raise ValueError("coolant must be 'water', 'rp1', 'methane' or "
                             "'hydrogen'.")
        self.coolant = coolant

        # Metan/hidrojen: CoolProp ZORUNLU — dahili tablo yok, sabit değere
        # sessiz düşüş yok (uydurma-veri bekçisiyle uyumlu açık politika).
        if coolant in SUPERCRITICAL_COOLANT_FLUIDS:
            if coolant_props_source == 'table':
                raise ValueError(
                    f"coolant='{coolant}' has no internal property table — "
                    "CoolProp is mandatory (coolant_props_source must be "
                    "'auto' or 'coolprop'). Refusing to substitute constant "
                    "properties.")
            if not _HAS_COOLPROP:
                raise ValueError(
                    f"coolant='{coolant}' requires CoolProp for (T, P)-"
                    "dependent properties, but CoolProp is not installed.")

        if not (coolant_mdot > 0.0):
            raise ValueError("coolant_mdot must be positive [kg/s].")
        if not (coolant_inlet_temp > 0.0):
            raise ValueError("coolant_inlet_temp must be positive [K].")
        if not (coolant_inlet_pressure > 0.0):
            raise ValueError("coolant_inlet_pressure must be positive [Pa].")
        if int(n_channels) < 1:
            raise ValueError("n_channels must be a positive integer.")
        if not (channel_width > 0.0) or not (channel_height > 0.0):
            raise ValueError("channel_width and channel_height must be "
                             "positive [m].")
        if not (wall_thickness > 0.0):
            raise ValueError("wall_thickness must be positive [m].")
        if wall_roughness < 0.0:
            raise ValueError("wall_roughness must be non-negative [m].")
        if flow_direction not in (FLOW_COUNTERFLOW, FLOW_COFLOW):
            raise ValueError("flow_direction must be 'counterflow' or "
                             "'coflow'.")
        if coolant_props_source not in ('auto', 'table', 'coolprop'):
            raise ValueError("coolant_props_source must be 'auto', 'table' "
                             "or 'coolprop'.")

        # --- malzeme (merkezi DB — kopya döner) ---
        try:
            self.material = get_material(wall_material)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        self.wall_material = wall_material

        self.motor_data = dict(motor_data or {})

        # --- geometri: boğaz/çıkış çapı veya genişleme oranı ---
        if throat_diameter is None:
            throat_diameter = self.motor_data.get('throat_diameter')
        if throat_diameter is None or not (float(throat_diameter) > 0.0):
            raise ValueError("throat_diameter must be provided and positive [m].")
        throat_diameter = float(throat_diameter)

        if exit_diameter is None:
            if expansion_ratio is not None:
                if not (float(expansion_ratio) > 1.0):
                    raise ValueError("expansion_ratio must be > 1.")
                exit_diameter = throat_diameter * math.sqrt(float(expansion_ratio))
            else:
                exit_diameter = self.motor_data.get('exit_diameter')
        if exit_diameter is None or not (float(exit_diameter) > throat_diameter):
            raise ValueError("exit_diameter must exceed throat_diameter "
                             "(supersonic nozzle, expansion ratio > 1).")
        exit_diameter = float(exit_diameter)

        self.chamber_pressure = float(chamber_pressure)
        self.chamber_temperature = float(chamber_temperature)
        self.gamma = float(gamma)
        self.molecular_weight = float(molecular_weight)
        self.throat_diameter = throat_diameter
        self.exit_diameter = exit_diameter
        self.coolant_mdot = float(coolant_mdot)
        self.coolant_inlet_temp = float(coolant_inlet_temp)
        self.coolant_inlet_pressure = float(coolant_inlet_pressure)
        self.n_channels = int(n_channels)
        self.channel_width = float(channel_width)
        self.channel_height = float(channel_height)
        self.wall_thickness = float(wall_thickness)
        self.n_stations = int(min(max(int(n_stations), REGEN_N_STATIONS_MIN),
                                  REGEN_N_STATIONS_MAX))
        self.flow_direction = flow_direction
        self.wall_roughness = float(wall_roughness)
        self.coolant_props_source = coolant_props_source
        # Fin (kanal sırtı) genişletilmiş-yüzey modeli: YALNIZ metan/hidrojen
        # süperkritik yolunda uygulanır. Su/RP-1 yolu eski davranış
        # sözleşmesini (soğutucu alanı = gaz alanı) birebir korur.
        self.fin_effect = bool(fin_effect)

        # --- süperkritik-yetenekli soğutucu: EOS sınırları + giriş durumu ---
        self._cp_fluid = SUPERCRITICAL_COOLANT_FLUIDS.get(self.coolant)
        if self._cp_fluid is not None:
            self.coolant_pcrit = float(_CP_PropsSI('Pcrit', self._cp_fluid))
            self.coolant_tcrit = float(_CP_PropsSI('Tcrit', self._cp_fluid))
            self._fluid_tmin = float(_CP_PropsSI('Tmin', self._cp_fluid))
            self._fluid_tmax = float(_CP_PropsSI('Tmax', self._cp_fluid))
            self._fluid_pmax = float(_CP_PropsSI('pmax', self._cp_fluid))
            if not (self._fluid_tmin <= self.coolant_inlet_temp
                    <= self._fluid_tmax):
                raise ValueError(
                    f"coolant_inlet_temp {self.coolant_inlet_temp:.1f} K is "
                    f"outside the {self._cp_fluid} EOS range "
                    f"[{self._fluid_tmin:.1f}, {self._fluid_tmax:.1f}] K.")
            if self.coolant_inlet_pressure > self._fluid_pmax:
                raise ValueError(
                    f"coolant_inlet_pressure {self.coolant_inlet_pressure/1e5:.1f} "
                    f"bar exceeds the {self._cp_fluid} EOS limit "
                    f"{self._fluid_pmax/1e5:.0f} bar.")
            # Giriş durumunu hemen çöz — aralık dışıysa AÇIK hata (erken).
            self._coolant_properties(self.coolant_inlet_temp,
                                     self.coolant_inlet_pressure)
        else:
            self.coolant_pcrit = None
            self.coolant_tcrit = None
            self._fluid_tmin = None
            self._fluid_tmax = None
            self._fluid_pmax = None

        # Türetilmiş kanal büyüklükleri
        self.channel_area = self.channel_width * self.channel_height  # m^2
        self.hydraulic_diameter = hydraulic_diameter_rect(
            self.channel_width, self.channel_height)                  # m
        self.mdot_per_channel = self.coolant_mdot / self.n_channels   # kg/s

        # Isı transferi yardımcıları (Bartz + gaz özellikleri) — tek kaynak.
        self._hta = HeatTransferAnalyzer()

        # motor_data'yı Bartz için tutarlı boğaz/çıkış çapıyla besle.
        self._md_gas = dict(self.motor_data)
        self._md_gas['chamber_pressure'] = self.chamber_pressure / 1e5  # bar
        self._md_gas['chamber_temperature'] = self.chamber_temperature
        self._md_gas['gamma'] = self.gamma
        self._md_gas['molecular_weight'] = self.molecular_weight
        self._md_gas['throat_diameter'] = self.throat_diameter
        self._md_gas.setdefault('exit_diameter', self.exit_diameter)

    # ------------------------------------------------------------------
    @classmethod
    def from_motor_data(cls, motor_data: Dict, **kwargs) -> 'RegenCooling':
        """Build from a repo-style motor dictionary (chamber_pressure in bar)."""
        md = dict(motor_data or {})
        params = dict(
            chamber_pressure=float(md.get('chamber_pressure', 20.0)) * 1e5,
            chamber_temperature=float(md.get('chamber_temperature', 3000.0)),
            gamma=float(md.get('gamma', md.get('gamma_avg', 1.2))),
            molecular_weight=float(md.get('molecular_weight', 24.0)),
            throat_diameter=md.get('throat_diameter'),
            exit_diameter=md.get('exit_diameter'),
            expansion_ratio=md.get('expansion_ratio'),
            motor_data=md,
        )
        params.update(kwargs)
        return cls(**params)

    # ------------------------------------------------------------------
    # Soğutucu özellik çözümü (CoolProp veya tablo)
    # ------------------------------------------------------------------
    def _cp_call(self, output: str, name1: str, value1: float,
                 name2: str, value2: float) -> float:
        """CoolProp PropsSI wrapper for the supercritical coolant fluid.

        Raises an EXPLICIT ValueError on any failure or non-finite result —
        no silent fallback to constants (fabricated-value guard policy).
        """
        try:
            val = float(_CP_PropsSI(output, name1, value1, name2, value2,
                                    self._cp_fluid))
        except Exception as exc:
            raise ValueError(
                f"CoolProp evaluation failed for {self._cp_fluid} "
                f"({output} at {name1}={value1:.6g}, {name2}={value2:.6g}): "
                f"{exc}. Coolant state is outside the EOS range — the model "
                "does not substitute constant values.") from exc
        if not math.isfinite(val):
            raise ValueError(
                f"CoolProp returned a non-finite {output} for "
                f"{self._cp_fluid} at {name1}={value1:.6g}, "
                f"{name2}={value2:.6g}.")
        return val

    def _saturation_temperature(self, pressure: float) -> float:
        """T_sat [K] at ``pressure`` (valid only below the critical pressure)."""
        return self._cp_call('T', 'P', pressure, 'Q', 0.0)

    def _coolant_properties(self, temperature: float,
                            pressure: float) -> Dict[str, float]:
        """Local coolant transport properties at (T, P).

        Water may use CoolProp (single-phase liquid); RP-1 always uses the
        internal table (no single CoolProp fluid). Falls back to the table on
        any CoolProp failure (e.g. two-phase state) with a flag.

        Methane / hydrogen ALWAYS use CoolProp (density, cp, conductivity,
        viscosity AND mass enthalpy at the local (T, P)); any failure raises
        an explicit error — there is no table and no constant fallback.
        """
        if self.coolant in SUPERCRITICAL_COOLANT_FLUIDS:
            rho = self._cp_call('D', 'T', temperature, 'P', pressure)
            cp = self._cp_call('C', 'T', temperature, 'P', pressure)
            k = self._cp_call('L', 'T', temperature, 'P', pressure)
            mu = self._cp_call('V', 'T', temperature, 'P', pressure)
            h = self._cp_call('Hmass', 'T', temperature, 'P', pressure)
            if rho <= 0.0 or cp <= 0.0 or k <= 0.0 or mu <= 0.0:
                raise ValueError(
                    f"Non-physical CoolProp properties for {self._cp_fluid} "
                    f"at T={temperature:.1f} K, P={pressure/1e5:.1f} bar.")
            return {
                'density': rho, 'cp': cp, 'conductivity': k,
                'viscosity': mu, 'prandtl': cp * mu / k,
                'enthalpy': h, 'clamped': False, 'source': 'coolprop',
            }
        want_cp = (self.coolant_props_source == 'coolprop'
                   or (self.coolant_props_source == 'auto'))
        if self.coolant == 'water' and want_cp and _HAS_COOLPROP:
            try:  # pragma: no cover - ortam bağımlı
                rho = float(_CP_PropsSI('D', 'T', temperature, 'P', pressure, 'Water'))
                cp = float(_CP_PropsSI('C', 'T', temperature, 'P', pressure, 'Water'))
                k = float(_CP_PropsSI('L', 'T', temperature, 'P', pressure, 'Water'))
                mu = float(_CP_PropsSI('V', 'T', temperature, 'P', pressure, 'Water'))
                if rho > 0 and cp > 0 and k > 0 and mu > 0:
                    return {
                        'density': rho, 'cp': cp, 'conductivity': k,
                        'viscosity': mu, 'prandtl': cp * mu / k,
                        'clamped': False, 'source': 'coolprop',
                    }
            except Exception:
                pass  # tabloya düş
        props = (water_properties(temperature) if self.coolant == 'water'
                 else rp1_properties(temperature))
        props['source'] = 'table'
        return props

    # ------------------------------------------------------------------
    # Geometri: ortak kontur örnekleyiciden istasyon ızgarası
    # ------------------------------------------------------------------
    def _build_stations(self):
        """Sample the shared contour and build the x-ascending station grid.

        Returns ``x_mm``, ``r_mm`` (gas-side inner radius) and the throat index;
        the throat station is guaranteed on the grid (M=1 anchored exactly).
        """
        # Tembel import: engines paketi -> analysis zinciri modül-üstü importta
        # döngü riski taşır (aynı gerekçe analyze_axial_profile'de belgelidir).
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour

        md_geo = dict(self.motor_data)
        md_geo['throat_diameter'] = self.throat_diameter
        md_geo['exit_diameter'] = self.exit_diameter
        md_geo.setdefault('chamber_diameter', 1.5 * self.throat_diameter)

        pts, meta = sample_nozzle_inner_contour(md_geo)
        z_pts = np.array([p[0] for p in pts], dtype=float)  # mm
        r_pts = np.array([p[1] for p in pts], dtype=float)  # mm
        z_throat = float(meta['z_throat'])
        z_exit = float(meta['z_exit'])
        r_throat = float(meta['r_throat'])

        # Boğaz istasyonu KESİN dahil (analyze_axial_profile ile aynı ızgara).
        n = self.n_stations
        frac_conv = z_throat / z_exit if z_exit > 0 else 0.5
        n_conv = int(round(n * frac_conv))
        n_conv = min(max(n_conv, 2), n - 1)
        n_div = n - n_conv + 1  # boğaz paylaşılır
        x_conv = np.linspace(0.0, z_throat, n_conv)
        x_div = np.linspace(z_throat, z_exit, n_div)[1:]
        x_mm = np.concatenate([x_conv, x_div])
        throat_index = n_conv - 1

        r_mm = np.interp(x_mm, z_pts, r_pts)
        area_ratio = np.maximum((r_mm / r_throat) ** 2, 1.0)
        area_ratio[throat_index] = 1.0

        return {
            'x_mm': x_mm, 'r_mm': r_mm, 'area_ratio': area_ratio,
            'throat_index': throat_index, 'r_throat_mm': r_throat,
            'z_throat_mm': z_throat, 'z_exit_mm': z_exit,
            'nozzle_type': meta.get('noz_type'),
        }

    # ------------------------------------------------------------------
    # Bir istasyonda kuple gaz-cidar dengesi (sabit nokta iterasyonu)
    # ------------------------------------------------------------------
    def _station_wall_balance(self, taw: float, t_coolant: float, h_c: float,
                              throat_d: float, c_star: float, rc_over_dt: float,
                              gas: Dict, area_ratio_local: float, mach: float,
                              k_wall: float):
        """Solve the local (h_g, q, T_wall_hot, T_wall_cold) fixed point.

        ``h_g`` depends on the hot-wall temperature through the Bartz sigma
        correction; iterate until the wall temperature is self-consistent.
        Series circuit per unit gas-side area:
            q = (Taw - T_coolant) / (1/h_g + t_w/k_w + 1/h_c).
        """
        r_cond = self.wall_thickness / k_wall     # m^2*K/W
        r_cool = 1.0 / h_c                          # m^2*K/W
        allowable = self.material.get('allowable_temperature', 1000.0)
        t_wall_hot = max(min(allowable, 0.8 * taw), t_coolant)
        h_g = 0.0
        q = 0.0
        for _ in range(60):
            h_g = self._hta._bartz_coefficient(
                throat_d, self.chamber_pressure, c_star, gas,
                self.chamber_temperature, t_wall_hot, rc_over_dt,
                area_ratio_local=area_ratio_local, mach_local=mach)
            r_total = 1.0 / h_g + r_cond + r_cool
            q = (taw - t_coolant) / r_total
            new_hot = taw - q / h_g
            if abs(new_hot - t_wall_hot) < 1e-3:
                t_wall_hot = new_hot
                break
            t_wall_hot = new_hot
        t_wall_cold = t_coolant + q * r_cool
        return h_g, q, t_wall_hot, t_wall_cold

    # ------------------------------------------------------------------
    # Süperkritik istasyon dengesi (Jackson — cidar özellik oranlı)
    # ------------------------------------------------------------------
    def _station_wall_balance_sc(self, taw: float, t_bulk: float,
                                 p_bulk: float, bulk: Dict, reynolds: float,
                                 throat_d: float, c_star: float,
                                 rc_over_dt: float, gas: Dict,
                                 area_ratio_local: float, mach: float,
                                 k_wall: float, t_pc: float,
                                 r_local: float):
        """Coupled wall balance with the Jackson supercritical coolant Nu.

        Unlike the Dittus-Boelter path, the coolant-side coefficient depends
        on the COLD-wall temperature through the (rho_w/rho_b) and
        (cp_bar/cp_b) property ratios (Jackson & Hall 1979). The fixed point
        over (T_wall_hot, T_wall_cold) is solved with damped iteration:

            q = (Taw - T_bulk) / (1/h_g(T_hot) + t_w/k_w + 1/(h_c*A_r))
            T_hot  <- Taw   - q/h_g,    T_cold <- T_bulk + q/(h_c*A_r)

        where A_r is the coolant-side extended-surface (channel-land fin)
        area ratio (``fin_area_ratio``; = 1 when ``fin_effect`` is False).
        Wall-side properties are evaluated at (min(T_cold, T_max_EOS), P);
        clamping at the EOS limit is COUNTED and reported as an explicit
        warning (the wall-limit warnings fire independently).

        ``r_local`` is the local gas-side inner radius [m] (sets the channel
        pitch for the fin geometry).

        Returns (h_g, q, T_wall_hot, T_wall_cold, h_c, nu, a_ratio,
        converged, wall_props_clamped).
        """
        r_cond = self.wall_thickness / k_wall       # m^2*K/W
        allowable = self.material.get('allowable_temperature', 1000.0)
        t_wall_hot = max(min(allowable, 0.8 * taw), t_bulk)
        t_wall_cold = t_bulk + 30.0
        rho_b = bulk['density']
        cp_b = bulk['cp']
        h_b = bulk['enthalpy']
        k_b = bulk['conductivity']
        pr_b = bulk['prandtl']
        # Kanal adımı (soğutucu tarafı çevresi / kanal sayısı) — fin geometrisi
        pitch = (2.0 * math.pi * (r_local + self.wall_thickness)
                 / self.n_channels)
        land = pitch - self.channel_width
        damping = 0.6            # sabit nokta sönümü (cp_bar hassasiyeti için)
        tol = 1.0e-3             # K
        h_g = 0.0
        h_c = 0.0
        q = 0.0
        nu = 0.0
        a_ratio = 1.0
        converged = False
        wall_props_clamped = False
        for _ in range(100):
            # Cidar tarafı özellik değerlendirme sıcaklığı (EOS içinde tut).
            t_eval = min(max(t_wall_cold, self._fluid_tmin), self._fluid_tmax)
            if t_eval != t_wall_cold:
                wall_props_clamped = True
            rho_w = self._cp_call('D', 'T', t_eval, 'P', p_bulk)
            h_w = self._cp_call('Hmass', 'T', t_eval, 'P', p_bulk)
            if abs(t_eval - t_bulk) > 0.1:
                # cp_bar = (h_w - h_b)/(T_w - T_b): entegre ortalama özgül ısı
                cp_bar = (h_w - h_b) / (t_eval - t_bulk)
            else:
                cp_bar = cp_b
            if cp_bar <= 0.0:
                cp_bar = cp_b  # h(T) monoton — negatif çıkamaz; sayısal koruma
            n_exp = jackson_exponent_n(t_bulk, t_eval, t_pc)
            nu = jackson_nu(reynolds, pr_b, rho_w / rho_b,
                            cp_bar / cp_b, n_exp)
            h_c = nu * k_b / self.hydraulic_diameter
            if self.fin_effect:
                a_ratio = fin_area_ratio(self.channel_width,
                                         self.channel_height, pitch, land,
                                         h_c, k_wall)
            h_g = self._hta._bartz_coefficient(
                throat_d, self.chamber_pressure, c_star, gas,
                self.chamber_temperature, t_wall_hot, rc_over_dt,
                area_ratio_local=area_ratio_local, mach_local=mach)
            r_cool = 1.0 / (h_c * a_ratio)
            r_total = 1.0 / h_g + r_cond + r_cool
            q = (taw - t_bulk) / r_total
            new_hot = taw - q / h_g
            new_cold = t_bulk + q * r_cool
            if (abs(new_hot - t_wall_hot) < tol
                    and abs(new_cold - t_wall_cold) < tol):
                t_wall_hot, t_wall_cold = new_hot, new_cold
                converged = True
                break
            t_wall_hot += damping * (new_hot - t_wall_hot)
            t_wall_cold += damping * (new_cold - t_wall_cold)
        return (h_g, q, t_wall_hot, t_wall_cold, h_c, nu, a_ratio, converged,
                wall_props_clamped)

    # ------------------------------------------------------------------
    # Ana çözüm: istasyon marşı
    # ------------------------------------------------------------------
    def solve(self) -> Dict:
        """Run the 1D station march and return station arrays + summary.

        Returns a dict with per-station arrays (``x_mm``, ``T_wall_hot_K``,
        ``T_wall_cold_K``, ``T_coolant_K``, ``P_coolant_bar``, ``q_MW_m2``,
        ``velocity_m_s`` and diagnostic companions), a ``summary`` block
        (peak wall temperature, material-limit comparison, total pressure
        drop, coolant exit temperature, coking status, warnings) and a
        ``model_note`` describing assumptions and validity.
        """
        geo = self._build_stations()
        x_mm = geo['x_mm']
        r_mm = geo['r_mm']
        area_ratio = geo['area_ratio']
        throat_index = geo['throat_index']
        n = self.n_stations

        # Gaz özellikleri + boğaz koşulları (tek kaynak).
        mdot_total = self.motor_data.get('mdot_total', 1.0)
        gas = self._hta._get_gas_properties(self._md_gas, self.chamber_temperature)
        throat = self._hta._resolve_throat_conditions(
            self._md_gas, self.chamber_pressure, self.chamber_temperature,
            gas, mdot_total)
        throat_d = throat['throat_diameter']
        c_star = throat['c_star']
        rc_over_dt = throat['rc_over_dt']
        k_wall = self.material['thermal_conductivity']

        # Her istasyonda Mach + recovery sıcaklığı (soğutmadan bağımsız).
        mach = np.empty(n)
        taw = np.empty(n)
        for i in range(n):
            supersonic = i > throat_index
            m = self._hta._mach_from_area_ratio(area_ratio[i], self.gamma, supersonic)
            mach[i] = m
            taw[i] = self._hta._adiabatic_wall_temperature(
                self.chamber_temperature, gas, m)

        # Marş sırası: geometrik indeks listesi (soğutucu akış yönünde).
        if self.flow_direction == FLOW_COUNTERFLOW:
            order = list(range(n - 1, -1, -1))   # çıkış -> kamara
        else:
            order = list(range(n))               # kamara -> çıkış

        # Çıktı dizileri (geometrik indekse göre doldurulur).
        t_coolant = np.empty(n)
        p_coolant = np.empty(n)
        t_wall_hot = np.empty(n)
        t_wall_cold = np.empty(n)
        q_flux = np.empty(n)          # W/m^2
        velocity = np.empty(n)
        reynolds = np.empty(n)
        h_gas = np.empty(n)
        h_cool = np.empty(n)

        r_m = r_mm / 1000.0           # m
        x_m = x_mm / 1000.0           # m

        # Marş durumu
        t_c = self.coolant_inlet_temp
        p_c = self.coolant_inlet_pressure
        total_heat_W = 0.0
        enthalpy_rise = 0.0           # J/kg (cp*dT integrali / h marşı)
        min_re = np.inf

        # --- süperkritik (metan/hidrojen) marş durumu: entalpi tabanlı ---
        sc_mode = self.coolant in SUPERCRITICAL_COOLANT_FLUIDS
        h_bulk = 0.0
        h_inlet = 0.0
        coolant_h = np.full(n, np.nan)   # J/kg (yalnız sc modda dolar)
        fin_ratio = np.ones(n)           # A_eff/A_gas (sc modda hesaplanır)
        dp_friction_total = 0.0
        dp_accel_total = 0.0
        n_jackson = 0                    # Jackson kullanılan istasyon sayısı
        n_db_subcritical = 0             # kritik-altı Dittus-Boelter istasyonu
        wall_balance_unconverged = 0
        jackson_wall_clamped = 0
        # F057: tablo bandı dışına taşan (özellikleri donmuş) istasyon sayacı
        table_clamped_stations = 0
        table_clamp_t_min = math.inf
        table_clamp_t_max = -math.inf
        table_band: Optional[tuple] = None
        bulk_boiling_stations = 0
        near_boiling_stations = 0
        wall_boiling_stations = 0
        if sc_mode:
            h_inlet = self._coolant_properties(t_c, p_c)['enthalpy']
            h_bulk = h_inlet

        for step, idx in enumerate(order):
            # --- soğutucu tarafı katsayısı (yerel yığın özellikleriyle) ---
            props = self._coolant_properties(t_c, p_c)
            rho = props['density']
            cp = props['cp']
            k_c = props['conductivity']
            mu = props['viscosity']
            pr = props['prandtl']

            # F057: tablo yolunda banda klamplanan istasyonları kaydet.
            # Klamp, özellikleri banda DONDURUR (rho/mu/Pr sabit kalır) —
            # sessizce yapılırsa kullanıcı geçerlilik zarfı dışına çıktığını
            # göremez. Uyarı marş sonunda toplu üretilir.
            if props.get('clamped'):
                table_clamped_stations += 1
                table_clamp_t_min = min(table_clamp_t_min, t_c)
                table_clamp_t_max = max(table_clamp_t_max, t_c)
                table_band = (props['table_t_min_K'], props['table_t_max_K'])

            v = self.mdot_per_channel / (rho * self.channel_area)  # m/s
            re = rho * v * self.hydraulic_diameter / mu

            if sc_mode and p_c > self.coolant_pcrit:
                # --- süperkritik bölge: Jackson + kuple cidar dengesi ---
                t_pc_local = pseudocritical_temperature(self._cp_fluid, p_c)
                (h_g, q, tw_hot, tw_cold, h_c, nu, a_ratio, converged,
                 clamped) = self._station_wall_balance_sc(
                    taw[idx], t_c, p_c, props, re, throat_d, c_star,
                    rc_over_dt, gas, area_ratio_local=1.0 / area_ratio[idx],
                    mach=mach[idx], k_wall=k_wall, t_pc=t_pc_local,
                    r_local=r_m[idx])
                fin_ratio[idx] = a_ratio
                n_jackson += 1
                if not converged:
                    wall_balance_unconverged += 1
                if clamped:
                    jackson_wall_clamped += 1
            else:
                nu = dittus_boelter_nu(re, pr, heating=True)
                h_c = nu * k_c / self.hydraulic_diameter           # W/m^2/K

                h_c_eff = h_c
                if sc_mode and self.fin_effect:
                    # Fin alan oranı (h_c cidara bağlı değil -> kapalı form).
                    pitch = (2.0 * math.pi * (r_m[idx] + self.wall_thickness)
                             / self.n_channels)
                    a_ratio = fin_area_ratio(
                        self.channel_width, self.channel_height, pitch,
                        pitch - self.channel_width, h_c, k_wall)
                    fin_ratio[idx] = a_ratio
                    h_c_eff = h_c * a_ratio

                # --- kuple gaz-cidar dengesi ---
                h_g, q, tw_hot, tw_cold = self._station_wall_balance(
                    taw[idx], t_c, h_c_eff, throat_d, c_star, rc_over_dt, gas,
                    area_ratio_local=1.0 / area_ratio[idx], mach=mach[idx],
                    k_wall=k_wall)

                if sc_mode:
                    # Kritik-altı basınç: kaynama riski denetimi (yerel Tsat).
                    n_db_subcritical += 1
                    t_sat = self._saturation_temperature(p_c)
                    if t_c >= t_sat:
                        bulk_boiling_stations += 1
                    elif t_c > t_sat - BOILING_MARGIN_K:
                        near_boiling_stations += 1
                    if tw_cold > t_sat:
                        wall_boiling_stations += 1

            # istasyon çıktıları
            t_coolant[idx] = t_c
            p_coolant[idx] = p_c
            t_wall_hot[idx] = tw_hot
            t_wall_cold[idx] = tw_cold
            q_flux[idx] = q
            velocity[idx] = v
            reynolds[idx] = re
            h_gas[idx] = h_g
            h_cool[idx] = h_c
            min_re = min(min_re, re)
            if sc_mode:
                coolant_h[idx] = h_bulk

            # --- segment (idx -> sonraki marş istasyonu): ısı + basınç ---
            if step < len(order) - 1:
                nxt = order[step + 1]
                # eğik (slant) uzunluk ve ortalama gaz-tarafı yarıçapı
                ds = math.hypot(x_m[nxt] - x_m[idx], r_m[nxt] - r_m[idx])  # m
                r_mean = 0.5 * (r_m[idx] + r_m[nxt])
                dA = 2.0 * math.pi * r_mean * ds                          # m^2
                dQ = q * dA                                               # W
                total_heat_W += dQ
                # basınç düşümü (Darcy-Weisbach + Haaland), kanal eğik uzunluğu
                f = haaland_friction_factor(re, self.wall_roughness / self.hydraulic_diameter)
                dP = darcy_weisbach_dp(f, ds, self.hydraulic_diameter, rho, v)
                if sc_mode:
                    # ENTALPİ marşı: h2 = h1 + dQ/mdot, T = T(P, h).
                    # Pseudo-kritik cp tepesinde dT = dQ/(m*cp) formunun
                    # sıcaklık hatasını önler (modül üst dokümantasyonu).
                    dh = dQ / self.coolant_mdot
                    h_next = h_bulk + dh
                    p_tmp = p_c - dP
                    if p_tmp <= 0.0:
                        raise ValueError(
                            "Coolant pressure fell to zero during the march "
                            "(friction) — channel geometry/mdot infeasible.")
                    # İvmelenme (momentum) terimi: yoğunluk değişimi.
                    rho_next = self._cp_call('D', 'P', p_tmp, 'Hmass', h_next)
                    g_flux = self.mdot_per_channel / self.channel_area
                    dP_acc = acceleration_dp(g_flux, rho, rho_next)
                    p_next = p_tmp - dP_acc
                    if p_next <= 0.0:
                        raise ValueError(
                            "Coolant pressure fell to zero during the march "
                            "(acceleration) — channel geometry/mdot "
                            "infeasible.")
                    t_next = self._cp_call('T', 'P', p_next, 'Hmass', h_next)
                    dp_friction_total += dP
                    dp_accel_total += dP_acc
                    enthalpy_rise += dh
                    t_c, p_c, h_bulk = t_next, p_next, h_next
                else:
                    # soğutucu sıcaklık artışı (yerel cp ile) — su/RP-1
                    # davranışı BİREBİR korunur (regresyon sözleşmesi).
                    dT = dQ / (self.coolant_mdot * cp)
                    enthalpy_rise += cp * dT
                    dp_friction_total += dP
                    # marş: bir sonraki istasyona taşı
                    t_c = t_c + dT
                    p_c = p_c - dP

        # --- özet ---
        t_out = t_c                     # marş sonundaki soğutucu sıcaklığı
        t_in = self.coolant_inlet_temp
        dT_total = t_out - t_in
        cp_mean = enthalpy_rise / dT_total if abs(dT_total) > 1e-12 else 0.0
        total_dP = self.coolant_inlet_pressure - p_c
        p_out = p_c

        max_wall_hot = float(np.max(t_wall_hot))
        max_wall_hot_idx = int(np.argmax(t_wall_hot))
        max_wall_cold = float(np.max(t_wall_cold))
        allowable = float(self.material.get('allowable_temperature', 1000.0))
        max_service = float(self.material.get('max_service_temperature', allowable))
        melting = float(self.material.get('melting_point', max_service))

        warnings_list: List[str] = []

        # malzeme limiti kıyası
        if max_wall_hot > melting:
            warnings_list.append(
                f"CRITICAL: peak hot-wall temperature {max_wall_hot:.0f} K "
                f"exceeds {self.material.get('name', self.wall_material)} melting "
                f"point {melting:.0f} K — liner failure.")
        elif max_wall_hot > max_service:
            warnings_list.append(
                f"UNSAFE: peak hot-wall temperature {max_wall_hot:.0f} K exceeds "
                f"{self.material.get('name', self.wall_material)} service limit "
                f"{max_service:.0f} K.")
        elif max_wall_hot > allowable:
            warnings_list.append(
                f"WARNING: peak hot-wall temperature {max_wall_hot:.0f} K exceeds "
                f"{self.material.get('name', self.wall_material)} allowable "
                f"{allowable:.0f} K — strength margin reduced.")

        # koklaşma (yalnız RP-1): yakıt tarafı cidar sıcaklığı
        coking = False
        if self.coolant == 'rp1' and max_wall_cold > RP1_COKING_TEMP_K:
            coking = True
            warnings_list.append(
                f"COKING: RP-1 coolant-side wall temperature reaches "
                f"{max_wall_cold:.0f} K, above the ~{RP1_COKING_TEMP_K:.0f} K "
                f"coking threshold (Huzel & Huang Ch. 4) — carbon deposition "
                f"and channel fouling likely.")

        # DÜZELTME (v2.6.2, fizik denetimi F057): soğutucu özellik TABLOSUNUN
        # geçerlilik zarfı dışına taşan istasyonlar artık bildiriliyor.
        # Önceki davranışta _interp_table'ın 'clamped' bayrağı üretiliyor ama
        # hiç okunmuyordu; RP-1 tablosu 500 K'de, su tablosu 400 K'de bittiği
        # için tipik bir RP-1 devresinde 500 K üstü her istasyon sessizce
        # DONMUŞ özellik kullanıyordu. Ölçüm (su, 459 K / 80 bar, CoolProp
        # referanslı): klamplı tablo mu=2.17e-4 verir (gerçek 1.47e-4, %48
        # yüksek), Pr=1.342 (gerçek 0.960); sabit mdot'ta h_c oranı 0.856 —
        # yani h_c %14 EKSİK çıkar. RP-1 için referans veri olmadığından
        # sapma ölçülemez, bu yüzden uyarı sayısal düzeltme değil zarf
        # bildirimi yapar. Kaynak: Incropera & DeWitt 6th ed. Table A.6 (su,
        # 280-400 K bandı); RP-1 tablosu 'approximate' mühendislik derlemesi.
        if table_clamped_stations > 0 and table_band is not None:
            warnings_list.append(
                f"PROPERTY RANGE: {self.coolant} bulk temperature leaves the "
                f"internal property table band "
                f"({table_band[0]:.0f}-{table_band[1]:.0f} K) at "
                f"{table_clamped_stations} station(s) "
                f"(T_bulk {table_clamp_t_min:.0f}-{table_clamp_t_max:.0f} K); "
                f"properties there are FROZEN at the nearest band edge — "
                f"transport properties and the coolant-side coefficient are "
                f"an extrapolation outside the source validity envelope.")

        # akış rejimi uyarısı (Dittus-Boelter türbülan geçerliliği)
        if min_re < RE_TURBULENT_FLOOR:
            warnings_list.append(
                f"NOTE: minimum channel Reynolds number {min_re:.0f} is below "
                f"the Dittus-Boelter turbulent floor (~1e4); the coolant-side "
                f"coefficient there is an extrapolation.")

        # kanal yerleşim uygunluğu (kabaca): boğazda çevreye sığıyor mu?
        circ_throat = 2.0 * math.pi * (geo['r_throat_mm'] / 1000.0
                                       + self.wall_thickness)
        if self.n_channels * self.channel_width > circ_throat:
            warnings_list.append(
                f"GEOMETRY: {self.n_channels} channels of width "
                f"{self.channel_width * 1e3:.2f} mm exceed the throat "
                f"circumference ({circ_throat * 1e3:.1f} mm) — channels do not "
                f"physically fit; reduce count/width.")

        # su kaynaması (kaba): yerel P'de doymuş sıcaklığın üstüne çıkış
        if self.coolant == 'water' and _HAS_COOLPROP and \
                self.coolant_props_source in ('auto', 'coolprop'):
            try:  # pragma: no cover - ortam bağımlı
                t_sat = float(_CP_PropsSI('T', 'P', max(p_out, 1e3), 'Q', 0, 'Water'))
                if t_out > t_sat:
                    warnings_list.append(
                        f"BOILING: water exit temperature {t_out:.0f} K exceeds "
                        f"the saturation temperature {t_sat:.0f} K at the outlet "
                        f"pressure — single-phase assumption violated.")
            except Exception:
                pass

        # --- süperkritik soğutucu (metan/hidrojen) sınır denetimleri ---
        t_pc_inlet = None
        if sc_mode:
            fluid_label = self._cp_fluid
            if self.coolant_inlet_pressure <= self.coolant_pcrit:
                warnings_list.append(
                    f"SUBCRITICAL PRESSURE: {fluid_label} inlet pressure "
                    f"{self.coolant_inlet_pressure/1e5:.1f} bar is below the "
                    f"critical pressure {self.coolant_pcrit/1e5:.1f} bar — "
                    f"boiling is possible; the model stays single phase and "
                    f"only FLAGS the risk (no two-phase model).")
            else:
                t_pc_inlet = pseudocritical_temperature(
                    self._cp_fluid, self.coolant_inlet_pressure)
                t_cool_min = float(np.min(t_coolant))
                t_cool_max = float(np.max(t_coolant))
                if t_cool_min < t_pc_inlet < t_cool_max:
                    warnings_list.append(
                        f"NOTE: coolant bulk temperature crosses the "
                        f"pseudo-critical temperature "
                        f"({t_pc_inlet:.0f} K at inlet pressure) along the "
                        f"channel — strong property variation; the enthalpy "
                        f"march and Jackson property-ratio corrections "
                        f"account for it to first order.")
            if bulk_boiling_stations > 0:
                warnings_list.append(
                    f"BOILING: coolant bulk temperature reaches/exceeds the "
                    f"local saturation temperature at "
                    f"{bulk_boiling_stations} station(s) (subcritical "
                    f"pressure) — single-phase assumption violated; results "
                    f"there are not valid.")
            elif near_boiling_stations > 0:
                warnings_list.append(
                    f"BOILING RISK: coolant bulk temperature is within "
                    f"{BOILING_MARGIN_K:.0f} K (screening margin) of the "
                    f"local saturation temperature at "
                    f"{near_boiling_stations} station(s).")
            if wall_boiling_stations > 0:
                warnings_list.append(
                    f"NUCLEATE BOILING RISK: coolant-side wall temperature "
                    f"exceeds the local saturation temperature at "
                    f"{wall_boiling_stations} station(s) (subcritical "
                    f"pressure) — wall boiling not modelled.")
            if wall_balance_unconverged > 0:
                warnings_list.append(
                    f"CONVERGENCE: the coupled wall balance did not converge "
                    f"to 1e-3 K at {wall_balance_unconverged} station(s) — "
                    f"wall temperatures there carry iteration residual.")
            if jackson_wall_clamped > 0:
                warnings_list.append(
                    f"NOTE: Jackson wall-side property ratios evaluated at "
                    f"the {fluid_label} EOS temperature limit "
                    f"({self._fluid_tmax:.0f} K) at {jackson_wall_clamped} "
                    f"station(s) — the coolant-side coefficient there is an "
                    f"extrapolation (wall-limit warnings apply "
                    f"independently).")

        if sc_mode:
            if n_jackson > 0 and n_db_subcritical > 0:
                coolant_correlation = 'jackson+dittus_boelter(subcritical)'
            elif n_jackson > 0:
                coolant_correlation = 'jackson'
            else:
                coolant_correlation = 'dittus_boelter(subcritical)'
        else:
            coolant_correlation = 'dittus_boelter'

        summary = {
            'coolant': self.coolant,
            'wall_material': self.wall_material,
            'wall_material_name': self.material.get('name', self.wall_material),
            'coolant_inlet_temp_K': t_in,
            'coolant_exit_temp_K': t_out,
            'coolant_dT_K': dT_total,
            'coolant_cp_mean_J_kgK': cp_mean,
            'total_heat_W': total_heat_W,
            'total_heat_kW': total_heat_W / 1e3,
            'total_pressure_drop_bar': total_dP / 1e5,
            'coolant_exit_pressure_bar': p_out / 1e5,
            'max_wall_hot_K': max_wall_hot,
            'max_wall_hot_x_mm': float(x_mm[max_wall_hot_idx]),
            'max_wall_cold_K': max_wall_cold,
            'peak_heat_flux_MW_m2': float(np.max(q_flux)) / 1e6,
            'max_coolant_velocity_m_s': float(np.max(velocity)),
            'min_reynolds': float(min_re),
            'material_allowable_temp_K': allowable,
            'material_service_limit_K': max_service,
            'material_melting_K': melting,
            'wall_temp_margin_K': allowable - max_wall_hot,
            'coking': coking,
            'coking_threshold_K': RP1_COKING_TEMP_K if self.coolant == 'rp1' else None,
            'flow_direction': self.flow_direction,
            'coolant_correlation': coolant_correlation,
            'pressure_drop_friction_bar': dp_friction_total / 1e5,
            'pressure_drop_acceleration_bar': dp_accel_total / 1e5,
            'coolant_critical_pressure_bar': (
                self.coolant_pcrit / 1e5 if sc_mode else None),
            'coolant_critical_temperature_K': (
                self.coolant_tcrit if sc_mode else None),
            'coolant_pseudocritical_T_K': t_pc_inlet,
            'coolant_inlet_enthalpy_J_kg': h_inlet if sc_mode else None,
            'coolant_exit_enthalpy_J_kg': h_bulk if sc_mode else None,
            'supercritical_pressure': (
                bool(self.coolant_inlet_pressure > self.coolant_pcrit)
                if sc_mode else None),
            'fin_effect': self.fin_effect if sc_mode else None,
            'fin_area_ratio_max': (float(np.max(fin_ratio))
                                   if sc_mode else None),
            # F057: tablo geçerlilik zarfı denetimi (panel/rapor görünürlüğü)
            'property_table_clamped_stations': table_clamped_stations,
            'property_table_band_K': (list(table_band) if table_band is not None
                                      else None),
            'warnings': warnings_list,
        }

        if sc_mode:
            model_note = (
                "1D regenerative-cooling station march (analysis mode), "
                "supercritical-coolant path. Gas side: Bartz correlation "
                "(Sutton & Biblarz 9th ed. Eq. 8-22) driven by the "
                "adiabatic-wall temperature. Coolant side: Jackson "
                "supercritical correlation Nu=0.0183 Re^0.82 Pr^0.5 "
                "(rho_w/rho_b)^0.3 (cp_bar/cp_b)^n (Jackson & Hall 1979; "
                "Jackson 2013, Nucl. Eng. Des. 264) above the critical "
                "pressure, Dittus-Boelter (Incropera Eq. 8.60) below it with "
                "explicit boiling-risk flags. Coolant properties: CoolProp "
                f"(T,P)-dependent for {self._cp_fluid} (Bell et al. 2014); "
                "no internal table, out-of-range states raise. Coolant march "
                "is ENTHALPY based (h2=h1+dQ/mdot, T=T(P,h)) — exact through "
                "the pseudo-critical cp peak. Wall: thin flat-plate radial "
                "conduction; coolant-side area uses the channel-land "
                "extended-surface (fin) model when fin_effect=True "
                "(eta=tanh(mL)/mL, Incropera Ch. 3.6; lands-as-fins per "
                "Huzel & Huang Ch. 4), else area = gas-side area; the "
                "coupled gas/wall/coolant balance is solved per station "
                "(damped fixed point). Pressure drop: Darcy-Weisbach with the "
                "Haaland friction factor PLUS the acceleration term "
                "G^2*d(1/rho) (Collier & Thome 3rd ed. Ch. 2). Two-phase "
                "boiling is NOT modelled (flagged only). Channel dimensions "
                "are user inputs (no auto-sizing)."
            )
        else:
            model_note = (
                "1D regenerative-cooling station march (analysis mode). Gas side: "
                "Bartz correlation (Sutton & Biblarz 9th ed. Eq. 8-22) driven by the "
                "adiabatic-wall temperature. Coolant side: Dittus-Boelter "
                "Nu=0.023 Re^0.8 Pr^0.4 (Incropera Eq. 8.60; valid Re>=1e4, "
                "0.6<=Pr<=160). Wall: thin flat-plate radial conduction, coolant-side "
                "area = gas-side area (fin efficiency ~1, 'approximate'). Pressure "
                "drop: Darcy-Weisbach with the Haaland friction factor. RP-1 "
                "properties are approximate engineering values; coking threshold "
                f"{RP1_COKING_TEMP_K:.0f} K (Huzel & Huang Ch. 4). Single-phase "
                "coolant assumed; no boiling / supercritical model. Channel "
                "dimensions are user inputs (no auto-sizing)."
            )

        result = {
            # --- istenen çekirdek istasyon dizileri (x artan sırada) ---
            'x_mm': x_mm.tolist(),
            'T_wall_hot_K': t_wall_hot.tolist(),
            'T_wall_cold_K': t_wall_cold.tolist(),
            'T_coolant_K': t_coolant.tolist(),
            'P_coolant_bar': (p_coolant / 1e5).tolist(),
            'q_MW_m2': (q_flux / 1e6).tolist(),
            'velocity_m_s': velocity.tolist(),
            # --- ek teşhis dizileri ---
            'r_mm': r_mm.tolist(),          # gaz-tarafı iç yarıçap (mm)
            'reynolds': reynolds.tolist(),
            'h_gas_W_m2K': h_gas.tolist(),
            'h_coolant_W_m2K': h_cool.tolist(),
            'area_ratio': area_ratio.tolist(),
            'mach': mach.tolist(),
            'T_recovery_K': taw.tolist(),
            'throat_index': throat_index,
            'x_throat_mm': geo['z_throat_mm'],
            'x_exit_mm': geo['z_exit_mm'],
            'nozzle_type': geo['nozzle_type'],
            'n_stations': n,
            'hydraulic_diameter_mm': self.hydraulic_diameter * 1e3,
            'channel_area_mm2': self.channel_area * 1e6,
            'mdot_per_channel_kg_s': self.mdot_per_channel,
            'summary': summary,
            'model_note': model_note,
        }
        if sc_mode:
            # İstasyon yığın entalpisi [kJ/kg] ve fin alan oranı — yalnız
            # metan/hidrojen yolunda (su/RP-1 çıktı sözleşmesi değişmez;
            # JSON'a NaN sızdırmayız).
            result['coolant_enthalpy_kJ_kg'] = (coolant_h / 1e3).tolist()
            result['fin_area_ratio'] = fin_ratio.tolist()
        return result
