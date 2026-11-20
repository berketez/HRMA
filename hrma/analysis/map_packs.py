# -*- coding: utf-8 -*-
"""
Fırlatma Sahası HARİTA PAKETLERİ — çevrimdışı OSM vektör paketi (V307/FS-HARİTA-VERİ faz 2).

Sorun (ölçüldü, faz 1 RAPOR Bölüm 1): kürede 20 km ve 2 km kamerada zemin dokusu
120x-1.201x büyütülmüş (rıza kapalı) ya da 19x büyütülmüş (rıza açık) leke; yer adı 0-1;
yol verisi hiç yok. Bu modül, kullanıcının ONAYIYLA HRMA'nın kendi GitHub release'inden
indirilen saha paketlerini (OpenStreetMap vektör karoları, Protomaps Basemap şeması,
PMTiles v3 tek dosya) okur, kürenin karo hattına RASTER olarak çizer ve yer adlarını
etiket modülüne verir. Paket kurucuya (DMG/EXE) GİRMEZ (ana model kararı K7).

Bileşenler (hepsi saf Python + Pillow; yeni bağımlılık YOK, karar K8):
  * PMTiles v3 okuyucu/yazıcı (spec: github.com/protomaps/PMTiles spec/v3) — sınırlı.
  * MVT 2.1 çözücü (github.com/mapbox/vector-tile-spec 2.1) — boyut/eleman sınırlı;
    bozuk/şişirilmiş girdide ADIYLA ret (:class:`PaketHatasi` ``kod``).
  * Paket listesi (``hrma/static/map/harita_paketleri.json``) okuma/doğrulama.
  * İndirme yöneticisi: yalnız izin listesindeki HRMA release önekinden, HTTPS, rıza
    olmadan TEK istek yok, Range ile devam, iptal, gerçek bayt ilerlemesi, sha256,
    disk alanı denetimi, boyut tavanı, atomik kurulum; arşiv AÇILMAZ (tek dosya).
  * Raster çizim (yol sınıfları, bina, su, kıyı, arazi kullanımı) ve etiket sorgusu
    (ad politikası K6: TR -> name:tr yoksa name; EN -> name:en yoksa name).

DÜRÜSTLÜK: paket kapsamadığı karoda çizim YOK (None -> uç 404; sahte doku yok). Paket
sha256'sı doğrulanmadan okunmaz. Görüntü bileşeni (uydu) BU FAZDA YOK (karar K2); liste
biçimi ``components`` ile ileride görüntü bileşeni alabilir, bu modül yalnız
``type == 'vector'`` bileşeni okur ve başka türü ADIYLA reddeder.
"""

import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
import zlib
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1) Sabitler (tek tanım; araç ve testler buradan okur)
# ---------------------------------------------------------------------------

#: Paket listesi (uygulamayla gelir; istemciden URL/adres ALINMAZ).
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'static', 'map', 'harita_paketleri.json')
MANIFEST_SCHEMA = 'hrma.map_packs/1'
#: Saha paketi yarıçapı [km] — HRMA seçimi (faz 1 RAPOR K1: 100 km, 20 km kamerada
#: ekran ~23 km genişlik; sahadan ~75 km uzaklaşınca kenar görünür).
SITE_RADIUS_KM = 100.0
#: Bölge paketlerinin kutuları (batı, güney, doğu, kuzey; derece) — HRMA seçimi; faz 1
#: bölge ölçümüyle aynı kutu (RAPOR Bölüm 2.1: Türkiye kutusu z0-z15 1,63 GB).
REGION_BBOXES = {'turkiye': (25.6, 35.8, 44.9, 42.2)}
#: Paketin en yüksek vektör düzeyi (Protomaps Basemap tavanı z15; spec/yapı metadata).
PACK_MAX_ZOOM = 15
#: GitHub release dosya sınırı: "Each file included in a release must be under 2 GiB"
#: (docs.github.com, About releases; 2026-11-16 denetlendi).
MAX_PACK_BYTES = 2 * 1024 ** 3 - 1
#: Disk alanı payı [B] — HRMA seçimi: kalan indirmeye ek olarak boş kalması istenen alan.
DISK_PAY_BYTES = 64 * 1024 * 1024
#: İndirme okuma parçası [B] ve ağ zaman aşımı [s] — HRMA seçimi.
DOWNLOAD_CHUNK = 256 * 1024
DOWNLOAD_TIMEOUT_S = 30.0
_HTTP_UA = 'HRMA map pack downloader (offline-first launch site tool)'

#: İzin verilen indirme öneki: güncelleme denetleyicisinin kendi önekiyle AYNI tanım
#: (tek kaynak, ``update_checker.DOWNLOAD_PREFIX``) + veri sürümü etiketi.
from hrma.utils.update_checker import DOWNLOAD_PREFIX as _RELEASE_DOWNLOAD_PREFIX  # noqa: E402
#: GitHub release indirmesi github.com'dan nesne deposuna 302 ile yönlenir; yalnız bu
#: HTTPS hostlarına izin var (başka host -> 'redirect_not_allowed').
ALLOWED_REDIRECT_HOSTS = frozenset({'github.com', 'objects.githubusercontent.com',
                                    'release-assets.githubusercontent.com'})

PACK_ID_RE = re.compile(r'^[a-z0-9_]{1,40}$')
PACK_FILE_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{0,120}\.(pmtiles|sqlite)$')
#: Bileşen türü -> dosya uzantısı. 'imagery' biçimi tanımlı, okuyucusu bu modülde YOK.
COMPONENT_EXT = {'vector': '.pmtiles', 'imagery': '.sqlite'}
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
RELEASE_TAG_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{0,60}$')

# --- PMTiles / MVT sınırları (saldırgan girdi kapısı; HRMA seçimi, ölçülü pay) ------
#: Örnek paketteki en büyük karo 0,3 MB (gzip'li); sınırlar 10x+ pay bırakır.
MAX_TILE_BYTES = 4 * 1024 * 1024          # sıkıştırılmış tek karo
MAX_MVT_BYTES = 16 * 1024 * 1024          # açılmış tek karo
MAX_DIR_BYTES = 64 * 1024 * 1024          # açılmış tek dizin
MAX_DIR_ENTRIES = 4_000_000
MAX_DIR_DEPTH = 4                         # kök + iç içe yaprak (spec en çok 3 öngörür)
MAX_LAYERS = 64
MAX_FEATURES = 400_000                    # karo başına toplam öğe
MAX_GEOM_INTS = 8_000_000                 # karo başına toplam geometri tamsayısı
MAX_KEYS_VALUES = 200_000                 # katman başına anahtar + değer
#: Etiket sorgusu sınırları (HRMA seçimi): kutu başına en çok karo ve dönen etiket.
MAX_LABEL_TILES = 64
MAX_LABELS = 500
#: Ad politikası (karar K6) ve etiketlenen türler.
LABEL_LANGS = ('tr', 'en')
#: Ad seçim sırası (karar K6, ana model 16 Kas düzeltmesi): ilk dolu alan kullanılır.
AD_SIRASI = {'tr': ('name:tr', 'name:en', 'name'), 'en': ('name:en', 'name')}
PLACE_KINDS = frozenset({'locality', 'neighbourhood', 'macrohood'})
LAUNCH_POI_KINDS = frozenset({'launch_complex', 'launchpad', 'spaceport'})

#: Web Mercator 256 px karo ile HRMA küre karosu (GIBS EPSG:4326, 512 px, açıklık
#: 288/2^z) arasındaki piksel açıklığı oranı: (360/256) / (288/512) = 2,5 (ekvatorda).
MERC_TILE_PX = 256
#: Küre karosu kenarı [px]: TEK tanım görüntü kabının sözleşmesinde
#: (``map_pack_imagery.TILE_PX``; 3.0.7 birleşmesinde iki ad tek tanıma indirildi).
from hrma.analysis import map_pack_imagery as _mpi  # noqa: E402
KURE_TILE_PX = _mpi.TILE_PX
KURE_SPAN_NUMERATOR = 288.0
_MERC_KURE_ORANI = (360.0 / MERC_TILE_PX) / (KURE_SPAN_NUMERATOR / KURE_TILE_PX)
MERC_MAX_LAT = 85.0511287798

#: Çizim stili sürümü — önbellek anahtarına girer (stil değişince eski karo sunulmaz).
STYLE_VERSION = 'v1'


class PaketHatasi(ValueError):
    """Paket/karo/girdi ADIYLA reddedildi. ``kod`` makine-okur (istemci i18n'den çevirir)."""

    def __init__(self, kod: str, ayrinti: str = ''):
        super().__init__('%s: %s' % (kod, ayrinti) if ayrinti else kod)
        self.kod = kod


# ---------------------------------------------------------------------------
# 2) Varint / gzip (sınırlı)
# ---------------------------------------------------------------------------

def _varint(b: bytes, i: int) -> Tuple[int, int]:
    sonuc = kay = 0
    n = len(b)
    while True:
        if i >= n:
            raise PaketHatasi('varint_truncated')
        c = b[i]
        i += 1
        sonuc |= (c & 0x7F) << kay
        if not c & 0x80:
            return sonuc, i
        kay += 7
        if kay > 63:
            raise PaketHatasi('varint_too_long')


def _ac(veri: bytes, sikistirma: int, tavan: int, kod: str) -> bytes:
    """1 = sıkıştırmasız, 2 = gzip; açılmış boyut ``tavan``ı aşarsa ``kod`` ile ret."""
    if sikistirma == 1:
        if len(veri) > tavan:
            raise PaketHatasi(kod, 'uncompressed data exceeds limit')
        return veri
    if sikistirma != 2:
        raise PaketHatasi('unsupported_compression', str(sikistirma))
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        cikti = d.decompress(veri, tavan + 1)
    except zlib.error as e:
        raise PaketHatasi('corrupt_gzip', str(e)) from None
    if len(cikti) > tavan or d.unconsumed_tail:
        raise PaketHatasi(kod, 'decompressed data exceeds limit')
    if not d.eof:
        raise PaketHatasi('corrupt_gzip', 'truncated stream')
    return cikti


def _gzip(veri: bytes) -> bytes:
    """Belirlenimci gzip (mtime=0): aynı girdi aynı bayt."""
    return gzip.compress(veri, 9, mtime=0)


# ---------------------------------------------------------------------------
# 3) PMTiles v3: karo kimliği (Hilbert), dizin, okuyucu, yazıcı
# ---------------------------------------------------------------------------

HEADER_LEN = 127
ROOT_DIR_LIMIT = 16384     # spec: başlık + kök dizin ilk 16 KiB içinde


def zoom_tabani(z: int) -> int:
    """z düzeyinin ilk karo kimliği: (4^z - 1) / 3."""
    return (4 ** z - 1) // 3


def zxy_tileid(z: int, x: int, y: int) -> int:
    """(z, x, y) -> PMTiles karo kimliği (Hilbert eğrisi; spec ``zxy_to_tileid``)."""
    if not (0 <= z <= 31):
        raise PaketHatasi('bad_zoom', str(z))
    n = 1 << z
    if not (0 <= x < n and 0 <= y < n):
        raise PaketHatasi('bad_tile', '%d/%d/%d' % (z, x, y))
    d, s = 0, n >> 1
    while s > 0:
        rx = 1 if (x & s) else 0
        ry = 1 if (y & s) else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s >>= 1
    return zoom_tabani(z) + d


def tileid_zoom(tid: int) -> int:
    z = 0
    while zoom_tabani(z + 1) <= tid:
        z += 1
    return z


def dizin_coz(veri: bytes) -> List[List[int]]:
    """Açılmış dizin -> [[tile_id, run_length, length, offset], ...] (sınırlı)."""
    i = 0
    n, i = _varint(veri, i)
    if n > MAX_DIR_ENTRIES:
        raise PaketHatasi('directory_too_large', str(n))
    # Her girdi en az 4 varint (4 bayt) ister; kalan veri yetmiyorsa bozuk.
    if 4 * n > len(veri) - i:
        raise PaketHatasi('directory_truncated')
    girdiler = []
    tid = 0
    for _ in range(n):
        v, i = _varint(veri, i)
        tid += v
        girdiler.append([tid, 0, 0, 0])
    for g in girdiler:
        g[1], i = _varint(veri, i)
    for g in girdiler:
        g[2], i = _varint(veri, i)
        if g[2] <= 0:
            raise PaketHatasi('directory_bad_length')
    for k, g in enumerate(girdiler):
        v, i = _varint(veri, i)
        if v == 0:
            if k == 0:
                raise PaketHatasi('directory_bad_offset')
            g[3] = girdiler[k - 1][3] + girdiler[k - 1][2]
        else:
            g[3] = v - 1
    return girdiler


def dizin_yaz(girdiler: List[List[int]]) -> bytes:
    """[[tile_id, run_length, length, offset], ...] -> açılmış dizin baytları."""
    out = bytearray()

    def v(x):
        while True:
            b = x & 0x7F
            x >>= 7
            if x:
                out.append(b | 0x80)
            else:
                out.append(b)
                return
    v(len(girdiler))
    onceki = 0
    for g in girdiler:
        v(g[0] - onceki)
        onceki = g[0]
    for g in girdiler:
        v(g[1])
    for g in girdiler:
        v(g[2])
    for k, g in enumerate(girdiler):
        if k > 0 and g[3] == girdiler[k - 1][3] + girdiler[k - 1][2]:
            v(0)
        else:
            v(g[3] + 1)
    return bytes(out)


def _u64(b, i):
    return int.from_bytes(b[i:i + 8], 'little')


def _i32(b, i):
    return int.from_bytes(b[i:i + 4], 'little', signed=True)


def baslik_coz(b: bytes) -> dict:
    if len(b) < HEADER_LEN or b[:7] != b'PMTiles':
        raise PaketHatasi('not_pmtiles')
    if b[7] != 3:
        raise PaketHatasi('unsupported_pmtiles_version', str(b[7]))
    return {
        'root_dir_offset': _u64(b, 8), 'root_dir_length': _u64(b, 16),
        'metadata_offset': _u64(b, 24), 'metadata_length': _u64(b, 32),
        'leaf_dirs_offset': _u64(b, 40), 'leaf_dirs_length': _u64(b, 48),
        'tile_data_offset': _u64(b, 56), 'tile_data_length': _u64(b, 64),
        'addressed_tiles': _u64(b, 72), 'tile_entries': _u64(b, 80),
        'tile_contents': _u64(b, 88), 'clustered': b[96],
        'internal_compression': b[97], 'tile_compression': b[98], 'tile_type': b[99],
        'min_zoom': b[100], 'max_zoom': b[101],
        'min_lon': _i32(b, 102) / 1e7, 'min_lat': _i32(b, 106) / 1e7,
        'max_lon': _i32(b, 110) / 1e7, 'max_lat': _i32(b, 114) / 1e7,
        'center_zoom': b[118], 'center_lon': _i32(b, 119) / 1e7, 'center_lat': _i32(b, 123) / 1e7,
    }


class PMTilesOkuyucu:
    """Yerel PMTiles v3 dosyası (yalnız MVT, gzip/düz). Bütün bölümler dosya sınırında denetlenir."""

    def __init__(self, yol: str):
        self.yol = yol
        self._kilit = threading.Lock()
        self._fh = open(yol, 'rb')
        try:
            self.boyut = os.fstat(self._fh.fileno()).st_size
            h = baslik_coz(self._oku(0, HEADER_LEN))
            for ad in ('root_dir', 'metadata', 'leaf_dirs', 'tile_data'):
                of, ln = h[ad + '_offset'], h[ad + '_length']
                if of + ln > self.boyut:
                    raise PaketHatasi('section_out_of_file', ad)
            if h['root_dir_offset'] + h['root_dir_length'] > ROOT_DIR_LIMIT:
                raise PaketHatasi('root_directory_too_far')
            if h['internal_compression'] not in (1, 2) or h['tile_compression'] not in (1, 2):
                raise PaketHatasi('unsupported_compression')
            if h['tile_type'] != 1:
                raise PaketHatasi('unsupported_tile_type', str(h['tile_type']))
            if h['max_zoom'] > PACK_MAX_ZOOM or h['min_zoom'] > h['max_zoom']:
                raise PaketHatasi('bad_zoom_range')
            self.h = h
            self._kok = dizin_coz(_ac(self._oku(h['root_dir_offset'], h['root_dir_length']),
                                      h['internal_compression'], MAX_DIR_BYTES, 'directory_too_large'))
            self._yapraklar: Dict[Tuple[int, int], list] = {}
        except Exception:
            self._fh.close()
            raise

    def kapat(self):
        with self._kilit:
            self._fh.close()

    def _oku(self, of: int, ln: int) -> bytes:
        if of < 0 or ln < 0 or of + ln > self.boyut:
            raise PaketHatasi('read_out_of_file')
        with self._kilit:
            self._fh.seek(of)
            b = self._fh.read(ln)
        if len(b) != ln:
            raise PaketHatasi('short_read')
        return b

    def meta(self) -> dict:
        h = self.h
        try:
            return json.loads(_ac(self._oku(h['metadata_offset'], h['metadata_length']),
                                  h['internal_compression'], MAX_DIR_BYTES, 'metadata_too_large'))
        except (ValueError, UnicodeDecodeError) as e:
            if isinstance(e, PaketHatasi):
                raise
            raise PaketHatasi('bad_metadata', str(e)) from None

    def _yaprak(self, of: int, ln: int) -> list:
        key = (of, ln)
        d = self._yapraklar.get(key)
        if d is None:
            if of + ln > self.h['leaf_dirs_length']:
                raise PaketHatasi('leaf_out_of_section')
            d = dizin_coz(_ac(self._oku(self.h['leaf_dirs_offset'] + of, ln),
                              self.h['internal_compression'], MAX_DIR_BYTES, 'directory_too_large'))
            if len(self._yapraklar) >= 256:
                self._yapraklar.pop(next(iter(self._yapraklar)))
            self._yapraklar[key] = d
        return d

    def bul(self, tid: int) -> Optional[Tuple[int, int]]:
        dizin = self._kok
        for _ in range(MAX_DIR_DEPTH):
            lo, hi, g = 0, len(dizin) - 1, None
            while lo <= hi:
                m = (lo + hi) // 2
                if dizin[m][0] <= tid:
                    g = dizin[m]
                    lo = m + 1
                else:
                    hi = m - 1
            if g is None:
                return None
            if g[1] == 0:
                dizin = self._yaprak(g[3], g[2])
                continue
            return (g[3], g[2]) if tid < g[0] + g[1] else None
        raise PaketHatasi('directory_too_deep')

    def karo(self, z: int, x: int, y: int) -> Optional[bytes]:
        """Sıkıştırılmış ham karo (gzip'li MVT) ya da None (pakette yok)."""
        if z < self.h['min_zoom'] or z > self.h['max_zoom']:
            return None
        r = self.bul(zxy_tileid(z, x, y))
        if r is None:
            return None
        of, ln = r
        if ln > MAX_TILE_BYTES:
            raise PaketHatasi('tile_too_large', str(ln))
        if of + ln > self.h['tile_data_length']:
            raise PaketHatasi('tile_out_of_section')
        return self._oku(self.h['tile_data_offset'] + of, ln)

    def girdiler(self) -> List[List[int]]:
        """Bütün karo girdileri (kök + yapraklar düzleştirilmiş). Araç/test için."""
        out = []

        def gez(d, derinlik):
            if derinlik > MAX_DIR_DEPTH:
                raise PaketHatasi('directory_too_deep')
            for g in d:
                if g[1] == 0:
                    gez(self._yaprak(g[3], g[2]), derinlik + 1)
                else:
                    out.append(list(g))
        gez(self._kok, 1)
        return out


def pmtiles_yaz(yol: str, karolar: Dict[int, bytes], meta: dict,
                bbox: Tuple[float, float, float, float],
                tile_type: int = 1, tile_compression: int = 2) -> dict:
    """{tile_id: sıkıştırılmış karo} -> kümelenmiş, içerik dedup'lu PMTiles v3 (atomik yazım).

    Belirlenimci: aynı girdi aynı bayt (gzip mtime=0, sıralı kimlik, json sort_keys).
    """
    if not karolar:
        raise PaketHatasi('empty_pack')
    return pmtiles_yaz_akis(yol, ((t, karolar[t]) for t in sorted(karolar)), meta, bbox,
                            tile_type=tile_type, tile_compression=tile_compression)


def pmtiles_yaz_akis(yol: str, karo_akisi, meta: dict,
                     bbox: Tuple[float, float, float, float],
                     tile_type: int = 1, tile_compression: int = 2) -> dict:
    """Akış yazıcı: ``karo_akisi`` artan tile_id sırasıyla (tid, bayt) üretir. Karo verisi
    belleğe toplanmaz, önce geçici dosyaya akar (bölge paketleri GB düzeyindedir); çıktı
    ``pmtiles_yaz`` ile bayt bayt aynı yerleşimdedir (başlık | kök | metadata | yapraklar |
    karo verisi). İçerik özdeşliği sha256 ile (dedup), ardışık aynı içerik run_length ile.
    """
    veri_yol = yol + '.veri.part'
    ofset_hash: Dict[bytes, int] = {}
    girdiler: List[List[int]] = []
    boy = 0
    onceki = -1
    ilk_t = None
    en_buyuk = 0
    with open(veri_yol, 'wb') as vf:
        for t, b in karo_akisi:
            if t <= onceki:
                raise PaketHatasi('tiles_not_sorted')
            onceki = t
            if ilk_t is None:
                ilk_t = t
            h = hashlib.sha256(b).digest()
            of = ofset_hash.get(h)
            if of is None:
                of = boy
                ofset_hash[h] = of
                vf.write(b)
                boy += len(b)
                en_buyuk = max(en_buyuk, len(b))
            son = girdiler[-1] if girdiler else None
            if son and son[3] == of and son[0] + son[1] == t:
                son[1] += 1
            else:
                girdiler.append([t, 1, len(b), of])
    if not girdiler:
        os.remove(veri_yol)
        raise PaketHatasi('empty_pack')
    tidler = (ilk_t, onceki)
    kok = _gzip(dizin_yaz(girdiler))
    yapraklar = b''
    if HEADER_LEN + len(kok) > ROOT_DIR_LIMIT:
        parca = 4096
        while True:
            yb, kg = bytearray(), []
            for i in range(0, len(girdiler), parca):
                d = _gzip(dizin_yaz(girdiler[i:i + parca]))
                kg.append([girdiler[i][0], 0, len(d), len(yb)])
                yb += d
            kok = _gzip(dizin_yaz(kg))
            if HEADER_LEN + len(kok) <= ROOT_DIR_LIMIT:
                yapraklar = bytes(yb)
                break
            parca *= 2
    metab = _gzip(json.dumps(meta, ensure_ascii=False, sort_keys=True).encode('utf-8'))
    kok_of = HEADER_LEN
    meta_of = kok_of + len(kok)
    yap_of = meta_of + len(metab)
    veri_of = yap_of + len(yapraklar)
    zmin, zmax = tileid_zoom(tidler[0]), tileid_zoom(tidler[-1])
    h = bytearray(b'PMTiles') + bytes([3])
    for x in (kok_of, len(kok), meta_of, len(metab), yap_of, len(yapraklar), veri_of, boy,
              sum(g[1] for g in girdiler), len(girdiler), len(ofset_hash)):
        h += int(x).to_bytes(8, 'little')
    h += bytes([1, 2, tile_compression, tile_type, zmin, zmax])
    for v in (bbox[0], bbox[1], bbox[2], bbox[3]):
        h += int(round(v * 1e7)).to_bytes(4, 'little', signed=True)
    h.append(zmax)
    for v in ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2):
        h += int(round(v * 1e7)).to_bytes(4, 'little', signed=True)
    assert len(h) == HEADER_LEN
    gecici = yol + '.part'
    try:
        with open(gecici, 'wb') as fh:
            for parca_b in (h, kok, metab, yapraklar):
                fh.write(parca_b)
            with open(veri_yol, 'rb') as vf:
                shutil.copyfileobj(vf, fh, 16 * 1024 * 1024)
        os.replace(gecici, yol)
    finally:
        try:
            os.remove(veri_yol)
        except OSError:
            pass
    return {'bytes': os.path.getsize(yol), 'tile_data_bytes': boy, 'entries': len(girdiler),
            'contents': len(ofset_hash), 'addressed': sum(g[1] for g in girdiler),
            'root_dir_bytes': len(kok), 'leaf_dir_bytes': len(yapraklar), 'min_zoom': zmin,
            'max_zoom': zmax, 'max_tile_bytes': en_buyuk}


# ---------------------------------------------------------------------------
# 4) MVT 2.1 çözücü (sınırlı)
# ---------------------------------------------------------------------------

def _alanlar(b: bytes):
    i, n = 0, len(b)
    while i < n:
        anahtar, i = _varint(b, i)
        no, tip = anahtar >> 3, anahtar & 7
        if tip == 0:
            v, i = _varint(b, i)
        elif tip == 1:
            if i + 8 > n:
                raise PaketHatasi('mvt_truncated')
            v = b[i:i + 8]
            i += 8
        elif tip == 2:
            ln, i = _varint(b, i)
            if i + ln > n:
                raise PaketHatasi('mvt_truncated')
            v = b[i:i + ln]
            i += ln
        elif tip == 5:
            if i + 4 > n:
                raise PaketHatasi('mvt_truncated')
            v = b[i:i + 4]
            i += 4
        else:
            raise PaketHatasi('mvt_bad_wire_type', str(tip))
        yield no, tip, v


def _paketli(b: bytes, sayac: list) -> List[int]:
    out, i = [], 0
    while i < len(b):
        v, i = _varint(b, i)
        out.append(v)
    sayac[0] += len(out)
    if sayac[0] > MAX_GEOM_INTS:
        raise PaketHatasi('mvt_too_many_geometry_ints')
    return out


def _zz(v: int) -> int:
    return (v >> 1) ^ -(v & 1)


def _deger(b: bytes):
    import struct
    for no, tip, v in _alanlar(b):
        if no == 1 and tip == 2:
            return v.decode('utf-8', 'replace')
        if no == 2 and tip == 5:
            return struct.unpack('<f', v)[0]
        if no == 3 and tip == 1:
            return struct.unpack('<d', v)[0]
        if no in (4, 5) and tip == 0:
            return v
        if no == 6 and tip == 0:
            return _zz(v)
        if no == 7 and tip == 0:
            return bool(v)
    return None


def geometri(komutlar: List[int]) -> List[List[Tuple[int, int]]]:
    """Komut dizisi -> [[(x, y), ...], ...] (karo birimi). ClosePath halkayı kapatır."""
    parcalar: List[List[Tuple[int, int]]] = []
    simdiki = None
    x = y = 0
    i, n = 0, len(komutlar)
    while i < n:
        c = komutlar[i]
        i += 1
        kid, say = c & 7, c >> 3
        if kid in (1, 2):
            if i + 2 * say > n:
                raise PaketHatasi('mvt_bad_geometry')
            for _ in range(say):
                x += _zz(komutlar[i])
                y += _zz(komutlar[i + 1])
                i += 2
                if kid == 1:
                    simdiki = [(x, y)]
                    parcalar.append(simdiki)
                elif simdiki is not None:
                    simdiki.append((x, y))
        elif kid == 7:
            if simdiki:
                simdiki.append(simdiki[0])
        else:
            raise PaketHatasi('mvt_bad_command', str(kid))
    return parcalar


def mvt_coz(veri: bytes, katman_suzgeci: Optional[frozenset] = None) -> Dict[str, dict]:
    """gzip'li ya da düz MVT -> {katman: {'extent': e, 'features': [(tip, öznitelik, parçalar)]}}.

    ``katman_suzgeci`` verilirse yalnız o katmanlar çözülür (diğerleri atlanır, sayılmaz).
    """
    if veri[:2] == b'\x1f\x8b':
        veri = _ac(veri, 2, MAX_MVT_BYTES, 'mvt_too_large')
    elif len(veri) > MAX_MVT_BYTES:
        raise PaketHatasi('mvt_too_large')
    katmanlar: Dict[str, dict] = {}
    oge_sayaci = 0
    geo_sayaci = [0]
    katman_sayisi = 0
    for no, tip, v in _alanlar(veri):
        if no != 3 or tip != 2:
            continue
        katman_sayisi += 1
        if katman_sayisi > MAX_LAYERS:
            raise PaketHatasi('mvt_too_many_layers')
        ad, extent, anahtar, deger, ham = None, 4096, [], [], []
        for no2, tip2, v2 in _alanlar(v):
            if no2 == 1 and tip2 == 2:
                ad = v2.decode('utf-8', 'replace')
                if katman_suzgeci is not None and ad not in katman_suzgeci:
                    break
            elif no2 == 2 and tip2 == 2:
                ham.append(v2)
            elif no2 == 3 and tip2 == 2:
                anahtar.append(v2.decode('utf-8', 'replace'))
            elif no2 == 4 and tip2 == 2:
                deger.append(_deger(v2))
            elif no2 == 5 and tip2 == 0:
                extent = v2
            if len(anahtar) + len(deger) > MAX_KEYS_VALUES:
                raise PaketHatasi('mvt_too_many_keys')
        if ad is None or (katman_suzgeci is not None and ad not in katman_suzgeci):
            continue
        if not (1 <= extent <= 1 << 16):
            raise PaketHatasi('mvt_bad_extent', str(extent))
        oge_sayaci += len(ham)
        if oge_sayaci > MAX_FEATURES:
            raise PaketHatasi('mvt_too_many_features')
        ozler = []
        for f in ham:
            gtip, etiket, geo = 0, [], []
            for no3, tip3, v3 in _alanlar(f):
                if no3 == 2 and tip3 == 2:
                    etiket = _paketli(v3, geo_sayaci)
                elif no3 == 3 and tip3 == 0:
                    gtip = v3
                elif no3 == 4 and tip3 == 2:
                    geo = _paketli(v3, geo_sayaci)
            oz = {}
            for k in range(0, len(etiket) - 1, 2):
                if etiket[k] < len(anahtar) and etiket[k + 1] < len(deger):
                    oz[anahtar[etiket[k]]] = deger[etiket[k + 1]]
            ozler.append((gtip, oz, geometri(geo)))
        katmanlar[ad] = {'extent': extent, 'features': ozler}
    return katmanlar


def mvt_katman_sil(veri_gz: bytes, silinecek: frozenset) -> bytes:
    """gzip'li MVT'den adı verilen katmanları bayt düzeyinde çıkarır (yeniden gzip, mtime=0).

    Araç kullanır (ör. paket z0-z7'deki Daylight 'landcover' katmanı OSM değildir).
    Katman dışı alanlar ve kalan katmanların baytı DEĞİŞMEZ.
    """
    ham = _ac(veri_gz, 2, MAX_MVT_BYTES, 'mvt_too_large') if veri_gz[:2] == b'\x1f\x8b' else veri_gz
    out = bytearray()
    i, n = 0, len(ham)
    degisti = False
    while i < n:
        bas = i
        anahtar, i = _varint(ham, i)
        no, tip = anahtar >> 3, anahtar & 7
        if tip != 2:
            raise PaketHatasi('mvt_bad_wire_type', str(tip))
        ln, i = _varint(ham, i)
        govde = ham[i:i + ln]
        i += ln
        if no == 3:
            ad = None
            for no2, tip2, v2 in _alanlar(govde):
                if no2 == 1 and tip2 == 2:
                    ad = v2.decode('utf-8', 'replace')
                    break
            if ad in silinecek:
                degisti = True
                continue
        out += ham[bas:i]
    if not degisti:
        return veri_gz
    return _gzip(bytes(out))


# ---------------------------------------------------------------------------
# 5) Coğrafya yardımcıları
# ---------------------------------------------------------------------------

def daire_bbox(lat: float, lon: float, r_km: float) -> Tuple[float, float, float, float]:
    """Merkez + yarıçap -> (batı, güney, doğu, kuzey) derece kutusu.

    1° enlem = 111,32 km (WGS84 ortalaması; faz 1 bölge ölçümüyle aynı tanım). Değer TEK
    yerde: ``map_pack_imagery.KM_PER_DEG`` (görüntü halkaları aynı ölçüyle çizilir).
    """
    dlat = r_km / _mpi.KM_PER_DEG
    dlon = r_km / (_mpi.KM_PER_DEG * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def merc_karo(lon: float, lat: float, z: int) -> Tuple[int, int]:
    """WGS84 -> Web Mercator XYZ karo indisi (kutupta kırpılır)."""
    n = 1 << z
    x = int(math.floor((lon + 180.0) / 360.0 * n))
    lr = math.radians(max(min(lat, MERC_MAX_LAT), -MERC_MAX_LAT))
    y = int(math.floor((1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n))
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def merc_lonlat(z: int, x: float, y: float) -> Tuple[float, float]:
    """Web Mercator karo koordinatı (kesirli) -> (boylam, enlem)."""
    n = float(1 << z)
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lon, lat


def kure_karo_bbox(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """HRMA küre karosu (GIBS EPSG:4326, açıklık 288/2^z) -> (batı, güney, doğu, kuzey).

    Geometrinin sahibi ``tile_cache`` (``tile_to_bbox``); burada aynı tanım çağrılır.
    """
    from hrma.analysis import tile_cache
    return tile_cache.tile_to_bbox(z, x, y)


def _kesisir(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


# ---------------------------------------------------------------------------
# 6) Paket listesi (manifest), bileşenler ve kurulu paketler
# ---------------------------------------------------------------------------
#
# Paket = bir ya da daha çok BİLEŞEN (``components``): bugün yalnız ``kind: vector``
# (OSM, PMTiles). ``kind: imagery`` (görüntü, SQLite kap) liste biçiminde TANIMLIDIR ama
# bu modül onu OKUMAZ (görüntü okuyucusu ayrı modülün işi; bkz. ``zemin_saglayici_kaydet``).
# İndirme ve doğrulama BİLEŞEN bazındadır: sonradan eklenen bileşen tek başına iner.

def _maps_dir() -> str:
    """Kurulum dizini: kullanıcı veri dizini/maps (Belgeler DEĞİL)."""
    from hrma.data.offline_store import _user_data_dir
    d = os.path.join(_user_data_dir(), 'maps')
    os.makedirs(d, exist_ok=True)
    return d


#: Testler kurulum dizinini değiştirebilir (ortam değişkeni YOK; kullanıcı girdisi değil).
_KURULUM_DIZINI_SAGLAYICI = _maps_dir


def kurulum_dizini() -> str:
    return _KURULUM_DIZINI_SAGLAYICI()


def manifest_dogrula(m) -> dict:
    """Paket listesini doğrular; her ihlal ADIYLA ``PaketHatasi('bad_manifest', ...)``."""
    def hata(ayrinti):
        raise PaketHatasi('bad_manifest', ayrinti)

    def metin(v):
        return isinstance(v, str) and 0 < len(v) <= 400
    if not isinstance(m, dict) or m.get('schema') != MANIFEST_SCHEMA:
        hata('schema')
    etiket = m.get('release_tag')
    if not isinstance(etiket, str) or not RELEASE_TAG_RE.match(etiket):
        hata('release_tag')
    paketler = m.get('packs')
    if not isinstance(paketler, list):
        hata('packs')
    gorulen_id, gorulen_dosya = set(), set()
    for p in paketler:
        if not isinstance(p, dict):
            hata('pack')
        pid = p.get('id')
        if not isinstance(pid, str) or not PACK_ID_RE.match(pid) or pid in gorulen_id:
            hata('id %r' % (pid,))
        gorulen_id.add(pid)
        if p.get('kind') not in ('site', 'region'):
            hata('%s kind' % pid)
        bbox = p.get('bbox')
        if (not isinstance(bbox, list) or len(bbox) != 4
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                           and math.isfinite(v) for v in bbox)
                or not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90)):
            hata('%s bbox' % pid)
        zm = p.get('zoom_max')
        if isinstance(zm, bool) or not isinstance(zm, int) or not (0 <= zm <= PACK_MAX_ZOOM):
            hata('%s zoom_max' % pid)
        if not metin(p.get('name_key')):
            hata('%s name_key' % pid)
        bilesenler = p.get('components')
        if not isinstance(bilesenler, list) or not bilesenler:
            hata('%s components' % pid)
        turler = [b.get('kind') if isinstance(b, dict) else None for b in bilesenler]
        if turler.count('vector') != 1 or turler.count('imagery') > 1 \
                or any(t not in COMPONENT_EXT for t in turler):
            hata('%s component kinds %r' % (pid, turler))
        for b in bilesenler:
            dosya = b.get('file')
            if (not isinstance(dosya, str) or not PACK_FILE_RE.match(dosya)
                    or not dosya.endswith(COMPONENT_EXT[b['kind']]) or dosya in gorulen_dosya):
                hata('%s file %r' % (pid, dosya))
            gorulen_dosya.add(dosya)
            boyut = b.get('size_bytes')
            if (not isinstance(boyut, int) or isinstance(boyut, bool)
                    or not (0 < boyut <= MAX_PACK_BYTES)):
                hata('%s size_bytes' % pid)
            if not isinstance(b.get('sha256'), str) or not SHA256_RE.match(b['sha256']):
                hata('%s sha256' % pid)
            if not metin(b.get('license')) or not metin(b.get('attribution')):
                hata('%s license/attribution' % pid)
            if b['kind'] == 'imagery':
                # Halka kuralı (18 Kas): görüntünün hangi düzeyi nerede var; panel metni buradan.
                try:
                    _mpi.duzey_kurali_dogrula(b.get('detail'), _mpi.IMAGERY_ZOOM_MIN,
                                              _mpi.IMAGERY_ZOOM_MAX)
                except _mpi.GoruntuHatasi as e:
                    hata('%s imagery %s' % (pid, e.ayrinti))
    return m


_manifest_cache: Dict[str, object] = {}


def manifest_oku(yol: Optional[str] = None) -> dict:
    """Uygulamayla gelen paket listesi (önbellekli; dosya değişirse yeniden okunur)."""
    yol = yol or MANIFEST_PATH
    try:
        st = os.stat(yol)
    except OSError:
        raise PaketHatasi('manifest_missing') from None
    anahtar = (yol, st.st_mtime_ns, st.st_size)
    if _manifest_cache.get('anahtar') != anahtar:
        try:
            with open(yol, encoding='utf-8') as fh:
                m = json.load(fh)
        except (OSError, ValueError) as e:
            raise PaketHatasi('bad_manifest', str(e)) from None
        _manifest_cache['m'] = manifest_dogrula(m)
        _manifest_cache['anahtar'] = anahtar
    return _manifest_cache['m']  # type: ignore[return-value]


def paket_bul(pid: str, m: Optional[dict] = None) -> dict:
    if not isinstance(pid, str) or not PACK_ID_RE.match(pid):
        raise PaketHatasi('unknown_pack')
    m = m or manifest_oku()
    for p in m['packs']:
        if p['id'] == pid:
            return p
    raise PaketHatasi('unknown_pack')


def vektor_bileseni(p: dict) -> dict:
    for b in p['components']:
        if b['kind'] == 'vector':
            return b
    raise PaketHatasi('bad_manifest', 'no vector component')


def paket_boyutu(p: dict) -> int:
    return sum(b['size_bytes'] for b in p['components'])


def _paket_yolu(dosya: str) -> str:
    kok = os.path.realpath(kurulum_dizini())
    yol = os.path.realpath(os.path.join(kok, dosya))
    if not PACK_FILE_RE.match(dosya) or not yol.startswith(kok + os.sep):
        raise PaketHatasi('path_not_allowed')
    return yol


def _isaret_yolu(yol: str) -> str:
    return yol + '.verified.json'


def _part_yolu(yol: str) -> str:
    return yol + '.part'


def _sha256_dosya(yol: str, iptal: Optional[threading.Event] = None) -> str:
    h = hashlib.sha256()
    with open(yol, 'rb') as fh:
        while True:
            if iptal is not None and iptal.is_set():
                raise PaketHatasi('cancelled')
            b = fh.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


_dogrulama_cache: Dict[str, tuple] = {}
_dogrulama_kilidi = threading.Lock()


def bilesen_kurulu_mu(b: dict) -> bool:
    """Bileşen dosyası var, boyutu ve sha256'sı listeyle aynı mı (doğrulanmamış dosya okunmaz).

    sha256 bir kez hesaplanır ve dosyanın (boyut, mtime_ns) imzasıyla işaret dosyasına
    yazılır; imza değişirse (dosya elle değiştirildiyse) yeniden hesaplanır.
    """
    try:
        yol = _paket_yolu(b['file'])
        st = os.stat(yol)
    except (OSError, PaketHatasi):
        return False
    imza = (st.st_size, st.st_mtime_ns, b['sha256'])
    with _dogrulama_kilidi:
        if _dogrulama_cache.get(yol) == imza:
            return True
    if st.st_size != b['size_bytes']:
        return False
    try:
        with open(_isaret_yolu(yol), encoding='utf-8') as fh:
            isaret = json.load(fh)
        if (isaret.get('sha256') == b['sha256'] and isaret.get('size') == st.st_size
                and isaret.get('mtime_ns') == st.st_mtime_ns):
            with _dogrulama_kilidi:
                _dogrulama_cache[yol] = imza
            return True
    except (OSError, ValueError, AttributeError):
        pass
    if _sha256_dosya(yol) != b['sha256']:
        return False
    _isaret_yaz(yol, b['sha256'])
    with _dogrulama_kilidi:
        _dogrulama_cache[yol] = imza
    return True


def kurulu_mu(p: dict) -> bool:
    """Paketin BÜTÜN bileşenleri kurulu ve doğrulanmış mı."""
    return all(bilesen_kurulu_mu(b) for b in p['components'])


def _isaret_yaz(yol: str, sha: str) -> None:
    st = os.stat(yol)
    gecici = _isaret_yolu(yol) + '.part'
    with open(gecici, 'w', encoding='utf-8') as fh:
        json.dump({'sha256': sha, 'size': st.st_size, 'mtime_ns': st.st_mtime_ns}, fh)
    os.replace(gecici, _isaret_yolu(yol))


_okuyucular: Dict[str, Tuple[tuple, PMTilesOkuyucu]] = {}
_okuyucu_kilidi = threading.Lock()


def kurulu_paketler(m: Optional[dict] = None) -> List[Tuple[dict, PMTilesOkuyucu]]:
    """Vektör bileşeni doğrulanmış paketler ve okuyucuları (kimliğe göre sıralı).

    Çizim yalnız vektör bileşenine bakar; görüntü bileşeni eksik olsa da vektör çizilir.
    İnmekte olan paket okunmaz.
    """
    m = m or manifest_oku()
    out = []
    for p in sorted(m['packs'], key=lambda q: q['id']):
        if indirme_durumu(p['id']).get('state') == 'downloading':
            continue
        b = vektor_bileseni(p)
        if not bilesen_kurulu_mu(b):
            continue
        yol = _paket_yolu(b['file'])
        st = os.stat(yol)
        imza = (st.st_size, st.st_mtime_ns, b['sha256'])
        with _okuyucu_kilidi:
            kayit = _okuyucular.get(yol)
            if kayit is None or kayit[0] != imza:
                if kayit is not None:
                    kayit[1].kapat()
                kayit = (imza, PMTilesOkuyucu(yol))
                _okuyucular[yol] = kayit
        out.append((p, kayit[1]))
    return out


def _okuyucu_birak(yol: str) -> None:
    with _okuyucu_kilidi:
        kayit = _okuyucular.pop(yol, None)
    if kayit is not None:
        kayit[1].kapat()
    # Görüntü bileşeninin açık SQLite bağlantısı da kapanır (silme / yeniden kurulum).
    _mpi.okuyuculari_birak(yol)
    with _dogrulama_kilidi:
        _dogrulama_cache.pop(yol, None)


def paketler_ozeti(m: Optional[dict] = None) -> List[dict]:
    """``GET /api/map-packs`` gövdesi (uç sözleşmesi; faz 2 brif)."""
    m = m or manifest_oku()
    out = []
    for p in m['packs']:
        durum = paket_durumu(p)
        vb = vektor_bileseni(p)
        lisanslar = []
        for b in p['components']:
            if b['license'] not in lisanslar:
                lisanslar.append(b['license'])
        out.append({
            'id': p['id'], 'kind': p['kind'], 'name_key': p['name_key'],
            'bbox': list(p['bbox']), 'zoom_max': p['zoom_max'],
            'size_bytes': paket_boyutu(p),
            # Sözleşmenin tek 'sha256' alanı vektör bileşeninin özetidir; her bileşenin
            # özeti 'components' içinde ayrıca yazılıdır.
            'sha256': vb['sha256'],
            'license': '; '.join(lisanslar),
            'status': durum['status'], 'progress': durum['progress'],
            'error_code': durum['error_code'],
            'components': [_bilesen_ozeti(b) for b in p['components']],
        })
    return out


def goruntu_ayrinti_ozeti(detail: dict) -> dict:
    """Görüntü bileşeninin halka kuralı, panel için: düzeylerin piksel boyu [m] koddan
    (``map_pack_imagery.piksel_metre``), yarıçaplar listeden."""
    k = _mpi.duzey_kurali_dogrula(detail, _mpi.IMAGERY_ZOOM_MIN, _mpi.IMAGERY_ZOOM_MAX)
    return {'full_zoom_max': k['full_zoom_max'],
            'full_m_per_px': round(_mpi.piksel_metre(k['full_zoom_max']), 1),
            'rings': [{'zoom': h['zoom'], 'radius_km': h['radius_km'],
                       'm_per_px': round(_mpi.piksel_metre(h['zoom']), 1)} for h in k['rings']]}


def _bilesen_ozeti(b: dict) -> dict:
    o = {'kind': b['kind'], 'size_bytes': b['size_bytes'], 'sha256': b['sha256'],
         'license': b['license'], 'attribution': b['attribution'],
         'installed': bilesen_kurulu_mu(b)}
    if b['kind'] == 'imagery':
        o['detail'] = goruntu_ayrinti_ozeti(b['detail'])
    return o


# ---------------------------------------------------------------------------
# 7) İndirme yöneticisi (bileşen bazında)
# ---------------------------------------------------------------------------

class _YonlendirmeKapisi(urllib.request.HTTPRedirectHandler):
    """Yönlendirme yalnız HTTPS + izinli host'a; aksi 'redirect_not_allowed'."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_izinli_host(newurl):
            raise PaketHatasi('redirect_not_allowed',
                              urllib.parse.urlsplit(newurl).hostname or '')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def url_izinli_host(url: str) -> bool:
    try:
        u = urllib.parse.urlsplit(url)
        port = u.port
    except ValueError:
        return False
    return (u.scheme == 'https' and u.hostname in ALLOWED_REDIRECT_HOSTS
            and u.username is None and u.password is None and port in (None, 443))


def url_kapisi(url: str) -> bool:
    """Başlangıç adresi kapısı: HRMA release öneki + HTTPS + izinli host."""
    return url.startswith(_RELEASE_DOWNLOAD_PREFIX) and url_izinli_host(url)


#: Testler yerel HTTP fikstürü için kapıyı ve açıcıyı değiştirebilir (ürün yolu sabit).
_URL_KAPISI = url_kapisi


def indirme_url(m: dict, b: dict) -> str:
    """İndirme adresi YALNIZ listeden kurulur: <HRMA release öneki><etiket>/<dosya>."""
    url = '%s%s/%s' % (_RELEASE_DOWNLOAD_PREFIX, m['release_tag'], b['file'])
    if not _URL_KAPISI(url):
        raise PaketHatasi('url_not_allowed')
    return url


def _acici_kur():
    return urllib.request.build_opener(_YonlendirmeKapisi())


_ACICI = _acici_kur

_durumlar: Dict[str, dict] = {}
_durum_kilidi = threading.Lock()


def _durum_yaz(pid: str, **alan) -> None:
    with _durum_kilidi:
        d = _durumlar.setdefault(pid, {'state': 'not_installed', 'bytes_done': 0,
                                       'bytes_total': 0, 'error_code': None})
        d.update(alan)


def indirme_durumu(pid: str) -> dict:
    with _durum_kilidi:
        return dict(_durumlar.get(pid) or {})


def paket_durumu(p: dict) -> dict:
    """status + progress + error_code (gerçek bayt, sahte ilerleme yok)."""
    d = indirme_durumu(p['id'])
    if d.get('state') == 'downloading':
        return {'status': 'downloading',
                'progress': {'bytes_done': d['bytes_done'], 'bytes_total': d['bytes_total']},
                'error_code': None}
    if kurulu_mu(p):
        return {'status': 'installed', 'progress': None, 'error_code': None}
    # Yarım kalmış indirme (kesinti): diskteki gerçek bayt; sonraki istek Range ile sürer.
    elde = 0
    yarim = False
    for b in p['components']:
        if bilesen_kurulu_mu(b):
            elde += b['size_bytes']
            continue
        try:
            elde += os.path.getsize(_part_yolu(_paket_yolu(b['file'])))
            yarim = True
        except (OSError, PaketHatasi):
            pass
    ilerleme = {'bytes_done': elde, 'bytes_total': paket_boyutu(p)} if (yarim or elde) else None
    if d.get('state') == 'error':
        return {'status': 'error', 'progress': ilerleme, 'error_code': d.get('error_code')}
    return {'status': 'not_installed', 'progress': ilerleme, 'error_code': None}


def disk_bos(dizin: str) -> int:
    return shutil.disk_usage(dizin).free


#: Testler disk alanı ölçerini değiştirebilir (disk dolu vakası).
_DISK_BOS = disk_bos

_iptaller: Dict[str, threading.Event] = {}
_is_parcaciklari: Dict[str, threading.Thread] = {}


def indirme_baslat(pid: str, consent=None, *, bekle: bool = False) -> dict:
    """Kullanıcı onayıyla eksik bileşenleri indirir. ``consent`` tam ``True`` değilse İSTEK YOK."""
    if consent is not True:
        raise PaketHatasi('consent_required')
    m = manifest_oku()
    p = paket_bul(pid, m)
    if indirme_durumu(pid).get('state') == 'downloading':
        raise PaketHatasi('already_downloading')
    eksik = [b for b in p['components'] if not bilesen_kurulu_mu(b)]
    if not eksik:
        raise PaketHatasi('already_installed')
    isler, kalan, elde = [], 0, paket_boyutu(p) - sum(b['size_bytes'] for b in eksik)
    for b in eksik:
        yol = _paket_yolu(b['file'])
        part = _part_yolu(yol)
        try:
            mevcut = os.path.getsize(part)
        except OSError:
            mevcut = 0
        if mevcut > b['size_bytes']:
            os.remove(part)
            mevcut = 0
        kalan += b['size_bytes'] - mevcut
        elde += mevcut
        isler.append((indirme_url(m, b), yol, b['size_bytes'], b['sha256']))
    if _DISK_BOS(kurulum_dizini()) < kalan + DISK_PAY_BYTES:
        _durum_yaz(pid, state='error', error_code='disk_full', bytes_done=elde,
                   bytes_total=paket_boyutu(p))
        raise PaketHatasi('disk_full')
    iptal = threading.Event()
    _iptaller[pid] = iptal
    _durum_yaz(pid, state='downloading', bytes_done=elde, bytes_total=paket_boyutu(p),
               error_code=None)
    t = threading.Thread(target=_indir, args=(pid, isler, iptal, paket_boyutu(p)),
                         name='hrma-map-pack-%s' % pid, daemon=True)
    _is_parcaciklari[pid] = t
    t.start()
    if bekle:
        t.join()
    return indirme_durumu(pid)


def indirme_iptal(pid: str) -> dict:
    paket_bul(pid)
    iptal = _iptaller.get(pid)
    if iptal is None or indirme_durumu(pid).get('state') != 'downloading':
        raise PaketHatasi('not_downloading')
    iptal.set()
    t = _is_parcaciklari.get(pid)
    if t is not None:
        t.join(timeout=DOWNLOAD_TIMEOUT_S + 5)
    return indirme_durumu(pid)


def paket_sil(pid: str) -> dict:
    p = paket_bul(pid)
    if indirme_durumu(pid).get('state') == 'downloading':
        raise PaketHatasi('downloading')
    silinen = 0
    for b in p['components']:
        yol = _paket_yolu(b['file'])
        _okuyucu_birak(yol)
        for f in (yol, _isaret_yolu(yol), _part_yolu(yol)):
            try:
                boyut = os.path.getsize(f)
                os.remove(f)
                silinen += boyut
            except OSError:
                pass
    _durum_yaz(pid, state='not_installed', bytes_done=0, bytes_total=0, error_code=None)
    return {'deleted_bytes': silinen}


#: Bütünlüğü bozan hatalar: yarım dosya silinir (devam edilemez, baştan inmeli).
_BOZUK_PART_KODLARI = frozenset({'sha256_mismatch', 'size_mismatch', 'too_many_bytes',
                                 'range_mismatch'})


def _indir(pid: str, isler: list, iptal: threading.Event, toplam_paket: int) -> None:
    part = None
    try:
        onceki = toplam_paket - sum(t[2] for t in isler)   # zaten kurulu bileşenler
        for url, yol, toplam, sha in isler:
            part = _part_yolu(yol)
            _indir_bilesen(pid, url, yol, part, toplam, sha, iptal, onceki)
            onceki += toplam
        _durum_yaz(pid, state='installed', bytes_done=toplam_paket, error_code=None)
    except PaketHatasi as e:
        if e.kod == 'cancelled':
            # İptal = vazgeçme: o anki yarım dosya silinir (devam yalnız kesintide).
            if part:
                try:
                    os.remove(part)
                except OSError:
                    pass
            _durum_yaz(pid, state='not_installed', bytes_done=0, error_code=None)
        else:
            if e.kod in _BOZUK_PART_KODLARI and part:
                try:
                    os.remove(part)
                except OSError:
                    pass
            _durum_yaz(pid, state='error', error_code=e.kod)
    except OSError as e:
        import errno
        kod = 'disk_full' if getattr(e, 'errno', None) == errno.ENOSPC else 'io_error'
        _durum_yaz(pid, state='error', error_code=kod)
    except Exception:
        _durum_yaz(pid, state='error', error_code='network_error')
    finally:
        _iptaller.pop(pid, None)


def _indir_bilesen(pid, url, yol, part, toplam, sha, iptal, onceki):
    import urllib.error
    h = hashlib.sha256()
    try:
        mevcut = os.path.getsize(part)
    except OSError:
        mevcut = 0
    if mevcut:
        # Devam: önce elde olan kısmın özeti (sha256 bütün dosya üzerinden doğrulanır).
        with open(part, 'rb') as fh:
            while True:
                if iptal.is_set():
                    raise PaketHatasi('cancelled')
                b = fh.read(1024 * 1024)
                if not b:
                    break
                h.update(b)
    if mevcut < toplam:
        req = urllib.request.Request(url, headers={'User-Agent': _HTTP_UA,
                                                   'Accept-Encoding': 'identity'})
        if mevcut:
            req.add_header('Range', 'bytes=%d-' % mevcut)
        try:
            yanit = _ACICI().open(req, timeout=DOWNLOAD_TIMEOUT_S)
        except urllib.error.HTTPError as e:
            raise PaketHatasi('http_%d' % e.code) from None
        with yanit:
            kod = getattr(yanit, 'status', 200)
            if mevcut and kod == 206:
                cr = (yanit.headers.get('Content-Range') or '').strip()
                mt = re.match(r'^bytes (\d+)-(\d+)/(\d+)$', cr)
                if not mt or int(mt.group(1)) != mevcut or int(mt.group(3)) != toplam:
                    raise PaketHatasi('range_mismatch', cr)
                kip = 'ab'
            elif kod == 200:
                # İlk indirme ya da sunucu aralığı yok saydı: baştan.
                if mevcut:
                    h = hashlib.sha256()
                    mevcut = 0
                cl = yanit.headers.get('Content-Length')
                if cl is not None and (not cl.strip().isdigit() or int(cl) != toplam):
                    raise PaketHatasi('size_mismatch', cl)
                kip = 'wb'
            else:
                raise PaketHatasi('http_%d' % kod)
            _durum_yaz(pid, bytes_done=onceki + mevcut)
            with open(part, kip) as fh:
                while True:
                    if iptal.is_set():
                        raise PaketHatasi('cancelled')
                    b = yanit.read(DOWNLOAD_CHUNK)
                    if not b:
                        break
                    if mevcut + len(b) > toplam:
                        raise PaketHatasi('too_many_bytes')
                    fh.write(b)
                    h.update(b)
                    mevcut += len(b)
                    _durum_yaz(pid, bytes_done=onceki + mevcut)
                fh.flush()
                os.fsync(fh.fileno())
    if mevcut != toplam:
        # Kesik indirme: yarım dosya KALIR (sonraki istekte Range ile devam).
        raise PaketHatasi('incomplete_download', '%d/%d' % (mevcut, toplam))
    if h.hexdigest() != sha:
        raise PaketHatasi('sha256_mismatch')
    # Atomik kurulum: doğrulanmış geçici dosya -> son ad.
    _okuyucu_birak(yol)
    os.replace(part, yol)
    _isaret_yaz(yol, sha)


# ---------------------------------------------------------------------------
# 8) Etiketler (ad politikası K6)
# ---------------------------------------------------------------------------

def ad_sec(oz: dict, dil: str) -> Optional[str]:
    """Arayüz diline göre ad (karar K6, ``AD_SIRASI``): ilk dolu alan.

    TR: name:tr -> name:en -> name.  EN: name:en -> name. (16 Kas düzeltmesi: TR ekranda
    ``name:tr`` olmayan yabancı sahada yerel yazı — ör. Jiuquan'da Çince — yerine Latin
    yazılı uluslararası ad gösterilir.) Hiçbiri yoksa None (etiket basılmaz).
    """
    for alan in AD_SIRASI[dil]:
        v = oz.get(alan)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def bbox_dogrula(bbox) -> Tuple[float, float, float, float]:
    if (not isinstance(bbox, (list, tuple)) or len(bbox) != 4
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v) for v in bbox)):
        raise PaketHatasi('bad_bbox')
    w, s, e, n = (float(v) for v in bbox)
    if not (-180 <= w < e <= 180 and -MERC_MAX_LAT <= s < n <= MERC_MAX_LAT):
        raise PaketHatasi('bad_bbox')
    return w, s, e, n


def etiketler(bbox, z: int, dil: str, paketler=None) -> dict:
    """Kutudaki yer adları + fırlatma kompleksi POI'leri (z = Web Mercator düzeyi 0-15)."""
    w, s, e, n = bbox_dogrula(bbox)
    if isinstance(z, bool) or not isinstance(z, int) or not (0 <= z <= PACK_MAX_ZOOM):
        raise PaketHatasi('bad_zoom')
    if dil not in LABEL_LANGS:
        raise PaketHatasi('bad_lang')
    x0, y0 = merc_karo(w, n, z)
    x1, y1 = merc_karo(e, s, z)
    if (x1 - x0 + 1) * (y1 - y0 + 1) > MAX_LABEL_TILES:
        raise PaketHatasi('bbox_too_large')
    if paketler is None:
        paketler = kurulu_paketler()
    adaylar = [(p, r) for p, r in paketler if _kesisir(tuple(p['bbox']), (w, s, e, n))]
    gorulen = {}
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            veri = None
            for _p, r in adaylar:
                veri = r.karo(z, x, y)
                if veri:
                    break
            if not veri:
                continue
            L = mvt_coz(veri, frozenset({'places', 'pois'}))
            for katman, turler in (('places', PLACE_KINDS), ('pois', LAUNCH_POI_KINDS)):
                kat = L.get(katman)
                if not kat:
                    continue
                ext = kat['extent']
                for gtip, oz, parca in kat['features']:
                    tur = oz.get('kind')
                    if gtip != 1 or tur not in turler or not parca or not parca[0]:
                        continue
                    ad = ad_sec(oz, dil)
                    if not ad:
                        continue
                    px, py = parca[0][0]
                    lon, lat = merc_lonlat(z, x + px / ext, y + py / ext)
                    if not (w <= lon <= e and s <= lat <= n):
                        continue
                    mz = oz.get('min_zoom')
                    rank = int(mz) if isinstance(mz, (int, float)) and not isinstance(mz, bool) \
                        and math.isfinite(mz) else PACK_MAX_ZOOM
                    anahtar = (ad, round(lon, 3), round(lat, 3))
                    if anahtar not in gorulen:
                        gorulen[anahtar] = {'name': ad, 'lon': round(lon, 5), 'lat': round(lat, 5),
                                            'kind': tur, 'rank': rank}
    sirali = sorted(gorulen.values(), key=lambda d: (d['rank'], d['name'], d['lon'], d['lat']))
    return {'labels': sirali[:MAX_LABELS], 'truncated': len(sirali) > MAX_LABELS}


# ---------------------------------------------------------------------------
# 9) Raster çizim (pack_detail katmanı)
# ---------------------------------------------------------------------------

#: Stil (HRMA seçimi; harita okunabilirliği için). RGBA; z15'te 512 px karo için çizgi
#: genişliği [px]. Düşük düzeyde genişlik 2^(z-15) ile ölçeklenir, en az 1 px.
_YOL_STIL = (   # çizim sırası: alttan üste
    ('path', (226, 208, 176, 190), 1.0, 14),
    ('minor_road', (245, 243, 236, 225), 2.0, 13),
    ('rail', (176, 176, 188, 230), 1.6, 11),
    ('aeroway', (222, 222, 238, 235), 4.0, 11),
    ('medium_road', (255, 246, 214, 235), 2.8, 11),
    ('major_road', (255, 222, 120, 240), 3.6, 9),
    ('highway', (255, 168, 76, 245), 5.0, 6),
)
_SU_ALAN = (70, 132, 200, 150)
_KIYI = (160, 205, 250, 220)
_SU_CIZGI = (100, 170, 235, 225)
_BINA_DOLGU = (238, 226, 210, 150)
_BINA_KENAR = (120, 108, 96, 200)
_ARAZI = {   # Protomaps landuse türü -> RGBA (ölçülen türler, faz 1 dökümü)
    'residential': (214, 200, 186, 60), 'commercial': (222, 180, 160, 70),
    'industrial': (210, 178, 160, 70), 'military': (214, 130, 130, 70),
    'farmland': (196, 214, 150, 45), 'wood': (92, 150, 92, 75), 'forest': (92, 150, 92, 75),
    'grass': (150, 196, 128, 55), 'meadow': (150, 196, 128, 55), 'grassland': (150, 196, 128, 55),
    'park': (130, 196, 130, 60), 'scrub': (160, 184, 120, 55), 'wetland': (120, 176, 176, 60),
    'nature_reserve': (120, 176, 120, 35), 'beach': (234, 218, 170, 80),
    'sand': (234, 218, 170, 80), 'bare_rock': (190, 184, 176, 60),
    'aerodrome': (204, 204, 222, 70), 'airfield': (204, 204, 222, 70),
    'runway': (190, 190, 205, 120), 'cemetery': (170, 200, 170, 60),
}
_SUPERSAMPLE = 2
_CIZIM_KATMANLARI = frozenset({'water', 'landuse', 'buildings', 'roads'})


def vektor_zoom(z: int, lat: float) -> int:
    """Küre karosu z'si için piksel açıklığı en yakın Web Mercator düzeyi (en çok 15).

    Mercator 256 px karo pikseli = küre 512 px karo pikselinin 2,5·cos(enlem) katı
    (``_MERC_KURE_ORANI``); eşit piksel için vz = z + log2(2,5·cos(enlem)).
    """
    c = max(math.cos(math.radians(lat)), 1e-6)
    return int(max(0, min(PACK_MAX_ZOOM, round(z + math.log2(_MERC_KURE_ORANI * c)))))


def _cizgi_genisligi(taban: float, z: int, olcek: int) -> int:
    return max(1, int(round(taban * (2.0 ** min(0, z - 15)) * olcek)))


# --- Zemin (görüntü) sağlayıcısı: BAĞLANTI NOKTASI --------------------------------
# Görüntü bileşenini (Copernicus Sentinel-2 mozaiği, SQLite kap) okuyan modül
# ``map_pack_imagery``'dir (ithal yan etkisi yok); sağlayıcı yalnız açık çağrıyla,
# ``goruntu_zemini_kaydet`` ile kaydedilir. Sözleşme:
#   fn(z, x, y) -> bytes | None
#     z, x, y : HRMA küre karosu (GIBS EPSG:4326 ızgarası, açıklık 288/2^z, 512 px)
#     dönüş   : o karonun 512x512 görüntüsü (Pillow'un açtığı JPEG/PNG/WebP baytı) ya da
#               None (görüntü yok -> bugünkü davranış: saydam vektör katmanı, zemin
#               istemcideki mevcut doku olur)
#   fn.surum  : önbellek anahtarına giren kısa sürüm dizesi (^[a-z0-9._-]{1,40}$)
# Kayıt: ``zemin_saglayici_kaydet(fn)``; kaldırma: ``zemin_saglayici_kaydet(None)``.
_ZEMIN_SAGLAYICI = None
_SURUM_RE = re.compile(r'^[a-z0-9._-]{1,40}$')


def zemin_saglayici_kaydet(fn) -> None:
    global _ZEMIN_SAGLAYICI
    if fn is not None:
        if not callable(fn) or not isinstance(getattr(fn, 'surum', None), str) \
                or not _SURUM_RE.match(fn.surum):
            raise PaketHatasi('bad_ground_provider')
    _ZEMIN_SAGLAYICI = fn


def zemin_kimligi() -> str:
    return _ZEMIN_SAGLAYICI.surum if _ZEMIN_SAGLAYICI is not None else 'none'


def _zemin_oku(z: int, x: int, y: int):
    """Kayıtlı sağlayıcıdan 512x512 RGBA zemin ya da None (biçim dışı bayt -> adıyla ret)."""
    from PIL import Image
    if _ZEMIN_SAGLAYICI is None:
        return None
    b = _ZEMIN_SAGLAYICI(z, x, y)
    if b is None:
        return None
    if not isinstance(b, (bytes, bytearray)) or len(b) > MAX_TILE_BYTES:
        raise PaketHatasi('bad_ground_tile')
    try:
        im = Image.open(io.BytesIO(b))
        if im.size != (KURE_TILE_PX, KURE_TILE_PX):
            raise PaketHatasi('bad_ground_tile', 'size %r' % (im.size,))
        return im.convert('RGBA')
    except PaketHatasi:
        raise
    except Exception as e:
        raise PaketHatasi('bad_ground_tile', type(e).__name__) from None


# --- Görüntü bileşeni -> zemin (V307/FS-HARİTA-GÖRÜNTÜ) -------------------------------
# Uygulama açılışında BİR KEZ, açık çağrıyla bağlanır (``hrma/app.py``,
# ``goruntu_zemini_kaydet()``). Kurulu görüntü bileşeni yoksa sağlayıcı her karoda None
# döner: çizim bugünkü (saydam vektör) yoldan BİT-AYNI çıkar; yalnız önbellek anahtarındaki
# sağlayıcı sürümü değişir (``zemin_kimligi``).

def kurulu_goruntu_kaynaklari(m: Optional[dict] = None) -> List[Tuple[str, str]]:
    """Kurulu ve sha256'sı DOĞRULANMIŞ görüntü bileşenlerinin ``(yol, sha256)`` listesi.

    İnmekte olan paketin bileşeni listeye girmez (``kurulu_paketler`` ile aynı kural).
    """
    m = m or manifest_oku()
    out = []
    for p in sorted(m['packs'], key=lambda q: q['id']):
        if indirme_durumu(p['id']).get('state') == 'downloading':
            continue
        for b in p['components']:
            if b['kind'] == 'imagery' and bilesen_kurulu_mu(b):
                out.append((_paket_yolu(b['file']), b['sha256']))
    return out


def _goruntu_buyut(ata) -> bytes:
    """Karo kendi düzeyinde yoksa (en ince düzeyin üstü ya da halka dışı; halka kuralı
    ``map_pack_imagery``) atadaki pencereyi 512 px'e büyütür (dz=1: 256 px … dz=4: 32 px
    pencere; LANCZOS). Ölçülmüş pikselin büyütülmesidir, yeni ayrıntı eklenmez. Kısmi karoda alfa öncarpımlı büyütülür (saydam kenarda renk
    sızması yok). Çıktı kayıpsız PNG: çizici sonucu bir kez daha kodladığı için ara adımda
    kayıplı kodlama yapılmaz.
    """
    from PIL import Image
    px0, py0, k = ata.pencere
    with Image.open(io.BytesIO(ata.veri)) as im:
        if ata.coverage >= 10000:
            p = im.convert('RGB').crop((px0, py0, px0 + k, py0 + k))
            p = p.resize((KURE_TILE_PX, KURE_TILE_PX), Image.LANCZOS)
        else:
            p = im.convert('RGBA').convert('RGBa').crop((px0, py0, px0 + k, py0 + k))
            p = p.resize((KURE_TILE_PX, KURE_TILE_PX), Image.LANCZOS).convert('RGBA')
    bio = io.BytesIO()
    p.save(bio, 'PNG', compress_level=1)
    return bio.getvalue()


def goruntu_zemini_kaydet() -> None:
    """Görüntü bileşeni okuyucusunu ``pack_detail`` çizicisinin zemini olarak kaydeder.

    * Kaynak: ``kurulu_goruntu_kaynaklari`` (her karoda yeniden okunur; paket kurulunca ya
      da silinince yeniden başlatma gerekmez).
    * Kısmi karo VERİLİR (``kismi_karo=True``): çizici zeminin alfasını korur
      (``karo_ciz``), veri olmayan piksel saydam kalır ve istemcide alttaki doku görünür.
    * Karo kendi düzeyinde yoksa (z14/z15 ya da halka dışı) kaynak düzeyin atasındaki
      pencere büyütülür (``_goruntu_buyut``): zemin halkadan halkaya boşluksuz geçer.
    * Okuyucu hatası (bozuk/şişirilmiş dosya) adıyla ``PaketHatasi(<okuyucu kodu>)`` olur:
      karo ucu 503 + ``error_code`` döner (500 yok, sessiz yedek yok).
    """
    mpi = _mpi
    temel = mpi.saglayici(kurulu_goruntu_kaynaklari, kismi_karo=True, buyutucu=_goruntu_buyut)

    def fn(z, x, y):
        try:
            return temel(z, x, y)
        except mpi.GoruntuHatasi as e:
            raise PaketHatasi(e.kod, e.ayrinti) from None
    fn.surum = temel.surum
    zemin_saglayici_kaydet(fn)


def karo_ciz(z: int, x: int, y: int, paketler=None) -> Optional[bytes]:
    """Küre karosu (GIBS ızgarası) için WebP ya da None.

    Zemin sağlayıcısı yoksa ya da None dönerse: SAYDAM RGBA, kayıpsız WebP (istemcideki
    mevcut zemin dokusunun üstüne biner). Zemin varsa: zemin + vektör, kayıplı WebP; zemin
    tam karoysa opak RGB, kısmi karoysa (görüntüsüz piksel) ALFASI korunur: veri olmayan
    piksel saydam kalır, istemcide alttaki doku görünür (siyah/yapay renk yok). Zemin
    varken alan dolguları (arazi kullanımı, su, bina içi) çizilmez; çizgiler (kıyı, akarsu,
    yol, bina kenarı) çizilir — görüntünün kendisi o alanların ölçülmüş rengidir.
    None = hiçbir kurulu paket bu karoyu kapsamıyor (uç 404; sahte doku yok). Kapsayan
    paket varsa çizilecek öğe olmasa da (açık deniz) saydam karo döner — gerçek veri.
    """
    from PIL import Image, ImageDraw
    if not (0 <= z <= PACK_MAX_ZOOM):
        return None
    kutu = kure_karo_bbox(z, x, y)
    if paketler is None:
        paketler = kurulu_paketler()
    adaylar = [(p, r) for p, r in paketler if _kesisir(tuple(p['bbox']), kutu)]
    if not adaylar:
        return None
    zemin = _zemin_oku(z, x, y)
    w, s, e, n = kutu
    vz = vektor_zoom(z, (s + n) / 2.0)
    S = KURE_TILE_PX * _SUPERSAMPLE
    sx = S / (e - w)
    sy = S / (n - s)
    tx0, ty0 = merc_karo(w, min(n, MERC_MAX_LAT), vz)
    tx1, ty1 = merc_karo(e - 1e-12, max(s, -MERC_MAX_LAT) + 1e-12, vz)
    tuval = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    bulunan = 0
    for mx in range(tx0, tx1 + 1):
        for my in range(ty0, ty1 + 1):
            veri = None
            for _p, r in adaylar:
                veri = r.karo(vz, mx, my)
                if veri:
                    break
            if not veri:
                continue
            bulunan += 1
            L = mvt_coz(veri, _CIZIM_KATMANLARI)
            # Bu MVT karosunun çıktı pikselindeki dikdörtgeni (komşularla ortak kenarlar
            # aynı fonksiyonla yuvarlanır: boşluk/örtüşme yok).
            lw, ln_ = merc_lonlat(vz, mx, my)
            le, ls = merc_lonlat(vz, mx + 1, my + 1)
            rx0 = max(0, int(round((lw - w) * sx)))
            rx1 = min(S, int(round((le - w) * sx)))
            ry0 = max(0, int(round((n - ln_) * sy)))
            ry1 = min(S, int(round((n - ls) * sy)))
            if rx1 <= rx0 or ry1 <= ry0:
                continue
            katman = Image.new('RGBA', (rx1 - rx0, ry1 - ry0), (0, 0, 0, 0))
            d = ImageDraw.Draw(katman, 'RGBA')
            _mvt_ciz(d, L, vz, mx, my, w, n, sx, sy, rx0, ry0, z, zemin_var=zemin is not None)
            tuval.alpha_composite(katman, dest=(rx0, ry0))
    if not bulunan and zemin is None:
        return None
    kucuk = tuval.convert('RGBa').resize((KURE_TILE_PX, KURE_TILE_PX), Image.LANCZOS).convert('RGBA')
    bio = io.BytesIO()
    if zemin is None:
        kucuk.save(bio, 'WEBP', lossless=True, quality=100, method=4, exact=False)
    else:
        zemin.alpha_composite(kucuk)
        if zemin.getchannel('A').getextrema() == (255, 255):
            zemin.convert('RGB').save(bio, 'WEBP', quality=82, method=4)
        else:
            zemin.save(bio, 'WEBP', quality=82, alpha_quality=100, method=4, exact=False)
    return bio.getvalue()


def onbellek_anahtari(z: int, x: int, y: int, paketler=None) -> Optional[str]:
    """Karonun önbellek anahtarı: stil sürümü + zemin sağlayıcı sürümü + karoyu kapsayan
    kurulu paketlerin BÜTÜN kurulu bileşen özetleri. Paket/bileşen kurulunca ya da
    silinince anahtar değişir (eski karo sunulmaz). Kapsayan paket yoksa None.
    """
    kutu = kure_karo_bbox(z, x, y)
    if paketler is None:
        paketler = kurulu_paketler()
    parcalar = []
    for p, _r in paketler:
        if not _kesisir(tuple(p['bbox']), kutu):
            continue
        for b in p['components']:
            if bilesen_kurulu_mu(b):
                parcalar.append('%s:%s:%s' % (p['id'], b['kind'], b['sha256']))
    if not parcalar:
        return None
    ham = '|'.join([STYLE_VERSION, zemin_kimligi()] + sorted(parcalar))
    return hashlib.sha256(ham.encode('utf-8')).hexdigest()[:24]


def _mvt_ciz(d, L, vz, mx, my, w, n, sx, sy, ox, oy, z, zemin_var=False):
    """Tek MVT karosunun öğelerini katman dikdörtgenine (ox, oy ofsetli) çizer.

    ``zemin_var``: altta görüntü zemini var; alan dolguları (arazi kullanımı, su, bina içi)
    atlanır, çizgiler aynı kalır (V307/FS-HARİTA-GÖRÜNTÜ; ölçüm: su dolgusu %59 opaklıkla
    denizi düz maviye boyuyordu). False iken çıktı önceki sürümle BİT-AYNIDIR.
    """
    nn = float(1 << vz)

    def donustur(parca, ext):
        out = []
        for px, py in parca:
            lon = (mx + px / ext) / nn * 360.0 - 180.0
            lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (my + py / ext) / nn))))
            out.append(((lon - w) * sx - ox, (n - lat) * sy - oy))
        return out
    o = _SUPERSAMPLE
    # 1) arazi kullanımı dolguları
    kat = L.get('landuse')
    if kat and not zemin_var:
        for gt, oz, parca in kat['features']:
            renk = _ARAZI.get(oz.get('kind'))
            if gt != 3 or renk is None:
                continue
            for p in parca:
                if len(p) > 2:
                    d.polygon(donustur(p, kat['extent']), fill=renk)
    # 2) su alanları + kıyı (çokgen kenarı; karo tamponundaki kenar dikdörtgen dışında kalır)
    kat = L.get('water')
    if kat:
        ext = kat['extent']
        for gt, oz, parca in kat['features']:
            if gt == 3:
                for p in parca:
                    if len(p) > 2:
                        pts = donustur(p, ext)
                        if not zemin_var:
                            d.polygon(pts, fill=_SU_ALAN)
                        d.line(pts, fill=_KIYI, width=_cizgi_genisligi(1.2, max(z, 12), o))
        for gt, oz, parca in kat['features']:
            if gt == 2:
                tur = oz.get('kind')
                taban = 2.6 if tur == 'river' else 1.4
                for p in parca:
                    if len(p) > 1:
                        d.line(donustur(p, ext), fill=_SU_CIZGI, width=_cizgi_genisligi(taban, z, o))
    # 3) binalar (z >= 13)
    kat = L.get('buildings')
    if kat and z >= 13:
        for gt, oz, parca in kat['features']:
            if gt != 3:
                continue
            for p in parca:
                if len(p) > 2:
                    d.polygon(donustur(p, kat['extent']), fill=None if zemin_var else _BINA_DOLGU,
                              outline=_BINA_KENAR)
    # 4) yollar (sınıf sırasıyla)
    kat = L.get('roads')
    if kat:
        ext = kat['extent']
        for tur, renk, taban, zmin in _YOL_STIL:
            if z < zmin:
                continue
            g = _cizgi_genisligi(taban, z, o)
            for gt, oz, parca in kat['features']:
                if gt != 2 or oz.get('kind') != tur:
                    continue
                for p in parca:
                    if len(p) > 1:
                        d.line(donustur(p, ext), fill=renk, width=g, joint='curve')
