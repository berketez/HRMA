# -*- coding: utf-8 -*-
"""ÖH D37 A1b · sahte-veri-b — güverte bayat önerisi, panel nöbetçileri, CAD itki yedeği.

Kart: ``docs/scofield/raw/OH/D37/ana-plan/A1b_kartlari.md`` "A1b-5".
Kanıt: ``docs/scofield/raw/OH/A1b/sahte-veri-b/a1/`` (bu dosya kanıt dizinini
OKUMAZ; docs'suz dalda da koşar).

- OH-D37-S4: ``analysis_dock.js applySuggestions`` yalnız sonlu öneriyi
  yazıyordu, alanı hiç temizlemiyordu. Süreli sıvı koşusundan sonra süresiz
  koşu yapılınca ÖNCEKİ koşunun ``burn_time`` / ``propellant_mass`` değeri
  kutuda kalıp yeni motorun isteğine kullanıcı girdisi gibi gidiyordu.
- OH-D37-S5: boş alanın çipi zorunlu / isteğe bağlı ayırmıyordu.
- OH-D37-S6: termal / yapısal / performans panellerinin ``burn_time``
  varsayılanı sonlu sayıydı (10 / 10 / 30 s) → süresiz motorda uydurma süre.
- OH-D37-S7 (CAD ayağı): ``_add_performance_chart`` itki yokken 1000 N
  çiziyordu.

JS gerçek dosyasıyla node altında koşar (asgari sahte DOM; ``innerHTML``
ayrıştırılır, alanlar gerçek varsayılanlarıyla kurulur, POST gövdesi
``fetch`` çağrısından yakalanır — güvertenin kendi ``buildPayload`` yolu).
Kaynak okuyan bekçiler dosyayı DOSYADAN okur.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import math
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
DOCK_JS = JS / 'analysis_dock.js'
I18N_COMMON = JS / 'i18n_common.js'
PANELS = JS / 'panels'
CAD_PY = KOK / 'hrma' / 'export' / 'cad_visualization.py'
SVB_ORNEK_PROJELER = {
    'hybrid': KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma',
    'solid': KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma',
    'liquid': KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma',
}
UC = {'hybrid': '/calculate', 'solid': '/calculate_solid',
      'liquid': '/calculate_liquid'}
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node yok')

#: Süreli sıvı koşusunun süresi — KULLANICI GİRDİSİ ÖRNEĞİ (varsayılan
#: değil). /analyze_safety bandı içinde (0-300 s); D36 sıvı a2 ile aynı.
SIVI_SURE_S = 250.0

#: Güvertenin sayfa sırası (liquid.html / solid.html betik listesi).
SVB_PANEL_DOSYALARI = ('structural_panel.js', 'thermal_panel.js',
                   'safety_panel.js', 'performance_panel.js')

# ---------------------------------------------------------------------------
# node düzeneği — gerçek analysis_dock.js + dört panel, asgari sahte DOM
# ---------------------------------------------------------------------------
DOCK_HARNESS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const [staticDir, girdiYolu] = JSON.parse(process.env.HRMA_ARGS);
const girdi = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));

const byId = {};
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this.dataset = {}; this._attrs = {};
    this._html = ''; this._text = ''; this._desc = []; this._listeners = {};
    this.disabled = false; this.id = '';
    this.classList = { contains: function () { return false; },
                       add: function () {}, remove: function () {},
                       toggle: function () {} };
    if (this.tagName === 'SELECT') { this.options = []; this._sel = -1; }
    else { this._value = ''; }
}
Object.defineProperty(El.prototype, 'value', {
    get: function () {
        if (this.tagName !== 'SELECT') return this._value;
        const o = this.options[this._sel];
        return o ? o.value : '';
    },
    set: function (v) {
        if (this.tagName !== 'SELECT') { this._value = String(v); return; }
        // Tarayıcı anlamı: seçenekte olmayan değer seçimi DÜŞÜRÜR.
        this._sel = -1;
        for (let i = 0; i < this.options.length; i++) {
            if (this.options[i].value === String(v)) { this._sel = i; break; }
        }
    }
});
Object.defineProperty(El.prototype, 'selectedIndex', {
    get: function () { return this._sel; },
    set: function (i) { this._sel = i; }
});
Object.defineProperty(El.prototype, 'textContent', {
    get: function () { return this._text; },
    set: function (v) { this._text = String(v); }
});
function attrs(s) {
    const out = {}; const re = /([\w:-]+)="([^"]*)"/g; let m;
    while ((m = re.exec(s))) out[m[1]] = m[2];
    return out;
}
// innerHTML: id taşıyan öğeler kurulur (alanlar gerçek varsayılanlarıyla);
// kökün torunları = aynı parçada ondan SONRA gelen öğeler.
Object.defineProperty(El.prototype, 'innerHTML', {
    get: function () { return this._html; },
    set: function (html) {
        this._html = String(html);
        const s = this._html;
        const re = /<(\w+)\b([^>]*)>/g; let m; const made = [];
        while ((m = re.exec(s))) {
            const a = attrs(m[2]);
            if (!a.id) continue;
            const e = new El(m[1]);
            e.id = a.id;
            Object.keys(a).forEach(function (k) {
                e._attrs[k] = a[k];
                if (k.indexOf('data-') === 0) {
                    const dk = k.slice(5).replace(/-(\w)/g, function (x, c) {
                        return c.toUpperCase(); });
                    e.dataset[dk] = a[k];
                }
            });
            if (e.tagName === 'INPUT') e._value = ('value' in a) ? a.value : '';
            if (e.tagName === 'SELECT') {
                const son = s.indexOf('</select>', m.index);
                const govde = s.slice(m.index, son);
                const ore = /<option\b([^>]*)>([^<]*)<\/option>/g; let om;
                while ((om = ore.exec(govde))) {
                    const oa = attrs(om[1]);
                    const opt = { value: oa.value || '', textContent: om[2],
                                  _a: oa,
                                  getAttribute: function (k) {
                                      return (k in this._a) ? this._a[k] : null; } };
                    e.options.push(opt);
                    if (/\bselected\b/.test(om[1])) e._sel = e.options.length - 1;
                }
                if (e._sel < 0 && e.options.length) e._sel = 0;
            }
            byId[a.id] = e;
            made.push(e);
        }
        if (made.length) {
            made[0]._desc = made.slice(1);
            this._first = made[0];
        }
    }
});
Object.defineProperty(El.prototype, 'firstElementChild', {
    get: function () { return this._first || (this._first = new El('div')); }
});
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.insertAdjacentHTML = function (w, h) { this._html += String(h); };
El.prototype.remove = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.removeAttribute = function (k) { delete this._attrs[k]; };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
};
El.prototype.fire = function (t) {
    (this._listeners[t] || []).forEach(function (fn) { fn({ target: this }); }, this);
};
El.prototype.querySelectorAll = function (sel) {
    const s = String(sel);
    const m = /^(\w*)\[([\w-]+)\]$/.exec(s);
    if (!m) return [];
    const tag = m[1] ? m[1].toUpperCase() : null;
    return this._desc.filter(function (e) {
        return e.getAttribute(m[2]) !== null && (!tag || e.tagName === tag);
    });
};
El.prototype.querySelector = function (sel) {
    const h = this.querySelectorAll(sel); return h.length ? h[0] : null;
};
function getEl(id) {
    if (!byId[id]) { byId[id] = new El('div'); byId[id].id = id; }
    return byId[id];
}
const documentStub = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: getEl,
    addEventListener: function () {},
};
const bodies = [];
const kullanilanAnahtarlar = {};
function bicimle(f, p) {
    return String(f).replace(/\{(\w+)\}/g, function (w, n) {
        return (p && n in p) ? String(p[n]) : w; });
}
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: setInterval, clearInterval: clearInterval,
    fetch: function (url, opts) {
        bodies.push({ url: url, body: JSON.parse((opts && opts.body) || 'null') });
        return Promise.reject(new Error('düzenek: ağ yok'));
    },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Promise: Promise,
    Error: Error, isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
    I18N: {
        t: function (k, f) { kullanilanAnahtarlar[k] = 1;
                             return girdi.anahtarIsaretle ? '⟦' + k + '⟧' + f : f; },
        tf: function (k, p, f) { kullanilanAnahtarlar[k] = 1;
                                 return (girdi.anahtarIsaretle ? '⟦' + k + '⟧' : '')
                                     + bicimle(f, p); },
        applyTo: function () {}, onChange: function () {},
        number: function (v, d) { return Number(v).toFixed(d); },
    },
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
function run(rel) {
    const f = path.join(staticDir, rel);
    vm.runInContext(fs.readFileSync(f, 'utf8'), sandbox, { filename: f });
}
run('units_constants.js');
run('analysis_dock.js');
(girdi.paneller || []).forEach(function (p) { run(path.join('panels', p)); });

let simdiki = null;
const AD = sandbox.window.AnalysisDock;
const registry = AD._registry;
function uygulananlar() {
    return registry.filter(function (s) {
        return !s.motorTypes || s.motorTypes.indexOf(girdi.motorType) !== -1;
    });
}
function slotOzeti(spec, fid) {
    const slot = byId['ad_src_' + spec.id + '_' + fid];
    if (!slot) return null;
    const h = slot.innerHTML || '';
    const kind = /data-src-kind="([^"]+)"/.exec(h);
    const title = /title="([^"]*)"/.exec(h);
    return { kind: kind ? kind[1] : null, title: title ? title[1] : null,
             html: h, dataset: Object.assign({}, slot.dataset) };
}
function olc(adim) {
    const out = { ad: adim.ad, paneller: {} };
    uygulananlar().forEach(function (spec) {
        if (girdi.panelKimlikleri && girdi.panelKimlikleri.indexOf(spec.id) < 0) return;
        const alanlar = {}; const cipler = {}; const imler = {};
        (spec.fields || []).forEach(function (f) {
            const el = byId['ad_f_' + spec.id + '_' + f[0]];
            alanlar[f[0]] = el ? el.value : null;
            cipler[f[0]] = slotOzeti(spec, f[0]);
            // A1b şart toplayıcı (X11): alan ÖĞESİNİN imleri (data-*)
            imler[f[0]] = el ? Object.assign({}, el.dataset) : null;
        });
        const once = bodies.length;
        const btn = byId['ad_run_' + spec.id];
        if (btn) btn.fire('click');
        const st = byId['ad_status_' + spec.id];
        out.paneller[spec.id] = {
            alanlar: alanlar, cipler: cipler, imler: imler,
            govde: bodies.length > once ? bodies[bodies.length - 1].body : null,
            uc: bodies.length > once ? bodies[bodies.length - 1].url : null,
            durum: st ? st.textContent : null,
        };
    });
    return out;
}
const olcumler = [];
girdi.adimlar.forEach(function (adim) {
    if ('sonuc' in adim) simdiki = adim.sonuc;
    if (adim.eylem === 'init') {
        AD.init({ motorType: girdi.motorType,
                  resultsProvider: function () { return simdiki; } });
    } else if (adim.eylem === 'refresh') {
        AD.refreshSuggestions();
    } else if (adim.eylem === 'elle') {
        adim.alanlar.forEach(function (a) {
            const el = byId['ad_f_' + a[0] + '_' + a[1]];
            el.value = a[2];
            el.fire('input');
        });
    } else if (adim.eylem === 'bosalt') {
        // Programatik boşaltma (olay YOK — kullanıcı girdisi değil), sonra
        // hesap sonrası tazeleme: zorunlu-boş hâlinin çipini ölçmek için.
        adim.alanlar.forEach(function (a) {
            byId['ad_f_' + a[0] + '_' + a[1]].value = '';
        });
        AD.refreshSuggestions();
    }
    olcumler.push(olc(adim));
});
const tanimlar = {};
registry.forEach(function (spec) {
    tanimlar[spec.id] = {};
    (spec.fields || []).forEach(function (f) { tanimlar[spec.id][f[0]] = f[2]; });
});
process.stdout.write(JSON.stringify({ olcumler: olcumler, tanimlar: tanimlar,
    anahtarlar: Object.keys(kullanilanAnahtarlar).sort() }));
"""


def dock_senaryo(motor_type, adimlar, paneller=SVB_PANEL_DOSYALARI,
                 panel_kimlikleri=None, anahtar_isaretle=False, static_dir=None):
    """Gerçek güverte + paneller üstünde adım adım senaryo koşar.

    ``adimlar``: ``{'ad', 'eylem': init|refresh|elle, 'sonuc'?, 'alanlar'?}``.
    Her adımdan sonra her panelin alan değerleri, çipleri ve Çalıştır'a
    basıldığında güvertenin POST ettiği gövde (ya da durdurma metni) döner.
    """
    with tempfile.TemporaryDirectory() as tmp:
        yol = pathlib.Path(tmp) / 'girdi.json'
        yol.write_text(json.dumps({
            'motorType': motor_type, 'adimlar': adimlar,
            'paneller': list(paneller), 'panelKimlikleri': panel_kimlikleri,
            'anahtarIsaretle': anahtar_isaretle}), encoding='utf-8')
        env = {'HRMA_ARGS': json.dumps([str(static_dir or JS), str(yol)]),
               'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin'}
        out = subprocess.run([NODE, '-'], input=DOCK_HARNESS,
                             capture_output=True, text=True, timeout=180,
                             env=env)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout)


def motor_sonuclari(client):
    """Üç örnek motor + süreli sıvı: /calculate ailesinin HAM yanıtları."""
    sonuc = {}
    for tip, yol in SVB_ORNEK_PROJELER.items():
        alanlar = json.loads(yol.read_text(encoding='utf-8'))['inputs']['fields']
        sonuc[tip] = client.post(UC[tip], json=dict(alanlar)).get_json()
        if tip == 'liquid':
            assert 'max_burn_duration' not in alanlar
            sonuc['liquid_sureli'] = client.post(UC[tip], json=dict(
                alanlar, max_burn_duration=SIVI_SURE_S)).get_json()
    return sonuc


# ---------------------------------------------------------------------------
# Modül düzenekleri — çözücü bir kez koşar
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def motorlar(client):
    with contextlib.redirect_stdout(io.StringIO()):
        s = motor_sonuclari(client)
    assert 'burn_time' not in s['liquid'], 'LU-1 önkoşulu: süresiz yanıt süre taşımaz'
    assert s['liquid_sureli'].get('burn_time') == SIVI_SURE_S
    return s


def _post(client, uc, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = client.post(uc, json=govde)
    return r.status_code, r.get_json()


#: Süreye bağlı dört güverte paneli (sıvı sayfası).
SVB_SURE_PANELLERI = ('safety', 'thermal', 'structural', 'performance')


def _sureli_sonra_suresiz(motorlar, **kw):
    return dock_senaryo('liquid', [
        {'ad': 'k1', 'eylem': 'init', 'sonuc': motorlar['liquid_sureli']},
        {'ad': 'k2', 'eylem': 'refresh', 'sonuc': motorlar['liquid']},
    ], panel_kimlikleri=list(SVB_SURE_PANELLERI), **kw)


# ---------------------------------------------------------------------------
# (a) OH-D37-S4 — bayat öneri
# ---------------------------------------------------------------------------
@needs_node
class TestS4BayatOneri:
    def test_suresiz_kosuda_onceki_sure_ve_kutle_govdeye_gitmez(self, motorlar, client):
        d = _sureli_sonra_suresiz(motorlar)
        k1, k2 = d['olcumler']
        for pid in SVB_SURE_PANELLERI:
            # önkoşul: süreli koşu alanı gerçekten doldurdu
            assert k1['paneller'][pid]['govde']['burn_time'] == SIVI_SURE_S, pid
            g = k2['paneller'][pid]['govde']
            assert g is not None, (pid, k2['paneller'][pid]['durum'])
            assert 'burn_time' not in g, (pid, g)
            assert k2['paneller'][pid]['alanlar']['burn_time'] == '', pid
        assert 'propellant_mass' in k1['paneller']['safety']['govde']
        assert 'propellant_mass' not in k2['paneller']['safety']['govde']
        # uç kendi kuralını ADIYLA uygular (uydurma girdiyle 200 değil)
        st, j = _post(client, '/analyze_thermal_safety', k2['paneller']['thermal']['govde'])
        assert st == 422 and j['missing_fields'] == ['burn_time'], (st, j)
        st, j = _post(client, '/analyze_safety', k2['paneller']['safety']['govde'])
        assert st == 422 and j['missing_fields'] == ['propellant_mass'], (st, j)

    def test_gecmisten_bagimsiz_govde(self, motorlar):
        """Aynı sonuç: önceki koşu ne olursa olsun gövde AYNI (sıfırdan kurulum)."""
        d = _sureli_sonra_suresiz(motorlar)
        taze = dock_senaryo('liquid', [
            {'ad': 'k', 'eylem': 'init', 'sonuc': motorlar['liquid']},
        ], panel_kimlikleri=list(SVB_SURE_PANELLERI))
        geri = dock_senaryo('liquid', [
            {'ad': 'k1', 'eylem': 'init', 'sonuc': motorlar['liquid']},
            {'ad': 'k2', 'eylem': 'refresh', 'sonuc': motorlar['liquid_sureli']},
        ], panel_kimlikleri=list(SVB_SURE_PANELLERI))
        sureli_taze = dock_senaryo('liquid', [
            {'ad': 'k', 'eylem': 'init', 'sonuc': motorlar['liquid_sureli']},
        ], panel_kimlikleri=list(SVB_SURE_PANELLERI))
        for pid in SVB_SURE_PANELLERI:
            assert (d['olcumler'][1]['paneller'][pid]['govde']
                    == taze['olcumler'][0]['paneller'][pid]['govde']), pid
            assert (geri['olcumler'][1]['paneller'][pid]['govde']
                    == sureli_taze['olcumler'][0]['paneller'][pid]['govde']), pid

    def test_elle_yazilan_alan_ezilmez(self, motorlar, client):
        d = dock_senaryo('liquid', [
            {'ad': 'k1', 'eylem': 'init', 'sonuc': motorlar['liquid_sureli']},
            {'ad': 'elle', 'eylem': 'elle', 'alanlar': [['thermal', 'burn_time', '42']]},
            {'ad': 'k2', 'eylem': 'refresh', 'sonuc': motorlar['liquid']},
            {'ad': 'k3', 'eylem': 'refresh', 'sonuc': motorlar['liquid_sureli']},
        ], panel_kimlikleri=['thermal'])
        for i in (2, 3):
            p = d['olcumler'][i]['paneller']['thermal']
            assert p['govde']['burn_time'] == 42, (i, p['govde'])
            assert p['cipler']['burn_time']['kind'] == 'user'
        st, _ = _post(client, '/analyze_thermal_safety',
                      d['olcumler'][2]['paneller']['thermal']['govde'])
        assert st == 200

    def test_temizlenen_alanin_cipi_adiyla_soyler(self, motorlar):
        d = _sureli_sonra_suresiz(motorlar, anahtar_isaretle=True)
        k1, k2 = d['olcumler']
        for pid in SVB_SURE_PANELLERI:
            c1 = k1['paneller'][pid]['cipler']['burn_time']
            c2 = k2['paneller'][pid]['cipler']['burn_time']
            assert c1['kind'] == 'computed' and 'cleared' not in c1['dataset'], pid
            assert c2['dataset'].get('cleared') == '1', (pid, c2)
            assert c2['kind'] == 'missing', (pid, c2)
            assert '⟦dock.src.fieldCleared⟧' in c2['title'], c2['title']
            # 'assumed' metni YALNIZ gerçek tanım varsayılanında
            assert 'dock.src.fieldAssumed' not in c2['title'], c2['title']
            assert 'class="ad-cleared-note" data-i18n="dock.src.fieldCleared"' in c2['html']
        # bir sonraki öneri imi kaldırır
        d2 = dock_senaryo('liquid', [
            {'ad': 'k1', 'eylem': 'init', 'sonuc': motorlar['liquid_sureli']},
            {'ad': 'k2', 'eylem': 'refresh', 'sonuc': motorlar['liquid']},
            {'ad': 'k3', 'eylem': 'refresh', 'sonuc': motorlar['liquid_sureli']},
        ], panel_kimlikleri=['thermal'])
        c3 = d2['olcumler'][2]['paneller']['thermal']['cipler']['burn_time']
        assert c3['kind'] == 'computed' and 'cleared' not in c3['dataset'], c3


# ---------------------------------------------------------------------------
# (b) OH-D37-S5 — boş alanın iki hâli
# ---------------------------------------------------------------------------
@needs_node
class TestS5BosAlanIkiHal:
    def test_zorunlu_bos_ve_istege_bagli_bos_ayri_not(self, motorlar):
        d = dock_senaryo('liquid', [
            {'ad': 'k1', 'eylem': 'init', 'sonuc': motorlar['liquid']},
            {'ad': 'bos', 'eylem': 'bosalt',
             'alanlar': [['performance', 'base_heat_flux']]},
        ], panel_kimlikleri=['thermal', 'performance'], anahtar_isaretle=True)
        opt = d['olcumler'][0]['paneller']['thermal']['cipler']['burn_time']
        assert opt['kind'] == 'missing'
        assert '⟦dock.src.fieldBlankOptional⟧' in opt['title'], opt['title']
        assert '⟦dock.src.fieldMissing⟧' not in opt['title']
        p = d['olcumler'][1]['paneller']['performance']
        zor = p['cipler']['base_heat_flux']
        assert zor['kind'] == 'missing'
        assert '⟦dock.src.fieldMissing⟧' in zor['title'], zor['title']
        assert '⟦dock.src.fieldBlankOptional⟧' not in zor['title']
        # zorunlu boş alan isteği gerçekten durdurur (not doğru söylüyor)
        assert p['govde'] is None and 'dock.missingFields' in p['durum'], p['durum']
        # isteğe bağlı boş alan isteği durdurmaz (not doğru söylüyor)
        assert d['olcumler'][0]['paneller']['thermal']['govde'] is not None

    def test_yeni_anahtarlar_en_ve_tr_var_ve_kullaniliyor(self):
        src = I18N_COMMON.read_text(encoding='utf-8')
        tr_bas = src.index('\n        tr: {')
        dock = DOCK_JS.read_text(encoding='utf-8')
        for anahtar in ('dock.src.fieldBlankOptional', 'dock.src.fieldCleared',
                        'dock.src.fieldMissing'):
            satir = "'%s':" % anahtar
            en = src.find(satir)
            tr = src.find(satir, tr_bas)
            assert -1 < en < tr_bas, (anahtar, 'EN yok')
            assert tr > tr_bas, (anahtar, 'TR yok')
            assert src.count(satir) == 2, anahtar
            assert "'%s'" % anahtar in dock, (anahtar, 'kodda kullanılmıyor')
        # mevcut zorunlu alan metni DEĞİŞMEDİ (TAM sahip A1c dil-kabuk)
        assert ("'dock.src.fieldMissing': 'The field is empty — the request "
                "will not be sent until you enter a value.'") in src
        assert ("'dock.src.fieldMissing': 'Alan boş — bir değer girene kadar "
                "istek gönderilmez.'") in src


# ---------------------------------------------------------------------------
# (c) OH-D37-S6 — panel nöbetçileri
# ---------------------------------------------------------------------------
def _eski_nobetcili_kopya(tmp):
    """Üç panelin ESKİ nöbetçileriyle JS kopyası (bit-aynılık kıyası)."""
    hedef = pathlib.Path(tmp) / 'js'
    shutil.copytree(JS, hedef)
    for ad, eski in (('thermal_panel.js', 10), ('structural_panel.js', 10),
                     ('performance_panel.js', 30)):
        p = hedef / 'panels' / ad
        s = p.read_text(encoding='utf-8')
        s2 = re.sub(r"\['burn_time', 'Burn Time \(s\)', '', ",
                    "['burn_time', 'Burn Time (s)', %d, " % eski, s)
        assert s2 != s, ad
        p.write_text(s2, encoding='utf-8')
    return hedef


@needs_node
class TestS6PanelNobetcileri:
    def test_uc_panelin_sure_varsayilani_sayi_degil(self, motorlar):
        d = dock_senaryo('liquid', [
            {'ad': 'k', 'eylem': 'init', 'sonuc': motorlar['liquid']}])
        for pid in ('thermal', 'structural', 'performance', 'performance_solid',
                    'safety'):
            v = d['tanimlar'][pid]['burn_time']
            assert not (isinstance(v, (int, float)) and math.isfinite(v)), (pid, v)

    def test_suresiz_sivida_uc_panel_sure_gondermez(self, motorlar, client):
        d = dock_senaryo('liquid', [
            {'ad': 'k', 'eylem': 'init', 'sonuc': motorlar['liquid']}],
            panel_kimlikleri=['thermal', 'structural', 'performance'])
        p = d['olcumler'][0]['paneller']
        for pid in ('thermal', 'structural', 'performance'):
            assert p[pid]['govde'] is not None, (pid, p[pid]['durum'])
            assert 'burn_time' not in p[pid]['govde'], (pid, p[pid]['govde'])
        st, j = _post(client, '/analyze_thermal_safety', p['thermal']['govde'])
        assert st == 422 and j['missing_fields'] == ['burn_time'], (st, j)
        # performans: ana figür süre tüketmez (200); ısı akısı şelalesi
        # süreyi ADIYLA ister (uydurma 30 s ile çizilmez)
        st, _ = _post(client, '/api/advanced-performance-analysis', p['performance']['govde'])
        assert st == 200
        st, j = _post(client, '/api/advanced-performance-analysis',
                      dict(p['performance']['govde'], analysis_type='heat_flux'))
        assert st == 422 and j['missing_fields'] == [['burn_time']], (st, j)
        # yapısal: süre zaten tüketilmiyordu; gövdeden düştü, hüküm 200
        st, j = _post(client, '/analyze_structural_safety', p['structural']['govde'])
        assert st == 200
        assert j['inputs_not_consumed']['burn_time']['submitted'] is False

    def test_sureli_motorlarda_govde_bit_ayni(self, motorlar):
        with tempfile.TemporaryDirectory() as tmp:
            eski = _eski_nobetcili_kopya(tmp)
            for tip, anahtar in (('hybrid', 'hybrid'), ('solid', 'solid'),
                                 ('liquid', 'liquid_sureli')):
                adim = [{'ad': 'k', 'eylem': 'init', 'sonuc': motorlar[anahtar]}]
                yeni = dock_senaryo(tip, adim)
                once = dock_senaryo(tip, adim, static_dir=eski)
                py = yeni['olcumler'][0]['paneller']
                po = once['olcumler'][0]['paneller']
                assert set(py) == set(po)
                for pid in py:
                    assert py[pid]['govde'] == po[pid]['govde'], (tip, pid)
                    assert py[pid]['govde'] is not None, (tip, pid, py[pid]['durum'])


# ---------------------------------------------------------------------------
# (d) OH-D37-S7 — CAD performans grafiği itki yedeği
# ---------------------------------------------------------------------------
def _perf_alt_grafik(geo):
    from hrma.export.cad_visualization import MotorCADDesigner
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        cad = MotorCADDesigner().generate_3d_motor_assembly(dict(geo))
    fig = json.loads(cad['plotly_visualization'])
    izler = [t for t in fig.get('data', [])
             if t.get('xaxis') == 'x2' and t.get('yaxis') == 'y2']
    notlar = [a.get('text') for a in fig['layout'].get('annotations', [])]
    return izler, notlar


def _perf_dogrudan(motor_data):
    """``_add_performance_chart``'ı tek başına koşturur (dönüş + iz)."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from hrma.export.cad_visualization import MotorCADDesigner
    fig = make_subplots(rows=1, cols=1)
    with contextlib.redirect_stdout(io.StringIO()):
        donus = MotorCADDesigner()._add_performance_chart(fig, motor_data, 1, 1)
    return donus, [t for t in fig.data if isinstance(t, go.Scatter)], \
        [a.text for a in fig.layout.annotations]


class TestS7CadItki:
    ITKI_NOTU = ('Performance chart not drawn: thrust was not published by '
                 'the solver and no design thrust is assumed.')

    def test_itki_yoksa_iz_yok_not_var(self):
        for md in ({'burn_time': 250.0}, {'burn_time': 250.0, 'thrust': None},
                   {'burn_time': 250.0, 'thrust': 0}, {'burn_time': 250.0, 'thrust': 'nan'}):
            donus, izler, notlar = _perf_dogrudan(md)
            assert izler == [], (md, izler)
            assert donus == self.ITKI_NOTU and self.ITKI_NOTU in notlar, (md, notlar)

    def test_itki_ve_sure_varken_iz_bit_ayni(self):
        donus, izler, notlar = _perf_dogrudan({'burn_time': 250.0, 'thrust': 25000.0})
        assert donus is None and notlar == []
        assert len(izler) == 1
        assert list(izler[0].x) == [0.0, 250.0]
        assert list(izler[0].y) == [25000.0, 25000.0]
        assert izler[0].name == 'Thrust (design point, constant-thrust assumption)'

    def test_montaj_yolunda_itkisiz_sivi_iz_cizmez(self, motorlar):
        from hrma.export.motor_geometry import liquid_results_to_motor_geometry
        geo = liquid_results_to_motor_geometry(motorlar['liquid_sureli'])
        izler, _ = _perf_alt_grafik(geo)
        assert len(izler) == 1 and izler[0]['y'] == [geo['thrust']] * 2
        geo.pop('thrust')
        izler, notlar = _perf_alt_grafik(geo)
        assert izler == [] and self.ITKI_NOTU in notlar

    def test_kaynakta_itki_yedegi_yok(self):
        agac = ast.parse(CAD_PY.read_text(encoding='utf-8'))
        fn = [n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef)
              and n.name == '_add_performance_chart']
        assert len(fn) == 1
        for n in ast.walk(fn[0]):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == 'get' and n.args
                    and isinstance(n.args[0], ast.Constant)
                    and n.args[0].value in ('thrust', 'burn_time')):
                assert len(n.args) == 1 and not n.keywords, ast.unparse(n)

    def test_not_performans_alt_grafiginde_paper_koordinatinda(self, motorlar):
        """Not ürünün plotly.js'inde (1.58.5) de DOĞRU alt grafikte durur.

        ``'x2 domain'`` başvurusunu 1.58.5 tanımıyor (ölçüldü, kanıt
        ``ara_domain_ref/``): not kesit görünümünün veri koordinatına düşüp
        eksenlerini geriyordu. Konum ``paper`` + alt grafiğin alan ortası.
        """
        from hrma.export.cad_visualization import PERFORMANCE_CHART_NOT_DRAWN_REASON
        from hrma.export.motor_geometry import liquid_results_to_motor_geometry
        itkisiz = liquid_results_to_motor_geometry(motorlar['liquid_sureli'])
        itkisiz.pop('thrust')
        for geo, metin in ((itkisiz, self.ITKI_NOTU),
                           (liquid_results_to_motor_geometry(motorlar['liquid']),
                            PERFORMANCE_CHART_NOT_DRAWN_REASON)):
            from hrma.export.cad_visualization import MotorCADDesigner
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                cad = MotorCADDesigner().generate_3d_motor_assembly(dict(geo))
            lay = json.loads(cad['plotly_visualization'])['layout']
            notlar = [a for a in lay['annotations'] if a.get('text') == metin]
            assert len(notlar) == 1, notlar
            a = notlar[0]
            assert (a.get('xref'), a.get('yref')) == ('paper', 'paper'), a
            xd, yd = lay['xaxis2']['domain'], lay['yaxis2']['domain']
            assert xd[0] < a['x'] < xd[1] and yd[0] < a['y'] < yd[1], (a, xd, yd)
            # hiçbir not 1.58.5'in tanımadığı 'domain' başvurusu taşımaz
            assert not [b for b in lay['annotations']
                        if 'domain' in str(b.get('xref', '')) + str(b.get('yref', ''))]


# ---------------------------------------------------------------------------
# A1b şart toplayıcı — sahte-veri-b denetçi Ş2 (X1 / X3 / X11 / X2 / X9)
#
# Denetçinin kaçan beş ters mutasyonu (scratchpad denetim-sahte-veri-b/
# mut_calistir.py, mut_sonuc.json: X1, X2, X3, X9, X11 YEŞİL kaldı) bu
# düğümlerle kırmızıya döner. Kanıt: docs/scofield/raw/OH/A1b/sart-toplayici/.
#
# SENTETİK sonuçlar (test altyapısı; kullanıcıya gösterilen veri değildir):
# sıvı motor yanıtının güvertenin okuduğu anahtarlarıyla KURGULANMIŞ iki
# koşu. Sayıların fiziksel anlamı konu değil — konu, A koşusunda önerilen
# bir alanın B koşusunda önerilmediğinde ne olduğudur. Anahtar yolları
# ürünün kendi okuyucularından (analysis_dock.js motorDict / readLengthM
# LENGTH_UNITS.liquid mm / readMassFlow total_mass_flow /
# readChamberMaterial structural_analysis.chamber_structure.material_key /
# readWallThicknessM ...wall_thickness mm).
# ---------------------------------------------------------------------------
def _sentetik_sivi(**degisiklik):
    """Sentetik sıvı yanıtı; ``None`` verilen anahtar yanıttan ÇIKARILIR."""
    r = {'chamber_pressure': 70.0, 'chamber_temperature': 3500.0,
         'chamber_diameter': 120.0, 'chamber_length': 300.0,
         'total_mass_flow': 5.5,
         'structural_analysis': {'chamber_structure': {
             'material_key': 'ss_304', 'wall_thickness': 4.0}}}
    yapi = r['structural_analysis']['chamber_structure']
    for k, v in degisiklik.items():
        hedef = yapi if k in ('material_key', 'wall_thickness') else r
        if v is None:
            hedef.pop(k, None)
        else:
            hedef[k] = v
    return r


#: A: oda basıncı ve malzeme ÖNERİLİR; B: ikisi de yanıtta YOK (gerisi aynı).
SENTETIK_A = _sentetik_sivi()
SENTETIK_B = _sentetik_sivi(chamber_pressure=None, material_key=None)
#: A'da önerilip B'de önerilmeyen termal alanlar (tanım: thermal_panel.js).
A_ONERIP_B_ONERMEYEN = {'chamber_pressure', 'material'}


def _tanim(pid):
    """Panel alan tanımlarının varsayılanı (gerçek kayıttan, node)."""
    return dock_senaryo('liquid', [{'ad': 'k', 'eylem': 'init', 'sonuc': None}],
                        panel_kimlikleri=[pid])['tanimlar'][pid]


@needs_node
class TestSartSahteVeriB:

    def test_x1_sonlu_varsayilanli_alan_tanim_varsayilanina_doner(self):
        """(X1) Sonlu varsayılanlı alan (termal ``chamber_pressure``, tanım
        40) A'da önerilip (70) B'de önerilmeyince TANIM varsayılanına döner
        — boşa değil; gövde, B ile sıfırdan açılan güvertenin gövdesiyle
        AYNI (geçmişten bağımsızlık). Denetçi X1: alan hep boşa döner."""
        tanim = _tanim('thermal')
        assert tanim['chamber_pressure'] == 40          # kurgu: sonlu varsayılan
        d = dock_senaryo('liquid', [
            {'ad': 'k1', 'eylem': 'init', 'sonuc': SENTETIK_A},
            {'ad': 'k2', 'eylem': 'refresh', 'sonuc': SENTETIK_B},
        ], panel_kimlikleri=['thermal'])
        taze = dock_senaryo('liquid', [
            {'ad': 'k', 'eylem': 'init', 'sonuc': SENTETIK_B},
        ], panel_kimlikleri=['thermal'])
        k1 = d['olcumler'][0]['paneller']['thermal']
        k2 = d['olcumler'][1]['paneller']['thermal']
        t = taze['olcumler'][0]['paneller']['thermal']
        # önkoşul: A gerçekten önerdi
        assert k1['alanlar']['chamber_pressure'] == '70', k1['alanlar']
        assert k1['govde']['chamber_pressure'] == 70
        # B: tanım varsayılanı (ekranda ve gövdede), boş değil
        assert k2['alanlar']['chamber_pressure'] == str(tanim['chamber_pressure'])
        assert k2['govde'] is not None, k2['durum']
        assert k2['govde']['chamber_pressure'] == tanim['chamber_pressure']
        assert k2['govde'] == t['govde'], (k2['govde'], t['govde'])
        assert k2['alanlar'] == t['alanlar']

    def test_x3_secici_alan_tanim_degerine_doner(self):
        """(X3) Seçici alan (termal ``material``, tanım ``steel``) A'da
        önerilip (``ss_304``) B'de önerilmeyince TANIM değerine döner;
        gövde sıfırdan kurulumla aynı. Denetçi X3: seçici dalında öneri imi
        yazılmazsa alan A'nın malzemesinde bayat kalır."""
        tanim = _tanim('thermal')
        assert tanim['material'] == 'steel'
        d = dock_senaryo('liquid', [
            {'ad': 'k1', 'eylem': 'init', 'sonuc': SENTETIK_A},
            {'ad': 'k2', 'eylem': 'refresh', 'sonuc': SENTETIK_B},
        ], panel_kimlikleri=['thermal'])
        taze = dock_senaryo('liquid', [
            {'ad': 'k', 'eylem': 'init', 'sonuc': SENTETIK_B},
        ], panel_kimlikleri=['thermal'])
        k1 = d['olcumler'][0]['paneller']['thermal']
        k2 = d['olcumler'][1]['paneller']['thermal']
        t = taze['olcumler'][0]['paneller']['thermal']
        assert k1['alanlar']['material'] == 'ss_304'
        assert k1['govde']['material'] == 'ss_304'
        assert k2['alanlar']['material'] == tanim['material']
        assert k2['govde']['material'] == tanim['material'], k2['govde']
        assert k2['govde'] == t['govde']

    def test_x11_init_ve_ilk_kosuda_temizlendi_imi_yok(self):
        """(X11) Sonuçsuz açılışta ve ilk koşuda HİÇBİR alanda
        ``data-cleared`` yok (ne alan öğesinde ne çip yuvasında, görünür
        'temizlendi' satırı da yok); ikinci koşuda imi YALNIZ önceki
        koşuda önerilip bu koşuda önerilmeyen alanlar taşır. Denetçi X11:
        im önceden önerilmemiş alana da basılır."""
        pids = ['thermal', 'structural', 'safety', 'performance']
        d = dock_senaryo('liquid', [
            {'ad': 'acilis', 'eylem': 'init', 'sonuc': None},
            {'ad': 'k1', 'eylem': 'refresh', 'sonuc': SENTETIK_A},
            {'ad': 'k2', 'eylem': 'refresh', 'sonuc': SENTETIK_B},
        ], panel_kimlikleri=pids)
        acilis, k1, k2 = d['olcumler']
        for adim in (acilis, k1):
            for pid in pids:
                p = adim['paneller'][pid]
                imli = sorted(f for f, im in p['imler'].items()
                              if im and im.get('cleared'))
                assert imli == [], (adim['ad'], pid, imli)
                for f, c in p['cipler'].items():
                    if c is None:
                        continue
                    assert 'cleared' not in c['dataset'], (adim['ad'], pid, f)
                    assert 'ad-cleared-note' not in c['html'], (adim['ad'], pid, f)
        # k2: termalde tam olarak A'da önerilip B'de önerilmeyenler
        p = k2['paneller']['thermal']
        imli = {f for f, im in p['imler'].items() if im and im.get('cleared')}
        assert imli == A_ONERIP_B_ONERMEYEN, imli
        for f, c in p['cipler'].items():
            assert (c['dataset'].get('cleared') == '1') == (f in A_ONERIP_B_ONERMEYEN), (f, c)
        # A ile B'de de önerilen alan (ör. oda sıcaklığı) imsiz
        assert 'cleared' not in p['imler']['chamber_temperature']

    def test_x2_elle_secim_engeli_kaldirir_dokunulmamis_yeniden_engellenir(self):
        """(X2, P17B2-08) Çözücü malzemesi listede yok → iki panel de
        koşmaz. Kullanıcı TERMAL'de seçimi elle yapınca termal koşar
        (seçtiği malzemeyle); DOKUNULMAMIŞ yapısal seçici aynı sonuçta
        her geçişte yeniden engellenir. Sonraki koşu malzeme yayımlamazsa
        önceki koşunun engeli yeni koşumu DURDURMAZ. Denetçi X2:
        ``blockedSelects`` geçiş başında sıfırlanmaz → elle seçim engeli
        kaldırmaz ve bayat engel sürer."""
        yok = _sentetik_sivi(material_key='unobtainium_zz')
        malzemesiz = _sentetik_sivi(material_key=None)
        d = dock_senaryo('liquid', [
            {'ad': 'k1', 'eylem': 'init', 'sonuc': yok},
            {'ad': 'elle', 'eylem': 'elle',
             'alanlar': [['thermal', 'material', 'ss_304']]},
            {'ad': 'k2', 'eylem': 'refresh', 'sonuc': yok},
            {'ad': 'k3', 'eylem': 'refresh', 'sonuc': malzemesiz},
        ], panel_kimlikleri=['thermal', 'structural'])
        k1, elle, k2, k3 = d['olcumler']
        for pid in ('thermal', 'structural'):
            p = k1['paneller'][pid]
            assert p['govde'] is None, (pid, p['govde'])
            assert 'solver="unobtainium_zz"' in p['durum'], (pid, p['durum'])
        for adim in (elle, k2):
            t = adim['paneller']['thermal']
            assert t['govde'] is not None, (adim['ad'], t['durum'])
            assert t['govde']['material'] == 'ss_304'
            s = adim['paneller']['structural']
            assert s['govde'] is None, (adim['ad'], s['govde'])
            assert 'solver="unobtainium_zz"' in s['durum'], (adim['ad'], s['durum'])
        # k3: malzeme yayımlanmadı → engel yok, tanım değeri gider
        s = k3['paneller']['structural']
        assert s['govde'] is not None, s['durum']
        assert s['govde']['material'] == _tanim('structural')['material']

    def test_x9_iki_yeni_anahtarin_tr_metni_en_den_farkli(self):
        """(X9) ``dock.src.fieldBlankOptional`` ve ``dock.src.fieldCleared``
        GERÇEK sözlük motorunda (i18n.js + i18n_common.js) iki dilde
        çözülür; TR metni EN'den farklı ve Türkçe harf taşır. Denetçi X9:
        TR girdisine EN metni yazılır."""
        betik = r"""
global.self = global; global.window = global;
const fs = require('fs');
global.document = { createElement() { return {}; }, getElementById() { return null; },
  querySelector() { return null; }, querySelectorAll() { return []; },
  addEventListener() {}, removeEventListener() {}, dispatchEvent() {},
  readyState: 'complete',
  documentElement: { setAttribute() {}, getAttribute() { return null; } } };
Object.defineProperty(global, 'localStorage', { configurable: true,
  value: { getItem() { return null; }, setItem() {}, removeItem() {} } });
Object.defineProperty(global, 'navigator', { configurable: true,
  value: { language: 'en' } });
const P = JSON.parse(process.env.HRMA_ARGS);
(0, eval)(fs.readFileSync(P[0], 'utf8'));
(0, eval)(fs.readFileSync(P[1], 'utf8'));
const out = {};
for (const lang of ['en', 'tr']) {
  I18N.lang = lang;
  out[lang] = {};
  for (const k of ['dock.src.fieldBlankOptional', 'dock.src.fieldCleared']) {
    out[lang][k] = I18N.t(k, '⟦YOK⟧');
  }
}
process.stdout.write(JSON.stringify(out));
"""
        env = {'HRMA_ARGS': json.dumps([str(JS / 'i18n.js'), str(I18N_COMMON)]),
               'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin'}
        r = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                           text=True, timeout=120, env=env)
        assert r.returncode == 0, r.stderr[-2000:]
        o = json.loads(r.stdout)
        for k in ('dock.src.fieldBlankOptional', 'dock.src.fieldCleared'):
            en, tr = o['en'][k], o['tr'][k]
            assert '⟦YOK⟧' not in (en, tr), (k, en, tr)
            assert en.strip() and tr.strip(), k
            assert tr != en, (k, tr)
            assert re.search('[çğıİöşüÇĞÖŞÜ]', tr), (k, tr)
