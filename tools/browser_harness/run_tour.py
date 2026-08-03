#!/usr/bin/env python3
"""Tarayıcı denetim turu — sürüm başına GÖRSEL kapı.

Ne yapar
--------
``/hybrid``, ``/solid`` ve ``/liquid`` sayfalarını gerçek bir tarayıcıda
açar, örnek girdilerle hesabı tetikler, 3B sahneyi kurdurur, yanmayı
başlatır ve dört soruyu ölçer:

1. 3B tuval boş mu?           (doluluk oranı + içerik entropisi)
2. Egzoz çiziliyor mu?        (``_plume.geometry.drawRange.count``)
3. Konsolda hata var mı?
4. Ekrana iç değer sızmış mı? (``[object Object]`` / ``undefined`` / ``NaN``)

Kullanım
--------
    python tools/browser_harness/run_tour.py --out /tmp/tur
    python tools/browser_harness/run_tour.py --pages hybrid --out /tmp/tur
    python tools/browser_harness/run_tour.py --out /tmp/tur \\
        --base-url http://127.0.0.1:8080

``--base-url`` verilmezse uygulama ``python -m hrma.run`` ile alt süreç
olarak başlatılır ve tur nasıl biterse bitsin ÖLDÜRÜLÜR.

Çıkış kodu: bütün denetimler geçerse 0, herhangi biri kalırsa 1.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

# Betik olarak da (``python tools/browser_harness/run_tour.py``), modül olarak
# da (``python -m tools.browser_harness.run_tour``) çalışsın diye depo kökü
# yola eklenir.
_BU_DIZIN = os.path.dirname(os.path.abspath(__file__))
_DEPO_KOKU = os.path.dirname(os.path.dirname(_BU_DIZIN))
if _DEPO_KOKU not in sys.path:
    sys.path.insert(0, _DEPO_KOKU)

from tools.browser_harness import denetimler, esikler, sayfalar, sunucu, tur  # noqa: E402

#: Rapor dosyasının adı. Kapıya bağlayan betik bu adı bekler.
RAPOR_ADI = 'tour_report.json'

#: Rapor şeması sürümü. Alan adı/anlamı değişirse artırılır.
RAPOR_SURUMU = 1


def argumanlari_coz(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ayristirici = argparse.ArgumentParser(
        prog='run_tour.py',
        description='HRMA arayüzünün tarayıcı denetim turu')
    ayristirici.add_argument(
        '--pages', default=','.join(sayfalar.VARSAYILAN_SIRA),
        help='virgülle ayrılmış sayfa listesi (varsayılan: %(default)s)')
    ayristirici.add_argument(
        '--out', required=True,
        help='raporun ve ekran görüntülerinin yazılacağı dizin')
    ayristirici.add_argument(
        '--base-url', default=None,
        help='zaten çalışan bir sunucunun adresi; verilmezse uygulama '
             'alt süreç olarak başlatılır ve sonunda öldürülür')
    ayristirici.add_argument(
        '--headed', action='store_true',
        help='tarayıcıyı görünür pencerede aç (elle izlemek için)')
    ayristirici.add_argument(
        '--channel', default='auto',
        help="Chromium yapısı: 'auto' (varsayılan) paketli Chromium'u, sonra "
             "sistemdeki 'chrome' ve 'msedge' kanallarını dener; açık bir ad "
             'verilirse yalnız o denenir')
    return ayristirici.parse_args(argv)


def esik_kunyesi() -> Dict[str, Any]:
    """Raporun içine eşiklerin anlık görüntüsü — sonradan okunabilsin diye.

    Eşik değişince eski rapor yanlış yorumlanmasın: hüküm hangi sayılarla
    verildiyse o sayılar raporun içinde durur.
    """
    kunye: Dict[str, Any] = {}
    for ad in dir(esikler):
        if not ad.isupper():
            continue
        deger = getattr(esikler, ad)
        if isinstance(deger, (int, float, str, bool, list, dict)):
            kunye[ad] = deger
        elif isinstance(deger, tuple):
            kunye[ad] = list(deger)
    return kunye


def rapor_olustur(temel_url: str, sunucu_kunyesi: Dict[str, Any],
                  tarayici: Dict[str, Any],
                  sayfa_raporlari: List[Dict[str, Any]]) -> Dict[str, Any]:
    kalan_denetimler = [
        {'sayfa': s['ad'], 'denetim': d['ad'], 'ozet': d['ozet'],
         'kesinlik': d.get('kesinlik')}
        for s in sayfa_raporlari for d in s.get('denetimler', [])
        if not d.get('gecti')
    ]
    rapor = {
        'surum': RAPOR_SURUMU,
        'arac': 'tools/browser_harness/run_tour.py',
        'olusturma_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'temel_url': temel_url,
        'sunucu': sunucu_kunyesi,
        'tarayici': tarayici,
        'esikler': esik_kunyesi(),
        'sayfalar': sayfa_raporlari,
        'ozet': {
            'sayfa_sayisi': len(sayfa_raporlari),
            'gecen_sayfa': sum(1 for s in sayfa_raporlari if s.get('gecti')),
            'kalan_sayfa': sum(1 for s in sayfa_raporlari if not s.get('gecti')),
            'kalan_denetim_sayisi': len(kalan_denetimler),
            'kalan_denetimler': kalan_denetimler,
        },
    }
    rapor['gecti'] = denetimler.rapor_hukmu(rapor)
    return rapor


def ozeti_yaz(rapor: Dict[str, Any], akis=None) -> None:
    """İnsanın okuyacağı kısa özet — ayrıntı JSON'da durur."""
    akis = akis or sys.stdout
    yaz = lambda s: print(s, file=akis)  # noqa: E731
    yaz('=' * 72)
    yaz('  TARAYICI DENETİM TURU — %s' % rapor.get('temel_url'))
    yaz('=' * 72)
    for sayfa in rapor.get('sayfalar', []):
        durum = 'GEÇTİ' if sayfa.get('gecti') else 'KALDI'
        yaz('')
        yaz('[%s] %s' % (durum, sayfa.get('url')))
        for d in sayfa.get('denetimler', []):
            isaret = '  ok ' if d.get('gecti') else '  XX '
            ek = '' if d.get('kesinlik') == 'dogrudan' else ' [%s ölçüm]' % d.get('kesinlik')
            yaz('%s%-16s %s%s' % (isaret, d.get('ad'), d.get('ozet'), ek))
    ozet = rapor.get('ozet', {})
    yaz('')
    yaz('-' * 72)
    yaz('SONUÇ: %s — %d/%d sayfa geçti, %d denetim kaldı'
        % ('KAPI AÇIK' if rapor.get('gecti') else 'KAPI KAPALI',
           ozet.get('gecen_sayfa', 0), ozet.get('sayfa_sayisi', 0),
           ozet.get('kalan_denetim_sayisi', 0)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = argumanlari_coz(argv)
    try:
        sayfa_tanimlari = sayfalar.sayfalari_coz(args.pages)
    except ValueError as hata:
        print('HATA: %s' % hata, file=sys.stderr)
        return 2

    cikti = os.path.abspath(args.out)
    os.makedirs(cikti, exist_ok=True)

    sunucu_nesnesi = None
    try:
        if args.base_url:
            temel_url = args.base_url.rstrip('/')
            sunucu_kunyesi = {'kaynak': 'harici', 'komut': None, 'port': None,
                              'gunluk': None, 'hazir_sure_s': None}
            if not sunucu.hazir_mi(temel_url):
                print('HATA: %s%s cevap vermiyor — sunucu çalışıyor mu?'
                      % (temel_url, sunucu.SAGLIK_YOLU), file=sys.stderr)
                return 2
        else:
            gunluk = os.path.join(cikti, 'sunucu.log')
            sunucu_nesnesi = sunucu.UygulamaSunucusu(gunluk_yolu=gunluk)
            print('Sunucu başlatılıyor: %s' % ' '.join(sunucu.komut()))
            sunucu_nesnesi.baslat()
            temel_url = sunucu_nesnesi.temel_url
            sunucu_kunyesi = {
                'kaynak': 'alt_surec', 'komut': sunucu.komut(),
                'port': sunucu_nesnesi.port, 'gunluk': gunluk,
                'hazir_sure_s': sunucu_nesnesi.hazir_sure_s,
            }
            print('Sunucu hazır: %s (%.1f s)'
                  % (temel_url, sunucu_nesnesi.hazir_sure_s or 0.0))

        sayfa_raporlari, tarayici_kunye = tur.turu_kos(
            temel_url, sayfa_tanimlari, cikti,
            basli=args.headed, kanal=args.channel)
    finally:
        if sunucu_nesnesi is not None:
            sunucu_nesnesi.durdur()

    rapor = rapor_olustur(temel_url, sunucu_kunyesi, tarayici_kunye, sayfa_raporlari)
    rapor_yolu = os.path.join(cikti, RAPOR_ADI)
    with open(rapor_yolu, 'w', encoding='utf-8') as dosya:
        json.dump(rapor, dosya, ensure_ascii=False, indent=2)

    ozeti_yaz(rapor)
    print('')
    print('Rapor: %s' % rapor_yolu)
    return denetimler.cikis_kodu(rapor)


if __name__ == '__main__':
    sys.exit(main())
