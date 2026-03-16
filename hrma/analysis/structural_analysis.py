"""
Structural Analysis Module
Wall thickness calculation and safety factor analysis for hybrid rocket motors
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional

class StructuralAnalyzer:
    """Structural analysis for hybrid rocket motor chambers"""
    
    def __init__(self):
        # Material properties database
        self.materials = {
            'steel_4130': {
                'yield_strength': 460e6,        # Pa
                'ultimate_strength': 730e6,     # Pa
                'elastic_modulus': 200e9,       # Pa
                'density': 7850,               # kg/m³
                'poisson_ratio': 0.27,
                'fatigue_limit': 230e6,        # Pa
                'safety_factor': 4.0
            },
            'aluminum_6061': {
                'yield_strength': 275e6,
                'ultimate_strength': 310e6,
                'elastic_modulus': 68.9e9,
                'density': 2700,
                'poisson_ratio': 0.33,
                'fatigue_limit': 96e6,
                'safety_factor': 4.0
            },
            'inconel_718': {
                'yield_strength': 1100e6,
                'ultimate_strength': 1275e6,
                'elastic_modulus': 200e9,
                'density': 8220,
                'poisson_ratio': 0.29,
                'fatigue_limit': 450e6,
                'safety_factor': 3.0
            },
            'titanium_6al4v': {
                'yield_strength': 880e6,
                'ultimate_strength': 950e6,
                'elastic_modulus': 114e9,
                'density': 4430,
                'poisson_ratio': 0.31,
                'fatigue_limit': 350e6,
                'safety_factor': 4.0
            }
        }
    
    def analyze_structure(self, motor_data: Dict, material: str = 'steel_4130',
                         design_pressure_factor: float = 1.5) -> Dict:
        """
        Complete structural analysis
        
        Args:
            motor_data: Motor performance and geometry data
            material: Material type
            design_pressure_factor: Safety factor for design pressure
            
        Returns:
            Structural analysis results
        """
        
        # Extract motor parameters
        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
        chamber_length = motor_data.get('chamber_length', 0.5)  # m
        throat_diameter = motor_data.get('throat_diameter', 0.02)  # m
        nozzle_type = motor_data.get('nozzle_type', 'conical')
        burn_time = motor_data.get('burn_time', 10)  # s
        
        # Design pressure
        design_pressure = chamber_pressure * design_pressure_factor
        
        # Get material properties
        mat_props = self.materials.get(material, self.materials['steel_4130'])
        
        # Chamber wall analysis
        chamber_analysis = self._analyze_chamber_wall(
            design_pressure, chamber_diameter, chamber_length, mat_props
        )
        
        # Nozzle analysis
        nozzle_analysis = self._analyze_nozzle_structure(
            design_pressure, throat_diameter, chamber_diameter, mat_props, nozzle_type
        )
        
        # End cap analysis
        end_cap_analysis = self._analyze_end_caps(
            design_pressure, chamber_diameter, mat_props
        )
        
        # Bolt/fastener analysis
        fastener_analysis = self._analyze_fasteners(
            design_pressure, chamber_diameter, mat_props
        )
        
        # Fatigue analysis
        fatigue_analysis = self._analyze_fatigue(
            chamber_analysis['hoop_stress'], burn_time, mat_props
        )
        
        # Weight analysis
        weight_analysis = self._calculate_weight(
            chamber_analysis, nozzle_analysis, end_cap_analysis, mat_props
        )
        
        # Safety analysis
        safety_analysis = self._analyze_safety_factors(
            chamber_analysis, nozzle_analysis, end_cap_analysis, mat_props
        )
        
        return {
            'chamber_analysis': chamber_analysis,
            'nozzle_analysis': nozzle_analysis,
            'end_cap_analysis': end_cap_analysis,
            'fastener_analysis': fastener_analysis,
            'fatigue_analysis': fatigue_analysis,
            'weight_analysis': weight_analysis,
            'safety_analysis': safety_analysis,
            'material_properties': mat_props,
            'design_parameters': {
                'material': material,
                'design_pressure': design_pressure / 1e5,  # bar
                'design_pressure_factor': design_pressure_factor
            }
        }
    
    def _analyze_chamber_wall(self, pressure: float, diameter: float,
                            length: float, mat_props: Dict) -> Dict:
        """Analyze chamber wall thickness and stresses"""
        
        radius = diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = mat_props['safety_factor']
        
        # Required wall thickness (thin wall approximation)
        # t = P*r / (sigma_allow)
        allowable_stress = yield_strength / safety_factor
        min_thickness = pressure * radius / allowable_stress
        
        # Recommended thickness (add 20% margin)
        recommended_thickness = min_thickness * 1.2
        
        # Actual stresses with recommended thickness
        hoop_stress = pressure * radius / recommended_thickness
        longitudinal_stress = pressure * radius / (2 * recommended_thickness)
        
        # Von Mises equivalent stress
        von_mises_stress = np.sqrt(hoop_stress**2 - hoop_stress * longitudinal_stress + longitudinal_stress**2)
        
        # Safety factors
        hoop_safety_factor = yield_strength / hoop_stress
        von_mises_safety_factor = yield_strength / von_mises_stress
        
        return {
            'minimum_thickness': min_thickness * 1000,  # mm
            'recommended_thickness': recommended_thickness * 1000,  # mm
            'hoop_stress': hoop_stress / 1e6,  # MPa
            'longitudinal_stress': longitudinal_stress / 1e6,  # MPa
            'von_mises_stress': von_mises_stress / 1e6,  # MPa
            'hoop_safety_factor': hoop_safety_factor,
            'von_mises_safety_factor': von_mises_safety_factor,
            'allowable_stress': allowable_stress / 1e6,  # MPa
            'diameter': diameter * 1000,  # mm
            'length': length * 1000  # mm
        }
    
    def _analyze_nozzle_structure(self, pressure: float, throat_diameter: float,
                                chamber_diameter: float, mat_props: Dict, nozzle_type: str) -> Dict:
        """Analyze nozzle structural requirements"""
        
        throat_radius = throat_diameter / 2
        chamber_radius = chamber_diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = mat_props['safety_factor']
        
        # Throat section is critical (smallest diameter, highest stress)
        allowable_stress = yield_strength / safety_factor
        min_throat_thickness = pressure * throat_radius / allowable_stress
        
        # Nozzle transition stresses (simplified)
        # Higher stress concentration at throat
        stress_concentration_factor = 2.0 if nozzle_type == 'conical' else 1.5
        
        # Effective stress at throat
        effective_stress = pressure * throat_radius / min_throat_thickness * stress_concentration_factor
        
        # Required thickness considering stress concentration
        required_throat_thickness = min_throat_thickness * stress_concentration_factor
        
        # Nozzle wall thickness variation
        chamber_thickness = pressure * chamber_radius / allowable_stress
        
        return {
            'throat_diameter': throat_diameter * 1000,  # mm
            'min_throat_thickness': min_throat_thickness * 1000,  # mm
            'required_throat_thickness': required_throat_thickness * 1000,  # mm
            'chamber_thickness': chamber_thickness * 1000,  # mm
            'stress_concentration_factor': stress_concentration_factor,
            'throat_stress': effective_stress / 1e6,  # MPa
            'safety_factor': yield_strength / effective_stress,
            'nozzle_type': nozzle_type
        }
    
    def _analyze_end_caps(self, pressure: float, diameter: float, mat_props: Dict) -> Dict:
        """Analyze end cap (head and injector end) requirements"""
        
        radius = diameter / 2
        yield_strength = mat_props['yield_strength']
        safety_factor = mat_props['safety_factor']
        
        # Flat circular plate under pressure
        # Maximum stress at center: sigma = (3/8) * P * (r²/t²) * (3 + nu)
        # Rearranging for thickness: t = r * sqrt((3*P*(3+nu))/(8*sigma_allow))
        
        poisson_ratio = mat_props['poisson_ratio']
        allowable_stress = yield_strength / safety_factor
        
        # Flat head thickness
        flat_head_thickness = radius * np.sqrt((3 * pressure * (3 + poisson_ratio)) / (8 * allowable_stress))
        
        # Dished head thickness (more efficient)
        # Assuming 2:1 elliptical head
        dished_head_thickness = pressure * radius / (2 * allowable_stress)
        
        # Bolt circle analysis
        bolt_circle_diameter = diameter + 0.05  # 50mm larger than chamber
        bolt_circle_stress = pressure * (bolt_circle_diameter/2) / flat_head_thickness
        
        return {
            'flat_head_thickness': flat_head_thickness * 1000,  # mm
            'dished_head_thickness': dished_head_thickness * 1000,  # mm
            'recommended_type': 'dished' if dished_head_thickness < flat_head_thickness else 'flat',
            'bolt_circle_diameter': bolt_circle_diameter * 1000,  # mm
            'bolt_circle_stress': bolt_circle_stress / 1e6,  # MPa
            'head_safety_factor': allowable_stress / bolt_circle_stress if bolt_circle_stress > 0 else float('inf')
        }
    
    def _analyze_fasteners(self, pressure: float, diameter: float, mat_props: Dict) -> Dict:
        """Analyze bolt and fastener requirements"""
        
        # Total force on end cap
        total_force = pressure * np.pi * (diameter/2)**2  # N
        
        # Assume 8-12 bolts depending on diameter
        if diameter < 0.1:
            num_bolts = 6
        elif diameter < 0.2:
            num_bolts = 8
        else:
            num_bolts = 12
        
        # Force per bolt (with safety factor)
        bolt_safety_factor = 4.0
        force_per_bolt = total_force * bolt_safety_factor / num_bolts
        
        # Bolt sizing (assume steel bolts, 400 MPa allowable stress)
        bolt_allowable_stress = 400e6  # Pa
        required_bolt_area = force_per_bolt / bolt_allowable_stress  # m²
        required_bolt_diameter = 2 * np.sqrt(required_bolt_area / np.pi)  # m
        
        # Standard bolt sizes (in meters)
        standard_sizes = [0.006, 0.008, 0.010, 0.012, 0.016, 0.020, 0.024, 0.030, 0.036, 0.042]  # M6 to M42
        suitable_sizes = [size for size in standard_sizes if size >= required_bolt_diameter]
        
        if suitable_sizes:
            recommended_bolt_size = min(suitable_sizes)
        else:
            # If required diameter exceeds largest standard size, use largest available
            recommended_bolt_size = max(standard_sizes)
            # Add warning about custom bolt requirement
        
        # Bolt circle
        bolt_circle_radius = (diameter/2) + 0.025  # 25mm from chamber edge
        
        # Warning if custom bolt needed
        bolt_warning = None
        if not suitable_sizes:
            bolt_warning = f"Required bolt diameter ({required_bolt_diameter*1000:.1f}mm) exceeds largest standard size. Custom bolts needed."
        
        return {
            'total_force': total_force / 1000,  # kN
            'num_bolts': num_bolts,
            'force_per_bolt': force_per_bolt / 1000,  # kN
            'required_bolt_diameter': required_bolt_diameter * 1000,  # mm
            'recommended_bolt_size': f"M{int(recommended_bolt_size*1000)}",
            'bolt_circle_radius': bolt_circle_radius * 1000,  # mm
            'bolt_spacing': 2 * np.pi * bolt_circle_radius / num_bolts * 1000,  # mm
            'bolt_safety_factor': bolt_safety_factor,
            'warning': bolt_warning
        }
    
    def _analyze_fatigue(self, stress: float, burn_time: float, mat_props: Dict) -> Dict:
        """Analyze fatigue life"""
        
        fatigue_limit = mat_props['fatigue_limit']
        
        # Estimate number of cycles
        # Assume pressure cycling during burn + startup/shutdown cycles
        cycles_per_burn = max(1, int(burn_time))  # Pressure oscillations
        startup_shutdown_cycles = 1
        total_cycles = cycles_per_burn + startup_shutdown_cycles
        
        # Fatigue safety factor
        fatigue_safety_factor = fatigue_limit / stress if stress > 0 else float('inf')
        
        # Estimated fatigue life (simplified S-N curve)
        if stress < fatigue_limit:
            estimated_life = float('inf')  # Infinite life
        else:
            # Simplified Basquin's law: N = (Sf/S)^b where b ≈ 10 for steel
            b_exponent = 10
            estimated_life = (fatigue_limit / stress) ** b_exponent
        
        fatigue_status = 'SAFE'
        if fatigue_safety_factor < 2.0:
            fatigue_status = 'CRITICAL'
        elif fatigue_safety_factor < 4.0:
            fatigue_status = 'MARGINAL'
        
        return {
            'stress_amplitude': stress / 1e6,  # MPa (assuming mean stress = stress amplitude)
            'fatigue_limit': fatigue_limit / 1e6,  # MPa
            'fatigue_safety_factor': fatigue_safety_factor,
            'estimated_cycles': total_cycles,
            'estimated_life': min(1e6, estimated_life) if estimated_life != float('inf') else 'Infinite',
            'fatigue_status': fatigue_status
        }
    
    def _calculate_weight(self, chamber_analysis: Dict, nozzle_analysis: Dict,
                        end_cap_analysis: Dict, mat_props: Dict) -> Dict:
        """Calculate structural weight"""
        
        density = mat_props['density']
        
        # Chamber weight
        chamber_thickness = chamber_analysis['recommended_thickness'] / 1000  # m
        chamber_diameter = chamber_analysis['diameter'] / 1000  # m
        chamber_length = chamber_analysis['length'] / 1000  # m
        
        chamber_volume = np.pi * ((chamber_diameter/2 + chamber_thickness)**2 - (chamber_diameter/2)**2) * chamber_length
        chamber_weight = chamber_volume * density
        
        # Nozzle weight (simplified)
        nozzle_weight = chamber_weight * 0.3  # Estimate as 30% of chamber weight
        
        # End caps weight
        end_cap_thickness = min(end_cap_analysis['flat_head_thickness'], end_cap_analysis['dished_head_thickness']) / 1000
        end_cap_area = np.pi * (chamber_diameter/2 + chamber_thickness)**2
        end_caps_weight = 2 * end_cap_area * end_cap_thickness * density  # Two end caps
        
        # Total weight
        total_weight = chamber_weight + nozzle_weight + end_caps_weight
        
        return {
            'chamber_weight': chamber_weight,  # kg
            'nozzle_weight': nozzle_weight,    # kg
            'end_caps_weight': end_caps_weight,  # kg
            'total_weight': total_weight,      # kg
            'weight_breakdown': {
                'chamber_percent': chamber_weight / total_weight * 100,
                'nozzle_percent': nozzle_weight / total_weight * 100,
                'end_caps_percent': end_caps_weight / total_weight * 100
            }
        }
    
    def _analyze_safety_factors(self, chamber_analysis: Dict, nozzle_analysis: Dict,
                              end_cap_analysis: Dict, mat_props: Dict) -> Dict:
        """Analyze overall safety factors"""
        
        min_safety_factor = min(
            chamber_analysis['hoop_safety_factor'],
            chamber_analysis['von_mises_safety_factor'],
            nozzle_analysis['safety_factor'],
            end_cap_analysis['head_safety_factor']
        )
        
        # Risk assessment
        if min_safety_factor < 2.0:
            risk_level = 'HIGH'
            status = 'UNSAFE'
        elif min_safety_factor < 3.0:
            risk_level = 'MEDIUM'
            status = 'MARGINAL'
        elif min_safety_factor < 4.0:
            risk_level = 'LOW'
            status = 'ACCEPTABLE'
        else:
            risk_level = 'VERY LOW'
            status = 'SAFE'
        
        recommendations = []
        if min_safety_factor < 3.0:
            recommendations.append('Increase wall thickness')
            recommendations.append('Consider higher strength material')
        if chamber_analysis['hoop_safety_factor'] < 3.0:
            recommendations.append('Increase chamber wall thickness')
        if nozzle_analysis['safety_factor'] < 3.0:
            recommendations.append('Increase nozzle throat thickness')
        
        return {
            'minimum_safety_factor': min_safety_factor,
            'risk_level': risk_level,
            'status': status,
            'safety_factors': {
                'chamber_hoop': chamber_analysis['hoop_safety_factor'],
                'chamber_von_mises': chamber_analysis['von_mises_safety_factor'],
                'nozzle': nozzle_analysis['safety_factor'],
                'end_cap': end_cap_analysis['head_safety_factor']
            },
            'recommendations': recommendations
        }