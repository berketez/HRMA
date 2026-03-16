"""
Heat Transfer Analysis Module
Chamber wall temperature and cooling analysis for hybrid rocket motors
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional

class HeatTransferAnalyzer:
    """Heat transfer analysis for hybrid rocket motor chambers"""
    
    def __init__(self):
        self.stefan_boltzmann = 5.67e-8  # W/m²·K⁴
        self.g0 = 9.81  # m/s²
        
        # Material properties database
        self.materials = {
            'steel': {
                'thermal_conductivity': 50.0,  # W/m·K
                'density': 7850,               # kg/m³
                'specific_heat': 460,          # J/kg·K
                'melting_point': 1773,         # K
                'emissivity': 0.8,
                'allowable_temperature': 1073   # K (safety limit)
            },
            'aluminum': {
                'thermal_conductivity': 205.0,
                'density': 2700,
                'specific_heat': 900,
                'melting_point': 933,
                'emissivity': 0.9,
                'allowable_temperature': 773
            },
            'inconel': {
                'thermal_conductivity': 15.0,
                'density': 8440,
                'specific_heat': 435,
                'melting_point': 1673,
                'emissivity': 0.85,
                'allowable_temperature': 1373
            },
            'copper': {
                'thermal_conductivity': 401.0,
                'density': 8960,
                'specific_heat': 385,
                'melting_point': 1358,
                'emissivity': 0.75,
                'allowable_temperature': 1000
            }
        }
    
    def analyze_heat_transfer(self, motor_data: Dict, material: str = 'steel', 
                            wall_thickness: float = 0.005, ambient_temp: float = 293.15,
                            cooling_type: str = 'natural') -> Dict:
        """
        Complete heat transfer analysis
        
        Args:
            motor_data: Motor performance and geometry data
            material: Wall material ('steel', 'aluminum', 'inconel', 'copper')
            wall_thickness: Wall thickness in meters
            ambient_temp: Ambient temperature in K
            cooling_type: 'natural', 'forced', 'regenerative'
            
        Returns:
            Heat transfer analysis results
        """
        
        # Extract motor parameters
        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
        chamber_length = motor_data.get('chamber_length', 0.5)  # m
        burn_time = motor_data.get('burn_time', 10)  # s
        mdot_total = motor_data.get('mdot_total', 1.0)  # kg/s
        
        # Get material properties
        mat_props = self.materials.get(material, self.materials['steel'])
        
        # Calculate heat transfer coefficients
        heat_transfer_coeffs = self._calculate_heat_transfer_coefficients(
            motor_data, mat_props, cooling_type
        )
        
        # Gas-side heat transfer
        gas_side_analysis = self._analyze_gas_side_heat_transfer(
            chamber_pressure, chamber_temperature, chamber_diameter,
            mdot_total, heat_transfer_coeffs['gas_side']
        )
        
        # Wall temperature distribution
        wall_analysis = self._analyze_wall_temperature(
            gas_side_analysis['heat_flux'], wall_thickness, mat_props,
            ambient_temp, heat_transfer_coeffs['coolant_side']
        )
        
        # Cooling requirements
        cooling_analysis = self._analyze_cooling_requirements(
            gas_side_analysis['total_heat_rate'], burn_time, motor_data, cooling_type
        )
        
        # Safety analysis
        safety_analysis = self._analyze_thermal_safety(
            wall_analysis['max_temperature'], mat_props, wall_thickness, chamber_pressure
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
                                           mat_props: Dict, cooling_type: str) -> Dict:
        """Calculate heat transfer coefficients"""
        
        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
        mdot_total = motor_data.get('mdot_total', 1.0)  # kg/s
        
        # Gas properties - use combustion gas properties
        R_gas = motor_data.get('gas_constant', 287)  # J/kg·K - from combustion analysis
        gas_conductivity = 0.2  # W/m·K
        gas_viscosity = 5e-5    # Pa·s
        gas_density = chamber_pressure / (R_gas * chamber_temperature)  # kg/m³
        gas_cp = motor_data.get('gas_cp', 1200)  # J/kg·K - from combustion analysis
        
        # Reynolds number
        velocity = mdot_total / (gas_density * np.pi * (chamber_diameter/2)**2)
        reynolds = gas_density * velocity * chamber_diameter / gas_viscosity
        
        # Prandtl number
        prandtl = gas_cp * gas_viscosity / gas_conductivity
        
        # Nusselt number (Dittus-Boelter correlation)
        nusselt = 0.023 * reynolds**0.8 * prandtl**0.4
        
        # Gas-side heat transfer coefficient
        h_gas = nusselt * gas_conductivity / chamber_diameter
        
        # Coolant-side heat transfer coefficient
        if cooling_type == 'natural':
            h_coolant = 25.0  # W/m²·K (natural convection in air)
        elif cooling_type == 'forced':
            h_coolant = 100.0  # W/m²·K (forced air cooling)
        elif cooling_type == 'regenerative':
            h_coolant = 2000.0  # W/m²·K (liquid cooling)
        else:
            h_coolant = 25.0
        
        return {
            'gas_side': h_gas,
            'coolant_side': h_coolant,
            'reynolds_number': reynolds,
            'prandtl_number': prandtl,
            'nusselt_number': nusselt
        }
    
    def _analyze_gas_side_heat_transfer(self, pressure: float, temperature: float,
                                      diameter: float, mdot: float, h_gas: float) -> Dict:
        """Analyze gas-side heat transfer"""
        
        # Chamber surface area
        length = 0.5  # Assumed chamber length
        surface_area = np.pi * diameter * length + np.pi * (diameter/2)**2  # Cylindrical + end
        
        # Wall temperature estimate (initial guess)
        T_wall_guess = 800  # K
        
        # Heat flux
        heat_flux = h_gas * (temperature - T_wall_guess)  # W/m²
        
        # Total heat transfer rate
        total_heat_rate = heat_flux * surface_area  # W
        
        # Heat flux distribution (simplified)
        # Higher at throat, lower at chamber
        throat_heat_flux = heat_flux * 1.5
        chamber_heat_flux = heat_flux * 0.8
        
        return {
            'heat_flux': heat_flux,
            'total_heat_rate': total_heat_rate,
            'surface_area': surface_area,
            'throat_heat_flux': throat_heat_flux,
            'chamber_heat_flux': chamber_heat_flux,
            'gas_temperature': temperature,
            'estimated_wall_temperature': T_wall_guess
        }
    
    def _analyze_wall_temperature(self, heat_flux: float, thickness: float,
                                mat_props: Dict, ambient_temp: float, h_coolant: float) -> Dict:
        """Analyze wall temperature distribution"""
        
        k = mat_props['thermal_conductivity']
        
        # Thermal resistance analysis
        R_conduction = thickness / k  # K·m²/W
        R_convection = 1 / h_coolant   # K·m²/W
        R_total = R_conduction + R_convection
        
        # Temperature drop across wall
        delta_T_conduction = heat_flux * R_conduction
        delta_T_convection = heat_flux * R_convection
        
        # Wall temperatures
        T_inner = ambient_temp + heat_flux * R_total  # Inner (hot) surface
        T_outer = ambient_temp + heat_flux * R_convection  # Outer (cold) surface
        T_average = (T_inner + T_outer) / 2
        
        # Temperature gradient
        temp_gradient = delta_T_conduction / thickness  # K/m
        
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
        
        # Safety factors
        temp_safety_factor = allowable_temp / max_temp
        melting_safety_factor = melting_point / max_temp
        
        # Thermal stress (simplified)
        thermal_expansion = 12e-6  # 1/K (typical for steel)
        elastic_modulus = 200e9    # Pa
        thermal_stress = elastic_modulus * thermal_expansion * (max_temp - 293)
        
        # Allowable stress (simplified)
        yield_strength = 250e6  # Pa (typical for steel)
        stress_safety_factor = yield_strength / thermal_stress
        
        # Risk assessment
        risk_level = 'LOW'
        if temp_safety_factor < 1.5:
            risk_level = 'HIGH'
        elif temp_safety_factor < 2.0:
            risk_level = 'MEDIUM'
        
        warnings = []
        if temp_safety_factor < 1.0:
            warnings.append('Wall temperature exceeds allowable limit')
        if melting_safety_factor < 2.0:
            warnings.append('Wall temperature approaches melting point')
        if stress_safety_factor < 2.0:
            warnings.append('High thermal stress - consider thicker walls')
        
        return {
            'temperature_safety_factor': temp_safety_factor,
            'melting_safety_factor': melting_safety_factor,
            'stress_safety_factor': stress_safety_factor,
            'thermal_stress': thermal_stress / 1e6,  # MPa
            'risk_level': risk_level,
            'warnings': warnings,
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