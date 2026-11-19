# -*- coding: utf-8 -*-
"""V307 / FS-HARİTA (9 Kas 2026) — Fırlatma Sahası küresinde yakın zoom bekçisi.

Kullanıcı şikâyeti (Berke, 9 Kas): "dünyada yakınlaştırınca şehirler ve
zemin yüklenmiyor". Ölçülen kök nedenler (kanıt
``~/HRMA-calisma/2026-11-09/FS-HARITA/olcum/``, RAPOR
``docs/scofield/raw/OH/V307/fs-harita/RAPOR.md``):

K1  Açılış / 'Tüm Dünya' kipinde yörünge hedefi Dünya MERKEZİNDE; tekerlekle
    yaklaşınca da orada kalıyor. Karo yaması hedef merkezdeyken HİÇ
    çalışmıyordu (rıza açıkken 0 istek); m/px hedefe uzaklıktan hesaplanıyordu
    (19,1 km irtifada 5.208 m/px, gerçek 15,6) -> etiket/vektör/ölçek donuk.
K2  Karo üçgenlerinin sarımı ters: yamalar ARKA YÜZ olarak atılıyordu; rıza
    açık/kapalı ekran pikselleri birebir aynıydı (karo sayacı mesh sayıyordu).
K3  En ince katman bluemarble z7 (~489 m/px): yakın zoomda ayrıntı yoktu.
K4  Natural Earth yer verisi seyrek (7.342 yer, Türkiye 83); NE MIN_ZOOM
    z_web 9'da biter.
K5  Rıza kapalıyken nedeni ve ayarın yeri yakın zoomda görünmüyordu.
K6  Yakın bakış sınırı 25,5 km, uçuşlu 'Sahaya yakınlaş' tabanı 191 km.

Bekçiler birim düzeyidir (tile_cache, gerçek küre/etiket modülü node'da);
ekran ölçümü ``olc_kure.py`` ile tarayıcıda yapılır (RAPOR önce/sonra).
"""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
GLOBE = JS / 'launch_site_globe.js'
ETIKET = JS / 'launch_site_labels.js'
I18N = JS / 'i18n_launch_site.js'
THREE_JS = KOK / 'hrma' / 'static' / 'vendor' / 'three-0.128.0.min.js'
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
HARITA = KOK / 'hrma' / 'static' / 'map'
PAKET = KOK / 'packaging'
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

from hrma.analysis import tile_cache as tc  # noqa: E402

import re  # noqa: E402

# Sahne ölçeğinin TEK sahibi küre modülüdür: sayı oradan okunur
# (six_dof_trajectory.R_EARTH ile aynı yarıçap; GLOBE_R sahne birimi).
_G = GLOBE.read_text(encoding='utf-8')
R_EARTH_M = float(re.search(r'var R_EARTH_M = ([0-9.]+);', _G).group(1))
GLOBE_R = float(re.search(r'var GLOBE_R = ([0-9.]+);', _G).group(1))
M_PER_UNIT = R_EARTH_M / GLOBE_R


def _oku(p):
    return p.read_text(encoding='utf-8')


# ===========================================================================
# 1) tile_cache — ayrıntı katmanı (K3)
# ===========================================================================

def test_ayrinti_katmani_kaydi_ve_geometrisi():
    cfg = tc.LAYERS['landsat_weld']
    assert cfg['wmts'] == 'Landsat_WELD_CorrectedReflectance_TrueColor_Global_Annual'
    assert cfg['tms'] == '31.25m' and cfg['max_zoom'] == 11
    assert cfg['fixed_date'] == '2000-12-01' and cfg['time'] is False
    assert cfg['ui_offered'] is True
    assert cfg['attribution_i18n_key'] == 'site.tileDetailAttribution'
    # Künye görüntünün güncel olmadığını söyler (2000 bileşkesi).
    assert '2000' in cfg['attribution'] and 'not current' in cfg['attribution']
    g = tc.matrix_geometry()
    # WMTSCapabilities.xml (2026-11-09) 31.25m: z11 2560x1280.
    # V307/FS-HARİTA-VERİ faz 2: yayımlanan geometri artık indirilen harita paketi
    # katmanının (pack_detail, z15) düzeylerini de kapsar; matrix_geometry() varsayılanı
    # LAYERS'ın en yüksek max_zoom'udur (15). Ayrıntı katmanının KENDİ tavanı 11 kalır
    # (aşağıdaki list_layers kaydı) ve z11 geometrisi aynen doğrulanır.
    assert g['max_zoom'] == 15
    assert (g['levels']['11']['matrix_width'], g['levels']['11']['matrix_height']) == (2560, 1280)
    k = tc.list_layers()['layers']['landsat_weld']
    assert k['source'] == 'gibs' and k['max_zoom'] == 11 and k['ui_offered'] is True


def test_ayrinti_url_sabit_tarih_ve_zyx_sirasi():
    url = tc._gibs_url(tc.LAYERS['landsat_weld'], 11, 1486, 348, 'IGNORED')
    assert url == ('https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/'
                   'Landsat_WELD_CorrectedReflectance_TrueColor_Global_Annual/default/'
                   '2000-12-01/31.25m/11/348/1486.jpg')


class _Yanit:
    status = 200
    headers = {'Content-Type': 'image/jpeg'}

    def __init__(self, govde):
        self._g = govde

    def read(self):
        return self._g

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ayrinti_katmani_rizasiz_aga_cikmaz_rizayla_tarihli_yola_yazar(tmp_path, monkeypatch):
    import urllib.request
    istek = []

    def sahte(req, timeout=0):
        istek.append(req.full_url)
        return _Yanit(b'\xff\xd8\xff\xe0' + b'0' * 64)
    monkeypatch.setattr(urllib.request, 'urlopen', sahte)
    monkeypatch.setenv('HRMA_TILE_CACHE_DIR', str(tmp_path))
    r = tc.resolve_tile('landsat_weld', 11, 1486, 348)
    assert r['ok'] is False and r['code'] == 403 and r.get('network_disabled') is True
    assert istek == []                                     # rıza yok: tek bayt yok
    # İstemcinin tarihi YOK SAYILIR: yol katmanın kendi tarihiyle sürümlenir.
    r = tc.resolve_tile('landsat_weld', 11, 1486, 348, date='1999-01-01', allow_network=True)
    assert r['ok'] is True and r['cached'] is False
    assert len(istek) == 1 and '/2000-12-01/31.25m/11/348/1486.jpg' in istek[0]
    assert pathlib.Path(r['path']) == tmp_path / 'landsat_weld' / '2000-12-01' / '11' / '1486' / '348.jpg'
    # z12 aralık dışı (kaynak tavanı z11).
    assert tc.resolve_tile('landsat_weld', 12, 0, 0, allow_network=True)['code'] == 400


# ===========================================================================
# 2) Küre — odak, karo isteği, sarım, rıza notu, yakın bakış (K1, K2, K5, K6)
# ===========================================================================

KURE_DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [THREE_JS, GLOBE_JS, DURUM_JSON, GOREV_JSON] = process.argv.slice(2);
const durum = JSON.parse(fs.readFileSync(DURUM_JSON, 'utf8'));
const gorev = JSON.parse(fs.readFileSync(GOREV_JSON, 'utf8'));
let saat = 0;
const ctx = { console, Math, JSON, Promise, setTimeout,
              performance: { now: () => saat },
              fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(durum) }) };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(THREE_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(GLOBE_JS, 'utf8'), ctx);
const THREE = ctx.THREE, G = ctx.LaunchSiteGlobe, R = 100, MPU = 6371000 / 100;

function kure(H) {
    const istek = [];
    const k = Object.assign(Object.create(G.prototype), {
        _tiles: new Map(), _tileNextT: 0, _tileAnyFail: false, _merkezDoku: null,
        camera: new THREE.PerspectiveCamera(38, 1440 / H, 0.01, 1e5),
        controls: { target: new THREE.Vector3() }, container: { clientHeight: H },
    });
    k._buildTilePatch = function (layer, z, tx, ty) {
        istek.push(layer + ':' + z);
        this._tiles.set(layer + ':' + z + ':' + tx + ':' + ty,
                        { mesh: null, loading: false, failed: !!gorev.dusur, fails: 1, retryAt: Infinity });
    };
    k._disposeTileEntry = function () {};
    return [k, istek];
}
// kip 'global': hedef Dünya merkezinde (açılış/viewGlobe + tekerlek); 'site': hedef yüzeyde.
function poz(k, lat, lon, altM, kip) {
    const n = G.latLonToVec3(lat, lon, 1).normalize();
    if (kip === 'global') k.controls.target.set(0, 0, 0);
    else k.controls.target.copy(n.clone().multiplyScalar(R));
    k.camera.position.copy(n.clone().multiplyScalar(R + altM / MPU));
}
(async () => {
    const out = {};
    const [k, istek] = kure(gorev.H || 900);
    poz(k, gorev.lat, gorev.lon, gorev.altM, gorev.kip);
    const od = k._odak();
    const ll = od.point ? G.vec3ToLatLon(od.point) : null;
    out.odak = { dist: od.dist, yuzey: od.yuzey, lat: ll && ll.lat, lon: ll && ll.lon };
    out.mpp = k._metersPerPixel();
    k._updateTilePatch();                       // geometri yükleme turu
    await new Promise(r => setTimeout(r, 0));
    saat += 1000; k._tileNextT = 0;
    k._updateTilePatch();
    const say = {};
    istek.forEach(s => { say[s] = (say[s] || 0) + 1; });
    out.istek = say;
    out.istenenZ = k._istenenZ;
    out.dustu = k._merkezKarosuDustu(k._istenenZ > 7 ? 'landsat_weld' : 'bluemarble', k._istenenZ,
                                     G.vec3ToLatLon(k._odak().point || k.controls.target));
    process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


def _kure(tmp_path, gorev, durum=None):
    if durum is None:
        durum = {'tile_matrix': tc.matrix_geometry(), 'layers': tc.list_layers(),
                 'network_opt_in': {'param': 'net', 'value': '1'}}
    js = tmp_path / 'kure.js'
    js.write_text(KURE_DUZENEK, encoding='utf-8')
    (tmp_path / 'durum.json').write_text(json.dumps(durum), encoding='utf-8')
    (tmp_path / 'gorev.json').write_text(json.dumps(gorev), encoding='utf-8')
    r = subprocess.run([NODE, str(js), str(THREE_JS), str(GLOBE), str(tmp_path / 'durum.json'),
                        str(tmp_path / 'gorev.json')], capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stderr[-2500:]
    return json.loads(r.stdout)


IST = (41.0082, 28.9784)
KSC = (28.6084, -80.6043)


@node_gerek
def test_K1_hedef_merkezdeyken_odak_yuzeyde_ve_mpp_gercek(tmp_path):
    # Ölçülen kusur: 19,1 km'de 5.208 m/px (hedef merkezde). Gerçek: 2·h·tan19°/H.
    h = 19113.0
    r = _kure(tmp_path, {'lat': IST[0], 'lon': IST[1], 'altM': h, 'kip': 'global'})
    assert r['odak']['yuzey'] is True
    assert abs(r['odak']['dist'] * M_PER_UNIT - h) < 0.5
    assert abs(r['odak']['lat'] - IST[0]) < 1e-6 and abs(r['odak']['lon'] - IST[1]) < 1e-6
    import math
    gercek = 2 * h * math.tan(math.radians(19)) / 900
    assert abs(r['mpp'] - gercek) / gercek < 1e-6, (r['mpp'], gercek)


@node_gerek
def test_K1_hedef_merkezdeyken_karo_istenir(tmp_path):
    # Eskiden 0 istek. 20 km, 900 px: ~16 m/px -> z11 ayrıntı + paketli z5.
    r = _kure(tmp_path, {'lat': IST[0], 'lon': IST[1], 'altM': 20000, 'kip': 'global'})
    assert r['istek'] == {'bm_local:5': 25, 'landsat_weld:11': 25}, r['istek']
    assert r['istenenZ'] == 11


@node_gerek
def test_K1_yuzeydeki_hedefte_sayi_degismez(tmp_path):
    # 'Sahaya yakınlaş' kipi: odak hedefin kendisi; m/px hedef mesafesinden.
    r = _kure(tmp_path, {'lat': KSC[0], 'lon': KSC[1], 'altM': 200000, 'kip': 'site'})
    assert r['odak']['yuzey'] is False
    assert abs(r['odak']['dist'] * M_PER_UNIT - 200000) < 1e-3
    # 200 km, 900 px: 153 m/px -> z9 > 7 -> ayrıntı katmanı z9.
    assert r['istek'] == {'bm_local:5': 25, 'landsat_weld:9': 25}, r['istek']


@node_gerek
def test_K3_ayrinti_tavani_sunucudan_okunmazsa_z7(tmp_path):
    durum = {'tile_matrix': tc.matrix_geometry(), 'network_opt_in': {'param': 'net', 'value': '1'}}
    katalog = tc.list_layers()
    katalog['layers'].pop('landsat_weld')
    durum['layers'] = katalog
    r = _kure(tmp_path, {'lat': IST[0], 'lon': IST[1], 'altM': 20000, 'kip': 'global'}, durum)
    assert r['istek'] == {'bm_local:5': 25, 'bluemarble:7': 25}, r['istek']


@node_gerek
def test_K5_merkez_karosu_dusunce_olcum_true(tmp_path):
    r = _kure(tmp_path, {'lat': IST[0], 'lon': IST[1], 'altM': 20000, 'kip': 'global', 'dusur': True})
    assert r['dustu'] is True
    r = _kure(tmp_path, {'lat': IST[0], 'lon': IST[1], 'altM': 20000, 'kip': 'global'})
    assert r['dustu'] is False


SARIM_DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [THREE_JS, GLOBE_JS, I18N_VAR] = process.argv.slice(2);
const ctx = { console, Math, JSON, Promise, setTimeout, performance: { now: () => 0 },
              fetch: () => Promise.reject(new Error('yok')) };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(THREE_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(GLOBE_JS, 'utf8'), ctx);
const THREE = ctx.THREE, G = ctx.LaunchSiteGlobe, P = G.prototype;
const out = {};
// Geometri sunucudan gelmiş gibi: tileGeomYukle fetch'i reddedildi; _makeTileMesh
// açıklığı tileLevel'den okur, bu yüzden geometriyi durum fetch'iyle kuruyoruz.
(async () => {
    ctx.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(process.env.DURUM)) });
    // tileGeomYukle bir kez çağrılır (ilk _updateTilePatch turu yerine doğrudan).
    const k = Object.assign(Object.create(P), { _tiles: new Map(), _tileNextT: 0,
        camera: new THREE.PerspectiveCamera(38, 1.6, 0.01, 1e5),
        controls: { target: new THREE.Vector3(0, 0, 0) }, container: { clientHeight: 900 } });
    k._buildTilePatch = function () {};
    k.camera.position.set(0, 0, 100.3);
    k._updateTilePatch();
    await new Promise(r => setTimeout(r, 0));
    const sonuc = [];
    for (const [z, tx, ty] of [[5, 21, 4], [9, 371, 87], [11, 1486, 348]]) {
        const m = k._makeTileMesh(z, tx, ty, new THREE.Texture());
        const pos = m.geometry.getAttribute('position').array, idx = m.geometry.index.array;
        let disari = 0, iceri = 0;
        for (let t = 0; t < idx.length; t += 3) {
            const a = new THREE.Vector3().fromArray(pos, 3 * idx[t]);
            const b = new THREE.Vector3().fromArray(pos, 3 * idx[t + 1]);
            const c = new THREE.Vector3().fromArray(pos, 3 * idx[t + 2]);
            const nrm = b.clone().sub(a).cross(c.clone().sub(a));
            // V307/FS-HARİTA-KÜRE: köşeler karo MERKEZİNE göredir (R7 onarımı);
            // "dışarı" sınavı köşenin DÜNYA konumuyla yapılır (normal ötelemeden
            // bağımsızdır, nokta çarpımın ikinci terimi değildir).
            if (nrm.dot(a.clone().add(m.position)) > 0) disari++; else iceri++;
        }
        sonuc.push({ z, disari, iceri, parca: Math.round(Math.sqrt(pos.length / 3)) - 1,
                     factor: m.material.polygonOffsetFactor, units: m.material.polygonOffsetUnits,
                     side: m.material.side === THREE.FrontSide });
    }
    out.sarim = sonuc;
    // K6: uçuşlu viewSite tabanı + yakın bakış sınırı.
    let hedefPos = null, hedefT = null;
    const v = Object.assign(Object.create(P), { camera: new THREE.PerspectiveCamera(38, 1.6, 0.01, 1e5),
        controls: { target: new THREE.Vector3() }, _sitePoint: G.latLonToVec3(28.6, -80.6, 100),
        _flight: { t: [0, 1] }, _pathMid: null });
    v._pathTangent = function (n) { return new THREE.Vector3(0, 1, 0).cross(n).normalize(); };
    v._pathBoundingRadius = function () { return 1500 / (6371000 / 100); };   // 1,5 km'lik yol
    v._flyCameraPos = function (p, t) { hedefPos = p; hedefT = t; };
    v.viewSite();
    out.viewSiteM = hedefPos.distanceTo(hedefT) * 63710;
    v._pathBoundingRadius = function () { return 28.5 / (6371000 / 100); };   // 57 m'lik yol
    v.viewSite();
    out.viewSite57M = hedefPos.distanceTo(hedefT) * 63710;
    v._flight = null; v.viewSite();
    out.viewSiteUcussuzM = hedefPos.distanceTo(hedefT) * 63710;
    process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


@node_gerek
def test_K2_karo_ucgenleri_disari_bakar_ve_egim_yanliligi_yok(tmp_path):
    import os
    js = tmp_path / 'sarim.js'
    js.write_text(SARIM_DUZENEK, encoding='utf-8')
    env = dict(os.environ, DURUM=json.dumps({'tile_matrix': tc.matrix_geometry(),
                                             'layers': tc.list_layers()}))
    r = subprocess.run([NODE, str(js), str(THREE_JS), str(GLOBE), ''], capture_output=True,
                       text=True, timeout=90, env=env)
    assert r.returncode == 0, r.stderr[-2500:]
    out = json.loads(r.stdout)
    for s in out['sarim']:
        # Ölçülen kusur: bütün üçgenler İÇERİ bakıyordu (arka yüz, atılıyordu).
        assert s['iceri'] == 0 and s['disari'] > 0, s
        assert s['side'] is True
        # Eğim yanlılığı NE çizgilerini örtüyordu; yalnız birim yanlılığı kalır.
        assert s['factor'] == 0 and s['units'] < 0, s
    # Kaba karo z7 parça açısıyla bölünür: z5 -> 32, z9/z11 -> 8.
    assert [s['parca'] for s in out['sarim']] == [32, 8, 8]
    # K6: 1,5 km'lik yol artık 191 km tabanına değil kendi çerçevesine göre:
    # 1500/sin(19°)·2,2 = 10,1 km (taban ~21 m).
    assert 9500 < out['viewSiteM'] < 10700, out['viewSiteM']
    # 57 m'lik uçuş (FS-İZLEME ölçümü): ~29 m yarıçap -> 57/2/sin19·2,2 = 193 m.
    assert 150 < out['viewSite57M'] < 250, out['viewSite57M']
    assert abs(out['viewSiteUcussuzM'] - 637100) < 1, out['viewSiteUcussuzM']


def test_K6_yakin_bakis_siniri_near_kuralindan():
    # Kural: near = NEAR_ORANI·mesafe tabana (NEAR_MIN) çarpmadan inilebilen
    # en küçük mesafe = 21,2 m (FS-UÇUŞ 1-20 km, FS-İZLEME birkaç yüz metre).
    src = _oku(GLOBE)
    assert 'var KAMERA_MIN_MESAFE = NEAR_MIN / NEAR_ORANI;' in src
    assert 'var CTRL_MIN_TARGET = KAMERA_MIN_MESAFE;' in src
    assert 'var SURFACE_MIN_LEN = GLOBE_R + KAMERA_MIN_MESAFE;' in src
    assert 'var floor = (this._flight ? CTRL_MIN_TARGET : GLOBE_R * 0.1);' in src
    assert 'var CTRL_MIN_TARGET = GLOBE_R * 0.004' not in src
    assert 'var SURFACE_MIN_LEN = GLOBE_R * 1.003' not in src


def test_K5_riza_notu_i18n_den_ve_rizayi_acmaz():
    src = _oku(GLOBE)
    i = src.index('LaunchSiteGlobe.prototype._detayNotu = function')
    govde = src[i:src.index('\n    };', i)]
    assert "'site.tileDetailOffHint'" in govde and "'site.tileDetailOffButton'" in govde
    assert 'setTileNetwork' not in govde and 'tileAgYaz' not in govde   # rızayı kendisi açmaz
    assert '.checked' not in govde and '.click()' not in govde
    d = _oku(I18N)
    for anahtar in ('site.tileDetailOffHint', 'site.tileDetailOffButton', 'site.tileDetailAttribution',
                    'site.tileDetailMagnified', 'site.mapGeonamesAttribution'):
        assert d.count("'%s':" % anahtar) == 2, anahtar          # EN + TR


# ===========================================================================
# 3) Etiketler — yakın ölçek GeoNames katmanı (K4)
# ===========================================================================

ETIKET_DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), crypto = require('crypto');
const [THREE_JS, GLOBE, ETIKET, DIZIN, GOREV] = process.argv.slice(2);
const gorev = JSON.parse(fs.readFileSync(GOREV, 'utf8'));
const ctx = { console, performance, Math, Promise, setTimeout, JSON, TextDecoder };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(THREE_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(GLOBE, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(ETIKET, 'utf8'), ctx);
const THREE = ctx.THREE, G = ctx.LaunchSiteGlobe, L = ctx.LaunchSiteLabels, R = 100, MPU = 6371000 / 100;
function Oge(tag) { this.tagName = tag; this.style = {}; this.className = ''; this.children = []; this.textContent = ''; }
Oge.prototype.appendChild = function (c) { this.children.push(c); return c; };
const belge = { createElement(tag) { return new Oge(tag); } };
const istek = [];
function dosyaFetch(u) {
    istek.push(path.basename(u));
    const f = path.join(DIZIN, path.basename(u));
    if (!fs.existsSync(f)) return Promise.resolve({ ok: false });
    const b = fs.readFileSync(f), ab = b.buffer.slice(b.byteOffset, b.byteOffset + b.length);
    return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(b.toString('utf8'))),
                             arrayBuffer: () => Promise.resolve(ab) });
}
const ozet = (b) => Promise.resolve(crypto.createHash('sha256').update(Buffer.from(b)).digest('hex'));
function kare(lat, lon, dKm) {
    const W = 1440, H = 900, n = new THREE.Vector3(...G.latLonToXYZ(lat, lon, 1, [0, 0, 0], 0));
    const hedef = n.clone().multiplyScalar(R), dU = dKm * 1000 / MPU;
    const cam = new THREE.PerspectiveCamera(38, W / H, 0.01, 1e5);
    cam.position.copy(hedef.clone().add(n.clone().multiplyScalar(dU)));
    cam.up.set(0, 1, 0); cam.lookAt(hedef); cam.updateMatrixWorld();
    const mpp = 2 * dU * Math.tan(19 * Math.PI / 180) / H * MPU;
    return { camera: cam, metersPerPixel: mpp, zWeb: Math.log2(G.Z_WEB_Z0_MPP / mpp),
             camAltitudeM: dKm * 1000, size: { width: W, height: H }, globeRadius: R };
}
(async () => {
    const l = new L({ container: new Oge('div'), document: belge, latLonToXYZ: G.latLonToXYZ,
                      baseUrl: '/static/map/', fetchImpl: dosyaFetch, digestImpl: ozet,
                      getLang: () => gorev.dil || 'en', measureText: (m) => m.length * 6.6,
                      now: () => 0 });
    await l.start();
    const out = [];
    for (const a of gorev.kareler) {
        l.update(kare(a.lat, a.lon, a.dKm));
        await new Promise(r => setTimeout(r, 50));
        await new Promise(r => setTimeout(r, 50));
        l.invalidate();
        const f = kare(a.lat, a.lon, a.dKm);
        l.update(f);
        out.push({ z: f.zWeb, info: l.getInfo(), yer: l.getPlacements().filter(p => p.tur !== 'country').map(p => p.ad),
                   istek: istek.slice() });
    }
    process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


def _etiket(tmp_path, kareler, dizin=HARITA, dil='en'):
    js = tmp_path / 'etiket.js'
    js.write_text(ETIKET_DUZENEK, encoding='utf-8')
    (tmp_path / 'gorev.json').write_text(json.dumps({'kareler': kareler, 'dil': dil}), encoding='utf-8')
    r = subprocess.run([NODE, str(js), str(THREE_JS), str(GLOBE), str(ETIKET), str(dizin),
                        str(tmp_path / 'gorev.json')], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-2500:]
    return json.loads(r.stdout)


@node_gerek
def test_K4_yakin_olcekte_geonames_etiketleri_gorunur_tekrarsiz(tmp_path):
    out = _etiket(tmp_path, [
        {'lat': IST[0], 'lon': IST[1], 'dKm': 800},    # z_web < 9: katman yüklenmez
        {'lat': IST[0], 'lon': IST[1], 'dKm': 60},     # z_web > 9: yüklenir, görünür
        {'lat': KSC[0], 'lon': KSC[1], 'dKm': 100},   # 76 m/px: Cape Canaveral 297 px güneyde
    ])
    uzak, ist, ksc = out
    assert uzak['z'] < 9 and uzak['info']['detay']['durum'] == 'bekliyor'
    assert 'places_detail_manifest.json' not in uzak['istek']        # tembel: istenmedi
    d = ist['info']['detay']
    assert ist['z'] > 9 and d['durum'] == 'hazir', d
    assert d['yerSayisi'] == 70019 and d['gorunur'] >= 3, (d, ist['yer'])
    assert d['kunye']['shaDogrulandi'] is True and 'CC BY 4.0' in d['kunye']['lisans']
    # NE 'Istanbul' ile GeoNames 'Istanbul' aynı şehir: ekranda bir kez.
    katli = [y.lower() for y in ist['yer']]
    assert katli.count('istanbul') == 1 and d['tekrarGizli'] >= 1, ist['yer']
    # Cape Canaveral'da NE 0 etiket veriyordu (ölçüm once/): artık yerleşimler var.
    assert len(ksc['yer']) >= 2 and 'Cape Canaveral' in ksc['yer'], ksc['yer']


@node_gerek
def test_K4_kanit_tutmazsa_katman_hata_ne_etkilenmez(tmp_path):
    dizin = tmp_path / 'map'
    shutil.copytree(HARITA, dizin, ignore=shutil.ignore_patterns('bm_pyr', 'vectors_*.bin'))
    m = json.loads((dizin / 'places_detail_manifest.json').read_text(encoding='utf-8'))
    m['places_detail']['sha256'] = '0' * 64
    (dizin / 'places_detail_manifest.json').write_text(json.dumps(m), encoding='utf-8')
    out = _etiket(tmp_path, [{'lat': IST[0], 'lon': IST[1], 'dKm': 60}], dizin=dizin)
    d = out[0]['info']['detay']
    assert d['durum'] == 'hata' and 'sha256' in d['hata'], d
    assert out[0]['info']['durum'] == 'hazir' and 'Istanbul' in out[0]['yer']


# ===========================================================================
# 4) Veri künyesi, lisans kapısı, şablon atfı (ana model kararı 9 Kas)
# ===========================================================================

def test_paketli_veri_kanitla_tutarli_ve_en_sade_bicimde():
    man = json.loads(_oku(HARITA / 'places_detail_manifest.json'))
    govde = (HARITA / 'places_detail.json').read_bytes()
    assert man['places_detail'] == {'file': 'places_detail.json', 'bytes': len(govde),
                                    'sha256': hashlib.sha256(govde).hexdigest()}
    assert man['archive_sha256'] == '550ec920954e46b7d2ff004354857383db49db4b07d848a0de80cb07b13117dd'
    assert man['downloaded_utc'] == '2026-11-09T14:28:57Z' and 'CC BY 4.0' in man['license']
    veri = json.loads(govde.decode('utf-8'))
    assert veri['fields'] == ['lon', 'lat', 'name', 'pop', 'cc', 'fcode']
    assert len(veri['rows']) == veri['provenance']['place_count'] == 70019
    pops = [r[3] for r in veri['rows']]
    assert pops == sorted(pops, reverse=True)                          # nüfus azalan
    # Paket boyutu bilinçli: ~3,5 MB (RAPOR'da; ana model onayı 9 Kas).
    assert 3_000_000 < len(govde) < 4_000_000


def test_lisans_kapisi_geonames_verisini_gorur(tmp_path):
    sys.path.insert(0, str(PAKET))
    try:
        import lisans_paketle as LP
    finally:
        sys.path.pop(0)
    bildirim = _oku(PAKET / 'licenses' / 'THIRD_PARTY_NOTICES.txt')
    assert LP.veri_bildirimlerini_denetle(KOK, bildirim) == ['hrma/static/map/places_detail.json']
    assert 'GeoNames' in bildirim and 'CC BY 4.0' in bildirim
    # Ters yön: beyan silinirse paketleme DURUR (fail-closed).
    beyansiz = bildirim.replace('Data: hrma/static/map/places_detail.json', '')
    with pytest.raises(LP.LisansHatasi):
        LP.veri_bildirimlerini_denetle(KOK, beyansiz)
    # Bildirimin andığı veri yoksa da durur.
    kaynak = tmp_path / 'kaynak'
    (kaynak / 'hrma' / 'static' / 'map').mkdir(parents=True)
    with pytest.raises(LP.LisansHatasi):
        LP.veri_bildirimlerini_denetle(kaynak, bildirim)


def test_sablon_geonames_atfi_ve_buyutme_anahtari():
    s = _oku(SABLON)
    i = s.index('function renderMapNotes')
    govde = s[i:s.index('\n    }\n', i)]
    assert "li.detay.gorunur > 0" in govde and "t('site.mapGeonamesAttribution'" in govde
    assert 'geoAtif].join' in govde                       # imza durumu taşır
    assert "landsat_weld: 'site.tileDetailMagnified'" in s


SINIR_DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [THREE_JS, VEKTOR_JS, GLOBE_JS, SINIR_JSON, MODUL] = process.argv.slice(2);
const veri = JSON.parse(fs.readFileSync(SINIR_JSON, 'utf8'));
const ctx = { console, Math, JSON, Promise, setTimeout, performance: { now: () => 0 },
              fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(veri) }) };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(THREE_JS, 'utf8'), ctx);
if (MODUL === '1') vm.runInContext(fs.readFileSync(VEKTOR_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(GLOBE_JS, 'utf8'), ctx);
const THREE = ctx.THREE, G = ctx.LaunchSiteGlobe, R = 100, MPU = 6371000 / 100;
(async () => {
    const k = Object.assign(Object.create(G.prototype), { opts: {}, scene: new THREE.Scene(), _frameListeners: [] });
    k._buildBorders();
    await new Promise(r => setTimeout(r, 20));
    let enSarkma = 0, rMin = Infinity, rMax = 0, parca = 0;
    k.bordersGroup.children.forEach(ls => {
        const p = ls.geometry.getAttribute('position').array;
        for (let i = 0; i < p.length; i += 6) {
            const a = new THREE.Vector3(p[i], p[i + 1], p[i + 2]), b = new THREE.Vector3(p[i + 3], p[i + 4], p[i + 5]);
            const ra = a.length(); rMin = Math.min(rMin, ra); rMax = Math.max(rMax, ra);
            const orta = a.clone().add(b).multiplyScalar(0.5).length();
            enSarkma = Math.max(enSarkma, (ra - orta) * MPU); parca++;
        }
    });
    const f = { camAltitudeM: 200000 };
    k._frameListeners.forEach(fn => fn(f));
    process.stdout.write(JSON.stringify({ enSarkma, rMinM: (rMin - R) * MPU, rMaxM: (rMax - R) * MPU, parca,
        olcekM: (k.bordersGroup.scale.x - 1) * 6371000, dinleyici: k._frameListeners.length }));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


@node_gerek
def test_FS_IZLEME_yedek_sinir_cizgisi_yuzeye_iner(tmp_path):
    js = tmp_path / 'sinir.js'
    js.write_text(SINIR_DUZENEK, encoding='utf-8')
    arg = [NODE, str(js), str(THREE_JS), str(JS / 'launch_site_vectors.js'), str(GLOBE),
           str(KOK / 'hrma' / 'static' / 'img' / 'earth_borders.json')]
    r = subprocess.run(arg + ['1'], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2500:]
    o = json.loads(r.stdout)
    # Eskiden 1,001R = 6.371 m yukarıda; en uzun kiriş 7.852 m sarkıyordu.
    assert abs(o['rMinM']) < 0.5 and abs(o['rMaxM']) < 0.5, o      # yüzeyde kurulur
    # Kiriş sarkması <= kaldırma tabanı (2 m); pay Float32 köşe nicemlemesidir
    # (100 birim · 2^-24 ≈ 6e-6 birim ≈ 0,38 m/bileşen).
    assert o['enSarkma'] <= 2.0 + 0.5, o
    assert o['parca'] > 50000, o
    # Her karede vektör modülünün kuralıyla kaldırılır: 200 km -> 20 m.
    assert abs(o['olcekM'] - 20.0) < 0.01 and o['dinleyici'] == 1, o
    # Vektör modülü yoksa kural okunamaz: eski 1,001R kurulumu.
    r = subprocess.run(arg + ['0'], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2500:]
    o = json.loads(r.stdout)
    assert abs(o['rMinM'] - 6371.0) < 1.0 and o['dinleyici'] == 0, o
