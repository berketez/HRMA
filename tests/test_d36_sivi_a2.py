# -*- coding: utf-8 -*-
"""ÖH D36 · kulvar onemli2-sivi · a2 — süresiz sıvıda uydurma 10 s / 5 kg yok.

LU-1 (Berke onaylı, ÖNEMLİ) ile sıvı çözücü, yanma süresi verilmediğinde
``burn_time`` ve itici kütlesini YAYIMLAMIYOR. Bu, depoda süre/kütle yokken
sessizce devreye giren yedekleri erişilir kıldı; a2 onları kapattı
(kanıt: docs/scofield/raw/OH/D36/onemli2-sivi/a2/ — once.json / sonra.json /
mutasyon.md; bu dosya kanıt dizinini OKUMAZ, docs'suz dalda da koşar):

- ``safety_analysis.py`` iki ``get('burn_time', 10)``: termal maruziyet,
  yanık dozu mesafesi, önerilen duruş mesafesi ve serbest kalan motorun
  impuls/hız/enerjisi 10 s'den hesaplanıyordu -> süreye bağlı kollar ADIYLA
  geri çekilir, süreden bağımsız kollar aynen kalır.
- ``/analyze_safety`` ``burn_time`` ``default=10`` -> ``None``.
- ``panels/safety_panel.js`` form varsayılanları 10 s ve 5 kg -> boş;
  beyanlı boşluk ekranda '—' + çip ve görünür beyan satırı.
- ``combustion_analysis.calculate_thrust_at_altitudes`` ve
  ``cad_visualization._add_performance_chart`` 10 s yedeği -> süre yoksa
  tablo/iz çizilmez, nedeni adıyla.
- ``liquid.html buildLiquidVizData`` sabit ``burn_time: 10`` ve
  ``motor_viz3d.js extractDims`` ``num(md.burn_time, 10)`` -> süre yoksa
  zaman ekseni yok (``motor_viz_deck.js`` oynatma/kaydırıcı gizli, saat
  yerine beyan).

Her grupta KARŞI iddia da kilitlidir: süre VERİLDİĞİNDE sayılar eski
formülle birebir (itki x süre, impuls / ortalama kütle, max(ışınım, doz,
asgari)), beyan anahtarı yok, iz 0 -> T.

Kaynak okuyan bekçiler dosyayı DOSYADAN okur (inspect.getsource yok); JS
node altında GERÇEKTEN koşturulur (betik stdin ile verilir).
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
PANEL_JS = JS / 'panels' / 'safety_panel.js'
VIZ_JS = JS / 'motor_viz3d.js'
DECK_JS = JS / 'motor_viz_deck.js'
LIQUID = KOK / 'hrma' / 'templates' / 'liquid.html'
I18N_PAGES = JS / 'i18n_pages.js'
ORNEK = KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node yok')

from hrma.analysis.safety_analysis import (  # noqa: E402
    BURN_TIME_NOT_EVALUATED,
    SAFETY_MODEL,
    THERMAL_BURN_TIME_FIELDS,
    UNRESTRAINED_BURN_TIME_FIELDS,
    SafetyAnalyzer,
)

#: Kullanıcı girdisi ÖRNEĞİ (varsayılan değil): süreli karşı iddialar için.
SURE_S = 30.0
#: /analyze_safety bandı içinde (0-300 s) bir sıvı süresi örneği.
SIVI_SURE_S = 250.0

#: Modül düzeneği: termal hükmün VERİLEBİLMESİ için cidar çifti açıkça
#: verilir (ısı zinciri yoksa hüküm zaten geri çekilir ve süre kolu
#: görünmez). Ölçüm girdisi, ürün verisi değildir.
A2_MODUL_MOTORU = {'chamber_pressure': 20.0, 'chamber_temperature': 3400.0,
         'thrust': 25000.0, 'chamber_diameter': 0.12, 'wall_thickness': 0.005,
         'wall_temperature_hot': 900.0, 'wall_temperature_cold': 600.0}
MODUL_KW = dict(propellant_mass=100.0, propellant_type='liquid_biprop',
                material='steel_4130', motor_type='liquid')
#: Uç düzeneği: zorunlu dörtlü + itki + cidar çifti (termal hüküm verilir).
UC_GOVDE = {'chamber_pressure': 20.0, 'propellant_mass': 100.0,
            'chamber_diameter': 0.12, 'wall_thickness': 0.005,
            'thrust': 25000.0, 'motor_type': 'liquid',
            'propellant_type': 'liquid_biprop',
            'wall_temperature_hot': 900.0, 'wall_temperature_cold': 600.0}


def _node(betik: str, env_args=None) -> dict:
    env = dict(os.environ)
    if env_args is not None:
        env['HRMA_ARGS'] = json.dumps([str(a) for a in env_args])
    out = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=180, env=env)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout)


def _blok(src: str, baslangic: str) -> str:
    start = src.index(baslangic)
    derinlik, i = 0, start
    while i < len(src):
        if src[i] == '{':
            derinlik += 1
        elif src[i] == '}':
            derinlik -= 1
            if derinlik == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError(baslangic + ' kapanmıyor')


def _modul(ek: dict) -> dict:
    with contextlib.redirect_stdout(io.StringIO()):
        return SafetyAnalyzer().analyze_comprehensive_safety(
            motor_data=dict(A2_MODUL_MOTORU, **ek), **MODUL_KW)


# ---------------------------------------------------------------------------
# Çözücü ve uç yanıtları — modül başına BİR koşu
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def sivi(client):
    # V301/T-ÇAPA-D: ÖRNEK kulvarı (5fa435893) örnek sıvıya yanma süresi
    # (max_burn_duration = 30 s) ve sayfanın boş alanlarını ('') yazdı. Bu
    # dosyanın senaryosu SÜRESİZ sıvıdır (kullanıcı süreyi girmedi): süre
    # açıkça çıkarılır, boş alanlar sayfa gibi gönderilmez
    # (tests/support/ornek_alanlari.py).
    from tests.support.ornek_alanlari import ornek_alanlari
    alanlar = ornek_alanlari(ORNEK)
    alanlar.pop('max_burn_duration', None)
    bos = client.post('/calculate_liquid', json=dict(alanlar)).get_json()
    sureli = client.post('/calculate_liquid', json=dict(
        alanlar, max_burn_duration=SIVI_SURE_S)).get_json()
    assert 'burn_time' not in bos, 'LU-1 önkoşulu: süresiz yanıt süre taşımaz'
    assert sureli.get('burn_time') == SIVI_SURE_S
    return {'bos': bos, 'sureli': sureli}


# ---------------------------------------------------------------------------
# 1) MODÜL — safety_analysis.analyze_comprehensive_safety
# ---------------------------------------------------------------------------
class TestModulGeriCekme:
    def test_suresiz_kollar_adiyla_geri_cekilir(self):
        s = _modul({})
        assert s['inputs_used']['burn_time_s'] is None
        th = s['thermal_safety']
        assert th['thermal_verdict'] == 'issued', 'düzenek termal hükmü vermeli'
        for ad in THERMAL_BURN_TIME_FIELDS:
            assert th[ad] is None, (ad, th[ad])
            assert ad in th['burn_time_not_evaluated']
        assert th['burn_time_status'] == BURN_TIME_NOT_EVALUATED
        assert th['burn_time_reason']
        um = s['explosive_hazards']['fragment_hazards']['unrestrained_motor']
        for ad in UNRESTRAINED_BURN_TIME_FIELDS:
            assert um[ad] is None, (ad, um[ad])
        assert um['status'] == BURN_TIME_NOT_EVALUATED
        assert um['not_evaluated'] == list(UNRESTRAINED_BURN_TIME_FIELDS)
        beyan = s['burn_time_dependent_not_evaluated']
        assert beyan['status'] == BURN_TIME_NOT_EVALUATED
        assert 'inputs_used.burn_time_s' in beyan['fields']
        assert 'thermal_safety.exposure_duration_s' in beyan['fields']
        assert ('explosive_hazards.fragment_hazards.unrestrained_motor.'
                'total_impulse_ns') in beyan['fields']

    def test_sureden_bagimsiz_kollar_kalir(self):
        s, t = _modul({}), _modul({'burn_time': SURE_S})
        for anahtar in ('radiant_heat_hazard_distance_m',
                        'estimated_wall_temperature_k', 'thermal_stress_mpa'):
            assert s['thermal_safety'][anahtar] == t['thermal_safety'][anahtar]
        um_s = s['explosive_hazards']['fragment_hazards']['unrestrained_motor']
        um_t = t['explosive_hazards']['fragment_hazards']['unrestrained_motor']
        assert um_s['required_restraint_force_n'] == um_t['required_restraint_force_n']
        assert um_s['mean_flight_mass_kg'] == um_t['mean_flight_mass_kg']
        assert (s['structural_safety'] == t['structural_safety'])

    def test_sure_verilince_formul_ayni_beyan_yok(self):
        s = _modul({'burn_time': SURE_S})
        assert 'burn_time_dependent_not_evaluated' not in s
        th = s['thermal_safety']
        assert 'burn_time_not_evaluated' not in th
        assert th['exposure_duration_s'] == SURE_S
        assert th['recommended_minimum_standoff_m'] == max(
            th['radiant_heat_hazard_distance_m'],
            th['second_degree_burn_distance_m'],
            SAFETY_MODEL['min_hazard_distance_m'])
        assert isinstance(th['thermal_protection_required'], bool)
        um = s['explosive_hazards']['fragment_hazards']['unrestrained_motor']
        assert 'status' not in um and 'not_evaluated' not in um
        assert um['total_impulse_ns'] == A2_MODUL_MOTORU['thrust'] * SURE_S
        assert um['burnout_velocity_ms'] == (um['total_impulse_ns']
                                             / um['mean_flight_mass_kg'])
        assert um['kinetic_energy_j'] == (0.5 * um['mean_flight_mass_kg']
                                          * um['burnout_velocity_ms'] ** 2)
        assert s['inputs_used']['burn_time_s'] == SURE_S


# ---------------------------------------------------------------------------
# 2) UÇ — /analyze_safety
# ---------------------------------------------------------------------------
class TestUc:
    def test_sure_gelmezse_uydurulmaz(self, client):
        r = client.post('/analyze_safety', json=dict(UC_GOVDE))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert 'burn_time' not in j['defaults_applied'], (
            'uç süreyi hâlâ kendi varsayılanından dolduruyor')
        sa = j['safety_analysis']
        assert sa['inputs_used']['burn_time_s'] is None
        assert sa['thermal_safety']['exposure_duration_s'] is None
        assert sa['burn_time_dependent_not_evaluated']['status'] == \
            BURN_TIME_NOT_EVALUATED

    def test_sure_gelince_aynen_gecer(self, client):
        r = client.post('/analyze_safety', json=dict(UC_GOVDE, burn_time=SURE_S))
        assert r.status_code == 200
        sa = r.get_json()['safety_analysis']
        assert sa['inputs_used']['burn_time_s'] == SURE_S
        assert sa['thermal_safety']['exposure_duration_s'] == SURE_S
        assert 'burn_time_dependent_not_evaluated' not in sa
        um = sa['explosive_hazards']['fragment_hazards']['unrestrained_motor']
        assert um['total_impulse_ns'] == UC_GOVDE['thrust'] * SURE_S


# ---------------------------------------------------------------------------
# 3) PANEL — safety_panel.js (GERÇEK dosya, node vm)
# ---------------------------------------------------------------------------
PANEL_HARNESS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const [staticDir, girdiYolu] = JSON.parse(process.env.HRMA_ARGS);
const girdi = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this.dataset = {}; this._attrs = {};
    this.innerHTML = '';
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.querySelectorAll = function () { return []; };
const documentStub = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
};
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: setInterval, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('ağ yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
function run(f) { vm.runInContext(fs.readFileSync(f, 'utf8'), sandbox, { filename: f }); }
run(path.join(staticDir, 'units_constants.js'));
run(path.join(staticDir, 'analysis_dock.js'));
run(path.join(staticDir, 'panels', 'safety_panel.js'));
sandbox.window.AnalysisDock._setMotorType(girdi.motorType || 'liquid');
const spec = sandbox.window.AnalysisDock._registry.filter(function (s) {
    return s.id === 'safety'; })[0];
const out = { defaults: {}, suggestions: {}, payload: {}, html: {} };
const sug = girdi.results ? spec.fromResults(girdi.results) : {};
(spec.fields || []).forEach(function (f) {
    const k = f[0];
    out.defaults[k] = f[2];
    out.suggestions[k] = (sug[k] === undefined) ? null : sug[k];
    // Güvertenin gövde kuralı (analysis_dock.js applySuggestions +
    // buildPayload): seçici değeri daima gider; sayı alanına öneri yalnız
    // SONLU SAYIYSA yazılır; kutuda sonlu sayı yoksa anahtar GİTMEZ.
    if (Array.isArray(f[3])) {
        out.payload[k] = (typeof sug[k] === 'string' && sug[k]) ? sug[k] : f[2];
        return;
    }
    let v = f[2];
    if (typeof sug[k] === 'number' && isFinite(sug[k])) {
        v = Number(sug[k].toPrecision(6));
    }
    if (typeof v === 'number' && isFinite(v)) out.payload[k] = v;
});
Object.keys(girdi.render || {}).forEach(function (ad) {
    const root = new El('div');
    sandbox.window.SafetyPanel._render(girdi.render[ad], root);
    out.html[ad] = root.innerHTML;
});
process.stdout.write(JSON.stringify(out));
"""


def _panel(results=None, render=None, motor_type='liquid'):
    with tempfile.TemporaryDirectory() as tmp:
        yol = pathlib.Path(tmp) / 'girdi.json'
        yol.write_text(json.dumps({'results': results, 'render': render or {},
                                   'motorType': motor_type}), encoding='utf-8')
        return _node(PANEL_HARNESS, [JS, yol])


WITHHELD_RE = re.compile(r'data-safety-withheld="([^"]+)"')


@needs_node
class TestPanel:
    def test_sure_ve_kutle_varsayilani_sayi_degil(self):
        """Nöbetçi 10 s / 5 kg kalkmalı: sonlu sayı varsayılan = kutuda sayı."""
        d = _panel()['defaults']
        for alan in ('burn_time', 'propellant_mass'):
            v = d[alan]
            assert not (isinstance(v, (int, float)) and math.isfinite(v)), (
                '%s form varsayılanı hâlâ sayı: %r' % (alan, v))

    def test_suresiz_sivida_govde_sure_kutle_tasimaz_uc_adiyla_reddeder(
            self, sivi, client):
        out = _panel(results=sivi['bos'])
        assert out['suggestions']['burn_time'] is None
        assert out['suggestions']['propellant_mass'] is None
        govde = out['payload']
        assert 'burn_time' not in govde and 'propellant_mass' not in govde, govde
        r = client.post('/analyze_safety', json=govde)
        assert r.status_code == 422
        assert r.get_json()['missing_fields'] == ['propellant_mass']

    def test_sureli_sivida_govde_cozucu_degerini_tasir(self, sivi):
        out = _panel(results=sivi['sureli'])
        govde = out['payload']
        assert govde['burn_time'] == SIVI_SURE_S
        kutle = sivi['sureli']['design_summary']['masses']['propellant_mass_kg']
        assert govde['propellant_mass'] == float('%.6g' % kutle)

    def test_beyanli_bosluk_ekranda_adiyla(self, client):
        yanit = client.post('/analyze_safety', json=dict(UC_GOVDE)).get_json()
        html = _panel(render={'bos': yanit})['html']['bos']
        geri = set(WITHHELD_RE.findall(html))
        beklenen = {'burn_time_s', 'exposure_duration_s',
                    'second_degree_burn_distance_m',
                    'recommended_minimum_standoff_m',
                    'thermal_protection_required',
                    'unrestrained_motor.total_impulse_ns',
                    'unrestrained_motor.burnout_velocity_ms',
                    'unrestrained_motor.kinetic_energy_j'}
        assert beklenen <= geri, beklenen - geri
        assert 'data-safety-burn-time-withheld="1"' in html
        assert 'burn_time_dependent_not_evaluated.fields' in html

    def test_sureli_yanitta_beyan_satiri_yok(self, client):
        yanit = client.post('/analyze_safety',
                            json=dict(UC_GOVDE, burn_time=SURE_S)).get_json()
        html = _panel(render={'t': yanit})['html']['t']
        geri = set(WITHHELD_RE.findall(html))
        assert not ({'burn_time_s', 'exposure_duration_s',
                     'unrestrained_motor.total_impulse_ns'} & geri), geri
        assert 'data-safety-burn-time-withheld' not in html
        i = html.index('data-safety-field="exposure_duration_s"')
        assert '30.00 s' in html[i:i + 400] or '30,00 s' in html[i:i + 400]


# ---------------------------------------------------------------------------
# 4) GRAFİKLER — itki-irtifa tablosu ve CAD performans izi
# ---------------------------------------------------------------------------
class TestGrafikler:
    @pytest.fixture(scope='class')
    def yanma(self):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        ca = CombustionAnalyzer()
        with contextlib.redirect_stdout(io.StringIO()):
            cr = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                       expansion_ratio=4.0)
        paket = {'performance': cr['performance'],
                 'conditions': cr['conditions'],
                 'chamber_pressure': 20.0, 'mdot_total': 2.1}
        return ca, paket

    def test_itki_irtifa_suresizse_cizilmez(self, yanma):
        ca, paket = yanma
        with contextlib.redirect_stdout(io.StringIO()):
            t = ca.calculate_thrust_at_altitudes(21000.0, dict(paket),
                                                 [0, 5000, 10000])
        assert t['status'] == 'NOT_EVALUATED' and t['reason']
        assert t['thrust_altitude_data'] == []
        assert t['base_thrust_sea_level'] is None

    def test_itki_irtifa_sureliyse_aynen(self, yanma):
        ca, paket = yanma
        with contextlib.redirect_stdout(io.StringIO()):
            t = ca.calculate_thrust_at_altitudes(
                21000.0, dict(paket, burn_time=7.0), [0, 5000, 10000])
        assert 'status' not in t
        assert t['base_thrust_sea_level'] == 21000.0 / 7.0
        assert len(t['thrust_altitude_data']) == 3

    @staticmethod
    def _perf(geo):
        from hrma.export.cad_visualization import MotorCADDesigner
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            cad = MotorCADDesigner().generate_3d_motor_assembly(dict(geo))
        fig = json.loads(cad['plotly_visualization'])
        izler = [t for t in fig.get('data', [])
                 if t.get('xaxis') == 'x2' and t.get('yaxis') == 'y2']
        notlar = [a.get('text') for a in fig['layout'].get('annotations', [])]
        return izler, notlar

    def test_cad_performans_suresizse_iz_yok_gerekce_var(self, sivi):
        from hrma.export.cad_visualization import (
            PERFORMANCE_CHART_NOT_DRAWN_REASON)
        from hrma.export.motor_geometry import liquid_results_to_motor_geometry
        izler, notlar = self._perf(liquid_results_to_motor_geometry(sivi['bos']))
        assert izler == [], izler
        assert PERFORMANCE_CHART_NOT_DRAWN_REASON in notlar

    def test_cad_performans_sureliyse_0_T(self, sivi):
        from hrma.export.motor_geometry import liquid_results_to_motor_geometry
        izler, _ = self._perf(liquid_results_to_motor_geometry(sivi['sureli']))
        assert len(izler) == 1
        assert izler[0]['x'] == [0.0, SIVI_SURE_S]
        assert izler[0]['y'][0] == izler[0]['y'][1] == sivi['sureli']['thrust']


# ---------------------------------------------------------------------------
# 5) ZAMAN EKSENİ — adaptör, sahne, güverte (node)
# ---------------------------------------------------------------------------
def _fonksiyon(yol: pathlib.Path, ad: str) -> str:
    return _blok(yol.read_text(encoding='utf-8'), 'function %s(' % ad)


LIQ_BARE = {'chamber_diameter': 120.0, 'chamber_length': 350.0,
            'throat_diameter': 0.04, 'exit_diameter': 0.12,
            'thrust': 25000.0, 'isp_vacuum': 330.0, 'chamber_pressure': 70.0}


@needs_node
class TestZamanEkseni:
    def test_sivi_adaptoru_sure_uydurmaz(self):
        betik = (_fonksiyon(LIQUID, 'buildLiquidVizData') + '\n'
                 + 'process.stdout.write(JSON.stringify({bos: '
                 + 'buildLiquidVizData(%s).burn_time, sureli: '
                 'buildLiquidVizData(%s).burn_time}));'
                 % (json.dumps(LIQ_BARE),
                    json.dumps(dict(LIQ_BARE, burn_time=400.0))))
        out = _node(betik)
        assert out['bos'] is None, 'adaptör süresiz sonuca süre uydurdu'
        assert out['sureli'] == 400.0

    def test_extractDims_suresi_yoksa_null(self):
        src = VIZ_JS.read_text(encoding='utf-8')
        govde = _blok(src, 'function extractDims(')
        m = re.search(r'\n\s*burnTime:\s*([\s\S]*?),\n\s*thrust:', govde)
        assert m, 'extractDims içinde burnTime alanı bulunamadı'
        betik = (_blok(src, 'function num(') + '\n'
                 + 'function bt(md) { return (%s); }\n' % m.group(1)
                 + 'process.stdout.write(JSON.stringify(['
                 'bt({}), bt({burn_time: null}), bt({burn_time: 0}), '
                 'bt({burn_time: 400}), bt({burn_time: 10}), '
                 'bt({burn_time: 0.05})]));')
        out = _node(betik)
        assert out[:3] == [None, None, None], out
        # Süre verildiğinde eski ifadeyle aynı: Math.max(0.1, t)
        assert out[3:] == [400, 10, 0.1], out

    def test_sahne_suresizse_oynatmaz(self):
        src = VIZ_JS.read_text(encoding='utf-8')
        betik = ('var MotorScene = function () {};\n'
                 + _blok(src, 'function clamp(') + '\n'
                 + _blok(src, 'MotorScene.prototype.play = function') + ';\n'
                 + _blok(src, 'MotorScene.prototype.setTime = function') + ';\n'
                 + r"""
var s = new MotorScene();
s.dims = { burnTime: null }; s.state = { time: 0, playing: false };
s.play(); var p0 = s.state.playing; s.setTime(5); var t0 = s.state.time;
s.dims.burnTime = 3.2; s.play(); var p1 = s.state.playing;
s.setTime(5); var t1 = s.state.time;
process.stdout.write(JSON.stringify([p0, t0, p1, t1]));
""")
        assert _node(betik) == [False, 0, True, 3.2]


DECK_HARNESS = r"""
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
const [i18nPath, chartsPath, deckPath, vizPath, bt] = JSON.parse(process.env.HRMA_ARGS);
require(i18nPath); require(chartsPath); window.I18N.setLang('tr');
const src = require('fs').readFileSync(vizPath, 'utf8');
function bildirim(ad) { return src.match(new RegExp('var ' + ad + ' = [^;]+;'))[0]; }
eval(bildirim('CFD_METRICS')); eval(bildirim('CFD_COLORSCALES'));
const burnTime = (bt === 'null') ? null : Number(bt);
let hooks = null;
const viz = {
    state: { cutaway: true, labels: true, plume: true, exploded: false,
             autoRotate: false, portShape: 'circular', playing: false, heatMap: false },
    dims: { burnTime: burnTime },
    getHeatInfo() { return null; }, setHeatMap() { return false; },
    getCfdField() { return null; }, getCfdReject() { return null; },
    setCfdMetric() { return { ok: false }; }, clearCfdField() { return true; },
    setPortShape() {}, cyclePortShape() {}, cycleCameraPreset() { return 'iso'; },
    setQuality() {}, cycleSpeed() { return 1; }, snapshot() { return null; },
    setCutaway() {}, setLabels() {}, setPlume() {}, setExploded() {},
    setAutoRotate() {}, resetCamera() {}, play() {}, pause() {}, setTime() {}, update() {},
};
global.MotorViz3D = { isSupported() { return true; },
    mount(id, md, h) { hooks = h; return viz; }, update() {},
    CFD_METRICS: CFD_METRICS, CFD_COLORSCALES: CFD_COLORSCALES };
require(deckPath);
const md = { chamber_diameter: 0.12, chamber_length: 0.35, throat_diameter: 0.04,
             exit_diameter: 0.12, chamber_pressure: 70, thrust: 25000, isp: 330,
             viz_motor_type: 'liquid' };
if (burnTime !== null) md.burn_time = burnTime;
const deck = window.MotorVizDeck.create('deck_host', md, { motorType: 'liquid' });
const p = deck.prefix;
nowMs += 1000;
hooks.onTick({ playing: false, burning: false, time: 0, burnTime: burnTime,
               portDiameter: 0, webRemaining: 1, of: null, isp: 330,
               thrust: 25000, pc: null });
function d(k) { const e = nodes[p + k]; return { t: e.innerHTML || e.textContent,
    display: e.style.display, noTime: e.getAttribute('data-no-time') }; }
process.stdout.write(JSON.stringify({ clock: d('_clock'), play: d('_play'),
    slider: d('_slider'), status: d('_status') }));
"""


def _guverte(bt):
    return _node(DECK_HARNESS, [JS / 'i18n.js', JS / 'i18n_charts.js',
                                DECK_JS, VIZ_JS, bt])


@needs_node
class TestGuverteSeridi:
    def test_suresizse_zaman_ekseni_cizilmez(self):
        out = _guverte('null')
        assert out['play']['display'] == 'none', out
        assert out['slider']['display'] == 'none', out
        assert out['clock']['noTime'] == '1'
        assert out['clock']['t'] == 'YANMA SÜRESİ VERİLMEDİ: ZAMAN EKSENİ ÇİZİLMEDİ'
        assert ' s / ' not in out['clock']['t']
        assert out['status']['t'] == 'BEKLEMEDE', 'süresiz sahne "yanma bitti" demez'

    def test_sureliyse_serit_eskisi_gibi(self):
        out = _guverte('3.2')
        assert out['play']['display'] != 'none'
        assert out['slider']['display'] != 'none'
        assert out['clock']['t'] == 't = <b>0,00</b> s / 3,20 s', out['clock']


# ---------------------------------------------------------------------------
# 6) i18n — yetim anahtarlar
# ---------------------------------------------------------------------------
def test_yetim_sivi_anahtarlari_silindi():
    metin = I18N_PAGES.read_text(encoding='utf-8')
    for anahtar in ('liq.msg.export_only_note',
                    'liq.msg.export_only_openrocket_eng_burn_time',
                    'liq.msg.set_a_positive_maximum_burn_duration'):
        assert "'%s'" % anahtar not in metin, anahtar


# ---------------------------------------------------------------------------
# a2 bağımsız denetçisinin şart 2 düğümleri (24 Eyl, ana model): denetçinin
# D2 ve D9 ters mutasyonları 20/20 yeşil kalıyordu.
# ---------------------------------------------------------------------------
class TestTermalEksenSkoru:
    """``_score_thermal_risk`` süresiz dalı (safety_analysis.py risks_not_evaluated).

    ``A2_MODUL_MOTORU`` (900/600 K) termal ekseni termal gerilme SF < 1
    kolunda 5,0'da bitirdiği için süre dalına HİÇ ulaşmıyordu. Ilık cidar
    çifti (420/400 K; denetçinin ölçüm düzeneği) gerilme kolunu geçip süre
    dalına iner. Ölçüm girdisi, ürün verisi değildir.
    """
    CIDAR_ILIK = {'wall_temperature_hot': 420.0, 'wall_temperature_cold': 400.0}

    def test_suresizde_termal_skorlanmaz_adiyla(self):
        ra = _modul(dict(self.CIDAR_ILIK))['risk_assessment']
        assert ra['individual_risks']['thermal'] is None
        assert 'thermal' in ra['risks_not_evaluated']

    def test_sureliyse_termal_skorlanir(self):
        ra = _modul(dict(self.CIDAR_ILIK, burn_time=SURE_S))['risk_assessment']
        assert ra['individual_risks']['thermal'] == 2.0
        assert 'thermal' not in ra['risks_not_evaluated']


@needs_node
class TestTickItkisi:
    """``_tick``'in yayımladığı itki: süre yokken tasarım itkisi (0 değil)."""

    def test_suresiz_sahne_tasarim_itkisini_yayimlar(self):
        govde = _blok(VIZ_JS.read_text(encoding='utf-8'),
                      'MotorScene.prototype._tick = function')
        m = re.search(r'\n\s*thrust:\s*([\s\S]*?),\n\s*pc:', govde)
        assert m, '_tick içinde thrust alanı bulunamadı'
        betik = ('function f(thrustNow, zamanVar, st, d) { return (%s); }\n'
                 % m.group(1)
                 + 'var D = {burnTime: null, thrust: 25000};\n'
                 + 'var DT = {burnTime: 10, thrust: 25000};\n'
                 + 'process.stdout.write(JSON.stringify(['
                 'f(null, false, {time: 0}, D), f(null, true, {time: 5}, DT), '
                 'f(null, true, {time: 12}, DT), f(18000, true, {time: 5}, DT), '
                 'f(18000, true, {time: 12}, DT)]));')
        # süresiz → tasarım itkisi; süreli → yanma içinde tasarım, sonra 0;
        # transient eğri varsa onun anlık değeri (yanma sonrası 0)
        assert _node(betik) == [25000, 25000, 0, 18000, 0]
