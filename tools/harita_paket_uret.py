#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HRMA harita paketi üretici (V307/FS-HARİTA-VERİ faz 2).

Protomaps Basemap gezegen yapısından (tek PMTiles dosyası, OpenStreetMap + Natural Earth,
ODbL) bir sahanın ya da bölgenin z0..z15 karolarını HTTP aralık (Range) istekleriyle çeker,
OSM olmayan 'landcover' katmanını (Daylight, ESA WorldCover türevi; yalnız z0-z7'de) çıkarır,
HRMA'nın kendi PMTiles yazıcısıyla (``hrma.analysis.map_packs.pmtiles_yaz``) tek dosyaya
yazar, geri okuyup karo karo doğrular, sha256 + boyut + lisans kaydını çıkarır ve
uygulamanın paket listesini (``hrma/static/map/harita_paketleri.json``) yazar.

Ürün çalışma zamanı bu aracı KULLANMAZ; araç yalnız paket üretir. Release'e yükleme ayrı
(elle / CI) bir adımdır. Bütün indirilen içerik VERİdir (karolar, dizinler); çalıştırılmaz.

Kullanım:
  python3 tools/harita_paket_uret.py saha --yapi 20261115 --cikti DIR --onbellek DIR [--id a,b] [--butce-mb 600]
  python3 tools/harita_paket_uret.py bolge-cek --yapi 20261115 --onbellek DIR --spool DIR --id turkiye [--sure-s 250] [--butce-mb 1900]
      (kaldığı yerden sürer; 'TAMAM' yazana kadar yeniden çağrılır)
  python3 tools/harita_paket_uret.py bolge-yaz --cikti DIR --onbellek DIR --spool DIR --id turkiye
  python3 tools/harita_paket_uret.py bolge-dogrula --cikti DIR --spool DIR --id turkiye
  python3 tools/harita_paket_uret.py liste --cikti DIR [--manifest hrma/static/map/harita_paketleri.json]

Kaynak kalıcılığı: Protomaps yapı sunucusu bir haftalık yapıları tutar
(docs.protomaps.com/basemaps/downloads); paketler üretildikten sonra HRMA release'inde
barındırılır, kaynak yapı adı + ETag + sürüm paket künyesine yazılır.
"""
import argparse
import bisect
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from hrma.analysis import map_packs as MP  # noqa: E402
from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS  # noqa: E402

YAPI_URL = 'https://build.protomaps.com/%s.pmtiles'
UA = 'HRMA map pack builder (offline map packs; range extraction)'
RELEASE_TAG = 'harita-paketleri-v1'
PAKET_SURUMU = 'v1'
LISANS = 'ODbL-1.0'
ATIF = ('© OpenStreetMap contributors (ODbL 1.0); Protomaps Basemap schema; '
        'Natural Earth (public domain)')
#: Çıkarılan katman: OSM olmayan Daylight landcover (ESA WorldCover 2020 türevi, z0-z7).
SILINEN_KATMANLAR = frozenset({'landcover'})
SILME_ZMAX = 7
BIRLESTIR_BOSLUK = 64 * 1024
AZAMI_ISTEK = 4 * 1024 * 1024
ES_ZAMANLI = 6


class Uzak:
    """Uzak PMTiles: aralık okuma, ETag sabitleme, bayt bütçesi."""

    def __init__(self, url, butce):
        self.url = url
        self.butce = butce
        self.okunan = 0
        self.istek = 0
        self.etag = None
        self._kilit = threading.Lock()

    def oku(self, of, ln):
        with self._kilit:
            if self.okunan + ln > self.butce:
                raise RuntimeError('bayt bütçesi aşılacaktı: %d + %d > %d'
                                   % (self.okunan, ln, self.butce))
            self.okunan += ln
            self.istek += 1
        req = urllib.request.Request(self.url, headers={
            'User-Agent': UA, 'Range': 'bytes=%d-%d' % (of, of + ln - 1)})
        if self.etag:
            req.add_header('If-Match', self.etag)
        for deneme in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    if r.status != 206:
                        raise RuntimeError('aralık isteği 206 dönmedi: %s' % r.status)
                    et = r.headers.get('ETag')
                    if self.etag is None:
                        self.etag = et
                    elif et != self.etag:
                        raise RuntimeError('kaynak değişti (ETag %s != %s)' % (et, self.etag))
                    b = r.read()
                if len(b) != ln:
                    raise RuntimeError('eksik okuma %d/%d' % (len(b), ln))
                return b
            except (OSError, RuntimeError) as e:
                if 'ETag' in str(e) or deneme == 3:
                    raise
                time.sleep(1 + 2 * deneme)


def _ac_dizin(b, h):
    return MP.dizin_coz(MP._ac(b, h['internal_compression'], MP.MAX_DIR_BYTES, 'directory_too_large'))


class UzakArsiv:
    def __init__(self, yapi, onbellek, butce):
        self.u = Uzak(YAPI_URL % yapi, butce)
        self.yapi = yapi
        self.onbellek = onbellek
        os.makedirs(onbellek, exist_ok=True)
        self.h = MP.baslik_coz(self.u.oku(0, MP.HEADER_LEN))
        self.kok = _ac_dizin(self.u.oku(self.h['root_dir_offset'], self.h['root_dir_length']), self.h)
        self.kok_tid = [g[0] for g in self.kok]
        self.meta = json.loads(MP._ac(self.u.oku(self.h['metadata_offset'], self.h['metadata_length']),
                                      self.h['internal_compression'], MP.MAX_DIR_BYTES, 'meta'))
        self._yaprak = {}

    def yaprak(self, g):
        key = (g[3], g[2])
        if key in self._yaprak:
            return self._yaprak[key]
        yol = os.path.join(self.onbellek, '%d_%d.bin' % (g[3], g[2]))
        if os.path.exists(yol) and os.path.getsize(yol) == g[2]:
            with open(yol, 'rb') as fh:
                b = fh.read()
        else:
            b = self.u.oku(self.h['leaf_dirs_offset'] + g[3], g[2])
            with open(yol + '.part', 'wb') as fh:
                fh.write(b)
            os.replace(yol + '.part', yol)
        d = _ac_dizin(b, self.h)
        if any(e[1] == 0 for e in d):
            raise RuntimeError('iç içe yaprak beklenmiyordu')
        tids = [e[0] for e in d]
        if len(self._yaprak) > 64:
            self._yaprak.pop(next(iter(self._yaprak)))
        self._yaprak[key] = (tids, d)
        return self._yaprak[key]

    def girdiler(self, tidler):
        """Sıralı karo kimlikleri -> [(tid, ofset, uzunluk)] (pakette olmayan atlanır)."""
        gruplar = {}
        for t in tidler:
            i = bisect.bisect_right(self.kok_tid, t) - 1
            if i >= 0:
                gruplar.setdefault(i, []).append(t)
        out = []
        with ThreadPoolExecutor(ES_ZAMANLI) as ex:
            list(ex.map(lambda i: self.yaprak(self.kok[i]) if self.kok[i][1] == 0 else None,
                        sorted(gruplar)))
        for i in sorted(gruplar):
            g = self.kok[i]
            if g[1] != 0:
                for t in gruplar[i]:
                    if g[0] <= t < g[0] + g[1]:
                        out.append((t, g[3], g[2]))
                continue
            tids, d = self.yaprak(g)
            for t in gruplar[i]:
                j = bisect.bisect_right(tids, t) - 1
                if j >= 0 and t < d[j][0] + d[j][1]:
                    out.append((t, d[j][3], d[j][2]))
        return out

    def karolari_cek(self, girdiler):
        benzersiz = sorted(set((o, n) for _, o, n in girdiler))
        gruplar, simdiki = [], []
        for o, n in benzersiz:
            if simdiki and (o - (simdiki[-1][0] + simdiki[-1][1]) > BIRLESTIR_BOSLUK
                            or o + n - simdiki[0][0] > AZAMI_ISTEK):
                gruplar.append(simdiki)
                simdiki = []
            simdiki.append((o, n))
        if simdiki:
            gruplar.append(simdiki)
        icerik = {}

        def getir(gr):
            bas = gr[0][0]
            son = max(o + n for o, n in gr)
            blok = self.u.oku(self.h['tile_data_offset'] + bas, son - bas)
            return [((o, n), blok[o - bas:o - bas + n]) for o, n in gr]
        with ThreadPoolExecutor(ES_ZAMANLI) as ex:
            for parca in ex.map(getir, gruplar):
                icerik.update(parca)
        return {t: icerik[(o, n)] for t, o, n in girdiler}, len(gruplar)


def bolge_tidleri(bbox, zmax):
    out = []
    for z in range(zmax + 1):
        x0, y0 = MP.merc_karo(bbox[0], bbox[3], z)
        x1, y1 = MP.merc_karo(bbox[2], bbox[1], z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                out.append(MP.zxy_tileid(z, x, y))
    return sorted(out)


def paket_uret(arsiv, pid, kind, bbox, cikti_dizin, ek_kunye):
    t0 = time.time()
    okunan0 = arsiv.u.okunan
    tidler = bolge_tidleri(bbox, MP.PACK_MAX_ZOOM)
    gir = arsiv.girdiler(tidler)
    karolar, nistek = arsiv.karolari_cek(gir)
    silinen = 0
    for t in list(karolar):
        if MP.tileid_zoom(t) <= SILME_ZMAX:
            yeni = MP.mvt_katman_sil(karolar[t], SILINEN_KATMANLAR)
            if yeni is not karolar[t]:
                silinen += 1
                karolar[t] = yeni
    kaynak_meta = arsiv.meta
    katmanlar = [L for L in kaynak_meta.get('vector_layers', [])
                 if L.get('id') not in SILINEN_KATMANLAR]
    meta = {
        'name': 'HRMA map pack %s' % pid,
        'description': 'OpenStreetMap vector tiles for the HRMA launch site globe (offline)',
        'attribution': ATIF,
        'license': LISANS,
        'type': 'baselayer',
        'vector_layers': katmanlar,
        'hrma': dict(ek_kunye, pack_id=pid, kind=kind, bbox=list(bbox), pack_version=PAKET_SURUMU,
                     removed_layers=sorted(SILINEN_KATMANLAR), removed_layers_max_zoom=SILME_ZMAX),
        'source': {'build': '%s.pmtiles' % arsiv.yapi, 'url': YAPI_URL % arsiv.yapi,
                   'etag': arsiv.u.etag, 'version': kaynak_meta.get('version'),
                   'osm_replication_time': kaynak_meta.get('planetiler:osm:osmosisreplicationtime'),
                   'description': kaynak_meta.get('description'),
                   'attribution': kaynak_meta.get('attribution')},
    }
    dosya = 'hrma-harita-%s-%s.pmtiles' % (pid, PAKET_SURUMU)
    yol = os.path.join(cikti_dizin, dosya)
    ozet = MP.pmtiles_yaz(yol, karolar, meta, tuple(bbox))
    # Geri oku: her karo bayt bayt aynı mı
    r = MP.PMTilesOkuyucu(yol)
    hatali = 0
    try:
        for t, b in karolar.items():
            konum = r.bul(t)
            if konum is None or r._oku(r.h['tile_data_offset'] + konum[0], konum[1]) != b:
                hatali += 1
    finally:
        r.kapat()
    if hatali:
        raise RuntimeError('%s: geri okumada %d karo hatalı' % (pid, hatali))
    sha = MP._sha256_dosya(yol)
    kayit = {'id': pid, 'kind': kind, 'bbox': [round(v, 6) for v in bbox], 'file': dosya,
             'size_bytes': os.path.getsize(yol), 'sha256': sha, 'writer': ozet,
             'tiles': len(karolar), 'landcover_removed_tiles': silinen,
             'source_bytes_read': arsiv.u.okunan - okunan0, 'range_requests': nistek,
             'seconds': round(time.time() - t0, 1), 'hrma': meta['hrma'], 'source': meta['source']}
    with open(yol + '.json', 'w', encoding='utf-8') as fh:
        json.dump(kayit, fh, indent=1, ensure_ascii=False)
    return kayit


def manifest_yaz(cikti_dizin, manifest_yolu):
    kayitlar = []
    for f in sorted(os.listdir(cikti_dizin)):
        if f.endswith('.pmtiles.json'):
            with open(os.path.join(cikti_dizin, f), encoding='utf-8') as fh:
                kayitlar.append(json.load(fh))
    sira = {p['id']: i for i, p in enumerate(LAUNCH_SITE_PRESETS)}
    kayitlar.sort(key=lambda k: (0 if k['kind'] == 'site' else 1, sira.get(k['id'], 999), k['id']))
    paketler = []
    for k in kayitlar:
        paketler.append({
            'id': k['id'], 'kind': k['kind'], 'name_key': 'site.mapPackName.%s' % k['id'],
            'bbox': k['bbox'], 'zoom_max': MP.PACK_MAX_ZOOM,
            'radius_km': k['hrma'].get('radius_km'),
            'components': [{'kind': 'vector', 'file': k['file'], 'size_bytes': k['size_bytes'],
                            'sha256': k['sha256'], 'license': LISANS, 'attribution': ATIF}],
            'source': {'build': k['source']['build'], 'version': k['source']['version'],
                       'osm_replication_time': k['source']['osm_replication_time'],
                       'etag': k['source']['etag']},
        })
    m = {'schema': MP.MANIFEST_SCHEMA, 'release_tag': RELEASE_TAG,
         'note': ('Files are published as assets of the HRMA GitHub release named by '
                  'release_tag; the application downloads only the files listed here and '
                  'verifies size and sha256 before use.'),
         'packs': paketler}
    MP.manifest_dogrula(m)
    with open(manifest_yolu + '.part', 'w', encoding='utf-8') as fh:
        json.dump(m, fh, indent=1, ensure_ascii=False)
        fh.write('\n')
    os.replace(manifest_yolu + '.part', manifest_yolu)
    return m


# ---------------------------------------------------------------------------
# Bölge paketi (GB düzeyi): kaldığı yerden devam eden çekim + akış yazımı.
# Çekim: karolar sıralı aralık gruplarıyla bir biriktirme dosyasına (spool) yazılır; her
# tamamlanan grup tamam.tsv'ye işlenir (fsync). Komut süre sınırında durur, yeniden
# çağrılınca eksik gruplardan sürer. Bayt bütçesi koşular arasında toplanır.
# Kaynak sabitlemesi: ilk koşunun ETag'i kaynak.json'a yazılır; sonraki koşular If-Match ile
# aynı nesneyi ister ve ETag farklıysa DURUR.
# ---------------------------------------------------------------------------

import array  # noqa: E402


def _girdiler_yukle_ya_da_kur(arsiv, bbox, spool):
    yol = os.path.join(spool, 'girdiler.bin')
    if os.path.exists(yol):
        a = array.array('q')
        with open(yol, 'rb') as fh:
            a.frombytes(fh.read())
        return [(a[i], a[i + 1], a[i + 2]) for i in range(0, len(a), 3)]
    gir = arsiv.girdiler(bolge_tidleri(bbox, MP.PACK_MAX_ZOOM))
    a = array.array('q')
    for t, o, n in gir:
        a.extend((t, o, n))
    with open(yol + '.part', 'wb') as fh:
        fh.write(a.tobytes())
    os.replace(yol + '.part', yol)
    return gir


def _gruplar(gir):
    benzersiz = sorted(set((o, n) for _, o, n in gir))
    gruplar, simdiki = [], []
    for o, n in benzersiz:
        if simdiki and (o - (simdiki[-1][0] + simdiki[-1][1]) > BIRLESTIR_BOSLUK
                        or o + n - simdiki[0][0] > AZAMI_ISTEK):
            gruplar.append(simdiki)
            simdiki = []
        simdiki.append((o, n))
    if simdiki:
        gruplar.append(simdiki)
    return gruplar


def _tamam_oku(spool):
    """{grup_no: (spool_ofset, bas, son)} ve tutarlı veri sonu."""
    yol = os.path.join(spool, 'tamam.tsv')
    tamam = {}
    if os.path.exists(yol):
        with open(yol, encoding='utf-8') as fh:
            for ln in fh:
                p = ln.rstrip('\n').split('\t')
                if len(p) == 4:
                    tamam[int(p[0])] = (int(p[1]), int(p[2]), int(p[3]))
    son = max((v[0] + v[2] - v[1] for v in tamam.values()), default=0)
    return tamam, son


def bolge_cek(a):
    import concurrent.futures as cf
    bbox = MP.REGION_BBOXES[a.id]
    spool = a.spool
    os.makedirs(spool, exist_ok=True)
    kaynak_yol = os.path.join(spool, 'kaynak.json')
    butce_yol = os.path.join(spool, 'butce.json')
    onceki_okunan = 0
    if os.path.exists(butce_yol):
        with open(butce_yol) as fh:
            onceki_okunan = json.load(fh)['okunan']
    butce = int(a.butce_mb * 1e6) - onceki_okunan
    if butce <= 0:
        raise SystemExit('bayt bütçesi tükendi (%d B okundu)' % onceki_okunan)
    arsiv = UzakArsiv(a.yapi, a.onbellek, butce)
    if os.path.exists(kaynak_yol):
        with open(kaynak_yol) as fh:
            k = json.load(fh)
        if k['etag'] != arsiv.u.etag or k['yapi'] != a.yapi:
            raise SystemExit('kaynak değişti: %r != %r' % (k, (a.yapi, arsiv.u.etag)))
    else:
        with open(kaynak_yol, 'w') as fh:
            json.dump({'yapi': a.yapi, 'etag': arsiv.u.etag, 'bbox': bbox, 'id': a.id}, fh)
    t0 = time.time()
    gir = _girdiler_yukle_ya_da_kur(arsiv, bbox, spool)
    gruplar = _gruplar(gir)
    tamam, veri_sonu = _tamam_oku(spool)
    veri_yol = os.path.join(spool, 'veri.bin')
    with open(veri_yol, 'ab') as fh:
        pass
    if os.path.getsize(veri_yol) != veri_sonu:
        with open(veri_yol, 'r+b') as fh:          # yarım yazılmış grup: tutarlı sona kes
            fh.truncate(veri_sonu)
    kalan = [i for i in range(len(gruplar)) if i not in tamam]
    print('girdi %d, grup %d, tamam %d, kalan %d (hazırlık %.0f s)'
          % (len(gir), len(gruplar), len(tamam), len(kalan), time.time() - t0), flush=True)

    def getir(i):
        gr = gruplar[i]
        bas = gr[0][0]
        son = max(o + n for o, n in gr)
        return i, bas, son, arsiv.u.oku(arsiv.h['tile_data_offset'] + bas, son - bas)
    yazilan = 0
    with open(veri_yol, 'ab') as vf, open(os.path.join(spool, 'tamam.tsv'), 'a',
                                          encoding='utf-8') as tf, \
            cf.ThreadPoolExecutor(ES_ZAMANLI) as ex:
        kuyruk = iter(kalan)
        bekleyen = set()
        for _ in range(ES_ZAMANLI * 2):
            i = next(kuyruk, None)
            if i is not None:
                bekleyen.add(ex.submit(getir, i))
        while bekleyen:
            bitti, bekleyen = cf.wait(bekleyen, return_when=cf.FIRST_COMPLETED)
            for f in bitti:
                i, bas, son, blok = f.result()
                vf.write(blok)
                vf.flush()
                os.fsync(vf.fileno())
                tf.write('%d\t%d\t%d\t%d\n' % (i, veri_sonu, bas, son))
                tf.flush()
                veri_sonu += len(blok)
                yazilan += 1
            if time.time() - t0 < a.sure_s:
                for _ in range(len(bitti)):
                    i = next(kuyruk, None)
                    if i is not None:
                        bekleyen.add(ex.submit(getir, i))
    with open(butce_yol, 'w') as fh:
        json.dump({'okunan': onceki_okunan + arsiv.u.okunan}, fh)
    eksik = len(kalan) - yazilan
    print('bu koşu %d grup, %.1f MB okundu; toplam okunan %.1f MB; eksik grup %d; %s'
          % (yazilan, arsiv.u.okunan / 1e6, (onceki_okunan + arsiv.u.okunan) / 1e6, eksik,
             'TAMAM' if eksik == 0 else 'DEVAM GEREKİR'), flush=True)


def bolge_yaz(a):
    bbox = MP.REGION_BBOXES[a.id]
    spool = a.spool
    with open(os.path.join(spool, 'kaynak.json')) as fh:
        kaynak = json.load(fh)
    arsiv = UzakArsiv(kaynak['yapi'], a.onbellek, 1024 * 1024)   # yalnız başlık + metadata
    if arsiv.u.etag != kaynak['etag']:
        raise SystemExit('kaynak değişti')
    t0 = time.time()
    gir = _girdiler_yukle_ya_da_kur(arsiv, bbox, spool)
    gruplar = _gruplar(gir)
    tamam, veri_sonu = _tamam_oku(spool)
    if len(tamam) != len(gruplar):
        raise SystemExit('çekim bitmemiş: %d/%d grup' % (len(tamam), len(gruplar)))
    konum = {}
    for i, gr in enumerate(gruplar):
        s_of, bas, _son = tamam[i]
        for o, n in gr:
            konum[(o, n)] = s_of + (o - bas)
    gir.sort()
    vf = open(os.path.join(spool, 'veri.bin'), 'rb')
    silinen = [0]

    def akis():
        for t, o, n in gir:
            vf.seek(konum[(o, n)])
            b = vf.read(n)
            if len(b) != n:
                raise RuntimeError('biriktirme dosyası kısa')
            if MP.tileid_zoom(t) <= SILME_ZMAX:
                yeni = MP.mvt_katman_sil(b, SILINEN_KATMANLAR)
                if yeni is not b:
                    silinen[0] += 1
                b = yeni
            yield t, b
    katmanlar = [L for L in arsiv.meta.get('vector_layers', []) if L.get('id') not in SILINEN_KATMANLAR]
    meta = {
        'name': 'HRMA map pack %s' % a.id,
        'description': 'OpenStreetMap vector tiles for the HRMA launch site globe (offline)',
        'attribution': ATIF, 'license': LISANS, 'type': 'baselayer', 'vector_layers': katmanlar,
        'hrma': {'pack_id': a.id, 'kind': 'region', 'bbox': list(bbox), 'pack_version': PAKET_SURUMU,
                 'radius_km': None, 'removed_layers': sorted(SILINEN_KATMANLAR),
                 'removed_layers_max_zoom': SILME_ZMAX},
        'source': {'build': '%s.pmtiles' % kaynak['yapi'], 'url': YAPI_URL % kaynak['yapi'],
                   'etag': kaynak['etag'], 'version': arsiv.meta.get('version'),
                   'osm_replication_time': arsiv.meta.get('planetiler:osm:osmosisreplicationtime'),
                   'description': arsiv.meta.get('description'),
                   'attribution': arsiv.meta.get('attribution')},
    }
    dosya = 'hrma-harita-%s-%s.pmtiles' % (a.id, PAKET_SURUMU)
    yol = os.path.join(a.cikti, dosya)
    try:
        ozet = MP.pmtiles_yaz_akis(yol, akis(), meta, bbox)
    finally:
        vf.close()
    if ozet['bytes'] > MP.MAX_PACK_BYTES:
        raise SystemExit('paket %d B > %d B: iki bileşene bölünmeli' % (ozet['bytes'], MP.MAX_PACK_BYTES))
    sha = MP._sha256_dosya(yol)
    kayit = {'id': a.id, 'kind': 'region', 'bbox': [round(v, 6) for v in bbox], 'file': dosya,
             'size_bytes': os.path.getsize(yol), 'sha256': sha, 'writer': ozet, 'tiles': len(gir),
             'landcover_removed_tiles': silinen[0], 'groups': len(gruplar),
             'seconds_write': round(time.time() - t0, 1), 'hrma': meta['hrma'], 'source': meta['source'],
             'verified': False}
    with open(yol + '.json', 'w', encoding='utf-8') as fh:
        json.dump(kayit, fh, indent=1, ensure_ascii=False)
    print('%s %d B sha256 %s karo %d en büyük karo %d B (%.0f s)'
          % (a.id, kayit['size_bytes'], sha, len(gir), ozet['max_tile_bytes'], time.time() - t0),
          flush=True)


def bolge_dogrula(a):
    """Yazılan paketi karo karo biriktirme dosyasıyla karşılaştırır (z <= 7 landcover hariç)."""
    bbox = MP.REGION_BBOXES[a.id]
    spool = a.spool
    t0 = time.time()
    a_ = array.array('q')
    with open(os.path.join(spool, 'girdiler.bin'), 'rb') as fh:
        a_.frombytes(fh.read())
    gir = sorted((a_[i], a_[i + 1], a_[i + 2]) for i in range(0, len(a_), 3))
    gruplar = _gruplar(gir)
    tamam, _ = _tamam_oku(spool)
    konum = {}
    for i, gr in enumerate(gruplar):
        s_of, bas, _son = tamam[i]
        for o, n in gr:
            konum[(o, n)] = s_of + (o - bas)
    dosya = 'hrma-harita-%s-%s.pmtiles' % (a.id, PAKET_SURUMU)
    yol = os.path.join(a.cikti, dosya)
    r = MP.PMTilesOkuyucu(yol)
    hatali = 0
    try:
        with open(os.path.join(spool, 'veri.bin'), 'rb') as vf:
            for t, o, n in gir:
                vf.seek(konum[(o, n)])
                b = vf.read(n)
                if MP.tileid_zoom(t) <= SILME_ZMAX:
                    b = MP.mvt_katman_sil(b, SILINEN_KATMANLAR)
                k = r.bul(t)
                if k is None or r._oku(r.h['tile_data_offset'] + k[0], k[1]) != b:
                    hatali += 1
    finally:
        r.kapat()
    with open(yol + '.json', encoding='utf-8') as fh:
        kayit = json.load(fh)
    kayit['verified'] = hatali == 0
    kayit['verify_errors'] = hatali
    kayit['seconds_verify'] = round(time.time() - t0, 1)
    with open(yol + '.json', 'w', encoding='utf-8') as fh:
        json.dump(kayit, fh, indent=1, ensure_ascii=False)
    print('doğrulama: %d karo, %d hatalı (%.0f s)' % (len(gir), hatali, time.time() - t0), flush=True)
    if hatali:
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('komut', choices=['saha', 'bolge-cek', 'bolge-yaz', 'bolge-dogrula', 'liste'])
    ap.add_argument('--spool', help='bölge çekiminin biriktirme dizini (kaldığı yerden sürer)')
    ap.add_argument('--sure-s', type=float, default=250.0, help='bölge çekiminde koşu süre sınırı')
    ap.add_argument('--yapi', default='20261115')
    ap.add_argument('--cikti', required=True)
    ap.add_argument('--onbellek')
    ap.add_argument('--id', default='')
    ap.add_argument('--butce-mb', type=float, default=600.0)
    ap.add_argument('--manifest', default=os.path.join(KOK, 'hrma', 'static', 'map',
                                                       'harita_paketleri.json'))
    a = ap.parse_args()
    os.makedirs(a.cikti, exist_ok=True)
    if a.komut == 'liste':
        m = manifest_yaz(a.cikti, a.manifest)
        print('paket', len(m['packs']), '->', a.manifest)
        return
    if a.komut == 'bolge-cek':
        bolge_cek(a)
        return
    if a.komut == 'bolge-yaz':
        bolge_yaz(a)
        return
    if a.komut == 'bolge-dogrula':
        bolge_dogrula(a)
        return
    arsiv = UzakArsiv(a.yapi, a.onbellek, int(a.butce_mb * 1e6))
    if a.komut == 'saha':
        secim = set(filter(None, a.id.split(',')))
        for s in LAUNCH_SITE_PRESETS:
            if secim and s['id'] not in secim:
                continue
            bbox = MP.daire_bbox(s['latitude'], s['longitude'], MP.SITE_RADIUS_KM)
            k = paket_uret(arsiv, s['id'], 'site', bbox, a.cikti,
                           {'center': [s['latitude'], s['longitude']],
                            'radius_km': MP.SITE_RADIUS_KM, 'preset': s['id']})
            print('%-18s %10d B  sha256 %s  karo %d  okunan %.1f MB  %.0f s' % (
                k['id'], k['size_bytes'], k['sha256'], k['tiles'],
                k['source_bytes_read'] / 1e6, k['seconds']), flush=True)
    print('toplam okunan %.1f MB, istek %d' % (arsiv.u.okunan / 1e6, arsiv.u.istek))


if __name__ == '__main__':
    main()
