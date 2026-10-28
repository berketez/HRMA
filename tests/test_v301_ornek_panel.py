"""V301/ÖRNEK-PANEL bekçisi — örnek motorlar analiz panellerinde ana hesapla çelişmez.

Berke (yayın kapısı, 27 Eki 2026): "üç örnek motor × her panel × her dışa
aktarım: kritik yok, ret yok, aynı büyüklük her panelde aynı sayı."

ÖLÇÜLEN KUSURLAR (docs/scofield/raw/OH/V301/ornek-panel/RAPOR.md, olcum/):
  * katı örnek: ısıl panel 2 mm çelik kasayı BOĞAZ istasyonunda, yalıtımsız,
    kararlı hâlde çözüp 1683,7 K / wall_pinned_adiabatic + temp_exceeds_
    allowable KRİTİK veriyordu; motor aynı kasayı 3 mm yalıtım + 2 mm astar
    arkasında yanma boyunca çözüyor: 313,55 K (sınır 811 K, "Excellent");
  * hibrit örnek: panel motorun ısı modülüne verdiği c*, γ, M, boğaz ve
    ışınım kesirlerini göndermiyordu (c* 1656,9 ⟷ motor 1420,9 m/s, boğaz
    akısı −%23); çıplak cidar kritiklerini motorun bölge hükmü (V301/
    H-termal) yerine KRİTİK basıyordu (3304 K "lüle sayısı" DEĞİLDİ: yanlış
    c*'lı çıplak ss_304 cidarın T_aw'a yapışmış dengesiydi);
  * sıvı örnek: akış paneli LOX/RP-1 için hibrit HTPB/N2O gönderiyordu;
    akış paneli hibrit/sıvıda ortam basıncını tohumlamıyordu (422).

Bu dosya üç katmanı sınar:
  (1) panel JS'i (gerçek analysis_dock.js + panel dosyası, node vm) örnek
      motorun yanıtından ne öneriyor;
  (2) ``/analyze_thermal_safety`` korunan cidar yolları ve fail-closed;
  (3) yeni/var olan isteğe bağlı alanların kapısı (500 yok, adlı 422).
"""

import json
import math
import pathlib
import shutil
import subprocess

import pytest

from tests.support.form_defaults import form_yuku
from tests.test_example_projects import ENDPOINTS, HEADERS, load_example_doc

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = ROOT / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Güvertenin öneri yuvarlaması (analysis_dock.js applySuggestions:
#: toPrecision(6)) — tohumlanan sayı ile motor sayısı arasındaki tek fark.
ONERI_BAGIL = 5e-6


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


_ANA = {}


def ana(client, mt):
    """Örnek .hrma + şablon varsayılanları = sayfanın Hesapla yükü."""
    if mt not in _ANA:
        yuk = form_yuku(mt, load_example_doc(mt)['inputs']['fields'])
        r = client.post(ENDPOINTS[mt], json=yuk, headers=HEADERS)
        assert r.status_code == 200, (mt, r.get_data()[:300])
        _ANA[mt] = r.get_json()
    return _ANA[mt]


def post(client, yol, govde):
    r = client.post(yol, json=govde, headers=HEADERS)
    return r.status_code, r.get_json()


def kritikler(o, yol=''):
    out = []
    if isinstance(o, dict):
        sev = o.get('severity')
        if isinstance(sev, str) and sev.lower() == 'critical':
            out.append((o.get('code'), yol))
        for k, v in o.items():
            out.extend(kritikler(v, yol + '.' + str(k)))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out.extend(kritikler(v, '%s[%d]' % (yol, i)))
    return out


# ---------------------------------------------------------------------------
# (1) Panel JS'i node vm'de: gerçek güverte + gerçek panel dosyası
# ---------------------------------------------------------------------------
PANEL_JS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const inp = JSON.parse(fs.readFileSync(0, 'utf8'));
function El(t) { this.tagName = String(t || 'div').toUpperCase(); this.children = [];
  this.style = {}; this.dataset = {}; this._a = {}; this.value = ''; this.options = [];
  this.classList = {contains() { return false; }, add() {}, remove() {}, toggle() {}}; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = El.prototype.appendChild;
El.prototype.remove = function () {}; El.prototype.removeChild = function () {};
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); };
El.prototype.getAttribute = function (k) { return k in this._a ? this._a[k] : null; };
El.prototype.hasAttribute = function (k) { return k in this._a; };
El.prototype.removeAttribute = function (k) { delete this._a[k]; };
El.prototype.addEventListener = function () {}; El.prototype.removeEventListener = function () {};
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.closest = function () { return null; };
El.prototype.insertAdjacentHTML = function () {};
El.prototype.contains = function () { return false; };
El.prototype.dispatchEvent = function () { return true; };
El.prototype.getBoundingClientRect = function () { return {left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0}; };
const ids = {};
const doc = {head: new El('head'), body: new El('body'), documentElement: new El('html'),
  readyState: 'complete', createElement(t) { return new El(t); }, createTextNode() { return new El('#t'); },
  createDocumentFragment() { return new El('f'); }, querySelector() { return null; },
  querySelectorAll() { return []; }, getElementById(i) { return ids[i] || (ids[i] = new El('div')); },
  addEventListener() {}, removeEventListener() {}};
const sb = {console: {log() {}, warn() {}, error() {}, info() {}, debug() {}},
  setTimeout() { return 0; }, clearTimeout() {}, setInterval() { return 0; }, clearInterval() {},
  requestAnimationFrame() { return 0; }, fetch() { return new Promise(function () {}); },
  JSON, Math, Number, Array, Object, String, Boolean, Promise, Error, TypeError, RangeError, RegExp,
  Date, Map, Set, WeakMap, Symbol, Intl, isFinite, isNaN, parseFloat, parseInt,
  encodeURIComponent, decodeURIComponent, document: doc,
  navigator: {language: 'en', userAgent: 'node'},
  location: {search: '', pathname: '/', href: 'http://127.0.0.1/', hash: ''},
  localStorage: {getItem() { return null; }, setItem() {}, removeItem() {}},
  sessionStorage: {getItem() { return null; }, setItem() {}, removeItem() {}},
  addEventListener() {}, removeEventListener() {},
  matchMedia() { return {matches: false, addEventListener() {}, addListener() {}}; },
  getComputedStyle() { return {getPropertyValue() { return ''; }}; }, performance: {now() { return 0; }},
  CustomEvent: function () {}, Event: function () {},
  MutationObserver: function () { this.observe = function () {}; this.disconnect = function () {}; },
  ResizeObserver: function () { this.observe = function () {}; this.disconnect = function () {}; },
  IntersectionObserver: function () { this.observe = function () {}; this.disconnect = function () {}; },
  Node: {TEXT_NODE: 3, ELEMENT_NODE: 1}, NodeFilter: {SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2}};
sb.window = sb; sb.globalThis = sb; sb.self = sb;
vm.createContext(sb);
const specs = [];
for (const f of inp.files) {
  vm.runInContext(fs.readFileSync(inp.dir + '/' + f, 'utf8'), sb, {filename: f});
  const AD = sb.window.AnalysisDock;
  if (AD && !AD.__b) { const o = AD.register; AD.register = function (s) { specs.push(s); return o.call(AD, s); }; AD.__b = true; }
}
sb.window.AnalysisDock.init({anchorId: 'x', motorType: inp.motorType, resultsProvider() { return inp.results; }});
const out = {};
for (const s of specs) {
  if (inp.ids.indexOf(s.id) === -1) continue;
  const sug = s.fromResults(inp.results) || {};
  // Güverte buildPayload aynası: öneri (sayı → toPrecision(6)) > alan varsayılanı;
  // boş isteğe bağlı alan gövdeye girmez; zorunlu boş alan 'missing'.
  const req = {}; (s.required || []).forEach(function (k) { req[k] = true; });
  const payload = {}, missing = [], fields = [];
  (s.fields || []).forEach(function (f) {
    const k = f[0], def = f[2], sel = Array.isArray(f[3]);
    fields.push(k);
    let v = sug[k];
    if (sel) {
      const opts = f[3].map(function (o) { return String(o[0]); });
      const val = (v != null && opts.indexOf(String(v)) !== -1) ? String(v)
                : (opts.indexOf(String(def)) !== -1 ? String(def) : opts[0]);
      if (val === '' && (req[k] || (typeof def === 'number'))) { missing.push(k); return; }
      if (val !== '') payload[k] = val;
      return;
    }
    if (typeof v === 'number' && Number.isFinite(v)) { payload[k] = Number(v.toPrecision(6)); return; }
    if (typeof def === 'number' && Number.isFinite(def)) { payload[k] = def; return; }
    if (req[k]) missing.push(k);
  });
  out[s.id] = {fields: fields, suggested: sug, payload: payload, missing: missing,
               required: s.required || []};
}
process.stdout.write(JSON.stringify(out));
"""


def panel_kur(mt, sonuc, ids=('thermal', 'flow')):
    assert NODE, 'node kurulu değil'
    girdi = json.dumps({'dir': str(STATIC_JS), 'motorType': mt, 'results': sonuc,
                        'ids': list(ids),
                        'files': ['analysis_dock.js', 'panels/thermal_panel.js',
                                  'panels/flow_panel.js']})
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (argv değil; Linux MAX_ARG_STRLEN —
    # tests/test_node_cagri_sozlesmesi.py); girdi betiğe JSON dize literali
    # olarak gömülür.
    oku = "JSON.parse(fs.readFileSync(0, 'utf8'))"
    assert PANEL_JS.count(oku) == 1
    betik = PANEL_JS.replace(oku, 'JSON.parse(%s)' % json.dumps(girdi))
    p = subprocess.run([NODE], input=betik, capture_output=True,
                       text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def yakin(a, b, rel=ONERI_BAGIL):
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=0.0)


@needs_node
def test_kati_isil_panel_motorun_cozdugu_kasa_sicakligini_tasir(client):
    s = ana(client, 'solid')
    p = panel_kur('solid', s)['thermal']
    kasa = s['thermal_analysis']['heat_transfer']['case_temperature_k']
    assert yakin(p['payload']['wall_temperature_hot'], kasa)
    assert yakin(p['payload']['wall_temperature_cold'], kasa)
    assert p['payload']['wall_protection'] == 'none'
    bg = s['heat_transfer_analysis']['bartz_gas_properties']
    assert yakin(p['payload']['gamma'], bg['gamma'])
    assert yakin(p['payload']['molecular_weight'], bg['molecular_weight'])
    assert yakin(p['payload']['c_star'], s['c_star'])
    assert not p['missing']


@needs_node
def test_hibrit_isil_panel_motorun_isi_girdileriyle_ve_astar_secimiyle(client):
    m = ana(client, 'hybrid')['motor']
    p = panel_kur('hybrid', {'motor': m})['thermal']
    y = p['payload']
    assert y['wall_protection'] == 'ablative_liner'
    assert 'wall_temperature_hot' not in y, 'beyanlı kasa sıcaklığı tohumlanmamalı'
    for k in ('c_star', 'gamma', 'molecular_weight', 'throat_diameter'):
        assert yakin(y[k], m[k]), k
    gsa = m['heat_transfer_analysis']['gas_side_analysis']
    assert yakin(y['x_H2O'], gsa['radiation_x_H2O'])
    assert yakin(y['x_CO2'], gsa['radiation_x_CO2'])


@needs_node
def test_sivi_isil_panel_cozulmus_cidar_cifti_ve_suresiz_adli_durus(client):
    s = ana(client, 'liquid')
    p = panel_kur('liquid', s)['thermal']
    cs = s['cooling_system']
    assert yakin(p['payload']['wall_temperature_hot'], cs['wall_temperature_solved_K'])
    assert yakin(p['payload']['wall_temperature_cold'], cs['wall_temperature_solved_cold_K'])
    assert p['payload']['cooling_type'] == s['cooling_type'] == 'regenerative'
    if 'burn_time' not in s:
        assert p['missing'] == ['burn_time'], p['missing']
    assert 'burn_time' in p['required']


@needs_node
@pytest.mark.parametrize('mt', ['solid', 'liquid', 'hybrid'])
def test_akis_paneli_ortam_basinci_motorun_lule_tasarim_basinci(client, mt):
    s = ana(client, mt)
    sonuc = {'motor': s['motor']} if mt == 'hybrid' else s
    m = s['motor'] if mt == 'hybrid' else s
    p = panel_kur(mt, sonuc)['flow']
    pa = m['nozzle_design']['performance']['ambient_pressure'] * 1e5
    assert yakin(p['payload']['ambient_pressure'], pa)
    kinetik = {'of_ratio', 'fuel_type', 'oxidizer_type', 'kinetic_fidelity'}
    if mt == 'hybrid':
        assert kinetik <= set(p['fields'])
        assert p['payload']['fuel_type'] == m['fuel_type']
        assert p['payload']['oxidizer_type'].lower() == (
            m['combustion_analysis']['inputs']['oxidizer_type'].lower())
        assert yakin(p['payload']['of_ratio'], m['of_ratio'])
    else:
        # Kinetik zincir yalnız hibrit yakıtlarını tanır: sıvı/katı gövdesinde
        # hibrit kimyası GİTMEZ.
        assert not (kinetik & set(p['fields'])), p['fields']
        assert not (kinetik & set(p['payload'])), p['payload']
    assert not p['missing']


@needs_node
def test_hibrit_akis_paneli_motor_iticisi_yoksa_adli_durus():
    """Motor sonucu itici vermiyorsa sessiz HTPB/N2O gitmez: alan adıyla durur."""
    p = panel_kur('hybrid', {'motor': {'chamber_pressure': 30}})['flow']
    assert set(p['missing']) >= {'fuel_type', 'oxidizer_type', 'of_ratio'}, p['missing']
    assert 'fuel_type' not in p['payload'] and 'oxidizer_type' not in p['payload']


# ---------------------------------------------------------------------------
# (2) /analyze_thermal_safety — korunan cidar yolları
# ---------------------------------------------------------------------------
def _isil(client, govde):
    durum, j = post(client, '/analyze_thermal_safety', govde)
    return durum, j


@needs_node
@pytest.mark.parametrize('mt', ['solid', 'hybrid'])
def test_ornek_isil_panel_200_kritik_yok(client, mt):
    s = ana(client, mt)
    sonuc = {'motor': s['motor']} if mt == 'hybrid' else s
    p = panel_kur(mt, sonuc)['thermal']
    durum, j = _isil(client, p['payload'])
    assert durum == 200, j
    assert not kritikler(j), kritikler(j)


@needs_node
def test_kati_hukum_verilen_kasada_ciplak_cidar_sayisi_kalir(client):
    s = ana(client, 'solid')
    y = panel_kur('solid', s)['thermal']['payload']
    durum, j = _isil(client, y)
    assert durum == 200
    ta = j['thermal_analysis']
    sw = ta['supplied_wall_check']
    assert sw['status'] == 'applied' and sw['governs'] is True
    # Hüküm verilen kasada: aynı eşik merdiveni (allowable / T_kasa).
    allow = ta['safety_analysis']['threshold_ladder']['allowable_K']
    assert ta['safety_analysis']['temperature_safety_factor'] == pytest.approx(
        allow / y['wall_temperature_hot'], rel=1e-12)
    assert ta['safety_analysis']['risk_level'] == 'LOW'
    # Çıplak cidar SAYISI aynı istek korumasız gönderildiğinde de aynı.
    ciplak = {k: v for k, v in y.items()
              if k not in ('wall_temperature_hot', 'wall_temperature_cold')}
    d2, j2 = _isil(client, ciplak)
    assert d2 == 200
    assert ta['wall_analysis'] == j2['thermal_analysis']['wall_analysis']
    assert sw['bare_wall_temperature_K'] == j2['thermal_analysis']['wall_analysis']['max_temperature']
    # Korumasız istekte kritikler AYNEN durur (fail-closed; yanıtta blok yok).
    assert kritikler(j2)
    assert 'supplied_wall_check' not in j2['thermal_analysis']
    assert 'chamber_liner_check' not in j2['thermal_analysis']
    # Aşılan kayıtlar silinmez: info + superseded_by + ASIL önem
    # (bare_wall_severity). Uyarı düzeyindeki çıplak cidar kaydı da aşılır —
    # ölçülen çelişki: "denge cidar 1690 K ... dayanım marjı kayboldu"
    # verilen kasa hükmünün (313,6 K, LOW) yanında güncel uyarı gibi duruyordu.
    gsa_w = ta['gas_side_analysis']['warnings']
    assert gsa_w and all(w.get('superseded_by') == 'supplied_wall_check'
                         and w['severity'] == 'info' for w in gsa_w), gsa_w
    assert any(w['bare_wall_severity'] == 'critical' for w in gsa_w)
    assert any(w['code'] == 'warn.thermal.wall_exceeds_allowable'
               and w['bare_wall_severity'] == 'warning' for w in gsa_w), gsa_w
    assert all(w.get('superseded_by')
               for w in ta['bare_wall_safety_analysis']['warnings'])
    # Hükmü veren blokta (verilen kasa, 313,6 K) aşılmış kayıt yok.
    assert not any(w.get('superseded_by') for w in ta['safety_analysis']['warnings'])


@needs_node
def test_hibrit_astar_motorun_kendi_astariyla_ayni(client):
    m = ana(client, 'hybrid')['motor']
    y = panel_kur('hybrid', {'motor': m})['thermal']['payload']
    durum, j = _isil(client, y)
    assert durum == 200
    cl = j['thermal_analysis']['chamber_liner_check']
    assert cl['verdict'] == 'LINER_REQUIRED' and cl['severity'] == 'warning'
    motor_astar = m['thermal_protection']['chamber_liner']['thickness']
    # Tek fark güvertenin 6 anlamlı basamaklı önerisi: 1e-4 bağıl içinde.
    assert cl['required_thickness_mm'] == pytest.approx(motor_astar, rel=1e-4)
    # Motorun bölge modeliyle aynı çıplak cidar kodları.
    assert sorted(cl['bare_wall_codes']) == sorted(
        m['chamber_wall_zones']['bare_wall_check']['codes'])
    sa = j['thermal_analysis']['safety_analysis']
    assert sa['risk_level'] == 'MEDIUM' and sa['bare_wall_risk_level'] == 'HIGH'
    # Güncel tek kayıt astar gereksinimidir; çıplak cidarın bütün kayıtları
    # (güvenlik + gaz tarafı) aşılmıştır.
    guncel = [w for w in sa['warnings'] if not w.get('superseded_by')]
    assert [w['code'] for w in guncel] == ['warn.thermal.chamber_liner_required'], guncel
    assert guncel[0]['severity'] == 'warning'
    assert all(w.get('superseded_by') == 'chamber_liner_check'
               for w in j['thermal_analysis']['gas_side_analysis']['warnings'])


def _hibrit_govde():
    return {'chamber_pressure': 30, 'chamber_temperature': 3333.07,
            'chamber_diameter': 0.0848023, 'chamber_length': 1.04141,
            'burn_time': 10, 'mdot_total': 1.4563, 'wall_thickness': 0.005,
            'material': 'ss_304', 'cooling_type': 'natural',
            'throat_diameter': 0.029936, 'c_star': 1420.93, 'gamma': 1.15184,
            'molecular_weight': 26.6322}


def test_astar_boyutlanamazsa_kritik_aynen_kalir(client):
    """Fail-closed: Q* modelinin geçerlilik tavanı aşılırsa hüküm verilmez."""
    g = _hibrit_govde()
    g.update(chamber_pressure=150, wall_protection='ablative_liner')
    durum, j = _isil(client, g)
    assert durum == 200, j
    cl = j['thermal_analysis']['chamber_liner_check']
    assert cl['verdict'] == 'NOT_SIZED' and cl['governs'] is False, cl
    assert kritikler(j), 'boyutlanamayan astarda çıplak cidar kritiği kalmalı'


def test_astar_secimi_ciplak_cidar_kritiksizse_hukmu_degistirmez(client):
    """Çıplak cidarda kritik kayıt yoksa astar hükmü verilmez, gövde aynıdır.

    Ölçülen durum (2026-10-27): grafit, rejeneratif, katı gazı -> çıplak
    cidar 988,9 K, kritik kayıt yok -> BARE_WALL_OK.
    """
    g = dict(_KATI, material='graphite', cooling_type='regenerative')
    d0, j0 = _isil(client, g)
    d1, j1 = _isil(client, dict(g, wall_protection='ablative_liner'))
    assert d0 == d1 == 200
    assert not kritikler(j0)
    ta = j1['thermal_analysis']
    assert ta['chamber_liner_check']['verdict'] == 'BARE_WALL_OK'
    assert ta['safety_analysis'] == j0['thermal_analysis']['safety_analysis']
    assert ta['gas_side_analysis'] == j0['thermal_analysis']['gas_side_analysis']


def test_katida_astar_secimi_q_yildiz_disi_kalirsa_kritik_kalir(client):
    """Katı gazında T_aw ablasyon yüzey sıcaklığının altında: Q* modeli astar
    boyutlandıramaz (NOT_SIZED) ve çıplak cidar kritikleri AYNEN kalır."""
    durum, j = _isil(client, dict(_KATI, wall_protection='ablative_liner'))
    assert durum == 200
    assert j['thermal_analysis']['chamber_liner_check']['verdict'] == 'NOT_SIZED'
    assert kritikler(j)


# ---------------------------------------------------------------------------
# (3) Kapılar — 500 yok, adlı 422
# ---------------------------------------------------------------------------
_KATI = {'chamber_pressure': 40, 'chamber_temperature': 1695.97,
         'chamber_diameter': 0.085, 'chamber_length': 0.464, 'burn_time': 2.277,
         'mdot_total': 1.0569, 'wall_thickness': 0.002, 'material': 'steel',
         'cooling_type': 'natural'}


@pytest.mark.parametrize('ek,alan,neden', [
    ({'wall_temperature_hot': 313.0}, 'wall_temperature_cold', 'pair_incomplete'),
    ({'wall_temperature_cold': 313.0}, 'wall_temperature_hot', 'pair_incomplete'),
    ({'wall_temperature_hot': 313.0, 'wall_temperature_cold': 400.0},
     'wall_temperature_cold', 'above_hot_wall_temperature'),
    ({'wall_temperature_hot': 5000.0, 'wall_temperature_cold': 300.0},
     'wall_temperature_hot', 'above_chamber_temperature'),
    ({'wall_temperature_hot': 'NaN', 'wall_temperature_cold': 300.0},
     'wall_temperature_hot', None),
    ({'wall_temperature_hot': True, 'wall_temperature_cold': 300.0},
     'wall_temperature_hot', None),
    ({'wall_protection': 'peynir'}, 'wall_protection', 'unsupported_value'),
    ({'wall_protection': ['ablative_liner']}, 'wall_protection', 'unsupported_value'),
    ({'gamma': 0.5}, 'gamma', 'out_of_range'),
    ({'gamma': 1.05}, 'gamma', 'out_of_range'),
    ({'gamma': 5.0}, 'gamma', 'out_of_range'),
    ({'molecular_weight': 'abc'}, 'molecular_weight', None),
    ({'c_star': -3.0}, 'c_star', 'must_be_positive'),
    ({'throat_diameter': 1e9}, 'throat_diameter', 'out_of_range'),
    ({'x_H2O': 1.5, 'x_CO2': 0.1}, 'x_H2O', 'out_of_range'),
    ({'x_H2O': -0.1}, 'x_H2O', 'must_be_non_negative'),
    ({'x_H2O': 0.7, 'x_CO2': 0.5}, 'x_CO2', 'mole_fractions_exceed_one'),
])
def test_isil_uc_kapilari_adli_422(client, ek, alan, neden):
    g = dict(_KATI)
    g.update(ek)
    durum, j = _isil(client, g)
    assert durum == 422, (ek, durum, j)
    assert j['error'] == 'invalid_thermal_input', j
    alanlar = {(f.get('field'), f.get('reason')) for f in j['invalid_fields']}
    assert any(a == alan and (neden is None or n == neden) for a, n in alanlar), alanlar


def test_yeni_alanlar_yoksa_yanit_degismez(client):
    """Korunan cidar alanları gönderilmeyen istekte yeni blok yok, hüküm eski."""
    durum, j = _isil(client, dict(_KATI))
    assert durum == 200
    ta = j['thermal_analysis']
    assert 'supplied_wall_check' not in ta and 'chamber_liner_check' not in ta
    assert 'bare_wall_safety_analysis' not in ta
    assert 'bare_wall_risk_level' not in ta['safety_analysis']
    assert any(c == 'warn.thermal.wall_pinned_adiabatic' for c, _ in kritikler(j))
