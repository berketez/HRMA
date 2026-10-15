"""Harita ayrıntısı F1 vektör basamaklarının bekçileri (K2, 7 Eki 2026).

Kod: ``hrma/static/js/launch_site_vectors.js`` (yeni) ve
``hrma/static/js/launch_site_globe.js`` (kare kancası, dinamik near, 110m
yedeği, karo LRU tavanı). Tasarım:
``docs/scofield/raw/OH/UI/harita-detay/tasarim.md`` §3.1, §3.2, §3.4, §3.5, §6.

Bekçilerin yakaladığı arıza sınıfları:

* **Basamak kayması.** m/px eşikleri (20.000 / 5.000) ve ±%10 histerezis
  tasarımdaki tablodan sapar ya da eşikte titreme döner.
* **Uydurma süzgeç.** Çizgi süzgeci NE'nin kendi ``min_zoom`` alanı değilse,
  "alan yok" (255) çizgileri kaybolursa ya da süzgeç çizgileri karıştırırsa.
* **Arka yüz.** Ufkun arkasındaki hücre çizilirse (ya da kaldırılmış çizginin
  ufuk ötesi payı unutulursa).
* **Kanıtsız varlık.** İmzası, boyutu, sha256'sı ya da blok sınırı tutmayan
  ikili çizilirse; 110m yüklenemezken eski görünüm kaybolursa.
* **Kanca ve near.** Kare kancası yükü getScaleInfo ile ayrışırsa; near
  sabit kalırsa ya da hedefe yakın nesneyi kıracak kadar büyürse.

Küçük sentetik HMV1 girdileri TEST ALTYAPISIDIR (fixture); K1 aracının kendi
yazıcısıyla üretilir, kullanıcıya gösterilen veri değildir.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import re
import shutil
import struct
import subprocess
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
for _yol in (str(KOK), str(KOK / 'tools')):
    if _yol not in sys.path:
        sys.path.insert(0, _yol)

import build_map_detail_assets as hat  # noqa: E402

JS = KOK / 'hrma' / 'static' / 'js'
GLOBE = JS / 'launch_site_globe.js'
VEKTOR = JS / 'launch_site_vectors.js'
THREE_JS = KOK / 'hrma' / 'static' / 'vendor' / 'three-0.128.0.min.js'
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
VARLIK_DIZIN = KOK / 'hrma' / 'static' / 'map'
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

R_EARTH_M = 6371000.0
M_PER_UNIT = R_EARTH_M / 100.0


def _oku(yol: pathlib.Path) -> str:
    return yol.read_text(encoding='utf-8')


def _kod(src: str) -> str:
    """Yorum satırlarını ve blok yorumlarını atar (bekçi kodu ölçsün)."""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return '\n'.join(s for s in src.splitlines() if not s.strip().startswith('//'))


def _govde(src: str, ad: str) -> str:
    m = re.search(r'LaunchSiteGlobe\.prototype\.%s = function \(.*?\n    \};' % re.escape(ad),
                  src, re.S)
    assert m, '%s gövdesi bulunamadı' % ad
    return m.group(0)


# ---------------------------------------------------------------------------
# Node düzeneği: three r128 + modüller bir vm bağlamında, ağ yerine dosya
# ---------------------------------------------------------------------------
DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), crypto = require('crypto');
const [THREE_JS, VEKTOR, GLOBE, GOREV] = process.argv.slice(2);
const gorev = JSON.parse(fs.readFileSync(GOREV, 'utf8'));
const ctx = { console, performance, Math, Promise, setTimeout, JSON };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(THREE_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(VEKTOR, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(GLOBE, 'utf8'), ctx);
const THREE = ctx.THREE, V = ctx.LaunchSiteVectors, G = ctx.LaunchSiteGlobe;
const R = 100, MPU = 6371000 / 100;

function dosyaFetch(kok, sayac) {
    return (u) => {
        if (sayac) sayac.push(path.basename(u));
        const f = path.join(kok, path.basename(u));
        if (!fs.existsSync(f)) return Promise.resolve({ ok: false });
        const b = fs.readFileSync(f);
        const ab = b.buffer.slice(b.byteOffset, b.byteOffset + b.length);
        return Promise.resolve({ ok: true,
            json: () => Promise.resolve(JSON.parse(b.toString('utf8'))),
            arrayBuffer: () => Promise.resolve(ab) });
    };
}
const ozet = (b) => Promise.resolve(crypto.createHash('sha256').update(Buffer.from(b)).digest('hex'));

function kamera(lat, lon, altM) {
    const cam = new THREE.PerspectiveCamera(38, 1.6, 0.01, 1e5);
    const p = G.latLonToXYZ(lat, lon, R + altM / MPU, [0, 0, 0], 0);
    cam.position.set(p[0], p[1], p[2]);
    cam.lookAt(0, 0, 0);
    cam.updateMatrixWorld();
    return cam;
}
function kare(k) {
    const mpp = k.mpp;
    return { camera: kamera(k.lat, k.lon, k.alt), target: new THREE.Vector3(),
             metersPerPixel: mpp, zWeb: Math.log2(G.Z_WEB_Z0_MPP / mpp),
             camAltitudeM: k.alt, size: { width: 1440, height: 900 }, globeRadius: R };
}
const bekle = (ms) => new Promise(r => setTimeout(r, ms));

function kur(kok, ek) {
    const scene = new THREE.Scene(), olaylar = [], istekler = [];
    const o = Object.assign({ THREE, scene, latLonToXYZ: G.latLonToXYZ,
        srgb: (h) => new THREE.Color(h).convertSRGBToLinear(),
        globeRadius: R, rEarthM: 6371000, baseUrl: '/static/map/',
        fetchImpl: dosyaFetch(kok, istekler), digestImpl: ozet,
        onReady: () => olaylar.push('hazir'), onFail: (e) => olaylar.push('hata:' + e) }, ek || {});
    return { v: new V(o), scene, olaylar, istekler };
}

function hucreDokumu(v) {
    const out = [];
    for (const ad of Object.keys(v.seviyeler)) {
        const sv = v.seviyeler[ad];
        if (!sv.hucreler) continue;
        for (const h of sv.hucreler) {
            if (!h.mesh) continue;
            out.push({ seviye: ad, katman: h.katman, hucre: h.meta.cell,
                       grupGorunur: sv.grup.visible, gorunur: h.mesh.visible,
                       ciz: h.mesh.geometry.drawRange.count,
                       toplam: h.mesh.geometry.attributes.position.count,
                       esikler: h.esikler, kumulatif: h.kumulatif });
        }
    }
    return out;
}

async function senaryo(g) {
    const { v, olaylar, istekler, scene } = kur(g.kok, g.digestYok ? { digestImpl: null } : null);
    if (g.digestYok) v._digest = null;
    await v.start();
    await bekle(5);
    const sonuc = [];
    for (const k of g.kareler) {
        for (let i = 0; i < (k.tekrar || 40); i++) { v.update(kare(k)); if (i % 10 === 9) await bekle(2); }
        const info = v.getInfo();
        sonuc.push({ info, hucreler: g.dokum ? hucreDokumu(v) : null, olcek: v.kok.scale.x });
    }
    const kokVar = scene.children.indexOf(v.kok) >= 0;
    v.dispose();
    return { olaylar, istekler, sonuc, kokVar, kokSonra: scene.children.indexOf(v.kok) >= 0 };
}

function saf() {
    const L = V.lodSec;
    const tek = [30000, 20001, 19999, 15000, 5001, 4999, 100, 29].map(m => L(m, null));
    // Histerezis: 110m'den inceye 18.000'in altında, 50m'den kabaya 22.000'in üstünde.
    const h = [[110, 18500, '110m'], [110, 17900, '50m'], [50, 21900, '50m'], [50, 22100, '110m'],
               [50, 4600, '50m'], [50, 4400, '10m'], [10, 5400, '10m'], [10, 5600, '50m'],
               [110, 100, '10m'], [10, 30000, '110m']];
    const hs = h.map(([o, m]) => L(m, o + 'm'));
    const kald = [0, 19000, 100000, 1.5e6, 1.8e7].map(a => V.kaldirmaOlcegi(a, 6371000));
    // Ufuk: Türkiye hücresi (bbox 30..40E, 36..42N) Sinop üstünden görünür,
    // karşı yarıküreden (lon -145) görünmez; tarih çizgisi kutusu her zaman aday.
    const kap = V.hucreKapagi([30, 36, 40, 42]);
    const cam = (lat, lon, alt) => { const p = G.latLonToXYZ(lat, lon, R + alt / MPU, [0, 0, 0], 0);
                                      return { x: p[0], y: p[1], z: p[2] }; };
    const uf = {
        ustten: V.ufuktaGorunur(kap, cam(42, 35, 4e5), R, 1),
        karsi: V.ufuktaGorunur(kap, cam(-42, -145, 4e5), R, 1),
        sinir_disi: V.ufuktaGorunur(kap, cam(42, 35 + 70, 1e6), R, 1),
        tarih: V.hucreKapagi([-180, 54, 180, 71]) === null,
    };
    // Kaldırma payı: ufuk ötesindeki kenar, yalnız kaldırma açısıyla görünür.
    const dar = V.hucreKapagi([0, -0.001, 0.001, 0.001]);
    const altM = 4e5, d = R + altM / MPU, teta = Math.acos(R / d);
    const pay = Math.acos(1 / V.kaldirmaOlcegi(1.8e7, 6371000));
    const lon = (teta + dar.alfa + pay * 0.5) * 180 / Math.PI;
    const c2 = cam(0, -lon, altM);
    const kaldirma = [V.ufuktaGorunur(dar, c2, R, 1), V.ufuktaGorunur(dar, c2, R, V.kaldirmaOlcegi(1.8e7, 6371000))];
    // latLonToXYZ ile latLonToVec3 aynı formül (tek sahip)
    const v3 = G.latLonToVec3(41.0, 28.97, 100.2), x = G.latLonToXYZ(41.0, 28.97, 100.2, [0, 0, 0], 0);
    return { tek, hs, kald, uf, kaldirma, ayni: [v3.x - x[0], v3.y - x[1], v3.z - x[2]],
             esik: V.BASAMAKLAR.map(b => [b.ad, b.mppUst]), hist: V.LOD_HISTEREZIS,
             z0: G.Z_WEB_Z0_MPP };
}

function kure() {
    // Prototip yöntemleri sahte nesnelerle: near, kanca, m/px tek formül, yedek.
    const P = G.prototype;
    const near = [];
    for (const [altU, dT] of [[180, 280], [23.5, 30], [0.3, 0.4], [0.3, 0.05], [1e-4, 0.4]]) {
        const cam = new THREE.PerspectiveCamera(38, 1.6, 0.01, 1e5);
        cam.position.set(0, 0, R + altU);
        const tgt = new THREE.Vector3(0, 0, R + altU - dT);
        const ben = { camera: cam, controls: { target: tgt } };
        P._updateNear.call(ben);
        near.push([cam.near, cam.projectionMatrix.elements[10]]);
    }
    const cam = new THREE.PerspectiveCamera(38, 1.6, 0.01, 1e5);
    cam.position.set(0, 0, 130);
    const ben = { camera: cam, controls: { target: new THREE.Vector3(0, 0, 100) },
                  container: { clientWidth: 1440, clientHeight: 900 },
                  _frameListeners: [], _tiles: new Map() };
    ben._metersPerPixel = P._metersPerPixel;
    ben._drawnTileCount = P._drawnTileCount;
    const gelen = [];
    const kaldir = P.addFrameListener.call(ben, (f) => gelen.push([f.metersPerPixel, f.zWeb,
        f.camAltitudeM, f.size.width, f.size.height, f.globeRadius, f.camera === cam]));
    P.addFrameListener.call(ben, () => { throw new Error('bozuk dinleyici'); });
    const hataSus = ctx.console.error; ctx.console.error = () => {};
    P._emitFrame.call(ben);
    const sonraSayi = ben._frameListeners.length;
    P._emitFrame.call(ben);
    ctx.console.error = hataSus;
    kaldir();
    P._emitFrame.call(ben);
    const olcek = P.getScaleInfo.call(ben);
    // Yedek: vektör onFail eski bindirmeyi geri açar, onReady gizler.
    let yaratilan = null;
    const sahte = function (o) { yaratilan = o; this.update = () => {}; this.start = () => {};
                                  this.getInfo = () => ({ durum: 'x' }); };
    ctx.LaunchSiteVectors = sahte;
    const k = { opts: {}, scene: new THREE.Scene(), _frameListeners: [],
                bordersGroup: { visible: true } };
    k.addFrameListener = P.addFrameListener;
    P._buildVectorLOD.call(k);
    const once = k.bordersGroup.visible;
    yaratilan.onReady();
    const hazirda = [k.bordersGroup.visible, k._vectorsReady];
    yaratilan.onFail('deneme');
    const hatada = [k.bordersGroup.visible, k._vectorsReady];
    ctx.LaunchSiteVectors = undefined;
    const k2 = { opts: {}, scene: new THREE.Scene(), _frameListeners: [], bordersGroup: { visible: true } };
    k2.addFrameListener = P.addFrameListener;
    P._buildVectorLOD.call(k2);
    const modulsuz = [k2._vectors === undefined || k2._vectors === null, k2.bordersGroup.visible,
                      P.getVectorInfo.call(k2)];
    return { near, gelen, sonraSayi, olcek, once, hazirda, hatada, modulsuz,
             baseUrl: yaratilan.baseUrl, yaricap: yaratilan.globeRadius,
             ayniXYZ: yaratilan.latLonToXYZ === G.latLonToXYZ };
}

(async () => {
    let r;
    if (gorev.tur === 'saf') r = saf();
    else if (gorev.tur === 'kure') r = kure();
    else r = await senaryo(gorev);
    process.stdout.write(JSON.stringify(r));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""


def _kos(tmp_path: pathlib.Path, gorev: dict, globe: pathlib.Path = GLOBE,
         vektor: pathlib.Path = VEKTOR) -> dict:
    d = tmp_path / 'duzenek.js'
    d.write_text(DUZENEK, encoding='utf-8')
    g = tmp_path / ('gorev_%d.json' % len(list(tmp_path.glob('gorev_*.json'))))
    g.write_text(json.dumps(gorev), encoding='utf-8')
    r = subprocess.run([NODE, str(d), str(THREE_JS), str(vektor), str(globe), str(g)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


# ---------------------------------------------------------------------------
# Sentetik HMV1 varlık seti (K1 aracının KENDİ yazıcısıyla)
# ---------------------------------------------------------------------------
def _toplayici(cizgiler):
    t = hat.KatmanToplayici()
    for koordinatlar, mz in cizgiler:
        t.ekle(koordinatlar, mz)
    return t


# z3 hücresi x=5, y=1 (boylam 0..36°D, enlem 18..54°K) içinde dört kıyı
# çizgisi; hepsi 36°D'nin batısında, yani hücre bölmesine uğramaz. min_zoom
# 255 (alan yok), 0, 3,0 ve 6,0; bir il sınırı (7,0). Karşı yarıkürede
# (lon -145) bir çizgi.
SENTETIK_10M = {
    'coastline': [
        ([(30.0, 40.0), (31.0, 40.5), (32.0, 41.0)], 60),
        ([(33.0, 41.0), (34.0, 41.5)], hat.MIN_ZOOM_YOK),
        ([(34.2, 41.0), (34.8, 41.2), (35.3, 41.4), (35.8, 41.0)], 30),
        ([(30.0, 37.0), (31.0, 37.5)], 0),
        ([(-145.0, 40.0), (-144.5, 40.5)], 0),
    ],
    'admin1': [
        ([(33.0, 39.0), (34.0, 39.5)], 70),
    ],
}


def _sentetik_varliklar(kok: pathlib.Path, bozuk: str = '') -> pathlib.Path:
    kok.mkdir(parents=True, exist_ok=True)
    tum = [([(30.0, 40.0), (32.0, 41.0)], hat.MIN_ZOOM_YOK)]
    seviyeler = {}
    for ad, katmanlar in (('110m', {'coastline': tum}),
                          ('50m', {'coastline': tum, 'borders': tum}),
                          ('10m', SENTETIK_10M)):
        veri, ozet = hat.basamak_ikilisi({k: _toplayici(c) for k, c in katmanlar.items()})
        dosya = 'vectors_%s.bin' % ad
        sha = hashlib.sha256(veri).hexdigest()
        if bozuk == 'sha_' + ad:
            sha = '0' * 64
        if bozuk == 'imza_' + ad:
            veri = b'XXXX' + veri[4:]
        if bozuk == 'tasma_' + ad:
            ozet['layers'][next(iter(ozet['layers']))]['cells'][0]['vertex_count'] += 10_000
        if bozuk == 'eksik_' + ad:
            veri = None
        if bozuk == 'cizgi_' + ad:
            # İlk hücrenin ilk çizgi uzunluğu +1: toplam köşe sayısını tutmaz.
            # sha256 bozuk ikiliden yeniden hesaplanır; ret YALNIZ çizgi
            # toplamı denetiminden gelebilsin (F1 denetimi D7).
            h0 = ozet['layers'][next(iter(ozet['layers']))]['cells'][0]
            o = h0['offset'] + 8 * h0['vertex_count']
            veri = bytearray(veri)
            struct.pack_into('<I', veri, o, struct.unpack_from('<I', veri, o)[0] + 1)
            veri = bytes(veri)
            sha = hashlib.sha256(veri).hexdigest()
        if veri is not None:
            (kok / dosya).write_bytes(veri)
        seviyeler[ad] = dict(file=dosya, bytes=len(veri) if veri else 0, sha256=sha,
                             nominal_scale='1:%s' % ad, **ozet)
    manifest = {
        'format': 'HMV1', 'byte_order': 'little',
        'coord_scale': hat.KOORDINAT_OLCEGI, 'min_zoom_scale': hat.MIN_ZOOM_OLCEGI,
        'min_zoom_absent': hat.MIN_ZOOM_YOK, 'levels': seviyeler,
        'provenance': {'attribution': hat.NE_ATIF, 'boundary_view': hat.SINIR_GORUNUMU},
    }
    if bozuk != 'manifest_yok':
        (kok / 'vectors_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return kok


# m/px'ten kare: z_web = log2(156543,03 / mpp)
def _kare(lat, lon, alt, mpp, tekrar=40):
    return {'lat': lat, 'lon': lon, 'alt': alt, 'mpp': mpp, 'tekrar': tekrar}


# ===========================================================================
# 1) Kaynak sözleşmesi (globe.js tek sahip)
# ===========================================================================

def test_karo_lru_tavani_64():
    """Tasarım §3.4: 128 karo ~179 MB GPU; 64 karo ~90 MB."""
    m = re.search(r'var TILE_LRU_MAX = (\d+);', _oku(GLOBE))
    assert m and int(m.group(1)) == 64, 'TILE_LRU_MAX 64 değil'


def test_en_yakin_hedef_yorumu_25_5_km():
    """CTRL_MIN_TARGET = 0,4 birim = 25.484 m; eski yorum '2.5 km' diyordu."""
    src = _oku(GLOBE)
    satir = [s for s in src.splitlines() if 'var CTRL_MIN_TARGET' in s]
    assert len(satir) == 1
    assert '25,5 km' in satir[0] and '2.5 km' not in satir[0], satir[0]
    m = re.search(r'var CTRL_MIN_TARGET = GLOBE_R \* ([0-9.]+);', src)
    assert abs(float(m.group(1)) * 100 * M_PER_UNIT - 25484) < 1


def test_eski_110m_yedegi_korunuyor():
    """_buildBorders hâlâ earth_borders.json okur ve vektör hazırsa gizli doğar."""
    src = _oku(GLOBE)
    b = _kod(_govde(src, '_buildBorders'))
    assert "/static/img/earth_borders.json" in b
    assert 'group.visible = !self._vectorsReady' in b, 'yedek görünürlüğü vektör durumuna bağlı değil'
    init = _kod(_govde(src, '_init'))
    i_sinir, i_vektor = init.find('this._buildBorders()'), init.find('this._buildVectorLOD()')
    assert 0 <= i_sinir < i_vektor, 'yedek bindirme vektör katmanından önce kurulmalı'
    assert (KOK / 'hrma' / 'static' / 'img' / 'earth_borders.json').is_file()


def test_kare_dongusu_near_ve_kanca_cizimden_once():
    """Near ve kanca, kamera SON konumundayken (kilit sonrası) ve çizimden önce."""
    dongu = _kod(_govde(_oku(GLOBE), '_animate'))
    sira = [dongu.find(s) for s in ('self.controls.update()', 'SURFACE_MIN_LEN',
                                     'self._updateNear()', 'self._emitFrame()',
                                     'self.renderer.render(')]
    assert all(i >= 0 for i in sira), sira
    assert sira == sorted(sira), 'sıra bozuk: kilit -> near -> kanca -> çizim olmalı'


def test_sablon_vektor_modulunu_kureden_once_yukler():
    s = _oku(SABLON)
    i_three = s.find('/static/vendor/three-0.128.0.min.js')
    i_vek = s.find('/static/js/launch_site_vectors.js')
    i_kure = s.find('/static/js/launch_site_globe.js"></script>')
    assert 0 <= i_three < i_vek < i_kure, (i_three, i_vek, i_kure)


def test_vektor_modulu_yeni_kutuphane_ve_ag_hostu_kullanmaz():
    """three r128 sabit; modül yalnız aynı kökten /static/map/ okur."""
    kod = _kod(_oku(VEKTOR))
    assert not re.search(r'https?://', kod), 'vektör modülünde dış host'
    assert 'import ' not in kod and 'require(' not in kod
    assert "'/static/map/'" in kod
    # Renkler lineere çevrilir (P12aB4-20): stil tablosu srgb() üzerinden.
    assert 'this.opts.srgb(stil.renk)' in kod


# ===========================================================================
# 2) Saf yardımcılar (node)
# ===========================================================================

@node_gerek
def test_basamak_esikleri_ve_histerezis(tmp_path):
    r = _kos(tmp_path, {'tur': 'saf'})
    # İlk basamağın üst sınırı Infinity'dir (JSON'da null).
    assert r['esik'] == [['110m', None], ['50m', 20000.0], ['10m', 5000.0]]
    assert r['hist'] == pytest.approx(0.10)
    assert r['tek'] == ['110m', '110m', '50m', '50m', '50m', '10m', '10m', '10m']
    assert r['hs'] == ['110m', '50m', '50m', '110m', '50m', '10m', '10m', '50m', '10m', '110m']
    assert r['z0'] == pytest.approx(156543.03)


@node_gerek
def test_kaldirma_olcegi_iki_metre_ya_da_irtifa_orani(tmp_path):
    r = _kos(tmp_path, {'tur': 'saf'})
    beklenen_m = [2.0, 2.0, 10.0, 150.0, 1800.0]
    for olcek, m in zip(r['kald'], beklenen_m):
        assert (olcek - 1.0) * R_EARTH_M == pytest.approx(m, rel=1e-6)


@node_gerek
def test_ufuk_ayiklama_ve_kaldirma_payi(tmp_path):
    r = _kos(tmp_path, {'tur': 'saf'})
    assert r['uf'] == {'ustten': True, 'karsi': False, 'sinir_disi': False, 'tarih': True}
    # Kaldırma payı yokken görünmeyen kenar, kaldırılmış çizgide görünür.
    assert r['kaldirma'] == [False, True]
    assert max(abs(x) for x in r['ayni']) == 0.0


# ===========================================================================
# 3) Küre kancası, near, yedek (node, prototip yöntemleri)
# ===========================================================================

@node_gerek
def test_dinamik_near(tmp_path):
    r = _kos(tmp_path, {'tur': 'kure'})
    near = [n for n, _ in r['near']]
    # tüm Dünya: üst sınır 1; 1.500 km: 0,3·23,5 > 1 -> 1; en yakın: 0,3·0,3;
    # hedef kameraya çok yakınken hedef mesafesi bağlar; alt sınır 1e-4.
    assert near == pytest.approx([1.0, 1.0, 0.09, 0.015, 1e-4], rel=1e-6)
    # izdüşüm matrisi yeni near ile kurulmuş (eski 0,01 değil)
    for (n, e10) in r['near']:
        far = 1e5
        assert e10 == pytest.approx(-(far + n) / (far - n), rel=1e-6)


@node_gerek
def test_kare_kancasi_yuku_tek_formul(tmp_path):
    r = _kos(tmp_path, {'tur': 'kure'})
    assert len(r['gelen']) == 2, 'kaldırılan dinleyici çağrılmaya devam ediyor'
    mpp, z, alt, w, h, gr, ayni = r['gelen'][0]
    beklenen = 2 * 30 * __import__('math').tan(__import__('math').radians(19)) / 900 * M_PER_UNIT
    assert mpp == pytest.approx(beklenen, rel=1e-9)
    assert mpp == pytest.approx(r['olcek']['metersPerPixel'], rel=1e-12), \
        'kanca yükü ile getScaleInfo ayrışıyor'
    assert z == pytest.approx(__import__('math').log2(156543.03 / mpp))
    assert alt == pytest.approx(30 * M_PER_UNIT)
    assert (w, h, gr, ayni) == (1440, 900, 100, True)
    assert r['sonraSayi'] == 1, 'hata atan dinleyici çıkarılmadı'


@node_gerek
def test_vektor_yedegi_ve_baglanti(tmp_path):
    r = _kos(tmp_path, {'tur': 'kure'})
    assert r['once'] is True, 'vektör hazır olmadan eski görünüm gizlenmiş'
    assert r['hazirda'] == [False, True]
    assert r['hatada'] == [True, False], 'vektör hatasında eski 110m görünümü geri gelmiyor'
    assert r['modulsuz'][0] and r['modulsuz'][1] is True
    assert r['modulsuz'][2]['durum'] == 'yok'
    assert r['baseUrl'] == '/static/map/' and r['yaricap'] == 100 and r['ayniXYZ'] is True


# ===========================================================================
# 4) Modül uçtan uca, sentetik HMV1 (node)
# ===========================================================================

@node_gerek
def test_min_zoom_suzgeci_drawrange_ile(tmp_path):
    kok = _sentetik_varliklar(tmp_path / 'map')
    # Sinop üstü, 10m basamağı, mpp 4000 -> z_web = log2(156543,03/4000) = 5,29.
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(40, 33, 1e6, 4000.0)],
                        'dokum': True})
    tr = [h for h in r['sonuc'][0]['hucreler']
          if h['seviye'] == '10m' and h['katman'] == 'coastline' and h['hucre'] == [5, 1]]
    assert len(tr) == 1
    h = tr[0]
    # 255 (alan yok) ve 0 aynı ilk kovada; sonra 30 ve 60.
    assert h['esikler'] == [0, 30, 60]
    # Kesim başına 2 köşe: 0-kovası (255 ve 0, birer kesim) 4; 30 (3 kesim)
    # +6 = 10; 60 (2 kesim) +4 = 14.
    assert h['kumulatif'] == [4, 10, 14]
    assert h['toplam'] == 14
    # z_web 5,29: 0 ve 3,0 görünür, 6,0 değil
    assert h['ciz'] == 10 and h['gorunur'] is True


@node_gerek
def test_min_zoom_esigi_z_web_ile_kayar(tmp_path):
    kok = _sentetik_varliklar(tmp_path / 'map')
    # 10m basamağında kalan mpp'ler: z_web 5,4 / 6,5 / 9,0
    # Kamera 1.000 km'de (40N, 33E): sentetik çizgilerin hepsi görüş alanında;
    # basamak ve süzgeç yalnız verilen m/px'ten gelir.
    kareler = [_kare(40, 33, 1e6, m) for m in (3700.0, 1722.0, 306.0)]
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': kareler, 'dokum': True})
    ciz = []
    for s in r['sonuc']:
        h = [x for x in s['hucreler'] if x['seviye'] == '10m'
             and x['katman'] == 'coastline' and x['hucre'] == [5, 1]][0]
        a = [x for x in s['hucreler'] if x['seviye'] == '10m' and x['katman'] == 'admin1'][0]
        ciz.append((h['ciz'], a['ciz'], a['gorunur']))
    assert ciz == [(10, 0, False), (14, 0, False), (14, 2, True)], ciz


@node_gerek
def test_arka_yuz_hucresi_cizilmez(tmp_path):
    kok = _sentetik_varliklar(tmp_path / 'map')
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(40, 33, 4e5, 459.0)], 'dokum': True})
    karsi = [h for h in r['sonuc'][0]['hucreler'] if h['seviye'] == '10m' and h['hucre'][0] == 0]
    # Görünür olmayan hücre KURULMAZ bile (geometri belleği harcanmaz).
    assert karsi == [], karsi
    info = r['sonuc'][0]['info']
    assert info['goster'] == '10m' and info['cizilenHucre'] == 2


@node_gerek
def test_basamak_gecisi_ve_olcek(tmp_path):
    kok = _sentetik_varliklar(tmp_path / 'map')
    kareler = [_kare(42, 35, 1.8e7, 20774.0), _kare(42, 35, 5e6, 13850.0),
               _kare(42, 35, 4e5, 459.0), _kare(42, 35, 1.8e7, 23000.0)]
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': kareler})
    gos = [s['info']['goster'] for s in r['sonuc']]
    assert gos == ['110m', '50m', '10m', '110m'], gos
    olc = [s['olcek'] for s in r['sonuc']]
    assert (olc[0] - 1) * R_EARTH_M == pytest.approx(1800.0)
    assert (olc[2] - 1) * R_EARTH_M == pytest.approx(40.0)
    assert r['sonuc'][2]['info']['nominalScale'] == '1:10m'
    assert r['olaylar'] == ['hazir']
    assert r['kokVar'] is True and r['kokSonra'] is False, 'dispose sahneyi temizlemedi'
    # sha256 doğrulandı (kanıtlı yükleme)
    assert all(s['shaDogrulandi'] for s in r['sonuc'][2]['info']['seviyeler'].values())


@node_gerek
def test_on_yukleme_10m_yalniz_yakinlasinca(tmp_path):
    """10m (~11 MB) açılışta indirilmez; 50m ekrana gelince önden istenir."""
    kok = _sentetik_varliklar(tmp_path / 'map')
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(42, 35, 1.8e7, 25000.0)]})
    assert 'vectors_10m.bin' not in r['istekler'], r['istekler']
    r2 = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(42, 35, 5e6, 13850.0)]})
    assert 'vectors_10m.bin' in r2['istekler']


@node_gerek
@pytest.mark.parametrize('bozuk,neden', [('sha_10m', 'sha256'), ('imza_10m', 'imza'),
                                         ('tasma_10m', 'tasma'), ('eksik_10m', 'http'),
                                         ('cizgi_10m', 'cizgi_toplami')])
def test_bozuk_ince_basamak_reddedilir_kaba_kalir(tmp_path, bozuk, neden):
    kok = _sentetik_varliklar(tmp_path / 'map', bozuk=bozuk)
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(42, 35, 4e5, 459.0)]})
    info = r['sonuc'][0]['info']
    assert info['seviyeler']['10m']['durum'] == 'hata'
    # Ret nedeni adıyla beyan edilir (tipli dizi taşma hatasına bırakılmaz).
    assert info['seviyeler']['10m']['hata'] == neden
    assert info['hedef'] == '10m' and info['goster'] == '50m', info
    assert r['olaylar'] == ['hazir']


@node_gerek
@pytest.mark.parametrize('bozuk', ['manifest_yok', 'sha_110m', 'imza_110m', 'eksik_110m'])
def test_temel_basamak_yoksa_eski_gorunume_doner(tmp_path, bozuk):
    kok = _sentetik_varliklar(tmp_path / 'map', bozuk=bozuk)
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(42, 35, 4e5, 459.0)]})
    assert len(r['olaylar']) == 1 and r['olaylar'][0].startswith('hata:'), r['olaylar']
    assert r['sonuc'][0]['info']['durum'] == 'hata'
    assert r['sonuc'][0]['info']['cizilenHucre'] == 0


@node_gerek
def test_sha_dogrulayicisi_yoksa_durum_dogru_beyan_edilir(tmp_path):
    kok = _sentetik_varliklar(tmp_path / 'map')
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(42, 35, 4e5, 459.0)],
                        'digestYok': True})
    sv = r['sonuc'][0]['info']['seviyeler']
    assert sv['10m']['durum'] == 'yuklu' and sv['10m']['shaDogrulandi'] is False


# ===========================================================================
# 5) Gerçek NE varlıklarıyla (depoda varsa onlar; yoksa ham kaynaktan üretim)
# ===========================================================================

def _gercek_varliklar(tmp_path: pathlib.Path) -> pathlib.Path:
    if (VARLIK_DIZIN / 'vectors_manifest.json').is_file():
        return VARLIK_DIZIN
    if not (hat.VARSAYILAN_KAYNAK / hat.SHA_LISTESI).is_file():
        pytest.skip('hrma/static/map yok ve ham NE kaynağı bu makinede yok; '
                    'gerçek veri senaryosu koşulamadı (yapım girdisi, docs kanıtı değil)')
    # Bütçe bir PAKETLEME kararıdır (K1 devri, ana model); çizim davranışını
    # sınamak için çıktı geçici dizine bütçe dışı üretilir, depoya yazılmaz.
    dosyalar, _ = hat.uret(hat.VARSAYILAN_KAYNAK, butce=10 ** 9)
    hedef = tmp_path / 'map'
    hat.yaz(dosyalar, hedef)
    return hedef


@node_gerek
def test_gercek_ne_sinop_yakininda_il_siniri_ve_butce(tmp_path):
    kok = _gercek_varliklar(tmp_path)
    kareler = [_kare(42.0, 35.1, 1.8e7, 20774.0, 5), _kare(42.0, 35.1, 1.5e6, 1722.0, 200),
               _kare(42.0, 35.1, 4e5, 459.0, 200), _kare(42.0, 35.1, 2.5e4, 29.0, 200)]
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': kareler, 'dokum': True})
    assert r['olaylar'] == ['hazir']
    s0, s1, s2, s3 = r['sonuc']
    assert s0['info']['goster'] == '110m'
    assert s1['info']['goster'] == '10m' and s2['info']['goster'] == '10m'
    # 400 km'de Türkiye hücresinde il sınırı çiziliyor (tasarım §5.2)
    il = [h for h in s2['hucreler'] if h['seviye'] == '10m' and h['katman'] == 'admin1'
          and h['hucre'] == [5, 1]]
    assert il and il[0]['ciz'] > 0 and il[0]['gorunur']
    # Bütçe §3.5: görünür köşe ≤ 1,5 M; vektör çizim çağrısı ≤ 48 (6 katman × 8)
    for s in (s1, s2, s3):
        assert s['info']['cizilenKose'] <= 1_500_000, s['info']['cizilenKose']
    for s in (s2, s3):
        assert s['info']['cizilenHucre'] <= 48, s['info']['cizilenHucre']


# ===========================================================================
# 6) F1 denetimi şartları Ş3 ve Ş4 (13 Eki 2026)
# ===========================================================================
# Ş3 (c): hücre kapağının ufuk payı (denetim D8 yeşil kalmıştı).
# Ş4 (karar §28-33): manifest dosya adı izin listesi; sha256 ya da bayt
# sayısı olmayan basamak İSTENMEZ (fail-closed).

KAPAK_DUZENEGI = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [VEKTOR, GIRDI] = process.argv.slice(2);
const ctx = { console, Math, JSON, Promise, Number, String };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(VEKTOR, 'utf8'), ctx);
const V = ctx.LaunchSiteVectors, g = JSON.parse(fs.readFileSync(GIRDI, 'utf8'));
const kapak = g.kutular.map(b => { const k = V.hucreKapagi(b); return k ? k.alfa : null; });
const ikili = g.ikili.map(([hex, meta]) => V.ikiliDogrula(new Uint8Array(Buffer.from(hex, 'hex')).buffer, meta));
const desen = { vektor: V.DOSYA_ADI_DESENI.source, adlar: g.adlar.map(a => V.DOSYA_ADI_DESENI.test(a)) };
process.stdout.write(JSON.stringify({ kapak, ikili, desen, pay: V.UFUK_PAYI_DEG }));
"""


def _kapak_kos(tmp_path: pathlib.Path, girdi: dict) -> dict:
    js = tmp_path / 'kapak.js'
    js.write_text(KAPAK_DUZENEGI, encoding='utf-8')
    g = tmp_path / 'kapak_girdi.json'
    g.write_text(json.dumps(girdi), encoding='utf-8')
    r = subprocess.run([NODE, str(js), str(VEKTOR), str(g)], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def _buyuk_daire(lat1, lon1, lat2, lon2) -> float:
    """İki nokta arasındaki merkez açısı [rad] (küresel kosinüs yasası)."""
    f1, f2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    c = math.sin(f1) * math.sin(f2) + math.cos(f1) * math.cos(f2) * math.cos(dl)
    return math.acos(max(-1.0, min(1.0, c)))


#: Hücre kapağının ufuk payı [derece]: K2'nin kayıtlı değeri
#: (rapor.md K2 dosya:satır tablosu, "Ufuk payı"; kayan nokta ve kutu köşesi
#: yaklaşıklığı için). Kâhin bu kayıt + bağımsız büyük daire formülü.
K2_UFUK_PAYI_DEG = 0.5

#: İzin listesi dışı dosya adları (yol kaçışı, mutlak yol, dış host, büyük
#: harf, sorgu dizgisi, yasak uzantı, boş, satır sonu).
DUSMAN_ADLAR = ['../vectors_10m.bin', '/etc/passwd', '/static/map/vectors_10m.bin',
                'a/vectors_10m.bin', '..', '..%2fvectors_10m.bin', 'VECTORS_10M.BIN',
                'vectors_10m.bin?x=1', 'vectors_10m.exe', '', 'vectors_10m.bin\n',
                'https://example.invalid/vectors_10m.bin', 'C:\\vectors_10m.bin']


@node_gerek
def test_hucre_kapagi_ufuk_payi_kutunun_kose_acisina_eklenir(tmp_path):
    kutular = [[30, 36, 40, 42], [0, -0.001, 0.001, 0.001], [-120, -60, -90, -30],
               [170, 10, 179.9, 20]]
    r = _kapak_kos(tmp_path, {'kutular': kutular, 'ikili': [], 'adlar': []})
    assert r['pay'] == K2_UFUK_PAYI_DEG
    for kutu, alfa in zip(kutular, r['kapak']):
        lo0, la0, lo1, la1 = kutu
        lam, phi = (lo0 + lo1) / 2, (la0 + la1) / 2
        kose = max(_buyuk_daire(phi, lam, la, lo) for lo in (lo0, lo1) for la in (la0, la1))
        assert alfa == pytest.approx(kose + math.radians(K2_UFUK_PAYI_DEG), abs=1e-12), kutu


@node_gerek
def test_ikili_dogrula_bayt_alani_yoksa_boyut_der(tmp_path):
    veri, ozet = hat.basamak_ikilisi({'coastline': _toplayici([([(30.0, 40.0), (31.0, 41.0)], 0)])})
    tam = dict(ozet, bytes=len(veri))
    eksik = dict(ozet)                      # bytes alanı yok
    r = _kapak_kos(tmp_path, {'kutular': [], 'adlar': [],
                              'ikili': [[veri.hex(), tam], [veri.hex(), eksik]]})
    assert r['ikili'] == [None, 'boyut']


def test_dosya_adi_deseni_iki_modulde_ayni_ve_varliklara_uyar():
    desen = re.compile(r"var DOSYA_ADI_DESENI = /(.+?)/;")
    v = desen.findall(_kod(_oku(VEKTOR)))
    e = desen.findall(_kod(_oku(JS / 'launch_site_labels.js')))
    assert len(v) == 1 and len(e) == 1 and v == e, (v, e)
    kalip = re.compile(v[0])
    for ad in DUSMAN_ADLAR:
        assert not kalip.fullmatch(ad), ad
    manifest = VARLIK_DIZIN / 'vectors_manifest.json'
    if manifest.is_file():
        m = json.loads(manifest.read_text(encoding='utf-8'))
        adlar = [b['file'] for b in m['levels'].values()]
        adlar += [m['places']['file'], m['country_labels']['file']]
        for ad in adlar:
            assert kalip.fullmatch(ad), ad


@node_gerek
def test_dosya_adi_deseni_jsde_dusman_adlari_reddeder(tmp_path):
    adlar = DUSMAN_ADLAR + ['vectors_10m.bin', 'places.json']
    r = _kapak_kos(tmp_path, {'kutular': [], 'ikili': [], 'adlar': adlar})
    assert r['desen']['adlar'] == [False] * len(DUSMAN_ADLAR) + [True, True]


def _manifesti_degistir(kok: pathlib.Path, degis) -> None:
    yol = kok / 'vectors_manifest.json'
    m = json.loads(yol.read_text(encoding='utf-8'))
    degis(m)
    yol.write_text(json.dumps(m), encoding='utf-8')


@node_gerek
@pytest.mark.parametrize('ad', DUSMAN_ADLAR)
def test_izin_listesi_disi_dosya_adi_istenmez_kaba_kalir(tmp_path, ad):
    kok = _sentetik_varliklar(tmp_path / 'map')
    _manifesti_degistir(kok, lambda m: m['levels']['10m'].__setitem__('file', ad))
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(42, 35, 4e5, 459.0)]})
    info = r['sonuc'][0]['info']
    assert info['seviyeler']['10m']['durum'] == 'hata'
    assert info['seviyeler']['10m']['hata'] == 'dosya_adi'
    assert info['hedef'] == '10m' and info['goster'] == '50m', info
    # İstek hiç atılmadı (yalnız manifest, 110m ve 50m istendi).
    assert set(r['istekler']) == {'vectors_manifest.json', 'vectors_110m.bin',
                                  'vectors_50m.bin'}, r['istekler']


@node_gerek
@pytest.mark.parametrize('alan,deger,neden', [('sha256', None, 'sha256_yok'),
                                               ('sha256', 'ABC', 'sha256_yok'),
                                               ('bytes', None, 'boyut_yok'),
                                               ('bytes', '1017884', 'boyut_yok')])
@pytest.mark.parametrize('ozetsiz', [False, True])
def test_kaniti_eksik_ince_basamak_istenmez(tmp_path, alan, deger, neden, ozetsiz):
    """sha256 ya da bayt alanı yoksa basamak istenmez; sha256 doğrulayıcısı
    olmayan tarayıcıda da (yalnız 'doğrulanamadı' beyanı yetmez)."""
    kok = _sentetik_varliklar(tmp_path / 'map')

    def degis(m):
        if deger is None:
            del m['levels']['10m'][alan]
        else:
            m['levels']['10m'][alan] = deger
    _manifesti_degistir(kok, degis)
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(42, 35, 4e5, 459.0)],
                        'digestYok': ozetsiz})
    info = r['sonuc'][0]['info']
    assert info['seviyeler']['10m']['durum'] == 'hata'
    assert info['seviyeler']['10m']['hata'] == neden
    assert info['goster'] == '50m', info
    assert 'vectors_10m.bin' not in r['istekler']


@node_gerek
def test_temel_basamakta_sha256_yoksa_eski_gorunume_doner(tmp_path):
    kok = _sentetik_varliklar(tmp_path / 'map')
    _manifesti_degistir(kok, lambda m: m['levels']['110m'].pop('sha256'))
    r = _kos(tmp_path, {'kok': str(kok), 'kareler': [_kare(42, 35, 4e5, 459.0)]})
    assert r['olaylar'] == ['hata:110m_sha256_yok'], r['olaylar']
    assert 'vectors_110m.bin' not in r['istekler']
