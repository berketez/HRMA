"""
Gerçek Zamanlı Validasyon ve Uyarı Sistemi
Rocket motor tasarım parametrelerinin doğruluğunu kontrol eder
"""

import numpy as np
from typing import List, Dict, Tuple
import warnings


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: dile bağlı sabit metin YERİNE yapısal kayıt.

    Dönen sözlük ``{"code", "params", "severity"}``. Dil tamamen frontend'e
    taşınır; frontend ``TF(code, params)`` ile yerelleştirilmiş metni kurar.
    ``severity`` ∈ {"critical", "warning", "info"} — kritik/uyarı ayrımı
    artık metin içeriğinden DEĞİL bu alandan yapılır (dil sızıntısı yok).
    """
    return {"code": code, "params": params, "severity": severity}


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
            sev = "critical" if isp < isp_limits[0] * 0.8 or isp > isp_limits[1] * 1.2 else "warning"
            warnings_list.append(_w("warn.validation.isp_out_of_range", sev,
                                    isp=round(float(isp), 1),
                                    lo=isp_limits[0], hi=isp_limits[1]))

        # C-star
        c_star = data.get('c_star', 0)
        c_star_limits = self.performance_limits['c_star'].get(propellant_combo, (1200, 1800))
        if not (c_star_limits[0] <= c_star <= c_star_limits[1]):
            sev = "critical" if c_star < c_star_limits[0] * 0.9 else "warning"
            warnings_list.append(_w("warn.validation.cstar_out_of_range", sev,
                                    cstar=round(float(c_star), 0),
                                    lo=c_star_limits[0], hi=c_star_limits[1]))

        # Gamma
        gamma = data.get('gamma', 0)
        gamma_limits = self.performance_limits['gamma']
        if not (gamma_limits[0] <= gamma <= gamma_limits[1]):
            warnings_list.append(_w("warn.validation.gamma_out_of_range", "warning",
                                    gamma=round(float(gamma), 3),
                                    lo=gamma_limits[0], hi=gamma_limits[1]))

        # O/F Ratio
        of_ratio = data.get('of_ratio', 0)
        of_limits = self.performance_limits['of_ratio'].get(propellant_combo, (0.5, 8.0))
        if not (of_limits[0] <= of_ratio <= of_limits[1]):
            warnings_list.append(_w("warn.validation.of_out_of_range", "warning",
                                    of=round(float(of_ratio), 2),
                                    lo=of_limits[0], hi=of_limits[1]))

        return warnings_list
    
    def validate_injector_data(self, data: Dict) -> List[str]:
        """İnjektör verilerini doğrula"""
        warnings_list = []
        
        # Reynolds Number
        reynolds = data.get('reynolds_number', 0)
        re_limits = self.injector_limits['reynolds_number']
        if not (re_limits[0] <= reynolds <= re_limits[1]):
            if reynolds < re_limits[0]:
                warnings_list.append(_w("warn.validation.reynolds_laminar", "critical",
                                        re=round(float(reynolds), 0), min=re_limits[0]))
            else:
                warnings_list.append(_w("warn.validation.reynolds_high", "warning",
                                        re=round(float(reynolds), 0), max=re_limits[1]))
        
        # Pressure Drop
        pressure_drop = data.get('pressure_drop', 0)
        chamber_pressure = data.get('chamber_pressure', 20)
        drop_ratio = pressure_drop / chamber_pressure if chamber_pressure > 0 else 0
        drop_limits = self.injector_limits['pressure_drop_ratio']
        
        if not (drop_limits[0] <= drop_ratio <= drop_limits[1]):
            if drop_ratio < drop_limits[0]:
                warnings_list.append(_w("warn.validation.dp_pc_low", "critical",
                                        ratio=round(float(drop_ratio), 2), min=drop_limits[0]))
            else:
                warnings_list.append(_w("warn.validation.dp_pc_high", "warning",
                                        ratio=round(float(drop_ratio), 2), max=drop_limits[1]))

        # Exit Velocity
        exit_velocity = data.get('exit_velocity', 0)
        vel_limits = self.injector_limits['exit_velocity']
        if not (vel_limits[0] <= exit_velocity <= vel_limits[1]):
            warnings_list.append(_w("warn.validation.exit_velocity_out_of_range", "warning",
                                    v=round(float(exit_velocity), 1),
                                    lo=vel_limits[0], hi=vel_limits[1]))

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
            warnings_list.append(_w("warn.validation.port_initial_out_of_range", "warning",
                                    d=round(float(d_port_initial), 1),
                                    lo=port_limits[0], hi=port_limits[1]))

        # Port Growth Check
        if d_port_initial > 0 and d_port_final > 0:
            growth_ratio = d_port_final / d_port_initial
            if growth_ratio < 1.2:
                warnings_list.append(_w("warn.validation.port_growth_low", "warning",
                                        ratio=round(float(growth_ratio), 2)))
            elif growth_ratio > 3.0:
                warnings_list.append(_w("warn.validation.port_growth_high", "critical",
                                        ratio=round(float(growth_ratio), 2)))

        # Chamber vs Port Diameter
        if d_chamber > 0 and d_port_final > 0:
            if d_port_final > d_chamber * 0.8:
                warnings_list.append(_w("warn.validation.port_exceeds_chamber", "critical"))

        # Expansion Ratio
        expansion_ratio = data.get('expansion_ratio', 0)
        exp_limits = self.geometry_limits['expansion_ratio']
        if expansion_ratio > 0 and not (exp_limits[0] <= expansion_ratio <= exp_limits[1]):
            warnings_list.append(_w("warn.validation.expansion_ratio_out_of_range", "warning",
                                    eps=round(float(expansion_ratio), 1),
                                    lo=exp_limits[0], hi=exp_limits[1]))

        return warnings_list
    
    def check_sutton_biblarz_criteria(self, data: Dict) -> List[str]:
        """Sutton & Biblarz kitabından kritik tasarım kriterleri"""
        warnings_list = []
        
        # Kısık yüklenmesi tutarlılık kontrolü:
        # F/At ≡ CF·Pc özdeşliği geçerlidir (Sutton & Biblarz 9. baskı, Denk. 3-31).
        # Eski sabit "2.0 N/mm²" eşiği fiziksel bir tasarım kriteri değildi:
        # CF≈1.5 için Pc > ~13 bar olan her normal motoru hatalı biçimde KRITIK
        # işaretliyordu. Bunun yerine ima edilen itki katsayısı
        # CF_ima = (F/At)/Pc hesaplanır ve teorik sınırlarla karşılaştırılır.
        # Üst sınır: gamma=1.2 için sonsuz genleşmeli vakum CF limiti ≈ 2.246
        # (Sutton & Biblarz 9. baskı, Denk. 3-30 limiti / Şekil 3-6).
        thrust = data.get('thrust', 0)
        throat_area = data.get('throat_area', 0)
        chamber_pressure_bar = data.get('chamber_pressure', 0)  # bar
        if thrust > 0 and throat_area > 0 and chamber_pressure_bar > 0:
            throat_loading = thrust / (throat_area * 1e6)  # N/mm² (= MPa)
            implied_cf = throat_loading / (chamber_pressure_bar * 0.1)  # Pc: bar → MPa
            if implied_cf > 2.25:
                warnings_list.append(_w("warn.validation.cf_too_high", "critical",
                                        cf=round(float(implied_cf), 2), limit=2.25))
            elif implied_cf < 0.8:
                warnings_list.append(_w("warn.validation.cf_too_low", "warning",
                                        cf=round(float(implied_cf), 2), limit=0.8))

        # L* kontrolü (Karakteristik uzunluk)
        l_star = data.get('l_star', 0)
        if l_star > 0:
            if l_star < 0.5:
                warnings_list.append(_w("warn.validation.lstar_low", "critical",
                                        lstar=round(float(l_star), 2)))
            elif l_star > 2.0:
                warnings_list.append(_w("warn.validation.lstar_high", "warning",
                                        lstar=round(float(l_star), 2)))

        # Regresyon hızı kontrolü
        regression_rate = data.get('regression_rate', 0) * 1000  # m/s to mm/s
        if regression_rate > 0:
            if regression_rate < 0.5:
                warnings_list.append(_w("warn.validation.regression_low", "warning",
                                        rate=round(float(regression_rate), 2)))
            elif regression_rate > 5.0:
                warnings_list.append(_w("warn.validation.regression_high", "critical",
                                        rate=round(float(regression_rate), 2)))

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
        
        # Kritik/uyarı ayrımı — ARTIK severity alanından (dil-bağımsız), eskiden
        # metin içindeki 'KRITIK'/'UYARI' string'inden parse ediliyordu.
        critical_warnings = [w for w in all_warnings if w.get('severity') == 'critical']
        regular_warnings = [w for w in all_warnings if w.get('severity') == 'warning']

        # Genel değerlendirme — status da i18n kodu ({code}); frontend TF ile çevirir.
        if critical_warnings:
            overall_status = _w("status.critical", "critical")
        elif regular_warnings:
            overall_status = _w("status.warnings", "warning")
        else:
            overall_status = _w("status.normal", "info")

        return {
            'overall_status': overall_status,
            'critical_warnings': critical_warnings,
            'regular_warnings': regular_warnings,
            'total_warnings': len(all_warnings),
            'validation_passed': len(critical_warnings) == 0
        }

# Global instance
validator = ValidationSystem()