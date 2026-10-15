"""ÖH A2 sivi-sogutma · 7. tur (14 Eki) — v3.0 devirleri, bekçiler.

Kalemler (rapor: docs/scofield/raw/OH/A2/sivi-sogutma/a1/rapor.md
"7. tur (14 Eki)"):

1. F-17 kaynaksız ön-dolgular (regen paneli): kanal genişliği/derinliği,
   astar, soğutucu, giriş basıncı ve sıcaklığı motorun YAYIMLADIĞI değerden
   (yalnız sonlu pozitif, yalnız kanal devresi varken); yoksa BOŞ + zorunlu.
2. Güverte 'boş + zorunlu' beyanı: ``spec.required`` — beyanlı alan boşsa
   istek gönderilmez, çip "zorunlu" notunu basar.
3. ``RegenCooling(n_channels=...)`` Python varsayılanı adlı sabite bağlı;
   her ÜRÜN çağrısı N'yi açıkça verir (AST).
4. 'Feed (Ox)', 'Feed (Fuel)', 'Feed', 'Inj. ΔP' grafik etiketlerinin TR
   karşılığı (EN = TR anlamca).
5. LH2 yoğunluk girdisi: yakıt değişince yoğunluk alanı başka yakıtın
   sayısını taşımaz; elle girilmiş değer korunur ve uyarıyla durur.
6. Basınç beslemede ``turbopump_efficiency`` / ``generator_gas_temp``
   gönderilirse ``inputs_not_used`` ile adıyla beyan edilir (uyarı listesi
   değişmez).
"""
import ast
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

os.environ.setdefault('HRMA_PROJECTS_DIR',
                      tempfile.mkdtemp(prefix='hrma-d37-sivi-t7-'))

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_JS = os.path.join(KOK, 'hrma', 'static', 'js')
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _oku(*yol):
    with open(os.path.join(KOK, *yol), encoding='utf-8') as fh:
        return fh.read()


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


def _sivi(istemci, **degisiklik):
    from tests.support import form_defaults
    from tests.test_example_projects import load_example_doc
    alanlar = dict(load_example_doc('liquid')['inputs']['fields'])
    alanlar.update(degisiklik)
    r = _sessiz(istemci.post, '/calculate_liquid',
                json=form_defaults.form_yuku('liquid', alanlar))
    assert r.status_code == 200, r.get_json()
    return r.get_json()


@pytest.fixture(scope='module')
def sonuclar(istemci):
    return {
        'rp1': _sivi(istemci),
        'lh2': _sivi(istemci, fuel_type='lh2'),
        'ablatif': _sivi(istemci, cooling_type='ablative'),
    }


# =========================================================================
# Güverte düzeneği: GERÇEK analysis_dock.js + GERÇEK cooling_panel.js
# =========================================================================
#: Sahte DOM: alanlar tanım değeriyle kurulur (fieldHtml'in yaptığı gibi),
#: `edits` kullanıcının elle yazdığı alanlardır (data-dirty). Koşum düğmesine
#: kayıtlı GERÇEK dinleyici tetiklenir; uca giden gövde ya da durum satırı
#: ölçülür.
DOCK_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const [staticDir, payloadPath] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this.dataset = {};
    this._attrs = {}; this.textContent = ''; this.innerHTML = '';
    this.disabled = false; this.value = ''; this.options = [];
    this.selectedIndex = -1; this._listeners = {};
    this.classList = { contains: function () { return false; },
                       add: function () {}, remove: function () {} };
}
Object.defineProperty(El.prototype, 'firstElementChild', {
    get: function () { return this._first || (this._first = new El('div')); }
});
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.insertAdjacentHTML = function (w, h) { this.innerHTML += h; };
El.prototype.remove = function () {};
El.prototype.removeChild = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.removeAttribute = function (k) { delete this._attrs[k]; };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
};
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };

const byId = {};
function getEl(id) { if (!byId[id]) byId[id] = new El('div'); return byId[id]; }

const documentStub = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: getEl, addEventListener: function () {},
};
const calls = [];
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: setInterval, clearInterval: clearInterval,
    fetch: function (url, opts) {
        calls.push({ url: url, body: opts && opts.body });
        const text = '{"status":"success","cooling":{}}';
        return Promise.resolve({ ok: true, status: 200,
            text: function () { return Promise.resolve(text); },
            json: function () { return Promise.resolve(JSON.parse(text)); } });
    },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Promise: Promise, Error: Error,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
function run(f) { vm.runInContext(fs.readFileSync(f, 'utf8'), sandbox, { filename: f }); }
run(path.join(staticDir, 'units_constants.js'));
run(path.join(staticDir, 'analysis_dock.js'));
run(path.join(staticDir, 'panels', 'cooling_panel.js'));
const spec = sandbox.window.AnalysisDock._registry.filter(function (s) {
    return s.id === 'cooling'; })[0];

// Alanlar: fieldHtml'in kurduğu hâl (select: tanım değeri seçili, yoksa ilk).
const fieldEls = [];
(spec.fields || []).forEach(function (f) {
    const isSel = Array.isArray(f[3]);
    const el = getEl('ad_f_cooling_' + f[0]);
    el.tagName = isSel ? 'SELECT' : 'INPUT';
    el.setAttribute('data-field', f[0]);
    if (isSel) {
        el.options = f[3].map(function (o) {
            const op = new El('option'); op.value = o[0]; op.textContent = o[1];
            if (o[2]) op.setAttribute('data-i18n', o[2]); return op; });
        let i = f[3].map(function (o) { return o[0]; }).indexOf(f[2]);
        if (i < 0) i = 0;
        el.selectedIndex = i;
        Object.defineProperty(el, 'value', {
            get: function () { return this.options[this.selectedIndex]
                ? this.options[this.selectedIndex].value : ''; },
            set: function (v) { const j = this.options.map(function (o) {
                return o.value; }).indexOf(String(v));
                this.selectedIndex = j; },
            configurable: true });
    } else {
        el.value = (f[2] == null) ? '' : String(f[2]);
    }
    fieldEls.push(el);
});
Object.keys(P.edits || {}).forEach(function (k) {
    const el = getEl('ad_f_cooling_' + k);
    el.value = P.edits[k]; el.dataset.dirty = '1';
});
const sec = getEl('ad_sec_cooling');
sec.querySelectorAll = function (sel) { return sel === '[data-field]' ? fieldEls : []; };

sandbox.window.AnalysisDock.init({ motorType: 'liquid',
    resultsProvider: function () { return P.results; } });
const btn = getEl('ad_run_cooling');
const ls = btn._listeners.click || [];
if (!ls.length) { console.log(JSON.stringify({ error: 'run dinleyicisi yok' })); process.exit(0); }
Promise.resolve(ls[0]()).then(function () {
    setTimeout(function () {
        const alanlar = {}, cipler = {};
        (spec.fields || []).forEach(function (f) {
            alanlar[f[0]] = getEl('ad_f_cooling_' + f[0]).value;
            cipler[f[0]] = getEl('ad_src_cooling_' + f[0]).innerHTML;
        });
        console.log(JSON.stringify({
            fetchCount: calls.length,
            body: calls.length ? JSON.parse(calls[0].body) : null,
            status: getEl('ad_status_cooling').textContent,
            fields: alanlar, chips: cipler, required: spec.required || null,
        }));
    }, 60);
});
"""


def dock_kos(sonuc, edits=None, static_dir=STATIC_JS):
    """Güverte düzeneğini koşturur (ölçüm betikleri de bunu çağırır)."""
    with tempfile.TemporaryDirectory() as tmp:
        h = os.path.join(tmp, 'h.js')
        p = os.path.join(tmp, 'p.json')
        with open(h, 'w', encoding='utf-8') as fh:
            fh.write(DOCK_HARNESS)
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump({'results': sonuc, 'edits': edits or {}}, fh)
        proc = subprocess.run([NODE, h, static_dir, p], capture_output=True,
                              text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert 'error' not in data, data
    return data


#: Kalem 1'in alanları ve eski kaynaksız ön-dolguları (ölçülen önce).
ESKI_ON_DOLGU = {'channel_width': 2.0, 'channel_height': 3.0,
                 'wall_thickness': 1.0, 'coolant': 'water',
                 'coolant_inlet_pressure': 60, 'coolant_inlet_temp': 300}
REGEN_ZORUNLU_ALANLAR = ['n_channels', 'coolant', 'coolant_inlet_temp',
           'coolant_inlet_pressure', 'channel_width', 'channel_height',
           'wall_thickness']


def _spec_alanlari():
    from tests.test_panel_units_v2626 import _run_harness
    return _run_harness({}, 'liquid')['panels']['cooling']


# =========================================================================
# 1 — kaynaksız ön-dolgu yok
# =========================================================================
@node_gerekli
class TestKaynaksizOnDolgu:
    def test_tanim_degerleri_bos(self):
        rec = _spec_alanlari()
        for alan in ESKI_ON_DOLGU:
            assert rec['fields'][alan] == '', (alan, rec['fields'][alan])
        # Soğutucu seçicisi boş seçimle açılır (ilk seçenek yer tutucu).
        assert rec['selectOptions']['coolant'][0] == ''

    def test_rp1_onerileri_motorun_yayimladigi_degerler(self, sonuclar):
        from tests.test_panel_units_v2626 import _run_harness
        r = sonuclar['rp1']
        cs = r['cooling_system']
        sug = _run_harness(r, 'liquid')['panels']['cooling']['suggestions']
        assert sug['n_channels'] == cs['cooling_channels']
        assert sug['channel_width'] == cs['channel_width_mm']
        assert sug['channel_height'] == cs['channel_height_mm']
        assert sug['wall_thickness'] == (
            cs['channel_count_fit']['hot_wall_thickness_mm'])
        assert sug['coolant_inlet_temp'] == cs['coolant_inlet_temperature']
        assert sug['coolant'] == r['fuel_type'] == 'rp1'
        # RP-1 marşının giriş basıncı yanıtta YOK → önerilmez (boş kalır).
        assert cs.get('regen_supercritical') is None
        assert 'coolant_inlet_pressure' not in sug

    def test_lh2_giris_basinci_suprkritik_marstan(self, sonuclar):
        from tests.test_panel_units_v2626 import _run_harness
        r = sonuclar['lh2']
        sc = r['cooling_system']['regen_supercritical']
        sug = _run_harness(r, 'liquid')['panels']['cooling']['suggestions']
        assert sug['coolant_inlet_pressure'] == sc['inlet_pressure_bar']
        assert sug['coolant_inlet_temp'] == sc['inlet_temp_K']
        assert sug['wall_thickness'] == (r['cooling_system']
                                         ['channel_count_fit']
                                         ['hot_wall_thickness_mm'])

    def test_kanal_devresi_yoksa_hicbiri_onerilmez(self, sonuclar):
        from tests.test_panel_units_v2626 import _run_harness
        r = sonuclar['ablatif']
        assert r['cooling_system']['cooling_channels'] == 0
        # motor kanalsız tasarımda da kesit sayısını taşıyor (kalıntı) —
        # panel onu almıyor
        assert r['cooling_system']['channel_width_mm'] > 0
        sug = _run_harness(r, 'liquid')['panels']['cooling']['suggestions']
        for alan in REGEN_ZORUNLU_ALANLAR:
            assert alan not in sug, (alan, sug.get(alan))

    @pytest.mark.parametrize('bozuk', [0, -2.0, float('nan'), '3.0', None,
                                       True, float('inf')])
    def test_gecersiz_sayi_onerilmez(self, bozuk):
        from tests.test_panel_units_v2626 import _run_harness
        cs = {'cooling_channels': 40, 'channel_width_mm': bozuk,
              'channel_height_mm': bozuk, 'coolant_inlet_temperature': bozuk,
              'channel_count_fit': {'hot_wall_thickness_mm': bozuk},
              'regen_supercritical': {'inlet_pressure_bar': bozuk}}
        # NaN/inf JSON'a yazılamaz; düzenek null alır — o da reddedilmeli
        if isinstance(bozuk, float) and bozuk != bozuk or bozuk == float('inf'):
            cs = json.loads(json.dumps(cs).replace('NaN', 'null')
                            .replace('Infinity', 'null'))
        sug = _run_harness({'cooling_system': cs, 'fuel_type': 'rp1'},
                           'liquid')['panels']['cooling']['suggestions']
        for alan in ('channel_width', 'channel_height', 'wall_thickness',
                     'coolant_inlet_temp', 'coolant_inlet_pressure'):
            assert alan not in sug, (alan, bozuk, sug)


# =========================================================================
# 2 — güverte 'boş + zorunlu' beyanı (gerçek güverte + gerçek panel)
# =========================================================================
@node_gerekli
class TestGuverteZorunluBeyan:
    def test_panel_beyani(self):
        out = dock_kos(None)
        assert sorted(out['required']) == sorted(REGEN_ZORUNLU_ALANLAR)

    def test_sonuc_yokken_istek_gitmez_eksikler_adiyla(self):
        out = dock_kos(None)
        assert out['fetchCount'] == 0, out['body']
        for etiket in ('Number of Channels', 'Coolant', 'Coolant Inlet T (K)',
                       'Coolant Inlet P (bar)', 'Channel Width (mm)',
                       'Channel Height (mm)', 'Liner Thickness (mm)'):
            assert etiket in out['status'], (etiket, out['status'])

    def test_bos_zorunlu_alanin_cipi_zorunlu_notunu_basar(self):
        out = dock_kos(None)
        for alan in REGEN_ZORUNLU_ALANLAR:
            cip = out['chips'][alan]
            assert 'request will not be sent' in cip, (alan, cip)
            assert 'endpoint applies its own rule' not in cip, (alan, cip)

    def test_rp1_sonucunda_yalniz_giris_basinci_eksik(self, sonuclar):
        out = dock_kos(sonuclar['rp1'])
        assert out['fetchCount'] == 0
        assert 'Coolant Inlet P (bar)' in out['status']
        for etiket in ('Number of Channels', 'Channel Width (mm)',
                       'Liner Thickness (mm)', 'Coolant Inlet T (K)'):
            assert etiket not in out['status'], (etiket, out['status'])

    def test_kullanici_girince_istek_gider_motor_degerleriyle(self, sonuclar):
        r = sonuclar['rp1']
        cs = r['cooling_system']
        out = dock_kos(r, edits={'coolant_inlet_pressure': '75'})
        assert out['fetchCount'] == 1, out['status']
        b = out['body']
        assert b['coolant'] == 'rp1'
        assert b['n_channels'] == cs['cooling_channels']
        assert b['channel_width'] == pytest.approx(cs['channel_width_mm'])
        assert b['channel_height'] == pytest.approx(cs['channel_height_mm'])
        assert b['wall_thickness'] == pytest.approx(
            cs['channel_count_fit']['hot_wall_thickness_mm'])
        assert b['coolant_inlet_temp'] == pytest.approx(
            cs['coolant_inlet_temperature'])
        assert b['coolant_inlet_pressure'] == 75

    def test_bos_secim_govdeye_gitmez(self):
        # Soğutucu dışındaki her şey elle girildi: istek yalnız boş seçim
        # yüzünden durur.
        out = dock_kos(None, edits={
            'n_channels': '40', 'coolant_inlet_temp': '300',
            'coolant_inlet_pressure': '80', 'channel_width': '3',
            'channel_height': '2', 'wall_thickness': '2'})
        assert out['fetchCount'] == 0, out['body']
        assert 'Coolant' in out['status']

    def test_lh2_sonucunda_istek_motorun_suprkritik_degerleriyle(self,
                                                                 sonuclar):
        r = sonuclar['lh2']
        sc = r['cooling_system']['regen_supercritical']
        out = dock_kos(r)
        assert out['fetchCount'] == 1, out['status']
        b = out['body']
        assert b['coolant'] == 'lh2'                 # önce: 'water'
        assert b['coolant_inlet_temp'] == pytest.approx(sc['inlet_temp_K'])
        assert b['coolant_inlet_pressure'] == pytest.approx(
            sc['inlet_pressure_bar'])

    def test_seciciye_dusmeyen_yakit_kosumu_durdurur(self):
        sahte = {'fuel_type': 'mmh', 'cooling_system': {
            'cooling_channels': 30, 'channel_width_mm': 3.0,
            'channel_height_mm': 2.0, 'coolant_inlet_temperature': 300.0,
            'channel_count_fit': {'hot_wall_thickness_mm': 2.0}}}
        out = dock_kos(sahte, edits={'coolant_inlet_pressure': '80'})
        assert out['fetchCount'] == 0
        assert 'solver="mmh"' in out['status'], out['status']

    def test_beyan_disi_alanin_kurali_aynen(self):
        """Beyan dışı boş alan isteğe bağlı kalır (diğer paneller)."""
        src = _oku('hrma', 'static', 'js', 'analysis_dock.js')
        m = re.search(r'function requiredFieldInfo\(spec\) \{(.*?)\n    \}',
                      src, re.S)
        assert m and 'spec.required' in m.group(1)
        assert "typeof def === 'number' && Number.isFinite(def)" in m.group(1)


# =========================================================================
# 3 — RegenCooling n_channels varsayılanı adlı; ürün çağrıları açık N
# =========================================================================
def test_n_channels_varsayilani_adli_sabit():
    import inspect
    from hrma.analysis import regen_cooling as rc
    imza = inspect.signature(rc.RegenCooling.__init__).parameters
    assert imza['n_channels'].default == rc.REGEN_N_CHANNELS_API_DEFAULT
    agac = ast.parse(_oku('hrma', 'analysis', 'regen_cooling.py'))
    for dugum in ast.walk(agac):
        if (isinstance(dugum, ast.FunctionDef) and dugum.name == '__init__'
                and any(a.arg == 'n_channels' for a in dugum.args.args)):
            adlar = [a.arg for a in dugum.args.args]
            vars_ = dugum.args.defaults
            d = vars_[adlar.index('n_channels') - (len(adlar) - len(vars_))]
            assert isinstance(d, ast.Name), ast.dump(d)
            assert d.id == 'REGEN_N_CHANNELS_API_DEFAULT'
            break
    else:
        pytest.fail('RegenCooling.__init__ bulunamadı')


#: Ürün kodunda RegenCooling kuran her dosya (ölçüldü: 3 çağrı).
URUN_CAGRILARI = {'hrma/app.py': 1, 'hrma/engines/liquid_rocket_engine.py': 2}


def test_her_urun_cagrisi_n_channels_veriyor():
    for yol, beklenen in URUN_CAGRILARI.items():
        agac = ast.parse(_oku(*yol.split('/')))
        cagrilar = [d for d in ast.walk(agac) if isinstance(d, ast.Call)
                    and getattr(d.func, 'id', None) == 'RegenCooling']
        assert len(cagrilar) == beklenen, (yol, len(cagrilar))
        for c in cagrilar:
            anahtarlar = {k.arg for k in c.keywords}
            if None in anahtarlar:          # RegenCooling(**kwargs) — uç
                assert yol == 'hrma/app.py'
                kaynak = _oku(*yol.split('/'))
                assert "kwargs['n_channels'] = int(n_channels)" in kaynak
                assert "'n_channels' is required" in kaynak
            else:
                assert 'n_channels' in anahtarlar, (yol, c.lineno)
    # Başka ürün dosyası RegenCooling kurmuyor.
    kurulanlar = []
    for kok, _, dosyalar in os.walk(os.path.join(KOK, 'hrma')):
        for ad in dosyalar:
            if ad.endswith('.py'):
                y = os.path.join(kok, ad)
                with open(y, encoding='utf-8') as fh:
                    if re.search(r'\bRegenCooling\(', fh.read()):
                        kurulanlar.append(os.path.relpath(y, KOK))
    assert sorted(kurulanlar) == sorted(
        list(URUN_CAGRILARI) + ['hrma/analysis/regen_cooling.py'])


# =========================================================================
# 4 — grafik kategori etiketleri TR
# =========================================================================
BESLEME_ETIKETLERI_TR = {'Feed (Ox)': 'Besleme (oksitleyici)',
             'Feed (Fuel)': 'Besleme (yakıt)', 'Feed': 'Besleme',
             'Inj. ΔP': 'Enj. ΔP'}


def _charts_degerleri(anahtar):
    return re.findall(r"^\s*'" + re.escape(anahtar) + r"': '([^']*)',$",
                      _oku('hrma', 'static', 'js', 'i18n_charts.js'), re.M)


@pytest.mark.parametrize('anahtar', sorted(BESLEME_ETIKETLERI_TR))
def test_grafik_etiketi_en_tr(anahtar):
    assert _charts_degerleri(anahtar) == [anahtar, BESLEME_ETIKETLERI_TR[anahtar]]


def test_etiketler_visualization_ile_ayni():
    """Sözlük anahtarı = sunucunun bastığı metnin kendisi."""
    src = _oku('hrma', 'visualization', 'visualization.py')
    for anahtar in BESLEME_ETIKETLERI_TR:
        assert "'%s'" % anahtar in src, anahtar


# =========================================================================
# 5 — yakıt yoğunluğu alanı yakıtı izler (liquid.html, gerçek fonksiyonlar)
# =========================================================================
#: liquid.html'den sökülen birim: yoğunluk kapısı + input dinleyicisi.
YOGUNLUK_HARNESS = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [srcPath, payloadPath] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
function El(id, v) { this.id = id; this.value = String(v == null ? '' : v);
    this.style = {}; this.innerHTML = ''; this.textContent = '';
    this._a = {}; this.parentNode = null; this.nextSibling = null;
    this.options = []; }
El.prototype.getAttribute = function (k) { return k in this._a ? this._a[k] : null; };
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); };
El.prototype.removeAttribute = function (k) { delete this._a[k]; };
const parent = { insertBefore: function (n) { F[n.id] = n; } };
const F = {};
['fuel_density', 'fuel_viscosity', 'oxidizer_density', 'oxidizer_viscosity']
    .forEach(function (id) { F[id] = new El(id, ''); F[id].parentNode = parent; });
F.fuel_type = new El('fuel_type', P.fuel0 || 'rp1');
F.fuel_type.options = ['rp1', 'lh2', 'methane', 'mmh', 'udmh'].map(function (k) {
    const o = new El('o', k); o.textContent = k.toUpperCase(); return o; });
const SP = {};
const listeners = [];
const dict = {};
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, isFinite: isFinite,
    parseFloat: parseFloat, parseInt: parseInt, Promise: Promise,
    T: function (k, fb) { return fb === undefined ? k : fb; },
    TF: function (k, p, fb) { let s = String(fb === undefined ? k : fb);
        Object.keys(p || {}).forEach(function (n) {
            s = s.split('{' + n + '}').join(String(p[n])); }); return s; },
    document: {
        getElementById: function (id) {
            if (F[id]) return F[id];
            if (/^(fuel|ox)-properties-/.test(id)) {
                if (!SP[id]) SP[id] = new El(id, ''); return SP[id]; }
            return null; },
        createElement: function (t) { return new El('', ''); },
        addEventListener: function (t, fn) { if (t === 'input') listeners.push(fn); },
    },
    fetch: function (url, init) {
        const b = JSON.parse(init.body);
        const k = b.propellant_type + '|' + b.propellant_name;
        if (P.fail && P.fail.indexOf(k) >= 0) return Promise.resolve({ ok: false });
        if (!P.responses[k]) return Promise.reject(new Error('stub ' + k));
        return Promise.resolve({ ok: true,
            json: function () { return Promise.resolve(P.responses[k]); } });
    },
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(srcPath, 'utf8'), sandbox, { filename: 'liq.js' });
function input(id, v, trusted) {
    F[id].value = String(v);
    listeners.forEach(function (fn) { fn({ target: F[id], isTrusted: !!trusted }); });
}
(async function () {
    const log = [];
    for (const adim of P.steps) {
        if (adim.op === 'fuel') {
            F.fuel_type.value = adim.v;
            await sandbox.loadPropellantProperties(adim.v, 'lox');
        } else if (adim.op === 'restore') {
            input('fuel_density', adim.v, false);
        } else if (adim.op === 'type') {
            input('fuel_density', adim.v, true);
        }
        const not = F.fuel_density_owner_note;
        log.push({ op: adim.op, v: adim.v, value: F.fuel_density.value,
                   owner: F.fuel_density.getAttribute('data-hrma-owner'),
                   note: not ? not.textContent : null });
    }
    process.stdout.write(JSON.stringify(log));
})().catch(function (e) { console.error(String(e && e.stack || e)); process.exit(3); });
"""


def _sablon(html, ad):
    from tests.test_z5guard_panel_motor import _sablon_fonksiyonu
    return _sablon_fonksiyonu(html, ad)


def yogunluk_kaynagi(html):
    """liquid.html'den kapı + dinleyici birimi (ölçüm betiği de kullanır)."""
    parcalar = ['const LIQUID_SIGFIG_DENSITY = 6, LIQUID_SIGFIG_TRANSPORT = 4;']
    for ad in ('numTxt', 'liquidSigFig', 'liqStateTempText', 'liqExpTxt',
               'propellantProvenance', 'markFieldProvenance',
               'liquidAutofillBayragi', 'liquidAutofillMi',
               'liquidAutofillField', 'liquidClearUnresolvedField',
               'loadPropellantProperties'):
        parcalar.append(_sablon(html, ad))
    bas = html.index("        document.addEventListener('input', function (ev) {")
    son = html.index('\n        }, true);', bas) + len('\n        }, true);')
    parcalar.append(html[bas:son])
    return '\n'.join(parcalar)


def yogunluk_kos(kaynak, yanitlar, adimlar, fuel0='rp1', fail=None):
    with tempfile.TemporaryDirectory() as tmp:
        s = os.path.join(tmp, 's.js')
        h = os.path.join(tmp, 'h.js')
        p = os.path.join(tmp, 'p.json')
        for yol, metin in ((s, kaynak), (h, YOGUNLUK_HARNESS)):
            with open(yol, 'w', encoding='utf-8') as fh:
                fh.write(metin)
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump({'responses': yanitlar, 'steps': adimlar,
                       'fuel0': fuel0, 'fail': fail or []}, fh)
        proc = subprocess.run([NODE, h, s, p], capture_output=True,
                              text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


@pytest.fixture(scope='module')
def itici_yanitlari(istemci):
    out = {}
    for tur, ad in (('liquid_fuel', 'rp1'), ('liquid_fuel', 'lh2'),
                    ('liquid_fuel', 'mmh'), ('oxidizer', 'lox')):
        r = _sessiz(istemci.post, '/api/get-propellant-properties',
                    json={'propellant_type': tur, 'propellant_name': ad})
        assert r.status_code == 200
        out[tur + '|' + ad] = r.get_json()
    return out


@pytest.fixture(scope='module')
def yogunluk_birimi():
    return yogunluk_kaynagi(_oku('hrma', 'templates', 'liquid.html'))


@node_gerekli
class TestYogunlukYakitiIzler:
    def test_proje_degeri_yakit_degisince_katalogu_izler(
            self, yogunluk_birimi, itici_yanitlari):
        lh2 = itici_yanitlari['liquid_fuel|lh2']['properties']['density']
        log = yogunluk_kos(yogunluk_birimi, itici_yanitlari, [
            {'op': 'restore', 'v': '810'}, {'op': 'fuel', 'v': 'lh2'}])
        assert float(log[-1]['value']) == pytest.approx(lh2, rel=1e-5)
        assert not log[-1]['note']

    def test_yakit_cekilemezse_baska_yakitin_sayisi_kalmaz(
            self, yogunluk_birimi, itici_yanitlari):
        """Uç yanıt vermezse RP-1'in 810'u LH2 girdisi diye gitmez."""
        log = yogunluk_kos(yogunluk_birimi, itici_yanitlari, [
            {'op': 'restore', 'v': '810'}, {'op': 'fuel', 'v': 'lh2'}],
            fail=['liquid_fuel|lh2'])
        assert log[-1]['value'] == '', log

    def test_cozulmeyen_yeni_yakitta_eski_proje_degeri_bosalir(
            self, yogunluk_birimi, itici_yanitlari):
        log = yogunluk_kos(yogunluk_birimi, itici_yanitlari, [
            {'op': 'restore', 'v': '810'}, {'op': 'fuel', 'v': 'mmh'}])
        assert log[-1]['value'] == '', log

    def test_ayni_yakitta_proje_degeri_korunur(self, yogunluk_birimi,
                                               itici_yanitlari):
        log = yogunluk_kos(yogunluk_birimi, itici_yanitlari, [
            {'op': 'restore', 'v': '805'}, {'op': 'fuel', 'v': 'rp1'}])
        assert log[-1]['value'] == '805'

    def test_elle_girilen_deger_korunur_ve_uyari_basilir(
            self, yogunluk_birimi, itici_yanitlari):
        lh2 = itici_yanitlari['liquid_fuel|lh2']['properties']['density']
        log = yogunluk_kos(yogunluk_birimi, itici_yanitlari, [
            {'op': 'type', 'v': '900'}, {'op': 'fuel', 'v': 'lh2'}])
        son = log[-1]
        assert son['value'] == '900'
        assert son['note'] and '900' in son['note'] and 'LH2' in son['note']
        assert ('%.1f' % lh2) in son['note'], son['note']
        # kullanıcı yeniden yazınca uyarı kalkar
        log = yogunluk_kos(yogunluk_birimi, itici_yanitlari, [
            {'op': 'type', 'v': '900'}, {'op': 'fuel', 'v': 'lh2'},
            {'op': 'type', 'v': '72'}])
        assert log[-1]['value'] == '72' and not log[-1]['note']

    def test_elle_deger_cozulmeyen_yakitta_da_korunur_uyariyla(
            self, yogunluk_birimi, itici_yanitlari):
        log = yogunluk_kos(yogunluk_birimi, itici_yanitlari, [
            {'op': 'type', 'v': '72'}, {'op': 'fuel', 'v': 'mmh'}],
            fuel0='lh2')
        assert log[-1]['value'] == '72'
        assert log[-1]['note'] and 'MMH' in log[-1]['note']

    def test_uyari_metni_i18n_anahtarli_en_tr(self):
        html = _oku('hrma', 'templates', 'liquid.html')
        sayfalar = _oku('hrma', 'static', 'js', 'i18n_pages.js')
        for anahtar in ('liq.msg.fuel_density_other_fuel',
                        'liq.msg.fuel_density_table_value',
                        'liq.msg.fuel_density_no_table_value'):
            assert anahtar in html, anahtar
            degerler = re.findall(r"'%s':\s*'((?:[^'\\]|\\.)*)'"
                                  % re.escape(anahtar), sayfalar)
            assert len(degerler) == 2 and degerler[0] != degerler[1], anahtar
            yer = [sorted(re.findall(r'\{(\w+)\}', d)) for d in degerler]
            assert yer[0] == yer[1], (anahtar, yer)

    def test_uyari_innerhtml_ile_basilmaz(self):
        govde = _sablon(_oku('hrma', 'templates', 'liquid.html'),
                        'loadPropellantProperties')
        i = govde.index('fuel_density_owner_note')
        blok = govde[i - 1500:i + 1500]
        assert '.textContent = ' in blok
        assert 'not.innerHTML' not in blok


# =========================================================================
# 6 — basınç beslemede turbopompa alanları adıyla beyan
# =========================================================================
from tests.test_v3_taban_a_turbinsiz import (  # noqa: E402
    BEYAN_ANAHTARLARI, EK_EPS5, _duz)



def _pf_govde(cevrim='pressure_fed', **d):
    from tests.support.form_defaults import sayisal_varsayilanlar
    g = dict(sayisal_varsayilanlar('liquid'))
    g.update(EK_EPS5)
    g['engine_cycle'] = cevrim
    for k, v in d.items():
        if v is None:
            g.pop(k, None)
        else:
            g[k] = v
    return g


@pytest.fixture(scope='module')
def tp_yanitlari(istemci):
    def post(g):
        r = _sessiz(istemci.post, '/calculate_liquid', json=g)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return r.get_json()
    return {
        'ile': post(_pf_govde(turbopump_efficiency=50.0,
                              generator_gas_temp=1500.0)),
        'olmadan': post(_pf_govde(turbopump_efficiency=None,
                                  generator_gas_temp=None)),
        'gg': post(_pf_govde('gas_generator', turbopump_efficiency=50.0,
                             generator_gas_temp=1500.0)),
    }


def test_basinc_beslemede_turbopompa_alanlari_beyan_edilir(tp_yanitlari):
    from hrma.engines.liquid_rocket_engine import (
        TURBOPUMP_INPUT_FIELDS, TURBOPUMP_INPUT_UNUSED_REASON)
    y = tp_yanitlari['ile']
    beyan = {b['field']: b for b in y.get('inputs_not_used') or []
             if b.get('reason') == TURBOPUMP_INPUT_UNUSED_REASON}
    assert sorted(beyan) == sorted(TURBOPUMP_INPUT_FIELDS)
    assert beyan['turbopump_efficiency']['submitted'] == 50.0
    assert beyan['generator_gas_temp']['submitted'] == 1500.0
    for alan, b in beyan.items():
        assert b['used_by_model'] is None
        assert alan in b['message'] and 'no turbopump' in b['message']
    # Beyan YALNIZ inputs_not_used'da: uyarı kümesi gönderilmeyen gövdeyle
    # aynı (test_d37_sivi_kati_a1 TestCevrimFormu kilidiyle uyumlu).
    assert y['input_warnings'] == tp_yanitlari['olmadan']['input_warnings']


def test_gonderilmezse_beyan_yok(tp_yanitlari):
    from hrma.engines.liquid_rocket_engine import TURBOPUMP_INPUT_UNUSED_REASON
    y = tp_yanitlari['olmadan']
    assert not [b for b in y.get('inputs_not_used') or []
                if b.get('reason') == TURBOPUMP_INPUT_UNUSED_REASON]


def test_beyan_dogru_yayimlanan_sayi_degismez(tp_yanitlari):
    """Beyanın iddiası ('hiçbir sonucu değiştirmedi') ölçülür."""
    a = dict(_duz({k: v for k, v in tp_yanitlari['ile'].items()
                   if k not in BEYAN_ANAHTARLARI}))
    b = dict(_duz({k: v for k, v in tp_yanitlari['olmadan'].items()
                   if k not in BEYAN_ANAHTARLARI}))
    farkli = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    assert farkli == [], farkli[:10]


def test_turbopompali_cevrimde_beyan_yok(tp_yanitlari):
    from hrma.engines.liquid_rocket_engine import TURBOPUMP_INPUT_UNUSED_REASON
    y = tp_yanitlari['gg']
    assert not [b for b in y.get('inputs_not_used') or []
                if b.get('reason') == TURBOPUMP_INPUT_UNUSED_REASON]


@pytest.mark.parametrize('ham,beklenen', [
    (float('nan'), 'nan'), ('x' * 100, 'x' * 80), (True, 'bool'),
    ('60', 60.0)])
def test_yanki_fail_closed(ham, beklenen):
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    m = LiquidRocketEngine.__new__(LiquidRocketEngine)
    m.overrides = {'turbopump_efficiency': ham}
    m.design_warnings = []
    beyan = m._declare_turbopump_inputs_unused()
    assert len(beyan) == 1 and beyan[0]['submitted'] == beklenen
    assert 'NaN' not in json.dumps(beyan, allow_nan=False)

