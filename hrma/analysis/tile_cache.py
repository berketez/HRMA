# -*- coding: utf-8 -*-
"""
NASA GIBS WMTS uydu karo (tile) getirici + kalıcı disk önbelleği.

Bu modül fırlatma sahası 3B küresinin yakın-zoom uydu dokusunu besler.
Küre TABANI paketle gelen tek Blue Marble dokusudur (~9 km/hücre); kullanıcı
bir sahaya yakınlaştığında (kamera rakımı < ~400 km) ön yüz her karonun kendi
yamasına yüksek çözünürlüklü GIBS karolarını bindirir. Karolar GIBS'ten TEK
SEFER çekilir, kalıcı kullanıcı-veri dizinine yazılır; sonraki açılışlarda
çevrimdışı gösterilir.

Kaynak: NASA GIBS (Global Imagery Browse Services), EPSG:4326 (CRS84, lon/lat
WGS84), anahtarsız, kamu malı. WMTS RESTful uç.

Doğrulama (canlı, 2026-07-24):
  * Katman `BlueMarble_ShadedRelief_Bathymetry`: Format=image/jpeg,
    TileMatrixSet=500m, Dimension YOK (statik), z0-z7 — WMTSCapabilities.xml.
  * Canlı HTTP 200 image/jpeg: z0/0/0, z3/2/4, z7/57/159 (Mahia 177.86°E).
  * URL segment sırası WMTS = z/y/x (TileMatrix/TileRow/TileCol), OSM'nin
    z/x/y'si DEĞİL. Kilit kanıtı: z7 (MW=160, MH=80) için 7/79/159 → HTTP 200
    ama takas 7/159/79 → HTTP 400 (TileRow=159 > MatrixHeight=80). Sıra TEK
    yerde (_gibs_url) kilitli.

DÜRÜSTLÜK: çevrimdışı ya da GIBS ulaşılamazken SAHTE doku ÜRETİLMEZ — ilgili
karo yamaya EKLENMEZ, taban Blue Marble o hücrede kalır (kısmi yükleme OK).

GÜVENLİK:
  * Çıkış hostu SABİT (GIBS_HOST) — istemciden URL gelmez, SSRF yok.
  * layer_key allowlist sözlük anahtarıdır (^[a-z0-9_]+$); bilinmeyen → 404.
  * date yalnız ^\\d{4}-\\d{2}-\\d{2}$ (zaman katmanı) ya da 'default'.
  * z/x/y int ve matris aralığında; disk yolu realpath(root) önekiyle
    doğrulanır (path traversal engellenir) → aksi 403.
  * Cache TILE_CACHE_MAX_BYTES (varsayılan 400 MB) cap + LRU (mtime).
"""

import math
import os
import re
import tempfile
import threading
import time
from typing import Dict, Optional, Tuple

from hrma.data.offline_store import _user_data_dir

# ---------------------------------------------------------------------------
# 1) Sabitler / güvenlik allowlist
# ---------------------------------------------------------------------------

# Çıkış hostu SABİT (SSRF koruması) — istemci hiçbir zaman URL/host göndermez.
GIBS_HOST = 'gibs.earthdata.nasa.gov'
GIBS_BASE = 'https://%s/wmts/epsg4326/best' % GIBS_HOST

_HTTP_UA = 'HRMA/2.6 (rocket motor analysis; offline-first launch site tool)'
HTTP_TIMEOUT_S = 8.0

# Katman allowlist. Anahtar (layer_key) HEM URL HEM disk yolunda kullanılır →
# ^[a-z0-9_]+$ ile sınırlı, sabit sözlük anahtarı (kullanıcı girdisi değil).
#   wmts      : GIBS resmi katman kimliği (WMTSCapabilities.xml ile teyitli)
#   tms       : TileMatrixSet kimliği (500m / 250m)
#   time      : Dimension:Time gerektirir mi (tarihli katman)
#   max_zoom  : izin verilen en yüksek z (500m z0-7, 250m z0-8)
#   ext       : dosya uzantısı / MIME türetimi
#   attribution: ön yüzün göstereceği kaynak metni
LAYERS: Dict[str, dict] = {
    'bluemarble': {
        'wmts': 'BlueMarble_ShadedRelief_Bathymetry',
        'tms': '500m',
        'time': False,
        'max_zoom': 7,
        'ext': 'jpg',
        'attribution': 'NASA GIBS — Blue Marble Shaded Relief + Bathymetry (~500 m)',
    },
    'viirs': {
        # OPSİYONEL: 250 m gerçek renk, TARİHLİ (Dimension:Time zorunlu),
        # bulut riski taşır → varsayılan DEĞİL, ön yüz dürüstlük uyarısıyla sunar.
        'wmts': 'VIIRS_SNPP_CorrectedReflectance_TrueColor',
        'tms': '250m',
        'time': True,
        'max_zoom': 8,
        'ext': 'jpg',
        'attribution': 'NASA GIBS — VIIRS SNPP True Color (~250 m, tarihli, bulut riski)',
    },
}
DEFAULT_TILE_LAYER = 'bluemarble'

_LAYER_KEY_RE = re.compile(r'^[a-z0-9_]+$')
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

_EXT_MIME = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png'}
_IMAGE_EXTS = ('.jpg', '.jpeg', '.png')

# ---------------------------------------------------------------------------
# 2) Cache boyutu / eşzamanlılık
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# Varsayılan 400 MB; HRMA_TILE_CACHE_MAX_BYTES ile değiştirilebilir.
TILE_CACHE_MAX_BYTES = _env_int('HRMA_TILE_CACHE_MAX_BYTES', 400 * 1024 * 1024)
# Cap aşıldığında LRU süpürme bu orana (düşük su) kadar iner.
_LRU_LOW_WATER = 0.80

# Disk yazımı + LRU süpürme serileştirilir (çoklu eşzamanlı istek).
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 3) WMTS EPSG:4326 karo matris geometrisi (GIBS "500m"/"250m" TileMatrixSet)
# ---------------------------------------------------------------------------
# deg/px = 0.5625/2^z (512 px karo), tileSpan(°) = 288/2^z.
# MatrixWidth  = ceil(360/tileSpan), MatrixHeight = ceil(180/tileSpan).
# (z0-2 düzensiz yuvarlanır ama ceil formülü hepsini doğru verir; teyit:
#  z0 2x1, z3 10x5, z7 160x80 — WMTSCapabilities.xml ile birebir.)

def tile_span_deg(z: int) -> float:
    """Bir karonun kapladığı derece (lon ve lat aynı, kareseldir)."""
    return 288.0 / float(1 << int(z))


def matrix_size(z: int) -> Tuple[int, int]:
    """(MatrixWidth, MatrixHeight) = (x sütun sayısı, y satır sayısı).

    Tamsayı ceil bölme ile float sapması olmadan hesaplanır.
    """
    p = 1 << int(z)                       # 2^z
    mw = -(-(360 * p) // 288)             # ceil(360*2^z / 288)
    mh = -(-(180 * p) // 288)             # ceil(180*2^z / 288)
    return int(mw), int(mh)


def tile_to_bbox(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """Karo -> (lonW, latS, lonE, latN) derece kutusu.

    TopLeftCorner=(-180,+90); x doğuya, y güneye artar.
    """
    span = tile_span_deg(z)
    lon_w = -180.0 + x * span
    lat_n = 90.0 - y * span
    return (lon_w, lat_n - span, lon_w + span, lat_n)


def lonlat_to_tile(z: int, lon_deg: float, lat_deg: float) -> Tuple[int, int]:
    """(lon,lat) -> (tx, ty). x tarih çizgisinde sarmalanır, y kutupta kırpılır."""
    span = tile_span_deg(z)
    mw, mh = matrix_size(z)
    tx = int(math.floor((lon_deg + 180.0) / span))
    ty = int(math.floor((90.0 - lat_deg) / span))
    tx = ((tx % mw) + mw) % mw            # tarih çizgisi (Mahia 177.86°E)
    ty = min(max(ty, 0), mh - 1)          # kutup kırpma (singularity yok)
    return tx, ty


def _in_range(z: int, x: int, y: int, max_zoom: int) -> bool:
    if z < 0 or z > max_zoom:
        return False
    mw, mh = matrix_size(z)
    return 0 <= x < mw and 0 <= y < mh


# ---------------------------------------------------------------------------
# 4) GIBS URL kurucu — z/y/x sırası TEK yerde kilitli
# ---------------------------------------------------------------------------

def _gibs_url(cfg: dict, z: int, x: int, y: int, date_seg: str) -> str:
    """WMTS RESTful karo URL'i.

    Statik : {base}/{layer}/default/{tms}/{z}/{y}/{x}.{ext}
    Tarihli: {base}/{layer}/default/{date}/{tms}/{z}/{y}/{x}.{ext}

    ⚠️ Segment sırası z / y / x = TileMatrix / TileRow / TileCol.
       Satır (y) sütundan (x) ÖNCE gelir — OSM'nin z/x/y'si DEĞİL.
       (Kanıt: z7 7/79/159→200, takas 7/159/79→400.)
    """
    if cfg['time']:
        style = 'default/%s' % date_seg
    else:
        style = 'default'
    return '%s/%s/%s/%s/%d/%d/%d.%s' % (
        GIBS_BASE, cfg['wmts'], style, cfg['tms'], z, y, x, cfg['ext'])


# ---------------------------------------------------------------------------
# 5) İkili HTTP getirici (_http_json'un ikili ikizi) — hata → None
# ---------------------------------------------------------------------------

def _http_bytes(url: str, timeout: float = HTTP_TIMEOUT_S) -> Optional[bytes]:
    """Kısa zaman aşımlı ikili GET; HER hata None döner (asla yükseltmez).

    launch_site._http_json'un ikili ikizidir; aynı UA. Yalnız HTTP 200 +
    Content-Type image/* döndüğünde bayt döner; aksi (GIBS hata XML'i dahil)
    None → çağıran sahte doku üretmez, karoyu atlar.
    """
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={'User-Agent': _HTTP_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, 'status', 200) != 200:
                return None
            ctype = (resp.headers.get('Content-Type') or '').lower()
            if not ctype.startswith('image/'):
                return None                # GIBS hata cevabı text/xml → yut
            data = resp.read()
            return data if data else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 6) Cache dizini + disk yolu (path traversal kapısı)
# ---------------------------------------------------------------------------

def tiles_root() -> str:
    """Karo önbellek kök dizini (yoksa oluşturulur).

    offline_store._user_data_dir() + 'tiles' (macOS
    ~/Library/Application Support/HRMA/tiles, Win %APPDATA%/HRMA/tiles).
    HRMA_TILE_CACHE_DIR ile değiştirilebilir. NOT: Belgeler/HRMA DEĞİL —
    orası .hrma proje dosyalarına ayrılmıştır (utils/projects.py).
    """
    override = os.environ.get('HRMA_TILE_CACHE_DIR')
    root = override if override else os.path.join(_user_data_dir(), 'tiles')
    os.makedirs(root, exist_ok=True)
    return root


def _tile_path(root: str, layer_key: str, date_seg: str,
               z: int, x: int, y: int, ext: str) -> Optional[str]:
    """Disk yolu tiles/<layer>/<date|default>/<z>/<x>/<y>.<ext>.

    Tüm bileşenler daha önce doğrulandığı için traversal zaten imkânsız; yine
    de savunma-derinliği olarak realpath(path) realpath(root) önekiyle
    doğrulanır. Önek dışında ise None (403).
    """
    rel = os.path.join(layer_key, date_seg, str(z), str(x), '%d.%s' % (y, ext))
    path = os.path.join(root, rel)
    root_real = os.path.realpath(root)
    path_real = os.path.realpath(path)
    if path_real != root_real and not path_real.startswith(root_real + os.sep):
        return None
    return path


# ---------------------------------------------------------------------------
# 7) LRU / boyut yönetimi
# ---------------------------------------------------------------------------

def _iter_tiles(root: str):
    """(mtime, size, path) üreteci — yalnız resim uzantıları."""
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if not f.lower().endswith(_IMAGE_EXTS):
                continue
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            yield st.st_mtime, st.st_size, p


def _cache_usage(root: Optional[str] = None) -> Tuple[int, int]:
    """(toplam_bayt, karo_sayısı)."""
    root = root or tiles_root()
    total = 0
    count = 0
    for _mtime, size, _p in _iter_tiles(root):
        total += size
        count += 1
    return total, count


def _enforce_cap(root: str) -> None:
    """Cap aşıldıysa en eski (mtime) karolardan başlayarak düşük-suya süpür.

    _lock altında çağrılmalı.
    """
    total, _ = _cache_usage(root)
    if total <= TILE_CACHE_MAX_BYTES:
        return
    target = int(TILE_CACHE_MAX_BYTES * _LRU_LOW_WATER)
    entries = sorted(_iter_tiles(root))    # en eski (küçük mtime) önce
    for _mtime, size, p in entries:
        if total <= target:
            break
        try:
            os.remove(p)
            total -= size
        except OSError:
            pass


def cache_status() -> dict:
    """{bytes, tiles, dir, max_bytes} — /api/tile/cache/status için."""
    root = tiles_root()
    total, count = _cache_usage(root)
    return {
        'bytes': int(total),
        'tiles': int(count),
        'dir': root,
        'max_bytes': int(TILE_CACHE_MAX_BYTES),
    }


def cache_clear() -> dict:
    """Tüm karoları sil + boş dizinleri temizle — /api/tile/cache/clear için."""
    root = tiles_root()
    removed = 0
    with _lock:
        for _mtime, _size, p in list(_iter_tiles(root)):
            try:
                os.remove(p)
                removed += 1
            except OSError:
                pass
        # Boş alt dizinleri (root hariç) temizle.
        for dirpath, _dirs, _files in os.walk(root, topdown=False):
            if os.path.realpath(dirpath) == os.path.realpath(root):
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass
    return {'cleared': int(removed), 'dir': root}


# ---------------------------------------------------------------------------
# 8) Ana çözücü — route bunu çağırır, kendisi ince kalır
# ---------------------------------------------------------------------------

def layer_config(layer_key: str) -> Optional[dict]:
    """Allowlist'teki katman yapılandırması ya da None."""
    if not isinstance(layer_key, str) or not _LAYER_KEY_RE.match(layer_key):
        return None
    return LAYERS.get(layer_key)


def list_layers() -> dict:
    """Ön yüze güvenli katman kataloğu (URL/host sızdırmaz)."""
    out = {}
    for key, cfg in LAYERS.items():
        out[key] = {
            'time': cfg['time'],
            'max_zoom': cfg['max_zoom'],
            'attribution': cfg['attribution'],
        }
    return {'default': DEFAULT_TILE_LAYER, 'layers': out}


def _err(code: int, message: str, **extra) -> dict:
    d = {'ok': False, 'code': int(code), 'error': message}
    d.update(extra)
    return d


def resolve_tile(layer_key: str, z, x, y, date: Optional[str] = None) -> dict:
    """Karoyu doğrula → önbellekten sun ya da GIBS'ten çek → önbelleğe yaz.

    Dönüş (route send_file/jsonify'a çevirir; Flask bağımlılığı YOK):
      başarı : {'ok': True, 'path': <abs>, 'mimetype': 'image/jpeg',
                'layer': <key>, 'cached': bool, 'attribution': <str>}
      hata   : {'ok': False, 'code': 404|400|403|503, 'error': <str>[, ...]}

    Kapılar (spec sırası): layer allowlist → z/x/y int+aralık → date regex →
    realpath önek → HIT(mtime touch) → MISS(GIBS→_http_bytes→atomik yaz)
    → fetch fail 503 {available:false}.
    """
    # -- 1) Katman allowlist --
    cfg = layer_config(layer_key)
    if cfg is None:
        return _err(404, 'unknown layer')

    # -- 2) z/x/y int + aralık --
    try:
        z = int(z); x = int(x); y = int(y)
    except (TypeError, ValueError):
        return _err(400, 'z/x/y must be integers')
    if not _in_range(z, x, y, cfg['max_zoom']):
        return _err(400, 'tile coordinate out of range')

    # -- 3) date (yalnız zaman katmanı) --
    if cfg['time']:
        if not date or not _DATE_RE.match(str(date)):
            return _err(400, 'date required (YYYY-MM-DD) for time layer')
        date_seg = str(date)
    else:
        date_seg = 'default'               # statik katman: date yok sayılır

    # -- 4) Disk yolu + realpath önek kapısı --
    root = tiles_root()
    path = _tile_path(root, layer_key, date_seg, z, x, y, cfg['ext'])
    if path is None:
        return _err(403, 'path traversal blocked')

    mimetype = _EXT_MIME.get(cfg['ext'], 'application/octet-stream')

    # -- 5) HIT: mtime dokun (LRU tazele) + sun --
    if os.path.exists(path):
        try:
            os.utime(path, None)
        except OSError:
            pass
        return {'ok': True, 'path': path, 'mimetype': mimetype,
                'layer': layer_key, 'cached': True,
                'attribution': cfg['attribution']}

    # -- 6) MISS: GIBS'ten çek (ağ, kilit DIŞINDA) --
    url = _gibs_url(cfg, z, x, y, date_seg)
    data = _http_bytes(url, HTTP_TIMEOUT_S)
    if not data:
        # Sahte doku YOK — çevrimdışı/erişilemez: 503, ön yüz karoyu atlar.
        return _err(503, 'tile fetch failed', available=False)

    # -- 7) Atomik yaz + LRU (kilit İÇİNDE) --
    with _lock:
        # Yarış: başka istek bu arada yazmış olabilir.
        if not os.path.exists(path):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                fd, tmp = tempfile.mkstemp(
                    dir=os.path.dirname(path), suffix='.tmp')
                try:
                    with os.fdopen(fd, 'wb') as fh:
                        fh.write(data)
                    os.replace(tmp, path)   # atomik
                finally:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
            except OSError:
                # Disk yazımı başarısız olsa bile baytları sunabiliriz, ama
                # kalıcılık yok. Yol yoksa yamayı besleyemeyiz → 503.
                return _err(503, 'tile cache write failed', available=False)
        _enforce_cap(root)

    return {'ok': True, 'path': path, 'mimetype': mimetype,
            'layer': layer_key, 'cached': False,
            'attribution': cfg['attribution']}
