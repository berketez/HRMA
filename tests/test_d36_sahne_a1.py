"""ÖH D36 · kulvar **sahne-hud** · a1 — bekçi.

Kalemler (kanıt: docs/scofield/raw/OH/D36/sahne-hud/a1/):
  1. OH-P-11 / B-2 kalanı — 3B güverte HUD (motor_viz_deck.js) sayıları TR'de
     VİRGÜL: saat, çipler, hız düğmesi, tasarım sürgüsü, ısı efsanesi, CFD
     aralığı. Ölçülen önce: TR kipinde 14 noktalı ondalık / 0 virgül.
  2. Berke 22 Eyl ("ANSYS gibi"): CFD koşumu bitince alan 3B sahneye
     TIKLAMASIZ gider (panels/cfd_panel.js `autoViz3d`), sahne görünüme
     kaydırılır, colorbar sahnenin ALTINDA yatay durur ve sayıları TR'de
     virgüllüdür (motor_viz3d.js `_cfdUpdateColorbar` + `decTxt`). Alan
     yoksa hiçbir çağrı yapılmaz; aynı yanıt yeniden çizilince (büyüklük
     seçici / dil değişimi) ikinci kez gönderilmez (KAPAT korunur).
  3. OH-P-14 Three.js ayağı: gerçek katı motor ölçüleriyle cameraFrameFit
     kadrajı dolu (fill ≥ 0,5) — "iğne" görünümü bu dosyada değil,
     solid.html'in Plotly yedek yolunda (devir).
  4. analysis_center.js koşum süresi metni: TR "d,d sn", EN "d.d s"; Merkez
     ve kiracının KENDİ metinlerinde TR kipinde İngilizce kalıntı yok
     (kalan İngilizce ucun yanıt beyanlarıdır — ölçülüp devredildi).
  5. hud.js sayacı TR virgül (zaten kanona bağlıydı; kilitlenir).

ÖLÇÜM YÖNTEMİ: GERÇEK dosyalar node altında koşar (kaynak DOSYADAN
okunur; inspect.getsource YOK). i18n motoru gerçek i18n.js'tir. Merkez +
kiracı düzeneği tests/test_cfd_panel.py::HARNESS'ten türetilir (ikinci
düzenek yazılmaz); motor sonucu ve CFD yanıtı gerçek Flask uçlarından.

Koşum hedeflidir:
    python3 -m pytest tests/test_d36_sahne_a1.py -q
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_cfd_endpoint import _sessiz, govde
from tests.test_cfd_panel import HARNESS, KATI_GOVDE, viz3d_tablo_bildirimleri

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

ONDALIK_NOKTA = re.compile(r'\d\.\d')
ONDALIK_VIRGUL = re.compile(r'\d,\d')
# TR ekranda geçmemesi gereken İngilizce işlev sözcükleri
EN_KALINTI = re.compile(
    r'\b(the|and|with|from|this|that|was|were|are|for|not|of|in the|is)\b')


def _node(script, argv=(), timeout=300):
    env = dict(os.environ)
    env['HRMA_ARGS'] = json.dumps([str(a) for a in argv])
    p = subprocess.run([NODE], input=script, env=env,
                       capture_output=True, text=True, timeout=timeout)
    assert p.returncode == 0, 'node çöktü:\n' + p.stderr[-3000:]
    return json.loads(p.stdout)


FAKE_DOM = r"""
const nodes = {};
function makeNode(id) {
    const n = {
        id: id, innerHTML: '', textContent: '', title: '', value: '',
        disabled: false, attrs: {}, classes: {}, onclick: null, children: [],
        style: { setProperty(k, v) { this[k] = v; } }, dataset: {},
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild(c) { this.children.push(c); return c; },
        querySelector() { return null; }, querySelectorAll() { return []; },
        addEventListener(type, fn) { (this.handlers = this.handlers || {})[type] = fn; },
        scrollIntoView() { this.scrolled = (this.scrolled || 0) + 1; },
    };
    n.classList = {
        toggle(c, on) { n.classes[c] = (on === undefined) ? !n.classes[c] : !!on; },
        add(c) { n.classes[c] = true; }, remove(c) { n.classes[c] = false; },
        contains(c) { return !!n.classes[c]; },
    };
    return n;
}
global.document = {
    body: makeNode('body'),
    documentElement: { lang: 'en', setAttribute() {}, getAttribute() { return null; } },
    readyState: 'complete',
    getElementById(id) { if (!(id in nodes)) nodes[id] = makeNode(id); return nodes[id]; },
    createElement() { return makeNode(null); },
    querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener() {}, dispatchEvent() {},
};
global.window = global;
Object.defineProperty(global, 'localStorage', { value: { getItem() { return null; }, setItem() {} }, configurable: true });
Object.defineProperty(global, 'navigator', { value: { language: 'en' }, configurable: true });
let nowMs = 0;
global.performance = { now() { return nowMs; } };
global.matchMedia = function () { return { matches: true }; };
const ARGS = JSON.parse(process.env.HRMA_ARGS);
"""


# ---------------------------------------------------------------------------
# Kaynak çıkarıcılar (motor_viz3d.js) — dosyadan, regex/derinlik ile
# ---------------------------------------------------------------------------
def _viz_src():
    return (JS / 'motor_viz3d.js').read_text(encoding='utf-8')


def _blok(src, baslangic):
    start = src.index(baslangic)
    depth, i = 0, start
    while i < len(src):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError(baslangic + ' kapanmıyor')


def _fn(src, name):
    return _blok(src, 'function %s(' % name)


def _method(src, name):
    return _blok(src, 'MotorScene.prototype.%s = function' % name)


def _const(src, name):
    m = re.search(r'var %s = [^;]+;' % re.escape(name), src)
    assert m, name
    return m.group(0)


# ---------------------------------------------------------------------------
# 1) GÜVERTE — motor_viz_deck.js
# ---------------------------------------------------------------------------
DECK_SCRIPT = FAKE_DOM + r"""
const [i18nPath, deckPath, vizPath, lang] = ARGS;
if (i18nPath !== 'YOK') { require(i18nPath); window.I18N.setLang(lang); }
const src = require('fs').readFileSync(vizPath, 'utf8');
function bildirim(ad) { return src.match(new RegExp('var ' + ad + ' = [^;]+;'))[0]; }
eval(bildirim('CFD_METRICS')); eval(bildirim('CFD_COLORSCALES'));
let hooks = null;
const viz = {
    state: { cutaway: true, labels: true, plume: true, exploded: false,
             autoRotate: false, portShape: 'circular', playing: false, heatMap: false },
    dims: { burnTime: 10 },
    getHeatInfo() { return { qRampMin: 1.234e6, qRampMax: 3.2789e6, qChamber: 1.5e6,
                             tWallInner: 1234.6, tWallOuter: 987.4 }; },
    setHeatMap() { return true; },
    getCfdField() { return { metric: 'mach', metrics: ['mach', 'pressure'],
        range: { min: 0.115, max: 2.912 }, cells: { axial: 60, radial: 12 },
        stations: { shown: 60, total: 60 }, decimated: false }; },
    getCfdReject() { return null; },
    setCfdMetric() { return { ok: true }; }, clearCfdField() { return true; },
    setPortShape() {}, cyclePortShape() {}, cycleCameraPreset() { return 'iso'; },
    setQuality() {}, cycleSpeed() { return 0.5; }, snapshot() { return null; },
    setCutaway() {}, setLabels() {}, setPlume() {}, setExploded() {},
    setAutoRotate() {}, resetCamera() {}, play() {}, pause() {}, setTime() {}, update() {},
};
global.MotorViz3D = { isSupported() { return true; },
    mount(id, md, h) { hooks = h; return viz; }, update() {},
    CFD_METRICS: CFD_METRICS, CFD_COLORSCALES: CFD_COLORSCALES };
require(deckPath);
const deck = window.MotorVizDeck.create('deck_host',
    { chamber_diameter: 0.1, chamber_length: 0.3, throat_diameter: 0.0212,
      exit_diameter: 0.0424, chamber_pressure: 40.25, thrust: 1234.5, isp: 222.8,
      burn_time: 3.2, viz_motor_type: 'solid', expansion_ratio: 4.0 },
    { motorType: 'solid' });
const p = deck.prefix;
nowMs += 1000;
hooks.onTick({ playing: true, burning: true, time: 1.234, burnTime: 3.2,
               portDiameter: 40.05, webRemaining: 0.678, of: 5.25, isp: 222.8,
               thrust: 1234.5, pc: 4025000 });
nodes[p + '_btn_speed'].onclick();
document.getElementById(p + '_design').style.display = 'none';
nodes[p + '_btn_design'].onclick();
nodes[p + '_btn_heat'].onclick();
const out = {};
['_clock', '_port', '_web', '_of', '_isp', '_thrust', '_pc', '_eps', '_dt',
 '_cfd_range', '_btn_speed', '_dv_dch', '_dv_len', '_dv_eps', '_hl_min', '_hl_max',
 '_hl_wall'].forEach(function (k) {
    const n = nodes[p + k];
    if (n) out[k] = n.innerHTML || n.textContent;
});
process.stdout.write(JSON.stringify(out));
"""


def _guverte(lang, i18n=True):
    out = _node(DECK_SCRIPT, [JS / 'i18n.js' if i18n else 'YOK',
                              JS / 'motor_viz_deck.js', JS / 'motor_viz3d.js', lang])
    return out, ' '.join(str(v) for v in out.values())


class TestGuverteSayiBicimi:
    def test_tr_kipinde_virgul_nokta_yok(self):
        out, metin = _guverte('tr')
        assert not ONDALIK_NOKTA.findall(metin), (
            'TR güvertede noktalı ondalık: %r' % out)
        assert len(ONDALIK_VIRGUL.findall(metin)) >= 10, out
        # Saat, çip, sürgü, efsane ve CFD aralığı — her aile ayrı ayrı
        assert out['_clock'].startswith('t = <b>1,23</b> s / 3,20 s'), out['_clock']
        assert out['_port'].startswith('40,0'), out['_port']
        assert out['_web'] == '%68', out['_web']          # TDK: işaret önde
        assert out['_isp'].startswith('222,8'), out['_isp']
        assert out['_pc'].startswith('40,3'), out['_pc']
        assert out['_cfd_range'].startswith('0,115'), out['_cfd_range']
        assert out['_btn_speed'].startswith('0,5'), out['_btn_speed']
        assert out['_dv_dch'].startswith('100,0'), out['_dv_dch']
        assert out['_hl_min'].startswith('1,23'), out['_hl_min']

    def test_en_kipinde_nokta(self):
        out, metin = _guverte('en')
        assert not ONDALIK_VIRGUL.findall(metin), out
        assert out['_web'] == '68%', out['_web']
        assert out['_clock'].startswith('t = <b>1.23</b> s / 3.20 s'), out['_clock']

    def test_i18nsiz_eski_davranis_korunur(self):
        """Sözlük motoru yokken sayı UYDURULMAZ, yalnız ayraç yerelleşmez
        (tests/test_cfd_alan_koprusu.py düzeneği güverteyi I18N'siz koşturur)."""
        out, metin = _guverte('tr', i18n=False)
        assert not ONDALIK_VIRGUL.findall(metin), out
        assert out['_cfd_range'].startswith('0.115'), out['_cfd_range']

    def test_kaynakta_ciplak_toFixed_kalmadi(self):
        """Ayraç kararı tek kaynakta: güverte gövdesinde `toFixed` yalnız
        I18N'siz yedek yolda (numTxt) durur."""
        src = (JS / 'motor_viz_deck.js').read_text(encoding='utf-8')
        govde = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
        govde = re.sub(r'//[^\n]*', '', govde)
        assert len(re.findall(r'\.toFixed\(', govde)) == 1, (
            'güvertede çıplak toFixed geri geldi')
        assert 'function numTxt(' in src and 'function unitTxt(' in src


# ---------------------------------------------------------------------------
# 2a) COLORBAR — motor_viz3d.js
# ---------------------------------------------------------------------------
def _colorbar(lang):
    src = _viz_src()
    parcalar = [_const(src, 'CFD_METRICS'), _const(src, 'CFD_COLORSCALES'),
                _fn(src, 'cfdColorbarTicks'), _fn(src, 'cfdTickLabel'),
                _fn(src, 'cfdFormatTemplate'), _fn(src, 'decTxt')]
    script = FAKE_DOM + r"""
const [i18nPath, lang] = ARGS;
require(i18nPath); window.I18N.setLang(lang);
function T(k, f) { return window.I18N.t(k, f); }
var MotorScene = function () {};
""" + '\n'.join(parcalar) + '\n' + _method(src, '_cfdUpdateColorbar') + r""";
const s = new MotorScene();
const kap = makeNode('viewport');
s.container = kap;
s._cfdLayer = { metric: 'pressure', range: { min: 44125.7, max: 1987654.3 },
                decimated: false, stationsShown: 60, stationsTotal: 60, colorbarEl: null };
s._cfdUpdateColorbar();
const el = s._cfdLayer.colorbarEl;
process.stdout.write(JSON.stringify({ cssText: el.style.cssText, html: el.innerHTML,
    attrs: el.attrs, appended: kap.children.length }));
"""
    out = _node(script, [JS / 'i18n.js', lang])
    out['metin'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', out['html'])).strip()
    return out


class TestColorbar:
    def test_sahnenin_altinda_yatay(self):
        out = _colorbar('tr')
        css = out['cssText']
        assert 'bottom:' in css and 'left:8px' in css, css
        assert 'top:50%' not in css and 'translateY' not in css, (
            'colorbar hâlâ sol kenarda dikey: %s' % css)
        assert 'to right' in out['html'], 'gradyan yatay değil'
        assert out['appended'] == 1 and out['attrs'].get('data-cfd-colorbar') == '1'
        assert out['attrs'].get('data-cfd-metric') == 'pressure'
        assert 'data-cfd-colorbar-min=' in out['html'] and 'data-cfd-colorbar-max=' in out['html']
        assert '[Pa]' in out['metin'], out['metin']           # birim başlıkta

    def test_tr_virgul_en_nokta(self):
        tr = _colorbar('tr')
        assert not ONDALIK_NOKTA.findall(tr['metin']), tr['metin']
        assert '44125,7' in tr['metin'] and '1,99e6' in tr['metin'], tr['metin']
        en = _colorbar('en')
        assert not ONDALIK_VIRGUL.findall(en['metin']), en['metin']
        assert '44125.7' in en['metin'], en['metin']

    def test_tik_etiketi_saf_kaldi(self):
        """cfdTickLabel ayraç seçmez (tek kaynak i18n.js); yerelleşme YALNIZ
        colorbar gövdesinde decTxt ile."""
        src = _viz_src()
        assert 'I18N' not in _fn(src, 'cfdTickLabel')
        assert _method(src, '_cfdUpdateColorbar').count('decTxt(cfdTickLabel(') >= 3


# ---------------------------------------------------------------------------
# 2b) OTOMATİK KÖPRÜ — panels/cfd_panel.js (Merkez + kiracı, gerçek yükler)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def yukler():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        r = _sessiz(c.post, '/calculate_solid', json=KATI_GOVDE)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        motor = r.get_json()
        r2 = _sessiz(c.post, '/api/cfd/nozzle', json=govde())
        assert r2.status_code == 200, r2.get_data(as_text=True)[:300]
        yanit = r2.get_json()
    assert (yanit.get('cfd') or {}).get('field'), 'uç alan bloğu yayımlamıyor'
    return motor, yanit


def _merkez_harness():
    """tests/test_cfd_panel.py::HARNESS + gerçek i18n motoru + sahne kabı."""
    h = HARNESS.replace('/*VIZ3D_TABLES*/', viz3d_tablo_bildirimleri())
    yamalar = [
        ("        querySelector() { return null; },\n"
         "        addEventListener(type, fn) { (this.handlers = this.handlers || {})[type] = fn; },\n",
         "        querySelector() { return null; },\n"
         "        querySelectorAll() { return []; },\n"
         "        scrollIntoView() { this.scrolled = (this.scrolled || 0) + 1; },\n"
         "        addEventListener(type, fn) { (this.handlers = this.handlers || {})[type] = fn; },\n"),
        ("global.window = global;\n",
         "global.window = global;\n"
         "global.document.documentElement = { lang: 'en', setAttribute() {}, getAttribute() { return null; } };\n"
         "global.document.readyState = 'complete';\n"
         "global.document.dispatchEvent = function () {};\n"
         "Object.defineProperty(global, 'localStorage', { value: { getItem() { return null; }, setItem() {} }, configurable: true });\n"
         "Object.defineProperty(global, 'navigator', { value: { language: 'en' }, configurable: true });\n"
         "if (payload.lang) { require(payload.i18nPath); require(payload.commonPath);"
         " require(payload.chartsPath); window.I18N.setLang(payload.lang); }\n"),
        ("    global.MotorViz3D = {\n        isSupported: function () { return vizCfg.supported !== false; },",
         "    global.MotorViz3D = {\n        get: function () { return { container: document.getElementById('viz_host') }; },\n"
         "        isSupported: function () { return vizCfg.supported !== false; },"),
        ("    out.viz3dCalls = viz3dCalls;",
         "    // ÖH D36: aynı yanıtı yeniden çiz (büyüklük seçici / dil değişimi yolu)\n"
         "    if (payload.redraw) {\n"
         "        const h = AC.history(); const son = h[h.length - 1];\n"
         "        if (payload.clearBefore && global.MotorViz3D) global.MotorViz3D.clearCfdField();\n"
         "        for (let i = 0; i < payload.redraw; i++) CP._render(son.data, document.getElementById('ac_view_root'));\n"
         "    }\n"
         "    // ÖH D36 a1 düzeltmesi: geçmiş şeridinde kayıtlar arasında gezin\n"
         "    if (payload.replayHistory) {\n"
         "        if (global.MotorViz3D) global.MotorViz3D.clearCfdField();\n"
         "        const h = AC.history();\n"
         "        payload.replayHistory.forEach(function (i) { CP._render(h[i].data, document.getElementById('ac_view_root')); });\n"
         "    }\n"
         "    out.viz3dCalls = viz3dCalls;\n"
         "    out.autoBridged = !!(CP._lastAutoBridgedCfd && CP._lastAutoBridgedCfd());\n"
         "    out.vizHostScrolled = nodes['viz_host'] ? (nodes['viz_host'].scrolled || 0) : 0;"),
    ]
    for eski, yeni in yamalar:
        assert h.count(eski) == 1, 'HARNESS deseni değişti: %r' % eski[:60]
        h = h.replace(eski, yeni)
    return h


def _merkez(tmp_path, lang, motor, yanit, **ek):
    betik = tmp_path / ('kos_merkez_%s.js' % (lang or 'nolang'))
    betik.write_text(_merkez_harness(), encoding='utf-8')
    payload = {'motorType': 'solid', 'results': motor, 'response': yanit,
               'select': ['nozzle_flow', 'cfd'], 'runs': 1, 'lang': lang,
               'i18nPath': str(JS / 'i18n.js'),
               'commonPath': str(JS / 'i18n_common.js'),
               'chartsPath': str(JS / 'i18n_charts.js')}
    payload.update(ek)
    girdi = tmp_path / ('girdi_%s.json' % (lang or 'nolang'))
    girdi.write_text(json.dumps(payload), encoding='utf-8')
    p = subprocess.run([NODE, str(betik), str(girdi),
                        str(JS / 'analysis_center.js'),
                        str(JS / 'panels' / 'cfd_panel.js')],
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, 'Merkez node altında çöktü:\n' + p.stderr[-3000:]
    out = json.loads(p.stdout)
    out['viz3d_durum'] = [v['text'] for k, v in out['nodes'].items()
                          if k.startswith('cfd_viz3d_status_')]
    return out


class TestOtomatikKopru:
    def test_alan_gelince_sahneye_tiklamasiz(self, tmp_path, yukler):
        motor, yanit = yukler
        out = _merkez(tmp_path, 'tr', motor, yanit)
        cagrilar = [c['fn'] for c in out['viz3dCalls']]
        assert 'setCfdField' in cagrilar, (
            'koşum bitti, alan geldi ama sahneye gönderilmedi (tıklama bekleniyor)')
        assert out['autoBridged'] is True
        assert out['vizHostScrolled'] >= 1, 'sahne görünüme kaydırılmadı'
        durum = ' '.join(out['viz3d_durum'])
        assert 'kendiliğinden' in durum, durum
        assert 'Mach' in durum and ONDALIK_VIRGUL.search(durum), durum
        assert not ONDALIK_NOKTA.search(durum), 'TR durumda noktalı ondalık: ' + durum

    def test_en_kipinde_beyan(self, tmp_path, yukler):
        motor, yanit = yukler
        out = _merkez(tmp_path, 'en', motor, yanit)
        durum = ' '.join(out['viz3d_durum'])
        assert 'automatically' in durum and 'Mach' in durum, durum

    def test_alan_yoksa_hicbir_cagri_yok(self, tmp_path, yukler):
        motor, yanit = yukler
        alansiz = json.loads(json.dumps(yanit))
        del alansiz['cfd']['field']
        out = _merkez(tmp_path, 'tr', motor, alansiz)
        assert not out['viz3dCalls'], 'alan yokken sahneye çağrı yapıldı: %r' % out['viz3dCalls']
        assert out['autoBridged'] is False
        html = out['nodes']['ac_view_root']['html']
        assert 'alan bloğu taşımıyor' in html, 'alan yokluğu adıyla beyan edilmemiş'

    def test_ayni_yanit_yeniden_cizilince_tekrar_gonderilmez(self, tmp_path, yukler):
        """Büyüklük seçici / dil değişimi aynı yanıtı yeniden çizer; KAPAT
        denmişse alan geri GELMEZ — gönderim yalnız yeni yanıtta."""
        motor, yanit = yukler
        out = _merkez(tmp_path, 'tr', motor, yanit, redraw=2, clearBefore=True)
        gonderim = [c for c in out['viz3dCalls'] if c['fn'] == 'setCfdField']
        assert len(gonderim) == 1, (
            'aynı yanıt yeniden çizilince alan yeniden gönderildi: %r' % out['viz3dCalls'])
        assert 'clearCfdField' in [c['fn'] for c in out['viz3dCalls']]

    def test_gecmis_seridinde_gezinince_kapat_korunur(self, tmp_path, yukler):
        """ÖH D36 a1 denetimi: iki koşum (iki ayrı yanıt nesnesi) → ikisi de
        bittiği anda birer kez gönderilir. Sonra şeritten KAPAT; geçmişte
        eski ve yeni kayıt arasında gezinmek alanı GERİ GETİRMEZ. Tek
        yuvalı kimlik (`lastAutoBridgedCfd`) eski kayda dönüşte yeniden
        gönderiyordu (ölçüldü: 2 yerine 5 gönderim)."""
        motor, yanit = yukler
        out = _merkez(tmp_path, 'tr', motor, yanit, runs=2, replayHistory=[0, 1, 0])
        gonderim = [c for c in out['viz3dCalls'] if c['fn'] == 'setCfdField']
        assert len(gonderim) == 2, (
            'geçmişte gezinince KAPAT çiğnendi: %d gönderim' % len(gonderim))

    def test_sahne_yokken_kopru_yok_ve_cokme_yok(self, tmp_path, yukler):
        motor, yanit = yukler
        out = _merkez(tmp_path, 'tr', motor, yanit, viz3d={'absent': True})
        assert not out['viz3dCalls']
        assert out['autoBridged'] is False

    def test_kaynak_kapisi_alan_varsa_kosulsuz(self):
        """drawInto: `if (vm.field)` bloğu bindViz3d + autoViz3d'yi birlikte
        çağırır; düğme yolu ile otomatik yol AYNI gönderim işlevini kullanır."""
        src = (JS / 'panels' / 'cfd_panel.js').read_text(encoding='utf-8')
        m = re.search(r'if \(vm\.field\) \{\s*bindViz3d\([^)]*\);[^}]*autoViz3d\(cfd, vm, viz3dStatusId\);', src)
        assert m, 'drawInto alan varken otomatik köprüyü çağırmıyor'
        # 1 tanım + 2 çağrı (düğme yolu, otomatik yol) — üçüncü bir gönderim mantığı yok
        assert src.count('sendToViz3d(cfd, vm);') == 2, 'düğme ve otomatik yol ayrı gönderim mantığı kurmuş'
        assert src.count('function sendToViz3d(cfd, vm)') == 1
        assert "'panel.cfd.viz3dAuto'" in src

    def test_sozluk_anahtari_iki_dilde(self):
        src = (JS / 'i18n_common.js').read_text(encoding='utf-8')
        assert src.count("'panel.cfd.viz3dAuto':") == 2
        tr = re.search(r"'panel\.cfd\.viz3dAuto': '([^']*kendiliğinden[^']*)'", src)
        assert tr, 'TR karşılığı yok ya da İngilizce kopya'


# ---------------------------------------------------------------------------
# 3) OH-P-14 Three.js ayağı — gerçek katı ölçüleriyle kadraj
# ---------------------------------------------------------------------------
class TestKatiKadraj:
    def test_gercek_kati_motor_kadraji_dolu(self, yukler):
        motor, _ = yukler
        src = _viz_src()
        consts = '\n'.join(_const(src, n) for n in
                           ['CAMERA_FOV_DEG', 'CAMERA_FIT_MARGIN', 'CAMERA_SLENDER_RATIO',
                            'CAMERA_DIR_REGULAR', 'CAMERA_DIR_DIAGONAL'])
        cad = motor.get('cad_design') or {}
        case = cad.get('case_design') or {}
        dch = float(motor['chamber_diameter']) / 1000.0
        lch = (float(case['length']) / 1000.0 if isinstance(case.get('length'), (int, float))
               else float(motor['grain_length']) / 1000.0 / 0.9)
        zs = [float(p[0]) for p in (motor.get('nozzle_contour') or {}).get('points', [])] or [0.0]
        ltot = lch + (max(zs) - min(zs))
        script = consts + '\n' + _fn(src, 'cameraFrameFit') + (
            "\nconst f = cameraFrameFit(%r, %r, CAMERA_FOV_DEG, 800/580);"
            "process.stdout.write(JSON.stringify({fill: f.fill, slender: f.slender}));"
            % (ltot / 2.0, dch / 2.0 * 1.1))
        out = _node(script)
        assert 0.5 <= out['fill'] <= 1.01, (
            'Three.js kadrajı katı motoru küçük bırakıyor: %r (L/D=%.2f)'
            % (out, ltot / dch))


# ---------------------------------------------------------------------------
# 4) MERKEZ — süre metni + kendi metinlerinde İngilizce kalıntı yok
# ---------------------------------------------------------------------------
class TestMerkezMetinleri:
    def test_sure_tr_bir_ondalik_virgul(self, tmp_path, yukler):
        motor, yanit = yukler
        out = _merkez(tmp_path, 'tr', motor, yanit)
        st = out['nodes']['ac_status']['text']
        assert re.fullmatch(r'\d+,\d sn içinde tamamlandı\.', st), st

    def test_sure_en_bir_ondalik_nokta(self, tmp_path, yukler):
        motor, yanit = yukler
        out = _merkez(tmp_path, 'en', motor, yanit)
        st = out['nodes']['ac_status']['text']
        assert re.fullmatch(r'Completed in \d+\.\d s\.', st), st

    def test_kaynakta_ciplak_toFixed_yok(self):
        src = (JS / 'analysis_center.js').read_text(encoding='utf-8')
        govde = re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', src, flags=re.S))
        assert len(re.findall(r'\.toFixed\(', govde)) == 1, 'süre metni kanondan koptu'
        assert 'secTxt(seconds)' in src and 'secTxt(e.seconds)' in src

    def test_merkezin_kendi_metinlerinde_ingilizce_yok(self, tmp_path, yukler):
        """TR kipinde ekrandaki her İngilizce cümle UCUN YANITINDAN gelmeli
        (beyan paragrafları — devir); Merkez/kiracı kendi İngilizcesini
        basmıyor. Ölçüm: yanıt JSON'unda geçmeyen İngilizce cümle = 0."""
        motor, yanit = yukler
        out = _merkez(tmp_path, 'tr', motor, yanit)
        yanit_metni = json.dumps(yanit, ensure_ascii=False)
        yanit_metni = yanit_metni.replace('\\"', '"')
        kendi = []
        for k, v in out['nodes'].items():
            metin = re.sub(r'<[^>]+>', ' ', v['html'] or '') + ' ' + (v['text'] or '')
            metin = metin.replace('&quot;', '"').replace('&gt;', '>').replace('&lt;', '<').replace('&amp;', '&')
            # Cümle VE tablo hücresi (2+ boşluk) sınırlarında böl: künye
            # tabloları anahtar + değer hücrelerini yan yana basar.
            for cumle in re.split(r'(?<=[.!?])\s+|\n|\s{2,}', metin):
                c = cumle.strip()
                if len(c) < 12 or len(EN_KALINTI.findall(c)) < 2:
                    continue
                # Ucun yanıtından mı? Üç sonda: baş, orta, son 50 karakter.
                sondalar = [c[:50], c[max(0, len(c) // 2 - 25):len(c) // 2 + 25], c[-50:]]
                if not any(sd in yanit_metni for sd in sondalar if len(sd) >= 12):
                    kendi.append((k, c[:140]))
        assert not kendi, 'Merkez/kiracının kendi İngilizce metni TR ekranda: %r' % kendi[:8]


# ---------------------------------------------------------------------------
# 5) HUD sayacı
# ---------------------------------------------------------------------------
class TestHudSayaci:
    @pytest.mark.parametrize('lang,beklenen', [('tr', '222,8'), ('en', '222.8')])
    def test_sayac_ayraci(self, lang, beklenen):
        script = FAKE_DOM + r"""
const [i18nPath, hudPath, lang] = ARGS;
require(i18nPath); window.I18N.setLang(lang);
require(hudPath);
const el = makeNode('c'); el.dataset = { target: '222.84', decimals: '1' };
window.HRMAHud.countUp(el);
process.stdout.write(JSON.stringify({ text: el.textContent }));
"""
        out = _node(script, [JS / 'i18n.js', JS / 'hud.js', lang])
        assert out['text'] == beklenen, out
