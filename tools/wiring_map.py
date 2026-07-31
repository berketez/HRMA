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

Yani harita, kodun o anki GERÇEK davranışıdır. Kod değişince yeniden üretilir
ve yeni gerçeği gösterir. Elle tutulan bir mimari şeması gibi eskimez.

Kullanım
--------
    python3 tools/wiring_map.py                  # üç motor tipi
    python3 tools/wiring_map.py --page hybrid    # tek sayfa (hızlı)
    python3 tools/wiring_map.py -o /tmp/map.html

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
from typing import Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.support import inventory, shake  # noqa: E402


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
        'star_radius': {'grain_type': 'star', 'star_points': 6,
                        'star_radius': 18},
        'star_fillet': {'grain_type': 'star', 'star_points': 6,
                        'star_fillet': 3},
        'fin_length': {'grain_type': 'finocyl', 'fin_count': 6,
                       'fin_length': 25},
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


def measure_page(client, page: str):
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
                       declared_unwired=declared)
    return report, inv, template_of_payload, template_specs


def measure_hybrid(client):
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
                       declared_unwired=cfg['declared_unused'])
    return report, inv, template_of_payload, template_specs


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
    d.innerHTML = esc(f.template) + (n?'<span class="n">'+n+'</span>':'');
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
    d.innerHTML = label;
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


def build_html(page: str, report, inv, template_of_payload, generated_at: str) -> str:
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
    }
    payload_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

    measured = (len(report.live_inputs) + len(report.dead_inputs)
                + len(report.echo_only_inputs))
    meta = (f'{page} &middot; {measured} alan ölçüldü &middot; '
            f'{report.baseline_leaf_count} çıktı yaprağı &middot; {generated_at}')

    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>HRMA bağlama haritası — {html.escape(page)}</title>
<style>{_CSS}</style></head><body>
<header>
  <h1>HRMA bağlama haritası</h1>
  <span class="meta">{meta}</span>
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


def build_index(written, generated_at: str) -> str:
    """Üç sayfanın giriş sayfası."""
    cards = []
    for page, out, rep in written:
        measured = (len(rep.live_inputs) + len(rep.dead_inputs)
                    + len(rep.echo_only_inputs))
        problems = len(rep.dead_inputs) + len(rep.echo_only_inputs)
        badge = ('temiz' if problems == 0
                 else f'{problems} sorunlu alan')
        cls = 'ok' if problems == 0 else 'warn'
        cards.append(f"""
        <a class="card {cls}" href="{html.escape(out.name)}">
          <h2>{html.escape(page)}</h2>
          <div class="big">{measured}</div>
          <div class="lbl">alan ölçüldü</div>
          <div class="tags">
            <span>{len(rep.live_inputs)} bağlı</span>
            <span class="bad">{len(rep.dead_inputs)} ölü</span>
            <span class="amb">{len(rep.echo_only_inputs)} yankı</span>
            <span class="amb">{len(rep.constant_outputs)} sabit çıktı</span>
          </div>
          <div class="badge">{badge}</div>
        </a>""")
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
  <div class="cards">{''.join(cards)}</div>
  <p class="note">Bu harita ÖLÇÜMDEN üretilir, elle düzenlenmez. Her alan
  gerçek bir hesap koşularak sarsılır ve yanıtın hangi dallarının değiştiği
  kaydedilir. Kod değişince <code>python3 tools/wiring_map.py</code> ile
  yeniden üretilir.<br><br>
  Sabit çıktı sayısı bir BULGU değil, BAKILACAK YER'dir: yalnız ölçülen
  alanlar için anlamlıdır, sarsılmayan bir girdinin etkilediği çıktı da
  orada sabit görünür.</p>
</div></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--page', default='all',
                    choices=sorted(PAGES) + ['all'],
                    help='ölçülecek sayfa (varsayılan: all = üçü birden)')
    ap.add_argument('-o', '--outdir', default=None,
                    help='çıktı dizini (varsayılan docs/dev/)')
    args = ap.parse_args()

    from hrma.app import app
    client = app.test_client()

    pages = sorted(PAGES) if args.page == 'all' else [args.page]
    outdir = pathlib.Path(args.outdir) if args.outdir else (ROOT / 'docs' / 'dev')
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y-%m-%d %H:%M')

    written = []
    for page in pages:
        t0 = time.perf_counter()
        print(f'ölçülüyor: {page} ...', file=sys.stderr)
        try:
            if page == 'hybrid':
                report, inv, tmap, _ = measure_hybrid(client)
            else:
                report, inv, tmap, _ = measure_page(client, page)
        except Exception as exc:
            # Bir sayfa ölçülemezse diğerleri yine üretilir; sessiz geçmez.
            print(f'  ATLANDI ({page}): {exc}', file=sys.stderr)
            continue
        dt = time.perf_counter() - t0
        print(f'  {report.summary()}  ({dt:.0f} sn)', file=sys.stderr)
        out = outdir / f'wiring_map_{page}.html'
        out.write_text(build_html(page, report, inv, tmap, stamp),
                       encoding='utf-8')
        written.append((page, out, report))

    if not written:
        print('hiçbir sayfa ölçülemedi', file=sys.stderr)
        return 1

    index = outdir / 'wiring_map.html'
    index.write_text(build_index(written, stamp), encoding='utf-8')
    for _page, out, _r in written:
        print(f'yazıldı: {out}', file=sys.stderr)
    print(f'yazıldı: {index}  (giriş sayfası)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
