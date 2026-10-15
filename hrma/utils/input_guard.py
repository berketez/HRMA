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
from typing import Any, Dict, Iterable, Optional, Tuple

__all__ = ['InputError', 'num', 'integer', 'choice', 'safe_name',
           'safe_arcname', 'is_safe_arcname', 'text',
           'is_within_dir', 'safe_join',
           'mm_to_m_read',
           'finite_number', 'finite_positive', 'first_finite_positive',
           'is_json_number',
           'MM_NOT_SUPPLIED', 'MM_OK', 'MM_UNREADABLE',
           'MM_NOT_POSITIVE', 'MM_NOT_FINITE']


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


#: Arşiv girdi adı için beyaz liste: '/' ile ayrılmış, her bileşeni
#: ``safe_name`` alfabesinde olan yol. Kara liste ('..' ara) KULLANILMAZ —
#: v2.6.26 ölçümünde ters bölü ve 'C:' sürücü ön eki kara listeden kaçmıştı
#: (POSIX'te ``os.path.normpath`` ters bölüyü yol ayracı saymıyor).
_SAFE_ARCNAME = re.compile(r'[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\Z')


def is_safe_arcname(value: Any) -> bool:
    """Bu dize ZIP arşivine girdi adı olarak yazılabilir mi?

    Yalnız beyaz listeye uyan, ``..`` bileşeni içermeyen göreli yollar geçer.
    """
    if not isinstance(value, str) or not value:
        return False
    if not _SAFE_ARCNAME.match(value):
        return False
    return '..' not in value.split('/')


def safe_arcname(*parts: Any) -> str:
    """Arşiv girdi adını güvenli bileşenlerden kurar: ``safe_arcname('step', ad)``.

    Her bileşen :func:`safe_name`'den geçer, sonra '/' ile birleştirilir. Böylece
    kullanıcı adındaki ``../``, ``..\\``, ``C:\\`` ve NUL baytı bileşenin İÇİNDE
    kalamaz; dizin yapısını yalnız çağıran kod belirler.
    """
    cleaned = [safe_name(p) for p in parts if str(p or '').strip() != '']
    return '/'.join(cleaned) or 'HRMA_MOTOR'


def is_within_dir(base: str, path: str) -> bool:
    """``path`` gerçekten ``base`` dizininin altında mı?

    KARŞILAŞTIRMA ÇÖZÜMLENMİŞ YOLLAR ÜZERİNDEDİR (``os.path.realpath``):
    sembolik bağ, ``..`` bileşeni ve ``~`` genişlemesi çözüldükten SONRA
    bakılır. Dize öneki karşılaştırması tek başına yetmez — ``/tmp/xy``
    yolu ``/tmp/x`` önekini taşır ama onun altında DEĞİLDİR; bu yüzden
    ayraç sınırı da denetlenir.

    Dizinin kendisi ``True`` sayılır (``base`` == ``path``).
    """
    kok = os.path.realpath(base)
    hedef = os.path.realpath(path)
    if hedef == kok:
        return True
    return hedef.startswith(kok.rstrip(os.sep) + os.sep)


def safe_join(base: str, *parts: Any, default: str = 'HRMA_MOTOR') -> str:
    """Taban dizinin ALTINDA kalan bir dosya yolu üretir (İKİ KATMAN).

    1. Her bileşen :func:`safe_name` süzgecinden geçer — yol ayracı,
       ``..`` ve sürücü ön eki bileşenin İÇİNDE kalamaz.
    2. Üretilen yolun gerçekten ``base`` altında kaldığı
       :func:`is_within_dir` ile DOĞRULANIR.

    İkinci katman süs değildir: birinci katman atlanır/gevşetilirse ya da
    ``base``in kendisi dışarıyı gösteren bir sembolik bağ içerirse kaçış
    yine yakalanır. Kaçış varsa sessizce düzeltme YOK — :class:`InputError`.

    Uzaktan gelen (GitHub asset adı, içe aktarılan arşiv girdisi, istemci
    alan adı) her ad dosya yoluna GİRMEDEN önce buradan geçmelidir.
    """
    cleaned = [safe_name(p, default=default) for p in parts
               if str(p if p is not None else '').strip() != '']
    if not cleaned:
        raise InputError('safe_join needs at least one non-empty name part')
    candidate = os.path.join(os.path.realpath(base), *cleaned)
    if not is_within_dir(base, candidate):
        raise InputError(
            f'resolved path escapes its base directory: '
            f'{os.path.realpath(candidate)!r} is not under '
            f'{os.path.realpath(base)!r}')
    return candidate


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


# ---------------------------------------------------------------------------
# MİLİMETRE → METRE: DEPONUN TEK OKUMA NOKTASI
# ---------------------------------------------------------------------------
# ÖH D26 / app-api a5 · defter P15B2-02 (ikiz ``_mm_to_m``) + P15B2-01
# (fail-closed merkezin kapsamı).
#
# ÖLÇÜLEN KUSUR (taban 7751531, ``once.json`` bölümü ``ayrisma_*``): ``mm``
# girdisini metreye çeviren İKİ ayrı tanım vardı ve aynı girdiye FARKLI
# karar veriyorlardı:
#
#   * ``hrma/app.py:_mm_to_m_read`` — ``0``, negatif, NaN/Inf, ``bool`` ve
#     okunamayan dizeyi REDDEDER (durum koduyla birlikte);
#   * ``hrma/analysis/flight_vehicle.py:_mm_to_m`` — NaN/Inf ve ``bool``u
#     reddeder ama ``0`` ile NEGATİFİ GEÇİRİR (−5 mm → −0,005 m).
#
# Yani "bir cidar/boy kaç metre" sorusunun cevabı, sorunun hangi modülde
# sorulduğuna bağlıydı. Kural #11 (tek kaynak) gereği karar buraya alındı;
# iki taraf da bu işlevi çağırır ve kendi sözleşmesini yazmaz.
#
# Kural ``num`` ile AYNIDIR (bool sayı değildir; sonlu olmayan sayı
# değildir; ``None``/``''`` "verilmedi" demektir) — buradaki fazlalık,
# uzunluk alanının FİZİKSEL şartı: bir kalınlık/boy POZİTİF olmak
# zorundadır, ve reddin NEDENİ çağırana durum koduyla söylenir (künye
# üreten çağıran "gönderilmedi" ile "okunamadı"yı ayırt edebilsin —
# P15S1-01'in yalan künyesi tam bu ayrımın silinmesinden doğmuştu).

#: ``mm_to_m_read`` durum kodları — künye/uyarı üreten her çağıran bunları
#: ADIYLA okur (dize kopyalamak yasak, ÖK-04).
MM_NOT_SUPPLIED = 'not_supplied'   # alan yok / '' / None
MM_OK = 'ok'                       # sonlu, pozitif, okundu
MM_UNREADABLE = 'unreadable'       # 'abc', '5,0', liste, bool
MM_NOT_POSITIVE = 'not_positive'   # 0 ve negatif
MM_NOT_FINITE = 'not_finite'       # NaN / Infinity


def mm_to_m_read(value: Any) -> Tuple[Optional[float], str]:
    """Milimetre girdisini ``(metre | None, durum)`` çiftine çevirir.

    Depodaki TEK mm→m okuma noktasıdır. ``metre`` yalnız durum
    :data:`MM_OK` iken doludur; her ret hâlinde ``None`` döner ve durum
    reddin nedenini söyler. Sessiz yedek/varsayılan ÜRETMEZ — varsayılan
    isteyen çağıran onu kendi katmanında, beyan ederek koyar.
    """
    if value is None or value == '':
        return None, MM_NOT_SUPPLIED
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        # ``float(True) == 1.0``: True bir ölçü DEĞİLDİR (``num`` ile aynı
        # gerekçe). Liste/sözlük de sayı değildir.
        return None, MM_UNREADABLE
    try:
        mm = float(value)
    except (TypeError, ValueError):
        return None, MM_UNREADABLE
    if not math.isfinite(mm):
        return None, MM_NOT_FINITE
    if mm <= 0:
        return None, MM_NOT_POSITIVE
    return mm / 1000.0, MM_OK


# ---------------------------------------------------------------------------
# DEĞER KATMANI: SONLU SAYI KAPILARI
# ---------------------------------------------------------------------------
# ÖH D28 / ihracat a1 · defter OH-D27-11 (P15B2-01 devri).
#
# Bu modülün üst kısmı UÇ katmanıdır: ``num``/``integer``/``choice`` sözlük
# + anahtar biçiminde çalışır ve istemci gövdesini okur. Depoda bir de DEĞER
# katmanı vardır — saf yardımcıların içinden çağrılan, çözücü SONUCUNDAN
# okuyan kapılar. Kuralı ``hrma/analysis/_input_guards.py`` yazmıştı ve o
# modülün künyesi iki katmanın ayrımını zaten kurar: *"İki katmanın KURALI
# aynıdır; kural değişirse iki dosya birlikte güncellenir."*
#
# Eksik olan üçüncü biçimdi: **yükseltmeyen** değer kapısı. Bir dışa aktarım
# üreticisi çözülemeyen alanı istisnayla değil ``None``/yedek ile karşılar,
# çünkü kararı çağıran verir ("hesaplanmadı" beyan eder, bkz.
# ``openrocket_integration.resolve_eng_inputs`` ``missing_fields``). Bu biçim
# merkezde olmadığı için sekiz ihracat modülü kendi tanımını yazmıştı.
#
# ÖLÇÜLEN KUSUR (taban 7cd08bcc, ``once.json`` + ``once_urun.json``):
# sekiz tanımın **8'i de** merkeze bağsızdı ve değer katmanı sözleşmesinden
# **13 kararda** ayrışıyordu — hepsi tek sebepten: ``float(True) == 1.0``.
# Ürün yüzeyinde ölçülen sonuç (``once_urun.json``, 6 ölçümün 5'i sızdı):
#
#   OpenRocketExporter.resolve_eng_inputs({'case_diameter': True})
#     -> case_diameter = 1.0   (``missing_fields`` BOŞ)
#
# Yani ``True`` bir gövde çapı sayılıyor ve ``.eng`` künyesine uydurma
# **1,0 m** iniyordu; alanın "çözülemedi" diye raporlanması gerekirdi.
# ``True`` bir ölçü DEĞİLDİR (P5B4-16 hükmü, ``_input_guards.reject_bool``).
#
# Tip kısıtı BİLEREK taşınmadı: ``num`` yalnız ``int``/``float``/``str``
# kabul eder, çünkü JSON gövdesinden başkası gelemez. Değer katmanında bu
# kısıt YANLIŞ olurdu — ``np.float32``/``np.int64`` ``(int, float, str)``
# örneği DEĞİLDİR (ölçüldü, ``once.json`` ``uc_katmani_ayrisma``) ve çözücü
# sonucu bu tipleri taşır; kısıt taşınsaydı ihracat hattı MEŞRU sayıları
# reddederdi. Bu yüzden değer katmanı ``float()``a güvenir, yalnız ``bool``u
# ve sonlu olmayanı eler.


def is_bool(value: Any) -> bool:
    """``value`` bir doğruluk değeri mi? (``numpy.bool_`` DAHİL)

    ``isinstance(x, bool)`` tek başına YETMEZ: ``numpy.bool_`` Python
    ``bool``un alt sınıfı DEĞİLDİR (ölçüldü) ama ``float()`` onu da
    1.0/0.0'a çevirir. Çözücü sonuçları numpy taşıdığı için bu delik
    gerçektir. numpy içe aktarılmaz — ``dtype.kind`` ördek denetimi yeter
    ('b' = boolean, NumPy dtype.kind tablosu).
    """
    if isinstance(value, bool):
        return True
    kind = getattr(getattr(value, 'dtype', None), 'kind', None)
    return kind == 'b'


#: ÖH D33-2 / app-api-uc a1 (OH-D32-15) — eski özel ad korunur.
#: Kural tek yerde yazılıdır; ``_is_bool`` yalnız aynı nesneye başka bir
#: addır (modül içi çağrılar ve depodaki eski içe aktarmalar için).
_is_bool = is_bool


def is_json_number(value: Any) -> bool:
    """İSTEK GÖVDESİNDEKİ bu değer bir JSON SAYISI mı?

    ÖH D30 / defter OH-D29-07 — TEK KURAL, ÜÇ KOPYA. Bu soru depoda üç ayrı
    yerde üç ayrı biçimde yanıtlanıyordu ve yanıtlar AYRIŞMIŞTI (ölçüldü,
    ``docs/scofield/raw/OH/D30/app-api-dogrulama/a1/once.json`` ->
    ``OH-D29-07``, taban ``ab7cf68b``): aynı ``"293.15"`` / ``"40.0"``
    biçimindeki sayı-benzeri dize

        ``POST /calculate``        (``oxidizer_temp``)   -> HTTP 200
        ``POST /calculate_solid``  (``chamber_pressure``)-> HTTP 400
        ``POST /calculate_liquid`` (``chamber_pressure``)-> HTTP 400

    veriyordu. Yani ürünün üç ucu, aynı tel biçimindeki aynı değere üç ayrı
    hüküm veriyordu; hangisinin uygulanacağı kullanıcının hangi sekmede
    olduğuna kalıyordu.

    KANON REDDETMEKTİR ve bu deponun KENDİ ölçtüğü gerekçedir (ÖH Z5S / S5,
    P16B2-11): dize kapıyı ``float('40')`` ile geçtiğinde çözücüye kadar
    iniyor ve orada HAM Python metniyle patlıyordu ("'<=' not supported
    between instances of 'str' and 'float'"). JSON'un sayı tipi vardır;
    istemci sayı göndermek istiyorsa sayı gönderir.

    :func:`finite_number` İLE KARIŞTIRILMAMALIDIR — o AYRI bir soruyu
    yanıtlar: "bu değer sonlu bir sayı olarak OKUNABİLİR mi?" (kayıtlı
    proje dosyası, içe aktarılan katalog, eski sözleşme). Bu fonksiyon
    İSTEK SINIRINDA "gelen tel biçimi doğru mu?" sorusunu yanıtlar. İki
    soru ayrıdır; kusur, ikisinin AYNI soru sanılıp farklı yanıtlanmasıydı.

    ``bool`` sayı DEĞİLDİR (``float(True) == 1.0`` bandın içine düşer;
    depo bu ayrımı ``num`` ve ``_form_band_kapisi`` içinde zaten yapıyor).
    ``numpy.bool_`` da elenir (bkz. :func:`_is_bool`).
    """
    if _is_bool(value):
        return False
    return isinstance(value, (int, float))


def finite_number(value: Any, default: Any = None) -> Any:
    """Sonlu sayı döndürür; çevrilemeyen/sonlu olmayan için ``default``.

    ``0`` ve NEGATİF geçerlidir (bir hız, sıcaklık farkı ya da eksen konumu
    sıfır veya negatif olabilir). ``bool`` sayı sayılmaz.

    Yükseltmez: karar çağıranındır — üretici alanı "hesaplanmadı" diye
    beyan eder. Yükselten biçim için
    :func:`hrma.analysis._input_guards.require_positive` ailesine bakın.
    """
    if _is_bool(value):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def finite_positive(value: Any, default: Any = None) -> Any:
    """Sonlu ve POZİTİF sayı döndürür; aksi hâlde ``default``.

    Bir çap, boy, kalınlık ya da kütle pozitif olmak zorundadır; ``0`` ve
    negatif bir ölçü değil, çözülememiş bir alandır.
    """
    parsed = finite_number(value)
    if parsed is None or not parsed > 0.0:
        return default
    return parsed


def first_finite_positive(*values: Any, default: Any = None) -> Any:
    """Sırayla bakar, İLK sonlu-pozitif değeri döndürür; yoksa ``default``.

    Aynı ölçünün birden çok anahtarda aranması (``case_diameter`` yoksa
    ``chamber_diameter`` ...) dışa aktarımda yaygındır; sıra çağıranın
    önceliğidir. Uydurma yedek ÜRETMEZ.
    """
    for value in values:
        parsed = finite_positive(value)
        if parsed is not None:
            return parsed
    return default
