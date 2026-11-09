"""V306/HIZ — "hızlı" diye sunulan analizlerin bitmemesi ve takılan koşular.

Kaynak bulgular: mühendis turu M-SIVI-19 (BELİRSİZLİK "Hızlı Tarama
(~10-30 s)" 38 dk'da bitmedi; ilerleme/iptal/zaman aşımı yok; motor
değişince panel eski koşuyu "çalışıyor" gösterdi) ve M-KATI-35 (büyük katı
motorda Monte Carlo 60 s bütçesi; ileti panelde olmayan bir alanı öneriyor).
Ölçümler ve rapor: ``docs/scofield/raw/OH/V306/hiz/``.

Bekçiler:
  * sıvı fabrikası performans haritalarını örnekte atlar ve dört çıktısı
    tam motorla BİT-AYNIDIR;
  * çekirdek ilerlemeyi HER değerlendirmede bildirir ve durdurma sinyalini
    yutmaz;
  * ``async`` iş yolu: gövde eşzamanlı yolla aynı, sayaç gerçek, iptal ve
    süre bütçesi adıyla durur, kısmi sonuç yok;
  * seviye etiketleri kaynaksız süre vaadi taşımaz, örnek sayıları
    ``LEVEL_BUDGETS`` ile aynıdır;
  * panel (node): ilerleme ucun sayacından, kalan süre yalnız ölçülmüş
    örnek süresinden; koşu sırasında form değişirse sonuç çizilmez.
"""

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC_JS = ROOT / 'hrma' / 'static' / 'js'
PANEL_JS = STATIC_JS / 'panels' / 'uncertainty_panel.js'
I18N_JS = STATIC_JS / 'i18n_common.js'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

HIBRIT_GIRDI = {'thrust': 2000, 'chamber_pressure': 25, 'burn_time': 8,
                'oxidizer_type': 'N2O', 'fuel_type': 'htpb', 'of_ratio': 6}


@pytest.fixture(scope='module')
def appmod():
    from hrma import app as _app
    return _app


@pytest.fixture()
def istemci(appmod):
    return appmod.app.test_client()


def _ornek_sivi_girdi():
    d = json.loads((ROOT / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma')
                   .read_text(encoding='utf-8'))
    f = d['inputs']['fields']
    return {k: v for k, v in f.items()
            if v not in ('', None) and not k.startswith(('traj_', 'fea_',
                                                         'hrma_ai'))}


# ===========================================================================
# 1) Sıvı fabrikası — haritalar atlanır, çıktılar bit-aynı
# ===========================================================================

def test_sivi_fabrika_performans_haritalarini_ornekte_atlar(monkeypatch):
    from hrma.analysis import uq_adapters as uqa
    from hrma.engines import liquid_rocket_engine as lre
    cagri = []
    asil = lre.LiquidRocketEngine._generate_performance_optimization_maps_impl

    def say(self):
        cagri.append(1)
        return asil(self)
    monkeypatch.setattr(lre.LiquidRocketEngine,
                        '_generate_performance_optimization_maps_impl', say)
    fab = uqa.make_factory('liquid', _ornek_sivi_girdi())
    out = fab({'mixture_ratio': 1.01, 'chamber_pressure': 0.99,
               'eta_c_star': 0.95})
    assert set(out) == {'isp', 'thrust', 'c_star', 'mdot_total'}
    assert cagri == [], ('belirsizlik örneği 24 motorluk performans '
                         'haritasını yeniden koşuyor (M-SIVI-19 kökü)')


def test_sivi_fabrika_ciktilari_tam_motorla_bit_ayni():
    """Atlama sonuç değiştirmez: aynı örnek tam ``calculate_performance``la."""
    from hrma.analysis import uq_adapters as uqa
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    girdi = _ornek_sivi_girdi()
    fab = uqa.make_factory('liquid', girdi)
    ornek = {'mixture_ratio': 1.013, 'chamber_pressure': 0.987,
             'eta_c_star': 0.951}
    hizli = fab(dict(ornek))
    ctor = dict(thrust=girdi['thrust'],
                chamber_pressure=girdi['chamber_pressure'] * 0.987,
                mixture_ratio=girdi['mixture_ratio'] * 1.013,
                fuel_type=girdi['fuel_type'],
                oxidizer_type=girdi['oxidizer_type'],
                cooling_type=girdi['cooling_type'],
                injector_type=girdi['injector_type'])
    ov = dict(girdi)
    ov['combustion_efficiency'] = 0.951 * 100.0
    probe = LiquidRocketEngine(overrides=girdi, **dict(
        ctor, chamber_pressure=girdi['chamber_pressure'],
        mixture_ratio=girdi['mixture_ratio']))
    tam = LiquidRocketEngine(propellant_data=dict(probe.web_propellant_data),
                             overrides=ov, **ctor).calculate_performance()
    assert tam['performance_maps'].get('status') != 'skipped'
    beklenen = {'isp': tam['isp_sea_level'], 'thrust': tam['thrust'],
                'c_star': tam['c_star'], 'mdot_total': tam['total_mass_flow']}
    assert {k: float(v) for k, v in beklenen.items()} == hizli


# ===========================================================================
# 2) Çekirdek — her değerlendirmede ilerleme, durdurma yutulmaz
# ===========================================================================

def _sahte_dagilim():
    from hrma.analysis import uncertainty as uq
    return uq.get_default_distributions('liquid')


def test_cekirdek_ilerlemeyi_her_degerlendirmede_bildirir():
    from hrma.analysis import uncertainty as uq
    dist = _sahte_dagilim()
    cagrilar = []
    sonuc = uq.run_uncertainty(
        lambda s: {'isp': 250.0 * s.get('mixture_ratio', 1.0)}, dist,
        n_samples=40, seed=3,
        progress_callback=lambda d, t: cagrilar.append((d, t)))
    assert sonuc['status'] == 'success'
    assert cagrilar == [(i, 41) for i in range(1, 42)]


def test_cekirdek_durdurma_sinyalini_yutmaz_baska_istisnayi_yutar():
    from hrma.analysis import uncertainty as uq
    dist = _sahte_dagilim()
    calisan = []

    def fab(s):
        calisan.append(1)
        return {'isp': 250.0 * s.get('mixture_ratio', 1.0)}

    def dur(d, t):
        if d == 6:
            raise uq.SamplingStopped('cancelled')
    with pytest.raises(uq.SamplingStopped):
        uq.run_uncertainty(fab, dist, n_samples=40, seed=3,
                           progress_callback=dur)
    # nominal referans + 6 değerlendirme; 7. örnek hiç çekilmedi
    assert len(calisan) == 7

    def bozuk(d, t):
        raise RuntimeError('ilerleme raporu bozuk')
    sonuc = uq.run_uncertainty(fab, dist, n_samples=40, seed=3,
                               progress_callback=bozuk)
    assert sonuc['status'] == 'success'


# ===========================================================================
# 3) ``async`` iş yolu — gövde aynı, sayaç gerçek, iptal/bütçe adlı
# ===========================================================================

def _bekle(istemci, jid, kosul, tavan_s=60.0):
    t0 = time.monotonic()
    while True:
        st = istemci.get(f'/api/uncertainty-analysis/jobs/{jid}').get_json()
        if kosul(st):
            return st
        assert time.monotonic() - t0 < tavan_s, st
        time.sleep(0.05)


def test_async_govde_eszamanli_govdeyle_ayni(istemci):
    g = {'motor_type': 'hybrid', 'level': 'fast', 'seed': 7,
         'inputs': HIBRIT_GIRDI, 'n_samples': 12}
    r = istemci.post('/api/uncertainty-analysis', json=g)
    assert r.status_code == 200
    sync = r.get_json()
    r = istemci.post('/api/uncertainty-analysis', json=dict(g, **{'async': True}))
    assert r.status_code == 202
    kuyruk = r.get_json()
    assert kuyruk['samples_total'] == 12
    assert kuyruk['poll_url'].endswith(kuyruk['job_id'])
    st = _bekle(istemci, kuyruk['job_id'],
                lambda s: s['state'] not in ('queued', 'running'))
    assert st['state'] == 'done'
    assert st['samples_done'] == st['samples_total'] == 12
    a = {k: v for k, v in st['result'].items() if k != 'timing_s'}
    b = {k: v for k, v in sync.items() if k != 'timing_s'}
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


class _YavasFabrika:
    """Gerçek motor yerine sabit süreli, deterministik örnek (iş yolu bekçisi)."""

    def __init__(self, gecikme):
        self.gecikme = gecikme
        self.cagri = 0
        self.nominal_design_warnings = None

    def __call__(self, sample):
        self.cagri += 1
        time.sleep(self.gecikme)
        return {'isp': 200.0 * float(sample.get('of_ratio', 1.0)
                                     if 'of_ratio' in sample else 1.0)
                + float(sample.get('chamber_pressure', 1.0))}


@pytest.fixture()
def yavas_fabrika(monkeypatch):
    from hrma.analysis import uq_adapters as uqa
    fab = _YavasFabrika(0.02)
    monkeypatch.setattr(uqa, 'make_factory', lambda *a, **k: fab)
    return fab


def _gonder(istemci, n):
    r = istemci.post('/api/uncertainty-analysis', json={
        'motor_type': 'hybrid', 'level': 'fast', 'seed': 1,
        'inputs': HIBRIT_GIRDI, 'n_samples': n, 'async': True})
    assert r.status_code == 202, r.get_json()
    return r.get_json()['job_id']


def test_async_sayac_gercek_ve_sure_yalniz_olculmus_ornekten(
        istemci, yavas_fabrika):
    jid = _gonder(istemci, 30)
    ara = _bekle(istemci, jid, lambda s: 3 <= s.get('samples_done', 0) < 30)
    # kalan süre YALNIZ ölçülmüş örnek süresinden
    assert ara['per_sample_s'] > 0
    assert ara['eta_s'] == pytest.approx(
        ara['per_sample_s'] * (30 - ara['samples_done']), abs=0.11)
    son = _bekle(istemci, jid, lambda s: s['state'] == 'done')
    assert son['samples_done'] == son['samples_total'] == 30
    # nominal referans + nominal prob + 30 örnek: sayaç fabrika
    # çağrılarından türer, uydurulmaz
    assert yavas_fabrika.cagri == 32
    assert 'eta_s' not in son


def test_async_iptal_adli_durur_kismi_sonuc_yok(istemci, yavas_fabrika):
    jid = _gonder(istemci, 200)
    _bekle(istemci, jid, lambda s: s.get('samples_done', 0) >= 3)
    r = istemci.post(f'/api/uncertainty-analysis/jobs/{jid}/cancel', json={})
    assert r.status_code == 200 and r.get_json()['cancel_requested'] is True
    st = _bekle(istemci, jid, lambda s: s['state'] not in ('queued', 'running'),
                tavan_s=10.0)
    assert st['state'] == 'cancelled'
    assert st['stopped']['reason'] == 'cancelled'
    assert 3 <= st['stopped']['samples_done'] < 200
    assert st['stopped']['samples_total'] == 200
    assert 'result' not in st
    # durdu: fabrika artık çağrılmıyor
    n = yavas_fabrika.cagri
    time.sleep(0.2)
    assert yavas_fabrika.cagri == n


def test_async_sure_butcesi_adli_durur(istemci, yavas_fabrika, monkeypatch,
                                       appmod):
    monkeypatch.setattr(appmod, 'UQ_JOB_TIME_BUDGET_S', 0.15)
    jid = _gonder(istemci, 200)
    st = _bekle(istemci, jid, lambda s: s['state'] not in ('queued', 'running'),
                tavan_s=20.0)
    assert st['state'] == 'error'
    assert st['error'] == 'uncertainty_time_budget_exceeded'
    assert st['stopped']['reason'] == 'time_budget_exceeded'
    assert 0 < st['stopped']['samples_done'] < 200
    assert 'result' not in st


def test_async_alan_dogrulama_ve_bilinmeyen_is(istemci):
    r = istemci.post('/api/uncertainty-analysis', json={
        'motor_type': 'hybrid', 'level': 'fast', 'inputs': HIBRIT_GIRDI,
        'async': 'evet'})
    assert r.status_code == 400
    assert r.get_json()['invalid_fields'][0]['field'] == 'async'
    assert istemci.get('/api/uncertainty-analysis/jobs/yok').status_code == 404
    assert istemci.post('/api/uncertainty-analysis/jobs/yok/cancel',
                        json={}).status_code == 404


# ===========================================================================
# 4) Etiketler — kaynaksız süre vaadi yok, sayı LEVEL_BUDGETS ile aynı
# ===========================================================================

def _sozluk_degeri(metin, anahtar):
    return re.findall(r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'",
                      metin)


def test_seviye_etiketleri_sure_vaadi_tasimaz_ornek_sayisi_tek_kaynak():
    from hrma.analysis.uncertainty import LEVEL_BUDGETS
    i18n = I18N_JS.read_text(encoding='utf-8')
    panel = PANEL_JS.read_text(encoding='utf-8')
    for anahtar, seviye in (('uq.levelFast', 'fast'),
                            ('uq.levelEng', 'engineering'),
                            ('uq.levelHigh', 'high_fidelity')):
        degerler = _sozluk_degeri(i18n, anahtar)
        assert len(degerler) == 2, anahtar          # EN + TR
        m = re.search(r"\['" + seviye + r"', '([^']*)', '" + re.escape(anahtar)
                      + "'\\]", panel)
        assert m, seviye
        for d in degerler + [m.group(1)]:
            assert str(LEVEL_BUDGETS[seviye]) in d, (anahtar, d)
            assert not re.search(r'~|\d\s*(s|sn|min|dk)\b', d), (anahtar, d)
    for d in _sozluk_degeri(i18n, 'panel.uncertainty.help.level'):
        assert '/api/' not in d
        for n in LEVEL_BUDGETS.values():
            assert str(n) in d


# ===========================================================================
# 5) Panel (node) — gerçek sayaç, ölçülmüş süre, bayat sonuç
# ===========================================================================

HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const staticDir = process.argv[2];
const senaryo = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

const byId = {};
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this._attrs = {}; this._id = '';
    this.textContent = ''; this.innerHTML = ''; this.disabled = false;
    this.value = ''; this.max = 0;
}
Object.defineProperty(El.prototype, 'id', {
    get: function () { return this._id; },
    set: function (v) { this._id = String(v); byId[this._id] = this; },
});
Object.defineProperty(El.prototype, 'firstElementChild', {
    get: function () { return this._first || (this._first = new El('div')); },
});
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.removeAttribute = function (k) { delete this._attrs[k]; };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.addEventListener = function () {};
El.prototype.querySelector = function () { return new El('select'); };
El.prototype.querySelectorAll = function () { return []; };
['ad_sec_uncertainty', 'ad_status_uncertainty', 'ad_root_uncertainty',
 'uq_run', 'uq_cancel', 'uq_progress', 'uq_level', 'uq_seed', 'ad_panes',
 'ad_tabs', 'ad_toolbar'].forEach(function (id) { const e = new El('div'); e.id = id; });
byId.uq_level.value = 'fast';
byId.uq_seed.value = '42';

const timers = [];
const documentStub = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function (id) { return byId[id] || null; },
    addEventListener: function () {},
};
const istekler = [];
let yoklamaSirasi = senaryo.yoklamalar.slice();
function yanit(body, status) {
    return Promise.resolve({ ok: status < 400, status: status,
        json: function () { return Promise.resolve(body); } });
}
let form = JSON.parse(JSON.stringify(senaryo.form));
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: function (fn) { timers.push(fn); return timers.length; },
    clearTimeout: function () {}, setInterval: function () { return 0; },
    clearInterval: function () {},
    requestAnimationFrame: function (fn) { fn(); return 1; },
    fetch: function (url, opt) {
        istekler.push({ url: url, body: opt && opt.body });
        if (url === '/api/uncertainty-analysis') return yanit(senaryo.kuyruk, 202);
        if (/\/cancel$/.test(url)) return yanit({ status: 'success' }, 200);
        const y = yoklamaSirasi.shift();
        return yanit(y, 200);
    },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Promise: Promise, Error: Error,
    RegExp: RegExp, isFinite: isFinite, parseFloat: parseFloat,
    parseInt: parseInt, document: documentStub,
    localStorage: { getItem: function () { return null; },
                    setItem: function () {}, removeItem: function () {} },
    Plotly: { react: function () {}, purge: function () {} },
    collectAllParameters: function () { return JSON.parse(JSON.stringify(form)); },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'analysis_dock.js'), 'utf8'),
                sandbox, { filename: 'analysis_dock.js' });
vm.runInContext(fs.readFileSync(path.join(staticDir, 'panels', 'uncertainty_panel.js'), 'utf8'),
                sandbox, { filename: 'uncertainty_panel.js' });
const P = sandbox.window.UncertaintyPanel;
const out = { adimlar: [] };
function kaydet() {
    const st = byId.ad_status_uncertainty;
    out.adimlar.push({
        durum: st.textContent,
        onceki: st.getAttribute('data-onceki-tasarim'),
        cubuk: [byId.uq_progress.value, byId.uq_progress.max,
                byId.uq_progress.style.display],
        cizildi: !!P.lastData,
        aktif: !!P.aktifIs,
    });
}
async function bosalt() { for (let i = 0; i < 20; i++) await Promise.resolve(); }
(async function () {
    await P.run();
    await bosalt();
    kaydet();
    for (let i = 0; i < senaryo.yoklamalar.length; i++) {
        if (senaryo.formDegisirAdim === i) form.thrust = form.thrust + 1;
        const fn = timers.shift();
        if (!fn) break;
        await fn();
        await bosalt();
        kaydet();
    }
    if (senaryo.sonraFormDegisir) {
        form.chamber_pressure = form.chamber_pressure + 1;
        P._gosterilenSonucuDenetle();
        kaydet();
    }
    out.gonderilen = JSON.parse(istekler[0].body);
    out.kokHtml = (function topla(el) {
        let s = el.innerHTML || '';
        (el.children || []).forEach(function (c) { s += topla(c); });
        return s;
    })(byId.ad_root_uncertainty);
    out.eta = P._ilerlemeMetni({ state: 'running', samples_done: 0,
        samples_total: 10, elapsed_s: 3 }, false);
    process.stdout.write(JSON.stringify(out));
})().catch(function (e) { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""

_SONUC = {
    'status': 'ok', 'motor_type': 'liquid', 'level': 'fast', 'n_samples': 10,
    'failed_samples': 0, 'seed': 42, 'timing_s': 1.0,
    'mean_shift_percent': {'isp': 0.0},
    'outputs': {'isp': {'nominal': 250.0, 'mean': 250.0, 'std': 1.0,
                        'cv': 0.4, 'cv_percent': 0.4, 'p5': 248.0,
                        'p25': 249.0, 'p50': 250.0, 'p75': 251.0,
                        'p95': 252.0,
                        'histogram': {'edges': [248.0, 250.0, 252.0],
                                      'counts': [5, 5]}}},
    'sensitivity': {}, 'sensitivity_status': 'not_modelled',
}
_KUYRUK = {'status': 'queued', 'job_id': 'j1', 'samples_total': 10,
           'poll_url': '/api/uncertainty-analysis/jobs/j1'}
_FORM = {'thrust': 5000, 'chamber_pressure': 30, 'fuel_type': 'rp1'}


def _kos_panel(tmp_path, yoklamalar, formDegisirAdim=None,
               sonraFormDegisir=False):
    script = tmp_path / 'uq_hiz.js'
    script.write_text(HARNESS_JS, encoding='utf-8')
    girdi = tmp_path / 'senaryo.json'
    girdi.write_text(json.dumps({
        'yoklamalar': yoklamalar, 'kuyruk': _KUYRUK, 'form': _FORM,
        'formDegisirAdim': formDegisirAdim,
        'sonraFormDegisir': sonraFormDegisir}), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(STATIC_JS), str(girdi)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


def _kosuyor(done, per=None, eta=None):
    b = {'status': 'success', 'state': 'running', 'samples_done': done,
         'samples_total': 10, 'elapsed_s': 2.0 + done}
    if per is not None:
        b.update(per_sample_s=per, eta_s=eta)
    return b


@needs_node
def test_panel_ilerleme_gercek_sayactan_sure_olculmus_ornekten(tmp_path):
    out = _kos_panel(tmp_path, [
        _kosuyor(0),
        _kosuyor(4, per=0.5, eta=3.0),
        {'status': 'success', 'state': 'done', 'samples_done': 10,
         'samples_total': 10, 'result': _SONUC},
    ])
    assert out['gonderilen']['async'] is True
    a0, a1, a2, a3 = out['adimlar']
    assert a0['cubuk'][:2] == [0, 10] and a0['aktif']
    # ilk örnek ölçülmeden kalan süre YAZILMAZ
    assert '0 of 10' in a1['durum'] and 'about' not in a1['durum']
    assert 'remaining time is shown once' in a1['durum']
    assert a1['cubuk'][:2] == [0, 10]
    # çubuk ve metin ucun sayacından; kalan süre ucun ölçümünden
    assert a2['cubuk'][:2] == [4, 10]
    assert '4 of 10' in a2['durum'] and 'about 3' in a2['durum']
    assert a3['cizildi'] and not a3['aktif'] and a3['onceki'] is None
    assert 'remaining time is shown once' in out['eta']
    # seviye kartı ham anahtar ('fast') değil seçicideki etiket
    assert 'Fast Screening' in out['kokHtml']
    assert '>fast<' not in out['kokHtml']


@needs_node
def test_panel_kosu_sirasinda_form_degisirse_sonuc_cizilmez(tmp_path):
    out = _kos_panel(tmp_path, [
        _kosuyor(2, per=0.5, eta=4.0),
        {'status': 'success', 'state': 'done', 'samples_done': 10,
         'samples_total': 10, 'result': _SONUC},
    ], formDegisirAdim=1)
    son = out['adimlar'][-1]
    assert not son['cizildi']
    assert son['onceki'] == '1'
    assert 'thrust' in son['durum'] and 'discarded' in son['durum']


@needs_node
def test_panel_gosterilen_sonuc_form_degisince_temizlenir(tmp_path):
    out = _kos_panel(tmp_path, [
        {'status': 'success', 'state': 'done', 'samples_done': 10,
         'samples_total': 10, 'result': _SONUC},
    ], sonraFormDegisir=True)
    assert out['adimlar'][-2]['cizildi']
    son = out['adimlar'][-1]
    assert not son['cizildi'] and son['onceki'] == '1'


@needs_node
def test_panel_butce_ve_iptal_adli_durma_metni(tmp_path):
    out = _kos_panel(tmp_path, [
        _kosuyor(3, per=0.5, eta=3.5),
        {'status': 'error', 'state': 'error', 'samples_done': 4,
         'samples_total': 10, 'error': 'uncertainty_time_budget_exceeded',
         'stopped': {'reason': 'time_budget_exceeded', 'samples_done': 4,
                     'samples_total': 10, 'time_budget_s': 3600.0}},
    ])
    son = out['adimlar'][-1]
    assert 'after 4 of 10 samples' in son['durum']
    assert 'time budget' in son['durum'] and '1 h 00 min' in son['durum']
    assert not son['cizildi'] and not son['aktif']


# ===========================================================================
# 6) Kalem 2 — katı Monte Carlo (M-KATI-35): bant, adlı ve gerçek durma, alan
# ===========================================================================

def _kati_mc_taban():
    """test_d30_app_api_uc_a3.py MC_TABAN ile aynı gövde (APCP, Ø100 kasa;
    çekirdek ucun kendi varsayılan geometrisinden)."""
    from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM
    return {'chamber_pressure': 40, 'chamber_diameter': 100,
            'grain_length': 500,
            'core_diameter': SOLID_DEFAULT_GEOMETRY_MM['core_diameter'],
            'propellant_type': 'apcp'}


def _kati_motor():
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    kw = {'grain_type': 'bates', 'propellant_type': 'apcp',
          'chamber_diameter': 100, 'grain_length': 500, 'core_diameter': 76,
          'chamber_pressure': 40, 'burn_rate_a': 0.005, 'burn_rate_n': 0.35}
    return SolidRocketEngine(overrides=dict(kw), **kw)


def test_kati_mc_ilerleme_kancasi_sonucu_degistirmez():
    import contextlib
    import io
    from hrma.engines.solid_rocket_engine import SOLID_MC_SAMPLE_BAND
    n = SOLID_MC_SAMPLE_BAND[0]
    with contextlib.redirect_stdout(io.StringIO()):
        a = _kati_motor().run_monte_carlo(n_samples=n, seed=5)
        cagri = []
        b = _kati_motor().run_monte_carlo(
            n_samples=n, seed=5, progress_callback=lambda d, t: cagri.append(d))
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(
        b, sort_keys=True, default=str)
    assert cagri == list(range(0, n + 1))


def test_kati_mc_bant_motorun_sabitinden_disi_adla_reddedilir(istemci):
    from hrma.engines.solid_rocket_engine import SOLID_MC_SAMPLE_BAND
    lo, hi = SOLID_MC_SAMPLE_BAND
    for n, neden in ((lo - 1, 'below_minimum'), (hi + 1, 'above_maximum')):
        r = istemci.post('/api/solid-monte-carlo',
                         json=dict(_kati_mc_taban(), n_samples=n))
        assert r.status_code == 422, (n, r.status_code)
        k = [f for f in r.get_json()['invalid_fields']
             if f['field'] == 'n_samples'][0]
        assert k['reason'] == neden
        assert k['accepted_range'] == [lo, hi]


def test_kati_mc_butce_asiminda_adli_ve_gercekten_durur(istemci, appmod,
                                                        monkeypatch):
    from hrma.engines import solid_rocket_engine as sre
    sayac = {'n': 0}
    asil = sre.SolidRocketEngine.calculate_performance

    def sayan(self, *a, **k):
        sayac['n'] += 1
        return asil(self, *a, **k)
    monkeypatch.setattr(sre.SolidRocketEngine, 'calculate_performance', sayan)
    monkeypatch.setattr(appmod, '_SIXDOF_WALL_CLOCK_BUDGET_S', 1.0)
    r = istemci.post('/api/solid-monte-carlo',
                     json=dict(_kati_mc_taban(), n_samples=sre.SOLID_MC_SAMPLE_BAND[1]))
    assert r.status_code == 503
    g = r.get_json()
    assert g['error'] == 'solid_monte_carlo_time_budget_exceeded'
    assert 0 <= g['n_samples_completed'] < sre.SOLID_MC_SAMPLE_BAND[1]
    assert g['accepted_range'] == list(sre.SOLID_MC_SAMPLE_BAND)
    if g['n_samples_completed'] >= 1:
        assert g['seconds_per_sample'] > 0
        assert g['samples_fitting_budget'] >= 0
    # durdurma bayrağı: arka plandaki koşu bir sonraki örnek sınırında biter
    time.sleep(1.5)
    n1 = sayac['n']
    time.sleep(1.0)
    assert sayac['n'] == n1, 'bütçe aşımından sonra MC arka planda sürüyor'


def test_kati_sayfa_ornek_sayisi_alani_ucun_sabitlerinden(istemci, appmod):
    from hrma.engines.solid_rocket_engine import SOLID_MC_SAMPLE_BAND
    html = istemci.get('/solid').get_data(as_text=True)
    m = re.search(r'<input[^>]*id="mc_n_samples"[^>]*>', html)
    assert m, 'Monte Carlo örnek sayısı alanı yok (M-KATI-35)'
    alan = m.group(0)
    assert f'value="{appmod.SOLID_MC_DEFAULT_SAMPLES}"' in alan
    assert f'min="{SOLID_MC_SAMPLE_BAND[0]}"' in alan
    assert f'max="{SOLID_MC_SAMPLE_BAND[1]}"' in alan
    # istek alandan kurulur; eski sabit 300 yazımı yok
    assert 'data.n_samples = 300' not in html
    assert "getElementById('mc_n_samples')" in html
    # ipucu (EN + TR): bant, varsayılan ve bütçe koddakiyle aynı; uç adı yok
    sayfalar = (STATIC_JS / 'i18n_pages.js').read_text(encoding='utf-8')
    ipuclari = _sozluk_degeri(sayfalar, 'solid.ui.mc_sample_count_help')
    assert len(ipuclari) == 2
    for d in ipuclari:
        assert str(SOLID_MC_SAMPLE_BAND[0]) in d and str(SOLID_MC_SAMPLE_BAND[1]) in d
        assert str(appmod.SOLID_MC_DEFAULT_SAMPLES) in d
        assert f'{appmod._SIXDOF_WALL_CLOCK_BUDGET_S:g}' in d
        assert '/api/' not in d and 'n_samples' not in d
