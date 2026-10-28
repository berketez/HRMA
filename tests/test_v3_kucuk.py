"""V3 KK bekçileri (14 Eki 2026).

Görev 1 — termal izin sıcaklığı (KAB devri 5, karar §28-31 tek izin basamağı).
ÖLÇÜLDÜ (main fe18664e, ``/analyze_thermal_safety``, örnek katı dock gövdesi):
'steel' için aynı yanıtta ``material_properties.allowable_temperature`` 1073 K
ile ``safety_analysis.threshold_ladder.allowable_K`` 811 K; 'ss_304'te ikisi de
1073 K. İkisi AYNI büyüklük değildir: birincisi malzeme kaydının ısıl izin
ADAYI, ikincisi hükmü veren basamak = min(allowable_temperature,
max_service_temp). Basamak hangi adaydan geldiğini söylemiyordu; artık
adayları ve hükmü vereni ADIYLA yayımlar (yanıt + panel, EN = TR). Hüküm ve
sayılar DEĞİŞMEZ (yalnız yeni yapraklar).

Görev 2 — dock yapısal paneli motorun tasarım SF hedefini taşır (YP7 devri).
ÖLÇÜLDÜ (aynı main, örnek sıvı): motor hedefi 2,5, dock ucu malzeme
varsayılanı 3,0 (``design_safety_factor_source = materials_database_default``)
ile notluyordu. Güverte yükü artık motorun KENDİ hedefini taşır; motor
yayımlamıyorsa alan boş kalır, uç malzeme varsayılanını kullanır ve bunu
yanıtta + panelde ADIYLA beyan eder.
"""

import json
import math
import os
import pathlib
import re
import shutil
import subprocess

import pytest

from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM

from hrma.data import materials_db as mdb

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')
H = {'Host': '127.0.0.1:8080'}
_HARNESS = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'P11' / 'B4-repro-03.js'
_THERMAL_JS = 'hrma/static/js/panels/thermal_panel.js'
_STRUCT_JS = 'hrma/static/js/panels/structural_panel.js'
_I18N_COMMON = REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_common.js'

#: Örnek katı dock termal gövdesi (KAB ölçümü docs/kabul/kanit_2026-10-14/
#: dock.json 'ornek_kati'.thermal.yuk; malzeme parametreli).
_TERMAL_GOVDE = {'chamber_pressure': 40.0, 'chamber_temperature': 1713.1,
                 'chamber_diameter': 0.081, 'chamber_length': 0.464,
                 'burn_time': 2.2771563941946757,
                 'mdot_total': 1.0568746594202951, 'wall_thickness': 0.002,
                 'cooling_type': 'natural'}
_MALZEMELER = ('steel', 'ss_304', 'steel_4130', 'copper', 'inconel_718')
_ADAY_ALANLARI = ('allowable_temperature', 'max_service_temp')
_YENI_ALANLAR = ('allowable_governed_by', 'allowable_candidates_K',
                 'allowable_governance_basis')


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('kk_projeler')))
    from hrma.app import app
    return app.test_client()


def _termal(client, malzeme):
    r = client.post('/analyze_thermal_safety',
                    json=dict(_TERMAL_GOVDE, material=malzeme), headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _kayit_adaylari(malzeme):
    """Bağımsız kâhin: materials_db kaydının iki aday alanı (yanıttan değil)."""
    rec = mdb.get_material(malzeme)
    return {a: float(rec[a]) for a in _ADAY_ALANLARI
            if isinstance(rec.get(a), (int, float))
            and math.isfinite(float(rec[a])) and float(rec[a]) > 0}


# ---------------------------------------------------------------------------
# Görev 1 — yanıt
# ---------------------------------------------------------------------------
class TestTermalIzinAdaylari:

    @pytest.mark.parametrize('malzeme', _MALZEMELER)
    def test_basamak_hukmu_vereni_adiyla_yayimlar(self, client, malzeme):
        ta = _termal(client, malzeme)['thermal_analysis']
        kahin = _kayit_adaylari(malzeme)
        assert kahin, malzeme
        en_siki = min(kahin, key=lambda a: kahin[a])
        for blok in (ta['safety_analysis']['threshold_ladder'],
                     ta['gas_side_analysis']['threshold_ladder']):
            assert blok['allowable_candidates_K'] == kahin
            assert blok['allowable_governed_by'] == en_siki
            assert blok['allowable_K'] == kahin[en_siki]
            assert 'GOVERNING' in blok['allowable_governance_basis']
        # Ham kayıt yankısı aynen durur (aday; hükmü veren değil).
        mp = ta['material_properties']
        assert float(mp['allowable_temperature']) == kahin[
            'allowable_temperature']

    def test_steel_olculen_vaka(self, client):
        """KAB devri 5 vakası: 1073 K aday, 811 K (max_service_temp) hüküm."""
        ta = _termal(client, 'steel')['thermal_analysis']
        tl = ta['safety_analysis']['threshold_ladder']
        assert ta['material_properties']['allowable_temperature'] == 1073
        assert tl['allowable_K'] == 811.0
        assert tl['allowable_governed_by'] == 'max_service_temp'
        assert tl['allowable_candidates_K'] == {
            'allowable_temperature': 1073.0, 'max_service_temp': 811.0}

    @pytest.mark.parametrize('malzeme', ('steel', 'ss_304'))
    def test_yalniz_yeni_yapraklar_eklenir(self, client, malzeme,
                                           monkeypatch):
        """Hüküm ve sayılar DEĞİŞMEZ: künye kapalıyken yanıt, künyeli
        yanıttan yalnız üç yeni alan çıkarılmış hâliyle bit-aynı."""
        import hrma.analysis.heat_transfer_analysis as hta
        yeni = _termal(client, malzeme)
        monkeypatch.setattr(hta, 'allowable_governance', lambda limits: {})
        eski = _termal(client, malzeme)
        ta = yeni['thermal_analysis']
        for blok in (ta['safety_analysis']['threshold_ladder'],
                     ta['gas_side_analysis']['threshold_ladder']):
            for alan in _YENI_ALANLAR:
                assert alan in blok
                del blok[alan]
        for g in (yeni, eski):
            g.pop('timestamp', None)
        assert json.dumps(yeni, sort_keys=True, default=str) == json.dumps(
            eski, sort_keys=True, default=str)

    def test_aday_yoksa_uydurulmaz(self):
        from hrma.analysis.heat_transfer_analysis import allowable_governance
        k = allowable_governance({'source_fields': {
            'allowable_K': None, 'allowable_candidates_K': {}}})
        assert k['allowable_governed_by'] is None
        assert k['allowable_candidates_K'] == {}
        assert allowable_governance(None)['allowable_governed_by'] is None


# ---------------------------------------------------------------------------
# Görev 1 — panel
# ---------------------------------------------------------------------------
def _termal_panel(govde):
    from tests.support.kanit import kanit_gerekli
    cfg = {'panelId': 'thermal', 'dataInline': govde,
           'panelFiles': [_THERMAL_JS]}
    p = subprocess.run([NODE, str(kanit_gerekli(str(_HARNESS)))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       cwd=str(REPO_ROOT), timeout=300)
    assert p.returncode == 0, p.stderr[-2000:]
    o = json.loads(p.stdout)
    assert not o.get('error'), o.get('error')
    return ' '.join(re.sub(r'<[^>]*>', ' ', o['html'] or '').split())


@needs_node
class TestTermalPanelHukmuVeren:

    def test_steel_iki_aday_adiyla(self, client):
        m = _termal_panel(_termal(client, 'steel'))
        assert '811 K allowable' in m
        assert ('Governing temperature limit structural service limit '
                '(max_service_temp) = 811 K gives the verdict · material '
                'allowable temperature (allowable_temperature) = 1073 K '
                'does not') in m
        assert '1073 K allowable' not in m

    def test_ss304_hukmu_veren_malzeme_izni(self, client):
        m = _termal_panel(_termal(client, 'ss_304'))
        assert ('material allowable temperature (allowable_temperature) = '
                '1073 K gives the verdict · structural service limit '
                '(max_service_temp) = 1143 K does not') in m

    def test_esit_adaylar(self, client):
        m = _termal_panel(_termal(client, 'inconel_718'))
        assert 'are both 977 K; that limit gives the verdict' in m

    @pytest.mark.parametrize('bozma', ('yok', 'bilinmeyen_ad', 'sayi_uyusmaz'))
    def test_kunye_yoksa_satir_basilmaz(self, client, bozma):
        g = _termal(client, 'steel')
        tl = g['thermal_analysis']['safety_analysis']['threshold_ladder']
        if bozma == 'yok':
            for alan in _YENI_ALANLAR:
                tl.pop(alan)
        elif bozma == 'bilinmeyen_ad':
            tl['allowable_governed_by'] = '<b>x</b>'
        else:
            tl['allowable_candidates_K']['max_service_temp'] = 999.0
        m = _termal_panel(g)
        assert 'Governing temperature limit' not in m
        assert '811 K allowable' in m


# ---------------------------------------------------------------------------
# Görev 2 — dock yapısal paneli: motorun tasarım SF hedefi
# ---------------------------------------------------------------------------
_DOCK_EV = (
    "var spec = window.AnalysisDock._registry.filter(function (s) {"
    "  return s.id === 'structural'; })[0];"
    "try { window.AnalysisDock.init({motorType: body.motorType,"
    "  resultsProvider: function () { return body.motor; }}); } catch (e) {}"
    "var sug = spec.fromResults(body.motor);"
    "var out = {suggested: sug, html: null, fields: spec.fields};"
    "if (body.endpoint) { var root = document.createElement('div');"
    "  spec.render(body.endpoint, root); out.html = root.innerHTML; }"
    "return out;")
#: Motor yanıtındaki hedef alanının yolu (bağımsız kâhin: motorun
#: kendi yayımı; panelin okuma yolundan değil, Python'da doğrudan okunur).
_HEDEF_YOLU = {
    'hybrid': ('motor', 'structural_analysis', 'chamber_analysis',
               'design_safety_factor_target'),
    'solid': ('structural_analysis', 'case_analysis', 'design_safety_factor'),
    'liquid': ('structural_analysis', 'chamber_structure', 'safety_factor'),
}


def _guvenli(o):
    s = json.dumps(o, default=str)
    return json.loads(s.replace('-Infinity', 'null').replace(
        'Infinity', 'null').replace('NaN', 'null'))


def _al(d, yol):
    for p in yol:
        d = d[p]
    return d


@pytest.fixture(scope='module')
def ornek_motorlar(client):
    from tests.test_example_projects import HEADERS, NAMES, calculate_payload
    out = {}
    for tur in ('hybrid', 'solid', 'liquid'):
        with open(REPO_ROOT / 'examples' / (NAMES[tur] + '.hrma'),
                  encoding='utf-8') as f:
            fields = json.load(f)['inputs']['fields']
        if tur == 'hybrid':
            r = client.post('/calculate', json=calculate_payload(tur, fields),
                            headers=HEADERS)
        elif tur == 'solid':
            r = client.post('/calculate_solid',
                            json=calculate_payload(tur, fields),
                            headers=HEADERS)
        else:
            r = client.post('/calculate_liquid',
                            json=calculate_payload(tur, fields),
                            headers=HEADERS)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        out[tur] = _guvenli(r.get_json())
    return out


def _dock_node(tur, motor, endpoint=None):
    from tests.support.kanit import kanit_gerekli
    cfg = {'panelId': '_yok', 'panelFiles': [_STRUCT_JS],
           'dataInline': {'motorType': tur, 'motor': motor,
                          'endpoint': endpoint},
           'evalFn': _DOCK_EV}
    p = subprocess.run([NODE, kanit_gerekli(str(_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       cwd=str(REPO_ROOT), timeout=240)
    assert p.returncode == 0, p.stderr[-2000:]
    ev = json.loads(p.stdout)['evaled']
    assert not ev.get('_err'), ev.get('_err')
    return ev


def _dock_yuku(fields, sug):
    """analysis_dock.js buildPayload: seçici değeri + yalnız sonlu sayılar."""
    out = {}
    for f in fields:
        k, var = f[0], f[2]
        v = sug.get(k) if sug.get(k) is not None else var
        if isinstance(f[3], list) or k == 'material':
            out[k] = v
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            out[k] = x
    return out


def _dock_akisi(client, tur, motor):
    ev = _dock_node(tur, motor)
    yuk = _dock_yuku(ev['fields'], ev['suggested'])
    r = client.post('/analyze_structural_safety', json=yuk, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    uc = _guvenli(r.get_json())
    html = _dock_node(tur, motor, uc)['html'] or ''
    return {'sug': ev['suggested'], 'yuk': yuk, 'uc': uc,
            'metin': ' '.join(re.sub(r'<[^>]*>', ' ', html).split())}


def _dta(uc):
    return uc['structural_analysis']['safety_analysis'][
        'design_target_assessment']


@needs_node
class TestDockMotorSfHedefi:

    @pytest.mark.parametrize('tur', ('hybrid', 'solid', 'liquid'))
    def test_hedef_tasinir_ve_adiyla_beyan(self, client, ornek_motorlar, tur):
        motor = ornek_motorlar[tur]
        hedef = _al(motor, _HEDEF_YOLU[tur])
        assert isinstance(hedef, float) and hedef > 0, (tur, hedef)
        d = _dock_akisi(client, tur, motor)
        assert d['sug']['safety_factor'] == hedef
        assert d['yuk']['safety_factor'] == hedef
        assert _dta(d['uc'])['design_safety_factor_target'] == hedef
        assert d['uc']['design_basis']['design_safety_factor_source'] == (
            'user_supplied')
        yol = 'motor.' + '.'.join(p for p in _HEDEF_YOLU[tur] if p != 'motor')
        assert f'source: motor design target ({yol})' in d['metin']
        assert 'material database default' not in d['metin']

    def test_sivi_olculen_vaka(self, client, ornek_motorlar):
        """YP7 devri: örnek sıvı hedefi 2,5; dock eskiden 3,0 notluyordu.

        V3.0.5 (28 Eki, A1): hedef girdiden AYNEN taşınır (tam eşitlik
        kalır). ``target_derived_minimum_safety_factor`` ise bir girdi
        değil, HRMA'nın hedefe göre boyutlandırdığı istasyonların (kapak,
        lüle) kendi geometrisinden YENİDEN HESAPLANAN emniyet katsayısıdır.
        Ürün bu sayıyı hedefle 1e-9 bağıl bant içinde "hedefi geri okuyor"
        diye sınıflar (``structural_analysis``: deger >= hedef·(1 − 1e-9)).
        ÖLÇÜLDÜ (RAPOR A1 §6): örnek sıvı gerçek sayfa gövdesiyle yeniden
        üretildikten sonra (V301/ÖRNEK 5fa435893) kapak 2,4999999999999996
        çıkıyor (1 ulp, bağıl 1,8e-16; eski örnek bugünkü kodla tam 2,5).
        Ekranda 2.50 basılıyor. Bu bir kayan nokta artığıdır, gerileme
        değildir. Sayı hedefe "yuvarlanıp" yayımlanmaz, çünkü hesaplanan
        değerdir. Kıyas: bağıl 1e-12 (ürünün kendi bandının bin kat
        içi)."""
        d = _dock_akisi(client, 'liquid', ornek_motorlar['liquid'])
        dta = _dta(d['uc'])
        assert dta['design_safety_factor_target'] == 2.5
        assert dta['target_derived_minimum_safety_factor'] == pytest.approx(
            2.5, rel=1e-12)

    @pytest.mark.parametrize('tur', ('hybrid', 'solid', 'liquid'))
    def test_hedef_yoksa_malzeme_varsayilani_adiyla(self, client,
                                                    ornek_motorlar, tur):
        motor = json.loads(json.dumps(ornek_motorlar[tur]))
        yol = _HEDEF_YOLU[tur]
        del _al(motor, yol[:-1])[yol[-1]]
        d = _dock_akisi(client, tur, motor)
        assert d['sug'].get('safety_factor') is None
        assert d['sug']['__withheld']['safety_factor'] == (
            'motor_published_no_design_safety_factor_target')
        assert 'safety_factor' not in d['yuk']
        assert d['uc']['design_basis']['design_safety_factor_source'] == (
            'materials_database_default')
        kahin = float(mdb.get_material(d['yuk']['material'])['safety_factor'])
        assert _dta(d['uc'])['design_safety_factor_target'] == kahin
        assert ('source: material database default (the motor result '
                'published no design safety factor target)') in d['metin']

    def test_sivi_kunyesiz_safety_factor_okunmaz(self, client,
                                                 ornek_motorlar):
        """Sıvının alan adı ``safety_factor`` tek başına belirsiz: hedefin
        künyesi (safety_factor_source) yoksa taşınmaz (fail-closed)."""
        motor = json.loads(json.dumps(ornek_motorlar['liquid']))
        del motor['structural_analysis']['chamber_structure'][
            'safety_factor_source']
        ev = _dock_node('liquid', motor)
        assert ev['suggested'].get('safety_factor') is None

    def test_panelde_elle_girilen_deger(self, client, ornek_motorlar):
        """Kullanıcı alanı değiştirdiyse kaynak 'motor hedefi' denmez."""
        motor = ornek_motorlar['liquid']
        ev = _dock_node('liquid', motor)
        yuk = _dock_yuku(ev['fields'], ev['suggested'])
        yuk['safety_factor'] = 3.5
        r = client.post('/analyze_structural_safety', json=yuk, headers=H)
        assert r.status_code == 200
        html = _dock_node('liquid', motor, _guvenli(r.get_json()))['html']
        m = ' '.join(re.sub(r'<[^>]*>', ' ', html or '').split())
        assert 'source: value entered in this panel' in m
        assert 'source: motor design target' not in m


# ---------------------------------------------------------------------------
# i18n: yeni anahtarlar EN = TR (ikisinde de var, TR metin Türkçe)
# ---------------------------------------------------------------------------
_YENI_ANAHTARLAR = (
    'panel.thermal.governingLimit', 'panel.thermal.governingLimitValue',
    'panel.thermal.governingLimitEqual', 'panel.thermal.governingLimitSingle',
    'panel.thermal.limitNameService', 'panel.thermal.limitNameAllowable',
    'common.f.designSafetyFactorTarget',
    'panel.structural.sfTargetMaterialDefault',
    'panel.structural.sfTargetFromMotor', 'panel.structural.sfTargetPanel')


@pytest.mark.parametrize('anahtar', _YENI_ANAHTARLAR)
def test_yeni_i18n_anahtari_en_tr(anahtar):
    metin = _I18N_COMMON.read_text(encoding='utf-8')
    satirlar = re.findall(r"'" + re.escape(anahtar) + r"': '([^']*)'", metin)
    assert len(satirlar) == 2, (anahtar, satirlar)
    en, tr = satirlar
    assert en != tr
    assert re.search('[çğıİöşüÇĞÖŞÜ]', tr), tr
    yer_en = sorted(re.findall(r'\{(\w+)\}', en))
    assert yer_en == sorted(re.findall(r'\{(\w+)\}', tr)), anahtar


# ===========================================================================
# 2. TUR (14 Eki 2026) — geç devirler: UPL, REL D-5, B11G, CFDS, FY, SO1 D-2
# ===========================================================================
_IMPORT_UI_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'import_ui.js'
_VALIDATION_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'panels' / 'validation_panel.js'
_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
_MB = 1024 * 1024


def _node_json(betik, girdi, timeout=240):
    """Betiği node'a stdin ile ver (argv DEĞİL: E2BIG), JSON çıktıyı oku."""
    kod = 'const girdi = JSON.parse(' + json.dumps(json.dumps(girdi)) + ');\n'
    p = subprocess.run([NODE, '-'], input=kod + betik, capture_output=True,
                       text=True, timeout=timeout, cwd=str(REPO_ROOT))
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


# ---------------------------------------------------------------------------
# Görev 1 — UPL devri: validation_panel seçili motoru yeniden karşılaştırma
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (dal tabanı 1b4bbff7): ``recompareSelectedMotor`` gövdeyi ön
# denetimsiz gönderiyordu ve sunucu 413'ü düz metin dönünce durum satırına
# HİÇBİR ileti yazılmıyordu (``data`` null → ileti koşulu düşüyor). Kâhin:
# ``imp.tooLarge`` iletisinin İngilizce yedek metni + sunucunun tavanı
# (``REQUEST_BODY_MAX_BYTES``) + gövde baytının Python'da bağımsız sayımı.
_UPL_KOSUCU = r"""
const vm = require('vm');
function El(id) { this.id = id || ''; this.style = {}; this.children = [];
  this.dinleyici = {}; this.value = ''; this.textContent = ''; this.innerHTML = '';
  this.disabled = false; this.oz = {}; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { return c; };
El.prototype.setAttribute = function (k, v) { this.oz[k] = v; };
El.prototype.getAttribute = function (k) { return k in this.oz ? this.oz[k] : null; };
El.prototype.addEventListener = function (t, f) { (this.dinleyici[t] = this.dinleyici[t] || []).push(f); };
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.remove = function () {}; El.prototype.removeChild = function () {};
Object.defineProperty(El.prototype, 'firstElementChild', { get() { return new El(); } });
const byId = new Map();
for (const id of girdi.idler) byId.set(id, new El(id));
const meta = new El('meta'); meta.setAttribute('content', girdi.meta);
const kayit = { fetch: [] };
const yanitlar = girdi.yanitlar.slice();
const document = { readyState: 'complete', body: new El('body'),
  createElement() { return new El(); }, getElementById(id) { return byId.get(id) || null; },
  querySelector(s) { return s === 'meta[name="hrma-upload-limits"]' ? meta : null; },
  addEventListener() {} };
async function fetch(url, opt) {
  kayit.fetch.push({ url: url, bayt: opt && typeof opt.body === 'string' ? Buffer.byteLength(opt.body) : null });
  const y = yanitlar.shift();
  return { status: y.status, ok: y.status >= 200 && y.status < 300,
    async json() { if (y.json === null) throw new SyntaxError('Unexpected token R'); return y.json; },
    async text() { return y.metin || ''; } };
}
const TF = (k, p, fb) => String(fb).replace(/\{(\w+)\}/g, (w, n) =>
  (p && Object.prototype.hasOwnProperty.call(p, n)) ? String(p[n]) : w);
const U = new Proxy({ t: (k, fb) => fb, tf: TF, motorDict() { return null; },
  esc: (s) => String(s), fmt: (v) => String(v) }, { get(o, k) { return k in o ? o[k] : () => ''; } });
const ctx = { document, fetch, Blob, console: { error() {}, warn() {}, log() {} },
  setTimeout, clearTimeout, setInterval, clearInterval, location: { pathname: '/solid' },
  FileReader: function () {}, FormData: function () {} };
ctx.window = ctx;
ctx.AnalysisDock = { register() {}, ui: U };
vm.createContext(ctx);
for (const k of girdi.betikler) vm.runInContext(k.kaynak, ctx, { filename: k.ad });
(async () => {
  const n = girdi.satir;
  const time = new Array(n), thrust = new Array(n);
  for (let i = 0; i < n; i++) { time[i] = i; thrust[i] = 1; }
  const motor = { time: time, thrust: thrust, meta: { name: 'M' }, warnings: [] };
  await ctx.ValidationPanel._importMotorFile('x', 't.eng');
  const dur1 = byId.get('ad_status_validation').textContent;
  // içe aktarma yanıtı motorları taşıdı; yeniden karşılaştırma seçili motorla
  girdi.motorlar = null;
  await ctx.ValidationPanel._recompareSelectedMotor();
  process.stdout.write(JSON.stringify({ fetch: kayit.fetch,
    durum: byId.get('ad_status_validation').textContent, ilk: dur1 }));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""
_UPL_IDLER = ['ad_sec_validation', 'ad_status_validation', 'vp_run',
              'vp_csv_file', 'vp_csv_text', 'ad_root_validation', 'vp_motor_bar',
              'vp_pred_source']


def _upl_meta(client):
    r = client.get('/solid', headers=H)
    assert r.status_code == 200
    import html as _html
    m = re.findall(r"""<meta name="hrma-upload-limits" content='([^']*)'>""",
                   r.get_data(as_text=True))
    assert len(m) == 1, m
    return _html.unescape(m[0])


def _upl_govde_bayti(satir):
    """Kâhin: csvFromCurve biçimi (``time,thrust`` + ``i,1`` satırları) ve
    JSON.stringify gövdesinin UTF-8 bayt sayısı — Python'da bağımsız."""
    csv = 'time,thrust\n' + '\n'.join('%d,1' % i for i in range(satir))
    return len(json.dumps({'csv_text': csv}, separators=(',', ':')).encode())


def _upl_kos(client, satir, ikinci_yanit):
    motor = {'time': list(range(3)), 'thrust': [1, 1, 1],
             'meta': {'name': 'M'}, 'warnings': []}
    ice_aktarma = {'status': 200, 'json': {
        'status': 'success', 'motors': [motor], 'motor': motor,
        'comparison': None, 'selected_index': 0, 'warnings': []}}
    girdi = {'idler': _UPL_IDLER, 'meta': _upl_meta(client), 'satir': satir,
             'yanitlar': [ice_aktarma, ikinci_yanit],
             'betikler': [{'ad': p.name, 'kaynak': p.read_text(encoding='utf-8')}
                          for p in (_IMPORT_UI_JS, _VALIDATION_JS)]}
    # Seçili motorun eğrisi node tarafında üretilir (büyük dizi stdin'e
    # girmesin): içe aktarma yanıtındaki motor, aynı uzunlukta eğriyle
    # değiştirilir.
    betik = _UPL_KOSUCU.replace(
        "await ctx.ValidationPanel._importMotorFile('x', 't.eng');",
        "girdi.yanitlar[0].json.motors[0].time = time;"
        " girdi.yanitlar[0].json.motors[0].thrust = thrust;"
        " yanitlar[0] = girdi.yanitlar[0];"
        " await ctx.ValidationPanel._importMotorFile('x', 't.eng');")
    return _node_json(betik, girdi)


def _upl_ileti(bayt, tavan):
    boyut = '%.1f' % (-(-bayt * 10 // _MB) / 10)
    return ('Upload too large: %s MB; the limit for this upload is %d MB.'
            % (boyut, tavan // _MB))


@needs_node
class TestUplYenidenKarsilastirma:

    def test_tavani_asan_govde_gonderilmez_ileti_basilir(self, client):
        from hrma.security.body_limit import REQUEST_BODY_MAX_BYTES as tavan
        satir = 4_000_000
        bayt = _upl_govde_bayti(satir)
        assert bayt > tavan, 'ön koşul: gövde tavanı aşmalı'
        s = _upl_kos(client, satir, {'status': 200, 'json': {}})
        # Yalnız içe aktarma isteği gitti; yeniden karşılaştırma gitmedi.
        assert [f['url'] for f in s['fetch']] == ['/api/import/motor-file'], s['fetch']
        assert s['durum'] == 'ERROR: ' + _upl_ileti(bayt, tavan), s['durum']

    @pytest.mark.parametrize('yanit', [
        {'status': 413, 'json': None,
         'metin': 'Request Entity Too Large\n\n(generated by waitress)'},
        {'status': 413, 'json': {'status': 'error',
                                 'error': 'request_body_too_large',
                                 'limit': 'body_bytes'}}],
        ids=['waitress_duz_metin', 'json_govde_kapisi'])
    def test_sunucu_413_ayni_ileti_ham_govde_yok(self, client, yanit):
        from hrma.security.body_limit import REQUEST_BODY_MAX_BYTES as tavan
        satir = 3
        s = _upl_kos(client, satir, yanit)
        assert [f['url'] for f in s['fetch']] == [
            '/api/import/motor-file', '/api/validation/upload-csv'], s['fetch']
        bayt = _upl_govde_bayti(satir)
        assert s['fetch'][1]['bayt'] == bayt
        assert s['durum'] == 'ERROR: ' + _upl_ileti(bayt, tavan), s['durum']
        for ham in ('waitress', 'request_body_too_large'):
            assert ham not in s['durum']

    def test_govdesiz_hata_http_kodu_basilir(self, client):
        s = _upl_kos(client, 3, {'status': 502, 'json': None, 'metin': '<h1>x</h1>'})
        assert s['durum'] == 'ERROR: HTTP 502', s['durum']

    def test_basarili_yeniden_karsilastirma_degismedi(self, client):
        """Tavan altı + 200: durum satırı temizlenir (eski davranış)."""
        s = _upl_kos(client, 3, {'status': 200, 'json': {
            'status': 'success', 'comparison': None}})
        assert len(s['fetch']) == 2 and s['durum'] == '', s


# ---------------------------------------------------------------------------
# Görev 2 — REL D-5: proje yükleme uyarısı makine kodu + parametre
# ---------------------------------------------------------------------------
_PROJE_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'project_bar.js'
_PROJE_KOSUCU = r"""
const fs = require('fs'); const vm = require('vm');
const src = fs.readFileSync('hrma/static/js/project_bar.js', 'utf8');
function govde(ad) {
  const m = new RegExp('(?:async\\s+)?function\\s+' + ad + '\\s*\\(').exec(src);
  if (!m) throw new Error(ad + ' yok');
  let d = 0; const j = src.indexOf('{', m.index + m[0].length - 1);
  for (let k = j; k < src.length; k++) {
    if (src[k] === '{') d++;
    else if (src[k] === '}') { d--; if (!d) return src.slice(m.index, k + 1); }
  }
  throw new Error(ad + ' kapanmadı');
}
const kod = /var PROJE_UYARI_KODU = [^\n]+\n/.exec(src)[0];
async function kos(lang) {
  const sb = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout,
    setInterval, clearInterval, JSON, Object, Array, Math, RegExp, String, Number,
    Boolean, Date, Error, Promise, parseFloat, parseInt, isNaN, isFinite,
    encodeURIComponent };
  sb.window = sb; sb.self = sb; sb.localStorage = null;
  sb.document = { readyState: 'loading', documentElement: { setAttribute() {} },
    addEventListener() {}, querySelectorAll: () => [], querySelector: () => null,
    getElementById: () => null };
  vm.createContext(sb);
  for (const f of ['i18n.js', 'i18n_common.js', 'i18n_charts.js'])
    vm.runInContext(fs.readFileSync('hrma/static/js/' + f, 'utf8'), sb, { filename: f });
  sb.I18N.setLang(lang);
  sb.__girdi = girdi;
  vm.runInContext(
    'var state = {}; var motorType = "solid"; var TYPE_PATH = {solid: "/solid"};\n'
    + 'var location = { pathname: "/solid", href: "" };\n'
    + 'var history = { replaceState() {} };\n'
    + 'var __toast = []; function toast(m, k) { __toast.push([String(m), k]); }\n'
    + 'function applyProject() {} function renderBar() {}\n'
    + 'async function apiLoad() { return __girdi.yanit; }\n'
    + kod + ['T', 'TF', 'srv', 'yuklemeUyariKayitlari', 'yuklemeUyariMetni',
       'loadIntoPage'].map(govde).join('\n'),
    sb, { filename: 'project_bar_parca.js' });
  await vm.runInContext('loadIntoPage("eski")', sb);
  return sb.__toast;
}
(async () => {
  process.stdout.write(JSON.stringify({ tr: await kos('tr'), en: await kos('en') }));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""


@pytest.fixture
def proje_yaniti(tmp_path, monkeypatch):
    """Gerçek uçtan: kaydet → dosyada app_version eski + created_at yok → yükle."""
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(tmp_path))
    from hrma.app import app
    from tests.test_projects_api import make_payload
    c = app.test_client()
    r = c.post('/api/projects/save', json={'name': 'eski',
                                           'payload': make_payload()})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    yol = tmp_path / 'eski.hrma'
    doc = json.loads(yol.read_text(encoding='utf-8'))
    doc['app_version'] = '2.6.26'
    doc.pop('created_at')
    yol.write_text(json.dumps(doc), encoding='utf-8')
    r = c.get('/api/projects/load/eski')
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


class TestProjeYuklemeUyarisi:

    def test_duz_liste_eski_metinle_bayt_ayni(self, proje_yaniti):
        """Kâhin: değişiklik ÖNCESİ load_project'ın f-string biçimi (dal
        tabanı 1b4bbff7, projects.py:546-551) — geriye uyum."""
        from hrma import __version__ as surum
        assert proje_yaniti['warnings'] == [
            'Project was saved with app version 2.6.26; '
            'current version is %s' % surum,
            "Project file is missing the 'created_at' stamp"]

    def test_kayitlar_kod_parametre_birebir(self, proje_yaniti):
        from hrma import __version__ as surum
        assert proje_yaniti['warning_records'] == [
            {'code': 'warn.project.app_version_mismatch', 'severity': 'warning',
             'params': {'saved_version': '2.6.26', 'current_version': surum}},
            {'code': 'warn.project.missing_stamp', 'severity': 'warning',
             'params': {'stamp': 'created_at'}}]

    def test_i18n_en_sunucu_metniyle_ayni_tr_turkce(self, proje_yaniti):
        metin = _I18N_COMMON.read_text(encoding='utf-8')
        for kayit, duz in zip(proje_yaniti['warning_records'],
                              proje_yaniti['warnings']):
            bulunan = re.findall(r"""'%s': (['"])(.*?)\1,""" % re.escape(
                kayit['code']), metin)
            assert len(bulunan) == 2, (kayit['code'], bulunan)
            # JS dizgesindeki kaçışlı tırnak (\') çözülür
            en, tr = (bulunan[0][1].replace("\\'", "'"),
                      bulunan[1][1].replace("\\'", "'"))
            assert en.format(**kayit['params']) == duz, (en, duz)
            assert re.search('[çğıİöşüÇĞÖŞÜ]', tr), tr
            assert (sorted(re.findall(r'\{(\w+)\}', en))
                    == sorted(re.findall(r'\{(\w+)\}', tr)))

    @needs_node
    def test_arayuz_tr_kipte_turkce_en_kipte_sunucu_metni(self, proje_yaniti):
        from hrma import __version__ as surum
        o = _node_json(_PROJE_KOSUCU, {'yanit': proje_yaniti})
        tr = [m for m, k in o['tr'] if k == 'warn']
        en = [m for m, k in o['en'] if k == 'warn']
        assert tr[:2] == [
            'Proje 2.6.26 uygulama sürümüyle kaydedilmiş; geçerli sürüm %s'
            % surum,
            "Proje dosyasında 'created_at' damgası yok"], tr
        assert en[:2] == proje_yaniti['warnings'], en

    @needs_node
    @pytest.mark.parametrize('bozma', ['eksik_kayit', 'bilinmeyen_kod',
                                       'nesne_parametre', 'kayit_yok'])
    def test_bozuk_kayitta_sunucu_metni_aynen(self, proje_yaniti, bozma):
        y = json.loads(json.dumps(proje_yaniti))
        if bozma == 'eksik_kayit':
            y['warning_records'] = y['warning_records'][:1]
        elif bozma == 'bilinmeyen_kod':
            y['warning_records'][0]['code'] = 'warn.liquid.turbine_pr_inconsistent'
        elif bozma == 'nesne_parametre':
            y['warning_records'][0]['params']['saved_version'] = {'x': 1}
        else:
            y.pop('warning_records')
        o = _node_json(_PROJE_KOSUCU, {'yanit': y})
        tr = [m for m, k in o['tr'] if k == 'warn']
        if bozma == 'eksik_kayit' or bozma == 'kayit_yok':
            assert tr[:2] == proje_yaniti['warnings'], tr
        else:
            assert tr[0] == proje_yaniti['warnings'][0], tr
            assert tr[1] == "Proje dosyasında 'created_at' damgası yok", tr


# ---------------------------------------------------------------------------
# Görev 3 — B11G devri: calculate_solid itici künyesi motorun kaynağından
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (dal tabanı 1b4bbff7, kanit/t2/b11g_once.json): istekte
# propellant_type boşken uç "propellant_type = apcp endpoint_default" diyordu;
# örnek katı motor (KNDX) 'kndx' çözüyordu. Kâhin: motorun kendi çözüm
# kaynağı (``propellant_type_source``) — künye ile motor AYNI şeyi söylemeli.
# v3.0.1 T-ÇAPA-B: eski çekirdek 30 mm @ 40 bar port boğulan motordu
# (A_p/A_t 0,947); K-A kapısından beri 422. Konu port değil: geometri
# tek tanım SOLID_DEFAULT_GEOMETRY_MM'den (kopyalanmaz).
_KATI_TABAN = {'chamber_pressure': 40, **SOLID_DEFAULT_GEOMETRY_MM}


def _itici_kunyesi(j):
    return [d for d in (j.get('defaults_applied') or [])
            if d.get('field') == 'propellant_type']


class TestKatiIticiBeyani:

    @pytest.mark.parametrize('ek,cozulen,kaynak', [
        ({'propellant_name': 'KNDX'}, 'kndx', 'propellant name (propellant_name)'),
        ({'burn_rate_preset': 'knsb'}, 'knsb', 'burn-rate preset (burn_rate_preset)'),
        ({'propellant_type': 'apcp'}, 'apcp', 'propellant_type input'),
    ])
    def test_turetilen_kimlik_varsayilan_diye_beyan_edilmez(
            self, client, ek, cozulen, kaynak):
        r = client.post('/calculate_solid', json=dict(_KATI_TABAN, **ek),
                        headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert j['propellant_type'] == cozulen
        assert j['propellant_type_source'] == kaynak
        assert _itici_kunyesi(j) == [], j.get('defaults_applied')

    def test_uc_varsayilani_gercekten_cozulduyse_beyan_edilir(self, client):
        from hrma.app import SOLID_ENDPOINT_DEFAULTS
        # v3.0.1 T-ÇAPA-B: a = 0,005 / n = 0,35 ile varsayılan çekirdek
        # (48 mm) de boğuluyor (A_p/A_t 0,958, ölçüldü); konu itici künyesi,
        # port değil → açık geçerli port: çekirdek 70 mm (A_p/A_t 1,90).
        r = client.post('/calculate_solid', json=dict(
            _KATI_TABAN, burn_rate_a=0.005, burn_rate_n=0.35,
            core_diameter=70), headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert j['propellant_type_source'] == 'endpoint default'
        k = _itici_kunyesi(j)
        assert len(k) == 1 and k[0]['reason'] == 'endpoint_default'
        assert k[0]['value'] == SOLID_ENDPOINT_DEFAULTS['propellant_type'] \
            == j['propellant_type']

    def test_ornek_kati_motor_kndx_apcp_diye_beyan_edilmez(self, ornek_motorlar):
        j = ornek_motorlar['solid']
        assert j['propellant_type'] == 'kndx'
        assert _itici_kunyesi(j) == [], j.get('defaults_applied')

    def test_ogretici_kip_aynen(self, client):
        r = client.post('/calculate_solid', json={'use_tutorial_defaults': True},
                        headers=H)
        assert r.status_code == 200
        k = _itici_kunyesi(r.get_json())
        assert len(k) == 1 and k[0]['reason'] == 'tutorial_default'


# ---------------------------------------------------------------------------
# Görev 4 — CFDS devri: runtime_basis TR karşılığı (serverText)
# ---------------------------------------------------------------------------
_CEVIRI_KOSUCU = r"""
const fs = require('fs'); const vm = require('vm');
const sb = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout,
  setInterval, clearInterval };
sb.window = sb; sb.self = sb; sb.localStorage = null;
sb.document = { readyState: 'loading', documentElement: { setAttribute() {} },
  addEventListener() {}, querySelectorAll: () => [], querySelector: () => null,
  getElementById: () => null };
vm.createContext(sb);
for (const f of ['i18n.js', 'i18n_common.js', 'i18n_charts.js'])
  vm.runInContext(fs.readFileSync('hrma/static/js/' + f, 'utf8'), sb, { filename: f });
const out = {};
for (const lang of ['tr', 'en']) {
  sb.I18N.setLang(lang);
  out[lang] = girdi.metinler.map((m) => sb.I18N.serverText(m));
}
process.stdout.write(JSON.stringify(out));
"""


def _runtime_basis_cumleleri():
    """Ucun KENDİ cümle kurucusundan (``api_cfd_nozzle`` içindeki
    ``runtime_basis`` ifadesi AST ile alınıp seviye × arka uç için
    değerlendirilir; CFD KOŞULMAZ)."""
    import ast
    import types
    import hrma.app as app_mod
    agac = ast.parse(pathlib.Path(app_mod.__file__).read_text(encoding='utf-8'))
    fn = next(n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef)
              and n.name == 'api_cfd_nozzle')
    ifade = None
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == 'runtime_basis':
                    ifade = v
    assert ifade is not None, 'runtime_basis ifadesi bulunamadı'
    kod = compile(ast.Expression(ifade), 'runtime_basis', 'eval')
    out = []
    for seviye, tablo in app_mod.CFD_RESOLUTION_WORST_CASE_S.items():
        for arka_uc in tablo:
            ad = dict(vars(app_mod), seviye=seviye, arka_uc=arka_uc,
                      viskoz_opts=None)
            out.append(eval(kod, ad))
    # cfd-sure biçimi (dal birleşince): viskoz kip de
    if hasattr(app_mod, '_cfd_runtime_basis'):
        for seviye, tablo in app_mod.CFD_VISCOUS_WORST_CASE_S.items():
            for turb in tablo:
                for arka_uc in ('numba', 'numpy'):
                    out.append(app_mod._cfd_runtime_basis(
                        seviye, arka_uc, types.SimpleNamespace(turbulence=turb)))
    return out


_KUYRUK_ORNEGI = "propellant_type 'apcp' matched the TNT-equivalent table"
_GOVDE_EN = ('solver_runtime_s is the steady driver itself, runtime_s the '
             'whole request (validation, grid, solve, separation, thinning). ')


@needs_node
class TestCfdRuntimeBasisTr:

    def test_ucun_bugunku_cumlesi_tr_ye_cevrilir(self):
        cumleler = _runtime_basis_cumleleri()
        assert cumleler
        o = _node_json(_CEVIRI_KOSUCU, {'metinler': cumleler})
        assert o['en'] == cumleler
        govde_tr = ('solver_runtime_s kararlı çözücü sürücüsünün kendi süresi, '
                    'runtime_s ise isteğin tamamıdır (doğrulama, ağ, çözüm, '
                    'ayrılma, seyreltme). Bu seviye ve arka uç için ölçülen en '
                    'kötü süre: ')
        for en, tr in zip(cumleler, o['tr']):
            kisa = re.fullmatch(r'[\s\S]*backend: (\d+(?:\.\d+)?) s\.', en)
            # ÖH 15 Eki (ana model; cfd-sure 4. tur) — dört koşulla çevrildi:
            # (1) eski dal yalnız main'in KISA cümlesini tanıyordu; cfd-sure'ün
            # UZUN cümlesi de ölçüm koşulu kuyruğuyla ' s.' ('0.1 s.') diye
            # bittiği için kısa dala düşüp kısa TR'yi bekliyordu; (2) kâhin:
            # ucun kendi cümlesi + ikinci desenin sözleşmesi (TR gövde, kip,
            # tablo, çevrilmiş kuyruk; İngilizce kuyruk kalmaz); (3) tolerans
            # yok; (4) rapor docs/scofield/raw/OH/V3/cfd-sure/rapor.md 4. tur.
            uzun = re.search(r'backend: (\d+(?:\.\d+)?) s - ', en)
            if kisa:
                assert tr == (govde_tr + kisa.group(1).replace('.', ',')
                              + ' s.'), tr
            elif uzun:
                assert tr.startswith(govde_tr + uzun.group(1).replace('.', ',')
                                     + ' s — '), tr
                assert 'Measured on' not in tr and 'Method:' not in tr, tr
            assert 'solver_runtime_s is the steady' not in tr or tr == en

    def test_olculmemis_hucre_cevrilmez(self):
        en = _GOVDE_EN + 'Measured worst case for this level and backend: None s.'
        o = _node_json(_CEVIRI_KOSUCU, {'metinler': [en]})
        assert o['tr'] == [en]

    def test_cfd_sure_bicimi_kuyruk_cevrilirse_cevrilir(self):
        en = (_GOVDE_EN + "Measured worst case for this level and backend: "
              "18.5 s - inviscid (Euler) run, level 'coarse', backend "
              "'numba', from CFD_RESOLUTION_WORST_CASE_S. " + _KUYRUK_ORNEGI)
        en_olcm = (_GOVDE_EN + "Measured worst case for this level and "
                   "backend: NOT MEASURED (this cell has no value in "
                   "CFD_VISCOUS_WORST_CASE_S; no estimate is published in its "
                   "place) - viscous, turbulence 'sa_neg' run, level "
                   "'standard', backend 'numpy', from CFD_VISCOUS_WORST_CASE_S. "
                   + _KUYRUK_ORNEGI)
        cevrilmez = en.replace(_KUYRUK_ORNEGI, 'Some untranslated tail.')
        o = _node_json(_CEVIRI_KOSUCU, {'metinler': [en, en_olcm, cevrilmez]})
        assert o['tr'][0].endswith(
            "en kötü süre: 18,5 s — viskozsuz (Euler) koşusu, seviye 'coarse', "
            "arka uç 'numba', kaynak CFD_RESOLUTION_WORST_CASE_S. "
            "propellant_type 'apcp' TNT eşdeğeri tablosuyla eşleşti"), o['tr'][0]
        assert ("ÖLÇÜLMEDİ (CFD_VISCOUS_WORST_CASE_S tablosunda bu hücrenin "
                "değeri yok; yerine tahmin yayımlanmaz) — viskoz, türbülans "
                "'sa_neg' koşusu") in o['tr'][1], o['tr'][1]
        assert o['tr'][2] == cevrilmez

    def test_esikler_yorumu_sayi_kopyalamaz(self):
        metin = (REPO_ROOT / 'tools' / 'browser_harness' / 'esikler.py'
                 ).read_text(encoding='utf-8')
        i = metin.index('MERKEZ_KOSUM_ZAMAN_ASIMI_MS = 300_000')
        yorum = metin[metin.rindex('\n\n', 0, i):i]
        assert "CFD_RESOLUTION_WORST_CASE_S['coarse']" in yorum
        import hrma.app as app_mod
        for sn in app_mod.CFD_RESOLUTION_WORST_CASE_S['coarse'].values():
            assert ('%g' % sn).replace('.', ',') not in yorum
        for eski in ('10,2', '14,9'):
            assert eski not in yorum


# ---------------------------------------------------------------------------
# Görev 5 — FY devri: fea_panel yük modeli künyesi + ham tepe bant tanısı
# ---------------------------------------------------------------------------
_FEA_JS = 'hrma/static/js/fea_panel.js'
_FEA_EV = (
    "if (body.lang && window.I18N) window.I18N.setLang(body.lang);"
    "var vm = window.FeaPanel.buildViewModel(body.fea);"
    "var els = {basis: document.createElement('div'),"
    "           basisText: document.createElement('div')};"
    "window.FeaPanel._renderBasis(els, vm);"
    "return {load_model: vm.load_model || null, peak_band: vm.peak_band || null,"
    "  satirlar: els.basisText.children.map(function (c) {"
    "    return [c.attrs['data-fea-load-model'], c.textContent]; }),"
    "  html: els.basisText.innerHTML};")


def _fea_kos(fea, lang=None):
    from tests.support.kanit import kanit_gerekli
    cfg = {'panelId': '__yok__', 'panelFiles': [_FEA_JS],
           'extraFiles': (['hrma/static/js/i18n.js',
                           'hrma/static/js/i18n_common.js',
                           'hrma/static/js/i18n_charts.js'] if lang else []),
           'dataInline': {'fea': fea, 'lang': lang}, 'evalFn': _FEA_EV}
    p = subprocess.run([NODE, kanit_gerekli(str(_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       cwd=str(REPO_ROOT), timeout=240)
    assert p.returncode == 0, p.stderr[-2000:]
    ev = json.loads(p.stdout)['evaled']
    assert not (isinstance(ev, dict) and ev.get('_err')), ev.get('_err')
    return ev


@pytest.fixture(scope='module')
def fea_ornek_kati(client, ornek_motorlar):
    """Gerçek uç: örnek katı motorla küçük yapısal FEA (tek süreç, hafif)."""
    yuk = {'n_axial0': 12, 'n_radial0': 4, 'max_rounds': 2,
           'motor_results': ornek_motorlar['solid']}
    r = client.post('/api/fea/structural', json=yuk, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    fea = r.get_json()['fea']
    assert fea['status'] == 'ok'
    return _guvenli(fea)


#: Köprünün (dalga37/v3-fea-yuk bridge.py ``_yuk_modeli_kur`` +
#: ``_kuvvet_dengesi_hukmu``) yayımladığı künye ŞEMASI — test girdisi
#: (fixture): alan adları ve kodlar o dalın kodundan, sayılar örnek.
_YUK_MODELI = {
    'distribution': 'isentropic_1d', 'p_c_pa': 4.0e6, 'gamma': 1.1338,
    'end_force': {'force_n': 12345.0, 'r0_m': 0.03},
    'scope': ('YALNIZ BASINÇ YÜKLEMESİ: iç yüzey basıncı + kapalı uç eşdeğer '
              'eksenel kuvveti.'),
    'force_balance': {'measured': True, 'holds': True, 'rel_error': 2.5e-5,
                      'tol': 1.0e-3},
}


def _beklenen_tepe(fea):
    """Bağımsız kâhin (Python): alanın en küçüğünün düğümü ve yük uygulanan
    uç kesitine Öklid uzaklığı (köprünün ölçütü)."""
    sf = fea['fields']['safety_factor']
    k = min((i for i, v in enumerate(sf) if isinstance(v, (int, float))),
            key=lambda i: (sf[i], i))
    p = fea['mesh']['nodes'][k]
    return k, p


def _uc_uzakligi(fea, p, uc):
    g = fea['mesh']['node_index_grid']
    satir = g[0] if uc == 'z_min' else g[-1]
    return min(math.hypot(p[0] - fea['mesh']['nodes'][n][0],
                          p[1] - fea['mesh']['nodes'][n][1]) for n in satir)


@needs_node
class TestFeaYukModeli:

    def test_gercek_uc_yaniti(self, fea_ornek_kati):
        """Bugünkü main yanıtı: load_model YOKSA satır yok; dal birleşince
        VARSA künye satırları basılır (iki durumda da iddia ölçülür)."""
        ev = _fea_kos(fea_ornek_kati)
        if fea_ornek_kati.get('load_model') is None:
            assert ev['load_model'] is None
            assert not [s for s in ev['satirlar'] if s[0] != 'peak_band']
        else:
            assert ev['load_model']['distribution'] == \
                fea_ornek_kati['load_model']['distribution']
            assert any(s[0] == 'distribution' for s in ev['satirlar'])
        sv = ((fea_ornek_kati.get('meta') or {}).get('cozucu') or {}).get(
            'saint_venant') or {}
        bant = [b for b in sv.get('bantlar') or []
                if b.get('neden') == 'yuk_uygulama']
        if len(bant) == 1 and sv.get('axial_fix') in ('z_min', 'z_max'):
            _k, p = _beklenen_tepe(fea_ornek_kati)
            uc = 'z_min' if sv['axial_fix'] == 'z_max' else 'z_max'
            banta = _uc_uzakligi(fea_ornek_kati, p, uc) <= bant[0]['d_SV_m']
            assert (ev['peak_band'] is not None) == banta
        else:
            assert ev['peak_band'] is None

    def test_kunye_satirlari_en(self, fea_ornek_kati):
        fea = dict(fea_ornek_kati, load_model=_YUK_MODELI)
        ev = _fea_kos(fea)
        satir = dict((a, m) for a, m in ev['satirlar'])
        assert satir['distribution'] == (
            'Wall pressure: 1-D isentropic static pressure p(x) along the '
            'nozzle (gamma = 1.1338), P_c in the chamber cylinder.')
        assert satir['end_force'].startswith('Closed-end axial force 12.35 kN')
        assert satir['scope'].startswith('Load scope: PRESSURE LOADING ONLY')
        assert satir['force_balance'] == (
            'Force balance holds: FEA support reaction vs analytic net axial '
            'pressure force, relative error 2.50e-5 (tolerance 1e-3).')
        assert 'data-fea-load-model' not in ev['html']   # textContent ile

    def test_kunye_satirlari_tr(self, fea_ornek_kati):
        fea = dict(fea_ornek_kati, load_model=dict(
            _YUK_MODELI, force_balance={'measured': True, 'holds': False,
                                        'rel_error': 3.0e-3, 'tol': 1.0e-3}))
        ev = _fea_kos(fea, lang='tr')
        satir = dict((a, m) for a, m in ev['satirlar'])
        # ÖH 14 Eki (ana model): TR tek terim kuralı nozzle → 'nozul' (d27 P12aB2-05).
        assert satir['distribution'].startswith('Cidar basıncı: nozul boyunca')
        assert satir['scope'].startswith('Yük kapsamı: YALNIZ BASINÇ')
        assert satir['force_balance'].startswith('Kuvvet dengesi TUTMUYOR')

    @pytest.mark.parametrize('bozma', ['kod', 'kapsam', 'denge'])
    def test_fail_closed(self, fea_ornek_kati, bozma):
        lm = json.loads(json.dumps(_YUK_MODELI))
        if bozma == 'kod':
            lm['distribution'] = '<b>x</b>'
        elif bozma == 'kapsam':
            lm['scope'] = 'pressure and thermal'
        else:
            lm['force_balance'] = {'measured': True, 'holds': 'evet',
                                   'rel_error': 'x', 'tol': 1e-3}
        ev = _fea_kos(dict(fea_ornek_kati, load_model=lm))
        adlar = [a for a, _m in ev['satirlar']]
        if bozma == 'kod':
            assert ev['load_model'] is None
            assert not [a for a in adlar if a != 'peak_band']
        elif bozma == 'kapsam':
            assert 'scope' not in adlar and 'distribution' in adlar
        else:
            assert 'force_balance' not in adlar and 'distribution' in adlar

    @pytest.mark.parametrize('oran,banta', [(1.5, True), (0.5, False)])
    def test_ham_tepe_bant_tanisi(self, fea_ornek_kati, oran, banta):
        """Bant d_SV'si tepe düğümünün uç kesite UZAKLIĞINA göre kurulur
        (kâhin Python'da): içerideyse tanı basılır, dışarıdaysa basılmaz.

        V3.0.5 (28 Eki, A1): bekçi eskiden yük ucunu sabit z_min alıyordu.
        Örnek katı motor gerçek sayfa gövdesiyle yeniden üretildi (V301/ÖRNEK
        5fa435893, main'e 9ece56015: lüle girdileri açık — boğaz 18,4 mm,
        yakınsak 45°, grafit lüle, kartuş yüklü tane). ÖLÇÜLDÜ (RAPOR A1):
        ham tepe artık z_min uç kesitinin İÇ KÖŞE düğümünde (d = 0; eski
        örnekle bugünkü kodda 28,6 mm). d = 0 iken sınıflandırma sınırı
        (d·oran) boşalır. Ürünün gerçek durumu (tepe yük uygulanan uçta →
        tanı basılır) ``test_gercek_uc_yaniti``nda ucun kendi bandıyla
        sınanıyor; bu bekçi sınıflandırıcıyı tepenin kesitine UZAK uçla
        sürer (yük ucu o uç, kip karşıtı). Ölçüt ve parametreler aynen."""
        fea = json.loads(json.dumps(fea_ornek_kati))
        k, p = _beklenen_tepe(fea)
        fea['scalars']['peak_safety_factor'] = fea['fields']['safety_factor'][k]
        uzaklik = {u: _uc_uzakligi(fea, p, u) for u in ('z_min', 'z_max')}
        uc = max(uzaklik, key=uzaklik.get)
        d = uzaklik[uc]
        assert d > 0, 'ön koşul: tepe en az bir uç kesitin üstünde değil'
        fea.setdefault('meta', {}).setdefault('cozucu', {})['saint_venant'] = {
            'axial_fix': 'z_max' if uc == 'z_min' else 'z_min',
            'bantlar': [{'neden': 'kisit', 'd_SV_m': 1.0},
                        {'neden': 'yuk_uygulama', 'd_SV_m': d * oran}]}
        ev = _fea_kos(fea)
        if not banta:
            assert ev['peak_band'] is None
            return
        pb = ev['peak_band']
        assert pb['end'] == uc
        assert pb['z_m'] == p[0] and pb['r_m'] == p[1]
        satir = dict((a, m) for a, m in ev['satirlar'])['peak_band']
        assert satir.startswith('Diagnosis (not a verdict): the raw peak '
                                'safety factor %.2f sits at z = %.1f mm, '
                                'r = %.1f mm' % (pb['peak_safety_factor'],
                                                 p[0] * 1000, p[1] * 1000))

    def test_tepe_alanla_eslesmezse_tani_yok(self, fea_ornek_kati):
        fea = json.loads(json.dumps(fea_ornek_kati))
        k, p = _beklenen_tepe(fea)
        fea['scalars']['peak_safety_factor'] = (
            fea['fields']['safety_factor'][k] * 1.01)
        fea.setdefault('meta', {}).setdefault('cozucu', {})['saint_venant'] = {
            'axial_fix': 'z_max',
            'bantlar': [{'neden': 'yuk_uygulama', 'd_SV_m': 10.0}]}
        assert _fea_kos(fea)['peak_band'] is None


_FY_ANAHTARLARI = ('fea.loadModelIsentropic', 'fea.loadModelFallback',
                   'fea.loadModelEndForce', 'fea.loadModelScopePressureOnly',
                   'fea.loadModelBalanceHolds', 'fea.loadModelBalanceFails',
                   'fea.loadModelBalanceNotMeasured', 'fea.peakInLoadBand',
                   'warn.project.app_version_mismatch',
                   'warn.project.missing_stamp')


@pytest.mark.parametrize('anahtar', _FY_ANAHTARLARI)
def test_t2_i18n_anahtari_en_tr(anahtar):
    metin = _I18N_COMMON.read_text(encoding='utf-8')
    satirlar = [m[1] for m in re.findall(
        r"""'%s': (['"])(.*?)\1,""" % re.escape(anahtar), metin)]
    assert len(satirlar) == 2, (anahtar, satirlar)
    en, tr = satirlar
    assert en != tr and re.search('[çğıİöşüÇĞÖŞÜ]', tr), tr
    assert (sorted(re.findall(r'\{(\w+)\}', en))
            == sorted(re.findall(r'\{(\w+)\}', tr))), anahtar


# ---------------------------------------------------------------------------
# Görev 6 — SO1 D-2: CEA veri dizini sapma denetimi + yeniden sabitleme
# ---------------------------------------------------------------------------
class TestCeaVeriDiziniSapmasi:

    def test_sapma_yeniden_sabitlenir(self, tmp_path, monkeypatch):
        cm = pytest.importorskip('rocketcea.cea_obj')
        from hrma.engines import cea_bridge as cb
        yol = cb.ensure_isolated_cea_data_dir()
        assert yol and cm.ROCKETCEA_DATA_DIR == yol
        # Başka bir çağıran global'i değiştirir (K-3 sınıfı); test sonunda
        # global monkeypatch ile geri gelir.
        monkeypatch.setattr(cm, 'ROCKETCEA_DATA_DIR', cm.ROCKETCEA_DATA_DIR)
        cm.set_rocketcea_data_dir(str(tmp_path), do_print=False)
        assert cm.ROCKETCEA_DATA_DIR != yol
        once = cb._CEA_DATA_DIR_REPINS
        assert cb.ensure_isolated_cea_data_dir() == yol
        assert cm.ROCKETCEA_DATA_DIR == yol
        assert cb._CEA_DATA_DIR_REPINS == once + 1
        # Sapma yoksa yeniden sabitleme yok (sıcak yol).
        assert cb.ensure_isolated_cea_data_dir() == yol
        assert cb._CEA_DATA_DIR_REPINS == once + 1

    def test_sabitlenemezse_none_fail_closed(self, tmp_path, monkeypatch):
        """Ayarlayıcı tutmazsa (geri okunan global yine sapık) yalıtım İDDİA
        EDİLMEZ: None. Global test sonunda monkeypatch ile geri gelir."""
        cm = pytest.importorskip('rocketcea.cea_obj')
        from hrma.engines import cea_bridge as cb
        yol = cb.ensure_isolated_cea_data_dir()
        assert yol
        yabanci = str(tmp_path)
        monkeypatch.setattr(cm, 'ROCKETCEA_DATA_DIR', yabanci)

        def _tutmayan(_d, do_print=False):
            cm.ROCKETCEA_DATA_DIR = yabanci

        monkeypatch.setattr(cm, 'set_rocketcea_data_dir', _tutmayan)
        assert cb.ensure_isolated_cea_data_dir() is None
        assert cm.ROCKETCEA_DATA_DIR == yabanci


# ===========================================================================
# 3. TUR (15 Eki 2026) — TR KİPTE KALAN DİL VE ONDALIK KUSURLARI (§28-50 (c))
# ===========================================================================
# ÖLÇÜLDÜ: docs/user_guide/img/v3_0/kanit/kayit_tr.json (KLV'nin TR kipte
# gerçek koşusunda ekrandan okunan metinler) + kk3 ölçümleri (rapor.md
# '3. tur'). Kâhinler ÜRETİCİDEN (Python modülü / uç yanıtı / AST) kurulur;
# çeviri yolunun kendisinden değil.
_KK3_KOSUCU = r"""
const fs = require('fs'); const vm = require('vm');
function El(id) { this.id = id || ''; this.tagName = 'DIV'; this.style = {};
  this.dataset = {}; this.children = []; this._attrs = {}; this.innerHTML = '';
  this.textContent = ''; this.value = ''; this.disabled = false; this._h = {};
  this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
  this.parentElement = null; }
El.prototype.appendChild = function (c) { this.children.push(c); c.parentElement = this; return c; };
El.prototype.insertBefore = function (c) { return this.appendChild(c); };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) { return (k in this._attrs) ? this._attrs[k] : null; };
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.addEventListener = function (ad, fn) { this._h[ad] = fn; };
El.prototype.remove = function () {};
Object.defineProperty(El.prototype, 'firstElementChild', { get: function () {
  return this.children[0] || this; } });
const dugum = {};
const yok = new Set(girdi.yokIdler || []);
const sb = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout,
  setInterval, clearInterval, Promise, JSON, Math };
sb.window = sb; sb.self = sb; sb.globalThis = sb; sb.localStorage = null;
sb.girdi = girdi;
sb.requestAnimationFrame = function (f) { f(0); return 1; };
sb.Plotly = { newPlot() {}, react() {}, purge() {} };
sb.document = { readyState: 'complete', documentElement: new El('html'),
  head: new El('head'), body: new El('body'), addEventListener() {},
  createElement: function () { return new El(); },
  querySelectorAll: () => [], querySelector: () => null,
  getElementById: function (id) { if (yok.has(id)) return null;
    if (!(id in dugum)) dugum[id] = new El(id); return dugum[id]; } };
sb.fetch = function () { const f = girdi.fetch || { status: 599, body: null };
  return Promise.resolve({ ok: f.status >= 200 && f.status < 300, status: f.status,
    json: function () { return Promise.resolve(f.body); } }); };
vm.createContext(sb);
for (const f of girdi.dosyalar)
  vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f });
if (girdi.ekKod) vm.runInContext(girdi.ekKod, sb, { filename: 'ek' });
sb.I18N.setLang(girdi.dil || 'tr');
sb.__dugum = dugum; sb.__El = El;
vm.runInContext('(async function () {' + girdi.betik + '})()', sb)
  .then(function (o) { process.stdout.write(JSON.stringify(o)); })
  .catch(function (e) { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""
_I18N_TEMEL = ['hrma/static/js/i18n.js', 'hrma/static/js/i18n_common.js',
               'hrma/static/js/i18n_charts.js']
_DOCK_DOSYALARI = _I18N_TEMEL + ['hrma/static/js/analysis_dock.js']


def _kk3(dosyalar, betik, dil='tr', **ek):
    return _node_json(_KK3_KOSUCU, dict(ek, dosyalar=dosyalar, betik=betik,
                                        dil=dil))


def _duz(html):
    return ' '.join(re.sub(r'<[^>]*>', ' ', html or '').split())


def _sunucu_metni(metinler, dil='tr'):
    return _kk3(_I18N_TEMEL, 'return girdi.metinler.map(function (m) {'
                ' return window.I18N.serverText(m); });', dil=dil,
                metinler=metinler)


#: TR çıktıda kalmaması gereken İngilizce işaret sözcükleri (cümlenin
#: çevrildiğinin bağımsız sınaması; makine alan adları bunları taşımaz).
_EN_ISARET = re.compile(r'\b(the|was|were|is|not|and|which|this|because)\b')


def _tr_mi(en, tr):
    assert tr != en, 'çevrilmedi: %r' % en[:80]
    kalan = _EN_ISARET.findall(re.sub(r'[A-Za-z_]+\.[A-Za-z_.]+|\w+_\w+', ' ', tr))
    assert not kalan, 'TR metinde İngilizce kaldı %r: %r' % (kalan, tr[:200])


# ---------------------------------------------------------------------------
# Kalem 1 + 6 — katı Yapısal sekmesi: sınıf kodları ve yüzde biçimi
# ---------------------------------------------------------------------------
_SOLID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'solid.html'


def _solid_yardimcilari():
    html = _SOLID_HTML.read_text(encoding='utf-8')
    a = html.index('>>> HRMA-HONEST-FORMATTERS-BEGIN <<<')
    b = html.index('>>> HRMA-HONEST-FORMATTERS-END <<<')
    kaynak = html[a:b].split('\n', 1)[1]
    s = html.index('\n        function escapeNoticeText(')
    e = html.index('\n        }\n', s) + len('\n        }\n')
    return html[s:e] + kaynak


def _motor_sinif_kodlari():
    """Bağımsız kâhin: solid_rocket_engine.py'nin üç sınıf değişkenine
    atanan TÜM dize sabitleri (AST; çeviri tablosundan değil)."""
    import ast
    yol = REPO_ROOT / 'hrma' / 'engines' / 'solid_rocket_engine.py'
    agac = ast.parse(yol.read_text(encoding='utf-8'))
    out = {'crack_risk': set(), 'thermal_compat': set(), 'rating': set()}
    for n in ast.walk(agac):
        if (isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id in out
                and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str)):
            out[n.targets[0].id].add(n.value.value)
    return out


@needs_node
class TestKk3KatiSinifVeYuzde:

    def _kos(self, dil, kodlar):
        betik = ('var o = {}; girdi.kodlar.forEach(function (k) {'
                 ' o[k] = fmtTextField({x: k}, "x", "sinif"); });'
                 ' o.__yuzde = fmtField({p: 16.2}, "p", 1, "%");'
                 ' o.__mm = fmtField({p: 1.6}, "p", 1, "mm");'
                 ' return o;')
        return _kk3(['hrma/static/js/i18n.js', 'hrma/static/js/i18n_pages.js'],
                    betik, dil=dil, kodlar=kodlar,
                    ekKod=_solid_yardimcilari())

    def test_motorun_her_sinif_kodu_tr_de_cevrilir(self):
        aileler = _motor_sinif_kodlari()
        # Kâhin dolu: üç aile (ölçülen 3 + 3 + 4 kod; 'Marginal' ortak).
        assert [len(aileler[a]) for a in ('crack_risk', 'thermal_compat',
                                          'rating')] == [3, 3, 4], aileler
        kodlar = sorted(set().union(*aileler.values()))
        tr = self._kos('tr', kodlar)
        en = self._kos('en', kodlar)
        for k in kodlar:
            assert en[k] == k, (k, en[k])
            assert tr[k] != k and tr[k].strip(), (k, tr[k])
        assert tr['High'] == 'Yüksek' and tr['Poor'] == 'Zayıf'

    def test_taninmayan_kod_ham_ve_kacisli(self):
        tr = self._kos('tr', ['<b>Yeni</b>'])
        assert tr['<b>Yeni</b>'] == '&lt;b&gt;Yeni&lt;/b&gt;'

    def test_yuzde_isareti_dile_gore(self):
        assert self._kos('tr', [])['__yuzde'] == '%16,2'
        assert self._kos('en', [])['__yuzde'] == '16.2%'
        assert self._kos('tr', [])['__mm'] == '1,6 mm'

    def test_yapisal_ve_termal_sekme_baglantisi(self):
        """Sekme üreticileri sınıf çevirisini ve yüzde biçimini GERÇEKTEN
        kullanır (yardımcı tek başına değil, sekmenin HTML'i)."""
        html = _SOLID_HTML.read_text(encoding='utf-8')
        govdeler = ''
        for ad in ('generateStructuralAnalysisHTML',
                   'generateThermalAnalysisHTML'):
            s0 = html.index('\n        function %s(' % ad)
            govdeler += html[s0:html.index('\n        }\n', s0)
                             + len('\n        }\n')]
        betik = ('var r = {structural_analysis: {case_analysis:'
                 ' {material_utilization_percent: 16.2},'
                 ' grain_structural: {crack_propagation_risk: "High",'
                 ' thermal_expansion_compatibility: "Poor"},'
                 ' assembly_integrity: {closure_joint: {status: "not_sized",'
                 ' basis: "<b>x</b>"}}},'
                 ' thermal_analysis: {heat_transfer: {thermal_protection_rating:'
                 ' "Adequate"}}};'
                 ' return {y: generateStructuralAnalysisHTML(r),'
                 ' t: generateThermalAnalysisHTML(r)};')
        out = _kk3(['hrma/static/js/i18n.js', 'hrma/static/js/i18n_pages.js'],
                   betik, ekKod=_solid_yardimcilari() + govdeler)
        y = _duz(out['y'])
        assert 'Yüksek' in y and 'Zayıf' in y and '%16,2' in y, y[:600]
        assert '&lt;b&gt;x&lt;/b&gt;' in out['y'] and '<b>x</b>' not in out['y']
        assert 'Yeterli' in _duz(out['t'])

    def test_civata_gerekcesi_kacisli_ve_cevrilir(self):
        html = _SOLID_HTML.read_text(encoding='utf-8')
        assert ("${escapeNoticeText(sunucuMetni(joint.basis || ''))}"
                in html)
        assert '${joint.basis ||' not in html


# ---------------------------------------------------------------------------
# Kalem 1-4 — sunucu cümleleri TR kipte (serverText), kâhin = üretici
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def kk3_cumleler(client, ornek_motorlar):
    from hrma.analysis import flight_vehicle as fv
    from hrma.analysis.uncertainty import _conditionality_block
    out = {}
    out['civata'] = ornek_motorlar['solid']['structural_analysis'][
        'assembly_integrity']['closure_joint']['basis']
    akis = _dock_akisi(client, 'solid', ornek_motorlar['solid'])
    out['burn_time'] = akis['uc']['inputs_not_consumed']['burn_time']['reason']
    out['cikis'] = _termal(client, 'steel')['thermal_analysis'][
        'gas_side_analysis']['wetted_integral_contour_basis'][
        'exit_diameter_source']
    cb = _conditionality_block({}, ['a'], 'lhs', 1)
    for k in ('applies_to', 'frozen_at_nominal', 'input_correlation_assumed',
              'interpretation'):
        out['uq_' + k] = cb[k]
    out['hibrit_kunye'] = fv.normalize(
        'hybrid', ornek_motorlar['hybrid'])['engine_inert_mass_note']
    out['sivi_kunye'] = fv.normalize(
        'liquid', ornek_motorlar['liquid'])['engine_inert_mass_note']
    out['sivi_tankli'] = fv._liquid_inert_mass({'propellant_tanks': {
        'system_summary': {'total_tank_mass': 12.5,
                           'total_propellant_mass': 110.0,
                           'total_propellant_mass_nominal': 100.0}}},
        40.25)[1]
    out['sivi_yok'] = fv._liquid_inert_mass({}, None)[1]
    return out


@needs_node
class TestKk3SunucuCumleleri:

    def test_ureticinin_cumleleri_tr_ye_cevrilir_en_aynen(self, kk3_cumleler):
        adlar = sorted(kk3_cumleler)
        metinler = [kk3_cumleler[a] for a in adlar]
        assert all(isinstance(m, str) and m for m in metinler), adlar
        tr = _sunucu_metni(metinler, 'tr')
        en = _sunucu_metni(metinler, 'en')
        for ad, m, t, e in zip(adlar, metinler, tr, en):
            assert e == m, ad
            _tr_mi(m, t)

    def test_hibrit_kunyesi_olcum_ve_dayanak_tr(self, kk3_cumleler):
        m = kk3_cumleler['hibrit_kunye']
        assert m.startswith('dry mass computed by the motor structural model')
        oran = re.search(r'measured dry/propellant ratio (\S+);', m).group(1)
        t = _sunucu_metni([m])[0]
        assert ('ölçülen kuru/itici oranı ' + oran.replace('.', ',')) in t
        assert 'dayanak: Uçuş zinciri' in t

    def test_dayanagi_cevrilemeyen_kunye_aynen_kalir(self):
        """Fail-closed: kuyruk çevrilemezse yarı Türkçe cümle üretilmez."""
        m = ('dry mass computed by the motor structural model, NOT the 0.25 '
             'rule of thumb; measured dry/propellant ratio 7.48; basis: '
             'an unknown future basis sentence')
        assert _sunucu_metni([m])[0] == m


# ---------------------------------------------------------------------------
# Kalem 3 — fırlatma sahası şablonu sunucu cümlesini çeviriden geçirir
# ---------------------------------------------------------------------------
class TestKk3FirlatmaSahasi:

    def test_sablon_ceviri_kanalini_yukler_ve_kullanir(self):
        html = (REPO_ROOT / 'hrma' / 'templates' / 'launch_site.html'
                ).read_text(encoding='utf-8')
        assert '<script src="/static/js/i18n_charts.js"></script>' in html
        assert "msg += (msg ? ' ' : '') + srv(inertNote);" in html
        assert 'yuklemeUyarilari.map(yuklemeUyarisiMetni).join' in html

    @staticmethod
    def _yukleme(metinler, dil):
        html = (REPO_ROOT / 'hrma' / 'templates' / 'launch_site.html'
                ).read_text(encoding='utf-8')
        a = html.index('    var YUKLEME_UYARILARI = [')
        b = html.index('\n    }\n', html.index('    function yuklemeUyarisiMetni('))
        kod = ('function t(k, fb) { return I18N.t(k, fb); }\n'
               + html[a:b + len('\n    }\n')])
        return _kk3(['hrma/static/js/i18n.js',
                     'hrma/static/js/i18n_launch_site.js'],
                    'return girdi.metinler.map(yuklemeUyarisiMetni);',
                    dil=dil, metinler=metinler, ekKod=kod)

    @needs_node
    def test_yukleme_uyarilari_tr_sablonla_birebir(self):
        from hrma.utils import projects as pj
        kayitlar = [
            {'code': pj.LOAD_WARNING_APP_VERSION_MISMATCH,
             'params': {'saved_version': '2.6.26', 'current_version': '3.0'}},
            {'code': pj.LOAD_WARNING_MISSING_STAMP,
             'params': {'stamp': 'created_at'}}]
        en = [pj.load_warning_text(r) for r in kayitlar]
        tr = self._yukleme(en + ['some future load warning'], 'tr')
        assert self._yukleme(en, 'en') == en
        assert tr[2] == 'some future load warning'
        # Kâhin: i18n_common.js TR şablonu (ayrı sözlük), parametreler
        # Python'da yerleştirilir; sürüm dizgisi ondalık kanonundan GEÇMEZ.
        kaynak = _I18N_COMMON.read_text(encoding='utf-8')
        tr_blok = kaynak[kaynak.index('\n        tr: {'):]
        for r, t in zip(kayitlar, tr):
            sablon = re.search(r"'%s': '((?:[^'\\]|\\.)*)'" % re.escape(
                r['code']), tr_blok).group(1).replace("\\'", "'")
            beklenen = re.sub(r'\{(\w+)\}', lambda x: r['params'][x.group(1)],
                              sablon)
            assert t == beklenen, (t, beklenen)

    def test_en_sablonu_sunucu_sablonuyla_birebir(self):
        from hrma.utils import projects as pj
        kaynak = (_JS / 'i18n_launch_site.js').read_text(encoding='utf-8')
        en_blok = kaynak[:kaynak.index('\n        tr: {')]
        for kod, anahtar in ((pj.LOAD_WARNING_APP_VERSION_MISMATCH,
                              'site.loadWarnAppVersion'),
                             (pj.LOAD_WARNING_MISSING_STAMP,
                              'site.loadWarnMissingStamp')):
            v = re.search(r"'%s': '((?:[^'\\]|\\.)*)'" % re.escape(anahtar),
                          en_blok).group(1).replace("\\'", "'")
            assert v == pj._LOAD_WARNING_TEXT_EN[kod]

    def test_ucun_arac_anahtar_kumesi_degismedi(self):
        """Uca alan eklenmedi (VEHICLE_EXTRA_KEYS dokunulmadı)."""
        from tests.test_faz6_f5_app import VEHICLE_EXTRA_KEYS
        assert VEHICLE_EXTRA_KEYS == {'load_warnings', 'airframe'}


# ---------------------------------------------------------------------------
# Kalem 2 + 6 — güverte termal / yapısal: TR ondalık ve sunucu cümlesi
# ---------------------------------------------------------------------------
_PANEL_RENDER = ('var spec = window.AnalysisDock._registry.filter(function (s) {'
                 ' return s.id === girdi.panel; })[0];'
                 ' var root = new window.__El("root");'
                 ' spec.render(girdi.veri, root);'
                 ' var h = root.innerHTML; root.children.forEach(function (c) {'
                 ' h += " " + c.innerHTML; }); return {html: h};')


def _panel_tr(panel, dosya, veri, dil='tr'):
    return _duz(_kk3(_DOCK_DOSYALARI + [dosya], _PANEL_RENDER, dil=dil,
                     panel=panel, veri=veri)['html'])


@needs_node
class TestKk3GuverteOndalik:

    def test_termal_kartlar_ve_satirlar_tr_virgullu(self, client):
        veri = _termal(client, 'aluminum_6061')
        ta = veri['thermal_analysis']
        gsa, cool = ta['gas_side_analysis'], ta['cooling_analysis']
        safe = ta['safety_analysis']
        metin = _panel_tr('thermal', _THERMAL_JS, veri)
        # Kâhin: Python'da yuvarlanan sayı + TR ayracı (panel kodundan değil).
        for deger in ('%.2f MW/m²' % (gsa['throat_heat_flux'] / 1e6),
                      '%.1f kW' % cool['peak_heat_rate'],
                      '%.2f m²' % cool['required_cooling_area'],
                      '%.2f' % safe['melting_safety_factor']):
            tr = deger.replace('.', ',')
            assert tr in metin, (tr, metin[:400])
        en = _panel_tr('thermal', _THERMAL_JS, veri, dil='en')
        assert ('%.2f MW/m²' % (gsa['throat_heat_flux'] / 1e6)) in en

    def test_termal_cikis_capi_beyani_tr(self, client):
        veri = _termal(client, 'steel')
        kaynak = veri['thermal_analysis']['gas_side_analysis'][
            'wetted_integral_contour_basis']['exit_diameter_source']
        assert kaynak.startswith('NOT GIVEN')
        metin = _panel_tr('thermal', _THERMAL_JS, veri)
        assert 'NOT GIVEN' not in metin and 'VERİLMEDİ — ne exit_diameter' in metin

    def test_yapisal_cidar_ve_burn_time_tr(self, client, ornek_motorlar):
        akis = _dock_akisi(client, 'solid', ornek_motorlar['solid'])
        db = akis['uc']['design_basis']
        assert isinstance(db.get('submitted_wall_thickness_mm'), (int, float))
        metin = _panel_tr('structural', _STRUCT_JS, akis['uc'])
        beklenen = ('%.3f' % db['submitted_wall_thickness_mm']).replace('.', ',')
        assert 'submitted_wall_thickness_mm ' + beklenen in metin
        assert 'bu analizde kullanılmadı' in metin
        assert 'not consumed by this analysis' not in metin
        assert 'burn_time is validated' not in metin


# ---------------------------------------------------------------------------
# Kalem 4 — belirsizlik: sıfır = otomatik (fix-7 sözleşmesi) + okunur ret
# ---------------------------------------------------------------------------
def _uq(client, alanlar):
    r = client.post('/api/uncertainty-analysis', json={
        'motor_type': 'hybrid', 'level': 'fast', 'seed': 42,
        'inputs': alanlar}, headers=H)
    return r.status_code, r.get_json()


@pytest.fixture(scope='module')
def hibrit_alanlari():
    with open(REPO_ROOT / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma',
              encoding='utf-8') as f:
        return json.load(f)['inputs']['fields']


class TestKk3BelirsizlikSifirOtomatik:

    def test_ornek_hibrit_sifir_cap_reddedilmez(self, client, hibrit_alanlari):
        assert hibrit_alanlari['chamber_diameter_input'] == 0
        kod, j = _uq(client, hibrit_alanlari)
        assert kod == 200 and j['status'] == 'ok', j.get('error')

    def test_sifir_verilmemisle_ayni_sonuc(self, client, hibrit_alanlari):
        """Kâhin: alan HİÇ gönderilmeyen koşu (çözücü çapı kendisi çözer)."""
        _, sifir = _uq(client, hibrit_alanlari)
        bos = dict(hibrit_alanlari)
        bos.pop('chamber_diameter_input')
        _, yok = _uq(client, bos)
        assert sifir['outputs'] == yok['outputs']
        assert 'chamber_diameter_input' not in sifir['conditionality'][
            'conditional_on_inputs']

    def test_negatif_cap_yine_reddedilir(self, client, hibrit_alanlari):
        kod, j = _uq(client, dict(hibrit_alanlari,
                                  chamber_diameter_input=-5.0))
        assert kod == 422 and j['error'] == 'non_physical_uncertainty_input'
        assert j['invalid_fields'][0]['field'] == 'chamber_diameter_input'
        assert j['invalid_fields'][0]['reason'] == 'must_be_non_negative'


_UQ_BETIK = (
    'window.getFormData = function () { return {chamber_diameter_input: -5}; };'
    'var h = window.__dugum.uq_run && window.__dugum.uq_run._h.click;'
    'if (!h) return {hata: "uq_run tıklama işleyicisi bağlanmadı"};'
    'await h(); await new Promise(function (r) { setTimeout(r, 20); });'
    'return {durum: window.__dugum.ad_status_uncertainty.textContent};')


@needs_node
class TestKk3BelirsizlikRetIletisi:

    def _kos(self, dil, govde):
        return _kk3(_DOCK_DOSYALARI
                    + ['hrma/static/js/panels/uncertainty_panel.js'],
                    _UQ_BETIK, dil=dil, yokIdler=['uq_custom'],
                    fetch={'status': 422, 'body': govde})

    def test_ret_okunur_ve_alan_adiyla(self, client, hibrit_alanlari):
        _, govde = _uq(client, dict(hibrit_alanlari,
                                    chamber_diameter_input=-5.0))
        tr = self._kos('tr', govde)
        en = self._kos('en', govde)
        assert not tr.get('hata') and not en.get('hata'), (tr, en)
        assert 'Belirsizlik analizi koşturulmadı' in tr['durum']
        assert 'chamber_diameter_input' in tr['durum']
        assert 'No uncertainty analysis was run' in en['durum']
        assert 'chamber_diameter_input' in en['durum']
        for d in (tr['durum'], en['durum']):
            assert d.strip() not in ('HATA: non_physical_uncertainty_input',
                                     'ERROR: non_physical_uncertainty_input')


@needs_node
class TestKk3KosulluBantMetinleri:

    def test_kosulluluk_degerleri_tr(self):
        from hrma.analysis.uncertainty import _conditionality_block
        cb = _conditionality_block({}, ['a'], 'lhs', 1)
        tr = _sunucu_metni([cb['interpretation'], cb['frozen_at_nominal']])
        assert tr[0].startswith('Bu yüzdelikler')
        assert tr[1] == 'conditional_on_inputs içinde listelenmeyen her model girdisi'


# ---------------------------------------------------------------------------
# Kalem 5 — uyarı parametresinde ham malzeme / soğutma kodu
# ---------------------------------------------------------------------------
@needs_node
class TestKk3UyariParametreleri:

    def _kos(self, dil, kayitlar):
        return _kk3(_DOCK_DOSYALARI + [_THERMAL_JS],
                    'return girdi.kayitlar.map(function (w) {'
                    ' return window.AnalysisDock.ui.warnText(w); });',
                    dil=dil, kayitlar=kayitlar)

    @staticmethod
    def _tr_ad(anahtar):
        """Kâhin: termal panelin KENDİ seçenek satırı (anahtar → mat.*)
        ve i18n_common.js TR değeri, Python'da ayrı ayrı okunur."""
        panel = (REPO_ROOT / _THERMAL_JS).read_text(encoding='utf-8')
        sk = re.search(r"\['%s', '[^']*', '(mat\.[A-Za-z0-9]+)'\]"
                       % re.escape(anahtar), panel).group(1)
        kaynak = _I18N_COMMON.read_text(encoding='utf-8')
        tr_blok = kaynak[kaynak.index('\n        tr: {'):]
        return re.search(r"'%s': '([^']*)'" % re.escape(sk), tr_blok).group(1)

    def test_ornek_hibrit_uyarilari(self, ornek_motorlar):
        m = ornek_motorlar['hybrid']['motor']
        kayitlar = [w for w in m['heat_transfer_analysis']['gas_side_analysis'
                                                          ]['warnings']
                    if isinstance(w, dict) and w.get('code') ==
                    'warn.thermal.wall_exceeds_melting']
        assert kayitlar
        anahtar = kayitlar[0]['params']['material']
        tr = self._kos('tr', kayitlar)[0]
        en = self._kos('en', kayitlar)[0]
        assert anahtar not in tr and anahtar not in en, (anahtar, tr)
        assert self._tr_ad(anahtar) in tr

    def test_klv_olcumu_steel_4130(self):
        """KLV 14 Eki TR ekranı: '... belirtilen soğutmayla steel_4130 ...'."""
        w = {'code': 'warn.thermal.wall_exceeds_melting',
             'params': {'T_wall': 3313, 'material': 'steel_4130',
                        'melting': 1705, 'q_MW': 27.1}}
        tr = self._kos('tr', [w])[0]
        assert 'steel_4130' not in tr
        assert self._tr_ad('steel_4130') in tr

    def test_sogutma_kodu_sozlukten(self):
        w = {'code': 'warn.hybrid.nozzle_material_over_temp',
             'params': {'wall_K': 3304, 'allowable_K': 3300,
                        'material': 'Graphite (isostatic, nozzle insert grade)',
                        'cooling': 'natural'}}
        tr = self._kos('tr', [w])[0]
        assert 'natural soğutmalı' not in tr
        assert 'Doğal (ısı emici) soğutmalı' in tr
        # Görünen ad (materials_db 'name') olduğu gibi kalır: uydurma yok.
        assert mdb.get_material('graphite')['name'] in tr

    def test_taninmayan_deger_aynen(self):
        w = {'code': 'warn.thermal.wall_exceeds_melting',
             'params': {'T_wall': 1, 'material': 'unobtainium',
                        'melting': 2, 'q_MW': 3}}
        assert 'unobtainium' in self._kos('tr', [w])[0]


# ---------------------------------------------------------------------------
# Kalem 7 — güvenlik paneli: cidar çifti NEDEN gönderilmedi
# ---------------------------------------------------------------------------
_GUVENLIK_JS = 'hrma/static/js/panels/safety_panel.js'
_GUVENLIK_BETIK = (
    'var spec = window.AnalysisDock._registry.filter(function (s) {'
    ' return s.id === "safety"; })[0];'
    'window.AnalysisDock._setMotorType("hybrid");'
    'var sug = spec.fromResults(girdi.motor);'
    'var root = new window.__El("root");'
    'spec.render(girdi.uc, root);'
    'return {sug: sug, html: root.innerHTML};')


@needs_node
class TestKk3GuvenlikCidarNedeni:

    def _kos(self, client, motor, dil='tr'):
        from tests.test_d37_panel_js_t5_guvenlik_sinifi import _node
        govde = _node({'vakalar': {'h': {'motorType': 'hybrid',
                                         'results': motor}}})['govdeler']['h']
        r = client.post('/analyze_safety', json=govde, headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        uc = _guvenli(r.get_json())
        out = _kk3(_DOCK_DOSYALARI + [_GUVENLIK_JS], _GUVENLIK_BETIK, dil=dil,
                   motor=motor, uc=uc)
        return govde, uc, out

    def test_bayrakli_ornek_hibritte_neden_adiyla(self, client,
                                                  ornek_motorlar):
        govde, uc, out = self._kos(client, ornek_motorlar['hybrid'])
        # Uca giden gövde DEĞİŞMEDİ (TestCidarKaynagi sözleşmesi).
        assert 'wall_temperature_hot' not in govde
        assert 'wall_temperature_hot' not in out['sug']
        assert uc['safety_analysis']['thermal_safety'][
            'thermal_verdict'] == 'withheld'
        metin = _duz(out['html'])
        assert 'data-safety-wall-unphysical' in out['html']
        assert 'wall_temperature_unphysical = true' in metin
        assert 'Termal eksen değerlendirilmedi' in metin
        # Isı modülünün KENDİ uyarısı (kâhin: motor yanıtındaki kayıt).
        gsa = ornek_motorlar['hybrid']['motor']['heat_transfer_analysis'][
            'gas_side_analysis']
        kod = [w for w in gsa['warnings'] if isinstance(w, dict)
               and w.get('code') == 'warn.thermal.wall_exceeds_melting'][0]
        assert ('%d K' % kod['params']['T_wall']) in metin
        en = _duz(self._kos(client, ornek_motorlar['hybrid'], 'en')[2]['html'])
        assert 'Thermal axis not evaluated' in en

    def test_bayraksiz_motorda_not_yok(self, client, ornek_motorlar):
        """Panel çifti GERİ TUTMADIYSA, uç termal ekseni başka nedenle geri
        çekse bile 'fiziksel değil' nedeni uydurulmaz."""
        import copy
        _g, uc_geri, _o = self._kos(client, ornek_motorlar['hybrid'])
        assert uc_geri['safety_analysis']['thermal_safety'][
            'thermal_verdict'] == 'withheld'
        r = copy.deepcopy(ornek_motorlar['hybrid'])
        r['motor']['heat_transfer_analysis']['gas_side_analysis'][
            'wall_temperature_unphysical'] = False
        # V3.0.5 T-ÇAPA-C1 — ÖNCÜL AÇIKÇA (V301/H-termal 77d64c641 + PANEL):
        # örnek hibritte cidar çiftinin kaynağı artık bölge beyanıdır
        # ('hybrid_chamber_zone_protection', güvertenin ÇÖZÜLMEDİ listesinde),
        # yani bayrak kalksa da çift önerilmez. Bu düğümün sorusu yalnız
        # "bayrak yokken 'fiziksel değil' nedeni uydurulmaz mı"; kopyada
        # kaynak, ısı modülünün kendi çözüm etiketine çekilir.
        r['motor']['structural_analysis']['thermal_analysis'][
            'wall_temperature_source'] = 'heat_transfer_module'
        out = _kk3(_DOCK_DOSYALARI + [_GUVENLIK_JS], _GUVENLIK_BETIK,
                   motor=r, uc=uc_geri)
        assert 'wall_temperature_hot' in out['sug']
        assert 'data-safety-wall-unphysical' not in out['html']


# ---------------------------------------------------------------------------
# Kalem 8 + yeni anahtarlar — kanonik terim ve EN = TR
# ---------------------------------------------------------------------------
def test_kk3_i18n_charts_tr_blokta_lule_yok():
    kaynak = (_JS / 'i18n_charts.js').read_text(encoding='utf-8')
    tr_blok = kaynak[kaynak.index('\n        tr: {'):kaynak.index(
        '\n    };', kaynak.index('\n        tr: {'))]
    degerler = re.findall(r"^\s*'(?:[^'\\]|\\.)*': '((?:[^'\\]|\\.)*)',?$",
                          tr_blok, flags=re.M)
    assert degerler
    assert not [d for d in degerler if re.search(r'[Ll]üle', d)]


_KK3_ANAHTARLAR = (
    ('i18n_common.js', 'panel.uncertainty.errNonPhysicalInput'),
    ('i18n_common.js', 'panel.structural.notConsumed'),
    ('i18n_common.js', 'panel.structural.defaultNotSupplied'),
    ('i18n_common.js', 'panel.safety.wallPairUnphysical'),
    ('i18n_pages.js', 'solid.js.class.high'),
    ('i18n_pages.js', 'solid.js.class.inadequate_service'),
)


@pytest.mark.parametrize('dosya,anahtar', _KK3_ANAHTARLAR)
def test_kk3_anahtar_en_tr(dosya, anahtar):
    kaynak = (_JS / dosya).read_text(encoding='utf-8')
    bas = re.compile(r"^\s*'%s': '((?:[^'\\]|\\.)*)'," % re.escape(anahtar),
                     re.M)
    i = kaynak.index('\n        tr: {')
    en, tr = bas.findall(kaynak[:i]), bas.findall(kaynak[i:])
    assert len(en) == 1 and len(tr) == 1, (anahtar, en, tr)
    assert en[0] != tr[0]
