#!/usr/bin/env python3
"""Paketlenen bağımlılıkların TEK KAYNAK kapısı.

ÖH D23 / altyapi · defter P10B3-19.

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D23/altyapi/a2/once.json``, taban
ef527ae): "paketlenen bağımlılıklar" tek bir dosyadan okunamıyordu.

* ``requirements.txt`` 27 paket, ``packaging/requirements_bundle.txt`` 33
  paket sayıyor; 22 ortak paketin **21'i** farklı kısıt taşıyor.
* 5 paket yalnız ``requirements.txt``te görünüyordu (black, flake8,
  gunicorn, pyinstaller, **rocketcea**) ve hiçbirinin yanında neden
  paketlenmediği yazmıyordu.
* Bunlardan **rocketcea aslında pakete giriyordu**: Windows tarafında
  ``packaging/build_win_payload.sh`` ``--no-deps`` ile kuruyor, macOS
  tarafında ``packaging/build_mac_app.sh`` anaconda ortamından kopyalıyor.
  Yani manifest eksik değil, YANILTICIYDI.

Bu kapı üç şeyi sınar ve hepsi FAIL-CLOSED çalışır:

1. **Beyansız eksik yok.** ``requirements.txt``teki her paket ya bundle'da
   pinlidir, ya ``# 2. AŞAMA: <paket>==<sürüm> — <gerekçe>`` ile beyan
   edilmiştir, ya da ``# HARİÇ: <paket> — <gerekçe>`` ile. Gerekçesiz
   kayıt kabul edilmez; sessiz eksiklik cantera vakasında (v2.6.2) yanlış
   termokimyaya yol açtı.
2. **Pin, aralığın içinde.** Bundle'ın ``==`` pini ``requirements.txt``in
   kısıtını SAĞLAMAK zorundadır. İki dosya "farklı" olabilir — ama
   ÇELİŞEMEZ.
3. **Beyan, betikle çaprazlanır.** Her ``2. AŞAMA`` kaydının adı en az bir
   derleme betiğinde geçmelidir. Böylece manifest ile betikler sessizce
   ayrışamaz: biri değişip diğeri kalırsa kapı kapanır.

Kullanım:
    python3 tools/bundle_kapisi.py            # insan okuru + çıkış kodu
    python3 tools/bundle_kapisi.py --json     # makine okuru
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

KOK = Path(__file__).resolve().parents[1]
REQ = KOK / 'requirements.txt'
BUNDLE = KOK / 'packaging' / 'requirements_bundle.txt'
#: 2. aşama beyanlarının çaprazlanacağı derleme betikleri.
DERLEME_BETIKLERI = (
    KOK / 'packaging' / 'build_win_payload.sh',
    KOK / 'packaging' / 'build_mac_app.sh',
)


def normalize(ad: str) -> str:
    """PEP 503 normalizasyonu (``typing_extensions`` == ``typing-extensions``)."""
    return re.sub(r'[-_.]+', '-', ad).lower()


def gereksinimleri_coz(metin: str) -> Dict[str, str]:
    """``ad -> kısıt`` sözlüğü. Yorum ve seçenek satırları atılır."""
    out: Dict[str, str] = {}
    for ln in metin.splitlines():
        s = ln.split('#')[0].strip()
        if not s or s.startswith('-'):
            continue
        m = re.match(r'^([A-Za-z0-9_.\-]+)\s*(.*)$', s)
        if m:
            out[normalize(m.group(1))] = m.group(2).strip()
    return out


def beyanlari_coz(metin: str) -> Tuple[Dict[str, Dict[str, str]], Dict[str, str]]:
    """``# 2. AŞAMA:`` ve ``# HARİÇ:`` beyanlarını okur."""
    asama2: Dict[str, Dict[str, str]] = {}
    haric: Dict[str, str] = {}
    for ln in metin.splitlines():
        m = re.match(r'^\s*#\s*2\.\s*AŞAMA:\s*([A-Za-z0-9_.\-]+)\s*'
                     r'(==\s*[^\s—-]+)?\s*[—-]\s*(.+?)\s*$', ln)
        if m:
            asama2[normalize(m.group(1))] = {
                'surum': (m.group(2) or '').replace(' ', ''),
                'gerekce': m.group(3).strip(),
            }
            continue
        m = re.match(r'^\s*#\s*HARİÇ:\s*([A-Za-z0-9_.\-]+)\s*[—-]\s*(.+?)\s*$', ln)
        if m:
            haric[normalize(m.group(1))] = m.group(2).strip()
    return asama2, haric


# ---------------------------------------------------------------------------
# Kısıt sağlama — dış bağımlılık olmadan
# ---------------------------------------------------------------------------

def _surum_demeti(s: str) -> Tuple[int, ...]:
    parcalar = []
    for p in re.split(r'[.\-+]', s.strip()):
        m = re.match(r'^(\d+)', p)
        parcalar.append(int(m.group(1)) if m else 0)
    return tuple(parcalar) or (0,)


def _kiyas(a: str, b: str) -> int:
    ta, tb = _surum_demeti(a), _surum_demeti(b)
    n = max(len(ta), len(tb))
    ta = ta + (0,) * (n - len(ta))
    tb = tb + (0,) * (n - len(tb))
    return (ta > tb) - (ta < tb)


def kisiti_sagliyor(pin: str, kisit: str) -> Tuple[bool, str]:
    """``==X`` pini ``kisit`` ifadesini sağlıyor mu?

    Ortam işaretçisi (``;platform_system==...``) taşıyan kısıtlar PLATFORMA
    bağlıdır; sürüm kısmı yine sınanır, işaretçi yok sayılır ve gerekçesi
    döndürülür.
    """
    m = re.match(r'^==\s*([0-9][^\s,;]*)$', pin)
    if not m:
        return False, 'bundle kaydı == pini değil: %r' % pin
    surum = m.group(1)
    kisit_govde = kisit.split(';')[0].strip()
    if not kisit_govde:
        return True, 'requirements kısıtsız'
    for parca in kisit_govde.split(','):
        parca = parca.strip()
        m2 = re.match(r'^(>=|<=|==|!=|>|<|~=)\s*([0-9][^\s]*)$', parca)
        if not m2:
            return False, 'çözülemeyen kısıt parçası: %r' % parca
        op, hedef = m2.group(1), m2.group(2)
        c = _kiyas(surum, hedef)
        tamam = {
            '>=': c >= 0, '<=': c <= 0, '==': c == 0, '!=': c != 0,
            '>': c > 0, '<': c < 0,
            '~=': c >= 0,   # uyumlu-sürüm: alt sınır; üst sınırı ayrıca yazılır
        }[op]
        if not tamam:
            return False, '%s pini %s kısıtını sağlamıyor' % (surum, parca)
    return True, '%s, %s içinde' % (surum, kisit_govde)


def denetle() -> Dict[str, object]:
    req = gereksinimleri_coz(REQ.read_text(encoding='utf-8'))
    bundle_metin = BUNDLE.read_text(encoding='utf-8')
    bundle = gereksinimleri_coz(bundle_metin)
    asama2, haric = beyanlari_coz(bundle_metin)

    betik_metni = '\n'.join(
        p.read_text(encoding='utf-8') for p in DERLEME_BETIKLERI if p.exists())

    beyansiz: List[str] = []
    celisen: List[Dict[str, str]] = []
    betiksiz: List[str] = []

    for ad, kisit in sorted(req.items()):
        if ad in bundle:
            tamam, gerekce = kisiti_sagliyor(bundle[ad], kisit)
            if not tamam:
                celisen.append({'paket': ad, 'requirements': kisit,
                                'bundle': bundle[ad], 'gerekce': gerekce})
            continue
        if ad in asama2 or ad in haric:
            continue
        beyansiz.append(ad)

    for ad, kayit in sorted(asama2.items()):
        # Beyan, betikle çaprazlanır: adı geçmiyorsa manifest ile derleme
        # sessizce ayrışmış demektir.
        if normalize(ad) not in normalize(betik_metni):
            betiksiz.append(ad)

    gecti = not (beyansiz or celisen or betiksiz)
    return {
        'gecti': gecti,
        'requirements_paket': len(req),
        'bundle_paket': len(bundle),
        'asama2_beyani': len(asama2),
        'haric_beyani': len(haric),
        'beyansiz_eksik': beyansiz,
        'celisen_kisit': celisen,
        'betikle_caprazlanmayan_asama2': betiksiz,
    }


def main(argv: List[str]) -> int:
    sonuc = denetle()
    if '--json' in argv:
        print(json.dumps(sonuc, ensure_ascii=False, indent=1))
    else:
        print('requirements: %d paket | bundle: %d paket | 2. aşama beyanı: %d '
              '| hariç beyanı: %d'
              % (sonuc['requirements_paket'], sonuc['bundle_paket'],
                 sonuc['asama2_beyani'], sonuc['haric_beyani']))
        for ad in sonuc['beyansiz_eksik']:
            print('KALDI  %s requirements.txt\'te var, bundle\'da yok ve '
                  'BEYAN EDİLMEMİŞ (2. AŞAMA / HARİÇ)' % ad)
        for c in sonuc['celisen_kisit']:
            print('KALDI  %s: %s' % (c['paket'], c['gerekce']))
        for ad in sonuc['betikle_caprazlanmayan_asama2']:
            print('KALDI  %s "2. AŞAMA" diye beyan edildi ama hiçbir derleme '
                  'betiğinde geçmiyor' % ad)
        print('SONUÇ: %s' % ('KAPI AÇIK' if sonuc['gecti'] else 'KAPI KAPALI'))
    return 0 if sonuc['gecti'] else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
