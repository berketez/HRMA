"""Bebek-Scofield arayüz bekçileri — F5-2, F5-5, F1-3 (parti 31).

Üç kusur da aynı sınıftan: **iki parça tek başına doğru, aralarındaki
sözleşme yanlış.** Üçü de arayüz tarafında yaşıyor ve üçü de yalnız gerçek
bir koşumla görülüyor; bu yüzden bu dosyadaki bekçilerin hiçbiri "kaynakta
şu dize var mı" ile yetinmez, gerçek çözücü yanıtını ve gerçek panel
kodunu (node içinde) koşturur.

F5-2 — YAPISAL PANEL CİDAR SICAKLIĞINI GÖNDERMİYOR
--------------------------------------------------
``/analyze_structural_safety`` ``wall_temperature_hot`` /
``wall_temperature_cold`` anahtarlarını BİRİNCİ ÖNCELİKLE okuyor
(``hrma/app.py``); yapısal modül de onları ``_estimate_wall_delta_T``
içinde 1. sırada kullanıyor. Analiz Güvertesi yapısal paneli ikisini de
HİÇ göndermiyordu, yani ısı zincirinin ÇÖZDÜĞÜ cidar sıcaklığı güverteye
ulaşmıyor, uç gaz sıcaklığından türeyen TAHMİN yoluna düşüyordu.

ÖLÇÜLDÜ (2026-08-17, ``examples/Example Hybrid N2O-HTPB 3kN.hrma``,
``/calculate`` -> panel ``fromResults`` -> ``/analyze_structural_safety``):

===========================  =============  ==========  ==========
                             T_iç [K]       SF_min      durum
===========================  =============  ==========  ==========
güverte (düzeltme öncesi)    729,9          4,000       MARGINAL
motorun kendi zinciri        3369,276       2,134       —
güverte (düzeltme sonrası)   3369,276       0,998       UNSAFE
===========================  =============  ==========  ==========

Yani güverte aynı motorun cidarını 4,6 kat soğuk gösteriyor ve emniyet
hükmünü o soğuk cidardan çıkarıyordu. Düzeltme sonrası güvertenin
sıcaklığı motorun sayısıyla BİT-AYNI. (Kalan SF farkının kaynağı ayrı bir
bulgudur — F5-1: ısı zinciri 5,0 mm cidar, yapısal zincir 18,789 mm.)

F5-5 — EKRANDA ``Reliability: NaN%``
------------------------------------
Sıvı sayfasının "Turbopump System" kartı ``turbopump.reliability``
anahtarını okuyup ``(x * 100).toFixed(1)`` basıyordu; çözücü bu anahtarı
HİÇ yayımlamıyor. Buradaki bekçi vaka listelemez, **tarar**: sıvı
şablonundaki her ``results.<yol>.toFixed(...)`` çağrısının yolu gerçek bir
``/calculate_liquid`` yanıtında GERÇEKTEN var mı diye bakar.

F1-3 — AYNI MANİFOLDA İKİ ÇAP
-----------------------------
ÖLÇÜLDÜ (aynı ``/calculate_liquid`` yanıtı, tek koşu):

=======  ==========================================  =======================
devre    ``injector_design.*_manifold_diameter_mm``  ``injector_design_detail
                                                     .*_circuit.manifold.d_mm``
=======  ==========================================  =======================
yakıt    23,5815 mm  (beyansız 2,5 x d_eş kuralı)    29,8285 mm (modellenmiş)
oksit.   32,8273 mm                                  41,5236 mm
=======  ==========================================  =======================

Oran her iki devrede de tam ``sqrt(10)/2,5 = 1,264911``: kaba kural alan
oranını 6,25 varsayıyor, devre modeli ise hedefini 10,0 olarak çözüyor
(Huzel & Huang). Kök düzeltme ÜRETİM MOTOR KODUNDADIR ve bu ajanın kapsamı
dışındadır; buradaki bekçi arayüz tarafının dürüstlüğünü kilitler:
kullanıcıya TEK değer gider ve o değer MODELLENMİŞ olandır.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'
EXAMPLES_DIR = REPO_ROOT / 'examples'
APP_PY = REPO_ROOT / 'hrma' / 'app.py'
STRUCTURAL_PANEL = PANELS_DIR / 'structural_panel.js'
DOCK_JS = STATIC_JS / 'analysis_dock.js'
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'
INJECTOR_PANEL = STATIC_JS / 'injector_panel.js'

# Uygulama yalnız geri döngü Host başlığına yanıt verir (DNS-rebinding kapısı)
HEADERS = {'Host': '127.0.0.1:8080'}

NAMES = {
    'hybrid': 'Example Hybrid N2O-HTPB 3kN',
    'solid': 'Example Solid KNDX BATES 75mm',
    'liquid': 'Example Liquid LOX-RP1 25kN',
}
ENDPOINTS = {
    'hybrid': '/calculate',
    'solid': '/calculate_solid',
    'liquid': '/calculate_liquid',
}

needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


def read(path):
    return pathlib.Path(path).read_text(encoding='utf-8')


def strip_js_comments(src):
    """// ve /* */ yorumlarını düşürür (dize içindeki // korunur değildir —
    bu dosyadaki kullanımlar için yeterli; her bekçi ayrıca canlı ölçümle
    desteklenir)."""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', src)


def deep_get(obj, path):
    cur = obj
    for key in path.split('.'):
        if not isinstance(cur, dict) or key not in cur:
            return None, False
        cur = cur[key]
    return cur, True


# ---------------------------------------------------------------------------
# Gerçek çözücü yanıtları (modül kapsamında bir kez)
# ---------------------------------------------------------------------------
def _calculate_payload(motor_type, fields):
    data = dict(fields)
    if motor_type == 'hybrid':
        if 'single_pressure' in data:
            data['atmospheric_pressure'] = data.pop('single_pressure')
        if 'thrust' in data and 'burn_time' in data:
            data['total_impulse'] = data['thrust'] * data['burn_time']
        data.setdefault('contraction_ratio', 0)
        data.setdefault('mass_flux_chamber', 0)
        data.setdefault('calculate_trajectory', False)
    return data


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def solver_results(client):
    """motor_type -> gerçek /calculate* yanıtı (uydurma yük yok)."""
    out = {}
    for motor_type in ('hybrid', 'solid', 'liquid'):
        project = json.loads(
            (EXAMPLES_DIR / (NAMES[motor_type] + '.hrma')).read_text(
                encoding='utf-8'))
        payload = _calculate_payload(motor_type, project['inputs']['fields'])
        resp = client.post(ENDPOINTS[motor_type], json=payload, headers=HEADERS)
        assert resp.status_code == 200, (
            f'{ENDPOINTS[motor_type]} {resp.status_code} döndü')
        out[motor_type] = resp.get_json()
    return out


# ---------------------------------------------------------------------------
# node koşum takımı — GERÇEK analysis_dock.js + GERÇEK panel dosyası
# ---------------------------------------------------------------------------
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [staticDir, panelList, resultsPath, motorType] = process.argv.slice(2);
const results = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this._attrs = {};
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.querySelectorAll = function () { return []; };

const documentStub = {
    head: new El('head'),
    body: new El('body'),
    readyState: 'complete',
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
    fetch: function () { return Promise.reject(new Error('sandbox: ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, isFinite: isFinite,
    parseFloat: parseFloat, parseInt: parseInt, document: documentStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function run(file) {
    vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox, { filename: file });
}

run(path.join(staticDir, 'analysis_dock.js'));
panelList.split(',').forEach(function (name) {
    run(path.join(staticDir, 'panels', name));
});
if (!sandbox.window.AnalysisDock) {
    console.log(JSON.stringify({ error: 'AnalysisDock yuklenmedi' }));
    process.exit(0);
}
sandbox.window.AnalysisDock._setMotorType(motorType);

const out = { motorType: motorType, panels: {} };
sandbox.window.AnalysisDock._registry.forEach(function (spec) {
    const rec = { fieldIds: [], defaults: {}, suggestions: {}, error: null };
    (spec.fields || []).forEach(function (f) {
        rec.fieldIds.push(f[0]);
        rec.defaults[f[0]] = Array.isArray(f[3]) ? '<select>' : f[2];
    });
    if (typeof spec.fromResults === 'function') {
        let sug = null;
        try { sug = spec.fromResults(results); }
        catch (e) { rec.error = String(e && e.message ? e.message : e); }
        if (sug && typeof sug === 'object') {
            Object.keys(sug).forEach(function (k) {
                rec.suggestions[k] = (sug[k] === undefined) ? null : sug[k];
            });
        }
    }
    out.panels[spec.id] = rec;
});
console.log(JSON.stringify(out));
"""


def _run_harness(results, motor_type, panel_files=('structural_panel.js',)):
    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, 'harness.js')
        payload = os.path.join(tmp, 'results.json')
        pathlib.Path(harness).write_text(HARNESS_JS, encoding='utf-8')
        pathlib.Path(payload).write_text(json.dumps(results), encoding='utf-8')
        proc = subprocess.run(
            ['node', harness, str(STATIC_JS), ','.join(panel_files),
             payload, motor_type],
            capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('node koşum takımı çöktü:\n'
                                  + proc.stderr[-3000:])
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert 'error' not in data, data.get('error')
    return data


@pytest.fixture(scope='module')
def panel_out(solver_results):
    return {mt: _run_harness(solver_results[mt], mt)
            for mt in ('hybrid', 'solid', 'liquid')}


# ===========================================================================
# F5-2 — ÇAPRAZ SÖZLEŞME: ucun okuduğu cidar sıcaklığı anahtarları ↔ panel
# ===========================================================================
def _uc_cidar_sicaklik_anahtarlari():
    """app.py'nin /analyze_structural_safety içinde okuduğu cidar anahtarları."""
    kaynak = read(APP_PY)
    blok = re.search(
        r"for wall_key in \(([^)]*)\):\s*\n\s*if data\.get\(wall_key\)",
        kaynak)
    assert blok, ('app.py cidar sıcaklığı okuma bloğu bulunamadı — bekçi kör. '
                  'Uç tarafı değiştiyse bu bekçi de aynı kalemde güncellenir.')
    return set(re.findall(r"'([^']+)'", blok.group(1)))


def _panel_cidar_sicaklik_alanlari():
    """structural_panel.js'in `fields` listesindeki cidar sıcaklığı alanları."""
    kaynak = strip_js_comments(read(STRUCTURAL_PANEL))
    blok = re.search(r'fields:\s*\[(.*?)\n\s*\],', kaynak, re.S)
    assert blok, 'structural_panel.js fields listesi bulunamadı — bekçi kör'
    adlar = set(re.findall(r"\['(wall_temperature_[a-z]+)'", blok.group(1)))
    return adlar


def test_yapisal_panel_cidar_sicakligi_alanlari_uc_ile_ayni():
    """F5-2 çekirdeği: uç ne okuyorsa panelde o alan olmalı (küme eşitliği).

    Bu bekçi sürüklenmenin İKİ yönünü de yakalar: panelden alan silinirse
    de, uca yeni bir cidar anahtarı eklenip panel güncellenmezse de kırılır.
    """
    uc = _uc_cidar_sicaklik_anahtarlari()
    panel = _panel_cidar_sicaklik_alanlari()
    assert uc, 'uç tarafı boş küme verdi — bekçi kör'
    assert uc == panel, (
        'Yapısal panel ile /analyze_structural_safety cidar sıcaklığı '
        'sözleşmesi AYRIŞMIŞ:\n'
        f'  uç okuyor  : {sorted(uc)}\n'
        f'  panel yolluyor: {sorted(panel)}\n'
        'Uç bu anahtarları BİRİNCİ ÖNCELİKLE kullanıyor; panel göndermezse '
        'ısı zincirinin çözdüğü cidar sıcaklığı güverteye hiç ulaşmaz ve '
        'hüküm gaz sıcaklığından türeyen TAHMİNE dayanır.')


def test_cidar_sicakligi_alanlari_istege_bagli_ve_bos_varsayilanli(panel_out):
    """0 K "verilmedi" ANLAMINA GELMEZ — varsayılan boş dize olmalı.

    ``analysis_dock.buildPayload`` sözleşmesi: sonlu sayısal varsayılanı olan
    alan ZORUNLUDUR (boşsa istek gönderilmez). Cidar sıcaklığı isteğe
    bağlıdır; ayrıca mutlak sıcaklıkta 0 gerçek bir değerdir, ``thrust``/
    ``wall_thickness`` alanlarındaki "0 = atla" sözleşmesi burada geçerli
    değildir.
    """
    varsayilanlar = panel_out['hybrid']['panels']['structural']['defaults']
    for alan in sorted(_panel_cidar_sicaklik_alanlari()):
        assert alan in varsayilanlar, f'{alan} panel alan listesinde yok'
        assert varsayilanlar[alan] == '', (
            f'{alan} varsayılanı {varsayilanlar[alan]!r}; boş dize olmalı — '
            'sayısal varsayılan alanı ZORUNLU yapar ve 0 K sahte bir '
            '"verilmedi" değeri olurdu.')


@needs_node
def test_hibritte_panel_motorun_cozdugu_cidar_sicakligini_tasiyor(
        solver_results, panel_out):
    """Panelin önerisi motorun ısı zincirinin çözdüğü sayıyla BİT-AYNI olmalı.

    Ölçülen kusur: panel hiç göndermiyordu ve uç 729,9 K'lik tahmine
    düşüyordu (motorun kendi sayısı 3369,276 K).
    """
    m = solver_results['hybrid']['motor']
    th = m['structural_analysis']['thermal_analysis']
    assert th['wall_temperature_source'] == 'heat_transfer_module', (
        'hibrit örnek motorda ısı zinciri artık cidar sıcaklığı çözmüyor — '
        'bu bekçinin dayanağı kaybolmuş, ölçüm yenilenmeli')

    sug = panel_out['hybrid']['panels']['structural']['suggestions']
    assert sug.get('wall_temperature_hot') == pytest.approx(
        th['wall_temperature_inner_K'], rel=0, abs=0), (
        'Panel ısı zincirinin çözdüğü SICAK yüz sıcaklığını taşımıyor: '
        f"panel {sug.get('wall_temperature_hot')} / "
        f"motor {th['wall_temperature_inner_K']}")
    assert sug.get('wall_temperature_cold') == pytest.approx(
        th['wall_temperature_outer_K'], rel=0, abs=0), (
        'Panel ısı zincirinin çözdüğü SOĞUK yüz sıcaklığını taşımıyor: '
        f"panel {sug.get('wall_temperature_cold')} / "
        f"motor {th['wall_temperature_outer_K']}")


@needs_node
def test_panelin_kurdugu_govde_ucta_cozulmus_cidarla_kosuyor(
        client, solver_results, panel_out):
    """CANLI kanıt: panelin gövdesi uca gidince uç ÇÖZÜLMÜŞ cidarı kullanır.

    Kusurun kendi senaryosu: panel cidar sıcaklığını göndermezse uç
    ``wall_temperature_source: 'chamber_temperature_estimate'`` döner ve
    T_iç 729,9 K'ye oturur. Bu bekçi tam o dönüşü kırmızıya çevirir.
    """
    sug = panel_out['hybrid']['panels']['structural']['suggestions']
    govde = {k: v for k, v in sug.items() if v is not None}
    resp = client.post('/analyze_structural_safety', json=govde,
                       headers=HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    th_uc = resp.get_json()['structural_analysis']['thermal_analysis']
    assert th_uc['wall_temperature_source'] == 'heat_transfer_module', (
        'Uç güverte gövdesiyle TAHMİN yoluna düştü '
        f"(kaynak: {th_uc['wall_temperature_source']}); panel cidar "
        'sıcaklığını göndermiyor demektir.')
    th_motor = (solver_results['hybrid']['motor']['structural_analysis']
                ['thermal_analysis'])
    assert th_uc['wall_temperature_inner_K'] == pytest.approx(
        th_motor['wall_temperature_inner_K'], rel=0, abs=0), (
        'Güverte ile motor aynı motor için FARKLI cidar sıcaklığı veriyor: '
        f"güverte {th_uc['wall_temperature_inner_K']} / "
        f"motor {th_motor['wall_temperature_inner_K']}")


@needs_node
@pytest.mark.parametrize('motor_type', ['liquid', 'solid'])
def test_beyani_cozulmus_demeyen_cidar_sicakligi_geri_beslenmez(
        solver_results, panel_out, motor_type):
    """Sahte veri kapısı: VARSAYIM sayı ölçüm gibi geri beslenmez.

    ÖLÇÜLDÜ: sıvı örnek motorda ``cooling_system.wall_temperature_source ==
    'assumed (cooling-type default)'`` ve değerler 800,0 / 350,0 K yuvarlak
    tasarım varsayımları. Katı zincir cidar sıcaklığı hiç yayımlamıyor.
    İki durumda da panel alanları BOŞ kalmalı; uç kendi beyanlı tahmin
    yoluna girer ve panel bunu ekranda söyler.
    """
    r = solver_results[motor_type]
    m = r.get('motor') or r
    if motor_type == 'liquid':
        kaynak = (m.get('cooling_system') or {}).get('wall_temperature_source')
        assert isinstance(kaynak, str) and kaynak.lower().startswith('assumed'), (
            'sıvı örnek motorun cidar sıcaklığı artık VARSAYIM değil '
            f'({kaynak!r}) — bu bekçinin dayanağı değişmiş, ölçüm yenilenmeli')
    else:
        th = (m.get('structural_analysis') or {}).get('thermal_analysis')
        assert not isinstance(th, dict) or not th.get('wall_temperature_source'), (
            'katı zincir artık cidar sıcaklığı beyanı yayımlıyor — ölçüm '
            'yenilenmeli')

    sug = panel_out[motor_type]['panels']['structural']['suggestions']
    for alan in sorted(_panel_cidar_sicaklik_alanlari()):
        assert sug.get(alan) is None, (
            f'{motor_type}: panel {alan} alanına {sug.get(alan)!r} öneriyor; '
            'çözücü bu sayıyı ÇÖZMEDİ (varsayım / hiç yok). Varsayımı ölçüm '
            'gibi geri beslemek sahte veridir.')


def test_panel_cidar_sicakligi_kaynagini_ekranda_soyluyor():
    """Uç ``wall_temperature_source`` beyanını gönderiyor; panel BASMALI.

    Termal gerilme, mukavemet deratingi ve servis sıcaklığı hükmü bu iki
    sayıdan türüyor. Hangisinin ÇÖZÜM hangisinin TAHMİN olduğu ekranda
    yazmazsa kullanıcı tahmini ölçüm sanır (``designBasisBlock`` ile aynı
    gerekçe).
    """
    kaynak = strip_js_comments(read(STRUCTURAL_PANEL))
    assert 'wall_temperature_source' in kaynak, (
        'structural_panel.js ucun cidar sıcaklığı kaynak beyanını okumuyor')
    assert 'thermal_analysis' in kaynak, (
        'structural_panel.js structural_analysis.thermal_analysis bloğunu '
        'okumuyor — cidar sıcaklığı beyanı oradan gelir')
    for sabit in ('heat_transfer_module', 'chamber_temperature_estimate',
                  'not_evaluated'):
        assert sabit in kaynak, (
            f'panel {sabit!r} kaynak değerini tanımıyor; modülün üç beyanı da '
            'ekranda ayırt edilebilmeli')


def test_dock_cidar_sicakligi_okuyucusu_kaynak_kapisi_tasiyor():
    """Merkezî okuyucu, çözücünün kaynak beyanına BAKMADAN değer taşımamalı."""
    kaynak = strip_js_comments(read(DOCK_JS))
    assert 'readWallTemperaturesK' in kaynak, (
        'analysis_dock.js merkezî cidar sıcaklığı okuyucusunu kaybetmiş')
    fn = re.search(r'function readWallTemperaturesK\(r\)\s*\{(.*?)\n    \}',
                   kaynak, re.S)
    assert fn, 'readWallTemperaturesK gövdesi bulunamadı — bekçi kör'
    govde = fn.group(1)
    assert 'wallTempSourceIsSolved' in govde, (
        'readWallTemperaturesK kaynak beyanı kapısını atlıyor: çözülmemiş '
        '(varsayım/tahmin) bir sıcaklık ölçüm gibi geri beslenebilir.')


RENDER_HARNESS_JS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const [staticDir, dataPath] = process.argv.slice(2);
const datasets = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
function El(t) {
    this.tagName = String(t || 'div').toUpperCase();
    this.children = []; this.style = {}; this.dataset = {};
    this._a = {}; this.innerHTML = '';
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._a, k) ? this._a[k] : null;
};
El.prototype.querySelectorAll = function () { return []; };
const doc = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: setInterval, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('sandbox: ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, isFinite: isFinite,
    parseFloat: parseFloat, parseInt: parseInt, document: doc,
};
sb.window = sb; sb.globalThis = sb; vm.createContext(sb);
function run(f) { vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
run(path.join(staticDir, 'analysis_dock.js'));
run(path.join(staticDir, 'panels', 'structural_panel.js'));
const out = {};
Object.keys(datasets).forEach(function (k) {
    const root = new El('div');
    try { sb.window.StructuralPanel._render(datasets[k], root);
          out[k] = { ok: true, html: root.innerHTML }; }
    catch (e) { out[k] = { ok: false, err: String((e && e.stack) || e) }; }
});
console.log(JSON.stringify(out));
"""


@needs_node
def test_panel_ciziminde_cidar_sicakligi_rozeti_beyanla_ayni(
        client, solver_results):
    """Panel GERÇEKTEN çizilir: rozet ucun beyanıyla aynı şeyi söylemeli.

    İki uç durum aynı motorla koşturulur: (1) güvertenin bugün gönderdiği
    tam gövde — çözülmüş cidar; (2) hiçbir sıcaklık girdisi olmayan gövde —
    termal yol koşmadı. Rozet ikisinde de doğru olmalı ve hiçbir çizimde
    NaN kullanıcıya ulaşmamalı.
    """
    m = solver_results['hybrid']['motor']
    th = m['structural_analysis']['thermal_analysis']
    tam = {
        'chamber_pressure': m['chamber_pressure'],
        'chamber_diameter': m['chamber_diameter'],
        'chamber_length': m['chamber_length'],
        'throat_diameter': m['throat_diameter'],
        'burn_time': m['burn_time'],
        'chamber_temperature': m['chamber_temperature'],
        'thrust': m['thrust'],
        'material': 'steel_4130',
        'wall_thickness': 0.005,
        'wall_temperature_hot': th['wall_temperature_inner_K'],
        'wall_temperature_cold': th['wall_temperature_outer_K'],
    }
    sicaksiz = {k: v for k, v in tam.items()
                if k not in ('wall_temperature_hot', 'wall_temperature_cold',
                             'chamber_temperature')}
    veri = {}
    for ad, govde in (('cozulmus', tam), ('sicaklik_yok', sicaksiz)):
        resp = client.post('/analyze_structural_safety', json=govde,
                           headers=HEADERS)
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
        veri[ad] = resp.get_json()

    with tempfile.TemporaryDirectory() as tmp:
        h = os.path.join(tmp, 'render.js')
        d = os.path.join(tmp, 'data.json')
        pathlib.Path(h).write_text(RENDER_HARNESS_JS, encoding='utf-8')
        pathlib.Path(d).write_text(json.dumps(veri), encoding='utf-8')
        proc = subprocess.run(['node', h, str(STATIC_JS), d],
                              capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr[-3000:]
    ciz = json.loads(proc.stdout.strip().splitlines()[-1])

    for ad in ('cozulmus', 'sicaklik_yok'):
        assert ciz[ad]['ok'], f'{ad} çizimi çöktü:\n{ciz[ad].get("err")}'
        assert 'NaN' not in ciz[ad]['html'], (
            f'{ad}: yapısal panel çiziminde NaN kullanıcıya ulaşıyor')

    assert 'SOLVED' in ciz['cozulmus']['html'], (
        'Çözülmüş cidar sıcaklığıyla koşan panel bunu ekranda SÖYLEMİYOR; '
        'kullanıcı hükmün dayanağını göremez.')
    assert 'NOT EVALUATED' in ciz['sicaklik_yok']['html'], (
        'Termal yol koşmadığı hâlde panel bunu ekranda söylemiyor — '
        'hesaplanmamış bir cidar sıcaklığı hesaplanmış gibi görünür.')
    # Hesaplanmamış durumda SAYI BASILMAZ (uç zaten None'a çekiyor).
    assert 'Hot-side (inner) wall' not in ciz['sicaklik_yok']['html'], (
        'Termal yol koşmadığı hâlde panel cidar sıcaklığı satırlarını '
        'basıyor — hesaplanmamış değer yayımlanmaz.')


# ===========================================================================
# F5-5 — sıvı sayfasında NaN taraması
# ===========================================================================
#: Şablonda ``results.<yol>`` üzerinde doğrudan sayısal biçimlendirme
#: çağıran desen. Vaka listelemez: yeni yazılan her çağrı da taranır.
_RESULT_PATH = re.compile(
    r'results\.([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)'
    r'\s*(?:\*\s*[\d.]+\s*\)?\s*)?\.(toFixed|toLocaleString)\s*\(')


def test_sivi_sayfasinda_bicimlendirilen_her_yol_yanitta_var(solver_results):
    """TARAYICI (F5-5): ``.toFixed``/``.toLocaleString`` çağrılan her yol
    gerçek bir ``/calculate_liquid`` yanıtında bulunmalı.

    Bulunmayan yol ``undefined`` demektir; ``undefined.toFixed`` çöker,
    ``(undefined * 100).toFixed(1)`` ise sessizce ``"NaN"`` basar. Ölçülen
    vaka tam ikincisiydi: ekranda her koşuda ``Reliability: NaN%``.
    """
    r = solver_results['liquid']
    eksik = {}
    for i, satir in enumerate(read(LIQUID_HTML).splitlines(), 1):
        for m in _RESULT_PATH.finditer(satir):
            yol = m.group(1)
            _, var = deep_get(r, yol)
            if not var:
                eksik.setdefault(yol, []).append(i)
    assert not eksik, (
        'Sıvı şablonu çözücünün YAYIMLAMADIĞI yolları biçimlendiriyor '
        '(NaN / çökme riski):\n'
        + '\n'.join('  results.%s  -> satır %s' % (y, s)
                    for y, s in sorted(eksik.items())))


@needs_node
def test_turbopompa_guvenilirlik_hucresi_nan_basmaz(solver_results):
    """Hücrenin KENDİSİ koşturulur: gerçek yanıtla çıktı NaN içermemeli.

    Şablondan ``_liquidReliabilityCell`` işlevi çıkarılıp node içinde
    gerçek turbopompa sözlüğüyle çağrılır — kaynakta dize aranmaz.
    """
    src = read(LIQUID_HTML)
    fn = re.search(r'function _liquidReliabilityCell\(tp\)\s*\{.*?\n        \}',
                   src, re.S)
    assert fn, ('liquid.html içinde _liquidReliabilityCell bulunamadı — '
                'güvenilirlik hücresi doğrudan şablona geri yazılmış olabilir')
    tp = (solver_results['liquid'].get('feed_system') or {}).get('turbopump')
    assert isinstance(tp, dict), 'sıvı örnek motorda turbopump bloğu yok'

    program = (
        "function T(k, f) { return f; }\n"
        + fn.group(0) + "\n"
        + "const tp = " + json.dumps(tp) + ";\n"
        + "console.log(JSON.stringify({ out: _liquidReliabilityCell(tp) }));\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'cell.js')
        pathlib.Path(p).write_text(program, encoding='utf-8')
        proc = subprocess.run(['node', p], capture_output=True, text=True,
                              timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])['out']
    assert 'NaN' not in out, (
        f'Turbopompa güvenilirlik hücresi ekrana {out!r} basıyor — '
        'çözücünün yayımlamadığı bir sayı biçimlendiriliyor.')
    assert 'Infinity' not in out, f'hücre {out!r} basıyor'
    # Çözücü bu koşuda güvenilirlik yayımlamıyorsa hücre YOKLUĞU ADIYLA
    # söylemeli — boş hücre de sessiz bir yalandır.
    if not isinstance(tp.get('reliability'), (int, float)):
        assert out.strip(), 'hücre boş; yokluk beyan edilmiyor'
        assert 'reliability' in out.lower() or 'model' in out.lower(), (
            f'hücre yokluğun nedenini söylemiyor: {out!r}')


def test_turbopompa_karti_ham_carpimla_yuzde_basmiyor():
    """Kusurun kendi yazım biçimi geri gelirse kırılır.

    Eski satır: ``${(results.feed_system.turbopump.reliability * 100)
    .toFixed(1)}%`` — sonluluk sınamayan doğrudan çarpım.
    """
    src = read(LIQUID_HTML)
    assert not re.search(
        r'results\.feed_system\.turbopump\.reliability\s*\*\s*100\s*\)\s*\.toFixed',
        src), ('Turbopompa güvenilirliği yine sonluluk sınanmadan '
               'biçimlendiriliyor — NaN geri geldi.')


# ===========================================================================
# F1-3 — aynı manifolda iki çap: kullanıcıya TEK değer gider
# ===========================================================================
#: Kaba kural (2,5 x d_eş) ile yayımlanan, künyesi/beyanı OLMAYAN anahtarlar.
KABA_KURAL_MANIFOLD_ANAHTARLARI = ('fuel_manifold_diameter_mm',
                                   'oxidizer_manifold_diameter_mm')

#: Arayüz dosyaları: kullanıcıya sayı gösteren her yüzey.
def _arayuz_dosyalari():
    dosyalar = sorted(TEMPLATES.glob('*.html'))
    dosyalar += sorted(STATIC_JS.glob('*.js'))
    dosyalar += sorted(PANELS_DIR.glob('*.js'))
    return dosyalar


def test_kaba_kural_manifold_capi_ekrana_cikmiyor():
    """F1-3 arayüz yarısı: iki çaptan yalnız MODELLENMİŞ olan gösterilir.

    Kaba kural anahtarları yanıtta duruyor (kök düzeltme motor kodundadır)
    ama arayüzde OKUNMUYOR. Biri ekrana bağlanırsa kullanıcı aynı manifold
    için iki farklı sayı görür ve hangisinin ne olduğunu ayırt edemez —
    bu bekçi tam o anda kırılır.
    """
    ihlal = []
    for dosya in _arayuz_dosyalari():
        kaynak = read(dosya)
        for anahtar in KABA_KURAL_MANIFOLD_ANAHTARLARI:
            for i, satir in enumerate(kaynak.splitlines(), 1):
                if anahtar in satir:
                    ihlal.append(f'{dosya.name}:{i}  {satir.strip()[:90]}')
    assert not ihlal, (
        'Arayüz kaba kural manifold çapını okuyor:\n  '
        + '\n  '.join(ihlal)
        + '\nAynı manifold için modellenmiş devre çapı da yayımlanıyor '
          '(injector_design_detail.*_circuit.manifold.d_mm). İki sayı birden '
          'gösterilecekse her biri ADIYLA ve KAYNAĞIYLA gösterilmeli; '
          'etiketsiz ikinci bir sayı kullanıcıyı yanıltır.')


def test_enjektor_paneli_modellenmis_devre_capini_okuyor():
    """Ekrandaki manifold çapı devre modelinin çözdüğü değer olmalı."""
    kaynak = strip_js_comments(read(INJECTOR_PANEL))
    assert re.search(r'c\.manifold\b', kaynak), (
        'injector_panel.js devre manifold bloğunu okumuyor')
    assert re.search(r'\bman\.d_mm\b', kaynak), (
        'injector_panel.js modellenmiş manifold çapını (manifold.d_mm) '
        'basmıyor — ekrandaki sayı devre modelinden gelmiyor olabilir.')


def test_iki_manifold_capi_celisiyorsa_ekranda_tek_deger_var(solver_results):
    """Çelişki DURDUKÇA arayüzün tek değer göstermesi zorunludur.

    Bekçi çelişkiyi DONDURMAZ: motor kodu iki sayıyı uzlaştırırsa (ya da
    kaba kural kalkarsa) bu test yine yeşil kalır. Yalnız çelişki
    sürerken arayüzün iki sayıyı birden, etiketsiz göstermesini yasaklar.
    """
    r = solver_results['liquid']
    kaba = r.get('injector_design') or {}
    detay = ((r.get('injection_system') or {})
             .get('injector_design_detail') or {})
    ciftler = [
        ('fuel_manifold_diameter_mm', 'fuel_circuit'),
        ('oxidizer_manifold_diameter_mm', 'ox_circuit'),
    ]
    celisen = []
    for kaba_anahtar, devre in ciftler:
        a = kaba.get(kaba_anahtar)
        b = ((detay.get(devre) or {}).get('manifold') or {}).get('d_mm')
        if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
            continue
        if abs(a - b) > 0.01 * max(abs(a), abs(b)):
            celisen.append((kaba_anahtar, a, b))
    if not celisen:
        pytest.skip('iki manifold çapı artık çelişmiyor — kök düzeltme inmiş')
    # Çelişki sürüyor: arayüz kaba kural değerini GÖSTERMEMELİ.
    test_kaba_kural_manifold_capi_ekrana_cikmiyor()
