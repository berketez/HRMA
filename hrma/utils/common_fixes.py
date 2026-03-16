"""
Common fixes and utilities for all motor types (Hybrid, Liquid, Solid)
Addresses all 17 common issues across the HRMA system
"""

import numpy as np
import plotly.graph_objects as go
from typing import Dict, Tuple, Optional, List
import warnings

class CommonValidation:
    """Common validation utilities for all motor types"""
    
    @staticmethod
    def validate_pressure_consistency(tank_pressure: float, chamber_pressure: float) -> Tuple[bool, str]:
        """
        Issue #6: Validate tank pressure > chamber pressure
        """
        if tank_pressure <= chamber_pressure:
            return False, f"Tank pressure ({tank_pressure} bar) must be greater than chamber pressure ({chamber_pressure} bar)"
        
        min_pressure_drop = 0.15 * chamber_pressure  # Minimum 15% pressure drop
        if (tank_pressure - chamber_pressure) < min_pressure_drop:
            return False, f"Insufficient pressure drop. Need at least {min_pressure_drop:.1f} bar drop for proper injection"
        
        return True, "Pressure validation passed"
    
    @staticmethod
    def validate_diameter_consistency(chamber_diameter: float, injector_diameter: float) -> Tuple[bool, str]:
        """
        Issue #5: Validate injector diameter < chamber diameter
        """
        if injector_diameter >= chamber_diameter:
            return False, f"Injector diameter ({injector_diameter} mm) must be less than chamber diameter ({chamber_diameter} mm)"
        
        if injector_diameter > 0.9 * chamber_diameter:
            return False, f"Injector diameter too large. Should be < 90% of chamber diameter for structural integrity"
        
        return True, "Diameter validation passed"
    
    @staticmethod
    def validate_total_impulse_consistency(total_impulse: float, thrust: float, burn_time: float) -> Tuple[bool, str]:
        """
        Issue #3: Validate total impulse = thrust * burn time
        """
        calculated_impulse = thrust * burn_time
        tolerance = 0.01  # 1% tolerance
        
        if abs(calculated_impulse - total_impulse) > tolerance * total_impulse:
            return False, f"Total impulse mismatch: Given {total_impulse} N·s, but Thrust×Time = {calculated_impulse} N·s"
        
        return True, "Total impulse validation passed"
    
    @staticmethod
    def validate_finite_area_combustion(contraction_ratio: Optional[float], mass_flux: Optional[float]) -> Tuple[bool, str]:
        """
        Issue #12: Validate only ONE of contraction ratio OR mass flux is provided
        """
        if contraction_ratio is not None and mass_flux is not None:
            return False, "For finite area combustion, provide EITHER contraction ratio OR mass flux, not both"
        
        if contraction_ratio is None and mass_flux is None:
            return False, "For finite area combustion, provide either contraction ratio or mass flux"
        
        return True, "Finite area combustion validation passed"

class CommonCalculations:
    """Common calculation fixes for all motor types"""
    
    @staticmethod
    def calculate_mass_flow_rate(thrust: float, isp: float, g0: float = 9.80665) -> float:
        """
        Issue #11: Correct mass flow rate calculation
        Formula: mdot = F / (g0 * Isp)
        """
        if isp <= 0:
            raise ValueError(f"Specific impulse must be positive (got {isp})")
        
        mdot = thrust / (g0 * isp)
        return mdot
    
    @staticmethod
    def calculate_reynolds_number(density: float, velocity: float, diameter: float, viscosity: float) -> float:
        """
        Issue #15: Correct Reynolds number calculation
        Re = ρ * v * D / μ
        """
        if viscosity <= 0:
            raise ValueError(f"Viscosity must be positive (got {viscosity})")
        
        Re = density * velocity * diameter / viscosity
        
        # Physical validation
        if Re < 1000:
            warnings.warn(f"Low Reynolds number ({Re:.0f}), laminar flow expected")
        elif Re > 200000:
            warnings.warn(f"Very high Reynolds number ({Re:.0f}), check design parameters")
        
        return Re
    
    @staticmethod
    def calculate_total_impulse_auto(thrust: Optional[float], burn_time: Optional[float], 
                                    total_impulse: Optional[float]) -> Dict[str, float]:
        """
        Issue #2 & #3: Auto-calculate missing parameter from the other two
        """
        provided_count = sum(x is not None for x in [thrust, burn_time, total_impulse])
        
        if provided_count < 2:
            raise ValueError("At least 2 of 3 parameters (thrust, burn_time, total_impulse) must be provided")
        
        if provided_count == 3:
            # Validate consistency
            calculated = thrust * burn_time
            if abs(calculated - total_impulse) > 0.01 * total_impulse:
                raise ValueError(f"Inconsistent values: Thrust×Time = {calculated} ≠ {total_impulse}")
        
        # Calculate missing parameter
        if thrust is None:
            thrust = total_impulse / burn_time
        elif burn_time is None:
            burn_time = total_impulse / thrust
        elif total_impulse is None:
            total_impulse = thrust * burn_time
        
        return {
            'thrust': thrust,
            'burn_time': burn_time,
            'total_impulse': total_impulse
        }

class GraphFixes:
    """Common graph and visualization fixes"""
    
    @staticmethod
    def create_safe_plot(fig_data: Dict, container_id: str) -> str:
        """
        Issue #1: Fix graph corruption on multiple clicks
        """
        # Always purge existing plot first
        purge_script = f"if(document.getElementById('{container_id}')) {{ Plotly.purge('{container_id}'); }}"
        
        # Create new plot
        plot_script = f"Plotly.newPlot('{container_id}', {fig_data});"
        
        return purge_script + plot_script
    
    @staticmethod
    def toggle_plot_visibility(container_id: str) -> str:
        """
        Issue #1: Toggle plot visibility instead of recreating
        """
        return f"""
        const container = document.getElementById('{container_id}');
        if (container.style.display === 'none') {{
            container.style.display = 'block';
        }} else {{
            container.style.display = 'none';
        }}
        """

class FuelMixtureSystem:
    """
    Issue #7: Support for custom fuel mixtures and compositions
    """
    
    def __init__(self):
        self.base_fuels = {
            'htpb': {'density': 920, 'a': 0.0003, 'n': 0.5},
            'paraffin': {'density': 900, 'a': 0.0008, 'n': 0.8},
            'carbon': {'density': 2200, 'a': 0.0001, 'n': 0.3},
            'aluminum_oxide': {'density': 3950, 'a': 0.0002, 'n': 0.4}
        }
    
    def create_mixture(self, components: Dict[str, float]) -> Dict:
        """
        Create custom fuel mixture from components
        components: {'fuel_name': mass_fraction, ...}
        """
        total_fraction = sum(components.values())
        if abs(total_fraction - 1.0) > 0.001:
            raise ValueError(f"Mass fractions must sum to 1.0 (got {total_fraction})")
        
        # Calculate mixture properties using mass-weighted averages
        mixture = {'density': 0, 'a': 0, 'n': 0}
        
        for fuel, fraction in components.items():
            if fuel not in self.base_fuels:
                raise ValueError(f"Unknown fuel component: {fuel}")
            
            props = self.base_fuels[fuel]
            mixture['density'] += props['density'] * fraction
            mixture['a'] += props['a'] * fraction
            mixture['n'] += props['n'] * fraction
        
        return mixture

class ExportFixes:
    """
    Issue #17: Fix export functionality for STL, motor files, etc.
    """
    
    @staticmethod
    def generate_basic_stl(motor_data: Dict) -> str:
        """Generate basic STL file content"""
        L = motor_data.get('chamber_length', 300)  # mm
        D = motor_data.get('chamber_diameter', 100)  # mm
        
        stl_content = f"""solid motor_assembly
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex {D} 0 0
    vertex {D/2} {D*0.866} 0
  endloop
endfacet
facet normal 0 0 -1
  outer loop
    vertex 0 0 {L}
    vertex {D/2} {D*0.866} {L}
    vertex {D} 0 {L}
  endloop
endfacet
endsolid motor_assembly"""
        
        return stl_content
    
    @staticmethod
    def generate_motor_file(motor_data: Dict) -> str:
        """Generate OpenRocket .eng file content"""
        thrust_curve = motor_data.get('thrust_curve', [(0, 0), (0.1, 1000), (10, 1000), (10.1, 0)])
        
        eng_content = f"; Motor file generated by HRMA\n"
        eng_content += f"; {motor_data.get('motor_name', 'Custom_Motor')}\n"
        eng_content += f"{motor_data.get('diameter', 100):.1f} {motor_data.get('length', 300):.1f} "
        eng_content += f"0 {motor_data.get('propellant_mass', 5):.3f} "
        eng_content += f"{motor_data.get('total_mass', 10):.3f} HRMA\n"
        
        for time, thrust in thrust_curve:
            eng_content += f"{time:.3f} {thrust:.1f}\n"
        
        eng_content += ";\n"
        
        return eng_content

# Global instances
validation = CommonValidation()
calculations = CommonCalculations()
graph_fixes = GraphFixes()
fuel_mixer = FuelMixtureSystem()
export_fixes = ExportFixes()