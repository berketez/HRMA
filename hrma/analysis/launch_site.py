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
* Dünya dönüşünün TAŞIMA HIZI (frame carry-along, ekvatorda 465,1 m/s doğu):
  atalet fırlatma hızı bütçesine girer, modellenmez.
  `NOT_MODELLED['earth_rotation_transport_velocity']` ile beyan edilir.
  DİKKAT — Coriolis ivmesi bu maddeye DAHİL DEĞİLDİR: 6-DOF çözücü
  fırlatmaya çakılı DÖNEN teğet düzlemde çalışır ve serbest uçuşta
  −2·Ω×v terimini ENTEGRE EDER (`six_dof_trajectory._coriolis_acceleration`).
  Coriolis'in fiilen koştuğu koşullar `CORIOLIS_MODELLING` sözlüğündedir;
  enlem verilmeyen çağrıda çözücü Coriolis'i KENDİLİĞİNDEN KAPATIR ve
  `warn.sixdof.coriolis_disabled_no_latitude` uyarısını üretir.
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
    ISA_TABLE_TOP_M,
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
#
# ÖH D18 / termo-ucus a1 (P4B3-17) — ANAHTAR ADI GERÇEĞE UYDURULDU.
# ÖLÇÜLDÜ (``once.json`` K4, taban 9071a64): ``earth_rotation`` anahtarının
# METNİ "Coriolis acceleration (2*Omega x v) IS integrated" diyordu ve o
# metin ``/api/launch-site/resolve`` yanıtında ``not_modelled`` başlığı
# altında yayımlanıyordu. Aynı dosyanın modül belgesi ise "6-DOF çözücü
# düz-Dünya atalet çerçevesinde çalışır" diyordu: tek dosya, iki zıt beyan,
# ve tüketici için hüküm YANLIŞ olan (modellenmiyor) taraftaydı.
# Modellenmeyen şey Coriolis DEĞİL, Dünya dönüşünün TAŞIMA HIZIDIR; anahtar
# artık onu adlandırır. Fiilen modellenen kısım ayrı bir sözlükte
# (``CORIOLIS_MODELLING``) ve ``modelled`` başlığı altında yayımlanır —
# "modellenmeyenler" listesinde modellenen bir şey durmaz.
NOT_MODELLED = {
    'earth_rotation_transport_velocity': (
        "The Earth-rotation TRANSPORT velocity (up to 465.1*cos(lat) m/s "
        'eastward, the speed at which the launch site itself is carried) is '
        'NOT added to the vehicle state. It affects the inertial '
        'launch-velocity budget, not apogee or delta-v in the '
        'launch-anchored frame. Coriolis acceleration is a SEPARATE effect '
        'and IS modelled - see the "modelled" block, key '
        '"earth_rotation_coriolis".'),
    'gravity_anomaly': (
        'Local gravity anomalies (Bouguer / isostatic) are not modelled; WGS84 '
        'ellipsoidal NORMAL gravity is used.'),
    'real_day_atmosphere': (
        'Humidity, fronts and seasonal profiles are not modelled; ISA standard '
        'day (optionally re-anchored to measured surface T/P).'),
}

# Bilinçli olarak MODELLENENLER — bir etkinin "modellenmeyenler" listesinde
# durup metninde "modelleniyor" demesi (P4B3-17) bir daha olmasın diye
# beyanın İKİ tarafı da adlandırılmıştır. Bu sözlük ``resolve_launch_site``
# çıktısına ``modelled`` anahtarıyla konur.
#
# Her madde, etkiyi FİİLEN koşturan kodu adıyla gösterir ve hangi koşulda
# koşmadığını söyler: "modelleniyor" demek "her çağrıda açık" demek
# değildir; şart yazılmazsa beyan yine yalan olur.
CORIOLIS_MODELLING = {
    'earth_rotation_coriolis': (
        'The 6-DOF solver (six_dof_trajectory.SixDOFTrajectory) integrates '
        'the Coriolis acceleration a = -2*Omega x v_rel during FREE FLIGHT in '
        'a launch-anchored ROTATING tangent-plane frame, and the centrifugal '
        'term is folded into WGS84 normal gravity. CONDITION: it runs only '
        'when a launch latitude is supplied - without one the solver disables '
        'Coriolis and emits warn.sixdof.coriolis_disabled_no_latitude. The 2-D '
        'planar solver (trajectory_analysis) does NOT model Coriolis at all.'),
}

# Dünya dönüş açısal hızı. Burada enleme bağlı doğu-atış TAŞIMA hızı
# göstergesi (earth_rotation_speed) için kullanılır; taşıma hızı 6-DOF
# fiziğine bağlanmaz (bkz. NOT_MODELLED['earth_rotation_transport_velocity']).
# Coriolis ivmesi
# ise six_dof_trajectory.py'de AYNI değerle (yerel OMEGA_EARTH) modellenir.
# Kaynak: IERS Konvansiyonları 2010, ω_E = 7.292115e-5 rad/s.
OMEGA_EARTH = 7.292115e-5  # rad/s


# ---------------------------------------------------------------------------
# TANIM KÜMELERİ — sessiz kırpma yerine ret (ÖH D19 / P4B3-18 kalan ayak)
#
# ÖLÇÜLDÜ (taban 60cd341, once.json K18): ``local_gravity(200, 0)`` ve
# ``normal_gravity(200)`` istisna ATMADAN 9,832184937859008 m/s²
# (kutup değeri) döndürüyordu; ``earth_rotation_speed(200)``
# 2,857503442515346e-14 m/s (yani cos 90°) veriyordu. D18'de yalnız
# ``resolve_launch_site`` kapatılmıştı: kütüphaneyi doğrudan çağıran her yol
# (6-DOF ``g_surface``, düzlemsel yörünge, hibrit motorun saha bandı)
# sessiz kırpmayı görmeye devam ediyordu. Kırpılmış enlem, sorulan enlem
# DEĞİLDİR ve yerel g doğrudan enlemden çıkar.
#
# Aynı ölçümde rakım ayağı: ``local_gravity(45, 1e9)`` = 720.083,96 m/s²,
# ``resolve_launch_site(39,9, 32,85, elevation_m=1e9)`` HTTP 200 ile
# g = 719.745,08 m/s² ve ISA T = 186,946 K yayımlıyordu; ``elevation_m =
# -1e6`` ise sessizce 0,0'a çekiliyordu (yalnız 'below_sea_level' uyarısı,
# büyüklüğün imkânsızlığını söyleyen tek satır yok).
#
# Bantlar YENİ EŞİK İCAT ETMEZ:
#   * enlem: WGS84 ondalık derece tanım kümesi [-90, 90],
#   * saha rakımı: Dünya KATI YÜZEYİNİN kendi bandı; tek kaynak aşağıdaki
#     ``SITE_ELEVATION_RANGE_M`` (hibrit motorun saha bandı da bunu
#     kullanır — iki tanım yok),
#   * yerel g'nin rakımı: serbest-hava açılımı (NIMA TR8350.2 Denk. 4-3)
#     h/a'da KESİLMİŞ bir seridir; HRMA onu kendi atmosfer tablosunun
#     tavanıyla sınırlar (``hrma.constants.ISA_TABLE_TOP_M`` = 84.852 m;
#     orada karesel terim birimin 5,4e-7'si kadardır, 1e9 m'de ise
#     73.700 katıdır).
LATITUDE_RANGE_DEG = (-90.0, 90.0)

#: Fırlatma sahasının meşru rakım bandı [m]. Alt uç -500 m (Ölü Deniz
#: kıyısı -430 m'nin altında bir tampon değil, HRMA'nın kendi saha bandının
#: D14'ten beri kullandığı alt ucu), üst uç 9.000 m (Everest 8.848,86 m).
#: TEK KAYNAK: hibrit motorun ``LAUNCH_SITE_ELEVATION_RANGE_M``i bu adı
#: içe aktarır.
SITE_ELEVATION_RANGE_M = (-500.0, 9000.0)

#: ``local_gravity`` serbest-hava açılımının geçerli rakım bandı [m].
GRAVITY_ALTITUDE_RANGE_M = (SITE_ELEVATION_RANGE_M[0], ISA_TABLE_TOP_M)


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

    Bant dışı enlem KIRPILMAZ, ``LaunchSiteInputError`` ile reddedilir
    (ÖH D19 / P4B3-18): kırpılmış enlem başka bir sahadır.
    """
    phi = math.radians(_require_band(
        latitude_deg, 'latitude_deg', LATITUDE_RANGE_DEG, 'deg',
        'the WGS84 decimal-degree domain'))
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

    Enlem ve rakım bant dışıysa değer KIRPILMAZ, ``LaunchSiteInputError``
    ile reddedilir (ÖH D19 / P4B3-18). Rakım bandı serbest-hava
    açılımının kendi geçerlilik bandıdır
    (``GRAVITY_ALTITUDE_RANGE_M``): 1e9 m'de bu seri 720.083,96 m/s²
    gibi fiziksel olmayan bir sayı üretiyordu.
    """
    lat = _require_band(latitude_deg, 'latitude_deg', LATITUDE_RANGE_DEG,
                        'deg', 'the WGS84 decimal-degree domain')
    h = _require_band(altitude_m, 'altitude_m', GRAVITY_ALTITUDE_RANGE_M,
                      'm', 'the validity band of the free-air expansion '
                      '(NIMA TR8350.2 Eq. 4-3, truncated in h/a)')
    phi = math.radians(lat)
    s2 = math.sin(phi) ** 2
    gamma = normal_gravity(lat)
    term = (1.0
            - (2.0 / WGS84_A) * (1.0 + WGS84_F + WGS84_M - 2.0 * WGS84_F * s2) * h
            + (3.0 / WGS84_A ** 2) * h * h)
    return gamma * term


def earth_rotation_speed(latitude_deg: float) -> float:
    """Enlemde Dünya yüzeyinin doğu yönlü taşıma hızı [m/s] — BİLGİLENDİRME.

        v = ω_E * R(φ) * cos(φ),  R(φ) = a / sqrt(1 − e² sin²φ)  (enine eğrilik)

    Ekvatorda ≈ 465.1 m/s. Doğuya atışta yörünge bütçesine katkı sağlar ama
    v1'de fiziğe BAĞLANMAZ
    (NOT_MODELLED['earth_rotation_transport_velocity']). Coriolis İVMESİ ise
    ayrı bir etkidir ve 6-DOF'ta modellenir (CORIOLIS_MODELLING).

    Bant dışı enlem KIRPILMAZ, ``LaunchSiteInputError`` ile reddedilir
    (ÖH D19 / P4B3-18).
    """
    phi = math.radians(_require_band(
        latitude_deg, 'latitude_deg', LATITUDE_RANGE_DEG, 'deg',
        'the WGS84 decimal-degree domain'))
    r_n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * math.sin(phi) ** 2)
    return OMEGA_EARTH * r_n * math.cos(phi)


class LaunchSiteInputError(ValueError):
    """Saha girdisi TANIM KÜMESİNİN dışında — kırpma yerine ret.

    ÖH D18 / termo-ucus a1 (P4B3-18, kütüphane ayağı). Alan adı ve gerekçe
    makine-okurdur (``problems``); çağıran uç 500 değil 4xx üretebilsin
    diye ``ValueError`` türevidir (kardeşi
    :class:`hrma.analysis.trajectory_analysis.TrajectoryInputError`).
    """

    def __init__(self, message, problems=None):
        super().__init__(message)
        self.problems = problems or []


def _clamp_latitude(latitude_deg: float) -> float:
    return max(-90.0, min(90.0, float(latitude_deg)))


def _require_band(value, field: str, band, unit: str, what: str) -> float:
    """Bant dışı değeri KIRPMAZ, adıyla reddeder (ÖH D19 / P4B3-18).

    ``LaunchSiteInputError`` fırlatır; ``problems`` girdisi
    ``resolve_launch_site``ın enlem kapısıyla AYNI sözleşmedir
    (field / reason / value / accepted_range / unit), böylece uç katmanı
    tek bir gövde biçimi yayımlar.
    """
    try:
        sayi = float(value)
    except (TypeError, ValueError):
        raise LaunchSiteInputError(
            f'{field} must be a finite number (got {value!r}); no value was '
            'assumed.',
            problems=[{'field': field, 'reason': 'not_a_number',
                       'value': repr(value), 'accepted_range': list(band),
                       'unit': unit}])
    lo, hi = float(band[0]), float(band[1])
    if not (math.isfinite(sayi) and lo <= sayi <= hi):
        raise LaunchSiteInputError(
            f'{field} = {sayi:g} {unit} is outside {what} [{lo:g}, {hi:g}]; '
            'the value was NOT clamped and nothing was resolved (a clamped '
            'input is a different input, with a different answer).',
            problems=[{'field': field, 'reason': 'out_of_range',
                       'value': sayi, 'accepted_range': [lo, hi],
                       'unit': unit}])
    return sayi


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


def dem_cell_size_ns_km() -> float:
    """DEM hücresinin KUZEY-GÜNEY boyu [km] — enlemden bağımsız.

    ÖH D22 / P4B3-26: doğu-batı boyunun yanında kuzey-güney boyu da adıyla
    yayımlanır; ikisi yalnız kutup yakınında birbirinden ayrışır ve saha
    kartındaki "hücre ne kadar kaba" sorusunun tam cevabı bu ikilidir.
    """
    dem = _load_dem()
    dlat = dem['dlat'] if dem else 1.0 / 12.0
    return dlat * (math.pi * WGS84_A / 180.0 / 1000.0)


def dem_cell_size_km(latitude_deg: float = 0.0) -> float:
    """DEM hücresinin enlemdeki DOĞU-BATI boyu [km] (ölçek göstergesi).

    Paralel yayı: 1 derece boylam ≈ (π*a/180)*cos(φ) (küresel yaklaşım,
    %0.5 içinde). Meridyen yayı (kuzey-güney) için ``dem_cell_size_ns_km``.

    DÜZELTME (ÖH D22 / P4B3-26)
    ---------------------------
    Eski satır iki hata taşıyordu:
      1. Doğu-batı boyu için ENLEM adımı (``dlat``) kullanılıyordu; doğru
         adım BOYLAM adımıdır (``dlon``). Bugünkü DEM'de ikisi de 1/12°
         olduğu için sayısal fark YOKTU — kusur, DEM'in dlon'u değişince
         sessizce yanlış boy yayımlanmasıydı (kural #11).
      2. ``cos φ`` çarpanına 0,05 TABANI konmuştu. ÖLÇÜLDÜ (taban b84b10a,
         ``once.json`` P4B3-26): φ = 89,9° için 0,463831 km yayımlanıyordu,
         gerçek doğu-batı boyu 0,016191 km — 28,6 kat şişik. Taban, hücreyi
         olduğundan çok daha kaba göstererek arazi belirsizliğinin ölçek
         göstergesini bozuyordu. Meridyenler kutupta gerçekten birleşir;
         sıfıra giden değer fiziksel gerçektir, uydurma taban değil.
    """
    dem = _load_dem()
    dlon = dem['dlon'] if dem else 1.0 / 12.0
    deg_km = math.pi * WGS84_A / 180.0 / 1000.0
    return dlon * deg_km * math.cos(math.radians(
        _clamp_latitude(latitude_deg)))


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
        # P4B3-26: doğu-batı boyu enleme bağlıdır, kuzey-güney boyu değil;
        # ikisi adıyla ayrılır (eskiden tek sayı vardı ve o da yanlış adımı
        # kullanıyordu).
        'cell_size_ew_km': dem_cell_size_km(lat),
        'cell_size_ns_km': dem_cell_size_ns_km(),
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
#
# ÖH D23 / P4B3-27 — LİSTE HÂLÂ ÖLÜ (kalem KISMEN kapandı).
#
# ÖLÇÜLDÜ (taban ef527ae, ``once.json`` P4B3_27): 14 kayıtlık bu liste
# hrma/ ağacında HİÇBİR yerden okunmuyor (okuyucu sayısı 0); arayüz kendi
# ayrı 7 kayıtlık listesini taşıyor ve buradaki ``approx`` bayrağı ona hiç
# ulaşmıyor — 'Sinop (TR)' gerçek bir pad olan 'Kourou ELA-3' ile aynı
# biçimde listeleniyor.
#
# BU AŞAMADA KAPANAMADI, GEREKÇE ÖLÇÜLDÜ: listeyi bir uçtan yayımlamak
# denendi (``/api/launch-site/presets``) ve GERİ ALINDI — arayüzün onu
# tüketmesi gerekiyor, ``hrma/templates/launch_site.html`` ise bu dalgada
# KARDEŞ DALDA (dalga23/arayuz) değiştirildiği için buradan dokunulamıyor.
# Tüketicisiz uç, ``tests/test_d18_bekci_cevirisi_a1.py::
# TestP13B208UcPanelEnvanteri`` bekçisinin adıyla yasakladığı şeydir:
# "ürün yüzünün hiç çağırmadığı, yalnız testin tanımladığı uç". Yani
# çözüm uç+arayüz TEK PARÇADIR ve ARAYÜZ KULVARINA aittir.
#
# BU AŞAMADA KAPANAN: iki Türkçe kayıt adındaki betimleyici ek kaldırıldı
# ('... — bolge referansi' ASCII yazılmış Türkçeydi, kural #24 ihlali; üstelik
# listenin geri kalanı İngilizceydi). Aynı hüküm arayüz tarafında da
# verilmişti: betimleyici ek veri satırından çıkar, anlamı ``approx``
# bayrağı taşır.
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
    {'id': 'sinop_tr', 'name': 'Sinop (TR)',
     'country': 'TR', 'latitude': 42.0231, 'longitude': 35.1531, 'approx': True},
    {'id': 'konya_tr', 'name': 'Konya (TR)',
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
    # ÖH D18 / termo-ucus a1 (P4B3-18) — KIRPMA YERİNE RET (KÜTÜPHANE AYAĞI).
    #
    # ÖLÇÜLDÜ (``once.json`` K5, taban 9071a64):
    #   resolve_launch_site(200.0, 5000.0) -> HTTP yok, İSTİSNA YOK;
    #   latitude_deg = 90,0 / longitude_deg = -40,0 ve g = 9,832184937859008
    #   (kutup değeri) ile TAM bir saha dönüyordu; kırpmayı söyleyen tek alan
    #   yoktu. ``/api/launch-site/resolve`` ucu bu bandı D15'te (P7B1-08)
    #   kapattı, ama KAPI YALNIZ UÇTAYDI: kütüphaneyi doğrudan çağıran her
    #   yol (hibrit motorun saha çözümü, yörünge katmanı, betikler) sessiz
    #   kırpmayı görmeye devam ediyordu. Kırpılmış saha, sorulan saha
    #   DEĞİLDİR ve yerel g doğrudan enlemden çıkar.
    #
    # Boylam AYRI muamele görür: boylam 360° PERİYODİKTİR, sarma tam ve
    # tersinirdir (bilgi kaybı yok). Yine de sessiz kalmaz — sarma değeri
    # fiilen değiştirdiyse uyarı üretilir.
    _lat_ham = float(latitude_deg)
    if not (-90.0 <= _lat_ham <= 90.0):
        raise LaunchSiteInputError(
            f"latitude_deg = {_lat_ham:g} deg is outside the WGS84 "
            'decimal-degree domain [-90, 90]; the value was NOT clamped and '
            'no site was resolved (a clamped site is a different site, with '
            'a different local gravity).',
            problems=[{'field': 'latitude_deg', 'reason': 'out_of_range',
                       'value': _lat_ham, 'accepted_range': [-90.0, 90.0],
                       'unit': 'degree'}])
    lat = _lat_ham
    # ---- RAKIM BANDI (ÖH D19 / P4B3-18 kalan ayak) ----------------------
    # D15 (P7B1-08) enlem/boylam/sıcaklık/basınç kapılarını koydu ama
    # ``elevation_m`` bandını AÇIKÇA devretmişti. ÖLÇÜLDÜ (once.json K18,
    # taban 60cd341): elevation_m = 1e9 -> HTTP 200, g = 719.745,08 m/s²,
    # ISA T = 186,946 K, uyarı YOK; elevation_m = -1e6 -> sessizce 0,0'a
    # çekiliyor. Kullanıcının gönderdiği sayı yanıtta ya fiziksel olmayan
    # bir g üretiyor ya da hiç görünmüyordu.
    #
    # Bant, Dünya KATI YÜZEYİNİN kendi bandıdır (SITE_ELEVATION_RANGE_M,
    # tek kaynak). DEM/çevrimiçi kaynaktan gelen rakım zaten bu bandın
    # içindedir; kapı YALNIZ kullanıcının elle verdiği değere uygulanır.
    if elevation_m is not None:
        elevation_m = _require_band(
            elevation_m, 'elevation_m', SITE_ELEVATION_RANGE_M, 'm',
            "Earth's solid-surface elevation band")
    lon = normalize_longitude(longitude_deg)
    warnings: list = []
    attribution: list = []
    if abs(float(longitude_deg) - lon) > 1e-12:
        warnings.append(
            f'longitude_deg {float(longitude_deg):g} deg was wrapped to '
            f'{lon:g} deg on the 360 deg period; the point is the same '
            'meridian, but the value reported below is the wrapped one.')

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
        'dem_cell_size_ns_km': dem_cell_size_ns_km(),
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
        # P4B3-17: beyanın MODELLENEN tarafı da adıyla yayımlanır. Aksi
        # halde "listede yok" ile "modellenmiyor" karışır ve modellenen bir
        # etkiyi anlatan metin modellenmeyenler başlığı altında durur.
        'modelled': dict(CORIOLIS_MODELLING),
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
