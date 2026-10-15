# -*- coding: utf-8 -*-
"""ÖH Dalga-18 / kulvar `electron`, aşama 1 — kabuk + fırlatma sahası bekçileri.

Yedi kalem (parti P12A, bulucu 4 ve 5):

  P12aB4-07  "küresel doku ~9 km hücre" notu ile "NASA GIBS ~500 m" atfı
             0-400 km bandında AYNI ANDA ekranda duruyordu (ölçüldü: 4 durum).
  P12aB4-08  STEP ölçü eşleme ekranının beş alan etiketi iki sözlükte de
             TANIMSIZ; TR kipinde İngilizce kalıyordu ve bekçi göremiyordu.
  P12aB4-10  Canlı okuma bloğunun dört satırından ikisi (Apoje, yatay mesafe)
             oynatım boyunca SABİT terminal değerlerdi; TR etiketi "Menzil"
             apojede duran çözümde toplam menzil iddiası taşıyordu.
  P12aB5-03  "İndirme yavaş, tarayıcıdan indirin" uyarısı tam bir yoklama
             (0,7 sn) durup düz ilerleme metniyle eziliyordu.
  P12aB5-04  Girdi listesi 60'ta SESSİZCE kırpılıyor, başlıktaki (60) toplam
             gibi okunuyordu (/hybrid'de 16 alan beyansız düşüyordu).
  P12aB5-05  Fırlatma sahasının enlem/boylamı herkese açık GitHub kaydına
             giriyordu; rıza metni konumdan hiç söz etmiyordu.
  P12aB5-06  /launch-site'ta "Ayarlar" ve "Sürüm Notları" bağlantıları HİÇ
             çizilmiyordu — Ayarlar o sayfada hiçbir yoldan açılamıyordu.

Bekçilerin tamamı ÜRÜN DAVRANIŞINI ölçer: node ile gerçek modüller yüklenir,
asgari DOM kurulur, üretilen metin/DOM okunur. Kaynak metni sınayan tek
denetim "tek tanım" sözleşmesidir (aynı tablo iki dosyada yaşamasın).

Ham kanıt: docs/scofield/raw/OH/D18/electron/a1/
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
JS = REPO / 'hrma' / 'static' / 'js'
TPL = REPO / 'hrma' / 'templates'
NODE = shutil.which('node')

needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _oku(p):
    return p.read_text(encoding='utf-8')


def _node(kaynak, tmp_path, ad='bekci.js', argv=()):
    h = tmp_path / ad
    h.write_text(kaynak, encoding='utf-8')
    res = subprocess.run([NODE, str(h), str(JS), str(TPL)] + list(argv),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, 'node koşumu hata verdi:\n' + res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


# ===========================================================================
# P12aB4-07 — çelişen iki çözünürlük beyanı
# ===========================================================================
GLOBE_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const JSDIR = process.argv[2];

class V3 {
    constructor(x, y, z) { this.x = x || 0; this.y = y || 0; this.z = z || 0; }
    length() { return Math.hypot(this.x, this.y, this.z); }
    clone() { return new V3(this.x, this.y, this.z); }
    normalize() { const l = this.length() || 1; this.x /= l; this.y /= l; this.z /= l; return this; }
    distanceTo(o) { return Math.hypot(this.x - o.x, this.y - o.y, this.z - o.z); }
}
const sandbox = { console: { log() {}, warn() {}, error() {} }, THREE: { Vector3: V3 } };
sandbox.window = sandbox;
vm.createContext(sandbox);
const SRC = path.join(JSDIR, 'launch_site_globe.js');
vm.runInContext(fs.readFileSync(SRC, 'utf8'), sandbox, { filename: 'launch_site_globe.js' });
const G = sandbox.LaunchSiteGlobe;
const src = fs.readFileSync(SRC, 'utf8');
const num = re => parseFloat(src.match(re)[1]);
const R_EARTH_M = num(/R_EARTH_M = ([\d.]+)/);
const GLOBE_R = num(/GLOBE_R = ([\d.]+)/);
const M_PER_UNIT = R_EARTH_M / GLOBE_R;

function kure(camAltM, cizilenKaro, basarisiz) {
    const r = GLOBE_R + camAltM / M_PER_UNIT;
    const tiles = new Map();
    for (let i = 0; i < cizilenKaro; i++) tiles.set('c' + i, { mesh: {} });
    for (let i = 0; i < (basarisiz || 0); i++) tiles.set('b' + i, { failed: true });
    return Object.assign(Object.create(G.prototype), {
        camera: { position: new V3(0, r, 0), fov: 38 },
        controls: { target: new V3(0, GLOBE_R, 0) },
        container: { clientHeight: 800 },
        _tiles: tiles, _tileAnyFail: !!basarisiz,
    });
}

const BANT = [17700, 134200, 250000, 399000, 458000, 900000, 1400000, 2000000];
const durumlar = [];
for (const alt of BANT) {
    for (const karo of [0, 12]) {
        const self = kure(alt, karo, 0);
        const s = G.prototype.getScaleInfo.call(self);
        const t = G.prototype.getTileInfo.call(self);
        durumlar.push({
            alt: Math.round(s.camAltitudeM), karo: karo,
            atif: t.active, not: s.textureCoarse,
            ikisi: !!(s.textureCoarse && t.active),
        });
    }
}
/* Karolar başarısız olup DÜŞTÜĞÜNDE not geri gelmeli (fail-closed dürüstlük:
   ekranda gerçekten taban dokusu var). */
const cevrimdisi = kure(134200, 0, 6);
const cd = G.prototype.getScaleInfo.call(cevrimdisi);
const cdT = G.prototype.getTileInfo.call(cevrimdisi);

/* --- canlı okuma bloğu (P12aB4-10) --- */
const n = 40;
const series = { time: [], north: [], east: [], altitude: [], speed: [] };
for (let i = 0; i < n; i++) {
    series.time.push(i * 0.5);
    series.north.push(i * 300);
    series.east.push(i * 120);
    series.altitude.push(Math.max(0, 12345 * Math.sin(Math.PI * i / (n - 1))));
    series.speed.push(300 - i * 4);
}
let kayitlar = [];
const kure10 = Object.assign(Object.create(G.prototype), {
    _onTime: function (s) { kayitlar.push(s); },
    clearFlightPath: function () {}, _buildFlightGeometry: function () {},
    viewSite: function () {},
    _exaggerate: 0, _playT: 0, _curIdx: 0, _playing: false,
});
G.prototype.setFlightPath.call(kure10, series, 28.6084, -80.6043, 0);
const f = kure10._flight;
kayitlar = [];
for (let i = 0; i < n; i++) {
    kure10._curIdx = i; kure10._playT = f.t[i];
    G.prototype._emitTime.call(kure10);
}
const alanlar = {};
for (const k of ['alt', 'speed', 'downrange', 'apogee', 'range']) {
    const kume = new Set(kayitlar.map(r => r[k]));
    alanlar[k] = { farkli: kume.size, ilk: kayitlar[0][k],
                   son: kayitlar[kayitlar.length - 1][k] };
}
console.log(JSON.stringify({
    durumlar: durumlar,
    ayni_anda_iki_cozunurluk: durumlar.filter(d => d.ikisi).length,
    cevrimdisi: { not: cd.textureCoarse, atif: cdT.active,
                  basarisizSayisi: cdT.failedCount },
    alanlar: alanlar,
    downrangeSonEsitRange: Math.abs(alanlar.downrange.son - alanlar.range.son) < 1e-9,
}));
"""


@needs_node
def test_p12ab4_07_doku_notu_ile_karo_atfi_ayni_anda_basilmaz(tmp_path):
    """ÖNCE (ölçüldü): 0-400 km bandında dört kamera yüksekliğinde de
    "~9 km hücre" notu ile "NASA GIBS ~500 m" atfı yan yana duruyordu —
    18 kat çelişen iki çözünürlük beyanı.
    """
    d = _node(GLOBE_HARNESS, tmp_path)
    assert d['ayni_anda_iki_cozunurluk'] == 0, (
        'Çelişen iki çözünürlük beyanı hâlâ aynı anda basılıyor: %s'
        % [x for x in d['durumlar'] if x['ikisi']])
    # Bekçi boş kapsamda çalışmasın: her iki gösterge de gerçekten çıkıyor.
    assert any(x['not'] for x in d['durumlar']), 'doku notu hiç çıkmıyor'
    assert any(x['atif'] for x in d['durumlar']), 'karo atfı hiç çıkmıyor'


@needs_node
def test_p12ab4_07_karo_dustugunde_doku_notu_geri_gelir(tmp_path):
    """Fail-closed dürüstlük: karolar çevrimdışı/başarısızsa ekranda
    GERÇEKTEN taban dokusu vardır — not o zaman basılmalıdır."""
    d = _node(GLOBE_HARNESS, tmp_path)
    assert d['cevrimdisi']['atif'] is False
    assert d['cevrimdisi']['not'] is True, (
        'Karolar düştüğünde "doku kaba" notu susturuluyor — kullanıcı ne '
        'gördüğünü bilemez')
    assert d['cevrimdisi']['basarisizSayisi'] == 6


# ===========================================================================
# P12aB4-10 — canlı okuma bloğunda sabit terminal değer
# ===========================================================================
@needs_node
def test_p12ab4_10_yatay_mesafe_indise_bagli_yayimlanir(tmp_path):
    """ÖNCE (ölçüldü): `_emitTime` yalnız SABİT `range` yolluyordu; t = 0'da
    "Altitude 0 m" ile "Menzil 8,2 km" yan yana duruyordu."""
    d = _node(GLOBE_HARNESS, tmp_path)
    a = d['alanlar']
    assert a['downrange']['farkli'] > 1, (
        'downrange yayını hâlâ sabit — canlı okuma değil')
    assert a['downrange']['ilk'] == 0, (
        'kalkış anında yatay mesafe 0 olmalı, bulunan: %r'
        % a['downrange']['ilk'])
    # TEK TANIM: terminal değer, canlı dizinin son elemanıdır.
    assert d['downrangeSonEsitRange'], (
        'Terminal `range` ile canlı dizinin son değeri ayrışmış — iki ayrı '
        'tanım doğmuş')


def test_p12ab4_10_canli_ve_ozet_bloklari_ayrildi():
    """Sabit (tüm çözüme ait) satır, canlı okuma bloğunda basılmaz.

    Ölçüt şablonun kendi yapısı: her okuma satırının hangi başlık grubunda
    durduğu ve `updatePlayUI`de hangi yayın alanından beslendiği.
    """
    html = _oku(TPL / 'launch_site.html')
    beklenen = {
        'ls-alt': ('site.liveHead', 'alt'),
        'ls-speed': ('site.liveHead', 'speed'),
        'ls-downrange': ('site.liveHead', 'downrange'),
        'ls-apogee': ('site.summaryHead', 'apogee'),
        'ls-range': ('site.summaryHead', 'range'),
    }
    for eid, (grup, alan) in beklenen.items():
        i = html.find('id="%s"' % eid)
        assert i > 0, '%s satırı şablonda yok' % eid
        basliklar = re.findall(r'<h2[^>]*data-i18n="([^"]+)"', html[:i])
        assert basliklar and basliklar[-1] == grup, (
            '%s satırı %r başlığı altında değil (bulunan: %r)'
            % (eid, grup, basliklar[-1] if basliklar else None))
        assert re.search(r"el\('%s'\)\.textContent\s*=[^;]*\bs\.%s\b"
                         % (eid, alan), html), (
            '%s satırı `s.%s` alanından beslenmiyor' % (eid, alan))


def test_p12ab4_10_tr_etiketi_toplam_menzil_iddiasi_tasimaz():
    """"Menzil" (toplam menzil) iddiası kaldırıldı: değer, çözümün SON
    noktasındaki yatay mesafedir ve 6-DOF çözücü varsayılan olarak apojede
    durur."""
    src = _oku(JS / 'i18n_launch_site.js')
    tr = re.search(r"'site\.rangeReadout':\s*'([^']*)'[\s\S]*$", src)
    hepsi = re.findall(r"'site\.rangeReadout':\s*'([^']*)'", src)
    assert len(hepsi) == 2, hepsi
    en_deger, tr_deger = hepsi
    coz = lambda s: re.sub(r'\\u([0-9a-fA-F]{4})',
                           lambda m: chr(int(m.group(1), 16)), s)
    assert coz(tr_deger).strip().casefold() != 'menzil', (
        'TR etiketi hâlâ çıplak "Menzil" — toplam menzil iddiası')
    assert 'çözüm sonu' in coz(tr_deger).casefold(), coz(tr_deger)
    assert 'end of solution' in en_deger.casefold(), en_deger
    assert tr is not None


# ===========================================================================
# P12aB4-08 — STEP eşleme etiketleri
# ===========================================================================
I18N_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const JSDIR = process.argv[2];
const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    localStorage: { getItem() { return null; }, setItem() {} },
    document: { documentElement: { setAttribute() {}, lang: 'en' },
                querySelectorAll() { return []; }, addEventListener() {},
                readyState: 'complete' },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(JSDIR, 'i18n.js'), 'utf8'), sandbox,
                { filename: 'i18n.js' });
for (const ad of fs.readdirSync(JSDIR).filter(f => /^i18n_.*\.js$/.test(f)).sort()) {
    vm.runInContext(fs.readFileSync(path.join(JSDIR, ad), 'utf8'), sandbox,
                    { filename: ad });
}
const I = sandbox.I18N;
const modul = fs.readFileSync(path.join(JSDIR, 'step_import_ui.js'), 'utf8');
const kullanilan = Array.from(new Set(
    (modul.match(/'stepimp\.[A-Za-z0-9_]+'/g) || []).map(s => s.slice(1, -1)))).sort();
const eksik = [], ingilizceKalan = [];
for (const k of kullanilan) {
    if (!I.has(k)) { eksik.push(k); continue; }
    I.setLang('en'); const en = I.t(k);
    I.setLang('tr'); const tr = I.t(k);
    if (tr === en) ingilizceKalan.push(k);
}
I.setLang('en');
console.log(JSON.stringify({
    kullanilan: kullanilan.length, eksik: eksik,
    trKipindeIngilizce: ingilizceKalan,
}));
"""


@needs_node
def test_p12ab4_08_step_esleme_etiketleri_iki_dilde_de_tanimli(tmp_path):
    """ÖNCE (ölçüldü): 33 anahtarın 5'i (fieldThroat/fieldExit/fieldChamberD/
    fieldChamberL/fieldWall) hem EN hem TR sözlüğünde yoktu; TR kipinde
    İngilizce yedek metin basılıyordu."""
    d = _node(I18N_HARNESS, tmp_path)
    assert d['kullanilan'] >= 30, d
    assert d['eksik'] == [], (
        'STEP eşleme ekranında sözlüksüz anahtar: %s' % d['eksik'])
    assert d['trKipindeIngilizce'] == [], (
        'TR kipinde İngilizce kalan anahtar: %s' % d['trKipindeIngilizce'])


def test_p12ab4_08_bekci_ciplak_dizi_anahtarlarini_goruyor():
    """Mevcut bekçi (tests/test_i18n_common.py) bu aileyi göremiyordu:
    anahtarlar `T(` çağrısı olarak değil, SUGGESTION_KEYS dizisinde çıplak
    dize olarak yaşıyor ve FIELD_RE'nin ön ek listesinde 'stepimp' yoktu."""
    kaynak = _oku(REPO / 'tests' / 'test_i18n_common.py')
    blok = re.search(r'FIELD_RE = re\.compile\((.*?)\)\n', kaynak, re.S)
    assert blok, 'test_i18n_common.py içinde FIELD_RE bulunamadı'
    assert 'stepimp' in blok.group(1), (
        "FIELD_RE ön ek listesinde 'stepimp' yok — çıplak dizi anahtarları "
        'yine görünmez olur')
    # Bekçi gerçekten yük taşısın: anahtarlar hâlâ çıplak dize biçiminde.
    modul = _oku(JS / 'step_import_ui.js')
    assert "'stepimp.fieldThroat'" in modul
    assert "T('stepimp.fieldThroat'" not in modul, (
        'Anahtar artık çağrı biçiminde — bu bekçinin gerekçesi güncellenmeli')


# ===========================================================================
# P12aB5-03 — takılma uyarısının ekranda kalması
# ===========================================================================
STALL_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path');
const JSDIR = process.argv[2];
const izleme = [];
function mkNode(tag) {
    const n = { tagName: tag, style: {}, children: [], _text: '', _html: '',
        id: '', disabled: false, onclick: null, watch: false,
        appendChild(c) { this.children.push(c); return c; },
        remove() {}, addEventListener() {}, setAttribute() {} };
    const set = (v) => { n._text = String(v); n._html = String(v);
                         if (n.watch) izleme.push(String(v)); };
    Object.defineProperty(n, 'textContent', { get() { return n._text; }, set });
    Object.defineProperty(n, 'innerHTML', { get() { return n._html; }, set });
    return n;
}
const created = [];
global.window = global;
global.document = {
    readyState: 'complete', body: mkNode('body'), documentElement: mkNode('html'),
    createElement(t) { const n = mkNode(t); created.push(n); return n; },
    createTextNode(t) { const n = mkNode('#text'); n._text = String(t); return n; },
    getElementById() { return null; }, querySelector() { return null; },
    querySelectorAll() { return []; }, addEventListener() {},
};
global.localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
let statusCalls = 0, pct = 12;
const timers = []; const realST = global.setTimeout;
global.setTimeout = function (fn) { timers.push(fn); return timers.length; };
global.fetch = function (u) {
    if (u === '/api/update/check')
        return Promise.resolve({ json: () => Promise.resolve(
            { available: true, latest: 'v9.9.9', current: '2.6.27' }) });
    if (u === '/api/update/download')
        return Promise.resolve({ json: () => Promise.resolve({ started: true }) });
    if (u === '/api/update/status') {
        statusCalls += 1;
        /* 120. yoklamadan sonra indirme YENİDEN İLERLER: uyarı kalkmalı. */
        if (statusCalls > 120) pct += 1;
        return Promise.resolve({ json: () => Promise.resolve(
            { state: 'downloading', pct: pct }) });
    }
    return Promise.resolve({ json: () => Promise.resolve({}) });
};
(0, eval)(fs.readFileSync(path.join(JSDIR, 'update_check.js'), 'utf8'));
async function pump(n) {
    for (let i = 0; i < n; i++) {
        const t = timers.shift(); if (!t) break; t();
        await new Promise(r => realST(r, 0)); await new Promise(r => realST(r, 0));
    }
}
(async () => {
    window.hrmaCheckForUpdates(true);
    await new Promise(r => realST(r, 40));
    created.filter(n => n.tagName === 'div').forEach(n => { n.watch = true; });
    created.filter(n => n.tagName === 'button')[0].onclick();
    await new Promise(r => realST(r, 20));
    await pump(180);
    const YAVAS = /looks slow/;
    const adim = izleme.map((v, i) => [v, i]).filter(([v]) => YAVAS.test(v))
                       .map(([, i]) => i);
    console.log(JSON.stringify({
        yoklama: statusCalls,
        uyariAdimSayisi: adim.length,
        ilkAdim: adim.length ? adim[0] : null,
        sonAdim: adim.length ? adim[adim.length - 1] : null,
        sonMetinUyariMi: YAVAS.test(String(izleme[izleme.length - 1] || '')),
    }));
})();
"""


@needs_node
def test_p12ab5_03_takilma_uyarisi_takilma_surdukce_ekranda_kalir(tmp_path):
    """ÖNCE (ölçüldü): 200 yoklamalık takılmada uyarı YALNIZ 1 adım (0,7 sn)
    ekranda kaldı; katı eşitlik (`=== STALL_LIMIT`) yüzünden bir sonraki
    yoklama onu düz "Downloading… %12" ile eziyordu."""
    d = _node(STALL_HARNESS, tmp_path)
    assert d['ilkAdim'] is not None, 'uyarı hiç çıkmadı — harness bozuk'
    assert d['uyariAdimSayisi'] > 50, (
        'Takılma sürerken uyarı ekranda kalmıyor (yalnız %d adım)'
        % d['uyariAdimSayisi'])


@needs_node
def test_p12ab5_03_ilerleme_yeniden_baslayinca_uyari_kalkar(tmp_path):
    """Uyarı YAPIŞIK olmamalı: pct yeniden artmaya başlayınca düz ilerleme
    metnine dönülür (aksi hâlde bu sefer ters yönde yanlış beyan olurdu)."""
    d = _node(STALL_HARNESS, tmp_path)
    assert d['sonMetinUyariMi'] is False, (
        'İndirme yeniden ilerlerken "yavaş" uyarısı ekranda kaldı')


# ===========================================================================
# P12aB5-04 + P12aB5-05 — hata kaydı: kırpma beyanı ve coğrafi konum
# ===========================================================================
BUG_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path');
const JSDIR = process.argv[2];
global.window = global;
Object.defineProperty(global, 'navigator',
    { configurable: true, writable: true, value: { userAgent: 'x' } });
global.location = { pathname: '/launch-site' };
let AKTIF = [];
global.document = {
    querySelectorAll(s) { return s === 'input' ? AKTIF : []; },
    querySelector() { return null; },
};
(0, eval)(fs.readFileSync(path.join(JSDIR, 'bug_report.js'), 'utf8'));
const BR = global.HRMABugReport;

/* (a) 75 sayısal alan + 2 koordinat alanı */
AKTIF = [];
for (let i = 0; i < 75; i++)
    AKTIF.push({ id: 'alan_' + i, type: 'number', value: String(i + 1) });
AKTIF.push({ id: 'ls-lat', type: 'number', value: '28.6084' });
AKTIF.push({ id: 'ls-lon', type: 'number', value: '-80.6043' });
const ozet = BR.collectInputSummary();
const govde = BR.buildBody({ what: 'x' }, { diagnostics: true });
const baslik = (govde.match(/#### Numeric inputs \(([^)]*)\)/) || [])[1];

/* (b) yanlış pozitif denetimi: coğrafi görünen ama olmayan adlar */
AKTIF = [
    { id: 'dilation', type: 'number', value: '1' },
    { id: 'latch_count', type: 'number', value: '2' },
    { id: 'relative_area', type: 'number', value: '3' },
    { id: 'along_axis', type: 'number', value: '4' },
    { id: 'chamberLatitude', type: 'number', value: '5' },
];
const ozet2 = BR.collectInputSummary();

console.log(JSON.stringify({
    kaydaGiren: ozet.fields.length,
    uygunToplam: ozet.eligible_total,
    dusen: ozet.dropped_count,
    geriTutulan: ozet.withheld_geo,
    baslik: baslik,
    kayittaKoordinatVar: ozet.fields.some(f => /^ls-(lat|lon)$/.test(f.id)),
    govdedeKoordinatDegeri: /28\.6084|-80\.6043/.test(govde),
    kirpmaBeyani: govde.indexOf('warn.bugreport.inputs_truncated') >= 0,
    konumBeyani: govde.indexOf('warn.bugreport.geo_withheld') >= 0,
    beyandaAlanAdi: govde.indexOf('ls-lat') >= 0 && govde.indexOf('ls-lon') >= 0,
    yanlisPozitif: ozet2.withheld_geo,
    yanlisPozitifKaydaGiren: ozet2.fields.map(f => f.id),
}));
"""


@needs_node
def test_p12ab5_04_girdi_kirpmasi_beyan_ediliyor(tmp_path):
    """ÖNCE (ölçüldü): /hybrid 76 alanın 60'ını yazıyor, 16'sı beyansız
    düşüyordu; gövde başlığı `Numeric inputs (60)` toplam gibi okunuyordu."""
    d = _node(BUG_HARNESS, tmp_path)
    assert d['kaydaGiren'] == 60, d
    assert d['uygunToplam'] == 75, d
    assert d['dusen'] == 15, d
    assert d['baslik'] == '60 / 75', (
        'Gövde başlığı hâlâ tavanı toplam gibi gösteriyor: %r' % d['baslik'])
    assert d['kirpmaBeyani'], (
        'Kırpma gövdede beyan edilmiyor — `warn.bugreport.inputs_truncated` yok')


@needs_node
def test_p12ab5_05_cografi_koordinat_kayda_girmez(tmp_path):
    """ÖNCE (ölçüldü): /launch-site'ta `ls-lat = 28.6084`, `ls-lon = -80.6043`
    tanılama açıkken herkese açık GitHub kaydına giriyordu."""
    d = _node(BUG_HARNESS, tmp_path)
    assert d['kayittaKoordinatVar'] is False, 'koordinat alanı hâlâ kayda giriyor'
    assert d['govdedeKoordinatDegeri'] is False, 'koordinat DEĞERİ gövdede'
    assert sorted(d['geriTutulan']) == ['ls-lat', 'ls-lon'], d['geriTutulan']
    assert d['konumBeyani'], (
        'Geri tutma sessiz — `warn.bugreport.geo_withheld` beyanı yok')
    assert d['beyandaAlanAdi'], 'Beyan hangi alanların tutulduğunu söylemiyor'


@needs_node
def test_p12ab5_05_cografi_suzgec_yanlis_pozitif_uretmez(tmp_path):
    """Süzgeç BELİRTEÇ eşleşmesidir: `dilation`, `latch_count`,
    `relative_area`, `along_axis` yenmez; `chamberLatitude` yakalanır."""
    d = _node(BUG_HARNESS, tmp_path)
    assert d['yanlisPozitif'] == ['chamberLatitude'], d['yanlisPozitif']
    assert d['yanlisPozitifKaydaGiren'] == [
        'dilation', 'latch_count', 'relative_area', 'along_axis'], d


def test_p12ab5_05_riza_metni_konumu_da_sayiyor():
    """Beyan (künye) kusuru gidermez ama GERÇEĞİ söylemek zorundadır:
    kaldırılanlar listesi coğrafi koordinatı da saymalı."""
    sp = _oku(JS / 'settings_panel.js')
    m = re.search(r"descLine\('shell\.bug\.diagnosticsDesc',([\s\S]{0,700}?)\)\)",
                  sp)
    assert m, 'settings_panel.js rıza metni bulunamadı'
    metin = re.sub(r"\s*\+\s*", '', m.group(1)).replace("'", '')
    assert re.search(r'coordinate', metin, re.I), (
        'Rıza metni coğrafi koordinattan söz etmiyor: %r' % metin)
    sozluk = _oku(JS / 'i18n_shell.js')
    for desen in (r"'shell\.bug\.diagnosticsDesc':\s*'[^']*coordinates",
                  r"'shell\.bug\.diagnosticsDesc':\s*'[^']*koordinat"):
        assert re.search(desen, sozluk), (
            'Sözlükte rıza metni konumu saymıyor: %s' % desen)


# ===========================================================================
# P12aB5-06 — kabuk bağlantıları her kabukta çizilir
# ===========================================================================
NAV_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const JSDIR = process.argv[2];
const SENARYO = process.argv[4];   // nav | aux | topbar | yok
const BETIKLER = ['release_notes.js', 'user_guide.js', 'bug_report.js',
                  'settings_panel.js'];

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.nodeType = 1; this.childNodes = []; this.className = '';
    this.id = ''; this.href = ''; this.style = {}; this._attrs = {};
    this._listeners = {};
}
Object.defineProperty(El.prototype, 'textContent', {
    get: function () { return this._t || ''; },
    set: function (v) { this._t = String(v); }
});
El.prototype.appendChild = function (c) { this.childNodes.push(c); return c; };
El.prototype.insertBefore = function (c, ref) {
    const i = this.childNodes.indexOf(ref);
    if (i < 0) this.childNodes.push(c); else this.childNodes.splice(i, 0, c);
    return c;
};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
};
El.prototype.querySelector = function (sel) {
    for (const c of this.childNodes) {
        if (c.nodeType !== 1) continue;
        if (sel === '[data-shell-aux]' && c.getAttribute('data-shell-aux')) return c;
        if (sel.charAt(0) === '.' && c.className === sel.slice(1)) return c;
    }
    return null;
};

const host = new El('div');
const HOST_SEL = { nav: '.nav-links', aux: '.aux-links', topbar: '#ls-topbar' }[SENARYO];
if (SENARYO === 'topbar') {
    const geri = new El('a'); geri.className = 'ls-link';
    geri.textContent = 'Back to app'; host.appendChild(geri);
}
const documentStub = {
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    getElementById: function () { return null; },
    querySelector: function (sel) { return (HOST_SEL && sel === HOST_SEL) ? host : null; },
    querySelectorAll: function () { return []; },
    addEventListener: function () {},
};
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    JSON: JSON, Math: Math, String: String, Number: Number, Array: Array,
    Object: Object, Date: Date, RegExp: RegExp, isFinite: isFinite,
    encodeURIComponent: encodeURIComponent, Promise: Promise, Error: Error,
    fetch: function () { return Promise.resolve({ json: function () { return Promise.resolve({}); } }); },
    document: documentStub,
    localStorage: { getItem: function () { return null; }, setItem: function () {} },
    navigator: { userAgent: 'x' }, location: { pathname: '/x' },
};
sandbox.window = sandbox; sandbox.globalThis = sandbox; sandbox.self = sandbox;
vm.createContext(sandbox);
for (const b of BETIKLER) {
    vm.runInContext(fs.readFileSync(path.join(JSDIR, b), 'utf8'), sandbox,
                    { filename: b });
}
const kids = host.childNodes.filter(function (c) { return c.nodeType === 1; });
console.log(JSON.stringify({
    sira: kids.map(function (c) { return c.id || ('.' + c.className); }),
    settings: kids.some(function (c) { return c.id === 'settingsLink'; }),
    release: kids.some(function (c) { return c.id === 'releaseNotesLink'; }),
    guide: kids.some(function (c) { return c.id === 'userGuideLink'; }),
    apiSettings: typeof sandbox.window.hrmaShowSettings === 'function',
    apiRelease: typeof sandbox.window.hrmaShowReleaseNotes === 'function',
    tablo: !!(sandbox.window.HRMA_SHELL_NAV
              && typeof sandbox.window.HRMA_SHELL_NAV.inject === 'function'),
}));
"""


@needs_node
@pytest.mark.parametrize('senaryo', ['nav', 'aux', 'topbar'])
def test_p12ab5_06_kabuk_baglantilari_uc_kabukta_da_cizilir(tmp_path, senaryo):
    """ÖNCE (ölçüldü): `settings_panel.js` ve `release_notes.js` yalnız
    `.nav-links` çapasını tanıyordu; /launch-site (#ls-topbar) ve index
    (.aux-links) kabuklarında `injectNavLink()` null dönüyor, `mountLink()`
    sessizce vazgeçiyordu. Ayarlar penceresi /launch-site'ta hiçbir yoldan
    açılamıyordu."""
    d = _node(NAV_HARNESS, tmp_path, argv=[senaryo])
    assert d['tablo'], 'window.HRMA_SHELL_NAV yayımlanmamış'
    assert d['settings'], '%s kabuğunda Ayarlar bağlantısı çizilmedi' % senaryo
    assert d['release'], '%s kabuğunda Sürüm Notları bağlantısı çizilmedi' % senaryo
    assert d['guide'], '%s kabuğunda Kılavuz bağlantısı çizilmedi' % senaryo


@needs_node
def test_p12ab5_06_launch_site_seridinde_geri_baglantisi_en_sagda(tmp_path):
    """Yerleşim sözleşmesi: "Uygulamaya dön" en sonda kalır."""
    d = _node(NAV_HARNESS, tmp_path, argv=['topbar'])
    assert d['sira'][-1] == '.ls-link', d['sira']
    for eid in ('settingsLink', 'releaseNotesLink', 'userGuideLink'):
        assert eid in d['sira'][:-1], d['sira']


@needs_node
def test_p12ab5_06_capasiz_kabukta_sessizce_vazgecilir(tmp_path):
    """Bilinen şeritlerden hiçbiri yoksa hata fırlatılmaz; pencere menüsünün
    kullandığı window.hrma* API'leri yine tanımlıdır."""
    d = _node(NAV_HARNESS, tmp_path, argv=['yok'])
    assert d['settings'] is False and d['release'] is False
    assert d['apiSettings'] is True and d['apiRelease'] is True


def test_p12ab5_06_kabuk_betikleri_sablonlarda_dogru_sirada():
    """Paylaşımlı tablo release_notes.js'te tanımlı; onu tüketen betikler
    HER şablonda ondan SONRA yüklenmeli."""
    tuketici = ('user_guide.js', 'settings_panel.js')
    sayilan = 0
    for yol in sorted(TPL.glob('*.html')):
        h = _oku(yol)
        if '/static/js/release_notes.js' not in h:
            for t in tuketici:
                assert '/static/js/%s' % t not in h, (
                    '%s: %s yüklü ama release_notes.js yok — paylaşımlı '
                    'tablo hiç doğmaz' % (yol.name, t))
            continue
        sayilan += 1
        i = h.index('/static/js/release_notes.js')
        for t in tuketici:
            j = h.find('/static/js/%s' % t)
            if j < 0:
                continue
            assert i < j, (
                '%s: %s, release_notes.js\'ten ÖNCE yükleniyor — tablo '
                'hazır olmaz' % (yol.name, t))
    assert sayilan >= 6, 'kabuk şablonu sayısı beklenenden az: %d' % sayilan
