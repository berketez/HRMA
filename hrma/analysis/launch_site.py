"""Fırlatma sahası çözümleyicisi: konum -> rakım -> atmosfer -> yerel yerçekimi.

Amaç
----
Kullanıcı Dünya üzerinde HERHANGİ bir noktayı fırlatma sahası olarak seçtiğinde
o noktanın (a) rakımını, (b) yüzey atmosfer koşullarını ve (c) yerel yerçekimi
ivmesini üretmek. Yeni bir fizik motoru DEĞİLDİR: mevcut USSA 1976 altyapısını
(hrma.constants) besleyen bir GİRDİ katmanıdır.

Kaynaklar (her sabit izlenebilir)
---------------------------------
* Atmosfer: U.S. Standard Atmosphere 1976 (NOAA/NASA/USAF), Tablo 4 —
  hrma.constants.ISA_LAYERS / isa_temperature() / isa_pressure() üzerinden.
  Bu modül ISA tablosunun KOPYASINI TUTMAZ, merkezden import eder.
* Yerçekimi: WGS84 normal yerçekimi. Somigliana kapalı formu ve elipsoid
  üstü irtifa düzeltmesi: NIMA TR8350.2, "Department of Defense World
  Geodetic System 1984", 3. baskı (1997/2000 düzeltmeli), Bölüm 4
  (Denklem 4-1 Somigliana, 4-3 irtifa açılımı).
* Rakım: ETOPO 2022 (NOAA NCEI, DOI 10.25921/fd45-gt74), 60 ark-saniye
  "ice surface" gridinden 5 ark-dakikaya indirgenmiş çevrimdışı kopya.
  Üretim: tools/build_launch_site_dem.py; köken: hrma/data/dem/SOURCE.md.
* Çevrimiçi zenginleştirme (opsiyonel, anahtarsız): Open-Meteo Elevation
  (Copernicus DEM GLO-90) ve Forecast (CC-BY 4.0). Attribution zorunlu;
  ATTRIBUTION_LINES sabiti UI'ya bu satırları taşır.

KRİTİK AYRIM — yerel g ve standart g0
-------------------------------------
Yerel yerçekimi (enleme + rakıma bağlı, ~%0.53 aralık) YALNIZCA ağırlık,
yörünge dinamiği ve itki/ağırlık oranına girer.

  I_sp = F / (mdot * g0)          -> g0 = 9.80665 SABİT (BIPM tanımı)
  ideal dV = I_sp * g0 * ln(MR)   -> g0 = 9.80665 SABİT
  W = m * g_yerel                 -> yerel g
  T/W = F / (m * g_yerel)         -> yerel g

Isp'yi yerel g ile tanımlamak klasik ve SESSİZ bir hatadır: aynı motor
ekvatorda ve kutupta farklı Isp veriyormuş gibi görünür. Bu modül Isp
zincirine ASLA g_yerel vermez; `standard_gravity()` her zaman G_0 döndürür
ve tests/test_launch_site.py bunu kilitler.

Modellenmeyenler (dürüst beyan — 'not_modelled')
------------------------------------------------
* Coriolis ivmesi ve Dünya dönüşünün taşıma hızı: 6-DOF çözücü düz-Dünya
  atalet çerçevesinde çalışır. `NOT_MODELLED` sözlüğünde beyan edilir.
* Yerel gravite anomalileri (Bouguer/izostatik): WGS84 elipsoid NORMAL
  yerçekimi kullanılır; gerçek g bundan tipik olarak birkaç on mGal
  (1 mGal = 1e-5 m/s^2) sapar — yani ~1e-4 m/s^2 mertebesi, roket
  performansı için ihmal edilebilir ama modellenmemiştir.
* Gerçek gün atmosferi (nem, cephe, mevsim): ISA standart gün varsayımı.
  Elle T/P override ya da çevrimiçi anlık hava ile kısmen giderilir.
"""

from __future__ import annotations

import gzip
import json
import math
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from hrma.constants import (
    G_0,
    M_AIR,
    R_STAR_ICAO,
    isa_pressure,
    isa_temperature,
)

# Kuru hava özgül gaz sabiti — trajectory_analysis ile BİREBİR aynı türetme
# (R*/M_air, ISO 2533). Ayrı bir sayı yazmak magic-number tutarsızlığı olurdu.
R_SPECIFIC_AIR = R_STAR_ICAO / M_AIR  # ≈ 287.05 J/(kg·K)
GAMMA_AIR = 1.4

# ---------------------------------------------------------------------------
# WGS84 elipsoid ve normal yerçekimi sabitleri
# Kaynak: NIMA TR8350.2, 3. baskı, Tablo 3.1 ve 3.4 (tanımlayıcı + türetilmiş)
# ---------------------------------------------------------------------------
WGS84_A = 6378137.0                 # m, büyük yarı eksen (tanımlayıcı)
WGS84_F = 1.0 / 298.257223563       # basıklık (tanımlayıcı)
WGS84_E2 = 6.69437999014e-3         # birinci dışmerkezlik karesi (türetilmiş)
WGS84_GAMMA_E = 9.7803253359        # m/s^2, ekvatorda normal yerçekimi
WGS84_GAMMA_P = 9.8321849378        # m/s^2, kutupta normal yerçekimi
WGS84_K = 0.00193185265241          # Somigliana sabiti (b*γp − a*γe)/(a*γe)
WGS84_M = 0.00344978650684          # m = ω²a²b/GM (TR8350.2, Bölüm 4)

# ---------------------------------------------------------------------------
# Çevrimdışı DEM
# ---------------------------------------------------------------------------
_DEM_DIR = Path(__file__).resolve().parents[1] / 'data' / 'dem'
_DEM_META_PATH = _DEM_DIR / 'etopo2022_5min_meta.json'

_dem_lock = threading.Lock()
_dem_cache: Optional[Dict] = None

# Attribution — lisans gereği KULLANICIYA GÖRÜNÜR olmalı (rapor §5.3).
ATTRIBUTION_LINES = {
    'dem_offline': 'Elevation: ETOPO 2022 (NOAA NCEI), doi:10.25921/fd45-gt74 — public domain',
    'dem_online': 'Elevation: Copernicus DEM GLO-90 via Open-Meteo (doi:10.5270/ESA-c5d3d65)',
    'weather_online': 'Weather data by Open-Meteo.com (CC-BY 4.0)',
    'geocoding_online': 'Geocoding by Open-Meteo.com (GeoNames, CC-BY 4.0)',
}

# Bilinçli olarak MODELLENMEYENLER. Bu sözlük API çıktısına konur ve
# arayüzde gösterilir; "sessizce yok sayıldı" durumu oluşmaz.
NOT_MODELLED = {
    'earth_rotation': (
        'Earth rotation transport velocity (up to 465.1*cos(lat) m/s eastward) '
        'is not coupled into the 6-DOF solver; flat-Earth launch-site inertial '
        'frame is used.'),
    'coriolis': (
        'Coriolis acceleration (2*Omega x v) is not integrated; affects impact '
        'point / range safety, not apogee or delta-v.'),
    'gravity_anomaly': (
        'Local gravity anomalies (Bouguer / isostatic) are not modelled; WGS84 '
        'ellipsoidal NORMAL gravity is used.'),
    'real_day_atmosphere': (
        'Humidity, fronts and seasonal profiles are not modelled; ISA standard '
        'day (optionally re-anchored to measured surface T/P).'),
}

# Dünya dönüş açısal hızı — yalnız BİLGİLENDİRME amaçlı doğu-atış hızı
# göstergesi için (fiziğe bağlanmaz, bkz. NOT_MODELLED['earth_rotation']).
# Kaynak: IERS Konvansiyonları 2010, ω_E = 7.292115e-5 rad/s.
OMEGA_EARTH = 7.292115e-5  # rad/s


# ---------------------------------------------------------------------------
# 1) Yerçekimi
# ---------------------------------------------------------------------------

def standard_gravity() -> float:
    """Isp ve ideal delta-v tanımlarında kullanılan STANDART yerçekimi.

    Her zaman 9.80665 m/s^2 döner (BIPM/ISO 80000-3). Enlem ya da rakım bu
    değeri DEĞİŞTİRMEZ — Isp bir motor özelliğidir, saha özelliği değil.
    """
    return G_0


def normal_gravity(latitude_deg: float) -> float:
    """WGS84 elipsoid yüzeyinde normal yerçekimi [m/s^2] (Somigliana).

        γ(φ) = γ_e * (1 + k*sin²φ) / sqrt(1 − e²*sin²φ)

    Kaynak: NIMA TR8350.2 Denklem 4-1. Uçlar: ekvator 9.7803253359,
    kutup 9.8321849378 (aralık ~%0.53).
    """
    phi = math.radians(_clamp_latitude(latitude_deg))
    s2 = math.sin(phi) ** 2
    return WGS84_GAMMA_E * (1.0 + WGS84_K * s2) / math.sqrt(1.0 - WGS84_E2 * s2)


def local_gravity(latitude_deg: float, altitude_m: float = 0.0) -> float:
    """Elipsoid üstünde h yüksekliğinde normal yerçekimi [m/s^2].

        g(φ,h) = γ(φ) * [1 − (2/a)(1 + f + m − 2f sin²φ) h + (3/a²) h²]

    Kaynak: NIMA TR8350.2 Denklem 4-3 (serbest-hava açılımı). Yüzeydeki
    gradyan ≈ −3.086e-6 m/s^2 per metre (−0.3086 mGal/m), literatürdeki
    standart serbest-hava gradyanıyla uyumludur.

    NOT: Bu YEREL g'dir. Isp/ideal-dV zincirine verilmez (bkz. modül
    başlığındaki KRİTİK AYRIM).
    """
    phi = math.radians(_clamp_latitude(latitude_deg))
    s2 = math.sin(phi) ** 2
    h = float(altitude_m)
    gamma = normal_gravity(latitude_deg)
    term = (1.0
            - (2.0 / WGS84_A) * (1.0 + WGS84_F + WGS84_M - 2.0 * WGS84_F * s2) * h
            + (3.0 / WGS84_A ** 2) * h * h)
    return gamma * term


def earth_rotation_speed(latitude_deg: float) -> float:
    """Enlemde Dünya yüzeyinin doğu yönlü taşıma hızı [m/s] — BİLGİLENDİRME.

        v = ω_E * R(φ) * cos(φ),  R(φ) = a / sqrt(1 − e² sin²φ)  (enine eğrilik)

    Ekvatorda ≈ 465.1 m/s. Doğuya atışta yörünge bütçesine katkı sağlar ama
    v1'de fiziğe BAĞLANMAZ (NOT_MODELLED['earth_rotation']).
    """
    phi = math.radians(_clamp_latitude(latitude_deg))
    r_n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * math.sin(phi) ** 2)
    return OMEGA_EARTH * r_n * math.cos(phi)


def _clamp_latitude(latitude_deg: float) -> float:
    return max(-90.0, min(90.0, float(latitude_deg)))


def normalize_longitude(longitude_deg: float) -> float:
    """Boylamı [-180, 180) aralığına sarar."""
    lon = float(longitude_deg)
    lon = (lon + 180.0) % 360.0 - 180.0
    return lon


# ---------------------------------------------------------------------------
# 2) Çevrimdışı DEM okuma (tembel)
# ---------------------------------------------------------------------------

def _load_dem() -> Optional[Dict]:
    """DEM'i ilk çağrıda belleğe açar (tembel). Dosya yoksa None döner.

    Uygulama açılışını yavaşlatmaması için modül import'unda DEĞİL, ilk
    rakım sorgusunda okunur. ~18.7 MB int16 (2160x4320) RAM.
    """
    global _dem_cache
    if _dem_cache is not None:
        return _dem_cache
    with _dem_lock:
        if _dem_cache is not None:
            return _dem_cache
        try:
            meta = json.loads(_DEM_META_PATH.read_text(encoding='utf-8'))
            bin_path = _DEM_DIR / meta['binary_file']
            with gzip.open(bin_path, 'rb') as fh:
                raw = fh.read()
            grid = np.frombuffer(raw, dtype='<i2')
            nlat, nlon = int(meta['nlat']), int(meta['nlon'])
            if grid.size != nlat * nlon:
                return None
            _dem_cache = {
                'grid': grid.reshape(nlat, nlon),
                'meta': meta,
                'nlat': nlat,
                'nlon': nlon,
                'lat0': float(meta['lat0_deg']),
                'lon0': float(meta['lon0_deg']),
                'dlat': float(meta['dlat_deg']),
                'dlon': float(meta['dlon_deg']),
            }
        except Exception:
            _dem_cache = None
            return None
    return _dem_cache


def dem_available() -> bool:
    """Çevrimdışı DEM yüklenebiliyor mu."""
    return _load_dem() is not None


def dem_metadata() -> Optional[Dict]:
    dem = _load_dem()
    return dict(dem['meta']) if dem else None


def dem_cell_size_km(latitude_deg: float = 0.0) -> float:
    """DEM hücresinin enlemdeki doğu-batı boyu [km] (ölçek göstergesi).

    Meridyen yayı: 1 derece ≈ π*a/180 (küresel yaklaşım, %0.5 içinde).
    """
    dem = _load_dem()
    dlat = dem['dlat'] if dem else 1.0 / 12.0
    deg_km = math.pi * WGS84_A / 180.0 / 1000.0
    return dlat * deg_km * max(math.cos(math.radians(_clamp_latitude(latitude_deg))), 0.05)


def dem_elevation(latitude_deg: float, longitude_deg: float) -> Optional[Dict]:
    """Çevrimdışı DEM'den bilinear interpolasyonla rakım [m].

    Döner: {'elevation_m', 'neighbour_min_m', 'neighbour_max_m',
            'cell_size_km', 'source'} ya da DEM yoksa None.

    'neighbour_min/max': ilgilenilen noktayı çevreleyen 3x3 grid hücresinin
    EN DÜŞÜK/EN YÜKSEK değeri. Bu bir hata modeli değil, ARAZİ ENGEBESİ
    ÖLÇÜSÜDÜR: düz sahada aralık dar, dağlık sahada geniştir. Kullanıcıya
    "gerçek saha rakımı bu bantta olabilir" uyarısı olarak sunulur.
    """
    dem = _load_dem()
    if dem is None:
        return None
    lat = _clamp_latitude(latitude_deg)
    lon = normalize_longitude(longitude_deg)

    # Kesirli grid indisleri (hücre MERKEZLERİ arasında interpolasyon)
    fy = (lat - dem['lat0']) / dem['dlat']
    fx = (lon - dem['lon0']) / dem['dlon']
    fy = min(max(fy, 0.0), dem['nlat'] - 1.0)      # kutup dışına taşma yok
    y0 = int(math.floor(fy))
    y1 = min(y0 + 1, dem['nlat'] - 1)
    ty = fy - y0
    x0 = int(math.floor(fx)) % dem['nlon']         # boylam periyodik
    x1 = (x0 + 1) % dem['nlon']
    tx = fx - math.floor(fx)

    g = dem['grid']
    v00 = float(g[y0, x0]); v01 = float(g[y0, x1])
    v10 = float(g[y1, x0]); v11 = float(g[y1, x1])
    top = v00 * (1.0 - tx) + v01 * tx
    bot = v10 * (1.0 - tx) + v11 * tx
    elev = top * (1.0 - ty) + bot * ty

    ys = [max(0, min(dem['nlat'] - 1, y0 + d)) for d in (-1, 0, 1, 2)]
    xs = [(x0 + d) % dem['nlon'] for d in (-1, 0, 1, 2)]
    patch = g[np.ix_(ys, xs)]
    return {
        'elevation_m': float(elev),
        'neighbour_min_m': float(patch.min()),
        'neighbour_max_m': float(patch.max()),
        'cell_size_km': dem_cell_size_km(lat),
        'source': 'dem_offline',
    }


# ---------------------------------------------------------------------------
# 3) Atmosfer (ISA tabanlı, opsiyonel yüzey T/P yeniden çapalama)
# ---------------------------------------------------------------------------

def atmosphere_at(altitude_m: float,
                  temperature_offset_k: float = 0.0,
                  pressure_ratio: float = 1.0) -> Dict[str, float]:
    """Verilen irtifada (T, P, rho, ses hızı).

    Taban: hrma.constants.isa_temperature/isa_pressure (USSA 1976).
    Standart-dışı gün: sıcaklık profili sabit ΔT ile kaydırılır ve basınç
    profili sabit bir oranla ölçeklenir (MIL-STD-210 / OpenRocket'ın
    "sıcak gün / soğuk gün" yaklaşımı). Bu bir YAKLAŞIMDIR: gerçek gün
    profili hidrostatik olarak yeniden entegre edilmez, lapse oranları
    standart kalır. Geçerlilik: yüzeye yakın birkaç km'de iyi, yüksek
    irtifada standart atmosfere yakınsar.
    """
    h = float(altitude_m)
    t = isa_temperature(h) + float(temperature_offset_k)
    t = max(t, 150.0)                       # negatif/absürt T koruması
    p = max(isa_pressure(h) * float(pressure_ratio), 1e-9)
    rho = p / (R_SPECIFIC_AIR * t)
    return {
        'temperature_k': float(t),
        'pressure_pa': float(p),
        'density_kg_m3': float(rho),
        'speed_of_sound_m_s': float(math.sqrt(GAMMA_AIR * R_SPECIFIC_AIR * t)),
    }


def isa_pressure_sensitivity_pa_per_m(altitude_m: float = 0.0) -> float:
    """|dP/dh| [Pa/m] — rakım hatasının basınç hatasına çevrilmesi için.

    Hidrostatik: dP/dh = −ρ·g. Deniz seviyesinde ≈ 12.0 Pa/m.
    """
    atm = atmosphere_at(altitude_m)
    return atm['density_kg_m3'] * G_0


# ---------------------------------------------------------------------------
# 4) Çevrimiçi zenginleştirme (opsiyonel, anahtarsız, kısa zaman aşımı)
# ---------------------------------------------------------------------------

ONLINE_TIMEOUT_S = 4.0
_ONLINE_UA = 'HRMA/2.6 (rocket motor analysis; offline-first launch site tool)'


def _http_json(url: str, timeout: float) -> Optional[dict]:
    """Kısa zaman aşımlı GET; her hata None döner (asla yükseltmez).

    Çevrimdışı-öncelik sözleşmesi: bu fonksiyon YALNIZCA use_online=True
    ile çağrılır ve başarısızlığı sessizce çevrimdışı yola düşürür.
    """
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={'User-Agent': _ONLINE_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None


def online_elevation(latitude_deg: float, longitude_deg: float,
                     timeout: float = ONLINE_TIMEOUT_S) -> Optional[float]:
    """Open-Meteo Elevation (Copernicus GLO-90, 90 m) — metre ya da None."""
    url = ('https://api.open-meteo.com/v1/elevation?latitude=%.6f&longitude=%.6f'
           % (_clamp_latitude(latitude_deg), normalize_longitude(longitude_deg)))
    data = _http_json(url, timeout)
    try:
        return float(data['elevation'][0])
    except Exception:
        return None


def online_surface_weather(latitude_deg: float, longitude_deg: float,
                           timeout: float = ONLINE_TIMEOUT_S) -> Optional[Dict]:
    """Open-Meteo Forecast anlık yüzey T/P/rüzgâr — CC-BY 4.0, attribution şart."""
    url = ('https://api.open-meteo.com/v1/forecast?latitude=%.6f&longitude=%.6f'
           '&current=temperature_2m,surface_pressure,wind_speed_10m,'
           'wind_direction_10m&wind_speed_unit=ms'
           % (_clamp_latitude(latitude_deg), normalize_longitude(longitude_deg)))
    data = _http_json(url, timeout)
    try:
        cur = data['current']
        return {
            'temperature_k': float(cur['temperature_2m']) + 273.15,
            'pressure_pa': float(cur['surface_pressure']) * 100.0,   # hPa -> Pa
            'wind_speed_m_s': float(cur.get('wind_speed_10m', 0.0)),
            'wind_direction_deg': float(cur.get('wind_direction_10m', 0.0)),
            'observed_at': str(cur.get('time', '')),
        }
    except Exception:
        return None


def online_geocode(query: str, count: int = 8,
                   timeout: float = ONLINE_TIMEOUT_S) -> list:
    """Open-Meteo Geocoding (GeoNames) — yer adı araması. Hata halinde []."""
    import urllib.parse
    if not query or not query.strip():
        return []
    url = ('https://geocoding-api.open-meteo.com/v1/search?name=%s&count=%d'
           % (urllib.parse.quote(query.strip()), max(1, min(int(count), 20))))
    data = _http_json(url, timeout)
    out = []
    try:
        for item in (data or {}).get('results') or []:
            out.append({
                'name': item.get('name'),
                'country': item.get('country'),
                'admin1': item.get('admin1'),
                'latitude': float(item['latitude']),
                'longitude': float(item['longitude']),
                'elevation_m': (float(item['elevation'])
                                if item.get('elevation') is not None else None),
            })
    except Exception:
        return out
    return out


# ---------------------------------------------------------------------------
# 5) Hazır saha kısayolları (KISIT DEĞİL — dünyanın her noktası seçilebilir)
# ---------------------------------------------------------------------------
# Koordinatlar kamuya açık, yayımlanmış pad/tesis konumlarıdır; 4 ondalık
# (~11 m) yuvarlanmıştır. 'approx' işaretli kayıtlar tesis değil, şehir/bölge
# referansıdır — sahanın kendisi değildir, kullanıcı ince ayar yapmalıdır.
LAUNCH_SITE_PRESETS = [
    {'id': 'ksc_lc39a', 'name': 'Kennedy Space Center LC-39A',
     'country': 'US', 'latitude': 28.6084, 'longitude': -80.6043, 'approx': False},
    {'id': 'ccsfs_slc40', 'name': 'Cape Canaveral SLC-40',
     'country': 'US', 'latitude': 28.5619, 'longitude': -80.5772, 'approx': False},
    {'id': 'vandenberg_slc4e', 'name': 'Vandenberg SLC-4E',
     'country': 'US', 'latitude': 34.6321, 'longitude': -120.6106, 'approx': False},
    {'id': 'wallops_0a', 'name': 'Wallops Flight Facility Pad 0A',
     'country': 'US', 'latitude': 37.8337, 'longitude': -75.4881, 'approx': False},
    {'id': 'kourou_ela3', 'name': 'Guiana Space Centre ELA-3 (Kourou)',
     'country': 'GF', 'latitude': 5.2390, 'longitude': -52.7683, 'approx': False},
    {'id': 'baikonur_1_5', 'name': 'Baikonur Site 1/5 (Gagarin Start)',
     'country': 'KZ', 'latitude': 45.9200, 'longitude': 63.3422, 'approx': False},
    {'id': 'esrange', 'name': 'Esrange Space Center (Kiruna)',
     'country': 'SE', 'latitude': 67.8931, 'longitude': 21.1043, 'approx': False},
    {'id': 'andoya', 'name': 'Andoya Space',
     'country': 'NO', 'latitude': 69.2941, 'longitude': 16.0208, 'approx': False},
    {'id': 'mahia_lc1', 'name': 'Rocket Lab LC-1 (Mahia)',
     'country': 'NZ', 'latitude': -39.2617, 'longitude': 177.8650, 'approx': False},
    {'id': 'tanegashima', 'name': 'Tanegashima Yoshinobu LP-1',
     'country': 'JP', 'latitude': 30.4000, 'longitude': 130.9700, 'approx': False},
    {'id': 'sriharikota', 'name': 'Satish Dhawan SC (Sriharikota)',
     'country': 'IN', 'latitude': 13.7330, 'longitude': 80.2350, 'approx': False},
    {'id': 'jiuquan_43', 'name': 'Jiuquan LC-43',
     'country': 'CN', 'latitude': 40.9583, 'longitude': 100.2917, 'approx': False},
    {'id': 'sinop_tr', 'name': 'Sinop (TR) — bolge referansi',
     'country': 'TR', 'latitude': 42.0231, 'longitude': 35.1531, 'approx': True},
    {'id': 'konya_tr', 'name': 'Konya (TR) — bolge referansi',
     'country': 'TR', 'latitude': 37.8746, 'longitude': 32.4932, 'approx': True},
]


# ---------------------------------------------------------------------------
# 6) Ana çözümleyici
# ---------------------------------------------------------------------------

def resolve_launch_site(latitude_deg: float,
                        longitude_deg: float,
                        elevation_m: Optional[float] = None,
                        temperature_k: Optional[float] = None,
                        pressure_pa: Optional[float] = None,
                        use_online: bool = False,
                        online_timeout: float = ONLINE_TIMEOUT_S) -> Dict:
    """Konumdan tam saha tanımı üretir.

    Args:
        latitude_deg / longitude_deg: ondalık derece (WGS84)
        elevation_m: kullanıcı elle rakım verdiyse (DEM'i ezer)
        temperature_k / pressure_pa: ölçülen yüzey değerleri (ISA'yı ezer)
        use_online: True ise Open-Meteo ile zenginleştirmeyi DENER; her hata
                    sessizce çevrimdışı yola düşer
    Döner: rakım, atmosfer, yerel g, kaynak etiketleri, belirsizlik, uyarılar.
    """
    lat = _clamp_latitude(latitude_deg)
    lon = normalize_longitude(longitude_deg)
    warnings: list = []
    attribution: list = []

    # ---- rakım ----
    elev_source = 'manual'
    neighbour_min = neighbour_max = None
    cell_km = dem_cell_size_km(lat)
    dem_hit = None
    if elevation_m is None:
        if use_online:
            online_elev = online_elevation(lat, lon, online_timeout)
            if online_elev is not None:
                elevation_m = online_elev
                elev_source = 'open_meteo_glo90'
                attribution.append(ATTRIBUTION_LINES['dem_online'])
        if elevation_m is None:
            dem_hit = dem_elevation(lat, lon)
            if dem_hit is not None:
                elevation_m = dem_hit['elevation_m']
                neighbour_min = dem_hit['neighbour_min_m']
                neighbour_max = dem_hit['neighbour_max_m']
                cell_km = dem_hit['cell_size_km']
                elev_source = 'dem_offline'
                attribution.append(ATTRIBUTION_LINES['dem_offline'])
            else:
                elevation_m = 0.0
                elev_source = 'not_available'
                warnings.append('dem_missing')
    if dem_hit is None and elev_source != 'dem_offline':
        # Elle/çevrimiçi rakımda da arazi engebesini gösterebilmek için
        # DEM komşuluğu (varsa) yine okunur — yalnızca BİLGİ amaçlı.
        probe = dem_elevation(lat, lon)
        if probe is not None:
            neighbour_min = probe['neighbour_min_m']
            neighbour_max = probe['neighbour_max_m']

    elevation_m = float(elevation_m)
    below_sea_level = elevation_m < 0.0
    if below_sea_level:
        # Okyanus hücresi ya da deniz seviyesi altı kara (Ölü Deniz, Hazar).
        # Fırlatma yüzeyi olarak 0 m alınır; ham değer ayrıca döndürülür.
        warnings.append('below_sea_level')
    site_elevation = max(elevation_m, 0.0)

    # ---- atmosfer ----
    atm_source = 'isa_1976'
    online_weather = None
    if use_online and (temperature_k is None or pressure_pa is None):
        online_weather = online_surface_weather(lat, lon, online_timeout)
        if online_weather:
            if temperature_k is None:
                temperature_k = online_weather['temperature_k']
            if pressure_pa is None:
                pressure_pa = online_weather['pressure_pa']
            atm_source = 'open_meteo_current'
            attribution.append(ATTRIBUTION_LINES['weather_online'])

    isa_t = isa_temperature(site_elevation)
    isa_p = isa_pressure(site_elevation)
    t_offset = (float(temperature_k) - isa_t) if temperature_k is not None else 0.0
    p_ratio = (float(pressure_pa) / isa_p) if pressure_pa is not None else 1.0
    if temperature_k is not None or pressure_pa is not None:
        if atm_source == 'isa_1976':
            atm_source = 'manual_override'
    surface = atmosphere_at(site_elevation, t_offset, p_ratio)

    # ---- yerçekimi ----
    g_local = local_gravity(lat, site_elevation)
    g_std = standard_gravity()

    # ---- belirsizlik görünürlüğü ----
    dpdh = isa_pressure_sensitivity_pa_per_m(site_elevation)
    relief_m = None
    elev_uncertainty = None
    if neighbour_min is not None and neighbour_max is not None:
        relief_m = float(neighbour_max - neighbour_min)
        # Yarı-aralık: gerçek saha rakımının komşuluk bandı içindeki konumu
        # bilinmediğinden, bandın yarısı görünür bir belirsizlik ÖLÇÜSÜ olarak
        # sunulur. Bu istatistiksel bir sigma DEĞİLDİR; arazi engebesinden
        # türetilmiş bir gösterge olarak etiketlenir.
        elev_uncertainty = relief_m / 2.0

    return {
        'latitude_deg': lat,
        'longitude_deg': lon,
        'elevation_m': site_elevation,
        'elevation_raw_m': elevation_m,
        'below_sea_level': below_sea_level,
        'elevation_source': elev_source,
        'elevation_uncertainty_m': elev_uncertainty,
        'elevation_uncertainty_kind': 'terrain_relief_half_range',
        'terrain_relief_m': relief_m,
        'terrain_relief_min_m': neighbour_min,
        'terrain_relief_max_m': neighbour_max,
        'dem_cell_size_km': cell_km,
        'pressure_sensitivity_pa_per_m': dpdh,
        'pressure_uncertainty_pa': (elev_uncertainty * dpdh
                                    if elev_uncertainty is not None else None),
        'atmosphere_source': atm_source,
        'temperature_k': surface['temperature_k'],
        'pressure_pa': surface['pressure_pa'],
        'density_kg_m3': surface['density_kg_m3'],
        'speed_of_sound_m_s': surface['speed_of_sound_m_s'],
        'isa_temperature_k': float(isa_t),
        'isa_pressure_pa': float(isa_p),
        'temperature_offset_k': float(t_offset),
        'pressure_ratio': float(p_ratio),
        'gravity_local_m_s2': g_local,
        'gravity_standard_m_s2': g_std,
        'gravity_delta_percent': (g_local - g_std) / g_std * 100.0,
        'earth_rotation_speed_m_s': earth_rotation_speed(lat),
        'online_used': bool(use_online and (
            elev_source == 'open_meteo_glo90' or atm_source == 'open_meteo_current')),
        'online_weather': online_weather,
        'attribution': attribution,
        'not_modelled': dict(NOT_MODELLED),
        'warnings': warnings,
    }


# ---------------------------------------------------------------------------
# 7) Yerel ENU yer değiştirmesi -> jeodezik koordinat (yörünge çizimi için)
# ---------------------------------------------------------------------------

def enu_to_geodetic(lat0_deg: float, lon0_deg: float, h0_m: float,
                    north_m, east_m, up_m):
    """Yerel düzlem (Kuzey/Doğu/Yukarı) yer değiştirmesini enlem/boylam/irtifaya çevirir.

    6-DOF çözücüsü konumu fırlatma noktasına çapalı, DÜZ-DÜNYA atalet
    çerçevesinde verir (x=Kuzey, y=Doğu, z=yukarı). Burada o yer
    değiştirme, yerel eğrilik yarıçaplarıyla jeodezik koordinata çevrilir:

        dφ = north / (M(φ0) + h0)          M: meridyen eğrilik yarıçapı
        dλ = east  / ((N(φ0) + h0)·cos φ0) N: enine (prime vertical) yarıçap

    M(φ) = a(1−e²)/(1−e² sin²φ)^{3/2},  N(φ) = a/(1−e² sin²φ)^{1/2}
    (Torge, "Geodesy", 3. baskı, §4.1; WGS84 parametreleri.)

    GEÇERLİLİK: birinci mertebe (teğet düzlem) yaklaşımı. Yer değiştirme
    ~100 km'ye kadar hata <%0.1 mertebesindedir; birkaç yüz km'nin ötesinde
    Dünya eğriliği ihmal edilemez ve bu dönüşüm sistematik olarak sapar.
    Bu, altındaki 6-DOF çözümünün de düz-Dünya varsayımının sınırıdır —
    dönüşüm çözümden DAHA doğru olamaz. Dünya dönüşü/Coriolis dahil
    değildir (NOT_MODELLED).
    """
    phi0 = math.radians(_clamp_latitude(lat0_deg))
    s2 = math.sin(phi0) ** 2
    w = math.sqrt(1.0 - WGS84_E2 * s2)
    m_rad = WGS84_A * (1.0 - WGS84_E2) / (w ** 3)      # meridyen
    n_rad = WGS84_A / w                                # enine
    north = np.asarray(north_m, dtype=float)
    east = np.asarray(east_m, dtype=float)
    up = np.asarray(up_m, dtype=float)

    dlat = north / (m_rad + float(h0_m))
    coslat = max(math.cos(phi0), 1e-9)                 # kutupta bölme koruması
    dlon = east / ((n_rad + float(h0_m)) * coslat)

    lat = np.degrees(phi0 + dlat)
    lon = np.degrees(math.radians(normalize_longitude(lon0_deg)) + dlon)
    lon = (lon + 180.0) % 360.0 - 180.0
    alt = float(h0_m) + up
    return lat, lon, alt
