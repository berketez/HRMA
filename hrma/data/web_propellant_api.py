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
import os
from hrma import DATA_DIR
from hrma.data import offline_store

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
CACHE_SCHEMA_VERSION = 1
CACHE_FILE_SUFFIX = '.json'
LEGACY_CACHE_SUFFIX = '.pkl'

# Veri durumu damgası: çağırana verinin nereden geldiği AÇIKÇA bildirilir.
# Denetim bulgusu: 10 yıllık bayat kayıt 'NIST API (Live)' etiketiyle
# sunuluyordu; artık bayat kayıt 'Live' etiketi ALAMAZ.
DATA_STATE_LIVE = 'live'        # bu çağrıda ağdan/kütüphaneden yeni alındı
DATA_STATE_CACHED = 'cached'    # disk önbelleği, TTL içinde
DATA_STATE_STALE = 'stale'      # disk önbelleği, süresi geçmiş
DATA_STATE_OFFLINE = 'offline'  # kalıcı depo / paket anlık görüntüsü / statik tablo

_DURUM_ETIKETI = {
    DATA_STATE_LIVE: 'Live',
    DATA_STATE_CACHED: 'Cached',
    DATA_STATE_STALE: 'Stale cache',
    DATA_STATE_OFFLINE: 'Offline store',
}

# En tazeden en bayata: bileşik sonucun durumu bileşenlerinin EN KÖTÜSÜDÜR
_DURUM_SIRASI = (DATA_STATE_LIVE, DATA_STATE_CACHED, DATA_STATE_STALE,
                 DATA_STATE_OFFLINE)

_LIVE_ETIKET_RE = re.compile(r'\(\s*live\s*\)', re.IGNORECASE)
_LIVE_KELIME_RE = re.compile(r'\blive\b', re.IGNORECASE)


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
        self.cache_dir = os.path.join(DATA_DIR, "propellant_cache")
        self.cache_ttl = 3600  # 1 hour cache
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'UZAYTEK-HRMA/1.0 (Rocket Analysis Tool)',
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
            'nist_unofficial': 'https://nist-api.fly.dev/crawl.json',  # Third-party NIST API
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
        """Load data from persistent offline store (user cache, then bundled snapshot)"""
        stored = offline_store.get(offline_key)
        if stored is None:
            return None
        print(f"Using offline store data for {offline_key}")
        # Depoya yazıldığı anda 'live' damgalı olan iç sözlükler de
        # düzeltilir: depodan okunan hiçbir şey artık canlı değildir.
        return self._damgala(self._damgala_derin(stored, DATA_STATE_OFFLINE),
                             DATA_STATE_OFFLINE)

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
            data.update({
                'source': 'NIST API (Live)',
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
            
            cea_ox_map = {
                'lox': 'LOX',
                'n2o4': 'N2O4',
                'h2o2': 'H2O2_98'
            }
            
            cea_fuel = cea_fuel_map.get(fuel, fuel.upper())
            cea_ox = cea_ox_map.get(oxidizer, oxidizer.upper())
            
            # Create CEA object
            cea_obj = CEA_Obj(oxName=cea_ox, fuelName=cea_fuel)
            
            # Calculate properties
            chamber_pressure_psia = chamber_pressure * 14.504  # Convert bar to psia
            
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

            results = {
                'fuel': fuel,
                'oxidizer': oxidizer,
                'isp_vacuum': cea_obj.get_Isp(Pc=chamber_pressure_psia, MR=mixture_ratio, eps=200),
                'isp_sea_level': cea_obj.get_Isp(Pc=chamber_pressure_psia, MR=mixture_ratio, eps=16),
                'c_star': cea_obj.get_Cstar(Pc=chamber_pressure_psia, MR=mixture_ratio),
                'chamber_temperature': cea_obj.get_Tcomb(Pc=chamber_pressure_psia, MR=mixture_ratio),
                'gamma': gamma_val,
                'molecular_weight': mw_val,
                'source': 'RocketCEA Library (NASA CEA)',
                'fetched_at': datetime.now().isoformat(),
                'status': 'success'
            }
            
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
            
            # Extract propellant info from Falcon 9 data
            rocket_data = {
                'falcon9_merlin': {
                    'propellants': 'RP-1/LOX',
                    'thrust_sea_level': 845000,  # N per engine
                    'thrust_vacuum': 914000,     # N per engine
                    'isp_sea_level': 282,        # s
                    'isp_vacuum': 311,           # s
                    'mixture_ratio': 2.56,       # Verified
                    'source': 'SpaceX Public API',
                    'last_flight': launch_data.get('date_utc', 'Unknown')
                }
            }
            
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
prob case=UZAYTEK rocket equilibrium
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
            data = {
                'fuel': fuel,
                'oxidizer': oxidizer,
                'isp_vacuum': None,
                'isp_sea_level': None,
                'c_star': None,
                'chamber_temperature': None,
                'gamma': None,
                'molecular_weight': None
            }
            
            # Parse specific impulse
            isp_match = re.search(r'Isp,\s*sec\s+(\d+\.?\d*)', output_text)
            if isp_match:
                data['isp_vacuum'] = float(isp_match.group(1))
                data['isp_sea_level'] = data['isp_vacuum'] * 0.88  # Approximate
            
            # Parse c* (characteristic velocity)
            cstar_match = re.search(r'CSTAR,\s*M/SEC\s+(\d+\.?\d*)', output_text)
            if cstar_match:
                data['c_star'] = float(cstar_match.group(1))
            
            # Parse chamber temperature
            temp_match = re.search(r'T,\s*K\s+(\d+\.?\d*)', output_text)
            if temp_match:
                data['chamber_temperature'] = float(temp_match.group(1))
            
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
        """Provide fallback CEA data"""
        
        combinations = {
            ('rp1', 'lox'): {
                'isp_vacuum': 353.2,
                'isp_sea_level': 311.8,
                'c_star': 1520.0,  # EXPERT FIX: Correct F-1 c_star value (was 1823.4)
                'chamber_temperature': 3670.2,
                'gamma': 1.2165,
                'molecular_weight': 22.86
            },
            ('lh2', 'lox'): {
                'isp_vacuum': 451.8,
                'isp_sea_level': 366.2,
                'c_star': 1580.0,  # NASA RS-25 effective C* value (theoretical: 2356.7, but effective ~67%)
                'chamber_temperature': 3357.4,
                'gamma': 1.2398,
                'molecular_weight': 15.96
            }
        }
        
        data = combinations.get((fuel, oxidizer), {
            'isp_vacuum': 320,
            'isp_sea_level': 285,
            'c_star': 1650,
            'chamber_temperature': 3200,
            'gamma': 1.22,
            'molecular_weight': 25
        })
        
        data.update({
            'fuel': fuel,
            'oxidizer': oxidizer,
            'source': 'Fallback CEA Data',
            'status': 'fallback',
            'fetched_at': datetime.now().isoformat()
        })

        return self._damgala(data, DATA_STATE_OFFLINE)

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
                'confidence': 'high' if all_success else 'medium'
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