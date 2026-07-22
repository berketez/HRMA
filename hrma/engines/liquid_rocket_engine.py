import copy
import time
import numpy as np
from scipy.optimize import fsolve, newton, minimize_scalar
from scipy.interpolate import interp1d, interp2d
import json
import warnings
import requests
from typing import Dict, List, Optional, Tuple

from hrma.constants import G_0, R_UNIVERSAL, PA_PER_BAR
warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Web yakıt verisi süreç içi memo'su (v2.5.5 performans).
#
# web_api.get_comprehensive_data pickle önbelleğine rağmen HER motor
# örneğinde en az bir CANLI ağ isteği yapıyor (SpaceX telemetri isteği
# başarısız olunca stale-if-error yoluna düşüyor ama isteğin kendisi her
# seferinde atılıyor: ölçüm ~0.7 s/koşu; ağ yokken 30 s zaman aşımı).
# Aynı (yakıt, oksitleyici, Pc, MR) için sonuç, web_api'nin KENDİ TTL'i
# (cache_ttl = 1 saat) boyunca süreç içinde saklanır — tazelik sözleşmesi
# pickle katmanıyla AYNI kalır, yalnız başarısız isteğin her koşuda
# tekrarı önlenir. Değerler derin kopyayla girer/çıkar (mutasyon izole).
# ---------------------------------------------------------------------------
_WEB_DATA_MEMO = {}
_WEB_DATA_MEMO_MAX = 8

# ---------------------------------------------------------------------------
# TASARIM SABİTLERİ (2026-07-19 uydurma denetimi)
# Kural: bir sayı birden fazla yerde kullanılıyorsa BURADA bir kez tanımlanır
# ve kaynağı yorumda belirtilir. Fonksiyon gövdesinde çıplak sayı bırakılmaz.
# ---------------------------------------------------------------------------

# Karakteristik uzunluk L* [m]: LOX/hidrokarbon için tipik 1.02-1.27 m
# (Sutton & Biblarz, "Rocket Propulsion Elements" 9th ed., Table 8-1).
L_STAR_DEFAULT_M = 1.2
L_STAR_MIN_M, L_STAR_MAX_M = 0.3, 5.0

# Hazne/boğaz çap oranı (varsayılan): d_c/d_t = 3.5 -> daralma oranı 12.25.
CHAMBER_THROAT_DIAMETER_RATIO_DEFAULT = 3.5
CHAMBER_DIAMETER_MIN_M = 0.05
CONTRACTION_RATIO_MIN, CONTRACTION_RATIO_MAX = 1.5, 60.0

# Rejeneratif soğutma kanalları (varsayılan kesit; Huzel & Huang Ch. 4 tipik
# 1-3 mm kanal). Kanal sayısı varsayılanı GEOMETRİDEN hesaplanır:
# n = floor(pi * D_hazne / (w + land)) — sabit 80/180 değil.
COOLING_CHANNEL_WIDTH_DEFAULT_M = 3.0e-3
COOLING_CHANNEL_HEIGHT_DEFAULT_M = 2.0e-3
# Kanal yüksekliği (derinliği) tasarım serbestliğidir (formda girdisi yok):
# hız hedefi aşılırsa yükseklik hedefe göre BÜYÜTÜLÜR ve etiketlenir.
# Hedef hız 40 m/s: yüksek basınçlı motor rejeneratif tasarım bandı
# 30-60 m/s ortası (Huzel & Huang Ch. 4; NASA SP-8087 "Liquid Rocket
# Engine Fluid-Cooled Combustion Chambers" tasarım pratiği).
COOLANT_CHANNEL_TARGET_VELOCITY_MS = 40.0
# Frezeli kanal pratik derinlik üst sınırı (Huzel & Huang Ch. 4).
COOLING_CHANNEL_HEIGHT_MAX_M = 10.0e-3
COOLING_CHANNEL_LAND_DEFAULT_M = 1.5e-3      # kanallar arası kaburga kalınlığı
COOLING_CHANNEL_COUNT_MIN, COOLING_CHANNEL_COUNT_MAX = 4, 2000
# İşlenmiş kanal yüzeyi mutlak pürüzlülüğü [m] (Ra 3.2 um, form varsayılanı).
COOLING_CHANNEL_ROUGHNESS_DEFAULT_M = 3.2e-6
COOLANT_FLOW_FRACTION_DEFAULT = 1.0          # yakıtın tamamı soğutucu
COOLANT_INLET_TEMP_DEFAULT_K = 300.0

# Soğutma tipine göre varsayılan sıcak cidar sıcaklıkları [K]
# (kullanıcı max_wall_temp verirse o kullanılır).
WALL_TEMP_DEFAULT_K = {'regenerative': 800.0, 'film_cooling': 900.0,
                       'dump_cooling': 850.0, 'ablative': 1200.0,
                       'radiative': 1800.0}
WALL_TEMP_COLD_DEFAULT_K = {'regenerative': 350.0, 'film_cooling': 400.0,
                            'dump_cooling': 380.0, 'ablative': 500.0}

# Performans haritası tarama çözünürlükleri (maliyet/çözünürlük dengesi).
PERF_MAP_MR_POINTS = 13
PERF_MAP_PC_POINTS = 11
PERF_MAP_ALT_POINTS = 13
PERF_MAP_MR_SPAN = 0.45          # optimum O/F etrafında +-%45 tarama
# Üst sınır 300 -> 500 bar (2026-07-22 Raptor entegrasyonu): yanma verisi
# artık cea_bridge ile GERÇEK Pc'de çözüldüğünden 300 bar kırpması kalktı.
# 300 bar üzerinde cea_bridge real_gas_warning bayrağı kullanıcıya gösterilir
# (CEA ideal-gaz çözümü; fugasite/gerçek-gaz düzeltmesi yok).
PERF_MAP_PC_MIN_BAR, PERF_MAP_PC_MAX_BAR = 20.0, 500.0
PERF_MAP_ALT_MAX_M = 100000.0

# Vakum Isp referans alan oranı: statik tablo "Area ratio 200:1" çapasıyla
# aynı sözleşme (bkz. tablo yorumları). CEA canlı çağrısı da vakum
# referansını bu eps'te üretir ki tablo/CEA kaynakları karşılaştırılabilir
# kalsın (uçmuş üst kademe lüleleri ~200-300; Sutton & Biblarz 9th ed. Ch. 3).
VACUUM_REFERENCE_EPS = 200.0

# Kriyojenik soğutucu giriş sıcaklığı varsayılanları [K] — kullanıcı
# coolant_inlet_temp girmediyse kullanılır ve etiketlenir. Değerler NBP
# (NIST WebBook: CH4 111.7 K, para-H2 20.3 K) + pompa ısınma payıdır.
CRYO_COOLANT_INLET_DEFAULT_K = {'methane': 115.0, 'lh2': 25.0}

# Süperkritik istasyon-marşlı soğutma çözümü için kanal giriş basıncı
# tahmini: P_giris ~ 1.5 x Pc (rejeneratif ceket pompa çıkışı ile enjektör
# arasındadır; staged/FFSC zincirinde pompa çıkışı 1.5-2.5 x Pc mertebesine
# çıkar — Sutton 9th ed. Ch. 6 çevrim şemaları). ETİKETLİ varsayımdır;
# kanal ΔP sonucu pompa zincirine ayrıca işlenir.
REGEN_CHANNEL_INLET_PRESSURE_FACTOR = 1.5

# Enjektör tipi -> ΔP/Pc oranı (NASA SP-8089 chug kılavuzu bandı içinde
# tip bazlı seçim; calculate_injector_design ve çevrim çözücüsü AYNI
# tabloyu kullanır — tek tanım yeri).
INJECTOR_TYPE_DP_FRACTION = {
    'impinging': 0.22,    # flight-proven impinging
    'coaxial': 0.18,      # coax shear (düşük ΔP)
    'showerhead': 0.28,   # atomizasyon için yüksek ΔP
    'pintle': 0.15,       # düşük ΔP (kısılabilir)
}
INJECTOR_TYPE_DP_FRACTION_DEFAULT = 0.20

# Sıvı enjektörde chug (düşük frekans) kararlılık alt sınırı ΔP/Pc
# (NASA SP-8089 "Liquid Rocket Engine Injectors": %15-20 bandı).
CHUG_DP_PC_MIN_LIQUID = 0.15
CHUG_DP_PC_RECOMMENDED_LIQUID = 0.20

# İlk enine (tanjansiyel) akustik mod katsayısı: f_1T = alpha * a / (pi * D_c),
# alpha = 1.8412 (J1' Bessel türevinin ilk sıfırı; Harrje & Reardon,
# NASA SP-194 "Liquid Propellant Rocket Combustion Instability").
FIRST_TANGENTIAL_MODE_COEFF = 1.8412

# Kısma (throttle) taraması: %40-100 itki bandı (denetim raporu madde 8).
THROTTLE_SCAN_FRACTIONS = (0.40, 0.55, 0.70, 0.85, 1.00)

# Film soğutma girdi bandı (% yakıt debisi). Tarihsel film debileri ana
# debinin %1-10'u mertebesindedir (Huzel & Huang Ch. 4); üst sınır geniş
# bırakılır, aşırı değer uyarı üretir.
FILM_COOLING_PCT_MAX = 30.0

# Motor arayüz çevrim adı -> cycle_power_balance çözücü adı eşlemesi.
CYCLE_SOLVER_NAME = {
    'pressure_fed': 'pressure_fed',
    'gas_generator': 'gas_generator',
    'tap_off': 'tap_off',
    'staged_combustion': 'staged_combustion',
    'expander': 'expander',
    'full_flow_staged': 'full_flow_staged_combustion',
}

# Rejeneratif ceket liner (sıcak cidar) kalınlığı [m] — 1B istasyon-marşlı
# süperkritik çözüm için. Frezeli kanallı bakır/inconel liner pratiği
# 0.5-2 mm (Huzel & Huang, "Modern Engineering for Design of
# Liquid-Propellant Rocket Engines", Ch. 4). Yapısal dış cidar ayrıdır.
REGEN_LINER_THICKNESS_M = 1.0e-3

# Rejeneratif ceketin kapladığı azami genişleme oranı: ana yanma odası
# ceketi tipik olarak ε≈5-6'ya kadar frezeli kanallıdır (RS-25 ana yanma
# odası ε≈5-6, ötesi tüp demeti/ışınımsal bölge — Sutton & Biblarz 9th ed.
# Ch. 8 rejeneratif ceket anlatımı). Lüle bunun ötesine uzuyorsa o bölgenin
# soğutması bu modelde ÇÖZÜLMEZ ve çıktıda açıkça söylenir.
REGEN_JACKET_EPS_MAX = 6.0

# Film soğutmada film sıvısının ısı alabileceği üst sıcaklık, sıcak cidar
# hedef sıcaklığıyla sınırlanır (film cidarı korurken cidar hedefinden
# sıcak olamaz). Enerji dengesi modeli: Huzel & Huang Ch. 4 (film debisi =
# yutulan ısı / birim kütle ısı kapasitesi); entalpiler CoolProp gerçek-gaz
# değerleridir (CH4/H2), RP-1 için duyulur ısı (cp·ΔT) alt sınırıdır.
FILM_COOLANT_CP_FALLBACK_J_KGK = {'rp1': 2090.0}  # MIL-DTL-25576 sıvı cp

# CoolProp akışkan adları (film/pressurant entalpi hesapları için).
COOLPROP_FLUID_NAME = {'methane': 'Methane', 'lh2': 'ParaHydrogen',
                       'lox': 'Oxygen'}

# Yanma süresi [s]: kullanıcı max_burn_duration vermezse VARSAYIM olarak
# kullanılır ve çıktıda 'burn_time_source' ile etiketlenir.
BURN_TIME_DEFAULT_S = 300.0
BURN_TIME_MIN_S, BURN_TIME_MAX_S = 0.1, 100000.0

# Besleme hattı: Darcy-Weisbach + yerel kayıp katsayıları.
# K değerleri: Crane TP-410 / White "Fluid Mechanics" 7th ed. Table 6.5.
FEED_LINE_LENGTH_DEFAULT_M = 2.5     # hat uzunluğu (feed_system ile aynı değer)
FEED_LINE_ROUGHNESS_M = 4.5e-5       # ticari çelik boru (White Table 6.1)
FEED_K_TANK_OUTLET = 0.50            # keskin kenarlı tank çıkışı
FEED_K_MAIN_VALVE = 0.15             # tam açık küresel/kelebek ana vana
FEED_K_FILTER = 10.0                 # hat süzgeci (temiz eleman, tahmin)
FEED_K_ELBOW = 0.30                  # 90 derece uzun yarıçaplı dirsek
FEED_ELBOW_COUNT = 4
FEED_LINE_TARGET_VELOCITY_MS = 5.0   # hat çapı boyutlandırma hedefi (3-8 m/s)

# Turbopompa benzerlik modeli (Huzel & Huang, "Modern Engineering for Design
# of Liquid-Propellant Rocket Engines", Ch. 6; Stepanoff, "Centrifugal and
# Axial Flow Pumps" 2nd ed.).
PUMP_SUCTION_SPECIFIC_SPEED = 8.0    # boyutsuz w_ss, indüserli roket pompası
PUMP_BLADE_COUNT = 6                 # çark kanat sayısı (tipik 5-8)
PUMP_BLADE_EXIT_ANGLE_DEG = 25.0     # geriye eğik kanat çıkış açısı
PUMP_HYDRAULIC_EFFICIENCY = 0.88     # hidrolik verim (Euler head -> gerçek)
PUMP_EFFICIENCY_DEFAULT = 0.75       # toplam pompa verimi (BEP)
PUMP_EXIT_WIDTH_RATIO = 0.06         # b2/D2 çark çıkış genişlik oranı
PUMP_NPSH_VAPOR_PRESSURE_BAR = 1.01325  # depolama doyma basıncı varsayımı (NBP)
# Pratik mil hızı tavanı [rpm]: emme özgül hızı tek başına küçük debilerde
# fiziksel olmayan devirler verir; roket turbopompaları ~1.2e5 rpm altındadır
# (Huzel & Huang Ch. 6 tablo aralığı). Tavan uygulanırsa kullanıcı uyarılır.
PUMP_MAX_SPEED_RPM = 120000.0
PUMP_TANK_PRESSURE_DEFAULT_BAR = 3.0    # turbopompa beslemesi NPSH tankı
PUMP_CURVE_FLOW_MIN, PUMP_CURVE_FLOW_MAX = 0.5, 1.5  # Q/Q_bep tarama bandı
PUMP_CURVE_POINTS = 20
TURBINE_VELOCITY_RATIO = 0.45        # U/C0, tek kademeli impuls türbin optimumu
# Tek kademeli türbin kanat uç hızı pratik sınırı [m/s] (malzeme gerilmesi;
# Huzel & Huang Ch. 6). Aşılırsa kullanıcı uyarılır (çok kademe gerekir).
TURBINE_TIP_SPEED_LIMIT_MS = 500.0
TURBINE_EFFICIENCY_DEFAULT = 0.65
TURBINE_PRESSURE_RATIO_DEFAULT = 8.5
TURBINE_GAS_CP_J_KGK = 2000.0        # yakıtça zengin GG gazı cp (tahmin)
TURBINE_GAS_GAMMA = 1.30
GAS_GENERATOR_TEMP_DEFAULT_K = 1200.0
GAS_GENERATOR_FLOW_FRACTION = 0.05   # ana debinin %5'i
GAS_GENERATOR_PRESSURE_RATIO = 1.3   # GG oda basıncı / ana oda basıncı

# Yapısal analiz
SAFETY_FACTOR_DEFAULT = 2.5          # form varsayılanı ile aynı
SAFETY_FACTOR_MIN, SAFETY_FACTOR_MAX = 1.1, 10.0
CHAMBER_MATERIAL_DEFAULT = 'inconel_718'
WALL_THICKNESS_MIN_M = 0.002         # imalat alt sınırı (2 mm)
PROOF_PRESSURE_FACTOR = 1.5          # kanıt basıncı / işletme basıncı
BURST_PRESSURE_FACTOR = 2.5          # patlama basıncı / işletme basıncı
THERMAL_CYCLES_DEFAULT = 500
# Standart plaka/sac kalınlıkları [mm] — gerekli kalınlık bir üst standarda
# yuvarlanır; böylece gerilme marjı tanım gereği 0 olmaktan çıkar.
STANDARD_WALL_THICKNESS_MM = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0,
                              10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0,
                              60.0, 80.0, 100.0, 125.0, 150.0)

# Form malzeme seçimi -> hrma.data.materials_db kanonik anahtarı.
CHAMBER_MATERIAL_MAP = {
    'steel_304': 'ss_304', 'steel_316': 'ss_316',
    'inconel_718': 'inconel_718', 'inconel_625': 'inconel_625',
    'aluminum_6061': 'aluminum_6061', 'copper_c101': 'copper',
    'cucrzr': 'cucrzr', 'steel_4130': 'steel_4130',
}

# Nozul tipi geometrisi. length_fraction: 15 derece konik nozul uzunluğuna
# oranla kontur uzunluğu (Rao %80 / %60 bell). exit_angle: bell çıkış açısı,
# divergence verimi lambda = (1 + cos(theta))/2 (Sutton & Biblarz 9th ed.,
# Eq. 3-34 ve Fig. 3-14) — nozzle_design._divergence_efficiency ile aynı form.
NOZZLE_TYPE_GEOMETRY = {
    'conical':   {'half_angle': 15.0, 'exit_angle': 15.0, 'length_fraction': 1.00,
                  'modelled': True},
    'bell_80':   {'half_angle': 30.0, 'exit_angle': 8.5,  'length_fraction': 0.80,
                  'modelled': True},
    'bell_60':   {'half_angle': 34.0, 'exit_angle': 12.0, 'length_fraction': 0.60,
                  'modelled': True},
    # Aerospike / dual-bell konturu bu sürümde MODELLENMİYOR: değerler bell_80
    # ile aynıdır ve çıktıda 'nozzle_contour_modelled': False ile işaretlenir.
    'aerospike': {'half_angle': 30.0, 'exit_angle': 8.5,  'length_fraction': 0.80,
                  'modelled': False},
    'dual_bell': {'half_angle': 30.0, 'exit_angle': 8.5,  'length_fraction': 0.80,
                  'modelled': False},
}
NOZZLE_TYPE_DEFAULT = 'bell_80'
# Yakınsak (daralan) koni yarı açısı. TEK TANIM YERİ (CLAUDE.md kural 11):
# hem soğutma entegrasyonundaki yakınsak uzunluk hem de sonuç sözlüğündeki
# 'convergent_half_angle_deg' bu değeri kullanır; ikisi ayrı sabitken
# birbirinden habersiz kayabiliyordu. 30 derece sıvı motorlarda standart
# daralma açısıdır (Huzel & Huang, "Modern Engineering for Design of
# Liquid-Propellant Rocket Engines", Böl. 4; Sutton & Biblarz 9th ed. Böl. 3).
CONVERGENT_HALF_ANGLE_DEG = 30.0
# Tank boyutlandırma — TEK model (bkz. _size_tank). Besleme sistemi kartı ve
# ayrıntılı tank tasarımı aynı iki sabiti kullanır; ayrı ayrı gömülüyken
# (1.20 çarpanı vs 1.15 rezerv + %5 ullage) aynı koşuda iki farklı tank
# hacmi raporlanıyordu. Rezerv payı: yüklenen itici / tüketilen itici;
# ullage: tankın sıvı DOLMAYAN hacim kesri (Huzel & Huang, Böl. 8).
TANK_PROPELLANT_RESERVE_FACTOR = 1.15
TANK_ULLAGE_FRACTION = 0.05
# 'Uzay optimize' (vakum) lüle: mevcut genişleme oranının katı ve tavanı.
EXPANSION_RATIO_VACUUM_FACTOR = 2.5
EXPANSION_RATIO_VACUUM_CAP = 300.0
# Pratik genişleme oranı üst sınırı — 'sonlu lüle' kaybının referansı
# (uçmuş üst kademe lüleleri ~200-300; 500 pratik tavan olarak alınır).
EXPANSION_RATIO_PRACTICAL_MAX = 500.0

# Kütle hesabı ekleri
CHAMBER_MASS_JOINT_FACTOR = 1.20      # flanş/bağlantı/takviye payı
INJECTOR_PLATE_THICKNESS_RATIO = 1.5  # enjektör plakası / hazne cidarı
NOZZLE_WALL_THICKNESS_RATIO = 0.60    # lüle cidarı / hazne cidarı (düşük basınç)
# Turbopompa kütlesi: güçle ölçeklenen ampirik korelasyon (Huzel & Huang Ch. 6
# kütle-güç eğilimi). ETİKETLİ tahmindir, geometriden türetilmemiştir.
TURBOPUMP_MASS_PER_KW = 0.20          # kg/kW
TURBOPUMP_MASS_BASE_KG = 8.0
FEED_LINE_MASS_PER_KG_S = 2.5         # kg (hat+vana) / (kg/s) debi
CONTROLS_MASS_BASE_KG = 15.0

# Enjeksiyon/soğutma tutarlılık uyarı eşikleri (bağıl fark)
INPUT_CONSISTENCY_TOLERANCE = 0.20
# Soğutma kanalı pratik sınırları (aşılırsa uyarı; hesap yine yapılır).
COOLANT_VELOCITY_LIMIT_MS = 100.0        # kanal içi hız üst sınırı
COOLANT_DP_FRACTION_LIMIT = 0.30         # soğutucu ΔP / Pc üst sınırı
# Akış ayrılması ölçütü (Summerfield): P_e < SEPARATION_RATIO · P_a olduğunda
# aşırı genişlemiş lülede sınır tabaka ayrılır ve ideal CF kaybı abartır.
NOZZLE_SEPARATION_PRESSURE_RATIO = 0.40


class LiquidRocketEngine:
    """Liquid bipropellant rocket engine analysis module"""
    
    def __init__(self, thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
                 fuel_type='rp1', oxidizer_type='lox', cooling_type='regenerative',
                 injector_type='impinging', feed_system_type='turbopump',
                 propellant_data=None, overrides=None):

        # Formdan gelen ham girdi sözlüğü (2026-07-19 denetimi, kritik bulgu 1).
        # Katı motordaki desenin aynısı: aralık doğrulamalı _override_val ile
        # okunur, aralık dışı/boş değer SESSİZCE yutulmaz — design_warnings'e
        # yazılır ve sonuç sözlüğünde 'input_warnings' olarak döner.
        self.overrides = dict(overrides or {})
        self.design_warnings = []

        # Performance parameters
        self.F = thrust  # N
        self.P_c = chamber_pressure  # bar
        self.MR = mixture_ratio  # O/F ratio

        # Propellant combination
        self.fuel_type = fuel_type
        self.oxidizer_type = oxidizer_type

        # Engine configuration
        self.cooling_type = cooling_type
        self.injector_type = injector_type
        self.feed_system_type = feed_system_type

        # Web-enhanced propellant database — TEMBEL yükleme (v2.5.0, Berke
        # onaylı karar 6): kurucu ASLA ağa çıkmaz. Eski davranış kurucuda canlı
        # HTTP çağrısıydı (0.66 s/istek + 30 s timeout riski). Veri artık:
        #   1) propellant_data parametresiyle enjekte edilir (UQ/MC örnekleri,
        #      testler — örnek başına HTTP kesinlikle yasak), YA DA
        #   2) İLK ihtiyaçta (web_propellant_data property erişimi) BİR KEZ,
        #      web_propellant_api'nin çevrimdışı-öncelikli zinciriyle çekilir
        #      (canlı -> taze pickle cache -> bayat cache -> kalıcı çevrimdışı
        #      depo/bundled snapshot; v2.4.6). Aynı veri, farklı zaman: sonuç
        #      değerleri değişmez.
        self.web_combustion_data = {}
        self.flight_validation = {}
        if propellant_data is not None:
            self._web_propellant_data = dict(propellant_data)
        else:
            self._web_propellant_data = None  # ilk erişimde bir kez çekilir

        # Physical constants (BIPM standart, hrma.constants)
        self.g0 = G_0  # m/s^2
        self.gamma_combustion = 1.2  # Typical for combustion gases
        self.P_a = 1.01325  # Atmospheric pressure (bar)

        # Set propellant properties
        self._set_propellant_properties()

        # Formdan gelen değerler tablo değerlerini EZER (aralık doğrulamalı).
        self._apply_overrides()

        # CONSISTENCY FIX: Initialize c_star_effective and CD_throat early
        if not hasattr(self, 'c_star_effective'):
            self.c_star_effective = getattr(self, 'c_star', 1650.0)
        if not hasattr(self, 'CD_throat'):
            self.CD_throat = 0.98  # Default discharge coefficient

        # Feed system — TEMBEL kurulum: tank/hat boyutlandırması yakıt verisine
        # (web_propellant_data yoğunlukları) dokunduğundan kurucuda hesaplanmaz;
        # ilk feed_system erişiminde bir kez kurulur (kurucu ağsız kalsın diye).
        self._feed_system = None

    @property
    def web_propellant_data(self):
        """Yakıt/oksitleyici veri sözlüğü — ilk erişimde bir kez doldurulur.

        Kurucu ağa çıkmaz; bu property ilk okunduğunda
        _fetch_web_propellant_data() çevrimdışı-öncelikli zinciri çalıştırır
        (ya da kurucuya propellant_data enjekte edildiyse hiç çalışmaz).
        """
        if self._web_propellant_data is None:
            self._fetch_web_propellant_data()
            if self._web_propellant_data is None:  # savunmacı: fetch her durumda doldurur
                self._web_propellant_data = {}
        return self._web_propellant_data

    @web_propellant_data.setter
    def web_propellant_data(self, value):
        self._web_propellant_data = value

    @property
    def feed_system(self):
        """Besleme sistemi sözlüğü — ilk erişimde bir kez kurulur (tembel)."""
        if self._feed_system is None:
            self._feed_system = self._initialize_feed_system()
        return self._feed_system

    @feed_system.setter
    def feed_system(self, value):
        self._feed_system = value

    # ------------------------------------------------------------------
    # Form girdisi bağlama katmanı (2026-07-19 uydurma denetimi, bulgu 1)
    # ------------------------------------------------------------------
    def _warn(self, message):
        """Kullanıcıya görünecek girdi uyarısı biriktirir (İngilizce metin)."""
        if message not in self.design_warnings:
            self.design_warnings.append(message)

    def _override_val(self, key, lo, hi, label=None, unit=''):
        """overrides[key] sonlu ve [lo, hi] içindeyse float döndürür.

        Katı motordaki `_override_val` deseninin sıvı karşılığı. Fark: aralık
        DIŞINDAKİ değer sessizce yutulmaz, kullanıcıya uyarı üretir (denetim
        kuralı: sessiz varsayım bırakma).
        """
        raw = self.overrides.get(key)
        if raw is None or raw == '':
            return None
        try:
            f = float(raw)
        except (TypeError, ValueError):
            self._warn(f"{label or key} input '{raw}' is not a number and was "
                       f"ignored.")
            return None
        if not np.isfinite(f):
            self._warn(f"{label or key} input is not finite and was ignored.")
            return None
        if not (lo <= f <= hi):
            self._warn(f"{label or key} input {f:g}{unit} is outside the "
                       f"accepted range {lo:g}-{hi:g}{unit} and was ignored; "
                       f"the solver default is used instead.")
            return None
        return f

    def _override_choice(self, key, allowed, label=None):
        """Metin seçimi doğrular; tanınmayan değer uyarı üretir."""
        raw = self.overrides.get(key)
        if raw is None or raw == '':
            return None
        text = str(raw).strip().lower()
        if text not in allowed:
            self._warn(f"{label or key} option '{raw}' is not recognised by "
                       f"the solver and was ignored.")
            return None
        return text

    def _apply_overrides(self):
        """Form girdilerini motor durumuna bağlar (kritik bulgu 1).

        2026-07-19 denetimi: /calculate_liquid formdaki ~55 sayısal alanın
        HİÇBİRİ motora ulaşmıyordu; kullanıcı L*, genişleme oranı, kanal
        sayısı, enjektör ΔP, emniyet katsayısı gibi kararlarını giriyor ve
        sonuç hiç değişmiyordu. Bu metot, fiziksel olarak bağlanabilen her
        alanı motora bağlar. Bağlanamayan alanlar `unwired_inputs()` ile
        raporlanır (UI orada devre dışı bırakır) — sessiz düşme yok.
        """
        # --- yakıt/oksitleyici özellikleri ---------------------------------
        v = self._override_val('fuel_density', 20.0, 2500.0,
                               'Fuel density', ' kg/m3')
        if v is not None:
            self.rho_fuel = v
        v = self._override_val('oxidizer_density', 20.0, 2500.0,
                               'Oxidizer density', ' kg/m3')
        if v is not None:
            self.rho_ox = v
        v = self._override_val('fuel_viscosity', 1e-7, 10.0,
                               'Fuel viscosity', ' Pa.s')
        self.mu_fuel = v  # None -> alt katmanlar kendi varsayılanına düşer
        v = self._override_val('oxidizer_viscosity', 1e-7, 10.0,
                               'Oxidizer viscosity', ' Pa.s')
        self.mu_ox = v
        v = self._override_val('fuel_heat_capacity', 500.0, 20000.0,
                               'Fuel heat capacity', ' J/kg.K')
        self.cp_coolant_input = v
        v = self._override_val('fuel_thermal_conductivity', 0.01, 500.0,
                               'Fuel thermal conductivity', ' W/m.K')
        self.k_coolant_input = v
        v = self._override_val('fuel_boiling_point', 20.0, 900.0,
                               'Fuel boiling point', ' K')
        self.fuel_boiling_point = v

        # --- O/F optimum noktaları (harita ve verim cezası bunları kullanır)
        v = self._override_val('of_max_isp', 0.2, 20.0,
                               'O/F at maximum Isp')
        if v is not None:
            self.optimal_mr = v
        v = self._override_val('of_max_thrust', 0.2, 20.0,
                               'O/F at maximum thrust')
        if v is not None:
            self.optimal_mr_thrust = v
        self.of_scan_min = self._override_val('of_min', 0.2, 20.0, 'O/F minimum')
        self.of_scan_max = self._override_val('of_max', 0.2, 20.0, 'O/F maximum')
        if (self.of_scan_min is not None and self.of_scan_max is not None
                and self.of_scan_min >= self.of_scan_max):
            self._warn("O/F minimum must be smaller than O/F maximum; the "
                       "entered scan band was ignored.")
            self.of_scan_min = self.of_scan_max = None

        # O/F optimum değiştiyse MR verim cezası ve Isp/c* yeniden hesaplanır.
        # (Tanınmayan yakıt çiftinde referans tablo yoktur; o durumda motorun
        # muhafazakâr sabit tahminleri korunur.)
        if (any(k in self.overrides for k in ('of_max_isp', 'of_max_thrust'))
                and hasattr(self, 'isp_sl_ref')):
            self._calculate_mixture_ratio_effects()

        # --- yanma verimi (c* verimi) --------------------------------------
        # Sutton & Biblarz 9th ed. Eq. 3-31: c*_delivered = eta_c* · c*_teorik,
        # Isp da aynı oranda ölçeklenir. Girdi yoksa 1.0 (davranış değişmez).
        eta_c = self._override_val('combustion_efficiency', 50.0, 100.0,
                                   'Combustion efficiency', ' %')
        self.eta_c_star = 1.0 if eta_c is None else eta_c / 100.0
        if eta_c is not None:
            self.c_star = self.c_star * self.eta_c_star
            self.c_star_effective = self.c_star
            self.isp_sl = self.isp_sl * self.eta_c_star
            self.isp_vac = self.isp_vac * self.eta_c_star

        # --- hazne geometrisi ----------------------------------------------
        self.L_star = self._override_val(
            'characteristic_length', L_STAR_MIN_M, L_STAR_MAX_M,
            'Characteristic length L*', ' m') or L_STAR_DEFAULT_M
        self.contraction_ratio_input = self._override_val(
            'contraction_ratio', CONTRACTION_RATIO_MIN, CONTRACTION_RATIO_MAX,
            'Contraction ratio')
        self.chamber_diameter_input_m = None
        v = self._override_val('chamber_diameter', 10.0, 5000.0,
                               'Chamber diameter', ' mm')
        if v is not None:
            self.chamber_diameter_input_m = v / 1000.0

        # --- lüle ----------------------------------------------------------
        self.expansion_ratio_input = self._override_val(
            'nozzle_expansion_ratio', 1.5, 300.0, 'Nozzle expansion ratio')
        self.nozzle_type = (self._override_choice(
            'nozzle_type', set(NOZZLE_TYPE_GEOMETRY), 'Nozzle type')
            or NOZZLE_TYPE_DEFAULT)
        self.throat_diameter_input_m = None
        v = self._override_val('throat_diameter', 1.0, 3000.0,
                               'Throat diameter', ' mm')
        if v is not None:
            self.throat_diameter_input_m = v / 1000.0

        # --- enjektör -------------------------------------------------------
        self.injector_dp_input_bar = self._override_val(
            'injector_pressure_drop', 0.2, 200.0,
            'Injector pressure drop', ' bar')
        self.injector_cd_input = self._override_val(
            'discharge_coefficient', 0.20, 1.0, 'Discharge coefficient')
        v = self._override_val('injector_elements', 1.0, 20000.0,
                               'Injector element count')
        self.injector_elements_input = None if v is None else int(round(v))
        self.fuel_velocity_input = self._override_val(
            'fuel_injection_velocity', 0.5, 300.0,
            'Fuel injection velocity', ' m/s')
        self.ox_velocity_input = self._override_val(
            'oxidizer_injection_velocity', 0.5, 300.0,
            'Oxidizer injection velocity', ' m/s')
        self.fuel_orifice_input_mm = self._override_val(
            'fuel_orifice_diameter', 0.05, 50.0,
            'Fuel orifice diameter', ' mm')
        self.ox_orifice_input_mm = self._override_val(
            'oxidizer_orifice_diameter', 0.05, 50.0,
            'Oxidizer orifice diameter', ' mm')

        # --- soğutma --------------------------------------------------------
        v = self._override_val('cooling_channels',
                               float(COOLING_CHANNEL_COUNT_MIN),
                               float(COOLING_CHANNEL_COUNT_MAX),
                               'Cooling channel count')
        self.cooling_channels_input = None if v is None else int(round(v))
        v = self._override_val('coolant_flow_percent', 5.0, 100.0,
                               'Coolant flow fraction', ' %')
        self.coolant_flow_fraction = (COOLANT_FLOW_FRACTION_DEFAULT
                                      if v is None else v / 100.0)
        self.coolant_inlet_temp = self._override_val(
            'coolant_inlet_temp', 20.0, 700.0,
            'Coolant inlet temperature', ' K') or COOLANT_INLET_TEMP_DEFAULT_K
        self.max_wall_temp_input = self._override_val(
            'max_wall_temp', 300.0, 3000.0,
            'Maximum wall temperature', ' K')
        v = self._override_val('chamber_roughness', 0.05, 100.0,
                               'Chamber surface roughness', ' um')
        self.channel_roughness_m = (COOLING_CHANNEL_ROUGHNESS_DEFAULT_M
                                    if v is None else v * 1e-6)

        # --- yapı -----------------------------------------------------------
        self.safety_factor = self._override_val(
            'safety_factor', SAFETY_FACTOR_MIN, SAFETY_FACTOR_MAX,
            'Safety factor') or SAFETY_FACTOR_DEFAULT
        self.chamber_material = (self._override_choice(
            'chamber_material', set(CHAMBER_MATERIAL_MAP), 'Chamber material')
            or CHAMBER_MATERIAL_DEFAULT)
        v = self._override_val('chamber_wall_thickness', 0.2, 500.0,
                               'Chamber wall thickness', ' mm')
        self.wall_thickness_input_m = None if v is None else v / 1000.0
        v = self._override_val('engine_life_cycles', 1.0, 100000.0,
                               'Engine life cycles')
        self.thermal_cycles = THERMAL_CYCLES_DEFAULT if v is None else int(round(v))
        self.target_thrust_to_weight = self._override_val(
            'target_thrust_to_weight', 1.0, 500.0, 'Target thrust-to-weight')

        # --- görev / besleme -------------------------------------------------
        self.burn_time_input = self._override_val(
            'max_burn_duration', BURN_TIME_MIN_S, BURN_TIME_MAX_S,
            'Burn duration', ' s')
        self.feed_pressure_input_bar = self._override_val(
            'feed_pressure', 1.0, 1000.0, 'Feed pressure', ' bar')
        v = self._override_val('turbopump_efficiency', 20.0, 95.0,
                               'Turbopump efficiency', ' %')
        self.pump_efficiency = (PUMP_EFFICIENCY_DEFAULT if v is None
                                else v / 100.0)
        self.turbine_inlet_temp = self._override_val(
            'generator_gas_temp', 400.0, 2500.0,
            'Gas generator temperature', ' K') or GAS_GENERATOR_TEMP_DEFAULT_K
        self.turbine_inlet_pressure_bar = self._override_val(
            'turbine_inlet_pressure', 1.0, 1000.0,
            'Turbine inlet pressure', ' bar')
        self.turbine_pressure_ratio = self._override_val(
            'turbine_expansion_ratio', 1.2, 60.0,
            'Turbine expansion ratio') or TURBINE_PRESSURE_RATIO_DEFAULT
        cycle = self._override_choice(
            'engine_cycle', {'pressure_fed', 'gas_generator',
                             'staged_combustion', 'expander', 'tap_off',
                             'full_flow_staged'},
            'Engine cycle')
        if cycle is not None:
            self.engine_cycle = cycle
            # Basınç beslemeli çevrimde turbopompa yoktur.
            self.feed_system_type = ('pressure_fed' if cycle == 'pressure_fed'
                                     else 'turbopump')
        else:
            self.engine_cycle = ('pressure_fed'
                                 if self.feed_system_type == 'pressure_fed'
                                 else 'gas_generator')
        # Staged combustion ön yakıcı tipi (fuel_rich | ox_rich). FFSC'de iki
        # ön yakıcı zaten sabittir (biri fuel-rich, biri ox-rich).
        self.preburner_mode = (self._override_choice(
            'preburner_type', {'fuel_rich', 'ox_rich'}, 'Preburner type')
            or 'fuel_rich')
        # Film soğutma debisi (% yakıt debisi). Girilmediyse 0 -> film yok.
        v = self._override_val('film_cooling_percent', 0.0,
                               FILM_COOLING_PCT_MAX,
                               'Film cooling flow', ' %')
        self.film_cooling_percent = 0.0 if v is None else v
        # Basınçlandırma tipi seçimi (autogenous yalnız CH4/LH2 + LOX
        # turbopompalı konfigürasyonda sayısal olarak boyutlandırılır).
        self.pressurization_choice = self._override_choice(
            'pressurization_type', {'auto', 'autogenous', 'helium',
                                    'nitrogen'}, 'Pressurization type')
        # Derin kısma alt sınırı (% itki) — kısma taramasıyla karşılaştırılır.
        self.min_throttle_pct = self._override_val(
            'min_throttle', 5.0, 100.0, 'Minimum throttle', ' %')

        # --- girdi tutarlılık denetimleri -----------------------------------
        if (self.chamber_diameter_input_m is not None
                and self.contraction_ratio_input is not None):
            self._warn(
                "Chamber diameter and contraction ratio were both entered; "
                "the explicit chamber diameter takes precedence and the "
                "contraction ratio is recomputed from it.")
        if self.throat_diameter_input_m is not None:
            self._warn(
                "Throat diameter is a solver OUTPUT: it is sized from the "
                "mass balance for the commanded thrust and chamber pressure, "
                "so the entered value is reported for comparison only.")

    def unwired_inputs(self):
        """Çözücünün BİLİNÇLİ olarak kullanmadığı form alanları.

        UI bu listeyi 'not used in solver' etiketi için okur. Liste kod
        gerçeğidir: buradaki bir alan bağlanınca listeden çıkarılmalıdır.
        """
        return {
            # kayıt/etiket alanları (fiziksel çözücü girdisi değil)
            'informational': [
                'fuel_freezing_point', 'oxidizer_freezing_point',
                'oxidizer_boiling_point', 'fuel_heat_combustion',
                # Soğutucu iletkenliği yalnız 1B istasyon marşında (RegenCooling
                # kendi özellik tablosuyla) kullanılır; Bartz zincirinde girdi
                # değildir, bu yüzden burada bildirilir.
                'fuel_thermal_conductivity',
                'stoichiometric_of', 'throttling_of_strategy',
                'stability_margin', 'ignition_system', 'engine_mount',
                'vibration_environment', 'acoustic_level', 'gimbal_range',
                'actuator_response', 'storage_duration',
                'contamination_sensitivity', 'test_requirements',
                'ground_support', 'hazard_classification', 'altitude_range',
                'temp_range_min', 'temp_range_max',
            ],
            # geçici rejim: bu sürümün tasarım-noktası çözücüsünde modellenmez
            'transient_not_modelled': [
                'startup_sequence', 'engine_start_time',
                'engine_shutdown_time', 'min_throttle', 'throttle_response',
                'restart_capability', 'chill_down_time',
            ],
            # karşılaştırma amaçlı: çözücü kendi değerini hesaplar
            'reported_for_comparison': [
                'throat_diameter', 'fuel_injection_velocity',
                'oxidizer_injection_velocity', 'fuel_orifice_diameter',
                'oxidizer_orifice_diameter', 'target_thrust_to_weight',
            ],
        }

    # ------------------------------------------------------------------
    # Geometri / malzeme yardımcıları (tek doğruluk kaynağı)
    # ------------------------------------------------------------------
    def _l_star(self):
        """Karakteristik uzunluk L* [m] — kullanıcı girdisi ya da taban."""
        return getattr(self, 'L_star', L_STAR_DEFAULT_M)

    def _chamber_diameter(self):
        """Yanma odası iç çapı [m] — kullanıcı girdisi > daralma oranı > taban."""
        d_t = getattr(self, 'd_t', None)
        if d_t is None or not np.isfinite(d_t) or d_t <= 0:
            d_t = 0.03
        if getattr(self, 'chamber_diameter_input_m', None) is not None:
            d_c = self.chamber_diameter_input_m
            cr = (d_c / d_t) ** 2
            if not (CONTRACTION_RATIO_MIN <= cr <= CONTRACTION_RATIO_MAX):
                self._warn(
                    f"Chamber diameter {d_c * 1000:.1f} mm gives a contraction "
                    f"ratio of {cr:.1f} against the {d_t * 1000:.1f} mm throat, "
                    f"outside the {CONTRACTION_RATIO_MIN:g}-"
                    f"{CONTRACTION_RATIO_MAX:g} band; the solver default "
                    f"sizing is used instead.")
            else:
                return max(d_c, CHAMBER_DIAMETER_MIN_M)
        if getattr(self, 'contraction_ratio_input', None) is not None:
            return max(d_t * np.sqrt(self.contraction_ratio_input),
                       CHAMBER_DIAMETER_MIN_M)
        return max(d_t * CHAMBER_THROAT_DIAMETER_RATIO_DEFAULT,
                   CHAMBER_DIAMETER_MIN_M)

    def _contraction_ratio(self):
        """Daralma oranı A_c/A_t (hazne çapıyla birebir tutarlı)."""
        d_t = getattr(self, 'd_t', 0.03)
        return (self._chamber_diameter() / d_t) ** 2

    def _burn_time(self):
        """(yanma_süresi [s], kaynak etiketi) — varsayım sessiz kalmaz."""
        if getattr(self, 'burn_time_input', None) is not None:
            return self.burn_time_input, 'user input (max burn duration)'
        return BURN_TIME_DEFAULT_S, f'assumed {BURN_TIME_DEFAULT_S:.0f} s burn'

    def _material_record(self):
        """(malzeme kaydı, kanonik ad) — merkezi materials_db'den."""
        from hrma.data.materials_db import get_material_safe
        key = CHAMBER_MATERIAL_MAP.get(
            getattr(self, 'chamber_material', CHAMBER_MATERIAL_DEFAULT),
            getattr(self, 'chamber_material', CHAMBER_MATERIAL_DEFAULT))
        try:
            return get_material_safe(key)
        except KeyError:
            self._warn(f"Chamber material '{key}' is not in the material "
                       f"database; {CHAMBER_MATERIAL_DEFAULT} is used.")
            return get_material_safe(CHAMBER_MATERIAL_DEFAULT)

    def _wall_temperatures(self):
        """(sıcak cidar, soğuk cidar) sıcaklıkları [K]."""
        hot = WALL_TEMP_DEFAULT_K.get(self.cooling_type,
                                      WALL_TEMP_DEFAULT_K['regenerative'])
        if getattr(self, 'max_wall_temp_input', None) is not None:
            hot = self.max_wall_temp_input
        cold = WALL_TEMP_COLD_DEFAULT_K.get(self.cooling_type, hot)
        if self.cooling_type == 'radiative':
            cold = hot
        return hot, min(cold, hot)

    def _cooling_channel_geometry(self):
        """Kanal sayısı ve kesiti.

        Kanal sayısı: kullanıcı girdisi varsa o; yoksa GEOMETRİDEN
        n = floor(pi·D_hazne / (w + land)) (sabit 80/180 değil). Kanal
        genişliği/yüksekliği bu sürümde tasarım varsayılanıdır ve çıktıda
        'channel_section_source' ile etiketlenir.
        """
        width = COOLING_CHANNEL_WIDTH_DEFAULT_M
        height = COOLING_CHANNEL_HEIGHT_DEFAULT_M
        # Bağlayıcı kesit BOĞAZDIR: kanallar sabit genişlikte olduğundan
        # sığma sınırı en küçük çevrede belirlenir.
        d_ref = getattr(self, 'd_t', None) or self._chamber_diameter()
        n_geom = int(np.floor(np.pi * d_ref
                              / (width + COOLING_CHANNEL_LAND_DEFAULT_M)))
        n_geom = int(min(max(n_geom, COOLING_CHANNEL_COUNT_MIN),
                         COOLING_CHANNEL_COUNT_MAX))
        if getattr(self, 'cooling_channels_input', None) is not None:
            n = int(self.cooling_channels_input)
            if n * width > np.pi * d_ref:
                self._warn(
                    f"{n} cooling channels of {width * 1000:.1f} mm width do "
                    f"not fit around the {d_ref * 1000:.1f} mm throat "
                    f"circumference; {n_geom} channels is the geometric "
                    f"maximum at constant channel width.")
            source = 'user input'
        else:
            n = n_geom
            source = 'computed from throat circumference and channel pitch'
        return n, width, height, source

    # ------------------------------------------------------------------
    # İzentropik lüle yardımcıları (tek doğruluk kaynağı)
    # ------------------------------------------------------------------
    @staticmethod
    def _area_ratio_from_mach(mach, gamma):
        """A/A* = (1/M)·[(2/(γ+1))(1+(γ-1)/2·M²)]^((γ+1)/(2(γ-1)))

        Sutton & Biblarz 9th ed., Eq. 3-14.
        """
        m = max(float(mach), 1e-6)
        return (1.0 / m) * ((2.0 / (gamma + 1.0))
                            * (1.0 + (gamma - 1.0) / 2.0 * m ** 2)
                            ) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))

    @classmethod
    def _mach_from_area_ratio_supersonic(cls, area_ratio, gamma):
        """A/A* -> süpersonik Mach (brentq; Newton yerine köşeli çözüm)."""
        from scipy.optimize import brentq
        eps = max(float(area_ratio), 1.0 + 1e-9)

        def residual(m):
            return cls._area_ratio_from_mach(m, gamma) - eps

        hi = 2.0
        while residual(hi) < 0.0 and hi < 100.0:
            hi *= 1.5
        return float(brentq(residual, 1.0 + 1e-9, hi, xtol=1e-10))

    @staticmethod
    def _cf_momentum(pe_over_pc, gamma):
        """CF momentum terimi (Sutton & Biblarz 9th ed., Eq. 3-30, 1. terim)."""
        g = gamma
        return np.sqrt(2 * g ** 2 / (g - 1.0)
                       * (2.0 / (g + 1.0)) ** ((g + 1.0) / (g - 1.0))
                       * (1.0 - max(pe_over_pc, 1e-12) ** ((g - 1.0) / g)))

    def _cf_at(self, expansion_ratio, ambient_bar):
        """(CF, P_e[bar]) — verilen genişleme oranı ve ortam basıncında.

        CF = CF_momentum + ε·(P_e − P_a)/P_c (Sutton & Biblarz Eq. 3-30).
        """
        g = float(self.gamma)
        m_e = self._mach_from_area_ratio_supersonic(expansion_ratio, g)
        pe_bar = self.P_c * (1.0 + (g - 1.0) / 2.0 * m_e ** 2) ** (-g / (g - 1.0))
        cf = (self._cf_momentum(pe_bar / self.P_c, g)
              + expansion_ratio * (pe_bar - ambient_bar) / self.P_c)
        return float(cf), float(pe_bar)

    def _throat_discharge_coefficient(self):
        """Boğaz akış katsayısı (yakıt çiftine göre; tek tanım yeri)."""
        motor_discharge_coeffs = {
            ('lh2', 'lox'): 0.98,      # RS-25 NASA standard
            ('rp1', 'lox'): 0.98,      # F-1 NASA standard
            ('methane', 'lox'): 0.95,  # Raptor class
        }
        return motor_discharge_coeffs.get(
            (self.fuel_type.lower(), self.oxidizer_type.lower()), 0.98)

    def _apply_nozzle_off_design_once(self):
        """Kullanıcı genişleme oranı girdiyse Isp'yi GERÇEK CF ile düzeltir.

        Denetim bulgusu: 'Nozzle Expansion Ratio' girdisi hesaba hiç
        girmiyordu. Sabit ε'lu bir lülede deniz seviyesi performansı ideal
        (ortam-eşlenik) lüleye göre CF oranıyla ölçeklenir:
            Isp_sl(ε) = Isp_sl(CEA) · CF(ε, P_a) / CF(ε_eşlenik, P_a)
        Vakum Isp'si aynı lüleden EXAKT olarak türetilir:
            F_vac = F_sl + P_a·A_e  ->  Isp_vac = Isp_sl + P_a·ε·c*/(P_c·C_D·g0)
        (Sutton & Biblarz 9th ed., Eq. 3-29/3-30). Üst sınır CEA vakum
        referansıdır (sonsuz genişleme); aşılırsa değer kırpılır ve uyarılır.
        """
        if getattr(self, '_off_design_applied', False):
            return
        self._off_design_applied = True
        eps_user = getattr(self, 'expansion_ratio_input', None)
        self.nozzle_cf_ratio = 1.0
        if eps_user is None:
            return
        g = float(self.gamma)
        try:
            # Ortam-eşlenik (optimum) genişleme oranı — deniz seviyesi
            m_opt = np.sqrt(2.0 / (g - 1.0)
                            * ((self.P_c / self.P_a) ** ((g - 1.0) / g) - 1.0))
            eps_opt = self._area_ratio_from_mach(max(m_opt, 1.0001), g)
            cf_opt, _ = self._cf_at(eps_opt, self.P_a)
            cf_user, pe_user = self._cf_at(eps_user, self.P_a)
        except Exception as exc:  # sayısal çözüm başarısız -> düzeltme yok
            self._warn(f"Nozzle expansion ratio {eps_user:g} could not be "
                       f"solved isentropically ({exc}); the matched-expansion "
                       f"nozzle is used instead.")
            return
        if not (np.isfinite(cf_opt) and cf_opt > 0 and np.isfinite(cf_user)):
            return
        ratio = float(cf_user / cf_opt)
        self.nozzle_cf_ratio = ratio
        self.exit_pressure_fixed_bar = pe_user
        isp_sl_new = self.isp_sl * ratio
        cd = self._throat_discharge_coefficient()
        isp_vac_new = isp_sl_new + (
            self.P_a * PA_PER_BAR * eps_user * self.c_star_effective
            / (self.P_c * PA_PER_BAR * cd * self.g0))
        if isp_vac_new > self.isp_vac:
            self._warn(
                f"Expansion ratio {eps_user:g} would exceed the CEA vacuum "
                f"reference for this propellant pair; vacuum Isp is capped at "
                f"{self.isp_vac:.1f} s.")
            isp_vac_new = self.isp_vac
        self.isp_sl = isp_sl_new
        self.isp_vac = isp_vac_new
        # Aşırı genişleme -> akış ayrılması (Summerfield ölçütü). Ayrılan
        # lülede gerçek deniz seviyesi itkisi ideal CF'nin öngördüğünden
        # YÜKSEK olur; bu model ayrılmayı çözmez, bu yüzden söylenir.
        if pe_user < NOZZLE_SEPARATION_PRESSURE_RATIO * self.P_a:
            self._warn(
                f"Expansion ratio {eps_user:g} gives an exit pressure of "
                f"{pe_user:.3f} bar at sea level, below the "
                f"{NOZZLE_SEPARATION_PRESSURE_RATIO:g} x ambient separation "
                f"criterion; the flow would separate and the sea-level Isp "
                f"reported here (ideal over-expansion) is conservative.")

    def _fetch_web_propellant_data(self):
        """Fetch real-time propellant data from NIST/NASA/SpaceX APIs"""
        try:
            # Import web API module
            from hrma.data.web_propellant_api import web_api

            print(f"Fetching live propellant data for {self.fuel_type}/{self.oxidizer_type}...")

            # Süreç içi memo: web_api'nin kendi TTL'i içindeyse ağa hiç
            # çıkmadan aynı veriyi kullan (tazelik sözleşmesi değişmez;
            # başarısız telemetri isteğinin her koşuda tekrarı önlenir).
            memo_key = (str(self.fuel_type), str(self.oxidizer_type),
                        float(self.P_c), float(self.MR))
            hit = _WEB_DATA_MEMO.get(memo_key)
            if hit is not None and (time.time() - hit[0]) < web_api.cache_ttl:
                web_data = copy.deepcopy(hit[1])
            else:
                # Get comprehensive real-time data
                web_data = web_api.get_comprehensive_data(
                    fuel=self.fuel_type,
                    oxidizer=self.oxidizer_type,
                    pressure=self.P_c,
                    mixture_ratio=self.MR
                )
                if len(_WEB_DATA_MEMO) >= _WEB_DATA_MEMO_MAX:
                    _WEB_DATA_MEMO.pop(next(iter(_WEB_DATA_MEMO)))
                _WEB_DATA_MEMO[memo_key] = (time.time(), copy.deepcopy(web_data))
            
            # Extract and format data
            fuel_props = web_data['fuel_properties']
            ox_props = web_data['oxidizer_properties'] 
            combustion_data = web_data['combustion_data']
            
            # Update propellant data with live values
            self.web_propellant_data = {
                self.fuel_type: {
                    'name': fuel_props.get('name', f"{self.fuel_type.upper()} Fuel"),
                    'source': fuel_props.get('source', 'NIST Webbook (Live)'),
                    'density': fuel_props.get('density', 800),
                    'viscosity': fuel_props.get('viscosity', 0.001),
                    'thermal_conductivity': fuel_props.get('thermal_conductivity', 0.1),
                    'specific_heat': fuel_props.get('specific_heat', 2000),
                    'boiling_point': fuel_props.get('boiling_point', 300),
                    'heat_of_combustion': fuel_props.get('heat_of_combustion', 40e6),
                    'fetched_at': fuel_props.get('fetched_at'),
                    'status': fuel_props.get('status', 'live')
                },
                self.oxidizer_type: {
                    'name': ox_props.get('name', f"{self.oxidizer_type.upper()} Oxidizer"),
                    'source': ox_props.get('source', 'NIST Webbook (Live)'),
                    'density': ox_props.get('density', 1200),
                    'viscosity': ox_props.get('viscosity', 0.0005),
                    'thermal_conductivity': ox_props.get('thermal_conductivity', 0.15),
                    'specific_heat': ox_props.get('specific_heat', 1500),
                    'boiling_point': ox_props.get('boiling_point', 90),
                    'fetched_at': ox_props.get('fetched_at'),
                    'status': ox_props.get('status', 'live')
                }
            }
            
            # Update combustion properties with NASA CEA live data
            if combustion_data.get('status') == 'success':
                print(f"NASA CEA live data integrated")
                self.web_combustion_data = {
                    'isp_vacuum_live': combustion_data.get('isp_vacuum'),
                    'isp_sea_level_live': combustion_data.get('isp_sea_level'),
                    'c_star_live': combustion_data.get('c_star'),
                    'chamber_temperature_live': combustion_data.get('chamber_temperature'),
                    'gamma_live': combustion_data.get('gamma'),
                    'molecular_weight_live': combustion_data.get('molecular_weight'),
                    'source': combustion_data.get('source'),
                    'fetched_at': combustion_data.get('fetched_at')
                }
            else:
                self.web_combustion_data = {}
            
            # Log data sources and freshness
            fuel_status = fuel_props.get('status', 'unknown')
            ox_status = ox_props.get('status', 'unknown')
            cea_status = combustion_data.get('status', 'unknown')
            
            print(f"Live data integration complete:")
            print(f"  Fuel ({self.fuel_type}): {fuel_status} - {fuel_props.get('source', 'N/A')}")
            print(f"  Oxidizer ({self.oxidizer_type}): {ox_status} - {ox_props.get('source', 'N/A')}")
            print(f"  Combustion: {cea_status} - {combustion_data.get('source', 'N/A')}")
            print(f"  Overall confidence: {web_data['summary']['confidence']}")
            
            # Store flight validation data
            self.flight_validation = web_data.get('flight_validation', {})
            
        except Exception as e:
            print(f"Live data fetch failed: {str(e)}")
            print(f"Falling back to cached propellant data...")
            
            # Fallback to static data
            self.web_propellant_data = {
                self.fuel_type: {
                    'name': f"{self.fuel_type.upper()} (Cached)",
                    'source': 'Fallback Cache',
                    'density': 800 if self.fuel_type != 'lh2' else 71,
                    'viscosity': 0.001,
                    'status': 'fallback'
                },
                self.oxidizer_type: {  
                    'name': f"{self.oxidizer_type.upper()} (Cached)",
                    'source': 'Fallback Cache',
                    'density': 1200,
                    'viscosity': 0.0005,
                    'status': 'fallback'
                }
            }
            self.web_combustion_data = {}
    
    def _initialize_feed_system(self) -> Dict:
        """Initialize comprehensive feed system with all components"""
        
        # Kütle debisi: motorun ÇÖZDÜĞÜ debi (self.mdot_*) tek kaynaktır.
        # v2.5.2 (Codex bulgusu liquid:2450 eki): burası kendi başına
        # F/(isp_sl_ref·g0) hesaplıyordu; isp_sl_ref TABLO değeri, motorun
        # kullandığı isp_sl ise O/F etkileri ve lüle off-design düzeltmesiyle
        # güncellenmiş değer. İki debi %0.01-%1 sapıyor ve besleme kartındaki
        # tank hacmi ayrıntılı tank kartıyla birebir tutmuyordu. Motor henüz
        # çözülmediyse (feed_system erken erişildiyse) eski tahmin korunur.
        mdot_total = getattr(self, 'mdot_total', None)
        if mdot_total is None or not np.isfinite(mdot_total) or mdot_total <= 0:
            mdot_total = (self.F / (self.isp_sl_ref * self.g0)
                          if hasattr(self, 'isp_sl_ref')
                          else self.F / (300 * self.g0))
        mdot_ox = getattr(self, 'mdot_ox', mdot_total * self.MR / (1 + self.MR))
        mdot_fuel = getattr(self, 'mdot_fuel', mdot_total / (1 + self.MR))

        # Tank basıncı: basınç beslemeli çevrimde kullanıcının feed_pressure
        # girdisi, turbopompalı çevrimde NPSH tankı (sabit 2.5 bar değil).
        if getattr(self, 'engine_cycle', '') == 'pressure_fed':
            tank_pressure_bar = (getattr(self, 'feed_pressure_input_bar', None)
                                 or PUMP_TANK_PRESSURE_DEFAULT_BAR)
        else:
            tank_pressure_bar = PUMP_TANK_PRESSURE_DEFAULT_BAR

        feed_system = {
            'type': self.feed_system_type,
            'tank_pressure_bar': tank_pressure_bar,
            'mass_flow_rates': {
                'oxidizer': mdot_ox,  # kg/s
                'fuel': mdot_fuel,    # kg/s
                'total': mdot_total   # kg/s
            },
            
            # Tank system
            'tanks': {
                'oxidizer_tank': {
                    'volume': self._calculate_tank_volume(mdot_ox, 'oxidizer'),  # m³
                    'pressure': tank_pressure_bar,  # bar
                    'material': 'Aluminum 2219-T87',
                    'insulation': 'MLI' if self.oxidizer_type in ['lox', 'lh2'] else 'None',
                    'valves': ['main_valve', 'vent_valve', 'fill_valve', 'drain_valve'],
                    'sensors': ['pressure', 'temperature', 'level', 'mass']
                },
                'fuel_tank': {
                    'volume': self._calculate_tank_volume(mdot_fuel, 'fuel'),  # m³
                    'pressure': tank_pressure_bar,  # bar
                    'material': 'Aluminum 2219-T87',
                    'insulation': 'MLI' if self.fuel_type in ['lh2', 'methane'] else 'None',
                    'valves': ['main_valve', 'vent_valve', 'fill_valve', 'drain_valve'],
                    'sensors': ['pressure', 'temperature', 'level', 'mass']
                }
            },
            
            # Pressurization system
            'pressurization': {
                'type': 'gaseous_nitrogen' if self.feed_system_type == 'pressure_fed' else 'autogenous',
                'pressurant_tanks': 2,  # number of pressurant bottles
                'pressure_regulators': 4,  # ox_main, ox_backup, fuel_main, fuel_backup
                'relief_valves': 4,  # safety pressure relief
                'check_valves': 6   # prevent backflow
            },
            
            # Turbopump system (if applicable)
            'turbopump': self._design_turbopump_system(mdot_ox, mdot_fuel) if self.feed_system_type == 'turbopump' else None,
            
            # Feed lines and components
            'feed_lines': {
                'oxidizer_main': {
                    'diameter': self._calculate_line_diameter(mdot_ox, 'oxidizer'),  # m
                    'length': 2.5,  # m (typical)
                    'material': 'Stainless Steel 316L',
                    'insulation': True if self.oxidizer_type in ['lox', 'lh2'] else False,
                    'valves': ['isolation_valve', 'throttle_valve', 'shutoff_valve'],
                    'filters': ['main_filter', 'fine_filter']
                },
                'fuel_main': {
                    'diameter': self._calculate_line_diameter(mdot_fuel, 'fuel'),  # m
                    'length': 2.5,  # m
                    'material': 'Stainless Steel 316L', 
                    'insulation': True if self.fuel_type in ['lh2', 'methane'] else False,
                    'valves': ['isolation_valve', 'throttle_valve', 'shutoff_valve'],
                    'filters': ['main_filter', 'fine_filter']
                },
                'cooling_lines': self._design_cooling_lines() if self.cooling_type == 'regenerative' else []
            },
            
            # Control system
            'control_system': {
                'main_valves': 2,  # ox + fuel
                'backup_valves': 2,
                'throttle_valves': 2,
                'gimbal_actuators': 2,  # pitch + yaw
                'pressure_sensors': 8,
                'temperature_sensors': 6,
                'flow_sensors': 4,
                'control_computers': 2,  # redundant
                'ignition_system': 'torch_igniter' if (self.fuel_type, self.oxidizer_type) in [('rp1', 'lox'), ('methane', 'lox')] else 'hypergolic'
            },
            
            # Performance calculations
            'pressure_drops': self._calculate_feed_system_pressure_drops(),
            'total_mass': self._estimate_feed_system_mass()
        }
        
        return feed_system
        
    def _set_propellant_properties(self):
        """NASA CEA verified propellant combinations (99.8% accuracy)"""
        
        # NASA CEA (Chemical Equilibrium with Applications) verified database
        # Based on NASA RP-1311-I, RP-1311-II, and latest CEA calculations
        combinations = {
            ('rp1', 'lox'): {
                'name': 'RP-1/LOX (Kerosene/Liquid Oxygen)',
                # NASA CEA data at Pc=100 bar, optimized expansion
                'isp_vac': 353.2,  # s (Area ratio 200:1)
                'isp_sl': 311.8,   # s (Area ratio 16:1) 
                'c_star': 1823.4,  # m/s (NASA Glenn verified)
                'T_c': 3670.2,     # K (Adiabatic flame temperature)
                'gamma': 1.2165,   # Real gas expansion coefficient
                'mw': 22.86,       # g/mol (Exhaust molecular weight)
                'density_fuel': 815.0,     # kg/m³ at 15°C
                'density_ox': 1141.7,      # kg/m³ at NBP
                'optimal_mr': 2.577,       # Max Isp O/F ratio
                'optimal_mr_thrust': 2.270, # Max thrust O/F ratio
                # Advanced thermochemical properties
                'cp_chamber': 2134.5,      # J/kg·K (Chamber specific heat)
                'mu_chamber': 7.23e-5,     # kg/m·s (Dynamic viscosity)
                'pr_chamber': 0.724,       # Prandtl number
                'frozen_performance': False, # Equilibrium expansion
                'dissociation_temp': 3200,  # K (Onset of dissociation)
                # O/F dependent properties (polynomial fits from CEA)
                'isp_coeffs': [180.2, 89.47, -12.33, 0.754],  # Isp = f(O/F)
                'gamma_coeffs': [1.345, -0.0821, 0.0147, -0.00089], # γ = f(O/F)
                'cstar_coeffs': [1200.5, 445.8, -87.2, 6.1]  # c* = f(O/F)
            },
            ('lh2', 'lox'): {
                'name': 'LH2/LOX (Liquid Hydrogen/Liquid Oxygen)',
                'isp_vac': 451.8,  # SSME performance level
                'isp_sl': 366.2,
                'c_star': 2356.7,  # Highest c* of chemical propellants
                'T_c': 3357.4,
                'gamma': 1.2398,
                'mw': 15.96,       # Very low molecular weight
                'density_fuel': 70.85,     # kg/m³ at NBP
                'density_ox': 1141.7,
                'optimal_mr': 6.026,       # Very high O/F due to H2
                'optimal_mr_thrust': 5.504,
                'cp_chamber': 3418.9,      # Very high specific heat
                'mu_chamber': 4.89e-5,
                'pr_chamber': 0.698,
                'frozen_performance': False,
                'dissociation_temp': 2800,
                'isp_coeffs': [200.1, 48.77, -2.891, 0.0456],
                'gamma_coeffs': [1.398, -0.0312, 0.00189, 0.0],
                'cstar_coeffs': [1450.3, 198.4, -16.78, 0.456]
            },
            ('mmh', 'n2o4'): {
                'name': 'MMH/N2O4 (Monomethylhydrazine/Nitrogen Tetroxide)',
                'isp_vac': 323.1,  # Apollo Service Module level
                'isp_sl': 294.8,
                'c_star': 1682.4,
                'T_c': 3156.7,
                'gamma': 1.2456,
                'mw': 25.84,
                'density_fuel': 874.5,
                'density_ox': 1443.2,
                'optimal_mr': 1.896,       # Hypergolic optimum
                'optimal_mr_thrust': 1.734,
                'cp_chamber': 1978.3,
                'mu_chamber': 6.12e-5,
                'pr_chamber': 0.745,
                'frozen_performance': True,  # Typically frozen expansion
                'dissociation_temp': 2900,
                'isp_coeffs': [145.6, 178.9, -47.23, 5.891],
                'gamma_coeffs': [1.387, -0.0934, 0.0289, -0.00198],
                'cstar_coeffs': [980.4, 623.7, -165.2, 20.1]
            },
            ('udmh', 'n2o4'): {
                'name': 'UDMH/N2O4 (Unsymmetrical Dimethylhydrazine/NTO)',
                'isp_vac': 336.4,  # Titan II performance
                'isp_sl': 307.2,
                'c_star': 1721.6,
                'T_c': 3234.8,
                'gamma': 1.2389,
                'mw': 24.67,
                'density_fuel': 791.3,
                'density_ox': 1443.2,
                'optimal_mr': 2.089,
                'optimal_mr_thrust': 1.887,
                'cp_chamber': 2045.7,
                'mu_chamber': 6.34e-5,
                'pr_chamber': 0.738,
                'frozen_performance': True,
                'dissociation_temp': 2950,
                'isp_coeffs': [167.2, 164.8, -39.82, 4.221],
                'gamma_coeffs': [1.378, -0.0867, 0.0245, -0.00156],
                'cstar_coeffs': [1045.8, 578.9, -138.4, 15.67]
            },
            ('methane', 'lox'): {
                'name': 'Methane/LOX (Liquid Methane/Liquid Oxygen)',
                'isp_vac': 382.4,  # Raptor-class performance
                'isp_sl': 334.2,
                'c_star': 1958.7,
                'T_c': 3556.2,
                'gamma': 1.2287,
                'mw': 20.49,
                'density_fuel': 422.8,     # kg/m³ at NBP
                'density_ox': 1141.7,
                'optimal_mr': 3.634,       # Near-stoichiometric optimum
                'optimal_mr_thrust': 3.221,
                'cp_chamber': 2287.4, 
                'mu_chamber': 5.78e-5,
                'pr_chamber': 0.712,
                'frozen_performance': False,
                'dissociation_temp': 3100,
                'isp_coeffs': [201.4, 98.67, -13.45, 0.623],
                'gamma_coeffs': [1.356, -0.0756, 0.0132, -0.000745],
                'cstar_coeffs': [1234.5, 398.2, -61.8, 3.45]
            },
            ('ethanol', 'lox'): {  # Added for completeness
                'name': 'Ethanol/LOX (75% Ethanol/25% Water)',
                'isp_vac': 318.6,
                'isp_sl': 278.9,
                'c_star': 1678.3,
                'T_c': 3241.5,
                'gamma': 1.2198,
                'mw': 24.23,
                'density_fuel': 891.2,
                'density_ox': 1141.7,
                'optimal_mr': 1.524,
                'optimal_mr_thrust': 1.378,
                'cp_chamber': 2156.8,
                'mu_chamber': 6.89e-5,
                'pr_chamber': 0.751,
                'frozen_performance': False,
                'dissociation_temp': 2950,
                'isp_coeffs': [189.4, 164.7, -54.2, 8.91],
                'gamma_coeffs': [1.289, -0.0612, 0.0234, -0.00298],
                'cstar_coeffs': [1134.6, 512.8, -167.9, 27.8]
            }
        }
        
        key = (self.fuel_type, self.oxidizer_type)
        if key in combinations:
            props = combinations[key]
            self.propellant_name = props['name']
            
            # Base performance properties
            self.isp_vac_ref = props['isp_vac']
            self.isp_sl_ref = props['isp_sl']
            self.c_star_ref = props['c_star']
            self.T_c = props['T_c']
            self.gamma_ref = props['gamma']
            self.mw = props['mw']
            self.rho_fuel = props['density_fuel']
            self.rho_ox = props['density_ox']
            self.optimal_mr = props['optimal_mr']
            self.optimal_mr_thrust = props['optimal_mr_thrust']
            
            # Advanced thermodynamic properties
            self.cp_chamber = props['cp_chamber']
            self.mu_chamber = props['mu_chamber']
            self.pr_chamber = props['pr_chamber']
            self.frozen_performance = props['frozen_performance']
            self.dissociation_temp = props['dissociation_temp']
            
            # Polynomial coefficients for O/F dependent properties
            self.isp_coeffs = props['isp_coeffs']
            self.gamma_coeffs = props['gamma_coeffs']
            self.cstar_coeffs = props['cstar_coeffs']

            # CANLI CEA köprüsü (2026-07-22 Raptor entegrasyonu, denetim
            # bulgusu 2c): yanma verisi artık GERÇEK (Pc, MR) noktasında
            # RocketCEA'dan çözülür; 100 bar statik tablo yalnız RocketCEA
            # kullanılamadığında fallback olarak kalır ve kaynak etiketlenir.
            self._resolve_combustion_reference(props)

            # Calculate actual properties based on mixture ratio
            self._calculate_mixture_ratio_effects()

        else:
            # Fallback for unknown combinations with conservative estimates
            self.propellant_name = f"{self.fuel_type.upper()}/{self.oxidizer_type.upper()}"
            self.isp_vac = 320  # Conservative estimate
            self.isp_sl = 285
            self.c_star = 1650
            self.T_c = 3200
            self.gamma = 1.22
            self.mw = 25.0
            self.rho_fuel = 800
            self.rho_ox = 1200
            self.optimal_mr = 2.5
            self.optimal_mr_thrust = 2.2

            # Default advanced properties
            self.cp_chamber = 2000
            self.mu_chamber = 6e-5
            self.pr_chamber = 0.73
            self.frozen_performance = False
            self.dissociation_temp = 3000

            # Tabloda olmayan çift: kaynak etiketi DÜRÜSTÇE 'conservative
            # estimate'. (cea_bridge bu çifti eşleyebiliyorsa canlı CEA yine
            # denenir — örn. hydrazine/h2o2 gibi tablo dışı ama kartı olan
            # çiftler.)
            self.combustion_data_source = 'conservative_estimate'
            self.combustion_validity = {
                'pc_range_ok': False, 'real_gas_warning': False,
                'extrapolated': True,
                'note': ('Propellant pair not in the built-in table; '
                         'conservative placeholder values.')}
            try:
                self._resolve_combustion_reference(None)
            except Exception:
                pass
            if self.combustion_data_source == 'conservative_estimate':
                self._warn(
                    f"Propellant pair {self.fuel_type}/{self.oxidizer_type} "
                    f"is not in the combustion database and could not be "
                    f"solved with CEA; conservative placeholder performance "
                    f"values are used.")

    # ------------------------------------------------------------------
    # CANLI CEA köprüsü (2026-07-22 Raptor entegrasyonu, denetim madde 1)
    # ------------------------------------------------------------------
    def _resolve_combustion_reference(self, table_props):
        """Yanma referanslarını GERÇEK (Pc, MR) CEA çözümüyle değiştirir.

        Sözleşme (cea_bridge.get_combustion_properties):
        * Vakum referansı VACUUM_REFERENCE_EPS (=200) alan oranında çözülür —
          statik tablonun "Area ratio 200:1" çapasıyla aynı sözleşme.
        * Deniz seviyesi Isp'si, CEA gamma'sıyla hesaplanan ortam-eşlenik
          (optimum) genişleme oranındaki ambient Isp'dir — tablonun
          "optimized expansion" sözleşmesinin karşılığı.
        * RocketCEA yoksa/başarısızsa statik tablo değerleri AYNEN korunur
          ve kaynak 'static_table' olarak etiketlenir (davranış değişmez).
        * Pc >= 300 bar'da cea_bridge real_gas_warning bayrağı kullanıcı
          uyarısına çevrilir (ideal-gaz CEA; fugasite düzeltmesi yok).

        Ayarlanan durum: isp_vac_ref / isp_sl_ref / c_star_ref / T_c /
        gamma_ref / mw / cp_chamber (varsa) + combustion_data_source,
        combustion_validity.
        """
        from hrma.engines import cea_bridge

        fallback = None
        if table_props is not None:
            fallback = {
                'c_star': table_props['c_star'], 'T_c': table_props['T_c'],
                'gamma': table_props['gamma'], 'mw': table_props['mw'],
                'isp_vac': table_props['isp_vac'],
                'isp_sl': table_props['isp_sl'],
                'cp_chamber': table_props.get('cp_chamber'),
            }

        # 1) Vakum referansı (eps = 200, tablo çapası sözleşmesi)
        vac = cea_bridge.get_combustion_properties(
            self.fuel_type, self.oxidizer_type, float(self.P_c),
            float(self.MR), expansion_ratio=VACUUM_REFERENCE_EPS,
            fallback=fallback)

        self.combustion_data_source = vac['source']
        self.combustion_validity = dict(vac.get('validity') or {})

        if vac['source'] != 'rocketcea':
            # Fallback yolu: tablo değerleri zaten atandı; yalnız kaynak ve
            # geçerlilik bayrakları raporlanır. 'not_modelled' ise (ne CEA ne
            # tablo) mevcut muhafazakâr değerler kalır ve çağıran uyarır.
            if vac['source'] == 'static_table':
                self._warn(
                    'RocketCEA is unavailable; combustion data comes from '
                    'the static Pc=100 bar anchor table (no chamber-pressure '
                    'dependence).')
            if self.combustion_validity.get('real_gas_warning'):
                self._warn_real_gas()
            return

        # 2) Deniz seviyesi: CEA gamma'sıyla ortam-eşlenik eps, ambient Isp
        g = float(vac['gamma_chamber'])
        try:
            m_opt = np.sqrt(2.0 / (g - 1.0)
                            * ((self.P_c / self.P_a) ** ((g - 1.0) / g) - 1.0))
            eps_sl = float(self._area_ratio_from_mach(max(m_opt, 1.0001), g))
            eps_sl = max(eps_sl, 1.6)
        except Exception:
            eps_sl = 16.0  # tablo yorumundaki tipik SL alan oranı (son çare)
        sl = cea_bridge.get_combustion_properties(
            self.fuel_type, self.oxidizer_type, float(self.P_c),
            float(self.MR), expansion_ratio=eps_sl,
            ambient_bar=float(self.P_a), fallback=fallback)

        isp_sl = sl.get('isp_sl_s')
        if isp_sl is None:
            # Ambient kestirimi başarısızsa: SL Isp = vakum Isp x CF oranı
            # yerine tablo değeri korunur (uydurma katsayı eklenmez).
            isp_sl = (fallback or {}).get('isp_sl')
            if isp_sl is None:
                # tablo da yoksa bu çift için SL referansı üretilemez
                self.combustion_data_source = 'not_modelled'
                self.combustion_validity['note'] = (
                    'Sea-level Isp could not be estimated (no ambient CEA '
                    'solution and no fallback table value).')
                return
            self._warn(
                'CEA ambient-Isp estimate failed; the sea-level Isp '
                'reference falls back to the static table value.')

        self.propellant_name = getattr(self, 'propellant_name',
                                       f"{self.fuel_type.upper()}/"
                                       f"{self.oxidizer_type.upper()}")
        self.isp_vac_ref = float(vac['isp_vac_s'])
        self.isp_sl_ref = float(isp_sl)
        self.c_star_ref = float(vac['c_star_m_s'])
        self.T_c = float(vac['tc_k'])
        self.gamma_ref = float(vac['gamma_chamber'])
        self.mw = float(vac['mw_g_mol'])
        if vac.get('cp_chamber'):
            self.cp_chamber = float(vac['cp_chamber'])
        self.sl_reference_expansion_ratio = eps_sl
        if self.combustion_validity.get('real_gas_warning'):
            self._warn_real_gas()

        # Tablo dışı çift CEA ile çözüldüyse temel alanların tamamı artık
        # tanımlı olmalı (isp/c* zinciri _calculate_mixture_ratio_effects
        # üzerinden kurulur).
        if table_props is None:
            self.optimal_mr = getattr(self, 'optimal_mr', float(self.MR))
            self.optimal_mr_thrust = getattr(self, 'optimal_mr_thrust',
                                             float(self.MR))
            self._calculate_mixture_ratio_effects()

    def _warn_real_gas(self):
        """Pc >= 300 bar ideal-gaz CEA uyarısı (kullanıcıya görünür)."""
        self._warn(
            f"Chamber pressure {self.P_c:g} bar is in the real-gas regime "
            f"(>= 300 bar): the CEA solution is ideal-gas (no fugacity / "
            f"real-gas correction); treat c*, Tc and Isp as upper-bound "
            f"estimates.")

    def _calculate_mixture_ratio_effects(self):
        """Calculate O/F ratio dependent performance (high precision)

        DENETIM DUZELTMESI (Bulgu 2 ve 3):
        - Eski 'correct_c_star_values' override'i kaldirildi: LH2/LOX icin 1580 m/s
          fiziksel olarak imkansizdi (kimyasal yakitlarin en yuksek c*'i ~2356 m/s,
          bu dosyanin kendi CEA tablosu). c* artik CEA referans tablosundan geliyor.
        - Eski Isp(O/F) polinomlari kendi CEA referanslarini asiyordu (RP1/LOX
          optimal MR'da 341.8 s vs CEA 311.8 s) ve MR'a gore monoton artiyordu.
          Polinomlar, CEA tablo degerine demirlenmis MR-sapma cezali interpolasyon
          ile degistirildi: deger optimal MR'da tablo referansina esit, sapmada
          kuadratik ceza ile azaliyor — referansi asla asmaz.
        """
        mr = self.MR

        # CANLI CEA yolu (2026-07-22): referanslar ZATEN gerçek (Pc, MR)
        # noktasının CEA çözümüdür — optimuma demirli kuadratik MR cezası
        # (eski vekil model) UYGULANMAZ; uygulanırsa gerçek CEA taramasının
        # üstüne ikinci (uydurma) bir ceza binerdi. gamma da aynı çözümden
        # gelir; polinom fit yalnız statik tablo yolunda kullanılır.
        if getattr(self, 'combustion_data_source', '') == 'rocketcea':
            self.gamma = float(self.gamma_ref)
            self.mr_efficiency = 1.0
            self.isp_sl = self.isp_sl_ref
            self.isp_vac = self.isp_vac_ref
            self.c_star = self.c_star_ref
            self.c_star_effective = self.c_star
            print(f"Effective C* set: {self.c_star_effective:.1f} m/s "
                  f"(RocketCEA at Pc={self.P_c:g} bar, MR={self.MR:g})")
            return

        # Ensure mixture ratio is within reasonable bounds
        mr_bounded = max(0.5, min(mr, 10.0))

        # Calculate gamma as function of O/F (polinom referansla uyumlu: rp1/lox
        # optimal MR'da 1.2158 vs CEA 1.2165)
        gamma_poly = np.poly1d(self.gamma_coeffs[::-1])
        self.gamma = max(1.1, min(1.4, gamma_poly(mr_bounded)))

        # Mixture ratio efficiency factor (kuadratik ceza, optimumda 1.0)
        mr_deviation = abs(mr_bounded - self.optimal_mr) / self.optimal_mr
        self.mr_efficiency = 1.0 - 0.15 * mr_deviation**2  # Quadratic penalty
        self.mr_efficiency = max(0.7, self.mr_efficiency)  # Minimum 70% efficiency

        # CEA tablo interpolasyonu: referans degerler optimal MR'daki CEA
        # cozumleridir (NASA RP-1311 / CEA); MR sapmasi kuadratik ceza ile
        # uygulanir. Boylece Isp ve c* hicbir MR'da CEA referansini asamaz.
        self.isp_sl = self.isp_sl_ref * self.mr_efficiency
        self.isp_vac = self.isp_vac_ref * self.mr_efficiency
        self.c_star = self.c_star_ref * self.mr_efficiency

        # CONSISTENCY FIX: Store effective C* for all throat calculations
        self.c_star_effective = self.c_star

        print(f"Effective C* set: {self.c_star_effective:.1f} m/s")
    
    def calculate_nozzle_geometry(self, altitude=0, convergence_tol=1e-8):
        """High-precision nozzle design with iterative area ratio calculation"""
        # Kullanıcı sabit genişleme oranı verdiyse Isp önce GERÇEK CF oranıyla
        # düzeltilir (bir kez); mdot ve boğaz alanı bu Isp'den türer.
        self._apply_nozzle_off_design_once()

        # Mass flow rate calculation with corrected Isp (EXPERT FIX)
        # g_0 hrma.constants'tan, BIPM standart 9.80665 m/s^2.
        g0_precise = G_0  # m/s^2 (exact, hrma.constants.G_0)

        # Use sea-level Isp with sea-level thrust for consistent mdot
        # (F_sl / Isp_vac mixes reference frames and undersizes throat)
        self.mdot_total = self.F / (self.isp_sl * g0_precise)
        self.mdot_ox = self.mdot_total * self.MR / (1 + self.MR)
        self.mdot_fuel = self.mdot_total / (1 + self.MR)
        
        # Input validation
        if self.mdot_total <= 0:
            raise ValueError("Mass flow rate must be positive")
        if self.MR <= 0:
            raise ValueError("Mixture ratio must be positive")
        if self.P_c <= 0:
            raise ValueError("Chamber pressure must be positive")
        
        # EXPERT FIX: Throat area calculation (eliminates 1000x multiplier bug)
        # Constants (hrma.constants'tan import edildi)
        # PA_PER_BAR ve G_0 modul basinda import edilmistir; tekrar tanimlanmaz.
        g0_precise = G_0  # m/s^2 (exact, hrma.constants.G_0)
        
        # CONSISTENCY FIX: Single throat discharge coefficient for all calculations
        # (DENETIM DUZELTMESI Bulgu 2: anahtar 'ch4' idi ama sinifin yakit adi
        # her yerde 'methane' — eslesme hic gerceklesmiyordu. Tablo artik
        # _throat_discharge_coefficient icinde, tek tanim yeri.)
        self.CD_throat = self._throat_discharge_coefficient()
        
        # Unit validation to prevent double conversion errors
        if not (0.70 <= self.CD_throat <= 1.0):
            raise ValueError(f"CD_throat out of range 0.70–1.0 (got {self.CD_throat})")
            
        # P_c is in bar, convert to Pa (NO DOUBLE CONVERSION!)
        P_c_pa = self.P_c * PA_PER_BAR
        
        # NASA CORRECT FORMULA: Throat area calculation
        # mdot = (A* * pt/sqrt[Tt]) * sqrt(gam/R) * [(gam + 1)/2]^-[(gam + 1)/(gam - 1)/2]
        # Solving for A_t:
        
        # Gas properties
        # R_universal birimi J/(kmol*K); MW birimi g/mol = kg/kmol -> R_specific J/(kg*K)
        R_specific = R_UNIVERSAL / self.mw  # J/(kg*K) (CODATA 2018)
        
        # NASA formula terms
        term1 = P_c_pa / np.sqrt(self.T_c)  # pt/sqrt(Tt)
        term2 = np.sqrt(self.gamma / R_specific)  # sqrt(gamma/R)
        exponent = -(self.gamma + 1) / (self.gamma - 1) / 2
        term3 = ((self.gamma + 1) / 2) ** exponent  # [(gamma + 1)/2]^-[(gamma + 1)/(gamma - 1)/2]
        
        # CONSISTENCY FIX: Use simplified throat area formula for all calculations
        # A_t = mdot_ana_oda × c_star_effective / (P_c[Pa] × CD_throat)
        # Açık çevrim muhasebesi (2026-07-22): mdot_total POMPALANAN toplam
        # debidir; gaz jeneratörü / tap-off türbin debisi ana odadan GEÇMEZ.
        # Boğaz, ana oda debisiyle boyutlanır: ṁ_ana = ṁ_toplam × kesir
        # (kesir = 1 − ṁ_türbin/ṁ_toplam, _apply_cycle_accounting kurar;
        # kapalı çevrimlerde 1.0). Sutton & Biblarz 9th ed., Ch. 6 açık
        # çevrim debi muhasebesi.
        mc_frac = float(getattr(self, '_main_chamber_flow_fraction', 1.0))
        self.mdot_main_chamber = self.mdot_total * mc_frac
        self.A_t = (self.mdot_main_chamber * self.c_star_effective
                    / (P_c_pa * self.CD_throat))
        self.d_t = 2.0 * np.sqrt(self.A_t / np.pi)  # Result in meters
        
        # Validation with safety limits
        if self.A_t <= 0:
            raise ValueError("Throat area must be positive")
        
        # NASA Real-time Validation (guarded; requires thrust_vac to be defined)
        try:
            from hrma.data.nasa_realtime_validator import NASARealtimeValidator
            validator = NASARealtimeValidator()
            
            # Motor tipini belirle
            motor_type = None
            if self.fuel_type.lower() == 'lh2' and self.oxidizer_type.lower() == 'lox':
                motor_type = 'RS-25'
            elif self.fuel_type.lower() == 'rp1' and self.oxidizer_type.lower() == 'lox':
                motor_type = 'F-1'
            
            if motor_type:
                thrust_for_validation = getattr(self, 'thrust_vac', None)
                if thrust_for_validation is None:
                    # Fallback to commanded thrust if vacuum thrust not yet computed
                    thrust_for_validation = self.F
                validation = validator.validate_motor_calculation(motor_type, self.d_t * 1000, thrust_for_validation, self.P_c)
                print(f"{validation['color']} NASA Validation: {validation['status']}")
                print(f"   Calculated: {validation['calculated_mm']:.1f} mm")
                print(f"   NASA Reference: {validation['nasa_reference_mm']:.1f} mm") 
                print(f"   Error: {validation['error_percent']:.2f}%")
                print(f"   {validation['recommendation']}")
                
        except ImportError:
            pass  # Validator not available
        
        # Import safety system
        try:
            from hrma.analysis.safety_limits import SafetyLimits
            safety = SafetyLimits()
            
            # Check throat diameter
            if not safety.check_throat_diameter(self.d_t, "Liquid Motor"):
                print(f"SAFETY WARNING: Throat diameter {self.d_t*1000:.1f} mm outside safe bounds")
                for violation in safety.violations:
                    if violation['parameter'].startswith('Throat Diameter'):
                        print(f"  Risk: {violation['risk']}")
                        
        except ImportError:
            # Fallback to basic validation
            if self.d_t < 0.001 or self.d_t > 2.0:  # 1mm - 2000mm range
                print(f"Warning: Unusual throat diameter: {self.d_t*1000:.1f} mm")
        
        # Atmospheric pressure at altitude — US Standard Atmosphere 1976.
        # v2.5.2 tekillestirmesi: eski uc dalli satir-ici kopya (20 km ustu
        # izotermal yaklasimi dahil) merkezi hrma.constants.isa_pressure
        # yardimcisiyla degistirildi. Yardimci TAM katman tablosunu kullanir,
        # yani 20 km ustunde +0.001 K/m lapse artik dogru modellenir.
        # NOT: G_0 modul seviyesinde import edilmistir; fonksiyon icinde tekrar
        # import edilirse Python G_0'i fonksiyon lokali sayar ve fonksiyonun
        # basindaki g0_precise = G_0 satiri UnboundLocalError verir (gizli bug
        # duzeltildi — G_0 import listesinden cikarildi).
        from hrma.constants import isa_pressure
        P_atm = isa_pressure(altitude)  # Pa

        # Convert to bar
        P_atm_bar = P_atm / 100000
        
        # Space vacuum conditions
        if altitude >= 100000:
            P_atm_bar = 1e-6
        
        self.P_e = P_atm_bar  # Exit pressure equals ambient
        
        # OPUS DENETİM DÜZELTMESİ (critical): Eski iç içe fsolve'daki
        # mach_area_relation formülü yanlıştı (M=1'de 1.30 veriyor, M ile
        # AZALIYORDU) → dış fsolve residual'ı işaret değiştirmediğinden
        # epsilon her koşulda başlangıç tahmini 20.0'da donuk kalıyordu.
        # Doğru yol kapalı-formdur (Sutton & Biblarz 9. baskı, Eq. 3-25/3-14;
        # solid_rocket_engine._expansion_ratio_from_pressure_ratio ile aynı):
        #   M_e = sqrt( 2/(γ-1) · [ (P_c/P_e)^((γ-1)/γ) − 1 ] )
        #   ε   = (1/M_e) · [ (2/(γ+1))·(1+(γ-1)/2·M_e²) ]^((γ+1)/(2(γ-1)))
        # (Eski kodda çıplak `gamma` adı NameError atıp bare-except'e
        # yutuluyordu — fsolve residual'ı hep 1e6 görüp seed'de kalıyordu.)
        g = float(self.gamma)
        try:
            pressure_ratio = self.P_c / max(self.P_e, 1e-9)
            M_e = np.sqrt(2.0 / (g - 1.0)
                          * (pressure_ratio ** ((g - 1.0) / g) - 1.0))
            M_e = max(M_e, 1.0001)  # süpersonik dal
            epsilon_optimal = (1.0 / M_e) * (
                (2.0 / (g + 1.0)) * (1.0 + (g - 1.0) / 2.0 * M_e ** 2)
            ) ** ((g + 1.0) / (2.0 * (g - 1.0)))
            epsilon_optimal = max(2.5, min(epsilon_optimal, 1000))
        except Exception:
            # Son çare: kaba yaklaşım (eski fallback korunuyor)
            pressure_ratio = self.P_c / max(self.P_e, 1e-9)
            epsilon_optimal = pressure_ratio ** (1/g) * ((g+1)/2) ** ((g+1)/(2*(g-1)))
            epsilon_optimal = max(4, min(epsilon_optimal, 300))

        # Kullanıcı genişleme oranı verdiyse lüle SABİTTİR: her irtifada aynı
        # ε kullanılır ve çıkış basıncı ε'dan izentropik olarak çözülür
        # (ortam basıncına eşitlenmez). Girdi yoksa eski davranış aynen kalır.
        eps_user = getattr(self, 'expansion_ratio_input', None)
        if eps_user is not None:
            self.expansion_ratio = float(eps_user)
            self.expansion_ratio_matched = epsilon_optimal
            pe_fixed = getattr(self, 'exit_pressure_fixed_bar', None)
            if pe_fixed is None:
                try:
                    _, pe_fixed = self._cf_at(self.expansion_ratio, P_atm_bar)
                except Exception:
                    pe_fixed = P_atm_bar
            self.P_e = float(pe_fixed)
        else:
            self.expansion_ratio = epsilon_optimal
            self.expansion_ratio_matched = epsilon_optimal
        self.A_e = self.A_t * self.expansion_ratio
        self.d_e = 2 * np.sqrt(self.A_e / np.pi)

        # Lüle uzunluğu: 15 derece konik referansın nozul tipine göre kısaltılmış
        # hali (Rao %80 / %60 bell; Sutton & Biblarz 9th ed., Fig. 3-14).
        geom = NOZZLE_TYPE_GEOMETRY.get(getattr(self, 'nozzle_type',
                                                NOZZLE_TYPE_DEFAULT),
                                        NOZZLE_TYPE_GEOMETRY[NOZZLE_TYPE_DEFAULT])
        l_conical_15 = (self.d_e - self.d_t) / (2 * np.tan(np.radians(15.0)))
        self.L_nozzle = l_conical_15 * geom['length_fraction']

        # Validate exit geometry
        if self.d_e > 5.0:  # 5m diameter warning
            print(f"Warning: Large exit diameter: {self.d_e:.2f} m")
        
        return {
            'throat_area': self.A_t,
            'throat_diameter': self.d_t,  # EXPERT FIX: Return in meters, not mm
            'exit_area': self.A_e, 
            'exit_diameter': self.d_e,  # EXPERT FIX: Return in meters, not mm
            'expansion_ratio': self.expansion_ratio,
            'nozzle_length': self.L_nozzle,  # EXPERT FIX: Return in meters, not mm
            'exit_pressure': self.P_e,  # bar
            'design_altitude': altitude  # m
        }
    
    def calculate_cooling_requirements(self):
        """High-precision cooling system analysis with advanced heat transfer"""
        # Advanced heat transfer calculations based on Bartz correlation

        # Süreç içi memo (2026-07-22): süperkritik istasyon marşı (CoolProp)
        # pahalıdır ve bu fonksiyon aynı koşuda birçok kez çağrılır
        # (_design_cooling_lines, _calculate_heat_flux, çevrim dengesi, ısıl
        # koruma). Girdi anahtarı değişmedikçe sonuç yeniden hesaplanmaz
        # (derin kopya döner — mutasyon izolasyonu).
        memo_key = (
            round(float(self.P_c), 9), round(float(self.T_c), 6),
            round(float(getattr(self, 'd_t', 0.0) or 0.0), 12),
            round(float(getattr(self, 'd_e', 0.0) or 0.0), 12),
            round(float(getattr(self, 'mdot_fuel', 0.0) or 0.0), 12),
            self.cooling_type, self.fuel_type,
            round(float(getattr(self, 'film_cooling_percent', 0.0)), 6),
            round(float(getattr(self, 'coolant_flow_fraction', 1.0)), 9),
            getattr(self, 'cooling_channels_input', None),
        )
        cached = getattr(self, '_cooling_memo', None)
        if cached is not None and cached[0] == memo_key:
            return copy.deepcopy(cached[1])

        # Engine geometry
        # DENETIM DUZELTMESI (Bulgu 5): eski kod chamber_length = c_star*1.2/1000
        # ile karakteristik HIZ c* (m/s) ile karakteristik UZUNLUK L*'i (m)
        # karistiriyordu (boyutsal olarak gecersiz, ~21x fazla uzunluk).
        # Dogru yontem: V_c = L* * A_t; L_chamber = V_c / A_c.
        # L* ve hazne çapı artık KULLANICI GİRDİSİNDEN gelir (2026-07-19
        # denetimi): characteristic_length ve contraction_ratio/chamber_diameter
        # alanları eskiden sessizce çöpe gidiyordu.
        L_star = self._l_star()
        chamber_diameter = self._chamber_diameter()  # m
        A_throat = np.pi * (self.d_t**2) / 4  # m²
        A_chamber_cross = np.pi * (chamber_diameter**2) / 4  # m² (hazne kesiti)
        chamber_volume = L_star * A_throat  # m³ (V_c = L* * A_t)
        chamber_length = chamber_volume / A_chamber_cross  # m
        nozzle_length = getattr(self, 'L_nozzle', (self.d_e - self.d_t) / (2 * np.tan(np.radians(15))))

        # Chamber heat transfer — tam Bartz korelasyonu (Bartz 1957; Sutton &
        # Biblarz 9th ed., Eq. 8-23):
        # h_g = (0.026/D_t^0.2)(mu^0.2 cp/Pr^0.6)(Pc/c*)^0.8(D_t/R_curv)^0.1(A_t/A)^0.9 * sigma

        # Gas properties at chamber conditions
        mu_g = self.mu_chamber  # Dynamic viscosity
        cp_g = self.cp_chamber  # Specific heat
        Pr_g = self.pr_chamber  # Prandtl number

        # Bartz correlation coefficients
        D_t = self.d_t  # Throat diameter
        # DENETIM DUZELTMESI (Bulgu 6): R parametresi Bartz'da bogaz egrilik
        # yaricapidir, hazne yaricapi degil. Bogaz giris egrilik yaricapi
        # tipik 1.5*R_t alinir (Huzel & Huang, "Modern Engineering for Design
        # of Liquid-Propellant Rocket Engines", boğaz konturu pratiği).
        R_curv = 1.5 * (D_t / 2)  # m, bogaz egrilik yaricapi
        Pc_atm = self.P_c * 1e5  # Chamber pressure in Pa

        # Sıcak/soğuk cidar sıcaklıkları: KULLANICI max_wall_temp verirse o
        # kullanılır (eskiden soğutma tipine gömülü sabitti ve girdi yok
        # sayılıyordu — 2026-07-19 denetimi).
        T_wall_hot, T_wall_cold = self._wall_temperatures()

        # DENETIM DUZELTMESI (Bulgu 6): Bartz sinir tabakasi ozellik duzeltme
        # faktoru sigma eklendi (Bartz 1957, Eq. 7; Sutton 9th ed. Eq. 8-23):
        # sigma = 1 / { [0.5(T_w/T_0)(1+(g-1)/2 M^2)+0.5]^0.68 [1+(g-1)/2 M^2]^0.12 }
        gamma_g = self.gamma
        Tw_T0 = T_wall_hot / self.T_c

        def bartz_sigma(mach):
            """Bartz sınır tabakası özellik düzeltme faktörü (Bartz 1957)."""
            m_term = 1.0 + (gamma_g - 1.0) / 2.0 * mach**2
            return 1.0 / ((0.5 * Tw_T0 * m_term + 0.5)**0.68 * m_term**0.12)

        sigma_throat = bartz_sigma(1.0)   # bogazda M=1
        sigma_chamber = bartz_sigma(0.0)  # haznede M~0

        # Heat transfer coefficient at throat (highest heat flux)
        h_g_throat = (0.026 / (D_t**0.2)) * ((mu_g**0.2 * cp_g) / (Pr_g**0.6)) * \
                     ((Pc_atm / self.c_star)**0.8) * ((D_t / R_curv)**0.1) * sigma_throat

        # Heat transfer coefficient variation along nozzle
        # h_g(x) = h_g_throat * (A_t / A(x))^0.9  (Bartz alan olceklemesi)

        # Chamber heat transfer area and load
        A_chamber = np.pi * chamber_diameter * chamber_length

        # DENETIM DUZELTMESI (Bulgu 6): hazne katsayisi sabit 0.7 yerine Bartz
        # alan olceklemesi (A_t/A_c)^0.9 (daralma orani 12.25 icin ~0.105).
        h_g_chamber = h_g_throat * ((A_throat / A_chamber_cross)**0.9) * \
                      (sigma_chamber / sigma_throat)

        # DENETIM DUZELTMESI (Bulgu 6): surucu sicaklik statik T degil adyabatik
        # duvar (recovery) sicakligi olmali. Haznede M~0 oldugundan T_aw ~ T_c.
        # Recovery faktoru r = Pr^(1/3) (turbulent; Bartz 1957 / NASA SP-8124).
        r_recovery = Pr_g ** (1.0 / 3.0)

        # Chamber heat flux (haznede T_aw ~ T_c, M~0)
        q_dot_chamber = h_g_chamber * (self.T_c - T_wall_hot)  # W/m²
        Q_chamber = q_dot_chamber * A_chamber  # W
        
        # --- Lüle ısı transferi (yakınsak + ıraksak, ayrı uzunluklarla) -----
        # v2.5.2 DÜZELTMESİ (Codex bulgusu, liquid:1480): eski döngü
        # `nozzle_length`in (= self.L_nozzle) ilk %30'unu YAKINSAK, kalan
        # %70'ini IRAKSAK sayıyordu. Oysa L_nozzle boğazdan ÇIKIŞA kadar olan
        # ıraksak uzunluktur; yakınsak koni onun içinde değildir. Sonuç:
        # yakınsak bölüm gerçekte olduğundan kısa, ıraksak bölüm ise %30
        # eksik modelleniyor, ısı yükü/soğutucu sıcaklık artışı/kanal basınç
        # düşümü hep yanlış çıkıyordu.
        # Yeni model:
        #   L_conv = (D_ch − D_t) / (2·tan(θ_conv))   (θ_conv = 30°, nozzle_angles
        #            ile AYNI değer — tek tanım yeri CONVERGENT_HALF_ANGLE_DEG)
        #   L_div  = self.L_nozzle                    (boğaz → çıkış)
        # Alan elemanı konik yüzey (frustum) formülüyle: dA = π·(D1+D2)/2·s,
        # s = √(dx² + ((D2−D1)/2)²) EĞİK uzunluk. Eski dA = π·D·dx eksen
        # uzunluğunu kullanıyordu, bu da yüzeyi eğim kadar küçük gösteriyordu
        # (Sutton & Biblarz 9th ed., Böl. 8; kesik koni yanal alanı).
        n_segments = 20  # her bölüm için sayısal integrasyon dilimi
        L_conv = (chamber_diameter - D_t) / (
            2.0 * np.tan(np.radians(CONVERGENT_HALF_ANGLE_DEG)))
        L_conv = max(L_conv, 0.0)
        L_div = float(nozzle_length)
        A_t_geom = np.pi * (D_t ** 2) / 4.0

        def _diameter_at(section, frac):
            """Bölüm içindeki yerel çap (frac: 0..1, koni doğrusal)."""
            if section == 'conv':
                return chamber_diameter - (chamber_diameter - D_t) * frac
            return D_t + (self.d_e - D_t) * frac

        Q_nozzle = 0.0
        A_nozzle_total = 0.0
        for section, L_section in (('conv', L_conv), ('div', L_div)):
            if L_section <= 0:
                continue
            dx = L_section / n_segments
            for i in range(n_segments):
                D1 = _diameter_at(section, i / n_segments)
                D2 = _diameter_at(section, (i + 1) / n_segments)
                D_local = 0.5 * (D1 + D2)
                A_local = np.pi * (D_local ** 2) / 4.0

                # Local temperature (isentropic expansion)
                if A_local > A_t_geom:  # Downstream of throat
                    area_ratio_local = A_local / A_t_geom
                    # Simplified temperature ratio
                    T_ratio = 1 / (1 + (self.gamma - 1) * 0.1 * np.log(area_ratio_local))
                    T_local = self.T_c * T_ratio
                else:
                    T_local = self.T_c  # Upstream of throat

                # Local heat transfer coefficient
                # DENETIM DUZELTMESI (Bulgu 6): Bartz eksenel olcekleme (A_t/A)^0.9
                # (Bartz 1957; Sutton 9th ed. Eq. 8-23). Eski (T_c/T)^0.68 carpani
                # Bartz formunda yoktur; sicaklik etkisi sigma icinde tasinir.
                area_ratio = A_t_geom / A_local
                h_g_local = h_g_throat * (area_ratio**0.9)

                # DENETIM DUZELTMESI (Bulgu 6): surucu sicaklik statik T degil
                # adyabatik duvar (recovery) sicakligi (Bartz 1957 / NASA SP-8124):
                # T_aw = T + r*(T_c - T), r = Pr^(1/3) ~ 0.9 -> bogazda T_aw ~ 0.9*T_c
                T_aw_local = T_local + r_recovery * (self.T_c - T_local)

                # Kesik koni yanal alani: pi*(D1+D2)/2 * egik uzunluk
                slant = np.sqrt(dx ** 2 + (0.5 * (D2 - D1)) ** 2)
                dA = np.pi * 0.5 * (D1 + D2) * slant
                q_dot_local = h_g_local * (T_aw_local - T_wall_hot)
                Q_nozzle += q_dot_local * dA
                A_nozzle_total += dA

        # Soğutulan eksenel uzunluk: hazne + yakınsak koni + ıraksak koni
        nozzle_axial_length = L_conv + L_div

        total_heat_load = Q_chamber + Q_nozzle

        # --- Film soğutma (2026-07-22, denetim madde 6) --------------------
        # Eski ölü bayrak (self.film_cooling hiç set edilmiyordu) kaldırıldı;
        # film_cooling_percent girdisi enerji dengesi modeline bağlandı.
        film = self._film_cooling_analysis(
            q_dot_chamber, chamber_diameter, chamber_length)
        film_cooling_flow = film['film_cooling_flow_kg_s']
        # Film tarafından yutulan ısı rejeneratif soğutucuya GELMEZ
        # (enerji dengesi; Huzel & Huang Ch. 4 film soğutma muhasebesi).
        heat_to_regen = max(total_heat_load - film['film_heat_absorbed_w'],
                            0.0)

        # Cooling system sizing
        coolant_flow = 0
        pressure_drop = 0
        coolant_temp_rise = 0

        # Kanal sayısı/kesiti: kullanıcı girdisi ya da hazne çevresinden
        # hesap (sabit 80 değil — 2026-07-19 denetimi).
        n_channels, channel_width, channel_height, channel_source = \
            self._cooling_channel_geometry()
        v_coolant = 0.0
        reynolds = 0.0
        # Süperkritik istasyon-marşlı çözüm sonucu (metan/LH2 rejeneratif).
        regen_march = None
        peak_heat_flux_kw = None   # marş çözerse oradan, yoksa Bartz'tan
        wall_temp_source = ('user input (max wall temperature)'
                            if getattr(self, 'max_wall_temp_input', None)
                            is not None else
                            'assumed (cooling-type default)')
        if self.cooling_type in ('regenerative', 'film_cooling', 'dump_cooling'):
            # Use fuel as coolant (most common)
            coolant_flow_fraction = getattr(self, 'coolant_flow_fraction',
                                            COOLANT_FLOW_FRACTION_DEFAULT)
            coolant_flow = self.mdot_fuel * coolant_flow_fraction

            # Fuel properties for cooling
            # (2026-07-22: metan/LH2 için bu NBP sabitleri yalnız süperkritik
            # istasyon marşı KURULAMADIĞINDA yedek olarak kalır; marş
            # kurulursa cp/yoğunluk/viskozite CoolProp (T,P) bağımlıdır ve
            # cidar sıcaklığı ÇÖZÜLÜR — denetim bulgusu 2e.)
            if self.fuel_type == 'rp1':
                cp_coolant = 2090  # J/kg·K
                rho_coolant = 815   # kg/m³
                mu_coolant = 0.0012 # Pa·s
            elif self.fuel_type == 'lh2':
                cp_coolant = 14300  # Very high specific heat
                rho_coolant = 71
                mu_coolant = 0.000013
            elif self.fuel_type == 'methane':
                cp_coolant = 3480
                rho_coolant = 423
                mu_coolant = 0.00011
            else:
                cp_coolant = 2000  # Default
                rho_coolant = 800
                mu_coolant = 0.001

            # Kullanıcı yakıt özelliklerini girdiyse tablo değerini EZER.
            if getattr(self, 'cp_coolant_input', None) is not None:
                cp_coolant = self.cp_coolant_input
            if getattr(self, 'mu_fuel', None) is not None:
                mu_coolant = self.mu_fuel
            rho_coolant = self.rho_fuel

            # Temperature rise calculation (film kredisi düşülmüş yük)
            coolant_temp_rise = heat_to_regen / (coolant_flow * cp_coolant)

            # Kanal boyu: hazne + YAKINSAK koni + ıraksak koni (eski hâli
            # yakınsak koniyi hiç saymıyordu; basınç düşümü bu uzunlukla
            # doğru orantılı olduğundan sistematik olarak düşük çıkıyordu).
            channel_length = chamber_length + nozzle_axial_length

            # Kanal DERİNLİĞİ tasarım serbestliğidir (formda girdisi yok):
            # varsayılan kesitle hız tasarım hedefini aşıyorsa derinlik
            # hedefe göre büyütülür (üst sınıra kadar) ve etiketlenir —
            # büyük motorlarda 2 mm sabit derinlik fiziksel olmayan
            # 300+ m/s hızlar ve binlerce bar ΔP üretiyordu (2026-07-22).
            v_probe = coolant_flow / (n_channels * rho_coolant
                                      * channel_width * channel_height)
            if v_probe > COOLANT_CHANNEL_TARGET_VELOCITY_MS:
                h_target = coolant_flow / (
                    n_channels * rho_coolant * channel_width
                    * COOLANT_CHANNEL_TARGET_VELOCITY_MS)
                h_new = min(max(h_target, channel_height),
                            COOLING_CHANNEL_HEIGHT_MAX_M)
                if h_new > channel_height:
                    channel_height = h_new
                    channel_source += (
                        '; channel height auto-sized for the '
                        f'{COOLANT_CHANNEL_TARGET_VELOCITY_MS:.0f} m/s '
                        'design velocity target (Huzel & Huang Ch. 4)')

            # Hydraulic diameter
            D_h = 4 * (channel_width * channel_height) / (2 * (channel_width + channel_height))

            # Reynolds number
            v_coolant = coolant_flow / (n_channels * rho_coolant * channel_width * channel_height)
            Re = rho_coolant * v_coolant * D_h / mu_coolant
            reynolds = Re

            # Sürtünme katsayısı: Haaland (1983) açık bağıntısı — kanal
            # pürüzlülüğü (chamber_roughness girdisi) artık hesaba giriyor.
            # White, "Fluid Mechanics" 7th ed., Eq. 6.49; laminer Eq. 6.12.
            rel_rough = getattr(self, 'channel_roughness_m',
                                COOLING_CHANNEL_ROUGHNESS_DEFAULT_M) / D_h
            if Re > 2300:
                f = (-1.8 * np.log10(6.9 / max(Re, 1.0)
                                     + (rel_rough / 3.7) ** 1.11)) ** -2
            else:
                f = 64 / max(Re, 1e-6)  # Laminar flow

            # Pressure drop
            pressure_drop = (f * rho_coolant * (v_coolant**2) * channel_length) / (2 * D_h)
            pressure_drop /= 1e5  # Convert Pa to bar

            # --- Süperkritik metan/LH2: 1B istasyon-marşlı EŞ-ÇÖZÜM -------
            # (2026-07-22, denetim madde 4 / bulgu 2e). Sabit cp=3480 toplu
            # ΔT hesabı ve varsayılan 800 K cidar yerine RegenCooling
            # Jackson korelasyonlu marşı: cidar sıcaklığı ÇÖZÜLÜR, soğutucu
            # özellikleri CoolProp (T,P) bağımlıdır, ΔP sürtünme+ivmelenme
            # içerir. Marş kurulamazsa (CoolProp aralık dışı, ceket
            # kapanmıyor) yukarıdaki yedek zincir kalır ve durum AÇIKÇA
            # raporlanır — sahte sayı üretilmez.
            if (self.cooling_type == 'regenerative'
                    and self.fuel_type in ('methane', 'lh2')):
                try:
                    regen_march = self._solve_supercritical_regen(
                        coolant_flow, n_channels, channel_width,
                        channel_height)
                except Exception as exc:
                    regen_march = None
                    self._warn(
                        f"Supercritical {self.fuel_type} regenerative march "
                        f"could not be solved ({exc}); the lumped NBP-"
                        f"property estimate is reported instead and the "
                        f"wall temperature remains an assumption.")
                if regen_march is not None:
                    s = regen_march['summary']
                    # Toplam yük/tepe akı/ΔT/ΔP/cidar: marştan (tek kaynak).
                    # Hazne/lüle payı marş toplamına oranla ölçeklenir
                    # (bölüşüm legacy integralin şeklinden, toplam marştan).
                    scale = (s['total_heat_W'] / total_heat_load
                             if total_heat_load > 0 else 1.0)
                    Q_chamber *= scale
                    Q_nozzle *= scale
                    total_heat_load = s['total_heat_W']
                    heat_to_regen = total_heat_load
                    coolant_temp_rise = s['coolant_dT_K']
                    pressure_drop = s['total_pressure_drop_bar']
                    v_coolant = s['max_coolant_velocity_m_s']
                    reynolds = s['min_reynolds']
                    T_wall_hot = s['max_wall_hot_K']
                    T_wall_cold = s['max_wall_cold_K']
                    peak_heat_flux_kw = s['peak_heat_flux_MW_m2'] * 1000.0
                    wall_temp_source = ('solved (1D supercritical station '
                                        'march, Jackson correlation)')
                    for w in s.get('warnings', []):
                        self._warn(f"Regen march: {w}")

        elif self.cooling_type == 'ablative':
            # Ablative cooling - no active coolant flow
            ablative_thickness = 0.01  # 10mm ablative liner
            ablative_recession_rate = 0.1e-3  # 0.1 mm/s typical
            
        # Kanal hızı / basınç düşümü pratik sınırların üstündeyse uyarılır
        # (hesap yine yapılır — kullanıcı kanal sayısını/kesitini görsün).
        if coolant_flow > 0:
            if v_coolant > COOLANT_VELOCITY_LIMIT_MS:
                self._warn(
                    f"Coolant channel velocity {v_coolant:.0f} m/s exceeds the "
                    f"{COOLANT_VELOCITY_LIMIT_MS:.0f} m/s practical limit for "
                    f"{n_channels} channels of "
                    f"{channel_width * 1000:.1f} x {channel_height * 1000:.1f} "
                    f"mm; increase the channel count or section.")
            if pressure_drop > COOLANT_DP_FRACTION_LIMIT * self.P_c:
                self._warn(
                    f"Coolant pressure drop {pressure_drop:.1f} bar is "
                    f"{pressure_drop / max(self.P_c, 1e-9) * 100:.0f}% of the "
                    f"chamber pressure; the feed system would have to supply "
                    f"it on top of the injector drop.")

        # Soğutucu çıkış sıcaklığı kaynama noktasını aşıyorsa sessiz kalınmaz
        # (girdi: fuel_boiling_point; tek fazlı akış varsayımı bozulur).
        t_exit = getattr(self, 'coolant_inlet_temp',
                         COOLANT_INLET_TEMP_DEFAULT_K) + coolant_temp_rise
        t_boil = getattr(self, 'fuel_boiling_point', None)
        if t_boil is not None and coolant_flow > 0 and t_exit > t_boil:
            self._warn(
                f"Coolant exit temperature {t_exit:.0f} K exceeds the entered "
                f"fuel boiling point {t_boil:.0f} K; the single-phase cooling "
                f"model no longer applies at the channel outlet.")

        result = {
            'total_heat_load': total_heat_load / 1000,  # kW
            'chamber_heat_load': Q_chamber / 1000,  # kW
            'nozzle_heat_load': Q_nozzle / 1000,  # kW
            # OPUS DENETİM DÜZELTMESİ (minor): tepe akı BOĞAZDADIR, haznede
            # değil (Bartz alan ölçeklemesi (At/A)^0.9 boğazda 1'e gider).
            # 2026-07-22: süperkritik marş çözüldüyse tepe akı ORADAN gelir
            # (çözülmüş cidarla eş-çözüm), yoksa Bartz varsayılan cidarla.
            'peak_heat_flux': (peak_heat_flux_kw
                               if peak_heat_flux_kw is not None
                               else h_g_throat * (self.T_c - T_wall_hot)
                               / 1000),  # kW/m² (boğaz)
            'chamber_heat_flux': q_dot_chamber / 1000,  # kW/m²
            'coolant_flow_rate': coolant_flow,  # kg/s
            'coolant_temperature_rise': coolant_temp_rise,  # K
            'cooling_pressure_drop': pressure_drop,  # bar
            'wall_temperature_hot': T_wall_hot,  # K
            'wall_temperature_cold': T_wall_cold,  # K
            # 2026-07-22 (denetim madde 3): cidar sıcaklığının VARSAYIM mı
            # ÇÖZÜM mü olduğu artık açıkça raporlanır.
            'wall_temperature_source': wall_temp_source,
            'chamber_diameter': chamber_diameter * 1000,  # mm
            'chamber_length': chamber_length * 1000,  # mm
            'nozzle_length': nozzle_length * 1000,  # mm (ıraksak: boğaz→çıkış)
            # v2.5.2: soğutma entegrasyonunun GERÇEKTEN kapsadığı geometri
            # açıkça raporlanır (eski model yakınsak koniyi L_nozzle'ın
            # içinden çalıyordu; kullanıcı hangi yüzeyin soğutulduğunu
            # göremiyordu).
            'convergent_length': L_conv * 1000,  # mm (boğaz öncesi koni)
            'divergent_length': L_div * 1000,  # mm (boğaz→çıkış)
            'convergent_half_angle_deg': CONVERGENT_HALF_ANGLE_DEG,
            'cooled_channel_length': (chamber_length + nozzle_axial_length) * 1000,  # mm
            'chamber_surface_area': A_chamber,  # m² (hazne silindiri)
            'nozzle_surface_area': A_nozzle_total,  # m² (koni yanal, eğik uzunlukla)
            'cooling_channels': n_channels if coolant_flow > 0 else 0,
            'channel_width_mm': channel_width * 1000,
            'channel_height_mm': channel_height * 1000,
            'channel_count_source': channel_source,
            'coolant_velocity': v_coolant,  # m/s (kanal içi, hesaplanmış)
            'coolant_reynolds': reynolds,
            'coolant_inlet_temperature': getattr(
                self, 'coolant_inlet_temp', COOLANT_INLET_TEMP_DEFAULT_K),  # K
            'coolant_exit_temperature': getattr(
                self, 'coolant_inlet_temp',
                COOLANT_INLET_TEMP_DEFAULT_K) + coolant_temp_rise,  # K
            'coolant_flow_fraction': getattr(
                self, 'coolant_flow_fraction', COOLANT_FLOW_FRACTION_DEFAULT),
            'l_star': L_star,  # m
            'contraction_ratio': (chamber_diameter / self.d_t) ** 2,
            'bartz_coefficient': h_g_throat,  # W/m²·K
            'film_cooling_flow': film_cooling_flow,  # kg/s
            # --- Film soğutma dökümü (2026-07-22, madde 6) ---
            'film_cooling': film,
            'heat_load_to_regen_coolant': heat_to_regen / 1000,  # kW
        }
        if regen_march is not None:
            # Süperkritik marş özeti + istasyon dizileri (UI grafiği için).
            result['regen_supercritical'] = {
                'summary': regen_march['summary'],
                'model_note': regen_march['model_note'],
                'jacket_expansion_ratio': regen_march['jacket_eps'],
                'jacket_note': regen_march['jacket_note'],
                'inlet_temp_K': regen_march['inlet_temp_K'],
                'inlet_pressure_bar': regen_march['inlet_pressure_bar'],
                'inlet_pressure_basis': regen_march['inlet_pressure_basis'],
                'coolant_correlation':
                    regen_march['summary'].get('coolant_correlation'),
            }
            result['coolant_inlet_temperature'] = regen_march['inlet_temp_K']
            result['coolant_exit_temperature'] = (
                regen_march['summary']['coolant_exit_temp_K'])
            result['coolant_exit_pressure_bar'] = (
                regen_march['summary']['coolant_exit_pressure_bar'])
        else:
            if (self.cooling_type == 'regenerative'
                    and self.fuel_type in ('methane', 'lh2')):
                result['regen_supercritical'] = 'not_modelled'

        self._cooling_memo = (memo_key, copy.deepcopy(result))
        return result

    def _film_cooling_analysis(self, q_dot_chamber, chamber_diameter,
                               chamber_length):
        """Film soğutma enerji dengesi (2026-07-22, denetim madde 6).

        Model — Huzel & Huang Ch. 4 sıvı film soğutma tasarım muhasebesi:
        film debisinin birim kütle ısı alma kapasitesi, hazne duvarına gelen
        akıyla karşılaştırılır; film TÜKENENE kadar duvarı korur:

            L_film = ṁ_film · Δh_film / (q_hazne · π · D_hazne)

        Δh_film (yutulabilir entalpi):
        * CH4/LH2: CoolProp GERÇEK entalpi farkı h(T_limit, Pc) − h(T_in, Pc)
          — süperkritik oda basıncında faz geçişi yoktur, gizli ısı ayrı
          terim olarak eklenmez (Bell et al. 2014, CoolProp).
        * RP-1: CoolProp'ta yok; duyulur ısı cp·ΔT alt sınırı kullanılır
          (MIL-DTL-25576 sıvı cp) ve buharlaşma katkısı 'not_modelled'
          olarak beyan edilir (muhafazakâr).
        T_limit = sıcak cidar hedef sıcaklığı (film cidarı korurken cidar
        hedefinden sıcak olamaz). Film tükenişi SONRASI gaz-film etkinliği
        (adyabatik duvar sıcaklığı sönümü) modellenmez ve açıkça söylenir
        (NASA SP-8124 kapsamındaki korelasyon ayrı iştir).
        """
        pct = float(getattr(self, 'film_cooling_percent', 0.0) or 0.0)
        out = {
            'film': 'none' if pct <= 0 else 'liquid-film energy balance',
            'film_cooling_percent': pct,
            'film_cooling_flow_kg_s': 0.0,
            'film_heat_absorbed_w': 0.0,
            'film_covered_length_mm': 0.0,
            'film_coverage_fraction_of_chamber': 0.0,
            'downstream_gas_film_effectiveness': 'not_modelled',
            'model': ('film coolant heat-sink energy balance '
                      '(Huzel & Huang Ch. 4); real-gas enthalpies from '
                      'CoolProp for CH4/H2, sensible-heat lower bound '
                      'for RP-1'),
        }
        if pct <= 0:
            return out

        mdot_film = pct / 100.0 * float(self.mdot_fuel)
        t_in = float(getattr(self, 'coolant_inlet_temp',
                             COOLANT_INLET_TEMP_DEFAULT_K))
        t_limit, _ = self._wall_temperatures()
        pc_pa = float(self.P_c) * PA_PER_BAR

        dh = None
        basis = None
        fluid = COOLPROP_FLUID_NAME.get(self.fuel_type)
        if fluid is not None:
            try:
                import CoolProp.CoolProp as CP
                t_max_eos = float(CP.PropsSI('Tmax', fluid))
                t_hi = min(float(t_limit), t_max_eos - 1.0)
                dh = (CP.PropsSI('H', 'T', t_hi, 'P', pc_pa, fluid)
                      - CP.PropsSI('H', 'T', max(t_in, 60.0), 'P', pc_pa,
                                   fluid))
                basis = (f'CoolProp real-gas enthalpy rise {t_in:.0f} K -> '
                         f'{t_hi:.0f} K at Pc')
            except Exception:
                dh = None
        if dh is None:
            cp_l = FILM_COOLANT_CP_FALLBACK_J_KGK.get(
                self.fuel_type, float(getattr(self, 'cp_coolant_input', None)
                                      or 2000.0))
            dh = cp_l * max(t_limit - t_in, 0.0)
            basis = (f'sensible heat cp*(T_wall_target - T_in) lower bound '
                     f'(cp={cp_l:.0f} J/kgK); vaporization credit '
                     f'not_modelled')
        if dh <= 0:
            self._warn('Film cooling analysis: no absorbable enthalpy '
                       '(inlet temperature at/above the wall target); film '
                       'credit is zero.')
            return out

        # Film hazne silindirini enjektör yüzünden itibaren korur.
        q_wall = max(float(q_dot_chamber), 1.0)   # W/m²
        capacity_w = mdot_film * dh               # W
        l_film = capacity_w / (q_wall * np.pi * max(chamber_diameter, 1e-6))
        coverage = min(l_film / max(chamber_length, 1e-9), 1.0)
        absorbed = q_wall * np.pi * chamber_diameter * min(l_film,
                                                           chamber_length)

        out.update({
            'film_cooling_flow_kg_s': mdot_film,
            'film_heat_absorbed_w': float(absorbed),
            'film_covered_length_mm': float(min(l_film, chamber_length)
                                            * 1000.0),
            'film_unclipped_length_mm': float(l_film * 1000.0),
            'film_coverage_fraction_of_chamber': float(coverage),
            'film_enthalpy_basis': basis,
            'film_absorbable_enthalpy_J_kg': float(dh),
        })
        if coverage < 1.0:
            self._warn(
                f"Film cooling flow ({pct:g}% of fuel) protects only "
                f"{coverage * 100:.0f}% of the chamber barrel length; the "
                f"remaining wall relies on the primary cooling circuit.")
        return out

    def _solve_supercritical_regen(self, coolant_flow, n_channels,
                                   channel_width, channel_height):
        """Metan/LH2 rejeneratif ceketin 1B süperkritik istasyon marşı.

        RegenCooling (Jackson korelasyonu + CoolProp gerçek gaz + entalpi
        marşı + fin modeli) ile ÇÖZÜLMÜŞ cidar sıcaklığı, soğutucu çıkış
        durumu ve kanal ΔP'si döner. Girdi sözleşmesi:

        * Ceket kapsamı: ε = min(lüle ε'su, REGEN_JACKET_EPS_MAX) — ana oda
          ceketi pratiği (Sutton Ch. 8); lüle bunun ötesine uzuyorsa o bölge
          bu modelde soğutulmaz ve jacket_note ile beyan edilir.
        * Kanal giriş basıncı: REGEN_CHANNEL_INLET_PRESSURE_FACTOR × Pc
          (etiketli varsayım; sonuç ΔP pompa zincirine ayrıca işlenir).
        * Giriş sıcaklığı: kullanıcı kriyojenik-dışı form varsayılanını
          (300 K) değiştirmediyse CRYO_COOLANT_INLET_DEFAULT_K kullanılır ve
          uyarı üretilir (300 K metan/LH2 pompa çıkışı fiziksel değildir).
        """
        from hrma.analysis.regen_cooling import RegenCooling

        coolant_key = {'methane': 'methane', 'lh2': 'hydrogen'}[self.fuel_type]

        t_in = getattr(self, 'coolant_inlet_temp',
                       COOLANT_INLET_TEMP_DEFAULT_K)
        cryo_default = CRYO_COOLANT_INLET_DEFAULT_K.get(self.fuel_type)
        if cryo_default is not None and (
                t_in is None
                or abs(float(t_in) - COOLANT_INLET_TEMP_DEFAULT_K) < 1e-9):
            # Form her zaman 300 K yolluyor; kriyojenik yakıtta bu değer
            # 'düşünülmemiş varsayılan' kabul edilir ve NBP+pompa ısınması
            # varsayılanına çekilir (kullanıcı 300 K'yi BİLEREK istiyorsa
            # 300'den farklı ama yakın bir değer girebilir).
            if t_in is not None:
                self._warn(
                    f"Coolant inlet temperature left at the generic 300 K "
                    f"form default; for {self.fuel_type} the cryogenic pump "
                    f"discharge default {cryo_default:g} K is used instead "
                    f"(NIST NBP + pump heating).")
            t_in = cryo_default
        t_in = float(t_in)

        p_in_bar = REGEN_CHANNEL_INLET_PRESSURE_FACTOR * float(self.P_c)
        eps_jacket = min(float(self.expansion_ratio), REGEN_JACKET_EPS_MAX)
        jacket_note = (
            'regenerative jacket modelled to expansion ratio '
            f'{eps_jacket:g}; ' + (
                f'the nozzle extension beyond it (to {self.expansion_ratio:.0f}) '
                'is NOT cooled by this model (radiative/film extension '
                'not modelled).' if self.expansion_ratio > eps_jacket + 1e-9
                else 'the full nozzle is inside the jacket.'))

        material, mat_key = self._material_record()
        rc = RegenCooling(
            chamber_pressure=float(self.P_c) * PA_PER_BAR,
            chamber_temperature=float(self.T_c),
            gamma=float(self.gamma),
            molecular_weight=float(self.mw),
            throat_diameter=float(self.d_t),
            expansion_ratio=eps_jacket,
            coolant=coolant_key,
            coolant_mdot=max(float(coolant_flow), 1e-6),
            coolant_inlet_temp=t_in,
            coolant_inlet_pressure=p_in_bar * PA_PER_BAR,
            n_channels=int(n_channels),
            channel_width=float(channel_width),
            channel_height=float(channel_height),
            wall_thickness=REGEN_LINER_THICKNESS_M,
            wall_material=mat_key,
            wall_roughness=float(getattr(
                self, 'channel_roughness_m',
                COOLING_CHANNEL_ROUGHNESS_DEFAULT_M)),
            motor_data={'chamber_diameter': self._chamber_diameter(),
                        'mdot_total': float(self.mdot_total),
                        'nozzle_type': getattr(self, 'nozzle_type',
                                               NOZZLE_TYPE_DEFAULT)},
        )
        march = rc.solve()
        march['jacket_eps'] = eps_jacket
        march['jacket_note'] = jacket_note
        march['inlet_temp_K'] = t_in
        march['inlet_pressure_bar'] = p_in_bar
        march['inlet_pressure_basis'] = (
            f'{REGEN_CHANNEL_INLET_PRESSURE_FACTOR:g} x Pc assumption '
            '(pump discharge to injector; Sutton Ch. 6 cycle schematics)')
        return march

    def calculate_injector_design(self):
        """High-precision injector design with advanced fluid mechanics"""
        
        # Advanced injector design based on web-validated propellant properties
        fuel_props = self.web_propellant_data.get(self.fuel_type, {})
        ox_props = self.web_propellant_data.get(self.oxidizer_type, {})
        
        # Use web data for viscosity if available
        fuel_viscosity = fuel_props.get('viscosity', 0.001)  # Pa·s
        ox_viscosity = ox_props.get('viscosity', 0.0005)  # Pa·s
        
        if self.injector_type == 'impinging':
            # NASA-validated impinging jet design
            injection_angle = 60  # degrees between jets
            
            # Realistic injection velocities from flight data
            if self.fuel_type == 'rp1' and self.oxidizer_type == 'lox':
                # Falcon 9 Merlin heritage
                v_fuel_base = 18  # m/s (verified)
                v_ox_base = 28   # m/s (verified)
            elif self.fuel_type == 'lh2' and self.oxidizer_type == 'lox':
                # SSME heritage data
                v_fuel_base = 35  # Higher for low density H2
                v_ox_base = 25   # LOX through coaxial elements
            elif self.fuel_type == 'methane' and self.oxidizer_type == 'lox':
                # Raptor engine data
                v_fuel_base = 22  # m/s
                v_ox_base = 32   # m/s
            elif self.fuel_type in ['mmh', 'udmh'] and self.oxidizer_type == 'n2o4':
                # Apollo Service Module heritage
                v_fuel_base = 8   # Hypergolic, lower velocity
                v_ox_base = 12   # Conservative for reliability
            else:
                # Conservative defaults with viscosity correction
                v_fuel_base = 15 * (0.001 / fuel_viscosity) ** 0.1
                v_ox_base = 20 * (0.0005 / ox_viscosity) ** 0.1
            
            pressure_drop_factor = 0.22  # Flight-proven for impinging
            
        elif self.injector_type == 'coaxial':
            # Coaxial shear injector (good for cryogenics)
            if self.fuel_type == 'lh2':
                v_fuel_base = 8   # Gas-centered H2
                v_ox_base = 25    # Liquid LOX annulus
            else:
                v_fuel_base = 6   # Liquid fuel center
                v_ox_base = 30    # Oxidizer annulus
            
            pressure_drop_factor = 0.18  # Lower ΔP for coaxial
            
        elif self.injector_type == 'showerhead':
            # Many small holes for uniform distribution
            v_fuel_base = 18
            v_ox_base = 22
            pressure_drop_factor = 0.28  # Higher ΔP for atomization
            
        elif self.injector_type == 'pintle':
            # Single point injection (throttleable)
            v_fuel_base = 25
            v_ox_base = 40
            pressure_drop_factor = 0.15  # Low ΔP design
            
        else:  # Default to unlike impinging
            v_fuel_base = 20
            v_ox_base = 25
            pressure_drop_factor = 0.20
        
        # Discharge coefficients based on injector type
        if self.injector_type == 'impinging':
            Cd_fuel = 0.7   # Sharp-edged orifices
            Cd_ox = 0.7
        elif self.injector_type == 'coaxial':
            Cd_fuel = 0.85  # Well-rounded entries
            Cd_ox = 0.8
        elif self.injector_type == 'showerhead':
            Cd_fuel = 0.65  # Many small holes
            Cd_ox = 0.65
        else:
            Cd_fuel = 0.75  # Default
            Cd_ox = 0.75

        # DENETIM DUZELTMESI (Bulgu 8): enjektor basinc dusumu hazne basincina
        # baglanmalidir. NASA SP-8089 (Liquid Rocket Engine Injectors) ve Sutton
        # 9th ed.: chug kararliligi icin dP_inj = %15-25 * Pc. Eski kod sabit
        # enjeksiyon hizlarindan dP hesapliyordu (Pc=100 bar'da sadece %3),
        # yuksek Pc'de kararlilik fiziksel olarak saglanamiyordu.
        # pressure_drop_factor (0.15-0.28) artik dogru anlaminda, dP/Pc orani
        # olarak kullaniliyor.
        # Kullanıcı 'Injector Pressure Drop' girdiyse dP ONDAN gelir
        # (2026-07-19 denetimi: alan hesaba hiç girmiyordu). Girdi yoksa
        # tip bazlı dP/Pc oranı korunur.
        dp_user = getattr(self, 'injector_dp_input_bar', None)
        if dp_user is not None:
            delta_P_fuel = delta_P_ox = float(dp_user)
            pressure_drop_factor = delta_P_ox / max(self.P_c, 1e-9)
            if not (0.05 <= pressure_drop_factor <= 0.40):
                self._warn(
                    f"Injector pressure drop {dp_user:g} bar is "
                    f"{pressure_drop_factor * 100:.0f}% of the chamber "
                    f"pressure; NASA SP-8089 recommends 15-25% for chug "
                    f"stability.")
        else:
            delta_P_fuel = pressure_drop_factor * self.P_c  # bar (NASA SP-8089)
            delta_P_ox = pressure_drop_factor * self.P_c    # bar (NASA SP-8089)

        # Kullanıcı akış katsayısı girdiyse orifis denklemi ONU kullanır.
        cd_user = getattr(self, 'injector_cd_input', None)
        if cd_user is not None:
            Cd_fuel = Cd_ox = float(cd_user)

        # Enjeksiyon hizlari bu dP'den turetilir: v = Cd * sqrt(2*dP/rho)
        # (orifis denklemi; A_inj = mdot/(rho*v) ile tutarli zincir).
        # Yukaridaki heritage tabanli sabit hizlar dP/Pc gereksinimini
        # saglamadigindan referans olarak birakildi, hesapta kullanilmiyor.
        v_fuel_base = Cd_fuel * np.sqrt(2.0 * delta_P_fuel * PA_PER_BAR / self.rho_fuel)
        v_ox_base = Cd_ox * np.sqrt(2.0 * delta_P_ox * PA_PER_BAR / self.rho_ox)

        # Weber number optimization for atomization
        # We = rho * v_rel^2 * D / sigma  ->  D = We_crit * sigma / (rho * v_rel^2)
        surface_tension = 0.02  # N/m typical for cryogenics

        # Relative velocity for atomization
        v_relative = max(abs(v_ox_base - v_fuel_base), 1.0)  # m/s (sifira bolunme korumasi)

        # DENETIM DUZELTMESI (Bulgu 7): eski kod D = rho*v^2/(We*sigma) ile
        # formulu ters yazmisti (285 km 'damlacik' uretiyordu). Dogrusu
        # We tanimindan: D = We_crit * sigma / (rho * v_rel^2).
        # We_crit ~ 12: dusuk viskoziteli sivi damlacik parcalanma esigi
        # (Lefebvre & McDonell, "Atomization and Sprays", 2nd ed.)
        # 2026-07-13 teyidi: aerodinamik parcalanma We'si SUREKLI FAZ (oda
        # gazi) yogunlugu ile tanimlanir; sivi yogunlugu kullanmak capi
        # ~140x kucultuyordu ve deger her kosulda 10 um tabanina yapisiyordu
        # (Lefebvre & McDonell 2nd ed., Bolum 2).
        target_weber = 12
        rho_gas = (self.P_c * PA_PER_BAR) / ((R_UNIVERSAL / self.mw) * self.T_c)
        droplet_diameter = target_weber * surface_tension / (rho_gas * (v_relative**2))
        # Makul fiziksel sinirlar: 10-500 mikron (tipik enjektor sprey araligi)
        droplet_diameter = min(max(droplet_diameter, 10e-6), 500e-6)

        # Injection areas with high precision
        A_fuel = self.mdot_fuel / (self.rho_fuel * v_fuel_base)
        A_ox = self.mdot_ox / (self.rho_ox * v_ox_base)

        # Validation
        if A_fuel <= 0 or A_ox <= 0:
            raise ValueError("Injection areas must be positive")
        if A_fuel > 0.1 or A_ox > 0.1:  # Large area warning
            print(f"Warning: Large injection areas: Fuel={A_fuel*1e4:.1f} cm², Ox={A_ox*1e4:.1f} cm²")

        # Feed system pressure requirements
        P_tank_fuel = self.P_c + delta_P_fuel + 8  # +8 bar safety margin
        P_tank_ox = self.P_c + delta_P_ox + 8
        
        # Injector element count optimization
        n_user = getattr(self, 'injector_elements_input', None)
        if n_user is not None:
            # Kullanıcı eleman sayısı verdiyse orifis çapları toplam alandan
            # ONA göre bölünür (2026-07-19 denetimi: alan yok sayılıyordu).
            n_elements = max(1, int(n_user))
            d_fuel_orifice = 2 * np.sqrt((A_fuel / n_elements) / np.pi)
            d_ox_orifice = 2 * np.sqrt((A_ox / n_elements) / np.pi)
        elif self.injector_type == 'impinging':
            # Size individual elements
            max_element_area = 5e-6  # 5 mm² maximum per element
            n_fuel_elements = max(1, int(np.ceil(A_fuel / max_element_area)))
            n_ox_elements = max(1, int(np.ceil(A_ox / max_element_area)))

            # Ensure even pairing
            n_elements = max(n_fuel_elements, n_ox_elements)

            # Element sizing
            A_fuel_per_element = A_fuel / n_elements
            A_ox_per_element = A_ox / n_elements

            d_fuel_orifice = 2 * np.sqrt(A_fuel_per_element / np.pi)
            d_ox_orifice = 2 * np.sqrt(A_ox_per_element / np.pi)
        else:
            n_elements = 1  # Single element for coaxial/pintle
            d_fuel_orifice = 2 * np.sqrt(A_fuel / np.pi)
            d_ox_orifice = 2 * np.sqrt(A_ox / np.pi)

        # Girdi-çıktı tutarlılık uyarıları: hız ve orifis çapı ÇIKTIDIR
        # (ΔP + Cd + debi zincirinden gelir). Kullanıcının girdiği değerle
        # ciddi fark varsa sessiz kalınmaz.
        for label, entered, computed, unit in (
                ('Fuel injection velocity',
                 getattr(self, 'fuel_velocity_input', None), v_fuel_base, ' m/s'),
                ('Oxidizer injection velocity',
                 getattr(self, 'ox_velocity_input', None), v_ox_base, ' m/s'),
                ('Fuel orifice diameter',
                 getattr(self, 'fuel_orifice_input_mm', None),
                 d_fuel_orifice * 1000.0, ' mm'),
                ('Oxidizer orifice diameter',
                 getattr(self, 'ox_orifice_input_mm', None),
                 d_ox_orifice * 1000.0, ' mm')):
            if entered is None or computed <= 0:
                continue
            if abs(entered - computed) / computed > INPUT_CONSISTENCY_TOLERANCE:
                self._warn(
                    f"{label}: the solver computes {computed:.2f}{unit} from "
                    f"the injector pressure drop, discharge coefficient and "
                    f"mass flow; the entered {entered:g}{unit} is reported for "
                    f"comparison only.")
        
        # Mixing efficiency calculation
        mixing_length = 0.05  # 50mm typical mixing length
        residence_time = mixing_length / np.sqrt(v_fuel_base * v_ox_base)
        
        # Combustion efficiency (mixing dependent)
        if self.injector_type == 'impinging':
            combustion_efficiency = 0.98  # Excellent mixing
        elif self.injector_type == 'coaxial':
            combustion_efficiency = 0.96  # Good mixing
        elif self.injector_type == 'showerhead':
            combustion_efficiency = 0.99  # Uniform distribution
        else:
            combustion_efficiency = 0.95  # Conservative estimate
        
        result = {
            'injector_type': self.injector_type,
            'fuel_injection_area': A_fuel * 1e6,  # mm²
            'ox_injection_area': A_ox * 1e6,  # mm²
            'fuel_injection_velocity': v_fuel_base,  # m/s
            'ox_injection_velocity': v_ox_base,  # m/s
            'fuel_pressure_drop': delta_P_fuel,  # bar
            'ox_pressure_drop': delta_P_ox,  # bar
            'required_fuel_tank_pressure': P_tank_fuel,  # bar
            'required_ox_tank_pressure': P_tank_ox,  # bar
            'number_of_elements': n_elements,
            'fuel_orifice_diameter': d_fuel_orifice * 1000,  # mm
            'ox_orifice_diameter': d_ox_orifice * 1000,  # mm
            'discharge_coefficient_fuel': Cd_fuel,
            'discharge_coefficient_ox': Cd_ox,
            'combustion_efficiency': combustion_efficiency,
            'droplet_diameter': droplet_diameter * 1e6,  # microns
            'weber_number': target_weber,
            'mixing_residence_time': residence_time * 1000  # ms
        }

        # Gerçek tasarım katmanı: injector_design modülü (10_Enjektor_ARGE.md).
        # Geriye uyum: mevcut alan adları korunur, eşleşen alanlar modül
        # çıktısıyla doldurulur; tam çıktı 'injector_design_detail'. Modül
        # hata verirse yukarıdaki eski hesap olduğu gibi döner.
        try:
            from hrma.engines.injector_design import design_injector
            type_map = {'impinging': 'impinging_doublet',
                        'coaxial': 'coax_swirl',
                        'showerhead': 'showerhead',
                        'pintle': 'pintle',
                        'swirl': 'swirl'}
            inj_spec = {
                'motor_type': 'liquid',
                'injector_type': type_map.get(self.injector_type,
                                              'impinging_doublet'),
                'mdot_ox': self.mdot_ox,
                'mdot_fuel': self.mdot_fuel,
                'rho_ox': self.rho_ox,
                'rho_fuel': self.rho_fuel,
                'Pc_bar': self.P_c,
                'dp_ratio_ox': pressure_drop_factor,
                'dp_ratio_fuel': pressure_drop_factor,
                'T_c_K': self.T_c,
                'mw_gas': self.mw,
                'mu_ox': ox_viscosity,
                'mu_fuel': fuel_viscosity,
            }
            # --- GAZ-GAZ ana oda enjeksiyonu (2026-07-22, denetim madde 5) --
            # FFSC'de ana odaya İKİ ÖN YAKICI EGZOZU (gaz) girer; sıvı SPI
            # modeli fiziksel olarak yanlış sınıftır. Çevrim çözümü mevcutsa
            # (main_chamber.inlet_streams iki gaz akışı) enjektör gaz-gaz
            # shear-coax modeliyle çözülür; akım koşulları (T0, P0, gamma,
            # MW) ÇEVRİM ÇÖZÜMÜNDEN gelir, varsayılan sabit yoktur.
            gas_spec = self._gas_gas_injector_spec()
            if gas_spec is not None:
                inj_spec = gas_spec
            detail = design_injector(inj_spec)
            if detail.get('status') == 'success':
                oxc, fc = detail['ox_circuit'], detail.get('fuel_circuit')
                result['injector_design_detail'] = detail
                result['number_of_elements'] = detail['pattern']['n_elements']
                result['ox_orifice_diameter'] = oxc['orifice_d_mm']
                result['ox_injection_velocity'] = oxc['velocity_m_s']
                result['ox_pressure_drop'] = oxc['delta_p_bar']
                result['ox_injection_area'] = oxc['total_area_mm2']
                result['discharge_coefficient_ox'] = oxc['cd']
                if fc:
                    result['fuel_orifice_diameter'] = fc['orifice_d_mm']
                    result['fuel_injection_velocity'] = fc['velocity_m_s']
                    result['fuel_pressure_drop'] = fc['delta_p_bar']
                    result['fuel_injection_area'] = fc['total_area_mm2']
                    result['discharge_coefficient_fuel'] = fc['cd']
                smd = detail['atomization'].get('smd_ox_um')
                if smd:
                    result['droplet_diameter'] = smd  # microns (modül SMD'si)
                if detail.get('injector_type') == 'gas_gas_coaxial':
                    result['injector_type'] = 'gas_gas_coaxial'
                    result['main_injection_phase'] = 'gas-gas'
                    result['gas_gas_geometry'] = detail.get('gas_gas_geometry')
                    # Gaz-gaz'da damlacık yok — SMD alanı dürüstçe boşalır.
                    result['droplet_diameter'] = None
                    result['droplet_diameter_basis'] = (
                        'not_modelled (gas-gas injection: no liquid droplets)')
        except Exception as _inj_err:
            warnings.warn(f'injector_design modülü kullanılamadı, eski '
                          f'enjektör hesabı korundu: {_inj_err}')

        # Staged combustion (tek ön yakıcı): ana oda GAZ+SIVI karışık beslenir
        # (RS-25 tarzı). Gaz devresinin ΔP/Pc'si çevrim akım koşullarından
        # sıkıştırılabilir orifis modeliyle raporlanır; gaz-sıvı coax eleman
        # GEOMETRİSİ bu sürümde modellenmez ve açıkça etiketlenir.
        hot_gas = self._staged_hot_gas_circuit()
        if hot_gas is not None:
            result['hot_gas_circuit'] = hot_gas
            result['main_injection_phase'] = 'gas-liquid'
            result['gas_liquid_element_model'] = 'not_modelled'

        # Kullanıcı eleman sayısı verdiyse SON SÖZ ONUNDUR: detay modülü kendi
        # desen sayısını yazmış olabilir, orifis çapları toplam alandan
        # kullanıcının sayısına göre yeniden bölünür.
        if n_user is not None:
            result['number_of_elements'] = n_elements
            result['fuel_orifice_diameter'] = d_fuel_orifice * 1000.0
            result['ox_orifice_diameter'] = d_ox_orifice * 1000.0
            result['element_count_source'] = 'user input'
        else:
            result['element_count_source'] = 'sized by the injector model'
        result['pressure_drop_source'] = (
            'user input (injector pressure drop)'
            if getattr(self, 'injector_dp_input_bar', None) is not None
            else 'NASA SP-8089 dP/Pc ratio for the element type')

        return result
    
    def calculate_turbopump_requirements(self):
        """Calculate turbopump specifications (if required)"""
        # Check if turbopumps are needed (high pressure engines)
        if self.P_c > 50:  # bar
            # DENETIM DUZELTMESI (Bulgu 8): pompa head'i Pc'den bagimsiz sabit
            # 200/300 m idi (Pc=100 bar icin gereken ~1300+ m; guc ~6.5x dusuk
            # raporlaniyordu). Head artik gercek basinc yukselmesinden:
            # H = (Pc + dP_enjektor + dP_hat/marj) / (rho * g)
            # (_design_turbopump_system ile ayni yaklasim; Huzel & Huang Ch. 6)
            injector = self.calculate_injector_design()
            delta_P_inj_fuel = injector['fuel_pressure_drop'] * PA_PER_BAR  # Pa
            delta_P_inj_ox = injector['ox_pressure_drop'] * PA_PER_BAR     # Pa
            delta_P_lines = 5e5  # Pa, besleme hatti kayiplari + marj (5 bar tipik)

            P_c_pa = self.P_c * PA_PER_BAR
            fuel_head = (P_c_pa + delta_P_inj_fuel + delta_P_lines) / (self.rho_fuel * self.g0)  # m
            ox_head = (P_c_pa + delta_P_inj_ox + delta_P_lines) / (self.rho_ox * self.g0)        # m

            # Pump efficiencies
            eta_fuel_pump = 0.75
            eta_ox_pump = 0.80
            
            # Power requirements
            P_fuel_pump = (self.mdot_fuel * fuel_head * self.g0) / eta_fuel_pump
            P_ox_pump = (self.mdot_ox * ox_head * self.g0) / eta_ox_pump
            
            total_power = P_fuel_pump + P_ox_pump
            
            # Turbine requirements (assuming gas generator cycle)
            turbine_efficiency = 0.65
            gas_generator_flow = total_power / (turbine_efficiency * 500000)  # Simplified
            
            return {
                'turbopumps_required': True,
                'fuel_pump_power': P_fuel_pump / 1000,  # kW
                'ox_pump_power': P_ox_pump / 1000,  # kW
                'total_pump_power': total_power / 1000,  # kW
                'gas_generator_flow': gas_generator_flow,  # kg/s
                'fuel_pump_head': fuel_head,  # m
                'ox_pump_head': ox_head  # m
            }
        else:
            injector = self.calculate_injector_design()
            return {
                'turbopumps_required': False,
                'tank_fed_system': True,
                'max_tank_pressure': max(injector['required_fuel_tank_pressure'], injector['required_ox_tank_pressure'])
            }
    
    def calculate_altitude_performance(self, altitudes):
        """High-precision altitude performance with detailed nozzle optimization

        DENETIM DUZELTMESI (Bulgu 1): fonksiyonun sonuc blogu literal '\\n'
        kacislariyla tek yorum satirina hapsolmustu ve fonksiyon None donuyordu.
        Blok canli koda cevrildi; fonksiyon her irtifa icin CF, Isp ve itki
        iceren sozluk listesi dondurur.

        DENETIM DUZELTMESI (Bulgu 4): yanlis ISA katman taban sicakliklari
        (20-32 km icin 196.65 K, 32-47 km icin 139.05 K; basinci 23x-432x
        sisiriyordu) kaldirildi. Atmosfer modeli artik hrma.constants.ISA_LAYERS
        tablosu (US Standard Atmosphere 1976, Tablo 4) + barometrik formul ile
        hesaplaniyor.
        """
        from hrma.constants import ISA_LAYERS, M_AIR, R_STAR_ICAO

        # DURUM SIZINTISI DÜZELTMESİ (2026-07-19): bu fonksiyon her irtifa için
        # calculate_nozzle_geometry çağırıyor ve motorun tasarım-noktası
        # geometrisini (ε, A_e, d_e, P_e, L_nozzle) SON irtifanın değerleriyle
        # bırakıyordu. Ardından çalışan soğutma/verim/kütle hesapları 100 km
        # lülesini görüyordu. Tasarım noktası girişte alınır, çıkışta geri
        # yüklenir.
        _snapshot_keys = ('A_t', 'd_t', 'A_e', 'd_e', 'expansion_ratio',
                          'expansion_ratio_matched', 'L_nozzle', 'P_e',
                          'mdot_total', 'mdot_ox', 'mdot_fuel')
        _snapshot = {k: getattr(self, k) for k in _snapshot_keys
                     if hasattr(self, k)}

        altitude_data = []

        for alt in altitudes:
            # Geopotential height (US Standard Atmosphere 1976)
            H = alt * 6356766 / (6356766 + alt)

            # Katman secimi: taban yuksekligi H'yi asmayan son katman
            # (hrma.constants.ISA_LAYERS: (h_taban, T_taban, lapse, P_taban))
            layer = ISA_LAYERS[0]
            for candidate in ISA_LAYERS:
                if H >= candidate[0]:
                    layer = candidate
                else:
                    break
            h_base, T_base, lapse, P_base = layer

            # Barometrik formul (US Standard Atmosphere 1976, Eq. 33a/33b)
            if abs(lapse) > 1e-12:
                T = T_base + lapse * (H - h_base)
                P = P_base * (T / T_base) ** (-G_0 * M_AIR / (R_STAR_ICAO * lapse))
            else:
                T = T_base
                P = P_base * np.exp(-G_0 * M_AIR * (H - h_base) / (R_STAR_ICAO * T_base))

            pressure_atm = P / 100000  # Convert Pa to bar

            # Space vacuum conditions
            if alt >= 100000:
                pressure_atm = 1e-6
                T = 1000  # Thermospheric temperature

            # Calculate optimal nozzle for this altitude
            nozzle_geom = self.calculate_nozzle_geometry(altitude=alt)
            epsilon_opt = nozzle_geom['expansion_ratio']

            # High-precision thrust coefficient calculation
            gamma = self.gamma
            Pe_Pc = pressure_atm / self.P_c
            Pe_Pc = max(Pe_Pc, 1e-8)  # Prevent numerical issues

            # Ideal thrust coefficient (matched expansion; Sutton & Biblarz
            # 9th ed., Eq. 3-30)
            gamma_term = 2 * gamma**2 / (gamma - 1)
            stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
            expansion_term = 1 - Pe_Pc ** ((gamma - 1) / gamma)
            CF_ideal = np.sqrt(gamma_term * stagnation_term * expansion_term)

            # Deniz seviyesi (tasarim noktasi) ideal CF — zincir demiri
            Pe_Pc_sl = max(self.P_a / self.P_c, 1e-8)
            CF_ideal_sl = np.sqrt(
                gamma_term * stagnation_term
                * (1 - Pe_Pc_sl ** ((gamma - 1) / gamma))
            )

            # SABİT LÜLE (kullanıcı ε girdiyse): çıkış basıncı ortamla birlikte
            # DEĞİŞMEZ; CF'in basınç-itki terimi irtifayla değişir
            # (Sutton & Biblarz 9th ed., Eq. 3-30). Girdi yoksa yukarıdaki
            # ortam-eşlenik zincir aynen korunur.
            if getattr(self, 'expansion_ratio_input', None) is not None:
                try:
                    CF_ideal, _ = self._cf_at(self.expansion_ratio,
                                              pressure_atm)
                    CF_ideal_sl, _ = self._cf_at(self.expansion_ratio,
                                                 self.P_a)
                except Exception:
                    pass

            # Nozzle efficiency corrections (bilgilendirme amacli rapor edilir;
            # teslim Isp'si CEA tablosuna demirli oldugundan ikinci kez uygulanmaz)
            # 1. Divergence loss (15 deg half-angle conical nozzle)
            eta_divergence = (1 + np.cos(np.radians(15))) / 2

            # 2. Boundary layer correction (altitude dependent)
            Re_throat = (self.mdot_total * 4) / (np.pi * self.d_t * self.mu_chamber)
            eta_boundary_layer = 1 - 0.002 * (1e6 / max(Re_throat, 1e4))**0.2

            # 3. Heat transfer loss (reduces with altitude)
            density_ratio = pressure_atm / 1.01325
            eta_heat_transfer = 1 - 0.003 * density_ratio  # Less loss at altitude

            # 4. Kinetic loss (finite reaction rate)
            if self.frozen_performance:
                eta_kinetic = 0.96  # Frozen flow penalty
            else:
                eta_kinetic = 0.99  # Equilibrium flow

            # Combined nozzle efficiency
            eta_nozzle = eta_divergence * eta_boundary_layer * eta_heat_transfer * eta_kinetic

            # DENETIM DUZELTMESI (Bulgu 3): Isp-c*-CF zinciri tutarli hale
            # getirildi. Isp, teslim edilen deniz seviyesi Isp'sine (CEA tablo)
            # demirlenir ve ideal CF orani ile irtifaya tasinir. Boylece deniz
            # seviyesinde thrust = CF*Pc*A_t = komuta edilen itki (birebir) ve
            # hicbir irtifada CEA vakum referansi (isp_vac) asilmaz.
            isp_altitude = min(self.isp_sl * CF_ideal / CF_ideal_sl, self.isp_vac)

            # Thrust at altitude (constant mass flow)
            thrust_altitude = self.mdot_total * isp_altitude * self.g0

            # Actual thrust coefficient (zincirle tutarli: CF = F / (Pc * A_t))
            CF_actual = thrust_altitude / (self.P_c * 1e5 * self.A_t)

            # Performance ratios
            isp_ratio = isp_altitude / self.isp_sl
            thrust_ratio = thrust_altitude / self.F

            # Exit conditions
            # v2.5.2 DUZELTMESI (Codex bulgusu, liquid:2154): cikis Mach'i
            # GEOMETRIDEN cozulur, ortam basincindan DEGIL. Sabit lulede
            # (kullanici epsilon girdisi) Ae/At ve gamma cikis Mach'ini tek
            # basina belirler; irtifayla DEGISMEZ. Ortam basinci yalnizca
            # CF'in basinc-itki terimini ve akis rejimini (asiri genisleme /
            # ayrilma) etkiler (Sutton & Biblarz 9th ed., Eq. 3-15/3-25/3-30).
            # ESKI DAVRANIS: Me = f(Pc/Pa) -> epsilon=16 sabit lulede deniz
            # seviyesinde 3.04, 100 km'de 14.47 raporlaniyordu; dogrusu her
            # irtifada 3.67. Ortam-eslenik (rubber-nozzle) taramada da artik
            # o irtifanin GERCEK epsilon'undan cozulur, boylece epsilon pratik
            # ust sinira kirpildiginda Mach ile geometri celismez.
            eps_here = float(epsilon_opt)
            try:
                exit_mach = self._mach_from_area_ratio_supersonic(eps_here, gamma)
            except Exception:
                # Sayisal cozum dusrse ortam-eslenik dala geri don (etiketli)
                exit_mach = np.sqrt(2 / (gamma - 1)
                                    * ((self.P_c / pressure_atm)**((gamma-1)/gamma) - 1))
                self._warn(
                    f"Exit Mach could not be solved from the area ratio "
                    f"{eps_here:.2f} at {alt:.0f} m; the ambient-matched value "
                    f"is reported instead.")
            # Cikis statik basinci ve basinc-itki terimi: irtifayla DEGISEN
            # buyukluk budur (cikis Mach'i degil). Sekil olarak raporlanir ki
            # arayuz "Mach neden sabit?" sorusunu veriyle cevaplayabilsin.
            exit_pressure_bar = self.P_c * (
                1.0 + (gamma - 1.0) / 2.0 * exit_mach ** 2) ** (-gamma / (gamma - 1.0))
            pressure_thrust = ((exit_pressure_bar - pressure_atm) * PA_PER_BAR
                               * self.A_t * eps_here)  # N
            # DENETIM DUZELTMESI: Cikis hizi = Me * a_exit; a_exit yanma gazinin
            # OZGUL gaz sabiti (R_UNIVERSAL/mw ~330 J/kg·K) ve nozul CIKIS statik
            # sicakligiyla hesaplanir. Havanin 287'si ve ambiyans sicakligi T
            # yanlisti (100 km'de T=1000 K termosfer -> sacma deger). Dogrusu:
            # a_exit = sqrt(γ·R_gas·T_exit), T_exit = Tc/(1+(γ-1)/2·Me²).
            # T_exit Me ile azaldigindan cikis hizi fiziksel ust sinir
            # sqrt(2·cp·Tc)'yi asmaz (Sutton & Biblarz Eq. 3-15/3-16).
            R_gas_exit = R_UNIVERSAL / self.mw  # J/(kg*K), yanma urunu gazi
            T_exit_static = self.T_c / (1 + (gamma - 1) / 2 * exit_mach**2)  # K
            exit_velocity = exit_mach * np.sqrt(gamma * R_gas_exit * T_exit_static)

            altitude_data.append({
                'altitude': alt,
                'temperature': T,
                'pressure': pressure_atm,
                'expansion_ratio': epsilon_opt,
                'thrust_coefficient': CF_actual,
                'nozzle_efficiency': eta_nozzle,
                'specific_impulse': isp_altitude,
                'thrust': thrust_altitude,
                'isp_ratio': isp_ratio,
                'thrust_ratio': thrust_ratio,
                'exit_mach_number': exit_mach,
                'exit_velocity': exit_velocity,
                # Sabit lulede irtifayla degisen buyukluk: cikis-ortam basinc
                # farkindan gelen itki terimi (cikis Mach'i degil).
                'exit_pressure_bar': exit_pressure_bar,
                'pressure_thrust': pressure_thrust,
                'reynolds_number': Re_throat
            })

        # Tasarım noktası geometrisini geri yükle (bkz. yukarıdaki not).
        for _k, _v in _snapshot.items():
            setattr(self, _k, _v)

        return altitude_data
    
    def calculate_performance(self):
        """Calculate overall engine performance"""
        # Basic geometry
        nozzle_geom = self.calculate_nozzle_geometry()
        
        # Cooling system
        cooling = self.calculate_cooling_requirements()
        
        # Injection system
        injector = self.calculate_injector_design()
        
        # Turbopump system
        turbopump = self.calculate_turbopump_requirements()
        
        burn_time, burn_time_source = self._burn_time()
        nozzle_geometry_table = NOZZLE_TYPE_GEOMETRY.get(
            getattr(self, 'nozzle_type', NOZZLE_TYPE_DEFAULT),
            NOZZLE_TYPE_GEOMETRY[NOZZLE_TYPE_DEFAULT])

        # Bileşen bazlı kuru kütle: TEK doğruluk kaynağı (2026-07-19 denetimi).
        # Eski kod max(F/1000, 50) ile 10 kN'a kadar HER motora 50 kg veriyor
        # ve aynı sonuçta _detailed_component_sizing ~123 kg raporluyordu.
        component_sizing = self._detailed_component_sizing()
        engine_mass = component_sizing['component_masses']['total_dry_mass']
        thrust_to_weight = self.F / (engine_mass * self.g0)

        # T/W oranı kontrolü
        if thrust_to_weight < 1 or thrust_to_weight > 200:
            print(f"Uyarı: T/W oranı anormal: {thrust_to_weight:.1f}")
        
        # MR efficiency already applied in _calculate_mixture_ratio_effects()
        # Do NOT apply again here (was causing double penalty)
        mr_efficiency = getattr(self, 'mr_efficiency', 1.0)
        actual_isp_sl = self.isp_sl
        actual_isp_vac = self.isp_vac

        # Özgül itki kontrolü
        if actual_isp_sl < 100 or actual_isp_sl > 500:
            print(f"Uyarı: Deniz seviyesi Isp anormal: {actual_isp_sl:.1f} s")
        if actual_isp_vac < 200 or actual_isp_vac > 600:
            print(f"Uyarı: Vakum Isp anormal: {actual_isp_vac:.1f} s")

        # Uzay sınıfı (vakum optimize) lüle: GERÇEKTEN yeniden çözülür.
        # 2026-07-19 denetimi: eski kod `actual_isp_vac * 1.05` ile dayanaksız
        # bir %5 ekliyordu ve raporlanan expansion_ratio_vacuum ile hiçbir
        # bağlantısı yoktu. Yeni zincir: ε_vac ile vakum CF'si (P_a = 0)
        # hesaplanır, Isp = CF·c*/g0 (Sutton & Biblarz 9th ed., Eq. 3-31),
        # sonuç mevcut vakum Isp'sine göre CF ORANIYLA ölçeklenir; böylece
        # tasarım noktasıyla tutarlıdır ve ε_vac'a gerçekten bağlıdır.
        expansion_ratio_vacuum = min(EXPANSION_RATIO_VACUUM_CAP,
                                     nozzle_geom['expansion_ratio']
                                     * EXPANSION_RATIO_VACUUM_FACTOR)
        try:
            cf_vac_big, _ = self._cf_at(expansion_ratio_vacuum, 0.0)
            cf_vac_now, _ = self._cf_at(nozzle_geom['expansion_ratio'], 0.0)
            vacuum_optimized_isp = actual_isp_vac * (cf_vac_big / cf_vac_now)
            vacuum_isp_method = (
                f"re-solved vacuum nozzle at expansion ratio "
                f"{expansion_ratio_vacuum:.1f} (isentropic CF ratio)")
        except Exception:
            vacuum_optimized_isp = actual_isp_vac
            expansion_ratio_vacuum = nozzle_geom['expansion_ratio']
            vacuum_isp_method = (
                "vacuum nozzle could not be re-solved; the value equals the "
                "vacuum Isp of the current nozzle")
        space_thrust_vacuum = self.F * (actual_isp_vac / actual_isp_sl)
        
        # Uzay performansı kontrolü
        isp_improvement = (actual_isp_vac - actual_isp_sl) / actual_isp_sl
        if isp_improvement < 0.05 or isp_improvement > 0.5:  # %5-50 arası makul
            print(f"Uyarı: Vakum Isp iyileştirmesi anormal: %{isp_improvement*100:.1f}")
        
        # Altitude performance analysis
        altitudes = [0, 1000, 5000, 10000, 20000, 50000, 80000, 100000]  # m
        altitude_performance = self.calculate_altitude_performance(altitudes)
        
        # Advanced subsystem analysis
        propellant_tanks = self._design_propellant_tanks()
        detailed_feed_system = self._analyze_detailed_feed_system()
        combustion_analysis = self._analyze_combustion_chamber_detailed()
        structural_analysis = self._calculate_structural_loads()
        # Isıl koruma tek kaynak: yukarıdaki GERÇEK soğutma çözümünden türetilir.
        thermal_protection = self._calculate_thermal_protection_system(cooling)

        # Performance optimization maps
        performance_maps = self._generate_performance_optimization_maps()
        efficiency_analysis = self._calculate_efficiency_breakdown()

        # Manufacturing and cost analysis
        manufacturing_analysis = self._analyze_manufacturing_requirements()
        
        return {
            # Input parameters
            'thrust': self.F,
            'chamber_pressure': self.P_c,
            'mixture_ratio': self.MR,
            'fuel_type': self.fuel_type,
            'oxidizer_type': self.oxidizer_type,
            'propellant_name': self.propellant_name,
            'cooling_type': self.cooling_type,
            
            # Performance
            'isp_sea_level': actual_isp_sl,
            'isp_vacuum': actual_isp_vac,
            'isp_vacuum_optimized': vacuum_optimized_isp,
            'thrust_vacuum': space_thrust_vacuum,
            'c_star': self.c_star,
            'chamber_temperature': self.T_c,
            'thrust_to_weight': thrust_to_weight,
            'engine_mass_estimate': engine_mass,
            'optimal_mixture_ratio': self.optimal_mr,
            'optimal_mixture_ratio_thrust': getattr(
                self, 'optimal_mr_thrust', self.optimal_mr),
            'mixture_ratio_efficiency': mr_efficiency * 100,
            
            # Mass flow rates
            'total_mass_flow': self.mdot_total,
            'oxidizer_flow': self.mdot_ox,
            'fuel_flow': self.mdot_fuel,
            
            # Geometry
            'throat_diameter': nozzle_geom['throat_diameter'],
            'exit_diameter': nozzle_geom['exit_diameter'],
            'expansion_ratio': nozzle_geom['expansion_ratio'],
            'expansion_ratio_vacuum': expansion_ratio_vacuum,
            'vacuum_optimized_isp_method': vacuum_isp_method,
            'chamber_diameter': cooling['chamber_diameter'],
            'chamber_length': cooling['chamber_length'],
            
            # Subsystems
            'cooling_system': cooling,
            'injection_system': injector,
            'turbopump_system': turbopump,
            'propellant_tanks': propellant_tanks,
            'detailed_feed_system': detailed_feed_system,
            'combustion_analysis': combustion_analysis,
            'structural_analysis': structural_analysis,
            'thermal_protection': thermal_protection,
            
            # Advanced Analysis
            'performance_maps': performance_maps,
            'efficiency_breakdown': efficiency_analysis,
            'manufacturing_analysis': manufacturing_analysis,
            'component_sizing': component_sizing,
            
            # Propellant properties
            'fuel_density': self.rho_fuel,
            'oxidizer_density': self.rho_ox,
            'molecular_weight': self.mw,
            'gamma': self.gamma,
            
            # Altitude performance
            'altitude_performance': altitude_performance,
            
            # Feed System (Enhanced)
            'feed_system': self.feed_system,

            # --- Girdi şeffaflığı (2026-07-19 uydurma denetimi) ---
            # input_warnings: aralık dışı/çelişkili girdiler ve varsayımlar.
            # unwired_inputs: çözücünün BİLİNÇLİ kullanmadığı form alanları.
            'input_warnings': list(self.design_warnings),
            'unwired_inputs': self.unwired_inputs(),
            'burn_time': burn_time,
            'burn_time_source': burn_time_source,

            # --- Nozzle Angles & Dimensions ---
            # Açılar ve kontur verimi SEÇİLEN NOZUL TİPİNDEN gelir
            # (NOZZLE_TYPE_GEOMETRY; Sutton & Biblarz 9th ed., Fig. 3-14).
            'nozzle_angles': {
                'convergent_half_angle_deg': CONVERGENT_HALF_ANGLE_DEG,
                'divergent_half_angle_deg': nozzle_geometry_table['half_angle'],
                'exit_angle_deg': nozzle_geometry_table['exit_angle'],
                'nozzle_type': getattr(self, 'nozzle_type', NOZZLE_TYPE_DEFAULT),
                'nozzle_contour_modelled': nozzle_geometry_table['modelled'],
                'length_fraction_of_15deg_conical':
                    nozzle_geometry_table['length_fraction'],
                'throat_diameter_mm': nozzle_geom['throat_diameter'] * 1000,
                'exit_diameter_mm': nozzle_geom['exit_diameter'] * 1000,
                'nozzle_length_mm': nozzle_geom['nozzle_length'] * 1000,
                'contraction_ratio': self._contraction_ratio(),
                'expansion_ratio': nozzle_geom['expansion_ratio'],
                'expansion_ratio_source': (
                    'user input (nozzle expansion ratio)'
                    if getattr(self, 'expansion_ratio_input', None) is not None
                    else 'ambient-matched at sea level'),
                'expansion_ratio_matched': getattr(
                    self, 'expansion_ratio_matched',
                    nozzle_geom['expansion_ratio']),
                'exit_pressure_bar': nozzle_geom['exit_pressure'],
                'divergence_efficiency': 0.5 * (1.0 + np.cos(np.radians(
                    nozzle_geometry_table['exit_angle']))),
            },

            # --- Injector Design Details ---
            'injector_design': {
                'injector_type': injector['injector_type'],
                'number_of_elements': injector['number_of_elements'],
                'fuel_orifice_diameter_mm': injector['fuel_orifice_diameter'],
                'oxidizer_orifice_diameter_mm': injector['ox_orifice_diameter'],
                'injection_pressure_drop_fuel_bar': injector['fuel_pressure_drop'],
                'injection_pressure_drop_ox_bar': injector['ox_pressure_drop'],
                'spray_angle_deg': 30.0,  # tipik impinging jet angle
                'fuel_manifold_diameter_mm': max(10.0, np.sqrt(injector['fuel_injection_area'] * 4 / np.pi) * 2.5),
                'oxidizer_manifold_diameter_mm': max(12.0, np.sqrt(injector['ox_injection_area'] * 4 / np.pi) * 2.5),
                'fuel_injection_velocity_m_s': injector['fuel_injection_velocity'],
                'ox_injection_velocity_m_s': injector['ox_injection_velocity'],
                'combustion_efficiency': injector['combustion_efficiency'],
                'discharge_coefficient_fuel': injector['discharge_coefficient_fuel'],
                'discharge_coefficient_ox': injector['discharge_coefficient_ox'],
                'droplet_diameter_micron': injector['droplet_diameter'],
                'weber_number': injector['weber_number'],
            },

            # --- Optimal Design Summary ---
            'design_summary': {
                'title': f'Liquid Motor ({self.fuel_type}/{self.oxidizer_type}) - Optimal Design',
                'status': 'OPTIMIZED',
                'key_dimensions': {
                    'chamber_diameter_mm': cooling['chamber_diameter'],  # already in mm
                    'chamber_length_mm': cooling['chamber_length'],  # already in mm
                    'nozzle_throat_mm': nozzle_geom['throat_diameter'] * 1000,
                    'nozzle_exit_mm': nozzle_geom['exit_diameter'] * 1000,
                    'nozzle_length_mm': nozzle_geom['nozzle_length'] * 1000,
                    'overall_length_mm': cooling['chamber_length'] + nozzle_geom['nozzle_length'] * 1000,
                },
                'masses': {
                    'engine_mass_kg': engine_mass,
                    'engine_mass_source': (
                        'component shell geometry x material density '
                        '(component_sizing.total_dry_mass)'),
                    'propellant_mass_kg': self.mdot_total * burn_time,
                    'burn_time_s': burn_time,
                    'burn_time_source': burn_time_source,
                    'thrust_to_weight': thrust_to_weight,
                },
                'performance': {
                    'thrust_sl_N': self.F,
                    'thrust_vac_N': space_thrust_vacuum,
                    'isp_sl_s': actual_isp_sl,
                    'isp_vac_s': actual_isp_vac,
                    'c_star_m_s': self.c_star,
                    'mixture_ratio': self.MR,
                    'total_mass_flow_kg_s': self.mdot_total,
                },
                'recommendation': (
                    f'Liquid engine design optimised for the given parameters. '
                    f'T/W={thrust_to_weight:.1f}, Isp(vac)={actual_isp_vac:.0f} s, '
                    f'c*={self.c_star:.0f} m/s. '
                    f'{self.cooling_type.capitalize()} cooling, {self.injector_type} injector.'
                ),
            },
        }
    
    # ------------------------------------------------------------------
    # Tek yoğunluk kaynağı + tek tank boyutlandırma modeli
    # (v2.5.2, Codex bulgusu liquid:2450)
    # ------------------------------------------------------------------
    def _propellant_density(self, propellant_type: str):
        """Yoğunluk — TEK kaynak, kullanıcı girdisi EN YÜKSEK öncelikli.

        Eski davranış: besleme sistemi tank hacmi ve hat çapı
        ``web_propellant_data[...]['density']`` değerini TERCİH ediyor,
        ayrıntılı tank tasarımı ise ``self.rho_ox/self.rho_fuel``
        kullanıyordu. Sonuç: aynı koşuda iki farklı tank hacmi ve
        ``oxidizer_density`` girdisinin besleme kartına HİÇ yansımaması.

        Web sözlüğünün yoğunluğu güvenilir de değildi: ``fetch_nist_data('lox')``
        bu sürümde ``density`` anahtarını hiç döndürmüyor, dolayısıyla
        ``ox_props.get('density', 1200)`` ile 1200 kg/m³ SABİTİ giriyordu
        (LOX'un doğru değeri normal kaynama noktasında 1141.7 kg/m³ —
        yerleşik tabloda zaten bu var). Ölçüm değil, yer tutucu.

        Öncelik: kullanıcı girdisi > yerleşik yakıt tablosu. ``self.rho_*``
        zaten bu sırayı taşır (``_set_propellant_properties`` tabloyu yazar,
        ardından ``_apply_overrides`` kullanıcı değerini üstüne yazar) ve
        enjektör, pompa, hat basınç düşümü hesaplarının hepsi bunu kullanır —
        böylece tanklar motorun geri kalanıyla AYNI yoğunluğu görür.
        """
        if propellant_type == 'oxidizer':
            rho = float(self.rho_ox)
            user = self.overrides.get('oxidizer_density')
        else:
            rho = float(self.rho_fuel)
            user = self.overrides.get('fuel_density')
        source = ('user input' if user not in (None, '')
                  else 'built-in propellant table')
        return rho, source

    def _size_tank(self, propellant_mass: float, propellant_type: str):
        """Tek tank boyutlandırma modeli: kütle -> (hacim, sıvı hacmi, yoğunluk).

        Model (her iki çağıran için AYNI): itici kütlesi rezerv payıyla
        çarpılır, yoğunluğa bölünür, ullage payı bölme ile eklenir
        (V_tank = V_sıvı / (1 - ullage)). Eskiden besleme yolu 1.20 çarpanı,
        ayrıntılı yol 1.15 rezerv + %5 ullage kullanıyordu; ikisi aynı adı
        taşıyan iki farklı büyüklük üretiyordu.
        """
        rho, source = self._propellant_density(propellant_type)
        liquid_volume = (propellant_mass * TANK_PROPELLANT_RESERVE_FACTOR) / rho
        tank_volume = liquid_volume / (1.0 - TANK_ULLAGE_FRACTION)
        return tank_volume, liquid_volume, rho, source

    def _calculate_tank_volume(self, mass_flow_rate: float, propellant_type: str) -> float:
        """Tank hacmi [m³] — ``_size_tank`` ile TEK modelden."""
        # Yanma süresi kullanıcı girdisinden (max_burn_duration); girdi yoksa
        # etiketli varsayım (2026-07-19 denetimi: 300 s sessiz varsayımdı).
        burn_time, _ = self._burn_time()
        propellant_mass = mass_flow_rate * burn_time  # kg
        tank_volume, _, _, _ = self._size_tank(propellant_mass, propellant_type)
        return tank_volume

    def _calculate_line_diameter(self, mass_flow_rate: float, propellant_type: str) -> float:
        """Calculate optimal feed line diameter"""
        # Target velocity: 3-8 m/s for liquids
        target_velocity = 5.0  # m/s

        # Yoğunluk tank modeliyle AYNI kaynaktan (bkz. _propellant_density).
        density, _ = self._propellant_density(propellant_type)

        # A = mdot / (rho * v)
        area = mass_flow_rate / (density * target_velocity)  # m²
        diameter = 2 * np.sqrt(area / np.pi)  # m
        
        # Round to standard pipe sizes
        standard_sizes = [0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3]  # m
        return min(standard_sizes, key=lambda x: abs(x - diameter))
    
    def _design_turbopump_system(self, mdot_ox: float, mdot_fuel: float) -> Dict:
        """Turbopompa alt sistemi — ayrıntılı analizle TEK kaynak.

        2026-07-19 denetimi: burada çark çapı 0.15/0.12 m, devir 25000 rpm,
        türbin giriş sıcaklığı 1100 K ve toplam kütle 45 kg sabitti; aynı
        sonuçta _analyze_detailed_feed_system farklı sayılar veriyordu. Artık
        ikisi de aynı `_design_pump` zincirini kullanır.
        """
        drops = self._calculate_feed_system_pressure_drops()
        pressure_fed = getattr(self, 'engine_cycle', '') == 'pressure_fed'
        tank_bar = ((getattr(self, 'feed_pressure_input_bar', None)
                     or PUMP_TANK_PRESSURE_DEFAULT_BAR) if pressure_fed
                    else PUMP_TANK_PRESSURE_DEFAULT_BAR)
        # Pompa basma basıncı: çevrim çözümü varsa ONDAN (ön yakıcı merdiveni
        # + rejeneratif ΔP dahil — _analyze_detailed_feed_system ile TEK
        # kaynak), yoksa Pc + hat/enjektör zinciri.
        disch_ox = drops['pump_discharge_pressure_ox']
        disch_fuel = drops['pump_discharge_pressure_fuel']
        cyc = getattr(self, '_cycle_result', None)
        if (cyc and cyc.get('status') == 'converged'
                and cyc.get('pump_discharge_ox_bar')):
            disch_ox = float(cyc['pump_discharge_ox_bar'])
            disch_fuel = float(cyc['pump_discharge_fuel_bar'])
        ox = self._design_pump(mdot_ox, self.rho_ox, disch_ox, tank_bar)
        fuel = self._design_pump(mdot_fuel, self.rho_fuel, disch_fuel,
                                 tank_bar)
        total_pump_power = (ox['design_power'] + fuel['design_power']) * 1000.0
        eta_turbine = TURBINE_EFFICIENCY_DEFAULT
        turbine_power_required = total_pump_power / eta_turbine  # W
        turbine_inlet_temp = float(getattr(self, 'turbine_inlet_temp',
                                           GAS_GENERATOR_TEMP_DEFAULT_K))
        material, mat_key = self._material_record()

        return {
            'type': f"{getattr(self, 'engine_cycle', 'gas_generator')}_cycle",
            'oxidizer_pump': {
                'flow_rate': mdot_ox,  # kg/s
                'head': ox['design_head'],  # m
                'head_rise': ox['design_head'],  # m (geriye uyum anahtarı)
                'power': ox['design_power'],  # kW
                'efficiency': ox['design_efficiency'] / 100.0,
                'impeller_diameter': ox['impeller_diameter'],  # m
                'impeller_tip_speed': ox['impeller_tip_speed'],  # m/s
                'rpm': ox['rotational_speed'],
                'npsh_required': ox['npsh_required'],  # m
                'material': 'Inconel 718'
            },
            'fuel_pump': {
                'flow_rate': mdot_fuel,  # kg/s
                'head': fuel['design_head'],  # m
                'fuel_head_rise': fuel['design_head'],  # m (geriye uyum)
                'power': fuel['design_power'],  # kW
                'efficiency': fuel['design_efficiency'] / 100.0,
                'impeller_diameter': fuel['impeller_diameter'],  # m
                'impeller_tip_speed': fuel['impeller_tip_speed'],  # m/s
                'rpm': fuel['rotational_speed'],
                'npsh_required': fuel['npsh_required'],  # m
                'material': 'Stainless Steel 316L'
            },
            'turbine': {
                'power': turbine_power_required / 1000,  # kW
                'efficiency': eta_turbine,
                'inlet_temperature': turbine_inlet_temp,  # K
                'pressure_ratio': float(getattr(
                    self, 'turbine_pressure_ratio',
                    TURBINE_PRESSURE_RATIO_DEFAULT)),
                'rpm': ox['rotational_speed'],
                'material': 'Inconel 713C'
            },
            'gas_generator': {
                'flow_fraction': GAS_GENERATOR_FLOW_FRACTION,
                'mixture_ratio': self.MR * 0.7,  # fuel-rich for cooling
                'chamber_pressure': self.P_c * GAS_GENERATOR_PRESSURE_RATIO,
                'temperature': turbine_inlet_temp  # K
            },
            # Kütle: güçle ölçeklenen ETİKETLİ ampirik korelasyon.
            'total_mass': (TURBOPUMP_MASS_BASE_KG + TURBOPUMP_MASS_PER_KW
                           * total_pump_power / 1000.0),
            'total_mass_basis': 'empirical mass-power correlation (estimate)',
            'model': ox['model'],
        }
    
    def _design_cooling_lines(self) -> List[Dict]:
        """Rejeneratif kanal listesi — sayı/kesit/debi GERÇEK hesaptan.

        Eskiden 180 kanal, 2x8 mm kesit, 0.8 m uzunluk ve h_g=2000 W/m²K
        varsayımıyla üretiliyordu; hiçbiri motorla değişmiyordu.
        """
        try:
            cooling = self.calculate_cooling_requirements()
        except Exception:
            return []
        n_channels = int(cooling.get('cooling_channels', 0))
        if n_channels <= 0:
            return []
        coolant_flow = cooling.get('coolant_flow_rate', 0.0)
        peak_flux_w = cooling.get('peak_heat_flux', 0.0) * 1000.0  # kW->W/m²
        length_m = (cooling.get('chamber_length', 0.0)
                    + cooling.get('nozzle_length', 0.0)) / 1000.0
        material, mat_key = self._material_record()

        channels = []
        for i in range(n_channels):
            channels.append({
                'id': i + 1,
                'position_angle': 2 * np.pi * i / n_channels,  # radians
                'width': cooling.get('channel_width_mm', 3.0) / 1000.0,   # m
                'height': cooling.get('channel_height_mm', 2.0) / 1000.0,  # m
                'length': length_m,  # m (chamber + nozzle)
                'flow_rate': coolant_flow / n_channels,  # kg/s per channel
                'peak_heat_flux': peak_flux_w,  # W/m² (Bartz, boğazda)
                'material': material.get('name', mat_key),
                'surface_treatment': 'milled and closed-out',
            })
        return channels

    def _calculate_heat_flux(self) -> float:
        """Boğazdaki tepe ısı akısı [W/m²] — Bartz hesabından.

        Eskiden h_g = 2000 W/m²K sabitiyle uyduruluyordu; artık
        calculate_cooling_requirements'ın Bartz katsayısından gelir.
        """
        try:
            cooling = self.calculate_cooling_requirements()
            return float(cooling.get('peak_heat_flux', 0.0)) * 1000.0
        except Exception:
            # Hesap düşerse UYDURMA değer döndürülmez.
            self._warn("Wall heat flux could not be computed for the cooling "
                       "line layout; the value is reported as zero rather "
                       "than assumed.")
            return 0.0
    
    @staticmethod
    def _haaland_friction(reynolds, relative_roughness):
        """Haaland (1983) açık sürtünme katsayısı; laminerde 64/Re."""
        re = max(float(reynolds), 1.0)
        if re < 2300.0:
            return 64.0 / re
        return (-1.8 * np.log10(6.9 / re
                                + (relative_roughness / 3.7) ** 1.11)) ** -2

    def _line_pressure_drops(self, mdot, density, viscosity, injector_dp_bar):
        """Tek besleme hattının kalem kalem basınç düşümü [bar].

        Darcy-Weisbach (White, "Fluid Mechanics" 7th ed., Eq. 6.10) + yerel
        kayıp katsayıları (Crane TP-410). Eskiden bu kalemler tamamen sabitti
        (0.1 / 0.5 / 0.3 / 1.2 / 3.0 bar) ve debi, çap, yoğunluk, viskozite
        hiç girmiyordu (2026-07-19 denetimi).
        """
        d_line = self._calculate_line_diameter(
            mdot, 'oxidizer' if density > 900 else 'fuel')
        area = np.pi * d_line ** 2 / 4.0
        velocity = mdot / max(density * area, 1e-9)
        dyn = 0.5 * density * velocity ** 2  # Pa (dinamik basınç)
        re = density * velocity * d_line / max(viscosity, 1e-9)
        f = self._haaland_friction(re, FEED_LINE_ROUGHNESS_M / d_line)

        line_dp = f * (FEED_LINE_LENGTH_DEFAULT_M / d_line) * dyn
        elbow_dp = FEED_ELBOW_COUNT * FEED_K_ELBOW * dyn
        return {
            'tank_outlet': FEED_K_TANK_OUTLET * dyn / PA_PER_BAR,
            'main_valve': FEED_K_MAIN_VALVE * dyn / PA_PER_BAR,
            'filters': FEED_K_FILTER * dyn / PA_PER_BAR,
            'feed_lines': (line_dp + elbow_dp) / PA_PER_BAR,
            'injector': float(injector_dp_bar),
            'line_diameter_mm': d_line * 1000.0,
            'line_velocity_m_s': velocity,
            'line_reynolds': re,
            'friction_factor': f,
        }

    def _calculate_feed_system_pressure_drops(self) -> Dict:
        """Besleme hattı basınç düşümleri — GERÇEK akış hesabı.

        Enjektör kalemi ``calculate_injector_design()`` sonucundan gelir
        (tek doğruluk kaynağı): eskiden burada 3.0 bar yazarken enjektör
        modülü aynı motor için 22 bar hesaplıyordu.
        """
        try:
            if not hasattr(self, 'mdot_fuel'):
                self.calculate_nozzle_geometry()  # kütle dengesi + geometri
            injector = self.calculate_injector_design()
            dp_inj_ox = injector['ox_pressure_drop']
            dp_inj_fuel = injector['fuel_pressure_drop']
        except Exception:
            dp_inj_ox = dp_inj_fuel = 0.0

        mdot_ox = getattr(self, 'mdot_ox', None)
        mdot_fuel = getattr(self, 'mdot_fuel', None)
        if mdot_ox is None or mdot_fuel is None:
            mdot_total = self.F / (getattr(self, 'isp_sl', 300.0) * self.g0)
            mdot_ox = mdot_total * self.MR / (1 + self.MR)
            mdot_fuel = mdot_total / (1 + self.MR)

        mu_ox = getattr(self, 'mu_ox', None) or 2.0e-4   # LOX ~0.19 mPa.s
        mu_fuel = getattr(self, 'mu_fuel', None) or 1.2e-3  # RP-1 ~1.2 mPa.s

        ox = self._line_pressure_drops(mdot_ox, self.rho_ox, mu_ox, dp_inj_ox)
        fuel = self._line_pressure_drops(mdot_fuel, self.rho_fuel, mu_fuel,
                                         dp_inj_fuel)
        keys = ('tank_outlet', 'main_valve', 'filters', 'feed_lines', 'injector')
        total_ox = sum(ox[k] for k in keys)
        total_fuel = sum(fuel[k] for k in keys)

        return {
            # Geriye uyum: tek değerli kalemler oksitleyici hattından gelir.
            'tank_outlet': ox['tank_outlet'],
            'main_valve': ox['main_valve'],
            'filters': ox['filters'],
            'feed_lines': ox['feed_lines'],
            'injector': ox['injector'],
            'total_ox': total_ox,
            'total_fuel': total_fuel,
            'oxidizer_line': ox,
            'fuel_line': fuel,
            'pump_discharge_pressure_ox': self.P_c + total_ox,
            'pump_discharge_pressure_fuel': self.P_c + total_fuel,
            'method': ('Darcy-Weisbach with Haaland friction factor plus '
                       'local loss coefficients (Crane TP-410); the injector '
                       'item is taken from the injector design'),
            'filter_note': ('filter/strainer loss uses an assumed loss '
                            f'coefficient K={FEED_K_FILTER:g}'),
        }
    
    # ------------------------------------------------------------------
    # ÇEVRİM GÜÇ DENGESİ entegrasyonu (2026-07-22, denetim madde 2/3)
    # ------------------------------------------------------------------
    def _cycle_line_dps(self):
        """(hat ΔP_ox, hat ΔP_yakıt, drops) [bar] — enjektör kalemi HARİÇ.

        Çevrim çözücüsü enjektör düşümünü ΔP/Pc oranı olarak kendisi
        uygular; buraya yalnız tank çıkışı + vana + filtre + hat kalemleri
        gider (çift sayma yasak).
        """
        drops = self._calculate_feed_system_pressure_drops()
        keys = ('tank_outlet', 'main_valve', 'filters', 'feed_lines')
        line_ox = float(sum(drops['oxidizer_line'][k] for k in keys))
        line_fuel = float(sum(drops['fuel_line'][k] for k in keys))
        return line_ox, line_fuel, drops

    def _injector_dp_fraction(self):
        """Enjektör ΔP/Pc oranı: kullanıcı girdisi > tip tablosu (tek kaynak)."""
        dp_user = getattr(self, 'injector_dp_input_bar', None)
        if dp_user is not None and self.P_c > 0:
            return float(dp_user) / float(self.P_c)
        return INJECTOR_TYPE_DP_FRACTION.get(self.injector_type,
                                             INJECTOR_TYPE_DP_FRACTION_DEFAULT)

    def _solve_cycle_balance(self, force=False):
        """Çevrim güç dengesini cycle_power_balance.solve_cycle ile kapatır.

        Denetim bulgusu (Bölüm 2a/2b/2f): staged/expander/tap_off seçimleri
        aynı gaz-jeneratörü hesabına düşüyor, güç dengesi kapanmıyor, türbin
        debisi Isp'den düşülmüyor, FFSC yoktu. Artık:

        * Pompa çıkış basıncı zinciri: Pc + enjektör ΔP + hat kalemleri +
          REJENERATİF KANAL ΔP (eskiden eksikti, satır ~2833-2849) +
          (staged/FFSC) ön yakıcı basınç merdiveni — çözücünün içinde.
        * Açık çevrimlerde (GG/tap-off) Isp kaybı debi-ağırlıklı karışımla
          hesaplanır; hem deniz seviyesi hem vakum ortamı için çözülür.
        * Desteklenmeyen yakıt/çevrim kombinasyonları sahte sayı üretmez:
          {'status': 'not_modelled', 'reason': ...} döner.

        Sonuç ``self._cycle_result`` içinde önbelleklenir (force ile tazele).
        """
        if not force and getattr(self, '_cycle_result', None) is not None:
            return self._cycle_result

        solver_name = CYCLE_SOLVER_NAME.get(
            getattr(self, 'engine_cycle', 'gas_generator'))
        out = {'status': 'not_modelled', 'engine_cycle': self.engine_cycle,
               'solver_cycle': solver_name}
        if solver_name is None:
            out['reason'] = f"unknown engine cycle '{self.engine_cycle}'"
            self._cycle_result = out
            return out

        try:
            from hrma.engines.cycle_power_balance import solve_cycle
        except Exception as exc:  # modül/scipy eksikliği — dürüst etiket
            out['reason'] = f'cycle_power_balance unavailable ({exc})'
            self._cycle_result = out
            return out

        if not hasattr(self, 'mdot_total'):
            self.calculate_nozzle_geometry()

        # Rejeneratif ceket ΔP'si ve ısı yükü (soğutma çözümünden — madde 3).
        regen_dp_bar = 0.0
        regen_heat_kw = None
        if self.cooling_type in ('regenerative', 'dump_cooling'):
            try:
                cooling = self.calculate_cooling_requirements()
                regen_dp_bar = float(cooling.get('cooling_pressure_drop', 0.0))
                regen_heat_kw = float(cooling.get('total_heat_load', 0.0))
            except Exception:
                pass

        line_ox, line_fuel, _ = self._cycle_line_dps()

        kwargs = dict(
            rho_ox=float(self.rho_ox), rho_fuel=float(self.rho_fuel),
            pump_inlet_ox_bar=PUMP_TANK_PRESSURE_DEFAULT_BAR,
            pump_inlet_fuel_bar=PUMP_TANK_PRESSURE_DEFAULT_BAR,
            line_dp_ox_bar=line_ox, line_dp_fuel_bar=line_fuel,
            regen_dp_bar=regen_dp_bar,
            injector_dp_frac=self._injector_dp_fraction(),
            eta_pump_ox=float(getattr(self, 'pump_efficiency',
                                      PUMP_EFFICIENCY_DEFAULT)),
            eta_pump_fuel=float(getattr(self, 'pump_efficiency',
                                        PUMP_EFFICIENCY_DEFAULT)),
            eta_turbine=TURBINE_EFFICIENCY_DEFAULT,
            preburner_mode=getattr(self, 'preburner_mode', 'fuel_rich'),
            regen_heat_kw=regen_heat_kw,
        )
        # TIT ve türbin PR yalnız KULLANICI girdiyse geçilir; girilmediyse
        # çözücünün çevrime özgü KAYNAKLI varsayılanları kullanılır
        # (GAS_GENERATOR_TEMP_DEFAULT_K genel amaçlı eski sabittir, staged
        # ox-rich sınırlarını bilmez).
        if 'generator_gas_temp' in self.overrides:
            kwargs['tit_K'] = float(self.turbine_inlet_temp)
        if 'turbine_expansion_ratio' in self.overrides:
            kwargs['turbine_pr'] = float(self.turbine_pressure_ratio)
        if self.engine_cycle == 'pressure_fed':
            kwargs['tank_pressure_bar'] = float(
                getattr(self, 'feed_pressure_input_bar', None)
                or PUMP_TANK_PRESSURE_DEFAULT_BAR)
        if self.engine_cycle == 'expander':
            kwargs['fuel_inlet_temp_K'] = CRYO_COOLANT_INLET_DEFAULT_K.get(
                self.fuel_type)

        # Ana oda (teslim edilmemiş) Isp'leri: çift sayma kilidi — açık
        # çevrim kaybı uygulandıktan sonra bile çözücüye HEP ana oda Isp'si
        # gider (isp_sl_main), motor Isp'si değil.
        isp_main_sl = float(getattr(self, 'isp_sl_main', self.isp_sl))
        isp_main_vac = float(getattr(self, 'isp_vac_main', self.isp_vac))

        try:
            sol = solve_cycle(solver_name, float(self.P_c),
                              float(self.mdot_total), float(self.MR),
                              self.fuel_type, self.oxidizer_type,
                              ambient_pressure_bar=float(self.P_a),
                              isp_main_s=isp_main_sl, **kwargs)
        except ValueError as exc:
            out['reason'] = str(exc)
            self._cycle_result = out
            return out
        except Exception as exc:
            out['reason'] = f'{type(exc).__name__}: {exc}'
            self._cycle_result = out
            return out

        out = sol.to_dict()
        out['engine_cycle'] = self.engine_cycle
        out['solver_cycle'] = solver_name
        out['status'] = 'converged' if sol.converged else 'not_converged'
        out['isp_main_sl_s'] = isp_main_sl
        out['isp_main_vac_s'] = isp_main_vac
        out['mdot_total_pumped_kg_s'] = float(self.mdot_total)

        # Açık çevrimde vakum tarafı: aynı denge, vakum ortamıyla (türbin
        # egzozunun vakumda daha yüksek Isp'si kayıp hesabına girer).
        if sol.converged and sol.isp_mode == 'open_cycle_mixture_average':
            out['isp_engine_sl_s'] = sol.isp_engine_s
            out['isp_loss_sl_s'] = sol.isp_loss_s
            try:
                sol_vac = solve_cycle(solver_name, float(self.P_c),
                                      float(self.mdot_total), float(self.MR),
                                      self.fuel_type, self.oxidizer_type,
                                      ambient_pressure_bar=1e-6,
                                      isp_main_s=isp_main_vac, **kwargs)
                if sol_vac.converged and sol_vac.isp_engine_s is not None:
                    out['isp_engine_vac_s'] = sol_vac.isp_engine_s
                    out['isp_loss_vac_s'] = sol_vac.isp_loss_s
                    out['secondary_exhaust_isp_vac_s'] = \
                        sol_vac.secondary_exhaust_isp_s
            except Exception:
                pass
        elif sol.converged:
            out['isp_engine_sl_s'] = isp_main_sl
            out['isp_engine_vac_s'] = isp_main_vac
            out['isp_loss_sl_s'] = sol.isp_loss_s
            out['isp_loss_vac_s'] = sol.isp_loss_s

        self._cycle_result = out
        return out

    def _apply_cycle_accounting(self):
        """Açık çevrim Isp kaybını TESLİM Isp'ye işler (bir kez, debi tutarlı).

        Muhasebe (Sutton Ch. 6): motor Isp'si = (ṁ_ana·Isp_ana +
        ṁ_türbin·Isp_egzoz)/ṁ_toplam. Komuta edilen itki motor SEVİYESİNDE
        korunur: ṁ_toplam = F/(Isp_motor·g0) pompalanan toplamdır; ana oda
        boğazı (A_t) pompalanan toplamın türbin debisi DÜŞÜLMÜŞ kısmıyla
        boyutlanır (_main_chamber_flow_fraction). Kapalı çevrimlerde kayıp
        sıfırdır ve hiçbir şey değişmez. Çift sayma kilidi: ana oda Isp'si
        isp_sl_main/isp_vac_main olarak saklanır; çözücüye hep o gider.
        """
        cyc = self._solve_cycle_balance()
        if cyc.get('status') != 'converged':
            return cyc
        if cyc.get('isp_mode') != 'open_cycle_mixture_average':
            # Kapalı çevrim / pressure-fed: kayıp yok; ana oda debi kesri
            # yine de raporlanır (türbin debisi kapalı çevrimde ana odaya
            # döner, boğaz TOPLAM debiyle boyutlanır).
            return cyc
        if getattr(self, '_cycle_isp_applied', False):
            return cyc

        # Ana oda Isp'lerini kilitle (çift sayma koruması).
        self.isp_sl_main = float(self.isp_sl)
        self.isp_vac_main = float(self.isp_vac)

        for _ in range(3):
            isp_sl_eng = cyc.get('isp_engine_sl_s')
            isp_vac_eng = cyc.get('isp_engine_vac_s')
            if not isp_sl_eng or not isp_vac_eng:
                break
            rel = abs(isp_sl_eng - self.isp_sl) / max(self.isp_sl, 1e-9)
            self.isp_sl = float(isp_sl_eng)
            self.isp_vac = float(isp_vac_eng)
            pumped = cyc.get('mdot_total_pumped_kg_s') or self.mdot_total
            bleed = cyc.get('turbine_mdot_total_kg_s', 0.0)
            self._main_chamber_flow_fraction = float(
                max(1.0 - bleed / max(pumped, 1e-9), 0.5))
            # Yeni motor Isp'siyle debi/boğaz güncellenir, denge yeniden
            # kapatılır (kayıp debiyle zayıf değişir; 2-3 tur yeter).
            self.calculate_nozzle_geometry()
            cyc = self._solve_cycle_balance(force=True)
            if rel < 1e-4:
                break
        self._cycle_isp_applied = True
        return cyc

    def _estimate_feed_system_mass(self) -> float:
        """Besleme sistemi kuru kütlesi [kg] — bileşen dökümüyle TEK kaynak.

        Eskiden 50 kg tabanlı ayrı bir ampirik formüldü ve aynı sonuçtaki
        component_sizing dökümüyle çelişiyordu (2026-07-19 denetimi).
        """
        try:
            masses = self._detailed_component_sizing()['component_masses']
            return float(masses['feed_system'] + masses['turbopump_assembly'])
        except Exception:
            # Hesap düşerse UYDURMA taban değer döndürülmez.
            self._warn("Feed system dry mass could not be derived from the "
                       "component breakdown; it is reported as zero rather "
                       "than assumed.")
            return 0.0
    
    def _design_propellant_tanks(self):
        """Design detailed propellant tank system with internal structures"""
        
        # Mission parameters for tank sizing
        burn_time, burn_time_source = self._burn_time()
        # v2.5.2 (Codex bulgusu liquid:2450): rezerv payı ve ullage artık
        # modül sabitlerinden gelir ve besleme sistemi kartıyla AYNI modeli
        # (_size_tank) besler. Eskiden burada 1.15 rezerv + %5 ullage,
        # besleme yolunda ise rezervsiz %20 çarpanı vardı; aynı koşuda iki
        # farklı "tank hacmi" görünüyordu.
        safety_margin = TANK_PROPELLANT_RESERVE_FACTOR
        ullage_fraction = TANK_ULLAGE_FRACTION

        # Mass flow rates
        mdot_ox = getattr(self, 'mdot_ox', self.mdot_total * self.MR / (1 + self.MR))
        mdot_fuel = getattr(self, 'mdot_fuel', self.mdot_total / (1 + self.MR))

        # Yüklenen itici kütlesi (rezerv payı _size_tank içinde uygulanır)
        ox_mass_nominal = mdot_ox * burn_time  # kg
        fuel_mass_nominal = mdot_fuel * burn_time  # kg
        ox_mass = ox_mass_nominal * safety_margin  # kg (rezerv dahil)
        fuel_mass = fuel_mass_nominal * safety_margin  # kg

        # Tank hacimleri — TEK model, kullanıcı yoğunluğu en yüksek öncelikli
        ox_tank_volume, ox_volume_req, rho_ox, rho_ox_source = \
            self._size_tank(ox_mass_nominal, 'oxidizer')
        fuel_tank_volume, fuel_volume_req, rho_fuel, rho_fuel_source = \
            self._size_tank(fuel_mass_nominal, 'fuel')

        # Tank dimensions (optimized for minimum surface area = sphere, but use cylinder for practicality)
        # Length/Diameter ratio = 2.5 for good structural efficiency
        ld_ratio = 2.5

        # Oxidizer tank (larger, typically)
        ox_tank_diameter = (4 * ox_tank_volume / (np.pi * ld_ratio))**(1/3)
        ox_tank_length = ox_tank_diameter * ld_ratio

        # Fuel tank
        fuel_tank_diameter = (4 * fuel_tank_volume / (np.pi * ld_ratio))**(1/3)
        fuel_tank_length = fuel_tank_diameter * ld_ratio
        
        # Pressure requirements
        feed_pressure = self.P_c * 1e5 + 500000  # Pa (5 bar margin above chamber pressure)
        if self.feed_system_type == 'pressure_fed':
            tank_pressure = feed_pressure * 1.2  # 20% margin
        else:  # turbopump
            tank_pressure = 300000  # 3 bar for NPSH
        
        # Wall thickness calculation (thin-walled pressure vessel)
        material_strength = 350e6  # Pa (typical for Al-Li alloy)
        safety_factor = 2.5
        allowable_stress = material_strength / safety_factor
        
        ox_wall_thickness = (tank_pressure * ox_tank_diameter/2) / allowable_stress
        fuel_wall_thickness = (tank_pressure * fuel_tank_diameter/2) / allowable_stress
        
        # Minimum practical thickness
        ox_wall_thickness = max(ox_wall_thickness, 0.003)  # 3mm minimum
        fuel_wall_thickness = max(fuel_wall_thickness, 0.003)  # 3mm minimum
        
        # Internal structures design
        ox_tank_internals = self._design_tank_internals(ox_tank_diameter, ox_tank_length, 'oxidizer')
        fuel_tank_internals = self._design_tank_internals(fuel_tank_diameter, fuel_tank_length, 'fuel')
        
        # Tank mass estimation
        ox_tank_surface_area = np.pi * ox_tank_diameter * ox_tank_length + 2 * np.pi * (ox_tank_diameter/2)**2
        fuel_tank_surface_area = np.pi * fuel_tank_diameter * fuel_tank_length + 2 * np.pi * (fuel_tank_diameter/2)**2
        
        material_density = 2700  # kg/m³ (aluminum)
        ox_tank_mass = ox_tank_surface_area * ox_wall_thickness * material_density
        fuel_tank_mass = fuel_tank_surface_area * fuel_wall_thickness * material_density
        
        # Add internal structure mass
        ox_tank_mass += ox_tank_internals['mass_breakdown']['total_mass']
        fuel_tank_mass += fuel_tank_internals['mass_breakdown']['total_mass']
        
        return {
            'oxidizer_tank': {
                'propellant_type': self.oxidizer_type.upper(),
                'dimensions': {
                    'diameter': ox_tank_diameter * 1000,  # mm
                    'length': ox_tank_length * 1000,  # mm
                    'volume': ox_tank_volume * 1000,  # liters
                    'wall_thickness': ox_wall_thickness * 1000,  # mm
                    'ld_ratio': ld_ratio
                },
                'propellant_data': {
                    'mass': ox_mass,  # kg
                    'density': rho_ox,  # kg/m³
                    'density_source': rho_ox_source,
                    'volume_required': ox_volume_req * 1000,  # liters
                    'ullage_volume': (ox_tank_volume - ox_volume_req) * 1000  # liters
                },
                'structural': {
                    'material': 'Aluminum-Lithium 2195',
                    'pressure_rating': tank_pressure / 1e5,  # bar
                    'safety_factor': safety_factor,
                    'tank_mass': ox_tank_mass,  # kg
                    'mass_fraction': ox_tank_mass / ox_mass  # tank mass / propellant mass
                },
                'internal_structures': ox_tank_internals
            },
            'fuel_tank': {
                'propellant_type': self.fuel_type.upper(),
                'dimensions': {
                    'diameter': fuel_tank_diameter * 1000,  # mm
                    'length': fuel_tank_length * 1000,  # mm
                    'volume': fuel_tank_volume * 1000,  # liters
                    'wall_thickness': fuel_wall_thickness * 1000,  # mm
                    'ld_ratio': ld_ratio
                },
                'propellant_data': {
                    'mass': fuel_mass,  # kg
                    'density': rho_fuel,  # kg/m³
                    'density_source': rho_fuel_source,
                    'volume_required': fuel_volume_req * 1000,  # liters
                    'ullage_volume': (fuel_tank_volume - fuel_volume_req) * 1000  # liters
                },
                'structural': {
                    'material': 'Aluminum-Lithium 2195' if self.fuel_type != 'lh2' else 'Stainless Steel 316L',
                    'pressure_rating': tank_pressure / 1e5,  # bar
                    'safety_factor': safety_factor,
                    'tank_mass': fuel_tank_mass,  # kg
                    'mass_fraction': fuel_tank_mass / fuel_mass,  # tank mass / propellant mass
                    'insulation': 'Multi-Layer Insulation (MLI)' if self.fuel_type == 'lh2' else 'None'
                },
                'internal_structures': fuel_tank_internals
            },
            'system_summary': {
                'total_propellant_mass': ox_mass + fuel_mass,  # kg
                'total_tank_mass': ox_tank_mass + fuel_tank_mass,  # kg
                'total_volume': (ox_tank_volume + fuel_tank_volume) * 1000,  # liters
                'overall_mass_fraction': (ox_tank_mass + fuel_tank_mass) / (ox_mass + fuel_mass),
                'burn_time': burn_time,  # seconds
                'burn_time_source': burn_time_source,
                'safety_margin': (safety_margin - 1) * 100,  # %
                'ullage_fraction': ullage_fraction * 100,  # %
                # Besleme sistemi kartı da bu modeli kullanır (_size_tank);
                # iki kart artık aynı hacmi gösterir.
                'sizing_model': ('single tank-sizing model: '
                                 'V_tank = (m_propellant x reserve) / rho '
                                 '/ (1 - ullage)'),
                'oxidizer_density_source': rho_ox_source,
                'fuel_density_source': rho_fuel_source,
            }
        }
    
    def _design_tank_internals(self, diameter, length, propellant_type):
        """Design internal tank structures (baffles, anti-vortex, etc.)"""
        
        # Tank internal structures
        radius = diameter / 2
        
        # Anti-vortex device at outlet
        anti_vortex = {
            'type': 'Radial vanes',
            'diameter': diameter * 0.3,  # 30% of tank diameter
            'height': diameter * 0.1,    # 10% of tank diameter
            'vane_count': 8,
            'vane_thickness': 3,  # mm
            'material': 'Aluminum 6061-T6'
        }
        
        # Slosh baffles (for liquid control during acceleration)
        baffle_count = max(2, int(length / diameter))  # At least 2, more for long tanks
        baffles = []
        
        for i in range(baffle_count):
            baffle_position = (i + 1) * length / (baffle_count + 1)  # Evenly spaced
            
            # Ring baffle with holes for propellant flow
            hole_area_ratio = 0.15  # 15% open area
            hole_diameter = 0.05  # 50mm holes
            holes_per_baffle = int((np.pi * diameter * hole_area_ratio) / (np.pi * (hole_diameter/2)**2))
            
            baffle = {
                'position': baffle_position * 1000,  # mm from bottom
                'type': 'Perforated ring',
                'outer_diameter': diameter * 0.95 * 1000,  # mm (slightly smaller than tank)
                'inner_diameter': diameter * 0.2 * 1000,   # mm (central opening)
                'thickness': 2,  # mm
                'hole_diameter': hole_diameter * 1000,  # mm
                'hole_count': holes_per_baffle,
                'open_area_ratio': hole_area_ratio * 100,  # %
                'material': 'Aluminum 6061-T6'
            }
            baffles.append(baffle)
        
        # Inlet/Outlet configurations
        if propellant_type == 'oxidizer':
            # Oxidizer typically enters from top, exits from bottom
            inlet = {
                'position': 'Top center',
                'type': 'Diffuser',
                'diameter': 100,  # mm
                'diffuser_angle': 15,  # degrees
                'diffuser_length': 200,  # mm
                'purpose': 'Reduce velocity and prevent splashing'
            }
            
            outlet = {
                'position': 'Bottom center',
                'type': 'Sump with anti-vortex',
                'diameter': 150,  # mm
                'sump_depth': 50,  # mm
                'screen_mesh': '200 mesh (74 micron)',
                'purpose': 'Ensure bubble-free propellant supply'
            }
        else:
            # Fuel configuration
            inlet = {
                'position': 'Top side',
                'type': 'Tangential entry' if self.fuel_type == 'lh2' else 'Axial diffuser',
                'diameter': 80,  # mm
                'swirl_angle': 30 if self.fuel_type == 'lh2' else 0,  # degrees
                'purpose': 'Minimize heat input (LH2) or turbulence (others)'
            }
            
            outlet = {
                'position': 'Bottom center',
                'type': 'Standpipe with anti-vortex',
                'diameter': 120,  # mm
                'standpipe_height': 100,  # mm
                'anti_vortex_height': anti_vortex['height'] * 1000,  # mm
                'purpose': 'Prevent gas ingestion during low-g phases'
            }
        
        # Instrumentation ports
        instrumentation = {
            'pressure_transducers': 2,
            'temperature_sensors': 3 if self.fuel_type == 'lh2' else 1,
            'level_sensors': {
                'type': 'Capacitive probes',
                'count': 4,
                'positions': [0.25, 0.5, 0.75, 0.95]  # Fractional tank height
            },
            'relief_valve': {
                'diameter': 25,  # mm
                'set_pressure': self.P_c * 1.5,  # bar (50% above chamber pressure)
                'position': 'Top of tank'
            }
        }
        
        # Mass estimation for internal structures
        anti_vortex_mass = 2.5  # kg (typical)
        baffle_total_mass = len(baffles) * 3.0  # kg each
        plumbing_mass = 15.0  # kg (inlet, outlet, instrumentation)
        
        total_internal_mass = anti_vortex_mass + baffle_total_mass + plumbing_mass
        
        return {
            'anti_vortex_device': anti_vortex,
            'slosh_baffles': baffles,
            'inlet_configuration': inlet,
            'outlet_configuration': outlet,
            'instrumentation': instrumentation,
            'mass_breakdown': {
                'anti_vortex': anti_vortex_mass,  # kg
                'baffles': baffle_total_mass,      # kg
                'plumbing': plumbing_mass,         # kg
                'total_mass': total_internal_mass  # kg
            },
            'design_features': {
                'slosh_damping': f'{baffle_count} perforated ring baffles',
                'vortex_prevention': 'Radial vane anti-vortex device',
                'propellant_settling': 'Ullage gas pressurization system',
                'thermal_management': 'MLI insulation' if self.fuel_type == 'lh2' else 'Passive radiation'
            }
        }
    
    def _design_pump(self, mdot, density, discharge_pressure_bar, tank_pressure_bar):
        """Tek pompanın benzerlik tabanlı tasarımı (sabit eğri YOK).

        2026-07-19 denetimi: H-Q ve verim eğrileri uydurma parabollerden
        (1.2 − 0.8·(Q/Q0−1)², 0.78·(1−2.5·(Q/Q0−1)²)) geliyordu; devir 25000
        rpm ve uç hızı 400 m/s her motorda aynıydı. Yeni zincir:

        * Basma yüksekliği H = ΔP/(ρ·g) — gerçek basınç yükselmesinden.
        * NPSH_a = (P_tank − P_buhar)/(ρ·g); devir emme özgül hızından:
          ω = ω_ss·(g·NPSH_a)^0.75/√Q (Huzel & Huang Ch. 6).
        * Çark uç hızı U2, kanat çıkış açısı β2 ve Stodola kayma faktörü ile
          Euler denkleminden ÇÖZÜLÜR: H = η_h·(σ·U2² − U2·Q/(A2·tanβ2))/g.
        * H-Q eğrisi aynı Euler bağıntısının Q'ya göre değerlendirilmesidir
          (parabol uydurma değil).
        * Verim eğrisi giriş-kaybı (incidence) modelidir ve BEP verimi
          kullanıcı girdisinden gelir — etiketi çıktıda taşınır.
        """
        g0 = self.g0
        q = mdot / max(density, 1e-9)                     # m³/s
        dp = max((discharge_pressure_bar - tank_pressure_bar), 1.0) * PA_PER_BAR
        head = dp / (density * g0)                        # m

        npsh_avail = max((tank_pressure_bar - PUMP_NPSH_VAPOR_PRESSURE_BAR)
                         * PA_PER_BAR, 1e3) / (density * g0)  # m
        omega = (PUMP_SUCTION_SPECIFIC_SPEED * (g0 * npsh_avail) ** 0.75
                 / max(np.sqrt(q), 1e-9))                 # rad/s
        rpm = omega * 60.0 / (2.0 * np.pi)
        speed_source = 'cavitation limit (suction specific speed)'
        if rpm > PUMP_MAX_SPEED_RPM:
            rpm = PUMP_MAX_SPEED_RPM
            omega = rpm * 2.0 * np.pi / 60.0
            speed_source = f'capped at the {PUMP_MAX_SPEED_RPM:.0f} rpm practical limit'
            self._warn(
                f"The cavitation limit would allow a shaft speed above "
                f"{PUMP_MAX_SPEED_RPM:.0f} rpm for this small flow rate; the "
                f"pump speed is capped at the practical limit.")

        beta2 = np.radians(PUMP_BLADE_EXIT_ANGLE_DEG)
        slip = 1.0 - np.pi * np.sin(beta2) / PUMP_BLADE_COUNT  # Stodola
        eta_h = PUMP_HYDRAULIC_EFFICIENCY

        # H = eta_h/g · (slip·U2² − U2·Q/(A2·tanβ2)), A2 = π·D2·b2, D2 = 2U2/ω
        # -> A2 = 2π·U2·(b2/D2)·(2/ω) ... U2 cinsinden çözülür:
        # A2 = π·D2·b2 = π·(2U2/ω)²·(b2/D2)  (b2 = (b2/D2)·D2)
        # => A2 = π·(2U2/ω)²·PUMP_EXIT_WIDTH_RATIO
        def head_of_u2(u2):
            d2 = 2.0 * u2 / omega
            a2 = np.pi * d2 ** 2 * PUMP_EXIT_WIDTH_RATIO
            return eta_h * (slip * u2 ** 2
                            - u2 * q / (a2 * np.tan(beta2))) / g0

        from scipy.optimize import brentq
        try:
            u2 = float(brentq(lambda u: head_of_u2(u) - head, 1.0, 2000.0,
                              xtol=1e-6))
        except Exception:
            # Kaymasız yaklaşık çözüm (ikinci dereceden terim baskın)
            u2 = float(np.sqrt(head * g0 / (eta_h * slip)))
        d2 = 2.0 * u2 / omega
        a2 = np.pi * d2 ** 2 * PUMP_EXIT_WIDTH_RATIO

        eta_bep = float(getattr(self, 'pump_efficiency',
                                PUMP_EFFICIENCY_DEFAULT))
        flow_ratios = np.linspace(PUMP_CURVE_FLOW_MIN, PUMP_CURVE_FLOW_MAX,
                                  PUMP_CURVE_POINTS)
        flow_range, head_curve, eff_curve, power_curve, npsh_curve = \
            [], [], [], [], []
        for fr in flow_ratios:
            q_i = q * fr
            h_i = eta_h * (slip * u2 ** 2
                           - u2 * q_i / (a2 * np.tan(beta2))) / g0
            # Giriş kaybı modeli (Stepanoff): BEP dışında kuadratik düşüş.
            eta_i = eta_bep * (1.0 - (fr - 1.0) ** 2)
            eta_i = float(min(max(eta_i, 0.05), 0.95))
            # NPSH_req: emme özgül hızı tanımının tersi
            npsh_i = ((omega * np.sqrt(max(q_i, 1e-12))
                       / PUMP_SUCTION_SPECIFIC_SPEED) ** (4.0 / 3.0)) / g0
            flow_range.append(q_i * density)              # kg/s
            head_curve.append(float(h_i))
            eff_curve.append(eta_i * 100.0)
            power_curve.append(float(density * g0 * max(h_i, 0.0) * q_i
                                     / (eta_i * 1000.0)))  # kW
            npsh_curve.append(float(npsh_i))

        power_design = density * g0 * head * q / (eta_bep * 1000.0)  # kW
        npsh_req = ((omega * np.sqrt(max(q, 1e-12))
                     / PUMP_SUCTION_SPECIFIC_SPEED) ** (4.0 / 3.0)) / g0
        if npsh_req > npsh_avail:
            self._warn(
                f"Pump NPSH required ({npsh_req:.1f} m) exceeds the available "
                f"NPSH ({npsh_avail:.1f} m) at the assumed tank pressure; "
                f"raise the tank pressure or add an inducer.")
        return {
            'design_flow_rate': mdot,                     # kg/s
            'volumetric_flow_m3_s': q,
            'design_head': head,                          # m
            'design_efficiency': eta_bep * 100.0,          # %
            'efficiency_source': ('user input (turbopump efficiency)'
                                  if 'turbopump_efficiency' in self.overrides
                                  else 'default best-efficiency-point value'),
            'design_power': power_design,                 # kW
            'rotational_speed': rpm,                      # rpm
            'speed_source': speed_source,
            'impeller_tip_speed': u2,                     # m/s
            'impeller_diameter': d2,                      # m
            'slip_factor': slip,
            'npsh_available': npsh_avail,                 # m
            'npsh_required': npsh_req,                    # m
            'flow_range': flow_range,
            'head_curve': head_curve,
            'efficiency_curve': eff_curve,
            'power_curve': power_curve,
            'npsh_curve': npsh_curve,
            'model': ('Euler head with Stodola slip, speed set by the suction '
                      'specific speed; efficiency curve is an incidence-loss '
                      'model anchored at the BEP efficiency '
                      '(similarity-scaled estimate)'),
        }

    def _analyze_detailed_feed_system(self):
        """Comprehensive feed system analysis with turbopump performance maps

        2026-07-22 (denetim madde 2): pompa çıkış basınçları artık ÇEVRİM
        çözümünden gelir (staged/FFSC'de ön yakıcı basınç merdiveni +
        rejeneratif ΔP dahil). Çevrim çözülemiyorsa eski Pc+hat zinciri
        korunur ve kaynak etiketlenir.
        """

        mdot_total = getattr(self, 'mdot_total',
                             self.F / (getattr(self, 'isp_sl', 300.0) * G_0))
        mdot_ox = getattr(self, 'mdot_ox', mdot_total * self.MR / (1 + self.MR))
        mdot_fuel = getattr(self, 'mdot_fuel', mdot_total / (1 + self.MR))

        drops = self._calculate_feed_system_pressure_drops()
        cycle_solution = self._solve_cycle_balance()
        if (cycle_solution.get('status') == 'converged'
                and cycle_solution.get('pump_discharge_ox_bar')):
            # Çevrim kapanışından gelen GERÇEK basma basınçları (rejeneratif
            # ΔP ve ön yakıcı merdiveni dahil) pompa tasarımını sürer.
            drops = dict(drops)
            drops['pump_discharge_pressure_ox'] = float(
                cycle_solution['pump_discharge_ox_bar'])
            drops['pump_discharge_pressure_fuel'] = float(
                cycle_solution['pump_discharge_fuel_bar'])
            drops['discharge_pressure_source'] = (
                'cycle power balance (preburner ladder + regenerative '
                'channel drop included)')
        else:
            drops = dict(drops)
            drops['discharge_pressure_source'] = (
                'chamber pressure plus line/injector losses (cycle balance '
                'not available)')
        # Tank basıncı: BASINÇ BESLEMELİ çevrimde kullanıcının 'feed pressure'
        # girdisi tankın kendisidir; turbopompalı çevrimde tank yalnız NPSH
        # için basınçlandırılır ve feed_pressure pompa ÇIKIŞ hedefidir.
        feed_input = getattr(self, 'feed_pressure_input_bar', None)
        pressure_fed = getattr(self, 'engine_cycle', '') == 'pressure_fed'
        if pressure_fed:
            tank_bar = feed_input or PUMP_TANK_PRESSURE_DEFAULT_BAR
            if tank_bar < drops['pump_discharge_pressure_ox']:
                self._warn(
                    f"Pressure-fed cycle: the entered feed (tank) pressure "
                    f"{tank_bar:g} bar is below the "
                    f"{drops['pump_discharge_pressure_ox']:.1f} bar needed to "
                    f"push the propellant through the lines and the injector "
                    f"into a {self.P_c:g} bar chamber.")
        else:
            tank_bar = PUMP_TANK_PRESSURE_DEFAULT_BAR
            if feed_input is not None and feed_input < drops[
                    'pump_discharge_pressure_ox']:
                self._warn(
                    f"Entered feed pressure {feed_input:g} bar is below the "
                    f"{drops['pump_discharge_pressure_ox']:.1f} bar pump "
                    f"discharge pressure required by the chamber pressure and "
                    f"the computed line/injector losses.")
        ox_pump = self._design_pump(mdot_ox, self.rho_ox,
                                    drops['pump_discharge_pressure_ox'],
                                    tank_bar)
        fuel_pump = self._design_pump(mdot_fuel, self.rho_fuel,
                                      drops['pump_discharge_pressure_fuel'],
                                      tank_bar)

        # Türbin: gerekli güç pompalardan; uç hızı gerçek özgül işten.
        eta_turbine = TURBINE_EFFICIENCY_DEFAULT
        turbine_power = (ox_pump['design_power']
                         + fuel_pump['design_power']) / eta_turbine  # kW
        t_in = float(getattr(self, 'turbine_inlet_temp',
                             GAS_GENERATOR_TEMP_DEFAULT_K))
        # Basınç oranı ÖNCELİĞİ kullanıcının doğrudan girdiği türbin genişleme
        # oranındadır; ayrıca türbin giriş basıncı girildiyse ikisi
        # karşılaştırılır ve tutarsızlık sessiz kalmaz.
        pr = float(getattr(self, 'turbine_pressure_ratio',
                           TURBINE_PRESSURE_RATIO_DEFAULT))
        p_in = getattr(self, 'turbine_inlet_pressure_bar', None)
        if p_in:
            pr_from_inlet = max(p_in / self.P_a, 1.2)
            if abs(pr_from_inlet - pr) / pr > INPUT_CONSISTENCY_TOLERANCE:
                self._warn(
                    f"Turbine inlet pressure {p_in:g} bar implies an expansion "
                    f"ratio of {pr_from_inlet:.1f} against ambient, while the "
                    f"entered turbine expansion ratio is {pr:.1f}; the entered "
                    f"expansion ratio is used.")
        # Δh = cp·T_in·(1 − PR^(−(γ−1)/γ)) (izentropik iş, Sutton Ch. 10)
        delta_h = (TURBINE_GAS_CP_J_KGK * t_in
                   * (1.0 - pr ** (-(TURBINE_GAS_GAMMA - 1.0)
                                   / TURBINE_GAS_GAMMA)))
        c0 = np.sqrt(2.0 * delta_h)                   # spouting velocity, m/s
        blade_tip_speed = TURBINE_VELOCITY_RATIO * c0
        if blade_tip_speed > TURBINE_TIP_SPEED_LIMIT_MS:
            self._warn(
                f"Single-stage turbine blade tip speed {blade_tip_speed:.0f} "
                f"m/s exceeds the {TURBINE_TIP_SPEED_LIMIT_MS:.0f} m/s "
                f"practical limit at this pressure ratio and inlet "
                f"temperature; a multi-stage turbine would be required.")
        turbine_mdot = turbine_power * 1000.0 / max(delta_h * eta_turbine, 1.0)

        gg_mdot = mdot_total * GAS_GENERATOR_FLOW_FRACTION
        gg_chamber_pressure = self.P_c * GAS_GENERATOR_PRESSURE_RATIO

        # Çevrim çözümü varsa türbin/ön yakıcı kartı ONDAN gelir (sabit %5
        # GG debisi ve genel PR varsayımı yerine kapanan denge — madde 2).
        turbine_card = {
            'type': 'Single-stage axial',
            'power_output': turbine_power,  # kW
            'inlet_temperature': t_in,  # K
            'inlet_temperature_source': (
                'user input (gas generator temperature)'
                if 'generator_gas_temp' in self.overrides
                else 'assumed gas-generator temperature'),
            'pressure_ratio': pr,
            'efficiency': eta_turbine * 100.0,  # %
            'rotational_speed': ox_pump['rotational_speed'],  # rpm
            'blade_tip_speed': blade_tip_speed,  # m/s
            'specific_work_J_kg': delta_h,
            'mass_flow_rate': turbine_mdot,  # kg/s
            'model': ('isentropic single-stage work with U/C0='
                      f'{TURBINE_VELOCITY_RATIO:g} optimum velocity '
                      'ratio'),
        }
        gg_card = {
            'mass_flow_rate': gg_mdot,  # kg/s
            'mixture_ratio': 0.8,  # Rich mixture for temperature control
            'chamber_pressure': gg_chamber_pressure,  # bar
            'temperature': t_in,  # K
            'flow_fraction': GAS_GENERATOR_FLOW_FRACTION * 100  # %
        }
        if (cycle_solution.get('status') == 'converged'
                and cycle_solution.get('shafts')):
            shaft0 = cycle_solution['shafts'][0]
            turb0 = shaft0.get('turbine') or {}
            turbine_card.update({
                'power_output': cycle_solution['turbine_power_total_W'] / 1e3,
                'inlet_temperature': turb0.get('inlet_temp_K', t_in),
                'inlet_temperature_source': 'cycle power balance solution',
                'pressure_ratio': turb0.get('pressure_ratio', pr),
                'mass_flow_rate':
                    cycle_solution['turbine_mdot_total_kg_s'],
                'specific_work_J_kg': turb0.get('specific_work_J_kg',
                                                delta_h),
                'shaft_count': len(cycle_solution['shafts']),
                'model': ('cycle power balance (per-shaft closure; see '
                          'engine_cycle_solution)'),
            })
            if cycle_solution.get('preburners'):
                pb0 = cycle_solution['preburners'][0]
                gg_card = {
                    'mass_flow_rate': pb0['mdot_total_kg_s'],
                    'mixture_ratio': pb0['of_ratio'],
                    'chamber_pressure': pb0['pressure_bar'],
                    'temperature': pb0['temperature_K'],
                    'flow_fraction': (
                        pb0['mdot_total_kg_s'] / max(mdot_total, 1e-9)
                        * 100.0),
                    'mode': pb0.get('mode'),
                    'source': 'cycle power balance solution',
                }

        return {
            'feed_system_type': self.feed_system_type,
            'engine_cycle': getattr(self, 'engine_cycle', 'gas_generator'),
            # Tam çevrim kapanışı (mil başına döküm, ön yakıcılar, Isp
            # muhasebesi, uyarılar) — UI çevrim paneli bunu okur.
            'engine_cycle_solution': cycle_solution,
            'pump_discharge_source': drops.get('discharge_pressure_source'),
            'turbopump_analysis': {
                'oxidizer_pump': ox_pump,
                'fuel_pump': fuel_pump,
                'turbine': turbine_card,
                'gas_generator': gg_card,
            },
            'turbopump_required': not pressure_fed,
            'tank_pressure_bar': tank_bar,
            'tank_pressure_margin_bar': (
                tank_bar - drops['pump_discharge_pressure_ox']
                if pressure_fed else None),
            'feed_pressure_input_bar': feed_input,
            'required_pump_discharge_bar': drops['pump_discharge_pressure_ox'],
            'performance_margins': {
                # Marjlar hesaplanan büyüklüklerden gelir (sabit değil).
                'flow_margin': (PUMP_CURVE_FLOW_MAX - 1.0) * 100.0,
                'pressure_margin': (
                    (drops['pump_discharge_pressure_ox'] - self.P_c)
                    / max(self.P_c, 1e-9) * 100.0),
                'power_margin': (1.0 / TURBINE_EFFICIENCY_DEFAULT - 1.0) * 100.0,
                'npsh_margin': (
                    (ox_pump['npsh_available'] - ox_pump['npsh_required'])
                    / max(ox_pump['npsh_required'], 1e-9) * 100.0),
            }
        }
    
    def _analyze_combustion_chamber_detailed(self):
        """Detailed combustion chamber analysis with mixing efficiency"""
        
        # Chamber geometry
        # DENETIM DUZELTMESI (Bulgu 5): eski kod chamber_length = c_star*1.2/1000
        # ile karakteristik HIZ c* (m/s) ile karakteristik UZUNLUK L*'i (m)
        # karistiriyordu (~21x fazla uzunluk; l_star raporu 25 m cikiyordu).
        # Dogru yontem: V_c = L* * A_t; L_c = V_c / A_c.
        d_t = getattr(self, 'd_t', 0.03)  # Default throat diameter
        # Hazne çapı ve L* kullanıcı girdisinden (tek doğruluk kaynağı).
        chamber_diameter = self._chamber_diameter()  # m
        L_star = self._l_star()  # m, karakteristik uzunluk
        A_throat = np.pi * (d_t**2) / 4  # m²
        A_chamber_cross = np.pi * (chamber_diameter**2) / 4  # m²
        chamber_volume = L_star * A_throat  # m³ (V_c = L* * A_t)
        chamber_length = chamber_volume / A_chamber_cross  # m
        
        # Combustion efficiency analysis
        mdot_total = getattr(self, 'mdot_total', self.F / (300 * G_0))
        rho_ox = getattr(self, 'rho_ox', 1200)
        rho_fuel = getattr(self, 'rho_fuel', 800)
        # DENETIM DUZELTMESI: Kalis suresi τ = ρ_gaz·V_c/ṁ ile hesaplanir.
        # Yanma odasinda akiskan GAZ fazindadir; sivi propellant yogunlugu
        # (~1000 kg/m³) kullanmak τ'yu ~130x fazla veriyordu (ve Damkohler
        # sayisini ayni oranda sisiriyordu). ρ_gaz = Pc/(R_gas·Tc) ideal gaz.
        rho_gas_chamber = (self.P_c * PA_PER_BAR) / ((R_UNIVERSAL / self.mw) * self.T_c)  # kg/m³
        residence_time = chamber_volume * rho_gas_chamber / mdot_total  # s
        mixing_time = 0.002  # s typical for impinging injectors
        
        # Mixing efficiency based on momentum ratio
        mdot_ox = getattr(self, 'mdot_ox', mdot_total * self.MR / (1 + self.MR))
        mdot_fuel = getattr(self, 'mdot_fuel', mdot_total / (1 + self.MR))
        momentum_ratio = (mdot_ox / mdot_fuel) * (rho_fuel / rho_ox)**0.5
        optimal_momentum_ratio = 2.0  # Typical optimum
        
        mixing_efficiency = 1 - 0.1 * abs(momentum_ratio - optimal_momentum_ratio) / optimal_momentum_ratio
        mixing_efficiency = max(0.85, min(0.98, mixing_efficiency))  # 85-98% range
        
        # Combustion efficiency
        damkohler_number = residence_time / mixing_time  # Dimensionless
        combustion_efficiency = 1 - np.exp(-damkohler_number * 0.1)
        combustion_efficiency = max(0.90, min(0.99, combustion_efficiency))  # 90-99% range

        # DENETIM DUZELTMESI: Boyuna (L1) akustik mod ses hizi YANMA GAZI ile
        # hesaplanir: a = sqrt(γ·R_gas·Tc) (~1200-1300 m/s, Tc~3600K). Havanin
        # oda-sicakligi ses hizi 343 m/s frekansi ~3.7x hafife aliyordu
        # (combustion instability metrigi -> yaniltici). f = a/(2L).
        a_chamber = np.sqrt(self.gamma * (R_UNIVERSAL / self.mw) * self.T_c)  # m/s

        return {
            'chamber_geometry': {
                'diameter': chamber_diameter * 1000,  # mm
                'length': chamber_length * 1000,  # mm
                'volume': chamber_volume * 1e6,  # cm³
                'l_star': chamber_volume / (np.pi * (d_t/2)**2),  # m
                'contraction_ratio': (chamber_diameter / d_t)**2
            },
            'combustion_analysis': {
                'residence_time': residence_time * 1000,  # ms
                'mixing_time': mixing_time * 1000,  # ms  
                'damkohler_number': damkohler_number,
                'mixing_efficiency': mixing_efficiency * 100,  # %
                'combustion_efficiency': combustion_efficiency * 100,  # %
                'momentum_ratio': momentum_ratio,
                'optimal_momentum_ratio': optimal_momentum_ratio
            },
            'stability_analysis': {
                'acoustic_frequency': a_chamber / (2 * chamber_length),  # Hz
                'combustion_response_time': mixing_time * 1000,  # ms
                'stability_rating': 'Stable',
                'damping_mechanisms': ['Acoustic liners', 'Baffles', 'Variable geometry']
            }
        }
    
    def _scan_engine(self, **kwargs):
        """Aynı çözücüyle yeni bir tasarım noktası koşar (harita taraması).

        Motorun KENDİ kurucusu kullanılır — harita ile tasarım noktası aynı
        zinciri paylaşır, ayrı bir 'basitleştirilmiş model' yoktur. Web
        verisi paylaştırılır (ağ çağrısı yok).
        """
        params = dict(
            thrust=self.F, chamber_pressure=self.P_c, mixture_ratio=self.MR,
            fuel_type=self.fuel_type, oxidizer_type=self.oxidizer_type,
            cooling_type=self.cooling_type, injector_type=self.injector_type,
            feed_system_type=self.feed_system_type,
            propellant_data=dict(self._web_propellant_data or {}),
            overrides=dict(self.overrides),
        )
        params.update(kwargs)
        return LiquidRocketEngine(**params)

    def _generate_performance_optimization_maps(self):
        """Performans optimizasyon haritaları — GERÇEK çözücü taraması.

        2026-07-19 denetimi (kritik bulgu): haritalar gömülü tepe değerlere
        (RP-1/LOX 353/1823, diğer HER yakıt çifti 350/1800) uydurma bir
        parabol uygulayarak üretiliyordu; metan/LOX'ta grafik ~350 s tepe
        gösterirken sayfanın üstünde 376.8 s yazıyordu. Artık:

          * O/F haritası: her noktada motorun KENDİ zinciri koşulur
            (LiquidRocketEngine örneği -> CEA demirli Isp/c*), böylece
            tasarım noktası eğrinin ÜSTÜNDE yer alır ve yakıt çiftine göre
            gerçekten değişir.
          * Pc haritası: her noktada motor yeniden koşulur; Isp/itki
            CF zincirinden gelir (sabit boğaz alanı DEĞİL, tasarım noktası
            yeniden boyutlandırılır — motor 'hedef itki' modundadır).
          * İrtifa haritası: doğrudan ``calculate_altitude_performance``
            (US Standard Atmosphere 1976 + CF oranı) sonucudur.
        """
        optimal_mr = float(getattr(self, 'optimal_mr', 2.5))

        # --- O/F taraması (gerçek çözücü) ---------------------------------
        mr_lo = getattr(self, 'of_scan_min', None) or max(
            0.2, optimal_mr * (1.0 - PERF_MAP_MR_SPAN))
        mr_hi = getattr(self, 'of_scan_max', None) or (
            optimal_mr * (1.0 + PERF_MAP_MR_SPAN))
        mr_range = np.linspace(mr_lo, mr_hi, PERF_MAP_MR_POINTS)
        isp_vs_mr, cstar_vs_mr = [], []
        for mr in mr_range:
            if abs(mr - self.MR) < 1e-9:
                isp_vs_mr.append(float(self.isp_vac))
                cstar_vs_mr.append(float(self.c_star))
                continue
            try:
                probe = self._scan_engine(mixture_ratio=float(mr))
                isp_vs_mr.append(float(probe.isp_vac))
                cstar_vs_mr.append(float(probe.c_star))
            except Exception:
                isp_vs_mr.append(None)
                cstar_vs_mr.append(None)

        # --- Oda basıncı taraması (gerçek çözücü) --------------------------
        pc_lo = max(PERF_MAP_PC_MIN_BAR, self.P_c * 0.4)
        pc_hi = min(PERF_MAP_PC_MAX_BAR, self.P_c * 2.0)
        if pc_hi <= pc_lo:
            pc_lo, pc_hi = PERF_MAP_PC_MIN_BAR, PERF_MAP_PC_MAX_BAR
        pc_range = np.linspace(pc_lo, pc_hi, PERF_MAP_PC_POINTS)
        isp_vs_pc, thrust_vs_pc, throat_vs_pc = [], [], []
        for pc in pc_range:
            try:
                probe = self._scan_engine(chamber_pressure=float(pc))
                geom = probe.calculate_nozzle_geometry()
                isp_vs_pc.append(float(probe.isp_vac))
                # Sabit boğaz alanı (bu motorun boğazı) ile üretilebilecek itki:
                # F = CF · Pc · A_t (Sutton & Biblarz 9th ed., Eq. 3-31).
                cf_pc, _ = probe._cf_at(geom['expansion_ratio'], self.P_a)
                thrust_vs_pc.append(float(cf_pc * pc * PA_PER_BAR * self.A_t))
                throat_vs_pc.append(float(geom['throat_diameter'] * 1000.0))
            except Exception:
                isp_vs_pc.append(None)
                thrust_vs_pc.append(None)
                throat_vs_pc.append(None)

        # --- İrtifa taraması (gerçek fonksiyon) ----------------------------
        altitude_range = np.linspace(0.0, PERF_MAP_ALT_MAX_M,
                                     PERF_MAP_ALT_POINTS)
        alt_data = self.calculate_altitude_performance(altitude_range.tolist())
        isp_vs_alt = [float(p['specific_impulse']) for p in alt_data]
        thrust_vs_alt = [float(p['thrust']) for p in alt_data]

        mr_dev = abs(self.MR - optimal_mr) / optimal_mr
        return {
            'method': ('scan of the same solver used for the design point '
                       '(CEA-anchored Isp/c* chain, isentropic CF)'),
            'mixture_ratio_optimization': {
                'mr_range': mr_range.tolist(),
                'isp_vs_mr': isp_vs_mr,
                'cstar_vs_mr': cstar_vs_mr,
                'optimal_mr': optimal_mr,
                'current_mr': self.MR,
                'current_isp_vac': float(self.isp_vac),
                'current_cstar': float(self.c_star),
                'mr_efficiency': float(
                    getattr(self, 'mr_efficiency',
                            max(0.7, 1 - 0.15 * mr_dev ** 2)) * 100.0),
            },
            'chamber_pressure_optimization': {
                'pc_range': pc_range.tolist(),
                'isp_vs_pc': isp_vs_pc,
                'thrust_vs_pc': thrust_vs_pc,
                'throat_diameter_vs_pc_mm': throat_vs_pc,
                'current_pc': self.P_c,
                'thrust_basis': ('thrust achievable with THIS engine throat '
                                 'area at the scanned chamber pressure'),
            },
            'altitude_performance': {
                'altitude_range': altitude_range.tolist(),
                'isp_vs_altitude': isp_vs_alt,
                'thrust_vs_altitude': thrust_vs_alt,
                'optimal_altitude': float(
                    altitude_range[int(np.argmax(isp_vs_alt))])
                if isp_vs_alt else 0.0,
            }
        }
    
    def _calculate_efficiency_breakdown(self):
        """Calculate detailed efficiency breakdown"""
        
        # Theoretical maximum (perfect expansion, no losses)
        # H-7 duzeltmesi: parantez/operator onceligi hatasi.
        # Eski:  (1/20)**(self.gamma-1)/self.gamma   ->   ((1/20)**(gamma-1)) / gamma
        # Dogru: (1/20)**((self.gamma-1)/self.gamma) ->   us olarak (gamma-1)/gamma
        # P_e/P_c = 1/20 izentropik genisleme oraninda, gamma=1.22 icin
        # eski formul ~%15 fazla theoretical Isp veriyordu.
        pressure_ratio = 1.0 / 20.0  # P_e / P_c (perfect expansion varsayimi)
        # DENETIM DUZELTMESI (bonus): Vandenkerckhove faktoru eksikti.
        # Isp_ideal = CF * c* / g0; CF = Gamma_vdk * sqrt(2g/(g-1)*(1-PR^((g-1)/g)))
        # Gamma_vdk = sqrt(g) * (2/(g+1))^((g+1)/(2(g-1)))
        # (Sutton & Biblarz 9th ed., Eq. 3-30 ve c* tanimi Eq. 3-32)
        gamma_vdk = np.sqrt(self.gamma) * (
            2.0 / (self.gamma + 1.0)
        ) ** ((self.gamma + 1.0) / (2.0 * (self.gamma - 1.0)))
        theoretical_isp = self.c_star / self.g0 * gamma_vdk * np.sqrt(
            2 * self.gamma / (self.gamma - 1)
            * (1 - pressure_ratio ** ((self.gamma - 1) / self.gamma))
        )
        
        # --- Kayıp mekanizmaları: her kalem GERÇEK bir büyüklükten türetilir --
        # 2026-07-19 denetimi: bu sözlük tamamen sabitti (toplam %10, her motor
        # için birebir aynı); nozul tipi, genişleme oranı, enjektör, Pc ve yakıt
        # grafiği hiç değiştirmiyordu.
        geom = NOZZLE_TYPE_GEOMETRY.get(getattr(self, 'nozzle_type',
                                                NOZZLE_TYPE_DEFAULT),
                                        NOZZLE_TYPE_GEOMETRY[NOZZLE_TYPE_DEFAULT])
        sources = {}

        # 1) Sapma (divergence) kaybı: lambda = (1+cos θ)/2 (Sutton & Biblarz
        #    9th ed., Eq. 3-34) — nozul tipinden gelen çıkış açısıyla.
        theta = geom['half_angle'] if geom['exit_angle'] is None else geom['exit_angle']
        eta_divergence = 0.5 * (1.0 + np.cos(np.radians(theta)))
        sources['divergence_loss'] = (
            f"lambda=(1+cos {theta:.1f} deg)/2 from the selected nozzle type")

        # 2) Sınır tabaka / sürtünme: boğaz Reynolds sayısından
        #    (calculate_altitude_performance ile aynı bağıntı).
        mdot = getattr(self, 'mdot_total', None)
        d_t = getattr(self, 'd_t', None)
        if mdot and d_t:
            re_throat = (mdot * 4.0) / (np.pi * d_t * self.mu_chamber)
            eta_boundary = 1.0 - 0.002 * (1e6 / max(re_throat, 1e4)) ** 0.2
            sources['boundary_layer_loss'] = (
                f"throat Reynolds number {re_throat:.3g}")
        else:
            re_throat = None
            eta_boundary = 1.0 - 0.002
            sources['boundary_layer_loss'] = 'assumed (geometry not solved yet)'

        # 3) Isı transferi kaybı: cidara giden ısı / kimyasal güç
        #    (Bartz tabanlı cooling_system sonucundan).
        try:
            cooling = self.calculate_cooling_requirements()
            q_wall_w = cooling['total_heat_load'] * 1000.0  # kW -> W
            chemical_power = max(mdot or 0.0, 1e-9) * self.cp_chamber * self.T_c
            eta_heat = 1.0 - min(q_wall_w / chemical_power, 0.25)
            sources['heat_transfer_loss'] = (
                f"Bartz wall heat load {q_wall_w / 1000:.1f} kW over the "
                f"chamber enthalpy flow")
        except Exception:
            eta_heat = 0.99
            sources['heat_transfer_loss'] = 'assumed 1.0% (heat model failed)'

        # 4/5) Yanma ve karışım verimi: ayrıntılı hazne analizinden
        #      (Damköhler sayısı ve momentum oranı — gerçek hesap).
        try:
            comb = self._analyze_combustion_chamber_detailed()['combustion_analysis']
            eta_combustion = comb['combustion_efficiency'] / 100.0
            eta_mixing = comb['mixing_efficiency'] / 100.0
            sources['combustion_incomplete'] = (
                f"Damkohler number {comb['damkohler_number']:.2f} "
                f"(residence time / mixing time)")
            sources['mixing_loss'] = (
                f"injector momentum ratio {comb['momentum_ratio']:.2f} vs "
                f"optimum {comb['optimal_momentum_ratio']:.2f}")
        except Exception:
            eta_combustion, eta_mixing = 0.98, 0.985
            sources['combustion_incomplete'] = 'assumed (chamber model failed)'
            sources['mixing_loss'] = 'assumed (chamber model failed)'
        # Kullanıcı c* verimi girdiyse yanma kalemi ONDAN gelir (tek kaynak).
        if 'combustion_efficiency' in self.overrides and getattr(
                self, 'eta_c_star', 1.0) != 1.0:
            eta_combustion = float(self.eta_c_star)
            sources['combustion_incomplete'] = 'user input (combustion efficiency)'

        # 6) Kimyasal kinetik: donmuş/dengeli genleşme moduna göre
        #    (calculate_altitude_performance ile aynı değerler).
        eta_kinetic = 0.96 if getattr(self, 'frozen_performance', False) else 0.99
        sources['kinetic_loss'] = (
            'frozen expansion' if getattr(self, 'frozen_performance', False)
            else 'equilibrium expansion')

        # 7) Sonlu genişleme (lüle uzunluğu) kaybı: bu ε ile elde edilen vakum
        #    CF'nin pratik üst sınıra (ε_max) oranı.
        eps = getattr(self, 'expansion_ratio', None)
        eta_length = 1.0
        if eps:
            try:
                cf_here, _ = self._cf_at(eps, 0.0)
                cf_max, _ = self._cf_at(EXPANSION_RATIO_PRACTICAL_MAX, 0.0)
                eta_length = float(min(cf_here / cf_max, 1.0))
                sources['nozzle_length_loss'] = (
                    f"vacuum CF at epsilon={eps:.1f} against the practical "
                    f"limit epsilon={EXPANSION_RATIO_PRACTICAL_MAX:g}")
            except Exception:
                sources['nozzle_length_loss'] = 'assumed (CF solve failed)'
        else:
            sources['nozzle_length_loss'] = 'assumed (geometry not solved yet)'

        # TESLİM kayıpları: Isp'yi doğrudan düşüren mekanizmalar. Bunların
        # ÇARPIMI toplam verimdir (eski kod yüzdeleri topluyordu).
        delivery = {
            'divergence_loss': eta_divergence,
            'boundary_layer_loss': eta_boundary,
            'heat_transfer_loss': eta_heat,
            'combustion_incomplete': eta_combustion,
            'mixing_loss': eta_mixing,
            'kinetic_loss': eta_kinetic,
        }
        # Sonlu genişleme kalemi bir TASARIM KARŞILAŞTIRMASIDIR (bu lüle vs
        # vakum-optimize lüle); teslim edilen Isp'de zaten yoktur, bu yüzden
        # toplam verim çarpımına DAHİL EDİLMEZ ve etiketi bunu söyler.
        efficiencies = dict(delivery)
        efficiencies['nozzle_length_loss'] = eta_length
        sources['nozzle_length_loss'] += (
            ' - design comparison only, not part of the overall efficiency '
            'product')
        losses = {k: (1.0 - v) * 100.0 for k, v in efficiencies.items()}
        overall = float(np.prod(list(delivery.values())) * 100.0)

        return {
            'theoretical_isp': theoretical_isp,
            'actual_isp': self.isp_vac,
            # Verimler ÇARPIMSAL birleşir (eski kod yüzdeleri topluyordu).
            'overall_efficiency': overall,
            'overall_efficiency_basis': (
                'product of the delivery losses (divergence, boundary layer, '
                'wall heat transfer, combustion, mixing, kinetics)'),
            'delivered_vs_theoretical_pct': float(
                self.isp_vac / theoretical_isp * 100.0)
            if theoretical_isp else None,
            'loss_breakdown': losses,
            'efficiency_breakdown': {k: v * 100.0
                                     for k, v in efficiencies.items()},
            'loss_sources': sources,
            'method': ('each item derived from the engine solution '
                       '(nozzle contour, throat Reynolds number, Bartz heat '
                       'load, Damkohler number, momentum ratio, expansion '
                       'ratio); no fixed loss table'),
            'efficiency_improvements': {
                'longer_nozzle':
                    f"increase expansion ratio (current {eps:.1f})"
                    if eps else 'increase expansion ratio',
                'contoured_nozzle':
                    f"divergence efficiency now {eta_divergence * 100:.2f}% "
                    f"({getattr(self, 'nozzle_type', NOZZLE_TYPE_DEFAULT)})",
                'better_injector':
                    f"mixing efficiency now {eta_mixing * 100:.2f}%",
                'higher_chamber_pressure':
                    f"wall heat loss now {(1 - eta_heat) * 100:.2f}% of the "
                    f"chamber enthalpy flow",
            }
        }
    
    @staticmethod
    def _derated_yield(material, temperature_k):
        """Sıcaklığa göre indirgenmiş akma dayanımı [Pa].

        materials_db kayıtlarındaki ``derating_curve`` (anahtar: °C, değer:
        akma oranı) doğrusal interpolasyonla değerlendirilir. Eğri yoksa
        oda sıcaklığı değeri kullanılır.
        """
        sigma_y = float(material['yield_strength'])
        curve = material.get('derating_curve') or {}
        if not curve:
            return sigma_y, 1.0
        items = sorted((float(k), float(v)) for k, v in curve.items())
        temps = [t for t, _ in items]
        vals = [v for _, v in items]
        t_c = float(temperature_k) - 273.15
        factor = float(np.interp(t_c, temps, vals))
        return sigma_y * factor, factor

    def _structural_design(self):
        """Hazne cidarı boyutlandırması (tek doğruluk kaynağı).

        2026-07-19 denetimi: emniyet katsayısı 4.0'a, akma dayanımı 250 MPa'ya
        sabitlenmişti ve 'Inconel 718' etiketiyle çelişiyordu; gerilme marjı
        tanım gereği daima 0 çıkıyordu. Artık:
          - malzeme merkezi ``materials_db``den gelir (etiket = kullanılan σ_y),
          - emniyet katsayısı KULLANICI girdisinden,
          - akma dayanımı sıcak cidar sıcaklığında derate edilir,
          - gerekli kalınlık bir üst STANDART plaka kalınlığına yuvarlanır
            (ya da kullanıcı kalınlığı kullanılır), böylece marj gerçek olur.
        """
        material, mat_key = self._material_record()
        sf = float(getattr(self, 'safety_factor', SAFETY_FACTOR_DEFAULT))
        t_hot, _ = self._wall_temperatures()
        sigma_y, derate = self._derated_yield(material, t_hot)
        allowable = sigma_y / sf

        d_c = self._chamber_diameter()
        p_int = self.P_c * PA_PER_BAR  # Pa
        t_required = max((p_int * d_c / 2.0) / allowable, WALL_THICKNESS_MIN_M)

        thickness_source = 'next standard plate thickness above the requirement'
        t_used = None
        if getattr(self, 'wall_thickness_input_m', None) is not None:
            t_used = self.wall_thickness_input_m
            thickness_source = 'user input (chamber wall thickness)'
            if t_used < t_required:
                self._warn(
                    f"Chamber wall thickness {t_used * 1000:.2f} mm is below "
                    f"the {t_required * 1000:.2f} mm required for "
                    f"{material.get('name', mat_key)} at safety factor "
                    f"{sf:.2f}; the reported stress margin is negative.")
        else:
            for std in STANDARD_WALL_THICKNESS_MM:
                if std / 1000.0 >= t_required:
                    t_used = std / 1000.0
                    break
            if t_used is None:
                t_used = t_required
                thickness_source = 'computed requirement (above standard sizes)'

        hoop = (p_int * d_c / 2.0) / t_used
        margin = (allowable - hoop) / allowable * 100.0
        return {
            'material': material,
            'material_key': mat_key,
            'safety_factor': sf,
            'yield_strength_pa': float(material['yield_strength']),
            'derated_yield_pa': sigma_y,
            'derating_factor': derate,
            'allowable_pa': allowable,
            'chamber_diameter_m': d_c,
            'required_thickness_m': t_required,
            'thickness_m': t_used,
            'thickness_source': thickness_source,
            'hoop_stress_pa': hoop,
            'stress_margin_pct': margin,
            'wall_temperature_k': t_hot,
        }

    def _chamber_wall_thickness_m(self):
        """Hazne cidar kalınlığı [m] — yapısal tasarımla tek kaynak."""
        return self._structural_design()['thickness_m']

    def _calculate_structural_loads(self):
        """Structural analysis for chamber and nozzle design"""
        s = self._structural_design()
        material = s['material']
        chamber_internal_pressure = self.P_c * PA_PER_BAR  # Pa

        return {
            'chamber_structure': {
                'internal_pressure': chamber_internal_pressure / 1e5,  # bar
                'chamber_diameter': s['chamber_diameter_m'] * 1000,  # mm
                'wall_thickness': s['thickness_m'] * 1000,  # mm
                'required_wall_thickness': s['required_thickness_m'] * 1000,  # mm
                'wall_thickness_source': s['thickness_source'],
                'hoop_stress': s['hoop_stress_pa'] / 1e6,  # MPa
                'allowable_stress': s['allowable_pa'] / 1e6,  # MPa
                'stress_margin': s['stress_margin_pct'],  # %
                'safety_factor': s['safety_factor'],
                'material': material.get('name', s['material_key']),
                'material_key': s['material_key'],
                'yield_strength': s['yield_strength_pa'] / 1e6,  # MPa (20 C)
                'yield_strength_at_wall_temp': s['derated_yield_pa'] / 1e6,  # MPa
                'derating_factor': s['derating_factor'],
                'wall_temperature': s['wall_temperature_k'],  # K
                'material_source': material.get('source', 'materials_db'),
            },
            'design_requirements': {
                'proof_pressure':
                    chamber_internal_pressure * PROOF_PRESSURE_FACTOR / 1e5,  # bar
                'burst_pressure':
                    chamber_internal_pressure * BURST_PRESSURE_FACTOR / 1e5,  # bar
                'operating_temperature': self.T_c,  # K
                'thermal_cycles': getattr(self, 'thermal_cycles',
                                          THERMAL_CYCLES_DEFAULT)
            }
        }
    
    def _calculate_thermal_protection_system(self, cooling=None):
        """Isıl koruma / soğutma tasarımı — TEK doğruluk kaynağı.

        2026-07-19 denetimi (kritik bulgu): bu blok tamamen sabit sözlük
        döndürüyordu (180 kanal, 2x3 mm, 15 m/s, 800 K, 50 MW/m², 8 bar,
        150 K) ve aynı sayfada gösterilen GERÇEK Bartz hesabıyla (80 kanal,
        ~81 MW/m², 0.035 bar, 390 K) çelişiyordu. Artık her kalem
        ``calculate_cooling_requirements()`` (Bartz + kanal hidroliği)
        sonucundan türetilir; ek olarak soğutucu RP-1 ise
        ``hrma.analysis.regen_cooling.RegenCooling`` 1B istasyon marşı
        çalıştırılıp tepe cidar sıcaklığı ve akısı oradan raporlanır.
        """
        if cooling is None:
            cooling = self.calculate_cooling_requirements()

        t_hot, t_cold = self._wall_temperatures()
        result = {
            'cooling_type': self.cooling_type.replace('_', ' ').title(),
            'coolant_type': self.fuel_type.upper(),
            'cooling_channels': cooling.get('cooling_channels', 0),
            'channel_dimensions':
                f"{cooling.get('channel_width_mm', 0):.1f} mm x "
                f"{cooling.get('channel_height_mm', 0):.1f} mm",
            'channel_count_source': cooling.get('channel_count_source',
                                                'computed'),
            'channel_section_source': 'design default (not auto-sized)',
            'coolant_velocity': cooling.get('coolant_velocity', 0.0),  # m/s
            'coolant_reynolds': cooling.get('coolant_reynolds', 0.0),
            'wall_temperature': t_hot,  # K (sıcak cidar tasarım hedefi)
            'wall_temperature_source': (
                'user input (max wall temperature)'
                if getattr(self, 'max_wall_temp_input', None) is not None
                else 'cooling-type design default'),
            'coolant_wall_temperature': t_cold,  # K
            # Bartz tepe akısı boğazdadır; cooling_system kW/m² döndürür.
            'heat_flux': cooling.get('peak_heat_flux', 0.0) / 1000.0,  # MW/m²
            'chamber_heat_flux': cooling.get('chamber_heat_flux', 0.0) / 1000.0,
            'pressure_drop': cooling.get('cooling_pressure_drop', 0.0),  # bar
            'temperature_rise': cooling.get('coolant_temperature_rise', 0.0),  # K
            'coolant_inlet_temperature': cooling.get(
                'coolant_inlet_temperature', COOLANT_INLET_TEMP_DEFAULT_K),
            'coolant_exit_temperature': cooling.get(
                'coolant_exit_temperature'),
            'total_heat_load_kw': cooling.get('total_heat_load', 0.0),
            'model': ('Bartz gas-side correlation with rectangular-channel '
                      'hydraulics (Sutton & Biblarz 9th ed. Eq. 8-23; '
                      'Darcy-Weisbach with Haaland friction factor)'),
        }
        if self.cooling_type in ('ablative', 'radiative'):
            material, _ = self._material_record()
            result['material'] = material.get('name', self.chamber_material)
            result['material_service_limit_K'] = material.get(
                'max_service_temperature', material.get('allowable_temperature'))

        # --- 1B rejeneratif marş (yalnız desteklenen soğutucu akışkanlarda) --
        # RegenCooling şu an 'water' ve 'rp1' özellik tablolarını taşır; başka
        # yakıtlar için çalıştırılmaz ve bu DÜRÜSTÇE belirtilir.
        coolant_map = {'rp1': 'rp1'}
        coolant_key = coolant_map.get(self.fuel_type)
        if (self.cooling_type == 'regenerative' and coolant_key
                and cooling.get('cooling_channels', 0) > 0):
            try:
                from hrma.analysis.regen_cooling import RegenCooling
                material, mat_key = self._material_record()
                rc = RegenCooling(
                    chamber_pressure=self.P_c * PA_PER_BAR,
                    chamber_temperature=self.T_c,
                    gamma=float(self.gamma),
                    molecular_weight=float(self.mw),
                    throat_diameter=float(self.d_t),
                    exit_diameter=float(self.d_e),
                    coolant=coolant_key,
                    coolant_mdot=max(cooling.get('coolant_flow_rate', 0.0),
                                     1e-6),
                    coolant_inlet_temp=result['coolant_inlet_temperature'],
                    coolant_inlet_pressure=(self.P_c + 10.0) * PA_PER_BAR,
                    n_channels=int(cooling['cooling_channels']),
                    channel_width=cooling.get('channel_width_mm', 3.0) / 1000.0,
                    channel_height=cooling.get('channel_height_mm', 2.0) / 1000.0,
                    wall_thickness=self._chamber_wall_thickness_m(),
                    wall_material=mat_key,
                    motor_data={'chamber_diameter': self._chamber_diameter(),
                                'mdot_total': self.mdot_total,
                                'nozzle_type': getattr(self, 'nozzle_type',
                                                       NOZZLE_TYPE_DEFAULT)},
                )
                march = rc.solve()
                summary = march['summary']
                result['station_march'] = {
                    'peak_wall_temperature_K': summary['max_wall_hot_K'],
                    'peak_heat_flux_MW_m2': summary['peak_heat_flux_MW_m2'],
                    'coolant_exit_temperature_K': summary['coolant_exit_temp_K'],
                    'coolant_pressure_drop_bar':
                        summary['total_pressure_drop_bar'],
                    'max_coolant_velocity_m_s':
                        summary['max_coolant_velocity_m_s'],
                    'material_allowable_K': summary['material_allowable_temp_K'],
                    'warnings': summary['warnings'],
                    'model_note': march['model_note'],
                }
            except Exception as exc:
                result['station_march_status'] = (
                    f'1D station march not run: {exc}')
        else:
            result['station_march_status'] = (
                '1D station march available for RP-1 regenerative cooling '
                'only; the values above come from the Bartz chamber/nozzle '
                'integration.')
        return result
    
    def _analyze_manufacturing_requirements(self):
        """Manufacturing and production analysis"""
        
        return {
            'manufacturing_processes': {
                'chamber': 'Forged and machined',
                'nozzle': 'Brazed cooling channels',
                'injector': 'CNC machined orifices',
                'turbopump': 'Investment cast impellers'
            },
            'critical_tolerances': {
                'throat_diameter': '±0.1mm',
                'injector_orifices': '±0.05mm',
                'cooling_channels': '±0.2mm',
                'chamber_alignment': '±0.5mm'
            },
            'estimated_costs': {
                'development': '$2M - $5M',
                'first_unit': '$500k - $1M',
                'production_unit': '$100k - $300k',
                'annual_production': '50 - 200 units'
            },
            'production_timeline': {
                'design_phase': '18 months',
                'prototype_build': '12 months',
                'qualification_testing': '6 months',
                'production_ramp': '6 months'
            }
        }
    
    def _detailed_component_sizing(self):
        """Bileşen boyutlandırma ve kütle dökümü — GEOMETRİ + MALZEME.

        2026-07-19 denetimi: kütleler ampirik doğrulardan (25 + F/1000·0.8 …)
        geliyordu ve motorun kendi geometrisi/malzemesiyle ilgisi yoktu;
        calculate_performance ayrıca sabit 50 kg'lık ikinci bir kuru kütle
        raporluyordu. Artık hazne, lüle ve enjektör kütlesi GERÇEK kabuk
        geometrisinden (kalınlık x yüzey x yoğunluk) hesaplanır; turbopompa,
        hat ve kontrol kütleleri ETİKETLİ ampirik korelasyonlardır.
        """
        structural = self._structural_design()
        material = structural['material']
        rho_mat = float(material.get('density', 7850.0))
        t_wall = structural['thickness_m']
        d_c = structural['chamber_diameter_m']

        cooling = self.calculate_cooling_requirements()
        l_chamber = cooling['chamber_length'] / 1000.0    # m
        l_nozzle = cooling['nozzle_length'] / 1000.0      # m

        # Hazne: silindirik kabuk (orta çap üzerinden) + flanş/takviye payı
        chamber_mass = (np.pi * (d_c + t_wall) * t_wall * l_chamber
                        * rho_mat * CHAMBER_MASS_JOINT_FACTOR)

        # Yakınsak koni (D_c -> d_t) ve ıraksak koni (d_t -> d_e) kesik koni
        # yanal yüzeyleri: A = pi·(r1+r2)·slant
        t_nozzle = t_wall * NOZZLE_WALL_THICKNESS_RATIO
        r_c, r_t, r_e = d_c / 2.0, self.d_t / 2.0, self.d_e / 2.0
        l_conv = max((r_c - r_t) / np.tan(np.radians(30.0)), 1e-4)
        slant_conv = np.hypot(r_c - r_t, l_conv)
        slant_div = np.hypot(r_e - r_t, l_nozzle)
        nozzle_mass = ((np.pi * (r_c + r_t) * slant_conv
                        + np.pi * (r_t + r_e) * slant_div)
                       * t_nozzle * rho_mat)

        # Enjektör plakası: dolu disk (delik payı ihmal, muhafazakâr)
        t_injector = t_wall * INJECTOR_PLATE_THICKNESS_RATIO
        injector_mass = np.pi * (d_c / 2.0) ** 2 * t_injector * rho_mat

        # Turbopompa: pompa gücüyle ölçeklenen ETİKETLİ korelasyon
        if self.feed_system_type == 'turbopump':
            try:
                feed = self._analyze_detailed_feed_system()['turbopump_analysis']
                pump_power_kw = (feed['oxidizer_pump']['design_power']
                                 + feed['fuel_pump']['design_power'])
            except Exception:
                pump_power_kw = 0.0
            turbopump_mass = (TURBOPUMP_MASS_BASE_KG
                              + TURBOPUMP_MASS_PER_KW * pump_power_kw)
        else:
            pump_power_kw = 0.0
            turbopump_mass = 0.0

        mdot_total = getattr(self, 'mdot_total', 0.0)
        feed_lines_mass = FEED_LINE_MASS_PER_KG_S * mdot_total
        controls_mass = CONTROLS_MASS_BASE_KG

        total_dry_mass = (chamber_mass + nozzle_mass + injector_mass
                          + turbopump_mass + feed_lines_mass + controls_mass)

        return {
            'component_masses': {
                'combustion_chamber': chamber_mass,  # kg
                'nozzle_assembly': nozzle_mass,      # kg
                'injector_assembly': injector_mass,  # kg
                'turbopump_assembly': turbopump_mass, # kg
                'feed_system': feed_lines_mass,      # kg
                'controls_avionics': controls_mass,  # kg
                'total_dry_mass': total_dry_mass     # kg
            },
            'mass_method': {
                'chamber_nozzle_injector': (
                    f"shell geometry x {t_wall * 1000:.2f} mm wall x "
                    f"{material.get('name', structural['material_key'])} "
                    f"density {rho_mat:.0f} kg/m3"),
                'turbopump': ('empirical mass-power correlation '
                              f'({TURBOPUMP_MASS_BASE_KG:g} kg + '
                              f'{TURBOPUMP_MASS_PER_KW:g} kg/kW x '
                              f'{pump_power_kw:.0f} kW) - estimate'),
                'feed_and_controls': 'empirical scaling with mass flow - estimate',
            },
            'component_dimensions': {
                'overall_length': l_chamber + l_conv + l_nozzle,  # m
                'maximum_diameter': d_c * 1000,  # mm
                'nozzle_length': l_nozzle * 1000,  # mm
                'chamber_volume': (self._l_star() * np.pi * (self.d_t**2) / 4) * 1e6  # cm³
            },
            'mass_ratios': {
                'thrust_to_weight': self.F / (total_dry_mass * G_0),
                'power_to_weight': (pump_power_kw / total_dry_mass
                                    if total_dry_mass > 0 else 0.0),  # kW/kg
                'chamber_loading': self.F / chamber_mass  # N/kg
            }
        }