"""NumPy sürüm köprüsü — TEK KAYNAK.

ÖH D26 · defter OH-D25-14 (Fable-D20 termo-ucus bulgusu).

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/D26/termo-ucus/a1/once.json, K1):
``np.trapz`` NumPy 2.0 ile ad alanından KALDIRILDI (NumPy 2.0 sürüm notları
ve göç kılavuzu: ``np.trapz`` -> ``np.trapezoid``; erişim artık
``AttributeError`` verir). Depoda bu ad ürün kodunda **30 çağrı sitesi /
11 dosya**, ayrıca ``tests/test_d20_termo_ucus_a1.py`` içinde 1 site
olarak yaşıyordu. Ölçüm, ``numpy`` ad alanından ``trapz``ı silerek
(NumPy 2 taklidi) yapıldı: çağrı ``AttributeError: module 'numpy' has no
attribute 'trapz'`` ile düşüyor — yani NumPy 2'ye geçildiği gün toplam
impuls, sürtünme direnci, basınç integrali gibi ÜRÜN yolları kırılırdı.

ÇÖZÜM: ad tek yerde çözülür, çağıranlar buradan ithal eder. İki ad da
AYNI yamuk kuralını uygular (NumPy 2.0'da yalnız YENİDEN ADLANDIRMA
yapıldı, algoritma değişmedi), dolayısıyla NumPy 1.x altında bu takma ad
``np.trapz``ın KENDİSİDİR ve sayısal çıktı bit-aynıdır.

Sayı/parametre değil AD tekilleştirmesi olduğu için sabit dosyalarına
girmez; ama kural aynıdır: ``np.trapz`` adı ürün kodunda bir daha
yazılmaz (bekçi: tests/test_d26_termo_ucus_a1.py).
"""

import numpy as np

__all__ = ['trapezoid', 'TRAPEZOID_SOURCE']

#: Yamuk kuralı integrali. NumPy >= 2.0'da ``np.trapezoid``, altında
#: ``np.trapz``. Ad çözümü İTHAL ANINDA yapılır; çağrı başına dallanma yok.
trapezoid = getattr(np, 'trapezoid', None)
if trapezoid is None:                      # NumPy < 2.0
    trapezoid = np.trapz

TRAPEZOID_SOURCE = (
    'Composite trapezoidal rule. NumPy 2.0 renamed np.trapz to '
    'np.trapezoid (same algorithm, name only); this module resolves the '
    'name once so product code runs unchanged on NumPy 1.x and 2.x.')
