# -*- coding: utf-8 -*-
"""V307 / FS-HARİTA-KÜRE (16 Kas 2026) — Fırlatma Sahası küresi: yakın zoomda
üst üste binen karolar (R7) ve indirilen harita paketinin küreye, yer adlarına
ve "Harita paketleri" paneline bağlanması (FS-HARİTA-VERİ faz 2, Parça K).

Kanıt ve tarayıcı ölçümleri: docs/scofield/raw/OH/V307/fs-harita-kure/ (RAPOR,
olcum/once_r7 -> sonra_r7: sentetik Landsat z9 ebeveyn / z11 çocuk, Sinop 20 km,
ebeveyn pikseli 3.619 -> 0). Bu dosyanın bekçileri birim düzeyidir: gerçek
three r128, gerçek küre/vektör/etiket/panel modülü node'da.

R7  Karo köşeleri karo merkezine göre (float32 nicemleme ~0,5 m -> mm altı);
    zemin karoları inceden kabaya + stencil 'en ince kazanır'; paket bindirmesi
    kendi bitiyle aynı kural.
Z15 Paket bindirmesi yalnız KURULU paketin kutusuyla kesişen karoda ve
    sunucu katmanı arayüze sunuluyorsa istenir; zemin tavanı değişmez.
NE  Paket bindirmesinin çizildiği pikselde NE kıyı/göl/akarsu çizgisi basılmaz.
AD  Paket yer adları: dil tr/en, gerçek Mercator düzeyi (en çok 15), rampa türü,
    NE/GeoNames ile aynı ad bir kez.
PNL Onaysız indirme isteği YOK; ilerleme yalnız sunucu baytı; iptal {} gövdeli.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
GLOBE = JS / 'launch_site_globe.js'
ETIKET = JS / 'launch_site_labels.js'
VEKTOR = JS / 'launch_site_vectors.js'
PANEL = JS / 'launch_site_map_packs.js'
I18N = JS / 'i18n_launch_site.js'
THREE_JS = KOK / 'hrma' / 'static' / 'vendor' / 'three-0.128.0.min.js'
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
PAKET_LISTESI = KOK / 'hrma' / 'static' / 'map' / 'harita_paketleri.json'
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

from hrma.analysis import tile_cache as tc  # noqa: E402

#: Sinop saha paketinin kutusu (harita_paketleri.json'dan; tek kaynak).
_PAKETLER = json.loads(PAKET_LISTESI.read_text(encoding='utf-8'))['packs']
SINOP_KUTU = next(p['bbox'] for p in _PAKETLER if p['id'] == 'sinop_tr')
SINOP = (42.0264, 35.1551)          # şehir merkezi (ölçüm pozuyla aynı)
ISTANBUL = (41.0082, 28.9784)       # paket kapsamı DIŞI


def _durum(ui_offered=True):
    """Sunucunun /api/tile/cache/status gövdesi; paket katmanı birleşmedeki hâliyle."""
    katman = tc.list_layers()
    paket = dict(katman['packs'][tc.PACK_LAYER_KEY])
    paket['ui_offered'] = ui_offered
    katman['packs'] = {tc.PACK_LAYER_KEY: paket}
    return {'tile_matrix': tc.matrix_geometry(), 'layers': katman, 'network_opt_in': None}


def _node(tmp_path, kod, *args, env=None):
    js = tmp_path / 'duzenek.js'
    js.write_text(kod, encoding='utf-8')
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run([NODE, str(js)] + [str(a) for a in args], capture_output=True,
                       text=True, timeout=120, env=e)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


# ===========================================================================
# KÜRE
# ===========================================================================
KURE_DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [THREE_JS, VEKTOR_JS, GLOBE_JS] = process.argv.slice(2);
const DURUM = JSON.parse(process.env.DURUM), KUTU = JSON.parse(process.env.KUTU);
const ctx = { console, Math, JSON, Promise, setTimeout, performance: { now: () => 0 },
              fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(DURUM) }) };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(THREE_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(VEKTOR_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(GLOBE_JS, 'utf8'), ctx);
const THREE = ctx.THREE, G = ctx.LaunchSiteGlobe, P = G.prototype;
let imza = 'sinop_tr:aa';
ctx.LaunchSiteMapPacks = { kuruluKutular: () => (process.env.DEPO === '0' ? [] : [{ id: 'sinop_tr', bbox: KUTU, sha256: 'aa' }]),
                           imza: () => imza };
if (process.env.DEPO === 'yok') delete ctx.LaunchSiteMapPacks;
const urls = [];
THREE.TextureLoader.prototype.load = function (url) { urls.push(url); };

function kure() {
    const k = Object.assign(Object.create(P), { _tiles: new Map(), _tileNextT: -1, _frameListeners: [],
        camera: new THREE.PerspectiveCamera(38, 1440 / 900, 0.01, 1e5),
        controls: { target: new THREE.Vector3() }, container: { clientWidth: 1440, clientHeight: 900 } });
    k._paketKur(new THREE.Scene());
    return k;
}
function koy(k, lat, lon, hKm) {
    const n = G.latLonToVec3(lat, lon, 1).normalize();
    k.controls.target.copy(n.clone().multiplyScalar(100));
    k.camera.position.copy(n.clone().multiplyScalar(100 + hKm * 1000 / 63710));
    k.camera.lookAt(k.controls.target);
    k.camera.updateMatrixWorld();
}
function istekler(k) {
    const out = [];
    k._buildTilePatch = function (layer, z, x, y) { out.push([layer, z, x, y]); };
    k._tileNextT = -1;
    k._updateTilePatch();
    return out;
}
function dunyaHatasi(m) {
    // Köşenin dünya konumu (yerel + nesne konumu, float64) küre yarıçapından ne kadar sapıyor.
    const a = m.geometry.getAttribute('position').array; let e = 0;
    for (let i = 0; i < a.length; i += 3) {
        const x = a[i] + m.position.x, y = a[i + 1] + m.position.y, z = a[i + 2] + m.position.z;
        e = Math.max(e, Math.abs(Math.sqrt(x * x + y * y + z * z) - 100));
    }
    let yerelEnBuyuk = 0;
    for (let i = 0; i < a.length; i++) yerelEnBuyuk = Math.max(yerelEnBuyuk, Math.abs(a[i]));
    return { radyusHatasi: e, yerelEnBuyuk };
}
function malzeme(m) {
    const t = m.material;
    return { stencilWrite: t.stencilWrite, ref: t.stencilRef, funcMask: t.stencilFuncMask,
             writeMask: t.stencilWriteMask, func: t.stencilFunc === THREE.NotEqualStencilFunc ? 'NotEqual' : t.stencilFunc,
             zpass: t.stencilZPass === THREE.ReplaceStencilOp ? 'Replace' : t.stencilZPass,
             transparent: t.transparent, depthWrite: t.depthWrite, renderOrder: m.renderOrder,
             tip: t.type, konumR: m.position.length() };
}
(async () => {
    const out = {};
    const k0 = kure(); koy(k0, 42.0264, 35.1551, 20);
    istekler(k0);                                   // durum fetch'i (geometri, tavanlar)
    await new Promise(r => setTimeout(r, 0));
    // --- Senaryolar: hangi karolar istenir --------------------------------
    const sen = [['sinop_2km', 42.0264, 35.1551, 2], ['sinop_20km', 42.0264, 35.1551, 20],
                 ['sinop_400km', 42.0264, 35.1551, 400], ['istanbul_2km', 41.0082, 28.9784, 2]];
    out.senaryo = {};
    for (const [ad, la, lo, h] of sen) {
        const k = kure(); koy(k, la, lo, h);
        const r = istekler(k);
        out.senaryo[ad] = { istek: r, paketEtkin: k._paketEtkin, paketZ: k._paketZ,
                            grupGorunur: k._paketGroup.visible };
    }
    if (process.env.DEPO !== '1') { process.stdout.write(JSON.stringify(out)); return; }
    // --- R7 birim: köşe hassasiyeti, stencil, çizim sırası -----------------
    const k = kure(); koy(k, 42.0264, 35.1551, 2);
    istekler(k);
    const sp = z => 288 / Math.pow(2, z);
    const karo = (z, lat, lon) => [Math.floor((lon + 180) / sp(z)), Math.floor((90 - lat) / sp(z))];
    const tex = new THREE.Texture();
    const m9 = k._makeTileMesh(9, ...karo(9, 42.0264, 35.1551), tex, 'landsat_weld');
    const m11 = k._makeTileMesh(11, ...karo(11, 42.0264, 35.1551), tex, 'landsat_weld');
    const p12 = k._makeTileMesh(12, ...karo(12, 42.0264, 35.1551), tex, 'pack_detail');
    const p15 = k._makeTileMesh(15, ...karo(15, 42.0264, 35.1551), tex, 'pack_detail');
    out.zemin9 = Object.assign(malzeme(m9), dunyaHatasi(m9));
    out.zemin11 = Object.assign(malzeme(m11), dunyaHatasi(m11));
    out.paket12 = Object.assign(malzeme(p12), dunyaHatasi(p12));
    out.paket15 = Object.assign(malzeme(p15), dunyaHatasi(p15));
    // Paket karosu kutunun BATI kenarını kesiyor: köşeler kutunun içinde kalmalı.
    const batı = karo(12, 42.0264, KUTU[0] + 0.01);
    const kenar = k._makeTileMesh(12, batı[0], batı[1], tex, 'pack_detail');
    const a = kenar.geometry.getAttribute('position').array; let enBati = Infinity, adim = 0;
    for (let i = 0; i < a.length; i += 3) {
        const v = new THREE.Vector3(a[i] + kenar.position.x, a[i + 1] + kenar.position.y, a[i + 2] + kenar.position.z);
        enBati = Math.min(enBati, G.vec3ToLatLon(v).lon);
    }
    const a15 = p15.geometry.getAttribute('position').array;
    out.kenar = { enBati, kutuBati: KUTU[0], karoBati: -180 + batı[0] * sp(12) };
    out.disarida = k._makeTileMesh(12, ...karo(12, 42.0, 30.0), tex, 'pack_detail') === null;
    out.paketAdimDeg = k._paketAdimDeg;
    out.paket12Parca = Math.round(Math.sqrt(p12.geometry.getAttribute('position').count)) - 1;
    out.zemin11Parca = Math.round(Math.sqrt(m11.geometry.getAttribute('position').count)) - 1;
    // --- NE su maskesi ------------------------------------------------------
    const mk = (katman) => ({ katman, malzeme: new THREE.LineBasicMaterial() });
    const hucreler = [mk('coastline'), mk('lakes'), mk('rivers'), mk('borders'), mk('admin1')];
    k._vectors = { seviyeler: { '10m': { hucreler } } };
    k._neSuMaskele();
    out.neMaske = hucreler.map(h => ({ katman: h.katman, stencil: h.malzeme.stencilWrite,
        ref: h.malzeme.stencilRef, writeMask: h.malzeme.stencilWriteMask,
        func: h.malzeme.stencilFunc === THREE.NotEqualStencilFunc }));
    // --- Paket URL sürümü (önbellek ayrımı) ----------------------------------
    const kp = kure(); koy(kp, 42.0264, 35.1551, 2); istekler(kp);
    kp._buildTilePatch = P._buildTilePatch;
    urls.length = 0;
    kp._buildTilePatch('pack_detail', 15, 1, 2);
    kp._buildTilePatch('landsat_weld', 11, 1, 2);
    imza = 'sinop_tr:bb'; kp._tileNextT = -1; kp._paketKatmani({ lat: 42.0264, lon: 35.1551 }, 15, 1.6);
    kp._buildTilePatch('pack_detail', 15, 3, 4);
    out.url = urls.slice();
    // Kurulu küme değişince eski bindirme karoları atılır (yenisi yeniden istenir).
    out.eskiGirdiKaldi = kp._tiles.has('pack_detail:15:1:2');
    out.yeniGirdiVar = kp._tiles.has('pack_detail:15:3:4');
    // getTileInfo().pack ve LRU sınıfları
    out.tileInfo = k.getTileInfo();
    // Kare yükü: gerçek Mercator düzeyi (Sinop 2 km, φ ≈ 42,03°).
    let yuk = null;
    k.addFrameListener(f => { yuk = { zWeb: f.zWeb, zMercator: f.zMercator }; });
    k._emitFrame();
    out.kareYuku = yuk;
    process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


def _kure(tmp_path, ui_offered=True, depo='1'):
    return _node(tmp_path, KURE_DUZENEK, THREE_JS, VEKTOR, GLOBE,
                 env={'DURUM': json.dumps(_durum(ui_offered)), 'KUTU': json.dumps(SINOP_KUTU),
                      'DEPO': depo})


def _paket(istek):
    return [i for i in istek if i[0] == tc.PACK_LAYER_KEY]


@node_gerek
def test_R7_kose_merkeze_gore_ve_stencil_en_ince_kazanir(tmp_path):
    o = _kure(tmp_path)
    for ad in ('zemin9', 'zemin11', 'paket12', 'paket15'):
        m = o[ad]
        # Köşe dünya koordinatında float32 olsaydı yarıçap hatası ~3,8e-6 birim
        # (~0,24 m) olurdu; karo merkezine göre köşede mm altı.
        assert m['radyusHatasi'] < 1e-7, (ad, m)
        assert m['yerelEnBuyuk'] < 2.0, (ad, m)          # köşe yerel (karo boyu mertebesi)
        assert abs(m['konumR'] - 100.0) < 1e-6, (ad, m)  # nesne konumu karo merkezi (küre üstü)
        assert m['stencilWrite'] is True and m['func'] == 'NotEqual' and m['zpass'] == 'Replace', m
    for ad in ('zemin9', 'zemin11'):
        m = o[ad]
        assert (m['ref'], m['funcMask'], m['writeMask']) == (1, 1, 1), m
        assert m['transparent'] is False and m['renderOrder'] > 0, m
    for ad in ('paket12', 'paket15'):
        m = o[ad]
        assert (m['ref'], m['funcMask'], m['writeMask']) == (2, 2, 2), m
        assert m['transparent'] is True and m['depthWrite'] is False, m
        assert -1 < m['renderOrder'] < 0, m               # yıldızlardan sonra, çizgilerden önce
    # İnceden kabaya: ince karonun çizim sırası daha önce.
    assert o['zemin11']['renderOrder'] < o['zemin9']['renderOrder']
    assert o['paket15']['renderOrder'] < o['paket12']['renderOrder']


@node_gerek
def test_paket_bindirmesi_kutuya_kirpilir_ve_ince_bolunur(tmp_path):
    o = _kure(tmp_path)
    k = o['kenar']
    assert k['karoBati'] < k['kutuBati'], k                 # karo kutunun batısına taşıyor
    assert k['enBati'] >= k['kutuBati'] - 1e-6, k            # bindirme kutuda kırpılmış
    assert o['disarida'] is True                              # kapsam dışı karo: yama YOK
    # Bindirme yüzü küreden en çok hMin/2 (1 m) sarkar: z12 karosu bu adıma göre bölünür.
    adim = o['paketAdimDeg']
    assert 0.04 < adim < 0.05, adim                           # 2·sqrt(1 m / R) = 0,0454°
    assert o['zemin11Parca'] == 8 and o['paket12Parca'] == 8, o


@node_gerek
def test_z15_tavani_yalniz_kurulu_paket_kapsaminda(tmp_path):
    o = _kure(tmp_path)['senaryo']
    s2 = o['sinop_2km']
    p = _paket(s2['istek'])
    assert p and {z for _, z, _, _ in p} == {15}, s2         # 2 km: paket z15
    assert s2['paketEtkin'] and s2['grupGorunur'] and s2['paketZ'] == 15
    # Zemin tavanı değişmez (ayrıntı katmanı 11, paketli 5).
    zemin = [i for i in s2['istek'] if i[0] != tc.PACK_LAYER_KEY]
    assert max(z for _, z, _, _ in zemin) <= 11, zemin
    assert {z for _, z, _, _ in _paket(o['sinop_20km']['istek'])} == {12}
    # Kutu (200 km) ekrandan dar: uzak ölçekte bindirme çizilmez.
    assert not _paket(o['sinop_400km']['istek']) and not o['sinop_400km']['paketEtkin']
    # Paket kapsamı dışı: bugünkü davranış (paket isteği yok).
    assert not _paket(o['istanbul_2km']['istek']) and not o['istanbul_2km']['grupGorunur']


@node_gerek
def test_paket_katmani_fail_closed(tmp_path):
    # Sunucu katmanı arayüze sunmuyorsa (künye anahtarı yok) paket istenmez.
    o = _kure(tmp_path, ui_offered=False)['senaryo']
    assert not _paket(o['sinop_2km']['istek']) and not o['sinop_2km']['paketEtkin']
    # Kurulu paket yoksa ya da depo modülü yoksa da istenmez.
    for depo in ('0', 'yok'):
        o = _kure(tmp_path, depo=depo)['senaryo']
        assert not _paket(o['sinop_2km']['istek']), depo


@node_gerek
def test_ne_su_cizgileri_paket_bindirmesinde_maskelenir(tmp_path):
    o = _kure(tmp_path)
    m = {x['katman']: x for x in o['neMaske']}
    for katman in ('coastline', 'lakes', 'rivers'):
        assert m[katman]['stencil'] is True and m[katman]['func'] is True, m[katman]
        assert m[katman]['ref'] == 2 and m[katman]['writeMask'] == 0, m[katman]
    for katman in ('borders', 'admin1'):              # paket sınır çizmez: maskelenmez
        assert not m[katman]['stencil'], m[katman]


@node_gerek
def test_paket_karo_url_kurulu_kumeyle_surumlenir(tmp_path):
    o = _kure(tmp_path)
    u = o['url']
    assert re.fullmatch(r'/api/tile/pack_detail/15/1/2\?v=[0-9a-f]+', u[0]), u
    assert u[1] == '/api/tile/landsat_weld/11/1/2', u          # zemin URL'si aynen
    assert u[2].split('?v=')[1] != u[0].split('?v=')[1], u     # paket kümesi değişti
    assert 'net=' not in u[0]                                  # paket ağa çıkmaz: rıza parametresi yok
    assert o['eskiGirdiKaldi'] is False and o['yeniGirdiVar'] is True, o   # eski bindirme atıldı
    y = o['kareYuku']
    import math
    assert abs(y['zMercator'] - (y['zWeb'] + math.log2(math.cos(math.radians(SINOP[0]))))) < 1e-3, y
    ti = o['tileInfo']
    assert ti['pack']['attributionKey'] == 'site.mapPackAttribution'
    assert set(ti['pack']) >= {'active', 'count', 'z', 'layer', 'attributionKey'}


# ===========================================================================
# ETİKETLER
# ===========================================================================
ETIKET_DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [THREE_JS, GLOBE_JS, ETIKET_JS] = process.argv.slice(2);
const KUTU = JSON.parse(process.env.KUTU);
const ctx = { console, Math, JSON, Promise, setTimeout, performance: { now: () => 1e6 } };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(THREE_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(GLOBE_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(ETIKET_JS, 'utf8'), ctx);
const THREE = ctx.THREE, G = ctx.LaunchSiteGlobe, L = ctx.LaunchSiteLabels;
ctx.LaunchSiteMapPacks = { kuruluKutular: () => [{ id: 'sinop_tr', bbox: KUTU, sha256: 'aa' }], imza: () => 'sinop_tr:aa' };
const istek = [];
let yanit = { labels: [] };
const lab = new L({ latLonToXYZ: G.latLonToXYZ, getLang: () => 'tr',
    fetchImpl: (url) => { istek.push(url); return Promise.resolve({ ok: true, json: () => Promise.resolve(yanit) }); } });
// Taban veri yerine en küçük durum: bir NE yeri ('Sinop'), ülke yok, GeoNames yüklenemedi.
Object.assign(lab, { durum: 'hazir', N: 1, M: 0, T: 1, _T0: 1, _neZTavan: 9,
    xyz: new Float64Array(3), tur: new Uint8Array(1), zAlt: new Float32Array([7]), zUst: new Float32Array([Infinity]),
    lat: new Float32Array([42.0]), lon: new Float32Array([35.15]), ad: ['Sinop'], adEn: ['Sinop'], adTr: ['Sinop'],
    _onceki: new Uint8Array(1), _simdiki: new Uint8Array(1), _aday: new Float64Array(1),
    _genislik: new Float32Array([NaN]), _yuvaOf: new Int16Array([-1]), kovalar: [] });
lab._dil = 'tr';
lab.detay.durum = 'hata';
function kamera(lat, lon, hKm) {
    const c = new THREE.PerspectiveCamera(38, 1440 / 900, 0.01, 1e5);
    const n = G.latLonToVec3(lat, lon, 1).normalize();
    c.position.copy(n.clone().multiplyScalar(100 + hKm * 1000 / 63710));
    c.up.set(0, 1, 0); c.lookAt(n.clone().multiplyScalar(100));
    c.near = 0.3 * hKm * 1000 / 63710; c.updateProjectionMatrix(); c.updateMatrixWorld();
    return c;
}
(async () => {
    const out = {};
    const cam = kamera(42.0264, 35.1551, 20);
    const mpp = 2 * 20000 * Math.tan(19 * Math.PI / 180) / 900;
    const zWeb = Math.log2(156543.03 / mpp);
    // Kare yükünü küre verir (ölçeğin tek sahibi): z_web + log2(cos φ), φ = 42,0264°.
    const f = { camera: cam, globeRadius: 100, zWeb: zWeb, metersPerPixel: mpp,
                zMercator: zWeb + Math.log2(Math.cos(42.0264 * Math.PI / 180)) };
    out.kutu = L.gorunenKutu(cam, 100);
    yanit = { labels: [
        { name: 'Sinop', lon: 35.15, lat: 42.02, kind: 'locality', rank: 7 },
        { name: 'Gelincik', lon: 35.1, lat: 42.01, kind: 'locality', rank: 13 },
        { name: 'Sinop Launch Area', lon: 35.16, lat: 42.03, kind: 'launch_complex', rank: 13 },
        { name: '', lon: 35.1, lat: 42.0, kind: 'locality', rank: 12 },
        { name: 'Bozuk', lon: 'x', lat: 42.0, kind: 'locality', rank: 12 },
        { name: 'Çok ince', lon: 35.12, lat: 42.0, kind: 'neighbourhood', rank: 16 } ], truncated: false };
    lab._paketIstegi(f, zWeb);
    await new Promise(r => setTimeout(r, 0)); await new Promise(r => setTimeout(r, 0));
    out.istek = istek.slice();
    out.paket = lab.getInfo().paket;
    out.tur = Array.from(lab.tur.slice(lab._Tp));
    out.ad = lab.ad.slice(lab._Tp);
    out.katliAyni = lab._katli[lab._Tp] === lab._katli[0];
    // Aday süzgeci: rank <= z_web (13,2 -> 13 alınır, 16 alınmaz).
    const e = new Float64Array(16);
    const pm = cam.projectionMatrix.elements, vm2 = cam.matrixWorldInverse.elements;
    for (let s = 0; s < 4; s++) for (let r = 0; r < 4; r++)
        e[s * 4 + r] = pm[r] * vm2[s * 4] + pm[4 + r] * vm2[s * 4 + 1] + pm[8 + r] * vm2[s * 4 + 2] + pm[12 + r] * vm2[s * 4 + 3];
    lab._onceki.fill(0);
    const n = lab._paketAdaylari(f, cam.position.x, cam.position.y, cam.position.z, 100, 0, e);
    out.aday = Array.from(lab._aday.slice(0, n)).map(a => lab.ad[a % lab.T]).sort();
    // Aynı istek yinelenmez; dil değişince yeni istek.
    lab._paketZaman = -Infinity;
    lab._paketIstegi(f, zWeb);
    out.yineleme = istek.length;
    lab._dil = 'en'; lab._paketZaman = -Infinity;
    lab._paketIstegi(f, zWeb);
    await new Promise(r => setTimeout(r, 0));
    out.dilIstek = istek[istek.length - 1];
    // Kurulu paket kalmadı: bölge boşalır.
    ctx.LaunchSiteMapPacks = { kuruluKutular: () => [], imza: () => '' };
    lab._paketIstegi(f, zWeb);
    out.bosalinca = { T: lab.T, Tp: lab._Tp, durum: lab.paket.durum };
    process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


@node_gerek
def test_paket_yer_adlari_dil_duzey_tur_ve_tekrar(tmp_path):
    o = _node(tmp_path, ETIKET_DUZENEK, THREE_JS, GLOBE, ETIKET, env={'KUTU': json.dumps(SINOP_KUTU)})
    w, s, e, n = o['kutu']['kutu']
    assert w < SINOP[1] < e and s < SINOP[0] < n, o['kutu']     # görünen kutu sahayı içerir
    assert (e - w) < 0.5 and (n - s) < 0.3, o['kutu']           # 20 km'de ~23 km genişlik
    assert len(o['istek']) == 1
    u = o['istek'][0]
    m = re.fullmatch(r'/api/map-packs/labels\?bbox=([-0-9.,]+)&z=(\d+)&lang=(tr|en)', u)
    assert m, u
    assert m.group(3) == 'tr'
    # z: gerçek Mercator düzeyi = z_web (13,2) + log2(cos 42°) -> 12; en çok 15.
    assert m.group(2) == '12', u
    kutu = [float(x) for x in m.group(1).split(',')]
    assert kutu[0] >= SINOP_KUTU[0] - 1e-9 and kutu[2] <= SINOP_KUTU[2] + 1e-9, kutu  # paket kutusuyla kesişim
    assert o['paket']['sayi'] == 4 and o['paket']['durum'] == 'hazir', o['paket']   # boş ad + bozuk konum basılmaz
    assert o['tur'] == [0, 0, 3, 0], o['tur']                   # launch_complex -> rampa türü
    assert o['katliAyni'] is True                               # 'Sinop' NE ile aynı ad: tekrar sayılır
    assert o['aday'] == ['Gelincik', 'Sinop', 'Sinop Launch Area'], o['aday']   # rank 16 elendi
    assert o['yineleme'] == 1                                   # aynı istek yinelenmedi
    assert o['dilIstek'].endswith('&lang=en'), o['dilIstek']
    assert o['bosalinca'] == {'T': o['bosalinca']['Tp'], 'Tp': o['bosalinca']['Tp'], 'durum': 'yok'}


# ===========================================================================
# PANEL
# ===========================================================================
PANEL_DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [PANEL_JS] = process.argv.slice(2);
// En küçük DOM benzeri (yalnız panelin kullandığı yüzey).
class Dugum {
    constructor(ad) { this.tagName = ad; this.children = []; this.parentNode = null; this.style = {};
                      this.attr = {}; this.dinle = {}; this._t = ''; this.className = ''; this.type = ''; }
    get firstChild() { return this.children[0] || null; }
    appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.children.push(c); return c; }
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; return c; }
    setAttribute(k, v) { this.attr[k] = String(v); }
    getAttribute(k) { return (k in this.attr) ? this.attr[k] : null; }
    addEventListener(t, fn) { (this.dinle[t] = this.dinle[t] || []).push(fn); }
    set textContent(v) { this._t = String(v); this.children = []; }
    get textContent() { return this._t + this.children.map(c => c.textContent).join(''); }
    tumu() { return [this].concat(...this.children.map(c => c.tumu())); }
}
const kok = { liste: new Dugum('div'), ozet: new Dugum('div') };
const doc = { createElement: a => new Dugum(a), getElementById: id => kok[id] || null };
const istek = [];
let durum = 'not_installed', ilerleme = { bytes_done: 0, bytes_total: 4271826 };
const yanit = (g, ok = true) => Promise.resolve({ ok, status: ok ? 200 : 400, json: () => Promise.resolve(g) });
function fetchImpl(url, sec) {
    istek.push([sec && sec.method || 'GET', url, sec && sec.body || null,
                sec && sec.headers ? sec.headers['Content-Type'] : null]);
    if (url === '/api/map-packs') return yanit({ packs: [{ id: 'jiuquan_43', kind: 'site', name_key: 'site.mapPackName.jiuquan_43',
        bbox: [99.1, 40.0, 101.5, 41.9], zoom_max: 15, size_bytes: 4271826, sha256: 'ab', license: 'ODbL-1.0',
        status: durum, progress: durum === 'downloading' ? ilerleme : null, error_code: null }] });
    if (url.endsWith('/download')) { durum = 'downloading'; return yanit({ state: 'downloading' }); }
    if (url.endsWith('/progress')) return yanit({ state: durum, bytes_done: ilerleme.bytes_done, bytes_total: ilerleme.bytes_total, error_code: null });
    if (url.endsWith('/cancel')) { durum = 'not_installed'; return yanit({ state: 'not_installed' }); }
    if (sec && sec.method === 'DELETE') { durum = 'not_installed'; return yanit({ deleted_bytes: 4271826 }); }
    return yanit({}, false);
}
const ctx = { console, Math, JSON, Promise, setTimeout, encodeURIComponent, String, Number,
              setInterval: () => 1, clearInterval: () => {} };
ctx.window = ctx;
// Anahtar döndüren en küçük I18N: metnin HANGİ anahtardan geldiği sınanır.
ctx.I18N = { t: k => k, has: () => true, number: (v, n) => Number(v).toFixed(n),
             tf: (k, p) => k + ' ' + JSON.stringify(p), onChange: () => {} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(PANEL_JS, 'utf8'), ctx);
const P = ctx.LaunchSiteMapPacks;
const bekle = () => new Promise(r => setTimeout(r, 0));
const dugmeler = () => kok.liste.tumu().filter(d => d.attr['data-paket-eylem']);
const tikla = ad => { const d = dugmeler().find(x => x.attr['data-paket-eylem'] === ad); if (!d) throw new Error('yok ' + ad); d.dinle.click.forEach(f => f()); };
(async () => {
    const out = {};
    await P.bind({ liste: 'liste', ozet: 'ozet', fetchImpl, document: doc });
    out.eylem0 = dugmeler().map(d => d.attr['data-paket-eylem']);
    tikla('indir'); await bekle();
    out.onayAcik = dugmeler().map(d => d.attr['data-paket-eylem']);
    tikla('vazgec'); await bekle();
    out.vazgecSonrasiPost = istek.filter(i => i[0] !== 'GET').length;
    tikla('indir'); await bekle();
    tikla('onayla-indir'); for (let i = 0; i < 4; i++) await bekle();
    out.post = istek.filter(i => i[0] === 'POST');
    out.inerkenMetin = kok.liste.textContent;
    ilerleme = { bytes_done: 2135913, bytes_total: 4271826 };
    await P._yokla(); for (let i = 0; i < 4; i++) await bekle();
    out.yarimMetin = kok.liste.textContent;
    out.cubuk = kok.liste.tumu().filter(d => d.attr.role === 'progressbar').map(d => d.attr['aria-valuenow']);
    tikla('iptal'); for (let i = 0; i < 4; i++) await bekle();
    out.iptal = istek.filter(i => i[1].endsWith('/cancel'));
    durum = 'installed'; await P.yenile();
    out.kurulu = P.kuruluKutular(); out.imza = P.imza();
    tikla('sil'); await bekle();
    out.silOnayOncesi = istek.filter(i => i[0] === 'DELETE').length;
    tikla('onayla-sil'); for (let i = 0; i < 4; i++) await bekle();
    out.sil = istek.filter(i => i[0] === 'DELETE');
    out.hata = ['http_404', 'http_503', 'sha256_mismatch', 'garip_kod', null].map(k => P._hataMetni(k));
    out.oz = [P._ilerlemeOzeti(512, 1024), P._ilerlemeOzeti(512, null), P._ilerlemeOzeti(null, 1024)];
    out.uc = P.UC; out.kodlar = P.HATA_ANAHTARI;
    process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


@node_gerek
def test_panel_onaysiz_indirme_yok_ilerleme_sunucudan_iptal_sil(tmp_path):
    o = _node(tmp_path, PANEL_DUZENEK, PANEL)
    assert o['eylem0'] == ['indir']
    assert set(o['onayAcik']) >= {'onayla-indir', 'vazgec'}
    assert o['vazgecSonrasiPost'] == 0                          # onay kutusu açıldı, kapandı: istek YOK
    assert len(o['post']) == 1, o['post']
    meth, url, govde, tip = o['post'][0]
    assert url == '/api/map-packs/jiuquan_43/download' and tip == 'application/json'
    assert json.loads(govde) == {'consent': True}               # gövde tam {"consent": true}
    # İlerleme: sunucu baytı 2.135.913 / 4.271.826 -> %50; çubuk aynı sayı.
    assert o['cubuk'] == ['50'], o['cubuk']
    assert 'site.mapPackProgress' in o['yarimMetin'] and '"pct":"50"' in o['yarimMetin'], o['yarimMetin']
    assert '"done":"2.1"' in o['yarimMetin'] and '"total":"4.3"' in o['yarimMetin']
    assert len(o['iptal']) == 1 and o['iptal'][0][2] == '{}' and o['iptal'][0][3] == 'application/json'
    assert o['kurulu'] == [{'id': 'jiuquan_43', 'bbox': [99.1, 40.0, 101.5, 41.9], 'sha256': 'ab'}]
    assert o['imza'] == 'jiuquan_43:ab'
    assert o['silOnayOncesi'] == 0 and len(o['sil']) == 1      # silme de onaylı
    assert o['sil'][0][1] == '/api/map-packs/jiuquan_43'
    # Yüzde yalnız toplam biliniyorken; bayt yoksa metin yok.
    assert o['oz'][0]['oran'] == 0.5 and o['oz'][1]['oran'] is None and o['oz'][2]['metin'] is None
    # Hata kodu ekrana HAM yazılmaz: her kod bir i18n anahtarına eşlenir (sayı yok).
    assert o['hata'] == ['site.mapPackErr.http404', 'site.mapPackErr.http',
                         'site.mapPackErr.sha256_mismatch', 'site.mapPackErr.other',
                         'site.mapPackErr.other'], o['hata']


# ===========================================================================
# İ18N / ŞABLON / SÖZLEŞME
# ===========================================================================
def _sozluk():
    kod = r"""
    const fs = require('fs'), vm = require('vm'); let d = null;
    const ctx = { window: {} }; ctx.window.I18N = { register: x => { d = x; } };
    vm.createContext(ctx); vm.runInContext('var window = this.window;' + fs.readFileSync(process.env.SOZLUK_YOLU, 'utf8'), ctx);
    process.stdout.write(JSON.stringify(d));
    """
    # Betik stdin'den (node çağrı sözleşmesi: argv ile betik geçmez).
    r = subprocess.run([NODE], input=kod, capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, SOZLUK_YOLU=str(I18N)))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@node_gerek
def test_i18n_paket_anahtarlari_en_tr_ve_kunye_kilidi(tmp_path):
    d = _sozluk()
    en, tr = d['en'], d['tr']
    yeni = [k for k in en if k.startswith(('site.mapPack', 'site.help.mapPack'))]
    assert len(yeni) >= 60
    for k in yeni:
        assert k in tr and tr[k].strip(), k
    # Her paket kimliğinin adı iki dilde (liste uygulamayla gelir).
    for p in _PAKETLER:
        assert p['name_key'] in en and p['name_key'] in tr, p['id']
    # Künye EN metni tile_cache katmanının makine künyesiyle BİREBİR (test_d31 kilidi
    # birleşmede ui_offered=True + attribution_i18n_key ile birlikte devreye girer).
    assert en['site.mapPackAttribution'] == tc.LAYERS[tc.PACK_LAYER_KEY]['attribution']
    # Panelin bildiği her hata kodunun metni iki dilde.
    panel = PANEL.read_text(encoding='utf-8')
    anahtarlar = re.findall(r"'(site\.mapPackErr\.[a-z_0-9]+)'", panel)
    assert len(set(anahtarlar)) >= 24, anahtarlar
    for k in anahtarlar:
        assert k in en and k in tr, k
    # Kullanıcı metninde uç adı / ham HTTP kodu yok.
    for k in yeni:
        for metin in (en[k], tr[k]):
            assert '/api/' not in metin and 'HTTP' not in metin and 'endpoint' not in metin.lower(), k


def test_sablon_paket_blogu_tek_ve_kunye_yedegi_kaynakla_ayni():
    s = SABLON.read_text(encoding='utf-8')
    assert s.count('<!-- FS-HARİTA-PAKET') == 1 and s.count('<!-- /FS-HARİTA-PAKET -->') == 1
    blok = s.split('<!-- FS-HARİTA-PAKET')[1].split('<!-- /FS-HARİTA-PAKET -->')[0]
    assert '<script src="/static/js/launch_site_map_packs.js"></script>' in blok
    assert 'data-i18n="site.help.mapPacks"' in blok and 'class="tooltip-icon"' in blok
    m = re.search(r'id="ls-pack-attr"[^>]*data-i18n="site.mapPackAttribution">([^<]*)</div>', blok)
    assert m and m.group(1) == tc.LAYERS[tc.PACK_LAYER_KEY]['attribution']


def test_panel_ve_etiket_ucu_yollari_uygulama_rotalari():
    from hrma.app import app
    kurallar = {r.rule for r in app.url_map.iter_rules()}
    panel = PANEL.read_text(encoding='utf-8')
    yollar = re.findall(r"var UC_[A-Z]+ = '([^']+)';", panel)
    assert len(yollar) == 5
    for y in yollar:
        assert y.replace('{id}', '<pack_id>') in kurallar, y
    etiket = ETIKET.read_text(encoding='utf-8')
    assert re.search(r"var PAKET_ETIKET_UCU = '/api/map-packs/labels';", etiket)
    assert '/api/map-packs/labels' in kurallar


# ===========================================================================
# UÇ BEKÇİLERİ: panelin ve etiket katmanının çağırdığı iki uç (silme, etiket)
# ===========================================================================
@pytest.fixture
def paket_istemci(tmp_path, monkeypatch):
    """Yalıtılmış kurulum dizini (kullanıcının gerçek veri dizini DEĞİL)."""
    from hrma.analysis import map_packs
    kurulum = tmp_path / 'maps'
    kurulum.mkdir()
    monkeypatch.setattr(map_packs, '_KURULUM_DIZINI_SAGLAYICI', lambda: str(kurulum))
    monkeypatch.setenv('HRMA_TILE_CACHE_DIR', str(tmp_path / 'tiles'))
    from hrma.app import app
    with app.test_client() as c:
        yield c, kurulum


def test_uc_paket_silme_get_ile_tetiklenemez_ve_delete_calisir(paket_istemci):
    c, kurulum = paket_istemci
    # Silme yalnız DELETE yöntemiyle: GET (bağlantı, önizleme, önbellek) silemez.
    r = c.get('/api/map-packs/sinop_tr')
    assert r.status_code == 405
    r = c.delete('/api/map-packs/sinop_tr')
    assert r.status_code == 200 and r.get_json() == {'deleted_bytes': 0}
    r = c.delete('/api/map-packs/yok_boyle_paket')
    assert r.status_code == 404 and r.get_json()['error_code'] == 'unknown_pack'
    assert list(kurulum.iterdir()) == []


def test_uc_paket_etiketleri_sozlesmesi(paket_istemci):
    c, _ = paket_istemci
    w, s, e, n = SINOP[1] - 0.05, SINOP[0] - 0.03, SINOP[1] + 0.05, SINOP[0] + 0.03
    r = c.get('/api/map-packs/labels', query_string={'bbox': '%f,%f,%f,%f' % (w, s, e, n),
                                                      'z': '12', 'lang': 'tr'})
    # Kurulu paket yok: boş liste (sahte ad yok).
    assert r.status_code == 200 and r.get_json() == {'labels': [], 'truncated': False}
    # Kutu bu düzeyde karo sınırını aşarsa adıyla ret (istemci bir düzey kaba ister).
    w2, s2, e2, n2 = SINOP_KUTU
    r = c.get('/api/map-packs/labels', query_string={'bbox': '%f,%f,%f,%f' % (w2, s2, e2, n2),
                                                      'z': '12', 'lang': 'tr'})
    assert r.status_code == 400 and r.get_json()['error_code'] == 'bbox_too_large'
    for kotu in ({'bbox': '1,2,3', 'z': '12', 'lang': 'tr'},
                 {'bbox': '%f,%f,%f,%f' % (w, s, e, n), 'z': '16', 'lang': 'tr'},
                 {'bbox': '%f,%f,%f,%f' % (w, s, e, n), 'z': '12', 'lang': 'de'}):
        r = c.get('/api/map-packs/labels', query_string=kotu)
        assert r.status_code == 400, kotu
