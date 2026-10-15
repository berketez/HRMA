#!/usr/bin/env python3
"""Fırlatma sahası küresinin yakın zoom vektör ve etiket varlıklarını üretir (F1).

Tasarım: ``docs/scofield/raw/OH/UI/harita-detay/tasarim.md`` §2.1, §3.2, §3.3,
§5.1, §6 (K1 satırı). Karar §28-20 (Berke, 7 Eki 2026).

AĞ YOK. Bu betik internete çıkmaz. Ham Natural Earth GeoJSON dosyaları depo
DIŞINDA, ``/Users/apple/HRMA-kaynaklar/harita/ne_v5.1.2/`` altında durur
(ana model Berke izniyle indirdi; ``SHA256SUMS.txt`` ve ``KAYNAK.txt`` aynı
yerde). Betik her dosyanın sha256'sını o listeyle KARŞILAŞTIRIR; tutmayan,
listede olmayan ya da GeoJSON imzası taşımayan dosyadan varlık ÜRETİLMEZ
(fail-closed). Ham dosyalar depoya kopyalanmaz; depoya yalnız aşağıdaki
küçük, türetilmiş dosyalar girer.

Üretilenler (``hrma/static/map/``)
---------------------------------
1) ``vectors_110m.bin``, ``vectors_50m.bin``, ``vectors_10m.bin``
   Çizgi katmanları, ikili, little-endian. Biçim (``HMV1``):

     ofset  tip            alan
     0      4 bayt         sihirli imza b'HMV1'
     4      uint32         blok sayısı
     8      uint32         toplam köşe sayısı
     12     uint32         toplam çizgi sayısı
     16     bloklar        her blok 4 bayta hizalı, sırası manifestte:
              int32[2*nv]  köşeler: [lon*1e5, lat*1e5] çiftleri (1e-5° ≈ 1,1 m)
              uint32[nl]   her çizginin köşe sayısı (sırayla)
              uint8[nl]    her çizginin kaynak ``min_zoom`` değeri *10
                           (yuvarlanmış); 255 = kaynakta alan yok
              0..3 bayt    dolgu (sonraki blok 4 bayta hizalansın)

   Bir blok = (katman, hücre). Hücre ızgarası GIBS EPSG:4326 z3 karo
   matrisidir (36°, 10x5); sayı ``hrma.analysis.tile_cache``'ten OKUNUR,
   burada türetilmez (P5B4-30: geometrinin tek sahibi). Bir çizgi hücre
   değiştirdiğinde iki parçaya bölünür; ilk parça yeni hücredeki İLK köşeyle
   biter, ikinci parça o köşeden başlar. Yeni köşe ÜRETİLMEZ (kesişim noktası
   enterpolasyonu yok), hiçbir parça iki kez çizilmez. Bu yüzden bir bloğun
   kutusu hücresinden bir köşe kadar taşabilir; kutu manifestte GERÇEK
   köşelerden ölçülmüş olarak durur, istemci türetmez.

   110m basamağı, depodaki mevcut ``hrma/static/img/earth_borders.json``
   dosyasından (NE 1:110m, ``master`` dalından, 2 ondalık) AYNI biçime
   çevrilir. İndirme seti 110m GeoJSON içermiyor; o dosyanın künyesi ve
   sha256'sı manifestte durur. ``earth_borders.json`` SİLİNMEZ (yedek katman).

2) ``vectors_manifest.json``
   Biçim tanımı, hücre ızgarası, her blok için (ofset, köşe, çizgi, kutu),
   kaynak künyesi (sürüm, sha256, lisans), sayımlar ve boyut bütçesi.

3) ``places.json``
   ``ne_10m_populated_places``'tan süzülmüş öznitelikler: konum, NAME,
   NAME_EN, NAME_TR, MIN_ZOOM, LABELRANK, FEATURECLA, ADM0_A3. Kayıtlar
   öncelik sırasında yazılır (başkent > LABELRANK küçük > POP_MAX büyük);
   POP_MAX yalnız sıralamada kullanılır ve DOSYAYA YAZILMAZ (tasarım §5.3-4:
   yılı belirsiz nüfus sayısı basılmaz).

4) ``country_labels.json``
   ``ne_10m_admin_0_countries``'in (sınır görünümü ``SINIR_GORUNUMU``)
   etiket noktaları: LABEL_X/LABEL_Y, NAME, NAME_EN, NAME_TR, MIN_LABEL,
   MAX_LABEL, LABELRANK, ADM0_A3. Poligonlar atılır.

   3) ve 4)'te adlar ham NE'dir; YALNIZ ``AD_DUZELTMELERI`` tablosundaki
   satırlar (karar §28-45) değişir. Tablo ESKİ değeri ham NE'de bulamazsa
   üretim durur; uygulanan her satır varlığın künyesine yazılır.

Boyut bütçesi: üretilen dosyaların toplamı ``BOYUT_BUTCESI_BAYT``'ı aşarsa
betik HİÇBİR DOSYA YAZMADAN durur ve ölçümü basar (tasarım §5.1, §7).

Çıktı belirlenimcidir: aynı kaynaktan iki koşu bayt bayt aynı dosyaları
verir (zaman damgası yazılmaz; künye kaynağın sha256'sına dayanır).

Kullanım::

    python3 tools/build_map_detail_assets.py            # üret
    python3 tools/build_map_detail_assets.py --olcum    # yalnız ölç, yazma
    python3 tools/build_map_detail_assets.py --kaynak DIZIN --cikti DIZIN
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, NamedTuple, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
for _yol in (str(REPO), str(TOOLS)):
    if _yol not in sys.path:
        sys.path.insert(0, _yol)

from hrma.analysis import tile_cache  # noqa: E402  (hücre ızgarasının tek sahibi)
# İndirme kanıtı sözleşmesi tek yerde yaşar (P10B4-17): GeoJSON imzası ve
# "veri değil hata sayfası" alt sınırı mevcut varlık aracından alınır.
from build_launch_site_assets import JSON_IMZA, NE_EN_AZ_BAYT  # noqa: E402

# ---------------------------------------------------------------------------
# Kaynak ve sürüm
# ---------------------------------------------------------------------------
#: Natural Earth etiketli sürümü (tasarım §2.1: ``master`` KULLANILMAZ).
NE_SURUM = 'v5.1.2'
NE_DEPO = 'https://github.com/nvkelso/natural-earth-vector'
NE_LISANS = 'Public domain (Natural Earth Terms of Use)'
NE_ATIF = 'Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.'

#: Varsayılan ham veri kökü (depo DIŞI). ``HRMA_HARITA_KAYNAK`` ya da
#: ``--kaynak`` ile değiştirilebilir.
VARSAYILAN_KAYNAK = Path(os.environ.get('HRMA_HARITA_KAYNAK',
                                        '/Users/apple/HRMA-kaynaklar/harita'))
SHA_LISTESI = 'SHA256SUMS.txt'
NE_ALT_DIZIN = 'ne_%s' % NE_SURUM

#: Tartışmalı sınırlar için ülke katmanının bakış açısı (§28-20, tasarım
#: §4.4-3). Berke'nin kararı gelene kadar Natural Earth VARSAYILAN (de facto)
#: görünümü. Değiştirmek için YALNIZ bu sabit değişir; ``tur`` dosyası indirme
#: setinde var ama bugün KULLANILMAZ. Not: sınır ÇİZGİLERİ
#: (``admin_0_boundary_lines_land``) indirme setinde yalnız varsayılan
#: görünümde var; bu sabit ülke etiket noktalarını seçer.
SINIR_GORUNUMU = 'varsayilan'
SINIR_GORUNUMU_DOSYALARI = {
    'varsayilan': 'ne_10m_admin_0_countries.geojson',
    'tur': 'ne_10m_admin_0_countries_tur.geojson',
}

#: Mevcut 110m varlığı (yedek katman; silinmez).
ESKI_110M = REPO / 'hrma' / 'static' / 'img' / 'earth_borders.json'

CIKTI_DIZIN = REPO / 'hrma' / 'static' / 'map'

# ---------------------------------------------------------------------------
# Biçim sabitleri
# ---------------------------------------------------------------------------
SIHIRLI = b'HMV1'
HMV1_BASLIK_BAYT = 16
#: 1e-5° nicemleme (tasarım §3.2). 10m verisinin ölçeğinin çok altında.
KOORDINAT_OLCEGI = 100_000
#: ``min_zoom`` kodlaması: uint8 = round(min_zoom * 10); 255 = alan yok.
MIN_ZOOM_OLCEGI = 10
MIN_ZOOM_YOK = 255
#: Hücre ızgarasının GIBS karo düzeyi (tasarım §3.2: 36°, z3, 10x5).
HUCRE_Z = 3
#: Yer kayıtlarının koordinat ondalığı (1e-5° = vektörlerle aynı nicemleme).
YER_ONDALIK = 5
#: Boyut bütçesi (tasarım §5.1, §6 K1). İlk değer 12 MB idi; ölçülen yük
#: 12 670 751 B çıktı ve araç fail-closed hiçbir dosya yazmadı (F1 denetimi,
#: 12 Eki). Karar §28-43 (Berke 12 Eki: "12,67 MB çıkmış, ekle onları"): 13 MB.
#: MB = 10^6 bayt (projedeki ``/ 1e6`` geleneği). Aşılırsa HİÇ yazılmaz.
BOYUT_BUTCESI_BAYT = 13_000_000

#: Başkent önceliği (tasarım §3.3-4: FEATURECLA "Admin-0 capital").
BASKENT_SINIFI = 'Admin-0 capital'
#: Türkiye il merkezi sayımı için sınıflar ve ülke kodu (tasarım §5.2).
IL_MERKEZI_SINIFLARI = ('Admin-0 capital', 'Admin-1 capital')
TURKIYE_A3 = 'TUR'
TURKIYE_IL_SAYISI = 81

#: Basamak -> katman -> kaynak dosya. Katman sırası blok sırasını belirler.
BASAMAKLAR: Dict[str, Dict[str, str]] = {
    '50m': {
        'coastline': 'ne_50m_coastline.geojson',
        'borders': 'ne_50m_admin_0_boundary_lines_land.geojson',
        'lakes': 'ne_50m_lakes.geojson',
        'rivers': 'ne_50m_rivers_lake_centerlines.geojson',
    },
    '10m': {
        'coastline': 'ne_10m_coastline.geojson',
        'borders': 'ne_10m_admin_0_boundary_lines_land.geojson',
        'admin1': 'ne_10m_admin_1_states_provinces_lines.geojson',
        'lakes': 'ne_10m_lakes.geojson',
        'rivers': 'ne_10m_rivers_lake_centerlines.geojson',
    },
}
#: 110m katmanları ``earth_borders.json`` içindeki anahtarlardan gelir.
ESKI_110M_KATMANLARI = {'coastline': 'coastline', 'borders': 'borders'}

# ---------------------------------------------------------------------------
# Sınır düzeltmeleri (karar §28-45/Kırım, Berke 13 Eki 2026: "Kırım Kırım işte")
# ---------------------------------------------------------------------------
# Türkiye'nin resmî görüşü: Kırım Ukrayna'dır. NE varsayılan (de facto)
# görünümü Perekop kıstağına bir 'Disputed (please verify)' Rusya-Ukrayna
# çizgisi koyar; o çizgi bu tabloyla künyeli düşülür. Başka hiçbir çizgi
# değişmez. NE'nin kendi Türkiye bakışı da bu çizgiyi uluslararası sınır
# saymaz (ölçüldü: aynı kaydın FCLASS_TR = 'Admin-1 boundary').
#
# Sözleşme (fail-closed, ``AdDuzeltmesi`` ile aynı ruh):
#  - Aday: bütün köşeleri kutunun İÇİNDE kalan her çizgi YA DA FEATURECLA
#    tartışmalı ve ülke çifti {RUS, UKR} olan her çizgi. Her aday tablonun
#    satırına tam uymalı: NE kimliği, FEATURECLA, BRK_A3, bütün köşeler
#    kutuda; ülke çifti alanları varsa {RUS, UKR} (50m'de bu alanlar YOK,
#    çift aynı NE kimliğinin 10m kaydından gelir). Uymazsa üretim durur.
#  - Kaynağın sha256'sı tablonun doğrulandığı dosyanınkiyle aynıysa beklenen
#    eşleşme sayısı ZORUNLUDUR (``SinirDuzeltmesi.beklenen``); tutmazsa
#    üretim HİÇBİR DOSYA YAZMADAN durur. Başka kaynakta (test fixture'ı)
#    aday yoksa satır 'not_applied' altında adıyla beyan edilir.
#  - Düşülen her çizgi manifestin künyesine yazılır.

#: Düzeltmenin kararı (künye).
SINIR_DUZELTMESI_KARARI = "Türkiye'nin resmî görüşü (karar §28-45/Kırım)"
#: Düzeltme uygulanmış manifestin dürüst kaynak eki.
SINIR_DUZELTMESI_KAYNAK_EKI = 'HRMA sınır düzeltmesi, karar §28-45/Kırım'
#: Perekop kıstağı kutusu: (boylam en az, boylam en çok, enlem en az, enlem en çok).
PEREKOP_KUTUSU = (33.3, 35.4, 45.6, 46.4)
#: NE'nin tartışmalı sınır sınıfı.
TARTISMALI_SINIF = 'Disputed (please verify)'
#: Perekop çizgisinin NE ülke çifti (10m ADM0_A3_L / ADM0_A3_R), sıralı.
KIRIM_ULKE_CIFTI = ('RUS', 'UKR')
#: Tablonun satır satır doğrulandığı ham dosyalar (sha256, ``SHA256SUMS.txt``).
SINIR_DUZELTMESI_KAYNAK_SHA = {
    'ne_10m_admin_0_boundary_lines_land.geojson':
        '74d9c16229c095fde65943a9919e337682f044bcebccb120764f38edf3b70f4a',
    'ne_50m_admin_0_boundary_lines_land.geojson':
        '2faac4f6b34386f3d21b6e018cf151f241f00e5c936d44dd17d7d9bfb147fa48',
}


class SinirDuzeltmesi(NamedTuple):
    """Tek sınır düzeltme satırı (karar §28-45/Kırım): çizgi düşülür."""
    dosya: str                      # ham NE sınır dosyası
    ne_id: int                      # NE kararlı kimliği (10m 'ne_id', 50m 'NE_ID')
    featurecla: str
    brk_a3: str
    ulke_cifti: Tuple[str, str]     # sıralı; 50m'de alan yok, 10m'den gelir
    kutu: Tuple[float, float, float, float]
    beklenen: int                   # doğrulanan kaynakta zorunlu eşleşme sayısı
    kunye: str


_PEREKOP = ("Perekop kıstağı 'Disputed (please verify)' Rusya-Ukrayna çizgisi; "
            "Türkiye'nin resmî görüşü: Kırım Ukrayna'dır. NE'nin kendi Türkiye "
            "bakışında da bu kayıt 'Admin-1 boundary' (FCLASS_TR)")

SINIR_DUZELTMELERI: Tuple[SinirDuzeltmesi, ...] = (
    SinirDuzeltmesi('ne_10m_admin_0_boundary_lines_land.geojson', 1746708787,
                    TARTISMALI_SINIF, 'B89', KIRIM_ULKE_CIFTI, PEREKOP_KUTUSU, 1,
                    _PEREKOP),
    SinirDuzeltmesi('ne_50m_admin_0_boundary_lines_land.geojson', 1746708787,
                    TARTISMALI_SINIF, 'B89', KIRIM_ULKE_CIFTI, PEREKOP_KUTUSU, 1,
                    _PEREKOP + '; 50m kaydında ülke çifti alanı yok, çift aynı '
                    'NE kimliğinin 10m kaydından'),
)

#: Eski 110m yedek katmanından (``earth_borders.json``, özniteliksiz) aynı
#: karar için bayt düzeyinde düşülen çizgi. Dosya künye alanı taşımadığı için
#: künye burada ve manifestte durur. Ölçüm: borders[181], 6 nokta, hepsi
#: Perekop kutusunda; kutudaki TEK sınır çizgisi; 10m çizgisinin her köşesi
#: buna en çok 0,047° (50m: 0,039°) uzak. Ham 110m NE kaynağı indirme
#: setinde yok, o yüzden öznitelikle eşlenemedi. Üretici bu dosyada kutunun
#: içinde kalan bir sınır çizgisi bulursa durur (``eski_110m_sinir_denetimi``).
ESKI_110M_SINIR_DUZELTMESI = {
    'decision': SINIR_DUZELTMESI_KARARI,
    'removed_from': 'hrma/static/img/earth_borders.json',
    'layer': 'borders',
    'index_before': 181,
    'points': [[33.44, 45.97], [33.7, 46.22], [34.41, 46.01], [34.73, 45.97],
               [34.86, 45.77], [35.01, 45.74]],
    'point_count_before': 8119,
    'point_count_after': 8113,
    'sha256_before': '93cbab80a1b504c4e7ffaf0a6deda339b4a7cb77feb3a1041d2233ab65cb1f89',
    'sha256_after': '5573bf64942355192392b9adcbe4c3faf80acbee466e122cd73ca1ad31d37c2f',
    'note': ('the only borders line lying wholly inside the Perekop box; every '
             'vertex of the 10m Natural Earth Perekop line is within 0.047 deg '
             'of it. No other byte of the file changed.'),
}
BASAMAK_SIRASI = ('110m', '50m', '10m')
YERLER_DOSYASI = 'ne_10m_populated_places.geojson'


class ButceAsildi(RuntimeError):
    """Üretilen toplam, boyut bütçesini aştı; hiçbir dosya yazılmadı."""


class KaynakHatasi(RuntimeError):
    """Kaynak dosya kanıtı tutmadı (sha256, imza ya da en az bayt)."""


# ---------------------------------------------------------------------------
# Kaynak doğrulama
# ---------------------------------------------------------------------------

def sha256_dosya(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, 'rb') as f:
        for parca in iter(lambda: f.read(1 << 20), b''):
            h.update(parca)
    return h.hexdigest()


def sha_listesini_oku(kok: Path) -> Dict[str, str]:
    """``SHA256SUMS.txt`` -> {göreli yol: sha256}. Dosya yoksa KaynakHatasi."""
    yol = kok / SHA_LISTESI
    if not yol.is_file():
        raise KaynakHatasi('%s yok; kaynak kanıtı olmadan üretim yapılmaz' % yol)
    liste = {}
    for satir in yol.read_text(encoding='utf-8').splitlines():
        satir = satir.strip()
        if not satir:
            continue
        ozet, _, ad = satir.partition('  ')
        if len(ozet) != 64 or not ad:
            raise KaynakHatasi('%s içinde biçimsiz satır: %r' % (yol, satir))
        liste[ad.strip()] = ozet.lower()
    return liste


def kaynak_dogrula(kok: Path, ad: str, liste: Dict[str, str]) -> Tuple[Path, str]:
    """NE dosyasını sha256, en az bayt ve GeoJSON imzasıyla doğrular."""
    goreli = '%s/%s' % (NE_ALT_DIZIN, ad)
    yol = kok / goreli
    if goreli not in liste:
        raise KaynakHatasi('%s SHA256SUMS listesinde yok' % goreli)
    if not yol.is_file():
        raise KaynakHatasi('%s bulunamadı' % yol)
    boyut = yol.stat().st_size
    if boyut < NE_EN_AZ_BAYT:
        raise KaynakHatasi('%s yalnız %d bayt (en az %d); veri değil'
                           % (yol, boyut, NE_EN_AZ_BAYT))
    with open(yol, 'rb') as f:
        bas = f.read(64).lstrip()
    if not bas.startswith(JSON_IMZA):
        raise KaynakHatasi('%s GeoJSON imzası taşımıyor (ilk baytlar %r)'
                           % (yol, bas[:8]))
    ozet = sha256_dosya(yol)
    if ozet != liste[goreli]:
        raise KaynakHatasi('%s sha256 tutmadı: %s != %s'
                           % (goreli, ozet, liste[goreli]))
    return yol, ozet


# ---------------------------------------------------------------------------
# Geometri
# ---------------------------------------------------------------------------

def nicemle(deger: float) -> int:
    return int(round(float(deger) * KOORDINAT_OLCEGI))


def cizgileri_ayikla(geometri: Optional[dict]) -> Iterator[Sequence]:
    """GeoJSON geometrisinden çizgi dizilerini verir (poligon halkası = çizgi)."""
    if not geometri:
        return
    tur = geometri.get('type')
    koord = geometri.get('coordinates') or []
    if tur == 'LineString':
        yield koord
    elif tur == 'MultiLineString':
        yield from koord
    elif tur == 'Polygon':
        yield from koord
    elif tur == 'MultiPolygon':
        for poligon in koord:
            yield from poligon


def min_zoom_kodla(ozellik: dict) -> int:
    for anahtar in ('min_zoom', 'MIN_ZOOM'):
        if anahtar in ozellik and ozellik[anahtar] is not None:
            deger = int(round(float(ozellik[anahtar]) * MIN_ZOOM_OLCEGI))
            if not 0 <= deger < MIN_ZOOM_YOK:
                raise ValueError('min_zoom kodlanamıyor: %r' % ozellik[anahtar])
            return deger
    return MIN_ZOOM_YOK


def hucre(lon_q: int, lat_q: int) -> Tuple[int, int]:
    """Nicemlenmiş köşenin GIBS z3 karo hücresi (tile_cache sahibi)."""
    return tile_cache.lonlat_to_tile(HUCRE_Z, lon_q / KOORDINAT_OLCEGI,
                                     lat_q / KOORDINAT_OLCEGI)


def cizgiyi_hucrelere_bol(noktalar: Sequence[Tuple[int, int]]
                          ) -> List[Tuple[Tuple[int, int], List[Tuple[int, int]]]]:
    """Nicemlenmiş çizgiyi hücre değişimlerinde parçalara böler.

    Parça, yeni hücredeki ilk köşeyle biter; sonraki parça o köşeden başlar.
    Yeni köşe üretilmez, her kesim (segment) tam bir parçada bulunur.
    """
    if len(noktalar) < 2:
        return []
    parcalar = []
    simdiki = hucre(*noktalar[0])
    parca = [noktalar[0]]
    for nokta in noktalar[1:]:
        h = hucre(*nokta)
        parca.append(nokta)
        if h != simdiki:
            parcalar.append((simdiki, parca))
            simdiki = h
            parca = [nokta]
    if len(parca) >= 2:
        parcalar.append((simdiki, parca))
    return parcalar


class KatmanToplayici:
    """Bir katmanın çizgilerini hücre bloklarına toplar."""

    def __init__(self) -> None:
        self.bloklar: Dict[Tuple[int, int], dict] = {}
        self.kaynak_cizgi = 0
        self.kaynak_kose = 0
        self.atilan_tekrar = 0
        self.atilan_kisa = 0
        self.geometrisiz = 0
        self.min_zoom_yok = 0

    def ekle(self, koordinatlar: Iterable, mz: int) -> None:
        self.kaynak_cizgi += 1
        noktalar: List[Tuple[int, int]] = []
        onceki = None
        for k in koordinatlar:
            self.kaynak_kose += 1
            q = (nicemle(k[0]), nicemle(k[1]))
            if q == onceki:
                self.atilan_tekrar += 1
                continue
            noktalar.append(q)
            onceki = q
        if len(noktalar) < 2:
            self.atilan_kisa += 1
            return
        if mz == MIN_ZOOM_YOK:
            self.min_zoom_yok += 1
        for h, parca in cizgiyi_hucrelere_bol(noktalar):
            blok = self.bloklar.setdefault(h, {'koseler': [], 'uzunluklar': [],
                                               'min_zoom': []})
            for lon_q, lat_q in parca:
                blok['koseler'].append(lon_q)
                blok['koseler'].append(lat_q)
            blok['uzunluklar'].append(len(parca))
            blok['min_zoom'].append(mz)


def _kutuda(koseler: Sequence, kutu: Tuple[float, float, float, float]) -> bool:
    """Bütün köşeler kutunun içinde mi (boş çizgi kutuda sayılmaz)?"""
    if not koseler:
        return False
    return all(kutu[0] <= float(k[0]) <= kutu[1] and kutu[2] <= float(k[1]) <= kutu[3]
               for k in koseler)


def _ne_kimligi(p: dict) -> Optional[int]:
    deger = p.get('NE_ID') if p.get('NE_ID') is not None else p.get('ne_id')
    return None if deger is None else int(deger)


def _ulke_cifti(p: dict) -> Optional[Tuple[str, ...]]:
    sol, sag = _metin(p.get('ADM0_A3_L')), _metin(p.get('ADM0_A3_R'))
    if sol is None and sag is None:
        return None
    return tuple(sorted((sol or '', sag or '')))


class _SinirDuzeltici:
    """Bir sınır dosyasının düzeltme satırını uygular (fail-closed)."""

    def __init__(self, dosya: str, duzeltmeler: Sequence[SinirDuzeltmesi],
                 kaynak_sha: Optional[str]) -> None:
        self.dosya = dosya
        satirlar = [d for d in duzeltmeler if d.dosya == dosya]
        if len(satirlar) > 1:
            raise KaynakHatasi('%s: sınır düzeltme tablosunda birden çok satır' % dosya)
        self.satir = satirlar[0] if satirlar else None
        self.zorunlu = (kaynak_sha is not None
                        and SINIR_DUZELTMESI_KAYNAK_SHA.get(dosya) == kaynak_sha)
        self.dusulen: List[dict] = []

    def dusur_mu(self, ozellik: dict) -> bool:
        d = self.satir
        if d is None:
            return False
        p = ozellik.get('properties') or {}
        koseler = [k for c in cizgileri_ayikla(ozellik.get('geometry')) for k in c]
        cift = _ulke_cifti(p)
        aday = (_kutuda(koseler, d.kutu)
                or (_metin(p.get('FEATURECLA')) == d.featurecla
                    and cift == tuple(sorted(d.ulke_cifti))))
        if not aday:
            return False
        kimlik = _ne_kimligi(p)
        hatalar = []
        if kimlik != d.ne_id:
            hatalar.append('NE kimliği %r (tabloda %r)' % (kimlik, d.ne_id))
        if _metin(p.get('FEATURECLA')) != d.featurecla:
            hatalar.append('FEATURECLA %r' % p.get('FEATURECLA'))
        if _metin(p.get('BRK_A3')) != d.brk_a3:
            hatalar.append('BRK_A3 %r' % p.get('BRK_A3'))
        if not _kutuda(koseler, d.kutu):
            hatalar.append('köşelerin bir kısmı kutu dışında')
        if cift is not None and cift != tuple(sorted(d.ulke_cifti)):
            hatalar.append('ülke çifti %r' % (cift,))
        if hatalar:
            raise KaynakHatasi('%s: sınır düzeltmesi adayı tabloya uymuyor (%s); NE '
                               'değişmiş, düzeltme yeniden doğrulanmadan üretim '
                               'yapılmaz' % (self.dosya, '; '.join(hatalar)))
        lons = [float(k[0]) for k in koseler]
        lats = [float(k[1]) for k in koseler]
        self.dusulen.append({
            'ne_id': kimlik, 'featurecla': d.featurecla, 'brk_a3': d.brk_a3,
            'country_pair': list(cift) if cift is not None else list(d.ulke_cifti),
            'country_pair_basis': ('ADM0_A3_L/ADM0_A3_R' if cift is not None
                                   else 'no pair fields in this file; same NE id '
                                        'as the 10m record'),
            'vertex_count': len(koseler),
            'bbox': [min(lons), min(lats), max(lons), max(lats)],
            'note': d.kunye})
        return True

    def bitir(self) -> Optional[dict]:
        d = self.satir
        if d is None:
            return None
        if len(self.dusulen) != d.beklenen and (self.zorunlu or self.dusulen):
            raise KaynakHatasi('%s: sınır düzeltmesi %d eşleşme buldu, beklenen %d; '
                               'HİÇBİR DOSYA YAZILMADI'
                               % (self.dosya, len(self.dusulen), d.beklenen))
        return {'decision': SINIR_DUZELTMESI_KARARI,
                'verified_against': {'file': self.dosya,
                                     'sha256': SINIR_DUZELTMESI_KAYNAK_SHA.get(self.dosya)},
                'dropped': self.dusulen,
                'not_applied': ([] if self.dusulen
                                else [{'ne_id': d.ne_id, 'note': d.kunye}])}


def geojson_katmani(yol: Path, sinir: Optional[_SinirDuzeltici] = None) -> KatmanToplayici:
    veri = json.loads(yol.read_text(encoding='utf-8'))
    t = KatmanToplayici()
    for ozellik in veri.get('features', []):
        geometri = ozellik.get('geometry')
        if not geometri:
            t.geometrisiz += 1
            continue
        if sinir is not None and sinir.dusur_mu(ozellik):
            continue
        mz = min_zoom_kodla(ozellik.get('properties') or {})
        for cizgi in cizgileri_ayikla(geometri):
            t.ekle(cizgi, mz)
    return t


def eski_110m_sinir_denetimi(veri: dict) -> None:
    """Eski 110m yedek katmanında Perekop kutusunda kalan sınır çizgisi varsa
    durur (karar §28-45/Kırım; çizgi ``earth_borders.json``'dan düşüldü)."""
    for i, duz in enumerate(veri['layers'].get('borders', [])):
        ciftler = [(duz[j], duz[j + 1]) for j in range(0, len(duz) - 1, 2)]
        if _kutuda(ciftler, PEREKOP_KUTUSU):
            raise KaynakHatasi('earth_borders.json borders[%d] Perekop kutusunda '
                               '(karar §28-45/Kırım); HİÇBİR DOSYA YAZILMADI' % i)


def eski_110m_katmani(veri: dict, anahtar: str) -> KatmanToplayici:
    """``earth_borders.json`` düz [lon,lat,...] dizilerini aynı biçime çevirir."""
    t = KatmanToplayici()
    for duz in veri['layers'][anahtar]:
        ciftler = [(duz[i], duz[i + 1]) for i in range(0, len(duz) - 1, 2)]
        t.ekle(ciftler, MIN_ZOOM_YOK)
    return t


def basamak_ikilisi(katmanlar: Dict[str, KatmanToplayici]) -> Tuple[bytes, dict]:
    """Katmanları HMV1 ikilisine yazar; (bayt, manifest parçası) döndürür."""
    govde = bytearray()
    katman_ozeti = {}
    blok_sayisi = toplam_kose = toplam_cizgi = 0
    mw, mh = tile_cache.matrix_size(HUCRE_Z)
    for ad, t in katmanlar.items():
        hucreler = []
        k_kose = k_cizgi = 0
        for cy in range(mh):
            for cx in range(mw):
                blok = t.bloklar.get((cx, cy))
                if not blok:
                    continue
                koseler = blok['koseler']
                nv = len(koseler) // 2
                nl = len(blok['uzunluklar'])
                ofset = HMV1_BASLIK_BAYT + len(govde)
                govde += struct.pack('<%di' % len(koseler), *koseler)
                govde += struct.pack('<%dI' % nl, *blok['uzunluklar'])
                govde += bytes(blok['min_zoom'])
                govde += b'\x00' * ((-len(govde)) % 4)
                lons = koseler[0::2]
                lats = koseler[1::2]
                hucreler.append({
                    'cell': [cx, cy],
                    'offset': ofset,
                    'vertex_count': nv,
                    'line_count': nl,
                    'bbox': [min(lons) / KOORDINAT_OLCEGI,
                             min(lats) / KOORDINAT_OLCEGI,
                             max(lons) / KOORDINAT_OLCEGI,
                             max(lats) / KOORDINAT_OLCEGI],
                })
                blok_sayisi += 1
                k_kose += nv
                k_cizgi += nl
        toplam_kose += k_kose
        toplam_cizgi += k_cizgi
        katman_ozeti[ad] = {
            'vertex_count': k_kose,
            'line_count': k_cizgi,
            'source_line_count': t.kaynak_cizgi,
            'source_vertex_count': t.kaynak_kose,
            'dropped_duplicate_vertices': t.atilan_tekrar,
            'dropped_short_lines': t.atilan_kisa,
            'features_without_geometry': t.geometrisiz,
            'lines_without_min_zoom': t.min_zoom_yok,
            'cells': hucreler,
        }
    baslik = SIHIRLI + struct.pack('<III', blok_sayisi, toplam_kose, toplam_cizgi)
    veri = bytes(baslik) + bytes(govde)
    return veri, {'block_count': blok_sayisi, 'vertex_count': toplam_kose,
                  'line_count': toplam_cizgi, 'layers': katman_ozeti}


# ---------------------------------------------------------------------------
# Yerler ve ülke etiketleri
# ---------------------------------------------------------------------------

def _metin(deger) -> Optional[str]:
    if deger is None:
        return None
    s = str(deger).strip()
    return s or None


def _sayi(deger):
    if deger is None:
        return None
    f = float(deger)
    return int(f) if f.is_integer() else f


# ---------------------------------------------------------------------------
# Ad düzeltmeleri (karar §28-45, Berke 13 Eki 2026)
# ---------------------------------------------------------------------------
# Berke: "türklerle alakalı olanlar, türkler için önemli olanlar düzgün
# isimlendirilir; geri kalan aynı kalsın". Aşağıdaki tablo TEK düzeltme
# kaynağıdır. Tablo DIŞINDAKİ her ad ve alan ham NE ile bit-aynı kalır.
#
# Sözleşme (fail-closed):
#  - Satır, NE'nin kararlı kimliğiyle bulunur: yerde ``NE_ID`` (ham veride
#    benzersiz, ölçüldü: 7342 kayıt, 7342 farklı NE_ID; ADM0_A3 + NAME ise 63
#    kez tekrarlıyor), ülkede ``ADM0_A3`` (258 kayıt, benzersiz). ``adm0``
#    çapraz denetimdir.
#  - Satırdaki ESKİ değer ham NE'deki değerle aynı değilse (NE değişmiş)
#    üretim ``KaynakHatasi`` ile durur. Aynı anahtar iki kayda uyarsa da durur.
#  - Kaynağın sha256'sı tablonun doğrulandığı dosyanınkiyle aynıysa
#    (``AD_DUZELTMESI_KAYNAK_SHA``) her satır uygulanmak ZORUNDADIR; anahtarı
#    bulunamayan satır üretimi durdurur. Başka bir kaynakta (ör. test
#    fixture'ı) anahtarı bulunmayan satır uygulanmaz ve künyede
#    ``not_applied`` altında adıyla beyan edilir.
#  - Uygulanan her satır varlığın künyesine (provenance) künyesiyle yazılır.

#: Düzeltmelerin kararı (künye).
AD_DUZELTMESI_KARARI = 'karar §28-45 (Berke, 13 Eki 2026)'
#: Düzeltme uygulanmış varlığın dürüst kaynak satırı.
AD_DUZELTMESI_KAYNAK_EKI = 'HRMA ad düzeltmeleri, karar §28-45'
#: Tablonun satır satır doğrulandığı ham dosyalar (sha256, ``SHA256SUMS.txt``).
AD_DUZELTMESI_KAYNAK_SHA = {
    'ne_10m_populated_places.geojson':
        '9b8e3de09048ef00dfc70357dbb9fa324493f214b5e0ae4daf1aa79a8d10116b',
    'ne_10m_admin_0_countries.geojson':
        '239eec57ac17f100a11e2536cffc56752c318b50ae765b0918ff7aab4ce8f255',
}
#: Varlık alanı -> ham NE özelliği.
AD_ALANI_NE = {'name': 'NAME', 'name_en': 'NAME_EN', 'name_tr': 'NAME_TR',
               # Ülke kodu yalnız karar §28-45/Kırım için (RUS -> UKR).
               'adm0': 'ADM0_A3'}
#: Kırım kutusu (boylam en az, en çok, enlem en az, en çok); karar §28-45/Kırım.
#: Doğrulanan kaynakta kutudaki ham 'RUS' yerleşimlerinin kümesi tablodaki
#: adm0 satırlarıyla BİREBİR olmalı (ölçüldü: 6 yer), değilse üretim durur.
KIRIM_KUTUSU = (32.4, 36.7, 44.3, 46.25)
KIRIM_ADM0_DUZELTMESI = ('adm0', 'RUS', 'UKR')
#: Katman -> kararlı anahtar alanı.
AD_ANAHTARI = {'places': 'NE_ID', 'country_labels': 'ADM0_A3'}


class AdDuzeltmesi(NamedTuple):
    """Tek düzeltme satırı (karar §28-45)."""
    katman: str                              # 'places' | 'country_labels'
    anahtar: object                          # NE_ID (yer) ya da ADM0_A3 (ülke)
    adm0: str                                # ADM0_A3 çapraz denetimi
    alanlar: Tuple[Tuple[str, str, str], ...]  # (alan, eski, yeni)
    kunye: str


_KIRIM = ("Türkçe ve Kırım Tatarca yerleşik ad; aynı bölgedeki 'Canköy' ile "
          "tutarlı. adm0 RUS -> UKR: Türkiye'nin resmî görüşü (karar §28-45/Kırım)")
_KIRIM_ADM0 = "adm0 RUS -> UKR: Türkiye'nin resmî görüşü (karar §28-45/Kırım)"
_ROMENCE = ("Türkçe yerleşik adda Romence harf: ș (U+0219) yerine Türkçe ş "
            "(U+015F)")

AD_DUZELTMELERI: Tuple[AdDuzeltmesi, ...] = (
    # --- Ülke etiketleri (anahtar ADM0_A3) ---------------------------------
    AdDuzeltmesi('country_labels', 'TUR', 'TUR',
                 (('name_en', 'Turkey', 'Türkiye'),),
                 "BM'de 2022'den beri resmî ad; T.C. Dışişleri Bakanlığı duyurusu"),
    AdDuzeltmesi('country_labels', 'CYP', 'CYP',
                 (('name_tr', 'Kıbrıs Cumhuriyeti', 'Güney Kıbrıs Rum Yönetimi'),
                  ('name_en', 'Cyprus',
                   'Greek Cypriot Administration of Southern Cyprus')),
                 'T.C. Dışişleri Bakanlığı resmî kullanımı: GKRY / GCASC'),
    AdDuzeltmesi('country_labels', 'ESB', 'ESB',
                 (('name_tr', 'Dhekelia Kantonu', 'Dikelya'),
                  ('name_en', 'Dhekelia Cantonment', 'Dhekelia Sovereign Base Area')),
                 "Türkçe yerleşik ad 'Ağrotur ve Dikelya'; NE'nin Ağrotur kaydıyla "
                 "(WSB: 'Ağrotur' / 'Akrotiri Sovereign Base Area') tutarlı"),
    # --- Yer adları (anahtar NE_ID) ----------------------------------------
    AdDuzeltmesi('places', 1159127441, 'TUR',
                 (('name', 'Elâzığ', 'Elazığ'), ('name_tr', 'Elâzığ', 'Elazığ')),
                 'TDK Yazım Kılavuzu; resmî il adı (Hakkâri TDK yazımıdır, değişmez)'),
    AdDuzeltmesi('places', 1159144591, 'AZE',
                 (('name', 'Stepanakert', 'Xankəndi'),
                  ('name_en', 'Stepanakert', 'Khankendi')),
                 "Azerbaycan'ın resmî adı; name_tr 'Hankendi' zaten doğru"),
    AdDuzeltmesi('places', 1159134155, 'RUS',
                 (('name_tr', 'Simferopol', 'Akmescit'), KIRIM_ADM0_DUZELTMESI), _KIRIM),
    AdDuzeltmesi('places', 1159134145, 'RUS',
                 (('name_tr', 'Evpatorya', 'Gözleve'), KIRIM_ADM0_DUZELTMESI), _KIRIM),
    AdDuzeltmesi('places', 1159150561, 'RUS', (KIRIM_ADM0_DUZELTMESI,),
                 _KIRIM_ADM0),                                    # Sevastopol
    AdDuzeltmesi('places', 1159134151, 'RUS', (KIRIM_ADM0_DUZELTMESI,),
                 _KIRIM_ADM0),                                    # Kerch
    AdDuzeltmesi('places', 1159147519, 'RUS', (KIRIM_ADM0_DUZELTMESI,),
                 _KIRIM_ADM0),                                    # Yalta
    AdDuzeltmesi('places', 1159134141, 'RUS', (KIRIM_ADM0_DUZELTMESI,),
                 _KIRIM_ADM0),                                    # Dzhankoy (Canköy)
    AdDuzeltmesi('places', 1159140707, 'CHN',
                 (('name_tr', 'Turfan İli', 'Turfan'),),
                 "Şehir etiketi; 'İli' idari birim ekidir"),
    AdDuzeltmesi('places', 1159126219, 'SYR',
                 (('name_tr', 'Hasiçi', 'Haseke'),), 'Türkçe yerleşik ad'),
    AdDuzeltmesi('places', 1159126193, 'SYR',
                 (('name_tr', 'İdlip', 'İdlib'),), 'Türkçe yerleşik ad'),
    AdDuzeltmesi('places', 1159136459, 'KGZ',
                 (('name_tr', 'Celal-Abad', 'Celalabad'),), 'Türkçe yerleşik ad'),
    AdDuzeltmesi('places', 1159134335, 'UZB',
                 (('name_tr', 'Karşi', 'Karşı'),), 'Türkçe yerleşik ad'),
    AdDuzeltmesi('places', 1159151263, 'ROU',
                 (('name_tr', 'Bükreș', 'Bükreş'),), _ROMENCE),
    AdDuzeltmesi('places', 1159149403, 'ROU',
                 (('name_tr', 'Yaș', 'Yaş'),), _ROMENCE),
    AdDuzeltmesi('places', 1159135835, 'ROU',
                 (('name_tr', 'Temeșvar', 'Temeşvar'),), _ROMENCE),
    AdDuzeltmesi('places', 1159127789, 'ROU',
                 (('name_tr', 'Tulca', 'Tulça'),), 'Türkçe yerleşik ad (Tulça)'),
)


def _duzeltme_satiri_kunyesi(d: AdDuzeltmesi) -> dict:
    return {'key_field': AD_ANAHTARI[d.katman], 'key': d.anahtar, 'adm0': d.adm0,
            'changes': [{'field': a, 'old': e, 'new': y} for a, e, y in d.alanlar],
            'note': d.kunye}


class _AdDuzeltici:
    """Bir katmanın düzeltme satırlarını kayıtlara uygular (fail-closed)."""

    def __init__(self, katman: str, duzeltmeler: Sequence[AdDuzeltmesi],
                 kaynak_dosya: str, kaynak_sha: Optional[str]) -> None:
        self.katman = katman
        self.anahtar_alani = AD_ANAHTARI[katman]
        self.kaynak_dosya = kaynak_dosya
        self.zorunlu = (kaynak_sha is not None
                        and AD_DUZELTMESI_KAYNAK_SHA.get(kaynak_dosya) == kaynak_sha)
        self.satirlar: Dict[object, AdDuzeltmesi] = {}
        for d in duzeltmeler:
            if d.katman != katman:
                continue
            if d.anahtar in self.satirlar:
                raise KaynakHatasi('ad düzeltme tablosunda %s=%r iki kez var'
                                   % (self.anahtar_alani, d.anahtar))
            for alan, _eski, yeni in d.alanlar:
                if alan not in AD_ALANI_NE or not _metin(yeni):
                    raise KaynakHatasi('ad düzeltmesi %r: alan ya da yeni değer geçersiz'
                                       % (d.anahtar,))
            self.satirlar[d.anahtar] = d
        self.uygulanan: List[AdDuzeltmesi] = []

    def uygula(self, p: dict, kayit: dict) -> None:
        d = self.satirlar.get(p.get(self.anahtar_alani))
        if d is None:
            return
        if d in self.uygulanan:
            raise KaynakHatasi('%s: %s=%r birden çok kayda uyuyor; anahtar kararlı değil'
                               % (self.kaynak_dosya, self.anahtar_alani, d.anahtar))
        if _metin(p.get('ADM0_A3')) != d.adm0:
            raise KaynakHatasi('%s: %s=%r ADM0_A3 %r, tabloda %r (NE değişmiş)'
                               % (self.kaynak_dosya, self.anahtar_alani, d.anahtar,
                                  p.get('ADM0_A3'), d.adm0))
        for alan, eski, yeni in d.alanlar:
            ham = _metin(p.get(AD_ALANI_NE[alan]))
            if ham != eski:
                raise KaynakHatasi('%s: %s=%r %s ham değeri %r, tablodaki eski değer %r '
                                   '(NE değişmiş; düzeltme yeniden doğrulanmadan '
                                   'üretim yapılmaz)'
                                   % (self.kaynak_dosya, self.anahtar_alani, d.anahtar,
                                      AD_ALANI_NE[alan], ham, eski))
            kayit[alan] = yeni
        self.uygulanan.append(d)

    def bitir(self) -> dict:
        eksik = [d for d in self.satirlar.values() if d not in self.uygulanan]
        if eksik and self.zorunlu:
            raise KaynakHatasi('%s: ad düzeltme satırı kaynakta bulunamadı: %s'
                               % (self.kaynak_dosya,
                                  ', '.join(repr(d.anahtar) for d in eksik)))
        return {'decision': AD_DUZELTMESI_KARARI,
                'verified_against': {'file': self.kaynak_dosya,
                                     'sha256': AD_DUZELTMESI_KAYNAK_SHA.get(self.kaynak_dosya)},
                'applied': [_duzeltme_satiri_kunyesi(d) for d in self.uygulanan],
                'not_applied': [_duzeltme_satiri_kunyesi(d) for d in eksik]}


YER_ALANLARI = ['lon', 'lat', 'name', 'name_en', 'name_tr', 'min_zoom',
                'labelrank', 'featurecla', 'adm0']


def yerleri_uret(yol: Path, duzeltmeler: Sequence[AdDuzeltmesi] = (),
                 kaynak_sha: Optional[str] = None) -> Tuple[dict, dict]:
    veri = json.loads(yol.read_text(encoding='utf-8'))
    duzeltici = _AdDuzeltici('places', duzeltmeler, yol.name, kaynak_sha)
    kayitlar = []
    kirim_ham_rus = set()
    for ozellik in veri.get('features', []):
        g = ozellik.get('geometry') or {}
        p = ozellik.get('properties') or {}
        if g.get('type') != 'Point':
            continue
        lon, lat = g['coordinates'][:2]
        if (KIRIM_KUTUSU[0] <= float(lon) <= KIRIM_KUTUSU[1]
                and KIRIM_KUTUSU[2] <= float(lat) <= KIRIM_KUTUSU[3]
                and _metin(p.get('ADM0_A3')) == KIRIM_ADM0_DUZELTMESI[1]):
            kirim_ham_rus.add(_sayi(p.get('NE_ID')))
        kayit = {
            'lon': round(float(lon), YER_ONDALIK),
            'lat': round(float(lat), YER_ONDALIK),
            'name': _metin(p.get('NAME')),
            'name_en': _metin(p.get('NAME_EN')),
            'name_tr': _metin(p.get('NAME_TR')),
            'min_zoom': _sayi(p.get('MIN_ZOOM')),
            'labelrank': _sayi(p.get('LABELRANK')),
            'featurecla': _metin(p.get('FEATURECLA')),
            'adm0': _metin(p.get('ADM0_A3')),
        }
        # Sıralama ham NAME ile kurulur: ad düzeltmesi kayıt sırasını değiştirmez.
        ham_ad = kayit['name']
        duzeltici.uygula(p, kayit)
        pop = p.get('POP_MAX')
        anahtar = (0 if kayit['featurecla'] == BASKENT_SINIFI else 1,
                   kayit['labelrank'] if kayit['labelrank'] is not None else math.inf,
                   -(float(pop) if pop is not None else -1.0),
                   ham_ad or '',
                   _sayi(p.get('NE_ID')) or 0)
        kayitlar.append((anahtar, kayit, _metin(p.get('ADM1NAME'))))
    kayitlar.sort(key=lambda x: x[0])
    satirlar = [[k[a] for a in YER_ALANLARI] for _, k, _ in kayitlar]

    toplam = len(satirlar)
    tr_dolu = sum(1 for _, k, _ in kayitlar if k['name_tr'])
    tr_farkli = sum(1 for _, k, _ in kayitlar
                    if k['name_tr'] and k['name_tr'] != k['name'])
    en_dolu = sum(1 for _, k, _ in kayitlar if k['name_en'])
    il_merkezleri = sorted(
        k['name_tr'] or k['name'] for _, k, _ in kayitlar
        if k['adm0'] == TURKIYE_A3 and k['featurecla'] in IL_MERKEZI_SINIFLARI)
    sayim = {
        'place_count': toplam,
        'name_tr_filled': tr_dolu,
        'name_tr_fill_ratio': round(tr_dolu / toplam, 4) if toplam else None,
        'name_tr_differs_from_name': tr_farkli,
        'name_tr_fallback_to_name': toplam - tr_dolu,
        'name_en_filled': en_dolu,
        'name_en_fallback_to_name': toplam - en_dolu,
        'turkey_place_count': sum(1 for _, k, _ in kayitlar if k['adm0'] == TURKIYE_A3),
        'turkey_province_centre_count': len(il_merkezleri),
        'turkey_province_count_expected': TURKIYE_IL_SAYISI,
        'turkey_province_centre_classes': list(IL_MERKEZI_SINIFLARI),
    }
    duzeltme = duzeltici.bitir()
    # Karar §28-45/Kırım: doğrulanan kaynakta Kırım kutusundaki ham 'RUS'
    # yerleşimleri ile tablonun adm0 satırları birebir aynı olmalı.
    kirim_tablo = {d.anahtar for d in duzeltici.satirlar.values()
                   if KIRIM_ADM0_DUZELTMESI in d.alanlar}
    if duzeltici.zorunlu and kirim_ham_rus != kirim_tablo:
        raise KaynakHatasi('%s: Kırım kutusundaki ham RUS yerleşimleri (%d) adm0 '
                           'düzeltme tablosuyla (%d) aynı değil: fazla %s, eksik %s '
                           '(karar §28-45/Kırım; HİÇBİR DOSYA YAZILMADI)'
                           % (yol.name, len(kirim_ham_rus), len(kirim_tablo),
                              sorted(kirim_ham_rus - kirim_tablo),
                              sorted(kirim_tablo - kirim_ham_rus)))
    sayim['name_corrections_applied'] = len(duzeltme['applied'])
    return ({'fields': YER_ALANLARI, 'rows': satirlar},
            dict(sayim, _il_merkezleri=il_merkezleri, _ad_duzeltmeleri=duzeltme))


ULKE_ALANLARI = ['lon', 'lat', 'name', 'name_en', 'name_tr', 'min_label',
                 'max_label', 'labelrank', 'adm0']


def ulke_etiketlerini_uret(yol: Path, duzeltmeler: Sequence[AdDuzeltmesi] = (),
                           kaynak_sha: Optional[str] = None) -> Tuple[dict, dict]:
    veri = json.loads(yol.read_text(encoding='utf-8'))
    duzeltici = _AdDuzeltici('country_labels', duzeltmeler, yol.name, kaynak_sha)
    kayitlar = []
    etiketsiz = 0
    for ozellik in veri.get('features', []):
        p = ozellik.get('properties') or {}
        if p.get('LABEL_X') is None or p.get('LABEL_Y') is None:
            etiketsiz += 1
            continue
        kayit = {
            'lon': round(float(p['LABEL_X']), YER_ONDALIK),
            'lat': round(float(p['LABEL_Y']), YER_ONDALIK),
            'name': _metin(p.get('NAME')),
            'name_en': _metin(p.get('NAME_EN')),
            'name_tr': _metin(p.get('NAME_TR')),
            'min_label': _sayi(p.get('MIN_LABEL')),
            'max_label': _sayi(p.get('MAX_LABEL')),
            'labelrank': _sayi(p.get('LABELRANK')),
            'adm0': _metin(p.get('ADM0_A3')),
        }
        # Sıralama ham NAME ile kurulur: ad düzeltmesi kayıt sırasını değiştirmez.
        ham_ad = kayit['name']
        duzeltici.uygula(p, kayit)
        kayitlar.append((ham_ad, kayit))
    kayitlar.sort(key=lambda x: (x[1]['labelrank'] if x[1]['labelrank'] is not None else math.inf,
                                 x[1]['min_label'] if x[1]['min_label'] is not None else math.inf,
                                 x[1]['adm0'] or '', x[0] or ''))
    kayitlar = [k for _, k in kayitlar]
    toplam = len(kayitlar)
    tr_dolu = sum(1 for k in kayitlar if k['name_tr'])
    duzeltme = duzeltici.bitir()
    sayim = {
        'country_count': toplam,
        'features_without_label_point': etiketsiz,
        'name_tr_filled': tr_dolu,
        'name_tr_fill_ratio': round(tr_dolu / toplam, 4) if toplam else None,
        'name_tr_fallback_to_name': toplam - tr_dolu,
        'name_corrections_applied': len(duzeltme['applied']),
    }
    return ({'fields': ULKE_ALANLARI, 'rows': [[k[a] for a in ULKE_ALANLARI] for k in kayitlar]},
            dict(sayim, _ad_duzeltmeleri=duzeltme))


# ---------------------------------------------------------------------------
# Ana üretim
# ---------------------------------------------------------------------------

def _json_bayt(nesne: dict) -> bytes:
    return (json.dumps(nesne, ensure_ascii=False, separators=(',', ':'))
            + '\n').encode('utf-8')


def _sha(veri: bytes) -> str:
    return hashlib.sha256(veri).hexdigest()


def uret(kaynak: Path = VARSAYILAN_KAYNAK, eski_110m: Path = ESKI_110M,
         butce: Optional[int] = None) -> Tuple[Dict[str, bytes], dict]:
    """Bütün varlıkları BELLEKTE üretir: ({dosya adı: bayt}, ölçüm özeti).

    Bütçe aşılırsa ``ButceAsildi`` yükselir; diske hiçbir şey yazılmaz
    (yazma ``yaz`` ile ayrı adımdır).
    """
    if butce is None:
        butce = BOYUT_BUTCESI_BAYT      # çağrı anında okunur (bekçi yamalayabilsin)
    if SINIR_GORUNUMU not in SINIR_GORUNUMU_DOSYALARI:
        raise KaynakHatasi('bilinmeyen SINIR_GORUNUMU: %r' % SINIR_GORUNUMU)
    liste = sha_listesini_oku(kaynak)
    kaynaklar = []

    def _kullan(ad: str) -> Path:
        yol, ozet = kaynak_dogrula(kaynak, ad, liste)
        kaynaklar.append({'file': ad, 'sha256': ozet, 'bytes': yol.stat().st_size,
                          'version': NE_SURUM, 'repository': NE_DEPO,
                          'license': NE_LISANS})
        return yol

    dosyalar: Dict[str, bytes] = {}
    basamaklar = {}

    # 110m: depodaki mevcut varlıktan.
    eski_bayt = eski_110m.read_bytes()
    eski = json.loads(eski_bayt.decode('utf-8'))
    eski_110m_sinir_denetimi(eski)
    katmanlar = {ad: eski_110m_katmani(eski, anahtar)
                 for ad, anahtar in ESKI_110M_KATMANLARI.items()}
    veri, ozet = basamak_ikilisi(katmanlar)
    dosyalar['vectors_110m.bin'] = veri
    basamaklar['110m'] = dict(
        file='vectors_110m.bin', bytes=len(veri), sha256=_sha(veri),
        nominal_scale='1:110m',
        source={'file': 'hrma/static/img/earth_borders.json',
                'sha256': _sha(eski_bayt),
                'origin': eski.get('source'),
                'license': eski.get('license'),
                'retrieved_utc': eski.get('retrieved_utc'),
                'format': eski.get('format'),
                'note': ('Converted from the in-repo 110m asset (Natural '
                         'Earth master branch, 2-decimal rounding); not '
                         're-derived from v5.1.2. Precision stays 0.01 deg.')},
        **ozet)
    # Künye yalnız depodaki düzeltilmiş dosyanın kendisi için yazılır.
    if _sha(eski_bayt) == ESKI_110M_SINIR_DUZELTMESI['sha256_after']:
        basamaklar['110m']['source']['boundary_corrections'] = ESKI_110M_SINIR_DUZELTMESI
    sinir_kunyeleri = {}

    for basamak in ('50m', '10m'):
        katmanlar = {}
        katman_kaynak = {}
        duzelticiler = {}
        for ad, dosya in BASAMAKLAR[basamak].items():
            yol = _kullan(dosya)
            duzelticiler[ad] = _SinirDuzeltici(dosya, SINIR_DUZELTMELERI,
                                               kaynaklar[-1]['sha256'])
            katmanlar[ad] = geojson_katmani(yol, duzelticiler[ad])
            katman_kaynak[ad] = dosya
        veri, ozet = basamak_ikilisi(katmanlar)
        ad = 'vectors_%s.bin' % basamak
        dosyalar[ad] = veri
        for katman, kaynak_ad in katman_kaynak.items():
            ozet['layers'][katman]['source'] = kaynak_ad
            kunye = duzelticiler[katman].bitir()
            if kunye is not None:
                ozet['layers'][katman]['boundary_corrections'] = kunye
                sinir_kunyeleri['%s/%s' % (basamak, katman)] = len(kunye['dropped'])
        basamaklar[basamak] = dict(file=ad, bytes=len(veri), sha256=_sha(veri),
                                   nominal_scale='1:%s' % basamak, **ozet)

    yer_yolu = _kullan(YERLER_DOSYASI)
    yerler, yer_sayim = yerleri_uret(yer_yolu, AD_DUZELTMELERI, kaynaklar[-1]['sha256'])
    il_merkezleri = yer_sayim.pop('_il_merkezleri')
    yer_duzeltme = yer_sayim.pop('_ad_duzeltmeleri')
    ulke_dosyasi = SINIR_GORUNUMU_DOSYALARI[SINIR_GORUNUMU]
    ulke_yolu = _kullan(ulke_dosyasi)
    ulkeler, ulke_sayim = ulke_etiketlerini_uret(ulke_yolu, AD_DUZELTMELERI,
                                                 kaynaklar[-1]['sha256'])
    ulke_duzeltme = ulke_sayim.pop('_ad_duzeltmeleri')

    ortak_kunye = {
        'source': 'Natural Earth %s (%s)' % (NE_SURUM, NE_DEPO),
        'license': NE_LISANS,
        'attribution': NE_ATIF,
        'boundary_view': SINIR_GORUNUMU,
    }

    def _ad_kunyesi(duzeltme: dict) -> dict:
        # Dürüst kaynak: düzeltme uygulandıysa kaynak satırı bunu söyler.
        if not duzeltme['applied']:
            return dict(ortak_kunye, name_corrections=duzeltme)
        return dict(ortak_kunye, name_corrections=duzeltme,
                    source='%s + %s' % (ortak_kunye['source'], AD_DUZELTMESI_KAYNAK_EKI))

    yerler['provenance'] = dict(_ad_kunyesi(yer_duzeltme), file=YERLER_DOSYASI,
                                sort_order=('Admin-0 capital first, then LABELRANK '
                                            'ascending, then POP_MAX descending '
                                            '(POP_MAX used for ordering only, '
                                            'not shipped), then raw NE NAME (before '
                                            'name corrections), NE_ID'),
                                coordinates='GeoJSON Point geometry, %d decimals'
                                % YER_ONDALIK,
                                **yer_sayim)
    ulkeler['provenance'] = dict(_ad_kunyesi(ulke_duzeltme), file=ulke_dosyasi,
                                 coordinates='LABEL_X/LABEL_Y, %d decimals' % YER_ONDALIK,
                                 **ulke_sayim)
    dosyalar['places.json'] = _json_bayt(yerler)
    dosyalar['country_labels.json'] = _json_bayt(ulkeler)

    mw, mh = tile_cache.matrix_size(HUCRE_Z)
    yuk_bayt = sum(len(v) for v in dosyalar.values())
    manifest = {
        'format': SIHIRLI.decode('ascii'),
        'byte_order': 'little',
        'layout': ('header: magic(4) uint32 block_count, uint32 vertex_count, '
                   'uint32 line_count; then blocks (4-byte aligned): '
                   'int32[2*vertex_count] [lon*scale, lat*scale] pairs, '
                   'uint32[line_count] vertices per line, uint8[line_count] '
                   'min_zoom*%d (%d = absent), zero padding to 4 bytes'
                   % (MIN_ZOOM_OLCEGI, MIN_ZOOM_YOK)),
        'coord_scale': KOORDINAT_OLCEGI,
        'min_zoom_scale': MIN_ZOOM_OLCEGI,
        'min_zoom_absent': MIN_ZOOM_YOK,
        'cell_grid': {
            'tile_matrix_zoom': HUCRE_Z,
            'span_deg': tile_cache.tile_span_deg(HUCRE_Z),
            'matrix_width': mw,
            'matrix_height': mh,
            'origin': 'top-left (-180, +90); x east, y south',
            'owner': 'hrma.analysis.tile_cache (lonlat_to_tile, matrix_size)',
            'split_rule': ('a line is cut where it enters a new cell; the '
                           'first piece ends at the first vertex inside the '
                           'new cell, the next piece starts there; no vertex '
                           'is created, no segment is duplicated; bbox is '
                           'measured from real vertices'),
        },
        'levels': {b: basamaklar[b] for b in BASAMAK_SIRASI},
        'places': {'file': 'places.json', 'bytes': len(dosyalar['places.json']),
                   'sha256': _sha(dosyalar['places.json']), **yer_sayim},
        'country_labels': {'file': 'country_labels.json',
                           'bytes': len(dosyalar['country_labels.json']),
                           'sha256': _sha(dosyalar['country_labels.json']),
                           **ulke_sayim},
        'sources': sorted(kaynaklar, key=lambda k: k['file']),
        'provenance': dict(ortak_kunye,
                           source=('%s + %s' % (ortak_kunye['source'],
                                                SINIR_DUZELTMESI_KAYNAK_EKI)
                                   if any(sinir_kunyeleri.values())
                                   else ortak_kunye['source']),
                           builder='tools/build_map_detail_assets.py',
                           boundary_view_file=ulke_dosyasi,
                           name_corrections={
                               'decision': AD_DUZELTMESI_KARARI,
                               'places_applied': len(yer_duzeltme['applied']),
                               'country_labels_applied': len(ulke_duzeltme['applied']),
                               'note': ('only places.json and country_labels.json; '
                                        'vector lines: see boundary_corrections')},
                           boundary_corrections={
                               'decision': SINIR_DUZELTMESI_KARARI,
                               'dropped_lines': sinir_kunyeleri,
                               'legacy_110m': (
                                   basamaklar['110m']['source'].get('boundary_corrections')
                                   is not None),
                               'note': ('every other vector line is raw Natural '
                                        'Earth; details per level under '
                                        'layers.borders.boundary_corrections and '
                                        'levels.110m.source.boundary_corrections')},
                           honesty=('Lines are 1:10m/1:50m generalized data; at '
                                    'close zoom positions may be off by hundreds '
                                    'of metres to kilometres. City points are '
                                    'administrative or population points, not '
                                    'city limits.')),
        'budget': {'limit_bytes': butce, 'payload_bytes': yuk_bayt},
    }
    manifest_bayt = _json_bayt(manifest)
    toplam = yuk_bayt + len(manifest_bayt)
    olcum = {
        'dosyalar': {ad: len(v) for ad, v in dosyalar.items()},
        'manifest_bayt': len(manifest_bayt),
        'toplam_bayt': toplam,
        'butce_bayt': butce,
        'kose': {b: basamaklar[b]['vertex_count'] for b in BASAMAK_SIRASI},
        'cizgi': {b: basamaklar[b]['line_count'] for b in BASAMAK_SIRASI},
        'yer': yer_sayim,
        'ulke': ulke_sayim,
        'il_merkezleri': il_merkezleri,
    }
    if toplam > butce:
        raise ButceAsildi(
            'üretilen toplam %d bayt (%.3f MB) > bütçe %d bayt (%.3f MB); '
            'HİÇBİR DOSYA YAZILMADI. Dosyalar: %s'
            % (toplam, toplam / 1e6, butce, butce / 1e6,
               json.dumps(olcum['dosyalar'])))
    dosyalar['vectors_manifest.json'] = manifest_bayt
    return dosyalar, olcum


def yaz(dosyalar: Dict[str, bytes], hedef: Path = CIKTI_DIZIN) -> None:
    """Dosyaları önce geçici adla yazar, sonra atomik olarak yerine koyar."""
    hedef.mkdir(parents=True, exist_ok=True)
    gecici = []
    for ad, veri in dosyalar.items():
        g = hedef / ('.%s.yaziliyor' % ad)
        g.write_bytes(veri)
        gecici.append((g, hedef / ad))
    for g, son in gecici:
        os.replace(g, son)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--kaynak', type=Path, default=VARSAYILAN_KAYNAK)
    ap.add_argument('--cikti', type=Path, default=CIKTI_DIZIN)
    ap.add_argument('--olcum', action='store_true',
                    help='yalnız ölç ve bas, dosya yazma')
    arg = ap.parse_args(argv)
    try:
        dosyalar, olcum = uret(arg.kaynak)
    except ButceAsildi as e:
        print('DUR: %s' % e, file=sys.stderr)
        return 2
    except KaynakHatasi as e:
        print('DUR (kaynak kanıtı): %s' % e, file=sys.stderr)
        return 3
    print(json.dumps(olcum, ensure_ascii=False, indent=1))
    if not arg.olcum:
        yaz(dosyalar, arg.cikti)
        for ad, veri in sorted(dosyalar.items()):
            print('  yazıldı: %s (%d bayt)' % (arg.cikti / ad, len(veri)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
