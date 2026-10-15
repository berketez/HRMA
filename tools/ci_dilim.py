#!/usr/bin/env python3
"""CI test dilimleme — pytest eklentisi + junit birleştirici (v3.0.0, 15 Eki 2026).

Neden
-----
``tests.yml``in ``pytest`` işi tek süreçte koşuyordu ve takım büyüdükçe
90 dakikalık iş sınırına sığmaz oldu. ÖLÇÜLDÜ (15 Eki 2026): v3.0 ağacının
iki push koşumu (38753576200, 38757753775) ``Test paketi`` adımında
zaman aşımına düşüp İPTAL edildi; aynı takım yerelde 26 522 test, junit
süreleri toplamı 141,7 dk. İş matrise bölündü: her dilim AYNI
``pytest tests/`` komutunu koşar, bu eklenti toplanan kümeyi DOSYA bazında
N dilime ayırır ve kendi dilimi dışındakileri SEÇMEZ (deselect — atlama
değil; seçilmeyen test junit raporuna girmez, atlama bütçesini etkilemez).

Dosya bazında bölünür ki modül düzeyi fikstürler dilimler arasında
tekrarlanmasın. Dengeleme ölçülen dosya sürelerinden yapılır
(``ci_dilim_agirliklari.json``); listede olmayan yeni dosya, test sayısı x
ölçülen ortalama test süresi ağırlığını alır. Atama deterministiktir: her
dilim aynı kümeyi toplar ve aynı bölümlemeyi hesaplar.

Etkinleştirme: ``PYTEST_ADDOPTS="-p tools.ci_dilim"`` + ``HRMA_CI_DILIM=k/N``.
``HRMA_CI_DILIM`` yoksa eklenti hiçbir şey yapmaz.

Birleştirme (``pytest-birlesik`` işi)::

    python3 tools/ci_dilim.py birlestir --dizin raporlar --cikti pytest-report.xml

Dilim sayısının TEK kaynağı iş akışının matris listesidir; her dilim onu
(``strategy.job-total``) künyesine yazar, birleştirici oradan okur.

FAIL-CLOSED: dilim künyelerinden biri eksikse, dilimler aynı kümeyi
toplamadıysa ya da seçilenlerin toplamı toplananı TUTMUYORSA birleştirme
düşer — kaybolan bir dilim "yeşil" sayılamaz.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

AGIRLIK_DOSYASI = pathlib.Path(__file__).with_name('ci_dilim_agirliklari.json')
KUNYE_ADI = 'ci-dilim-kunye.json'
ORTAM_DEGISKENI = 'HRMA_CI_DILIM'


def dilim_coz(deger: str) -> Tuple[int, int]:
    """``'k/N'`` → ``(k, N)``; 1 <= k <= N, N >= 1. Bozuksa ValueError."""
    try:
        k_metin, n_metin = str(deger).strip().split('/')
        k, n = int(k_metin), int(n_metin)
    except Exception as hata:
        raise ValueError('%s=%r "k/N" biçiminde değil' % (ORTAM_DEGISKENI, deger)) from hata
    if n < 1 or not 1 <= k <= n:
        raise ValueError('%s=%r: 1 <= k <= N olmalı' % (ORTAM_DEGISKENI, deger))
    return k, n


def agirliklari_oku(yol: pathlib.Path = AGIRLIK_DOSYASI) -> Tuple[Dict[str, float], float]:
    """(dosya → saniye, test başına ortalama saniye). Dosya yoksa ({}, 1.0)."""
    try:
        veri = json.loads(yol.read_text(encoding='utf-8'))
        dosyalar = {str(k): float(v) for k, v in veri['dosyalar'].items()}
        ortalama = float(veri['_kunye']['ortalama_test_s'])
    except Exception:
        return {}, 1.0
    return dosyalar, ortalama


def dilimle(sayilar: Dict[str, int], n: int,
            agirliklar: Dict[str, float], ortalama_test_s: float) -> Dict[str, int]:
    """Dosya → dilim (1..n). Açgözlü: en ağır dosya en hafif dilime.

    Sıra ve eşitlik bozma tamamen deterministiktir (ağırlık azalan, sonra
    yol; eşit yükte küçük dilim numarası).
    """
    def agirlik(dosya: str) -> float:
        if dosya in agirliklar:
            return agirliklar[dosya]
        return sayilar[dosya] * ortalama_test_s

    yuk = [0.0] * n
    atama: Dict[str, int] = {}
    for dosya in sorted(sayilar, key=lambda d: (-agirlik(d), d)):
        j = min(range(n), key=lambda i: (yuk[i], i))
        atama[dosya] = j + 1
        yuk[j] += agirlik(dosya)
    return atama


# ---------------------------------------------------------------------------
# pytest eklentisi
# ---------------------------------------------------------------------------
try:
    import pytest
except ImportError:  # birleştirici pytest'siz de koşar
    pytest = None

EKLENTI_SECENEGI = '-p tools.ci_dilim'

if pytest is not None:
    def pytest_configure(config):
        # Dilim bilgisi YALNIZ bu sürece aittir. Takımın bazı testleri alt
        # süreçte pytest koşar (ör. atlama bütçesi bekçileri); ortam miras
        # kalsaydı iç koşum da dilimlenir ya da `tools` ithal edilemeyen
        # geçici dizinde eklenti yüklenemeyip çökerdi.
        config._hrma_ci_dilim = os.environ.pop(ORTAM_DEGISKENI, '').strip()
        ek = os.environ.get('PYTEST_ADDOPTS')
        if ek is not None and EKLENTI_SECENEGI in ek:
            kalan = ' '.join(ek.replace(EKLENTI_SECENEGI, ' ').split())
            if kalan:
                os.environ['PYTEST_ADDOPTS'] = kalan
            else:
                os.environ.pop('PYTEST_ADDOPTS', None)

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(session, config, items):
        deger = getattr(config, '_hrma_ci_dilim', '')
        if not deger:
            return
        try:
            k, n = dilim_coz(deger)
        except ValueError as hata:
            raise pytest.UsageError(str(hata))
        sayilar = collections.Counter(it.nodeid.split('::')[0] for it in items)
        agirliklar, ortalama = agirliklari_oku()
        atama = dilimle(dict(sayilar), n, agirliklar, ortalama)
        secilen, birakilan = [], []
        for it in items:
            (secilen if atama[it.nodeid.split('::')[0]] == k else birakilan).append(it)
        toplanan = len(items)
        if birakilan:
            config.hook.pytest_deselected(items=birakilan)
        items[:] = secilen
        kunye = {
            'dilim': k, 'dilim_sayisi': n, 'toplanan': toplanan,
            'secilen': len(secilen),
            'dosya_sayisi': sum(1 for d in atama.values() if d == k),
            'tahmini_yuk_s': round(sum(
                agirliklar.get(d, sayilar[d] * ortalama)
                for d, j in atama.items() if j == k), 1),
        }
        pathlib.Path(KUNYE_ADI).write_text(
            json.dumps(kunye, ensure_ascii=False) + '\n', encoding='utf-8')
        sys.stderr.write('CI dilimi %d/%d: %d/%d test, %d dosya, tahmini %.0f s\n'
                         % (k, n, len(secilen), toplanan, kunye['dosya_sayisi'],
                            kunye['tahmini_yuk_s']))


# ---------------------------------------------------------------------------
# Birleştirici
# ---------------------------------------------------------------------------
def birlestir(dizin: pathlib.Path, cikti: pathlib.Path,
              dilim_sayisi: Optional[int] = None) -> List[str]:
    """Dilim raporlarını tek junit'e birleştirir; hata listesi döner.

    ``dilim_sayisi`` verilmezse künyelerin ORTAK ``dilim_sayisi`` alanından
    okunur; künyeler farklı sayı söylüyorsa ya da hiç künye yoksa hata.
    """
    hata: List[str] = []
    kunyeler = []
    for yol in sorted(dizin.rglob(KUNYE_ADI)):
        try:
            kunyeler.append(json.loads(yol.read_text(encoding='utf-8')))
        except Exception as exc:
            hata.append('%s okunamadı (%s)' % (yol, exc))
    if dilim_sayisi is None:
        sayilar = {int(k.get('dilim_sayisi', 0)) for k in kunyeler}
        if len(sayilar) != 1 or not next(iter(sayilar), 0):
            hata.append('dilim sayısı künyelerden okunamadı (%s; %d künye)'
                        % (sorted(sayilar), len(kunyeler)))
            return hata
        dilim_sayisi = next(iter(sayilar))
    dilimler = sorted(int(k.get('dilim', 0)) for k in kunyeler)
    if dilimler != list(range(1, dilim_sayisi + 1)):
        hata.append('dilim künyeleri %s, beklenen 1..%d — bir dilim raporsuz '
                    'kaldı ya da iki kez sayıldı' % (dilimler, dilim_sayisi))
    toplananlar = {int(k.get('toplanan', -1)) for k in kunyeler}
    if len(toplananlar) != 1:
        hata.append('dilimler AYNI kümeyi toplamamış: %s' % sorted(toplananlar))
    secilen = sum(int(k.get('secilen', 0)) for k in kunyeler)
    if len(toplananlar) == 1 and secilen != next(iter(toplananlar)):
        hata.append('dilimlerin seçtiği %d test, toplanan %d — bölümleme '
                    'kümeyi örtmüyor' % (secilen, next(iter(toplananlar))))

    raporlar = sorted(p for p in dizin.rglob('*.xml'))
    if len(raporlar) != dilim_sayisi:
        hata.append('%d junit raporu bulundu, beklenen %d' % (len(raporlar), dilim_sayisi))

    kok = ET.Element('testsuites')
    suite = ET.SubElement(kok, 'testsuite', name='pytest')
    gorulen = set()
    tekrar = 0
    sure = 0.0
    for yol in raporlar:
        try:
            r = ET.parse(yol).getroot()
        except ET.ParseError as exc:
            hata.append('%s ayrıştırılamadı (%s)' % (yol, exc))
            continue
        s = r if r.tag == 'testsuite' else r.find('testsuite')
        if s is None:
            hata.append('%s içinde testsuite yok' % yol)
            continue
        sure = max(sure, float(s.get('time') or 0))
        for tc in s.findall('testcase'):
            # Toplama düzeyi kayıtları (modül atlaması, toplama hatası) her
            # dilimde AYNEN tekrar eder — kimliği aynı olan ikinci kayıt
            # sayılmaz. Gerçek test yalnız tek dilimde koşar.
            anahtar = (tc.get('classname'), tc.get('name'))
            if anahtar in gorulen:
                tekrar += 1
                continue
            gorulen.add(anahtar)
            suite.append(tc)
    testler = suite.findall('testcase')
    suite.set('tests', str(len(testler)))
    suite.set('failures', str(sum(1 for t in testler if t.find('failure') is not None)))
    suite.set('errors', str(sum(1 for t in testler if t.find('error') is not None)))
    suite.set('skipped', str(sum(1 for t in testler if t.find('skipped') is not None)))
    suite.set('time', '%.3f' % sure)
    ET.ElementTree(kok).write(cikti, encoding='utf-8', xml_declaration=True)
    print('birleşik rapor: %d dilim, %d test (toplama düzeyi tekrarı %d atıldı), '
          'en uzun dilim %.0f s -> %s' % (len(raporlar), len(testler), tekrar, sure, cikti))
    return hata


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    alt = ap.add_subparsers(dest='komut', required=True)
    b = alt.add_parser('birlestir', help='dilim junit raporlarını birleştirir')
    b.add_argument('--dizin', required=True)
    b.add_argument('--dilim-sayisi', type=int, default=None,
                   help='verilmezse künyelerden okunur')
    b.add_argument('--cikti', default='pytest-report.xml')
    a = ap.parse_args(argv)
    hata = birlestir(pathlib.Path(a.dizin), pathlib.Path(a.cikti), a.dilim_sayisi)
    if hata:
        sys.stderr.write('CI dilim birleştirme KAPALI: ' + '; '.join(hata) + '\n')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
