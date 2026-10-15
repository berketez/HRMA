"""İstek JSON'unun sıkı ayrıştırılması (V3 SG-1 fuzz bulguları F-01, F-03).

Ürünün bütün JSON okuması iki yoldan geçer: gövde kapısı
(``hrma/app.py::_reject_malformed_json_body``) ve uçların
``request.get_json()``'i (Flask bunu ``app.json.loads``'a devreder). İkisi de
buradaki ``loads_strict``'i kullanır; böylece aşağıdaki iki sınıf HER uçta
aynı biçimde, hesaba ulaşmadan reddedilir.

KUSUR (ölçüldü, ``docs/scofield/raw/OH/V3/guvenlik/sg1/``; Flask
``test_client``, gerçek sunucu ayarı ``TESTING=False``):

* **Çok derin iç içe JSON** (``[[[…]]]``, 100 000 düzey ≈ 200 KB, gövde
  tavanının çok altında): CPython ayrıştırıcısı ``RecursionError`` atar.
  ``RecursionError`` ``ValueError`` DEĞİLDİR; kapının ``except
  (ValueError, UnicodeDecodeError)`` dalı ve Werkzeug'un ``get_json(silent=
  True)``'si onu yakalamaz → bütün JSON uçlarında HTML 500 (tam koşuda 111
  istek; kendi taşıyıcısı olan yükleme/proje uçlarında 1 MiB üstü derin
  gövdeyle de).
* **float64'e sığmayan tam sayı** (``10**400``): JSON'da geçerli, Python'da
  ``int``; uçların ``float(x)`` dönüşümü ``OverflowError`` atar ve
  ``except (TypeError, ValueError)`` dallarını atlar → 26 uçta HTTP 500
  (gövdede ham ``int too large to convert to float``).

Düzeltme fail-closed: iki durum da ``ValueError`` alt sınıfı olarak
yükseltilir. Kapı bunları kendi makine-okur koduyla 400'e çevirir; kapıya
uğramayan uç (kendi boyut kapısı olan büyük gövde) ``get_json(silent=True)``
ile ``None`` alır ve kendi "içerik yok" 400'ünü verir. Hiçbir değer
uydurulmaz, hiçbir hesap başlatılmaz.

Maliyet: tam sayı denetimi pahalı yoldan (her tam sayı için Python geri
çağrısı) YALNIZ gövdede ``FLOAT_MAX_INT_DIGITS`` uzunlukta bir rakam dizisi
varsa yapılır; o uzunlukta dizi yoksa taşma imkânsızdır ve ayrıştırma
standart C yolundan gider (ölçülü fark yok).
"""
from __future__ import annotations

import json
import re
import sys

from flask.json.provider import DefaultJSONProvider

#: float64'ün en büyük sonlu değerinin tam sayı kısmının ondalık basamak
#: sayısı (``sys.float_info.max`` ≈ 1,8e308 → 309). Daha kısa rakam dizisi
#: float'a her zaman sığar.
FLOAT_MAX_INT_DIGITS = len(str(int(sys.float_info.max)))
_LONG_DIGIT_RUN_BYTES = re.compile(rb'\d{%d}' % FLOAT_MAX_INT_DIGITS)
_LONG_DIGIT_RUN_TEXT = re.compile(r'\d{%d}' % FLOAT_MAX_INT_DIGITS)

#: Ayrıştırma reddinin HTTP kodu (istemci hatası; gövde kapısıyla aynı).
PARSE_REJECTION_HTTP_STATUS = 400


class JSONNumberOutOfRange(ValueError):
    """Gövdedeki bir tam sayı float64'e dönüştürülemiyor."""

    error_code = 'number_out_of_range'
    message = ('A number in the request body is too large to be represented '
               'as a double-precision value (magnitude above about 1.8e308). '
               'No analysis was attempted and no value was assumed.')


class JSONNestingTooDeep(ValueError):
    """Gövde, ayrıştırıcının özyineleme sınırından derin iç içe."""

    error_code = 'json_nesting_too_deep'
    message = ('The request body nests JSON arrays or objects deeper than '
               'the server parses. No analysis was attempted.')


def _checked_int(text):
    value = int(text)
    try:
        float(value)
    except OverflowError:
        raise JSONNumberOutOfRange(
            f'integer with {len(text.lstrip("-"))} digits') from None
    return value


def _has_long_digit_run(data):
    if isinstance(data, (bytes, bytearray)):
        return _LONG_DIGIT_RUN_BYTES.search(data) is not None
    return _LONG_DIGIT_RUN_TEXT.search(data) is not None


def loads_strict(data, **kwargs):
    """``json.loads`` + iki koruma (taşan tam sayı, aşırı derinlik).

    İki koruma da ``ValueError`` alt sınıfı yükseltir; çağıranın mevcut
    ``except ValueError`` dalları ve Werkzeug'un ``silent=True`` sözleşmesi
    değişmeden çalışır.
    """
    if 'parse_int' not in kwargs and _has_long_digit_run(data):
        kwargs['parse_int'] = _checked_int
    try:
        return json.loads(data, **kwargs)
    except RecursionError:
        raise JSONNestingTooDeep('JSON nesting exceeds the parser limit') \
            from None


def parse_rejection(exc):
    """Koruma reddi ise ``(gövde, 400)``; değilse ``None`` (çağıran kendi
    ``malformed_json_body`` yanıtını verir)."""
    if isinstance(exc, (JSONNumberOutOfRange, JSONNestingTooDeep)):
        return ({'status': 'error', 'error': exc.error_code,
                 'message': exc.message}, PARSE_REJECTION_HTTP_STATUS)
    return None


class StrictJSONProvider(DefaultJSONProvider):
    """``app.json``: istek gövdesi ``loads_strict`` ile ayrıştırılır.

    Yalnız ``loads`` değişir; yanıt üretimi (``dumps``) Flask'ın
    varsayılanıdır.
    """

    def loads(self, s, **kwargs):
        return loads_strict(s, **kwargs)
