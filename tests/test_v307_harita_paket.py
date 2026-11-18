# -*- coding: utf-8 -*-
"""V307 / FS-HARİTA-VERİ faz 2 — indirilebilir harita paketleri (sunucu tarafı, Parça S).

Kapsam: PMTiles v3 okuma/yazma gidiş-dönüş ve sınırları; MVT çözücü sınırları (bozuk ve
şişirilmiş girdi ADIYLA reddedilir); paket listesi doğrulaması; indirme yöneticisi (yerel
HTTP fikstürü: rıza yok -> istek yok, Range ile devam, sha256 uyuşmazlığı, kesik indirme,
fazla bayt, iptal, disk dolu, izin listesi dışı adres/yönlendirme); çizim belirlenimciliği
ve 404 yolu; zemin sağlayıcı bağlantı noktası; ad politikası (K6); karo katmanı ve uçlar;
depodaki paket listesinin künyesi ve lisans bildirimi.
"""
import gzip
import hashlib
import http.server
import io
import json
import os
import pathlib
import socketserver
import threading
import time
import urllib.request

import pytest

from hrma.analysis import map_packs as MP
from hrma.analysis import tile_cache as tc

KOK = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Test yardımcıları: asgari MVT kodlayıcı
# ---------------------------------------------------------------------------

def _v(x):
    out = bytearray()
    while True:
        b = x & 0x7F
        x >>= 7
        if x:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _alan(no, tip, veri):
    if tip == 0:
        return _v((no << 3) | 0) + _v(veri)
    return _v((no << 3) | 2) + _v(len(veri)) + veri


def _zz(n):
    return (n << 1) ^ (n >> 63)


def _komut(noktalar, kapali=False, nokta=False):
    out, px, py = [], 0, 0
    x, y = noktalar[0]
    out += [(1 << 3) | 1, _zz(x - px), _zz(y - py)]
    px, py = x, y
    if not nokta:
        out.append(((len(noktalar) - 1) << 3) | 2)
        for x, y in noktalar[1:]:
            out += [_zz(x - px), _zz(y - py)]
            px, py = x, y
    if kapali:
        out.append((1 << 3) | 7)
    return out


def mvt_kodla(katmanlar, extent=4096):
    """{ad: [(gtip, {anahtar: değer}, noktalar)]} -> düz MVT baytı."""
    tile = b''
    for ad, ozler in katmanlar.items():
        anahtarlar, degerler, govde = [], [], b''
        for gtip, oz, nok in ozler:
            etiket = []
            for k, v in oz.items():
                if k not in anahtarlar:
                    anahtarlar.append(k)
                if v not in degerler:
                    degerler.append(v)
                etiket += [anahtarlar.index(k), degerler.index(v)]
            geo = _komut(nok, kapali=(gtip == 3), nokta=(gtip == 1))
            f = _alan(2, 2, b''.join(_v(t) for t in etiket)) + _alan(3, 0, gtip) + \
                _alan(4, 2, b''.join(_v(c) for c in geo))
            govde += _alan(2, 2, f)
        katman = _alan(15, 0, 2) + _alan(1, 2, ad.encode()) + govde
        for k in anahtarlar:
            katman += _alan(3, 2, k.encode())
        for v in degerler:
            dv = _alan(1, 2, v.encode()) if isinstance(v, str) else _alan(5, 0, v)
            katman += _alan(4, 2, dv)
        katman += _alan(5, 0, extent)
        tile += _alan(3, 2, katman)
    return tile


def gz(b):
    return gzip.compress(b, 9, mtime=0)


# Sentetik saha: Sinop yakını
LAT, LON = 42.0264, 35.1551
GZ = 12                                        # küre karosu düzeyi
SP = tc.tile_span_deg(GZ)
GX, GY = int((LON + 180) // SP), int((90 - LAT) // SP)


def _ornek_karolar():
    """Küre karosu GZ/GX/GY'yi kapsayan MVT karoları (yol + su + bina + yer adları)."""
    w, s, e, n = tc.tile_to_bbox(GZ, GX, GY)
    vz = MP.vektor_zoom(GZ, (s + n) / 2)
    x0, y0 = MP.merc_karo(w, n, vz)
    x1, y1 = MP.merc_karo(e, s, vz)
    karolar = {}
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            lay = {
                'roads': [(2, {'kind': 'highway', 'min_zoom': 6}, [(0, 2048), (4096, 2048)]),
                          (2, {'kind': 'minor_road'}, [(2048, 0), (2048, 4096)])],
                'water': [(3, {'kind': 'water'}, [(100, 100), (900, 100), (900, 900), (100, 900)])],
                'buildings': [(3, {'kind': 'building'}, [(3000, 3000), (3200, 3000), (3200, 3200)])],
                'places': [(1, {'kind': 'locality', 'name': 'Köy%d%d' % (x % 10, y % 10),
                                'name:en': 'Village%d%d' % (x % 10, y % 10), 'min_zoom': 11},
                            [(1024, 1024)]),
                           (1, {'kind': 'neighbourhood', 'name': 'Mahalle%d%d' % (x % 10, y % 10),
                                'min_zoom': 12}, [(1100, 1100)]),
                           (1, {'kind': 'country', 'name': 'Ülke'}, [(1500, 1500)])],
                'pois': [(1, {'kind': 'launch_complex', 'name': 'Rampa A', 'name:tr': 'Rampa A (TR)',
                              'min_zoom': 12}, [(2500, 2500)]),
                         (1, {'kind': 'restaurant', 'name': 'Lokanta'}, [(2600, 2600)])],
            }
            karolar[MP.zxy_tileid(vz, x, y)] = gz(mvt_kodla(lay))
    # düşük düzey: tek karo
    karolar[MP.zxy_tileid(0, 0, 0)] = gz(mvt_kodla({'earth': [(3, {'kind': 'earth'},
                                                                [(0, 0), (10, 0), (10, 10)])]}))
    return karolar, vz


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Yalıtılmış kurulum dizini + liste + karo önbelleği + sentetik paket dosyası."""
    kurulum = tmp_path / 'maps'
    kurulum.mkdir()
    monkeypatch.setattr(MP, '_KURULUM_DIZINI_SAGLAYICI', lambda: str(kurulum))
    monkeypatch.setenv('HRMA_TILE_CACHE_DIR', str(tmp_path / 'tiles'))
    karolar, vz = _ornek_karolar()
    paket = tmp_path / 'kaynak.pmtiles'
    bbox = MP.daire_bbox(LAT, LON, 30.0)
    MP.pmtiles_yaz(str(paket), karolar, {'name': 'test'}, bbox)
    veri = paket.read_bytes()
    sha = hashlib.sha256(veri).hexdigest()
    m = {'schema': MP.MANIFEST_SCHEMA, 'release_tag': 'harita-paketleri-test',
         'packs': [{'id': 'sinop_test', 'kind': 'site', 'name_key': 'site.mapPackName.sinop_test',
                    'bbox': [round(v, 6) for v in bbox], 'zoom_max': 15,
                    'components': [{'kind': 'vector', 'file': 'hrma-harita-sinop_test-v1.pmtiles',
                                    'size_bytes': len(veri), 'sha256': sha, 'license': 'ODbL-1.0',
                                    'attribution': '(c) OpenStreetMap contributors'}]}]}
    man = tmp_path / 'harita_paketleri.json'
    man.write_text(json.dumps(m), encoding='utf-8')
    monkeypatch.setattr(MP, 'MANIFEST_PATH', str(man))
    MP._manifest_cache.clear()
    MP._durumlar.clear()
    MP._dogrulama_cache.clear()
    for yol in list(MP._okuyucular):
        MP._okuyucu_birak(yol)
    monkeypatch.setattr(MP, '_ZEMIN_SAGLAYICI', None)
    yield {'tmp': tmp_path, 'kurulum': kurulum, 'veri': veri, 'sha': sha, 'manifest': m,
           'karolar': karolar, 'vz': vz, 'dosya': 'hrma-harita-sinop_test-v1.pmtiles'}
    for yol in list(MP._okuyucular):
        MP._okuyucu_birak(yol)
    MP._manifest_cache.clear()
    MP._durumlar.clear()


def _kur(ortam):
    """Paketi doğrudan kur (indirme yolu ayrı testlerde)."""
    hedef = ortam['kurulum'] / ortam['dosya']
    hedef.write_bytes(ortam['veri'])
    return hedef


# ---------------------------------------------------------------------------
# 1) PMTiles gidiş-dönüş ve sınırlar
# ---------------------------------------------------------------------------

def test_pmtiles_gidis_donus_ve_dedup(tmp_path):
    ayni = gz(b'\x1a\x00')
    karolar = {MP.zxy_tileid(3, x, y): gz(mvt_kodla({'a': [(1, {'k': 'v%d%d' % (x, y)}, [(1, 1)])]}))
               for x in range(8) for y in range(8)}
    karolar[MP.zxy_tileid(5, 1, 1)] = ayni
    karolar[MP.zxy_tileid(5, 1, 2)] = ayni
    yol = tmp_path / 'a.pmtiles'
    oz = MP.pmtiles_yaz(str(yol), karolar, {'name': 'x'}, (0, 0, 1, 1))
    assert oz['contents'] == len(karolar) - 1          # iki aynı içerik tek kez
    r = MP.PMTilesOkuyucu(str(yol))
    try:
        for t, b in karolar.items():
            z = MP.tileid_zoom(t)
            off, ln = r.bul(t)
            assert r._oku(r.h['tile_data_offset'] + off, ln) == b
        assert r.karo(3, 2, 5) == karolar[MP.zxy_tileid(3, 2, 5)]
        assert r.karo(4, 0, 0) is None
        assert r.meta() == {'name': 'x'}
        assert len(r.girdiler()) >= 1
    finally:
        r.kapat()
    # Belirlenimci: aynı girdi aynı bayt
    yol2 = tmp_path / 'b.pmtiles'
    MP.pmtiles_yaz(str(yol2), karolar, {'name': 'x'}, (0, 0, 1, 1))
    assert yol.read_bytes() == yol2.read_bytes()


def test_pmtiles_yaprak_dizinleri(tmp_path):
    """Kök dizin 16 KiB'a sığmayınca yaprak dizinleri kurulur ve okunur."""
    import random
    rnd = random.Random(7)
    karolar = {}
    for i in range(30000):
        t = MP.zoom_tabani(12) + rnd.randrange(16 ** 6)
        karolar[t] = bytes([rnd.randrange(256) for _ in range(rnd.randrange(1, 40))])
    yol = tmp_path / 'y.pmtiles'
    oz = MP.pmtiles_yaz(str(yol), karolar, {}, (0, 0, 1, 1), tile_compression=1)
    assert oz['leaf_dir_bytes'] > 0
    r = MP.PMTilesOkuyucu(str(yol))
    try:
        for t in list(karolar)[:500]:
            off, ln = r.bul(t)
            assert r._oku(r.h['tile_data_offset'] + off, ln) == karolar[t]
    finally:
        r.kapat()


def test_akis_yazici_ayni_bayt_ve_sira_kapisi(tmp_path):
    """Bölge paketleri için akış yazıcı: sözlük yazıcısıyla bayt bayt aynı; sırasız girdi ret."""
    karolar = {MP.zxy_tileid(4, x, y): gz(mvt_kodla({'a': [(1, {'k': 'v%d' % (x * y)}, [(x, y)])]}))
               for x in range(16) for y in range(16)}
    a = tmp_path / 'a.pmtiles'
    b = tmp_path / 'b.pmtiles'
    MP.pmtiles_yaz(str(a), karolar, {'n': 1}, (0, 0, 1, 1))
    oz = MP.pmtiles_yaz_akis(str(b), ((t, karolar[t]) for t in sorted(karolar)), {'n': 1}, (0, 0, 1, 1))
    assert a.read_bytes() == b.read_bytes()
    assert oz['max_tile_bytes'] == max(len(v) for v in karolar.values())
    assert not (tmp_path / 'b.pmtiles.veri.part').exists()
    with pytest.raises(MP.PaketHatasi) as e:
        MP.pmtiles_yaz_akis(str(tmp_path / 'c.pmtiles'), iter([(5, b'x'), (3, b'y')]), {}, (0, 0, 1, 1))
    assert e.value.kod == 'tiles_not_sorted'


@pytest.mark.parametrize('bozma,kod', [
    (lambda b: b'XXTiles' + b[7:], 'not_pmtiles'),
    (lambda b: b[:7] + bytes([2]) + b[8:], 'unsupported_pmtiles_version'),
    (lambda b: b[:99] + bytes([2]) + b[100:], 'unsupported_tile_type'),
    (lambda b: b[:64] + (10 ** 9).to_bytes(8, 'little') + b[72:], 'section_out_of_file'),
    (lambda b: b[:8] + (20000).to_bytes(8, 'little') + b[16:], 'section_out_of_file'),
])
def test_pmtiles_bozuk_baslik_adiyla_reddedilir(tmp_path, bozma, kod):
    yol = tmp_path / 'a.pmtiles'
    MP.pmtiles_yaz(str(yol), {0: gz(b'\x1a\x00')}, {}, (0, 0, 1, 1))
    yol.write_bytes(bozma(yol.read_bytes()))
    with pytest.raises(MP.PaketHatasi) as e:
        MP.PMTilesOkuyucu(str(yol))
    assert e.value.kod == kod


def test_pmtiles_sisirilmis_dizin_ve_karo(tmp_path, monkeypatch):
    yol = tmp_path / 'a.pmtiles'
    karolar = {MP.zxy_tileid(2, x, 0): gz(bytes(5000)) for x in range(4)}
    MP.pmtiles_yaz(str(yol), karolar, {}, (0, 0, 1, 1))
    monkeypatch.setattr(MP, 'MAX_DIR_BYTES', 4)
    with pytest.raises(MP.PaketHatasi) as e:
        MP.PMTilesOkuyucu(str(yol))
    assert e.value.kod == 'directory_too_large'
    monkeypatch.setattr(MP, 'MAX_DIR_BYTES', 64 * 1024 * 1024)
    r = MP.PMTilesOkuyucu(str(yol))
    monkeypatch.setattr(MP, 'MAX_TILE_BYTES', 10)
    try:
        with pytest.raises(MP.PaketHatasi) as e:
            r.karo(2, 1, 0)
        assert e.value.kod == 'tile_too_large'
    finally:
        r.kapat()


def test_dizin_kesik_ve_hatali():
    with pytest.raises(MP.PaketHatasi) as e:
        MP.dizin_coz(_v(50) + b'\x01\x01')
    assert e.value.kod == 'directory_truncated'
    with pytest.raises(MP.PaketHatasi) as e:
        MP.dizin_coz(_v(1) + _v(0) + _v(1) + _v(5) + _v(0))   # ilk girdinin ofseti 0 (önceki yok)
    assert e.value.kod == 'directory_bad_offset'


# ---------------------------------------------------------------------------
# 2) MVT çözücü sınırları
# ---------------------------------------------------------------------------

def test_mvt_cozucu_dogru_ve_suzgecli():
    ham = mvt_kodla({'roads': [(2, {'kind': 'highway'}, [(0, 0), (10, 5), (20, 0)])],
                     'places': [(1, {'name': 'A', 'min_zoom': 9}, [(7, 8)])]})
    L = MP.mvt_coz(gz(ham))
    assert L['roads']['features'][0][2] == [[(0, 0), (10, 5), (20, 0)]]
    assert L['places']['features'][0][1] == {'name': 'A', 'min_zoom': 9}
    assert set(MP.mvt_coz(ham, frozenset({'places'}))) == {'places'}


@pytest.mark.parametrize('veri,kod', [
    (mvt_kodla({'a': [(1, {}, [(1, 1)])]})[:-3], 'mvt_truncated'),
    (b'\x1b\x00', 'mvt_bad_wire_type'),
    (_alan(3, 2, _alan(1, 2, b'a') + _alan(2, 2, _alan(4, 2, _v((1 << 3) | 4))) + _alan(5, 0, 4096)),
     'mvt_bad_command'),
    (_alan(3, 2, _alan(1, 2, b'a') + _alan(2, 2, _alan(4, 2, _v((5 << 3) | 1) + _v(2)))),
     'mvt_bad_geometry'),
    (_alan(3, 2, _alan(1, 2, b'a') + _alan(5, 0, 0)), 'mvt_bad_extent'),
])
def test_mvt_bozuk_girdi_adiyla_reddedilir(veri, kod):
    with pytest.raises(MP.PaketHatasi) as e:
        MP.mvt_coz(veri)
    assert e.value.kod == kod


def test_mvt_sisirilmis_girdi(monkeypatch):
    bomba = gz(b'\x00' * (2 * 1024 * 1024))
    monkeypatch.setattr(MP, 'MAX_MVT_BYTES', 1024 * 1024)
    with pytest.raises(MP.PaketHatasi) as e:
        MP.mvt_coz(bomba)
    assert e.value.kod == 'mvt_too_large'
    cok = b''.join(_alan(3, 2, _alan(1, 2, b'k%d' % i)) for i in range(5))
    monkeypatch.setattr(MP, 'MAX_LAYERS', 4)
    with pytest.raises(MP.PaketHatasi) as e:
        MP.mvt_coz(cok)
    assert e.value.kod == 'mvt_too_many_layers'
    monkeypatch.setattr(MP, 'MAX_LAYERS', 64)
    monkeypatch.setattr(MP, 'MAX_FEATURES', 3)
    with pytest.raises(MP.PaketHatasi) as e:
        MP.mvt_coz(mvt_kodla({'a': [(1, {}, [(i, i)]) for i in range(4)]}))
    assert e.value.kod == 'mvt_too_many_features'


def test_landcover_katmani_silinir_digerleri_bayt_ayni():
    a = mvt_kodla({'earth': [(3, {}, [(0, 0), (5, 0), (5, 5)])]})
    b = mvt_kodla({'landcover': [(3, {'kind': 'forest'}, [(0, 0), (5, 0), (5, 5)])]})
    c = mvt_kodla({'water': [(3, {}, [(1, 1), (4, 1), (4, 4)])]})
    kaynak = gz(a + b + c)
    cikti = MP.mvt_katman_sil(kaynak, frozenset({'landcover'}))
    assert gzip.decompress(cikti) == a + c
    assert MP.mvt_katman_sil(gz(a + c), frozenset({'landcover'})) == gz(a + c)


# ---------------------------------------------------------------------------
# 3) Paket listesi doğrulaması
# ---------------------------------------------------------------------------

def _liste():
    return {'schema': MP.MANIFEST_SCHEMA, 'release_tag': 'harita-paketleri-v1',
            'packs': [{'id': 'a1', 'kind': 'site', 'name_key': 'k', 'bbox': [1, 2, 3, 4], 'zoom_max': 15,
                       'components': [{'kind': 'vector', 'file': 'a1.pmtiles', 'size_bytes': 10,
                                       'sha256': '0' * 64, 'license': 'ODbL-1.0', 'attribution': 'x'}]}]}


@pytest.mark.parametrize('boz', [
    lambda m: m.update(schema='x'),
    lambda m: m.update(release_tag='../x'),
    lambda m: m['packs'][0].update(id='../a'),
    lambda m: m['packs'].append(dict(m['packs'][0])),
    lambda m: m['packs'][0].update(bbox=[3, 2, 1, 4]),
    lambda m: m['packs'][0].update(zoom_max=16),
    lambda m: m['packs'][0]['components'][0].update(file='../../a.pmtiles'),
    lambda m: m['packs'][0]['components'][0].update(size_bytes=2 ** 31),
    lambda m: m['packs'][0]['components'][0].update(sha256='abc'),
    lambda m: m['packs'][0]['components'][0].update(license=''),
    lambda m: m['packs'][0]['components'][0].update(kind='other'),
    lambda m: m['packs'][0]['components'][0].update(file='a1.sqlite'),
    lambda m: m['packs'][0]['components'].append(
        {'kind': 'vector', 'file': 'b.pmtiles', 'size_bytes': 1, 'sha256': '1' * 64,
         'license': 'x', 'attribution': 'y'}),
])
def test_liste_dogrulama_ihlali_adiyla(boz):
    m = _liste()
    boz(m)
    with pytest.raises(MP.PaketHatasi) as e:
        MP.manifest_dogrula(m)
    assert e.value.kod == 'bad_manifest'


def test_liste_goruntu_bileseni_bicimde_tanimli():
    """Görüntü bileşeni (kind=imagery, .sqlite) sonradan eklenebilir (karar K2)."""
    m = _liste()
    m['packs'][0]['components'].append({'kind': 'imagery', 'file': 'a1-goruntu.sqlite',
                                        'size_bytes': 5, 'sha256': '2' * 64,
                                        'license': 'Copernicus', 'attribution': 'c'})
    MP.manifest_dogrula(m)
    assert MP.paket_boyutu(m['packs'][0]) == 15
    assert MP.vektor_bileseni(m['packs'][0])['file'] == 'a1.pmtiles'


# ---------------------------------------------------------------------------
# 4) İndirme yöneticisi — yerel HTTP fikstürü
# ---------------------------------------------------------------------------

class _Sunucu:
    def __init__(self, veri):
        self.veri = veri
        self.kip = 'normal'
        self.istekler = []
        sahip = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def log_message(self, *a):
                pass

            def do_GET(self):
                sahip.istekler.append((self.path, self.headers.get('Range')))
                v = sahip.veri
                if sahip.kip == 'yonlendir':
                    self.send_response(302)
                    self.send_header('Location', 'http://evil.invalid/x.pmtiles')
                    self.end_headers()
                    return
                if sahip.kip == 'bozuk':
                    v = bytes(len(v))
                rng = self.headers.get('Range')
                if rng and sahip.kip == 'normal':
                    bas = int(rng.split('=')[1].split('-')[0])
                    self.send_response(206)
                    self.send_header('Content-Range', 'bytes %d-%d/%d' % (bas, len(v) - 1, len(v)))
                    self.send_header('Content-Length', str(len(v) - bas))
                    self.end_headers()
                    self.wfile.write(v[bas:])
                    return
                self.send_response(200)
                if sahip.kip == 'kesik':
                    self.end_headers()
                    self.wfile.write(v[:len(v) // 2])
                    return
                if sahip.kip == 'fazla':
                    self.end_headers()
                    self.wfile.write(v + b'EXTRA')
                    return
                self.send_header('Content-Length', str(len(v)))
                self.end_headers()
                if sahip.kip == 'yavas':
                    for i in range(0, len(v), 64):
                        self.wfile.write(v[i:i + 64])
                        self.wfile.flush()
                        time.sleep(0.05)
                    return
                self.wfile.write(v)

        self.srv = socketserver.ThreadingTCPServer(('127.0.0.1', 0), H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def kapat(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def sunucu(ortam, monkeypatch):
    s = _Sunucu(ortam['veri'])
    onek = 'http://127.0.0.1:%d/' % s.port
    monkeypatch.setattr(MP, '_RELEASE_DOWNLOAD_PREFIX', onek)
    monkeypatch.setattr(MP, '_URL_KAPISI', lambda url: url.startswith(onek))
    monkeypatch.setattr(MP, '_ACICI', lambda: urllib.request.build_opener(MP._YonlendirmeKapisi()))
    monkeypatch.setattr(MP, 'DOWNLOAD_CHUNK', 4096)
    yield s
    s.kapat()


@pytest.mark.parametrize('onay', [None, False, 'true', 1, {'x': 1}])
def test_riza_yoksa_hic_istek_yok(ortam, sunucu, onay):
    with pytest.raises(MP.PaketHatasi) as e:
        MP.indirme_baslat('sinop_test', consent=onay)
    assert e.value.kod == 'consent_required'
    assert sunucu.istekler == []


def test_indirme_kurulum_sha_ve_ilerleme(ortam, sunucu):
    d = MP.indirme_baslat('sinop_test', consent=True, bekle=True)
    assert d['state'] == 'installed' and d['error_code'] is None
    assert d['bytes_done'] == d['bytes_total'] == len(ortam['veri'])
    hedef = ortam['kurulum'] / ortam['dosya']
    assert hedef.read_bytes() == ortam['veri']
    assert not (ortam['kurulum'] / (ortam['dosya'] + '.part')).exists()
    assert json.loads((ortam['kurulum'] / (ortam['dosya'] + '.verified.json')).read_text())['sha256'] == ortam['sha']
    assert MP.paket_durumu(MP.paket_bul('sinop_test'))['status'] == 'installed'
    with pytest.raises(MP.PaketHatasi) as e:
        MP.indirme_baslat('sinop_test', consent=True)
    assert e.value.kod == 'already_installed'


def test_range_ile_devam(ortam, sunucu):
    part = ortam['kurulum'] / (ortam['dosya'] + '.part')
    part.write_bytes(ortam['veri'][:1000])
    d = MP.indirme_baslat('sinop_test', consent=True, bekle=True)
    assert d['state'] == 'installed'
    assert sunucu.istekler[-1][1] == 'bytes=1000-'
    assert (ortam['kurulum'] / ortam['dosya']).read_bytes() == ortam['veri']


def test_sunucu_araligi_yok_sayarsa_bastan(ortam, sunucu):
    sunucu.kip = 'aralik_yok'
    part = ortam['kurulum'] / (ortam['dosya'] + '.part')
    part.write_bytes(b'\xff' * 1000)                       # yanlış önek: baştan inmeli
    d = MP.indirme_baslat('sinop_test', consent=True, bekle=True)
    assert d['state'] == 'installed'
    assert (ortam['kurulum'] / ortam['dosya']).read_bytes() == ortam['veri']


def test_sha256_uyusmazligi_kurmaz(ortam, sunucu):
    sunucu.kip = 'bozuk'
    d = MP.indirme_baslat('sinop_test', consent=True, bekle=True)
    assert d['state'] == 'error' and d['error_code'] == 'sha256_mismatch'
    assert not (ortam['kurulum'] / ortam['dosya']).exists()
    assert not (ortam['kurulum'] / (ortam['dosya'] + '.part')).exists()


def test_kesik_indirme_yarim_dosya_kalir(ortam, sunucu):
    sunucu.kip = 'kesik'
    d = MP.indirme_baslat('sinop_test', consent=True, bekle=True)
    assert d['state'] == 'error' and d['error_code'] == 'incomplete_download'
    part = ortam['kurulum'] / (ortam['dosya'] + '.part')
    assert part.stat().st_size == len(ortam['veri']) // 2
    ozet = MP.paket_durumu(MP.paket_bul('sinop_test'))
    assert ozet['progress']['bytes_done'] == len(ortam['veri']) // 2   # gerçek bayt
    sunucu.kip = 'normal'
    MP._durumlar.clear()
    assert MP.indirme_baslat('sinop_test', consent=True, bekle=True)['state'] == 'installed'


def test_fazla_bayt_reddedilir(ortam, sunucu):
    sunucu.kip = 'fazla'
    d = MP.indirme_baslat('sinop_test', consent=True, bekle=True)
    assert d['state'] == 'error' and d['error_code'] == 'too_many_bytes'
    assert not (ortam['kurulum'] / ortam['dosya']).exists()


def test_iptal(ortam, sunucu, monkeypatch):
    sunucu.kip = 'yavas'
    monkeypatch.setattr(MP, 'DOWNLOAD_CHUNK', 64)
    MP.indirme_baslat('sinop_test', consent=True)
    time.sleep(0.3)
    assert MP.indirme_durumu('sinop_test')['state'] == 'downloading'
    d = MP.indirme_iptal('sinop_test')
    assert d['state'] == 'not_installed'
    assert not (ortam['kurulum'] / (ortam['dosya'] + '.part')).exists()
    assert not (ortam['kurulum'] / ortam['dosya']).exists()
    with pytest.raises(MP.PaketHatasi) as e:
        MP.indirme_iptal('sinop_test')
    assert e.value.kod == 'not_downloading'


def test_disk_dolu_istek_yok(ortam, sunucu, monkeypatch):
    monkeypatch.setattr(MP, '_DISK_BOS', lambda d: len(ortam['veri']))   # pay yetmez
    with pytest.raises(MP.PaketHatasi) as e:
        MP.indirme_baslat('sinop_test', consent=True)
    assert e.value.kod == 'disk_full'
    assert sunucu.istekler == []


def test_izin_listesi_disi_yonlendirme(ortam, sunucu):
    sunucu.kip = 'yonlendir'
    d = MP.indirme_baslat('sinop_test', consent=True, bekle=True)
    assert d['state'] == 'error' and d['error_code'] == 'redirect_not_allowed'
    assert not (ortam['kurulum'] / ortam['dosya']).exists()


def test_url_kapisi_ve_host_listesi():
    onek = MP._RELEASE_DOWNLOAD_PREFIX
    assert onek == 'https://github.com/berketez/HRMA/releases/download/'
    assert MP.url_kapisi(onek + 'harita-paketleri-v1/a.pmtiles')
    for kotu in ('http://github.com/berketez/HRMA/releases/download/x/a.pmtiles',
                 'https://evil.example/berketez/HRMA/releases/download/x/a.pmtiles',
                 'https://github.com/someone/else/releases/download/x/a.pmtiles'):
        assert not MP.url_kapisi(kotu), kotu
    assert MP.url_izinli_host('https://objects.githubusercontent.com/a')
    assert MP.url_izinli_host('https://release-assets.githubusercontent.com/a')
    for kotu in ('https://github.com.evil.example/a', 'https://github.com:8443/a',
                 'https://u:p@github.com/a', 'http://objects.githubusercontent.com/a',
                 'ftp://github.com/a'):
        assert not MP.url_izinli_host(kotu), kotu


def test_indirme_adresi_istemciden_alinmaz(ortam):
    m = MP.manifest_oku()
    url = MP.indirme_url(m, MP.vektor_bileseni(m['packs'][0]))
    assert url == ('https://github.com/berketez/HRMA/releases/download/'
                   'harita-paketleri-test/hrma-harita-sinop_test-v1.pmtiles')


def test_bilinmeyen_paket_ve_sil(ortam):
    with pytest.raises(MP.PaketHatasi) as e:
        MP.indirme_baslat('yok_boyle', consent=True)
    assert e.value.kod == 'unknown_pack'
    with pytest.raises(MP.PaketHatasi):
        MP.paket_bul('../x')
    _kur(ortam)
    assert MP.kurulu_mu(MP.paket_bul('sinop_test'))
    assert len(MP.kurulu_paketler()) == 1
    sonuc = MP.paket_sil('sinop_test')
    assert sonuc['deleted_bytes'] >= len(ortam['veri'])
    assert not (ortam['kurulum'] / ortam['dosya']).exists()
    assert MP.kurulu_paketler() == []


def test_degistirilmis_paket_okunmaz(ortam):
    hedef = _kur(ortam)
    assert MP.kurulu_mu(MP.paket_bul('sinop_test'))
    b = bytearray(hedef.read_bytes())
    b[-1] ^= 0xFF
    time.sleep(0.01)
    hedef.write_bytes(bytes(b))
    MP._dogrulama_cache.clear()
    assert not MP.kurulu_mu(MP.paket_bul('sinop_test'))
    assert MP.kurulu_paketler() == []


# ---------------------------------------------------------------------------
# 5) Çizim, zemin sağlayıcısı, etiketler
# ---------------------------------------------------------------------------

def test_cizim_belirlenimci_ve_gercek_piksel(ortam):
    from PIL import Image
    _kur(ortam)
    a = MP.karo_ciz(GZ, GX, GY)
    b = MP.karo_ciz(GZ, GX, GY)
    assert a is not None and a == b
    im = Image.open(io.BytesIO(a)).convert('RGBA')
    assert im.size == (512, 512)
    alfa = im.getchannel('A')
    assert alfa.getextrema()[1] > 100          # yol/su çizildi (z12: ince çizgi, LANCZOS)
    assert alfa.getextrema()[0] == 0           # boş alan saydam (zemin istemcide)


def test_kapsam_disi_none_ve_404(ortam):
    _kur(ortam)
    assert MP.karo_ciz(GZ, 0, 0) is None
    r = tc.resolve_tile('pack_detail', GZ, 0, 0)
    assert r['ok'] is False and r['code'] == 404 and r['error_code'] == 'not_covered'


def test_paket_yokken_404(ortam):
    r = tc.resolve_tile('pack_detail', GZ, GX, GY)
    assert r['code'] == 404 and r['error_code'] == 'not_covered'


def test_karo_katmani_onbellek(ortam):
    _kur(ortam)
    r1 = tc.resolve_tile('pack_detail', GZ, GX, GY)
    assert r1['ok'] and r1['cached'] is False and r1['mimetype'] == 'image/webp'
    r2 = tc.resolve_tile('pack_detail', GZ, GX, GY)
    assert r2['ok'] and r2['cached'] is True and r2['path'] == r1['path']
    assert tc._is_valid_webp(r1['path'])
    assert tc.resolve_tile('pack_detail', 16, 0, 0)['code'] == 400


def test_zemin_saglayici_baglanti_noktasi(ortam):
    from PIL import Image
    _kur(ortam)
    yalin = MP.karo_ciz(GZ, GX, GY)
    anahtar0 = MP.onbellek_anahtari(GZ, GX, GY)

    def bos(z, x, y):
        return None
    bos.surum = 'test-1'
    MP.zemin_saglayici_kaydet(bos)
    assert MP.karo_ciz(GZ, GX, GY) == yalin                 # None -> davranış aynen
    assert MP.onbellek_anahtari(GZ, GX, GY) != anahtar0     # sürüm anahtara girer

    def kirmizi(z, x, y):
        bio = io.BytesIO()
        Image.new('RGB', (512, 512), (200, 0, 0)).save(bio, 'PNG')
        return bio.getvalue()
    kirmizi.surum = 'test-2'
    MP.zemin_saglayici_kaydet(kirmizi)
    im = Image.open(io.BytesIO(MP.karo_ciz(GZ, GX, GY))).convert('RGBA')
    assert im.getchannel('A').getextrema() == (255, 255)    # opak zemin
    assert MP.karo_ciz(GZ, 0, 0) is None                    # paket kapsamıyorsa yine yok

    def bozuk(z, x, y):
        return b'not an image'
    bozuk.surum = 'test-3'
    MP.zemin_saglayici_kaydet(bozuk)
    with pytest.raises(MP.PaketHatasi) as e:
        MP.karo_ciz(GZ, GX, GY)
    assert e.value.kod == 'bad_ground_tile'
    with pytest.raises(MP.PaketHatasi):
        MP.zemin_saglayici_kaydet(lambda z, x, y: None)      # sürüm yok -> ret
    MP.zemin_saglayici_kaydet(None)


def test_etiket_ad_politikasi_K6(ortam):
    _kur(ortam)
    w, s, e, n = tc.tile_to_bbox(GZ, GX, GY)
    vz = ortam['vz']
    tr = MP.etiketler((w, s, e, n), vz, 'tr')['labels']
    en = MP.etiketler((w, s, e, n), vz, 'en')['labels']
    tr_ad = {d['name'] for d in tr}
    en_ad = {d['name'] for d in en}
    assert any(a.startswith('Village') for a in tr_ad)      # name:tr yok -> name:en
    assert not any(a.startswith('Köy') for a in tr_ad)      # yerel ad name:en'in önüne geçmez
    assert any(a.startswith('Mahalle') for a in tr_ad)      # name:tr / name:en yok -> name
    assert any(a.startswith('Village') for a in en_ad)      # name:en
    assert any(a.startswith('Mahalle') for a in en_ad)      # name:en yok -> name
    assert 'Rampa A (TR)' in tr_ad and 'Rampa A' in en_ad   # POI: name:tr / name
    assert 'Lokanta' not in tr_ad and 'Ülke' not in tr_ad   # etiketlenmeyen türler
    assert {d['kind'] for d in tr} <= MP.PLACE_KINDS | MP.LAUNCH_POI_KINDS
    assert tr == sorted(tr, key=lambda d: (d['rank'], d['name'], d['lon'], d['lat']))


@pytest.mark.parametrize('oz,tr,en', [
    ({'name': 'Σινώπη', 'name:en': 'Sinop'}, 'Sinop', 'Sinop'),
    ({'name': '酒泉', 'name:en': 'Jiuquan'}, 'Jiuquan', 'Jiuquan'),
    ({'name': 'Yerel', 'name:tr': 'Türkçe', 'name:en': 'English'}, 'Türkçe', 'English'),
    ({'name': 'Yerel', 'name:tr': 'Türkçe'}, 'Türkçe', 'Yerel'),    # EN ekranda name:tr yok
    ({'name': 'Yerel'}, 'Yerel', 'Yerel'),
    ({'name': 'Yerel', 'name:tr': '  ', 'name:en': ''}, 'Yerel', 'Yerel'),
    ({'kind': 'locality'}, None, None),
])
def test_ad_sirasi_K6_tablosu(oz, tr, en):
    """K6 (16 Kas): TR name:tr -> name:en -> name; EN name:en -> name."""
    assert MP.AD_SIRASI == {'tr': ('name:tr', 'name:en', 'name'), 'en': ('name:en', 'name')}
    assert MP.ad_sec(oz, 'tr') == tr
    assert MP.ad_sec(oz, 'en') == en


@pytest.mark.parametrize('args,kod', [
    (((10, 10, 5, 20), 10, 'tr'), 'bad_bbox'),
    (((0, 0, 1, 1), 16, 'tr'), 'bad_zoom'),
    (((0, 0, 1, 1), 10, 'de'), 'bad_lang'),
    (((-170, -80, 170, 80), 15, 'tr'), 'bbox_too_large'),
])
def test_etiket_girdi_kapisi(ortam, args, kod):
    with pytest.raises(MP.PaketHatasi) as e:
        MP.etiketler(*args)
    assert e.value.kod == kod


# ---------------------------------------------------------------------------
# 6) Uçlar
# ---------------------------------------------------------------------------

@pytest.fixture
def istemci(ortam):
    from hrma.app import app
    with app.test_client() as c:
        yield c


def test_uc_liste_sozlesmesi(istemci, ortam):
    j = istemci.get('/api/map-packs').get_json()
    p = j['packs'][0]
    for alan in ('id', 'kind', 'name_key', 'bbox', 'zoom_max', 'size_bytes', 'sha256',
                 'license', 'status', 'progress', 'error_code'):
        assert alan in p, alan
    assert p['status'] == 'not_installed' and p['progress'] is None
    assert p['sha256'] == ortam['sha'] and p['license'] == 'ODbL-1.0'


def test_uc_indirme_riza_ve_hatalar(istemci, ortam):
    r = istemci.post('/api/map-packs/sinop_test/download', json={})
    assert r.status_code == 400 and r.get_json()['error_code'] == 'consent_required'
    r = istemci.post('/api/map-packs/sinop_test/download', json={'consent': 'yes'})
    assert r.status_code == 400
    r = istemci.post('/api/map-packs/yok/download', json={'consent': True})
    assert r.status_code == 404 and r.get_json()['error_code'] == 'unknown_pack'
    r = istemci.post('/api/map-packs/sinop_test/cancel', json={})
    assert r.status_code == 409 and r.get_json()['error_code'] == 'not_downloading'
    r = istemci.get('/api/map-packs/sinop_test/progress')
    assert r.get_json() == {'state': 'not_installed', 'bytes_done': None,
                            'bytes_total': None, 'error_code': None}
    assert istemci.delete('/api/map-packs/yok').status_code == 404


def test_uc_etiket_ve_karo(istemci, ortam):
    _kur(ortam)
    w, s, e, n = tc.tile_to_bbox(GZ, GX, GY)
    r = istemci.get('/api/map-packs/labels?bbox=%f,%f,%f,%f&z=%d&lang=en' % (w, s, e, n, ortam['vz']))
    assert r.status_code == 200 and r.get_json()['labels']
    for kotu in ('bbox=1,2,3&z=10&lang=tr', 'bbox=a,b,c,d&z=10&lang=tr',
                 'bbox=0,0,1,1&z=1.5&lang=tr', 'bbox=0,0,1,1&z=10&lang=de',
                 'bbox=0,0,1,1&lang=tr', 'bbox=0,0,1,1&z=10'):
        r = istemci.get('/api/map-packs/labels?' + kotu)
        assert r.status_code == 400, kotu
        assert r.get_json()['error_code'] in ('invalid_input', 'bad_bbox'), kotu
    r = istemci.get('/api/tile/pack_detail/%d/%d/%d' % (GZ, GX, GY))
    assert r.status_code == 200 and r.mimetype == 'image/webp'
    r = istemci.get('/api/tile/pack_detail/%d/0/0' % GZ)
    assert r.status_code == 404


def test_katman_kaydi_ve_katalog():
    cfg = tc.LAYERS['pack_detail']
    assert cfg['source'] == tc.PACK_SOURCE == 'pack' and cfg['max_zoom'] == MP.PACK_MAX_ZOOM == 15
    kat = tc.list_layers()
    assert 'pack_detail' in kat['packs'] and 'pack_detail' not in kat['layers']
    # 3.0.7 birleşmesi (ana model): künye anahtarı (Parça K'nın i18n'i) EN + TR geldi,
    # katman arayüze AÇIK. Bağ fail-closed kalır: anahtar sözlükte iki dilde yoksa kırmızı.
    assert cfg['attribution_i18n_key'] == 'site.mapPackAttribution' and cfg['ui_offered'] is True
    i18n = (KOK / 'hrma' / 'static' / 'js' / 'i18n_launch_site.js').read_text(encoding='utf-8')
    assert i18n.count("'site.mapPackAttribution':") == 2  # EN + TR
    assert tc.matrix_geometry()['max_zoom'] == 15


# ---------------------------------------------------------------------------
# 7) Depodaki paket listesi ve lisans bildirimi
# ---------------------------------------------------------------------------

def test_depodaki_liste_hazir_sahalarla_tutarli():
    from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
    m = json.loads((KOK / 'hrma' / 'static' / 'map' / 'harita_paketleri.json').read_text(encoding='utf-8'))
    MP.manifest_dogrula(m)
    assert m['release_tag'] == 'harita-paketleri-v1'
    sahalar = {s['id']: s for s in LAUNCH_SITE_PRESETS}
    site = [p for p in m['packs'] if p['kind'] == 'site']
    assert {p['id'] for p in site} == set(sahalar)
    for p in site:
        s = sahalar[p['id']]
        beklenen = MP.daire_bbox(s['latitude'], s['longitude'], MP.SITE_RADIUS_KM)
        assert p['bbox'] == [round(v, 6) for v in beklenen], p['id']
        b = MP.vektor_bileseni(p)
        assert b['license'] == 'ODbL-1.0' and 'OpenStreetMap' in b['attribution']
        assert b['file'] == 'hrma-harita-%s-v1.pmtiles' % p['id']
        assert p['name_key'] == 'site.mapPackName.%s' % p['id']


def test_depodaki_liste_bolge_paketi():
    """Türkiye bölge vektör paketi (ana model 16 Kas): kutu tek kaynaktan, dosya <= 2 GiB."""
    m = json.loads((KOK / 'hrma' / 'static' / 'map' / 'harita_paketleri.json').read_text(encoding='utf-8'))
    bolge = {p['id']: p for p in m['packs'] if p['kind'] == 'region'}
    assert set(bolge) == set(MP.REGION_BBOXES) == {'turkiye'}
    p = bolge['turkiye']
    assert p['bbox'] == [round(v, 6) for v in MP.REGION_BBOXES['turkiye']]
    assert p['name_key'] == 'site.mapPackName.turkiye' and p['zoom_max'] == 15
    for b in p['components']:
        assert b['kind'] == 'vector' and b['size_bytes'] <= MP.MAX_PACK_BYTES
        assert b['license'] == 'ODbL-1.0'


def test_lisans_bildirimi_paket_lisansini_beyan_eder(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('lisans_paketle', KOK / 'packaging' / 'lisans_paketle.py')
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    bildirim = (KOK / 'packaging' / 'licenses' / 'THIRD_PARTY_NOTICES.txt').read_text(encoding='utf-8')
    assert lp.harita_paketi_bildirimlerini_denetle(KOK, bildirim) == ['ODbL-1.0']
    lp.veri_bildirimlerini_denetle(KOK, bildirim)
    # Ters: lisans satırı yoksa paketleme DURUR
    with pytest.raises(lp.LisansHatasi):
        lp.harita_paketi_bildirimlerini_denetle(KOK, bildirim.replace('Pack-Licence: ODbL-1.0', ''))
    with pytest.raises(lp.LisansHatasi):
        lp.harita_paketi_bildirimlerini_denetle(
            KOK, bildirim.replace('Data: hrma/static/map/harita_paketleri.json', ''))
