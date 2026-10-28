"""ÖH D37 A1b panel-js 5. tur (14 Eki) — güvenlik paneli motor sınıfı.

ÖLÇÜLEN KUSUR (KAB 14 Eki ``dock.json``; önce/sonra
``docs/scofield/raw/OH/A1b/panel-js/a1/t5/``): ``safety_panel.js`` katı VE
hibrit motoru ``propellant_type='composite'`` (APCP/HTPB) diye gönderiyordu.
Örnek N2O/HTPB hibritte uç sınıf ``composite``, TNT 5,435 kg, patlama
tahliyesi 1600 m; örnek KNDX katıda (şeker itici) yine ``composite``,
TNT 1,011 kg, tahliye 1600 m.

Bekçiler:
  * panel itici sınıfını motorun KENDİ iticisinden türetir (katı: merkezi
    katalog ``family``; kâhin ``hrma.data.propellants_db.PROPELLANTS``);
  * hibrit ve şeker itici akışında sayısal TNT / patlama mesafesi / Gurney
    parça menzili / tahliye YOK, NOT_EVALUATED + adlı gerekçe VAR;
  * APCP katı ve sıvı akışında panel gövdesi eski kuralla ('composite' /
    'liquid_biprop') AYNI ve uç yanıtı bayt bayt aynı (sha256).
"""
import contextlib
import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
ORNEK_HIBRIT = KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma'
ORNEK_KATI = KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma'
ORNEK_SIVI = KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node yok')

#: Sıvı örnekte itici kütlesinin yayımlanması için süre (D36 sıvı a2 ile
#: aynı bant; /analyze_safety 0-300 s). Ölçüm girdisi, ürün verisi değil.
SIVI_SURE_S = 250.0

from hrma.analysis.safety_analysis import (  # noqa: E402
    EXPLOSIVE_NOT_MODELLED_CODE_BY_MOTOR,
    EXPLOSIVE_NOT_MODELLED_DEFAULT_CODE,
    EXPLOSIVE_NOT_MODELLED_REASONS,
    GURNEY_FRAGMENT_FIELDS,
    KNOWN_PROPELLANT_CLASSES,
    PROPELLANT_CLASS_NOT_MODELLED,
    SafetyAnalyzer,
    THERMAL_VERDICT_NOT_EVALUATED,
)
from hrma.data.propellants_db import PROPELLANTS as KATALOG  # noqa: E402

HARNESS = r"""
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = JSON.parse(process.env.HRMA_ARGS);
const girdi = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
function El(tag) { this.tagName = String(tag || 'div').toUpperCase();
  this.children = []; this.style = {}; this.dataset = {}; this._attrs = {}; this.innerHTML = ''; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; };
El.prototype.querySelectorAll = function () { return []; };
const documentStub = { head: new El('head'), body: new El('body'), readyState: 'complete',
  createElement: function (t) { return new El(t); }, querySelector: function () { return null; },
  querySelectorAll: function () { return []; }, getElementById: function () { return null; },
  addEventListener: function () {} };
const katalog = girdi.catalog || null;
const sandbox = { console: { log() {}, warn() {}, error() {} },
  setTimeout, clearTimeout, setInterval, clearInterval,
  fetch: function (u) {
    if (katalog && String(u) === '/api/propellants') {
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve(katalog); } });
    }
    return Promise.reject(new Error('ağ yok')); },
  JSON, Math, Number, Array, Object, String, Boolean, RegExp, Promise,
  isFinite, parseFloat, parseInt, document: documentStub };
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
function run(f) { vm.runInContext(fs.readFileSync(f, 'utf8'), sandbox, { filename: f }); }
run(path.join(staticDir, 'units_constants.js'));
run(path.join(staticDir, 'analysis_dock.js'));
if (girdi.loadCatalog) run(path.join(staticDir, 'propellant_catalog.js'));
run(path.join(staticDir, 'panels', 'safety_panel.js'));
(async function () {
  if (girdi.loadCatalog && sandbox.window.HRMAPropellants) await sandbox.window.HRMAPropellants.load();
  const out = { siniflar: {}, govdeler: {}, html: {} };
  const spec = sandbox.window.AnalysisDock._registry.filter(s => s.id === 'safety')[0];
  (girdi.siniflar || []).forEach(function (s) {
    out.siniflar[s.ad] = sandbox.window.SafetyPanel._propellantClassFromMotor(s.results, s.motorType);
    if (out.siniflar[s.ad] === undefined) out.siniflar[s.ad] = null;
  });
  Object.keys(girdi.vakalar || {}).forEach(function (ad) {
    const v = girdi.vakalar[ad];
    sandbox.window.AnalysisDock._setMotorType(v.motorType);
    const sug = spec.fromResults(v.results);
    const govde = {};
    // Güvertenin gövde kuralı (analysis_dock.js applySuggestions +
    // buildPayload): seçiciye öneri YALNIZ seçenek varsa yazılır; sayı
    // alanına öneri yalnız sonlu sayıysa; kutuda sonlu sayı yoksa gitmez.
    (spec.fields || []).forEach(function (f) {
      const k = f[0];
      if (Array.isArray(f[3])) {
        const secenekler = f[3].map(o => o[0]);
        const istek = (typeof sug[k] === 'string' && sug[k]) ? sug[k] : null;
        govde[k] = (istek !== null && secenekler.indexOf(istek) !== -1) ? istek : f[2];
        return;
      }
      let val = f[2];
      if (typeof sug[k] === 'number' && isFinite(sug[k])) val = Number(sug[k].toPrecision(6));
      if (typeof val === 'number' && isFinite(val)) govde[k] = val;
    });
    // V301/PANEL (NK-18): güvertenin runPanel kuralı — form dışı bağlam
    // (spec.contextFromResults: motorun yapısal hüküm bloğu) alanı EZMEDEN
    // eklenir; boş bağlam gönderilmez.
    if (typeof spec.contextFromResults === 'function') {
      const ctx = spec.contextFromResults(v.results);
      if (ctx && typeof ctx === 'object') Object.keys(ctx).forEach(function (k) {
        if (!(k in govde) && ctx[k] !== undefined && ctx[k] !== null) govde[k] = ctx[k];
      });
    }
    out.govdeler[ad] = govde;
  });
  Object.keys(girdi.render || {}).forEach(function (ad) {
    const root = new El('div');
    sandbox.window.SafetyPanel._render(girdi.render[ad], root);
    out.html[ad] = root.innerHTML;
  });
  process.stdout.write(JSON.stringify(out));
})().catch(function (e) { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


def _sessiz(fn, *a, **k):
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon), contextlib.redirect_stderr(tampon):
        return fn(*a, **k)


def _node(girdi: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        yol = pathlib.Path(tmp) / 'girdi.json'
        yol.write_text(json.dumps(girdi), encoding='utf-8')
        env = dict(os.environ, HRMA_ARGS=json.dumps([str(JS), str(yol)]))
        out = subprocess.run([NODE, '-'], input=HARNESS, capture_output=True,
                             text=True, timeout=180, env=env)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout)


def _sha(j) -> str:
    return hashlib.sha256(json.dumps(j, sort_keys=True,
                                     default=str).encode()).hexdigest()


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def katalog_json(client):
    r = client.get('/api/propellants')
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def motorlar(client):
    """Örnek projelerin GERÇEK çözücü yanıtları (modül başına bir koşu)."""
    def alanlar(yol):
        return json.loads(yol.read_text(encoding='utf-8'))['inputs']['fields']
    kati = alanlar(ORNEK_KATI)
    out = {
        'hybrid': _sessiz(client.post, '/calculate',
                          json=alanlar(ORNEK_HIBRIT)).get_json(),
        'kndx': _sessiz(client.post, '/calculate_solid', json=kati).get_json(),
        # APCP: aynı örnek geometri, itici kimliği açık alanla (öncelik
        # propellant_type > ön ayar; solid_rocket_engine çözümleyicisi).
        # V301/PANEL — KURGU DÜZELTİLDİ (main f77564ee5'te de kırmızıydı):
        # örnek KNDX kaydının ``burn_rate_preset: 'kndx'`` alanı APCP
        # kimliğiyle KARIŞIK kayıttı; V301/K-C2 (NK-29/NK-70) bunu haklı
        # olarak 422 ``burn_rate_law_propellant_mismatch`` ile reddediyor.
        # APCP vakası kendi yanma hızı tablosuyla kurulur; iddialar aynı.
        'apcp': _sessiz(client.post, '/calculate_solid',
                        json=dict(kati, propellant_type='apcp',
                                  burn_rate_preset='apcp')).get_json(),
        'liquid': _sessiz(client.post, '/calculate_liquid', json=dict(
            alanlar(ORNEK_SIVI), max_burn_duration=SIVI_SURE_S)).get_json(),
    }
    assert out['kndx'].get('propellant_type') == 'kndx'
    assert out['apcp'].get('propellant_type') == 'apcp'
    return out


VAKA_MOTOR = {'hybrid': 'hybrid', 'kndx': 'solid', 'apcp': 'solid',
              'liquid': 'liquid'}


@pytest.fixture(scope='module')
def panel(motorlar, katalog_json):
    return _node({'loadCatalog': True, 'catalog': katalog_json, 'vakalar': {
        ad: {'motorType': VAKA_MOTOR[ad], 'results': motorlar[ad]}
        for ad in VAKA_MOTOR}})


# ---------------------------------------------------------------------------
# 1) MODÜL — beyan bir sınıf değildir; geri çekme kaydı tek kaynaktan
# ---------------------------------------------------------------------------
class TestModulBeyani:
    def test_beyan_sinif_degil_ve_sayi_tasimaz(self):
        an = SafetyAnalyzer()
        assert PROPELLANT_CLASS_NOT_MODELLED not in KNOWN_PROPELLANT_CLASSES
        assert PROPELLANT_CLASS_NOT_MODELLED not in an.propellant_tnt_equivalents

    @pytest.mark.parametrize('motor', ['hybrid', 'solid', 'liquid', None])
    def test_sinif_cozulmez_gerekce_motor_tipine_gore(self, motor):
        sinif, gerekce = SafetyAnalyzer()._resolve_explosive_class(
            PROPELLANT_CLASS_NOT_MODELLED, motor)
        kod = EXPLOSIVE_NOT_MODELLED_CODE_BY_MOTOR.get(
            motor, EXPLOSIVE_NOT_MODELLED_DEFAULT_CODE)
        assert sinif is None
        assert gerekce == EXPLOSIVE_NOT_MODELLED_REASONS[kod]

    def test_hibritte_oksitleyici_adi_beyani_sinifa_cevirmez(self):
        an = SafetyAnalyzer()
        an._requested_oxidizer = 'n2o'
        sinif, _ = an._resolve_explosive_class(PROPELLANT_CLASS_NOT_MODELLED,
                                               'hybrid')
        assert sinif is None


# ---------------------------------------------------------------------------
# 2) UÇ — beyanlı istekte hiçbir patlayıcı sayısı yayımlanmaz
# ---------------------------------------------------------------------------
BEYAN_UC_GOVDE = {'chamber_pressure': 30.0, 'propellant_mass': 12.94,
            'chamber_diameter': 0.121, 'wall_thickness': 0.005,
            'thrust': 3000.0, 'burn_time': 10.0, 'material': 'ss_304'}


def _beyan_yok_sayi_yok(j, kod):
    s = j['safety_analysis']
    ex = s['explosive_hazards']
    assert ex['explosive_class'] is None
    for alan in ('tnt_equivalent_kg', 'tnt_equivalent_factor',
                 'blast_distances', 'qd_requirements'):
        assert alan not in ex, (alan, ex.get(alan))
    beyan = ex['explosive_not_modelled']
    assert beyan['status'] == THERMAL_VERDICT_NOT_EVALUATED
    assert beyan['code'] == kod
    assert ex['explosive_verdict_withheld_because'] == \
        EXPLOSIVE_NOT_MODELLED_REASONS[kod]
    fr = ex['fragment_hazards']
    for alan in GURNEY_FRAGMENT_FIELDS:
        assert alan in fr and fr[alan] is None, (alan, fr.get(alan))
    assert fr['fragment_throw_status'] == THERMAL_VERDICT_NOT_EVALUATED
    pat = s['emergency_procedures']['explosion_response']
    assert pat['evacuation_distance'] is None
    assert pat['evacuation_distance_status'] == THERMAL_VERDICT_NOT_EVALUATED
    assert pat['evacuation_distance_reason'] == \
        EXPLOSIVE_NOT_MODELLED_REASONS[kod]
    ra = s['risk_assessment']
    assert 'explosive' in ra['risks_not_evaluated']
    assert ra['individual_risks']['explosive'] is None


class TestUc:
    @pytest.mark.parametrize('motor,kod', [
        ('hybrid', 'hybrid_oxidiser_tank'),
        ('solid', 'solid_no_sourced_tnt')])
    def test_beyanli_istek_sayi_yayimlamaz(self, client, motor, kod):
        r = _sessiz(client.post, '/analyze_safety', json=dict(
            BEYAN_UC_GOVDE, motor_type=motor,
            propellant_type=PROPELLANT_CLASS_NOT_MODELLED))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        _beyan_yok_sayi_yok(r.get_json(), kod)

    def test_katida_toksik_sinif_motor_tipinden_composite_olmaz(self, client):
        r = _sessiz(client.post, '/analyze_safety', json=dict(
            BEYAN_UC_GOVDE, motor_type='solid',
            propellant_type=PROPELLANT_CLASS_NOT_MODELLED))
        kunye = r.get_json()['toxic_basis']
        assert kunye['propellant_class'] is None, kunye


# ---------------------------------------------------------------------------
# 3) PANEL — sınıf motorun KENDİ iticisinden (kâhin: katalog 'family')
# ---------------------------------------------------------------------------
def _beklenen_kati_sinifi(anahtar):
    aile = KATALOG[anahtar]['family']
    return aile if aile in KNOWN_PROPELLANT_CLASSES else \
        PROPELLANT_CLASS_NOT_MODELLED


@needs_node
class TestPanelSinifi:
    def test_katalogun_her_satiri_kendi_ailesinden(self, katalog_json):
        siniflar = [{'ad': k, 'motorType': 'solid',
                     'results': {'propellant_type': k}} for k in KATALOG]
        out = _node({'loadCatalog': True, 'catalog': katalog_json,
                     'siniflar': siniflar})['siniflar']
        for k in KATALOG:
            assert out[k] == _beklenen_kati_sinifi(k), (k, out[k])
        # Şeker ailesinin tamamı ve kara barut modellenmedi; APCP ailesi
        # composite (kâhin tablodan, bu liste yalnız kapsam tanığı).
        for k in ('kndx', 'knsb', 'knsu', 'kner', 'sugar', 'black_powder'):
            assert out[k] == PROPELLANT_CLASS_NOT_MODELLED, k
        assert out['apcp'] == 'composite'

    def test_fail_closed_katalog_yok_ya_da_ad_bilinmiyor(self, katalog_json):
        girdi = [{'ad': 'bilinmeyen', 'motorType': 'solid',
                  'results': {'propellant_type': 'peynir'}},
                 {'ad': 'adsiz', 'motorType': 'solid', 'results': {}}]
        out = _node({'loadCatalog': True, 'catalog': katalog_json,
                     'siniflar': girdi})['siniflar']
        assert out == {'bilinmeyen': PROPELLANT_CLASS_NOT_MODELLED,
                       'adsiz': PROPELLANT_CLASS_NOT_MODELLED}
        # Katalog yüklenemediyse APCP bile ürün varsayılanına ÇEVRİLMEZ.
        out = _node({'loadCatalog': False, 'siniflar': [
            {'ad': 'apcp', 'motorType': 'solid',
             'results': {'propellant_type': 'apcp'}}]})['siniflar']
        assert out == {'apcp': PROPELLANT_CLASS_NOT_MODELLED}

    def test_hibrit_ve_sivi(self, katalog_json):
        out = _node({'loadCatalog': True, 'catalog': katalog_json,
                     'siniflar': [
                         {'ad': 'h', 'motorType': 'hybrid', 'results': {}},
                         {'ad': 's', 'motorType': 'liquid', 'results': {}}]})
        assert out['siniflar'] == {'h': PROPELLANT_CLASS_NOT_MODELLED,
                                   's': 'liquid_biprop'}


# ---------------------------------------------------------------------------
# 4) UÇTAN UCA — gerçek örnek motor -> panel gövdesi -> /analyze_safety
# ---------------------------------------------------------------------------
@needs_node
class TestUctanUca:
    @pytest.mark.parametrize('ad,kod', [('hybrid', 'hybrid_oxidiser_tank'),
                                        ('kndx', 'solid_no_sourced_tnt')])
    def test_hibrit_ve_seker_itici_sayi_yok_beyan_var(self, client, panel,
                                                       ad, kod):
        govde = panel['govdeler'][ad]
        assert govde['propellant_type'] == PROPELLANT_CLASS_NOT_MODELLED
        assert govde['motor_type'] == VAKA_MOTOR[ad]
        r = _sessiz(client.post, '/analyze_safety', json=govde)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        _beyan_yok_sayi_yok(r.get_json(), kod)

    @pytest.mark.parametrize('ad,eski', [('apcp', 'composite'),
                                         ('liquid', 'liquid_biprop')])
    def test_gecerli_siniflarda_yanit_bit_ayni(self, client, panel, ad, eski):
        """Eski kural: katıda 'composite', sıvıda 'liquid_biprop'."""
        govde = panel['govdeler'][ad]
        assert govde['propellant_type'] == eski
        yeni = _sessiz(client.post, '/analyze_safety', json=govde)
        eskisi = _sessiz(client.post, '/analyze_safety',
                         json=dict(govde, propellant_type=eski))
        assert yeni.status_code == eskisi.status_code == 200
        assert _sha(yeni.get_json()) == _sha(eskisi.get_json())
        ex = yeni.get_json()['safety_analysis']['explosive_hazards']
        assert ex['explosive_class'] == eski
        assert 'explosive_not_modelled' not in ex
        pat = yeni.get_json()['safety_analysis']['emergency_procedures'][
            'explosion_response']
        assert isinstance(pat['evacuation_distance'], float)
        assert 'evacuation_distance_status' not in pat


# ---------------------------------------------------------------------------
# 5) EKRAN — gri DEĞERLENDİRİLMEDİ + gerekçe, sayı yok
# ---------------------------------------------------------------------------
@needs_node
class TestEkran:
    def test_hibrit_ekraninda_beyan_var_sayi_yok(self, client, panel):
        yanit = _sessiz(client.post, '/analyze_safety',
                        json=panel['govdeler']['hybrid']).get_json()
        html = _node({'render': {'h': yanit}})['html']['h']
        assert 'data-safety-not-modelled="hybrid_oxidiser_tank"' in html
        for yol in ('explosion_response.evacuation_distance',
                    'fragment_hazards.lethal_fragment_range_m',
                    'fragment_hazards.fragment_velocity_ms',
                    'fragment_hazards.maximum_range_m'):
            assert 'data-safety-withheld="%s"' % yol in html, yol
        assert '1600' not in html

    def test_yeni_anahtarlar_en_ve_tr_sozlukte(self):
        metin = (JS / 'i18n_common.js').read_text(encoding='utf-8')
        for anahtar in ('prop.notModelled', 'panel.safety.explosiveNotEvaluated',
                        'panel.safety.notModelledHybrid',
                        'panel.safety.notModelledSolid',
                        'panel.safety.notModelledGeneric'):
            assert metin.count("'%s':" % anahtar) == 2, anahtar
