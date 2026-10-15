#!/usr/bin/env python3
"""Paketli Blue Marble karo piramidi (harita-detay K4 / F2; tasarım §2.2, §3.4).

NASA Blue Marble Next Generation topografya + batimetri, Aralık 2004
(``world.topo.bathy.200412.3x21600x10800.jpg``, 0,016667°/px ≈ 1,85 km;
Reto Stöckli, NASA Earth Observatory) GIBS EPSG:4326 ızgarasında z0-z5
WebP karolarına bölünür ve uygulamayla birlikte gelir. Çalışma anında AĞ
YOKTUR: ``tile_cache`` bu karoları ``'bm_local'`` katmanından, diskten verir.

Izgara: karo 512 px, açıklık ``tile_cache.tile_span_deg(z) = 288/2**z``,
matris ``tile_cache.matrix_size(z)``, kutu ``tile_cache.tile_to_bbox`` —
geometri TEK sahibinden içe aktarılır (kopya yok). z5'te 0,017578°/px
(ekvatorda ~1,96 km); kaynak 0,016667°/px, yani en ince düzey bile hafif
KÜÇÜLTMEDİR: kaynakta olmayan ayrıntı üretilmez, daha ince z ÜRETİLMEZ.

Dünya dışı alan: GIBS matrisi z <= 2'de Dünya'dan taşar (z0 2x1 karo x
288°). Taşan bölge görüntü DEĞİLDİR; RGBA karoda saydam (alfa 0) bırakılır
ve künyede yazılır. Ön yüz bu düzeyleri istemez (en kaba istek z4).

Belirlenimcilik: her karo, kaynağın tamamından ``Image.resize(box=...)``
ile Lanczos yeniden örneklenir (şerit sınırı yok); WebP kodlayıcı ayarları
sabittir. Aynı girdi + aynı Pillow/libwebp -> aynı bayt (sürümler
künyededir).

Kaynak kanıtı: dosyanın sha256'sı ``KAYNAK_SHA256`` ile birebir tutmalı,
boyutu ``KAYNAK_BOYUT`` olmalı; tutmazsa HİÇBİR DOSYA YAZILMAZ.
Boyut bütçesi: toplam ``PIRAMIT_BUTCESI_BAYT``; aşılırsa HİÇBİR DOSYA
YAZILMAZ (çıkış kodu 2), ``--max-zoom`` ile daha kaba bir tavan seçilir
(karar ana modelde).

Kullanım:
    python3 tools/build_bm_pyramid.py [--kaynak YOL] [--max-zoom 5] [--olcum]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hrma.analysis.tile_cache import (  # noqa: E402  (tek sahip)
    EQUATOR_M_PER_DEG, PACKAGED_LAYER_KEY, LAYERS, WORLD_LAT_N, WORLD_LAT_S,
    WORLD_LON_E, WORLD_LON_W, matrix_size, packaged_root, tile_span_deg)

#: Varsayılan kaynak (depo dışı yapım önbelleği; indirme izni 7 Eki 2026).
VARSAYILAN_KAYNAK = Path('/Users/apple/HRMA-kaynaklar/harita/nasa/'
                         'world.topo.bathy.200412.3x21600x10800.jpg')
KAYNAK_ADI = 'world.topo.bathy.200412.3x21600x10800.jpg'
KAYNAK_URL = ('https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/'
              + KAYNAK_ADI)
#: HRMA-kaynaklar/harita/SHA256SUMS.txt kaydı (7 Eki 2026 indirmesi).
KAYNAK_SHA256 = '3006c58b1272362db0a8c2df02dc07cea4b12dfe820b7dc4a159a075caf5d4d4'
KAYNAK_BOYUT = (21600, 10800)
KAYNAK_KUNYE = {
    'product': 'NASA Blue Marble Next Generation, topography and bathymetry',
    'month': '2004-12',
    'author': 'Reto Stöckli, NASA Earth Observatory',
    'license': ('NASA imagery; no copyright unless noted (NASA Media Usage '
                'Guidelines); attribution expected'),
    'url': KAYNAK_URL,
}

KARO_PX = 512
#: Paket bütçesi (tasarım §5.1: z0-z5 ~30-45 MB tahmini; ana model 45 MB).
PIRAMIT_BUTCESI_BAYT = 45_000_000
#: WebP kodlayıcı (lossy). Değiştirmek bütün sha256'ları değiştirir.
WEBP_KALITE = 80
WEBP_YONTEM = 6
BICIM = 'HRMA-BMPYR-1'


class KaynakHatasi(RuntimeError):
    """Kaynak kanıtı tutmadı (sha256 / boyut) — hiçbir dosya yazılmadı."""


class ButceAsildi(RuntimeError):
    """Toplam bayt bütçeyi aştı — hiçbir dosya yazılmadı."""


def sha256_dosya(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, 'rb') as fh:
        for parca in iter(lambda: fh.read(1 << 20), b''):
            h.update(parca)
    return h.hexdigest()


def kaynak_ac(yol: Path, beklenen_sha: str = KAYNAK_SHA256,
              beklenen_boyut=KAYNAK_BOYUT):
    """Kaynağı KANITLA aç: sha256 ve piksel boyutu tutmazsa yükselt.

    Pillow'un açılış bombası sınırı yalnız kanıtı tutan dosya için ve
    yalnız o dosyanın piksel sayısına açılır (genel sınır gevşetilmez).
    """
    from PIL import Image
    yol = Path(yol)
    if not yol.is_file():
        raise KaynakHatasi('kaynak yok: %s' % yol)
    sha = sha256_dosya(yol)
    if sha != beklenen_sha:
        raise KaynakHatasi('kaynak sha256 tutmadı: %s (beklenen %s)'
                           % (sha, beklenen_sha))
    eski = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = beklenen_boyut[0] * beklenen_boyut[1]
    try:
        img = Image.open(yol)
        if img.size != tuple(beklenen_boyut):
            raise KaynakHatasi('kaynak boyutu %s, beklenen %s'
                               % (img.size, beklenen_boyut))
        img = img.convert('RGB')
    finally:
        Image.MAX_IMAGE_PIXELS = eski
    return img, sha


def karo_uret(img, z: int, x: int, y: int):
    """Tek karo (PIL görüntüsü). Kaynak tüm Dünya'yı eşdikdörtgen kaplar.

    Karonun Dünya içindeki kısmı kaynakta ``box`` ile seçilir ve o kısmın
    piksel boyutuna Lanczos ile yeniden örneklenir; Dünya dışı kısım
    saydam kalır (yalnız z <= 2).
    """
    from PIL import Image
    span = tile_span_deg(z)
    lon_w = WORLD_LON_W + x * span
    lat_n = WORLD_LAT_N - y * span
    lon_e, lat_s = lon_w + span, lat_n - span
    # Dünya ile kesişim (derece)
    k_w, k_e = max(lon_w, WORLD_LON_W), min(lon_e, WORLD_LON_E)
    k_n, k_s = min(lat_n, WORLD_LAT_N), max(lat_s, WORLD_LAT_S)
    px_derece = KARO_PX / span
    # Karo içindeki piksel aralığı (z >= 3'te tam karo; tamsayıya oturur)
    hx0 = round((k_w - lon_w) * px_derece)
    hx1 = round((k_e - lon_w) * px_derece)
    hy0 = round((lat_n - k_n) * px_derece)
    hy1 = round((lat_n - k_s) * px_derece)
    sw, sh = img.size
    kutu = ((k_w - WORLD_LON_W) / 360.0 * sw, (WORLD_LAT_N - k_n) / 180.0 * sh,
            (k_e - WORLD_LON_W) / 360.0 * sw, (WORLD_LAT_N - k_s) / 180.0 * sh)
    parca = img.resize((hx1 - hx0, hy1 - hy0), Image.LANCZOS, box=kutu)
    if (hx0, hy0, hx1, hy1) == (0, 0, KARO_PX, KARO_PX):
        return parca
    karo = Image.new('RGBA', (KARO_PX, KARO_PX), (0, 0, 0, 0))
    karo.paste(parca.convert('RGBA'), (hx0, hy0))
    return karo


def webp_bayt(karo) -> bytes:
    tampon = io.BytesIO()
    karo.save(tampon, 'WEBP', quality=WEBP_KALITE, method=WEBP_YONTEM,
              exact=False)
    return tampon.getvalue()


def uret(img, kaynak_sha: str, max_zoom: int, butce: int = PIRAMIT_BUTCESI_BAYT,
         ilerleme=None):
    """Bellekte üret: (dosyalar {göreli_yol: bayt}, manifest). Yazmaz."""
    from PIL import __version__ as pil_surum
    from PIL import features
    katman = LAYERS[PACKAGED_LAYER_KEY]
    if not (0 <= max_zoom <= int(katman['max_zoom'])):
        raise ValueError('max_zoom 0..%d olmalı' % katman['max_zoom'])
    dosyalar, kayit, duzeyler, toplam = {}, {}, {}, 0
    for z in range(max_zoom + 1):
        mw, mh = matrix_size(z)
        span = tile_span_deg(z)
        dz_bayt = 0
        for y in range(mh):
            for x in range(mw):
                veri = webp_bayt(karo_uret(img, z, x, y))
                yol = '%d/%d/%d.webp' % (z, x, y)
                dosyalar[yol] = veri
                kayit[yol] = {'sha256': hashlib.sha256(veri).hexdigest(),
                              'bytes': len(veri)}
                dz_bayt += len(veri)
            if ilerleme:
                ilerleme(z, y, mh)
        toplam += dz_bayt
        duzeyler[str(z)] = {
            'matrix_width': mw, 'matrix_height': mh, 'tiles': mw * mh,
            'span_deg': span, 'deg_per_px': span / KARO_PX,
            'm_per_px_equator': round(span / KARO_PX * EQUATOR_M_PER_DEG, 1),
            'bytes': dz_bayt,
            'out_of_world': 'transparent' if z <= 2 else None,
        }
    manifest = {
        'format': BICIM,
        'layer': PACKAGED_LAYER_KEY,
        'source': dict(KAYNAK_KUNYE, file=KAYNAK_ADI, sha256=kaynak_sha,
                       size_px=list(img.size)),
        'grid': {
            'basis': ('GIBS WMTS EPSG:4326 (CRS84) geometry from '
                      'hrma.analysis.tile_cache (tile_span_deg = 288/2**z, '
                      'matrix_size, TopLeftCorner -180,+90); path z/x/y'),
            'tile_px': KARO_PX, 'min_zoom': 0, 'max_zoom': max_zoom,
        },
        'resample': 'Pillow LANCZOS, per tile from the full source (box)',
        'encoding': {'format': 'webp', 'quality': WEBP_KALITE,
                     'method': WEBP_YONTEM, 'pillow': pil_surum,
                     'libwebp': features.version('webp')},
        'levels': duzeyler,
        'files': kayit,
        'total_bytes': toplam,
        'budget_bytes': butce,
    }
    if toplam > butce:
        raise ButceAsildi('toplam %d B > bütçe %d B (max_zoom %d)'
                          % (toplam, butce, max_zoom))
    return dosyalar, manifest


def yaz(dosyalar: dict, manifest: dict, hedef: Path) -> None:
    """Atomik yazım: geçici dizinde kur, eski dizinin yerine koy."""
    hedef = Path(hedef)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = Path(tempfile.mkdtemp(prefix='.bm_pyr_', dir=str(hedef.parent)))
    try:
        for yol, veri in dosyalar.items():
            d = gecici / yol
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_bytes(veri)
        (gecici / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True)
            + '\n', encoding='utf-8')
        if hedef.exists():
            eski = Path(str(hedef) + '.eski')
            if eski.exists():
                shutil.rmtree(eski)
            os.replace(hedef, eski)
            os.replace(gecici, hedef)
            shutil.rmtree(eski)
        else:
            os.replace(gecici, hedef)
    finally:
        if gecici.exists():
            shutil.rmtree(gecici)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--kaynak', default=str(VARSAYILAN_KAYNAK))
    ap.add_argument('--max-zoom', type=int,
                    default=int(LAYERS[PACKAGED_LAYER_KEY]['max_zoom']))
    ap.add_argument('--hedef', default=str(packaged_root()))
    ap.add_argument('--olcum', action='store_true',
                    help='yalnız ölç ve özetle; dosya yazma')
    a = ap.parse_args(argv)
    try:
        img, sha = kaynak_ac(Path(a.kaynak))
    except KaynakHatasi as e:
        print('KAYNAK REDDEDİLDİ: %s' % e, file=sys.stderr)
        return 3

    def ilerleme(z, y, mh):
        if y == mh - 1:
            print('  z%d bitti' % z, flush=True)
    try:
        dosyalar, manifest = uret(img, sha, a.max_zoom, ilerleme=ilerleme)
    except ButceAsildi as e:
        print('BÜTÇE AŞILDI, hiçbir dosya yazılmadı: %s' % e, file=sys.stderr)
        return 2
    print('toplam %d karo, %d B (bütçe %d B)'
          % (len(dosyalar), manifest['total_bytes'], manifest['budget_bytes']))
    for z, d in manifest['levels'].items():
        print('  z%s: %d karo, %d B, %.1f m/px' % (z, d['tiles'], d['bytes'],
                                                  d['m_per_px_equator']))
    if a.olcum:
        return 0
    yaz(dosyalar, manifest, Path(a.hedef))
    print('yazıldı: %s' % a.hedef)
    return 0


if __name__ == '__main__':
    sys.exit(main())
