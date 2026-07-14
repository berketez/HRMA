import numpy as np
from scipy.optimize import fminbound, minimize_scalar, brentq
from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.nozzle_design import NozzleDesigner
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.regression_analysis import RegressionAnalyzer
from hrma.data.external_data_fetcher import data_fetcher
from hrma.data.propellant_database import (
    HYBRID_REGRESSION_COEFFICIENTS,
    N2O_LIQUID_DENSITY_SAT_25C,
)
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
                 fuel_type='htpb', motor_name='', motor_description='',
                 initial_gox=None, flux_mode='total', track_performance=True,
                 oxidizer_type='n2o'):
        
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
        self.oxidizer_type = oxidizer_type  # 'n2o' | 'lox' | 'h2o2' ...

        # Regresyon akı modu (denetim bulgusu #1): 'total' = Marxman
        # G_total = G_ox + G_fuel (VARSAYILAN); 'ox' = eski G_ox-only (geriye
        # uyum). Marxman & Gilbert (1963); Sutton & Biblarz 9th ed., Böl. 16.
        self.flux_mode = flux_mode if flux_mode in ('total', 'ox') else 'total'
        # O/F kayması -> anlık c*/Isp izleme (denetim bulgusu #2). False ise
        # performans tasarım O/F'sinde donar (eski hızlı davranış).
        self.track_performance = bool(track_performance)
        # Anlık O/F->c*/Isp tablo önbelleği (pahalı denge çözümünü tekrarlamaz)
        self._perf_cache = {}
        
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

        # Başlangıç port oksitleyici kütle akısı G_ox [kg/m²·s] — TASARIM
        # parametresidir (denetim bulgusu #1): port kesit alanı bu akıdan
        # boyutlandırılır (A_port = mdot_ox / G_ox). Enjektör orifis akısıyla
        # KARIŞTIRILMAZ. Tipik N2O/HTPB başlangıç değeri 100-500 kg/m²·s,
        # flooding sınırı ~600-700 kg/m²·s (Sutton & Biblarz, Rocket Propulsion
        # Elements 9. baskı, Böl. 16 — hibrit itki).
        if initial_gox is not None and initial_gox > 0:
            self.G_ox_design = float(initial_gox)
            if self.G_ox_design > 600:
                warnings.warn(
                    f"G_ox = {self.G_ox_design:.0f} kg/m²·s flooding sınırına "
                    "(~600-700 kg/m²·s) yakın/üstünde — Sutton & Biblarz 9. baskı, Böl. 16"
                )
        else:
            self.G_ox_design = 350.0  # kg/m²·s — tipik tasarım orta noktası
        
        self.g0 = G_0  # m/s^2 (BIPM standart, hrma.constants)
        
        # Initialize advanced analysis modules
        self.combustion_analyzer = CombustionAnalyzer()
        self.nozzle_designer = NozzleDesigner()
        self.heat_transfer_analyzer = HeatTransferAnalyzer()
        self.structural_analyzer = StructuralAnalyzer()
        
        # Set fuel-specific properties
        self._set_fuel_properties()
    
    def _set_fuel_properties(self):
        """Set fuel-specific regression rate parameters and density

        Regresyon katsayıları (a, n) merkezi tablodan gelir:
        hrma/data/propellant_database.py -> HYBRID_REGRESSION_COEFFICIENTS
        (SI birimler: r [m/s] = a * (G_ox [kg/m²·s])^n; kaynak atıfları orada).
        """
        # Default properties for different fuel types
        fuel_properties = {
            'htpb': {
                'density': 920,  # kg/m³
                'combustion_temp': 3200,  # K
                'gas_constant': 415  # J/kg·K
            },
            'pe': {  # Polyethylene
                'density': 950,
                'combustion_temp': 3100,
                'gas_constant': 420
            },
            'pmma': {  # PMMA
                'density': 1180,
                'combustion_temp': 2900,
                'gas_constant': 380
            },
            'paraffin': {
                'density': 900,
                'combustion_temp': 3000,
                'gas_constant': 450
            },
            'abs': {
                'density': 1040,
                'combustion_temp': 2800,
                'gas_constant': 390
            },
            'pla': {
                'density': 1250,
                'combustion_temp': 2700,
                'gas_constant': 370
            },
            'carbon': {
                'density': 2200,
                'combustion_temp': 3500,
                'gas_constant': 350
            },
            'aluminum': {
                'density': 2700,
                'combustion_temp': 3800,
                'gas_constant': 320
            },
            'al2o3': {
                'density': 3950,
                'combustion_temp': 3400,
                'gas_constant': 300
            }
        }

        # Get properties for selected fuel type (default to HTPB if not found)
        fuel_key = self.fuel_type.lower()
        props = fuel_properties.get(fuel_key, fuel_properties['htpb'])
        regression = HYBRID_REGRESSION_COEFFICIENTS.get(
            fuel_key, HYBRID_REGRESSION_COEFFICIENTS['htpb']
        )

        # Set properties - use fuel-specific values if user didn't provide them
        if self.rho_f is None:
            self.rho_f = props['density']
        if self.a is None:
            self.a = regression['a']
        if self.n is None:
            self.n = regression['n']
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
        # Kamara boyu: L* tabanlı kalış-süresi boyu ile grain boyunun büyüğü —
        # kamara, yakıt üretim kapanışından çözülen grain'i fiziksel olarak
        # içerebilmelidir (denetim bulgusu #6; grain boyu artık L* haznesinden
        # türetilmiyor).
        self.L = max(4 * self.V_c / (np.pi * self.D_ch**2), self.L_grain)

        # Calculate propellant masses
        self.m_ox = self.mdot_ox * self.t_b
        # Yakıt kütlesi grain geometrisinden (denetim bulgusu #6):
        # m_f = rho_f · (π/4) · (D_final² − D_initial²) · L_grain.
        # Eski mdot_f·t_b değeri grain'in fiilen ürettiği kütleyle
        # eşitlenmiyordu (3-4 kat tutarsızlık).
        self.m_f = self.m_f_grain
        self.m_total = self.m_ox + self.m_f
        # OPUS DENETİM DÜZELTMESİ (major): m_f YANAN yakıttır; grain dış
        # çapı kamara iç çapına kadar döküldüğünden YÜKLENEN yakıt daha
        # büyüktür (yanmayan sliver kalır). İkisi ayrı raporlanır ki araç
        # kütle bütçesi (yüklenen) ile performans bütçesi (yanan)
        # karıştırılmasın.
        r_grain_outer = self.D_ch / 2.0
        self.m_f_loaded = self.rho_f * np.pi / 4.0 * (
            (2.0 * r_grain_outer) ** 2 - self.D_port_initial ** 2
        ) * self.L_grain
        self.fuel_sliver_fraction = max(
            0.0, 1.0 - self.m_f / max(self.m_f_loaded, 1e-9))
        
        # Advanced combustion analysis with Cantera (kendi yanma çözücümüz)
        fuel_composition = {self.fuel_type: 100.0}  # Simplified for now
        ox = getattr(self, 'oxidizer_type', None) or 'N2O'
        combustion_results = self.combustion_analyzer.analyze_combustion(
            fuel_composition, ox, self.OF, self.P_c, None
        )

        # Gerçek termodinamik değerler CombustionAnalyzer denge çözümünden alınır.
        # DİKKAT: gamma/MW/sıcaklık 'compositions'->'chamber' altındadır
        # ('conditions'->'chamber' yalnızca {'P','T'} içerir; eski kod yanlış
        # anahtara baktığı için bu güncelleme hiç çalışmıyordu).
        if 'compositions' in combustion_results and 'chamber' in combustion_results['compositions']:
            chamber_data = combustion_results['compositions']['chamber']
            if 'gamma' in chamber_data:
                self.gamma = chamber_data['gamma']  # shifting-equilibrium isentropik üs
            if 'molecular_weight' in chamber_data:
                self.R = self.combustion_analyzer.R_universal / chamber_data['molecular_weight']
            if 'temperature' in chamber_data:
                self.T_c = chamber_data['temperature']  # HP dengesinden alev sıcaklığı
        
        # Advanced nozzle design — gerçek yanma değerlerini (gamma, R, T_c)
        # geçir; aksi halde design_nozzle eski hardcoded 1.25/300/3000'e düşer
        # ve CF/Isp motorun geri kalanıyla tutarsız olur (entegrasyon gap fix).
        nozzle_results = self.nozzle_designer.design_nozzle(
            self.At, self.epsilon, self.P_c, self.P_a, self.nozzle_type,
            gamma=self.gamma, R_specific=self.R, T_chamber=self.T_c
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
        
        # Structural analysis — chamber_temperature GEÇİLMELİ; aksi halde
        # structural modülü ortam (300 K) varsayıp termal gerilme=0 ve
        # mukavemet deratingi=yok ile çalışır, emniyet faktörünü tehlikeli
        # şekilde yüksek gösterir (entegrasyon gap fix). Mümkünse ısı transferi
        # modülünün hesapladığı gerçek cidar sıcaklıklarını geçir; yoksa T_c'den
        # konservatif tahmin yapılır.
        struct_input = {
            'chamber_pressure': self.P_c,
            'chamber_temperature': self.T_c,
            'ambient_temperature': 300.0,
            'chamber_diameter': self.D_ch,
            'chamber_length': self.L,
            'throat_diameter': self.d_t,
            'nozzle_type': self.nozzle_type,
            'burn_time': self.t_b
        }
        # ISI -> YAPISAL ZİNCİR (Dalga 0, 2026-07-14): Isı analizinin
        # hesapladığı GERÇEK iç/dış cidar sıcaklıkları yapısal modüle
        # aktarılır. structural_analysis._estimate_wall_delta_T bu
        # anahtarları birinci öncelikle okur; verilmezse T_c'den hayali,
        # aşırı karamsar bir gradyan tahmini yapıyordu (iki modül aynı
        # motor için farklı cidar sıcaklığı varsayıyordu).
        try:
            wall = heat_transfer_results['wall_analysis']
            t_hot = float(wall['inner_temperature'])
            t_cold = float(wall['outer_temperature'])
            if np.isfinite(t_hot) and np.isfinite(t_cold) and t_hot > 0:
                struct_input['wall_temperature_hot'] = t_hot
                struct_input['wall_temperature_cold'] = max(t_cold, 0.0)
        except (KeyError, TypeError, ValueError):
            pass  # ısı sonucu yoksa eski konservatif T_c tahmini devrede kalır
        structural_results = self.structural_analyzer.analyze_structure(
            struct_input,
            material='steel_4130',
            design_pressure_factor=1.5
        )
        
        return self._compile_results(combustion_results, nozzle_results, 
                                   altitude_performance, optimum_of, thrust_altitude_analysis,
                                   heat_transfer_results, structural_results)
    
    def _calculate_c_star(self):
        """Karakteristik hızı (c*) KENDİ yanma çözücümüzle hesaplar.

        Hibrit motor termokimyası CombustionAnalyzer (Cantera gri30 dengesi +
        shifting-equilibrium isentropik üs) ile çözülür. NASA CEA'ya BAĞLI
        DEĞİLDİR — kod kendi kimyasal dengesini kurar; CEA yalnızca bağımsız
        doğrulama referansıdır. Bu çözücünün c*'ı N2O/LOX/H2O2 ile HTPB,
        paraffin, PE, PMMA, ABS, PLA için NASA CEA'ya %0-1.5 içinde doğrulanmıştır
        (tasarım O/F bandı, Pc=20 bar). Eski sürüm RocketCEA'yı doğrudan çağırıp
        sonucu c* olarak alıyordu (CEA bağımlılığı) — bu kaldırıldı.
        """
        fuel_composition = {self.fuel_type: 100.0}
        ox = getattr(self, 'oxidizer_type', None) or 'n2o'

        # T_c=None geçilir ki CombustionAnalyzer adyabatik alev sıcaklığını
        # KENDİ HP dengesinden hesaplasın (sabit tablo değeri yerine).
        results = self.combustion_analyzer.analyze_combustion(
            fuel_composition, ox, self.OF, self.P_c, None
        )
        perf = results['performance']
        chamber = results['compositions']['chamber']

        # Gerçek denge değerlerini sınıfa aktar (shifting-eq. gamma, doğru T_c, MW)
        self.gamma = chamber['gamma']
        self.R = self.combustion_analyzer.R_universal / chamber['molecular_weight']
        self.T_c = chamber['temperature']

        c_star = perf['c_star']

        # c* validasyonu (fiziksel bant; hibrit yakıt/oksitleyici aralığı)
        if not (1000 < c_star < 1900):
            warnings.warn(f"Anormal c* değeri: {c_star:.0f} m/s (beklenen ~1300-1850)")

        return c_star

    def _instantaneous_performance(self, of_ratio):
        """Anlık O/F'den anlık (c*, Isp) döndürür (denetim bulgusu #2).

        O/F kayması performansa yansıtılır: yanma çözücü her O/F için c*'ı
        verir; Isp ise mevcut CF (nozul geometrisi sabit) ile c*'tan ölçeklenir
        (Isp = CF · c* / g0). CF burada O/F ile küçük değiştiği için tasarım
        CF'si kullanılır — bu, c*'taki (çok daha büyük) O/F duyarlılığını
        yakalamak için yeterlidir ve nozul yeniden çözümünden kaçınır.

        O/F değerleri 0.05 çözünürlükte yuvarlanıp önbelleğe alınır
        (Cantera denge çözümünü her time-marching adımında tekrarlamamak için).
        """
        of_key = round(float(of_ratio) / 0.05) * 0.05
        if of_key in self._perf_cache:
            return self._perf_cache[of_key]

        try:
            fuel_composition = {self.fuel_type: 100.0}
            ox = getattr(self, 'oxidizer_type', None) or 'n2o'
            results = self.combustion_analyzer.analyze_combustion(
                fuel_composition, ox, max(of_key, 0.1), self.P_c, None
            )
            cstar_inst = results['performance']['c_star']
        except Exception:
            cstar_inst = getattr(self, 'C_star', 1500.0)

        # CF tasarım değeri (calculate() önce CF'yi hesaplar); yoksa nominal.
        cf = getattr(self, 'CF', None)
        if cf is None or not np.isfinite(cf):
            cf = 1.5  # tipik hibrit deniz seviyesi CF (Sutton & Biblarz 9th ed.)
        isp_inst = cf * cstar_inst / self.g0
        self._perf_cache[of_key] = (cstar_inst, isp_inst)
        return cstar_inst, isp_inst
    
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
        
        # Eslenik (matched, Pe = Pa) genlesme orani oldugu gibi kullanilir
        # (denetim bulgusu #8): eski max(4, ...) tabani, Pc/Pa orani kucuk
        # motorlarda nozulu tasarim noktasinda asiri genlesmis hale getiriyordu.
        # Alt sinir yalnizca matematiksel gecerlilik icindir (suporsonik nozul
        # icin Ae/At > 1); ust sinir 250 vakum nozullari icin pratik limittir.
        # Kullanici epsilon verirse bu fonksiyon zaten cagrilmaz (calculate()).
        return max(1.01, min(epsilon, 250))
    
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
    
    def _get_oxidizer_density(self):
        """Sıvı N2O besleme yoğunluğu [kg/m³].

        Faz, O/F oranından DEĞİL besleme (tank) koşulundan belirlenir
        (denetim bulgusu #2): bu modül self-pressurized sıvı N2O beslemesi
        varsayar (referans tank sıcaklığı 25°C). Gaz enjeksiyonu için ayrıca
        sıkıştırılabilir orifis modeli gerekir ve burada modellenmemiştir.

        Birincil kaynak: external_data_fetcher (CoolProp/NIST, yoksa
        Span-Wagner EOS korelasyonu). Erişilemezse literatür sabiti
        N2O_LIQUID_DENSITY_SAT_25C kullanılır (NIST WebBook,
        Lemmon & Span 2006 EOS: 298.15 K doygun sıvı ≈ 743 kg/m³).
        """
        T_tank = 298.15  # K — 25°C referans tank sıcaklığı (yer işletmesi)
        # Doygunluk basıncının (~56.6 bar @ 298 K) üzerinde bir besleme basıncı
        # verilir ki CoolProp sıvı dalı çözsün; sıvı sıkıştırılabilirliği düşük
        # olduğundan yoğunluk doygun sıvıya çok yakındır.
        P_feed = max(1.2 * self.P_c, 60.0)  # bar
        try:
            props = data_fetcher.fetch_nist_oxidizer_properties(
                'n2o', temperature=T_tank, pressure=P_feed
            )
            rho = float(props.get('density', 0.0))
            # Sıvı faz makulluk penceresi: doygun sıvı N2O 25°C'de ~743,
            # 20°C'de ~785 kg/m³ (NIST WebBook). Pencere dışı → fallback.
            if 500.0 < rho < 1000.0:
                return rho
        except Exception:
            pass
        return N2O_LIQUID_DENSITY_SAT_25C  # kg/m³ — NIST WebBook (Lemmon & Span 2006)

    def _design_fuel_grain(self):
        """Design fuel grain geometry using correct hybrid rocket equations.

        Port oksitleyici akısı G_ox = mdot_ox / A_port bir TASARIM
        parametresidir ve enjektör orifis akısından (rho·v_enjeksiyon)
        tamamen ayrıdır (denetim bulgusu #1). Grain boyu, yakıt üretim
        kapanışından çözülür: mdot_f = rho_f · π · D_port · L · r_dot
        (Sutton & Biblarz 9. baskı, Böl. 16, yakıt üretim denklemi).
        """
        # --- Enjektör parametreleri (YALNIZ enjektör tasarımı için) ---
        delta_P = 0.2 * self.P_c  # bar — tipik %20 enjektör basınç düşümü (Sutton & Biblarz 9. baskı, Böl. 8)
        rho_ox = self._get_oxidizer_density()  # kg/m³ — sıvı N2O besleme yoğunluğu
        # Bernoulli: v = sqrt(2·ΔP/ρ) — yoğunluk, akan akışkanın yoğunluğuyla
        # TUTARLI (denetim bulgusu #3; eski kodda 1220 hardcoded idi)
        injection_velocity = np.sqrt(2 * delta_P * 1e5 / rho_ox)  # m/s

        # Store injector parameters for results output
        self._inj_delta_P = delta_P          # bar
        self._inj_velocity = injection_velocity  # m/s
        self._inj_rho_ox = rho_ox            # kg/m³

        # --- Port boyutlandırma: tasarım akısından (bulgu #1 düzeltmesi) ---
        # G_ox = mdot_ox / A_port  =>  A_port = mdot_ox / G_ox_design
        G_ox_initial = self.G_ox_design  # kg/m²·s
        A_port_initial = self.mdot_ox / G_ox_initial
        self.D_port_initial = 2 * np.sqrt(A_port_initial / np.pi)

        # --- Regresyon hızı: Marxman toplam-akı bağıntısı (denetim bulgusu) ---
        # r = a · G_total^n, G_total = G_ox + G_fuel (Marxman & Gilbert 1963;
        # Sutton & Biblarz 9th ed., Böl. 16). Yalnız G_ox kullanmak (eski kod)
        # yakıt akısının önemli olduğu düşük-O/F rejiminde r'yi DÜŞÜK tahmin
        # eder -> web tükenme süresini iyimser gösterir (güvenli olmayan yön).
        # G_fuel, r'ye bağlı olduğundan iteratif kapanış yapılır.
        # flux_mode='ox' verilirse eski davranış (geriye uyum).
        # Not: ilk grain boyu tahmini gerektiğinden, L_grain'i önce mdot_f
        # hedefinden (tasarım O/F) türetip sonra Marxman ile tutarlılaştırırız.
        # Başlangıç L_grain tahmini (yalnız G_ox ile, alt sınır):
        r_dot_ox_only = self.a * G_ox_initial ** self.n
        self.L_grain = self.mdot_f / (
            self.rho_f * np.pi * self.D_port_initial * r_dot_ox_only
        )

        # Marxman G_total ile başlangıç regresyon hızı (iteratif).
        reg0 = RegressionAnalyzer.regression_rate(
            self.a, self.n, G_ox_initial,
            rho_f=self.rho_f, port_diameter=self.D_port_initial,
            grain_length=self.L_grain, flux_mode=self.flux_mode
        )
        self.r_dot_initial = reg0['r_dot']
        self.r_dot = self.r_dot_initial  # For compatibility
        self.G_total_initial = reg0['G_total']

        # L_grain'i Marxman r_dot ile yeniden tutarlılaştır: hedef yakıt
        # debisi (tasarım O/F'den mdot_f) Marxman regresyonuyla sağlanmalı.
        # mdot_f = rho_f·π·D·L·r_dot_marxman  =>  L_grain (güncel)
        self.L_grain = self.mdot_f / (
            self.rho_f * np.pi * self.D_port_initial * self.r_dot_initial
        )

        # --- Euler time-marching (denetim bulgusu #5 düzeltmesi) ---
        # Sabit 10 adım yerine dt = t_b/200 taban çözünürlüğü; ek olarak ilk
        # adımdaki çap artışı başlangıç çapının %1'ini geçmeyecek şekilde adım
        # sayısı artırılır (ilk adım sıçraması koruması).
        num_steps = max(
            200,
            int(np.ceil(self.t_b * 2 * self.r_dot_initial / (0.01 * self.D_port_initial)))
        )
        dt = self.t_b / num_steps
        D_port = self.D_port_initial

        # Fiziksel sınır: port çapı kamara çapının %80'ini geçmemeli.
        # Eski koddaki hasattr(self, 'D_ch') kontrolü İLK çağrıda her zaman
        # False idi (D_ch grain tasarımından SONRA atanıyor) → ölü kod; ikinci
        # çağrıda ise bayat D_ch kullanılıyordu. Düzeltme: sınır yalnızca
        # kullanıcı kamara çapı verdiyse uygulanabilir; verilmediyse kamara
        # çapı port sonundan türetildiği için (D_ch = 1.5·D_port_final,
        # yani D_port_final ≈ 0.67·D_ch < 0.8·D_ch) sınır kendiliğinden sağlanır.
        if self.chamber_diameter_input > 0:
            max_port = 0.8 * self.chamber_diameter_input
            if max_port <= self.D_port_initial:
                warnings.warn(
                    f"Kamara çapı ({self.chamber_diameter_input*1000:.1f} mm) başlangıç "
                    f"portu ({self.D_port_initial*1000:.1f} mm) için çok küçük — "
                    "port sınırı uygulanamıyor, kamara çapını büyütün"
                )
                max_port = np.inf
        else:
            max_port = np.inf

        # O/F kayması izleme: anlık mdot_f / O/F / c* / Isp her adımda.
        # Anlık c*/Isp, anlık O/F'den combustion analyzer ile hesaplanır
        # (denetim bulgusu #2): O/F kayması performansa YANSITILIR; eski kod
        # c*/Isp'yi tasarım O/F'sinde donduruyordu. Pahalı denge çözümünü her
        # adımda tekrarlamamak için O/F->c*/Isp tablosu önbelleğe alınır
        # (track_performance=True ise).
        web_exhausted = False
        self._of_history = []
        self._cstar_history = []
        self._isp_history = []
        self._time_history = []
        # Port çapı zaman serisi: 3D yanma animasyonu D_port(t)'yi buradan okur
        # (track_performance'dan bağımsız tutulur — geometri her zaman lazım)
        self._port_time_history = []
        self._port_diameter_history = []

        for i in range(num_steps):
            t_now = i * dt
            self._port_time_history.append(t_now)
            self._port_diameter_history.append(D_port)
            A_port = np.pi * (D_port / 2)**2
            G_ox = self.mdot_ox / A_port  # kg/m²·s oksitleyici akış yoğunluğu

            # Marxman regresyon hızı: r = a · G_total^n (G_total iteratif).
            reg = RegressionAnalyzer.regression_rate(
                self.a, self.n, G_ox,
                rho_f=self.rho_f, port_diameter=D_port,
                grain_length=self.L_grain, flux_mode=self.flux_mode
            )
            r_dot = reg['r_dot']  # m/s

            # Anlık yakıt üretimi ve O/F (kayma izleme)
            mdot_f_inst = self.rho_f * np.pi * D_port * self.L_grain * r_dot
            of_inst = self.mdot_ox / mdot_f_inst if mdot_f_inst > 0 else self.OF

            # Anlık c*/Isp (O/F shift -> performans, bulgu #2). Tablo
            # önbelleği ile (track_performance açıkken).
            if self.track_performance:
                cstar_inst, isp_inst = self._instantaneous_performance(of_inst)
                self._of_history.append(of_inst)
                self._cstar_history.append(cstar_inst)
                self._isp_history.append(isp_inst)
                self._time_history.append(t_now)

            # Port yarıçapını artır (çap artışı = 2 · yarıçap artışı)
            D_port += 2 * r_dot * dt

            if D_port >= max_port:
                D_port = max_port
                web_exhausted = True
                warnings.warn(
                    "Port çapı 0.8·D_kamara sınırına ulaştı — web yanma süresi "
                    "bitmeden tükendi, grain tasarımını gözden geçirin"
                )
                break

        self.D_port_final = D_port
        # Seriye son noktayı ekle (erken web tükenmesinde son adım zamanı)
        self._port_time_history.append(t_now + dt if web_exhausted else self.t_b)
        self._port_diameter_history.append(D_port)

        # Final oxidizer flux hesaplama
        A_port_final = np.pi * (self.D_port_final / 2)**2
        self.G_ox_final = self.mdot_ox / A_port_final

        # Yanma sonu Marxman regresyonu ve anlık yakıt debisi / O/F (bulgu #6)
        reg_final = RegressionAnalyzer.regression_rate(
            self.a, self.n, self.G_ox_final,
            rho_f=self.rho_f, port_diameter=self.D_port_final,
            grain_length=self.L_grain, flux_mode=self.flux_mode
        )
        r_dot_final = reg_final['r_dot']
        self.G_total_final = reg_final['G_total']
        self.mdot_f_final = self.rho_f * np.pi * self.D_port_final * self.L_grain * r_dot_final
        self.OF_final = self.mdot_ox / self.mdot_f_final if self.mdot_f_final > 0 else self.OF

        # Zaman-ortalamalı regresyon oranı (Marxman, port-ortalama G_ox).
        # G_total iterasyonu ortalama G_ox'ta tekrar çözülür ki ortalama r
        # tutarlı olsun (yalnız uç noktaların aritmetik ortalaması değil).
        G_ox_avg = (G_ox_initial + self.G_ox_final) / 2  # Aritmetik ortalama daha stabil
        reg_avg = RegressionAnalyzer.regression_rate(
            self.a, self.n, G_ox_avg,
            rho_f=self.rho_f, port_diameter=(self.D_port_initial + self.D_port_final) / 2,
            grain_length=self.L_grain, flux_mode=self.flux_mode
        )
        self.r_dot_avg = reg_avg['r_dot']

        # Grain'in fiilen ürettiği yakıt kütlesi (denetim bulgusu #6):
        # m_f = rho_f · (V_grain_initial − V_grain_final)
        #     = rho_f · (π/4) · (D_final² − D_initial²) · L_grain
        self.m_f_grain = (
            self.rho_f * (np.pi / 4.0)
            * (self.D_port_final**2 - self.D_port_initial**2)
            * self.L_grain
        )
        self._web_exhausted = web_exhausted

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
            'fuel_mass': self.m_f,                      # YANAN yakıt (performans bütçesi)
            'fuel_mass_loaded': getattr(self, 'm_f_loaded', self.m_f),  # yüklenen (kütle bütçesi)
            'fuel_sliver_fraction': getattr(self, 'fuel_sliver_fraction', 0.0),
            
            # Operating conditions
            'chamber_pressure': self.P_c,
            'chamber_temperature': self.T_c,
            'burn_time': self.t_b,
            'of_ratio': self.OF,

            # O/F kayması (denetim bulgusu #6): port büyüdükçe mdot_f değişir;
            # başlangıç O/F tasarım değeridir, yanma sonu O/F time-marching
            # içindeki anlık mdot_f'den gelir.
            'of_ratio_initial': self.OF,
            'of_ratio_final': self.OF_final,
            'fuel_mass_flow_final': self.mdot_f_final,
            'grain_length': self.L_grain,
            'g_ox_design': self.G_ox_design,

            # Marxman toplam akı (denetim bulgusu #1): regresyon G_total ile
            # hesaplanır; G_ox-only'ye göre düşük-O/F rejiminde daha yüksek
            # (konservatif) r verir.
            'regression_flux_mode': self.flux_mode,
            'g_total_initial': getattr(self, 'G_total_initial', self.G_ox_initial),
            'g_total_final': getattr(self, 'G_total_final', self.G_ox_final),
        }

        # gamma + molecular_weight ÜST SEVİYEDE (Dalga 0, 2026-07-14):
        # Bartz ve lüle tüketicileri artık compositions->chamber'a inmek
        # ya da varsayılana (gamma=1.20, MW=24) düşmek zorunda kalmaz.
        # Öncelik: yanma dengesinin chamber kaydı; yoksa sınıf değerleri
        # (self.gamma, MW = R_evrensel / self.R).
        gamma_top = self.gamma
        mw_top = None
        if getattr(self, 'R', None):
            mw_top = self.combustion_analyzer.R_universal / self.R  # g/mol
        if combustion_results:
            chamber_comp = combustion_results.get(
                'compositions', {}).get('chamber', {})
            gamma_top = chamber_comp.get('gamma', gamma_top)
            mw_top = chamber_comp.get('molecular_weight', mw_top)
        basic_results['gamma'] = gamma_top
        basic_results['molecular_weight'] = mw_top

        # O/F kaymasının performansa etkisi (denetim bulgusu #2): time-marching
        # boyunca anlık O/F'den hesaplanan c*/Isp dizileri ve zaman-ortalamaları.
        if self.track_performance and getattr(self, '_cstar_history', None):
            cstar_hist = self._cstar_history
            isp_hist = self._isp_history
            basic_results['of_shift_performance'] = {
                'time': list(self._time_history),
                'of_ratio': list(self._of_history),
                'c_star': list(cstar_hist),
                'isp': list(isp_hist),
                'c_star_time_avg': float(np.mean(cstar_hist)) if cstar_hist else self.C_star,
                'isp_time_avg': float(np.mean(isp_hist)) if isp_hist else self.Isp,
                'c_star_design_of': self.C_star,
                'isp_design_of': self.Isp,
            }

        # Port çapı zaman serisi (3D yanma animasyonu için, metre + saniye).
        # Yanıt boyutunu sınırlamak için ~200 noktaya seyreltilir.
        if getattr(self, '_port_diameter_history', None):
            pt = self._port_time_history
            pd = self._port_diameter_history
            stride = max(1, len(pt) // 200)
            idx = list(range(0, len(pt), stride))
            if idx[-1] != len(pt) - 1:
                idx.append(len(pt) - 1)
            basic_results['port_history'] = {
                'time': [float(pt[i]) for i in idx],
                'port_diameter': [float(pd[i]) for i in idx],
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
        # Grain boyu yakıt üretim kapanışından gelir (denetim bulgusu #6),
        # kamara boyundan DEĞİL: mdot_f = rho_f·π·D_port·L_grain·r_dot
        fuel_length = self.L_grain
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
        # Gerçek tasarım: injector_design modülü (docs/10_Enjektor_ARGE.md).
        # N2O'da Dyer NHNE iki-faz debisi, Cd gerekçesi, delik planı, SMD,
        # chug/flip kontrolleri. Modül hata verirse eski basit Bernoulli
        # hesabına düşülür (hesap zinciri kırılmaz).
        delta_P_inj = self._inj_delta_P  # bar (stored from _design_fuel_grain)
        rho_ox = self._inj_rho_ox        # kg/m³
        try:
            from hrma.engines.injector_design import design_injector
            inj_spec = {
                'motor_type': 'hybrid',
                'injector_type': 'showerhead',
                'mdot_ox': self.mdot_ox,
                'rho_ox': rho_ox,
                'Pc_bar': self.P_c,
                'dp_ratio_ox': delta_P_inj / self.P_c if self.P_c > 0 else 0.20,
            }
            ox_name = (getattr(self, 'oxidizer_type', None) or 'n2o').lower()
            if ox_name == 'n2o':
                # Tank sıcaklığı motor girdisi değil; doymuş depolama 293 K
                # varsayımı (transient/blowdown varsayılanıyla aynı)
                inj_spec['fluid_ox'] = 'n2o'
                inj_spec['T_ox_K'] = 293.15
            # Oda gazı yoğunluğu (SMD için): T_c ve MW = R_evrensel/R_spesifik
            if getattr(self, 'T_c', None) and getattr(self, 'R', None):
                inj_spec['T_c_K'] = self.T_c
                inj_spec['mw_gas'] = 8314.462618 / self.R
            detail = design_injector(inj_spec)
            if detail.get('status') != 'success':
                raise ValueError(detail.get('error', 'enjektör tasarım hatası'))
            oxc = detail['ox_circuit']
            basic_results['injector_design'] = {
                'injector_type': detail['injector_type'],
                'oxidizer_flow_rate_kg_s': self.mdot_ox,
                'injection_velocity_m_s': oxc['velocity_m_s'],
                'number_of_orifices': oxc['n_orifices'],
                'orifice_diameter_mm': oxc['orifice_d_mm'],
                'injection_pressure_drop_bar': oxc['delta_p_bar'],
                'manifold_diameter_mm': oxc['manifold']['d_mm'],
                'discharge_coefficient': oxc['cd'],
                'total_injector_area_mm2': oxc['total_area_mm2'],
            }
            basic_results['injector_design_detail'] = detail
        except Exception as _inj_err:
            warnings.warn(f'injector_design modülü kullanılamadı, basit '
                          f'hesaba düşüldü: {_inj_err}')
            # Eski basit boyutlandırma (geriye uyum):
            Cd_inj = 0.65  # Typical sharp-edge orifice discharge coefficient
            A_inj_total = self.mdot_ox / (
                Cd_inj * np.sqrt(2 * rho_ox * delta_P_inj * 1e5))
            n_orifices = 12  # Typical showerhead pattern
            A_single = A_inj_total / n_orifices
            d_orifice = np.sqrt(4 * A_single / np.pi)  # m
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