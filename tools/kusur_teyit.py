#!/usr/bin/env python3
"""138 kusurun GERÇEKTEN kapandığını bağımsız ölçümle teyit eder.

Neden ayrı bir araç: kusurları kapatan ajanlar kendi işlerini raporluyor.
"Bağladım" beyanı kanıt değildir. Bu araç rapora hiç bakmadan, uygulamanın
kendi HTTP yanıtından ölçer: her form alanı sarsılır, hangi çıktı yapraklarının
HİÇ kıpırdamadığı çıkarılır (``shake.ShakeReport.constant_outputs``), sonra
138 kusurun yolu bu sabit kümede aranır.

Sonuç sınıfları:

``KAPALI``      Yaprak artık en az bir girdiyle oynuyor — kusur kapanmış.
``HALA_SABIT``  Yaprak hâlâ hiçbir girdiye tepki vermiyor — kusur açık.
``YAPRAK_YOK``  Yol yanıtta bulunamadı. Kalem bilinçli kaldırıldıysa
                (uydurma blok söküldü, NOT_MODELLED yapıldı) bu MEŞRU bir
                kapanıştır; ama otomatik "kapalı" sayılmaz, göze bakar.
``ELLE``        Kalemin ``yol``'u bir JSON yaprağı değil (alan adı, uç nokta
                tarifi, "dalın tamamı" gibi). Mekanik olarak ölçülemez.

Kullanım:
    PYTHONPATH=. python3 tools/kusur_teyit.py
    PYTHONPATH=. python3 tools/kusur_teyit.py --sayfa liquid
    PYTHONPATH=. python3 tools/kusur_teyit.py --cikti docs/dev/kusur_teyit.json

Ölçüm üç sayfa için ~2 dakika sürer (her alan için gerçek bir hesap koşar).
Çıkış kodu: açık kusur kalmadıysa 0, kaldıysa 2.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

VARSAYILAN_RAPOR = os.path.expanduser(
    '~/HRMA-kurtarma/takim-raporlari/sabit-bulgular.json')
VARSAYILAN_CIKTI = str(ROOT / 'docs' / 'dev' / 'kusur_teyit.json')

#: Rapor grubu -> ölçülecek sayfa. Yankı grubu üç sayfaya da bakar.
GRUP_SAYFA = {
    'hibrit': 'hybrid',
    'kati': 'solid',
    'sıvı': 'liquid',
    'sivi': 'liquid',
}


def sayfa_of(grup: str) -> str | None:
    """Rapor grubunun adından sayfayı çıkarır."""
    g = (grup or '').lower()
    for anahtar, sayfa in GRUP_SAYFA.items():
        if g.startswith(anahtar):
            return sayfa
    return None  # YANKI grubu ve tanınmayanlar: üç sayfada da aranır


def kusurlari_yukle(rapor_yolu: str) -> list[dict]:
    with open(rapor_yolu, encoding='utf-8') as f:
        gruplar = json.load(f)
    kusurlar = []
    for grup in gruplar:
        for kalem in grup.get('kalemler', []):
            if kalem.get('sinif') != 'KUSUR':
                continue
            kayit = dict(kalem)
            kayit['_grup'] = grup.get('grup', '')
            kayit['_sayfa'] = sayfa_of(kayit['_grup'])
            kusurlar.append(kayit)
    return kusurlar


def ek_anahtar_sarsimi(client, sayfa: str, anahtar: str,
                       degerler: list) -> set[str]:
    """Şablon alanı OLMAYAN bir payload anahtarını sarsar.

    Neden gerekli: sarsım altyapısı ölçülecek alanları HTML şablonundan
    çıkarır. Şablonda karşılığı olmayan ama uç noktanın okuduğu anahtarlar
    (ör. katı sayfasında ``propellant_type`` — katalog satırı seçiminden
    türetiliyor, ayrı bir form alanı değil) hiç denenmez. Bu alanlara bağlanan
    yapraklar, gerçekte canlı olsalar bile ölçümde "sabit" görünür.

    Bu yüzden teyit aracı onları kendisi sarsar. Aksi hâlde teyit YALAN söyler:
    katı motorun yakıt kimliğine bağlanan 11 kalem haksız yere "hâlâ sabit"
    çıkardı.
    """
    import wiring_map
    from tests.support import shake

    endpoint = wiring_map.PAGES[sayfa]['endpoint']
    ornek = ROOT / 'examples' / wiring_map.EXAMPLE_FOR[sayfa]
    with ornek.open(encoding='utf-8') as fh:
        proje = json.load(fh)
    base = dict((proje.get('inputs') or {}).get('fields') or {})

    def call(payload):
        # differing_paths DÜZ yaprak sözlüğü bekler (yol -> değer), ham JSON
        # gövdesi değil; shake.run da aynı şekilde düzleştiriyor.
        r = client.post(endpoint, json=dict(payload), headers=shake.HEADERS)
        if r.status_code != 200:
            return {}
        try:
            return dict(shake.leaves(r.get_json()))
        except Exception:
            return {}

    taban = call(base)
    if not taban:
        return set()

    oynayan: set[str] = set()
    for d in degerler:
        govde = call({**base, anahtar: d})
        if govde:
            oynayan.update(shake.differing_paths(taban, govde))
    return oynayan


def yakit_anahtarlari() -> list:
    """Katı motor yakıt kataloğunun anahtarları — TEK kaynaktan.

    Listeyi buraya elle yazmak kataloğu ikinci kez tanımlamak olurdu.
    """
    try:
        from hrma.engines.solid_rocket_engine import _PROPELLANT_CATALOG
        return sorted(_PROPELLANT_CATALOG)
    except Exception:
        return []


def olc(sayfalar: list[str]) -> dict[str, dict]:
    """Her sayfa için sarsım ölçümünü koşar.

    Döner: sayfa -> {'sabit': set(yol), 'tum_yapraklar': set(yol)}
    """
    import wiring_map
    from hrma.app import app

    client = app.test_client()
    sonuc: dict[str, dict] = {}
    for sayfa in sayfalar:
        if sayfa == 'hybrid':
            report, *_ = wiring_map.measure_hybrid(client)
        else:
            report, *_ = wiring_map.measure_page(client, sayfa)

        # Ölçümün gördüğü yaprakların tamamı, raporun kendisinden:
        #   sabit kalanlar  U  en az bir alanla oynayanlar
        # Fazladan HTTP çağrısı yapmaya gerek yok; ayrıca taban yükü burada
        # yeniden kurmak (measure_page onu döndürmüyor) mantığı ikinci kez
        # yazmak olurdu — magic number/ikinci tanım yasağının aynısı.
        sabit = set(report.constant_outputs)
        oynayan: set[str] = set()
        for _alan, yollar in (report.changed_paths or {}).items():
            oynayan.update(yollar)

        # Şablonda karşılığı olmayan payload anahtarları ayrıca sarsılır.
        ek_not = ''
        if sayfa == 'solid':
            anahtarlar = yakit_anahtarlari()
            if len(anahtarlar) > 1:
                ek = ek_anahtar_sarsimi(client, sayfa, 'propellant_type',
                                        anahtarlar)
                if ek:
                    oynayan |= ek
                    sabit -= ek
                    ek_not = (f'; propellant_type sarsımı {len(ek)} yaprağı '
                              f'sabit kümesinden çıkardı')

        sonuc[sayfa] = {
            'sabit': sabit,
            'tum_yapraklar': sabit | oynayan,
            'ozet': report.summary() + ek_not,
        }
    return sonuc


def teyit_et(kusurlar: list[dict], olcum: dict[str, dict]) -> list[dict]:
    satirlar = []
    for k in kusurlar:
        yol = k.get('yol') or ''
        # JSON yaprağı mı, yoksa serbest tarif mi?
        if not yol.startswith('.'):
            satirlar.append({**_temel(k), 'sonuc': 'ELLE',
                             'neden': 'yol bir JSON yaprağı değil'})
            continue

        sayfalar = ([k['_sayfa']] if k.get('_sayfa') in olcum
                    else list(olcum))
        sabit_mi = False
        var_mi = False
        nerede_sabit = []
        for s in sayfalar:
            if yol in olcum[s]['tum_yapraklar']:
                var_mi = True
            if yol in olcum[s]['sabit']:
                sabit_mi = True
                nerede_sabit.append(s)

        if sabit_mi:
            satirlar.append({**_temel(k), 'sonuc': 'HALA_SABIT',
                             'neden': 'sayfa(lar): ' + ', '.join(nerede_sabit)})
        elif var_mi:
            satirlar.append({**_temel(k), 'sonuc': 'KAPALI',
                             'neden': 'yaprak üretiliyor ve girdiyle oynuyor'})
        else:
            satirlar.append({**_temel(k), 'sonuc': 'YAPRAK_YOK',
                             'neden': 'yol yanıtta yok — kaldırılmış olabilir, '
                                      'göze bakar'})
    return satirlar


def _temel(k: dict) -> dict:
    return {
        'yol': k.get('yol'),
        'eski_deger': k.get('deger'),
        'grup': k.get('_grup'),
        'sayfa': k.get('_sayfa'),
        'guven': k.get('guven'),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rapor', default=VARSAYILAN_RAPOR)
    ap.add_argument('--cikti', default=VARSAYILAN_CIKTI)
    ap.add_argument('--sayfa', choices=['hybrid', 'liquid', 'solid', 'all'],
                    default='all')
    args = ap.parse_args()

    if not os.path.exists(args.rapor):
        print(f'Rapor bulunamadı: {args.rapor}', file=sys.stderr)
        return 1

    kusurlar = kusurlari_yukle(args.rapor)
    sayfalar = (['hybrid', 'liquid', 'solid'] if args.sayfa == 'all'
                else [args.sayfa])

    print(f'{len(kusurlar)} kusur okundu. Ölçüm başlıyor '
          f'({len(sayfalar)} sayfa, her alan için gerçek hesap)...',
          file=sys.stderr)
    olcum = olc(sayfalar)
    for s, v in olcum.items():
        print(f'  {s}: {v["ozet"]}', file=sys.stderr)

    satirlar = teyit_et(kusurlar, olcum)

    sayim: dict[str, int] = {}
    for s in satirlar:
        sayim[s['sonuc']] = sayim.get(s['sonuc'], 0) + 1

    print()
    print('TEYİT SONUCU')
    for ad in ('KAPALI', 'HALA_SABIT', 'YAPRAK_YOK', 'ELLE'):
        print(f'  {ad:12s} {sayim.get(ad, 0):3d}')

    acik = [s for s in satirlar if s['sonuc'] == 'HALA_SABIT']
    if acik:
        print(f'\nHÂLÂ SABİT ({len(acik)}):')
        for s in acik:
            print(f'  {s["yol"]}')
            print(f'      eski değer: {str(s["eski_deger"])[:70]}  |  {s["neden"]}')

    gozle = [s for s in satirlar if s['sonuc'] in ('YAPRAK_YOK', 'ELLE')]
    if gozle:
        print(f'\nGÖZLE TEYİT GEREKENLER ({len(gozle)}):')
        for s in gozle:
            print(f'  [{s["sonuc"]}] {s["yol"][:78]}')

    os.makedirs(os.path.dirname(args.cikti), exist_ok=True)
    with open(args.cikti, 'w', encoding='utf-8') as f:
        json.dump({'sayim': sayim, 'satirlar': satirlar}, f,
                  ensure_ascii=False, indent=2)
    print(f'\nYazıldı: {args.cikti}')

    return 2 if acik else 0


if __name__ == '__main__':
    sys.exit(main())
