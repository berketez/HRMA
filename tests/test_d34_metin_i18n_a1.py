# -*- coding: utf-8 -*-
"""ÖH Dalga 34 · kulvar metin-i18n · aşama A1 bekçileri.

Altı kalem (OH-GT-01..06). Bekçilerin ortak kuralı: KAYNAK DİZESİ ARAMAK
YETMEZ — ürünün kendi yolları koşturulur.

  * Sunucu tarafı: Flask test istemcisiyle gerçek uçlar.
  * Tarayıcı tarafı: node içinde ürünün KENDİ ``i18n.js`` / ``i18n_*.js`` /
    panel dosyaları çalıştırılır; çeviri ve panel davranışı oradan okunur.
  * Olay kümesi çözücünün KAYNAĞINDAN (AST) çıkarılır; elle yazılmış bir
    liste ile kıyaslanmaz.

Ölçümler: ``docs/scofield/raw/OH/D34/metin-i18n/a1/once.json`` (onarım
öncesi) ve ``sonra.json`` (sonrası).
"""
import ast
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

CALC_HEADERS = {'X-Requested-With': 'XMLHttpRequest'}

#: OH-GT-01 ölçüm noktası — sayfanın form varsayılanları
#: (tests/test_faz6_f2b_sivi.py::LIQUID_FORM ile aynı tasarım noktası).
LIQUID_FORM = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox',
    'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'nozzle_expansion_ratio': 50, 'max_burn_duration': 400,
    'combustion_efficiency': 97, 'contraction_ratio': 4,
    'characteristic_length': 1.2, 'chamber_wall_thickness': 5,
    'cooling_type': 'regenerative', 'injector_type': 'impinging',
    'engine_cycle': 'pressure_fed', 'safety_factor': 2.5,
    'cooling_channels': 80,
}
# ÖH A2 sivi-sogutma F-17 (Berke Sunum 2 onayı sonrası çeviri, denetçi Ş5.1):
# iki sığma ölçütü tek tanıma indi; eski kod artık basılmıyor ve sözlükten
# söküldü. Niyet (uyarı ÇEVREYİ yayımlar, çapı çevre diye basmaz) aynen.
FIT_CODE = 'warn.liquid.cooling_channels_exceed_fit_limit'
THIN_CODE = 'warn.structural.thin_wall_invalid'


# =========================================================================
# Ortak yardımcılar
# =========================================================================
def _uyarilari_topla(x, cikti=None):
    """Gövdenin HER yerindeki ``{'code': 'warn.*'}`` kayıtları."""
    cikti = [] if cikti is None else cikti
    if isinstance(x, dict):
        if isinstance(x.get('code'), str) and x['code'].startswith('warn.'):
            cikti.append({'code': x['code'], 'params': x.get('params') or {}})
        for v in x.values():
            _uyarilari_topla(v, cikti)
    elif isinstance(x, list):
        for v in x:
            _uyarilari_topla(v, cikti)
    return cikti


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def sivi_yanit(istemci):
    r = istemci.post('/calculate_liquid', json=LIQUID_FORM,
                     headers=CALC_HEADERS)
    assert r.status_code == 200, 'sıvı uç düştü: HTTP %s' % r.status_code
    return r.get_json()


def _node(betik, girdi):
    with tempfile.TemporaryDirectory() as tmp:
        bp = os.path.join(tmp, 'sonda.js')
        with open(bp, 'w', encoding='utf-8') as fh:
            fh.write(betik)
        gp = os.path.join(tmp, 'girdi.json')
        with open(gp, 'w', encoding='utf-8') as fh:
            json.dump(girdi, fh)
        p = subprocess.run([NODE, bp, str(JS), gp], capture_output=True,
                           text=True, timeout=600)
    assert p.returncode == 0, 'node çöktü:\n' + p.stderr[-3000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


#: Sözlük sondası — ürünün KENDİ I18N'i, DOM'suz.
SOZLUK_SONDA = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
const depo = {};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    document: { readyState: 'complete', addEventListener: function () {},
                querySelectorAll: function () { return []; },
                querySelector: function () { return null; },
                documentElement: { setAttribute: function () {} },
                createElement: function () { return { style: {} }; } },
    localStorage: {
        getItem: function (k) { return (k in depo) ? depo[k] : null; },
        setItem: function (k, v) { depo[k] = String(v); },
        removeItem: function (k) { delete depo[k]; } },
    navigator: { language: 'en-US' },
    matchMedia: function () { return { matches: true }; },
    performance: { now: function () { return 0; } },
    requestAnimationFrame: null,
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
function kos(f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
kos(path.join(staticDir, 'i18n.js'));
kos(path.join(staticDir, 'i18n_common.js'));
kos(path.join(staticDir, 'i18n_pages.js'));
kos(path.join(staticDir, 'i18n_advanced.js'));
kos(path.join(staticDir, 'i18n_charts.js'));
const OUT = { grafik: {}, anahtar: {}, var: {}, uyari: {} };
['en', 'tr'].forEach(function (dil) {
    sb.window.I18N.setLang(dil);
    OUT.grafik[dil] = (P.grafik || []).map(function (s) {
        return sb.window.I18N.chartText(s); });
    OUT.anahtar[dil] = {};
    (P.anahtar || []).forEach(function (a) {
        OUT.anahtar[dil][a] = sb.window.I18N.t(a, null); });
    OUT.var[dil] = {};
    (P.varMi || []).forEach(function (a) {
        OUT.var[dil][a] = !!sb.window.I18N.has(a); });
    OUT.uyari[dil] = {};
    (P.uyari || []).forEach(function (c) {
        OUT.uyari[dil][c.kod] = sb.window.I18N.tf(c.kod, c.params || {}, null); });
});
process.stdout.write(JSON.stringify(OUT));
"""

#: Panel sondası — bitiş olayı etiketi/rozeti (OH-GT-05) ve tane FEA
#: panelinin dil değişimi davranışı (OH-GT-06) ürünün kendi kodundan.
PANEL_SONDA = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
const KAYIT = {}; const HTMLKAYIT = [];
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this._a = {}; this._html = '';
    this.dataset = {}; this.id = ''; this.textContent = ''; this.checked = true;
}
Object.defineProperty(El.prototype, 'innerHTML', {
    get: function () { return this._html; },
    set: function (v) {
        this._html = String(v); HTMLKAYIT.push(this._html);
        var re = /id="([\w-]+)"/g; var m;
        while ((m = re.exec(this._html))) {
            if (!KAYIT[m[1]]) { var e = new El('div'); e.id = m[1]; KAYIT[m[1]] = e; }
        }
        var ilk = new El('div'); this._firstEl = ilk;
    }
});
Object.defineProperty(El.prototype, 'firstElementChild', {
    get: function () { return this._firstEl || null; } });
El.prototype.appendChild = function (x) { this.children.push(x); return x; };
El.prototype.insertBefore = function (x) { this.children.push(x); return x; };
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._a, k) ? this._a[k] : null; };
El.prototype.removeAttribute = function (k) { delete this._a[k]; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.querySelector = function () { return null; };
El.prototype.addEventListener = function () {};
const depo = {}; const DINLE = {};
const doc = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    documentElement: new El('html'),
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function (id) { return KAYIT[id] || null; },
    addEventListener: function (ad, fn) { (DINLE[ad] = DINLE[ad] || []).push(fn); },
    dispatchEvent: function (ev) {
        (DINLE[ev && ev.type] || []).forEach(function (f) { f(ev); }); },
};
function CustomEvent(t, o) { this.type = t; this.detail = (o || {}).detail; }
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: function () {}, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    Promise: Promise, Error: Error, isFinite: isFinite,
    parseFloat: parseFloat, parseInt: parseInt,
    alert: function () {}, document: doc, CustomEvent: CustomEvent,
    localStorage: {
        getItem: function (k) { return (k in depo) ? depo[k] : null; },
        setItem: function (k, v) { depo[k] = String(v); },
        removeItem: function (k) { delete depo[k]; } },
    navigator: { language: 'en-US' },
    matchMedia: function () { return { matches: true }; },
    performance: { now: function () { return 0; } },
    requestAnimationFrame: null,
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
function kos(f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
kos(path.join(staticDir, 'units_constants.js'));
kos(path.join(staticDir, 'i18n.js'));
kos(path.join(staticDir, 'i18n_common.js'));
kos(path.join(staticDir, 'i18n_pages.js'));
kos(path.join(staticDir, 'i18n_charts.js'));
kos(path.join(staticDir, 'transient_panel.js'));
kos(path.join(staticDir, 'blowdown_panel.js'));
kos(path.join(staticDir, 'fea_panel.js'));

const OUT = { olay: {}, harita: {}, fea: {} };
['en', 'tr'].forEach(function (dil) {
    sb.window.I18N.setLang(dil);
    OUT.olay[dil] = {};
    (P.olaylar || []).concat(P.uydurma || []).forEach(function (o) {
        OUT.olay[dil][o] = {
            transient: {
                etiket: sb.window.TransientPanel._endEventLabel(o),
                rozet: sb.window.TransientPanel._endEventKind(o) },
            blowdown: {
                etiket: sb.window.BlowdownPanel._endEventLabel(o),
                rozet: sb.window.BlowdownPanel._endEventKind(o) },
        };
    });
});
OUT.harita.transient = Object.keys(sb.window.TransientPanel._endEventKindMap).sort();
OUT.harita.blowdown = Object.keys(sb.window.BlowdownPanel._endEventKindMap).sort();

/* --- OH-GT-06: panel EN kurulur, dil TR'ye çevrilir, düğme okunur --- */
sb.window.I18N.setLang('en');
sb.window.GrainFeaPanel.init({
    anchorId: 'yok', hookName: 'displayResults',
    paramsProvider: function () { return null; },
    labelsProvider: function () {
        return {
            title: sb.window.I18N.t('solid.fea.title', 'Grain Section FEA'),
            intro: sb.window.I18N.t('solid.fea.intro', 'intro'),
            run: sb.window.I18N.t('solid.fea.run', 'Run grain section FEA'),
            showMesh: sb.window.I18N.t('solid.fea.show_mesh',
                                       'Show mesh wireframe'),
        };
    },
});
function kosuMetni() {
    var b = doc.getElementById('grainfea_run');
    if (b && b.textContent) return b.textContent;
    for (var i = HTMLKAYIT.length - 1; i >= 0; i--) {
        var m = /id="grainfea_run"[^>]*>([^<]*)</.exec(HTMLKAYIT[i]);
        if (m) return m[1];
    }
    return null;
}
OUT.fea.kurulum_en = kosuMetni();
sb.window.I18N.setLang('tr');
OUT.fea.tr_cevrildikten_sonra = kosuMetni();
OUT.fea.sozlukte_tr = sb.window.I18N.t('solid.fea.run', null);
sb.window.I18N.setLang('en');
OUT.fea.geri_en = kosuMetni();
process.stdout.write(JSON.stringify(OUT));
"""


# =========================================================================
# OH-GT-01 — sığmama uyarısı ÇEVREYİ yayımlar, çapı "çevre" diye basmaz
# =========================================================================
def test_gt01_sigmama_uyarisi_cevre_yayimlar(sivi_yanit):
    """Metne giren sayı gerçekten çevre mi? (ölçüm: once.json 30,8 mm çap)

    Kusur: ``d_ref_mm`` BOĞAZ ÇAPI idi, metin ona "boğaz çevresi" diyordu.
    Bekçi sayıyı motorun kendi boğaz çapıyla kıyaslar — dize aramaz.
    """
    kayit = [w for w in _uyarilari_topla(sivi_yanit) if w['code'] == FIT_CODE]
    assert kayit, ('%s uyarısı bu tasarım noktasında çıkmıyor; kalemin ön '
                   'koşulu kayboldu (cooling_channels=80).' % FIT_CODE)
    params = kayit[0]['params']
    assert 'c_ref_mm' in params, (
        'uyarı çevreyi yayımlamıyor; parametreler: %s' % sorted(params))
    assert 'd_ref_mm' not in params, (
        'çap hâlâ "çevre" adı altında yayımlanıyor: %s' % sorted(params))
    d_t_m = float(sivi_yanit['throat_diameter'])
    # Kanal TABANI çevresi (tek sığma ölçütü): 2*pi*(r_boğaz + t_sıcak_cidar).
    # Beklenen değer yayımlanan boğaz ÇAPINDAN bağımsız hesaplanır; t, aynı
    # yanıttaki sığma bloğunun yayımladığı sıcak cidar kalınlığıdır
    # (reference_circumference_mm alanı KULLANILMAZ — kopya olurdu).
    t_m = float(sivi_yanit['cooling_system']['channel_count_fit']
                ['hot_wall_thickness_mm']) / 1000.0
    beklenen = 2.0 * math.pi * (d_t_m / 2.0 + t_m) * 1000.0
    assert abs(float(params['c_ref_mm']) - beklenen) <= 0.05, (
        'c_ref_mm=%s ama 2*pi*(r_t + t)=%.3f mm' % (params['c_ref_mm'],
                                                  beklenen))
    # Çap DEĞİL: kusur geri gelirse bu sayı d_t'ye eşit olurdu.
    assert abs(float(params['c_ref_mm']) - d_t_m * 1000.0) > 1.0, (
        'yayımlanan sayı boğaz ÇAPINA eşit — kusur geri geldi')


@node_gerek
def test_gt01_sigmama_metni_iki_dilde_cevreyi_kullanir():
    """EN + TR metinleri ``{c_ref_mm}`` yer tutucusunu kullanır."""
    out = _node(SOZLUK_SONDA, {'uyari': [
        {'kod': FIT_CODE, 'params': {'n': 80, 'width_mm': 3.0,
                                     'land_mm': 1.5, 'need_mm': 360.0,
                                     'c_ref_mm': 109.3, 'd_ref_mm': 30.8,
                                     'n_max': 24}}]})
    for dil in ('en', 'tr'):
        metin = out['uyari'][dil][FIT_CODE]
        assert metin, '%s [%s] sözlükte yok' % (FIT_CODE, dil)
        assert '109,3' in metin or '109.3' in metin, (
            '%s [%s] çevreyi basmıyor: %s' % (FIT_CODE, dil, metin))
        assert '30,8' not in metin and '30.8' not in metin, (
            '%s [%s] hâlâ çapı basıyor: %s' % (FIT_CODE, dil, metin))


# =========================================================================
# OH-GT-02 — yapılmış iş "yapılmamış" gibi önerilmiyor
# =========================================================================
@pytest.fixture(scope='module')
def kalin_cidar_yaniti(istemci):
    r = istemci.post('/analyze_structural_safety', json={
        'chamber_pressure': 300, 'chamber_diameter': 0.1,
        'chamber_length': 0.5, 'throat_diameter': 0.02,
        'burn_time': 10, 'material': 'steel_4130'}, headers=CALC_HEADERS)
    assert r.status_code == 200, 'yapısal uç düştü: HTTP %s' % r.status_code
    return r.get_json()


def _pressure_hoop_model(govde):
    yig = [govde]
    while yig:
        n = yig.pop()
        if isinstance(n, dict):
            if 'pressure_hoop_model' in n:
                return n['pressure_hoop_model']
            yig.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            yig.extend(v for v in n if isinstance(v, (dict, list)))
    return None


def test_gt02_ince_cidar_uyarisi_cikarken_lame_zaten_kullaniliyor(
        kalin_cidar_yaniti):
    """Uyarının çıktığı koşumda ürün ZATEN Lamé kullanıyor (davranış).

    Metin "Lamé kullanın" derken model çoktan ``lame_thick_wall`` idi;
    kullanıcı ürünün yapmadığı bir şeyi yapması gerektiğini sanıyordu.
    """
    kodlar = [w['code'] for w in _uyarilari_topla(kalin_cidar_yaniti)]
    assert THIN_CODE in kodlar, 'ince cidar uyarısı bu koşumda çıkmıyor'
    assert _pressure_hoop_model(kalin_cidar_yaniti) == 'lame_thick_wall', (
        'uyarı çıkıyor ama model Lamé değil — kalemin dayanağı değişmiş')


@node_gerek
def test_gt02_ince_cidar_metni_yapilan_isi_anlatir():
    """Metin EMİR değil BEYAN: Lamé'nin kullanıldığını söyler."""
    out = _node(SOZLUK_SONDA, {'uyari': [{'kod': THIN_CODE, 'params': {}}]})
    en = out['uyari']['en'][THIN_CODE]
    tr = out['uyari']['tr'][THIN_CODE]
    assert en and tr, 'ince cidar metni sözlükte eksik'
    assert 'use thick-wall' not in en.lower(), (
        'EN metni hâlâ "use thick-wall" diye öğüt veriyor: %s' % en)
    assert 'kullanın' not in tr.lower(), (
        'TR metni hâlâ "kullanın" diye öğüt veriyor: %s' % tr)
    for dil, metin in (('EN', en), ('TR', tr)):
        assert 'Lam' in metin, '%s metninde Lamé adı yok: %s' % (dil, metin)
    assert 'WAS computed' in en or 'was computed' in en, (
        'EN metni yapılan işi beyan etmiyor: %s' % en)
    assert 'HESAPLANDI' in tr or 'hesaplandı' in tr, (
        'TR metni yapılan işi beyan etmiyor: %s' % tr)


# =========================================================================
# OH-GT-03 — Plotly başlıkları / seri adları TR'de çevriliyor
# =========================================================================
#: ``hrma/visualization/visualization.py`` içindeki dinamik ekli başlıklar.
#: Liste kaynağa ÇAPALIDIR: başlık dosyada değişirse bekçi kırılır ve
#: sözlüğün güncellenmesini zorlar (şablon-körü olmaması bundandır).
VIZ_BASLIKLARI = [
    '3D Performance Map: Chamber Pressure vs O/F vs Isp',
    'Nozzle Mach Number Distribution',
    'Wall heat flux, heat-sink wall',
]


def test_gt03_basliklar_kaynakta_hala_bu_dizelerle_uretiliyor():
    """Sözlük girdileri ürünün gerçekten bastığı dizelere bağlı kalsın."""
    kaynak = (ROOT / 'hrma' / 'visualization' / 'visualization.py').read_text(
        encoding='utf-8')
    eksik = [b for b in VIZ_BASLIKLARI if b not in kaynak]
    assert not eksik, (
        'visualization.py artık bu başlıkları basmıyor: %s — sözlük girdisi '
        'ölü kalmış olabilir, listeyi ve i18n_charts.js sözlüğünü '
        'birlikte güncelleyin.' % eksik)


@node_gerek
def test_gt03_basliklar_tr_kipinde_cevriliyor():
    """Dinamik ek (``<br><sub>…</sub>``, ``(temel)``) olsa da gövde çevrilir."""
    metinler = []
    for b in VIZ_BASLIKLARI:
        metinler.append(b)
        metinler.append(b + '<br><sub>ALT BASLIK</sub>')
    metinler.append('Wall heat flux, heat-sink wall (Bartz + Leckner)')
    out = _node(SOZLUK_SONDA, {'grafik': metinler})
    cevrilmeyen = [m for m, c in zip(metinler, out['grafik']['tr']) if m == c]
    assert not cevrilmeyen, (
        'TR kipinde İngilizce kalan grafik metni: %s' % cevrilmeyen)
    # EN kipinde metin DEĞİŞMEZ (çeviri katmanı İngilizceye dokunmaz).
    assert out['grafik']['en'] == metinler, 'EN kipinde metin değiştirilmiş'


@node_gerek
def test_gt03_cift_eksen_oku_efsane_cevirisini_bozmuyor():
    """'Thrust ←' gibi eksen oklu efsane adları da çevrilir.

    Ok BAŞIBOŞ DEĞİL: ``hrma/templates/solid.html``
    (``markDualAxisSeries``) üst üste düşen iki eğriyi ayırmak için
    efsane adının sonuna eksen yönü koyar. Ölçüldü (once_ok.json):
    ek yüzünden sözlük araması tutmuyor ve ad İngilizce kalıyordu.
    """
    metinler = ['Thrust', 'Thrust \u2190', 'Chamber Pressure \u2192',
                'Burn Area \u2190']
    out = _node(SOZLUK_SONDA, {'grafik': metinler + ['Bilinmeyen Seri \u2190']})
    cevrilmeyen = [m for m, c in zip(metinler, out['grafik']['tr']) if m == c]
    assert not cevrilmeyen, (
        'eksen oklu efsane adı TR kipinde İngilizce kaldı: %s' % cevrilmeyen)
    for m, c in zip(metinler[1:], out['grafik']['tr'][1:]):
        assert c.endswith(m[-1]), (
            'eksen oku çeviride kayboldu: %r -> %r' % (m, c))
    # Sözlükte olmayan taban DEĞİŞTİRİLMEZ (yedek davranış korunur).
    assert out['grafik']['tr'][-1] == 'Bilinmeyen Seri \u2190'


# =========================================================================
# OH-GT-04 — aynı kontrolün sayfadan sayfaya TEK Türkçe karşılığı
# =========================================================================
def _tr_buyut(metin):
    """Türkçe büyük harf: ``i`` -> ``İ``, ``ı`` -> ``I``.

    Python'un ``.upper()``/``.lower()``u Türkçe nokta kurallarını bilmez
    (``'İzometrik'.upper()`` noktasız ``I`` üretir); iki sözlüğün aynı
    sözcüğü yazıp yazmadığını kıyaslarken bu fark sahte kırmızı yapardı.
    """
    return metin.replace('i', 'İ').replace('ı', 'I').upper()


@node_gerek
def test_gt04_ayni_kontrol_tek_turkce_karsilik():
    """'Design Mode' ve 'Iso' iki sözlükte de AYNI Türkçeye bağlanır."""
    out = _node(SOZLUK_SONDA, {
        'grafik': ['Design Mode', 'Iso'],
        'anahtar': ['adv.btn.designMode', 'viz3d.cad.iso']})
    deck_design, deck_iso = out['grafik']['tr']
    adv_design = out['anahtar']['tr']['adv.btn.designMode']
    viz_iso = out['anahtar']['tr']['viz3d.cad.iso']
    assert _tr_buyut(deck_design) == _tr_buyut(adv_design), (
        "'Design Mode' iki sayfada farklı: şerit=%r, hibrit=%r"
        % (deck_design, adv_design))
    assert _tr_buyut(deck_iso) == _tr_buyut(viz_iso), (
        "kamera ISO kipi iki sayfada farklı: şerit=%r, 3B sahne=%r"
        % (deck_iso, viz_iso))


# =========================================================================
# OH-GT-05 — bitiş olayı: tam kapsam + çeviri + fail-closed
# =========================================================================
def _cozucu_olaylari():
    """``transient_ballistics.py`` içindeki ``event = '...'`` kümesi (AST)."""
    kaynak = (ROOT / 'hrma' / 'analysis' / 'transient_ballistics.py')
    agac = ast.parse(kaynak.read_text(encoding='utf-8'))
    olaylar = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Assign) and len(d.targets) == 1:
            t = d.targets[0]
            if (isinstance(t, ast.Name) and t.id == 'event'
                    and isinstance(d.value, ast.Constant)
                    and isinstance(d.value.value, str)):
                olaylar.add(d.value.value)
    return olaylar


def test_gt05_cozucu_olay_kumesi_bos_degil():
    olaylar = _cozucu_olaylari()
    assert len(olaylar) >= 6, (
        'çözücünün olay kümesi okunamadı (%s) — AST çıkarımı bozulmuş olabilir'
        % sorted(olaylar))


@node_gerek
def test_gt05_her_olayin_iki_dilde_etiketi_var():
    """Sözlük kapsamı çözücünün KENDİ kümesinden türetilir."""
    olaylar = sorted(_cozucu_olaylari())
    out = _node(SOZLUK_SONDA, {
        'varMi': ['transient.end.' + o for o in olaylar]})
    for dil in ('en', 'tr'):
        eksik = [o for o in olaylar
                 if not out['var'][dil]['transient.end.' + o]]
        assert not eksik, (
            '%s sözlüğünde etiketi olmayan bitiş olayı: %s' % (dil, eksik))


@node_gerek
def test_gt05_paneller_olay_kumesini_tam_kapsar_ve_fail_closed():
    """Rozet haritası TAM kapsar; bilinmeyen değer sessizce 'ok' olmaz."""
    olaylar = sorted(_cozucu_olaylari())
    uydurma = 'kimsenin_bilmedigi_olay'
    out = _node(PANEL_SONDA, {'olaylar': olaylar, 'uydurma': [uydurma]})
    for panel in ('transient', 'blowdown'):
        assert out['harita'][panel] == olaylar, (
            '%s_panel.js rozet haritası çözücü kümesiyle uyuşmuyor: '
            'panel=%s, çözücü=%s'
            % (panel, out['harita'][panel], olaylar))
    for o in olaylar:
        for panel in ('transient', 'blowdown'):
            tr_etiket = out['olay']['tr'][o][panel]['etiket']
            en_etiket = out['olay']['en'][o][panel]['etiket']
            assert tr_etiket and '(?)' not in tr_etiket, (
                '%s [%s] TR etiketi işaretli/ham kaldı: %r'
                % (o, panel, tr_etiket))
            assert o.upper() != tr_etiket, (
                '%s [%s] ekrana HAM makine sabiti olarak basılıyor' % (o, panel))
            assert en_etiket, '%s [%s] EN etiketi yok' % (o, panel)
    # FAIL-CLOSED: tanınmayan olay ham + işaretli basılır, rozeti 'warn'.
    for panel in ('transient', 'blowdown'):
        kayit = out['olay']['tr'][uydurma][panel]
        assert kayit['etiket'] == uydurma.upper() + ' (?)', (
            '%s_panel.js bilinmeyen olayı işaretlemiyor: %r'
            % (panel, kayit['etiket']))
        assert kayit['rozet'] == 'warn', (
            '%s_panel.js bilinmeyen olayı sessizce %r rozetine düşürüyor'
            % (panel, kayit['rozet']))


# =========================================================================
# OH-GT-06 — tane FEA paneli dil değişiminde yeniden etiketleniyor
# =========================================================================
@node_gerek
def test_gt06_tane_fea_dugmesi_dil_degisince_cevriliyor():
    """Panel EN kurulur, dil TR olur; koşu düğmesi Türkçeye döner.

    Ölçülen kusur (once.json): sözlükte Türkçesi VARDI ve etiket
    sağlayıcısı yeniden çağrılıyordu, ama panelin durağan iskeleti yalnız
    kurulum anında yazılıyordu — düğme 'Run grain section FEA' kalıyordu.
    """
    out = _node(PANEL_SONDA, {'olaylar': [], 'uydurma': []})
    fea = out['fea']
    assert fea['sozlukte_tr'], 'solid.fea.run TR karşılığı sözlükte yok'
    assert fea['kurulum_en'] == 'Run grain section FEA', (
        'kurulum İngilizce değil: %r' % fea['kurulum_en'])
    assert fea['tr_cevrildikten_sonra'] == fea['sozlukte_tr'], (
        'dil TR olduğu hâlde düğme %r diyor (sözlük: %r)'
        % (fea['tr_cevrildikten_sonra'], fea['sozlukte_tr']))
    # Geri dönüş de çalışır: etiket donmuş değil, her çizimde yeniden yazılır.
    assert fea['geri_en'] == 'Run grain section FEA', (
        'EN\'e dönüşte düğme %r kaldı' % fea['geri_en'])
