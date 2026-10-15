#!/usr/bin/env python3
"""Yayın iş akışının "hangi kapı adımı koştu" beyanını TEK KAYNAKTAN üretir.

Neden var (ÖH D28 / altyapi, defter OH-D27-04 havuzu)
-----------------------------------------------------
``.github/workflows/release.yml`` taslak sürümün GÖVDESİNE ve iş özetine
"koşan kapı adımları" tablosu basıyordu. Tablo ELLE yazılmıştı ve
``packaging/release_gate.sh``in adım numaralarını dondurmuştu. Ölçüldü
(``docs/scofield/raw/OH/D28/altyapi/a1/once.json``): kapının o an **9**
adımı vardı ve hepsi ``N/9`` diye numaralanıyordu, oysa taslak gövdesi
hâlâ ``1/8``…``7/8`` diyordu ve bir satırı şunu iddia ediyordu:

    "8/8 paket içerik denetimi | release_gate.sh'ta böyle bir adım yok
     (başlıklar 1/8..7/8)"

Bu cümle ÖLÇÜMLE YANLIŞTI: ``baslik "8/9  Paket içerik manifesti + boyut
sapması"`` betikte 2026-08-04'ten beri duruyor. Yani "Publish" düğmesine
basacak kişinin okuduğu tek kayıt, kapının kendisi hakkında yanlış bilgi
veriyordu. Kusur elle yazılmış olmasıdır: kapı büyüdükçe beyan bayatlar.

Bu araç tabloyu kapı betiğinin KENDİSİNDEN türetir. Numara/payda hiçbir
yerde ikinci kez yazılmaz. Durumlar adım BAŞLIĞINA göre eşlenir, numaraya
göre değil — adım eklenip numaralar kayınca eşleme bozulmasın diye.

FAIL-CLOSED: başlığı ``DURUMLAR``da karşılığı olmayan bir adım "koştu"
sayılmaz, "beyan edilmedi" diye basılır. Yeni bir kapı adımı eklendiğinde
beyan sessizce eksilmez, görünür şekilde eksik kalır.

Kullanım:
    python3 tools/yayin_kapi_ozeti.py --tablo     # markdown tablo satırları
    python3 tools/yayin_kapi_ozeti.py --gerekce   # taslak gövdesi için düz metin
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Dict, List, NamedTuple, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAPI_BETIGI = os.path.join(REPO_ROOT, 'packaging', 'release_gate.sh')

#: Adım başlığında aranan ayırt edici parça -> (durum kısaltması, açıklama).
#: Anahtar KÜÇÜK HARFE çevrilmiş başlıkta ``in`` ile aranır; numara değil.
DURUMLAR: Dict[str, Tuple[str, str]] = {
    'sürüm tutarlılığı': (
        'kostu', 'koştu (`surum-baglantisi` işi: etiket ↔ paket sürümü ↔ '
                 'changelog ↔ sürüm notu ↔ README)'),
    'git durumu': (
        'kosmadi', '**koşmadı** — etiket üzerinde ayrık HEAD\'de üst akış '
                   'dalı yok; yerine etiket SHA ↔ derleme SHA karşılaştırıldı'),
    'yapı ↔ commit': (
        'kostu', 'koştu — köken kaydı (BUILD_INFO.sha == etiket SHA), hem '
                 'DMG içinden hem Windows payload\'dan'),
    'github actions': (
        'kostu', 'koştu — `tests` iş akışının bu SHA\'daki sonucu ayrı işte '
                 '(`ci-durumu`) ölçüldü'),
    'tam test takımı': ('kostu', 'koştu'),
    'canlı duman testi': (
        'kostu', 'koştu (8087 portu, üç motor türü, Origin başlıklı)'),
    'macos paket imzası': (
        'kostu', 'koştu (`--deep`; DMG içeriği için `--deep --strict`)'),
    'paket içerik manifesti': (
        'kismen', 'KISMEN — DMG boyutu, Resources kökü ve örnek proje sayısı '
                  '(depo ⟷ paket) ölçüldü; kapının boyut SAPMASI eşiği bu iş '
                  'akışında koşmadı'),
    'görsel tur': (
        'kosmadi', '**koşmadı** — tarayıcı denetim turu yayın iş akışında '
                   'ayağa kaldırılmıyor; yerel kapıda koşar'),
    'iddia dili': (
        'kostu', 'koştu — `tools/iddia_lint.py --check` (`testler` işi)'),
}

BEYAN_EDILMEDI = (
    'beyan',
    '**beyan edilmedi** — bu iş akışında karşılığı ölçülmedi (kapıya yeni '
    'adım eklendiğinde beyan sessizce eksilmesin diye fail-closed basılır)')


class Adim(NamedTuple):
    numara: int
    payda: int
    baslik: str


def kapi_adimlari(betik: str = KAPI_BETIGI) -> List[Adim]:
    """``baslik "N/P  Ad"`` satırlarını kapı betiğinden oku."""
    with open(betik, encoding='utf-8') as fh:
        metin = fh.read()
    adimlar = [Adim(int(n), int(p), b.strip())
               for n, p, b in re.findall(r'^baslik "(\d+)/(\d+)\s+([^"]*)"',
                                         metin, flags=re.M)]
    if not adimlar:
        raise SystemExit(
            f'KAPI ADIMI OKUNAMADI: {betik} içinde `baslik "N/P ..."` yok. '
            'Beyan uydurulmaz; iş kırılır.')
    return adimlar


def _kucult(metin: str) -> str:
    """Türkçe duyarlı küçültme.

    ``'İ'.lower()`` Python'da ``'i'`` DEĞİL, ``'i' + U+0307`` (birleşen üst
    nokta) üretir; düz ``in`` araması o yüzden "İddia dili" başlığında
    ``'iddia dili'`` anahtarını KAÇIRIR. Ölçüldü: eşleme sessizce düşüyor ve
    adım "beyan edilmedi" görünüyordu — yani hata fail-closed tarafa düşüyor
    ama beyan yine de yanlış oluyordu. Nokta önce elle sökülür.
    """
    return metin.replace('İ', 'i').replace('I', 'ı').lower()


def durum(baslik: str) -> Tuple[str, str]:
    kucuk = _kucult(baslik)
    for anahtar, deger in DURUMLAR.items():
        if _kucult(anahtar) in kucuk:
            return deger
    return BEYAN_EDILMEDI


def tutarlilik(adimlar: List[Adim]) -> List[str]:
    """Kapının KENDİ beyanı tutarlı mı? (ölçüm, iddia değil)"""
    sorun = []
    paydalar = {a.payda for a in adimlar}
    if len(paydalar) != 1:
        sorun.append(f'adımlar tek bir paydada değil: {sorted(paydalar)}')
    elif paydalar != {len(adimlar)}:
        sorun.append(f'beyan edilen adım sayısı {paydalar.pop()} ama '
                     f'betikte {len(adimlar)} adım var')
    if [a.numara for a in adimlar] != list(range(1, len(adimlar) + 1)):
        sorun.append(f'numaralar 1..N sırasında değil: '
                     f'{[a.numara for a in adimlar]}')
    return sorun


def tablo(adimlar: List[Adim]) -> List[str]:
    satirlar = ['| Kapı adımı | Durum |', '|---|---|']
    for a in adimlar:
        _kod, metin = durum(a.baslik)
        satirlar.append(f'| {a.numara}/{a.payda} {a.baslik} | {metin} |')
    return satirlar


def gerekce(adimlar: List[Adim]) -> str:
    kostu, kosmadi, digeri = [], [], []
    for a in adimlar:
        kod, _metin = durum(a.baslik)
        etiket = f'{a.numara}/{a.payda} {a.baslik}'
        (kostu if kod == 'kostu' else
         kosmadi if kod == 'kosmadi' else digeri).append(etiket)
    parcalar = [
        'CI taslağı (.github/workflows/release.yml): artefaktlar etiketlenen '
        'ağaçtan bu koşuda üretildi.',
        'KOŞAN kapı adımları — ' + '; '.join(kostu) + '.',
    ]
    if kosmadi:
        parcalar.append('KOŞMAYAN — ' + '; '.join(kosmadi) + '.')
    if digeri:
        parcalar.append('KISMEN / BEYAN EDİLMEDİ — ' + '; '.join(digeri) + '.')
    parcalar.append(
        'Adım listesi packaging/release_gate.sh betiğinden türetilir '
        '(tools/yayin_kapi_ozeti.py); bu metinde elle yazılmış adım numarası '
        'yoktur.')
    parcalar.append(
        'Otomasyon paketin üretildiğini ve imzalı olduğunu kanıtlar, KURULUM '
        'DENEYİMİNİ kanıtlamaz: yayına çevirmeden önce en az bir artefaktı '
        'indirip kurun. Ayrıntı: docs/dev/yayin_otomasyonu.md')
    return ' '.join(parcalar)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tablo', action='store_true')
    ap.add_argument('--gerekce', action='store_true')
    ap.add_argument('--betik', default=KAPI_BETIGI)
    args = ap.parse_args(argv)

    adimlar = kapi_adimlari(args.betik)
    sorunlar = tutarlilik(adimlar)
    if sorunlar:
        for s in sorunlar:
            print(f'KAPI BEYANI TUTARSIZ: {s}', file=sys.stderr)
        return 1

    if args.gerekce:
        print(gerekce(adimlar))
    else:
        print('\n'.join(tablo(adimlar)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
