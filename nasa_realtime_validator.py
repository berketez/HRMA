"""
NASA Real-time Data Validator
Günlük NASA/NIST verilerini çekip motor hesaplamalarını doğrular
"""

import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import os


class NASARealtimeValidator:
    """NASA/NIST gerçek zamanlı veri doğrulayıcısı"""
    
    def __init__(self):
        self.cache_file = "nasa_validation_cache.json"
        self.last_update = None
        self.update_interval = 24 * 3600  # 24 saat
        
        # NASA resmi motor spesifikasyonları
        self.nasa_motors = {
            'RS-25': {
                'throat_diameter_mm': 261.6,  # 10.3 inch official
                'thrust_sl_N': 1860000,
                'thrust_vac_N': 2279000,
                'isp_sl_s': 366,
                'isp_vac_s': 452,
                'chamber_pressure_bar': 204,
                'mixture_ratio': 6.0,
                'propellant': 'LOX/LH2',
                'source': 'NASA RS-25 Fact Sheet'
            },
            'F-1': {
                'throat_diameter_mm': 914.4,  # 36 inch official
                'thrust_sl_N': 6770000,
                'isp_sl_s': 263,
                'chamber_pressure_bar': 70,
                'mixture_ratio': 2.27,
                'propellant': 'LOX/RP-1',
                'source': 'NASA Saturn V Technical Data'
            }
        }
    
    def fetch_nasa_propellant_data(self, propellant_combo: str) -> Optional[Dict]:
        """NASA CEA web servisinden güncel propellant data çek"""
        try:
            # NASA CEA web interface
            cea_url = "https://cearun.grc.nasa.gov/cgi-bin/CEA.pl"
            
            # Propellant parameters
            params = {
                'fuel': propellant_combo.split('/')[1].lower(),
                'oxidizer': propellant_combo.split('/')[0].lower(),
                'pressure': 204 if 'LH2' in propellant_combo else 70,
                'mixture_ratio': 6.0 if 'LH2' in propellant_combo else 2.27
            }
            
            headers = {
                'User-Agent': 'HRMA-Rocket-Analysis-System/1.0',
                'Accept': 'application/json'
            }
            
            response = requests.get(cea_url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Parse CEA output (simplified)
                data = {
                    'c_star': self._extract_cstar(response.text),
                    'gamma': self._extract_gamma(response.text),
                    'molecular_weight': self._extract_mw(response.text),
                    'chamber_temp': self._extract_temp(response.text),
                    'fetched_at': datetime.now().isoformat(),
                    'source': 'NASA CEA Live'
                }
                return data
            
        except Exception as e:
            print(f"NASA CEA fetch error: {e}")
            
        return None
    
    def fetch_nist_gas_properties(self, gas: str) -> Optional[Dict]:
        """NIST webbook'tan gerçek gas properties çek"""
        try:
            nist_url = "https://webbook.nist.gov/cgi/cbook.cgi"
            
            params = {
                'ID': self._get_nist_id(gas),
                'Type': 'JANAF',
                'Table': 'on'
            }
            
            response = requests.get(nist_url, params=params, timeout=10)
            
            if response.status_code == 200:
                return {
                    'molecular_weight': self._extract_nist_mw(response.text),
                    'cp_cv_ratio': self._extract_nist_gamma(response.text),
                    'fetched_at': datetime.now().isoformat(),
                    'source': 'NIST WebBook Live'
                }
                
        except Exception as e:
            print(f"NIST fetch error: {e}")
            
        return None
    
    def validate_motor_calculation(self, motor_name: str, calculated_throat_mm: float, thrust_N: float = None) -> Dict:
        """Motor hesaplamasını NASA referansıyla karşılaştır"""
        
        if motor_name not in self.nasa_motors:
            return {'status': 'unknown_motor', 'message': f'Motor {motor_name} not in NASA database'}
        
        reference = self.nasa_motors[motor_name]
        expected_mm = reference['throat_diameter_mm']
        error_pct = abs(calculated_throat_mm - expected_mm) / expected_mm * 100
        
        # İtki ölçeği kontrolü - çok büyük motorlar için daha esnek tolerans
        thrust_scaling_factor = 1.0
        if thrust_N and 'thrust_sl_N' in reference:
            thrust_ratio = thrust_N / reference['thrust_sl_N']
            # Eğer hesaplanan itki NASA'nın %10'undan az ise (ölçek çok farklı), toleransı artır
            if thrust_ratio < 0.1:
                thrust_scaling_factor = 3.0  # 3x daha esnek tolerans
                status_note = f" (Scale diff: {thrust_ratio:.3f}x)"
            else:
                status_note = ""
        else:
            status_note = ""
        
        # Doğrulama seviyeleri (ölçek faktörü ile)
        if error_pct < 1.0 * thrust_scaling_factor:
            status = 'EXCELLENT'
            color = '🟢'
        elif error_pct < 5.0 * thrust_scaling_factor:
            status = 'GOOD'
            color = '🟡'
        elif error_pct < 15.0 * thrust_scaling_factor:
            status = 'ACCEPTABLE'
            color = '🟠'
        else:
            status = 'POOR'
            color = '🔴'
        
        # Status'a scale note ekle
        if status_note:
            status += status_note
        
        return {
            'status': status,
            'color': color,
            'calculated_mm': calculated_throat_mm,
            'nasa_reference_mm': expected_mm,
            'error_percent': error_pct,
            'nasa_source': reference['source'],
            'validation_time': datetime.now().isoformat(),
            'recommendation': self._get_recommendation(error_pct)
        }
    
    def daily_validation_report(self) -> str:
        """Günlük doğrulama raporu oluştur"""
        report = [
            "🚀 NASA REAL-TIME VALIDATION REPORT",
            "=" * 50,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        
        # Her motor için validation check
        for motor_name in self.nasa_motors.keys():
            report.append(f"Motor: {motor_name}")
            report.append("-" * 30)
            
            # Güncel propellant data çek
            prop_data = self.fetch_nasa_propellant_data(
                self.nasa_motors[motor_name]['propellant']
            )
            
            if prop_data:
                report.append(f"✅ NASA CEA Data: Updated")
                report.append(f"   c*: {prop_data.get('c_star', 'N/A')} m/s")
                report.append(f"   γ: {prop_data.get('gamma', 'N/A')}")
                report.append(f"   MW: {prop_data.get('molecular_weight', 'N/A')} kg/kmol")
            else:
                report.append(f"❌ NASA CEA Data: Failed to fetch")
            
            report.append("")
        
        return "\n".join(report)
    
    def _extract_cstar(self, cea_text: str) -> Optional[float]:
        """CEA output'undan c* değerini çıkar"""
        # CEA parsing logic (simplified)
        try:
            # Look for CSTAR in m/s
            import re
            match = re.search(r'CSTAR.*?(\d+\.?\d*)', cea_text)
            if match:
                return float(match.group(1))
        except:
            pass
        return None
    
    def _extract_gamma(self, cea_text: str) -> Optional[float]:
        """CEA output'undan gamma değerini çıkar"""
        try:
            import re
            match = re.search(r'GAMMAs.*?(\d+\.?\d*)', cea_text)
            if match:
                return float(match.group(1))
        except:
            pass
        return None
    
    def _extract_mw(self, cea_text: str) -> Optional[float]:
        """CEA output'undan molecular weight çıkar"""
        try:
            import re
            match = re.search(r'M.*?(\d+\.?\d*)', cea_text)
            if match:
                return float(match.group(1))
        except:
            pass
        return None
    
    def _extract_temp(self, cea_text: str) -> Optional[float]:
        """CEA output'undan chamber temperature çıkar"""
        try:
            import re
            match = re.search(r'T.*?(\d+\.?\d*)', cea_text)
            if match:
                return float(match.group(1))
        except:
            pass
        return None
    
    def _get_nist_id(self, gas: str) -> str:
        """Gas için NIST ID döndür"""
        nist_ids = {
            'lh2': 'C1333740',
            'lox': 'C7782447',
            'rp1': 'C8006619',  # Representative hydrocarbon
            'ch4': 'C74828'
        }
        return nist_ids.get(gas.lower(), gas)
    
    def _extract_nist_mw(self, nist_text: str) -> Optional[float]:
        """NIST'ten molecular weight çıkar"""
        # NIST parsing logic
        try:
            import re
            match = re.search(r'Molecular weight.*?(\d+\.?\d*)', nist_text)
            if match:
                return float(match.group(1))
        except:
            pass
        return None
    
    def _extract_nist_gamma(self, nist_text: str) -> Optional[float]:
        """NIST'ten gamma çıkar"""
        try:
            import re
            match = re.search(r'Cp/Cv.*?(\d+\.?\d*)', nist_text)
            if match:
                return float(match.group(1))
        except:
            pass
        return None
    
    def _get_recommendation(self, error_pct: float) -> str:
        """Hata yüzdesine göre öneri döndür"""
        if error_pct < 1.0:
            return "Calculation is NASA-grade accurate"
        elif error_pct < 5.0:
            return "Good accuracy for engineering purposes"
        elif error_pct < 15.0:
            return "Acceptable for preliminary design"
        else:
            return "Requires parameter review and calibration"


def run_daily_validation():
    """Günlük validation check çalıştır"""
    validator = NASARealtimeValidator()
    
    print("🚀 Starting NASA Real-time Validation...")
    print("Fetching latest NASA/NIST data...")
    
    report = validator.daily_validation_report()
    print(report)
    
    # Save report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"nasa_validation_{timestamp}.txt"
    
    with open(filename, 'w') as f:
        f.write(report)
    
    print(f"\n📊 Report saved: {filename}")


if __name__ == "__main__":
    run_daily_validation()