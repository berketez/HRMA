"""Harita ayrıntısı F1 şehir ve ülke etiketlerinin bekçileri (K3, 7 Eki 2026).

Kod: ``hrma/static/js/launch_site_labels.js`` (yeni), şablondaki bindirme ve
not düğümleri (``hrma/templates/launch_site.html``) ve sözlük anahtarları
(``hrma/static/js/i18n_launch_site.js``). Tasarım:
``docs/scofield/raw/OH/UI/harita-detay/tasarim.md`` §3.3, §3.5, §4.1-3,
§5.2, §5.3.

Bekçilerin yakaladığı arıza sınıfları:

* **Uydurma eşik.** Yer süzgeci NE'nin kendi ``MIN_ZOOM`` alanı, ülke süzgeci
  ``MIN_LABEL``/``MAX_LABEL`` değilse; eşiksiz kayıt basılırsa.
* **Arka yüz.** Ufkun arkasındaki yerin etiketi basılırsa.
* **Çakışma.** Yerleşmiş iki etiket dikdörtgeni kesişirse; öncelik dosya
  sırasından (K1: başkent > LABELRANK > POP_MAX) saparsa.
* **Titreme.** Öncelik, çakışma payı, zoom ya da tavan histerezisi kalkarsa.
* **Tavan ve havuz.** 150'den çok etiket basılırsa; kare başına DOM öğesi
  kurulursa ya da ekranda kalan etiketin metni yeniden yazılırsa.
* **Dil.** TR arayüzde NAME_TR (yoksa NAME), EN'de NAME_EN (yoksa NAME)
  dışında bir ad basılırsa.
* **Kanıtsız varlık.** Bayt sayısı ya da sha256'sı manifestle tutmayan yer
  dosyası okunursa.
* **Beyan.** Vektör ölçeği notunun sayısı çizilen basamaktan gelmezse; NE
  atfı K1 künyesinden ayrışırsa; yeni metinlerde EN/TR paritesi bozulursa.

Küçük sentetik yer/ülke girdileri TEST ALTYAPISIDIR (fixture); K1 aracının
kendi üreticileriyle (``yerleri_uret``, ``ulke_etiketlerini_uret``) yazılır,
kullanıcıya gösterilen veri değildir. Metin genişliği testte sabit bir
ölçüyle (6,6 px/harf) verilir; tarayıcıdaki gerçek ölçüm raporda.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
for _yol in (str(KOK), str(KOK / 'tools')):
    if _yol not in sys.path:
        sys.path.insert(0, _yol)

import build_map_detail_assets as hat  # noqa: E402

JS = KOK / 'hrma' / 'static' / 'js'
ETIKET = JS / 'launch_site_labels.js'
GLOBE = JS / 'launch_site_globe.js'
I18N = JS / 'i18n_launch_site.js'
THREE_JS = KOK / 'hrma' / 'static' / 'vendor' / 'three-0.128.0.min.js'
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
VARLIK_DIZIN = KOK / 'hrma' / 'static' / 'map'
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

K3_SOZLUK_ANAHTARLARI = ('site.vectorScaleNote', 'site.neAttribution', 'site.labelsProvenance',
                   'site.boundaryViewDefault', 'site.labelsFallback')


def _oku(yol: pathlib.Path) -> str:
    return yol.read_text(encoding='utf-8')


def _kod(src: str) -> str:
    """Yorumları atar (bekçi kodu ölçsün, açıklamayı değil)."""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return '\n'.join(s for s in src.splitlines() if not s.strip().startswith('//'))


# ---------------------------------------------------------------------------
# Node düzeneği: three r128 + küre (tek dönüşüm) + etiket modülü, sahte DOM
# ---------------------------------------------------------------------------
DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), crypto = require('crypto');
const [THREE_JS, GLOBE, ETIKET, GOREV] = process.argv.slice(2);
const gorev = JSON.parse(fs.readFileSync(GOREV, 'utf8'));
const ctx = { console, performance, Math, Promise, setTimeout, JSON, TextDecoder };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(THREE_JS, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(GLOBE, 'utf8'), ctx);
vm.runInContext(fs.readFileSync(ETIKET, 'utf8'), ctx);
const THREE = ctx.THREE, G = ctx.LaunchSiteGlobe, L = ctx.LaunchSiteLabels;
const R = 100, MPU = 6371000 / 100;

// Sahte DOM: öğe kurma ve metin yazma sayılır.
const dom = { kurulan: 0, metinYazma: 0 };
function Oge(tag) {
    this.tagName = tag; this.style = {}; this.className = ''; this.children = [];
    this.parentNode = null; this._metin = '';
}
Object.defineProperty(Oge.prototype, 'textContent', {
    get() { return this._metin; }, set(v) { dom.metinYazma++; this._metin = String(v); } });
Oge.prototype.appendChild = function (c) { c.parentNode = this; this.children.push(c); return c; };
Oge.prototype.removeChild = function (c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; };
const belge = { createElement(tag) { dom.kurulan++; return new Oge(tag); } };

function dosyaFetch(kok) {
    return (u) => {
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

// Kamera: hedef (lat, lon) yüzeyde, d km uzakta, kuzeye doğru `egim` derece.
function kare(k) {
    const W = k.W || 1440, H = k.H || 900;
    const n = new THREE.Vector3(...G.latLonToXYZ(k.lat, k.lon, 1, [0, 0, 0], 0));
    const dogu = new THREE.Vector3(0, 1, 0).cross(n).normalize();
    const kuzey = n.clone().cross(dogu).normalize();
    const t = (k.egim || 0) * Math.PI / 180;
    const hedef = n.clone().multiplyScalar(R);
    const yon = n.clone().multiplyScalar(Math.cos(t)).add(kuzey.multiplyScalar(-Math.sin(t)));
    const dU = k.d * 1000 / MPU;
    const cam = new THREE.PerspectiveCamera(38, W / H, 0.01, 1e5);
    cam.position.copy(hedef.clone().add(yon.multiplyScalar(dU)));
    cam.up.set(0, 1, 0);
    cam.lookAt(hedef);
    cam.updateMatrixWorld();
    const mpp = 2 * dU * Math.tan(19 * Math.PI / 180) / H * MPU;
    return { camera: cam, target: hedef, metersPerPixel: mpp,
             zWeb: (k.z != null) ? k.z : Math.log2(G.Z_WEB_Z0_MPP / mpp),
             camAltitudeM: k.d * 1000, size: { width: W, height: H }, globeRadius: R };
}

(async () => {
    const sonuc = [];
    let l = null, dil = 'en', kap = null, engel = null, saat = 0;
    for (const a of gorev.adimlar) {
        if (a.op === 'kur') {
            dil = a.dil || 'en';
            kap = new Oge('div');
            const o = { container: kap, document: belge, latLonToXYZ: G.latLonToXYZ,
                        baseUrl: '/static/map/', fetchImpl: dosyaFetch(a.dizin),
                        digestImpl: a.ozetYok ? null : ozet, getLang: () => dil,
                        measureText: (m) => m.length * 6.6 };
            if (a.ozetYok) { o.digestImpl = null; ctx.crypto = undefined; }
            if (a.engeller) { engel = a.engeller; o.getObstacles = () => engel; }
            o.now = () => saat;     // sahte saat: her karede 1 s ilerler
            l = new L(o);
            await l.start();
            sonuc.push({ op: 'kur', durum: l.durum, hata: l.hata, kunye: l.kunye,
                         havuz: kap.children.length });
        } else if (a.op === 'dil') {
            dil = a.dil;
        } else if (a.op === 'engel') {
            engel = a.engeller;
        } else if (a.op === 'kare') {
            saat += 1000;
            const f = kare(a);
            l.update(f);
            const c = f.camera.position;
            const pl = l.getPlacements().map(p => {
                const v = G.latLonToXYZ(p.lat, p.lon, 1, [0, 0, 0], 0);
                p.onYuz = v[0] * c.x + v[1] * c.y + v[2] * c.z;
                return p;
            });
            const gorunurOge = kap.children.filter(e => e.style.visibility === 'visible')
                .map(e => ({ metin: e.children[1].textContent, sinif: e.className,
                             transform: e.style.transform }));
            sonuc.push({ op: 'kare', z: f.zWeb, R: R, yer: pl, info: l.getInfo(),
                         dom: Object.assign({}, dom), gorunurOge: gorunurOge });
        }
    }
    process.stdout.write(JSON.stringify(sonuc));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


def _kos(tmp_path: pathlib.Path, adimlar: list) -> list:
    js = tmp_path / 'duzenek.js'
    js.write_text(DUZENEK, encoding='utf-8')
    gorev = tmp_path / 'gorev.json'
    gorev.write_text(json.dumps({'adimlar': adimlar}), encoding='utf-8')
    r = subprocess.run([NODE, str(js), str(THREE_JS), str(GLOBE), str(ETIKET), str(gorev)],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


# ---------------------------------------------------------------------------
# Sentetik girdi: K1'in kendi üreticileriyle yazılır (fixture)
# ---------------------------------------------------------------------------

def _yer(ad, lon, lat, mz, rank=5, sinif='Populated place', ad_en=None, ad_tr=None,
         pop=1000, ne_id=0):
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
            'properties': {'NAME': ad, 'NAME_EN': ad_en, 'NAME_TR': ad_tr, 'MIN_ZOOM': mz,
                           'LABELRANK': rank, 'FEATURECLA': sinif, 'ADM0_A3': 'XXX',
                           'POP_MAX': pop, 'NE_ID': ne_id, 'ADM1NAME': None}}


def _ulke(ad, lon, lat, mn, mx, rank=2, ad_en=None, ad_tr=None):
    return {'type': 'Feature', 'geometry': None,
            'properties': {'LABEL_X': lon, 'LABEL_Y': lat, 'NAME': ad, 'NAME_EN': ad_en,
                           'NAME_TR': ad_tr, 'MIN_LABEL': mn, 'MAX_LABEL': mx,
                           'LABELRANK': rank, 'ADM0_A3': 'XXX'}}


def _sentetik(dizin: pathlib.Path, yerler: list, ulkeler: list = (),
              bozuk: str = '') -> pathlib.Path:
    dizin.mkdir(parents=True, exist_ok=True)
    gy = dizin / 'yer.geojson'
    gy.write_text(json.dumps({'type': 'FeatureCollection', 'features': list(yerler)}),
                  encoding='utf-8')
    gu = dizin / 'ulke.geojson'
    gu.write_text(json.dumps({'type': 'FeatureCollection', 'features': list(ulkeler)}),
                  encoding='utf-8')
    y, _ = hat.yerleri_uret(gy)
    u, _ = hat.ulke_etiketlerini_uret(gu)
    y['provenance'] = {'source': 'Natural Earth v5.1.2 (fixture)', 'boundary_view': 'varsayilan'}
    u['provenance'] = {'source': 'Natural Earth v5.1.2 (fixture)', 'boundary_view': 'varsayilan'}
    yb, ub = hat._json_bayt(y), hat._json_bayt(u)
    (dizin / 'places.json').write_bytes(yb)
    (dizin / 'country_labels.json').write_bytes(ub)
    m = {'places': {'file': 'places.json', 'bytes': len(yb), 'sha256': hat._sha(yb)},
         'country_labels': {'file': 'country_labels.json', 'bytes': len(ub),
                            'sha256': hat._sha(ub)}}
    if bozuk == 'sha':
        m['places']['sha256'] = '0' * 64
    elif bozuk == 'bayt':
        m['places']['bytes'] += 1
    (dizin / 'vectors_manifest.json').write_text(json.dumps(m), encoding='utf-8')
    return dizin


def _adlar(s: dict) -> list:
    return [p['ad'] for p in s['yer']]


# ===========================================================================
# 1) Süzgeç: NE'nin kendi eşikleri
# ===========================================================================

@node_gerek
def test_yer_suzgeci_ne_min_zoom(tmp_path):
    d = _sentetik(tmp_path / 'm', [_yer('Erken', 10, 0, 3.0, ne_id=1),
                                   _yer('Gec', 14, 0, 7.0, ne_id=2),
                                   _yer('Esiksiz', 18, 0, None, ne_id=3)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 0, 'lon': 14, 'd': 3000, 'z': 5.0},
                        {'op': 'kare', 'lat': 0, 'lon': 14, 'd': 3000, 'z': 7.0}])
    assert r[0]['durum'] == 'hazir', r[0]
    assert r[0]['kunye']['esiksizKayit'] == 1
    assert _adlar(r[1]) == ['Erken']
    assert sorted(_adlar(r[2])) == ['Erken', 'Gec']   # eşiksiz kayıt hiç basılmaz


@node_gerek
def test_ulke_suzgeci_min_label_max_label(tmp_path):
    d = _sentetik(tmp_path / 'm', [], [_ulke('Genis', 10, 0, 2.0, 5.0),
                                       _ulke('Dar', 30, 0, 4.0, 9.0)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 0, 'lon': 20, 'd': 9000, 'z': 3.0},
                        {'op': 'kare', 'lat': 0, 'lon': 20, 'd': 9000, 'z': 4.5},
                        {'op': 'kare', 'lat': 0, 'lon': 20, 'd': 9000, 'z': 6.0}])
    assert _adlar(r[1]) == ['Genis']
    assert sorted(_adlar(r[2])) == ['Dar', 'Genis']
    # Genis 4,5'te gösterildi; 6,0 > 5,0 + histerezis -> kaybolur.
    assert _adlar(r[3]) == ['Dar']
    assert all(p['tur'] == 'country' for s in r[1:] for p in s['yer'])


# ===========================================================================
# 2) Ufuk ve çakışma, öncelik
# ===========================================================================

@node_gerek
def test_arka_yuz_etiketi_basilmaz(tmp_path):
    # Kamera 0°/0° üstünde, tüm Dünya uzaklığında: ufuk açısı
    # acos(R / |kamera|) ~ 74,9°. 180° boylamdaki yer arka yüzde; 76° ve
    # -76° ufkun hemen ötesinde ama KOVALARI ufuk başlığına değiyor ve
    # izdüşümleri ekranın içinde: yalnız noktanın kendi ufuk sınavı atar.
    d = _sentetik(tmp_path / 'm', [_yer('On', 0, 0, 1.0, ne_id=1),
                                   _yer('Arka', 180, 0, 1.0, ne_id=2),
                                   _yer('UfukOtesi', 76, 0, 1.0, ne_id=3),
                                   _yer('UfukOtesiB', -76, 0, 1.0, ne_id=4)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 0, 'lon': 0, 'd': 18100, 'z': 9.0}])
    s = r[1]
    assert _adlar(s) == ['On']
    assert all(p['onYuz'] > s['R'] for p in s['yer'])


@node_gerek
def test_cakisan_iki_yerden_dosya_sirasinda_onceki_kalir(tmp_path):
    # K1 dosya sırası: başkent önce. İki nokta aynı ekran pikseline düşer.
    d = _sentetik(tmp_path / 'm', [_yer('Kasaba', 30.0, 40.0, 2.0, rank=8, ne_id=1),
                                   _yer('Baskent', 30.01, 40.0, 2.0, rank=1,
                                        sinif='Admin-0 capital', ne_id=2)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0}])
    assert _adlar(r[1]) == ['Baskent']
    assert r[1]['yer'][0]['tur'] == 'capital'
    assert r[1]['info']['cakismaGizli'] == 1


@node_gerek
def test_ulke_adi_yerlerden_once_yarisir(tmp_path):
    d = _sentetik(tmp_path / 'm', [_yer('Sehir', 30.0, 40.0, 2.0, rank=1,
                                        sinif='Admin-0 capital', ne_id=1)],
                  [_ulke('Ulke', 30.0, 40.0, 1.0, 9.0)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0}])
    assert _adlar(r[1]) == ['Ulke']


def _kesisim(a, b):
    w = min(a['x1'], b['x1']) - max(a['x0'], b['x0'])
    h = min(a['y1'], b['y1']) - max(a['y0'], b['y0'])
    return w * h if (w > 0 and h > 0) else 0.0


@node_gerek
def test_yogun_kumede_kesisim_alani_sifir_ve_tavan(tmp_path):
    # 40x40 yer, 0,25° aralıkla: tavan da çakışma da zorlanır.
    yerler = [_yer('Y%d_%d' % (i, j), 20 + 0.25 * i, 30 + 0.25 * j, 2.0, ne_id=100 * i + j)
              for i in range(40) for j in range(40)]
    d = _sentetik(tmp_path / 'm', yerler)
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 35, 'lon': 25, 'd': 400, 'z': 9.0},
                        {'op': 'kare', 'lat': 35, 'lon': 25, 'd': 1500, 'z': 7.0}])
    for s in r[1:]:
        yer = s['yer']
        assert 0 < len(yer) <= 150, len(yer)
        for i in range(len(yer)):
            for j in range(i + 1, len(yer)):
                assert _kesisim(yer[i], yer[j]) == 0.0, (yer[i], yer[j])
    assert len(r[1]['yer']) == 150 and r[1]['info']['tavanGizli'] > 0


@node_gerek
def test_panel_altina_etiket_basilmaz(tmp_path):
    # Kamera (40, 30) üstünde; yer ekran ortasında (720, 450). Ortayı örten
    # bir panel kutusu verilince etiket basılmaz; kenardaki kutu engellemez.
    d = _sentetik(tmp_path / 'm', [_yer('Orta', 30, 40, 2.0, ne_id=1)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d), 'engeller': [[600, 400, 900, 500]]},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0},
                        {'op': 'kur', 'dizin': str(d), 'engeller': [[0, 0, 300, 900]]},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0}])
    assert _adlar(r[1]) == [] and r[1]['info']['engel'] == 1
    assert _adlar(r[3]) == ['Orta']


@node_gerek
def test_panel_kalkinca_durgun_kamerada_da_yenilenir(tmp_path):
    d = _sentetik(tmp_path / 'm', [_yer('Orta', 30, 40, 2.0, ne_id=1)])
    k = {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0}
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d), 'engeller': [[600, 400, 900, 500]]},
                        dict(k), {'op': 'engel', 'engeller': []}, dict(k)])
    assert _adlar(r[1]) == [] and _adlar(r[2]) == ['Orta']


def test_sablon_panelleri_engel_olarak_verir():
    kod = _kod(_oku(SABLON))
    m = re.search(r"var LS_ETIKET_ENGELLERI = \[(.*?)\];", kod)
    assert m
    ids = re.findall(r"'([\w-]+)'", m.group(1))
    # Ş2 (F1 denetimi, 12 Eki): üst şerit de engeldir.
    assert set(ids) == {'ls-topbar', 'ls-left', 'ls-right', 'ls-scalebar', 'ls-notes',
                        'ls-cursor'}
    for i in ids:
        assert 'id="%s"' % i in kod, i
    assert 'getObstacles: function ()' in kod


@node_gerek
def test_ust_serit_kutusu_kenardan_tasan_etiketi_engeller(tmp_path):
    """Ş2: üst şerit bindirmenin üstündedir; getObstacles onun kutusunu
    negatif y'de verir ([0, -h, W, 0]). Çapası üst kenara yakın, metni
    kenardan taşan etiket basılmaz; tamamı ekranda olan basılır."""
    ust = [[0, -41, 1440, 0]]
    adim = []
    enlemler = [40.0 + 0.05 * i for i in range(400)]
    for i, la in enumerate(enlemler):
        d = _sentetik(tmp_path / ('m%d' % i), [_yer('U', 30, la, 2.0, ne_id=1)])
        adim += [{'op': 'kur', 'dizin': str(d)},
                 {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0}]
    r = _kos(tmp_path, adim)
    kareler = r[1::2]
    tasan = [i for i, s in enumerate(kareler) if s['yer'] and s['yer'][0]['y0'] < 0 < s['yer'][0]['y1']]
    tam = [i for i, s in enumerate(kareler) if s['yer'] and s['yer'][0]['y0'] >= 10]
    assert tasan and tam, 'düzenek üst kenarı kesen etiket üretemedi'
    i, j = tasan[0], tam[-1]
    adim = []
    for k in (i, j):
        adim += [{'op': 'kur', 'dizin': str(tmp_path / ('m%d' % k)), 'engeller': ust},
                 {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0}]
    r2 = _kos(tmp_path, adim)
    assert _adlar(r2[1]) == [] and r2[1]['info']['engel'] == 1
    assert _adlar(r2[3]) == ['U']


# ===========================================================================
# 3) Histerezis (titreme)
# ===========================================================================

@node_gerek
def test_zoom_histerezisi(tmp_path):
    d = _sentetik(tmp_path / 'm', [_yer('A', 30, 40, 6.0, ne_id=1)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 1500, 'z': 5.95},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 1500, 'z': 6.0},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 1500, 'z': 5.95},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 1500, 'z': 5.85}])
    assert [_adlar(s) for s in r[1:]] == [[], ['A'], ['A'], []]


@node_gerek
def test_gosterilen_etiket_yakin_oncelikli_yeniyle_sokulmez(tmp_path):
    # 'Eski' z=4'te tek başına görünür; z=5'te ondan BİR sıra önde 'Yeni'
    # (MIN_ZOOM 5) aynı yere girer. Öncelik payı gösterileni korur.
    d = _sentetik(tmp_path / 'm', [_yer('Yeni', 30.01, 40.0, 5.0, rank=3, ne_id=1),
                                   _yer('Eski', 30.0, 40.0, 4.0, rank=4, ne_id=2)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 5.0}])
    assert _adlar(r[1]) == ['Eski'] and _adlar(r[2]) == ['Eski']


@node_gerek
def test_yeni_etiket_bosluk_payi_ister_gosterilen_istemez(tmp_path):
    # İki ad yan yana; aralarındaki boşluk payın altında: yalnız öncelikli
    # olan basılır. Önce yalnız ikincisi görünürken (z süzgeci) kurulursa
    # ikisi de kalır mı? Hayır: aynı karede ikisi de YENİ ise pay uygulanır.
    L = 'AAAA'      # 4 harf * 6,6 px = 27 px (yuvarlanır 27)
    d = _sentetik(tmp_path / 'm', [_yer(L, 30.0, 40.0, 2.0, rank=1, ne_id=1),
                                   _yer('BBBB', 30.0, 40.0, 2.0, rank=2, ne_id=2)])
    js = _kod(_oku(ETIKET))
    assert 'izgara.bosMu(r, onceki[k] ? 0 : YENI_ETIKET_PAYI_PX)' in js
    m = re.search(r'var YENI_ETIKET_PAYI_PX = (\d+);', js)
    assert m and int(m.group(1)) > 0
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0}])
    assert _adlar(r[1]) == [L]


@node_gerek
def test_tavanda_gosterilenler_sokulmez(tmp_path):
    # 400 yer; ilk karede tavan dolar. Sonra çok daha öncelikli 5 yeni yer
    # (MIN_ZOOM daha büyük) görünür olur: gösterilen 150 korunur. Aradaki
    # 600 dolgu kaydı (hiç uygun olmayan MIN_ZOOM) yeni yerleri öncelik
    # payının ötesine taşır; böylece yalnız TAVAN histerezisi sınanır.
    yerler = [_yer('Y%03d' % i, 20 + 0.5 * (i % 20), 30 + 0.5 * (i // 20), 2.0,
                   rank=5, ne_id=i) for i in range(400)]
    dolgu = [_yer('D%03d' % i, -60 + 0.1 * i, -40, 30.0, rank=1, ne_id=2000 + i)
             for i in range(600)]
    yeni = [_yer('N%d' % i, 20.1 + 0.5 * i, 30.1, 6.0, rank=0, ne_id=1000 + i)
            for i in range(5)]
    d = _sentetik(tmp_path / 'm', yeni + dolgu + yerler)
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 35, 'lon': 25, 'd': 3000, 'z': 5.0, 'W': 4000, 'H': 3000},
                        {'op': 'kare', 'lat': 35, 'lon': 25, 'd': 3000, 'z': 6.0, 'W': 4000, 'H': 3000}])
    a, b = set(_adlar(r[1])), set(_adlar(r[2]))
    assert len(a) == 150 and len(b) == 150
    assert a == b, 'tavanda gösterilen etiket yeni adayla söküldü: %s' % sorted(a - b)[:5]


# ===========================================================================
# 4) DOM havuzu, imza atlaması, dil
# ===========================================================================

@node_gerek
def test_dom_havuzu_bir_kez_kurulur_metin_yeniden_yazilmaz(tmp_path):
    d = _sentetik(tmp_path / 'm', [_yer('A', 30, 40, 2.0, ne_id=1),
                                   _yer('B', 32, 40, 2.0, ne_id=2)])
    adim = [{'op': 'kur', 'dizin': str(d)}]
    for i in range(6):
        adim.append({'op': 'kare', 'lat': 40, 'lon': 31 + 0.01 * i, 'd': 1500, 'z': 7.0})
    adim.append({'op': 'kare', 'lat': 40, 'lon': 31.05, 'd': 1500, 'z': 7.0})   # aynı kamera
    r = _kos(tmp_path, adim)
    assert r[0]['havuz'] == 150
    kurulan = [s['dom']['kurulan'] for s in r[1:]]
    assert len(set(kurulan)) == 1 and kurulan[0] == 3 * 150, kurulan
    yazma = [s['dom']['metinYazma'] for s in r[1:]]
    assert yazma[0] == 2 and len(set(yazma)) == 1, yazma
    # Kamera değişmeyince güncelleme atlanır.
    assert r[-1]['info']['atlananKare'] == 1
    assert r[-1]['info']['guncellemeSayisi'] == 6
    goru = r[-2]['gorunurOge']
    assert sorted(g['metin'] for g in goru) == ['A', 'B']
    assert all(g['transform'].startswith('translate3d(') for g in goru)


@node_gerek
def test_dil_secimi_ve_dil_degisiminde_yeniden_basim(tmp_path):
    d = _sentetik(tmp_path / 'm', [
        _yer('Istanbul', 29.0, 41.0, 2.0, rank=1, ad_en='Istanbul', ad_tr='İstanbul', ne_id=1),
        _yer('Yerel', 33.0, 37.0, 2.0, rank=2, ad_en=None, ad_tr=None, ne_id=2),
        _yer('Icel', 34.6, 36.8, 2.0, rank=3, ad_en='Mersin', ad_tr='Mersin', ne_id=3)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d), 'dil': 'tr'},
                        {'op': 'kare', 'lat': 39, 'lon': 31, 'd': 1500, 'z': 7.0},
                        {'op': 'dil', 'dil': 'en'},
                        {'op': 'kare', 'lat': 39, 'lon': 31, 'd': 1500, 'z': 7.0}])
    assert r[0]['kunye']['adYedegi'] == {'tr': 1, 'en': 1}
    tr = sorted(g['metin'] for g in r[1]['gorunurOge'])
    en = sorted(g['metin'] for g in r[2]['gorunurOge'])
    assert tr == ['Mersin', 'Yerel', 'İstanbul']
    assert en == ['Istanbul', 'Mersin', 'Yerel']
    assert r[2]['info']['dil'] == 'en'


# ===========================================================================
# 5) Kanıtlı yükleme
# ===========================================================================

@node_gerek
@pytest.mark.parametrize('bozuk,neden', [('sha', 'sha256_places'), ('bayt', 'boyut_places')])
def test_kaniti_tutmayan_yer_dosyasi_reddedilir(tmp_path, bozuk, neden):
    d = _sentetik(tmp_path / 'm', [_yer('A', 30, 40, 2.0, ne_id=1)], bozuk=bozuk)
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 1500, 'z': 7.0}])
    assert r[0]['durum'] == 'hata' and r[0]['hata'] == neden, r[0]
    assert r[1]['yer'] == [] and r[0]['havuz'] == 0


#: İzin listesi dışı dosya adları (F1 denetimi Ş4, karar §28-33). Biri
#: '../places.json': yol kaçışı; düzenekteki dosya okuyucu yalnız dosya adını
#: aldığı için istek atılsaydı gerçek dosya yüklenir, durum 'hazir' olurdu.
DUSMAN_ADLAR = ['../places.json', '/etc/passwd', '/static/map/places.json', 'a/places.json',
                '..', 'PLACES.JSON', 'places.json?x=1', 'places.js', '', 'places.json\n',
                'https://example.invalid/places.json']


@node_gerek
@pytest.mark.parametrize('ad', DUSMAN_ADLAR)
def test_izin_listesi_disi_dosya_adi_istenmez(tmp_path, ad):
    d = _sentetik(tmp_path / 'm', [_yer('A', 30, 40, 2.0, ne_id=1)])
    m = json.loads((d / 'vectors_manifest.json').read_text(encoding='utf-8'))
    m['places']['file'] = ad
    (d / 'vectors_manifest.json').write_text(json.dumps(m), encoding='utf-8')
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d)},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 1500, 'z': 7.0}])
    # Boş ad mevcut 'manifest_' denetimine takılır; geri kalanı izin listesine.
    beklenen = 'manifest_places' if not ad else 'dosya_adi_places'
    assert r[0]['durum'] == 'hata' and r[0]['hata'] == beklenen, r[0]
    assert r[1]['yer'] == [] and r[0]['havuz'] == 0


@node_gerek
@pytest.mark.parametrize('deger', [None, 'ABC', '0' * 63])
@pytest.mark.parametrize('ozetYok', [False, True])
def test_sha256_alani_yoksa_yer_dosyasi_istenmez(tmp_path, deger, ozetYok):
    """sha256 yoksa doğrulayıcısı olmayan tarayıcıda da ret (vektör modülüyle
    aynı sözleşme; F1 denetimi: iki modül tutarsızdı)."""
    d = _sentetik(tmp_path / 'm', [_yer('A', 30, 40, 2.0, ne_id=1)])
    m = json.loads((d / 'vectors_manifest.json').read_text(encoding='utf-8'))
    if deger is None:
        del m['places']['sha256']
    else:
        m['places']['sha256'] = deger
    (d / 'vectors_manifest.json').write_text(json.dumps(m), encoding='utf-8')
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d), 'ozetYok': ozetYok}])
    assert r[0]['durum'] == 'hata' and r[0]['hata'] == 'sha256_yok_places', r[0]
    assert r[0]['havuz'] == 0


@node_gerek
def test_varlik_yoksa_etiket_yok_ve_durum_beyanli(tmp_path):
    (tmp_path / 'bos').mkdir()
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(tmp_path / 'bos')},
                        {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 1500, 'z': 7.0}])
    assert r[0]['durum'] == 'hata' and r[0]['hata'].startswith('http_')
    assert r[1]['yer'] == []


@node_gerek
def test_sha_dogrulanamazsa_beyan_edilir(tmp_path):
    d = _sentetik(tmp_path / 'm', [_yer('A', 30, 40, 2.0, ne_id=1)])
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(d), 'ozetYok': True}])
    assert r[0]['durum'] == 'hazir'
    assert r[0]['kunye']['shaDogrulandi'] == {'places': False, 'country_labels': False}


# ===========================================================================
# 6) Kaynak bekçileri: tek tanım, şablon, sözlük
# ===========================================================================

def test_etiket_modulu_kendi_olcegini_ve_donusumunu_tutmaz():
    js = _kod(_oku(ETIKET))
    assert 'f.zWeb' in js
    assert 'Math.log2' not in js and '156543' not in js, 'z_web ikinci kez tanımlanmış'
    assert 'Math.cos(lo' not in js and 'deg2rad' not in js, 'enlem/boylam dönüşümü kopyalanmış'
    assert 'this.opts.latLonToXYZ' in js
    m = re.search(r'var ETIKET_TAVANI = (\d+);', js)
    assert m and int(m.group(1)) == 150
    assert re.search(r'var HAVUZ_BOYUTU = ETIKET_TAVANI;', js)
    assert re.search(r'var IZGARA_PX = 64;', js) and re.search(r'var KOVA_DERECE = 10;', js)


def test_sablon_bindirme_ve_baglanti():
    s = _oku(SABLON)
    i_v, i_l, i_g = (s.index('/static/js/launch_site_vectors.js'),
                     s.index('/static/js/launch_site_labels.js'),
                     s.index('/static/js/launch_site_globe.js'))
    assert i_v < i_l < i_g
    assert '<div id="ls-labels"></div>' in s
    css = re.search(r'#ls-labels \{(.*?)\}', s, re.S).group(1)
    assert 'pointer-events: none' in css
    z = int(re.search(r'z-index:\s*(\d+)', css).group(1))
    panel = int(re.search(r'\.ls-panel \{.*?z-index:\s*(\d+)', s, re.S).group(1))
    assert z < panel, 'etiketler panellerin üstüne çıkıyor'
    kod = _kod(s)
    assert 'latLonToXYZ: window.LaunchSiteGlobe.latLonToXYZ' in kod
    assert 'globe.addFrameListener(function (f) { labels.update(f); });' in kod
    # Etiket dili sayfanın TEK dil kanalından (I18N.lang) okunur.
    assert "getLang: function () { return (I18N && I18N.lang) || 'en'; }" in kod
    assert 'renderMapNotes(false);' in kod and 'renderMapNotes(true);' in kod


def test_sozluk_yeni_anahtarlar_parite_ve_uzun_tire_yok():
    sys.path.insert(0, str(KOK / 'tests'))
    from test_z5i18n_supurme import sozluk  # noqa: E402
    en, tr = sozluk(I18N, 'en'), sozluk(I18N, 'tr')
    for k in K3_SOZLUK_ANAHTARLARI:
        assert k in en and k in tr, k
        assert set(re.findall(r'\{(\w+)\}', en[k])) == set(re.findall(r'\{(\w+)\}', tr[k])), k
        for v in (en[k], tr[k]):
            assert '—' not in v and '–' not in v, (k, v)
            assert not re.search('[\U0001F300-\U0001FAFF☀-➿]', v), (k, v)
    assert re.search('[çğıİöşü]', tr['site.vectorScaleNote'])
    # NE atfının EN metni K1 künyesiyle aynı (iki kaynak ayrışmasın).
    assert en['site.neAttribution'] == hat.NE_ATIF
    # Şablondaki tf/t yedek metinleri sözlüğün EN değerleriyle aynı (i18n
    # betiği yüklenemezse ekrana çıkan metin sözlükten ayrışmasın).
    kod = _kod(_oku(SABLON))
    dizgi = r"((?:'(?:[^'\\]|\\.)*'\s*\+?\s*)+)\)"
    cagri = {'site.vectorScaleNote': r"tf\('site\.vectorScaleNote',\s*\{.*?\},\s*",
             'site.labelsProvenance': r"tf\('site\.labelsProvenance',\s*\{.*?\},\s*",
             'site.labelsFallback': r"tf\('site\.labelsFallback',\s*\{.*?\},\s*",
             'site.neAttribution': r"t\('site\.neAttribution',\s*",
             'site.boundaryViewDefault': r"t\(gorAnahtar,\s*"}
    assert set(cagri) == set(K3_SOZLUK_ANAHTARLARI)
    assert "{ varsayilan: 'site.boundaryViewDefault' }" in kod
    for k, desen in cagri.items():
        govde = re.search(desen + dizgi, kod, re.S)
        assert govde, k
        yedek = ''.join(re.findall(r"'((?:[^'\\]|\\.)*)'", govde.group(1)))
        assert yedek == en[k], (k, yedek)


def _not_islevi() -> str:
    s = _oku(SABLON)
    m = re.search(r'    function vectorScaleNumber\(v\) \{.*?\n    \}\n', s, re.S)
    assert m
    return m.group(0)


@node_gerek
def test_olcek_notu_sayisi_cizilen_basamaktan(tmp_path):
    s = _oku(SABLON)
    m = re.search(r'var VEKTOR_NOTU_MPP = (\d+);', s)
    assert m and int(m.group(1)) == 500, 'tasarım §5.3-1: not m/px < 500 iken'
    assert 'info.metersPerPixel < VEKTOR_NOTU_MPP' in _kod(s)
    js = tmp_path / 'not.js'
    js.write_text(_not_islevi() + r"""
const vakalar = [
  [{durum: 'hazir', nominalScale: '1:10m', legacyVisible: false}, '10'],
  [{durum: 'hazir', nominalScale: '1:50m', legacyVisible: false}, '50'],
  [{durum: 'yok', legacyVisible: true}, '110'],
  [{durum: 'hata', nominalScale: null, legacyVisible: true}, '110'],
  [{durum: 'yukleniyor', nominalScale: null, legacyVisible: false}, null],
  [null, null],
];
const out = vakalar.map(([v, b]) => [vectorScaleNumber(v), b]);
process.stdout.write(JSON.stringify(out));
""", encoding='utf-8')
    r = subprocess.run([NODE, str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    for alinan, beklenen in json.loads(r.stdout):
        assert alinan == beklenen


# ===========================================================================
# 7) Gerçek NE verisiyle (depoda varsa onlar; yoksa ham kaynaktan üretim)
# ===========================================================================

@pytest.fixture(scope='module')
def gercek_dizin(tmp_path_factory):
    if (VARLIK_DIZIN / 'places.json').is_file() and (VARLIK_DIZIN / 'vectors_manifest.json').is_file():
        return VARLIK_DIZIN
    if not (hat.VARSAYILAN_KAYNAK / hat.SHA_LISTESI).is_file():
        pytest.skip('hrma/static/map yok ve ham NE kaynağı bu makinede yok; '
                    'gerçek veri senaryosu koşulamadı (yapım girdisi, docs kanıtı değil)')
    # Bütçe bir PAKETLEME kararıdır (K1 devri, ana model); etiket davranışını
    # sınamak için çıktı geçici dizine bütçe dışı üretilir, depoya yazılmaz.
    dosyalar, _ = hat.uret(hat.VARSAYILAN_KAYNAK, butce=10 ** 9)
    hedef = tmp_path_factory.mktemp('ne') / 'map'
    hat.yaz(dosyalar, hedef)
    return hedef


@node_gerek
def test_gercek_ne_turkiye_ve_sahalar(tmp_path, gercek_dizin):
    pozlar = [
        {'op': 'kare', 'lat': 39.0, 'lon': 35.0, 'd': 18100},              # tüm Dünya
        {'op': 'kare', 'lat': 39.0, 'lon': 32.0, 'd': 1500},               # Türkiye
        {'op': 'kare', 'lat': 42.0, 'lon': 35.1, 'd': 400, 'egim': 46},    # Sinop
        {'op': 'kare', 'lat': 42.0, 'lon': 35.1, 'd': 25.5, 'egim': 46},
        {'op': 'kare', 'lat': 28.57, 'lon': -80.65, 'd': 100},             # Kennedy
        {'op': 'kare', 'lat': -39.26, 'lon': 177.86, 'd': 400, 'egim': 30},  # Mahia
    ]
    r = _kos(tmp_path, [{'op': 'kur', 'dizin': str(gercek_dizin), 'dil': 'tr'}] + pozlar
             + [{'op': 'dil', 'dil': 'en'}, dict(pozlar[1])])
    k = r[0]
    assert k['durum'] == 'hazir' and k['kunye']['surum'] == 'v5.1.2'
    assert k['kunye']['shaDogrulandi'] == {'places': True, 'country_labels': True}
    for s in r[1:]:
        yer = s['yer']
        assert len(yer) <= 150
        assert all(p['onYuz'] > s['R'] for p in yer)
        for i in range(len(yer)):
            for j in range(i + 1, len(yer)):
                assert _kesisim(yer[i], yer[j]) == 0.0
    dunya, tr1500, sinop400 = r[1], r[2], r[3]
    assert dunya['yer'] and all(p['tur'] in ('country', 'capital', 'city') for p in dunya['yer'])
    assert 'Türkiye' in set(_adlar(dunya))
    adlar = set(_adlar(tr1500))
    assert {'Ankara', 'İstanbul', 'İzmir'} <= adlar, sorted(adlar)[:40]
    # Sinop çevresinde en az bir il merkezi adı (tasarım §5.2).
    assert {'Sinop', 'Kastamonu', 'Samsun'} & set(_adlar(sinop400))
    en1500 = set(_adlar(r[-1]))
    assert {'Istanbul', 'Ankara'} <= en1500 and 'İstanbul' not in en1500, sorted(en1500)[:40]
