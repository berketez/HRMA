#!/usr/bin/env python3
"""3D Dünya küresinin görsel varlıklarını kaynağından yeniden üretir.

Üretilenler
-----------
1) hrma/static/img/blue_marble_4096.jpg
   NASA Blue Marble Next Generation (Nisan 2004, topografya + batimetri),
   5400x2700 kaynaktan 4096x2048'e (2:1, ikinin kuvveti) yeniden örneklenir.
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


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print('  onbellek: %s' % dest.name)
        return dest
    print('  indiriliyor: %s' % url)
    req = urllib.request.Request(url, headers={'User-Agent': 'HRMA-asset-builder'})
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())
    return dest


def build_texture() -> None:
    from PIL import Image
    src = _download(BLUE_MARBLE_URL, CACHE / 'blue_marble_src.jpg')
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


def build_borders() -> None:
    layers = {}
    total_pts = 0
    for name in NE_FILES:
        path = _download(NE_BASE + name, CACHE / name)
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

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    dest = IMG_DIR / 'earth_borders.json'
    payload = {
        'source': 'Natural Earth 1:110m (naturalearthdata.com)',
        'license': 'Public domain',
        'retrieved_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'format': 'flat [lon,lat,...] arrays, degrees, %d decimals' % COORD_DECIMALS,
        'point_count': total_pts,
        'layers': layers,
    }
    dest.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    print('  yazildi: %s (%.0f kB, %d nokta)'
          % (dest, dest.stat().st_size / 1e3, total_pts))


if __name__ == '__main__':
    print('1) Blue Marble dokusu')
    build_texture()
    print('2) Natural Earth sinirlari')
    build_borders()
