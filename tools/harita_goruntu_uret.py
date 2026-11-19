#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V307 / FS-HARİTA-GÖRÜNTÜ üretim aracı: Copernicus Sentinel-2 L2A sahnelerinden HRMA küre
ızgarasında KENDİ bulutsuz mozaiğimiz (harita paketinin görüntü bileşeni, tek SQLite dosyası).

Berke kararı (16 Kas): hazır EOX s2cloudless KULLANILMAZ (lisans çelişkisi + toplu indirme
izni yok). Kaynak: Element84 Earth Search STAC ``sentinel-2-l2a`` (AWS açık veri,
``sentinel-cogs`` kovası, istekçi-öder değil); varlıklar ``visual`` (TCI, 10 m, RGB uint8) ve
``scl`` (sahne sınıflandırması, 20 m). Lisans: AB Komisyonu "Legal notice on the use of
Copernicus Sentinel Data and Service Information" (Delegated Regulation (EU) No 1159/2013);
değiştirilmiş veri için atıf ``Contains modified Copernicus Sentinel data [Year]``.

ÇALIŞMA ORTAMI: üretim venv'i (rasterio/GDAL + numpy + requests). Ürün çalışma zamanı
bağımlılığı DEĞİLDİR; kullanıcıya giden tek şey üretilen ``.sqlite`` dosyasıdır ve okuyucusu
``hrma/analysis/map_pack_imagery.py`` (saf Python + sqlite3). Ağır kitaplıklar yalnız ilgili
adımın içinde içe aktarılır (testler saf işlevleri sistem Python'uyla sınar).

Adımlar (her biri kısa; kaldığı yerden devam eder; ağa çıkan adımlar alt süreçte koşar ve
GDAL ağ istatistiğinden ölçülen bayt ``indirme_defteri.jsonl``'a yazılır):
  ara      STAC araması (tarih + mevsim + bulut), aday sahneler          (ağ)
  planla   adayların SCL genel görünümü (~160 m) -> açgözlü sahne planı, gerekli bloklar,
           TCI genel görünümünden (~160 m) sahneler arası renk dengesi       (ağ, küçük)
  indir    planlanan sahnelerin YALNIZ gereken 1024 px TCI / 512 px SCL bloklarını COG aralık
           okumasıyla yerel seyrek kopyaya alır                              (ağ, büyük)
  mozaik   z10 blokları hâlinde: SCL maskesi (bulut/gölge/doygun + genişletme), en iyi piksel,
           renk dengesi, z13..z10 karoları (yerel)
  bitir    z9 karoları, kalite kapısı, metadata, sıralı yazım + VACUUM, sha256, künye (yerel)
  olc      indirme defterinin toplamı

Veri yok bölgeleri (bulut kalıntısı, Sentinel-2 kapsamı dışı açık deniz, paket alanı dışı)
SAYDAM kalır; yapay doldurma ve yapay deniz rengi YOKTUR.

Kullanım (venv):
  PY=~/HRMA-calisma/araclar/harita-venv/bin/python
  $PY -I tools/harita_goruntu_uret.py ara    --saha sinop_tr --liste <harita_paketleri.json>
  $PY -I tools/harita_goruntu_uret.py planla --saha sinop_tr --liste ...
  $PY -I tools/harita_goruntu_uret.py indir  --saha sinop_tr --sure 240
  $PY -I tools/harita_goruntu_uret.py mozaik --saha sinop_tr --liste ... --sure 240
  $PY -I tools/harita_goruntu_uret.py bitir  --saha sinop_tr --liste ... --kanit <dizin>
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
import types
import warnings
import zlib

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _hrma_modul(ad: str):
    """``hrma.analysis.<ad>``'ı paketin ağır ``__init__``'ini (scipy …) koşmadan yükler.

    Üretim venv'inde HRMA'nın bilimsel bağımlılıkları yoktur; ızgara (``tile_cache``) ve kap
    sabitleri (``map_pack_imagery``) yalnız standart kitaplık kullanır. Gerçek paket zaten
    yüklüyse o kullanılır.
    """
    if DEPO not in sys.path:
        sys.path.insert(0, DEPO)
    if 'hrma.analysis' not in sys.modules:
        try:
            importlib.import_module('hrma.analysis')     # tam ortam (test, uygulama)
        except ImportError:
            # Üretim venv'i: ağır __init__ yerine yalnız yol taşıyan paket nesneleri.
            importlib.import_module('hrma')
            for paket, yol in (('hrma.analysis', ('hrma', 'analysis')),
                               ('hrma.data', ('hrma', 'data'))):
                sys.modules.pop(paket, None)
                m = types.ModuleType(paket)
                m.__path__ = [os.path.join(DEPO, *yol)]      # type: ignore[attr-defined]
                sys.modules[paket] = m
    return importlib.import_module('hrma.analysis.' + ad)


tile_cache = _hrma_modul('tile_cache')
mpi = _hrma_modul('map_pack_imagery')

# ---------------------------------------------------------------------------
# 1) Sabitler (kaynaklı ya da "HRMA seçimi" diye beyanlı)
# ---------------------------------------------------------------------------
STAC_URL = 'https://earth-search.aws.element84.com/v1'
STAC_HOST = 'earth-search.aws.element84.com'
COLLECTION = 'sentinel-2-l2a'
#: COG varlıklarının izinli kaynağı (AWS açık veri, herkese açık; istekçi-öder değil).
COG_HOST = 'sentinel-cogs.s3.us-west-2.amazonaws.com'
#: Arama tarih aralığı (HRMA seçimi: son ~2,5 yıl, işlem tabanı 05.xx dönemi).
TARIH_ARALIGI = '2024-03-01T00:00:00Z/2026-10-31T23:59:59Z'
#: STAC sorgusunda granül bulut oranı üst sınırı [%] (HRMA seçimi: aday havuzu).
STAC_BULUT_UST = 40.0
#: MGRS karosu başına en çok aday (en az bulutlu; HRMA seçimi).
MGRS_BASINA_ADAY = 8
#: Sahaya göre tercih edilen aylar (HRMA seçimi; iklim gerekçesi RAPOR'da):
#: kuzey ılıman: yaz; Florida: kuru mevsim (Kas-Nis); Kaliforniya kıyısı: yaz deniz sisi
#: dışı; Kourou: kuru mevsim (Ağu-Kas); kutup üstü: karsız yaz; Mahia: güney yazı;
#: Tanegashima: yağmur/tayfun dışı; Sriharikota: muson dışı (Oca-May).
SAHA_AYLAR = {
    'sinop_tr': (6, 7, 8, 9), 'konya_tr': (5, 6, 7, 8, 9),
    'ksc_lc39a': (11, 12, 1, 2, 3, 4), 'ccsfs_slc40': (11, 12, 1, 2, 3, 4),
    'vandenberg_slc4e': (9, 10, 11, 3, 4), 'wallops_0a': (5, 6, 7, 8, 9, 10),
    'kourou_ela3': (8, 9, 10, 11), 'baikonur_1_5': (5, 6, 7, 8, 9),
    'esrange': (6, 7, 8), 'andoya': (6, 7, 8), 'mahia_lc1': (12, 1, 2, 3),
    'tanegashima': (10, 11, 12, 3, 4, 5), 'sriharikota': (1, 2, 3, 4, 5),
    'jiuquan_43': (4, 5, 6, 7, 8, 9, 10),
}
#: Sentinel-2 L2A SCL sınıfları (ESA Sen2Cor; Sentinel-2 L2A ürün tanımı):
#: 0 veri yok, 1 doygun/kusurlu, 2 karanlık alan/topoğrafik gölge, 3 bulut gölgesi,
#: 4 bitki, 5 bitki dışı, 6 su, 7 sınıflandırılmamış, 8 orta olasılıklı bulut,
#: 9 yüksek olasılıklı bulut, 10 ince sirrus, 11 kar/buz.
SCL_IYI = (4, 5, 6)
SCL_KABUL = (2, 7, 11)          # iyi yoksa ikinci geçişte (gerçek ölçüm; kar dahil)
SCL_KOTU = (1, 3, 8, 9, 10)
#: Kötü sınıf genişletmesi: planlamada 1 kaba piksel (~240 m), mozaikte z13 pikseli
#: cinsinden (≈ 8 x 7,6 m ≈ 60 m; bulut kenarı halesi) — HRMA seçimi.
KABA_GENISLETME = 1
INCE_GENISLETME = 8
#: Su üstünde kaçırılmış bulut: SCL "su" (6) dediği, KARADAN UZAK pikselde TCI'nın en küçük
#: kanalı bu eşiğin üstündeyse piksel BULUT sayılır (genişletilir, doldurulmaz). TCI 8 bit;
#: açık su koyudur (pilot Sinop denizi z11 ortanca mavi 39-73), bulut > 150 (ölçüldü: Sinop
#: kuzey kenarındaki iki bulut). İnce pus eşiğin altında kalır, künyede adıyla yazılır.
#: İlk deneme (eşik 130, kara tamponu yok) Canaveral'da kumsal/köpük şeridini ve liman
#: betonunu (SCL "su", parlak) sildi: gerçek veri kaybı -> eşik 150 + kara tamponu.
SU_BULUT_ESIK = 150
#: Kıyı geçişi: iki geçişten sonra hâlâ boş kalan, kıyı bandındaki (su ve karaya ≤ bu kadar
#: z13 pikseli, 16 px ≈ 120 m) piksellerde SCL bulut sınıfları 8/10 ve iyi/kabul sınıfları
#: GENİŞLETMESİZ kabul edilir. Gerekçe (pilot ölçümü, Canaveral KSC bloğu): Sen2Cor parlak
#: kumsalı ve kıyı köpüğünü her tarihte orta olasılıklı bulut/sirrus sayıyor; genişletmeyle
#: kıyı boyunca sürekli boşluk kalıyordu. Kabul edilen piksel sayısı künyede ayrı yazılır.
KIYI_BANDI = 16
SCL_KIYI = (4, 5, 6, 2, 7, 11, 8, 10)
#: Su-bulut kuralının uygulanmadığı kara tamponu [z13 px] (32 px ≈ 240 m enlem yönünde):
#: kıyı köpüğü, kumsal, liman yapıları. HRMA seçimi.
SU_BULUT_KARA_TAMPONU = 32
#: Su-bulut kuralının KALICI parlak su istisnası (17 Kas, Konya ölçümü): SCL "su" (6) ve
#: parlak (min(R,G,B) > SU_BULUT_ESIK) bir kaba hücre, en az bu kadar FARKLI edinimde
#: (datatake) VE o hücrenin su gözlemlerinin en az bu oranında parlaksa, bulut değil kalıcı
#: parlak yüzeydir (tuz gölü, tuzla): su-bulut kuralı orada uygulanmaz, ölçülen piksel
#: kullanılır. Gerekçe (ölçüm): Konya'da Tuz Gölü 13 edinimin su gözlemlerinin 8/8'inde parlak;
#: kural onu bulut sayıp 3,07 milyon z13 pikseli boşaltıyordu (kalite kapısı %1,27 > %0,5).
#: Geçici bulut aynı ~240 m hücrede tarihten tarihe tekrarlamaz. HRMA seçimi.
KALICI_PARLAK_SU_EN_AZ = 2
KALICI_PARLAK_SU_ORAN = 0.5
#: Kaba planlama ızgarası: z13 karosunun 1/16'sı = z8 pikseli (~240 m).
KABA_BOLUM = 16
#: Açgözlü planda bir sahnenin seçilmesi için en az kazanç: gözlenen alanın binde 0,5'i
#: ya da 20 kaba piksel (büyük olan) — HRMA seçimi. Plan en çok 16 sahne.
EN_AZ_KAZANC_ORANI = 0.0005
EN_AZ_KAZANC_PX = 20
EN_COK_SAHNE = 16
#: Renk dengesi: en az eşli piksel, kabul edilen kazanç aralığı (dışında birim dönüşüm).
RENK_EN_AZ_ESLI = 500
RENK_KAZANC_ARALIK = (0.6, 1.6)
#: Renk eşlemesine giren SCL sınıfları: bitki (4) ve bitki dışı kara (5).
RENK_KARA_SINIFLARI = (4, 5)
#: Tamamla adımı: her boş kaba hücre için en çok kaç yedek granül (HRMA seçimi). Pilot
#: ölçümü: Canaveral'da 2 yedek 466 blok / 876 MB isterken boşluk alanın %0,1'iydi;
#: 1 yedek + ikinci tur, bütçe/boşluk dengesini korur.
TAMAMLA_DERINLIK = 1
#: Tamamla adımının en çok tur sayısı (pilot: Sinop 2 turda 53.293 -> 1.124 px; üçüncü tur
#: kazancı bütçeye değmiyor). HRMA seçimi.
TAMAMLA_EN_COK_TUR = 2
#: Mozaik blok düzeyi (z10 karo = 8x8 z13 karo = 4096x4096 z13 pikseli).
BLOK_Z = 10
#: Blok kenarında SCL için ek pay [z13 px] (genişletmenin blok sınırında eksik kalmaması).
BLOK_PAY = 16
#: WebP kalite (faz 1 örneğiyle aynı: q80).
WEBP_KALITE = 80
#: Kalite kapısı: bulut kalıntısı (gözlenmiş ama hiç açık görülmemiş alan) / gözlenen alan
#: üst sınırı (HRMA seçimi). Aşılırsa ``bitir`` dosya YAZMAZ (çıkış 3).
BULUT_KALINTI_ESIK = 0.005
#: Toplam girdi indirme bütçesi (brif: ≤ 30 GB).
BUTCE_BAYT = 30 * 10 ** 9
#: GDAL ortamı (iş parçacığı 2; ortak kural).
GDAL_ORTAM = {
    'GDAL_NUM_THREADS': '2', 'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR',
    'CPL_VSIL_CURL_ALLOWED_EXTENSIONS': '.tif', 'GDAL_HTTP_MERGE_CONSECUTIVE_RANGES': 'YES',
    'GDAL_HTTP_MULTIPLEX': 'YES', 'GDAL_HTTP_MAX_RETRY': '4', 'GDAL_HTTP_RETRY_DELAY': '2',
    'VSI_CACHE': 'FALSE', 'GDAL_CACHEMAX': '256',
}
DOSYA_SURUMU = 'v2'
UA = 'HRMA-harita-goruntu/1 (offline map pack builder)'


def paket_dosya_adi(saha: str) -> str:
    """Görüntü bileşeni dosya adı (``map_packs.PACK_FILE_RE`` ile uyumlu)."""
    if not re.match(r'^[a-z0-9_]{1,40}$', saha):
        raise SystemExit('gecersiz saha kimligi')
    return 'hrma-goruntu-%s-%s.sqlite' % (saha, DOSYA_SURUMU)


# ---------------------------------------------------------------------------
# 2) Izgara yardımcıları (geometrinin sahibi tile_cache)
# ---------------------------------------------------------------------------

def alan_karolari(bbox, z: int = mpi.IMAGERY_ZOOM_MAX):
    """Paket kutusunu z düzeyindeki karo sınırlarına DIŞA doğru hizalar.

    Dönüş ``(tx0, ty0, tx1, ty1)`` (tx1/ty1 hariç) — görüntü alanı bu karoların birleşimidir.
    """
    w, s, e, n = bbox
    sp = tile_cache.tile_span_deg(z)
    tx0 = int(math.floor((w + 180.0) / sp + 1e-9))
    tx1 = int(math.ceil((e + 180.0) / sp - 1e-9))
    ty0 = int(math.floor((90.0 - n) / sp + 1e-9))
    ty1 = int(math.ceil((90.0 - s) / sp - 1e-9))
    mw, mh = tile_cache.matrix_size(z)
    if not (0 <= tx0 < tx1 <= mw and 0 <= ty0 < ty1 <= mh):
        raise ValueError('bbox matris disinda')
    return tx0, ty0, tx1, ty1


def alan_kutusu(karolar, z: int = mpi.IMAGERY_ZOOM_MAX):
    tx0, ty0, tx1, ty1 = karolar
    sp = tile_cache.tile_span_deg(z)
    return (-180.0 + tx0 * sp, 90.0 - ty1 * sp, -180.0 + tx1 * sp, 90.0 - ty0 * sp)


def piksel_derece(z: int) -> float:
    return tile_cache.tile_span_deg(z) / mpi.TILE_PX


def duzey_kurali() -> dict:
    """Halka kuralı (``mpi.IMAGERY_FULL_ZOOM_MAX`` + ``mpi.IMAGERY_RINGS``; tek tanım okuyucuda)."""
    return {'full_zoom_max': mpi.IMAGERY_FULL_ZOOM_MAX,
            'rings': [{'zoom': z, 'radius_km': float(r)} for z, r in mpi.IMAGERY_RINGS]}


def paket_merkezi(bbox):
    """Fırlatma noktası = paket kaydının merkezi (enlem, boylam). Paket kutusu
    ``map_packs.daire_bbox(enlem, boylam, 100 km)`` ile kurulduğu için kutunun orta noktası
    saha ön ayarının konumudur (liste 6 ondalıkla yazılı: ≤ 0,11 m)."""
    w, s, e, n = bbox
    return ((s + n) / 2.0, (w + e) / 2.0)


def halka_karolari(z: int, merkez, yaricap_km: float, bbox):
    """z düzeyinde halkaya değen (``mpi.karo_halkada_mi``) ve paket alanının (z düzeyinde dışa
    hizalı kutu) içindeki karolar: sıralı (x, y) listesi."""
    lat0, lon0 = merkez
    tx0, ty0, tx1, ty1 = alan_karolari(bbox, z)
    dlat = yaricap_km / mpi.KM_PER_DEG
    dlon = yaricap_km / (mpi.KM_PER_DEG * math.cos(math.radians(lat0)))
    sp = tile_cache.tile_span_deg(z)
    cx0 = max(tx0, int(math.floor((lon0 - dlon + 180.0) / sp)) - 1)
    cx1 = min(tx1, int(math.floor((lon0 + dlon + 180.0) / sp)) + 2)
    cy0 = max(ty0, int(math.floor((90.0 - lat0 - dlat) / sp)) - 1)
    cy1 = min(ty1, int(math.floor((90.0 - lat0 + dlat) / sp)) + 2)
    return [(x, y) for y in range(cy0, cy1) for x in range(cx0, cx1)
            if mpi.karo_halkada_mi(z, x, y, lat0, lon0, yaricap_km)]


def halka_plani(plan) -> dict:
    """Plandan halka kuralının karo kümeleri: {z: set((x, y))} (yalnız halkalı düzeyler)."""
    kural = plan['duzey_kurali']
    merkez = tuple(plan['merkez'])
    return {h['zoom']: set(halka_karolari(h['zoom'], merkez, h['radius_km'], plan['bbox']))
            for h in kural['rings']}


def halka_bloklari(halkalar) -> set:
    """Halka karolarına değen z10 blokları (tam çözünürlükle mozaiklenir)."""
    out = set()
    for z, karolar in halkalar.items():
        k = z - BLOK_Z
        out.update((x >> k, y >> k) for x, y in karolar)
    return out


def blok_halka_maskeleri(halkalar, bx: int, by: int):
    """Bloğun z13 pikseli ızgarasında her halkanın maskesi: {'z<düzey>': bool (N, N)}."""
    import numpy as np
    f = 1 << (mpi.IMAGERY_ZOOM_MAX - BLOK_Z)
    N = mpi.TILE_PX * f
    out = {}
    for z, karolar in sorted(halkalar.items()):
        k = mpi.IMAGERY_ZOOM_MAX - z
        boy = mpi.TILE_PX << k
        m = np.zeros((N, N), bool)
        for x, y in karolar:
            if (x >> (z - BLOK_Z), y >> (z - BLOK_Z)) != (bx, by):
                continue
            c0 = ((x << k) - bx * f) * mpi.TILE_PX
            r0 = ((y << k) - by * f) * mpi.TILE_PX
            m[r0:r0 + boy, c0:c0 + boy] = True
        out['z%d' % z] = m
    return out


def kapsama_degeri(alfa_ortalama: float, tam: bool, bos_degil: bool) -> int:
    """Karo ``coverage`` değeri: alfa ortalaması x 10000; 10000 ⟺ tam karo; veri varsa ≥ 1."""
    if tam:
        return 10000
    c = int(alfa_ortalama * 10000)
    if bos_degil and c < 1:
        c = 1
    return min(c, 9999)


def atif_metni(yillar) -> str:
    ys = sorted(set(int(y) for y in yillar))
    return mpi.ATTRIBUTION_TEMPLATE.format(years=', '.join(str(y) for y in ys))


def sahne_anahtari(oz: dict) -> tuple:
    """Aynı (MGRS, datatake) için yinelenen ürünlerde sonek büyük olan kalır."""
    m = re.match(r'^S2[ABC]_[0-9A-Z]{5}_\d{8}_(\d+)_L2A$', oz['id'])
    return (oz['mgrs'], oz['datatake']), int(m.group(1)) if m else 0


def adaylari_sec(adaylar, aylar, k: int = MGRS_BASINA_ADAY):
    """Ay süzgeci + yinelenen ürün ayıklama + MGRS başına en az bulutlu k aday (belirlenimci)."""
    tekil = {}
    for a in adaylar:
        if int(a['datetime'][5:7]) not in aylar or a['nodata'] >= 90.0:
            continue
        anah, sonek = sahne_anahtari(a)
        if anah not in tekil or sonek > tekil[anah][0]:
            tekil[anah] = (sonek, a)
    mgrs = {}
    for _s, a in tekil.values():
        mgrs.setdefault(a['mgrs'], []).append(a)
    secilen = set()
    for m in sorted(mgrs):
        for a in sorted(mgrs[m], key=lambda a: (a['cloud'], a['datetime'], a['id']))[:k]:
            secilen.add(a['datatake'])
    # Seçilen edinimlerin (datatake) BÜTÜN granülleri: bir edinimin komşu MGRS
    # granülleri aynı gün/aynı yörüngedir; biri havuz dışında kalırsa temel edinim alanın
    # bir parçasını kaplayamaz ve orada başka tarihten dikiş oluşur (pilot ölçümü: Sinop
    # kuzey sıra granülleri havuzda yoktu, denizde düz dikiş).
    out = [a for _s, a in tekil.values() if a['datatake'] in secilen]
    return sorted(out, key=lambda a: a['id'])


def kabuk_href(href: str) -> str:
    """COG adresi yalnız izinli HTTPS kaynaktan; değilse SystemExit."""
    from urllib.parse import urlparse
    u = urlparse(href)
    if u.scheme != 'https' or u.hostname != COG_HOST or u.port not in (None, 443) \
            or u.username or not u.path.endswith('.tif'):
        raise SystemExit('izin listesi disi adres: %s' % href[:120])
    return '/vsicurl/' + href


# ---------------------------------------------------------------------------
# 3) Yollar, defter
# ---------------------------------------------------------------------------

class Yollar:
    """Dizinler. ``onbellek`` (varsayılan ``calisma``): indirme önbelleği (STAC anlık görüntüsü,
    granül seyrek kopyaları) ve indirme defteri — sahalar arasında ORTAK, kalıcı. ``calisma``:
    sahanın plan/iş dosyaları (``gecici/<saha>``) ve paketler. 18 Kas: hafif paketler yeni
    çalışma dizinine yazılır, 16 Kas önbelleği yerinde kalır (brif GÖRÜNTÜ-HAFİF)."""

    def __init__(self, calisma: str, saha: str, onbellek: str = None):
        self.calisma = calisma
        self.onbellek = onbellek or calisma
        self.saha = saha
        self.stac = os.path.join(self.onbellek, 'indirilen', 'stac')
        self.cog = os.path.join(self.onbellek, 'indirilen', 'cog')
        self.gecici = os.path.join(calisma, 'gecici', saha)
        self.paketler = os.path.join(calisma, 'paketler')
        for d in (self.stac, self.cog, self.gecici, self.paketler):
            os.makedirs(d, exist_ok=True)
        self.adaylar = os.path.join(self.stac, '%s_adaylar.json' % saha)
        self.plan = os.path.join(self.gecici, 'plan.json')
        self.kaba = os.path.join(self.gecici, 'kaba_scl.npz')
        self.kaba_tci = os.path.join(self.gecici, 'kaba_tci.npz')
        self.is_db = os.path.join(self.gecici, 'is.sqlite')
        self.defter = os.path.join(self.onbellek, 'indirme_defteri.jsonl')
        self.paket = os.path.join(self.paketler, paket_dosya_adi(saha))

    def granul_dizini(self, gid: str) -> str:
        if not re.match(r'^S2[ABC]_[0-9A-Z]{5}_\d{8}_\d+_L2A$', gid):
            raise SystemExit('gecersiz granul kimligi')
        d = os.path.join(self.cog, gid)
        os.makedirs(d, exist_ok=True)
        return d


def defter_toplami(defter: str) -> dict:
    top = {'gdal_bayt': 0, 'istek_bayt': 0, 'sure_s': 0.0, 'saha': {}, 'toplam_bayt': 0}
    if not os.path.exists(defter):
        return top
    with open(defter, encoding='utf-8') as fh:
        for satir in fh:
            if not satir.strip():
                continue
            k = json.loads(satir)
            top['gdal_bayt'] += k.get('gdal_bayt', 0)
            top['istek_bayt'] += k.get('istek_bayt', 0)
            top['sure_s'] += k.get('sure_s', 0.0)
            s = top['saha'].setdefault(k['saha'], {})
            a = s.setdefault(k['adim'], {'gdal_bayt': 0, 'istek_bayt': 0, 'sure_s': 0.0, 'kosu': 0})
            a['gdal_bayt'] += k.get('gdal_bayt', 0)
            a['istek_bayt'] += k.get('istek_bayt', 0)
            a['sure_s'] += k.get('sure_s', 0.0)
            a['kosu'] += 1
    top['toplam_bayt'] = top['gdal_bayt'] + top['istek_bayt']
    return top


def ag_istatistigi_coz(stderr: str) -> int:
    """GDAL ``CPL_VSIL_SHOW_NETWORK_STATS`` çıktısından toplam GET baytı (yoksa 0)."""
    i = stderr.rfind('Network statistics:')
    if i < 0:
        return 0
    try:
        d = json.loads(stderr[i + len('Network statistics:'):].strip())
    except ValueError:
        return 0
    return int(d.get('methods', {}).get('GET', {}).get('downloaded_bytes', 0))


def _olcumlu_kos(argv, y: Yollar, adim: str) -> int:
    """Ağa çıkan adımı alt süreçte koşar; ölçülen baytı deftere yazar."""
    env = dict(os.environ, CPL_VSIL_SHOW_NETWORK_STATS='YES', HRMA_GORUNTU_COCUK='1')
    env.update(GDAL_ORTAM)
    t0 = time.time()
    p = subprocess.run([sys.executable, '-I', os.path.abspath(__file__)] + argv, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    sure = time.time() - t0
    istek = 0
    cikti = p.stdout
    k = cikti.find('Network statistics:')
    for satir in (cikti if k < 0 else cikti[:k]).splitlines():
        if satir.startswith('ISTEK_BAYT '):
            istek += int(satir.split()[1])
        else:
            print(satir)
    hata = p.stderr
    j = hata.rfind('Network statistics:')
    if j >= 0:
        hata = hata[:j]
    hata = '\n'.join(s for s in hata.splitlines() if 'NotGeoreferencedWarning' not in s
                     and 'rd = ' not in s and 'writer(' not in s)
    if hata.strip():
        sys.stderr.write(hata[-4000:] + '\n')
    kayit = {'zaman': _dt.datetime.now().isoformat(timespec='seconds'), 'adim': adim,
             'saha': y.saha,
             # GDAL istatistiği stdout'a basar (ölçüldü); iki akış da taranır.
             'gdal_bayt': max(ag_istatistigi_coz(p.stdout), ag_istatistigi_coz(p.stderr)),
             'istek_bayt': istek,
             'sure_s': round(sure, 1), 'cikis_kodu': p.returncode}
    with open(y.defter, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(kayit, ensure_ascii=False) + '\n')
    print('DEFTER', json.dumps(kayit, ensure_ascii=False))
    return p.returncode


def paket_kutusu(liste: str, saha: str):
    with open(liste, encoding='utf-8') as fh:
        m = json.load(fh)
    for p in m.get('packs', []):
        if p.get('id') == saha:
            b = p['bbox']
            return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
    raise SystemExit('saha listede yok: %s' % saha)


# ---------------------------------------------------------------------------
# 4) ara — STAC araması
# ---------------------------------------------------------------------------

def adim_ara(a, y: Yollar):
    import requests
    bbox = paket_kutusu(a.liste, a.saha)
    govde = {'collections': [COLLECTION], 'bbox': list(bbox), 'datetime': TARIH_ARALIGI,
             'query': {'eo:cloud_cover': {'lt': STAC_BULUT_UST}}, 'limit': 200}
    url = STAC_URL + '/search'
    oturum = requests.Session()
    oturum.headers['User-Agent'] = UA
    ozet, bayt, sayfa = [], 0, 0
    while url:
        from urllib.parse import urlparse
        if urlparse(url).hostname != STAC_HOST or not url.startswith('https://'):
            raise SystemExit('STAC disi adres')
        r = oturum.post(url, json=govde, timeout=90)
        bayt += len(r.content)
        r.raise_for_status()
        d = r.json()
        sayfa += 1
        for f in d.get('features', []):
            p = f['properties']
            vis, scl = f['assets']['visual'], f['assets']['scl']
            ozet.append({
                'id': f['id'], 'datetime': p['datetime'], 'cloud': float(p['eo:cloud_cover']),
                'nodata': float(p.get('s2:nodata_pixel_percentage', 0.0)),
                'mgrs': p.get('grid:code'),
                'datatake': p.get('s2:datatake_id') or f['id'].split('_')[0] + '_' + f['id'].split('_')[2],
                'epsg': int(p.get('proj:epsg')), 'baseline': p.get('s2:processing_baseline'),
                'bbox': f['bbox'], 'visual': vis['href'], 'scl': scl['href'],
                'visual_transform': vis.get('proj:transform'), 'visual_shape': vis.get('proj:shape'),
                'scl_transform': scl.get('proj:transform'), 'scl_shape': scl.get('proj:shape'),
                'snow': p.get('s2:snow_ice_percentage'), 'shadow': p.get('s2:cloud_shadow_percentage'),
            })
        url = None
        for ln in d.get('links', []):
            if ln.get('rel') == 'next':
                url = ln['href']
                govde = ln.get('body', govde)
        if sayfa >= 50:
            break
    ozet.sort(key=lambda o: o['id'])
    with open(y.adaylar, 'w', encoding='utf-8') as fh:
        json.dump({'saha': a.saha, 'bbox': bbox, 'tarih': TARIH_ARALIGI, 'bulut_lt': STAC_BULUT_UST,
                   'sayfa': sayfa, 'ogeler': ozet}, fh, indent=0)
    print('ara', a.saha, 'oge', len(ozet), 'sayfa', sayfa)
    print('ISTEK_BAYT %d' % bayt)


# ---------------------------------------------------------------------------
# 5) planla — kaba SCL, açgözlü sahne seçimi, bloklar, renk dengesi
# ---------------------------------------------------------------------------

def genislet(m, r: int):
    """İkili maskeyi (2r+1)x(2r+1) kutuyla genişletir (birikimli toplam; numpy)."""
    import numpy as np
    if r <= 0:
        return m.copy()
    a = m.astype(np.int32)
    c = np.cumsum(np.pad(a, ((0, 0), (r + 1, r))), axis=1)
    a = c[:, 2 * r + 1:] - c[:, :-2 * r - 1]
    c = np.cumsum(np.pad(a, ((r + 1, r), (0, 0))), axis=0)
    a = c[2 * r + 1:, :] - c[:-2 * r - 1, :]
    return a > 0


def maskeler(sinif, r: int):
    """SCL dizisinden (iyi, kabul, gözlenen) maskeleri; kötü sınıf r pikselle genişletilir."""
    import numpy as np
    kotu = genislet(np.isin(sinif, SCL_KOTU), r)
    iyi = np.isin(sinif, SCL_IYI) & ~kotu
    kabul = np.isin(sinif, SCL_KABUL) & ~kotu
    return iyi, kabul, sinif != 0


def acgozlu_plan(edinim_iyi: dict, edinim_kabul: dict, gozlenen):
    """Açgözlü küme örtüsü: önce İYİ, sonra KABUL sınıflarıyla. Belirlenimci (eşitlikte ad).

    Dönüş: ``[(edinim, gecis, kazanc_px)]`` ve atama dizisi (sıra no; -1 boş).
    """
    import numpy as np
    n_goz = int(gozlenen.sum())
    esik = max(EN_AZ_KAZANC_PX, int(EN_AZ_KAZANC_ORANI * n_goz))
    ortu = np.zeros_like(gozlenen)
    secim = []
    for gecis, kume in (('iyi', edinim_iyi), ('kabul', edinim_kabul)):
        while len(secim) < EN_COK_SAHNE:
            en, en_ad = 0, None
            for ad in sorted(kume):
                k = int((kume[ad] & ~ortu).sum())
                if k > en:
                    en, en_ad = k, ad
            if en_ad is None or en < esik:
                break
            secim.append((en_ad, gecis, en))
            ortu |= kume[en_ad]
    atama = np.full(gozlenen.shape, -1, np.int16)
    for i, (ad, gecis, _k) in enumerate(secim):
        kume = edinim_iyi if gecis == 'iyi' else edinim_kabul
        atama[(atama < 0) & kume[ad]] = i
    return secim, atama


def renk_uydur(ref, kaynak, maske):
    """Bant başına y = a·x + b, ortalama + standart sapma eşlemesiyle (aykırı ayıklamalı).

    En küçük kareler eğimi iki tarih arasındaki gerçek değişimi gürültü sayıp eğimi 1'in
    altına çeker (regresyon seyrelmesi; ilk denemede 0,81-0,86 ölçüldü); ortalama/sapma
    eşlemesi bu yanlılığı taşımaz. Eşli farkın ortancadan 3·MAD'den uzak olanları (ekin
    hasadı, su düzeyi …) dışarıda kalır. Yetersiz eşli piksel ya da aralık dışı kazanç ->
    birim dönüşüm (``'birim'``).
    """
    import numpy as np
    out = []
    for b in range(3):
        x = kaynak[b][maske].astype(np.float64)
        yv = ref[b][maske].astype(np.float64)
        if x.size >= RENK_EN_AZ_ESLI:
            fark = yv - x
            med = np.median(fark)
            mad = np.median(np.abs(fark - med)) + 1e-9
            tut = np.abs(fark - med) <= 3.0 * 1.4826 * mad
            x, yv = x[tut], yv[tut]
        if x.size < RENK_EN_AZ_ESLI or x.std() < 1e-6:
            out.append((1.0, 0.0, int(x.size), 'birim'))
            continue
        a_ = float(yv.std() / x.std())
        b_ = float(yv.mean() - a_ * x.mean())
        if not (RENK_KAZANC_ARALIK[0] <= a_ <= RENK_KAZANC_ARALIK[1]):
            out.append((1.0, 0.0, int(x.size), 'birim'))
        else:
            out.append((a_, b_, int(x.size), 'uyduruldu'))
    return out


def tiff_karo_baytlari(bas: bytes):
    """Klasik/BigTIFF başlığından İLK IFD'nin (tam çözünürlük) karo bayt sayıları.

    COG'da IFD'ler ve dizileri dosyanın başındadır; dizi verilen baytın dışındaysa None.
    Dönüş: (karo_genislik, karo_yukseklik, genislik, yukseklik, [bayt …]) ya da None.
    """
    import struct as st
    if bas[:2] == b'II':
        e = '<'
    elif bas[:2] == b'MM':
        e = '>'
    else:
        return None
    try:
        return _tiff_karo_baytlari(bas, e, st)
    except st.error:
        return None                      # kesik başlık: dizi/IFD verilen baytın dışında


def _tiff_karo_baytlari(bas, e, st):
    sur = st.unpack_from(e + 'H', bas, 2)[0]
    tip_boy = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 16: 8}
    if sur == 42:
        ifd = st.unpack_from(e + 'I', bas, 4)[0]
        n = st.unpack_from(e + 'H', bas, ifd)[0]
        gir, boy, sayf, degf = ifd + 2, 12, 'I', 'I'
    elif sur == 43:
        ifd = st.unpack_from(e + 'Q', bas, 8)[0]
        n = st.unpack_from(e + 'Q', bas, ifd)[0]
        gir, boy, sayf, degf = ifd + 8, 20, 'Q', 'Q'
    else:
        return None
    etiket = {}
    for k in range(n):
        o = gir + k * boy
        tag, tip = st.unpack_from(e + 'HH', bas, o)
        say = st.unpack_from(e + sayf, bas, o + 4)[0]
        ob = tip_boy.get(tip, 1) * say
        kap = 4 if sur == 42 else 8
        if ob <= kap:
            ofs = o + 4 + (4 if sur == 42 else 8)
        else:
            ofs = st.unpack_from(e + degf, bas, o + 4 + (4 if sur == 42 else 8))[0]
        if ofs + ob > len(bas):
            if tag in (256, 257, 322, 323, 325):
                return None
            continue
        fmt = {3: 'H', 4: 'I', 16: 'Q'}.get(tip)
        if fmt:
            etiket[tag] = list(st.unpack_from(e + fmt * say, bas, ofs))
    try:
        return (etiket[322][0], etiket[323][0], etiket[256][0], etiket[257][0], etiket[325])
    except KeyError:
        return None


def _kaba_izgara(bbox):
    from rasterio.transform import from_origin
    karolar = alan_karolari(bbox)
    kw, ks, ke, kn = alan_kutusu(karolar)
    d = tile_cache.tile_span_deg(mpi.IMAGERY_ZOOM_MAX) / KABA_BOLUM
    W = (karolar[2] - karolar[0]) * KABA_BOLUM
    H = (karolar[3] - karolar[1]) * KABA_BOLUM
    return karolar, from_origin(kw, kn, d, d), W, H


def _kaba_oku(href, T, W, H, ovr: int, resampling):
    import rasterio
    from rasterio.vrt import WarpedVRT
    with rasterio.open(kabuk_href(href), overview_level=ovr) as src:
        with WarpedVRT(src, crs='EPSG:4326', transform=T, width=W, height=H,
                       resampling=resampling, src_nodata=0, nodata=0) as v:
            return v.read()


def granul_bloklari(m, c: dict, T) -> set:
    """Kaba maske ``m``'nin granül ``c``'de dokunduğu 1024 px (10,24 km) blokları."""
    import numpy as np
    from rasterio.warp import transform as donustur
    if not m.any():
        return set()
    rr, cc = np.nonzero(m)
    lon = T.c + (cc + 0.5) * T.a
    lat = T.f + (rr + 0.5) * T.e
    xs, ys = donustur('EPSG:4326', 'EPSG:%d' % c['epsg'], lon.tolist(), lat.tolist())
    xs, ys = np.asarray(xs), np.asarray(ys)
    t = c['visual_transform']
    x0, y0 = t[2], t[5]
    pay = abs(T.a) * 111320.0            # bir kaba piksel (m), güvenli üst sınır
    bloklar = set()
    for dx in (-pay, 0.0, pay):
        for dy in (-pay, 0.0, pay):
            bc = np.floor((xs + dx - x0) / 10240.0).astype(int)
            br = np.floor((y0 - (ys + dy)) / 10240.0).astype(int)
            ok = (bc >= 0) & (bc < 11) & (br >= 0) & (br < 11)
            bloklar.update(zip(br[ok].tolist(), bc[ok].tolist()))
    return bloklar


def renk_dengesi(sirali_edinimler, edinim, onceki, tci, H, W):
    """Edinim sırasına göre kaba (~240 m) referans mozaiği kurar; her edinimin kara
    piksellerinden (SCL 4/5) birincile göre doğrusal kazanç/kayma uydurur."""
    import numpy as np
    ref = np.zeros((3, H, W), np.float32)
    ref_dolu = np.zeros((H, W), bool)
    ref_kara = np.zeros((H, W), bool)
    renk = {}
    for sira, dt_ in enumerate(sirali_edinimler):
        kaynak = np.zeros((3, H, W), np.float32)
        kdolu = np.zeros((H, W), bool)
        kkara = np.zeros((H, W), bool)
        for g in sorted(gid for gid in edinim[dt_] if gid in tci):
            iy, kb, _o = maskeler(onceki[g], KABA_GENISLETME)
            mm = (iy | kb) & ~kdolu & (tci[g].sum(0) > 0)
            kaynak[:, mm] = tci[g][:, mm]
            kdolu |= mm
            kkara |= mm & np.isin(onceki[g], RENK_KARA_SINIFLARI)
        if sira == 0:
            renk[dt_] = [(1.0, 0.0, int(kkara.sum()), 'referans')] * 3
        else:
            # Su (6) eşlemeye girmez: deniz rengi tarihten tarihe gerçekten değişir
            # (fitoplankton, bulanıklık, güneş yansıması); yalnız kara pikselleri.
            renk[dt_] = renk_uydur(ref, kaynak, ref_kara & kkara)
        duz = np.stack([kaynak[b] * renk[dt_][b][0] + renk[dt_][b][1] for b in range(3)])
        yeni = kdolu & ~ref_dolu
        ref[:, yeni] = duz[:, yeni]
        ref_kara |= yeni & kkara
        ref_dolu |= yeni
    return renk


def indirme_tahmini(granuller) -> int:
    """Her granülün ``bloklar`` listesi için TCI+SCL karo baytı (TIFF başlığından, 64 KiB
    aralık isteği); ``tahmini_bayt`` alanına yazar. Dönüş: istek baytı."""
    import requests
    oturum = requests.Session()
    oturum.headers['User-Agent'] = UA
    istek_bayt = 0
    baslik = {}
    for g in granuller:
        tah = 0
        for anah in ('visual', 'scl'):
            href = g[anah]
            kabuk_href(href)
            if href not in baslik:
                r = oturum.get(href, headers={'Range': 'bytes=0-65535'}, timeout=60)
                istek_bayt += len(r.content)
                if r.status_code != 206:
                    raise SystemExit('aralik istegi desteklenmedi: %d' % r.status_code)
                t = tiff_karo_baytlari(r.content)
                if t is None:
                    raise SystemExit('TIFF basligi cozulemedi: %s' % href[-60:])
                baslik[href] = t
            kw_, kh_, w_, h_, baytlar = baslik[href]
            sut = -(-w_ // kw_)
            for br, bc in g['bloklar']:
                tah += baytlar[br * sut + bc]
        g['tahmini_bayt'] = tah
    return istek_bayt


def _kaba_scl_yukle(y, adaylar, T, W, H):
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
    from rasterio.enums import Resampling
    onceki = {}
    if os.path.exists(y.kaba):
        z = np.load(y.kaba)
        onceki = {k: z[k] for k in z.files}
    eksik = [c for c in adaylar if c['id'] not in onceki]

    def oku(c):
        return c['id'], _kaba_oku(c['scl'], T, W, H, 2, Resampling.nearest)[0]
    with ThreadPoolExecutor(4) as ex:
        for gid, arr in ex.map(oku, eksik):
            onceki[gid] = arr
    if eksik:
        np.savez_compressed(y.kaba, **onceki)
    return onceki


def _kaba_tci_yukle(y, gidler, gran, T, W, H):
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
    from rasterio.enums import Resampling
    tci = {}
    if os.path.exists(y.kaba_tci):
        z = np.load(y.kaba_tci)
        tci = {k: z[k] for k in z.files}
    gerek = sorted(set(gidler) - set(tci))

    def oku_tci(gid):
        return gid, _kaba_oku(gran[gid]['visual'], T, W, H, 3, Resampling.bilinear)
    with ThreadPoolExecutor(4) as ex:
        for gid, arr in ex.map(oku_tci, gerek):
            tci[gid] = arr
    if gerek:
        np.savez_compressed(y.kaba_tci, **tci)
    return tci


def adim_planla(a, y: Yollar):
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
    from rasterio.enums import Resampling
    bbox = paket_kutusu(a.liste, a.saha)
    with open(y.adaylar, encoding='utf-8') as fh:
        ad = json.load(fh)
    adaylar = adaylari_sec(ad['ogeler'], SAHA_AYLAR[a.saha])
    karolar, T, W, H = _kaba_izgara(bbox)
    print('aday', len(adaylar), 'kaba izgara', W, H)
    # 1) Kaba SCL (genel görünüm 3. düzey = x8 = 160 m); önbellekli.
    onceki = _kaba_scl_yukle(y, adaylar, T, W, H)
    # 2) Edinim (datatake) maskeleri
    gran = {c['id']: c for c in adaylar}
    edinim = {}
    for c in adaylar:
        edinim.setdefault(c['datatake'], []).append(c['id'])
    e_iyi, e_kabul = {}, {}
    gozlenen = np.zeros((H, W), bool)
    for dt_, gids in edinim.items():
        iy = np.zeros((H, W), bool)
        kb = np.zeros((H, W), bool)
        for g in gids:
            i_, k_, o_ = maskeler(onceki[g], KABA_GENISLETME)
            iy |= i_
            kb |= k_
            gozlenen |= o_
        e_iyi[dt_], e_kabul[dt_] = iy, kb & ~iy
    secim, atama = acgozlu_plan(e_iyi, e_kabul, gozlenen)
    # 3) Granül bazında gerekli bloklar (atanan alan + 2 kaba piksel pay)
    granuller = []
    for sira, (dt_, gecis, kazanc) in enumerate(secim):
        alan = genislet(atama == sira, 2)
        for g in sorted(edinim[dt_]):
            c = gran[g]
            bloklar = granul_bloklari(alan & (onceki[g] != 0), c, T)
            if not bloklar:
                continue
            granuller.append({'id': g, 'edinim': dt_, 'sira': sira, 'gecis': gecis,
                              'bloklar': sorted(bloklar), 'cloud': c['cloud'],
                              'datetime': c['datetime'], 'mgrs': c['mgrs'], 'epsg': c['epsg'],
                              'bbox': c['bbox'], 'visual': c['visual'], 'scl': c['scl']})
    # 4) Renk dengesi: seçilen granüllerin TCI genel görünümü (x16 = 160 m)
    tci = _kaba_tci_yukle(y, [g['id'] for g in granuller], gran, T, W, H)
    renk = renk_dengesi([d for d, _g, _k in secim], edinim, onceki, tci, H, W)
    # 5) Kesin indirme tahmini (TIFF başlığındaki karo bayt sayıları)
    print('ISTEK_BAYT %d' % indirme_tahmini(granuller))
    n_goz = int(gozlenen.sum())
    ortu_iyi = int(((atama >= 0) & np.isin(atama, [i for i, s in enumerate(secim) if s[1] == 'iyi'])).sum())
    plan = {
        'saha': a.saha, 'olusturma': _dt.date.today().isoformat(), 'bbox': list(bbox),
        'merkez': list(paket_merkezi(bbox)), 'duzey_kurali': duzey_kurali(),
        'dis_kaynak': 'tam_10m', 'halka_hazir': {'yeni_plan': True},
        'alan_karolari_z13': list(karolar), 'alan_kutusu': list(alan_kutusu(karolar)),
        'kaba_izgara': {'W': W, 'H': H, 'derece': T.a}, 'aylar': list(SAHA_AYLAR[a.saha]),
        'aday_sayisi': len(adaylar),
        'secim': [{'edinim': d, 'gecis': g, 'kazanc_px': k,
                   'tarih': min(gran[x]['datetime'] for x in edinim[d])[:10],
                   'renk': renk.get(d)} for d, g, k in secim],
        'granuller': granuller,
        'kaba_istatistik': {
            'kaba_px': W * H, 'gozlenen_px': n_goz, 'gozlenmeyen_px': W * H - n_goz,
            'ortulen_iyi_px': ortu_iyi, 'ortulen_toplam_px': int((atama >= 0).sum()),
            'bulut_kalintisi_px': int((gozlenen & (atama < 0)).sum()),
        },
        'blok_toplami': sum(len(g['bloklar']) for g in granuller),
        'tahmini_indirme_bayt': sum(g['tahmini_bayt'] for g in granuller),
    }
    with open(y.plan, 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, indent=1, ensure_ascii=False)
    print('plan', a.saha, 'sahne', len(secim), 'granul', len(granuller), 'blok', plan['blok_toplami'],
          'tahmini_indirme_bayt', plan['tahmini_indirme_bayt'])
    print(json.dumps(plan['kaba_istatistik']))
    for s in plan['secim']:
        print(' ', s['tarih'], s['edinim'], s['gecis'], s['kazanc_px'],
              [tuple(round(v, 3) for v in r[:2]) for r in (s['renk'] or [])])


def adim_tamamla(a, y: Yollar):
    """İnce düzeyde boş kalan kaba hücreler için ek sahne blokları (ölçüme dayalı).

    Kaba plan (~160 m SCL) küçük bulutları görmez; mozaikte bunlar 60 m genişletmeyle
    boşluk bırakır. Burada: mozaiğin kaydettiği boş kaba hücrelerde İYİ gözlemi olan,
    o bölgede bloğu HENÜZ İNDİRİLMEMİŞ granüller öncelik sırasıyla (önce plandaki edinimler,
    sonra boşlukta en çok iyi pikseli olan) her hücreye en çok ``TAMAMLA_DERINLIK`` yedek
    olacak kadar eklenir.
    Etkilenen z10 blokları yeniden mozaiklenmek üzere işaretlenir.
    """
    import numpy as np
    bbox = paket_kutusu(a.liste, a.saha)
    with open(y.plan, encoding='utf-8') as fh:
        plan = json.load(fh)
    with open(y.adaylar, encoding='utf-8') as fh:
        adaylar = adaylari_sec(json.load(fh)['ogeler'], SAHA_AYLAR[a.saha])
    if len(plan.get('tamamla_turlari', [])) >= TAMAMLA_EN_COK_TUR:
        print('tamamla', a.saha, 'tur siniri', TAMAMLA_EN_COK_TUR)
        return
    gran = {c['id']: c for c in adaylar}
    karolar, T, W, H = _kaba_izgara(bbox)
    onceki = _kaba_scl_yukle(y, adaylar, T, W, H)
    db = is_db_ac(y.is_db)
    bos = np.zeros((H, W), bool)
    bos_bloklar = []
    for bx, by, ist in db.execute('SELECT bx, by, istatistik FROM bloklar'):
        d = json.loads(ist)
        if d.get('bos_kaba'):
            bos_bloklar.append((bx, by))
            for r, c in d['bos_kaba']:
                if 0 <= r < H and 0 <= c < W:
                    bos[r, c] = True
    if not bos.any():
        print('tamamla', a.saha, 'bos yok')
        db.close()
        return
    mevcut = {g['id']: set(tuple(b) for b in g['bloklar']) for g in plan['granuller']}
    sira_no = {s_['edinim']: i for i, s_ in enumerate(plan['secim'])}
    iyi = {gid: maskeler(onceki[gid], KABA_GENISLETME)[0] for gid in gran}
    oncelik = []
    for gid, c in gran.items():
        n = int((bos & iyi[gid]).sum())
        if n:
            oncelik.append((0 if c['datatake'] in sira_no else 1,
                            sira_no.get(c['datatake'], 0), -n, gid))
    derinlik = np.zeros((H, W), np.int8)
    ekler = {}
    for _o, _s, _n, gid in sorted(oncelik):
        m = bos & iyi[gid] & (derinlik < TAMAMLA_DERINLIK)
        if not m.any():
            continue
        yeni = granul_bloklari(genislet(m, 1) & (onceki[gid] != 0), gran[gid], T) \
            - mevcut.get(gid, set())
        if not yeni:
            continue
        derinlik[m] += 1
        ekler[gid] = yeni
    # Yeni edinimler sıranın sonuna (öncelik sırasıyla); renk dengesi bütün sıra için
    edinim = {}
    for c in adaylar:
        edinim.setdefault(c['datatake'], []).append(c['id'])
    yeni_edinim = []
    for _o, _s, _n, gid in sorted(oncelik):
        dt_ = gran[gid]['datatake']
        if gid in ekler and dt_ not in sira_no and dt_ not in yeni_edinim:
            yeni_edinim.append(dt_)
    for dt_ in yeni_edinim:
        sira_no[dt_] = len(plan['secim'])
        plan['secim'].append({'edinim': dt_, 'gecis': 'tamamla', 'kazanc_px': 0,
                              'tarih': min(gran[x]['datetime'] for x in edinim[dt_])[:10],
                              'renk': None})
    tum_gid = sorted(set(g['id'] for g in plan['granuller']) | set(ekler))
    tci = _kaba_tci_yukle(y, tum_gid, {**{g['id']: g for g in plan['granuller']}, **gran},
                          T, W, H)
    renk = renk_dengesi([s_['edinim'] for s_ in plan['secim']], edinim, onceki, tci, H, W)
    for s_ in plan['secim']:
        s_['renk'] = renk.get(s_['edinim'])
    ek_liste = []
    for gid in sorted(ekler):
        c = gran[gid]
        ek_liste.append({'id': gid, 'visual': c['visual'], 'scl': c['scl'],
                         'bloklar': sorted(ekler[gid])})
        var = [g for g in plan['granuller'] if g['id'] == gid]
        if var:
            var[0]['bloklar'] = sorted(set(tuple(b) for b in var[0]['bloklar']) | ekler[gid])
            var[0]['bloklar'] = [list(b) for b in var[0]['bloklar']]
        else:
            plan['granuller'].append({'id': gid, 'edinim': c['datatake'],
                                      'sira': sira_no[c['datatake']], 'gecis': 'tamamla',
                                      'bloklar': sorted(ekler[gid]), 'cloud': c['cloud'],
                                      'datetime': c['datetime'], 'mgrs': c['mgrs'],
                                      'epsg': c['epsg'], 'bbox': c['bbox'],
                                      'visual': c['visual'], 'scl': c['scl']})
    print('ISTEK_BAYT %d' % indirme_tahmini(ek_liste))
    tur = {'tur': len(plan.get('tamamla_turlari', [])) + 1, 'bos_kaba_px': int(bos.sum()),
           'bos_blok': len(bos_bloklar), 'ek_granul': len(ek_liste),
           'ek_blok': sum(len(g['bloklar']) for g in ek_liste),
           'yeni_edinim': yeni_edinim,
           'tahmini_bayt': sum(g['tahmini_bayt'] for g in ek_liste),
           'yedekli_px': int(((derinlik >= 1) & bos).sum()),
           'yedeksiz_px': int((bos & (derinlik == 0)).sum())}
    plan.setdefault('tamamla_turlari', []).append(tur)
    plan['tahmini_indirme_bayt'] = plan.get('tahmini_indirme_bayt', 0) + tur['tahmini_bayt']
    with open(y.plan + '.part', 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, indent=1, ensure_ascii=False)
    os.replace(y.plan + '.part', y.plan)
    # Boşluklu z10 blokları yeniden mozaiklenecek
    if ek_liste:
        for bx, by in bos_bloklar:
            db.execute('INSERT INTO bloklar_gecmis SELECT ?, bx, by, istatistik FROM bloklar '
                       'WHERE bx=? AND by=?', (tur['tur'], bx, by))
        db.executemany('DELETE FROM bloklar WHERE bx=? AND by=?', bos_bloklar)
        db.commit()
    db.close()
    print('tamamla', a.saha, json.dumps(tur, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 6) indir — yalnız gereken bloklar, yerel seyrek kopya
# ---------------------------------------------------------------------------

def _yerel_ac(yol, src, blok: int, bant: int):
    import rasterio
    if os.path.exists(yol):
        return rasterio.open(yol, 'r+')
    prof = {'driver': 'GTiff', 'width': src.width, 'height': src.height, 'count': bant,
            'dtype': 'uint8', 'crs': src.crs, 'transform': src.transform, 'nodata': 0,
            'tiled': True, 'blockxsize': blok, 'blockysize': blok, 'compress': 'deflate',
            'predictor': 2, 'zlevel': 4, 'sparse_ok': True, 'interleave': 'pixel'}
    return rasterio.open(yol, 'w', **prof)


def adim_indir(a, y: Yollar):
    import rasterio
    from concurrent.futures import ThreadPoolExecutor
    from rasterio.windows import Window
    import threading
    with open(y.plan, encoding='utf-8') as fh:
        plan = json.load(fh)
    t0 = time.time()
    yerel = threading.local()

    def kaynak(href):
        d = getattr(yerel, 'd', None)
        if d is None:
            d = yerel.d = {}
        if href not in d:
            d[href] = rasterio.open(kabuk_href(href))
        return d[href]

    def getir(is_):
        href, pencere = is_
        return kaynak(href).read(window=pencere)
    toplam_blok = 0
    ag_hatasi = None
    for g in plan['granuller']:
        if ag_hatasi:
            break
        dz = y.granul_dizini(g['id'])
        durum_yolu = os.path.join(dz, 'bloklar.json')
        bitti = set()
        if os.path.exists(durum_yolu):
            with open(durum_yolu, encoding='utf-8') as fh:
                bitti = set(tuple(b) for b in json.load(fh)['bitti'])
        kalan = [tuple(b) for b in g['bloklar'] if tuple(b) not in bitti]
        if not kalan:
            continue
        with rasterio.open(kabuk_href(g['visual'])) as tsrc, \
                rasterio.open(kabuk_href(g['scl'])) as ssrc:
            tci = _yerel_ac(os.path.join(dz, 'TCI.tif'), tsrc, 1024, 3)
            scl = _yerel_ac(os.path.join(dz, 'SCL.tif'), ssrc, 512, 1)
            try:
                with ThreadPoolExecutor(6) as ex:
                    for i in range(0, len(kalan), 6):
                        if time.time() - t0 > a.sure:
                            break
                        grup = kalan[i:i + 6]
                        isler = []
                        for br, bc in grup:
                            w10 = Window(bc * 1024, br * 1024, min(1024, tsrc.width - bc * 1024),
                                         min(1024, tsrc.height - br * 1024))
                            w20 = Window(bc * 512, br * 512, min(512, ssrc.width - bc * 512),
                                         min(512, ssrc.height - br * 512))
                            isler += [(g['visual'], w10), (g['scl'], w20)]
                        try:
                            sonuc = list(ex.map(getir, isler))
                        except rasterio.errors.RasterioIOError as e:
                            # 17 Kas ölçümü: bağlantı kopması GDAL yeniden denemesinden sonra
                            # 'Read failed' verdi ve adım (dolayısıyla saha) düştü. Grup yazılmaz,
                            # o ana kadarki ilerleme kayıtlı kalır; adım sıfır çıkışla biter ve
                            # hat bir sonraki çağrıda KALDIĞI YERDEN sürer (kalan_blok > 0).
                            ag_hatasi = '%s: %s' % (g['id'], str(e)[:160])
                            break
                        for j, (br, bc) in enumerate(grup):
                            tci.write(sonuc[2 * j], window=isler[2 * j][1])
                            scl.write(sonuc[2 * j + 1], window=isler[2 * j + 1][1])
                            bitti.add((br, bc))
                            toplam_blok += 1
                        with open(durum_yolu + '.part', 'w', encoding='utf-8') as fh:
                            json.dump({'bitti': sorted(bitti)}, fh)
                        os.replace(durum_yolu + '.part', durum_yolu)
            finally:
                tci.close()
                scl.close()
        print('granul', g['id'], 'blok', len(bitti), '/', len(g['bloklar']),
              'sure_s', round(time.time() - t0, 1), flush=True)
        if time.time() - t0 > a.sure:
            break
    kalan_say = 0
    for g in plan['granuller']:
        durum_yolu = os.path.join(y.granul_dizini(g['id']), 'bloklar.json')
        bitti = set()
        if os.path.exists(durum_yolu):
            with open(durum_yolu, encoding='utf-8') as fh:
                bitti = set(tuple(b) for b in json.load(fh)['bitti'])
        kalan_say += sum(1 for b in g['bloklar'] if tuple(b) not in bitti)
    if ag_hatasi:
        print('indir AG_HATASI (yeniden denenecek)', ag_hatasi, flush=True)
    print('indir', a.saha, 'bu_kosu_blok', toplam_blok, 'kalan_blok', kalan_say)


# ---------------------------------------------------------------------------
# 7) mozaik — z10 blokları
# ---------------------------------------------------------------------------

def is_db_ac(yol: str) -> sqlite3.Connection:
    db = sqlite3.connect(yol)
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('CREATE TABLE IF NOT EXISTS tiles (z INTEGER NOT NULL, x INTEGER NOT NULL, '
               'y INTEGER NOT NULL, coverage INTEGER NOT NULL, data BLOB NOT NULL, '
               'PRIMARY KEY (z, x, y)) WITHOUT ROWID')
    db.execute('CREATE TABLE IF NOT EXISTS bloklar (bx INTEGER, by INTEGER, istatistik TEXT, '
               'PRIMARY KEY (bx, by))')
    db.execute('CREATE TABLE IF NOT EXISTS ara_z10 (x INTEGER, y INTEGER, rgba BLOB, '
               'PRIMARY KEY (x, y))')
    db.execute('CREATE TABLE IF NOT EXISTS bloklar_gecmis (tur INTEGER, bx INTEGER, '
               'by INTEGER, istatistik TEXT)')
    return db


def webp_kodla(rgb, alfa8=None) -> bytes:
    """(3,H,W) uint8 [+ (H,W) uint8 alfa] -> WebP baytı (GDAL WEBP sürücüsü, sabit ayar)."""
    import numpy as np
    from rasterio.io import MemoryFile
    veri = rgb if alfa8 is None else np.concatenate([rgb, alfa8[None]], axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with MemoryFile() as mf:
            with mf.open(driver='WEBP', width=veri.shape[2], height=veri.shape[1],
                         count=veri.shape[0], dtype='uint8', QUALITY=WEBP_KALITE) as d:
                d.write(veri)
            return mf.read()


def karo_yaz(db, z, x, y_, rgb_u8, alfa_f):
    """Tek karo: alfa (0..1) tamamsa opak RGB WebP, değilse RGBA; alfa 0 ise yazılmaz."""
    import numpy as np
    bos_degil = bool((alfa_f > 0).any())
    if not bos_degil:
        return None
    tam = bool((alfa_f >= 1.0).all())
    cov = kapsama_degeri(float(alfa_f.mean()), tam, bos_degil)
    if tam:
        b = webp_kodla(rgb_u8)
    else:
        a8 = np.round(alfa_f * 255.0).astype(np.uint8)
        rgb2 = rgb_u8.copy()
        rgb2[:, a8 == 0] = 0
        b = webp_kodla(rgb2, a8)
    db.execute('INSERT OR REPLACE INTO tiles VALUES (?,?,?,?,?)', (z, x, y_, cov, b))
    return cov


def yarila(pre, alfa):
    """Öncarpılmış (3,H,W) float + (H,W) alfa -> 2x küçültülmüş (ortalama)."""
    _, H, W = pre.shape
    p = pre.reshape(3, H // 2, 2, W // 2, 2).mean(axis=(2, 4))
    al = alfa.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3))
    return p, al


def coz_on(pre, alfa):
    import numpy as np
    with np.errstate(invalid='ignore', divide='ignore'):
        rgb = np.where(alfa[None] > 0, pre / np.maximum(alfa[None], 1e-12), 0.0)
    return np.clip(np.round(rgb), 0, 255).astype(np.uint8)


def _blok_listesi(karolar):
    f = 1 << (mpi.IMAGERY_ZOOM_MAX - BLOK_Z)
    tx0, ty0, tx1, ty1 = karolar
    return [(bx, by) for by in range(ty0 // f, (ty1 - 1) // f + 1)
            for bx in range(tx0 // f, (tx1 - 1) // f + 1)]


def _warp(yol, T, W, H, resampling, bant=None):
    import rasterio
    from rasterio.vrt import WarpedVRT
    with rasterio.open(yol) as src:
        with WarpedVRT(src, crs='EPSG:4326', transform=T, width=W, height=H,
                       resampling=resampling, src_nodata=0, nodata=0,
                       **{'NUM_THREADS': 2, 'UNIFIED_SRC_NODATA': 'YES'}) as v:
            return v.read(bant) if bant else v.read()


_BLOK_KUTU_ONBELLEK = {}


def granul_blok_kutulari(y: Yollar, gid: str, ovr: bool = False):
    """Granülün İNDİRİLMİŞ bloklarının boylam/enlem kutuları (süreç içi önbellekli).

    ``ovr=False``: 10 m TCI'nın 10,24 km blokları (``bitti``); ``ovr=True``: TCI genel
    görünümünün (``TCI_OVR``) karoları (``bitti_ovr``, kenar ``ovr_karo`` px x 20 m).
    Kutular UTM blok köşelerinin dönüşümünün sarmalayıcısıdır (döndürülmüş blok için hafif
    büyük = güvenli taraf). İndirilmiş blok yoksa boş liste.
    """
    if (gid, ovr) in _BLOK_KUTU_ONBELLEK:
        return _BLOK_KUTU_ONBELLEK[(gid, ovr)]
    import rasterio
    from rasterio.warp import transform as donustur
    dz = os.path.join(y.cog, gid)
    kutular = []
    durum = os.path.join(dz, 'bloklar.json')
    if os.path.exists(durum) and os.path.exists(os.path.join(dz, 'SCL.tif')):
        with open(durum, encoding='utf-8') as fh:
            d = json.load(fh)
        bitti = d.get('bitti_ovr', []) if ovr else d['bitti']
        with rasterio.open(os.path.join(dz, 'SCL.tif')) as src:
            t, crs = src.transform, src.crs
        x0, y0 = t.c, t.f
        kenar = d['ovr_karo'] * abs(t.a) if ovr and bitti else 10240.0
        for br, bc in bitti:
            xs = [x0 + bc * kenar, x0 + (bc + 1) * kenar] * 2
            ys = [y0 - br * kenar] * 2 + [y0 - (br + 1) * kenar] * 2
            lo, la = donustur(crs, 'EPSG:4326', xs, ys)
            kutular.append((min(lo), min(la), max(lo), max(la)))
    _BLOK_KUTU_ONBELLEK[(gid, ovr)] = kutular
    return kutular


def _bos_var_mi(bos, kutular, lonW, latN, d13):
    """``bos`` (blok ızgarası) içinde kutulardan herhangi birinin altında True var mı?"""
    N = bos.shape[0]
    for w, s_, e, n in kutular:
        c0 = max(0, int((w - lonW) / d13) - 1)
        c1 = min(N, int((e - lonW) / d13) + 2)
        r0 = max(0, int((latN - n) / d13) - 1)
        r1 = min(N, int((latN - s_) / d13) + 2)
        if c1 > c0 and r1 > r0 and bos[r0:r1, c0:c1].any():
            return True
    return False


#: Pencereli warp payı [z13 px]: en geniş komşuluk işlemi (su-bulut kara tamponu + kötü sınıf
#: genişletmesi) kadar; blok kenarındaki eski 16 px paydan geniş (kenar bağlamı daha doğru).
PENCERE_PAYI = SU_BULUT_KARA_TAMPONU + INCE_GENISLETME


def _bos_penceresi(bos, kutular, lonW, latN, d13):
    """``bos``'un granül blok kutularının altında kalan kısmının sınır kutusu (r0, r1, c0, c1)
    — dışlayıcı uçlar, blok ızgarasında; boş piksel yoksa None."""
    import numpy as np
    N = bos.shape[0]
    r_min = c_min = N
    r_max = c_max = -1
    for w, s_, e, n in kutular:
        c0 = max(0, int((w - lonW) / d13) - 1)
        c1 = min(N, int((e - lonW) / d13) + 2)
        r0 = max(0, int((latN - n) / d13) - 1)
        r1 = min(N, int((latN - s_) / d13) + 2)
        if c1 <= c0 or r1 <= r0:
            continue
        alt = bos[r0:r1, c0:c1]
        satir = np.flatnonzero(alt.any(axis=1))
        if satir.size == 0:
            continue
        sutun = np.flatnonzero(alt.any(axis=0))
        r_min = min(r_min, r0 + int(satir[0]))
        r_max = max(r_max, r0 + int(satir[-1]))
        c_min = min(c_min, c0 + int(sutun[0]))
        c_max = max(c_max, c0 + int(sutun[-1]))
    if r_max < 0:
        return None
    return r_min, r_max + 1, c_min, c_max + 1


def kalici_parlak_su(kaba_scl, kaba_tci, edinim_of, H, W):
    """Kaba ızgarada KALICI parlak su maskesi (bool (H, W)).

    ``kaba_scl``/``kaba_tci``: granül kimliği -> kaba SCL (H, W) / TCI (3, H, W);
    ``edinim_of``: granül -> edinim (datatake). Yalnız TCI'sı olan granüller sayılır. Bir hücre
    için: parlak = SCL 6 ve min(R,G,B) > SU_BULUT_ESIK olduğu farklı edinim sayısı; su = SCL 6
    olduğu farklı edinim sayısı. Kalıcı: parlak >= KALICI_PARLAK_SU_EN_AZ ve
    parlak >= KALICI_PARLAK_SU_ORAN * su.
    """
    import numpy as np
    parlak, su = {}, {}
    for gid in sorted(kaba_tci):
        if gid not in kaba_scl or gid not in edinim_of:
            continue
        sc, t = kaba_scl[gid], kaba_tci[gid]
        gecerli = t.sum(axis=0) > 0
        w_ = (sc == 6) & gecerli
        e = edinim_of[gid]
        parlak.setdefault(e, np.zeros((H, W), bool))
        su.setdefault(e, np.zeros((H, W), bool))
        parlak[e] |= w_ & (t.min(axis=0) > SU_BULUT_ESIK)
        su[e] |= w_
    P = np.zeros((H, W), np.int32)
    S = np.zeros((H, W), np.int32)
    for e in parlak:
        P += parlak[e]
        S += su[e]
    return (P >= KALICI_PARLAK_SU_EN_AZ) & (P >= KALICI_PARLAK_SU_ORAN * S)


def _kalici_yukle(plan, y: Yollar):
    """Sahanın kaba dosyalarından kalıcı parlak su maskesi (dosya yoksa None)."""
    import numpy as np
    if not (os.path.exists(y.kaba) and os.path.exists(y.kaba_tci)):
        return None
    scl = np.load(y.kaba)
    tci = np.load(y.kaba_tci)
    ed = {g['id']: g['edinim'] for g in plan['granuller']}
    return kalici_parlak_su({k: scl[k] for k in scl.files if k in ed},
                            {k: tci[k] for k in tci.files if k in ed}, ed,
                            plan['kaba_izgara']['H'], plan['kaba_izgara']['W'])


def _kaba_pencere(kalici, plan, bx, by, r0, c0, h, w):
    """Blok içindeki (r0, c0) başlangıçlı h x w z13 penceresi için kaba maskenin değerleri."""
    import numpy as np
    if kalici is None:
        return np.zeros((h, w), bool)
    N = mpi.TILE_PX << (mpi.IMAGERY_ZOOM_MAX - BLOK_Z)
    K = mpi.TILE_PX // KABA_BOLUM
    tx0, ty0 = plan['alan_karolari_z13'][0], plan['alan_karolari_z13'][1]
    gr = by * N + r0 + np.arange(h) - ty0 * mpi.TILE_PX
    gc = bx * N + c0 + np.arange(w) - tx0 * mpi.TILE_PX
    kr, kc = np.floor_divide(gr, K), np.floor_divide(gc, K)
    H_, W_ = kalici.shape
    rok, cok = (kr >= 0) & (kr < H_), (kc >= 0) & (kc < W_)
    out = np.zeros((h, w), bool)
    alt = kalici[np.clip(kr, 0, H_ - 1)][:, np.clip(kc, 0, W_ - 1)]
    out[np.ix_(rok, cok)] = alt[np.ix_(rok, cok)]
    return out


#: Mozaik kaynağı: 10 m TCI (yerel seyrek kopya ``TCI.tif``) ya da TCI'nın ilk genel görünümü
#: (20 m, ``TCI_OVR``; halka dışı bloklar, 18 Kas). Kübik çekirdeğin veri-yok kenarındaki
#: halesi için geçerli alanın daraltılması [z13 px]: kaynak pikselinin boyuyla ölçeklenir
#: (10 m: 2 px; 20 m: 4 px) — HRMA seçimi.
TCI_TAM = 'TCI.tif'
TCI_OVR = 'TCI_ovr.tif'
HALE_PX = {TCI_TAM: 2, TCI_OVR: 4}


def blok_mozaik(plan, y: Yollar, bx, by, kalici=None, alanlar=None, tci_adi=TCI_TAM):
    """Bir z10 bloğunun z13 mozaiği: (rgb uint8 (3,N,N), alfa bool (N,N), istatistik).

    ``kalici``: kaba ızgarada kalıcı parlak su maskesi (``kalici_parlak_su``); orada su-bulut
    kuralı uygulanmaz. ``alanlar``: {ad: bool (N, N)} — istatistik bu alt alanların her biri
    için ayrıca sayılır (``istatistik['alanlar'][ad]``; halka kuralının kalite kapısı).
    ``tci_adi``: ``TCI_TAM`` (10 m) ya da ``TCI_OVR`` (20 m genel görünüm; halka dışı).
    Mozaik kuralı iki kaynakta aynıdır; yalnız renk kaynağının çözünürlüğü değişir.
    """
    import numpy as np
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    N = mpi.TILE_PX << (mpi.IMAGERY_ZOOM_MAX - BLOK_Z)          # 4096
    d13 = piksel_derece(mpi.IMAGERY_ZOOM_MAX)
    sp = tile_cache.tile_span_deg(BLOK_Z)
    lonW, latN = -180.0 + bx * sp, 90.0 - by * sp
    M = BLOK_PAY
    Tm = from_origin(lonW - M * d13, latN + M * d13, d13, d13)
    T = from_origin(lonW, latN, d13, d13)
    # Alan içi maske (z13 karo hizalı alan)
    tx0, ty0, tx1, ty1 = plan['alan_karolari_z13']
    f = 1 << (mpi.IMAGERY_ZOOM_MAX - BLOK_Z)
    ic = np.zeros((N, N), bool)
    c0 = max(tx0 - bx * f, 0) * mpi.TILE_PX
    c1 = min(tx1 - bx * f, f) * mpi.TILE_PX
    r0 = max(ty0 - by * f, 0) * mpi.TILE_PX
    r1 = min(ty1 - by * f, f) * mpi.TILE_PX
    if c1 > c0 and r1 > r0:
        ic[r0:r1, c0:c1] = True
    rgb = np.zeros((3, N, N), np.uint8)
    dolu = np.zeros((N, N), bool)
    gozlendi = np.zeros((N, N), bool)
    katki = {}
    blok_kutu = (lonW, latN - sp, lonW + sp, latN)
    renk = {s['edinim']: s['renk'] for s in plan['secim']}
    ovr = tci_adi == TCI_OVR
    granuller = [g for g in plan['granuller']
                 if g['bbox'][0] < blok_kutu[2] and blok_kutu[0] < g['bbox'][2]
                 and g['bbox'][1] < blok_kutu[3] and blok_kutu[1] < g['bbox'][3]
                 and os.path.exists(os.path.join(y.cog, g['id'], 'SCL.tif'))
                 and os.path.exists(os.path.join(y.cog, g['id'], tci_adi))]
    granuller.sort(key=lambda g: (g['sira'], g['id']))
    sinif_onbellek, tci_onbellek, su_bulut_say, kalici_say = {}, {}, {}, {}
    kiyi_px = 0
    atlanan = 0
    alanlar = alanlar or {}
    asay = {ad: {'katki': {}, 'su_bulut_px': 0, 'kiyi_kabul_px': 0, 'kalici_parlak_su_px': 0}
            for ad in alanlar}
    for gecis in ('iyi', 'kabul', 'kiyi'):
        for g in granuller:
            bos = ic & ~dolu
            if not bos.any():
                break
            dz = os.path.join(y.cog, g['id'])
            if g['id'] not in sinif_onbellek:
                # Hız (pilot ölçümü: tamamla sonrası 20+ granül, blok başına ~10 s): granülün
                # İNDİRİLMİŞ blokları bu bloktaki boş piksellere değmiyorsa warp edilmez;
                # değiyorsa YALNIZ o boş piksellerin sınır kutusu (pencere) warp edilir. Boş
                # alan geçişler boyunca yalnız küçüldüğü için ilk pencere sonrakileri kapsar.
                # Pencere payı (PENCERE_PAYI) genişletme + kara tamponunun bağlamını kapsar.
                pen = _bos_penceresi(bos, granul_blok_kutulari(y, g['id'], ovr), lonW, latN, d13)
                if pen is None:
                    atlanan += 1
                    continue
                r0, r1, c0, c1 = pen
                h_, w_ = r1 - r0, c1 - c0
                M = PENCERE_PAYI
                Tp = from_origin(lonW + (c0 - M) * d13, latN - (r0 - M) * d13, d13, d13)
                s = _warp(os.path.join(dz, 'SCL.tif'), Tp, w_ + 2 * M, h_ + 2 * M,
                          Resampling.nearest, 1)
                # Su üstünde kaçırılmış bulut (SU_BULUT_ESIK): su varsa TCI pay'lı okunur
                tm = None
                if (s == 6).any():
                    tm = _warp(os.path.join(dz, tci_adi), Tp, w_ + 2 * M, h_ + 2 * M,
                               Resampling.cubic)
                    kara_yakin = genislet(np.isin(s, (2, 4, 5, 7, 11)), SU_BULUT_KARA_TAMPONU)
                    su_bulut = (s == 6) & ~kara_yakin & (tm.min(axis=0) > SU_BULUT_ESIK)
                    kal = _kaba_pencere(kalici, plan, bx, by, r0 - M, c0 - M, h_ + 2 * M, w_ + 2 * M)
                    kalici_say[g['id']] = int((su_bulut & kal)[M:-M, M:-M].sum())
                    for ad, am in alanlar.items():
                        asay[ad]['kalici_parlak_su_px'] += int(
                            ((su_bulut & kal)[M:-M, M:-M] & am[r0:r1, c0:c1]).sum())
                    su_bulut &= ~kal
                    s = s.copy()
                    s[su_bulut] = 9            # yüksek olasılıklı bulut gibi işlenir
                    su_bulut_say[g['id']] = int(su_bulut[M:-M, M:-M].sum())
                    for ad, am in alanlar.items():
                        asay[ad]['su_bulut_px'] += int(
                            (su_bulut[M:-M, M:-M] & am[r0:r1, c0:c1]).sum())
                iy, kb, gz = maskeler(s, INCE_GENISLETME)
                kiyi = (genislet(s == 6, KIYI_BANDI) & genislet(np.isin(s, (4, 5)), KIYI_BANDI)
                        & np.isin(s, SCL_KIYI))
                sinif_onbellek[g['id']] = ((r0, r1, c0, c1), iy[M:-M, M:-M], kb[M:-M, M:-M],
                                           gz[M:-M, M:-M], kiyi[M:-M, M:-M])
                if tm is not None:
                    tci_onbellek[g['id']] = tm[:, M:-M, M:-M]
            (r0, r1, c0, c1), iy, kb, gz, ky = sinif_onbellek[g['id']]
            pen = (slice(r0, r1), slice(c0, c1))
            gozlendi[pen] |= gz
            m = {'iyi': iy, 'kabul': kb, 'kiyi': ky}[gecis] & ic[pen] & ~dolu[pen]
            if not m.any():
                continue
            t = tci_onbellek.get(g['id'])
            if t is None:
                Tp0 = from_origin(lonW + c0 * d13, latN - r0 * d13, d13, d13)
                t = tci_onbellek[g['id']] = _warp(os.path.join(dz, tci_adi), Tp0,
                                                  c1 - c0, r1 - r0, Resampling.cubic)
            gecerli = t.any(axis=0)
            # cubic çekirdeğinin veri-yok kenarındaki halesi: geçerli alan daraltılır
            gecerli = ~genislet(~gecerli, HALE_PX[tci_adi])
            m &= gecerli
            if not m.any():
                continue
            k = renk.get(g['edinim']) or [(1.0, 0.0, 0, 'birim')] * 3
            alt_rgb = rgb[:, r0:r1, c0:c1]
            for b in range(3):
                v = t[b][m].astype(np.float32) * k[b][0] + k[b][1]
                alt_rgb[b][m] = np.clip(np.round(v), 0, 255).astype(np.uint8)
            dolu[pen] |= m
            katki[g['id']] = katki.get(g['id'], 0) + int(m.sum())
            if gecis == 'kiyi':
                kiyi_px += int(m.sum())
            for ad, am in alanlar.items():
                n_ = int((m & am[pen]).sum())
                if n_:
                    asay[ad]['katki'][g['id']] = asay[ad]['katki'].get(g['id'], 0) + n_
                    if gecis == 'kiyi':
                        asay[ad]['kiyi_kabul_px'] += n_
    # Bulut kalıntısı tahmini (beyaz, düşük doygunluk; gerçek beyaz yüzeyleri de sayar)
    mx = rgb.max(axis=0)
    mn = rgb.min(axis=0)
    beyaz = dolu & (mn > 200) & ((mx.astype(np.int16) - mn) < 20)
    # Boş piksel içeren kaba (z13/32) hücreler, sahanın kaba ızgarasında (tamamla adımı için)
    K = mpi.TILE_PX // KABA_BOLUM
    bos_k = (ic & ~dolu).reshape(N // K, K, N // K, K).any(axis=(1, 3))
    r_ofs = (by * f - ty0) * KABA_BOLUM
    c_ofs = (bx * f - tx0) * KABA_BOLUM
    rr, cc = np.nonzero(bos_k)
    bos_kaba = [[int(r + r_ofs), int(c + c_ofs)] for r, c in zip(rr, cc)]
    ist = {'ic_px': int(ic.sum()), 'dolu_px': int(dolu.sum()), 'bos_kaba': bos_kaba,
           'bos_gozlenmis_px': int((ic & ~dolu & gozlendi).sum()),
           'bos_gozlenmemis_px': int((ic & ~dolu & ~gozlendi).sum()),
           'beyaz_px': int(beyaz.sum()), 'katki': katki,
           'su_bulut_px': sum(su_bulut_say.values()), 'kiyi_kabul_px': kiyi_px,
           'kalici_parlak_su_px': sum(kalici_say.values()), 'atlanan_granul': atlanan}
    if ovr:
        ist['kaynak'] = 'ovr'
    if alanlar:
        ist['alanlar'] = {}
        for ad, am in alanlar.items():
            ia = ic & am
            ist['alanlar'][ad] = dict(
                asay[ad], ic_px=int(ia.sum()), dolu_px=int((dolu & ia).sum()),
                bos_gozlenmis_px=int((ia & ~dolu & gozlendi).sum()),
                bos_gozlenmemis_px=int((ia & ~dolu & ~gozlendi).sum()),
                beyaz_px=int((beyaz & am).sum()))
    return rgb, dolu & ic, ist


def blok_karolari(db, bx, by, rgb, alfa_b):
    """z13..z10 karolarını yazar; z10 karosunu z9 için ara tabloya koyar."""
    import numpy as np
    f = 1 << (mpi.IMAGERY_ZOOM_MAX - BLOK_Z)
    P = mpi.TILE_PX
    sayac = {}
    # z13: doğrudan
    for j in range(f):
        for i in range(f):
            a = alfa_b[j * P:(j + 1) * P, i * P:(i + 1) * P]
            if not a.any():
                continue
            c = karo_yaz(db, mpi.IMAGERY_ZOOM_MAX, bx * f + i, by * f + j,
                         rgb[:, j * P:(j + 1) * P, i * P:(i + 1) * P], a.astype(np.float32))
            sayac[13] = sayac.get(13, 0) + (1 if c else 0)
    # Öncarpılmış (alfa 0/1) ilk küçültme: uint16 toplam ile bellek dostu
    alfa = alfa_b.astype(np.float32)
    pre = rgb.astype(np.float32) * alfa[None]
    z = mpi.IMAGERY_ZOOM_MAX
    while z > BLOK_Z:
        pre, alfa = yarila(pre, alfa)
        z -= 1
        n = f >> (mpi.IMAGERY_ZOOM_MAX - z)
        rgb_z = coz_on(pre, alfa)
        for j in range(n):
            for i in range(n):
                a = alfa[j * P:(j + 1) * P, i * P:(i + 1) * P]
                c = karo_yaz(db, z, bx * n + i, by * n + j,
                             rgb_z[:, j * P:(j + 1) * P, i * P:(i + 1) * P], a)
                sayac[z] = sayac.get(z, 0) + (1 if c else 0)
    rgb10 = coz_on(pre, alfa)
    a8 = np.round(alfa * 255.0).astype(np.uint8)
    ham = zlib.compress(np.concatenate([rgb10, a8[None]]).tobytes(), 6)
    db.execute('INSERT OR REPLACE INTO ara_z10 VALUES (?,?,?)', (bx, by, ham))
    return sayac


def blok_kaynagi(plan, halka_b, bx, by) -> str:
    """Bloğun renk kaynağı: halka bloğu 10 m; değilse plan genel görünümlüyse 20 m, eski
    (16-17 Kas) planda 10 m (o sahaların bütün blokları 10 m indirildi)."""
    if (bx, by) in halka_b or plan.get('dis_kaynak') != 'cog_ovr':
        return TCI_TAM
    return TCI_OVR


def adim_mozaik(a, y: Yollar):
    with open(y.plan, encoding='utf-8') as fh:
        plan = json.load(fh)
    if 'duzey_kurali' not in plan:
        raise SystemExit('planda halka kurali yok (eski plan: once halka-hazirla)')
    db = is_db_ac(y.is_db)
    t0 = time.time()
    bitti = set((r[0], r[1]) for r in db.execute('SELECT bx, by FROM bloklar'))
    bloklar = _blok_listesi(plan['alan_karolari_z13'])
    halkalar = halka_plani(plan)
    halka_b = halka_bloklari(halkalar)
    yapilan = 0
    kalici = _kalici_yukle(plan, y)
    for bx, by in bloklar:
        if (bx, by) in bitti:
            continue
        if time.time() - t0 > a.sure:
            break
        t1 = time.time()
        alanlar = blok_halka_maskeleri(halkalar, bx, by) if (bx, by) in halka_b else None
        rgb, alfa, ist = blok_mozaik(plan, y, bx, by, kalici, alanlar,
                                     blok_kaynagi(plan, halka_b, bx, by))
        sayac = blok_karolari(db, bx, by, rgb, alfa)
        ist['karo'] = sayac
        ist['sure_s'] = round(time.time() - t1, 2)
        db.execute('INSERT OR REPLACE INTO bloklar VALUES (?,?,?)', (bx, by, json.dumps(ist)))
        db.commit()
        yapilan += 1
        print('blok', bx, by, 'dolu', ist['dolu_px'], '/', ist['ic_px'], 'sure', ist['sure_s'],
              flush=True)
    kalan = len(bloklar) - len(bitti) - yapilan
    db.close()
    print('mozaik', a.saha, 'bu_kosu', yapilan, 'kalan', kalan,
          'sure_s', round(time.time() - t0, 1))


def blok_sifirla(db, bx: int, by: int) -> int:
    """Bloğun kaydını, z13..z10 karolarını ve z9 ara parçasını siler (yeniden mozaik için;
    ``karo_yaz`` boş karoyu yazmadığından eski karo kalmasın). Silinen karo sayısı döner."""
    n = 0
    for z in range(BLOK_Z, mpi.IMAGERY_ZOOM_MAX + 1):
        k = z - BLOK_Z
        x0, y0 = bx << k, by << k
        n += db.execute('DELETE FROM tiles WHERE z=? AND x>=? AND x<? AND y>=? AND y<?',
                        (z, x0, x0 + (1 << k), y0, y0 + (1 << k))).rowcount
    db.execute('DELETE FROM ara_z10 WHERE x=? AND y=?', (bx, by))
    db.execute('DELETE FROM bloklar WHERE bx=? AND by=?', (bx, by))
    return n


def adim_halka_hazirla(a, y: Yollar):
    """16-17 Kas'ta 10 m ile bitmiş sahayı halka kuralına hazırlar (İNDİRMESİZ yeniden paket).

    ``--kaynak-gecici`` (eski ``gecici/<saha>``, SALT OKUNUR) içinden plan, kaba dosyalar ve
    iş veritabanı bu çalışma dizinine KOPYALANIR; kopyada halka bloklarının kaydı ve karoları
    silinir (``mozaik`` onları alt alan istatistiğiyle yeniden kurar; kaynak ve kural aynı).
    Halka dışı blokların karoları aynen kalır. Kaynak dizine hiçbir şey yazılmaz.
    """
    import shutil
    if os.path.exists(y.plan):
        with open(y.plan, encoding='utf-8') as fh:
            if json.load(fh).get('halka_hazir'):
                print('halka-hazirla', a.saha, 'zaten hazir')
                return
    kaynak = a.kaynak_gecici
    if not kaynak or os.path.realpath(kaynak) == os.path.realpath(y.gecici):
        raise SystemExit('--kaynak-gecici gerekli (bu calisma dizininden farkli)')
    # plan + kaba dosyalar zorunlu; iş veritabanı yalnız mozaiği başlamış sahada vardır
    # (16-17 Kas'ta planlanıp indirmesi yarım kalan sahalar: yalnız plan taşınır).
    kopyalar = []
    for ad in ('plan.json', 'kaba_scl.npz', 'kaba_tci.npz', 'is.sqlite'):
        k = os.path.join(kaynak, ad)
        if not os.path.exists(k):
            if ad == 'is.sqlite':
                continue
            raise SystemExit('kaynakta yok: %s' % ad)
        shutil.copyfile(k, os.path.join(y.gecici, ad + '.kopya'))
        kopyalar.append(ad)
    with open(os.path.join(y.gecici, 'plan.json.kopya'), encoding='utf-8') as fh:
        plan = json.load(fh)
    bbox = paket_kutusu(a.liste, a.saha)
    if [round(v, 9) for v in plan['bbox']] != [round(v, 9) for v in bbox]:
        raise SystemExit('plan kutusu listeyle ayni degil')
    plan['merkez'] = list(paket_merkezi(bbox))
    plan['duzey_kurali'] = duzey_kurali()
    plan['dis_kaynak'] = 'tam_10m'
    halka_b = sorted(halka_bloklari(halka_plani(plan)))
    silinen = 0
    if 'is.sqlite' in kopyalar:
        db = is_db_ac(os.path.join(y.gecici, 'is.sqlite.kopya'))
        silinen = sum(blok_sifirla(db, bx, by) for bx, by in halka_b)
        db.commit()
        db.close()
    plan['halka_hazir'] = {'kaynak_gecici': os.path.abspath(kaynak), 'halka_blok': len(halka_b),
                           'silinen_karo': silinen, 'is_db_kopyalandi': 'is.sqlite' in kopyalar,
                           'tarih': _dt.datetime.now().isoformat(timespec='seconds')}
    for ad in kopyalar:
        if ad != 'plan.json':
            os.replace(os.path.join(y.gecici, ad + '.kopya'), os.path.join(y.gecici, ad))
    with open(y.plan + '.part', 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, indent=1, ensure_ascii=False)
    os.replace(y.plan + '.part', y.plan)
    os.remove(os.path.join(y.gecici, 'plan.json.kopya'))
    print('halka-hazirla', a.saha, 'halka_blok', len(halka_b), 'silinen_karo', silinen)


# ---------------------------------------------------------------------------
# 8) bitir — z9, kalite kapısı, son dosya, künye
# ---------------------------------------------------------------------------

_IST_ANAHTAR = ('ic_px', 'dolu_px', 'bos_gozlenmis_px', 'bos_gozlenmemis_px', 'beyaz_px',
                'su_bulut_px', 'kiyi_kabul_px', 'kalici_parlak_su_px')


def _kapi(top: dict) -> dict:
    gozlenen = top['dolu_px'] + top['bos_gozlenmis_px']
    kalinti = top['bos_gozlenmis_px'] / gozlenen if gozlenen else 0.0
    return {'bulut_kalintisi_orani': round(kalinti, 6), 'esik': BULUT_KALINTI_ESIK,
            'gecti': kalinti <= BULUT_KALINTI_ESIK}


def alan_istatistigi(bitti: dict, halkalar: dict) -> dict:
    """Blok istatistiklerinden alan toplamları: 'kutu' (bütün paket alanı, z9..z11) ve her
    halka ('z12', 'z13'; yalnız o halkanın karolarının z13 pikselleri). Halka bloğunun alt
    alan istatistiği yoksa SystemExit (eski blok: halka-hazirla/mozaik koşulmamış)."""
    top = {k: 0 for k in _IST_ANAHTAR}
    katki = {}
    for ist in bitti.values():
        for k in top:
            top[k] += ist.get(k, 0)
        for g, n in ist['katki'].items():
            katki[g] = katki.get(g, 0) + n
    out = {'kutu': dict(top, gozlenen_px=top['dolu_px'] + top['bos_gozlenmis_px'],
                        kapi=_kapi(top))}
    halka_b = halka_bloklari(halkalar)
    for z in sorted(halkalar):
        ad = 'z%d' % z
        h = {k: 0 for k in _IST_ANAHTAR}
        for b in sorted(halka_b):
            al = bitti[b].get('alanlar', {}).get(ad)
            if al is None:
                raise SystemExit('halka istatistigi eksik: blok %r %s' % (b, ad))
            for k in h:
                h[k] += al.get(k, 0)
        out[ad] = dict(h, gozlenen_px=h['dolu_px'] + h['bos_gozlenmis_px'], kapi=_kapi(h),
                       karo=len(halkalar[z]))
    return out, katki


def adim_bitir(a, y: Yollar):
    import numpy as np
    with open(y.plan, encoding='utf-8') as fh:
        plan = json.load(fh)
    if 'duzey_kurali' not in plan:
        raise SystemExit('planda halka kurali yok')
    kural = plan['duzey_kurali']
    db = is_db_ac(y.is_db)
    bloklar = _blok_listesi(plan['alan_karolari_z13'])
    bitti = {(r[0], r[1]): json.loads(r[2]) for r in
             db.execute('SELECT bx, by, istatistik FROM bloklar')}
    eksik = [b for b in bloklar if b not in bitti]
    if eksik:
        raise SystemExit('mozaik bitmedi: %d blok eksik' % len(eksik))
    halkalar = halka_plani(plan)
    # z9: 2x2 z10 parçası
    P = mpi.TILE_PX
    parca = {}
    for x, y_, ham in db.execute('SELECT x, y, rgba FROM ara_z10'):
        arr = np.frombuffer(zlib.decompress(ham), np.uint8).reshape(4, P, P)
        parca[(x, y_)] = arr
    z9 = sorted(set((x >> 1, y_ >> 1) for x, y_ in parca))
    for x9, y9 in z9:
        pre = np.zeros((3, 2 * P, 2 * P), np.float32)
        alfa = np.zeros((2 * P, 2 * P), np.float32)
        for dy in (0, 1):
            for dx in (0, 1):
                p = parca.get((2 * x9 + dx, 2 * y9 + dy))
                if p is None:
                    continue
                al = p[3].astype(np.float32) / 255.0
                alfa[dy * P:(dy + 1) * P, dx * P:(dx + 1) * P] = al
                pre[:, dy * P:(dy + 1) * P, dx * P:(dx + 1) * P] = p[:3].astype(np.float32) * al
        pre, alfa = yarila(pre, alfa)
        karo_yaz(db, mpi.IMAGERY_ZOOM_MIN, x9, y9, coz_on(pre, alfa), alfa)
    db.commit()
    # İstatistik + kalite kapısı (paket kutusu ve her halka ayrı; hepsi geçmeli)
    alan, katki = alan_istatistigi(bitti, halkalar)
    kapi = {ad: v['kapi'] for ad, v in alan.items()}
    gecti = all(k['gecti'] for k in kapi.values())
    gran = {g['id']: g for g in plan['granuller']}
    sahneler = []
    for gid in sorted(katki, key=lambda g: (-katki[g], g)):
        g = gran[gid]
        sahneler.append({'id': gid, 'datetime': g['datetime'], 'mgrs': g['mgrs'],
                         'cloud_cover': g['cloud'], 'datatake': g['edinim'],
                         'pixel_share': round(katki[gid] / max(alan['kutu']['dolu_px'], 1), 6),
                         'source': g['visual'].rsplit('/', 1)[0] + '/'})
    yillar = sorted(set(s['datetime'][:4] for s in sahneler))
    if not gecti and not a.kapi_istisnasi:
        print('KALITE KAPISI GECMEDI', json.dumps(kapi))
        db.close()
        sys.exit(3)

    def pakette(z, x, y_):
        return z <= kural['full_zoom_max'] or (x, y_) in halkalar.get(z, ())
    say, tam, bayt = {}, {}, {}
    for z, x, y_, cov, n in db.execute('SELECT z, x, y, coverage, length(data) FROM tiles'):
        if pakette(z, x, y_):
            say[z] = say.get(z, 0) + 1
            bayt[z] = bayt.get(z, 0) + n
            if cov == 10000:
                tam[z] = tam.get(z, 0) + 1
    # Halka karosunda veri yoksa (bütünüyle saydam) karo yazılmaz: sayı, halka karosundan az olabilir
    istatistik = dict(alan['kutu'], kapi=kapi['kutu'], alanlar={k: v for k, v in alan.items() if k != 'kutu'},
                      karo=say, tam_karo=tam, karo_bayt=bayt,
                      beyaz_orani=round(alan['kutu']['beyaz_px'] / max(alan['kutu']['dolu_px'], 1), 6),
                      kapi_hepsi=kapi, kaba=plan['kaba_istatistik'])
    if a.kapi_istisnasi:
        istatistik['kapi_istisnasi'] = a.kapi_istisnasi
    detail = {'center': [round(v, 9) for v in plan['merkez']],
              'full_zoom_max': kural['full_zoom_max'], 'rings': kural['rings']}
    mpi.duzey_kurali_dogrula({k: detail[k] for k in ('full_zoom_max', 'rings')},
                             mpi.IMAGERY_ZOOM_MIN, mpi.IMAGERY_ZOOM_MAX)
    dis = {'tam_10m': 'outside the rings: the 10 m mosaic downsampled (same blocks as the rings)',
           'cog_ovr': 'outside the rings: first COG overview of TCI (20 m), same masking rules'}
    meta = {
        'schema': mpi.SCHEMA, 'grid': mpi.GRID_ID, 'tile_px': str(mpi.TILE_PX), 'format': 'webp',
        'zoom_min': str(mpi.IMAGERY_ZOOM_MIN), 'zoom_max': str(mpi.IMAGERY_ZOOM_MAX),
        'bounds': ','.join('%.9f' % v for v in plan['alan_kutusu']), 'pack_id': a.saha,
        'attribution': atif_metni(yillar), 'license': mpi.LICENSE_ID,
        'scenes': json.dumps(sahneler, ensure_ascii=False, sort_keys=True),
        'source': 'Element84 Earth Search STAC collection %s (AWS open data, %s); '
                  'assets visual (TCI 10 m) + scl (20 m)' % (COLLECTION, COG_HOST),
        'detail': json.dumps(detail, sort_keys=True),
        'method': json.dumps({'compositing': 'best-pixel, greedy acquisition order',
                              'mask_bad_scl': list(SCL_KOTU), 'good_scl': list(SCL_IYI),
                              'water_cloud_min_rgb_gt': SU_BULUT_ESIK,
                              'water_cloud_land_buffer_px_z13': SU_BULUT_KARA_TAMPONU,
                              'water_cloud_persistent_exempt': {
                                  'min_acquisitions': KALICI_PARLAK_SU_EN_AZ,
                                  'min_fraction_of_water_obs': KALICI_PARLAK_SU_ORAN,
                                  'grid': 'coarse (z13 tile / %d)' % KABA_BOLUM},
                              'window_margin_px_z13': PENCERE_PAYI,
                              'coastal_pass': {'band_px_z13': KIYI_BANDI,
                                               'scl': list(SCL_KIYI), 'dilation': 0},
                              'fallback_scl': list(SCL_KABUL), 'bad_dilation_px_z13': INCE_GENISLETME,
                              'resampling': 'cubic (TCI), nearest (SCL)',
                              'colour_balance': 'per-acquisition linear gain/offset at ~240 m',
                              'detail_rule': {
                                  'pack_area_zoom': [mpi.IMAGERY_ZOOM_MIN, kural['full_zoom_max']],
                                  'rings_km_around_launch_point': {
                                      str(h['zoom']): h['radius_km'] for h in kural['rings']},
                                  'tile_in_ring': 'tile box within radius (local equirectangular, '
                                                  '%.2f km per degree)' % mpi.KM_PER_DEG,
                                  'outer_source': dis[plan['dis_kaynak']]},
                              'webp_quality': WEBP_KALITE, 'empty': 'transparent (no fill)'},
                             sort_keys=True),
        'empty_regions': json.dumps(istatistik, sort_keys=True),
        'created': plan['olusturma'], 'generator': 'tools/harita_goruntu_uret.py %s' % DOSYA_SURUMU,
    }
    gecici = y.paket + '.part'
    if os.path.exists(gecici):
        os.remove(gecici)
    son = sqlite3.connect(gecici)
    son.execute('PRAGMA page_size=4096')
    son.execute('PRAGMA journal_mode=OFF')
    for ddl in mpi.DDL:
        son.execute(ddl)
    son.executemany('INSERT INTO metadata VALUES (?,?)', sorted(meta.items()))
    for r in db.execute('SELECT z, x, y, coverage, data FROM tiles ORDER BY z, x, y'):
        if pakette(r[0], r[1], r[2]):
            son.execute('INSERT INTO tiles VALUES (?,?,?,?,?)', r)
    son.commit()
    son.execute('VACUUM')
    son.close()
    db.close()
    os.replace(gecici, y.paket)
    h = hashlib.sha256()
    with open(y.paket, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    boyut = os.path.getsize(y.paket)
    # Geri okuma: ürün okuyucusuyla her karo (ve karo kendi düzeyinin alanında mı)
    ok = mpi.GoruntuOkuyucu(y.paket)
    hata = alan_disi = 0
    for z, x, y_ in sqlite3.connect('file:%s?mode=ro' % y.paket, uri=True).execute(
            'SELECT z, x, y FROM tiles'):
        try:
            if ok.karo(z, x, y_) is None:
                hata += 1
            if not ok.duzeyde_mi(z, x, y_):
                alan_disi += 1
        except mpi.GoruntuHatasi:
            hata += 1
    ok.kapat()
    if alan_disi:
        raise SystemExit('okuyucu halka kurali ile uretim ayrisiyor: %d karo' % alan_disi)
    kunye = {'pack_id': a.saha, 'file': os.path.basename(y.paket), 'size_bytes': boyut,
             'sha256': h.hexdigest(), 'geri_okuma_hata': hata, 'metadata': meta,
             'istatistik': istatistik, 'plan_ozet': {k: plan[k] for k in
                                                     ('aylar', 'aday_sayisi', 'secim', 'kaba_istatistik')}}
    bilesen = {'kind': 'imagery', 'file': os.path.basename(y.paket), 'size_bytes': boyut,
               'sha256': h.hexdigest(), 'license': mpi.LICENSE_ID,
               'attribution': atif_metni(yillar),
               'detail': {'full_zoom_max': kural['full_zoom_max'], 'rings': kural['rings']}}
    kunye['manifest_bileseni'] = bilesen
    if a.kanit:
        os.makedirs(a.kanit, exist_ok=True)
        with open(os.path.join(a.kanit, '%s_kunye.json' % a.saha), 'w', encoding='utf-8') as fh:
            json.dump(kunye, fh, indent=1, ensure_ascii=False, sort_keys=True)
    print('bitir', a.saha, 'bayt', boyut, 'sha256', h.hexdigest(), 'geri_okuma_hata', hata)
    print(json.dumps({'kapi': kapi, 'karo': say, 'karo_bayt': bayt}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 9) Ana giriş
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('adim', choices=['ara', 'planla', 'tamamla', 'indir', 'mozaik', 'bitir',
                                     'olc', 'halka-hazirla'])
    ap.add_argument('--saha', required=True)
    ap.add_argument('--liste', default=os.path.join(DEPO, 'hrma', 'static', 'map',
                                                   'harita_paketleri.json'))
    ap.add_argument('--calisma', default=os.path.expanduser(
        '~/HRMA-calisma/2026-11-16/FS-HARITA-GORUNTU'))
    ap.add_argument('--onbellek', default=None,
                    help='indirme onbellegi + defter koku (varsayilan: --calisma)')
    ap.add_argument('--kaynak-gecici', default=None,
                    help='halka-hazirla: eski gecici/<saha> dizini (salt okunur)')
    ap.add_argument('--sure', type=float, default=240.0, help='adım süre tavanı [s]')
    ap.add_argument('--kanit', default=None)
    ap.add_argument('--kapi-istisnasi', default=None)
    a = ap.parse_args(argv)
    if a.saha not in SAHA_AYLAR and a.adim != 'olc':
        raise SystemExit('bilinmeyen saha')
    y = Yollar(a.calisma, a.saha, a.onbellek)
    if a.adim == 'olc':
        print(json.dumps(defter_toplami(y.defter), indent=1))
        return
    if a.adim in ('ara', 'planla', 'tamamla', 'indir') \
            and not os.environ.get('HRMA_GORUNTU_COCUK'):
        top = defter_toplami(y.defter)
        if top['toplam_bayt'] >= BUTCE_BAYT:
            print('KARAR GEREKIYOR: indirme butcesi doldu', top['toplam_bayt'])
            sys.exit(4)
        sys.exit(_olcumlu_kos(sys.argv[1:] if argv is None else argv, y, a.adim))
    for k, v in GDAL_ORTAM.items():
        os.environ.setdefault(k, v)
    {'ara': adim_ara, 'planla': adim_planla, 'tamamla': adim_tamamla, 'indir': adim_indir,
     'mozaik': adim_mozaik, 'bitir': adim_bitir, 'halka-hazirla': adim_halka_hazirla}[a.adim](a, y)


if __name__ == '__main__':
    main()
