"""Faz 5 — arayüz (şablon + JS) katmanının bekçileri.

Faz 5 avında yedi salt-okunur ajan ölçüm yaptı. Bu dosya, o raporlardan
ARAYÜZ TARAFINA düşen kalemleri kalıcı olarak kilitler. Her testin başında
ölçülen değer yazılıdır; hiçbiri "böyle olmalı" varsayımı değildir.

Kapsanan kalemler
-----------------
H3-B8  ``/api/thermal-protection`` panelde bir sayısal alan BOŞALTILDIĞINDA
       500 dönüyordu. Ölçüm (2026-08-03, ``app.test_client``, mode=ablative):

           tam gövde                  -> HTTP 200
           q_net_W_m2 alanı boş ('')  -> HTTP 500
             {"error":"ThermalProtectionAnalyzer.ablative_thickness()
               missing 1 required positional argument: 'q_net_W_m2'"}

       Kök neden panelde: ``buildPayload`` sonlu olmayan alanı payload'a hiç
       koymuyordu ("backend kendi varsayılanını kullanır"), ama uç için o
       argüman ZORUNLUYDU. Artık istek gönderilmez, eksik alan kullanıcıya
       adıyla söylenir. Uydurma varsayılan KONMAZ.

H3-B9  Üç uç RFC 8259 dışı JSON yayımlıyor (ölçüldü, HTTP 200):
           /api/altitude-to-pressure  {"altitude":-Infinity,...}
           /api/oxidizer-properties   ..."temperature":Infinity}
           /api/regression-analysis   "port_diameter":[30.0,Infinity,...]
       Tarayıcıda ``response.json()`` bunda PATLAR. Panel tarafında hata
       yutulmamalı ve kullanıcı ayrıştırıcı gürültüsü değil açık bir metin
       görmeli.

H3-B10 ``chamber_temperature`` ``/calculate``'te ölü girdi. ARAYÜZ TARAFINDA
       bulgu GEÇERSİZ: hiçbir şablon bu alanı girdi olarak göndermiyor.
       Bu test o durumu kilitler (ileride biri sessizce eklerse kırılır).

H4-11  ``solid.html`` kür sıcaklığı K -> °C çevriminde 273 kullanıyordu;
       mutlak sıfır 273,15 K'dir.

Yöntem: JS metnine bakan regex testlerinin yanında, ``analysis_dock.js``
GERÇEKTEN node içinde sahte bir DOM ile çalıştırılır ve panelin uca
GÖNDERDİĞİ (ya da göndermediği) şey ölçülür — "yazılmış mı" değil,
"ne yapıyor" sınanır.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'

NODE = shutil.which('node')


def read(path):
    return path.read_text(encoding='utf-8')


# ===========================================================================
# H3-B8 / H3-B9 — analysis_dock.js DAVRANIŞ testi (node + sahte DOM)
# ===========================================================================
#
# analysis_dock.js modül içi ``buildPayload`` / ``runPanel`` dışa açık değil.
# Bu yüzden gerçek dosya bir vm bağlamında yüklenir, sahte DOM ``init()`` ve
# ``mountPanel()`` yolunu yürütür ve "Run Analysis" düğmesine kayıtlı GERÇEK
# dinleyici tetiklenir. Ölçülen: fetch çağrıldı mı, gövdesi ne, durum satırına
# ne yazıldı.
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [staticDir, scenario] = process.argv.slice(2);

// --- asgari sahte DOM ------------------------------------------------------
// innerHTML AYRIŞTIRILMAZ: mountPanel'in ürettiği HTML atılır, ihtiyaç
// duyulan düğümler getElementById üzerinden talep anında üretilir. Test
// edilen şey düzen değil, VERİ AKIŞI (hangi gövde uca gidiyor).
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.classList = { contains: function () { return false; }, add: function () {} };
    this._attrs = {};
    this.textContent = '';
    this.innerHTML = '';
    this.disabled = false;
    this.value = '';
    this.options = [];
    this._listeners = {};
}
Object.defineProperty(El.prototype, 'firstElementChild', {
    get: function () { return this._first || (this._first = new El('div')); }
});
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.remove = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
};
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };

const byId = {};
function getEl(id) {
    if (!byId[id]) byId[id] = new El('div');
    return byId[id];
}

// Panelin form alanları: [alanAdı, etiket, varsayılan, adım]
// protection_panel.js'in GERÇEK alan kalıbı: zorunlu alanlar sayısal
// varsayılan taşır, isteğe bağlı olanlar '' taşır ve etiketinde söyler.
const SPEC_FIELDS = [
    ['mode', 'Analysis Mode', 'ablative', [['ablative', 'Ablative']]],
    ['q_net_W_m2', '[A] Net Heat Flux (W/m2)', 2000000, 100000],
    ['burn_time_s', '[A/H] Burn Time (s)', 10, 0.5],
    ['q_star_MJ_kg', '[A] Q* Override (MJ/kg, blank = band)', '', 0.5]
];

function makeField(name, tagName, value) {
    const el = new El(tagName);
    el.setAttribute('data-field', name);
    el.value = value;
    return el;
}

const fieldEls = [
    makeField('mode', 'select', 'ablative'),
    makeField('q_net_W_m2', 'input', '2000000'),
    makeField('burn_time_s', 'input', '10'),
    makeField('q_star_MJ_kg', 'input', '')
];
if (scenario === 'zorunlu_alan_bos') {
    fieldEls[1].value = '';          // q_net_W_m2 boşaltıldı
}

const sec = getEl('ad_sec_p_test');
sec.querySelectorAll = function (selector) {
    return selector === '[data-field]' ? fieldEls : [];
};

const documentStub = {
    head: new El('head'),
    body: new El('body'),
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: getEl,
    addEventListener: function () {},
};

const calls = [];
function fakeFetch(url, opts) {
    calls.push({ url: url, body: opts && opts.body });
    let text = '{"status":"success","ok":1}';
    if (scenario === 'gecersiz_json') {
        // /api/altitude-to-pressure altitude=-inf ile ÖLÇÜLEN gerçek gövde
        text = '{"altitude":-Infinity,"pressure":Infinity,"temperature":Infinity}';
    }
    return Promise.resolve({
        ok: true,
        status: 200,
        text: function () { return Promise.resolve(text); },
        json: function () { return Promise.resolve(JSON.parse(text)); }
    });
}

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    fetch: fakeFetch,
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Promise: Promise, Error: Error,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'analysis_dock.js'), 'utf8'),
                sandbox, { filename: 'analysis_dock.js' });

const rendered = [];
sandbox.window.AnalysisDock.register({
    id: 'p_test',
    title: 'Test panel',
    category: 'THERMAL',
    endpoint: '/api/thermal-protection',
    fields: SPEC_FIELDS,
    render: function (data) { rendered.push(data); }
});
sandbox.window.AnalysisDock.init({ motorType: 'hybrid' });

const btn = getEl('ad_run_p_test');
const listeners = btn._listeners.click || [];
if (!listeners.length) {
    console.log(JSON.stringify({ error: 'Run düğmesine dinleyici bağlanmadı' }));
    process.exit(0);
}
listeners[0]();

setTimeout(function () {
    console.log(JSON.stringify({
        fetchCount: calls.length,
        body: calls.length ? calls[0].body : null,
        status: getEl('ad_status_p_test').textContent,
        rendered: rendered.length,
        buttonDisabled: btn.disabled
    }));
}, 60);
"""


def run_harness(tmp_path, scenario):
    harness = tmp_path / 'faz5_dock_harness.js'
    harness.write_text(HARNESS_JS, encoding='utf-8')
    result = subprocess.run(
        [NODE, str(harness), str(STATIC_JS), scenario],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, 'node koşumu hata verdi:\n' + result.stderr
    out = result.stdout.strip().splitlines()
    assert out, 'koşum çıktı üretmedi:\n' + result.stdout + result.stderr
    data = json.loads(out[-1])
    assert 'error' not in data, data['error']
    return data


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_dock_bos_zorunlu_alanda_istek_gondermez(tmp_path):
    """H3-B8: zorunlu alan boşsa uca HİÇ gidilmez, eksik alan söylenir.

    ÖNCE (ölçüldü): boş alan payload'dan düşüyordu, uç 500 +
    "missing 1 required positional argument: 'q_net_W_m2'" döndürüyordu.
    SONRA: fetch hiç çağrılmıyor, durum satırı alan adını yazıyor.
    """
    data = run_harness(tmp_path, 'zorunlu_alan_bos')
    assert data['fetchCount'] == 0, (
        'zorunlu alan boşken uca yine istek gitti (gövde: %s)' % data['body'])
    assert '[A] Net Heat Flux (W/m2)' in data['status'], (
        'eksik alan kullanıcıya adıyla söylenmiyor: %r' % data['status'])
    assert data['rendered'] == 0, 'istek gitmediği hâlde bir şey çizildi'
    assert data['buttonDisabled'] is False, (
        'istek gönderilmedi ama düğme kilitli kaldı')


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_dock_dolu_formda_istek_gonderilir_ve_istege_bagli_alan_atlanir(tmp_path):
    """Yanlış pozitif kapısı: yalnız boş bırakılan İSTEĞE BAĞLI alan varsa
    istek normal gider ve o anahtar gövdeye konmaz.

    Bu ayrım panel tanımından gelir: varsayılanı sonlu sayı olan alan
    zorunlu, varsayılanı '' olan alan isteğe bağlıdır (protection_panel
    q_star_MJ_kg / emissivity, vessel_panel wall_thickness_mm,
    joint_panel external_axial_load_n).
    """
    data = run_harness(tmp_path, 'normal')
    assert data['fetchCount'] == 1, 'dolu formda istek gönderilmedi'
    body = json.loads(data['body'])
    assert body['q_net_W_m2'] == 2000000
    assert body['burn_time_s'] == 10
    assert body['mode'] == 'ablative'
    assert 'q_star_MJ_kg' not in body, (
        'boş bırakılan İSTEĞE BAĞLI alan gövdeye uydurma değerle kondu: %s'
        % body)
    assert data['status'] == '', 'başarılı koşuda hata satırı kaldı'
    assert data['rendered'] == 1


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_dock_gecersiz_json_govdesinde_acik_hata_gosterir(tmp_path):
    """H3-B9: uç Infinity yayarsa panel boş kalmaz, açık hata gösterir.

    Gövde, /api/altitude-to-pressure'ın altitude=-inf ile ÖLÇÜLEN gerçek
    yanıtıdır. Kullanıcı tarayıcının "Unexpected token" gürültüsünü değil,
    ne olduğunu anlatan bir cümle görmeli.
    """
    data = run_harness(tmp_path, 'gecersiz_json')
    assert data['fetchCount'] == 1
    assert data['rendered'] == 0, 'ayrıştırılamayan yanıtla çizim yapıldı'
    status = data['status']
    assert status, 'geçersiz JSON sessizce yutuldu (durum satırı boş)'
    assert 'not valid JSON' in status, (
        'geçersiz JSON hatası açıkça adlandırılmıyor: %r' % status)
    assert 'Unexpected token' not in status, (
        'kullanıcıya ham ayrıştırıcı mesajı gösteriliyor: %r' % status)
    assert data['buttonDisabled'] is False, 'düğme kilitli kaldı'


# ===========================================================================
# H3-B9 — advanced.html: iki fetch de katı JSON okuyucudan geçer
# ===========================================================================
def test_advanced_json_okuyucu_tanimli_ve_kullaniliyor():
    src = read(TEMPLATES / 'advanced.html')
    assert 'async function readJsonBodyStrict(' in src, (
        'advanced.html katı JSON okuyucusunu tanımlamıyor')
    # Ölçülen iki sızıntı ucu bu okuyucudan geçmeli.
    for endpoint in ('/api/oxidizer-properties', '/api/regression-analysis'):
        idx = src.index(endpoint)
        window = src[idx:idx + 2500]
        assert 'readJsonBodyStrict(response)' in window, (
            '%s çağrısı hâlâ korumasız response.json() kullanıyor' % endpoint)
        assert 'await response.json()' not in window, (
            '%s çağrısında korumasız response.json() kaldı' % endpoint)


def test_advanced_json_hatasi_konsola_ve_ekrana_gider():
    """Hata YUTULMAZ: ham gövde konsola, açıklama istisnaya gider."""
    src = read(TEMPLATES / 'advanced.html')
    body_start = src.index('async function readJsonBodyStrict(')
    body = src[body_start:body_start + 1600]
    assert 'console.error' in body, 'ham gövde konsola yazılmıyor'
    assert 'throw new Error' in body, 'hata yukarı fırlatılmıyor (yutuluyor)'
    assert 'common.badJson' in body, 'hata metni çeviri anahtarı kullanmıyor'


def test_badjson_anahtari_iki_dilde_var():
    dict_js = read(STATIC_JS / 'i18n_common.js')
    assert dict_js.count("'common.badJson'") == 2, (
        "common.badJson anahtarı EN ve TR'de birer kez bulunmalı")
    assert dict_js.count("'dock.missingFields'") == 2, (
        "dock.missingFields anahtarı EN ve TR'de birer kez bulunmalı")


# ===========================================================================
# H3-B10 — chamber_temperature arayüzden GÖNDERİLMİYOR (bulgu geçersiz)
# ===========================================================================
def test_chamber_temperature_arayuzden_gonderilmiyor():
    """``/calculate`` ``chamber_temperature`` girdisini yok sayıyor (ölçüldü:
    2500 / 3500 / 0 / -3000 gönderildiğinde yanıt BİT-AYNI, her seferinde
    çözücünün bulduğu 3307,13 K dönüyor).

    Arayüz tarafında bulgu GEÇERSİZ: hiçbir şablonda bu ada sahip bir giriş
    alanı yok ve hesap gövdesini kuran ``getFormData`` bu anahtarı taşımıyor.
    Sessizce yok sayılan girdi ARAYÜZDE YOK; bu test onu böyle tutar.
    """
    for name in ('index.html', 'advanced.html', 'liquid.html', 'solid.html'):
        src = read(TEMPLATES / name)
        assert 'id="chamber_temperature"' not in src, (
            '%s içine chamber_temperature giriş alanı eklenmiş; '
            '/calculate bu alanı yok sayıyor' % name)
        assert 'name="chamber_temperature"' not in src, name

    adv = read(TEMPLATES / 'advanced.html')
    start = adv.index('function getFormData()')
    end = adv.index('\n        }', start)
    assert 'chamber_temperature' not in adv[start:end], (
        'getFormData chamber_temperature gönderiyor; /calculate bu alanı '
        'sessizce yok sayar (ölçüldü: değer ne olursa olsun yanıt bit-aynı)')


# ===========================================================================
# H4-11 — Kelvin -> Celsius sabiti
# ===========================================================================
def test_kelvin_celsius_cevriminde_273_15_kullanilir():
    """ÖLÇÜLDÜ (examples/Example Solid KNDX BATES 75mm.hrma -> /calculate_solid):
    ``curing_process.temperature_k = 398.0``.
      önce : 398,0 - 273    = 125,00
      sonra: 398,0 - 273,15 = 124,85
    0 ondalıkla iki gösterim de "125 °C"dir; düzeltilen şey sabittir.
    """
    src = read(TEMPLATES / 'solid.html')
    assert 'v - 273.15' in src, 'K -> °C çevrimi 273,15 kullanmıyor'
    # Yalnız KOD desenine bakılır (`v - 273`), yorum metnine değil.
    kotu = re.findall(r'\bv\s*-\s*273(?!\.15)(?![\d.])', src)
    assert not kotu, 'K -> °C çevriminde hâlâ 273 kullanan yer var: %s' % kotu


# ===========================================================================
# H1-B10 — 6DOF paneli null alanlarda çökmez, uydurma hüküm basmaz
# ===========================================================================
#
# Uç ölçemediği büyüklüğü bilerek null yayımlıyor. ÖLÇÜLDÜ (2026-08-03,
# POST /api/six-dof-analysis, {dry_mass:20, propellant_mass:10, thrust:3000,
# burn_time:5, t_max:1}) -> HTTP 200 ve:
#   {"apogee":null,"apogee_time":null,"stable":null,
#    "max_mach":0.27473448283522395,"max_alpha_deg":0.0,
#    "static_margin_full":4.841810538672934,
#    "static_margin_empty":5.841810538672935,
#    "cn_alpha":11.106843491233196,"x_cp":1.5841810538672936,
#    "max_speed":93.44179868510761,"end_reason":"time_limit"}
#
# Panelin rozet bloğu GERÇEK dosyadan kesilip node içinde çalıştırılır.
BADGE_BLOCK_START = 'const numOf = (v) =>'
BADGE_BLOCK_END = 'badges.innerHTML = html;'

# time_limit ölçümünün birebir kendisi
SUMMARY_TIME_LIMIT = {
    'apogee': None, 'apogee_time': None, 'stable': None,
    'max_mach': 0.27473448283522395, 'max_alpha_deg': 0.0,
    'static_margin_full': 4.841810538672934,
    'static_margin_empty': 5.841810538672935,
    'cn_alpha': 11.106843491233196, 'x_cp': 1.5841810538672936,
    'max_speed': 93.44179868510761, 'end_reason': 'time_limit',
}
# solver_failed yolunda alanların TAMAMI null (H1 raporu, dry_mass=0)
SUMMARY_SOLVER_FAILED = {k: None for k in SUMMARY_TIME_LIMIT}
SUMMARY_SOLVER_FAILED['end_reason'] = 'solver_failed'


def _badge_block():
    src = read(STATIC_JS / 'sixdof_panel.js')
    start = src.index(BADGE_BLOCK_START)
    end = src.index(BADGE_BLOCK_END, start)
    return src[start:end]


def _run_badge_block(tmp_path, summary, name):
    script = tmp_path / ('sixdof_badges_%s.js' % name)
    script.write_text(
        "'use strict';\n"
        "const s = " + json.dumps(summary) + ";\n"
        "const usedCurve = true;\n"   # render(data, usedCurve) imzasından
        "function badge(text, kind) { return '[' + kind + ']' + text + '\\n'; }\n"
        "function T(k, f) { return f; }\n"
        "function TF(k, p, f) {\n"
        "  return String(f).replace(/\\{(\\w+)\\}/g,"
        " (w, n) => (p && n in p) ? String(p[n]) : w);\n"
        "}\n"
        + _badge_block()
        + "\nprocess.stdout.write(html);\n",
        encoding='utf-8')
    result = subprocess.run([NODE, str(script)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, (
        '6DOF rozet bloğu null alanlarda çöktü:\n' + result.stderr)
    return result.stdout


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_sixdof_rozetleri_time_limit_null_alanlarinda_cokmez(tmp_path):
    """ÖNCE: `s.apogee_time.toFixed(1)` -> TypeError
    ("Cannot read properties of null (reading 'toFixed')") ve kullanıcı
    panelin try/catch'i yüzünden ham JS mesajını görüyordu.
    SONRA: sayı basılmaz, niçin basılmadığı yazılır.
    """
    out = _run_badge_block(tmp_path, SUMMARY_TIME_LIMIT, 'time_limit')
    assert 'APOGEE NOT REPORTED' in out, out
    assert 'STABILITY NOT EVALUATED' in out, out
    assert 'UNSTABLE' not in out, (
        'ölçülmemiş kararlılık "UNSTABLE" diye uydurulmuş hüküm olarak '
        'basılıyor:\n' + out)
    assert 'null' not in out and 'NaN' not in out and 'undefined' not in out, out
    # Gerçekten ölçülmüş olanlar basılmaya devam etmeli
    assert 'MAX MACH 0.27' in out, out
    assert 'MARGIN 4.84 / 5.84 cal' in out, out


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_sixdof_rozetleri_tamamen_null_ozette_cokmez(tmp_path):
    """Çözücü çöktüğünde (`solver_failed`) alanların hepsi null gelir."""
    out = _run_badge_block(tmp_path, SUMMARY_SOLVER_FAILED, 'solver_failed')
    assert 'APOGEE NOT REPORTED' in out, out
    assert 'STABILITY NOT EVALUATED' in out, out
    for kirli in ('null', 'NaN', 'undefined', 'MAX MACH', 'MARGIN', 'CNα'):
        assert kirli not in out, (
            'ölçülmemiş büyüklük yine de basılıyor (%s):\n%s' % (kirli, out))


def strip_js_comments(text):
    """JS yorumlarını siler (yorumdaki örnek kod deseni testi yanıltmasın)."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    return '\n'.join(re.sub(r'//.*$', '', line) for line in text.split('\n'))


def test_sixdof_panelinde_korumasiz_tofixed_kalmadi():
    src = strip_js_comments(read(STATIC_JS / 'sixdof_panel.js'))
    for kotu in ('s.apogee_time.toFixed', 's.max_mach.toFixed',
                 's.max_alpha_deg.toFixed', 's.cn_alpha.toFixed',
                 's.x_cp.toFixed', 's.static_margin_full.toFixed',
                 's.static_margin_empty.toFixed', '(s.apogee / 1000).toFixed'):
        # Yalnız KORUMASIZ kullanım aranır: Number.isFinite kapısının
        # arkasındaki kullanım (Barrowman çapraz kontrolü) meşrudur.
        for satir in src.split('\n'):
            if kotu in satir:
                pencere = src[max(0, src.index(satir) - 400):
                              src.index(satir) + len(satir)]
                assert 'Number.isFinite(s.' in pencere, (
                    'korumasız %s kaldı; uç bu alanı null döndürebiliyor'
                    % kotu)


# ===========================================================================
# Sözdizimi — dokunulan JS dosyaları
# ===========================================================================
@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
@pytest.mark.parametrize('name', ['analysis_dock.js', 'i18n_common.js',
                                  'sixdof_panel.js'])
def test_js_sozdizimi(name):
    result = subprocess.run([NODE, '--check', str(STATIC_JS / name)],
                            capture_output=True, text=True)
    assert result.returncode == 0, '%s sözdizimi hatası:\n%s' % (name, result.stderr)
