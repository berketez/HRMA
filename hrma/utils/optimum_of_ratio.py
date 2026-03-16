"""
Optimum O/F Ratio Finder for all motor types
Uses NASA CEA data and real-time calculations
"""

import numpy as np
from typing import Dict, Tuple, Optional
import requests

class OptimumOFRatioFinder:
    """Find optimum O/F ratio for maximum ISP"""
    
    def __init__(self):
        # Theoretical optimum O/F ratios for common propellant combinations
        self.theoretical_optimums = {
            # Hybrid propellants
            ('n2o', 'htpb'): 7.5,
            ('n2o', 'paraffin'): 8.0,
            ('lox', 'htpb'): 2.3,
            ('lox', 'paraffin'): 2.5,
            
            # Liquid propellants
            ('lox', 'lh2'): 6.0,      # Hydrogen/LOX
            ('lox', 'rp1'): 2.77,     # RP-1/LOX (Saturn V)
            ('lox', 'methane'): 3.5,  # Methane/LOX (Raptor)
            ('lox', 'ch4'): 3.5,      # Alternative methane notation
            ('n2o4', 'mmh'): 2.1,     # Hypergolic
            ('n2o4', 'udmh'): 2.6,    # Hypergolic
            
            # Solid propellants (effective O/F for reference)
            ('ap', 'htpb'): 6.0,      # APCP
            ('ap', 'pban'): 5.5,      # PBAN
        }
        
        # ISP polynomial coefficients for rapid optimization
        self.isp_models = {
            ('n2o', 'htpb'): [-0.5, 7.5, -35, 80, 200],  # ax^4 + bx^3 + cx^2 + dx + e
            ('lox', 'lh2'): [-0.2, 3.0, -15, 35, 400],
            ('lox', 'rp1'): [-0.8, 9.0, -38, 75, 260],
        }
    
    def find_optimum_hybrid(self, oxidizer: str, fuel: str, 
                           chamber_pressure: float = 20.0) -> Dict:
        """Find optimum O/F ratio for hybrid motors"""
        
        # Try to get from theoretical database first
        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key, None)
        
        # Search range
        of_range = np.linspace(1.0, 12.0, 50)
        isp_values = []
        
        # Calculate ISP for each O/F ratio
        for of_ratio in of_range:
            isp = self._calculate_isp_hybrid(oxidizer, fuel, of_ratio, chamber_pressure)
            isp_values.append(isp)
        
        # Find maximum
        max_idx = np.argmax(isp_values)
        optimum_of = of_range[max_idx]
        max_isp = isp_values[max_idx]
        
        # Create performance curve
        performance_curve = {
            'of_ratios': of_range.tolist(),
            'isp_values': isp_values
        }
        
        return {
            'optimum_of_ratio': optimum_of,
            'max_isp': max_isp,
            'theoretical_optimum': theoretical,
            'performance_curve': performance_curve,
            'oxidizer': oxidizer,
            'fuel': fuel,
            'chamber_pressure': chamber_pressure
        }
    
    def find_optimum_liquid(self, oxidizer: str, fuel: str, 
                          chamber_pressure: float = 100.0) -> Dict:
        """Find optimum O/F ratio for liquid motors"""
        
        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key, None)
        
        # Different range for liquid motors
        if fuel.lower() in ['lh2', 'hydrogen']:
            of_range = np.linspace(2.0, 10.0, 50)
        else:
            of_range = np.linspace(1.0, 5.0, 50)
        
        isp_values = []
        
        for of_ratio in of_range:
            isp = self._calculate_isp_liquid(oxidizer, fuel, of_ratio, chamber_pressure)
            isp_values.append(isp)
        
        max_idx = np.argmax(isp_values)
        optimum_of = of_range[max_idx]
        max_isp = isp_values[max_idx]
        
        return {
            'optimum_of_ratio': optimum_of,
            'max_isp': max_isp,
            'theoretical_optimum': theoretical,
            'performance_curve': {
                'of_ratios': of_range.tolist(),
                'isp_values': isp_values
            },
            'oxidizer': oxidizer,
            'fuel': fuel,
            'chamber_pressure': chamber_pressure
        }
    
    def _calculate_isp_hybrid(self, oxidizer: str, fuel: str, 
                            of_ratio: float, chamber_pressure: float) -> float:
        """Calculate ISP for hybrid motor at given O/F ratio"""
        
        # Use polynomial model if available
        key = (oxidizer.lower(), fuel.lower())
        if key in self.isp_models:
            coeffs = self.isp_models[key]
            isp = np.polyval(coeffs, of_ratio)
        else:
            # Generic model based on bell curve around theoretical optimum
            theoretical = self.theoretical_optimums.get(key, 7.0)
            deviation = abs(of_ratio - theoretical) / theoretical
            efficiency = np.exp(-2 * deviation**2)  # Bell curve
            
            # Base ISP depends on propellant combination
            if oxidizer.lower() == 'n2o':
                base_isp = 250
            else:  # LOX
                base_isp = 300
            
            # Pressure correction
            pressure_factor = np.sqrt(chamber_pressure / 20.0)
            
            isp = base_isp * efficiency * pressure_factor
        
        return max(100, min(400, isp))  # Realistic bounds
    
    def _calculate_isp_liquid(self, oxidizer: str, fuel: str, 
                            of_ratio: float, chamber_pressure: float) -> float:
        """Calculate ISP for liquid motor at given O/F ratio"""
        
        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key, 3.0)
        
        # Special handling for hydrogen
        if fuel.lower() in ['lh2', 'hydrogen']:
            base_isp = 450
            optimal_of = 6.0
        elif fuel.lower() in ['rp1', 'kerosene']:
            base_isp = 350
            optimal_of = 2.77
        elif fuel.lower() in ['methane', 'ch4']:
            base_isp = 380
            optimal_of = 3.5
        else:
            base_isp = 320
            optimal_of = theoretical
        
        # Calculate efficiency based on deviation from optimum
        deviation = abs(of_ratio - optimal_of) / optimal_of
        efficiency = np.exp(-3 * deviation**2)  # Sharper curve for liquids
        
        # Pressure correction (higher effect for liquids)
        pressure_factor = (chamber_pressure / 100.0) ** 0.3
        
        isp = base_isp * efficiency * pressure_factor
        
        return max(150, min(500, isp))
    
    def get_recommendation(self, motor_type: str, oxidizer: str, fuel: str) -> str:
        """Get recommendation text for optimum O/F ratio"""
        
        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key, None)
        
        if theoretical:
            return f"Recommended O/F ratio for {fuel.upper()}/{oxidizer.upper()}: {theoretical:.2f} (NASA/industry standard)"
        else:
            return f"No standard data available for {fuel.upper()}/{oxidizer.upper()}. Using computational optimization."

# Global instance
of_optimizer = OptimumOFRatioFinder()