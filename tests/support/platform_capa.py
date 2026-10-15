"""Sayısal çapaların platform kapsamı (v3.0.0, 15 Eki 2026).

Depodaki regresyon çapalarının (``pytest.approx(<ölçülmüş sayı>, rel=1e-12)``
türü kilitler) hepsi darwin/arm64'te ölçüldü. v3.0 takımı CI'da (ubuntu,
linux/x86_64) ilk kez koştuğunda bu çapalar AYNI kodla 1e-11 – 1e-7 bağıl
sapma verdi (koşum 38770162288): libm, SIMD ve kayan nokta işlem sırası
platformdan platforma bit düzeyinde değişir; ODE tümlevinde uyarlamalı adım
bu farkı büyütür. Çapanın SORDUĞU soru (davranış değişti mi) iki platformda
da aynıdır; değişen yalnız ulaşılabilir kesinliktir.

Kural: referans platformda çapanın kendi toleransı AYNEN geçerlidir. Başka
platformda her çağrı yerinin kendi gerekçeli toleransı kullanılır — o tolerans
CI'da ÖLÇÜLEN sapmanın üstünde ama davranış değişikliğini (çapaların
yenilendiği kaymalar: 1e-4 – 1e-2) yakalayacak kadar dardır.
"""

import platform
import sys

#: Çapaların ölçüldüğü platform.
REFERANS_PLATFORM = 'darwin/arm64'


def bu_platform():
    return '%s/%s' % (sys.platform, platform.machine())


def referans_platformda_mi():
    return bu_platform() == REFERANS_PLATFORM


def capa_rel(rel_referans, rel_yabanci):
    """Referans platformda ``rel_referans``, başka platformda ``rel_yabanci``."""
    return rel_referans if referans_platformda_mi() else rel_yabanci
