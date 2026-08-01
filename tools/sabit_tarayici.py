#!/usr/bin/env python3
"""Sabit çıktı yaprağı tarayıcısı — payload anahtarları üstünden.

Neden ayrı bir araç: `tools/wiring_map.py` ölçülecek alanları HTML
ŞABLONUNDAN çıkarır. Şablonda karşılığı olmayan ama uç noktanın okuduğu
anahtarlar (katıda ``propellant_type`` katalog seçiminden türetilir,
hibritte ``plate_thickness`` panel yolundan gelir) hiç denenmez; onlara
bağlı yapraklar gerçekte canlı olsa bile ölçümde "sabit" görünür. Faz 1'de
bu kör nokta 10 kalemde yanlış pozitif üretti.

Bu tarayıcı taban yükün TÜM anahtarlarını sarsar, artı sayfaya özgü ek
anahtarları dener, ve hiç kıpırdamayan yaprakları listeler. Çıktı, bilinen
kusur/meşru listeleriyle karşılaştırılarak "yeni sabit var mı" sorusunu
yanıtlar.

Kullanım:
    PYTHONPATH=. python3 tools/sabit_tarayici.py
    PYTHONPATH=. python3 tools/sabit_tarayici.py --sayfa solid
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

VARSAYILAN_RAPOR = os.path.expanduser(
    '~/HRMA-kurtarma/takim-raporlari/sabit-bulgular.json')
VARSAYILAN_CIKTI = str(ROOT / 'docs' / 'dev' / 'sabit_tarama.json')

#: Şablonda alanı olmayan ama uç noktanın okuduğu anahtarlar.
#: Listeye ekleme yapılırken değerler MERKEZİ kaynaktan alınmalı; buraya
#: elle katalog kopyalamak ikinci tanım açmak olur.
EK_ANAHTARLAR = {
    'hybrid': {
        'plate_thickness': [1.0, 20.0],
        'ambient_temp': [233.15, 313.15],
        'orifice_inlet': ['sharp', 'radiused'],
        'bolt_property_class': ['8.8', '12.9'],
        'vehicle_mass_dry': [25.0, 120.0],
        'vehicle_reference_area_m2': [0.02, 0.2],
        'launch_angle': [60.0, 90.0],
        'wind_speed': [0.0, 20.0],
    },
    'liquid': {
        'film_cooling_percent': [0.0, 8.0],
        'injector_type': ['impinging', 'coaxial'],
        'engine_cycle': ['gas_generator', 'staged_combustion'],
    },
    'solid': {},
}


def yakit_anahtarlari():
    """Katı yakıt kataloğunun anahtarları — TEK kaynaktan okunur."""
    try:
        from hrma.engines.solid_rocket_engine import _PROPELLANT_CATALOG
        return sorted(_PROPELLANT_CATALOG)
    except Exception:
        return []


def taban_yuk(page, wiring_map):
    """Taban yük — formun GERÇEKTEN gönderdiği alan kümesiyle.

    v2.6.26 (Faz 2 dersi): taban yük yalnız ``examples/*.hrma`` dosyasından
    alınıyordu. Örnek proje ise kullanıcının DEĞİŞTİRDİĞİ alanları saklar
    (katıda 21 alan), oysa sayfa "Hesapla"ya basınca 86 alan gönderir.
    Taban yükte olmayan alan hiç sarsılmaz; ona bağlı yapraklar haksız yere
    "sabit" görünür. Katı sayfasında bu tek başına 4 yanlış pozitif üretti
    (insulation_thickness, safety_factor, liner_thickness, two_phase_loss).

    Bu yüzden örnek proje ŞABLON VARSAYILANLARIYLA tamamlanır. Örnekteki
    değerler üstün kalır — örnek, çözüldüğü doğrulanmış bir tasarımdır.
    """
    if page == 'hybrid':
        return dict(wiring_map._layer_b_config()['base'])

    ornek = ROOT / 'examples' / wiring_map.EXAMPLE_FOR[page]
    with ornek.open(encoding='utf-8') as fh:
        proje = json.load(fh)
    base = dict((proje.get('inputs') or {}).get('fields') or {})

    from tests.support import inventory
    for ad, alan in inventory.field_specs_for(page).items():
        if ad in base or alan.kind == 'text':
            continue
        deger = alan.default
        if deger in (None, '') and alan.options:
            deger = list(alan.options)[0]
        if deger in (None, ''):
            continue
        if alan.kind != 'choice':
            try:
                deger = float(deger)
            except (TypeError, ValueError):
                continue
        base[ad] = deger
    return base


def tara(page, client, wiring_map, shake, sessiz):
    """Sayfayı iki ölçümün BİRLEŞİMİYLE tarar.

    (1) wiring_map'in şablon güdümlü sarsımı — her alanı kendi min/max
        bandında ve gerekli dal bağlamıyla dener. Kapsamı geniştir.
    (2) Buradaki payload anahtarı sarsımı — şablonda alanı olmayan
        anahtarlara ulaşır (propellant_type, plate_thickness, ...).

    Yalnız (2) ile ölçmek YANILTIR: ilk sürüm böyleydi ve hibritte 479
    "sabit" buluyordu, oysa şablon güdümlü ölçüm aynı sayfada 209 diyor.
    Zayıf sarsım, canlı yaprağı sabit gösterir. İkisinin birleşimi her iki
    kör noktayı da kapatır.
    """
    ep = wiring_map.PAGES[page]['endpoint']
    base = taban_yuk(page, wiring_map)

    with contextlib.redirect_stdout(sessiz):
        if page == 'hybrid':
            report, *_ = wiring_map.measure_hybrid(client)
        else:
            report, *_ = wiring_map.measure_page(client, page)
    # DİKKAT — burada `report.changed_paths` KULLANILMAZ.
    # O alan yankıları (bir girdinin kendi çıktıdaki kopyası) bilerek eler;
    # amacı "bu girdi ölü mü" sorusudur. Sabit ÇIKTI taraması için yanlış
    # kaynaktır: yankı da bir değişimdir ve yaprağı sabit olmaktan çıkarır.
    # `constant_outputs` ise `ever_changed` üstünden, yankılar DAHİL
    # hesaplanır (tests/support/shake.py:241) — doğru kaynak odur.
    # İlk sürüm changed_paths kullanıyordu ve hibritte 6 canlı yaprağı
    # (ör. .trajectory.vehicle_parameters.drag_coefficient) sabit gösterdi.
    sablon_sabit = set(report.constant_outputs)

    def call(payload):
        with contextlib.redirect_stdout(sessiz):
            r = client.post(ep, json=dict(payload), headers=shake.HEADERS)
        if r.status_code != 200:
            return {}
        try:
            return dict(shake.leaves(r.get_json()))
        except Exception:
            return {}

    taban = call(base)
    if not taban:
        raise SystemExit(f'{page}: taban çağrısı başarısız')

    denemeler = []
    # Şablonun seçim listeleri — string alanları sarsmak için TEK kaynak.
    try:
        from tests.support import inventory
        _specs = inventory.field_specs_for(page)
    except Exception:
        _specs = {}

    for k, v in base.items():
        if isinstance(v, bool) or v in (None, ''):
            continue
        if isinstance(v, (int, float)) and v:
            # ±%40 bazı rejim eşiklerini geçmiyor (ölçüldü: cıvata izin
            # verilen gerilmesi 580 -> 600 MPa için itkiyi 10 kat büyütmek
            # gerekti, ISO 898-1'in d>16 mm dilimine geçmek için). Bu yüzden
            # dar ve geniş bant birlikte denenir.
            for carpan in (1.4, 0.6, 10.0, 0.1):
                denemeler.append((k, v * carpan))
        elif isinstance(v, str):
            # Seçim alanları sayısal döngüye takılmıyordu; chamber_material
            # ve fuel_type hiç denenmediği için onlara bağlı yapraklar
            # (malzeme emniyet katsayısı, elemental bileşim) sabit görünüyordu.
            alan = _specs.get(k)
            secenekler = list(getattr(alan, 'options', None) or ())
            for secenek in secenekler:
                if str(secenek) != str(v):
                    denemeler.append((k, secenek))
    ek = dict(EK_ANAHTARLAR.get(page, {}))
    if page == 'solid':
        anahtarlar = yakit_anahtarlari()
        if len(anahtarlar) > 1:
            ek['propellant_type'] = anahtarlar
    for k, degerler in ek.items():
        for v in degerler:
            denemeler.append((k, v))

    oynayan = set()
    basarisiz = 0
    for k, v in denemeler:
        d = call({**base, k: v})
        if not d:
            basarisiz += 1
            continue
        oynayan.update(shake.differing_paths(taban, d))

    # Yalnız SAYISAL yapraklar aranır; metin/etiket alanları doğal olarak
    # sabittir ve onları "kusur" saymak gürültü üretir.
    # Sabit = ŞABLON ölçümünde de sabit VE payload sarsımında da kıpırdamayan.
    # İki ölçümün KESİŞİMİ alınır: biri diğerinin göremediğini görüyor.
    sabit = []
    for yol, deger in taban.items():
        if isinstance(deger, bool) or not isinstance(deger, (int, float)):
            continue
        if yol in oynayan:
            continue
        if sablon_sabit and yol not in sablon_sabit:
            # Şablon ölçümü bu yaprağı canlı görmüş (yankı dahil) — sabit değil.
            continue
        sabit.append(yol)

    return {
        'sayfa': page,
        'endpoint': ep,
        'deneme_sayisi': len(denemeler),
        'basarisiz_deneme': basarisiz,
        'taban_yaprak': len(taban),
        'sayisal_yaprak': sum(1 for v in taban.values()
                              if isinstance(v, (int, float))
                              and not isinstance(v, bool)),
        'oynayan_yaprak': len(oynayan),
        'sabit_yapraklar': sorted(sabit),
    }


def bilinen_yollar(rapor_yolu):
    """Takım raporundaki kalemlerin yolları (kusur + meşru)."""
    if not os.path.exists(rapor_yolu):
        return set(), set()
    with open(rapor_yolu, encoding='utf-8') as f:
        gruplar = json.load(f)
    kusur, mesru = set(), set()
    for grup in gruplar:
        for k in grup.get('kalemler', []):
            yol = k.get('yol') or ''
            if not yol.startswith('.'):
                continue
            (kusur if k.get('sinif') == 'KUSUR' else mesru).add(yol)
    return kusur, mesru


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sayfa', choices=['hybrid', 'liquid', 'solid', 'all'],
                    default='all')
    ap.add_argument('--rapor', default=VARSAYILAN_RAPOR)
    ap.add_argument('--cikti', default=VARSAYILAN_CIKTI)
    args = ap.parse_args()

    import wiring_map
    from tests.support import shake
    from hrma.app import app

    client = app.test_client()
    sessiz = io.StringIO()
    sayfalar = (['hybrid', 'liquid', 'solid'] if args.sayfa == 'all'
                else [args.sayfa])

    kusur, mesru = bilinen_yollar(args.rapor)
    sonuc = {'sayfalar': [], 'yeni_sabitler': []}

    for page in sayfalar:
        print(f'{page} taranıyor...', file=sys.stderr)
        r = tara(page, client, wiring_map, shake, sessiz)
        yeni = [y for y in r['sabit_yapraklar']
                if y not in kusur and y not in mesru]
        r['bilinen_kusur'] = sum(1 for y in r['sabit_yapraklar'] if y in kusur)
        r['bilinen_mesru'] = sum(1 for y in r['sabit_yapraklar'] if y in mesru)
        r['yeni'] = yeni
        sonuc['sayfalar'].append(r)
        sonuc['yeni_sabitler'].extend((page, y) for y in yeni)

        print(f"  {page}: {r['deneme_sayisi']} sarsım "
              f"({r['basarisiz_deneme']} başarısız), "
              f"{r['sayisal_yaprak']} sayısal yaprak, "
              f"{len(r['sabit_yapraklar'])} sabit "
              f"[bilinen kusur {r['bilinen_kusur']}, "
              f"bilinen meşru {r['bilinen_mesru']}, YENİ {len(yeni)}]",
              file=sys.stderr)

    print()
    print('SABİT YAPRAK TARAMASI')
    for r in sonuc['sayfalar']:
        print(f"  {r['sayfa']:8s} sabit={len(r['sabit_yapraklar']):4d}  "
              f"yeni={len(r['yeni']):4d}")
    toplam_yeni = len(sonuc['yeni_sabitler'])
    print(f"\nTakım raporunda GEÇMEYEN sabit yaprak: {toplam_yeni}")

    os.makedirs(os.path.dirname(args.cikti), exist_ok=True)
    with open(args.cikti, 'w', encoding='utf-8') as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=2)
    print(f'Yazıldı: {args.cikti}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
