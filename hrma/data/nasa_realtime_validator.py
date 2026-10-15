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
from hrma import DATA_DIR


#: ÖH D22 / P9B5-13 — künye eşiği. Bu sayı HESABA GİRMEZ: ölçekleme her
#: zaman uygulanır (bkz. ``validate_motor_calculation``). Yalnız "ölçeklendi"
#: notunun basılıp basılmayacağını belirler, yani okunabilirlik eşiğidir;
#: sayısal sonucu değiştirmediği için bir hüküm eşiği değildir.
SCALE_NOTE_VISIBILITY = 0.001

class NASARealtimeValidator:
    """NASA/NIST gerçek zamanlı veri doğrulayıcısı"""

    def __init__(self):
        self.cache_file = os.path.join(DATA_DIR, "nasa_validation_cache.json")
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
        """NIST WebBook'tan gaz özelliği çek — KÜNYE KAZANILARAK.

        P9B5-15 ONARIMI (2026-08-27). Eski davranış: HTTP 200 gelir gelmez
        sonuç ``'source': 'NIST WebBook Live'`` künyesiyle dönüyordu. Ama
        dönen sözlüğün iki sayısı da ``_extract_nist_mw`` /
        ``_extract_nist_gamma`` çıktısıydı ve bu iki ayrıştırıcı, WebBook'un
        gerçek JANAF sayfasında ARADIĞI deseni (``Molecular weight`` /
        ``Cp/Cv``) bulamadığında ``None`` döner. Yani "NIST'ten canlı veri"
        künyesi, İÇİNDE TEK BİR SAYI OLMAYAN bir sözlüğe basılabiliyordu:
        yanıtın gelmiş olması, sayının ayıklanmış olması demek değildir.

        Yeni sözleşme (Z4'ün kazanılmış-künye kuralının veri katmanındaki
        eşliği): 'Live' damgası ANCAK en az bir sayı gerçekten ayıklandığında
        verilir. Hiçbiri ayıklanamazsa sayı UYDURULMAZ, sözlük
        ``status='parse_failed'`` ve kökeni dürüstçe söyleyen bir künye ile
        döner; hangi alanların ayıklandığı/ayıklanamadığı ADLARIYLA yazılır.
        Sayılara dokunulmadı — yalnız künye gerçeğe bağlandı.
        """
        try:
            nist_url = "https://webbook.nist.gov/cgi/cbook.cgi"

            params = {
                'ID': self._get_nist_id(gas),
                'Type': 'JANAF',
                'Table': 'on'
            }

            response = requests.get(nist_url, params=params, timeout=10)

            if response.status_code == 200:
                ayiklanan = {}
                for alan, ayiklayici in (
                        ('molecular_weight', self._extract_nist_mw),
                        ('cp_cv_ratio', self._extract_nist_gamma)):
                    deger = ayiklayici(response.text)
                    if deger is not None:
                        ayiklanan[alan] = deger

                ortak = {
                    'gas': gas,
                    'nist_id': self._get_nist_id(gas),
                    'source_url': nist_url,
                    'http_status': response.status_code,
                    'fetched_at': datetime.now().isoformat(),
                    'parsed_fields': sorted(ayiklanan),
                    'unparsed_fields': sorted(
                        {'molecular_weight', 'cp_cv_ratio'} - set(ayiklanan)),
                }

                if not ayiklanan:
                    # Yanıt geldi ama TEK SAYI ayıklanamadı: 'Live' künyesi
                    # KAZANILMADI. Boş anahtar da konmuyor (fail-closed) —
                    # çağıran ".get(anahtar, yedek)" ile kendi kaynağına düşer.
                    ortak.update({
                        'status': 'parse_failed',
                        'source': ('NIST WebBook reached (HTTP 200) but no '
                                   'numeric property could be parsed'),
                    })
                    return ortak

                ortak.update(ayiklanan)
                ortak.update({
                    'status': 'success' if not ortak['unparsed_fields']
                              else 'partial',
                    'source': 'NIST WebBook Live',
                })
                return ortak

        except Exception as e:
            print(f"NIST fetch error: {e}")

        return None
    
    def validate_motor_calculation(self, motor_name: str, calculated_throat_mm: float, thrust_N: float = None, chamber_pressure_bar: float = None) -> Dict:
        """Motor hesaplamasını NASA referansıyla karşılaştır

        Thrust/Pc ölçeği farklıysa referans throat'u ölçekler:
        d_t ∝ sqrt(F / Pc)
        """
        import math

        if motor_name not in self.nasa_motors:
            return {'status': 'unknown_motor', 'message': f'Motor {motor_name} not in NASA database'}

        reference = self.nasa_motors[motor_name]
        ref_throat_mm = reference['throat_diameter_mm']

        # ------------------------------------------------------------------
        # ÖH D22 / defter P9B5-13 — ÖLÇEKLEME EŞİĞİ SÖKÜLDÜ (SÜREKSİZLİK).
        #
        # ÖLÇÜLDÜ (taban ``b84b10a``, ``once.json`` bölümü P9B5-13, F-1
        # referansı: d_t = 914,4 mm, F_ref = 6 770 000 N, Pc_ref = 70 bar):
        #
        #     itki oranı 1,0999 -> beklenen boğaz 914,400 mm, "DEVIATION < 2%"
        #     itki oranı 1,1001 -> beklenen boğaz 959,074 mm, "DEVIATION 2-5%"
        #
        # İtki **%0,02** değişince referans boğaz çapı **%4,886** sıçrıyor ve
        # hüküm etiketi değişiyordu. Sıçramanın kaynağı fizik değil, bir
        # ``if abs(thrust_ratio - 1.0) > 0.1`` kapısıydı: eşiğin altında
        # ölçekleme HİÇ uygulanmıyor (yani sessizce ``thrust_ratio = 1``
        # varsayılıyor), üstünde tam uygulanıyordu. Aynı sıçrama Pc tarafında
        # daha da sinsiydi: itki referansla aynı ama Pc iki katı olan bir
        # motorda ölçekleme dalına HİÇ girilmiyor, yani ``sqrt(Pc_ref/Pc)``
        # düzeltmesi tamamen düşüyordu.
        #
        # Bağıntının kendisi (d_t ∝ sqrt(F/Pc)) SÜREKLİDİR ve oran 1'e
        # eşitken birim dönüşümüdür. Bu yüzden eşik KALDIRILDI, yeni bir
        # eşik de İCAT EDİLMEDİ: ölçekleme her zaman uygulanır, oran 1 iken
        # sonuç ref_throat_mm'in kendisidir (özdeşlik). Eşik yalnız
        # KÜNYE metninde yaşamaya devam eder — "ölçeklendi" notu, ölçeğin
        # okunur biçimde farklı olduğu durumda basılır; SAYIYI etkilemez.
        # ------------------------------------------------------------------
        scale_note = ""
        thrust_ratio = None
        pc_ratio = None
        if thrust_N and 'thrust_sl_N' in reference:
            thrust_ratio = thrust_N / reference['thrust_sl_N']
        if chamber_pressure_bar and 'chamber_pressure_bar' in reference:
            pc_ratio = chamber_pressure_bar / reference['chamber_pressure_bar']

        _F = thrust_ratio if (thrust_ratio and thrust_ratio > 0) else 1.0
        _P = pc_ratio if (pc_ratio and pc_ratio > 0) else 1.0
        # d_t_scaled = d_t_ref * sqrt(F_user / F_ref) * sqrt(Pc_ref / Pc_user)
        expected_mm = ref_throat_mm * math.sqrt(_F / _P)
        if abs(_F / _P - 1.0) > SCALE_NOTE_VISIBILITY:
            _parcalar = []
            if thrust_ratio is not None:
                _parcalar.append(f"thrust ratio: {thrust_ratio:.4f}x")
            if pc_ratio is not None:
                _parcalar.append(f"chamber pressure ratio: {pc_ratio:.4f}x")
            scale_note = (f" (scaled from {reference['source']}, "
                          + ', '.join(_parcalar) + ")")

        error_pct = abs(calculated_throat_mm - expected_mm) / expected_mm * 100

        # Sapma bandı — HÜKÜM DEĞİL, yalnız yüzdenin hangi aralığa düştüğü.
        # DENETİM DÜZELTMESİ (2026-08-02, C4): eski etiketler 'EXCELLENT' /
        # 'GOOD' / 'ACCEPTABLE' / 'POOR' idi; %15'lik bir boğaz çapı sapmasına
        # "ACCEPTABLE" demek, dayanağı olmayan bir kabul hükmüdür. Bandın
        # sınırları da kalibre edilmiş değil, yalnız okuma kolaylığı için
        # seçilmiş yuvarlak sayılardır; etiket artık bunu söylüyor.
        if error_pct < 2.0:
            status = 'DEVIATION < 2%'
            color = '🟢'
        elif error_pct < 5.0:
            status = 'DEVIATION 2-5%'
            color = '🟡'
        elif error_pct < 15.0:
            status = 'DEVIATION 5-15%'
            color = '🟠'
        else:
            status = 'DEVIATION > 15%'
            color = '🔴'

        return {
            'status': status + scale_note,
            'color': color,
            'calculated_mm': calculated_throat_mm,
            'nasa_reference_mm': expected_mm,
            'error_percent': error_pct,
            'nasa_source': reference['source'],
            'validation_time': datetime.now().isoformat(),
            # Karşılaştırmanın NE OLDUĞU ve NE OLMADIĞI ayrı alanlarda da
            # makinece okunabilir dursun (tüketici yalnız metni basmasın).
            'comparison_basis': (
                f"single published throat diameter of {motor_name} "
                f"({reference['source']})"
                + (' scaled by sqrt(F/Pc) to the requested operating point'
                   if scale_note else '')),
            'comparison_is_not': (
                'not a validation campaign: one geometric quantity, one '
                'operating point, no test data, no uncertainty budget'),
            'recommendation': self._comparison_statement(
                error_pct, motor_name, reference['source'], bool(scale_note)),
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
    
    def _comparison_statement(self, error_pct: float, motor_name: str,
                              source: str, scaled: bool) -> str:
        """Karşılaştırmayı olgusal olarak anlatır — hüküm vermez.

        DENETİM DÜZELTMESİ (2026-08-02, C4). Eski ``_get_recommendation``
        TEK bir yüzde hatasından üç yasak hüküm üretiyordu:

        IDDIA-LINT-MUAF-BASLANGIC (kaldırılan kusurun birebir alıntısı)
            error < 1%   -> "Calculation is NASA-grade accurate"
            error < 5%   -> "Good accuracy for engineering purposes"
            error < 15%  -> "Acceptable for preliminary design"
        IDDIA-LINT-MUAF-BITIS

        Üçü de kazanılmamış iddiaydı. Karşılaştırılan şey TEK bir sayıydı:
        yayımlanmış bir motorun boğaz çapı. Bunun ne akreditasyonla
        ("NASA-grade") ne de bir tasarım aşamasının kabulüyle  IDDIA-LINT-MUAF
        ("preliminary design") ilgisi var; ölçülen doğruluk bandı bile
        yalnız o tek geometrik büyüklüğe ve tek çalışma noktasına ait.

        Yerine geçen metin şunları verir: sapma yüzdesi, karşılaştırılan
        kaynak, ölçekleme uygulandı mı, ve karşılaştırmanın NE OLMADIĞI.
        """
        scale_clause = (
            ', after scaling the reference throat by sqrt(F/Pc) to the '
            'requested operating point' if scaled else '')
        return (
            f'Computed throat diameter differs by {error_pct:.2f}% from the '
            f'published {motor_name} throat diameter ({source})'
            f'{scale_clause}. This is a single-point comparison of one '
            f'geometric quantity against one published motor: it is not a '
            f'validation of the analysis, carries no uncertainty budget, '
            f'and says nothing about accuracy at other operating points or '
            f'for other quantities.')


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