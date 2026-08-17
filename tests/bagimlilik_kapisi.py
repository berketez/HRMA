"""Bağımlılık kapısı — "kurulu değil" gerekçesi YALAN SÖYLEYEMEZ.

Bu deponun ölçülmüş kusur sınıfı: opsiyonel bir bağımlılığa dayanan bekçiler,
ÜRÜN YOLU bozulduğunda da "kütüphane kurulu değil" diyerek atlıyor. Atlama
sessizdir, CI yeşil kalır, kusur görünmez.

Ölçüm (17 Ağustos 2026, parti 31 / T2-2):

    HRMA_BOZ_MEKANIZMA=1  ->  cantera KURULU ama ``ct.Solution`` her
    mekanizmada patlıyor (ürün yolu bozuk):

        tests/test_combustion.py + test_combustion_cea_validation.py
        + test_kinetic_efficiency.py  ->  2 failed, 61 passed, **39 skipped**

    39 bekçi, gerekçesi "Cantera kurulu değil" olan bir atlamaya düştü —
    oysa Cantera kuruluydu. Yalnız ``test_kinetic_efficiency.py`` (kapısı
    doğrudan modül bayrağına bağlı) kırmızıya döndü.

Kapının kuralı üç durumludur:

======================================  ======================================
durum                                   davranış
======================================  ======================================
kütüphane KURULU DEĞİL                  ATLA (dürüst, gerekçesi doğru)
kütüphane kurulu, ürün yolu AÇIK        KOŞ
kütüphane KURULU, ürün yolu KAPALI      **KIRMIZI** (bu, ürün kusurudur)
======================================  ======================================

CI tarafında eşi vardır: ``.github/workflows/tests.yml`` ve ``release.yml``,
cantera / CoolProp / numba'nın gerçekten kurulu olduğunu ayrı bir adımda
doğrular. Yani üçüncü satır CI'da fiilen "her zaman geçerli" hale gelir.
"""

import importlib.util

import pytest

__all__ = ['kurulu_mu', 'kapi']


def kurulu_mu(modul_adi: str) -> bool:
    """Modül bu ortamda ithal EDİLEBİLİR mi? (ithal etmeden bakar)

    Ürün bayraklarına (``cantera_available``, ``_COOLPROP``, ...) sorulmaz —
    onlar "kurulu mu" ile "yol açık mı" sorularını tek bayrakta birleştiriyor;
    bu kapının varlık sebebi tam olarak o birleşmeyi çözmektir.
    """
    try:
        return importlib.util.find_spec(modul_adi) is not None
    except (ImportError, ValueError):  # pragma: no cover - bozuk paket kaydı
        return False


def kapi(modul_adi: str, urun_yolu_acik: bool, kirik_aciklamasi: str) -> None:
    """Üç durumlu kapı. Ayrıntı için modül docstring'ine bakınız.

    Parameters
    ----------
    modul_adi
        İthal adı (``'cantera'``, ``'CoolProp'``, ``'numba'``).
    urun_yolu_acik
        Ürünün o kütüphaneyi GERÇEKTEN kullandığını söyleyen ölçüm
        (bayrak değil, ürünün kendi durumu).
    kirik_aciklamasi
        Yol kapalıyken basılacak teşhis: nerede kırıldığı ADIYLA yazılır.
    """
    if urun_yolu_acik:
        return
    if not kurulu_mu(modul_adi):
        pytest.skip(
            f'{modul_adi} kurulu değil — isteğe bağlı bağımlılık, bu bekçi '
            f'bu ortamda koşamaz (gerekçe DOĞRULANDI: '
            f'importlib.util.find_spec({modul_adi!r}) is None)')
    pytest.fail(
        f'{modul_adi} KURULU ama ürün yolu kapalı — bu bir ÜRÜN KUSURUDUR, '
        f'atlanamaz.\n{kirik_aciklamasi}\n'
        f'(Eskiden bu durum "{modul_adi} kurulu değil" gerekçesiyle SESSİZCE '
        f'atlanıyordu; parti 31 / T2-2, T2-3.)')
