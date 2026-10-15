#!/usr/bin/env python3
"""Atlama kapısı — junit raporundan atlama bütçesini MEKANİK olarak uygular.

Neden ayrı dosya
----------------
``.github/workflows/tests.yml`` içindeki ``pytest`` işi 27 Ağustos 2026'da
ölçülmüş bir atlama bütçesi uyguluyor. ``release.yml``'in aynı adı taşıyan
adımı ise o bütçenin ESKİ, kapısız sürümünün bayt kopyasıydı (ÖH defter
OH-B3-04): ne eşik vardı ne de junit'in ``type`` alanı olmayan MODÜL DÜZEYİ
atlamaları sayılıyordu. ÖLÇÜLDÜ (D17/altyapi ``once.json``):

    300 gerçek atlama          -> release.yml adımı çıkış kodu 0 (YEŞİL)
    12 modül toplama düzeyinde -> çıkış kodu 0 (YEŞİL)
    toplama çöktü (3 test)     -> çıkış kodu 0 (YEŞİL)

Yani yayın kapısı, shapely/CoolProp gibi bir bağımlılık yayın ortamında
düşüp 96 bekçi sessizce kaybolduğunda da YEŞİL çıkıyordu. Bu dosya kapının
gövdesini iş akışı YAML'inden çıkarır: sayı tek yerde yazılır, iki iş akışı
aynı davranışı çağırır ve davranış yerelde de koşturulabilir (bekçi
``tests/test_d17_altyapi_a1.py`` bunu sentetik junit'e karşı ölçer).

Kullanım
--------
    python3 tools/atlama_kapisi.py pytest-report.xml
    python3 tools/atlama_kapisi.py pytest-report.xml --butce 76
    python3 tools/atlama_kapisi.py pytest-report.xml --tests-dizini tests

Çıkış kodu 0 = kapı açık; 1 = kapı kapalı (gerekçe stderr'e yazılır).

Kanıt atlaması — AYRI SINIF (ÖH D37 / YB-15)
--------------------------------------------
Yayın dalı ``docs/scofield``, ``docs/arastirma``, ``docs/tasarim``
ÇIKARILARAK üretilir; o ağaçta ``tests/support/kanit.py`` kapısı eksik
kanıtı ``GEREKCE_ONEKI`` ("kanıt yok: ") önekli gerekçeyle atlar. D36
kanit-atlama raporu: ~638 test düzeyi (630 ölçülen + 8 beklenen); toplama
düzeyinde 3 modül (D37 ``--collect-only`` ile yeniden ölçüldü). Bu atlamalar
bütçeye sayılsaydı yayın dalı CI'ı bütçe VE "modül düzeyi sıfır" kuralıyla
KIRMIZI olurdu. Kural:

1. "kanıt yok: " önekli atlama bütçeye (``ATLAMA_BUTCESI``) SAYILMAZ;
2. modül düzeyinde de olsa "toplama düzeyi sıfır" kuralına takılmaz;
3. AMA yalnız ağaçta ``docs/scofield`` YOKKEN meşrudur — varsa TEK bir
   kanıt atlaması bile HATA (geliştirme ağacında kanıt kapısı atlamaz;
   atlama görüldüyse kanıt sessizce kaybolmuştur);
4. rapor ayrı sayı basar: ``kanit_atlamasi=N (docs'suz agac: evet|hayir)``;
5. önek ve geliştirme işareti TEK kaynaktan, ``tests/support/kanit.py``den
   AST ile okunur (ithal değil); okunamazsa kapı KAPANIR.
"""

from __future__ import annotations

import argparse
import ast
import os
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

#: TEK KAYNAK — 27 Ağustos 2026 ölçümü (tam süit, CI benzetimi, HEAD baa9d9e:
#: 9341 passed · 75 skipped · 81 xfailed; + bu paketin eklediği 1 bekçi = 76).
#: Dökümün tamamı `.github/workflows/tests.yml` içindeki gerekçe bloğundadır.
#: Değiştirirken ölçüm komutunu, tarihi ve dökümü BİRLİKTE güncelleyin.
ATLAMA_BUTCESI = 76

#: Toplama çöktüğünde "0 test, 0 atlama" ile yeşil kalmayı engelleyen taban.
#: Ölçülen toplama 9497; taban %94,8'ine kondu.
TOPLANAN_TABANI = 9000

#: ``importorskip`` hedefi bu köklerden biriyse "isteğe bağlı bağımlılık"
#: gerekçesi geçersizdir: modül DEPONUN KENDİSİDİR (P13B1-05 / P14 §3.2-e).
DEPO_KOKLERI = ('hrma', 'app', 'tools', 'data')

#: Kanıt atlaması sözleşmesinin kaynağı (depo köküne göre). Önek
#: (``GEREKCE_ONEKI``) ve geliştirme ağacı işareti (``GELISTIRME_ISARETI``)
#: BURADA YAZILMAZ — o dosyadan AST ile okunur (ÖH D37 / YB-15).
KANIT_KAYNAGI = 'tests/support/kanit.py'


def _ust_duzey_sabitler(agac):
    """Modül gövdesindeki ``AD = <literal>`` atamaları (ithal etmeden)."""
    sabitler = {}
    for dugum in agac.body:
        if (isinstance(dugum, ast.Assign) and len(dugum.targets) == 1
                and isinstance(dugum.targets[0], ast.Name)):
            try:
                sabitler[dugum.targets[0].id] = ast.literal_eval(dugum.value)
            except Exception:                     # noqa: BLE001 - literal değil
                pass
    return sabitler


def kanit_sozlesmesi(kok='.'):
    """``(önek, geliştirme_işareti)`` — ``KANIT_KAYNAGI``dan AST ile okunur.

    İTHAL DEĞİL: ``kanit.py`` ``pytest`` ithal eder ve depo kökünü kendi
    konumundan hesaplar; kapı pytest'siz de koşabilmeli ve iş akışı YAML
    gövdesiyle AYNI yoldan okumalı. FAIL-CLOSED: dosya yok, ayrıştırılamıyor
    ya da iki addan biri eksik/boşsa ``ValueError`` — önek bilinmeden kanıt
    atlaması ayrılamaz, ayrılamayan atlama da ne bütçeye ne muafiyete
    yazılabilir.
    """
    yol = pathlib.Path(kok) / KANIT_KAYNAGI
    if not yol.is_file():
        raise ValueError(f'{yol} yok — kanit atlamasi oneki OKUNAMIYOR, '
                         'kanit sinifi ayrilamaz')
    try:
        agac = ast.parse(yol.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise ValueError(f'{yol} ayristirilamadi ({exc}) — kanit atlamasi '
                         'oneki OKUNAMIYOR') from exc
    sabitler = _ust_duzey_sabitler(agac)
    sonuc = []
    for ad in ('GEREKCE_ONEKI', 'GELISTIRME_ISARETI'):
        deger = sabitler.get(ad)
        if not isinstance(deger, str) or not deger.strip():
            raise ValueError(f'{yol} icinde {ad} yok ya da bos — kanit '
                             'sozlesmesi kirilmis, kanit sinifi ayrilamaz')
        sonuc.append(deger)
    return tuple(sonuc)


def kanit_atlamasi_mi(tip, mesaj_alani, metin, onek):
    """Bir ``<skipped>`` düğümü "kanıt yok" sınıfından mı?

    ÖLÇÜLDÜ (pytest 8.3.4, 24 Eylül 2026; gerçek ``kanit.py`` ile kurulmuş
    docs'suz sentetik ağaç):

    * gövde içi ``kanit_gerekli`` -> ``type='pytest.skip'``, ``message``
      ÖNEKLE BAŞLAR;
    * modül düzeyi (ithal anında ``kanit_gerekli``; ``skipif`` koşulunda
      çağrılan da buraya düşer) -> ``type`` YOK, ``message='collection
      skipped'``, gerekçe düğüm METNİNDE:
      ``('<yol>', <satır>, "Skipped: kanıt yok: ...")``.

    Önek gerekçenin BAŞINDA aranır; içinde geçmesi yetmez. xfail hiçbir
    zaman bu sınıftan değildir.
    """
    if tip == 'pytest.skip':
        return mesaj_alani.startswith(onek)
    if tip is None:
        return re.search(r""", \d+, ['"]Skipped: """ + re.escape(onek),
                         metin) is not None
    return False


def atlamalari_ayikla(rapor_yolu, kanit_oneki):
    """junit raporundan ``(atlanan, modül_düzeyi, kanıt, toplanan)`` çıkarır.

    ATLAMA SÜZGECİ — ölçüldü (sentetik junit, pytest 8.4): gövde içi skip ve
    ``skipif`` -> ``type='pytest.skip'``; xfail -> ``type='pytest.xfail'``
    (SAYILMAZ); MODÜL DÜZEYİ atlama -> ``type`` alanı YOK. Üçüncüsü
    sayılmazsa bir test dosyasının TAMAMI bütçeye görünmeden kaybolur
    (P13B1-06 / K8).

    ``kanit_oneki`` ile başlayan atlamalar (``kanit_atlamasi_mi``) ``atlanan``
    ve ``modül_düzeyi`` listelerine GİRMEZ, ayrı ``kanıt`` listesine yazılır
    (ÖH D37 / YB-15). Önek zorunludur: boş önek her atlamayı kanıt sayardı.
    """
    if not isinstance(kanit_oneki, str) or not kanit_oneki.strip():
        raise ValueError('kanit_oneki bos — kanit sinifi ayrilamaz')
    root = ET.parse(rapor_yolu).getroot()
    suite = root if root.tag == 'testsuite' else root.find('testsuite')
    if suite is None:
        raise ValueError('junit raporunda <testsuite> yok')
    toplam = int(suite.get('tests', 0))
    atlanan, toplama_duzeyi, kanit = [], [], []
    for tc in suite.iter('testcase'):
        s = tc.find('skipped')
        if s is None:
            continue
        tip = s.get('type')
        if tip == 'pytest.xfail':
            continue
        mesaj = ((s.get('message') or '') + ' ' + (s.text or '')).strip()
        kayit = (f"{tc.get('classname')}::{tc.get('name')}", mesaj, tip)
        if kanit_atlamasi_mi(tip, s.get('message') or '', s.text or '',
                             kanit_oneki):
            kanit.append(kayit)
            continue
        atlanan.append(kayit)
        if tip is None:
            toplama_duzeyi.append(kayit)
    return atlanan, toplama_duzeyi, kanit, toplam


def _kanit_ozeti(kanit):
    """Kanıt atlamalarını dosya başına toplar (yüzlerce satır basmamak için)."""
    moduller, testler = [], {}
    for ad, _mesaj, tip in kanit:
        if tip is None:
            moduller.append(ad)
        else:
            dosya = ad.split('::', 1)[0]
            testler[dosya] = testler.get(dosya, 0) + 1
    satirlar = [f'  KANIT YOK (MODUL) {ad}' for ad in sorted(moduller)]
    satirlar += [f'  KANIT YOK {dosya}: {n} test'
                 for dosya, n in sorted(testler.items())]
    return satirlar


def depo_ici_importorskip(tests_dizini):
    """``tests/`` altında DEPO-İÇİ modüle bakan importorskip sitelerini sayar.

    Koşum sırasında GÖRÜNMEZ (modül yerindeyken atlama üretmez), modül
    kırıldığında bekçiyi kırmızı vermeden yok eder — bu yüzden dinamik sayım
    değil STATİK tarama gerekir.
    """
    kok = pathlib.Path(tests_dizini)
    if not kok.is_dir():
        raise FileNotFoundError(str(kok))
    bulunan = []
    for yol in sorted(kok.rglob('test_*.py')):
        try:
            agac = ast.parse(yol.read_text(encoding='utf-8'))
        except SyntaxError as exc:
            raise SyntaxError(f'{yol} ayristirilamadi ({exc})') from exc
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.Call)
                    and isinstance(dugum.func, ast.Attribute)
                    and dugum.func.attr == 'importorskip'
                    and dugum.args
                    and isinstance(dugum.args[0], ast.Constant)):
                hedef = str(dugum.args[0].value)
                if hedef.split('.')[0] in DEPO_KOKLERI:
                    bulunan.append(f'{yol}:{dugum.lineno} -> {hedef}')
    return bulunan


def kapi(rapor_yolu, butce=ATLAMA_BUTCESI, tests_dizini='tests',
         toplanan_tabani=TOPLANAN_TABANI, yaz=print, kok=None):
    """Kapıyı koşturur; hata gerekçelerinin listesini döndürür (boş = açık).

    FAIL-CLOSED: rapor yoksa, ``tests/`` yoksa, rapor ayrıştırılamazsa ya da
    kanıt sözleşmesi (``KANIT_KAYNAGI``) okunamazsa kapı KAPANIR —
    "ölçemedim" hâli yeşile sayılmaz.

    ``kok``: docs'suz ağaç ölçütünün ve ``KANIT_KAYNAGI``nın çözüldüğü depo
    kökü; verilmezse ``tests_dizini``nin (sözcüksel) üst dizini.
    """
    hata = []
    if not os.path.exists(rapor_yolu):
        return [f'{rapor_yolu} yok — test adimi raporu uretmeden dustu, '
                'atlama sayisi OLCULEMIYOR']
    if kok is None:
        kok = os.path.dirname(os.path.abspath(tests_dizini))
    try:
        onek, gelistirme_isareti = kanit_sozlesmesi(kok)
    except ValueError as exc:
        return [str(exc)]
    docssuz = not (pathlib.Path(kok) / gelistirme_isareti).is_dir()
    try:
        atlanan, toplama_duzeyi, kanit, toplam = atlamalari_ayikla(
            rapor_yolu, onek)
    except Exception as exc:                      # noqa: BLE001 - fail-closed
        return [f'{rapor_yolu} ayristirilamadi ({exc}) — atlama sayisi '
                'OLCULEMIYOR']

    yaz(f'toplanan={toplam} atlanan={len(atlanan)} '
        f'(toplama_duzeyi={len(toplama_duzeyi)}) butce={butce}')
    for ad, mesaj, tip in atlanan:
        yaz(f"  {'MODUL DUSTU' if tip is None else 'ATLANDI'} {ad} "
            f'-> {mesaj[:160]}')
    yaz(f"kanit_atlamasi={len(kanit)} "
        f"(docs'suz agac: {'evet' if docssuz else 'hayir'})")
    for satir in _kanit_ozeti(kanit):
        yaz(satir)

    try:
        depo_ici = depo_ici_importorskip(tests_dizini)
    except FileNotFoundError:
        return [f'{tests_dizini} dizini yok — depo-ici importorskip taramasi '
                'yapilamadi']
    except SyntaxError as exc:
        return [str(exc)]
    yaz(f'depo-ici importorskip = {len(depo_ici)} (olculdu: 0)')
    for satir in depo_ici:
        yaz(f'  DEPO-ICI IMPORTORSKIP {satir}')

    if len(atlanan) > butce:
        hata.append(f'{len(atlanan)} test atlandi, butce {butce} (yukaridaki '
                    'listeye bakin: yeni bir bagimlilik sessizce dusmus '
                    'olabilir)')
    if toplama_duzeyi:
        hata.append(f'{len(toplama_duzeyi)} MODUL toplama duzeyinde atlandi — '
                    'tek satir gorunur ama dosyanin BUTUN testleri '
                    'raporlanmadan kaybolur; sayiyla butcelenemez, sifir olmali')
    if kanit and not docssuz:
        hata.append(f'{len(kanit)} "kanit yok" atlamasi var ama agacta '
                    f'{gelistirme_isareti} VAR — gelistirme agacinda kanit '
                    'kapisi ATLAMAZ; atlama goruldu ise kanit sessizce '
                    'kaybolmustur (HRMA_KANIT_ZORUNLU sozlesmesi)')
    if toplam < toplanan_tabani:
        hata.append(f'yalnizca {toplam} test toplandi; 27 Agustos 2026 olcumu '
                    f'9497 idi (taban {toplanan_tabani}) — toplama kirilmis '
                    'olabilir')
    if depo_ici:
        hata.append(f'{len(depo_ici)} depo-ici importorskip sitesi var; modul '
                    'DEPONUN KENDISI oldugu icin "istege bagli bagimlilik" '
                    'gerekcesi gecersiz — duz ithale cevirin (P13B1-05)')
    return hata


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rapor', nargs='?', default='pytest-report.xml')
    ap.add_argument('--butce', type=int, default=ATLAMA_BUTCESI)
    ap.add_argument('--tests-dizini', default='tests')
    ns = ap.parse_args(argv)
    hata = kapi(ns.rapor, ns.butce, ns.tests_dizini)
    if hata:
        print('Atlama kapisi: ' + '; '.join(hata), file=sys.stderr)
        return 1
    print('Atlama kapisi: TAMAM')
    return 0


if __name__ == '__main__':
    sys.exit(main())
