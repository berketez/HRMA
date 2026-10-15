#!/usr/bin/env python3
"""Canlı duman testinin GÖVDE hükmü — 200 tek başına "hesap yaptı" değildir.

ÖH D23 / altyapi · defter P13B1-11.

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D23/altyapi/a2/once.json``, taban
ef527ae): ``.github/workflows/release.yml`` içindeki "Canlı duman testi
(kapı 6/8)" adımının karar zincirinde gövdeye bakan **tek dal yoktu** —
``$KOD`` 200 ise "GEÇTİ" basılıyordu. Gövde yalnız hata mesajında,
``head -c 200`` ile anılıyordu. Yani uçların birinin gövdesi ``{}``,
``null`` ya da bir HTML hata sayfası olsa bile kapı AÇIK kalırdı; adımın
kendi yorumu ise "gerçekten hesap yaptığı"nı sınadığını söylüyordu.

Bu betik o boşluğu kapatır ve FAIL-CLOSED çalışır:

* dosya okunamaz / JSON değilse   -> KALDI
* gövde nesne değilse             -> KALDI
* istenen alan yoksa              -> KALDI (alan adıyla)
* alan sayı değilse / bool ise    -> KALDI
* alan sonsuz ya da NaN ise       -> KALDI
* alan <= 0 ise                   -> KALDI

Eşik YOKTUR. "Sonlu ve kesin pozitif"in ötesine geçmek kapıya beyan
edilmemiş bir kabul ölçütü koymak olurdu; bu betiğin işi bir sayının
DOĞRU olduğunu söylemek değil, ortada bir sayı BULUNDUĞUNU kanıtlamaktır.

Kullanım:
    python3 tools/duman_govde_kapisi.py <govde.json> <alan1,alan2,...>

Alan adı noktalı yol olabilir (``motor.c_star``): hibritte sayılar
``motor`` altında, katı ve sıvıda üst düzeydedir (ölçüldü, 5 Eylül 2026).

Çıkış kodu 0 = geçti (özet stdout'a), 1 = kaldı (gerekçe stdout'a).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, List, Tuple


def alan_getir(govde: Any, yol: str) -> Tuple[bool, Any]:
    """Noktalı yolu izler. ``(bulundu, deger)`` döndürür."""
    dugum = govde
    for parca in yol.split('.'):
        if not isinstance(dugum, dict) or parca not in dugum:
            return False, None
        dugum = dugum[parca]
    return True, dugum


def alani_hukumle(yol: str, bulundu: bool, deger: Any) -> str:
    """Tek alanın hükmü. Boş dize = geçti, dolu dize = kalma gerekçesi."""
    if not bulundu:
        return '%s alanı gövdede YOK' % yol
    if isinstance(deger, bool) or not isinstance(deger, (int, float)):
        return '%s sayı değil (%s: %r)' % (yol, type(deger).__name__, deger)
    if not math.isfinite(float(deger)):
        return '%s sonlu değil (%r)' % (yol, deger)
    if float(deger) <= 0.0:
        return '%s kesin pozitif değil (%r)' % (yol, deger)
    return ''


def govde_hukmu(govde: Any, alanlar: List[str]) -> Tuple[bool, str]:
    if not isinstance(govde, dict):
        return False, ('gövde bir JSON nesnesi değil (%s)'
                       % type(govde).__name__)
    if not alanlar:
        # FAIL-CLOSED: sınanacak alan verilmediyse bu bir "temiz geçiş"
        # değil, ölçüm YAPILMAMASIDIR.
        return False, 'sınanacak alan listesi boş — ölçüm yapılmadı'
    gerekceler = []
    olculen = []
    for yol in alanlar:
        bulundu, deger = alan_getir(govde, yol)
        gerekce = alani_hukumle(yol, bulundu, deger)
        if gerekce:
            gerekceler.append(gerekce)
        else:
            olculen.append('%s=%.6g' % (yol, float(deger)))
    if gerekceler:
        return False, '; '.join(gerekceler)
    return True, ', '.join(olculen)


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print('kullanım: duman_govde_kapisi.py <govde.json> <alan1,alan2,...>')
        return 1
    yol = Path(argv[1])
    alanlar = [a.strip() for a in argv[2].split(',') if a.strip()]
    try:
        ham = yol.read_text(encoding='utf-8')
    except OSError as hata:
        print('gövde dosyası okunamadı (%s): %s' % (yol, hata))
        return 1
    try:
        govde = json.loads(ham)
    except json.JSONDecodeError as hata:
        print('gövde JSON değil (%s): ilk 120 bayt %r'
              % (hata.msg, ham[:120]))
        return 1
    gecti, ozet = govde_hukmu(govde, alanlar)
    print(ozet)
    return 0 if gecti else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
