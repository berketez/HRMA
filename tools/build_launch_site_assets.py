#!/usr/bin/env python3
"""3D Dünya küresinin görsel varlıklarını kaynağından yeniden üretir.

Üretilenler
-----------
1) hrma/static/img/blue_marble_4096.jpg
   NASA Blue Marble Next Generation (Aralık 2004 — dosya adındaki 200412;
   topografya + batimetri; Reto Stöckli, NASA Earth Observatory),
   5400x2700 kaynaktan 4096x2048'e (2:1, ikinin kuvveti) yeniden örneklenir.
   (Eski künye "Nisan 2004" diyordu; kaynağın kendi adı Aralık 2004'tür.)
   İkinin kuvveti şart: WebGL1 (three.js r128) POT olmayan dokularda mipmap
   üretemez, dokuyu çalışma anında yeniden ölçekler.
   Kaynak: NASA Visible Earth / Earth Observatory, telifsiz (NASA görselleri
   aksi belirtilmedikçe kamu malıdır — NASA Media Usage Guidelines).

2) hrma/static/img/earth_borders.json
   Natural Earth 1:110m ülke sınır çizgileri + kıyı şeridi, kompakt
   polyline formatına indirgenir (ondalık 2 hane ≈ 1.1 km, küre üstünde
   çizgi çizimi için yeterli).
   Kaynak: Natural Earth (naturalearthdata.com) — KAMU MALI, atıf isteğe
   bağlı. nvkelso/natural-earth-vector deposundaki GeoJSON kopyası okunur.
   Sınır düzeltmesi (karar §28-45/Kırım): Perekop kıstağındaki tartışmalı
   Rusya-Ukrayna çizgisi yazmadan önce düşülür. Düşülecek çizginin TEK
   tanımı tools/build_map_detail_assets.py ESKI_110M_SINIR_DUZELTMESI'dir
   (burada içe aktarılır, kopya yok). Çizgi tabloyla birebir bulunamazsa ya
   da kutuda başka sınır çizgisi kalırsa HİÇBİR DOSYA YAZILMAZ.

Kullanım:
    python3 tools/build_launch_site_assets.py
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMG_DIR = REPO / 'hrma' / 'static' / 'img'
CACHE = Path('/tmp/hrma_launch_site_assets')

BLUE_MARBLE_URL = ('https://eoimages.gsfc.nasa.gov/images/imagerecords/'
                   '73000/73909/world.topo.bathy.200412.3x5400x2700.jpg')
NE_BASE = ('https://raw.githubusercontent.com/nvkelso/natural-earth-vector/'
           'master/geojson/')
NE_FILES = ['ne_110m_admin_0_boundary_lines_land.geojson',
            'ne_110m_coastline.geojson']

TEX_W, TEX_H = 4096, 2048
COORD_DECIMALS = 2       # ~1.1 km — 110m ölçekli veri için zaten yeterli

# ---------------------------------------------------------------------------
# İNDİRME KANITI — ÖH D23 / altyapi (defter P10B4-17)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (a2/once.json, taban ef527ae): bu betiğin ``_download``'ı HTTP
# kodunu, boyutu ve içeriği HİÇ sormuyordu; ``dest.stat().st_size > 0``
# önbellek ölçütüydü. Yani bir vekil sunucunun döndürdüğü 12 baytlık HTML
# hata sayfası hem "indirildi" sayılıyor hem de önbellekte SONSUZA dek
# geçerli kalıyordu — ağ bir daha hiç denenmiyordu. Kardeş betik
# ``tools/sky_assets/build_sky_assets.py::_indir`` üç kanıtı da alıyor;
# burada AYNI sözleşme kullanılır (ikinci bir indirme doktrini yazılmaz).
#
# En-az-bayt değerleri kaynakların BUGÜNKÜ ölçülen boyutunun güvenli alt
# sınırıdır (Blue Marble 5400x2700 JPEG ~3,7 MB; Natural Earth 110m GeoJSON
# sınır dosyası ~180 kB, kıyı şeridi ~350 kB). Amaç baytı kilitlemek değil,
# "veri değil hata sayfası geldi" hâlini yakalamaktır.
BLUE_MARBLE_EN_AZ_BAYT = 1_000_000
NE_EN_AZ_BAYT = 50_000

JPEG_IMZA = b'\xff\xd8\xff'
#: GeoJSON gövdesi bir JSON nesnesidir; ilk anlamlı bayt ``{``'tir. HTML
#: hata sayfası ``<``, gzip ``\x1f\x8b`` ile başlar — ikisi de elenir.
JSON_IMZA = b'{'


def _download(url: str, dest: Path, en_az_bayt: int, imza: bytes) -> Path:
    """İndirir ve İNDİRDİĞİNİ KANITLAR: HTTP kodu, boyut, sihirli baytlar.

    Üçünden biri tutmazsa dosya YAZILMAZ (ya da önbellekteyse SİLİNİR) ve
    yükselir. FAIL-CLOSED: kanıtlanmamış bir indirmeden varlık üretilmez.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size >= en_az_bayt:
        # Önbellek de indirilen veriyle AYNI kanıtı vermek zorundadır:
        # yalnız boyuta bakan eski dal, bir kez yarım/HTML inen dosyayı
        # sonsuza dek "geçerli" sayıyordu.
        with open(dest, 'rb') as f:
            bas = f.read(max(len(imza), 8))
        if bas.startswith(imza):
            print('  onbellek: %s (%.2f MB, imza dogrulandi)'
                  % (dest.name, dest.stat().st_size / 1e6))
            return dest
        print('  onbellek REDDEDILDI (imza tutmadi, ilk baytlar %r): %s '
              '— siliniyor, yeniden indirilecek' % (bas[:8], dest.name))
        dest.unlink()

    print('  indiriliyor: %s' % url)
    req = urllib.request.Request(url, headers={'User-Agent': 'HRMA-asset-builder'})
    with urllib.request.urlopen(req, timeout=180) as resp:
        kod = resp.status
        icerik_tipi = resp.headers.get('Content-Type', '?')
        veri = resp.read()
    boyut = len(veri)
    print('  HTTP %s | %s | %d bayt (%.2f MB)'
          % (kod, icerik_tipi, boyut, boyut / 1e6))

    if kod != 200:
        raise RuntimeError('%s -> HTTP %s (200 bekleniyordu)' % (url, kod))
    if boyut < en_az_bayt:
        raise RuntimeError(
            '%s -> yalniz %d bayt geldi, en az %d bekleniyordu. Bu buyukluk '
            'veri degil hata sayfasidir; SAHTE VARLIK URETILMEYECEK.'
            % (url, boyut, en_az_bayt))
    if not veri.lstrip()[:len(imza)].startswith(imza):
        raise RuntimeError(
            '%s -> dosyanin ilk baytlari %r, beklenen imza %r. Sunucu veri '
            'yerine baska bir sey dondurdu.' % (url, veri[:8], imza))

    dest.write_bytes(veri)
    return dest


def build_texture() -> None:
    from PIL import Image
    src = _download(BLUE_MARBLE_URL, CACHE / 'blue_marble_src.jpg',
                    BLUE_MARBLE_EN_AZ_BAYT, JPEG_IMZA)
    img = Image.open(src).convert('RGB')
    print('  kaynak %dx%d -> %dx%d' % (img.width, img.height, TEX_W, TEX_H))
    out = img.resize((TEX_W, TEX_H), Image.LANCZOS)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    dest = IMG_DIR / 'blue_marble_4096.jpg'
    out.save(dest, 'JPEG', quality=86, optimize=True, progressive=False)
    print('  yazildi: %s (%.2f MB)' % (dest, dest.stat().st_size / 1e6))


def _iter_linestrings(geojson: dict):
    for feat in geojson.get('features', []):
        geom = feat.get('geometry') or {}
        gtype = geom.get('type')
        coords = geom.get('coordinates') or []
        if gtype == 'LineString':
            yield coords
        elif gtype == 'MultiLineString':
            for line in coords:
                yield line
        elif gtype == 'Polygon':
            for ring in coords:
                yield ring
        elif gtype == 'MultiPolygon':
            for poly in coords:
                for ring in poly:
                    yield ring


def sinir_duzeltmesini_uygula(layers: dict) -> int:
    """Karar §28-45/Kırım: ``borders`` katmanından tablodaki Perekop
    çizgisini düşer, düşülen nokta sayısını döndürür (FAIL-CLOSED).

    Tablo ``build_map_detail_assets.ESKI_110M_SINIR_DUZELTMESI``'dir (tek
    kaynak; ``eski_110m_sinir_denetimi`` de oradan). Çizgi, noktaları
    tabloyla BİREBİR aynı olan sınır çizgisidir; tam 1 eşleşme şarttır.
    Düşüşten sonra Perekop kutusunda sınır çizgisi kalırsa da yükselir.
    Yükselirse ``layers`` değişmemiştir ve hiçbir dosya yazılmaz.
    """
    import sys
    araclar = str(Path(__file__).resolve().parent)
    if araclar not in sys.path:
        sys.path.insert(0, araclar)
    from build_map_detail_assets import (ESKI_110M_SINIR_DUZELTMESI,
                                         eski_110m_sinir_denetimi)
    tablo = ESKI_110M_SINIR_DUZELTMESI
    hedef = [float(v) for nokta in tablo['points'] for v in nokta]
    cizgiler = layers.get(tablo['layer']) or []
    eslesen = [i for i, c in enumerate(cizgiler) if [float(v) for v in c] == hedef]
    if len(eslesen) != 1:
        raise RuntimeError(
            'sinir duzeltmesi (%s): tablodaki cizgi %s katmaninda %d kez '
            'bulundu, tam 1 bekleniyordu. Kaynak degismis olabilir; tablo '
            'yeniden dogrulanmadan DOSYA YAZILMAYACAK.'
            % (tablo['decision'], tablo['layer'], len(eslesen)))
    kalan = [c for i, c in enumerate(cizgiler) if i != eslesen[0]]
    eski_110m_sinir_denetimi({'layers': dict(layers, **{tablo['layer']: kalan})})
    layers[tablo['layer']] = kalan
    return len(hedef) // 2


def sinir_yuku_bayt(layers: dict, retrieved_utc: str) -> bytes:
    """``earth_borders.json`` baytları (biçimin tek tanımı)."""
    payload = {
        'source': 'Natural Earth 1:110m (naturalearthdata.com)',
        'license': 'Public domain',
        'retrieved_utc': retrieved_utc,
        'format': 'flat [lon,lat,...] arrays, degrees, %d decimals' % COORD_DECIMALS,
        'point_count': sum(len(c) // 2 for cizgiler in layers.values() for c in cizgiler),
        'layers': layers,
    }
    return json.dumps(payload, separators=(',', ':')).encode('utf-8')


def build_borders() -> None:
    layers = {}
    total_pts = 0
    for name in NE_FILES:
        path = _download(NE_BASE + name, CACHE / name,
                         NE_EN_AZ_BAYT, JSON_IMZA)
        data = json.loads(path.read_text(encoding='utf-8'))
        lines = []
        for coords in _iter_linestrings(data):
            flat = []
            prev = None
            for pt in coords:
                lon = round(float(pt[0]), COORD_DECIMALS)
                lat = round(float(pt[1]), COORD_DECIMALS)
                if prev is not None and prev == (lon, lat):
                    continue                      # yuvarlama sonrası tekrar
                flat.append(lon)
                flat.append(lat)
                prev = (lon, lat)
            if len(flat) >= 4:
                lines.append(flat)
                total_pts += len(flat) // 2
        key = 'borders' if 'boundary' in name else 'coastline'
        layers[key] = lines
        print('  %s -> %d cizgi' % (name, len(lines)))

    # Karar §28-45/Kırım: yazmadan ÖNCE (yükselirse dosya yazılmaz).
    dusulen = sinir_duzeltmesini_uygula(layers)
    total_pts -= dusulen
    print('  sinir duzeltmesi (karar §28-45/Kirim): %d nokta dusuldu' % dusulen)

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    dest = IMG_DIR / 'earth_borders.json'
    dest.write_bytes(sinir_yuku_bayt(
        layers, datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')))
    print('  yazildi: %s (%.0f kB, %d nokta)'
          % (dest, dest.stat().st_size / 1e3, total_pts))


if __name__ == '__main__':
    print('1) Blue Marble dokusu')
    build_texture()
    print('2) Natural Earth sinirlari')
    build_borders()
