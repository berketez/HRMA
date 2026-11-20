# -*- coding: utf-8 -*-
"""V307 / FS-HARİTA-GÖRÜNTÜ: harita paketlerinin GÖRÜNTÜ bileşenini okuyan saf Python modül.

Sorun (ölçüldü, FS-HARİTA-VERİ faz 1 RAPOR Bölüm 1): Fırlatma Sahası küresinde yakın
zoomda zemin dokusu ya ``bm_local`` z5 (~2 km/px; 20 km kamerada 120x, 2 km kamerada
1.201x büyütülmüş) ya da rızayla ``landsat_weld`` z11 (~31 m, 2000 yılı). Görüntü bileşeni
Copernicus Sentinel-2 L2A sahnelerinden HRMA'nın KENDİ ürettiği bulutsuz mozaiktir
(``tools/harita_goruntu_uret.py``; Berke kararı 16 Kas: hazır EOX mozaiği kullanılmaz).

Kap biçimi (faz 1 KARAR K5a): tek SQLite dosyası, iki tablo::

    metadata(name TEXT PRIMARY KEY, value TEXT)            -- WITHOUT ROWID
    tiles(z, x, y INTEGER, coverage INTEGER, data BLOB,    -- WITHOUT ROWID
          PRIMARY KEY (z, x, y))

* Izgara: HRMA küre karosu = GIBS EPSG:4326 ızgarası, açıklık ``288/2^z`` derece, sol üst
  (-180, +90), x doğuya, y güneye; geometrinin sahibi ``tile_cache`` (``tile_span_deg``,
  ``matrix_size``). Karo 512x512 WebP.
* Halka kuralı (şema /2, metadata ``detail``): z9..``full_zoom_max`` paket kutusunun
  tamamında; daha ince her düzey yalnız fırlatma noktasının (``center``) o düzeye ait
  yarıçapı içindeki karolarda (``karo_halkada_mi``). Halka dışında ince düzey istenirse
  okuyucu kaba düzeyin atasını verir (``karo_veya_ata``; büyütme çağıranın işi).
* ``coverage``: karonun ölçülmüş veri taşıyan piksel payı, 0..10000 (10000 = tam karo).
  Tam olmayan karoda veri olmayan pikseller SAYDAMDIR (alfa 0): bulut kalıntısı, Sentinel-2
  kapsamı dışı (açık deniz) ya da paket alanı dışı. Yapay doldurma yoktur.

Bu modül YALNIZ standart kitaplık + ``sqlite3`` kullanır (numpy/rasterio/Pillow YOK); paket
okunmadan önce bileşenin boyut + sha256 doğrulaması paket yöneticisinin işidir
(``map_packs.bilesen_kurulu_mu``). Buradaki kapılar ayrıca bozuk/şişirilmiş dosyaya karşı
fail-closed çalışır: her ihlal ADIYLA ``GoruntuHatasi(kod)``.

Zemin sağlayıcı bağlantı noktası (FS-HARİTA-VERİ faz 2 F2.4): ``saglayici(...)`` dönen
çağrılabilir ``fn(z, x, y) -> bytes | None`` ve ``fn.surum`` taşır; ana model
``map_packs.zemin_saglayici_kaydet(fn)`` ile bağlar (bu modül ``map_packs``'i İÇE AKTARMAZ).
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import struct
import threading
from typing import Callable, Dict, Iterable, List, NamedTuple, Optional, Tuple

from hrma.analysis import tile_cache

# ---------------------------------------------------------------------------
# 1) Sabitler (tek tanım; üretim aracı ``tools/harita_goruntu_uret.py`` buradan okur)
# ---------------------------------------------------------------------------
#: Kap şeması (metadata 'schema'); biçim değişirse sürüm artar, eski okuyucu reddeder.
#: /2 (18 Kas, GÖRÜNTÜ-HAFİF): zorunlu 'detail' (halka kuralı: düzeylerin kapladığı alan).
#: /1 dosyaları (bütün düzeyler paket kutusunun tamamında; hiç yayımlanmadı) adıyla
#: reddedilir (``bad_imagery_schema``).
SCHEMA = 'hrma.map_pack_imagery/2'
#: Izgara kimliği (metadata 'grid'): tile_cache ızgarası, 288/2^z açıklık, 512 px.
GRID_ID = 'hrma-globe-epsg4326-288-512'
#: Karo kenarı [px] — TEK tanım: ``map_packs.KURE_TILE_PX`` buradan ithal edilir
#: (HRMA küre ızgarası, GIBS EPSG:4326 düzeni; 3.0.7 birleşmesi).
TILE_PX = 512
#: Görüntü düzeyleri (HRMA seçimi, faz 1 RAPOR 3.1): z9 ~122 m/px … z13 ~7,6 m/px (ekvator,
#: enlem yönünde). z13, Sentinel-2'nin 10 m çözünürlüğünü bütün sahalarda karşılayan ilk düzey.
IMAGERY_ZOOM_MIN = 9
IMAGERY_ZOOM_MAX = 13
#: Okuyucunun kabul ettiği mutlak z aralığı (paket katmanının tavanı z15, Parça S
#: ``PACK_MAX_ZOOM``); dosyadaki zoom_min/zoom_max bunun içinde olmalı.
READER_MAX_ZOOM = 15
#: Tek karo baytı üst sınırı (``map_packs.MAX_TILE_BYTES`` ve zemin sağlayıcı sözleşmesi
#: ``≤ 4 MiB`` ile aynı değer).
MAX_TILE_BYTES = 4 * 1024 * 1024
#: Kap dosyası üst sınırı (GitHub release varlığı < 2 GiB; ``map_packs.MAX_PACK_BYTES``).
MAX_FILE_BYTES = 2 * 1024 ** 3 - 1
#: Metadata: en çok satır sayısı ve tek değer uzunluğu (sahne künyesi JSON'u dahil).
MAX_META_ROWS = 64
MAX_META_VALUE_CHARS = 256 * 1024
#: Bir sorguda SQLite sanal makinesinin en çok adım sayısı (bozuk/kötü niyetli dosyada
#: sonsuz tarama yerine adıyla ret). Ölçek: tek karo sorgusu ~10^2 adım.
MAX_VM_STEPS = 2_000_000
#: Bekçinin çağrılma aralığı (sanal makine komutu); küçük sorgular da en az bir kez sayılır.
_VM_ADIM_ARALIGI = 100
#: 1 derece enlem [km] (WGS84 ortalaması). TEK tanım: ``map_packs.daire_bbox`` paket
#: kutusunu, ``karo_halkada_mi`` halka sınırını bununla kurar (aynı ölçü).
KM_PER_DEG = 111.32
#: HALKA KURALI (HRMA seçimi; Berke 17 Kas: "o mozaikler aşırı detaylı olmasına gerek
#: yoktu"; brif 18 Kas GÖRÜNTÜ-HAFİF): z9..IMAGERY_FULL_ZOOM_MAX paket kutusunun TAMAMI
#: (~100 km yarıçap), daha ince düzeyler yalnız fırlatma noktasının (paket merkezi)
#: çevresinde: (düzey, yarıçap km). z11 ~31 m/px, z12 ~15 m/px, z13 ~7,6 m/px (enlem yönünde).
IMAGERY_FULL_ZOOM_MAX = 11
IMAGERY_RINGS = ((12, 50.0), (13, 25.0))
#: Yukarı örnekleme en çok kaç düzey: istenen düzeyin karosu yoksa (halka dışı ya da
#: zoom_max üstü) atadaki pencere büyütülür. Tavan: paket katmanının en ince düzeyi
#: (READER_MAX_ZOOM = 15) ile kutunun tamamını kaplayan düzey (z11) arasındaki fark; z15'te
#: z11 atasının 32 px'i.
MAX_UPSAMPLE_LEVELS = READER_MAX_ZOOM - IMAGERY_FULL_ZOOM_MAX
#: 'detail' halka yarıçapı kabul aralığı [km] ve halka sayısı tavanı (bozuk dosyaya kapı).
MAX_RING_KM = 1000.0
#: Kaynak sınıfları (künyede): Copernicus hukuki bildirimi, değiştirilmiş veri atfı.
ATTRIBUTION_TEMPLATE = 'Contains modified Copernicus Sentinel data {years}'
LICENSE_ID = 'Copernicus-Sentinel-Data-Legal-Notice'

#: Zorunlu metadata anahtarları ve doğrulayıcıları aşağıda (``_metadata_dogrula``).
REQUIRED_META = ('schema', 'grid', 'tile_px', 'format', 'zoom_min', 'zoom_max', 'bounds',
                 'pack_id', 'attribution', 'license', 'scenes', 'detail')
_PACK_ID_RE = re.compile(r'^[a-z0-9_]{1,40}$')
_SQLITE_MAGIC = b'SQLite format 3\x00'

# Tabloların BEKLENEN sütunları (PRAGMA table_info: ad, tür, notnull, pk sırası).
_TILES_COLUMNS = [('z', 'INTEGER', 1, 1), ('x', 'INTEGER', 1, 2), ('y', 'INTEGER', 1, 3),
                  ('coverage', 'INTEGER', 1, 0), ('data', 'BLOB', 1, 0)]
_META_COLUMNS = [('name', 'TEXT', 1, 1), ('value', 'TEXT', 1, 0)]
#: Kap DDL'i: üretim aracı bu metni aynen kullanır (tek tanım).
DDL = (
    'CREATE TABLE metadata (name TEXT NOT NULL PRIMARY KEY, value TEXT NOT NULL) '
    'WITHOUT ROWID',
    'CREATE TABLE tiles (z INTEGER NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL, '
    'coverage INTEGER NOT NULL, data BLOB NOT NULL, PRIMARY KEY (z, x, y)) WITHOUT ROWID',
)


class GoruntuHatasi(Exception):
    """Adlı hata; ``kod`` makine-okur (``bad_imagery_file``, ``bad_imagery_schema`` …)."""

    def __init__(self, kod: str, ayrinti: str = ''):
        super().__init__('%s: %s' % (kod, ayrinti) if ayrinti else kod)
        self.kod = kod
        self.ayrinti = ayrinti


# ---------------------------------------------------------------------------
# 2) WebP başlık denetimi (Pillow yok): imza + RIFF boyutu + tuval 512x512
# ---------------------------------------------------------------------------

def webp_boyutu(b: bytes) -> Tuple[int, int]:
    """WebP baytından (genişlik, yükseklik); biçim dışıysa ``GoruntuHatasi('bad_tile')``.

    Desteklenen ilk öbekler: ``VP8X`` (genişletilmiş; alfa taşıyan karolar), ``VP8 `` (kayıplı),
    ``VP8L`` (kayıpsız). RIFF boyutu dosya uzunluğuyla tutarlı olmalı (kesik/fazla bayt ret).
    """
    if not isinstance(b, (bytes, bytearray)) or len(b) < 30:
        raise GoruntuHatasi('bad_tile', 'too short')
    if b[0:4] != b'RIFF' or b[8:12] != b'WEBP':
        raise GoruntuHatasi('bad_tile', 'not webp')
    riff = struct.unpack_from('<I', b, 4)[0]
    if riff + 8 != len(b):
        raise GoruntuHatasi('bad_tile', 'riff size %d != %d' % (riff + 8, len(b)))
    ob = bytes(b[12:16])
    ob_boy = struct.unpack_from('<I', b, 16)[0]
    if 20 + ob_boy > len(b):
        raise GoruntuHatasi('bad_tile', 'chunk overflow')
    p = 20
    if ob == b'VP8X':
        if ob_boy < 10:
            raise GoruntuHatasi('bad_tile', 'vp8x')
        w = 1 + (b[p + 4] | (b[p + 5] << 8) | (b[p + 6] << 16))
        h = 1 + (b[p + 7] | (b[p + 8] << 8) | (b[p + 9] << 16))
        return w, h
    if ob == b'VP8 ':
        if ob_boy < 10 or b[p + 3:p + 6] != b'\x9d\x01\x2a':
            raise GoruntuHatasi('bad_tile', 'vp8')
        w = struct.unpack_from('<H', b, p + 6)[0] & 0x3FFF
        h = struct.unpack_from('<H', b, p + 8)[0] & 0x3FFF
        return w, h
    if ob == b'VP8L':
        if ob_boy < 5 or b[p] != 0x2F:
            raise GoruntuHatasi('bad_tile', 'vp8l')
        v = struct.unpack_from('<I', b, p + 1)[0]
        return 1 + (v & 0x3FFF), 1 + ((v >> 14) & 0x3FFF)
    raise GoruntuHatasi('bad_tile', 'chunk %r' % ob)


# ---------------------------------------------------------------------------
# 3) Okuyucu
# ---------------------------------------------------------------------------

class AtaKaro(NamedTuple):
    """``karo_veya_ata`` sonucu: kaynak karo + istenen karonun o karodaki pencere'si.

    ``pencere = (px0, py0, kenar)``: kaynak 512 px karoda istenen karoya düşen kare
    (piksel). ``dz == 0`` ise pencere tam karodur ve bayt doğrudan kullanılır.
    """
    veri: bytes
    z: int
    x: int
    y: int
    dz: int
    pencere: Tuple[int, int, int]
    coverage: int


def _int_mi(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _koordinat(z, x, y) -> Tuple[int, int, int]:
    if not (_int_mi(z) and _int_mi(x) and _int_mi(y)):
        raise GoruntuHatasi('bad_tile_coord', 'z/x/y must be int')
    return z, x, y


def _matriste(z: int, x: int, y: int) -> bool:
    if not (0 <= z <= READER_MAX_ZOOM):
        return False
    mw, mh = tile_cache.matrix_size(z)
    return 0 <= x < mw and 0 <= y < mh


def _bounds_coz(v: str) -> Tuple[float, float, float, float]:
    parca = v.split(',')
    if len(parca) != 4:
        raise GoruntuHatasi('bad_imagery_meta', 'bounds')
    try:
        w, s, e, n = (float(t) for t in parca)
    except ValueError:
        raise GoruntuHatasi('bad_imagery_meta', 'bounds') from None
    if not all(math.isfinite(t) for t in (w, s, e, n)) \
            or not (-180.0 <= w < e <= 180.0 and -90.0 <= s < n <= 90.0):
        raise GoruntuHatasi('bad_imagery_meta', 'bounds range')
    return w, s, e, n


def karo_halkada_mi(z: int, x: int, y: int, merkez_lat: float, merkez_lon: float,
                    yaricap_km: float) -> bool:
    """Karonun kutusu (``tile_cache``) merkezin ``yaricap_km`` çevresine değiyor mu.

    Ölçü paket kutusuyla aynıdır (``map_packs.daire_bbox``): yerel eşdikdörtgen, 1° enlem =
    ``KM_PER_DEG``, boylam farkı cos(merkez enlemi) ile ölçeklenir. Karonun merkeze en yakın
    noktası (kutuya kıstırılmış merkez) yarıçap içindeyse (sınır dahil) True. Üretim aracı
    (hangi karo pakete girer) ve okuyucu (hangi düzeyde karo vardır) AYNI işlevi kullanır.
    """
    w, s, e, n = tile_cache.tile_to_bbox(z, x, y)
    lon = min(max(merkez_lon, w), e)
    lat = min(max(merkez_lat, s), n)
    dx = (lon - merkez_lon) * KM_PER_DEG * math.cos(math.radians(merkez_lat))
    dy = (lat - merkez_lat) * KM_PER_DEG
    return dx * dx + dy * dy <= yaricap_km * yaricap_km


def piksel_metre(z: int) -> float:
    """z düzeyinde bir pikselin enlem yönündeki boyu [m]: açıklık / 512 x ``KM_PER_DEG``."""
    return tile_cache.tile_span_deg(z) / TILE_PX * KM_PER_DEG * 1000.0


def duzey_kurali_dogrula(d, zoom_min: int, zoom_max: int) -> dict:
    """Halka kuralını (``detail``) doğrular; ``{'full_zoom_max', 'rings'}`` normal biçimi döner.

    Biçim: ``{'full_zoom_max': int, 'rings': [{'zoom': int, 'radius_km': sayı}, ...]}``.
    Kurallar: ``zoom_min <= full_zoom_max <= zoom_max``; ``full_zoom_max+1 .. zoom_max``
    düzeylerinin HER BİRİ için tam bir halka, artan düzey sırasıyla; yarıçap sonlu,
    ``0 < r <= MAX_RING_KM`` ve düzey arttıkça ARTMAZ (ince halka kabanın içinde kalır).
    İhlal adıyla ``GoruntuHatasi('bad_imagery_meta', 'detail …')``.
    """
    def hata(ne):
        raise GoruntuHatasi('bad_imagery_meta', 'detail %s' % ne)
    if not isinstance(d, dict):
        hata('type')
    fz = d.get('full_zoom_max')
    if not _int_mi(fz) or not (zoom_min <= fz <= zoom_max):
        hata('full_zoom_max')
    halkalar = d.get('rings')
    if not isinstance(halkalar, list) or len(halkalar) != zoom_max - fz:
        hata('rings')
    out, onceki = [], None
    for i, h in enumerate(halkalar):
        if not isinstance(h, dict) or set(h) != {'zoom', 'radius_km'}:
            hata('ring')
        z, r = h['zoom'], h['radius_km']
        if not _int_mi(z) or z != fz + 1 + i:
            hata('ring zoom')
        if isinstance(r, bool) or not isinstance(r, (int, float)) or not math.isfinite(r) \
                or not (0.0 < r <= MAX_RING_KM) or (onceki is not None and r > onceki):
            hata('ring radius')
        onceki = float(r)
        out.append({'zoom': z, 'radius_km': float(r)})
    return {'full_zoom_max': fz, 'rings': out}


def _detail_coz(v: str, zmin: int, zmax: int, bounds) -> dict:
    try:
        d = json.loads(v)
    except ValueError:
        raise GoruntuHatasi('bad_imagery_meta', 'detail json') from None
    if not isinstance(d, dict) or set(d) != {'center', 'full_zoom_max', 'rings'}:
        raise GoruntuHatasi('bad_imagery_meta', 'detail keys')
    kural = duzey_kurali_dogrula({k: d[k] for k in ('full_zoom_max', 'rings')}, zmin, zmax)
    c = d['center']
    if not isinstance(c, list) or len(c) != 2 or not all(
            isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in c):
        raise GoruntuHatasi('bad_imagery_meta', 'detail center')
    lat, lon = float(c[0]), float(c[1])
    w, s, e, n = bounds
    if not (w <= lon <= e and s <= lat <= n):
        raise GoruntuHatasi('bad_imagery_meta', 'detail center outside bounds')
    kural['center'] = (lat, lon)
    kural['ring_km'] = {h['zoom']: h['radius_km'] for h in kural['rings']}
    return kural


def _metadata_dogrula(meta: Dict[str, str]) -> dict:
    # Şema ÖNCE: başka sürümün dosyası (ör. /1, 'detail' yok) eksik alan değil şema reddidir.
    if 'schema' in meta and meta['schema'] != SCHEMA:
        raise GoruntuHatasi('bad_imagery_schema', meta['schema'][:80])
    eksik = [k for k in REQUIRED_META if k not in meta]
    if eksik:
        raise GoruntuHatasi('bad_imagery_meta', 'missing %s' % ','.join(eksik))
    if meta['grid'] != GRID_ID:
        raise GoruntuHatasi('bad_imagery_meta', 'grid')
    if meta['tile_px'] != str(TILE_PX):
        raise GoruntuHatasi('bad_imagery_meta', 'tile_px')
    if meta['format'] != 'webp':
        raise GoruntuHatasi('bad_imagery_meta', 'format')
    try:
        zmin, zmax = int(meta['zoom_min']), int(meta['zoom_max'])
    except ValueError:
        raise GoruntuHatasi('bad_imagery_meta', 'zoom') from None
    if not (0 <= zmin <= zmax <= READER_MAX_ZOOM):
        raise GoruntuHatasi('bad_imagery_meta', 'zoom range')
    if not _PACK_ID_RE.match(meta['pack_id']):
        raise GoruntuHatasi('bad_imagery_meta', 'pack_id')
    for k in ('attribution', 'license'):
        if not (0 < len(meta[k]) <= 400):
            raise GoruntuHatasi('bad_imagery_meta', k)
    try:
        sahneler = json.loads(meta['scenes'])
    except ValueError:
        raise GoruntuHatasi('bad_imagery_meta', 'scenes json') from None
    if not isinstance(sahneler, list) or not sahneler \
            or not all(isinstance(s, dict) and isinstance(s.get('id'), str)
                       and isinstance(s.get('datetime'), str) for s in sahneler):
        raise GoruntuHatasi('bad_imagery_meta', 'scenes')
    bounds = _bounds_coz(meta['bounds'])
    return {'zoom_min': zmin, 'zoom_max': zmax, 'bounds': bounds,
            'pack_id': meta['pack_id'], 'attribution': meta['attribution'],
            'license': meta['license'], 'scenes': sahneler,
            'detail': _detail_coz(meta['detail'], zmin, zmax, bounds)}


class GoruntuOkuyucu:
    """Bir görüntü bileşeni dosyasını salt-okur açar ve karoları verir.

    Açılışta: boyut tavanı, SQLite imzası, şema nesneleri (yalnız iki tablo; görünüm,
    tetikleyici, ek tablo ret), sütun tanımları, metadata doğrulaması. Bağlantı
    ``mode=ro&immutable=1`` + ``trusted_schema=OFF`` + ``query_only=ON`` + sanal makine
    adım tavanı ile açılır. Karo okuma iş parçacığı güvenlidir (tek bağlantı + kilit).
    """

    def __init__(self, yol: str):
        self.yol = yol
        try:
            st = os.stat(yol)
        except OSError as e:
            raise GoruntuHatasi('imagery_missing', type(e).__name__) from None
        if not os.path.isfile(yol):
            raise GoruntuHatasi('imagery_missing', 'not a file')
        if st.st_size > MAX_FILE_BYTES:
            raise GoruntuHatasi('imagery_too_large', str(st.st_size))
        try:
            with open(yol, 'rb') as fh:
                bas = fh.read(len(_SQLITE_MAGIC))
        except OSError as e:
            raise GoruntuHatasi('bad_imagery_file', type(e).__name__) from None
        if bas != _SQLITE_MAGIC:
            raise GoruntuHatasi('bad_imagery_file', 'not sqlite')
        self._kilit = threading.Lock()
        self._adim = [0]
        self._db = None
        try:
            self._db = self._ac(yol)
            self._sema_dogrula()
            self.bilgi = self._metadata_oku()
        except sqlite3.Error as e:
            self.kapat()
            raise GoruntuHatasi('bad_imagery_file', type(e).__name__) from None
        except GoruntuHatasi:
            self.kapat()
            raise

    # -- bağlantı ----------------------------------------------------------
    def _ac(self, yol: str) -> sqlite3.Connection:
        from urllib.parse import quote
        uri = 'file:%s?mode=ro&immutable=1' % quote(os.path.abspath(yol))
        db = sqlite3.connect(uri, uri=True, check_same_thread=False, isolation_level=None)
        if hasattr(db, 'setlimit'):              # Python 3.11+: blob/dize tavanı
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_TILE_BYTES + 1024)
            db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 4096)
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA query_only=ON')
        adim = self._adim

        def bekci():
            adim[0] += _VM_ADIM_ARALIGI
            return 1 if adim[0] > MAX_VM_STEPS else 0
        # Sayaç her sorgudan önce sıfırlanır (``_sorgu``).
        db.set_progress_handler(bekci, _VM_ADIM_ARALIGI)
        return db

    def _sorgu(self, sql: str, args: tuple = ()) -> list:
        db = self._db
        if db is None:
            raise GoruntuHatasi('imagery_closed')
        self._adim[0] = 0
        try:
            return db.execute(sql, args).fetchall()
        except sqlite3.OperationalError as e:
            if 'interrupted' in str(e):
                raise GoruntuHatasi('imagery_query_limit') from None
            raise GoruntuHatasi('bad_imagery_file', type(e).__name__) from None
        except sqlite3.Error as e:
            # Tavanı aşan blob/dize (SQLITE_TOOBIG), bozuk sayfa (DatabaseError) …
            raise GoruntuHatasi('bad_imagery_file', type(e).__name__) from None

    def kapat(self) -> None:
        db, self._db = self._db, None
        if db is not None:
            try:
                db.close()
            except sqlite3.Error:
                pass

    # -- doğrulama ---------------------------------------------------------
    def _sema_dogrula(self) -> None:
        nesneler = self._sorgu('SELECT type, name FROM sqlite_master')
        beklenen = {('table', 'metadata'), ('table', 'tiles')}
        bulunan = set((t, n) for t, n in nesneler)
        if bulunan != beklenen or len(nesneler) != 2:
            raise GoruntuHatasi('bad_imagery_schema', 'objects %r' % sorted(bulunan)[:6])
        for tablo, beklenen_sutun in (('tiles', _TILES_COLUMNS), ('metadata', _META_COLUMNS)):
            sutun = [(r[1], (r[2] or '').upper(), int(r[3]), int(r[5]))
                     for r in self._sorgu('PRAGMA table_info(%s)' % tablo)]
            if sutun != beklenen_sutun:
                raise GoruntuHatasi('bad_imagery_schema', 'columns %s' % tablo)

    def _metadata_oku(self) -> dict:
        satir = self._sorgu('SELECT count(*), max(length(name)), max(length(value)) FROM metadata')
        adet, ad_boy, deger_boy = satir[0]
        if adet > MAX_META_ROWS or (ad_boy or 0) > 64 or (deger_boy or 0) > MAX_META_VALUE_CHARS:
            raise GoruntuHatasi('bad_imagery_meta', 'size')
        meta = {}
        for ad, deger in self._sorgu('SELECT name, value FROM metadata'):
            if not isinstance(ad, str) or not isinstance(deger, str):
                raise GoruntuHatasi('bad_imagery_meta', 'types')
            meta[ad] = deger
        return _metadata_dogrula(meta)

    # -- karo --------------------------------------------------------------
    def karo_bilgisi(self, z, x, y) -> Optional[Tuple[int, int]]:
        """(coverage 0..10000, bayt) ya da karo yoksa None."""
        z, x, y = _koordinat(z, x, y)
        if not _matriste(z, x, y) or not (self.bilgi['zoom_min'] <= z <= self.bilgi['zoom_max']):
            return None
        with self._kilit:
            r = self._sorgu('SELECT coverage, length(data), typeof(data) FROM tiles '
                            'WHERE z=? AND x=? AND y=?', (z, x, y))
        if not r:
            return None
        cov, boy, tur = r[0]
        if tur != 'blob' or not _int_mi(cov) or not (0 < cov <= 10000):
            raise GoruntuHatasi('bad_tile', 'row')
        if boy > MAX_TILE_BYTES:
            raise GoruntuHatasi('tile_too_large', str(boy))
        return cov, boy

    def karo(self, z, x, y) -> Optional[bytes]:
        """512x512 WebP baytı ya da karo yoksa (kapsam dışı / düzey dışı) None."""
        r = self._karo_satir(z, x, y)
        return None if r is None else r[1]

    def _karo_satir(self, z, x, y) -> Optional[Tuple[int, bytes]]:
        if self.karo_bilgisi(z, x, y) is None:
            return None
        with self._kilit:
            r = self._sorgu('SELECT coverage, data FROM tiles WHERE z=? AND x=? AND y=?',
                            (z, x, y))
        if not r:
            return None
        cov, veri = r[0]
        veri = bytes(veri)
        if len(veri) > MAX_TILE_BYTES:
            raise GoruntuHatasi('tile_too_large', str(len(veri)))
        if webp_boyutu(veri) != (TILE_PX, TILE_PX):
            raise GoruntuHatasi('bad_tile', 'size')
        return cov, veri

    def duzeyde_mi(self, z: int, x: int, y: int) -> bool:
        """(z, x, y) karosu dosyanın z düzeyindeki ALANINDA mı (halka kuralı; veri olup
        olmadığından bağımsız). ``z <= full_zoom_max``: paket kutusu; daha ince düzey: o
        düzeyin halkası (``karo_halkada_mi``, üretim aracıyla aynı işlev)."""
        d = self.bilgi['detail']
        if z <= d['full_zoom_max']:
            return self.kapsar_mi(z, x, y)
        r = d['ring_km'].get(z)
        return r is not None and karo_halkada_mi(z, x, y, d['center'][0], d['center'][1], r)

    def kaynak_duzeyi(self, z: int, x: int, y: int) -> Optional[int]:
        """İstenen karonun verisinin okunacağı düzey: ``min(z, zoom_max)``'tan aşağı, karonun
        atasının o düzeyin alanında olduğu İLK düzey. Paket kutusu dışında / ``zoom_min``
        altında None. Halka dışında daha ince düzey istenirse kaba halkanın (ya da kutunun)
        düzeyi döner: zemin halkadan halkaya BOŞLUKSUZ geçer (aynı mozaiğin kaba düzeyi)."""
        zmin, zmax = self.bilgi['zoom_min'], self.bilgi['zoom_max']
        if z < zmin or not self.kapsar_mi(z, x, y):
            return None
        L = min(z, zmax)
        while L > zmin and not self.duzeyde_mi(L, x >> (z - L), y >> (z - L)):
            L -= 1
        return L

    def karo_veya_ata(self, z, x, y, en_fazla: int = MAX_UPSAMPLE_LEVELS) -> Optional[AtaKaro]:
        """Karo kendi düzeyinde varsa kendisi (dz=0); yoksa ``kaynak_duzeyi`` atasındaki pencere.

        Ata iki durumda kullanılır: ``z > zoom_max`` (en ince düzeyin üstü) ve karo kendi
        düzeyinin HALKASI dışında (halka kuralı; ör. z13 istenir, karo 25 km halkası dışında:
        z12 ya da z11 atası). En çok ``en_fazla`` (≤ ``MAX_UPSAMPLE_LEVELS``) düzey yukarı;
        pencereyi büyütmek çağıranın işidir (bu modül görüntü çözmez). Kaynak düzeyde karo
        yoksa (veri yok: bulut kalıntısı, açık deniz) None — daha kaba düzeye inilmez.
        """
        z, x, y = _koordinat(z, x, y)
        if not _int_mi(en_fazla) or not (0 <= en_fazla <= MAX_UPSAMPLE_LEVELS):
            raise GoruntuHatasi('bad_upsample_levels')
        if not _matriste(z, x, y):
            return None
        L = self.kaynak_duzeyi(z, x, y)
        if L is None:
            return None
        dz = z - L
        if dz > en_fazla:
            return None
        ax, ay = x >> dz, y >> dz
        r = self._karo_satir(L, ax, ay)
        if r is None:
            return None
        kenar = TILE_PX >> dz
        return AtaKaro(r[1], L, ax, ay, dz,
                       ((x - (ax << dz)) * kenar, (y - (ay << dz)) * kenar, kenar), r[0])

    def kapsar_mi(self, z: int, x: int, y: int) -> bool:
        """Karonun kutusu görüntü alanı (bounds) ile kesişiyor mu (veri olup olmadığından bağımsız)."""
        w, s, e, n = tile_cache.tile_to_bbox(z, x, y)
        bw, bs, be, bn = self.bilgi['bounds']
        return w < be and bw < e and s < bn and bs < n


# ---------------------------------------------------------------------------
# 4) Zemin sağlayıcı (map_packs.zemin_saglayici_kaydet sözleşmesi)
# ---------------------------------------------------------------------------
#: Sağlayıcı biçim sürümü (önbellek anahtarına girer; davranış değişirse artar).
#: img2 (18 Kas): halka kuralı — halka dışında kaba düzeyin atası büyütülür; birden çok
#: dosyada en ince tam karo seçilir.
PROVIDER_VERSION = 'img2'

_okuyucular: Dict[str, Tuple[tuple, GoruntuOkuyucu]] = {}
_okuyucu_kilidi = threading.Lock()


def okuyucu(yol: str, sha256: str) -> GoruntuOkuyucu:
    """Yol + doğrulanmış sha256 için önbellekli okuyucu (dosya değişirse yeniden açılır)."""
    try:
        st = os.stat(yol)
    except OSError as e:
        raise GoruntuHatasi('imagery_missing', type(e).__name__) from None
    imza = (st.st_size, st.st_mtime_ns, sha256)
    # Kurulum kilit İÇİNDE: iki iş parçacığı aynı dosya için aynı anda okuyucu kurup
    # birbirinin bağlantısını kapatmasın (açılış küçük bir okuma; kilit kısa sürer).
    with _okuyucu_kilidi:
        kayit = _okuyucular.get(yol)
        if kayit is not None and kayit[0] == imza:
            return kayit[1]
        yeni = GoruntuOkuyucu(yol)
        _okuyucular[yol] = (imza, yeni)
    if kayit is not None:
        kayit[1].kapat()
    return yeni


def okuyuculari_birak(yol: Optional[str] = None) -> None:
    """Paket silinirken/yeniden kurulurken açık bağlantıyı kapatır (None: hepsi)."""
    with _okuyucu_kilidi:
        anahtarlar = list(_okuyucular) if yol is None else [yol]
        kayitlar = [_okuyucular.pop(k, None) for k in anahtarlar]
    for k in kayitlar:
        if k is not None:
            k[1].kapat()


def saglayici(kaynaklar: Callable[[], Iterable[Tuple[str, str]]], *,
              kismi_karo: bool = False,
              buyutucu: Optional[Callable[[AtaKaro], bytes]] = None):
    """``map_packs.zemin_saglayici_kaydet`` için zemin sağlayıcısı kurar.

    ``kaynaklar()``: kurulu ve sha256'sı DOĞRULANMIŞ görüntü bileşenlerinin
    ``(yol, sha256)`` listesi (paket yöneticisinden; inmekte olan dosya listede olmaz).
    Dönüş ``fn(z, x, y) -> bytes | None`` (``fn.surum`` taşır):

    * Karoyu kapsayan dosyaların hepsi ``(yol)`` sırasıyla denenir (belirlenimci). TAM karo
      (coverage 10000) verenler arasında en ince kaynak düzeyli olan (en küçük ``dz``;
      eşitlikte yol sırası) seçilir: üst üste binen iki pakette (KSC ⟷ Cape Canaveral)
      birinin halkası dışında ötekinin ince düzeyi kullanılır.
    * ``kismi_karo=False`` (varsayılan): tam olmayan karo VERİLMEZ (None). Gerekçe: bugünkü
      çizici zemini opak RGB'ye çevirir (``convert('RGB')``); saydam (veri yok) pikseller
      siyah/rastgele renge dönerdi = sahte doku. Çizici alfayı korumaya geçince True yapılır.
      Tam karo yoksa kısmi karolar arasında yine en ince kaynak düzeyli olan verilir.
    * Karo kendi düzeyinde yoksa (``z > zoom_max`` ya da halka dışı) ``buyutucu``
      verilmişse atadaki pencere ona verilir (çağıran Pillow ile kırpıp 512 px'e büyütür);
      verilmemişse None.
    """
    if not callable(kaynaklar):
        raise GoruntuHatasi('bad_provider_sources')
    if buyutucu is not None and not callable(buyutucu):
        raise GoruntuHatasi('bad_provider_upsampler')
    surum = '%s-k%d-b%d' % (PROVIDER_VERSION, 1 if kismi_karo else 0, 1 if buyutucu else 0)

    def fn(z, x, y) -> Optional[bytes]:
        z, x, y = _koordinat(z, x, y)
        if not _matriste(z, x, y):
            return None
        adaylar = sorted(kaynaklar())
        tam = kismi = None
        for yol, sha in adaylar:
            ok = okuyucu(yol, sha)
            if not ok.kapsar_mi(z, x, y):
                continue
            ata = ok.karo_veya_ata(z, x, y, MAX_UPSAMPLE_LEVELS if buyutucu else 0)
            if ata is None:
                continue
            if ata.coverage >= 10000:
                if tam is None or ata.dz < tam.dz:
                    tam = ata
                if ata.dz == 0:
                    break                                # daha incesi olamaz
            elif kismi_karo and (kismi is None or ata.dz < kismi.dz):
                kismi = ata
        sec = tam if tam is not None else kismi
        if sec is None:
            return None
        return sec.veri if sec.dz == 0 else buyutucu(sec)    # type: ignore[misc]

    fn.surum = surum                             # type: ignore[attr-defined]
    return fn


def kunye(yol: str) -> dict:
    """Dosyanın künyesi (pack_id, zoom, bounds, atıf, lisans, sahneler) — panel/rapor için."""
    ok = GoruntuOkuyucu(yol)
    try:
        b = dict(ok.bilgi)
        b['bounds'] = list(b['bounds'])
        d = b['detail']
        b['detail'] = {'center': list(d['center']), 'full_zoom_max': d['full_zoom_max'],
                       'rings': [dict(h) for h in d['rings']]}
        return b
    finally:
        ok.kapat()


__all__ = ['SCHEMA', 'GRID_ID', 'TILE_PX', 'IMAGERY_ZOOM_MIN', 'IMAGERY_ZOOM_MAX',
           'IMAGERY_FULL_ZOOM_MAX', 'IMAGERY_RINGS', 'KM_PER_DEG', 'MAX_UPSAMPLE_LEVELS',
           'MAX_TILE_BYTES', 'MAX_FILE_BYTES', 'DDL', 'GoruntuHatasi', 'GoruntuOkuyucu',
           'AtaKaro', 'webp_boyutu', 'okuyucu', 'okuyuculari_birak', 'saglayici', 'kunye',
           'karo_halkada_mi', 'piksel_metre', 'duzey_kurali_dogrula',
           'ATTRIBUTION_TEMPLATE', 'LICENSE_ID', 'PROVIDER_VERSION']
