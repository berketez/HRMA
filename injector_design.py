import numpy as np
from scipy.optimize import minimize_scalar
from external_data_fetcher import data_fetcher
import warnings

class InjectorDesign:
    def __init__(self, mdot_ox, chamber_pressure, oxidizer_phase='liquid',
                 oxidizer_density=1220, oxidizer_viscosity=0.0002,
                 tank_pressure=50, pressure_drop=0, discharge_coefficient=0.7,
                 injector_type='showerhead', oxidizer_temp=293):
        
        self.mdot_ox = mdot_ox  # kg/s
        self.P_c = chamber_pressure  # bar
        self.ox_phase = oxidizer_phase
        self.P_tank = tank_pressure  # bar
        self.oxidizer_temp = oxidizer_temp  # K
        
        print(f"Oksitleyici özellikleri alınıyor... (T={oxidizer_temp:.0f}K, P={tank_pressure:.1f} bar)")
        
        # Termodinamik veritabanından gerçek oksitleyici özellikleri çek
        nist_data = data_fetcher.fetch_nist_oxidizer_properties('n2o', oxidizer_temp, tank_pressure)
        
        # Veri validasyonu
        is_valid, msg = data_fetcher.validate_data(nist_data, 'oxidizer')
        if not is_valid:
            warnings.warn(f"NIST oksitleyici verisi geçersiz: {msg}")
            print(f"UYARI - Veri geçersizliği: {msg}")
        
        # NIST verilerini kullan veya yedek değerleri al
        self.rho_ox = nist_data.get('density', oxidizer_density)  # kg/m³
        self.mu_ox = nist_data.get('viscosity', oxidizer_viscosity)  # Pa·s
        
        # Veri kaynağını logla
        data_source = nist_data.get('data_source', 'nist_webbook')
        print(f"Veri kaynağı: {data_source.upper()}")
        print(f"   ρ = {self.rho_ox:.0f} kg/m³")
        print(f"   μ = {self.mu_ox:.6f} Pa·s")
        
        # Daha gerçekçi basınç düşümü hesaplaması
        # İnjektör basınç düşümü tipik olarak kamara basıncının %15-25'i olmalı
        # Çok düşükse atomizasyon kötü, çok yüksekse tankaj sistemi ağır
        if pressure_drop > 0:
            self.delta_P_inj = pressure_drop
        else:
            # NASA SP-8089 standardına göre optimum basınç düşümü
            min_delta_P = 0.15 * chamber_pressure  # Minimum %15
            optimal_delta_P = 0.20 * chamber_pressure  # Optimal %20
            max_delta_P = 0.30 * chamber_pressure  # Maksimum %30
            
            # Tank basıncına göre optimize et
            available_delta_P = tank_pressure - chamber_pressure
            if available_delta_P < min_delta_P:
                self.delta_P_inj = min_delta_P
                print(f"Uyarı: Tank basıncı yetersiz. Minimum {min_delta_P:.1f} bar basınç düşümü gerekli.")
            elif available_delta_P > max_delta_P:
                self.delta_P_inj = optimal_delta_P
            else:
                self.delta_P_inj = min(optimal_delta_P, available_delta_P * 0.8)
        self.C_d = discharge_coefficient
        self.injector_type = injector_type
        
        # Type-specific parameters
        self.showerhead_params = {}
        self.pintle_params = {}
        self.swirl_params = {}
        
    def set_showerhead_params(self, target_velocity=30, n_holes=0,
                            hole_diameter_min=0.3, hole_diameter_max=2.0,
                            plate_thickness=3.0):
        self.showerhead_params = {
            'v_target': target_velocity,
            'n_holes': n_holes,
            'd_min': hole_diameter_min / 1000,  # Convert mm to m
            'd_max': hole_diameter_max / 1000,
            't_plate': plate_thickness / 1000
        }
    
    def set_pintle_params(self, outer_diameter=50, pintle_diameter=25):
        self.pintle_params = {
            'D_outer': outer_diameter / 1000,  # Convert mm to m
            'D_pintle': pintle_diameter / 1000
        }
    
    def set_swirl_params(self, n_slots=6, slot_width=0, slot_height=0):
        self.swirl_params = {
            'n_slots': n_slots,
            'w': slot_width / 1000 if slot_width > 0 else None,
            'h': slot_height / 1000 if slot_height > 0 else None
        }
    
    def calculate(self):
        if self.injector_type == 'showerhead':
            return self._calculate_showerhead()
        elif self.injector_type == 'pintle':
            return self._calculate_pintle()
        elif self.injector_type == 'swirl':
            return self._calculate_swirl()
        else:
            raise ValueError(f"Unknown injector type: {self.injector_type}")
    
    def _calculate_showerhead(self):
        # Correct orifice equation: mdot = Cd * A * sqrt(2 * rho * delta_P)
        delta_P_Pa = self.delta_P_inj * 1e5
        A_inj_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))
        
        # Exit velocity from Bernoulli: v = sqrt(2 * delta_P / rho)
        v_exit = np.sqrt(2 * delta_P_Pa / self.rho_ox)
        
        # Optimize holes if not specified
        params = self.showerhead_params
        if params['n_holes'] == 0:
            n_holes, d_h = self._optimize_showerhead_holes(A_inj_required, params)
        else:
            n_holes = params['n_holes']
            d_h = 2 * np.sqrt(A_inj_required / (n_holes * np.pi))
        
        # Check constraints
        d_h = max(params['d_min'], min(d_h, params['d_max']))
        
        # Recalculate with final values
        A_inj = n_holes * np.pi * (d_h/2)**2
        # Use consistent velocity calculation
        v_exit = np.sqrt(2 * delta_P_Pa / self.rho_ox)
        
        # Reynolds number hesaplaması - doğru formül ve birimler
        # Re = ρ * v * D / μ
        # ρ: kg/m³, v: m/s, D: m, μ: Pa·s = kg/(m·s)
        # N2O sıvısı için 20°C'de viskozite: ~0.0002 Pa·s
        
        # Sıcaklık etkisiyle viskozite düzeltmesi (NIST verileri)
        T_inj = 293  # K (20°C varsayılan)
        mu_corrected = self.mu_ox * (T_inj / 273.15) ** 0.5  # Sıcaklık düzeltmesi
        
        Re = self.rho_ox * v_exit * d_h / mu_corrected
        
        # Fiziksel kontrol - Reynolds sayısı 1000-200000 arası olmalı
        if Re < 1000:
            print(f"UYARI: Düşük Reynolds sayısı ({Re:.0f}), laminar akış olabilir")
        elif Re > 200000:
            print(f"UYARI: Çok yüksek Reynolds sayısı ({Re:.0f}), tasarımı kontrol edin")
        
        # L/D ratio
        L_D = params['t_plate'] / d_h
        
        return {
            'type': 'showerhead',
            'n_holes': n_holes,
            'hole_diameter': d_h * 1000,  # mm
            'plate_thickness': params['t_plate'] * 1000,  # mm
            'L_D_ratio': L_D,
            'injection_area': A_inj * 1e6,  # mm²
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'pressure_drop': self.delta_P_inj,
            'warnings': self._check_warnings(v_exit, Re, L_D)
        }
    
    def _calculate_pintle(self):
        # Get parameters
        params = self.pintle_params
        D_outer = params['D_outer']
        D_pintle = params['D_pintle']
        
        # Calculate required gap
        delta_P_Pa = self.delta_P_inj * 1e5
        A_ann_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))
        
        # Annular flow area
        D_avg = (D_outer + D_pintle) / 2
        gap = A_ann_required / (np.pi * D_avg)
        
        # Check limits
        gap = max(0.0003, min(gap, 0.003))
        
        # Actual area and velocity
        A_ann = np.pi * D_avg * gap
        v_exit = np.sqrt(2 * delta_P_Pa / self.rho_ox)
        
        # Reynolds number
        Re = self.rho_ox * v_exit * gap / self.mu_ox
        
        return {
            'type': 'pintle',
            'outer_diameter': D_outer * 1000,  # mm
            'pintle_diameter': D_pintle * 1000,  # mm
            'gap': gap * 1000,  # mm
            'annular_area': A_ann * 1e6,  # mm²
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'pressure_drop': self.delta_P_inj,
            'warnings': self._check_warnings(v_exit, Re)
        }
    
    def _calculate_swirl(self):
        # Get parameters
        params = self.swirl_params
        n_slots = params['n_slots']
        
        # Calculate required flow area
        delta_P_Pa = self.delta_P_inj * 1e5
        A_slots_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))
        
        # Individual slot area
        A_slot = A_slots_required / n_slots
        
        # Slot dimensions
        if params['h'] is None:
            h = np.sqrt(A_slot / 2)
            w = 2 * h
        else:
            h = params['h']
            w = params['w']
        
        # Actual slot area
        A_slots = n_slots * w * h
        
        # Exit velocity
        v_exit = self.mdot_ox / (self.rho_ox * A_slots)
        
        # Effective area (accounting for swirl losses)
        A_eff = A_slots * 0.6
        
        # Exit orifice
        exit_orifice_area = A_eff
        spray_angle = 90  # degrees
        
        # Reynolds number (hydraulic diameter)
        D_h = 2 * w * h / (w + h)
        Re = self.rho_ox * v_exit * D_h / self.mu_ox
        
        return {
            'type': 'swirl',
            'n_slots': n_slots,
            'slot_width': w * 1000,  # mm
            'slot_height': h * 1000,  # mm
            'total_slot_area': A_slots * 1e6,  # mm²
            'effective_area': A_eff * 1e6,  # mm²
            'exit_orifice_area': exit_orifice_area * 1e6,  # mm²
            'spray_angle': spray_angle,
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'pressure_drop': self.delta_P_inj,
            'warnings': self._check_warnings(v_exit, Re)
        }
    
    def _optimize_showerhead_holes(self, A_required, params):
        """Optimize number of holes for showerhead injector"""
        def objective(N):
            N = int(N)
            if N < 4:
                return 1e6
            
            d_h = 2 * np.sqrt(A_required / (N * np.pi))
            
            penalty = 0
            
            # Diameter constraints
            if d_h < params['d_min']:
                penalty += 100 * (params['d_min'] - d_h) / params['d_min']
            elif d_h > params['d_max']:
                penalty += 100 * (d_h - params['d_max']) / params['d_max']
            
            # L/D constraint
            L_D = params['t_plate'] / d_h
            if L_D < 3 or L_D > 5:
                penalty += 10 * abs(L_D - 4)
            
            # Velocity deviation
            A_actual = N * np.pi * (d_h/2)**2
            v_actual = self.mdot_ox / (self.rho_ox * A_actual)
            if abs(v_actual - params['v_target']) > 10:
                penalty += (v_actual - params['v_target'])**2 / 100
            
            return penalty
        
        # Optimize
        result = minimize_scalar(objective, bounds=(4, 200), method='bounded')
        N_optimal = int(result.x)
        d_h_optimal = 2 * np.sqrt(A_required / (N_optimal * np.pi))
        
        return N_optimal, d_h_optimal
    
    def _check_warnings(self, v_exit, Re, L_D=None):
        warnings = []
        
        # Pressure drop check
        if self.delta_P_inj < 0.2 * self.P_c:
            warnings.append("Low pressure drop (<20% of chamber pressure)")
        
        # Exit velocity check
        if v_exit < 20 or v_exit > 50:
            warnings.append(f"Exit velocity ({v_exit:.1f} m/s) outside optimal range (20-50 m/s)")
        
        # Reynolds number check
        if Re < 4000:
            warnings.append(f"Low Reynolds number ({Re:.0f}) - laminar flow expected")
        
        # L/D check for showerhead
        if L_D is not None and (L_D < 3 or L_D > 5):
            warnings.append(f"L/D ratio ({L_D:.1f}) outside optimal range (3-5)")
        
        # Cavitation risk for liquids
        if self.ox_phase == 'liquid' and self.delta_P_inj > 0.5 * self.P_tank:
            warnings.append("Cavitation risk detected")
        
        # Flash boiling risk for N2O
        if self.ox_phase == 'liquid':
            P_vapor = 51  # bar at 20°C for N2O
            if self.P_c < P_vapor * 0.8:
                warnings.append("Flash boiling risk detected")
        
        return warnings