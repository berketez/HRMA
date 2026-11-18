"""Kurulum paketine HRMA lisansını ve üçüncü taraf lisans bildirimlerini koyar.

Kullanım (derleme betiklerinden; ``set -e`` altında, hata derlemeyi durdurur):
    python3 packaging/lisans_paketle.py --kaynak <depo kökü> \
        --app <paket app/ dizini> --libs <paket libs/ dizini>

NEDEN (3.0.6, CI-SÜREÇ kalem 1, S1 lisans)
------------------------------------------
v3.0.5'in yayınlanan macOS paketi ölçüldü (``/Applications/HRMA.app``, köken
sha 0a138ff6a): ``Resources/app`` içinde ``LICENSE`` YOK; paket RocketCEA
1.2.1'i (GPLv3) taşıyor; ``cadquery-ocp-novtk`` tekerleği Open CASCADE
(LGPL-2.1 + istisna), FreeImage, LibRaw ve FreeType yerel kütüphanelerini
lisans dosyası OLMADAN taşıyor (kanıt:
``docs/scofield/raw/OH/V306/ci-surec/lisans_envanteri_v305_mac.json``).
Kaynak ağaç 3.0.6'dan itibaren GPL-3.0-or-later; GPL, programı alan herkese
lisansın bir kopyasının da verilmesini şart koşar (MIT de bildirimin
kopyalarla birlikte gitmesini isterdi).

Ne yapar
--------
1. ``<kaynak>/LICENSE`` -> ``<app>/LICENSE`` (GPLv3 metni değilse DURUR).
2. ``packaging/licenses/*`` -> ``<app>/licenses/`` (bildirim + metinler).
3. ``<libs>/*.dist-info`` taranır -> ``<app>/licenses/PYTHON_PACKAGES.txt``
   (dağıtım adı, sürüm, beyan edilen lisans, paket içindeki lisans dosyaları).

FAIL-CLOSED denetimler (biri tutmazsa çıkış kodu 1, paket ÜRETİLMEZ)
--------------------------------------------------------------------
- RocketCEA dist-info'su libs'te var ve kendi lisans dosyasını taşıyor.
- Metaverisi kopyalayıcı-izinli (GPL/LGPL/AGPL/MPL/EPL/CDDL) görünen HER
  dağıtım ``THIRD_PARTY_NOTICES.txt`` içinde ``Distribution: <ad>`` satırıyla
  beyan edilmiş: yeni bir copyleft bağımlılık bildirimsiz pakete giremez.
- Bildirimin ``licenses/<dosya>`` diye andığı her metin pakette var.
- V307/FS-HARİTA: ``hrma/static/map/*_manifest.json`` içinde üst düzeyde
  ``license`` beyan eden her ÜÇÜNCÜ TARAF VERİ manifestinin işaret ettiği
  veri dosyası bildirimde ``Data: hrma/static/map/<dosya>`` satırıyla beyan
  edilmiş; bildirimin andığı her ``Data:`` yolu kaynak ağaçta var. Atıf
  isteyen (CC BY) yeni bir veri dosyası bildirimsiz pakete giremez.
"""

import argparse
import pathlib
import re
import shutil
import sys

PAKETLEME = pathlib.Path(__file__).resolve().parent
LISANS_KAYNAK_DIZINI = PAKETLEME / 'licenses'
BILDIRIM_ADI = 'THIRD_PARTY_NOTICES.txt'
DAGITIM_LISTESI_ADI = 'PYTHON_PACKAGES.txt'

#: Bildirimin ZORUNLU olarak lisans dosyasıyla taşıdığı dağıtımlar
#: (normalize ad). RocketCEA, paketin bütünüyle GPL dağıtılma nedenidir.
ZORUNLU_DAGITIMLAR = ('rocketcea',)

#: Metaveride kopyalayıcı-izinli aile göstergesi.
COPYLEFT = re.compile(
    r'\b(A?GPL|LGPL|GNU (Affero |Lesser |Library )?General Public|MPL|'
    r'Mozilla Public|EPL|Eclipse Public|CDDL)\b', re.I)
LISANS_DOSYASI = re.compile(r'^(LICEN[CS]E|COPYING|NOTICE)', re.I)


class LisansHatasi(Exception):
    pass


def normalize(ad):
    """PEP 503 dağıtım adı normalizasyonu (``Foo_Bar`` -> ``foo-bar``)."""
    return re.sub(r'[-_.]+', '-', ad or '').lower()


def metadata_oku(dist_info):
    yol = dist_info / 'METADATA'
    alanlar = {'Name': None, 'Version': None, 'License': None,
               'License-Expression': None, 'Classifier': []}
    if not yol.exists():
        return alanlar
    for satir in yol.read_text(encoding='utf-8', errors='replace').splitlines():
        if not satir.strip():
            break  # başlıklar bitti, gövde başladı
        if ':' not in satir or satir.startswith((' ', '\t')):
            continue
        anahtar, deger = satir.split(':', 1)
        deger = deger.strip()
        if anahtar == 'Classifier':
            if deger.startswith('License ::'):
                alanlar['Classifier'].append(deger)
        elif anahtar in alanlar and alanlar[anahtar] is None:
            alanlar[anahtar] = deger
    return alanlar


def lisans_ozeti(m):
    """Tek satırlık beyan: License-Expression > kısa License > sınıflandırıcı."""
    if m['License-Expression']:
        return m['License-Expression']
    lisans = (m['License'] or '').strip()
    if lisans and len(lisans) <= 80 and '\n' not in lisans:
        return lisans
    if m['Classifier']:
        return '; '.join(c.split('::')[-1].strip() for c in m['Classifier'])
    if lisans:
        return lisans.splitlines()[0][:80]
    return 'BEYAN YOK (lisans dosyasına bakın)'


def dagitimlari_tara(libs):
    kayitlar = []
    for di in sorted(libs.glob('*.dist-info')):
        m = metadata_oku(di)
        dosyalar = sorted(p.relative_to(libs).as_posix() for p in di.rglob('*')
                          if p.is_file() and (LISANS_DOSYASI.match(p.name)
                                              or 'licenses' in p.relative_to(di).parts))
        beyan = ' | '.join(filter(None, [m['License'], m['License-Expression']]
                                  + m['Classifier']))
        kayitlar.append({
            'ad': m['Name'] or di.name.split('-')[0],
            'surum': m['Version'] or '?',
            'lisans': lisans_ozeti(m),
            'dosyalar': dosyalar,
            'copyleft': bool(COPYLEFT.search(beyan)),
        })
    return kayitlar


def bildirimdeki_dagitimlar(metin):
    return {normalize(a) for a in
            re.findall(r'^Distribution:\s*(\S+)\s*$', metin, flags=re.M)}


def bildirimdeki_metinler(metin):
    return set(re.findall(r'licenses/([A-Za-z0-9_.\-]+\.txt)', metin))


#: Üçüncü taraf veri manifestlerinin dizini (depo köküne göre) ve adı.
VERI_DIZINI = ('hrma', 'static', 'map')
VERI_MANIFEST_DESENI = '*_manifest.json'


def bildirimdeki_veriler(metin):
    return set(re.findall(r'^Data:\s*(\S+)\s*$', metin, flags=re.M))


def lisansli_veri_dosyalari(kaynak):
    """Üst düzeyde ``license`` beyan eden veri manifestlerinin dosyaları.

    Dönüş: {depo-göreli yol: manifest adı}. Manifest okunamazsa ya da
    lisanslı olup dosya adı taşımıyorsa HATA (fail-closed): beyanı
    ölçülemeyen veri pakete sessizce girmez.
    """
    import json
    dizin = kaynak.joinpath(*VERI_DIZINI)
    cikti = {}
    if not dizin.is_dir():
        return cikti
    for man in sorted(dizin.glob(VERI_MANIFEST_DESENI)):
        try:
            m = json.loads(man.read_text(encoding='utf-8'))
        except (OSError, ValueError) as hata:
            raise LisansHatasi('veri manifesti okunamadı: %s (%s)' % (man.name, hata))
        if not isinstance(m, dict) or not m.get('license'):
            continue
        dosyalar = [v.get('file') for v in m.values()
                    if isinstance(v, dict) and isinstance(v.get('file'), str)]
        if not dosyalar:
            raise LisansHatasi('lisanslı veri manifesti dosya adı taşımıyor: %s' % man.name)
        for ad in dosyalar:
            if '/' in ad or '\\' in ad or ad.startswith('.'):
                raise LisansHatasi('veri manifestinde geçersiz dosya adı: %s (%r)' % (man.name, ad))
            cikti['/'.join(VERI_DIZINI + (ad,))] = man.name
    return cikti


def veri_bildirimlerini_denetle(kaynak, bildirim):
    """Lisanslı her veri dosyası bildirimde ``Data:`` ile beyanlı mı?"""
    beyanli = bildirimdeki_veriler(bildirim)
    gereken = lisansli_veri_dosyalari(kaynak)
    beyansiz = sorted('%s (%s)' % (yol, man) for yol, man in gereken.items()
                      if yol not in beyanli)
    if beyansiz:
        raise LisansHatasi('lisanslı veri dosyası bildirimde beyan edilmemiş (%s '
                           'içine "Data: <yol>" bölümü ekleyin): %s'
                           % (BILDIRIM_ADI, '; '.join(beyansiz)))
    yok = sorted(y for y in beyanli if not kaynak.joinpath(*y.split('/')).is_file())
    if yok:
        raise LisansHatasi('bildirimin andığı veri dosyası kaynak ağaçta yok: %s'
                           % ', '.join(yok))
    return sorted(gereken)


#: V307/FS-HARİTA-VERİ: indirilebilir harita paketlerinin listesi (kurucuda yalnız liste
#: bulunur; paketler ayrı dosyadır). Listede anılan her lisans, bildirimde bu listenin
#: ``Data:`` bölümünde ``Pack-Licence: <lisans>`` satırıyla beyanlı olmalıdır.
HARITA_PAKET_LISTESI = ('hrma', 'static', 'map', 'harita_paketleri.json')


def harita_paketi_bildirimlerini_denetle(kaynak, bildirim):
    """Harita paketi listesindeki her bileşen lisansı bildirimde beyanlı mı? (fail-closed)"""
    import json
    yol = kaynak.joinpath(*HARITA_PAKET_LISTESI)
    if not yol.is_file():
        return []
    try:
        m = json.loads(yol.read_text(encoding='utf-8'))
        lisanslar = sorted({b['license'] for p in m['packs'] for b in p['components']})
    except (OSError, ValueError, KeyError, TypeError) as hata:
        raise LisansHatasi('harita paketi listesi okunamadı: %s (%s)' % (yol.name, hata))
    if not lisanslar:
        raise LisansHatasi('harita paketi listesi lisans taşımıyor: %s' % yol.name)
    rel = '/'.join(HARITA_PAKET_LISTESI)
    bolum = None
    for parca in re.split(r'^== ', bildirim, flags=re.M):
        if re.search(r'^Data:\s*%s\s*$' % re.escape(rel), parca, flags=re.M):
            bolum = parca
            break
    if bolum is None:
        raise LisansHatasi('harita paketi listesi bildirimde beyan edilmemiş (%s içine '
                           '"Data: %s" bölümü ekleyin)' % (BILDIRIM_ADI, rel))
    beyanli = set(re.findall(r'^Pack-Licence:\s*(\S+)\s*$', bolum, flags=re.M))
    eksik = [l for l in lisanslar if l not in beyanli]
    if eksik:
        raise LisansHatasi('harita paketi lisansı bildirimde beyan edilmemiş ("Pack-Licence: '
                           '<lisans>" satırı ekleyin): %s' % ', '.join(eksik))
    return lisanslar


def paketle(kaynak, app, libs):
    lisans = kaynak / 'LICENSE'
    if not lisans.is_file():
        raise LisansHatasi('depoda LICENSE yok: %s' % lisans)
    bas = lisans.read_text(encoding='utf-8', errors='replace')[:400]
    if 'GNU GENERAL PUBLIC LICENSE' not in bas or 'Version 3' not in bas:
        raise LisansHatasi('LICENSE GNU GPL sürüm 3 metni değil (ilk satırlar: %r) — '
                           'paketin lisans beyanı GPL-3.0-or-later' % bas[:80])
    if not app.is_dir():
        raise LisansHatasi('paket app/ dizini yok: %s' % app)
    if not libs.is_dir():
        raise LisansHatasi('paket libs/ dizini yok: %s' % libs)

    bildirim_yolu = LISANS_KAYNAK_DIZINI / BILDIRIM_ADI
    bildirim = bildirim_yolu.read_text(encoding='utf-8')
    eksik_metin = sorted(m for m in bildirimdeki_metinler(bildirim)
                         if m != DAGITIM_LISTESI_ADI  # derlemede üretilir
                         and not (LISANS_KAYNAK_DIZINI / m).is_file())
    if eksik_metin:
        raise LisansHatasi('bildirimin andığı lisans metni packaging/licenses/ '
                           'altında yok: %s' % ', '.join(eksik_metin))

    veri_bildirimlerini_denetle(kaynak, bildirim)
    harita_paketi_bildirimlerini_denetle(kaynak, bildirim)

    kayitlar = dagitimlari_tara(libs)
    adlar = {normalize(k['ad']): k for k in kayitlar}
    for zorunlu in ZORUNLU_DAGITIMLAR:
        k = adlar.get(zorunlu)
        if k is None:
            raise LisansHatasi('%s dağıtımı libs/ içinde yok — bildirimi ölçülemiyor' % zorunlu)
        if not k['dosyalar']:
            raise LisansHatasi('%s %s lisans dosyası taşımıyor (dist-info)' % (zorunlu, k['surum']))
    beyanli = bildirimdeki_dagitimlar(bildirim)
    beyansiz = sorted('%s %s (%s)' % (k['ad'], k['surum'], k['lisans'])
                      for k in kayitlar
                      if k['copyleft'] and normalize(k['ad']) not in beyanli)
    if beyansiz:
        raise LisansHatasi('kopyalayıcı-izinli lisanslı dağıtım bildirimde beyan '
                           'edilmemiş (%s içine "Distribution: <ad>" bölümü '
                           'ekleyin): %s' % (BILDIRIM_ADI, '; '.join(beyansiz)))

    shutil.copyfile(lisans, app / 'LICENSE')
    hedef = app / 'licenses'
    if hedef.exists():
        shutil.rmtree(hedef)
    hedef.mkdir()
    for dosya in sorted(LISANS_KAYNAK_DIZINI.iterdir()):
        if dosya.is_file():
            shutil.copyfile(dosya, hedef / dosya.name)
    satirlar = [
        'HRMA — bundled Python distributions and their licences',
        'Generated by packaging/lisans_paketle.py from libs/*.dist-info when the',
        'package was built. Paths are relative to the libs/ directory of this',
        'installation. Copyleft-licensed entries are described in %s.' % BILDIRIM_ADI,
        '',
    ]
    for k in kayitlar:
        satirlar.append('%s %s — %s%s' % (k['ad'], k['surum'], k['lisans'],
                                          '  [copyleft]' if k['copyleft'] else ''))
        satirlar.extend('    %s' % d for d in k['dosyalar'])
        if not k['dosyalar']:
            satirlar.append('    (the distribution ships no licence file)')
    (hedef / DAGITIM_LISTESI_ADI).write_text('\n'.join(satirlar) + '\n', encoding='utf-8')
    return kayitlar


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--kaynak', required=True, type=pathlib.Path)
    ap.add_argument('--app', required=True, type=pathlib.Path)
    ap.add_argument('--libs', required=True, type=pathlib.Path)
    a = ap.parse_args(argv)
    try:
        kayitlar = paketle(a.kaynak, a.app, a.libs)
    except LisansHatasi as hata:
        print('HATA (lisans): %s' % hata)
        return 1
    copyleft = [k['ad'] for k in kayitlar if k['copyleft']]
    print('      LICENSE (GPL-3.0-or-later) + licenses/ pakette; %d dağıtım '
          'listelendi, copyleft beyanlı: %s' % (len(kayitlar), ', '.join(copyleft) or '-'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
