"""
Real-time Web API Integration for Propellant Data
Fetches live data from NIST, NASA CEA, and other verified sources

Offline behavior (2026-07-16): every fetch now resolves in this order:
1. Fresh disk cache (within TTL)
2. Live network fetch (on success: written to both the disk cache and
   the persistent offline store, hrma.data.offline_store)
3. STALE disk cache, age-unlimited ('stale-if-error')
4. Persistent offline store: user cache file, then the bundled
   offline_snapshot.json shipped with the package
5. Existing static fallback data

So once a combination has been fetched successfully at least once (or is
covered by the bundled snapshot), the application keeps returning real
data with no network available.

Every returned dictionary carries a ``data_state`` key
(live / cached / stale / offline) so the caller can never mistake an aged
record for a fresh one.

Source provenance (P9B5-33, 2026-08-27): the "NIST" fetch does NOT talk to
a NIST server. Its only network source is ``nist-api.fly.dev``, a
third-party crawler of the NIST WebBook; the returned ``source`` field now
names that operator instead of claiming NIST, and ``source_is_official_nist``
carries the same fact machine-readably. Numbers were not touched.
"""

import requests
import json
import tempfile
import time
import re
from typing import Dict, Optional, List
from urllib.parse import urlencode
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import asyncio
import aiohttp
from datetime import datetime, timedelta
import hashlib
import math
import os
from hrma import DATA_DIR, USER_DATA_DIR
from hrma.data import offline_store
# ÖH D15 / P9B4-01: RocketCEA'nın İngiliz birimlerini SI'ya çeviren
# çarpanlar deponun TEK tanım noktasından gelir (cea_bridge). İkinci bir
# 0.3048 / (5/9) literali bu dosyaya yazılmaz.
from hrma.engines.cea_bridge import DEG_R_TO_K, FT_PER_S_TO_M_PER_S
# KU H-5 (K2b-10): peroksit kart adı ve beyanı da aynı tek kaynaktan.
from hrma.engines.cea_bridge import OX_CARD_MAP as _CEA_OX_CARD_MAP
from hrma.engines.cea_bridge import OX_CARD_NOTES as _CEA_OX_CARD_NOTES
from hrma.engines.cea_bridge import _CEA_STATE_LOCK
from hrma.engines.cea_bridge import (
    ensure_isolated_cea_data_dir as _cea_ensure_isolated_dir)
from hrma.constants import G_0, PSIA_PER_BAR

#: Kayıt "NASA doğrulanmış" rozetiyle kullanıcıya çıkıyor; hangi birimden
#: çevrildiği kaydın KENDİ içinde durur.
ROCKETCEA_UNIT_NOTE = (
    'RocketCEA returns c* in ft/s and T_c in Rankine; both were converted '
    'to SI here (c* x 0.3048 -> m/s, T_c x 5/9 -> K)')

# --- Önbellek biçimi (v2.6.26 güvenlik düzeltmesi) ---------------------------
# ESKİ DAVRANIŞ: önbellek kayıtları ``pickle.load`` ile okunuyordu
# (bu dosyanın 88. satırı). Denetimde kurcalanmış bir ``.pkl`` dosyasıyla
# ``/bin/sh`` ÇALIŞTIRILDI (uid=501 doğrulandı): pickle akışı, çözülürken
# rastgele kod çalıştırabilir. Dizin de tahmin edilebilirdi
# (``<repo>/data/propellant_cache/<özet>.pkl``); ne sağlama toplamı ne şema
# vardı, yani kurcalanan dosya sessizce kabul ediliyordu.
#
# YENİ DAVRANIŞ: yalnız sürümlü JSON okunur/yazılır — ``json.load`` kod
# çalıştıramaz. Her kayıt şema sürümü, kaynak URL, alınma zamanı, son
# kullanma ve içerik özeti taşır; özet tutmayan kayıt REDDEDİLİR.
# Eski ``.pkl`` dosyaları OKUNMAZ ve SİLİNMEZ (kullanıcının dosyasıdır);
# yalnızca bir kez günlüğe düşülür.
#
# ŞEMA 2 (P9B5-20, ÖH D16/ihracat a2). Şema numarası VERİ SÖZLEŞMESİNİN de
# numarasıdır. Sözleşme değişti ama numara sabit kaldığı için EMPERYAL
# birimli eski kayıtlar sorgusuz geri dönüyordu:
#
#   ÖLÇÜLDÜ (taban 6fde52b): ``_use_rocketcea_library``ın canlı yolu artık
#   ft/s -> m/s ve °R -> K çeviriyor, AMA çeviri ÖNCESİ yazılmış bir
#   ``schema_version: 1`` kaydı ``_load_cache`` tarafından aynen kabul
#   ediliyordu: ``c_star = 5934,662`` (ft/s), ``chamber_temperature =
#   6672,677`` (°R). Aynı sözlük anahtarı, kaydın YAŞINA göre iki farklı
#   birim taşıyordu. Rapor edilen kirlenme: 186 kaydın 186'sı emperyal.
#
# İki katmanlı onarım: (1) numara 2'ye çıktı — çeviri öncesi yazılmış her
# kayıt artık şema uyuşmazlığından reddedilir; (2) numaradan BAĞIMSIZ bir
# birim sözleşmesi kapısı eklendi (``_birim_sozlesmesi_ihlali``), çünkü
# numara ileride yine unutulabilir ve çevrimdışı depo şema numarası
# taşımıyor.
CACHE_SCHEMA_VERSION = 2
CACHE_FILE_SUFFIX = '.json'
LEGACY_CACHE_SUFFIX = '.pkl'

# Veri durumu damgası: çağırana verinin nereden geldiği AÇIKÇA bildirilir.
# Denetim bulgusu: 10 yıllık bayat kayıt 'NIST API (Live)' etiketiyle
# sunuluyordu; artık bayat kayıt 'Live' etiketi ALAMAZ.
# ---------------------------------------------------------------------------
# Yedek CEA çapası (P9B5-21) — üretilmiş tablo + fizik kapısı
# ---------------------------------------------------------------------------
#
# ÇAPA KOŞULLARI. Yedek yolun sözleşmesi "koşulsuz bir CEA değeri" DEĞİLDİR:
# tablo tek bir çalışma noktasına demirlidir ve o nokta sonuçla birlikte
# yayımlanır (``anchor_conditions``). Basınç ``fetch_nasa_cea_data``ın kendi
# varsayılanı (100 bar); karışım oranları çiftin standart tasarım noktası
# (LOX/LH2 6,0 — RS-25 ~6,0; LOX/RP1 2,5 — modülün kendi varsayılanı);
# genişleme oranı 16 (vakum Isp'sinin tanımlı olması için gerekli).
_CEA_ANCHOR_CONDITIONS = {
    ('lh2', 'lox'): {'chamber_pressure_bar': 100.0, 'mixture_ratio': 6.0,
                     'expansion_ratio': 16.0},
    ('rp1', 'lox'): {'chamber_pressure_bar': 100.0, 'mixture_ratio': 2.5,
                     'expansion_ratio': 16.0},
}

#: Çapa tablosu. Bu sayılar ELLE YAZILMADI — yukarıdaki koşullarla
#: ``cea_bridge.get_combustion_properties`` çağrılarak ÜRETİLDİ
#: (RocketCEA/NASA CEA, ÖH D16/ihracat a2, 1 Eylül 2026). Üretim betiği:
#: ``docs/scofield/raw/OH/D16/ihracat/a2/capa_uret.py``. RocketCEA kurulu
#: olan makinede bu tablo HİÇ kullanılmaz (canlı kapı kazanır); tablo yalnız
#: kütüphanesiz makinede devreye girer ve aynı kaynağın kaydıdır.
_CEA_ANCHOR_TABLE = {
    ('lh2', 'lox'): {
        'isp_vacuum': 430.43124197543625,
        'isp_sea_level': 392.2266490556514,
        'c_star': 2310.9949773552457,
        'chamber_temperature': 3523.790595119956,
        'gamma': 1.142549695937192,
        'molecular_weight': 13.512578523049072,
    },
    ('rp1', 'lox'): {
        'isp_vacuum': 339.0178644237776,
        'isp_sea_level': 309.11399057908426,
        'c_star': 1808.8846648268513,
        'chamber_temperature': 3707.0404366159974,
        'gamma': 1.1421142637757746,
        'molecular_weight': 23.233978430704774,
    },
}

_CEA_ANCHOR_SOURCE = ('Generated CEA anchor table (RocketCEA via cea_bridge, '
                      'Pc=100 bar)')


# ---------------------------------------------------------------------------
# Birim sözleşmesi kapısı (P9B5-20)
# ---------------------------------------------------------------------------
#
# Yayımlanan CEA sözlüğünün birimleri SI'dir. Aşağıdaki tavanlar FİZİKSEL
# zarftır, kalibrasyon parametresi değil: hiçbir kimyasal itici çifti bu
# değerleri aşamaz, dolayısıyla aşan bir sayı ancak BAŞKA BİR BİRİMDE
# yazılmış olabilir.
#
#   * c*: bilinen en yüksek kimyasal karakteristik hız LOX/LH2 ~2400 m/s
#     (H2/F2 gibi egzotik çiftlerde ~2530 m/s). 3000 m/s tavanı cömerttir;
#     ft/s cinsinden aynı değerler 3,28 kat büyüktür (>5000) ve takılır.
#   * T_c: bilinen en yüksek kimyasal alev sıcaklığı ~4700 K (H2/F2).
#     5000 K tavanı cömerttir; Rankine cinsinden aynı değerler 1,8 kat
#     büyüktür (3700 K -> 6660 °R) ve takılır.
CEA_C_STAR_MAX_M_S = 3000.0
CEA_CHAMBER_TEMP_MAX_K = 5000.0


def _birim_sozlesmesi_ihlali(data) -> Optional[str]:
    """CEA gövdesi SI sözleşmesini çiğniyorsa nedeni, çiğnemiyorsa ``None``.

    Şema numarasından BAĞIMSIZ çalışır: hem disk önbelleği hem çevrimdışı
    depo bu kapıdan geçer (depo şema numarası taşımaz).
    """
    if not isinstance(data, dict):
        return None
    cs = data.get('c_star')
    if isinstance(cs, (int, float)):
        birim = data.get('c_star_units')
        # ÖH D17 / P9B4-01 (Fable-D15 ŞART) + OH-D16-14 — KÜNYE ZORUNLU.
        # Fiziksel tavan tek başına YETMEZ: ÖLÇÜLDÜ (taban ``2426b4d``,
        # ``once.json``), künyesiz ``{'c_star': 2500,
        # 'chamber_temperature': 4500}`` kaydı hem ``_kayit_dogrula``dan hem
        # ``_load_offline_store``dan GEÇİYOR ve SI diye servis ediliyordu —
        # oysa 2500 ft/s = 762 m/s'dir ve iki okuma arasında 3,28 kat fark
        # vardır. Tavan yalnız BÜYÜK emperyal sayıları yakalar; bandın
        # altında kalan emperyal kayıt görünmez. Künyesi olmayan sayı
        # KAZANILMAMIŞTIR ve yayımlanmaz (Berke doktrini 1: sessiz varsayım
        # yasak). Üreticiler künyeyi zaten yazıyor (``_use_rocketcea_library``,
        # çapa tablosu, metin ayrıştırıcısı); künyesiz kayıt ancak bu
        # sözleşmeden ÖNCE yazılmış eski bir dosyadır.
        if birim is None:
            return ('c_star carries no unit label; a record written before '
                    'the SI unit contract cannot be republished as m/s '
                    '(the same number reads 3.28x smaller in ft/s)')
        if str(birim) != 'm/s':
            return (f"c_star is labelled {birim!r}; this store publishes "
                    'characteristic velocity in m/s only')
        if cs > CEA_C_STAR_MAX_M_S:
            return (f'c_star is {cs:g}, above the {CEA_C_STAR_MAX_M_S:g} m/s '
                    'physical ceiling for any chemical propellant — the '
                    'record was written in imperial units (ft/s)')
    tc = data.get('chamber_temperature')
    if isinstance(tc, (int, float)):
        birim = data.get('chamber_temperature_units')
        # Aynı gerekçe (P9B4-01): 4500 °R = 2500 K, ikisi de 5000 tavanının
        # altında kalır; künyesiz sayı ayırt edilemez.
        if birim is None:
            return ('chamber_temperature carries no unit label; a record '
                    'written before the SI unit contract cannot be '
                    'republished as K (the same number reads 1.8x smaller '
                    'in Rankine)')
        if str(birim) not in ('K', 'kelvin'):
            return (f"chamber_temperature is labelled {birim!r}; this store "
                    'publishes chamber temperature in K only')
        if tc > CEA_CHAMBER_TEMP_MAX_K:
            return (f'chamber_temperature is {tc:g}, above the '
                    f'{CEA_CHAMBER_TEMP_MAX_K:g} K physical ceiling for any '
                    'chemical propellant — the record was written in '
                    'imperial units (Rankine)')
    return None


def _cf_vakum_ust_siniri(gamma: float) -> float:
    """Vakumda SONSUZ genişleme itki katsayısı üst sınırı CF_max(gamma).

    Sutton & Biblarz, *Rocket Propulsion Elements*, Eq. 3-30'un
    ``p_e -> 0``, ``p_a = 0`` limiti::

        CF_max = sqrt( (2*g^2/(g-1)) * (2/(g+1))^((g+1)/(g-1)) )

    Hiçbir gerçek nozul bunu aşamaz; aşan bir (Isp_vac, c*, gamma) üçlüsü
    ölçüm değil, kendi içinde tutarsız bir tablodur.
    """
    g = float(gamma)
    if not (g > 1.0):
        raise ValueError(f'gamma must be > 1, got {g!r}')
    return math.sqrt((2.0 * g * g / (g - 1.0))
                     * (2.0 / (g + 1.0)) ** ((g + 1.0) / (g - 1.0)))


def _cea_ucluSu_mumkun_mu(data: Dict):
    """(gecti, gerekce) — (Isp_vac, c*, gamma) üçlüsü mümkün mü?

    ``CF = Isp_vac * g0 / c*`` ima edilen itki katsayısıdır; ``CF_max(gamma)``
    sonsuz genişlemedeki üst sınırdır. ``CF > CF_max`` FİZİKSEL OLARAK
    imkânsızdır (P9B5-21'in tam olarak ölçtüğü kusur).
    """
    isp = data.get('isp_vacuum')
    cs = data.get('c_star')
    gm = data.get('gamma')
    if not all(isinstance(x, (int, float)) for x in (isp, cs, gm)):
        return False, 'isp_vacuum / c_star / gamma is missing or non-numeric'
    if not (cs > 0):
        return False, f'c_star is {cs:g}, which is not positive'
    try:
        cf_max = _cf_vakum_ust_siniri(gm)
    except ValueError as exc:
        return False, str(exc)
    cf = float(isp) * G_0 / float(cs)
    if cf > cf_max:
        return False, (f'implied CF = Isp_vac*g0/c* = {cf:.4f} exceeds the '
                       f'infinite-expansion vacuum limit CF_max({gm:.4f}) = '
                       f'{cf_max:.4f} by {(cf / cf_max - 1.0) * 100.0:.1f}%')
    return True, (f'implied CF = {cf:.4f} <= CF_max({gm:.4f}) = {cf_max:.4f} '
                  f'({cf / cf_max * 100.0:.1f}% of the vacuum limit)')


DATA_STATE_LIVE = 'live'        # bu çağrıda ağdan/kütüphaneden yeni alındı
DATA_STATE_CACHED = 'cached'    # disk önbelleği, TTL içinde
DATA_STATE_STALE = 'stale'      # disk önbelleği, süresi geçmiş
DATA_STATE_OFFLINE = 'offline'  # kalıcı depo / paket anlık görüntüsü / statik tablo

_DURUM_ETIKETI = {
    DATA_STATE_LIVE: 'Live',
    DATA_STATE_CACHED: 'Cached',
    DATA_STATE_STALE: 'Stale cache',
    # v3.0.1 (Berke: "online/offline varsa sök"): kullanıcıya görünen künye
    # eki 'Offline store' -> 'Stored copy'. Makine değeri DATA_STATE_OFFLINE
    # ('offline') API uyumu için aynı kalır; değişen yalnız kaynak metnine
    # eklenen etiket (kalıcı depo / paket anlık görüntüsü kaydı).
    DATA_STATE_OFFLINE: 'Stored copy',
}

# En tazeden en bayata: bileşik sonucun durumu bileşenlerinin EN KÖTÜSÜDÜR
_DURUM_SIRASI = (DATA_STATE_LIVE, DATA_STATE_CACHED, DATA_STATE_STALE,
                 DATA_STATE_OFFLINE)

_LIVE_ETIKET_RE = re.compile(r'\(\s*live\s*\)', re.IGNORECASE)
_LIVE_KELIME_RE = re.compile(r'\blive\b', re.IGNORECASE)

# --- Kaynak künyesi KAZANILIR (P9B5-33) --------------------------------------
# ``fetch_nist_data``ın BİRİNCİL (ve tek) ağ kaynağı NIST'in kendi sunucusu
# DEĞİL: ``https://nist-api.fly.dev/crawl.json``, NIST WebBook'u tarayan
# üçüncü taraf bir hizmet. Künye yine de ``'NIST API (Live)'`` yazıyordu;
# okuyucu sayının NIST'in resmî ucundan geldiğini sanıyordu. Sayı DEĞİŞMEZ,
# yalnız kimin verdiği doğru yazılır — kaynak adı gerçek kökeni söylemeli.
#
# '(Live)' eki KASITLI olarak korunuyor: ``_damgala`` bu eki bulup bayat/
# çevrimdışı yollarda '(Stale cache)' / '(Stored copy)' ile değiştiriyor.
NIST_UCUNCU_TARAF_KUNYE = ('NIST WebBook via nist-api.fly.dev '
                           'third-party crawler (Live)')
NIST_UCUNCU_TARAF_ISLETMECI = ('third-party service (nist-api.fly.dev), '
                               'not operated by NIST')


def _icerik_ozeti(payload) -> str:
    """Kayıt gövdesinin kanonik SHA-256 özeti (kurcalama tespiti).

    Anahtarlar sıralanır ki aynı sözlük her zaman aynı özeti versin.
    """
    metin = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(metin.encode('utf-8')).hexdigest()


def _birlesik_durum(durumlar) -> str:
    """Birden çok kaynaktan gelen sonucun ortak durumu = en bayat olanı."""
    en_kotu = DATA_STATE_LIVE
    for durum in durumlar:
        if durum not in _DURUM_SIRASI:
            continue
        if _DURUM_SIRASI.index(durum) > _DURUM_SIRASI.index(en_kotu):
            en_kotu = durum
    return en_kotu

class WebPropellantAPI:
    """Real-time propellant data from NASA/NIST/ESA sources"""

    def __init__(self):
        # PK-01 / P17B4-06: önbellek KULLANICI veri dizinine yazılır. Eskiden
        # DATA_DIR (paketin kendi hrma/data dizini) kullanılıyordu; paketli
        # .app ilk açılışta buraya yazınca kendi kod imzasını bozuyordu.
        self.cache_dir = os.path.join(USER_DATA_DIR, "propellant_cache")
        self.cache_ttl = 3600  # 1 hour cache
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'HRMA/1.0 (Rocket Analysis Tool)',
            'Accept': 'application/json, text/html, */*'
        })
        
        # Önbellek dizini yalnız sahibine açık (0700) oluşturulur: dizin yolu
        # tahmin edilebilir olduğu için başka bir kullanıcının buraya kayıt
        # bırakmasını engelleyen ilk savunma katmanı.
        os.makedirs(self.cache_dir, mode=0o700, exist_ok=True)

        # Eski pickle dosyaları için tek seferlik uyarı defteri (yolun tekrar
        # tekrar günlüğe düşmesini engeller)
        self._legacy_reported = set()

        # API endpoints and configurations (verified URLs)
        self.endpoints = {
            'nist_webbook': 'https://webbook.nist.gov/cgi/fluid.cgi',
            # DİKKAT (P9B5-33): resmî NIST ucu DEĞİL. fetch_nist_data'nın
            # BİRİNCİL kaynağı budur; künyesi bu yüzden NIST'i değil bu
            # üçüncü taraf tarayıcıyı anar (NIST_UCUNCU_TARAF_KUNYE).
            'nist_unofficial': 'https://nist-api.fly.dev/crawl.json',  # Third-party NIST crawler
            'nasa_cea': 'https://cearun.grc.nasa.gov/',
            'spacex_data': 'https://api.spacexdata.com/v4/',
            'rocketcea_lib': 'local'  # Use RocketCEA Python library instead
        }
        
        # Compound ID mappings for NIST (CAS numbers)
        self.nist_compounds = {
            'lox': '7782-44-7',    # Oxygen
            'lh2': '1333-74-0',    # Hydrogen  
            'methane': '74-82-8',  # Methane
            'rp1': '8008-20-6',    # Kerosene (approximate)
            'n2o4': '10544-72-6',  # Nitrogen tetroxide
            'mmh': '60-34-4',      # Monomethylhydrazine
            'udmh': '57-14-7',     # UDMH
            'hydrazine': '302-01-2' # Hydrazine
        }
        
        print("Web Propellant API initialized")
        print(f"Cache directory: {self.cache_dir}")
        print(f"Cache TTL: {self.cache_ttl}s")
    
    def _get_cache_key(self, source: str, compound: str, params: Dict = None) -> str:
        """Generate cache key for request"""
        key_data = f"{source}_{compound}_{str(params) if params else ''}"
        # SHA-256 (kısaltılmış): MD5 ile aynı dosya adı uzunluğu, çakışma
        # direnci yüksek. Anahtar aynı zamanda kaydın İÇİNE yazılır ve
        # okurken karşılaştırılır (dosya adı ↔ içerik bağı).
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    def _cache_path(self, cache_key: str) -> str:
        return os.path.join(self.cache_dir, f"{cache_key}{CACHE_FILE_SUFFIX}")

    def _legacy_pickle_uyar(self, cache_key: str):
        """Eski ``.pkl`` kaydını BİR KEZ bildir — okuma ve silme YOK.

        Geçişte kullanıcının dosyası sessizce silinmez; yalnızca yok
        sayıldığı görünür kılınır. Yeniden çekim (ya da çevrimdışı beyan)
        normal akışla zaten devreye girer.
        """
        legacy = os.path.join(self.cache_dir, f"{cache_key}{LEGACY_CACHE_SUFFIX}")
        if legacy in self._legacy_reported:
            return
        self._legacy_reported.add(legacy)
        if os.path.exists(legacy):
            print(f"Legacy pickle cache ignored (never loaded): "
                  f"{os.path.basename(legacy)}")

    @staticmethod
    def _kayit_dogrula(record, cache_key: str) -> Optional[str]:
        """Kaydı şema + bütünlük açısından denetle; sorun varsa nedenini döndür."""
        if not isinstance(record, dict):
            return 'record is not a JSON object'
        if record.get('schema_version') != CACHE_SCHEMA_VERSION:
            return (f"schema version {record.get('schema_version')!r} "
                    f"!= {CACHE_SCHEMA_VERSION}")
        if record.get('cache_key') != cache_key:
            return 'cache key does not match the file name'
        data = record.get('data')
        if not isinstance(data, dict):
            return 'payload is not a JSON object'
        beklenen = record.get('content_hash')
        if not isinstance(beklenen, str) or beklenen != _icerik_ozeti(data):
            return 'content hash mismatch (tampered or truncated)'
        # P9B5-20: birim sözleşmesi. Bütünlüğü sağlam ama BİRİMİ yanlış bir
        # kayıt da geçersizdir — sayı doğru dosyadan gelmiş olabilir ama
        # yanlış birimde yazılmıştır.
        birim = _birim_sozlesmesi_ihlali(data)
        if birim is not None:
            return f'unit contract violated ({birim})'
        return None

    def _read_cache_record(self, cache_key: str) -> Optional[tuple]:
        """Önbellek kaydını oku; ``(data, yas_saniye)`` ya da ``None``.

        Hiçbir yolda kod çalıştırılmaz: yalnız ``json.load``. Reddetme
        nedenleri: sembolik bağ, bozuk JSON, şema uyuşmazlığı, dosya
        adı ↔ anahtar kopukluğu, içerik özeti tutmaması, çözülemeyen
        zaman damgası.
        """
        self._legacy_pickle_uyar(cache_key)
        cache_file = self._cache_path(cache_key)
        if os.path.islink(cache_file):
            print(f"Cache entry is a symlink, ignored: {cache_key[:8]}")
            return None
        if not os.path.isfile(cache_file):
            return None
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                record = json.load(f)
        except (OSError, ValueError) as e:
            print(f"Cache read error: {e}")
            return None

        red = self._kayit_dogrula(record, cache_key)
        if red is not None:
            print(f"Cache entry rejected ({red}): {cache_key[:8]}")
            return None

        try:
            fetched_at = datetime.fromisoformat(str(record.get('fetched_at')))
        except (TypeError, ValueError):
            print(f"Cache entry rejected (unreadable timestamp): {cache_key[:8]}")
            return None

        # Saat geriye alınmışsa negatif yaş çıkabilir; 0'a kırpılır
        yas = max(0.0, (datetime.now() - fetched_at).total_seconds())
        return record['data'], yas

    def _load_cache(self, cache_key: str, allow_stale: bool = False) -> Optional[Dict]:
        """Load data from cache if valid (allow_stale=True ignores TTL: stale-if-error).

        Dönen sözlük HER ZAMAN durum damgası taşır: TTL içindeki kayıt
        'cached', süresi geçmiş kayıt 'stale'. 'live' damgası YALNIZCA
        canlı çekimde verilir.
        """
        record = self._read_cache_record(cache_key)
        if record is None:
            return None
        data, yas = record

        if yas < self.cache_ttl:
            print(f"Using cached data for {cache_key[:8]} (age {yas:.0f}s)")
            return self._damgala(data, DATA_STATE_CACHED, yas)

        if allow_stale:
            print(f"Using stale cached data for {cache_key[:8]} "
                  f"(age {yas:.0f}s, stale-if-error)")
            return self._damgala(data, DATA_STATE_STALE, yas)

        return None

    def _load_offline_store(self, offline_key: str) -> Optional[Dict]:
        """Load data from persistent offline store (user cache, then bundled snapshot).

        P9B4-19: kaydın YAŞI çağırana taşınır. Depo her kaydın yanına zaman
        damgası yazıyor ama ``offline_store.get()`` yalnız gövdeyi
        döndürdüğü için 39 günlük paketli anlık görüntü ile 39 dakikalık
        veri BİREBİR AYNI görünüyordu. Artık ``get_entry()`` kullanılıyor ve
        yaş ölçülemiyorsa sayı UYDURULMUYOR (``offline_record_age_state``
        'unknown' der).
        """
        kayit = offline_store.get_entry(offline_key)
        if kayit is None:
            return None
        # P9B5-20: çevrimdışı depo şema numarası taşımaz; birim sözleşmesi
        # kapısı buraya da uygulanır (emperyal kayıt disk önbelleğinden
        # reddedilip aynı sayıyı depodan almak onarımı boşa çıkarırdı).
        birim = _birim_sozlesmesi_ihlali(kayit.get('data'))
        if birim is not None:
            print(f'Offline store entry rejected (unit contract violated: '
                  f'{birim}): {offline_key}')
            return None
        yas = kayit.get('age_seconds')
        print(f"Using offline store data for {offline_key} "
              f"(origin {kayit.get('origin')}, age "
              f"{'unknown' if yas is None else f'{yas:.0f}s'})")
        # Depoya yazıldığı anda 'live' damgalı olan iç sözlükler de
        # düzeltilir: depodan okunan hiçbir şey artık canlı değildir.
        out = self._damgala(
            self._damgala_derin(kayit['data'], DATA_STATE_OFFLINE),
            DATA_STATE_OFFLINE)
        if not isinstance(out, dict):
            return out
        out['offline_record_origin'] = kayit.get('origin')
        out['offline_record_timestamp'] = kayit.get('timestamp')
        if yas is None:
            out['offline_record_age_seconds'] = None
            out['offline_record_age_state'] = (
                'unknown - record carries no readable timestamp')
        else:
            out['offline_record_age_seconds'] = round(float(yas), 1)
            out['offline_record_age_days'] = round(float(yas) / 86400.0, 3)
            out['offline_record_age_state'] = 'measured'
        return out

    def _save_cache(self, cache_key: str, data: Dict, source_url: str = ''):
        """Save data to cache as a versioned, hash-protected JSON record."""
        cache_file = self._cache_path(cache_key)

        try:
            # numpy/datetime gibi tipler JSON'a indirgenir; aksi hâlde kayıt
            # yazılamaz ve önbellek sessizce boş kalırdı.
            payload = offline_store.json_safe(data)
            if not isinstance(payload, dict):
                raise TypeError('cache payload must be a mapping')

            simdi = datetime.now()
            record = {
                'schema_version': CACHE_SCHEMA_VERSION,
                'cache_key': cache_key,
                'source_url': str(source_url or ''),
                'fetched_at': simdi.isoformat(timespec='seconds'),
                'expires_at': (simdi + timedelta(seconds=self.cache_ttl)
                               ).isoformat(timespec='seconds'),
                'content_hash': _icerik_ozeti(payload),
                'data': payload,
            }

            os.makedirs(self.cache_dir, mode=0o700, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix='.propcache_', suffix='.tmp',
                                            dir=self.cache_dir)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(record, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.chmod(tmp_path, 0o600)
                os.replace(tmp_path, cache_file)  # atomik: tmp + rename
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            print(f"Cached data for {cache_key[:8]}")
        except (OSError, TypeError, ValueError) as e:
            print(f"Cache write error: {e}")

    @staticmethod
    def _damgala(data: Dict, state: str, age_seconds: float = None) -> Dict:
        """Sonuca veri durumunu (live/cached/stale/offline) AÇIKÇA yaz.

        Bulgu: 10 yıllık bayat önbellek kaydı ``'NIST API (Live)'``
        etiketiyle sunuluyordu. Artık canlı olmayan her dönüş yolunda
        'Live' etiketi gerçek duruma çevrilir ve ``data_state`` anahtarı
        eklenir; uydurma değer üretilmez, yalnız kaynağın adı düzeltilir.
        """
        if not isinstance(data, dict):
            return data
        out = dict(data)
        out['data_state'] = state
        if age_seconds is not None:
            out['cache_age_seconds'] = round(float(age_seconds), 1)

        etiket = _DURUM_ETIKETI.get(state, state)
        kaynak = str(out.get('source') or '')
        if state != DATA_STATE_LIVE and kaynak:
            yeni = _LIVE_ETIKET_RE.sub(f'({etiket})', kaynak)
            if yeni == kaynak and _LIVE_KELIME_RE.search(kaynak):
                yeni = _LIVE_KELIME_RE.sub(etiket, kaynak)
            out['source'] = yeni
        return out

    @classmethod
    def _damgala_derin(cls, data, state):
        """Bileşik sonuçların İÇ sözlüklerindeki durum damgasını da düzelt.

        Kalıcı depoya yazılan bileşik sonuç, yazıldığı andaki 'live'
        damgasını taşır; depodan okunduğunda bu artık doğru değildir.
        Yalnız kaynak/durum taşıyan sözlükler damgalanır (parametre
        sözlükleri kirletilmez).
        """
        if isinstance(data, dict):
            out = {k: cls._damgala_derin(v, state) for k, v in data.items()}
            if 'data_state' in out or 'source' in out or 'status' in out:
                out = cls._damgala(out, state)
            return out
        if isinstance(data, list):
            return [cls._damgala_derin(v, state) for v in data]
        return data

    @staticmethod
    def _dogru_durum(data: Dict) -> Dict:
        """'success' damgasini GERCEGE gore duzeltir.

        v2.6.26 — ayristirma basarisiz oldugunda sozluk
        {'error': ..., 'source': 'NIST API (Live)', 'status': 'success'}
        seklinde donuyordu ve cagiran onu canli veri sayiyordu. Damga her
        donus yolunda (canli fetch, disk onbellegi, kalici depo) ayni kurala
        tabi olmali; yoksa eski onbellek kayitlari yalani tasimaya devam
        eder.
        """
        if not isinstance(data, dict):
            return data
        if data.get('error') or data.get('density') is None:
            if data.get('status') == 'success':
                data = dict(data)
                data['status'] = 'parse_failed'
                kaynak = str(data.get('source') or '')
                if 'not parsable' not in kaynak:
                    data['source'] = (kaynak + ' - response not parsable').strip(' -')
        return data

    def fetch_nist_data(self, compound: str) -> Dict:
        """Fetch real-time data from NIST sources"""
        print(f"Fetching NIST data for {compound}...")
        
        cache_key = self._get_cache_key('nist', compound)
        cached = self._load_cache(cache_key)
        if cached:
            return self._dogru_durum(cached)

        offline_key = offline_store.make_key('webapi', 'nist', compound)

        try:
            # Try unofficial NIST API first
            cas_number = self.nist_compounds.get(compound)
            if not cas_number:
                raise ValueError(f"Unknown compound: {compound}")
            
            # Use unofficial NIST API
            params = {
                'spider_name': 'webbook_nist',
                'start_requests': 'true',
                'crawl_args': f'{{"cas":"{cas_number}"}}'
            }
            
            response = self.session.get(self.endpoints['nist_unofficial'], params=params, timeout=30)
            response.raise_for_status()
            
            # Parse JSON response
            api_data = response.json()
            data = self._parse_nist_api_response(api_data, compound)
            
            # Add metadata
            # P9B5-33 — KÜNYE GERÇEK KÖKENİ SÖYLER. Eskiden burada
            # 'NIST API (Live)' yazıyordu; oysa yanıtı veren NIST değil,
            # NIST WebBook'u tarayan üçüncü taraf bir hizmet
            # (nist-api.fly.dev). Sayıya DOKUNULMADI; yalnız kaynağın adı
            # ve resmî olup olmadığı makinece okunabilir alanlara yazıldı.
            data.update({
                'source': NIST_UCUNCU_TARAF_KUNYE,
                'source_url': self.endpoints['nist_unofficial'],
                'source_operator': NIST_UCUNCU_TARAF_ISLETMECI,
                'source_is_official_nist': False,
                'fetched_at': datetime.now().isoformat(),
                'cas_number': cas_number,
                'status': 'success'
            })
            # v2.6.26 — "success" DAMGASI KOSULLU.
            # Ayristirma basarisiz oldugunda bu sozluk
            #   {'error': "argument of type 'NoneType' is not iterable",
            #    'source': 'NIST API (Live)', 'status': 'success'}
            # seklinde donuyordu. Cagiran onu CANLI veri sayip her alani
            # .get(anahtar, varsayilan) ile okuyordu; sonucta sayfada
            # "NIST (Live)" rozetiyle gosterilen her ozellik aslinda bir
            # varsayilandi (olculdu: LH2 viskozitesi 0,001 gosteriliyordu,
            # gercegi 1,34e-5 — 77 kat). Asagidaki kosul, bir satir altta
            # zaten var olan 'density is None' kontrolunun donen sozluge de
            # uygulanmis halidir; o kontrol yalniz kalici depoyu koruyordu.
            data = self._dogru_durum(data)

            # Cache the result (JSON disk cache + persistent offline store)
            self._save_cache(cache_key, data,
                             source_url=self.endpoints['nist_unofficial'])
            # Kalici depoya yalniz gercek deger tasiyan sonuclar yazilir
            # (ucuncu-taraf API bazen parse edilemeyen 'success' donduruyor)
            if data.get('density') is not None:
                offline_store.put(offline_key, data)

            print(f"NIST data fetched for {compound}")
            return self._damgala(data, DATA_STATE_LIVE)

        except Exception as e:
            print(f"NIST API failed for {compound}: {str(e)}")
            # stale-if-error: bayat disk onbellegi yas siniri olmadan kullanilir
            # (v2.6.26: pickle degil, ozetli JSON; donus 'stale' damgali gelir)
            stale = self._load_cache(cache_key, allow_stale=True)
            if stale is not None:
                return self._dogru_durum(stale)
            # Persistent offline store (user cache -> bundled snapshot)
            stored = self._load_offline_store(offline_key)
            if stored is not None:
                return self._dogru_durum(stored)
            # Try direct NIST webbook as fallback
            return self._dogru_durum(self._try_direct_nist(compound))
    
    def fetch_nasa_cea_data(self, fuel: str, oxidizer: str, chamber_pressure: float = 100, mixture_ratio: float = 2.5) -> Dict:
        """Fetch real-time NASA CEA combustion data"""
        print(f"Fetching NASA CEA data for {fuel}/{oxidizer}...")
        
        cache_key = self._get_cache_key('cea', f"{fuel}_{oxidizer}", {
            'pc': chamber_pressure, 'mr': mixture_ratio
        })
        cached = self._load_cache(cache_key)
        if cached:
            return cached

        offline_key = offline_store.make_key('webapi', 'cea', fuel, oxidizer,
                                             float(chamber_pressure), float(mixture_ratio))

        # Try RocketCEA library first (more reliable)
        try:
            results = self._use_rocketcea_library(fuel, oxidizer, chamber_pressure, mixture_ratio)
            if results.get('status') == 'success':
                # Cache the result (JSON disk cache + persistent offline store)
                self._save_cache(cache_key, results,
                                 source_url='local:rocketcea')
                offline_store.put(offline_key, results)
                print(f"NASA CEA data fetched via RocketCEA for {fuel}/{oxidizer}")
                return self._damgala(results, DATA_STATE_LIVE)
        except Exception as e:
            print(f"RocketCEA failed: {str(e)}")
        
        # Fallback to web interface
        try:
            # NASA CEA web interface
            cea_url = self.endpoints['nasa_cea']
            
            # Prepare CEA input file format
            cea_input = self._generate_cea_input(fuel, oxidizer, chamber_pressure, mixture_ratio)
            
            # Submit to CEA web interface
            cea_data = {
                'inputfile': cea_input,
                'output_format': 'short',
                'submit': 'Run CEA'
            }
            
            response = self.session.post(cea_url + 'cgi-bin/CEA.pl', data=cea_data, timeout=60)
            response.raise_for_status()
            
            # Parse CEA output
            results = self._parse_cea_output(response.text, fuel, oxidizer)
            
            # Add metadata
            results.update({
                'source': 'NASA CEA Web (Live)',
                'fetched_at': datetime.now().isoformat(),
                'input_parameters': {
                    'fuel': fuel,
                    'oxidizer': oxidizer,
                    'chamber_pressure': chamber_pressure,
                    'mixture_ratio': mixture_ratio
                },
                'status': 'success'
            })
            
            # Cache the result (JSON disk cache + persistent offline store)
            self._save_cache(cache_key, results,
                             source_url=cea_url + 'cgi-bin/CEA.pl')
            offline_store.put(offline_key, results)

            print(f"NASA CEA web data fetched for {fuel}/{oxidizer}")
            return self._damgala(results, DATA_STATE_LIVE)

        except Exception as e:
            print(f"NASA CEA web failed: {str(e)}")
            # stale-if-error: bayat disk onbellegi yas siniri olmadan kullanilir
            # (v2.6.26: pickle degil, ozetli JSON; donus 'stale' damgali gelir)
            stale = self._load_cache(cache_key, allow_stale=True)
            if stale is not None:
                return stale
            # Persistent offline store (user cache -> bundled snapshot)
            stored = self._load_offline_store(offline_key)
            if stored is not None:
                return stored
            return self._get_fallback_cea_data(fuel, oxidizer)
    
    def _parse_nist_api_response(self, api_data: Dict, compound: str) -> Dict:
        """Parse unofficial NIST API JSON response"""
        try:
            data = {
                'compound': compound,
                'density': None,
                'viscosity': None,
                'thermal_conductivity': None,
                'specific_heat': None,
                'boiling_point': None
            }
            
            # Extract data from JSON response
            if 'items' in api_data:
                items = api_data['items']
                for item in items:
                    # Look for thermophysical properties
                    if 'properties' in item:
                        props = item['properties']
                        
                        # Extract density
                        if 'density' in props:
                            data['density'] = float(props['density'])
                        
                        # Extract viscosity
                        if 'viscosity' in props:
                            data['viscosity'] = float(props['viscosity'])
            
            return data
            
        except Exception as e:
            print(f"NIST API parsing error: {e}")
            return {'error': str(e), 'compound': compound}
    
    def _try_direct_nist(self, compound: str) -> Dict:
        """Try direct NIST webbook access as fallback"""
        try:
            # Simplified direct access
            print(f"Trying direct NIST access for {compound}...")
            
            # Use known properties for common compounds
            direct_data = {
                'lox': {
                    'density': 1141.7,
                    'viscosity': 0.000194,
                    'thermal_conductivity': 0.150,
                    'boiling_point': 90.188
                },
                'lh2': {
                    'density': 70.85,
                    'viscosity': 1.34e-5,
                    'thermal_conductivity': 0.1005,
                    'boiling_point': 20.369
                },
                'methane': {
                    'density': 422.6,
                    'viscosity': 1.17e-4,
                    'thermal_conductivity': 0.195,
                    'boiling_point': 111.66
                }
            }
            
            if compound in direct_data:
                data = direct_data[compound].copy()
                data.update({
                    'compound': compound,
                    'source': 'NIST Direct (Verified)',
                    'status': 'success'
                })
                # Bu bir AĞ çekimi değil, kaynaklı yerleşik tablodur;
                # 'live' damgası verilmez.
                return self._damgala(data, DATA_STATE_OFFLINE)

            return self._get_fallback_data(compound, 'direct_nist_error')
            
        except Exception as e:
            return self._get_fallback_data(compound, f'direct_error_{str(e)}')
    
    def _use_rocketcea_library(self, fuel: str, oxidizer: str, chamber_pressure: float, mixture_ratio: float) -> Dict:
        """Use RocketCEA Python library for NASA CEA calculations"""
        try:
            # Try to import RocketCEA
            from rocketcea.cea_obj import CEA_Obj
            
            # Map fuel/oxidizer names to RocketCEA format
            cea_fuel_map = {
                'rp1': 'RP1',
                'lh2': 'LH2',
                'methane': 'CH4',
                'mmh': 'MMH',
                'udmh': 'UDMH',
                'hydrazine': 'N2H4'
            }
            
            # KU H-5 (K2b-10) — KART ADI DÜZELDİ, SAYI SEÇİMİ YAPILMADI.
            # 'H2O2_98' RocketCEA'da YOK (doğru ad '98_H2O2'). ÖLÇÜLDÜ
            # (taban 9842af22): bu yol her 'h2o2' çağrısında "bad oxidizer
            # name (H2O2_98)" hatasıyla düşüyordu ('rocketcea_error');
            # ağsız makinede zincirin sonu 'not_modelled' idi. Ad artık
            # deponun TEK eşlemesinden (``cea_bridge.OX_CARD_MAP``) okunur:
            # kardeş yollar ('h2o2' -> 'H2O2', %100) ile aynı kart. %90/%98
            # HTP'ye geçmek bir değer seçimidir; bu kalemde yapılmadı ve
            # yanıt hangi kartın çözüldüğünü ``oxidizer_card_note`` ile söyler.
            cea_ox_map = {
                'lox': 'LOX',
                'n2o4': 'N2O4',
                'h2o2': _CEA_OX_CARD_MAP['h2o2'],
            }
            
            cea_fuel = cea_fuel_map.get(fuel, fuel.upper())
            cea_ox = cea_ox_map.get(oxidizer, oxidizer.upper())
            
            # K-4 (V3 kararlılık 2. tur): kurulum ve bütün CEA çağrıları
            # köprünün TEK süreç kilidi altında (Fortran COMMON durumu
            # süreç-global; 4 iş parçacığında sessiz yanlış sayı ölçüldü),
            # kurucu da bu sürecin yalıtılmış veri dizininde çalışır.
            _cea_ensure_isolated_dir()
            with _CEA_STATE_LOCK:
                # Create CEA object
                cea_obj = CEA_Obj(oxName=cea_ox, fuelName=cea_fuel)
            
                # Calculate properties
                # ÖH D30 / fix-29a — SAYI DEĞİŞTİ, BEYANLI. P15B2-10 (ÖH D29,
                # ec8fe7d8) bar -> psia katsayısının üç kopyasını merkeze
                # bağlamıştı; bu DÖRDÜNCÜ kopya görülmemişti, çünkü
                # ``tools/sabit_envanteri.py`` ``IN_M ** 2`` üssünü
                # çözemediği için PSIA_PER_BAR envantere hiç girmiyordu
                # (kör band, fix-29a'da kapatıldı). 14,504 -> 14,503773773
                # (kesin tanımlardan türetilir); bağıl fark -1,56e-5.
                chamber_pressure_psia = chamber_pressure * PSIA_PER_BAR
            
                # Get combustion properties
                # get_Chamber_MolWt_gamma returns (MolWt, gamma) - correct API for RocketCEA 1.2.x
                try:
                    mw_gamma = cea_obj.get_Chamber_MolWt_gamma(Pc=chamber_pressure_psia, MR=mixture_ratio, eps=1.0)
                    gamma_val = mw_gamma[1]
                    mw_val = mw_gamma[0]
                except AttributeError:
                    # Fallback for older/newer RocketCEA versions
                    gamma_val = 1.2  # Typical combustion gas gamma
                    mw_val = 22.0   # Typical exhaust molecular weight
                    print("Warning: get_Chamber_MolWt_gamma not available, using defaults")

                # P9B5-23 — 'isp_sea_level' ADI KAZANILMAMIŞTI.
                # ``CEA_Obj.get_Isp(..., eps=N)`` her zaman o genişleme oranındaki
                # VAKUM Isp'sini döndürür; ortam basıncı hesaba girmez. eps=16'nın
                # sayısı bu yüzden bir deniz seviyesi değeri DEĞİL, yalnız daha
                # küçük bir lülenin vakum değeridir (ölçüldü: RP-1/LOX 20 bar,
                # MR 2,5 -> eps=200: 377,338 s, eps=16: 335,771 s; gerçek deniz
                # seviyesi değeriyle fark %+9,7). Sayı DEĞİŞMEDİ, adı düzeldi:
                # artık hangi genişleme oranının vakum değeri olduğu yazıyor.
                # Deniz seviyesi Isp'si ortam basıncı düzeltmesi ister; bu modül
                # onu HESAPLAMIYOR, o yüzden alanı BASMIYOR (fail-closed) ve
                # gerekçesini adlandırıyor.
                results = {
                    'fuel': fuel,
                    'oxidizer': oxidizer,
                    'isp_vacuum': cea_obj.get_Isp(Pc=chamber_pressure_psia, MR=mixture_ratio, eps=200),
                    'isp_vacuum_expansion_ratio': 200,
                    'isp_vacuum_eps16': cea_obj.get_Isp(Pc=chamber_pressure_psia, MR=mixture_ratio, eps=16),
                    'isp_vacuum_eps16_expansion_ratio': 16,
                    'isp_sea_level_withheld_reason': (
                        'RocketCEA get_Isp(eps=N) returns the VACUUM Isp at that '
                        'area ratio; no ambient-pressure correction is applied '
                        'here, so no sea-level value is published'),
                    # ÖH D15 / defter P9B4-01 — ETİKET SAYIYA UYMUYORDU.
                    # ``rocketcea`` bu iki çağrıda İNGİLİZ birimi döndürür
                    # (c* ft/s, T_c Rankine) ve buradaki sözlük onları hiçbir
                    # çevrim yapmadan SI etiketli anahtarlara yazıyordu.
                    # ÖLÇÜLDÜ (kaydın kendi iç tutarlılığıyla, dış referans
                    # GEREKMEDEN): ideal c* özdeşliği
                    # ``c* = sqrt(R_u/M * T_c) / Gamma(gamma)`` (Sutton &
                    # Biblarz Eq. 3-32) bu yoldan üretilmiş 7 çevrimdışı kaydın
                    # 7'sinde de yalnız (ft/s, °R) yorumunda sağlanıyordu
                    # (|hata| <= %0,21); SI yorumunda sapma +%144,0..144,7 idi.
                    # RP-1/LOX: c* 5831,3 -> 1777,4 m/s (3,28x),
                    # T_c 6270,5 -> 3483,6 K (1,80x).
                    # Çarpanlar burada YENİDEN YAZILMAZ: deponun tek tanım
                    # noktası ``cea_bridge`` (aynı kütüphaneyi zaten doğru
                    # çeviren kardeş yol) ve oradan ithal edilir.
                    'c_star': float(cea_obj.get_Cstar(
                        Pc=chamber_pressure_psia,
                        MR=mixture_ratio)) * FT_PER_S_TO_M_PER_S,
                    'c_star_units': 'm/s',
                    'chamber_temperature': float(cea_obj.get_Tcomb(
                        Pc=chamber_pressure_psia,
                        MR=mixture_ratio)) * DEG_R_TO_K,
                    'chamber_temperature_units': 'K',
                    'unit_conversion_note': ROCKETCEA_UNIT_NOTE,
                    'gamma': gamma_val,
                    'molecular_weight': mw_val,
                    'source': 'RocketCEA Library (NASA CEA)',
                    'fetched_at': datetime.now().isoformat(),
                    'status': 'success'
                }
            # KU H-5: kartı addan anlaşılmayan oksitleyicide hangi kartın
            # çözüldüğü yanıtta yazılır (sayı taşımaz).
            if cea_ox in _CEA_OX_CARD_NOTES:
                results['oxidizer_card'] = cea_ox
                results['oxidizer_card_note'] = _CEA_OX_CARD_NOTES[cea_ox]

            return results

        except ImportError:
            print("RocketCEA library not installed, using fallback")
            return {'status': 'rocketcea_not_available'}
        except Exception as e:
            print(f"RocketCEA calculation error: {str(e)}")
            return {'status': 'rocketcea_error', 'error': str(e)}
    
    def fetch_spacex_telemetry(self) -> Dict:
        """Fetch SpaceX public telemetry data for validation"""
        print("Fetching SpaceX public data...")
        
        cache_key = self._get_cache_key('spacex', 'telemetry')
        cached = self._load_cache(cache_key)
        if cached:
            return cached

        offline_key = offline_store.make_key('webapi', 'spacex')

        try:
            # SpaceX API for launch data
            response = self.session.get(self.endpoints['spacex_data'] + 'launches/latest', timeout=30)
            response.raise_for_status()
            
            launch_data = response.json()

            # P9B5-22 — KÜNYE SAYIYI SAYMIYORDU.
            # Bu blok 'SpaceX Public API' künyesiyle altı alan sunuyordu ama
            # API'den okunan TEK alan uçuş tarihiydi; itki, Isp ve karışım
            # oranı bu dosyaya GÖMÜLÜ sabitlerdir (v4 launches/latest yanıtı
            # motor performansı içermez, üstelik uç bugün HTTP 525 dönüyor).
            # Sayılar DEĞİŞMEDİ — yalnız hangisinin API'den geldiği, hangisinin
            # gömülü sabit olduğu ayrı ayrı yazıldı.
            _SABIT_ALANLAR = ['propellants', 'thrust_sea_level',
                              'thrust_vacuum', 'isp_sea_level', 'isp_vacuum',
                              'mixture_ratio']
            son_ucus = launch_data.get('date_utc') if isinstance(
                launch_data, dict) else None

            motor = {
                'propellants': 'RP-1/LOX',
                'thrust_sea_level': 845000,  # N per engine
                'thrust_vacuum': 914000,     # N per engine
                'isp_sea_level': 282,        # s
                'isp_vacuum': 311,           # s
                'mixture_ratio': 2.56,       # Verified
                'source': ('Built-in Falcon 9 / Merlin 1D reference constants '
                           '(published specifications) - NOT returned by the '
                           'SpaceX API'),
                'constant_fields': _SABIT_ALANLAR,
                'api_source': self.endpoints['spacex_data'] + 'launches/latest',
                'api_derived_fields': ['last_flight'] if son_ucus else [],
            }
            if son_ucus:
                motor['last_flight'] = son_ucus
            else:
                motor['last_flight_withheld_reason'] = (
                    "SpaceX API response carried no 'date_utc' field; no "
                    'flight date is published')

            # Extract propellant info from Falcon 9 data
            rocket_data = {'falcon9_merlin': motor}


            # Cache the result (JSON disk cache + persistent offline store)
            self._save_cache(
                cache_key, rocket_data,
                source_url=self.endpoints['spacex_data'] + 'launches/latest')
            offline_store.put(offline_key, rocket_data)

            print("SpaceX data fetched")
            return self._damgala(rocket_data, DATA_STATE_LIVE)

        except Exception as e:
            print(f"SpaceX fetch failed: {str(e)}")
            # stale-if-error: bayat disk onbellegi yas siniri olmadan kullanilir
            # (v2.6.26: pickle degil, ozetli JSON; donus 'stale' damgali gelir)
            stale = self._load_cache(cache_key, allow_stale=True)
            if stale is not None:
                return stale
            # Persistent offline store (user cache -> bundled snapshot)
            stored = self._load_offline_store(offline_key)
            if stored is not None:
                return stored
            return {'error': str(e), 'source': 'spacex_error'}
    
    def _parse_nist_response(self, html_content: str, compound: str) -> Dict:
        """Parse NIST Webbook HTML response"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for data tables
            tables = soup.find_all('table')
            
            if not tables:
                raise ValueError("No data tables found in NIST response")
            
            # Parse thermophysical properties table
            data = {
                'compound': compound,
                'density': None,
                'viscosity': None,
                'thermal_conductivity': None,
                'specific_heat': None,
                'surface_tension': None,
                'properties': []
            }
            
            # Extract data from HTML tables
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        # Extract numerical data
                        cell_texts = [cell.get_text().strip() for cell in cells]
                        
                        # Look for density data
                        if 'density' in cell_texts[0].lower() and len(cell_texts) > 1:
                            try:
                                data['density'] = float(re.findall(r'[\d.]+', cell_texts[1])[0])
                            except:
                                pass
                        
                        # Look for viscosity data  
                        if 'viscosity' in cell_texts[0].lower() and len(cell_texts) > 1:
                            try:
                                data['viscosity'] = float(re.findall(r'[\d.e-]+', cell_texts[1])[0])
                            except:
                                pass
            
            # If no data extracted, use regex on full text
            if not data['density']:
                density_match = re.search(r'Density.*?(\d+\.?\d*)', html_content, re.IGNORECASE)
                if density_match:
                    data['density'] = float(density_match.group(1))
            
            return data
            
        except Exception as e:
            print(f"NIST parsing error: {e}")
            return {'error': str(e), 'compound': compound}
    
    def _generate_cea_input(self, fuel: str, oxidizer: str, pressure: float, mixture_ratio: float) -> str:
        """Generate CEA input file format"""
        
        # Map fuel/oxidizer to CEA names
        cea_fuels = {
            'rp1': 'RP-1',
            'lh2': 'H2(L)',
            'methane': 'CH4(L)',
            'mmh': 'CH3NHNH2(L)',
            'udmh': '(CH3)2NNH2(L)',
            'hydrazine': 'N2H4(L)'
        }
        
        cea_oxidizers = {
            'lox': 'O2(L)',
            'n2o4': 'N2O4(L)',
            'h2o2': 'H2O2(L)'
        }
        
        cea_fuel = cea_fuels.get(fuel, fuel.upper())
        cea_ox = cea_oxidizers.get(oxidizer, oxidizer.upper())
        
        cea_input = f"""
prob case=HRMA rocket equilibrium
  p,bar= {pressure}
  o/f= {mixture_ratio}
react
  fuel {cea_fuel} wt%=100.000
  oxid {cea_ox} wt%=100.000
output
  siunits short
  transport
  thermodynamic properties
end
"""
        return cea_input.strip()
    
    def _parse_cea_output(self, output_text: str, fuel: str, oxidizer: str) -> Dict:
        """Parse NASA CEA output text"""
        try:
            # P9B5-23 (ikinci ayak) — 'isp_sea_level' burada da KAZANILMAMIŞTI:
            # ``isp_vacuum * 0,88`` çarpanı hiçbir çalışma noktasından, hiçbir
            # kaynaktan gelmiyordu ("# Approximate" dışında dayanağı yoktu) ve
            # sonuç, sanki CEA'nın kendi ayrıştırılmış çıktısıymış gibi
            # yayımlanıyordu (ölçüldü: Isp_vac 350,5 -> 308,44). Deniz seviyesi
            # Isp'si genişleme oranına ve ortam basıncına bağlıdır; sabit bir
            # oranla üretilemez. Uydurma sayı BASILMIYOR, gerekçe adlandırılıyor.
            data = {
                'fuel': fuel,
                'oxidizer': oxidizer,
                'isp_vacuum': None,
                'isp_sea_level_withheld_reason': (
                    'sea-level Isp requires an ambient-pressure correction at '
                    'the actual expansion ratio; the previous 0.88 factor had '
                    'no source and is not published'),
                'c_star': None,
                'chamber_temperature': None,
                'gamma': None,
                'molecular_weight': None
            }

            # Parse specific impulse
            isp_match = re.search(r'Isp,\s*sec\s+(\d+\.?\d*)', output_text)
            if isp_match:
                data['isp_vacuum'] = float(isp_match.group(1))

            # Parse c* (characteristic velocity)
            # ÖH D17 / P9B4-01: künye AYRIŞTIRMANIN KENDİSİNDEN kazanılır —
            # desen 'CSTAR, M/SEC' başlığını şart koşuyor, yani eşleşen sayı
            # tanım gereği m/s'dir. Künye yazılmazsa okuma kapısı (bkz.
            # ``_birim_sozlesmesi_ihlali``) bu kaydı haklı olarak reddeder.
            cstar_match = re.search(r'CSTAR,\s*M/SEC\s+(\d+\.?\d*)', output_text)
            if cstar_match:
                data['c_star'] = float(cstar_match.group(1))
                data['c_star_units'] = 'm/s'
            
            # Parse chamber temperature
            temp_match = re.search(r'T,\s*K\s+(\d+\.?\d*)', output_text)
            if temp_match:
                data['chamber_temperature'] = float(temp_match.group(1))
                data['chamber_temperature_units'] = 'K'
            
            # Parse gamma
            gamma_match = re.search(r'GAMMAs\s+(\d+\.?\d*)', output_text)
            if gamma_match:
                data['gamma'] = float(gamma_match.group(1))
            
            # Parse molecular weight
            mw_match = re.search(r'M,\s*\(1/n\)\s+(\d+\.?\d*)', output_text)
            if mw_match:
                data['molecular_weight'] = float(mw_match.group(1))
            
            return data
            
        except Exception as e:
            print(f"CEA parsing error: {e}")
            return {'error': str(e), 'fuel': fuel, 'oxidizer': oxidizer}
    
    def _get_fallback_data(self, compound: str, error_type: str) -> Dict:
        """Provide fallback data when web fetch fails"""
        
        fallback_data = {
            'lox': {
                'name': 'Liquid Oxygen',
                'density': 1141.7,
                'viscosity': 0.000194,
                'thermal_conductivity': 0.150,
                'specific_heat': 1699,
                'boiling_point': 90.188
            },
            'rp1': {
                'name': 'RP-1 Kerosene',
                'density': 815.0,
                'viscosity': 0.00164,
                'thermal_conductivity': 0.145,
                'specific_heat': 2090,
                'heat_of_combustion': 43.135e6
            },
            'lh2': {
                'name': 'Liquid Hydrogen',
                'density': 70.85,
                'viscosity': 1.34e-5,
                'thermal_conductivity': 0.1005,
                'specific_heat': 9715,
                'boiling_point': 20.369
            },
            'methane': {
                'name': 'Liquid Methane',
                'density': 422.6,
                'viscosity': 1.17e-4,
                'thermal_conductivity': 0.195,
                'specific_heat': 3483,
                'boiling_point': 111.66
            }
        }
        
        data = fallback_data.get(compound, {
            'name': compound,
            'density': 800,
            'viscosity': 0.001,
            'error': 'Unknown compound'
        })
        
        data.update({
            'source': f'Fallback Data ({error_type})',
            'status': 'fallback',
            'fetched_at': datetime.now().isoformat()
        })

        return self._damgala(data, DATA_STATE_OFFLINE)

    def _get_fallback_cea_data(self, fuel: str, oxidizer: str) -> Dict:
        """Ağ + önbellek + çevrimdışı depo boşken son kaynak (P9B5-21).

        ÖLÇÜLDÜ (ÖH D16/ihracat a2, taban 6fde52b): eski elle yazılmış tablo
        TERMODİNAMİK OLARAK İMKÂNSIZ üçlüler taşıyordu. İma edilen itki
        katsayısı ``CF = Isp_vac·g0/c*`` vakumda sonsuz genişlemedeki üst
        sınırı ``CF_max(gamma)`` aşıyordu:

            ('lh2','lox') Isp 451,8 · c* 1580,0 · gamma 1,2398
                          -> CF 2,8042 > CF_max 2,1099   (**+%32,9**)
            ('rp1','lox') Isp 353,2 · c* 1520,0 · gamma 1,2165
                          -> CF 2,2788 > CF_max 2,1847   (**+%4,3**)

        Koddaki gerekçe de yanlışı "düzeltme" diye kayda geçirmişti:
        ``# NASA RS-25 effective C* value (theoretical: 2356.7, but
        effective ~67%)`` — RS-25'in gerçek c* verimi ~%99'dur, %67
        uydurmadır. Üçlü kendi içinde tutarsız olduğu için hangi alanın
        okunduğuna göre FARKLI yanlış sonuç veriyordu.

        Yeni sözleşme:

        1. **Tek kaynak.** Sayılar önce deponun kendi CEA kapısından
           (``cea_bridge.get_combustion_properties``) ÇÖZÜLÜR. Bu, canlı
           yolun da kullandığı modüldür; ikinci bir elle yazılmış tablo
           tutulmaz.
        2. **Çapa tablosu üretilmiştir, uydurulmamıştır.** RocketCEA
           kurulu değilse ``_CEA_ANCHOR_TABLE`` kullanılır; içindeki her
           satır aynı ``cea_bridge`` çağrısıyla ÜRETİLDİ ve hangi koşulda
           üretildiği (``anchor_conditions``) sonuçla birlikte yayımlanır —
           koşulsuz bir "CEA değeri" gibi okunamaz.
        3. **Fizik kapısı.** Yayımlanmadan önce üçlü ``CF <= CF_max(gamma)``
           denetiminden geçer. Geçmezse SAYI YAYIMLANMAZ: ``status:
           'not_modelled'`` + hangi denetimin düştüğü. Böylece bu kusur
           sınıfı bir daha sessizce giremez.
        4. **Bilinmeyen çift için sayı yok.** Eski kod tanımadığı HER çift
           için (320 s / 1650 / 3200 / 1,22 / 25) uyduruyordu. Artık
           tanınmayan çift fail-closed işaretlenir.
        """
        cozum = self._cea_cozumu(fuel, oxidizer)
        if cozum is None:
            data = {
                'fuel': fuel,
                'oxidizer': oxidizer,
                'source': 'No CEA source available',
                'status': 'not_modelled',
                'error': (
                    f"No CEA data could be resolved for '{fuel}'/'{oxidizer}': "
                    'the network, the disk cache and the offline store are all '
                    'empty, RocketCEA is not available and this propellant pair '
                    'has no generated anchor entry. No substitute numbers are '
                    'invented.'),
                'fetched_at': datetime.now().isoformat(),
            }
            return self._damgala(data, DATA_STATE_OFFLINE)

        data, kunye = cozum
        gecti, gerekce = _cea_ucluSu_mumkun_mu(data)
        if not gecti:
            # Fizik kapısı düştü: sayı YAYIMLANMAZ (beyan çözüm değildir).
            temiz = {
                'fuel': fuel,
                'oxidizer': oxidizer,
                'source': kunye,
                'status': 'not_modelled',
                'error': (
                    f"The CEA anchor for '{fuel}'/'{oxidizer}' failed the "
                    f'thermodynamic consistency check ({gerekce}); the values '
                    'are withheld rather than published.'),
                'fetched_at': datetime.now().isoformat(),
            }
            return self._damgala(temiz, DATA_STATE_OFFLINE)

        data = dict(data)
        data.update({
            'fuel': fuel,
            'oxidizer': oxidizer,
            'source': kunye,
            'status': 'fallback',
            'c_star_units': 'm/s',
            'chamber_temperature_units': 'K',
            'anchor_conditions': dict(_CEA_ANCHOR_CONDITIONS[(fuel, oxidizer)]),
            'consistency_check': gerekce,
            'fetched_at': datetime.now().isoformat(),
        })

        return self._damgala(data, DATA_STATE_OFFLINE)

    def _cea_cozumu(self, fuel: str, oxidizer: str):
        """(veri, künye) ya da None — yedek CEA sayılarının TEK çözüm yolu.

        Önce canlı kapı (``cea_bridge``), sonra ondan ÜRETİLMİŞ çapa satırı.
        """
        kosul = _CEA_ANCHOR_CONDITIONS.get((str(fuel).lower(),
                                            str(oxidizer).lower()))
        if kosul is None:
            return None
        try:
            from hrma.engines import cea_bridge
            r = cea_bridge.get_combustion_properties(
                fuel, oxidizer, kosul['chamber_pressure_bar'],
                kosul['mixture_ratio'],
                expansion_ratio=kosul['expansion_ratio'])
            if (r.get('source') == 'rocketcea'
                    and r.get('c_star_m_s') and r.get('isp_vac_s')):
                return ({
                    'isp_vacuum': float(r['isp_vac_s']),
                    'isp_sea_level': (float(r['isp_sl_s'])
                                      if r.get('isp_sl_s') else None),
                    'c_star': float(r['c_star_m_s']),
                    'chamber_temperature': float(r['tc_k']),
                    'gamma': float(r['gamma_chamber']),
                    'molecular_weight': float(r['mw_g_mol']),
                }, 'CEA anchor solved live via cea_bridge (RocketCEA)')
        except Exception as exc:  # pragma: no cover - kütüphane yoksa
            print(f'cea_bridge anchor unavailable: {exc}')
        satir = _CEA_ANCHOR_TABLE.get((str(fuel).lower(),
                                       str(oxidizer).lower()))
        if satir is None:
            return None
        return dict(satir), _CEA_ANCHOR_SOURCE

    def get_comprehensive_data(self, fuel: str, oxidizer: str, **kwargs) -> Dict:
        """Get comprehensive propellant data from all sources"""
        print(f"Fetching comprehensive data for {fuel}/{oxidizer}...")

        pressure = kwargs.get('pressure', 100)
        mixture_ratio = kwargs.get('mixture_ratio', 2.5)
        offline_key = offline_store.make_key('webapi', fuel, oxidizer,
                                             float(pressure), float(mixture_ratio))

        fuel_props = self.fetch_nist_data(fuel)
        ox_props = self.fetch_nist_data(oxidizer)
        combustion_data = self.fetch_nasa_cea_data(fuel, oxidizer, pressure, mixture_ratio)

        # Guven seviyesi zaten cekilmis sonuclardan hesaplanir (tekrar fetch yok;
        # ag yokken 3 ekstra timeout beklenmesin)
        all_success = all([
            fuel_props.get('status') == 'success',
            ox_props.get('status') == 'success',
            combustion_data.get('status') == 'success'
        ])

        # Bileşik sonucun tazeliği, en bayat bileşeni kadardır. Bu değer
        # HESAPLANIR (uydurulmaz): üç alt sonucun kendi damgalarından gelir.
        birlesik_durum = _birlesik_durum([
            fuel_props.get('data_state', DATA_STATE_OFFLINE),
            ox_props.get('data_state', DATA_STATE_OFFLINE),
            combustion_data.get('data_state', DATA_STATE_OFFLINE),
        ])

        # P9B5-24 — GÜVEN ARTIK YAŞA DA BAKIYOR.
        # Eski kural tek girdiliydi: ``'high' if all_success else 'medium'``.
        # 'success' yalnız "yanıt ayrıştırılabildi" demektir; kaydın 10 yıllık
        # bir bayat önbellek girdisi olması bu hükmü hiç değiştirmiyordu —
        # 'stale' damgalı sonuç yine 'high' güven üretiyordu. Tazelik zaten
        # ÖLÇÜLÜYOR (data_state), hükme sokulmuyordu. Yeni eşleme, yeni bir
        # eşik icat etmez; yalnız iki mevcut ölçümü birleştirir ve kuralı
        # 'confidence_basis' alanında yazılı hâle getirir.
        _TAZE_DURUMLAR = (DATA_STATE_LIVE, DATA_STATE_CACHED)
        if all_success and birlesik_durum in _TAZE_DURUMLAR:
            guven = 'high'
        elif birlesik_durum == DATA_STATE_STALE:
            # TTL'i dolmuş disk kaydı: yaşı üst sınırsız (stale-if-error)
            guven = 'low'
        elif all_success:
            # Kalıcı depo / paket anlık görüntüsü: küratörlü ama canlı değil
            guven = 'medium'
        else:
            guven = 'low' if birlesik_durum == DATA_STATE_OFFLINE else 'medium'

        # En bayat bileşenin ÖLÇÜLEN yaşı (yoksa None — uydurulmaz)
        _yaslar = [y for y in (
            (p or {}).get('cache_age_seconds',
                          (p or {}).get('offline_record_age_seconds'))
            for p in (fuel_props, ox_props, combustion_data))
            if isinstance(y, (int, float)) and not isinstance(y, bool)]
        en_bayat_yas = round(float(max(_yaslar)), 1) if _yaslar else None

        results = {
            'fuel_properties': fuel_props,
            'oxidizer_properties': ox_props,
            'combustion_data': combustion_data,
            # ÖLÜ AĞ ÇAĞRISI SÖKÜLDÜ (2026-07-23 performans denetimi):
            # burada her toplu veri çekiminde SpaceX API'sine 30 saniye zaman
            # aşımlı bir istek atılıyordu. Sonuç motorda yalnız
            # self.flight_validation'a atanıyor ve HİÇBİR yerde okunmuyordu
            # (şablon, JS, sonuç sözlüğü — hiçbiri). Ölçüm: uç nokta HTTP 525
            # döndürüyor, sıvı motor taramasının %40'ını yiyor ve servis
            # yavaşladığında 30 saniyelik asılma riski taşıyor.
            # Anahtar KALDIRILMADI: sessizce yok olmak yerine durumu bildiriyor.
            'flight_validation': {'status': 'not_fetched', 'reason':
                                  'Uçuş telemetrisi hiçbir hesapta '
                                  'kullanılmıyordu; çağrı kaldırıldı. '
                                  'fetch_spacex_telemetry() elle çağrılabilir.'},
            'summary': {
                'combination': f"{fuel.upper()}/{oxidizer.upper()}",
                # 'data_freshness' ÇAĞRI zamanıdır, veri yaşı değil; veri
                # yaşı ayrı anahtarda (data_state) dürüstçe taşınır.
                'data_freshness': datetime.now().isoformat(),
                'data_state': birlesik_durum,
                'sources_used': ['NIST Webbook', 'NASA CEA'],
                'confidence': guven,
                # Hüküm HANGİ ÖLÇÜMLERDEN çıktı: okuyucu tek kelimeye
                # değil, arkasındaki iki girdiye bakabilsin.
                'confidence_basis': (
                    'all_sources_parsed=%s AND data_state=%s; a stale record '
                    'can never earn "high"' % (all_success, birlesik_durum)),
                'confidence_inputs': {
                    'all_sources_parsed': all_success,
                    'data_state': birlesik_durum,
                    'oldest_component_age_seconds': en_bayat_yas,
                },
            },
            'data_state': birlesik_durum,
        }

        if all_success:
            # Basarili bilesik sonucu kalici depoya yaz (cevrimdisi kullanim icin)
            offline_store.put(offline_key, results)
        elif combustion_data.get('status') == 'fallback':
            # Tum canli/cache/snapshot alt-katmanlar bos kaldi: bilesik anahtari dene
            stored = self._load_offline_store(offline_key)
            if stored is not None:
                return stored

        print(f"Comprehensive data collection complete")
        return results

# Global instance
web_api = WebPropellantAPI()

# Test function
def test_api():
    """Test the web API functionality"""
    print("Testing Web Propellant API...")
    
    # Test NIST data fetch
    lox_data = web_api.fetch_nist_data('lox')
    print(f"LOX data: {lox_data.get('density', 'N/A')} kg/m³")
    
    # Test NASA CEA fetch
    cea_data = web_api.fetch_nasa_cea_data('rp1', 'lox')
    print(f"RP1/LOX Isp: {cea_data.get('isp_vacuum', 'N/A')} s")
    
    # Test SpaceX data
    spacex_data = web_api.fetch_spacex_telemetry()
    print(f"SpaceX data: {list(spacex_data.keys())}")
    
    print("API testing complete")

if __name__ == "__main__":
    test_api()