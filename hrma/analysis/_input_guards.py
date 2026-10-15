# -*- coding: utf-8 -*-
"""Sayısal girdi kapıları — analiz modüllerinin TEK KAYNAĞI.

ÖH D23 / P5B4-16. Aynı ``_require_positive`` gövdesi depoda ÜÇ analiz
modülünde (``igniter_sizing.py``, ``gimbal_mount.py``, ``valve_feedline.py``)
BİREBİR kopyalanmıştı (ölçüldü ``once.json`` P5B4-16:
``inspect.getsource`` karşılaştırması ``True``, ama
``ig._require_positive is gm._require_positive`` ``False``). Üç kopya üç
ayrı yerde düzeltilmek zorundaydı; bu modül tanımı tek yere alır.

**Neden ayrı modül:** ``hrma/utils/input_guard.py`` sözlük+anahtar
(``num(data, key, ...)``) biçiminde çalışır ve uç katmanının kapısıdır;
buradaki kapılar DEĞER biçimindedir ve saf yardımcıların içinden çağrılır.
BOOL KURALI TEK KAYNAKTAN OKUNUR (ÖH D33 / OH-D23-21 ŞART + OH-UC-06).
Bu künye v2.6.27'ye kadar *"İki katmanın KURALI aynıdır; kural değişirse
iki dosya birlikte güncellenir"* diyordu — yani tekliği bir SÖZE
bağlıyordu ve o söz ölçülmemişti. ÖLÇÜLDÜ (taban ``56f88e70``,
``docs/scofield/raw/OH/D33/app-api-uc/a1/once.json`` K1): sekiz örneğin
**ikisi** iki katmanda ayrı hüküm alıyordu ::

    numpy.bool_(True)   -> reject_bool: GEÇTİ   input_guard._is_bool: True
    numpy.bool_(False)  -> reject_bool: GEÇTİ   input_guard._is_bool: True

``numpy.bool_`` Python ``bool``un alt sınıfı DEĞİLDİR, dolayısıyla
buradaki çıplak ``isinstance(value, bool)`` onu göremiyordu; oysa
``float(numpy.bool_(True)) == 1.0`` ve çözücü sonuçları numpy taşır, yani
delik tam da bu modülün kapatmak için var olduğu delikti
(``size_igniter(main_mass_flow_kg_s=...)``). Karar bu yüzden söz değil
ÇAĞRIDIR: :func:`reject_bool` artık ``hrma.utils.input_guard._is_bool``\ı
çağırır — kural tek yerde yazılıdır, ayrışması imkânsızdır.

BORÇ (ölçülen, kapanmadı): iki katmanın *tip* kuralları hâlâ AYRIDIR ve
bu BİLEREK böyledir — ``input_guard.is_json_number`` istek sınırında
``'1.0'`` gibi sayı-benzeri DİZEYİ reddeder, bu modül ise onu kabul eder
(çözücü sonucu ``numpy.float64`` taşır; ``(int, float, str)`` kısıtı meşru
sayıları elerdi — gerekçe ``input_guard``ın "DEĞER KATMANI" bölümünde
yazılıdır). Birleşen şey bool hükmüdür, tip hükmü değildir.
``water_hammer.py`` içindeki ``_require_positive`` sözleşmesi de farklıdır
(``None`` döner, dönüşüm yapmaz) ve bu dalganın kapsamı dışındadır — o da
borç olarak kalır.

ÖLÇÜLEN KUSUR (P5B4-16, ``once.json``): ``float(True) == 1.0`` olduğu için
``bool`` sessizce sayı sayılıyordu —
``size_igniter(main_mass_flow_kg_s=True)`` HTTP hatası değil
``energy_J = 542466,67 J`` (yani mdot = 1,0 kg/s) üretiyordu; aynı kapı
``analyze_gimbal_mount(thrust_N=True)`` ile ``axial_N = 0,9945 N``
veriyordu. ``True`` bir kütle debisi ya da itki DEĞİLDİR; sayıya
çevrilmez, reddedilir.
"""

import math

# TEK KAYNAK (OH-D23-21 ŞART / OH-UC-06): doğruluk-değeri hükmü burada
# YAZILMAZ, uç katmanının merkezinden OKUNUR. Çevrim riski yoktur —
# ``hrma.utils.input_guard`` bir YAPRAK modüldür (gövdesinde tek bir
# ``hrma`` ithali yok: yalnız ``math``/``os``/``re``/``typing``) ve
# ``hrma.utils.__init__`` D32/OH-D31-06 ile tembelleştirildi, yani bu
# ithal ``hrma.engines.*`` zincirini uyandırmaz.
from hrma.utils.input_guard import _is_bool as _uc_katmani_bool_mu

__all__ = ['reject_bool', 'require_positive',
           'require_non_negative', 'require_whole_number']


def reject_bool(value, name: str, unit: str = '') -> None:
    """``bool`` sayı sayılmaz — hüküm ``input_guard._is_bool``\ındır.

    ``numpy.bool_`` DAHİLDİR: çıplak ``isinstance(value, bool)`` onu
    kaçırıyordu (ölçüm modül künyesinde, ``once.json`` K1).
    """
    if _uc_katmani_bool_mu(value):
        raise ValueError(
            f'{name} must be a number, not a boolean {unit}; got '
            f'{value!r}. True/False are not measurements: they would '
            f'silently become 1.0/0.0.')


def require_positive(value, name: str, unit: str = '') -> float:
    """Pozitif ve sonlu olma şartı; değilse İngilizce ValueError.

    Metin, üç modüldeki eski kopyalarla BİREBİR aynıdır (mevcut bekçiler
    ve kullanıcıya dönük uç mesajları korunur); tek davranış farkı
    ``bool``un artık reddedilmesidir.
    """
    reject_bool(value, name, unit)
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a positive finite number {unit}')
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(
            f'{name} must be a positive finite number {unit}; got {value!r}')
    return v


def require_non_negative(value, name: str, unit: str = '') -> float:
    """Negatif olmama şartı; değilse İngilizce ValueError."""
    reject_bool(value, name, unit)
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a non-negative finite number {unit}')
    if not math.isfinite(v) or v < 0.0:
        raise ValueError(
            f'{name} must be a non-negative finite number {unit}; '
            f'got {value!r}')
    return v


def require_whole_number(value, name: str, unit: str = '') -> int:
    """Tam sayı şartı — KESİRLİ DEĞER SESSİZCE KIRPILMAZ.

    ÖH D23 / P5B4-20. Kural ``hrma.utils.input_guard.integer`` ile aynıdır
    ("Kesirli değer reddedilir (sessizce yuvarlanmaz)"); orada sözlük
    anahtarı üzerinden, burada değer üzerinden uygulanır.

    ÖLÇÜLEN KUSUR (``once.json`` P5B4-20): ``int(11.4) == 11`` olduğu için
    ``bolt_count = 11,4`` sessizce 11 cıvataya iniyordu ve momentin
    doğurduğu en büyük cıvata yükü 13937,13 N yerine 15204,14 N
    yayımlanıyordu (**+%9,09**, yani kullanıcı gönderdiği sayıdan DAHA AZ
    cıvatalı, DAHA YÜKLÜ bir bağlantı görüyordu). Kırpma yönü daima
    aşağıdır, dolayısıyla sapma tek yönlüdür. ``12,9`` da 12 oluyordu.
    Sayı yuvarlanmaz da kırpılmaz da: hangi tam sayının istendiği
    kullanıcıya sorulur.
    """
    reject_bool(value, name, unit)
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a whole number {unit}; '
                         f'got {value!r}')
    if not math.isfinite(v):
        raise ValueError(f'{name} must be a finite whole number {unit}; '
                         f'got {value!r}')
    if not v.is_integer():
        raise ValueError(
            f'{name} must be a whole number {unit}; got {value!r}. It was '
            f'NOT truncated or rounded: a fractional count would silently '
            f'become {int(v)} and change every load derived from it.')
    return int(v)
