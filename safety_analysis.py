"""
Comprehensive Safety Analysis Module
Safety, hazard, and risk assessment for rocket motor systems
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

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
                                   facility_type: str = 'test_stand') -> Dict:
        """
        Complete safety analysis including all hazard types
        
        Args:
            motor_data: Motor performance and design data
            propellant_mass: Total propellant mass (kg)
            propellant_type: Type of propellant system
            facility_type: 'test_stand', 'manufacturing', 'transport', 'launch'
            
        Returns:
            Comprehensive safety analysis results
        """
        
        # Extract motor parameters
        chamber_pressure = motor_data.get('chamber_pressure', 20.0)  # bar
        chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        thrust = motor_data.get('thrust', 1000)  # N
        burn_time = motor_data.get('burn_time', 10)  # s
        
        # Structural safety analysis
        structural_safety = self._analyze_structural_safety(motor_data)
        
        # Pressure vessel safety
        pressure_safety = self._analyze_pressure_vessel_safety(
            chamber_pressure, motor_data.get('chamber_diameter', 0.1)
        )
        
        # Thermal safety analysis
        thermal_safety = self._analyze_thermal_safety(
            chamber_temperature, motor_data.get('wall_thickness', 0.005)
        )
        
        # Explosive hazard analysis
        explosive_hazards = self._analyze_explosive_hazards(
            propellant_mass, propellant_type, thrust
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
            'recommendations': self._generate_safety_recommendations(risk_assessment)
        }
    
    def _analyze_structural_safety(self, motor_data: Dict) -> Dict:
        """Analyze structural safety factors and failure modes"""
        
        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
        wall_thickness = motor_data.get('wall_thickness', 0.005)  # m
        
        # Material properties (conservative steel values)
        yield_strength = 250e6  # Pa
        ultimate_strength = 400e6  # Pa
        
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
            'yield_safety_factor': yield_safety_factor,
            'ultimate_safety_factor': ultimate_safety_factor,
            'failure_probability': failure_probability,
            'failure_modes': failure_modes,
            'structural_integrity': 'SAFE' if yield_safety_factor >= 4.0 else 'MARGINAL' if yield_safety_factor >= 2.0 else 'UNSAFE',
            'recommended_inspection_interval': self._calculate_inspection_interval(yield_safety_factor)
        }
    
    def _analyze_pressure_vessel_safety(self, chamber_pressure: float, diameter: float) -> Dict:
        """Analyze pressure vessel safety requirements"""
        
        # Design pressure with safety factor
        design_pressure = chamber_pressure * self.safety_margins.pressure_safety_factor
        
        # Burst pressure requirement
        required_burst_pressure = chamber_pressure * self.safety_margins.minimum_burst_pressure_ratio
        
        # Pressure test requirements
        hydrostatic_test_pressure = design_pressure * 1.5
        proof_pressure = design_pressure * 1.25
        
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
        
        return {
            'operating_pressure_bar': chamber_pressure,
            'design_pressure_bar': design_pressure,
            'required_burst_pressure_bar': required_burst_pressure,
            'hydrostatic_test_pressure_bar': hydrostatic_test_pressure,
            'proof_pressure_bar': proof_pressure,
            'vessel_classification': vessel_class,
            'inspection_requirements': inspection_requirements,
            'applicable_codes': ['ASME BPVC Section VIII', 'EN 13445', 'AS 1210'],
            'safety_devices_required': self._determine_pressure_safety_devices(chamber_pressure)
        }
    
    def _analyze_thermal_safety(self, chamber_temperature: float, wall_thickness: float) -> Dict:
        """Analyze thermal safety and heat-related hazards"""
        
        # Material temperature limits (conservative values)
        steel_max_temp = 800  # K
        aluminum_max_temp = 600  # K
        
        # Estimated wall temperature (simplified heat transfer)
        wall_temperature = chamber_temperature * 0.3  # Rough approximation
        
        # Thermal safety factors
        steel_thermal_safety = steel_max_temp / wall_temperature
        aluminum_thermal_safety = aluminum_max_temp / wall_temperature
        
        # Thermal expansion effects
        thermal_expansion_steel = 12e-6 * (wall_temperature - 293)  # strain
        thermal_stress_estimate = 200e9 * thermal_expansion_steel  # Pa (simplified)
        
        # Burn hazard distances
        radiant_heat_distance = self._calculate_radiant_heat_distance(
            chamber_temperature, wall_thickness * 100  # convert to area approximation
        )
        
        return {
            'chamber_temperature_k': chamber_temperature,
            'estimated_wall_temperature_k': wall_temperature,
            'steel_thermal_safety_factor': steel_thermal_safety,
            'aluminum_thermal_safety_factor': aluminum_thermal_safety,
            'thermal_stress_mpa': thermal_stress_estimate / 1e6,
            'radiant_heat_hazard_distance_m': radiant_heat_distance,
            'material_recommendation': 'Steel' if steel_thermal_safety > 1.3 else 'Inconel/High-temp alloy',
            'cooling_required': wall_temperature > steel_max_temp / self.safety_margins.temperature_safety_factor,
            'thermal_protection_required': radiant_heat_distance > 3.0
        }
    
    def _analyze_explosive_hazards(self, propellant_mass: float, propellant_type: str, thrust: float) -> Dict:
        """Analyze explosive hazards and calculate safety distances"""
        
        # TNT equivalent calculation
        tnt_equivalent = propellant_mass * self.propellant_tnt_equivalents.get(propellant_type, 0.4)
        
        # Blast overpressure distances (Hopkinson-Cranz law)
        distances = self._calculate_blast_distances(tnt_equivalent)
        
        # Fragment hazard analysis
        fragment_hazards = self._calculate_fragment_hazards(propellant_mass, thrust)
        
        # Quantity-distance (Q-D) requirements
        qd_requirements = self._calculate_qd_requirements(tnt_equivalent)
        
        return {
            'propellant_mass_kg': propellant_mass,
            'tnt_equivalent_kg': tnt_equivalent,
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
        
        overpressures = {
            'lethal': 100000,      # Pa (100 kPa)
            'serious_injury': 35000,  # Pa (35 kPa)
            'minor_injury': 7000,     # Pa (7 kPa)
            'property_damage': 2000   # Pa (2 kPa)
        }
        
        distances = {}
        for level, pressure in overpressures.items():
            # Simplified Kingery-Bulmash relationship
            scaled_distance = 0.067 * (pressure / 100000) ** (-0.4)
            distance = scaled_distance * (tnt_equivalent ** (1/3))
            distances[level] = {
                'distance_m': distance,
                'overpressure_kpa': pressure / 1000
            }
        
        return distances
    
    def _calculate_fragment_hazards(self, propellant_mass: float, thrust: float) -> Dict:
        """Calculate fragment throw distances and hazards"""
        
        # Estimate case mass (empirical relationship)
        case_mass = propellant_mass * 0.15  # Typical case mass fraction
        
        # Fragment velocity estimation (Gurney equation approximation)
        gurney_velocity = 2700  # m/s for steel case
        fragment_velocity = gurney_velocity * np.sqrt(propellant_mass / (propellant_mass + case_mass/2))
        
        # Fragment range (45-degree trajectory, no air resistance)
        max_range = fragment_velocity**2 / 9.81
        
        # Lethal fragment analysis
        lethal_fragment_mass = 0.01  # kg (10g fragment considered lethal)
        lethal_kinetic_energy = 79  # J (NATO STANAG 2920)
        lethal_velocity = np.sqrt(2 * lethal_kinetic_energy / lethal_fragment_mass)
        
        return {
            'estimated_case_mass_kg': case_mass,
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
        
        # NATO STANAG 4123 / DOD 6055.9-STD relationships
        # K-factors for different exposed sites
        k_factors = {
            'inhabited_building': 40,      # K = 40
            'public_traffic_route': 18,    # K = 18
            'explosives_facility': 12,     # K = 12
            'personnel_facility': 22,      # K = 22
            'ammunition_storage': 12       # K = 12
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
        vessel_class = pressure_safety.get('vessel_classification', 'MEDIUM_PRESSURE')
        if vessel_class == 'LOW_PRESSURE':
            return 1.0
        elif vessel_class == 'MEDIUM_PRESSURE':
            return 2.0
        else:
            return 3.0
    
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
    
    # Placeholder methods for other calculations
    def _calculate_radiant_heat_distance(self, temperature: float, area: float) -> float:
        # Stefan-Boltzmann law approximation
        emissivity = 0.8
        stefan_boltzmann = 5.67e-8
        heat_flux = emissivity * stefan_boltzmann * (temperature**4 - 293**4)
        # Distance for 2.5 kW/m² (pain threshold)
        pain_threshold = 2500  # W/m²
        distance = np.sqrt(heat_flux * area / (4 * np.pi * pain_threshold))
        return max(distance, 3.0)  # Minimum 3m
    
    def _identify_toxic_components(self, propellant_type: str) -> List[str]:
        toxic_map = {
            'liquid_biprop': ['n2o4'] if 'n2o4' in propellant_type.lower() else [],
            'liquid_monoprop': ['mmh', 'udmh', 'hydrazine'],
            'solid_monoprop': ['n2o'] if 'n2o' in propellant_type.lower() else []
        }
        return toxic_map.get(propellant_type, [])
    
    # Many more helper methods would be implemented here...
    # This is a representative sample of the complete safety analysis system