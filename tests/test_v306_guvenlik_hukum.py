"""V306/GÜVENLİK — güvenlik sekmesinde tek hüküm, açık kısmilik (NR-3).

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/V306/guvenlik/olcum/
guvenlik_once.json``; taban 853764cb4): üç örnek motorun üçünde de yapısal
eksen (hibritte termal de) değerlendirilmemişken GÜVENLİK sekmesinin üst
şeridi yeşil "MOTOR TASARIM RİSKİ: LOW" ve yeşil "SKOR 2.00 / 5" basıyordu;
kısmilik yalnız aşağıda İngilizce ham alandaydı. Hibritte termal eksenin
gerekçesi ısı modülünün ÇIPLAK CİDAR uyarısıydı ("3257 K, erime 1673 K
aşılıyor") — motorun kendi bölge sonucu (yakıt bloğu altı korunur, ön/son
odaya astar) o kaydı geçersiz kılmışken.

Bekçiler (üç örnek motor × panelin gövdesi × gerçek uç × panelin render'ı,
TR ve EN):
  * değerlendirilmeyen motor ekseni varken yanıtta ve ekranda LOW/MEDIUM
    yok, rozet yeşil değil, "N / 3 eksen" ve eksen adları yazılı;
  * hibritte termal eksenin gerekçesi motorun bölge kaydıdır (sayılar
    ``chamber_wall_zones`` ile aynı), çıplak cidar uyarısı basılmaz;
  * katı ve sıvıda termal eksenin cidar sıcaklığı motorun çözdüğü çifttir;
  * bütün motor eksenleri değerlendirildiğinde LOW aynen yayımlanır, kısmi
    HIGH/CRITICAL uyarısı susturulmaz.
"""
import json
import os
import pathlib
import re
import subprocess
import tempfile

import pytest

from hrma.analysis.safety_analysis import (
    MOTOR_DESIGN_RISK_AXES,
    SafetyAnalyzer,
    motor_solved_wall_pair,
)
from tests.test_d37_panel_js_t5_guvenlik_sinifi import (  # noqa: F401
    JS, NODE, ORNEK_HIBRIT, ORNEK_KATI, ORNEK_SIVI, _sessiz, client,
    katalog_json, needs_node)

ORNEK = {'hybrid': (ORNEK_HIBRIT, '/calculate'),
         'solid': (ORNEK_KATI, '/calculate_solid'),
         'liquid': (ORNEK_SIVI, '/calculate_liquid')}

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
function kur(lang) {
  const doc = { head: new El('head'), body: new El('body'), readyState: 'complete',
    documentElement: { setAttribute() {}, lang: lang },
    createElement: function (t) { return new El(t); }, querySelector: function () { return null; },
    querySelectorAll: function () { return []; }, getElementById: function () { return null; },
    addEventListener: function () {} };
  const katalog = girdi.catalog || null;
  const sb = { console: { log() {}, warn() {}, error() {} },
    setTimeout, clearTimeout, setInterval, clearInterval,
    fetch: function (u) {
      if (katalog && String(u) === '/api/propellants') {
        return Promise.resolve({ ok: true, json: function () { return Promise.resolve(katalog); } });
      }
      return Promise.reject(new Error('ağ yok')); },
    JSON, Math, Number, Array, Object, String, Boolean, RegExp, Promise, Date, Error,
    isFinite, isNaN, parseFloat, parseInt, encodeURIComponent, document: doc };
  sb.window = sb; sb.globalThis = sb; sb.self = sb; sb.localStorage = null;
  vm.createContext(sb);
  function run(f) { vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
  if (lang) {
    for (const f of ['i18n.js', 'i18n_common.js', 'i18n_charts.js']) run(path.join(staticDir, f));
    sb.I18N.setLang(lang);
  }
  run(path.join(staticDir, 'units_constants.js'));
  run(path.join(staticDir, 'analysis_dock.js'));
  run(path.join(staticDir, 'propellant_catalog.js'));
  run(path.join(staticDir, 'panels', 'safety_panel.js'));
  return sb;
}
function govdeKur(sb, motorType, results) {
  sb.window.AnalysisDock._setMotorType(motorType);
  const spec = sb.window.AnalysisDock._registry.filter(s => s.id === 'safety')[0];
  const sug = spec.fromResults(results);
  const govde = {};
  (spec.fields || []).forEach(function (f) {
    const k = f[0];
    if (Array.isArray(f[3])) {
      const sec = f[3].map(o => o[0]);
      const istek = (typeof sug[k] === 'string' && sug[k]) ? sug[k] : null;
      govde[k] = (istek !== null && sec.indexOf(istek) !== -1) ? istek : f[2];
      return;
    }
    let val = f[2];
    if (typeof sug[k] === 'number' && isFinite(sug[k])) val = Number(sug[k].toPrecision(6));
    if (typeof val === 'number' && isFinite(val)) govde[k] = val;
  });
  const ctx = spec.contextFromResults(results);
  if (ctx && typeof ctx === 'object') Object.keys(ctx).forEach(function (k) {
    if (!(k in govde) && ctx[k] !== undefined && ctx[k] !== null) govde[k] = ctx[k];
  });
  return govde;
}
(async function () {
  const out = { govdeler: {}, html: {} };
  const langs = girdi.render ? ['tr', 'en'] : [null];
  for (const lang of langs) {
    const sb = kur(lang);
    if (sb.window.HRMAPropellants) await sb.window.HRMAPropellants.load();
    for (const ad of Object.keys(girdi.vakalar || {})) {
      const v = girdi.vakalar[ad];
      const govde = govdeKur(sb, v.motorType, v.results);
      if (!girdi.render) { out.govdeler[ad] = govde; continue; }
      const root = new El('div');
      sb.window.SafetyPanel._render(girdi.render[ad], root);
      out.html[ad + ':' + lang] = root.innerHTML;
    }
  }
  process.stdout.write(JSON.stringify(out));
})().catch(function (e) { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


def _node(girdi):
    with tempfile.TemporaryDirectory() as tmp:
        yol = pathlib.Path(tmp) / 'girdi.json'
        yol.write_text(json.dumps(girdi), encoding='utf-8')
        env = dict(os.environ, HRMA_ARGS=json.dumps([str(JS), str(yol)]))
        out = subprocess.run([NODE, '-'], input=HARNESS, capture_output=True,
                             text=True, timeout=240, env=env)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout)


def _duz(h):
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', h.replace('&amp;', '&')).strip()


def _serit(h):
    """Üst rozet şeridi (ilk flex kutusu) — ham HTML."""
    m = re.search(r'<div style="display:flex; flex-wrap:wrap; gap:8px; '
                  r'margin:8px 0;">(.*?)</div>', h, flags=re.S)
    assert m, 'üst rozet şeridi bulunamadı'
    return m.group(1)


@pytest.fixture(scope='module')
def kosum(client, katalog_json):
    motor = {}
    for mt, (yol, uc) in ORNEK.items():
        alan = json.loads(yol.read_text(encoding='utf-8'))['inputs']['fields']
        r = _sessiz(client.post, uc, json=alan)
        assert r.status_code == 200, (mt, r.get_data(as_text=True)[:300])
        motor[mt] = r.get_json()
    vakalar = {mt: {'motorType': mt, 'results': motor[mt]} for mt in ORNEK}
    g = _node({'catalog': katalog_json, 'vakalar': vakalar})
    yanit = {}
    for mt in ORNEK:
        r = _sessiz(client.post, '/analyze_safety', json=g['govdeler'][mt])
        assert r.status_code == 200, (mt, r.get_data(as_text=True)[:300])
        yanit[mt] = r.get_json()
    h = _node({'catalog': katalog_json, 'vakalar': vakalar, 'render': yanit})
    return {'motor': motor, 'govde': g['govdeler'], 'yanit': yanit,
            'html': h['html']}


# ---------------------------------------------------------------------------
# NR-3 (b) — kısmi değerlendirme LOW/yeşil değildir
# ---------------------------------------------------------------------------
@needs_node
@pytest.mark.parametrize('mt', sorted(ORNEK))
def test_kismi_sepette_dusuk_risk_yayimlanmaz(kosum, mt):
    ra = kosum['yanit'][mt]['safety_analysis']['risk_assessment']
    yok = ra['motor_axes_not_evaluated']
    assert set(yok) | set(ra['motor_axes_evaluated']) == set(
        MOTOR_DESIGN_RISK_AXES)
    # Ölçülen durum: üç örnekte de yapısal eksen motorun zincirinde geri
    # çekili (HRMA'nın boyutlandırdığı cidar hüküm kazanmaz).
    assert 'structural' in yok
    assert ra['risk_level'] not in ('LOW', 'MEDIUM')
    assert ra['risk_level'] == 'NOT_EVALUATED'
    assert ra['risk_level_of_evaluated_axes'] in ('LOW', 'MEDIUM')
    assert ra['risk_level_withheld_because']


@needs_node
@pytest.mark.parametrize('mt', sorted(ORNEK))
@pytest.mark.parametrize('lang', ['tr', 'en'])
def test_rozet_kismiligi_soyler_yesil_yanmaz(kosum, mt, lang):
    ra = kosum['yanit'][mt]['safety_analysis']['risk_assessment']
    h = kosum['html'][mt + ':' + lang]
    serit = _serit(h)
    m = re.search(r'<span data-safety-motor-risk="([^"]+)">(.*?)</span>\s*'
                  r'</span>', serit, flags=re.S)
    assert m, 'motor tasarım riski rozeti yok'
    rozet = m.group(2)
    yesil = 'var(--hd-green'
    assert yesil not in rozet, 'kısmi motor hükmü YEŞİL basılıyor'
    metin = _duz(rozet)
    assert not re.search(r'\b(LOW|DÜŞÜK)\b', metin), metin
    n, top = len(ra['motor_axes_evaluated']), len(MOTOR_DESIGN_RISK_AXES)
    beklenen = ('%d EKSENDEN %d TANESİ DEĞERLENDİRİLDİ' % (top, n)
                if lang == 'tr' else '%d OF %d AXES EVALUATED' % (n, top))
    assert beklenen in metin, metin
    assert ('DEĞERLENDİRİLMEDİ' if lang == 'tr' else 'NOT EVALUATED') in metin
    # Skor rozeti kısmi sepette yeşil değil ve "değerlendirilen eksenler"
    # diye etiketli.
    assert ('DEĞERLENDİRİLEN EKSENLERİN SKORU' if lang == 'tr'
            else 'SCORE OF EVALUATED AXES') in _duz(serit)
    # Kısmilik cümlesi eksenleri ADIYLA söyler (kullanıcı dilinde).
    m2 = re.search(r'<p data-safety-partial="1"[^>]*>(.*?)</p>', h, re.S)
    assert m2, 'kısmilik cümlesi yok'
    cumle = _duz(m2.group(1))
    adlar = {'tr': {'structural': 'Yapısal', 'pressure': 'Basınç',
                    'thermal': 'Termal'},
             'en': {'structural': 'Structural', 'pressure': 'Pressure',
                    'thermal': 'Thermal'}}[lang]
    for eksen in ra['motor_axes_not_evaluated']:
        assert adlar[eksen] in cumle, (eksen, cumle)
    if lang == 'tr':
        assert 'risk_level_is_partial' not in cumle
        assert re.search(r'\d,\d\d / 5', cumle), cumle   # TR virgüllü


# ---------------------------------------------------------------------------
# NR-3 (a) — termal eksen motorun cidar sonucunu okur (tek kaynak)
# ---------------------------------------------------------------------------
@needs_node
@pytest.mark.parametrize('lang', ['tr', 'en'])
def test_hibrit_termal_eksen_motorun_bolge_sonucu(kosum, lang):
    motor = kosum['motor']['hybrid']
    bolge = (motor.get('motor') or motor)['chamber_wall_zones']
    th = kosum['yanit']['hybrid']['safety_analysis']['thermal_safety']
    assert th['thermal_verdict'] == 'withheld'
    ozet = th['motor_wall_zones']['zones']
    # Yanıttaki bölge kaydı motorunkiyle AYNI (sayı türetilmez).
    assert [z['zone'] for z in ozet] == [z['zone'] for z in bolge['zones']]
    for a, b in zip(ozet, bolge['zones']):
        assert a['verdict'] == b['verdict']
        for k in ('liner_thickness_mm', 'casing_temperature_K'):
            if b.get(k) is not None:
                assert a[k] == b[k], (k, a, b)
    h = kosum['html']['hybrid:' + lang]
    assert 'data-safety-wall-unphysical' not in h, (
        'motorun bölge sonucu varken çıplak cidar uyarısı basılıyor')
    m = re.search(r'<div data-safety-zone-thermal="1"[^>]*>(.*?)</div>', h,
                  re.S)
    assert m, 'termal eksen notu motorun bölge sonucunu basmıyor'
    not_ = _duz(m.group(1))
    astar = [z['liner_thickness_mm'] for z in bolge['zones']
             if z.get('liner_thickness_mm') is not None]
    assert astar
    sayi = ('%.2f' % astar[0])
    if lang == 'tr':
        sayi = sayi.replace('.', ',')
    assert sayi + ' mm' in not_, (sayi, not_)
    # Isı modülünün çıplak cidar denge sıcaklığı ve erime sözcüğü bu
    # eksenin hükmü olarak basılmaz.
    t_ciplak = bolge['bare_wall_check']['temperature_K']
    assert ('%.0f K' % t_ciplak) not in _duz(h)
    assert 'erime noktası' not in _duz(h) and 'melting point' not in _duz(h)


@needs_node
@pytest.mark.parametrize('mt', ['solid', 'liquid'])
def test_kati_sivi_termal_eksen_motorun_cifti(kosum, mt):
    th = kosum['yanit'][mt]['safety_analysis']['thermal_safety']
    cift = motor_solved_wall_pair(mt, kosum['motor'][mt])
    assert cift is not None
    assert th['thermal_verdict'] == 'issued'
    # Gövde güvertenin 6 anlamlı basamağıyla yazar (toPrecision(6)).
    assert th['inner_wall_temperature_k'] == pytest.approx(cift['hot'],
                                                           rel=1e-5)
    assert th['outer_wall_temperature_k'] == pytest.approx(cift['cold'],
                                                           rel=1e-5)


# ---------------------------------------------------------------------------
# Sepetin kendisi — tam sepette LOW kalır, kısmi uyarı susturulmaz
# ---------------------------------------------------------------------------
def _sepet(yapisal, basinc, termal):
    sa = SafetyAnalyzer()
    sa._score_structural_risk = lambda _b: yapisal
    sa._score_pressure_risk = lambda _b: basinc
    sa._score_thermal_risk = lambda _b: termal
    sa._score_explosive_risk = lambda _b: None
    sa._score_toxic_risk = lambda _b: None
    sa._score_fire_risk = lambda _b: 2.0
    return sa._calculate_overall_risk({}, {}, {}, {}, {}, {})


def test_tam_sepette_low_aynen():
    ra = _sepet(1.0, 2.0, 2.0)
    assert ra['risk_level'] == 'LOW'
    assert ra['motor_axes_not_evaluated'] == []
    assert 'risk_level_withheld_because' not in ra
    assert 'risk_level_of_evaluated_axes' not in ra


@pytest.mark.parametrize('skorlar,beklenen', [
    ((None, 4.0, 2.0), 'HIGH'), ((None, 5.0, None), 'CRITICAL')])
def test_kismi_uyari_susturulmaz(skorlar, beklenen):
    ra = _sepet(*skorlar)
    assert ra['risk_level'] == beklenen
    assert ra['risk_level_is_partial'] is True


@pytest.mark.parametrize('skorlar', [(None, 2.0, 2.0), (None, 3.0, None),
                                     (None, None, None)])
def test_kismi_dusuk_orta_geri_cekilir(skorlar):
    ra = _sepet(*skorlar)
    assert ra['risk_level'] == 'NOT_EVALUATED'


# ---------------------------------------------------------------------------
# NR-19 — aynı kamara: tek deneme, tek patlama, gerilme ⟷ patlama aynı katman
# ---------------------------------------------------------------------------
def _sivi_kayit(kosum):
    m = kosum['motor']['liquid']
    return m['structural_analysis'], kosum['yanit']['liquid'][
        'safety_analysis']['pressure_safety']


@needs_node
def test_sivi_tek_deneme_tek_patlama_tanimi(kosum):
    # V306/SIVI-KÜTLE (kalem 5): sıvı motorun kamarası motor donanımıdır —
    # katsayılar NASA-STD-5012C Tablo 1 (tek tablo, kod modu).
    from hrma.analysis.pressure_vessel import CODE_PRESSURE_FACTORS
    PROOF = CODE_PRESSURE_FACTORS['nasa_std_5012c']['proof']
    BURST = CODE_PRESSURE_FACTORS['nasa_std_5012c']['burst']
    sa, ps = _sivi_kayit(kosum)
    assert ps['code_mode'] == 'nasa_std_5012c'
    dr = sa['design_requirements']
    # V306/SIVI-KÜTLE (kalem 4): gereksinim değerlendirilen katmanın MDP'si
    # üstünden — iki katmanlı örnek sıvıda dış kabuğun MDP'si ceketteki en
    # yüksek soğutucu basıncıdır (76,29 bar), oda basıncı (50 bar) değil.
    kabuk = [k for k in sa['chamber_structure']['wall_layers']
             if k['role'] == 'closeout'][0]
    mdp = ps['mdp_bar']
    assert mdp == pytest.approx(kabuk['coolant_pressure_bar'])
    assert dr['mdp_bar'] == pytest.approx(mdp)
    # Alt Sistemler/Yapısal kartı ile GÜVENLİK/Basınçlı Kap AYNI sayı.
    assert dr['proof_pressure'] == pytest.approx(ps['proof_pressure_bar'])
    assert dr['burst_pressure'] == pytest.approx(
        ps['required_burst_pressure_bar'])
    assert ps['proof_pressure_bar'] == pytest.approx(PROOF * mdp)
    assert ps['required_burst_pressure_bar'] == pytest.approx(BURST * mdp)
    # Kabul (proof) testi hidrostatik testtir; hedef patlamanın üstünde
    # bir test basıncı yayımlanmaz.
    assert ps['hydrostatic_test_pressure_bar'] == ps['proof_pressure_bar']
    assert ps['hydrostatic_test_pressure_bar'] < ps[
        'required_burst_pressure_bar']


@needs_node
def test_sivi_patlama_basinci_gerilmenin_katmaninda(kosum):
    sa, ps = _sivi_kayit(kosum)
    cs = sa['chamber_structure']
    kabuk = [k for k in cs['wall_layers'] if k['role'] == 'closeout'][0]
    el = ps['evaluated_layer']
    assert el['role'] == 'closeout'
    # Gerilmenin katmanı = patlama basıncının katmanı (geometri + sıcaklık).
    assert ps['wall_thickness_mm'] == pytest.approx(kabuk['thickness_mm'])
    assert ps['inner_diameter_mm'] == pytest.approx(
        2 * kabuk['inner_radius_mm'])
    assert el['temperature_K'] == pytest.approx(kabuk['max_temperature_K'])
    assert el['motor_hoop_stress_MPa'] == pytest.approx(cs['hoop_stress'])
    assert el['load_pressure_bar'] == pytest.approx(
        kabuk['coolant_pressure_bar'])
    assert el['stack_thickness_mm'] == pytest.approx(cs['wall_thickness'])
    # Tutarlılık: çember gerilmesi patlama basıncına doğrusal ölçeklenince
    # katmanın sıcaklıktaki çekme dayanımının ±%10'u içinde kalır (iki
    # yol: Barlow dış yarıçap ⟷ Faupel / ince cidar min). Eski yol (5,5 mm
    # yığın tek parça Inconel) bu oranı 3,8 katı aşıyordu.
    from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
    from hrma.data.materials_db import get_material
    mat = get_material(kabuk['material_key'])
    su = PressureVesselAnalyzer()._derate_strength(
        mat, kabuk['max_temperature_K'])['derated_ultimate_strength_Pa'] / 1e6
    sigma_patlama = (el['motor_hoop_stress_MPa'] * ps[
        'actual_burst_pressure_bar'] / el['load_pressure_bar'])
    assert sigma_patlama == pytest.approx(su, rel=0.10), (sigma_patlama, su)
    assert el['burst_margin_vs_load_pressure'] == pytest.approx(
        ps['actual_burst_pressure_bar'] / el['load_pressure_bar'])


def test_katman_girdi_ayrisinca_benimsenmez():
    """Kullanıcı güvertede cidarı değiştirdiyse motorun katmanı kullanılmaz."""
    sa = SafetyAnalyzer()
    katman = {'role': 'closeout', 'material_key': 'inconel_718',
              'thickness_mm': 2.5, 'inner_radius_mm': 118.9,
              'max_temperature_K': 414.0, 'coolant_pressure_bar': 76.3,
              'stress_MPa': 370.5}
    kayit = {'status': 'NOT_EVALUATED', 'withheld': True, 'reasons': [],
             'source': 'motor_structural_chain', 'pressure_layer': katman,
             'inputs': {'chamber_pressure': 50.0, 'chamber_diameter': 0.1338,
                        'wall_thickness': 0.0055}}
    md = {'chamber_pressure': 50.0, 'chamber_temperature': 3300.0,
          'chamber_diameter': 0.1338, 'wall_thickness': 0.003,
          'thrust': 25000.0, 'burn_time': 30.0}
    r = sa.analyze_comprehensive_safety(
        md, 50.0, propellant_type='liquid_biprop', material='inconel_718',
        motor_type='liquid', motor_verdict=kayit)
    ps = r['pressure_safety']
    assert ps['evaluated_layer']['role'] == 'chamber_wall'
    assert ps['wall_thickness_mm'] == pytest.approx(3.0)
    assert ps['pressure_layer_not_adopted']['fields'][0]['field'] == \
        'wall_thickness'


@pytest.mark.parametrize('bozuk', [
    {'thickness_mm': -1.0}, {'thickness_mm': float('nan')},
    {'material_key': 'peynir'}, {'coolant_pressure_bar': None},
    {'material_key': ['inconel_718']}])
def test_bozuk_katman_kaydi_kullanilmaz(bozuk):
    from hrma.analysis.safety_analysis import motor_pressure_bearing_layer
    k = {'role': 'closeout', 'material_key': 'inconel_718',
         'thickness_mm': 2.5, 'inner_radius_mm': 118.9,
         'max_temperature_K': 414.0, 'coolant_pressure_bar': 76.3,
         'stress_MPa': 370.5}
    k.update(bozuk)
    blok = {'wall_model': 'two_layer_regenerative', 'wall_layers': [k]}
    assert motor_pressure_bearing_layer(blok) is None


# ---------------------------------------------------------------------------
# NR-18 — hibrit Yapısal FEA: motorun katsayısı istasyon ADIYLA
# ---------------------------------------------------------------------------
FEA_HARNESS = r"""
const fs = require('fs'), path = require('path'), vm = require('vm');
const [staticDir, girdiYolu] = JSON.parse(process.env.HRMA_ARGS);
const girdi = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
function El(t) { this.tagName = String(t || 'div').toUpperCase();
  this.children = []; this.style = {}; this.innerHTML = ''; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function () {};
El.prototype.getAttribute = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.addEventListener = function () {};
const out = {};
for (const lang of ['tr', 'en']) {
  const doc = { head: new El('head'), body: new El('body'), readyState: 'complete',
    documentElement: { setAttribute() {}, lang: lang },
    createElement: function (t) { return new El(t); }, querySelector: function () { return null; },
    querySelectorAll: function () { return []; }, getElementById: function () { return null; },
    addEventListener: function () {} };
  const sb = { console: { log() {}, warn() {}, error() {} }, setTimeout, clearTimeout,
    setInterval, clearInterval, fetch: function () { return Promise.reject(new Error('ag yok')); },
    JSON, Math, Number, Array, Object, String, Boolean, RegExp, Date, Error, isFinite, isNaN,
    parseFloat, parseInt, encodeURIComponent, document: doc };
  sb.window = sb; sb.globalThis = sb; sb.self = sb; sb.localStorage = null;
  vm.createContext(sb);
  const run = f => vm.runInContext(fs.readFileSync(path.join(staticDir, f), 'utf8'), sb, { filename: f });
  for (const f of ['i18n.js', 'i18n_common.js', 'i18n_charts.js']) run(f);
  sb.I18N.setLang(lang);
  run('analysis_dock.js'); run('units_constants.js'); run('fea_panel.js');
  const P = sb.window.FeaPanel;
  const el = new El('div');
  P._renderBadges(el, P.buildViewModel(girdi.fea, null));
  out[lang] = el.innerHTML;
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope='module')
def fea_kosum(kosum, client):
    motor = kosum['motor']['hybrid']
    r = _sessiz(client.post, '/api/fea/structural',
                json={'motor': motor['motor']})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    fea = r.get_json()['fea']
    with tempfile.TemporaryDirectory() as tmp:
        yol = pathlib.Path(tmp) / 'girdi.json'
        yol.write_text(json.dumps({'fea': fea}), encoding='utf-8')
        env = dict(os.environ, HRMA_ARGS=json.dumps([str(JS), str(yol)]))
        out = subprocess.run([NODE, '-'], input=FEA_HARNESS,
                             capture_output=True, text=True, timeout=240,
                             env=env)
    assert out.returncode == 0, out.stderr[-3000:]
    return {'motor': motor['motor'], 'fea': fea,
            'html': json.loads(out.stdout)}


@needs_node
def test_fea_kiyasi_ayni_cidar_istasyonlari(fea_kosum):
    sa = fea_kosum['motor']['structural_analysis']
    k = fea_kosum['fea']['motor_station_comparison']
    harita = sa['safety_analysis']['safety_factors']
    # Kıyaslanan istasyonlar FEA ağının taşıdığı KAMARA cidarını
    # değerlendiren istasyonlardır; sayıları motorun kendi sayılarıdır.
    assert set(k['stations_compared']) <= {'chamber_hoop', 'chamber_von_mises'}
    assert k['stations_compared'], 'kamara uzantısı ağda değil mi?'
    for st in k['stations_compared']:
        assert k['station_safety_factors'][st] == harita[st]
    assert k['motor_min_safety_factor'] == min(
        harita[st] for st in k['stations_compared'])
    # Köprünün eski kıyas sayısı (kamara çember kesiti) ile aynı tanım.
    assert k['motor_min_safety_factor'] == pytest.approx(
        sa['chamber_analysis']['hoop_safety_factor'])
    # Manşet asgarisi ve istasyonları yanında, adlı nedenle.
    assert k['motor_headline_min_safety_factor'] == \
        sa['safety_analysis']['minimum_safety_factor']
    assert k['motor_headline_governing_stations'] == \
        sa['safety_analysis']['binding_safety_factors']
    for st in k['motor_headline_governing_stations']:
        if st not in k['stations_compared']:
            assert k['stations_outside_reasons'][st]
    assert k['fea_min_safety_factor'] == pytest.approx(
        fea_kosum['fea']['scalars']['min_safety_factor'])


@needs_node
@pytest.mark.parametrize('lang', ['tr', 'en'])
def test_fea_rozeti_istasyonu_adiyla_soyler(fea_kosum, lang):
    h = _duz(fea_kosum['html'][lang])
    k = fea_kosum['fea']['motor_station_comparison']
    sayi = '%.2f' % k['motor_min_safety_factor']
    manset = '%.2f' % k['motor_headline_min_safety_factor']
    if lang == 'tr':
        assert 'MOTORUN KENDİ EMNİYET KATSAYISI' in h
        assert 'istasyon: kamara çevresel gerilmesi' in h, h
        assert 'PERFORMANS ÖZETİ ASGARİSİ' in h, h
        assert 'nozul' in h and 'uç kapak' in h
        # Yarı İngilizce kalıntı yok.
        for yasak in ('nodal/SPR field', 'DERATE', 'derate'):
            assert yasak not in h, yasak
    else:
        assert 'ENGINE’S OWN SAFETY FACTOR' in h or \
            'ENGINE’S OWN SAFETY FACTOR' in h
        assert 'station: chamber hoop stress' in h, h
        assert 'PERFORMANCE SUMMARY MINIMUM' in h
    for s_ in (sayi, manset):
        assert s_ in h or s_.replace('.', ',') in h, (s_, h)


# ---------------------------------------------------------------------------
# NR-4 — Basınçlı Kap Özeti: kullanıcı etiketleri, virgüllü ondalık,
# geliştirici notu yok (API'de alan adları aynen)
# ---------------------------------------------------------------------------
def _kap_bolumu(h, lang):
    bas = 'Basınçlı Kap Özeti' if lang == 'tr' else 'Pressure Vessel Summary'
    son = 'Mevzuat uygunluğu' if lang == 'tr' else 'Regulatory compliance'
    d = _duz(h)
    i, j = d.find(bas), d.find(son)
    assert i >= 0 and j > i, 'basınçlı kap bölümü bulunamadı'
    return d[i:j]


def _detaysiz(h):
    """Kapalı "Teknik ayrıntı" gövdeleri ayıklanmış HTML (görünen ekran)."""
    return re.sub(r'<details\b.*?</details>', ' ', h, flags=re.S)


@needs_node
@pytest.mark.parametrize('mt', sorted(ORNEK))
@pytest.mark.parametrize('lang', ['tr', 'en'])
def test_basincli_kap_ozeti_kullanici_dilinde(kosum, mt, lang):
    h = kosum['html'][mt + ':' + lang]
    gorunen = _kap_bolumu(_detaysiz(h), lang)
    # Ham alan adları ve geliştirici notları görünen ekranda yok.
    for ham in ('safety_devices_required[', 'inner_diameter_mm',
                'wall_thickness_mm', 'actual_burst_pressure_bar',
                'actual_burst_pressure_basis', 'design_pressure_basis',
                'burst_margin_vs_meop', 'vessel_status', 'historical',
                'existing consumers', 'same key name',
                'compliance.disclaimer_code', 'disclaimer_code',
                'warn.safety.compliance_not_evaluated',
                'overall_risk_score_is_partial', 'risk_level_is_partial'):
        assert ham not in gorunen, (ham, gorunen[:400])
    ps = kosum['yanit'][mt]['safety_analysis']['pressure_safety']
    if lang == 'tr':
        for ing in ('MEDIUM PRESSURE', 'LOW PRESSURE', 'HIGH PRESSURE',
                    '-year visual', 'Annual visual'):
            assert ing not in gorunen, ing
        # TR virgüllü ondalık: işletme basıncı ve öngörülen patlama basıncı.
        for v in (ps['operating_pressure_bar'],
                  ps['actual_burst_pressure_bar']):
            assert ('%.1f' % v).replace('.', ',') + ' bar' in gorunen, (
                v, gorunen[:300])
            assert ('%.1f' % v) + ' bar' not in gorunen
        assert 'Öngörülen patlama basıncı' in gorunen  # z5i18n: kap paneliyle tek karşılık
        assert 'model tahmini, ölçülmüş dayanım değil' in gorunen
    else:
        assert 'Predicted burst pressure' in gorunen
    # Sözleşme: API alan adları değişmedi.
    for alan in ('actual_burst_pressure_bar', 'predicted_burst_pressure_bar',
                 'actual_burst_pressure_basis', 'design_pressure_basis',
                 'inner_diameter_mm', 'wall_thickness_mm',
                 'safety_devices_required', 'vessel_classification',
                 'inspection_requirements'):
        assert alan in ps, alan
    b = ps['actual_burst_pressure_basis']
    assert 'historical' not in b and 'existing consumers' not in b
    assert 'MODEL PREDICTION' in b


# ---------------------------------------------------------------------------
# G3-N1 — Termal FEA: izin verilen sıcaklık yokken "the allowable — K" yok
# ---------------------------------------------------------------------------
G3_HARNESS = r"""
const fs = require('fs'), path = require('path'), vm = require('vm');
const [staticDir] = JSON.parse(process.env.HRMA_ARGS);
const out = {};
function El(t) { this.style = {}; this.innerHTML = ''; this.children = []; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function () {}; El.prototype.getAttribute = function () { return null; };
El.prototype.querySelectorAll = function () { return []; }; El.prototype.addEventListener = function () {};
for (const lang of ['tr', 'en']) {
  const doc = { readyState: 'complete', documentElement: { setAttribute() {}, lang: lang },
    head: new El(), body: new El(), createElement: () => new El(), querySelector: () => null,
    querySelectorAll: () => [], getElementById: () => null, addEventListener() {} };
  const sb = { console: { log() {}, warn() {}, error() {} }, setTimeout, clearTimeout,
    setInterval, clearInterval, fetch: () => Promise.reject(new Error('ag yok')),
    JSON, Math, Number, Array, Object, String, Boolean, RegExp, Date, Error, isFinite, isNaN,
    parseFloat, parseInt, encodeURIComponent, document: doc };
  sb.window = sb; sb.globalThis = sb; sb.self = sb; sb.localStorage = null;
  vm.createContext(sb);
  const run = f => vm.runInContext(fs.readFileSync(path.join(staticDir, f), 'utf8'), sb, { filename: f });
  for (const f of ['i18n.js', 'i18n_common.js', 'i18n_charts.js']) run(f);
  sb.I18N.setLang(lang);
  run('analysis_dock.js'); run('units_constants.js'); run('thermal_fea_panel.js');
  const B = sb.window.ThermalFeaPanel._withheldBadge;
  const neden = { verdict_withheld: true,
    verdict_withheld_reasons: ['numerical_convergence_not_achieved'] };
  out[lang] = {
    izinli: B(Object.assign({ allowable_temperature_K: 1143, melting_point_K: 1673 }, neden)),
    yalniz_erime: B(Object.assign({ allowable_temperature_K: null, melting_point_K: 1673 }, neden)),
    hicbiri: B(Object.assign({ allowable_temperature_K: null, melting_point_K: null }, neden)),
  };
}
process.stdout.write(JSON.stringify(out));
"""


@needs_node
def test_g3n1_izin_yokken_bos_izin_cumlesi_basilmaz():
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, HRMA_ARGS=json.dumps([str(JS)]))
        out = subprocess.run([NODE, '-'], input=G3_HARNESS,
                             capture_output=True, text=True, timeout=120,
                             env=env, cwd=tmp)
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout)
    for lang in ('tr', 'en'):
        for durum in ('yalniz_erime', 'hicbiri'):
            m = _duz(r[lang][durum])
            assert not re.search(r'—\s*K\b', m), (lang, durum, m)
            assert 'allowable' not in m.replace('no allowable', '') or \
                lang == 'tr', m
        erime = _duz(r[lang]['yalniz_erime'])
        assert '1673 K' in erime
        assert ('erime sıcaklığı 1673 K' if lang == 'tr'
                else 'melting point 1673 K') in erime, erime
        assert ('yalnız bilgi için' if lang == 'tr'
                else 'for information only') in erime
        # İzin verilen sıcaklık varken cümle aynen (bit-aynı yol).
        izinli = _duz(r[lang]['izinli'])
        assert '1143 K' in izinli
