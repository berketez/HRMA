"""İstemci girdisi doğrulama katmanı.

Rotalar kendi şemalarını AÇIKÇA yazar (okunabilirlik), ama dönüştürme /
sonluluk / aralık mantığı tek yerde yaşar. Projede önceden üç ayrı desen
yan yana duruyordu; bu modül en temizi olan ``_json_float`` desenini
genelleştirir.

İlkeler:
- ``0`` ile "verilmedi" ASLA karıştırılmaz. Yalnız ``None`` ve ``''``
  varsayılana düşer. (Eski davranış ``thrust=0`` girdisini sessizce
  1000 N'a çeviriyordu — kullanıcı yanlış sonuç aldığını fark etmiyordu.)
- Bütçe/aralık aşılırsa sessiz kısaltma YOK, açık hata.
- Dosya adı bileşenleri beyaz listeyle sadeleştirilir (yol ayracı geçemez).
"""

from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, Iterable, Optional

__all__ = ['InputError', 'num', 'integer', 'choice', 'safe_name', 'text']


class InputError(ValueError):
    """İstemci girdisi hatası — rota katmanı bunu HTTP 400'e çevirir."""


_SAFE_NAME = re.compile(r'[^A-Za-z0-9._-]+')


def safe_name(value: Any, default: str = 'HRMA_MOTOR',
              maxlen: int = 64) -> str:
    """Dosya adı bileşeni üret: yol ayracı yok, yalnız beyaz liste.

    ``os.path.join`` ikinci bileşen MUTLAK yol ise birinciyi tamamen atar;
    göreli ``../`` de aynı sonucu verir. Bu yüzden dışarıdan gelen her ad
    dosya yoluna girmeden önce buradan geçmelidir. Üretilen ZIP arşivinin
    İÇİNDEKİ adlar için de kullanılır (zip-slip taşımayalım).
    """
    raw = str(value or '').replace('\\', '/').strip()
    base = os.path.basename(raw)
    cleaned = _SAFE_NAME.sub('_', base).strip('._')
    return (cleaned or default)[:maxlen]


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def num(data: Dict[str, Any], key: str, *,
        lo: Optional[float] = None, hi: Optional[float] = None,
        default: Optional[float] = None, unit: str = '',
        required: bool = False) -> Optional[float]:
    """Sonlu sayı çek; aralık dışıysa veya NaN/Inf ise :class:`InputError`.

    ``0`` geçerli bir değerdir ve varsayılana DÜŞMEZ.
    """
    value = data.get(key)
    suffix = f' ({unit})' if unit else ''
    if _missing(value):
        if required:
            raise InputError(f"'{key}' is required{suffix}")
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InputError(
            f"'{key}' must be a number (got {type(value).__name__})")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise InputError(f"'{key}' must be a number (got {value!r})")
    if not math.isfinite(parsed):
        raise InputError(f"'{key}' must be a finite number (got {value})")
    if lo is not None and parsed < lo:
        raise InputError(
            f"'{key}' must be at least {lo}{suffix}; got {parsed:g}")
    if hi is not None and parsed > hi:
        raise InputError(
            f"'{key}' must be at most {hi}{suffix}; got {parsed:g}")
    return parsed


def integer(data: Dict[str, Any], key: str, *,
            lo: Optional[int] = None, hi: Optional[int] = None,
            default: Optional[int] = None, unit: str = '',
            required: bool = False) -> Optional[int]:
    """Tam sayı çek. Kesirli değer reddedilir (sessizce yuvarlanmaz)."""
    parsed = num(data, key, lo=lo, hi=hi, unit=unit, required=required,
                 default=None if default is None else float(default))
    if parsed is None:
        return None
    if float(parsed).is_integer():
        return int(parsed)
    raise InputError(f"'{key}' must be a whole number; got {parsed:g}")


def choice(data: Dict[str, Any], key: str, allowed: Iterable[str], *,
           default: Optional[str] = None,
           required: bool = False) -> Optional[str]:
    """Sabit listeden seçim çek; liste dışıysa :class:`InputError`."""
    value = data.get(key)
    options = list(allowed)
    if _missing(value):
        if required:
            raise InputError(
                f"'{key}' is required (one of: {', '.join(options)})")
        return default
    text_value = str(value).strip()
    if text_value not in options:
        raise InputError(
            f"'{key}' must be one of: {', '.join(options)}; got "
            f"{text_value!r}")
    return text_value


def text(data: Dict[str, Any], key: str, *, maxlen: int = 200,
         default: str = '', required: bool = False) -> str:
    """Serbest metin çek ve uzunluğunu sınırla (dosya yoluna GİRMEZ).

    Dosya adı üretecekseniz :func:`safe_name` kullanın.
    """
    value = data.get(key)
    if _missing(value):
        if required:
            raise InputError(f"'{key}' is required")
        return default
    parsed = str(value).strip()
    if len(parsed) > maxlen:
        raise InputError(f"'{key}' must be at most {maxlen} characters; "
                         f"got {len(parsed)}")
    return parsed
