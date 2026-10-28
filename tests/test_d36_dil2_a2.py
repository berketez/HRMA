# -*- coding: utf-8 -*-
"""ÖH D36 · 2. aşama · kulvar ``dil2-i18n-pdf`` (a2) bekçileri.

Kanıt paketi: ``docs/scofield/raw/OH/D36/dil2-i18n-pdf/a2/`` (``once.json``
taban bb7ee57c dondurulmuş ağaçta, ``sonra.json`` kulvarda, aynı
``olcum.py`` ile — o betik ölçüm düzeneklerini BU dosyadan içe aktarır;
tarayıcı ölçümü ``olcum_tarayici.py``; ``mutasyon.md``; ``rapor.md``).

Kalemler:

  K4  Güvenlik paneli ``explosiveBasisBlock`` / ``toxicBasisBlock`` (D35 pdf
      kulvarı devri 2): uçtan inen geri çekme gerekçeleri ekranda adıyla;
      alan yoksa blok çizilmez; TR'de gerekçe cümleleri Türkçe.
  K5  Plotly figür metinlerinde TR ondalık (OH-P-11 geniş kök):
      ``layout.separators`` TR'de ``',.'``, literal ondalıklar virgül;
      ``%{...}``, sürüm dizesi, HTML/URL içi, veri eksenleri dokunulmaz; EN
      değişmez; yerel ayar (katı kulvarı) ile idempotent.
  K6  fea_panel.js'in sözlüğe giden bütün anahtarları EN+TR sözlükte (node
      ile ölçülür) ve seçenek etiketleri ``data-i18n`` taşır (OH-GT devri).
  K7  Taban kırmızısı: enjektör imalat bandı uyarısı TR ``serverText``
      çevirisi (``tests/test_i18n_charts.py`` kapsam bekçisi %92,3 -> yeşil).

Kaynak okuyan bekçiler kaynağı DOSYADAN okur (``inspect.getsource`` yok).
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC_JS = ROOT / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _oku(yol):
    return Path(yol).read_text(encoding='utf-8')


# ===========================================================================
# Ölçüm ve bekçi ORTAK düzenekleri. ``docs/.../a2/olcum.py`` bunları BURADAN
# içe aktarır (yön: kanıt -> test; test docs/'a bağlı DEĞİL, docs'suz yayın
# dalında da koşar).
# ===========================================================================
import html as _html  # noqa: E402

#: Patlayıcı ekseni GERİ ÇEKİLEN güvenlik isteği (kimliksiz 'apcp', motor
#: tipi yok — D35 OH-ON-06 ölçümündeki hâl); toksik hüküm de geri çekilir.
SAFETY_WITHHELD = {
    'chamber_pressure': 40.0, 'chamber_temperature': 3000.0,
    'propellant_mass': 5.0, 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'wall_thickness': 0.005, 'thrust': 1000.0, 'burn_time': 10.0,
    'propellant_type': 'apcp', 'facility_type': 'test_stand',
    'material': 'steel_4130',
}
#: Hüküm VERİLEN istek (tabloda sınıf: composite, katı motor).
SAFETY_EVALUATED = dict(SAFETY_WITHHELD, propellant_type='composite',
                        motor_type='solid')

#: Taban kırmızısının gerçek mesajı (test_i18n_charts.py çıktısı, bb7ee57c).
ENJEKTOR_BANT = (
    'Solved orifice diameter 2.1515 mm is outside the manufacturing band '
    '(0.30-2.00 mm). The hole plan comes from the injector circuit solution '
    'and is NOT resized here: resizing would publish a second, different '
    'injector in the same answer. Either widen the band or change the feed '
    'pressure / orifice count.')

I18N_DOSYALARI = ['i18n.js', 'i18n_common.js', 'i18n_shell.js', 'i18n_pages.js',
                  'i18n_advanced.js', 'i18n_formulas.js', 'i18n_launch_site.js',
                  'i18n_charts.js']


def node_calistir(kok, script_metni, yuk, tmpdir, ad):
    """Düzeneği ``node <script> <kok> <girdi.json>`` ile koşar, JSON döner."""
    script = os.path.join(str(tmpdir), ad + '.js')
    with open(script, 'w', encoding='utf-8') as fh:
        fh.write(script_metni)
    girdi = os.path.join(str(tmpdir), ad + '.json')
    with open(girdi, 'w', encoding='utf-8') as fh:
        json.dump(yuk, fh)
    p = subprocess.run([NODE or 'node', script, str(kok), girdi], capture_output=True,
                       text=True, timeout=180)
    if p.returncode != 0:
        return {'error': p.stderr[-2000:]}
    return json.loads(p.stdout)


DOCK_HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const [rootDir, payloadPath] = process.argv.slice(2);
const cfg = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
function makeNode(id) {
    return { id: id, __html: '', textContent: '', style: {}, attrs: {}, children: [], value: '',
        classList: { contains: function () { return false; }, add: function () {}, remove: function () {} },
        setAttribute: function (k, v) { this.attrs[k] = String(v); },
        getAttribute: function (k) { return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild: function (c) { this.children.push(c); return c; },
        querySelector: function () { return makeNode('q'); },
        querySelectorAll: function () { return []; },
        addEventListener: function () {},
        get innerHTML() { return this.__html; }, set innerHTML(v) { this.__html = v; } };
}
function deepText(n) { if (!n) return ''; let s = String(n.innerHTML || '');
    (n.children || []).forEach(function (c) { s += deepText(c); }); return s; }
const nodes = {};
global.document = { head: makeNode('head'), body: makeNode('body'),
    getElementById: function (id) { if (!(id in nodes)) nodes[id] = makeNode(id); return nodes[id]; },
    createElement: function () { return makeNode(null); },
    querySelector: function () { return makeNode('q'); }, querySelectorAll: function () { return []; },
    addEventListener: function () {} };
global.window = global;
try { Object.defineProperty(global, 'navigator', { value: { language: 'en' }, configurable: true }); } catch (e) {}
global.localStorage = { getItem: function () { return null; }, setItem: function () {} };
global.requestAnimationFrame = function (fn) { fn(0); return 1; };
global.fetch = function () { return Promise.resolve({ ok: false, json: function () { return {}; } }); };
(cfg.preFiles || []).forEach(function (f) { require(path.join(rootDir, f)); });
if (cfg.lang && window.I18N && window.I18N.setLang) window.I18N.setLang(cfg.lang);
require(path.join(rootDir, 'hrma/static/js/analysis_dock.js'));
(cfg.panelFiles || []).forEach(function (f) { require(path.join(rootDir, f)); });
const spec = (window.AnalysisDock._registry || []).filter(function (p) { return p.id === cfg.panelId; })[0];
if (!spec) { process.stdout.write(JSON.stringify({ error: 'panel kayıtlı değil' })); }
else {
    const root = makeNode('root'); let err = null;
    try { spec.render(cfg.body, root); } catch (e) { err = String((e && e.stack) || e); }
    const html = deepText(root);
    process.stdout.write(JSON.stringify({ error: err, html: html,
        text: html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim() }));
}
"""


def panel_ciz(kok, veri, dil, tmpdir, ad):
    return node_calistir(kok, DOCK_HARNESS_JS, {
        'panelId': 'safety', 'body': veri, 'lang': dil,
        'preFiles': ['hrma/static/js/i18n.js', 'hrma/static/js/i18n_common.js',
                     'hrma/static/js/i18n_charts.js'],
        'panelFiles': ['hrma/static/js/panels/safety_panel.js']}, tmpdir, ad)


def k4_olc(istemci, kok, tmpdir):
    out = {}
    for durum, govde in (('geri_cekilen', SAFETY_WITHHELD),
                         ('hukum_verilen', SAFETY_EVALUATED)):
        r = istemci.post('/analyze_safety', json=govde)
        if r.status_code != 200:
            out[durum] = {'durum': r.status_code}
            continue
        veri = r.get_json()
        eh = (veri.get('safety_analysis') or {}).get('explosive_hazards') or {}
        tb = veri.get('toxic_basis') or {}
        kayit = {'durum': 200,
                 'uc_explosive_verdict_withheld_because': eh.get('explosive_verdict_withheld_because'),
                 'uc_requirements_scope': eh.get('requirements_scope'),
                 'uc_toxic_basis_alanlari': sorted(tb.keys()),
                 'uc_toxic_hazard_level_withheld_because': tb.get('toxic_hazard_level_withheld_because')}
        for dil in ('en', 'tr'):
            ciz = panel_ciz(kok, veri, dil, tmpdir, 'k4_%s_%s' % (durum, dil))
            if ciz.get('error'):
                kayit[dil] = {'error': ciz['error'][:600]}
                continue
            metin = _html.unescape(ciz['text'])
            h = ciz['html']
            kayit[dil] = {
                'explosive_verdict_withheld_because_etiketi': h.count('data-safety-field="explosive_verdict_withheld_because"'),
                'requirements_scope_etiketi': h.count('data-safety-field="requirements_scope"'),
                'toxic_basis_bolumu': h.count('data-safety-basis="toxic_basis"'),
                'explosive_basis_bolumu': h.count('data-safety-basis="explosive_verdict"'),
                'toxic_hazard_level_withheld_because_etiketi': h.count('data-safety-field="toxic_hazard_level_withheld_because"'),
                'toxic_inventory_basis_etiketi': h.count('data-safety-field="toxic_inventory_basis"'),
                'requirements_scope_ingilizce_metin': metin.count('Unconditional items only'),
                'toxic_withheld_ingilizce_metin': metin.count('No toxic inventory could be identified'),
                'explosive_withheld_ingilizce_metin': metin.count('is not a tabulated class and no motor_type was supplied'),
                'tr_ornek': [s for s in ('TNT eşdeğeri', 'toksik envanter', 'Koşulsuz maddeler',
                                         'Patlayıcı hükmü', 'Toksik hükmün')
                             if s in metin],
            }
        out[durum] = kayit
    return out


PLOTLY_DUZENEK = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
function makeDoc() { const listeners = {}; return { readyState: 'complete',
    documentElement: { setAttribute() {}, appendChild() {} }, head: { appendChild() {} }, body: { appendChild() {} },
    createElement: () => ({ setAttribute() {}, appendChild() {}, style: {} }), getElementById: () => null,
    querySelector: (s) => (String(s).indexOf('i18n_charts.js') >= 0 ? {} : null), querySelectorAll: () => [],
    addEventListener: (n, f) => { (listeners[n] = listeners[n] || []).push(f); },
    dispatchEvent: (ev) => { (listeners[ev.type] || []).forEach((f) => f(ev)); return true; } }; }
const calls = [];
const sandbox = { console, setTimeout, clearTimeout, setInterval, clearInterval, JSON, Object, Array, Math, RegExp,
    String, Number, Boolean, Date, Error, parseFloat, parseInt, isNaN, isFinite };
sandbox.window = sandbox; sandbox.self = sandbox; sandbox.document = makeDoc(); sandbox.localStorage = null;
sandbox.CustomEvent = function (t, i) { this.type = t; this.detail = (i && i.detail) || null; };
sandbox.Plotly = { newPlot(el, data, layout) { calls.push({ data, layout }); }, react(el, data, layout) { calls.push({ data, layout }); } };
vm.createContext(sandbox);
for (const f of ['i18n.js', 'i18n_common.js', 'i18n_charts.js', 'plotly_dark.js']) {
    vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/' + f, 'utf8'), sandbox, { filename: f }); }
function ozet(c) {
    /* Derin kopya: aynı figür nesnesi sonraki çağrıda yerinde değişir
       (tablo hücre dizisi yerinde güncellenir), özet o ANIN hâlidir. */
    return JSON.parse(JSON.stringify({ separators: c.layout.separators === undefined ? null : c.layout.separators,
        annotations: (c.layout.annotations || []).map((a) => a.text),
        title: c.layout.title && (c.layout.title.text || c.layout.title),
        xaxis_title: c.layout.xaxis && c.layout.xaxis.title && (c.layout.xaxis.title.text || c.layout.xaxis.title),
        ticktext: c.layout.xaxis && c.layout.xaxis.ticktext,
        x: c.data[0].x, text: c.data[0].text, hovertemplate: c.data[0].hovertemplate, name: c.data[0].name,
        hovertext: c.data[1] && c.data[1].hovertext, cells: c.data[2] && c.data[2].cells && c.data[2].cells.values,
        x_sayisal_kategori: c.data[3] && c.data[3].x }));
}
const out = {};
for (const lang of ['tr', 'en']) {
    sandbox.I18N.setLang(lang);
    const fig = JSON.parse(JSON.stringify(JOB.figure));
    sandbox.Plotly.newPlot('d', fig.data, fig.layout);
    out[lang] = ozet(calls[calls.length - 1]);
}
/* Yerel ayar SAHİBİ çağıran (katı kulvarının solid.html yerel ayarı):
   TR'de ',.' zaten yazılmış figür ikinci kez işlenince aynı kalmalı. */
sandbox.I18N.setLang('tr');
const yerel = JSON.parse(JSON.stringify(JOB.figure)); yerel.layout.separators = ',.';
yerel.data[0].text = ['6,81', '1,5 kg'];
sandbox.Plotly.newPlot('d', yerel.data, yerel.layout);
out.tr_yerel_ayarli = ozet(calls[calls.length - 1]);
/* Dil gidiş-dönüşü: aynı nesne TR -> EN -> TR (redrawAllPlots yolu:
   Plotly.react(gd, gd.data, gd.layout) aynı nesneleri yeniden verir). */
const gd = JSON.parse(JSON.stringify(JOB.figure));
sandbox.I18N.setLang('tr'); sandbox.Plotly.react('d', gd.data, gd.layout);
sandbox.I18N.setLang('en'); sandbox.Plotly.react('d', gd.data, gd.layout);
out.gidis_donus_en = ozet(calls[calls.length - 1]);
sandbox.I18N.setLang('tr'); sandbox.Plotly.react('d', gd.data, gd.layout);
out.gidis_donus_tr = ozet(calls[calls.length - 1]);
process.stdout.write(JSON.stringify(out));
"""

K5_ORNEK_FIGUR = {
    'data': [
        {'type': 'bar', 'x': ['Total', 'Oxidizer'], 'y': [6.81, 1.5],
         'text': ['6.81', '1.5 kg'], 'name': 'Thrust 2.5',
         'hovertemplate': 'Isp: %{y:.2f} s<br>eta = 0.98<extra></extra>'},
        {'type': 'scatter', 'x': [0, 1], 'y': [1, 2], 'hovertext': ['v2.6.27', 'k = 1.25']},
        {'type': 'table', 'cells': {'values': [['Pc', 'Isp'], ['30.5 bar', '239.7 s']]}},
        # Sayısal DİZE kategori ekseni: veri kimliği, ondalık dönüşümü görmez.
        {'type': 'bar', 'x': ['0.5', '1.5'], 'y': [1, 2]},
    ],
    'layout': {
        'title': {'text': 'HRMA v2.6.27 report, eps 4.5'},
        'xaxis': {'title': 'Chamber Pressure (bar) 30.5', 'ticktext': ['0.5', '1.0'], 'tickvals': [0, 1]},
        'annotations': [{'text': 'Isp = 250.5 s'},
                        {'text': '<b>Cf</b> 1.75 <a href="http://x.y/1.5">link 2.5</a>'},
                        {'text': 'dt=1.5e-3 s, 1.25x, 10.5%'},
                        {'text': 'Sutton Eq. 3.25, doi:10.2514/1.B35869, Table 4.1'},
                        {'text': 'K_c = 0.00 < 1.5 (P_1 = 50.4 bar)<br>build 2.6.27'}],
    },
}


def k5_olc(kok, tmpdir):
    return node_calistir(kok, PLOTLY_DUZENEK, {'figure': K5_ORNEK_FIGUR}, tmpdir, 'k5')


FEA_ANAHTAR_JS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sandbox = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error, parseFloat, parseInt, isNaN, isFinite };
sandbox.window = sandbox; sandbox.self = sandbox; sandbox.localStorage = null;
sandbox.document = { readyState: 'loading', documentElement: { setAttribute() {} }, addEventListener() {},
    querySelectorAll: () => [], querySelector: () => null, getElementById: () => null };
vm.createContext(sandbox);
for (const f of JOB.files) {
    vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/' + f, 'utf8'), sandbox, { filename: f }); }
const I = sandbox.I18N;
const out = { eksik_tr: [], eksik_en_ve_tr: [], tr_kopya_en: [], toplam: JOB.keys.length };
for (const k of JOB.keys) {
    I.setLang('en'); const enVar = I.has(k); const en = enVar ? I.t(k) : null;
    I.setLang('tr'); const trVar = I.has(k); const tr = trVar ? I.t(k) : null;
    if (!enVar && !trVar) out.eksik_en_ve_tr.push(k);
    else if (!trVar) out.eksik_tr.push(k);
    else if (enVar && tr === en && /[a-z]{3}/i.test(en)) out.tr_kopya_en.push(k + ' = ' + en);
}
process.stdout.write(JSON.stringify(out));
"""


def fea_anahtarlari(kok):
    """fea_panel.js'in sözlüğe giden BÜTÜN anahtarları (kaynaktan, regex)."""
    src = open(os.path.join(kok, 'hrma', 'static', 'js', 'fea_panel.js'),
               encoding='utf-8').read()
    anahtar = r"""['"]([A-Za-z][\w]*(?:\.[\w]+)+)['"]"""
    kume = set(re.findall(r'\bTF?\(\s*' + anahtar, src))
    kume |= set(re.findall(r'\b(?:acSection|acNoBlockHtml)\(\s*' + anahtar, src))
    kume |= set(re.findall(r"""data-i18n(?:-[a-z]+)?=\\?["']([\w.]+)\\?["']""", src))
    # GRAIN_FIELDS benzeri tablolar: satırın etiket ve ipucu anahtarları
    # ('panel.grain.x'). T-ÇAPA-C2 (27 Eki): v3.0.1 N-girdi-1/2 satıra 6.
    # öğe olarak '?' ipucu anahtarını ekledi; etiket anahtarı artık SON öğe
    # değil ('panel.grain.fieldOuter', 'panel.grain.help.outer']) ve tarama
    # onu kaçırıyordu. Virgülden sonra gelen ve ',' ya da ']' ile biten her
    # panel/fea/common anahtarı alınır (ikisi de sözlükte aranır).
    kume |= set(re.findall(r""",\s*\n?\s*'((?:panel|fea|common)\.[\w.]+)'\s*[\],]""", src))
    return sorted(kume)


def k6_olc(kok, tmpdir):
    anahtarlar = fea_anahtarlari(kok)
    dosyalar = [f for f in I18N_DOSYALARI if os.path.exists(os.path.join(kok, 'hrma', 'static', 'js', f))]
    sonuc = node_calistir(kok, FEA_ANAHTAR_JS, {'files': dosyalar, 'keys': anahtarlar}, tmpdir, 'k6')
    sonuc['yuklenen_sozlukler'] = dosyalar
    return sonuc


SERVERTEXT_JS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sandbox = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error, parseFloat, parseInt, isNaN, isFinite };
sandbox.window = sandbox; sandbox.self = sandbox; sandbox.localStorage = null;
sandbox.document = { readyState: 'loading', documentElement: { setAttribute() {} }, addEventListener() {},
    querySelectorAll: () => [], querySelector: () => null, getElementById: () => null };
vm.createContext(sandbox);
for (const f of ['i18n.js', 'i18n_common.js', 'i18n_charts.js']) {
    vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/' + f, 'utf8'), sandbox, { filename: f }); }
const out = {};
for (const lang of ['tr', 'en']) { sandbox.I18N.setLang(lang); out[lang] = JOB.msgs.map((m) => sandbox.I18N.serverText(m)); }
process.stdout.write(JSON.stringify(out));
"""



# ===========================================================================
# K6 — fea_panel.js anahtarları + seçenek etiketleri
# ===========================================================================
@node_gerek
def test_k6_fea_panel_butun_anahtarlar_EN_ve_TR_sozlukte(tmp_path):
    """Node ortamında I18N çekirdeği + bütün i18n_*.js yüklenir; fea_panel.js'in
    T/TF/data-i18n/acSection/acNoBlockHtml/GRAIN_FIELDS anahtarlarının HER biri
    iki dilde de ``I18N.has``. (Ölçüldü: 88 anahtar, taban bb7ee57c'de de eksik
    0 — bekçi bu hâli kilitler.)"""
    anahtarlar = fea_anahtarlari(str(ROOT))
    assert len(anahtarlar) >= 85, 'fea_panel.js anahtar taraması daraldı: %d' % len(anahtarlar)
    for k in ('fea.metricAspect', 'fea.metricJacobian', 'fea.qualityMetric',
              'panel.grain.fieldOuter'):
        assert k in anahtarlar, '%s taramada yok (dolaylı anahtar kaçıyor)' % k
    dosyalar = [f for f in I18N_DOSYALARI if (STATIC_JS / f).exists()]
    sonuc = node_calistir(ROOT, FEA_ANAHTAR_JS, {'files': dosyalar, 'keys': anahtarlar}, tmp_path, 'k6')
    assert 'error' not in sonuc, sonuc
    assert sonuc['eksik_tr'] == [], 'TR sözlükte yok: %s' % sonuc['eksik_tr']
    assert sonuc['eksik_en_ve_tr'] == [], 'iki dilde de yok: %s' % sonuc['eksik_en_ve_tr']
    # Tek bilinen TR==EN kopyası özel addır + birim ('von Mises [MPa]').
    assert all(k.startswith('fea.cbarVm') for k in sonuc['tr_kopya_en']), sonuc['tr_kopya_en']


def test_k6_T_ile_basilan_her_secenek_data_i18n_tasir():
    """``<option>`` metni ``T('anahtar', ...)`` ile basılıyorsa AYNI anahtarı
    ``data-i18n`` ile taşır: dil değişiminde ``I18N.apply`` yalnız işaretli
    düğümü çevirir. (Taban bb7ee57c: ``#fea_metric`` iki seçeneği özniteliksiz.)"""
    src = _oku(STATIC_JS / 'fea_panel.js')
    secenekler = re.findall(
        r"""<option\b([^>]*)>\s*(?:\$\{|'\s*\+\s*esc\()\s*T\(\s*['"]([\w.]+)['"]""", src)
    bulunan = {k for _, k in secenekler}
    assert {'fea.metricAspect', 'fea.metricJacobian'} <= bulunan, bulunan
    # Merkez kopyası öznitelik ile T() arasında satır kırıyor: ayrıca tara.
    for oznitelik, anahtar in secenekler:
        assert 'data-i18n="%s"' % anahtar in oznitelik, (
            '<option%s> metni T(%r) ile basılıyor ama data-i18n yok' % (oznitelik, anahtar))


# ===========================================================================
# K7 — enjektör imalat bandı uyarısı (taban kırmızısı)
# ===========================================================================
@node_gerek
def test_k7_enjektor_bant_uyarisi_TR_ve_ondalik_virgul(tmp_path):
    sonuc = node_calistir(ROOT, SERVERTEXT_JS, {'msgs': [
        ENJEKTOR_BANT,
        ENJEKTOR_BANT.replace('2.1515', '0.2500').replace('0.30-2.00', '0.35-1.80'),
    ]}, tmp_path, 'k7')
    assert 'error' not in sonuc, sonuc
    tr, tr2 = sonuc['tr']
    assert tr == ('Çözülen orifis çapı 2,1515 mm, imalat bandının (0,30-2,00 mm) '
                  'dışında. Delik planı enjektör devresi çözümünden gelir ve burada '
                  'yeniden BOYUTLANDIRILMAZ: yeniden boyutlandırmak aynı yanıtta '
                  'ikinci, farklı bir enjektör yayımlamak olurdu. Ya bandı genişletin '
                  'ya da besleme basıncını / orifis sayısını değiştirin.'), tr
    assert '0,2500 mm' in tr2 and '(0,35-1,80 mm)' in tr2, tr2
    assert not re.search(r'\d\.\d', tr + tr2), 'TR metinde noktalı ondalık kaldı'
    assert sonuc['en'] == [ENJEKTOR_BANT,
                           ENJEKTOR_BANT.replace('2.1515', '0.2500').replace('0.30-2.00', '0.35-1.80')]


def test_k7_desen_ureticinin_cumlesiyle_ayni():
    """Desen üreticinin (``injector_design.py``) sabit gövdesini birebir
    taşır: üretici cümleyi değiştirirse bu bekçi düşer (sessiz İngilizce yok)."""
    uretici = _oku(ROOT / 'hrma' / 'utils' / 'injector_design.py')
    for parca in ('is outside ', 'the manufacturing band ',
                  'The hole plan comes ', 'from the injector circuit solution and is NOT resized ',
                  'here: resizing would publish a second, different ',
                  'injector in the same answer. Either widen the band or ',
                  'change the feed pressure / orifice count.'):
        assert parca in uretici, 'üretici cümlesi değişti: %r' % parca
    desenler = _oku(STATIC_JS / 'i18n_charts.js')
    assert 'Solved orifice diameter (\\S+) mm is outside the manufacturing band' in desenler


# ===========================================================================
# K4 — güvenlik paneli: patlayıcı ve toksik hüküm künyesi
# ===========================================================================
@pytest.fixture(scope='module')
def istemci():
    os.environ.setdefault('HRMA_HEADLESS', '1')
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def k4(istemci, tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    return k4_olc(istemci, ROOT, tmp_path_factory.mktemp('k4'))


def test_k4_uc_alanlari_yayimliyor(k4):
    """Sözleşmenin öbür ucu: alan adları ÖLÇÜLEREK alındı; uç adı değiştirirse
    panel sessizce boş kalmasın diye bekçi uçtan da okur."""
    g = k4['geri_cekilen']
    assert g['durum'] == 200
    assert g['uc_explosive_verdict_withheld_because']
    assert g['uc_requirements_scope']
    assert g['uc_toxic_hazard_level_withheld_because']
    for alan in ('toxic_inventory_basis', 'toxic_inventory_resolution', '_basis',
                 'propellant_class', 'known_propellant_classes'):
        assert alan in g['uc_toxic_basis_alanlari'], alan
    assert k4['hukum_verilen']['uc_explosive_verdict_withheld_because'] is None


@pytest.mark.parametrize('dil', ['en', 'tr'])
def test_k4_geri_cekilen_istekte_gerekceler_adiyla(k4, dil):
    e = k4['geri_cekilen'][dil]
    assert 'error' not in e, e
    assert e['explosive_basis_bolumu'] == 1
    assert e['explosive_verdict_withheld_because_etiketi'] == 1
    assert e['requirements_scope_etiketi'] == 1
    assert e['toxic_basis_bolumu'] == 1
    assert e['toxic_hazard_level_withheld_because_etiketi'] == 1
    assert e['toxic_inventory_basis_etiketi'] == 1


def test_k4_TR_gerekceler_turkce(k4):
    tr = k4['geri_cekilen']['tr']
    assert tr['requirements_scope_ingilizce_metin'] == 0
    assert tr['toxic_withheld_ingilizce_metin'] == 0
    for s in ('TNT eşdeğeri', 'toksik envanter', 'Patlayıcı hükmü', 'Toksik hükmün'):
        assert s in tr['tr_ornek'], (s, tr['tr_ornek'])
    en = k4['geri_cekilen']['en']
    assert en['requirements_scope_ingilizce_metin'] == 1
    assert en['toxic_withheld_ingilizce_metin'] == 1


@pytest.mark.parametrize('dil', ['en', 'tr'])
def test_k4_hukum_verilen_istekte_patlayici_blogu_CIZILMEZ(k4, dil):
    e = k4['hukum_verilen'][dil]
    assert e['explosive_basis_bolumu'] == 0
    assert e['explosive_verdict_withheld_because_etiketi'] == 0
    assert e['requirements_scope_etiketi'] == 0
    # Toksik künye uç yayımladıkça çizilir (termal künye gibi); geri çekme
    # satırı yoktur çünkü uç o alanı yayımlamadı.
    assert e['toxic_basis_bolumu'] == 1
    assert e['toxic_hazard_level_withheld_because_etiketi'] == 0


@node_gerek
def test_k4_alan_yoksa_hicbir_blok_cizilmez(tmp_path):
    """Yanıtta ne ``toxic_basis`` ne patlayıcı geri çekme alanı varsa iki
    blok da HİÇ çizilmez (fail-closed: boş başlık yok)."""
    ciz = panel_ciz(ROOT, {'safety_analysis': {'explosive_hazards': {
        'explosive_class': 'composite', 'propellant_mass_kg': 5.0}}},
        'en', tmp_path, 'bos')
    assert not ciz.get('error'), ciz.get('error')
    assert 'data-safety-basis=' not in ciz['html']
    assert 'explosive_verdict_withheld_because' not in ciz['html']


def test_k4_kaynakta_iki_blok_render_zincirinde():
    src = _oku(STATIC_JS / 'panels' / 'safety_panel.js')
    assert re.search(r'function explosiveBasisBlock\(b\)', src)
    assert re.search(r'function toxicBasisBlock\(basis\)', src)
    assert 'html += explosiveBasisBlock(s.explosive_hazards);' in src
    assert 'html += toxicBasisBlock(data.toxic_basis);' in src


def test_k4_yedekli_anahtarlar_iki_sozlukte():
    """Yedekli ``T('x', 'fallback')`` çağrısının anahtarı iki sözlükte de
    (yedekle yaşayan anahtar TR'de İngilizce görünür)."""
    src = _oku(STATIC_JS / 'i18n_common.js')
    en_bas = src.index('en: {')
    tr_bas = src.index('tr: {')
    for k in ('panel.safety.secExplosiveBasis', 'panel.safety.explosiveWithheldNote',
              'panel.safety.secToxicBasis'):
        assert src.count("'%s':" % k) == 2, k
        assert en_bas < src.index("'%s':" % k) < tr_bas < src.rindex("'%s':" % k), k


# ===========================================================================
# K5 — Plotly figür metinlerinde TR ondalık
# ===========================================================================
@pytest.fixture(scope='module')
def k5(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    return k5_olc(ROOT, tmp_path_factory.mktemp('k5'))


def test_k5_TR_ayrac_ve_literal_ondalik(k5):
    tr = k5['tr']
    assert tr['separators'] == ',.'
    assert tr['text'] == ['6,81', '1,5 kg']
    assert tr['ticktext'] == ['0,5', '1,0']
    assert tr['xaxis_title'] == 'Oda basıncı (bar) 30,5'
    assert tr['name'] == 'İtki 2,5'
    assert tr['cells'] == [['Pc', 'Isp'], ['30,5 bar', '239,7 s']]
    assert tr['annotations'][0] == 'Isp = 250,5 s'
    assert tr['annotations'][2] == 'dt=1,5e-3 s, 1,25x, 10,5%'


def test_k5_TR_dokunulmayanlar(k5):
    tr = k5['tr']
    assert tr['hovertemplate'] == 'Isp: %{y:.2f} s<br>eta = 0,98<extra></extra>', (
        '%{...} biçim belirteci korunmalı, literal 0.98 çevrilmeli')
    assert tr['title'] == 'HRMA v2.6.27 report, eps 4,5', 'sürüm dizesi korunmalı'
    assert tr['hovertext'] == ['v2.6.27', 'k = 1,25']
    assert tr['annotations'][1] == '<b>Cf</b> 1,75 <a href="http://x.y/1.5">link 2,5</a>', (
        'HTML özniteliği / URL korunmalı, etiket içi metin çevrilmeli')
    assert tr['annotations'][3] == 'Sutton Eq. 3.25, doi:10.2514/1.B35869, Table 4.1', (
        'denklem/tablo numarası ve DOI TR\'de de noktalı kalır')
    assert tr['x'] == ['Toplam', 'Oksitleyici']
    assert tr['x_sayisal_kategori'] == ['0.5', '1.5'], 'veri ekseni ondalık dönüşümü görmez'


def test_k5_EN_degismez(k5):
    en = k5['en']
    assert en['separators'] is None
    assert en['text'] == ['6.81', '1.5 kg']
    assert en['annotations'][0] == 'Isp = 250.5 s'
    assert en['hovertemplate'] == 'Isp: %{y:.2f} s<br>eta = 0.98<extra></extra>'
    assert en['cells'] == [['Pc', 'Isp'], ['30.5 bar', '239.7 s']]


def test_k5_yerel_ayarla_idempotent_ve_gidis_donus(k5):
    """Katı kulvarının solid.html yerel ``separators`` ayarı ile çakışmaz:
    ',.' zaten yazılıysa aynı kalır, '6,81' ikinci kez dönüştürülmez. Aynı
    figür TR -> EN -> TR yeniden çizilince (redrawAllPlots yolu) ayraç ve
    metin dile göre döner, bayat kalmaz."""
    y = k5['tr_yerel_ayarli']
    assert y['separators'] == ',.'
    assert y['text'] == ['6,81', '1,5 kg']
    en = k5['gidis_donus_en']
    assert en['separators'] in (None, '.,')
    assert en['text'] == ['6.81', '1.5 kg'] and en['cells'][1] == ['30.5 bar', '239.7 s']
    tr = k5['gidis_donus_tr']
    assert tr['separators'] == ',.' and tr['text'] == ['6,81', '1,5 kg']


def test_k5_kucuktur_isareti_etiket_degil(k5):
    """Metindeki '<' (küçüktür) HTML etiketi sayılmaz; ardındaki ondalıklar
    çevrilir, <br> etiketi ve sürüm dizesi korunur. (Ölçüldü: hibrit enjektör
    uyarı kutusunda 4 ondalık bu yüzden noktalı kalıyordu.)"""
    assert k5['tr']['annotations'][4] == 'K_c = 0,00 < 1,5 (P_1 = 50,4 bar)<br>build 2.6.27'
    assert k5['en']['annotations'][4] == 'K_c = 0.00 < 1.5 (P_1 = 50.4 bar)<br>build 2.6.27'
