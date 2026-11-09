"""V306/BAYAT DEVİR 1 bekçisi — güverte paneli eski motorun sonucunu göstermez.

ÖLÇÜLDÜ (docs/scofield/raw/OH/V306/bayat/olcum_nr9_once.json): üç sayfada
Basınçlı Kap paneli motor yeniden hesaplanınca eski girdilerle bulunmuş
"DURUM: PASS … 96.0 bar" sonucunu İŞARETSİZ gösteriyordu. Onarım
(1d5f11da5, `analysis_dock.js` `refreshSuggestions`): panelin son başarılı
koşusunun GÖVDESİ, tazelenen girdilerle kurulan gövdeyle kıyaslanır; farklıysa
sonuç temizlenir ve durum satırı nedenini söyler (`dock.staleDesign`).

Düzenek: gerçek `analysis_dock.js` node altında vm bağlamında, küçük bir DOM
taklidiyle (kalıp: tests/test_faz6_guverte.py). Panel GERÇEK koşu yolundan
(çalıştır düğmesinin tıklama dinleyicisi → runPanel → fetch) koşturulur,
sonra motor değerleri değişir ve `refreshSuggestions` çağrılır.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const staticDir = __STATIC_DIR__;
const ayniGirdi = __AYNI_GIRDI__;

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.classList = { contains: function () { return false; }, add: function () {},
                       remove: function () {}, toggle: function () {} };
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
El.prototype.removeAttribute = function (k) { delete this._attrs[k]; };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.hasAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k);
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

let fetchSayisi = 0;
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    fetch: function () {
        fetchSayisi += 1;
        const govde = JSON.stringify({ status: 'success', sonuc: 96.0 });
        return Promise.resolve({ ok: true, status: 200,
            text: function () { return Promise.resolve(govde); },
            json: function () { return Promise.resolve(JSON.parse(govde)); } });
    },
    document: documentStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'analysis_dock.js'), 'utf8'),
                sandbox, { filename: 'analysis_dock.js' });

// Motorun güverteye verdiği değerler (yeniden hesapta değişir).
const motor = { chamber_pressure_bar: 50.0, wall_thickness_mm: 3.0 };
let cizim = 0;
sandbox.window.AnalysisDock.register({
    id: 'p_kap',
    title: 'Pressure vessel (test)',
    category: 'STRUCTURAL',
    endpoint: '/api/pressure-vessel',
    fields: [['chamber_pressure_bar', 'Pc', 1, 0.1],
             ['wall_thickness_mm', 't', 1, 0.1]],
    fromResults: function () {
        return { chamber_pressure_bar: motor.chamber_pressure_bar,
                 wall_thickness_mm: motor.wall_thickness_mm };
    },
    render: function (data, root) { cizim += 1; root.innerHTML = 'DURUM: PASS'; }
});
sandbox.window.AnalysisDock.init({
    motorType: 'solid',
    resultsProvider: function () { return { motor: {} }; }
});

const root = getEl('ad_root_p_kap');
const status = getEl('ad_status_p_kap');
const dugme = getEl('ad_run_p_kap');
// buildPayload alanları bölümün `[data-field]` öğelerinden okur; taklit
// DOM'da bölüm bu iki alan öğesini döndürür (gerçek sayfadaki işaretleme).
const alanOgeleri = ['chamber_pressure_bar', 'wall_thickness_mm'].map(function (k) {
    const e = getEl('ad_f_p_kap_' + k);
    e.tagName = 'INPUT';
    e._attrs['data-field'] = k;
    return e;
});
getEl('ad_sec_p_kap').querySelectorAll = function (s) {
    return s === '[data-field]' ? alanOgeleri : [];
};

(async function () {
    const tik = (dugme._listeners.click || [])[0];
    if (!tik) { console.log(JSON.stringify({ hata: 'calistir_dugmesi_yok' })); return; }
    tik();
    await new Promise(function (r) { setTimeout(r, 50); });
    const kosuSonrasi = { gorunur: root.style.display, icerik: root.innerHTML,
                          fetch: fetchSayisi, cizim: cizim };

    // Motor yeniden hesaplandı.
    if (!ayniGirdi) { motor.chamber_pressure_bar = 60.0; }
    sandbox.window.AnalysisDock.refreshSuggestions();

    console.log(JSON.stringify({
        kosuSonrasi: kosuSonrasi,
        alanPc: getEl('ad_f_p_kap_chamber_pressure_bar').value,
        gorunur: root.style.display,
        icerik: root.innerHTML,
        oncekiTasarim: status.getAttribute('data-onceki-tasarim'),
        durum: status.textContent,
    }));
})();
"""


def _kos(ayni_girdi):
    betik = (HARNESS_JS
             .replace('__STATIC_DIR__', json.dumps(str(STATIC_JS)))
             .replace('__AYNI_GIRDI__', 'true' if ayni_girdi else 'false'))
    # Betik stdin'den (test_node_cagri_sozlesmesi).
    proc = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                          timeout=60)
    assert proc.returncode == 0, 'node koşumu hata verdi:\n' + proc.stderr
    satirlar = [s for s in proc.stdout.strip().splitlines() if s.strip()]
    assert satirlar, 'koşum çıktı üretmedi:\n' + proc.stdout + proc.stderr
    return json.loads(satirlar[-1])


@needs_node
def test_duzenek_paneli_gercek_kosu_yolundan_calistiriyor():
    """Isırık önkoşulu: panel gerçekten koştu, sonuç ekranda."""
    r = _kos(ayni_girdi=True)
    assert 'hata' not in r, r
    k = r['kosuSonrasi']
    assert k['fetch'] == 1 and k['cizim'] == 1, k
    assert k['gorunur'] == 'block' and 'PASS' in k['icerik'], k


@needs_node
def test_motor_degisince_eski_sonuc_temizlenir_ve_nedeni_yazilir():
    r = _kos(ayni_girdi=False)
    assert 'hata' not in r, r
    # Öneri yeni motora tazelendi (yoksa kıyas anlamsız olurdu).
    assert float(r['alanPc']) == pytest.approx(60.0), r
    assert r['gorunur'] == 'none', r
    assert r['icerik'] == '', r
    assert r['oncekiTasarim'] == '1', r
    assert 'recalculated' in r['durum'] and 'Run it again' in r['durum'], r


@needs_node
def test_girdi_degismediyse_sonuc_kalir():
    """Gövde aynıysa sonuç hâlâ ekrandaki girdilere aittir: temizlenmez."""
    r = _kos(ayni_girdi=True)
    assert r['gorunur'] == 'block', r
    assert 'PASS' in r['icerik'], r
    assert r['oncekiTasarim'] is None, r


def test_ileti_iki_dilde_tek_anahtarla_var():
    src = (STATIC_JS / 'i18n_common.js').read_text(encoding='utf-8')
    satirlar = [s for s in src.splitlines() if "'dock.staleDesign':" in s]
    assert len(satirlar) == 2, satirlar          # EN + TR, birer kez
    assert any('Motor yeniden hesaplandı' in s for s in satirlar), satirlar
