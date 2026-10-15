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

AĞ KAPISI (K5a, gizlilik; temel ilke karar §28-33, tasarım §4.1-2):
  * Karo isteği, kullanıcının HANGİ bölgeye baktığını sağlayıcıya söyler.
    Bu yüzden dış istek yalnız kullanıcı ağ anahtarını AÇTIYSA gider.
    Varsayılan KAPALI; kapı fail-closed.
  * Kapı dış isteği atan TEK fonksiyondadır (``_http_bytes``): izin
    bağlamı açık değilse ``NetworkDisabledError`` yükseltir ve tek bayt
    ağa çıkmaz. Bu fonksiyonu çağıran yeni bir yol da varsayılan olarak
    kapalıdır (izni unutan kod sessizce ağa çıkamaz).
  * İzin YALNIZ ``resolve_tile(..., allow_network=True)`` çağrısı süresince
    açıktır (``contextvars``; iş parçacığı ya da istek arasında sızmaz).
    ``True`` dışındaki her değer (None, 1, 'true', ...) kapalı sayılır.
  * Kapalıyken önbellekteki karo yine sunulur (dış istek yok); önbellekte
    olmayan karo 403 ``{'network_disabled': True}`` döner, ön yüz o hücrede
    taban dokuyu bırakır (sahte doku yok).
"""

import contextvars
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

# --- K5a ağ kapısı ---------------------------------------------------------
#: Ön yüzün karo isteğine eklediği rıza parametresi (``?net=1``). Kullanıcının
#: kalıcı ağ anahtarı açıksa gönderilir; yoksa ya da başka bir değerse kapı
#: KAPALIDIR (fail-closed). Tek kaynak: ``network_opt_in``.
NETWORK_OPT_IN_PARAM = 'net'
NETWORK_OPT_IN_VALUE = '1'
#: Bu çağrı bağlamında dış isteğe izin var mı? Varsayılan KAPALI.
_NETWORK_ALLOWED = contextvars.ContextVar('hrma_tile_network_allowed',
                                          default=False)


class NetworkDisabledError(RuntimeError):
    """Ağ anahtarı kapalıyken dış karo isteği denendi (hiç istek atılmadı)."""


def network_opt_in(value) -> bool:
    """İstekteki rıza değerini fail-closed okur: yalnız tam ``'1'`` açıktır."""
    return isinstance(value, str) and value == NETWORK_OPT_IN_VALUE

# Katman allowlist. Anahtar (layer_key) HEM URL HEM disk yolunda kullanılır →
# ^[a-z0-9_]+$ ile sınırlı, sabit sözlük anahtarı (kullanıcı girdisi değil).
#   wmts      : GIBS resmi katman kimliği (WMTSCapabilities.xml ile teyitli)
#   tms       : TileMatrixSet kimliği (500m / 250m)
#   time      : Dimension:Time gerektirir mi (tarihli katman)
#   max_zoom  : izin verilen en yüksek z (500m z0-7, 250m z0-8)
#   ext       : dosya uzantısı / MIME türetimi
#   attribution: kaynak metni (sunucu tarafı kaydı — EKRANDAKİ metin
#                i18n sözlüğünden gelir, bkz. attribution_i18n_key)
#   attribution_i18n_key: ekrandaki künyenin i18n anahtarı; ön yüz künyeyi
#                BU anahtardan çevirir (ÖH D21 / P12aB4-19). Anahtarı
#                olmayan katmanın künyesi hiç basılmaz (fail-closed).
#   ui_offered: ÖN YÜZ bu katmanı seçilebilir olarak sunuyor mu?
#
# --- ÖH D24 / P5B4-29: "ön yüz sunar" İDDİASI YANLIŞTI --------------------
# ÖLÇÜLEN (taban ``88a29d3``, kanıt ``once_p5b429.json``): ``viirs``
# katmanının künyesi "ön yüz dürüstlük uyarısıyla sunar" diyordu. Depoda
# ``viirs`` araması bu dosyanın DIŞINDA yalnız testlerde eşleşiyor;
# ``launch_site_globe.js`` ``TILE_LAYER = 'bluemarble'`` SABİTİ ile çalışır
# ve ``TILE_ATTRIBUTION_KEY``te tek bir katman (bluemarble) tanımlıdır.
# Yani ön yüzde katman seçici YOKTUR ve viirs hiçbir zaman çizilmez.
# Buna karşın katman ``/api/tile/cache/status`` gövdesinde diğerinin
# yanında, ayırt edilmeden yayımlanıyordu — okuyan onu "mevcut" sanardı.
#
# Katman SUNUCUDAN çekilebilir durumdadır (``resolve_tile`` onu getirir);
# yalan olan "ön yüz sunar" kısmıydı. İki gerçek artık yanıtta AYRI
# alanlarda yazılıdır: ``served`` (arka uç getirir) ve ``ui_offered``
# (arayüz seçtirir). Ön yüze katman seçici eklemek P15 borcudur.
LAYERS: Dict[str, dict] = {
    'bluemarble': {
        'wmts': 'BlueMarble_ShadedRelief_Bathymetry',
        'tms': '500m',
        'time': False,
        'max_zoom': 7,
        'ext': 'jpg',
        'attribution': 'NASA GIBS — Blue Marble Shaded Relief + Bathymetry (~500 m)',
        'attribution_i18n_key': 'site.tileAttribution',
        'ui_offered': True,
    },
    'viirs': {
        # OPSİYONEL: 250 m gerçek renk, TARİHLİ (Dimension:Time zorunlu),
        # bulut riski taşır → varsayılan DEĞİL. Ön yüz bu katmanı SUNMAZ
        # (P5B4-29): seçici yok, i18n künye anahtarı yok. Arka uç ister
        # istenirse getirir; ekranda çizilmez.
        'wmts': 'VIIRS_SNPP_CorrectedReflectance_TrueColor',
        'tms': '250m',
        'time': True,
        'max_zoom': 8,
        'ext': 'jpg',
        # ÖH D26 / defter P5B4-35 — DİL KARIŞIMI GİDERİLDİ. Bu alan bir
        # API alanıdır (``/api/tile/cache/status`` gövdesinde, katman
        # kaydının içinde yayımlanır) ve kardeşi (``bluemarble``)
        # İNGİLİZCEDİR. Eski metin "(~250 m, tarihli, bulut riski)" ile
        # cümlenin yarısını Türkçeye çeviriyordu: aynı alanın iki kaydı
        # iki dilde konuşuyordu. Ekrandaki künye zaten i18n sözlüğünden
        # gelir (``attribution_i18n_key``; bu katmanda None, çünkü ön yüz
        # onu sunmuyor — P5B4-29), yani buradaki metnin Türkçe olmasının
        # kullanıcıya hiçbir faydası yoktu, tek etkisi tutarsızlıktı.
        'attribution': ('NASA GIBS — VIIRS SNPP True Color (~250 m, '
                        'time-dimensioned, cloud risk)'),
        'attribution_i18n_key': None,
        'ui_offered': False,
    },
    # --- harita-detay K4 (F2; tasarım §3.4): PAKETLİ çevrimdışı piramit ---
    # NASA Blue Marble NG (Aralık 2004, Reto Stöckli) 21600x10800 kaynaktan
    # tools/build_bm_pyramid.py ile üretilen z0-z5 WebP karolar
    # (hrma/static/map/bm_pyr/<z>/<x>/<y>.webp + manifest.json). Bu katman
    # AĞA HİÇ ÇIKMAZ ve disk önbelleğine yazmaz: dosya zaten pakette. Ağ
    # kapısı (K5a) bu katmanı ilgilendirmez; anahtar kapalıyken de çizilir.
    # API künyesi tek dilde (İngilizce, ASCII) yazılır: Stöckli -> Stoeckli
    # (test_d26 tek dil bekçisi); Türkçe künye i18n sözlüğündedir.
    'bm_local': {
        'source': 'packaged',
        'max_zoom': 5,
        'ext': 'webp',
        'time': False,
        'attribution': ('NASA Blue Marble Next Generation, December 2004 '
                        '(Reto Stoeckli, NASA Earth Observatory); packaged '
                        'offline texture, ~2 km'),
        'attribution_i18n_key': 'site.tilePackagedAttribution',
        'ui_offered': True,
    },
}
DEFAULT_TILE_LAYER = 'bluemarble'
#: Paketli katmanın anahtarı ve kaynak türü (tek tanım; araç ve testler
#: buradan okur).
PACKAGED_LAYER_KEY = 'bm_local'
PACKAGED_SOURCE = 'packaged'
#: Ekvatorda bir derece [m] (WGS84 yarı büyük eksen 6.378.137 m x pi/180).
#: launch_site_globe.js TILE_Z0_MPP yorumundaki çarpanla aynı tanım.
EQUATOR_M_PER_DEG = 111319.49
#: Paketli piramidin kökü (depo içi, salt-okur). Testler bunu geçici dizine
#: çevirebilir; ortam değişkeniyle değiştirilemez (kullanıcı girdisi değil).
PACKAGED_ROOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'static', 'map', 'bm_pyr')


def packaged_root() -> str:
    """Paketli piramit kökü (``hrma/static/map/bm_pyr``)."""
    return PACKAGED_ROOT

_LAYER_KEY_RE = re.compile(r'^[a-z0-9_]+$')
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

_EXT_MIME = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
             'webp': 'image/webp'}
_IMAGE_EXTS = ('.jpg', '.jpeg', '.png')

# ---------------------------------------------------------------------------
# 2) Cache boyutu / eşzamanlılık
# ---------------------------------------------------------------------------

class TileCacheConfigError(ValueError):
    """Önbellek yapılandırması çözülemedi — sessiz varsayılana DÜŞÜLMEZ.

    ÖH D24 / P5B4-27 — ÖLÇÜLEN KUSUR (taban ``88a29d3``, kanıt
    ``docs/scofield/raw/OH/D24/yapisal-sistem/a1/once_p5b427.json``):
    ``_env_int`` yalnız ``KeyError`` ve ``ValueError`` yakalıyordu, yani

    * ``HRMA_TILE_CACHE_MAX_BYTES=0``  -> cap 0 kabul edildi,
    * ``HRMA_TILE_CACHE_MAX_BYTES=-1`` -> cap −1 kabul edildi,
    * ``HRMA_TILE_CACHE_MAX_BYTES=abc``/``4.5`` -> SESSİZCE 400 MB.

    Sıfır/negatif cap'in ölçülen sonucu: 50 karo / 102.400 baytlık bir
    önbellekte TEK bir ``_enforce_cap`` çağrısı 0 karo / 0 bayta iner —
    yani önbellek her yazımda kendini siler ve her istek GIBS'e gider.
    Operatör bunu hiçbir yerden öğrenemiyordu. Artık çözülemeyen değer
    yapılandırma hatasıdır: adı ve alınan değer istisnada yazılıdır.
    """


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    """Ortam değişkenini tamsayı olarak çöz; çözülemezse HATA ver.

    Değişken HİÇ tanımlı değilse (``KeyError``) belgelenmiş varsayılan
    uygulanır — bu bir yedek değil, "operatör bir şey söylemedi"dir.
    Tanımlıysa ne dediği çözülmek ZORUNDADIR: sayı değilse ya da
    ``minimum`` altındaysa ``TileCacheConfigError``.
    """
    if name not in os.environ:
        return default
    ham = os.environ[name]
    try:
        deger = int(str(ham).strip())
    except (TypeError, ValueError):
        raise TileCacheConfigError(
            f"{name}={ham!r} is not an integer. The tile cache limit was "
            f"not silently reset to its default ({default} bytes): a cache "
            "running on a limit the operator did not choose is a limit "
            "nobody owns.") from None
    if deger < minimum:
        raise TileCacheConfigError(
            f"{name}={deger} is below the minimum ({minimum}). A cap of 0 "
            "or less makes every _enforce_cap call empty the cache "
            "completely, so every tile request would go to GIBS; that is "
            "not a smaller cache, it is no cache at all.")
    return deger


# Varsayılan 400 MB; HRMA_TILE_CACHE_MAX_BYTES ile değiştirilebilir.
# En küçük anlamlı cap 1 bayttır (0 ve altı reddedilir, bkz. P5B4-27).
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

#: Dünya sınırları (EPSG:4326) — karo matrisi z<=2'de bunları TAŞAR.
WORLD_LON_W, WORLD_LON_E = -180.0, 180.0
WORLD_LAT_S, WORLD_LAT_N = -90.0, 90.0


def _dogrula_zoom(z) -> int:
    """z negatif olmayan bir tamsayı mı? Değilse ADIYLA reddet (P5B4-28).

    ÖLÇÜLDÜ (taban ``88a29d3``): ``tile_span_deg(-1)`` ve türevleri çıplak
    ``ValueError: negative shift count`` veriyordu — mesajda ne alanın adı
    ne alınan değer vardı. ``bool`` da bir zoom değildir (``1 << True``
    sessizce çalışırdı).
    """
    if isinstance(z, bool) or not isinstance(z, int):
        raise ValueError(
            f"'z' must be a non-negative integer zoom level; got {z!r} "
            f"({type(z).__name__}).")
    if z < 0:
        raise ValueError(
            f"'z' must be a non-negative integer zoom level; got {z}.")
    return z


def tile_span_deg(z: int) -> float:
    """Bir karonun kapladığı derece (lon ve lat aynı, kareseldir)."""
    return 288.0 / float(1 << _dogrula_zoom(z))


def matrix_size(z: int) -> Tuple[int, int]:
    """(MatrixWidth, MatrixHeight) = (x sütun sayısı, y satır sayısı).

    Tamsayı ceil bölme ile float sapması olmadan hesaplanır.
    """
    p = 1 << _dogrula_zoom(z)             # 2^z
    mw = -(-(360 * p) // 288)             # ceil(360*2^z / 288)
    mh = -(-(180 * p) // 288)             # ceil(180*2^z / 288)
    return int(mw), int(mh)


def matrix_geometry(max_zoom: Optional[int] = None) -> dict:
    """WMTS karo matris geometrisinin YAYIMLANABİLİR biçimi (P5B4-30).

    ÖH D26 / defter P5B4-30 — ÖLÇÜLEN KUSUR (taban ``7751531``, kanıt
    ``docs/scofield/raw/OH/D26/arayuz/a2/once.json``): aynı geometri
    İKİ yerde yaşıyordu.

    * burada, tamsayı ceil ile:
      ``tile_span_deg(z) = 288/2**z``, ``matrix_size(z) =
      (ceil(360*2^z/288), ceil(180*2^z/288))``;
    * ``hrma/static/js/launch_site_globe.js`` içinde, FLOAT ceil ile:
      ``tileSpanDeg(z) = 288.0/Math.pow(2,z)`` ve
      ``mw = Math.ceil(360.0/span), mh = Math.ceil(180.0/span)``.

    z0-z7'de iki taraf aynı sayıyı veriyordu (sayısal ayrışma ÖLÇÜLDÜ ve
    YOKTU); kusur sonuçta değil SAHİPLİKTEDİR. İstemcinin kendi
    kopyasındaki yorum bunu zaten itiraf ediyordu: *"tile_cache.py'nin
    AYNI formülünün istemci kopyası ... İkisi değişirse birlikte
    güncellenmeli"*. Aynı sayının iki sahibi olduğunda biri sessizce
    kayar; kutup kırpma ve tarih çizgisi sarmalama mantığı da aynı
    şekilde ikizlenmişti.

    ARTIK: sayı burada üretilir, uç (``/api/tile/cache/status``) yayımlar
    ve istemci OKUR. İstemci kendi türetimini yapmaz; geometri
    yüklenmemişse karo İSTEMEZ (fail-closed) — yanlış karo istemektense
    hiç istememek doğrudur, altındaki taban dokusu görünür kalır.

    Dönen sözlük:
      ``tile_span_deg_numerator``  — açıklık formülünün payı (288.0)
      ``levels``                   — z -> {span_deg, matrix_width,
                                     matrix_height}
      ``max_zoom``                 — kapsanan en yüksek z
      ``wrap_x`` / ``clamp_y``     — sarmalama/kırpma sözleşmesi (istemci
                                     kendi kuralını icat etmesin)
      ``basis``                    — künye
    """
    if max_zoom is None:
        max_zoom = max(int(cfg['max_zoom']) for cfg in LAYERS.values())
    max_zoom = _dogrula_zoom(max_zoom)
    seviyeler = {}
    for z in range(max_zoom + 1):
        mw, mh = matrix_size(z)
        seviyeler[str(z)] = {
            'span_deg': tile_span_deg(z),
            'matrix_width': mw,
            'matrix_height': mh,
        }
    return {
        'tile_span_deg_numerator': 288.0,
        'max_zoom': max_zoom,
        'levels': seviyeler,
        # Sözleşme: x tarih çizgisinde SARMALANIR, y kutupta KIRPILIR.
        # (``lonlat_to_tile`` bu iki kuralı uygular; istemci ikizlemesin.)
        'wrap_x': True,
        'clamp_y': True,
        'basis': (
            'WMTS EPSG:4326 (CRS84) TileMatrixSet geometry, computed with '
            'integer ceiling division from tile_span_deg = 288/2**z; '
            'MatrixWidth = ceil(360*2**z/288), MatrixHeight = '
            'ceil(180*2**z/288). Verified against GIBS '
            'WMTSCapabilities.xml (z0 2x1, z3 10x5, z7 160x80). This is '
            'the single owner of the number: no client re-derives it.'),
    }


def tile_to_bbox(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """Karo -> (lonW, latS, lonE, latN) derece kutusu, DÜNYAYA KIRPILMIŞ.

    TopLeftCorner=(-180,+90); x doğuya, y güneye artar.

    ÖH D24 / P5B4-28 — ÖLÇÜLEN KUSUR (taban ``88a29d3``, kanıt
    ``once_p5b428.json``): WMTS matris genişliği ``ceil(360/span)``
    olduğundan z<=2'de matris dünyadan TAŞAR (z0 2x1 karo x 288° = 576°
    x 288°). Kırpma yapılmadığı için son karo ``(108,0, -198,0, 396,0,
    90,0)`` dönüyordu: hem boylam hem enlem dünya dışında. Bu kutuyla
    çizilen bir yama Dünya'nın olmayan bir parçasını kaplardı.

    Kırpma ÜRETMEZ, KISITLAR: dönen kutu her zaman
    [-180,180] x [-90,90] içindedir; z>=3'te matris dünyayla birebir
    örtüştüğü için hiçbir sayı değişmez (kırpma etkisizdir).
    """
    span = tile_span_deg(z)
    lon_w = -180.0 + x * span
    lat_n = 90.0 - y * span
    return (
        min(max(lon_w, WORLD_LON_W), WORLD_LON_E),
        min(max(lat_n - span, WORLD_LAT_S), WORLD_LAT_N),
        min(max(lon_w + span, WORLD_LON_W), WORLD_LON_E),
        min(max(lat_n, WORLD_LAT_S), WORLD_LAT_N),
    )


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

    K5a: TEK istisna ağ kapısıdır. Bu çağrı bağlamında izin açık değilse
    (``_NETWORK_ALLOWED`` tam ``True`` değil) ``NetworkDisabledError``
    yükseltir; ``urllib`` hiç çağrılmaz, ağa tek bayt çıkmaz.
    """
    if _NETWORK_ALLOWED.get() is not True:
        raise NetworkDisabledError('tile network access is disabled')
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


# --- ÖH D21 / P5B4-24: MUHASEBE DİSKİ SAYAR, YALNIZ RESİMLERİ DEĞİL -------
# Üç muhasebe fonksiyonunun üçü de ``_iter_tiles`` üzerinden yürüyordu ve o
# üreteç YALNIZ ``_IMAGE_EXTS`` uzantılı dosyaları görüyordu. Yarıda kalan
# yazımın bıraktığı ``.tmp`` (``tempfile.mkstemp(suffix='.tmp')`` — süreç
# çökerse ``finally`` koşmaz) hiçbir sayıya girmiyordu.
# ÖLÇÜLDÜ (``once.json`` P5B4-24; 2 karo x 26 B + 1 adet 500.000 B .tmp):
#     diskte 500.052 B / 3 dosya  <->  cache_status.bytes = 52, tiles = 2
#     cache_clear -> {'cleared': 2}, diskte 500.000 B KALIYOR
#     ardından cache_status.bytes = 0  (disk hâlâ yarım megabayt dolu)
# Yani 400 MB'lık ``TILE_CACHE_MAX_BYTES`` disk kullanımının capı DEĞİLDİ:
# LRU süpürmesi de aynı üreteci kullandığı için artıkları hiç görmüyordu ve
# cap altında kalındığı sanılırken disk sınırsız büyüyebiliyordu.
#
# Önbellek kökü YALNIZ bu modüle aittir (``tiles_root()``), dolayısıyla
# oradaki HER dosya önbelleğin disk kullanımıdır. Muhasebe artık tüm
# dosyaları sayar; süpürme ve temizlik de tümünü kapsar. Karo SAYISI
# (``tiles``) yine yalnız resimleri sayar — o "kaç karo önbellekte" sorusunun
# cevabıdır ve artık ``bytes`` ile aynı soruyu yanıtlıyor gibi görünmez:
# artık baytlar ``stale_bytes``/``stale_files`` alanlarında AYRICA yazılıdır.
def _iter_all_files(root: str):
    """(mtime, size, path) üreteci — önbellek kökündeki HER dosya."""
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            yield st.st_mtime, st.st_size, p


#: ÖH D22 / P5B4-25 — karo imzaları. Uzantı bir İDDİAdır, imza KANITtır.
#: (JPEG: SOI ``FF D8 FF``; PNG: 8 baytlık imza.) Sunulan mimetype bu
#: tablodan doğrulanır; yeni bir uzantı eklenirse imzası da buraya girer.
_TILE_MAGIC = {
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'png': (b'\x89PNG\r\n\x1a\n',),
}


#: WebP: RIFF kabı, 8. bayttan itibaren 'WEBP' (RIFF uzunluğu arada).
_WEBP_RIFF, _WEBP_ETIKET, _WEBP_ETIKET_KONUM = b'RIFF', b'WEBP', 8


def _is_valid_webp(path: str) -> bool:
    """Dosya RIFF/WEBP imzası taşıyor mu? (boş ya da başka biçim -> False)"""
    try:
        with open(path, 'rb') as fh:
            bas = fh.read(_WEBP_ETIKET_KONUM + len(_WEBP_ETIKET))
    except OSError:
        return False
    return (bas.startswith(_WEBP_RIFF)
            and bas[_WEBP_ETIKET_KONUM:] == _WEBP_ETIKET)


def _is_valid_tile(path: str, ext: str) -> bool:
    """Dosya gerçekten o uzantının resmi mi? (boyut + sihirli imza)

    İmzası bilinmeyen uzantı için yalnız "boş değil" şartı aranır — bu
    fonksiyon hiçbir zaman sahte bir 'geçerli' üretmez, yalnız kanıtı
    olmayan baytı reddeder.
    """
    try:
        if os.path.getsize(path) <= 0:
            return False
        imzalar = _TILE_MAGIC.get(str(ext).lower())
        if not imzalar:
            return True
        with open(path, 'rb') as fh:
            bas = fh.read(max(len(i) for i in imzalar))
        return any(bas.startswith(i) for i in imzalar)
    except OSError:
        return False


def _cache_usage(root: Optional[str] = None) -> Tuple[int, int]:
    """(toplam_disk_baytı, karo_sayısı).

    Bayt DİSK kullanımıdır (artıklar dâhil); sayaç yalnız resim karolarını
    sayar. Bkz. yukarıdaki P5B4-24 ölçümü.
    """
    root = root or tiles_root()
    total = 0
    count = 0
    for _mtime, _size, p in _iter_all_files(root):
        total += _size
        if p.lower().endswith(_IMAGE_EXTS):
            count += 1
    return total, count


def _stale_usage(root: str) -> Tuple[int, int]:
    """(artık_bayt, artık_dosya_sayısı) — resim OLMAYAN her dosya."""
    total = 0
    count = 0
    for _mtime, size, p in _iter_all_files(root):
        if p.lower().endswith(_IMAGE_EXTS):
            continue
        total += size
        count += 1
    return total, count


#: ÖH D22 / P5B4-26 — ÇALIŞAN BAYT SAYACI (kök -> bayt).
#: ``_lock`` altında okunur/yazılır; süreç ömrü boyunca yaşar.
_usage_cache: dict = {}


def _usage_bump(root: str, delta: int) -> None:
    """Sayaç KURULUYSA delta kadar ilerlet (yoksa dokunma).

    Sayaç yoksa bir sonraki ``_enforce_cap`` zaten tam tarama yapar.
    """
    mevcut = _usage_cache.get(root)
    if mevcut is not None:
        _usage_cache[root] = max(0, mevcut + int(delta))


def _enforce_cap(root: str, added_bytes: int = 0) -> None:
    """Cap aşıldıysa artıkları ve en eski karoları düşük-suya kadar siler.

    _lock altında çağrılmalı. Süpürme sırası: önce yarım yazımdan kalan
    resim-olmayan artıklar (hiçbir HIT onları sunamaz, yani en ucuz bayt),
    sonra en eski (küçük mtime) karolar.

    --- ÖH D22 / P5B4-26: HER YAZIMDA TAM TARAMA YOK -------------------
    ÖLÇÜLDÜ (``once.json`` P5B4-26): fonksiyon her ıskalanan karo
    yazımında KOŞULSUZ tam bir ``os.walk`` yapıyordu ve bunu global
    ``_lock`` İÇİNDE yapıyordu — 20 çağrıda 20 tarama; 200 karoda
    0,7226 ms, 2000 karoda 5,374 ms (yaklaşık doğrusal). 400 MB'lık
    varsayılan cap ~200.000 dosya demektir, yani ölçek büyüdükçe her
    önbellek yazımı bütün ağacı kilit altında geziyordu.

    Düzeltme MUHASEBEYİ DEĞİŞTİRMEZ, yalnız ne zaman sayıldığını
    değiştirir: çalışan bir bayt sayacı tutulur (kilit altında, tek
    yazar), yeni yazılan bayt ona eklenir ve TAM TARAMA yalnız sayaç capı
    aştığında (ya da sayaç henüz kurulmamışken) yapılır. Süpürme kararı
    hâlâ diskin gerçeğinden verilir — sayaç yalnız "bakmaya değer mi"
    sorusunu ucuzlatır, cap'in kendisini gevşetmez.
    """
    calisan = _usage_cache.get(root)
    if calisan is not None:
        calisan += int(added_bytes)
        _usage_cache[root] = calisan
        if calisan <= TILE_CACHE_MAX_BYTES:
            return
    total, _ = _cache_usage(root)
    _usage_cache[root] = total
    if total <= TILE_CACHE_MAX_BYTES:
        return
    target = int(TILE_CACHE_MAX_BYTES * _LRU_LOW_WATER)
    # 1) Artıklar: sunulamayan bayt önce gider.
    for _mtime, size, p in sorted(_iter_all_files(root)):
        if total <= target:
            _usage_cache[root] = total
            return
        if p.lower().endswith(_IMAGE_EXTS):
            continue
        try:
            os.remove(p)
            total -= size
        except OSError:
            pass
    # 2) Karolar: en eskiden başlayarak.
    entries = sorted(_iter_tiles(root))    # en eski (küçük mtime) önce
    for _mtime, size, p in entries:
        if total <= target:
            break
        try:
            os.remove(p)
            total -= size
        except OSError:
            pass
    _usage_cache[root] = total


def cache_status() -> dict:
    """{bytes, tiles, stale_bytes, stale_files, dir, max_bytes, network_opt_in}.

    ``bytes`` önbellek kökünün GERÇEK disk kullanımıdır (``max_bytes`` bunun
    capıdır); ``tiles`` sunulabilir karo sayısı, ``stale_*`` ise yarım
    yazımdan kalan sunulamaz artıklardır. /api/tile/cache/status için.
    """
    root = tiles_root()
    total, count = _cache_usage(root)
    stale_bytes, stale_files = _stale_usage(root)
    return {
        'bytes': int(total),
        'tiles': int(count),
        'stale_bytes': int(stale_bytes),
        'stale_files': int(stale_files),
        'dir': root,
        'max_bytes': int(TILE_CACHE_MAX_BYTES),
        # K5a: ön yüz rıza parametresini buradan okur (ikinci kopya yok).
        'network_opt_in': {'param': NETWORK_OPT_IN_PARAM,
                           'value': NETWORK_OPT_IN_VALUE,
                           'default': 'off'},
    }


def cache_clear() -> dict:
    """Önbellek kökündeki HER dosyayı sil + boş dizinleri temizle.

    ``cleared`` silinen karo sayısıdır (eski sözleşme), ``cleared_stale``
    silinen artık sayısı, ``bytes_freed`` boşalan disk. /api/tile/cache/clear.
    """
    root = tiles_root()
    removed = 0
    removed_stale = 0
    freed = 0
    with _lock:
        for _mtime, size, p in list(_iter_all_files(root)):
            karo = p.lower().endswith(_IMAGE_EXTS)
            try:
                os.remove(p)
            except OSError:
                continue
            freed += size
            if karo:
                removed += 1
            else:
                removed_stale += 1
        # Boş alt dizinleri (root hariç) temizle.
        for dirpath, _dirs, _files in os.walk(root, topdown=False):
            if os.path.realpath(dirpath) == os.path.realpath(root):
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass
        _usage_cache[root] = 0        # ÖH D22 / P5B4-26: sayaç da sıfırlanır
    return {'cleared': int(removed), 'cleared_stale': int(removed_stale),
            'bytes_freed': int(freed), 'dir': root}


# ---------------------------------------------------------------------------
# 8) Ana çözücü — route bunu çağırır, kendisi ince kalır
# ---------------------------------------------------------------------------

def layer_config(layer_key: str) -> Optional[dict]:
    """Allowlist'teki katman yapılandırması ya da None."""
    if not isinstance(layer_key, str) or not _LAYER_KEY_RE.match(layer_key):
        return None
    return LAYERS.get(layer_key)


#: ``list_layers`` künyesi (ÖH D24 / P5B4-29). Yanıtta ``layers_basis``.
LAYERS_BASIS = (
    "'served' means the backend will fetch and cache this layer if it is "
    "asked for. 'ui_offered' means the shipped front end actually lets a "
    "user select it: today only the default layer is offered, because "
    "launch_site_globe.js draws a single fixed layer and carries an "
    "attribution key for that one alone. A layer with ui_offered=false is "
    "reachable through the API but is never drawn on screen; listing it "
    "here is not a claim that you can see it.")


#: ``list_layers`` 'packaged' künyesi (harita-detay K4).
PACKAGED_BASIS = (
    "'packaged' layers ship with the application and are served from disk "
    "without any network request. They are not NASA GIBS layers: each "
    "carries its own source attribution.")


def list_layers() -> dict:
    """Ön yüze güvenli katman kataloğu (URL/host sızdırmaz).

    ÖH D24 / P5B4-29: katalog artık "arka uç getirir" ile "arayüz sunar"
    iddialarını AYIRIR; ikisi aynı şey değildir ve eskiden ayırt
    edilmiyordu.
    """
    out, paketli = {}, {}
    for key, cfg in LAYERS.items():
        # harita-detay K4: paketli katman GIBS kataloğuna KARIŞMAZ. 'layers'
        # NASA GIBS'ten gelen katmanlardır (her birinin künyesi GIBS atfını
        # taşır; test_faz6_baslik_kodlama bunu kilitler); paketli katman
        # GIBS'ten gelmez, kendi künyesiyle 'packaged' altında yayımlanır.
        hedef = paketli if cfg.get('source') == PACKAGED_SOURCE else out
        hedef[key] = {
            # 'packaged': uygulamayla gelir, ağa çıkmaz; 'gibs': NASA GIBS.
            'source': cfg.get('source', 'gibs'),
            'time': cfg['time'],
            'max_zoom': cfg['max_zoom'],
            'attribution': cfg['attribution'],
            # Ekrandaki künyenin TEK kaynağı i18n sözlüğüdür; burada yalnız
            # anahtar durur (metin ikinci kez yazılmaz).
            'attribution_i18n_key': cfg.get('attribution_i18n_key'),
            'served': True,
            'ui_offered': bool(cfg.get('ui_offered', False)),
        }
    return {'default': DEFAULT_TILE_LAYER, 'layers': out,
            'layers_basis': LAYERS_BASIS, 'packaged': paketli,
            'packaged_basis': PACKAGED_BASIS}


def _err(code: int, message: str, **extra) -> dict:
    d = {'ok': False, 'code': int(code), 'error': message}
    d.update(extra)
    return d


def resolve_tile(layer_key: str, z, x, y, date: Optional[str] = None,
                 allow_network: bool = False) -> dict:
    """Karoyu doğrula → önbellekten sun ya da GIBS'ten çek → önbelleğe yaz.

    ``allow_network``: kullanıcının ağ anahtarı (K5a). Yalnız tam ``True``
    dış isteğe izin verir; varsayılan KAPALI. Kapalıyken önbellek HIT'i
    sunulur, MISS 403 ``{'network_disabled': True}`` döner.

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

    # -- 2b) Paketli katman: AĞ YOK, önbellek YOK (harita-detay K4) --
    if cfg.get('source') == PACKAGED_SOURCE:
        return _resolve_packaged(layer_key, cfg, z, x, y)

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

    # -- 5) HIT: sağlamlık kapısı -> mtime dokun (LRU tazele) + sun --
    # --- ÖH D22 / P5B4-25: BOZUK KARO GEÇERLİ SAYILMAZ -------------------
    # ÖLÇÜLDÜ (``once.json`` P5B4-25): önbellek yoluna 0 baytlık bir dosya
    # ya da düz metin ("<html>404 not found</html>") konduğunda HIT dalı
    # onu ``ok=True, cached=True, mimetype='image/jpeg'`` ile sunuyordu —
    # tek kapı ``os.path.exists``ti. Üstüne ``app.py`` yanıta
    # ``max-age=31536000, immutable`` koyuyor, yani tarayıcı o bozuk baytı
    # BİR YIL saklıyordu; ``os.utime`` da her HIT'te mtime'ı tazelediği
    # için LRU süpürmesi bozuk karoyu asla eskitmiyordu (kalıcı kilit).
    #
    # Kapı fail-closed ve İMZAdan okur, uzantıdan değil: dosya boşsa ya da
    # baytları uzantının sihirli imzasını taşımıyorsa karo YOK sayılır,
    # diskten silinir ve akış MISS dalına düşer (yeniden çekilir). Sahte
    # doku üretilmez; ağ da yoksa mevcut 503 yolu aynen çalışır.
    if os.path.exists(path) and not _is_valid_tile(path, cfg['ext']):
        try:
            os.remove(path)
        except OSError:
            pass
    if os.path.exists(path):
        try:
            os.utime(path, None)
        except OSError:
            pass
        return {'ok': True, 'path': path, 'mimetype': mimetype,
                'layer': layer_key, 'cached': True,
                'attribution': cfg['attribution']}

    # -- 6) MISS: GIBS'ten çek (ağ, kilit DIŞINDA) --
    # K5a: izin YALNIZ bu çağrı süresince açılır ve her yolda geri alınır.
    url = _gibs_url(cfg, z, x, y, date_seg)
    jeton = _NETWORK_ALLOWED.set(allow_network is True)
    try:
        data = _http_bytes(url, HTTP_TIMEOUT_S)
    except NetworkDisabledError:
        return _err(403, 'tile network access is disabled',
                    network_disabled=True, available=False)
    finally:
        _NETWORK_ALLOWED.reset(jeton)
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
            _yeni_bayt = len(data)
        else:
            _yeni_bayt = 0
        # ÖH D22 / P5B4-26: yeni bayt sayaca bildirilir; tam tarama yalnız
        # cap aşıldığında (ya da sayaç kurulmamışken) yapılır.
        _enforce_cap(root, added_bytes=_yeni_bayt)

    return {'ok': True, 'path': path, 'mimetype': mimetype,
            'layer': layer_key, 'cached': False,
            'attribution': cfg['attribution']}


def _resolve_packaged(layer_key: str, cfg: dict, z: int, x: int, y: int) -> dict:
    """Paketli karoyu diskten ver (harita-detay K4; tasarım §3.4).

    * Ağa HİÇ çıkılmaz (``_http_bytes`` çağrılmaz), disk önbelleğine
      yazılmaz, ağ izni (K5a) sorulmaz.
    * Yol yalnız doğrulanmış tamsayılardan kurulur ve realpath önekiyle
      pakette kalması denetlenir; sembolik bağla dışarı kaçan yol 403.
    * Dosya yoksa ya da WebP imzası tutmazsa 404 ``available=False``:
      sahte doku yok, ön yüz o hücrede daha kaba katmanı bırakır.
    """
    root = packaged_root()
    rel = os.path.join(str(z), str(x), '%d.%s' % (y, cfg['ext']))
    path = os.path.join(root, rel)
    root_real = os.path.realpath(root)
    path_real = os.path.realpath(path)
    if not path_real.startswith(root_real + os.sep):
        return _err(403, 'path traversal blocked')
    if not os.path.isfile(path_real) or not _is_valid_webp(path_real):
        return _err(404, 'packaged tile not available', available=False,
                    packaged=True)
    return {'ok': True, 'path': path_real,
            'mimetype': _EXT_MIME.get(cfg['ext'], 'application/octet-stream'),
            'layer': layer_key, 'cached': True, 'packaged': True,
            'attribution': cfg['attribution']}
