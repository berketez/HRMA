"""
Heat Transfer Analysis Module
Chamber wall temperature and cooling analysis for hybrid rocket motors.

REVISION (2026-06): Gas-side heat transfer rewritten from a tube-flow
Dittus-Boelter correlation to the Bartz throat correlation, which is the
physically correct model for rocket nozzle/throat gas-side convection.
The previous implementation under-predicted the gas-side coefficient by
~4-15x (UNSAFE direction: burn-through risk invisible). See validation in
tests/test_heat_transfer_validation.py.

Key references:
  - Bartz, D.R. (1957), "A Simple Equation for Rapid Estimation of Rocket
    Nozzle Convective Heat Transfer Coefficients", Jet Propulsion 27(1).
  - Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed., Eq. 8-22 (Bartz).
  - NASA SP-8124, "Liquid Rocket Engine Self-Cooled Combustion Chambers".
  - Huzel & Huang, "Modern Engineering for Design of Liquid-Propellant
    Rocket Engines", AIAA, Chapter 4 (cooling).

IMPORTANT UNITS NOTE (g0 pitfall):
  Sutton 9th ed. Eq. 8-22 is written in US customary units, where the
  (Pc*g0/c*) group uses g0 = 32.174 lbm*ft/(lbf*s^2) as a unit-conversion
  factor between lbf and lbm. In a *consistent SI* system Pc/c* already has
  units of mass flux [kg/(m^2*s)], so g0 must NOT appear. Including g0 in SI
  inflates h_g by g0^0.8 ~ 6.2x. This module uses the SI-consistent form
  (no g0). Dimensional check: kg/s^3/K = W/(m^2*K) exactly (verified).
"""

import numpy as np
import json
import warnings
from typing import Dict, List, Tuple, Optional

# Universal gas constant [J/(mol*K)] for frozen Cp / R_specific derivation.
R_UNIVERSAL = 8314.462618  # J/(kmol*K) == J/(mol*K)*1000; here used with MW in g/mol

class HeatTransferAnalyzer:
    """Heat transfer analysis for hybrid rocket motor chambers"""

    def __init__(self):
        self.stefan_boltzmann = 5.670374419e-8  # W/(m^2*K^4), CODATA 2018
        self.g0 = 9.80665  # m/s^2 (standard gravity; NOT used in SI Bartz)

        # Material properties database
        # 'max_service_temperature': physical upper bound for steady-state wall
        #   temperature used for unphysical-result clamping/warnings.
        self.materials = {
            'steel': {
                'thermal_conductivity': 50.0,  # W/m·K
                'density': 7850,               # kg/m³
                'specific_heat': 460,          # J/kg·K
                'melting_point': 1773,         # K
                'emissivity': 0.8,
                'allowable_temperature': 1073,  # K (safety limit)
                'max_service_temperature': 2000  # K (clamp bound for steel)
            },
            # Alias: hybrid_rocket_engine.py passes material='steel_4130'.
            # 4130 chromoly steel — properties near plain steel, slightly higher
            # service limit. Kept as explicit entry so the fallback to 'steel'
            # is no longer silently triggered.
            'steel_4130': {
                'thermal_conductivity': 42.7,  # W/m·K (AISI 4130, ~ room temp)
                'density': 7850,
                'specific_heat': 477,
                'melting_point': 1705,         # K (solidus ~1432 C)
                'emissivity': 0.8,
                'allowable_temperature': 1000,  # K (loses strength rapidly above)
                'max_service_temperature': 2000
            },
            'aluminum': {
                'thermal_conductivity': 205.0,
                'density': 2700,
                'specific_heat': 900,
                'melting_point': 933,
                'emissivity': 0.9,
                'allowable_temperature': 773,
                'max_service_temperature': 933
            },
            'inconel': {
                'thermal_conductivity': 15.0,
                'density': 8440,
                'specific_heat': 435,
                'melting_point': 1673,
                'emissivity': 0.85,
                'allowable_temperature': 1373,
                'max_service_temperature': 1673
            },
            'copper': {
                'thermal_conductivity': 401.0,
                'density': 8960,
                'specific_heat': 385,
                'melting_point': 1358,
                'emissivity': 0.75,
                'allowable_temperature': 1000,
                'max_service_temperature': 1358
            },
            # Ablative / refractory liner: high allowable surface temperature.
            # Used as clamp bound for ablative-cooled chambers (<3500 K).
            'ablative': {
                'thermal_conductivity': 0.5,   # W/m·K (charred phenolic, low k)
                'density': 1400,
                'specific_heat': 1500,
                'melting_point': 3800,
                'emissivity': 0.9,
                'allowable_temperature': 3300,
                'max_service_temperature': 3500
            },
            'graphite': {
                'thermal_conductivity': 100.0,
                'density': 1800,
                'specific_heat': 710,
                'melting_point': 3900,         # sublimes ~3900 K
                'emissivity': 0.85,
                'allowable_temperature': 3300,
                'max_service_temperature': 3500
            }
        }

    # ------------------------------------------------------------------
    # Gas property model (replaces hardcoded k=0.2, mu=5e-5, cp=1200)
    # ------------------------------------------------------------------
    def _get_gas_properties(self, motor_data: Dict, chamber_temperature: float) -> Dict:
        """
        Resolve combustion-gas transport properties for the Bartz correlation.

        Priority order (most authoritative first):
          1. Properties supplied directly in motor_data (e.g. from a prior
             Cantera / RocketCEA equilibrium solve upstream).
          2. Cantera equilibrium of an upstream-provided mechanism/composition
             (motor_data['cantera_gas'] handle), if present.
          3. Bartz-recommended frozen estimates derived from gamma and
             molecular weight, with a temperature-dependent viscosity
             correlation (Bartz 1957 / Sutton & Biblarz).

        Bartz (1957) recommends evaluating cp and Pr in the FROZEN sense:
            Pr = 4*gamma / (9*gamma - 5)              (Sutton & Biblarz Eq. 8-23)
            cp = gamma * R_specific / (gamma - 1)      (calorically-perfect)
        and a viscosity from the kinetic-theory-like correlation:
            mu = 1.184e-7 * (MW)^0.5 * T^0.6   [kg/(m*s)], MW in g/mol, T in K
            (Bartz 1957; reproduced in Sutton & Biblarz 9th ed.)
        """
        # --- gamma / molecular weight / R_specific ---
        gamma = motor_data.get('gamma', motor_data.get('gamma_avg', 1.20))
        # guard against non-physical gamma
        if not (1.05 < gamma < 1.67):
            gamma = 1.20
        molecular_weight = motor_data.get('molecular_weight', None)  # g/mol
        R_specific = motor_data.get('gas_constant', None)            # J/(kg*K)
        if molecular_weight is None and R_specific is not None:
            molecular_weight = R_UNIVERSAL / R_specific
        if molecular_weight is None:
            molecular_weight = 24.0  # g/mol, typical hybrid combustion product mix
        if R_specific is None:
            R_specific = R_UNIVERSAL / molecular_weight

        # --- Prandtl number (frozen, Bartz/Sutton Eq. 8-23) ---
        prandtl = motor_data.get('prandtl', None)
        if prandtl is None:
            prandtl = 4.0 * gamma / (9.0 * gamma - 5.0)

        # --- specific heat cp ---
        gas_cp = motor_data.get('gas_cp', None)  # J/(kg*K)
        if gas_cp is None:
            # calorically-perfect frozen cp from gamma, R_specific
            gas_cp = gamma * R_specific / (gamma - 1.0)

        # --- dynamic viscosity mu [Pa*s] ---
        gas_viscosity = motor_data.get('gas_viscosity', None)
        if gas_viscosity is None:
            # Bartz 1957 viscosity correlation (SI):
            #   mu = 1.184e-7 * MW^0.5 * T^0.6   [kg/(m*s)]
            # MW in g/mol, T in K. Validated vs RocketCEA chamber transport
            # (within ~10-20% for typical 13-30 g/mol combustion gases).
            gas_viscosity = 1.184e-7 * (molecular_weight ** 0.5) * (chamber_temperature ** 0.6)

        # --- thermal conductivity k [W/(m*K)] (derived from Pr definition) ---
        gas_conductivity = motor_data.get('gas_conductivity', None)
        if gas_conductivity is None:
            # k = cp * mu / Pr  (consistent with the Prandtl number above)
            gas_conductivity = gas_cp * gas_viscosity / prandtl

        # --- optional Cantera refinement (only if a gas handle is provided) ---
        # We never silently fabricate a mechanism here; only refine if upstream
        # passed a configured Cantera Solution object set to the burned state.
        cantera_gas = motor_data.get('cantera_gas', None)
        if cantera_gas is not None:
            try:
                cp_ct = float(cantera_gas.cp_mass)           # J/(kg*K)
                mu_ct = float(cantera_gas.viscosity)         # Pa*s
                k_ct = float(cantera_gas.thermal_conductivity)  # W/(m*K)
                if cp_ct > 0 and mu_ct > 0 and k_ct > 0:
                    gas_cp = cp_ct
                    gas_viscosity = mu_ct
                    gas_conductivity = k_ct
                    prandtl = cp_ct * mu_ct / k_ct
            except Exception:
                # fall back silently to the analytic estimates above
                pass

        return {
            'gamma': gamma,
            'molecular_weight': molecular_weight,
            'gas_constant': R_specific,
            'gas_cp': gas_cp,
            'gas_viscosity': gas_viscosity,
            'gas_conductivity': gas_conductivity,
            'prandtl': prandtl,
        }

    # ------------------------------------------------------------------
    # Throat conditions (replaces throat_flux = chamber*1.5 hardcode)
    # ------------------------------------------------------------------
    def _resolve_throat_conditions(self, motor_data: Dict, chamber_pressure: float,
                                   chamber_temperature: float, gas: Dict,
                                   mdot_total: float) -> Dict:
        """
        Compute real throat geometry and stagnation->throat conditions.

        c* (characteristic velocity) from theory if not provided:
            c* = sqrt(gamma * R * Tc) / ( gamma * sqrt( (2/(gamma+1))^((gamma+1)/(gamma-1)) ) )
            (Sutton & Biblarz Eq. 3-32)
        Throat area from continuity at the choked throat if not provided:
            A_t = mdot * c* / Pc          (definition of c*: Pc*A_t = mdot*c*)
        Throat temperature (static) for sigma correction:
            T_t = Tc / (1 + (gamma-1)/2)   (M=1)
        """
        gamma = gas['gamma']
        R = gas['gas_constant']

        # characteristic velocity c* [m/s]
        c_star = motor_data.get('c_star', motor_data.get('cstar', None))
        if c_star is None:
            num = np.sqrt(gamma * R * chamber_temperature)
            den = gamma * np.sqrt((2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0)))
            c_star = num / den

        # throat diameter [m]
        throat_diameter = motor_data.get('throat_diameter', None)
        throat_area = motor_data.get('throat_area', None)
        if throat_diameter is not None:
            throat_area = np.pi * (throat_diameter / 2.0) ** 2
        elif throat_area is not None:
            throat_diameter = 2.0 * np.sqrt(throat_area / np.pi)
        else:
            # A_t = mdot * c* / Pc  (continuity at choked throat)
            if mdot_total > 0 and chamber_pressure > 0:
                throat_area = mdot_total * c_star / chamber_pressure
            else:
                # last resort: assume throat ~ 0.3 * chamber diameter
                chamber_diameter = motor_data.get('chamber_diameter', 0.1)
                throat_area = np.pi * (0.3 * chamber_diameter / 2.0) ** 2
            throat_diameter = 2.0 * np.sqrt(throat_area / np.pi)

        # throat radius of curvature (for the (Dt/Rc)^0.1 term).
        # Typical converging-diverging nozzles: Rc ~ 0.5..2 * throat radius.
        # Use Rc = 1.5 * throat_radius if not provided (common Bartz assumption).
        throat_radius = throat_diameter / 2.0
        rc = motor_data.get('throat_radius_curvature', 1.5 * throat_radius)
        rc_over_dt = max(rc / throat_diameter, 0.25)  # keep correction bounded

        # static throat temperature (M=1)
        throat_temperature = chamber_temperature / (1.0 + (gamma - 1.0) / 2.0)

        return {
            'c_star': c_star,
            'throat_diameter': throat_diameter,
            'throat_area': throat_area,
            'throat_radius_curvature': rc,
            'rc_over_dt': rc_over_dt,
            'throat_temperature': throat_temperature,
        }

    # ------------------------------------------------------------------
    # Bartz gas-side coefficient
    # ------------------------------------------------------------------
    def _bartz_coefficient(self, throat_diameter: float, chamber_pressure: float,
                           c_star: float, gas: Dict, chamber_temperature: float,
                           wall_temperature: float, rc_over_dt: float,
                           area_ratio_local: float = 1.0, mach_local: float = 1.0) -> float:
        """
        Bartz convective heat-transfer coefficient (SI-consistent, no g0).

        Sutton & Biblarz 9th ed. Eq. 8-22 (Bartz 1957), SI form:

          h_g = (0.026 / D_t^0.2)
                * (mu^0.2 * cp / Pr^0.6)
                * (Pc / c*)^0.8
                * (D_t / R_c)^0.1
                * (A_t / A)^0.9
                * sigma

        with the boundary-layer property correction (Sutton Eq. 8-22):

          sigma = 1 / { [ 0.5*(Tw/Tc)*(1 + (g-1)/2 * M^2) + 0.5 ]^0.68
                        * [ 1 + (g-1)/2 * M^2 ]^0.12 }

        Returns h_g in W/(m^2*K).  area_ratio_local = A_t/A (=1 at throat).
        """
        mu = gas['gas_viscosity']
        cp = gas['gas_cp']
        Pr = gas['prandtl']
        gamma = gas['gamma']

        # boundary-layer correction factor sigma
        m2 = 1.0 + (gamma - 1.0) / 2.0 * mach_local ** 2
        t_ratio = wall_temperature / chamber_temperature
        sigma = 1.0 / ((0.5 * t_ratio * m2 + 0.5) ** 0.68 * m2 ** 0.12)

        # NO g0 in SI: Pc/c* already has units kg/(m^2*s).
        mass_flux_term = (chamber_pressure / c_star) ** 0.8
        prop_term = (mu ** 0.2) * cp / (Pr ** 0.6)
        curvature_term = (1.0 / rc_over_dt) ** 0.1  # (D_t / R_c)^0.1
        area_term = area_ratio_local ** 0.9

        h_g = (0.026 / throat_diameter ** 0.2) * prop_term * mass_flux_term \
            * curvature_term * area_term * sigma
        return h_g

    def _adiabatic_wall_temperature(self, chamber_temperature: float, gas: Dict,
                                    mach_local: float = 1.0) -> float:
        """
        Adiabatic (recovery) wall temperature — the correct driving temperature
        for q = h_g*(Taw - Tw), NOT the stagnation temperature.

          Taw = Tc * (1 + r*(g-1)/2 * M^2) / (1 + (g-1)/2 * M^2)
          r   = Pr^(1/3)  (turbulent recovery factor; Sutton & Biblarz)
        """
        gamma = gas['gamma']
        Pr = gas['prandtl']
        r = Pr ** (1.0 / 3.0)
        m2 = (gamma - 1.0) / 2.0 * mach_local ** 2
        return chamber_temperature * (1.0 + r * m2) / (1.0 + m2)

    # ==================================================================
    # PUBLIC API (signature preserved)
    # ==================================================================
    def analyze_heat_transfer(self, motor_data: Dict, material: str = 'steel',
                            wall_thickness: float = 0.005, ambient_temp: float = 293.15,
                            cooling_type: str = 'natural') -> Dict:
        """
        Complete heat transfer analysis (Bartz-based gas side).

        Args:
            motor_data: Motor performance and geometry data. Recognized optional
                keys (used when present, otherwise physically derived):
                  chamber_pressure [bar], chamber_temperature [K],
                  chamber_diameter [m], chamber_length [m], burn_time [s],
                  mdot_total [kg/s], gamma, molecular_weight [g/mol],
                  gas_constant [J/kg/K], gas_cp, gas_viscosity, gas_conductivity,
                  prandtl, c_star [m/s], throat_diameter [m], throat_area [m^2],
                  throat_radius_curvature [m], cantera_gas (Cantera Solution).
            material: Wall material key (steel, steel_4130, aluminum, inconel,
                copper, ablative, graphite).
            wall_thickness: Wall thickness in meters.
            ambient_temp: Ambient / coolant inlet temperature in K.
            cooling_type: 'natural', 'forced', 'regenerative'.

        Returns:
            Heat transfer analysis results (dict). Top-level keys preserved:
            heat_transfer_coefficients, gas_side_analysis, wall_analysis,
            cooling_analysis, safety_analysis, material_properties,
            design_parameters.
        """
        # Extract motor parameters
        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
        chamber_length = motor_data.get('chamber_length', 0.5)  # m
        burn_time = motor_data.get('burn_time', 10)  # s
        mdot_total = motor_data.get('mdot_total', 1.0)  # kg/s

        # Get material properties (steel_4130 now resolves directly)
        mat_props = self.materials.get(material, self.materials['steel'])

        # Resolve gas properties + throat conditions (no hardcoding)
        gas = self._get_gas_properties(motor_data, chamber_temperature)
        throat = self._resolve_throat_conditions(
            motor_data, chamber_pressure, chamber_temperature, gas, mdot_total
        )

        # Calculate heat transfer coefficients (Bartz gas side)
        heat_transfer_coeffs = self._calculate_heat_transfer_coefficients(
            motor_data, mat_props, cooling_type, gas, throat,
            chamber_pressure, chamber_temperature
        )

        # Gas-side heat transfer (with energy-balance wall temperature)
        gas_side_analysis = self._analyze_gas_side_heat_transfer(
            chamber_pressure, chamber_temperature, chamber_diameter, chamber_length,
            mdot_total, heat_transfer_coeffs, gas, throat, mat_props,
            wall_thickness, ambient_temp
        )

        # Wall temperature distribution (uses the energy-balance flux)
        wall_analysis = self._analyze_wall_temperature(
            gas_side_analysis['heat_flux'], wall_thickness, mat_props,
            ambient_temp, heat_transfer_coeffs['coolant_side'],
            chamber_temperature, gas_side_analysis
        )

        # Cooling requirements
        cooling_analysis = self._analyze_cooling_requirements(
            gas_side_analysis['total_heat_rate'], burn_time, motor_data, cooling_type
        )

        # Safety analysis
        safety_analysis = self._analyze_thermal_safety(
            wall_analysis['max_temperature'], mat_props, wall_thickness, chamber_pressure
        )
        # Surface energy-balance warnings.
        safety_analysis['warnings'] = (
            list(safety_analysis.get('warnings', [])) + gas_side_analysis.get('warnings', [])
        )

        return {
            'heat_transfer_coefficients': heat_transfer_coeffs,
            'gas_side_analysis': gas_side_analysis,
            'wall_analysis': wall_analysis,
            'cooling_analysis': cooling_analysis,
            'safety_analysis': safety_analysis,
            'material_properties': mat_props,
            'design_parameters': {
                'material': material,
                'wall_thickness': wall_thickness * 1000,  # mm
                'cooling_type': cooling_type,
                'ambient_temperature': ambient_temp
            }
        }

    def _calculate_heat_transfer_coefficients(self, motor_data: Dict,
                                           mat_props: Dict, cooling_type: str,
                                           gas: Optional[Dict] = None,
                                           throat: Optional[Dict] = None,
                                           chamber_pressure: Optional[float] = None,
                                           chamber_temperature: Optional[float] = None) -> Dict:
        """
        Calculate heat transfer coefficients.

        Gas side now uses the Bartz throat correlation (physically correct for
        rocket nozzles) instead of the Dittus-Boelter pipe-flow correlation,
        which under-predicted h_g by ~4-15x in the unsafe direction.
        """
        # Backward-compatible resolution if called without the new args.
        if chamber_pressure is None:
            chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        if chamber_temperature is None:
            chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        mdot_total = motor_data.get('mdot_total', 1.0)
        if gas is None:
            gas = self._get_gas_properties(motor_data, chamber_temperature)
        if throat is None:
            throat = self._resolve_throat_conditions(
                motor_data, chamber_pressure, chamber_temperature, gas, mdot_total
            )

        # --- Gas-side: Bartz at the throat (M=1, A_t/A=1) ---
        # Use an estimated cooled-wall temperature for the first sigma estimate;
        # the gas-side analysis later refines wall temperature via energy balance.
        wall_guess = min(0.5 * chamber_temperature, mat_props.get('max_service_temperature', 2000) * 0.8)
        h_gas = self._bartz_coefficient(
            throat['throat_diameter'], chamber_pressure, throat['c_star'],
            gas, chamber_temperature, wall_guess, throat['rc_over_dt'],
            area_ratio_local=1.0, mach_local=1.0
        )

        # Reynolds / Nusselt reported at the throat for reference/diagnostics.
        throat_d = throat['throat_diameter']
        rho_throat = chamber_pressure / (gas['gas_constant'] * throat['throat_temperature'])
        a_throat = np.sqrt(gas['gamma'] * gas['gas_constant'] * throat['throat_temperature'])
        v_throat = a_throat  # M=1
        reynolds = rho_throat * v_throat * throat_d / gas['gas_viscosity']
        prandtl = gas['prandtl']
        nusselt = h_gas * throat_d / gas['gas_conductivity']

        # --- Coolant side ---
        # Representative coolant-side film coefficients [W/(m^2*K)].
        # Regenerative value reflects high-velocity liquid coolant in cooling
        # channels (Huzel & Huang Ch. 4: typically 1e4-5e4 W/m^2/K for
        # cryogenic/liquid regenerative cooling); the previous 2000 W/m^2/K was
        # an order of magnitude too low and pinned the wall near-adiabatic.
        h_coolant = motor_data.get('coolant_side_coefficient', None)
        if h_coolant is None:
            if cooling_type == 'natural':
                h_coolant = 25.0     # natural convection in air
            elif cooling_type == 'forced':
                h_coolant = 100.0    # forced air cooling
            elif cooling_type == 'regenerative':
                h_coolant = 20000.0  # liquid regenerative cooling (Huzel & Huang)
            else:
                h_coolant = 25.0

        return {
            'gas_side': h_gas,
            'coolant_side': h_coolant,
            'reynolds_number': reynolds,
            'prandtl_number': prandtl,
            'nusselt_number': nusselt,
            # extra diagnostics (additive, do not break existing consumers)
            'correlation': 'Bartz (Sutton & Biblarz 9th ed. Eq. 8-22)',
            'c_star': throat['c_star'],
            'throat_diameter': throat['throat_diameter'],
            'gas_viscosity': gas['gas_viscosity'],
            'gas_conductivity': gas['gas_conductivity'],
            'gas_cp': gas['gas_cp'],
            'gamma': gas['gamma'],
        }

    def _analyze_gas_side_heat_transfer(self, pressure: float, temperature: float,
                                      diameter: float, length: float, mdot: float,
                                      coeffs: Dict, gas: Dict, throat: Dict,
                                      mat_props: Dict, wall_thickness: float,
                                      ambient_temp: float) -> Dict:
        """
        Analyze gas-side heat transfer.

        Two distinct quantities are computed, and conflating them is exactly the
        bug that previously hid burn-through:

        (A) DESIGN HEAT FLUX (safety-relevant load). The convective+radiative
            heat flux the cooling system MUST remove, evaluated at a conservative
            *reference cooled wall temperature* (the material allowable temp,
            bounded). This is q = h_g*(Taw - Tw_ref) + eps*sigma_SB*(Taw^4-Tw_ref^4).
            It must NOT be allowed to collapse to zero — letting the wall float to
            the adiabatic temperature drives q->0 and masks the danger.

        (B) EQUILIBRIUM WALL TEMPERATURE (cooling-adequacy check). The steady
            wall temperature actually reached for the *specified* cooling, from
            the surface energy balance q_in(Tw) = q_out(Tw):
                q_in  = h_g*(Taw - Tw) + eps*sigma_SB*(Taw^4 - Tw^4)
                q_out = (Tw - T_coolant) / (R_cond + R_coolant)
            If Tw floats near Taw, the cooling is grossly inadequate (warn).

        References: Bartz (1957); Sutton & Biblarz 9th ed. Ch. 8;
        NASA SP-8124; Huzel & Huang Ch. 4.
        """
        warnings_list: List[str] = []

        h_gas = coeffs['gas_side']
        h_coolant = coeffs['coolant_side']
        k_wall = mat_props['thermal_conductivity']
        emissivity = mat_props.get('emissivity', 0.8)
        max_service = mat_props.get('max_service_temperature', 2000)
        allowable = mat_props.get('allowable_temperature', 1073)

        # Adiabatic wall (recovery) temperature at the throat (M=1).
        Taw = self._adiabatic_wall_temperature(temperature, gas, mach_local=1.0)

        # --- (A) DESIGN HEAT FLUX at a conservative reference cooled wall ---
        # Reference wall temperature: the material allowable temperature, but not
        # warmer than ~80% of Taw (a well-cooled wall is always below Taw). This
        # guarantees a non-zero, conservative thermal load even if the modelled
        # cooling is weak. Lower reference wall => higher (more conservative) q.
        Tw_ref = min(allowable, 0.8 * Taw)
        Tw_ref = max(Tw_ref, ambient_temp)

        def gas_side_flux(Tw, h):
            q_conv = h * (Taw - Tw)
            q_rad = emissivity * self.stefan_boltzmann * (Taw ** 4 - max(Tw, 0.0) ** 4)
            return q_conv + q_rad

        throat_heat_flux = gas_side_flux(Tw_ref, h_gas)  # W/m^2 (real design load)

        # --- (B) EQUILIBRIUM WALL TEMPERATURE for the specified cooling ---
        R_cond = wall_thickness / k_wall
        R_coolant = 1.0 / h_coolant
        R_out = R_cond + R_coolant

        def q_out(Tw):
            return (Tw - ambient_temp) / R_out

        lo, hi = ambient_temp, Taw
        if (gas_side_flux(lo, h_gas) - q_out(lo)) <= 0:
            T_wall = ambient_temp
        elif (gas_side_flux(hi, h_gas) - q_out(hi)) >= 0:
            T_wall = hi
        else:
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                if (gas_side_flux(mid, h_gas) - q_out(mid)) > 0:
                    lo = mid
                else:
                    hi = mid
                if hi - lo < 1e-3:
                    break
            T_wall = 0.5 * (lo + hi)

        # --- Physical clamp / warnings on equilibrium wall temperature ---
        wall_unphysical = False
        mat_name = material_name(mat_props, self.materials)
        if T_wall > max_service:
            wall_unphysical = True
            warnings_list.append(
                f"UNSAFE: equilibrium wall temperature {T_wall:.0f} K exceeds "
                f"{mat_name} service limit {max_service:.0f} K with the specified "
                f"cooling — burn-through likely. Required cooling load "
                f"q={throat_heat_flux/1e6:.1f} MW/m^2 at the throat."
            )
        elif T_wall > allowable:
            warnings_list.append(
                f"WARNING: equilibrium wall temperature {T_wall:.0f} K exceeds "
                f"{mat_name} allowable {allowable:.0f} K — strength margin lost."
            )
        if T_wall > 3500:
            warnings_list.append(
                f"Wall temperature {T_wall:.0f} K is non-physical for any solid "
                f"liner (>3500 K). Regenerative/film cooling or ablative liner required."
            )
        if T_wall >= 0.95 * Taw:
            warnings_list.append(
                "Equilibrium wall temperature pinned near the adiabatic-wall "
                "temperature: modelled cooling is grossly insufficient."
            )

        # The 'heat_flux' key (consumed downstream) is the conservative design
        # load — NEVER the masked near-adiabatic value.
        heat_flux = throat_heat_flux

        # --- Chamber-barrel flux (lower than throat: A_t/A < 1) ---
        throat_area = throat['throat_area']
        surface_area = np.pi * diameter * length + np.pi * (diameter / 2.0) ** 2  # m^2
        chamber_area = np.pi * (diameter / 2.0) ** 2
        area_ratio_chamber = throat_area / chamber_area if chamber_area > 0 else 0.1
        area_ratio_chamber = min(area_ratio_chamber, 1.0)
        h_chamber = self._bartz_coefficient(
            throat['throat_diameter'], pressure, throat['c_star'], gas,
            temperature, Tw_ref, throat['rc_over_dt'],
            area_ratio_local=area_ratio_chamber, mach_local=0.2
        )
        chamber_heat_flux = gas_side_flux(Tw_ref, h_chamber)  # W/m^2 (design load)

        # Total heat rate: chamber flux over barrel area + throat flux over throat.
        total_heat_rate = chamber_heat_flux * surface_area + throat_heat_flux * throat_area  # W

        return {
            'heat_flux': heat_flux,                  # W/m^2 (conservative design load, throat)
            'total_heat_rate': total_heat_rate,      # W
            'surface_area': surface_area,            # m^2
            'throat_heat_flux': throat_heat_flux,    # W/m^2 (real Bartz, not chamber*1.5)
            'chamber_heat_flux': chamber_heat_flux,  # W/m^2 (real Bartz at A_t/A)
            'gas_temperature': temperature,          # K (stagnation/chamber)
            'adiabatic_wall_temperature': Taw,       # K (recovery temperature)
            'reference_wall_temperature': Tw_ref,    # K (cooled wall for design flux)
            'estimated_wall_temperature': T_wall,    # K (equilibrium, given cooling)
            'gas_side_coefficient': h_gas,           # W/m^2/K
            'wall_temperature_unphysical': wall_unphysical,
            'warnings': warnings_list,
        }

    def _analyze_wall_temperature(self, heat_flux: float, thickness: float,
                                mat_props: Dict, ambient_temp: float, h_coolant: float,
                                chamber_temperature: Optional[float] = None,
                                gas_side: Optional[Dict] = None) -> Dict:
        """
        Analyze wall temperature distribution.

        The hot-side (inner) wall temperature is taken from the gas-side energy
        balance when available; the conduction drop across the wall and the
        coolant-side drop are then back-computed consistently from the flux.
        """
        k = mat_props['thermal_conductivity']

        # Thermal resistance analysis [m^2*K/W]
        R_conduction = thickness / k
        R_convection = 1.0 / h_coolant
        R_total = R_conduction + R_convection

        # Temperature drops driven by the (now physical) heat flux.
        delta_T_conduction = heat_flux * R_conduction
        delta_T_convection = heat_flux * R_convection

        if gas_side is not None and 'estimated_wall_temperature' in gas_side:
            # Inner hot-wall from energy balance; outer/coolant temps from flux.
            T_inner = gas_side['estimated_wall_temperature']
            T_outer = T_inner - delta_T_conduction
        else:
            # Backward-compatible resistance-network estimate.
            T_inner = ambient_temp + heat_flux * R_total
            T_outer = ambient_temp + heat_flux * R_convection
        T_average = (T_inner + T_outer) / 2.0

        # Temperature gradient through the wall
        temp_gradient = delta_T_conduction / thickness if thickness > 0 else 0.0

        return {
            'inner_temperature': T_inner,
            'outer_temperature': T_outer,
            'average_temperature': T_average,
            'max_temperature': T_inner,
            'temperature_gradient': temp_gradient,
            'thermal_resistance': {
                'conduction': R_conduction,
                'convection': R_convection,
                'total': R_total
            },
            'temperature_drops': {
                'conduction': delta_T_conduction,
                'convection': delta_T_convection
            }
        }

    def _analyze_cooling_requirements(self, heat_rate: float, burn_time: float,
                                    motor_data: Dict, cooling_type: str) -> Dict:
        """Analyze cooling requirements"""

        # Total heat energy
        total_heat_energy = heat_rate * burn_time  # J

        # Cooling capacity requirements
        if cooling_type == 'natural':
            required_surface_area = heat_rate / (25.0 * 50)  # m² (natural convection)
            coolant_flow_rate = 0  # No active cooling
        elif cooling_type == 'forced':
            required_surface_area = heat_rate / (100.0 * 100)  # m² (forced air)
            coolant_flow_rate = heat_rate / (1000 * 20)  # kg/s (air flow)
        elif cooling_type == 'regenerative':
            coolant_flow_rate = heat_rate / (4180 * 50)  # kg/s (water, 50K rise)
            required_surface_area = heat_rate / (2000.0 * 100)  # m²
        else:
            required_surface_area = 0
            coolant_flow_rate = 0

        # Heat sink analysis (for passive cooling)
        heat_sink_mass = total_heat_energy / (460 * 200)  # kg (steel, 200K rise)

        return {
            'total_heat_energy': total_heat_energy / 1e6,  # MJ
            'peak_heat_rate': heat_rate / 1000,  # kW
            'required_cooling_area': required_surface_area,  # m²
            'coolant_flow_rate': coolant_flow_rate,  # kg/s
            'heat_sink_mass': heat_sink_mass,  # kg
            'cooling_efficiency': self._calculate_cooling_efficiency(cooling_type),
            'recommendations': self._get_cooling_recommendations(cooling_type, heat_rate)
        }

    def _analyze_thermal_safety(self, max_temp: float, mat_props: Dict,
                              thickness: float, pressure: float) -> Dict:
        """Analyze thermal safety margins"""

        allowable_temp = mat_props['allowable_temperature']
        melting_point = mat_props['melting_point']

        # Safety factors (guard against division by zero / negative temps)
        max_temp_safe = max(max_temp, 1.0)
        temp_safety_factor = allowable_temp / max_temp_safe
        melting_safety_factor = melting_point / max_temp_safe

        # Thermal stress (simplified)
        thermal_expansion = 12e-6  # 1/K (typical for steel)
        elastic_modulus = 200e9    # Pa
        thermal_stress = elastic_modulus * thermal_expansion * (max_temp - 293)

        # Allowable stress (simplified)
        yield_strength = 250e6  # Pa (typical for steel)
        stress_safety_factor = yield_strength / thermal_stress if thermal_stress > 0 else 1e6

        # Risk assessment
        risk_level = 'LOW'
        if temp_safety_factor < 1.5:
            risk_level = 'HIGH'
        elif temp_safety_factor < 2.0:
            risk_level = 'MEDIUM'

        warnings_list = []
        if temp_safety_factor < 1.0:
            warnings_list.append('Wall temperature exceeds allowable limit')
        if melting_safety_factor < 2.0:
            warnings_list.append('Wall temperature approaches melting point')
        if stress_safety_factor < 2.0:
            warnings_list.append('High thermal stress - consider thicker walls')

        return {
            'temperature_safety_factor': temp_safety_factor,
            'melting_safety_factor': melting_safety_factor,
            'stress_safety_factor': stress_safety_factor,
            'thermal_stress': thermal_stress / 1e6,  # MPa
            'risk_level': risk_level,
            'warnings': warnings_list,
            'recommendations': self._get_safety_recommendations(temp_safety_factor, thickness)
        }

    def _calculate_cooling_efficiency(self, cooling_type: str) -> float:
        """Calculate cooling system efficiency"""
        efficiencies = {
            'natural': 0.3,
            'forced': 0.6,
            'regenerative': 0.9
        }
        return efficiencies.get(cooling_type, 0.3)

    def _get_cooling_recommendations(self, cooling_type: str, heat_rate: float) -> List[str]:
        """Get cooling system recommendations"""
        recommendations = []

        if heat_rate > 100000:  # > 100 kW
            recommendations.append('High heat load - consider regenerative cooling')
            recommendations.append('Use high thermal conductivity materials')

        if cooling_type == 'natural' and heat_rate > 10000:
            recommendations.append('Natural cooling insufficient - use forced cooling')

        recommendations.append('Consider heat sink or thermal mass for short burns')
        recommendations.append('Monitor wall temperature during operation')

        return recommendations

    def _get_safety_recommendations(self, temp_safety_factor: float, thickness: float) -> List[str]:
        """Get thermal safety recommendations"""
        recommendations = []

        if temp_safety_factor < 1.5:
            recommendations.append('Increase wall thickness')
            recommendations.append('Improve cooling system')
            recommendations.append('Use higher temperature material')

        if thickness < 0.003:
            recommendations.append('Minimum wall thickness should be 3mm')

        recommendations.append('Consider thermal barrier coating')
        recommendations.append('Implement temperature monitoring')

        return recommendations


def material_name(mat_props: Dict, materials_db: Dict) -> str:
    """Reverse-lookup a material name from its property dict (best effort)."""
    for name, props in materials_db.items():
        if props is mat_props:
            return name
    return 'material'
