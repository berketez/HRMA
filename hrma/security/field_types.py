"""Alan düzeyinde tip kapısı (V3 SG-1 fuzz bulguları F-04…F-11).

Fuzz koşusu (``docs/scofield/raw/OH/V3/guvenlik/sg1/``) birkaç uçta aynı
kalıbı ölçtü: gövdedeki bir alan beklenen tipte değilse (metin yerine
liste/sözlük/sayı, nesne yerine metin, sayı yerine metin) değer çekirdeğe
olduğu gibi iniyor, orada ``unhashable type`` / ``has no attribute 'lower'``
/ ``'<' not supported`` gibi bir Python hatasına dönüşüyor ve ucun genel
``except Exception`` dalı bunu **HTTP 500** + ham Python metni olarak
yayımlıyordu. İstemci hatası sunucu arızası gibi görünüyordu.

Bu modül ucun GİRİŞİNDE tipi denetler ve makine-okur **400** üretir
(``invalid_input`` + ``invalid_fields``; ``input_guard`` yakalayan uçların
mevcut sözleşmesiyle aynı biçim). Değer uydurulmaz, varsayılana düşülmez,
hesap başlatılmaz. Alan HİÇ verilmemişse (``None``) karar çağıranındır
(varsayılan ya da zorunluluk ucun kendi sözleşmesidir).

Flask'a bağımlı değildir: ``(gövde, kod)`` döndürür, çağıran ``jsonify``
eder.
"""
from __future__ import annotations

import numbers

#: Tip reddinin HTTP kodu (istemci hatası).
FIELD_TYPE_HTTP_STATUS = 400
#: Yanıtta ham değerin yankılanmaz; yalnız tip adı (kısaltılmış) döner.
TYPE_NAME_MAX_CHARS = 40

#: Beklenen tip → (``reason`` kodu, iletideki tanım).
EXPECTED_TYPES = {
    'string': ('not_a_string', 'a text value'),
    'object': ('not_an_object', 'a JSON object'),
    'array': ('not_an_array', 'a JSON array'),
    'number': ('not_a_json_number', 'a JSON number'),
    'number_or_array': ('not_a_json_number',
                        'a JSON number or an array of JSON numbers'),
}


def _is_json_number(value):
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _matches(value, expected):
    if expected == 'string':
        return isinstance(value, str)
    if expected == 'object':
        return isinstance(value, dict)
    if expected == 'array':
        return isinstance(value, list)
    if expected == 'number':
        return _is_json_number(value)
    if expected == 'number_or_array':
        return _is_json_number(value) or (
            isinstance(value, list) and all(_is_json_number(v)
                                            for v in value))
    raise ValueError(f'unknown expected type: {expected!r}')


def _invalid_body(field, reason, message, extra=None):
    entry = {'field': field, 'reason': reason}
    if extra:
        entry.update(extra)
    return ({
        'status': 'error',
        'error': 'invalid_input',
        'message': message,
        'invalid_fields': [entry],
    }, FIELD_TYPE_HTTP_STATUS)


def field_type_error(field, value, expected):
    """``value`` beklenen tipte değilse ``(gövde, 400)``, ise ``None``.

    ``None`` (alan yok / JSON null) denetlenmez: o karar çağıranındır.
    """
    if value is None or _matches(value, expected):
        return None
    reason, description = EXPECTED_TYPES[expected]
    received = type(value).__name__[:TYPE_NAME_MAX_CHARS]
    return _invalid_body(
        field, reason,
        f"'{field}' must be {description}; received {received}. "
        'No analysis was attempted and no value was assumed.',
        {'received_type': received})


def first_field_type_error(data, expected_by_field):
    """``{alan: beklenen_tip}`` sırasıyla ilk tip reddini döndürür."""
    for field, expected in expected_by_field.items():
        error = field_type_error(field, data.get(field), expected)
        if error is not None:
            return error
    return None


def input_error_body(field, exc):
    """``input_guard.InputError`` → ``(gövde, 400)`` (ileti aynen)."""
    return _invalid_body(field, 'invalid_text', str(exc))
