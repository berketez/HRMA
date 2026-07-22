#!/usr/bin/env python3
"""HRMA fırlatma sahası DEM'ini kaynağından yeniden üretir.

Kaynak
------
ETOPO 2022 (NOAA NCEI), 60 ark-saniye "ice surface" küresel rölyef modeli.
DOI: 10.25921/fd45-gt74 — ABD federal ürünü, telif korumasız (kamu malı).
Dikey datum: EGM2008 geoidi. Yatay: WGS84 coğrafi (EPSG:4326).

Erişim yöntemi
--------------
Tam dosya (21600 x 10800 float32 ≈ 933 MB) indirilmez. NOAA THREDDS
sunucusunun OPeNDAP (DAP2) arayüzü üzerinden ADIMLI (strided) alt küme
istenir: `z[2:5:10799][2:5:21599]`.

  - stride 5  -> 60 ark-saniye kaynaktan 5 ark-dakika hedef grid
  - offset 2  -> 5x5 bloğun MERKEZ hücresi (köşe değil)

Bu bir DECIMATION (nokta örnekleme) işlemidir, blok ORTALAMASI değildir.
Neden: blok ortalaması tüm 933 MB'ın indirilmesini gerektirir; bu depoda
mevcut bağlantı hızıyla (~150 kB/s) saatler sürer. Çözünürlük kaybının
sonuçları SOURCE.md içinde açıkça raporlanır.

Çıktı
-----
  hrma/data/dem/etopo2022_5min_int16.bin.gz   (gzip'li ham int16, satır-öncelikli)
  hrma/data/dem/etopo2022_5min_meta.json      (grid geometrisi + köken)

Grid geometrisi (çıktı dosyasında da yazılı):
  nlat=2160, nlon=4320, çözünürlük 1/12 derece (5 ark-dakika)
  lat[0]  = -89.9583333 (güney kenar), lat artan yönde kuzeye
  lon[0]  = -179.9583333, lon artan yönde doğuya
  Değerler hücre MERKEZİ örnekleri, metre, int16 (little-endian).

Kullanım:
    python3 tools/build_launch_site_dem.py            # tam üretim
    python3 tools/build_launch_site_dem.py --rows 100 # hızlı duman testi
"""

from __future__ import annotations

import argparse
import gzip
import json
import struct
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / 'hrma' / 'data' / 'dem'

# NOAA THREDDS OPeNDAP uç noktası (ETOPO 2022, 60 ark-saniye, ice surface)
DODS_URL = (
    'https://www.ngdc.noaa.gov/thredds/dodsC/global/ETOPO2022/60s/'
    '60s_surface_elev_netcdf/ETOPO_2022_v1_60s_N90W180_surface.nc.dods'
)
SRC_NLAT = 10800          # kaynak satır sayısı (60 ark-saniye)
SRC_NLON = 21600          # kaynak sütun sayısı
STRIDE = 5                # 60" -> 300" (5 ark-dakika)
OFFSET = 2                # 5x5 bloğun merkez hücresi
OUT_NLAT = 2160
OUT_NLON = 4320
FILL_VALUE = -99999.0     # ETOPO _FillValue

BIN_NAME = 'etopo2022_5min_int16.bin.gz'
META_NAME = 'etopo2022_5min_meta.json'

# Derin deniz tabanı nicemlemesi (yalnız DOSYA BOYUTU için).
# -500 m'den DERİN hücreler 100 m adımlara yuvarlanır. Gerekçe: Dünya'nın en
# alçak açık kara noktası Ölü Deniz kıyısı (≈ -430 m) olduğundan -500 m'nin
# altı tanım gereği deniz/göl tabanıdır ve fırlatma sahası olamaz (yüzey
# zaten 0 m alınır). -500 m ve üstü değerler AYNEN korunur — kara ve kıyı
# rakımlarında hiçbir kayıp yoktur. Kazanç: gzip 14.6 MB -> 8.6 MB.
# İşlem idempotenttir (yeniden uygulamak sonucu değiştirmez).
DEEP_QUANT_THRESHOLD_M = -500
DEEP_QUANT_STEP_M = 100


def _quantize_deep_ocean(grid: np.ndarray) -> np.ndarray:
    deep = grid < DEEP_QUANT_THRESHOLD_M
    if deep.any():
        vals = grid[deep].astype(np.float64) / DEEP_QUANT_STEP_M
        grid[deep] = (np.rint(vals) * DEEP_QUANT_STEP_M).astype(np.int16)
    return grid


def _fetch_band(row_start: int, nrows: int, retries: int = 4) -> np.ndarray:
    """OPeNDAP'tan row_start'tan başlayan nrows çıktı satırını adımlı çeker.

    DAP2 `.dods` yanıtı: DDS metni + b'\\nData:\\n' + XDR gövde.
    Grid serileştirmesi: önce ARRAY (2x4 bayt uzunluk + veri), sonra MAP'ler.
    Float32 big-endian ('>f4').

    DİKKAT: DAP2 dilim sözdiziminde son indis DAHİLDİR ve kaynak sınırını
    AŞAMAZ (aşarsa sunucu HTTP 400 döner). Bu yüzden son indis, gerçekten
    örneklenen son satır olarak yazılır: row_start + (nrows-1)*STRIDE.
    """
    row_last = row_start + (nrows - 1) * STRIDE
    if row_last > SRC_NLAT - 1:
        raise ValueError('kaynak satır sınırı aşıldı: %d' % row_last)
    query = 'z[%d:%d:%d][%d:%d:%d]' % (
        row_start, STRIDE, row_last, OFFSET, STRIDE, SRC_NLON - 1)
    url = DODS_URL + '?' + urllib.parse.quote(query, safe='[]:')
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=180) as resp:
                raw = resp.read()
            break
        except Exception as exc:               # ağ hatası -> yeniden dene
            last_err = exc
            time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError('OPeNDAP bandı alınamadı: %s' % last_err)

    marker = b'\nData:\n'
    idx = raw.find(marker)
    if idx < 0:
        raise RuntimeError('DAP2 yanıtında Data bölümü yok: %r' % raw[:200])
    body = raw[idx + len(marker):]
    n1, n2 = struct.unpack('>ii', body[:8])
    if n1 != n2:
        raise RuntimeError('DAP2 dizi uzunluk başlığı tutarsız: %d/%d' % (n1, n2))
    data = np.frombuffer(body[8:8 + 4 * n1], dtype='>f4')
    if data.size != nrows * OUT_NLON:
        raise RuntimeError('Beklenen %d değer, gelen %d'
                           % (nrows * OUT_NLON, data.size))
    return data.reshape(nrows, OUT_NLON).astype(np.float64)


def _write(grid: np.ndarray) -> dict:
    """Gridi nicemler, gzip'ler ve meta dosyasını yazar."""
    grid = _quantize_deep_ocean(grid)
    bin_path = OUT_DIR / BIN_NAME
    payload = grid.astype('<i2').tobytes(order='C')
    with gzip.open(bin_path, 'wb', compresslevel=9) as fh:
        fh.write(payload)

    meta = {
        'name': 'ETOPO 2022 ice-surface, 5 ark-dakikaya adımlı örneklenmiş',
        'source_dataset': 'ETOPO 2022 v1, 60 arc-second, ice surface',
        'source_doi': '10.25921/fd45-gt74',
        'source_url': DODS_URL,
        'source_agency': 'NOAA National Centers for Environmental Information',
        'license': 'Public domain (U.S. Government work, 17 U.S.C. 105)',
        'retrieved_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'resample_method': 'decimation (stride 5, offset 2 = 5x5 blok merkezi)',
        'deep_ocean_quantization': (
            'cells deeper than %d m rounded to %d m steps (file size only; '
            'land and coastal values untouched)'
            % (DEEP_QUANT_THRESHOLD_M, DEEP_QUANT_STEP_M)),
        'vertical_datum': 'EGM2008 geoid',
        'horizontal_crs': 'WGS84 geographic (EPSG:4326)',
        'units': 'meters',
        'dtype': 'int16 little-endian',
        'nlat': int(grid.shape[0]),
        'nlon': int(OUT_NLON),
        'lat0_deg': -90.0 + 0.5 / 12.0,
        'lon0_deg': -180.0 + 0.5 / 12.0,
        'dlat_deg': 1.0 / 12.0,
        'dlon_deg': 1.0 / 12.0,
        'row_order': 'south_to_north',
        'col_order': 'west_to_east',
        'fill_policy': '_FillValue (-99999) -> 0 m',
        'binary_file': BIN_NAME,
        'raw_bytes': len(payload),
        'gz_bytes': bin_path.stat().st_size,
    }
    (OUT_DIR / META_NAME).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Yazıldı: %s (%.2f MB gzip, %.2f MB ham)'
          % (bin_path, meta['gz_bytes'] / 1e6, meta['raw_bytes'] / 1e6))
    return meta


def requantize_existing() -> None:
    """Mevcut dosyayı yeniden indirmeden nicemler (idempotent)."""
    meta = json.loads((OUT_DIR / META_NAME).read_text(encoding='utf-8'))
    with gzip.open(OUT_DIR / meta['binary_file'], 'rb') as fh:
        raw = fh.read()
    grid = np.frombuffer(raw, dtype='<i2').reshape(
        int(meta['nlat']), int(meta['nlon'])).copy()
    _write(grid)


def build(max_rows: int | None = None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_needed = OUT_NLAT if max_rows is None else min(max_rows, OUT_NLAT)
    grid = np.zeros((rows_needed, OUT_NLON), dtype=np.int16)

    band_rows = 120                    # çıktı satırı / istek
    done = 0
    t0 = time.time()
    while done < rows_needed:
        take = min(band_rows, rows_needed - done)
        src_start = OFFSET + done * STRIDE
        band = _fetch_band(src_start, take)
        band[band <= FILL_VALUE + 1.0] = 0.0     # dolgu değeri -> 0 m
        np.clip(band, -32000.0, 32000.0, out=band)
        grid[done:done + take, :] = np.rint(band).astype(np.int16)
        done += take
        el = time.time() - t0
        print('  %5d / %d satır  (%.0f s, kalan ~%.0f s)'
              % (done, rows_needed, el, el / done * (rows_needed - done)),
              flush=True)

    _write(grid)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rows', type=int, default=None,
                    help='yalnız ilk N çıktı satırı (duman testi)')
    ap.add_argument('--requantize', action='store_true',
                    help='indirme yapmadan mevcut dosyayı yeniden nicemle')
    args = ap.parse_args()
    if args.requantize:
        requantize_existing()
    else:
        build(args.rows)
    sys.exit(0)
