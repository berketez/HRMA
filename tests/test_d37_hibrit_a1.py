"""ÖH D37 · A1a · kulvar hibrit-beyan (kart A1a-4) bekçileri — 24 Eylül 2026.

Kanıt: docs/scofield/raw/OH/A1a/hibrit-beyan/a1/ (once.json, sonra.json,
mutasyon.md, rapor.md). Bu dosya docs kanıtını OKUMAZ: bütün girdiler ürün
kaynağından (app.js / advanced.html / sözlükler) ya da uçun kendisinden
(Flask test istemcisi) gelir; yayın dalında da koşar.

Kalemler ve bekçileri
---------------------
CW-A4E6   ``defaults_applied`` künyesi ekranda: uçun GERÇEK listesi
          ``defaultsAppliedBlock`` ile çizilir, listedeki her ad ekranda;
          liste boşsa blok yok; ``not_supplied_solver_derives`` kaydının
          "türet" işareti (0) sayı olarak basılmaz.
CW-B3     Ana zincir kartı iki sorunun metnini, iki sayıyı ve künyeyi taşır;
          FEA koşulmadıysa ikinci sayı UYDURULMAZ (gri "koşulmadı").
CW-U6     ``app.js`` + ``advanced.html``de ``alert(`` çağrısı 0 (yorumsuz
          kaynak); ``showError``/``showInfo``/``handleError`` sayfa içi,
          kendiliğinden kaybolmayan, Kapat düğmeli bildirim üretir; açılır
          pencerenin indirme düğmeleri ana pencere yokken pencere içi
          bildirim üretir.
OH-D31-04 Soğutma menüsü notu uçun ``equivalence_classes`` alanından
          kurulur (liste elle yazılmaz); alan yoksa not gizli.
DV36-14   ``advanced.html``de sökülen kardeş sayfaya bayat atıf kalmaz.
OH-P-07   Regresyon grafiğinin İÇ Plotly düğümü sayfanın dış-kap asgari
          yüksekliğini devralmaz (canlı ölçüm sonra.json M6: boşluk 180 →
          2 px).
DV-GT27   Dolum kütlesi satırlarının etiket hücresi ham alan adından ibaret
          değildir (EN + TR çevrilmiş etiket + alan imi).
CM-H2     ``_downloadExport`` ihraç gövdesi ``currentResults.motor``un
          ``injector_design`` bloğunu AYNEN taşır (sentetik gövde; CM-H1'e
          bağımlı değil).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
APP_JS = JS / 'app.js'
SABLON = KOK / 'hrma' / 'templates' / 'advanced.html'
I18N_COMMON = JS / 'i18n_common.js'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _oku(yol: pathlib.Path) -> str:
    return yol.read_text(encoding='utf-8')


def _islev(metin: str, bas: str) -> str:
    """``bas`` ile başlayan işlevin tam metni (süslü parantez eşlemesiyle)."""
    i = metin.index(bas)
    j = metin.index('{', i)
    derinlik = 0
    for k in range(j, len(metin)):
        c = metin[k]
        if c == '{':
            derinlik += 1
        elif c == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[i:k + 1]
    raise AssertionError(f'{bas!r} kapanmadı')


def _js_yorumsuz(kaynak: str) -> str:
    """JS yorumlarını söker; dize/şablon/regex içeriğine dokunmaz.

    Hafif bir tarayıcıdır: tek/çift tırnak, ters tırnak ve ``//``, ``/* */``
    ayırt edilir. Regex hazır değerleri nadirdir ve ``alert(`` taşımaz;
    sayım için yeterlidir (ters mutasyonla sınandı: mutasyon.md).
    """
    out = []
    i, n = 0, len(kaynak)
    tirnak = None
    while i < n:
        c = kaynak[i]
        if tirnak:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(kaynak[i + 1])
                i += 2
                continue
            if c == tirnak:
                tirnak = None
            i += 1
            continue
        if c in '\'"`':
            tirnak = c
            out.append(c)
            i += 1
            continue
        if kaynak.startswith('//', i):
            j = kaynak.find('\n', i)
            i = n if j < 0 else j
            continue
        if kaynak.startswith('/*', i):
            j = kaynak.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _sablon_betikleri() -> str:
    """advanced.html'deki satır içi betik gövdeleri, yorumları sökülmüş."""
    src = _oku(SABLON)
    src = re.sub(r'<!--.*?-->', ' ', src, flags=re.S)
    govdeler = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', src,
                          flags=re.S)
    return '\n'.join(_js_yorumsuz(g) for g in govdeler)


ALERT_RE = re.compile(r'(?<![\w.$])(?:window\.)?alert\s*\(')


# ---------------------------------------------------------------------------
# node koşum takımı — app.js'i (ve istenirse sözlükleri) sahte DOM'la
# GERÇEKTEN çalıştırır. Sahte DOM yalnız ürünün kullandığı yüzeyi taşır.
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [jsDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
const kayitliZamanlayici = [];
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this._a = {}; this._l = {};
    this._html = ''; this.textContent = ''; this.id = ''; this.className = '';
    this.parentNode = null; this.hidden = false; this.options = [];
    this.dataset = {}; this.value = '';
}
Object.defineProperty(El.prototype, 'innerHTML', {
    get: function () { return this._html; },
    set: function (v) { this._html = String(v); if (!v) this.children = []; },
});
El.prototype.appendChild = function (x) { x.parentNode = this; this.children.push(x); return x; };
El.prototype.insertBefore = function (x, ref) {
    x.parentNode = this; const i = this.children.indexOf(ref);
    if (i < 0) this.children.push(x); else this.children.splice(i, 0, x); return x; };
El.prototype.removeChild = function (x) {
    const i = this.children.indexOf(x); if (i >= 0) this.children.splice(i, 1);
    x.parentNode = null; return x; };
El.prototype.remove = function () { if (this.parentNode) this.parentNode.removeChild(this); };
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); if (k === 'id') this.id = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._a, k) ? this._a[k] : null; };
El.prototype.removeAttribute = function (k) { delete this._a[k]; };
El.prototype.addEventListener = function (t, f) { (this._l[t] = this._l[t] || []).push(f); };
El.prototype.fire = function (t, e) { (this._l[t] || []).forEach(function (f) { f(e); }); };
El.prototype.focus = function () { doc.activeElement = this; };
El.prototype.click = function () { this.fire('click', { preventDefault: function () {} }); };
El.prototype.querySelectorAll = function (sel) {
    const cls = String(sel).replace(/^\./, ''); const out = [];
    (function gez(n) { n.children.forEach(function (c) {
        if ((' ' + c.className + ' ').indexOf(' ' + cls + ' ') >= 0) out.push(c);
        gez(c); }); })(this);
    return out; };
El.prototype.querySelector = function (sel) { return this.querySelectorAll(sel)[0] || null; };
El.prototype.metin = function () {
    return this.textContent + this.children.map(function (c) { return c.metin(); }).join(''); };

const nodes = {};
const doc = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    documentElement: new El('html'), activeElement: null,
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function (id) { return nodes[id] || null; },
    addEventListener: function () {},
    contains: function () { return true; },
};
const depo = {};
const alertKaydi = [];
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {},
               group: function () {}, groupEnd: function () {} },
    setTimeout: function (f, ms) { kayitliZamanlayici.push(ms); return 0; },
    clearTimeout: function () {},
    setInterval: function () {}, clearInterval: function () {},
    fetch: function () { return Promise.reject(new Error('ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date, Promise: Promise,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    alert: function (m) { alertKaydi.push(String(m)); }, document: doc,
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
function kos(f) { vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
if (P.sozluk) {
    kos(path.join(jsDir, 'i18n.js'));
    kos(path.join(jsDir, 'i18n_common.js'));
}
kos(path.join(jsDir, 'app.js'));
if (P.sozluk) sb.window.I18N.setLang(P.dil || 'en');
const OUT = {};

// CW-A4E6
if (P.defaults_results !== undefined) {
    OUT.defaults_html = sb.defaultsAppliedBlock(P.defaults_results);
}
// CW-B3
if (P.wall_motor !== undefined) {
    if (P.fea_payload !== undefined) sb.window.ThermalFeaPanel = { payload: P.fea_payload };
    OUT.wall_html = sb.wallTemperatureQuestionsBlock(P.wall_motor);
    delete sb.window.ThermalFeaPanel;
}
// OH-D31-04
if (P.cooling_motor !== undefined) {
    const not = new El('div'); not.id = 'coolingEquivalenceNote'; not.hidden = true;
    const menu = new El('select'); menu.id = 'cooling_channels';
    (P.menu || []).forEach(function (o) {
        const op = new El('option'); op.value = o[0]; op.textContent = o[1];
        menu.options.push(op); });
    nodes.coolingEquivalenceNote = not; nodes.cooling_channels = menu;
    sb.coolingEquivalenceNote(P.cooling_motor);
    OUT.cooling = { text: not.textContent, hidden: not.hidden };
    delete nodes.coolingEquivalenceNote; delete nodes.cooling_channels;
}
// DV-GT27
if (P.dolum_motor !== undefined) {
    OUT.dolum_html = sb.loadedMassRows(P.dolum_motor);
}
// CW-U6 — app.js bildirimleri
if (P.bildirim) {
    const kap = new El('div'); kap.id = 'hrmaNotices'; nodes.hrmaNotices = kap;
    kayitliZamanlayici.length = 0;
    sb.showError('ornek-hata');
    sb.showInfo('ornek-bilgi');
    sb.handleError(new Error('HTTP 500: ornek'), 'ornek');
    const notlar = kap.querySelectorAll('.hrma-notice');
    OUT.bildirim = {
        alert: alertKaydi.slice(),
        sayi: notlar.length,
        rol: notlar.map(function (n) { return n.getAttribute('role'); }),
        kapat: notlar.map(function (n) {
            const b = n.children.filter(function (c) { return c.tagName === 'BUTTON'; })[0];
            return b ? b.textContent : null; }),
        metin: notlar.map(function (n) { return n.metin(); }),
        zamanlayici: kayitliZamanlayici.slice(),
        odak_bildirimde: !!(doc.activeElement && doc.activeElement.className
                            && doc.activeElement.className.indexOf('hrma-notice') >= 0),
    };
    // Kapat düğmesi bildirimi kaldırır.
    const ilk = notlar[0];
    const b = ilk.children.filter(function (c) { return c.tagName === 'BUTTON'; })[0];
    b.click();
    OUT.bildirim.kapattiktan_sonra = kap.querySelectorAll('.hrma-notice').length;
    // Escape de kapatır.
    const ikinci = kap.querySelectorAll('.hrma-notice')[0];
    ikinci.fire('keydown', { key: 'Escape', preventDefault: function () {} });
    OUT.bildirim.escape_sonra = kap.querySelectorAll('.hrma-notice').length;
    delete nodes.hrmaNotices;
}
// CW-U6 — ağ kopması bildirimi (D22 P17B4-02 ölçümünün bildirim kanalı)
if (P.ag_imzalari) {
    const kap = new El('div'); kap.id = 'hrmaNotices'; nodes.hrmaNotices = kap;
    OUT.ag = P.ag_imzalari.map(function (msg) {
        const r = sb.handleError(new TypeError(msg), 'Main Calculation Function');
        const n = kap.querySelectorAll('.hrma-notice');
        return { imza: msg, kaynak: r.source, metin: n.length ? n[n.length - 1].metin() : '' };
    });
    OUT.ag_alert = alertKaydi.slice();
    delete nodes.hrmaNotices;
}
// CW-U6 — açılır pencere betiği (şablondan)
if (P.popup_betik) {
    const kap = new El('div'); kap.id = 'popupNotices'; nodes.popupNotices = kap;
    sb.opener = null;
    alertKaydi.length = 0;
    vm.runInContext(P.popup_betik, sb, { filename: 'popup.js' });
    const sonuc = {};
    ['downloadSTL', 'downloadCAD', 'downloadDrawings', 'downloadSpecs'].forEach(function (ad) {
        sb[ad]();
        const n = kap.querySelectorAll('.hrma-notice');
        sonuc[ad] = { sayi: n.length, rol: n.length ? n[0].getAttribute('role') : null,
                      metin: n.length ? n[0].metin() : '' };
    });
    OUT.popup = { sonuc: sonuc, alert: alertKaydi.slice() };
    delete nodes.popupNotices;
}
// CM-H2 — ihraç gövdesi (şablonun _downloadExport'u)
if (P.ihrac_betik) {
    const ad = new El('input'); ad.id = 'motor_name'; ad.value = 'bekci-motor';
    nodes.motor_name = ad;
    let govde = null;
    sb.fetch = function (u, o) { govde = JSON.parse(o.body);
        return Promise.resolve({ ok: false, status: 499,
            json: function () { return Promise.resolve({ error: 'bekci' }); } }); };
    sb.showMessage = function () {};
    sb.i18nText = function (k, f) { return f; };
    sb.i18nFmt = function (k, p, f) { return f; };
    sb._ihracRetMetni = function () { return 'bekci'; };
    sb.currentResults = P.ihrac_sonuc;
    vm.runInContext(P.ihrac_betik + '\n;globalThis._downloadExport = _downloadExport;', sb,
                    { filename: 'ihrac.js' });
    sb._downloadExport('/api/export-step', 'b.step', 'STEP').then(function (r) {
        OUT.ihrac = { donus: r, govde: govde };
        process.stdout.write(JSON.stringify(OUT));
    });
} else {
    process.stdout.write(JSON.stringify(OUT));
}
"""


def _node(girdi: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        betik = os.path.join(tmp, 'kosum.js')
        with open(betik, 'w', encoding='utf-8') as fh:
            fh.write(HARNESS)
        veri = os.path.join(tmp, 'girdi.json')
        with open(veri, 'w', encoding='utf-8') as fh:
            json.dump(girdi, fh)
        p = subprocess.run([NODE, betik, str(JS), veri], capture_output=True,
                           text=True, timeout=300)
    assert p.returncode == 0, 'node çöktü:\n' + p.stderr[-3000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def _metin(html: str) -> str:
    t = re.sub(r'<[^>]+>', ' ', html or '')
    t = t.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return ' '.join(t.replace(' ', ' ').split())


# ---------------------------------------------------------------------------
# CW-A4E6 — defaults_applied künyesi (uçun GERÇEK listesi)
# ---------------------------------------------------------------------------
#: Ornek-H1 (D35 onemli-hibrit-fizik a1 ``olcum.py`` ORNEK_H1 elle alanları;
#: Cowork görsel turu 21 Eyl): enjektör/geometri alanlarının hiçbiri yok.
ORNEK_H1 = {
    'thrust': 1000.0, 'burn_time': 10.0, 'chamber_pressure': 20.0,
    'of_ratio': 7.5, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'tank_pressure': 50.0, 'injector_type': 'showerhead',
}


@pytest.fixture(scope='module')
def ornek_h1_yaniti():
    from hrma.app import app
    app.config['TESTING'] = True
    buf = io.StringIO()
    with app.test_client() as c, contextlib.redirect_stdout(buf), \
            contextlib.redirect_stderr(buf):
        r = c.post('/calculate', json=ORNEK_H1)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@node_gerekli
def test_cwa4e6_ucun_listesindeki_her_ad_ekranda(ornek_h1_yaniti):
    liste = ornek_h1_yaniti.get('defaults_applied')
    assert isinstance(liste, list) and liste, (
        'Ornek-H1 yanıtı defaults_applied yayımlamıyor — bekçinin ölçeceği '
        'künye yok (uç sözleşmesi değişmiş olabilir)')
    for dil in ('en', 'tr'):
        out = _node({'sozluk': True, 'dil': dil,
                     'defaults_results': ornek_h1_yaniti})
        html = out['defaults_html']
        satirlar = re.findall(r'data-defaults-applied-field="([^"]+)"', html)
        adlar = [k['field'] if isinstance(k, dict) else k for k in liste]
        assert satirlar == adlar, (
            '%s: ekrandaki künye satırları uçun listesiyle aynı değil: %r ⟷ %r'
            % (dil, satirlar, adlar))
        metin = _metin(html)
        for ad in adlar:
            assert ad in metin, '%s: %s ekranda yok' % (dil, ad)


@node_gerekli
def test_cwa4e6_turet_isareti_sayi_olarak_basilmaz_ve_bos_liste_blok_yok():
    liste = [
        {'field': 'l_star', 'reason': 'not_supplied', 'value': 1.0, 'unit': 'm'},
        {'field': 'expansion_ratio', 'reason': 'not_supplied_solver_derives',
         'value': 0, 'unit': 'dimensionless'},
        {'field': 'hole_diameter_min', 'reason': 'not_supplied', 'value': 0.3,
         'unit': 'mm'},
    ]
    en = _node({'sozluk': True, 'dil': 'en',
                'defaults_results': {'defaults_applied': liste}})['defaults_html']
    satir = re.search(r'data-defaults-applied-field="expansion_ratio".*?</div>',
                      en, re.S).group(0)
    assert '= <strong>' not in satir, (
        'türet işareti (value 0) uygulanmış bir sayı gibi basılıyor: %r' % satir)
    assert 'l_star</code> = <strong>1 m</strong>' in en, en
    tr = _node({'sozluk': True, 'dil': 'tr',
                'defaults_results': {'defaults_applied': liste}})['defaults_html']
    assert '0,3 mm' in tr, 'TR kipte ayraç virgül değil: %r' % tr
    for bos in ({}, {'defaults_applied': []}, None):
        out = _node({'sozluk': False, 'defaults_results': bos})
        assert out['defaults_html'] == '', 'boş listede blok çiziliyor'


def test_cwa4e6_liste_elle_yazilmaz():
    """Blok sunucunun listesini okur; alan adı listesi kaynağa gömülmez."""
    govde = _islev(_oku(APP_JS), 'function defaultsAppliedBlock(')
    assert 'results.defaults_applied' in govde
    for ad in ('l_star', 'hole_diameter_min', 'hole_diameter_max',
               'cooling_channels', 'target_velocity'):
        assert "'%s'" % ad not in govde, (
            'künye listesi elle yazılmış: %s' % ad)


# ---------------------------------------------------------------------------
# CW-B3 — ana zincir kartı: iki soru, iki sayı, künye
# ---------------------------------------------------------------------------
WALL_MOTOR = {
    'heat_transfer_analysis': {'wall_analysis': {'max_temperature': 3323.2958}},
    'cooling_channel_geometry': {'resolved_class': 'natural'},
}
FEA_YUKU = {'status': 'ok', 'scalars': {'peak_wall_T_K': 2724.4,
                                        'peak_time_s': 10.0}}


@node_gerekli
@pytest.mark.parametrize('dil', ['en', 'tr'])
def test_cwb3_kart_iki_soru_iki_sayi_kunye(dil):
    out = _node({'sozluk': True, 'dil': dil, 'wall_motor': WALL_MOTOR,
                 'fea_payload': FEA_YUKU})
    html = out['wall_html']
    assert 'data-wall-temperature-questions' in html
    metin = _metin(html)
    sozluk = _oku(I18N_COMMON)
    blok = sozluk.split("tr: {")[1] if dil == 'tr' else sozluk.split("tr: {")[0]

    def deger(anahtar):
        m = re.search(r"'%s':\s*'((?:[^'\\]|\\.)*)'" % re.escape(anahtar), blok)
        assert m, anahtar
        return m.group(1)
    # İki soru metni (sözlükteki şablonların sabit gövdesi) ekranda.
    denge = deger('app.wallT.eqQuestion').split('{cls}')[0].strip()
    fea = deger('app.wallT.feaQuestion').split('{t}')[0].strip()
    assert denge in metin, 'denge sorusu yok: %r' % metin
    assert fea in metin, 'FEA sorusu yok: %r' % metin
    # İki sayı: 3323 K (ana zincir) ve 2724 K (FEA), zaman 10 s.
    assert '3323 K' in metin and '2724 K' in metin, metin
    assert ('10,00' if dil == 'tr' else '10.00') in metin, metin
    # Künye: iki sayının kaynağı adıyla.
    # V3.0.5 T-ÇAPA-C1 — BEKLENTİ DEĞİŞTİ (V301/DİL-2 f36795100): ana
    # zincirin makine yolu ekranda HAM basılmaz (TR ekranda ham anahtar
    # yasağı); yol öğenin data-field / title özniteliğinde, görünen metin
    # app.wallT.srcMain etiketidir. Kaynak yine ADIYLA durur.
    assert ('data-field="heat_transfer_analysis.wall_analysis.max_temperature"'
            in html), html
    assert deger('app.wallT.srcMain') in metin, metin
    assert 'scalars.peak_wall_T_K' in metin
    # Soğutma sınıfı çevrilmiş adıyla (ham 'natural' değil).
    assert deger('app.wallT.clsNatural') in metin


@node_gerekli
def test_cwb3_fea_kosulmadiysa_ikinci_sayi_uydurulmaz():
    for yuk in (None, {'status': 'not_modelled', 'scalars': {}}):
        girdi = {'sozluk': True, 'dil': 'en', 'wall_motor': WALL_MOTOR}
        if yuk is not None:
            girdi['fea_payload'] = yuk
        metin = _metin(_node(girdi)['wall_html'])
        assert '3323 K' in metin
        assert re.findall(r'\b\d{3,4} K\b', metin) == ['3323 K'], (
            'FEA koşulmadan ikinci sıcaklık basılıyor: %r' % metin)
        assert 'not run for this result' in metin
    # Ana zincir sayısı yoksa etiketlenecek bir şey yok: blok yok.
    out = _node({'sozluk': False, 'wall_motor': {'heat_transfer_analysis': {}}})
    assert out['wall_html'] == ''


# ---------------------------------------------------------------------------
# CW-U6 — yerli alert yok; sayfa içi, kalıcı, kapatılabilir bildirim
# ---------------------------------------------------------------------------
def test_cwu6_alert_cagrisi_sifir():
    app_kod = _js_yorumsuz(_oku(APP_JS))
    sablon_kod = _sablon_betikleri()
    kalan = {'app.js': len(ALERT_RE.findall(app_kod)),
             'advanced.html': len(ALERT_RE.findall(sablon_kod))}
    assert kalan == {'app.js': 0, 'advanced.html': 0}, (
        'yerli alert() çağrısı kaldı (CW-U6, hibrit ayağı): %r' % kalan)


@node_gerekli
def test_cwu6_bildirim_sayfa_ici_kalici_kapatilabilir():
    out = _node({'sozluk': True, 'dil': 'tr', 'bildirim': True})['bildirim']
    assert out['alert'] == [], 'alert() çağrıldı: %r' % out['alert']
    assert out['sayi'] == 3, out
    assert out['rol'] == ['alert', 'status', 'alert'], out['rol']
    assert out['kapat'] == ['Kapat'] * 3, out['kapat']
    assert out['zamanlayici'] == [], (
        'bildirim kendini silmek için zamanlayıcı kuruyor (5 s kaybolmaz '
        'kuralı): %r' % out['zamanlayici'])
    assert out['odak_bildirimde'] is True, 'hata bildirimi odağı almıyor'
    assert 'Hata: ornek-hata' in out['metin'][0]
    assert 'Bilgi: ornek-bilgi' in out['metin'][1]
    assert out['kapattiktan_sonra'] == 2 and out['escape_sonra'] == 1, out


@node_gerekli
def test_cwu6_ag_kopmasi_bildirimi_veri_tipi_demez():
    """D22 P17B4-02'nin iletisi artık BİLDİRİMDE: ağ kopması 'Data type
    mismatch' diye teşhis edilmez. (D22 kanıt düzeneği ``alert`` gövdesini
    topluyordu; alert söküldüğü için o liste boş kalır — bu bekçi aynı
    iddiayı bildirim metni üstünden sınar.)"""
    imzalar = ['Failed to fetch',
               'NetworkError when attempting to fetch resource.',
               'Load failed']
    out = _node({'sozluk': False, 'ag_imzalari': imzalar})
    assert out['ag_alert'] == []
    assert [s['imza'] for s in out['ag']] == imzalar
    for s in out['ag']:
        assert 'Connection' in s['kaynak'], s
        assert s['metin'], 'bildirim metni boş: %r' % s
        assert 'Data type mismatch' not in s['metin'], s
        assert 'Network/Connection' in s['metin'], s


def _popup_betigi() -> str:
    src = _oku(SABLON)
    m = re.search(r"<scr` \+ `ipt>(.*?)</scr` \+ `ipt>", src, re.S)
    assert m, 'açılır pencere betiği bulunamadı'
    betik = m.group(1)

    def yedek(mm):
        return json.dumps(mm.group(2).replace("\\'", "'"))
    betik = re.sub(r"\$\{JSON\.stringify\(i18nText\('([^']+)',\s*'((?:[^'\\]|\\.)*)'\)\)\}",
                   yedek, betik)
    assert '${' not in betik, 'çözülmemiş şablon yeri kaldı: %r' % betik[:200]
    return betik


@node_gerekli
def test_cwu6_acilir_pencere_ana_pencere_yokken_bildirim():
    out = _node({'sozluk': False, 'popup_betik': _popup_betigi()})['popup']
    assert out['alert'] == [], 'açılır pencere alert() açıyor: %r' % out['alert']
    for ad, s in out['sonuc'].items():
        assert s['sayi'] == 1 and s['rol'] == 'alert', (ad, s)
        assert 'The main HRMA window is closed' in s['metin'], (ad, s)


# ---------------------------------------------------------------------------
# OH-D31-04 — soğutma menüsü notu uçun alanından
# ---------------------------------------------------------------------------
MENU_EN = [['none', 'None'], ['radial', 'Radial Channels'],
           ['spiral', 'Spiral Channels']]


@node_gerekli
def test_ohd3104_not_ucun_denklik_siniflarindan():
    motor = {'cooling_channel_geometry': {'equivalence_classes': {
        'natural': ['none'], 'regenerative': ['radial', 'spiral']}}}
    out = _node({'sozluk': True, 'dil': 'en', 'cooling_motor': motor,
                 'menu': MENU_EN})['cooling']
    assert out['hidden'] is False
    assert 'Radial Channels = Spiral Channels' in out['text'], out
    assert 'None' not in out['text'], 'tek üyeli sınıf nota girmiş: %r' % out
    # Sınıflar ayrışırsa (ör. F-08 Dean modeli) not kendiliğinden kalkar.
    ayri = {'cooling_channel_geometry': {'equivalence_classes': {
        'natural': ['none'], 'regen_radial': ['radial'], 'regen_spiral': ['spiral']}}}
    out = _node({'sozluk': False, 'cooling_motor': ayri, 'menu': MENU_EN})['cooling']
    assert out == {'text': '', 'hidden': True}, out
    # Alan yoksa iddia yok.
    out = _node({'sozluk': False, 'cooling_motor': {}, 'menu': MENU_EN})['cooling']
    assert out == {'text': '', 'hidden': True}, out


def test_ohd3104_liste_elle_yazilmaz_ve_not_sablonda():
    govde = _islev(_oku(APP_JS), 'function coolingEquivalenceNote(')
    for ad in ("'radial'", "'spiral'", "'regenerative'"):
        assert ad not in govde, 'denklik listesi elle yazılmış: %s' % ad
    assert 'equivalence_classes' in govde
    sablon = _oku(SABLON)
    assert re.search(r'<div id="coolingEquivalenceNote"[^>]*\bhidden\b', sablon), (
        'not öğesi şablonda yok ya da gizli doğmuyor')


# ---------------------------------------------------------------------------
# DV36-14 — sökülen kardeş sayfaya bayat atıf
# ---------------------------------------------------------------------------
def test_dv3614_sokulen_kardes_sayfaya_atif_yok():
    assert 'simple.html' not in _oku(SABLON), (
        'advanced.html sökülen simple.html sayfasını hâlâ anıyor (DV36-14)')


# ---------------------------------------------------------------------------
# OH-P-07 — regresyon grafiğinin iç düğümü dış-kap asgari yüksekliğini almaz
# ---------------------------------------------------------------------------
def test_ohp07_ic_plotly_dugumu_dis_kap_yuksekligini_devralmaz():
    css = re.sub(r'/\*.*?\*/', ' ', _oku(SABLON), flags=re.S)
    # Çakışmanın kökü yerinde (dış kap kuralı) — onarım onu SİLMEDEN çözer.
    assert re.search(r'\.plot-container\s*\{[^}]*min-height:\s*500px', css)
    m = re.search(r'#designReportRegressionChart\s*>\s*\.plot-container\s*\{([^}]*)\}',
                  css)
    assert m and re.search(r'min-height:\s*0\b', m.group(1)), (
        'regresyon grafiğinin iç .plot-container düğümü dış kabın 500 px '
        'asgari yüksekliğini devralıyor: çizim 320 px, kap 500 px (OH-P-07)')
    # Çizim yüksekliği kap kadar kalır (D34 bekçisinin çapası bozulmaz).
    assert 'height: Math.max(320, el.clientHeight || 0)' in _oku(APP_JS)


# ---------------------------------------------------------------------------
# DV-GT27 — dolum kütlesi satırlarının etiketi ham alan adı değil
# ---------------------------------------------------------------------------
@node_gerekli
@pytest.mark.parametrize('dil', ['en', 'tr'])
def test_dvgt27_etiket_ham_alan_adindan_ibaret_degil(dil):
    motor = {'fuel_sliver_fraction': 0.12, 'oxidizer_mass_residual_kg': 0.0}
    html = _node({'sozluk': True, 'dil': dil, 'dolum_motor': motor})['dolum_html']
    satirlar = re.findall(r'<tr><td>(.*?)</td>', html, re.S)
    assert len(satirlar) == 2, html
    for hucre, alan in zip(satirlar, ('fuel_sliver_fraction',
                                      'oxidizer_mass_residual_kg')):
        assert alan in hucre, 'alan imi kayboldu: %r' % hucre
        etiket = _metin(re.sub(r'<span class="hd-field-tag".*?</span>', '',
                               hucre, flags=re.S))
        assert etiket and etiket != alan and '_' not in etiket, (
            '%s: etiket ham alan adından ibaret: %r' % (dil, etiket))
        if dil == 'tr':
            assert re.search(r'[çğıöşüÇĞİÖŞÜ]', etiket), (
                'TR etiket Türkçe değil: %r' % etiket)


# ---------------------------------------------------------------------------
# CM-H2 — ihraç gövdesi injector_design bloğunu aynen taşır
# ---------------------------------------------------------------------------
@node_gerekli
def test_cmh2_ihrac_govdesi_injector_design_blogunu_aynen_tasir():
    betik = _islev(_oku(SABLON), 'async function _downloadExport(')
    enjektor = {'plate_thickness_mm': 3.0, 'n_holes': 3,
                'hole_diameter_mm': 2.1154, 'earned': True,
                'basis': 'bekci: sentetik gövde'}
    sonuc = {'motor': {'thrust': 1000.0, 'injector_design': enjektor}}
    out = _node({'sozluk': False, 'ihrac_betik': betik,
                 'ihrac_sonuc': sonuc})['ihrac']
    assert out['donus'] is False   # 499: çağıran hükmü okuyabilir
    govde = out['govde']
    assert govde['motor_data']['injector_design'] == enjektor, govde
    assert govde['motor_type'] == 'hybrid'
