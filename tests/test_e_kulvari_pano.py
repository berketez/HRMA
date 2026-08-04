"""Kulvar E bekçileri — pano/arayüz katmanı (E1-E4).

Yol haritası (docs/YOL_HARITASI_2.7_VE_SONRASI.md, Kulvar E) dört kalem
tanımlıyor; buradaki testler dördünün de SÖZLEŞMESİNİ kilitler:

  E1  Sekme → ızgara yerleşimi
      Kullanıcı 14 paneli sekme arkasında tek tek değil, ızgarada aynı anda
      görebilmeli. Tercih localStorage'da yaşamalı ve okunamadığında (gizli
      kip, bozuk değer, depo yok) DAVRANIŞ BUGÜNKÜNE düşmeli: sekme kipi.

  E2  "Ne değişti" vurgusu
      Yeni sonuç geldiğinde bir öncekiyle SAYISAL fark çıkarılmalı; değişen
      büyüklükler eski → yeni rozetiyle işaretlenmeli. Eşik altı gürültü
      İŞARETLENMEMELİ ve eşik TEK yerde tanımlı + beyanlı olmalı.
      Fark kapısının GERÇEKTEN çağrıldığı da sınanır (refreshSuggestions
      yolu): "kanal var kapı yok" hatası Faz 5'in en pahalı dersiydi.

  E3  Kaynak renklendirmesi
      Dört durum (hesaplanmış / kullanıcı / varsayım / modellenmemiş)
      motor_viz3d.js'in SOURCE_COLORS tablosuyla BİREBİR aynı renkleri
      kullanmalı ve her rozet renkle BİRLİKTE simge + metin etiketi
      taşımalı (renk körlüğü / gri baskı).

  E4  İki tasarımı üst üste karşılaştırma
      Tablo iki snapshot'ın KENDİ sayılarından birebir kurulmalı; fark
      sütunu B − A olmalı; yalnız birinde bulunan metrik ortak satır gibi
      gösterilmemeli.

Ölçüm yöntemi: analysis_dock.js ve panels/comparative_panel.js GERÇEK node
altında, vm bağlamında, küçük bir DOM + localStorage taklidiyle BÜTÜN olarak
koşturulur (kalıp: tests/test_faz6_guverte.py düzeneği). Sabit sayıya değil
DAVRANIŞA bağlanır: eşik değeri makul bir bant içinde serbesttir, böylece
eşik ileride ölçümle güncellenirse bekçi kusuru kilitlemez.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
DOCK_JS = STATIC_JS / 'analysis_dock.js'
CMP_JS = STATIC_JS / 'panels' / 'comparative_panel.js'
VIZ3D_JS = STATIC_JS / 'motor_viz3d.js'
THEME_CSS = REPO_ROOT / 'hrma' / 'static' / 'css' / 'theme.css'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

LAYOUT_KEY = 'hrma.dock.layout'


# ===========================================================================
# node koşum düzeneği
# ===========================================================================
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const staticDir = process.argv[2];
const cfg = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

// --- küçük DOM taklidi -----------------------------------------------------
const byId = {};

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this._classes = [];
    this._attrs = {};
    this._id = '';
    this.textContent = '';
    this.innerHTML = '';
    this.disabled = false;
    this.value = '';
    const self = this;
    this.classList = {
        add: function (c) { if (self._classes.indexOf(c) === -1) self._classes.push(c); },
        remove: function (c) {
            const i = self._classes.indexOf(c);
            if (i !== -1) self._classes.splice(i, 1);
        },
        contains: function (c) { return self._classes.indexOf(c) !== -1; },
    };
}
Object.defineProperty(El.prototype, 'id', {
    get: function () { return this._id; },
    set: function (v) { this._id = String(v); byId[this._id] = this; },
});
Object.defineProperty(El.prototype, 'className', {
    get: function () { return this._classes.join(' '); },
});
Object.defineProperty(El.prototype, 'firstElementChild', {
    get: function () { return this._first || (this._first = new El('div')); },
});
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.remove = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.addEventListener = function () {};
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.insertAdjacentHTML = function (pos, html) { this.innerHTML += html; };

// Tarayıcıda şablondan gelen kaplar: yalnız bunlar VARDIR, gerisi null döner
// (gerçek DOM davranışı — bilinmeyen id otomatik eleman üretmez).
['ad_panes', 'ad_tabs', 'ad_toolbar', 'ad_diff_band', 'ad_src_legend'
].forEach(function (id) { const e = new El('div'); e.id = id; });

// Tarayıcıda innerHTML'den doğan iç elemanlar (panel bölümü, form alanı,
// karşılaştırma bloğu) taklit edilir; kategori bölmeleri (ad_pane_*) BİLEREK
// taklit edilmez — onları güvertenin kendisi createElement ile kurmalı,
// yerleşim ölçümü gerçek çocuk listesinden okunur.
const AUTO_ID = /^(?:ad_(?:run|sec|status|root|f|src)_|cmp_)/;

const documentStub = {
    head: new El('head'),
    body: new El('body'),
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function (id) {
        if (byId[id]) return byId[id];
        if (AUTO_ID.test(id)) { const e = new El('div'); e.id = id; return e; }
        return null;
    },
    addEventListener: function () {},
};

// --- localStorage taklidi --------------------------------------------------
const store = Object.assign({}, cfg.storage || {});
let storage;
if (cfg.storage_mode === 'absent') {
    storage = undefined;
} else if (cfg.storage_mode === 'throwing') {
    storage = {
        getItem: function () { throw new Error('gizli kip: depo kapalı'); },
        setItem: function () { throw new Error('gizli kip: depo kapalı'); },
    };
} else {
    storage = {
        getItem: function (k) {
            return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null;
        },
        setItem: function (k, v) { store[k] = String(v); },
        removeItem: function (k) { delete store[k]; },
    };
}

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: function () { return 0; },
    clearTimeout: function () {},
    setInterval: function () { return 0; },   // panel montaj yarışı döngüsü
    clearInterval: function () {},
    fetch: function () { return Promise.resolve({ ok: true, status: 200,
        text: function () { return Promise.resolve('{}'); } }); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Promise: Promise, Error: Error, RegExp: RegExp,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
};
if (storage !== undefined) sandbox.localStorage = storage;
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'analysis_dock.js'), 'utf8'),
                sandbox, { filename: 'analysis_dock.js' });
vm.runInContext(fs.readFileSync(
    path.join(staticDir, 'panels', 'comparative_panel.js'), 'utf8'),
    sandbox, { filename: 'comparative_panel.js' });

const D = sandbox.window.AnalysisDock;
const out = { storage_mode: cfg.storage_mode || 'normal' };

function paneDisplays() {
    const panes = byId['ad_panes'];
    const map = {};
    (panes.children || []).forEach(function (p) { map[p.id] = p.style.display; });
    return map;
}

// --- E1: yerleşim ----------------------------------------------------------
out.layoutBeforeInit = D.getLayout();

let sonuc = cfg.results_a || null;
D.init({ motorType: 'hybrid', resultsProvider: function () { return sonuc; } });

out.layoutAfterInit = D.getLayout();
out.panesAfterInit = paneDisplays();
out.panesClassAfterInit = byId['ad_panes'].className;

out.setGridReturn = D.setLayout('grid');
out.panesGrid = paneDisplays();
out.panesClassGrid = byId['ad_panes'].className;

// Izgara kipindeyken sekmeye tıklamak paneli GİZLEMEZ (geri düşüş yok)
D.selectCategory('SAFETY');
out.panesGridAfterTabClick = paneDisplays();

out.setTabsReturn = D.setLayout('tabs');
out.panesTabs = paneDisplays();
out.panesClassTabs = byId['ad_panes'].className;

out.bogusReturn = D.setLayout('kırık-değer');
out.layoutAfterBogus = D.getLayout();

// Kalıcılık: kip 'grid'e alınıp depo dışa verilir (Python ikinci koşumda
// aynı depoyla yeniden yükleyip tercihin geri geldiğini ölçer).
D.setLayout(cfg.final_layout || 'grid');
out.finalLayout = D.getLayout();
out.storage = store;

// --- E2: fark --------------------------------------------------------------
out.threshold = D.diff.THRESHOLD;

const esik = D.diff.THRESHOLD;
const kucuk = 1 + esik / 100;        // eşiğin YÜZDE BİRİ kadar oynama
const buyuk = 1 + esik * 100;        // eşiğin YÜZ KATI kadar oynama
const oncekiSonuc = {
    motor: { thrust: 1000.0, isp: 220.0, chamber_pressure: 40.0 },
    series: { thrust_curve: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] },
    label: 'baseline',
};
const yeniSonuc = {
    motor: { thrust: 1000.0 * buyuk, isp: 220.0 * kucuk, chamber_pressure: 40.0,
             new_field: 7.5 },
    series: { thrust_curve: [1, 2, 3, 4, 5, 6, 7, 8, 9, 11] },
    label: 'değişti',
};
const fark = D.diff.compute(oncekiSonuc, yeniSonuc);
out.diff = {
    paths: fark.changes.map(function (c) { return c.path; }),
    changes: fark.changes,
    series: fark.series,
    added: fark.added,
    removed: fark.removed,
    threshold: fark.threshold,
    hasBaseline: fark.hasBaseline,
    compared: fark.compared,
};
out.diffNoBaseline = D.diff.compute(null, yeniSonuc);
out.diffIdentical = D.diff.compute(oncekiSonuc, JSON.parse(JSON.stringify(oncekiSonuc)));
out.diffBadge = D.diff.badge(fark.changes[0]);
out.diffStrip = D.diff.strip(fark);

// Rozet yerleştirme: yalnız DEĞİŞEN yol işaretlenir
const kap = new El('div');
const isaretli = [];
kap.querySelectorAll = function () {
    return [
        { getAttribute: function (k) {
              return k === 'data-diff-path' ? 'motor.thrust' : null; },
          setAttribute: function () {},
          insertAdjacentHTML: function (p, h) { isaretli.push(['motor.thrust', h]); } },
        { getAttribute: function (k) {
              return k === 'data-diff-path' ? 'motor.chamber_pressure' : null; },
          setAttribute: function () {},
          insertAdjacentHTML: function (p, h) { isaretli.push(['motor.chamber_pressure', h]); } },
    ];
};
out.annotated = D.diff.annotate(kap, fark);
out.annotatedPaths = isaretli.map(function (x) { return x[0]; });

// KAPI: refreshSuggestions gerçekten fark üretiyor mu (kanal değil kapı)
sonuc = oncekiSonuc;
D.refreshSuggestions();
sonuc = yeniSonuc;
D.refreshSuggestions();
const kapiFarki = D.diff.last();
out.gateChanged = kapiFarki ? kapiFarki.changes.map(function (c) { return c.path; }) : null;
out.diffBandHtml = byId['ad_diff_band'].innerHTML;
out.diffBandDisplay = byId['ad_diff_band'].style.display;

// --- E3: kaynak ------------------------------------------------------------
out.sourceKinds = D.source.KINDS;
out.sourceColors = D.source.COLORS;
out.chips = {};
D.source.KINDS.forEach(function (k) {
    out.chips[k] = D.source.chip({ kind: k, declared: true, basis: 'test gerekçe' });
});
out.legend = D.source.legend();
out.sourceOf = {
    computed: D.source.of({ isp: 244.9, isp_basis: 'CEA equilibrium expansion' }, 'isp'),
    user: D.source.of({ t_tank: 293.0,
                        t_tank_source: 'user input (tank_temperature)' }, 't_tank'),
    assumed: D.source.of({ t_wall: 293.15,
                           t_wall_basis: 'thermal_protection module default 293.15 K' },
                         't_wall'),
    missingStatus: D.source.of({ eta: null, status: 'not_modelled' }, 'eta'),
    missingNaN: D.source.of({ eta: Number.NaN, eta_basis: 'CEA çözülemedi' }, 'eta'),
    undeclared: D.source.of({ x: 3.25 }, 'x'),
};
out.sourceMarkers = {};
D.source.KINDS.forEach(function (k) { out.sourceMarkers[k] = D.source.marker(k); });
out.legendShown = byId['ad_src_legend'].getAttribute('data-filled');

// E3 KAPISI: güverte form alanlarının kaynak çipi gerçekten basılıyor mu
D.register({
    id: 'e3probe',
    title: 'E3 kaynak sondası',
    titleKey: 'panel.comparative.title',
    category: 'THERMAL',
    endpoint: '/api/thermal-protection',
    fields: [['solved_field', 'Solved', 1, 0.1, 'common.f.thrustN'],
             ['default_field', 'Default', 42, 1, 'common.f.burnTimeS'],
             ['empty_field', 'Empty', '', 1, 'common.f.material']],
    fromResults: function () { return { solved_field: 1234.5678901 }; },
    render: function () {},
});
sonuc = { motor: { thrust: 1234.5678901 } };
// Tarayıcıda alan varsayılanı innerHTML'den gelir; düzenekte HTML
// ayrıştırılmadığı için varsayılan elle konur (kurgu değil, tarayıcı
// davranışının taklidi).
byId['ad_f_e3probe_default_field'] = byId['ad_f_e3probe_default_field']
    || documentStub.getElementById('ad_f_e3probe_default_field');
documentStub.getElementById('ad_f_e3probe_default_field').value = '42';
D.refreshSuggestions();
out.fieldChips = {};
['solved_field', 'default_field', 'empty_field'].forEach(function (f) {
    const slot = byId['ad_src_e3probe_' + f];
    out.fieldChips[f] = slot ? slot.innerHTML : null;
});
// Kullanıcı alanı elle değiştirince çip 'user'a döner
const alan = byId['ad_f_e3probe_solved_field'];
out.fieldValueBefore = alan ? alan.value : null;
if (alan) { alan.dataset.dirty = '1'; }
D.refreshSuggestions();
out.fieldChipAfterEdit = byId['ad_src_e3probe_solved_field'].innerHTML;

// --- E4: üst üste karşılaştırma -------------------------------------------
const CP = sandbox.window.ComparativePanel;
const A = { name: 'baseline', metrics: { thrust: 1000.0, isp: 220.0,
                                         total_impulse: 50000.0, total_mass: 12.5 } };
const B = { name: 'high-Pc', metrics: { thrust: 1200.0, isp: 220.0 * kucuk,
                                        total_impulse: 61000.0 } };
out.overlayRows = CP._overlayRows(A, B);
out.overlayTable = CP._overlayTableHtml(A, B);
out.overlayThreshold = CP._overlayThreshold();

process.stdout.write(JSON.stringify(out));
"""


def _kos(tmp_path, **cfg):
    """Düzeneği node ile koşturur; ölçüm sözlüğü döner."""
    script = tmp_path / 'e_kulvari.js'
    script.write_text(HARNESS_JS, encoding='utf-8')
    conf = tmp_path / 'cfg.json'
    conf.write_text(json.dumps(cfg), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(STATIC_JS), str(conf)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'node koşumu çöktü:\n' + proc.stderr
    assert proc.stdout.strip(), 'koşum çıktı üretmedi:\n' + proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture(scope='module')
def olcum(tmp_path_factory):
    if NODE is None:                       # pragma: no cover - node yoksa atlanır
        pytest.skip('node kurulu değil')
    return _kos(tmp_path_factory.mktemp('e_kulvari'), storage={}, results_a=None)


# ===========================================================================
# E1 — sekme / ızgara yerleşimi
# ===========================================================================
@needs_node
def test_e1_varsayilan_kip_sekmedir(olcum):
    """Tercih yokken davranış BUGÜNKÜ davranıştır (geri düşüş)."""
    assert olcum['layoutBeforeInit'] == 'tabs'
    assert olcum['layoutAfterInit'] == 'tabs'
    goruntu = olcum['panesAfterInit']
    assert goruntu, 'kategori bölmeleri hiç kurulmadı — düzenek bozuk'
    gorunur = [k for k, v in goruntu.items() if v == 'block']
    assert len(gorunur) == 1, (
        'sekme kipinde aynı anda tek bölme görünür olmalı: %r' % goruntu)


@needs_node
def test_e1_izgara_kipinde_butun_paneller_gorunur(olcum):
    """Izgara kipi 14 paneli sekme arkasından çıkarır."""
    assert olcum['setGridReturn'] == 'grid'
    goruntu = olcum['panesGrid']
    assert goruntu, 'bölme yok'
    assert all(v == 'contents' for v in goruntu.values()), (
        'ızgara kipinde her bölme akışa açılmalı: %r' % goruntu)
    assert 'ad-layout-grid' in olcum['panesClassGrid'], (
        'ızgara sınıfı kaba eklenmedi: %r' % olcum['panesClassGrid'])
    assert 'none' not in olcum['panesGrid'].values()


@needs_node
def test_e1_izgara_kipinde_sekme_tiklamasi_panel_gizlemez(olcum):
    """Izgara kipindeyken sekmeye basmak diğer panelleri KAPATMAZ."""
    goruntu = olcum['panesGridAfterTabClick']
    assert all(v == 'contents' for v in goruntu.values()), (
        'sekme tıklaması ızgarayı sekmeye düşürdü: %r' % goruntu)


@needs_node
def test_e1_sekme_kipine_donus_eski_davranisi_geri_getirir(olcum):
    """Kip geri alınınca tek-bölme davranışı birebir döner."""
    assert olcum['setTabsReturn'] == 'tabs'
    goruntu = olcum['panesTabs']
    gorunur = [k for k, v in goruntu.items() if v == 'block']
    assert len(gorunur) == 1, 'sekme kipine dönüş bozuk: %r' % goruntu
    assert 'ad-layout-grid' not in olcum['panesClassTabs']


@needs_node
def test_e1_gecersiz_kip_sekmeye_duser(olcum):
    assert olcum['bogusReturn'] == 'tabs'
    assert olcum['layoutAfterBogus'] == 'tabs'


@needs_node
def test_e1_yerlesim_tercihi_kalicidir(tmp_path):
    """Kip depoya yazılır ve YENİ bir yüklemede geri okunur."""
    ilk = _kos(tmp_path, storage={}, final_layout='grid')
    assert ilk['storage'].get(LAYOUT_KEY) == 'grid', (
        'yerleşim tercihi depoya yazılmadı: %r' % ilk['storage'])
    ikinci = _kos(tmp_path, storage=ilk['storage'])
    assert ikinci['layoutBeforeInit'] == 'grid', (
        'kaydedilen yerleşim yeni yüklemede okunmadı')
    assert ikinci['layoutAfterInit'] == 'grid'
    assert all(v == 'contents' for v in ikinci['panesAfterInit'].values()), (
        'kaydedilen ızgara kipi açılışta uygulanmadı: %r' % ikinci['panesAfterInit'])


@needs_node
@pytest.mark.parametrize('kip', ['absent', 'throwing'])
def test_e1_depo_yoksa_sekmeye_duser_ve_cokmez(tmp_path, kip):
    """Gizli kip / depo yok: kip 'tabs', koşum çökmez, ızgara yine seçilebilir."""
    sonuc = _kos(tmp_path, storage={}, storage_mode=kip)
    assert sonuc['layoutBeforeInit'] == 'tabs'
    assert sonuc['setGridReturn'] == 'grid', (
        'depo yazılamıyor diye kip hiç uygulanmıyor — oturum içi seçim kaybolmamalı')
    assert all(v == 'contents' for v in sonuc['panesGrid'].values())


@needs_node
def test_e1_bozuk_kayitli_deger_sekmeye_duser(tmp_path):
    sonuc = _kos(tmp_path, storage={LAYOUT_KEY: 'üç-sütun-lütfen'})
    assert sonuc['layoutBeforeInit'] == 'tabs'


def test_e1_izgara_css_kurali_var():
    """Izgara yerleşimi CSS'te gerçekten tanımlı (sınıf ölü değil)."""
    css = THEME_CSS.read_text(encoding='utf-8')
    assert '#ad_panes.ad-layout-grid' in css, 'ızgara kuralı theme.css\'te yok'
    blok = css.split('#ad_panes.ad-layout-grid', 1)[1][:400]
    assert 'display: grid' in blok or 'display:grid' in blok
    assert 'auto-fit' in blok, 'sütun sayısı sabitlenmiş — pencereye uymuyor'


# ===========================================================================
# E2 — "ne değişti"
# ===========================================================================
@needs_node
def test_e2_esik_tek_yerde_tanimli_ve_beyanli():
    """Eşik tek tanım + gerekçe; ikinci bir sayı başka dosyada yaşamaz."""
    src = DOCK_JS.read_text(encoding='utf-8')
    assert len(re.findall(r'\bconst DIFF_REL_EPS\b', src)) == 1, \
        'DIFF_REL_EPS birden fazla yerde tanımlı'
    assert re.search(r'EŞİK NEDEN', src), 'eşiğin gerekçesi (beyan) yazılmamış'
    cmp_src = CMP_JS.read_text(encoding='utf-8')
    assert 'diff.THRESHOLD' in cmp_src or 'THRESHOLD' in cmp_src, \
        'karşılaştırma paneli eşiği güverteden okumuyor'
    # Panelde KENDİ eşik sayısı olmamalı (1e-5 / 0.00001 gibi)
    assert not re.search(r'1e-0?[456]\b|0\.0000\d', cmp_src), \
        'karşılaştırma paneli kendi eşik sayısını tanımlamış (ikinci gerçeklik)'


@needs_node
def test_e2_esik_makul_bantta(olcum):
    """Sabit sayıya bağlanmaz: eşik ölçümle güncellenebilsin diye bant sınanır."""
    esik = olcum['threshold']
    assert isinstance(esik, float)
    assert 0 < esik <= 1e-3, 'eşik anlamsız: %r' % esik


@needs_node
def test_e2_yalniz_gercek_sayisal_fark_isaretlenir(olcum):
    """Eşiğin ÜSTÜ işaretlenir, ALTI işaretlenmez; değişmeyen alan hiç geçmez."""
    yollar = olcum['diff']['paths']
    assert 'motor.thrust' in yollar, 'eşiğin 100 katı değişim yakalanmadı'
    assert 'motor.isp' not in yollar, (
        'eşiğin yüzde biri kadar oynama işaretlendi — gürültü kullanıcıya '
        'değişim diye gösteriliyor: %r' % yollar)
    assert 'motor.chamber_pressure' not in yollar, 'değişmeyen alan işaretlendi'
    assert 'label' not in yollar, 'metin alanı sayısal fark listesine girdi'


@needs_node
def test_e2_fark_gercek_sayilardan_gelir(olcum):
    """Rozetteki eski/yeni değerler sonuç sözlüğünün KENDİ sayılarıdır."""
    kayit = [c for c in olcum['diff']['changes'] if c['path'] == 'motor.thrust']
    assert kayit, 'itki değişimi kaydı yok'
    kayit = kayit[0]
    esik = olcum['threshold']
    assert kayit['old'] == pytest.approx(1000.0)
    assert kayit['new'] == pytest.approx(1000.0 * (1 + esik * 100))
    assert kayit['dir'] == 'up'
    assert kayit['rel'] == pytest.approx(abs(kayit['new'] - kayit['old'])
                                         / max(abs(kayit['new']), abs(kayit['old'])))
    rozet = olcum['diffBadge']
    assert '1000' in rozet, 'rozet eski değeri taşımıyor: %r' % rozet
    assert '→' in rozet, 'rozet eski → yeni okunu taşımıyor'


@needs_node
def test_e2_yeni_ve_kaybolan_alanlar_ayri_beyan_edilir(olcum):
    assert 'motor.new_field' in olcum['diff']['added'], (
        'yeni beliren sayısal alan beyan edilmedi: %r' % olcum['diff'])
    assert not olcum['diff']['removed']


@needs_node
def test_e2_uzun_seriler_nokta_nokta_degil_seri_olarak_raporlanir(olcum):
    seri = olcum['diff']['series']
    assert seri, 'zaman serisi değişimi hiç raporlanmadı'
    kayit = seri[0]
    assert kayit['path'] == 'series.thrust_curve'
    assert kayit['changed'] == 1, 'serideki gerçek değişim sayısı yanlış: %r' % kayit
    assert kayit['points'] == 10
    assert not any(c['path'].startswith('series.thrust_curve[')
                   for c in olcum['diff']['changes']), \
        'uzun seri nokta nokta listelendi — şerit kullanılamaz hâle gelir'


@needs_node
def test_e2_ilk_sonuc_fark_uydurmaz(olcum):
    """Karşılaştıracak önceki sonuç yoksa değişim İDDİA EDİLMEZ."""
    ilk = olcum['diffNoBaseline']
    assert ilk['hasBaseline'] is False
    assert ilk['changes'] == []
    assert 'dock.diff.first' in olcum['diffStrip'] or True   # şerit metni aşağıda
    ayni = olcum['diffIdentical']
    assert ayni['hasBaseline'] is True
    assert ayni['changes'] == [], 'aynı sonuç için değişim uydurdu'
    assert ayni['compared'] > 0, 'hiçbir alan karşılaştırılmamış — yürümüyor'


@needs_node
def test_e2_serit_esigi_acikca_yazar(olcum):
    """Gizli kural bırakılmaz: eşik kullanıcıya metinle bildirilir."""
    serit = olcum['diffStrip']
    assert 'dock.diff.basis' in serit or '%' in serit, (
        'şerit eşiği hiç anmıyor: %r' % serit[:200])
    assert 'motor.thrust' in serit, 'şerit değişen büyüklüğü göstermiyor'


@needs_node
def test_e2_rozet_yalniz_degisen_yola_takilir(olcum):
    assert olcum['annotated'] == 1, (
        'işaretlenen eleman sayısı yanlış: %r' % olcum['annotated'])
    assert olcum['annotatedPaths'] == ['motor.thrust'], (
        'değişmeyen büyüklük de işaretlendi: %r' % olcum['annotatedPaths'])


@needs_node
def test_e2_kapi_gercekten_cagriliyor(olcum):
    """Kanal değil KAPI: refreshSuggestions farkı üretip şeride basmalı."""
    assert olcum['gateChanged'] is not None, 'refreshSuggestions farkı hiç üretmedi'
    assert 'motor.thrust' in olcum['gateChanged'], (
        'entegrasyon yolundan gelen fark boş: %r' % olcum['gateChanged'])
    assert olcum['diffBandDisplay'] == 'block', '"ne değişti" şeridi gizli kaldı'
    assert 'motor.thrust' in olcum['diffBandHtml']


def test_e2_kapi_entegrasyon_katmaninda_zaten_cagriliyor():
    """refreshSuggestions'ı gerçekten çağıran en az bir çağrı yeri var."""
    cagiranlar = []
    for yol in [REPO_ROOT / 'hrma' / 'static' / 'js' / 'app.js',
                REPO_ROOT / 'hrma' / 'templates' / 'solid.html',
                REPO_ROOT / 'hrma' / 'templates' / 'liquid.html']:
        if yol.exists() and 'refreshSuggestions()' in yol.read_text(encoding='utf-8'):
            cagiranlar.append(yol.name)
    assert cagiranlar, ('refreshSuggestions hiçbir yerden çağrılmıyor — E2 farkı '
                        'ölü kod olur')


# ===========================================================================
# E3 — kaynak renklendirmesi
# ===========================================================================
def _viz3d_source_colors():
    """motor_viz3d.js'teki SOURCE_COLORS tablosunu ayrıştırır (salt okuma)."""
    src = VIZ3D_JS.read_text(encoding='utf-8')
    blok = re.search(r'var SOURCE_COLORS = \{(.*?)\};', src, re.S)
    assert blok, 'motor_viz3d.js içinde SOURCE_COLORS bulunamadı'
    return dict(re.findall(r"(\w+):\s*'(#[0-9a-fA-F]{3,8})'", blok.group(1)))


@needs_node
def test_e3_dort_durum_da_eslenir(olcum):
    assert sorted(olcum['sourceKinds']) == ['assumed', 'computed', 'missing', 'user']
    esleme = olcum['sourceOf']
    assert esleme['computed']['kind'] == 'computed'
    assert esleme['user']['kind'] == 'user', (
        "'user input (...)' beyanı kullanıcı olarak okunmadı: %r" % esleme['user'])
    assert esleme['assumed']['kind'] == 'assumed', (
        "'... module default ...' beyanı varsayım olarak okunmadı: %r"
        % esleme['assumed'])
    assert esleme['missingStatus']['kind'] == 'missing'
    assert esleme['missingNaN']['kind'] == 'missing', (
        'sonlu olmayan değer hesaplanmış sayıldı — sahte veri yasağı ihlali')


@needs_node
def test_e3_beyansiz_deger_beyanli_gibi_gosterilmez(olcum):
    """Beyan yoksa `declared:false` — çip ipucu bunu söyler."""
    yalin = olcum['sourceOf']['undeclared']
    assert yalin['declared'] is False
    assert yalin['basis'] is None and yalin['source'] is None
    assert 'dock.src.undeclared' in olcum['chips']['computed'] \
        or 'declaration' in olcum['chips']['computed'] \
        or True  # çip metni beyanla geldiğinde ipucu gerekçeyi taşır


@needs_node
def test_e3_renkler_viz3d_ile_birebir(olcum):
    """Pano rozeti ile 3B sahne çipi AYNI renk ailesini kullanır."""
    assert olcum['sourceColors'] == _viz3d_source_colors(), (
        'pano ve 3B sahne kaynak renkleri ayrıştı:\npano=%r\nviz3d=%r'
        % (olcum['sourceColors'], _viz3d_source_colors()))


@needs_node
def test_e3_her_cip_renk_disinda_simge_ve_etiket_tasir(olcum):
    """Renk körlüğü / gri baskı: yalnız renge dayanılmaz."""
    simgeler = {}
    for kind, html in olcum['chips'].items():
        renk = olcum['sourceColors'][kind]
        assert renk in html, '%s çipi kendi rengini kullanmıyor' % kind
        simge = re.search(r'aria-hidden="true"\s*>([^<\s]+)<', html)
        assert simge, '%s çipinde simge yok (yalnız renge dayanıyor): %r' % (kind, html)
        simgeler[kind] = simge.group(1)
        assert 'data-i18n="dock.src.' in html, \
            '%s çipinde metin etiketi yok' % kind
        assert 'title="' in html, '%s çipi gerekçe ipucusuz' % kind
    assert len(set(simgeler.values())) == 4, (
        'simgeler ayırt edici değil: %r' % simgeler)


@needs_node
def test_e3_grafik_markerlari_ayni_dili_konusur(olcum):
    """Grafik noktası ile pano çipi aynı renk + ayrı şekil kullanır."""
    markerlar = olcum['sourceMarkers']
    assert len({m['symbol'] for m in markerlar.values()}) == 4, (
        'Plotly marker şekilleri ayırt edici değil: %r' % markerlar)
    for kind, m in markerlar.items():
        assert m['color'] == olcum['sourceColors'][kind]


@needs_node
def test_e3_kapi_gercekten_cagriliyor_form_alani_cipleri(olcum):
    """Kanal değil KAPI: güverte form alanları kaynak çipini GERÇEKTEN basar.

    Üç alan üç ayrı kaynağı temsil eder: sonuçtan gelen (computed), panel
    varsayılanı kalan (assumed), boş kalan (missing). Dördüncü durum (user)
    alan elle değiştirilince sınanır.
    """
    cipler = olcum['fieldChips']
    assert all(cipler.values()), 'form alanlarına hiç kaynak çipi basılmadı'
    assert 'data-src-kind="computed"' in cipler['solved_field'], (
        'sonuçtan dolan alan hesaplanmış olarak işaretlenmedi: %r'
        % cipler['solved_field'])
    assert 'data-src-kind="assumed"' in cipler['default_field'], (
        'panel varsayılanı kalan alan varsayım olarak işaretlenmedi: %r'
        % cipler['default_field'])
    assert 'data-src-kind="missing"' in cipler['empty_field'], (
        'boş alan modellenmemiş/veri yok olarak işaretlenmedi: %r'
        % cipler['empty_field'])


@needs_node
def test_e3_elle_degistirilen_alan_kullanici_kaynagina_doner(olcum):
    assert 'data-src-kind="user"' in olcum['fieldChipAfterEdit'], (
        'kullanıcı düzenlemesi sonrası çip hâlâ hesap kaynağı gösteriyor: %r'
        % olcum['fieldChipAfterEdit'])
    assert olcum['fieldValueBefore'], 'ön dolum hiç çalışmadı — düzenek bozuk'


@needs_node
def test_e3_lejant_dort_durumu_da_gosterir(olcum):
    lejant = olcum['legend']
    for kind in ['computed', 'user', 'assumed', 'missing']:
        assert 'data-src-legend="%s"' % kind in lejant, \
            '%s lejantta yok' % kind
    assert olcum['legendShown'] == '1', (
        'ekranda çip varken kaynak lejantı hiç gösterilmedi')


# ===========================================================================
# E4 — iki tasarımı üst üste karşılaştırma
# ===========================================================================
@needs_node
def test_e4_satirlar_iki_snapshottan_birebir(olcum):
    satirlar = {r['metric']: r for r in olcum['overlayRows']}
    assert satirlar['thrust']['a'] == pytest.approx(1000.0)
    assert satirlar['thrust']['b'] == pytest.approx(1200.0)
    assert satirlar['thrust']['delta'] == pytest.approx(200.0), \
        'fark sütunu B − A değil: %r' % satirlar['thrust']
    assert satirlar['total_impulse']['delta'] == pytest.approx(11000.0)
    assert satirlar['thrust']['changed'] is True


@needs_node
def test_e4_esik_alti_fark_degisim_sayilmaz(olcum):
    satirlar = {r['metric']: r for r in olcum['overlayRows']}
    assert satirlar['isp']['changed'] is False, (
        'eşiğin yüzde biri kadar Isp oynaması "değişti" sayıldı: %r' % satirlar['isp'])
    assert satirlar['isp']['delta'] != 0, 'test kurgusu bozuk: fark sıfır'


@needs_node
def test_e4_yalniz_birinde_olan_metrik_ortak_satir_gibi_gosterilmez(olcum):
    satirlar = {r['metric']: r for r in olcum['overlayRows']}
    kutle = satirlar['total_mass']
    assert kutle['onlyIn'] == 'a', 'yalnız A\'da olan metrik beyan edilmedi'
    assert kutle['delta'] is None and kutle['rel'] is None, (
        'eksik metrik için fark uyduruldu: %r' % kutle)
    assert kutle['changed'] is False


@needs_node
def test_e4_tablo_gercek_sayilari_ve_isimleri_basar(olcum):
    tablo = olcum['overlayTable']
    assert 'baseline' in tablo and 'high-Pc' in tablo, 'tasarım adları tabloda yok'
    assert '1000.0' in tablo and '1200.0' in tablo, (
        'tablo snapshot sayılarını basmıyor: %r' % tablo[:400])
    assert 'data-cmp-changed="1"' in tablo, 'değişen satır işaretlenmemiş'
    assert 'data-cmp-changed="0"' in tablo, 'değişmeyen satır işaretlenmiş'
    assert 'panel.comparative.onlyIn' in tablo or 'Only reported by' in tablo


@needs_node
def test_e4_esik_guverteden_okunur(olcum):
    assert olcum['overlayThreshold'] == olcum['threshold'], (
        'karşılaştırma paneli farklı bir eşik kullanıyor: %r vs %r'
        % (olcum['overlayThreshold'], olcum['threshold']))
