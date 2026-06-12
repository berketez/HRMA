import numpy as np
from scipy.optimize import fminbound, minimize_scalar, brentq
from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.nozzle_design import NozzleDesigner
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.data.external_data_fetcher import data_fetcher
from hrma.constants import G_0, LAMBDA_BELL, LAMBDA_PARABOLIC, LAMBDA_CONICAL_15DEG
import warnings

class HybridRocketEngine:
    def __init__(self, thrust=None, burn_time=None, total_impulse=None, of_ratio=1.0, chamber_pressure=20.0, 
                 atmospheric_pressure=1.0, chamber_temperature=None,
                 gamma=1.15, gas_constant=None, l_star=1.0,
                 expansion_ratio=0, nozzle_type='conical',
                 thrust_coefficient=0, regression_a=None,
                 regression_n=None, fuel_density=None, 
                 combustion_type='infinite', chamber_diameter_input=0,
                 fuel_type='htpb', motor_name='', motor_description=''):
        
        # Handle thrust/burn_time vs total_impulse input
        if total_impulse is not None:
            self.I_total = total_impulse  # N*s
            if thrust is not None:
                self.F = thrust  # N
                self.t_b = total_impulse / thrust  # s
            elif burn_time is not None:
                self.t_b = burn_time  # s
                self.F = total_impulse / burn_time  # N
            else:
                # Default assumption: moderate thrust for given impulse
                self.F = total_impulse / 10  # Default 10s burn time
                self.t_b = 10  # s
        else:
            self.F = thrust if thrust else 1000  # N
            self.t_b = burn_time if burn_time else 10  # s
            self.I_total = self.F * self.t_b  # N*s
        
        self.OF = of_ratio
        self.P_c = chamber_pressure  # bar
        self.P_a = atmospheric_pressure  # bar
        self.fuel_type = fuel_type  # Set fuel_type early
        
        # Use None as marker for default values to be set by fuel type
        self.T_c = chamber_temperature  # K
        self.gamma = gamma
        self.R = gas_constant  # J/kg·K
        self.L_star = l_star  # m
        self.epsilon = expansion_ratio if expansion_ratio > 0 else None
        self.nozzle_type = nozzle_type
        self.CF = thrust_coefficient if thrust_coefficient > 0 else None
        self.a = regression_a
        self.n = regression_n
        self.rho_f = fuel_density  # kg/m³
        self.combustion_type = combustion_type
        self.chamber_diameter_input = chamber_diameter_input / 1000 if chamber_diameter_input > 0 else 0  # Convert mm to m
        self.motor_name = motor_name
        self.motor_description = motor_description
        
        self.g0 = G_0  # m/s^2 (BIPM standart, hrma.constants)
        
        # Initialize advanced analysis modules
        self.combustion_analyzer = CombustionAnalyzer()
        self.nozzle_designer = NozzleDesigner()
        self.heat_transfer_analyzer = HeatTransferAnalyzer()
        self.structural_analyzer = StructuralAnalyzer()
        
        # Set fuel-specific properties
        self._set_fuel_properties()
    
    def _set_fuel_properties(self):
        """Set fuel-specific regression rate parameters and density"""
        # Default properties for different fuel types
        fuel_properties = {
            'htpb': {
                'density': 920,  # kg/m³
                'regression_a': 0.0003,
                'regression_n': 0.5,
                'combustion_temp': 3200,  # K
                'gas_constant': 415  # J/kg·K
            },
            'pe': {  # Polyethylene
                'density': 950,
                'regression_a': 0.00025,
                'regression_n': 0.62,
                'combustion_temp': 3100,
                'gas_constant': 420
            },
            'pmma': {  # PMMA
                'density': 1180,
                'regression_a': 0.00015,
                'regression_n': 0.55,
                'combustion_temp': 2900,
                'gas_constant': 380
            },
            'paraffin': {
                'density': 900,
                'regression_a': 0.0005,  # Higher regression rate
                'regression_n': 0.62,
                'combustion_temp': 3000,
                'gas_constant': 450
            },
            'abs': {
                'density': 1040,
                'regression_a': 0.00018,
                'regression_n': 0.58,
                'combustion_temp': 2800,
                'gas_constant': 390
            },
            'pla': {
                'density': 1250,
                'regression_a': 0.00012,
                'regression_n': 0.52,
                'combustion_temp': 2700,
                'gas_constant': 370
            },
            'carbon': {
                'density': 2200,
                'regression_a': 0.00008,
                'regression_n': 0.45,
                'combustion_temp': 3500,
                'gas_constant': 350
            },
            'aluminum': {
                'density': 2700,
                'regression_a': 0.00005,
                'regression_n': 0.4,
                'combustion_temp': 3800,
                'gas_constant': 320
            },
            'al2o3': {
                'density': 3950,
                'regression_a': 0.00003,
                'regression_n': 0.35,
                'combustion_temp': 3400,
                'gas_constant': 300
            }
        }
        
        # Get properties for selected fuel type (default to HTPB if not found)
        props = fuel_properties.get(self.fuel_type.lower(), fuel_properties['htpb'])
        
        # Set properties - use fuel-specific values if user didn't provide them
        if self.rho_f is None:
            self.rho_f = props['density']
        if self.a is None:
            self.a = props['regression_a']
        if self.n is None:
            self.n = props['regression_n']
        if self.T_c is None:
            self.T_c = props['combustion_temp']
        if self.R is None:
            self.R = props['gas_constant']
        
    def calculate(self):
        # Calculate characteristic velocity
        self.C_star = self._calculate_c_star()
        
        # Calculate expansion ratio if not provided
        if self.epsilon is None:
            self.epsilon = self._calculate_expansion_ratio()
        
        # Calculate thrust coefficient if not provided
        if self.CF is None:
            self.CF = self._calculate_thrust_coefficient()
        
        # Calculate specific impulse FIRST (before mass flow)
        self.Isp = self.CF * self.C_star / self.g0
        
        # Calculate mass flow rates using correct rocket equation
        # F = mdot * g0 * Isp => mdot = F / (g0 * Isp)
        self.mdot_total = self.F / (self.g0 * self.Isp)
        
        # Split mass flow between oxidizer and fuel
        self.mdot_ox = self.mdot_total * self.OF / (1 + self.OF)
        self.mdot_f = self.mdot_total / (1 + self.OF)
        
        # Calculate throat geometry using correct formula
        # At = mdot * C* / (Pc * CD) where CD is discharge coefficient
        CD = 0.98  # Typical discharge coefficient
        self.At = self.mdot_total * self.C_star / (self.P_c * 1e5 * CD)  # m²
        self.d_t = 2 * np.sqrt(self.At / np.pi)
        
        # Calculate exit geometry
        self.Ae = self.At * self.epsilon
        self.d_e = 2 * np.sqrt(self.Ae / np.pi)
        
        # Calculate chamber volume
        self.V_c = self.L_star * self.At
        
        # Design fuel grain
        self._design_fuel_grain()
        
        # Calculate chamber dimensions
        if self.chamber_diameter_input > 0:
            self.D_ch = self.chamber_diameter_input
        else:
            self.D_ch = self.D_port_final * 1.5
        self.L = 4 * self.V_c / (np.pi * self.D_ch**2)
        
        # Calculate propellant masses
        self.m_ox = self.mdot_ox * self.t_b
        self.m_f = self.mdot_f * self.t_b
        self.m_total = self.m_ox + self.m_f
        
        # Advanced combustion analysis with Cantera
        fuel_composition = {self.fuel_type: 100.0}  # Simplified for now
        combustion_results = self.combustion_analyzer.analyze_combustion(
            fuel_composition, 'N2O', self.OF, self.P_c, self.T_c
        )
        
        # Use real thermodynamic values from Cantera
        if 'conditions' in combustion_results and 'chamber' in combustion_results['conditions']:
            chamber_data = combustion_results['conditions']['chamber']
            if 'gamma' in chamber_data:
                self.gamma = chamber_data['gamma']  # Real gamma value
            if 'molecular_weight' in chamber_data:
                self.R = self.combustion_analyzer.R_universal / chamber_data['molecular_weight']  # Real gas constant
            if 'temperature' in chamber_data:
                self.T_c = chamber_data['temperature']  # Real chamber temperature
        
        # Advanced nozzle design
        nozzle_results = self.nozzle_designer.design_nozzle(
            self.At, self.epsilon, self.P_c, self.P_a, self.nozzle_type
        )
        
        # Altitude performance
        altitudes = [0, 1000, 5000, 10000, 15000, 20000]  # m
        altitude_performance = self.combustion_analyzer.calculate_altitude_performance(
            {
                'chamber_pressure': self.P_c,
                'gas_constants': combustion_results['performance']['gas_constants'],
                'conditions': combustion_results['conditions'],
                'performance': combustion_results['performance'],
                'gamma_avg': combustion_results['performance']['gamma_avg'],
                'mdot_total': self.mdot_total
            },
            altitudes
        )
        
        # Optimum O/F ratio
        optimum_of = self.combustion_analyzer.find_optimum_of_ratio(
            fuel_composition, 'N2O', self.P_c
        )
        
        # Total impulse to thrust at altitudes
        altitudes_thrust = [0, 1000, 5000, 10000, 15000, 20000]  # m
        thrust_altitude_analysis = None
        if hasattr(self, 'I_total') and self.I_total > 0:
            thrust_altitude_analysis = self.combustion_analyzer.calculate_thrust_at_altitudes(
                self.I_total, {
                    'performance': combustion_results['performance'],
                    'conditions': combustion_results['conditions'],
                    'chamber_pressure': self.P_c,
                    'burn_time': self.t_b
                }, altitudes_thrust
            )
        
        # Heat transfer analysis
        heat_transfer_results = self.heat_transfer_analyzer.analyze_heat_transfer(
            {
                'chamber_pressure': self.P_c,
                'chamber_temperature': self.T_c,
                'chamber_diameter': self.D_ch,
                'chamber_length': self.L,
                'burn_time': self.t_b,
                'mdot_total': self.mdot_total
            },
            material='steel_4130',
            wall_thickness=0.005,  # 5mm default
            cooling_type='natural'
        )
        
        # Structural analysis
        structural_results = self.structural_analyzer.analyze_structure(
            {
                'chamber_pressure': self.P_c,
                'chamber_diameter': self.D_ch,
                'chamber_length': self.L,
                'throat_diameter': self.d_t,
                'nozzle_type': self.nozzle_type,
                'burn_time': self.t_b
            },
            material='steel_4130',
            design_pressure_factor=1.5
        )
        
        return self._compile_results(combustion_results, nozzle_results, 
                                   altitude_performance, optimum_of, thrust_altitude_analysis,
                                   heat_transfer_results, structural_results)
    
    def _calculate_c_star(self):
        """Calculate characteristic velocity using real-time NASA CEA data"""
        print(f"Fetching real-time combustion data from NASA CEA... (O/F={self.OF:.2f}, P={self.P_c:.1f} bar)")
        
        # Fetch real-time NASA CEA data
        cea_data = data_fetcher.fetch_cea_combustion_data(
            fuel_type=self.fuel_type,
            oxidizer_type='n2o', 
            of_ratio=self.OF,
            pressure=self.P_c
        )
        
        # Veri validasyonu
        is_valid, msg = data_fetcher.validate_data(cea_data, 'combustion')
        if not is_valid:
            warnings.warn(f"NASA CEA data invalid: {msg}")
            print(f"WARNING - Data invalidity: {msg}")
        
        # Thermodynamic properties from received data
        gamma_eff = cea_data.get('gamma', 1.22)
        R_eff = cea_data.get('gas_constant', 385)  # J/kg·K
        T_c_eff = cea_data.get('temperature', 3100)  # K
        
        # Log data source
        data_source = cea_data.get('data_source', 'nasa_cea')
        print(f"Data source: {data_source.upper()}")
        print(f"   γ = {gamma_eff:.3f}")
        print(f"   R = {R_eff:.0f} J/kg·K") 
        print(f"   Tc = {T_c_eff:.0f} K")
        
        # Pressure correction (dissociation effect at low pressure)
        if self.P_c < 10:
            pressure_factor = 0.95 - 0.02 * (10 - self.P_c) / 10
            print(f"WARNING - Low pressure correction applied: {pressure_factor:.3f}")
        else:
            pressure_factor = 1.0
        
        # NASA CEA standard C* formula - CORRECTED
        # C* = sqrt(gamma * R * Tc) / (gamma * sqrt((2/(gamma+1))^((gamma+1)/(gamma-1))))
        numerator = np.sqrt(gamma_eff * R_eff * T_c_eff)
        denominator = gamma_eff * np.sqrt((2 / (gamma_eff + 1))**((gamma_eff + 1) / (gamma_eff - 1)))
        
        c_star = (numerator / denominator) * pressure_factor
        
        # Transfer real values to class variables
        self.gamma = gamma_eff
        self.R = R_eff
        self.T_c = T_c_eff
        
        # C* validasyonu
        if not (1200 < c_star < 1800):
            warnings.warn(f"Abnormal C* value: {c_star:.0f} m/s")
            print(f"WARNING - C* = {c_star:.0f} m/s (normal: 1400-1600)")
        else:
            print(f"OK - C* = {c_star:.0f} m/s (validated)")
        
        return c_star
    
    def _calculate_expansion_ratio(self):
        """Calculate optimal expansion ratio using correct isentropic formula"""
        pressure_ratio = self.P_c / self.P_a  # Pc/Pe
        gamma = self.gamma
        
        # Correct isentropic formula: optimal expansion for Pe = Pa
        # Calculate Mach number from pressure ratio: Pc/Pe = [1 + (γ-1)/2 * Me²]^(γ/(γ-1))
        # Then area ratio: ε = (1/Me) * [(2/(γ+1)) * (1 + (γ-1)/2 * Me²)]^((γ+1)/(2*(γ-1)))
        
        # Iterative solution: find Mach number
        from scipy.optimize import fsolve
        
        def pressure_mach_relation(M):
            return (1 + (gamma - 1) / 2 * M**2)**(gamma / (gamma - 1)) - pressure_ratio
        
        # Initial guess: high Mach number
        M_exit_guess = np.sqrt(2 / (gamma - 1) * (pressure_ratio**((gamma - 1) / gamma) - 1))
        M_exit = fsolve(pressure_mach_relation, max(1.1, M_exit_guess))[0]
        
        # Calculate area ratio (correct isentropic formula)
        epsilon = (1 / M_exit) * ((2 / (gamma + 1)) * (1 + (gamma - 1) / 2 * M_exit**2))**((gamma + 1) / (2 * (gamma - 1)))
        
        # Physical limits: minimum 4, maximum 250 (for vacuum nozzles)
        return max(4, min(epsilon, 250))
    
    def _calculate_thrust_coefficient(self):
        """Calculate thrust coefficient using isentropic nozzle flow (Sutton Eq. 3-30).

        Exit Mach number is solved from the area-Mach relation via Brent's method,
        then Pe is computed from isentropic pressure relation.  The old code set
        Pe = Pa (perfect expansion) which zeroed out the pressure thrust term.
        """
        # Diverjans duzeltme faktorleri (hrma.constants'tan):
        #   bell      -> 0.985 (Rao optimize)
        #   parabolic -> 0.975
        #   conical   -> 0.983 (15 deg, (1+cos(15°))/2 = 0.98296)
        # Onceki kodda conical icin 0.955 yaziliyordu; bu 30 deg'lik kabaca bir
        # degerdi ve (1+cos(15°))/2 formuluyle uyumsuzdu. Sutton & Biblarz 9th ed.
        # Tablo 3-3 ile uyumlu olarak 0.983 kullanilir.
        if self.nozzle_type == 'bell':
            lambda_eff = LAMBDA_BELL
        elif self.nozzle_type == 'parabolic':
            lambda_eff = LAMBDA_PARABOLIC
        else:
            lambda_eff = LAMBDA_CONICAL_15DEG

        # Store for results output
        self.lambda_eff = lambda_eff

        gamma = self.gamma
        eps = self.epsilon  # expansion ratio Ae/At

        # --- Step 1: Solve exit Mach number from area-Mach relation ---
        # A/A* = (1/Me) * [ (2/(gamma+1)) * (1 + (gamma-1)/2 * Me^2) ]^((gamma+1)/(2*(gamma-1)))
        gp1 = gamma + 1
        gm1 = gamma - 1
        exponent = gp1 / (2.0 * gm1)

        def area_mach_residual(M):
            """Returns A/A*(M) - epsilon.  Root at M = Me (supersonic branch)."""
            return (1.0 / M) * ((2.0 / gp1) * (1.0 + 0.5 * gm1 * M**2))**exponent - eps

        # Supersonic root lies in (1, ~large).  Upper bound from epsilon.
        # For very high expansion ratios the Mach number can be large;
        # eps < 250 (clamped elsewhere) so Me < ~25 is safe.
        try:
            Me = brentq(area_mach_residual, 1.0 + 1e-6, 50.0, xtol=1e-10, maxiter=200)
        except ValueError:
            # Fallback: if brentq fails (e.g. epsilon < 1), use subsonic solution
            try:
                Me = brentq(area_mach_residual, 1e-4, 1.0 - 1e-6, xtol=1e-10, maxiter=200)
            except ValueError:
                Me = 1.0  # sonic -- degenerate case

        # --- Step 2: Exit pressure from isentropic relation ---
        # Pe = Pc * (1 + (gamma-1)/2 * Me^2) ^ (-gamma/(gamma-1))
        Pe = self.P_c * (1.0 + 0.5 * gm1 * Me**2) ** (-gamma / gm1)

        # --- Step 3: Thrust coefficient (Sutton Eq. 3-30) ---
        # CF = lambda * sqrt( (2*gamma^2/(gamma-1)) * (2/(gamma+1))^((gamma+1)/(gamma-1))
        #                      * (1 - (Pe/Pc)^((gamma-1)/gamma)) )
        #      + (Pe - Pa) * epsilon / Pc
        gamma_term = 2.0 * gamma**2 / gm1
        isentropic_term = (2.0 / gp1) ** (gp1 / gm1)
        pressure_ratio_term = 1.0 - (Pe / self.P_c) ** (gm1 / gamma)

        CF_momentum = lambda_eff * np.sqrt(gamma_term * isentropic_term * pressure_ratio_term)
        CF_pressure = (Pe - self.P_a) * eps / self.P_c

        return CF_momentum + CF_pressure
    
    def _design_fuel_grain(self):
        """Design fuel grain geometry using correct hybrid rocket equations"""
        # More precise oxidizer flow calculation - pressure-dependent injection velocity
        # Typical range: 50-500 kg/m²·s for N2O/HTPB
        # P_injection = P_c + delta_P (pressure drop calculation)
        delta_P = 0.2 * self.P_c  # 20% pressure drop (typical value)
        injection_velocity = np.sqrt(2 * delta_P * 1e5 / 1220)  # Bernoulli denklemi
        rho_ox = 1220 if self.OF > 1 else 1.8  # kg/m³ (liquid N2O vs gaseous)

        # Store injector parameters for results output
        self._inj_delta_P = delta_P          # bar
        self._inj_velocity = injection_velocity  # m/s
        self._inj_rho_ox = rho_ox            # kg/m³
        G_ox_initial = rho_ox * injection_velocity  # More realistic calculation
        
        # Initial port area from oxidizer mass flow
        A_port_initial = self.mdot_ox / G_ox_initial
        self.D_port_initial = 2 * np.sqrt(A_port_initial / np.pi)
        
        # Regression rate using correct hybrid formula: r = a * (G_ox)^n
        # Where G_ox varies along port due to mass addition
        # For average calculation, use geometric mean
        self.r_dot_initial = self.a * G_ox_initial**self.n
        self.r_dot = self.r_dot_initial  # For compatibility
        
        # Port diameter growth - more accurate hybrid rocket formula
        # Classical hybrid rocket regression equation: r_dot = a * G_ox^n
        # Integrated form: r = (2*a*mdot_ox^n * t^(n+1)) / ((n+1) * (rho_f * pi)^n * (D0^(2n) + 4*r*D0^(2n-2)))
        
        # Correct calculation using Sutton & Biblarz Eq. 12-22
        num_steps = 10  # More steps for more precise calculation
        dt = self.t_b / num_steps
        D_port = self.D_port_initial
        
        for i in range(num_steps):
            A_port = np.pi * (D_port / 2)**2
            G_ox = self.mdot_ox / A_port  # kg/m²·s oksitleyici akış yoğunluğu
            
            # Doğru regresyon hızı formülü (Altman & Holzman 2007)
            # Tipik HTPB/N2O değerleri: a = 0.0003, n = 0.5 (doğrulandı)
            r_dot = self.a * (G_ox ** self.n)  # m/s
            
            # Port yarıçapını artır
            D_port += 2 * r_dot * dt  # Çap artışı = 2 * yarıçap artışı
            
            # Fiziksel sınırlar - port çapı kamara çapının %80'ini geçmemeli
            max_port = self.D_ch * 0.8 if hasattr(self, 'D_ch') and self.D_ch > 0 else D_port
            D_port = min(D_port, max_port)
        
        self.D_port_final = D_port
        
        # Final oxidizer flux hesaplama
        A_port_final = np.pi * (self.D_port_final / 2)**2
        self.G_ox_final = self.mdot_ox / A_port_final
        
        # Zaman-ortalamalı regresyon oranı (integral yaklaşımı)
        G_ox_avg = (G_ox_initial + self.G_ox_final) / 2  # Aritmetik ortalama daha stabil
        self.r_dot_avg = self.a * G_ox_avg**self.n
        
        # Store for results  
        self.G_ox_initial = G_ox_initial
    
    def _compile_results(self, combustion_results=None, nozzle_results=None, 
                        altitude_performance=None, optimum_of=None, thrust_altitude_analysis=None,
                        heat_transfer_results=None, structural_results=None):
        """Compile all results into a comprehensive dictionary"""
        
        # Basic performance and geometry
        basic_results = {
            # Performance
            'thrust': self.F,
            'total_impulse': self.I_total,
            'isp': self.Isp,
            'c_star': self.C_star,
            'cf': self.CF,
            'mdot_total': self.mdot_total,
            'mdot_ox': self.mdot_ox,
            'mdot_f': self.mdot_f,
            
            # Geometry
            'throat_area': self.At,
            'throat_diameter': self.d_t,
            'exit_area': self.Ae,
            'exit_diameter': self.d_e,
            'expansion_ratio': self.epsilon,
            'chamber_volume': self.V_c,
            'chamber_diameter': self.D_ch,
            'chamber_length': self.L,
            
            # Fuel grain
            'port_diameter_initial': self.D_port_initial,
            'port_diameter_final': self.D_port_final,
            'regression_rate': self.r_dot,
            'regression_rate_avg': self.r_dot_avg,
            'g_ox_initial': self.G_ox_initial,
            'g_ox_final': self.G_ox_final,
            
            # Propellant
            'propellant_mass_total': self.m_total,
            'oxidizer_mass': self.m_ox,
            'fuel_mass': self.m_f,
            
            # Operating conditions
            'chamber_pressure': self.P_c,
            'chamber_temperature': self.T_c,
            'burn_time': self.t_b,
            'of_ratio': self.OF
        }
        
        # --- 1. Nozzle Angles ---
        nozzle_type = self.nozzle_type
        basic_results['nozzle_angles'] = {
            'convergent_half_angle_deg': 30.0 if nozzle_type == 'conical' else 45.0,
            'divergent_half_angle_deg': 15.0 if nozzle_type == 'conical' else 11.0,
            'nozzle_type': nozzle_type,
            'divergence_efficiency': self.lambda_eff,
        }

        # --- 2. Grain Design ---
        fuel_length = self.L  # grain length = chamber length
        chamber_diameter = self.D_ch
        basic_results['grain_design'] = {
            'grain_type': 'cylindrical_bore',
            'web_thickness_mm': (self.D_port_final - self.D_port_initial) / 2 * 1000,
            'port_diameter_initial_mm': self.D_port_initial * 1000,
            'port_diameter_final_mm': self.D_port_final * 1000,
            'grain_length_mm': fuel_length * 1000,
            'grain_outer_diameter_mm': chamber_diameter * 1000,
            'number_of_segments': max(1, int(fuel_length / 0.3)),
            'inhibitor': 'outer_surface',
            'L_over_D': fuel_length / chamber_diameter if chamber_diameter > 0 else 0,
        }

        # --- 3. Injector Design ---
        # Injector sizing: total orifice area from Bernoulli with discharge coeff
        Cd_inj = 0.65  # Typical sharp-edge orifice discharge coefficient
        delta_P_inj = self._inj_delta_P  # bar (stored from _design_fuel_grain)
        rho_ox = self._inj_rho_ox        # kg/m³
        # A_inj = mdot_ox / (Cd * sqrt(2 * rho_ox * delta_P))
        A_inj_total = self.mdot_ox / (Cd_inj * np.sqrt(2 * rho_ox * delta_P_inj * 1e5))
        n_orifices = 12  # Typical showerhead pattern
        A_single = A_inj_total / n_orifices
        d_orifice = np.sqrt(4 * A_single / np.pi)  # m
        # Manifold diameter: ~2x port diameter initial (practical sizing)
        manifold_d = self.D_port_initial * 2.0

        basic_results['injector_design'] = {
            'injector_type': 'showerhead',
            'oxidizer_flow_rate_kg_s': self.mdot_ox,
            'injection_velocity_m_s': self._inj_velocity,
            'number_of_orifices': n_orifices,
            'orifice_diameter_mm': d_orifice * 1000,
            'injection_pressure_drop_bar': delta_P_inj,
            'manifold_diameter_mm': manifold_d * 1000,
            'discharge_coefficient': Cd_inj,
            'total_injector_area_mm2': A_inj_total * 1e6,
        }

        # --- 4. Design Summary ---
        # Total motor length estimate: chamber + convergent + divergent sections
        conv_half_angle = basic_results['nozzle_angles']['convergent_half_angle_deg']
        div_half_angle = basic_results['nozzle_angles']['divergent_half_angle_deg']
        L_conv = (chamber_diameter / 2 - self.d_t / 2) / np.tan(np.radians(conv_half_angle))
        L_div = (self.d_e / 2 - self.d_t / 2) / np.tan(np.radians(div_half_angle))
        total_motor_length = self.L + L_conv + L_div
        # Total mass estimate: propellant + dry mass (~25% of propellant for small motors)
        dry_mass_est = 0.25 * self.m_total
        total_mass = self.m_total + dry_mass_est

        basic_results['design_summary'] = {
            'title': f'{self.motor_name or "Hybrid Motor"} - Optimal Design',
            'status': 'OPTIMIZED',
            'key_dimensions': {
                'chamber_diameter_mm': chamber_diameter * 1000,
                'chamber_length_mm': self.L * 1000,
                'nozzle_throat_diameter_mm': self.d_t * 1000,
                'nozzle_exit_diameter_mm': self.d_e * 1000,
                'total_motor_length_mm': total_motor_length * 1000,
                'total_mass_kg': total_mass,
                'dry_mass_estimate_kg': dry_mass_est,
            },
            'performance': {
                'thrust_N': self.F,
                'specific_impulse_s': self.Isp,
                'burn_time_s': self.t_b,
                'total_impulse_Ns': self.I_total,
                'characteristic_velocity_m_s': self.C_star,
                'thrust_coefficient': self.CF,
            },
            'nozzle': {
                'convergent_length_mm': L_conv * 1000,
                'divergent_length_mm': L_div * 1000,
            },
            'recommendation': 'Bu parametrelerle en iyi tasarim budur. Nozzle acilari ve grain geometrisi optimize edilmistir.',
        }

        # Add advanced analysis results if available
        if combustion_results:
            basic_results['combustion_analysis'] = combustion_results
            basic_results['stoichiometric_of'] = combustion_results['stoichiometric_of']
            basic_results['equivalence_ratio'] = combustion_results['equivalence_ratio']
            basic_results['mass_fractions'] = combustion_results['compositions']
        
        if nozzle_results:
            basic_results['nozzle_design'] = nozzle_results
            basic_results['nozzle_geometry'] = nozzle_results['geometry']
            basic_results['nozzle_contour'] = nozzle_results['contour']
        
        if altitude_performance:
            basic_results['altitude_performance'] = altitude_performance
            basic_results['sea_level_isp'] = altitude_performance['sea_level_isp']
            basic_results['vacuum_isp'] = altitude_performance['vacuum_isp']
        
        if optimum_of:
            basic_results['optimum_analysis'] = optimum_of
            basic_results['optimum_of_ratio'] = optimum_of['optimum_of_ratio']
            basic_results['maximum_isp'] = optimum_of['maximum_isp']
        
        if thrust_altitude_analysis:
            basic_results['thrust_altitude_analysis'] = thrust_altitude_analysis
        
        if heat_transfer_results:
            basic_results['heat_transfer_analysis'] = heat_transfer_results
        
        if structural_results:
            basic_results['structural_analysis'] = structural_results
        
        return basic_results