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

N_STATIONS_MIN = 20
N_STATIONS_MAX = 50

FLOW_COUNTERFLOW = 'counterflow'  # soğutucu çıkış -> boğaz -> kamara (varsayılan)
FLOW_COFLOW = 'coflow'            # soğutucu kamara -> boğaz -> çıkış

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
        'water' or 'rp1'.
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
        for RP-1), 'table' (force internal tables), or 'coolprop'.
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
        else:
            raise ValueError("coolant must be 'water' or 'rp1'.")
        self.coolant = coolant

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
        self.n_stations = int(min(max(int(n_stations), N_STATIONS_MIN),
                                  N_STATIONS_MAX))
        self.flow_direction = flow_direction
        self.wall_roughness = float(wall_roughness)
        self.coolant_props_source = coolant_props_source

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
    def _coolant_properties(self, temperature: float,
                            pressure: float) -> Dict[str, float]:
        """Local coolant transport properties at (T, P).

        Water may use CoolProp (single-phase liquid); RP-1 always uses the
        internal table (no single CoolProp fluid). Falls back to the table on
        any CoolProp failure (e.g. two-phase state) with a flag.
        """
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
        enthalpy_rise = 0.0           # J/kg (cp*dT integrali)
        min_re = np.inf

        for step, idx in enumerate(order):
            # --- soğutucu tarafı katsayısı (yerel yığın özellikleriyle) ---
            props = self._coolant_properties(t_c, p_c)
            rho = props['density']
            cp = props['cp']
            k_c = props['conductivity']
            mu = props['viscosity']
            pr = props['prandtl']

            v = self.mdot_per_channel / (rho * self.channel_area)  # m/s
            re = rho * v * self.hydraulic_diameter / mu
            nu = dittus_boelter_nu(re, pr, heating=True)
            h_c = nu * k_c / self.hydraulic_diameter               # W/m^2/K

            # --- kuple gaz-cidar dengesi ---
            h_g, q, tw_hot, tw_cold = self._station_wall_balance(
                taw[idx], t_c, h_c, throat_d, c_star, rc_over_dt, gas,
                area_ratio_local=1.0 / area_ratio[idx], mach=mach[idx],
                k_wall=k_wall)

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

            # --- segment (idx -> sonraki marş istasyonu): ısı + basınç ---
            if step < len(order) - 1:
                nxt = order[step + 1]
                # eğik (slant) uzunluk ve ortalama gaz-tarafı yarıçapı
                ds = math.hypot(x_m[nxt] - x_m[idx], r_m[nxt] - r_m[idx])  # m
                r_mean = 0.5 * (r_m[idx] + r_m[nxt])
                dA = 2.0 * math.pi * r_mean * ds                          # m^2
                dQ = q * dA                                               # W
                # soğutucu sıcaklık artışı (yerel cp ile)
                dT = dQ / (self.coolant_mdot * cp)
                total_heat_W += dQ
                enthalpy_rise += cp * dT
                # basınç düşümü (Darcy-Weisbach + Haaland), kanal eğik uzunluğu
                f = haaland_friction_factor(re, self.wall_roughness / self.hydraulic_diameter)
                dP = darcy_weisbach_dp(f, ds, self.hydraulic_diameter, rho, v)
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
            'warnings': warnings_list,
        }

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

        return {
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
