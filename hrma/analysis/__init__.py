"""Analiz modulleri.

ÖH D24 / P5B4-37 — ÖLÇÜLEN KUSUR (taban ``88a29d3``, kanıt
``docs/scofield/raw/OH/D24/yapisal-sistem/a1/once_p5b437.json``): aşağıdaki
beş ithal ``try/except ImportError`` içindeydi ve hata yalnız bir
``warnings.warn`` ile yutuluyordu. Sonuç ölçüldü: alt modüllerden biri
patlasa bile ``import hrma.analysis`` BAŞARILI oluyor, ad ise çok sonra —
başka bir çağrı yığınında — ``AttributeError: module 'hrma.analysis' has no
attribute 'SafetyAnalyzer'`` olarak patlıyordu. Yani koruma, hatayı
ortadan kaldırmıyor yalnız TEŞHİSİ bozuyordu; üstelik ``warnings.warn``
varsayılan filtrede bir kez basılır ve sunucu günlüğünde kaybolur.

Koruma karşılıksızdı: bu beş adı paket ad alanından (``hrma.analysis.X``)
çeken tek bir tüketici yok — hepsi kendi modülünden ithal ediyor (ölçüm
aynı dosyada). İthaller bu yüzden DÜZ: bir alt modül yüklenemiyorsa
``ImportError`` çağıranın yüzüne, gerçek geri izleme ile döner
(fail-closed).
"""

# v2.6.27 (teknik borç §4): emekli çözücülerin (cfd_analysis,
# kinetic_analysis) paket-düzeyi importları kaldırıldı — uçları 501
# dönüyor, ~2100 satır her açılışta boşuna yükleniyordu. Dosyalar
# depoda duruyor (kaldırma/legacy taşıma kararı Berke'de); ihtiyaç
# duyan, modülü doğrudan import eder.
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.safety_analysis import SafetyAnalyzer
from hrma.analysis.regression_analysis import regression_analyzer, RegressionAnalyzer
from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer

__all__ = [
    'HeatTransferAnalyzer',
    'StructuralAnalyzer',
    'SafetyAnalyzer',
    'RegressionAnalyzer',
    'regression_analyzer',
    'TrajectoryAnalyzer',
]
