#!/usr/bin/env python3
"""``node``a kapılı test dosyalarını KAYNAKTAN sayar — elle yazılmış sayı yok.

NEDEN (ÖH defter OH-D25-24, zincir OH-D17-19 / P13B1-04):
CI iş akışlarının yorumunda "<N> test dosyası ön yüz sözleşmelerini node ile
doğruluyor" iddiası ELLE yazılıydı ve her birleşme dalgasında çürüdü:

    88 (D21)  ->  92 (fix-20)  ->  94 (fix-23)  ->  97 (D26 tabanı)

Üç kez elle güncellendi, üç kez yeniden çürüdü; dördüncüsünde (97) bekçi yine
kırmızıydı. Kusur sayının yanlış olması DEĞİL, sayının ELLE tutulmasıdır:
bir dosyayı `node` kapısına alan her kulvar, ilgisiz bir iş akışı yorumunu
aynı commit'te güncellemek zorunda kalıyordu — yapılmadığı her seferde kapı
sessizce bayatladı.

ÇÖZÜM — TEK KAYNAK: sayı yalnız BURADA, ölçümle üretilir. İş akışları bu
betiği KOŞAR (yorumda sayı taşımazlar), bekçi de aynı işlevi ithal eder.
Böylece güncellenecek bir sayı kalmaz.

Kullanım:
    python tools/node_kapisi_sayimi.py            # sayar, tabanın altındaysa 1
    python tools/node_kapisi_sayimi.py --liste    # dosyaları da yazar
    python tools/node_kapisi_sayimi.py --json
"""
import argparse
import json
import pathlib
import re
import sys

KOK = pathlib.Path(__file__).resolve().parents[1]

#: Bir test dosyasını ``node``a KAPILI yapan deyim. P13'ün ölçümüyle birebir
#: aynı prob (ALT SINIR: ``which`` sormadan node çağıran dosyalar girmez).
NODE_KAPISI = re.compile(r"which\(\s*['\"]node['\"]\s*\)")

#: ...ve deyimi GERÇEKTEN çağırabilmesi için modülü ithal etmiş olmalı.
#: Bu ikinci koşul olmadan ölçüm KENDİ ARACINI da sayar: bekçinin hata
#: metinlerinde geçen ``shutil.which('node')`` dizgesi sayıyı bir artırıyor
#: ve "yorum çürüdü" bekçisini yalancı kırmızıya düşürüyordu (ölçüldü,
#: 27 Ağustos 2026). Metinde ANMAK kapı kurmak değildir.
SHUTIL_ITHALI = re.compile(r'^\s*(import shutil|from shutil import)',
                           re.MULTILINE)

#: Ölçümün kendisi bozulursa (regex kırılır, kapı toptan sökülür) sayı sıfıra
#: yaklaşır ve bu betik SESSİZ kalırsa 2026-08-03 vakası aynen tekrar eder:
#: node kurulmamıştı, kapılı bekçilerin hiçbiri CI'da bir kez bile koşmamıştı.
#: Bu yüzden TABAN bir fail-closed alt sınırdır — sayı ölçülür, taban sabittir.
#: P13 ölçümü 67 idi; taban o günden bu yana hiç düşmedi.
TABAN = 50


def node_kapili_test_dosyalari(kok=KOK) -> frozenset:
    """``node``a kapılı test dosyaları — ELLE liste değil, kaynaktan ölçüm."""
    kok = pathlib.Path(kok).resolve()
    bulunan = set()
    for p in sorted((kok / 'tests').rglob('test_*.py')):
        try:
            kaynak = p.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        if NODE_KAPISI.search(kaynak) and SHUTIL_ITHALI.search(kaynak):
            bulunan.add(p.relative_to(kok).as_posix())
    return frozenset(bulunan)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kok', default=str(KOK))
    ap.add_argument('--liste', action='store_true')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)

    dosyalar = sorted(node_kapili_test_dosyalari(args.kok))
    if args.json:
        print(json.dumps({'taban': TABAN, 'sayi': len(dosyalar),
                          'dosyalar': dosyalar}, ensure_ascii=False, indent=2))
    else:
        print(f'node kapılı test dosyası: {len(dosyalar)} (taban {TABAN})')
        if args.liste:
            for d in dosyalar:
                print(f'  {d}')
    if len(dosyalar) < TABAN:
        print(
            f'HATA: ölçüm {len(dosyalar)} döndü, taban {TABAN}. Ya ön yüz '
            "kapısı toptan söküldü ya ölçüm (regex) bozuldu. `node` "
            'kurulmazsa bu dosyaların bekçileri KIRMIZI VERMEDEN atlanır '
            '(2026-08-03 vakası). Sessiz kalınamaz.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
