#!/usr/bin/env python3
"""Geliştirici bağlama haritası — "bu sayı nereden geliyor?" sorusunun cevabı.

Bu araç HRMA'nın kullanıcı arayüzünden çıktı yapraklarına kadar olan
bağlantıları ÖLÇEREK çıkarır ve tek dosyalık bir HTML olarak yazar.

Neden gerekli
-------------
Bu kod tabanındaki ciddi kusurların neredeyse tamamı aynı sınıftan: iki parça
tek başına doğru, aralarındaki sözleşme yanlış. Bu sınıfı kovalarken en çok
zamanı iki soru yiyor:

    "Kullanıcının girdiği bu alan nereye gidiyor?"
    "Ekrandaki bu sayıyı hangi girdiler belirliyor?"

Kod okuyarak cevaplamak yarım saat sürüyor, çünkü zincir şablon -> toplayıcı
-> HTTP -> çözücü -> yanıt sözlüğü boyunca dört ayrı katmandan geçiyor ve
arada isim değişiyor (ör. ``pressure_drop_percent`` yüzde olarak toplanıp
``pressure_drop`` olarak bar cinsinden gidiyor).

Harita bu iki soruyu saniyeye indirir.

Neden çürümez
-------------
Harita elle yazılmaz. İki ölçümden üretilir:

* **Katman A** (``tests/support/inventory.py``): şablondaki her form alanı
  hangi toplayıcıda okunuyor.
* **Katman B** (``tests/support/shake.py``): her payload anahtarı sarsıldığında
  yanıtın hangi yaprakları değişiyor.
* **Uç kapsamı** (``tests/support/uc_katalogu.py``, ÖH D23 · defter P10B4-16):
  üç motor sayfasının ötesindeki POST uçları. Harita v2.6.27'ye kadar ürünün
  80 POST ucunun 3'ünü ölçüyordu; merkezî uç-yükü kataloğu kurulunca ``--uclar``
  ile 66'sı ölçülür, kalan 14'ü ADIYLA ve GEREKÇESİYLE listelenir.

Yani harita, kodun o anki GERÇEK davranışıdır. Kod değişince yeniden üretilir
ve yeni gerçeği gösterir. Elle tutulan bir mimari şeması gibi eskimez.

Kullanım
--------
    python3 tools/wiring_map.py                  # üç motor tipi
    python3 tools/wiring_map.py --page hybrid    # tek sayfa (hızlı)
    python3 tools/wiring_map.py -o /tmp/map.html
    python3 tools/wiring_map.py --uclar          # + BÜTÜN POST uçları
    python3 tools/wiring_map.py --yalniz-uclar   # yalnız uç kapsamı
    python3 tools/wiring_map.py --yalniz-uclar --uclar-sinir 6   # kuru koşum

Ölçüm hibritte ~40 sn, üç sayfa birlikte birkaç dakika sürer (her alan için
gerçek bir hesap koşulur). Çıktı varsayılan olarak
``docs/dev/wiring_map.html``.

DÜRÜSTLÜK NOTU: harita yalnız ÖLÇÜLENİ gösterir. Ölçülemeyen alan "ölü" diye
işaretlenmez, "ölçülemedi" diye işaretlenir — ikisi farklı şeydir ve
karıştırmak tam olarak bu araçla kovaladığımız hata sınıfıdır.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.support import inventory, shake, uc_katalogu  # noqa: E402


# ---------------------------------------------------------------------------
# Sayfa tanımları — taban motor, bağlam ve isim eşlemeleri
#
# Bu tablolar Katman B bekçisiyle (tests/test_field_wiring_layer_b.py) AYNI
# bilgiyi taşır. Tek kaynak olması için oradan içe aktarılır; bekçi kurulumu
# değişirse harita da onunla birlikte değişir.
# ---------------------------------------------------------------------------

def _layer_b_config():
    """Katman B bekçisinin taban yükü ve bağlamlarını ödünç alır."""
    import importlib
    mod = importlib.import_module('tests.test_field_wiring_layer_b')
    return {
        'base': mod.HYBRID_BASE,
        'contexts': mod.HYBRID_CONTEXTS,
        'rename': mod.TEMPLATE_TO_PAYLOAD,
        'not_in_calculate': mod.NOT_IN_CALCULATE,
        'payload_range': mod.PAYLOAD_RANGE,
        'declared_unused': mod.DECLARED_UNUSED_IN_APP,
    }


PAGES = {
    'hybrid': {'endpoint': '/calculate', 'template': 'advanced.html'},
    'solid': {'endpoint': '/calculate_solid', 'template': 'solid.html'},
    'liquid': {'endpoint': '/calculate_liquid', 'template': 'liquid.html'},
}

# ---------------------------------------------------------------------------
# ÖH D27 a4 · P11S1-05 — KAPSAM SINIRI BAŞLIKTA BEYAN EDİLİR.
#
# ÖLÇÜLDÜ (docs/scofield/raw/OH/D27/arayuz/a4/once.json,
# `p11s1_05_pages_uc_sayisi` = 3, `p11s1_05_kapsam_beyani` = 0): alan
# haritası YALNIZ yukarıdaki üç `/calculate*` ucunu tarıyor. P11 taraması
# ürünün 36 POST ucundan 1'ini ve 23 analiz güvertesi panelinden 0'ını
# gördüğünü ölçtü — güverte panelleri kendi uçlarına (`/api/...`) konuşur ve
# bu tablonun dışındadır. Sınır kendi başına bir kusur DEĞİL (harita alan →
# yaprak bağlaması için kuruldu), ama beyan edilmemesi kusurdur: başlığı
# "HRMA bağlama haritası" olan, hiçbir yerinde sınırını söylemeyen bir belge
# okuyucuya ÜRÜNÜN TAMAMINI gördüğünü ima eder. Bu aracın kovaladığı hata
# sınıfının ta kendisi (dosyanın kendi DÜRÜSTLÜK NOTU'na bakınız).
#
# Sayı elle yazılmaz: kapsanan uçlar PAGES'ten, kapsanmayanların sayısı
# uç kataloğundan okunur (katalog yoksa cümle sayısız kurulur).
# ---------------------------------------------------------------------------
KAPSAM_SINIRI_BASLIK = 'KAPSAM SINIRI'


def kapsam_beyani() -> str:
    """Haritanın neyi kapsayıp neyi kapsamadığını tek cümlede söyler."""
    kapsanan = sorted(v['endpoint'] for v in PAGES.values())
    try:
        # Katalogun kendi kayıt tablosu — sayı burada ELLE yazılmaz.
        toplam = len(uc_katalogu.kayitlar())
    except Exception:
        toplam = None
    disarida = ('' if toplam is None
                else ' Ürünün ölçülen %d POST ucundan %d\u0027i kapsanıyor;'
                     ' kalan %d uç (analiz güvertesi panellerinin'
                     ' /api/... uçları dâhil) bu haritada YOKTUR.'
                     % (toplam, len(kapsanan), toplam - len(kapsanan)))
    return ('%s: bu harita yalnız %s uçlarının şablon alanlarını sarsar.%s'
            ' Uç kapsamı için: python3 tools/wiring_map.py --uclar'
            % (KAPSAM_SINIRI_BASLIK, ', '.join(kapsanan), disarida))

#: ÖH D20 · P10B4-06 (Fable-D17 ŞART'ı) — SÜPÜRME KARARI ÖLÇÜMLE VERİLDİ.
#:
#: Ölçüm (``docs/scofield/raw/OH/D20/bekci-cevirisi/a1/
#: once_supurme_maliyeti.json``, bu makinede, tek çekirdek bütçesiyle):
#:
#: * /calculate çağrısı = **0,93 sn** (üç koşumun ortancası);
#: * hibrit ``fuel_type`` 11 seçenek → 10 ek çağrı: **ÖLÇÜLEN 16,25 sn**
#:   (aynı JSON, ``fuel_type.supurme_sn``) ve dördü (carbon, al2o3,
#:   mixture, custom) HTTP **400** veriyor;
#: * TAM süpürme (üç sayfanın 39 seçim alanı) = **124 ek çağrı**;
#:   ortanca çağrı maliyetiyle projeksiyon ≈ 116 sn, ÖLÇÜLEN süpürme
#:   hızıyla (1,625 sn/çağrı) ≈ **202 sn** (hibrit 38 · katı 24 · sıvı 62).
#:
#: ÖH D26 · defter **OH-D25-05** [24] — DÜZELTME. Bu blok önce "10 ek
#: çağrı = 9,3 sn" diyordu; 9,3 bir PROJEKSİYONDU (0,9335 ortanca × 10),
#: ölçülen değer ise 16,25 sn'dir, yani gerçek maliyet projeksiyonun
#: **1,74 katı** (süpürme çağrıları taban çağrıdan pahalı: her biri farklı
#: yakıtla tam çözüm koşturuyor, ortanca çağrının önbellek avantajı yok).
#: Kararı değiştirmez, ama rakam artık ölçülen rakamdır.
#:
#: Aynı JSON'daki 1 alanlık fark da adlandırıldı: tam süpürme
#: projeksiyonu hibrit için **13** seçim alanı sayarken canlı haritanın
#: kapsam beyanı **12** yazıyor. Fark ``injector_type``tır — süpürme spec
#: kümesinde var, kapsam beyanında yok. Süpürme kapsamı ile beyan kapsamı
#: aynı kümeden türetilmediği sürece bu fark durur; adı burada dursun.
#:
#: KARAR: tam süpürme her koşuda AÇILMAZ (ölçülen hızla ~202 sn, haritanın
#: kendi ölçümüne kıyasla küçük değil), ``--supurme`` ile açılır. Kırık
#: seçeneği ÖLÇÜLMÜŞ alanlar ise her koşuda süpürülür — 16,25 sn
#: karşılığında "canlı" hükmünün yalan olduğu tek yer görünür kalır.
#: Kapsam BEYANI (1/N denendi) süpürme kapalıyken de yayımlanır ve
#: maliyeti sıfırdır.
SUPURULEN_ALANLAR: Dict[str, Tuple[str, ...]] = {
    'hybrid': ('fuel_type',),
    'solid': (),
    'liquid': (),
}


# ---------------------------------------------------------------------------
# Katı ve sıvı için taban motor + bağlam
#
# Taban yükler ``examples/*.hrma`` içindeki GERÇEK örnek projelerden alınır —
# elle uydurulmuş bir motor değil, uygulamanın kendi kaydetme yolundan geçmiş,
# hesaplandığı doğrulanmış tasarımlar. Böylece harita "bu motor gerçekten
# çözülüyor mu" sorusunu da dolaylı olarak yanıtlar.
# ---------------------------------------------------------------------------

EXAMPLE_FOR = {
    'solid': 'Example Solid KNDX BATES 75mm.hrma',
    'liquid': 'Example Liquid LOX-RP1 25kN.hrma',
}

#: Yalnız kendi dalında canlı olan alanlar için refakat değerleri.
#: Bunlar olmadan alan YALANCI ÖLÜ görünür (dal kurulmadığı için).
CONTEXTS = {
    'solid': {
        # Grain tipine özgü alanlar kendi grain tipiyle ölçülür
        'star_points': {'grain_type': 'star', 'star_points': 6},
        'star_inner_diameter': {'grain_type': 'star', 'star_points': 6,
                                'star_inner_diameter': 20},
        'star_outer_diameter': {'grain_type': 'star', 'star_points': 6,
                                'star_outer_diameter': 55},
        'slot_width': {'grain_type': 'slotted', 'slot_width': 8},
        'slot_depth': {'grain_type': 'slotted', 'slot_depth': 12},
        'fin_count': {'grain_type': 'finocyl', 'fin_count': 6},
        'fin_height': {'grain_type': 'finocyl', 'fin_height': 12},
        'fin_width': {'grain_type': 'finocyl', 'fin_width': 5},
        # slot_count yalnız 'slotted' grain'de anlamlı; kardeşleri (slot_width,
        # slot_depth) buradaydı ama kendisi unutulmuştu ve haritada ÖLÜ
        # görünüyordu. Dal kurulmadan ölçülen alan yalancı ölü verir.
        'slot_count': {'grain_type': 'slotted', 'slot_count': 4},
        # star_radius / star_fillet yıldız grain'e, fin_length finocyl'e
        # özgüdür. Kardeşleri (star_points, fin_count...) buradaydı ama bu
        # üçü unutulmuştu ve dal kurulmadığı için ÖLÜ görünüyorlardı —
        # star_radius'un motorda _override_val kaydı bile var.
        #
        # ÖH D15 / harita H3 — REFAKAT DEĞERİ BANDIN İÇİNDE OLMALI.
        # Dal kurulmuştu ama alanlar HÂLÂ ölü görünüyordu; sebep ikinci bir
        # yalancı-ölü kaynağıydı: buradaki refakat değeri motorun GEOMETRİK
        # KIRPMA sınırının ÜSTÜNDEYDİ. Katı örnek motor Ø75 mm dış / Ø32 mm
        # çekirdek olduğundan _radial_slot_params derinliği
        # max_depth_fraction·(r_dış − r_port) ile kırpar. ÖLÇÜLDÜ
        # (/calculate_solid, örnek proje tabanı):
        #   star_radius  = 3 / 5 / 8 / 10 / 12 / 15 mm -> derinlik aynen,
        #       ortalama itki 1030,2 / 959,8 / 909,2 / 892,1 / 875,5 / 850,7 N
        #   star_radius  = 18 / 27 / 40 mm -> ÜÇÜ DE 17,20 mm'ye kırpılıyor,
        #       yanıt BİT-AYNI (clipped: ['star_radius'])
        #   fin_length   = 3 / 5 / 8 / 10 / 12 / 15 mm -> derinlik aynen,
        #       ortalama itki 1092,6 / 1085,0 / 1082,5 / 1081,7 / 1052,7 /
        #       1021,9 N
        #   fin_length   = 25 / 37,5 mm -> ikisi de 18,275 mm'ye kırpılıyor,
        #       yanıt BİT-AYNI (clipped: ['fin_length'])
        # Eski refakat değerleri 18 ve 25 idi; sarsım onları 1,5 katına
        # (27 ve 37,5) çıkarıyor ve İKİ UÇ DA kırpma sınırına oturduğu için
        # hiçbir yaprak kıpırdamıyordu. Alan ölü değildi, ÖLÇÜM noktası
        # bandın dışındaydı — kırpma da sessiz değil, yanıtta `clipped`
        # olarak beyan ediliyor.
        # Yeni değer 8 mm: sarsım 12 mm'ye çıkar, ikisi de kırpma sınırının
        # (17,20 / 18,275 mm) ALTINDA kalır ve alan gerçek etkisiyle ölçülür.
        'star_radius': {'grain_type': 'star', 'star_points': 6,
                        'star_radius': 8},
        'star_fillet': {'grain_type': 'star', 'star_points': 6,
                        'star_fillet': 3},
        'fin_length': {'grain_type': 'finocyl', 'fin_count': 6,
                       'fin_length': 8},
        # v2.6.26 — kapak cıvatası ÖLÇÜSÜ ve SINIFI yalnız cıvata SAYISI
        # verildiğinde anlamlıdır: sayı boşsa çözücü bağlantıyı bilinçli
        # olarak 'not_sized' bırakır ve hiçbir yaprak oynamaz. Dal
        # kurulmadan ölçülünce ikisi de YALANCI ÖLÜ görünüyordu.
        'closure_bolt_size': {'closure_bolt_count': 6,
                              'closure_bolt_size': 'M10'},
        'closure_bolt_class': {'closure_bolt_count': 6,
                               'closure_bolt_class': '12.9'},
    },
    'liquid': {
        # Çevrime özgü alanlar kendi çevrimiyle ölçülür: basınç beslemeli
        # tasarımda turbopompa alanlarının etkisi olmaması DOĞRUDUR.
        'turbopump_efficiency': {'engine_cycle': 'gas_generator',
                                 'turbopump_efficiency': 75},
        'generator_gas_temp': {'engine_cycle': 'gas_generator',
                               'generator_gas_temp': 900},
        'turbine_expansion_ratio': {'engine_cycle': 'gas_generator',
                                    'turbine_expansion_ratio': 4},
        'turbine_inlet_pressure': {'engine_cycle': 'gas_generator',
                                   'turbine_inlet_pressure': 4.05},
        # Ön yakıcı tipi yalnız ön yakıcısı OLAN çevrimlerde anlamlıdır;
        # basınç beslemeli taban motorda etkisiz olması DOĞRUDUR. Dal
        # kurulmadığı için haritada ölü görünüyordu.
        'preburner_type': {'engine_cycle': 'staged_combustion',
                           'preburner_type': 'fuel_rich'},
        # Hazne çapı artık OPSİYONEL (boşsa daralma oranından türetilir), bu
        # yüzden örnek projede yok ve taban yükte görünmüyor. Ölçüm için bir
        # değer verilir; verildiğinde çap daralma oranını ezmeli ve
        # warn.liquid.chamber_diameter_overrides_contraction üretmelidir.
        'chamber_diameter': {'chamber_diameter': 150},
    },
}

#: Şablon adı ile payload anahtarının ayrıştığı alanlar.
RENAME = {
    'solid': {},
    'liquid': {},
}

#: Ayrı uç noktaya giden ya da istemcide kalan alanlar (Katman B'nin konusu
#: değil; Katman A onları kendi gerekçeli listesinde tutar).
NOT_IN_ENDPOINT = {
    'solid': {
        'traj_burn_time', 'traj_drag_coeff', 'traj_final_mass',
        'traj_initial_mass', 'traj_ref_area', 'propellant_name',
    },
    'liquid': {
        'traj_alt_start', 'traj_alt_end', 'traj_points',
    },
}


def measure_page(client, page: str, probe_all_options: bool = False):
    """Katı/sıvı sayfası için A+B ölçümünü koşar."""
    example = ROOT / 'examples' / EXAMPLE_FOR[page]
    if not example.is_file():
        raise SystemExit(f'örnek proje bulunamadı: {example}')
    with example.open(encoding='utf-8') as fh:
        project = json.load(fh)
    base = dict((project.get('inputs') or {}).get('fields') or {})
    if not base:
        raise SystemExit(f'{example} içinde inputs.fields yok')

    template_specs = inventory.field_specs_for(page)

    # Taban yükü ŞABLON VARSAYILANLARIYLA tamamla — örnek projedeki değerler
    # üstün kalır.
    #
    # Neden: örnek proje yalnız kullanıcının değiştirdiği alanları saklar (katı
    # örnekte 21 alan), oysa kullanıcı sayfayı açıp "Hesapla"ya bastığında form
    # 70+ alanı VARSAYILANLARIYLA gönderir. Taban yük eksik olunca sarsım
    # alanın taban değerini bilemiyordu ve seçim listelerinde ilk seçeneği
    # deniyordu (shake.perturb: current=None -> options[0]). O seçenek çoğu
    # zaman motorun varsayılanıyla AYNI olduğu için "değişmedi" görünüyor ve
    # alan YALANCI ÖLÜ sayılıyordu — nozzle_material tam olarak böyleydi:
    # HTTP yanıtı graphite/tungsten için farklı sonuç verdiği hâlde harita
    # alanı ölü gösteriyordu.
    # YALNIZ seçim listeleri (choice) tamamlanır. Sayısal alanlara varsayılan
    # eklemek taban MOTORU değiştiriyor: örneğin throat_diameter şablonda 15
    # diye duruyor, taban yüke eklenince çözücü onu kullanıcı ezmesi sanıyor
    # ve tüm taban geometri kayıyor (ölçüldü: 48 canlı -> 38, 9 alan
    # ölçülemez oldu). Seçim listelerinde ise sorun tersi: taban değer
    # bilinmezse sarsım ilk seçeneği dener, o da genelde motorun varsayılanı
    # olduğu için "değişmedi" çıkar.
    for _ad, _f in template_specs.items():
        if _ad in base or _f.kind != 'choice':
            continue
        # Şablonda 'selected' yoksa tarayıcı ilk seçeneği gösterir; taban yük
        # de onu taşımalı. (nozzle_material tam olarak böyleydi: varsayılanı
        # boş olduğu için taban yüke hiç girmiyor, sarsım da ilk seçeneği
        # deneyip motorun varsayılanıyla aynı değeri gönderiyordu.)
        _deger = _f.default or (list(_f.options)[0] if _f.options else None)
        if _deger in (None, ''):
            continue
        base[_ad] = _deger
    inv = inventory.build(page)
    contexts = CONTEXTS.get(page, {})
    rename = RENAME.get(page, {})
    skip = NOT_IN_ENDPOINT.get(page, set())

    specs = []
    seen = set()
    template_of_payload: Dict[str, str] = {}
    for name in sorted(inv.collected_fields & set(template_specs)):
        payload_key = rename.get(name, name)
        if payload_key in skip or payload_key in seen:
            continue
        field = template_specs[name]
        if field.kind == 'text':
            continue
        seen.add(payload_key)
        template_of_payload[payload_key] = name
        specs.append(shake.FieldSpec(
            name=payload_key, kind=field.kind,
            lo=field.minimum, hi=field.maximum,
            options=tuple(field.options or ()),
            context=contexts.get(payload_key, {}),
        ))

    # Motorun KENDİ beyanını ölçüme taşı. Bunsuz, "bu alanı kullanmıyorum ve
    # bunu söylüyorum" diyen alanlar haritada ÖLÜ görünüyordu: sıvı motorun
    # unwired_inputs() beyanındaki 14 alan (informational + geçici rejimde
    # modellenmeyenler) haksız yere ölü sayılıyordu. Hibrit yolu bu listeyi
    # zaten geçiriyordu; katı/sıvı yolu geçirmiyordu.
    #
    # Liste STATİK değil, motorun taban koşudaki yanıtından okunur: beyan
    # değişirse harita kendiliğinden uyar. shake.run beyan edilmiş ama
    # gerçekte çıktıyı oynatan alanı ayrıca `declared_but_live` olarak
    # raporlar — yani beyan çürümesi gizlenmez, görünür olur.
    declared = []
    try:
        taban = client.post(PAGES[page]['endpoint'], json=dict(base))
        govde = taban.get_json() or {}
        for _kategori, _alanlar in (govde.get('unwired_inputs') or {}).items():
            declared.extend(_alanlar or [])
    except Exception:
        pass  # beyan okunamazsa ölçüm yine koşar, yalnız sınıflama kabalaşır

    report = shake.run(client, PAGES[page]['endpoint'], base, specs,
                       declared_unwired=declared,
                       probe_all_options=probe_all_options,
                       probe_fields=SUPURULEN_ALANLAR.get(page, ()))
    return report, inv, template_of_payload, template_specs


def measure_hybrid(client, probe_all_options: bool = False):
    """Hibrit sayfası için A+B ölçümünü koşar."""
    cfg = _layer_b_config()
    template_specs = inventory.field_specs_for('hybrid')
    inv = inventory.build('hybrid')

    specs = []
    seen = set()
    template_of_payload: Dict[str, str] = {}
    for name in sorted(inv.collected_fields & set(template_specs)):
        payload_key = cfg['rename'].get(name, name)
        if payload_key in cfg['not_in_calculate'] or payload_key in seen:
            continue
        field = template_specs[name]
        if field.kind == 'text':
            continue
        seen.add(payload_key)
        template_of_payload[payload_key] = name
        lo, hi = cfg['payload_range'].get(
            payload_key,
            (None, None) if payload_key != name
            else (field.minimum, field.maximum))
        specs.append(shake.FieldSpec(
            name=payload_key, kind=field.kind, lo=lo, hi=hi,
            options=tuple(field.options or ()),
            context=cfg['contexts'].get(payload_key, {}),
        ))

    report = shake.run(client, '/calculate', cfg['base'], specs,
                       declared_unwired=cfg['declared_unused'],
                       probe_all_options=probe_all_options,
                       probe_fields=SUPURULEN_ALANLAR['hybrid'])
    return report, inv, template_of_payload, template_specs


# ---------------------------------------------------------------------------
# UÇ KAPSAMI — üç sayfanın ötesi (ÖH D23 · defter P10B4-16)
#
# Harita v2.6.27'ye kadar ürünün 3 ucunu ölçüyordu; üründe 80 POST ucu var.
# Kalan uçların ölü-girdi / uydurma-sabit taraması yoktu ve engelin kökü tek
# bir eksiklikti: her uç için GEÇERLİ taban yük. O yükler artık merkezî
# katalogdadır (``tests/support/uc_katalogu``) ve buradan ölçülür.
#
# Kapsam BEYANI ölçümle birlikte yayımlanır: kataloglanmamış ya da ölçülemeyen
# uç "temiz" sayılmaz, ADIYLA ve GEREKÇESİYLE listelenir.
# ---------------------------------------------------------------------------

def measure_endpoint(client, yol: str, probe_all_options: bool = False):
    """Katalogdaki bir ucun sarsım matrisini koşar.

    Alan şartnameleri taban yükün kendi değerlerinden türer (API uçlarının
    HTML formu yoktur); metin alanları seçenek listesi bilinmediği için
    sarsılamaz ve ``unmeasurable`` olarak ADIYLA raporlanır.
    """
    kayit = uc_katalogu.kayit(yol)
    taban = uc_katalogu.taban_yuk(yol)
    specs = uc_katalogu.alan_speclari(yol)
    report = shake.run(client, kayit.cagri_yolu, taban, specs,
                       probe_all_options=probe_all_options)
    return report


def measure_endpoints(client, yollar=None, sinir: Optional[int] = None,
                      ilerleme=None) -> Dict[str, Any]:
    """Katalogdaki ölçülebilir uçları sırayla ölçer.

    Dönen sözlük her uç için ya ölçüm özetini ya da ADLI bir başarısızlık
    gerekçesini taşır. Ölçülemeyen uç sessizce düşmez (fail-closed).
    """
    if yollar is None:
        yollar = uc_katalogu.olculebilir_uclar()
    if sinir is not None:
        yollar = list(yollar)[:sinir]
    sonuc: Dict[str, Any] = {}
    for yol in yollar:
        t0 = time.perf_counter()
        try:
            rapor = measure_endpoint(client, yol)
        except Exception as exc:
            sonuc[yol] = {'olculdu': False,
                          'gerekce': f'{type(exc).__name__}: {exc}'}
            if ilerleme:
                ilerleme(yol, sonuc[yol])
            continue
        ic = uc_katalogu.ic_anahtarlar(yol)
        sonuc[yol] = {
            'olculdu': True,
            'sn': round(time.perf_counter() - t0, 2),
            'taban_yaprak': rapor.baseline_leaf_count,
            'alan': (len(rapor.live_inputs) + len(rapor.dead_inputs)
                     + len(rapor.echo_only_inputs) + len(rapor.unmeasurable)),
            'canli': sorted(rapor.live_inputs),
            'olu': sorted(rapor.dead_inputs),
            'yalniz_yanki': sorted(rapor.echo_only_inputs),
            'olculemedi': dict(sorted(rapor.unmeasurable.items())),
            'sabit_cikti': len(rapor.constant_outputs),
            'sabit_cikti_yollari': sorted(rapor.constant_outputs)[:40],
            # Kapsam beyanı: bu katmanda sarsılMAYAN iç anahtarlar.
            'sarsilmayan_ic_anahtar': ic,
        }
        if ilerleme:
            ilerleme(yol, sonuc[yol])
    return sonuc


def uc_kapsami(app, olcumler: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Katalog + ürün karşılaştırması ve (varsa) ölçüm özeti."""
    rapor = uc_katalogu.kapsam_raporu(app)
    kayitlar = uc_katalogu.kayitlar()
    satirlar = []
    for yol in uc_katalogu.post_uclari(app):
        k = kayitlar.get(yol)
        olcum = (olcumler or {}).get(yol)
        satirlar.append({
            'yol': yol,
            'sinif': k.sinif if k else 'KATALOGDA YOK',
            'gerekce': k.gerekce if k else 'katalog eksik — bekçi kırmızı',
            'kaynak': k.kaynak if k else '',
            'olcum': olcum,
        })
    rapor['satirlar'] = satirlar
    if olcumler is not None:
        rapor['olculen_uc'] = sum(1 for v in olcumler.values()
                                  if v.get('olculdu'))
        rapor['olculemeyen_uc'] = sorted(
            y for y, v in olcumler.items() if not v.get('olculdu'))
    return rapor


# ---------------------------------------------------------------------------
# HTML üretimi
# ---------------------------------------------------------------------------

_CSS = """
:root{--bg:#0a1017;--panel:#101a24;--line:#1d2c3a;--ink:#cfe0ea;--dim:#7f96a6;
--cyan:#00e5ff;--red:#ff5d73;--amber:#ffd166;--green:#2dd4a8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
header{padding:18px 22px;border-bottom:1px solid var(--line);
display:flex;align-items:baseline;gap:18px;flex-wrap:wrap}
h1{margin:0;font-size:17px;font-weight:600;letter-spacing:.4px}
.meta{color:var(--dim);font-size:12px}
.legend{display:flex;gap:14px;font-size:12px;margin-left:auto;flex-wrap:wrap}
.legend span{display:flex;align-items:center;gap:6px}
.sw{width:10px;height:10px;border-radius:2px;display:inline-block}
.filters{padding:12px 22px;border-bottom:1px solid var(--line);
display:flex;gap:10px;align-items:center;flex-wrap:wrap}
input[type=search]{background:var(--panel);border:1px solid var(--line);
color:var(--ink);padding:7px 11px;border-radius:6px;min-width:260px;font-size:13px}
button{background:var(--panel);border:1px solid var(--line);color:var(--ink);
padding:6px 12px;border-radius:6px;cursor:pointer;font-size:12px}
button.on{border-color:var(--cyan);color:var(--cyan)}
.cols{display:grid;grid-template-columns:1fr 1fr 1.4fr;gap:0;height:calc(100vh - 132px)}
.col{overflow:auto;border-right:1px solid var(--line);padding:10px 0}
.col:last-child{border-right:0}
.col h2{margin:0 16px 8px;font-size:11px;letter-spacing:1.2px;
text-transform:uppercase;color:var(--dim);font-weight:600}
.row{padding:6px 16px;cursor:pointer;border-left:3px solid transparent;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}
.row:hover{background:#16222e}
.row.sel{background:#17303c;border-left-color:var(--cyan)}
.row.dim{opacity:.28}
.row .n{color:var(--dim);font-size:11px;margin-left:8px}
.row.dead{color:var(--red)}
.row.echo{color:var(--amber)}
.row.const{color:var(--amber)}
.row.unmeas{color:var(--dim);font-style:italic}
.row.live{color:var(--ink)}
.hint{margin:10px 16px;color:var(--dim);font-size:12px;white-space:normal}
code{background:#0d1720;padding:1px 5px;border-radius:3px;font-size:12px}
.path{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
/* ÖH D20 / P10B4-06: secim alaninin OLCUM GUCU hukumle birlikte gorunur. */
.kapsam{color:var(--dim);font-size:11px}
.kirik{color:var(--red);font-size:11px;font-weight:600}
/* Sutunlar arasi baglanti oklari: secili alanin nereye gittigini gorsel
   olarak izlemek icin. Fare olaylarini engellememesi sart. */
#links{position:fixed;inset:0;pointer-events:none;z-index:5}
#links path{fill:none;stroke:var(--cyan);stroke-width:1.4;opacity:.55}
#links path.faint{opacity:.18;stroke-width:1}
"""

_JS = """
const D = __DATA__;
let selField = null, selLeaf = null, q = '';  // selLeaf: yol INDEKSI
const showDeadOnly = {v:false};

function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

// ÖH D20 / P10B4-06 (Fable-D17 ŞART'ı) — "canlı" hükmü ölçüm gücünü
// SAKLAMAZ. Seçim alanı N seçenekten kaçıyla sarsıldıysa o rozet yazılır;
// süpürme açıkken 200 vermeyen seçenekler ADIYLA görünür.
function kapsamRozeti(f){
  const k = (D.secimKapsami||{})[f];
  if (!k) return '';
  let s = ' <span class="kapsam">('+k.denenen+'/'+k.toplam+' denendi)</span>';
  const km = (D.kismenOlculdu||{})[f];
  const kirik = km && km.kirik ? Object.keys(km.kirik) : [];
  if (kirik.length){
    const detay = kirik.map(o=>o+': HTTP '+km.kirik[o]).join(', ');
    s += ' <span class="kirik" title="'+esc(detay)+'">'+kirik.length+
         ' seçenek düşüyor</span>';
  }
  return s;
}

function fieldClass(f){
  if (D.unmeasurable[f] !== undefined) return 'unmeas';
  if (D.dead.includes(f)) return 'dead';
  if (D.echo.includes(f)) return 'echo';
  return 'live';
}

// Yaprak -> onu değiştiren girdiler. byField'in tersi; JS'te kurulur ki
// dosyada aynı bilgi iki kez saklanmasın.
const byLeaf = {};
Object.keys(D.byField).forEach(f=>{
  D.byField[f].forEach(i=>{ (byLeaf[i]=byLeaf[i]||[]).push(f); });
});
const P = i => D.paths[i];

function render(){
  // --- 1. sütun: şablon alanları
  const fc = document.getElementById('cField');
  fc.innerHTML = '<h2>Form alanı (şablon)</h2>';
  D.fields.forEach(f=>{
    if (q && !(f.payload+f.template).toLowerCase().includes(q)) return;
    if (showDeadOnly.v && fieldClass(f.payload)==='live') return;
    const d = document.createElement('div');
    d.className = 'row ' + fieldClass(f.payload) + (selField===f.payload?' sel':'');
    if (selLeaf !== null && !(byLeaf[selLeaf]||[]).includes(f.payload)) d.className += ' dim';
    const n = D.live[f.payload];
    d.innerHTML = esc(f.template) + (n?'<span class="n">'+n+'</span>':'')
                + kapsamRozeti(f.payload);
    d.onclick = ()=>{ selField = selField===f.payload?null:f.payload; selLeaf=null; render(); };
    fc.appendChild(d);
  });

  // --- 2. sütun: payload anahtarları
  const pc = document.getElementById('cPayload');
  pc.innerHTML = '<h2>Sunucuya giden anahtar</h2>';
  D.fields.forEach(f=>{
    if (q && !(f.payload+f.template).toLowerCase().includes(q)) return;
    if (showDeadOnly.v && fieldClass(f.payload)==='live') return;
    const d = document.createElement('div');
    d.className = 'row ' + fieldClass(f.payload) + (selField===f.payload?' sel':'');
    if (selLeaf !== null && !(byLeaf[selLeaf]||[]).includes(f.payload)) d.className += ' dim';
    let label = esc(f.payload);
    if (f.payload !== f.template) label += ' <span class="n">&larr; ' + esc(f.template) + '</span>';
    d.innerHTML = label + kapsamRozeti(f.payload);
    d.onclick = ()=>{ selField = selField===f.payload?null:f.payload; selLeaf=null; render(); };
    pc.appendChild(d);
  });

  // --- 3. sütun: çıktı yaprakları
  const lc = document.getElementById('cLeaf');
  let leaves;
  let head;
  if (selField) {
    leaves = D.byField[selField] || [];
    head = esc(selField) + ' &rarr; ' + leaves.length + ' çıktı dalı';
  } else {
    leaves = D.constants;
    head = 'Hiçbir girdiden etkilenmeyen sayısal çıktılar (' + leaves.length + ')';
  }
  lc.innerHTML = '<h2>' + head + '</h2>';
  if (!selField && leaves.length) {
    lc.innerHTML += '<div class="hint">Bir alan seçin, o alanın değiştirdiği '
      + 'çıktılar burada listelenir. Bir çıktı seçerseniz onu belirleyen '
      + 'girdiler solda vurgulanır.</div>';
  }
  if (selField && !leaves.length) {
    const why = D.unmeasurable[selField];
    lc.innerHTML += '<div class="hint">' + (why
      ? 'Bu alan ÖLÇÜLEMEDİ: ' + esc(why) + '. Ölçülemeyen alan ölü demek '
        + 'DEĞİLDİR; refakat alanlarıyla ölçülebilir hale getirilmeli ya da '
        + 'gerekçesiyle listelenmelidir.'
      : 'Bu alan sarsıldığında çıktı hiç değişmedi.') + '</div>';
  }
  leaves.forEach(i=>{
    const p = P(i);
    if (q && selField===null && !p.toLowerCase().includes(q)) return;
    const d = document.createElement('div');
    d.className = 'row path ' + (selField?'live':'const') + (selLeaf===i?' sel':'');
    const src = (byLeaf[i]||[]).length;
    d.innerHTML = esc(p) + (src?'<span class="n">'+src+' girdi</span>':'');
    d.onclick = ()=>{ selLeaf = selLeaf===i?null:i; selField=null; render(); };
    lc.appendChild(d);
  });

  requestAnimationFrame(drawLinks);
}

/* Sütunlar arası bağlantı okları.
   Seçili alan için: şablon adı -> payload anahtarı -> etkilediği çıktılar.
   Seçili çıktı için: onu belirleyen her girdiden çıktı satırına.
   Eğriler DOM'daki gerçek satır konumlarından çizilir; kaydırmada ve
   pencere boyutunda yeniden hesaplanır. */
function drawLinks(){
  const svg = document.getElementById('links');
  svg.innerHTML = '';
  const rows = sel => Array.from(document.querySelectorAll(sel));
  const anchor = (el, side) => {
    const r = el.getBoundingClientRect();
    return {x: side==='r' ? r.right - 4 : r.left + 4, y: r.top + r.height/2};
  };
  const visible = el => {
    const r = el.getBoundingClientRect();
    const c = el.parentElement.getBoundingClientRect();
    return r.bottom > c.top + 4 && r.top < c.bottom - 4;
  };
  const curve = (a, b, faint) => {
    const dx = Math.max(28, (b.x - a.x) * 0.45);
    const p = document.createElementNS('http://www.w3.org/2000/svg','path');
    p.setAttribute('d', `M${a.x},${a.y} C${a.x+dx},${a.y} ${b.x-dx},${b.y} ${b.x},${b.y}`);
    if (faint) p.setAttribute('class','faint');
    svg.appendChild(p);
  };

  const fieldRows = rows('#cField .row');
  const payloadRows = rows('#cPayload .row');
  const leafRows = rows('#cLeaf .row');

  if (selField) {
    const i = fieldRows.findIndex(r=>r.classList.contains('sel'));
    if (i >= 0 && payloadRows[i] && visible(fieldRows[i]) && visible(payloadRows[i])) {
      curve(anchor(fieldRows[i],'r'), anchor(payloadRows[i],'l'), false);
    }
    if (i >= 0 && visible(payloadRows[i])) {
      const from = anchor(payloadRows[i],'r');
      // Çok fazla ok çizmek okunabilirliği bozar: görünür ilk 40 dal.
      leafRows.filter(visible).slice(0,40).forEach(r=>curve(from, anchor(r,'l'), true));
    }
  } else if (selLeaf !== null) {
    const target = leafRows.find(r=>r.classList.contains('sel'));
    if (target && visible(target)) {
      const to = anchor(target,'l');
      payloadRows.filter(r=>!r.classList.contains('dim') && visible(r))
                 .slice(0,40)
                 .forEach(r=>curve(anchor(r,'r'), to, true));
    }
  }
}

document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('q').addEventListener('input',e=>{q=e.target.value.toLowerCase();render();});
  const b=document.getElementById('bDead');
  b.onclick=()=>{showDeadOnly.v=!showDeadOnly.v;b.classList.toggle('on',showDeadOnly.v);render();};
  document.getElementById('bClear').onclick=()=>{selField=null;selLeaf=null;q='';
    document.getElementById('q').value='';render();};
  ['cField','cPayload','cLeaf'].forEach(id=>{
    document.getElementById(id).addEventListener('scroll', drawLinks, {passive:true});
  });
  window.addEventListener('resize', drawLinks);
  render();
});
"""


_INDEX = __import__('re').compile(r'\[\d+\]')


def collapse(path: str) -> str:
    """Dizi indislerini ``[*]`` ile katlar.

    Zaman serileri her örnekleme noktasını AYRI bir yaprak yapar:
    ``.trajectory.phases.descent[1247].altitude``. Bekçi testinin bunlara
    tek tek bakması doğru (bir tanesi bile değişmiyorsa girdi ölüdür), ama
    harita için gürültüdür: kullanıcı "yükseklik dizisi etkileniyor mu"
    bilmek ister, 1247. elemanı değil. Katlamadan harita 25 MB çıkıyordu.
    """
    return _INDEX.sub('[*]', path)


def erime_kaniti(erime: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Erime ölçümünü SINIFLANDIRICI kanıtına çevirir — TEK dönüşüm yeri.

    ÖH D23 · P15B3-09. ``erime_olc`` zaten hangi yaprağın hangi sarsımda
    oynadığını ölçüyordu; yalnız SAYISI tutuluyor, adlar atılıyordu. Aynı
    koşumda sınıflandırıcı o yapraklara bakıp *"neden sabit oldugu
    bilinmiyor"* diyordu. Kanal vardı, kapı yoktu; kapı burada.

    Ölçüm yoksa ``None`` döner ve sınıflandırma eski davranışını korur
    (fail-closed: ölçülmemiş kanıtla hüküm verilmez).
    """
    if not erime or not erime.get('olculdu'):
        return None
    return {'erime': erime.get('kaynak') or {},
            'payload_anahtarlari': tuple(erime.get('anahtarlar') or ())}


def sabit_sinif_ozeti(report, erime: Optional[Dict[str, Any]] = None
                      ) -> Dict[str, Any]:
    """Sabit yaprakların KATLANMIŞ (``[*]``) sınıf özeti — TEK TANIM YERİ.

    ÖH D18 / altyapi (P10B4-04). ÖLÇÜLDÜ (once_p10b4_04.json): giriş sayfası
    ile detay sayfası AYNI ÜRETİMDE aynı büyüklük için farklı sayı basıyordu.
    Sebep tek kaynak eksikliğiydi:

    * detay sayfası (``build_html``) sınıfları ``collapse()`` ile katlanmış
      yol kimliklerine bağlıyor ve KATLANMIŞ yaprak sayıyordu,
    * giriş sayfası (``build_index``) ``siniflandir_hepsi``'yi ayrıca çağırıp
      HAM yaprak sayımını (``_s['sayim']``) basıyordu.

    Zaman serileri her örnekleme noktasını ayrı yaprak yaptığı için ikisi kat
    kat ayrışıyordu (üretimde 284 ⟷ 87, 3,26×; sentetik ölçümde 127 ⟷ 10).
    "İzlenen tek sayı" kalın basıldığı için bu, geliştiriciye YANLIŞ hedef
    gösteren bir sayıydı. İki sayfa da artık BU fonksiyondan okur.

    Döner: ``{'sinif_of': {katlanmış yol: sınıf}, 'gerekce_of': {...},
    'sayim': {sınıf: adet}, 'toplam': katlanmış sabit yaprak sayısı,
    'belirsiz': sınıflandırılmamış adedi, 'aciklanan': toplam - belirsiz}``
    """
    from sabit_siniflandirma import ACIK_HESAP_SINIFLARI, siniflandir_hepsi
    ham = siniflandir_hepsi(report.constant_outputs, report.baseline_leaves,
                            erime_kaniti(erime))
    sinif_of: Dict[str, str] = {}
    gerekce_of: Dict[str, str] = {}
    for yol, sinif, gerekce in ham['kalemler']:
        cyol = collapse(yol)
        # Çökertilmiş yol birden çok yaprağı temsil edebilir; en KÖTÜ sınıf
        # kazanır ki iyi kardeşler belirsiz olanı gizlemesin.
        if sinif_of.get(cyol) != 'SINIFLANDIRILMAMIS':
            sinif_of[cyol] = sinif
            gerekce_of[cyol] = gerekce
    sayim: Dict[str, int] = {}
    for sinif in sinif_of.values():
        sayim[sinif] = sayim.get(sinif, 0) + 1
    toplam = len({collapse(y) for y in report.constant_outputs})
    belirsiz = sayim.get('SINIFLANDIRILMAMIS', 0)
    # ÖH D23 · P15B3-09 — AÇIK HESAP: ölçümle açıklandı ama AKLANMADI.
    # "Sınıflandırılmamış" sayısının düşmesi tek başına temizlik değildir;
    # bu kova ayrı yayımlanır ve "temiz" hükmünü BLOKLAR.
    acik_hesap = sum(sayim.get(s, 0) for s in ACIK_HESAP_SINIFLARI)
    return {'sinif_of': sinif_of, 'gerekce_of': gerekce_of, 'sayim': sayim,
            'toplam': toplam, 'belirsiz': belirsiz,
            'acik_hesap': acik_hesap,
            'aciklanan': toplam - belirsiz - acik_hesap}


def erime_olc(client, page: str, report) -> Dict[str, Any]:
    """ÖH D19 · P10B4-07 — "sabit yaprak" sayısının ÖLÇÜM GÜCÜNE bağlılığı.

    ÖLÇÜLDÜ (D19, taban 60cd341): bu dosyanın yayımladığı "sabit çıktı
    yaprağı" sayısı alan başına TEK alternatifle sarsılan zayıf bir ölçümden
    gelir. Aynı sayfa payload anahtarı üstünden (×1,4 ×0,6 ×10 ×0,1 + tüm
    seçim seçenekleri + tüm yakıt kataloğu) sarsılınca:

        solid  : 200 "sabit" yaprağın **200'ü** (%100) oynuyor → geriye
                 iki ölçümde de sabit kalan **0** yaprak kalıyor.
        hybrid : 231'in 39'u (%16,9) oynuyor, 192'si kalıyor.

    Yani katı sayfasında sayının TAMAMI ölçüm zayıflığı artifaktıdır. Giriş
    sayfası bu sayıyı bir KAPI ÖLÇÜTÜ olarak öneriyordu ("izlenen tek sayı
    sınıflandırılmamış, hedefi sıfırdır"); o kapı kurulsaydı kapatmanın yolu
    kusuru düzeltmek değil sarsımı zayıflatmak olurdu.

    FAIL-CLOSED: erime ölçülmediyse kapı hükmü YAYIMLANMAZ (bkz.
    ``build_index``). Beyan çözüm değildir — ama ölçülmemiş bir hükmü
    yayımlamamak beyan değil, hükmü geri çekmektir.

    Ölçüm TEK KAYNAKTAN gelir: ``tools/sabit_tarayici.py::tara``. O araç bu
    kesişimi zaten hesaplıyordu ve hiçbir tüketicisi yoktu.
    """
    import contextlib
    import io as _io
    sys.path.insert(0, str(ROOT / 'tools'))
    import sabit_tarayici                                   # noqa: E402
    from tests.support import shake as _shake               # noqa: E402
    sonuc = sabit_tarayici.tara(page, client, sys.modules[__name__],
                                _shake, _io.StringIO(), report=report)
    toplam = sonuc['zayif_sarsim_sabit']
    eriyen = sonuc['eriyen']
    return {
        'olculdu': True,
        'toplam': toplam,
        'eriyen': eriyen,
        'kalan': toplam - eriyen,
        'yuzde': (100.0 * eriyen / toplam) if toplam else 0.0,
        'deneme': sonuc['deneme_sayisi'],
        # ÖH D23 · P15B3-09 — eriyen yaprakların ADLARI ve onları oynatan
        # sarsım, artı sarsımın kapsadığı payload anahtarları. Sayı değil
        # KANIT: sınıflandırıcı bunlarla "şablon körü" hükmünü verir.
        'kaynak': sonuc.get('eriyen_kaynak') or {},
        'anahtarlar': sonuc.get('taban_anahtarlar') or [],
    }


#: Erime ölçülmemişken meta satırına giren ADLI RET. Sayı yayımlanır ama
#: HÜKÜM (kapı ölçütü olması) yayımlanmaz.
ERIME_OLCULMEDI = ('erime ÖLÇÜLMEDİ — bu sayı ölçüm gücüne bağlıdır, '
                   'kapı ölçütü DEĞİLDİR')


def erime_meta(erime: Optional[Dict[str, Any]]) -> str:
    """Meta satırının erime parçası (tek kaynak: giriş ve detay aynı metin)."""
    if not erime or not erime.get('olculdu'):
        return ERIME_OLCULMEDI
    return ('güçlü sarsımda %d/%d eriyor (%%%.1f) &middot; iki ölçümde de '
            'sabit: %d' % (erime['eriyen'], erime['toplam'],
                           erime['yuzde'], erime['kalan']))


def build_html(page: str, report, inv, template_of_payload, generated_at: str,
               erime: Optional[Dict[str, Any]] = None) -> str:
    # Yolları katla + tekilleştir, sonra INDEKSLE. İndeksleme şart: aynı yol
    # onlarca alanın listesinde geçiyor, düz metin olarak saklamak dosyayı
    # gereksiz büyütür.
    path_id: Dict[str, int] = {}
    paths: List[str] = []

    def pid(p: str) -> int:
        cp = collapse(p)
        if cp not in path_id:
            path_id[cp] = len(paths)
            paths.append(cp)
        return path_id[cp]

    by_field: Dict[str, List[int]] = {}
    for fld, raw_paths in report.changed_paths.items():
        seen = sorted({pid(p) for p in raw_paths})
        by_field[fld] = seen

    constants = sorted({collapse(p) for p in report.constant_outputs})
    for c in constants:
        pid(c)

    # v2.6.26 — SABİT YAPRAKLAR SINIFLANDIRILIR.
    # "207 sabit çıktı" tek başına hüküm taşımıyordu; bir kısmı tarama
    # ızgarası, bir kısmı ISA atmosferi, bir kısmı beyanlı. Sınıflandırınca
    # geriye tek anlamlı rakam kalıyor: kaç yaprağın NEDEN sabit olduğunu
    # bilmiyoruz. Kapı ona bağlanabilir.
    # ÖH D18 / P10B4-04: sınıflandırma TEK KAYNAKTAN gelir
    # (``sabit_sinif_ozeti``); giriş sayfası da aynı fonksiyonu okur.
    _ozet = sabit_sinif_ozeti(report, erime)
    _sinif_of: Dict[int, str] = {}
    _gerekce_of: Dict[int, str] = {}
    for _cyol, _s in _ozet['sinif_of'].items():
        _cid = path_id.get(_cyol)
        if _cid is None:
            continue
        _sinif_of[_cid] = _s
        _gerekce_of[_cid] = _ozet['gerekce_of'][_cyol]
    _sinif_sayim = dict(_ozet['sayim'])

    fields = [{'payload': payload, 'template': template}
              for payload, template in sorted(template_of_payload.items())]

    data = {
        'page': page,
        'fields': fields,
        'paths': paths,
        'live': report.live_inputs,
        'dead': report.dead_inputs,
        'echo': report.echo_only_inputs,
        'unmeasurable': report.unmeasurable,
        'constants': [path_id[c] for c in constants],
        'byField': by_field,
        'constClass': _sinif_of,
        'constWhy': _gerekce_of,
        'constCounts': _sinif_sayim,
        # ÖH D20 · P10B4-06 (Fable-D17 ŞART'ı): "canlı" hükmü ölçüm gücünü
        # SAKLAMAZ. Seçim alanı 11 seçenekten YALNIZ BİRİYLE sarsıldıysa
        # harita bunu "canlı (1/11 denendi)" diye yazar; süpürme açıkken
        # 200 vermeyen seçenekler adıyla ve durum koduyla görünür.
        'secimKapsami': report.secim_kapsami,
        'kismenOlculdu': report.kismen_olculdu,
    }
    payload_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

    measured = (len(report.live_inputs) + len(report.dead_inputs)
                + len(report.echo_only_inputs))
    _belirsiz = _ozet['belirsiz']
    # ÖH D23 · P15B3-09 — açık hesap sayısı meta satırında AYRI durur:
    # açıklanmış olmak aklanmış olmak değildir.
    _acik = _ozet['acik_hesap']
    # ÖH D20 · P10B4-06 — seçim alanlarının ölçüm gücü sayfa düzeyinde de
    # yazılır: "N seçim alanı, M'si tek seçenekle" (kapsam beyanı bedava).
    _sec = report.secim_kapsami or {}
    _tek = sum(1 for k in _sec.values() if k.get('denenen', 1) <= 1
               and k.get('toplam', 1) > 1)
    _kirik_alan = len(report.kismen_olculdu or {})
    _kapsam_meta = (f'{len(_sec)} seçim alanı ({_tek} tek seçenekle ölçüldü'
                    + (f' &middot; {_kirik_alan} alanda seçenek düşüyor'
                       if _kirik_alan else '') + ')')
    meta = (f'{page} &middot; {measured} alan ölçüldü &middot; '
            f'{report.baseline_leaf_count} çıktı yaprağı &middot; '
            f'{len(constants)} sabit '
            f'({_belirsiz} sınıflandırılmamış &middot; '
            f'{_acik} açık hesap &middot; {erime_meta(erime)})'
            f' &middot; {_kapsam_meta}'
            f' &middot; {generated_at}')

    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>HRMA bağlama haritası — {html.escape(page)}</title>
<style>{_CSS}</style></head><body>
<header>
  <h1>HRMA bağlama haritası</h1>
  <span class="meta">{meta}</span>
  <p class="meta" data-kapsam="1">{html.escape(kapsam_beyani())}</p>
  <div class="legend">
    <span><i class="sw" style="background:#cfe0ea"></i>bağlı</span>
    <span><i class="sw" style="background:#ff5d73"></i>ölü girdi</span>
    <span><i class="sw" style="background:#ffd166"></i>yalnız yankı / sabit çıktı</span>
    <span><i class="sw" style="background:#7f96a6"></i>ölçülemedi</span>
  </div>
</header>
<div class="filters">
  <input id="q" type="search" placeholder="alan ya da çıktı yolu ara...">
  <button id="bDead">Yalnız sorunlular</button>
  <button id="bClear">Seçimi temizle</button>
  <span class="meta">Bu harita ölçümden üretilir; elle düzenlenmez.</span>
</div>
<div class="cols">
  <div class="col" id="cField"></div>
  <div class="col" id="cPayload"></div>
  <div class="col" id="cLeaf"></div>
</div>
<svg id="links"></svg>
<script>{_JS.replace('__DATA__', payload_json)}</script>
</body></html>"""


def build_index(written, generated_at: str,
                erimeler: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """Üç sayfanın giriş sayfası.

    ÖH D19 / P10B4-07 — KAPI HÜKMÜ ARTIK KAZANILIYOR. Bu sayfa eskiden
    ``"izlenen tek sayı sınıflandırılmamış, hedefi sıfırdır"`` diye bir
    KAPI ÖLÇÜTÜ öneriyordu. Ölçüldü ki o sayı ölçüm gücüne bağlıdır: katıda
    200 "sabit" yaprağın 200'ü daha güçlü sarsımda oynuyor (%100 artifakt),
    hibritte 231'in 39'u (%16,9). Kapı o hâliyle kurulsaydı kapatmanın yolu
    kusuru düzeltmek değil sarsımı zayıflatmak olurdu.

    Fail-closed: erime ÖLÇÜLMEDİYSE kapı cümlesi yayımlanmaz, yerine adlı
    ret geçer. Ölçüldüyse artifakt payı sayıyla YANINDA durur.
    """
    erimeler = erimeler or {}
    cards = []
    toplam_belirsiz = 0
    toplam_acik = 0
    for page, out, rep in written:
        measured = (len(rep.live_inputs) + len(rep.dead_inputs)
                    + len(rep.echo_only_inputs))
        # v2.6.26 — "sorunlu alan" sayısına YANKI dahil edilmiyor artık.
        # Beyanı olan yankı bir sorun değil; beyanı OLMAYAN yankı zaten
        # ölçümde `declared_but_live` ya da beyan listesinin dışında görünür.
        # Kartın kırmızı/sarı olması ölü alan ve beyan çürümesine bakar.
        problems = len(rep.dead_inputs) + len(rep.unmeasurable) \
            + len(rep.declared_but_live)
        # ÖH D18 / P10B4-04: detay sayfasıyla AYNI fonksiyon, AYNI sayı.
        # Eskiden burada ``siniflandir_hepsi`` ayrıca çağrılıyor ve HAM
        # yaprak sayımı basılıyordu; detay sayfası KATLANMIŞ sayıyordu.
        _er = erimeler.get(page)
        _ozet = sabit_sinif_ozeti(rep, _er)
        belirsiz = _ozet['belirsiz']
        toplam_belirsiz += belirsiz
        aciklanan = _ozet['aciklanan']
        # ÖH D23 · P15B3-09 — açık hesap: ölçümle açıklandı, AKLANMADI.
        acik = _ozet['acik_hesap']
        toplam_acik += acik
        if not _er or not _er.get('olculdu'):
            erime_rozet = 'erime ölçülmedi'
            erime_cls = 'amb'
        else:
            erime_rozet = ('güçlü sarsımda %d/%d eriyor (%%%.1f)'
                           % (_er['eriyen'], _er['toplam'], _er['yuzde']))
            erime_cls = 'ok' if _er['eriyen'] == 0 else 'bad'
        # ÖH D22 · P10B4-05 — ROZETİN KAPSAMI HÜKMÜYLE EŞLEŞMELİ.
        # ÖLÇÜLDÜ (D22): "temiz" rozeti YALNIZ girdi düzeyi sayılara
        # bakıyordu (dead_inputs + unmeasurable + declared_but_live).
        # Kampanyanın BASKIN kusur sınıfı ise girdi düzeyinde görünmez:
        # girdi CANLI ama ÖNEMLİ bir yaprakta ölü — hibritin 12 regresyon
        # yaprağının 9'u yakıt kimliğine kör (P10B4-05), yedi yakıtın
        # hepsinde .motor.regression_rate birebir aynı. O sayfa yine de
        # "temiz" rozeti alıyordu.
        #
        # Aynı kartta bu sınıfı GÖREN iki ölçüm zaten hesaplanıyordu
        # (sınıflandırılmamış sabit yaprak sayısı ve erime) ama rozetin
        # hükmüne girmiyordu. Artık giriyor. Bu bir beyan değil, hükmün
        # geri çekilmesidir: dosyanın kendi doktrini (build_index,
        # "Ölçülemedi = temiz DEĞİL") burada da uygulanıyor.
        yaprak_olculdu = bool(_er and _er.get('olculdu'))
        if problems:
            badge = f'{problems} sorunlu alan'
        elif not yaprak_olculdu:
            badge = 'girdi düzeyi temiz — yaprak düzeyi ÖLÇÜLMEDİ'
        elif belirsiz:
            badge = (f'girdi düzeyi temiz — {belirsiz} sınıflandırılmamış '
                     f'yaprak')
        elif acik:
            # ÖH D23 · P15B3-09 — "açıklandı" ≠ "temiz". Şablon körü ve
            # girdi yankısı sınıfları ölçümle AÇIKLANMIŞ ama formun o
            # sayıyı besleyemediğini söyleyen sınıflardır; rozet bunu
            # yutarsa sınıflandırmayı iyileştirmek sayfayı yalancı yere
            # temiz gösterirdi.
            badge = f'girdi düzeyi temiz — {acik} açık hesap yaprağı'
        else:
            badge = 'temiz'
        cls = 'ok' if badge == 'temiz' else 'warn'
        belirsiz_cls = 'ok' if belirsiz == 0 else 'bad'
        acik_cls = 'ok' if acik == 0 else 'amb'
        cards.append(f"""
        <a class="card {cls}" href="{html.escape(out.name)}">
          <h2>{html.escape(page)}</h2>
          <div class="big">{measured}</div>
          <div class="lbl">alan ölçüldü</div>
          <div class="tags">
            <span>{len(rep.live_inputs)} bağlı</span>
            <span class="bad">{len(rep.dead_inputs)} ölü</span>
            <span class="amb">{len(rep.echo_only_inputs)} yankı (beyanlı)</span>
          </div>
          <div class="tags">
            <span>{aciklanan} sabit aklandı</span>
            <span class="{acik_cls}">{acik} açık hesap</span>
            <span class="{belirsiz_cls}">{belirsiz} sınıflandırılmamış</span>
          </div>
          <div class="tags"><span class="{erime_cls}">{erime_rozet}</span></div>
          <div class="badge">{badge}</div>
        </a>""")
    # KAPI HÜKMÜ (P10B4-07): yalnız KAZANILDIYSA yayımlanır.
    _olculen = [erimeler.get(pg) for pg, _o, _r in written]
    if any(not e or not e.get('olculdu') for e in _olculen):
        kapi_cumlesi = (
            '<b>Kapı ölçütü YAYIMLANMADI.</b> "Sınıflandırılmamış sabit" '
            'sayısı ölçüm gücüne bağlıdır ve bu koşumda erime ÖLÇÜLMEDİ; '
            'ölçülmemiş bir eşiği kapı diye yayımlamak, kapatmanın yolunu '
            'kusuru düzeltmekten sarsımı zayıflatmaya çevirir '
            '(defter P10B4-07). Ölçmek için: '
            '<code>python3 tools/wiring_map.py</code> (erime varsayılan '
            'olarak ölçülür; <code>--erime-yok</code> ile kapatılmıştı).')
    else:
        _toplam_eriyen = sum(e['eriyen'] for e in _olculen)
        _toplam_sabit = sum(e['toplam'] for e in _olculen)
        _pay = (100.0 * _toplam_eriyen / _toplam_sabit) if _toplam_sabit else 0.0
        if _toplam_eriyen == 0:
            kapi_cumlesi = (
                'Erime ÖLÇÜLDÜ: %d sabit yaprağın hiçbiri daha güçlü '
                'sarsımda oynamıyor. İzlenen sayı <b>sınıflandırılmamış</b>, '
                'hedefi sıfırdır — bu hüküm ölçümle kazanıldı.'
                % _toplam_sabit)
        else:
            kapi_cumlesi = (
                'Erime ÖLÇÜLDÜ: %d sabit yaprağın <b>%d\'i (%%%.1f)</b> daha '
                'güçlü sarsımda oynuyor (payload anahtarı sarsımı: ×1,4 ×0,6 '
                '×10 ×0,1 + tüm seçim seçenekleri). Bu pay sıfıra inmeden '
                '"sınıflandırılmamış = 0" bir KAPI ÖLÇÜTÜ DEĞİLDİR: sayı '
                'kusur değil ölçüm gücü ölçüyor (defter P10B4-07).'
                % (_toplam_sabit, _toplam_eriyen, _pay))
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>HRMA bağlama haritası</title>
<style>{_CSS}
.wrap{{max-width:980px;margin:40px auto;padding:0 22px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-top:24px}}
.card{{display:block;text-decoration:none;color:var(--ink);background:var(--panel);
border:1px solid var(--line);border-radius:10px;padding:20px}}
.card:hover{{border-color:var(--cyan)}}
.card.warn{{border-left:3px solid var(--amber)}}
.card.ok{{border-left:3px solid var(--green)}}
.card h2{{margin:0 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:1.4px;color:var(--dim)}}
.big{{font-size:38px;font-weight:600;line-height:1}}
.lbl{{color:var(--dim);font-size:12px;margin-bottom:12px}}
.tags{{display:flex;flex-wrap:wrap;gap:8px;font-size:12px;color:var(--dim)}}
.tags .bad{{color:var(--red)}} .tags .amb{{color:var(--amber)}}
.badge{{margin-top:12px;font-size:12px;color:var(--dim)}}
p.note{{color:var(--dim);font-size:13px;line-height:1.7}}
</style></head><body>
<div class="wrap">
  <h1 style="font-size:20px">HRMA bağlama haritası</h1>
  <p class="meta">ölçüm: {generated_at}</p>
  <p class="meta" data-kapsam="1">{html.escape(kapsam_beyani())}</p>
  <div class="cards">{''.join(cards)}</div>
  <p class="note">Bu harita ÖLÇÜMDEN üretilir, elle düzenlenmez. Her alan
  gerçek bir hesap koşularak sarsılır ve yanıtın hangi dallarının değiştiği
  kaydedilir. Kod değişince <code>python3 tools/wiring_map.py</code> ile
  yeniden üretilir.<br><br>
  Sabitler sınıflandırılır (ızgara / standart / tanım / beyanlı / kopya);
  Sınıfların tanımı: <code>tools/sabit_siniflandirma.py</code>.<br>
  Toplam sınıflandırılmamış: <b>{toplam_belirsiz}</b> &middot;
  toplam açık hesap (ölçümle açıklandı, AKLANMADI): <b>{toplam_acik}</b><br>
  <i>Açık hesap</i> = <code>sablon_koru</code> (yaprak sabit değil; şablonun
  gönderdiği alanlar onu görmüyor, payload anahtarı sarsımında oynuyor) +
  <code>girdi_yankisi</code> (alt-çözümlemenin kendi girdisi; /calculate
  yükünde onu besleyen alan yok). İkisi de <b>iş listesinde kalır</b>.<br>
  {kapi_cumlesi}</p>
</div></body></html>"""


def build_uc_kapsami_html(kapsam: Dict[str, Any], generated_at: str) -> str:
    """Uç kapsamı sayfası — ürünün BÜTÜN POST uçları, sınıfıyla ve ölçümüyle.

    Dürüstlük kuralı haritanın geri kalanıyla aynı: ölçülemeyen uç "temiz"
    değil, ADIYLA ve GEREKÇESİYLE listelenir. Kapsam sayısı sayfanın en
    üstünde durur, böylece "ölçüldü" hükmü ölçüm gücünü saklamaz.
    """
    satirlar = []
    sinif_rozet = {
        'olculebilir': ('ok', 'ölçülebilir'),
        'yan_etkili': ('amb', 'yan etkili'),
        'dosya_yuklemeli': ('amb', 'dosya yüklemeli'),
        'govdesiz': ('amb', 'gövdesiz'),
        'kataloglanmadi': ('bad', 'kataloglanmadı'),
        'KATALOGDA YOK': ('bad', 'KATALOGDA YOK'),
    }
    for row in kapsam['satirlar']:
        cls, ad = sinif_rozet.get(row['sinif'], ('bad', row['sinif']))
        o = row.get('olcum')
        if o and o.get('olculdu'):
            ic = o.get('sarsilmayan_ic_anahtar') or {}
            olcum_hucre = (
                f"{o['alan']} alan · {len(o['canli'])} canlı · "
                f"<b class=bad>{len(o['olu'])} ölü</b> · "
                f"{len(o['olculemedi'])} ölçülemedi · "
                f"{o['sabit_cikti']} sabit yaprak"
                + (f" · <span class=amb>{len(ic)} iç anahtar SARSILMADI</span>"
                   if ic else ''))
        elif o:
            olcum_hucre = f"<span class=bad>ölçülemedi: {html.escape(o['gerekce'])}</span>"
        else:
            olcum_hucre = '<span class=dim>bu koşuda ölçülmedi</span>'
        satirlar.append(
            '<tr><td><code>%s</code></td><td class=%s>%s</td><td>%s</td>'
            '<td class=dim>%s</td></tr>'
            % (html.escape(row['yol']), cls, ad, olcum_hucre,
               html.escape(row['gerekce'] or row['kaynak'] or '')))
    olculen = kapsam.get('olculen_uc')
    ust = (
        '<p>Ürün <b>%d</b> POST ucu yayımlıyor; katalog <b>%d</b> kaydın '
        'tamamını taşıyor (eksik: %d, fazla: %d). Sarsım matrisi '
        '<b>%d</b> uçta koşabilir%s.</p>'
        % (kapsam['urun_post_sayisi'], kapsam['katalog_kayit_sayisi'],
           len(kapsam['eksik']), len(kapsam['fazla']),
           kapsam['olculebilir_sayisi'],
           ('; bu koşuda <b>%d</b> uç ölçüldü' % olculen) if olculen is not None else ''))
    return (
        '<!doctype html><meta charset="utf-8"><title>uç kapsamı</title>'
        '<style>%s</style><body><h1>Uç kapsamı</h1>'
        '<p class=dim>üretildi: %s · kaynak: tests/support/uc_katalogu</p>%s'
        '<table><tr><th>uç</th><th>sınıf</th><th>ölçüm</th>'
        '<th>gerekçe / kaynak</th></tr>%s</table>'
        '<p class=dim>Ölçülemeyen uç "temiz" değildir; gerekçesi yanında '
        'durur. Yeni bir POST ucu eklenip kataloglanmazsa '
        'tests/test_d23_altyapi_a1.py kırmızıya döner.</p></body>'
        % (_CSS, html.escape(generated_at), ust, ''.join(satirlar)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--page', default='all',
                    choices=sorted(PAGES) + ['all'],
                    help='ölçülecek sayfa (varsayılan: all = üçü birden)')
    ap.add_argument('-o', '--outdir', default=None,
                    help='çıktı dizini (varsayılan docs/dev/)')
    ap.add_argument('--supurme', action='store_true',
                    help='seçim alanlarının BÜTÜN seçeneklerini dene '
                         '(ölçüldü: 124 ek çağrı ≈ 116 sn, üç sayfa). '
                         'Kapalıyken kırık seçeneği bilinen alanlar '
                         '(SUPURULEN_ALANLAR) yine süpürülür — defter '
                         'P10B4-06')
    ap.add_argument('--erime-yok', action='store_true',
                    help='"sabit" sayısının ölçüm gücüne bağlılığını ÖLÇME '
                         '(hızlı); kapı hükmü o zaman yayımlanmaz — '
                         'defter P10B4-07')
    ap.add_argument('--uclar', action='store_true',
                    help='ÜÇ SAYFANIN ÖTESİ: merkezî uç-yükü kataloğundaki '
                         '(tests/support/uc_katalogu) bütün ölçülebilir POST '
                         'uçlarında sarsım matrisini koşar ve uç kapsamı '
                         'sayfasını yazar — defter P10B4-16')
    ap.add_argument('--uclar-sinir', type=int, default=None,
                    help='--uclar ile ölçülecek uç sayısını sınırla (hızlı '
                         'kuru koşum); sınırlıysa kapsam sayfası bunu ADIYLA '
                         'yazar')
    ap.add_argument('--yalniz-uclar', action='store_true',
                    help='yalnız uç kapsamını ölç, üç sayfa haritasını '
                         'üretme')
    args = ap.parse_args()

    from hrma.app import app
    client = app.test_client()

    pages = [] if args.yalniz_uclar else (
        sorted(PAGES) if args.page == 'all' else [args.page])
    outdir = pathlib.Path(args.outdir) if args.outdir else (ROOT / 'docs' / 'dev')
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y-%m-%d %H:%M')

    written = []
    erimeler: Dict[str, Any] = {}
    for page in pages:
        t0 = time.perf_counter()
        print(f'ölçülüyor: {page} ...', file=sys.stderr)
        try:
            if page == 'hybrid':
                report, inv, tmap, _ = measure_hybrid(
                    client, probe_all_options=args.supurme)
            else:
                report, inv, tmap, _ = measure_page(
                    client, page, probe_all_options=args.supurme)
        except Exception as exc:
            # Bir sayfa ölçülemezse diğerleri yine üretilir; sessiz geçmez.
            print(f'  ATLANDI ({page}): {exc}', file=sys.stderr)
            continue
        dt = time.perf_counter() - t0
        print(f'  {report.summary()}  ({dt:.0f} sn)', file=sys.stderr)
        # ÖH D19 / P10B4-07 — erime ölçümü. Şablon ölçümü ZATEN elde;
        # ikinci kez koşulmaz (``report=`` ile geçilir).
        erime = None
        if not args.erime_yok:
            t1 = time.perf_counter()
            try:
                erime = erime_olc(client, page, report)
                print('  erime: %d/%d (%%%.1f)  (%.0f sn)'
                      % (erime['eriyen'], erime['toplam'], erime['yuzde'],
                         time.perf_counter() - t1), file=sys.stderr)
            except Exception as exc:
                # Ölçülemedi = "temiz" DEĞİL. Hüküm yayımlanmaz.
                print(f'  erime ÖLÇÜLEMEDİ ({page}): {exc}', file=sys.stderr)
                erime = None
        erimeler[page] = erime
        out = outdir / f'wiring_map_{page}.html'
        out.write_text(build_html(page, report, inv, tmap, stamp, erime),
                       encoding='utf-8')
        written.append((page, out, report))

    # --- UÇ KAPSAMI (defter P10B4-16) ----------------------------------
    uc_cikti = None
    if args.uclar or args.yalniz_uclar:
        def _ilerleme(yol, ozet):
            if ozet.get('olculdu'):
                print('  %-42s %2d alan · %2d ölü · %3d sabit (%.0f sn)'
                      % (yol, ozet['alan'], len(ozet['olu']),
                         ozet['sabit_cikti'], ozet['sn']), file=sys.stderr)
            else:
                print('  %-42s ÖLÇÜLEMEDİ: %s' % (yol, ozet['gerekce']),
                      file=sys.stderr)
        print('uç kapsamı ölçülüyor ...', file=sys.stderr)
        olcumler = measure_endpoints(client, sinir=args.uclar_sinir,
                                     ilerleme=_ilerleme)
        kapsam = uc_kapsami(app, olcumler)
        if args.uclar_sinir is not None:
            kapsam['sinir'] = args.uclar_sinir
        uc_cikti = outdir / 'wiring_uclar.html'
        uc_cikti.write_text(build_uc_kapsami_html(kapsam, stamp),
                            encoding='utf-8')
        (outdir / 'wiring_uclar.json').write_text(
            json.dumps(kapsam, ensure_ascii=False, indent=1), encoding='utf-8')
        print('yazıldı: %s' % uc_cikti, file=sys.stderr)
        print('yazıldı: %s' % (outdir / 'wiring_uclar.json'), file=sys.stderr)

    if not written:
        if uc_cikti is not None:
            return 0
        print('hiçbir sayfa ölçülemedi', file=sys.stderr)
        return 1

    index = outdir / 'wiring_map.html'
    index.write_text(build_index(written, stamp, erimeler), encoding='utf-8')
    for _page, out, _r in written:
        print(f'yazıldı: {out}', file=sys.stderr)
    print(f'yazıldı: {index}  (giriş sayfası)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
