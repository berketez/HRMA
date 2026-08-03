"""Model limit kontrolleri — SINIRLI ve AÇIKÇA BEYAN EDİLMİŞ kapsam.

Bu modülün üretimdeki TEK canlı girişi ``SafetyLimits.check_throat_diameter``
(``hrma/engines/liquid_rocket_engine.py:2723``) ve o çağrının sonucu yalnız
``print()`` ile konsola gider. Yani burası bir GÜVENLİK KAPISI DEĞİLDİR:
``violations`` listesi hiçbir HTTP yanıtına, export'a ya da panele
girmemektedir. Bu cümle süs değil, ölçüm sonucudur — aşağıya bakınız.

Faz 5 / H5-8 temizliği (3 Ağustos 2026, HEAD 9d3728e)
-----------------------------------------------------
Modül 361 satırdı ve bu satırların çoğu ULAŞILAMAZ koddu. Ölçüm (depo
genelinde grep; kendi tanımları ve bu dosya hariç tutularak):

    comprehensive_check      -> üretim: 0   test: 0
    check_chamber_pressure   -> üretim: 0   test: 0
    check_wall_temperature   -> üretim: 0   test: 0
    check_thrust             -> üretim: 0   test: 0
    check_mass_flow_rate     -> üretim: 0   test: 0
    MotorValidator           -> depo genelinde 0 referans
    check_throat_diameter    -> üretim: 1   (liquid_rocket_engine.py:2723)

Dört ``check_*`` metodu YALNIZ ``comprehensive_check`` içinden çağrılıyordu,
``comprehensive_check`` da hiçbir yerden çağrılmıyordu; yani hiçbiri hiçbir
zaman koşmadı. Bu ölü yüzey, modülün çalışan kapsamlı bir güvenlik denetimi
olduğu izlenimini veriyordu. Karar: BAĞLAYAMADIĞIMIZ için KALDIRILDI —
ulaşılamayan kodun "var olması" hiçbir şeyi denetlemez, yalnız okuyucuyu
yanıltır. Yeniden ihtiyaç duyulursa git geçmişinden alınabilir; geri
gelirse ÇAĞRI YERİYLE birlikte gelmelidir.

Korunan yüzey ve gerekçesi:
* ``check_throat_diameter`` — üretimde canlı (tek çağrı yeri yukarıda).
* ``generate_safety_report`` / ``clear_violations`` — üretimde çağrılmıyor;
  ``tests/test_safety_honesty.py`` bunları doğrudan sınıyor çünkü
  2026-07-28'de kapatılan FAIL-OPEN kusurunun bekçileridir (aşağıya bakınız).
  Bu ikisi bilerek bırakıldı ve test-yüzeyi oldukları burada beyan edilir.
"""

from typing import List, Dict


class SafetyLimits:
    """Boğaz çapı akıl sağlığı sınırları ve ihlal kaydı.

    İşletme emniyeti hükmü VERMEZ; yalnız model girdisinin fiziksel olarak
    anlamlı bir aralıkta olup olmadığına bakar.
    """

    def __init__(self,
                 throat_diameter_min: float = 0.001,  # m (1mm)
                 throat_diameter_max: float = 2.0):   # m (2000mm)
        """
        Args:
            throat_diameter_min/max: Throat diameter sanity bounds (m)
        """
        self.throat_dia_min = throat_diameter_min
        self.throat_dia_max = throat_diameter_max

        self.violations: List[Dict] = []  # Track all violations
        # Fail-open koruması (2026-07-28): koşan kontrol sayısı izlenir.
        # Eskiden hiç kontrol koşmamışken de "ALL CHECKS PASSED" dönüyordu —
        # "hiç değerlendirilmedi" ile "tümü geçti" ayırt edilemiyordu.
        self.checks_run = 0

    def check_throat_diameter(self, throat_dia: float,
                              motor_name: str = "Motor") -> bool:
        """Check throat diameter for sanity bounds"""
        self.checks_run += 1
        throat_mm = throat_dia * 1000  # Convert to mm

        if throat_dia < self.throat_dia_min:
            violation = {
                'parameter': 'Throat Diameter (too small)',
                'value': throat_mm,
                'limit': self.throat_dia_min * 1000,
                'unit': 'mm',
                'motor': motor_name,
                'severity': 'CRITICAL',
                'risk': 'Excessive pressure - motor explosion'
            }
            self.violations.append(violation)
            return False

        if throat_dia > self.throat_dia_max:
            violation = {
                'parameter': 'Throat Diameter (too large)',
                'value': throat_mm,
                'limit': self.throat_dia_max * 1000,
                'unit': 'mm',
                'motor': motor_name,
                'severity': 'HIGH',
                'risk': 'Calculation error - performance loss'
            }
            self.violations.append(violation)
            return False

        return True

    def generate_safety_report(self) -> str:
        """Generate human-readable safety report.

        Fail-open düzeltmesi (2026-07-28): eski sürüm ihlal listesi boşsa
        "ALL CHECKS PASSED - MOTOR SAFE FOR OPERATION" dönüyordu — hiç
        kontrol koşulmamışken bile. "Hiç değerlendirilmedi" artık ayrı
        raporlanır ve sertifikasyon iması taşıyan "MOTOR SAFE FOR
        OPERATION" ifadesi kaldırıldı: bu sınıf yalnız model limitlerini
        kontrol eder, işletme emniyeti hükmü veremez.
        """
        if self.checks_run == 0:
            return "SAFETY STATUS: NOT EVALUATED - no applicable checks ran"
        if not self.violations:
            return (f"SAFETY STATUS: NO LIMIT VIOLATIONS DETECTED "
                    f"({self.checks_run} checks run; model limit checks "
                    f"only - not a safety certification)")

        report = ["SAFETY VIOLATION REPORT", "=" * 50]

        critical_violations = [v for v in self.violations
                               if v['severity'] == 'CRITICAL']
        if critical_violations:
            report.append("\nCRITICAL VIOLATIONS (IMMEDIATE DANGER):")
            for v in critical_violations:
                report.append(f"  {v['motor']}: {v['parameter']}")
                report.append(f"    Value: {v['value']:.2f} {v['unit']}")
                report.append(f"    Limit: {v['limit']:.2f} {v['unit']}")
                report.append(f"    Risk: {v['risk']}")
                report.append("")

        high_violations = [v for v in self.violations
                           if v['severity'] == 'HIGH']
        if high_violations:
            report.append("HIGH PRIORITY VIOLATIONS:")
            for v in high_violations:
                report.append(f"  {v['motor']}: {v['parameter']}")
                report.append(f"    Value: {v['value']:.2f} {v['unit']}")
                report.append(f"    Limit: {v['limit']:.2f} {v['unit']}")
                report.append(f"    Risk: {v['risk']}")
                report.append("")

        # NOT: MEDIUM şiddet dalı bilerek YOK. Tek canlı kontrol
        # (check_throat_diameter) yalnız CRITICAL/HIGH üretir; MEDIUM dalı
        # kaldırılan check_mass_flow_rate'e aitti ve ulaşılamazdı
        # (H5-8, 3 Ağustos 2026).

        if critical_violations:
            report.append("RECOMMENDATION: DO NOT OPERATE - CRITICAL SAFETY RISK")
        else:
            report.append("RECOMMENDATION: REVIEW DESIGN BEFORE OPERATION")

        return "\n".join(report)

    def clear_violations(self):
        """Clear all recorded violations (tam sıfırlama).

        checks_run da sıfırlanır: temizlenmiş bir nesneden rapor istenirse
        "değerlendirilmedi" denmelidir, "N kontrol geçti" değil.
        """
        self.violations = []
        self.checks_run = 0
