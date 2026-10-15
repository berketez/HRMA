#!/usr/bin/env python3
"""Kampanya sabit-çıktı defterinin TEK okuyucusu — fail-closed.

Neden ayrı bir modül
--------------------
``kusur_teyit.py``, ``kusur_partileri.py`` ve ``sabit_tarayici.py`` üçü de
aynı defteri okuyor ve üçü de varsayılan yolu kendi dosyasında ayrı ayrı
tanımlıyordu::

    VARSAYILAN_RAPOR = os.path.expanduser(
        '~/HRMA-kurtarma/takim-raporlari/sabit-bulgular.json')

Bu yol DEPO DIŞINDAYDI ve 27 Ağustos 2026'da ölçüldüğünde dizinin kendisi
yoktu (``ls ~/HRMA-kurtarma`` → *No such file or directory*). Yani 138
kusurun kapanış defteri yeniden ölçülemiyordu: üç aracın da girdisi
kaybolmuştu (P10B4-10). Aynı sabitin üç kopyası olması, düzeltmenin de üç
yerde yapılmasını gerektiriyordu; bu modül o sabiti tek kaynağa indirir.

Fail-closed sözleşmesi (P10B4-12)
---------------------------------
``sabit_tarayici.bilenen_yollar()`` defter yoksa sessizce ``set(), set()``
döndürüyordu; ardından ``main()`` "Takım raporunda GEÇMEYEN sabit yaprak: N"
satırını sanki karşılaştırma yapılmış gibi basıyor, çıkış kodu 0 (temiz)
oluyordu. Referansı kaybolmuş bir bekçinin vermesi gereken hüküm
"temiz" değil "ÖLÇEMEDİM"dir. Bu modüldeki okuyucular dosya yoksa ya da
biçim tanınmıyorsa ``DefterYok`` / ``DefterBozuk`` yükseltir; sessiz boş
küme YOKTUR.

Defterin kapsam sınırı
----------------------
Depo içindeki defter (``docs/dev/sabit_bulgular.json``) 1 Ağustos 2026
üretimi ``docs/dev/kusur_partileri.json`` türevinden yeniden kuruldu.
Parti aracı yalnız ``sinif == 'KUSUR'`` kayıtlarını taşıdığı için MEŞRU
sınıfı kurtarılamadı. Bu bir ölçüm değil KAPSAM SINIRIDIR ve defterin
künyesinde ``mesru_kurtarilamadi`` bayrağıyla yazılıdır; ``kapsam_beyani()``
onu her koşumda ekrana basar ki "meşru 0" ile "meşru ölçüldü ve 0 çıktı"
birbirine karışmasın.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any, Dict, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Defterin depo İÇİNDEKİ tek yolu. Üç araç da buradan okur.
VARSAYILAN_DEFTER = str(ROOT / 'docs' / 'dev' / 'sabit_bulgular.json')

#: Kaybolan depo dışı yol — yalnız hata metninde anılır ki eski koşum
#: kayıtlarını okuyan biri neyin değiştiğini anlasın.
ESKI_DEPO_DISI_YOL = '~/HRMA-kurtarma/takim-raporlari/sabit-bulgular.json'


class DefterHatasi(Exception):
    """Defter okunamadı — ölçüm YAPILAMAZ (fail-closed)."""


class DefterYok(DefterHatasi):
    pass


class DefterBozuk(DefterHatasi):
    pass


def defteri_yukle(yol: str = VARSAYILAN_DEFTER
                  ) -> Tuple[List[dict], Dict[str, Any]]:
    """Defteri oku. Döner: (gruplar, künye).

    İki biçim kabul edilir:

    * ``[{'grup': ..., 'kalemler': [...]}, ...]`` — özgün takım raporu
      biçimi (künye boş döner),
    * ``{'_kunye': {...}, 'gruplar': [...]}`` — depo içi yeniden kurulmuş
      defter.

    Dosya yoksa ``DefterYok``, biçim tanınmıyorsa ``DefterBozuk`` yükselir.
    Sessiz boş küme YOKTUR: bu fonksiyonun sessizce boş dönmesi, aracı
    "hiçbir şey bilinmiyor" moduna düşüren fail-open kusurunun ta kendisiydi.
    """
    if not os.path.exists(yol):
        raise DefterYok(
            f'Kampanya defteri bulunamadı: {yol}\n'
            f'  Defter olmadan "yeni sabit" / "kusur kapandı" hükmü '
            f'VERİLEMEZ (fail-closed).\n'
            f'  Not: eski varsayılan yol depo dışındaydı '
            f'({ESKI_DEPO_DISI_YOL}) ve kayboldu; defter artık depo '
            f'içindedir: {VARSAYILAN_DEFTER}')
    try:
        with open(yol, encoding='utf-8') as f:
            ham = json.load(f)
    except (OSError, ValueError) as hata:
        raise DefterBozuk(f'Kampanya defteri okunamadı: {yol} ({hata})')

    if isinstance(ham, list):
        gruplar, kunye = ham, {}
    elif isinstance(ham, dict) and isinstance(ham.get('gruplar'), list):
        gruplar, kunye = ham['gruplar'], dict(ham.get('_kunye') or {})
    else:
        raise DefterBozuk(
            f'Kampanya defterinin biçimi tanınmadı: {yol}\n'
            f'  Beklenen: grup listesi ya da {{"_kunye":..., "gruplar":[...]}}')

    if not gruplar:
        raise DefterBozuk(f'Kampanya defteri boş: {yol}')
    for grup in gruplar:
        if not isinstance(grup, dict) or 'kalemler' not in grup:
            raise DefterBozuk(
                f'Kampanya defterinde "kalemler" alanı olmayan grup var: {yol}')
    return gruplar, kunye


def kusurlari_yukle(yol: str = VARSAYILAN_DEFTER) -> List[dict]:
    """KUSUR sınıfındaki kalemler, ``_grup`` alanı eklenmiş olarak."""
    gruplar, _kunye = defteri_yukle(yol)
    kusurlar = []
    for grup in gruplar:
        for kalem in grup.get('kalemler', []):
            if kalem.get('sinif') != 'KUSUR':
                continue
            kayit = dict(kalem)
            kayit['_grup'] = grup.get('grup', '')
            kusurlar.append(kayit)
    return kusurlar


def bilinen_yollar(yol: str = VARSAYILAN_DEFTER
                   ) -> Tuple[set, set, Dict[str, Any]]:
    """Defterdeki JSON yaprağı yolları. Döner: (kusur, meşru, künye).

    Dosya yoksa YÜKSELTİR — eski sürüm burada ``set(), set()`` döndürüyordu
    ve tarayıcı her sabiti "YENİ" sayıyordu (P10B4-12).
    """
    gruplar, kunye = defteri_yukle(yol)
    kusur, mesru = set(), set()
    for grup in gruplar:
        for k in grup.get('kalemler', []):
            hedef = k.get('yol') or ''
            if not hedef.startswith('.'):
                continue
            (kusur if k.get('sinif') == 'KUSUR' else mesru).add(hedef)
    return kusur, mesru, kunye


def kapsam_beyani(kunye: Dict[str, Any]) -> str:
    """Defterin kapsam sınırını tek satırda beyan eder ("" ise sınır yok)."""
    if not kunye:
        return ''
    parcalar = []
    if kunye.get('orijinal_kaynak_durumu'):
        parcalar.append(f"defter kaynağı: {kunye['orijinal_kaynak_durumu']}")
    if kunye.get('mesru_kurtarilamadi'):
        parcalar.append(
            kunye.get('kapsam_siniri')
            or 'MEŞRU sınıfı defterde YOK — "bilinen meşru 0" bir ölçüm '
               'değil kapsam sınırıdır.')
    return ' | '.join(parcalar)
