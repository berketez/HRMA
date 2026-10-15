"""docs/ kanıtının TEK okuma kapısı — ÖH D36 kanit-atlama (yayın dalı engeli, seçenek A).

NEDEN VAR
---------
Yayın dalı ``packaging/yayin_dali_uret.sh`` ile ``docs/scofield``,
``docs/arastirma`` ve ``docs/tasarim`` ÇIKARILARAK üretilir (Berke kuralı,
15 Eylül 2026: iç dokümanlar yayımlanmaz). Test süitinin bir kısmı ölçüm
kanıtını bu dizinlerden okur. Ölçüldü (23 Eylül 2026, HEAD bb7ee57c, docs'suz
kopya): ``tests/test_d23_bekci_cevirisi_a1.py`` kanıtı İTHAL anında okuyordu ve
``pytest --collect-only`` TOPLAMADA ``FileNotFoundError`` ile duruyordu —
tek test değil, bütün süit. Toplamayı geçen dosyalardaki okumalar da test
anında kırmızı verirdi; yani yayın dalı CI'da (``pytest tests/``) koşamıyordu.

SÖZLEŞME
--------
``kanit_yolu(bagil)``
    Kanıt yolunu depo köküne göre ÇÖZER ve ``pathlib.Path`` döndürür. Dosya
    sistemine dokunmaz, atlamaz — modül/sınıf sabiti tanımlamak içindir.

``kanit_gerekli(yol)``
    Kanıtı OKUMADAN HEMEN ÖNCE çağrılır (okuma, varlık denetimi, ``node``/
    ``python`` ile kanıt betiği koşturma, ``spec_from_file_location``); ``yol``'u AYNEN döndürür (tür
    korunur: ``str`` gelen ``str``, ``Path`` gelen ``Path`` döner). Kural:

    1. Kanıt VARSA hiçbir şey olmaz.
    2. Yoksa ve ``HRMA_KANIT_ZORUNLU=1`` ise: ``pytest.fail`` — atlama DEĞİL
       HATA (geliştirici / ana depo CI koşusu için).
    3. Yoksa ve GELİŞTİRME AĞACIYSA (``docs/scofield`` VAR): ATLANMAZ; yol
       aynen döner ve çağıran eskisi gibi kırmızı verir. Sessiz kayıp yok.
    4. Yoksa ve ağaç docs'suzsa (yayın dalı): gerekçeli ``pytest.skip``.
       Test gövdesinde çağrılırsa YALNIZ o test, modül ithal edilirken
       çağrılırsa (modül düzeyi okuma) modülün tamamı atlanır — ikincisi
       olmasa pytest toplamada düşer.

    Kanıt dizinleri DIŞINDAKİ bir yol (ör. ``hrma/...`` ile ``docs/...``'u
    karıştıran parametrize listesinin öğesi) denetlenmeden aynen döner.

``kanit_cikti(yol)``
    Kanıt dizinine YAZILAN çıktı için: yolun ÜST dizinine aynı kural uygulanır.

Bekçi: ``tests/test_kanit_atlama_kapisi.py`` — (a) geliştirme ağacında
statik olarak bilinen her kanıt yolunun var olduğunu, (b) test kodunda
docs/ kanıtını bu kapı DIŞINDA okuyan yer kalmadığını
(``tests/support/kanit_tarayici.py``), (c) kapıdan geçen okuma sayısının
düşmediğini ölçer.
"""
from __future__ import annotations

import os
import pathlib
import sys
from typing import TypeVar, Union

import pytest

#: Depo kökü (bu dosya ``tests/support/kanit.py``).
KOK = pathlib.Path(__file__).resolve().parents[2]

#: Yayın dalından ÇIKARILAN dizinler — ``packaging/yayin_dali_uret.sh``
#: içindeki ``HARIC`` varsayılanıyla aynı küme (bekçi ikisini karşılaştırır).
HARIC = ('docs/scofield', 'docs/arastirma', 'docs/tasarim')

#: Geliştirme ağacı ölçütü: bu dizin VARSA kapı hiçbir koşulda atlamaz.
GELISTIRME_ISARETI = 'docs/scofield'

#: ``1`` iken eksik kanıt atlama değil HATA olur.
ZORUNLU_DEGISKENI = 'HRMA_KANIT_ZORUNLU'

#: Atlama gerekçesinin sabit başı — junit/CI tarafında bu önekle ayrılabilir.
GEREKCE_ONEKI = 'kanıt yok: '
GEREKCE_KALIBI = (GEREKCE_ONEKI + "{yol} — yayın dalı docs'suz üretilir "
                  "(docs/ yayımlanmaz); bu düğüm geliştirme ağacında koşar")

_Y = TypeVar('_Y', str, os.PathLike)


def _tam_yol(yol: Union[str, os.PathLike], kok: pathlib.Path) -> pathlib.Path:
    p = pathlib.Path(os.fspath(yol))
    return p if p.is_absolute() else kok / p


def _bagil(tam: pathlib.Path, kok: pathlib.Path):
    """``tam``'ın depo-göreli POSIX yazımı; kanıt dizinleri DIŞINDAYSA None.

    Önce SÖZCÜKSEL (``abspath``), olmazsa GERÇEK yol (``realpath``) ile
    denenir: kanıt dizini sembolik bağ ise ilki, depo kökü bağlı bir yoldan
    (ör. macOS ``/tmp`` -> ``/private/tmp``) kurulmuşsa ikincisi tutar.
    """
    for t, k in ((os.path.abspath(tam), os.path.abspath(kok)),
                 (os.path.realpath(tam), os.path.realpath(kok))):
        try:
            bagil = pathlib.Path(t).relative_to(k).as_posix()
        except ValueError:
            continue
        if any(bagil == h or bagil.startswith(h + '/') for h in HARIC):
            return bagil
    return None


def kanit_yolu(bagil: str) -> pathlib.Path:
    """Depo-göreli kanıt yolunu çözer (G/Ç YOK, atlama YOK)."""
    if pathlib.PurePosixPath(bagil).is_absolute():
        raise ValueError('kanit_yolu depo-göreli yol ister: %s' % bagil)
    tam = KOK / bagil
    if _bagil(tam, KOK) is None:
        raise ValueError('kanit_yolu yalnız %s altındaki yollar içindir: %s'
                         % (', '.join(HARIC), bagil))
    return tam


def gelistirme_agaci(kok: pathlib.Path = None) -> bool:
    """``docs/scofield`` VAR mı — varsa kapı asla atlamaz."""
    return ((kok or KOK) / GELISTIRME_ISARETI).is_dir()


def _ithal_aninda() -> bool:
    """Çağrı bir test modülü İTHAL edilirken mi yapılıyor?

    Yığında ``tests/`` altındaki bir dosyanın modül gövdesi (``<module>``)
    varsa evet. Sınıf gövdesi de ithal anında koşar ve yığında o modülün
    gövdesinin altında durur, dolayısıyla aynı yoldan yakalanır.
    """
    testler = os.path.realpath(str(KOK / 'tests')) + os.sep
    cerceve = sys._getframe(2)
    while cerceve is not None:
        kod = cerceve.f_code
        if (kod.co_name == '<module>'
                and os.path.realpath(kod.co_filename).startswith(testler)):
            return True
        cerceve = cerceve.f_back
    return False


def _karar(yol, kok: pathlib.Path, ortam) -> str:
    """Yan etkisiz karar (bekçi bunu doğrudan sınar).

    'kapsam_disi' (docs/ kanıt dizinleri dışında; denetlenmez) | 'var' |
    'hata' (HRMA_KANIT_ZORUNLU=1) | 'gelistirme' (docs/scofield VAR: atlanmaz) |
    'atla' (docs'suz ağaç).
    """
    tam = _tam_yol(yol, kok)
    if _bagil(tam, kok) is None:
        return 'kapsam_disi'
    if tam.exists():
        return 'var'
    if ortam.get(ZORUNLU_DEGISKENI) == '1':
        return 'hata'
    if gelistirme_agaci(kok):
        return 'gelistirme'
    return 'atla'


def kanit_gerekli(yol: _Y) -> _Y:
    """Okumadan hemen önce: kanıt yoksa kurala göre atla/hata; ``yol``'u AYNEN döndür.

    Kanıt dizinleri dışındaki bir yol (ör. ``hrma/...`` ile ``docs/...``'u
    karıştıran bir parametrize listesinin öğesi) denetlenmeden aynen döner.
    """
    karar = _karar(yol, KOK, os.environ)
    if karar in ('kapsam_disi', 'var', 'gelistirme'):
        return yol
    bagil = _bagil(_tam_yol(yol, KOK), KOK)
    if karar == 'hata':
        pytest.fail('%s=1 ama kanıt eksik: %s — atlanmaz, HATA verilir'
                    % (ZORUNLU_DEGISKENI, bagil), pytrace=False)
    pytest.skip(GEREKCE_KALIBI.format(yol=bagil),
                allow_module_level=_ithal_aninda())


def kanit_cikti(yol: _Y) -> _Y:
    """Kanıt dizinine YAZILACAK çıktı: ÜST dizini ``kanit_gerekli`` kuralıyla ister.

    Bazı bekçiler ölçüm betiğinin çıktısını kanıt dizinine yazar; çıktının
    kendisi koşumdan önce yoktur, dolayısıyla ``kanit_gerekli`` ile
    sorulamaz (``HRMA_KANIT_ZORUNLU=1`` onu haklı olarak HATA sayardı).
    Sorulan, yazılacağı dizindir. ``yol`` AYNEN döner.
    """
    ust = _tam_yol(yol, KOK).parent
    karar = _karar(ust, KOK, os.environ)
    if karar in ('kapsam_disi', 'var', 'gelistirme'):
        return yol
    bagil = _bagil(ust, KOK)
    if karar == 'hata':
        pytest.fail('%s=1 ama çıktı dizini eksik: %s — atlanmaz, HATA verilir'
                    % (ZORUNLU_DEGISKENI, bagil), pytrace=False)
    pytest.skip(GEREKCE_KALIBI.format(yol=bagil),
                allow_module_level=_ithal_aninda())
