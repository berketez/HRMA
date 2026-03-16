"""
Gerçek Zamanlı Validasyon ve Uyarı Sistemi
Rocket motor tasarım parametrelerinin doğruluğunu kontrol eder
"""

import numpy as np
from typing import List, Dict, Tuple
import warnings

class ValidationSystem:
    """Gerçek zamanlı validasyon ve uyarı sistemi"""
    
    def __init__(self):
        # Sutton & Biblarz, NASA SP-8089, ve AIAA standartları
        self.performance_limits = {
            'specific_impulse': {
                'n2o_htpb': (180, 250),    # s
                'n2o_paraffin': (190, 260),
                'lox_htpb': (220, 280),
            },
            'chamber_pressure': (5, 100),   # bar
            'of_ratio': {
                'n2o_htpb': (0.5, 6.0),
                'n2o_paraffin': (1.0, 8.0),
            },
            'c_star': {
                'n2o_htpb': (1350, 1650),  # m/s
                'n2o_paraffin': (1400, 1700),
            },
            'gamma': (1.10, 1.35),
            'gas_constant': (200, 500),     # J/kg·K
            'temperature': (2500, 3500),    # K
        }
        
        self.injector_limits = {
            'reynolds_number': (1000, 200000),
            'pressure_drop_ratio': (0.10, 0.35),  # ΔP/Pc
            'exit_velocity': (10, 100),           # m/s
            'hole_diameter': (0.2, 5.0),          # mm
        }
        
        self.geometry_limits = {
            'expansion_ratio': (4, 250),
            'port_diameter_initial': (5, 100),    # mm
            'port_diameter_final': (10, 200),     # mm
            'chamber_length': (50, 2000),         # mm
        }
    
    def validate_performance_data(self, data: Dict, propellant_combo: str) -> List[str]:
        """Performans verilerini doğrula"""
        warnings_list = []
        
        # Specific Impulse
        isp = data.get('isp', 0)
        isp_limits = self.performance_limits['specific_impulse'].get(propellant_combo, (150, 300))
        if not (isp_limits[0] <= isp <= isp_limits[1]):
            severity = "KRITIK" if isp < isp_limits[0] * 0.8 or isp > isp_limits[1] * 1.2 else "UYARI"
            warnings_list.append(f"{severity}: Isp = {isp:.1f}s (normal: {isp_limits[0]}-{isp_limits[1]}s)")
        
        # C-star
        c_star = data.get('c_star', 0)
        c_star_limits = self.performance_limits['c_star'].get(propellant_combo, (1200, 1800))
        if not (c_star_limits[0] <= c_star <= c_star_limits[1]):
            severity = "KRITIK" if c_star < c_star_limits[0] * 0.9 else "UYARI"
            warnings_list.append(f"{severity}: C* = {c_star:.0f}m/s (normal: {c_star_limits[0]}-{c_star_limits[1]}m/s)")
        
        # Gamma
        gamma = data.get('gamma', 0)
        gamma_limits = self.performance_limits['gamma']
        if not (gamma_limits[0] <= gamma <= gamma_limits[1]):
            warnings_list.append(f"UYARI: γ = {gamma:.3f} (normal: {gamma_limits[0]}-{gamma_limits[1]})")
        
        # O/F Ratio
        of_ratio = data.get('of_ratio', 0)
        of_limits = self.performance_limits['of_ratio'].get(propellant_combo, (0.5, 8.0))
        if not (of_limits[0] <= of_ratio <= of_limits[1]):
            warnings_list.append(f"UYARI: O/F = {of_ratio:.2f} (optimal: {of_limits[0]}-{of_limits[1]})")
        
        return warnings_list
    
    def validate_injector_data(self, data: Dict) -> List[str]:
        """İnjektör verilerini doğrula"""
        warnings_list = []
        
        # Reynolds Number
        reynolds = data.get('reynolds_number', 0)
        re_limits = self.injector_limits['reynolds_number']
        if not (re_limits[0] <= reynolds <= re_limits[1]):
            if reynolds < re_limits[0]:
                warnings_list.append(f"KRITIK: Re = {reynolds:.0f} (laminar akış riski, min: {re_limits[0]})")
            else:
                warnings_list.append(f"UYARI: Re = {reynolds:.0f} (çok yüksek, max: {re_limits[1]})")
        
        # Pressure Drop
        pressure_drop = data.get('pressure_drop', 0)
        chamber_pressure = data.get('chamber_pressure', 20)
        drop_ratio = pressure_drop / chamber_pressure if chamber_pressure > 0 else 0
        drop_limits = self.injector_limits['pressure_drop_ratio']
        
        if not (drop_limits[0] <= drop_ratio <= drop_limits[1]):
            if drop_ratio < drop_limits[0]:
                warnings_list.append(f"KRITIK: ΔP/Pc = {drop_ratio:.2f} (atomizasyon yetersiz, min: {drop_limits[0]})")
            else:
                warnings_list.append(f"UYARI: ΔP/Pc = {drop_ratio:.2f} (tank basıncı yüksek, max: {drop_limits[1]})")
        
        # Exit Velocity
        exit_velocity = data.get('exit_velocity', 0)
        vel_limits = self.injector_limits['exit_velocity']
        if not (vel_limits[0] <= exit_velocity <= vel_limits[1]):
            warnings_list.append(f"UYARI: v_exit = {exit_velocity:.1f}m/s (optimal: {vel_limits[0]}-{vel_limits[1]}m/s)")
        
        return warnings_list
    
    def validate_geometry_data(self, data: Dict) -> List[str]:
        """Geometri verilerini doğrula"""
        warnings_list = []
        
        # Port Diameters
        d_port_initial = data.get('port_diameter_initial', 0) * 1000  # m to mm
        d_port_final = data.get('port_diameter_final', 0) * 1000
        d_chamber = data.get('chamber_diameter', 0) * 1000
        
        port_limits = self.geometry_limits['port_diameter_initial']
        if d_port_initial > 0 and not (port_limits[0] <= d_port_initial <= port_limits[1]):
            warnings_list.append(f"UYARI: İlk port çapı = {d_port_initial:.1f}mm (tipik: {port_limits[0]}-{port_limits[1]}mm)")
        
        # Port Growth Check
        if d_port_initial > 0 and d_port_final > 0:
            growth_ratio = d_port_final / d_port_initial
            if growth_ratio < 1.2:
                warnings_list.append("UYARI: Port çapı artışı düşük (min 20% artış önerilir)")
            elif growth_ratio > 3.0:
                warnings_list.append("KRITIK: Aşırı port çapı artışı (yapısal sorunlara yol açabilir)")
        
        # Chamber vs Port Diameter
        if d_chamber > 0 and d_port_final > 0:
            if d_port_final > d_chamber * 0.8:
                warnings_list.append("KRITIK: Final port çapı kamara çapının %80'ini aşıyor")
        
        # Expansion Ratio
        expansion_ratio = data.get('expansion_ratio', 0)
        exp_limits = self.geometry_limits['expansion_ratio']
        if expansion_ratio > 0 and not (exp_limits[0] <= expansion_ratio <= exp_limits[1]):
            warnings_list.append(f"UYARI: ε = {expansion_ratio:.1f} (tipik: {exp_limits[0]}-{exp_limits[1]})")
        
        return warnings_list
    
    def check_sutton_biblarz_criteria(self, data: Dict) -> List[str]:
        """Sutton & Biblarz kitabından kritik tasarım kriterleri"""
        warnings_list = []
        
        # Kısık oranı kontrol (Throat Loading)
        thrust = data.get('thrust', 0)
        throat_area = data.get('throat_area', 0)
        if thrust > 0 and throat_area > 0:
            throat_loading = thrust / (throat_area * 1e6)  # N/mm²
            if throat_loading > 2.0:
                warnings_list.append(f"KRITIK: Kısık yüklenmesi = {throat_loading:.2f} N/mm² (max: 2.0)")
        
        # L* kontrolü (Karakteristik uzunluk)
        l_star = data.get('l_star', 0)
        if l_star > 0:
            if l_star < 0.5:
                warnings_list.append("KRITIK: L* çok düşük (yanma verimliliği düşük)")
            elif l_star > 2.0:
                warnings_list.append("UYARI: L* çok yüksek (gereksiz ağırlık)")
        
        # Regresyon hızı kontrolü
        regression_rate = data.get('regression_rate', 0) * 1000  # m/s to mm/s
        if regression_rate > 0:
            if regression_rate < 0.5:
                warnings_list.append("UYARI: Regresyon hızı düşük (yanma süresi uzayabilir)")
            elif regression_rate > 5.0:
                warnings_list.append("KRITIK: Regresyon hızı çok yüksek (kontrol zorluğu)")
        
        return warnings_list
    
    def comprehensive_validation(self, motor_data: Dict, injector_data: Dict, 
                               propellant_combo: str = 'n2o_htpb') -> Dict:
        """Kapsamlı validasyon"""
        all_warnings = []
        
        # Tüm validasyonları çalıştır
        all_warnings.extend(self.validate_performance_data(motor_data, propellant_combo))
        all_warnings.extend(self.validate_injector_data(injector_data))
        all_warnings.extend(self.validate_geometry_data(motor_data))
        all_warnings.extend(self.check_sutton_biblarz_criteria(motor_data))
        
        # Kritik/uyarı ayrımı
        critical_warnings = [w for w in all_warnings if 'KRITIK' in w]
        regular_warnings = [w for w in all_warnings if 'UYARI' in w and 'KRITIK' not in w]
        
        # Genel değerlendirme
        if critical_warnings:
            overall_status = "KRITIK SORUNLAR MEVCUT"
        elif regular_warnings:
            overall_status = "UYARILAR MEVCUT"
        else:
            overall_status = "TUM PARAMETRELER NORMAL"
        
        return {
            'overall_status': overall_status,
            'critical_warnings': critical_warnings,
            'regular_warnings': regular_warnings,
            'total_warnings': len(all_warnings),
            'validation_passed': len(critical_warnings) == 0
        }

# Global instance
validator = ValidationSystem()