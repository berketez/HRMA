#!/usr/bin/env python3
"""Sürüm adı commit'inin dosyalarını taslaklardan üretir.

Kaynak: 3.0.6 sürüm adı üreticisi (ana model, 9 Kas 2026,
``docs/scofield/raw/OH/V306/ana-model/olcum/surum_notu_sayilari/surum_commit_uret.py``).
16 Kas 2026'da depoya alındı ve genelleştirildi (3.0.7 SÜREÇ kalem 1).

Neden README de burada (3.0.6 yayın günü, 10 Kas): sürüm adı commit'i
(7ac9815e1) README'yi kapsamıyordu. Yayın kapısı 1/10 README'de
``HRMA-Setup-<sürüm>`` arıyor; rc.7'nin README'si 3.0.5 bağlantılarını
taşıyordu, kapı 3.0.6 adıyla ilk kez yayın günü koştu ve rc.8 kesildi
(+~2 saat). Bu araç artık kapı 1/10'un aradığı HER ŞEYİ aynı commit'te yazar:
``__version__``, ``hrma/data/changelog.json`` en üst kaydı, sürüm notu dosyası,
README indirme bağlantıları (iki tablo × iki platform = 4 satır) ve README
``**HRMA vX.Y.Z**`` satırı. Kapının ölçütü: ``tests/test_v307_surec.py``
araç çıktısı üstünde kapının 1/10 işlevini koşturur.

Kullanım (depo kökünden):
  python3 tools/surum_commit_uret.py --surum 3.0.7 --tarih 2026-11-20 \\
      --baslik "Stable release: ..." \\
      --surum-notu <SURUM_NOTU_TASLAK.md> --changelog <CHANGELOG_TASLAK.md> [--kuru]

  --kuru  hiçbir dosyaya yazmaz; değişecek dosyaları ve satır sayılarını basar.
  --kok   başka bir ağaçta üret (bekçi geçici kopyada koşar); varsayılan: cwd.

Kaynaklar (tek kaynak, elle iki kez yazılmaz):
  sürüm notu taslağı → packaging/release_notes_v<sürüm>.md
  CHANGELOG taslağı  → CHANGELOG.md (önceki sürümün üstüne)
  ikisi              → hrma/data/changelog.json en üst kayıt (başlık + tarih +
                       giriş + Öne çıkanlar + CHANGELOG bölümleri + Güncelleme)
  README.md          → 4 indirme satırı + **HRMA v<sürüm>** satırı
  hrma/__init__.py   → __version__ = "<sürüm>"

Fail-closed: taslaktaki ``<!-- TASLAK ... -->`` yorumu ve ``@@TARIH@@`` dışında
yer tutucu kalırsa, README'nin bilinen biçimi tutmazsa (bağlantı satırı sayısı
4 değilse, sürüm satırı tek değilse), yeni sürüm eskisinden büyük değilse ya da
hedef dosyalar zaten yeni sürümü taşıyorsa HİÇBİR dosya yazılmadan durur.
README'de yeni sürümle değişmeyen eski sürüm anmaları (ör. "Current stable
release" bloğu, "What's New" başlığı — yayından SONRA elle yazılır) satır
numarasıyla basılır; araç onlara dokunmaz.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Dict, List, Tuple

#: README'de indirme bağlantısı taşıyan satır sayısı: "Download" tablosu +
#: "Installation" tablosu, her birinde Windows ve macOS (3.0.6 README'si,
#: 324f88c72). Sayı değişirse araç durur — kapı 1/10 eksik satırı göremez.
README_INDIRME_SATIRI = 4


class UretimHatasi(Exception):
    """Üretim durdu; hiçbir dosya yazılmadı."""


def surum_demeti(metin: str) -> Tuple[int, int, int]:
    m = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', metin)
    if not m:
        raise UretimHatasi('sürüm X.Y.Z biçiminde değil: %r' % metin)
    return tuple(int(p) for p in m.groups())  # type: ignore[return-value]


def temizle(metin: str, tarih: str) -> str:
    metin = re.sub(r'\n*<!-- TASLAK.*?-->\n*', '\n', metin, flags=re.S)
    metin = metin.replace('@@TARIH@@', tarih)
    if '@@' in metin or 'TASLAK' in metin:
        raise UretimHatasi('taslakta yer tutucu ya da TASLAK notu kaldı')
    return metin.strip() + '\n'


def bolum(metin: str, baslik: str) -> str:
    """'## <baslik>' bölümünün gövdesi (bir sonraki '## 'e kadar)."""
    m = re.search(r'^## ' + re.escape(baslik) + r'\n(.*?)(?=^## |\Z)', metin,
                  flags=re.S | re.M)
    if not m:
        raise UretimHatasi('sürüm notunda "## %s" bölümü yok' % baslik)
    return m.group(1).strip()


def uygulama_notu(surum: str, tarih: str, not_md: str, cl_govde: str,
                  one_cikan: str, guncelleme: str) -> str:
    """changelog.json notu: notun başlığı + tarih + CHANGELOG girişi +
    Öne çıkanlar + CHANGELOG bölümleri (### → ##) + Güncelleme."""
    satirlar = not_md.splitlines()
    baslik = satirlar[0]
    if not baslik.startswith('# HRMA v%s' % surum):
        raise UretimHatasi('sürüm notu başlığı "# HRMA v%s" değil: %r' % (surum, baslik))
    tarih_satiri = next((s for s in satirlar if s.startswith('*') and tarih in s), None)
    if tarih_satiri is None:
        raise UretimHatasi('sürüm notunda tarih satırı (*… %s …*) yok' % tarih)
    govde = re.sub(r'^\*.*?\*\n+', '', cl_govde, count=1, flags=re.S)
    giris, _, bolumler = govde.partition('\n### ')
    bolumler = '### ' + bolumler
    bolumler = re.sub(r'^### ', '## ', bolumler, flags=re.M)
    return (f'{baslik}\n\n{tarih_satiri}\n\n{giris.strip()}\n\n'
            f'## {one_cikan}\n\n{bolum(not_md, one_cikan)}\n\n'
            f'{bolumler.strip()}\n\n'
            f'## {guncelleme}\n\n{bolum(not_md, guncelleme)}\n')


def readme_yaz(metin: str, eski: str, yeni: str) -> Tuple[str, List[str]]:
    """README indirme satırları + sürüm satırı. (yeni metin, kalan eski anmalar)."""
    satirlar = metin.split('\n')
    e = re.escape(eski)
    indirme = re.compile(r'/releases/download/v%s/HRMA-Setup-%s(?:-macOS\.dmg|\.exe)\)' % (e, e))
    degisen = 0
    for i, s in enumerate(satirlar):
        if indirme.search(s):
            s2 = s.replace('/releases/download/v%s/' % eski, '/releases/download/v%s/' % yeni)
            s2 = s2.replace('HRMA-Setup-%s-macOS.dmg' % eski, 'HRMA-Setup-%s-macOS.dmg' % yeni)
            s2 = s2.replace('HRMA-Setup-%s.exe' % eski, 'HRMA-Setup-%s.exe' % yeni)
            satirlar[i] = s2
            degisen += 1
    if degisen != README_INDIRME_SATIRI:
        raise UretimHatasi('README\'de v%s indirme bağlantısı taşıyan %d satır var, '
                           'beklenen %d — README biçimi değişti; kapı 1/10 eksik satırı '
                           'göremez, araç güncellenmeli' % (eski, degisen, README_INDIRME_SATIRI))
    surum_satiri = '**HRMA v%s**' % eski
    yerler = [i for i, s in enumerate(satirlar) if s.strip() == surum_satiri]
    if len(yerler) != 1:
        raise UretimHatasi('README\'de "%s" satırı %d kez var, beklenen 1'
                           % (surum_satiri, len(yerler)))
    satirlar[yerler[0]] = satirlar[yerler[0]].replace(surum_satiri, '**HRMA v%s**' % yeni)
    kalan = ['README.md:%d: %s' % (i + 1, s.strip()[:110])
             for i, s in enumerate(satirlar)
             if re.search(r'(?<![\d.])v?%s(?![\d])' % e, s)]
    return '\n'.join(satirlar), kalan


def uret(kok: pathlib.Path, surum: str, tarih: str, baslik: str,
         notu_taslak: str, cl_taslak: str) -> Tuple[Dict[pathlib.Path, str], List[str]]:
    """Yazılacak dosyalar (yol → yeni içerik) ve README'de kalan eski anmalar.

    Hiçbir şey yazmaz; bütün denetimler burada yapılır (fail-closed: önce
    hepsi hesaplanır, sonra hepsi yazılır).
    """
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', tarih):
        raise UretimHatasi('tarih YYYY-AA-GG değil: %r' % tarih)
    init = kok / 'hrma' / '__init__.py'
    if not init.is_file():
        raise UretimHatasi('depo kökü değil (hrma/__init__.py yok): %s' % kok)
    init_metin = init.read_text(encoding='utf-8')
    m = re.findall(r'^__version__ = "([^"]+)"$', init_metin, flags=re.M)
    if len(m) != 1:
        raise UretimHatasi('hrma/__init__.py içinde tek __version__ satırı yok')
    eski = m[0]
    if surum_demeti(surum) <= surum_demeti(eski):
        raise UretimHatasi('yeni sürüm %s, bugünkü %s\'ten büyük değil' % (surum, eski))
    cikti: Dict[pathlib.Path, str] = {}

    # 1. Sürüm notu
    notu = temizle(notu_taslak, tarih)
    if not notu.startswith('<!--HRMA-LANG:en-->') or '<!--HRMA-LANG:tr-->' not in notu:
        raise UretimHatasi('sürüm notunda <!--HRMA-LANG:en/tr--> imleri yok')
    notu_yol = kok / 'packaging' / ('release_notes_v%s.md' % surum)
    if notu_yol.exists():
        raise UretimHatasi('%s zaten var' % notu_yol.relative_to(kok))
    cikti[notu_yol] = notu
    not_en, not_tr = notu.split('<!--HRMA-LANG:tr-->')
    not_en = not_en.replace('<!--HRMA-LANG:en-->', '').strip()
    not_tr = not_tr.strip()

    # 2. CHANGELOG
    cl = temizle(cl_taslak, tarih)
    if not cl.startswith('## %s — English' % surum) or '## %s — Türkçe' % surum not in cl:
        raise UretimHatasi('CHANGELOG taslağı "## %s — English/Türkçe" ile başlamıyor' % surum)
    cl_yol = kok / 'CHANGELOG.md'
    cl_eski = cl_yol.read_text(encoding='utf-8')
    if '## %s — English' % surum in cl_eski:
        raise UretimHatasi('CHANGELOG zaten %s içeriyor' % surum)
    cap = '## %s — English' % eski
    if cl_eski.count(cap) != 1:
        raise UretimHatasi('CHANGELOG\'da "%s" başlığı tek değil' % cap)
    cikti[cl_yol] = cl_eski.replace(cap, cl.rstrip() + '\n\n' + cap, 1)
    cl_en = cl.split('## %s — Türkçe' % surum)[0].replace('## %s — English' % surum, '').strip()
    cl_tr = cl.split('## %s — Türkçe' % surum)[1].strip()

    # 3. changelog.json
    notes_en = uygulama_notu(surum, tarih, not_en, cl_en, 'Highlights', 'Updating')
    notes_tr = uygulama_notu(surum, tarih, not_tr, cl_tr, 'Öne çıkanlar', 'Güncelleme')
    cj_yol = kok / 'hrma' / 'data' / 'changelog.json'
    cj = json.loads(cj_yol.read_text(encoding='utf-8'))
    if cj['versions'][0]['version'] != eski:
        raise UretimHatasi('changelog.json en üst kayıt %s, paket %s'
                           % (cj['versions'][0]['version'], eski))
    cj['versions'].insert(0, {'version': surum, 'date': tarih, 'title': baslik,
                              'notes_en': notes_en, 'notes_tr': notes_tr})
    cikti[cj_yol] = json.dumps(cj, ensure_ascii=False, indent=2) + '\n'

    # 4. __version__
    cikti[init] = init_metin.replace('__version__ = "%s"' % eski,
                                     '__version__ = "%s"' % surum, 1)

    # 5. README — kapı 1/10'un aradığı bağlantılar + sürüm satırı
    readme = kok / 'README.md'
    yeni_readme, kalan = readme_yaz(readme.read_text(encoding='utf-8'), eski, surum)
    cikti[readme] = yeni_readme
    return cikti, kalan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--surum', required=True)
    ap.add_argument('--tarih', required=True)
    ap.add_argument('--baslik', required=True,
                    help='changelog.json "title" (EN), ör. "Stable release: corrections"')
    ap.add_argument('--surum-notu', required=True, type=pathlib.Path)
    ap.add_argument('--changelog', required=True, type=pathlib.Path)
    ap.add_argument('--kok', type=pathlib.Path, default=pathlib.Path.cwd())
    ap.add_argument('--kuru', action='store_true')
    a = ap.parse_args(argv)
    kok = a.kok.resolve()
    try:
        cikti, kalan = uret(kok, a.surum, a.tarih, a.baslik,
                            a.surum_notu.read_text(encoding='utf-8'),
                            a.changelog.read_text(encoding='utf-8'))
    except UretimHatasi as hata:
        print('DURDU (hiçbir dosya yazılmadı): %s' % hata, file=sys.stderr)
        return 2
    for yol, metin in cikti.items():
        eski = yol.read_text(encoding='utf-8') if yol.exists() else ''
        print('%s %s (%d → %d satır)' % ('yazılacak' if a.kuru else 'yazıldı',
                                         yol.relative_to(kok), eski.count('\n'),
                                         metin.count('\n')))
        if not a.kuru:
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_text(metin, encoding='utf-8')
    if kalan:
        print('README\'de eski sürümü anan, araçla DEĞİŞMEYEN satırlar '
              '(yayından sonra elle — kapı 1/10 bunları aramaz):')
        for s in kalan:
            print('  ' + s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
