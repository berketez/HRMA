"""
Advanced Nozzle Design Module
Detailed nozzle geometry calculations including contour design
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional

class NozzleDesigner:
    """Advanced nozzle design and analysis"""
    
    def __init__(self):
        self.g0 = 9.81  # m/s²
    
    def design_nozzle(self, throat_area: float, expansion_ratio: float, 
                     chamber_pressure: float, exit_pressure: float,
                     nozzle_type: str = 'bell', efficiency: float = 0.98) -> Dict:
        """
        Complete nozzle design with detailed geometry
        
        Args:
            throat_area: Throat area in m²
            expansion_ratio: Area ratio Ae/At
            chamber_pressure: Chamber pressure in bar
            exit_pressure: Exit pressure in bar
            nozzle_type: 'bell', 'conical', or 'parabolic'
            efficiency: Nozzle efficiency factor
            
        Returns:
            Detailed nozzle design parameters
        """
        
        # Basic dimensions
        dt = 2 * np.sqrt(throat_area / np.pi)  # Throat diameter
        exit_area = throat_area * expansion_ratio
        de = 2 * np.sqrt(exit_area / np.pi)  # Exit diameter
        
        # Nozzle contour design
        contour = self._design_nozzle_contour(dt, de, nozzle_type)
        
        # Performance calculations
        performance = self._calculate_nozzle_performance(
            throat_area, exit_area, chamber_pressure, exit_pressure, efficiency
        )
        
        # Geometric parameters
        geometry = self._calculate_nozzle_geometry(dt, de, contour, nozzle_type)
        
        return {
            'basic_dimensions': {
                'throat_diameter': dt * 1000,  # mm
                'exit_diameter': de * 1000,    # mm
                'throat_area': throat_area * 1e6,  # mm²
                'exit_area': exit_area * 1e6,      # mm²
                'expansion_ratio': expansion_ratio
            },
            'geometry': geometry,
            'contour': contour,
            'performance': performance,
            'nozzle_type': nozzle_type
        }
    
    def _design_nozzle_contour(self, dt: float, de: float, nozzle_type: str) -> Dict:
        """Design nozzle contour based on type"""
        
        if nozzle_type == 'bell':
            return self._design_bell_nozzle(dt, de)
        elif nozzle_type == 'conical':
            return self._design_conical_nozzle(dt, de)
        elif nozzle_type == 'parabolic':
            return self._design_parabolic_nozzle(dt, de)
        else:
            # Default to bell
            return self._design_bell_nozzle(dt, de)
    
    def _design_bell_nozzle(self, dt: float, de: float) -> Dict:
        """Design bell nozzle contour (most efficient)"""
        
        rt = dt / 2  # Throat radius
        re = de / 2  # Exit radius
        
        # Bell nozzle parameters
        # Convergent section
        Rc = 1.5 * rt  # Chamber radius
        Rn = 0.382 * rt  # Throat radius of curvature
        
        # Divergent section
        theta_n = 30.0  # Throat angle (degrees)
        theta_e = 8.0   # Exit angle (degrees)
        
        # Calculate lengths
        # Convergent length
        Lc = 0.8 * Rc  # Convergent length
        
        # Divergent length (bell formula)
        Ld = 0.8 * (np.sqrt(de**2 - dt**2) / (2 * np.tan(np.radians(15))))
        
        # Total length
        Lt = Lc + Ld
        
        return {
            'convergent': {
                'chamber_radius': Rc * 1000,  # mm
                'throat_radius_curvature': Rn * 1000,  # mm
                'length': Lc * 1000,  # mm
                'contraction_ratio': (Rc / rt)**2
            },
            'divergent': {
                'length': Ld * 1000,  # mm
                'throat_angle': theta_n,  # degrees
                'exit_angle': theta_e,    # degrees
                'type': 'bell'
            },
            'total_length': Lt * 1000,  # mm
            'length_efficiency': 0.98  # Bell nozzles are most efficient
        }
    
    def _design_conical_nozzle(self, dt: float, de: float) -> Dict:
        """Design conical nozzle contour"""
        
        rt = dt / 2
        re = de / 2
        
        # Conical nozzle parameters
        theta = 15.0  # Half angle (degrees)
        
        # Convergent section
        Rc = 1.5 * rt
        Lc = 0.8 * Rc
        
        # Divergent section
        Ld = (re - rt) / np.tan(np.radians(theta))
        
        # Total length
        Lt = Lc + Ld
        
        return {
            'convergent': {
                'chamber_radius': Rc * 1000,
                'length': Lc * 1000,
                'contraction_ratio': (Rc / rt)**2
            },
            'divergent': {
                'length': Ld * 1000,
                'half_angle': theta,
                'type': 'conical'
            },
            'total_length': Lt * 1000,
            'length_efficiency': 0.95  # Slightly less efficient than bell
        }
    
    def _design_parabolic_nozzle(self, dt: float, de: float) -> Dict:
        """Design parabolic nozzle contour"""
        
        rt = dt / 2
        re = de / 2
        
        # Parabolic nozzle parameters
        Rc = 1.5 * rt
        Lc = 0.8 * Rc
        
        # Divergent section - parabolic
        Ld = 1.2 * (re - rt) / np.tan(np.radians(15))  # Longer than conical
        
        Lt = Lc + Ld
        
        return {
            'convergent': {
                'chamber_radius': Rc * 1000,
                'length': Lc * 1000,
                'contraction_ratio': (Rc / rt)**2
            },
            'divergent': {
                'length': Ld * 1000,
                'type': 'parabolic',
                'curvature_parameter': 0.8
            },
            'total_length': Lt * 1000,
            'length_efficiency': 0.96
        }
    
    def _calculate_nozzle_performance(self, throat_area: float, exit_area: float,
                                    chamber_pressure: float, exit_pressure: float,
                                    efficiency: float, gamma: float = 1.25, 
                                    R_specific: float = 300, T_chamber: float = 3000) -> Dict:
        """Calculate nozzle performance parameters"""
        
        expansion_ratio = exit_area / throat_area
        pressure_ratio = chamber_pressure / exit_pressure
        
        # Characteristic velocity
        c_star = np.sqrt(R_specific * T_chamber / gamma) / \
                ((2 / (gamma + 1))**((gamma + 1) / (2 * (gamma - 1))))
        
        # Thrust coefficient (ideal)
        cf_ideal = np.sqrt(2 * gamma**2 / (gamma - 1) * 
                          (2 / (gamma + 1))**((gamma + 1) / (gamma - 1)) *
                          (1 - (exit_pressure / chamber_pressure)**((gamma - 1) / gamma)))
        
        # Apply efficiency
        cf_actual = cf_ideal * efficiency
        
        # Specific impulse
        isp = cf_actual * c_star / self.g0
        
        # Exit velocity
        ve = cf_actual * c_star
        
        # Nozzle efficiency
        eta_nozzle = cf_actual / cf_ideal
        
        return {
            'characteristic_velocity': c_star,
            'thrust_coefficient_ideal': cf_ideal,
            'thrust_coefficient_actual': cf_actual,
            'specific_impulse': isp,
            'exit_velocity': ve,
            'nozzle_efficiency': eta_nozzle,
            'pressure_ratio': pressure_ratio,
            'expansion_ratio': expansion_ratio
        }
    
    def _calculate_nozzle_geometry(self, dt: float, de: float, 
                                 contour: Dict, nozzle_type: str) -> Dict:
        """Calculate detailed nozzle geometry parameters"""
        
        rt = dt / 2
        re = de / 2
        
        # Areas
        At = np.pi * rt**2
        Ae = np.pi * re**2
        
        # Surface area calculation
        if nozzle_type == 'conical':
            theta = contour['divergent']['half_angle']
            L_div = contour['divergent']['length'] / 1000  # Convert to m
            surface_area = np.pi * (rt + re) * np.sqrt(L_div**2 + (re - rt)**2)
        else:
            # Approximate for bell/parabolic
            L_div = contour['divergent']['length'] / 1000
            surface_area = np.pi * (rt + re) * L_div * 1.1  # 10% increase for curvature
        
        # Volume calculation
        L_total = contour['total_length'] / 1000
        volume = np.pi * L_total * (rt**2 + rt * re + re**2) / 3
        
        # Mass estimation (assuming steel, density ≈ 7850 kg/m³)
        wall_thickness = max(0.003, dt * 0.1)  # Minimum 3mm or 10% of throat diameter
        nozzle_mass = surface_area * wall_thickness * 7850
        
        return {
            'surface_area': surface_area * 1e6,  # mm²
            'volume': volume * 1e9,  # mm³
            'wall_thickness': wall_thickness * 1000,  # mm
            'estimated_mass': nozzle_mass,  # kg
            'throat_radius': rt * 1000,  # mm
            'exit_radius': re * 1000,    # mm
            'length_to_diameter_ratio': (contour['total_length'] / 1000) / dt
        }
    
    def calculate_nozzle_flow_properties(self, nozzle_data: Dict, 
                                       mass_flow_rate: float,
                                       chamber_conditions: Dict) -> Dict:
        """Calculate flow properties throughout the nozzle"""
        
        gamma = 1.25
        R = chamber_conditions.get('gas_constant', 300)
        T_chamber = chamber_conditions.get('temperature', 3000)
        P_chamber = chamber_conditions.get('pressure', 40)  # bar
        
        # Throat conditions (choked flow)
        T_throat = T_chamber * (2 / (gamma + 1))
        P_throat = P_chamber * (2 / (gamma + 1))**(gamma / (gamma - 1))
        rho_throat = P_throat * 1e5 / (R * T_throat)  # kg/m³
        v_throat = np.sqrt(gamma * R * T_throat)
        
        # Exit conditions
        expansion_ratio = nozzle_data['basic_dimensions']['expansion_ratio']
        
        # Calculate exit Mach number from area ratio
        def mach_from_area_ratio(epsilon, gamma):
            """Calculate exit Mach number from area ratio using iterative method"""
            # Simplified approximation for supersonic flow
            M_e = np.sqrt(2 / (gamma - 1) * ((epsilon)**(2 * (gamma - 1) / (gamma + 1)) - 1))
            return max(M_e, 1.01)  # Ensure supersonic
        
        M_exit = mach_from_area_ratio(expansion_ratio, gamma)
        
        # Calculate exit pressure from Mach number
        P_exit = P_chamber / ((1 + (gamma - 1) / 2 * M_exit**2)**(gamma / (gamma - 1)))
        T_exit = T_chamber / (1 + (gamma - 1) / 2 * M_exit**2)
        rho_exit = P_exit * 1e5 / (R * T_exit)
        v_exit = np.sqrt(2 * gamma * R * T_chamber / (gamma - 1) * 
                        (1 - (P_exit / P_chamber)**((gamma - 1) / gamma)))
        
        # Mach numbers
        a_throat = np.sqrt(gamma * R * T_throat)
        a_exit = np.sqrt(gamma * R * T_exit)
        
        M_throat = v_throat / a_throat  # Should be 1.0
        M_exit = v_exit / a_exit
        
        return {
            'chamber': {
                'temperature': T_chamber,
                'pressure': P_chamber,
                'density': P_chamber * 1e5 / (R * T_chamber),
                'velocity': 0,  # Negligible in chamber
                'mach_number': 0
            },
            'throat': {
                'temperature': T_throat,
                'pressure': P_throat,
                'density': rho_throat,
                'velocity': v_throat,
                'mach_number': M_throat,
                'sonic_velocity': a_throat
            },
            'exit': {
                'temperature': T_exit,
                'pressure': P_exit,
                'density': rho_exit,
                'velocity': v_exit,
                'mach_number': M_exit,
                'sonic_velocity': a_exit
            },
            'mass_flow_rate': mass_flow_rate,
            'area_ratios': {
                'throat': 1.0,
                'exit': expansion_ratio
            }
        }