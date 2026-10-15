"""JSON serileştirme bekçilerinin ortak, İDDİALI çekirdeği (ÖH D22 · P13B1-10).

ÖLÇÜLDÜ (ÖH D22, ``once.json``/``P13B1-10``): "yanıt JSON'a çevrilebiliyor"
diyen yedi test gövdesinde **hiç ``assert`` yoktu** — tek yaptıkları
``json.dumps(...)`` çağırmaktı. Böyle bir gövde üç şeyi birden kaçırır:

1. **Vakumluk.** Sözlük boş gelirse (blok hiç üretilmemişse) ``dumps({})``
   yine başarılı olur; test yeşil kalır ve "yeni bloklar sözleşmeyi
   bozmuyor" der — oysa blok ORTADA YOKTUR.
2. **Gidiş–dönüş kaybı.** ``dumps`` başarılı olsa bile çözülen nesne
   yayımlanandan farklı olabilir (sözlük anahtarı sayı ise dizeye döner).
3. **NaN/Inf sızıntısı.** Python ``json`` varsayılan olarak ``NaN``,
   ``Infinity`` basar; bunlar STANDART JSON DEĞİLDİR ve katı bir
   ayrıştırıcı (tarayıcı ``JSON.parse`` dâhil) onları reddeder. Yani
   ``dumps`` geçse bile ürünün yayımladığı gövde istemcide patlayabilir.

Bu yardımcı üçünü de kapatır ve tek yerde durur.
"""
from __future__ import annotations

import json
from typing import Any, Mapping


def json_capasi(govde: Mapping[str, Any], ad: str = 'gövde') -> str:
    """``govde``yi KATI JSON'a çevirir ve gidiş–dönüşü sınar.

    Döndürdüğü dize, çağıranın ek iddia kurabilmesi içindir.
    """
    assert isinstance(govde, Mapping), (
        '%s bir eşleme değil: %s' % (ad, type(govde).__name__))
    assert govde, '%s boş — "serileştirilebilir" iddiası vakumluk' % ad
    for anahtar, deger in govde.items():
        assert isinstance(anahtar, str), (ad, anahtar)
        assert deger is not None, (
            '%s.%s None — blok üretilmemiş, sözleşme sınanmıyor'
            % (ad, anahtar))
    # allow_nan=False: NaN/Infinity STANDART JSON değildir; katı
    # ayrıştırıcı (tarayıcı JSON.parse) reddeder. Varsayılan dumps bunu
    # sessizce basardı.
    metin = json.dumps(govde, allow_nan=False, sort_keys=True)
    geri = json.loads(metin)
    assert geri == govde, (
        '%s gidiş–dönüşte değişti (sözlük anahtarı ya da tip kaybı)' % ad)
    return metin
