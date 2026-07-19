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
        
        # 2026-07-15: Eski "polinom" katsayıları uydurmaydı ve N2O/HTPB için
        # 400 s Isp raporluyordu (gerçek teorik vakum ~250 s). Kaldırıldı;
        # yerine literatür tabanlı teorik vakum Isp tepe değerleri (Sutton,
        # Rocket Propulsion Elements, tipik CEA sonuçları) + çan eğrisi şekli
        # kullanılır. Bu araç bir TARAMA aracıdır: optimum O/F oranının YERİ
        # güvenilirdir, mutlak Isp için gerçek CEA hesabı esas alınmalıdır.
        self.peak_vac_isp = {
            ('n2o', 'htpb'): 250, ('n2o', 'paraffin'): 255,
            ('lox', 'htpb'): 330, ('lox', 'paraffin'): 335,
            ('lox', 'lh2'): 455, ('lox', 'rp1'): 355,
            ('lox', 'methane'): 365, ('lox', 'ch4'): 365,
            ('n2o4', 'mmh'): 335, ('n2o4', 'udmh'): 330,
        }
    
    def find_optimum_hybrid(self, oxidizer: str, fuel: str,
                           chamber_pressure: float = 20.0) -> Dict:
        """Find optimum O/F ratio for hybrid motors.

        Raises:
            ValueError: the propellant pair has no reference data (see
                _calculate_isp_hybrid). No silent default is produced.
        """

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
        """Calculate ISP for hybrid motor at given O/F ratio.

        Raises:
            ValueError: the propellant pair is not in the reference table.
                DUZELTME (v2.5.2): eski kod tabloda olmayan cift icin sessizce
                O/F=7.0 (N2O/HTPB degeri) ve 250 s tepe Isp varsayiyordu, yani
                yakit/oksitleyici secilmeden de 'optimum' uretiyordu. Sessiz
                varsayilan YASAK; cagiran taraf ya tam yanma analizini
                calistirmali ya da secimi duzeltmelidir.
        """
        # Çan eğrisi: tepe = literatür teorik vakum Isp, konum = teorik optimum
        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key)
        base_isp = self.peak_vac_isp.get(key)
        if theoretical is None or base_isp is None:
            # Kullaniciya gorunur metin -> Ingilizce.
            raise ValueError(
                f"No optimum O/F data for pair {oxidizer.upper()}+{fuel.upper()}; "
                f"run full combustion analysis or verify propellant selection.")
        deviation = abs(of_ratio - theoretical) / theoretical
        efficiency = np.exp(-2 * deviation**2)

        # Basınç düzeltmesi ZAYIF olmalı: Isp'nin Pc bağımlılığı c* üzerinden
        # yüzde birkaç mertebesindedir (eski sqrt(Pc/20) 30 bar'da +%22 veriyordu)
        pressure_factor = float(np.clip((chamber_pressure / 20.0) ** 0.05, 0.92, 1.08))

        isp = base_isp * efficiency * pressure_factor
        return max(50.0, float(isp))
    
    def _calculate_isp_liquid(self, oxidizer: str, fuel: str,
                            of_ratio: float, chamber_pressure: float) -> float:
        """Calculate ISP for liquid motor at given O/F ratio.

        Raises:
            ValueError: unknown fuel AND unknown propellant pair — same
                no-silent-default rule as the hybrid branch (v2.5.2).
        """
        key = (oxidizer.lower(), fuel.lower())
        theoretical = self.theoretical_optimums.get(key)

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
        elif theoretical is not None:
            base_isp = 320
            optimal_of = theoretical
        else:
            # Kullaniciya gorunur metin -> Ingilizce.
            raise ValueError(
                f"No optimum O/F data for pair {oxidizer.upper()}+{fuel.upper()}; "
                f"run full combustion analysis or verify propellant selection.")

        # Calculate efficiency based on deviation from optimum
        deviation = abs(of_ratio - optimal_of) / optimal_of
        efficiency = np.exp(-3 * deviation**2)  # Sharper curve for liquids
        
        # Basınç düzeltmesi zayıf tutulur (Isp ~ birkaç % / Pc dekadı)
        pressure_factor = float(np.clip((chamber_pressure / 100.0) ** 0.08, 0.90, 1.08))

        isp = base_isp * efficiency * pressure_factor
        return max(100.0, float(isp))
    
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