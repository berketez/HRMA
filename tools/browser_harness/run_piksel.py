#!/usr/bin/env python3
"""Piksel turu — OLUŞMUŞ SAYFANIN dil, ondalık ve taşma denetimi (ÖH D37).

Ne yapar
--------
Motor sayfalarını (varsayılan ``hybrid,solid,liquid``) her DİL (``tr``,
``en``) ve her GENİŞLİK (``1440`` = 1440x900, ``390`` = 390x844) için ayrı,
temiz bir tarayıcı bağlamında açar; ürünle gelen ÖRNEK PROJEYİ
(``?project=<ad>``) yükletir, hesabı tetikler ve oluşmuş sayfada beş
soruyu ölçer (defter OH-D33-45):

 1. ``piksel_dil_safligi``         TR sayfada İngilizce cümle / EN'de Türkçe
 2. ``piksel_ondalik_tutarliligi`` aynı panelde virgül + nokta ondalık
 3. ``piksel_oge_tasmasi``         metin kutusu içeriğinden dar
 4. ``piksel_ebeveyn_asimi``       metin öğesi ebeveyn kutusunu aşıyor
 5. ``piksel_yatay_kaydirma``      belge görüntü alanından geniş (DV-TOOLTIP)

Varsayılan kapı turu (``run_tour.py``) BU DENETİMLERİ KOŞTURMAZ: piksel
turu ayrı bir kiptir (dil × genişlik matrisi, örnek proje). Kapıya
bağlanması Faz C / paketleme kararıdır.

Kullanım
--------
    python tools/browser_harness/run_piksel.py --out /tmp/piksel
    python tools/browser_harness/run_piksel.py --out /tmp/piksel \\
        --base-url http://127.0.0.1:8191 --pages liquid --langs tr --widths 390

``--base-url`` verilmezse uygulama ``python -m hrma.run`` ile alt süreç
olarak başlatılır ve tur nasıl biterse bitsin ÖLDÜRÜLÜR. O durumda
``HRMA_PROJECTS_DIR`` ayarlı değilse ``<out>/projeler`` yapılır: örnek
tohumlama kullanıcının GERÇEK proje dizinine yazmasın.

Çıkış kodu: bütün denetimler geçerse 0, herhangi biri kalırsa 1,
argüman/sunucu hatasında 2.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence

_BU_DIZIN = os.path.dirname(os.path.abspath(__file__))
_DEPO_KOKU = os.path.dirname(os.path.dirname(_BU_DIZIN))
if _DEPO_KOKU not in sys.path:
    sys.path.insert(0, _DEPO_KOKU)

from tools.browser_harness import denetimler, esikler, piksel, sayfalar, sunucu  # noqa: E402

#: Rapor dosyasının adı.
PIKSEL_RAPOR_ADI = 'piksel_raporu.json'

#: Rapor şeması sürümü. Alan adı/anlamı değişirse artırılır.
PIKSEL_RAPOR_SURUMU = 1


def argumanlari_coz(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    a = argparse.ArgumentParser(prog='run_piksel.py',
                                description='HRMA oluşmuş sayfa piksel turu')
    a.add_argument('--pages', default=','.join(sayfalar.HESAPLI_SIRA),
                   help='virgülle ayrılmış sayfa listesi (varsayılan: %(default)s)')
    a.add_argument('--langs', default=','.join(esikler.PIKSEL_DILLERI),
                   help='diller (varsayılan: %(default)s)')
    a.add_argument('--widths', default=','.join(esikler.PIKSEL_GORUNTU_ALANLARI),
                   help='genişlik adları (varsayılan: %(default)s)')
    a.add_argument('--out', required=True, help='rapor dizini')
    a.add_argument('--base-url', default=None,
                   help='çalışan sunucunun adresi; verilmezse alt süreç başlatılır')
    a.add_argument('--headed', action='store_true', help='tarayıcıyı görünür aç')
    a.add_argument('--channel', default='auto', help='Chromium yapısı (run_tour ile aynı)')
    a.add_argument('--screenshots', action='store_true',
                   help='her kombinasyonun görüntü alanı karesini kaydet')
    a.add_argument('--dict-delay-ms', type=int, default=0,
                   help='SÖZLÜK YARIŞI kipi: ortak sözlük isteğini bu kadar '
                        'beklet (varsayılan 0 = kapalı; bkz. esikler.'
                        'PIKSEL_GEC_SOZLUK_DESENI)')
    a.add_argument('--raw', action='store_true',
                   help='ham ölçümü (bütün metin yaprakları) rapora ekle — büyük')
    return a.parse_args(argv)


def _liste(metin: str) -> List[str]:
    return [p.strip() for p in (metin or '').split(',') if p.strip()]


def _git_kunyesi() -> Dict[str, Any]:
    """Ölçülen ağacın kimliği — rapor hangi koda aitti (en iyi çaba)."""
    try:
        bas = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=_DEPO_KOKU,
                             capture_output=True, text=True, timeout=10)
        kirli = subprocess.run(['git', 'status', '--porcelain', '--', 'hrma'],
                               cwd=_DEPO_KOKU, capture_output=True, text=True,
                               timeout=20)
        return {'commit': bas.stdout.strip() or None,
                'hrma_kirli': bool(kirli.stdout.strip())}
    except Exception as hata:  # pragma: no cover - git yoksa
        return {'commit': None, 'hata': str(hata)[:200]}


def esik_kunyesi() -> Dict[str, Any]:
    """Piksel hükmüne giren eşiklerin anlık görüntüsü."""
    adlar = [a for a in dir(esikler) if a.isupper() and (
        a.startswith(('PIKSEL_', 'DIL_SAFLIGI_', 'ONDALIK_'))
        or a in ('URUN_DIL_DEPOLAMA_ANAHTARI', 'YATAY_TASMA_TOLERANS_PX'))]
    kunye: Dict[str, Any] = {}
    for a in sorted(adlar):
        d = getattr(esikler, a)
        kunye[a] = list(d) if isinstance(d, tuple) else d
    return kunye


def rapor_olustur(temel_url: str, sunucu_kunyesi: Dict[str, Any],
                  tarayici: Dict[str, Any],
                  kayitlar: List[Dict[str, Any]]) -> Dict[str, Any]:
    denetim_ozeti: Dict[str, Dict[str, int]] = {}
    kirmizilar: List[Dict[str, Any]] = []
    for k in kayitlar:
        for d in k.get('denetimler', []):
            o = denetim_ozeti.setdefault(d['ad'], {'gecen': 0, 'kalan': 0})
            o['gecen' if d.get('gecti') else 'kalan'] += 1
            if not d.get('gecti'):
                kirmizilar.append({'sayfa': k['sayfa'], 'dil': k['dil'],
                                   'genislik': k['genislik'], 'denetim': d['ad'],
                                   'ozet': d['ozet']})
    tarayici_hukmu = denetimler.tarayici_denetimi(tarayici)
    rapor = {
        'surum': PIKSEL_RAPOR_SURUMU,
        'arac': 'tools/browser_harness/run_piksel.py',
        'olusturma_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'temel_url': temel_url,
        'agac': _git_kunyesi(),
        'sunucu': sunucu_kunyesi,
        'tarayici': tarayici,
        'denetimler': [tarayici_hukmu.sozluk()],
        'esikler': esik_kunyesi(),
        'kombinasyonlar': kayitlar,
        'ozet': {
            'kombinasyon_sayisi': len(kayitlar),
            'gecen_kombinasyon': sum(1 for k in kayitlar if k.get('gecti')),
            'kalan_kombinasyon': sum(1 for k in kayitlar if not k.get('gecti')),
            'denetim_bazinda': denetim_ozeti,
            'kirmizi_sayisi': len(kirmizilar),
            'kirmizilar': kirmizilar,
        },
    }
    rapor['gecti'] = (bool(kayitlar) and all(k.get('gecti') for k in kayitlar)
                      and tarayici_hukmu.gecti)
    return rapor


def ozeti_yaz(rapor: Dict[str, Any], akis=None) -> None:
    akis = akis or sys.stdout
    yaz = lambda s: print(s, file=akis)  # noqa: E731
    yaz('=' * 72)
    yaz('  PİKSEL TURU — %s' % rapor.get('temel_url'))
    yaz('=' * 72)
    for d in rapor.get('denetimler', []):
        yaz('%s%-28s %s' % ('  ok ' if d.get('gecti') else '  XX ', d['ad'], d['ozet']))
    for k in rapor.get('kombinasyonlar', []):
        yaz('')
        yaz('[%s] %s · %s · %s' % ('GEÇTİ' if k.get('gecti') else 'KALDI',
                                   k['sayfa'], k['dil'], k['genislik']))
        for d in k.get('denetimler', []):
            yaz('%s%-28s %s' % ('  ok ' if d.get('gecti') else '  XX ', d['ad'],
                                d['ozet'][:220]))
    o = rapor.get('ozet', {})
    yaz('')
    yaz('-' * 72)
    yaz('SONUÇ: %s — %d/%d kombinasyon geçti, %d kırmızı denetim'
        % ('TEMİZ' if rapor.get('gecti') else 'KIRMIZI VAR',
           o.get('gecen_kombinasyon', 0), o.get('kombinasyon_sayisi', 0),
           o.get('kirmizi_sayisi', 0)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = argumanlari_coz(argv)
    try:
        tanimlar = sayfalar.sayfalari_coz(args.pages)
        bilinmeyen = [t.ad for t in tanimlar if t.ad not in esikler.PIKSEL_ORNEK_PROJELERI]
        if bilinmeyen:
            raise ValueError('örnek projesi tanımlı olmayan sayfa: %s (piksel turu '
                             'yalnız motor sayfalarını gezer)' % ', '.join(bilinmeyen))
        diller = _liste(args.langs)
        genislikler = _liste(args.widths)
        if not diller or not genislikler:
            raise ValueError('dil ve genişlik listesi boş olamaz')
    except ValueError as hata:
        print('HATA: %s' % hata, file=sys.stderr)
        return 2

    cikti = os.path.abspath(args.out)
    os.makedirs(cikti, exist_ok=True)
    sunucu_nesnesi = None
    try:
        if args.base_url:
            temel_url = args.base_url.rstrip('/')
            sunucu_kunyesi = {'kaynak': 'harici'}
            if not sunucu.hazir_mi(temel_url):
                print('HATA: %s%s cevap vermiyor' % (temel_url, sunucu.SAGLIK_YOLU),
                      file=sys.stderr)
                return 2
        else:
            if not os.environ.get('HRMA_PROJECTS_DIR'):
                os.environ['HRMA_PROJECTS_DIR'] = os.path.join(cikti, 'projeler')
            gunluk = os.path.join(cikti, 'sunucu.log')
            sunucu_nesnesi = sunucu.UygulamaSunucusu(gunluk_yolu=gunluk)
            sunucu_nesnesi.baslat()
            temel_url = sunucu_nesnesi.temel_url
            sunucu_kunyesi = {'kaynak': 'alt_surec', 'port': sunucu_nesnesi.port,
                              'gunluk': gunluk,
                              'proje_dizini': os.environ.get('HRMA_PROJECTS_DIR')}
        try:
            kayitlar, kunye = piksel.piksel_turu_kos(
                temel_url, tanimlar, diller, genislikler, cikti_dizini=cikti,
                basli=args.headed, kanal=args.channel, goruntu=args.screenshots,
                ham=args.raw, sozluk_gecikmesi_ms=max(0, args.dict_delay_ms))
        except ValueError as hata:
            print('HATA: %s' % hata, file=sys.stderr)
            return 2
    finally:
        if sunucu_nesnesi is not None:
            sunucu_nesnesi.durdur()

    rapor = rapor_olustur(temel_url, sunucu_kunyesi, kunye, kayitlar)
    yol = os.path.join(cikti, PIKSEL_RAPOR_ADI)
    with open(yol, 'w', encoding='utf-8') as f:
        json.dump(rapor, f, ensure_ascii=False, indent=1)
    ozeti_yaz(rapor)
    print('')
    print('Rapor: %s' % yol)
    return 0 if rapor['gecti'] else 1


if __name__ == '__main__':
    sys.exit(main())
