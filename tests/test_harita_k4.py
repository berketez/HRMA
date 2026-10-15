"""Harita ayrıntısı 5. tur bekçileri (14 Eki 2026): K4 paketli doku piramidi
(F2) + HS5 devirleri (K-2 eki, K-3 seçenek b).

Yakalanan arıza sınıfları:

* **Paket bütünlüğü.** ``hrma/static/map/bm_pyr`` içindeki her karo
  manifestte sha256 ve bayt sayısıyla kayıtlı; manifestte olmayan dosya,
  dosyası olmayan kayıt, bozuk imza, bütçe aşımı ya da tile_cache
  ızgarasından sapan düzey KIRMIZI.
* **Sahte veri yok.** Kaynak (NASA BMNG Aralık 2004, 21600x10800) yerelde
  varsa z0-z3 karoları ondan YENİDEN üretilir ve paketteki baytlarla
  birebir karşılaştırılır (karolar yalnız ham görüntüden gelir).
* **Ağsız sunum.** ``bm_local`` karosu, ağ izni açık olsa bile hiçbir dış
  istek atmadan ve disk önbelleğine yazmadan diskten verilir.
* **Kaçış reddi.** Sembolik bağla paket dışına giden yol 403; bilinmeyen
  katman, aralık dışı z/x/y, imzası tutmayan ya da eksik dosya fail-closed.
* **İstemci kaynak sırası.** Paketli katman her zaman (tavanına kırpılmış
  z), GIBS yalnız z paketli tavanın üstündeyse istenir; tavan sunucudan
  okunamazsa paketli katman kullanılmaz. Ebeveyn yedeği (z >= 3) çizilmiş
  atayı LRU'da tutar. Büyütme notu m/px oranına bağlıdır.
* **K-3 (b).** Panel ile ekran kenarı arasında bir etiket satırından geniş
  olmayan şerit engeldir (eşik ``SATIR_PX``; eşitlik dahil).
* **K-2 eki.** Kamera 'Tüm Dünya' düğmesinin mesafesindeyken (kare
  yükündeki ``globalViewDist``) tavan 40'tır; mesafe yüklenmemişse kural
  uygulanmaz.

Sentetik yer girdileri ve küçük sentetik görüntüler TEST ALTYAPISIDIR
(fixture), kullanıcıya gösterilen veri değildir.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
for _yol in (str(KOK), str(KOK / 'tools'), str(KOK / 'tests')):
    if _yol not in sys.path:
        sys.path.insert(0, _yol)

import build_bm_pyramid as pyr  # noqa: E402
from hrma.analysis import tile_cache as tc  # noqa: E402
from test_harita_etiket import (ETIKET, GLOBE, NODE, SABLON, THREE_JS,  # noqa: E402
                                _oku, _sentetik, _yer, node_gerek)
from test_harita_s5 import _duzenek  # noqa: E402

PAKET = pathlib.Path(tc.packaged_root())
MANIFEST = PAKET / 'manifest.json'
I18N = KOK / 'hrma' / 'static' / 'js' / 'i18n_launch_site.js'


def _manifest() -> dict:
    assert MANIFEST.is_file(), 'paketli piramit manifesti yok (K4 varlığı depoda olmalı)'
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


# ===========================================================================
# 1) Paket bütünlüğü: manifest sha256 <-> dosyalar
# ===========================================================================

def test_manifest_dosyalarla_birebir():
    m = _manifest()
    diskte = sorted(str(p.relative_to(PAKET)) for p in PAKET.rglob('*')
                    if p.is_file() and p.name != 'manifest.json')
    assert diskte == sorted(m['files']), 'manifest ile dizin farklı dosya kümesi taşıyor'
    toplam = 0
    for yol, kayit in m['files'].items():
        veri = (PAKET / yol).read_bytes()
        assert len(veri) == kayit['bytes'], yol
        assert hashlib.sha256(veri).hexdigest() == kayit['sha256'], yol
        assert tc._is_valid_webp(str(PAKET / yol)), '%s WebP imzası taşımıyor' % yol
        toplam += len(veri)
    assert toplam == m['total_bytes']
    assert m['total_bytes'] <= pyr.PIRAMIT_BUTCESI_BAYT == m['budget_bytes']


def test_duzeyler_tile_cache_izgarasiyla_ayni():
    m = _manifest()
    tavan = tc.LAYERS[tc.PACKAGED_LAYER_KEY]['max_zoom']
    assert m['grid']['max_zoom'] == tavan and m['layer'] == tc.PACKAGED_LAYER_KEY
    assert sorted(int(z) for z in m['levels']) == list(range(tavan + 1))
    for z in range(tavan + 1):
        mw, mh = tc.matrix_size(z)
        d = m['levels'][str(z)]
        assert (d['matrix_width'], d['matrix_height'], d['tiles']) == (mw, mh, mw * mh)
        assert d['span_deg'] == tc.tile_span_deg(z)
        beklenen = {'%d/%d/%d.webp' % (z, x, y) for x in range(mw) for y in range(mh)}
        assert beklenen == {k for k in m['files'] if k.startswith('%d/' % z)}


def test_kunye_kaynak_ve_tarih():
    m = _manifest()
    src = m['source']
    assert src['sha256'] == pyr.KAYNAK_SHA256 and src['file'] == pyr.KAYNAK_ADI
    assert src['month'] == '2004-12' and '200412' in src['file']
    assert 'Reto St' in src['author'] and src['size_px'] == list(pyr.KAYNAK_BOYUT)


def test_gercek_kaynaktan_yeniden_uretim_paketle_ayni():
    """Karolar yalnız ham görüntüden: z0-z3 yeniden üretilir, bayt bayt eşit."""
    if not pyr.VARSAYILAN_KAYNAK.is_file():
        pytest.skip('BMNG 21600 kaynağı bu makinede yok (yapım önbelleği, depo dışı)')
    img, sha = pyr.kaynak_ac(pyr.VARSAYILAN_KAYNAK)
    dosyalar, _ = pyr.uret(img, sha, 3)
    m = _manifest()
    for yol, veri in dosyalar.items():
        assert hashlib.sha256(veri).hexdigest() == m['files'][yol]['sha256'], yol


# ===========================================================================
# 2) Araç: belirlenimcilik, Dünya dışı saydamlık, kaynak ve bütçe kapıları
# ===========================================================================

def _sentetik_kaynak(w=720, h=360):
    """Sentetik eşdikdörtgen görüntü (fixture): konuma bağlı belirlenimci renk."""
    from PIL import Image
    img = Image.new('RGB', (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256)
    return img


def test_arac_belirlenimci_ve_dunya_disi_saydam():
    img = _sentetik_kaynak()
    d1, m1 = pyr.uret(img, 'sentetik', 2)
    d2, m2 = pyr.uret(img, 'sentetik', 2)
    assert d1 == d2 and m1 == m2
    from PIL import Image
    import io
    # z0 karo 1: boylam 108..396 -> 180'in doğusu Dünya dışı: alfa 0.
    k = Image.open(io.BytesIO(d1['0/1/0.webp'])).convert('RGBA')
    span = tc.tile_span_deg(0)
    x_sinir = round((tc.WORLD_LON_E - (tc.WORLD_LON_W + span)) * pyr.KARO_PX / span)
    assert k.getpixel((x_sinir + 5, 10))[3] == 0
    assert k.getpixel((x_sinir - 5, 10))[3] == 255
    assert m1['levels']['0']['out_of_world'] == 'transparent'


def test_kaynak_kaniti_tutmazsa_dosya_yazilmaz(tmp_path):
    sahte = tmp_path / 'kaynak.jpg'
    _sentetik_kaynak(64, 32).save(sahte, 'JPEG')
    hedef = tmp_path / 'cikti'
    rc = pyr.main(['--kaynak', str(sahte), '--hedef', str(hedef)])
    assert rc == 3 and not hedef.exists()
    with pytest.raises(pyr.KaynakHatasi):
        pyr.kaynak_ac(sahte)
    # Boyut doğru, sha yanlış -> yine ret (iki kanıt ayrı ayrı aranır).
    dogru = hashlib.sha256(sahte.read_bytes()).hexdigest()
    with pytest.raises(pyr.KaynakHatasi):
        pyr.kaynak_ac(sahte, beklenen_sha='0' * 64, beklenen_boyut=(64, 32))
    img, sha = pyr.kaynak_ac(sahte, beklenen_sha=dogru, beklenen_boyut=(64, 32))
    assert sha == dogru and img.size == (64, 32)


def test_butce_asilirsa_hata_ve_yazim_yok(tmp_path):
    with pytest.raises(pyr.ButceAsildi):
        pyr.uret(_sentetik_kaynak(), 'sentetik', 2, butce=1000)


# ===========================================================================
# 3) tile_cache 'bm_local': ağsız, önbelleksiz, kaçışsız
# ===========================================================================

@pytest.fixture
def ag_yasak(monkeypatch, tmp_path):
    """Her ağ yolu patlar; disk önbelleği geçici ve boş başlar."""
    cagri = []

    def patla(*a, **k):
        cagri.append(a)
        raise AssertionError('paketli katman ağa çıktı')
    monkeypatch.setattr(tc, '_http_bytes', patla)
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', patla)
    onbellek = tmp_path / 'onbellek'
    monkeypatch.setenv('HRMA_TILE_CACHE_DIR', str(onbellek))
    return cagri, onbellek


def test_paketli_karo_agsiz_ve_onbelleksiz(ag_yasak):
    cagri, onbellek = ag_yasak
    for izin in (False, True):
        r = tc.resolve_tile('bm_local', 5, 11, 6, allow_network=izin)
        assert r['ok'] and r['mimetype'] == 'image/webp' and r.get('packaged') is True
        assert os.path.realpath(r['path']).startswith(os.path.realpath(str(PAKET)) + os.sep)
    assert cagri == []
    assert not onbellek.exists() or not any(onbellek.rglob('*'))


def test_paketli_katman_tavan_ustu_ve_gecersiz_girdi(ag_yasak):
    tavan = tc.LAYERS['bm_local']['max_zoom']
    assert tc.resolve_tile('bm_local', tavan + 1, 0, 0)['code'] == 400
    assert tc.resolve_tile('bm_local', 5, 40, 0)['code'] == 400        # x >= MatrixWidth
    assert tc.resolve_tile('bm_local', '../5', 1, 1)['code'] == 400
    assert tc.resolve_tile('../bm_local', 5, 1, 1)['code'] == 404
    assert tc.resolve_tile('bm_local', float('nan'), 1, 1)['code'] == 400


def test_paket_disina_kacis_ve_bozuk_dosya_reddedilir(ag_yasak, monkeypatch, tmp_path):
    kok = tmp_path / 'bm_pyr'
    (kok / '5' / '11').mkdir(parents=True)
    disarida = tmp_path / 'gizli.webp'
    disarida.write_bytes((PAKET / '5' / '11' / '6.webp').read_bytes())
    os.symlink(disarida, kok / '5' / '11' / '6.webp')
    (kok / '5' / '11' / '7.webp').write_bytes(b'<html>not a tile</html>')
    monkeypatch.setattr(tc, 'PACKAGED_ROOT', str(kok))
    assert tc.resolve_tile('bm_local', 5, 11, 6)['code'] == 403
    r = tc.resolve_tile('bm_local', 5, 11, 7)
    assert r['code'] == 404 and r['available'] is False
    assert tc.resolve_tile('bm_local', 5, 11, 8)['code'] == 404


def test_katalog_paketli_kaynagi_beyan_eder():
    """Paketli katman GIBS kataloğuna karışmaz ('layers' yalnız GIBS; her
    künye GIBS atfını taşır), kendi künyesiyle 'packaged' altında durur."""
    kat = tc.list_layers()
    assert 'bm_local' not in kat['layers'] and kat['layers']['bluemarble']['source'] == 'gibs'
    p = kat['packaged']['bm_local']
    assert p['source'] == 'packaged' and p['ui_offered'] is True and p['max_zoom'] == 5
    assert 'GIBS' not in p['attribution'] and '2004' in p['attribution']
    assert kat['packaged_basis']


# ===========================================================================
# 4) İstemci: kaynak sırası, ebeveyn yedeği, büyütme notu (node, gerçek modül)
# ===========================================================================

KURE_DUZENEK = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [GLOBE_JS, DURUM_JSON, GOREV_JSON] = process.argv.slice(2);
class V3 {
    constructor(x, y, z) { this.x = x || 0; this.y = y || 0; this.z = z || 0; }
    length() { return Math.hypot(this.x, this.y, this.z); }
    clone() { return new V3(this.x, this.y, this.z); }
    normalize() { const l = this.length() || 1; this.x /= l; this.y /= l; this.z /= l; return this; }
    multiplyScalar(s) { this.x *= s; this.y *= s; this.z *= s; return this; }
    distanceTo(o) { return Math.hypot(this.x - o.x, this.y - o.y, this.z - o.z); }
    set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; }
}
let saat = 0;
const durum = JSON.parse(fs.readFileSync(DURUM_JSON, 'utf8'));
const gorev = JSON.parse(fs.readFileSync(GOREV_JSON, 'utf8'));
const ctx = { console, Math, JSON, Promise, THREE: { Vector3: V3 },
              performance: { now: () => saat },
              fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(durum) }) };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(GLOBE_JS, 'utf8'), ctx);
const G = ctx.LaunchSiteGlobe;
const M_PER_UNIT = 6371000 / 100;
function kure() {
    const istek = [];
    const k = Object.assign(Object.create(G.prototype), {
        _tiles: new Map(), _tileNextT: 0, _tileAnyFail: false, _merkezDoku: null,
        camera: { position: new V3(), fov: 38 }, controls: { target: new V3() },
        container: { clientHeight: gorev.H },
    });
    k._buildTilePatch = function (layer, z, tx, ty) {
        istek.push(layer + ':' + z);
        this._tiles.set(layer + ':' + z + ':' + tx + ':' + ty,
                        { mesh: gorev.ciz.includes(layer) ? {} : null,
                          loading: !gorev.ciz.includes(layer) });
    };
    k._disposeTileEntry = function () {};
    return [k, istek];
}
function poz(k, lat, lon, altM) {
    const n = G.latLonToVec3(lat, lon, 100).normalize();
    k.controls.target = n.clone().multiplyScalar(100);
    k.camera.position = n.clone().multiplyScalar(100 + altM / M_PER_UNIT);
}
(async () => {
    const out = {};
    const [k, istek] = kure();
    poz(k, 42.0, 35.1, gorev.altM);
    k._updateTilePatch();                         // geometri yok -> istek yok, yükleme başlar
    out.ilkTur = istek.length;
    await new Promise(r => setTimeout(r, 0));
    for (const on of (gorev.onceden || [])) k._tiles.set(on, { mesh: {} });
    saat += 1000; k._tileNextT = 0;
    k._updateTilePatch();
    const say = {};
    istek.forEach(s => { say[s] = (say[s] || 0) + 1; });
    out.istek = say;
    out.sira = [...k._tiles.keys()];
    out.scale = k.getScaleInfo();
    out.tileInfo = k.getTileInfo();
    process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(2); });
"""


def _kure(tmp_path, altM, katalog=True, ciz=(), onceden=(), H=845):
    durum = {'tile_matrix': tc.matrix_geometry(), 'network_opt_in': {'param': 'net', 'value': '1'}}
    if katalog:
        durum['layers'] = tc.list_layers()
    js = tmp_path / 'kure_k4.js'
    js.write_text(KURE_DUZENEK, encoding='utf-8')
    (tmp_path / 'durum.json').write_text(json.dumps(durum), encoding='utf-8')
    (tmp_path / 'gorev.json').write_text(json.dumps({'altM': altM, 'ciz': list(ciz), 'H': H,
                                                     'onceden': list(onceden)}), encoding='utf-8')
    r = subprocess.run([NODE, str(js), str(GLOBE), str(tmp_path / 'durum.json'),
                        str(tmp_path / 'gorev.json')], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@node_gerek
def test_kaynak_sirasi_yakin_zoomda_paketli_arti_gibs(tmp_path):
    # 400 km, tuval 845 px: 326 m/px -> z = 7 (> paketli tavan 5).
    r = _kure(tmp_path, 400000)
    assert r['ilkTur'] == 0
    assert r['istek'] == {'bm_local:5': 25, 'bluemarble:7': 25}


@node_gerek
def test_kaynak_sirasi_tavan_ve_altinda_gibs_istenmez(tmp_path):
    # 1.490 km, tuval 600 px: ~1.710 m/px -> z = 5 = paketli tavan: yalnız
    # paketli katman; aynı 2004 verisi için dış GIBS isteği atılmaz.
    r = _kure(tmp_path, 1490000, H=600)
    assert r['istek'] == {'bm_local:5': 25}
    # Aynı yükseklik 845 px'te z = 6: paketli z5 + GIBS z6.
    r = _kure(tmp_path, 1490000)
    assert r['istek'] == {'bm_local:5': 25, 'bluemarble:6': 25}


@node_gerek
def test_paketli_tavan_okunamazsa_paketli_katman_kullanilmaz(tmp_path):
    r = _kure(tmp_path, 400000, katalog=False)
    assert r['istek'] == {'bluemarble:7': 25}


@node_gerek
def test_ebeveyn_yedegi_cizilmis_atayi_lru_sonuna_tasir(tmp_path):
    # z5 çocuklar henüz çizilmedi; merkez karonun z4 atası (bm_local:4) ve
    # z3 atası çizilmiş. Ata LRU'da tazelenir (Map'in sonuna taşınır).
    lon, lat = 35.1, 42.0
    span5 = tc.tile_span_deg(5)
    x5, y5 = int((lon + 180) // span5), int((90 - lat) // span5)
    ata4 = 'bm_local:4:%d:%d' % (x5 // 2, y5 // 2)
    ata3 = 'bm_local:3:%d:%d' % (x5 // 4, y5 // 4)
    r = _kure(tmp_path, 1490000, onceden=[ata3, ata4, 'bm_local:4:0:0'])
    sira = r['sira']
    assert sira.index(ata4) > sira.index('bm_local:4:0:0'), 'ata LRU sonuna taşınmadı'
    # Merkezdeki en ince çizilen doku atadır (z4, paketli); not ve künye ondan.
    assert r['scale']['textureLayer'] == 'bm_local'
    assert r['tileInfo']['attributionKey'] == 'site.tilePackagedAttribution'


@node_gerek
def test_buyutme_notu_mpx_oranina_bagli(tmp_path):
    vakalar = {
        # 400 km (326 m/px): yalnız paketli z5 çizili (1.957 m/px) -> büyütme
        'paketli_400': (_kure(tmp_path, 400000, ciz=['bm_local']), True, 'bm_local'),
        # 400 km: GIBS z7 de çizili (~489 m/px) < 2 x 326 -> not yok
        'gibs_400': (_kure(tmp_path, 400000, ciz=['bm_local', 'bluemarble']), False, 'bluemarble'),
        # 1.490 km (1.214 m/px): paketli z5 1.957 < 2 x 1.214 -> not yok
        'paketli_1490': (_kure(tmp_path, 1490000, ciz=['bm_local']), False, 'bm_local'),
        # hiç karo çizili değil: not yok, katman null
        'bos_400': (_kure(tmp_path, 400000), False, None),
    }
    for ad, (r, beklenen, katman) in vakalar.items():
        s = r['scale']
        assert s['textureMagnified'] is beklenen, (ad, s)
        assert s['textureLayer'] == katman, (ad, s)
        if s['textureMpp']:
            assert s['textureMagnified'] == (s['textureMpp'] > 2 * s['metersPerPixel'])


def test_sablon_notu_textcontent_ve_anahtarlar_iki_dilde():
    s = _oku(SABLON)
    assert 'id="ls-texmag"' in s
    govde = s[s.index('function renderTextureMagNote'):]
    govde = govde[:govde.index('\n    }\n')]
    assert 'n.textContent = ' in govde and 'innerHTML' not in govde
    i18n = _oku(I18N)
    for anahtar in ('site.textureMagnifiedPackaged', 'site.textureMagnifiedOnline',
                    'site.tilePackagedAttribution', 'site.vectorShiftMeasured'):
        assert i18n.count("'%s':" % anahtar) == 2, anahtar


# ===========================================================================
# 5) K-3 (b) kenar şeridi ve K-2 eki (etiket modülü, node)
# ===========================================================================

def _etiket_kos(tmp_path, adimlar):
    s = _duzenek()
    eski = "camAltitudeM: k.d * 1000, size: { width: W, height: H }, globeRadius: R };"
    assert s.count(eski) == 1
    s = s.replace(eski, "camAltitudeM: k.d * 1000, size: { width: W, height: H }, globeRadius: R,"
                        " globalViewDist: k.gvdOran ? dU * k.gvdOran : undefined };")
    js = tmp_path / 'duzenek_k4.js'
    js.write_text(s, encoding='utf-8')
    g = tmp_path / 'gorev.json'
    g.write_text(json.dumps({'adimlar': adimlar}), encoding='utf-8')
    env = dict(os.environ, HRMA_VEKTOR=str(KOK / 'hrma' / 'static' / 'js' / 'launch_site_vectors.js'))
    r = subprocess.run([NODE, str(js), str(THREE_JS), str(GLOBE), str(ETIKET), str(g)],
                       capture_output=True, text=True, timeout=240, env=env)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


@node_gerek
def test_kenar_seridi_bir_satirdan_genis_degilse_engeldir(tmp_path):
    """Sayfada paneller kenardan 14 px içeride (ölçüldü). Üst kenarı ekrandan
    taşan ve paneli 6 px payla geçen yeni etiket bu şeritte iki kare görünüp
    kayboluyordu (K-3: Giresun, Mahabad). Şerit <= SATIR_PX ise kutu kenara
    uzar; 15 px'lik şerit uzamaz."""
    W, H = 1440, 845
    adim = []
    enlemler = [40.0 + 0.05 * i for i in range(400)]
    for i, la in enumerate(enlemler):
        d = _sentetik(tmp_path / ('m%d' % i), [_yer('Kenar', 30, la, 2.0, ne_id=1)])
        adim += [{'op': 'kur', 'dizin': str(d)},
                 {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0, 'W': W, 'H': H}]
    r = _etiket_kos(tmp_path, adim)
    kareler = r[1::2]
    aday = [i for i, s in enumerate(kareler)
            if s['yer'] and 0 < s['yer'][0]['y1'] <= 8 and s['yer'][0]['y0'] < 0]
    assert aday, 'düzenek üst kenarı taşan etiket üretemedi'
    i = aday[0]
    x0 = kareler[i]['yer'][0]['x0']
    sonuc = {}
    for serit in (14, 15, 30):
        panel = [[x0 - 100, serit, x0 + 200, 400]]
        r2 = _etiket_kos(tmp_path, [{'op': 'kur', 'dizin': str(tmp_path / ('m%d' % i)), 'engeller': panel},
                                    {'op': 'kare', 'lat': 40, 'lon': 30, 'd': 3000, 'z': 4.0, 'W': W, 'H': H}])
        sonuc[serit] = [p['ad'] for p in r2[1]['yer']]
        assert r2[1]['info']['engel'] == 1
    assert sonuc == {14: [], 15: ['Kenar'], 30: ['Kenar']}


@node_gerek
def test_kenara_yasla_dort_kenar(tmp_path):
    kod = ("const fs=require('fs'),vm=require('vm');const ctx={console,Math,JSON};ctx.window=ctx;"
           "vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),ctx);"
           "const L=ctx.LaunchSiteLabels,o=[0,0,0,0];"
           "const f=(e)=>Array.from(L.kenaraYasla(e,1440,845,o));"
           "process.stdout.write(JSON.stringify({s:L.KENAR_SERIDI_PX,"
           "a:f([14,14,302,751]),b:f([15,15,1425,830]),c:f([0,-55,1440,0]),d:f([1126,14,1426,395])}));")
    js = tmp_path / 'yasla.js'
    js.write_text(kod, encoding='utf-8')
    r = subprocess.run([NODE, str(js), str(ETIKET)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d['s'] == 14
    assert d['a'] == [0, 0, 302, 751]          # sol ve üst 14 px -> kenara
    assert d['b'] == [15, 15, 1425, 830]       # 15 px şerit -> değişmez
    assert d['c'] == [0, -55, 1440, 0]         # ekran dışı kutu değişmez
    assert d['d'] == [1126, 0, 1440, 395]      # sağ ve üst 14 px -> kenara


@node_gerek
def test_kare_yuku_tum_dunya_mesafesini_tasir(tmp_path):
    """K-2 ekinin kaynağı: kare yükündeki globalViewDist, 'Tüm Dünya'
    düğmesinin mesafesidir. Bağımsız kâhin: tarayıcıda 1440x900 (tuval
    1440x845) viewGlobe sonrası kameranın Dünya merkezine uzaklığı ölçüldü:
    383,94418584465535 birim (t5/k2_sonra.json) = 100 / sin(19°) x 1,25."""
    kod = r"""
const fs=require('fs'),vm=require('vm');
class V3{constructor(x,y,z){this.x=x||0;this.y=y||0;this.z=z||0;}
 length(){return Math.hypot(this.x,this.y,this.z);} distanceTo(o){return Math.hypot(this.x-o.x,this.y-o.y,this.z-o.z);}}
const ctx={console,Math,JSON,THREE:{Vector3:V3}};ctx.window=ctx;vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),ctx);
const G=ctx.LaunchSiteGlobe; let yuk=null;
const k=Object.assign(Object.create(G.prototype),{camera:{position:new V3(0,0,300),fov:38,aspect:1440/845},
  controls:{target:new V3()},container:{clientWidth:1440,clientHeight:845},_frameListeners:[]});
k.addFrameListener(f=>{yuk=f.globalViewDist;}); k._emitFrame();
process.stdout.write(JSON.stringify({gvd:yuk}));
"""
    js = tmp_path / 'kare_yuku.js'
    js.write_text(kod, encoding='utf-8')
    r = subprocess.run([NODE, str(js), str(GLOBE)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    import math
    kahin = 100.0 / math.sin(math.radians(19.0)) * 1.25
    assert abs(kahin - 383.94418584465535) < 1e-9
    assert abs(json.loads(r.stdout)['gvd'] - kahin) < 1e-9


@node_gerek
def test_tum_dunya_mesafesinde_tavan_40(tmp_path):
    """'Tüm Dünya' düğmesi 1440x900'de 19.935 m/px veriyordu (bandın %0,3
    altı): Sinop 66-73 etiket ölçüldü. Kamera düğmenin mesafesindeyken tavan
    40; mesafe yükte yoksa ya da kamera daha yakınsa kural uygulanmaz."""
    from test_harita_s5 import TUVAL_H, TUVAL_W, VARLIK_DIZIN
    poz = {'op': 'kare', 'lat': 42.0, 'lon': 35.1, 'merkez': True, 'mpp': 19935,
           'W': TUVAL_W, 'H': TUVAL_H}
    isit = dict(poz, mpp=14751)
    adim = [{'op': 'kur', 'dizin': str(VARLIK_DIZIN), 'dil': 'tr'}, isit, dict(poz, gvdOran=1.0),
            isit, dict(poz, gvdOran=1.001), isit, dict(poz)]
    r = _etiket_kos(tmp_path, adim)
    esit, yakin, yok = r[2], r[4], r[6]
    assert esit['info']['tavan'] == 40 and len(esit['yer']) <= 40 and esit['info']['tavanGizli'] > 0
    assert yakin['info']['tavan'] == 150 and len(yakin['yer']) > 40
    assert yok['info']['tavan'] == 150


def test_kiyi_kaymasi_notu_olcum_kanitiyla_ayni():
    """§5.3-1: ekrandaki kayma sayıları ölçüm kanıtının kendisidir (uydurma yok)."""
    import re
    from support.kanit import kanit_gerekli, kanit_yolu
    # ÖH 15 Eki (ana model; yayın kapısı): kanıt tarayıcısı
    # (test_kanit_atlama_kapisi::test_b, docs'suz CI'de de koşar)
    # kanit_yolu('docs/…') dize tohumunu kapı dışı okuma sayıyor; depodaki
    # kalıp: yol parçalarla kurulur, okumadan hemen önce kapıdan geçer.
    yol = (KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'UI' / 'harita-detay'
           / 't5' / 'kayma' / 'kayma.json')
    k = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))
    m = re.search(r'var KIYI_KAYMASI_OLCUMU = \{ medyanM: (\d+), p90M: (\d+), cozunurlukM: (\d+) \};',
                  _oku(SABLON))
    assert m, 'kayma ölçüm sabiti şablonda yok'
    satir = k['satir_dis_kiyi']
    assert (int(m.group(1)), int(m.group(2)), int(m.group(3))) == (
        satir['medyan_m'], satir['p90_m'], k['cozunurluk_m']['enlem'])
    assert k['karo']['z'] == 7 and (k['karo']['x'], k['karo']['y']) == (44, 27)
