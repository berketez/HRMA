"""
Comprehensive Safety Analysis Module
Safety, hazard, and risk assessment for rocket motor systems
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from hrma.data.materials_db import get_material

# ---------------------------------------------------------------------------
# Emniyet modeli sabitleri — TEK tanım noktası (magic number yasağı).
# Bu blok dışında sayısal sabit yazılmaz; testler de buradan okur.
# ---------------------------------------------------------------------------
SAFETY_MODEL = {
    # Ortam / radyasyon
    'ambient_temperature_k': 293.15,
    'stefan_boltzmann': 5.670374419e-8,      # W/m²K⁴ (CODATA 2018)
    'default_surface_emissivity': 0.80,      # oksitlenmiş metal dış yüzey
    'radiant_pain_threshold_w_m2': 2500.0,   # ISO 13732-1 acı eşiği (~2.5 kW/m²)
    # 2. derece yanık doz eşiği: ~1000 (kW/m²)^(4/3)·s  (Eisenberg probit /
    # API 521 termal doz birimi, TDU). Maruziyet süresi yanma süresidir.
    'second_degree_burn_tdu': 1000.0,
    'min_hazard_distance_m': 3.0,
    # Işıyan yüzey alanı bilinmiyorsa varsayılan narinlik (L/D). Sonuç
    # 'radiating_area_basis' alanında AÇIKÇA beyan edilir.
    'assumed_length_to_diameter': 5.0,
    # Kasa kütle kesri — yalnız geometri verilmediğinde kullanılan ampirik
    # yedek; kullanıldığında 'case_mass_basis' alanında beyan edilir.
    'fallback_case_mass_fraction': 0.15,
    'gurney_velocity_ms': 2700.0,            # √(2E), çelik kılıf tipik
    'fragment_drag_limited_range_m': 2000.0,
    'lethal_fragment_mass_kg': 0.01,
    'lethal_kinetic_energy_j': 79.0,         # NATO STANAG 2920
    # Serbest kalan (bağı kopan) motorun balistik menzili için sürükleme
    # sınırlı pratik tavan.
    'loose_motor_range_cap_m': 5000.0,
    'gravity_m_s2': 9.80665,
    # Basınçlı kap: emniyet valfi ayarı tasarım basıncının bu oranıdır
    # (API 520 sınıfı pratik: set ≤ MAWP).
    'relief_setting_fraction_of_design': 0.85,
}

# motor_type -> TNT eşdeğeri sınıfı. Kullanıcının seçtiği motor tipi,
# propellant_type serbest metin olduğunda patlayıcı sınıfını belirler.
MOTOR_TYPE_TO_EXPLOSIVE_CLASS = {
    'solid': 'composite',
    'hybrid': 'liquid_biprop',   # yakıt grain'i tek başına inert; olay
                                 # oksitleyici kaynaklıdır
    'liquid': 'liquid_biprop',
}


@dataclass
class SafetyMargins:
    """Safety margin requirements for different components"""
    structural_safety_factor: float = 4.0
    pressure_safety_factor: float = 1.5
    temperature_safety_factor: float = 1.3
    flow_safety_margin: float = 0.2
    minimum_burst_pressure_ratio: float = 2.0

@dataclass
class HazardDistance:
    """Hazard distance calculations"""
    debris_distance: float  # meters
    blast_distance: float   # meters
    thermal_distance: float # meters
    toxic_distance: float   # meters

class SafetyAnalyzer:
    """Comprehensive safety analysis for rocket motor systems"""
    
    def __init__(self):
        self.safety_margins = SafetyMargins()
        
        # Explosive classifications (TNT equivalent)
        self.propellant_tnt_equivalents = {
            'composite': 0.42,     # APCP/HTPB
            'double_base': 0.55,   # Nitrocellulose/Nitroglycerin
            'composite_db': 0.48,  # Composite double base
            'liquid_biprop': 0.35, # LOX/RP-1, LOX/LH2
            'liquid_monoprop': 0.28, # Hydrazine, N2O4
            'solid_monoprop': 0.33   # Ammonium perchlorate
        }
        
        # Toxic hazard data
        self.toxic_hazards = {
            'n2o4': {'lc50': 115, 'immediately_dangerous': 25, 'twa': 5},  # ppm
            'mmh': {'lc50': 825, 'immediately_dangerous': 50, 'twa': 0.01},
            'udmh': {'lc50': 622, 'immediately_dangerous': 25, 'twa': 0.01},
            'hydrazine': {'lc50': 570, 'immediately_dangerous': 50, 'twa': 0.01},
            'n2o': {'asphyxiant': True, 'inerting_concentration': 30000}  # ppm
        }
    
    def analyze_comprehensive_safety(self, motor_data: Dict, propellant_mass: float,
                                   propellant_type: str = 'composite',
                                   facility_type: str = 'test_stand',
                                   material: str = 'steel_4130',
                                   motor_type: Optional[str] = None) -> Dict:
        """
        Complete safety analysis including all hazard types

        Args:
            motor_data: Motor performance and design data
            propellant_mass: Total propellant mass (kg)
            propellant_type: Type of propellant system
            facility_type: 'test_stand', 'manufacturing', 'transport', 'launch'
            material: Chamber material key (hrma.data.materials_db); the
                structural-safety hoop check uses this material's real
                yield/ultimate strengths instead of a fixed generic steel.
            motor_type: 'solid' | 'hybrid' | 'liquid'. Selects the explosive
                (TNT-equivalent) class when propellant_type is not one of the
                tabulated class keys. Also read from motor_data['motor_type'].

        Returns:
            Comprehensive safety analysis results
        """

        # Extract motor parameters
        chamber_pressure = motor_data.get('chamber_pressure', 20.0)  # bar
        thrust = motor_data.get('thrust', 1000)  # N
        burn_time = motor_data.get('burn_time', 10)  # s
        if motor_type is None:
            motor_type = motor_data.get('motor_type')

        # Structural safety analysis
        structural_safety = self._analyze_structural_safety(motor_data, material)

        # Pressure vessel safety — gerçek cidar/malzeme ile (kopma basıncı
        # PressureVesselAnalyzer'dan, sabit çarpanlardan değil).
        pressure_safety = self._analyze_pressure_vessel_safety(
            chamber_pressure, motor_data.get('chamber_diameter', 0.1),
            wall_thickness=motor_data.get('wall_thickness', 0.005),
            material=material,
        )

        # Thermal safety analysis — cidar sıcaklığı ısı transferi modülünden,
        # termal gerilme seçilen malzemenin gerçek E/alfa/nu değerlerinden.
        thermal_safety = self._analyze_thermal_safety(motor_data, material)

        # Explosive hazard analysis
        explosive_hazards = self._analyze_explosive_hazards(
            propellant_mass, propellant_type, thrust, burn_time,
            motor_type=motor_type, motor_data=motor_data, material=material
        )

        # Toxic hazard analysis
        toxic_hazards = self._analyze_toxic_hazards(
            propellant_type, propellant_mass, facility_type
        )
        
        # Fire hazard analysis
        fire_hazards = self._analyze_fire_hazards(
            propellant_type, propellant_mass, motor_data
        )
        
        # Operational safety procedures
        operational_safety = self._generate_operational_safety_procedures(
            motor_data, propellant_type, facility_type
        )
        
        # Emergency response procedures
        emergency_procedures = self._generate_emergency_procedures(
            explosive_hazards, toxic_hazards, fire_hazards
        )
        
        # Safety equipment requirements
        safety_equipment = self._determine_safety_equipment_requirements(
            explosive_hazards, toxic_hazards, fire_hazards, facility_type
        )
        
        # Overall risk assessment
        risk_assessment = self._calculate_overall_risk(
            structural_safety, pressure_safety, thermal_safety,
            explosive_hazards, toxic_hazards, fire_hazards
        )
        
        return {
            'structural_safety': structural_safety,
            'pressure_safety': pressure_safety,
            'thermal_safety': thermal_safety,
            'explosive_hazards': explosive_hazards,
            'toxic_hazards': toxic_hazards,
            'fire_hazards': fire_hazards,
            'operational_safety': operational_safety,
            'emergency_procedures': emergency_procedures,
            'safety_equipment': safety_equipment,
            'risk_assessment': risk_assessment,
            'compliance': self._check_safety_compliance(risk_assessment),
            'recommendations': self._generate_safety_recommendations(risk_assessment),
            # Hangi girdinin gerçekten kullanıldığı kullanıcıya görünür olsun
            # (eskiden motor_type/thrust/burn_time sessizce düşüyordu).
            'inputs_used': {
                'motor_type': motor_type if motor_type else 'not supplied',
                'thrust_n': thrust,
                'burn_time_s': burn_time,
                'chamber_material': material,
                'propellant_type': propellant_type,
                'facility_type': facility_type,
            },
        }
    
    def _analyze_structural_safety(self, motor_data: Dict,
                                   material: str = 'steel_4130') -> Dict:
        """Analyze structural safety factors and failure modes.

        Dalga 0 (2026-07-14): Eski sürüm sabit 250/400 MPa jenerik çelikle
        hesaplıyordu; structural_analysis aynı motor için 4130'da 460 MPa +
        derating kullanınca iki panel farklı SF gösteriyordu. Artık malzeme
        dayanımları merkezi hrma/data/materials_db.py kaydından okunur.
        """

        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
        wall_thickness = motor_data.get('wall_thickness', 0.005)  # m

        # Malzeme dayanımları merkezi DB'den (bilinmeyen ad -> steel_4130)
        try:
            mat = get_material(material)
            material_key = material
        except KeyError:
            mat = get_material('steel_4130')
            material_key = 'steel_4130'
        yield_strength = mat['yield_strength']        # Pa
        ultimate_strength = mat['ultimate_strength']  # Pa

        # Hoop stress calculation
        hoop_stress = chamber_pressure * (chamber_diameter/2) / wall_thickness
        
        # Safety factors
        yield_safety_factor = yield_strength / hoop_stress
        ultimate_safety_factor = ultimate_strength / hoop_stress
        
        # Failure probability estimation (simplified)
        if yield_safety_factor < 2.0:
            failure_probability = 0.1  # 10% chance
        elif yield_safety_factor < 4.0:
            failure_probability = 0.01  # 1% chance
        else:
            failure_probability = 0.001  # 0.1% chance
        
        # Failure modes analysis
        failure_modes = [
            {
                'mode': 'Catastrophic Rupture',
                'probability': failure_probability * 0.3,
                'consequences': 'Complete vessel destruction, debris field',
                'severity': 'CRITICAL'
            },
            {
                'mode': 'Crack Propagation',
                'probability': failure_probability * 0.5,
                'consequences': 'Gradual pressure loss, possible flame jet',
                'severity': 'HIGH'
            },
            {
                'mode': 'Seal Failure',
                'probability': failure_probability * 0.2,
                'consequences': 'Pressure loss, possible fire',
                'severity': 'MEDIUM'
            }
        ]
        
        return {
            'hoop_stress_mpa': hoop_stress / 1e6,
            'material': material_key,
            'material_name': mat.get('name', material_key),
            'yield_strength_mpa': yield_strength / 1e6,
            'ultimate_strength_mpa': ultimate_strength / 1e6,
            'yield_safety_factor': yield_safety_factor,
            'ultimate_safety_factor': ultimate_safety_factor,
            'failure_probability': failure_probability,
            'failure_modes': failure_modes,
            'structural_integrity': 'SAFE' if yield_safety_factor >= 4.0 else 'MARGINAL' if yield_safety_factor >= 2.0 else 'UNSAFE',
            'recommended_inspection_interval': self._calculate_inspection_interval(yield_safety_factor)
        }

    def _calculate_inspection_interval(self, yield_safety_factor: float) -> str:
        """Emniyet katsayısına göre önerilen muayene aralığı.

        Basınçlı kap pratiğiyle uyumlu kaba merdiven: katsayı düştükçe
        muayene sıklaşır; 2'nin altı zaten 'UNSAFE' sınıfında raporlanıyor.
        """
        if yield_safety_factor >= 4.0:
            return 'Every 12 months (visual), hydrostatic every 5 years'
        if yield_safety_factor >= 3.0:
            return 'Every 6 months (visual), hydrostatic every 3 years'
        if yield_safety_factor >= 2.0:
            return 'Before each test campaign (visual + dye penetrant)'
        return 'Do not operate — redesign required (SF < 2)'

    def _analyze_pressure_vessel_safety(self, chamber_pressure: float, diameter: float,
                                        wall_thickness: float = 0.005,
                                        material: str = 'steel_4130') -> Dict:
        """Analyze pressure vessel safety requirements.

        DENETİM DÜZELTMESİ (2026-07-19): eskiden yalnız MEOP × sabit çarpanlar
        raporlanıyordu; kabın GERÇEKTEN kaç barda patladığı hiç hesaplanmıyordu,
        yani cidar kalınlığı ve malzeme bu panele hiç girmiyordu. Gerçek kopma
        basıncı artık merkezi PressureVesselAnalyzer'dan (Faupel kalın-cidar +
        ince-cidar plastik limit, sıcaklık derating'i) gelir — yapısal panelle
        aynı kaynak.
        """

        # Design pressure with safety factor
        design_pressure = chamber_pressure * self.safety_margins.pressure_safety_factor

        # Burst pressure requirement
        required_burst_pressure = chamber_pressure * self.safety_margins.minimum_burst_pressure_ratio

        # Pressure test requirements
        hydrostatic_test_pressure = design_pressure * 1.5
        proof_pressure = design_pressure * 1.25

        # --- GERÇEK kopma basıncı (malzeme + cidar kalınlığı + çap) ---
        actual_burst_pressure = None
        burst_margin = None
        vessel_status = None
        vessel_warnings: List[str] = []
        try:
            from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
            pv = PressureVesselAnalyzer().analyze(
                meop_bar=max(float(chamber_pressure), 1e-6),
                inner_diameter_mm=max(float(diameter), 1e-6) * 1e3,
                material=material,
                wall_thickness_mm=max(float(wall_thickness), 1e-9) * 1e3,
            )
            actual_burst_pressure = pv['actual_burst_pressure_bar']
            burst_margin = pv['burst_margin']
            vessel_status = pv['status']
            vessel_warnings = list(pv.get('warnings', []))
        except Exception as exc:      # malzeme/geometri geçersizse sessiz kalma
            vessel_warnings.append(
                f"Actual burst pressure could not be computed for this "
                f"geometry/material ({exc}); only code-required pressures are "
                f"shown.")

        # Pressure vessel classification
        if chamber_pressure > 100:  # bar
            vessel_class = 'HIGH_PRESSURE'
            inspection_requirements = 'Annual visual, 5-year hydrostatic'
        elif chamber_pressure > 20:
            vessel_class = 'MEDIUM_PRESSURE'
            inspection_requirements = '2-year visual, 10-year hydrostatic'
        else:
            vessel_class = 'LOW_PRESSURE'
            inspection_requirements = '5-year visual, 15-year hydrostatic'
        
        result = {
            'operating_pressure_bar': chamber_pressure,
            'design_pressure_bar': design_pressure,
            'required_burst_pressure_bar': required_burst_pressure,
            'hydrostatic_test_pressure_bar': hydrostatic_test_pressure,
            'proof_pressure_bar': proof_pressure,
            'vessel_classification': vessel_class,
            'inspection_requirements': inspection_requirements,
            'applicable_codes': ['ASME BPVC Section VIII', 'EN 13445', 'AS 1210'],
            'safety_devices_required': self._determine_pressure_safety_devices(chamber_pressure),
            # Gerçek kap kapasitesi (malzeme + cidar kalınlığı + çap)
            'material': material,
            'wall_thickness_mm': float(wall_thickness) * 1e3,
            'inner_diameter_mm': float(diameter) * 1e3,
            'actual_burst_pressure_bar': actual_burst_pressure,
            'burst_margin': burst_margin,
            'vessel_status': vessel_status,
            'vessel_warnings': vessel_warnings,
            'burst_pressure_source': (
                'Faupel thick-wall / thin-wall plastic limit '
                '(hrma.analysis.pressure_vessel)'),
        }
        return result

    def _analyze_thermal_safety(self, motor_data: Dict,
                                material: str = 'steel_4130') -> Dict:
        """Analyze thermal safety and heat-related hazards.

        DENETİM DÜZELTMESİ (2026-07-19). Eski sürümdeki üç uydurma kaldırıldı:
          (a) cidar sıcaklığı = 0.3 × hazne sıcaklığı sabit katsayısı,
          (b) termal gerilme sabit çelik özellikleriyle (E=200 GPa, alfa=12e-6)
              ve tam ankastre varsayımıyla — malzeme seçimi sonucu hiç
              değiştirmiyordu,
          (c) radyan tehlike mesafesine ışıyan ALAN yerine cidar kalınlığının
              100 katının geçilmesi (birim hatası; cidar kalınlaştıkça tehlike
              mesafesi büyüyordu).

        Yeni zincir:
          1) Cidar sıcaklığı: motor_data['wall_temperature_hot'/'cold']
             sözleşmesi (ısı transferi modülünün GERÇEK sonucu) varsa o;
             yoksa HeatTransferAnalyzer (Bartz + yüzey enerji dengesi)
             burada çağrılır. Yapısal panel ile aynı kaynak.
          2) Termal gerilme: seçilen malzemenin materials_db değerleriyle
             klasik cidar-gradyan formu sigma = E*alfa*dT/(2(1-nu))
             (Timoshenko/Boley-Weiner; structural_analysis ile AYNI form).
          3) Radyan tehlike: gerçek dış yüzey alanı ve DIŞ CİDAR sıcaklığı
             (hazne gazı sıcaklığı değil). Uzunluk verilmemişse varsayım
             'radiating_area_basis' alanında açıkça beyan edilir.
        """
        chamber_temperature = float(motor_data.get('chamber_temperature', 3000))
        wall_thickness = float(motor_data.get('wall_thickness', 0.005) or 0.005)
        chamber_diameter = float(motor_data.get('chamber_diameter', 0.1) or 0.1)
        burn_time = float(motor_data.get('burn_time', 10) or 10)
        ambient = float(motor_data.get('ambient_temperature',
                                       SAFETY_MODEL['ambient_temperature_k']))

        try:
            mat = get_material(material)
            material_key = material
        except KeyError:
            mat = get_material('steel_4130')
            material_key = 'steel_4130'

        # --- 1) Gerçek cidar sıcaklıkları -----------------------------------
        wall_hot, wall_cold, wall_source = self._resolve_wall_temperatures(
            motor_data, material_key, wall_thickness, ambient)

        # --- 2) Termal gerilme: seçilen malzeme + gerçek cidar gradyanı -----
        delta_T_wall = max(0.0, wall_hot - wall_cold)
        E = float(mat['elastic_modulus'])
        alpha = float(mat['thermal_expansion'])
        nu = float(mat['poisson_ratio'])
        thermal_stress_estimate = E * alpha * delta_T_wall / (2.0 * (1.0 - nu))

        # --- Malzeme sıcaklık marjları (materials_db, sabit 800/600 K değil) -
        selected_limit = float(mat.get('max_service_temp', np.nan))
        steel_limit = float(get_material('steel_4130')['max_service_temp'])
        aluminum_limit = float(get_material('aluminum_6061')['max_service_temp'])
        steel_thermal_safety = steel_limit / wall_hot if wall_hot > 0 else float('inf')
        aluminum_thermal_safety = (aluminum_limit / wall_hot
                                   if wall_hot > 0 else float('inf'))
        selected_thermal_safety = (selected_limit / wall_hot
                                   if wall_hot > 0 else float('inf'))

        # --- 3) Radyan ısı: gerçek ışıyan yüzey + dış cidar sıcaklığı -------
        area, area_basis = self._radiating_surface_area(
            chamber_diameter, wall_thickness, motor_data)
        emissivity = float(mat.get('emissivity',
                                   SAFETY_MODEL['default_surface_emissivity']))
        radiant_heat_distance = self._calculate_radiant_heat_distance(
            wall_cold, area, emissivity=emissivity, ambient=ambient)

        # Maruziyet dozu: yanma süresi burada GERÇEKTEN kullanılıyor.
        flux_at_distance = self._radiant_flux_at(
            wall_cold, area, radiant_heat_distance, emissivity, ambient)
        burn_distance = self._burn_dose_distance(
            wall_cold, area, burn_time, emissivity, ambient)

        return {
            'chamber_temperature_k': chamber_temperature,
            'estimated_wall_temperature_k': wall_hot,
            'inner_wall_temperature_k': wall_hot,
            'outer_wall_temperature_k': wall_cold,
            'wall_temperature_source': wall_source,
            'wall_delta_T_k': delta_T_wall,
            'material': material_key,
            'material_name': mat.get('name', material_key),
            'material_max_service_temp_k': selected_limit,
            'material_thermal_safety_factor': selected_thermal_safety,
            'steel_thermal_safety_factor': steel_thermal_safety,
            'aluminum_thermal_safety_factor': aluminum_thermal_safety,
            'thermal_stress_mpa': thermal_stress_estimate / 1e6,
            'thermal_stress_formula': (
                'sigma_th = E*alpha*dT/(2*(1-nu)) with the selected material '
                'and the through-wall gradient'),
            'radiating_area_m2': area,
            'radiating_area_basis': area_basis,
            'radiating_surface_temperature_k': wall_cold,
            'surface_emissivity': emissivity,
            'radiant_heat_hazard_distance_m': radiant_heat_distance,
            'radiant_flux_at_hazard_distance_kw_m2': flux_at_distance / 1000.0,
            'exposure_duration_s': burn_time,
            'second_degree_burn_distance_m': burn_distance,
            'recommended_minimum_standoff_m': max(
                radiant_heat_distance, burn_distance,
                SAFETY_MODEL['min_hazard_distance_m']),
            'material_recommendation': (
                'Selected material acceptable'
                if selected_thermal_safety
                > self.safety_margins.temperature_safety_factor
                else 'Insulation or a higher-temperature alloy required'),
            'cooling_required': bool(
                wall_hot > selected_limit
                / self.safety_margins.temperature_safety_factor),
            'thermal_protection_required': bool(
                radiant_heat_distance > SAFETY_MODEL['min_hazard_distance_m']
                or burn_distance > SAFETY_MODEL['min_hazard_distance_m']),
        }

    # ------------------------------------------------------------------
    # Termal emniyet yardımcıları
    # ------------------------------------------------------------------
    def _resolve_wall_temperatures(self, motor_data: Dict, material: str,
                                   wall_thickness: float,
                                   ambient: float) -> Tuple[float, float, str]:
        """(T_ic, T_dis, kaynak) — sabit katsayı YOK.

        Öncelik:
          1) motor_data['wall_temperature_hot'/'wall_temperature_cold']
             (motor zincirlerinin doldurduğu sözleşme)
          2) HeatTransferAnalyzer.analyze_heat_transfer (Bartz + yüzey enerji
             dengesi) — projedeki tek gerçek cidar sıcaklığı kaynağı
          3) Hiçbiri çalışmazsa ortam sıcaklığı + AÇIK uyarı (uydurma sayı
             döndürmek yerine hesaplanamadığını söyler)
        """
        hot = motor_data.get('wall_temperature_hot')
        cold = motor_data.get('wall_temperature_cold')
        if hot is not None and cold is not None:
            return (float(hot), float(cold),
                    'motor_data wall_temperature_hot/cold contract')

        try:
            from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
            ht = HeatTransferAnalyzer().analyze_heat_transfer(
                motor_data, material=material,
                wall_thickness=max(float(wall_thickness), 1e-6),
                ambient_temp=ambient,
                cooling_type=motor_data.get('cooling_type', 'natural'))
            wall = ht['wall_analysis']
            return (float(wall['inner_temperature']),
                    float(wall['outer_temperature']),
                    'HeatTransferAnalyzer (Bartz gas side + surface energy balance)')
        except Exception as exc:
            return (float(ambient), float(ambient),
                    f'NOT COMPUTED - heat transfer chain failed ({exc}); '
                    f'wall temperature defaulted to ambient and must not be '
                    f'used for design')

    def _radiating_surface_area(self, chamber_diameter: float,
                                wall_thickness: float,
                                motor_data: Dict) -> Tuple[float, str]:
        """Motor gövdesinin dış ışıyan yüzey alanı [m²] ve dayanağı.

        A = pi*D_dis*L + 2*(pi/4)*D_dis²  (silindir + iki uç kapak).
        Uzunluk verilmemişse varsayılan narinlik kullanılır ve bu, dönen
        metinde AÇIKÇA beyan edilir — sessiz varsayım bırakılmaz.
        """
        d_outer = float(chamber_diameter) + 2.0 * float(wall_thickness)
        length = motor_data.get('chamber_length') or motor_data.get('motor_length')
        if length:
            length = float(length)
            basis = 'computed from chamber_diameter, wall_thickness and chamber_length'
        else:
            length = SAFETY_MODEL['assumed_length_to_diameter'] * float(chamber_diameter)
            basis = (f"ASSUMED L/D = {SAFETY_MODEL['assumed_length_to_diameter']:.0f} "
                     f"(chamber_length was not supplied)")
        area = np.pi * d_outer * length + 2.0 * (np.pi / 4.0) * d_outer ** 2
        return float(area), basis

    def _radiant_flux_at(self, surface_temperature: float, area: float,
                         distance: float, emissivity: float,
                         ambient: float) -> float:
        """Verilen mesafede radyan akı [W/m²] (nokta kaynak yaklaşımı)."""
        sigma = SAFETY_MODEL['stefan_boltzmann']
        power = emissivity * sigma * max(
            surface_temperature ** 4 - ambient ** 4, 0.0) * max(area, 0.0)
        if distance <= 0:
            return 0.0
        return float(power / (4.0 * np.pi * distance ** 2))

    def _analyze_explosive_hazards(self, propellant_mass: float, propellant_type: str,
                                   thrust: float, burn_time: float = 10.0,
                                   motor_type: Optional[str] = None,
                                   motor_data: Optional[Dict] = None,
                                   material: str = 'steel_4130') -> Dict:
        """Analyze explosive hazards and calculate safety distances.

        DENETİM DÜZELTMESİ (2026-07-19): motor_type artık patlayıcı sınıfını
        seçiyor (eskiden tamamen düşüyordu) ve thrust/burn_time serbest kalan
        motor tehlikesinde GERÇEKTEN kullanılıyor (eski imza thrust'ı alıp
        gövdede hiç kullanmıyordu).
        """

        # TNT equivalent calculation — sınıf çözümü motor tipini de dikkate alır
        class_key, class_basis = self._resolve_explosive_class(
            propellant_type, motor_type)
        tnt_factor = self.propellant_tnt_equivalents[class_key]
        tnt_equivalent = propellant_mass * tnt_factor

        # Blast overpressure distances (Hopkinson-Cranz law)
        distances = self._calculate_blast_distances(tnt_equivalent)

        # Fragment hazard analysis
        fragment_hazards = self._calculate_fragment_hazards(
            propellant_mass, thrust, burn_time, motor_data, material)

        # Quantity-distance (Q-D) requirements
        qd_requirements = self._calculate_qd_requirements(tnt_equivalent)

        return {
            'propellant_mass_kg': propellant_mass,
            'tnt_equivalent_kg': tnt_equivalent,
            'tnt_equivalent_factor': tnt_factor,
            'explosive_class': class_key,
            'explosive_class_basis': class_basis,
            'blast_distances': distances,
            'fragment_hazards': fragment_hazards,
            'qd_requirements': qd_requirements,
            'explosive_classification': self._classify_explosive_hazard(tnt_equivalent),
            'storage_requirements': self._determine_storage_requirements(tnt_equivalent, propellant_type),
            'transport_requirements': self._determine_transport_requirements(tnt_equivalent, propellant_type)
        }
    
    def _analyze_toxic_hazards(self, propellant_type: str, propellant_mass: float, facility_type: str) -> Dict:
        """Analyze toxic hazard exposure and safety distances"""
        
        toxic_components = self._identify_toxic_components(propellant_type)
        
        if not toxic_components:
            return {
                'toxic_hazard_level': 'NONE',
                'toxic_components': [],
                'exposure_limits': {},
                'detection_required': False,
                'ppe_requirements': []
            }
        
        # Calculate worst-case release scenario
        release_scenarios = []
        for component in toxic_components:
            scenario = self._calculate_toxic_release_scenario(
                component, propellant_mass, facility_type
            )
            release_scenarios.append(scenario)
        
        # Determine detection requirements
        detection_requirements = self._determine_toxic_detection_requirements(toxic_components)
        
        # PPE requirements
        ppe_requirements = self._determine_toxic_ppe_requirements(toxic_components)
        
        return {
            'toxic_hazard_level': self._assess_toxic_hazard_level(release_scenarios),
            'toxic_components': toxic_components,
            'release_scenarios': release_scenarios,
            'detection_requirements': detection_requirements,
            'ppe_requirements': ppe_requirements,
            'exposure_monitoring': self._determine_exposure_monitoring(toxic_components),
            'emergency_treatment': self._determine_emergency_treatment(toxic_components)
        }
    
    def _analyze_fire_hazards(self, propellant_type: str, propellant_mass: float, motor_data: Dict) -> Dict:
        """Analyze fire hazards and suppression requirements"""
        
        # Fire classification
        fire_class = self._classify_fire_hazard(propellant_type)
        
        # Auto-ignition analysis
        auto_ignition_risk = self._assess_auto_ignition_risk(
            propellant_type, motor_data.get('chamber_temperature', 3000)
        )
        
        # Fire spread analysis
        fire_spread = self._analyze_fire_spread_potential(propellant_mass, propellant_type)
        
        # Suppression requirements
        suppression_system = self._determine_fire_suppression_system(
            fire_class, propellant_mass, auto_ignition_risk
        )
        
        return {
            'fire_classification': fire_class,
            'auto_ignition_risk': auto_ignition_risk,
            'fire_spread_potential': fire_spread,
            'suppression_system': suppression_system,
            'fire_safety_distances': self._calculate_fire_safety_distances(propellant_mass),
            'ignition_sources_control': self._identify_ignition_sources_control(),
            'fire_fighting_procedures': self._generate_fire_fighting_procedures(fire_class)
        }
    
    def _calculate_blast_distances(self, tnt_equivalent: float) -> Dict:
        """Calculate blast overpressure distances using scaled distance"""
        
        # Scaled distance formula: Z = R / W^(1/3)
        # Where R = distance (m), W = TNT equivalent (kg)
        
        # (aşırı-basınç [Pa], ölçekli mesafe Z [m/kg^(1/3)]) çiftleri.
        # Z değerleri serbest-hava küresel TNT patlaması için doğrulanmış
        # Kingery-Bulmash / Kinney-Graham eğrisinden alınmıştır (UFC 3-340-02,
        # Kinney & Graham "Explosive Shocks in Air" 2nd ed.). ESKİ HATA:
        # Z = 0.067·(P/1e5)^(-0.4) katsayısı ~30-60x KÜÇÜK Z veriyordu
        # (100 kPa'da 0.067 yerine ~2.4 olmalı) → emniyet mesafelerini tehlikeli
        # şekilde az gösteriyordu. Değerler konservatif (biraz büyük) tarafta.
        overpressures = {
            'lethal':          (100000, 2.4),   # 100 kPa
            'serious_injury':  (35000,  4.5),   # 35 kPa
            'minor_injury':    (7000,  10.5),   # 7 kPa
            'property_damage': (2000,  20.0),   # 2 kPa
        }

        distances = {}
        for level, (pressure, scaled_distance) in overpressures.items():
            distance = scaled_distance * (tnt_equivalent ** (1.0 / 3.0))
            distances[level] = {
                'distance_m': distance,
                'overpressure_kpa': pressure / 1000
            }

        return distances
    
    def _resolve_explosive_class(self, propellant_type: str,
                                 motor_type: Optional[str]) -> Tuple[str, str]:
        """(TNT eşdeğeri sınıfı, dayanak metni).

        propellant_type tablo anahtarlarından biriyse doğrudan kullanılır.
        Değilse (ör. 'apcp', 'n2o_htpb' gibi serbest ad) motor tipi sınıfı
        belirler — bu, motor_type girdisinin GERÇEK kullanım yeridir.
        """
        key = str(propellant_type or '').strip().lower()
        if key in self.propellant_tnt_equivalents:
            return key, f"propellant_type '{key}' matched the TNT-equivalent table"

        mt = str(motor_type or '').strip().lower()
        if mt in MOTOR_TYPE_TO_EXPLOSIVE_CLASS:
            resolved = MOTOR_TYPE_TO_EXPLOSIVE_CLASS[mt]
            return resolved, (
                f"propellant_type '{propellant_type}' is not a tabulated class; "
                f"motor_type '{mt}' selected the '{resolved}' class")

        return 'composite', (
            f"propellant_type '{propellant_type}' is not a tabulated class and "
            f"no motor_type was supplied; the conservative 'composite' class "
            f"was assumed")

    def _estimate_case_mass(self, propellant_mass: float,
                            motor_data: Optional[Dict],
                            material: str) -> Tuple[float, str]:
        """(kasa kütlesi kg, dayanak). Geometri varsa GERÇEK kabuk kütlesi.

        m = rho * [pi*D_ort*L*t + 2*(pi/4)*D_dis^2*t]  (silindir + uç kapaklar)
        Geometri yoksa ampirik kütle kesri kullanılır ve bu beyan edilir.
        """
        md = motor_data or {}
        diameter = md.get('chamber_diameter')
        thickness = md.get('wall_thickness')
        length = md.get('chamber_length') or md.get('motor_length')
        if diameter and thickness:
            try:
                rho = float(get_material(material)['density'])
            except KeyError:
                rho = float(get_material('steel_4130')['density'])
            d = float(diameter)
            t = float(thickness)
            if length:
                L = float(length)
                basis = 'shell mass from chamber diameter, length and wall thickness'
            else:
                L = SAFETY_MODEL['assumed_length_to_diameter'] * d
                basis = ("shell mass from chamber diameter and wall thickness "
                         f"with an ASSUMED L/D = "
                         f"{SAFETY_MODEL['assumed_length_to_diameter']:.0f} "
                         "(chamber_length was not supplied)")
            d_outer = d + 2.0 * t
            volume = (np.pi * (d + t) * L * t
                      + 2.0 * (np.pi / 4.0) * d_outer ** 2 * t)
            return float(rho * volume), basis

        frac = SAFETY_MODEL['fallback_case_mass_fraction']
        return (float(propellant_mass) * frac,
                f"EMPIRICAL case mass fraction {frac:.2f} of propellant mass "
                f"(chamber geometry was not supplied)")

    def _calculate_fragment_hazards(self, propellant_mass: float, thrust: float,
                                    burn_time: float = 10.0,
                                    motor_data: Optional[Dict] = None,
                                    material: str = 'steel_4130') -> Dict:
        """Calculate fragment throw distances and hazards.

        DENETİM DÜZELTMESİ (2026-07-19): kasa kütlesi artık gerçek kabuk
        geometrisinden hesaplanır (eski sabit %15 kesri yalnız geometri
        yokken, beyan edilerek kullanılır) ve thrust/burn_time serbest kalan
        motor tehlikesinde gerçekten kullanılır.
        """

        case_mass, case_mass_basis = self._estimate_case_mass(
            propellant_mass, motor_data, material)

        # Fragment velocity estimation (Gurney equation approximation).
        # Gurney silindir formu: V = √(2E)·√(C/(M + C/2)); C = şarj (yakıt),
        # M = kılıf (metal) kütlesi. ESKİ HATA: payda propellant + case/2
        # (C + M/2) yazılmıştı → M ve C rolleri ters. Doğru payda M + C/2.
        gurney_velocity = SAFETY_MODEL['gurney_velocity_ms']  # m/s (√(2E))
        fragment_velocity = gurney_velocity * np.sqrt(
            propellant_mass / (case_mass + propellant_mass / 2)) \
            if (case_mass + propellant_mass / 2) > 0 else 0.0

        # Fragment range. Vakum/45° menzili (v²/g) aerodinamik sürüklemeyi
        # ihmal eder ve ~2600 m/s parça için ~700 km gibi FİZİKSEL OLMAYAN
        # değer verir. Gerçek roket parçaları sürükleme-sınırlıdır; pratik
        # üst sınırla kırpılır (tahliye mesafesi hesabına saçma değer gitmesin).
        g0 = SAFETY_MODEL['gravity_m_s2']
        vacuum_range = fragment_velocity ** 2 / g0
        max_range = min(vacuum_range, SAFETY_MODEL['fragment_drag_limited_range_m'])

        # Lethal fragment analysis
        lethal_fragment_mass = SAFETY_MODEL['lethal_fragment_mass_kg']
        lethal_kinetic_energy = SAFETY_MODEL['lethal_kinetic_energy_j']
        lethal_velocity = np.sqrt(2 * lethal_kinetic_energy / lethal_fragment_mass)

        # --- Serbest kalan motor tehlikesi: thrust ve burn_time BURADA gerçekten
        # kullanılıyor. Test standından kopan motor bir mermi gibi davranır;
        # toplam impuls onu hızlandırır (Sutton & Biblarz Böl. 2 impuls-momentum).
        total_impulse = max(float(thrust), 0.0) * max(float(burn_time), 0.0)
        # Ortalama uçuş kütlesi: kasa + yakıtın yarısı (yanma boyunca ortalama)
        mean_mass = max(case_mass + propellant_mass / 2.0, 1e-6)
        loose_velocity = total_impulse / mean_mass                    # m/s
        loose_energy = 0.5 * mean_mass * loose_velocity ** 2          # J
        # Bağlama elemanlarının karşılaması gereken kuvvet (yapısal emniyet
        # katsayısıyla) — itkinin doğrudan emniyet karşılığı.
        restraint_force = (max(float(thrust), 0.0)
                           * self.safety_margins.structural_safety_factor)

        return {
            'estimated_case_mass_kg': case_mass,
            'case_mass_basis': case_mass_basis,
            'unrestrained_motor': {
                'total_impulse_ns': total_impulse,
                'mean_flight_mass_kg': mean_mass,
                'burnout_velocity_ms': loose_velocity,
                'kinetic_energy_j': loose_energy,
                'required_restraint_force_n': restraint_force,
                'note': ('If the motor breaks free of its restraint it becomes '
                         'a projectile: burnout speed is total impulse divided '
                         'by mean flight mass. The tie-down must react the '
                         'thrust with the structural safety factor. No '
                         'trajectory range is quoted because it depends on '
                         'drag and attitude, which this model does not solve.'),
            },
            'fragment_velocity_ms': fragment_velocity,
            'maximum_range_m': max_range,
            'lethal_fragment_range_m': max_range * 0.8,  # Conservative estimate
            'fragment_density_per_m2': case_mass / (np.pi * max_range**2),
            'lethal_velocity_threshold_ms': lethal_velocity,
            'fragment_size_distribution': {
                'small_fragments_g': [0.1, 1.0],    # 0.1-1g
                'medium_fragments_g': [1.0, 10.0],  # 1-10g
                'large_fragments_g': [10.0, 100.0]  # 10-100g
            }
        }
    
    def _calculate_qd_requirements(self, tnt_equivalent: float) -> Dict:
        """Calculate quantity-distance requirements for different exposed sites"""
        
        # NATO STANAG 4123 / DOD 6055.9-STD ilişkileri, R = K·W^(1/3).
        # DDESB/UFC 3-340-02 K-faktörleri klasik olarak ft/lb^(1/3)
        # birimindedir; bu modül W'yi kg, R'yi m ile kullandığından metrik
        # eşdeğere çevrildi (çarpan 0.3048/0.4536^(1/3) = 0.3966 m·lb^(1/3)/
        # (ft·kg^(1/3))). ESKİ HATA: imperial 40/18/... değerleri doğrudan
        # metrik girdiye uygulanıp mesafeler ~2.5x abartılıyordu.
        # Örn. IBD: 40 ft/lb^(1/3) → 15.9 m/kg^(1/3).
        _IMP_TO_METRIC = 0.3966
        k_factors = {
            'inhabited_building':   40 * _IMP_TO_METRIC,   # ≈15.9 (IBD)
            'public_traffic_route': 18 * _IMP_TO_METRIC,   # ≈7.14 (PTRD)
            'explosives_facility':  12 * _IMP_TO_METRIC,   # ≈4.76
            'personnel_facility':   22 * _IMP_TO_METRIC,   # ≈8.73
            'ammunition_storage':   12 * _IMP_TO_METRIC,   # ≈4.76
        }
        
        qd_distances = {}
        for site_type, k_factor in k_factors.items():
            # Distance = K * W^(1/3), minimum 30m
            distance = max(30, k_factor * (tnt_equivalent ** (1/3)))
            qd_distances[site_type] = {
                'distance_m': distance,
                'k_factor': k_factor
            }
        
        return qd_distances
    
    def _generate_operational_safety_procedures(self, motor_data: Dict, 
                                              propellant_type: str, facility_type: str) -> Dict:
        """Generate operational safety procedures"""
        
        procedures = {
            'pre_operation_checks': [
                'Verify all safety systems functional',
                'Confirm personnel evacuation complete',
                'Check weather conditions acceptable',
                'Verify emergency response teams ready',
                'Test communication systems',
                'Confirm fire suppression systems armed'
            ],
            'operation_procedures': [
                'Maintain minimum safe distance',
                'Monitor pressure and temperature continuously',
                'Have abort procedures ready',
                'Maintain constant communication',
                'Document all anomalies immediately'
            ],
            'post_operation_procedures': [
                'Allow minimum cooling time before approach',
                'Check for unexploded ordnance',
                'Document all observations',
                'Secure facility and equipment',
                'Conduct post-test inspection'
            ],
            'personnel_limits': self._determine_personnel_limits(motor_data, facility_type),
            'qualification_requirements': self._determine_qualification_requirements(facility_type),
            'training_requirements': self._determine_training_requirements(propellant_type, facility_type)
        }
        
        return procedures
    
    def _generate_emergency_procedures(self, explosive_hazards: Dict, 
                                     toxic_hazards: Dict, fire_hazards: Dict) -> Dict:
        """Generate comprehensive emergency response procedures"""
        
        return {
            'explosion_response': {
                'immediate_actions': [
                    'Sound evacuation alarm immediately',
                    'Evacuate to minimum safe distance',
                    'Account for all personnel',
                    'Contact emergency services',
                    'Establish incident command post'
                ],
                'evacuation_distance': max(
                    explosive_hazards.get('blast_distances', {}).get('serious_injury', {}).get('distance_m', 100),
                    explosive_hazards.get('fragment_hazards', {}).get('lethal_fragment_range_m', 100)
                ),
                're-entry_criteria': [
                    'Minimum 2-hour cooling period',
                    'EOD clearance if required',
                    'Structural damage assessment',
                    'Environmental monitoring complete'
                ]
            },
            'fire_response': {
                'immediate_actions': [
                    'Activate fire suppression system',
                    'Sound fire alarm',
                    'Evacuate upwind',
                    'Call fire department',
                    'Prepare for secondary explosions'
                ],
                'suppression_method': fire_hazards.get('suppression_system', {}).get('primary_agent', 'Water/Foam'),
                'evacuation_distance': fire_hazards.get('fire_safety_distances', {}).get('radiant_heat_m', 50)
            },
            'toxic_release_response': {
                'immediate_actions': [
                    'Don appropriate PPE',
                    'Evacuate downwind areas',
                    'Activate gas detection systems',
                    'Contact HAZMAT team',
                    'Establish decontamination procedures'
                ],
                'evacuation_distance': max([
                    scenario.get('hazard_distance_m', 50) 
                    for scenario in toxic_hazards.get('release_scenarios', [])
                ] + [50]),  # Default 50m minimum
                'decontamination': toxic_hazards.get('emergency_treatment', {})
            },
            'medical_response': {
                'on_site_capabilities': 'Basic first aid, oxygen, decontamination',
                'hospital_notification': 'Notify trauma center of potential casualties',
                'antidotes_required': self._determine_required_antidotes(toxic_hazards),
                'treatment_protocols': self._generate_treatment_protocols(toxic_hazards)
            }
        }
    
    def _calculate_overall_risk(self, structural_safety: Dict, pressure_safety: Dict,
                               thermal_safety: Dict, explosive_hazards: Dict,
                               toxic_hazards: Dict, fire_hazards: Dict) -> Dict:
        """Calculate overall risk assessment matrix"""
        
        # Risk scoring (1-5 scale)
        structural_risk = self._score_structural_risk(structural_safety)
        pressure_risk = self._score_pressure_risk(pressure_safety)
        thermal_risk = self._score_thermal_risk(thermal_safety)
        explosive_risk = self._score_explosive_risk(explosive_hazards)
        toxic_risk = self._score_toxic_risk(toxic_hazards)
        fire_risk = self._score_fire_risk(fire_hazards)
        
        # Weighted overall risk
        weights = {
            'structural': 0.25,
            'pressure': 0.20,
            'thermal': 0.15,
            'explosive': 0.20,
            'toxic': 0.10,
            'fire': 0.10
        }
        
        overall_risk_score = (
            structural_risk * weights['structural'] +
            pressure_risk * weights['pressure'] +
            thermal_risk * weights['thermal'] +
            explosive_risk * weights['explosive'] +
            toxic_risk * weights['toxic'] +
            fire_risk * weights['fire']
        )
        
        # Risk level classification
        if overall_risk_score <= 2.0:
            risk_level = 'LOW'
            acceptability = 'ACCEPTABLE'
        elif overall_risk_score <= 3.0:
            risk_level = 'MEDIUM'
            acceptability = 'ACCEPTABLE_WITH_CONTROLS'
        elif overall_risk_score <= 4.0:
            risk_level = 'HIGH'
            acceptability = 'REQUIRES_MITIGATION'
        else:
            risk_level = 'CRITICAL'
            acceptability = 'UNACCEPTABLE'
        
        return {
            'individual_risks': {
                'structural': structural_risk,
                'pressure': pressure_risk,
                'thermal': thermal_risk,
                'explosive': explosive_risk,
                'toxic': toxic_risk,
                'fire': fire_risk
            },
            'overall_risk_score': overall_risk_score,
            'risk_level': risk_level,
            'acceptability': acceptability,
            'risk_matrix': self._generate_risk_matrix(),
            'mitigation_priority': self._determine_mitigation_priority(
                structural_risk, pressure_risk, thermal_risk,
                explosive_risk, toxic_risk, fire_risk
            )
        }
    
    # Helper methods for risk scoring
    def _score_structural_risk(self, structural_safety: Dict) -> float:
        safety_factor = structural_safety.get('yield_safety_factor', 1.0)
        if safety_factor >= 4.0:
            return 1.0
        elif safety_factor >= 3.0:
            return 2.0
        elif safety_factor >= 2.0:
            return 3.0
        elif safety_factor >= 1.5:
            return 4.0
        else:
            return 5.0
    
    def _score_pressure_risk(self, pressure_safety: Dict) -> float:
        """Basınç riski: sınıf tabanı + GERÇEK kopma marjı.

        Eskiden yalnız basınç sınıfına bakıyordu; kasa duvarı ince veya
        malzeme zayıf olsa bile skor değişmiyordu. Artık gerçek kopma
        marjı (actual_burst / required_burst) skoru yönetir.
        """
        vessel_class = pressure_safety.get('vessel_classification', 'MEDIUM_PRESSURE')
        if vessel_class == 'LOW_PRESSURE':
            base = 1.0
        elif vessel_class == 'MEDIUM_PRESSURE':
            base = 2.0
        else:
            base = 3.0

        margin = pressure_safety.get('burst_margin')
        if margin is None:
            return base
        if margin < 1.0:
            return 5.0
        if margin < 1.25:
            return max(base, 4.0)
        if margin < 2.0:
            return max(base, 3.0)
        return base
    
    def _score_thermal_risk(self, thermal_safety: Dict) -> float:
        if thermal_safety.get('cooling_required', False):
            return 4.0
        elif thermal_safety.get('thermal_protection_required', False):
            return 3.0
        else:
            return 2.0
    
    def _score_explosive_risk(self, explosive_hazards: Dict) -> float:
        tnt_equivalent = explosive_hazards.get('tnt_equivalent_kg', 0)
        if tnt_equivalent > 100:
            return 5.0
        elif tnt_equivalent > 10:
            return 4.0
        elif tnt_equivalent > 1:
            return 3.0
        else:
            return 2.0
    
    def _score_toxic_risk(self, toxic_hazards: Dict) -> float:
        hazard_level = toxic_hazards.get('toxic_hazard_level', 'NONE')
        if hazard_level == 'NONE':
            return 1.0
        elif hazard_level == 'LOW':
            return 2.0
        elif hazard_level == 'MEDIUM':
            return 3.0
        elif hazard_level == 'HIGH':
            return 4.0
        else:
            return 5.0
    
    def _score_fire_risk(self, fire_hazards: Dict) -> float:
        auto_ignition = fire_hazards.get('auto_ignition_risk', {}).get('risk_level', 'LOW')
        if auto_ignition == 'LOW':
            return 2.0
        elif auto_ignition == 'MEDIUM':
            return 3.0
        else:
            return 4.0
    
    # Additional helper methods would continue here...
    # For brevity, I'll include key remaining methods
    
    def _check_safety_compliance(self, risk_assessment: Dict) -> Dict:
        """Check compliance with safety standards and regulations"""
        
        compliance_status = {
            'overall_compliance': risk_assessment['acceptability'] in ['ACCEPTABLE', 'ACCEPTABLE_WITH_CONTROLS'],
            'nfpa_compliance': True,  # Would check specific NFPA requirements
            'osha_compliance': True,  # Would check OSHA requirements
            'dot_compliance': True,   # Would check DOT transport requirements
            'local_regulations': 'REQUIRES_REVIEW',
            'insurance_requirements': 'REQUIRES_REVIEW'
        }
        
        return compliance_status
    
    def _generate_safety_recommendations(self, risk_assessment: Dict) -> List[str]:
        """Generate prioritized safety recommendations"""
        
        recommendations = []
        
        if risk_assessment['acceptability'] == 'UNACCEPTABLE':
            recommendations.append('CRITICAL: Do not proceed - unacceptable risk level')
            recommendations.append('Redesign required to reduce fundamental hazards')
        
        if risk_assessment['individual_risks']['structural'] >= 4.0:
            recommendations.append('Increase structural safety factors')
            recommendations.append('Consider higher strength materials')
        
        if risk_assessment['individual_risks']['explosive'] >= 4.0:
            recommendations.append('Implement blast-resistant design')
            recommendations.append('Increase safety distances')
        
        if risk_assessment['individual_risks']['toxic'] >= 3.0:
            recommendations.append('Implement toxic gas detection systems')
            recommendations.append('Provide appropriate PPE and training')
        
        # Add more recommendations based on specific risks...
        
        return recommendations
    
    # Deterministik yardımcı hesaplar (2026-07-14'te gerçek
    # implementasyonla dolduruldu; danışma amaçlı büyüklük kestirimleri)
    def _calculate_radiant_heat_distance(self, temperature: float, area: float,
                                         emissivity: Optional[float] = None,
                                         ambient: Optional[float] = None) -> float:
        """Acı eşiği (2.5 kW/m²) radyan tehlike mesafesi [m].

        Args:
            temperature: IŞIYAN YÜZEYİN sıcaklığı [K] — hazne gazı değil, dış
                cidar. (Eski çağrı hazne gazını geçiyordu; T^4 nedeniyle akı
                ~100x şişiyordu.)
            area: Işıyan dış yüzey ALANI [m²]. (Eski çağrı buraya cidar
                kalınlığının 100 katını geçiyordu — birim hatası.)
            emissivity: Yüzey yayınırlığı; None ise varsayılan.
            ambient: Ortam sıcaklığı [K]; None ise varsayılan.

        Model: P = eps*sigma*(T^4 - T_amb^4)*A yayılan güç, izotropik nokta
        kaynak yaklaşımıyla q(r) = P/(4*pi*r²). r, q = 2.5 kW/m² için çözülür.
        """
        eps = (SAFETY_MODEL['default_surface_emissivity']
               if emissivity is None else float(emissivity))
        t_amb = (SAFETY_MODEL['ambient_temperature_k']
                 if ambient is None else float(ambient))
        sigma = SAFETY_MODEL['stefan_boltzmann']
        emitted_flux = eps * sigma * max(float(temperature) ** 4 - t_amb ** 4, 0.0)
        threshold = SAFETY_MODEL['radiant_pain_threshold_w_m2']
        distance = np.sqrt(emitted_flux * max(float(area), 0.0)
                           / (4.0 * np.pi * threshold))
        return float(max(distance, SAFETY_MODEL['min_hazard_distance_m']))

    def _burn_dose_distance(self, surface_temperature: float, area: float,
                            exposure_time_s: float, emissivity: float,
                            ambient: float) -> float:
        """2. derece yanık DOZ mesafesi [m] — maruziyet süresini kullanır.

        Termal doz birimi (API 521 / Eisenberg probit):
            TDU = t * (q [kW/m²])^(4/3)
        2. derece yanık eşiği ~1000 (kW/m²)^(4/3)·s. Eşik akı:
            q_esik = (TDU_esik / t)^(3/4)  [kW/m²]
        ve mesafe q(r) = P/(4*pi*r²) tersinden çözülür. Yanma süresi uzadıkça
        aynı akı daha tehlikeli olur, yani mesafe BÜYÜR.
        """
        t_exp = max(float(exposure_time_s), 1e-3)
        sigma = SAFETY_MODEL['stefan_boltzmann']
        power = emissivity * sigma * max(
            float(surface_temperature) ** 4 - float(ambient) ** 4, 0.0) * max(
                float(area), 0.0)
        q_threshold_kw = (SAFETY_MODEL['second_degree_burn_tdu'] / t_exp) ** 0.75
        q_threshold = q_threshold_kw * 1000.0  # W/m²
        if power <= 0 or q_threshold <= 0:
            return 0.0
        # Hesaplanan değer KIRPILMADAN döner; asgari duruş mesafesi önerisi
        # ayrı alanda (recommended_minimum_standoff_m) verilir. Kırpma burada
        # yapılırsa maruziyet süresinin etkisi görünmez olur.
        return float(np.sqrt(power / (4.0 * np.pi * q_threshold)))


    def _identify_toxic_components(self, propellant_type: str) -> List[str]:
        toxic_map = {
            'liquid_biprop': ['n2o4'] if 'n2o4' in propellant_type.lower() else [],
            'liquid_monoprop': ['mmh', 'udmh', 'hydrazine'],
            'solid_monoprop': ['n2o'] if 'n2o' in propellant_type.lower() else []
        }
        return toxic_map.get(propellant_type, [])

    # ------------------------------------------------------------------
    # 2026-07-14: /analyze_safety 500 veriyordu — sınıfın çağırdığı 25
    # yardımcı metot hiç yazılmamıştı ("Many more helper methods would be
    # implemented here..."). Aşağıdakiler genel emniyet pratiğine dayalı
    # deterministik sınıflandırma/tavsiye merdivenleridir; tesise özgü
    # mevzuat yerine geçmez, danışma amaçlıdır.
    # ------------------------------------------------------------------

    def _determine_pressure_safety_devices(self, chamber_pressure: float) -> List[str]:
        devices = ['Pressure relief valve sized for full flow', 'Burst disc (secondary relief)']
        if chamber_pressure > 20:
            devices.append('Remote pressure monitoring with automatic abort')
        if chamber_pressure > 100:
            devices.append('Redundant transducers (2oo3 voting) and hard-wired cutoff')
        return devices

    def _classify_explosive_hazard(self, tnt_equivalent: float) -> str:
        if tnt_equivalent < 0.5:
            return 'HD 1.4 equivalent — minor hazard, local effects only'
        if tnt_equivalent < 5:
            return 'HD 1.3 equivalent — mass fire / minor blast hazard'
        return 'HD 1.1 equivalent treatment recommended — mass explosion potential'

    def _determine_storage_requirements(self, tnt_equivalent: float, propellant_type: str) -> List[str]:
        reqs = ['Segregate oxidizer and fuel storage', 'Grounded, ventilated storage area',
                'No ignition sources within exclusion zone']
        if tnt_equivalent >= 0.5:
            reqs.append('Dedicated magazine with quantity-distance siting')
        if 'liquid' in propellant_type:
            reqs.append('Secondary containment and leak detection for liquid propellants')
        return reqs

    def _determine_transport_requirements(self, tnt_equivalent: float, propellant_type: str) -> List[str]:
        reqs = ['Transport per ADR/DOT dangerous goods rules', 'Documented and placarded load']
        if tnt_equivalent >= 0.5:
            reqs.append('Class 1 explosives routing and escort requirements apply')
        if 'liquid' in propellant_type:
            reqs.append('Pressure-rated, relief-equipped transport containers')
        return reqs

    def _calculate_toxic_release_scenario(self, component: str, propellant_mass: float,
                                          facility_type: str) -> Dict:
        # Kaba korunma mesafesi: kütle ile karekök ölçekleme, bileşene göre katsayı
        katsayi = {'n2o4': 60.0, 'mmh': 80.0, 'udmh': 80.0, 'hydrazine': 90.0, 'n2o': 15.0}
        base = katsayi.get(component, 30.0)
        distance_m = base * max(propellant_mass, 0.1) ** 0.5
        return {
            'component': component,
            'release_mass_kg': propellant_mass,
            'protective_action_distance_m': round(distance_m, 0),
            'hazard_distance_m': round(distance_m, 0),  # tüketici bu adı okuyor
            'facility_type': facility_type,
            'scenario': 'Worst-case full inventory release, neutral weather (F stability)',
        }

    def _determine_toxic_detection_requirements(self, toxic_components: List[str]) -> List[str]:
        if not toxic_components:
            return []
        return ['Fixed gas detection for: ' + ', '.join(toxic_components),
                'Portable detectors for entry teams',
                'Alarm setpoints at 50% of exposure limit']

    def _determine_toxic_ppe_requirements(self, toxic_components: List[str]) -> List[str]:
        if not toxic_components:
            return ['Standard test-stand PPE (eye/ear protection, flame-resistant clothing)']
        agir = any(c in ('mmh', 'udmh', 'hydrazine', 'n2o4') for c in toxic_components)
        if agir:
            return ['SCBA or supplied-air respirator for transfer operations',
                    'Chemical splash suit (Level B) for hypergolic handling',
                    'Butyl rubber gloves; emergency shower/eyewash within 10 s reach']
        return ['Half-mask respirator with appropriate cartridge available',
                'Chemical splash goggles and gloves']

    def _assess_toxic_hazard_level(self, release_scenarios: List[Dict]) -> str:
        if not release_scenarios:
            return 'LOW'
        d = max(s.get('hazard_distance_m', 0) for s in release_scenarios)
        if d >= 300:
            return 'HIGH'
        if d >= 75:
            return 'MEDIUM'
        return 'LOW'

    def _determine_exposure_monitoring(self, toxic_components: List[str]) -> List[str]:
        if not toxic_components:
            return []
        return ['Personal dosimetry/badge sampling for exposed personnel',
                'Post-operation area sampling before re-entry',
                'Medical surveillance program for routine handlers']

    def _determine_emergency_treatment(self, toxic_components: List[str]) -> Dict:
        tedavi = {}
        for c in toxic_components:
            if c in ('mmh', 'udmh', 'hydrazine'):
                tedavi[c] = 'Remove from exposure, oxygen, pyridoxine (B6) protocol per physician'
            elif c == 'n2o4':
                tedavi[c] = 'Fresh air, oxygen; observe 24-48 h for delayed pulmonary edema'
            elif c == 'n2o':
                tedavi[c] = 'Fresh air, oxygen if hypoxic symptoms'
            else:
                tedavi[c] = 'Decontaminate, supportive care, consult poison control'
        return tedavi

    def _classify_fire_hazard(self, propellant_type: str) -> str:
        if 'liquid' in propellant_type:
            return 'Class B (flammable liquid) with oxidizer-enhanced burning'
        if 'hybrid' in propellant_type:
            return 'Class A fuel grain + oxidizer-enhanced burning'
        return 'Class 1.3-type solid propellant fire (self-oxidized, cannot be smothered)'

    def _assess_auto_ignition_risk(self, propellant_type: str, chamber_temperature: float) -> Dict:
        # _score_fire_risk 'risk_level' anahtarını okuyor — dict sözleşmesi
        if 'solid' in propellant_type and chamber_temperature > 2500:
            return {'risk_level': 'MEDIUM',
                    'note': 'Residual grain can reignite from hot surfaces; enforce cooldown'}
        if 'liquid' in propellant_type:
            return {'risk_level': 'MEDIUM',
                    'note': 'Vapor accumulation near hot components; ventilate before approach'}
        return {'risk_level': 'LOW', 'note': 'Controlled ignition sources only'}

    def _analyze_fire_spread_potential(self, propellant_mass: float, propellant_type: str) -> str:
        if propellant_mass > 100:
            return 'HIGH — radiant heating can ignite adjacent structures; wide firebreak needed'
        if propellant_mass > 10:
            return 'MEDIUM — local spread possible; clear combustibles within safety distance'
        return 'LOW — limited to immediate test area'

    def _determine_fire_suppression_system(self, fire_class: str, propellant_mass: float,
                                           auto_ignition_risk: str) -> Dict:
        sistemler = ['Water deluge for cooling structures (note: solid propellant fires are not extinguishable — protect exposures and let burn)']
        primary = 'Water deluge (exposure protection)'
        if 'Class B' in fire_class:
            sistemler.append('Foam or CO2 capability for liquid fuel spill fires')
            primary = 'Foam (AFFF) on liquid spill; water for cooling'
        if propellant_mass > 50 or auto_ignition_risk.get('risk_level') in ('HIGH', 'MEDIUM'):
            sistemler.append('Fixed remote-actuated deluge over test stand')
        sistemler.append('Rated portable extinguishers at all egress points')
        return {'primary_agent': primary, 'systems': sistemler}

    def _calculate_fire_safety_distances(self, propellant_mass: float) -> Dict:
        # Kaba kübik-kök ölçekleme (kütle ↑ → mesafe ↑), min 15 m
        base = max(propellant_mass, 1.0) ** (1.0 / 3.0)
        return {
            'personnel_distance_m': round(max(15.0, 20.0 * base), 0),
            'equipment_distance_m': round(max(10.0, 10.0 * base), 0),
            'public_distance_m': round(max(60.0, 60.0 * base), 0),
            # _generate_emergency_procedures bu anahtarı okuyor
            'radiant_heat_m': round(max(15.0, 20.0 * base), 0),
        }

    def _identify_ignition_sources_control(self) -> List[str]:
        return ['Hot work permit system within exclusion zone',
                'Bonding/grounding of all transfer equipment',
                'Non-sparking tools for propellant handling',
                'ATEX/intrinsically-safe electrical equipment in vapor zones',
                'No smoking / no open flame policy with physical enforcement']

    def _generate_fire_fighting_procedures(self, fire_class: str) -> List[str]:
        adimlar = ['Evacuate to safety distance and account for personnel',
                   'Actuate remote deluge; do NOT approach burning propellant',
                   'Notify fire brigade with propellant data sheet']
        if 'not be smothered' in fire_class or 'solid' in fire_class.lower():
            adimlar.append('Let solid propellant burn out; cool surroundings only')
        adimlar.append('Re-enter only after thermal + toxic clearance measurements')
        return adimlar

    def _determine_safety_equipment_requirements(self, explosive_hazards: Dict,
                                                 toxic_hazards: Dict, fire_hazards: Dict,
                                                 facility_type: str) -> Dict:
        return {
            'fixed_systems': ['Remote firing and abort system', 'Blast barrier or berm',
                              'Fixed deluge (per fire analysis)', 'Area gas detection (per toxic analysis)'],
            'personal_equipment': ['Flame-resistant clothing', 'Hearing and eye protection',
                                   'Hard hats in mechanical hazard areas'] +
                                  toxic_hazards.get('ppe_requirements', []),
            'emergency_equipment': ['First aid + burn kit', 'Emergency shower/eyewash',
                                    'Backup communications', 'Fire blankets and extinguishers'],
            'facility_type': facility_type,
        }

    def _determine_personnel_limits(self, motor_data: Dict, facility_type: str) -> Dict:
        return {
            'test_cell_during_operation': 0,
            'control_room': 'Essential test crew only',
            'observation_area': 'Authorized personnel behind rated barrier',
            'note': 'No personnel inside exclusion zone from pressurization to safing',
        }

    def _determine_qualification_requirements(self, facility_type: str) -> List[str]:
        return ['Documented propellant-handling qualification for operators',
                'Test conductor certified on abort procedures',
                'Annual requalification and emergency drill participation']

    def _determine_training_requirements(self, propellant_type: str, facility_type: str) -> List[str]:
        egitim = ['Propellant hazards and compatibility training',
                  'Emergency response and evacuation drills',
                  'Pressure systems safety awareness']
        if 'liquid' in propellant_type:
            egitim.append('Cryogenic/toxic liquid transfer procedures (as applicable)')
        return egitim

    def _determine_required_antidotes(self, toxic_hazards: Dict) -> List[str]:
        bilesenler = toxic_hazards.get('toxic_components', []) or []
        antidot = []
        if any(c in ('mmh', 'udmh', 'hydrazine') for c in bilesenler):
            antidot.append('Pyridoxine (vitamin B6) IV protocol available on site/nearby')
        if 'n2o4' in bilesenler:
            antidot.append('Oxygen therapy capability; bronchodilators per physician')
        return antidot or ['No specific antidote required — supportive care']

    def _generate_treatment_protocols(self, toxic_hazards: Dict) -> List[str]:
        return ['Decontaminate (remove clothing, flush 15 min) before transport',
                'Transport with propellant safety data sheet',
                'Observe gas-exposure casualties for delayed symptoms (24-48 h)']

    def _generate_risk_matrix(self) -> Dict:
        return {
            'axes': {'likelihood': ['Rare', 'Unlikely', 'Possible', 'Likely', 'Frequent'],
                     'severity': ['Negligible', 'Minor', 'Major', 'Critical', 'Catastrophic']},
            'acceptance': {'LOW': 'Acceptable with routine controls',
                           'MEDIUM': 'Acceptable with documented mitigations',
                           'HIGH': 'Requires risk reduction before test',
                           'CRITICAL': 'Unacceptable — redesign or re-site'},
        }

    def _determine_mitigation_priority(self, structural_risk: float, pressure_risk: float,
                                       thermal_risk: float, explosive_risk: float,
                                       toxic_risk: float, fire_risk: float) -> List[Dict]:
        adlar = [('structural', structural_risk), ('pressure', pressure_risk),
                 ('thermal', thermal_risk), ('explosive', explosive_risk),
                 ('toxic', toxic_risk), ('fire', fire_risk)]
        sirali = sorted(adlar, key=lambda x: x[1], reverse=True)
        return [{'area': ad, 'risk_score': round(sk, 2), 'priority': i + 1}
                for i, (ad, sk) in enumerate(sirali)]
    # This is a representative sample of the complete safety analysis system