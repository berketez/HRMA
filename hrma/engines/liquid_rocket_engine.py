import copy
import time
from functools import lru_cache
import numpy as np
from scipy.optimize import fsolve, newton, minimize_scalar
from scipy.interpolate import interp1d, interp2d
import json
import warnings
import requests
from typing import Dict, List, Optional, Tuple

from hrma.constants import (G_0, R_UNIVERSAL, PA_PER_BAR, LAMBDA_BELL,
                            NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT,
                            lambda_conical,
                            ISA_TABLE_TOP_M, isa_temperature, isa_pressure)
# B5 (v2.6.27): NPSH zinciri TEK KAYNAK — mevcut NPSH tanımı, devir düşürme
# çarpanı ve birim çevrimleri turbopompa boyutlandırma modülünden İTHAL
# edilir; motor kendi kopyalarını TANIMLAMAZ (parametre tutarlılığı kuralı).
# turbopump_sizing yalnız hrma.constants'a bağımlıdır, döngüsel import yoktur.
from hrma.analysis.turbopump_sizing import (
    NPSH_MARGIN_FACTOR_SOURCE,
    NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE, NPSH_SINGLE_MARGIN_CONTRACT,
    NPSH_STATIC_HEAD_DEFAULT_M, NPSH_STATIC_HEAD_SOURCE,
    NPSH_VELOCITY_HEAD_FACTORS, NPSH_VELOCITY_HEAD_SOURCE,
    SPEED_DERATE_DEFAULT,
    # ÖH D25 · OH-D24-14: türbin verimi GEÇERLİLİK BANDI tek kaynaktır.
    # Motor aynı kuralı kendi literalleriyle (0,0 < eta <= 1,0) ikinci kez
    # yazıyordu; band boyutlandırma modülünde tanımlı ve gerekçesi
    # (Huzel & Huang, NASA SP-125 Böl. 6; Sutton 9. baskı Böl. 10) orada —
    # motor onu TÜKETİR, yeniden yazmaz.
    TURBINE_EFFICIENCY_VALID,
    # ÖH D27 · OH-D26-09: pompanın DEVİR SEÇİMİNİ yargılayan iki literatür
    # bandı da tek kaynaktır (bu modülde yeniden yazılmaz):
    #   NSS_NO_INDUCER_MAX_US  — indüsersiz emme kabiliyeti tavanı,
    #   NS_CENTRIFUGAL_MIN/MAX_US — radyal çarkın ÖZGÜL DEVİR bandı.
    # Kart bugüne kadar ikisini de yalnız DÜZYAZIDA anıyordu ('~11000'
    # elle yazılıydı) ve yapısal bir alan yayımlamıyordu.
    NS_CENTRIFUGAL_MAX_US, NS_CENTRIFUGAL_MIN_US, NS_SOURCE,
    NSS_NO_INDUCER_MAX_US, NSS_SOURCE,
    # ÖH D28 · OH-D27-02 (OH-D26-09 kalan yarısı): KADEME SAYISI bir
    # TASARIM KARARIDIR ve kuralı da (Ns_kademe = Ns_toplam·n^0,75 >= 500
    # veren en küçük n, üst sınır PUMP_STAGES_MAX) tek kaynaktadır. Motor
    # kartı bugüne kadar kararı hiç yayımlamıyordu; aynı yanıtta
    # ``turbopump_sizing`` bloğu 2/3/4/6 kademe derken kart çarkı TOPLAM
    # yükle tek kademe çözüyordu (türbinde P3B4-02'nin kapattığı kusurun
    # pompa ikizi). Kural buradan İTHAL EDİLİR, yeniden yazılmaz.
    PUMP_STAGES_MAX, pump_stage_count,
    m3s_to_gpm, m_to_ft, npsh_available_m,
    npsh_required_velocity_head_m, tank_pressure_from_npsh_Pa)
# F2b-2 (v2.6.27): kamara akustiği ve chug eşikleri TEK KAYNAKTAN gelir.
# Bu modül eskiden kendi 1L/1T'sini ve kendi eşik çiftini taşıyordu; hibrit
# ve katı motorlar zaten merkezî modülü çağırıyordu (üç motorun üçüncüsü
# ayrı hesaplıyordu). acoustic_modes yalnız math/scipy'ye bağlıdır, döngüsel
# import yoktur. Chug ÇEVRİMİ (nötr eğri, kök yeri) hrma.stability.chug
# içindedir ve _stability_assessment içinde GEÇ (lazy) ithal edilir:
# hrma.stability scipy.special.lambertw yükler, motor import zincirini
# ağırlaştırmamak için çağrı noktasında ithal edilir.
from hrma.analysis.acoustic_modes import (
    CHUG_DP_RATIO_MINIMUM,
    CHUG_DP_RATIO_RECOMMENDED,
    CHUG_THRESHOLD_SOURCE,
    AcousticModeAnalyzer,
    longitudinal_frequency,
    transverse_frequency,
    transverse_root,
)
# Kullanıcı Cd bandının TEK tanımı enjektör modülündedir (bkz. USER_CD_RANGE
# künyesi); bu modül bandı kendi literalleriyle YENİDEN YAZMAZ.
from hrma.engines.injector_design import USER_CD_RANGE
# ÖH D24 · P15B2-09 (Fable-D18 ŞARTI): kapak/flanş cıvata birleşiminin
# varsayılan sözleşmesi birleşimi ÇÖZEN modülde tek kez yazılıdır; sıvı
# motor onu literal olarak yeniden yazmaz, buradan türetir
# (bkz. LIQUID_CLOSURE_JOINT_DEFAULTS). Hibrit motor aynı iki adı aynı
# takma adlarla içe aktarıyor — desen bilerek birebir aynı.
from hrma.analysis.bolted_joint import (
    CLOSURE_JOINT_DEFAULTS as _BOLTED_JOINT_CLOSURE_DEFAULTS,
    CLOSURE_JOINT_MEMBER_MATERIAL_DEFAULT as _BOLTED_JOINT_MEMBER_MATERIAL,
)
# v2.6.2: buradaki ``warnings.filterwarnings('ignore')`` KALDIRILDI.
# Argümansız çağrı SÜREÇ GENELİNDE catch-all filtre kurar — kapsam bu modül
# değil, tüm Python süreci. Yani sıvı motor modülünü içe aktarmak (app.py her
# açılışta yapıyor) uygulamanın tamamında numpy'nin sıfıra bölme / geçersiz
# değer uyarılarını öldürüyordu. Ampirik teyit: modülü import ettikten sonra
# ``np.float64(1.0)/np.float64(0.0)`` hiçbir RuntimeWarning basmadan inf
# döndürüyordu. Bu, NaN'ın sessizce çıktıya sızmasının ilk halkasıydı.
# Belirli bir uyarıyı bastırmak gerekirse dar kapsamlı yapılmalı:
#   warnings.filterwarnings('ignore', category=..., module=r'hrma\.engines\..*')

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
# TASARIM ÖZETİ DURUM SÖZLÜĞÜ (Faz 4B, bulgu B1/B2/A3)
#
# Aynı sözlük üç motor dosyasında da BİREBİR tanımlıdır (hybrid / liquid /
# solid); tam gerekçe ve etiket anlamları
# hrma/engines/hybrid_rocket_engine.py içindeki aynı blokta yazılıdır. Çapraz
# import bilinçli olarak yapılmaz; değerlerin aynı kaldığı makinece denetlenir:
#   tests/test_faz4_motor_kapilari.py::test_durum_sozlugu_uc_motorda_ayni
#
# ÖLÇÜM (2 Ağustos 2026, HEAD a7ff1e7): burada :4492'de koşulsuz 'OPTIMIZED'
# yazıyordu — hiçbir eniyileme çalışmamış olsa da, hatta itici çifti için
# yanma modeli hiç yokken bile.
# ---------------------------------------------------------------------------
DESIGN_STATUS_OPTIMIZED = 'OPTIMIZED'
DESIGN_STATUS_CALCULATED = 'CALCULATED'
DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS = 'ESTIMATED_WITH_DEFAULTS'
DESIGN_STATUS_TARGET_NOT_MET = 'TARGET_NOT_MET'
DESIGN_STATUS_UNVALIDATED_ESTIMATE = 'UNVALIDATED_ESTIMATE'
DESIGN_STATUS_NOT_CONVERGED = 'NOT_CONVERGED'

DESIGN_STATUS_SEVERITY = {
    DESIGN_STATUS_OPTIMIZED: 0,
    DESIGN_STATUS_CALCULATED: 1,
    DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS: 2,
    DESIGN_STATUS_TARGET_NOT_MET: 3,
    DESIGN_STATUS_UNVALIDATED_ESTIMATE: 4,
    DESIGN_STATUS_NOT_CONVERGED: 5,
}


class UnsupportedPropellantPairError(ValueError):
    """Tabloda da CEA kartında da olmayan itici çifti (bulgu A3).

    Böyle bir çift için yayımlanabilir bir yanma çözümü YOKTUR. Eskiden bu
    durumda düz yazılmış yer tutucular (Isp_sl = 285 s, Isp_vac = 320 s,
    c* = 1650 m/s) gerçek performansmış gibi döndürülüyordu. Artık hesap
    burada durur; çağıran (app.py /calculate_liquid) bunu HTTP 400 + gerekçe
    olarak kullanıcıya iletir.

    ``ValueError`` türetilmiştir ki mevcut ``except Exception``/``ValueError``
    yakalayan yollar (Monte Carlo, UQ fabrikaları) davranışlarını değiştirmeden
    çalışmayı sürdürsün.
    """

    def __init__(self, message, fuel=None, oxidizer=None, validity=None):
        super().__init__(message)
        self.reason_code = 'propellant_pair_not_modelled'
        self.fuel = fuel
        self.oxidizer = oxidizer
        self.validity = dict(validity or {})


class UnsupportedPropellantDensityError(ValueError):
    """İticinin YOĞUNLUĞU hiçbir kaynaktan çözülemedi — sayı uydurulmaz.

    ÖH D15 (P3B1-01). Yoğunluk sıvı motorun donanım zincirinin kökündedir:
    tank hacmi, besleme hattı çapı, enjektör orifisi, pompa gücü ve devri
    doğrudan ondan türer. Çözülemeyen yoğunluk için temsili bir sayı
    yayımlamak, kullanıcıya donanımı 11 kat yanlış boyutlanmış bir motoru
    "çözüldü" diye teslim etmek demektir (ölçüm: lh2/n2o4'te tank hacmi
    1,065 ⟷ 12,023 m³). Kapalı devre: ya tablodan/kullanıcıdan gerçek bir
    yoğunluk gelir, ya da motor kurulmaz.
    """

    def __init__(self, message, propellant=None, role=None):
        super().__init__(message)
        self.reason_code = 'propellant_density_not_available'
        self.propellant = propellant
        self.role = role


class UnsupportedInjectorTypeError(ValueError):
    """Enjektör tipinin devre modeli YOK — yerine başka tip tasarlanmaz.

    ÖH D17 (P3B1-12). Eski yönlendirme tablosu tanınmayan her tipi sessizce
    ``impinging_doublet``a düşürüyordu: kullanıcı 'unlike_impinging' (formun
    kendi seçeneği) ya da tanınmayan bir dize seçtiğinde ekranda BAŞKA bir
    enjektörün tasarımı, üstelik tip-bağımsız ΔP/Pc oranıyla görünüyordu.
    Kapalı devre: tip tanınır ve modellenir, ya da enjektör tasarlanmaz.
    """

    def __init__(self, message, injector_type=None):
        super().__init__(message)
        self.reason_code = 'injector_type_not_modelled'
        self.injector_type = injector_type


# Tablo dışı ama CEA ile ÇÖZÜLEBİLEN çiftlerde (ör. rp1/n2o4, lh2/n2o4) itici
# YOĞUNLUKLARI için beyan edilmiş yedek değerler [kg/m3]. Bunlar kimyadan
# TÜREMEZ, tipik bir hidrokarbon yakıt / depolanabilir oksitleyici mertebesidir
# ve yalnız çağıran hiçbir yoğunluk vermediğinde kullanılır: arayüzün
# ``fuel_density`` / ``oxidizer_density`` alanları _apply_overrides içinde
# (kurucu sırası: _set_propellant_properties -> _apply_overrides) bu değerleri
# EZER. Yanma performansı için yer tutucu üretmek yasaktır (bkz.
# UnsupportedPropellantPairError); yoğunluk bir yanma çözümü değil, ezilebilir
# bir madde özelliğidir ve bu ayrım bilinçlidir.
# ÖH D15 / sıvı (P3B1-01, kritik): bu iki sabit ARTIK KULLANILMIYOR.
# Ölçüldü (docs/scofield/raw/OH/D15/sivi/a1/once.json): arayüzün sunduğu 10
# çiftin 5'i (rp1/n2o4, lh2/n2o4, methane/n2o4, mmh/lox, udmh/lox) tabloda
# olmadığı için buraya düşüyordu; lh2/n2o4'te rho_fuel 800 ⟷ gerçek 70,85
# (11,3 kat) yayımlanıyor, üstelik künye 'built-in propellant table' diyordu —
# yayımlanan 3145 yaprağın 823'ü bu uydurma sayıdan türüyordu. Oysa doğru
# yoğunluklar AYNI tablonun içinde duruyor: her tür (rp1, lh2, methane, mmh,
# udmh, ethanol, lox, n2o4) tabloda en az bir çiftte geçiyor. Yoğunluk artık
# _species_densities_from_table ile TÜR bazında o tablodan okunur; tür de
# tabloda yoksa sayı UYDURULMAZ (fail-closed:
# UnsupportedPropellantDensityError). Sabitler yalnız tarihsel kayıt olarak
# ve eski çağıranların ImportError almaması için duruyor.
LIQUID_UNKNOWN_PAIR_FUEL_DENSITY = 800.0   # ARTIK KULLANILMIYOR (P3B1-01)
LIQUID_UNKNOWN_PAIR_OX_DENSITY = 1200.0    # ARTIK KULLANILMIYOR (P3B1-01)

# ---------------------------------------------------------------------------
# YERLEŞİK İTİCİ REFERANS TABLOSU (NASA CEA doğrulamalı çiftler)
# ÖH D15 / sıvı (P3B1-06): tablo eskiden _set_propellant_properties'in
# GÖVDESİNDE bir yerel değişkendi; dışarıdan okunamadığı için yedek gaz
# özellikleri sabitleri elle yazılmış bir "bant" iddiasıyla anlatılıyordu ve
# iddia yanlıştı (ölçüldü: cp'nin 6 değerinin 5'i beyan edilen bandın
# dışındaydı). Tablo modül düzeyine alındı; bant artık TABLODAN türetiliyor
# (bkz. unknown_pair_gas_reference) ve iki yerde yazılmıyor.
# ---------------------------------------------------------------------------
LIQUID_PROPELLANT_REFERENCE_TABLE = {
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


# Aynı çiftler için yanma GAZI taşıma özellikleri. Bunlar da performans değil:
# Bartz ısı-taşınım korelasyonu bir viskozite ve Prandtl sayısı ister, CEA
# köprüsü bunları döndürmez.
#
# ÖH D15 / sıvı (P3B1-06): burada eskiden ELLE YAZILMIŞ bir bant iddiası
# vardı — "yerleşik tablodaki altı çiftin ölçülen bandının ortasındadır
# (mu 5.78e-5 ... 6.89e-5, Pr 0.712 ... 0.751, cp 2156 ... 2287) ve bu bant
# zaten dardır". ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/sivi/a3/once.json):
# tablonun GERÇEK cp bandı 1978,3 ... 3418,9 J/kg·K'dir (beyan edilenin
# ~11 katı geniş) ve altı değerin BEŞİ beyan edilen bandın dışındadır;
# yedek cp = 2000,0 da beyan edilen bandın DIŞINDA kalıyordu. Künye kendi
# tablosunu yanlış anlatıyordu ve yedek "bandın ortası" değildi.
#
# Bant ve yedek artık TABLODAN türetilir (tek kaynak; iki yerde yazılmaz),
# bkz. ``unknown_pair_gas_reference()``. Aşağıdaki sabitler yalnız TARİHSEL
# kayıttır ve eski çağıranların ImportError almaması için durur; motor
# onları OKUMAZ.
LIQUID_UNKNOWN_PAIR_GAS_VISCOSITY = 6e-5      # TARİHSEL (P3B1-06)
LIQUID_UNKNOWN_PAIR_GAS_PRANDTL = 0.73        # TARİHSEL (P3B1-06)
LIQUID_UNKNOWN_PAIR_GAS_CP = 2000.0           # TARİHSEL (P3B1-06)
LIQUID_UNKNOWN_PAIR_DISSOCIATION_TEMP = 3000  # K

# Geopotansiyel <-> geometrik irtifa dönüşümünün etkin yarıçapı [m]
# (US Standard Atmosphere 1976 r0). Bu dosyada İKİ yerde çıplak sayı olarak
# duruyordu (irtifa performansı ve tasarım irtifası); tek tanım (ÖH D15 a3).
ISA_GEOPOTENTIAL_EARTH_RADIUS_M = 6356766.0


@lru_cache(maxsize=1)
def unknown_pair_gas_reference():
    """Tablo dışı çiftler için yanma gazı taşıma özellikleri — TABLODAN.

    Dönen sözlük her büyüklük için (value, band, basis) taşır. Değer,
    yerleşik tablonun o büyüklükteki MEDYANIDIR (medyan tek uçtaki
    değerden — cp'de lh2/lox 3418,9 — sürüklenmez); bant tablonun gerçek
    min/max'ıdır ve elle YAZILMAZ. Bartz zincirine giren sayı böylece her
    zaman tablonun içinden gelir ve künyesi bandı ölçerek söyler.
    """
    out = {}
    for alan, birim in (('mu_chamber', 'Pa.s'), ('pr_chamber', '-'),
                        ('cp_chamber', 'J/kg.K')):
        degerler = sorted(
            float(v[alan]) for v in LIQUID_PROPELLANT_REFERENCE_TABLE.values()
            if v.get(alan) is not None)
        n = len(degerler)
        if not n:                                        # pragma: no cover
            out[alan] = {'value': None, 'band': None, 'count': 0,
                         'basis': 'not_modelled (table carries no value)'}
            continue
        medyan = (degerler[n // 2] if n % 2
                  else 0.5 * (degerler[n // 2 - 1] + degerler[n // 2]))
        out[alan] = {
            'value': float(medyan),
            'band': [degerler[0], degerler[-1]],
            'count': n,
            'basis': (
                f'median of the {n} built-in propellant pairs '
                f'({medyan:.6g} {birim}); the measured spread of the table '
                f'is {degerler[0]:.6g} ... {degerler[-1]:.6g} {birim} '
                f'({degerler[-1] / degerler[0]:.2f}x), so this is a '
                'table-derived stand-in for a pair the table does not cover '
                '- not a solved property of THIS propellant pair'),
        }
    return out

# ---------------------------------------------------------------------------
# TASARIM SABİTLERİ (2026-07-19 uydurma denetimi)
# Kural: bir sayı birden fazla yerde kullanılıyorsa BURADA bir kez tanımlanır
# ve kaynağı yorumda belirtilir. Fonksiyon gövdesinde çıplak sayı bırakılmaz.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# L* ve DARALMA ORANI — ÖH D18 fizik-a2 (F2 ≡ OH-D15-01)
#
# Ölçüldü (once_f2f3.json, taban e726048'de beş sıvı koşumu):
#   * Taban daralma oranı d_c/d_t = 3,5 → ε_c = 12,25 idi. Huzel & Huang
#     SP-125 Tablo 1-3'ün TAMAMI 1,3-6 bandındadır: taban bandın 2,04 KATI,
#     pompa beslemeli bandın (1,3-2,5) ~5 katıydı. Beş koşumun BEŞİ de
#     ε_c = 12,25 yayımlıyordu.
#   * Konverjan koni (yarı açı 30°) o oranda tek başına L* = 12,088·d_t
#     tutuyordu; taban L* = 1,2 m boğazı 99,3 mm'yi geçen HER motorda
#     ulaşılamaz hâle geliyor ve 'yayımlanan L*'ı yükselt' kaçış yolu
#     ateşleniyordu: 100 kN'da 2,63 m (+%119), 500 kN'da 4,15 m (+%246).
#     Yani istenen 1,2 m ile çizilen hazne arasındaki fark 3,5 KATA çıkıyordu.
#   * Silindirik boy L*/ε_c'ye kilitleniyordu (1,2/12,25 = 97,96 mm), yani
#     500 kN motorun haznesi 853 mm çapında ve 98 mm boyunda bir GÖZLEME idi:
#     L_c/D_c = 0,115. Beş koşumun beşinde de L_c/D_c < 0,5.
#
# Onarım: L* itici çiftine anahtarlı tablodan (SP-125 Tablo 4-1), daralma
# oranı boğaz ÇAPINA bağlı kestirimden gelir; ikisi de bandıyla beyan edilir.
# ---------------------------------------------------------------------------

# Karakteristik uzunluk L* [m] — itici çiftine anahtarlı TEK tablo.
# Kaynak: Huzel & Huang, NASA SP-125 (1971) Böl. IV Tablo 4-1 (s. 87);
# inçten metreye çevrilmiş bantlar. Anahtar (yakıt, oksitleyici) kanonik
# küçük harf; değer (alt, üst) metre. Varsayılan bandın ORTASIDIR ve
# yayımlanan künye bandı da söyler.
L_STAR_BY_PAIR_M = {
    # LOX/RP-1 40-50 in
    ('rp1', 'lox'): (1.02, 1.27),
    ('kerosene', 'lox'): (1.02, 1.27),
    # LOX/LH2, LH2 enjeksiyonu 30-40 in (GH2 enjeksiyonu 22-28 in ayrı satır;
    # HRMA enjektör fazını modellemediği için KÖTÜMSER, yani uzun olan alınır)
    ('lh2', 'lox'): (0.76, 1.02),
    # LOX/NH3 30-40 in
    ('nh3', 'lox'): (0.76, 1.02),
    # N2O4 / hidrazin ailesi (MMH, UDMH, A-50) 30-35 in
    ('mmh', 'n2o4'): (0.76, 0.89),
    ('udmh', 'n2o4'): (0.76, 0.89),
    ('hydrazine', 'n2o4'): (0.76, 0.89),
    ('aerozine50', 'n2o4'): (0.76, 0.89),
    # Nitrik asit / hidrazin 30-35 in (RFNA/IRFNA aynı satır)
    ('hydrazine', 'rfna'): (0.76, 0.89),
    ('hydrazine', 'irfna'): (0.76, 0.89),
    ('mmh', 'rfna'): (0.76, 0.89),
    ('mmh', 'irfna'): (0.76, 0.89),
    ('udmh', 'rfna'): (0.76, 0.89),
    ('udmh', 'irfna'): (0.76, 0.89),
    # H2O2/RP-1 (katalizör yatağı dâhil) 60-70 in
    ('rp1', 'h2o2'): (1.52, 1.78),
    ('kerosene', 'h2o2'): (1.52, 1.78),
    # LF2/LH2 22-26 in (paralel enjeksiyon) ile 25-30 in (çapraz) satırlarını
    # KAPSAYAN bant; hangi enjeksiyon olduğu modellenmediği için birleşik.
    ('lh2', 'lf2'): (0.56, 0.76),
}
# Tabloda OLMAYAN çift için SP-125'in GENEL aralığı (15-120 in, kalış süresi
# 0,002-0,040 s). KU-K1/SP-H1 K4: bu iki aralık Tablo 4-1'in değil s. 87
# METNİNİN aralığıdır; Tablo 4-1'in kendi satırları 22-70 in arasıdır. Bu bir çift-özel değer DEĞİLDİR ve yayında
# öyle de söylenir; sayı uydurulmaz, "hangi satırdan geldiği" beyan edilir.
# TEK KAYNAK: genel taban ve genel bant hrma.constants'tadır (aynı sayıyı
# hrma/analysis/kinetic_efficiency.py da oradan okur — eskiden 1,2 ⟷ 1,0
# çelişkisi vardı).
from hrma.constants import (L_STAR_DEFAULT_M,          # noqa: E402
                            L_STAR_GENERIC_BAND_M)     # noqa: E402
L_STAR_MIN_M, L_STAR_MAX_M = 0.3, 5.0
L_STAR_TABLE_SOURCE = (
    'Huzel & Huang, NASA SP-125 (1971) Ch. IV Table 4-1 (p. 87), '
    'propellant-pair chamber characteristic length L* = V_c/A_t, inches '
    'converted to metres. The published default is the MIDPOINT of that '
    "pair's band and the band itself is published next to it.")

# Daralma oranı ε_c = A_c/A_t.
# Kullanıcı vermezse boğaz ÇAPINDAN kestirilir (RPA pratiği):
#     ε_c = 8 · D_t[cm]^(-0,6) + 1,25
# UYARI: bu bağıntının BİRİNCİL KAYNAĞI DOĞRULANAMADI (SP-125'te yoktur;
# D18 literatür raporu §3 "açık kalanlar" 1. madde). Bu yüzden künyesi
# "ampirik, birincil kaynak doğrulanmamış" der ve sonuç Huzel & Huang
# Tablo 1-3 bandına (1,3-6) KIRPILIR — sessiz kullanım yasak.
CONTRACTION_RATIO_CORRELATION_BAND = (1.3, 6.0)      # H&H Tablo 1-3
CONTRACTION_RATIO_PUMP_FED_BAND = (1.3, 2.5)         # H&H Böl. IV metni
CONTRACTION_RATIO_PRESSURE_FED_BAND = (2.0, 5.0)     # H&H Böl. IV metni
CONTRACTION_RATIO_CORRELATION_BASIS = (
    'eps_c = 8 * D_t[cm]^-0.6 + 1.25, clipped to the Huzel & Huang NASA '
    'SP-125 Table 1-3 band [1.3, 6.0]. EMPIRICAL, PRIMARY SOURCE '
    'UNVERIFIED: the correlation is quoted for RPA-style preliminary sizing '
    'but is NOT in SP-125, so it is used only as a banded estimate and never '
    'silently. A user-supplied contraction ratio always wins. '
    'The hunt for a primary source was REPEATED and RECORDED in D23 '
    '(OH-D18-04, docs/scofield/raw/OH/D23/sivi/a1/literatur_olcum.json): two '
    'independent web engines returned only derivative uses that reproduce '
    'the identical expression without attribution, so "primary source '
    'unverified" is now a MEASURED statement, not an assumption. The '
    'documented alternative (falling back to the mid-point of the Huzel & '
    'Huang family band) was NOT taken: it would replace a monotone '
    'throat-size trend with a constant and move eps_c by up to +216% at a '
    '30 mm throat (chamber diameter scales with sqrt(eps_c)), which is a '
    'product-behaviour change needing its own ruling, not a repair of an '
    'unsourced number.')
# Silindirik hazne boyu / hazne çapı pratik bandı. Bant YORUMDUR (SP-125 bir
# L_c/D_c sınırı vermez); dışına çıkıldığında hüküm verilmez, uyarı yayımlanır.
CHAMBER_LENGTH_DIAMETER_BAND = (0.5, 4.0)
CHAMBER_DIAMETER_MIN_M = 0.05
CONTRACTION_RATIO_MIN, CONTRACTION_RATIO_MAX = 1.5, 60.0


def l_star_band_for_pair(fuel, oxidizer):
    """(alt_m, ust_m, kaynak_etiketi) — itici çifti için L* bandı.

    Çift tabloda yoksa SP-125'in GENEL aralığı ve 'generic' etiketi döner;
    çağıran bu etiketi künyeye ve uyarıya taşır (sessiz düşüş yok).
    """
    f = str(fuel or '').strip().lower()
    o = str(oxidizer or '').strip().lower()
    band = L_STAR_BY_PAIR_M.get((f, o))
    if band is not None:
        return band[0], band[1], 'sp125_table_4_1_pair'
    return (L_STAR_GENERIC_BAND_M[0], L_STAR_GENERIC_BAND_M[1],
            'sp125_table_4_1_generic')


#: Metre -> milimetre dönüşüm katsayısı (SI, tanım gereği tam 1000).
#:
#: ÖH D26 / OH-D25-16 (zincir OH-D17-15). ÖLÇÜLDÜ (``a2/once.json``
#: ``OH-D25-16.ifade_yerleri``): AYNI kaynak sözlüğün (``nozzle_geom``) aynı
#: üç alanı (``throat_diameter`` / ``exit_diameter`` / ``nozzle_length``)
#: **dokuz ayrı yerde** elle çarpılarak mm'ye çevriliyordu, üstelik iki
#: farklı yazımla: üst düzey blokta ``float(x) * 1000.0``, motor bloğunda
#: ``x * 1000``. Bugün ikisi de aynı sayıyı veriyor (ölçüldü: ``repr`` eşit,
#: tipler ``float``/``float``) — yani bu bir sayı kusuru DEĞİL, doktrin-4
#: (TEK KAYNAK) ihlalidir: dönüşüm dokuz yerde ayrı ayrı yazıldığı için
#: birinin ``float()`` sarmalayıp diğerinin sarmalamaması gibi ayrışmalar
#: sessizce doğabiliyordu (kaynak ``numpy`` skaleri döndürseydi iki yaprağın
#: JSON tipi ayrışırdı). Dönüşüm tek noktaya alındı; SAYI DEĞİŞMEDİ.
MM_PER_M = 1000.0


def m_to_mm(deger_m):
    """Metre cinsinden uzunluğu milimetreye çevirir — TEK dönüşüm noktası.

    ``float()`` sarmalaması KASITLIDIR: kaynak sözlük ``numpy`` skaleri
    taşırsa yayımlanan yaprağın tipi yine yerleşik ``float`` olur ve JSON
    çıktısı çağrı yerine göre ayrışmaz.
    """
    return float(deger_m) * MM_PER_M


def contraction_ratio_estimate(d_t_m):
    """Boğaz çapından daralma oranı kestirimi (bantla kırpılmış).

    Döner: (eps_c, ham_eps_c, kirpildi_mi). ``d_t_m`` metre.
    """
    d_t_cm = max(float(d_t_m), 1e-9) * 100.0
    ham = 8.0 * d_t_cm ** (-0.6) + 1.25
    alt, ust = CONTRACTION_RATIO_CORRELATION_BAND
    eps = min(max(ham, alt), ust)
    return float(eps), float(ham), bool(eps != ham)

# Rejeneratif soğutma kanalları (varsayılan kesit; Huzel & Huang Ch. 4 tipik
# 1-3 mm kanal). Kanal sayısı varsayılanı GEOMETRİDEN hesaplanır — ÖH A2
# sivi-sogutma · F-17: TEK ölçüt ``regen_cooling.channel_fit_limit``
# (N·(w + s) <= 2·pi·(r_boğaz + t_sıcak_cidar); kanal TABANI çevresi,
# NASA SP-8087). Eski satır ``n = floor(pi * D_boğaz / (w + land))`` iç gaz
# çevresini ölçüyordu ve regen modülündeki kaburgasız ikinci kopyayla
# çelişiyordu. (P3B1-10, D23: bağlayıcı eksenel kesit BOĞAZDIR.)
COOLING_CHANNEL_WIDTH_DEFAULT_M = 3.0e-3
COOLING_CHANNEL_HEIGHT_DEFAULT_M = 2.0e-3
# Kanal yüksekliği (derinliği) tasarım serbestliğidir (formda girdisi yok):
# hız hedefi aşılırsa yükseklik hedefe göre BÜYÜTÜLÜR ve etiketlenir.
# Hedef hız 40 m/s: HRMA'nın MUHAFAZAKÂR tavanıdır. KU-K5 (6 Eki 2026): eski
# künye 40 m/s'yi bir "30-60 m/s bandının ortası" diye Huzel & Huang Ch. 4
# ve NASA SP-8087'ye bağlıyordu. NASA
# SP-8087 (1972) §3.1.1.5.3 s. 62: sıvı soğutucu hızı 200 ft/s (61 m/s)
# ALTINDA tutulur — bir ÜST SINIR, "30-60 m/s bandı" değil; 40 m/s bu
# sınırın içindedir. NASA SP-125'te genel hız bandı YOK (tek örnek RP-1
# 26,7 m/s, Örnek 4-4, s. 111; SP-H1 K10). Değer DEĞİŞMEDİ (KC-6).
COOLANT_CHANNEL_TARGET_VELOCITY_MS = 40.0
# Frezeli kanal pratik derinlik üst sınırı. KU-K1/SP-H1 K12: eski künye
# "Huzel & Huang Ch. 4" idi; SP-125 (1967) bu sınırı içermez; AIAA 1992
# baskısı okunmadı — kaynaksız pratik sınır, sayfa doğrulanmadı.
COOLING_CHANNEL_HEIGHT_MAX_M = 10.0e-3
# Süperkritik marş hızıyla derinlik boyutlandırması (sıvı 6. tur): sabit
# nokta adım sınırı (hesap kaynağı sınırı) ve hedef üstü kabul payı. İkisi
# de HRMA sayısal ayarıdır (kaynak değil); hedefin kendisi yukarıda.
REGEN_MARCH_SIZING_MAX_ITER = 4
REGEN_MARCH_SIZING_REL_TOL = 0.01
# v2.6.26 BEYAN ÇÜRÜMESİ DÜZELTMESİ: eskiden tek bir
# ``channel_section_source: 'design default (not auto-sized)'`` metni HEM
# genişliği HEM derinliği anlatıyordu ve derinlik için YALAN söylüyordu —
# derinlik hız hedefine göre otomatik boyutlanıyor (ölçüldü: 2 MN itkide
# 6,70 mm). Üstelik beyan ``_calculate_thermal_protection_system`` bloğunda,
# sayı ise ``cooling_system`` bloğundaydı: sayı bir yerde, gerekçesi başka
# yerde. Artık iki AYRI metin var ve ikisi de kendi sayısının yanında duruyor.
COOLING_CHANNEL_WIDTH_BASIS = (
    'fixed design default channel width (Huzel & Huang Ch. 4, typical 1-3 mm '
    'milled channel); NOT auto-sized and not a user input. The same width '
    'also sets the geometric channel count through the channel-base '
    'circumference at the throat (see cooling_system.channel_count_fit)')
COOLING_CHANNEL_HEIGHT_BASIS = (
    'default channel height (depth), which IS auto-sized: when the resulting '
    f'coolant velocity exceeds the {COOLANT_CHANNEL_TARGET_VELOCITY_MS:.0f} '
    'm/s design target the depth is increased to meet it, up to the '
    f'{COOLING_CHANNEL_HEIGHT_MAX_M * 1e3:.0f} mm milled-channel ceiling. It '
    'stays at the default only while the velocity target is already met; the '
    'channel_count_source field records when the auto-sizing actually fired')
# Kanallar arası kaburga (land) genişliği ve sığma ölçütü: TEK TANIM
# regen_cooling'de (F-17; künye COOLING_CHANNEL_LAND_BASIS). Buradaki ad
# geriye uyum için AYNI nesneye bağlanır, sayı ikinci kez yazılmaz.
from hrma.analysis.regen_cooling import (  # noqa: E402
    COOLING_CHANNEL_LAND_M as COOLING_CHANNEL_LAND_DEFAULT_M,
    COOLING_CHANNEL_LAND_BASIS, channel_fit_limit)
COOLING_CHANNEL_COUNT_MIN, COOLING_CHANNEL_COUNT_MAX = 4, 2000
# İşlenmiş kanal yüzeyi mutlak pürüzlülüğü [m] (Ra 3.2 um, form varsayılanı).
COOLING_CHANNEL_ROUGHNESS_DEFAULT_M = 3.2e-6
COOLANT_FLOW_FRACTION_DEFAULT = 1.0          # yakıtın tamamı soğutucu
COOLANT_INLET_TEMP_DEFAULT_K = 300.0

# Soğutma tipine göre varsayılan sıcak cidar sıcaklıkları [K]
# (kullanıcı max_wall_temp verirse o kullanılır).
#
# ÖH D31 · OH-D25-25 — KÜNYE. Bu beş sayı KAYNAKSIZ BİR VARSAYIM KÜMESİDİR:
# hiçbir literatür tablosundan alınmadılar ve hiçbir denklemden türemezler;
# soğutma tipine göre "makul bir sıcak cidar" seçen mühendislik yerleşiğidir.
# ÇÖZÜLMÜŞ cidar sıcaklığı yalnız süperkritik istasyon marşı kurulduğunda
# vardır (metan/LH2 rejeneratif; _solve_supercritical_regen) ve o zaman bu
# tablo KULLANILMAZ. Çalışma anında hangisinin geçerli olduğu çıktıda
# ``wall_temperature_source`` ile zaten beyan ediliyor; eksik olan sabit
# tanımının kendi künyesiydi, o da budur. Sayıyı kullanan her yanıt
# ``wall_temperature_default_basis`` alanını da taşır.
WALL_TEMP_DEFAULT_BASIS = (
    'UNSOURCED ASSUMPTION SET: the hot-wall temperature defaults are '
    'engineering placeholders chosen per cooling type, not values taken '
    'from a reference table and not derived from any equation. They are '
    'used only when the user supplies no max_wall_temp AND no solved wall '
    'is available (the 1D supercritical station march solves the wall for '
    'regeneratively cooled methane/LH2 and overrides them). Supply '
    'max_wall_temp for a design-driven number.')
WALL_TEMP_DEFAULT_K = {'regenerative': 800.0, 'film_cooling': 900.0,
                       'dump_cooling': 850.0, 'ablative': 1200.0,
                       'radiative': 1800.0}

# ÖH D31 · OH-D25-25 — DUMP SOĞUTMA CEKET DEBİSİ / ΔP: MODELLENMEDİ.
# ÖLÇÜLDÜ (docs/scofield/raw/OH/D31/sivi/a1/once_dump.json, 25 kN RP-1/LOX):
# dump_cooling seçen kullanıcı rejeneratif sayılarının TA KENDİSİNİ alıyordu
# (ceket debisi 2,561458273760645 kg/s ve ΔP 3,761542589148719 bar iki tipte
# BİT-AYNI) ve künye ona "regenerative jacket flow" diyordu. Dump soğutmada
# soğutucu ceketten geçip hazneye DÖNMEZ, dışarı atılır; debisi yakıtın
# tamamı değil kaynak künyeli bir BLEED KESRİDİR ve o kesir için model
# kazanılamadı (Huzel & Huang dump-cooling bleed kesri — literatür kalemi).
# Doğru hamle modellemek değil REDDETMEKTİR: sayı yayımlanmaz.
DUMP_COOLING_BLEED_NOT_MODELLED = (
    'NOT MODELLED: dump cooling discharges the coolant overboard instead of '
    'returning it to the chamber, so the jacket flow is a source-cited BLEED '
    'FRACTION of the fuel, not the whole fuel budget. HRMA has no bleed-'
    'fraction model (Huzel & Huang Ch. 4 dump-cooling flow split), so the '
    'jacket flow rate and the jacket pressure drop are NOT published for '
    'this cooling type - publishing the regenerative numbers under a dump '
    'label would be a silent substitution. The thermal load, the wall '
    'temperatures and the film-cooling chain are unaffected.')
WALL_TEMP_COLD_DEFAULT_K = {'regenerative': 350.0, 'film_cooling': 400.0,
                            'dump_cooling': 380.0, 'ablative': 500.0}

# Soğutma tipi TANINAN değerler — TEK tanım noktası (ÖH defter P3B4-09,
# Z5S/PK1). Motorun cidar sıcaklığı tablosu zaten bu beş değeri biliyordu;
# kapılar ise "ablatif/radyatif DEĞİLSE aktif soğutuluyordur" diye kuruluydu
# ve TANINMAYAN her dize ('banana', 'none', '') o hükmü alıyordu. Küme
# tablodan TÜRETİLİR ki iki liste ayrışamasın.
COOLING_TYPES_PASSIVE = ('ablative', 'radiative')
COOLING_TYPES_RECOGNISED = tuple(WALL_TEMP_DEFAULT_K)
COOLING_TYPES_ACTIVE = tuple(t for t in COOLING_TYPES_RECOGNISED
                             if t not in COOLING_TYPES_PASSIVE)

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

# İTİCİ KAPASİTE referansı için alan oranı: statik tablonun "Area ratio
# 200:1" çapasıyla aynı sözleşme. DİKKAT (2026-07-22 doğruluk düzeltmesi):
# bu SADECE "bu itici çifti çok uzun bir lülede ne verir" kapasite sayısıdır,
# motorun performansı DEĞİLDİR. Motorun Isp'si kendi genişleme oranında
# (kullanıcı ε'su ya da ortam-eşlenik ε) çözülür — bkz.
# _design_expansion_ratio / _finalize_performance_reference.
VACUUM_REFERENCE_EPS = 200.0

# Optimum O/F taraması (2026-07-23): canlı CEA yolunda maksimum Isp veren
# karışım oranı ARTIK hesaplanır, kullanıcıdan alınmaz. Band, kimyasal
# iticilerin pratik O/F aralığını kapsayacak genişliktedir (LH2/LOX ~4-6,
# RP-1/LOX ~2.2-2.8, N2O4/MMH ~1.6-2.2, metan/LOX ~3.2-3.8; Sutton &
# Biblarz 9. baskı Böl. 5 tabloları). Tepe, parabolik uydurmayla ızgara
# adımının altına indirilir.
OF_OPTIMUM_SCAN_BAND = (0.8, 8.0)
OF_OPTIMUM_SCAN_POINTS = 25

# KRİTİK Weber sayısı — damlacık aerodinamik parçalanma EŞİĞİ. Hesaplanan bir
# Weber sayısı DEĞİLDİR; damlacık çapı bu eşikten geri çözülür:
#     D = We_krit * sigma / (rho_gaz * v_bagil^2)
# (Lefebvre & McDonell, "Atomization and Sprays" 2. baskı, Böl. 2). v2.6.26'ya
# kadar çıktıya 'weber_number' adıyla basılıyordu ve AYNI yanıtta
# injector_design_detail.*.weber_number GERÇEKTEN hesaplanan Weber sayısını
# taşıyordu — aynı ad, iki anlam.
CRITICAL_WEBER_NUMBER = 12
CRITICAL_WEBER_NUMBER_BASIS = (
    'critical Weber number, i.e. the droplet aerodynamic breakup threshold '
    '(We_crit ~ 12 for low-viscosity liquids; Lefebvre & McDonell '
    '"Atomization and Sprays" 2nd ed. Ch. 2). It is a breakup CRITERION, NOT '
    'a computed Weber number - the field was called weber_number until '
    'v2.6.26, which collided with the genuinely computed Weber number of the '
    'injector module. It only drives the legacy fallback droplet estimate: '
    'whenever injector_design solves, the reported droplet_diameter is that '
    'module\'s SMD correlation (injector_design_detail.atomization) and this '
    'threshold is a comparison value only')

# ---------------------------------------------------------------------------
# İMALAT BİLGİSİ (2026-07-28 dürüstlük denetimi, LIQ-MFG-4)
# HRMA'da tedarikçi fiyatı, işçilik ücreti ve program takvimi verisi YOKTUR.
# Bu yüzden maliyet/termin ÜRETİLMEZ. Üretilen tek sayısal imalat bilgisi
# tolerans; o da motorun GERÇEK nominal ölçüsünden standart tablosuyla
# aranır ve tasarım toleransı olmadığı açıkça etiketlenir.
# ---------------------------------------------------------------------------

# ISO 2768-1 "Genel toleranslar — lineer ölçüler" izin verilen sapmalar [mm].
# Her satır: (nominal ölçü aralığının ÜST sınırı, {sınıf: ± sapma}).
# f = hassas (fine), m = orta (medium). Standardın kapsamı 0.5-4000 mm'dir;
# dışında kalan ölçüde genel tolerans verilmez, ölçü tek tek belirtilir.
ISO2768_LINEAR_TOLERANCE_MM = (
    (3.0, {'f': 0.05, 'm': 0.1}),
    (6.0, {'f': 0.05, 'm': 0.1}),
    (30.0, {'f': 0.1, 'm': 0.2}),
    (120.0, {'f': 0.15, 'm': 0.3}),
    (400.0, {'f': 0.2, 'm': 0.5}),
    (1000.0, {'f': 0.3, 'm': 0.8}),
    (2000.0, {'f': 0.5, 'm': 1.2}),
    (4000.0, {'f': None, 'm': 2.0}),
)
ISO2768_MIN_NOMINAL_MM = 0.5

# Akışa hassas işlenmiş yüzeyler hassas sınıfta, gövde/montaj ölçüleri orta
# sınıfta aranır (atölye pratiği).
ISO2768_GRADE_PRECISION = 'f'
ISO2768_GRADE_GENERAL = 'm'

ISO2768_TOLERANCE_BASIS = (
    'ISO 2768-1 general tolerance looked up for the computed nominal size; '
    'workshop standard, NOT a performance-driven tolerance allocation')

# Nitel üretim rotası: motorun soğutma/enjektör/besleme seçimine göre TİPİK
# yöntem. Sayı değildir, ölçüt değildir; çıktıda kaynağıyla etiketlenir.
MANUFACTURING_ROUTE_BASIS = (
    'typical production route for the selected configuration; qualitative, '
    'not a manufacturing plan and not computed from the analysis')

CHAMBER_PROCESS_BY_COOLING = {
    'regenerative': 'Machined liner, milled coolant channels, brazed closeout',
    'dump_cooling': 'Machined liner, milled coolant channels, brazed closeout',
    'film_cooling': 'Forged and machined shell with film-coolant ring',
    'ablative': 'Structural case with ablative liner layup',
    'radiative': 'Formed refractory-alloy shell, welded',
}
CHAMBER_PROCESS_DEFAULT = 'Forged and machined'

NOZZLE_PROCESS_BY_COOLING = {
    'regenerative': 'Brazed cooling channels',
    'dump_cooling': 'Brazed cooling channels',
    'film_cooling': 'Machined contour with film-coolant slots',
    'ablative': 'Ablative liner in a composite overwrap',
    'radiative': 'Formed refractory-alloy contour, welded',
}
NOZZLE_PROCESS_DEFAULT = 'Machined contour'

INJECTOR_PROCESS_BY_TYPE = {
    'impinging': 'CNC drilled impinging orifices',
    'coaxial': 'CNC machined coaxial elements',
    'showerhead': 'CNC drilled showerhead orifices',
    'pintle': 'CNC machined pintle assembly',
}
INJECTOR_PROCESS_DEFAULT = 'CNC machined orifices'

FEED_PROCESS_BY_TYPE = {
    'turbopump': 'Investment cast impellers, machined and welded volutes',
    'pressure_fed': 'Pressurant tank, regulator and valve assembly '
                    '(no turbomachinery)',
}
FEED_PROCESS_DEFAULT = 'Feed system hardware not identified'

# Maliyet ve termin alanları v2.6.26'da KALDIRILDI. Arayüz boş hücre yerine
# bu açıklamayı basabilsin diye alanın yokluğu açıkça raporlanır.
MANUFACTURING_COST_STATUS = (
    'not calculated: HRMA has no supplier pricing, labour-rate or programme '
    'schedule data. Development/unit cost and phase durations were removed '
    'because the previous values were fixed literals, identical for a 10 N '
    'thruster and a 2 MN booster engine')


def _iso2768_linear_tolerance_mm(nominal_mm, grade=ISO2768_GRADE_PRECISION):
    """Nominal ölçü için ISO 2768-1 genel tolerans sapması [mm].

    Standardın kapsamı dışındaki ölçüde ya da geçersiz girdide None döner:
    uydurma tolerans üretilmez, çağıran alanı açıkça etiketler.
    """
    try:
        nominal = float(nominal_mm)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(nominal) or nominal < ISO2768_MIN_NOMINAL_MM:
        return None
    for upper, grades in ISO2768_LINEAR_TOLERANCE_MM:
        if nominal <= upper:
            return grades.get(grade)
    return None


def _iso2768_feature(nominal_mm, grade=ISO2768_GRADE_PRECISION):
    """Tek bir kritik ölçünün tolerans kaydı: nominal + sapma + sınıf.

    Ölçü yoksa/geçersizse None döner (çağıran alanı hiç yazmaz); ölçü var ama
    standardın kapsamı dışındaysa sapma None kalır ve durumu yazılır.
    """
    try:
        nominal = float(nominal_mm)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(nominal) or nominal <= 0:
        return None
    entry = {'nominal_mm': round(nominal, 3), 'iso_grade': grade,
             'tolerance_mm': _iso2768_linear_tolerance_mm(nominal, grade),
             # v2.6.26: sapma HESAPLANAN nominal ölçüden aranır ama standardın
             # tablosu BASAMAKLIDIR — nominal aynı ölçü bandında kaldığı sürece
             # sapma kıpırdamaz. Bu bir uydurma sabit değil, bir arama
             # sonucudur; ayrımı okuyucu göremeyeceği için yazılı beyan edilir.
             'tolerance_basis': (
                 f'ISO 2768-1 general linear tolerance, grade {grade}, looked '
                 'up for the computed nominal size. The standard is banded, '
                 'so the tolerance is a step function of the nominal and stays '
                 'constant while the nominal stays inside one size band. It is '
                 'a workshop standard, NOT a performance-driven tolerance '
                 'allocation')}
    if entry['tolerance_mm'] is None:
        entry['status'] = ('nominal size outside the ISO 2768-1 range '
                           '(0.5-4000 mm); tolerance must be specified '
                           'individually on the drawing')
    return entry


@lru_cache(maxsize=256)
def _optimal_mr_scan_cached(fuel, oxidizer, pc_bar, eps, n_points,
                            olcut='isp'):
    """Ölçütü maksimize eden O/F — CEA taraması, önbellekli.

    ``olcut='isp'``  -> vakum Isp tepesi (tasarım O/F'si)
    ``olcut='thrust'`` -> itki katsayısı (Isp/c*) tepesi; sabit Pc ve boğazda
    itkiyi maksimize eden O/F (P3B1-04).

    Optimum, İMZADAKİ dört büyüklüğün fonksiyonudur: itici çifti, Pc ve
    referans genişleme oranı eps (artı tarama çözünürlüğü). Motorun itkisi
    ya da çevrimi onu değiştirmez, AMA eps motorun GEOMETRİSİDİR ve çağıran
    (``_optimal_mixture_ratio``) motorun tasarım eps'ini geçirir - yani
    lüle geometrisi optimumu DEĞİŞTİRİR. ÖH defter P3B1-13 (D23): bu
    docstring "motorun ... geometrisi ya da çevrimi onu değiştirmez"
    diyordu ve kendi içinde çelişiyordu; ÖLÇÜLDÜ (25 kN / 60 bar RP1-LOX,
    yalnız nozzle_expansion_ratio süpürüldü): eps=5 -> O/F 2,43912;
    eps=200 -> 2,95384, yani %21,1 kayma. Yayımlanan sayı doğruydu, beyan
    yanlıştı. Önbellek anahtarı eps'i ZATEN içerdiği için önbellek
    doğruluğu bozulmuyor - beyanın düzeltilmesi o denetimi de mümkün kılar.

    Modül seviyesinde önbelleğe alınır: kullanıcı formda önbellek
    anahtarına GİRMEYEN başka bir alanı oynattığında 25 CEA çağrısı TEKRAR
    yapılmaz (soğuk tarama ~3-12 s sürüyordu; sıcak isabet anlıktır).
    Argümanlar hashlenebilir olsun diye yuvarlanmış skalerlerdir.

    Çözülemezse None döner — çağıran 'not_solved' etiketi koyar, sahte
    optimum ÜRETİLMEZ.
    """
    from hrma.engines import cea_bridge
    lo, hi = OF_OPTIMUM_SCAN_BAND
    mrs = np.linspace(lo, hi, int(n_points))
    isps = []
    for mr in mrs:
        try:
            props = cea_bridge.get_combustion_properties(
                fuel, oxidizer, float(pc_bar), float(mr),
                expansion_ratio=float(eps))
        except Exception:
            isps.append(None)
            continue
        if props.get('source') != 'rocketcea':
            isps.append(None)
            continue
        isp = props.get('isp_vac_s')
        if olcut == 'thrust':
            # P3B1-04: SABİT oda basıncı ve SABİT boğazda itki
            #     F = mdot.Isp.g0 ,  mdot = C_D.Pc.A_t / c*
            # olduğundan F ∝ Isp/c* = CF/g0 — yani itki optimumu itki
            # KATSAYISININ tepesidir, Isp'ninki değil (Sutton & Biblarz 9.
            # baskı Denk. 3-30/3-31; Huzel & Huang SP-125 Böl. I §1.3,
            # s. 10-16 — KU-K1/SP-H1 K45: eski künye "Böl. 2"). c* karışım
            # zenginleştikçe düşer, bu yüzden CF tepesi Isp tepesinin
            # SAĞINDA (daha yüksek O/F'de) kalır.
            c_star = props.get('c_star_m_s')
            isps.append(float(isp) / float(c_star)
                        if (isp and c_star) else None)
        else:
            isps.append(isp)
    valid = [v for v in isps if v is not None]
    if not valid:
        return None
    k = int(np.argmax([v if v is not None else -1.0 for v in isps]))
    best = float(mrs[k])
    # Tepe komşularıyla parabolik iyileştirme (ızgara adımının altına iner)
    if 0 < k < len(mrs) - 1 and None not in (isps[k - 1], isps[k + 1]):
        y0, y1, y2 = isps[k - 1], isps[k], isps[k + 1]
        denom = (y0 - 2.0 * y1 + y2)
        if denom != 0:
            delta = 0.5 * (y0 - y2) / denom
            if abs(delta) <= 1.0:
                best = float(mrs[k] + delta * float(mrs[1] - mrs[0]))
    return best

# --- TESLİM (delivered) performans zinciri --------------------------------
# CEA IDEAL (kayıpsız, tek boyutlu, denge) değer verir. Gerçek motorun
# teslim Isp'si dört mekanizmayla düşer (JANNAF basitleştirilmiş performans
# metodolojisi; Sutton & Biblarz 9th ed. Böl. 3.5, Huzel & Huang SP-125
# Böl. I §1.3 s. 10-16 ve Böl. IV — KU-K1/SP-H1 K45: eski künye "Böl. 1-4"):
#     Isp_teslim = Isp_CEA(ε) · η_c* · λ_sapma · η_sürtünme · η_kinetik
# HRMA bu zincirin ÜÇÜNÜ hesaplar (λ konturdan, η_sürtünme kaynaklı tipik
# değerden, η_kinetik CEA donmuş/kayan bandından); η_c* enjektör/karışım
# kalitesine bağlıdır ve tasarım girdilerinden TÜRETİLEMEZ — kullanıcı
# 'combustion_efficiency' girmezse 1.0 alınır (ek varsayım YOK) ve bu durum
# çıktıda açıkça etiketlenir. Bunun sonucu: HRMA'nın varsayılan Isp'si
# "mükemmel enerji salımı" üst sınırıdır; gerçek motorların η_c*'ı
# 0.92-0.99 bandındadır (Sutton & Biblarz 9th ed. Böl. 5).
DELIVERED_ETA_CSTAR_DEFAULT = 1.0
# ÖH defter P16B2-07 (D23) — η_c* GİRDİ BİRİMİ SÖZLEŞMESİ, TEK TANIM YERİ.
# ÖLÇÜLDÜ (once.json P16B2-07, taban ef527ae): ``combustion_efficiency``
# uca BAĞLI (``/calculate_liquid`` gövdesi motora ``overrides`` olarak
# geçiyor) ve 97 gönderen koşu 0,97'yi künyesiyle ('user input (combustion
# efficiency)') uyguluyor - kalemin "0,97 gönderene 1,0 uygulanıp 'user
# input' yazılıyor" başlığı bu ağaçta ÇÜRÜK. Kalan GERÇEK kusur birim
# asimetrisiydi: yanıt aynı büyüklüğü KESİR olarak yayımlıyor
# (``combustion_efficiency_unit = 'fraction'``, 0,97) ama girdi bandı
# YÜZDE; yanıttan okunan 0,97'yi geri gönderen çağıran, değerin sessizce
# reddedildiğini (η_c* = 1,0, künye 'not supplied') ancak genel
# ``input_out_of_range`` uyarısından çıkarabiliyordu ve yanıtın hiçbir
# yerinde girdinin biriminin YÜZDE olduğu yazmıyordu. Band artık tek
# yerde tanımlıdır, çıktıda ADIYLA yayımlanır ve kesir biçimli değer
# kendi uyarı koduyla reddedilir (dönüştürülmez - sayı uydurulmaz).
COMBUSTION_EFFICIENCY_INPUT_BAND_PERCENT = (50.0, 100.0)
COMBUSTION_EFFICIENCY_INPUT_UNIT = 'percent'
# Sürtünme / sınır tabaka itki kaybı kesri. hrma.constants içinde TEK
# tanımlıdır ve nozzle_flow_1d ile AYNI değerdir (tipik %0.5-2,
# Sutton & Biblarz 9th ed. Böl. 3.5).
# (NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT hrma.constants'tan import edilir.)

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
# ÖH D27 / OH-D26-07 — TİP TABLOSU DIŞINDA KALAN ENJEKTÖRÜN ORANI.
# ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D27/sivi/a1/once.json``): bu satır
# 0,20'yi SAYI olarak yeniden yazıyordu; oysa aynı sayı chug tasarım
# kuralının TAVSİYE EDİLEN oranıdır ve tanım noktası
# ``acoustic_modes.CHUG_DP_RATIO_RECOMMENDED``tır (yukarıda zaten ithal
# edilmiş). Tip tablosunda olmayan bir enjektör için düşülen değer tam
# olarak "klasik tasarım kuralının tavsiye ettiği oran"dır — ayrı bir
# büyüklük değildir. Sayı DEĞİŞMEDİ (0,20); ikinci tanım noktası kalktı.
INJECTOR_TYPE_DP_FRACTION_DEFAULT = CHUG_DP_RATIO_RECOMMENDED

# Enjektör tipi TANINAN değerler — TEK tanım noktası (ÖH D17 · P3B1-12).
# COOLING_TYPES_RECOGNISED ile AYNI desen: küme yazılmaz, ΔP/Pc tablosundan
# TÜRETİLİR ki iki liste ayrışamasın. ÖLÇÜLDÜ (once.json P3B1-12):
# ``injector_type='banana'`` HTTP 200 alıyor ve yanıtta
# ``injection_system.injector_type = 'banana'`` diye yayımlanıyordu; motor
# ise ΔP oranını sessizce INJECTOR_TYPE_DP_FRACTION_DEFAULT'a düşürüp
# çarpışma/sprey geometrisinin hiçbir dalını çalıştırmıyordu — tanınmayan
# bir tip için tam bir enjektör tasarımı basılıyordu.
# Form seçeneği -> enjektör devre modelinin (hrma.engines.injector_design)
# çözdüğü tip. TEK TANIM: hem calculate_injector_design hem /calculate_liquid
# uç kapısı buradan okur.
#
# 'unlike_impinging' arayüzün (hrma/templates/liquid.html:1049) SUNDUĞU bir
# seçenektir ve eski tabloda YOKTU: sessiz ``.get(..., 'impinging_doublet')``
# ikamesiyle çarpışan-doublet çözümüne düşüyor, üstelik ΔP/Pc oranını da
# tip-bağımsız varsayılandan alıyordu. Modülün ``impinging_doublet``i zaten
# FARKLI akışkanların çarpıştığı doublet'tir, yani eşleme uydurma değil
# adlandırmanın düzeltilmesidir.
INJECTOR_TYPE_CIRCUIT_MODEL = {
    'impinging': 'impinging_doublet',
    'unlike_impinging': 'impinging_doublet',
    'coaxial': 'coax_swirl',
    'showerhead': 'showerhead',
    'pintle': 'pintle',
    'swirl': 'swirl',
}
#: Uç kapısının beyaz listesi — küme YAZILMAZ, yönlendirme tablosundan
#: TÜRETİLİR (COOLING_TYPES_RECOGNISED ile aynı desen).
INJECTOR_TYPES_RECOGNISED = tuple(INJECTOR_TYPE_CIRCUIT_MODEL)

# Sıvı enjektörde chug (düşük frekans) kararlılık eşikleri ΔP/Pc.
# F2b-2 (17 Ağu 2026): bu iki sayı burada YENİDEN TANIMLIYDU (künyesi
# "SP-8089"), aynı çift acoustic_modes'ta da tanımlıydı (künyesi "Sutton +
# SP-194") — aynı sayı, iki künye. Artık merkezî tanımın TAKMA ADIDIR;
# sayı değişmedi, künye hükmü CHUG_THRESHOLD_SOURCE içindedir. Adlar
# korunur (bu dosyanın içinde ve dışında bu adlarla okunuyorlar).
CHUG_DP_PC_MIN_LIQUID = CHUG_DP_RATIO_MINIMUM
CHUG_DP_PC_RECOMMENDED_LIQUID = CHUG_DP_RATIO_RECOMMENDED

# İlk enine (tanjansiyel) mod katsayısı BURADA TANIMLI DEĞİLDİR (F2b-2).
# Eskiden `FIRST_TANGENTIAL_MODE_COEFF = 1.8412` diye elle yazılıydı; merkez
# modül aynı sayıyı J'_1'in ilk sıfırından scipy.special.jnp_zeros ile
# ÜRETİYOR (1,8411837813406593). Yuvarlanmış kopya öldürüldü; _stability_
# assessment kökü acoustic_modes.transverse_root(1, 0)'dan alır. Göç farkı
# ölçüldü ve beyanlı: tests/test_sivi_akustik_gocu.py (manifest tablosu).

# Kısma (throttle) taraması: %40-100 itki bandı (denetim raporu madde 8).
THROTTLE_SCAN_FRACTIONS = (0.40, 0.55, 0.70, 0.85, 1.00)

# Film soğutma girdi bandı (% yakıt debisi). Tarihsel film debileri ana
# debinin %1-10'u mertebesindedir (KU-K1/SP-H1 K14: eski künye "Huzel &
# Huang Ch. 4" idi; SP-125 s. 117 yalnız "tipik bir durumda ≈ %3" der, bant
# vermez — bant kaynaksız mühendislik aralığıdır); üst sınır geniş
# bırakılır, aşırı değer uyarı üretir.
FILM_COOLING_PCT_MAX = 30.0
# Kullanıcı soğutma tipini 'film_cooling' seçtiği hâlde film debisi
# girmediğinde uygulanan ETİKETLİ varsayılan (% yakıt debisi). Literatürde
# yaygın bant %3-10'dur (Sutton & Biblarz 9th ed. Ch. 8; KU-K1/SP-H1 K14:
# SP-125 s. 117 yalnız "tipik bir durumda ≈ %3" der, bant vermez);
# ortası alınır. Bu varsayım çıktıda 'film_cooling_percent_source' ile
# bildirilir — sessizce uygulanmaz. Aksi hâlde 'film cooling' seçimi hiçbir
# sayıyı değiştirmiyordu (film debisi 0 -> film yok).
FILM_COOLING_PCT_DEFAULT = 5.0

# Damlacık ikincil parçalanma (atomizasyon) süresi için boyutsuz süre T*:
#     t_b = T* · d_jet / v_rel · sqrt(rho_l / rho_gas)
# Pilch & Erdman (1987), Int. J. Multiphase Flow 13(6), 741-757; Nicholls
# (1972) — torba/çok modlu parçalanma rejiminde T* ≈ 5. Yanma odasındaki
# karakteristik karışma/atomizasyon zamanı bu ölçekten gelir.
DROPLET_BREAKUP_TIME_CONST = 5.0

# --- τ_c ÇAPRAZI (sıvı + hibrit ORTAK yardımcısı, v2.6.27 parti 31) --------
# Kamara zaman sabitine İKİ bağımsız yol vardır ve ikisi de aynı fiziksel
# süreyi ölçer:
#     tau_c = L*/(c*·Γ²)        (çekirdek: hrma.stability.chamber)
#     tau   = rho_gaz·V_c/mdot  (bu koşunun kendi kalış süresi)
# Cebirsel olarak ÖZDEŞtirler (ṁ = P_c·A_t/c* ve ρ = P_c/(R·T), R·T = (c*Γ)²).
# Eşit çıkmıyorlarsa fark motorun KENDİ ṁ ↔ c* tutarlılığındandır; sıvıda bu
# ölçüm %2,55'lik bir tutarsızlığı yakalamıştı. Alan biçimi tek yerde tanımlı
# olsun ki hibrit ikizi "aynı ada sahip başka bir sözlük" olmasın: ortak metin
# burada, motora ÖZGÜ kalıntı gerekçesi çağrıdan gelir (hibritte debi zinciri
# başkadır — yakıt grenden gelir, ölçüm cümlesi bunu söylemek ZORUNDADIR).
# Bekçiler: tests/test_enjektor_sozlesme_borclari.py (biçim + bant + bit-aynı).
TAU_C_RESIDENCE_COMMON_BASIS = (
    'Two independent routes to the SAME physical time: '
    'tau_c = L*/(c* Gamma^2) and the chamber residence time '
    'rho_gas*V_c/mdot. They are algebraically identical when '
    'mdot = Pc*A_t/c* holds exactly. The residual measured '
    'here is ')

#: Sıvı zincirinin kalıntı gerekçesi.
#
# --- ÖH D22 / P6B4-02 · GEREKÇE YANLIŞTI, ÖLÇÜLDÜ VE DÜZELTİLDİ -----------
# Eski metin şunu söylüyordu: "kalıntı sıvı zincirinin KENDİ ṁ ⟷ c*
# tutarlılığıdır (debi itki/Isp zincirinden gelir, boğulmuş-boğaz
# özdeşliğinden DEĞİL)". ÖLÇÜLDÜ (raw/OH/D22/sivi/a1/once_p6b402.json,
# dört koşu) ve bu cümle YANLIŞ çıktı: debi tam olarak boğulmuş-boğaz
# özdeşliğinden geliyor, üstelik bire bir:
#     mdot_total / (Pc*A_t/c*) - 1  =  -2,000000000%  (C_D = 0,98'de)
#                                   =  -5,000000000%  (C_D = 0,95'te)
# yani ṁ = Pc·A_t·C_D/c*, kalıntısı 1e-14 mertebesinde. Kalıntının
# GERÇEK kaynağı ölçülerek ikiye ayrıldı ve çarpımları yayımlanan oranı
# 16 anlamlı hanede yeniden üretiyor:
#     oran = (1/C_D) · (c*·Γ)²/(R·T)
#   1) 1/C_D           — boğaz akış katsayısı (τ_c'nin tanımı C_D'siz
#                        ṁ = Pc·A_t/c* varsayar);
#   2) (c*Γ)²/(R·T)    — R·T özdeşliğinin TÜKETİCİDE kırılması: ρ_gaz
#                        CEA'nın (R_u/mw)·T_c'sinden kuruluyor, τ_c ise
#                        c*'tan; ikisi eşit olmak ZORUNDA ama ölçülen
#                        sapma −%1,60 / −%2,11 / +%0,33 / +%0,31.
# Metin artık bu iki terimi ADIYLA söylüyor ve sayıları
# ``residual_decomposition`` alanında makine-okur olarak yayımlanıyor.
LIQUID_TAU_C_RESIDUAL = (
    'NOT an unexplained inconsistency: it factorises exactly into two '
    'named terms, published in residual_decomposition. (1) The throat '
    'discharge coefficient: this run solves mdot = Pc*A_t*C_D/c_star '
    '(measured to 1e-14), while the tau_c definition assumes the C_D-free '
    'choked identity mdot = Pc*A_t/c_star, so the ratio carries a factor '
    '1/C_D. (2) The R*T identity break at the CONSUMER: the residence time '
    'builds rho_gas from CEA (R_universal/mw)*T_c, whereas tau_c builds the '
    'same quantity from c* through R*T = (c*Gamma)^2. The two must agree and '
    'do not. Their product reproduces the published ratio to 16 significant '
    'figures; nothing is silently absorbed.')

#: ``residual_decomposition`` alanının künyesi (tek tanım yeri).
TAU_C_RESIDUAL_DECOMPOSITION_BASIS = (
    'ratio = discharge_coefficient_term * rt_identity_term, where '
    'discharge_coefficient_term = 1/C_D and rt_identity_term = '
    '(c*Gamma)^2/(R*T). unexplained_pct is the leftover after both named '
    'terms are removed; it is the number that would have to be explained by '
    'anything else, and it is published even when it is zero.')


def tau_c_vs_residence_time_field(tau_c_s, residence_time_s, residual_source,
                                  residual_terms=None):
    """τ_c ↔ kalış süresi çaprazının YAYIMLANAN alan biçimi.

    Args:
        tau_c_s: çekirdeğin ``chamber_time_constant`` çıktısındaki tau_c [s].
        residence_time_s: bu koşunun kalış süresi ρ_gaz·V_c/ṁ [s].
        residual_source: kalıntının HANGİ zincirden geldiğini söyleyen cümle;
            motor tipine özgüdür ve uydurulmaz (sıvı: itki/Isp zinciri,
            hibrit: ox debisi + gerileme kaynaklı yakıt debisi).

    Returns:
        dict — ``tau_c_s``, ``residence_time_s``, ``ratio``, ``interpretation``
        ve (``residual_terms`` verilirse) ``residual_decomposition``.
    """
    alan = {
        'tau_c_s': tau_c_s,
        'residence_time_s': float(residence_time_s),
        'ratio': float(residence_time_s) / tau_c_s,
        'interpretation': TAU_C_RESIDENCE_COMMON_BASIS + residual_source,
    }
    if residual_terms:
        alan['residual_decomposition'] = dict(residual_terms)
    return alan


# Motor arayüz çevrim adı -> cycle_power_balance çözücü adı eşlemesi.
CYCLE_SOLVER_NAME = {
    'pressure_fed': 'pressure_fed',
    'gas_generator': 'gas_generator',
    'tap_off': 'tap_off',
    'staged_combustion': 'staged_combustion',
    'expander': 'expander',
    'full_flow_staged': 'full_flow_staged_combustion',
}

# --- ÖH D27 / OH-D26-12 — "TANK ENJEKTÖRÜ BESLER Mİ?" TEK KAYNAK ---------
#
# ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D27/sivi/a1/once.json``, OH-D26-12):
# ``/calculate_liquid``in tank basıncı kapısı ``tank_pressure``ı ENJEKTÖRÜ
# BESLEYEN basınç sayıyor ve hazne basıncına göre yargılıyordu. Bu önerme
# YALNIZ basınç beslemeli çevrimde doğrudur. Turbopompalı çevrimde enjektörü
# POMPA besler; tank yalnız pompanın NPSH'ı için basınçlanır ve çözücü onu
# NPSH'ten kendisi boyutlandırır (``_tank_pressure_bar`` -> turbopompa
# dalı). Ölçülen çelişki (10 kN RP-1/LOX, Pc = 30 bar, çevrim belirtilmemiş
# = turbopompalı):
#   tank_pressure =   3 bar -> HTTP 400 "must be greater than chamber
#                              pressure (30.0 bar)"  (yanlış önerme)
#   tank_pressure yok       -> HTTP 200, AYNI yanıt
#                              detailed_feed_system.tank_pressure_bar =
#                              2,768 bar YAYIMLIYOR (uç KENDİ yayımladığı
#                              sayıyı öbür gövdede reddediyor)
#   tank_pressure = 200 bar -> HTTP 200, hiçbir sayıyı oynatmıyor
#                              (``inputs_not_used`` beyanı var — beyan
#                              çözüm değildir, sessiz yutma sürüyordu)
#
# Çevrim ayrımı burada TEK KEZ tanımlanır; uç katmanı bu yardımcıyı çağırır
# ki iki yerde iki farklı "hangi çevrim turbopompalı" kuralı doğmasın.
# Varsayılan FAIL-CLOSED yönündedir: çevrim adı verilmemiş ya da tanınmayan
# bir ad verilmişse motor kurucusu da turbopompaya düşer
# (``feed_system_type='turbopump'``), bu yardımcı da öyle der.
PRESSURE_FED_CYCLE_NAME = 'pressure_fed'

#: Türbin kartının girdi alanları. V3 taban-a (14 Eki; KAB devri, kabul
#: brifi N7): basınç beslemeli çevrimde türbin YOKTUR; bu alanlar o çevrimde
#: DEĞERLENDİRİLMEZ (türbin basınç oranı karşılaştırması yapılmaz) ve
#: gönderildilerse ``inputs_not_used`` ile ADIYLA beyan edilir. Ölçülen
#: kusur: form varsayılanları (150 bar / 4) türbinsiz motora
#: 'warn.liquid.turbine_pr_inconsistent' bastırıyordu
#: (docs/kabul/kanit_2026-10-14/taze.json ek_sivi_eps5).
TURBINE_INPUT_FIELDS = ('turbine_inlet_pressure', 'turbine_expansion_ratio')
#: Bu beyanın ``inputs_not_used`` gerekçe adı.
TURBINE_INPUT_UNUSED_REASON = 'no_turbine_in_this_cycle'
#: ÖH A2 sivi-sogutma · 7. tur (TBA devri): turbopompanın İKİ girdisi daha
#: basınç beslemeli çevrimde okunmuyor ama API'den gönderilirse sessizce
#: yutuluyordu. ÖLÇÜLDÜ (docs/scofield/raw/OH/A2/sivi-sogutma/a1/sart7/
#: olcum/k6_once.json + k6_once_regen.json; KAB ek_sivi_eps5 gövdesi,
#: ablatif ve rejeneratif): pompa verimi 75 / 50 / 40 %, gaz üreteci
#: sıcaklığı 1000 / 1500 / 2000 K ve ikisinin gövdeden düşürülmesi beyan
#: kanalları dışında 0 yaprak oynatıyor; ``inputs_not_used`` ikisini de
#: anmıyordu. Türbin alanlarıyla AYNI beyan deseni (``inputs_not_used``),
#: ayrı gerekçe adı: bu çevrimde turbopompanın kendisi (pompa da türbin de)
#: yoktur.
TURBOPUMP_INPUT_FIELDS = ('turbopump_efficiency', 'generator_gas_temp')
#: Turbopompa alanları beyanının ``inputs_not_used`` gerekçe adı.
TURBOPUMP_INPUT_UNUSED_REASON = 'no_turbopump_in_this_cycle'


def _pump_ns_band_status(rpm, q_m3_s, head_m):
    """Pompanın ÖZGÜL DEVRİ radyal çark bandının neresinde? (ÖH D27)

    Bandın kendisi ``turbopump_sizing`` sabitlerinden okunur; burada sayı
    YAZILMAZ. Ölçülemeyen girdi için hüküm verilmez: ``None`` döner ve kart
    alanı boş kalır (uydurma sınıf yayımlanmaz).
    """
    try:
        if not (q_m3_s > 0.0 and head_m > 0.0 and rpm > 0.0):
            return None
        ns = rpm * m3s_to_gpm(q_m3_s) ** 0.5 / m_to_ft(head_m) ** 0.75
    except Exception:                                      # pragma: no cover
        return None
    if not np.isfinite(ns):                                # pragma: no cover
        return None
    if ns < NS_CENTRIFUGAL_MIN_US:
        return 'below_centrifugal_band'
    if ns > NS_CENTRIFUGAL_MAX_US:
        return 'above_centrifugal_band'
    return 'in_centrifugal_band'


def tank_feeds_injector(request_data):
    """Bu istekte tankın kendisi enjektörü besliyor mu? (True/False)

    Motorun kurucusundaki kuralın (``_override_choice('engine_cycle', ...)``
    -> ``feed_system_type``) UÇ KATMANI için okunabilir tek kopyasıdır.
    Sözlük dışı girdi, boş değer ve tanınmayan çevrim adı için False döner:
    turbopompa varsayımı, tank basıncını enjektör beslemesi saymamak
    demektir ve yanlış hüküm vermemek bakımından güvenli taraftır.
    """
    if not isinstance(request_data, dict):
        return False
    ham = request_data.get('engine_cycle')
    if not isinstance(ham, str):
        return False
    ad = ham.strip().lower()
    if ad not in CYCLE_SOLVER_NAME:
        return False
    return ad == PRESSURE_FED_CYCLE_NAME

# Rejeneratif ceket liner (sıcak cidar) kalınlığı [m] — 1B istasyon-marşlı
# süperkritik çözüm için. Frezeli kanallı bakır/inconel liner pratiği
# 0.5-2 mm (Huzel & Huang, "Modern Engineering for Design of
# Liquid-Propellant Rocket Engines", AIAA 1992, Ch. 4 — KU-K1/SP-H1 K3/K13:
# bu baskı okunmadı, sayfa doğrulanmadı; NASA SP-125 (1967) ayrı kitaptır ve
# bu bandı içermez). Yapısal dış cidar ayrıdır.
REGEN_LINER_THICKNESS_M = 1.0e-3

# Rejeneratif ceketin kapladığı azami genişleme oranı: ana yanma odası
# ceketi tipik olarak ε≈5-6'ya kadar frezeli kanallıdır (RS-25 ana yanma
# odası ε≈5-6, ötesi tüp demeti/ışınımsal bölge — Sutton & Biblarz 9th ed.
# Ch. 8 rejeneratif ceket anlatımı). Lüle bunun ötesine uzuyorsa o bölgenin
# soğutması bu modelde ÇÖZÜLMEZ ve çıktıda açıkça söylenir.
REGEN_JACKET_EPS_MAX = 6.0

# Film soğutmada film sıvısının ısı alabileceği üst sıcaklık, sıcak cidar
# hedef sıcaklığıyla sınırlanır (film cidarı korurken cidar hedefinden
# sıcak olamaz). Enerji dengesi modeli: film debisi = yutulan ısı / birim
# kütle ısı kapasitesi (KU-K1/SP-H1 K15: SP-125 Eş. 4-33, s. 115 bir film
# VERİMİ η_c (%30-70) içerir, bu modelde YOK — o fark ÖNEMLİ kalemi B3'tür); entalpiler CoolProp gerçek-gaz
# değerleridir (CH4/H2), RP-1 için duyulur ısı (cp·ΔT) alt sınırıdır.
FILM_COOLANT_CP_FALLBACK_J_KGK = {'rp1': 2090.0}  # MIL-DTL-25576 sıvı cp

# ÖH A2 sivi-sogutma · uc-kapi devri ``fuel_heat_capacity`` — REJENERATİF
# CEKET toplu ΔT hesabının soğutucu cp tablosu TEK TANIM. Eskiden bu sayılar
# ``calculate_cooling_requirements`` içinde YEREL if/elif satırlarıydı; uç
# kapısı (A1a uc-kapi) formun 2090 ön-dolgusunu kanonik değerle
# karşılaştıramıyordu çünkü kanonik değer motor durumunda hiç tutulmuyordu.
# Değerler DEĞİŞMEDİ (bit-aynı); değişen, kurucuda çözülüp künyesiyle
# yayımlanmalarıdır (cooling_system.coolant_heat_capacity[_source]).
# Metan/LH2 rejeneratifte süperkritik istasyon marşı kurulursa cp CoolProp
# (T,P) bağımlıdır ve bu tablo toplu ΔT dışında kullanılmaz.
COOLANT_CP_TABLE_J_KGK = {'rp1': 2090.0, 'lh2': 14300.0, 'methane': 3480.0}
COOLANT_CP_FALLBACK_J_KGK = 2000.0
#: Satır künyeleri (ölçüm: docs/scofield/raw/OH/A2/sivi-sogutma/a1/rapor.md
#: — CoolProp 6.8.0 karşılaştırması). LH2 satırı sıvının DEĞİL 300 K gaz
#: H2'nin cp'sidir; sayıyı değiştirmek yayımlanan ΔT'yi değiştirir (ÖNEMLİ)
#: -> bu kulvarda DEĞİŞTİRİLMEDİ, künye gerçeği söyler (DEVİR).
COOLANT_CP_TABLE_BASIS = {
    'rp1': ('propellant table value 2090 J/kg.K for liquid RP-1 (the film '
            'table cites MIL-DTL-25576; that attribution is NOT verified '
            'in this lane)'),
    'lh2': ('propellant table value 14300 J/kg.K: this equals gaseous '
            'hydrogen near 300 K (CoolProp 14313 J/kg.K), NOT liquid '
            'para-hydrogen at its normal boiling point (CoolProp 9729 '
            'J/kg.K). Used only by the bulk jacket temperature rise when '
            'the supercritical station march is not run; flagged, not '
            'changed'),
    'methane': ('propellant table value 3480 J/kg.K: saturated liquid '
                'methane at its normal boiling point (CoolProp 3481 '
                'J/kg.K)'),
}
COOLANT_CP_FALLBACK_BASIS = (
    'ASSUMED generic value 2000 J/kg.K: this fuel has no entry in the '
    'coolant heat-capacity table and no fuel_heat_capacity was supplied; '
    'the number has no source')

# CoolProp akışkan adları (film/pressurant entalpi hesapları için).
COOLPROP_FLUID_NAME = {'methane': 'Methane', 'lh2': 'ParaHydrogen',
                       'lox': 'Oxygen'}

# Yanma süresi [s] — ÖH D36 / LU-1 (Cowork, Berke onaylı, ÖNEMLİ):
# kullanıcı max_burn_duration vermezse ARTIK VARSAYIM YOK. Eski durum
# ÖLÇÜLDÜ (raw/OH/D36/onemli2-sivi/a1/once.json, örnek proje, süre boş):
# yanıt ``burn_time = 300`` + ``'assumed 300 s burn'`` yayımlıyor, bu
# sayıdan ``propellant_mass_kg`` (2756 kg), tank kartı (3170 kg yüklü) ve
# 3515 baytlık bir .eng dosyası türetiliyordu; arayüz ise alanı 400 ile ön
# dolduruyor ve boş bırakılsa bile ``|| 400`` ile gönderiyordu — yani
# "kullanıcı girdisi" künyesi hiç girilmemiş bir sayıya basılıyordu.
# Kural (fail-closed): süre yoksa hesaba GİRMEZ ve bu ADIYLA beyan edilir
# (``burn_time_source = 'not_supplied'``); ``burn_time``, ``propellant_mass_kg``
# ve süreye bağlı tank/basınçlandırma blokları YAYIMLANMAZ. Varsayılan
# yalnız öğretici kipte (``use_tutorial_defaults``) ve kendi künyesiyle
# uygulanır; uç bunu ``defaults_applied`` listesine yazar.
BURN_TIME_DEFAULT_S = 300.0
BURN_TIME_MIN_S, BURN_TIME_MAX_S = 0.1, 100000.0
#: ``burn_time_source`` künyeleri — TEK tanım noktası (arayüz ve bekçi bu
#: dizeleri okur; burada değişirse tests/test_d36_sivi_a1.py kırılır).
BURN_TIME_SOURCE_USER = 'user input (max burn duration)'
BURN_TIME_SOURCE_TUTORIAL = ('tutorial default (%g s, use_tutorial_defaults)'
                             % BURN_TIME_DEFAULT_S)
BURN_TIME_SOURCE_NOT_SUPPLIED = 'not_supplied'
#: Süre verilmediğinde süreye bağlı her bloğun ortak gerekçe cümlesi.
BURN_TIME_NOT_SUPPLIED_REASON = (
    'the burn time was not supplied (max_burn_duration is empty) and no '
    'default is assumed, so nothing that depends on it was computed: '
    'burn_time, total_impulse, propellant_mass_kg, the propellant tank '
    'card, the feed-system tank volumes and the autogenous pressurant '
    'budget. Fill "Maximum Burn Duration" (or send use_tutorial_defaults '
    'for the declared tutorial value) to get them.')


def _flag_true(value):
    """``use_tutorial_defaults`` bayrağı — yalnız AÇIK doğru değerler.

    Uç (app.py ``_form_bool_kapisi``) bayrağı zaten adlı 4xx ile okuyup
    gerçek ``bool``a çevirir; motor doğrudan çağrıldığında da ``"false"``
    / ``"0"`` gibi dizeler öğretici kipi AÇMAMALI (P7B2-07'nin dersi).
    """
    if value is True:
        return True
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')

# Besleme hattı: Darcy-Weisbach + yerel kayıp katsayıları.
# K değerleri: Crane TP-410 / White "Fluid Mechanics" 7th ed. Table 6.5.
#
# v2.6.26 KUSUR (ÇİFT TANIM, kapatıldı): bu sabit basınç düşümüne giriyordu
# (``_feed_line_pressure_drops``), ama ``_initialize_feed_system`` ekrana
# çıkan hat boyunu AYRI bir ``2.5`` literaliyle yazıyordu. İkisi bugün aynı
# sayıydı; biri değişse gösterilen boru boyu ile basınç düşümünün varsaydığı
# boy SESSİZCE ayrışırdı. Artık tek tanım yeri burasıdır.
FEED_LINE_LENGTH_DEFAULT_M = 2.5     # hat uzunluğu (TEK tanım yeri)
FEED_LINE_LENGTH_BASIS = (
    'assumed engine-to-tank run length; a layout assumption, NOT solved from '
    'a vehicle geometry (HRMA has no stage layout model). Single definition '
    'point FEED_LINE_LENGTH_DEFAULT_M - the same length also drives the '
    'Darcy-Weisbach line pressure drop, so the displayed length and the '
    'pressure drop cannot disagree')
FEED_LINE_ROUGHNESS_M = 4.5e-5       # ticari çelik boru (White Table 6.1)
FEED_K_TANK_OUTLET = 0.50            # keskin kenarlı tank çıkışı
FEED_K_MAIN_VALVE = 0.15             # tam açık küresel/kelebek ana vana
FEED_K_FILTER = 10.0                 # hat süzgeci (temiz eleman, tahmin)
FEED_K_ELBOW = 0.30                  # 90 derece uzun yarıçaplı dirsek
FEED_ELBOW_COUNT = 4
# --- B5 (v2.6.27): EMME / BASMA ayrımı -------------------------------------
# NPSH'tan yalnız pompa GİRİŞİNE kadarki (emme tarafı) kayıp düşülür. Emme
# kalemleri: tank çıkışı (K) + hat süzgeci (K, pompayı korumak için emmede)
# + kısa düz emme borusu. ANA VANA pompanın BASMASINDADIR (tam açık ana
# kesme vanası enjektör öncesi hat üstünde; C2 vana bloğu onu hat SONUNDA
# boyutlandırıyor) ve dirsekli uzun koşu da basma tarafına aittir: emme
# borusu kavitasyonu beslememek için kısa ve DÜZ tutulur (Huzel & Huang,
# NASA SP-125 Böl. IX §9.5 kanallar — KU-K1/SP-H1 K34: eski künye "Böl. 8
# itici boruları" idi, Böl. VIII tanklardır; Böl. 6 pompa emme performansı). Emme boyu, toplam
# FEED_LINE_LENGTH_DEFAULT_M = 2,5 m koşusunun bir PAYI olarak beyan edilir
# — yerleşim varsayımıdır, araç geometrisinden ÇÖZÜLMEZ. Eski kod hattın
# TAMAMINI (ana vana + 2,5 m + 4 dirsek) emmeden düşüyordu; ölçülen sonuç
# 25 kN örneğinde yakıt pompası NPSH_a = -14,4 m idi (2026-08-14 teşhisi).
FEED_SUCTION_LINE_LENGTH_M = 0.5     # tank çıkışı -> pompa girişi düz boru
FEED_SUCTION_LINE_BASIS = (
    'suction line length: an assumed short straight tank-to-pump run '
    f'({FEED_SUCTION_LINE_LENGTH_M:g} m share of the '
    f'{FEED_LINE_LENGTH_DEFAULT_M:g} m engine-to-tank layout run) - pump '
    'suction ducts are kept short and straight to protect NPSH (Huzel & '
    'Huang, NASA SP-125, Ch. IX Sec. 9.5 ducts). The main valve and the '
    'elbowed remainder of the run are DISCHARGE-side items and are not '
    'charged against NPSH.')
FEED_LINE_TARGET_VELOCITY_MS = 5.0   # hat çapı boyutlandırma hedefi (3-8 m/s)
# Sıvı besleme hattı için tavsiye edilen ÜST hız [m/s]. KU-K1/SP-H1 K33: eski
# künye "Huzel & Huang Böl. 7; NASA SP-125" idi; 3-8 m/s bandı SP-125'te YOK
# (SP-125 yüksek itkili motor kanallarında >100 ft/s eğilimini ve 20,2 m/s
# örnek basma kanalını verir; SP-H1 notu s. 287, s. 300 — bu turda yeniden
# doğrulanmadı). Bant kaynaksız düşük hızlı hat tercihidir; değer DEĞİŞMEDİ
# (emme/basma ayrımı B5 kalemi). Hat çapı standart boru ölçüsüne yuvarlandığı için gerçek hız
# hedeften sapar; besleme sistemi debi marjı bu tavana göre raporlanır.
FEED_LINE_MAX_VELOCITY_MS = 8.0
# Bandın ALT ucu [m/s]. Aynı kaynaksız bant (SP-125'te yok, yukarıya bak):
# bandın altına düşen hat gereksiz ağır ve hantaldır ve
# ÖH defter P3B3-04'te ölçülen 'sessizce band dışı' vakalarının yarısı
# bu uçtaydı (5 kN oksitleyici 2,21 m/s). Sayı İKİ YERDE yazılmaz:
# hem çap seçimi hem uyarı eşiği bu sabitten okur.
FEED_LINE_MIN_VELOCITY_MS = 3.0
# ÖH defter P3B3-01/-02: çevrim çözümünden gelen kartların künyesi TEK
# metindir; iki blok (feed_system.turbopump ve detailed_feed_system)
# aynı sözü söyler, yoksa 'iki kart iki kaynak' kusuru geri döner.
CYCLE_CARD_SOURCE = 'cycle power balance solution'
# P3B3-05: reddedilen girdinin künyesi — 'user input' DEMEZ ve neden
# reddedildiğini söyler (SAFETY_FACTOR_SOURCE_REJECTED deseninin eşi).
# ---------------------------------------------------------------------------
# ÖH defter P3B3-06: KRİYOJENİK TANK MALZEMESİ TARAMASI
#
# Ölçüldü: LH2 yakıt tankı ``'steel'`` (Carbon steel, A36 sınıfı) olarak
# boyutlanıp status=PASS alıyordu; aynı fonksiyonun kendi yorumu ise
# "pratikte paslanmaz seçilir / Stainless Steel 316L" diyordu. Seçim üstelik
# TERSİNE dönmüştü: 20 K'de depolanan LH2'ye BCC karbon çelik, 300 K'deki
# RP-1'e kriyojenikte uygun alüminyum.
#
# Tarama ölçütü kristal yapıdır (ASME BPVC Sec. VIII Div. 1 UHA-51 muafiyet
# mantığı; NASA SP-8040; Huzel & Huang Böl. 8): YMK (FCC) metaller —
# ostenitik paslanmazlar, alüminyum alaşımları, bakır, Inconel — kriyojenik
# sıcaklıklarda tokluklarını korur ve darbe testi muafiyeti alır; HMK (BCC)
# ferritik/karbon çeliklerin sünek-gevrek geçiş sıcaklığı (DBTT) oda
# sıcaklığının yakınındadır ve kriyojenik tankta kullanılmaz.
#
# Bu, tam bir kırılma mekaniği hükmü DEĞİLDİR (HRMA'da tank ısıl modeli ve
# darbe/CTOD verisi yok) — bir TARAMADIR ve künyesi bunu söyler.
# ÖH D17 · P3B3-06 ŞART (Fable-D15) + OH-D16-08 — TEK KAYNAK.
#
# ÖLÇÜLDÜ (once.json, P3B3-06.kume_dbtt_celiskisi): bu küme ELLE YAZILMIŞ
# İKİNCİ bir listeydi ve deponun tek tanımıyla ÇELİŞİYORDU. ``ss_17_4ph``
# martenzitik çökelme sertleşmeli bir çeliktir; ``materials_db.DBTT_SENSITIVE``
# (P9B4-08) onu DBTT-duyarlı sayar ve ``analysis/pressure_vessel`` aynı
# malzeme için "brittle fracture risk" der — ama buradaki liste onu
# kriyojenik tank için UYGUN sayıp aynı koşumda 'pass' veriyordu. Aynı
# malzeme, aynı depoda, iki karşıt güvenlik hükmü.
#
# Küme artık YAZILMAZ, TÜRETİLİR: uygunluk hükmünü veren tek yer
# ``materials_db.is_dbtt_sensitive()``tir (kanonik ada çözer, takma adla
# çağrılınca da doğru cevap verir). Kümenin kendisi yalnız künye/echo
# amaçlıdır; hükmü ``_tank_cryo_screening`` doğrudan o fonksiyondan alır.
def _tank_cryo_suitable_from_db():
    """materials_db'den TÜRETİLEN uygun malzeme kümesi (tek kaynak)."""
    from hrma.data.materials_db import MATERIALS, is_dbtt_sensitive
    return frozenset(ad for ad in MATERIALS
                     if is_dbtt_sensitive(ad) is False)


# Adın söylediği şey TAM OLARAK budur: "DBTT gerekçesiyle ELENMEYENLER".
# Bir malzemenin bu kümede olması onu kriyojenik tank için UYGUN yapmaz —
# yalnız düşük sıcaklık tokluğu gerekçesiyle dışlanmadığını söyler (künye
# TANK_CRYO_SCREENING_BASIS bunu ayrıca yazar). Türetim kümeye metalik
# olmayan kayıtları da sokar (graphite, carbon_carbon, ablative,
# brass_c360, magnesium_az31b): onlar da DBTT ile elenmez, ama tank
# malzemesi seçimi bu taramadan ibaret değildir.
TANK_CRYO_NOT_DBTT_EXCLUDED = _tank_cryo_suitable_from_db()
#: Eski ad — D15 bekçilerinin ithal ettiği isim korunur (aynı nesne).
TANK_CRYO_SUITABLE_MATERIALS = TANK_CRYO_NOT_DBTT_EXCLUDED
# Arayüzün sunduğu kriyojenik iticiler (normal kaynama noktası << 273 K).
CRYOGENIC_PROPELLANTS = frozenset({'lh2', 'lox', 'methane'})
TANK_CRYO_SCREENING_BASIS = (
    'ductile-to-brittle transition (DBTT) screening, resolved through the '
    'single repository definition materials_db.is_dbtt_sensitive() (ASME '
    'BPVC Sec. VIII Div. 1 UHA-51 impact-test exemption logic; NASA '
    'SP-8040; Huzel & Huang Ch. 8): body-centred-cubic ferritic and '
    'martensitic steels and the bcc refractory metals have a '
    'ductile-to-brittle transition near or above cryogenic temperature and '
    'are excluded. Face-centred-cubic alloys (austenitic stainless, '
    'aluminium, copper, nickel alloys) and the hexagonal close-packed '
    'titanium alloys, which have no sharp transition, are not excluded on '
    'this ground. This is a SCREEN, not a fracture-mechanics verdict: HRMA '
    'has no tank thermal model and no impact/CTOD data, so a passing screen '
    'still requires a separate toughness qualification.')
# LH2 tankı: fonksiyonun kendi beyanının ("Stainless Steel 316L") bağlandığı
# kayıt. materials_db 316L'yi ayrı tutmaz; tavlanmış 316 kaydı kullanılır ve
# bu ikame künyede ADIYLA söylenir.
TANK_LH2_MATERIAL_KEY = 'ss_316'
TANK_LH2_MATERIAL_BASIS = (
    'austenitic stainless steel for the liquid-hydrogen tank: the module '
    'declared "Stainless Steel 316L" but sized the wall with a generic '
    'CARBON steel record (A36 class), which is exactly the material a '
    'cryogenic tank must not use. materials_db carries no separate 316L '
    'entry, so the annealed 316 record is used and the substitution is named '
    'here rather than hidden.')

TURBINE_INLET_TEMP_SOURCE_REJECTED = (
    'user input REJECTED (out of the accepted range or not a number); '
    'the cycle solver used its own cycle-specific default and the entered '
    'value changed nothing')
# Standart boru merdiveni [m]: çap seçimi ve künye AYNI listeden okur
# (eskiden gövde içinde satır içi literaldi).
FEED_LINE_STANDARD_SIZES_M = (0.025, 0.05, 0.075, 0.1, 0.15, 0.2,
                              0.25, 0.3)
# --- ÖH D20 / OH-D18-03 ----------------------------------------------------
# Besleme hattı modeli TEK KOLDU: merdivenin en büyük basamağı (300 mm) bile
# banda yetmediğinde o basamak seçilip hız ihlali beyanla geçiliyordu.
# Ölçüldü (once.json OH-D18-03-F1tam, 6770 kN rp1/lox): iki hat da 300 mm'e
# dayanıyor, hızlar 12,73 (yakıt) ve 20,63 m/s (oksitleyici) — 3-8 bandının
# 1,6 ve 2,6 katı — ve tank basıncı 33,56 bara çıkıyor. Gerçek F-1 sınıfı
# motorlarda bu akış ÇOKLU KOL ile taşınır. Kol sayısı artık bir tasarım
# ÇIKTISIDIR: bandı sağlayan en küçük paralel kol sayısı çözülür. Üst sınır
# bir tasarım seçimidir (tek motorda makul kol sayısı), ölçülmüş bir sınır
# değildir ve künyede böyle yazar.
FEED_LINE_MAX_PARALLEL = 8

# ---------------------------------------------------------------------------
# Besleme sistemi TOPOLOJİSİ (v2.6.26)
#
# Aşağıdaki bileşen sayıları eskiden gövde içinde satır içi literaldi ve
# "tasarım sonucu" gibi sunuluyordu. İkiye ayrıldılar:
#
#   1. TOPOLOJİK olanlar — iki itici devresi, iki gimbal ekseni ve ikili
#      yedeklilik seçiminden ARİTMETİK OLARAK çıkarlar. Bunlar burada
#      adlandırılmış mimari sabitlerden hesaplanır ve beyanla yayımlanır.
#   2. HİÇBİR mimariden türemeyenler (basınç/sıcaklık/debi sensörü sayısı,
#      çek vana sayısı, basınçlandırıcı şişe sayısı) — HRMA'da P&ID, ölçüm
#      doğruluğu gereksinimi veya güvenilirlik hedefi MODELİ YOKTUR. Bunlara
#      "mimari varsayımı" demek, ortada olmayan bir mimariyi beyan etmek
#      olurdu; yanlış beyan beyansızlıktan kötüdür. Onlar None + NOT_MODELLED
#      olarak yayımlanır (katı motorda kurulan desen).
PROPELLANT_CIRCUIT_COUNT = 2         # oksitleyici + yakıt devresi
GIMBAL_AXIS_COUNT = 2                # yunuslama + sapma
CONTROL_REDUNDANCY = 2               # ikili yedekli (aktif + yedek)


def _feed_topology_basis(alan_adi, tureme):
    """Topolojik bileşen sayısı için beyan metni.

    Metin, alanın ADINDAKİ sözcükleri geçirmek ZORUNDADIR: sınıflandırıcı
    (``tools/sabit_siniflandirma.py::_kardes_beyan_var``) blok beyanlarını
    jeton eşleşmesiyle kabul ediyor ve "havada" duran genel bir cümle bir
    yaprağı aklamamalı. Bu yüzden tek bir ortak metin yerine alan başına
    metin üretilir.
    """
    return (f'{alan_adi.replace("_", " ")}: {tureme} - a topological '
            'consequence of the declared architecture, NOT a sized quantity: '
            'no valve flow coefficient, actuator torque or reliability '
            'allocation is solved anywhere in HRMA')


# --- Hipergolluk (P3B1-02, ÖH D15) -----------------------------------------
# Ölçüldü (once.json): kod beyaz liste mantığındaydı — torch_igniter YALNIZ
# (rp1,lox) ve (methane,lox), kalan HER çift 'hypergolic'. Arayüzün sunduğu
# 10 çiftin 8'i 'hypergolic' hükmü alıyordu; oysa gerçekten hipergolik olan
# yalnız 2'si. LH2/LOX, MMH/LOX, UDMH/LOX, RP-1/N2O4, METHANE/N2O4
# hipergolik DEĞİLDİR: hepsi harici bir ateşleme kaynağı ister. Yön
# tehlikeli — hipergolik sanılan motora ateşleyici konmaz, yanmamış itici
# birikir ve sert ateşleme/patlama olur.
#
# Hipergolluk bir KİMYA olgusudur ve çiftin kendisine bağlıdır: amin bazlı
# yakıtlar (hidrazin, MMH, UDMH, Aerozine-50) nitrojen tetroksit / kırmızı
# dumanlı nitrik asit ile temasta kendiliğinden tutuşur (Sutton & Biblarz,
# "Rocket Propulsion Elements" 9. baskı, Böl. 7.3; Huzel & Huang, NASA SP-125
# Böl. I §1.4, s. 18-19 — KU-K1/SP-H1 K46: eski künye "Böl. 2").
# Sıvı oksijen bu yakıtların hiçbiriyle hipergolik değildir.
LIQUID_HYPERGOLIC_PAIRS = frozenset({
    ('mmh', 'n2o4'), ('udmh', 'n2o4'), ('hydrazine', 'n2o4'),
    ('aerozine50', 'n2o4'),
    ('mmh', 'rfna'), ('udmh', 'rfna'), ('hydrazine', 'rfna'),
    ('mmh', 'irfna'), ('udmh', 'irfna'), ('hydrazine', 'irfna'),
    ('mmh', 'mon3'), ('udmh', 'mon3'), ('hydrazine', 'mon3'),
})
LIQUID_HYPERGOLIC_BASIS = (
    'hypergolicity is a property of the propellant pair chemistry (amine '
    'fuels - hydrazine, MMH, UDMH, Aerozine-50 - ignite on contact with '
    'nitrogen tetroxide and nitric-acid oxidisers): Sutton & Biblarz, '
    '"Rocket Propulsion Elements" 9th ed. Ch. 7.3; Huzel & Huang, NASA '
    'SP-125 Ch. I Sec. 1.4 (pp. 18-19). '
    'Liquid oxygen is NOT hypergolic with any of these fuels.')
# Hipergolik OLMAYAN çiftte hangi ateşleyici donanımının seçileceği
# (kıvılcım, meşale, piroteknik, TEA-TEB slug) HRMA'da MODELLENMEZ: bu bir
# ateşleme enerjisi / gecikme / güvenilirlik hesabı ister ve modülde böyle
# bir hesap yok. Beslemedeki sensör alanlarının (iki satır aşağıda) izlediği
# dürüstlük sözleşmesi burada da uygulanır: alan null döner, durumu ve
# gerekçesi yanında yayımlanır.
LIQUID_IGNITER_STATUS = 'NOT_MODELLED'
LIQUID_IGNITER_BASIS = (
    'not selected: this pair is not hypergolic, so an ignition source is '
    'required, but HRMA models no ignition energy, ignition delay or '
    'igniter reliability and therefore cannot choose the hardware (spark, '
    'torch, pyrotechnic or TEA-TEB slug). The previous value was a two-entry '
    'whitelist that labelled every other pair "hypergolic" - 6 of the 10 '
    'pairs the interface offers, LH2/LOX included - which is the unsafe '
    'direction, because a pair believed hypergolic is flown without an '
    'igniter.')

FEED_INSTRUMENTATION_STATUS = 'NOT_MODELLED'
FEED_INSTRUMENTATION_BASIS = (
    'not calculated: HRMA has no P&ID, no measurement-accuracy requirement '
    'and no reliability allocation, so a sensor count cannot be derived. The '
    'previous values (8 pressure, 6 temperature, 4 flow sensors, 6 check '
    'valves, 2 pressurant bottles) were fixed literals - identical for a '
    '10 N thruster and a 2 MN booster - and are removed rather than '
    'relabelled as an assumption')

# Turbopompa benzerlik modeli (Huzel & Huang, "Modern Engineering for Design
# of Liquid-Propellant Rocket Engines", AIAA 1992, Ch. 6 — KU-K1/SP-H1 K3: bu
# baskı okunmadı, sayfa doğrulanmadı; NASA SP-125 (1967) Böl. 6'daki NPSH,
# N_ss ve N_s tanımları Eş. 6-7/6-8/6-10, s. 190-192; Stepanoff,
# "Centrifugal and Axial Flow Pumps" 2nd ed.).
PUMP_SUCTION_SPECIFIC_SPEED = 8.0    # boyutsuz w_ss, indüserli roket pompası
# --- B5 (v2.6.27): boyutsuz Ω_ss <-> ABD birim geleneği Nss köprüsü --------
# Modülün emme bantları ABD birimleriyle (rpm, gpm, ft) tanımlı; motorun
# emme kabiliyeti ise boyutsuz Ω_ss = 8.0. İKİNCİ bir emme-hızı literali
# yazmamak için çevrim katsayısı modülün KESİN birim tanımlarından türetilir
# (Nss_US = Ω_ss · (60/2π) · g^0.75 · √(gpm/(m³/s)) / (ft/m)^0.75 ≈ 2733·Ω_ss;
# turbopump_sizing modül başlığındaki aynı bağıntı). Sonuç ≈ 21 861 US —
# modül bantlarına göre İNDÜSERLİ sınıf (indüsersiz tavan 11 000 US'in
# üstünde, indüserli tasarım varsayılanı 30 000 US'in altında).
NSS_US_PER_OMEGA_SS = ((60.0 / (2.0 * np.pi)) * G_0 ** 0.75
                       * m3s_to_gpm(1.0) ** 0.5 / m_to_ft(1.0) ** 0.75)
PUMP_SUCTION_SPECIFIC_SPEED_US = (PUMP_SUCTION_SPECIFIC_SPEED
                                  * NSS_US_PER_OMEGA_SS)
PUMP_BLADE_COUNT = 6                 # çark kanat sayısı (tipik 5-8)
PUMP_BLADE_EXIT_ANGLE_DEG = 25.0     # geriye eğik kanat çıkış açısı
PUMP_HYDRAULIC_EFFICIENCY = 0.88     # hidrolik verim (Euler head -> gerçek)
PUMP_EFFICIENCY_DEFAULT = 0.75       # toplam pompa verimi (BEP)
PUMP_EXIT_WIDTH_RATIO = 0.06         # b2/D2 çark çıkış genişlik oranı
# B5 (v2.6.27): bu sabit artık YALNIZ YEDEK değerdir. NPSH buhar basıncı
# önce _feed_fluid_record kaydından (su koçu tablosuyla TEK kaynak) gelir;
# kayıt yoksa NBP depolama doygunluğu (1 atm) varsayılır ve bu düşüş SESSİZ
# DEĞİLDİR: warn.liquid.npsh_vapor_pressure_assumed uyarısı + basis beyanı
# üretilir. Eski davranış her iticiye 1,013 bar dayatıyordu — RP-1'in gerçek
# buhar basıncı ~0,007 bar iken NPSH ~12,7 m eksik sayılıyordu (ölçüm:
# 25 kN LOX/RP-1 örneği, 2026-08-15).
PUMP_NPSH_VAPOR_PRESSURE_BAR = 1.01325  # YEDEK: NBP depolama doygunluğu
# NPSH_a <= 0 çıktığında emme sınırı devir TANIMLAMAZ; donanım yine de
# boyutlansın diye devir seçiminde kullanılan nominal giriş yükü tabanı.
# Tasarım bu durumda GERÇEKLENEMEZ ve critical uyarı + speed_source beyanı
# üretilir (eski kod aynı 1e3 Pa tabanını satır içi ve SESSİZ uyguluyordu).
PUMP_NPSH_SPEED_FLOOR_PA = 1.0e3
# Pratik mil hızı tavanı [rpm]: emme özgül hızı tek başına küçük debilerde
# fiziksel olmayan devirler verir; roket turbopompaları ~1.2e5 rpm altındadır.
# KU-K1/SP-H1 K30: eski künye "Huzel & Huang Ch. 6 tablo aralığı" idi; SP-125
# (1967) bir tavan vermez (kitaptaki en yüksek devir ~31 740 rpm) — kaynaksız
# pratik tavan. Tavan uygulanırsa kullanıcı uyarılır.
PUMP_MAX_SPEED_RPM = 120000.0
PUMP_TANK_PRESSURE_DEFAULT_BAR = 3.0    # turbopompa beslemesi NPSH tankı
# GEREKEN besleme basıncının beyanlı payı [bar] (bkz. calculate_injector_design
# -> required_*_tank_pressure). Eskiden formülün içinde çıplak "+ 8" olarak
# duruyordu ve künyesi yoktu; sayı DEĞİŞMEDİ, yalnız tek tanım noktasına
# alındı ve beyan metni buradan üretiliyor (ÖH defter P3B2-01, Z5S/PK1).
INJECTOR_FEED_MARGIN_BAR = 8.0
PUMP_CURVE_FLOW_MIN, PUMP_CURVE_FLOW_MAX = 0.5, 1.5  # Q/Q_bep tarama bandı
PUMP_CURVE_POINTS = 20
TURBINE_VELOCITY_RATIO = 0.45        # U/C0, tek kademeli impuls türbin optimumu
# Tek kademeli türbin kanat uç hızı pratik sınırı [m/s] (malzeme gerilmesi).
# KU-K1/SP-H1 K31: eski künye "Huzel & Huang Ch. 6" idi; SP-125'te 500 m/s
# YOK. NASA SP-8110 s. 18: güncel tasarımların pitch hızı 1000-1500 ft/s
# (305-457 m/s); Sutton 9. bs. s. 390 kanat uç hızı 400-700 m/s (SP-T2 K10).
# Değer DEĞİŞMEDİ (çift sabit kalemi B8/KU-13). Aşılırsa kullanıcı uyarılır.
TURBINE_TIP_SPEED_LIMIT_MS = 500.0
TURBINE_EFFICIENCY_DEFAULT = 0.65
TURBINE_PRESSURE_RATIO_DEFAULT = 8.5
# KU-26 BEYANI (6 Eki 2026; H-6 fail-closed onarımı DEVİR — bkz. aşağı):
# Aşağıdaki üç sayı ÇEVRİM KAPANMADIĞINDA türbin kartının yedek yolunu
# besler ve KAYNAKSIZDIR: TIT 1200 K, HRMA'nın kendi soğutmasız sınırı
# cycle_power_balance.TIT_UNCOOLED_LIMIT_K = 1100 K'nin ÜSTÜNDEDİR; gaz cp
# 2000 J/(kg·K) ve γ 1,30 NASA SP-8110 (1974) Tablo III (s. 16) ile uyuşan
# itken vermez (LOX/RP-1 cp ~2,66-2,77 kJ/(kg·K), γ ~1,10-1,15; LOX/LH2 cp
# ~7,3-8,4, γ ~1,33-1,37; SP-T2 notu K8/K9). Yedek yolu fail-closed yapmak
# (sayı yerine DEĞERLENDİRİLMEDİ) tests/test_scofield_sivi.py:239-269
# bekçisinin beklentisini (kapanmayan çevrimde ṁ = P/(Δh·η) özdeşliği sayısal
# Δh ister) değiştirmeyi gerektirdi; kulvar kuralı gereği YAPILMADI, devir.
# Sayılar DEĞİŞMEDİ; kart künyesi bu durumu TURBINE_FALLBACK_GAS_BASIS ile
# söyler.
TURBINE_GAS_CP_J_KGK = 2000.0        # yakıtça zengin GG gazı cp (tahmin)
TURBINE_GAS_GAMMA = 1.30
GAS_GENERATOR_TEMP_DEFAULT_K = 1200.0
TURBINE_FALLBACK_GAS_BASIS = (
    'UNSOURCED FALLBACK (cycle power balance did not converge): turbine gas '
    'cp 2000 J/(kg K) and gamma 1.30 match no propellant in NASA SP-8110 '
    'Table III (p. 16), and the 1200 K inlet temperature used when none is '
    'supplied exceeds HRMA\'s own 1100 K uncooled turbine limit; the specific '
    'work, gas mass flow and single-stage blade speed on this card are '
    'therefore not evaluated against a real turbine gas')
GAS_GENERATOR_FLOW_FRACTION = 0.05   # ana debinin %5'i
GAS_GENERATOR_PRESSURE_RATIO = 1.3   # GG oda basıncı / ana oda basıncı

# Yapısal analiz
SAFETY_FACTOR_DEFAULT = 2.5          # form varsayılanı ile aynı
SAFETY_FACTOR_MIN, SAFETY_FACTOR_MAX = 1.1, 10.0
CHAMBER_MATERIAL_DEFAULT = 'inconel_718'
# --- B4 (v2.6.27 6. dalga): emniyet katsayısı / malzeme KAYNAK beyanı ------
# Tank bloğu kendi emniyet katsayısının kaynağını zaten beyan ediyordu
# ('user input (safety factor)' / 'not supplied -> ... default'); HAZNE
# tarafında aynı beyan YOKTU: _structural_design sessizce
# SAFETY_FACTOR_DEFAULT ve CHAMBER_MATERIAL_DEFAULT kullanıyor, çıktıdaki
# 'safety_factor: 2.5' ve 'material: Inconel 718 (aged)' kullanıcı seçimiyle
# varsayılanı ayırt ettirmiyordu. Aynı desen (YENİ mekanizma değil) hazneye
# de uygulanır; metinler TEK tanım noktasından üretilir ki tank ile hazne
# aynı durumu iki farklı cümleyle anlatmasın.
SAFETY_FACTOR_SOURCE_USER = 'user input (safety factor)'
SAFETY_FACTOR_SOURCE_DEFAULT = (
    f'not supplied -> {SAFETY_FACTOR_DEFAULT:g} default')
SAFETY_FACTOR_SOURCE_REJECTED = (
    f'supplied value not usable (see input_warnings) -> '
    f'{SAFETY_FACTOR_DEFAULT:g} default')
CHAMBER_MATERIAL_SOURCE_USER = 'user input (chamber material)'
CHAMBER_MATERIAL_SOURCE_DEFAULT = (
    f"not supplied -> '{CHAMBER_MATERIAL_DEFAULT}' default")
CHAMBER_MATERIAL_SOURCE_REJECTED = (
    f'supplied value not recognised (see input_warnings) -> '
    f"'{CHAMBER_MATERIAL_DEFAULT}' default")
# Hesaplanan cidar kalınlığının altına inemeyeceği İMALAT tabanı [m].
# Hibritteki WALL_THICKNESS_INPUT_MIN_M ile karıştırılmamalı: o,
# kullanıcının elle girebileceği en ince değerdir (0.5 mm).
WALL_THICKNESS_MANUFACTURING_MIN_M = 0.002
PROOF_PRESSURE_FACTOR = 1.5          # kanıt basıncı / işletme basıncı
BURST_PRESSURE_FACTOR = 2.5          # patlama basıncı / işletme basıncı
THERMAL_CYCLES_DEFAULT = 500
# Standart plaka/sac kalınlıkları [mm] — gerekli kalınlık bir üst standarda
# yuvarlanır; böylece gerilme marjı tanım gereği 0 olmaktan çıkar.
STANDARD_WALL_THICKNESS_MM = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0,
                              10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0,
                              60.0, 80.0, 100.0, 125.0, 150.0)
# ÖH A2 sivi-sogutma · denetçi Ş2 (4. tur, Berke §27-18): cidar boyutlandırması
# BOĞAZ kesitinin eksenel (meridyen) zar yükünü de görür. Türetim ve kaynaklar
# (baskı + sayfa; sayfalar pdftotext çıktısında sayfa başlığı/altı basılı
# numarayla doğrulandı, 29 Eyl — kanıt a1/sart4/):
#   * Boğaz kesitindeki cidar kuvveti = kesitin bir yanındaki cidara etkiyen
#     basıncın eksene dik düzlemdeki izdüşümünün toplamı (Sutton & Biblarz,
#     Rocket Propulsion Elements 9. baskı, Wiley 2017, s. 32: "Axial thrust can
#     be determined by integrating all the pressures acting on areas that have
#     a projection on the plane normal to the nozzle axis"; s. 297: "chamber
#     walls have to transmit thrust loads"; NASA SP-8087, 1972, s. 66: lülenin
#     itki yükü boğazdan "local meridional loads" olarak geçer).
#   * Basınç, yerel STATİK basınçtır (SP-8087 s. 27: lülede çember çekmesi
#     statik basınçtan doğar), 1B izantropik akış: alan-Mach Sutton Eş. 3-14
#     (s. 50), boğaz basıncı Eş. 3-20 (s. 57). İntegral kapalı biçimde itki
#     fonksiyonuyla alınır: d(p·A·(1 + γM²)) = p·dA (Sutton Eş. 2-13'ün, s. 33,
#     kontrol hacmi türetimi).
#   * İki serbest cisim, ZARFI alınır (itkinin hangi uçtan alındığı bu
#     modelde bilinmez): aşağı akım (itki boğazın ÖNÜNDEN alınır — enjektör/
#     gimbal bağlantısı): ıraksak cidar kuvveti, boğazda BASI; yukarı akım
#     (kapalı enjektör ucu, Sutton Eş. 15-1 s. 557 σ_θ = 2σ_l = pR/d'nin boğaz
#     karşılığı): uç yükü − yakınsak cidar izdüşümü, boğazda ÇEKME.
#   * Eşdeğer gerilme bozulma enerjisi (von Mises) ile (SP-8087 s. 72); boğaz
#     çemberi σ_θ = p_t·r_t/t (silindir yaklaşımı — meridyen eğriliği ve
#     süreksizlik eğilmesi zar boyutlandırmasında YOK, FEA'da var).
# FEA köprüsü (hrma.fea.bridge) iç yüzeye lüle BOYUNCA SABİT P_c uygular
# (beyanlı üst sınır). Onun boğaz yükü aşağı akım için (ε − 1)·P_c·A_t'dir;
# izantropik değerle oranı ``throat_meridional_check`` bloğunda yayımlanır
# (karşılaştırma bandı). FEA yük modeli A3c-4 fea-kopru-yuk kulvarının işidir.
THROAT_MERIDIONAL_BASIS = (
    'Throat section meridional (axial) membrane load: the force the wall must '
    'carry across the throat equals the axial projection of the wall pressure '
    'on one side of the cut (Sutton & Biblarz, Rocket Propulsion Elements 9th '
    'ed., Wiley 2017, p. 32 and p. 297; NASA SP-8087 (1972) p. 66, nozzle '
    'thrust loads are carried through the throat as local meridional loads). '
    'The pressure is the local static pressure of 1-D isentropic flow (NASA '
    'SP-8087 p. 27; Sutton Eq. 3-14 p. 50, throat pressure Eq. 3-20 p. 57), '
    'integrated in closed form through the impulse function '
    'd(p A (1 + gamma M^2)) = p dA (control-volume momentum, Sutton Eq. 2-13 '
    'p. 33). Both free bodies are taken and the worse governs, because the '
    'thrust take-out point is not modelled: downstream (thrust taken out '
    'forward of the throat) = divergent-wall force, compressive at the throat; '
    'upstream (closed injector end, the throat analogue of Sutton Eq. 15-1 '
    'p. 557) = end load minus the convergent-wall projection, tensile. '
    'Equivalent stress by the distortion-energy (von Mises) theory (NASA '
    'SP-8087 p. 72) with the throat hoop stress p_t r_t / t (cylinder '
    'approximation: meridional curvature and discontinuity bending are not in '
    'this membrane sizing; the structural FEA resolves them).')

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

# ---------------------------------------------------------------------------
# ÖH D21 · OH-D20-02 — ÇAN SAPMA VERİMİ ARTIK KONTURA BAĞLI
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (once.json OH-D20-02): ``bell_80`` (çıkış açısı 8,5°, %80 uzunluk)
# ile ``bell_60`` (çıkış açısı 12,0°, %60 uzunluk) AYNI λ = 0,985'i alıyor,
# dolayısıyla ikisinin teslim Isp'si BİREBİR aynı çıkıyordu (333,2237 s).
# Kısa çan daha çok sapma kaybeder; bu iki kontur ayırt edilemez olamaz.
#
# Sayı UYDURULMAZ. İki YAYIMLANMIŞ büyüklük birleştirilir:
#   1) ``hrma.constants.LAMBDA_BELL`` = 0,985 — Rao-optimize çan için
#      yayımlanmış değer (Sutton & Biblarz 9. baskı). Bu değer KANONİK
#      %80 çan içindir; HRMA'nın referans konturu da odur
#      (NOZZLE_TYPE_DEFAULT = 'bell_80').
#   2) EŞDEĞER-KONİ yaklaşımı (KU-K1/SP-H1 K42: eski künye "Huzel & Huang,
#      NASA SP-125, Böl. 1" idi; SP-125 Böl. I'de eşdeğer koni / ortalama
#      açı YOK — bell λ SP-125 Şekil 4-12, s. 91'dedir; yaklaşım HRMA'nındır):
#      λ_koni(ᾱ) = (1 + cos ᾱ)/2, ᾱ = ½(θ_boğaz_çıkış + θ_lüle_çıkış).
#      Bu bağıntı depoda ZATEN var ve AYNI büyüklüğü çözüyor
#      (hrma/analysis/nozzle_flow_1d.py, 'bell' dalı) — yani sıvı motorun
#      0,985'i ile lüle çözücüsünün eşdeğer-koni değeri aynı lüle için
#      ayrışıyordu.
#
# Sözleşme: referans kontur yayımlanan değeri AYNEN alır (bu yüzden
# ``bell_80``, ``aerospike`` ve ``dual_bell`` sayıları DEĞİŞMEZ); başka bir
# çan konturu, eşdeğer-koni ORANI kadar düzeltilir:
#       λ(kontur) = LAMBDA_BELL · λ_koni(ᾱ_kontur) / λ_koni(ᾱ_referans)
# Oran boyutsuzdur ve iki yayımlanmış büyüklükten kurulur; ne yeni bir
# katsayı ne de yeni bir tablo girer.
# ---------------------------------------------------------------------------
# ÖH D21 · P15B1-07 — VERİM DÖKÜMÜNÜN AD↔ANLAM SÖZLEŞMESİ
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (once.json P15B1-07; 250 kN / Pc 150): ``efficiency_breakdown``
# bloğunun ALTI anahtarı ``_loss`` sonekliyken VERİM taşıyordu
# (``divergence_loss = 98,50``, ``mixing_loss = 94,55`` …). Aynı yanıtta
# ``loss_breakdown`` AYNI adlarla KAYBI taşıyor. Mevcut bekçi
# (tests/test_liquid_wiring_v2626.py) ``kayıp == 100 − verim`` aritmetiğini
# doğru sınıyor ama "bu adın anlamı ne" sorusunu hiç sormuyordu.
#
# Anahtarları yeniden ADLANDIRMAK panel tüketicilerini kırardı; bu yüzden
# doğru adlı ikinci bir döküm yayımlanır ve tarihsel anahtarlar TAKMA AD
# olarak kalır. Eşleme TEK TANIM YERİDİR: hem ürün hem bekçi bunu okur, iki
# liste ayrışamaz.
EFFICIENCY_MECHANISM_NAMES = {
    'divergence_loss': 'divergence_efficiency',
    'boundary_layer_loss': 'boundary_layer_efficiency',
    'heat_transfer_loss': 'heat_transfer_efficiency',
    'combustion_incomplete': 'combustion_efficiency',
    'mixing_loss': 'mixing_efficiency',
    'kinetic_loss': 'kinetic_efficiency',
    'nozzle_length_loss': 'nozzle_length_efficiency',
}
EFFICIENCY_MECHANISM_NAMES_SOURCE = (
    'name/meaning contract: the historic efficiency_breakdown keys keep a '
    '"_loss" suffix while carrying an EFFICIENCY (percent). They are kept '
    'for panel compatibility and re-published here under names that say what '
    'the number is. efficiency_by_mechanism[X] + loss_by_mechanism[X] = 100 '
    'for every mechanism X, and the alias map is published next to them so '
    'no consumer has to guess.')

LAMBDA_BELL_REFERENCE_CONTOUR = 'bell_80'
LAMBDA_BELL_CONTOUR_SOURCE = (
    'published Rao-optimised bell divergence factor '
    '(hrma.constants.LAMBDA_BELL, Sutton & Biblarz 9th ed.) anchored on the '
    "canonical 80% bell, carried to this contour by an HRMA "
    'equivalent-cone RATIO (not in NASA SP-125 Ch. I; the SP-125 bell lambda '
    'is Fig. 4-12, p. 91) lambda_cone(mean wall angle of this '
    'contour)/lambda_cone(mean wall angle of the 80% bell), where the mean '
    'wall angle is (throat-exit turn angle + nozzle exit angle)/2. The '
    'equivalent-cone treatment is the same one hrma/analysis/'
    'nozzle_flow_1d.py uses for bell contours, so the two blocks no longer '
    'disagree about the same nozzle. APPROXIMATE: the ratio is a '
    'first-order contour correction, not a Rao table.')

#: Devre modeli sözcüğü -> ``injector_pattern.pattern_type`` sözcüğü
#: (motor_viz3d.js readInjectorPattern sözleşmesi; v2.6.27 B2). viz
#: sözleşmesi 'imping*' önekini çarpışma çizgileri, 'swirl' sözcüğünü sprey
#: konisi için özel işler; kalan tipler yalnız veri olarak taşınır.
#: Eşlenmeyen tip için blok YAYIMLANMAZ — sözlüğe uydurma sözcük girmez.
INJECTOR_PATTERN_WORD = {
    'showerhead': 'showerhead',
    'like_impinging': 'impinging',
    'impinging_doublet': 'impinging',
    'impinging_triplet': 'impinging',
    'pintle': 'pintle',
    'swirl': 'swirl',
    'coax_swirl': 'swirl',
    'gas_gas_coaxial': 'coaxial',
}

# Yakınsak (daralan) koni yarı açısı. TEK TANIM YERİ (CLAUDE.md kural 11):
# hem soğutma entegrasyonundaki yakınsak uzunluk hem de sonuç sözlüğündeki
# 'convergent_half_angle_deg' bu değeri kullanır; ikisi ayrı sabitken
# birbirinden habersiz kayabiliyordu. 30 derece yaygın bir daralma açısıdır.
# KU-K1/SP-H1 K8: eski künye "standart (Huzel & Huang Böl. 4)" idi; NASA
# SP-125 s. 89 yakınsak yarı açıyı 20°-45° ARALIĞI olarak verir ve 30°'yi
# "standart" demez (Örnek 4-2 20° kullanır); 30° aralığın içindedir. Değer
# DEĞİŞMEDİ. (Sutton & Biblarz 9th ed. Böl. 3.)
CONVERGENT_HALF_ANGLE_DEG = 30.0
CONVERGENT_HALF_ANGLE_BASIS = (
    '30 deg convergent half angle, inside the 20-45 deg range of NASA SP-125 '
    '(Huzel & Huang 1967) p. 89 - SP-125 does not call 30 deg standard; '
    'Sutton & Biblarz 9th ed. Ch. 3; a fixed design choice from the single '
    'definition '
    'point CONVERGENT_HALF_ANGLE_DEG, NOT solved from the contraction contour '
    '- the same angle also sets the convergent cone length used by the '
    'cooling integration, so the two cannot disagree')
# Tank boyutlandırma — TEK model (bkz. _size_tank). Besleme sistemi kartı ve
# ayrıntılı tank tasarımı aynı iki sabiti kullanır; ayrı ayrı gömülüyken
# (1.20 çarpanı vs 1.15 rezerv + %5 ullage) aynı koşuda iki farklı tank
# hacmi raporlanıyordu. Rezerv payı: yüklenen itici / tüketilen itici;
# ullage: tankın sıvı DOLMAYAN hacim kesri.
# KU H-1 (K20, 6 Eki 2026): eski künye "Huzel & Huang Böl. 8" idi; NASA SP-125
# (1967) Böl. 8'de 1,15 çarpanı YOK. SP-125 Eş. 8-1 (s. 332) tank hacmini kalem
# kalem kurar (V kullanılabilir + T hapsolan + B kaynayan + U ullage); Örnek
# 8-1 (s. 333) ullage'ı itici hacminin %2,5'i alır. Sutton & Biblarz 9. bs.
# s. 399-401 (itici bütçesi) ve Tablo 11-1 (s. 402, "mühendislik tahmini")
# kalemleri toplamı ~%2,6-14,5'tir. 1,15 bu yüzden KAYNAKSIZ muhafazakâr
# kabuldür; AIAA 1992 baskısı ("Modern Engineering...") okunamadı, orada
# geçip geçmediği doğrulanmadı. Değer DEĞİŞMEDİ (değer kararı KC-9, Berke).
TANK_PROPELLANT_RESERVE_FACTOR = 1.15
TANK_ULLAGE_FRACTION = 0.05
TANK_RESERVE_BASIS = (
    'TANK_PROPELLANT_RESERVE_FACTOR = 1.15 loaded/consumed propellant reserve; '
    'an UNSOURCED conservative sizing assumption for the safety margin, NOT a '
    'mission-derived residual - HRMA has no mixture-ratio-shift, trapped-'
    'propellant or flight-performance-reserve budget. Comparison: NASA SP-125 '
    '(Huzel & Huang 1967) Eq. 8-1 p. 332 builds the tank volume item by item '
    '(usable + trapped + boil-off + ullage) and does not contain a 1.15 '
    'factor; Sutton & Biblarz 9th ed. pp. 399-401 and Table 11-1 (p. 402, '
    'engineering estimates) give budget items summing to roughly 2.6-14.5 %. '
    'The AIAA 1992 edition was not read (page not verified)')
TANK_ULLAGE_BASIS = (
    'TANK_ULLAGE_FRACTION = 0.05 non-liquid ullage volume fraction of the '
    'tank; fixed, NOT solved from thermal expansion or pressurant demand. '
    'Inside the 3-10 % of tank volume of Sutton & Biblarz 9th ed. p. 196; '
    'NASA SP-125 Example 8-1 (p. 333) uses 2.5 % of the propellant volume')
# Silindirik tank boy/çap oranı. TEK tanım yeri (eskiden gövde içinde satır
# içi 2.5 idi ve iki tank sözlüğüne ayrı ayrı yazılıyordu).
TANK_LD_RATIO = 2.5
TANK_LD_RATIO_BASIS = (
    'length/diameter ratio L/D = 2.5, a structural-efficiency design choice '
    'for a cylindrical tank; NOT optimised against buckling or vehicle '
    'packaging - neither is modelled here. The tank diameter and length '
    'follow from this ratio and the required volume')
# --- A11 (v2.6.27): tank tek-geometri beyanları ----------------------------
# Cidar alt sınırı [m]: imalat/kaynak edilebilirlik tabanı. Eskiden gövdede
# iki kez satır içi 0.003 yazılıydı ve hangi hükmün (basınç boyutlandırması
# mı, taban mı) cidarı yönettiği çıktıda beyan edilmiyordu.
TANK_WALL_MIN_THICKNESS_M = 0.003
TANK_WALL_THICKNESS_BASIS = (
    'thin-wall hoop sizing t = P*r / (yield/SF) at the tank operating '
    'pressure, floored at the 3 mm minimum manufacturing gauge '
    '(TANK_WALL_MIN_THICKNESS_M). wall_thickness_governed_by names which of '
    'the two ruled; the pressure-sized value is kept apart under its own '
    'name (wall_thickness_pressure_sized_mm) so the two numbers cannot be '
    'read as one concept. The pressure_vessel.required_thickness_mm leaf is '
    'a DIFFERENT requirement (ultimate strength x burst factor), '
    'deliberately reported under its own name.')
# Yüklenen itici kütlesi beyanı: tank kartındaki kütle REZERV DAHİLDİR ve
# design_summary'deki nominal yanma kütlesinden %15 büyüktür. İki sayı aynı
# kavram DEĞİLDİR; ikisi de kendi adıyla ve oranı beyan edilerek raporlanır
# (turbopompa çark çapı deseni: iki büyüklük bilerek ayrı adla yayımlanır).
TANK_LOADED_MASS_BASIS = (
    'loaded propellant mass = nominal burned mass (mass flow x burn time, '
    'the design_summary.masses.propellant_mass_kg concept, reported here as '
    f'mass_nominal) x {TANK_PROPELLANT_RESERVE_FACTOR:g} reserve '
    '(TANK_PROPELLANT_RESERVE_FACTOR). The two masses are deliberately '
    'reported under separate names with the reserve declared, so the 15% '
    'gap cannot be read as a contradiction')
# Tank işletme basıncı kaynak künyeleri (bkz. _tank_pressure_bar) — metin
# TEK tanım noktasından üretilir ki besleme kartı ile tank kartı aynı
# durumu iki farklı cümleyle anlatmasın.
TANK_PRESSURE_SOURCE_PRESSURE_FED_USER = (
    'user feed pressure input (pressure-fed cycle: the tank IS the feed '
    'pressure source, so the tank operating pressure is the same input the '
    'feed chain uses)')
TANK_PRESSURE_SOURCE_PRESSURE_FED_DEFAULT = (
    'no feed pressure supplied -> '
    f'{PUMP_TANK_PRESSURE_DEFAULT_BAR:g} bar '
    'PUMP_TANK_PRESSURE_DEFAULT_BAR fallback, the SAME fallback the feed '
    'chain reports; almost certainly too low to feed the chamber - see '
    'tank_pressure_margin_bar / required_ox_tank_pressure for the shortfall')
TANK_PRESSURE_SOURCE_TURBOPUMP = (
    'NPSH tank pressurisation assumption '
    f'({PUMP_TANK_PRESSURE_DEFAULT_BAR:g} bar, '
    'PUMP_TANK_PRESSURE_DEFAULT_BAR) - the SAME value the pump NPSH chain '
    'uses; HRMA has no pressurisation schedule model')
# F3 (ÖH D18 fizik-a2): turbopompa dalında tank basıncı artık bu sabitten
# DEĞİL, pompaların NPSH gereksiniminden boyutlandırılır. Sabit yalnız
# gereksinim ÇÖZÜLEMEDİĞİNDE (hat/akışkan kaydı yok) geri dönüş yoludur ve
# o zaman da künye bunu söyler.
TANK_PRESSURE_SOURCE_TURBOPUMP_NPSH = (
    'sized from the pump NPSH requirement: p_tank = p_v + rho*g*(k*NPSH_req '
    '- z) + dp_suction, with NPSH_req = k_v * c_m^2/(2g). ' +
    NPSH_VELOCITY_HEAD_SOURCE + ' ' + NPSH_SINGLE_MARGIN_CONTRACT + ' ' +
    NPSH_STATIC_HEAD_SOURCE + ' The governing pump (the one that needs the '
    'higher tank pressure) sets the number for both tanks, because HRMA '
    'models one pressurisation level per stage.')
# SP-8107 Table II'de kayıtlı UÇUŞ motorlarının pompa GİRİŞ basınçları
# 22-77 psia arasındadır (LR87-AJ-3 RP-1 22; MA-5 sustainer RP-1 77). Bu bant
# türetilen tank basıncı için bir akıl sağlığı çapasıdır, HÜKÜM değildir.
SP8107_INLET_PRESSURE_BAND_BAR = (1.517, 5.309)
SP8107_INLET_PRESSURE_BAND_SOURCE = (
    'NASA SP-8107 (1974) Table II pump inlet total pressures of flight '
    'engines: 22 psia (LR87-AJ-3 RP-1) to 77 psia (MA-5 sustainer RP-1), '
    'i.e. 1.52-5.31 bar. HRMA sizes the MINIMUM pressurisation the steady '
    'design point needs; flight vehicles pressurise above that minimum for '
    'the start transient, which HRMA does not model, so landing at or below '
    'the lower edge of this band is expected for small engines.')
TANK_PRESSURE_SOURCE_TURBOPUMP_FALLBACK = (
    'NPSH-sized tank pressure could NOT be solved on this run (the feed-line '
    'or fluid record needed for the inlet velocity head is missing), so the '
    f'declared {PUMP_TANK_PRESSURE_DEFAULT_BAR:g} bar model fallback '
    '(PUMP_TANK_PRESSURE_DEFAULT_BAR) is used. This is a stand-in, NOT a '
    'sized pressurisation level.')
# --- Tank iç yapıları (bkz. _design_tank_internals) ------------------------
# Bu blok GEOMETRİK ORANLAMA kurallarıdır, fiziksel yasa değildir; her biri
# çıktıda kendi 'basis' etiketiyle bildirilir. Değerler eskiden fonksiyonun
# içinde satır içi gömülüydü (0.3 / 0.1 / 8 / 0.95 / 0.2 / 15° / %15) ve
# oradan çıktıya SABİT sayı olarak basılıyordu.
TANK_ANTIVORTEX_D_RATIO = 0.30        # kanat dizisi çapı / tank çapı
TANK_ANTIVORTEX_H_RATIO = 0.10        # kanat yüksekliği / tank çapı
TANK_ANTIVORTEX_VANE_COUNT = 8        # radyal kanat sayısı
TANK_BAFFLE_OUTER_D_RATIO = 0.95      # bafl dış çapı / tank çapı
TANK_BAFFLE_INNER_D_RATIO = 0.20      # bafl merkez açıklığı / tank çapı
# Halka bafl hedef açık alan oranı. TASARIM HEDEFİDİR; NASA SP-8031 (Propellant
# Slosh Loads) delikli halka baflları için %10-30 bandını verir. Delik SAYISI
# bu hedeften boyutsal olarak doğru türetilir ve GERÇEKLENEN oran ayrıca
# raporlanır (hedef ile gerçeklenen artık aynı sayı değildir).
TANK_BAFFLE_OPEN_AREA_TARGET = 0.15
# Halka genişliği boyunca kaç sıra delik açılacağı — İMALAT seçimidir ve
# çıktıda öyle etiketlenir. Delik ÇAPI bundan ve hedef açık alan oranından
# üçgen adımlı delikli plaka özdeşliğiyle çıkar:
#     acik_alan_orani = (pi / (2*sqrt(3))) * (d/p)^2      [üçgen dizilim]
# p = halka_genisligi / sira_sayisi. Buradaki pi/(2*sqrt(3)) bir GEOMETRİK
# ÖZDEŞLİKTİR, uydurulmuş katsayı değildir.
TANK_BAFFLE_HOLE_ROWS = 3
# İç yapı sac kalınlıkları [mm] — ASGARİ İMALAT GAUGE'İDİR, yüke göre
# boyutlandırılmamıştır. Çalkantı/çarpma yükü bu sürümde MODELLENMİYOR
# (NASA SP-8031 halka bafl yükü eksenel ivme ister; araç modeli yok), bu
# yüzden değerler 'load-sized' diye sunulmaz.
TANK_VANE_GAUGE_MM = 3.0
TANK_BAFFLE_GAUGE_MM = 2.0
TANK_INTERNALS_MATERIAL = 'aluminum_6061'
# Tank ağzı difüzör yarı açısı [derece] — ayrılmayan yayılma için 15° tipiktir
# (ESDU 73024 konik difüzör ayrılma sınırı). KU-K1/SP-H1 K35: eski künye
# "Huzel & Huang Böl. 7" idi; SP-125'te difüzör Böl. VIII §8.7'dedir ve 15°
# sayısı orada bulunamadı (sayfa doğrulanmadı).
TANK_DIFFUSER_HALF_ANGLE_DEG = 15.0
# Difüzör çıkış çapı / giriş (hat) çapı: hızı yaklaşık dörtte birine indirir.
TANK_DIFFUSER_AREA_RATIO = 2.0
# Sump / standpipe ağız çapı / besleme hattı çapı. Girdap ve NPSH kaybını
# azaltmak için tank ağzı hattan geniş tutulur (tipik 1.2-1.5; KU-K1/SP-H1
# K35: eski künye "Huzel & Huang Böl. 7"; SP-125'te bu oran bulunamadı —
# kaynaksız pratik). Kritik dalma (gaz yutma) ölçütü MODELLENMİYOR.
TANK_OUTLET_TO_LINE_D_RATIO = 1.30
# Bir tank ağzı için borulama uzunluğu / ağız çapı (stub + flanş payı).
TANK_PORT_STUB_LD = 3.0
# --- Tank enstrümantasyonu (v2.6.26) ---------------------------------------
# Bu iki kalem MİMARİ VARSAYIMIDIR; ölçüm doğruluğu, ullage çözünürlüğü ya da
# güvenilirlik hedefi HRMA'da modellenmez. Seviye probu SAYISI ayrıca
# yazılmaz: yerleşim listesinin uzunluğudur (tek tanım yeri), yoksa iki sayı
# birbirinden habersiz kayabilir.
TANK_PRESSURE_TRANSDUCER_COUNT = 2
TANK_LEVEL_PROBE_POSITIONS = (0.25, 0.5, 0.75, 0.95)   # doluluk kesri
# --- A2: itici çalkantısı (slosh) bağlaması (v2.6.27) -----------------------
# Çalkantı modeli hrma.analysis.slosh_analysis'tir (NASA SP-106 / Dodge 2000
# doğrusal serbest yüzey, dik rijit silindir). Motor tarafında TEK varsayım
# eksenel ivmedir: uçuş ivme profili bu çözücüde yoktur (yörünge modülüyle
# bağlanması yol haritasında ayrı kalemdir), bu yüzden g_eff = 1g alınır ve
# çıktıda adıyla beyan edilir. Sayı uydurulmaz: 1g yer/statik durumun ta
# kendisidir ve uçuşta frekans sqrt(g_eff) ile ölçeklenir (SP-106 Eq. 2.4).
TANK_SLOSH_G_EFF_BASIS = (
    'g_eff = 9.80665 m/s2 (standard gravity): ground/static condition. HRMA '
    'does not couple the flight axial-acceleration profile into the tank '
    'model, so the in-flight slosh frequency is NOT reported; it scales as '
    'sqrt(g_eff/g0) per NASA SP-106 Eq. 2.4 - rescale for a known thrust '
    'acceleration.')
# --- A6: besleme hattı su koçu (water hammer) bağlaması (v2.6.27) -----------
# hrma.analysis.water_hammer FLUID_PROPERTIES tablosunda hacimsel modülü
# TABLOLU olan itici anahtarları. Haritada OLMAYAN itici için o hat
# NOT_MODELLED beyanıyla boş döner (bulk modül uydurulmaz) ve kullanıcı
# /api/water-hammer ucuna bulk_modulus_Pa + density_kg_m3 vererek özel sıvı
# analizi yapabilir.
#
# ÖH D31 · P4B4-07 + OH-D27-08 — HARİTA 2'DEN 7'YE ÇIKTI.
# Harita v2.6.27'ye kadar yalnız {lox, rp1} taşıyordu; motorun kendi itici
# listesindeki yedi itici haritasızdı (ÖLÇÜLDÜ: kapsama 2/9, üretilen su
# koçu bloğu 2). Beş itici için BİRİNCİL kaynaklı hacimsel modül + yoğunluk
# + buhar basıncı kaydı kazanıldı (water_hammer.FLUID_PROPERTIES içindeki
# künyelere bakın: NIST Chemistry WebBook; AFRPL-TR-69-149; AFRPL-TR-76-76)
# ve bu beş itici haritaya girdi.
#
# HARİTAYA ALINMAYAN İKİ İTİCİ — gerekçeleri ADIYLA:
#   h2o2 : FLUID_PROPERTIES kaydı VAR (K ve rho künyeli) ama BUHAR BASINCI
#          için birincil kaynak kazanılamadı. Bu harita aynı zamanda
#          besleme buhar basıncı kaynağıdır (FEED_FLUID_PROPERTY_KEY),
#          dolayısıyla buhar basıncısız bir kaydı buraya koymak NPSH ve
#          kolon ayrılması kapılarını kaynaksız bırakırdı. Fail-closed.
#   n2o  : kaydı D31'de kanona taşındı (yoğunluk artık
#          N2O_LIQUID_DENSITY_SAT_25C) ve künyesi tamamdır; haritaya
#          alınması ürün kapsamı kararıdır (onaylanan D31 genişlemesi beş
#          itici içindi) ve o karar verilene kadar fail-closed kalır.
WATER_HAMMER_FLUID_KEY = {
    'lox': 'lox',
    'rp1': 'rp1',
    'lh2': 'lh2',
    'methane': 'methane',
    'mmh': 'mmh',
    'udmh': 'udmh',
    'n2o4': 'n2o4',
}
# Besleme borusu malzemesi: motorun bir hat malzemesi SEÇİMİ yoktur (hat
# geometrisi yalnız akış hızına göre boyutlanır). Kullanıcı
# 'feed_line_material' vermezse su koçu modülünün kendi paslanmaz varsayılanı
# kullanılır ve kaynağı çıktıda beyan edilir.
WATER_HAMMER_DEFAULT_PIPE_MATERIAL = 'ss_304'

# --- C1/C2 (v2.6.27 6. dalga): besleme akışkanı BUHAR BASINCI -------------
# Buhar basıncı motorun hiçbir yerinde ÇÖZÜLMEZ (itici sıcaklığı bir durum
# değişkeni değil). Hem turbopompa NPSH'ı (Eş. 1) hem vana kavitasyon
# taraması onsuz kurulamaz. Uydurmak yerine deponun KENDİ kaynak künyeli
# tablosu kullanılır: hrma.analysis.water_hammer.FLUID_PROPERTIES, yani
# A6 su koçu bağlamasının AYNI itici kaydı (tek kaynak — iki modül iki
# farklı buhar basıncı varsayamaz). Referans sıcaklık ve kaynak metni
# çıktıya aynen taşınır. Tabloda olmayan itici için ilgili blok
# NOT_MODELLED döner ve eksik girdiyi ADIYLA söyler.
FEED_FLUID_PROPERTY_KEY = WATER_HAMMER_FLUID_KEY
# Ana kesme vanası stili: hattın K=0.15 kalemi TAM AÇIK küresel/kelebek
# vanadır (FEED_K_MAIN_VALVE yorumuyla aynı), dolayısıyla ISA-75.01.01
# basınç geri kazanım faktörü tablosundaki karşılığı tam geçişli küresel
# vanadır. Vana STİLİ bir HRMA girdisi değildir; beyan edilir.
FEED_MAIN_VALVE_STYLE = 'ball_full_bore'
# Viskozite kullanıcı girdisi yoksa Darcy-Weisbach zincirinin düştüğü
# değerler (_calculate_feed_system_pressure_drops ile TEK tanım). Vana/hat
# bütçesi de AYNI değeri kullanır ki iki hat hesabı ayrışmasın.
FEED_VISCOSITY_FALLBACK_PA_S = {'oxidizer': 2.0e-4, 'fuel': 1.2e-3}

# --- A5 (v2.6.27 6. dalga): pasif ısıl koruma bağlaması --------------------
# Ablatif astar varsayılan malzemesi. thermal_protection modülünün tanıdığı
# ablatiflerden biri; hibrit motorun LINER_MATERIAL_DEFAULT'u ile AYNI
# değerdir (iki motor aynı modüle iki farklı varsayılanla gitmez).
# TASARIM SEÇİMİDİR, çözüm değildir — çıktıda adıyla beyan edilir.
TPS_LINER_MATERIAL_DEFAULT = 'silica_phenolic'
# Cidar sıcaklık geçmişi örnekleme tavanı (hibritteki WALL_HISTORY_MAX_POINTS
# ile aynı gerekçe: yanıt boyutu sınırlanır, son nokta daima korunur).
TPS_WALL_HISTORY_MAX_POINTS = 200
# API RP 520 Part I sertifikalı emniyet vanası boşaltma katsayısı.
RELIEF_VALVE_DISCHARGE_COEFF = 0.975
# Emniyet vanası ayar basıncı / tank işletme basıncı (ASME VIII Div.1 UG-134:
# ayar basıncı en çok MAWP kadar; %10 pay ile).
RELIEF_VALVE_SET_PRESSURE_FACTOR = 1.10
# Boşaltma hesabı için basınçlandırma gazı referans sıcaklığı [K]. Tank
# ortam sıcaklığı bu çözücüde modellenmiyor (form alanı 'temp_range_*'
# bilinçli olarak bağlanmamış beyanındadır); standart oda sıcaklığı
# referans alınır ve çıktıda belirtilir.
RELIEF_VALVE_GAS_TEMP_K = 293.15
# 'Uzay optimize' (vakum) lüle: mevcut genişleme oranının katı ve tavanı.
EXPANSION_RATIO_VACUUM_FACTOR = 2.5
EXPANSION_RATIO_VACUUM_CAP = 300.0
# ÖH D33 · OH-UC-05 — VAKUM/DENİZ SEVİYESİ Isp İYİLEŞMESİNİN MAKUL BANDI.
#
# (Isp_vac − Isp_SL)/Isp_SL oranı, itki katsayısındaki ortam basıncı
# teriminin payıdır: CF_vac − CF_SL = ε·p_a/P_c (Sutton & Biblarz, Rocket
# Propulsion Elements, 9. baskı, Eş. 3-30/3-31). Uçmuş donanımda bu pay
# yüzde birkaçtan yüzde on-yirmilere çıkar; bandın DIŞI, çözümün kendisinin
# şüpheli olduğunu söyler (aşırı küçük ε ya da ortam basıncı teriminin
# kaçması). Sayı BURADA TEK KEZ yazılır — hem hükmü ateşleyen satır hem
# bekçi buradan okur (Doktrin 4 / CLAUDE.md kural 11); eskiden ``0.05`` ve
# ``0.5`` doğrudan ``calculate_performance`` gövdesine gömülüydü.
#
# ÖLÇÜLDÜ (docs/scofield/raw/OH/D33/motorlar/a1/once.json · K1): hüküm
# taban ağacında YALNIZ ``print()`` ile stdout'a basılıyordu; yanıtın
# ``design_warnings`` listesinde eşleşen kayıt sayısı 0 idi.
VACUUM_ISP_IMPROVEMENT_BAND = (0.05, 0.50)


def _warning_record(code, severity, params):
    """Sıvı motor uyarı kaydının ŞEMASI — bu dosyada TEK tanım noktası.

    ÖH D33 · OH-UC-05. Şema eskiden ``_warn`` gövdesine gömülüydü; kaydı
    listeye EKLEMEDEN kurmanın (dolayısıyla ``fallback`` gibi üst düzey bir
    alanı dışarıdan sarmanın) yolu yoktu. Kurucu buraya alındı, ``_warn``
    ve ``_mk_warning`` ikisi de buradan okur.

    Ad bilerek ``_w``/``_warn``/``_mk_warning`` DEĞİLDİR: uyarı bekçileri o
    üç adı "yayım yeri" sayıp ilk argümanın bir ``warn.*`` dizgesi olmasını
    bekler; boru tesisatı bir yayım yeri değildir ve öyle sayılırsa yanlış
    alarm üretir (ölçüldü: ``test_v262_release_gate.py::
    test_no_raw_warnings_left_in_engines`` -> "ham uyarı kalmış:
    liquid_rocket_engine.py:2264").

    Sözleşme ``hrma.engines.warning_records.warning_identity`` ile aynıdır:
    kimlik ``code`` + ``severity`` + ``params``tan kurulur; ``fallback``
    gibi ek metin alanları kimliğe GİRMEZ.
    """
    return {"code": code, "params": params, "severity": severity}


def _cea_call_failed_record(validity):
    """CEA çağrısı düşüp tabloya inildiyse köprünün uyarı kaydı, yoksa None.

    ÖH A2 sivi-sogutma · 6. tur (SO1 D-1). ``cea_bridge`` K-1'den beri
    ``validity['fallback_reason'] == FALLBACK_REASON_CEA_CALL_FAILED`` ve
    ``validity['fallback_warning'] = {code, params, severity}`` yayımlar.
    Kayıt YALNIZ köprünün kendi kodu, izinli bir şiddet ve dize ``error``
    parametresiyle kabul edilir (girdi doğrulaması fail-closed: biçim
    tutmazsa None döner ve çağıran eski 'rocketcea_unavailable' uyarısına
    düşer — tabloya iniş hiçbir yolda sessiz kalmaz).
    """
    from hrma.engines import cea_bridge
    if not isinstance(validity, dict):
        return None
    if validity.get('fallback_reason') != \
            cea_bridge.FALLBACK_REASON_CEA_CALL_FAILED:
        return None
    fw = validity.get('fallback_warning')
    if not isinstance(fw, dict):
        return None
    params = fw.get('params')
    if (fw.get('code') != cea_bridge.WARN_CEA_CALL_FAILED
            or fw.get('severity') not in ('warning', 'critical', 'info')
            or not isinstance(params, dict)
            or set(params) != {'error'}
            or not isinstance(params.get('error'), str)):
        return None
    return _warning_record(fw['code'], fw['severity'],
                           {'error': params['error']})


# Pratik genişleme oranı üst sınırı — 'sonlu lüle' kaybının referansı
# (uçmuş üst kademe lüleleri ~200-300; 500 pratik tavan olarak alınır).
EXPANSION_RATIO_PRACTICAL_MAX = 500.0
# Ortam-eşlenik ε çözücüsünün kabul bandı (ÖH defter P3B2-09). Bu iki eşik
# eskiden `max(2.5, min(eps, 1000))` olarak satır içi yazılıydı; kırpma
# SESSİZ olduğu için 'ortam-eşlenik optimum (pe = pa)' iddiası kırpılmış
# lülede de ayakta kalıyordu. Eşikler artık TEK tanımlıdır ve kırpma
# olgusu adıyla yayımlanır.
EXPANSION_RATIO_SOLVER_MIN = 2.5
EXPANSION_RATIO_SOLVER_MAX = 1000.0
# Kapalı form çözülemezse kullanılan KABA yaklaşımın kabul bandı (ÖH D20,
# P3B2-09 ŞART md. 2). Bu iki eşik de eskiden `max(4, min(eps, 300))` olarak
# satır içi yazılıydı: aynı fonksiyonda İKİ ayrı kırpma bandı vardı, ikincisi
# hiçbir yerde yayımlanmıyordu ve kırpma olgusu yedek dalda SESSİZDİ. Bant
# çözücü bandından DARDIR çünkü yedek yaklaşım (izentropik olmayan kaba
# bağıntı) uçlarda anlamsız değerler üretir; bu bir tasarım seçimidir,
# ölçülmüş bir fizik sınırı değildir ve künyesi çıktıda böyle yazılır.
EXPANSION_RATIO_FALLBACK_MIN = 4.0
EXPANSION_RATIO_FALLBACK_MAX = 300.0

# --- ÖH D22 / OH-D20-01 · Isp ÖZDEŞLİK KAPANIŞ EŞİĞİ ----------------------
# ``isp_identity.status`` (CLOSED / OPEN) eşiği eskiden çağrı yerinde çıplak
# ``abs(_res) <= 0.5`` olarak yazılıydı: YAYIMLANAN bir hükmün eşiği koda
# gömülüydü, adı yoktu, künyesi yoktu; okuyucu "%0,5 nereden geliyor"
# sorusunun cevabını hiçbir yerden göremiyordu. Kardeş motorlarda aynı sınıf
# eşik ZATEN adlıdır (``solid_rocket_engine.SOLID_CSTAR_IDENTITY_TOLERANCE_
# PCT`` = 0,05; ``hybrid_rocket_engine.HYBRID_CF_CROSS_CHECK_TOL_PCT`` =
# 0,001); sıvı bu düzenin dışında kalmıştı.
#
# DEĞER DEĞİŞMEDİ (%0,5): bu bir ürün davranışı değişikliği değil, eşiğin
# TEK TANIMLI hâle getirilmesidir. Künye: özdeşlik
# Isp_sl = C_F(0 m)·c*/(g0·C_D) cebirsel olarak TAM kapanır (Sutton &
# Biblarz 9. baskı Denk. 3-31) ve bu ağaçta ölçülen kalıntı tam 0,0'dır
# (raw/OH/D22/sivi/a1/once_d2005.json). Band, üç sayının yayımlanmadan önce
# geçtiği yuvarlama/serileştirme adımlarına ve CEA'nın platformlar arası
# oynamasına ayrılmış mühendislik payıdır; ölçülmüş bir fizik sapma sınırı
# DEĞİLDİR. Kalıntı bandı aşarsa sayı gizlenmez: durum 'OPEN' olur ve kalıntı
# ``residual_pct`` alanında adıyla yayımlanır (fail-closed beyan).
LIQUID_ISP_IDENTITY_TOLERANCE_PCT = 0.5

# Kütle hesabı ekleri
CHAMBER_MASS_JOINT_FACTOR = 1.20      # flanş/bağlantı/takviye payı
INJECTOR_PLATE_THICKNESS_RATIO = 1.5  # enjektör plakası / hazne cidarı
NOZZLE_WALL_THICKNESS_RATIO = 0.60    # lüle cidarı / hazne cidarı (düşük basınç)
# Turbopompa kütlesi: güçle ölçeklenen ampirik korelasyon. KU-K1/SP-H1 K32:
# eski künye "Huzel & Huang Ch. 6 kütle-güç eğilimi" idi; SP-125 §6.2 (s. 186)
# yalnız "eşdeğer ağırlık" kavramını verir, korelasyon yok — kaynaksız
# tahmindir. ETİKETLİ tahmindir, geometriden türetilmemiştir.
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

# --- B4 (v2.6.27 6. dalga): OKUNMAYAN gövde alanları -----------------------
# ÖLÇÜLDÜ (11 Ağustos 2026, bu blok yazılmadan önce): /calculate_liquid
# gövdesine `expansion_ratio` 4 / 20 / 60 / 150 / 400 gönderildi; BEŞİNDE DE
# yanıt `expansion_ratio = 13,223420430204907` ve `isp_sea_level = 298,37`
# döndü. Sebep ad uyuşmazlığı: sıvı çözücünün genişleme oranı girdisi
# `nozzle_expansion_ratio`'dur (liquid.html o adı gönderir, _apply_overrides
# o adı okur). `expansion_ratio` ise çözücünün ÜRETTİĞİ bir çıktı adıdır.
# Yani kullanıcının 400'ü sessizce yok oluyor ve yanıtta aynı ada sahip
# BAŞKA bir sayı duruyordu — okuyan bunu "girdim kabul edildi, 13,22'ye
# yuvarlandı" diye okuyabilirdi.
#
# NEDEN TAKMA AD YAPILMADI: `expansion_ratio` aynı yanıtın ÇIKTI adıdır.
# Girdi olarak da kabul edilseydi, sonucu geri gönderen her istemci (proje
# kaydı, dışa aktarım turu, API zinciri) lüleyi farkında olmadan
# SABİTLERDİ — tasarım "ortam-eşlenik optimum"dan "kullanıcı verdi"ye
# sessizce düşerdi. Bu, düzeltilen kusurun aynısını ters yönde kurardı.
# Bunun yerine depodaki mevcut beyan deseni (app.py
# `_declare_overridden_inputs` -> `inputs_not_used`, alanlar birebir aynı)
# motor tarafında da uygulanır ve DOĞRU alan adı kullanıcıya söylenir.
#
# Beyan VARSAYIMLA değil ÖLÇÜMLE üretilir: gönderilen sayı ile sonuçta
# fiilen duran sayı karşılaştırılır; eşitlerse hiçbir şey yazılmaz.
LIQUID_UNREAD_INPUT_FIELDS = {
    'expansion_ratio': {
        # sonuçtaki hangi alan bu büyüklüğün FİİLEN kullanılan değerini taşır
        'result_key': 'expansion_ratio',
        # kullanıcının bunun yerine göndermesi gereken GERÇEK girdi adı
        'use_instead': 'nozzle_expansion_ratio',
        'reason': 'field_not_read',
    },
}
#: Gönderilen ile kullanılan değerin "aynı" sayıldığı bağıl tolerans.
#: app.py `_INPUT_ECHO_REL_TOL` ile aynı değer — iki yol aynı soruyu aynı
#: eşikle cevaplasın diye.
LIQUID_INPUT_ECHO_REL_TOL = 1e-6


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
        #
        # P3B1-11 (ÖH D17) — YERLEŞİK TABLO ARAMASI HARF/BOŞLUK DUYARLIYDI.
        # ÖLÇÜLDÜ (once.json P3B1-11): ``LIQUID_PROPELLANT_REFERENCE_TABLE``
        # anahtarı ham (fuel_type, oxidizer_type) ikilisiyle aranıyordu;
        # ('methane','lox') tabloda VAR, ('METHANE','LOX') YOK. Aynı fiziksel
        # çift, yalnız büyük harfle yazıldığı için tablo dalını ıskalayıp
        # "tablo dışı çift" dalına düşüyordu: propellant_name
        # 'Methane/LOX (Liquid Methane/Liquid Oxygen)' yerine 'METHANE/LOX',
        # ve performans referansı tablodan değil CEA/bilinmeyen-çift
        # zincirinden çözülüyordu (combustion_data_source değişiyor).
        # Kanonikleştirme burada TEK KEZ yapılır; aşağı akıştaki her
        # ``str(self.fuel_type).lower()`` çağrısı zaten bunu varsayıyordu.
        self.fuel_type = self._canonical_propellant_key(fuel_type)
        self.oxidizer_type = self._canonical_propellant_key(oxidizer_type)

        # Engine configuration
        self.cooling_type = cooling_type
        # ÖH defter P3B4-09 (Z5S/PK1): tanınmayan bir soğutma tipi bugüne
        # kadar SESSİZCE geçiyordu ve aşağı akıştaki kapılar onu "aktif
        # soğutuluyor" sayıyordu. Değer EZİLMEZ (kullanıcı ne yazdıysa
        # çıktıda o durur), ama tanınmadığı ADIYLA söylenir; kapılar da
        # artık tanınan kümelere bakar.
        if str(cooling_type or '').strip().lower() not in \
                COOLING_TYPES_RECOGNISED:
            self._warn('warn.liquid.option_not_recognised', 'warning',
                       field='cooling_type', field_label_en='Cooling type',
                       raw=str(cooling_type))
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
        # ÖH defter P3B1-09 (D23): burada ``self.gamma_combustion = 1.2``
        # duruyordu. ÖLÇÜLDÜ (once_statik.json): depo genelinde tek eşleşme
        # tanımın KENDİSİYDİ - hiçbir yerden okunmuyordu. Motorun gerçek
        # gamma'sı ``self.gamma``dır (CEA eşdeğeri, itici çiftine göre
        # ~1,13-1,24); yanlış gamma'yı okuyacak sonraki geliştirici için
        # tuzaktı. Ölü öznitelik SİLİNDİ; yerine ikinci bir sayı KONMADI.
        self.P_a = 1.01325  # Atmospheric pressure (bar)

        # Set propellant properties
        self._set_propellant_properties()

        # Formdan gelen değerler tablo değerlerini EZER (aralık doğrulamalı).
        self._apply_overrides()

        # CONSISTENCY FIX: Initialize c_star_effective and CD_throat early
        #
        # ÖH defter P3B1-14 (Z5S/PK1): burada
        # ``getattr(self, 'c_star', 1650.0)`` yazıyordu. 1650 m/s, A3
        # kapanışının (UnsupportedPropellantPairError belgesi, yukarıda)
        # ADIYLA YASAKLADIĞI üç yer tutucudan biridir; bugün erişilemez
        # (``_set_propellant_properties`` her yolda ya c*'ı çözer ya
        # A3 hatasını atar) ama kurucu sırası değişirse SESSİZCE canlanır ve
        # hiçbir kimyadan gelmeyen bir c* motorun her sayısına yayılırdı.
        # Artık yedek YOK: c* çözülmemişse hesap burada durur (fail-closed).
        if not hasattr(self, 'c_star_effective'):
            if not hasattr(self, 'c_star'):
                raise UnsupportedPropellantPairError(
                    'characteristic velocity (c*) was never solved for this '
                    'propellant pair, so no effective c* can be published; '
                    'HRMA does not substitute a representative placeholder '
                    '(A3 closure).',
                    fuel=getattr(self, 'fuel_type', None),
                    oxidizer=getattr(self, 'oxidizer_type', None))
            self.c_star_effective = self.c_star
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
    #: ÖH D21 · P3B3-10 — YALNIZCA turbopompalı çevrimde anlamı olan uyarı
    #: kodları. Basınç beslemeli motorda pompa ve türbin YOKTUR (çıktıda
    #: ``turbopump_analysis.applicable = False``, kartlar ``None``), ama
    #: boyutlandırma zinciri yine de koşuyor ve bu kodlar kullanıcıya
    #: gidiyordu. ÖLÇÜLDÜ (once.json P3B3-10; 5 kN / Pc 20 / pressure_fed):
    #: 5 uyarının biri ``warn.liquid.pump_speed_capped`` idi — var olmayan
    #: bir pompanın devri için "tavan uygulandı" haberi. Küme TEK tanım
    #: yeridir: uyarıyı ateşleyen satırlar da bekçi de bunu okur.
    PUMP_ONLY_WARNING_CODES = frozenset({
        'warn.liquid.npsh_pressurization_insufficient',
        'warn.liquid.npsh_velocity_head_not_met',
        'warn.liquid.npsh_insufficient',
        'warn.liquid.pump_speed_capped',
        'warn.liquid.turbine_tip_speed_exceeded',
    })

    def _warn(self, code, severity="warning", **params):
        """Kullanıcıya görünecek uyarıyı i18n kaydı olarak biriktirir.

        v2.6.2 (D-track): backend dilsizdir. Sabit İngilizce metin YERİNE
        ``{"code", "params", "severity"}`` sözlüğü biriktirilir; metni
        frontend ``TF(code, params)`` ile kurar. Sözleşme
        cycle_power_balance._w / validation_system._w ile birebir aynıdır.

        ``code``: ``warn.liquid.<slug>``. ``severity`` ∈ {"critical",
        "warning", "info"}. ``params``: metne gömülü tüm değişkenler.

        Yineleme davranışı korunur: aynı (code, params, severity) üçlüsü
        listeye iki kez girmez (eski kod aynı METNİ iki kez eklemiyordu).
        """
        # ÖH D21 · P3B3-10: basınç beslemeli çevrimde pompa/türbin uyarısı
        # YAYIMLANMAZ. Bu bir susturma değil, KAPSAM hükmüdür: aynı yanıt
        # zaten 'pressure-fed cycle: no pumps, no turbine, no gas generator
        # in this engine' diyor ve kartları boş bırakıyor; olmayan donanım
        # için uyarı üretmek o hükümle çelişirdi. Kararın kendisi
        # ``pressure_fed_pump_warnings_suppressed`` alanıyla BEYAN edilir.
        if (code in self.PUMP_ONLY_WARNING_CODES
                and getattr(self, 'engine_cycle', '') == 'pressure_fed'):
            bastirilan = getattr(self, '_pressure_fed_muted_warnings', None)
            if bastirilan is None:
                bastirilan = self._pressure_fed_muted_warnings = []
            if code not in bastirilan:
                bastirilan.append(code)
            return
        # ``_mk_warning`` DEĞİL, ortak kurucu çağrılır: iki uyarı bekçisi
        # (``test_engine_warning_i18n``, ``test_v262_release_gate``) ``_w`` /
        # ``_warn`` / ``_mk_warning`` adlı çağrıların İLK ARGÜMANINI bir
        # ``warn.*`` DİZGESİ sanar; buradaki ``code`` bir değişkendir ve
        # "ham uyarı kalmış" diye yanlış alarm üretirdi (ölçüldü:
        # liquid_rocket_engine.py:2264). Boru tesisatı yayım yeri değildir.
        record = _warning_record(code, severity, params)
        if record not in self.design_warnings:
            self.design_warnings.append(record)

    def _mk_warning(self, code, severity="warning", **params):
        """Uyarı KAYDINI kurar (listeye EKLEMEZ) — ``_warn`` ile aynı şema.

        ÖH D33 · OH-UC-05. Kaydın şeması ``_warn`` gövdesinde gömülüydü;
        bu yüzden ``i18n_common.js`` anahtarı henüz gelmemiş bir kodun
        İngilizce yedek metnini (``fallback``) KAYDIN ÜST DÜZEYİNE koymanın
        yolu yoktu — ``_warn(..., fallback=...)`` onu ``params`` içine
        düşürürdü ve ``tests/test_engine_warning_i18n.py``nin parametre
        bekçisi anahtar geldiği gün haklı olarak kırılırdı.

        Şema artık TEK yerde kurulur; ``fallback`` katı motordaki kanıtlı
        desenin aynısıyla, DIŞARIDAN sarılır::

            self.design_warnings.append(dict(self._mk_warning(
                KOD, 'warning', a=1), fallback='...'))

        (Örnekteki ``KOD`` bilerek değişken yazıldı: bekçi motor
        dosyalarındaki ``warn.*`` DİZGELERİNİ tarar ve docstring'e yazılmış
        örnek bir kodu gerçek yayım sanardı — ölçüldü, uydurma kod
        ``test_every_engine_code_has_translation``i kırmızıya düşürdü.)

        ``fallback`` bir parametre DEĞİL kayıt alanıdır ve kimliğe girmez
        (bkz. ``hrma.engines.warning_records.warning_identity`` docstring'i).

        Metodun ADI bilerek ``_mk_warning``tir: uyarı bekçilerinin tanıdığı
        yardımcı adlarındandır, dolayısıyla buraya verilen parametreler
        ``test_engine_warning_i18n::test_declared_params_are_used_in_text``
        kapsamında KALIR (anahtar sözlüğe girdiği gün metinle eşleşmeleri
        sınanır). Şemanın kendisi ``_warning_record``tadır.
        """
        return _warning_record(code, severity, params)

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
            self._warn('warn.liquid.input_not_a_number', 'warning',
                       field=key, field_label_en=(label or key), raw=str(raw))
            return None
        if not np.isfinite(f):
            self._warn('warn.liquid.input_not_finite', 'warning',
                       field=key, field_label_en=(label or key))
            return None
        if not (lo <= f <= hi):
            self._warn('warn.liquid.input_out_of_range', 'warning',
                       field=key, field_label_en=(label or key),
                       value=float(f), unit=unit, lo=float(lo), hi=float(hi))
            return None
        return f

    def _override_choice(self, key, allowed, label=None):
        """Metin seçimi doğrular; tanınmayan değer uyarı üretir."""
        raw = self.overrides.get(key)
        if raw is None or raw == '':
            return None
        text = str(raw).strip().lower()
        if text not in allowed:
            self._warn('warn.liquid.option_not_recognised', 'warning',
                       field=key, field_label_en=(label or key), raw=str(raw))
            return None
        return text

    def _resolve_coolant_cp(self, user_cp=None):
        """(cp [J/kg.K], künye) — rejeneratif ceket toplu ΔT'sinin cp'si.

        Sıra: kullanıcı ``fuel_heat_capacity`` > itici tablosu
        (``COOLANT_CP_TABLE_J_KGK``) > künyeli genel varsayım. TEK çözüm
        noktası; ``calculate_cooling_requirements`` buradan okur.
        """
        if user_cp is not None:
            return float(user_cp), 'user input (fuel_heat_capacity)'
        yakit = str(getattr(self, 'fuel_type', '') or '').lower()
        if yakit in COOLANT_CP_TABLE_J_KGK:
            return (COOLANT_CP_TABLE_J_KGK[yakit],
                    COOLANT_CP_TABLE_BASIS[yakit])
        return COOLANT_CP_FALLBACK_J_KGK, COOLANT_CP_FALLBACK_BASIS

    def _coolant_cp(self):
        """(cp, künye) — çağrı anındaki ``cp_coolant_input``tan (tek çözüm)."""
        return self._resolve_coolant_cp(getattr(self, 'cp_coolant_input',
                                                None))

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
        # ÖH A2 sivi-sogutma (uc-kapi devri): kanonik cp KURUCUDA çözülür ve
        # künyesiyle tutulur (tek tanım COOLANT_CP_TABLE_J_KGK).
        self.coolant_cp_J_kgK, self.coolant_cp_source = \
            self._resolve_coolant_cp(v)
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
            self.optimal_mr_source = 'user input (of_max_isp)'
        v = self._override_val('of_max_thrust', 0.2, 20.0,
                               'O/F at maximum thrust')
        if v is not None:
            self.optimal_mr_thrust = v
            # P3B1-04: kullanıcı yazdıysa künye onu söyler — 'çözüldü' ile
            # 'kullanıcı yazdı' aynı yaprakta ayırt edilemiyordu.
            self.optimal_mr_thrust_source = 'user input (of_max_thrust)'
        self.of_scan_min = self._override_val('of_min', 0.2, 20.0, 'O/F minimum')
        self.of_scan_max = self._override_val('of_max', 0.2, 20.0, 'O/F maximum')
        if (self.of_scan_min is not None and self.of_scan_max is not None
                and self.of_scan_min >= self.of_scan_max):
            self._warn('warn.liquid.of_scan_band_invalid', 'warning')
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
        # 2026-07-22: çarpma burada YAPILMAZ — teslim verim zinciri tek yerde
        # (_finalize_performance_reference / _calculate_mixture_ratio_effects)
        # uygulanır; iki yerde uygulanırsa η_c* ÇİFT SAYILIR.
        eta_c = self._override_val(
            'combustion_efficiency',
            COMBUSTION_EFFICIENCY_INPUT_BAND_PERCENT[0],
            COMBUSTION_EFFICIENCY_INPUT_BAND_PERCENT[1],
            'Combustion efficiency', ' %')
        # P16B2-07: KESİR biçimli değer (0 < x <= 1) yüzde bandının dışına
        # düşer ve reddedilir. Reddin GEREKÇESİ adıyla söylenir; değer
        # SESSİZCE yüzdeye çevrilmez (kullanıcı gerçekten %0,97 demiş
        # olabilir ve o da reddedilecek bir girdidir).
        if eta_c is None:
            _ham_eta = self.overrides.get('combustion_efficiency')
            if _ham_eta not in (None, ''):
                try:
                    _f_eta = float(_ham_eta)
                except (TypeError, ValueError):
                    _f_eta = None
                if _f_eta is not None and 0.0 < _f_eta <= 1.0:
                    self._warn('warn.liquid.efficiency_unit_is_percent',
                               'warning', field='combustion_efficiency',
                               field_label_en='Combustion efficiency',
                               value=float(_f_eta),
                               as_percent=round(float(_f_eta) * 100.0, 3),
                               lo=COMBUSTION_EFFICIENCY_INPUT_BAND_PERCENT[0],
                               hi=COMBUSTION_EFFICIENCY_INPUT_BAND_PERCENT[1])
        self.eta_c_star = 1.0 if eta_c is None else eta_c / 100.0
        # ÖH defter P3B2-08 (D18): η_c*'ın KÜNYESİ de tek yerde kurulur.
        # Enjektör bloğu buna paralel ikinci bir sayı (enjektör tipinden
        # 0,95-0,99) üretip aynı adla yayımlıyordu; ölçüldü (once.json):
        # injection_system.combustion_efficiency = 0,98 'estimated from the
        # injector type (impinging)' ⟷ combustion_analysis 100,0 'not
        # supplied -> ideal energy release (1.000) assumed'. Aynı yanıt, aynı
        # büyüklük, iki değer ve iki çelişik hikâye; üstelik %2'lik fark
        # hiçbir hesaba girmiyordu.
        self.eta_c_star_source = (
            'user input (combustion efficiency)' if eta_c is not None
            else ('not supplied -> ideal energy release (1.000) assumed; '
                  'real engines deliver 0.92-0.99 (Sutton & Biblarz 9th ed., '
                  'Ch. 5). The injector type is NOT used to invent a c* '
                  'efficiency - HRMA does not model that link'))

        # --- hazne geometrisi ----------------------------------------------
        _ham_l_star = self._override_val(
            'characteristic_length', L_STAR_MIN_M, L_STAR_MAX_M,
            'Characteristic length L*', ' m')
        # P3B2-02: L*'ın KULLANICIDAN mı MODEL TABANINDAN mı geldiği
        # kaydedilir. Geometri çelişkisinde hükmü kimin verdiği buna bağlıdır:
        # kullanıcı yazdıysa çelişki fail-closed reddedilir, model tabanıysa
        # taban yükseltilip BEYAN edilir (ikisi de sessiz kalmaz).
        self.l_star_source = ('user input (characteristic_length)'
                              if _ham_l_star is not None else 'model default')
        # F2 (ÖH D18 fizik-a2): model tabanı artık TEK bir 1,2 m sayısı değil,
        # itici ÇİFTİNE anahtarlı SP-125 Tablo 4-1 bandının ORTASIDIR. Çift
        # tabloda yoksa genel aralık kullanılır ve bu SESSİZ KALMAZ.
        _alt, _ust, _l_kaynak = l_star_band_for_pair(
            getattr(self, 'fuel_type', None), getattr(self, 'oxidizer_type', None))
        self.l_star_band_m = (float(_alt), float(_ust))
        self.l_star_band_source = _l_kaynak
        if _ham_l_star is not None:
            self.L_star = _ham_l_star
            if not (_alt <= float(_ham_l_star) <= _ust):
                self._warn('warn.liquid.l_star_outside_pair_band', 'info',
                           l_star_m=round(float(_ham_l_star), 4),
                           band_low_m=round(float(_alt), 3),
                           band_high_m=round(float(_ust), 3),
                           pair=f'{getattr(self, "fuel_type", "?")}/'
                                f'{getattr(self, "oxidizer_type", "?")}')
        elif _l_kaynak == 'sp125_table_4_1_pair':
            self.L_star = 0.5 * (float(_alt) + float(_ust))
            self.l_star_source = (
                'SP-125 Table 4-1 propellant-pair band midpoint')
        else:
            # Çift tabloda YOK: genel aralığın içindeki model tabanı kalır,
            # ama künye "bu çift için çözülmüş bir değer değildir" der.
            self.L_star = L_STAR_DEFAULT_M
            self.l_star_source = (
                'model default (propellant pair not in SP-125 Table 4-1)')
            self._warn('warn.liquid.l_star_pair_not_tabulated', 'info',
                       pair=f'{getattr(self, "fuel_type", "?")}/'
                            f'{getattr(self, "oxidizer_type", "?")}',
                       l_star_m=float(L_STAR_DEFAULT_M),
                       band_low_m=float(L_STAR_GENERIC_BAND_M[0]),
                       band_high_m=float(L_STAR_GENERIC_BAND_M[1]))
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
        # Band TEK KAYNAKTAN (injector_design.USER_CD_RANGE): hibrit ayağı
        # aynı bandı kullanır, iki motor kullanıcıya farklı kapı açamaz.
        # Sayılar DEĞİŞMEDİ (0,20-1,0) — yalnız tanım tekleşti.
        self.injector_cd_input = self._override_val(
            'discharge_coefficient', USER_CD_RANGE[0], USER_CD_RANGE[1],
            'Discharge coefficient')
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
        # B4 (v2.6.27): KARAR burada verilir, KAYNAK da burada yazılır.
        # Üç durum ayrı ayrı beyan edilir çünkü kullanıcı açısından üçü ayrı
        # şeydir: (a) girdim kullanıldı, (b) hiç girmedim, varsayılan kullanıldı,
        # (c) girdim reddedildi (aralık dışı / tanınmayan seçenek) ve yerine
        # varsayılan kullanıldı. (c) durumunda 'kullanıcı girdi' demek YALAN
        # olurdu; eski davranış ikisini de sessizce aynı sayıya düşürüyordu.
        sf_raw = self.overrides.get('safety_factor')
        sf_val = self._override_val(
            'safety_factor', SAFETY_FACTOR_MIN, SAFETY_FACTOR_MAX,
            'Safety factor')
        if sf_val is not None:
            self.safety_factor = sf_val
            self.safety_factor_source = SAFETY_FACTOR_SOURCE_USER
        else:
            self.safety_factor = SAFETY_FACTOR_DEFAULT
            self.safety_factor_source = (
                SAFETY_FACTOR_SOURCE_REJECTED if sf_raw not in (None, '')
                else SAFETY_FACTOR_SOURCE_DEFAULT)
        mat_raw = self.overrides.get('chamber_material')
        mat_val = self._override_choice(
            'chamber_material', set(CHAMBER_MATERIAL_MAP), 'Chamber material')
        if mat_val is not None:
            self.chamber_material = mat_val
            self.chamber_material_source = CHAMBER_MATERIAL_SOURCE_USER
        else:
            self.chamber_material = CHAMBER_MATERIAL_DEFAULT
            self.chamber_material_source = (
                CHAMBER_MATERIAL_SOURCE_REJECTED if mat_raw not in (None, '')
                else CHAMBER_MATERIAL_SOURCE_DEFAULT)
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
        # ÖH D36 / LU-1: öğretici kip bayrağı; yalnız bu bayrakla
        # BURN_TIME_DEFAULT_S uygulanır (bkz. _burn_time).
        self.tutorial_defaults = _flag_true(
            self.overrides.get('use_tutorial_defaults'))
        self.feed_pressure_input_bar = self._override_val(
            'feed_pressure', 1.0, 1000.0, 'Feed pressure', ' bar')
        v = self._override_val('turbopump_efficiency', 20.0, 95.0,
                               'Turbopump efficiency', ' %')
        self.pump_efficiency = (PUMP_EFFICIENCY_DEFAULT if v is None
                                else v / 100.0)
        # ÖH defter P3B3-09'un kardeşi P3B3-08 (D18): pompa verimi künyesi
        # `_design_pump` içinde "'turbopump_efficiency' in self.overrides"
        # ile kuruluyordu — anahtarın VARLIĞINA bakıyor, değerin KABUL
        # EDİLİP EDİLMEDİĞİNE bakmıyordu. Ölçüldü (once.json, 25 kN gg):
        # turbopump_efficiency=150 ve 'abc' REDDEDİLİYOR (verim 75'te
        # kalıyor, warn.liquid.input_out_of_range ateşleniyor) ama künye
        # 'user input (turbopump efficiency)' diyordu — sayı doğru, BEYAN
        # yalandı. Künye artık kabul kararının KENDİSİNDEN doğar (safety_factor
        # ve generator_gas_temp için kurulmuş desenin aynısı).
        if v is not None:
            self.pump_efficiency_source = 'user input (turbopump efficiency)'
        elif 'turbopump_efficiency' in self.overrides and str(
                self.overrides.get('turbopump_efficiency')).strip() != '':
            self.pump_efficiency_source = (
                'the supplied turbopump efficiency was REJECTED (not a '
                'number, or outside the 20-95% band); the '
                f'{PUMP_EFFICIENCY_DEFAULT * 100:g}% default '
                'best-efficiency-point value is used instead - this figure '
                'does NOT come from what was supplied')
        else:
            self.pump_efficiency_source = 'default best-efficiency-point value'
        # ÖH defter P3B3-05: REDDEDİLEN girdi yayımlanan sayıyı değiştiriyordu.
        # Aşağıdaki iki alan için karar noktası (_solve_cycle_balance) anahtarın
        # VARLIĞINA bakıyordu ('generator_gas_temp' in self.overrides), değerin
        # KABUL EDİLİP EDİLMEDİĞİNE değil. Aralık dışı 99999 K girildiğinde
        # _override_val None döner, öznitelik genel varsayılana (1200 K) düşer
        # ve o dal YİNE ateşlenip çözücüye 1200 K DAYATIR. Ölçüldü (250 kN):
        # girdi yok -> TIT 1000 K / GG debisi 2,429 kg/s; REDDEDİLEN 99999 ->
        # TIT 1200 K / 1,976 kg/s (-%18,7). Kabul EDİLMİŞ olma durumu artık
        # ayrı bir bayrakta durur ve karar noktaları ONU okur (doktrin:
        # 'reddedilen girdiye sahip çıkılmaz', bkz. test_sivi_baglama_beyan).
        _tit = self._override_val(
            'generator_gas_temp', 400.0, 2500.0,
            'Gas generator temperature', ' K')
        self.turbine_inlet_temp_accepted = _tit is not None
        self.turbine_inlet_temp = (_tit if _tit is not None
                                   else GAS_GENERATOR_TEMP_DEFAULT_K)
        self.turbine_inlet_pressure_bar = self._override_val(
            'turbine_inlet_pressure', 1.0, 1000.0,
            'Turbine inlet pressure', ' bar')
        _tpr = self._override_val(
            'turbine_expansion_ratio', 1.2, 60.0,
            'Turbine expansion ratio')
        self.turbine_pressure_ratio_accepted = _tpr is not None
        self.turbine_pressure_ratio = (_tpr if _tpr is not None
                                       else TURBINE_PRESSURE_RATIO_DEFAULT)
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
        # Film soğutma debisi (% yakıt debisi).
        # Girilmediyse 0 -> film yok; AMA kullanıcı soğutma tipini
        # 'film_cooling' seçtiyse 0 dönmek seçimi ölü bırakıyordu (film
        # bloğunun beş yaprağı da sabit 0'dı). O durumda etiketli literatür
        # varsayılanı uygulanır ve kaynağı çıktıda bildirilir.
        v = self._override_val('film_cooling_percent', 0.0,
                               FILM_COOLING_PCT_MAX,
                               'Film cooling flow', ' %')
        if v is not None:
            self.film_cooling_percent = v
            self.film_cooling_percent_source = 'user input (film cooling flow)'
        elif self.cooling_type == 'film_cooling':
            self.film_cooling_percent = FILM_COOLING_PCT_DEFAULT
            self.film_cooling_percent_source = (
                f'not supplied -> {FILM_COOLING_PCT_DEFAULT:g}% of the fuel '
                'flow assumed because the cooling type is film cooling '
                '(typical 3-10%, Sutton & Biblarz 9th ed. Ch. 8; Huzel & '
                'Huang NASA SP-125 p. 117 cites about 3% for a typical case, '
                'no band)')
        else:
            self.film_cooling_percent = 0.0
            self.film_cooling_percent_source = (
                'not supplied and the cooling type is not film cooling '
                '-> no film coolant')
        # Basınçlandırma tipi seçimi (autogenous yalnız CH4/LH2 + LOX
        # turbopompalı konfigürasyonda sayısal olarak boyutlandırılır).
        self.pressurization_choice = self._override_choice(
            'pressurization_type', {'auto', 'autogenous', 'helium',
                                    'nitrogen'}, 'Pressurization type')
        # Derin kısma alt sınırı (% itki) — kısma taramasıyla karşılaştırılır.
        self.min_throttle_pct = self._override_val(
            'min_throttle', 5.0, 100.0, 'Minimum throttle', ' %')

        # --- girdi tutarlılık denetimleri -----------------------------------
        # Oda çapı / daralma oranı çakışması BURADA duyurulmaz: bu noktada d_t
        # henüz çözülmediğinden hangisinin öncelik alacağı bilinemez (aralık
        # dışı bir oda çapı reddedilip sıra daralma oranına geçebilir). Uyarı,
        # kararın gerçekten verildiği _chamber_diameter() içinde üretilir —
        # aksi hâlde kullanıcıya gerçekleşmeyen bir öncelik bildiriliyordu.
        if self.throat_diameter_input_m is not None:
            self._warn('warn.liquid.throat_diameter_is_output', 'info')

        # --- performans referansının SON hali -------------------------------
        # Tüm girdiler bağlandıktan sonra (genişleme oranı, lüle tipi, c*
        # verimi, L*) CEA çözümü motorun gerçek tasarım noktasında yenilenir
        # ve teslim verim zinciri uygulanır.
        self._finalize_performance_reference()

    def unwired_inputs(self):
        """Çözücünün BİLİNÇLİ olarak kullanmadığı form alanları.

        UI bu listeyi 'not used in solver' etiketi için okur. Liste kod
        gerçeğidir: buradaki bir alan bağlanınca listeden çıkarılmalıdır.

        Ölçüt (2026-07-29 beyan denetimi): beyan edilen bir alan hiçbir
        FİZİKSEL büyüklüğü oynatmamalıdır. Alanın kendisi hakkında rapor
        üreten düğümler (input_warnings, girilen değerin yankısı, girilen
        değere ilişkin bir yargı) beyanı bozmaz — bunlar zaten 'değeriniz
        kullanılmadı' demenin biçimleridir. tests/test_liquid_input_wiring.py
        bu kuralı iki yönlü ölçer.

        NOT (self=None ile çağrılabilir): tests/test_liquid_unwired_ui.py
        listeyi motor kurmadan ``unwired_inputs(None)`` ile okur. Bu yüzden
        koşullu dallar yalnız ``getattr`` ile durum sorgular, metot çağırmaz.
        """
        # Daralma oranı KOŞULLU beyan edilir. Motor onu gerçekten kullanır —
        # ama yalnız oda çapı verilmediğinde. liquid.html her koşuda oda çapı
        # gönderdiğinden arayüzdeki alan pratikte ölüdür; koşulu bilmeden
        # 'ölü' demek de yanlış olurdu (API/proje yüklemesinde canlı).
        # Kaynak kararını _chamber_diameter() yazar, biz yalnız okuruz.
        comparison = [
            'throat_diameter', 'fuel_injection_velocity',
            'oxidizer_injection_velocity', 'fuel_orifice_diameter',
            'oxidizer_orifice_diameter', 'target_thrust_to_weight',
        ]
        # Türbin giriş basıncı KOŞULLU beyan edilir. Öncelik doğrudan girilen
        # genişleme oranındadır; o VARSA giriş basıncı yalnız karşılaştırılır
        # ('warn.liquid.turbine_pr_inconsistent'). Genişleme oranı YOKSA
        # basınç oranı giriş basıncından çözülür ve alan gerçekten canlıdır
        # (bkz. _solve_cycle_balance). liquid.html her koşuda genişleme oranı
        # gönderdiğinden arayüzde alan pratikte karşılaştırmalıdır.
        # Basınç beslemeli çevrimde türbin yoktur: karşılaştırma YAPILMAZ,
        # alan 'karşılaştırma' diye beyan edilmez; gönderildiyse
        # ``inputs_not_used`` (TURBINE_INPUT_UNUSED_REASON) söyler.
        _ov = getattr(self, 'overrides', None) or {}
        _turbinsiz = (getattr(self, 'engine_cycle', '')
                      == PRESSURE_FED_CYCLE_NAME)
        if (not _ov or 'turbine_expansion_ratio' in _ov) and not _turbinsiz:
            comparison.append('turbine_inlet_pressure')
        if (getattr(self, '_chamber_diameter_source', None) == 'chamber_diameter'
                and getattr(self, 'contraction_ratio_input', None) is not None):
            comparison.append('contraction_ratio')
        return {
            # kayıt/etiket alanları (fiziksel çözücü girdisi değil)
            'informational': [
                'fuel_freezing_point', 'oxidizer_freezing_point',
                'oxidizer_boiling_point', 'fuel_heat_combustion',
                # Soğutucu iletkenliği yalnız 1B istasyon marşında (RegenCooling
                # kendi özellik tablosuyla) kullanılır; Bartz zincirinde girdi
                # değildir, bu yüzden burada bildirilir.
                'fuel_thermal_conductivity',
                # Yakıt kaynama noktası hiçbir şeyi BOYUTLANDIRMAZ: çözücü
                # soğutucu çıkış sıcaklığını kendi hesaplar, kaynama noktası
                # yalnız 'warn.liquid.coolant_exit_above_boiling' sınır
                # denetiminde okunur. Kanal sayısı/debi ona göre iterasyona
                # sokulmadığı için burada bildirilir (2026-07-29 ölçümü:
                # 500 K -> 800 K değişimi hiçbir sayıyı oynatmıyor).
                'fuel_boiling_point',
                'stoichiometric_of', 'throttling_of_strategy',
                'stability_margin', 'ignition_system', 'engine_mount',
                'vibration_environment', 'acoustic_level', 'gimbal_range',
                'actuator_response', 'storage_duration',
                'contamination_sensitivity', 'test_requirements',
                'ground_support', 'hazard_classification', 'altitude_range',
                'temp_range_min', 'temp_range_max',
            ],
            # geçici rejim: bu sürümün tasarım-noktası çözücüsünde modellenmez
            #
            # v2.6.26 — 'min_throttle' BU LİSTEDEN ÇIKARILDI: beyan çürümüştü.
            # Alan gerçekten kullanılıyor — kısma haritasında
            # `min_throttle_pct` ve `min_throttle_chug_risk` üretiyor
            # (ölçüldü: 20 girilince ikisi de değişiyor). Bekçi bunu
            # "beyanlı ama canlı" diye yakaladı. Yanlış beyan, beyansızlıktan
            # kötüdür: kullanıcıya "bu alan kullanılmıyor" diyorduk, oysa
            # onun girdisiyle bir risk hükmü veriliyordu.
            #
            # KALAN EKSİK (ayrı iş): kısma tarama ızgarası
            # THROTTLE_SCAN_FRACTIONS (0,40-1,00) kullanıcının min_throttle
            # değerine UZANMIYOR. Yani "en derin kısmada chug riski" hükmü
            # %40'ta değerlendirilmiş oluyor; kullanıcı %20 girse bile.
            'transient_not_modelled': [
                'startup_sequence', 'engine_start_time',
                'engine_shutdown_time', 'throttle_response',
                'restart_capability', 'chill_down_time',
            ],
            # karşılaştırma amaçlı: çözücü kendi değerini hesaplar
            'reported_for_comparison': comparison,
        }

    def _declare_turbine_inputs_unused(self):
        """Türbinsiz çevrimde GÖNDERİLMİŞ türbin alanlarını beyan eder.

        Yalnız gövdede fiilen bulunan alan beyan edilir (gönderilmeyen alan
        hakkında hüküm yok). Gönderilen değer JSON'a yazılabilir biçimde
        yankılanır: sonlu sayı ``float``, başka her şey kısaltılmış tip/metin
        (sonlu olmayan sayı ``Infinity``/``NaN`` belirteci olarak basılmaz).
        """
        beyanlar = self._declare_cycle_inputs_unused(
            TURBINE_INPUT_FIELDS, TURBINE_INPUT_UNUSED_REASON,
            "'{field}' was supplied but the pressure-fed cycle has "
            'no turbine: the field was not evaluated and changed no '
            'result. It is read only in turbopump cycles.')
        for b in beyanlar:
            self._warn('warn.liquid.turbine_input_not_used_pressure_fed',
                       'info', field=b['field'])
        self._turbine_inputs_unused = beyanlar
        return beyanlar

    def _declare_turbopump_inputs_unused(self):
        """Basınç beslemede GÖNDERİLMİŞ turbopompa alanlarını beyan eder.

        ÖH A2 sivi-sogutma · 7. tur (TBA devri): ``turbopump_efficiency`` ve
        ``generator_gas_temp`` bu çevrimde hiçbir yaprağı oynatmıyor (ölçüm
        ``TURBOPUMP_INPUT_FIELDS`` yorumunda). Türbin alanlarıyla aynı yankı
        kuralı ve ayrı gerekçe adı; beyan YALNIZ ``inputs_not_used``
        kanalındadır, uyarı listesine eklenmez: form bu iki alanı basınç
        beslemede zaten göndermiyor (liquid.html ``LIQ_CYCLE_UNREAD_FIELDS``)
        ve basınç beslemenin uyarı kümesi mevcut bir bekçiyle kilitli
        (tests/test_d37_sivi_kati_a1.py::TestCevrimFormu::
        test_basinc_beslemede_dort_alan_hicbir_sayiyi_oynatmiyor — ölçüldü:
        uyarı basılınca KIRMIZI). Uyarı kanalı ayrı karar (rapor devri).
        """
        beyanlar = self._declare_cycle_inputs_unused(
            TURBOPUMP_INPUT_FIELDS, TURBOPUMP_INPUT_UNUSED_REASON,
            "'{field}' was supplied but the pressure-fed cycle has no "
            'turbopump (no pump, no turbine): the field was not evaluated '
            'and changed no result. It is read only in turbopump cycles.')
        self._turbopump_inputs_unused = beyanlar
        return beyanlar

    def _declare_cycle_inputs_unused(self, fields, reason, message):
        """Çevrimin okumadığı, gövdede fiilen bulunan alanları beyan eder.

        ``message`` içindeki ``{field}`` alan adıyla doldurulur. Yankı kuralı
        (fail-closed, JSON güvenli) türbin ve turbopompa beyanında ortaktır.
        Uyarıyı çağıran basar (kod literal kalır: i18n bekçisi parametreleri
        AST ile okuyor).
        """
        overrides = getattr(self, 'overrides', None) or {}
        beyanlar = []
        for field in fields:
            raw = overrides.get(field)
            if raw is None or raw == '':
                continue
            submitted = None
            if not isinstance(raw, bool):
                try:
                    _f = float(raw)
                    if np.isfinite(_f):
                        submitted = _f
                except (TypeError, ValueError):
                    submitted = None
            if submitted is None:
                if isinstance(raw, float):
                    submitted = repr(raw)          # 'nan' / 'inf'
                elif isinstance(raw, str):
                    submitted = raw[:80]
                else:
                    submitted = type(raw).__name__
            beyanlar.append({
                'field': field,
                'submitted': submitted,
                'used_by_model': None,
                'reason': reason,
                'message': message.replace('{field}', field),
            })
        return beyanlar

    def _declare_unread_inputs(self, results):
        """Gönderilmiş ama çözücünün OKUMADIĞI gövde alanlarını beyan eder.

        Yol haritası B4 (v2.6.27). ``unwired_inputs()`` ARAYÜZ alanlarının
        listesidir ve koşudan bağımsızdır; bu ise BU KOŞUDA fiilen gönderilmiş
        bir değerin yok sayıldığını ÖLÇEREK söyler. İkisi karışmasın diye ayrı
        adreslerde durur.

        Şema, hibrit rotasının ``inputs_not_used`` beyanıyla birebir aynıdır
        (``field``, ``submitted``, ``used_by_model``, ``reason``, ``message``);
        ek olarak ``use_instead`` alanı kullanıcının GERÇEK girdi adını söyler
        — "girdiniz kullanılmadı" demek, doğrusunu söylemeden yarım kalır.

        Ölçüm kuralı: gönderilen sayı ile sonuçta fiilen duran sayı
        karşılaştırılır. Eşitlerse hiçbir şey beyan edilmez (yanlış alarm da
        bir yalandır). Sayıya çevrilemeyen ya da sonuçta karşılığı bulunmayan
        alan için de sessiz kalınır: ölçemediğimiz şey hakkında hüküm
        vermeyiz.

        Returns:
            Beyan listesi (koşullar sağlanmadıysa boş liste).
        """
        beyanlar = []
        overrides = getattr(self, 'overrides', None) or {}
        for field, spec in LIQUID_UNREAD_INPUT_FIELDS.items():
            raw = overrides.get(field)
            if raw is None or raw == '':
                continue
            try:
                submitted = float(raw)
            except (TypeError, ValueError):
                continue
            used = results.get(spec['result_key'])
            try:
                used_value = float(used)
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(submitted) and np.isfinite(used_value)):
                continue
            if abs(submitted - used_value) <= (
                    LIQUID_INPUT_ECHO_REL_TOL * abs(used_value)):
                continue
            use_instead = spec['use_instead']
            beyanlar.append({
                'field': field,
                'submitted': submitted,
                'used_by_model': used_value,
                'reason': spec['reason'],
                'use_instead': use_instead,
                'message': (
                    f"'{field}' was supplied as {submitted:g} but the liquid "
                    f'solver does not read that field; the analysis and every '
                    f'echo of this name in the response carry the solved '
                    f"value {used_value:g}. The input field for this quantity "
                    f"is '{use_instead}'."),
            })
            self._warn('warn.liquid.input_field_not_read', 'warning',
                       field=field, use_instead=use_instead,
                       submitted=float(submitted), used=float(used_value))
        # Türbinsiz çevrimde gönderilen türbin alanları (beyan
        # _analyze_detailed_feed_system'de ölçülüp burada yayımlanır).
        beyanlar.extend(getattr(self, '_turbine_inputs_unused', None) or [])
        # 7. tur: aynı çevrimde gönderilen turbopompa alanları.
        beyanlar.extend(getattr(self, '_turbopump_inputs_unused', None) or [])
        return beyanlar

    # ------------------------------------------------------------------
    # Geometri / malzeme yardımcıları (tek doğruluk kaynağı)
    # ------------------------------------------------------------------
    def _l_star(self):
        """Karakteristik uzunluk L* [m] — kullanıcı girdisi ya da taban."""
        return getattr(self, 'L_star', L_STAR_DEFAULT_M)

    def _chamber_diameter(self):
        """Yanma odası iç çapı [m] — kullanıcı girdisi > daralma oranı > taban.

        Önceliği kim kazandıysa ``_chamber_diameter_source`` alanına yazılır.
        unwired_inputs() beyanı ORADAN üretir: karar bir yerde verilip beyan
        başka bir yerde tahmin edilirse rozet yalan söyler (2026-07-29
        denetimi: form her koşuda oda çapını da gönderdiğinden daralma oranı
        fiilen ölüydü, ama hiçbir yerde bildirilmiyordu).
        """
        d_t = getattr(self, 'd_t', None)
        d_t_solved = d_t is not None and np.isfinite(d_t) and d_t > 0
        if not d_t_solved:
            d_t = 0.03
        if getattr(self, 'chamber_diameter_input_m', None) is not None:
            d_c = self.chamber_diameter_input_m
            cr = (d_c / d_t) ** 2
            if not (CONTRACTION_RATIO_MIN <= cr <= CONTRACTION_RATIO_MAX):
                self._warn('warn.liquid.contraction_ratio_out_of_band',
                           'warning',
                           d_c_mm=round(float(d_c) * 1000.0, 1),
                           cr=round(float(cr), 1),
                           d_t_mm=round(float(d_t) * 1000.0, 1),
                           cr_min=float(CONTRACTION_RATIO_MIN),
                           cr_max=float(CONTRACTION_RATIO_MAX))
            else:
                # Oda çapı öncelik aldı: kullanıcı ayrıca daralma oranı
                # girdiyse o değer hesaba GİRMİYOR, sessiz kalınmaz.
                if getattr(self, 'contraction_ratio_input', None) is not None:
                    self._warn(
                        'warn.liquid.chamber_diameter_overrides_contraction',
                        'info')
                # Kaynak yalnız d_t GERÇEKTEN çözülmüşken kaydedilir; erken
                # (0.03 m varsayılanlı) çağrılar beyanı kirletmemeli.
                if d_t_solved:
                    self._chamber_diameter_source = 'chamber_diameter'
                return self._chamber_diameter_floor(d_c, 'chamber_diameter',
                                                    d_t_solved)
        if getattr(self, 'contraction_ratio_input', None) is not None:
            if d_t_solved:
                self._chamber_diameter_source = 'contraction_ratio'
            return self._chamber_diameter_floor(
                d_t * np.sqrt(self.contraction_ratio_input),
                'contraction_ratio', d_t_solved)
        # F2 (ÖH D18 fizik-a2): TÜREV yol artık sabit bir d_c/d_t = 3,5
        # (ε_c = 12,25) oranı DEĞİL, boğaz çapına bağlı kestirimdir. Eski
        # sabit, Huzel & Huang Tablo 1-3 bandının (1,3-6) 2,04 katıydı ve
        # konverjan koninin tek başına L* = 12,088·d_t tutmasına yol açıyordu.
        eps_c, eps_ham, kirpildi = contraction_ratio_estimate(d_t)
        if d_t_solved:
            self._chamber_diameter_source = 'default'
            self._contraction_ratio_estimate = (float(eps_c), float(eps_ham),
                                                bool(kirpildi))
            if kirpildi and not getattr(self, '_cr_clip_warned', False):
                self._cr_clip_warned = True
                self._warn('warn.liquid.contraction_ratio_estimate_clipped',
                           'info', raw=round(float(eps_ham), 3),
                           used=round(float(eps_c), 3),
                           band_low=float(CONTRACTION_RATIO_CORRELATION_BAND[0]),
                           band_high=float(CONTRACTION_RATIO_CORRELATION_BAND[1]),
                           d_t_mm=round(float(d_t) * 1000.0, 2))
            self._warn_contraction_band(eps_c)
        return self._chamber_diameter_floor(
            d_t * float(np.sqrt(eps_c)), 'default', d_t_solved)

    def _warn_contraction_band(self, eps_c):
        """Çevrim ailesinin daralma oranı bandı dışındaysa uyar (H&H Böl. IV).

        Pompa beslemeli 1,3-2,5; basınç beslemeli 2-5. Bant AŞILMAZ sınır
        değildir (hüküm verilmez), yalnız tasarımcıya söylenir.
        """
        if getattr(self, '_cr_band_warned', False):
            return
        basinc_besleme = getattr(self, 'engine_cycle', '') == 'pressure_fed'
        alt, ust = (CONTRACTION_RATIO_PRESSURE_FED_BAND if basinc_besleme
                    else CONTRACTION_RATIO_PUMP_FED_BAND)
        if alt <= float(eps_c) <= ust:
            return
        self._cr_band_warned = True
        self._warn('warn.liquid.contraction_ratio_outside_family_band',
                   'info', cr=round(float(eps_c), 3),
                   band_low=float(alt), band_high=float(ust),
                   family=('pressure-fed' if basinc_besleme
                           else 'turbopump-fed'))

    def _contraction_ratio_source(self):
        """Daralma oranının KAYNAK künyesi (tek tanım noktası)."""
        if getattr(self, 'chamber_diameter_input_m', None) is not None:
            return 'user input (chamber_diameter)'
        if getattr(self, 'contraction_ratio_input', None) is not None:
            return 'user input (contraction_ratio)'
        if getattr(self, '_chamber_diameter_source', None) == 'model_floor':
            return 'model floor (chamber diameter clamped)'
        return 'estimated from throat diameter'

    def _contraction_ratio_basis(self):
        """Daralma oranının BEYAN metni — kestirimse kaynağın belirsizliğiyle."""
        kaynak = self._contraction_ratio_source()
        if kaynak.startswith('user input'):
            return (f'{kaynak}: the user hypothesis governs; the H&H SP-125 '
                    'bands (turbopump-fed 1.3-2.5, pressure-fed 2.0-5.0, '
                    'Table 1-3 overall 1.3-6.0) are reported as warnings '
                    'only, never applied as a clamp.')
        if kaynak.startswith('model floor'):
            return ('the derived chamber diameter fell below the '
                    f'{CHAMBER_DIAMETER_MIN_M * 1000.0:.0f} mm model floor, so '
                    'the published ratio follows the floored diameter, not '
                    'the correlation. ' + CONTRACTION_RATIO_CORRELATION_BASIS)
        kestirim = getattr(self, '_contraction_ratio_estimate', None)
        ek = ''
        if kestirim:
            ek = (f' Raw correlation value {kestirim[1]:.3f}'
                  + (f', clipped to {kestirim[0]:.3f}.' if kestirim[2]
                     else ' (inside the band, not clipped).'))
        return CONTRACTION_RATIO_CORRELATION_BASIS + ek

    def _chamber_slenderness_status(self, chamber_length, chamber_diameter):
        """L_c/D_c pratik bandı hükmü — bant YORUM olduğu için 'uyarı'dır.

        Ölçüldü (D18 fizik-a2 önce koşumu): sabit ε_c = 12,25 tabanıyla beş
        koşumun BEŞİNDE de L_c/D_c < 0,5 çıkıyordu (500 kN'da 0,115; 853 mm
        çapında, 98 mm boyunda bir gözleme). Oran artık yayımlanır ve bandın
        dışına çıkarsa SESSİZ KALINMAZ.
        """
        if not chamber_diameter:
            return None
        oran = float(chamber_length) / float(chamber_diameter)
        alt, ust = CHAMBER_LENGTH_DIAMETER_BAND
        if oran < alt:
            durum = 'below_band'
        elif oran > ust:
            durum = 'above_band'
        else:
            return 'in_band'
        if not getattr(self, '_slenderness_warned', False):
            self._slenderness_warned = True
            self._warn('warn.liquid.chamber_slenderness_out_of_band',
                       'warning', ratio=round(oran, 4),
                       band_low=float(alt), band_high=float(ust),
                       l_c_mm=round(float(chamber_length) * 1000.0, 1),
                       d_c_mm=round(float(chamber_diameter) * 1000.0, 1))
        return durum

    def _chamber_diameter_floor(self, d_c, kaynak, d_t_solved):
        """50 mm model tabanı — KULLANICI girdisini EZMEZ (P3B1-03, ÖH D15).

        Ölçüldü (once.json, 500 N / 10 bar RP-1/LOX): kabul bandı İÇİNDEKİ
        dört ayrı girdi (chamber_diameter=30, =40, contraction_ratio=2,0,
        =4,0) bit-aynı geometriyi veriyordu — dördü de 50,000 mm / cr 4,5066,
        ve 2 girdi uyarısının hiçbiri kırpmadan söz etmiyordu. Yani kullanıcı
        formu dolduruyor, sayı hiç değişmiyor, üstelik ``_chamber_diameter_
        source`` hâlâ 'chamber_diameter' diyordu: kırpmada kullanıcı GİRDİSİ
        hükmetmemiştir, künye yalan söylüyordu. Kırpma 100 N - 1500 N
        bandının tamamını, yani ``liquid.html``in reklam ettiği
        "Small thrusters: 10-1000N" bandını komple yutuyordu.

        Yeni kural:
        * AÇIK kullanıcı girdisi (chamber_diameter / contraction_ratio)
          EZİLMEZ. Değer 50 mm model tabanının altındaysa uyarı yayımlanır
          (bant beyanı) ama sayı kullanıcının verdiği gibi kalır.
        * Yalnız TÜREV (default) yolda taban uygulanır — orada ezilen bir
          kullanıcı hükmü yok — ve uygulandığı zaman da sessiz kalınmaz.
        * Boğazdan dar bir hazne bir hazne değildir: d_c <= d_t fail-closed
          reddedilir (sayı uydurulmaz).
        """
        d_c = float(d_c)
        d_t = float(getattr(self, 'd_t', 0.0) or 0.0)
        kullanici_hukmu = kaynak in ('chamber_diameter', 'contraction_ratio')
        if d_t_solved and d_t > 0.0 and d_c <= d_t:
            self._warn('warn.liquid.chamber_diameter_below_throat', 'critical',
                       d_c_mm=round(d_c * 1000.0, 3),
                       d_t_mm=round(d_t * 1000.0, 3), source=kaynak)
            raise ValueError(
                "Chamber diameter %.3f mm is not larger than the throat "
                "diameter %.3f mm (source: %s): a combustion chamber narrower "
                "than its own throat is not a chamber, and HRMA does not "
                "silently enlarge it." % (d_c * 1000.0, d_t * 1000.0, kaynak))
        if d_c >= CHAMBER_DIAMETER_MIN_M:
            return d_c
        if kullanici_hukmu:
            if d_t_solved and not getattr(self, '_chamber_floor_warned', False):
                self._chamber_floor_warned = True
                self._warn('warn.liquid.chamber_diameter_below_model_floor',
                           'warning', d_c_mm=round(d_c * 1000.0, 3),
                           floor_mm=round(CHAMBER_DIAMETER_MIN_M * 1000.0, 1),
                           source=kaynak)
            return d_c
        if d_t_solved and not getattr(self, '_chamber_floor_warned', False):
            self._chamber_floor_warned = True
            self._warn('warn.liquid.chamber_diameter_floor_applied', 'warning',
                       derived_mm=round(d_c * 1000.0, 3),
                       floor_mm=round(CHAMBER_DIAMETER_MIN_M * 1000.0, 1))
            self._chamber_diameter_source = 'model_floor'
        return CHAMBER_DIAMETER_MIN_M

    def _contraction_ratio(self):
        """Daralma oranı A_c/A_t (hazne çapıyla birebir tutarlı)."""
        d_t = getattr(self, 'd_t', 0.03)
        return (self._chamber_diameter() / d_t) ** 2

    def _burn_time(self):
        """(yanma_süresi [s] ya da None, kaynak künyesi) — TEK karar yeri.

        ÖH D36 / LU-1: üç hâl, üçü de adıyla —
          * kullanıcı ``max_burn_duration`` verdi -> (değer, USER)
          * vermedi ama ``use_tutorial_defaults`` açık -> (300 s, TUTORIAL)
          * vermedi -> (None, 'not_supplied'); varsayım YOK, çağıran her
            tüketici None'ı görünce kendi bloğunu yayımlamaz (fail-closed).
        Eski ``'assumed 300 s burn'`` dalı kaldırıldı (gerekçe modül
        sabitlerinin üstünde).
        """
        if getattr(self, 'burn_time_input', None) is not None:
            return self.burn_time_input, BURN_TIME_SOURCE_USER
        if getattr(self, 'tutorial_defaults', False):
            return BURN_TIME_DEFAULT_S, BURN_TIME_SOURCE_TUTORIAL
        return None, BURN_TIME_SOURCE_NOT_SUPPLIED

    def _safety_factor_source(self):
        """Hazne emniyet katsayısının KAYNAK künyesi (tek tanım noktası).

        Karar ``_apply_overrides`` içinde verilir; burada yalnız okunur.
        Öznitelik yoksa (kurucu dışı bir yoldan gelen nesne) beyan yine de
        varsayılanı söyler — sessiz kalmaz.
        """
        return getattr(self, 'safety_factor_source',
                       SAFETY_FACTOR_SOURCE_DEFAULT)

    def _chamber_material_source(self):
        """Hazne MALZEME SEÇİMİNİN kaynak künyesi (tek tanım noktası).

        DİKKAT: ``materials_db`` kaydındaki ``source`` alanıyla karıştırılmaz.
        O, malzeme ÖZELLİKLERİNİN literatür künyesidir (hangi el kitabından
        geldiği); bu ise malzemeyi KİMİN seçtiğidir (kullanıcı mı, varsayılan
        mı). İkisi ayrı sorudur ve çıktıda ayrı adlarla durur.
        """
        return getattr(self, 'chamber_material_source',
                       CHAMBER_MATERIAL_SOURCE_DEFAULT)

    def _material_record(self):
        """(malzeme kaydı, kanonik ad) — merkezi materials_db'den."""
        from hrma.data.materials_db import get_material_safe
        key = CHAMBER_MATERIAL_MAP.get(
            getattr(self, 'chamber_material', CHAMBER_MATERIAL_DEFAULT),
            getattr(self, 'chamber_material', CHAMBER_MATERIAL_DEFAULT))
        try:
            return get_material_safe(key)
        except KeyError:
            self._warn('warn.liquid.chamber_material_unknown', 'warning',
                       material=str(key),
                       fallback=str(CHAMBER_MATERIAL_DEFAULT))
            # Kullanılan malzeme kullanıcınınki DEĞİL: künye de öyle demeli
            # (kaynak, kararın verildiği yerde güncellenir).
            self.chamber_material_source = CHAMBER_MATERIAL_SOURCE_REJECTED
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

    def _supercritical_march_applies(self):
        """Süperkritik istasyon marşının (``_solve_supercritical_regen``)
        koştuğu yol: rejeneratif + metan/LH2.

        Denetçi Ş6/A7 (4. tur): kanal tabanı cidarının seçimi
        (``_channel_base_wall_thickness``) ile marşın çağrı kapısı İKİ ayrı
        satır içi yüklemdi; biri değişince (ör. metan film soğutmada liner)
        sığma ölçütü marşın iletmediği bir cidara bakardı. Tek yüklem budur;
        iki yer de bunu çağırır.
        """
        return bool(self.cooling_type == 'regenerative'
                    and self.fuel_type in ('methane', 'lh2'))

    def _channel_base_wall_thickness(self):
        """(t_sıcak_cidar [m], künye) — kanal TABANININ gaz yüzeyinden uzaklığı.

        ÖH A2 sivi-sogutma · F-17. Sığma ölçütünün yarıçapı r_boğaz + t'dir
        (``regen_cooling.channel_fit_limit``). t, bu yakıt yolunda soğutma
        modelinin ısıyı İLETTİĞİ sıcak cidardır — başka bir sayı seçilirse
        motorun kanal sayısı ile aynı yanıttaki istasyon marşının kendi
        sığma denetimi iki ayrı geometriye bakar (F-17'nin kapattığı kusur):

        * rejeneratif + metan/LH2: süperkritik marş ``REGEN_LINER_THICKNESS_M``
          liner'ı üzerinden iletir (``_solve_supercritical_regen``);
        * diğer yollar: hazne cidarı (``_chamber_wall_thickness_m``) — RP-1
          istasyon marşı ``thermal_protection``da bu cidarla koşar; bu yolda
          modelin ayrı bir liner'ı YOKTUR (beyan künyede).
        """
        if self._supercritical_march_applies():
            return float(REGEN_LINER_THICKNESS_M), (
                'regenerative liner (hot-gas wall) thickness '
                f'{REGEN_LINER_THICKNESS_M * 1e3:g} mm: the wall the '
                'supercritical station march of this fuel conducts through '
                '(REGEN_LINER_THICKNESS_M)')
        return float(self._chamber_wall_thickness_m()), (
            'chamber wall thickness (structural_analysis.chamber_structure.'
            'wall_thickness): on this path the model has no separate liner, '
            'the channels sit on the drawn chamber wall and the RP-1 station '
            'march conducts through that same wall')

    def _cooling_channel_geometry(self):
        """Kanal sayısı ve kesiti.

        ÖH A2 sivi-sogutma · F-17 (CW-F2b + CW-F3): kanal sayısı artık TEK
        sığma ölçütünden (``regen_cooling.channel_fit_limit``):
        N·(w + s) <= 2·pi·(r_boğaz + t_sıcak_cidar) — kanal TABANI çevresi
        (NASA SP-8087 s. 1/26/58: frezeli kanallar sıcak cidarın dış yüzünde).
        Kullanıcı sayı vermezse N = n_max (HRMA boyutlandırır; Berke §9 ve
        §24.1: form ön-dolgusu 80 kalktı). Kullanıcı sayısı sığmıyorsa sayı
        yine kullanıcınındır ama sığmadığı ADIYLA yayımlanır
        (``channel_count_fit.status = 'does_not_fit'`` + kritik uyarı);
        sığmayan N ile hesaplanan hidrolik sayılarının None'a çevrilmesi bu
        kulvarda yapılmadı (DEVİR — yedi tüketici; rapor).

        Eski ölçüt ``n = floor(pi·D_boğaz / (w + land))`` (iç gaz çevresi)
        ile regen modülündeki kaburgasız dış çevre ölçütü aynı geometride
        farklı hüküm veriyordu; ikisi de söküldü.

        Kesit: burada dönen değerler BAŞLANGIÇ değerleridir. Genişlik gerçekten
        sabittir (``COOLING_CHANNEL_WIDTH_BASIS``); DERİNLİK ise çağıran
        tarafında hız hedefine göre büyütülebilir
        (``COOLING_CHANNEL_HEIGHT_BASIS`` + ``channel_height_auto_sized``).
        İkisi tek bir beyanla anlatılamaz, bu yüzden iki ayrı metin taşınır.
        """
        width = COOLING_CHANNEL_WIDTH_DEFAULT_M
        height = COOLING_CHANNEL_HEIGHT_DEFAULT_M
        # Bağlayıcı eksenel kesit BOĞAZDIR (en küçük gaz yarıçapı).
        d_ref = getattr(self, 'd_t', None) or self._chamber_diameter()
        t_cidar, t_kunye = self._channel_base_wall_thickness()
        uygunluk = channel_fit_limit(float(d_ref) / 2.0, t_cidar, width,
                                     COOLING_CHANNEL_LAND_DEFAULT_M)
        n_max = int(uygunluk['n_max'])
        n_geom = int(min(max(n_max, COOLING_CHANNEL_COUNT_MIN),
                         COOLING_CHANNEL_COUNT_MAX))
        # Denetçi Ş4 (4. tur, ana model kararı: fail-closed). Kullanıcı sayı
        # vermediğinde HRMA boyutlandırır; boğaza HRMA'nın en az
        # COOLING_CHANNEL_COUNT_MIN kanalı bile sığmıyorsa eskiden n_geom bu
        # tabana KIRPILIYOR (uydurma N = 4 > n_max), künye "sized by HRMA",
        # hidrolik beyan ve uyarı "you entered / girilen" diyordu (ölçüldü:
        # metan/LOX 100 N / 100 bar, alan boş → N 4, n_max 3). Artık kanal
        # sayısı YAYIMLANMAZ, ceket hidroliği hesaplanmaz, künye nedenini
        # söyler.
        kullanici_n = getattr(self, 'cooling_channels_input', None) is not None
        boyutlanamadi = bool(not kullanici_n
                             and n_max < COOLING_CHANNEL_COUNT_MIN)
        if kullanici_n:
            n = int(self.cooling_channels_input)
            source = 'user input'
        elif boyutlanamadi:
            n = None
            source = (
                "NOT sized: HRMA's minimum of "
                f'{COOLING_CHANNEL_COUNT_MIN} channels does not fit this '
                f'throat at the channel base (at most {n_max} fit), see '
                'channel_count_fit; no channel count is published')
        else:
            n = n_geom
            source = ('sized by HRMA: the channel fit limit at the channel '
                      'base (throat radius + hot-wall thickness), see '
                      'channel_count_fit')
        sigiyor = bool(n is not None and n <= n_max)
        # Ceketi olmayan soğutma tiplerinde (ablatif/ışınımsal) kanal yoktur;
        # sığmama hükmü de yoktur (eskiden bu uyarı ablatif koşuda da
        # basılıyordu — form 80'i her tipte gönderiyordu). Denetçi Ş6/D11
        # (3. tur): dump soğutmada ceket MODELLENMİYOR (OH-D25-25;
        # cooling_channels 0, channel_count_fit None yayımlanır) — sığma
        # hükmü de o blokla aynı kapıdan geçer: yayımlanmayan bir n_max/c_ref
        # ile kritik uyarı basılmaz.
        ceket_var = self.cooling_type in ('regenerative', 'film_cooling')
        if boyutlanamadi and ceket_var:
            self._warn('warn.liquid.cooling_channels_min_count_does_not_fit',
                       'critical', n_min=int(COOLING_CHANNEL_COUNT_MIN),
                       width_mm=round(float(width) * 1000.0, 2),
                       land_mm=round(float(COOLING_CHANNEL_LAND_DEFAULT_M)
                                     * 1000.0, 2),
                       c_ref_mm=round(float(
                           uygunluk['reference_circumference_m']) * 1000.0, 1),
                       n_max=n_max)
        elif not sigiyor and ceket_var:
            self._warn('warn.liquid.cooling_channels_exceed_fit_limit',
                       'critical', n=int(n),
                       width_mm=round(float(width) * 1000.0, 2),
                       land_mm=round(float(COOLING_CHANNEL_LAND_DEFAULT_M)
                                     * 1000.0, 2),
                       need_mm=round(float(n * uygunluk['pitch_m'])
                                     * 1000.0, 1),
                       c_ref_mm=round(float(
                           uygunluk['reference_circumference_m']) * 1000.0, 1),
                       n_max=n_max)
        self._channel_count_fit = {
            'status': ('not_sized' if boyutlanamadi
                       else ('fits' if sigiyor else 'does_not_fit')),
            'n_used': None if n is None else int(n),
            'n_max': n_max,
            'n_min': int(COOLING_CHANNEL_COUNT_MIN),
            'criterion': 'N * (channel_width + land_width) <= '
                         '2*pi*(throat_radius + hot_wall_thickness)',
            'throat_radius_mm': float(uygunluk['gas_side_radius_m']) * 1e3,
            'hot_wall_thickness_mm':
                float(uygunluk['hot_wall_thickness_m']) * 1e3,
            'hot_wall_thickness_basis': t_kunye,
            'reference_radius_mm': float(uygunluk['reference_radius_m']) * 1e3,
            'reference_circumference_mm':
                float(uygunluk['reference_circumference_m']) * 1e3,
            'channel_width_mm': float(width) * 1e3,
            'land_width_mm': float(COOLING_CHANNEL_LAND_DEFAULT_M) * 1e3,
            'land_width_basis': COOLING_CHANNEL_LAND_BASIS,
            'basis': uygunluk['basis'],
            # Denetçi Ş4(iv): sığan durumda da GERÇEK bir beyan (None değil):
            # hidrolik sayıların hangi kanal sayısı için kurulduğu ve o
            # sayının sınıra göre yeri (ikisi de bu blokta yayımlanan
            # değerlerden).
            'hydraulics_basis': (
                f'the coolant velocity, Reynolds number and pressure drop '
                f'below are computed for these {int(n)} channels, which fit '
                f'the channel-base circumference ({int(n)} x '
                f'{float(uygunluk["pitch_m"]) * 1e3:.2f} mm = '
                f'{float(n * uygunluk["pitch_m"]) * 1e3:.1f} mm of '
                f'{float(uygunluk["reference_circumference_m"]) * 1e3:.1f} '
                f'mm)' if sigiyor else
                ("NOT computed: HRMA's minimum of "
                 f'{int(COOLING_CHANNEL_COUNT_MIN)} channels does not fit '
                 'this throat at the channel base (at most '
                 f'{n_max} fit), so no channel count is published and the '
                 'coolant velocity, Reynolds number and jacket pressure drop '
                 'are not computed (None); the fuel feed pressure that would '
                 'contain the jacket drop is not computed either'
                 if boyutlanamadi else
                 'the channel count you entered does NOT fit the '
                 'channel-base '
                 'circumference; the coolant velocity, Reynolds number and '
                 'pressure drop below are computed for that count as entered '
                 'and describe a geometry that cannot be built')),
        }
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

    @classmethod
    def _mach_from_area_ratio_subsonic(cls, area_ratio, gamma):
        """A/A* -> SUBSONİK Mach (Eq. 3-14'ün ikinci kökü; brentq).

        Aynı alan oranının iki kökü vardır; yakınsak konide (boğaz ÖNCESİ)
        geçerli olan subsonik olanıdır. ÖH defter P3B2-11: ısı transferi
        istasyon döngüsü bu kökü hiç çözmüyor, yerine kaynaksız bir
        ``T/T_c = 1/(1+(γ-1)·0.1·ln(A/A_t))`` yaklaşımı kullanıyordu.
        """
        from scipy.optimize import brentq
        eps = max(float(area_ratio), 1.0 + 1e-12)

        def residual(m):
            return cls._area_ratio_from_mach(m, gamma) - eps

        lo = 1e-6
        if residual(lo) < 0.0:
            return 1.0
        return float(brentq(residual, lo, 1.0 - 1e-12, xtol=1e-12))

    @staticmethod
    def _clamp_expansion_ratio(eps, lo, hi):
        """(ε_kırpılmış, kırpma_etiketi) — TEK kırpma noktası.

        ÖH D20 / P3B2-09 (Fable-D18 ŞARTI md. 2): ε kırpması iki ayrı dalda
        iki ayrı satır içi eşik çiftiyle yapılıyordu (çözücü dalı
        ``max(2.5, min(eps, 1000))``, yedek dal ``max(4, min(eps, 300))``) ve
        yalnız birincisi kırpma olgusunu yayımlıyordu. Artık her iki dal da
        bu yardımcıyı çağırır; etiket (``'floor'`` / ``'ceiling'`` / ``None``)
        çıktıda ``nozzle_angles.expansion_ratio_clamp`` olarak yayımlanır.
        """
        eps = float(eps)
        kirpilmis = max(float(lo), min(eps, float(hi)))
        if kirpilmis > eps * (1.0 + 1e-12):
            return kirpilmis, 'floor'
        if kirpilmis < eps * (1.0 - 1e-12):
            return kirpilmis, 'ceiling'
        return kirpilmis, None

    @classmethod
    def _isentropic_static_temperature(cls, t_chamber, area_ratio, gamma,
                                       supersonic):
        """Durgunluk sıcaklığından yerel STATİK sıcaklık [K].

        T/T_0 = (1 + (γ-1)/2 · M²)^(-1) (Sutton & Biblarz 9th ed., Eq. 3-7),
        M alan oranının uygun kökünden. Tek tanım noktası: aynı Eq. 3-14
        çözücüsü CF/çıkış basıncı zincirinde de kullanılır.
        """
        ar = max(float(area_ratio), 1.0)
        if ar <= 1.0 + 1e-12:
            mach = 1.0
        elif supersonic:
            mach = cls._mach_from_area_ratio_supersonic(ar, gamma)
        else:
            mach = cls._mach_from_area_ratio_subsonic(ar, gamma)
        return (float(t_chamber)
                / (1.0 + (gamma - 1.0) / 2.0 * mach ** 2)), float(mach)

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

    #: Boğaz akış katsayısı tablosu (tek tanım yeri).
    #: --- ÖH D20 / OH-D20-03 --------------------------------------------
    #: Ölçüldü (once.json OH-D20-03): tablo değerleri kodda
    #: ``# RS-25 NASA standard`` / ``# F-1 NASA standard`` / ``# Raptor
    #: class`` yorumlarıyla duruyordu ve yayımlanan künye bunları "NASA
    #: values" diye tekrarlıyordu — oysa hiçbirinin belge atfı YOKTU
    #: (belge adı, bölüm, tablo numarası hiçbir yerde geçmiyor). Uydurma
    #: atıf, atıfsız sayıdan daha kötüdür: okuyan onu doğrulanmış sanır.
    #: Sayılar DEĞİŞTİRİLMEDİ (ürün davranışı aynı kalsın diye); değişen,
    #: her kaydın ne olduğunun DOĞRU söylenmesidir. Üçü de yayımlanmış
    #: bandın (ζ_d ~ 0,98-1,0 iyi tasarlanmış lülelerde; Sutton & Biblarz,
    #: "Rocket Propulsion Elements" 9. baskı, Böl. 3.2 boğaz akış/deşarj
    #: düzeltmesi) içinde seçilmiş VARSAYIMDIR.
    THROAT_DISCHARGE_COEFFICIENTS = {
        ('lh2', 'lox'): (0.98, 'assumed'),
        ('rp1', 'lox'): (0.98, 'assumed'),
        ('methane', 'lox'): (0.95, 'assumed'),
    }
    THROAT_DISCHARGE_COEFFICIENT_DEFAULT = (0.98, 'assumed')

    def _throat_discharge_coefficient(self, with_source=False):
        """Boğaz akış katsayısı (yakıt çiftine göre; tek tanım yeri).

        ``with_source=True`` ile ``(C_D, künye)`` döner; künye değerin
        ATFINI (belgeli mi, varsayım mı) ve tablodan mı yoksa varsayılandan
        mı geldiğini söyler. Uydurma belge adı yazılmaz.
        """
        anahtar = (self.fuel_type.lower(), self.oxidizer_type.lower())
        kayit = self.THROAT_DISCHARGE_COEFFICIENTS.get(anahtar)
        tablodan = kayit is not None
        if kayit is None:
            kayit = self.THROAT_DISCHARGE_COEFFICIENT_DEFAULT
        deger, atif = kayit
        if not with_source:
            return deger
        kunye = {
            'value': float(deger),
            'attribution': atif,
            'from_table': tablodan,
            'propellant_pair': f'{anahtar[0]}/{anahtar[1]}',
            'basis': (
                f'C_D = {deger:g} is an ASSUMED engineering value, not a '
                'measured or document-cited number for this propellant pair'
                + ('' if tablodan else
                   ' (this pair is not in the table; the default is used)')
                + '. It sits inside the published band for well designed '
                  'converging-diverging throats (discharge correction '
                  '~0.98-1.0; Sutton & Biblarz, "Rocket Propulsion '
                  'Elements" 9th ed., Ch. 3). HRMA has no throat boundary '
                  'layer solution, so the value is NOT solved'),
        }
        return deger, kunye

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
        # 2026-07-22: canlı CEA yolunda Isp ZATEN kullanıcının ε'sunda
        # çözülmüştür (bkz. _solve_design_expansion); burada bir kez daha
        # CF oranıyla ölçeklemek ÇİFT SAYIM olur. Yalnız ayrılma uyarısı ve
        # çıkış basıncı bilgisi üretilir.
        if (getattr(self, 'combustion_data_source', '') == 'rocketcea'
                and abs(float(getattr(self, 'design_reference_expansion_ratio',
                                      -1.0)) - float(eps_user)) < 1e-6):
            try:
                _, pe_user = self._cf_at(eps_user, self.P_a)
                self.exit_pressure_fixed_bar = pe_user
                self._warn_flow_separation(eps_user, pe_user)
            except Exception:
                pass
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
            self._warn('warn.liquid.expansion_ratio_unsolved', 'warning',
                       eps=float(eps_user), detail=str(exc))
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
            self._warn('warn.liquid.vacuum_isp_capped', 'warning',
                       eps=float(eps_user),
                       isp_vac=round(float(self.isp_vac), 1))
            isp_vac_new = self.isp_vac
        self.isp_sl = isp_sl_new
        self.isp_vac = isp_vac_new
        self._warn_flow_separation(eps_user, pe_user)

    def _static_path_vacuum_anchor(self):
        """Statik tablo dalında vakum Isp'sini MOTORUN KENDİ lülesine taşır.

        ÖH D15 / sıvı (P3B1-07). RocketCEA kullanılamadığında (paketlenmiş /
        çevrimdışı kullanım — ürünün en çok koştuğu dal budur) performans
        referansları yerleşik tablodan gelir. Tablonun ``isp_sl`` çapası
        ORTAM-EŞLENİK lüleye, ``isp_vac`` çapası ise ÇOK daha büyük bir
        lüleye aittir (rp1/lox satırı bunu kendi yorumunda söylüyor:
        "Area ratio 16:1" ve "Area ratio 200:1"). Motorun kendi lülesi ise
        ölçüldü (once.json, 25 kN / Pc=100 / MR=2,577) ε = 11,357: aynı
        yanıtta ÜÇ FARKLI LÜLE buluşuyordu ve yayımlanan vakum Isp'si
        353,200 s, aynı lülenin tutarlı değerinden (333,633 s) +19,567 s
        (+%5,86) İYİMSERDİ.

        Canlı CEA yolunda bu kapatılmıştı (_resolve_combustion_reference
        çapayı motorun ε'suna taşır) ve kullanıcı bir ε girdiğinde statik
        dalda da kapanıyordu (_apply_nozzle_off_design_once); AÇIK KALAN tek
        dal, kullanıcının ε girmediği statik koşuydu — yani varsayılan.

        Taşıma AYNI LÜLE özdeşliğidir (Sutton & Biblarz 9th ed., Eq. 3-29):
            F_vac = F_sl + P_a·A_e  ->  Isp_vac = Isp_sl + P_a·ε·c*/(P_c·C_D·g0)
        Tablonun vakum çapası atılmaz: itici KAPASİTE referansı olarak
        (``isp_vac_capability_ref``) ve tablodan GERİ ÇÖZÜLEN alan oranıyla
        birlikte yayımlanır — o alan oranı tablonun kendi sayılarından
        ölçülür, uydurulmaz.
        """
        if getattr(self, '_static_vac_anchor_applied', False):
            return
        if getattr(self, 'combustion_data_source', '') == 'rocketcea':
            return
        if getattr(self, 'expansion_ratio_input', None) is not None:
            # Kullanıcı ε verdiyse taşıma _apply_nozzle_off_design_once
            # içinde ZATEN yapıldı; ikinci kez uygulanırsa çift sayım olur.
            return
        eps = float(getattr(self, 'expansion_ratio', 0) or 0)
        c_star = float(getattr(self, 'c_star_effective', 0)
                       or getattr(self, 'c_star', 0) or 0)
        isp_sl = float(getattr(self, 'isp_sl', 0) or 0)
        isp_vac_table = float(getattr(self, 'isp_vac', 0) or 0)
        if eps <= 1.0 or c_star <= 0 or isp_sl <= 0 or isp_vac_table <= 0:
            return
        cd = self._throat_discharge_coefficient()
        isp_vac_own = isp_sl + (
            float(self.P_a) * PA_PER_BAR * eps * c_star
            / (float(self.P_c) * PA_PER_BAR * cd * self.g0))
        self._static_vac_anchor_applied = True
        self.isp_vac_capability_ref = isp_vac_table
        self.isp_vac_capability_eps = self._expansion_ratio_from_vacuum_cf(
            isp_vac_table * self.g0 / c_star)
        eps_capability = self.isp_vac_capability_eps
        self.isp_vac = float(isp_vac_own)
        self.isp_vacuum_basis = (
            'static anchor table path: the tabulated vacuum Isp '
            f'({isp_vac_table:.3f} s) belongs to a much larger nozzle '
            + (f'(ideal-CF-equivalent area ratio {eps_capability:.1f}, '
               'recovered from the table own c* and Isp; the tabulated value '
               'is a delivered-level anchor, so this is smaller than the '
               'geometric ratio the table comment cites) '
               if eps_capability else
               '(its area ratio could not be recovered from the table) ')
            + f'and is reported as a propellant capability reference; the '
            f'vacuum Isp of THIS nozzle (epsilon={eps:.3f}) is derived from '
            'the same nozzle sea-level value with F_vac = F_sl + P_a*A_e '
            '(Sutton & Biblarz 9th ed., Eq. 3-29)')

    def _expansion_ratio_from_vacuum_cf(self, cf_target):
        """CF_vac(ε) = cf_target denklemini sağlayan ε (yoksa None).

        Tablonun KENDİ sayılarından (isp_vac, c*) ima edilen alan oranını
        geri çözer; hiçbir alan oranı elle yazılmaz (P3B1-07).
        """
        try:
            hedef = float(cf_target)
            if not np.isfinite(hedef) or hedef <= 0:
                return None
            lo, hi = 1.5, 1000.0
            f_lo = self._cf_at(lo, 0.0)[0] - hedef
            f_hi = self._cf_at(hi, 0.0)[0] - hedef
            if f_lo * f_hi > 0:
                return None
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                f_mid = self._cf_at(mid, 0.0)[0] - hedef
                if f_lo * f_mid <= 0:
                    hi, f_hi = mid, f_mid
                else:
                    lo, f_lo = mid, f_mid
            return float(0.5 * (lo + hi))
        except Exception:
            return None

    def _warn_flow_separation(self, eps_user, pe_user):
        """Aşırı genişleme -> akış ayrılması (Summerfield ölçütü) uyarısı.

        Ayrılan lülede gerçek deniz seviyesi itkisi ideal CF'nin
        öngördüğünden YÜKSEK olur; bu model ayrılmayı çözmez, bu yüzden
        kullanıcıya açıkça söylenir.
        """
        if pe_user < NOZZLE_SEPARATION_PRESSURE_RATIO * self.P_a:
            self._warn('warn.liquid.flow_separation', 'warning',
                       eps=float(eps_user),
                       pe_bar=round(float(pe_user), 3),
                       ratio=float(NOZZLE_SEPARATION_PRESSURE_RATIO))

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
            
            # v2.6.26 — AYRISTIRILAMAYAN YANIT "CANLI" SAYILMAZ.
            # fetch_nist_data ayristirma basarisiz oldugunda
            # {'error': ..., 'status': 'parse_failed'} donuyor (eskiden
            # 'success' damgaliydi). O durumda asagidaki .get(anahtar,
            # SABIT) zinciri devreye giriyor ve satir ici sabitler (0,001 /
            # 0,0005 / 800 ...) "NIST (Live)" etiketiyle sunuluyordu.
            # Artik depoda ZATEN var olan kaynakli tablo kullaniliyor
            # (web_propellant_api._get_fallback_data: LOX mu=1,94e-4,
            # RP-1 1,64e-3, LH2 1,34e-5, metan 1,17e-4) ve kaynak durumu
            # durustce tasiniyor.
            def _usable(props, compound):
                if isinstance(props, dict) and props.get('status') == 'success' \
                        and props.get('density') is not None:
                    return props
                try:
                    yedek = dict(web_api._get_fallback_data(compound, 'parse_failed'))
                except Exception:
                    return props if isinstance(props, dict) else {}
                yedek.setdefault('status', 'fallback_table')
                yedek.setdefault('source', 'HRMA sourced property table')
                return yedek

            fuel_props = _usable(fuel_props, self.fuel_type)
            ox_props = _usable(ox_props, self.oxidizer_type)

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
        #
        # ÖH defter P3B1-14 (Z5S/PK1): yedeğin yedeği ``self.F / (300 *
        # self.g0)`` idi — A3 kapanışının yasakladığı "Isp = 300 s" yer
        # tutucusu. Bugün erişilemez (isp_sl_ref her yolda kurulur) ama
        # canlanırsa tank hacminden pompa gücüne kadar her besleme sayısı
        # kimyasız bir Isp'den türerdi. Artık yedek YOK: referans Isp
        # kurulmamışsa besleme kartı sayı üretmez (fail-closed).
        mdot_total = getattr(self, 'mdot_total', None)
        if mdot_total is None or not np.isfinite(mdot_total) or mdot_total <= 0:
            if not hasattr(self, 'isp_sl_ref'):
                raise UnsupportedPropellantPairError(
                    'the feed system was requested before any Isp reference '
                    'was solved, so the propellant mass flow cannot be '
                    'derived; HRMA does not substitute a representative '
                    'Isp = 300 s placeholder (A3 closure).',
                    fuel=getattr(self, 'fuel_type', None),
                    oxidizer=getattr(self, 'oxidizer_type', None))
            mdot_total = self.F / (self.isp_sl_ref * self.g0)
        mdot_ox = getattr(self, 'mdot_ox', mdot_total * self.MR / (1 + self.MR))
        mdot_fuel = getattr(self, 'mdot_fuel', mdot_total / (1 + self.MR))

        # Tank basıncı: basınç beslemeli çevrimde kullanıcının feed_pressure
        # girdisi, turbopompalı çevrimde NPSH tankı (sabit 2.5 bar değil).
        # A11: mantık artık _tank_pressure_bar'da TEK kopya — ayrıntılı tank
        # kartı da aynı fonksiyondan okur, iki kart çelişemez.
        tank_pressure_bar, tank_pressure_source = self._tank_pressure_bar()
        # Basınçlandırma gazı: TEK tanım yeri (P3B1-05).
        _pressurant_type, _pressurant_basis = self._pressurization_type()

        feed_system = {
            'type': self.feed_system_type,
            'tank_pressure_bar': tank_pressure_bar,
            'tank_pressure_source': tank_pressure_source,
            'mass_flow_rates': {
                'oxidizer': mdot_ox,  # kg/s
                'fuel': mdot_fuel,    # kg/s
                'total': mdot_total   # kg/s
            },
            
            # Tank system
            'tanks': {
                'oxidizer_tank': {
                    'volume': self._calculate_tank_volume(mdot_ox, 'oxidizer'),  # m³ (None = süre verilmedi)
                    'volume_source': self._tank_volume_source(),
                    'pressure': tank_pressure_bar,  # bar
                    'material': 'Aluminum 2219-T87',
                    'insulation': 'MLI' if self.oxidizer_type in ['lox', 'lh2'] else 'None',
                    'valves': ['main_valve', 'vent_valve', 'fill_valve', 'drain_valve'],
                    'sensors': ['pressure', 'temperature', 'level', 'mass']
                },
                'fuel_tank': {
                    'volume': self._calculate_tank_volume(mdot_fuel, 'fuel'),  # m³ (None = süre verilmedi)
                    'volume_source': self._tank_volume_source(),
                    'pressure': tank_pressure_bar,  # bar
                    'material': 'Aluminum 2219-T87',
                    'insulation': 'MLI' if self.fuel_type in ['lh2', 'methane'] else 'None',
                    'valves': ['main_valve', 'vent_valve', 'fill_valve', 'drain_valve'],
                    'sensors': ['pressure', 'temperature', 'level', 'mass']
                }
            },
            
            # Pressurization system
            'pressurization': {
                # P3B1-05: tip TEK kaynaktan (_pressurization_type) gelir;
                # eskiden burada 'autogenous' KOŞULSUZ yazılıyordu ve aynı
                # yanıttaki autogenous_pressurization bloğu 'uygulanamaz'
                # diyordu.
                'type': _pressurant_type,
                'type_basis': _pressurant_basis,
                # Türemeyen sayılar KALDIRILDI (bkz. FEED_INSTRUMENTATION_BASIS).
                'pressurant_tanks': None,
                'pressurant_tanks_status': FEED_INSTRUMENTATION_STATUS,
                'pressurant_tanks_basis': (
                    'not calculated: the number of pressurant tanks needs a '
                    'bottle volume and storage pressure choice, neither of '
                    'which HRMA solves; the field was also meaningless for '
                    'the autogenous configuration, which has no pressurant '
                    'bottle at all'),
                # Devre başına ana + yedek regülatör: ox_main, ox_backup,
                # fuel_main, fuel_backup (kodun kendi eski yorumu buydu).
                'pressure_regulators': (PROPELLANT_CIRCUIT_COUNT
                                        * CONTROL_REDUNDANCY),
                'pressure_regulators_basis': _feed_topology_basis(
                    'pressure_regulators',
                    f'a main and a backup regulator on each of the '
                    f'{PROPELLANT_CIRCUIT_COUNT} propellant circuits '
                    f'({PROPELLANT_CIRCUIT_COUNT} x {CONTROL_REDUNDANCY})'),
                # Emniyet vanası sayısı artık ÇÖZÜCÜNÜN KENDİ modelinden:
                # her itici tankı için _size_tank_relief_valve bir vana
                # boyutlandırıyor. Eski literal 4 idi ve tank kartlarındaki
                # 2 vanayla çelişiyordu.
                'relief_valves': PROPELLANT_CIRCUIT_COUNT,
                'relief_valves_basis': (
                    'relief valves: one per propellant tank, matching the '
                    'valve actually sized by _size_tank_relief_valve (API RP '
                    '520 Part I critical gas flow) and reported under '
                    'propellant_tanks.*.internal_structures.instrumentation.'
                    'relief_valve. The previous literal 4 contradicted the '
                    'tank cards, which carry exactly 2 sized valves'),
                'check_valves': None,
                'check_valves_status': FEED_INSTRUMENTATION_STATUS,
                'check_valves_basis': (
                    'not calculated: HRMA solves a single-branch line, not a '
                    'flow network, so the number of check valves needed to '
                    'prevent backflow cannot be derived'),
            },
            
            # Turbopump system (if applicable)
            'turbopump': self._design_turbopump_system(mdot_ox, mdot_fuel) if self.feed_system_type == 'turbopump' else None,
            
            # Feed lines and components
            'feed_lines': {
                'oxidizer_main': {
                    'diameter': self._calculate_line_diameter(mdot_ox, 'oxidizer'),  # m
                    # ÇİFT TANIM kapatıldı: boy artık basınç düşümünün
                    # kullandığı sabitin ta kendisi.
                    'length': FEED_LINE_LENGTH_DEFAULT_M,  # m
                    'length_basis': FEED_LINE_LENGTH_BASIS,
                    'material': 'Stainless Steel 316L',
                    'insulation': True if self.oxidizer_type in ['lox', 'lh2'] else False,
                    'valves': ['isolation_valve', 'throttle_valve', 'shutoff_valve'],
                    'filters': ['main_filter', 'fine_filter'],
                    **self._line_leg_declaration(mdot_ox, 'oxidizer'),
                },
                'fuel_main': {
                    'diameter': self._calculate_line_diameter(mdot_fuel, 'fuel'),  # m
                    # OH-D18-03: bu çap KOL BAŞINADIR. Kol sayısı olmadan
                    # yayımlanan tek bir "ana hat" çapı, çoklu kollu bir
                    # tasarımı tek borulu gösterir.
                    **self._line_leg_declaration(mdot_fuel, 'fuel'),
                    'length': FEED_LINE_LENGTH_DEFAULT_M,  # m
                    'length_basis': FEED_LINE_LENGTH_BASIS,
                    'material': 'Stainless Steel 316L',
                    'insulation': True if self.fuel_type in ['lh2', 'methane'] else False,
                    'valves': ['isolation_valve', 'throttle_valve', 'shutoff_valve'],
                    'filters': ['main_filter', 'fine_filter']
                },
                'cooling_lines': self._design_cooling_lines() if self.cooling_type == 'regenerative' else []
            },
            
            # Control system
            #
            # v2.6.26: sayılar iki sınıfa ayrıldı. Devre/eksen/yedeklilik
            # sayısından ARİTMETİK olarak çıkanlar hesaplanıp topoloji
            # beyanıyla yayımlanır; hiçbir mimariden türemeyen sensör
            # sayıları None + NOT_MODELLED olur.
            'control_system': {
                'main_valves': PROPELLANT_CIRCUIT_COUNT,      # ox + yakıt
                'main_valves_basis': _feed_topology_basis(
                    'main_valves',
                    f'one shutoff valve per propellant circuit '
                    f'({PROPELLANT_CIRCUIT_COUNT} circuits: oxidizer, fuel)'),
                'backup_valves': PROPELLANT_CIRCUIT_COUNT,
                'backup_valves_basis': _feed_topology_basis(
                    'backup_valves',
                    f'one backup valve per propellant circuit '
                    f'({PROPELLANT_CIRCUIT_COUNT} circuits)'),
                'throttle_valves': PROPELLANT_CIRCUIT_COUNT,
                'throttle_valves_basis': _feed_topology_basis(
                    'throttle_valves',
                    f'one throttling valve per propellant circuit '
                    f'({PROPELLANT_CIRCUIT_COUNT} circuits)'),
                'gimbal_actuators': GIMBAL_AXIS_COUNT,        # yunuslama + sapma
                'gimbal_actuators_basis': _feed_topology_basis(
                    'gimbal_actuators',
                    f'one actuator per gimbal axis ({GIMBAL_AXIS_COUNT} axes: '
                    'pitch, yaw)'),
                'control_computers': CONTROL_REDUNDANCY,      # yedekli
                'control_computers_basis': _feed_topology_basis(
                    'control_computers',
                    f'{CONTROL_REDUNDANCY}x redundancy on the control '
                    'computer (active plus standby)'),
                'pressure_sensors': None,
                'pressure_sensors_status': FEED_INSTRUMENTATION_STATUS,
                'pressure_sensors_basis': FEED_INSTRUMENTATION_BASIS,
                'temperature_sensors': None,
                'temperature_sensors_status': FEED_INSTRUMENTATION_STATUS,
                'temperature_sensors_basis': FEED_INSTRUMENTATION_BASIS,
                'flow_sensors': None,
                'flow_sensors_status': FEED_INSTRUMENTATION_STATUS,
                'flow_sensors_basis': FEED_INSTRUMENTATION_BASIS,
                # P3B1-02: hüküm artık kimyadan (LIQUID_HYPERGOLIC_PAIRS),
                # beyaz listeden değil. Hipergolik olmayan çiftte donanım
                # SEÇİLMEZ; sensör alanlarıyla aynı sözleşmede beyan edilir.
                'propellant_hypergolic': self._pair_is_hypergolic(),
                'propellant_hypergolic_basis': LIQUID_HYPERGOLIC_BASIS,
                'ignition_system': ('hypergolic'
                                    if self._pair_is_hypergolic() else None),
                'ignition_system_status': (
                    None if self._pair_is_hypergolic()
                    else LIQUID_IGNITER_STATUS),
                'ignition_system_basis': (
                    LIQUID_HYPERGOLIC_BASIS if self._pair_is_hypergolic()
                    else LIQUID_IGNITER_BASIS),
            },
            
            # Performance calculations
            'pressure_drops': self._calculate_feed_system_pressure_drops(),
            'total_mass': self._estimate_feed_system_mass()
        }
        
        return feed_system
        
    def _chamber_volume_split(self):
        """L* muhasebesi — konverjan koni DÂHİL (P3B2-02, ÖH D15).

        Ölçüldü (once.json, 25 kN / 60 bar / LOX-RP1, characteristic_length =
        1,2 m): yayımlanan ``cooling_system.l_star`` ve
        ``combustion_analysis.chamber_geometry.l_star`` 1,2 m diyordu, ama
        aynı yanıtın KENDİ geometrisinden (D_ch, d_t, L_conv) çizilen hazne
        1,9144 m L*'a karşılık geliyordu (+%59,5). Sebep: ``V_c = L*·A_t``
        kurulup ``L_c = V_c / A_c`` ile bütün hacim SİLİNDİRE veriliyordu;
        boğaz öncesi konverjan koni hacmi hiç sayılmıyordu. Yayımlanan
        ``l_star = V_c/A_t`` üçlüsü de bağımsız doğrulama gibi duruyordu ama
        totolojiydi: V_c zaten L*·A_t olarak kurulmuştu, tanım gereği girdiye
        eşit çıkıyordu.

        L* tanımı boğaza kadarki TÜM hazne hacmini kapsar (Sutton & Biblarz
        9. baskı Böl. 8; Huzel & Huang Böl. 4). Bu yüzden silindirik boy artık
        koni hacmi DÜŞÜLEREK çözülür:

            V_c   = L*·A_t                         (istenen)
            V_kon = π·L_conv/3·(r_c² + r_c·r_t + r_t²)   (kesik koni)
            V_sil = V_c − V_kon    ;    L_sil = V_sil / A_c

        Böylece ÇİZİLEN hazne istenen L*'ı fiilen teslim eder. İstenen L*
        koninin tek başına doldurduğu hacmin altındaysa o geometri
        ULAŞILAMAZ — sayı uydurulmaz, fail-closed reddedilir.

        Döner: (V_toplam, V_koni, V_silindir, L_silindir, L_koni) [SI].
        """
        d_t = float(getattr(self, 'd_t', 0.03) or 0.03)
        d_c = float(self._chamber_diameter())
        l_star = float(self._l_star())
        a_t = np.pi * d_t ** 2 / 4.0
        a_c = np.pi * d_c ** 2 / 4.0
        l_conv = max((d_c - d_t)
                     / (2.0 * np.tan(np.radians(CONVERGENT_HALF_ANGLE_DEG))),
                     0.0)
        r_c, r_t = d_c / 2.0, d_t / 2.0
        v_kon = np.pi * l_conv / 3.0 * (r_c * r_c + r_c * r_t + r_t * r_t)
        v_top = l_star * a_t
        v_sil = v_top - v_kon
        if v_sil <= 0.0:
            # Koni tek başına istenen L*'ı doldurdu. Hükmü KİM verdi?
            #
            # (a) KULLANICI L* yazdıysa istek gerçekten kurulamaz: iki
            #     kullanıcı hükmü (L* ve daralma oranı) aynı anda
            #     sağlanamaz — sayı uydurulmaz, fail-closed reddedilir.
            # (b) L* MODEL TABANIysa (L_STAR_DEFAULT_M) kurulamayan bir
            #     kullanıcı isteği yoktur; iki MODEL tabanı (L* = 1,2 m ile
            #     d_c/d_t = 3,5) birbiriyle çelişiyordur. Ölçüldü: koninin
            #     tek başına tuttuğu L* = 12,088·d_t olduğundan boğazı
            #     99,3 mm'yi geçen her motorda (60 bar'da ~70 kN üstü) taban
            #     L* ulaşılamaz hâle gelir. Böyle bir motoru reddetmek
            #     kusuru düzeltmez, ürünü kırar; taban L* koninin gerektirdiği
            #     değere YÜKSELTİLİR (daha uzun hazne = daha uzun kalış
            #     süresi, muhafazakâr yön) ve yayımlanan l_star artık ÇİZİLEN
            #     geometrinin kendisidir — beyan 'l_star_basis' ile birlikte
            #     cooling_system'de durur. Eski davranış her iki durumda da
            #     1,2 m diyor, 1,91-2,42 m çiziyordu.
            self._warn('warn.liquid.l_star_unreachable', 'warning',
                       l_star_m=round(l_star, 4),
                       l_star_convergent_only_m=round(float(v_kon / a_t), 4),
                       contraction_ratio=round(float((d_c / d_t) ** 2), 3))
            # Silindirik gövde KISALTILARAK istenen L*'a inilemez: koni tek
            # başına daha fazlasını tutuyor. Bu geometride ulaşılabilir en
            # küçük L* koninin kendisidir ve sıfır boylu bir hazne yayımlamak
            # (yüzey alanı 0 -> hazne ısı yükü 0) sessiz bir sıfır üretir.
            # Bu yüzden ÇİZİLEN gövde değiştirilmez (silindir eski tanımıyla
            # L*·A_t/A_c kalır) ama YAYIMLANAN L* artık o gövdenin kendisidir
            # ve istenen değer yanında 'l_star_requested' olarak durur.
            v_sil = v_top
            v_top = v_sil + v_kon
        return (float(v_top), float(v_kon), float(v_sil),
                float(v_sil / a_c), float(l_conv), float(v_top / a_t))

    @staticmethod
    def _canonical_propellant_key(ad):
        """İtici adının kanonik biçimi (P3B1-11): kırpılmış + küçük harf.

        Dize olmayan ya da kırpınca boşalan değer DEĞİŞTİRİLMEDEN döner —
        girdi kapısı burada değil, uçtadır; bu yalnız tablo aramasının
        yazım biçimine takılmamasını sağlar.
        """
        if not isinstance(ad, str):
            return ad
        k = ad.strip().lower()
        return k if k else ad

    def _manifold_diameter_report(self, injector):
        """Manifold çapı yaprakları — TEK KAYNAK devre modelidir (P3B2-06).

        Döner: yayımlanacak anahtarlar. Modül çözdüyse iki çap + künye;
        çözemediyse SAYI YOK, yalnız künye (fail-closed).
        """
        detay = (injector or {}).get('injector_design_detail')
        blok = {}
        cozulen = []
        if isinstance(detay, dict) and detay.get('status') == 'success':
            for anahtar, devre in (('fuel_manifold_diameter_mm',
                                    'fuel_circuit'),
                                   ('oxidizer_manifold_diameter_mm',
                                    'ox_circuit')):
                man = ((detay.get(devre) or {}).get('manifold') or {})
                d_mm = man.get('d_mm')
                if isinstance(d_mm, (int, float)) and np.isfinite(d_mm) \
                        and d_mm > 0:
                    blok[anahtar] = float(d_mm)
                    cozulen.append(devre)
        if blok:
            blok['manifold_diameter_basis'] = (
                'solved by the injector circuit model '
                '(injector_design_detail.*_circuit.manifold): the manifold '
                'cross-section is sized from the circuit feed area ratio and '
                'the manifold/orifice velocity ratio limit, and is the SAME '
                'number the detail block publishes. The former 2.5 x '
                'equivalent-orifice-diameter rule of thumb with a 10/12 mm '
                'floor is gone: it had no basis field and disagreed with the '
                'solved diameter in the same response.')
        else:
            blok['manifold_diameter_basis'] = (
                'NOT PUBLISHED: the injector circuit model did not return a '
                'manifold solution on this run, and no rule-of-thumb '
                'diameter is substituted for it.')
        return blok

    def _pair_is_hypergolic(self):
        """Bu itici çifti hipergolik mi (P3B1-02) — kimyadan, beyaz listeden değil."""
        return (str(self.fuel_type).lower(),
                str(self.oxidizer_type).lower()) in LIQUID_HYPERGOLIC_PAIRS

    @staticmethod
    def _species_densities_from_table(combinations):
        """Çift tablosundan TÜR bazlı yoğunluk sözlükleri (P3B1-01).

        Tablo çift anahtarlıdır ((yakıt, oksitleyici) -> özellikler) ama
        ``density_fuel`` / ``density_ox`` alanları çiftin değil TÜRÜN
        özelliğidir: ``lox`` iki ayrı çiftte de 1141,7 kg/m³, ``n2o4`` iki
        ayrı çiftte de 1443,2 kg/m³ yazar. Bu yüzden tablo dışı bir çiftte
        (ör. lh2/n2o4) her iki yoğunluk da AYNI tablodan okunabilir — yeni
        sayı üretilmez, sabit yazılmaz (tek kaynak: tablonun kendisi).

        Aynı tür iki çiftte FARKLI yazılmışsa bu tablonun kendi iç
        çelişkisidir; sessizce birini seçmek yerine o tür çözülemez sayılır
        (değer None döner ve çağıran fail-closed davranır).
        """
        yakit, oks = {}, {}
        for (f, o), props in combinations.items():
            for anahtar, sozluk, alan in ((str(f).lower(), yakit,
                                           'density_fuel'),
                                          (str(o).lower(), oks,
                                           'density_ox')):
                deger = props.get(alan)
                if deger is None:
                    continue
                deger = float(deger)
                if anahtar in sozluk and sozluk[anahtar] is not None:
                    if abs(sozluk[anahtar] - deger) > 1e-9:
                        sozluk[anahtar] = None      # tablo kendi içinde çelişik
                else:
                    sozluk.setdefault(anahtar, deger)
        return yakit, oks

    def _resolve_species_density(self, tur, tablo, override_alani, rol):
        """(yoğunluk, künye) — tablo dışı çiftte tek çözüm yolu (P3B1-01).

        Öncelik: kullanıcı girdisi > tablodaki TÜR yoğunluğu > YOK (None).
        None dönerse çağıran fail-closed davranır; yer tutucu üretilmez.
        """
        ham = self.overrides.get(override_alani)
        if ham not in (None, ''):
            try:
                kullanici = float(ham)
            except (TypeError, ValueError):
                kullanici = None
            if kullanici is not None and np.isfinite(kullanici) and kullanici > 0:
                # Değer ayrıca _apply_overrides'ta aralık denetiminden geçer;
                # burada yalnız künyenin doğru olması için okunur.
                return kullanici, 'user input'
        deger = tablo.get(str(tur).lower())
        if deger is not None:
            return float(deger), (
                'built-in propellant table (species density; this pair is '
                'not a table entry, the density is read from the table pair '
                'that shares this propellant)')
        return None, None

    def _set_propellant_properties(self):
        """NASA CEA verified propellant combinations (99.8% accuracy)"""
        
        # NASA CEA (Chemical Equilibrium with Applications) verified database
        # Based on NASA RP-1311-I, RP-1311-II, and latest CEA calculations
        combinations = LIQUID_PROPELLANT_REFERENCE_TABLE
        
        key = (self.fuel_type, self.oxidizer_type)
        if key in combinations:
            props = combinations[key]
            # Girdi katmanı bittikten sonra CEA referansı motorun GERÇEK
            # tasarım ε'sunda yenilenir; fallback sözlüğü o zaman da gerekir.
            self._table_props = props
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
            # P3B1-01: yoğunluğun NEREDEN geldiği burada kaydedilir; künye
            # _propellant_density'de tahmin EDİLMEZ (eski davranış: kaynak
            # 'user input' değilse koşulsuz 'built-in propellant table'
            # basılıyordu — tabloda olmayan çiftte YALAN oluyordu).
            self.rho_fuel_source = 'built-in propellant table'
            self.rho_ox_source = 'built-in propellant table'
            self.optimal_mr = props['optimal_mr']
            # P3B1-04: tablo satırındaki 'optimal_mr_thrust' ARTIK
            # OKUNMUYOR. Ölçüldü: tablodaki 6 çiftin 6'sında da
            # of_thrust < of_isp yazıyor, oysa modülün kendi fizik beyanı
            # (ve F ∝ Isp/c* türetmesi) itki optimumunun DAHA YÜKSEK O/F'de
            # olduğunu söylüyor — yani tablo sütunu yönü ters bir literal.
            # Değer CEA taramasıyla çözülür (_solve_optimal_mixture_ratio);
            # çözülemezse alan yayımlanmaz.
            self.optimal_mr_thrust = None
            self.optimal_mr_thrust_source = 'not_modelled'
            
            # Advanced thermodynamic properties
            self.cp_chamber = props['cp_chamber']
            self.cp_chamber_source = (
                'built-in propellant table entry for this exact pair')
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
            # ----------------------------------------------------------------
            # TABLODA OLMAYAN İTİCİ ÇİFTİ (Faz 4B, bulgu A3)
            #
            # ÖLÇÜM (2 Ağustos 2026, HEAD a7ff1e7): fuel='zirvaaa',
            # oxidizer='gizemli' gönderilen istek HTTP 200 dönüyor,
            # design_summary.status 'OPTIMIZED' yazıyor ve kullanıcıya
            # Isp_sl = 285 s / Isp_vac = 320 s / c* = 1650 m/s gösteriliyordu.
            # Bu sayılar HİÇBİR kimyadan gelmiyor: aşağıdaki blokta düz
            # yazılmış yer tutuculardı ve "muhafazakâr kestirim" adıyla
            # sunuluyordu. Beyan kanalı doğru kuruluydu
            # (combustion_data_source), ama kimse okumuyordu; ayrıca ölçüldü:
            # kaynak 'not_modelled'a düştüğü için aşağıdaki uyarı bile HİÇ
            # ateşlenmiyordu (design_warnings == []).
            #
            # KARAR: KAPALI DEVRE (fail-closed). Modellenmeyen bir çift için
            # temsili performans ÜRETİLMEZ. Depodaki yerleşik standart budur
            # (cea_bridge._not_modelled + tests/test_cea_bridge.py
            # ::test_unmapped_pair_no_fallback_not_modelled: "sahte sayı YOK").
            #
            # Bu kapı MEŞRU seçimleri kapatmaz — ölçüldü: liquid.html'in
            # sunduğu 5 yakıt x 2 oksitleyici = 10 çiftin 10'u da RocketCEA
            # ile çözülüyor (rp1/n2o4, lh2/n2o4, methane/n2o4, mmh/lox,
            # udmh/lox dahil; hiçbiri tabloda değil). Kapıya yalnız ne tabloda
            # ne CEA kartında olan girdiler takılır.
            #
            # PERFORMANS DIŞI özellikler önden atanır: istisna kurulmadan ÖNCE
            # _resolve_combustion_reference çağrılır ve o yol BAŞARILI olduğunda
            # (tablo dışı ama CEA ile çözülen çiftler) motorun geri kalanı bu
            # değerlere ihtiyaç duyar. Ayrımı net tutmak şart: Isp / c* / T_c /
            # gamma / mw PERFORMANSTIR ve yer tutucusu YASAKTIR — CEA çözerse
            # CEA'dan gelir, çözemezse motor kurulmaz. Aşağıdakiler ise taşıma
            # ve yoğunluk özellikleridir, beyan edilmiş yedeklerdir ve
            # kullanıcı overrides ile ezebilir (bkz. sabitlerin tanımı).
            # ----------------------------------------------------------------
            self.propellant_name = f"{self.fuel_type.upper()}/{self.oxidizer_type.upper()}"
            # --- P3B1-01 (ÖH D15): YOĞUNLUK UYDURULMAZ ------------------
            # Çift tabloda yok ama TÜRLERİ tabloda var: yakıt yoğunluğu
            # tablodaki herhangi bir çiftin aynı yakıtından, oksitleyici
            # yoğunluğu aynı oksitleyicisinden okunur. Bu bir yer tutucu
            # değil, tablonun KENDİ ölçülen değeridir (lh2 70,85 kg/m³ NBP,
            # methane 422,8, n2o4 1443,2 ...) ve künyesi bunu söyler.
            # Tür de tabloda yoksa kullanıcı girdisine bakılır; o da yoksa
            # motor kurulmaz (UnsupportedPropellantDensityError).
            rho_f_tab, rho_o_tab = self._species_densities_from_table(
                combinations)
            self.rho_fuel, self.rho_fuel_source = self._resolve_species_density(
                self.fuel_type, rho_f_tab, 'fuel_density', 'fuel')
            self.rho_ox, self.rho_ox_source = self._resolve_species_density(
                self.oxidizer_type, rho_o_tab, 'oxidizer_density', 'oxidizer')
            # P3B1-06: yanma gazı taşıma özellikleri TABLODAN türetilir;
            # yedeğin bandın İÇİNDE olduğu artık ölçülebilir ve künye bandı
            # tablodan okuyarak söyler (elle yazılmış bant iddiası yok).
            _gaz = unknown_pair_gas_reference()
            self.mu_chamber = _gaz['mu_chamber']['value']
            self.pr_chamber = _gaz['pr_chamber']['value']
            self.cp_chamber = _gaz['cp_chamber']['value']
            self.mu_chamber_source = _gaz['mu_chamber']['basis']
            self.pr_chamber_source = _gaz['pr_chamber']['basis']
            self.cp_chamber_source = _gaz['cp_chamber']['basis']
            self.chamber_gas_property_band = {
                k: list(_gaz[k]['band']) for k in _gaz}
            self.dissociation_temp = LIQUID_UNKNOWN_PAIR_DISSOCIATION_TEMP
            self.frozen_performance = False
            self.combustion_data_source = 'not_modelled'
            self.combustion_validity = {
                'pc_range_ok': False, 'real_gas_warning': False,
                'extrapolated': True,
                'note': ('Propellant pair not in the built-in table; awaiting '
                         'a CEA solution.')}
            try:
                self._resolve_combustion_reference(None)
            except Exception:
                pass
            if self.combustion_data_source != 'rocketcea':
                # Ne tablo ne CEA: bu çift için yayımlanabilir bir yanma çözümü
                # YOK. Uydurma sayı döndürmek yerine açık gerekçeyle dur.
                self._warn('warn.liquid.propellant_pair_not_in_database',
                           'critical', fuel=str(self.fuel_type),
                           oxidizer=str(self.oxidizer_type))
                raise UnsupportedPropellantPairError(
                    f"Propellant pair '{self.fuel_type}'/'{self.oxidizer_type}' "
                    f"is not in the built-in combustion table and could not be "
                    f"solved with CEA, so no combustion solution exists for it. "
                    f"HRMA does not publish placeholder performance for an "
                    f"unmodelled pair. Choose a supported pair "
                    f"({', '.join(sorted({f'{f}/{o}' for f, o in combinations}))}) "
                    f"or one that maps to a CEA propellant card.",
                    fuel=self.fuel_type, oxidizer=self.oxidizer_type,
                    validity=dict(self.combustion_validity or {}))

            # P3B1-01 yoğunluk kapısı: çift CEA ile çözüldü ama türün
            # yoğunluğu ne tabloda ne kullanıcı girdisinde varsa donanım
            # zinciri (tank/hat/orifis/pompa) hesaplanamaz — sayı uydurmak
            # yerine açık gerekçeyle dur.
            for _rho, _ad, _rol, _alan in (
                    (self.rho_fuel, self.fuel_type, 'fuel', 'fuel_density'),
                    (self.rho_ox, self.oxidizer_type, 'oxidizer',
                     'oxidizer_density')):
                if _rho is None:
                    self._warn('warn.liquid.propellant_density_not_available',
                               'critical', propellant=str(_ad), role=_rol)
                    raise UnsupportedPropellantDensityError(
                        f"No liquid density is available for the {_rol} "
                        f"'{_ad}': it does not appear in any built-in "
                        f"propellant-table pair and no '{_alan}' override was "
                        f"supplied. HRMA does not publish a placeholder "
                        f"density, because tank volume, feed-line diameter, "
                        f"injector orifice area and pump power are all sized "
                        f"directly from it. Send '{_alan}' in kg/m3 (at the "
                        f"storage state) or choose a propellant that the "
                        f"built-in table covers.",
                        propellant=str(_ad), role=_rol)

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
                # ÖH A2 sivi-sogutma · 6. tur (SO1 D-1): CEA KURULU ama
                # çağrı düştüyse köprü gerekçeyi ve hazır uyarı kaydını
                # (validity.fallback_reason / fallback_warning, EN = TR)
                # taşıyor; burada yine de "RocketCEA kullanılamıyor"
                # basılıyordu — yanlış neden. Kayıt köprünün tek kaynağından
                # aynen geçer; şekli tutmazsa eski uyarıya düşülür
                # (fail-closed: tabloya iniş hiçbir yolda sessiz değil).
                kayit = _cea_call_failed_record(self.combustion_validity)
                if kayit is not None:
                    if kayit not in self.design_warnings:
                        self.design_warnings.append(kayit)
                else:
                    self._warn('warn.liquid.rocketcea_unavailable', 'warning')
            if self.combustion_validity.get('real_gas_warning'):
                self._warn_real_gas()
            return

        # 2) MOTORUN KENDİ lülesinde çözüm (2026-07-22 doğruluk düzeltmesi).
        #
        # DOĞRULUK REGRESYONUNUN KÖK NEDENİ: ilk entegrasyonda hem vakum hem
        # deniz seviyesi Isp'si SABİT referans alan oranlarından okunuyordu
        # (vakum ε=200, SL ortam-eşlenik ε). Bir motorun vakum Isp'si kendi
        # genişleme oranına kuvvetle bağlıdır (RS-25 ε=69'da 462.8 s, ε=200'de
        # 478.1 s — %3.3 fark), bu yüzden ε=200 referansı motor tahmini olarak
        # kullanıldığında sistematik ve büyük bir aşırı-tahmin doğuruyordu.
        # Artık her iki Isp de TASARIM ε'sunda (kullanıcı girdisi ya da
        # ortam-eşlenik lüle) çözülür; ε=200 yalnız 'itici kapasitesi'
        # referansı olarak raporlanır.
        eps_design, gamma_eff, iterations = self._solve_design_expansion(
            cea_bridge, fallback, float(vac['gamma_chamber']))

        des = cea_bridge.get_combustion_properties(
            self.fuel_type, self.oxidizer_type, float(self.P_c),
            float(self.MR), expansion_ratio=eps_design,
            ambient_bar=float(self.P_a), fallback=fallback)

        isp_sl = des.get('isp_sl_s')
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
            self._warn('warn.liquid.cea_ambient_isp_failed', 'warning')

        self.propellant_name = getattr(self, 'propellant_name',
                                       f"{self.fuel_type.upper()}/"
                                       f"{self.oxidizer_type.upper()}")
        # IDEAL (kayıpsız CEA) referanslar — teslim verim zinciri bunların
        # üstüne _delivered_performance_efficiency ile uygulanır.
        self.isp_vac_ref = float(des['isp_vac_s'])
        self.isp_sl_ref = float(isp_sl)
        self.c_star_ref = float(vac['c_star_m_s'])
        self.isp_vac_frozen_ref = des.get('isp_vac_frozen_s')
        self.T_c = float(vac['tc_k'])
        # gamma: izentropik alan/CF bağıntılarında CEA'nın DENGE oda gamma'sı
        # (LOX/LH2'de ~1.147) kullanılamaz — o cp'si reaksiyon ısısını içeren
        # bir termodinamik türevdir, lüle genişlemesinin efektif üssü değil.
        # gamma_eff, CF_1D(ε, γ) = g0·Isp_CEA(ε)/c*_CEA denklemini sağlayan
        # EŞDEĞER izentropik üstür (Sutton & Biblarz 9th ed. Böl. 3: gamma
        # lüle boyunca değişir, pratikte ortalama/eşdeğer bir değer kullanılır).
        self.gamma_chamber_cea = float(vac['gamma_chamber'])
        self.gamma_throat_cea = float(vac.get('gamma_throat')
                                      or vac['gamma_chamber'])
        self.gamma_ref = float(gamma_eff)
        self.gamma_effective_source = (
            f"equivalent isentropic exponent reproducing the CEA thrust "
            f"coefficient at epsilon={eps_design:.1f} "
            f"(CEA chamber gamma {self.gamma_chamber_cea:.4f}, "
            f"throat {self.gamma_throat_cea:.4f}); {iterations} iteration(s)")
        self.mw = float(vac['mw_g_mol'])
        if vac.get('cp_chamber'):
            self.cp_chamber = float(vac['cp_chamber'])
            self.cp_chamber_source = (
                'CEA equilibrium chamber cp at the solved (Pc, O/F)')
        self.design_reference_expansion_ratio = float(eps_design)
        self.sl_reference_expansion_ratio = float(eps_design)
        # İtici KAPASİTE referansı (motor performansı değil, bkz. sabit yorumu)
        self.isp_vac_capability_ref = float(vac['isp_vac_s'])
        self.isp_vac_capability_eps = VACUUM_REFERENCE_EPS
        if self.combustion_validity.get('real_gas_warning'):
            self._warn_real_gas()

        # Tablo dışı çift CEA ile çözüldüyse temel alanların tamamı artık
        # tanımlı olmalı (isp/c* zinciri _calculate_mixture_ratio_effects
        # üzerinden kurulur).
        if table_props is None:
            self.optimal_mr = getattr(self, 'optimal_mr', float(self.MR))
            # P3B1-04: "optimum" alanına kullanıcının ÇALIŞMA O/F'sini
            # koymak optimumu çözmek değildir — alan çözülemezse boş kalır
            # ve künyesi bunu söyler (aşağıda CEA taraması doldurur).
            if getattr(self, 'optimal_mr_thrust', None) is None:
                self.optimal_mr_thrust = None
                self.optimal_mr_thrust_source = 'not_modelled'
        # CANLI CEA yolunda optimum O/F ARTIK HESAPLANIR (2026-07-23).
        # Eskiden statik tablodan okunuyor ya da kullanıcının 'of_max_isp'
        # girdisinden alınıyordu; ikisi de gerçek Pc'deki kimyayı temsil
        # etmiyordu. Optimum, itici çiftinin ve oda basıncının bir SONUCUdur,
        # kullanıcı tercihi değildir — bu yüzden çözülür ve raporlanır.
        if self.combustion_data_source == 'rocketcea':
            self._solve_optimal_mixture_ratio(cea_bridge, fallback)
        self._calculate_mixture_ratio_effects()

    def _solve_optimal_mixture_ratio(self, cea_bridge, fallback,
                                     n_points=OF_OPTIMUM_SCAN_POINTS):
        """Vakum Isp'yi maksimize eden O/F'yi CEA taramasıyla çözer.

        Tarama bandı stokiyometri etrafında geniş tutulur ve çözüm parabolik
        tepe uydurmasıyla ızgara adımının altına iner. cea_bridge çağrıları
        önbelleklidir; aynı (yakıt, oksitleyici, Pc) için tarama bir kez
        yapılır. Çözülemezse mevcut değerler korunur ve sessizce geçilmez —
        'optimal_mr_source' alanı hangi yoldan geldiğini bildirir.

        Maksimum İTKİ O/F'si maksimum Isp'ninkinden daha YÜKSEKtir ve artık
        AYNI tarama makinesiyle ikinci bir ölçütte (Isp/c* = CF/g0)
        çözülür; kaynağı 'optimal_mr_thrust_source' ile yayımlanır. Eski
        davranışta bu alan statik tablodan geliyor, Pc'yle hiç oynamıyor ve
        yönü modülün kendi beyanının tersi çıkıyordu (P3B1-04).
        """
        eps = float(getattr(self, 'design_reference_expansion_ratio', 0)
                    or VACUUM_REFERENCE_EPS)
        # KULLANICI GİRDİSİ EZİLMEZ (P3B1-08, kardeşi P3B1-04 ile simetrik).
        # 'of_max_isp' /calculate_liquid ucunun hâlâ kabul ettiği bir alandır
        # (tests/test_sivi_form_alanlari.py:75). Eskiden değer _apply_overrides
        # içinde okunuyor, künyesi 'user input (of_max_isp)' yazılıyor ve
        # HEMEN ARDINDAN bu tarama onu sessizce eziyordu: ölçüldü (once.json)
        # 1,8 / 2,577 / 3,6 / 4,0 gönderilen dört koşunun DÖRDÜ de aynı
        # 2,53096'yı döndürdü, hiçbir uyarı ve hiçbir beyan üretmedi. Alan
        # ölü girdiye dönmüştü. Değer artık kullanıcının kalır; künye
        # 'çözüldü' ile 'kullanıcı yazdı'yı ayırt eder.
        if getattr(self, 'optimal_mr_source',
                   None) == 'user input (of_max_isp)':
            best_mr = None
        else:
            best_mr = _optimal_mr_scan_cached(
                str(self.fuel_type), str(self.oxidizer_type),
                round(float(self.P_c), 1), round(eps, 2), int(n_points),
                'isp')
        # P3B1-04 (ÖH D15): İTKİ optimumu artık ÇÖZÜLÜYOR — eskiden statik
        # tablodan geliyordu ve ölçüldü (once.json): rp1/lox'ta Pc=40/100/200
        # bar'ın ÜÇÜNDE de 2,2700'de çakılıydı (Isp optimumu 2,4503 -> 2,7322
        # hareket ederken), üstelik yön modülün KENDİ beyanının tersiydi
        # (tablodaki 6 çiftin 6'sında da of_thrust < of_isp). Doğru yön:
        # F ∝ Isp/c*, ve c* zenginleşmeyle düştüğü için itki tepesi Isp
        # tepesinin SAĞINDADIR.
        # KULLANICI GİRDİSİ EZİLMEZ (P3B1-04, kalemin (d) şıkkı).
        # 'of_max_thrust' /calculate_liquid ucunun hâlâ kabul ettiği bir
        # alandır (tests/test_sivi_form_alanlari.py:76). Kullanıcı yazdığı
        # hâlde tarama sonucunu basmak alanı ÖLÜ GİRDİye çevirir: üç ayrı
        # değer gönderilir, aynı yanıt döner (P3B1-08'de of_max_isp kolunda
        # ölçülen kusurun aynısı). Değer kullanıcının kalır; künye 'user
        # input (of_max_thrust)' der, böylece 'çözüldü' ile 'kullanıcı yazdı'
        # yaprakta ayırt edilir.
        if getattr(self, 'optimal_mr_thrust_source',
                   None) == 'user input (of_max_thrust)':
            best_mr_thrust = None
        else:
            best_mr_thrust = _optimal_mr_scan_cached(
                str(self.fuel_type), str(self.oxidizer_type),
                round(float(self.P_c), 1), round(eps, 2), int(n_points),
                'thrust')
            if best_mr_thrust is None:
                self.optimal_mr_thrust = None
                self.optimal_mr_thrust_source = 'not_solved'
            else:
                self.optimal_mr_thrust = float(best_mr_thrust)
                self.optimal_mr_thrust_source = (
                    'cea_scan (max Isp/c*, i.e. max CF)')
        if best_mr is None:
            # Kullanıcı yazdıysa DEĞER VE KÜNYE KORUNUR (P3B1-08); yalnız
            # tarama gerçekten çözülemediğinde 'not_solved' yazılır.
            if getattr(self, 'optimal_mr_source',
                       None) != 'user input (of_max_isp)':
                self.optimal_mr_source = 'not_solved'
            return
        self.optimal_mr = float(best_mr)
        self.optimal_mr_source = 'cea_scan'

    def _matched_expansion_ratio(self, gamma):
        """Ortam basıncına eşlenik (optimum) genişleme oranı.

        M_e = sqrt(2/(γ-1)·[(P_c/P_a)^((γ-1)/γ) − 1]); ε = A/A*(M_e)
        (Sutton & Biblarz 9th ed., Eq. 3-25 ve 3-14).
        """
        g = float(gamma)
        m_opt = np.sqrt(2.0 / (g - 1.0)
                        * ((self.P_c / self.P_a) ** ((g - 1.0) / g) - 1.0))
        return max(float(self._area_ratio_from_mach(max(m_opt, 1.0001), g)),
                   1.6)

    def _equivalent_gamma(self, eps, cf_target):
        """CF_1D(ε, γ, vakum) = cf_target denklemini sağlayan eşdeğer γ.

        CEA'nın (çok türlü, denge) genişlemesini HRMA'nın tek-γ izentropik
        bağıntılarına taşıyan köprüdür; hiçbir kalibrasyon katsayısı içermez.
        Kök bulunamazsa None döner (çağıran CEA boğaz gamma'sına düşer).
        """
        from scipy.optimize import brentq

        def residual(g):
            cf, _ = self._cf_ideal(eps, g, 0.0)
            return cf - cf_target

        try:
            lo, hi = 1.05, 1.45
            if residual(lo) * residual(hi) > 0:
                return None
            return float(brentq(residual, lo, hi, xtol=1e-6))
        except Exception:
            return None

    def _cf_ideal(self, expansion_ratio, gamma, ambient_bar):
        """(CF, P_e[bar]) — self.gamma'dan BAĞIMSIZ, γ parametreli sürüm."""
        g = float(gamma)
        m_e = self._mach_from_area_ratio_supersonic(expansion_ratio, g)
        pe_bar = self.P_c * (1.0 + (g - 1.0) / 2.0 * m_e ** 2) ** (-g / (g - 1.0))
        cf = (self._cf_momentum(pe_bar / self.P_c, g)
              + expansion_ratio * (pe_bar - ambient_bar) / self.P_c)
        return float(cf), float(pe_bar)

    def _solve_design_expansion(self, cea_bridge, fallback, gamma_seed):
        """(ε_tasarım, γ_eşdeğer, iterasyon) — motorun KENDİ lülesi.

        Kullanıcı genişleme oranı girdiyse ε sabittir ve yalnız γ_eşdeğer
        çözülür. Girmediyse ε ortam-eşlenik lüledir; ε ile γ birbirine bağlı
        olduğundan sabit-nokta iterasyonu yapılır (2-3 tur yeter).
        """
        eps_user = getattr(self, 'expansion_ratio_input', None)
        gamma = float(gamma_seed)
        eps = (float(eps_user) if eps_user is not None
               else self._matched_expansion_ratio(gamma))
        iterations = 0
        for _ in range(4):
            iterations += 1
            data = cea_bridge.get_combustion_properties(
                self.fuel_type, self.oxidizer_type, float(self.P_c),
                float(self.MR), expansion_ratio=eps, fallback=fallback)
            isp_vac = data.get('isp_vac_s')
            c_star = data.get('c_star_m_s')
            if not isp_vac or not c_star:
                break
            g_new = self._equivalent_gamma(eps, isp_vac * self.g0 / c_star)
            if g_new is None:
                gamma = float(data.get('gamma_throat') or gamma)
                break
            gamma = g_new
            if eps_user is not None:
                break
            eps_new = self._matched_expansion_ratio(gamma)
            converged = abs(eps_new - eps) <= 1e-3 * max(eps, 1.0)
            eps = eps_new
            if converged:
                break
        return float(eps), float(gamma), iterations

    def _warn_real_gas(self):
        """Pc >= 300 bar ideal-gaz CEA uyarısı (kullanıcıya görünür)."""
        self._warn('warn.liquid.real_gas_regime', 'warning',
                   pc_bar=float(self.P_c))

    # ------------------------------------------------------------------
    # TESLİM (delivered) performans zinciri — 2026-07-22 doğruluk düzeltmesi
    # ------------------------------------------------------------------
    def _divergence_efficiency(self):
        """(λ, kaynak) — lüle sapma verimi, SEÇİLEN kontura göre.

        Konik lülede λ = (1+cos α)/2 (Sutton & Biblarz 9th ed., Eq. 3-34);
        çan (bell) konturunda bu bağıntı geçerli DEĞİLDİR (çıkış açısı küçük
        olsa da akış tam eksenel değildir), bu yüzden Rao-optimize çan için
        yayımlanmış λ değeri kullanılır (hrma.constants.LAMBDA_BELL = 0.985,
        Sutton & Biblarz 9th ed.) — her iki değer de merkezî sabit
        dosyasındadır, burada yeniden tanımlanmaz.
        """
        ntype = getattr(self, 'nozzle_type', NOZZLE_TYPE_DEFAULT)
        geom = NOZZLE_TYPE_GEOMETRY.get(ntype,
                                        NOZZLE_TYPE_GEOMETRY[NOZZLE_TYPE_DEFAULT])
        if ntype == 'conical':
            lam = float(lambda_conical(geom['half_angle']))
            src = (f"conical divergence lambda=(1+cos {geom['half_angle']:.1f} "
                   f"deg)/2 (Sutton & Biblarz 9th ed., Eq. 3-34)")
        else:
            # ÖH D21 · OH-D20-02: çan λ'sı artık KONTURA bağlı
            # (LAMBDA_BELL_CONTOUR_SOURCE). Referans kontur yayımlanan
            # değeri aynen alır; öteki çanlar eşdeğer-koni ORANIyla
            # taşınır.
            ref = NOZZLE_TYPE_GEOMETRY[LAMBDA_BELL_REFERENCE_CONTOUR]
            a_ref = 0.5 * (float(ref['half_angle'])
                           + float(ref['exit_angle']))
            a_bu = 0.5 * (float(geom['half_angle'])
                          + float(geom['exit_angle']))
            oran = float(lambda_conical(a_bu)) / float(lambda_conical(a_ref))
            lam = float(LAMBDA_BELL) * oran
            src = (LAMBDA_BELL_CONTOUR_SOURCE
                   + f" This contour: mean wall angle {a_bu:.2f} deg vs "
                     f"{a_ref:.2f} deg for the reference "
                     f"'{LAMBDA_BELL_REFERENCE_CONTOUR}', ratio "
                     f"{oran:.6f}, lambda {lam:.6f}.")
            if not geom.get('modelled', True):
                src += (f"; the '{ntype}' contour itself is not modelled and "
                        f"is treated as an 80% bell")
        return lam, src

    def _kinetic_efficiency(self, isp_shifting, isp_frozen, throat_diameter):
        """(η_kinetik, tanı) — sonlu-hız kimyası kaybı.

        Gerçek lüle akışı DONMUŞ (ODF) ile KAYAN DENGE (ODE) arasındadır.
        Harman kesri, HRMA'nın kendi (bu görevden ÖNCE yazılmış ve
        kaynaklandırılmış) `hrma.analysis.kinetic_efficiency` 'engineering'
        seviyesinden gelir: Damköhler benzeri parametre, oda kalış süresi
        t_res = L*·rho_c·c*/P_c (Sutton & Biblarz 9th ed. Eq. 8-9) ve
        üç-cisimli rekombinasyon zamanı tau ∝ P^-2 (Bray 1959; Vincenti &
        Kruger Böl. 8). Buradaki hiçbir katsayı bu görevde ayarlanmadı.

        CEA donmuş değeri yoksa (statik tablo yolu) kinetik kayıp
        ÇÖZÜLMEZ: η = 1.0 ve tanı 'not_modelled'.
        """
        if not isp_shifting or not isp_frozen or isp_frozen >= isp_shifting:
            return 1.0, {'model': 'not_modelled',
                         'note': ('CEA frozen expansion value unavailable; '
                                  'the finite-rate (kinetic) loss is not '
                                  'resolved and no loss is applied.')}
        try:
            from hrma.analysis.kinetic_efficiency import KineticEfficiency
            mw = float(getattr(self, 'mw', 22.0))
            rho_c = (float(self.P_c) * PA_PER_BAR
                     / ((R_UNIVERSAL / mw) * float(self.T_c)))
            cres = {
                'performance': {'c_star': float(self.c_star_ref),
                                'isp_frozen': float(isp_frozen),
                                'isp_shifting': float(isp_shifting)},
                'conditions': {'chamber': {'P': float(self.P_c),
                                           'T': float(self.T_c)}},
                'compositions': {'chamber': {'molecular_weight': mw,
                                             'density': rho_c}},
            }
            res = KineticEfficiency().evaluate(
                combustion_results=cres, fidelity='engineering',
                chamber_pressure=float(self.P_c),
                characteristic_length=float(getattr(self, 'L_star',
                                                    L_STAR_DEFAULT_M)),
                throat_diameter=throat_diameter)
        except Exception as exc:
            return 1.0, {'model': 'not_modelled',
                         'note': f'kinetic correlation unavailable ({exc})'}
        eta = float(res['isp_predicted']) / float(isp_shifting)
        return eta, {
            'model': 'kinetic_efficiency (engineering, JANNAF-style blend)',
            'isp_shifting_s': float(isp_shifting),
            'isp_frozen_s': float(isp_frozen),
            'isp_predicted_s': float(res['isp_predicted']),
            'kinetic_loss_pct': float(res['kinetic_loss_pct']),
            'loss_band_pct': list(res['loss_band_pct']),
            'damkohler': res['diagnostics'].get('damkohler'),
            'note': res['model_note'],
        }

    def _estimate_throat_diameter(self, isp_sl_ideal):
        """Geometri henüz çözülmeden boğaz çapı KESTİRİMİ [m] veya None.

        Kinetik korelasyonun boyut faktörü için gerekir (büyük lüle daha
        yavaş genişler, akış dengeye daha yakın kalır). d_t = 2·sqrt(A_t/π),
        A_t = ṁ·c*/(P_c·C_D), ṁ = F/(Isp_sl·g0).

        2026-07-29 beyan denetimi: burada eskiden kullanıcının girdiği boğaz
        çapı varsa DOĞRUDAN o kullanılıyordu. Boğaz alanı serbest değişken
        değildir — verilen itki ve oda basıncında A_t kütle dengesinden çıkar
        (motor bunu zaten 'warn.liquid.throat_diameter_is_output' ile söylüyor
        ve geometriyi kendi d_t'siyle kuruyor). Kullanıcının değeri yalnız bu
        korelasyona sızdığında kinetik kayıp, RAPORLANANDAN BAŞKA bir motorun
        boğazıyla hesaplanıyordu (ölçüm: 95 mm girdi -> 30.7 mm geometri, 781
        çıktı yaprağı kayıyordu) ve alan 'karşılaştırma amaçlı' diye beyan
        edildiği hâlde çözümü sürüklüyordu. Kestirim artık her koşulda
        motorun kendi kütle dengesinden gelir.
        """
        # (Buradaki 'GECICI GERI ALMA' notlu erken donus 31 Tem 2026'da
        # kaldirildi: yukaridaki gerekce uygulanmis gorunuyordu ama kullanicinin
        # degeri hala dogrudan donuyordu, yani beyan ile davranis celisiyordu.)
        try:
            if not isp_sl_ideal or isp_sl_ideal <= 0:
                return None
            mdot = float(self.F) / (float(isp_sl_ideal) * self.g0)
            cd = self._throat_discharge_coefficient()
            a_t = mdot * float(self.c_star_ref) / (float(self.P_c)
                                                   * PA_PER_BAR * cd)
            return float(2.0 * np.sqrt(a_t / np.pi))
        except Exception:
            return None

    def _delivered_performance_efficiency(self):
        """CEA IDEAL -> TESLİM Isp verim zinciri (tek doğruluk kaynağı).

        Isp_teslim = Isp_CEA(ε) · η_c* · λ_sapma · η_sürtünme · η_kinetik
        c*_teslim  = c*_CEA · η_c*
        (JANNAF basitleştirilmiş performans metodolojisi; Sutton & Biblarz
        9th ed. Böl. 3.5.)

        η_c* kullanıcı 'combustion_efficiency' girdisinden gelir; GİRİLMEZSE
        1.0 alınır — enjektör/karışım kalitesi tasarım girdilerinden
        türetilemez ve UYDURULMAZ. Bunun anlamı çıktıda açıkça yazılır:
        varsayılan sonuç 'mükemmel enerji salımı' üst sınırıdır.
        """
        eta_cs = float(getattr(self, 'eta_c_star', DELIVERED_ETA_CSTAR_DEFAULT)
                       or DELIVERED_ETA_CSTAR_DEFAULT)
        # ÖH D21 · P3B4-11: künye anahtarın VARLIĞINDAN değil, KABUL
        # kararının tek tanım noktasından (self.eta_c_star_source, bkz.
        # _apply_overrides) okunur. ÖLÇÜLDÜ (once.json P3B4-11
        # 'motor_red_300'): combustion_efficiency=300 % bant dışı olduğu
        # için reddediliyor (eta_c_star 1,000 kalıyor, kullanıcıya
        # warn.liquid.input_out_of_range gidiyor) ama bu künye yine de
        # 'user input (combustion efficiency)' diyordu — aynı motorun
        # eta_c_star_source alanıysa doğru şekilde 'not supplied'. Tek
        # yanıtta aynı büyüklük için iki çelişik köken kalamaz.
        cs_source = str(getattr(
            self, 'eta_c_star_source',
            'not supplied -> ideal energy release (1.000) assumed; real '
            'engines deliver 0.92-0.99 (Sutton & Biblarz 9th ed., Ch. 5)'))
        lam, lam_source = self._divergence_efficiency()
        eta_f = 1.0 - NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT
        f_source = (f"{NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT * 100:.1f}% "
                    f"friction / boundary-layer thrust loss (typical 0.5-2%, "
                    f"Sutton & Biblarz 9th ed. Sec. 3.5; shared constant with "
                    f"the quasi-1D nozzle model)")
        d_t = self._estimate_throat_diameter(getattr(self, 'isp_sl_ref', None))
        eta_kin, kin_diag = self._kinetic_efficiency(
            getattr(self, 'isp_vac_ref', None),
            getattr(self, 'isp_vac_frozen_ref', None), d_t)
        eta_nozzle = lam * eta_f * eta_kin
        return {
            'eta_c_star': eta_cs,
            'eta_c_star_source': cs_source,
            'lambda_divergence': lam,
            'lambda_divergence_source': lam_source,
            'eta_friction': eta_f,
            'eta_friction_source': f_source,
            'eta_kinetic': eta_kin,
            'kinetic': kin_diag,
            'eta_nozzle': eta_nozzle,
            'eta_isp': eta_cs * eta_nozzle,
            'throat_diameter_estimate_m': d_t,
            'model': ('JANNAF-style delivered-performance chain: '
                      'Isp_delivered = Isp_CEA(eps) x eta_c* x lambda_div x '
                      'eta_friction x eta_kinetic; c*_delivered = c*_CEA x '
                      'eta_c* (Sutton & Biblarz 9th ed. Sec. 3.5)'),
        }

    def _finalize_performance_reference(self):
        """Girdi katmanı bittikten sonra performans referansını tazeler.

        _set_propellant_properties kurucunun BAŞINDA çalışır; kullanıcının
        genişleme oranı / lüle tipi / c* verimi girdileri henüz okunmamıştır.
        Bu adım, girdiler bağlandıktan sonra:
          1) CEA çözümünü motorun GERÇEK tasarım ε'sunda yeniler,
          2) teslim verim zincirini kurar ve uygular.
        Statik tablo yolunda (RocketCEA yok) yalnız η_c* uygulanır: tablo
        değerleri zaten teslim seviyesine demirli sayılardır (örn. LH2/LOX
        451.8 s = RS-25 teslim Isp'si), üstlerine ikinci bir lüle kaybı
        zinciri binerse ÇİFT SAYIM olur.
        """
        if getattr(self, 'combustion_data_source', '') == 'rocketcea':
            try:
                self._resolve_combustion_reference(
                    getattr(self, '_table_props', None))
            except Exception as exc:
                self._warn('warn.liquid.combustion_reference_refresh_failed',
                           'warning', detail=str(exc))
            self._delivered_eff = self._delivered_performance_efficiency()
            self._calculate_mixture_ratio_effects()
            return

        # Statik tablo / muhafazakâr tahmin yolu: eski davranış (yalnız η_c*).
        eta_cs = float(getattr(self, 'eta_c_star', 1.0) or 1.0)
        if eta_cs != 1.0 and hasattr(self, 'c_star'):
            self.c_star = self.c_star * eta_cs
            self.c_star_effective = self.c_star
            self.isp_sl = self.isp_sl * eta_cs
            self.isp_vac = self.isp_vac * eta_cs
        self._delivered_eff = {
            'eta_c_star': eta_cs,
            # ÖH D21 · P3B4-11: künye anahtarın VARLIĞINDAN kuruluyordu.
            # ÖLÇÜLDÜ (once.json P3B4-11 'motor_red_300'):
            # combustion_efficiency=300 % bandın (50-100) dışında olduğu
            # için REDDEDİLİYOR (eta_c_star 1,000 kalıyor) ama bu künye
            # yine 'user input (combustion efficiency)' diyordu; aynı
            # motorun eta_c_star_source alanı ise doğru şekilde 'not
            # supplied' diyordu - tek yanıtta aynı büyüklük için iki
            # çelişik köken. Künye artık KABUL kararının tek tanım
            # noktasından (self.eta_c_star_source) okunur.
            'eta_c_star_source': str(getattr(
                self, 'eta_c_star_source',
                'not supplied -> ideal energy release (1.000) assumed')),
            'eta_nozzle': 1.0,
            'eta_isp': eta_cs,
            'model': ('static anchor table path: the tabulated Isp values are '
                      'already delivered-level anchors, so no additional '
                      'nozzle-loss chain is applied (double counting)'),
        }

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
            # Referanslar CEA IDEAL değerleridir; TESLİM zinciri burada
            # uygulanır (tek yer — bu fonksiyon başka noktalardan da
            # çağrılabildiği için verim her çağrıda tutarlı kalır).
            eff = getattr(self, '_delivered_eff', None) or {}
            eta_isp = float(eff.get('eta_isp', 1.0))
            eta_cs = float(eff.get('eta_c_star', 1.0))
            self.isp_vac = self.isp_vac_ref * eta_isp
            self.c_star = self.c_star_ref * eta_cs
            self.c_star_effective = self.c_star
            # Deniz seviyesi Isp'si vakum Isp'sinden TAM bağıntıyla türetilir:
            #   F_sl = F_vac − P_a·A_e   ->   Isp_sl = Isp_vac − P_a·A_e/(ṁ·g0)
            #   A_e/ṁ = ε·c*_teslim/(P_c·C_D)
            # (Sutton & Biblarz 9th ed., Eq. 3-29). Bu ayrılmamış akış için
            # KESİN bir özdeşliktir ve motorun kendi ε'suyla tutarlıdır;
            # CEA'nın estimate_Ambient_Isp kestirimi ise aşırı genişlemede
            # kendi ayrılma varsayımını uygular (RS-25 ε=69'da 376 s verir,
            # ayrılmamış özdeşlik 367 s — ölçülen 366 s). Ayrılma riski
            # ayrıca uyarı olarak bildirilir.
            eps_ref = float(getattr(self, 'design_reference_expansion_ratio',
                                    0.0) or 0.0)
            isp_sl_exact = None
            if eps_ref > 0:
                cd = self._throat_discharge_coefficient()
                dp = (self.P_a * PA_PER_BAR * eps_ref * self.c_star
                      / (self.P_c * PA_PER_BAR * cd * self.g0))
                isp_sl_exact = self.isp_vac - dp
            if isp_sl_exact is not None and isp_sl_exact > 0:
                self.isp_sl_cea_ambient_ref = self.isp_sl_ref * eta_isp
                self.isp_sl = float(isp_sl_exact)
            else:
                self.isp_sl = self.isp_sl_ref * eta_isp
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
        # F1-1 BEYANI (2026-08-17): _apply_cycle_accounting BİLEREK bağlı
        # değildir (gerekçesi kendi docstring'inde); kesir bu yüzden bugün
        # her çevrimde 1.0 kalır ve bu durum sonuçta cycle_isp_accounting
        # bloğuyla açıkça yayımlanır.
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
        
        # --- ÖH D24 · P3B2-15 · UYARI STDOUT'A DEĞİL YANITA GİDER ----------
        # ÖLÇÜLDÜ (raw/OH/D24/sivi/a1/once.json, P3B2-15; taban 88a29d3):
        # sıvı motorda ALTI uyarı dalı (yedi print) yalnız ``print`` ile
        # sunucunun stdout'una yazıyordu: boğaz çapı emniyet sınırı dışında,
        # boğaz çapı olağan dışı, çok büyük çıkış çapı, çok büyük enjeksiyon
        # alanı, T/W bandı dışı, deniz seviyesi ve vakum Isp'si bandı dışı.
        # Bunların HİÇBİRİ yanıta girmiyordu — yani kullanıcı tarayıcıda
        # "boğaz çapı emniyet sınırlarının dışında" uyarısını göremiyor,
        # cümle yalnızca sunucu terminaline düşüyordu. Motorun ZATEN bir
        # kullanıcıya-görünür uyarı kanalı var (``_warn`` -> design_warnings
        # -> input_warnings); dalların tamamı o kanala taşındı. Bu bir
        # susturma değil, TERSİ: susan uyarılar konuşur oldu.
        # Import safety system
        try:
            from hrma.analysis.safety_limits import SafetyLimits
            safety = SafetyLimits()
            
            # Check throat diameter
            if not safety.check_throat_diameter(self.d_t, "Liquid Motor"):
                # ÖH D24 · P3B2-14/P3B2-15: bu dal SADECE stdout'a basıyordu
                # (aşağıdaki blok yorumuna bak). Uyarı artık yanıta girer.
                riskler = '; '.join(
                    str(v.get('risk', '')) for v in safety.violations
                    if str(v.get('parameter', '')).startswith(
                        'Throat Diameter')) or 'not stated'
                self._warn('warn.liquid.throat_diameter_outside_safe_bounds',
                           'critical',
                           d_t_mm=round(float(self.d_t) * 1000.0, 1),
                           risks=riskler)
        except ImportError:
            # Fallback to basic validation
            if self.d_t < 0.001 or self.d_t > 2.0:  # 1mm - 2000mm range
                self._warn('warn.liquid.throat_diameter_unusual', 'warning',
                           d_t_mm=round(float(self.d_t) * 1000.0, 1),
                           lo_mm=1.0, hi_mm=2000.0)
        
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
            # --- ÖH defter P3B2-09 (D18) ---------------------------------
            # Ölçüldü (once.json, 5 kN / Pc=10 bar = arayüzün KABUL ETTİĞİ
            # alt sınır): ortam-eşlenik ε 2,3'lerdeyken yayımlanan
            # expansion_ratio 2,50000 — taban SESSİZCE bağlıyordu. Buna
            # rağmen design_summary 'expansion ratio chosen at the
            # ambient-matched optimum (pe = pa)' diyordu ve nozzle_angles
            # çıkış basıncı olarak 1,01325 bar (P_atm ataması) yayımlarken
            # irtifa tablosu aynı lülenin izentropik çözümünü (0,94649 bar)
            # veriyordu: %7,05 fark, iki çıkış basıncı, tek uyarı yok.
            # Onarım: kırpma OLGUSU kaydedilir, çıkış basıncı KIRPILMIŞ
            # ε'dan izentropik olarak yeniden çözülür (P_atm ataması artık
            # yalnız kırpılmamış dalda geçerlidir) ve eniyileme iddiası
            # düşürülür. Sayı uydurulmaz: eşiklerin ikisi de burada TEK
            # tanımlıdır ve kırpılmamış değer adıyla yayımlanır.
            eps_unclamped = float(epsilon_optimal)
            epsilon_optimal, kirpma = self._clamp_expansion_ratio(
                epsilon_optimal, EXPANSION_RATIO_SOLVER_MIN,
                EXPANSION_RATIO_SOLVER_MAX)
            kirpma_bandi = (EXPANSION_RATIO_SOLVER_MIN,
                            EXPANSION_RATIO_SOLVER_MAX)
            self._expansion_optimum_fallback = False
        except Exception:
            # Son çare: kaba yaklaşım (eski fallback korunuyor)
            pressure_ratio = self.P_c / max(self.P_e, 1e-9)
            epsilon_optimal = pressure_ratio ** (1/g) * ((g+1)/2) ** ((g+1)/(2*(g-1)))
            # ÖH D20 / P3B2-09 ŞART md. 2: eşikler TEK tanımlı sabitten gelir
            # ve kırpma olgusu bu dalda da adıyla yayımlanır (eskiden
            # `max(4, min(eps, 300))` satır içiydi ve `kirpma = None`
            # atanıyordu, yani yedek dalda kırpma SESSİZDİ).
            eps_unclamped = float(epsilon_optimal)
            epsilon_optimal, kirpma = self._clamp_expansion_ratio(
                epsilon_optimal, EXPANSION_RATIO_FALLBACK_MIN,
                EXPANSION_RATIO_FALLBACK_MAX)
            kirpma_bandi = (EXPANSION_RATIO_FALLBACK_MIN,
                            EXPANSION_RATIO_FALLBACK_MAX)
            # Faz 4B (bulgu B1): bu dala düşüldüğünde ortam-eşlenik optimum
            # ÇÖZÜLEMEMİŞTİR; kaba bir yaklaşım kullanılır. design_summary
            # bunu okur ve o koşuyu 'OPTIMIZED' saymaz.
            self._expansion_optimum_fallback = True

        # P3B2-09: kırpma durumu YALNIZ tasarım irtifası (altitude=0) için
        # saklanır. calculate_altitude_performance bu fonksiyonu 0-100 km
        # arasında yeniden çağırıyor; bayrak irtifaya göre kapsanmazsa üst
        # irtifaların TAVAN kırpması design_summary'ye ve nozzle_angles'a
        # sızar (bugünkü çağrı sırası tesadüfen doğru sonucu veriyordu).
        if altitude == 0:
            self._expansion_unclamped = eps_unclamped
            self._expansion_clamp = kirpma
            self._expansion_clamp_band = kirpma_bandi
            # ÖH defter OH-D18-08 (D23): kırpma OLGUSU yalnız
            # ``nozzle_angles.expansion_ratio_clamp`` alanında duruyordu -
            # yani ekranın uyarı kanalına HİÇ düşmüyordu; kullanıcı
            # istediği ε ile çözülen ε'nun ayrıldığını ancak o alanı
            # okuyarak görebiliyordu. Olgu artık kendi uyarı koduyla
            # yayımlanır (sayı uydurulmaz; kırpılmamış değer de künyede).
            if kirpma:
                self._warn('warn.liquid.expansion_ratio_clamped', 'warning',
                           edge=str(kirpma),
                           eps_unclamped=round(float(eps_unclamped), 4),
                           eps_clamped=round(float(epsilon_optimal), 4),
                           lo=float(kirpma_bandi[0]),
                           hi=float(kirpma_bandi[1]))

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
                except Exception as _pe_err:
                    # --- ÖH D20 / P3B2-09 ŞART md. 1 (FAIL-CLOSED) --------
                    # Burada `pe_fixed = P_atm_bar` yazılıydı: çıkış basıncı
                    # ÇÖZÜLEMEDİĞİNDE sessizce ORTAM BASINCI yayımlanıyordu.
                    # Ölçüldü (once.json P3B2-09.cf_at_dustugunde): `_cf_at`
                    # düşürüldüğünde P_e = 1,01325 bar — yani kullanıcının
                    # SABİT ε'lu lülesi, hiçbir şey çözülmemişken tam olarak
                    # 'ortamla eşlenik' görünüyordu; oysa sabit ε'lu lülenin
                    # ortamla eşlenik olmaması o girdinin bütün anlamıdır.
                    # Artık sayı uydurulmaz: P_e NaN kalır ve hüküm
                    # `nozzle_angles.exit_pressure_status = 'NOT_SOLVED'`
                    # olarak alan adıyla ve gerekçesiyle yayımlanır.
                    self._exit_pressure_unsolved = (
                        f'{type(_pe_err).__name__}: {_pe_err}')
                    pe_fixed = float('nan')
            self.P_e = float(pe_fixed)
        else:
            self.expansion_ratio = epsilon_optimal
            self.expansion_ratio_matched = epsilon_optimal
            # P3B2-09: taban/tavan bağladıysa lüle ARTIK ortamla eşlenik
            # DEĞİLDİR; çıkış basıncı P_atm'e eşitlenemez, ε'dan izentropik
            # çözülür (irtifa tablosunun kullandığı aynı bağıntı → tek sayı).
            if kirpma is not None:
                try:
                    _, pe_clamped = self._cf_at(self.expansion_ratio,
                                                P_atm_bar)
                    self.P_e = float(pe_clamped)
                except Exception as _pe_err:
                    self._expansion_clamp_pe_unsolved = True
                    # ŞART md. 1 ile aynı sözleşme: çözülemeyen çıkış basıncı
                    # tek alandan (exit_pressure_status) okunur.
                    self._exit_pressure_unsolved = (
                        f'{type(_pe_err).__name__}: {_pe_err}')
                # KULLANICI UYARISI BU DALGADA EKLENEMEDİ (beyanlı engel):
                # yeni bir `warn.liquid.*` kodu i18n sözlüğünde (
                # hrma/static/js/i18n_common.js) EN+TR karşılığı olmadan
                # kullanıcıya ham anahtar olarak düşer ve
                # tests/test_engine_warning_i18n.py'yi kırar. O dosya D18'de
                # arayüz kulvarının sahasındadır (kardeş-dal ölçümü:
                # dalga18/arayuz diff'inde i18n_common.js var), bu yüzden
                # dokunulmadı. Kırpma olgusu YİNE DE sessiz değildir:
                # nozzle_angles.expansion_ratio_clamp / _unclamped /
                # expansion_ratio_source ve design_summary.status(_basis)
                # kırpmayı adıyla, sayısıyla ve gerekçesiyle yayımlar.
                pass
            # P3B1-07: statik tablo dalında vakum Isp'si ε=200 çapasında
            # kalıyordu; artık motorun KENDİ lülesine taşınır.
            self._static_path_vacuum_anchor()
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
            self._warn('warn.liquid.exit_diameter_large', 'warning',
                       d_e_m=round(float(self.d_e), 2), limit_m=5.0)
        
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
        # P3B2-02: hacim muhasebesi konverjan koniyi SAYAR (tek kaynak:
        # _chamber_volume_split). chamber_volume artık boğaza kadarki TOPLAM
        # hazne hacmidir ve chamber_length yalnız SİLİNDİRİN boyudur.
        (chamber_volume, convergent_volume, cylinder_volume,
         chamber_length, _l_conv_geo,
         l_star_achieved) = self._chamber_volume_split()
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
        # tipik 1.5*R_t alinir (boğaz konturu pratiği; KU-K1/SP-H1 K3/K9:
        # eski künye "Huzel & Huang, Modern Engineering" idi — o AIAA 1992
        # baskısı okunmadı; NASA SP-125 Örnek 4-3 s. 102 R'yi ORTALAMA kontur
        # yarıçapı alır — o fark ÖNEMLİ kalemi B4'tür, burada değişmez).
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
        # --- ÖH D20 / OH-D20-06 -------------------------------------------
        # Hazne ısı yükü D18 fizik-a2 sonrası 120,95 -> 1232,36 kW'a çıktı
        # (x10,2) ve bunun bir ALAN/BİRİM kusuru olup olmadığı sorulmuştu.
        # Ölçüldü (once.json OH-D20-06.ayristirma): kusur YOK, sıçrama
        # daralma oranının 12,25'ten 3,998'e düşmesinin iki ayrı etkisidir:
        #   (a) Bartz alan ölçeklemesi (A_t/A_c)^0.9 -> (1/12,25)^0.9 =
        #       0,1051'den (1/3,998)^0.9 = 0,2873'e, yani h_g x2,73;
        #   (b) aynı L* daha küçük CR'de daha UZUN/ İNCE hazne demektir,
        #       yanal alan A = pi*D_c*L_c buna göre büyür.
        # Üç çarpan da yayımlanır ki okuyan sayıyı KENDİ çarpabilsin; sayı
        # uydurulmuyor, hesabın kendi terimleri açılıyor.
        self._chamber_heat_closure = {
            'h_gas_chamber_W_m2K': float(h_g_chamber),
            'h_gas_throat_W_m2K': float(h_g_throat),
            'bartz_area_scaling_(At_over_Ac)^0.9': float(
                (A_throat / A_chamber_cross) ** 0.9),
            'sigma_ratio_chamber_over_throat': float(
                sigma_chamber / sigma_throat),
            'contraction_ratio': float(A_chamber_cross / max(A_throat, 1e-30)),
            'driving_delta_T_K': float(self.T_c - T_wall_hot),
            'chamber_lateral_area_m2': float(A_chamber),
            'chamber_heat_load_W': float(Q_chamber),
            'basis': (
                'Q_chamber = h_g_chamber * (T_c - T_wall_hot) * A_chamber '
                'with h_g_chamber = h_g_throat * (A_t/A_c)^0.9 * '
                '(sigma_chamber/sigma_throat) (Bartz 1957; Sutton & Biblarz '
                '9th ed. Eq. 8-23) and A_chamber = pi * D_c * L_c. Every '
                'factor above is the one the integral used: multiplying them '
                'reproduces chamber_heat_load exactly. The load scales as '
                'CR^-0.9 through the Bartz area term, so a contraction ratio '
                'change moves it by much more than the geometry change '
                'looks - this is the model, not a unit error'),
        }
        
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
        # --- ÖH D20 / P3B2-11 (Fable-D18 ŞARTI) ---------------------------
        # ŞART: bekçi ÜRÜN yolunu kilitlesin. Sürücü sıcaklık profili
        # buraya kadar yalnız KOD OKUYARAK doğrulanabiliyordu; yayımlanan
        # tek yaprak künye metniydi. İstasyon profili artık ÇIKTIDA durur:
        # her istasyonun A/A_t, M, T_static, T_aw değeri, entegrale girip
        # girmediğiyle birlikte. Sayılar entegrasyon döngüsünün KENDİ
        # değerleridir (yeniden hesap değil), bu yüzden döngüdeki çözücü
        # değişirse yayımlanan profil de değişir.
        istasyon_profili = []
        for section, L_section in (('conv', L_conv), ('div', L_div)):
            if L_section <= 0:
                continue
            dx = L_section / n_segments
            for i in range(n_segments):
                D1 = _diameter_at(section, i / n_segments)
                D2 = _diameter_at(section, (i + 1) / n_segments)
                D_local = 0.5 * (D1 + D2)
                A_local = np.pi * (D_local ** 2) / 4.0

                # --- ÖH defter P3B2-11 (D18) --------------------------
                # Eski kod:
                #   if A_local > A_t_geom:            # 'Downstream of throat'
                #       T_ratio = 1/(1+(γ-1)*0.1*ln(A/A_t))
                #   else:
                #       T_local = T_c                 # 'Upstream of throat'
                # İKİ kusur ölçüldü:
                #  (1) 0.1 ÇIPLAK bir katsayıydı — künyesi, kaynağı yok,
                #      yorumu yalnız 'Simplified'. İzentropik bağıntıyla
                #      (T/T_c = (1+(γ-1)/2·M²)^-1) hiçbir ilişkisi yok:
                #      ε=9,58'de T/T_c = 0,9634 veriyordu, izentropik değer
                #      0,5437. Bu dosyanın her Bartz terimi künyeliyken
                #      sürücü sıcaklık profili kaynaksızdı.
                #  (2) Etiket YANLIŞ, dal ÖLÜ: koşul A_local > A_t_geom,
                #      oysa YAKINSAK konide de A > A_t'dir; else dalı ancak
                #      tam boğazda çalışır (40 dilimin 0'ında çalıştı) ve
                #      'Upstream of throat' diye adlandırılmıştı.
                # Onarım: dal artık BÖLÜMDEN gelir (yakınsak = subsonik kök,
                # ıraksak = süpersonik kök) ve sıcaklık, CF/çıkış basıncı
                # zincirinin kullandığı AYNI izentropik bağıntıdan çözülür
                # (tek kaynak). Yeni fizik eklenmedi: modülün kendi
                # Eq. 3-7/3-14 çözücüsü ısı zincirine de bağlandı.
                area_ratio_local = max(A_local / A_t_geom, 1.0)
                T_local, M_local = self._isentropic_static_temperature(
                    self.T_c, area_ratio_local, self.gamma,
                    supersonic=(section == 'div'))

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
                istasyon_profili.append({
                    'section': ('convergent' if section == 'conv'
                                else 'divergent'),
                    'x_fraction_of_section': (i + 0.5) / n_segments,
                    'area_ratio': float(area_ratio_local),
                    'mach': float(M_local),
                    'static_temperature_K': float(T_local),
                    'adiabatic_wall_temperature_K': float(T_aw_local),
                    'heat_flux_W_m2': float(q_dot_local),
                    'in_heat_integral': True,
                })

        # Çıkış DÜZLEMİ istasyonu: entegrasyon dilimleri orta noktalarda
        # değerlendirildiği için son dilim çıkış düzlemine düşmez. ŞART'ın
        # istediği karşılaştırma (yaprak ⟷ _isentropic_static_temperature
        # (T_c, ε_çıkış, γ, True)) bu istasyondadır. Sıfır uzunluklu bir
        # sınırdır: ısı entegraline GİRMEZ ve bu, alanın yanında yazar.
        if L_div > 0 and A_t_geom > 0:
            eps_exit_geom = max((self.d_e / D_t) ** 2, 1.0)
            T_exit_st, M_exit_st = self._isentropic_static_temperature(
                self.T_c, eps_exit_geom, self.gamma, supersonic=True)
            istasyon_profili.append({
                'section': 'exit_plane',
                'x_fraction_of_section': 1.0,
                'area_ratio': float(eps_exit_geom),
                'mach': float(M_exit_st),
                'static_temperature_K': float(T_exit_st),
                'adiabatic_wall_temperature_K': float(
                    T_exit_st + r_recovery * (self.T_c - T_exit_st)),
                'heat_flux_W_m2': None,
                'in_heat_integral': False,
            })

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
        # (enerji dengesi; HRMA muhasebesi. KU-K1/SP-H1 K15: eski künye
        # "Huzel & Huang Ch. 4 film soğutma muhasebesi" idi; SP-125 Eş. 4-33,
        # s. 115 film verimi η_c içerir, bu modelde YOK — ÖNEMLİ kalemi B3).
        heat_to_regen = max(total_heat_load - film['film_heat_absorbed_w'],
                            0.0)

        # Cooling system sizing
        coolant_flow = 0
        pressure_drop = 0
        coolant_temp_rise = 0
        coolant_flow_basis = (
            'no regenerative jacket in this cooling type: the jacket flow is '
            'zero, not assumed')

        # Kanal sayısı/kesiti: kullanıcı girdisi ya da hazne çevresinden
        # hesap (sabit 80 değil — 2026-07-19 denetimi).
        n_channels, channel_width, channel_height, channel_source = \
            self._cooling_channel_geometry()
        v_coolant = 0.0
        reynolds = 0.0
        # uc-kapi devri: ceket yoksa cp de yayımlanmaz (None).
        cp_coolant = None
        cp_coolant_source = None
        # Süperkritik istasyon-marşlı çözüm sonucu (metan/LH2 rejeneratif).
        regen_march = None
        peak_heat_flux_kw = None   # marş çözerse oradan, yoksa Bartz'tan
        # ÖH D31 · OH-D25-25 — dump soğutmanın ceket ayağı fail-closed.
        _dump_jacket_not_modelled = (self.cooling_type == 'dump_cooling')
        wall_temp_source = ('user input (max wall temperature)'
                            if getattr(self, 'max_wall_temp_input', None)
                            is not None else
                            'assumed (cooling-type default)')
        if self.cooling_type in ('regenerative', 'film_cooling', 'dump_cooling'):
            # Use fuel as coolant (most common)
            coolant_flow_fraction = getattr(self, 'coolant_flow_fraction',
                                            COOLANT_FLOW_FRACTION_DEFAULT)
            # --- ÖH defter P3B2-10 (D18) ---------------------------------
            # Ölçüldü (once.json, 25 kN, film_cooling_percent=20):
            # fuel_flow 2,72726 kg/s; coolant_flow_rate 2,72726 (yakıtın
            # TAMAMI ceketten, fraction=1,0); film_cooling_flow 0,54545 →
            # TOPLAM 1,200 × mdot_fuel. Motor yakıtın %120'sini soğutucu
            # olarak harcıyordu. Fizikte film soğutucu yakıtın bir kısmını
            # cekettan AYIRIR (kütle korunumu, K15): iki debi aynı bütçeden
            # gelir. Ceket debisi artık film payı DÜŞÜLDÜKTEN sonra kalan
            # yakıttan alınır; böylece ceket + film <= mdot_fuel korunur ve
            # ceketin ΔT'si / cidar sıcaklığı iki kez iyimser olmaz.
            jacket_budget = max(float(self.mdot_fuel)
                                - float(film_cooling_flow), 0.0)
            coolant_flow = jacket_budget * coolant_flow_fraction
            coolant_flow_basis = (
                'regenerative jacket flow = (fuel flow - film coolant flow) '
                'x coolant_flow_fraction. The film coolant is bled from the '
                'SAME fuel budget upstream of the jacket (mass conservation; '
                'HRMA accounting, not a Huzel & Huang Ch. 4 model - the film '
                'efficiency of NASA SP-125 Eq. 4-33, p. 115 is not modelled), '
                'so jacket + film can never exceed the fuel flow')

            # Fuel properties for cooling
            # (2026-07-22: metan/LH2 için bu NBP sabitleri yalnız süperkritik
            # istasyon marşı KURULAMADIĞINDA yedek olarak kalır; marş
            # kurulursa cp/yoğunluk/viskozite CoolProp (T,P) bağımlıdır ve
            # cidar sıcaklığı ÇÖZÜLÜR — denetim bulgusu 2e.)
            # ÖH A2 sivi-sogutma (uc-kapi devri fuel_heat_capacity): cp artık
            # KURUCUDA çözülmüş tek değerden (kullanıcı > tablo > künyeli
            # varsayım; _resolve_coolant_cp). Yoğunluk aşağıda motorun kendi
            # itici yoğunluğudur; viskozite satırları yerel yedek olarak kalır.
            cp_coolant, cp_coolant_source = self._coolant_cp()
            if self.fuel_type == 'rp1':
                mu_coolant = 0.0012 # Pa·s
            elif self.fuel_type == 'lh2':
                mu_coolant = 0.000013
            elif self.fuel_type == 'methane':
                mu_coolant = 0.00011
            else:
                mu_coolant = 0.001
            if getattr(self, 'mu_fuel', None) is not None:
                mu_coolant = self.mu_fuel
            rho_coolant = self.rho_fuel

            # Temperature rise calculation (film kredisi düşülmüş yük)
            coolant_temp_rise = heat_to_regen / (coolant_flow * cp_coolant)

            # Kanal boyu: hazne + YAKINSAK koni + ıraksak koni (eski hâli
            # yakınsak koniyi hiç saymıyordu; basınç düşümü bu uzunlukla
            # doğru orantılı olduğundan sistematik olarak düşük çıkıyordu).
            channel_length = chamber_length + nozzle_axial_length
            # Denetçi Ş4 (4. tur): HRMA kanal sayısını boyutlandıramadıysa
            # (n_channels None — en az COOLING_CHANNEL_COUNT_MIN kanal bile
            # sığmıyor) ceket hidroliği HESAPLANMAZ: hız, Reynolds ve ΔP
            # None; istasyon marşı koşulmaz. Uydurma N ile sayı üretilmez.
            if n_channels is None:
                v_coolant = None
                reynolds = None
                pressure_drop = None
            else:

                # Kanal DERİNLİĞİ tasarım serbestliğidir (formda girdisi yok):
                # varsayılan kesitle hız tasarım hedefini aşıyorsa derinlik
                # hedefe göre büyütülür (üst sınıra kadar) ve etiketlenir —
                # büyük motorlarda 2 mm sabit derinlik fiziksel olmayan
                # 300+ m/s hızlar ve binlerce bar ΔP üretiyordu (2026-07-22).
                #
                # ÖH A2 sivi-sogutma · 6. tur (LH2 v_probe ⟷ coolant_velocity):
                # aşağıdaki sıvı yoğunluklu sonda YALNIZ yayımlanan hızın da
                # aynı sıvı yoğunluğundan geldiği yolda karar verir (RP-1 ve
                # süperkritik marşın kurulamadığı yedek). Süperkritik marş
                # çözülürse boyutlandırma marşın KENDİ hızıyla (istasyonun
                # yerel T, P'sindeki gerçek akışkan yoğunluğu) yeniden yapılır
                # — bkz. _size_supercritical_regen; bu yüzden sığma
                # ölçütünün derinliği ve künyesi burada saklanır.
                channel_height_geom = channel_height
                channel_source_geom = channel_source
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
                if self._supercritical_march_applies():
                    try:
                        regen_march, h_march, sizing_note = \
                            self._size_supercritical_regen(
                                coolant_flow, n_channels, channel_width,
                                channel_height_geom)
                    except Exception as exc:
                        regen_march = None
                        self._warn('warn.liquid.regen_march_failed', 'warning',
                                   fuel=str(self.fuel_type), detail=str(exc))
                    if regen_march is not None:
                        # Yayımlanan derinlik ve künyesi marşın boyutlandırdığı
                        # kesittir (sıvı yoğunluklu sondanın kararı atılır —
                        # yayımlanan hız onunla verilmiyor).
                        channel_height = h_march
                        channel_source = channel_source_geom + sizing_note
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
                        # --- P3B2-05 (ÖH D15) --------------------------------
                        # (1) İÇ ÇELİŞKİ: q_dot_chamber yukarıda MARŞ ÖNCESİ
                        #     cidarla (kullanıcının 800 K'sı) kuruluyordu,
                        #     T_wall_hot burada marş sonucuyla EZİLİYORDU, ve
                        #     ikisi AYNI sözlükte yayımlanıyordu. Ölçüldü
                        #     (once.json, methane/lox 25 kN): yayımlanan
                        #     chamber_heat_flux 4540,2 kW/m² 800 K cidara aitti,
                        #     yanındaki wall_temperature_hot ise 2107,7 K.
                        #     Yayımlanan akı artık MARŞIN KENDİ hazne payından
                        #     gelir (q = Q_chamber/A_chamber). Marş bu dalda
                        #     ısının tek kaynağıdır; Bartz'ı marş sonrası cidarla
                        #     yeniden değerlendirmek q·A_chamber ile Q_chamber'ı
                        #     ayırır ve Q_chamber + Q_nozzle = total_heat_load
                        #     muhasebesini bozardı. Bu yolla üç yaprak da tek
                        #     hesabı anlatır.
                        # (2) KULLANICININ LİMİTİ: aşıldığında SESSİZ kalınmaz;
                        #     limit, ulaşılan değer ve hüküm yayımlanır.
                        if A_chamber > 0:
                            q_dot_chamber = Q_chamber / A_chamber
                        limit_K = getattr(self, 'max_wall_temp_input', None)
                        if limit_K is not None and T_wall_hot > float(limit_K):
                            self._warn('warn.liquid.wall_temp_limit_exceeded',
                                       'critical',
                                       limit_K=round(float(limit_K), 1),
                                       solved_K=round(float(T_wall_hot), 1),
                                       ratio=round(float(T_wall_hot)
                                                   / float(limit_K), 2))
                        peak_heat_flux_kw = s['peak_heat_flux_MW_m2'] * 1000.0
                        wall_temp_source = ('solved (1D supercritical station '
                                            'march, Jackson correlation)')
                        for w in s.get('warnings', []):
                            # Alt modülün (regen_cooling) kendi metni params.detail
                            # olarak taşınır; o modül D-track kapsamı dışında.
                            self._warn('warn.liquid.regen_march_note', 'warning',
                                       detail=str(w))

        elif self.cooling_type == 'ablative':
            # Ablative cooling - no active coolant flow.
            # ÖH defter P3B2-13 (D23): burada ``ablative_thickness = 0.01``
            # ve ``ablative_recession_rate = 0.1e-3`` atanıyor, HİÇBİR yerden
            # okunmuyordu (soğutma sözlüğüne tek ablatif büyüklük girmiyordu).
            # Gerçek ablatif boyutlandırma ZATEN var ve ölçülüyor:
            # ``thermal_protection`` bloğu ``ThermalProtectionAnalyzer.
            # ablative_thickness(...)`` çağırır. İki ölü yerel sabit
            # SİLİNDİ; yerine ikinci bir kalınlık modeli KONMADI.
            pass
            
        # Kanal hızı / basınç düşümü pratik sınırların üstündeyse uyarılır
        # (hesap yine yapılır — kullanıcı kanal sayısını/kesitini görsün).
        if coolant_flow > 0 and n_channels is not None:
            if v_coolant > COOLANT_VELOCITY_LIMIT_MS:
                self._warn('warn.liquid.coolant_velocity_above_limit',
                           'warning', v_coolant=round(float(v_coolant)),
                           limit=round(float(COOLANT_VELOCITY_LIMIT_MS)),
                           n_channels=int(n_channels),
                           width_mm=round(float(channel_width) * 1000.0, 1),
                           height_mm=round(float(channel_height) * 1000.0, 1))
            if pressure_drop > COOLANT_DP_FRACTION_LIMIT * self.P_c:
                self._warn('warn.liquid.coolant_pressure_drop_high', 'warning',
                           dp_bar=round(float(pressure_drop), 1),
                           pct=round(float(pressure_drop)
                                     / max(float(self.P_c), 1e-9) * 100.0))

        # Soğutucu çıkış sıcaklığı kaynama noktasını aşıyorsa sessiz kalınmaz
        # (girdi: fuel_boiling_point; tek fazlı akış varsayımı bozulur).
        t_exit = getattr(self, 'coolant_inlet_temp',
                         COOLANT_INLET_TEMP_DEFAULT_K) + coolant_temp_rise
        t_boil = getattr(self, 'fuel_boiling_point', None)
        if t_boil is not None and coolant_flow > 0 and t_exit > t_boil:
            self._warn('warn.liquid.coolant_exit_above_boiling', 'warning',
                       t_exit=round(float(t_exit)),
                       t_boil=round(float(t_boil)))

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
            # P3B2-11: istasyon sürücü sıcaklığının künyesi.
            'nozzle_gas_temperature_basis': (
                'station static temperature from the isentropic relation '
                'T/T_c = (1 + (gamma-1)/2 * M^2)^-1 (Sutton & Biblarz 9th '
                'ed. Eq. 3-7) with M from the area ratio (Eq. 3-14): the '
                'SUBSONIC root in the convergent cone and the SUPERSONIC '
                'root in the divergent cone - the same solver the CF / exit '
                'pressure chain uses. The driving temperature is then the '
                'adiabatic wall temperature T_aw = T + r*(T_c - T), '
                'r = Pr^(1/3)'),
            # OH-D20-06: hazne ısı yükünün çarpan çarpan kapanışı.
            'chamber_heat_load_closure': getattr(
                self, '_chamber_heat_closure', None),
            # P3B2-11 (ŞART): künyenin ANLATTIĞI profilin KENDİSİ.
            'nozzle_station_profile': istasyon_profili,
            'nozzle_station_profile_basis': (
                'the stations of the nozzle heat integration loop, in the '
                'loop order (convergent cone first, then divergent cone), '
                'each evaluated at the segment mid point; the last entry is '
                'the exit PLANE (zero length, not part of the integral). '
                'static_temperature_K comes from '
                '_isentropic_static_temperature(T_c, A/A_t, gamma, root) - '
                'the subsonic root in the convergent cone, the supersonic '
                'root in the divergent cone - and '
                'adiabatic_wall_temperature_K = T + r*(T_c - T) with '
                'r = Pr^(1/3). These are the numbers the integral actually '
                'used, not a re-computation'),
            # ÖH D31 · OH-D25-25: dump soğutmada ceket debisi ve ΔP
            # YAYIMLANMAZ (bkz. DUMP_COOLING_BLEED_NOT_MODELLED).
            'coolant_flow_rate': (None if _dump_jacket_not_modelled
                                  else coolant_flow),  # kg/s
            'coolant_temperature_rise': coolant_temp_rise,  # K
            'cooling_pressure_drop': (None if _dump_jacket_not_modelled
                                      else pressure_drop),  # bar
            'wall_temperature_hot': T_wall_hot,  # K
            'wall_temperature_cold': T_wall_cold,  # K
            # 2026-07-22 (denetim madde 3): cidar sıcaklığının VARSAYIM mı
            # ÇÖZÜM mü olduğu artık açıkça raporlanır.
            'wall_temperature_source': wall_temp_source,
            # P3B2-05: kullanıcının cidar sıcaklığı limiti ve ona göre
            # HÜKÜM aynı sözlükte yayımlanır — yapısal emniyet zinciri
            # (structural_panel.js -> /analyze_structural_safety ->
            # structural_analysis.py) bu alanı okuyup malzemenin izin
            # verilen gerilmesini seçiyor; limitin sessizce aşılması o
            # hükmün girdisi oluyordu.
            'wall_temperature_limit_K': (
                float(self.max_wall_temp_input)
                if getattr(self, 'max_wall_temp_input', None) is not None
                else None),
            'wall_temperature_limit_status': (
                None if getattr(self, 'max_wall_temp_input', None) is None
                else ('EXCEEDED'
                      if T_wall_hot > float(self.max_wall_temp_input)
                      else 'MET')),
            # Isı akısının hangi cidar sıcaklığına ait olduğu artık
            # tektir: q = h_g*(T_c - wall_temperature_hot).
            'chamber_heat_flux_basis': (
                'chamber heat load divided by the chamber wetted area. When '
                'the 1D supercritical station march solves the wall (see '
                'wall_temperature_source), the march is the single source of '
                'the heat split, so this flux, chamber_heat_load and '
                'wall_temperature_hot all come from the same solution and '
                'chamber_heat_load + nozzle_heat_load = total_heat_load '
                'holds. Otherwise it is the Bartz chamber coefficient times '
                '(T_c - wall_temperature_hot) at the assumed wall.'),
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
            'convergent_half_angle_basis': CONVERGENT_HALF_ANGLE_BASIS,
            'cooled_channel_length': (chamber_length + nozzle_axial_length) * 1000,  # mm
            'chamber_surface_area': A_chamber,  # m² (hazne silindiri)
            'nozzle_surface_area': A_nozzle_total,  # m² (koni yanal, eğik uzunlukla)
            # Denetçi Ş4 (4. tur): HRMA boyutlandıramadıysa (n_channels None)
            # sayı yayımlanmaz — 0 = "çizilen kanal yok" (dump emsali,
            # OH-D25-25); nedeni channel_count_fit.status = 'not_sized'.
            'cooling_channels': (
                0 if (_dump_jacket_not_modelled or n_channels is None)
                else (n_channels if coolant_flow > 0 else 0)),
            'channel_width_mm': channel_width * 1000,
            'channel_width_basis': COOLING_CHANNEL_WIDTH_BASIS,
            'channel_height_mm': channel_height * 1000,
            'channel_height_basis': COOLING_CHANNEL_HEIGHT_BASIS,
            'channel_height_auto_sized': bool(
                channel_height > COOLING_CHANNEL_HEIGHT_DEFAULT_M + 1e-12),
            'channel_count_source': channel_source,
            # ÖH A2 sivi-sogutma · F-17: sığma ölçütü, sınırı ve hükmü sayının
            # YANINDA (tek tanım regen_cooling.channel_fit_limit). Ceket yoksa
            # (ablatif/ışınımsal, dump'ta ceket modellenmedi) blok yayımlanmaz.
            'channel_count_fit': (
                None if (_dump_jacket_not_modelled or not coolant_flow > 0)
                else getattr(self, '_channel_count_fit', None)),
            'coolant_velocity': v_coolant,  # m/s (kanal içi, hesaplanmış)
            # ÖH A2 sivi-sogutma (uc-kapi devri fuel_heat_capacity): toplu
            # ceket ΔT'sine giren cp ve künyesi sayının yanında (kurucuda
            # çözüldü; ceket yoksa None). Süperkritik marş çözdüyse ΔT marştan
            # gelir ve bu cp yalnız yedek zincirin değeridir (künye söyler).
            'coolant_heat_capacity': (None if _dump_jacket_not_modelled
                                      else cp_coolant),  # J/kg·K
            'coolant_heat_capacity_source': (
                None if (_dump_jacket_not_modelled or cp_coolant is None)
                else (cp_coolant_source + (
                    '; NOT used for the published temperature rise: the '
                    'supercritical station march solved it with CoolProp '
                    'properties' if regen_march is not None else ''))),
            'coolant_reynolds': reynolds,
            'coolant_inlet_temperature': getattr(
                self, 'coolant_inlet_temp', COOLANT_INLET_TEMP_DEFAULT_K),  # K
            'coolant_exit_temperature': getattr(
                self, 'coolant_inlet_temp',
                COOLANT_INLET_TEMP_DEFAULT_K) + coolant_temp_rise,  # K
            'coolant_flow_fraction': getattr(
                self, 'coolant_flow_fraction', COOLANT_FLOW_FRACTION_DEFAULT),
            # P3B2-10: ceket debisinin hangi bütçeden alındığı sayının yanında.
            'coolant_flow_rate_basis': (
                DUMP_COOLING_BLEED_NOT_MODELLED
                if _dump_jacket_not_modelled else coolant_flow_basis),
            'dump_cooling_jacket_status': (
                'NOT_MODELLED' if _dump_jacket_not_modelled else None),
            # Denetçi Ş4 (4. tur): ceket hidroliğinin (hız, Re, ΔP) HESAPLANIP
            # hesaplanmadığı makine-okur; 'not_computed' iken ΔP'yi seri
            # zincirde taşıyan tüketiciler (yakıt tankı basıncı, çevrim
            # dengesi) sayı üretmez.
            'jacket_hydraulics_status': (
                'not_computed' if (n_channels is None and coolant_flow > 0
                                   and not _dump_jacket_not_modelled)
                else None),
            'wall_temperature_default_basis': WALL_TEMP_DEFAULT_BASIS,
            'coolant_plus_film_flow_kg_s': float(coolant_flow
                                                 + film_cooling_flow),
            'coolant_plus_film_fraction_of_fuel': (
                float((coolant_flow + film_cooling_flow)
                      / max(float(self.mdot_fuel), 1e-12))),
            # P3B2-02: yayımlanan L* ÇİZİLEN geometrinin kendisidir
            # (V_toplam/A_t, konverjan koni dâhil). Eski satır istenen değeri
            # basıyordu; ölçüldü: 1,2 m yayımlanırken aynı yanıtın kendi
            # geometrisi 1,9144 m veriyordu (+%59,5).
            'l_star': l_star_achieved,  # m (çizilen)
            'l_star_requested': L_star,  # m (girdi / model tabanı)
            'l_star_source': getattr(self, 'l_star_source', 'model default'),
            'l_star_basis': (
                'characteristic length of the drawn chamber: (cylindrical '
                'volume + convergent cone volume) / throat area, Sutton & '
                'Biblarz 9th ed. Ch. 8. When the requested value is the '
                'model default and the convergent cone alone already exceeds '
                'it, the default is raised to what the geometry delivers '
                'instead of publishing a length the chamber does not have.'),
            # F2 (ÖH D18 fizik-a2): L* artık itici ÇİFTİNE anahtarlı bandın
            # ortasıdır; bant ve hangi satırdan geldiği sayının yanında durur.
            'l_star_band_m': list(getattr(self, 'l_star_band_m',
                                          L_STAR_GENERIC_BAND_M)),
            'l_star_band_source': getattr(self, 'l_star_band_source',
                                          'sp125_table_4_1_generic'),
            'l_star_table_source': L_STAR_TABLE_SOURCE,
            'contraction_ratio': (chamber_diameter / self.d_t) ** 2,
            'contraction_ratio_source': self._contraction_ratio_source(),
            'contraction_ratio_basis': self._contraction_ratio_basis(),
            'chamber_length_diameter_ratio': (
                float(chamber_length / chamber_diameter)
                if chamber_diameter else None),
            'chamber_length_diameter_band': list(
                CHAMBER_LENGTH_DIAMETER_BAND),
            'chamber_length_diameter_status': self._chamber_slenderness_status(
                chamber_length, chamber_diameter),
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
            if self._supercritical_march_applies():
                result['regen_supercritical'] = 'not_modelled'

        self._cooling_memo = (memo_key, copy.deepcopy(result))
        return result

    def _film_cooling_analysis(self, q_dot_chamber, chamber_diameter,
                               chamber_length):
        """Film soğutma enerji dengesi (2026-07-22, denetim madde 6).

        Model — sıvı film ısı-yutucu enerji dengesi (KU-K1/SP-H1 K15: eski
        künye "Huzel & Huang Ch. 4 muhasebesi" idi; SP-125 Eş. 4-33, s. 115 bir
        film verimi η_c %30-70 içerir, bu modelde YOK — ÖNEMLİ kalemi B3):
        film debisinin birim kütle ısı alma kapasitesi, hazne duvarına gelen
        akıyla karşılaştırılır; film TÜKENENE kadar duvarı korur:

            L_film = ṁ_film · Δh_film / (q_hazne · π · D_hazne)

        Δh_film (yutulabilir entalpi):
        * CH4/LH2: CoolProp GERÇEK entalpi farkı h(T_limit, Pc) − h(T_in, Pc)
          — süperkritik oda basıncında faz geçişi yoktur, gizli ısı ayrı
          terim olarak eklenmez (Bell et al. 2014, CoolProp).
        * RP-1: CoolProp'ta yok; duyulur ısı cp·ΔT alt sınırı kullanılır
          (MIL-DTL-25576 sıvı cp). KU H-14 (6 Eki 2026): eski metin
          "buharlaşma katkısı not_modelled (muhafazakâr)" diyordu; oda basıncı
          RP-1'in kritik basıncının üstündeyse (tipik sıvı motorlarda öyle;
          ASYA notu: Kim-Joh-Choi 2011, Park 2016) ayrı bir buharlaşma (gizli
          ısı) terimi yoktur — "buharlaşma kredisi" orada anlamsızdır.
          Eksik olan, süperkritik RP-1'in gerçek entalpi artışıdır; o da bu
          modelde yoktur ve öyle beyan edilir.
        T_limit = sıcak cidar hedef sıcaklığı (film cidarı korurken cidar
        hedefinden sıcak olamaz). Film tükenişi SONRASI gaz-film etkinliği
        (adyabatik duvar sıcaklığı sönümü) modellenmez ve açıkça söylenir
        (NASA SP-8124 kapsamındaki korelasyon ayrı iştir).
        """
        pct = float(getattr(self, 'film_cooling_percent', 0.0) or 0.0)
        out = {
            'film': 'none' if pct <= 0 else 'liquid-film energy balance',
            'film_cooling_percent': pct,
            'film_cooling_percent_source': str(getattr(
                self, 'film_cooling_percent_source', 'not supplied')),
            'film_cooling_flow_kg_s': 0.0,
            'film_heat_absorbed_w': 0.0,
            'film_covered_length_mm': 0.0,
            'film_coverage_fraction_of_chamber': 0.0,
            'downstream_gas_film_effectiveness': 'not_modelled',
            'model': ('film coolant heat-sink energy balance (no film '
                      'efficiency factor; cf. NASA SP-125 Eq. 4-33, p. 115); '
                      'real-gas enthalpies from CoolProp for CH4/H2, '
                      'sensible-heat lower bound for RP-1'),
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
                     f'(cp={cp_l:.0f} J/kgK); latent heat not_modelled - '
                     f'meaningful only below the RP-1 critical pressure: at a '
                     f'supercritical chamber pressure there is no separate '
                     f'vaporization term and the missing piece is the '
                     f'real-fluid enthalpy rise, also not_modelled')
        if dh <= 0:
            self._warn('warn.liquid.film_cooling_no_enthalpy', 'warning')
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
            self._warn('warn.liquid.film_cooling_partial_coverage', 'warning',
                       pct=float(pct),
                       coverage_pct=round(float(coverage) * 100.0))
        return out

    def _size_supercritical_regen(self, coolant_flow, n_channels,
                                  channel_width, channel_height):
        """Süperkritik marş + kanal DERİNLİĞİNİN marş hızıyla boyutlandırılması.

        ÖH A2 sivi-sogutma · 6. tur (LH2 v_probe ⟷ coolant_velocity).
        ÖLÇÜLDÜ (örnek proje, fuel_type=lh2, 25 kN): derinlik kararı
        motorun SIVI yoğunluğuyla (formdan gelen 810 kg/m³) veriliyordu —
        sonda 11,4 m/s, hedef (40 m/s) altında, derinlik 2 mm kaldı —;
        yayımlanan ``coolant_velocity`` ise marşın en hızlı istasyonundan,
        yerel T, P'deki hidrojen yoğunluğuyla (54,8 kg/m³) 168,9 m/s idi.
        Aynı yanıtta iki ayrı yoğunluk tabanı: karar hedefi tutturduğunu
        sanıyor, yayımlanan sayı hedefin 4,2 katı.

        Kural (ana model): boyutlandırma ile yayımlanan hız AYNI yoğunluk
        tabanını kullanır — istasyonun yerel T, P'sindeki gerçek akışkan
        özelliği. Derinlik sığma ölçütünün başlangıç değerinden başlar;
        marşın en büyük kanal hızı hedefi aşıyorsa derinlik h·v/hedef ile
        büyütülür (üst sınır COOLING_CHANNEL_HEIGHT_MAX_M) ve marş yeniden
        çözülür. Yerel yoğunluk derinlikle zayıf değiştiği için sabit
        noktaya birkaç adımda gelinir; adım sayısı
        REGEN_MARCH_SIZING_MAX_ITER ile SINIRLI (hesap kaynağı sınırı),
        yakınsamazsa künye bunu ADIYLA söyler.

        Dönüş: (march, derinlik [m], künye eki — büyütme olmadıysa '').
        """
        h = float(channel_height)
        march = self._solve_supercritical_regen(
            coolant_flow, n_channels, channel_width, h)
        grown = False
        converged = True
        n_iter = 0
        while True:
            v = march['summary'].get('max_coolant_velocity_m_s')
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not np.isfinite(v) or v <= 0.0):
                raise ValueError(
                    'supercritical station march published no finite '
                    f'positive coolant velocity ({v!r}); the channel depth '
                    'cannot be sized on it')
            if v <= COOLANT_CHANNEL_TARGET_VELOCITY_MS * (
                    1.0 + REGEN_MARCH_SIZING_REL_TOL):
                break
            if h >= COOLING_CHANNEL_HEIGHT_MAX_M:
                break
            if n_iter >= REGEN_MARCH_SIZING_MAX_ITER:
                converged = False
                break
            h_new = min(h * v / COOLANT_CHANNEL_TARGET_VELOCITY_MS,
                        COOLING_CHANNEL_HEIGHT_MAX_M)
            if not h_new > h:
                break
            h = h_new
            grown = True
            n_iter += 1
            march = self._solve_supercritical_regen(
                coolant_flow, n_channels, channel_width, h)
        if not grown:
            return march, h, ''
        v_fin = float(march['summary']['max_coolant_velocity_m_s'])
        note = (
            '; channel height auto-sized for the '
            f'{COOLANT_CHANNEL_TARGET_VELOCITY_MS:.0f} m/s design velocity '
            'target on the SAME density basis as the published '
            'coolant_velocity: the fastest station of the supercritical '
            'station march, real-fluid density at its local T and P '
            f'(CoolProp); {n_iter} resize step(s), final peak channel '
            f'velocity {v_fin:.1f} m/s')
        if h >= COOLING_CHANNEL_HEIGHT_MAX_M and v_fin > (
                COOLANT_CHANNEL_TARGET_VELOCITY_MS
                * (1.0 + REGEN_MARCH_SIZING_REL_TOL)):
            note += (f' - the {COOLING_CHANNEL_HEIGHT_MAX_M * 1e3:.0f} mm '
                     'depth ceiling was reached before the target was met')
        elif not converged:
            note += (f' - NOT converged within {REGEN_MARCH_SIZING_MAX_ITER} '
                     'resize steps; the target is not met')
        return march, h, note

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
                self._warn('warn.liquid.coolant_inlet_cryo_default', 'info',
                           fuel_type=self.fuel_type,
                           cryo_default_K=round(float(cryo_default), 1))
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

    def _gas_gas_injector_spec(self):
        """FFSC ana odası için gaz-gaz enjektör spec'i (çevrim çözümünden).

        Yalnız full_flow_staged çevrimde ve çevrim dengesi kapanmışsa dolu
        döner: ana odaya giren İKİ ön yakıcı egzozunun (T0, P0) akım
        koşulları çevrim çözümünden, gaz bileşimi (gamma, MW) ön yakıcı CEA
        çözümünden gelir — varsayılan sabit yok (uydurma yasağı). Koşullar
        sağlanmıyorsa None (sıvı model + uyarı yolu).
        """
        if getattr(self, 'engine_cycle', '') != 'full_flow_staged':
            return None
        cyc = getattr(self, '_cycle_result', None)
        if not cyc or cyc.get('status') != 'converged':
            return None
        streams = (cyc.get('main_chamber') or {}).get('inlet_streams') or []
        gas_streams = [s for s in streams if s.get('phase') == 'gas']
        if len(gas_streams) != 2:
            return None
        preburners = {p.get('mode'): p for p in (cyc.get('preburners') or [])}
        pb_f = preburners.get('fuel_rich')
        pb_ox = preburners.get('ox_rich')
        if not pb_f or not pb_ox:
            return None

        def _stream(label_part):
            for s in gas_streams:
                if label_part in str(s.get('label', '')):
                    return s
            return None

        s_fuel = _stream('fuel-rich')
        s_ox = _stream('ox-rich')
        if s_fuel is None or s_ox is None:
            return None

        spec = {
            'motor_type': 'liquid',
            'injector_type': 'gas_gas_coaxial',
            'Pc_bar': float(self.P_c),
            'mdot_ox': float(s_ox['mdot_kg_s']),
            'mdot_fuel': float(s_fuel['mdot_kg_s']),
            'gas_ox': {
                'T0_K': float(s_ox['temperature_K']),
                'P0_bar': float(s_ox['pressure_bar']),
                'gamma': float(pb_ox['gas']['gamma']),
                'MW': float(pb_ox['gas']['molecular_weight']),
            },
            'gas_fuel': {
                'T0_K': float(s_fuel['temperature_K']),
                'P0_bar': float(s_fuel['pressure_bar']),
                'gamma': float(pb_f['gas']['gamma']),
                'MW': float(pb_f['gas']['molecular_weight']),
            },
        }
        cd_user = getattr(self, 'injector_cd_input', None)
        if cd_user is not None:
            spec['cd'] = float(cd_user)
        return spec

    def _staged_hot_gas_circuit(self):
        """Staged combustion'da ana odaya giren SICAK GAZ devresinin durumu.

        Tek ön yakıcılı staged çevrimde ana oda gaz+sıvı karışık beslenir
        (RS-25 tarzı): türbin egzozu gaz devresi sıkıştırılabilir orifis
        modeliyle (Anderson, "Modern Compressible Flow" Ch. 3 — injector
        modülündeki compressible_orifice_flow) çözülüp raporlanır; gaz-sıvı
        coax ELEMAN geometrisi bu sürümde modellenmez ('not_modelled').
        FFSC bu yoldan geçmez (orada tam gaz-gaz model çalışır).
        """
        if getattr(self, 'engine_cycle', '') != 'staged_combustion':
            return None
        cyc = getattr(self, '_cycle_result', None)
        if not cyc or cyc.get('status') != 'converged':
            return None
        streams = (cyc.get('main_chamber') or {}).get('inlet_streams') or []
        gas_streams = [s for s in streams if s.get('phase') == 'gas']
        preburners = cyc.get('preburners') or []
        if len(gas_streams) != 1 or not preburners:
            return None
        s = gas_streams[0]
        gas = preburners[0].get('gas') or {}
        if not gas.get('gamma') or not gas.get('molecular_weight'):
            return None
        try:
            from hrma.engines.injector_design import compressible_orifice_flow
            r_sp = R_UNIVERSAL / float(gas['molecular_weight'])
            st = compressible_orifice_flow(
                0.85, 1.0, float(s['pressure_bar']) * PA_PER_BAR,
                float(s['temperature_K']), float(gas['gamma']), r_sp,
                float(self.P_c) * PA_PER_BAR)
        except Exception:
            return None
        p0 = float(s['pressure_bar'])
        dp = p0 - float(self.P_c)
        area_m2 = float(s['mdot_kg_s']) / max(st['mass_flux'], 1e-12)
        return {
            'label': s.get('label'),
            'mdot_kg_s': float(s['mdot_kg_s']),
            'T0_K': float(s['temperature_K']),
            'P0_bar': p0,
            'delta_p_bar': dp,
            'dp_pc_ratio': dp / max(float(self.P_c), 1e-9),
            'velocity_m_s': float(st['v_exit_m_s']),
            'mach': float(st['mach']),
            'choked': bool(st['choked']),
            'total_area_mm2': area_m2 * 1e6,
            'cd_assumed': 0.85,
            'model': ('compressible orifice flow (Anderson, Modern '
                      'Compressible Flow, Ch. 3); stream state from the '
                      'cycle power balance'),
            'element_geometry': 'not_modelled (gas-liquid coax element)',
        }

    def calculate_injector_design(self, cooling=None):
        """High-precision injector design with advanced fluid mechanics

        Args:
            cooling: ``calculate_cooling_requirements()`` sonucu. Verilmezse
                bir kez çözülür. GEREKEN tank basıncı yakıt tarafında
                soğutma ceketi ΔP'sini de içerdiği için (ÖH defter P3B2-01)
                bu blok soğutma çözümünü görmek zorundadır; çağıran zaten
                çözdüyse aynı sözlük geçirilir (ikinci bir çözüm yok).
        """

        # ÖH defter P3B2-13 (D23) — ÖLÜ MİRAS HIZ TABLOSU SİLİNDİ.
        # Burada enjektör tipine göre 12 satırlık bir "heritage" enjeksiyon
        # hızı tablosu (Merlin 18/28, SSME 35/25, Raptor 22/32, Apollo 8/12,
        # showerhead 18/22, pintle 25/40, varsayılan 20/25) ve bir
        # ``injection_angle = 60`` sabiti atanıyordu. ÖLÇÜLDÜ
        # (once_statik.json): ``injection_angle`` hiçbir yerden okunmuyordu,
        # ``v_fuel_base``/``v_ox_base`` ise ~110 satır aşağıda orifis
        # denkleminden KOŞULSUZ yeniden hesaplanıyordu - yani tablo hiçbir
        # sayıya girmiyor, yalnız "uçuş verisiyle doğrulanmış" izlenimi
        # bırakıyordu. Kodun kendi yorumu da bunu söylüyordu ("referans
        # olarak bırakıldı, hesapta kullanılmıyor"); beyan çözüm değildir,
        # ölü kod kaldırıldı. Aynı gerekçeyle ``fuel_viscosity`` /
        # ``ox_viscosity`` yerelleri de düştü: tek tüketicileri yukarıdaki
        # tablonun ``else`` dalıydı. (Enjektör devresinin GERÇEK viskozite
        # ihtiyacı ``hrma.engines.injector_design.liquid_viscosity``
        # üzerinden karşılanır - tek tanım yeri.)

        # ÖH D21 · P15B2-07 — ΔP/Pc oranı TEK TANIM YERİNDEN.
        # Bu blokta beş satır-içi kopya vardı (0,22 / 0,18 / 0,28 / 0,15 /
        # 0,20) ve modülün kendi künyesi (INJECTOR_TYPE_DP_FRACTION yorumu)
        # "calculate_injector_design ve çevrim çözücüsü AYNI tabloyu
        # kullanır - tek tanım yeri" diyordu. ÖLÇÜLDÜ (once.json P15B2-07):
        # beş kopya bugün tabloyla birebir eşitti, yani kusur GİZİLDİ -
        # tablo değişince kopyaların geride kalması SESSİZ olurdu. Oran
        # artık çevrim çözücüsüyle aynı okuma noktasından (_injector_dp_
        # fraction) gelir; kullanıcının ΔP girdisi aşağıda zaten ezer.
        pressure_drop_factor = self._injector_dp_fraction()

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
                self._warn('warn.liquid.injector_dp_outside_sp8089', 'warning',
                           dp_bar=float(dp_user),
                           dp_percent=round(pressure_drop_factor * 100.0))
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
        #
        # ÖH defter P3B2-13 (D23): burada ``surface_tension = 0.02  # N/m
        # typical for cryogenics`` çıplak sabiti duruyordu ve RP-1 dâhil HER
        # akışkana uygulanıyordu (RP-1 kriyojenik değildir). Depoda bu
        # büyüklüğün TEK TANIM YERİ zaten var:
        # ``hrma.engines.injector_design.liquid_surface_tension`` (NIST
        # WebBook referans noktaları + N2O için Guggenheim ölçeklemesi) -
        # aynı modül delik çözümünde de onu kullanıyor. İki devre iki ayrı
        # sıvıdır, dolayısıyla iki ayrı sigma ve iki ayrı damlacık tahmini
        # çözülür; tanınmayan akışkanda modül 'generic' der ve bu künyeye
        # yazılır (sessiz varsayım yok).
        from hrma.engines.injector_design import liquid_surface_tension
        sigma_fuel, sigma_fuel_basis = liquid_surface_tension(self.fuel_type)
        sigma_ox, sigma_ox_basis = liquid_surface_tension(self.oxidizer_type)

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
        # v2.6.26 AD DÜZELTMESİ: bu sayı bir Weber SAYISI değil, KRİTİK Weber
        # sayısıdır (damlacık parçalanma EŞİĞİ). Eskiden çıktıya
        # 'weber_number' adıyla basılıyordu; aynı ad
        # hrma/utils/injector_design.py'de GERÇEKTEN hesaplanan Weber sayısını
        # taşıyor (app.js:2473 onu 'Weber Number' diye basıyor) — aynı ad, iki
        # anlam. Ad artık ayrık: 'critical_weber_number'.
        #
        # Aşağıdaki damlacık çapı YEDEK tahmindir: injector_design modülü
        # çözerse result['droplet_diameter'] modülün SMD korelasyonuyla
        # EZİLİR. Beyan metni (CRITICAL_WEBER_NUMBER_BASIS) bunu söyler.
        critical_weber = CRITICAL_WEBER_NUMBER
        rho_gas = (self.P_c * PA_PER_BAR) / ((R_UNIVERSAL / self.mw) * self.T_c)

        def _damlacik(sigma):
            d = critical_weber * float(sigma) / (rho_gas * (v_relative ** 2))
            # Makul fiziksel sinirlar: 10-500 mikron (tipik enjektor sprey
            # araligi)
            return min(max(d, 10e-6), 500e-6)

        fuel_droplet_diameter = _damlacik(sigma_fuel)
        ox_droplet_diameter = _damlacik(sigma_ox)
        # Tek skaler geriye uyum icin korunur: iki devrenin KABASI, cunku
        # buharlasma uzunlugunu belirleyen damlacik en irisidir. Hangi
        # devrenin yonettigi kunyede ADIYLA yazilir - tahmin birakilmaz.
        if ox_droplet_diameter >= fuel_droplet_diameter:
            droplet_diameter = ox_droplet_diameter
            droplet_circuit = 'oxidizer'
        else:
            droplet_diameter = fuel_droplet_diameter
            droplet_circuit = 'fuel'

        # Injection areas with high precision
        A_fuel = self.mdot_fuel / (self.rho_fuel * v_fuel_base)
        A_ox = self.mdot_ox / (self.rho_ox * v_ox_base)

        # Validation
        if A_fuel <= 0 or A_ox <= 0:
            raise ValueError("Injection areas must be positive")
        if A_fuel > 0.1 or A_ox > 0.1:  # Large area warning
            self._warn('warn.liquid.injection_area_large', 'warning',
                       fuel_cm2=round(float(A_fuel) * 1e4, 1),
                       ox_cm2=round(float(A_ox) * 1e4, 1),
                       limit_cm2=1000.0)

        # Feed system pressure requirements
        #
        # ÖH defter P3B2-01 (Z5S/PK1): bu talep P_c + ΔP_enjektör + 8 bar
        # çıplak paydı ve SOĞUTMA CEKETİ ΔP'si formüle HİÇ girmiyordu.
        # ÖLÇÜLDÜ (25 kN, Pc=70, gaz jeneratörü): rejeneratif koşuda ceket
        # 3,7685 bar yutuyor, ablatif koşuda 0,0000 bar; talep İKİSİNDE DE
        # 93,4000 bar çıkıyordu (fark 0,0000). Yakıt, ceketten geçen
        # soğutucunun ta kendisidir (coolant_flow_rate = mdot_fuel x
        # coolant_flow_fraction), yani talep ceket kadar EKSİKTİ ve eksiklik
        # güvenlik açısından yanlış taraftaydı.
        #
        # Model TEK KAYNAKTAN alınır: çevrim güç dengesi çözücüsü zaten
        # ``disch_fuel = Pc + inj_dp + line_dp_fuel + regen_dp`` seri
        # zincirini kuruyor (cycle_power_balance.py, hem basınç beslemeli
        # dalda hem sıvı besleme zincirinde). Burada aynı seri varsayım
        # kullanılır; oksitleyici ceketten geçmediği için o taraf hareket
        # etmez.
        if cooling is None:
            cooling = self.calculate_cooling_requirements()
        # Denetçi Ş4 (4. tur): ceket hidroliği hesaplanmadıysa (HRMA kanal
        # sayısını boyutlandıramadı) ceket ΔP'si BİLİNMEZ; 0 sayılıp eksik
        # bir tank basıncı tasarım değeri gibi yayımlanmaz (fail-closed).
        jacket_dp_unknown = ((cooling or {}).get('jacket_hydraulics_status')
                             == 'not_computed')
        jacket_dp_fuel = float((cooling or {}).get('cooling_pressure_drop',
                                                   0.0) or 0.0)
        if not np.isfinite(jacket_dp_fuel) or jacket_dp_fuel < 0.0:
            jacket_dp_fuel = 0.0
        P_tank_fuel = (None if jacket_dp_unknown else
                       (self.P_c + delta_P_fuel + jacket_dp_fuel
                        + INJECTOR_FEED_MARGIN_BAR))
        P_tank_ox = self.P_c + delta_P_ox + INJECTOR_FEED_MARGIN_BAR
        tank_pressure_basis_fuel = (
            'required FUEL feed pressure = chamber pressure + injector dP + '
            'regenerative jacket dP + '
            f'{INJECTOR_FEED_MARGIN_BAR:g} bar declared margin. The jacket '
            'term is the cooling circuit pressure drop this same answer '
            'publishes (cooling_system.cooling_pressure_drop = '
            f'{jacket_dp_fuel:.4f} bar); fuel IS the coolant, so it pays the '
            'jacket before it reaches the injector (series circuit, the same '
            'chain the cycle power balance uses).')
        if jacket_dp_unknown:
            tank_pressure_basis_fuel = (
                'not_computed: the regenerative jacket pressure drop is NOT '
                'computed on this run (cooling_system.jacket_hydraulics_'
                "status = 'not_computed': HRMA could not fit its minimum "
                'channel count in this throat, see cooling_system.'
                'channel_count_fit), and the fuel pays that drop in series '
                'before the injector, so the required fuel feed pressure is '
                'not published. No zero or partial sum is substituted.')
        tank_pressure_basis_ox = (
            'required OXIDIZER feed pressure = chamber pressure + injector '
            f'dP + {INJECTOR_FEED_MARGIN_BAR:g} bar declared margin. No '
            'jacket term: the oxidizer does not pass through the cooling '
            'channels in this design.')

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

        # Mixing efficiency calculation
        # --- ÖH D24 · P3B2-14 · KARIŞIM BOYU MOTORUN KENDİ HAZNESİDİR ------
        # Burada ``mixing_length = 0.05`` (50 mm) SABİTİ vardı. ÖLÇÜLDÜ
        # (raw/OH/D24/sivi/a1/once.json, P3B2-14; taban 88a29d3): 1 kN ve
        # 100 kN motorlarda yayımlanan ``mixing_residence_time`` BİREBİR
        # aynıydı (1,9309116425898014 ms), oysa aynı iki koşuda silindirik
        # hazne boyu 142,313 ⟷ 365,874 mm (x2,57) ve boğaz çapı
        # 18,457 ⟷ 182,105 mm (x9,87) idi. Enjeksiyon hızları ölçekten
        # bağımsız olduğu için (ΔP/ρ ile kurulurlar) pay da payda da sabit
        # kalıyordu: alan, motorun büyüklüğüne HİÇ bakmayan bir sayıydı.
        #
        # Kalış süresi, damlacığın karışıp buharlaşmak için katettiği YOLA
        # bölünür; o yol enjektör yüzünden yakınsak koninin başladığı yere
        # kadar olan SİLİNDİRİK hazne boyudur (Huzel & Huang, "Design of
        # Liquid Propellant Rocket Engines", NASA SP-125, Böl. 4: karışma ve
        # buharlaşma silindirik bölümde tamamlanmak zorundadır). O boy bu
        # motorda ZATEN tek kaynaktan çözülüyor (``_chamber_volume_split``,
        # L* muhasebesi) — burada ikinci bir hazne modeli KURULMAZ.
        # Çözülemezse sayı UYDURULMAZ: süre None kalır ve künye nedenini
        # söyler (fail-closed).
        mixing_length = None
        mixing_length_basis = None
        try:
            mixing_length = float(self._chamber_volume_split()[3])  # L_sil [m]
        except Exception as exc:
            mixing_length = None
            mixing_length_basis = (
                'not published: the cylindrical chamber length could not be '
                f'solved on this run ({type(exc).__name__}), so the mixing '
                'residence time is not formed from an assumed length')
        if mixing_length is not None and (
                not np.isfinite(mixing_length) or mixing_length <= 0.0):
            mixing_length = None
            mixing_length_basis = (
                'not published: the L* accounting returned a non-positive '
                'cylindrical chamber length, so no mixing length is assumed')
        if mixing_length is not None:
            mixing_length_basis = (
                'cylindrical chamber length from the injector face to the '
                'start of the convergent cone, taken from the SAME L* '
                'accounting the chamber geometry uses '
                '(_chamber_volume_split); Huzel & Huang (NASA SP-125) Ch. 4 '
                'treats mixing and vaporisation as having to complete inside '
                'that section. It is NOT a fixed 50 mm assumption')
        v_karisim = np.sqrt(v_fuel_base * v_ox_base)
        residence_time = (
            None if (mixing_length is None or not np.isfinite(v_karisim)
                     or v_karisim <= 0.0)
            else mixing_length / v_karisim)
        
        # Yanma verimi: kullanıcı 'combustion_efficiency' girdiyse TEK KAYNAK
        # ODUR (2026-07-30 / O6: enjektör paneli kullanıcının %97'sini yok
        # sayıp enjektör tipine bağlı 0.98 sabitini gösteriyordu; kullanıcı
        # %80 girse bile panel 0.98'de kalıyordu). Girdi yoksa enjektör
        # tipinden gelen karışım kalitesi tahmini kullanılır ve etiketlenir.
        # ÖH defter P3B2-08 (D18): TEK KAYNAK. Burada enjektör tipinden
        # 0,95-0,99 arası bir sayı UYDURULUYORDU (yorumları 'Excellent /
        # Good mixing'; künyesi 'estimated from the injector type') ve
        # teslim zincirinin AYNI büyüklük için kullandığı η_c* ile
        # çelişiyordu — üstelik uydurulan sayı hiçbir hesaba girmiyor,
        # yalnız kullanıcıya gösteriliyordu. Yayımlanan yanma verimi artık
        # motorun FİİLEN uyguladığı η_c*'tır ve künyesi de onunla aynıdır.
        combustion_efficiency = float(getattr(self, 'eta_c_star', 1.0) or 1.0)
        combustion_efficiency_source = str(getattr(
            self, 'eta_c_star_source',
            'not supplied -> ideal energy release (1.000) assumed'))

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
            # P3B2-01: talebin HANGİ kalemlerden kurulduğu sayının yanında.
            'required_fuel_tank_pressure_basis': tank_pressure_basis_fuel,
            'required_ox_tank_pressure_basis': tank_pressure_basis_ox,
            'required_fuel_tank_pressure_terms': {
                'chamber_pressure_bar': float(self.P_c),
                'injector_pressure_drop_bar': float(delta_P_fuel),
                'cooling_jacket_pressure_drop_bar': (
                    None if jacket_dp_unknown else float(jacket_dp_fuel)),
                'declared_margin_bar': float(INJECTOR_FEED_MARGIN_BAR),
            },
            'number_of_elements': n_elements,
            # Devre başına DELİK sayısı: n·π/4·d² = A özdeşliğinin kullandığı
            # sayı budur (eleman sayısı tipe göre farklı olabilir, ör. pintle).
            'fuel_orifice_count': n_elements,
            'ox_orifice_count': n_elements,
            'fuel_orifice_diameter': d_fuel_orifice * 1000,  # mm
            'ox_orifice_diameter': d_ox_orifice * 1000,  # mm
            'discharge_coefficient_fuel': Cd_fuel,
            'discharge_coefficient_ox': Cd_ox,
            'combustion_efficiency': combustion_efficiency,
            'combustion_efficiency_source': combustion_efficiency_source,
            # P3B2-08: birim sözleşmesi adın yanında (aynı büyüklük
            # combustion_analysis bloğunda YÜZDE olarak yayımlanıyor).
            'combustion_efficiency_unit': 'fraction',
            # P16B2-07: yayımlanan birim KESİR, girdi birimi YÜZDE. Bu
            # asimetri artık yanıtın kendisinde yazılıdır, böylece
            # yanıttan okunup geri gönderilen değerin neden reddedildiği
            # tahmin edilmek zorunda kalınmaz.
            'combustion_efficiency_input_field': 'combustion_efficiency',
            'combustion_efficiency_input_unit': (
                COMBUSTION_EFFICIENCY_INPUT_UNIT),
            'combustion_efficiency_input_band': list(
                COMBUSTION_EFFICIENCY_INPUT_BAND_PERCENT),
            'combustion_efficiency_unit_contract': (
                'this block publishes eta_c* as a FRACTION; the input field '
                "'combustion_efficiency' is read as a PERCENT in the "
                '%g-%g band. A fraction-shaped value (0 < x <= 1) is '
                'REJECTED with warn.liquid.efficiency_unit_is_percent and is '
                'never silently converted.'
                % COMBUSTION_EFFICIENCY_INPUT_BAND_PERCENT),
            'droplet_diameter': droplet_diameter * 1e6,  # microns
            # P3B2-13: sigma artik akiskan tablosundan gelir (tek tanim yeri
            # injector_design.liquid_surface_tension); iki devre iki sivi.
            'fuel_droplet_diameter': fuel_droplet_diameter * 1e6,  # microns
            'ox_droplet_diameter': ox_droplet_diameter * 1e6,  # microns
            'atomisation_surface_tension_fuel_N_m': float(sigma_fuel),
            'atomisation_surface_tension_ox_N_m': float(sigma_ox),
            'atomisation_surface_tension_fuel_source': str(sigma_fuel_basis),
            'atomisation_surface_tension_ox_source': str(sigma_ox_basis),
            'atomisation_surface_tension_basis': (
                'liquid surface tension from '
                'hrma.engines.injector_design.liquid_surface_tension (NIST '
                'WebBook reference points; Guggenheim scaling for N2O) - the '
                'same single definition point the orifice solution uses. '
                f"fuel '{self.fuel_type}': {sigma_fuel:.4f} N/m "
                f'({sigma_fuel_basis}); '
                f"oxidiser '{self.oxidizer_type}': {sigma_ox:.4f} N/m "
                f'({sigma_ox_basis}). The scalar droplet_diameter above is '
                f'the COARSER of the two circuits (here: {droplet_circuit}), '
                'because the largest droplet sets the vaporisation length; '
                'both circuits are published so neither has to be guessed.'),
            'droplet_diameter_governing_circuit': droplet_circuit,
            'critical_weber_number': critical_weber,
            'critical_weber_number_basis': CRITICAL_WEBER_NUMBER_BASIS,
            'mixing_residence_time': (None if residence_time is None
                                      else residence_time * 1000),  # ms
            # P3B2-14: süre artık motorun ÖLÇEĞİNE bağlı; hangi boya
            # bölündüğü sayının yanında durur.
            'mixing_length_mm': (None if mixing_length is None
                                 else mixing_length * 1000.0),
            'mixing_length_basis': mixing_length_basis,
            'mixing_velocity_m_s': (float(v_karisim)
                                    if np.isfinite(v_karisim) else None),
        }

        # Gerçek tasarım katmanı: injector_design modülü (10_Enjektor_ARGE.md).
        # Geriye uyum: mevcut alan adları korunur, eşleşen alanlar modül
        # çıktısıyla doldurulur; tam çıktı 'injector_design_detail'. Modül
        # hata verirse yukarıdaki eski hesap olduğu gibi döner.
        #
        # K3 DÜZELTMESİ (2026-07-30): panel eskiden İKİ hesabın karışımıydı —
        # toplam alan/hız modülden, delik çapı eski hesaptan geliyordu; aynı
        # delik için 3.9 kat fark ve panelin kendi içinde
        # n·π/4·d² ≠ A çelişkisi (%11.4) vardı. Artık eleman sayısı modüle
        # GİRDİ olarak verilir (n_orifices_*), çap modülün KENDİ alanından
        # bölünür ve tek sayı kümesi kalır.
        try:
            from hrma.engines.injector_design import design_injector
            # P3B1-12 (ÖH D17): yönlendirme tablosu MODÜL DÜZEYİNE taşındı
            # (INJECTOR_TYPE_CIRCUIT_MODEL) ki uç kapısı ile aynı nesneden
            # okusun. Eski satırdaki ``.get(..., 'impinging_doublet')``
            # sessiz ikame idi: tanınmayan her tip (form seçeneği
            # 'unlike_impinging' dâhil) çarpışan-doublet çözümüne
            # düşürülüyor ve kullanıcıya seçtiği tipin tasarımı diye
            # gösteriliyordu. Kapı üyeliği garanti ettiği için burada
            # doğrudan indekslenir; doğrudan kurulan motorda (test/API)
            # eksik anahtar SESSİZ ikame yerine adıyla hata verir.
            inj_type_kanonik = str(self.injector_type or '').strip().lower()
            if inj_type_kanonik not in INJECTOR_TYPE_CIRCUIT_MODEL:
                raise UnsupportedInjectorTypeError(
                    f"injector_type '{self.injector_type}' has no circuit "
                    f"model; recognised: "
                    f"{', '.join(INJECTOR_TYPES_RECOGNISED)}. No substitute "
                    f"injector is designed.")
            inj_spec = {
                'motor_type': 'liquid',
                'injector_type': INJECTOR_TYPE_CIRCUIT_MODEL[
                    inj_type_kanonik],
                'mdot_ox': self.mdot_ox,
                'mdot_fuel': self.mdot_fuel,
                'rho_ox': self.rho_ox,
                'rho_fuel': self.rho_fuel,
                'Pc_bar': self.P_c,
                'dp_ratio_ox': pressure_drop_factor,
                'dp_ratio_fuel': pressure_drop_factor,
                'T_c_K': self.T_c,
                'mw_gas': self.mw,
            }

            # --- v2.6.26: AKIŞKAN KİMLİĞİ enjektöre TESLİM EDİLİR ------------
            # Bu iki anahtar hiç konmuyordu; enjektör modülü 'generic' dalına
            # düşüyor ve buhar basıncını 0,05 bar varsayıyordu. Ölçüldü:
            # LOX'un gerçek doyma basıncı 1,01325 bar (NBP 90,19 K) — yani
            # 20 kat hata, ve hata GÜVENLİK YÖNÜNDE YANLIŞ TARAFTA:
            # K_c = (P1 − P_v)/(P1 − P2) yukarı çıkıyor, kavitasyon riski
            # olduğundan DÜŞÜK görünüyor. RP-1'de ters yönde 25 kat
            # (gerçek 0,002 bar). Modülün kendi docstring'i (injector_design
            # .py:544) tam bu vakayı uyarı olarak yazıyor; hibrit motor bunu
            # zaten yapıyordu (hybrid_rocket_engine.py:2346), sıvı yolu
            # bağlanmamıştı.
            #
            # N₂O istisnası: modül 'n2o' oksitleyicide NHNE dalına girer ve
            # T_ox_K'yı ZORUNLU ister (injector_design.py:850). Sıvı motorda
            # oksitleyici deposu sıcaklığı modellenmiyor, bu yüzden kimlik
            # yalnız sıcaklık gerektirmeyen akışkanlar için geçirilir;
            # aksi hâlde modül kendi 'generic' beyanını üretir.
            _fluid_ox = str(self.oxidizer_type or '').lower()
            if _fluid_ox and _fluid_ox != 'n2o':
                inj_spec['fluid_ox'] = _fluid_ox
            if self.fuel_type:
                inj_spec['fluid_fuel'] = str(self.fuel_type).lower()

            # --- v2.6.26: viskozite yalnız KULLANICI verdiyse geçirilir -----
            # Eskiden `fuel_props.get('viscosity', 0.001)` geçiliyordu.
            # fuel_props, web_propellant_api'nin HATA sözlüğü olabiliyor
            # ({'error': ..., 'status': 'success'}), o zaman değer sessizce
            # 0,001'e düşüyordu — LH2'de gerçek 1,34e-5, yani 77 kat. Ayrıca
            # bu sabit, modülün kendi kaynaklı MU_LIQUID_REF tablosunu
            # bastırıyordu. Artık: kullanıcı girdisi varsa o, yoksa anahtar
            # HİÇ konmaz ve modül kendi tablosunu kaynağıyla birlikte kullanır.
            if self.mu_ox is not None:
                inj_spec['mu_ox'] = self.mu_ox
            if self.mu_fuel is not None:
                inj_spec['mu_fuel'] = self.mu_fuel
            # --- GAZ-GAZ ana oda enjeksiyonu (2026-07-22, denetim madde 5) --
            # FFSC'de ana odaya İKİ ÖN YAKICI EGZOZU (gaz) girer; sıvı SPI
            # modeli fiziksel olarak yanlış sınıftır. Çevrim çözümü mevcutsa
            # (main_chamber.inlet_streams iki gaz akışı) enjektör gaz-gaz
            # shear-coax modeliyle çözülür; akım koşulları (T0, P0, gamma,
            # MW) ÇEVRİM ÇÖZÜMÜNDEN gelir, varsayılan sabit yoktur.
            # Kullanıcının eleman sayısı modüle GİRDİ olarak verilir: bir
            # eleman = devre başına bir delik (unlike doublet, koaksiyel,
            # showerhead). Modül çapı kendi toplam alanından bu sayıya böler,
            # sonra alanı n·π/4·d² ile geri kurar → aritmetik TAM tutar.
            if n_user is not None:
                inj_spec['n_orifices_ox'] = n_elements
                inj_spec['n_orifices_fuel'] = n_elements
            gas_spec = self._gas_gas_injector_spec()
            if gas_spec is not None:
                inj_spec = gas_spec
            detail = design_injector(inj_spec)
            if detail.get('status') == 'success':
                cd_applied = self._apply_user_discharge_coefficient(
                    detail, cd_user)
                oxc, fc = detail['ox_circuit'], detail.get('fuel_circuit')
                result['injector_design_detail'] = detail
                result['number_of_elements'] = detail['pattern']['n_elements']
                result['ox_orifice_count'] = oxc['n_orifices']
                result['ox_orifice_diameter'] = oxc['orifice_d_mm']
                result['ox_injection_velocity'] = oxc['velocity_m_s']
                result['ox_pressure_drop'] = oxc['delta_p_bar']
                result['ox_injection_area'] = oxc['total_area_mm2']
                result['discharge_coefficient_ox'] = oxc['cd']
                if fc:
                    result['fuel_orifice_count'] = fc['n_orifices']
                    result['fuel_orifice_diameter'] = fc['orifice_d_mm']
                    result['fuel_injection_velocity'] = fc['velocity_m_s']
                    result['fuel_pressure_drop'] = fc['delta_p_bar']
                    result['fuel_injection_area'] = fc['total_area_mm2']
                    result['discharge_coefficient_fuel'] = fc['cd']
                result['orifice_geometry_source'] = (
                    'injector design model (single source: element count, '
                    'orifice diameter, area, velocity and Cd)')
                result['discharge_coefficient_source'] = (
                    'user input (discharge coefficient)' if
                    (cd_user is not None and cd_applied) else
                    oxc.get('cd_basis', 'injector design model'))
                # Kullanıcı Cd'si bu yolda uygulanamadıysa SESSİZ KALINMAZ.
                if cd_user is not None and not cd_applied:
                    self._warn('warn.liquid.entered_value_is_comparison_only',
                               'info', label='Injector discharge coefficient',
                               computed=round(float(oxc['cd']), 3),
                               entered=float(cd_user), unit='')
                # Eleman sayısını modül tipe göre kendi kurduysa (ör. pintle
                # tek elemandır) kullanıcıya bildirilir.
                if (n_user is not None
                        and int(result['number_of_elements']) != int(n_elements)):
                    self._warn('warn.liquid.entered_value_is_comparison_only',
                               'info', label='Injector element count',
                               computed=int(result['number_of_elements']),
                               entered=int(n_user), unit='')
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
        except UnsupportedInjectorTypeError:
            # ÖH D19 / P3B1-12 (Fable-D17 ŞARTI): tanınmayan enjektör tipi
            # HATASI genel ``except``e YUTULUYORDU. Ölçüldü (once.json
            # P3B1-12.dogrudan_motor): doğrudan kurulan motorda
            # ``injector_type='banana'`` hata vermeden 28 alanlık EKSİKSİZ
            # bir enjektör tasarımı döndürüyordu (yanıtta
            # ``injector_type: 'banana'``) — yani D17'de kurulan "başka bir
            # enjektörün tasarımı yayımlanmaz" kuralı YALNIZ uç kapısında
            # geçerliydi, motor katmanında (test/API/kütüphane yolu) değil.
            # Kapı hatası bir "modül kullanılamadı" durumu DEĞİLDİR: eski
            # hesabın korunması tam da sessiz ikamenin ta kendisidir.
            raise
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

        # K3: eleman sayısı ARTIK modüle girdi olarak veriliyor (yukarıda);
        # burada çapı eski hesaba geri çeviren blok KALDIRILDI — panelin
        # alanı modülden, çapı eski hesaptan gelince n·π/4·d² = A tutmuyordu.
        result['element_count_source'] = (
            'user input' if n_user is not None
            else 'sized by the injector model')
        result['pressure_drop_source'] = (
            'user input (injector pressure drop)'
            if getattr(self, 'injector_dp_input_bar', None) is not None
            else 'NASA SP-8089 dP/Pc ratio for the element type')

        # Girdi-çıktı tutarlılık uyarıları: hız ve orifis çapı ÇIKTIDIR
        # (ΔP + Cd + debi zincirinden gelir). Kullanıcının girdiği değerle
        # ciddi fark varsa sessiz kalınmaz.
        # K3: kıyaslama artık PANELDE GÖSTERİLEN nihai değerlerle yapılıyor;
        # eskiden modül öncesi eski hesapla kıyaslanıyor ve uyarı panelden
        # farklı bir üçüncü sayı ("hesaplanan 49.19 m/s" vs panel 54.81 m/s)
        # bildiriyordu.
        for label, entered, computed, unit in (
                ('Fuel injection velocity',
                 getattr(self, 'fuel_velocity_input', None),
                 result['fuel_injection_velocity'], ' m/s'),
                ('Oxidizer injection velocity',
                 getattr(self, 'ox_velocity_input', None),
                 result['ox_injection_velocity'], ' m/s'),
                ('Fuel orifice diameter',
                 getattr(self, 'fuel_orifice_input_mm', None),
                 result['fuel_orifice_diameter'], ' mm'),
                ('Oxidizer orifice diameter',
                 getattr(self, 'ox_orifice_input_mm', None),
                 result['ox_orifice_diameter'], ' mm')):
            if entered is None or computed is None or computed <= 0:
                continue
            if abs(entered - computed) / computed > INPUT_CONSISTENCY_TOLERANCE:
                self._warn('warn.liquid.entered_value_is_comparison_only',
                           'info', label=label,
                           computed=round(float(computed), 2),
                           entered=float(entered), unit=unit)

        return result

    # Cd'si tablo yerine swirl geometrisinden (Giffen-Muraszew) gelen tipler:
    # bunlarda düz orifis Cd'si fiziksel olarak YANLIŞ sınıftır, kullanıcı
    # değeri uygulanmaz (uygulanmadığı açıkça bildirilir).
    _SWIRL_CD_INJECTOR_TYPES = ('swirl', 'coax_swirl')

    def _apply_user_discharge_coefficient(self, detail, cd_user):
        """Modül enjektör çözümünü kullanıcının Cd'sine TAM cebirle taşır.

        injector_design.design_injector sözleşmesinde SIVI devreleri için Cd
        giriş alanı yoktur (yalnız gaz-gaz dalı spec['cd'] okur); Cd, orifis
        giriş geometrisi + L/D tablosundan gelir. Kullanıcının ölçtüğü Cd'yi
        AYRI bir hesapla uygulamak K3 çelişkisini doğuruyordu. Burada modülün
        KENDİ SPI cebriyle tam ölçekleme yapılır ve sonuç modül çıktısına
        GERİ YAZILIR; böylece geriye tek sayı kümesi kalır:

            ṁ = Cd·A·√(2ρΔP),  v = Cd·√(2ΔP/ρ),  d = √(4A/(π·n))
            r = Cd_model / Cd_user  ⇒  A ∝ r,  d ∝ √r,  v ∝ 1/r

        ΔP, ρ, ṁ, ΔP/Pc, kavitasyon sayısı, chug ve hidrolik flip kalemleri
        Cd'den bağımsızdır; dokunulmaz.

        Dönüş: uygulandı mı (bool). False dönerse çağıran taraf kullanıcıya
        'bu yolda kullanılmıyor' bildirimini yapar.
        """
        if cd_user is None:
            return True   # kullanıcı Cd vermedi: modül Cd'si zaten tek kaynak
        inj_type = detail.get('injector_type')
        if inj_type == 'gas_gas_coaxial':
            return True   # gaz-gaz dalı spec['cd'] ile Cd'yi zaten aldı
        if inj_type in self._SWIRL_CD_INJECTOR_TYPES:
            return False  # swirl Cd'si geometriden gelir, düz orifis Cd'si değil
        circuits = {k: detail.get(k) for k in ('ox_circuit', 'fuel_circuit')}
        live = [c for c in circuits.values() if c]
        if not live:
            return False
        # Ölçekleme yalnız tek fazlı orifis (SPI) çözümünde tam geçerlidir;
        # NHNE (flaşlayan N₂O) devresinde Cd doğrusal ölçeklenmez.
        if any(c.get('flow_model') != 'SPI' for c in live):
            return False

        cd_user = float(cd_user)
        ratios = {}
        for key, c in circuits.items():
            if not c:
                continue
            r = float(c['cd']) / cd_user
            ratios[key] = r
            root = float(np.sqrt(r))
            c['total_area_mm2'] = float(c['total_area_mm2']) * r
            c['orifice_d_mm'] = float(c['orifice_d_mm']) * root
            c['velocity_m_s'] = float(c['velocity_m_s']) / r
            c['cd'] = cd_user
            c['cd_basis'] = (
                'user input (discharge coefficient); the model value '
                f"({float(r) * cd_user:.3f}) was replaced through the same "
                'SPI orifice equation')
            man = c.get('manifold')
            if man:
                man['d_mm'] = float(man['d_mm']) * root
                man['velocity_m_s'] = float(man['velocity_m_s']) / r

        r_ox = ratios.get('ox_circuit', 1.0)
        r_fuel = ratios.get('fuel_circuit', r_ox)
        # Çarpışma geometrisi doğrudan d_ox ile ölçekli (3·d ve 6·d kuralları)
        imp = (detail.get('pattern') or {}).get('impingement')
        if imp:
            root_ox = float(np.sqrt(r_ox))
            for key in ('free_jet_length_mm', 'element_spacing_mm'):
                if imp.get(key):
                    imp[key] = float(imp[key]) * root_ox
        # SMD: impinging korelasyonu D32 = C·d·We^(-1/3) ⇒ d^(2/3)·v^(-2/3) ∝ r.
        # Elkotb ve Lefebvre-swirl korelasyonları yalnız ΔP / eleman başına
        # debi / akışkan özelliklerine bağlıdır — Cd'den etkilenmez.
        atom = detail.get('atomization') or {}
        if atom.get('correlation') == 'impinging-We13':
            if atom.get('smd_ox_um'):
                atom['smd_ox_um'] = float(atom['smd_ox_um']) * r_ox
            if atom.get('smd_fuel_um'):
                atom['smd_fuel_um'] = float(atom['smd_fuel_um']) * r_fuel
        # Pintle geometrisinin tüm uzunlukları √alan ile ölçekli; BF, delik
        # sayısı ve L_s/D_p oranları boyutsuzdur ve değişmez.
        pin = detail.get('pintle_geometry')
        if pin:
            root_ox = float(np.sqrt(r_ox))
            for key in ('d_pintle_mm', 'skip_distance_mm', 'annulus_gap_mm',
                        'radial_hole_d_mm'):
                if pin.get(key):
                    pin[key] = float(pin[key]) * root_ox
        return True

    def calculate_turbopump_requirements(self):
        """Turbopompa özeti — çevrimden ve TEK pompa zincirinden.

        Y4 DÜZELTMESİ (2026-07-30): karar ölçütü 'Pc > 50 bar' idi, bu yüzden
        BASINÇ BESLEMELİ çevrimde bile turbopompa raporlanıyordu
        (turbopumps_required=True iken detailed_feed_system.turbopump_required
        =False). Ayrıca güç burada kendi head/verim sabitleriyle yeniden
        hesaplanıyor ve _design_turbopump_system / çevrim çözümüyle üç farklı
        değer veriyordu (65.217 kW / 0.543 kW / 0.0 W). Artık:
          - turbopompa gerekliliği ÇEVRİMDEN gelir (pressure_fed -> yok),
          - güç TEK kaynaktan (_design_turbopump_system -> _design_pump).
        """
        injector = self.calculate_injector_design()
        if getattr(self, 'feed_system_type', 'turbopump') != 'turbopump':
            return {
                'turbopumps_required': False,
                'tank_fed_system': True,
                'engine_cycle': getattr(self, 'engine_cycle', 'pressure_fed'),
                'not_applicable_reason': (
                    'pressure-fed cycle: the propellants are pushed by tank '
                    'pressure, there is no turbopump'),
                # Denetçi Ş4 (4. tur): yakıt tarafı hesaplanmadıysa (None)
                # en büyük değer de yayımlanmaz.
                'max_tank_pressure': (
                    None if injector['required_fuel_tank_pressure'] is None
                    else max(injector['required_fuel_tank_pressure'],
                             injector['required_ox_tank_pressure'])),
            }

        # Turbopompalı çevrim: sayılar ayrıntılı pompa tasarımından gelir.
        tp = self._design_turbopump_system(self.mdot_ox, self.mdot_fuel)
        if tp.get('status') == 'not_computed':
            # F-20: pompa boyutlanmadıysa güç/basma yüksekliği de YOK.
            return {
                'turbopumps_required': True,
                'engine_cycle': getattr(self, 'engine_cycle', 'gas_generator'),
                'status': 'not_computed',
                'reason': tp.get('reason'),
                'fuel_pump_power': None,
                'ox_pump_power': None,
                'total_pump_power': None,
                'turbine_power': None,
                'fuel_pump_head': None,
                'ox_pump_head': None,
                'power_source': ('_design_turbopump_system (single pump-design '
                                 'chain shared with detailed_feed_system)'),
            }
        fuel_power_kw = float(tp['fuel_pump']['power'])
        ox_power_kw = float(tp['oxidizer_pump']['power'])
        return {
            'turbopumps_required': True,
            'engine_cycle': getattr(self, 'engine_cycle', 'gas_generator'),
            'fuel_pump_power': fuel_power_kw,   # kW
            'ox_pump_power': ox_power_kw,       # kW
            'total_pump_power': fuel_power_kw + ox_power_kw,  # kW
            'turbine_power': float(tp['turbine']['power']),   # kW
            'fuel_pump_head': float(tp['fuel_pump']['head']),  # m
            'ox_pump_head': float(tp['oxidizer_pump']['head']),  # m
            'power_source': ('_design_turbopump_system (single pump-design '
                             'chain shared with detailed_feed_system)'),
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
            H = (alt * ISA_GEOPOTENTIAL_EARTH_RADIUS_M
                 / (ISA_GEOPOTENTIAL_EARTH_RADIUS_M + alt))

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
            # v2.6.26 — 100 km satiri ELLE YAZILMIS sayilarla doluyordu:
            #   pressure_atm = 1e-6 ; T = 1000
            # Oysa fonksiyonun kendi belgesi ICAO/ISO 2533 dogrulugu iddia
            # ediyor ve tablonun diger 7 satiri gercek ISA'dan geliyor.
            # Olculdu: 100 km'de deponun KENDI isa_temperature'i 186,95 K,
            # isa_pressure'i 2,344e-07 bar. Yani sicaklik 5,3 kat, basinc
            # 4,3 kat yanlisti ve tek yanitta ayni buyuklugun iki farkli
            # kaynagi vardi. Ayni yardimcilar hrma/analysis/launch_site.py
            # tarafindan zaten kullaniliyor — tek kaynaga baglaniyor.
            # ISA tablosu 84,852 km'de biter; ustunde izotermal uzanti
            # uygulanir ve bu durum cikti satirinda beyan edilir.
            if alt > ISA_TABLE_TOP_M:
                T = isa_temperature(alt)
                pressure_atm = isa_pressure(alt) / 1e5   # Pa -> bar
                atmosphere_basis = ('ISA isothermal extension above '
                                    '84.852 km (US Std Atm 1976 table top)')
            else:
                atmosphere_basis = 'ISA / US Std Atm 1976'

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
            # P3B2-04 (ÖH D15): ortam-eşlenik zincirde CF, satırın KENDİ
            # yayımladığı genişleme oranından çözülür. Eşlenik rejimde iki
            # ifade ÖZDEŞTİR (basınç terimi sıfırdır), ama ε bir tavana
            # dayandığında (ölçüldü: 50/80/100 km satırlarında ε = 1000,00
            # kırpılmış) eşlenik varsayımı artık geçerli değildir; o zaman
            # satır, çizdiği lülenin CF'sini yayımlamalıdır.
            try:
                CF_ideal_eps, _ = self._cf_at(float(epsilon_opt),
                                              float(pressure_atm))
                if np.isfinite(CF_ideal_eps):
                    CF_ideal = float(CF_ideal_eps)
            except Exception:
                pass

            # Deniz seviyesi (tasarim noktasi) ideal CF — zincir demiri
            Pe_Pc_sl = max(self.P_a / self.P_c, 1e-8)
            CF_ideal_sl = np.sqrt(
                gamma_term * stagnation_term
                * (1 - Pe_Pc_sl ** ((gamma - 1) / gamma))
            )
            # Vakum ideal CF: ortam-eşlenik zincirde P_e/P_c -> 0 limiti.
            # Daima pozitiftir, kutbu yoktur — ikinci demir adayı (aşağı).
            CF_ideal_vac = np.sqrt(gamma_term * stagnation_term)
            # Bu satırın kendi lülesinin VAKUM CF'si — Isp tavanı buradan
            # gelir (aşağıdaki not).
            try:
                CF_vac_eps, _ = self._cf_at(float(epsilon_opt), 0.0)
                CF_vac_eps = (float(CF_vac_eps)
                              if np.isfinite(CF_vac_eps) else None)
            except Exception:
                CF_vac_eps = None
            # Sabit lülede çıkış statik basıncı (bar); ayrılma ölçütü için.
            # Ortam-eşlenik zincirde tanımsızdır (lüle her irtifada eşlenir).
            pe_fixed_bar = None

            # SABİT LÜLE (kullanıcı ε girdiyse): çıkış basıncı ortamla birlikte
            # DEĞİŞMEZ; CF'in basınç-itki terimi irtifayla değişir
            # (Sutton & Biblarz 9th ed., Eq. 3-30). Girdi yoksa yukarıdaki
            # ortam-eşlenik zincir aynen korunur.
            if getattr(self, 'expansion_ratio_input', None) is not None:
                try:
                    CF_ideal, _ = self._cf_at(self.expansion_ratio,
                                              pressure_atm)
                    CF_ideal_sl, pe_fixed_bar = self._cf_at(
                        self.expansion_ratio, self.P_a)
                    CF_ideal_vac, _ = self._cf_at(self.expansion_ratio, 0.0)
                except Exception:
                    pass

            # Nozzle efficiency corrections (bilgilendirme amacli rapor edilir;
            # teslim Isp'si CEA tablosuna demirli oldugundan ikinci kez uygulanmaz)
            # 1. Sapma kaybı — P3B2-07: sabit 15° konik yerine SEÇİLEN
            #    konturun λ'sı (tek kaynak: _divergence_efficiency).
            eta_divergence, _lam_src = self._divergence_efficiency()

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
            #
            # FAZ 5 / H2-2 DÜZELTMESİ — İŞARET TERS DÖNMESİ VE KUTUP.
            # Demir oranı Isp/CF aslında bir ODA büyüklüğüdür (c*_teslim /
            # (C_D·g0)) ve irtifadan bağımsız olmalıdır. Deniz seviyesi demiri
            # `self.isp_sl / CF_ideal_sl` yalnız lüle deniz seviyesinde
            # AYRILMADAN çalışıyorsa geçerlidir: aşırı genişlemiş lülede
            # CF_ideal_sl önce küçülür, sonra SIFIRI GEÇER, sonra negatif olur.
            # Pay (CEA'nın ayrılma düzeltmeli isp_sl'i) ile payda (ayrılmayı
            # HİÇ görmeyen ideal CF) farklı modellerden geldiği için oran
            # patlıyordu.
            #
            # ÖLÇÜM (25 kN LOX/RP-1, Pc=70 bar, MR=2,3; 3 Ağustos 2026):
            #     ε    P_e[bar]  ayrılma?  isp_sl/CF_sl    isp_vac/CF_vac
            #     8    1.2848    hayır         177.913          178.610
            #    16    0.5174    hayır         177.117          178.546
            #    25    0.2908    EVET          176.156          178.520
            #   100    0.0500    EVET          151.326          178.427
            #   135    0.0343    EVET         6152.295          178.407
            #   138    0.0334    EVET     -1017083.901          178.406
            #   250    0.0159    EVET         -158.074          178.370
            # Vakum demiri %0,14 bandında SABİT; deniz seviyesi demiri ayrılma
            # başlar başlamaz kullanılamaz hale geliyor. Düzeltme öncesi
            # ε=138'de 50 km satırı Isp = -2 029 819 s ve itki = -197 247,8 kN
            # yayımlıyordu (HTTP 200, `error` alanı yok). ε = 100-300 bandı
            # uydurma değil: vakum üst kademe lüleleri oradadır (RL10B-2 ≈ 280;
            # KU-K6: ikincil kaynaklar — Sutton 9. bs. Tablo 6-9 s. 235 385:1
            # der, büyük olasılıkla baskı hatası; üretici verisi doğrulanmadı).
            #
            # Ortam-eşlenik (rubber-nozzle) zincirde demir DEĞİŞMEZ: orada
            # CF_ideal_sl daima pozitiftir ve deniz seviyesinde itki komuta
            # edilen itke birebir eşittir (ölçüldü: 25,000 kN). Bu yüzden
            # vakum demirine yalnız deniz seviyesi demiri GEÇERSİZKEN düşülür.
            sl_anchor_ok = bool(CF_ideal_sl > 0.0)
            if pe_fixed_bar is not None:
                # Summerfield ölçütü (NOZZLE_SEPARATION_PRESSURE_RATIO = 0,40):
                # ayrılan lülede ideal CF gerçek itkiyi temsil etmez.
                sl_anchor_ok = sl_anchor_ok and bool(
                    pe_fixed_bar >= NOZZLE_SEPARATION_PRESSURE_RATIO * self.P_a)
            if sl_anchor_ok:
                isp_per_cf = self.isp_sl / CF_ideal_sl
                isp_anchor_basis = (
                    'delivered Isp anchored at the sea-level design point '
                    '(attached flow); Isp = (isp_sl / CF_sl) * CF(altitude)')
            elif CF_ideal_vac > 0.0:
                isp_per_cf = self.isp_vac / CF_ideal_vac
                isp_anchor_basis = (
                    'delivered Isp anchored at the vacuum reference; the '
                    'sea-level anchor is invalid because this nozzle is '
                    'separated at sea level (Summerfield criterion, '
                    'Pe < %.2f * Pa)' % NOZZLE_SEPARATION_PRESSURE_RATIO)
            else:
                isp_per_cf = None
                isp_anchor_basis = 'not_modelled (no positive ideal-CF anchor)'

            if isp_per_cf is None or not (CF_ideal > 0.0):
                # Bu irtifada ideal tek boyutlu teori NEGATİF itki katsayısı
                # veriyor: lüle tamamen ayrılmış rejimde. HRMA akış ayrılmasını
                # ÇÖZMEZ, bu yüzden sayı UYDURULMAZ — alanlar null döner ve
                # gerekçesi satırın kendisinde yazar. (Ayrılma ayrıca
                # `warn.liquid.flow_separation` ile de bildirilir.)
                isp_altitude = None
                thrust_altitude = None
                CF_actual = None
                isp_ratio = None
                thrust_ratio = None
                not_modelled_reason = (
                    'ideal 1-D thrust coefficient is not positive at this '
                    'ambient pressure (CF_ideal = %.4f): the nozzle is fully '
                    'separated and flow separation is NOT modelled here'
                    % float(CF_ideal))
            else:
                # P3B2-04: TAVAN ARTIK SATIRIN KENDİ ε'SUNDAN.
                # Eski satır  min(isp_per_cf*CF_ideal, self.isp_vac)  idi ve
                # ölçüldü (once.json): 8 satırın 5'i (10/20/50/80/100 km)
                # birebir aynı Isp (312,871936 s) ve aynı itki (27 503,369 N)
                # yayımlıyordu — 10 km'de ortam basıncı 26,4 kPa iken motor
                # TAM VAKUM performansı ilan ediyordu (iyimser, yörünge
                # hesabında tehlikeli yön), ve kırpma HİÇBİR alanda beyan
                # edilmiyordu: satırın kendi 'isp_anchor_basis' künyesi hâlâ
                # kırpmasız formülü yazıyordu. Kategori hatası: self.isp_vac
                # SABİT tasarım lülesinin (ε=9,007) vakum Isp'sidir, oysa bu
                # zincir her irtifada lüleyi ortama eşliyor (ε 9 -> 1000).
                # Doğru tavan satırın KENDİ lülesinin vakum Isp'sidir; o
                # tavan tanım gereği hiçbir ortam basıncında bağlamaz, çünkü
                # CF(ε, P_a>0) < CF(ε, 0).
                isp_altitude = isp_per_cf * CF_ideal
                if CF_vac_eps is not None:
                    isp_altitude = min(isp_altitude, isp_per_cf * CF_vac_eps)
                # Thrust at altitude (constant mass flow)
                thrust_altitude = self.mdot_total * isp_altitude * self.g0
                # Actual thrust coefficient (zincirle tutarli: CF = F/(Pc*A_t))
                CF_actual = thrust_altitude / (self.P_c * 1e5 * self.A_t)
                # Performance ratios
                isp_ratio = (isp_altitude / self.isp_sl
                             if self.isp_sl else None)
                thrust_ratio = thrust_altitude / self.F if self.F else None
                not_modelled_reason = None

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
                self._warn('warn.liquid.exit_mach_unsolved', 'warning',
                           expansion_ratio=round(float(eps_here), 2),
                           altitude_m=round(float(alt)))
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
                'reynolds_number': Re_throat,
                # H2-2: Isp'nin hangi referansa demirlendiği ve satır
                # çözülemediyse NEDEN çözülemediği veriyle birlikte gider.
                'isp_anchor_basis': isp_anchor_basis,
                'not_modelled_reason': not_modelled_reason,
            })

        # Tasarım noktası geometrisini geri yükle (bkz. yukarıdaki not).
        for _k, _v in _snapshot.items():
            setattr(self, _k, _v)

        return altitude_data

    def _nozzle_exit_design_block(self, altitude_performance):
        """Nozul çıkış durumu bloğu — motor_viz3d.js plume veri sözleşmesi.

        v2.6.26 sahte-plume sökümünden sonra 3-B egzoz yalnız GERÇEK çıkış
        büyüklükleriyle çizilir; ``readNozzleExit`` (motor_viz3d.js) şunları
        okur ve biri eksikse plume'u HİÇ çizmez:

            nozzle_design.performance.exit_pressure     [bar]
            nozzle_design.performance.ambient_pressure  [bar]
            nozzle_design.performance.exit_mach         [-]
            nozzle_design.performance.exit_velocity     [m/s]  (yedek adres)
            gamma, chamber_temperature, exit_diameter   (üst düzey)

        Hibrit motor bu şemayı ``design_nozzle`` çıktısıyla yayımlıyordu;
        sıvı motor AYNI büyüklükleri irtifa tablosunda zaten hesaplıyor ama
        hiç yayımlamıyordu — sıvı sayfasında egzozun hiç çizilmemesinin
        nedeni buydu. Bu blok yeni bir şey HESAPLAMAZ:
        ``calculate_altitude_performance`` çıktısının deniz seviyesi
        satırındaki (altitude == 0) gerçek değerleri sözleşme adlarıyla
        yeniden yayımlar.

        Çıkış hızı için not: hibritte ``readNozzleExit`` önce
        ``altitude_performance.altitude_performance[0].exit_velocity``
        (sözlük-sarmalı) adresine bakar. Sıvıda üst düzey
        ``altitude_performance`` DÜZ LİSTEDİR ve liquid.html o listeyi
        ``results.altitude_performance.length`` / ``.map`` ile tüketir;
        sarmalamak o paneli kırar. Bu yüzden çıkış hızı sözleşmenin YEDEK
        adresinde (``performance.exit_velocity``) yayımlanır — JS tam olarak
        bu sıra için yazılmıştır (liste sarmalı bulunamazsa perf'e düşer).

        Deniz seviyesi satırı çözülememişse değer UYDURULMAZ: alanlar null
        döner ve gerekçe ``exit_state_basis`` içinde NOT_MODELLED olarak
        yazar (plume çizilmez).
        """
        sea_level = None
        if isinstance(altitude_performance, list) and altitude_performance:
            row = altitude_performance[0]
            if isinstance(row, dict) and row.get('altitude') == 0:
                sea_level = row

        def _finite(value):
            try:
                value = float(value)
            except (TypeError, ValueError):
                return None
            return value if np.isfinite(value) else None

        exit_pressure = ambient_pressure = exit_mach = exit_velocity = None
        if sea_level is not None:
            exit_pressure = _finite(sea_level.get('exit_pressure_bar'))
            ambient_pressure = _finite(sea_level.get('pressure'))
            exit_mach = _finite(sea_level.get('exit_mach_number'))
            exit_velocity = _finite(sea_level.get('exit_velocity'))

        source = ('liquid_rocket_engine.calculate_altitude_performance '
                  'sea-level (altitude = 0 m) row of THIS design')
        if None in (exit_pressure, ambient_pressure, exit_mach,
                    exit_velocity):
            return {
                'performance': {
                    'exit_pressure': None,
                    'ambient_pressure': None,
                    'exit_mach': None,
                    'exit_velocity': None,
                    'exit_state_basis': (
                        'NOT_MODELLED: the sea-level row of the altitude '
                        'performance table could not be resolved, so the '
                        'nozzle exit state is not published. No value is '
                        'invented; the 3-D exhaust plume stays off.'),
                    'exit_state_source': source,
                },
                'schema_source': ('motor_viz3d.js readNozzleExit contract '
                                  '(nozzle_design.performance), shared with '
                                  'the hybrid engine'),
            }

        return {
            'performance': {
                # bar — ε ile tutarlı izentropik çıkış statik basıncı
                # (Sutton & Biblarz 9th ed., Eq. 3-25 ailesi).
                'exit_pressure': exit_pressure,
                'exit_pressure_basis': (
                    'isentropic static pressure at the geometric exit Mach '
                    'of the design nozzle (Sutton & Biblarz 9th ed., '
                    'Eq. 3-25 family); sea-level row of the altitude '
                    'performance table'),
                # bar — ISA deniz seviyesi (irtifa tablosunun kendi atmosferi)
                'ambient_pressure': ambient_pressure,
                'ambient_pressure_basis': (
                    'ISA / US Standard Atmosphere 1976 at 0 m, the same '
                    'atmosphere model as the altitude performance table'),
                # [-] — çıkış Mach'ı GEOMETRİDEN (Ae/At, gamma) çözülür,
                # ortam basıncından değil (v2.5.2 düzeltmesi).
                'exit_mach': exit_mach,
                'exit_mach_basis': (
                    'solved from the design area ratio Ae/At and gamma '
                    '(supersonic branch); independent of ambient pressure'),
                # m/s — v_e = Me·a_exit, a_exit yanma gazının R\'si ve
                # izentropik çıkış statik sıcaklığıyla.
                'exit_velocity': exit_velocity,
                'exit_velocity_basis': (
                    'v_e = Me * sqrt(gamma * R_gas * T_exit_static) with '
                    'combustion-gas R and the isentropic exit static '
                    'temperature; sea-level row. Published here (the '
                    'readNozzleExit fallback address) because the liquid '
                    'top-level altitude_performance is a plain list '
                    'consumed by liquid.html and cannot be dict-wrapped '
                    'like the hybrid one'),
                'exit_state_source': source,
            },
            'schema_source': ('motor_viz3d.js readNozzleExit contract '
                              '(nozzle_design.performance), shared with '
                              'the hybrid engine'),
        }

    def calculate_performance(self):
        """Calculate overall engine performance"""
        # Basic geometry
        nozzle_geom = self.calculate_nozzle_geometry()
        
        # Cooling system
        cooling = self.calculate_cooling_requirements()

        # Injection system — ceket ΔP'si GEREKEN besleme basıncına girdiği
        # için (P3B2-01) soğutma çözümü buraya AYNEN geçirilir; ikinci bir
        # soğutma çözümü koşmaz ve iki blok aynı ΔP'yi kullanır.
        injector = self.calculate_injector_design(cooling=cooling)

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
            self._warn('warn.liquid.thrust_to_weight_out_of_band', 'warning',
                       ratio=round(float(thrust_to_weight), 1),
                       lo=1.0, hi=200.0)
        
        # MR efficiency already applied in _calculate_mixture_ratio_effects()
        # Do NOT apply again here (was causing double penalty).
        # v2.6.26: raporlanan DEĞER performans haritasının gerçek O/F
        # taramasından gelir (aşağıda performance_maps çözüldükten sonra
        # okunur); self.mr_efficiency canlı CEA yolunda koşulsuz 1.0'dır ve
        # yaprağı her motorda %100'e çiviliyordu.
        actual_isp_sl = self.isp_sl
        actual_isp_vac = self.isp_vac

        # Özgül itki kontrolü
        if actual_isp_sl < 100 or actual_isp_sl > 500:
            self._warn('warn.liquid.isp_sea_level_out_of_band', 'warning',
                       isp_s=round(float(actual_isp_sl), 1),
                       lo_s=100.0, hi_s=500.0)
        if actual_isp_vac < 200 or actual_isp_vac > 600:
            self._warn('warn.liquid.isp_vacuum_out_of_band', 'warning',
                       isp_s=round(float(actual_isp_vac), 1),
                       lo_s=200.0, hi_s=600.0)

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
        
        # Uzay performansı kontrolü — ÖH D33 · OH-UC-05.
        #
        # ESKİ HÂL: hüküm YALNIZ ``print()`` ile stdout'a basılıyordu. Sunucu
        # günlüğüne düşüyor, kullanıcının gördüğü ``design_warnings``
        # listesine HİÇ girmiyordu; üstelik metin Türkçe gömülüydü, yani
        # backend'in dilsizlik sözleşmesini de deliyordu. ÖLÇÜLDÜ
        # (docs/scofield/raw/OH/D33/motorlar/a1/once.json · K1, Isp_vac
        # Isp_SL'ye eşitlenmiş 5 kN basınç beslemeli motor): stdout'ta
        # "Vakum Isp iyileştirmesi anormal: %0.0" satırı VAR, yanıttaki
        # eşleşen uyarı kaydı sayısı 0.
        #
        # Beyan değil KANAL onarımı: hüküm aynı hükümdür, artık kullanıcıya
        # ULAŞAN listeye yazılır. Eşikler tek kaynaktan
        # (``VACUUM_ISP_IMPROVEMENT_BAND``) okunur.
        #
        # ``fallback``: ``i18n_common.js`` arayuz-i18n kulvarının sahasıdır
        # ve bu dalgada sahipsizdir; kod ZİNCİR BORCU olarak yayımlanır ve
        # İngilizce yedek metnini kendisi taşır — ekran katmanı
        # (``static/js/app.js`` ``warnToText``) ``w.fallback || w.code`` ile
        # onu basar, yani kullanıcı ham anahtar GÖRMEZ. Borcun bekçisi
        # ``tests/test_engine_warning_i18n.py::ZINCIR_BORCU``.
        isp_improvement = (actual_isp_vac - actual_isp_sl) / actual_isp_sl
        if (isp_improvement < VACUUM_ISP_IMPROVEMENT_BAND[0]
                or isp_improvement > VACUUM_ISP_IMPROVEMENT_BAND[1]):
            _iyilesme_kaydi = dict(self._mk_warning(
                'warn.liquid.vacuum_isp_improvement_out_of_band', 'warning',
                improvement_pct=round(100.0 * float(isp_improvement), 1),
                lo_pct=round(100.0 * VACUUM_ISP_IMPROVEMENT_BAND[0], 1),
                hi_pct=round(100.0 * VACUUM_ISP_IMPROVEMENT_BAND[1], 1),
                isp_sl_s=round(float(actual_isp_sl), 1),
                isp_vac_s=round(float(actual_isp_vac), 1)),
                fallback=("Vacuum Isp is {improvement_pct}% above the "
                          "sea-level value ({isp_sl_s} s -> {isp_vac_s} s), "
                          "outside the {lo_pct}-{hi_pct}% band expected from "
                          "the ambient-pressure term of the thrust "
                          "coefficient (CF_vac - CF_SL = eps*p_a/P_c, Sutton "
                          "& Biblarz 9th ed. Eqs. 3-30/3-31). Check the "
                          "expansion ratio and the ambient pressure you "
                          "entered before using these two numbers."))
            if _iyilesme_kaydi not in self.design_warnings:
                self.design_warnings.append(_iyilesme_kaydi)


        # Altitude performance analysis
        altitudes = [0, 1000, 5000, 10000, 20000, 50000, 80000, 100000]  # m
        altitude_performance = self.calculate_altitude_performance(altitudes)

        # Nozul çıkış durumu (plume sözleşmesi): deniz seviyesi satırının
        # GERÇEK değerleri hibritle aynı şema adları altında yayımlanır —
        # bkz. _nozzle_exit_design_block docstring'i.
        nozzle_design_block = self._nozzle_exit_design_block(
            altitude_performance)

        # Advanced subsystem analysis
        propellant_tanks = self._design_propellant_tanks()
        detailed_feed_system = self._analyze_detailed_feed_system()
        # F1-1 (bebek-Scofield): başlık Isp'si ile çevrim çözümünün motor
        # Isp'si aynı yanıtta çelişiyordu ve fark hiçbir yerde beyan
        # edilmiyordu — ilişki artık adıyla yayımlanır (blok, motorun gerçek
        # _cycle_isp_applied durumundan türediği için davranıştan kopamaz).
        cycle_isp_accounting = self._cycle_isp_accounting_block(
            detailed_feed_system.get('engine_cycle_solution') or {})
        combustion_analysis = self._analyze_combustion_chamber_detailed()
        structural_analysis = self._calculate_structural_loads()
        # ÖH D24 · P9B2-24 — ön kapak boyu, imalat STEP'iyle TEK KAYNAKTAN.
        # İhraç katmanı kapağı DÜZ modeller ve kalınlığını
        # ``end_cap_analysis.flat_head_thickness``tan okur; yayımlanan boy da
        # aynı alandan okunur ki panel ile indirilen katı aynı cümleyi kursun.
        _forward_closure_mm, _forward_closure_basis = \
            self._forward_closure_length_mm(structural_analysis)
        # Isıl koruma tek kaynak: yukarıdaki GERÇEK soğutma çözümünden türetilir.
        thermal_protection = self._calculate_thermal_protection_system(cooling)
        # Güverte ısı haritasının okuduğu şema (Z5-C5 / OH-Z3-03): AYNI
        # soğutma çözümünden yayımlanır, yeni fizik hesabı YOKTUR.
        heat_transfer_analysis = self._build_heat_transfer_analysis(cooling)

        # Performance optimization maps
        performance_maps = self._generate_performance_optimization_maps()
        efficiency_analysis = self._calculate_efficiency_breakdown()

        # Kısma haritası (2026-07-23): %40-100 itki bandı, her nokta chug
        # marjıyla. Çözülemezse sahte harita değil, hatası raporlanır.
        try:
            throttle_map = self.solve_throttle_map()
        except Exception as exc:
            throttle_map = {'status': 'error', 'reason':
                            f'{type(exc).__name__}: {exc}', 'points': []}

        # Autogenous basınçlandırma (2026-07-23): yalnız turbopompalı +
        # metan/LOX veya LH2/LOX konfigüracıyonunda sayısal boyutlandırılır.
        autogenous = self._autogenous_pressurization_summary()

        # Manufacturing and cost analysis
        # Soğutma ve enjektör sonuçları yukarıda zaten hesaplandı; tolerans
        # tablosu bunların GERÇEK ölçülerini kullanır (tekrar hesap yok).
        manufacturing_analysis = self._analyze_manufacturing_requirements(
            cooling=cooling, injector=injector)

        # P3B2-07: sapma verimi TEK kaynaktan (yayımlanan her yaprak aynı).
        lam_div, lam_div_source = self._divergence_efficiency()

        # --- ÖH defter P3B2-12: Isp / C_F / c* özdeşlik denetimi ------------
        # Üç yayımlanan sayı ile ders kitabı özdeşliği ARTIK KAPANIR ve
        # artık (residual) sayıyla birlikte durur. Kapanmıyorsa gizlenmez:
        # kalan yayımlanır ve durum 'OPEN' olur (fail-closed beyan).
        _cf_sl = None
        for _row in (altitude_performance or []):
            if isinstance(_row, dict) and _row.get('altitude') == 0:
                _cf_sl = _row.get('thrust_coefficient')
                break
        _cd = float(self.CD_throat)
        if (_cf_sl and actual_isp_sl and getattr(self, 'c_star', None)
                and _cd > 0):
            _pred = float(_cf_sl) * float(self.c_star) / (G_0 * _cd)
            _res = (float(actual_isp_sl) - _pred) / float(actual_isp_sl) * 100.0
            isp_identity = {
                'identity': 'isp_sea_level = thrust_coefficient(0 m) * '
                            'c_star / (g0 * throat_discharge_coefficient)',
                'isp_sea_level_s': float(actual_isp_sl),
                'thrust_coefficient_sea_level': float(_cf_sl),
                'c_star_m_s': float(self.c_star),
                'throat_discharge_coefficient': _cd,
                'predicted_isp_s': float(_pred),
                'residual_pct': float(_res),
                # ÖH D22 / OH-D20-01: eşik artık TEK TANIMLI ve künyeli
                # (LIQUID_ISP_IDENTITY_TOLERANCE_PCT); değeri okuyucuya da
                # yayımlanır ki 'CLOSED' hükmü çıplak kalmasın.
                'status': ('CLOSED'
                           if abs(_res) <= LIQUID_ISP_IDENTITY_TOLERANCE_PCT
                           else 'OPEN'),
                'closure_tolerance_pct': float(
                    LIQUID_ISP_IDENTITY_TOLERANCE_PCT),
                'basis': (
                    'Sutton & Biblarz 9th ed. Eq. 3-31 written for a throat '
                    'with a discharge coefficient: F = C_F*P_c*A_t and '
                    'mdot = P_c*A_t*C_D/c_star, so Isp = C_F*c_star/(g0*C_D). '
                    'Without the C_D term the same three published numbers '
                    'miss by exactly 1/C_D (measured 2.0000% at C_D=0.98) '
                    'and the reader cannot tell why. The CLOSED/OPEN band is '
                    f'{LIQUID_ISP_IDENTITY_TOLERANCE_PCT:g}% and is an '
                    'engineering allowance for rounding and cross-platform '
                    'CEA drift, NOT a measured physical deviation limit; the '
                    'algebraic identity itself closes exactly'),
            }
        else:
            isp_identity = {
                'identity': 'isp_sea_level = thrust_coefficient(0 m) * '
                            'c_star / (g0 * throat_discharge_coefficient)',
                'status': 'NOT_EVALUATED',
                'basis': ('the sea-level thrust coefficient, c* or the '
                          'delivered sea-level Isp is not available in this '
                          'run, so the identity is NOT evaluated and no '
                          'residual is invented'),
            }

        # --- Tasarım durumu: 'OPTIMIZED' artık bir KOŞUL (Faz 4B, bulgu B1) ---
        # Burada koşulsuz 'OPTIMIZED' yazıyordu (:4492). Sıvı motorda tasarıma
        # FİİLEN uygulanan tek eniyileme, genişleme oranının ortam-eşlenik
        # optimumda seçilmesidir (pe = pa; Sutton & Biblarz 9. baskı Böl. 3 —
        # verilen irtifada itkiyi maksimize eden ε). Kullanıcı ε'yu kendisi
        # verdiyse bu eniyileme ÇALIŞMAZ, lüle sabittir; kapalı-form çözüm
        # başarısız olup kaba yaklaşıma düşüldüyse de eniyileme BAŞARILI
        # dönmemiştir. Karışım oranı optimumu (_solve_optimal_mixture_ratio)
        # yalnız DANIŞMA amaçlıdır — tasarım MR'ını değiştirmez — bu yüzden
        # durumu yükseltmez, sadece 'optimizations_applied' listesinde adı
        # geçmez.
        eps_kullanici = getattr(self, 'expansion_ratio_input', None)
        eps_yedege_dustu = bool(getattr(self, '_expansion_optimum_fallback',
                                        False))
        # P3B2-09: kırpılmış lüle ortamla EŞLENİK DEĞİLDİR — eniyileme
        # iddiası taşıyamaz.
        eps_kirpma = getattr(self, '_expansion_clamp', None)
        eniyilemeler = []
        if eps_kullanici is None and not eps_yedege_dustu and not eps_kirpma:
            eniyilemeler.append(
                'expansion ratio chosen at the ambient-matched optimum '
                '(pe = pa) for the design altitude')
        if eniyilemeler:
            design_status = DESIGN_STATUS_OPTIMIZED
            design_status_basis = eniyilemeler
        else:
            design_status = DESIGN_STATUS_CALCULATED
            if eps_kullanici is not None:
                gerekce = ('the expansion ratio was supplied by the user, so '
                           'no expansion optimisation was performed')
            elif eps_kirpma:
                _unc = getattr(self, '_expansion_unclamped', None)
                gerekce = (
                    'the ambient-matched optimum was solved but then bound '
                    f'by the solver {eps_kirpma} '
                    f'({EXPANSION_RATIO_SOLVER_MIN:g} / '
                    f'{EXPANSION_RATIO_SOLVER_MAX:g}): the unclamped optimum '
                    f'is {_unc:.5f} and the nozzle actually carries '
                    f'{self.expansion_ratio:.5f}, so pe != pa and this run '
                    'is NOT ambient-matched. The exit pressure is solved '
                    'isentropically from the clamped expansion ratio')
            else:
                gerekce = ('the ambient-matched expansion optimum could not be '
                           'solved in closed form; a coarse approximation was '
                           'used instead')
            design_status_basis = [gerekce]

        results = {
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
            # F1-1: başlık Isp'sinin çevrim çözümüyle ilişkisi — kayıp
            # uygulanmadıysa fark burada ADIYLA ve ölçülen değerle durur.
            'cycle_isp_accounting': cycle_isp_accounting,
            'isp_vacuum_optimized': vacuum_optimized_isp,
            'thrust_vacuum': space_thrust_vacuum,
            'c_star': self.c_star,
            # --- ÖH defter P3B2-12 (D18) ---------------------------------
            # Ölçüldü (once.json, 25 kN/60 bar): yayımlanan
            # isp_sea_level=283,2556 s ⟷ CF_sl*c*/g0=277,5905 s, fark
            # %2,0000 = tam 1/0,98. Isp=C_F*c*/g0 özdeşliği KAPALI bir lüle
            # içindir; bu motorun boğazı A_t = mdot*c*/(P_c*C_D) ile
            # boyutlandığından doğru özdeşlik Isp = C_F*c*/(g0*C_D)'dir.
            # Uzlaştıran C_D yanıtın HİÇBİR yerinde yayımlanmıyordu
            # ('discharge_coefficient' adını taşıyan tek alan enjektör
            # Cd'siydi), yani kullanıcı üç sayıyı alıp özdeşliği kuramıyor ve
            # farkın nereden geldiğini göremiyordu. Sayı uydurulmuyor: zaten
            # hesapta kullanılan C_D adıyla ve künyesiyle yayımlanıyor.
            'throat_discharge_coefficient': float(self.CD_throat),
            'throat_discharge_coefficient_basis': (
                'nozzle throat discharge coefficient C_D used to size the '
                'geometric throat: A_t = mdot_main_chamber * c_star / '
                '(P_c * C_D). '
                + self._throat_discharge_coefficient(with_source=True)[1]
                ['basis'] +
                '. It is the term that closes Isp = C_F * c_star / '
                '(g0 * C_D): with C_D < 1 the geometric throat is larger '
                'than the effective one, so the published Isp exceeds '
                'C_F*c_star/g0 by exactly 1/C_D'),
            # OH-D20-03: atıf ayrı bir alandır — 'assumed' sözcüğü metnin
            # içinde kaybolmasın, makine de okuyabilsin.
            'throat_discharge_coefficient_source':
                self._throat_discharge_coefficient(with_source=True)[1],
            'isp_identity': isp_identity,
            'chamber_temperature': self.T_c,
            'thrust_to_weight': thrust_to_weight,
            'engine_mass_estimate': engine_mass,
            'optimal_mixture_ratio': self.optimal_mr,
            # P3B1-04: künyeler ARTIK YAYIMLANIYOR. Ölçüldü: iki alan
            # (optimal_mr_source / optimal_mr_thrust_source) motorun
            # özniteliği olarak gerçekten üretiliyor ama yanıtın hiçbir
            # yerinde YOKTU — modülün kendi docstring'i "optimal_mr_source
            # alanı hangi yoldan geldiğini bildirir" diyordu, bildirmiyordu.
            'optimal_mixture_ratio_source': getattr(
                self, 'optimal_mr_source', None),
            'optimal_mixture_ratio_thrust': getattr(
                self, 'optimal_mr_thrust', None),
            'optimal_mixture_ratio_thrust_source': getattr(
                self, 'optimal_mr_thrust_source', None),
            'mixture_ratio_efficiency': (
                (performance_maps.get('mixture_ratio_optimization') or {})
                .get('mr_efficiency')),
            'mixture_ratio_efficiency_basis': (
                (performance_maps.get('mixture_ratio_optimization') or {})
                .get('mr_efficiency_basis', 'not_modelled')),
            
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
            # --- ÖH D20 / OH-D17-15 -----------------------------------
            # Ölçüldü (once.json OH-D17-15.ust_duzey_geometri_alanlari):
            # AYNI düzeyde chamber_diameter = 118,686 (mm) ile
            # throat_diameter = 0,059358 (m) yan yana duruyordu; alan
            # adlarının hiçbirinde birim eki yoktu ve okuyan biri hangi
            # sayının hangi birimde olduğunu ancak kaynağa bakarak
            # anlayabiliyordu (aynı yanıtın motor_geometry bloğu dördünü de
            # METRE veriyor). Tarihsel adlar panel/JS okuyucuları için
            # KORUNUR (yeniden adlandırma arayüz kulvarının sahası); onların
            # yanına TEK BİRİMLİ (mm) ve SONEKLİ dörtlü ile birimlerin
            # açık beyanı konur. Yeni sayı üretilmez: aynı çözümün aynı
            # değerleri, birim dönüşümü tek yerde.
            'chamber_diameter_mm': float(cooling['chamber_diameter']),
            'chamber_length_mm': float(cooling['chamber_length']),
            'throat_diameter_mm': m_to_mm(nozzle_geom['throat_diameter']),
            'exit_diameter_mm': m_to_mm(nozzle_geom['exit_diameter']),
            'contraction_ratio': self._contraction_ratio(),
            'geometry_units': {
                'suffixed_fields_unit': 'mm',
                'suffixed_fields': ['chamber_diameter_mm',
                                    'chamber_length_mm',
                                    'throat_diameter_mm',
                                    'exit_diameter_mm'],
                'legacy_field_units': {
                    'chamber_diameter': 'mm',
                    'chamber_length': 'mm',
                    'throat_diameter': 'm',
                    'exit_diameter': 'm',
                },
                'basis': (
                    'the four historic top-level geometry fields do NOT share '
                    'a unit (two are mm, two are m) and carry no unit suffix; '
                    'they are kept for panel/JS readers. Use the *_mm fields '
                    'for a single-unit read. contraction_ratio is the '
                    'DIMENSIONLESS A_chamber/A_throat of the same solution, '
                    'so a reader can cross-check the pair: '
                    '(chamber_diameter_mm / throat_diameter_mm)^2 = '
                    'contraction_ratio'),
            },
            
            # Subsystems
            'cooling_system': cooling,
            'injection_system': injector,
            'turbopump_system': turbopump,
            'propellant_tanks': propellant_tanks,
            'detailed_feed_system': detailed_feed_system,
            'combustion_analysis': combustion_analysis,
            'structural_analysis': structural_analysis,
            'thermal_protection': thermal_protection,
            'heat_transfer_analysis': heat_transfer_analysis,
            
            # Advanced Analysis
            'performance_maps': performance_maps,
            'throttle_map': throttle_map,
            'autogenous_pressurization': autogenous,
            # Yanma verisi kaynağı rozeti (UI): CEA @ gerçek Pc mi statik tablo
            # mu, ve gerçek-gaz uyarısı (Pc>300 bar'da CEA ideal-gaz çözümü).
            'combustion_data_source': getattr(self, 'combustion_data_source',
                                              'unknown'),
            'combustion_validity': dict(getattr(self, 'combustion_validity',
                                                {}) or {}),
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

            # --- Nozul çıkış durumu: 3-B egzoz (plume) veri sözleşmesi ---
            # motor_viz3d.js readNozzleExit bu adresleri okur; hibritle aynı
            # şema. Değerler irtifa tablosunun deniz seviyesi satırından
            # gelir, yeni hesap yoktur (_nozzle_exit_design_block).
            # gamma ve chamber_temperature sözleşmenin üst düzey adresleri —
            # bu sözlükte zaten yayımlıdır ('gamma', 'chamber_temperature'),
            # exit_diameter de metre cinsinden yukarıda ('Geometry') vardır.
            'nozzle_design': nozzle_design_block,

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
                'convergent_half_angle_basis': CONVERGENT_HALF_ANGLE_BASIS,
                'divergent_half_angle_deg': nozzle_geometry_table['half_angle'],
                'exit_angle_deg': nozzle_geometry_table['exit_angle'],
                'nozzle_type': getattr(self, 'nozzle_type', NOZZLE_TYPE_DEFAULT),
                'nozzle_contour_modelled': nozzle_geometry_table['modelled'],
                'length_fraction_of_15deg_conical':
                    nozzle_geometry_table['length_fraction'],
                'throat_diameter_mm': m_to_mm(nozzle_geom['throat_diameter']),
                'exit_diameter_mm': m_to_mm(nozzle_geom['exit_diameter']),
                'nozzle_length_mm': m_to_mm(nozzle_geom['nozzle_length']),
                'contraction_ratio': self._contraction_ratio(),
                'expansion_ratio': nozzle_geom['expansion_ratio'],
                'expansion_ratio_source': (
                    'user input (nozzle expansion ratio)'
                    if getattr(self, 'expansion_ratio_input', None) is not None
                    else (
                        'ambient-matched at sea level'
                        if getattr(self, '_expansion_clamp', None) is None
                        else 'ambient-matched optimum bound by the solver '
                             f'{getattr(self, "_expansion_clamp", "")} '
                             f'({EXPANSION_RATIO_SOLVER_MIN:g} / '
                             f'{EXPANSION_RATIO_SOLVER_MAX:g}) - NOT '
                             'ambient-matched')),
                # P3B2-09: kırpma olgusu sayının yanında durur.
                'expansion_ratio_clamp': getattr(self, '_expansion_clamp',
                                                 None),
                # ÖH D20 / P3B2-09 ŞART md. 2: kırpmanın hangi BANTLA
                # yapıldığı da yayımlanır — çözücü dalı ile kaba yedek dalın
                # bantları farklıdır ve sayıya bakan biri hangisinin
                # bağladığını görebilmelidir.
                'expansion_ratio_clamp_band': list(
                    getattr(self, '_expansion_clamp_band',
                            (EXPANSION_RATIO_SOLVER_MIN,
                             EXPANSION_RATIO_SOLVER_MAX))),
                # ŞART md. 1: çıkış basıncı ÇÖZÜLDÜ MÜ? Çözülemediyse sayı
                # uydurulmaz (P_e = NaN) ve hüküm burada adıyla durur.
                'exit_pressure_status': (
                    'NOT_SOLVED'
                    if getattr(self, '_exit_pressure_unsolved', None)
                    else 'SOLVED'),
                'exit_pressure_status_basis': (
                    'the exit pressure could not be solved from the '
                    'expansion ratio ('
                    f'{getattr(self, "_exit_pressure_unsolved", "")}); no '
                    'substitute value is published - the ambient pressure is '
                    'NOT assigned to the exit plane'
                    if getattr(self, '_exit_pressure_unsolved', None)
                    else 'solved isentropically from the expansion ratio '
                         '(Sutton & Biblarz 9th ed., Eq. 3-25/3-30) - the '
                         'same chain the altitude table uses'),
                'expansion_ratio_unclamped': getattr(
                    self, '_expansion_unclamped', None),
                'expansion_ratio_matched': getattr(
                    self, 'expansion_ratio_matched',
                    nozzle_geom['expansion_ratio']),
                'exit_pressure_bar': nozzle_geom['exit_pressure'],
                # --- ÖH defter P3B2-07 (D18) -------------------------------
                # Burada konik bağıntı λ=(1+cos α)/2 ÇAN konturunun çıkış
                # açısıyla değerlendiriliyordu; oysa bu dosyanın kendi
                # `_divergence_efficiency` docstring'i o bağıntının çan
                # konturunda GEÇERSİZ olduğunu yazıp LAMBDA_BELL'e geçiyor.
                # Ölçüldü (once.json, bell_80): Isp'ye FİİLEN uygulanan λ
                # 0,985000 iken bu yaprak 0,994508, irtifa döngüsü ise nozul
                # tipinden bağımsız sabit 15° ile 0,982963 yayımlıyordu —
                # aynı yanıtta ÜÇ λ. Üçü de tek kaynağa bağlandı.
                'divergence_efficiency': lam_div,
                'divergence_efficiency_source': lam_div_source,
                'lambda_divergence_applied': lam_div,
            },

            # --- Injector Design Details ---
            'injector_design': {
                'injector_type': injector['injector_type'],
                'number_of_elements': injector['number_of_elements'],
                'fuel_orifice_diameter_mm': injector['fuel_orifice_diameter'],
                'oxidizer_orifice_diameter_mm': injector['ox_orifice_diameter'],
                'injection_pressure_drop_fuel_bar': injector['fuel_pressure_drop'],
                'injection_pressure_drop_ox_bar': injector['ox_pressure_drop'],
                # v2.6.26: burada sabit 30.0 vardı ve enjektör TİPİ ne olursa
                # olsun (swirl, pintle, gaz-gaz) aynı sayı basılıyordu; oysa
                # injector_design bu açıyı zaten tipine göre ÇÖZÜYOR.
                **self._spray_angle_report(),
                # P3B2-06 (ÖH D17): AYNI manifolda İKİ ÇAP vardı.
                # Burada beyansız bir kaba kural yazılıydı
                # (max(10/12 mm, 2,5 x d_eş)) ve aynı yanıtın
                # injector_design_detail.*_circuit.manifold.d_mm alanı
                # devre modelinin ÇÖZDÜĞÜ (alan oranı + hız oranı
                # sınırlarına oturtulmuş) çapı yayımlıyordu — ölçüldü
                # (once.json P3B2-06): yakıt 24,93 ⟷ modül çözümü, oksit.
                # 34,00 ⟷ modül çözümü. İki sayı, tek manifold, künye yok.
                # Kaba kural KALDIRILDI: sayı modülün çözümünden gelir;
                # modül çözemediyse UYDURULMAZ (anahtar yayımlanmaz) ve
                # nedeni manifold_diameter_basis'te durur.
                **self._manifold_diameter_report(injector),
                'fuel_injection_velocity_m_s': injector['fuel_injection_velocity'],
                'ox_injection_velocity_m_s': injector['ox_injection_velocity'],
                'combustion_efficiency': injector['combustion_efficiency'],
                # P3B2-08: künye ve birim burada da sayının yanında durur;
                # eskiden injector_design bloğu sayıyı KÜNYESİZ taşıyordu.
                'combustion_efficiency_source': injector[
                    'combustion_efficiency_source'],
                'combustion_efficiency_unit': injector[
                    'combustion_efficiency_unit'],
                'discharge_coefficient_fuel': injector['discharge_coefficient_fuel'],
                'discharge_coefficient_ox': injector['discharge_coefficient_ox'],
                'droplet_diameter_micron': injector['droplet_diameter'],
                'critical_weber_number': injector['critical_weber_number'],
                'critical_weber_number_basis':
                    injector['critical_weber_number_basis'],
            },

            # --- Design Summary ---
            'design_summary': {
                'title': f'Liquid Motor ({self.fuel_type}/{self.oxidizer_type}) - Design Summary',
                'status': design_status,
                # Etiketin NEDEN o olduğu ve hangi eniyilemenin FİİLEN
                # uygulandığı okunabilir olmalı: etiketin tek başına gezmesi
                # bu bulgunun ta kendisiydi.
                'status_basis': design_status_basis,
                'optimizations_applied': eniyilemeler,
                'key_dimensions': {
                    'chamber_diameter_mm': cooling['chamber_diameter'],  # already in mm
                    'chamber_length_mm': cooling['chamber_length'],  # already in mm
                    'nozzle_throat_mm': m_to_mm(nozzle_geom['throat_diameter']),
                    'nozzle_exit_mm': m_to_mm(nozzle_geom['exit_diameter']),
                    'nozzle_length_mm': m_to_mm(nozzle_geom['nozzle_length']),
                    # P3B2-02/-03: konverjan koni ARTIK sayılıyor. Ölçüldü
                    # (once.json): eski satır chamber_length + divergent
                    # topluyordu, konverjan koniyi (127,95 mm) atlıyordu —
                    # yayımlanan 274,506 mm, aynı yanıttaki
                    # cooled_channel_length 402,456 mm (+%46,6) ve STEP/CAD
                    # ihracı da 402,456 mm çiziyordu. Panelde okunan motor
                    # boyu, ihraç edilen motorun %68'iydi. Üç bölümün toplamı
                    # tek tanımdır (bkz. test_endpoint_params.py
                    # ::test_cooled_channel_length_covers_all_three_sections).
                    'convergent_length_mm': cooling['convergent_length'],
                    'overall_length_mm': (cooling['chamber_length']
                                          + cooling['convergent_length']
                                          + m_to_mm(nozzle_geom['nozzle_length'])),
                    # --- ÖH D24 · P9B2-24 (kalan yarı: ÖN KAPAK) ----------
                    # D23'te bu kalemin BÜYÜK ayağı (yakınsak koni) kapandı
                    # ve ölçüldü ki kalan farkın TAMAMI x < 0'daki ön
                    # kapaktır: yayımlanan 401,536 ⟷ STEP montajı 408,286 mm
                    # (+6,750 mm). Bu ağaçta yeniden ölçüldü (once.json,
                    # P9B2-24; 10 kN RP-1/LOX, 30 bar, MR=2,2, ε=12):
                    # yayımlanan 517,529 mm, imalat STEP'inin çizdiği düz
                    # kapak 7,001 mm — yani indirilen katı yayımlanan boydan
                    # %1,353 UZUN ve iki sayı hiçbir alanda uzlaştırılmıyordu.
                    # Kullanıcı gövdesini yayımlanan boya göre boyutlandırıp
                    # daha uzun bir motor indiriyordu.
                    #
                    # SAYI UYDURULMAZ: kapak boyu, imalat STEP'inin ÇİZDİĞİ
                    # parçanın kendisidir; ihraç katmanı onu
                    # ``end_cap_analysis.flat_head_thickness``tan okur
                    # (export/cad_visualization._front_cap_design), burası da
                    # AYNI alandan okur — tek kaynak. Yapısal analiz kapağı
                    # boyutlandıramadıysa (status != 'sized') alanlar None
                    # kalır ve künye nedenini söyler; kapaklı boy tahmin
                    # edilmez. Hibrit motordaki adlandırma deseninin sıvı
                    # karşılığıdır (total_motor_length_with_caps_mm /
                    # forward_closure_length_mm).
                    'forward_closure_length_mm': _forward_closure_mm,
                    'overall_length_with_closure_mm': (
                        None if _forward_closure_mm is None else
                        (cooling['chamber_length']
                         + cooling['convergent_length']
                         + m_to_mm(nozzle_geom['nozzle_length'])
                         + _forward_closure_mm)),
                    'overall_length_basis': (
                        'cylindrical chamber + convergent cone + divergent '
                        'nozzle, the same three sections summed by '
                        'cooling_system.cooled_channel_length and by the '
                        'STEP/STL export (export/motor_geometry.py). It '
                        'EXCLUDES the forward closure head, which the '
                        'manufacturing STEP draws at x < 0: '
                        + _forward_closure_basis),
                },
                'masses': {
                    'engine_mass_kg': engine_mass,
                    'engine_mass_source': (
                        'component shell geometry x material density '
                        '(component_sizing.total_dry_mass)'),
                    # ÖH D36 / LU-1: süre yoksa bu iki alan aşağıda
                    # (yayım kapısı) SİLİNİR ve basis gerekçeyi taşır.
                    'propellant_mass_kg': (
                        None if burn_time is None
                        else self.mdot_total * burn_time),
                    # A11: tank kartındaki kütle bu sayının 1.15 katıdır ve
                    # bunu KENDİ beyan eder — iki sayı aynı kavram değildir.
                    'propellant_mass_basis': (
                        BURN_TIME_NOT_SUPPLIED_REASON if burn_time is None else
                        'nominal burned mass = total mass flow x burn time; '
                        'the tank card loads this x '
                        f'{TANK_PROPELLANT_RESERVE_FACTOR:g} reserve and '
                        'declares it (propellant_tanks.system_summary.'
                        'total_propellant_mass_basis)'),
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
                # v2.6.26 (bulgu B1): metin koşulsuz "design optimised" diyordu.
                # Hiçbir eniyileme çalışmadığında bu iddia yanlıştı; fiil artık
                # duruma göre seçilir.
                'recommendation': (
                    f'Liquid engine design '
                    f'{"optimised" if eniyilemeler else "sized"} for the given '
                    f'parameters. '
                    f'T/W={thrust_to_weight:.1f}, Isp(vac)={actual_isp_vac:.0f} s, '
                    f'c*={self.c_star:.0f} m/s. '
                    f'{self.cooling_type.capitalize()} cooling, {self.injector_type} injector.'
                ),
            },
        }

        # --- v2.6.27 (B3): lüle iç konturu TEK kaynaktan yayımlanır --------
        # motor_viz3d.js selectNozzleContour bu bloğu okur; blok yoksa sahne
        # yerel üretime düşer ve bunu çipiyle beyan eder. Örnekleyici, 2B
        # kesit / STL-STEP dışa aktarımının kullandığı fonksiyonun AYNISIDIR
        # (nozzle_design.sample_nozzle_inner_contour). Sıvı rotasının üst
        # düzey birimleri KARIŞIKTIR (chamber mm, throat/exit m — bkz.
        # export/motor_geometry.liquid_results_to_motor_geometry docstring'i);
        # bu yüzden örnekleyiciye METRE bazlı ayrı bir sözlük kurulur ve
        # değerler dışa aktarım otoritesinin okuduğu kaynakların TA
        # KENDİSİDİR (cooling chamber/convergent/divergent, nozzle_geom
        # throat/exit) — iki yol aynı geometriyi üretir.
        #
        # ORİJİN SÖZLEŞMESİ (doğrulandı): örnekleyicinin ilk noktası
        # konverjan GİRİŞİDİR (kamara-lüle birleşimi) — s=0'da
        # r = rt + (rc-rt)·(0.5+0.5·cos 0) = rc, z = 0; z çıkışa doğru artar.
        # viz3d bu varsayımla çizer; boğaz-orijinli seri lüleyi yanlış
        # konumlandırır. Bekçi: tests/test_motor_geometri_yayimi.py.
        # Örnekleyici başarısız olursa blok yayımlanmaz (uydurma kontur yok).
        try:
            from hrma.engines.nozzle_design import sample_nozzle_inner_contour
            md_geo = {
                # cooling sözlüğü mm taşır; burada metreye çevrilir.
                'chamber_diameter': float(cooling['chamber_diameter']) / 1000.0,
                'throat_diameter': float(nozzle_geom['throat_diameter']),  # m
                'exit_diameter': float(nozzle_geom['exit_diameter']),      # m
                'nozzle_angles': results['nozzle_angles'],
                'nozzle_convergent_length':
                    float(cooling['convergent_length']) / 1000.0,          # m
                'nozzle_divergent_length':
                    float(cooling['divergent_length']) / 1000.0,           # m
            }
            pts_mm, kontur_meta = sample_nozzle_inner_contour(md_geo)
            results['nozzle_contour'] = {
                'points': [[float(z) / 1000.0, float(r) / 1000.0]
                           for z, r in pts_mm],
                '_basis': (
                    'sampled inner flow-path contour from hrma.engines.'
                    'nozzle_design.sample_nozzle_inner_contour — the same '
                    'sampler the 2D cross-section and the STL/STEP exports '
                    'consume, fed with the liquid solver geometry in metres '
                    '(cooling-integration chamber diameter and convergent/'
                    'divergent lengths, nozzle throat/exit diameters). '
                    'points are [z_m, r_m] pairs in metres; the FIRST point '
                    'is the convergent inlet (chamber-nozzle junction, '
                    'z = 0, r = chamber radius) and z increases toward the '
                    'nozzle exit. Divergent length source: '
                    + str(kontur_meta.get('divergent_length_source'))),
            }
        except Exception:
            # Fail-closed: kontur üretilemiyorsa ÜRETİLMEZ; viz yerel üretime
            # düşer ve kaynağı 'kontur: yerel üretim' çipiyle beyan eder.
            pass

        # --- v2.6.27 (B1): rejeneratif kanal geometrisi -------------------
        # motor_viz3d.js coolingChannelSpec sözleşmesi: {n_channels,
        # channel_width_m, channel_height_m, land_width_m, _basis}. Kaynak
        # calculate_cooling_requirements'ın kanal geometrisidir (sayı kullanıcı
        # girdisi ya da boğaz çevresi/hatvesinden; kesit tek doğruluk
        # kaynağından, derinlik hız hedefine göre büyütülmüş olabilir —
        # channel_count_source/channel_height_basis aynı sözlükte). Soğutma
        # REJENERATİF DEĞİLSE blok yayımlanmaz: frezeli soğutma kanalı ancak
        # rejeneratif gömlekte imal edilir; film/ablatif/radyatif cidara
        # kanal çizdirmek fabrikasyondur (bekçisi: fabrikasyon-yok testi).
        if self.cooling_type == 'regenerative':
            n_kanal = int(cooling.get('cooling_channels') or 0)
            kanal_w_m = float(cooling.get('channel_width_mm') or 0.0) / 1000.0
            kanal_h_m = float(cooling.get('channel_height_mm') or 0.0) / 1000.0
            if n_kanal >= 1 and kanal_w_m > 0.0 and kanal_h_m > 0.0:
                kanal_blok = {
                    'n_channels': n_kanal,
                    'channel_width_m': kanal_w_m,
                    'channel_height_m': kanal_h_m,
                    '_basis': (
                        'regenerative cooling channel geometry from '
                        'calculate_cooling_requirements (cooling_system.'
                        'cooling_channels / channel_width_mm / '
                        'channel_height_mm converted to metres). Channel '
                        'count source: '
                        + str(cooling.get('channel_count_source'))
                        + '. land_width_m, when present, is derived at the '
                        'binding section, the channel base at the throat: '
                        '2*pi*(throat_radius + hot_wall_thickness)/n_channels'
                        ' - channel_width (cooling_system.channel_count_fit;'
                        ' channels are constant-width, so the land varies '
                        'along the axis and is narrowest there).'),
                }
                # ÖH A2 sivi-sogutma · F-17: kaburga (land) sığma ölçütüyle
                # AYNI kesitte türetilir — kanal TABANI çevresi (eskiden gaz
                # tarafı iç çevresi pi*d_t idi; ölçüt tek tanıma geçince
                # buradaki ikinci yarıçap da söküldü). Pozitif değilse
                # (kanallar sığmıyor — çözücü uyarıyor) alan YAYIMLANMAZ.
                _uyg = cooling.get('channel_count_fit') or {}
                _c_ref_m = float(_uyg.get('reference_circumference_mm')
                                 or 0.0) / 1000.0
                land_m = ((_c_ref_m / n_kanal) - kanal_w_m
                          if _c_ref_m > 0.0 else float('nan'))
                if np.isfinite(land_m) and land_m > 0.0:
                    kanal_blok['land_width_m'] = float(land_m)
                results['cooling_channels'] = kanal_blok

        # --- v2.6.27 (B2): enjektör delik deseni — yalnız GERÇEK çözümden --
        # motor_viz3d.js readInjectorPattern sözleşmesi: {n_holes,
        # hole_diameter_m, pattern_type, impingement_angle_deg?, _basis}.
        # Kaynak devre modelinin başarılı çözümüdür (injector_design_detail);
        # modül çözemeyip eski Bernoulli tahmini kaldıysa blok YOKTUR — iki
        # farklı çözücünün sayıları tek desende harmanlanmaz. n_rings hiçbir
        # yerde hesaplanmadığı için yayımlanmaz (hesaplanmayan alan konmaz).
        detay = injector.get('injector_design_detail')
        if isinstance(detay, dict) and detay.get('status') == 'success':
            oxc = detay.get('ox_circuit') or {}
            fc = detay.get('fuel_circuit') or None
            desen_sozcugu = INJECTOR_PATTERN_WORD.get(
                str(detay.get('injector_type') or '').lower())
            n_ox = int(oxc.get('n_orifices') or 0)
            n_fuel = int((fc or {}).get('n_orifices') or 0)
            if desen_sozcugu and (n_ox + n_fuel) >= 1:
                desen = {
                    # Yüzeydeki TOPLAM delik sayısı: oksitleyici + yakıt
                    # devresi (iki-devreli yüzde her delik gerçektir).
                    'n_holes': n_ox + n_fuel,
                    'pattern_type': desen_sozcugu,
                    '_basis': (
                        'orifice plan from the injector design model '
                        '(injector_design_detail): n_holes is the TOTAL face '
                        f'orifice count, oxidizer circuit {n_ox} + fuel '
                        f'circuit {n_fuel}. n_rings is not computed by any '
                        'solver and is therefore not published.'),
                }
                # Tek delik çapı ancak tek devre varsa ya da iki devrenin
                # çapı fiilen aynıysa GERÇEKTİR; farklıysa tek sayı uydurmak
                # yakıt deliklerini oksitleyici çapında göstermek olur —
                # alan yayımlanmaz, iki çap _basis'te beyan edilir.
                d_ox_mm = float(oxc.get('orifice_d_mm') or 0.0)
                d_fuel_mm = float((fc or {}).get('orifice_d_mm') or 0.0)
                if n_fuel == 0 and d_ox_mm > 0:
                    desen['hole_diameter_m'] = d_ox_mm / 1000.0
                elif (d_ox_mm > 0 and d_fuel_mm > 0
                        and abs(d_ox_mm - d_fuel_mm)
                        <= 0.01 * max(d_ox_mm, d_fuel_mm)):
                    desen['hole_diameter_m'] = d_ox_mm / 1000.0
                else:
                    desen['_basis'] += (
                        ' hole_diameter_m is not published because the two '
                        f'circuits differ (ox {d_ox_mm:.3f} mm, fuel '
                        f'{d_fuel_mm:.3f} mm); a single diameter would '
                        'misrepresent one circuit.')
                # Açı yalnız GERÇEKTEN çözülen/ilan edilen yerden gelir:
                #  - çarpışmalı: pattern.impingement.half_angle_deg (SP-8089
                #    tasarım seçimi; temeli modülün kendi beyanında),
                #  - swirl: atomization.spray_cone_half_angle_deg (çözülür).
                # Sözleşme İKİ JET ARASINDAKİ TAM açıyı taşır (viz yarılar).
                yarim_aci = None
                if desen_sozcugu == 'impinging':
                    yarim_aci = ((detay.get('pattern') or {})
                                 .get('impingement') or {}).get('half_angle_deg')
                elif desen_sozcugu == 'swirl':
                    yarim_aci = (detay.get('atomization') or {}).get(
                        'spray_cone_half_angle_deg')
                if yarim_aci is not None and np.isfinite(float(yarim_aci)) \
                        and float(yarim_aci) > 0:
                    desen['impingement_angle_deg'] = 2.0 * float(yarim_aci)
                results['injector_pattern'] = desen

        # --- B4 (v2.6.27): sessizce yok sayılan gövde alanı olmaz ----------
        # Beyan EN SONDA üretilir: karşılaştırılacak "fiilen kullanılan değer"
        # ancak sonuç sözlüğü tamamlandığında bellidir. Uyarı listesi de
        # yeniden anlık görüntülenir — 'input_warnings' yukarıda kopyalandığı
        # için burada üretilen uyarı aksi hâlde kullanıcıya ulaşmazdı.
        okunmayanlar = self._declare_unread_inputs(results)
        if okunmayanlar:
            results['inputs_not_used'] = okunmayanlar
            results['input_warnings'] = list(self.design_warnings)

        # --- ÖH D36 / LU-1 — YANMA SÜRESİ YAYIM KAPISI (fail-closed) -------
        # Süre verilmediyse ``burn_time`` ve ondan türeyen kütle alanları
        # YAYIMLANMAZ; künye ``burn_time_source = 'not_supplied'`` ve
        # ``burn_time_reason`` adıyla kalır. Tüketiciler (.eng üreticisi,
        # PDF, arayüz) alanı bulamayınca kendi fail-closed dallarına düşer —
        # sahte 300 s'lik bir toplam impuls/itici kütlesi artık üretilmez.
        if burn_time is None:
            results.pop('burn_time', None)
            results['burn_time_reason'] = BURN_TIME_NOT_SUPPLIED_REASON
            _masses = results.get('design_summary', {}).get('masses')
            if isinstance(_masses, dict):
                _masses.pop('propellant_mass_kg', None)
                _masses.pop('burn_time_s', None)
        return results

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
            kayitli = getattr(self, 'rho_ox_source', None)
        else:
            rho = float(self.rho_fuel)
            user = self.overrides.get('fuel_density')
            kayitli = getattr(self, 'rho_fuel_source', None)
        # P3B1-01 (ÖH D15): künye TAHMİN EDİLMEZ, atama anında kaydedilen
        # kaynak okunur. Eski satır 'user input' değilse koşulsuz 'built-in
        # propellant table' basıyordu; tabloda OLMAYAN çiftte (arayüzün 10
        # çiftinden 5'i) bu düpedüz yalandı — ölçüldü, lh2/n2o4'te 800 kg/m³
        # uydurma sayı 'tablodan geldi' diye yayımlanıyordu.
        if user not in (None, ''):
            source = 'user input'
        elif kayitli:
            source = kayitli
        else:
            source = 'built-in propellant table'
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
        if burn_time is None:
            # ÖH D36 / LU-1: süre yok -> hacim yok (None); besleme kartı
            # ``volume_source`` ile gerekçeyi yayımlar.
            return None
        propellant_mass = mass_flow_rate * burn_time  # kg
        tank_volume, _, _, _ = self._size_tank(propellant_mass, propellant_type)
        return tank_volume

    def _tank_volume_source(self):
        """Besleme kartı tank hacminin kaynak künyesi (LU-1)."""
        burn_time, burn_time_source = self._burn_time()
        if burn_time is None:
            return BURN_TIME_NOT_SUPPLIED_REASON
        return ('total mass flow x burn time (%s) / propellant density, '
                'plus ullage (_size_tank)' % burn_time_source)

    def _tank_pressure_bar(self):
        """Tank işletme basıncı [bar] — TEK tanım noktası (A11, 2.7 kapı #4).

        Eski durum: aynı yanıtta DÖRT ayrı tanım noktası vardı ve basınç
        beslemeli çevrimde ikisi ÇELİŞİYORDU:

        * besleme kartı / pompa zinciri / çevrim çözücüsü: kullanıcının
          feed_pressure girdisi (25 kN örneğinde 105 bar),
        * ayrıntılı tank kartı (_design_propellant_tanks): (P_c + 5 bar)
          çarpı 1.2 türetilmiş tahmini (aynı örnekte 90 bar) — kullanıcının
          GERÇEK girdisini yok sayıyordu; cidar, tank kütlesi, MEOP ve
          emniyet vanası ayarı hep bu ikinci sayıdan türüyordu,
        * turbopompalı dalda tank kartı 3e5 Pa satır içi literali,
          autogenous bloğu da aynı literali kullanıyordu — bugün
          PUMP_TANK_PRESSURE_DEFAULT_BAR ile aynı sayı, ama sabit değişse
          sessizce ayrışırlardı.

        Artık NPSH zincirinin (B5, v2.6.27) kullandığı mantığın TEK kopyası
        buradadır; besleme kartı, pompa boyutlandırması, çevrim çözücüsü,
        ayrıntılı tank kartı ve autogenous bloğu hepsi buradan okur.

        Returns:
            (bar, kaynak_metni)
        """
        if getattr(self, 'engine_cycle', '') == 'pressure_fed':
            user = getattr(self, 'feed_pressure_input_bar', None)
            if user:
                return float(user), TANK_PRESSURE_SOURCE_PRESSURE_FED_USER
            return (PUMP_TANK_PRESSURE_DEFAULT_BAR,
                    TANK_PRESSURE_SOURCE_PRESSURE_FED_DEFAULT)
        # F3 (ÖH D18 fizik-a2): turbopompa dalında tank basıncı NPSH
        # gereksiniminden BOYUTLANDIRILIR. Ölçüldü (once_f2f3.json): eski
        # sabit 3,0 bar beş koşumun beşinde de aynıydı ve 500 kN LOX/RP-1'de
        # NPSH_a = -2,354 m veriyordu (tasarım 'not_feasible').
        npsh_tank = self._tank_pressure_from_npsh()
        if npsh_tank is not None:
            return npsh_tank['bar'], TANK_PRESSURE_SOURCE_TURBOPUMP_NPSH
        return (PUMP_TANK_PRESSURE_DEFAULT_BAR,
                TANK_PRESSURE_SOURCE_TURBOPUMP_FALLBACK)

    # ------------------------------------------------------------------
    # F3: NPSH gereksiniminden tank basıncı (ÖH D18 fizik-a2)
    # ------------------------------------------------------------------
    @staticmethod
    def _npsh_velocity_head_factor(propellant):
        """(k_v, sınıf_adı) — SP-8109 §3.2.1.2 giriş hız-yükü çarpanı.

        Sınıf iticinin adından değil, DEPOLAMA SINIFINDAN gelir: kriyojenik
        oksitleyici (LOX, LF2) 2,3; sıvı hidrojen 1,3; geri kalan her şey
        (RP-1, hidrazin ailesi, N2O4, nitrik asit, su) 3,0.
        """
        ad = str(propellant or '').strip().lower()
        if ad in ('lh2', 'liquid_hydrogen', 'hydrogen'):
            return NPSH_VELOCITY_HEAD_FACTORS['hydrogen'], 'hydrogen'
        if ad in ('lox', 'liquid_oxygen', 'lf2', 'liquid_fluorine'):
            return (NPSH_VELOCITY_HEAD_FACTORS['cryogenic_ox'],
                    'cryogenic_ox')
        return NPSH_VELOCITY_HEAD_FACTORS['storable'], 'storable'

    def _npsh_vapor_pressure(self, propellant):
        """(p_buhar [Pa], künye) — gerçek kayıt > beyanlı NBP yedeği.

        ``_design_pump`` içindeki mantığın TEK kopyası; iki yerde iki farklı
        buhar basıncı seçilmesi (ve tank basıncının pompadan farklı bir
        p_v ile boyutlanması) böylece olanaksızdır.
        """
        record = None
        if propellant is not None:
            _, record = self._feed_fluid_record(propellant)
        if record is not None and record.get('vapor_pressure_Pa') is not None:
            return (float(record['vapor_pressure_Pa']),
                    str(record.get('vapor_pressure_source')))
        return (PUMP_NPSH_VAPOR_PRESSURE_BAR * PA_PER_BAR,
                'vapor pressure record missing for '
                f"'{propellant}': normal-boiling-point storage saturation "
                f'({PUMP_NPSH_VAPOR_PRESSURE_BAR:g} bar, '
                'PUMP_NPSH_VAPOR_PRESSURE_BAR) assumed - a declared '
                'fallback, NOT a computed property')

    def _tank_pressure_from_npsh(self):
        """Pompaların NPSH gereksiniminden gereken tank basıncı, ya da None.

        Her pompa için (SP-8109 §3.2.1.2 + SP-125 eş. 6-8 tersi):

            c_m         = emme hattı hızı (hattın KENDİ Darcy zincirinden)
            NPSH_gerekli = k_v · c_m² / (2g)
            p_tank      = p_v + ρg(k·NPSH_gerekli − z) + Δp_emme

        Dönen sayı iki pompanın İSTEDİĞİ BASINCIN BÜYÜĞÜdür: HRMA kademe
        başına tek basınçlandırma seviyesi modeller, küçüğünü seçmek
        diğer pompayı kavitasyona sokardı.

        Çözülemezse (hat ya da akışkan kaydı yok) ``None`` döner ve çağıran
        beyanlı geri dönüşe düşer — sessiz sayı üretilmez.
        """
        onbellek = getattr(self, '_npsh_tank_cache', None)
        if onbellek is not None:
            return onbellek if onbellek != {} else None
        try:
            drops = self._feed_line_drops_for_npsh()
        except Exception as exc:  # fix-9: istisna sınıfı künyeye
            self._npsh_tank_fail_reason = f'{type(exc).__name__}: {exc}'[:160]
            self._npsh_tank_cache = {}
            return None
        if not drops:
            self._npsh_tank_cache = {}
            return None
        kalemler = {}
        dusenler = {}
        for etiket, hat, yogunluk, itici in drops:
            try:
                c_m = float(hat['line_velocity_m_s'])
                k_v, sinif = self._npsh_velocity_head_factor(itici)
                npsh_req = npsh_required_velocity_head_m(c_m, k_v)
                p_v, p_v_kaynak = self._npsh_vapor_pressure(itici)
                emme = self._suction_line_dp(hat, yogunluk)
                dp_pa = float(emme['total']) * PA_PER_BAR
                # ÖH D21 · OH-D20-09 — TEK MARJ. Buraya SP-8109 hız-yükü
                # kuralının TABANI geliyor; o taban zaten marjlıdır, üstüne
                # SP-8107 oranı BİNMEZ (bkz. NPSH_SINGLE_MARGIN_CONTRACT).
                p_tank_pa = tank_pressure_from_npsh_Pa(
                    p_v, float(yogunluk), npsh_req, dp_pa,
                    NPSH_STATIC_HEAD_DEFAULT_M,
                    NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE)
            except Exception as exc:
                # ÖH D21 · OH-D20-08 — SESSİZ DEĞİL. Eskiden burada
                # `continue` vardı: bir pompanın çözümü patlarsa pompa
                # defterden düşüyor, sağ kalan öteki pompa governing_pump
                # oluyor ve npsh_tank_sizing bunu HİÇ söylemiyordu.
                # ÖLÇÜLDÜ (once.json OH-D20-08): lox buhar basıncı
                # çözülemediğinde tank basıncı 4,3900 -> 2,3691 bar'a
                # (-%46,0) düşüyor, status hâlâ 'sized' diyordu.
                dusenler[etiket] = f'{type(exc).__name__}: {exc}'[:200]
                continue
            if not np.isfinite(p_tank_pa) or p_tank_pa <= 0.0:
                dusenler[etiket] = (
                    'required tank pressure did not solve to a finite '
                    f'positive value ({p_tank_pa!r} Pa)')
                continue
            kalemler[etiket] = {
                'inlet_velocity_m_s': c_m,
                'velocity_head_factor': float(k_v),
                'velocity_head_class': sinif,
                'npsh_required_m': float(npsh_req),
                'vapor_pressure_Pa': float(p_v),
                'vapor_pressure_source': p_v_kaynak,
                'suction_loss_bar': float(emme['total']),
                'required_tank_pressure_bar': float(p_tank_pa / PA_PER_BAR),
                'propellant': str(itici),
            }
        if not kalemler:
            if dusenler:
                self._npsh_tank_fail_reason = (
                    'no pump solved: '
                    + '; '.join(f'{a}: {b}' for a, b in
                                sorted(dusenler.items())))[:400]
            self._npsh_tank_cache = {}
            return None
        # ÖH D21 · OH-D20-08 — FAIL-CLOSED. Bu türetim iki pompanın
        # İSTEDİĞİ basıncın BÜYÜĞÜdür; bir pompa defterden düşerse kalanın
        # istediği sayı BÜYÜĞÜ DEĞİLDİR ve o pompayı kavitasyona sokar.
        # Eksik pompayla "boyutlandırıldı" hükmü verilmez: sayı yayımlanmaz,
        # düşen pompa ve istisnası ADIYLA rapor edilir.
        if dusenler:
            self._npsh_tank_fail_reason = (
                'incomplete pump set: '
                + '; '.join(f'{a}: {b}' for a, b in sorted(dusenler.items()))
            )[:400]
            self._npsh_tank_cache = {}
            self._npsh_tank_dropped = dict(dusenler)
            self._npsh_tank_solved = {
                a: float(b['required_tank_pressure_bar'])
                for a, b in kalemler.items()}
            return None
        yoneten = max(kalemler, key=lambda k:
                      kalemler[k]['required_tank_pressure_bar'])
        sonuc = {
            'bar': float(kalemler[yoneten]['required_tank_pressure_bar']),
            'governing_pump': yoneten,
            'per_pump': kalemler,
            # ÖH D21 · OH-D20-09: tek marj sözleşmesi — hız-yükü kuralının
            # üstüne SP-8107 oranı binmez.
            'margin_factor': float(NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE),
            'margin_factor_basis': NPSH_SINGLE_MARGIN_CONTRACT,
            'static_head_m': float(NPSH_STATIC_HEAD_DEFAULT_M),
            'basis': TANK_PRESSURE_SOURCE_TURBOPUMP_NPSH,
        }
        self._npsh_tank_cache = sonuc
        return sonuc

    def _npsh_tank_sizing_report(self):
        """NPSH tabanlı tank basıncı boyutlandırma defteri (ya da None).

        SP-8107 Table II'nin ölçülmüş pompa GİRİŞ basınçları (22-77 psia =
        1,52-5,31 bar) referans banttır; türetilen basıncın o bandın neresine
        düştüğü yayımlanır. Bant bir HÜKÜM DEĞİLDİR (uçuş donanımı başlangıç
        geçici rejimi için asgarinin üstüne basınçlandırır, HRMA o rejimi
        modellemez) — yalnız akıl sağlığı çapasıdır.
        """
        if getattr(self, 'engine_cycle', '') == 'pressure_fed':
            return None
        rapor = self._tank_pressure_from_npsh()
        if rapor is None:
            # ÖH D21 · OH-D20-08: NEDEN çözülmediği künyeye girer; per-pompa
            # istisnası artık sessizce yutulmuyor.
            blok = {
                'status': 'not_solved',
                'basis': TANK_PRESSURE_SOURCE_TURBOPUMP_FALLBACK,
            }
            sebep = getattr(self, '_npsh_tank_fail_reason', None)
            if sebep:
                blok['not_solved_reason'] = str(sebep)
            dusen = getattr(self, '_npsh_tank_dropped', None)
            if dusen:
                blok['excluded_pumps'] = dict(dusen)
                blok['solved_pumps_bar'] = dict(
                    getattr(self, '_npsh_tank_solved', {}) or {})
                blok['fail_closed_basis'] = (
                    'the derived tank pressure is the MAXIMUM of the per-pump '
                    'requirements; with a pump missing from that set the '
                    'maximum is not defined and the surviving pump\'s figure '
                    'would under-pressurise the excluded one. No number is '
                    'published (see excluded_pumps for the reason).')
            return blok
        alt, ust = SP8107_INLET_PRESSURE_BAND_BAR
        p = float(rapor['bar'])
        out = dict(rapor)
        out.update({
            'status': 'sized',
            'sp8107_inlet_pressure_band_bar': list(
                SP8107_INLET_PRESSURE_BAND_BAR),
            'sp8107_band_status': ('in_band' if alt <= p <= ust
                                   else 'below_band' if p < alt
                                   else 'above_band'),
            'sp8107_band_basis': SP8107_INLET_PRESSURE_BAND_SOURCE,
        })
        return out

    def _feed_line_drops_for_npsh(self):
        """[(etiket, hat_sözlüğü, yoğunluk, itici)] — TEK hat modelinden.

        ``_line_pressure_drops`` doğrudan çağrılır (enjektör kalemi 0, çünkü
        emme tarafına girmiyor): böylece tank basıncı türetimi ile pompa
        boyutlandırması AYNI çap/hız/sürtünme zincirini okur. Kendi hat
        modelini kurmak iki ayrı hız üretirdi.
        """
        if not hasattr(self, 'mdot_fuel') or not hasattr(self, 'mdot_ox'):
            self.calculate_nozzle_geometry()
        mdot_ox = getattr(self, 'mdot_ox', None)
        mdot_fuel = getattr(self, 'mdot_fuel', None)
        if not mdot_ox or not mdot_fuel:
            return []
        mu_ox = (getattr(self, 'mu_ox', None)
                 or FEED_VISCOSITY_FALLBACK_PA_S['oxidizer'])
        mu_fuel = (getattr(self, 'mu_fuel', None)
                   or FEED_VISCOSITY_FALLBACK_PA_S['fuel'])
        # ÖH D18 fix-9 (2 Eyl 2026): D18 sıvı kulvarı (P3B3-09, b3fb65e)
        # ``_line_pressure_drops``'a zorunlu ``prop_kind`` ekledi; fizik-a2'nin
        # bu çağrısı (e726048 tabanı) 4 argümanla kalınca TypeError, üstteki
        # ``except Exception`` ile yutulup tank basıncı 'not_solved'a düşüyordu
        # (birleşik ağaç ölçümü: 3 motorda da 3,0 bar). Hat türü artık ADIYLA.
        return [
            ('oxidizer_pump',
             self._line_pressure_drops(mdot_ox, self.rho_ox, mu_ox, 0.0,
                                       'oxidizer'),
             float(self.rho_ox), self.oxidizer_type),
            ('fuel_pump',
             self._line_pressure_drops(mdot_fuel, self.rho_fuel, mu_fuel,
                                       0.0, 'fuel'),
             float(self.rho_fuel), self.fuel_type),
        ]

    def _tank_cryo_screening(self, material_key, propellant, tank_label):
        """Kriyojenik tank malzemesi taraması (ÖH defter P3B3-06).

        Döner: ``{'verdict', 'propellant_is_cryogenic', 'basis'}``.
        ``verdict`` in {'pass', 'fail', 'not_required'}. Elenen malzeme
        SESSİZ geçmez: kritik uyarı ateşlenir (fail-closed beyan zinciri).
        """
        kriyo = str(propellant or '').lower() in CRYOGENIC_PROPELLANTS
        if not kriyo:
            return {
                'verdict': 'not_required',
                'propellant_is_cryogenic': False,
                'basis': (f"'{propellant}' is stored near ambient "
                          'temperature; the cryogenic toughness screen does '
                          'not apply. ' + TANK_CRYO_SCREENING_BASIS),
            }
        # ÖH D17 (P3B3-06 ŞART / OH-D16-08): hüküm ELLE YAZILMIŞ kümeden
        # değil, deponun TEK tanımından okunur. Üç değerli: True duyarlı,
        # False duyarlı değil, None ad TANINMADI. Tanınmayan adda hüküm
        # KAZANILMAMIŞTIR — 'pass' da 'fail' da uydurma olur, bu yüzden
        # ayrı bir durum yayımlanır ve kritik uyarı ateşlenir.
        from hrma.data.materials_db import is_dbtt_sensitive
        duyarli = is_dbtt_sensitive(str(material_key))
        if duyarli is None:
            self._warn('warn.liquid.tank_material_not_cryogenic', 'critical',
                       tank=str(tank_label), material=str(material_key),
                       propellant=str(propellant))
            return {
                'verdict': 'unresolved',
                'propellant_is_cryogenic': True,
                'basis': (f"'{material_key}' is not a materials_db record, "
                          'so its low-temperature toughness class cannot be '
                          'resolved. No screening verdict is invented. '
                          + TANK_CRYO_SCREENING_BASIS),
            }
        gecti = not duyarli
        if not gecti:
            self._warn('warn.liquid.tank_material_not_cryogenic', 'critical',
                       tank=str(tank_label), material=str(material_key),
                       propellant=str(propellant))
        return {
            'verdict': 'pass' if gecti else 'fail',
            'propellant_is_cryogenic': True,
            'basis': ((f"'{material_key}' is not flagged DBTT-sensitive by "
                       'materials_db, so it is not excluded on low-'
                       'temperature toughness grounds. '
                       if gecti else
                       f"'{material_key}' IS flagged DBTT-sensitive by "
                       'materials_db (body-centred-cubic ferritic, '
                       'martensitic or refractory): it is not an acceptable '
                       'cryogenic tank material. The tank numbers below are '
                       'still computed from its strength, but the design '
                       'FAILS this screen. ')
                      + TANK_CRYO_SCREENING_BASIS),
        }

    @staticmethod
    def _cycle_card_withheld_basis(cyc_sol, what):
        """Çevrim kapanmadığında kartın NEDEN boş olduğunu söyleyen künye.

        ÖH defter P3B3-01/-02: eski kart, çevrim kapanmasa da sabitlerden
        (MR = 0,7·MR_ana, T = GAS_GENERATOR_TEMP_DEFAULT_K, PR = 8,5) bir
        tasarım uyduruyordu. Fail-closed: hüküm kazanılmadıysa sayı
        yayımlanmaz, yerine gerekçe konur.
        """
        durum = (cyc_sol or {}).get('status') or 'not_solved'
        neden = (cyc_sol or {}).get('reason')
        metin = (f'NOT published: the cycle power balance did not converge '
                 f'(status={durum})')
        if neden:
            metin += f' - {neden}'
        return (metin + f'. No {what} numbers are invented in its place; '
                'the earlier fixed assumptions (a fraction of the main '
                'chamber mixture ratio and a generic gas temperature) were '
                'not a design.')

    def _line_diameter_selection(self, mass_flow_rate: float,
                                 propellant_type: str) -> Dict:
        """Besleme hattı çapı seçimi — hız BANDI bağlayıcı kısıttır.

        ÖH defter **P3B3-04**. Eski kod ham çapı standart merdivenin EN YAKIN
        basamağına yuvarlıyordu (``min(sizes, key=|x - d|)``) ve sonucu hiç
        denetlemiyordu. Ölçüldü (RP-1/LOX, Pc 70, MR 2,3): 25 kN oksitleyici
        d_ham 37,12 mm -> 25,00 mm, hız **11,03 m/s** — beyan edilen 3-8 m/s
        bandının tavanının %38 üstünde, TEK BİR UYARI YOK. 5 kN'da aynı
        yuvarlama ters yöne kaçıyor ve hız 2,21 m/s ile bandın ALTINA
        düşüyordu. Aradaki fark masum değil: hız emme kaybına karesiyle
        girer, emme kaybı NPSH_mevcut'u belirler, NPSH pompa devrini ve çark
        çapını belirler (P3B3-03 zincirinin ilk halkası; ölçülen NPSH_a
        gidişi 13,3/1,6/5,9/9,3/3,4/-4,6/0,6/8,9 m — düzensizliğin kaynağı
        yuvarlama yönünün itkiyle zıplamasıydı).

        Yeni kural: yuvarlama ÇAPTA değil HIZDA yapılır — bandın içine
        düşen basamaklar arasından, hızı tasarım hedefine
        (FEED_LINE_TARGET_VELOCITY_MS) EN YAKIN olan seçilir. Band
        sağlanamıyorsa sayı UYDURULMAZ: banda en yakın basamak seçilir,
        ihlal ADIYLA ve ölçülen hızla beyan edilir ve uyarı ateşlenir.
        Eşikler
        FEED_LINE_MIN_VELOCITY_MS / FEED_LINE_MAX_VELOCITY_MS sabitlerinden
        okunur (tek tanım noktası).

        Döner: {'diameter_m', 'velocity_m_s', 'raw_diameter_m', 'band_status',
                'source'} — ``band_status`` in {'within', 'above', 'below'}.
        """
        # Hedef hız TEK YERDE tanımlıdır (CLAUDE.md kural 11): burada satır içi
        # 5.0 yazılıyken modül başındaki FEED_LINE_TARGET_VELOCITY_MS ile aynı
        # kavramın iki tanımı vardı ve biri değişse öbürü sessizce kalırdı.
        target_velocity = FEED_LINE_TARGET_VELOCITY_MS  # m/s (3-8 bandı)

        # Yoğunluk tank modeliyle AYNI kaynaktan (bkz. _propellant_density).
        density, _ = self._propellant_density(propellant_type)

        # A = mdot / (rho * v)
        area = mass_flow_rate / (density * target_velocity)  # m²
        diameter = 2 * np.sqrt(area / np.pi)  # m

        sizes = sorted(FEED_LINE_STANDARD_SIZES_M)

        def hiz(d, n=1):
            return (mass_flow_rate / float(n)) / max(
                density * np.pi * d ** 2 / 4.0, 1e-12)

        # Yuvarlama ÇAPTA değil HIZDA yapılır: seçim ölçütü tasarımın kendi
        # hedefidir (FEED_LINE_TARGET_VELOCITY_MS) ve band bağlayıcı kısıttır.
        # Çapta yuvarlamak (eski kural) v ~ 1/d^2 olduğu için hızı asimetrik
        # kaydırır ve bandı görmeden küçük boruyu seçebiliyordu.
        #
        # OH-D18-03: kol sayısı ARTIK sabit 1 değildir. Bandı sağlayan EN
        # KÜÇÜK paralel kol sayısı çözülür (arama n=1'den başlar, yani tek
        # kolun yettiği her motorda sonuç birebir eskisiyle aynıdır); kol
        # sayısı çıktıda adıyla durur. Paralel kollar aynı ΔP'yi paylaşır:
        # basınç düşümü TEK kolun düşümüdür, kollar debiyi böler.
        # Kol EKLEMEK hızı DÜŞÜRÜR. Tek kol zaten bandın ALTINDAysa (akış
        # merdivenin en küçük borusu için bile yavaşsa) kol eklemek durumu
        # KÖTÜLEŞTİRİR: arama yalnız tek kolun bandı ÜSTTEN aştığı durumda
        # açılır, aksi hâlde n = 1'de kalınır (eski davranış birebir korunur).
        _en_hizli_tek_kol = max(hiz(d, 1) for d in sizes)
        arama_tavani = (FEED_LINE_MAX_PARALLEL
                        if _en_hizli_tek_kol > FEED_LINE_MAX_VELOCITY_MS
                        else 1)
        n_kol, secim, durum = 1, None, None
        for n in range(1, arama_tavani + 1):
            icerde = [d for d in sizes
                      if (FEED_LINE_MIN_VELOCITY_MS <= hiz(d, n)
                          <= FEED_LINE_MAX_VELOCITY_MS)]
            if icerde:
                n_kol = n
                secim = min(icerde,
                            key=lambda d, _n=n: abs(
                                hiz(d, _n) - FEED_LINE_TARGET_VELOCITY_MS))
                durum = 'within'
                break
        if secim is None:
            # Kol sayısı tavanına kadar hiçbir (n, çap) çifti banda düşmedi:
            # sayı uydurulmaz, tavandaki kol sayısıyla banda EN YAKIN basamak
            # seçilir ve ihlal ölçülen hızıyla beyan edilir.
            n_kol = arama_tavani

            def band_uzakligi(d):
                v = hiz(d, n_kol)
                if v > FEED_LINE_MAX_VELOCITY_MS:
                    return v - FEED_LINE_MAX_VELOCITY_MS
                return FEED_LINE_MIN_VELOCITY_MS - v
            secim = min(sizes, key=band_uzakligi)
            durum = ('above' if hiz(secim, n_kol) > FEED_LINE_MAX_VELOCITY_MS
                     else 'below')
        v_son = hiz(secim, n_kol)
        kaynak = (
            'standard pipe size whose resulting line velocity is closest to '
            f'the {FEED_LINE_TARGET_VELOCITY_MS:g} m/s design target WITHIN '
            f'the recommended {FEED_LINE_MIN_VELOCITY_MS:g}-'
            f'{FEED_LINE_MAX_VELOCITY_MS:g} m/s band (HRMA low-velocity line '
            'preference; this band is NOT in NASA SP-125). The unrounded '
            'area-target diameter '
            '(A = mdot/(rho x v_target)) is '
            f'{diameter * 1000.0:.2f} mm; the standard ladder is '
            + '/'.join(f'{d * 1000:g}' for d in sizes) + ' mm')
        if n_kol > 1:
            kaynak += (
                f'. The flow is carried by {n_kol} PARALLEL lines: no single '
                'ladder size lands inside the band at this flow rate, and '
                f'{n_kol} is the smallest leg count that does (search cap '
                f'FEED_LINE_MAX_PARALLEL = {FEED_LINE_MAX_PARALLEL}, a design '
                'choice, not a measured limit). Each leg carries '
                f'{mass_flow_rate / n_kol:.4f} kg/s; the quoted diameter, '
                'velocity and pressure drop are PER LEG - parallel legs share '
                'the same pressure drop')
        if durum == 'above':
            kaynak += (' - NO ladder size lands inside the band at this flow '
                       'rate; the closest one still exceeds the ceiling '
                       '(declared, see warnings)')
        elif durum == 'below':
            kaynak += (' - NO ladder size lands inside the band at this flow '
                       'rate; the closest one falls below the floor '
                       '(declared, see warnings)')
        return {
            'diameter_m': float(secim),
            'velocity_m_s': float(v_son),
            'raw_diameter_m': float(diameter),
            'band_status': durum,
            'n_parallel_lines': int(n_kol),
            'per_line_mass_flow_kg_s': float(mass_flow_rate) / float(n_kol),
            'source': kaynak,
        }

    def _line_leg_declaration(self, mass_flow_rate, propellant_type):
        """Hat kolu beyanı — çapın KOL BAŞINA olduğu sayının yanında durur."""
        secim = self._line_diameter_selection(mass_flow_rate, propellant_type)
        n = int(secim.get('n_parallel_lines', 1) or 1)
        return {
            'n_parallel_lines': n,
            'per_line_mass_flow_kg_s': float(secim['per_line_mass_flow_kg_s']),
            'diameter_basis': (
                'inner diameter PER LEG; this circuit is carried by '
                f'{n} parallel line(s) (see n_parallel_lines). '
                + str(secim.get('source', ''))),
        }

    def _calculate_line_diameter(self, mass_flow_rate: float, propellant_type: str) -> float:
        """Besleme hattı iç çapı [m] — seçim ``_line_diameter_selection``da."""
        return self._line_diameter_selection(
            mass_flow_rate, propellant_type)['diameter_m']
    
    # ÖH D24 · P3B4/P3B3-14: ``_cycle_pump_flows`` BURADAN KALDIRILDI.
    # ÖLÇÜLDÜ (raw/OH/D24/sivi/a1/once.json, P3B3-14; taban 88a29d3): tanımı
    # vardı, çağrısı hiçbir yerde yoktu (sıvı motorda 0, deponun geri
    # kalanında 0). Yaptığı iş ``_cycle_pump_duty``nin dört değerinden ilk
    # ikisini döndürmekti; ikinci bir "pompa debisi" adı, aynı büyüklüğün
    # ikinci bir kapısı demektir ve bu depo tam olarak onu kovalıyor.
    # İhtiyaç olursa çağıran ``_cycle_pump_duty()[:2]`` yazar.

    def _cycle_pump_duty(self):
        """(ṁ_ox, ṁ_yakıt, P_ox_kW, P_yakıt_kW) — çevrim çözümünden.

        Güç değerleri çevrim güç dengesinin mil başına kapanışıdır; çok
        kademeli (ana + boost) mimariyi de içerdiği için tek kademe
        varsayımıyla hesaplanan değerden farklı olabilir. Çevrim kapanmadıysa
        None döner ve pompa kendi tek kademeli zinciriyle boyutlandırılır.
        """
        if getattr(self, 'feed_system_type', 'turbopump') != 'turbopump':
            return None
        cyc = self._solve_cycle_balance()
        if not cyc or cyc.get('status') != 'converged':
            return None
        mdot = {'oxidizer': 0.0, 'fuel': 0.0}
        power = {'oxidizer': 0.0, 'fuel': 0.0}
        found = False
        for shaft in (cyc.get('shafts') or []):
            for pump in (shaft.get('pumps') or []):
                key = str(pump.get('propellant', '')).lower()
                if key in mdot and pump.get('mdot_kg_s'):
                    mdot[key] += float(pump['mdot_kg_s'])
                    power[key] += float(pump.get('power_W') or 0.0) / 1000.0
                    found = True
        if not found or mdot['oxidizer'] <= 0 or mdot['fuel'] <= 0:
            return None
        return (mdot['oxidizer'], mdot['fuel'],
                power['oxidizer'] or None, power['fuel'] or None)

    def _design_turbopump_system(self, mdot_ox: float, mdot_fuel: float) -> Dict:
        """Turbopompa alt sistemi — ayrıntılı analizle TEK kaynak.

        2026-07-19 denetimi: burada çark çapı 0.15/0.12 m, devir 25000 rpm,
        türbin giriş sıcaklığı 1100 K ve toplam kütle 45 kg sabitti; aynı
        sonuçta _analyze_detailed_feed_system farklı sayılar veriyordu. Artık
        ikisi de aynı `_design_pump` zincirini kullanır.
        """
        drops = self._calculate_feed_system_pressure_drops()
        pressure_fed = getattr(self, 'engine_cycle', '') == 'pressure_fed'
        # A11: tank basıncı TEK tanım noktasından (bkz. _tank_pressure_bar).
        tank_bar, _ = self._tank_pressure_bar()
        # Y4: pompaların GERÇEKTEN bastığı debi ve mil gücü çevrim
        # çözümünden gelir (gaz jeneratörü / ön yakıcı payı dahil). Ana oda
        # debisiyle boyutlandırmak çevrim güç dengesinden farklı bir pompa
        # gücü üretiyordu (64.5 kW vs 64.96 kW).
        duty = self._cycle_pump_duty()
        p_ox_kw = p_fuel_kw = None
        if duty is not None:
            mdot_ox, mdot_fuel, p_ox_kw, p_fuel_kw = duty
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
        # ÖH A2 sivi-sogutma · F-20: besleme bütçesi enjektör kalemini
        # çözemediyse (basma basıncı None) ve çevrim çözümü de basma
        # basıncını vermiyorsa pompalar BOYUTLANDIRILMAZ — alt sınır basınçla
        # pompa tasarlanmaz (fail-closed).
        if disch_ox is None or disch_fuel is None:
            return {
                'status': 'not_computed',
                'reason': (
                    'the pump discharge pressure is not available: the feed '
                    'budget could not compute its injector item '
                    '(feed_system.pressure_drops.injector_drop_status = '
                    "'not_computed') and the cycle balance published no "
                    'discharge pressure, so no pump or turbine is sized'),
                'oxidizer_pump': None,
                'fuel_pump': None,
                'turbine': None,
            }
        ox = self._design_pump(mdot_ox, self.rho_ox, disch_ox, tank_bar,
                               shaft_power_kw=p_ox_kw,
                               propellant=self.oxidizer_type, role='oxidizer',
                               line=drops['oxidizer_line'])
        fuel = self._design_pump(mdot_fuel, self.rho_fuel, disch_fuel,
                                 tank_bar, shaft_power_kw=p_fuel_kw,
                                 propellant=self.fuel_type, role='fuel',
                                 line=drops['fuel_line'])
        total_pump_power = (ox['design_power'] + fuel['design_power']) * 1000.0
        eta_turbine = TURBINE_EFFICIENCY_DEFAULT
        # F5-3 (bebek-Scofield, 2026-08-17): türbin MİL gücü = pompa mil gücü
        # (kararlı halde mil dengesi; çevrim çözücüsü de tam bu özdeşliği
        # kapatır — _feed_performance_margins docstring'i: "türbin gücü ≡
        # pompa gücü"). Eski satır ``total_pump_power / eta_turbine`` mil
        # gücünü türbin verimine BÖLÜYORDU; verim gaz tarafı boyutlandırmasına
        # aittir (ṁ_türbin = P_mil/(η·Δh)), mil gücüne değil. Ölçülen: aynı
        # yanıtta kullanıcıya 169,55 kW (=110,21/0,65) gösterilirken çevrim
        # kapanışı 110,21 kW diyordu. Bekçi: tests/test_scofield_sivi.py.
        turbine_shaft_power = total_pump_power  # W (mil dengesi)
        turbine_inlet_temp = float(getattr(self, 'turbine_inlet_temp',
                                           GAS_GENERATOR_TEMP_DEFAULT_K))
        material, mat_key = self._material_record()

        # -------------------------------------------------------------------
        # ÖH defter P3B3-01 / P3B3-02: türbin ve gaz jeneratörü kartları
        # -------------------------------------------------------------------
        # ÖLÇÜLDÜ (250 kN / Pc 150): bu kart (panelin okuduğu kart)
        # gas_generator {MR 1,75; T 1200 K; P 195 bar; flow_fraction 0,05}
        # yayımlarken AYNI yanıttaki çevrim çözümü {MR 0,058; T 900 K;
        # P 215,98 bar; flow_fraction 30,23} diyordu — karışım oranı 30 KAT,
        # sıcaklık 300 K ayrı. Üstelik ``flow_fraction`` alanı iki kartta iki
        # FARKLI BİRİM taşıyordu (burada kesir 0,05 = %5, orada yüzde 30,23):
        # alan adına bakan tüketici 605 kat yanılırdı. Türbinde aynı desen:
        # {T 1200 K; PR 8,5; verim 0,65} ⟷ {T 900 K; PR 1,25; verim 65,0} ve
        # çevrimin GERÇEKTEN kullandığı verim 0,78.
        #
        # Buradaki sayılar TASARIM DEĞİL VARSAYIMDI: MR = 0,7·MR_ana ve
        # T = GAS_GENERATOR_TEMP_DEFAULT_K, ikisi de motorun kendi çözümüyle
        # ilgisiz. Çözüm TEK KAYNAK: çevrim güç dengesi kapandıysa kart ONDAN
        # kurulur (ayrıntılı blokla aynı sayılar, aynı künye); kapanmadıysa
        # sayı UYDURULMAZ — status='not_computed' + gerekçe (fail-closed).
        # Birimler artık alanın YANINDA yazılıdır (*_unit) ve iki kartta da
        # aynıdır: flow_fraction YÜZDE, efficiency KESİR.
        cyc_sol = self._solve_cycle_balance()
        cyc_ok = bool(cyc_sol and cyc_sol.get('status') == 'converged'
                      and cyc_sol.get('shafts'))
        turb0 = ((cyc_sol.get('shafts') or [{}])[0].get('turbine') or {}
                 ) if cyc_ok else {}
        turbine_card_a = {
            'power': turbine_shaft_power / 1000,  # kW (mil dengesi)
            'power_basis': (
                'shaft power balance: turbine shaft power equals the '
                'total pump shaft power (steady state). The turbine '
                'efficiency sizes the GAS consumption '
                '(mdot = P_shaft/(eta x ideal specific work)), it does '
                'not inflate the shaft power. When the cycle power '
                'balance converges this is the same closure it reports '
                '(engine_cycle_solution.turbine_power_total_W).'),
            'rpm': ox['rotational_speed'],
            'material': 'Inconel 713C',
            'efficiency_unit': 'fraction',
        }
        if cyc_ok:
            eta_solved = turb0.get('efficiency')
            turbine_card_a.update({
                'status': 'modelled',
                'efficiency': (float(eta_solved)
                               if isinstance(eta_solved, (int, float))
                               else eta_turbine),
                'inlet_temperature': float(turb0.get('inlet_temp_K',
                                                     turbine_inlet_temp)),
                'pressure_ratio': float(turb0.get(
                    'pressure_ratio',
                    getattr(self, 'turbine_pressure_ratio',
                            TURBINE_PRESSURE_RATIO_DEFAULT))),
                'source': CYCLE_CARD_SOURCE,
            })
        else:
            turbine_card_a.update({
                'status': 'not_computed',
                'efficiency': None,
                'inlet_temperature': None,
                'pressure_ratio': None,
                'source': self._cycle_card_withheld_basis(cyc_sol, 'turbine'),
            })

        gg_card_a = {'flow_fraction_unit': 'percent'}
        pb0 = ((cyc_sol.get('preburners') or [{}])[0]) if cyc_ok else {}
        if cyc_ok and pb0:
            mdot_tot = float(getattr(self, 'mdot_total', 0.0) or 0.0)
            gg_card_a.update({
                'status': 'modelled',
                'mass_flow_rate': pb0.get('mdot_total_kg_s'),
                'mixture_ratio': pb0.get('of_ratio'),
                'chamber_pressure': pb0.get('pressure_bar'),
                'temperature': pb0.get('temperature_K'),
                'flow_fraction': (float(pb0['mdot_total_kg_s'])
                                  / max(mdot_tot, 1e-9) * 100.0
                                  if pb0.get('mdot_total_kg_s') else None),
                'mode': pb0.get('mode'),
                'source': CYCLE_CARD_SOURCE,
            })
        else:
            gg_card_a.update({
                'status': 'not_computed',
                'mass_flow_rate': None, 'mixture_ratio': None,
                'chamber_pressure': None, 'temperature': None,
                'flow_fraction': None,
                'source': self._cycle_card_withheld_basis(
                    cyc_sol, 'gas generator / preburner'),
            })

        # ÖH defter P3B3-03: bu kart (feed_system.turbopump) panelin OKUDUĞU
        # karttır (49 gönderme); ayrıntılı blok 5 gönderme alır. Ölçüldü:
        # gerçekleşemezliği söyleyen alanlar (npsh_available, speed_source,
        # suction_feasible, status) YALNIZ ayrıntılı blokta duruyordu, masum
        # alan (npsh_required) buraya da taşınıyordu. Aynı pompa için iki
        # blok zıt hüküm veremez: dürüstlük alanları artık AYNI kartta.
        def _pump_karti(blok, material):
            return {
                'flow_rate': blok['design_flow_rate'],  # kg/s
                'head': blok['design_head'],  # m
                'power': blok['design_power'],  # kW
                'efficiency': blok['design_efficiency'] / 100.0,
                'efficiency_unit': 'fraction',
                'impeller_diameter': blok['impeller_diameter'],  # m
                'impeller_tip_speed': blok['impeller_tip_speed'],  # m/s
                'impeller_geometry_status': blok['impeller_geometry_status'],
                'impeller_geometry_basis': blok['impeller_geometry_basis'],
                'rpm': blok['rotational_speed'],
                'speed_source': blok['speed_source'],
                'npsh_required': blok['npsh_required'],  # m
                'npsh_available': blok['npsh_available'],  # m
                'npsh_available_basis': blok['npsh_available_basis'],
                'suction_feasible': blok['suction_feasible'],
                'status': blok['status'],
                'status_basis': blok['status_basis'],
                'material': material,
            }

        ox_card = _pump_karti(ox, 'Inconel 718')
        ox_card['head_rise'] = ox['design_head']  # m (geriye uyum anahtarı)
        fuel_card = _pump_karti(fuel, 'Stainless Steel 316L')
        fuel_card['fuel_head_rise'] = fuel['design_head']  # m (geriye uyum)

        return {
            'type': f"{getattr(self, 'engine_cycle', 'gas_generator')}_cycle",
            'oxidizer_pump': ox_card,
            'fuel_pump': fuel_card,
            'turbine': turbine_card_a,
            # B5 (v2.6.27): pompa devirleri ayrı emme sınırlarından gelir;
            # farklıysa bu bir dişli/çift-mil varsayımıdır ve BEYAN edilir.
            'shaft_architecture_note': self._shaft_architecture_note(ox, fuel),
            'gas_generator': gg_card_a,
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
        # ÖH D31 · OH-D25-25: dump soğutmada bu alan None'dur
        # (ceket debisi modellenmedi); n_channels de 0 gelir,
        # yani zincir yukarıda zaten kesilir. Yine de sayısal
        # zincire None sızmasın.
        coolant_flow = cooling.get('coolant_flow_rate') or 0.0
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

    # ÖH D24 · P3B3-14: sıvı motorun ``_calculate_heat_flux``ı BURADAN
    # KALDIRILDI. ÖLÇÜLDÜ (raw/OH/D24/sivi/a1/once.json, P3B3-14; taban
    # 88a29d3): tanımı vardı, sıvı motorda çağrısı 0'dı (dosya dışındaki iki
    # çağrı KATI motorun kendi metodunadır, aynı ad farklı sınıf). İki kusuru
    # birden taşıyordu: (a) tepe akı için ``cooling['peak_heat_flux']``ın
    # yanında İKİNCİ bir kapı açıyor ve o kapı tüm soğutma zincirini
    # yeniden koşuyordu; (b) hesap düşerse ``0.0`` DÖNDÜRÜYORDU — yorumu
    # "UYDURMA değer döndürülmez" dese de sıfır akı bir sayıdır ve tüketici
    # onu ölçüm sanır (fail-closed ihlali). Akıyı isteyen
    # ``calculate_cooling_requirements()['peak_heat_flux']`` (kW/m²) okur.

    @staticmethod
    def _haaland_friction(reynolds, relative_roughness):
        """Haaland (1983) açık sürtünme katsayısı; laminerde 64/Re."""
        re = max(float(reynolds), 1.0)
        if re < 2300.0:
            return 64.0 / re
        return (-1.8 * np.log10(6.9 / re
                                + (relative_roughness / 3.7) ** 1.11)) ** -2

    def _line_pressure_drops(self, mdot, density, viscosity, injector_dp_bar,
                             prop_kind):
        """Tek besleme hattının kalem kalem basınç düşümü [bar].

        Darcy-Weisbach (White, "Fluid Mechanics" 7th ed., Eq. 6.10) + yerel
        kayıp katsayıları (Crane TP-410). Eskiden bu kalemler tamamen sabitti
        (0.1 / 0.5 / 0.3 / 1.2 / 3.0 bar) ve debi, çap, yoğunluk, viskozite
        hiç girmiyordu (2026-07-19 denetimi).

        ÖH defter **P3B3-09** (D18): ``prop_kind`` eskiden burada
        ``'oxidizer' if density > 900 else 'fuel'`` ile TAHMİN ediliyordu.
        Çağıran (``_calculate_feed_system_pressure_drops``) hangi hattı
        hesapladığını ZATEN biliyor; tahmin, yoğunluğu 900'ün üstünde olan
        bir YAKITTA (hidrazin/MMH sınıfı, form bandı 20-2500 kg/m³) yakıt
        hattını 'oksitleyici' sayıyor ve ``_line_diameter_selection``
        içindeki ``_propellant_density('oxidizer')`` çağrısı çapı
        OKSİTLEYİCİ yoğunluğuyla seçiyordu: seçim ve yayımlanan hız iki
        farklı yoğunluktan geliyor, hız bandı hükmü yanlış akışkana ait
        oluyordu. Cins artık argümandır — tahmin edilmez.
        """
        prop_kind = str(prop_kind)
        if prop_kind not in ('oxidizer', 'fuel'):
            raise ValueError(
                "prop_kind must be 'oxidizer' or 'fuel' (got "
                f"{prop_kind!r}): the feed line's propellant side is a "
                'caller fact, it is not inferred from density')
        secim = self._line_diameter_selection(mdot, prop_kind)
        d_line = secim['diameter_m']
        # OH-D18-03: paralel kollarda hız/Re KOL BAŞINA debiden kurulur;
        # basınç düşümü paralel kolların ortak düşümüdür (n ile bölünmez ve
        # n ile çarpılmaz). n = 1'de bu ifade eski davranışın aynısıdır.
        n_kol = int(secim.get('n_parallel_lines', 1) or 1)
        mdot_kol = float(mdot) / float(n_kol)
        area = np.pi * d_line ** 2 / 4.0
        velocity = mdot_kol / max(density * area, 1e-9)
        dyn = 0.5 * density * velocity ** 2  # Pa (dinamik basınç)
        re = density * velocity * d_line / max(viscosity, 1e-9)
        f = self._haaland_friction(re, FEED_LINE_ROUGHNESS_M / d_line)

        # P3B3-04: band ihlali SESSİZ kalmaz. Eskiden yayımlanan sözlükte hız
        # vardı ama bandı yoktu; ölçüldü, hiçbir warn.* kodu hızla ilgili
        # değildi. Uyarı hangi hatta, hangi hızda, hangi banda karşı olduğunu
        # söyler; kod tek, taraf parametrede.
        if secim['band_status'] != 'within':
            self._warn('warn.liquid.feed_line_velocity_out_of_band',
                       'warning', line=prop_kind,
                       velocity_ms=round(float(velocity), 2),
                       lo_ms=FEED_LINE_MIN_VELOCITY_MS,
                       hi_ms=FEED_LINE_MAX_VELOCITY_MS,
                       diameter_mm=round(d_line * 1000.0, 1))

        line_dp = f * (FEED_LINE_LENGTH_DEFAULT_M / d_line) * dyn
        elbow_dp = FEED_ELBOW_COUNT * FEED_K_ELBOW * dyn
        return {
            'tank_outlet': FEED_K_TANK_OUTLET * dyn / PA_PER_BAR,
            'main_valve': FEED_K_MAIN_VALVE * dyn / PA_PER_BAR,
            'filters': FEED_K_FILTER * dyn / PA_PER_BAR,
            'feed_lines': (line_dp + elbow_dp) / PA_PER_BAR,
            # ÖH A2 sivi-sogutma · F-20 (OH-FB-02): enjektör kalemi
            # çözülemediyse None kalır (eskiden 0,0 "sıfır beyanı").
            'injector': (None if injector_dp_bar is None
                         else float(injector_dp_bar)),
            'line_diameter_mm': d_line * 1000.0,
            # P3B3-09: çapın hangi akışkan için seçildiği artık sayının
            # yanında durur; tüketici (tank iç yapısı, valve_feedline) iki
            # tanım noktasının aynı tarafa baktığını okuyarak doğrulayabilir.
            'line_propellant_side': prop_kind,
            # OH-D18-03: kol sayısı ve kol başına debi sayının yanında durur.
            'n_parallel_lines': n_kol,
            'per_line_mass_flow_kg_s': mdot_kol,
            'total_mass_flow_kg_s': float(mdot),
            'line_diameter_source': secim['source'],
            'line_velocity_m_s': velocity,
            # P3B3-04: hız yayımlanıyordu, BANDI yayımlanmıyordu — tüketici
            # sayının kabul edilebilir olup olmadığını bilemiyordu.
            'line_velocity_band_m_s': [FEED_LINE_MIN_VELOCITY_MS,
                                       FEED_LINE_MAX_VELOCITY_MS],
            'line_velocity_band_status': secim['band_status'],
            'line_reynolds': re,
            'friction_factor': f,
        }

    def _calculate_feed_system_pressure_drops(self) -> Dict:
        """Besleme hattı basınç düşümleri — GERÇEK akış hesabı.

        Enjektör kalemi ``calculate_injector_design()`` sonucundan gelir
        (tek doğruluk kaynağı): eskiden burada 3.0 bar yazarken enjektör
        modülü aynı motor için 22 bar hesaplıyordu.
        """
        # ÖH D25 · OH-D24-13 (P3B1-12 kalıntısı): buradaki genel yakalayıcı
        # enjektör KAPI hatalarını da yutuyordu. ÖLÇÜLDÜ (once.json
        # OH-D24-13; 25 kN / 60 bar, injector_type='banana'): enjektör kalemi
        # 13,2 bar iken sessizce 0,0 bara düşüyor, oksitleyici hattının
        # toplamı 15,7314 → 2,5314 bara iniyordu. O toplam pompa BASMA
        # basıncını sürer (``pump_discharge_pressure_ox``), yani tanınmayan
        # tipte pompa 13,2 bar eksik boyutlanmış olarak "hesaplandı" diye
        # yayımlanıyordu; ne hata ne künye vardı.
        #
        # Kapı hataları (tip / itici çifti / yoğunluk çözülemedi) bir "modül
        # kullanılamadı" durumu DEĞİLDİR — onlar zaten fail-closed hükmüdür,
        # yutulmaz, yükselir (D19 P3B1-12'de aynı desen enjektör modülünde
        # kuruldu). Kapı dışı bir arızada da sayı uydurulmaz: kalem sıfır
        # kalır ama SIFIR OLDUĞU ve NEDENİ kartta yazar.
        inj_dp_basis = (
            'computed: the injector item of this budget is the pressure drop '
            'the injector design chain solved for THIS engine '
            '(calculate_injector_design, single source), not an assumed '
            'allowance')
        try:
            if not hasattr(self, 'mdot_fuel'):
                self.calculate_nozzle_geometry()  # kütle dengesi + geometri
            injector = self.calculate_injector_design()
            dp_inj_ox = injector['ox_pressure_drop']
            dp_inj_fuel = injector['fuel_pressure_drop']
            inj_dp_resolved = True
        except (UnsupportedInjectorTypeError, UnsupportedPropellantPairError,
                UnsupportedPropellantDensityError):
            raise
        except Exception as exc:
            # ÖH A2 sivi-sogutma · F-20 (OH-FB-02, Berke onayı bekler —
            # ÖNEMLİ: arıza yolunda yayımlanan sayı değişir). ÖLÇÜLDÜ
            # (a1/once/ariza.json; 10 kN / 100 bar RP-1/LOX, arıza YALNIZ bu
            # bütçenin enjektör çağrısında): HTTP 200, enjektör kalemi
            # 20,0 -> 0,0 bar, pump_discharge_pressure_ox 122,277 -> 102,277
            # bar; basınç beslemede required_pump_discharge_bar da 102,277
            # (alt sınır tasarım değeri gibi yayımlanıyordu). Kalem artık
            # 0,0 DEĞİL None; onu içeren her toplam da None (fail-closed).
            dp_inj_ox = dp_inj_fuel = None
            inj_dp_resolved = False
            inj_dp_basis = (
                'not_computed: the injector design chain failed with '
                f'{type(exc).__name__} ({str(exc)[:160]}), so the injector '
                'item of this feed budget is NOT published (None), and '
                'neither is any total that contains it: total_ox, '
                'total_fuel, pump_discharge_pressure_ox, '
                'pump_discharge_pressure_fuel, oxidizer_line.injector, '
                'fuel_line.injector. No zero or lower-bound value is '
                'substituted.')

        mdot_ox = getattr(self, 'mdot_ox', None)
        mdot_fuel = getattr(self, 'mdot_fuel', None)
        if mdot_ox is None or mdot_fuel is None:
            mdot_total = self.F / (getattr(self, 'isp_sl', 300.0) * self.g0)
            mdot_ox = mdot_total * self.MR / (1 + self.MR)
            mdot_fuel = mdot_total / (1 + self.MR)

        # Viskozite: kullanıcı girdisi > tablo tabanı. Taban değerler TEK
        # tanım yerinden gelir (FEED_VISCOSITY_FALLBACK_PA_S); C2 vana/hat
        # bütçesi de aynı sözlüğü okur, iki hat hesabı ayrışamaz.
        mu_ox = (getattr(self, 'mu_ox', None)
                 or FEED_VISCOSITY_FALLBACK_PA_S['oxidizer'])
        mu_fuel = (getattr(self, 'mu_fuel', None)
                   or FEED_VISCOSITY_FALLBACK_PA_S['fuel'])

        ox = self._line_pressure_drops(mdot_ox, self.rho_ox, mu_ox, dp_inj_ox,
                                       'oxidizer')
        fuel = self._line_pressure_drops(mdot_fuel, self.rho_fuel, mu_fuel,
                                         dp_inj_fuel, 'fuel')
        keys = ('tank_outlet', 'main_valve', 'filters', 'feed_lines', 'injector')
        # F-20: enjektör kalemi yoksa toplam da YOK (kısmi toplam alt sınırdır,
        # tasarım değeri gibi yayımlanmaz).
        total_ox = (sum(ox[k] for k in keys) if inj_dp_resolved else None)
        total_fuel = (sum(fuel[k] for k in keys) if inj_dp_resolved
                      else None)

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
            'pump_discharge_pressure_ox': (None if total_ox is None
                                           else self.P_c + total_ox),
            'pump_discharge_pressure_fuel': (None if total_fuel is None
                                             else self.P_c + total_fuel),
            'method': ('Darcy-Weisbach with Haaland friction factor plus '
                       'local loss coefficients (Crane TP-410); the injector '
                       'item is taken from the injector design'),
            # ÖH D25 · OH-D24-13: enjektör kalemi çözülemediyse SUSMAZ;
            # metin 'computed:' ile mi 'not_modelled:' ile mi başlıyor,
            # kalemin gerçekten hesaplanıp hesaplanmadığını o söyler.
            'injector_drop_basis': inj_dp_basis,
            # --- ÖH D33-2 · OH-FB-02 (Fable sivi-03) ----------------------
            # ÖLÇÜLDÜ (once.json OH-FB-02; 10 kN / 30 bar RP1-LOX, enjektör
            # zincirine KAPI DIŞI RuntimeError enjekte edildi): enjektör
            # kalemi 6,6000 -> 0,0000 bar, total_ox 8,4738 -> 1,8738 bar,
            # pump_discharge_pressure_ox 38,4738 -> 31,8738 bar (-%17,2) ve
            # HİÇBİR makine okunur alan bunu söylemiyordu: tek işaret
            # ``injector_drop_basis`` metninin 'not_modelled:' ile başlaması,
            # yani tüketicinin İNGİLİZCE CÜMLE AYRIŞTIRMASIydı. Artık kapı
            # ADIYLA yayımlanır; aşağıdaki sayılara bakan her tüketici
            # (pompa boyutlandırma, su koçu, vana/hat bütçesi, marjlar) bu
            # bayraklardan fail-closed davranabilir.
            #
            # KISMİ ONARIM BEYANI: Fable'ın önerdiği tam fail-closed biçim
            # (kalem ve toplamlar None + pompa boyutlandırması
            # 'not_computed') bu sayıları aritmetiğe sokan YEDİ tüketiciyi
            # birden kapılamayı gerektirir (_analyze_detailed_feed_system,
            # _feed_water_hammer_analysis, _valve_feedline_block,
            # turbopompa bloğu, basınç-beslemeli tank kapısı,
            # required_pump_discharge_bar, performance_margins). Bu dalgada
            # yapılan, sayının SESSİZ kalmasını bitirmektir; None'a çevirme
            # kendi dalgasında yapılır.
            #
            # ÖH A2 sivi-sogutma · F-20: yukarıdaki "kısmi onarım" TAMAMLANDI.
            # Kalem ve toplamlar artık None; alt sınır YAYIMLANMADIĞI için
            # 'feed_budget_is_lower_bound' arıza yolunda da False'tur (listede
            # alt sınır olan alan yok). Yedi tüketici None'a karşı kapılandı:
            # _analyze_detailed_feed_system (basınç-beslemeli tank kapısı,
            # su koçu, vana/hat bütçesi, required_pump_discharge_bar,
            # performance_margins — çevrim çözümü basma basıncını vermiyorsa
            # blok 'not_computed' döner) ve turbopompa bloğu
            # (_design_turbopump_system + güç özeti). Normal yolda anahtar
            # kümesi ve değerler BİT-AYNI (bekçi: tests/test_d37_sivi_a1.py).
            'injector_drop_status': ('computed' if inj_dp_resolved
                                     else 'not_computed'),
            'feed_budget_is_lower_bound': False,
            'feed_budget_lower_bound_fields': None,
            # V3 taban-a (14 Eki): gerekçe alanı İKİ durumda da düzyazıdır.
            # Kapı açıkken (enjektör kalemi hesaplandı) ``None`` yayımlanıyordu
            # — beyan ailesinde içi boş bir ``*_basis`` (bekçi
            # tests/test_liquid_declarations_v2626.py::test_beyan_metinleri_bos_degil,
            # ilk kırmızı ba69fa6f). Birleşme (sıvı 6. tur): F-20 ile arıza
            # yolunda alt sınır YAYIMLANMAZ (alanlar None, bayrak False);
            # gerekçe artık kapının neden kapalı olduğunu da söyler.
            'feed_budget_lower_bound_basis': (
                'MACHINE-READABLE GATE: the injector item was computed on '
                'this run (injector_drop_status = computed), so the feed '
                'budget fields are design values, not lower bounds, and '
                'feed_budget_lower_bound_fields is null.'
                if inj_dp_resolved else (
                    'MACHINE-READABLE GATE: the injector item could not be '
                    'computed on this run (injector_drop_status = '
                    "'not_computed'). The fields injector, total_ox, "
                    'total_fuel, pump_discharge_pressure_ox, '
                    'pump_discharge_pressure_fuel, oxidizer_line.injector '
                    'and fuel_line.injector are None: nothing in this budget '
                    'is a lower bound, the missing items are simply not '
                    'published.')),
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
        regen_dp_basis = None
        if self.cooling_type in ('regenerative', 'dump_cooling'):
            # 5. tur DEVİR (önceki denetimin 'except Exception: pass'
            # bulgusu): soğutma çözümünün HER hatası burada yutuluyor ve
            # çevrim ceket ΔP'si 0 bar ile SESSİZCE kapanıyordu (ölçüldü:
            # dump soğutmada cooling_pressure_drop None → float(None)
            # TypeError → ΔP 0, ısı yükü None; yanıtta beyan yok). Artık
            # hata fail-closed (çevrim çözülmez, neden adıyla) ve dump
            # ceketinin modellenmemiş ΔP'si sayıyla DEĞİL beyanla taşınır.
            try:
                cooling = self.calculate_cooling_requirements()
            except Exception as exc:
                out['reason'] = (
                    'cooling solution failed '
                    f'({type(exc).__name__}: {exc}); the regenerative jacket '
                    'pressure drop sits in series in the fuel pump discharge, '
                    'so the cycle power balance is not solved')
                self._cycle_result = out
                return out
            # Denetçi Ş4 (4. tur): ceket ΔP'si hesaplanmadıysa çevrim
            # dengesi ΔP'yi 0 sayıp kapanmaz — çözülmez, nedeni yazılır.
            if cooling.get('jacket_hydraulics_status') == 'not_computed':
                out['reason'] = (
                    'regenerative jacket pressure drop not computed '
                    "(cooling_system.jacket_hydraulics_status = "
                    "'not_computed': HRMA could not fit its minimum "
                    'channel count in this throat); the fuel pump '
                    'discharge pressure contains that drop in series, so '
                    'the cycle power balance is not solved')
                self._cycle_result = out
                return out
            _dp = cooling.get('cooling_pressure_drop')
            if _dp is None and (cooling.get('dump_cooling_jacket_status')
                                == 'NOT_MODELLED'):
                # Sayılar eskisiyle BİT-AYNI (ΔP 0, ısı yükü yok); fark
                # yalnız beyan: dengeye girmeyen terim adıyla yazılır.
                regen_dp_basis = (
                    'dump-cooling jacket NOT_MODELLED '
                    "(cooling_system.dump_cooling_jacket_status): its "
                    'pressure drop and heat load are NOT in this balance '
                    '(0 bar used); if the dump jacket is fed in series from '
                    'the fuel pump, the fuel pump discharge pressure and '
                    'power published here are lower bounds')
            elif _dp is None or not np.isfinite(float(_dp)):
                out['reason'] = (
                    'regenerative jacket pressure drop not available '
                    f'(cooling_system.cooling_pressure_drop = {_dp!r}); the '
                    'fuel pump discharge pressure contains that drop in '
                    'series, so the cycle power balance is not solved')
                self._cycle_result = out
                return out
            else:
                regen_dp_bar = float(_dp)
                _q = cooling.get('total_heat_load', 0.0)
                regen_heat_kw = (float(_q) if _q is not None
                                 and np.isfinite(float(_q)) else None)

        line_ox, line_fuel, _ = self._cycle_line_dps()

        # ÖH defter P3B3-13 (Z5S/PK1): pompa emme basıncı burada
        # PUMP_TANK_PRESSURE_DEFAULT_BAR sabitinden DOĞRUDAN okunuyordu.
        # A11 reformunun kurduğu tek tanım noktası ``_tank_pressure_bar()``
        # olduğu için :5570-5572'deki "çevrim çözücüsü de buradan okur"
        # beyanı YANLIŞTI: tek tanım noktası oynatıldığında besleme kartı
        # 12,0 bara gidiyor, çözücünün pompa girişleri 3,0 barda kalıyordu
        # (ölçüldü, 25 kN gaz jeneratörü). Bugün iki yol aynı sayıyı verdiği
        # için ayrışma görünmüyordu; artık beyan doğrudur.
        # Basınç beslemeli çevrimde çözücü pompa girişini HİÇ kullanmaz
        # (cycle_power_balance.py:592 dalı pompalardan önce döner), o yüzden
        # bu satır orada da sayı kaydırmaz.
        pump_inlet_bar = float(self._tank_pressure_bar()[0])

        kwargs = dict(
            rho_ox=float(self.rho_ox), rho_fuel=float(self.rho_fuel),
            pump_inlet_ox_bar=pump_inlet_bar,
            pump_inlet_fuel_bar=pump_inlet_bar,
            line_dp_ox_bar=line_ox, line_dp_fuel_bar=line_fuel,
            regen_dp_bar=regen_dp_bar,
            injector_dp_frac=self._injector_dp_fraction(),
            eta_pump_ox=float(getattr(self, 'pump_efficiency',
                                      PUMP_EFFICIENCY_DEFAULT)),
            eta_pump_fuel=float(getattr(self, 'pump_efficiency',
                                        PUMP_EFFICIENCY_DEFAULT)),
            # Türbin verimi çevrim SINIFINA göre seçilsin (2026-07-23): sabit
            # 0.65 gaz-jeneratörü (açık çevrim, yüksek PR impuls kademesi)
            # değeridir; staged/FFSC/expander türbinleri düşük PR'de %78+
            # verim alır (NASA SP-8110, RS-25 HPFTP %81). eta_turbine=None
            # verince çözücü çevrim sınıfına göre seçer. Bu satır 0.65
            # zorladığı sürece FFSC güç dengesi yüksek Pc'de KAPANMAZ.
            # Kullanıcı generator_gas_temp/turbine PR girdiyse aşağıda ayrıca
            # geçilir; türbin verimini kullanıcı ayrı override etmiyor.
            eta_turbine=None,
            preburner_mode=getattr(self, 'preburner_mode', 'fuel_rich'),
            regen_heat_kw=regen_heat_kw,
        )
        # TIT ve türbin PR yalnız KULLANICI girdiyse geçilir; girilmediyse
        # çözücünün çevrime özgü KAYNAKLI varsayılanları kullanılır
        # (GAS_GENERATOR_TEMP_DEFAULT_K genel amaçlı eski sabittir, staged
        # ox-rich sınırlarını bilmez).
        # P3B3-05: koşul artık KABUL edilmiş olmaya bakıyor; reddedilen girdi
        # çözücüye hiç ulaşmaz ve yanıt 'alan hiç gönderilmemiş' koşuyla
        # BİT-AYNI olur (savcının önerdiği kapanış ölçütü).
        if getattr(self, 'turbine_inlet_temp_accepted', False):
            kwargs['tit_K'] = float(self.turbine_inlet_temp)
        if getattr(self, 'turbine_pressure_ratio_accepted', False):
            kwargs['turbine_pr'] = float(self.turbine_pressure_ratio)
        elif getattr(self, 'turbine_inlet_pressure_bar', None):
            # v2.6.26: kullanıcı genişleme oranını BOŞ bırakıp giriş basıncı
            # verdiyse alan artık ölü değil — basınç oranı ondan çözülür.
            # Önceliği hâlâ doğrudan girilen genişleme oranı alır; ikisi de
            # verilmişse yukarıdaki dal çalışır ve giriş basıncı yalnız
            # karşılaştırılır (bkz. unwired_inputs).
            p_exhaust, _basis = self._turbine_exhaust_pressure_bar()
            pr_from_inlet = float(self.turbine_inlet_pressure_bar) / p_exhaust
            if pr_from_inlet > 1.05:
                kwargs['turbine_pr'] = pr_from_inlet
                self.turbine_pressure_ratio = pr_from_inlet
        if self.engine_cycle == 'pressure_fed':
            # A11: tank basıncı TEK tanım noktasından (_tank_pressure_bar).
            kwargs['tank_pressure_bar'] = float(self._tank_pressure_bar()[0])
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
        if regen_dp_basis is not None:
            out['regen_jacket_dp_basis'] = regen_dp_basis
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

        F1-1 BEYANI (bebek-Scofield, 2026-08-17): bu yol BİLEREK başlık
        zincirine BAĞLI DEĞİLDİR. Başlık Isp/debi/boğaz sayıları ana oda
        zincirinden gelir ve bu zincirin verim kalibrasyonu, kayıp
        uygulanmadan, 14 gerçek motorun TESLİM verisine karşı doğrulanmıştır
        (tests/test_correlation_guards.py: sıvı isp_vac medAPE %0,93 tabanı).
        Kaybı başlığa işlemek her yayımlanan sayıyı değiştirir ve o
        korelasyon tabanının yeniden doğrulanmasını gerektirir — kendi
        partisinin işidir. Çelişki SESSİZ BIRAKILMAZ: fark, ölçülen kayıpla
        birlikte sonuçta ``cycle_isp_accounting`` bloğunda adıyla yayımlanır
        (_cycle_isp_accounting_block) ve blok bu metodun GERÇEK durumundan
        (_cycle_isp_applied) türediği için yalan söyleyemez. Bu yol bir gün
        bağlanırsa blok applied=True bildirir ve bekçi kimlikleri başlığın
        motor-Isp'sine eşitlenmesini zorlar (tests/test_scofield_sivi.py).
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

    def _cycle_isp_accounting_block(self, cycle_solution):
        """Başlık Isp'si ↔ çevrim çözümü ilişkisinin BEYANI (F1-1).

        Bebek-Scofield ölçümü (2026-08-17): gaz jeneratörü örneğinde başlık
        Isp_sl = 277,449 s iken aynı yanıtın yakınsamış çevrim çözümü motor
        Isp'sini 274,034 s (kayıp 3,415 s, %1,25) raporluyordu ve hangi
        sayının hangi muhasebeden geldiği HİÇBİR yerde yazmıyordu
        (_apply_cycle_accounting ölü koddu). Bu blok çelişkiyi adıyla ve
        ölçülen farkla yayımlar; içeriği motorun GERÇEK durumundan türediği
        için (``_cycle_isp_applied``) beyan davranıştan kopamaz.
        """
        applied = bool(getattr(self, '_cycle_isp_applied', False))
        block = {
            'applied': applied,
            'headline_isp_sl_s': float(self.isp_sl),
            'headline_isp_vac_s': float(self.isp_vac),
        }
        status = (cycle_solution or {}).get('status')
        if status != 'converged':
            block['status'] = 'cycle_solution_unavailable'
            block['headline_isp_basis'] = (
                'main-chamber delivered chain; the cycle power balance did '
                'not converge (or is not modelled) for this run, so there is '
                'no engine-level cycle Isp to reconcile against (see '
                'detailed_feed_system.engine_cycle_solution.status)')
            return block
        block['status'] = 'reconciled'
        isp_mode = cycle_solution.get('isp_mode')
        if isp_mode != 'open_cycle_mixture_average':
            # Kapalı çevrim / basınç beslemeli: türbin debisi ana odaya döner
            # (ya da hiç yoktur); çevrim kaybı tanım gereği sıfırdır.
            block['isp_loss_sl_s'] = 0.0
            block['engine_isp_sl_s'] = float(self.isp_sl)
            block['engine_isp_vac_s'] = float(self.isp_vac)
            block['headline_isp_basis'] = (
                f'closed or pressure-fed cycle ({isp_mode}): no open-cycle '
                'bleed loss exists, the headline Isp IS the engine-level '
                'Isp by construction')
            return block
        engine_sl = cycle_solution.get('isp_engine_sl_s')
        engine_vac = cycle_solution.get('isp_engine_vac_s')
        block.update({
            'engine_isp_sl_s': engine_sl,
            'engine_isp_vac_s': engine_vac,
            'isp_loss_sl_s': cycle_solution.get('isp_loss_sl_s'),
            'isp_loss_vac_s': cycle_solution.get('isp_loss_vac_s'),
            'turbine_bleed_kg_s':
                cycle_solution.get('turbine_mdot_total_kg_s'),
            'main_chamber_isp_sl_s': cycle_solution.get('isp_main_sl_s'),
        })
        if isinstance(engine_sl, (int, float)) and engine_sl > 0:
            block['headline_minus_engine_sl_s'] = (
                float(self.isp_sl) - float(engine_sl))
        if applied:
            block['headline_isp_basis'] = (
                'open-cycle mixture-average accounting APPLIED: the headline '
                'Isp is the engine-level value (main chamber + turbine '
                'exhaust, flow weighted; Sutton Ch. 6) and matches '
                'engine_cycle_solution.isp_engine_sl_s')
        else:
            block['headline_isp_basis'] = (
                'main-chamber delivered chain: the open-cycle turbine bleed '
                'loss reported by the converged cycle solution '
                '(isp_loss_sl_s) is NOT subtracted from the headline '
                'thrust/Isp/mass-flow numbers. The headline chain\'s '
                'efficiency calibration was validated as a whole against '
                'delivered engine data without this subtraction '
                '(tests/test_correlation_guards.py, liquid isp_vac cell); '
                'wiring the loss in changes every downstream number and '
                'requires that validation to be redone. The engine-level '
                'Isp and the measured difference are published here so the '
                'two numbers cannot be silently read as the same quantity.')
        return block

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
            self._warn('warn.liquid.feed_dry_mass_unavailable', 'warning')
            return 0.0
    
    def _design_propellant_tanks(self):
        """Design detailed propellant tank system with internal structures"""
        
        # Mission parameters for tank sizing
        burn_time, burn_time_source = self._burn_time()
        if burn_time is None:
            # ÖH D36 / LU-1: tank kartı yakılan kütleden (debi x süre)
            # boyutlanır; süre yoksa kart YOK — adıyla (fail-closed).
            return {
                'status': 'not_modelled',
                'reason': BURN_TIME_NOT_SUPPLIED_REASON,
                'burn_time_source': burn_time_source,
            }
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
        # v2.6.26: satır içi 2.5 literali yerine TEK tanım yeri olan modül
        # sabiti; oran çıktıda kendi gerekçesiyle yayımlanır.
        ld_ratio = TANK_LD_RATIO

        # Oxidizer tank (larger, typically)
        ox_tank_diameter = (4 * ox_tank_volume / (np.pi * ld_ratio))**(1/3)
        ox_tank_length = ox_tank_diameter * ld_ratio

        # Fuel tank
        fuel_tank_diameter = (4 * fuel_tank_volume / (np.pi * ld_ratio))**(1/3)
        fuel_tank_length = fuel_tank_diameter * ld_ratio
        
        # Tank işletme basıncı — NPSH/besleme zinciriyle AYNI kaynaktan
        # (A11): eskiden burada basınç beslemeli dal için (P_c + 5 bar) çarpı
        # 1.2 türetilmiş tahmini, turbopompa dalı için 3e5 Pa satır içi
        # literali vardı. Aynı yanıtta besleme kartı kullanıcının girdisiyle
        # 105 bar derken bu kart 90 bar diyor; cidar, tank kütlesi, MEOP ve
        # emniyet vanası ayarı o ikinci sayıdan türüyordu.
        tank_pressure_bar_val, tank_pressure_source = self._tank_pressure_bar()
        tank_pressure = tank_pressure_bar_val * PA_PER_BAR  # Pa
        
        # Cidar kalınlığı (ince cidarlı basınçlı kap).
        #
        # v2.6.2 düzeltmesi — malzeme TEK KAYNAKTAN okunuyor:
        # Burada ``material_strength = 350e6  # Al-Li alloy`` ve aşağıda
        # ``material_density = 2700  # aluminum`` satır içi sabitleri vardı.
        # İkisi BİRBİRİYLE ÇELİŞİYORDU: etiket Al-Li diyordu ama 2700 kg/m³
        # saf alüminyumun (6061) yoğunluğu; Al-Li alaşımları ~2540 kg/m³.
        # Ayrıca değerler materials_db'den GELMİYORDU, oysa yapısal, termal ve
        # emniyet modüllerinin hepsi o veritabanını kullanıyor — tank
        # boyutlandırma tek başına kopmuş bir adaydı ve kullanıcıya gösterilen
        # tank kütlesi/kütle oranı bu yüzden LH2 durumunda ~4.3 kat iyimser
        # çıkabiliyordu.
        # Artık dayanım ve yoğunluk AYNI kayıttan okunur, dolayısıyla
        # çelişemezler; malzeme adı da çıktıda raporlanır.
        tank_material = getattr(self, 'tank_material', None) or 'al_2024_t3'
        from hrma.data.materials_db import get_material_safe
        try:
            # get_material_safe -> (kayıt, kanonik_anahtar) çifti döndürür
            _mat, tank_material = get_material_safe(tank_material)
        except KeyError as exc:
            raise ValueError(
                f"Unknown tank material '{tank_material}'. "
                "Tank sizing requires a material present in materials_db; "
                "no generic fallback is applied."
            ) from exc
        material_strength = float(_mat['yield_strength'])   # Pa
        material_density = float(_mat['density'])           # kg/m^3
        # Emniyet katsayısı bir MALZEME ÖZELLİĞİ değil, tasarım kararıdır:
        # çağıran verebilsin diye öznitelik olarak okunur.
        # v2.6.26: 'tank_safety_factor' HİÇBİR YERDE atanmıyordu, dolayısıyla
        # getattr her koşuda 2.5'e düşüyordu: kullanıcı formda 1.6 girse bile
        # tank cidarı, kütlesi ve çıktıdaki 'safety_factor' yaprağı 2.5 ile
        # hesaplanıyordu (sessiz beyan boşluğu). Artık kullanıcının emniyet
        # katsayısı girdisi (self.safety_factor) tank tasarımına da gider;
        # ayrı bir tank katsayısı atayan çağıran varsa önceliği korunur.
        tank_sf_override = getattr(self, 'tank_safety_factor', None)
        if tank_sf_override is not None:
            safety_factor = float(tank_sf_override)
            safety_factor_source = 'caller-supplied tank safety factor'
        else:
            safety_factor = float(getattr(self, 'safety_factor',
                                          SAFETY_FACTOR_DEFAULT))
            # B4 (v2.6.27): künye artık KARARIN verildiği yerden okunur.
            # Eski satır yalnız anahtarın gövdede BULUNMASINA bakıyordu:
            # aralık dışı bir katsayı (ör. 99) gönderildiğinde değer
            # reddedilip 2.5 kullanılıyor ama beyan hâlâ "user input (safety
            # factor)" diyordu — kullanılmayan girdiye sahip çıkan bir künye.
            safety_factor_source = self._safety_factor_source()
        allowable_stress = material_strength / safety_factor

        # Yakıt tankı AYRI malzeme kullanabilir. Kriyojenik hidrojen alüminyum
        # alaşımlarında geçirgenlik/gevrekleşme sorunları çıkardığı için pratikte
        # paslanmaz seçilir; kod bunu ETİKETTE zaten söylüyordu ("Stainless Steel
        # 316L") ama KALINLIK ve KÜTLEYİ alüminyum özellikleriyle hesaplıyordu.
        # v2.6.2: etiket ile hesap aynı kayda bağlandı.
        fuel_tank_material = getattr(self, 'fuel_tank_material', None)
        fuel_material_basis = 'same material as the oxidizer tank'
        if fuel_tank_material is None:
            if self.fuel_type == 'lh2':
                # P3B3-06: eskiden 'steel' (KARBON çelik, A36) seçiliyordu.
                fuel_tank_material = TANK_LH2_MATERIAL_KEY
                fuel_material_basis = TANK_LH2_MATERIAL_BASIS
            else:
                fuel_tank_material = tank_material
        else:
            fuel_material_basis = 'caller-supplied fuel tank material'
        try:
            _fmat, fuel_tank_material = get_material_safe(fuel_tank_material)
        except KeyError as exc:
            raise ValueError(
                f"Unknown fuel tank material '{fuel_tank_material}'."
            ) from exc
        fuel_material_strength = float(_fmat['yield_strength'])
        fuel_material_density = float(_fmat['density'])
        fuel_allowable_stress = fuel_material_strength / safety_factor

        # İnce cidar çember gerilmesi boyutlandırması; basınçtan gelen değer
        # AYRI adla saklanır ki imalat tabanı hükmü sessizce yutmasın (A11).
        ox_wall_pressure_sized = (tank_pressure * ox_tank_diameter/2) / allowable_stress
        fuel_wall_pressure_sized = (tank_pressure * fuel_tank_diameter/2) / fuel_allowable_stress

        # İmalat tabanı — TEK tanım noktası (eskiden iki satır içi 0.003)
        ox_wall_thickness = max(ox_wall_pressure_sized,
                                TANK_WALL_MIN_THICKNESS_M)
        fuel_wall_thickness = max(fuel_wall_pressure_sized,
                                  TANK_WALL_MIN_THICKNESS_M)
        ox_wall_governed_by = ('pressure sizing'
                               if ox_wall_pressure_sized
                               > TANK_WALL_MIN_THICKNESS_M
                               else 'minimum manufacturing gauge')
        fuel_wall_governed_by = ('pressure sizing'
                                 if fuel_wall_pressure_sized
                                 > TANK_WALL_MIN_THICKNESS_M
                                 else 'minimum manufacturing gauge')
        
        # Internal structures design — ağız çapları ve iç yapı kütleleri artık
        # DEBİDEN ve GEOMETRİDEN hesaplanıyor; tank basıncı emniyet vanası
        # boyutlandırması için geçiliyor.
        ox_tank_internals = self._design_tank_internals(
            ox_tank_diameter, ox_tank_length, 'oxidizer',
            tank_pressure, mdot_ox)
        fuel_tank_internals = self._design_tank_internals(
            fuel_tank_diameter, fuel_tank_length, 'fuel',
            tank_pressure, mdot_fuel)
        
        # --- A2 (v2.6.27): çalkantı analizi — tankın KENDİ geometrisiyle ---
        # Sıvı yüksekliği rezerv dahil sıvı hacminden (ullage hariç):
        # h = V_sıvı / (pi R^2). Bafl geometrisi iç yapı listesinden okunur.
        ox_fill_height = ox_volume_req / (np.pi * (ox_tank_diameter / 2) ** 2)
        fuel_fill_height = fuel_volume_req / (np.pi
                                              * (fuel_tank_diameter / 2) ** 2)
        ox_slosh = self._tank_slosh_analysis(
            'oxidizer', ox_tank_diameter / 2, ox_fill_height,
            rho_ox, rho_ox_source, ox_tank_internals)
        fuel_slosh = self._tank_slosh_analysis(
            'fuel', fuel_tank_diameter / 2, fuel_fill_height,
            rho_fuel, rho_fuel_source, fuel_tank_internals)

        # --- A3 (v2.6.27): basınçlı kap analizi — tank kartıyla AYNI girdi --
        ox_vessel = self._tank_pressure_vessel_analysis(
            'oxidizer_tank', tank_pressure, ox_tank_diameter,
            ox_wall_thickness, tank_material)
        fuel_vessel = self._tank_pressure_vessel_analysis(
            'fuel_tank', tank_pressure, fuel_tank_diameter,
            fuel_wall_thickness, fuel_tank_material)

        # Tank mass estimation
        ox_tank_surface_area = np.pi * ox_tank_diameter * ox_tank_length + 2 * np.pi * (ox_tank_diameter/2)**2
        fuel_tank_surface_area = np.pi * fuel_tank_diameter * fuel_tank_length + 2 * np.pi * (fuel_tank_diameter/2)**2
        
        # material_density yukarıda materials_db kaydından okundu — burada
        # SATIR İÇİ 2700 kg/m³ yazılıydı ve dayanım değeriyle çelişiyordu
        # (etiket Al-Li, yoğunluk saf alüminyum). Yeniden atama yapılmaz;
        # tek kaynak korunur.
        ox_tank_mass = ox_tank_surface_area * ox_wall_thickness * material_density
        fuel_tank_mass = fuel_tank_surface_area * fuel_wall_thickness * fuel_material_density
        
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
                    'wall_thickness_pressure_sized_mm':
                        ox_wall_pressure_sized * 1000,
                    'wall_thickness_governed_by': ox_wall_governed_by,
                    'wall_thickness_basis': TANK_WALL_THICKNESS_BASIS,
                    'ld_ratio': ld_ratio,
                    'ld_ratio_basis': TANK_LD_RATIO_BASIS
                },
                'propellant_data': {
                    'mass': ox_mass,  # kg (rezerv DAHİL — bkz. mass_basis)
                    'mass_nominal': ox_mass_nominal,  # kg (yanan nominal)
                    'mass_basis': TANK_LOADED_MASS_BASIS,
                    'density': rho_ox,  # kg/m³
                    'density_source': rho_ox_source,
                    'volume_required': ox_volume_req * 1000,  # liters
                    'ullage_volume': (ox_tank_volume - ox_volume_req) * 1000,  # liters
                    'ullage_fraction_basis': TANK_ULLAGE_BASIS,
                },
                'structural': {
                    # Etiket, dayanım ve yoğunluk AYNI materials_db kaydından.
                    # Eskiden buraya sabit 'Aluminum-Lithium 2195' yazılıyordu
                    # ama hesap 350 MPa / 2700 kg/m³ kullanıyordu — Al-Li 2195'in
                    # akma dayanımı ~560 MPa'dır, yani etiket ile sayı tutmuyordu.
                    'material': _mat.get('name', tank_material),
                    'material_key': tank_material,
                    'cryogenic_suitability': self._tank_cryo_screening(
                        tank_material, self.oxidizer_type, 'oxidizer'),
                    'yield_strength_mpa': material_strength / 1e6,
                    'density_kg_m3': material_density,
                    'pressure_rating': tank_pressure / 1e5,  # bar
                    'pressure_rating_source': tank_pressure_source,
                    'safety_factor': safety_factor,
                    'safety_factor_source': safety_factor_source,
                    'tank_mass': ox_tank_mass,  # kg
                    'mass_fraction': ox_tank_mass / ox_mass  # tank mass / propellant mass
                },
                'internal_structures': ox_tank_internals,
                # A2/A3 (v2.6.27): çalkantı + basınçlı kap bağlamaları.
                'slosh': ox_slosh,
                'pressure_vessel': ox_vessel,
            },
            'fuel_tank': {
                'propellant_type': self.fuel_type.upper(),
                'dimensions': {
                    'diameter': fuel_tank_diameter * 1000,  # mm
                    'length': fuel_tank_length * 1000,  # mm
                    'volume': fuel_tank_volume * 1000,  # liters
                    'wall_thickness': fuel_wall_thickness * 1000,  # mm
                    'wall_thickness_pressure_sized_mm':
                        fuel_wall_pressure_sized * 1000,
                    'wall_thickness_governed_by': fuel_wall_governed_by,
                    'wall_thickness_basis': TANK_WALL_THICKNESS_BASIS,
                    'ld_ratio': ld_ratio,
                    'ld_ratio_basis': TANK_LD_RATIO_BASIS
                },
                'propellant_data': {
                    'mass': fuel_mass,  # kg (rezerv DAHİL — bkz. mass_basis)
                    'mass_nominal': fuel_mass_nominal,  # kg (yanan nominal)
                    'mass_basis': TANK_LOADED_MASS_BASIS,
                    'density': rho_fuel,  # kg/m³
                    'density_source': rho_fuel_source,
                    'volume_required': fuel_volume_req * 1000,  # liters
                    'ullage_volume': (fuel_tank_volume - fuel_volume_req) * 1000,  # liters
                    'ullage_fraction_basis': TANK_ULLAGE_BASIS,
                },
                'structural': {
                    # Etiket ile hesap tek kaynaktan (bkz. oksitleyici tankı notu).
                    'material': _fmat.get('name', fuel_tank_material),
                    'material_key': fuel_tank_material,
                    'material_source': fuel_material_basis,
                    # P3B3-06: kriyojenik uygunluk hükmü artık kartta.
                    'cryogenic_suitability': self._tank_cryo_screening(
                        fuel_tank_material, self.fuel_type, 'fuel'),
                    'yield_strength_mpa': fuel_material_strength / 1e6,
                    'density_kg_m3': fuel_material_density,
                    'pressure_rating': tank_pressure / 1e5,  # bar
                    'pressure_rating_source': tank_pressure_source,
                    'safety_factor': safety_factor,
                    'safety_factor_source': safety_factor_source,
                    'tank_mass': fuel_tank_mass,  # kg
                    'mass_fraction': fuel_tank_mass / fuel_mass,  # tank mass / propellant mass
                    'insulation': 'Multi-Layer Insulation (MLI)' if self.fuel_type == 'lh2' else 'None'
                },
                'internal_structures': fuel_tank_internals,
                # A2/A3 (v2.6.27): çalkantı + basınçlı kap bağlamaları.
                'slosh': fuel_slosh,
                'pressure_vessel': fuel_vessel,
            },
            'system_summary': {
                'total_propellant_mass': ox_mass + fuel_mass,  # kg (rezervli)
                'total_propellant_mass_nominal':
                    ox_mass_nominal + fuel_mass_nominal,  # kg
                'total_propellant_mass_basis': TANK_LOADED_MASS_BASIS,
                'total_tank_mass': ox_tank_mass + fuel_tank_mass,  # kg
                'total_volume': (ox_tank_volume + fuel_tank_volume) * 1000,  # liters
                'overall_mass_fraction': (ox_tank_mass + fuel_tank_mass) / (ox_mass + fuel_mass),
                'burn_time': burn_time,  # seconds
                'burn_time_source': burn_time_source,
                'safety_margin': (safety_margin - 1) * 100,  # %
                'safety_margin_basis': TANK_RESERVE_BASIS,
                'ullage_fraction': ullage_fraction * 100,  # %
                'ullage_fraction_basis': TANK_ULLAGE_BASIS,
                # Besleme sistemi kartı da bu modeli kullanır (_size_tank);
                # iki kart artık aynı hacmi gösterir.
                'sizing_model': ('single tank-sizing model: '
                                 'V_tank = (m_propellant x reserve) / rho '
                                 '/ (1 - ullage)'),
                'oxidizer_density_source': rho_ox_source,
                'fuel_density_source': rho_fuel_source,
            }
        }
    
    def _tank_slosh_analysis(self, propellant_type, radius_m, fill_height_m,
                             rho, rho_source, internals):
        """Tank çalkantı (slosh) analizi — hrma.analysis.slosh_analysis ile.

        Yol haritası A2 (v2.6.27). Fizik künyesi: NASA SP-106 Böl. 2
        (Abramson & Bauer) / Dodge (2000) doğrusal serbest yüzey çalkantısı,
        dik rijit dairesel silindir; halka bafl sönümü Miles (1958) yarı
        ampirik kestirimi. Modül app.py /api/slosh-analysis ucunda ZATEN
        bağlıydı ama tank kartı kendi hesapladığı geometriyle onu hiç
        çağırmıyordu — kullanıcı bafl listesi görüyor, çalkantı frekansını
        göremiyordu.

        Girdilerin TAMAMI motorun kendi çözümünden gelir:
          - yarıçap ve sıvı yüksekliği tank boyutlandırmasından
            (h = V_sıvı / (pi R^2); V_sıvı rezerv dahil gerçek sıvı hacmi),
          - yoğunluk _propellant_density'nin tek kaynağından,
          - bafl geometrisi _design_tank_internals'ın GERÇEK halka bafl
            listesinden: serbest yüzeyin altındaki EN YAKIN bafl
            değerlendirilir (Miles modeli tek düz halka içindir).
        Tek varsayım g_eff = 1g'dir ve TANK_SLOSH_G_EFF_BASIS ile beyan
        edilir; uçuş ivmesi bağlanmaz (sayı uydurulmaz).
        """
        try:
            from hrma.analysis.slosh_analysis import analyze_slosh
        except Exception as exc:                      # pragma: no cover
            return {'status': 'not_computed',
                    'basis': f'slosh module unavailable: {exc}'}

        radius_m = float(radius_m)
        fill_height_m = float(fill_height_m)
        if radius_m <= 0.0 or fill_height_m <= 0.0:
            return {'status': 'not_computed',
                    'basis': ('tank radius or liquid depth is non-positive - '
                              'no slosh problem exists for an empty tank')}

        # Serbest yüzeyin altındaki en yakın GERÇEK bafl (pozisyonlar tank
        # tabanından; dizilim simetrik olduğundan yön seçimi sonucu
        # değiştirmez). Bafl genişliği halka listesinin kendi ölçüsüdür.
        baffle_kwargs = {}
        baffle_basis = ('no ring baffle lies below the free surface at this '
                        'fill level - a target-damping baffle recommendation '
                        'is reported instead (Miles 1958 inversion)')
        baffles = (internals or {}).get('slosh_baffles') or []
        depths = []
        for b in baffles:
            z_m = float(b.get('position', 0.0)) / 1000.0   # mm -> m (tabandan)
            depth = fill_height_m - z_m
            if depth > 0.0:
                depths.append((depth, b))
        if depths:
            depth, near = min(depths, key=lambda t: t[0])
            width_m = float(near.get('ring_width_mm', 0.0)) / 1000.0
            width_ratio = min(max(width_m / radius_m, 0.0), 1.0)
            if width_ratio > 0.0:
                baffle_kwargs = {
                    'baffle_width_ratio': width_ratio,
                    'baffle_depth_ratio': depth / radius_m,
                }
                baffle_basis = (
                    'the ring baffle of the tank internals list nearest '
                    'below the full-fill free surface, evaluated with its '
                    'actual ring width (Miles 1958 single flat ring; the '
                    'wave amplitude is the module\'s declared small-'
                    'amplitude design point)')

        try:
            result = analyze_slosh(radius=radius_m,
                                   fill_height=fill_height_m,
                                   g_eff=G_0, fluid_density=float(rho),
                                   **baffle_kwargs)
        except Exception as exc:
            return {'status': 'not_computed',
                    'basis': f'slosh analysis rejected the inputs: {exc}'}

        result = dict(result)
        result.update({
            'status': 'computed',
            'propellant': propellant_type,
            'g_eff_basis': TANK_SLOSH_G_EFF_BASIS,
            'fill_height_basis': (
                'liquid depth h = V_liquid / (pi R^2) from the tank sizing '
                'model (reserve-loaded liquid volume, single _size_tank '
                'source); the cylinder is the same one the tank card '
                'publishes'),
            'density_source': rho_source,
            'baffle_basis': baffle_basis,
            'basis': (
                'computed by hrma.analysis.slosh_analysis (NASA SP-106 / '
                'Dodge 2000 linear slosh, upright rigid cylinder) with the '
                'tank geometry and propellant density of THIS design; the '
                'same analyser serves /api/slosh-analysis'),
        })
        return result

    def _tank_pressure_vessel_analysis(self, tank_label, tank_pressure_pa,
                                       diameter_m, wall_thickness_m,
                                       material_key):
        """Tank basınçlı kap analizi — hrma.analysis.pressure_vessel ile.

        Yol haritası A3 (v2.6.27). Katı motordaki desenin sıvı karşılığı
        (solid_rocket_engine._calculate_safety_analysis): membran gerekli
        kalınlık + kapak (başlık) kalınlıkları + MAWP/proof/burst zinciri
        merkezi PressureVesselAnalyzer'dan okunur (AIAA S-080 modu; Faupel
        kalın cidar + ince cidar plastik limit kopması). Girdiler tank
        kartının KENDİ değerleridir: MEOP = tank basıncı, çap/cidar/malzeme
        tank boyutlandırmasından — iki kart çelişemez.

        Cidar tasarım sıcaklığı ORTAM alınır ve beyan edilir: HRMA'da tank
        termal modeli yok. Kriyojenik iticide (LOX/LH2) düşük sıcaklık
        tokluğu (DBTT) denetimi bu çağrıda DEVREYE GİRMEZ; sayı uydurmak
        yerine sınır açıkça yazılır.
        """
        # ÖH defter P3B3-11 (Z5S/PK1): buraya İŞLETME basıncı MEOP diye
        # veriliyordu; aynı tankın emniyet vanası ise (bkz.
        # _design_tank_internals -> relief_valve) o basıncın
        # RELIEF_VALVE_SET_PRESSURE_FACTOR = 1,10 katında açıyordu ve iki
        # alan arasında çapraz denetim YOKTU. ÖLÇÜLDÜ (25 kN): turbopompalı
        # koşuda meop_bar = 3,0000 / vana ayarı = 3,3000; basınç beslemelide
        # 105,0000 / 115,5000. Kap, kendi vanası açılmadan ÖNCE fiilen
        # ulaşacağı basıncın %10 ALTINDA nitelendiriliyor ve status=PASS
        # hükmü o düşük zeminde veriliyordu.
        #
        # ASME VIII Div.1 UG-134 mantığı: emniyet vanası ayarı tasarım
        # basıncını (MAWP) AŞAMAZ; yani kap en az vana ayarına göre
        # nitelendirilmelidir. Nitelendirme basıncı artık vana ayarının ta
        # kendisidir ve işletme basıncı ayrı ADLA yanında durur — iki sayı
        # aynı adı paylaşmaz, biri diğerinin yerine sessizce geçmez.
        operating_bar = max(float(tank_pressure_pa) / PA_PER_BAR, 1e-6)
        qualification_bar = operating_bar * RELIEF_VALVE_SET_PRESSURE_FACTOR
        try:
            from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
            res = PressureVesselAnalyzer().analyze(
                meop_bar=qualification_bar,
                inner_diameter_mm=float(diameter_m) * 1000.0,
                material=material_key,
                wall_thickness_mm=float(wall_thickness_m) * 1000.0)
        except Exception as exc:
            return {'status': 'not_computed',
                    'basis': f'pressure-vessel analysis rejected the inputs: '
                             f'{exc}'}

        res = dict(res)
        if res.get('status') == 'FAIL':
            self._warn('warn.liquid.tank_vessel_fail', 'critical',
                       tank=tank_label,
                       burst_margin=round(float(res.get('burst_margin', 0.0)),
                                          2))
        res.update({
            'basis': (
                'computed by hrma.analysis.pressure_vessel (AIAA S-080 '
                'membrane + UG-32-form head closures, Faupel/thin-wall '
                'burst) with the MEOP, diameter, wall thickness and '
                'material of THIS tank card - the same analyser the solid '
                'motor safety panel uses'),
            'temperature_basis': (
                'wall design temperature assumed ambient: HRMA has no tank '
                'thermal model. For cryogenic propellants the low-'
                'temperature toughness (DBTT) screening of the pressure-'
                'vessel module is NOT engaged at the storage temperature - '
                'verify material toughness separately'),
            # P3B3-11: nitelendirme basıncının HANGİ basınç olduğu ve
            # işletme basıncıyla ilişkisi sayının yanında.
            'operating_pressure_bar': float(operating_bar),
            'relief_valve_set_pressure_bar': float(qualification_bar),
            'meop_basis': (
                'qualification pressure = tank operating pressure '
                f'({operating_bar:.4f} bar) x '
                f'{RELIEF_VALVE_SET_PRESSURE_FACTOR:g} '
                '(RELIEF_VALVE_SET_PRESSURE_FACTOR), i.e. the pressure this '
                'tank actually reaches before its own relief valve opens. '
                'ASME VIII Div.1 UG-134 style: the relief setting cannot '
                'exceed the design pressure, so the vessel is qualified at '
                'the relief setting, not at the operating point. The '
                'operating pressure itself is reported as '
                'operating_pressure_bar and is the SAME single-source value '
                'the feed chain and the tank card publish '
                '(structural.pressure_rating).'),
        })
        return res

    def _design_tank_internals(self, diameter, length, propellant_type,
                               tank_pressure_pa=None, mdot=None):
        """Tank iç yapıları — GEOMETRİDEN ve DEBİDEN hesaplanır.

        v2.6.26 öncesinde bu fonksiyonun döndürdüğü 25 yaprak SABİTTİ: giriş
        ağzı 100 mm, çıkış 150 mm, difüzör boyu 200 mm, sump 50 mm, emniyet
        vanası 25 mm, kanat 3 mm, bafl 2 mm, delik 50 mm, kütleler 2.5 / 6.0 /
        15.0 / 23.5 kg. 25 kN'lik motorla 2 MN'lik motor aynı tank ağzını ve
        aynı iç yapı kütlesini görüyordu; üstelik iç yapı kütlesi tank
        kütlesine EKLENDİĞİ için kütle oranı da bu sabitlerden etkileniyordu.
        Ayrıca delik sayısı ``(pi*D*oran)/(pi*(d/2)^2)`` ile hesaplanıyordu —
        pay [m], payda [m²] olduğundan bağıntı BOYUTSAL OLARAK YANLIŞTI.

        Şimdi:

        * Ağız çapları ``_calculate_line_diameter`` ile besleme hattının
          KENDİ modelinden gelir (A = ṁ/(ρ·v), v = 3-8 m/s bandı; kaynaksız
          HRMA tercihi, SP-125'te yok — KU-K1/SP-H1 K33), tank ağzı hattan
          biraz geniş tutulur.
        * Difüzör boyu artık bir seçim değil bir SONUÇTUR:
          L = (D_çıkış − D_giriş)/(2·tan θ).
        * Bafl halkası alanı, delik çapı ve delik sayısı boyutsal olarak
          doğru türetilir; HEDEF açık alan oranı ile GERÇEKLENEN oran ayrı
          ayrı raporlanır.
        * Kütleler geometri × malzeme yoğunluğu (materials_db) ile hesaplanır.
        * Emniyet vanası alanı API RP 520 Part I kritik (boğulmuş) gaz akışı
          bağıntısıyla, ullage yer değiştirme debisi üstünden boyutlandırılır.

        MODELLENMEYEN, açıkça öyle etiketlenen kalemler:
        * Sac kalınlıkları (kanat, bafl) ASGARİ İMALAT GAUGE'idir; çalkantı
          yükü (NASA SP-8031) eksenel ivme ister, araç modeli bu çözücüde yok.
        * Sump derinliği / standpipe yüksekliği geometrik zarftır; kritik
          dalma (gaz yutma) ölçütü (NASA SP-8004) çözülmez.
        """
        from hrma.data.materials_db import get_material_safe

        radius = diameter / 2.0
        if mdot is None:
            mdot = (getattr(self, 'mdot_ox', None) if propellant_type == 'oxidizer'
                    else getattr(self, 'mdot_fuel', None)) or 0.0
        mdot = float(mdot)

        try:
            _imat, _imat_key = get_material_safe(TANK_INTERNALS_MATERIAL)
        except KeyError as exc:                              # pragma: no cover
            raise ValueError('tank internals material missing from '
                             'materials_db') from exc
        rho_internals = float(_imat['density'])              # kg/m³
        internals_material = _imat.get('name', _imat_key)

        # --- Girdap önleyici kanatlar --------------------------------------
        av_diameter = diameter * TANK_ANTIVORTEX_D_RATIO      # m
        av_height = diameter * TANK_ANTIVORTEX_H_RATIO        # m
        vane_thickness_m = TANK_VANE_GAUGE_MM / 1000.0
        # Kanat = dikdörtgen plaka: yükseklik x radyal uzunluk x kalınlık.
        # Radyal uzunluk göbekten dış çapa: D_cihaz/2.
        vane_radial_len = av_diameter / 2.0                   # m
        anti_vortex_mass = (TANK_ANTIVORTEX_VANE_COUNT * av_height
                            * vane_radial_len * vane_thickness_m
                            * rho_internals)                  # kg
        # T13 (2026-08-03): bu sözlük yıllarca AYNI kayıtta iki birim
        # yayımladı — 'diameter'/'height' METRE, 'vane_radial_length_mm' ve
        # 'vane_thickness' MİLİMETRE — ve hiçbir yerde birim BEYAN edilmedi.
        # Her tüketici tahmin etmek zorunda kaldı, ikisi de yanlış tahmin
        # etti: /liquid 3B görünümü çapı 2000'e bölüp düzeneği 258,91 mm
        # yerine 0,26 mm çizdi (gözle görünmez), cad_export ise ZIP'e 0,2356
        # yazdı. Çözüm birimi VERİYLE birlikte taşımak: 'units' alanı
        # 'diameter'/'height' alanlarının birimini beyan eder, '*_mm' alanları
        # ise tahmine hiç gerek bırakmaz. Eski metre alanları geriye uyumluluk
        # için bırakıldı (cad_export.normalize_anti_vortex_mm onları çözücünün
        # kendi geometrik özdeşliğinden zaten doğru çeviriyor).
        anti_vortex = {
            'type': 'Radial vanes',
            'diameter': av_diameter,                          # m
            'height': av_height,                              # m
            'units': 'm',                # 'diameter'/'height' alanlarının birimi
            'diameter_mm': av_diameter * 1000.0,              # mm
            'height_mm': av_height * 1000.0,                  # mm
            'vane_count': TANK_ANTIVORTEX_VANE_COUNT,
            'vane_count_basis': (
                'geometric proportioning choice: the vane count is a fixed '
                'radial layout number, NOT sized against a swirl or drain '
                'load. NASA SP-8004 vane sizing needs the outflow vortex '
                'model, which is not solved here'),
            'vane_count_load_sized': False,
            'vane_radial_length_mm': vane_radial_len * 1000.0,
            'vane_thickness': TANK_VANE_GAUGE_MM,             # mm
            'vane_thickness_basis': (
                'minimum manufacturing gauge - NOT sized against a load; the '
                'vane flow/impact load is not modelled (NASA SP-8031 ring '
                'baffle loads need the vehicle axial acceleration, which this '
                'solver does not have)'),
            'vane_thickness_load_sized': False,
            'material': internals_material,
            'geometry_basis': (
                f'device diameter = {TANK_ANTIVORTEX_D_RATIO:g} x tank '
                f'diameter, height = {TANK_ANTIVORTEX_H_RATIO:g} x tank '
                'diameter (geometric proportioning)'),
        }

        # --- Çalkantı baflları ---------------------------------------------
        baffle_count = max(2, int(length / diameter))
        d_out = diameter * TANK_BAFFLE_OUTER_D_RATIO          # m
        d_in = diameter * TANK_BAFFLE_INNER_D_RATIO           # m
        ring_area = np.pi / 4.0 * (d_out ** 2 - d_in ** 2)    # m² (delik yok)
        ring_width = (d_out - d_in) / 2.0                     # m radyal genişlik
        # Delik çapı: üçgen adımlı delikli plaka özdeşliğinden. Adım p halka
        # genişliğine sıra sayısıyla oturur; çap hedef açık alan oranından
        # çıkar -> delik çapı tank çapıyla ölçeklenir.
        hole_pitch = ring_width / TANK_BAFFLE_HOLE_ROWS        # m
        _tri = np.pi / (2.0 * np.sqrt(3.0))                    # üçgen dizilim
        hole_diameter = max(hole_pitch
                            * np.sqrt(TANK_BAFFLE_OPEN_AREA_TARGET / _tri),
                            1e-3)
        hole_area = np.pi / 4.0 * hole_diameter ** 2          # m²
        # Delik SAYISI hedef açık alan oranından BOYUTSAL OLARAK DOĞRU türetilir
        # (eski bağıntı [m]/[m²] idi). En az bir delik.
        holes_per_baffle = max(1, int(round(
            TANK_BAFFLE_OPEN_AREA_TARGET * ring_area / hole_area)))
        open_area_achieved = holes_per_baffle * hole_area / max(ring_area, 1e-12)
        baffle_thickness_m = TANK_BAFFLE_GAUGE_MM / 1000.0
        baffle_solid_area = ring_area * (1.0 - open_area_achieved)   # m²
        baffle_mass_each = baffle_solid_area * baffle_thickness_m * rho_internals
        baffle_total_mass = baffle_count * baffle_mass_each          # kg

        baffles = []
        for i in range(baffle_count):
            baffle_position = (i + 1) * length / (baffle_count + 1)
            baffles.append({
                'position': baffle_position * 1000.0,          # mm
                'type': 'Perforated ring',
                'outer_diameter': d_out * 1000.0,              # mm
                'inner_diameter': d_in * 1000.0,               # mm
                'ring_width_mm': ring_width * 1000.0,
                'thickness': TANK_BAFFLE_GAUGE_MM,             # mm
                'thickness_basis': (
                    'minimum manufacturing gauge - NOT sized against the slosh '
                    'load; NASA SP-8031 ring-baffle sizing needs the vehicle '
                    'axial acceleration and wave height. v2.6.27: the tank '
                    'slosh block DOES now report modal frequency/mass at a '
                    'declared 1 g (A2 wiring), but the flight acceleration '
                    'and the design wave height remain unmodelled, so the '
                    'plate thickness is still a gauge, not a load result'),
                'thickness_load_sized': False,
                'hole_diameter': hole_diameter * 1000.0,       # mm
                'hole_pitch_mm': hole_pitch * 1000.0,
                'hole_diameter_basis': (
                    f'triangular-pitch perforated plate: {TANK_BAFFLE_HOLE_ROWS} '
                    'hole rows across the ring width sets the pitch (a '
                    'manufacturing choice); d = p*sqrt(open_area_ratio / '
                    '(pi/(2*sqrt(3)))) is then a geometric identity'),
                'hole_count': holes_per_baffle,
                'hole_count_basis': (
                    'n = target open-area ratio x ring annulus area / hole '
                    'area (dimensionally consistent)'),
                'open_area_ratio': TANK_BAFFLE_OPEN_AREA_TARGET * 100.0,  # %
                'open_area_ratio_is_target': True,
                'open_area_ratio_achieved': open_area_achieved * 100.0,   # %
                # ÖLÇÜLDÜ (v2.6.26): tank çapı 295 -> 3702 mm (12,5 kat)
                # aralığında hole_count 50'de, gerçeklenen oran %14,9818'de
                # sabit kalıyor. Bu bir uydurma sayı DEĞİL, ölçek
                # değişmezliğinin sonucudur ve öyle beyan edilir.
                'open_area_ratio_achieved_basis': (
                    'scale-invariant by construction: the hole area and the '
                    'ring annulus area both scale as D^2, so the achieved '
                    'open area ratio does not change with tank size. Only the '
                    'hole-row count and the target ratio move it; the residual '
                    'gap to the target is the integer rounding of the hole '
                    'count'),
                'open_area_target_basis': (
                    'design target; NASA SP-8031 gives 10-30% open area for '
                    'perforated ring slosh baffles'),
                'mass_kg': baffle_mass_each,
                'material': internals_material,
            })

        # --- Giriş / çıkış ağızları ----------------------------------------
        # Besleme hattı çapı motorun KENDİ hat modelinden (tek kaynak).
        d_line = (self._calculate_line_diameter(mdot, propellant_type)
                  if mdot > 0 else 0.0)                        # m
        d_outlet = d_line * TANK_OUTLET_TO_LINE_D_RATIO        # m
        d_inlet = d_line                                       # m (dolum hattı)
        # Difüzör: giriş çapından alan oranı kadar genişler; boy artık bir
        # SEÇİM değil bir SONUÇTUR.
        d_diffuser_exit = d_inlet * np.sqrt(TANK_DIFFUSER_AREA_RATIO)
        diffuser_length = ((d_diffuser_exit - d_inlet) / 2.0
                           / np.tan(np.radians(TANK_DIFFUSER_HALF_ANGLE_DEG)))
        # Sump / standpipe: kanat yüksekliği + bir ağız çapı yaklaşma boyu.
        sump_depth = av_height + d_outlet                      # m
        port_geometry_basis = (
            'line diameter from _calculate_line_diameter (A = mdot/(rho*v), '
            f'target {FEED_LINE_TARGET_VELOCITY_MS:g} m/s, rounded to a '
            'standard pipe size); tank port = '
            f'{TANK_OUTLET_TO_LINE_D_RATIO:g} x line diameter')
        submergence_basis = (
            'geometric envelope: anti-vortex vane height plus one port '
            'diameter of approach length. The critical submergence '
            '(gas-ingestion) criterion of NASA SP-8004 is NOT solved.')

        if propellant_type == 'oxidizer':
            inlet = {
                'position': 'Top center',
                'type': 'Diffuser',
                'diameter': d_inlet * 1000.0,                  # mm
                'diffuser_angle': TANK_DIFFUSER_HALF_ANGLE_DEG,
                # Gerekçe kaynak kodda vardı ama çıktıya hiç taşınmıyordu.
                'diffuser_angle_basis': (
                    f'{TANK_DIFFUSER_HALF_ANGLE_DEG:g} deg diffuser half '
                    'angle for non-separating diffusion (ESDU 73024 conical '
                    'diffuser separation limit; not found in NASA SP-125) - a '
                    'design '
                    'choice, NOT solved from the local flow'),
                'diffuser_exit_diameter_mm': d_diffuser_exit * 1000.0,
                'diffuser_length': diffuser_length * 1000.0,   # mm
                'diffuser_length_basis': (
                    'L = (D_exit - D_inlet)/(2*tan(half angle)) - a consequence '
                    'of the diameters and the angle, not a chosen length'),
                'diameter_basis': port_geometry_basis,
                'purpose': 'Reduce velocity and prevent splashing',
            }
            outlet = {
                'position': 'Bottom center',
                'type': 'Sump with anti-vortex',
                'diameter': d_outlet * 1000.0,                 # mm
                'diameter_basis': port_geometry_basis,
                'sump_depth': sump_depth * 1000.0,             # mm
                'sump_depth_basis': submergence_basis,
                'screen_mesh': '200 mesh (74 micron)',
                'purpose': 'Ensure bubble-free propellant supply',
            }
        else:
            inlet = {
                'position': 'Top side',
                'type': ('Tangential entry' if self.fuel_type == 'lh2'
                         else 'Axial diffuser'),
                'diameter': d_inlet * 1000.0,                  # mm
                'diameter_basis': port_geometry_basis,
                'swirl_angle': 30 if self.fuel_type == 'lh2' else 0,
                'purpose': 'Minimize heat input (LH2) or turbulence (others)',
            }
            outlet = {
                'position': 'Bottom center',
                'type': 'Standpipe with anti-vortex',
                'diameter': d_outlet * 1000.0,                 # mm
                'diameter_basis': port_geometry_basis,
                'standpipe_height': sump_depth * 1000.0,       # mm
                'standpipe_height_basis': submergence_basis,
                'anti_vortex_height': av_height * 1000.0,      # mm
                'purpose': 'Prevent gas ingestion during low-g phases',
            }

        # --- Emniyet vanası (API RP 520 Part I, kritik gaz akışı) ----------
        relief = self._size_tank_relief_valve(tank_pressure_pa, mdot,
                                              propellant_type)

        # --- Enstrümantasyon -------------------------------------------------
        # v2.6.26 beyanı: bu sayıların hiçbiri bir ölçüm gereksiniminden
        # ÇÖZÜLMEZ. Prob YERLEŞİMİ tek tanım yeridir ve sayı ondan türer;
        # ikisi ayrı yazılırsa biri değişince öteki sessizce yalan söyler.
        level_probe_positions = TANK_LEVEL_PROBE_POSITIONS
        instrumentation = {
            'pressure_transducers': TANK_PRESSURE_TRANSDUCER_COUNT,
            'pressure_transducers_basis': (
                'redundancy architecture assumption (dual pressure '
                'transducers per tank); NOT derived from a reliability target '
                'or a measurement-accuracy requirement - HRMA models neither'),
            'temperature_sensors': 3 if self.fuel_type == 'lh2' else 1,
            'level_sensors': {
                'type': 'Capacitive probes',
                'count': len(level_probe_positions),
                'count_basis': (
                    'instrumentation architecture assumption: the count is '
                    'the length of the declared probe position list '
                    'TANK_LEVEL_PROBE_POSITIONS, NOT derived from a '
                    'measurement-accuracy or ullage-resolution requirement'),
                'positions': list(level_probe_positions),
                'positions_basis': (
                    'evenly spaced fill-fraction stations plus a near-full '
                    'probe; a layout choice, not solved from a draining or '
                    'sloshing model'),
            },
            'relief_valve': relief,
        }

        # --- Borulama kütlesi ----------------------------------------------
        # Giriş + çıkış stub boruları: ince cidarlı silindir kabuk, cidar
        # kalınlığı iç yapı gauge'i, boy = TANK_PORT_STUB_LD x çap.
        def _stub_mass(d_port):
            if d_port <= 0:
                return 0.0
            t = TANK_VANE_GAUGE_MM / 1000.0
            return (np.pi * (d_port + t) * t * TANK_PORT_STUB_LD * d_port
                    * rho_internals)

        plumbing_mass = _stub_mass(d_inlet) + _stub_mass(d_outlet)
        # Difüzör konisi (kesik koni yanal yüzeyi)
        if diffuser_length > 0:
            slant = np.hypot(diffuser_length,
                             (d_diffuser_exit - d_inlet) / 2.0)
            plumbing_mass += (np.pi * 0.5 * (d_inlet + d_diffuser_exit) * slant
                              * (TANK_VANE_GAUGE_MM / 1000.0) * rho_internals)

        total_internal_mass = (anti_vortex_mass + baffle_total_mass
                               + plumbing_mass)

        return {
            'anti_vortex_device': anti_vortex,
            'slosh_baffles': baffles,
            'inlet_configuration': inlet,
            'outlet_configuration': outlet,
            'instrumentation': instrumentation,
            'mass_breakdown': {
                'anti_vortex': anti_vortex_mass,   # kg
                'baffles': baffle_total_mass,      # kg
                'plumbing': plumbing_mass,         # kg
                'total_mass': total_internal_mass,  # kg
                'material': internals_material,
                'density_kg_m3': rho_internals,
                'method': ('component geometry x material density from '
                           'materials_db (no fixed allowances)'),
            },
            'design_features': {
                'slosh_damping': f'{baffle_count} perforated ring baffles',
                'vortex_prevention': 'Radial vane anti-vortex device',
                'propellant_settling': 'Ullage gas pressurization system',
                'thermal_management': ('MLI insulation' if self.fuel_type == 'lh2'
                                       else 'Passive radiation'),
            },
            'not_modelled': [
                'slosh load sizing of the baffle and vane plate thickness '
                '(NASA SP-8031; needs vehicle axial acceleration). Modal '
                'slosh frequency/mass ARE reported in the tank slosh block '
                'at a declared 1 g (v2.6.27, A2), but no load sizing is '
                'performed from them',
                'critical submergence / gas-ingestion criterion for the outlet '
                '(NASA SP-8004)',
            ],
        }

    def _size_tank_relief_valve(self, tank_pressure_pa, mdot, propellant_type):
        """Tank emniyet vanası — API RP 520 Part I kritik gaz akışı.

        Boyutlandırma durumu (AÇIKÇA beyan edilir): tank boşalırken ullage
        hacmini dolduran basınçlandırma gazının NOMİNAL debisi. Bu bir ALT
        SINIRDIR: regülatörün açık kalması (fail-open) gibi arıza senaryosunun
        debisi bu çözücüde modellenmiyor, dolayısıyla uydurulmuyor.

        Boğulmuş (kritik) akışta bir orifisin kütle debisi

            ṁ = K_d · A · P0 · sqrt(γ/(R_s·T0)) · (2/(γ+1))^((γ+1)/(2(γ-1)))

        (API RP 520 Part I kritik akış bağıntısının SI biçimi; K_d = 0.975
        sertifikalı vana boşaltma katsayısı.) A için çözülür.
        """
        out = {
            'position': 'Top of tank',
            'sizing_case': (
                'ullage gas displacement at the nominal expulsion rate '
                '(lower bound). Regulator-fail-open capacity is NOT modelled.'),
            'method': ('API RP 520 Part I critical (choked) gas flow, '
                       f'Kd = {RELIEF_VALVE_DISCHARGE_COEFF:g}'),
        }
        if not tank_pressure_pa or tank_pressure_pa <= 0 or mdot <= 0:
            out.update({'diameter': None, 'set_pressure': None,
                        'diameter_basis': 'not_modelled (tank state unknown)'})
            return out

        set_pressure_pa = tank_pressure_pa * RELIEF_VALVE_SET_PRESSURE_FACTOR
        # Basınçlandırma gazı kimliği — TEK kaynak (P3B1-05).
        # Eskiden bu blok gazı kendi başına seçiyordu ('nitrogen' değilse
        # helyum) ve besleme kartının yayımladığı 'autogenous' tipiyle aynı
        # yanıtta çelişiyordu. Artık ikisi de _pressurization_type()'ı okur.
        _tip, _tip_kunye = self._pressurization_type()
        if _tip == 'autogenous':
            # Autogenous'ta ullage gazı iticinin KENDİSİdir.
            gas_name = ('oxygen' if propellant_type == 'oxidizer'
                        else str(self.fuel_type).strip().lower())
        elif _tip == 'gaseous_nitrogen':
            gas_name = 'nitrogen'
        else:
            gas_name = str(_tip)
        out['pressurant_gas'] = gas_name
        out['pressurant_basis'] = _tip_kunye
        try:
            from hrma.analysis.pressurant_sizing import gas_properties
            _key, gas = gas_properties(gas_name)
            r_specific = float(gas['R'])          # J/(kg·K)
            gamma = float(gas['gamma'])
        except Exception as exc:                             # pragma: no cover
            out.update({'diameter': None, 'set_pressure':
                        set_pressure_pa / 1e5,
                        'diameter_basis':
                        f'not_modelled (pressurant properties unavailable: '
                        f'{exc})'})
            return out

        rho_liquid, _ = self._propellant_density(propellant_type)
        t0 = RELIEF_VALVE_GAS_TEMP_K
        # Boşalan sıvı hacmini dolduran gazın kütle debisi
        q_ullage = mdot / max(float(rho_liquid), 1e-9)        # m³/s
        rho_gas = set_pressure_pa / (r_specific * t0)          # kg/m³
        mdot_gas = rho_gas * q_ullage                          # kg/s

        flow_fn = (np.sqrt(gamma / (r_specific * t0))
                   * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0)
                                               / (2.0 * (gamma - 1.0))))
        area = mdot_gas / (RELIEF_VALVE_DISCHARGE_COEFF * set_pressure_pa
                           * flow_fn)                          # m²
        d_relief = 2.0 * np.sqrt(area / np.pi)                 # m
        out.update({
            'diameter': d_relief * 1000.0,                     # mm
            'diameter_basis': ('required orifice diameter for the sizing case '
                               'above'),
            'required_area_mm2': area * 1e6,
            'relieving_gas': gas_name,
            'relieving_flow_kg_s': mdot_gas,
            'relieving_gas_temperature_K': t0,
            'relieving_gas_temperature_basis': (
                'standard reference temperature; the tank ambient temperature '
                'is not modelled (temp_range_* is a declared unwired input)'),
            'set_pressure': set_pressure_pa / 1e5,             # bar
            'set_pressure_basis': (
                f'{RELIEF_VALVE_SET_PRESSURE_FACTOR:g} x tank operating '
                'pressure (ASME VIII Div.1 UG-134 style). This used to be '
                '1.5 x CHAMBER pressure, which put a 105 bar relief setting '
                'on a 3 bar NPSH tank.'),
        })
        return out

    @staticmethod
    def _suction_line_dp(line, density):
        """Emme tarafı (tank -> pompa girişi) kayıp dökümü [bar].

        B5 (v2.6.27): NPSH'tan düşülecek kayıp YALNIZ emme kalemleridir —
        tank çıkışı (K) + hat süzgeci (K) + kısa düz emme borusu
        (FEED_SUCTION_LINE_LENGTH_M üzerinden Darcy-Weisbach). Ana vana ve
        dirsekli koşu basma tarafındadır (FEED_SUCTION_LINE_BASIS). Sürtünme
        katsayısı, çap ve hız hattın KENDİ Darcy zincirinden okunur
        (_line_pressure_drops sözlüğü) — ikinci bir hat modeli kurulmaz;
        K sabitleri de aynı tek tanım noktasından gelir. Hem motorun kendi
        pompa tasarımı (_design_pump) hem C1 modül bağlaması (_pump_block)
        BU yardımcıyı çağırır: iki yer tek emme kümesini okur.
        """
        v = float(line['line_velocity_m_s'])
        d = float(line['line_diameter_mm']) / 1000.0
        f = float(line['friction_factor'])
        dyn = 0.5 * float(density) * v * v               # Pa
        items = {
            'tank_outlet': FEED_K_TANK_OUTLET * dyn / PA_PER_BAR,
            'filters': FEED_K_FILTER * dyn / PA_PER_BAR,
            'suction_line': (f * (FEED_SUCTION_LINE_LENGTH_M / d) * dyn
                             / PA_PER_BAR),
        }
        items['total'] = sum(items.values())
        return items

    def _design_pump(self, mdot, density, discharge_pressure_bar,
                     tank_pressure_bar, shaft_power_kw=None,
                     propellant=None, line=None, role=None):
        """Tek pompanın benzerlik tabanlı tasarımı (sabit eğri YOK).

        2026-07-19 denetimi: H-Q ve verim eğrileri uydurma parabollerden
        (1.2 − 0.8·(Q/Q0−1)², 0.78·(1−2.5·(Q/Q0−1)²)) geliyordu; devir 25000
        rpm ve uç hızı 400 m/s her motorda aynıydı. Yeni zincir:

        * Basma yüksekliği H = ΔP/(ρ·g) — gerçek basınç yükselmesinden.
        * NPSH_a: turbopump_sizing.npsh_available_m (Eş. 1, TEK kaynak) —
          (P_tank − ΔP_emme − P_buhar)/(ρ·g). Buhar basıncı iticinin GERÇEK
          kaydından (_feed_fluid_record); kayıt yoksa NBP varsayımı YÜKSEK
          sesle beyan edilir. Hat kaybı yalnız EMME kalemleridir
          (_suction_line_dp).
        * Devir emme özgül hızı SINIRININ derate katıdır:
          ω = derate · ω_ss·(g·NPSH_a)^0.75/√Q (Huzel & Huang Ch. 6;
          derate = SPEED_DERATE_DEFAULT, modülden ithal — ikinci 0.9 yok).
          Böylece NPSH_gerekli/NPSH_mevcut = derate^(4/3) olur ve marj
          totolojik sıfır DEĞİLDİR (B5 düzeltmesi: eski kod devri tam
          kavitasyon sınırından seçiyordu, npsh_margin ≡ 0 idi ve
          npsh_insufficient uyarısı cebirsel olarak ulaşılamazdı).
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

        # --- B5: buhar basıncı — gerçek kayıt > beyanlı NBP yedeği ---------
        record = None
        if propellant is not None:
            _, record = self._feed_fluid_record(propellant)
        if record is not None and record.get('vapor_pressure_Pa') is not None:
            vapor_pa = float(record['vapor_pressure_Pa'])
            vapor_source = str(record.get('vapor_pressure_source'))
        else:
            vapor_pa = PUMP_NPSH_VAPOR_PRESSURE_BAR * PA_PER_BAR
            vapor_source = (
                'vapor pressure record missing for '
                f"'{propellant}': normal-boiling-point storage saturation "
                f'({PUMP_NPSH_VAPOR_PRESSURE_BAR:g} bar, '
                'PUMP_NPSH_VAPOR_PRESSURE_BAR) assumed - a declared '
                'fallback, NOT a computed property')
            self._warn('warn.liquid.npsh_vapor_pressure_assumed', 'warning',
                       propellant=str(propellant),
                       assumed_bar=PUMP_NPSH_VAPOR_PRESSURE_BAR)

        # --- B5: emme tarafı hat kaybı (ana vana/basma kalemleri HARİÇ) ----
        if line is not None:
            suction = self._suction_line_dp(line, density)
            suction_dp_bar = suction['total']
        else:
            suction = None
            suction_dp_bar = 0.0

        # --- B5: NPSH_a TEK kaynaktan (turbopump_sizing.npsh_available_m) --
        tank_pa = float(tank_pressure_bar) * PA_PER_BAR
        suction_dp_pa = suction_dp_bar * PA_PER_BAR
        try:
            npsh_avail = npsh_available_m(tank_pa, vapor_pa, density,
                                          suction_dp_pa)
            suction_feasible = True
        except ValueError:
            # Gerçek (<= 0) değer RAPORLANIR; pozitif değer uydurulmaz.
            npsh_avail = (tank_pa - suction_dp_pa - vapor_pa) / (density * g0)
            suction_feasible = False
            self._warn('warn.liquid.npsh_pressurization_insufficient',
                       'critical',
                       npsh_available_m=round(float(npsh_avail), 1),
                       tank_bar=round(float(tank_pressure_bar), 2),
                       suction_dp_bar=round(float(suction_dp_bar), 2))

        # --- F3: SP-8109 §3.2.1.2 giriş hız-yükü gereksinimi (CANLI sınama)
        npsh_vh_factor, npsh_vh_class = self._npsh_velocity_head_factor(
            propellant)
        npsh_inlet_v = (float(line['line_velocity_m_s'])
                        if line is not None else None)
        if npsh_inlet_v is None:
            npsh_req_vh = None
            npsh_vh_status = 'not_evaluated'
        else:
            npsh_req_vh = float(npsh_required_velocity_head_m(
                npsh_inlet_v, npsh_vh_factor))
            # ÖH D21 · OH-D20-09 — TEK MARJ SÖZLEŞMESİ. SP-8109 §3.2.1.2
            # kuralı zaten marjlı bir KABUL TABANIdır (k_v'nin kendisi
            # paydır); üstüne SP-8107 Table II oranını (1,25) koymak aynı
            # payı iki kez saymaktı. ÖLÇÜLDÜ (once.json OH-D20-09):
            # kural tabanı 16,8865 m -> yayımlanan gereksinim 21,1081 m.
            gerekli = (float(NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE)
                       * npsh_req_vh)
            # Tank basıncı bu gereksinimden TÜRETİLDİĞİNDE yöneten pompa tam
            # eşitlik noktasında oturur; bar<->Pa çevrimlerinin 1e-16'lık
            # artığı hükmü rastgele 'not_met'e çeviriyordu (ölçüldü: V5 ox
            # 4,00398 vs 4,00408). Bu SAYISAL bir eşik toleransıdır, fizik
            # gevşetmesi değil: 1e-6 bağıl, yani 4 m'lik gereksinimde 4 µm.
            npsh_vh_status = (
                'met' if float(npsh_avail) >= gerekli * (1.0 - 1e-6)
                else 'not_met')
            if npsh_vh_status == 'not_met':
                self._warn('warn.liquid.npsh_velocity_head_not_met',
                           'critical', propellant=str(propellant),
                           npsh_available_m=round(float(npsh_avail), 3),
                           npsh_required_m=round(gerekli, 3),
                           velocity_head_factor=float(npsh_vh_factor),
                           inlet_velocity_ms=round(float(npsh_inlet_v), 2))

        # F3 fail-closed: donanım hükmü ARTIK yalnız NPSH_a > 0'a değil,
        # SP-8109 §3.2.1.2 giriş hız-yükü gereksinimine de bağlıdır.
        # 'Kavitasyona girmiyor' ile 'kavitasyonsuz ÇALIŞIR' aynı şey
        # değildir: aradaki fark tam da bu kuraldır.
        hardware_feasible = bool(suction_feasible
                                 and npsh_vh_status != 'not_met')

        # --- B5: devir = derate x emme sınırı (modül disipliniyle) ---------
        npsh_for_speed = (npsh_avail if suction_feasible
                          else PUMP_NPSH_SPEED_FLOOR_PA / (density * g0))
        omega = (SPEED_DERATE_DEFAULT * PUMP_SUCTION_SPECIFIC_SPEED
                 * (g0 * npsh_for_speed) ** 0.75
                 / max(np.sqrt(q), 1e-9))                 # rad/s
        rpm = omega * 60.0 / (2.0 * np.pi)
        if suction_feasible:
            speed_source = (
                'suction specific speed limit derated by '
                f'{SPEED_DERATE_DEFAULT:g} (SPEED_DERATE_DEFAULT) for NPSH '
                'margin')
        else:
            speed_source = (
                'suction limit undefined (NPSH_available <= 0): a nominal '
                f'{PUMP_NPSH_SPEED_FLOOR_PA:g} Pa inlet-head floor sizes the '
                'hardware; the design is NOT feasible at this tank pressure '
                '(see warnings)')
        if rpm > PUMP_MAX_SPEED_RPM:
            rpm = PUMP_MAX_SPEED_RPM
            omega = rpm * 2.0 * np.pi / 60.0
            speed_source = f'capped at the {PUMP_MAX_SPEED_RPM:.0f} rpm practical limit'
            self._warn('warn.liquid.pump_speed_capped', 'info',
                       limit_rpm=round(float(PUMP_MAX_SPEED_RPM)))

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

        eta_bep = float(getattr(self, 'pump_efficiency',
                                PUMP_EFFICIENCY_DEFAULT))
        power_design = density * g0 * head * q / (eta_bep * 1000.0)  # kW
        power_source = ('rho*g*H*Q/eta at the design point '
                        '(total pump head rise)')
        # Y4 (2026-07-30): çok kademeli mimaride (staged combustion'da RS-25
        # tipi ana+boost oksitleyici pompası) TOPLAM debi bildirilen en yüksek
        # basma basıncını GÖRMEZ; yalnız küçük ön yakıcı payı boost kademesine
        # girer. Tek kademe varsayımıyla hesaplanan güç bu durumda çevrim güç
        # dengesinden %12.8 sapıyordu. Çevrim mil gücü verildiyse TEK KAYNAK
        # odur; eğri şekli korunarak aynı oranla ölçeklenir.
        # --- ÖH defter P3B3-07 (D18) --------------------------------------
        # Ölçüldü (once.json, 250 kN staged_combustion oksitleyici pompası):
        # yayımlanan design_power 1251,65 kW iken AYNI karttaki
        # rho*g*H*Q/eta = 1663,76 kW — kart kendi içinde %24,77 çelişiyordu.
        # Sebep: güç çevrim çözümünden ÖLÇEKLENİYOR ama H, Q ve eta TEK
        # KADEME değerlerinde kalıyor; kartı okuyan P = rho*g*H*Q/eta
        # özdeşliğini kuramıyor ve hangi sayının yanlış olduğunu bilemiyor.
        # Beyan (design_power_source) doğruydu ama EKSİK büyüklüğü vermiyordu.
        # Onarım: eksik büyüklük YAYIMLANIR — çevrim gücünün aynı Q ve eta'da
        # ima ettiği TOPLAM basma yüksekliği ve ondan çıkan kademe sayısı.
        # Böylece kart kapanır: P = rho*g*H_toplam*Q/eta (artık TAM).
        # design_head TEK KADEME kalır (çark geometrisini o kurar) ve künyesi
        # bunu söyler.
        head_total = head
        cycle_power_ratio = 1.0
        cycle_scale = None
        if shaft_power_kw is not None and power_design > 1e-9:
            cycle_scale = float(shaft_power_kw) / power_design
            power_design = float(shaft_power_kw)
            power_source = ('cycle power balance shaft power (multi-stage '
                            'architecture accounted for)')
            head_total = head * cycle_scale
            cycle_power_ratio = cycle_scale

        # --- ÖH D28 · OH-D27-02 — KADEME SAYISI BİR TASARIM KARARIDIR -----
        #
        # ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D28/sivi/a1/once.json``;
        # beş motor, on pompa kartı): AYNI yanıtta
        # ``detailed_feed_system.turbopump_sizing.<pompa>.pump.stage_count``
        # 2 / 3 / 4 / 6 kademe derken bu kart kademeyi HİÇ yayımlamıyor ve
        # çarkı TOPLAM yükle TEK kademe çözüyordu. On pompanın beşi radyal
        # bandın altındaydı (Ns 103 - 407 US) ve beşinin de kademe alanı
        # YOKTU. Bu, türbin tarafında P3B4-02 / Z5S-PK1'in kapattığı kusurun
        # pompa ikizidir: "kademe sayısı bir TASARIM KARARIDIR; iki blok iki
        # karar veremez" (tests/test_sivi_baglama_beyan.py).
        #
        # Kusurun sayısal izi ``impeller_diameter_ratio`` alanındaydı: kart
        # onu "tasarım olgunluğu göstergesi" diye yayımlıyor ama oran
        # ÖLÇÜLDÜĞÜNDE n'e bağlıydı (tek kademeli pompalarda 1,06-1,12;
        # 2 kademede 0,810; 3'te 0,671; 4'te 0,582; 6'da 0,477 — yani
        # 1,12/sqrt(n)). Modül çapı KADEME yükünden (H/n), kart çapı TOPLAM
        # yükten çözdüğü için oran iki modelin farkını değil sqrt(n)'i
        # ölçüyordu.
        #
        # ONARIM: karar modülün KENDİ kuralından (pump_stage_count) okunur —
        # burada ikinci bir kural yazılmaz — ve çark o kararın KADEME yüküyle
        # çözülür. Yayımlanan H-Q ve güç eğrileri POMPANIN eğrileridir, yani
        # kademe Euler yükünün n katı; tasarım noktasında değerleri
        # değişmez. Tek kademeli pompada (n = 1) zincir bit-aynı kalır.
        ns_overall = None
        # ÖH D33-2 · OH-FB-03 (Fable sivi-03): Ns ÇÖZÜLEMEZSE NEDENİ ADIYLA
        # saklanır. Eskiden üç girdiden hangisinin düştüğü hiçbir yerde
        # yazmıyordu; kart ``stage_count: null`` diyor ama çarkı yine TOPLAM
        # yükle TEK kademe çözüyordu — yani karar verilmemişken n = 1
        # SESSİZ VARSAYIMI uygulanıyordu (fail-closed ihlali, bekçisiz ayak).
        ns_eksik = []
        if not (q > 0.0):
            ns_eksik.append('volumetric_flow_m3_s (Q <= 0)')
        if not (head_total > 0.0):
            ns_eksik.append('total_head_m (H <= 0; with a cycle shaft power '
                            'this is design_head x the cycle power ratio)')
        if not (rpm > 0.0):
            ns_eksik.append('rotational_speed (rpm <= 0)')
        if not ns_eksik:
            _ns = rpm * m3s_to_gpm(q) ** 0.5 / m_to_ft(head_total) ** 0.75
            if np.isfinite(_ns):
                ns_overall = float(_ns)
            else:
                ns_eksik.append('specific_speed_us (Ns is not finite for '
                                'these inputs)')
        try:
            n_stages = (pump_stage_count(ns_overall)
                        if ns_overall is not None else None)
        except ValueError:                                 # pragma: no cover
            n_stages = None
            ns_eksik.append('stage_count (pump_stage_count rejected '
                            f'Ns = {ns_overall!r})')
        stage_not_resolved_reason = (
            None if n_stages else (
                'Stage count NOT decided on this run: '
                + '; '.join(ns_eksik or ['specific_speed_us could not be '
                                         'measured'])
                + '. The impeller geometry is therefore NOT published: '
                  'solving it would silently assume a single stage and '
                  'publish an impeller sized on the TOTAL head.'))
        ns_stage = (ns_overall * n_stages ** 0.75
                    if (ns_overall is not None and n_stages) else None)
        # Kademe yükü ÇARKI kuran yüktür. Kademe kararı çözülemediyse
        # (Ns ölçülemez) zincir eski tek kademeli hâline düşer ve kart
        # kademe alanlarını BOŞ bırakır — uydurma karar yayımlanmaz.
        head_stage = head / n_stages if n_stages else head
        if n_stages is None:
            stage_status = None
        elif ns_stage is not None and ns_stage < NS_CENTRIFUGAL_MIN_US:
            stage_status = 'below_band_at_stage_cap'
        elif ns_stage is not None and ns_stage > NS_CENTRIFUGAL_MAX_US:
            stage_status = 'above_centrifugal_band'
        else:
            stage_status = 'in_centrifugal_band'

        from scipy.optimize import brentq
        try:
            u2 = float(brentq(lambda u: head_of_u2(u) - head_stage,
                              1.0, 2000.0, xtol=1e-6))
        except Exception:
            # Kaymasız yaklaşık çözüm (ikinci dereceden terim baskın)
            u2 = float(np.sqrt(head_stage * g0 / (eta_h * slip)))
        d2 = 2.0 * u2 / omega
        a2 = np.pi * d2 ** 2 * PUMP_EXIT_WIDTH_RATIO

        stage_multiplier = n_stages if n_stages else 1
        # ÖH D33-2 · OH-FB-03 — ÇARK GEOMETRİSİ İKİ ŞARTA BAĞLIDIR.
        # (1) donanım uygulanabilir (NPSH kapıları) — D2x'te kuruldu;
        # (2) KADEME KARARI VERİLEBİLDİ. İkincisi eksikken çark yine
        # çözülüyordu: ``head_stage`` sessizce TOPLAM yüke düşüyor, yani
        # kart 'kademe sayısı: null' derken geometri n = 1 varsayıyordu.
        # Aynı yanıttaki ``turbopump_sizing`` bloğu kararsız kaldığında
        # boyutlandırmayı REDDEDİYOR; iki blok aynı pompa için zıt hüküm
        # veremez (OH-D27-02 deseninin ikinci ayağı).
        geometry_publishable = bool(hardware_feasible and n_stages)
        flow_ratios = np.linspace(PUMP_CURVE_FLOW_MIN, PUMP_CURVE_FLOW_MAX,
                                  PUMP_CURVE_POINTS)
        flow_range, head_curve, eff_curve, power_curve, npsh_curve = \
            [], [], [], [], []
        for fr in flow_ratios:
            q_i = q * fr
            # Bir KADEMENİN Euler yükü; pompanın yükü bunun n katıdır
            # (kademeler seri bağlı, aynı debiyi görür).
            h_stage_i = eta_h * (slip * u2 ** 2
                                 - u2 * q_i / (a2 * np.tan(beta2))) / g0
            h_i = stage_multiplier * h_stage_i
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
        if cycle_scale is not None:
            power_curve = [p * cycle_scale for p in power_curve]

        if cycle_scale is None:
            head_role = (
                'TOTAL head rise of this pump (dP/(rho*g) from the published '
                'pressure rise). The SINGLE-STAGE Euler head that sets the '
                'impeller geometry is stage_head_m = design_head / '
                f'stage_count (= {stage_multiplier} stage(s) here); with one '
                'stage the two are the same number. No cycle shaft power was '
                'supplied, so this is also total_head_m and rho*g*H*Q/eta '
                'equals design_power')
        else:
            head_role = (
                'TOTAL head rise of this pump, NOT the published '
                'design_power head and NOT the head of one impeller. The '
                'SINGLE-STAGE Euler head that sets the impeller geometry is '
                'stage_head_m = design_head / stage_count '
                f'(= {stage_multiplier} stage(s) here). The cycle power '
                'balance covers the whole pump and the total flow does not '
                'see the single-stage head rise, so the head that closes '
                'P = rho*g*H*Q/eta is total_head_m = design_head x '
                f'{cycle_scale:.4f} (cycle_power_to_single_stage_ratio). The '
                'ratio is below 1 when the cycle duty is lighter than the '
                'single-stage estimate and above 1 when it is heavier')
        power_identity_kw = (density * g0 * head_total * q
                             / (eta_bep * 1000.0))
        power_identity_residual_pct = (
            (power_design - power_identity_kw) / power_identity_kw * 100.0
            if power_identity_kw > 1e-12 else None)
        # B5: NPSH_gerekli emme özgül hızı tanımının TERSİDİR ve devir
        # derate'li seçildiği için NPSH_mevcut'tan FARKLIDIR: tavansız
        # tasarım noktasında oran derate^(4/3) (~0.869), yani ~%15 marj.
        # rpm tavana takıldıysa marj bu satırda otomatik yeniden hesaplanır
        # (düşük devir -> düşük NPSH_req -> daha büyük marj). Uyarı artık
        # ULAŞILABİLİR: NPSH_a <= 0 vakasında npsh_req > npsh_avail olur.
        npsh_req = ((omega * np.sqrt(max(q, 1e-12))
                     / PUMP_SUCTION_SPECIFIC_SPEED) ** (4.0 / 3.0)) / g0
        if npsh_req > npsh_avail:
            self._warn('warn.liquid.npsh_insufficient', 'critical',
                       npsh_required_m=round(float(npsh_req), 1),
                       npsh_available_m=round(float(npsh_avail), 1))
        if suction is not None and suction_dp_bar > 0:
            filter_share = suction['filters'] / suction_dp_bar * 100.0
            suction_basis = (
                'suction-side losses only: tank outlet '
                f'K={FEED_K_TANK_OUTLET:g} + line filter K={FEED_K_FILTER:g} '
                f'(an assumed clean-element estimate, {filter_share:.0f}% of '
                'the suction loss) + Darcy-Weisbach over the '
                f'{FEED_SUCTION_LINE_LENGTH_M:g} m suction run. '
                + FEED_SUCTION_LINE_BASIS)
        else:
            suction_basis = ('no feed-line data supplied to the pump design: '
                             'suction line loss taken as zero (declared, not '
                             'computed)')
        # ÖH D25 · OH-D24-12 (Fable-D19 bulgusu [53], P3B3-07 komşuluğu):
        # kart, özdeşliğini KURAN yoğunluğu yayımlamıyordu. ÖLÇÜLDÜ
        # (once.json ``OH-D24-12``): dört pompa kartının hiçbirinde adında
        # 'dens' geçen tek bir alan yok; P = ρ·g·H·Q/η dışarıdan
        # kurulamıyor, çünkü dört çarpandan biri kartta değil. Sonuç:
        # ``power_identity_residual_pct`` yapı gereği 0 çıkıyor (aynı ρ hem
        # payda hem paydada) ve kartı okuyanın elinde BAĞIMSIZ denetim
        # kalmıyordu — D19 bekçisi bile ρ'yu geri çözmek zorunda kalmıştı
        # ("Yoğunluk kartta yayımlanmıyor" notu, test_d19_sivi_a1.py:475).
        # ρ artık motorun TEK yoğunluk kaynağından (_propellant_density)
        # künyesiyle yayımlanır; uydurma yok, ikinci tanım yok.
        _rho_source = None
        if role in ('oxidizer', 'fuel'):
            _rho_single, _rho_source = self._propellant_density(role)
            if abs(float(_rho_single) - float(density)) > 1e-9:
                # İki farklı gerçek yayımlanmaz: kart HANGİ sayıyla
                # hesaplandığını söyler ve ayrışmayı adıyla bildirir.
                _rho_source = (
                    f'{_rho_source} (NOTE: the pump chain was called with '
                    f'{float(density):.6g} kg/m3 while the engine density '
                    f'source resolves to {float(_rho_single):.6g} kg/m3; the '
                    'published number is the one this card was computed '
                    'with)')
        return {
            'design_flow_rate': mdot,                     # kg/s
            'volumetric_flow_m3_s': q,
            # OH-D24-12: özdeşliğin dördüncü çarpanı.
            'fluid_density_kg_m3': float(density),
            'fluid_density_source': (
                _rho_source or
                'density passed to the pump design chain by the caller; the '
                'propellant role was not declared, so the engine density '
                'source could not be quoted'),
            'design_head': head,                          # m
            'design_efficiency': eta_bep * 100.0,          # %
            # P3B3-08: TEK tanım noktası (_read_overrides); künye kabul
            # kararından gelir, anahtarın varlığından değil.
            'efficiency_source': str(getattr(
                self, 'pump_efficiency_source',
                'default best-efficiency-point value')),
            'design_power': power_design,                 # kW
            'design_power_source': power_source,
            # P3B3-07: kartın kendi içinde kapanması için EKSİK olan üç alan.
            'design_head_role': head_role,
            'total_head_m': float(head_total),
            'total_head_basis': (
                'the head that, at this volumetric flow and efficiency, '
                'reproduces the published design_power. Without cycle '
                'scaling it equals design_head. It is the head of the WHOLE '
                'pump; one impeller raises stage_head_m of it.'),
            'cycle_power_to_single_stage_ratio': float(cycle_power_ratio),
            'power_identity_kW': float(power_identity_kw),
            'power_identity_residual_pct': (
                None if power_identity_residual_pct is None
                else float(power_identity_residual_pct)),
            'power_identity_basis': (
                'fluid_density_kg_m3*g*total_head_m*volumetric_flow_m3_s/'
                '(design_efficiency/100)/1000 - by construction this equals '
                'design_power, so the card closes. Using design_head (single '
                'stage) instead reproduces design_power only when '
                'cycle_power_to_single_stage_ratio == 1. Every factor of the '
                'identity is published on this card, so a reader can rebuild '
                'it WITHOUT back-solving any of them (OH-D24-12)'),
            'rotational_speed': rpm,                      # rpm
            'speed_source': speed_source,
            # ÖH defter P3B3-03: emme çözülemediğinde (NPSH_mevcut <= 0)
            # devir UYDURMA bir 1000 Pa giriş yükünden seçiliyor ve o devirle
            # çözülen çark METRELERCE çıkıyordu (ölçüldü: 250 kN'da 11,98 m;
            # F-1'in LOX çarkı ~0,4 m). Aynı yanıtta C1 boyutlandırma modülü
            # ('turbopump_sizing') tam bu gerekçeyle pompayı boyutlandırmayı
            # REDDEDİYOR (status='not_computed'). İki blok aynı pompa için
            # zıt hüküm veremez: donanım geometrisi artık uydurma tabandan
            # YAYIMLANMAZ (fail-closed). Taban devriyle ima edilen geometri
            # kaybolmuyor, AYRI adla ve künyesiyle duruyor.
            'impeller_tip_speed': (u2 if geometry_publishable else None),
            'impeller_diameter': (d2 if geometry_publishable else None),  # m
            'impeller_geometry_status': ('modelled' if geometry_publishable
                                         else 'not_computed'),
            'impeller_geometry_basis': (
                'Euler head with Stodola slip at the selected shaft speed, '
                'solved for stage_head_m (ONE stage of stage_count = '
                f'{stage_multiplier}), not for the whole pump head'
                if geometry_publishable else
                # ÖH D33-2 · OH-FB-03 — KARARSIZ KADEME = GEOMETRİ YOK.
                (stage_not_resolved_reason
                 + ' The figures a single-stage assumption would imply are '
                   'carried under impeller_*_if_inlet_head_floor and are NOT '
                   'a design.')
                if n_stages is None else
                ('NOT published: NPSH_available <= 0 at this tank pressure, '
                 'so the shaft speed is not defined by a suction limit and '
                 'no feasible impeller geometry exists. The figures the '
                 f'nominal {PUMP_NPSH_SPEED_FLOOR_PA:g} Pa inlet-head floor '
                 'would imply are carried under '
                 'impeller_*_if_inlet_head_floor and are NOT a design.')
                if not suction_feasible else
                ('NOT published: NPSH_available is positive but falls short '
                 f'of {NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE:g} x the '
                 'SP-8109 inlet '
                 'velocity-head requirement, so the pump would run cavitated '
                 'at the design point. The geometry the speed chain would '
                 'imply is carried under impeller_*_if_inlet_head_floor and '
                 'is NOT a design.')),
            'impeller_tip_speed_if_inlet_head_floor': (
                None if geometry_publishable else float(u2)),
            'impeller_diameter_if_inlet_head_floor': (
                None if geometry_publishable else float(d2)),
            'suction_feasible': bool(suction_feasible),
            'hardware_feasible': bool(hardware_feasible),
            'status': ('modelled' if hardware_feasible else 'not_feasible'),
            'status_basis': (
                'suction side solved: NPSH_available > 0, the SP-8109 inlet '
                'velocity-head requirement is met with the single-margin '
                f'factor {NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE:g}, and the '
                'shaft speed comes from the derated suction specific speed '
                'limit'
                if hardware_feasible else
                ('NPSH_available <= 0: the pump inlet total pressure does '
                 'not exceed the propellant vapour pressure after '
                 'suction-line losses; the pump would cavitate and this '
                 'design is NOT feasible at this tank pressure (same verdict '
                 'as turbopump_sizing for this pump)')
                if not suction_feasible else
                ('NPSH_available > 0 but below '
                 f'{NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE:g} x the SP-8109 '
                 'Sec. 3.2.1.2 '
                 'inlet velocity-head requirement: the inlet head clears the '
                 'vapour pressure but not the head the inlet flow itself '
                 'consumes, so the design is NOT feasible at this tank '
                 'pressure')),
            'slip_factor': slip,
            'npsh_available': npsh_avail,                 # m
            'npsh_available_basis': (
                'NPSH_a = (p_tank - dp_suction - p_vapor)/(rho*g) via '
                'hrma.analysis.turbopump_sizing.npsh_available_m (Eq. 1, '
                'single source with the C1 sizing chain). ' + suction_basis),
            'vapor_pressure_Pa': vapor_pa,
            'vapor_pressure_source': vapor_source,
            'suction_line_dp_bar': suction_dp_bar,
            'suction_loss_breakdown_bar': suction,
            'npsh_required': npsh_req,                    # m
            'npsh_required_basis': (
                'inverse of the suction specific speed definition at the '
                'selected shaft speed: NPSH_req = '
                '(omega*sqrt(Q)/omega_ss)^(4/3)/g. The speed is derated by '
                f'{SPEED_DERATE_DEFAULT:g} (SPEED_DERATE_DEFAULT, imported '
                'from turbopump_sizing) below the suction limit, so at the '
                'uncapped design point NPSH_req/NPSH_avail = '
                f'{SPEED_DERATE_DEFAULT:g}^(4/3) ~= '
                f'{SPEED_DERATE_DEFAULT ** (4.0 / 3.0):.3f} (~15% margin) - '
                'no longer equal by construction'),
            # --- F3 (ÖH D18 fizik-a2): SP-8109 giriş hız-yükü kuralı ------
            # Devir tabanlı marj (npsh_required) tasarım gereği
            # derate^(-4/3) = 1,155'e KİLİTLİDİR: mil devri zaten emme
            # sınırından seçildiği için o oran bir SINAMA değil, bir
            # ÖZDEŞLİKtir. Ölçüldü (once_f2f3.json): beş koşumun tüm
            # gerçeklenebilir pompalarında marj oranı 1,15083 ± 0 idi.
            # Bağımsız ve CANLI sınama SP-8109 §3.2.1.2 hız-yükü kuralıdır;
            # tank basıncı türetilmediğinde (kullanıcı basıncı, basınç
            # beslemeli çevrim) bu sınama GERÇEKTEN kırmızıya döner.
            'npsh_required_velocity_head_m': npsh_req_vh,
            'npsh_velocity_head_factor': npsh_vh_factor,
            'npsh_velocity_head_class': npsh_vh_class,
            'npsh_inlet_velocity_m_s': npsh_inlet_v,
            'npsh_velocity_head_status': npsh_vh_status,
            'npsh_velocity_head_basis': (
                'NPSH_req(inlet) = k_v * c_m^2/(2g) with c_m taken as the '
                'suction line velocity from the same Darcy chain that sets '
                'the suction loss (the pump inlet duct is not separately '
                'modelled, so the line velocity stands in for the impeller '
                'inlet meridional velocity - a declared approximation). '
                + NPSH_VELOCITY_HEAD_SOURCE + ' The verdict compares '
                'NPSH_available against '
                f'{NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE:g} x '
                'this requirement. ' + NPSH_SINGLE_MARGIN_CONTRACT
                + ' (The stacked ratio it replaces was: '
                + NPSH_MARGIN_FACTOR_SOURCE + ')'),
            'npsh_margin_factor': float(
                NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE),
            'npsh_margin_factor_basis': NPSH_SINGLE_MARGIN_CONTRACT,
            'tank_pressure_bar': float(tank_pressure_bar),
            'tank_pressure_source': self._tank_pressure_bar()[1],
            'suction_specific_speed_dimensionless': PUMP_SUCTION_SPECIFIC_SPEED,
            'suction_specific_speed_us': PUMP_SUCTION_SPECIFIC_SPEED_US,
            'suction_specific_speed_basis': (
                'dimensionless omega_ss '
                f'{PUMP_SUCTION_SPECIFIC_SPEED:g} (inducer-class rocket '
                'pump; Huzel & Huang Ch. 6) = '
                f'{PUMP_SUCTION_SPECIFIC_SPEED_US:.0f} US units '
                '(rpm*gpm^0.5/ft^0.75), derived through the exact unit '
                'bridge NSS_US_PER_OMEGA_SS (no second suction-capability '
                'literal). Against the turbopump_sizing bands this sits in '
                'the WITH-INDUCER class: above the no-inducer ceiling '
                f'({NSS_NO_INDUCER_MAX_US:.0f} US, read from '
                'turbopump_sizing - not written here), below the inducer '
                'design default (30000 US)'),
            # --- ÖH D27 / OH-D26-09 — DEVİR SEÇİMİNİ YARGILAYAN İKİ BANT --
            #
            # ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D27/sivi/a1/once.json``
            # OH-D26-09; 25 kN LOX/RP-1, Pc = 60 bar): mil devri emme
            # sınırının 0,90 katı olarak seçiliyor ve kart o devri
            # yayımlıyor, AMA devrin donanım sınıfı hakkında hiçbir YAPISAL
            # alan yayımlanmıyordu:
            #   * omega_ss = 8 -> 21864 US, yani indüsersiz tavanın (11000)
            #     iki katı: bu tasarım İNDÜSER İSTER. Alan ``inducer_required``
            #     kartta vardı ama HİÇ doldurulmuyordu (None), gerekliliği
            #     yalnız düzyazı söylüyordu.
            #   * ÖZGÜL DEVİR ölçüldü: yakıt pompası Ns = 922,8 US (radyal
            #     bandın 500-3000 ortası), oksitleyici pompası Ns = 407,4 US
            #     (bandın ALTINDA - modülün kendi künyesi "below ~500 the
            #     single-stage efficiency collapses and the head is split
            #     over more stages" diyor). Kart bunu da SÖYLEMİYORDU.
            #
            # Kalemin sorduğu soru ("yakıt devrinin YÖNÜ mü yanlış, yoksa
            # tavan mı bayat") bu iki ölçümle yanıtlanır: yakıt pompası
            # 52 711 rpm'de özgül devir bandının ORTASINDA ve çevresel hızı
            # 129 m/s (SP-125 s. 208: u2 tipik 200-1500 ft/s = 61-457 m/s;
            # KU-K1/SP-H1 K29 — eski metin "H&H'nin 200-400 m/s pratiği"), yani
            # devrin yönü bandın dışına çıkmıyor - eski 60 000 rpm tavanı
            # bir SAYI çapasıydı, fizik sınırı değil. Bağlayıcı kısıt
            # indüser gerekliliği ve oksitleyici tarafındaki kademe
            # sorusudur; ikisi de artık ADIYLA yayımlanır.
            'inducer_required': bool(
                PUMP_SUCTION_SPECIFIC_SPEED_US > NSS_NO_INDUCER_MAX_US),
            'inducer_required_basis': (
                'suction_specific_speed_us '
                f'{PUMP_SUCTION_SPECIFIC_SPEED_US:.0f} vs the no-inducer '
                f'ceiling {NSS_NO_INDUCER_MAX_US:.0f} US '
                '(hrma.analysis.turbopump_sizing, single source). '
                + NSS_SOURCE),
            'specific_speed_us': ns_overall,
            'specific_speed_band_status': _pump_ns_band_status(
                rpm, q, head_total),
            'specific_speed_basis': (
                'Ns = rpm*gpm^0.5/ft^0.75 at the published speed, flow and '
                'total head of THIS card (no second flow or head source). '
                f'Centrifugal band {NS_CENTRIFUGAL_MIN_US:.0f}-'
                f'{NS_CENTRIFUGAL_MAX_US:.0f} US read from '
                'hrma.analysis.turbopump_sizing. ' + NS_SOURCE),
            # --- ÖH D28 / OH-D27-02 — KADEME KARARI YAYIMLANIR ------------
            # Karar ``turbopump_sizing.pump_stage_count``tan gelir (tek
            # kaynak), bu yüzden aynı yanıttaki ``turbopump_sizing`` bloğu
            # ile bu kart aynı pompa için iki farklı kademe sayısı veremez.
            'stage_count': (int(n_stages) if n_stages else None),
            'stage_count_max': int(PUMP_STAGES_MAX),
            'stage_count_basis': (
                'smallest n with Ns_stage = specific_speed_us * n^0.75 >= '
                f'{NS_CENTRIFUGAL_MIN_US:.0f} US, capped at '
                f'{PUMP_STAGES_MAX} '
                '(hrma.analysis.turbopump_sizing.pump_stage_count - the same '
                'single rule the turbopump_sizing block applies, so the two '
                'blocks cannot decide differently about this pump). '
                + NS_SOURCE),
            'stage_head_m': (float(head_stage) if n_stages else None),
            'stage_head_basis': (
                'design_head / stage_count - the head ONE impeller raises. '
                'This is the head the Euler/Stodola geometry solve uses; the '
                'published impeller_tip_speed and impeller_diameter belong '
                'to a SINGLE stage, and head_curve/power_curve are the '
                'whole pump (stage_count x the stage Euler head).'),
            'specific_speed_per_stage_us': (
                float(ns_stage) if ns_stage is not None else None),
            'stage_count_status': stage_status,
            # ÖH D33-2 · OH-FB-03 — kararın VERİLEMEDİĞİ hâl de ADIYLA
            # yayımlanır; ``stage_count: null`` tek başına "neden" demez.
            'stage_count_not_resolved_reason': stage_not_resolved_reason,
            'stage_count_status_basis': (
                None if stage_status is None else
                ('per-stage specific speed '
                 f'{ns_stage:.0f} US stays below the centrifugal band '
                 f'minimum {NS_CENTRIFUGAL_MIN_US:.0f} even at the stage cap '
                 f'n={PUMP_STAGES_MAX}: the centrifugal head-coefficient / '
                 'Euler impeller model is OUTSIDE its validity range here '
                 '(declared, not silently extrapolated) - the same verdict '
                 'turbopump_sizing records for this pump'
                 if stage_status == 'below_band_at_stage_cap' else
                 'per-stage specific speed '
                 f'{ns_stage:.0f} US exceeds the centrifugal band maximum '
                 f'{NS_CENTRIFUGAL_MAX_US:.0f} US (mixed-flow/axial regime); '
                 'the centrifugal impeller model is outside its validity '
                 'range (declared, not silently extrapolated)'
                 if stage_status == 'above_centrifugal_band' else
                 'per-stage specific speed '
                 f'{ns_stage:.0f} US sits inside the centrifugal band '
                 f'{NS_CENTRIFUGAL_MIN_US:.0f}-{NS_CENTRIFUGAL_MAX_US:.0f} '
                 'US, which is the validity range of the impeller model '
                 'used here')),
            'flow_range': flow_range,
            'head_curve': head_curve,
            'efficiency_curve': eff_curve,
            'power_curve': power_curve,
            'npsh_curve': npsh_curve,
            'model': ('Euler head with Stodola slip solved per STAGE '
                      f'(stage_count = {stage_multiplier}); shaft speed set '
                      f'at {SPEED_DERATE_DEFAULT:g} x the suction specific '
                      'speed limit (real vapor pressure, suction-side line '
                      'losses); efficiency curve is an incidence-loss '
                      'model anchored at the BEP efficiency '
                      '(similarity-scaled estimate)'),
        }

    @staticmethod
    def _shaft_architecture_note(ox_pump, fuel_pump):
        """Mil mimarisi beyanı — B5 (v2.6.27).

        Yakıt ve oksitleyici pompa devirleri kendi emme sınırlarından ayrı
        ayrı seçilir ve genelde FARKLIDIR. Bu bir dişli kutusu / çift mil
        VARSAYIMIDIR ve eskiden hiçbir yerde beyan edilmiyordu: türbin
        sessizce oksitleyici pompa devrinde boyutlanırken yakıt pompası
        türbin milinden farklı hızda dönüyordu. Yeniden TASARLANMAZ; yalnız
        söylenir (yanlış beyan beyansızlıktan kötü, beyansızlık da yalandan
        yalnız bir adım geride).
        """
        rpm_ox = float(ox_pump['rotational_speed'])
        rpm_fuel = float(fuel_pump['rotational_speed'])
        if abs(rpm_ox - rpm_fuel) / max(rpm_ox, rpm_fuel, 1e-9) < 0.01:
            return (
                'single-shaft assumption: both pumps run at practically the '
                f'same suction-limited speed ({rpm_ox:.0f} rpm) and the '
                'turbine is sized on that shaft.')
        return (
            f'geared / dual-shaft assumption: the oxidizer pump runs at '
            f'{rpm_ox:.0f} rpm and the fuel pump at {rpm_fuel:.0f} rpm, each '
            'set by its own suction limit. The turbine is sized on the '
            'OXIDIZER pump shaft; the fuel pump is assumed to be driven '
            'through a gearbox or a separate shaft, and HRMA does not size '
            'that gearing.')

    def _feed_pipe_material(self):
        """(ad, kaynak) — besleme borusunun YAPISAL malzemesi (tek tanım).

        ÖH Z5S / defter P4B4-08. Bu ad ``materials_db`` anahtarıdır (Young
        modülü + hoop dayanımı); boru yüzey PÜRÜZLÜLÜĞÜ ayrı bir büyüklüktür
        ve motor onu EL KİTABI TABLOSUNDAN (``FEED_LINE_ROUGHNESS_M``,
        ticari çelik boru — White Tablo 6.1) verir; ölçüm DEĞİLDİR ve
        çağrıda ``roughness_provenance='handbook_table'`` ile öyle beyan
        edilir (ÖH D21 · P3B3-12). Su koçu bloğu
        ile vana/hat bütçesinin su koçu bağlaması AYNI adı okur; eskiden
        birincisi kullanıcının 'feed_line_material' girdisini, ikincisi
        valve_feedline'ın 'stainless_tubing' varsayılanını kullanıyordu ve
        aynı motorun yanıtında iki malzeme künyesi bulunuyordu.
        """
        secim = self.overrides.get('feed_line_material')
        ad = str(secim or WATER_HAMMER_DEFAULT_PIPE_MATERIAL).strip()
        kaynak = ('user input (feed line material)' if secim else
                  f"not supplied -> '{WATER_HAMMER_DEFAULT_PIPE_MATERIAL}' "
                  'assumed (HRMA does not model a line material choice)')
        return ad, kaynak

    def _feed_water_hammer_analysis(self, drops, tank_bar, pressure_fed):
        """Besleme hattı su koçu analizi — hrma.analysis.water_hammer ile.

        Yol haritası A6 (v2.6.27). Fizik künyesi: Joukowsky/Allievi toplu
        parametre su koçu (Wylie & Streeter, "Fluid Transients" 1978) +
        Michaud yavaş kapanma + kolon ayrılması denetimi; modül app.py
        /api/water-hammer ucunda ZATEN bağlıydı ama motorun kendi hat
        verisiyle hiç çağrılmıyordu.

        Girdi envanteri (KOD OKUNARAK çıkarıldı — hangileri gerçekten
        hesaplanıyor):
          - hat İÇ ÇAPI ve HIZI: hesaplanıyor (_calculate_line_diameter /
            _line_pressure_drops; drops sözlüğünün kendi değerleri),
          - hat UZUNLUĞU: FEED_LINE_LENGTH_DEFAULT_M — beyanlı yerleşim
            varsayımı (basınç düşümüyle AYNI tek tanım),
          - çalışma basıncı: hesaplanıyor (turbopompada pompa basma basıncı,
            basınç beslemelide tank basıncı),
          - boru CİDAR KALINLIĞI: HİÇBİR YERDE hesaplanmıyor -> kullanıcı
            girdisi (feed_line_wall_thickness [mm]); verilmezse hat bloğu
            NOT_MODELLED döner, sayı UYDURULMAZ,
          - vana KAPANMA SÜRESİ: hesaplanmıyor -> kullanıcı girdisi
            (valve_closure_time_ms); verilmezse analizör ANİ kapanma (tam
            Joukowsky, muhafazakâr üst sınır) varsayar ve bunu kendisi
            beyan eder (closure_regime alanı),
          - sıvı hacimsel modülü: yalnız FLUID_PROPERTIES tablosundaki
            iticiler için (WATER_HAMMER_FLUID_KEY); tablosuz itici hattı
            NOT_MODELLED döner.
        """
        wall_mm = self._override_val('feed_line_wall_thickness', 0.1, 50.0,
                                     'Feed line wall thickness', ' mm')
        closure_ms = self._override_val('valve_closure_time_ms', 0.1, 6e5,
                                        'Valve closure time', ' ms')
        pipe_material, pipe_material_source = self._feed_pipe_material()

        def _line_block(label, propellant, line, working_bar, rho):
            fluid_key = WATER_HAMMER_FLUID_KEY.get(str(propellant).lower())
            missing = []
            if fluid_key is None:
                missing.append(
                    f"no tabulated liquid bulk modulus for '{propellant}' "
                    '(water_hammer FLUID_PROPERTIES covers '
                    f'{sorted(WATER_HAMMER_FLUID_KEY)}); use /api/water-'
                    'hammer with bulk_modulus_Pa + density_kg_m3 for a '
                    'custom fluid')
            if wall_mm is None:
                missing.append(
                    'feed_line_wall_thickness [mm] not supplied - no feed-'
                    'line wall thickness is computed anywhere in HRMA (the '
                    'line is sized for flow velocity only), and the elastic-'
                    'pipe wave speed cannot be evaluated without it')
            if missing:
                return {
                    'status': 'NOT_MODELLED',
                    'basis': ('water-hammer transient not evaluated for '
                              'this line; inputs are not invented. '
                              + ' | '.join(missing)),
                    'required_inputs': (
                        ['feed_line_wall_thickness'] if wall_mm is None
                        else []),
                }
            try:
                from hrma.analysis.water_hammer import WaterHammerAnalyzer
                res = WaterHammerAnalyzer().analyze(
                    fluid=fluid_key,
                    line_length_m=FEED_LINE_LENGTH_DEFAULT_M,
                    line_id_mm=float(line['line_diameter_mm']),
                    wall_thickness_mm=float(wall_mm),
                    working_pressure_bar=float(working_bar),
                    flow_velocity_m_s=float(line['line_velocity_m_s']),
                    valve_closure_time_ms=closure_ms,
                    pipe_material=pipe_material,
                    density_kg_m3=float(rho))
            except Exception as exc:
                return {'status': 'not_computed',
                        'basis': ('water-hammer analysis rejected the '
                                  f'inputs: {exc}')}
            res = dict(res)
            if res.get('status') == WaterHammerAnalyzer.STATUS_UNSAFE:
                self._warn('warn.liquid.water_hammer_unsafe', 'critical',
                           line=label,
                           peak_bar=round(float(
                               res.get('design_peak_pressure_bar', 0.0)), 1),
                           yield_bar=round(float(
                               (res.get('pipe') or {})
                               .get('hoop_yield_pressure_bar', 0.0)), 1))
            res.update({
                'line': label,
                'line_length_basis': FEED_LINE_LENGTH_BASIS,
                'working_pressure_basis': (
                    'tank pressure (pressure-fed cycle)' if pressure_fed
                    else 'pump discharge pressure of this line (chamber '
                         'pressure + line/injector losses, or the cycle '
                         'balance solution when it converges)'),
                'flow_velocity_basis': (
                    'the SAME line velocity the Darcy-Weisbach feed '
                    'pressure-drop chain computes (mdot/(rho*A) at the '
                    'standard-rounded line diameter)'),
                'valve_closure_time_source': (
                    'user input (valve closure time)'
                    if closure_ms is not None else
                    'not supplied -> instantaneous closure assumed by the '
                    'analyser (full Joukowsky rise, conservative upper '
                    'bound); supply valve_closure_time_ms for the slow-'
                    'closure estimate'),
                'pipe_material_source': pipe_material_source,
                'density_source': ('engine propellant density (single '
                                   '_propellant_density source), not the '
                                   'fluid-table nominal'),
                'basis': (
                    'computed by hrma.analysis.water_hammer (Joukowsky/'
                    'Allievi + Michaud slow closure + column-separation '
                    'check) with the line diameter, velocity and working '
                    'pressure of THIS engine; the same analyser serves '
                    '/api/water-hammer'),
            })
            return res

        ox_working = (tank_bar if pressure_fed
                      else drops['pump_discharge_pressure_ox'])
        fuel_working = (tank_bar if pressure_fed
                        else drops['pump_discharge_pressure_fuel'])
        return {
            'oxidizer_line': _line_block('oxidizer_line', self.oxidizer_type,
                                         drops['oxidizer_line'], ox_working,
                                         self.rho_ox),
            'fuel_line': _line_block('fuel_line', self.fuel_type,
                                     drops['fuel_line'], fuel_working,
                                     self.rho_fuel),
            'model': ('Joukowsky/Allievi feed-line water hammer '
                      '(hrma.analysis.water_hammer); per-line evaluation at '
                      'the main valve'),
        }

    @staticmethod
    def _feed_fluid_record(propellant):
        """(anahtar, kayıt) — besleme akışkanının kaynak künyeli özellikleri.

        Tek kaynak: A6 su koçu bağlamasının kullandığı AYNI tablo
        (hrma.analysis.water_hammer.FLUID_PROPERTIES). Tabloda yoksa
        (None, None) döner ve çağıran NOT_MODELLED beyanı üretir — buhar
        basıncı UYDURULMAZ.
        """
        key = FEED_FLUID_PROPERTY_KEY.get(str(propellant).lower())
        if key is None:
            return None, None
        try:
            from hrma.analysis.water_hammer import FLUID_PROPERTIES
        except Exception:                                  # pragma: no cover
            return None, None
        return key, FLUID_PROPERTIES.get(key)

    def _turbopump_sizing_block(self, drops, tank_bar, pressure_fed,
                                ox_pump, fuel_pump, turbine_card,
                                cycle_solution):
        """Turbopompa boyutlandırma zinciri — hrma.analysis.turbopump_sizing.

        Yol haritası C1 (v2.6.27). Çevrim güç dengesi ṁ, ΔP, verim ve mil
        gücünü zaten veriyordu; bu modül eksik kalan boyutlandırma zincirini
        kapatır: NPSH_mevcut -> emme özgül devri -> ÖZGÜL DEVİR Ns ->
        KADEME SAYISI -> çark çapı (baş katsayısı) -> indüser gereksinimi ->
        NPSH_gerekli ve MARJ; türbinde ortalama çap + kademe sayısı.

        TEK KAYNAK KARARLARI (iki farklı doğru üretmemek için)
        ------------------------------------------------------
        * MİL DEVRİ modüle SEÇTİRİLMEZ, motorun kendi pompa zincirinden
          (``_design_pump``: Euler baş + Stodola kayma, devir emme özgül
          hızı sınırının SPEED_DERATE_DEFAULT katından — B5) GEÇİLİR. Aksi
          hâlde aynı yanıtta iki farklı devir bulunurdu. Modülün emme
          sınırlı üst devri yalnız KARŞILAŞTIRMA olarak yayımlanır; motor
          devri artık o üst devrin derate katı olduğu için ikisi tutarlıdır
          (bekçi: test_devir_emme_sinirinin_derate_katidir). Emme kabiliyeti
          hedefi de motorun TEK tanımından geçirilir
          (PUMP_SUCTION_SPECIFIC_SPEED_US) — modül 30000 US varsayılanıyla
          ikinci bir NPSH_gerekli üretemez.
        * ÇARK ÇAPI iki modelde de çıkar (motorda Euler/Stodola, modülde
          baş katsayısından). İkisi de raporlanır ve oranı verilir; hangisinin
          hangi modelden geldiği alan adında yazılıdır. Sessizce birinin
          diğerinin yerine geçmesi yasak.
        * TÜRBİN bir kez boyutlandırılır (ortak mil): pompa başına ikinci bir
          türbin raporlanmaz.

        GİRDİ ENVANTERİ (kod okunarak):
          - ṁ, ΔP, yoğunluk, hat kaybı: HESAPLANIYOR (çevrim çözümü +
            Darcy-Weisbach hat zinciri),
          - tank basıncı: turbopompada NPSH tankı varsayımı
            (PUMP_TANK_PRESSURE_DEFAULT_BAR), basınç beslemelide kullanıcı
            girdisi — ikisi de beyanlı,
          - buhar basıncı: HESAPLANMIYOR -> water_hammer FLUID_PROPERTIES
            kaynak künyeli tablosu (A6 ile tek kaynak); tablosuz itici
            NOT_MODELLED,
          - türbin gücü/debisi/verimi: çevrim çözümünden (kapanmadıysa
            motorun izentropik türbin kartından).
        """
        basis = (
            'pump and turbine sizing chain from hrma/analysis/'
            'turbopump_sizing.py (Huzel & Huang, NASA SP-125 Ch. 6; Sutton & '
            'Biblarz 9th ed. Ch. 10): NPSH_available -> suction specific '
            'speed -> specific speed Ns -> stage count -> impeller diameter '
            'from the head coefficient -> inducer requirement -> NPSH '
            'required and margin; turbine mean diameter and stage count from '
            'the equal-work impulse relations. Every driving input is THIS '
            "run's solver value; the shaft speed is NOT re-selected by the "
            'module but taken from the engine pump design chain (single '
            'source).')
        if pressure_fed or getattr(self, 'feed_system_type',
                                   'turbopump') != 'turbopump':
            return {
                'status': 'NOT_APPLICABLE',
                '_basis': basis,
                'reason': ('pressure-fed feed system: there is no pump and no '
                           'turbine to size in this engine.'),
            }
        try:
            from hrma.analysis.turbopump_sizing import (
                size_pump, size_turbine)
        except Exception as exc:                           # pragma: no cover
            return {'status': 'NOT_MODELLED', '_basis': basis,
                    'reason': f'turbopump_sizing module unavailable: {exc}'}

        # B5 (v2.6.27): hat kaybı yalnız EMME tarafıdır — motorun kendi pompa
        # zinciriyle (_design_pump) AYNI _suction_line_dp yardımcısı okunur;
        # iki yer tek emme kümesini görür. Eskiden buradan hattın TAMAMI
        # (ana vana + 2,5 m dirsekli koşu dahil) düşülüyordu ve 25 kN
        # örneğinde yakıt pompası NPSH_a = -14,4 m çıkıyordu; ana vana ve
        # dirsekli koşu pompanın BASMASINDADIR.

        def _pump_block(label, propellant, line, pump, discharge_bar, rho):
            fluid_key, record = self._feed_fluid_record(propellant)
            if record is None or record.get('vapor_pressure_Pa') is None:
                return {
                    'status': 'NOT_MODELLED',
                    'required_inputs': ['vapor_pressure'],
                    'basis': (
                        'the NPSH chain needs the propellant vapour '
                        f"pressure and HRMA does not solve it for "
                        f"'{propellant}'; the tabulated feed-fluid record "
                        f'covers {sorted(FEED_FLUID_PROPERTY_KEY)} only. No '
                        'vapour pressure is invented in its place.'),
                }
            dp_line_bar = float(self._suction_line_dp(line, rho)['total'])
            pressure_rise_pa = (float(discharge_bar) - float(tank_bar)) \
                * PA_PER_BAR
            if pressure_rise_pa <= 0.0:
                return {
                    'status': 'not_computed',
                    'basis': ('pump pressure rise is not positive '
                              f'({pressure_rise_pa:.0f} Pa): the tank already '
                              'delivers the required discharge pressure, so '
                              'no pump is sized.'),
                }
            try:
                res = size_pump(
                    mass_flow_kg_s=float(pump['design_flow_rate']),
                    pressure_rise_Pa=pressure_rise_pa,
                    density_kg_m3=float(rho),
                    vapor_pressure_Pa=float(record['vapor_pressure_Pa']),
                    tank_pressure_Pa=float(tank_bar) * PA_PER_BAR,
                    line_pressure_drop_Pa=dp_line_bar * PA_PER_BAR,
                    shaft_speed_rpm=float(pump['rotational_speed']),
                    # B5: emme kabiliyeti motorun TEK tanımından (boyutsuz
                    # Ω_ss=8'in kesin birim köprüsüyle US karşılığı). Aksi
                    # hâlde modül 30000 US varsayılanıyla İKİNCİ bir NPSH_req
                    # üretirdi (aynı yanıtta iki farklı gerçek).
                    target_suction_specific_speed_us=(
                        PUMP_SUCTION_SPECIFIC_SPEED_US))
            except Exception as exc:
                return {'status': 'not_computed',
                        'basis': ('turbopump_sizing rejected the inputs: '
                                  f'{exc}')}
            res = dict(res)
            d2_module = (res.get('pump') or {}).get('impeller_diameter_m')
            # F3 (ÖH D18 fizik-a2): motor zinciri çapı hükmü KAZANMADIYSA
            # (NPSH fail-closed) None yayımlar; burada float() ona çarpıp
            # bütün /calculate_liquid isteğini 400'e düşürüyordu. Ölçüldü:
            # F-1 sınıfı (6 770 kN) koşumu bu satırda TypeError veriyordu.
            _d2_ham = pump.get('impeller_diameter')
            d2_engine = (float(_d2_ham) if isinstance(_d2_ham, (int, float))
                         else None)
            res.update({
                'pump_label': label,
                'shaft_speed_source': (
                    'the engine pump design chain (_design_pump: Euler head '
                    'with Stodola slip, speed set at SPEED_DERATE_DEFAULT x '
                    'the suction specific speed limit and capped at the '
                    'practical rpm limit). The module did NOT re-select it, '
                    'so this answer carries a single shaft speed; the '
                    'suction capability target below is the SAME engine '
                    'omega_ss=8 through the exact unit bridge, so NPSH_req '
                    'is also single-source.'),
                'vapor_pressure_Pa': float(record['vapor_pressure_Pa']),
                'vapor_pressure_reference_K': record.get(
                    'vapor_pressure_ref_K'),
                'vapor_pressure_source': record.get('vapor_pressure_source'),
                'tank_pressure_bar': float(tank_bar),
                # F3: künye artık sabit metin DEĞİL, _tank_pressure_bar'ın
                # kendi kararının künyesi (NPSH'ten türetildiyse öyle der).
                'tank_pressure_source': self._tank_pressure_bar()[1],
                'line_pressure_drop_bar': dp_line_bar,
                'line_pressure_drop_basis': (
                    'SUCTION-side items of THIS engine only (single source '
                    'with the engine pump chain, _suction_line_dp): tank '
                    f'outlet K={FEED_K_TANK_OUTLET:g} + line filter '
                    f'K={FEED_K_FILTER:g} (assumed clean-element estimate) '
                    '+ Darcy-Weisbach over the '
                    f'{FEED_SUCTION_LINE_LENGTH_M:g} m suction run. The '
                    'main valve, the elbowed discharge run and the injector '
                    'drop are downstream of the pump and are excluded. '
                    + FEED_SUCTION_LINE_BASIS),
                'impeller_diameter_head_coefficient_m': d2_module,
                'impeller_diameter_euler_stodola_m': d2_engine,
                'impeller_diameter_note': (
                    'TWO INDEPENDENT ESTIMATES, deliberately both reported: '
                    'the head-coefficient estimate (psi = g*H_stage/u2^2, '
                    'Huzel & Huang Ch. 6) and the engine chain Euler head '
                    'with Stodola slip. They are different models of the '
                    'same impeller and neither silently replaces the other; '
                    'their ratio is a design-maturity indicator. ÖH D28 / '
                    'OH-D27-02: both are now solved for ONE stage at the '
                    'SAME stage_count, so the ratio measures the model '
                    'difference alone. Until D28 the engine chain solved '
                    'the WHOLE pump head with a single impeller, which made '
                    'this ratio scale as 1/sqrt(stage_count) (measured over '
                    'ten pump cards: 1.06-1.12 at n=1 but 0.810 / 0.671 / '
                    '0.582 / 0.477 at n = 2 / 3 / 4 / 6) - it was reading '
                    'the stage count, not the models.'),
                'impeller_diameter_ratio': (
                    float(d2_module) / d2_engine
                    if (d2_module and d2_engine and d2_engine > 0)
                    else None),
                'status': 'modelled',
            })
            return res

        ox = _pump_block('oxidizer_pump', self.oxidizer_type,
                         drops['oxidizer_line'], ox_pump,
                         drops['pump_discharge_pressure_ox'], self.rho_ox)
        fuel = _pump_block('fuel_pump', self.fuel_type,
                           drops['fuel_line'], fuel_pump,
                           drops['pump_discharge_pressure_fuel'],
                           self.rho_fuel)

        # --- Türbin: ortak mil, TEK kez boyutlandırılır -------------------
        #
        # ÖH D25 · OH-D24-14 (Fable-D19 bulgusu [58]). Ön süzgeç aynı kuralı
        # İKİNCİ KEZ, üstelik FARKLI sınırlarla yazıyordu: burada
        # ``0,0 < eta <= 1,0``, boyutlandırma modülünde
        # ``TURBINE_EFFICIENCY_VALID = (0,10, 1,00)``. ÖLÇÜLDÜ (once.json
        # ``OH-D24-14``, 250 kN/150 bar staged, çevrim verimi 0,05'e
        # çekildi): motor değeri KABUL ediyor, ``eta_source``a "cycle power
        # balance solution" yazıyor, sonra modül aynı sayıyı reddediyor ve
        # türbin kartının tamamı ``not_computed`` oluyordu — üstelik
        # gerekçe "turbine sizing rejected the inputs" diyerek suçu
        # boyutlandırmaya atıyor, sayının ÇEVRİMDEN geldiğini hiçbir yerde
        # söylemiyordu (``turbine_efficiency_source`` = None).
        #
        # Band artık TEK yerden gelir. Bandın DIŞINDA sayısal bir çevrim
        # verimi model hatasıdır (modülün künyesi: "altındaki değer türbin
        # değil model hatasıdır"): motor onun yerine kendi varsayılanını
        # koyup türbini boyutlandırmaz — bu sessiz ikame olurdu — kartı
        # ADIYLA geri çeker. Çevrim hiç verim yayımlamadıysa (None / sayı
        # değil) davranış değişmez: motor varsayılanı, künyesiyle.
        turbine = None
        eta_turb = TURBINE_EFFICIENCY_DEFAULT
        eta_source = (f'engine default turbine efficiency '
                      f'({TURBINE_EFFICIENCY_DEFAULT:g})')
        eta_rejected_basis = None
        _eta_lo, _eta_hi = TURBINE_EFFICIENCY_VALID
        shafts = (cycle_solution or {}).get('shafts') or []
        if (cycle_solution or {}).get('status') == 'converged' and shafts:
            eta_cyc = (shafts[0].get('turbine') or {}).get('efficiency')
            if isinstance(eta_cyc, (int, float)):
                if _eta_lo <= float(eta_cyc) <= _eta_hi:
                    eta_turb = float(eta_cyc)
                    eta_source = (
                        'cycle power balance solution (the efficiency the '
                        'converged shaft turbine actually used)')
                else:
                    eta_rejected_basis = (
                        f'the converged cycle power balance published a '
                        f'turbine efficiency of {float(eta_cyc):g}, which is '
                        f'outside the validity band '
                        f'{TURBINE_EFFICIENCY_VALID} of '
                        'hrma.analysis.turbopump_sizing (single source). A '
                        'value below the band is a model error, not a '
                        'turbine, so NO turbine geometry is estimated here '
                        'and the engine default is NOT substituted for it - '
                        'that substitution would publish a turbine that has '
                        'nothing to do with the solved cycle.')
        p_turb_w = float(turbine_card.get('power_output') or 0.0) * 1000.0
        mdot_turb = float(turbine_card.get('mass_flow_rate') or 0.0)
        if eta_rejected_basis is not None:
            turbine = {'status': 'not_computed',
                       'turbine_efficiency': None,
                       'turbine_efficiency_source': (
                           'REJECTED: ' + eta_rejected_basis),
                       'basis': eta_rejected_basis}
        elif p_turb_w > 0.0 and mdot_turb > 0.0:
            try:
                turbine = size_turbine(
                    shaft_speed_rpm=float(ox_pump['rotational_speed']),
                    power_W=p_turb_w,
                    mass_flow_kg_s=mdot_turb,
                    efficiency=eta_turb,
                    pump_tip_speed_m_s=float(ox_pump['impeller_tip_speed']))
                turbine = dict(turbine)
                turbine.update({
                    'status': 'modelled',
                    'shaft_speed_rpm': float(ox_pump['rotational_speed']),
                    'turbine_efficiency': eta_turb,
                    'turbine_efficiency_source': eta_source,
                    'power_source': turbine_card.get('model'),
                    'shaft_assumption': (
                        'single shaft: the turbine is sized at the OXIDIZER '
                        'pump speed with that pump\'s impeller tip speed as '
                        'the pitch-speed envelope. Multi-shaft architectures '
                        'are reported by the cycle power balance, not here.'),
                })
            except Exception as exc:
                turbine = {'status': 'not_computed',
                           'basis': f'turbine sizing rejected the inputs: '
                                    f'{exc}'}
        else:
            turbine = {
                'status': 'NOT_MODELLED',
                'required_inputs': ['turbine_power', 'turbine_mass_flow'],
                'basis': ('the turbine power and mass flow of this run are '
                          'not both positive, so no turbine geometry is '
                          'estimated (nothing is invented in their place).'),
            }
        return {
            'status': 'modelled',
            '_basis': basis,
            'oxidizer_pump': ox,
            'fuel_pump': fuel,
            'turbine': turbine,
        }

    @staticmethod
    def _reconcile_turbine_geometry(turbine_card, sizing_turbine):
        """Türbin kartının geometrisini boyutlandırma modülünden okutur.

        ÖH defter **P3B4-02** (Z5S/PK1). ÖLÇÜLDÜ (10 kN / Pc=100): aynı
        yanıtta ``turbopump_analysis.turbine`` U = 615,4852 m/s (tek kademeli
        U/C0 optimumu) ve N = 36265,5701 rpm yayımlıyordu — ima edilen
        ortalama çap D = 60U/(piN) = 0,32418 m; ``turbopump_sizing.turbine``
        ise AYNI devirde D = 0,06719 m (4,824x) diyordu. Üstelik kart
        ``'Single-stage axial'`` derken boyutlandırma bloğu 3 kademe +
        ``pressure_compounded_impulse_equal_work`` yayımlıyordu: tek yanıtta
        aynı türbin hem tek hem üç kademeliydi.

        Bu bir "iki bağımsız kestirim" durumu DEĞİLDİR: kademe sayısı bir
        TASARIM KARARIDIR ve kartın 615 m/s'lik tek kademeli hızı zaten
        yapısal çevre hızı sınırının (TURBINE_TIP_SPEED_LIMIT_MS) üstünde,
        yani kartın kendi modeli o noktada geçerli değil. Karar veren model
        ``hrma.analysis.turbopump_sizing.size_turbine``'dir (işi kademelere
        böler, çevre hızını min(yapısal sınır, pompa çark uç hızı) zarfının
        altına indirir), dolayısıyla YAYIMLANAN geometri oradan gelir.

        Kartın kendi tek kademeli kestirimi silinmez: ayrı adla
        (``blade_speed_single_stage_optimum_m_s``) ve künyesiyle durur.
        Modül geometri üretemediyse (NOT_MODELLED / not_computed) karta
        dokunulmaz ve bu durum ``blade_tip_speed_basis`` ile söylenir —
        uydurma geometri konmaz (fail-closed).

        ÖH D15 BİRLEŞME ETKİLEŞİMİ (1 Eylül 2026) — KARAR ⟷ TÜREV AYRIMI
        ----------------------------------------------------------------
        Yapısal-sistem kulvarının **P5B3-04** onarımı, kademe sayısı tavana
        kırpıldığında ``mean_diameter_m``i GERİ ÇEKİYOR (``None``): o durumda
        ``u_pitch = u_env`` olduğu için ``D = 60·U/(pi·N)`` yalnız dışarıdan
        gelen zarfı tekrar eder (ölçüldü: üç motorda da pompa çark çapına
        bağıl fark 0,0). Bu doğrudur ve KORUNUR.

        Ama bu metot ÇAPI geçerlilik ÖN KOŞULU sayıyordu: çap geri çekilince
        kartın tamamı ``not_sized`` dalına düşüyor, kademe sayısı ve pitch
        hızı da atılıyordu. ÖLÇÜLDÜ (birleşik ana ağaç, 10 kN / Pc=100):
        boyutlandırma 3 kademe · 127,5766 m/s yayımlarken kart
        ``'Single-stage axial'`` · **747,9283 m/s** diyordu — yani P3B4-02'nin
        kapattığı kusur (tek yanıtta iki kademe sayısı ve iki çevre hızı,
        üstelik kartınki yapısal sınırın üstünde) geri gelmişti;
        ``warn.liquid.turbine_tip_speed_exceeded`` de o kestirimden yeniden
        ateşleniyordu.

        Ayrım şudur: **kademe sayısı ve pitch hızı KARARDIR** — boyutlandırma
        modülü onları kırpılmış hâlde de yayımlar ve ``validity`` ile beyan
        eder; **ortalama çap o kararın TÜREVİDİR** ve kendi geçerlilik hükmünü
        taşır. Kart artık kararı her hâlükârda modülden okur; çapı modül
        yayımladıysa yayımlar, geri çektiyse **aynı hükmü** verir
        (``mean_diameter_m = None`` + ``mean_diameter_status='withheld_by_
        sizing'`` + modülün KENDİ gerekçe metni). Böylece iki blok ya aynı
        sayıyı ya da aynı "geri çekildi" hükmünü verir, ikisi de tek kaynaktan.
        """
        if not isinstance(turbine_card, dict):
            return turbine_card
        blok = sizing_turbine if isinstance(sizing_turbine, dict) else {}
        d_mean = blok.get('mean_diameter_m')
        u_pitch = blok.get('pitch_speed_m_s')
        n_stage = blok.get('stage_count')

        def _sayi(x):
            return isinstance(x, (int, float)) and not isinstance(x, bool)

        # KARAR: kademe sayısı + pitch hızı. Çap bunun TÜREVİDİR, ön koşulu
        # DEĞİLDİR (yukarıdaki birleşme notu).
        karar_var = (blok.get('status') == 'modelled'
                     and _sayi(u_pitch)
                     and isinstance(n_stage, int) and n_stage >= 1
                     and float(u_pitch) > 0.0)
        if not karar_var:
            turbine_card['blade_tip_speed_basis'] = (
                'single-stage optimum velocity ratio estimate of THIS card '
                '(U = ' f'{TURBINE_VELOCITY_RATIO:g}' ' x C0). The turbopump '
                'sizing block produced no turbine geometry for this run, so '
                'no sized pitch speed or mean diameter is published here; '
                'nothing is invented in their place.')
            turbine_card['geometry_source'] = 'not_sized'
            # ÖH D21 · P3B4-04: geometri çözülmediğinde 'type' kartın KENDİ
            # tek kademeli kestirimidir; boyutlandırma modülünün kararı
            # DEĞİLDİR. Künye o zaman da sayının yanında durur — kademe
            # kararı yayımlandığında (aşağıda) künye modüle geçer.
            turbine_card['type_source'] = (
                "this card's own single-stage assumption: the turbopump "
                'sizing block produced no turbine geometry for this run, so '
                'no stage count is read from it and none is invented here '
                '(see geometry_source).')
            turbine_card['mean_diameter_m'] = None
            turbine_card['mean_diameter_status'] = 'not_sized'
            turbine_card['mean_diameter_basis'] = (
                'the turbopump sizing block produced no turbine geometry for '
                'this run (see geometry_source); no mean diameter is invented '
                'here.')
            return turbine_card

        cap_var = _sayi(d_mean) and float(d_mean) > 0.0
        # Çap geri çekildiyse GEREKÇE modülün KENDİ kaydından okunur: iki blok
        # için iki ayrı metin yazılmaz (tek kaynak).
        cap_gerekce = None
        for kayit in (blok.get('validity') or []):
            if (isinstance(kayit, dict)
                    and kayit.get('field') == 'turbine_mean_diameter'):
                cap_gerekce = kayit.get('message')
                break

        duzen = str(blok.get('arrangement') or '')
        turbine_card['stage_count'] = int(n_stage)
        turbine_card['arrangement'] = duzen or None
        turbine_card['mean_diameter_m'] = (float(d_mean) if cap_var else None)
        turbine_card['mean_diameter_status'] = ('published' if cap_var
                                                else 'withheld_by_sizing')
        turbine_card['mean_diameter_basis'] = (
            'turbopump_sizing.turbine.mean_diameter_m, read at the same shaft '
            'speed, so the two blocks cannot disagree about the same turbine.'
            if cap_var else
            (cap_gerekce
             or 'turbopump_sizing withheld the turbine mean diameter for this '
                'run; this card publishes the SAME verdict instead of a '
                'second, invented diameter.'))
        turbine_card['blade_tip_speed'] = float(u_pitch)
        turbine_card['blade_tip_speed_basis'] = (
            'pitch-line blade speed of the SIZED turbine '
            '(turbopump_sizing.turbine.pitch_speed_m_s); the mean diameter '
            'published here is that block\'s D = 60U/(pi N) at the same '
            'shaft speed, so the two blocks cannot disagree about the same '
            'turbine.'
            if cap_var else
            'pitch-line blade speed of the SIZED turbine '
            '(turbopump_sizing.turbine.pitch_speed_m_s). That block WITHHELD '
            'the mean diameter for this run (see mean_diameter_basis) and '
            'this card publishes the same verdict: the stage count and the '
            'pitch speed are the sizing decision and are published, the '
            'diameter is not re-derived here.')
        turbine_card['geometry_source'] = (
            'hrma.analysis.turbopump_sizing.size_turbine (single source for '
            'turbine stage count, pitch speed and mean diameter)')
        if int(n_stage) <= 1:
            turbine_card['type'] = 'Single-stage axial impulse'
        else:
            turbine_card['type'] = (
                f'{int(n_stage)}-stage axial impulse'
                + (f' ({duzen})' if duzen else ''))
        turbine_card['type_source'] = turbine_card['geometry_source']
        return turbine_card

    def _valve_feedline_block(self, drops, tank_bar, pressure_fed):
        """Besleme hattı bütçesi + ana vana Cv — hrma.analysis.valve_feedline.

        Yol haritası C2 (v2.6.27). Hat geometrisi motorun kendisinindir
        (A6 su koçu bağlamasıyla AYNI kaynak): çap akış hızı hedefinden
        boyutlanır, uzunluk FEED_LINE_LENGTH_DEFAULT_M beyanlı yerleşim
        varsayımıdır, yerel kayıp katsayıları motorun kendi Crane TP-410
        kalemleridir ve buraya ``extra_loss_coefficient`` olarak AYNEN
        geçirilir (çift sayma yok, ikinci bir hat modeli kurulmaz).

        Vana hattın SONUNDADIR: giriş basıncı hat çıkış basıncıdır. Vana
        basınç düşümü motorun kendi ana vana kalemidir (K = 0.15 x dinamik
        basınç). Kavitasyon taraması iticinin KRİTİK basıncını da ister;
        HRMA onu hesaplamaz, bu yüzden modül taramayı yapmaz ve bunu kendi
        beyanıyla söyler — sessiz 'güvenli' verilmez.
        """
        basis = (
            'steady feed-line pressure budget and main-valve Cv/Kv sizing '
            'from hrma/analysis/valve_feedline.py (Darcy-Weisbach with the '
            'Haaland friction factor, Crane TP-410 equivalent-length local '
            'losses, ISA-75.01.01 / IEC 60534-2-1 liquid valve sizing). Line '
            'diameter, velocity, roughness, length and the local loss '
            "coefficients are THIS engine's own feed chain values, so this "
            'budget cannot disagree with the pressure drops reported '
            'elsewhere in the same answer.')
        try:
            from hrma.analysis.valve_feedline import analyze_valve_feedline
        except Exception as exc:                           # pragma: no cover
            return {'status': 'NOT_MODELLED', '_basis': basis,
                    'reason': f'valve_feedline module unavailable: {exc}'}

        wall_mm = self._override_val('feed_line_wall_thickness', 0.1, 50.0,
                                     'Feed line wall thickness', ' mm')
        closure_ms = self._override_val('valve_closure_time_ms', 0.1, 6e5,
                                        'Valve closure time', ' ms')
        # Su koçu bloğuyla AYNI tek tanım (P4B4-08): yapısal boru malzemesi
        # materials_db anahtarıdır; pürüzlülük ayrıca ÖLÇÜYLE verilir.
        pipe_material, pipe_material_source = self._feed_pipe_material()
        # Motorun kendi yerel kayıpları (ana vana HARİÇ — o vananın kendisi).
        k_extra = (FEED_K_TANK_OUTLET + FEED_K_FILTER
                   + FEED_ELBOW_COUNT * FEED_K_ELBOW)

        def _line_block(label, propellant, line, mdot, rho, mu, mu_user,
                        working_bar):
            fluid_key, record = self._feed_fluid_record(propellant)
            vapor_pa = (None if record is None
                        else record.get('vapor_pressure_Pa'))
            try:
                res = analyze_valve_feedline(
                    mass_flow_kg_s=float(mdot),
                    density_kg_m3=float(rho),
                    viscosity_Pa_s=float(mu),
                    line_id_m=float(line['line_diameter_mm']) / 1000.0,
                    line_length_m=FEED_LINE_LENGTH_DEFAULT_M,
                    inlet_pressure_Pa=float(working_bar) * PA_PER_BAR,
                    valve_pressure_drop_Pa=float(line['main_valve'])
                    * PA_PER_BAR,
                    wall_thickness_m=(None if wall_mm is None
                                      else float(wall_mm) / 1000.0),
                    # ÖH Z5S / defter P4B4-07 + P5B3-02 DÜZELTMESİ: burada
                    # eskiden ``fluid=(fluid_key or 'water')`` yazıyordu.
                    # Besleme akışkan haritası 9 iticinin yalnız 2'sini
                    # (lox, rp1) kapsıyor; kalan 7'si için hattın etiketi
                    # SESSİZCE 'water' oluyordu. Aynı yanıtın çözücü ayağı
                    # o itici için NOT_MODELLED derken bu blok su etiketi
                    # yayımlıyordu; ölçüldü (LH2, rho 70,8 kg/m3): etiketin
                    # tablo yoğunluğuyla aynı hattın debisi 14,096 kat,
                    # Joukowsky artışı 11,33 kat sapıyordu. Etiket artık
                    # UYDURULMAZ: harita boşsa None gider ve modül su koçu
                    # bağlamasını üretmeyip sebebini adıyla beyan eder.
                    fluid=fluid_key,
                    roughness_m=FEED_LINE_ROUGHNESS_M,
                    # ÖH D21 · P3B3-12: köken BEYAN EDİLİR. Bu sayı bu
                    # borunun ÖLÇÜLMÜŞ pürüzlülüğü değildir; ticari çelik
                    # boru için EL KİTABI tablosu değeridir (White Tablo
                    # 6.1). Beyan edilmediğinde modül künyeye 'UNDECLARED
                    # provenance' yazıyordu (ölçüldü: once.json P3B3-12,
                    # roughness_provenance=None) ve motorun kendi
                    # docstring'i sayıyı 'ölçüyle verir' diye anlatıyordu.
                    roughness_provenance='handbook_table',
                    # ÖH Z5S / defter P4B4-08: yapısal boru malzemesi
                    # (materials_db anahtarı) su koçu bloğuyla AYNI tek
                    # tanımdan gelir; pürüzlülük zaten ÖLÇÜYLE
                    # (FEED_LINE_ROUGHNESS_M) verildiği için bitiş anahtarı
                    # okunmaz. Eskiden adaptör varsayılanı
                    # 'stainless_tubing' su koçu tarafına gidiyor, her
                    # çağrıda ss_304'e düşüyor ve hükmü zorla MARGINAL'e
                    # indiriyordu — aynı motorun iki bloğunda iki malzeme
                    # künyesi vardı.
                    pipe_structural_material=pipe_material,
                    extra_loss_coefficient=k_extra,
                    vapor_pressure_Pa=vapor_pa,
                    valve_style=FEED_MAIN_VALVE_STYLE,
                    valve_closure_time_s=(None if closure_ms is None
                                          else float(closure_ms) / 1000.0),
                    # ÖH D35 / OH-GT-19: modül İKİ kez çağrılıyor ve panel
                    # dört validity adresini tek listede topluyor. Hat adı
                    # verilmezse aynı su koçu cümlesi iki hattan da AYNEN
                    # geliyor: kullanıcı uyarıyı iki kez görüyor ve hangi
                    # hatta ait olduğunu okuyamıyor (ölçüldü:
                    # raw/OH/D35/dil-safligi/a1/once.json, GT19). Etiket
                    # `label`den TÜRETİLİR — ikinci bir ad tanımlanmaz.
                    line_label=str(label).replace('_', ' '))
            except Exception as exc:
                return {'status': 'not_computed',
                        'basis': ('valve/feed-line analysis rejected the '
                                  f'inputs: {exc}')}
            res = dict(res)
            res.update({
                'status': 'modelled',
                # B4 (v2.6.27) DÜZELTMESİ: etiket 'line' adıyla yazılıyordu ve
                # modülün 'line' ALT SÖZLÜĞÜNÜ (giriş çapı/uzunluğu/pürüzü,
                # hız, Reynolds, sürtünme faktörü, kayıp dökümü) bir metinle
                # EZİYORDU. Blok "hat çapı, hızı ve pürüzü bu motorun kendi
                # değerleridir" diye beyan ederken o değerlerin hiçbiri
                # çıktıda kalmıyordu. Etiket, turbopompa bloğundaki
                # 'pump_label' deseniyle aynı biçimde ayrı adla taşınır.
                'line_label': label,
                'line_length_basis': FEED_LINE_LENGTH_BASIS,
                'line_diameter_basis': (
                    'the SAME standard-rounded line diameter the engine feed '
                    'pressure-drop chain uses (sized for the '
                    f'{FEED_LINE_TARGET_VELOCITY_MS:g} m/s target velocity)'),
                'roughness_basis': (
                    'commercial steel absolute roughness '
                    f'{FEED_LINE_ROUGHNESS_M * 1e3:g} mm '
                    '(FEED_LINE_ROUGHNESS_M) - the single value the engine '
                    'Darcy-Weisbach chain also uses'),
                'extra_loss_coefficient': k_extra,
                'extra_loss_basis': (
                    'the local-loss coefficients of this engine carried over '
                    f'unchanged: sharp tank outlet K={FEED_K_TANK_OUTLET:g}, '
                    f'line filter K={FEED_K_FILTER:g}, '
                    f'{FEED_ELBOW_COUNT:d} long-radius elbows at '
                    f'K={FEED_K_ELBOW:g} each. The main valve is NOT in this '
                    'sum: it is the valve being sized.'),
                'valve_pressure_drop_basis': (
                    'the engine main-valve loss item '
                    f'(K={FEED_K_MAIN_VALVE:g} x dynamic pressure at the '
                    'line velocity)'),
                'valve_style_source': (
                    f"declared design choice '{FEED_MAIN_VALVE_STYLE}': HRMA "
                    'has no valve-style input, and the engine loss item is '
                    'written for a full-open ball/butterfly main valve'),
                'viscosity_Pa_s': float(mu),
                'viscosity_source': (
                    'user input (propellant viscosity)' if mu_user
                    else 'not supplied -> the same tabulated fallback the '
                         'engine Darcy-Weisbach feed chain uses'),
                'inlet_pressure_bar': float(working_bar),
                'inlet_pressure_basis': (
                    'tank pressure (pressure-fed cycle)' if pressure_fed
                    else 'pump discharge pressure of this line - the same '
                         'working pressure the water-hammer block uses'),
                'vapor_pressure_Pa': vapor_pa,
                'vapor_pressure_source': (
                    None if record is None
                    else record.get('vapor_pressure_source')),
                # ÖH Z5S / P4B4-07 + P5B3-02: yayımlanan akışkan etiketi ve
                # nereden geldiği. Haritasız itici için etiket YOKTUR (None);
                # sessizce 'water' konmaz.
                'water_hammer_fluid_key': fluid_key,
                'water_hammer_fluid_key_source': (
                    'feed fluid map (WATER_HAMMER_FLUID_KEY) - the same key '
                    'the engine water-hammer block uses' if fluid_key
                    else f"'{propellant}' is not in the feed fluid map "
                         f'(covered: {sorted(FEED_FLUID_PROPERTY_KEY)}); no '
                         'fluid label is substituted, so the water-hammer '
                         'coupling is not produced'),
                'pipe_structural_material': pipe_material,
                'pipe_structural_material_source': pipe_material_source,
                'water_hammer_coupling_source': (
                    'user input (feed line wall thickness)'
                    if (wall_mm is not None and fluid_key) else
                    'not produced: ' + ' | '.join(
                        ([] if wall_mm is not None else [
                            'feed_line_wall_thickness [mm] is not supplied '
                            'and HRMA computes no line wall thickness, so '
                            'the elastic wave speed is undefined'])
                        + ([] if fluid_key else [
                            f"'{propellant}' has no tabulated water-hammer "
                            'fluid record (liquid bulk modulus), and no '
                            'fluid label is invented in its place']))),
            })
            if vapor_pa is None:
                res['cavitation_screening_source'] = (
                    'no tabulated vapour pressure for '
                    f"'{propellant}' -> the module performed no cavitation "
                    'screening and says so in its own validity list')
            return res

        mdot_ox = getattr(self, 'mdot_ox', None)
        mdot_fuel = getattr(self, 'mdot_fuel', None)
        if not mdot_ox or not mdot_fuel:
            return {'status': 'NOT_MODELLED', '_basis': basis,
                    'reason': ('propellant mass flows are not solved in this '
                               'run; no feed-line budget is produced.')}
        mu_ox_user = getattr(self, 'mu_ox', None)
        mu_fuel_user = getattr(self, 'mu_fuel', None)
        ox_working = (tank_bar if pressure_fed
                      else drops['pump_discharge_pressure_ox'])
        fuel_working = (tank_bar if pressure_fed
                        else drops['pump_discharge_pressure_fuel'])
        return {
            'status': 'modelled',
            '_basis': basis,
            'oxidizer_line': _line_block(
                'oxidizer_line', self.oxidizer_type, drops['oxidizer_line'],
                mdot_ox, self.rho_ox,
                mu_ox_user or FEED_VISCOSITY_FALLBACK_PA_S['oxidizer'],
                mu_ox_user is not None, ox_working),
            'fuel_line': _line_block(
                'fuel_line', self.fuel_type, drops['fuel_line'],
                mdot_fuel, self.rho_fuel,
                mu_fuel_user or FEED_VISCOSITY_FALLBACK_PA_S['fuel'],
                mu_fuel_user is not None, fuel_working),
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
            # --- ÖH D22 / OH-D20-04 · BASI ANA KADEMEDEN KURULUR ----------
            # ÖLÇÜLDÜ (250 kN, Pc=150, staged_combustion): çevrimin
            # yayımladığı tek ``pump_discharge_ox_bar`` iki kademenin
            # MAKSİMUMU (ön yakıcı boost kademesi, 248 bar). Aşağı akıştaki
            # tek kademeli basi hesabı bunu TÜM debiye uyguladığı için
            # H = 2178,7 m çıkıyordu; oysa çevrimin KENDİ güç ayrımı tüm
            # debiyi ana kademede ~186 bar'a, yalnız ön yakıcı payını
            # 248 bar'a çıkarıyor. Aynı yanıtta pompa gücü bölünmüş, basısı
            # bölünmemişti. Pompa boyutlandırması artık ANA kademe basıncını
            # görür; boost kademesi kaybolmaz, adıyla yanında durur.
            _split = cycle_solution.get('pump_stage_split')
            if isinstance(_split, dict):
                for _yan, _anahtar in (('oxidizer', 'ox'), ('fuel', 'fuel')):
                    _k = _split.get(_yan) or {}
                    _ana = _k.get('main_stage_discharge_bar')
                    if _ana and float(_ana) > 0:
                        drops[f'pump_discharge_pressure_{_anahtar}'] = float(
                            _ana)
                drops['pump_stage_split'] = _split
                drops['discharge_pressure_source'] = (
                    'cycle power balance, MAIN stage discharge (preburner '
                    'ladder + regenerative channel drop included). The '
                    'preburner boost stage reaches a higher pressure with '
                    'only its own share of the flow; see pump_stage_split.')
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
        # A11: değer TEK tanım noktasından (_tank_pressure_bar); uyarı
        # eşikleri değişmedi.
        tank_bar, _ = self._tank_pressure_bar()
        # ÖH A2 sivi-sogutma · F-20 (OH-FB-02): basma basıncı ne besleme
        # bütçesinden (enjektör kalemi çözülemedi -> None) ne çevrim
        # çözümünden geliyorsa, bu basınca bağlı YEDİ tüketicinin hiçbiri
        # sayı üretmez: basınç-beslemeli tank kapısı, besleme basıncı uyarısı,
        # pompa tasarımı, required_pump_discharge_bar, performance_margins,
        # su koçu çalışma basıncı, vana/hat bütçesi. Eskiden bu yol alt sınır
        # basma basıncıyla (ölçüldü: 102,277 ⟷ 122,277 bar) tasarım
        # değeri gibi devam ediyordu.
        if (drops.get('pump_discharge_pressure_ox') is None
                or drops.get('pump_discharge_pressure_fuel') is None):
            return {
                'status': 'not_computed',
                'reason': (
                    'the pump discharge pressure is not available: the feed '
                    'budget could not compute its injector item '
                    '(feed_system.pressure_drops.injector_drop_status = '
                    "'not_computed') and the cycle balance published no "
                    'discharge pressure. The tank gate, pump sizing, '
                    'required_pump_discharge_bar, performance_margins, '
                    'water_hammer and valve_feedline blocks all depend on it '
                    'and are NOT computed; no lower-bound value is '
                    'substituted.'),
                'engine_cycle_solution': cycle_solution,
                'turbopump_required': not pressure_fed,
                'tank_pressure_bar': tank_bar,
                'tank_pressure_source': self._tank_pressure_bar()[1],
                'feed_pressure_input_bar': feed_input,
                'required_pump_discharge_bar': None,
                'performance_margins': None,
                'discharge_pressure_source': drops.get(
                    'discharge_pressure_source'),
            }
        # F1-2 (bebek-Scofield, 2026-08-17): tank basıncı marjı TEK kaynaktan
        # — çevrim çözücüsünün kendi tanımı (cycle_power_balance:613,
        # margin = tank − max(req_ox, req_yakıt)). Eski formül
        # ``tank_bar − pump_discharge_pressure_ox`` YALNIZ oksitleyici
        # hattına bakıyordu ve rejeneratif ΔP taşıyan YAKIT gereksinimi
        # bağlayıcıyken marjın İŞARETİNİ ters çeviriyordu (ölçülen: 95 bar
        # tank, req_ox 90,60 / req_fuel 98,58 → yayımlanan +4,40, çözücü
        # −3,58 + critical infeasible uyarısı — aynı yanıtta). Buradaki
        # değer artık çözücünün yayımladığı marjın KENDİSİDİR; ikinci bir
        # marj formülü tanımlanmaz. Bekçi: tests/test_scofield_sivi.py.
        tank_margin = None
        tank_margin_basis = (
            'turbopump-fed cycle: the tank only pressurises for pump NPSH; '
            'a pressure-fed tank margin is not defined here')
        if pressure_fed:
            _cyc_margin = cycle_solution.get('tank_pressure_margin_bar')
            if isinstance(_cyc_margin, (int, float)):
                tank_margin = float(_cyc_margin)
                tank_margin_basis = (
                    'engine_cycle_solution.tank_pressure_margin_bar (single '
                    'source): tank pressure minus the LARGER of the oxidizer '
                    'and fuel required tank pressures (the fuel side carries '
                    'the regenerative-jacket pressure drop) — see '
                    'required_tank_pressure_ox_bar / '
                    'required_tank_pressure_fuel_bar in the same solution')
            else:
                tank_margin_basis = (
                    'not_modelled: the cycle balance did not publish a tank '
                    'pressure margin for this run (see '
                    'engine_cycle_solution.status); no substitute margin is '
                    'invented from a partial pressure chain')
        if pressure_fed:
            # Kapı da AYNI kaynaktan: marj negatifse (yakıt YA DA oksitleyici
            # tarafı bağlayıcı) kullanıcıya motor seviyesinde de söylenir.
            # Eski kapı yalnız oksitleyici basma basıncına bakıyordu ve
            # ölçülen vakada (yakıt tarafı bağlayıcı) hiç ateşlemiyordu.
            if tank_margin is not None and tank_margin < 0.0:
                _req = max(
                    float(cycle_solution.get(
                        'required_tank_pressure_ox_bar') or 0.0),
                    float(cycle_solution.get(
                        'required_tank_pressure_fuel_bar') or 0.0))
                self._warn('warn.liquid.pressure_fed_tank_too_low', 'critical',
                           tank_bar=float(tank_bar),
                           required_bar=round(_req, 1),
                           chamber_bar=float(self.P_c))
            elif (tank_margin is None
                    and tank_bar < drops['pump_discharge_pressure_ox']):
                # Çözücü marj yayımlayamadıysa eski oksitleyici-alt-sınır
                # kapısı yedek olarak kalır (marj DEĞİL, alt sınır).
                self._warn('warn.liquid.pressure_fed_tank_too_low', 'critical',
                           tank_bar=float(tank_bar),
                           required_bar=round(float(
                               drops['pump_discharge_pressure_ox']), 1),
                           chamber_bar=float(self.P_c))
        else:
            if feed_input is not None and feed_input < drops[
                    'pump_discharge_pressure_ox']:
                self._warn('warn.liquid.feed_pressure_below_pump_discharge', 'warning',
                           feed_bar=float(feed_input),
                           required_bar=round(float(
                               drops['pump_discharge_pressure_ox']), 1))
        duty = self._cycle_pump_duty()
        p_ox_kw = p_fuel_kw = None
        if duty is not None:
            mdot_ox, mdot_fuel, p_ox_kw, p_fuel_kw = duty
        ox_pump = self._design_pump(mdot_ox, self.rho_ox,
                                    drops['pump_discharge_pressure_ox'],
                                    tank_bar, shaft_power_kw=p_ox_kw,
                                    propellant=self.oxidizer_type,
                                    role='oxidizer',
                                    line=drops['oxidizer_line'])
        fuel_pump = self._design_pump(mdot_fuel, self.rho_fuel,
                                      drops['pump_discharge_pressure_fuel'],
                                      tank_bar, shaft_power_kw=p_fuel_kw,
                                      propellant=self.fuel_type,
                                      role='fuel',
                                      line=drops['fuel_line'])

        # Türbin: MİL gücü pompalardan (mil dengesi); uç hızı gerçek özgül
        # işten. F5-3 (bebek-Scofield, 2026-08-17): buradaki ikinci
        # ``/ eta_turbine`` kopyası da kaldırıldı — verim mil gücünü
        # büyütmez, gaz debisi boyutlandırmasına girer (aşağıda
        # turbine_mdot = P_mil/(Δh·η)). Eski hâliyle mdot P/(η²Δh)
        # oluyordu (verim iki kez uygulanıyordu).
        eta_turbine = TURBINE_EFFICIENCY_DEFAULT
        turbine_power = (ox_pump['design_power']
                         + fuel_pump['design_power'])  # kW (mil dengesi)
        t_in = float(getattr(self, 'turbine_inlet_temp',
                             GAS_GENERATOR_TEMP_DEFAULT_K))
        # Basınç oranı ÖNCELİĞİ kullanıcının doğrudan girdiği türbin genişleme
        # oranındadır; ayrıca türbin giriş basıncı girildiyse ikisi
        # karşılaştırılır ve tutarsızlık sessiz kalmaz.
        pr = float(getattr(self, 'turbine_pressure_ratio',
                           TURBINE_PRESSURE_RATIO_DEFAULT))
        p_in = getattr(self, 'turbine_inlet_pressure_bar', None)
        if pressure_fed:
            # V3 taban-a: türbinsiz çevrimde türbin alanları DEĞERLENDİRİLMEZ;
            # gönderilenler adıyla beyan edilir (sessizce yutulmaz).
            self._declare_turbine_inputs_unused()
            self._declare_turbopump_inputs_unused()
        elif p_in:
            # v2.6.26: karşılaştırma tabanı ATMOSFER BASINCIYDI
            # (pr_from_inlet = p_in / P_a). Türbin hiçbir çevrimde atmosfere
            # boşalmaz: kapalı çevrimde ana odaya, açık çevrimde kendi egzoz
            # lülesine açılır (Sutton & Biblarz 9th ed. Böl. 10; Huzel & Huang
            # Böl. 6). Kullanıcı 150 bar girdiğinde ima edilen PR 148 çıkıyor
            # ve tutarsızlık uyarısı HER koşuda basılıyordu. Referans artık
            # çözücünün KENDİ türbin çıkış basıncıdır.
            p_exhaust, exhaust_basis = self._turbine_exhaust_pressure_bar()
            pr_from_inlet = max(p_in / p_exhaust, 1.2)
            if abs(pr_from_inlet - pr) / pr > INPUT_CONSISTENCY_TOLERANCE:
                self._warn('warn.liquid.turbine_pr_inconsistent', 'warning',
                           inlet_bar=float(p_in),
                           pr_from_inlet=round(float(pr_from_inlet), 1),
                           pr_entered=round(float(pr), 1))
        # Δh = cp·T_in·(1 − PR^(−(γ−1)/γ)) (izentropik iş, Sutton Ch. 10)
        # KU-26 beyanı: cp/γ (ve girdi yoksa T_in) kaynaksız yedektir —
        # TURBINE_FALLBACK_GAS_BASIS; çevrim kapanırsa aşağıda ezilir.
        delta_h = (TURBINE_GAS_CP_J_KGK * t_in
                   * (1.0 - pr ** (-(TURBINE_GAS_GAMMA - 1.0)
                                   / TURBINE_GAS_GAMMA)))
        c0 = np.sqrt(2.0 * delta_h)                   # spouting velocity, m/s
        # TEK KADEMELİ optimum çevre hızı — bu kartın KENDİ kestirimi.
        # ÖH defter P3B4-02 (Z5S/PK1): eskiden bu sayı doğrudan
        # 'blade_tip_speed' olarak yayımlanıyordu ve aynı yanıttaki
        # turbopump_sizing bloğu AYNI türbin için başka bir çevre hızı ve
        # başka bir ortalama çap (4,824x) veriyordu. Sayı kaybolmuyor;
        # aşağıda kendi ADIYLA ve künyesiyle duruyor, yayımlanan geometri
        # ise boyutlandırma modülünün kademe-kısıtlı çözümünden geliyor.
        single_stage_tip_speed = TURBINE_VELOCITY_RATIO * c0
        # ÖH defter P3B4-01: uyarı BURADA ateşleniyordu ve girdisi bu yerel
        # kestirimdi. t_in/pr modül varsayılanları (1200 K / 8,5) olduğu için
        # sayı HER motorda birebir 615,4852 m/s çıkıyor, yani uyarı her
        # turbopompalı koşuda ateşleniyordu: bilgi taşımayan sabit alarm,
        # gerçekten aşan tasarımla aşmayanı ayırt edemiyordu (ölçüldü: 6/6).
        # Uyarı artık YAYIMLANAN (boyutlandırılmış) çevre hızına karşı, kartın
        # geometrisi mutabık kılındıktan SONRA ateşlenir.
        turbine_mdot = turbine_power * 1000.0 / max(delta_h * eta_turbine, 1.0)

        # Çevrim çözümü varsa türbin/ön yakıcı kartı ONDAN gelir (sabit %5
        # GG debisi ve genel PR varsayımı yerine kapanan denge — madde 2).
        turbine_card = {
            # 'type' ve geometri alanları aşağıda boyutlandırma modülünden
            # mutabık kılınır (_reconcile_turbine_geometry); modül geometri
            # üretemezse kartın kendi tek kademeli kestirimi künyesiyle
            # kalır. Buradaki başlangıç değeri o yedeğin ta kendisidir.
            'type': 'Single-stage axial',
            'power_output': turbine_power,  # kW (mil dengesi = pompa gücü)
            'power_output_basis': (
                'shaft power balance: turbine shaft power equals the total '
                'pump shaft power; the turbine efficiency sizes the gas '
                'mass flow (mdot = P_shaft/(eta x ideal specific work)), '
                'not the shaft power'),
            'inlet_temperature': t_in,  # K
            # P3B3-05: künye anahtarın VARLIĞINA bakıyordu; reddedilen girdi
            # de 'user input' diye etiketleniyordu (sayı varsayılana düşmüş
            # olmasına rağmen). Üç durum artık ayrı ADLANDIRILIR.
            'inlet_temperature_source': (
                'user input (gas generator temperature)'
                if getattr(self, 'turbine_inlet_temp_accepted', False)
                else (TURBINE_INLET_TEMP_SOURCE_REJECTED
                      if 'generator_gas_temp' in self.overrides
                      else 'assumed gas-generator temperature')),
            # Çevrim kapandığında yukarıdaki künye çözücünün adıyla EZİLİR;
            # kullanıcının girdisine ne olduğu ayrı ve EZİLMEYEN bir alanda
            # durur, yoksa reddedilme haberi kartta kaybolur (P3B3-05).
            'inlet_temperature_input_status': (
                'accepted'
                if getattr(self, 'turbine_inlet_temp_accepted', False)
                else ('rejected' if 'generator_gas_temp' in self.overrides
                      else 'not_supplied')),
            'inlet_temperature_input_basis': (
                TURBINE_INLET_TEMP_SOURCE_REJECTED
                if ('generator_gas_temp' in self.overrides
                    and not getattr(self, 'turbine_inlet_temp_accepted',
                                    False))
                else 'no rejected turbine inlet temperature input'),
            'pressure_ratio': pr,
            # ÖH defter P3B3-02: bu alan YÜZDE (65,0) yayımlanırken kardeş
            # kart AYNI ADLA kesir (0,65) yayımlıyordu — tek yanıtta iki
            # birim. İki kart artık KESİR yayımlar ve birimi yanında yazar.
            'efficiency': eta_turbine,
            'efficiency_unit': 'fraction',
            'rotational_speed': ox_pump['rotational_speed'],  # rpm
            'blade_tip_speed': single_stage_tip_speed,  # m/s
            'specific_work_J_kg': delta_h,
            'mass_flow_rate': turbine_mdot,  # kg/s
            # KU-26 beyanı: çevrim kapanırsa bu alan aşağıda çözümün adıyla
            # ezilir; kapanmazsa yedek gazın kaynaksız olduğu burada söylenir.
            'model': ('isentropic single-stage work with U/C0='
                      f'{TURBINE_VELOCITY_RATIO:g} optimum velocity '
                      'ratio - ' + TURBINE_FALLBACK_GAS_BASIS),
            # P3B4-02: kartın KENDİ tek kademeli kestirimi — adı ayrı, künyesi
            # ayrı; yayımlanan geometriyle karıştırılmasın diye hep durur.
            'blade_speed_single_stage_optimum_m_s': float(
                single_stage_tip_speed),
            'blade_speed_single_stage_optimum_basis': (
                f'U = {TURBINE_VELOCITY_RATIO:g} x C0 with C0 = '
                'sqrt(2 x ideal specific work): the optimum velocity ratio '
                'of a SINGLE-stage impulse turbine. It is an upper-bound '
                'estimate, not the sized geometry - a single stage at this '
                'speed can exceed the structural pitch-speed practice limit '
                f'({TURBINE_TIP_SPEED_LIMIT_MS:g} m/s), which is exactly why '
                'the sizing block pressure-compounds the work into stages.'),
        }
        # ÖH defter P3B3-01: çevrim kapanmadığında burada MR = 0,8 ve
        # %5 sabit debi payı yayımlanıyordu — hiçbiri motorla değişmeyen,
        # tasarım olmayan varsayımlar. Fail-closed: kapanmadıysa sayı yok.
        gg_card = {
            'status': 'not_computed',
            'mass_flow_rate': None,
            'mixture_ratio': None,
            'chamber_pressure': None,
            'temperature': None,
            'flow_fraction': None,
            'flow_fraction_unit': 'percent',
            'source': self._cycle_card_withheld_basis(
                cycle_solution, 'gas generator / preburner'),
        }
        if (cycle_solution.get('status') == 'converged'
                and cycle_solution.get('shafts')):
            shaft0 = cycle_solution['shafts'][0]
            turb0 = shaft0.get('turbine') or {}
            turbine_card.update({
                'power_output': cycle_solution['turbine_power_total_W'] / 1e3,
                # ÖH D21 · P3B4-04: SAYININ KAYNAĞI DEĞİŞİNCE KÜNYE DE
                # DEĞİŞİR. Yukarıdaki başlangıç künyesi "türbin mil gücü =
                # TOPLAM POMPA mil gücü" diyordu; çevrim yolunda sayı artık
                # çözücünün MİL BAŞINA kapanışının toplamıdır
                # (turbine_power_total_W). ÖLÇÜLDÜ (once.json P3B4-04;
                # staged, 250 kN / Pc 150): power_output 2374,2626 kW
                # yayımlanırken künye hâlâ eski kapanışı anlatıyordu.
                'power_output_basis': (
                    'cycle power balance: the sum of the per-shaft turbine '
                    'powers the solver closed (engine_cycle_solution.'
                    'turbine_power_total_W over '
                    f"{len(cycle_solution['shafts'])} shaft(s)). Each shaft "
                    'closes its own shaft power balance - turbine shaft '
                    'power equals the pump shaft power ON THAT SHAFT; the '
                    'turbine efficiency sizes the GAS flow '
                    '(mdot = P_shaft/(eta x ideal specific work)), it does '
                    'not inflate the shaft power.'),
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
                'source': CYCLE_CARD_SOURCE,
            })
            # ÖH defter P3B3-02: çevrim çözücüsü türbin verimini çevrim
            # SINIFINA göre seçiyor (staged/FFSC'de 0,78) ama kart eski
            # 0,65 gaz-jeneratörü sabitini yayımlamayı sürdürüyordu —
            # üçüncü bir verim değeri. Kart artık çözücünün KULLANDIĞI
            # verimi yayımlar.
            _eta_solved = turb0.get('efficiency')
            if isinstance(_eta_solved, (int, float)) and _eta_solved > 0:
                turbine_card['efficiency'] = float(_eta_solved)
            # ÖH defter P3B4-01: kartın 'tek kademeli optimum' kestirimi de
            # ATILAN türbine aitti — Δh yerel varsayılanlardan (1200 K / 8,5)
            # hesaplanıyor, kartın geri kalanı çözücünün türbinini (1000 K /
            # 16,0) anlatıyordu. Aynı kartta iki türbin kalamaz: kestirim
            # artık ÇÖZÜLEN türbinin izentropik işinden türer.
            _dh_ideal = turb0.get('ideal_specific_work_J_kg')
            if not isinstance(_dh_ideal, (int, float)) or _dh_ideal <= 0:
                _eta = turbine_card.get('efficiency') or eta_turbine
                _dh_real = turbine_card.get('specific_work_J_kg')
                _dh_ideal = (float(_dh_real) / float(_eta)
                             if isinstance(_dh_real, (int, float))
                             and _dh_real and _eta else None)
            if isinstance(_dh_ideal, (int, float)) and _dh_ideal > 0:
                single_stage_tip_speed = (TURBINE_VELOCITY_RATIO
                                          * np.sqrt(2.0 * float(_dh_ideal)))
                turbine_card['blade_speed_single_stage_optimum_m_s'] = float(
                    single_stage_tip_speed)
                # Kartın YAYIMLADIĞI çevre hızı da bu kestirimdir; boyutlandırma
                # modülü geometri üretirse _reconcile_turbine_geometry bunu
                # kademe-kısıtlı pitch hızıyla değiştirir. Eski kod yalnız ayrı
                # adlı alanı tazeliyor, yayımlanan alan ATILAN türbinin
                # sabitinde (615,4852) kalıyordu.
                turbine_card['blade_tip_speed'] = float(single_stage_tip_speed)
                turbine_card['ideal_specific_work_J_kg'] = float(_dh_ideal)
                turbine_card['ideal_specific_work_basis'] = (
                    'isentropic (ideal) specific work of the SOLVED turbine: '
                    'the cycle balance value when it publishes one, otherwise '
                    'the published real work divided by the turbine '
                    'efficiency the same solution used')
            if cycle_solution.get('preburners'):
                pb0 = cycle_solution['preburners'][0]
                gg_card = {
                    'status': 'modelled',
                    'mass_flow_rate': pb0['mdot_total_kg_s'],
                    'mixture_ratio': pb0['of_ratio'],
                    'chamber_pressure': pb0['pressure_bar'],
                    'temperature': pb0['temperature_K'],
                    'flow_fraction': (
                        pb0['mdot_total_kg_s'] / max(mdot_total, 1e-9)
                        * 100.0),
                    'flow_fraction_unit': 'percent',
                    'mode': pb0.get('mode'),
                    'source': CYCLE_CARD_SOURCE,
                }

        # Türbin giriş basıncı 'reported_for_comparison' beyanıyla bildirilen
        # bir alandır; kullanıcının karşılaştırabilmesi için çözücünün KENDİ
        # ima ettiği giriş basıncı da yayımlanır (P_in = PR · P_atmosfer,
        # tutarlılık denetiminin ters çevrilmiş hâli). Arayüz bu düğümü okur;
        # sabit atmosfer basıncı JS'e kopyalanmaz.
        # v2.6.26: burada `PR x P_atmosfer` yazıyordu ve aynı koşuda çevrim
        # çözücüsü türbin giriş basıncını 78.78 bar diye raporlarken bu yaprak
        # 4.05 bar diyordu (19 kat fark). Arayüz kullanıcının 150 bar'lık
        # girdisini 4.05 bar ile karşılaştırıyordu. Çözüm TEK KAYNAK: çevrim
        # kapandıysa mil türbininin kendi giriş basıncı yayımlanır.
        solver_p_in = None
        if (cycle_solution.get('status') == 'converged'
                and cycle_solution.get('shafts')):
            solver_p_in = ((cycle_solution['shafts'][0].get('turbine') or {})
                           .get('inlet_pressure_bar'))
        if isinstance(solver_p_in, (int, float)) and solver_p_in > 0:
            turbine_card['inlet_pressure_implied_bar'] = float(solver_p_in)
            turbine_card['inlet_pressure_implied_basis'] = (
                'cycle power balance: the shaft turbine inlet pressure of the '
                'solved pressure ladder')
        else:
            p_exhaust, exhaust_basis = self._turbine_exhaust_pressure_bar()
            turbine_card['inlet_pressure_implied_bar'] = float(
                turbine_card['pressure_ratio']) * p_exhaust
            turbine_card['inlet_pressure_implied_basis'] = (
                'pressure ratio x turbine exhaust pressure (' + exhaust_basis
                + '); the cycle balance did not converge')
        _p_exh, _exh_basis = self._turbine_exhaust_pressure_bar()
        turbine_card['exhaust_pressure_bar'] = _p_exh
        turbine_card['exhaust_pressure_basis'] = _exh_basis

        margins = self._feed_performance_margins(drops, ox_pump, fuel_pump,
                                                 turbine_card, pressure_fed)

        # C1 (v2.6.27) turbopompa boyutlandırma zinciri. ÖH defter P3B4-02
        # (Z5S/PK1): blok ÖNCE çözülür ve türbin kartının geometri/kademe
        # alanları ONDAN mutabık kılınır — aynı yanıtta aynı türbin için iki
        # çevre hızı, iki ortalama çap ve iki kademe sayısı kalamaz.
        turbopump_sizing = self._turbopump_sizing_block(
            drops, tank_bar, pressure_fed, ox_pump, fuel_pump,
            turbine_card, cycle_solution)
        if not pressure_fed:
            self._reconcile_turbine_geometry(
                turbine_card, (turbopump_sizing or {}).get('turbine'))
            # ÖH defter P3B4-01: uyarı YAYIMLANAN çevre hızına karşı verilir.
            # Boyutlandırma modülü işi kademelere böldüğünde gerçek türbin
            # sınırın altındadır ve uyarı ÇIKMAMALIDIR; modül geometri
            # üretemediyse (geometry_source='not_sized') kartın kendi tek
            # kademeli kestirimi yayımlanan sayıdır ve sınır ONA uygulanır.
            _u_pub = turbine_card.get('blade_tip_speed')
            if (isinstance(_u_pub, (int, float))
                    and float(_u_pub) > TURBINE_TIP_SPEED_LIMIT_MS):
                self._warn('warn.liquid.turbine_tip_speed_exceeded', 'warning',
                           tip_speed_ms=round(float(_u_pub)),
                           limit_ms=round(float(TURBINE_TIP_SPEED_LIMIT_MS)))
            turbine_card['blade_tip_speed_limit_ms'] = float(
                TURBINE_TIP_SPEED_LIMIT_MS)

        return {
            'feed_system_type': self.feed_system_type,
            'engine_cycle': getattr(self, 'engine_cycle', 'gas_generator'),
            # Tam çevrim kapanışı (mil başına döküm, ön yakıcılar, Isp
            # muhasebesi, uyarılar) — UI çevrim paneli bunu okur.
            'engine_cycle_solution': cycle_solution,
            'pump_discharge_source': drops.get('discharge_pressure_source'),
            'turbopump_analysis': {
                # Y4 (2026-07-30): basınç beslemeli çevrimde turbopompa
                # YOKTUR; pompa/türbin/gaz jeneratörü kartları burada sahte
                # sayı olur (0.543 kW'lık iki pompa, 130 bar gaz jeneratörü,
                # PR=4 türbin raporlanıyordu). Kartlar bilinçli olarak boş
                # bırakılır ve gerekçesi çıktıda yazar.
                'applicable': not pressure_fed,
                'not_applicable_reason': (
                    None if not pressure_fed else
                    'pressure-fed cycle: no pumps, no turbine, no gas '
                    'generator in this engine'),
                'oxidizer_pump': None if pressure_fed else ox_pump,
                'fuel_pump': None if pressure_fed else fuel_pump,
                'turbine': None if pressure_fed else turbine_card,
                'gas_generator': None if pressure_fed else gg_card,
                # B5 (v2.6.27): yakıt/oks pompaları farklı devirdeyse bu bir
                # dişli/çift-mil varsayımıdır; türbin oks miline boyutlanır.
                'shaft_architecture_note': (
                    None if pressure_fed
                    else self._shaft_architecture_note(ox_pump, fuel_pump)),
                # ÖH D21 · P3B3-10: kararın BEYANI. Basınç beslemeli
                # çevrimde pompa/türbin uyarıları kullanıcıya gitmez;
                # hangi kodların susturulduğu burada yazılıdır (sessiz
                # susturma yok).
                'suppressed_pump_warnings': (
                    None if not pressure_fed
                    else sorted(getattr(
                        self, '_pressure_fed_muted_warnings', []) or [])),
                'suppressed_pump_warnings_basis': (
                    None if not pressure_fed else
                    'pressure-fed cycle: the pump/turbine sizing chain still '
                    'runs to size the tanks and lines, but its pump- and '
                    'turbine-only warnings describe hardware this engine '
                    'does not have, so they are not published. The '
                    'suppression itself is declared here and the codes are '
                    'listed.'),
            },
            'turbopump_required': not pressure_fed,
            'tank_pressure_bar': tank_bar,
            # F3 (ÖH D18 fizik-a2): tank basıncının NASIL boyutlandığı sayının
            # yanında durur — hangi pompa yönetti, hangi hız-yükü sınıfı,
            # hangi NPSH gereksinimi, hangi marj katsayısı.
            'tank_pressure_source': self._tank_pressure_bar()[1],
            'npsh_tank_sizing': self._npsh_tank_sizing_report(),
            # F1-2: marj çevrim çözümünün KENDİSİNDEN okunur (yukarıda
            # kuruldu); eski ``tank_bar − ox basma basıncı`` formülü yakıt
            # tarafı bağlayıcıyken işareti ters çeviriyordu.
            'tank_pressure_margin_bar': tank_margin,
            'tank_pressure_margin_basis': tank_margin_basis,
            'feed_pressure_input_bar': feed_input,
            'required_pump_discharge_bar': drops['pump_discharge_pressure_ox'],
            'performance_margins': margins,
            # A6 (v2.6.27): besleme hattı su koçu — motorun kendi hat
            # verisiyle (çap/hız/basınç), eksik girdiler beyanla.
            'water_hammer': self._feed_water_hammer_analysis(
                drops, tank_bar, pressure_fed),
            # C2 (v2.6.27): hat basınç bütçesi + ana vana Cv/Kv — AYNI hat
            # verisiyle (su koçu bloğuyla tek kaynak).
            'valve_feedline': self._valve_feedline_block(
                drops, tank_bar, pressure_fed),
            # C1 (v2.6.27): turbopompa boyutlandırma zinciri (Ns, kademe,
            # çark çapı, NPSH marjı, türbin ortalama çapı). Basınç
            # beslemelide NOT_APPLICABLE.
            'turbopump_sizing': turbopump_sizing,
        }
    
    def _turbine_exhaust_pressure_bar(self):
        """(türbin çıkış basıncı [bar], gerekçe) — çevrim SINIFINA göre.

        Türbin hiçbir çevrimde atmosfere boşalmaz:

        * Kapalı çevrim (staged, FFSC, expander): türbin egzozu ANA ODAYA
          girer, dolayısıyla karşı basınç oda basıncı + enjektör ΔP'sidir.
        * Açık çevrim (gaz jeneratörü, tap-off): türbin KENDİ egzoz lülesine
          boşalır; karşı basıncı ortam basıncına yakındır.

        (Sutton & Biblarz 9th ed. Böl. 10; Huzel & Huang Böl. 6.) Çevrim
        çözümü varsa türbinin kendi çıkış basıncı önceliklidir.
        """
        cyc = getattr(self, '_cycle_result', None)
        if isinstance(cyc, dict) and cyc.get('status') == 'converged':
            shafts = cyc.get('shafts') or []
            if shafts:
                p_exit = (shafts[0].get('turbine') or {}).get(
                    'exit_pressure_bar')
                if isinstance(p_exit, (int, float)) and p_exit > 0:
                    return float(p_exit), 'cycle power balance solution'
        cycle = getattr(self, 'engine_cycle', 'gas_generator')
        if cycle in ('staged_combustion', 'full_flow_staged', 'expander'):
            try:
                dp_frac = float(self._injector_dp_fraction())
            except Exception:
                dp_frac = 0.0
            p = float(self.P_c) * (1.0 + max(dp_frac, 0.0))
            return p, ('closed cycle: the turbine exhausts into the main '
                       'chamber (Pc plus injector dP)')
        return float(self.P_a), ('open cycle: the turbine exhausts through '
                                 'its own nozzle to ambient')

    def _feed_performance_margins(self, drops, ox_pump, fuel_pump,
                                  turbine_card, pressure_fed):
        """Besleme sistemi marjları — hepsi HESAPLANAN büyüklüklerden.

        v2.6.26 öncesi iki kalem sabitti ve marj değil ARTEFAKTTI:

        * ``flow_margin`` = (PUMP_CURVE_FLOW_MAX − 1)·100 = %50. Bu, pompa
          eğrisinin TARAMA BANDI genişliğidir; motorla hiçbir ilgisi yoktur.
        * ``power_margin`` = (1/η_türbin − 1)·100 = %53.85. Bu, türbin
          veriminin cebirsel yankısıdır; hiçbir marjı ölçmez.

        Yerlerine ne kondu ve NEDEN:

        ``flow_margin`` — besleme HATTININ debi payı. Hat çapı standart boru
        ölçüsüne yuvarlandığı için gerçek hız hedeften sapar; tavsiye edilen
        üst hıza (3-8 m/s bandının tepesi; kaynaksız HRMA tercihi, SP-125'te
        yok — KU-K1/SP-H1 K33)
        kalan pay gerçek bir tasarım marjıdır ve debi/yoğunluk/çap ile
        değişir. İki hattın DARBOĞAZI raporlanır.

        POMPANIN DEBİ marjı bu modelde tanım gereği sıfırdır: ``_design_pump``
        çarkı tam gerekli debi ve basma yüksekliğinde çözer (H(Q_gerekli) =
        H_gerekli) — bunu %50 diye raporlamak yanlıştı. NPSH marjı ise
        B5 (v2.6.27) düzeltmesiyle GERÇEK bir marjdır: devir kavitasyon
        sınırının SPEED_DERATE_DEFAULT katına indirildiği için tavansız
        tasarım noktasında NPSH_mevcut/NPSH_gerekli = derate^(-4/3) ≈ 1,15
        (~%15). Eski kod devri tam sınırdan seçiyor, marj her motorda ~1e-14
        çıkıyor ve basis metni bunu 'by construction' diye itiraf ediyordu.

        ``power_margin`` — türbinin ÖZGÜL İŞ payı. Tek kademeli impuls
        türbinde P = ṁ·Δh·η ve Δh = (U/(U/C₀))²/2 olduğundan, kanat uç hızı
        sınırında (TURBINE_TIP_SPEED_LIMIT_MS; künyesi sabitin yanında) aynı gaz
        debisiyle çıkarılabilecek en büyük özgül iş bellidir. Marj =
        Δh_sınır/Δh_çalışma − 1. TIT, basınç oranı ve çevrim sınıfıyla
        gerçekten değişir. Çevrim güç dengesi mil başına TAM kapandığı için
        (türbin gücü ≡ pompa gücü) "üretilen − gereken" farkı tanım gereği
        sıfırdır; o yüzden marj gaz tarafından değil TÜRBİNİN sınırından
        okunur.
        """
        # B5 (v2.6.27): npsh_margin artık GERÇEK bir marj. Eskiden devir tam
        # kavitasyon sınırından seçildiği için NPSH_req ≡ NPSH_avail idi ve
        # buradaki değer her motorda ~1e-14 çıkıyordu (totolojik ölü metrik;
        # kendi basis metni bunu itiraf ediyordu). Devir artık derate'li
        # seçilir (SPEED_DERATE_DEFAULT); marj tavansız noktada
        # derate^(-4/3)-1 ~= %15'tir, rpm tavanı bağlarsa büyür, tank
        # basınçlandırması yetersizse NEGATİF olur ve görünür. İki pompanın
        # KÖTÜSÜ raporlanır — eski kod yalnız oksitleyiciye bakarken yakıt
        # pompası -14 m NPSH ile sessizce geçiyordu.
        # ÖH D21 · P3B4-10 — DEJENERE PAYDA. Eski satır paydayı
        # ``max(abs(NPSH_req), 1e-9)`` ile korurdu: NPSH_req sıfıra
        # yaklaştığında (ya da çözülemediğinde) bu koruma bir SAYI
        # ÜRETİYORDU — savcı raporu aynı yanıtta boyutlandırma bloğu
        # 'hesaplanamadı' derken npsh_margin = -64757,02 % ölçtü. Oran
        # tanımsızsa oran YAYIMLANMAZ (fail-closed): hangi pompanın hangi
        # alanı yüzünden tanımsız olduğu adıyla beyan edilir.
        npsh_worst = None
        npsh_worst_pump = None
        npsh_undefined = {}
        for name, pump in (('oxidizer_pump', ox_pump),
                           ('fuel_pump', fuel_pump)):
            req = (pump or {}).get('npsh_required')
            avail = (pump or {}).get('npsh_available')
            gecerli = (isinstance(req, (int, float))
                       and not isinstance(req, bool)
                       and np.isfinite(req) and float(req) > 0.0
                       and isinstance(avail, (int, float))
                       and not isinstance(avail, bool)
                       and np.isfinite(avail))
            if not gecerli:
                npsh_undefined[name] = (
                    f'npsh_required={req!r}, npsh_available={avail!r}: the '
                    'ratio (NPSH_a - NPSH_r)/NPSH_r needs a finite positive '
                    'NPSH_required; no margin is published for this pump')
                continue
            m = (float(avail) - float(req)) / float(req) * 100.0
            if npsh_worst is None or m < npsh_worst:
                npsh_worst, npsh_worst_pump = m, name
        if npsh_undefined:
            # Bir pompanın oranı tanımsızsa "en kötü" hükmü de eksiktir:
            # sağ kalan pompanın sayısı bütün motorun marjı diye
            # yayımlanamaz.
            npsh_worst = None
            npsh_worst_pump = None
        margins = {
            'pressure_margin': (
                (drops['pump_discharge_pressure_ox'] - self.P_c)
                / max(self.P_c, 1e-9) * 100.0),
            'npsh_margin': npsh_worst,
            'npsh_margin_undefined_pumps': (npsh_undefined or None),
            'npsh_margin_basis': (
                ('NOT published: the NPSH margin is undefined for '
                 + ', '.join(sorted(npsh_undefined))
                 + '. ' + '; '.join(f'{a}: {b}' for a, b in
                                    sorted(npsh_undefined.items())))
                if npsh_undefined else (
                '(NPSH_available - NPSH_required)/NPSH_required of the '
                f'binding (worst) pump: {npsh_worst_pump}. The shaft speed '
                'is derated below the suction-limited maximum '
                f'(SPEED_DERATE_DEFAULT {SPEED_DERATE_DEFAULT:g}), so the '
                'uncapped design-point margin is '
                f'{(SPEED_DERATE_DEFAULT ** (-4.0 / 3.0) - 1.0) * 100.0:.1f}'
                '% rather than zero-by-construction; it grows when the '
                'practical rpm cap binds and goes negative when tank '
                'pressurization is insufficient (see '
                'warn.liquid.npsh_pressurization_insufficient)')),
        }

        # --- Hat debi marjı -------------------------------------------------
        worst = None
        worst_line = None
        for name in ('oxidizer_line', 'fuel_line'):
            line = drops.get(name) or {}
            v = line.get('line_velocity_m_s')
            if not v or v <= 0:
                continue
            m = (FEED_LINE_MAX_VELOCITY_MS / float(v) - 1.0) * 100.0
            if worst is None or m < worst:
                worst, worst_line = m, name
        margins['flow_margin'] = worst
        margins['flow_margin_basis'] = (
            'feed-line flow headroom to the recommended upper velocity '
            f'({FEED_LINE_MAX_VELOCITY_MS:g} m/s); binding line: '
            f'{worst_line}. The pumps themselves are sized exactly at the '
            'required duty and therefore carry no FLOW margin by '
            'construction; their NPSH headroom is the separate, real '
            'npsh_margin above.'
            if worst is not None else
            'not_modelled (feed line velocities unavailable)')

        # --- Türbin özgül iş marjı -----------------------------------------
        # ÖH defter P3B4-03: payda YANLIŞ BÜYÜKLÜKTÜ. dh_limit = (U_sınır /
        # (U/C0))^2 / 2, yani C0 = sqrt(2·Δh_izentropik) tanımından gelen
        # İDEAL (izentropik) iştir. Payda ise turbine_card'ın
        # 'specific_work_J_kg' alanıydı ve çevrim kapandığında o alan GERÇEK
        # işle (ideal × η) EZİLİYORDU: aynı ad, iki fiziksel büyüklük. Sapma
        # tam 1/η katıdır. ÖLÇÜLDÜ (250 kN/200 bar RP-1/LOX): yayımlanan marj
        # -%29,86 iken ideal/ideal oranı -%54,41 — 24,55 PUAN İYİMSER, üstelik
        # yön iyimser (kullanıcı sınıra uzak sanıyor). Marj artık ideal işe
        # bölünür ve paydanın hangi büyüklük olduğu ADIYLA yayımlanır.
        dh_ideal = None
        dh_ideal_source = None
        if not pressure_fed:
            v = turbine_card.get('ideal_specific_work_J_kg')
            if isinstance(v, (int, float)) and v > 0:
                dh_ideal, dh_ideal_source = float(v), (
                    'turbine card ideal (isentropic) specific work of the '
                    'solved turbine')
            else:
                dh_real = turbine_card.get('specific_work_J_kg')
                eta = turbine_card.get('efficiency')
                if (isinstance(dh_real, (int, float)) and dh_real > 0
                        and isinstance(eta, (int, float)) and 0 < eta <= 1.0):
                    dh_ideal = float(dh_real) / float(eta)
                    dh_ideal_source = (
                        'published real specific work divided by the turbine '
                        'efficiency of the same card (the card publishes real '
                        'work once the cycle balance converges)')
                elif isinstance(dh_real, (int, float)) and dh_real > 0:
                    dh_ideal = float(dh_real)
                    dh_ideal_source = (
                        'card specific work used as-is: the cycle balance did '
                        'not converge, so the field still holds the isentropic '
                        'work of the card\'s own single-stage estimate')
        if dh_ideal and dh_ideal > 0:
            dh_limit = (TURBINE_TIP_SPEED_LIMIT_MS
                        / TURBINE_VELOCITY_RATIO) ** 2 / 2.0
            margins['power_margin'] = (dh_limit / dh_ideal - 1.0) * 100.0
            margins['power_margin_specific_work_J_kg'] = dh_ideal
            margins['power_margin_specific_work_source'] = dh_ideal_source
            margins['power_margin_basis'] = (
                'single-stage turbine specific-work headroom: the blade tip '
                f'speed limit ({TURBINE_TIP_SPEED_LIMIT_MS:g} m/s at '
                f'U/C0 = {TURBINE_VELOCITY_RATIO:g}) caps the extractable '
                'IDEAL (isentropic) work at the same gas flow, so the '
                'denominator is the ideal work too - dividing it by the REAL '
                'work would compare two different quantities and read '
                'optimistic by exactly 1/eta. A multi-stage turbine relaxes '
                'this limit. The shaft power balance itself closes exactly, '
                'so turbine-minus-pump power is zero by construction.')
        else:
            margins['power_margin'] = None
            margins['power_margin_specific_work_J_kg'] = None
            margins['power_margin_specific_work_source'] = None
            margins['power_margin_basis'] = (
                'pressure-fed cycle: no turbine' if pressure_fed
                else 'not_modelled (turbine specific work unavailable)')
        return margins

    def _design_altitude_report(self):
        """Lülenin TASARIM (optimum) irtifası — P_cikis = P_ortam çözümü.

        Bir lüle, çıkış basıncı ortam basıncına eşit olduğu irtifada
        optimumdur (tam genişleme; Sutton & Biblarz 9th ed. Böl. 3.4).
        Isp irtifayla monoton arttığı için "Isp'nin en büyük olduğu irtifa"
        her zaman taramanın son noktasıdır ve tasarım irtifası DEĞİLDİR.

        ISA basınç profili (hrma.constants.ISA_LAYERS, US Standard Atmosphere
        1976) katman katman TERS çevrilir; barometrik bağıntı her katmanda
        analitik olarak çözülebilir. P_cikis ISA tabanının (deniz seviyesi)
        üstündeyse lüle deniz seviyesinde bile eksik genişlemiştir; ISA
        tavanının altındaysa lüle vakuma optimize edilmiştir ve SONLU bir
        optimum yoktur — ikisi de dürüstçe söylenir, sayı uydurulmaz.
        """
        from hrma.constants import (ISA_LAYERS, ISA_TABLE_TOP_M, M_AIR,
                                    R_STAR_ICAO)
        try:
            geom = self.calculate_nozzle_geometry()
            p_exit_bar = float(geom['exit_pressure'])
        except Exception as exc:
            return {'optimal_altitude': None,
                    'optimal_altitude_basis':
                        f'not_modelled (nozzle exit pressure unavailable: '
                        f'{exc})'}
        p_exit = p_exit_bar * PA_PER_BAR                        # Pa
        if p_exit >= ISA_LAYERS[0][3]:
            return {
                'optimal_altitude': 0.0,
                'nozzle_exit_pressure_bar': p_exit_bar,
                'optimal_altitude_basis': (
                    'exit pressure is at or above sea-level ambient: the '
                    'nozzle is under-expanded everywhere, so the optimum is '
                    'at h = 0'),
            }

        # ÖH D15 / sıvı (P3B4-05): katman seçimi DÜZELTİLDİ.
        # Eski kapı `if p_exit > p_base: continue` idi. ISA_LAYERS'ta p_base
        # AZALARAK gider (101325 -> 3,96 Pa) ve deniz seviyesi üstü yukarıda
        # ayrı ele alındığı için döngüye giren her p_exit 101325'ten
        # küçüktür: kapı HİÇ ısırmaz, döngü BİRİNCİ katmanda kırılırdı.
        # Altı katmanın altısı ölüydü, yani "katman katman ters çevrilir"
        # diyen künyeye rağmen HER irtifa troposfer formülüyle çözülüyordu
        # (ölçüldü, docs/scofield/raw/OH/D15/sivi/a3/once.json: eps=300'de
        # 25.696 m yayımlanırken doğrusu 30.587 m — 4.890 m eksik; kapanış
        # denetimi de tutmuyordu: yayımlanan irtifadaki gerçek ISA basıncı
        # 2292 Pa iken çıkış basıncı 1097 Pa idi).
        # p_exit'i İÇEREN katman, taban basıncı p_exit'ten KÜÇÜK OLMAYAN
        # katmanların SONUNCUSUDUR (hrma.constants._isa_layer'ın irtifa
        # tarafındaki seçimiyle aynı mantık, basınç ekseninde).
        katman = None
        for aday in ISA_LAYERS:
            if aday[3] >= p_exit:
                katman = aday
            else:
                break
        h_geopot = None
        if katman is not None:
            h_base, t_base, lapse, p_base = katman
            if abs(lapse) > 1e-12:
                # P = P_b (T/T_b)^(-g M/(R L))  ->  T = T_b (P/P_b)^(-R L/(g M))
                expo = -(R_STAR_ICAO * lapse) / (G_0 * M_AIR)
                t = t_base * (p_exit / p_base) ** expo
                h_geopot = h_base + (t - t_base) / lapse
            else:
                h_geopot = h_base - (R_STAR_ICAO * t_base / (G_0 * M_AIR)) \
                    * np.log(p_exit / p_base)
            # Tablo tavanının üstüne düşen çözüm tablonun DIŞINDADIR; orada
            # izotermal uzantı vardır ve "katman katman ters" künyesi artık
            # doğru olmaz — sayı uydurulmaz.
            if not np.isfinite(h_geopot) or h_geopot > ISA_TABLE_TOP_M:
                h_geopot = None
        if h_geopot is None:
            return {
                'optimal_altitude': None,
                'nozzle_exit_pressure_bar': p_exit_bar,
                'optimal_altitude_basis': (
                    'vacuum-optimised: the exit pressure is below the top of '
                    f'the ISA table ({ISA_TABLE_TOP_M / 1000.0:.3f} km '
                    'geopotential), so there is no finite matched altitude '
                    'inside the tabulated atmosphere'),
            }
        # Geopotansiyel -> geometrik irtifa (aynı dönüşümün tersi)
        r_earth = ISA_GEOPOTENTIAL_EARTH_RADIUS_M
        h_geom = h_geopot * r_earth / (r_earth - h_geopot)
        return {
            'optimal_altitude': float(h_geom),                 # m
            'nozzle_exit_pressure_bar': p_exit_bar,
            'optimal_altitude_basis': (
                'altitude where the ISA ambient pressure equals the nozzle '
                'exit pressure (fully expanded); US Standard Atmosphere 1976 '
                'inverted layer by layer'),
        }

    def _spray_angle_report(self):
        """Sprey açısı yaprakları — enjektör tasarım modelinin KENDİ çözümü.

        Kaynak sırası:
          1. ``atomization.spray_cone_half_angle_deg`` — swirl/coax-swirl ve
             pintle elemanlarda modül açıyı gerçekten çözer (swirl_solve K
             kökünden; pintle için theta = arccos(1/(1+TMR)), Cheng 2017).
          2. Çarpışmalı (impinging) elemanda sprey yelpazesinin yarı açısı
             çarpışma yarı açısıdır (2θ ≈ 60°, NASA SP-8089) — TANIM GEREĞİ
             bir tasarım seçimidir; ama iki jetin momentumu eşit olmadığında
             ortaya çıkan bileşke sprey EKSENİ eksenden sapar:
                 tan(beta) = tan(theta)·(M_ox − M_yakit)/(M_ox + M_yakit)
             (Sutton & Biblarz 9th ed. Böl. 8 momentum dengesi). Bu sapma
             ayrı bir yaprak olarak raporlanır ve girdilerle DEĞİŞİR.
          3. Modül açı vermiyorsa (showerhead, gaz-gaz) sayı uydurulmaz.
        """
        detail = self._injector_detail() or {}
        atom = detail.get('atomization') or {}
        cone = atom.get('spray_cone_half_angle_deg')
        out = {}
        if isinstance(cone, (int, float)):
            out['spray_angle_deg'] = float(cone)
            out['spray_angle_source'] = (
                'injector design model: solved spray cone half angle '
                f"({detail.get('injector_type')})")
            return out

        imp = ((detail.get('pattern') or {}).get('impingement') or {})
        half = imp.get('half_angle_deg')
        if isinstance(half, (int, float)):
            out['spray_angle_deg'] = float(half)
            out['spray_angle_source'] = (
                'injector design model: impingement half angle (2*theta '
                'design choice, NASA SP-8089) - single source with the '
                'injector pattern')
            mom = detail.get('momentum') or {}
            ratio = mom.get('momentum_ratio')
            if isinstance(ratio, (int, float)) and ratio >= 0:
                # M_yakit / M_ox = momentum_ratio  ->  bileşke sapma
                tan_beta = (np.tan(np.radians(float(half)))
                            * (1.0 - float(ratio)) / (1.0 + float(ratio)))
                out['spray_resultant_angle_deg'] = float(
                    np.degrees(np.arctan(tan_beta)))
                out['spray_resultant_angle_basis'] = (
                    'resultant spray axis tilt from the doublet momentum '
                    'balance: tan(beta) = tan(theta)*(M_ox - M_fuel)/'
                    '(M_ox + M_fuel) (Sutton & Biblarz 9th ed. Ch. 8); '
                    'zero means balanced jets')
            return out

        out['spray_angle_deg'] = None
        out['spray_angle_source'] = (
            'not_modelled: this injector element type has no spray cone '
            'solution in the injector design model')
        return out

    def _injector_detail(self):
        """``injector_design`` modülünün tam çıktısı ya da None (memoize).

        ÖH D25 · OH-D24-13. Genel yakalayıcı enjektör KAPI hatalarını da
        yutuyordu: ÖLÇÜLDÜ (once.json ``OH-D24-13.taninmayan_banana``)
        tanınmayan tipte 15 alanlık ayrıntı sessizce ``None`` oluyor, bu
        değeri okuyan atomizasyon/karışma zinciri de "modellenmedi" diyerek
        kapanıyordu — yani kullanıcı gerçek nedeni ("bu enjektör tipinin
        devre modeli yok") HİÇBİR yerde görmüyordu. Kapı hatası yükselir;
        kapı dışı arıza ``None`` döndürür ama nedeni ADIYLA saklanır
        (``_injector_detail_error``), çağıranların künyesi onu söyleyebilsin.
        """
        cached = getattr(self, '_injector_detail_memo', None)
        if cached is not None:
            return cached or None
        try:
            detail = (self.calculate_injector_design() or {}).get(
                'injector_design_detail')
        except (UnsupportedInjectorTypeError, UnsupportedPropellantPairError,
                UnsupportedPropellantDensityError):
            raise
        except Exception as exc:
            detail = None
            self._injector_detail_error = (
                f'{type(exc).__name__}: {str(exc)[:160]}')
        self._injector_detail_memo = detail or {}
        return detail

    def _injector_mixing_residence_time_s(self):
        """Enjektörün KARIŞMA KALIŞ süresi [s], ya da None (fail-closed).

        ÖH D32 · OH-D31-08 (defter P6B4-03) — İKİNCİ ZAMAN ÖLÇEĞİ ÇEVRİME
        ADAY OLARAK VERİLİR. Bu motor AYNI yanıtta iki karışım zaman ölçeği
        yayımlar:
          * ``combustion_analysis.mixing_time`` — enjektörün ikincil
            parçalanma (atomizasyon) süresi; chug çevriminin BUGÜN duyarlı
            gecikme τ olarak kullandığı ölçek (``_atomisation_time``);
          * ``injection_system.mixing_residence_time`` — enjektörün karışma
            KALIŞ süresi, L_silindirik / v_karışım (``calculate_injector_
            design``).
        Çevrim ikincisini HİÇ görmüyordu; hangi ölçeğin daha kararsız hüküm
        verdiği ölçülmüyor, yalnız ``tau_source`` CÜMLESİNDE "conservative"
        deniyordu. Beyan çözüm değildir: ölçek buradan okunup çevrime aday
        olarak verilir, çevrim her adayı FİİLEN koşar ve farkı yayımlar
        (``tau_choice_sensitivity``; çekirdek
        ``hrma.stability.chug.chug_tau_sensitivity``).

        TEK KAYNAK: sayı burada YENİDEN HESAPLANMAZ. Enjektör bloğunun KENDİ
        yayımladığı değer okunur ve saniyeye çevrilir (blok ms yayımlar,
        bkz. ``calculate_injector_design`` sonucunun
        ``mixing_residence_time`` alanı); ikinci bir karışma modeli
        kurulmaz.

        FAIL-CLOSED: değer çözülemediyse (None, sonlu değil ya da ≤ 0) None
        döner; çağıran aday listesine HİÇBİR ŞEY koymaz ve duyarlılık alanı
        hiç yayımlanmaz. Uydurma bir τ üretilmez.
        """
        # Özyineleme kapısı: bu erişim enjektör çözümünü çağırır; o çözümün
        # (bugün olmayan) bir yolu çevrim bloğuna geri dönerse sayı
        # uydurulmaz, aday hiç konmaz.
        if getattr(self, '_injector_mixing_tau_reentry', False):
            return None
        self._injector_mixing_tau_reentry = True
        try:
            ms = (self.calculate_injector_design() or {}).get(
                'mixing_residence_time')
        except Exception as exc:
            # Neden ADIYLA saklanır (``_injector_detail_error`` deseni):
            # duyarlılık alanının yokluğu sessiz kalmasın.
            self._injector_mixing_tau_error = (
                f'{type(exc).__name__}: {str(exc)[:160]}')
            return None
        finally:
            self._injector_mixing_tau_reentry = False
        try:
            saniye = float(ms) / 1000.0            # ms -> s (blok ms yayımlar)
        except (TypeError, ValueError):
            return None
        return saniye if np.isfinite(saniye) and saniye > 0.0 else None

    def _atomisation_time(self, rho_gas):
        """(t_atomizasyon [s], gerekçe) — ikincil parçalanma zaman ölçeği.

        Sıvı roket odasında en yavaş fiziksel süreç sıvı kolonun damlacığa
        dönüşmesi ve buharlaşmasıdır; karakteristik karışma zamanı bu ölçekten
        gelir. Aerodinamik (ikincil) parçalanma için boyutsuz süre bağıntısı

            t_b = T* · d_jet / v_rel · sqrt(rho_sivi / rho_gaz)

        (Pilch & Erdman 1987, Int. J. Multiphase Flow 13(6); Nicholls 1972 —
        torba/çok modlu rejimde T* ≈ 5, ``DROPLET_BREAKUP_TIME_CONST``).

        Jet çapı ve hızı enjektör tasarım modelinin KENDİ çözümünden alınır;
        bu modül çözülemezse süre uydurulmaz, None döner.
        """
        detail = self._injector_detail()
        ox = (detail or {}).get('ox_circuit') or {}
        d_jet_mm = ox.get('orifice_d_mm')
        v_jet = ox.get('velocity_m_s')
        if not d_jet_mm or not v_jet or not rho_gas or rho_gas <= 0:
            return None, ('not_modelled: the injector jet diameter/velocity '
                          'is unavailable, so the atomisation time scale is '
                          'not resolved')
        rho_l = float(getattr(self, 'rho_ox', 0.0) or 0.0)
        if rho_l <= 0:
            return None, 'not_modelled: liquid density unavailable'
        t_b = (DROPLET_BREAKUP_TIME_CONST * (float(d_jet_mm) * 1e-3)
               / float(v_jet) * np.sqrt(rho_l / float(rho_gas)))
        return float(t_b), (
            f'secondary (aerodynamic) breakup time t = T*·d_jet/v_jet·'
            f'sqrt(rho_l/rho_gas) with T* = {DROPLET_BREAKUP_TIME_CONST:g} '
            f'(Pilch & Erdman 1987; Nicholls 1972); d_jet = '
            f'{float(d_jet_mm):.3f} mm and v_jet = {float(v_jet):.1f} m/s '
            'come from the injector design model')

    def _injector_momentum_criterion(self):
        """(momentum_orani, hedef, gerekçe) — enjektör modelinin TEK kaynağı.

        Hazne analizi kendi momentum oranını ve kendi 'optimum'unu (2.0)
        tanımlıyordu; enjektör paneli aynı koşuda Rupe bandına göre başka bir
        oran ve hedef 1.0 gösteriyordu. Aynı yanıtta iki çelişen tanım vardı.
        Artık ikisi de ``injector_design.design_injector`` çıktısındaki
        ``momentum`` düğümünden okunur (Rupe, JPL Progress Report 20-195,
        1953; bant ``injector_design.MR_BAND``).

        Momentum ölçütü tanımsız olan eleman tiplerinde (showerhead,
        like-impinging, gaz-gaz) (None, None, gerekçe) döner — uydurma bir
        hedef üretilmez.
        """
        detail = self._injector_detail()
        mom = (detail or {}).get('momentum')
        if not isinstance(mom, dict):
            return None, None, (
                'not_modelled: the injector element type has no '
                'momentum-ratio design criterion')
        value = mom.get('momentum_ratio')
        if value is None:
            value = mom.get('tmr')
        target = mom.get('target')
        if not isinstance(target, (int, float)):
            target = None
        if value is None or target is None:
            return None, None, (
                'not_modelled: the injector momentum criterion is reported '
                'qualitatively for this element type')
        try:
            from hrma.engines.injector_design import MR_BAND
            band = f'{MR_BAND[0]:g}-{MR_BAND[1]:g}'
        except Exception:
            band = 'model band'
        return float(value), float(target), (
            'single source: injector_design momentum node (Rupe criterion, '
            f'JPL Progress Report 20-195, 1953; practical band {band}). The '
            'chamber analysis no longer defines a second momentum ratio or a '
            'second optimum.')

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
        # P3B2-02: aynı muhasebe tek kaynaktan (bkz. _chamber_volume_split);
        # burada da konverjan koni hacmi sayılır.
        (chamber_volume, convergent_volume, cylinder_volume,
         chamber_length, _l_conv_geo,
         l_star_achieved) = self._chamber_volume_split()
        
        # Combustion efficiency analysis
        #
        # ÖH defter P3B1-14 (Z5S/PK1) — KARDEŞ SATIR: burada
        # ``getattr(self, 'mdot_total', self.F / (300 * G_0))`` yazıyordu.
        # AST bekçisi ``300 * self.g0`` desenini arıyor, bu kopya ``G_0``
        # modül sabitini kullandığı için taramadan kaçıyordu — ama yasaklanan
        # yer tutucu (Isp = 300 s) aynı yer tutucudur ve ``getattr``ın
        # varsayılanı HER çağrıda hesaplanır. Yedek kaldırıldı.
        mdot_total = getattr(self, 'mdot_total', None)
        if mdot_total is None:
            raise UnsupportedPropellantPairError(
                'the detailed chamber analysis was requested before the '
                'nozzle solve set the propellant mass flow; HRMA does not '
                'substitute a representative Isp = 300 s placeholder '
                '(A3 closure).',
                fuel=getattr(self, 'fuel_type', None),
                oxidizer=getattr(self, 'oxidizer_type', None))
        rho_ox = getattr(self, 'rho_ox', 1200)
        rho_fuel = getattr(self, 'rho_fuel', 800)
        # DENETIM DUZELTMESI: Kalis suresi τ = ρ_gaz·V_c/ṁ ile hesaplanir.
        # Yanma odasinda akiskan GAZ fazindadir; sivi propellant yogunlugu
        # (~1000 kg/m³) kullanmak τ'yu ~130x fazla veriyordu (ve Damkohler
        # sayisini ayni oranda sisiriyordu). ρ_gaz = Pc/(R_gas·Tc) ideal gaz.
        rho_gas_chamber = (self.P_c * PA_PER_BAR) / ((R_UNIVERSAL / self.mw) * self.T_c)  # kg/m³
        residence_time = chamber_volume * rho_gas_chamber / mdot_total  # s

        # --- Karakteristik karışma (atomizasyon) süresi ---------------------
        # v2.6.26: burada `mixing_time = 0.002  # s typical for impinging`
        # yazıyordu ve bu tek sabit ÜÇ yaprağı birden donduruyordu: mixing_time,
        # Damköhler sayısı üzerinden combustion_efficiency ve stability
        # bloğundaki combustion_response_time. Artık süre enjektörün KENDİ
        # çözümünden gelir (jet çapı, jet hızı, sıvı ve gaz yoğunluğu).
        mixing_time, mixing_time_basis = self._atomisation_time(
            rho_gas_chamber)

        # --- Momentum oranı: TEK KAYNAK enjektör tasarım modeli -------------
        # Eski kod burada kendi momentum oranını ((ṁ_ox/ṁ_f)·sqrt(ρ_f/ρ_ox))
        # ve kendi 'optimum'unu (2.0) tanımlıyordu; enjektör paneli aynı
        # koşuda BAŞKA bir momentum oranı ve BAŞKA bir hedef (Rupe bandı,
        # hedef 1.0) gösteriyordu. İki tanım tek yanıtta çelişiyordu.
        mdot_ox = getattr(self, 'mdot_ox', mdot_total * self.MR / (1 + self.MR))
        mdot_fuel = getattr(self, 'mdot_fuel', mdot_total / (1 + self.MR))
        momentum_ratio, optimal_momentum_ratio, momentum_basis = \
            self._injector_momentum_criterion()
        if momentum_ratio is None or not optimal_momentum_ratio:
            # Enjektör tipinde momentum ölçütü tanımlı değil (showerhead,
            # like-impinging, gaz-gaz): uydurma bir karışım verimi üretilmez.
            mixing_efficiency = None
            mixing_efficiency_basis = (
                'not_modelled: the injector model defines no momentum-ratio '
                'criterion for this element type')
        else:
            dev = abs(momentum_ratio - optimal_momentum_ratio) \
                / optimal_momentum_ratio
            mixing_efficiency = float(max(0.85, min(0.98, 1.0 - 0.1 * dev)))
            mixing_efficiency_basis = (
                'penalty on the injector momentum-ratio deviation from its '
                'own design target, clamped to 0.85-0.98 (engineering '
                'correlation, not a first-principles mixing solution)')

        # --- Yanma verimi: TEK KAYNAK ---------------------------------------
        # Eski kod burada 1 − exp(−0.1·Da) bağıntısını kullanıp sonucu
        # [0.90, 0.99] bandına kelepçeliyordu. Kelepçe HER motorda alt sınıra
        # oturuyordu (Da ~1 mertebesinde 1 − exp(−0.1) ≈ 0.10), yani yaprak
        # kullanıcının hiçbir girdisiyle oynamıyordu; üstelik 0.1 katsayısı
        # kaynaksızdı ve aynı yanıtta üçüncü bir 'yanma verimi' üretiyordu
        # (kullanıcının η_c* girdisi ve enjektör panelinin değeriyle çelişen).
        # Yanma verimi artık TESLİM zincirinin η_c*'ından okunur.
        combustion_efficiency = float(getattr(self, 'eta_c_star', 1.0) or 1.0)
        # P3B2-08: künye TEK tanım noktasından (self.eta_c_star_source);
        # koşul artık anahtarın varlığı değil, kabul edilen girdidir.
        combustion_efficiency_source = str(getattr(
            self, 'eta_c_star_source',
            'not supplied -> ideal energy release (1.000) assumed'))
        damkohler_number = (residence_time / mixing_time
                            if mixing_time and mixing_time > 0 else None)

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
                'mixing_time': (mixing_time * 1000 if mixing_time else None),
                'mixing_time_basis': mixing_time_basis,
                'damkohler_number': damkohler_number,
                'damkohler_basis': ('chamber residence time / atomisation '
                                    'time'),
                'mixing_efficiency': (mixing_efficiency * 100
                                      if mixing_efficiency is not None
                                      else None),
                'mixing_efficiency_basis': mixing_efficiency_basis,
                'combustion_efficiency': combustion_efficiency * 100,  # %
                'combustion_efficiency_source': combustion_efficiency_source,
                # P3B2-08: bu blok YÜZDE yayımlar, injection_system/
                # injector_design KESİR yayımlar; sözleşme adın yanında.
                'combustion_efficiency_unit': 'percent',
                'momentum_ratio': momentum_ratio,
                'optimal_momentum_ratio': optimal_momentum_ratio,
                'momentum_criterion_basis': momentum_basis,
            },
            'stability_analysis': self._stability_assessment(
                a_chamber, chamber_length, chamber_diameter, mixing_time,
                # P6B4-01 (ÖH D17): chug çevrimi ÇİZİLEN L*'ı tüketir.
                # ÖLÇÜLDÜ (once.json P6B4-01): tau_c = L*/(c*·Γ²) İSTENEN
                # 1,2 m ile kuruluyordu ve 25 kN / 250 kN / 1 MN üç koşuda
                # bit-aynı 0,001596822 s çıkıyordu — oysa aynı yanıtın
                # çizdiği hazne 1,200 / 3,472 / 5,743 m L* veriyor (+%189,
                # +%379). Kamara zaman sabiti FİİLEN ÇİZİLEN hacmin
                # özelliğidir (V_c/(A_t·c*·Γ²)); istenen değer çizilmeyen
                # bir hazneye aitti ve hüküm o yüzden ters dönüyordu.
                l_star_m=l_star_achieved, residence_time_s=residence_time)
        }

    def _stability_assessment(self, a_chamber, chamber_length, chamber_diameter,
                              mixing_time, l_star_m=None,
                              residence_time_s=None):
        """Yanma kararlılığı: HESAPLANABİLİR ölçütler + dürüst 'unknown'.

        SAHA HATASI (2026-07-23 denetimi): burada 'stability_rating' HER motor
        için sabit 'Stable' yazıyordu ve yanına sabit bir sönümleme mekanizması
        listesi konuyordu. Girdilerden bağımsız bir "kararlı" hükmü, roket
        yazılımında verilebilecek en tehlikeli sahte çıktılardan biridir.

        Artık yalnız hesaplanabilir olan hesaplanır:
          - 1L (boyuna) mod: f = a / (2·L)          [açık-açık boru yaklaşımı]
          - 1T (ilk teğetsel) mod: f = α·a/(π·D), α = J'_1'in ilk sıfırı
          - kamara akustik mod TABLOSU (merkezî modül, F2b-2)
          - chug (düşük frekans) marjı: ΔP_enjektör / Pc oran kuralı
          - chug ÇEVRİMİ: nötr eğri + baskın kök (hrma.stability.chug)
        Yüksek frekanslı akustik kararlılık (akustik-yanma bağlaşımı) bu
        modelde ÇÖZÜLMÜYOR; 'acoustic_analysis' alanı bunu açıkça söyler ve
        GENEL hüküm hâlâ 'unknown'dır — chug çevriminin hükmü KAPSAM
        ETİKETLİDİR ve yalnız kendi mekanizmasını bağlar. Sönümleme
        mekanizmaları da tasarım TAVSİYESİDİR, motorda var oldukları iddia
        edilmez.

        F2b-2 GÖÇÜ (17 Ağu 2026) — kopya akustik öldü
        ---------------------------------------------
        Bu metot 1L ve 1T'yi KENDİ İÇİNDE hesaplıyordu (``a/(2L)`` ve elle
        yazılmış ``1.8412``); hibrit ve katı motorlar aynı sayıları merkezî
        ``hrma.analysis.acoustic_modes``ten alıyordu. Üç motordan biri ayrı
        hesaplıyordu, yani depoda akustiğin İKİ tanımı vardı. Artık üçü de
        merkezden okur. ÖLÇÜLEN FARK (manifest:
        ``tests/test_sivi_akustik_gocu.py``): 1L bit-özdeş (aynı formül, aynı
        girdi); 1T'de bağıl −8,81e-06 — çünkü merkez, kökü
        ``scipy.special.jnp_zeros`` ile ÜRETİYOR (1,8411837813406593) ve eski
        yerel sabit onun 5 haneye yuvarlanmışıydı (1,8412). Fark beklenen
        model farkıdır ve manifestte adıyla kayıtlıdır; beklenmeyen bir fark
        çıksa test kırmızı olur.
        """
        # 1L / 1T ARTIK MERKEZDEN: aynı formüller, tek tanım yeri.
        # (Merkezin 1T'si f = a·α/(π·D), α = jnp_zeros(1,1)[0]; 1L'i
        #  f = q·a/(2L), q = 1 — eski yerel ifadelerle cebirsel olarak aynı.)
        alpha_1t = transverse_root(1, 0)
        f_1l = (longitudinal_frequency(a_chamber, chamber_length, 1)
                if chamber_length > 0 else None)
        f_1t = (transverse_frequency(a_chamber, chamber_diameter, alpha_1t)
                if chamber_diameter > 0 else None)
        # ΔP/Pc tek kaynaktan gelir: kullanıcı girdisi varsa o, yoksa enjektör
        # tipinin tablo değeri (_injector_dp_fraction — çevrim çözücüsü de
        # aynı fonksiyonu kullanır, iki ayrı doğru olmaz).
        try:
            dp_pc = float(self._injector_dp_fraction())
        except Exception:
            dp_pc = None
        if dp_pc is None or not np.isfinite(dp_pc) or dp_pc <= 0:
            rating, reason = 'unknown', (
                'the injector pressure drop is unknown, so the chug margin '
                'could not be evaluated')
        elif dp_pc >= CHUG_DP_PC_RECOMMENDED_LIQUID:
            rating, reason = 'chug_margin_ok', (
                'dP/Pc = %.3f, above the recommended threshold (%.2f) of the '
                'classical design rule' % (dp_pc,
                                           CHUG_DP_PC_RECOMMENDED_LIQUID))
        elif dp_pc >= CHUG_DP_PC_MIN_LIQUID:
            rating, reason = 'chug_margin_marginal', (
                'dP/Pc = %.3f, between the lower bound (%.2f) and the '
                'recommended threshold (%.2f)' % (dp_pc,
                                                  CHUG_DP_PC_MIN_LIQUID,
                                                  CHUG_DP_PC_RECOMMENDED_LIQUID))
        else:
            rating, reason = 'chug_risk', (
                'dP/Pc = %.3f, below the lower bound (%.2f) of the classical '
                'design rule - low-frequency (chug) instability risk'
                % (dp_pc, CHUG_DP_PC_MIN_LIQUID))

        # --- MERKEZÎ mod tablosu (F2b-2): hibrit/katı ile AYNI modül -------
        modes_block = self._acoustic_modes_block(
            chamber_diameter, chamber_length, dp_pc)
        # --- chug ÇEVRİMİ (F2b-2): oran kuralı değil, gerçek kök yeri ------
        chug_loop = self._chug_loop_block(dp_pc, mixing_time, l_star_m, rating,
                                          residence_time_s)

        return {
            'acoustic_frequency': f_1l,                 # Hz (1L modu)
            'first_longitudinal_hz': f_1l,
            'first_tangential_hz': f_1t,
            # Yanma tepki süresi: Crocco-Cheng n-tau modelindeki duyarlı zaman
            # gecikmesi tau pratikte atomizasyon/buharlaşma ölçeğidir
            # (Harrje & Reardon, NASA SP-194 Böl. 4). Buraya eskiden sabit
            # 2 ms geliyordu (mixing_time'ın sabit değeri); artık enjektörün
            # kendi jet çözümünden gelen atomizasyon süresidir. Basınç
            # duyarlılık üsteli n ÇÖZÜLMEZ, aşağıda öyle bildirilir.
            'combustion_response_time': (mixing_time * 1000
                                         if mixing_time else None),   # ms
            'combustion_response_time_basis': (
                'atomisation (secondary breakup) time from the injector jet '
                'solution, used as the Crocco-Cheng sensitive time lag tau '
                '(NASA SP-194)' if mixing_time else
                'not_modelled (atomisation time unresolved)'),
            'pressure_interaction_index_n': 'not_modelled',
            'pressure_interaction_index_note': (
                'the Crocco-Cheng pressure sensitivity index n is not solved; '
                'only the time lag tau is reported'),
            'injector_dp_over_pc': dp_pc,
            'chug_rating': rating,
            'chug_basis': reason,
            'chug_threshold_source': CHUG_THRESHOLD_SOURCE,
            # 1L/1T'nin hangi modülden geldiği ADIYLA yazılır: bu alan
            # olmadan "merkezî modüle geçildi" iddiası çıktıdan okunamaz.
            'mode_source': (
                'hrma.analysis.acoustic_modes (longitudinal_frequency, '
                'transverse_frequency, transverse_root) — the same module '
                'the hybrid and solid solvers call. The first tangential '
                'root is computed from the Bessel derivative zero '
                '(scipy.special.jnp_zeros), not from a hand-written '
                'constant.'),
            'first_tangential_alpha': float(alpha_1t),
            # Merkezî mod TABLOSU (10 en düşük mod, bant sınıfları, chug
            # raporu). Bu blok F2c panelinin veri kaynağıdır.
            'acoustic_modes': modes_block,
            # Gerçek chug çevrimi (hrma.stability.chug) — oran kuralı ile
            # ilişkisi 'rule_vs_loop' alanında ÖLÇÜLÜ olarak beyanlı.
            'chug_loop': chug_loop,
            # Genel kararlılık hükmü VERİLMEZ: yüksek frekanslı akustik
            # bağlaşım modellenmiyor, dolayısıyla "kararlı" denemez.
            # chug_loop.verdict bir hükümdür ama KAPSAM ETİKETLİDİR ve
            # yalnız kendi mekanizmasını bağlar (F2a karar 1).
            'stability_rating': 'unknown',
            'stability_rating_basis': (
                'No overall stability verdict is issued: high-frequency '
                'combustion-acoustic coupling is not solved. The chug loop '
                'below DOES issue a verdict, but it is scope-labelled '
                '(verdict_scope) and binds only the feed-coupled '
                'low-frequency mechanism.'),
            'acoustic_analysis': 'not_modelled',
            'acoustic_analysis_note': (
                'acoustic-combustion coupling (high-frequency instability) '
                'is not solved in this model; only the mode frequencies '
                '(from the central acoustic module) and the chug loop are '
                'reported'),
            'damping_recommendations': ['Acoustic liners', 'Baffles',
                                        'Injector face pattern'],
        }

    # ------------------------------------------------------------------
    # F2b-2 yardımcıları: merkezî akustik tablo + gerçek chug çevrimi
    # ------------------------------------------------------------------
    def _acoustic_modes_block(self, chamber_diameter, chamber_length, dp_pc):
        """Kamara akustik mod tablosu — hibrit/katı ile AYNI merkezî modül.

        Geometri, ses hızı ve gaz özellikleri bu koşunun KENDİ çözümünden
        gelir (uydurma yok). Modül girdiyi reddederse sayı üretilmez, gerekçe
        döner (hibritteki ``_acoustic_modes_block`` deseninin aynısı).
        """
        basis = (
            'Rigid-wall closed-closed cylindrical cavity modes from '
            'hrma.analysis.acoustic_modes. Geometry is the solved chamber '
            'inner diameter and the solved chamber length (V_c/A_c); the gas '
            'is the equilibrium chamber state (gamma, T_c, R = R_u/MW) of '
            'this run. The cavity is idealised as a plain cylinder: the '
            'injector face cavity, the convergent nozzle volume and any '
            'baffle are NOT part of the acoustic model.')
        try:
            res = AcousticModeAnalyzer().analyze(
                chamber_temperature=float(self.T_c),
                gamma=float(self.gamma),
                gas_constant=float(R_UNIVERSAL / self.mw),
                chamber_diameter=float(chamber_diameter),
                chamber_length=float(chamber_length),
                chamber_pressure=float(self.P_c),
                injector_dp_ratio=(float(dp_pc) if dp_pc and
                                   np.isfinite(dp_pc) and dp_pc > 0
                                   else None))
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (f'the acoustic-mode analyser rejected the chamber '
                           f'state: {exc}'),
            }
        res = dict(res)
        res['status'] = 'modelled'
        res['_basis'] = basis
        # --- ÖH defter P17B3-03 (D23) — LÜLE GİRİŞİ ORTALAMA AKIŞ MACH'I ---
        # ÖLÇÜLDÜ (P17 turu, B3-rapor.md): Analiz Merkezi'nin akustik
        # kiracısı hibrit ve katı sonucundan dört alanı da DOLU alıyor,
        # sıvıda yalnız ``nozzle_entrance_mach`` BOŞ kalıyor ve panel isteği
        # (doğru biçimde, fail-closed) reddediyor: "Nozzle entrance mean-flow
        # Mach M_N ... The request was NOT sent". Yani sıvı kullanıcısı,
        # öteki iki motorda tek tıkla koşan bir analizi ancak M_N'i kendisi
        # bularak koşturabiliyordu - üstelik sayfanın elinde onu çözecek her
        # büyüklük ZATEN vardı.
        # Sayı UYDURULMAZ, ÇÖZÜLÜR: Culick & Yang'in kendi tanımı olan
        # kütle-akısı oranı kullanılır (hibrit/katı bağlamalarındaki
        # ``mach_basis`` ile AYNI özdeşlik):
        #     M_N = mdot_toplam / (rho_c · a · S_c),  rho_c = P_c/(R·T_c)
        # Kavite kesiti S_c, mod tablosunun kurulduğu AYNI idealleştirilmiş
        # silindirin kesitidir (hazne iç çapı) - iki blok aynı lüle için
        # ayrışamaz. Herhangi bir büyüklük çözülmemişse alan KONMAZ.
        try:
            mdot_toplam = float(getattr(self, 'mdot_total', 0.0) or 0.0)
            a_ses = float(res.get('sound_speed_m_s') or 0.0)
            s_c = np.pi * (float(chamber_diameter) ** 2) / 4.0
            rho_c = ((float(self.P_c) * PA_PER_BAR)
                     / ((R_UNIVERSAL / float(self.mw)) * float(self.T_c)))
            if mdot_toplam > 0 and a_ses > 0 and s_c > 0 and rho_c > 0:
                res['chamber_gas_density_kg_m3'] = float(rho_c)
                res['acoustic_cavity_area_m2'] = float(s_c)
                res['mass_flow_kg_s'] = float(mdot_toplam)
                res['mean_flow_mach_M_N'] = float(
                    mdot_toplam / (rho_c * a_ses * s_c))
                res['mach_basis'] = (
                    'M_N = mdot_total/(rho_c*a*S_c) is a mass-flux ratio, '
                    'exactly how Culick & Yang define the mean-flow group '
                    '(their M_N = M_b*S_b/S_c). rho_c = P_c/(R*T_c) with '
                    'R = R_u/MW is the SAME chamber gas state the mode table '
                    'above uses, and S_c is the cross-section of the SAME '
                    'idealised cylinder (chamber inner diameter), so the two '
                    'blocks cannot disagree about one nozzle. The '
                    'quasi-steady short-nozzle damping limit assumes a small '
                    'mean-flow Mach number; M_N is published so that '
                    'assumption can be checked against this engine. This is '
                    'the mean-flow group only - HRMA does NOT solve a liquid '
                    'acoustic damping budget and issues no stability verdict '
                    'on this path.')
        except Exception as exc:
            res['mean_flow_mach_M_N'] = None
            res['mach_basis'] = (
                f'the mean-flow Mach group could not be solved on this run '
                f'({type(exc).__name__}); no number is invented in its place')
        return res

    def _feed_line_inertance_inputs(self):
        """Besleme hattı ataleti girdileri — KARAR 5: FORMA ALAN EKLENMEDİ.

        Çözücü tarafı hazırdır: kullanıcı (şimdilik yalnız API/override
        yoluyla) gerçek hat uzunluğunu ve kesitini verirse chug çevrimi
        ikinci mertebe (ataletli) forma geçer. Vermezse ataletsiz koşar ve
        bunu beyan eder. Hiçbir yerleşim varsayımı (ör. 2,5 m hat) buraya
        KOPYALANMAZ — uydurma varsayılan yasağı.

        Returns:
            (tau_f_s veya None, beyan sözlüğü veya None)
        """
        length = self._override_val('feed_line_length_m', 0.05, 50.0,
                                    'Feed line length', ' m')
        if length is None:
            return None, None
        # --- ÖH D22 / P6B4-05 · ZİNCİR YANITIN KENDİ HATTINI KULLANIR -----
        # ÖLÇÜLDÜ (raw/OH/D22/sivi/a1/once_ham.json): kullanıcı hat çapını
        # 12,0 mm verirken AYNI yanıt kendi besleme hattını
        # ``feed_system.pressure_drops.{oxidizer,fuel}_line.line_diameter_mm``
        # = 25,0 mm (standart boru merdivenine yuvarlanmış) olarak
        # yayımlıyordu. τ_f ∝ L/A, yani ∝ 1/d²: 12,0 ⟷ 25,0 çapı τ_f'yi
        # 4,3 kat oynatır ve yayımlanan chug frekansı 14,281 / 47,025 /
        # 88,156 Hz arasında (6,2×) geziniyordu. İki çap AYNI fiziksel hattı
        # anlatıyor ve tek yanıtta yan yana duruyorlardı; hangisinin hüküm
        # ürettiği hiçbir yerde YAZMIYORDU.
        #
        # İki kapanış:
        #   1) Kullanıcı kesit vermezse zincir artık YANITIN KENDİ çözülmüş
        #      hattını kullanır (uydurma değil: aynı sayıyı basınç düşümü
        #      zinciri ve su koçu bloğu da kullanıyor). Uzunluk hâlâ
        #      kullanıcıdan gelir — FEED_LINE_LENGTH_DEFAULT_M buraya
        #      KOPYALANMAZ, yerleşim varsayımı bir kararlılık hükmünü
        #      sessizce sürükleyemez.
        #   2) Kullanıcı kesit VERİRSE ve bu, çözülmüş hattan sapıyorsa
        #      çelişki adıyla yayımlanır (``solved_line_cross_check``) ve
        #      hangi çapın hükmü ürettiği açıkça yazılır.
        cozulmus_d_mm = self._cozulmus_hat_capi_mm()
        area = self._override_val('feed_line_area_m2', 1e-8, 1.0,
                                  'Feed line flow area', ' m²')
        kesit_kaynagi = 'user input (feed_line_area_m2)'
        kullanici_d_mm = None
        if area is None:
            kullanici_d_mm = self._override_val(
                'feed_line_diameter_mm', 0.5, 500.0,
                'Feed line inner diameter', ' mm')
            if kullanici_d_mm is not None:
                area = np.pi * (float(kullanici_d_mm) / 1000.0) ** 2 / 4.0
                kesit_kaynagi = 'user input (feed_line_diameter_mm)'
        if area is None and cozulmus_d_mm:
            area = np.pi * (float(cozulmus_d_mm) / 1000.0) ** 2 / 4.0
            kesit_kaynagi = (
                'this run own solved feed line inner diameter '
                f'({float(cozulmus_d_mm):.4g} mm, feed_system.pressure_drops'
                '.*.line_diameter_mm) - the SAME line the pressure-drop '
                'chain and the water-hammer block already use')
        if area is None:
            return None, None
        mdot = getattr(self, 'mdot_total', None)
        dp_bar = None
        try:
            dp_bar = float(self._injector_dp_fraction()) * float(self.P_c)
        except Exception:
            dp_bar = None
        if not (mdot and np.isfinite(mdot) and mdot > 0) or \
                not (dp_bar and np.isfinite(dp_bar) and dp_bar > 0):
            return None, None
        from hrma.stability.chug import feed_inertance_time_constant
        tau_f = feed_inertance_time_constant(
            line_length_m=float(length), line_area_m2=float(area),
            mass_flow_kg_s=float(mdot), dp_injector_Pa=dp_bar * PA_PER_BAR)
        kullanilan_d_mm = float(np.sqrt(4.0 * float(area) / np.pi)) * 1000.0
        yanki = {
            'line_length_m': float(length),
            'line_area_m2': float(area),
            'line_diameter_mm': kullanilan_d_mm,
            'line_area_source': kesit_kaynagi,
            'mass_flow_kg_s': float(mdot),
            'dp_injector_Pa': dp_bar * PA_PER_BAR,
            '_basis': (
                'Feed line length is supplied by the caller; the flow area is '
                'named in line_area_source. The mass flow is this run\'s '
                'TOTAL propellant flow and the pressure drop is the lumped '
                'injector drop, consistent with the single lumped injector '
                'used for J. Separate oxidiser/fuel line dynamics are NOT '
                'modelled (that is a coupled two-line problem).'),
        }
        # --- P6B4-05 · ÇAPRAZ DENETİM (aynı hat, iki sayı olamaz) ---------
        if cozulmus_d_mm:
            _sapma = ((kullanilan_d_mm - float(cozulmus_d_mm))
                      / float(cozulmus_d_mm) * 100.0)
            yanki['solved_line_cross_check'] = {
                'solved_line_diameter_mm': float(cozulmus_d_mm),
                'diameter_used_by_chug_mm': kullanilan_d_mm,
                'deviation_pct': _sapma,
                'agreement': ('agree' if abs(_sapma) <= 1e-6 else 'disagree'),
                'tau_f_sensitivity': (
                    'tau_f scales as L/A, i.e. as 1/d^2: the ratio of the two '
                    'diameters squared is the factor by which the published '
                    'chug frequency would move if the other diameter were '
                    'used '
                    f'({(float(cozulmus_d_mm) / kullanilan_d_mm) ** 2:.4g}x).'),
                '_basis': (
                    'The same physical feed line must not carry two different '
                    'diameters in one answer. This run solves the feed line '
                    'to a standard pipe size (feed_system.pressure_drops.*.'
                    'line_diameter_mm); if the caller overrides the chug '
                    'inertance diameter, BOTH numbers are published here with '
                    'the one that actually produced the verdict named in '
                    'line_area_source. Nothing is silently preferred.'),
            }
        else:
            yanki['solved_line_cross_check'] = {
                'status': 'NOT_EVALUATED',
                '_basis': ('this run did not solve a feed line diameter, so '
                           'there is nothing to cross-check against and no '
                           'diameter is invented'),
            }
        return tau_f, yanki

    def _cozulmus_hat_capi_mm(self):
        """Bu koşunun KENDİ çözdüğü besleme hattı iç çapı [mm] ya da None.

        ÖH D22 / P6B4-05. Sayı UYDURULMAZ: yalnız basınç düşümü zincirinin
        gerçekten çözdüğü çap döner (oksitleyici hattı; iki hat farklıysa
        chug'ın toplu (lumped) tek hat kabuliyle tutarlı olan taraf odur —
        toplu enjektör düşümü de oksitleyici kolundan alınır). Zincir
        çözülmediyse None.
        """
        drops = getattr(self, '_feed_drops_cache', None)
        if not isinstance(drops, dict):
            try:
                drops = self._calculate_feed_system_pressure_drops()
            except Exception:
                return None
            if isinstance(drops, dict):
                self._feed_drops_cache = drops
        if not isinstance(drops, dict):
            return None
        hat = drops.get('oxidizer_line') or drops.get('fuel_line')
        if not isinstance(hat, dict):
            return None
        d = hat.get('line_diameter_mm')
        try:
            d = float(d)
        except (TypeError, ValueError):
            return None
        return d if np.isfinite(d) and d > 0 else None

    def _chug_loop_block(self, dp_pc, mixing_time, l_star_m, rule_rating,
                         residence_time_s=None):
        """Gerçek chug çevrimi (hrma.stability.chug) + oran kuralıyla İLİŞKİ.

        Oran kuralı (ΔP/Pc ≥ 0,20) yalnız enjektör kazancına bakar; gecikmeyi
        (τ) ve kamara zaman sabitini (τ_c) HİÇ görmez. Çevrim üçünü birden
        kullanır. İkisi çeliştiğinde HRMA birini diğerine EZDİRMEZ: ikisi de
        yayımlanır ve çelişki adıyla beyan edilir (``rule_vs_loop``).
        """
        missing = []
        if not (dp_pc and np.isfinite(dp_pc) and dp_pc > 0):
            missing.append('injector_dp_over_pc (J = dP_inj/Pc)')
        tau_s = (float(mixing_time)
                 if mixing_time and np.isfinite(mixing_time)
                 and mixing_time > 0 else None)
        if tau_s is None:
            missing.append('sensitive time lag tau (atomisation time)')
        l_star = (float(l_star_m) if l_star_m and np.isfinite(l_star_m)
                  and l_star_m > 0 else None)
        if l_star is None:
            missing.append('l_star_m')
        c_star = getattr(self, 'c_star', None)
        if not (c_star and np.isfinite(c_star) and c_star > 0):
            missing.append('c_star_m_s')
            c_star = None
        if missing:
            return {
                'status': 'NOT_EVALUATED',
                'missing_inputs': missing,
                '_basis': (
                    'The feed-coupled chug loop needs J, the sensitive time '
                    'lag tau, L* and c*. One or more were not solved on this '
                    'run, so no loop result is fabricated.'),
            }

        from hrma.stability.chamber import chamber_time_constant
        from hrma.stability.chug import assess_chug

        try:
            tau_c = chamber_time_constant(l_star_m=l_star,
                                          c_star_m_s=float(c_star),
                                          gamma=float(self.gamma))
            tau_f, feed_echo = self._feed_line_inertance_inputs()
            # ÖH D22 / P6B4-04: kısma haritası aynı çevrimi KENDİ J'siyle
            # yeniden koşabilsin diye çevrim girdileri saklanır. Sayı
            # KOPYALANMAZ, girdi saklanır — harita hükmü kendisi üretir.
            self._chug_loop_inputs = {
                'tau_s': float(tau_s),
                'tau_c_s': float(tau_c['tau_c_s']),
                'tau_f_s': (None if tau_f is None else float(tau_f)),
                'feed_line': feed_echo,
            }
            # ÖH D32 · OH-D31-08 (defter P6B4-03) — SEÇİMİN BEDELİ ÖLÇÜLÜR.
            # Aynı yanıtta yayımlanan İKİNCİ karışım zaman ölçeği
            # (enjektörün karışma kalış süresi) çevrime ADAY olarak verilir;
            # çekirdek her adayı AYNI çevrimle fiilen koşar ve hangisinin
            # daha kararsız hüküm verdiğini SAYIYLA söyler
            # (``tau_choice_sensitivity``). Fail-closed: aday çözülemezse
            # liste boş kalır ve alan HİÇ konmaz (uydurma aday yok).
            aday_taular = {}
            tau_karisim = self._injector_mixing_residence_time_s()
            if tau_karisim is not None:
                aday_taular['mixing_residence_time'] = tau_karisim
            loop = assess_chug(dp_ratio_j=float(dp_pc), tau_s=tau_s,
                               tau_c_s=tau_c['tau_c_s'], tau_f_s=tau_f,
                               feed_line=feed_echo,
                               alternative_taus=(aday_taular or None))
        except Exception as exc:
            return {
                'status': 'NOT_EVALUATED',
                'reason': f'the chug loop rejected the inputs: {exc}',
                '_basis': ('No number is fabricated when the core refuses an '
                           'input.'),
            }

        loop = dict(loop)
        loop['status'] = 'modelled'
        loop['chamber_time_constant'] = tau_c
        loop['tau_source'] = (
            'atomisation (secondary breakup) time of this run\'s injector '
            'solution, used as the Crocco-Cheng sensitive time lag; its own '
            'uncertainty propagates DIRECTLY into the verdict below. This is '
            'a CONSERVATIVE choice and its direction is known: Crocco\'s tau '
            'is only the pressure-SENSITIVE part of the total delay, while '
            'the breakup time is the full time scale, so substituting it can '
            'only move the verdict toward "unstable", never away from it '
            '(Crocco & Cheng, AGARDograph 8, 1956). That conservatism is '
            'stated RELATIVE TO Crocco\'s pressure-sensitive sub-delay, and '
            'it says nothing about the OTHER mixing time scale this same '
            'answer publishes (the injector mixing residence time). Which of '
            'the two gives the less stable verdict is not asserted here - it '
            'is MEASURED, candidate by candidate, in '
            '\'tau_choice_sensitivity\' below (ÖH D32 / OH-D31-08); when '
            'that field names a candidate other than \'selected\' as '
            '\'most_conservative\', the run\'s selected tau is NOT the '
            'most conservative of the published scales.')
        # τ_c'nin İKİNCİ yolu: bu koşunun kendi kalış süresi. Cebirsel olarak
        # AYNI büyüklüktür (ρV/ṁ = L*/(c*Γ²), çünkü ṁ = P_c A_t/c* ve
        # ρ = P_c/(RT), R·T = (c*Γ)²). Eşit ÇIKMIYORSA fark SESSİZ KALMAZ.
        #
        # ÖH D22 / P6B4-02: kalıntının gerekçesi artık TAHMİN DEĞİL ÖLÇÜM.
        # İki terim burada, bu koşunun KENDİ sayılarından hesaplanır
        # (bkz. LIQUID_TAU_C_RESIDUAL künyesi):
        #   1/C_D  ve  (c*Γ)²/(R·T)
        # Çarpımları yayımlanan oranı yeniden üretmiyorsa artan
        # ``unexplained_pct`` alanında ADIYLA durur — gizlenmez.
        if (residence_time_s and np.isfinite(residence_time_s)
                and residence_time_s > 0):
            terimler = None
            try:
                from hrma.stability.chamber import rt_from_cstar
                _cd = float(self.CD_throat)
                _rt_cstar = float(rt_from_cstar(float(c_star),
                                                float(self.gamma)))
                _rt_direct = float(
                    (R_UNIVERSAL / float(self.mw)) * float(self.T_c))
                if _cd > 0 and _rt_direct > 0:
                    _cd_terim = 1.0 / _cd
                    _rt_terim = _rt_cstar / _rt_direct
                    _oran = float(residence_time_s) / tau_c['tau_c_s']
                    _aciklanan = _cd_terim * _rt_terim
                    terimler = {
                        'discharge_coefficient_term': _cd_terim,
                        'throat_discharge_coefficient': _cd,
                        'rt_identity_term': _rt_terim,
                        'rt_from_cstar_m2_s2': _rt_cstar,
                        'rt_from_cea_m2_s2': _rt_direct,
                        'rt_identity_break_pct': (
                            (_rt_direct - _rt_cstar) / _rt_cstar * 100.0),
                        'explained_ratio': _aciklanan,
                        'unexplained_pct': ((_oran - _aciklanan)
                                            / _aciklanan * 100.0),
                        '_basis': TAU_C_RESIDUAL_DECOMPOSITION_BASIS,
                    }
            except Exception:
                terimler = None
            loop['tau_c_vs_residence_time'] = tau_c_vs_residence_time_field(
                tau_c['tau_c_s'], residence_time_s, LIQUID_TAU_C_RESIDUAL,
                residual_terms=terimler)
        # --- oran kuralı ile çevrimin İLİŞKİSİ (ölçülür, varsayılmaz) ---
        rule_says_safe = rule_rating in ('chug_margin_ok',
                                         'chug_margin_marginal')
        loop_says_stable = loop.get('verdict') == 'stable'
        loop['rule_vs_loop'] = {
            'ratio_rule_rating': rule_rating,
            'loop_verdict': loop.get('verdict'),
            'agreement': ('agree' if rule_says_safe == loop_says_stable
                          else 'disagree'),
            'interpretation': (
                'The classical ratio rule tests ONLY the injector gain '
                'J = dP_inj/Pc; it is blind to the sensitive time lag tau '
                'and to the chamber time constant tau_c, so it cannot '
                'distinguish a fast-burning large chamber from a '
                'slow-burning small one. The loop uses all three. Where the '
                'two disagree, HRMA publishes BOTH and lets neither '
                'override the other: the loop is the model with more '
                'physics, but its verdict is only as good as tau (an '
                'atomisation correlation, not a measurement), while the rule '
                'is an engineering rule of thumb with decades of practice '
                'behind it and no explicit validity envelope.'),
        }
        return loop

    def solve_throttle_map(self, fractions=THROTTLE_SCAN_FRACTIONS):
        """Kısma haritası: %40-100 itki bandında çalışma noktaları.

        Kısma, oda basıncını düşürür; bu da enjektör ΔP/Pc oranını ve dolayısıyla
        chug (düşük frekans) kararlılık marjını değiştirir. Sabit-alanlı bir
        enjektörde ΔP debinin karesiyle ölçeklendiğinden (ΔP ∝ ṁ², SPI orifis
        bağıntısı) kısılan motorda ΔP, Pc'den DAHA HIZLI düşer — bu yüzden
        derin kısmada chug riski artar. Klasik sonuç budur ve NASA SP-8089'un
        kısılabilir motorlar için ayrı ΔP tavsiyesinin nedenidir.

        Her nokta motorun KENDİ zinciriyle (aynı CEA köprüsü, aynı teslim
        verim oranı, aynı ε) yeniden çözülür; ayrı bir basitleştirilmiş model
        yoktur. Çözülemeyen sayı uydurulmaz. ÖH D24 / P3B4-13 düzeltmesi —
        bu cümle eskiden "çözülemeyen nokta atlanır ve 'skipped' listesinde
        gerekçesiyle görünür" diyordu ve YANLIŞTI: 'skipped' hiçbir zaman
        doldurulmuyordu, çözülemeyen satır ise atlanmıyor, ``thrust_n=None``
        ve kendi ``thrust_basis``ıyla YAYIMLANIYORDU. Gerçek sözleşme:
        haritadan DÜŞEN istek (aralık dışı kısma oranı) 'skipped'te
        gerekçesiyle durur; yayımlanan ama itkisi çözülemeyen satır kendi
        ``thrust_basis``ında nedenini söyler ve ``points_without_thrust``ta
        sayılır (bkz. ``skipped_basis``).

        Dönen sözlük 'throttle_map' anahtarıyla sonuca girer.
        """
        # v2.6.26 — TARAMA KULLANICININ ALT SINIRINA UZANIR.
        # Sabit ızgara %40'ta başlıyordu; kullanıcı min_throttle=%20 girse
        # bile "en derin kısmada chug riski" hükmü %40'ta değerlendirilmiş
        # oluyordu — yani kullanıcının sorduğu noktada hiç bakılmıyordu.
        # Kullanıcı alt sınırı ızgaranın altındaysa o nokta taramaya EKLENİR
        # (ızgaranın kendisi değişmez; yalnız bir nokta eklenir ki hüküm
        # gerçekten sorulan yerde verilsin).
        try:
            _min_pct = self._override_val('min_throttle', 5.0, 100.0,
                                          'Minimum throttle', ' %')
        except Exception:
            _min_pct = None
        if _min_pct:
            _min_frac = float(_min_pct) / 100.0
            if _min_frac < min(fractions) - 1e-9:
                fractions = tuple(sorted(set(fractions) | {_min_frac}))

        base_pc = float(self.P_c)
        dp_frac_design = float(self._injector_dp_fraction())
        eps = float(getattr(self, 'design_reference_expansion_ratio', 0)
                    or VACUUM_REFERENCE_EPS)
        # Motorun TESLİM verim oranı (teslim Isp / ideal CEA Isp), tasarım
        # noktasında bir kez hesaplanır ve kısma boyunca sabit tutulur. Bu
        # oran eta_c* ve lüle veriminden gelir; Pc'ye zayıf bağımlıdır, bu
        # yüzden kısma bandında sabit kabulü ETİKETLENMİŞ bir varsayımdır.
        # Isp'nin kendisi her noktada GERÇEK Pc'de CEA ile yeniden çözülür.
        eta_vac = eta_sl = None
        try:
            from hrma.engines import cea_bridge
            ideal0 = cea_bridge.get_combustion_properties(
                self.fuel_type, self.oxidizer_type, base_pc, float(self.MR),
                expansion_ratio=eps, ambient_bar=float(self.P_a))
            if ideal0.get('source') == 'rocketcea':
                iv0 = ideal0.get('isp_vac_s')
                il0 = ideal0.get('isp_sl_s')
                if iv0 and iv0 > 0:
                    eta_vac = float(self.isp_vac) / float(iv0)
                if il0 and il0 > 0:
                    eta_sl = float(self.isp_sl) / float(il0)
        except Exception:
            cea_bridge = None

        # ÖH D15 / sıvı (P3B4-08): itki artık haritanın KENDİ fiziğinden
        # gelir. Eskiden `thrust_n = self.F * f` (doğrusal kabul) yazılıyor,
        # aynı satırda tablonun KENDİ isp_sea_level sütunu düşüyordu; iki
        # sütun birbiriyle çelişiyordu. Ölçüldü (once.json, 25 kN/60 bar):
        # f=0,40 -> yayımlanan 10.000,00 N ⟷ tablonun kendi Isp'siyle
        # tutarlı 8.604,65 N (+%16,22 İYİMSER); f=0,55 +%8,31; f=0,70
        # +%4,21; f=0,85 +%1,70. Haritanın kendi varsayımı (sabit enjektör
        # alanı, ṁ ∝ Pc) ile F = ṁ(Pc)·g0·Isp_sl(Pc) tek doğru satırdır.
        if not hasattr(self, 'mdot_total'):
            try:
                self.calculate_nozzle_geometry()
            except Exception:
                pass
        mdot_design = getattr(self, 'mdot_total', None)
        # Sabit lülede çıkış basıncı Pc ile DOĞRUSAL ölçeklenir (izentropik,
        # aynı ε ve γ): P_e(f) = P_e(tasarım)·Pc(f)/Pc(tasarım).
        pe_design = None
        try:
            eps_nozzle = float(getattr(self, 'expansion_ratio', 0) or 0)
            if eps_nozzle > 1.0:
                _, pe_design = self._cf_at(eps_nozzle, self.P_a)
        except Exception:
            pe_design = None
        ayrilma_esigi = NOZZLE_SEPARATION_PRESSURE_RATIO * float(self.P_a)
        ayrilma_uyarildi = False

        points, skipped = [], []
        for frac in fractions:
            f = float(frac)
            if not (0 < f <= 1.0):
                # ÖH D24 · P3B4-13: bu dal eskiden SESSİZ ``continue`` idi;
                # istenen bir kısma noktası haritadan düşüyor ama 'skipped'
                # boş kaldığı için okuyucu "hepsi değerlendirildi" sanıyordu.
                skipped.append({
                    'throttle_fraction': f,
                    'reason': (
                        'the throttle fraction is outside the physical range '
                        '(0, 1]; the map does not extrapolate above the '
                        'design point and a zero/negative fraction has no '
                        'chamber pressure, so no row is fabricated for it'),
                })
                continue
            # Sabit enjektör alanı: ṁ ∝ Pc (boğulmuş boğaz) ve ṁ ∝ sqrt(ΔP)
            # olduğundan Pc birinci mertebeden itki oranıyla ölçeklenir.
            pc = base_pc if abs(f - 1.0) < 1e-9 else base_pc * f
            # Isp: GERÇEK indirgenmiş Pc'de CEA + sabit teslim verim oranı.
            isp_vac = isp_sl = None
            if cea_bridge is not None and eta_vac is not None:
                try:
                    idf = cea_bridge.get_combustion_properties(
                        self.fuel_type, self.oxidizer_type, pc, float(self.MR),
                        expansion_ratio=eps, ambient_bar=float(self.P_a))
                    if idf.get('source') == 'rocketcea':
                        if idf.get('isp_vac_s'):
                            isp_vac = eta_vac * float(idf['isp_vac_s'])
                        if eta_sl is not None and idf.get('isp_sl_s'):
                            isp_sl = eta_sl * float(idf['isp_sl_s'])
                except Exception:
                    pass
            # ΔP sabit alanda debinin karesiyle ölçeklenir: ΔP(f) = ΔP_tasarım·f²
            dp_bar = dp_frac_design * base_pc * (f ** 2)
            dp_over_pc = dp_bar / pc if pc > 0 else None
            if dp_over_pc is None:
                chug = 'unknown'
            elif dp_over_pc >= CHUG_DP_PC_RECOMMENDED_LIQUID:
                chug = 'chug_margin_ok'
            elif dp_over_pc >= CHUG_DP_PC_MIN_LIQUID:
                chug = 'chug_margin_marginal'
            else:
                chug = 'chug_risk'
            # --- Ayrılma denetimi (Summerfield): kısılan motorda P_e düşer.
            pe_f = (None if pe_design is None
                    else float(pe_design) * float(pc) / base_pc)
            # Bağıl tolerans: ortam-eşlenik tasarımda (P_e = P_a) f = oran
            # noktası ÖLÇÜTÜN TAM ÜSTÜNE düşer; çıplak `<` orada kayan
            # nokta gürültüsüyle platformdan platforma dönerdi. Sınırın
            # kendisi "altında" sayılmaz (ölçüt katı eşitsizliktir).
            ayrilmis = (pe_f is not None
                        and pe_f < ayrilma_esigi * (1.0 - 1e-9))
            if ayrilmis and not ayrilma_uyarildi:
                # Mevcut anahtar (yeni i18n anahtarı açılmadı).
                self._warn('warn.liquid.flow_separation', 'warning',
                           eps=float(getattr(self, 'expansion_ratio', 0) or 0),
                           pe_bar=round(float(pe_f), 3),
                           ratio=float(NOZZLE_SEPARATION_PRESSURE_RATIO))
                ayrilma_uyarildi = True

            # --- İtki: haritanın KENDİ Isp'si ve KENDİ debi varsayımıyla.
            thrust_n = None
            if ayrilmis:
                thrust_basis = (
                    'not published: at this chamber pressure the nozzle is '
                    f'separated by the engine own Summerfield criterion '
                    f'(P_e = {pe_f:.4f} bar < '
                    f'{NOZZLE_SEPARATION_PRESSURE_RATIO:g} x P_a = '
                    f'{ayrilma_esigi:.4f} bar). HRMA does not solve separated '
                    'nozzle flow, so no sea-level number is invented here.')
                isp_sl = None
            elif isp_sl is None or mdot_design is None:
                thrust_basis = (
                    'not published: the sea-level Isp at this reduced chamber '
                    'pressure could not be solved (no CEA solution), so the '
                    'thrust cannot be formed from the map own physics')
            else:
                mdot_f = float(mdot_design) * float(pc) / base_pc
                thrust_n = float(mdot_f) * float(self.g0) * float(isp_sl)
                thrust_basis = (
                    'F = mdot(Pc) x g0 x Isp_sl(Pc) with mdot proportional to '
                    'Pc (the fixed-injector-area assumption declared below); '
                    'the thrust column is therefore consistent with the Isp '
                    'column of the same row')
            points.append({
                'throttle_fraction': f,
                'thrust_n': thrust_n,
                'thrust_basis': thrust_basis,
                'chamber_pressure_bar': float(pc),
                'exit_pressure_bar': (None if pe_f is None else float(pe_f)),
                'flow_separated': (None if pe_f is None else bool(ayrilmis)),
                'isp_sea_level': float(isp_sl) if isp_sl else None,
                'isp_vacuum': float(isp_vac) if isp_vac else None,
                'injector_dp_bar': float(dp_bar),
                'injector_dp_over_pc': float(dp_over_pc) if dp_over_pc else None,
                'chug_rating': chug,
            })

        # --- ÖH D22 / P6B4-04 · HARİTA ÇEVRİM HÜKMÜNÜ DE TAŞIR ------------
        # ÖLÇÜLDÜ (raw/OH/D22/sivi/a1/once_ham.json): nokta anahtarlarında
        # `verdict` de `loop` da YOKTU — harita yalnız oran kuralının
        # (`chug_rating`) hükmünü yayımlıyordu. Tasarım noktasında ise HRMA
        # iki hükmü de yayımlayıp çelişkiyi adıyla beyan ediyor
        # (`rule_vs_loop`, bkz. `_chug_loop_block`). Yani kullanıcı aynı
        # yanıtta "tasarım noktasında iki hüküm var, kısma boyunca bir
        # hüküm var" görüyordu; kısma haritası tam da chug riskinin
        # BÜYÜDÜĞÜ banttır ve orada susan taraf FİZİĞİ ÇOK olan taraftı.
        # 32 koşunun 29'unda (%90,6) iki hüküm zaten çelişiyordu.
        #
        # Sayı KOPYALANMAZ: her nokta çevrimi KENDİ J'siyle yeniden koşar.
        # Zaman ölçekleri (τ, τ_c) tasarım noktasında dondurulur — bu
        # haritanın ZATEN beyan ettiği "c*'ın zayıf Pc bağımlılığı ihmal
        # edildi" kabulünün aynısıdır ve aşağıda ADIYLA yazılır.
        cevrim_girdi = getattr(self, '_chug_loop_inputs', None)
        cevrim_beyani = None
        if isinstance(cevrim_girdi, dict):
            from hrma.stability.chug import assess_chug as _assess_chug
            _celisen = 0
            _hukumlu = 0
            for p in points:
                j = p.get('injector_dp_over_pc')
                if not (j and np.isfinite(j) and j > 0):
                    p['chug_loop_verdict'] = None
                    p['chug_loop_status'] = 'NOT_EVALUATED'
                    continue
                try:
                    _l = _assess_chug(
                        dp_ratio_j=float(j),
                        tau_s=cevrim_girdi['tau_s'],
                        tau_c_s=cevrim_girdi['tau_c_s'],
                        tau_f_s=cevrim_girdi['tau_f_s'],
                        feed_line=cevrim_girdi['feed_line'])
                except Exception as _exc:
                    p['chug_loop_verdict'] = None
                    p['chug_loop_status'] = f'NOT_EVALUATED: {_exc}'
                    continue
                p['chug_loop_status'] = 'modelled'
                p['chug_loop_verdict'] = _l.get('verdict')
                p['chug_loop_growth_rate_1_s'] = _l.get('growth_rate_1_s')
                p['chug_loop_frequency_hz'] = _l.get('frequency_hz')
                _kural_guvenli = p['chug_rating'] in ('chug_margin_ok',
                                                      'chug_margin_marginal')
                _cevrim_kararli = _l.get('verdict') == 'stable'
                p['rule_vs_loop'] = ('agree' if _kural_guvenli == _cevrim_kararli
                                     else 'disagree')
                _hukumlu += 1
                if p['rule_vs_loop'] == 'disagree':
                    _celisen += 1
            cevrim_beyani = {
                'points_with_loop_verdict': _hukumlu,
                'points_where_rule_and_loop_disagree': _celisen,
                'tau_s': cevrim_girdi['tau_s'],
                'tau_c_s': cevrim_girdi['tau_c_s'],
                'tau_f_s': cevrim_girdi['tau_f_s'],
                '_basis': (
                    'Every point re-runs the SAME feed-coupled chug loop '
                    '(hrma.stability.chug.assess_chug) with that point own '
                    'injector gain J = dP_inj/Pc; no verdict is copied from '
                    'the design point. The two time scales are held at their '
                    'design-point values: the chamber time constant tau_c '
                    '(because c* is already assumed Pc-independent by this '
                    'map, see assumptions) and the sensitive time lag tau '
                    '(the atomisation time, whose throttle scaling is not '
                    'solved here). Holding tau fixed is the CONSERVATIVE '
                    'direction for the deep-throttle end: at reduced Pc the '
                    'injection velocity falls and the real breakup time '
                    'grows, which can only push the loop further toward '
                    '"unstable", never away from it. Where this loop verdict '
                    'and the classical ratio rule disagree, BOTH are '
                    'published and neither overrides the other - the same '
                    'contract the design point uses (rule_vs_loop).'),
            }
        else:
            cevrim_beyani = {
                'status': 'NOT_EVALUATED',
                '_basis': (
                    'The design-point chug loop was not solved on this run '
                    '(missing J, tau, L* or c*), so the throttle map has no '
                    'loop inputs to re-run and no verdict is fabricated.'),
            }

        min_pct = getattr(self, 'min_throttle_pct', None)
        # ÖH D24 · P3B4-13 — 'skipped' NE SÖYLER, NE SÖYLEMEZ.
        # ÖLÇÜLDÜ (raw/OH/D24/sivi/a1/once.json, P3B4-13; taban 88a29d3):
        # ``skipped.append`` deponun HİÇBİR yerinde yoktu, alan her koşuda
        # ``[]`` olarak yayımlanıyordu; aynı koşuda 5 noktanın 5'inde
        # ``thrust_n`` None idi. Yani "atlanan yok" diyen bir alanla, itkisi
        # çözülemeyen beş satır aynı yanıtta duruyordu ve docstring
        # "çözülemeyen nokta ... 'skipped' listesinde gerekçesiyle görünür"
        # diye YANLIŞ bir sözleşme ilan ediyordu. İki durum artık ayrı ayrı
        # ve ADIYLA yayımlanır: haritadan DÜŞEN nokta 'skipped'te gerekçesiyle
        # durur; yayımlanan ama itkisi çözülemeyen satır ise kendi
        # 'thrust_basis' alanında nedenini söyler ve burada SAYILIR.
        _itkisiz = sum(1 for p in points if p.get('thrust_n') is None)
        out = {
            'points': points,
            'skipped': skipped,
            'skipped_basis': (
                "'skipped' lists only the requested throttle fractions that "
                'were dropped before evaluation (outside the physical range '
                '(0, 1]). A row that IS published but whose thrust could not '
                'be solved is NOT in this list: it stays in points with '
                'thrust_n = null and its own thrust_basis. On this run '
                f'{len(skipped)} fraction(s) were dropped and {_itkisiz} of '
                f'{len(points)} published rows carry no thrust'),
            'points_without_thrust': _itkisiz,
            'design_dp_over_pc': dp_frac_design,
            'chug_loop_across_throttle': cevrim_beyani,
            'assumptions': [
                'chamber pressure is scaled to first order with the '
                "thrust ratio (the weak Pc dependence of c* is neglected).",
                'the injector area is held CONSTANT; dP scales with the '
                'square of the mass flow (dP ~ mdot^2). A throttleable '
                '(e.g. pintle) injector can hold a higher real dP.',
                'the transient regime (dynamic behaviour during the throttle '
                'transition) is NOT modelled; every point is a STEADY-state '
                'solution.',
                "thrust is derived from the row's OWN Isp "
                '(F = mdot*g0*Isp_sl, mdot ~ Pc); the linear "throttle '
                'ratio x design thrust" assumption is NOT used.',
                'at the points where the nozzle separates '
                '(P_e < %g*P_a, Summerfield) the sea-level Isp and thrust '
                'are NOT published; separated flow is not solved.'
                % NOZZLE_SEPARATION_PRESSURE_RATIO,
                'the chug LOOP verdict (chug_loop_verdict) of every point is '
                "re-solved with that point's OWN J; tau and tau_c are frozen "
                'at the design point (see chug_loop_across_throttle). When '
                'the ratio rule and the loop disagree BOTH are published '
                '(rule_vs_loop); neither overwrites the other.',
            ],
            'separation_threshold_bar': float(ayrilma_esigi),
            'transient_response': 'not_modelled',
        }
        if min_pct is not None:
            out['min_throttle_pct'] = float(min_pct)
            worst = [p for p in points
                     if p['throttle_fraction'] * 100.0 >= float(min_pct) - 1e-9
                     and p['chug_rating'] == 'chug_risk']
            out['min_throttle_chug_risk'] = bool(worst)
        return out

    def _autogenous_applicable(self):
        """(uygun_mu, gerekçe) — autogenous basınçlandırma bu motorda mümkün mü?

        ÖH D15 / sıvı (P3B1-05): bu yüklem eskiden YALNIZ boyutlandırma
        bloğunun içindeydi; besleme sisteminin yayımladığı
        ``pressurization.type`` ise ondan habersiz, tek satırda
        ``'autogenous' if feed_system_type != 'pressure_fed'`` yazıyordu.
        Sonuç: aynı yanıtta hem "autogenous basınçlandırma" hem "autogenous
        uygulanamaz, helyum kullanılır" duruyordu (ölçüldü: arayüzün
        sunduğu 5 yakıtın 3'ünde — rp1, mmh, udmh). Yüklem artık TEK
        yerdedir ve hem boyutlandırma hem tip beyanı buradan okur.
        """
        if self.feed_system_type != 'turbopump':
            return False, ('autogenous pressurisation belongs to turbopump '
                           'cycles; a pressure-fed system has no pump to tap '
                           'and uses a separate stored pressurant')
        fuel = str(self.fuel_type).strip().lower()
        ox = str(self.oxidizer_type).strip().lower()
        if ox not in ('lox', 'oxygen') or fuel not in ('methane', 'lch4',
                                                       'ch4', 'lh2',
                                                       'hydrogen'):
            return False, (
                'autogenous pressurisation is modelled only for methane/LOX '
                f"and LH2/LOX; '{self.fuel_type}/{self.oxidizer_type}' is not "
                'supported (the other propellants use stored helium)')
        return True, ''

    def _pressurization_type(self):
        """(tip, künye) — tank basınçlandırma gazının TEK tanım yeri.

        ÖH D15 / sıvı (P3B1-05). Karar sırası:
          1) Kullanıcı bir tip seçtiyse (``pressurization_type``) o geçerlidir
             — 'autogenous' seçimi yalnız fiilen uygulanabiliyorsa kabul
             edilir; uygulanamıyorsa sessizce yutulmaz, reddi künyede
             adıyla söylenir ve modellenen tipe düşülür.
          2) Basınç beslemeli sistemde depolanmış inert gaz (azot şişesi).
          3) Turbopompalı sistemde autogenous ancak ``_autogenous_applicable``
             evet diyorsa; aksi hâlde helyum.
        Emniyet vanası boyutlandırması da (``_relief_valve_sizing``) bu
        fonksiyonu okur; eskiden o blok helyumu bağımsız seçiyordu.
        """
        uygun, gerekce = self._autogenous_applicable()
        secim = str(getattr(self, 'pressurization_choice', None)
                    or 'auto').strip().lower()
        if secim and secim != 'auto':
            if secim == 'autogenous' and not uygun:
                # Uyarı bir kez: bu fonksiyon besleme kartı ve her tankın
                # emniyet vanası için ayrı ayrı çağrılır.
                if not getattr(self, '_pressurant_choice_warned', False):
                    self._pressurant_choice_warned = True
                    self._warn('warn.liquid.option_not_recognised', 'warning',
                               field='pressurization_type',
                               field_label_en='Pressurization type',
                               raw='autogenous')
                tip = ('gaseous_nitrogen'
                       if self.feed_system_type == 'pressure_fed' else 'helium')
                return tip, (
                    "user input 'autogenous' rejected: " + gerekce
                    + f" -> '{tip}' is the modelled pressurant")
            if secim == 'nitrogen':
                return 'gaseous_nitrogen', 'user input (pressurization type)'
            return secim, 'user input (pressurization type)'
        if self.feed_system_type == 'pressure_fed':
            return 'gaseous_nitrogen', (
                'pressure-fed system: a stored inert gas bottle pressurises '
                'the tanks (no pump, no autogenous heat exchanger)')
        if uygun:
            return 'autogenous', (
                'turbopump cycle with a propellant pair HRMA models for '
                'autogenous pressurisation (methane/LOX or LH2/LOX): the '
                'propellants are tapped, heated and fed back to their own '
                'tanks; sized in autogenous_pressurization')
        return 'helium', (
            'stored helium: ' + gerekce)

    def _autogenous_pressurization_summary(self):
        """Autogenous basınçlandırma boyutlandırması (uygunsa).

        Yalnız TURBOPOMPALI + metan/LOX veya LH2/LOX konfigürasyonunda
        sayısal boyutlandırılır — bu iticiler ısı değiştiriciden geçirilip
        kendi tanklarına gaz olarak geri beslenebilir (Raptor/Starship yolu).
        Uygun değilse sahte sayı değil, 'not_applicable' gerekçesi döner.

        Pompadan/ısı değiştiriciden çalınan gaz kütlesi sistem bütçesine
        işlenir; itki üretmez.
        """
        uygun, gerekce = self._autogenous_applicable()
        if not uygun:
            return {'status': 'not_applicable', 'reason': gerekce}
        fuel = str(self.fuel_type).strip().lower()
        try:
            from hrma.analysis.pressurant_sizing import autogenous_pressurant
            if not hasattr(self, 'mdot_total'):
                self.calculate_nozzle_geometry()
            burn_time, _ = self._burn_time()
            if burn_time is None:
                # ÖH D36 / LU-1: boşalan hacim = debi x süre; süre yoksa
                # bütçe yok (mevcut 'not_applicable' sözleşmesi, adıyla).
                return {'status': 'not_applicable',
                        'reason': BURN_TIME_NOT_SUPPLIED_REASON}
            mdot_ox = getattr(self, 'mdot_ox',
                              self.mdot_total * self.MR / (1 + self.MR))
            mdot_fuel = getattr(self, 'mdot_fuel',
                                self.mdot_total / (1 + self.MR))
            # Boşalan itici hacimleri (rho tank modeliyle aynı kaynak)
            _, ox_vol, _, _ = self._size_tank(mdot_ox * burn_time, 'oxidizer')
            _, fuel_vol, _, _ = self._size_tank(mdot_fuel * burn_time, 'fuel')
            # Turbopompalı tanklarda basınç NPSH için düşüktür (~3 bar);
            # A11: değer artık tank kartı ve NPSH zinciriyle AYNI tanım
            # noktasından okunur (eskiden 3e5 Pa satır içi literaldi).
            tank_pressure_pa = self._tank_pressure_bar()[0] * PA_PER_BAR
            ox_gas = autogenous_pressurant(ox_vol, tank_pressure_pa, 'oxygen')
            fuel_gas = autogenous_pressurant(fuel_vol, tank_pressure_pa, fuel)
            total_kg = 0.0
            for g in (ox_gas, fuel_gas):
                if g.get('status') == 'ok':
                    total_kg += float(g.get('gas_mass_kg', 0.0))
            prop_mass = (mdot_ox + mdot_fuel) * burn_time
            return {
                'status': 'ok',
                'oxidizer_side': ox_gas,
                'fuel_side': fuel_gas,
                'total_pressurant_gas_kg': total_kg,
                'fraction_of_propellant': (total_kg / prop_mass
                                           if prop_mass > 0 else None),
                'note': ('autogenous pressurisation: the propellants '
                         'are tapped, heated in a heat exchanger and fed '
                         'back to their own tanks as gas, so there is no '
                         'separate helium bottle. The tapped gas mass is '
                         'charged to the propellant budget.'),
            }
        except Exception as exc:
            return {'status': 'error',
                    'reason': f'{type(exc).__name__}: {exc}'}

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
        probe = LiquidRocketEngine(**params)
        # --- ÖH D24 · P3B4-12 · KANAL VAR KAPI YOK -------------------------
        # ÖLÇÜLDÜ (raw/OH/D24/sivi/a1/once.json, P3B4-12; taban 88a29d3):
        # ``_skip_optimization_maps`` bayrağının OKUYUCUSU vardı (1 getattr,
        # _generate_performance_optimization_maps) ama deponun tamamında
        # YAZICISI yoktu (0). Yani "tarama motorlarında pahalı haritalar
        # atlanır" diye ilan edilen kapı hiçbir zaman kapanmıyordu ve
        # ``{'status': 'skipped'}`` dalı ölü bir çıktı biçimiydi: tüketici
        # o biçime göre kod yazsa hiç görmezdi. Bayrak artık TAM DA ilan
        # edildiği yerde, tarama örneğinin üstünde yakılır. Bugün hiçbir
        # tarama motoru calculate_performance() çağırmadığı için ürün
        # çıktısı DEĞİŞMEZ (çapa bit-aynı kalır); değişen, ilan edilen
        # sözleşmenin artık doğru olması ve iç içe taramanın kapısının
        # gerçekten kapalı olmasıdır.
        probe._skip_optimization_maps = True
        return probe

    def _generate_performance_optimization_maps(self):
        """Performans optimizasyon haritaları — GERÇEK çözücü taraması.

        HAFİF MOD (2026-07-23): Bu fonksiyon her noktada motoru yeniden
        koşan pahalı bir taramadır (~3.5 s). Kısma haritası gibi motoru zaten
        _scan_engine ile YENİDEN koşan tüketiciler bu haritalara ihtiyaç
        duymaz; sonsuz iç içe tarama olmasın diye _skip_optimization_maps
        bayrağı taşıyan örneklerde atlanır. (Kısma taraması kendisi zaten
        chug marjını ve Isp'yi doğrudan hesaplar.)
        """
        if getattr(self, '_skip_optimization_maps', False):
            return {'status': 'skipped',
                    'reason': 'scan engine (throttle/inner sweep)'}
        return self._generate_performance_optimization_maps_impl()

    def _generate_performance_optimization_maps_impl(self):
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
        # FAZ 5 / H2-5 DÜZELTMESİ — `mixture_ratio_efficiency` kendi tanımını
        # aşıyordu. Gösterge "seçilen O/F'nin Isp'si / bu taramanın maksimumu"
        # diye tanımlı, yani <= %100 olmalı; ölçülen (Pc=11 bar, LOX/RP-1,
        # O/F=2,3) %100,02585694901296 idi. Sebep: eşit aralıklı ızgara
        # SEÇİLEN O/F'yi içermeyebiliyor, dolayısıyla tasarım noktasının
        # Isp'si ızgara maksimumunu aşabiliyordu (aşım %0,026).
        # Çözüm sayıyı kırpmak DEĞİL, tasarım noktasını taramanın KENDİSİNE
        # koymak: eğri artık gerçekten tasarım noktasından geçiyor ve oran
        # tanım gereği <= %100 oluyor.
        if not bool(np.any(np.isclose(mr_range, float(self.MR),
                                      rtol=0.0, atol=1e-9))):
            mr_range = np.sort(np.append(mr_range, float(self.MR)))
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
        # ÖH D15 / sıvı (P3B4-07): bu taramanın İKİ ailesi vardır ve eskiden
        # ikisi AYNI eksende, künyesiz, tek motormuş gibi yayımlanıyordu.
        #   * `_scan_engine(chamber_pressure=pc)` TASARIM İTKİSİNİ sabit
        #     tutar; boğaz Pc ile küçülür -> throat_diameter_vs_pc_mm bu
        #     ailenin eğrisidir (SABİT İTKİ ailesi).
        #   * thrust_vs_pc ise BU motorun boğazını sabit tutup Pc'yi
        #     yükseltmenin itkisiydi (SABİT DONANIM ailesi).
        # Ölçüldü (once.json, 25 kN/60 bar): x = 120 bar noktasında bir eğri
        # 55.779 N (59,34 mm boğazla), öbürü 40,85 mm boğaz diyordu; aynı
        # noktada iki farklı motor duruyordu (boğaz oranı 0,688 ... 1,665).
        # Artık üst düzey eğriler TEK aileye (sabit itki) aittir ve sabit
        # donanım ailesi AYRI adla, AYRI künyeyle yayımlanır.
        isp_vs_pc, thrust_vs_pc, throat_vs_pc = [], [], []
        thrust_fixed_throat_vs_pc = []
        for pc in pc_range:
            try:
                probe = self._scan_engine(chamber_pressure=float(pc))
                geom = probe.calculate_nozzle_geometry()
                isp_vs_pc.append(float(probe.isp_vac))
                # SABİT İTKİ ailesi: gereksinim itkidir, boğaz yeniden
                # boyutlanır. Yayımlanan itki taramanın her noktasında
                # tasarım itkisidir — eğri düz olabilir ama DOĞRUDUR.
                thrust_vs_pc.append(float(self.F))
                throat_vs_pc.append(float(geom['throat_diameter'] * 1000.0))
                # SABİT DONANIM ailesi (ayrı eğri, ayrı künye):
                # F = CF · Pc · A_t (Sutton & Biblarz 9th ed., Eq. 3-31).
                cf_pc, _ = probe._cf_at(geom['expansion_ratio'], self.P_a)
                thrust_fixed_throat_vs_pc.append(
                    float(cf_pc * pc * PA_PER_BAR * self.A_t))
            except Exception:
                isp_vs_pc.append(None)
                thrust_vs_pc.append(None)
                throat_vs_pc.append(None)
                thrust_fixed_throat_vs_pc.append(None)

        # --- İrtifa taraması (gerçek fonksiyon) ----------------------------
        altitude_range = np.linspace(0.0, PERF_MAP_ALT_MAX_M,
                                     PERF_MAP_ALT_POINTS)
        alt_data = self.calculate_altitude_performance(altitude_range.tolist())
        # H2-2: ayrılmış rejimde satır `None` döner (sayı uydurulmaz); grafik
        # dizisi de boşluk taşır — `float(None)` ile çökmemeli.
        isp_vs_alt = [None if p['specific_impulse'] is None
                      else float(p['specific_impulse']) for p in alt_data]
        thrust_vs_alt = [None if p['thrust'] is None else float(p['thrust'])
                         for p in alt_data]

        # --- O/F verimi: AYNI taramanın kendisinden ------------------------
        # Eskiden burada `getattr(self, 'mr_efficiency', ...)` okunuyordu;
        # canlı CEA yolunda o değer koşulsuz 1.0'a atanıyor (bkz.
        # _calculate_mixture_ratio_effects) ve yaprak HER motorda %100
        # çıkıyordu — "seçtiğiniz O/F optimum" diyen sahte bir hüküm. Artık
        # oran taramanın KENDİ noktalarından gelir: eta_MR = Isp(MR_secilen)
        # / max(Isp(MR)). Tarama çözülemezse sayı uydurulmaz.
        isp_valid = [v for v in isp_vs_mr if isinstance(v, (int, float))]
        if isp_valid and max(isp_valid) > 0:
            mr_efficiency_pct = float(self.isp_vac) / max(isp_valid) * 100.0
            mr_efficiency_basis = (
                'Isp(vac) at the selected O/F divided by the maximum Isp of '
                'this very O/F scan (same solver chain, CEA-anchored); the '
                'selected O/F is itself one of the scan points, so the ratio '
                'cannot exceed 100%')
        else:
            mr_efficiency_pct = None
            mr_efficiency_basis = 'not_modelled (the O/F scan did not solve)'
        self.mr_efficiency_from_scan = (None if mr_efficiency_pct is None
                                        else mr_efficiency_pct / 100.0)
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
                'mr_efficiency': mr_efficiency_pct,
                'mr_efficiency_basis': mr_efficiency_basis,
            },
            'chamber_pressure_optimization': {
                'pc_range': pc_range.tolist(),
                'isp_vs_pc': isp_vs_pc,
                'thrust_vs_pc': thrust_vs_pc,
                'throat_diameter_vs_pc_mm': throat_vs_pc,
                'current_pc': self.P_c,
                # Tek aile, tek motor: her x noktasında AYNI motor.
                'family': ('constant thrust: the design thrust is the '
                           'requirement, so at every scanned chamber pressure '
                           'the engine is re-sized (the throat shrinks as Pc '
                           'rises). Every curve below belongs to THIS family.'),
                'thrust_basis': ('the design thrust is held constant across '
                                 'the scan (that is the family definition), '
                                 'so this curve is flat by construction; the '
                                 'variable that moves is the throat diameter'),
                'throat_diameter_basis': (
                    'throat solved at each chamber pressure for the design '
                    'thrust, with the same solver as the design point'),
                'isp_basis': ('vacuum Isp of the re-sized engine at each '
                              'chamber pressure (same CEA-anchored chain); '
                              'Isp is scale-free, so it is common to both '
                              'families'),
                # İKİNCİ AİLE — donanım sabit, itki değişken. Ayrı ad, ayrı
                # künye: aynı eksende çizilse bile aynı motor DEĞİLDİR.
                'thrust_vs_pc_fixed_throat': thrust_fixed_throat_vs_pc,
                'thrust_vs_pc_fixed_throat_basis': (
                    'DIFFERENT family: this engine hardware is kept as built '
                    f'(throat diameter {float(self.d_t) * 1000.0:.3f} mm, '
                    'fixed) and only the chamber pressure is raised: '
                    'F = CF x Pc x A_t. It answers a different question than '
                    'thrust_vs_pc / throat_diameter_vs_pc_mm and must not be '
                    'read together with them as one engine.'),
                'fixed_throat_diameter_mm': float(self.d_t) * 1000.0,
            },
            'altitude_performance': {
                'altitude_range': altitude_range.tolist(),
                'isp_vs_altitude': isp_vs_alt,
                'thrust_vs_altitude': thrust_vs_alt,
                # v2.6.26: burada argmax(Isp) vardı. Isp irtifayla MONOTON
                # arttığı için argmax HER motorda taramanın son noktasıydı ve
                # yaprak 100 000 m'ye çivilenmişti — "bu lülenin tasarım
                # irtifası" diye okunuyordu, oysa yalnız tarama tavanıydı.
                # Bir lülenin tasarım (optimum) irtifası P_cikis = P_ortam
                # kosulundan cozulur.
                **self._design_altitude_report(),
            }
        }
    
    def _calculate_efficiency_breakdown(self):
        """Calculate detailed efficiency breakdown"""
        
        # --- Teorik (kayıpsız) tavan: BU LÜLENİN kendi tavanı ---------------
        # ÖH D15 / sıvı (P3B4-06). Eskiden burada SABİT bir P_e/P_c = 1/20
        # genişlemesi vardı; motorun kendi genişleme oranıyla hiçbir ilgisi
        # yoktu. Kıyaslanan actual_isp ise VAKUM Isp'sidir — yani sonlu
        # çıkış basınçlı, motorunkinden DAHA KÖTÜ bir lülenin ideali, bir
        # motorun vakum performansına "tavan" diye sunuluyordu. Sonuç fizik
        # dışıydı: ölçüldü (once.json) 25 kN/70 bar'da
        # delivered_vs_theoretical_pct = %119,93 iken aynı blok
        # overall_efficiency = %91,70 diyordu — ikisi birlikte imkânsızdır.
        #
        # Doğru tavan: AYNI lülenin (aynı ε), AYNI referans çerçevesinin
        # (vakum) KAYIPSIZ Isp'si. CF_vac(ε) = CF_momentum(P_e/P_c) + ε·P_e/P_c
        # (Sutton & Biblarz 9th ed., Eq. 3-30) ve Isp_ideal = CF_vac·c*_ideal/g0
        # (Eq. 3-32). c*_ideal, teslim zincirinin η_c* ile ÇARPILMAMIŞ
        # hâlidir; aksi hâlde tavanın içine motorun kendi kaybı girer.
        eta_chain = getattr(self, '_delivered_eff', None) or {}
        eta_c_star = float(eta_chain.get('eta_c_star', 1.0) or 1.0)
        c_star_ideal = getattr(self, 'c_star_ref', None)
        if not c_star_ideal:
            c_star_ideal = float(self.c_star) / (eta_c_star or 1.0)
        eps_own = float(getattr(self, 'expansion_ratio', 0) or 0)
        theoretical_isp = None
        theoretical_isp_basis = None
        if eps_own > 1.0:
            try:
                cf_vac_ideal, pe_ideal_bar = self._cf_at(eps_own, 0.0)
                if np.isfinite(cf_vac_ideal) and cf_vac_ideal > 0:
                    theoretical_isp = float(cf_vac_ideal) * float(
                        c_star_ideal) / self.g0
                    theoretical_isp_basis = (
                        f'loss-free vacuum Isp of THIS nozzle: '
                        f'CF_vac(epsilon={eps_own:.3f}, gamma='
                        f'{float(self.gamma):.4f}) = {float(cf_vac_ideal):.4f} '
                        f'times the ideal c* ({float(c_star_ideal):.1f} m/s, '
                        f'before eta_c*), same reference frame as actual_isp '
                        '(Sutton & Biblarz 9th ed., Eq. 3-30/3-32)')
            except Exception as exc:                        # pragma: no cover
                theoretical_isp = None
                theoretical_isp_basis = (
                    f'not_modelled (ideal CF could not be solved: {exc})')
        if theoretical_isp is None and theoretical_isp_basis is None:
            # Genişleme oranı çözülmemişse tavan UYDURULMAZ (fail-closed).
            theoretical_isp_basis = (
                'not_modelled (the expansion ratio of this engine is not '
                'solved, so a loss-free ceiling for its own nozzle cannot '
                'be formed)')

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
        # P3B2-07: konik bağıntının çan konturunda kullanılması burada da
        # kaldırıldı; λ tek kaynaktan gelir ve künyesi o kaynağın künyesidir.
        eta_divergence, _lam_src = self._divergence_efficiency()
        sources['divergence_loss'] = _lam_src

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
            sources['combustion_incomplete'] = str(
                comb.get('combustion_efficiency_source', 'chamber model'))
            mix_pct = comb.get('mixing_efficiency')
            if mix_pct is None:
                # Karışım ölçütü olmayan eleman tipinde UYDURMA verim
                # uygulanmaz: kayıp sıfır sayılır ve öyle etiketlenir.
                eta_mixing = 1.0
                sources['mixing_loss'] = (
                    'not_modelled: this injector element type has no '
                    'momentum-ratio criterion, so no mixing loss is applied')
            else:
                eta_mixing = mix_pct / 100.0
                sources['mixing_loss'] = (
                    f"injector momentum ratio "
                    f"{comb['momentum_ratio']:.2f} vs its design target "
                    f"{comb['optimal_momentum_ratio']:.2f} "
                    "(single source: injector design model)")
        except Exception:
            eta_combustion, eta_mixing = 0.98, 0.985
            sources['combustion_incomplete'] = 'assumed (chamber model failed)'
            sources['mixing_loss'] = 'assumed (chamber model failed)'

        # 6) Kimyasal kinetik kaybı — TEK KAYNAK: teslim verim zincirinin
        #    KENDİ kinetik çözümü (_kinetic_efficiency -> hrma.analysis.
        #    kinetic_efficiency, Damköhler benzeri parametre + Bray donma
        #    ölçütü). Burada eskiden `0.96 if frozen else 0.99` yazıyordu:
        #    iki değerli bir bayrak sabiti, motorun aynı yanıtta raporladığı
        #    gerçek kinetik verimden bağımsız ve onunla ÇELİŞEN ikinci bir
        #    kinetik kayıptı (ölçüm: eta_kinetic 0.9966 iken bu kalem 0.99).
        eff_chain = getattr(self, '_delivered_eff', None) or {}
        kin_diag = eff_chain.get('kinetic') or {}
        eta_kin_chain = eff_chain.get('eta_kinetic')
        if (isinstance(eta_kin_chain, (int, float))
                and kin_diag.get('model') not in (None, 'not_modelled')):
            eta_kinetic = float(eta_kin_chain)
            sources['kinetic_loss'] = (
                "delivered-performance chain kinetic efficiency "
                f"({kin_diag.get('model')}); loss "
                f"{float(kin_diag.get('kinetic_loss_pct', 0.0)):.2f}% of the "
                "shifting-equilibrium Isp")
        else:
            eta_kinetic = 1.0
            sources['kinetic_loss'] = (
                'not_modelled: the CEA frozen-expansion value is unavailable, '
                'so the finite-rate (kinetic) loss is not resolved and no '
                'loss is applied')

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
            'theoretical_isp_basis': theoretical_isp_basis,
            'actual_isp': self.isp_vac,
            # Verimler ÇARPIMSAL birleşir (eski kod yüzdeleri topluyordu).
            'overall_efficiency': overall,
            'overall_efficiency_basis': (
                'product of the delivery losses (divergence, boundary layer, '
                'wall heat transfer, combustion, mixing, kinetics)'),
            'delivered_vs_theoretical_pct': float(
                self.isp_vac / theoretical_isp * 100.0)
            if theoretical_isp else None,
            'delivered_vs_theoretical_basis': (
                'published vacuum Isp divided by the loss-free vacuum Isp of '
                'the SAME nozzle; by construction this cannot exceed 100%. '
                'It is the efficiency the solver ACTUALLY applied '
                '(delivered-performance chain), which is a different estimate '
                'of the same losses than the itemised overall_efficiency '
                'above - the two are not required to agree and the difference '
                'is the spread between the two loss models.'),
            'applied_delivery_efficiency_pct': (
                float(eta_chain['eta_isp']) * 100.0
                if eta_chain.get('eta_isp') is not None else None),
            'loss_breakdown': losses,
            'efficiency_breakdown': {k: v * 100.0
                                     for k, v in efficiencies.items()},
            # ÖH D21 · P15B1-07: AD↔ANLAM. Aynı sayılar, adı ne olduklarını
            # söyleyen anahtarlarla (tek tanım: EFFICIENCY_MECHANISM_NAMES).
            'efficiency_by_mechanism': {
                EFFICIENCY_MECHANISM_NAMES[k]: v * 100.0
                for k, v in efficiencies.items()},
            'loss_by_mechanism': {
                EFFICIENCY_MECHANISM_NAMES[k].replace('_efficiency', '_loss'):
                    v for k, v in losses.items()},
            'efficiency_breakdown_aliases': dict(EFFICIENCY_MECHANISM_NAMES),
            'efficiency_breakdown_aliases_basis': (
                EFFICIENCY_MECHANISM_NAMES_SOURCE),
            'efficiency_by_mechanism_unit': (
                'percent EFFICIENCY (100 x efficiency)'),
            'loss_by_mechanism_unit': (
                'percent LOSS (100 x (1 - efficiency))'),
            # P3B2-07 (ikinci yarı): AYNI anahtar adı iki blokta iki farklı
            # büyüklük taşıyor — 'efficiency_breakdown.*_loss' VERİMİ (%),
            # 'loss_breakdown.*_loss' KAYBI (%) tutuyor. Anahtarları yeniden
            # adlandırmak panel tüketicilerini (arayüz kulvarı) kırardı, bu
            # yüzden bu dalgada sözleşme sayının yanına yazılır; tekilleştirme
            # P15'e (ad/birim) borç kalır.
            'loss_breakdown_unit': 'percent loss (100 x (1 - efficiency))',
            'efficiency_breakdown_unit': (
                'percent EFFICIENCY (100 x efficiency) - the keys keep their '
                'historic "_loss" suffix for panel compatibility, so '
                'efficiency_breakdown.X + loss_breakdown.X = 100 for every X'),
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
    def _derated_yield(material, temperature_k, with_basis=False):
        """Sıcaklığa göre indirgenmiş akma dayanımı [Pa].

        materials_db kayıtlarındaki ``derating_curve`` (anahtar: °C, değer:
        akma oranı) doğrusal interpolasyonla değerlendirilir. Eğri yoksa
        oda sıcaklığı değeri kullanılır.

        ÖH Z4 (P15B1-01 kardeşi): ``np.interp`` eğrinin DIŞINDA sessizce uç
        değere sabitler. Eğrinin son noktası inconel_718'de 900 °C,
        alüminyum 6061'de 350 °C'dir; bunun üstünde sabitleme dayanımı
        OLDUĞUNDAN YÜKSEK gösterir (gerçek metal kaybetmeye devam eder ve
        erimede sıfırlanır). Sayı değiştirilmez, zarf ihlali ADIYLA
        yayımlanır — kardeş modülün deseni
        (``structural_analysis._derate_strength``).

        Args:
            with_basis: True ise (sigma, faktör, beyan) üçlüsü döner.
        """
        sigma_y = float(material['yield_strength'])
        curve = material.get('derating_curve') or {}
        t_c = float(temperature_k) - 273.15
        if not curve:
            beyan = {
                'curve_min_temp_C': None, 'curve_max_temp_C': None,
                'above_curve_envelope': False, 'below_curve_envelope': False,
                'basis': ('no derating curve for this material: room '
                          'temperature yield strength used as-is'),
            }
            return (sigma_y, 1.0, beyan) if with_basis else (sigma_y, 1.0)
        items = sorted((float(k), float(v)) for k, v in curve.items())
        temps = [t for t, _ in items]
        vals = [v for _, v in items]
        factor = float(np.interp(t_c, temps, vals))
        above = t_c > temps[-1]
        below = t_c < temps[0]
        beyan = {
            'curve_min_temp_C': temps[0],
            'curve_max_temp_C': temps[-1],
            'above_curve_envelope': bool(above),
            'below_curve_envelope': bool(below),
            'basis': (
                'yield strength derated on the material derating_curve '
                '(MMPDS / MIL-HDBK-5 pattern) at the wall temperature'
                if not (above or below) else
                f'EXTRAPOLATED AND NOT CONSERVATIVE: wall temperature '
                f'{t_c:.1f} C is above the last point of the derating curve '
                f'({temps[-1]} C), so the retention factor is HELD at '
                f'{factor}; a real metal keeps losing strength above that '
                'point, so this strength is an upper bound'
                if above else
                f'wall temperature {t_c:.1f} C is below the first point of '
                f'the derating curve ({temps[0]} C): room-temperature '
                'strength is used'),
        }
        return ((sigma_y * factor, factor, beyan) if with_basis
                else (sigma_y * factor, factor))

    @staticmethod
    def _next_standard_plate_m(t_m):
        """(kalınlık [m], standart_mı) — ``t_m``'e eşit ya da üstündeki ilk
        standart levha; tablonun üstündeyse gereksinimin kendisi.

        Boyutlandırma ve imalat tabanı yüklemi (denetçi Ş5, 4. tur) AYNI
        karşılaştırmayı kullanır — iki yerde ayrı döngü yazılmaz.
        """
        for std in STANDARD_WALL_THICKNESS_MM:
            if std / 1000.0 >= t_m:
                return std / 1000.0, True
        return float(t_m), False

    @classmethod
    def _throat_meridional_coefficients(cls, gamma, expansion_ratio,
                                        contraction_ratio):
        """Boğaz kesitinin eksenel zar kuvveti, ``P_c·A_t`` biriminde.

        Denetçi Ş2 (4. tur, Berke §27-18). Türetim ve künye
        ``THROAT_MERIDIONAL_BASIS``te. Birimsiz itki fonksiyonu
        Î(M) = p̂(M)·Â(M)·(1 + γM²), p̂ = p/P_c, Â = A/A_t; izantropik akışta
        dÎ = p̂·dÂ olduğundan kesitin bir yanındaki cidar izdüşümü Î
        farkıdır (sembolik doğrulama a1/sart4/sembolik.py).

        Dönüş: ``None`` (girdi fiziksel değilse — sayı uydurulmaz) ya da
        n_downstream = Î(M_e) − Î(1) (ıraksak cidar; boğazda bası),
        n_upstream = Â_c − (Î(M_c) − Î(1)) (enjektör ucu yükü − yakınsak
        izdüşüm; boğazda çekme), p_throat_ratio = (2/(γ+1))^(γ/(γ−1)) ve
        FEA köprüsünün sabit-P_c yükü için aynı büyüklükler (ε − 1 ve 1).
        """
        try:
            g = float(gamma)
            eps = float(expansion_ratio)
            cr = float(contraction_ratio)
        except (TypeError, ValueError):
            return None
        if not all(np.isfinite(v) for v in (g, eps, cr)):
            return None
        if g <= 1.0 or eps < 1.0 or cr < 1.0:
            return None

        def p_hat(m):
            return (1.0 + 0.5 * (g - 1.0) * m * m) ** (-g / (g - 1.0))

        def impulse(m, a_hat):
            return p_hat(m) * a_hat * (1.0 + g * m * m)

        m_e = (cls._mach_from_area_ratio_supersonic(eps, g)
               if eps > 1.0 else 1.0)
        m_c = (cls._mach_from_area_ratio_subsonic(cr, g)
               if cr > 1.0 else 1.0)
        i_t = impulse(1.0, 1.0)
        return {
            'p_throat_ratio': p_hat(1.0),
            'mach_exit': m_e,
            'mach_chamber': m_c,
            'n_downstream': impulse(m_e, eps) - i_t,
            'n_upstream': cr - (impulse(m_c, cr) - i_t),
            'n_downstream_constant_pc': eps - 1.0,
            'n_upstream_constant_pc': 1.0,
        }

    @staticmethod
    def _membrane_equivalent_coefficient(k_hoop, k_meridional):
        """√(k_θ² − k_θ·k_m + k_m²) — iki eksenli zar von Mises katsayısı
        (NASA SP-8087 s. 72, bozulma enerjisi; k_m işaretli: bası < 0)."""
        return float(np.sqrt(k_hoop * k_hoop - k_hoop * k_meridional
                             + k_meridional * k_meridional))

    def _throat_meridional_check(self, p_int, allowable):
        """Boğaz eksenel yük denetimi — gereken kalınlık ve katsayılar.

        Dönüş sözlüğü ``status`` taşır: 'evaluated' ya da 'not_evaluated'
        (boğaz çapı, γ ya da ε bu çağrıda çözülmemişse — sayı uydurulmaz,
        gereksinim zarfına girmez ve neden yazılır).
        """
        d_t = getattr(self, 'd_t', None)
        gamma = getattr(self, 'gamma', None)
        eps = getattr(self, 'expansion_ratio', None)
        eksik = [ad for ad, v in (('throat diameter', d_t), ('gamma', gamma),
                                  ('expansion ratio', eps))
                 if v is None or not np.isfinite(float(v)) or float(v) <= 0]
        if eksik:
            return {'status': 'not_evaluated',
                    'required_thickness_m': None,
                    'basis': ('throat meridional check NOT evaluated: '
                              + ', '.join(eksik) + ' not solved on this '
                              'call; the wall requirement is the chamber hoop '
                              'and the manufacturing floor only')}
        r_t = float(d_t) / 2.0
        d_c = self._chamber_diameter()
        cr = (float(d_c) / float(d_t)) ** 2
        k = self._throat_meridional_coefficients(gamma, eps, cr)
        if k is None:
            return {'status': 'not_evaluated',
                    'required_thickness_m': None,
                    'basis': ('throat meridional check NOT evaluated: '
                              f'gamma={gamma!r}, expansion ratio={eps!r}, '
                              f'contraction ratio={cr!r} outside the '
                              'isentropic relations')}
        k_hoop = k['p_throat_ratio']
        # σ_m = N/(2π r_t t) = n·P_c·π r_t²/(2π r_t t) = (n/2)·P_c·r_t/t
        k_up = self._membrane_equivalent_coefficient(
            k_hoop, 0.5 * k['n_upstream'])
        k_down = self._membrane_equivalent_coefficient(
            k_hoop, -0.5 * k['n_downstream'])
        k_eq = max(k_up, k_down)
        k_pc = max(
            self._membrane_equivalent_coefficient(
                1.0, 0.5 * k['n_upstream_constant_pc']),
            self._membrane_equivalent_coefficient(
                1.0, -0.5 * k['n_downstream_constant_pc']))
        return {
            'status': 'evaluated',
            'throat_radius_m': r_t,
            'contraction_ratio': cr,
            'expansion_ratio': float(eps),
            'gamma': float(gamma),
            'coefficients': k,
            'equivalent_coefficient_upstream': k_up,
            'equivalent_coefficient_downstream': k_down,
            'equivalent_coefficient': k_eq,
            'governing_free_body': ('upstream' if k_up >= k_down
                                    else 'downstream'),
            'equivalent_coefficient_constant_pc': k_pc,
            'required_thickness_m': k_eq * float(p_int) * r_t / allowable,
        }

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
        # B4 (v2.6.27): iki karar da BEYANLI çıkar. Emniyet katsayısı ve
        # malzeme tasarımın en belirleyici iki girdisidir (kalınlık, marj,
        # kütle); hangisinin kullanıcıdan hangisinin varsayılandan geldiği
        # sayının yanında durmazsa okuyan ikisini ayıramaz. Kaynak metni
        # _apply_overrides'ın yazdığı TEK künyeden okunur.
        sf_source = self._safety_factor_source()
        mat_source = self._chamber_material_source()
        t_hot, _ = self._wall_temperatures()
        sigma_y, derate, derate_beyani = self._derated_yield(
            material, t_hot, with_basis=True)
        allowable = sigma_y / sf

        d_c = self._chamber_diameter()
        p_int = self.P_c * PA_PER_BAR  # Pa
        # ÖH A2 sivi-sogutma · denetçi Ş2 (3. tur): basıncın TEK BAŞINA
        # istediği kalınlık ayrıca tutulur — imalat tabanı bağlayıcıysa
        # künye bunu söyler (sayı yayımlanmaz, yalnız hangi kuralın
        # bağladığı; ölçüm örnek projede 0,999 mm ⟷ taban 2,0 mm).
        t_pressure = (p_int * d_c / 2.0) / allowable
        # Denetçi Ş2 (4. tur, Berke §27-18): gereksinim artık hazne çemberi,
        # BOĞAZ eksenel zar yükü (eşdeğer gerilme) ve imalat tabanının
        # ZARFIDIR. Hedef emniyet katsayısı aynı sabitten (``allowable``).
        throat = self._throat_meridional_check(p_int, allowable)
        t_throat = throat.get('required_thickness_m')
        t_struct = max(t_pressure, t_throat if t_throat is not None else 0.0)
        t_required = max(t_struct, WALL_THICKNESS_MANUFACTURING_MIN_M)
        if t_required > t_struct:
            requirement_governing = 'manufacturing_floor'
        elif t_throat is not None and t_throat > t_pressure:
            requirement_governing = 'throat_meridional'
        else:
            requirement_governing = 'chamber_hoop'

        thickness_source = 'next standard plate thickness above the requirement'
        t_used = None
        if getattr(self, 'wall_thickness_input_m', None) is not None:
            t_used = self.wall_thickness_input_m
            thickness_source = 'user input (chamber wall thickness)'
            if t_used < t_required:
                self._warn('warn.liquid.wall_thickness_below_required', 'critical',
                           t_used_mm=round(float(t_used) * 1000, 2),
                           t_required_mm=round(float(t_required) * 1000, 2),
                           material=material.get('name', mat_key),
                           safety_factor=round(float(sf), 2))
        else:
            t_used, standart = self._next_standard_plate_m(t_required)
            if not standart:
                thickness_source = 'computed requirement (above standard sizes)'
        # Denetçi Ş5 (4. tur): imalat tabanı cümlesinin yüklemi "taban
        # SEÇİLEN levhayı değiştirdi mi": basınç gerilmelerinin tek başına
        # seçtireceği levha, kullanılan levhadan İNCE ise. Eski yüklem
        # (t_basınç < 2 mm) 1,5-2,0 mm bandında yanlış VAR diyordu (inconel
        # 718, 100 kN / 70 bar: t_basınç 1,763 mm → standart 2,0 mm = çizilen).
        manufacturing_floor_governs = bool(
            getattr(self, 'wall_thickness_input_m', None) is None
            and self._next_standard_plate_m(t_struct)[0] < t_used)

        hoop = (p_int * d_c / 2.0) / t_used
        margin = (allowable - hoop) / allowable * 100.0
        if throat.get('status') == 'evaluated':
            k_eq = throat['equivalent_coefficient']
            sig_eq = k_eq * p_int * throat['throat_radius_m'] / t_used
            throat['equivalent_stress_pa'] = sig_eq
            throat['safety_factor'] = (sigma_y / sig_eq if sig_eq > 0
                                       else float('inf'))
            throat['basis'] = THROAT_MERIDIONAL_BASIS
        # --- OH-Z2-02 (ÖH Z4): ÇİZİLEN CİDARDA HESAPLANMIŞ EMNİYET KATSAYISI
        # Blok bugüne dek yalnız ``safety_factor``ı yayımlıyordu ve o sayı
        # KULLANICININ HEDEFİDİR (``self.safety_factor``), bir ölçüm değil.
        # Ölçüldü (varsayılan sıvı koşumu, inconel_718, Pc = 20 bar):
        # yayımlanan 2,5 ⟷ çizilen 2,0 mm cidarda hesaplanan
        # 958,155 / 86,234 = 11,11. Fark küçük bir sapma değil: gerekli
        # kalınlık (0,45 mm) imalat tabanına (2,0 mm) yükseltildiği için
        # gerçek marj hedefin çok üstünde. Sayı hedefin yanında ADIYLA
        # durur; hangi soruyu cevapladığı ``safety_factor_basis``te yazar.
        # Ad seçimi rastgele değil: ihraç katmanının cidar-SF şeması
        # (export/cad_visualization.CHAMBER_WALL_SF_SCHEMAS) hazne bloğu
        # için ``hoop_safety_factor``ı ölçüm adayı olarak tanır.
        # ÖH D16 / OH-Z4-01 düzeltmesi: bu cümle "ZATEN tanıyor" diyordu ve
        # YANLIŞTI — şemanın ``chamber_structure`` girişi o tarihte BOŞ
        # ``measured_keys`` taşıyordu, yani ad eşleşmesi vardı ama şema
        # anahtarı hiç okumuyordu. Şema aynı dalgada dolduruldu; cümle artık
        # ürünün gerçek hâlini anlatıyor.
        hoop_sf = (sigma_y / hoop) if hoop > 0 else float('inf')
        design_mode = ('verify'
                       if getattr(self, 'wall_thickness_input_m', None)
                       is not None else 'size')
        return {
            'material': material,
            'design_mode': design_mode,
            'hoop_safety_factor': hoop_sf,
            'safety_factor_is_tautological': bool(design_mode == 'size'),
            # ÖH D16 / OH-Z4-01: ilk cümle KİPTEN BAĞIMSIZ olarak "the wall
            # was sized so that the pressure hoop stress meets it" diyordu.
            # ``design_mode == 'verify'`` (kalınlığı KULLANICI verdi) hâlinde
            # bu YANLIŞTIR — o koşuda cidar hedefe boyutlandırılmaz,
            # kullanıcının kalınlığı denetlenir — ve aynı dizenin kuyruğu
            # "this one is a verification" dediği için cümle kendi kendisiyle
            # çelişiyordu. İlk cümle artık kipe göre kuruluyor.
            'safety_factor_basis': (
                ('safety_factor is the DESIGN TARGET read back (see '
                 'safety_factor_source), not a measurement: the wall was '
                 'sized so that the pressure hoop stress meets it. '
                 'The requirement is the envelope of the chamber hoop '
                 'stress, the throat meridional membrane stress (see '
                 'throat_meridional_check) and the manufacturing floor; '
                 f'largest requirement: {requirement_governing}. '
                 + ('On this run the manufacturing minimum, not the '
                    'pressure, set the thickness: the pressure stresses '
                    'alone would be met by a thinner standard plate than the '
                    'one drawn, and WALL_THICKNESS_MANUFACTURING_MIN_M = '
                    f'{WALL_THICKNESS_MANUFACTURING_MIN_M * 1e3:g} mm (an '
                    'ASSUMED floor; source NOT verified) raised it to the '
                    'next standard plate at or above that floor, so the hoop '
                    'stress sits below the target. '
                    if manufacturing_floor_governs else '')
                 if design_mode == 'size' else
                 'safety_factor is the DESIGN TARGET read back (see '
                 'safety_factor_source), not a measurement: it is the target '
                 'this run was CHECKED AGAINST, not a target the wall was '
                 'sized to - the thickness came from you. ')
                + 'hoop_safety_factor is the factor computed ON THE DRAWN '
                'WALL: derated yield at the wall temperature divided by the '
                'hoop stress of the thickness actually used'
                + (' (thickness supplied by the user, so this one is a '
                   'verification).' if design_mode == 'verify' else
                   ' (thickness chosen by HRMA, so it is not a verification '
                   'of a wall you built).')),
            'material_key': mat_key,
            'material_selection_source': mat_source,
            'safety_factor': sf,
            'safety_factor_source': sf_source,
            'yield_strength_pa': float(material['yield_strength']),
            'derated_yield_pa': sigma_y,
            'derating_factor': derate,
            'derating_basis': derate_beyani,
            'allowable_pa': allowable,
            'chamber_diameter_m': d_c,
            'required_thickness_m': t_required,
            'required_thickness_hoop_m': t_pressure,
            'required_thickness_throat_m': t_throat,
            'requirement_governing': requirement_governing,
            'manufacturing_floor_governs': manufacturing_floor_governs,
            'throat_check': throat,
            'thickness_m': t_used,
            'thickness_source': thickness_source,
            'hoop_stress_pa': hoop,
            'stress_margin_pct': margin,
            'wall_temperature_k': t_hot,
        }

    def _throat_check_publication(self, throat):
        """``chamber_structure.throat_meridional_check`` — yayım birimleri.

        Kuvvetler kN, gerilme MPa, basınç bar, uzunluk mm. Karşılaştırma
        bandı: sabit-P_c yükünün (lüle boyunca P_c; v3.0 öncesi FEA yükü)
        aynı serbest cisimlerde verdiği kuvvet ve eşdeğer gerilme katsayısı
        izantropik değerin YANINDA, üst sınır olarak yayımlanır. FEA'nın
        kendi yük modeli fea.load_model'dedir (dalga37/v3-fea-yuk; karar
        §28-18 (B) — iki dal birlikte birleşir).
        """
        if not isinstance(throat, dict) or throat.get('status') != 'evaluated':
            return {'status': 'not_evaluated',
                    'basis': (throat or {}).get('basis')}
        k = throat['coefficients']
        pc = float(self.P_c) * PA_PER_BAR
        a_t = np.pi * throat['throat_radius_m'] ** 2
        f = pc * a_t / 1e3          # kN / (P_c·A_t)
        return {
            'status': 'evaluated',
            'throat_radius_mm': throat['throat_radius_m'] * 1e3,
            'contraction_ratio': throat['contraction_ratio'],
            'expansion_ratio': throat['expansion_ratio'],
            'gamma': throat['gamma'],
            'throat_static_pressure_bar': k['p_throat_ratio'] * float(self.P_c),
            'meridional_force_upstream_kn': k['n_upstream'] * f,
            'meridional_force_downstream_kn': k['n_downstream'] * f,
            'governing_free_body': throat['governing_free_body'],
            'equivalent_stress': throat['equivalent_stress_pa'] / 1e6,  # MPa
            'safety_factor': throat['safety_factor'],
            'required_wall_thickness': (
                throat['required_thickness_m'] * 1e3),  # mm
            'constant_pc_meridional_force_upstream_kn':
                k['n_upstream_constant_pc'] * f,
            'constant_pc_meridional_force_downstream_kn':
                k['n_downstream_constant_pc'] * f,
            'constant_pc_to_isentropic_equivalent_ratio': (
                throat['equivalent_coefficient_constant_pc']
                / throat['equivalent_coefficient']),
            # Karar §28-18 (B): FEA yük modeli (dalga37/v3-fea-yuk,
            # OH-DK-04) bu dalla BİRLİKTE birleşir; künye FEA'nın bugünkü
            # yükünü İDDİA ETMEZ (o, fea.load_model'de yazar) — bant yalnız
            # bir üst sınır karşılaştırmasıdır.
            'constant_pc_basis': (
                'upper-bound comparison band, not a design load: the same '
                'free bodies loaded with the chamber pressure over the WHOLE '
                'nozzle wall (no static-pressure drop) give the constant_pc_* '
                'forces and an equivalent stress '
                'constant_pc_to_isentropic_equivalent_ratio times the '
                'isentropic one; the structural FEA (/api/fea/structural) '
                'states its own wall-pressure model in fea.load_model'),
            'basis': throat['basis'],
        }

    def _chamber_wall_thickness_m(self):
        """Hazne cidar kalınlığı [m] — yapısal tasarımla tek kaynak."""
        return self._structural_design()['thickness_m']

    #: Kapak/enjektör flanşı cıvata birleşiminin varsayılan kabulleri.
    #: Bunlar HESAP DEĞİL, kullanıcı girdisi verilmediğinde kullanılan
    #: sözleşme değerleridir ve çıktıda adıyla beyan edilirler.
    #:
    #: ÖH D24 · P15B2-09 (Fable-D18 ŞARTI) — SÖZLEŞME ARTIK BURADA YAZILI
    #: DEĞİL, İTHAL. Aynı alanlar üç motor dosyasında üç kez yazılıydı;
    #: D18'de hibrit kopyası ``hrma.analysis.bolted_joint``tan türetildi ama
    #: sıvı ve katı kopyalar LİTERAL SÖZLÜK olarak kaldı. ÖLÇÜLDÜ
    #: (docs/scofield/raw/OH/D24/sivi/a1/once.json, P15B2-09; taban
    #: 88a29d3): literal kopya 2 (sıvı + katı), türetilmiş 1 (hibrit).
    #: Eşitliği sınayan D18 bekçisi vardı ama o bekçi yalnız DEĞERLERİN
    #: bugün eşit olduğunu görüyordu; üç ayrı literalin yarın sessizce
    #: ayrışması hâlâ serbestti. Tek tanım noktası birleşimi ÇÖZEN
    #: modüldedir (değerleri kullanan yerle aynı yer); motorlar birbirini
    #: import etmez (mevcut doktrin), ortak çözümleyiciyi ise zaten import
    #: ediyorlar. Üye malzemesi AYRI sabitten gelir, çünkü katı motor onu
    #: bilerek kullanmaz (D15 / P2B2-12: üye malzemesi kasadan türetilir).
    LIQUID_CLOSURE_JOINT_DEFAULTS = dict(
        _BOLTED_JOINT_CLOSURE_DEFAULTS,
        member_material=_BOLTED_JOINT_MEMBER_MATERIAL,
    )

    def _closure_joint_analysis(self):
        """Kapak/enjektör flanşı cıvata birleşimi — hrma.analysis.bolted_joint.

        Yol haritası A4 (v2.6.27). Katı motordaki bağlanma deseninin birebir
        sıvı karşılığı (solid_rocket_engine._closure_joint_analysis): çözüm
        ``analyze_bolted_joint`` (Shigley Böl. 8 / ISO 898-1 /
        NASA-STD-5020A ön-yük saçılımı) ve /api/bolted-joint ucunda ZATEN
        vardı; sıvı motor onu hiç çağırmıyordu.

        Ayırıcı yük = oda basıncı x sızdırmazlık alanı; sızdırmazlık çapı
        hazne İÇ çapıdır (basıncın kapağa/enjektör plakasına ittiği alan).
        Cıvata sayısı kullanıcı girdisidir (closure_bolt_count); verilmezse
        birleşim BOYUTLANDIRILMAZ — sayı uydurulmaz.
        """
        cfg = self.LIQUID_CLOSURE_JOINT_DEFAULTS
        lo, hi = cfg['bolt_count_range']
        count = self._override_val('closure_bolt_count', lo, hi,
                                   'Closure bolt count')
        if count is None or int(count) < 1:
            return {
                'status': 'not_sized',
                'basis': ('No closure bolt count was supplied, so the joint '
                          'is not sized. Enter the number of closure bolts '
                          'to get separation and proof safety factors.'),
            }
        size = str(self.overrides.get('closure_bolt_size')
                   or cfg['size']).strip().upper()
        prop_class = str(self.overrides.get('closure_bolt_class')
                         or cfg['property_class']).strip()
        seal_diameter_mm = self._chamber_diameter() * 1000.0
        try:
            from hrma.analysis.bolted_joint import analyze_bolted_joint
            res = analyze_bolted_joint(
                pressure_bar=float(self.P_c),
                seal_diameter_mm=float(seal_diameter_mm),
                bolt_count=int(count),
                size=size,
                property_class=prop_class,
                member_material=cfg['member_material'])
        except Exception as exc:
            return {
                'status': 'not_sized',
                'basis': f'Bolted-joint analysis rejected the inputs: {exc}',
            }
        sf = res.get('safety_factors', {})
        sep = res.get('separation', {})
        tq = res.get('torque', {})
        return {
            'status': 'sized',
            'bolt_count': int(count),
            'bolt_size': size,
            'property_class': prop_class,
            # Sıkma torku ön yükten ve cıvata çapından çıkar (T = K·F_i·d,
            # Shigley Denk. 8-27); değer analizörün kendi torque() çıktısıdır
            # — katı motorla aynı şema.
            'tightening_torque_nm': tq.get('recommended_torque_Nm'),
            'nut_factor_K': tq.get('K_nut_factor'),
            'thread_condition': tq.get('condition'),
            'preload_scatter_percent': tq.get('preload_uncertainty_pct'),
            'tightening_torque_basis': (
                'T = K x F_i x d (Shigley 10th ed. Eq. 8-27) with '
                'F_i = 0.75 x proof load (reusable joint) from ISO 898-1 '
                'proof strength; torque control scatters the achieved preload '
                'by the percentage above'),
            'seal_diameter_mm': float(seal_diameter_mm),
            'pressure_bar': float(self.P_c),
            'proof_safety_factor': sf.get('proof_SF_min'),
            'separation_factor': sf.get('separation_factor_n0_min'),
            'overload_factor': sf.get('overload_factor_nL_min'),
            'separated': sep.get('separated'),
            'governing_basis': sf.get('governing_basis'),
            'member_material': cfg['member_material'],
            'assumptions': res.get('assumptions'),
            'warnings': res.get('warnings'),
            'source': res.get('source'),
            'basis': ('Separating load = chamber pressure x sealed area '
                      '(chamber inner diameter); safety factors from the '
                      'bolted-joint analyser used by /api/bolted-joint - '
                      'the same wiring pattern as the solid motor closure '
                      'joint.'),
        }

    def _calculate_structural_loads(self):
        """Structural analysis for chamber and nozzle design"""
        s = self._structural_design()
        material = s['material']
        chamber_internal_pressure = self.P_c * PA_PER_BAR  # Pa
        # --- V3 yapi-sf 3. tur B (karar §28-37 Ş2-3 (a)): (C) MODEL
        # GEÇERLİLİK SINIRI. Ölçüt hibritteki TEK kaynaktan gelir; burada
        # yalnız çağrılır. Cidar, yayımlanan ``wall_temperature``ta
        # değerlendirildiği için ölçüt o sıcaklığı okur. Sınır aşıldıysa
        # sayılar tanı amaçlı kalır, onay/sayısal tasarım hükmü verilmez.
        from hrma.analysis.structural_analysis import (
            LIQUID_MODEL_VALIDITY_BASIS,
            LIQUID_MODEL_VALIDITY_SAFETY_FACTOR_BASIS,
            model_validity_publication, structural_model_validity_at)
        gecerlilik = model_validity_publication(
            structural_model_validity_at(
                material, {'chamber_hot_wall': s['wall_temperature_k']}),
            LIQUID_MODEL_VALIDITY_BASIS)
        gecerlilik_disi = gecerlilik.get('model_validity_limit_exceeded') is True

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
                # OH-Z2-02: hedef ⟷ ölçüm ayrımı (tek üretim noktası
                # _structural_design; burada yalnız taşınır).
                'design_mode': s['design_mode'],
                'hoop_safety_factor': s['hoop_safety_factor'],
                'safety_factor_is_tautological':
                    s['safety_factor_is_tautological'],
                'safety_factor_basis': (
                    LIQUID_MODEL_VALIDITY_SAFETY_FACTOR_BASIS
                    if gecerlilik_disi else s['safety_factor_basis']),
                # V3 yapi-sf 3. tur B: geçerlilik bayrağı + künye (+ sınır
                # aşıldıysa verdict_withheld ve gerekçe kodu).
                **gecerlilik,
                # B4 (v2.6.27): katsayı ve malzeme künyeleri sayının YANINDA.
                # 'material_source' (aşağıda) malzeme ÖZELLİKLERİNİN literatür
                # künyesidir; 'material_selection_source' malzemeyi KİMİN
                # seçtiğini söyler. İki ayrı soru, iki ayrı alan.
                'safety_factor_source': s['safety_factor_source'],
                'material': material.get('name', s['material_key']),
                'material_key': s['material_key'],
                'material_selection_source': s['material_selection_source'],
                'yield_strength': s['yield_strength_pa'] / 1e6,  # MPa (20 C)
                'yield_strength_at_wall_temp': s['derated_yield_pa'] / 1e6,  # MPa
                'derating_factor': s['derating_factor'],
                # Z4: derating eğrisinin zarfı dışına çıkıldıysa SESSİZ
                # kalmaz (yön: dayanımı yüksek gösterir).
                'derating_basis': s['derating_basis'],
                'wall_temperature': s['wall_temperature_k'],  # K
                'material_source': material.get('source', 'materials_db'),
                # Denetçi Ş2 (4. tur, Berke §27-18): gereksinim zarfının
                # bileşenleri ve boğaz eksenel yük denetimi yanıtta.
                'required_wall_thickness_hoop': (
                    s['required_thickness_hoop_m'] * 1000),  # mm
                'required_wall_thickness_throat': (
                    None if s['required_thickness_throat_m'] is None
                    else s['required_thickness_throat_m'] * 1000),  # mm
                'required_wall_thickness_governing':
                    s['requirement_governing'],
                # Denetçi Ş5 (4. tur): taban SEÇİLEN levhayı değiştirdi mi
                # (safety_factor_basis'teki imalat tabanı cümlesinin yüklemi).
                'manufacturing_floor_changed_plate':
                    s['manufacturing_floor_governs'],
                'throat_meridional_check':
                    self._throat_check_publication(s['throat_check']),
            },
            'design_requirements': {
                'proof_pressure':
                    chamber_internal_pressure * PROOF_PRESSURE_FACTOR / 1e5,  # bar
                'burst_pressure':
                    chamber_internal_pressure * BURST_PRESSURE_FACTOR / 1e5,  # bar
                'operating_temperature': self.T_c,  # K
                'thermal_cycles': getattr(self, 'thermal_cycles',
                                          THERMAL_CYCLES_DEFAULT)
            },
            # A4 (v2.6.27): kapak/enjektör flanşı cıvata birleşimi — katı
            # motorla aynı şema adı (closure_joint) ve aynı analizör.
            'closure_joint': self._closure_joint_analysis(),
            # ÖH D22 / P9B1-17: baş kapak ARTIK yapısal analize soruluyor.
            # V3 yapi-sf 4. tur (karar §28-44 (i)): hazne cidarının
            # geçerlilik bayrağı kapağa da taşınır (bkz.
            # ``_end_cap_publication``).
            'end_cap_analysis': self._end_cap_publication(gecerlilik),
        }

    def _forward_closure_length_mm(self, structural_analysis=None):
        """(kapak eksenel boyu [mm], künye) — imalat STEP'iyle TEK KAYNAK.

        ÖH D24 · defter P9B2-24. ÖLÇÜLEN KUSUR: yayımlanan
        ``design_summary.key_dimensions.overall_length_mm`` hazne + yakınsak
        koni + ıraksak lüle toplamıdır ve x < 0'daki ön kapağı SAYMAZ; oysa
        indirilen imalat STEP'i kapağı çizer. D23'te ölçülmüştü (hibrit a1,
        10 kN): yayımlanan 401,536 ⟷ montaj 408,286 mm; bu ağaçta yeniden
        ölçüldü (once.json P9B2-24): yayımlanan 517,529 mm, kapak 7,001 mm
        (+%1,353). İki sayı hiçbir alanda uzlaştırılmıyordu.

        Kapak boyu BURADA HESAPLANMAZ. İhraç katmanının çizdiği parça DÜZ
        kapaktır ve kalınlığını ``end_cap_analysis.flat_head_thickness``tan
        okur (``export/cad_visualization._front_cap_design``); bu metot aynı
        alandan okur, böylece panel ile tezgâh aynı sayıyı söyler. Yapısal
        analiz kapağı boyutlandıramadıysa sayı UYDURULMAZ: ``None`` döner ve
        künye nedenini söyler (fail-closed).

        Not: ``head_thickness_used_mm`` DEĞİL ``flat_head_thickness``
        okunur — birincisi analizin DEĞERLENDİRDİĞİ (dişbükey olabilen)
        kalınlıktır, ikincisi katının fiilen çizildiği düz kapaktır. Ölçüldü
        (once.json): aynı koşuda 0,684 ⟷ 7,001 mm, yani ikisi aynı büyüklük
        değildir ve montajın boyunu belirleyen ikincisidir.
        """
        blok = (structural_analysis
                if isinstance(structural_analysis, dict) else {})
        cap = blok.get('end_cap_analysis')
        cap = cap if isinstance(cap, dict) else {}
        if not cap:
            return None, (
                'the forward closure length is not published because this '
                'run has no structural end-cap analysis to read it from; it '
                'is NOT estimated from a geometry rule')
        durum = cap.get('status')
        ham = cap.get('flat_head_thickness')
        try:
            t_mm = float(ham)
        except (TypeError, ValueError):
            t_mm = None
        if durum != 'sized' or t_mm is None or not np.isfinite(t_mm) \
                or t_mm <= 0:
            return None, (
                'the forward closure length is not published because the '
                'structural end-cap analysis did not size a flat head on '
                'this run (status='
                + str(durum or 'missing')
                + '); no thickness is invented in its place. Reason: '
                + str(cap.get('basis') or 'not stated'))
        return t_mm, (
            f'overall_length_with_closure_mm adds the {t_mm:.3f} mm flat '
            'closure head that the manufacturing STEP draws at x < 0, read '
            'from the SAME field the exporter reads '
            '(structural_analysis.end_cap_analysis.flat_head_thickness, '
            'Roark Table 11.2 / ASME VIII-1 UG-34), so the panel length and '
            'the downloaded solid reconcile')

    def _end_cap_analysis(self):
        """Baş/enjektör tarafı kapak kalınlığı — hrma.analysis.structural.

        ÖH D22 / P9B1-17. ÖLÇÜLEN KUSUR: sıvı yanıtının
        ``structural_analysis`` bloğunda ``end_cap_analysis`` HİÇ YOKTU
        (ölçüldü: raw/OH/D22/sivi/a1/once_ham.json — blok anahtarları yalnız
        ``chamber_structure``, ``closure_joint``, ``design_requirements``).
        Basınç sınırındaki kapak bu yüzden CAD üreticisinin kendi kuralına
        kalıyordu: ``cad_visualization.py`` bunu kendi künyesinde
        "(katı ve sıvı sonuçlarında end_cap_analysis bloğu YOK) ... so the
        thickness is a generator assumption" diye yazıyor, yani kapak
        ASSUMED künyesiyle çiziliyordu. Uydurma kuralla çizilen bir kapak
        basınç sınırıdır: patlarsa motor patlar.

        Kapanış BEYANLA DEĞİL HESAPLA: çözücü zaten vardı
        (``StructuralAnalyzer._analyze_end_caps`` — Roark Tablo 11.2 düz
        dairesel plaka + ASME BPVC VIII-1 UG-34 çapraz denetimi, dişbükey
        kapak için UG-32(d)); sıvı motor onu hiç çağırmıyordu. Girdiler bu
        koşunun KENDİ sayılarıdır: tasarım basıncı (proof çarpanıyla, cidar
        boyutlandırmasıyla AYNI kaynak), hazne iç çapı, malzeme kaydı,
        kullanıcının emniyet katsayısı ve cidar sıcaklığındaki derating.
        Kullanıcı gerçek kapak kalınlığı verirse (``end_cap_thickness``)
        çözücü doğrulama moduna geçer. Çözülemezse sayı UYDURULMAZ:
        'not_sized' + gerekçe döner.
        """
        try:
            from hrma.analysis.structural_analysis import StructuralAnalyzer
        except Exception as exc:
            return {'status': 'not_sized',
                    'basis': f'structural analyser unavailable: {exc}'}
        material, mat_key = self._material_record()
        analiz = StructuralAnalyzer()
        mat_props = analiz.materials.get(mat_key)
        if mat_props is None:
            return {
                'status': 'not_sized',
                'basis': (
                    f"the chamber material '{mat_key}' has no record in the "
                    'structural materials view, so the end cap is NOT sized; '
                    'no thickness is invented in its place.'),
            }
        t_hot, _ = self._wall_temperatures()
        try:
            derating = analiz._derate_strength(mat_props, float(t_hot))
        except Exception:
            derating = None
        # KANAL AÇILMADI (tests/test_sivi_form_alanlari.py::
        # test_motorda_okunan_her_anahtarin_formda_kapisi_var): çözücü
        # ``actual_thickness`` ile doğrulama modunu destekliyor ama /liquid
        # formunda kapak kalınlığı alanı YOKTUR. Formda kapısı olmayan bir
        # override kanalı açmak tam olarak bu deponun kovaladığı kusurdur
        # ("kanal var kapı yok"), bu yüzden kapak burada YALNIZ
        # BOYUTLANDIRILIR. Doğrulama modu, forma alan eklendiği gün
        # (arayüz kulvarı) tek satırla bağlanır.
        t_kapak_m = None
        # Tasarım basıncı: hazne cidarıyla AYNI tanım (proof çarpanı dâhil).
        design_pressure_pa = (float(self.P_c) * PA_PER_BAR
                              * float(PROOF_PRESSURE_FACTOR))
        try:
            res = analiz._analyze_end_caps(
                design_pressure_pa, float(self._chamber_diameter()),
                mat_props, derating=derating,
                design_safety_factor=float(
                    getattr(self, 'safety_factor', SAFETY_FACTOR_DEFAULT)),
                actual_thickness=t_kapak_m)
        except Exception as exc:
            return {'status': 'not_sized',
                    'basis': f'end-cap analysis rejected the inputs: {exc}'}
        if not isinstance(res, dict):
            return {'status': 'not_sized',
                    'basis': 'the end-cap analyser returned no result'}
        res = dict(res)
        res['status'] = 'sized'
        res['design_pressure_bar'] = design_pressure_pa / PA_PER_BAR
        res['material_key'] = mat_key
        res['material'] = material.get('name', mat_key)
        res['thickness_source'] = 'sized by the structural analyser'
        res['design_mode_note'] = (
            'size mode only: the /liquid form has no end-cap thickness field, '
            'so no verification thickness is read here and none is invented.')
        res['_basis'] = (
            'Flat circular head: Roark Table 11.2 (uniformly loaded circular '
            'plate) with the ASME BPVC VIII-1 UG-34 bolted flat head form as '
            'a cross-check; 2:1 ellipsoidal (dished) head: ASME UG-32(d). '
            'The design pressure is this run own chamber pressure raised by '
            f'the proof factor ({PROOF_PRESSURE_FACTOR:g}), the same '
            'definition the chamber wall uses; the yield strength is derated '
            'at the solved hot-wall temperature and the design safety factor '
            'is the user input, so the head is not sized on a different '
            'basis from the rest of the vessel. Before this block existed '
            'the CAD generator had no analysed thickness to read and drew '
            'the head from its own assumption (P9B1-17).')
        return res

    def _end_cap_publication(self, gecerlilik):
        """Yayımlanan ``end_cap_analysis`` — hazne geçerlilik bayrağıyla.

        V3 yapi-sf 4. tur (karar §28-44 (i); yeniden denetim-3 U3 (i)).
        ÖLÇÜLDÜ (denetim-3, olc/dal/sivi_rad.json): inconel_718 hazne 1800 K
        (erime 1533 K) iken ``chamber_structure`` geçerlilik dışı ve
        ``verdict_withheld`` diyordu; aynı yanıttaki kapak bloğu ise eğrinin
        sonunda kırpılmış üst sınır dayanımla (385 MPa) boyutlanan 3,756 mm
        başlık ve SF 2,5'i hiçbir işaret olmadan yayımlıyordu.

        Ölçüt BURADA YAZILMAZ: kapak dayanımı hazne cidarıyla AYNI sıcaklık
        (``_wall_temperatures``) ve AYNI malzeme kaydından
        (``_material_record``) düşürülür, bu yüzden hazne bayrağı
        (``gecerlilik``, ``_calculate_structural_loads``ın TEK ölçüt
        çağrısı) kapağın da bayrağıdır. Geçerlilik dışında kapak bloğu aynı
        bayrak + künye + ``verdict_withheld`` taşır; sayılar ve ``status``
        (imalat/CAD bu alandan kalınlık okur) değişmez. Geçerlilik içinde
        blok bit-aynı kalır.
        """
        kapak = self._end_cap_analysis()
        if (isinstance(gecerlilik, dict)
                and gecerlilik.get('model_validity_limit_exceeded') is True
                and isinstance(kapak, dict) and kapak.get('status') == 'sized'):
            kapak = {**kapak, **gecerlilik}
        return kapak


    def _build_heat_transfer_analysis(self, cooling=None):
        """Güverte ısı haritasının okuduğu şemayı yayımlar (Z5-C5 / OH-Z3-03).

        ÖLÇÜLEN KUSUR (kanıt: ``docs/scofield/raw/OH/Z5/c/
        olcum_c5_isi_haritasi_once.txt``): ``/calculate_liquid`` yanıtında
        ``heat_transfer_analysis`` bloğu HİÇ YOKTU. 3B güvertenin ısı
        haritası kapısı ``motor_viz3d.js:1841``'de şudur::

            heat = null;
            if (gas.throat_heat_flux) { heat = {...} }

        Yani blok olmayınca ``getHeatInfo()`` null döner ve güverte ısı
        düğmesini GİZLER. Sıvı motorda ısı haritası bu yüzden ERİŞİLEMEZDİ.

        Bu metot YENİ FİZİK HESABI YAPMAZ. Bütün sayılar
        ``calculate_cooling_requirements()``'in (Bartz gaz-tarafı korelasyonu
        + kanal hidroliği; süperkritik marş çözüldüyse onun tepe akısı)
        ZATEN döndürdüğü değerlerdir; burada yalnızca birim çevrimi
        (kW/m² -> W/m²) ve şema adlandırması yapılır, gerekçe alanı da
        çözücünün kendi beyanını taşır.

        FAIL-CLOSED: akılar yoksa ya da fiziksel değilse blok
        ``NOT_MODELLED`` döner ve ``throat_heat_flux`` KONMAZ — güverte
        düğmesi kapalı kalır. Cidar sıcaklıkları ise yalnız çözücünün KENDİ
        kaynak beyanı çözüldüğünü söylediğinde yayımlanır: ``assumed
        (cooling-type default)`` beyanlı 800/350 K yuvarlak TASARIM HEDEFİ
        bir ölçüm değildir ve ısı haritasında ölçüm gibi gösterilemez
        (aynı kapı ``analysis_dock.readWallTemperaturesK``'de de var).

        Args:
            cooling: ``calculate_cooling_requirements()`` sonucu; None ise
                yeniden çözülür.

        Returns:
            ``heat_transfer_analysis`` sözlüğü.
        """
        if cooling is None:
            cooling = self.calculate_cooling_requirements()

        basis = (
            'republished from cooling_system (Bartz gas-side correlation '
            'with rectangular-channel hydraulics; Sutton & Biblarz 9th ed. '
            'Eq. 8-23) — no separate heat-transfer solve runs here, only a '
            'kW/m^2 -> W/m^2 unit change and the schema the 3D deck reads')

        def _pozitif(x):
            try:
                v = float(x)
            except (TypeError, ValueError):
                return None
            return v if (np.isfinite(v) and v > 0) else None

        q_throat_kw = _pozitif(cooling.get('peak_heat_flux'))
        q_chamber_kw = _pozitif(cooling.get('chamber_heat_flux'))
        eksik = [ad for ad, deger in (('peak_heat_flux', q_throat_kw),
                                      ('chamber_heat_flux', q_chamber_kw))
                 if deger is None]
        if eksik:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (
                    'the deck heat map needs the Bartz chamber and throat '
                    'fluxes; missing or non-physical in this run: '
                    + ', '.join(eksik)),
                'gas_side_analysis': {},
                'wall_analysis': {},
            }

        wall_source = str(cooling.get('wall_temperature_source') or '')
        # Yalnız ÇÖZÜLMÜŞ cidar sıcaklığı yayımlanır (tasarım hedefi değil).
        cozuldu = 'solved' in wall_source.lower()
        t_hot = _pozitif(cooling.get('wall_temperature_hot'))
        t_cold = _pozitif(cooling.get('wall_temperature_cold'))

        wall_analysis = {
            'wall_temperature_source': wall_source or None,
            'wall_temperature_solved': bool(cozuldu),
            'inner_temperature': (t_hot if cozuldu else None),
            'outer_temperature': (t_cold if cozuldu else None),
            # Çözülmemişse sayı GİZLENİR ama nereye baktığı yazılır:
            # tasarım hedefi ayrı bir alanda, ölçüm gibi görünmeden durur.
            'design_target_wall_temperature_hot_K': t_hot,
            'design_target_wall_temperature_cold_K': t_cold,
        }
        if not cozuldu:
            wall_analysis['wall_temperature_status'] = 'not_solved'
            wall_analysis['wall_temperature_withheld_reason'] = (
                'cooling_system.wall_temperature_source is '
                f'{wall_source!r}: the hot/cold wall pair is a design '
                'requirement the Bartz chain was evaluated AT, not a solved '
                'equilibrium — publishing it into the heat map would show an '
                'assumption as a measurement')

        # --- ÖH D16 / OH-Z5-01: SÜRÜCÜ (TOPARLANMA) SICAKLIĞI --------------
        # Ölçüldü (``raw/OH/D16/sivi/a1/once.json``): rejeneratif soğutulan
        # sıvı koşumunda yanıtın TAMAMINDA ``T_recovery_K`` yolu SAYISI 0'dı;
        # kardeş hibritte 9, sıvının kendi ablatif/ışınım dallarında 3 ve 2.
        # Yani koruma paneli sıvıda (h_gas, T_recovery) çiftini bulamıyor ve
        # kendi panel varsayılanında kalıyordu. Eksik olan bir MODEL değil,
        # zincirin ZATEN kullandığı sayının yayımlanmasıydı:
        #
        #   * Sürücü sıcaklık T_c'dir. Haznede M ~ 0 olduğu için T_aw ~ T_c;
        #     boğaz/yakınsak istasyonda da zincirin KENDİSİ T_c kullanır
        #     (``calculate_cooling_requirements``: q = h_g*(T_c - T_wall)).
        #     Bu, ``_passive_thermal_protection``ın astar istasyonlarına
        #     geçirdiği AYNI sürücüdür — iki blok iki farklı T_aw varsayamaz.
        #   * Kamara h_g'si bu akıdan CEBİRSEL olarak geri gelir:
        #     q_kamara/(T_c - T_cidar_sicak). İkinci bir Bartz hesabı YOK.
        #
        # Fail-closed: T_c ya da payda çözülemiyorsa sayı yayımlanmaz,
        # yokluğu adıyla beyan edilir (uydurma sürücü sıcaklık basılmaz).
        gas_side = {
            # W/m² — güvertenin okuduğu birim (hibrit blokla aynı).
            'throat_heat_flux': q_throat_kw * 1000.0,
            'chamber_heat_flux': q_chamber_kw * 1000.0,
            'heat_flux_basis': (
                'cooling_system.peak_heat_flux (throat) and '
                'cooling_system.chamber_heat_flux, converted kW/m^2 '
                '-> W/m^2'),
            'gas_side_coefficient_throat': _pozitif(
                cooling.get('bartz_coefficient')),
        }
        t_c = _pozitif(getattr(self, 'T_c', None))
        if t_c is None:
            gas_side['T_recovery_K'] = None
            gas_side['T_recovery_status'] = 'NOT_MODELLED'
            gas_side['T_recovery_basis'] = (
                'the recovery (driving) temperature is not published: this '
                'run has no finite chamber temperature, and the Bartz chain '
                'driver is NOT substituted with a nominal value')
        else:
            # --- Fable-D16 ŞART (OH-Z5-01) ---------------------------------
            # Denetçi ŞART'ı: bu iki künye ``wall_temperature_source``a
            # BAĞLANMALI. Gerekçe ölçüldü: cidar 1B süperkritik istasyon
            # MARŞI ile çözüldüğünde (metan/LH2 rejeneratif) yayımlanan
            # ``chamber_heat_flux`` artık Bartz'tan değil MARŞIN kendi hazne
            # payından gelir (q = Q_chamber/A_chamber) ve
            # ``wall_temperature_hot`` marşın TEPE cidarıdır. O koşumda
            # q_kamara/(T_c - T_cidar) bölmesi 'bu koşumun Bartz kamara
            # katsayısı' DEĞİLDİR — künye öyle diyorsa yalan söyler.
            # Ölçüldü (once.json, methane/lox 25 kN Pc=100 rejeneratif):
            # wall_temperature_solved=True iken künye 'returns the Bartz
            # chamber coefficient of this run' iddiasını taşıyordu.
            # Ayrıca marşta sürücü sıcaklık her istasyonda T_aw(x)'tir;
            # kamara istasyonunda T_aw ~ T_c olduğu için yayımlanan sayı
            # geçerli kalır ama künye bunu söylemelidir.
            marsli = bool(cozuldu)
            gas_side['T_recovery_K'] = t_c
            gas_side['T_recovery_source'] = (
                'solved' if marsli else 'assumed')
            gas_side['T_recovery_basis'] = (
                (
                    'T_recovery = the chamber temperature of this run. The '
                    'wall of this run is SOLVED by the 1D supercritical '
                    'station march (cooling_system.wall_temperature_source), '
                    'and that march evaluates its own T_aw(x) at every '
                    'station; at the CHAMBER station M ~ 0 so T_aw ~ T_c, '
                    'which is the value published here. It is the same '
                    'driver the passive thermal protection block passes to '
                    'the liner stations - no second Bartz evaluation is made '
                    'here.'
                ) if marsli else (
                    'T_recovery = the chamber temperature of this run. The '
                    'wall temperature of this run is ASSUMED '
                    '(cooling_system.wall_temperature_source), so the Bartz '
                    'chain is evaluated AT that wall: in the chamber M ~ 0 '
                    'so T_aw ~ T_c, and the chain uses T_c as the driving '
                    'temperature at BOTH the chamber and the throat station '
                    '(q = h_g*(T_c - T_wall)). It is the SAME driver the '
                    'passive thermal protection block passes to the liner '
                    'stations - no second Bartz evaluation is made here.'
                ))
            delta = (t_c - t_hot) if t_hot is not None else None
            if delta is None or delta <= 0:
                gas_side['gas_side_coefficient_chamber'] = None
                gas_side['gas_side_coefficient_chamber_status'] = (
                    'NOT_PUBLISHED')
                gas_side['gas_side_coefficient_chamber_basis'] = (
                    'chamber coefficient not published: recovering it needs '
                    'a positive (T_recovery - wall_temperature_hot), and '
                    'this run does not have one')
            elif marsli:
                # ŞART, birinci seçenek: MARŞLI koşumda katsayı
                # yayımlanmaz. Bölme cebirsel olarak yapılabilir ama
                # sonucu Bartz kamara katsayısı DEĞİLDİR (akı marş ısı
                # payından, cidar marş tepe değerinden gelir), ve
                # 'Bartz' iddiası taşımayan bir sayı da bu alanda
                # tüketiciyi yanıltır. Fail-closed: sayı yerine adıyla
                # beyan edilen yokluk.
                gas_side['gas_side_coefficient_chamber'] = None
                gas_side['gas_side_coefficient_chamber_status'] = (
                    'NOT_PUBLISHED')
                gas_side['gas_side_coefficient_chamber_basis'] = (
                    'chamber gas-side coefficient NOT published in this run: '
                    'cooling_system.wall_temperature_source is a SOLVED 1D '
                    'supercritical station march, so chamber_heat_flux is '
                    'the march heat split (Q_chamber/A_chamber) and '
                    'wall_temperature_hot is the march PEAK wall, not the '
                    'wall the Bartz chamber-station coefficient was '
                    'evaluated at. '
                    'q_chamber/(T_recovery - wall_temperature_hot) would '
                    'therefore be an EFFECTIVE coefficient consistent with '
                    'the march heat share, and it is NOT a Bartz '
                    'chamber-station coefficient - so it is not published '
                    'under that name. The throat coefficient '
                    '(gas_side_coefficient_throat) is still the Bartz value '
                    'and is published.')
                gas_side['gas_side_effective_chamber_coefficient_if_march'] = (
                    q_chamber_kw * 1000.0 / delta)
                gas_side[
                    'gas_side_effective_chamber_coefficient_if_march_basis'
                ] = (
                    'q_chamber/(T_recovery - wall_temperature_hot) with the '
                    'march heat split and the march peak wall. It is an '
                    'EFFECTIVE coefficient consistent with the march heat '
                    'share, and it is NOT a Bartz chamber-station '
                    'coefficient; it is carried under this explicit name so '
                    'it can never be read as one')
            else:
                gas_side['gas_side_coefficient_chamber'] = (
                    q_chamber_kw * 1000.0 / delta)
                gas_side['gas_side_coefficient_chamber_status'] = 'PUBLISHED'
                gas_side['gas_side_coefficient_chamber_basis'] = (
                    'chamber coefficient recovered from the chamber design '
                    'flux: h_g = q_chamber/(T_recovery - '
                    'wall_temperature_hot). cooling_system.'
                    'wall_temperature_source is ASSUMED, so the chamber flux '
                    'is BUILT as h_g*(T_c - wall_temperature_hot) at that '
                    'same wall and this division returns the Bartz chamber '
                    'coefficient of this run.')

        return {
            'status': 'modelled',
            '_basis': basis,
            'source': 'cooling_system',
            'gas_side_analysis': gas_side,
            'wall_analysis': wall_analysis,
            'cooling_analysis': {
                'cooling_type': getattr(self, 'cooling_type', None),
                'total_heat_load_kW': cooling.get('total_heat_load'),
                'coolant_temperature_rise_K': cooling.get(
                    'coolant_temperature_rise'),
            },
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
        # --- ÖH D24 · P3B4-14 · KANALSIZ TASARIMDA KANAL YAYIMLANMAZ -------
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/D24/sivi/a1/once.json, P3B4-14; taban
        # 88a29d3): ``cooling_type='ablative'`` ve ``'radiative'`` koşumlarında
        # bu blok kanal SAYISI 0 iken şunları yayımlıyordu —
        #   channel_dimensions      '3.0 mm x 2.0 mm'
        #   channel_count_source    'computed from throat circumference and
        #                            channel pitch'
        #   coolant_type            'RP1'
        #   coolant_inlet/exit_temp 300,0 K
        # Yani olmayan bir kanalın ölçüsü, o ölçünün HESAPLANDIĞI ('computed')
        # künyesi ve olmayan bir soğutucunun adı ile sıcaklığı basılıyordu.
        # Ablatif/ışınımlı motorda ceket YOKTUR (COOLING_TYPES_PASSIVE);
        # ``calculate_cooling_requirements`` bu tiplerde ceket kolunu hiç
        # koşmaz, dolayısıyla o dört alan hesaptan değil VARSAYILAN
        # değerlerden geliyordu. Beyan çözüm değildir: alanlar artık
        # yayımlanmaz (None) ve NEDENİ adıyla yazılır. Kapı kanal SAYISINA
        # bakar (tipe değil), çünkü aktif soğutmalı bir tasarımda da ceket
        # kapanmayabilir (warn.liquid.cooling_channels_do_not_fit).
        _kanal_sayisi = cooling.get('cooling_channels', 0) or 0
        _kanalli = bool(_kanal_sayisi > 0)
        _kanalsiz_beyan = (
            'no cooling channels exist in this design '
            f"(cooling_type='{self.cooling_type}', cooling_channels="
            f'{int(_kanal_sayisi)}), so the channel section, its provenance, '
            'the coolant name and the coolant temperatures are NOT published: '
            'there is no coolant circuit to describe and no number is '
            'carried over from the regenerative defaults')
        result = {
            'cooling_type': self.cooling_type.replace('_', ' ').title(),
            'coolant_type': (self.fuel_type.upper() if _kanalli else None),
            'cooling_channels': _kanal_sayisi,
            'channel_dimensions': (
                f"{cooling.get('channel_width_mm', 0):.1f} mm x "
                f"{cooling.get('channel_height_mm', 0):.1f} mm"
                if _kanalli else None),
            'channel_count_source': (
                cooling.get('channel_count_source', 'computed')
                if _kanalli else None),
            'coolant_circuit_status': ('modelled' if _kanalli
                                       else 'no_cooling_channels'),
            'coolant_circuit_basis': (None if _kanalli else _kanalsiz_beyan),
            # v2.6.26: tek metin iki farklı şeyi anlatamaz. Eski
            # 'channel_section_source' genişlik ve derinliği birlikte "design
            # default (not auto-sized)" ilan ediyordu; derinlik için bu YALANDI.
            # Beyanlar ayrıldı ve sayının yanına taşındı (cooling_system).
            'channel_width_basis': (COOLING_CHANNEL_WIDTH_BASIS
                                    if _kanalli else None),
            'channel_height_basis': (COOLING_CHANNEL_HEIGHT_BASIS
                                     if _kanalli else None),
            'channel_height_auto_sized': (
                cooling.get('channel_height_auto_sized') if _kanalli
                else None),
            'coolant_velocity': (cooling.get('coolant_velocity', 0.0)
                                 if _kanalli else None),  # m/s
            'coolant_reynolds': (cooling.get('coolant_reynolds', 0.0)
                                 if _kanalli else None),
            'wall_temperature': t_hot,  # K (sıcak cidar tasarım hedefi)
            'wall_temperature_source': (
                'user input (max wall temperature)'
                if getattr(self, 'max_wall_temp_input', None) is not None
                else 'cooling-type design default'),
            'coolant_wall_temperature': t_cold,  # K
            # Bartz tepe akısı boğazdadır; cooling_system kW/m² döndürür.
            'heat_flux': cooling.get('peak_heat_flux', 0.0) / 1000.0,  # MW/m²
            'chamber_heat_flux': cooling.get('chamber_heat_flux', 0.0) / 1000.0,
            'pressure_drop': (cooling.get('cooling_pressure_drop', 0.0)
                              if _kanalli else None),  # bar
            'temperature_rise': (
                cooling.get('coolant_temperature_rise', 0.0)
                if _kanalli else None),  # K
            'coolant_inlet_temperature': (
                cooling.get('coolant_inlet_temperature',
                            COOLANT_INLET_TEMP_DEFAULT_K)
                if _kanalli else None),
            'coolant_exit_temperature': (
                cooling.get('coolant_exit_temperature')
                if _kanalli else None),
            'total_heat_load_kw': cooling.get('total_heat_load', 0.0),
            'model': ('Bartz gas-side correlation with rectangular-channel '
                      'hydraulics (Sutton & Biblarz 9th ed. Eq. 8-23; '
                      'Darcy-Weisbach with Haaland friction factor)'),
        }
        # F5-4 (bebek-Scofield, 2026-08-17): yukarıdaki akı/ΔT/çıkış
        # sıcaklığı/ΔP değerlerinin HANGİ cidar kapanışından geldiği artık
        # sayının yanında yazar. Süperkritik marş (metan/LH2) soğutma
        # zincirini zaten TEK kaynağa indirger; RP-1'de ise toplu Bartz
        # zinciri cidarı TASARIM sıcaklığında TUTULMUŞ varsayar (bir
        # gereksinim) ve 1B istasyon marşı aynı devreyi kuple ÇÖZER (bir
        # denge). Ölçülen fark (örnek motor): tepe akı 52,15 ⟷ 10,95 MW/m²
        # (4,76×), çıkış 820,0 ⟷ 421,9 K — ikisi aynı büyüklük DEĞİLDİR ve
        # fark channel_circuit_reconciliation bloğunda adıyla yayımlanır.
        _chain_solved = 'solved' in str(
            cooling.get('wall_temperature_source', ''))
        if _chain_solved:
            _chain_basis = (
                'coupled 1D supercritical station march (solved wall '
                'temperature) — the single source for this circuit; see '
                'cooling_system.wall_temperature_source')
        else:
            _chain_basis = (
                'Bartz chain evaluated AT the design wall temperature '
                f'({t_hot:g} K, {result["wall_temperature_source"]}): a '
                'requirement to hold that wall, NOT a solved equilibrium of '
                'the as-built channels — the solved equilibrium is the '
                'station_march block; the measured gap between the two is '
                'published in channel_circuit_reconciliation')
        result['heat_flux_basis'] = _chain_basis
        result['temperature_rise_basis'] = _chain_basis
        result['coolant_exit_temperature_basis'] = _chain_basis
        result['pressure_drop_basis'] = _chain_basis
        if self.cooling_type in ('ablative', 'radiative'):
            material, _ = self._material_record()
            result['material'] = material.get('name', self.chamber_material)
            # ÖH D37 A2-1 / F-01 + M2 (patch/motor_m2.patch): "servis sınırı"
            # diye ERİME yayımlanıyordu (max_service_temperature = melting_point
            # 20/24 kayıtta; ss_304 1673, 718 1533 K). Künye artık tek eşik
            # merdiveninin İZİN basamağı (ss_304 1073, 718 977 K) ve
            # basamakların hepsi yanında durur — ÖNEMLİ, önce/sonra tablosu.
            from hrma.data.materials_db import temperature_limits
            _tl = temperature_limits(material)
            result['material_service_limit_K'] = _tl['allowable_K']
            result['material_service_limit_basis'] = (
                'materials_db.temperature_limits(rec).allowable_K = '
                'min(allowable_temperature, max_service_temp) (F-01/M2 single '
                'ladder); before this change the field carried '
                'max_service_temperature, which equals the melting point for '
                'most records')
            result['material_temperature_ladder_K'] = {
                'allowable_K': _tl['allowable_K'], 'service_K': _tl['service_K'],
                'melting_K': _tl['melting_K']}

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
                # ÖH defter P15B1-06 (Z5S/PK1): aynı soğutma devresinin İKİ
                # çözümünden yalnız biri (toplu Bartz zinciri) üst katmanın
                # ÇIPLAK alanlarına çıkıyordu; kuple çözülmüş istasyon marşı
                # yalnız 'station_march' alt bloğunda kalıyordu. Çıplak alanı
                # okuyan her tüketici (panel, PDF/ihracat, AI belgesi) bu
                # yüzden tek kümeyi görüyordu. ÖLÇÜLDÜ (10 kN / Pc=100):
                # akı 79,8703 ⟷ 11,6788 MW/m², çıkış 796,0493 ⟷ 453,7269 K,
                # ΔP 1,4780 ⟷ 1,2348 bar — marş karşılığını taşıyan üst
                # katman alanı YOKTU.
                #
                # Takma adlar (heat_flux / coolant_exit_temperature /
                # pressure_drop) DEĞİŞMEZ: bugün toplu zinciri taşıyorlar ve
                # o bağ bilinçli olarak kilitlidir. Marş karşılığı ayrı ADLA,
                # ayrı KÜNYEYLE üst katmana çıkar — iki küme aynı adı
                # paylaşmaz, biri diğerinin yerine sessizce geçmez.
                _march_basis = (
                    'coupled 1D station march (regen_cooling) solution of '
                    'THIS same cooling circuit, published alongside the bulk '
                    'Bartz chain value of the same name; the two are not the '
                    'same quantity and their measured gap is reported in '
                    'channel_circuit_reconciliation')
                result['heat_flux_station_march_MW_m2'] = \
                    summary['peak_heat_flux_MW_m2']
                result['coolant_exit_temperature_station_march_K'] = \
                    summary['coolant_exit_temp_K']
                result['pressure_drop_station_march_bar'] = \
                    summary['total_pressure_drop_bar']
                result['temperature_rise_station_march_K'] = (
                    float(summary['coolant_exit_temp_K'])
                    - float(result['coolant_inlet_temperature']))
                result['station_march_scalars_basis'] = _march_basis
                # F5-4: aynı devrenin iki çıktı kümesi arasındaki fark
                # adıyla ve ölçülen sayılarla yayımlanır; hangi kümenin
                # fiziksel denge olduğu enerji dengesiyle bloğun içinde
                # karara bağlanır.
                result['channel_circuit_reconciliation'] = \
                    self._channel_circuit_reconciliation(
                        cooling, summary, march)
            except Exception as exc:
                result['station_march_status'] = (
                    f'1D station march not run: {exc}')
                # ÖH A2 sivi-sogutma · 6. tur (marş zarfı uyarı kanalı):
                # marş DENENDİ ve koşmadı (ölçüldü: kalın cidarda ince-cidar
                # zarfı reddi — Al 50 mm, Cu 40 mm, 304 10 mm, 316 8 mm;
                # 250 kN / 20 bar). Marş koşsaydı tepe cidar sıcaklığının
                # ısıl hükmü (CRITICAL erime vb.) station_march.warnings'te
                # yayımlanırdı; koşmayınca o hüküm yalnız
                # station_march_status künyesinde kalıyor, uyarı listesine
                # HİÇBİR şey düşmüyordu (sessiz kayıp). Artık "ısıl hüküm
                # verilmedi" uyarı kanalından ADIYLA söylenir; neden aynı
                # metin (detail). Sayı üretilmez — fail-closed.
                self._warn('warn.liquid.station_march_not_run', 'warning',
                           fuel=str(self.fuel_type), detail=str(exc))
        else:
            result['station_march_status'] = (
                '1D station march available for RP-1 regenerative cooling '
                'only; the values above come from the Bartz chamber/nozzle '
                'integration.')

        # ÖH D15 BİRLEŞME ETKİLEŞİMİ (1 Eylül 2026) — SARKAN BEYAN.
        #
        # Yukarıdaki dört künye (_chain_basis) marş DENENMEDEN önce yazılıyor
        # ve "the solved equilibrium is the station_march block; ... published
        # in channel_circuit_reconciliation" diyor. Termo-uçuş kulvarının
        # **P4B2-09** onarımı RegenCooling'e ince-cidar zarfı kapısı koydu
        # (düz-levha ⟷ silindirik iletim direnci bağıl farkı > %10 -> ret).
        # ÖLÇÜLDÜ (deponun kendi form varsayılanları, 10 kN / Pc=100 /
        # chamber_wall_thickness = 5 mm, boğaz yarıçapı 15,4 mm: fark %13,4):
        # marş REDDEDİLİYOR, dolayısıyla station_march ve
        # channel_circuit_reconciliation blokları yanıtta HİÇ YOK — ama künye
        # kullanıcıyı hâlâ o iki bloğa yolluyordu. Var olmayan bloğa işaret
        # eden beyan, beyansız sayıdan kötüdür: kullanıcı aradığını bulamaz ve
        # farkın ölçüldüğünü sanır.
        #
        # Künye artık marş kararından SONRA kesinleşir: çözülmüş denge
        # yayımlanmadıysa beyan bunu söyler ve reddin gerekçesini taşıyan
        # ALANI (station_march_status) adıyla gösterir. Marş koştuğunda metin
        # bit-aynı kalır (P15B1-06 / F5-4 sözleşmesi bozulmaz).
        if ('channel_circuit_reconciliation' not in result
                and not _chain_solved):
            _chain_basis = (
                'Bartz chain evaluated AT the design wall temperature '
                f'({t_hot:g} K, {result["wall_temperature_source"]}): a '
                'requirement to hold that wall, NOT a solved equilibrium of '
                'the as-built channels. The coupled 1D station march that '
                'would solve that equilibrium was NOT published for this run '
                '- the reason is named in station_march_status - so no '
                'measured gap is available and none is implied here.')
            result['heat_flux_basis'] = _chain_basis
            result['temperature_rise_basis'] = _chain_basis
            result['coolant_exit_temperature_basis'] = _chain_basis
            result['pressure_drop_basis'] = _chain_basis

        # --- A5 (v2.6.27): ablatif/radyatif ısıl koruma boyutlandırması ----
        result.update(self._passive_thermal_protection(cooling))
        return result

    def _channel_circuit_reconciliation(self, cooling, summary, march):
        """Aynı soğutma devresinin iki çıktı kümesini ADIYLA mutabık kılar.

        F5-4 (bebek-Scofield, 2026-08-17). Ölçülen çelişki (örnek 25 kN
        LOX/RP-1, Pc=70 bar): toplu Bartz zinciri tepe akı 52,15 MW/m² /
        çıkış 820,0 K derken 1B istasyon marşı 10,95 MW/m² / 421,9 K
        diyordu — aynı yanıtta, aynı devre için, beyansız.

        İki küme aynı büyüklük DEĞİLDİR:

        * ``bulk_chain`` — Bartz gaz tarafı, cidar TASARIM sıcaklığında
          TUTULMUŞ varsayılarak (gereksinim). Kendi enerji dengesini kurgu
          gereği kapatır (ΔT := Q/(ṁ·cp)).
        * ``station_march`` — kanal hidroliğiyle KUPLE çözülmüş denge; kendi
          enerji dengesi (ṁ·c̄p·ΔT = ∮q dA) ölçülerek yayımlanır.

        Hangisinin fiziksel denge olduğu enerji dengesiyle karara bağlanır:
        tasarım-cidar akısını kanal filmi taşıyabiliyorsa iki küme yakınsar;
        taşıyamıyorsa (q_tasarım/h_c gereken film ΔT'si mevcut film ΔT'sini
        aşar) cidar tasarım sıcaklığında TUTULAMAZ ve çözülmüş denge marştır
        (ölçülen örnekte cidar 2871,9 K'ye kaçıyor — marş bunu kendi
        uyarılarıyla beyan eder). Bekçi: tests/test_scofield_sivi.py.
        """
        q_design_mw = float(cooling.get('peak_heat_flux', 0.0)) / 1000.0
        q_solved_mw = float(summary['peak_heat_flux_MW_m2'])
        mdot_c = float(cooling.get('coolant_flow_rate', 0.0))
        inlet_K = float(cooling.get('coolant_inlet_temperature',
                                    COOLANT_INLET_TEMP_DEFAULT_K))
        t_hot, t_cold = self._wall_temperatures()
        bulk = {
            'peak_heat_flux_MW_m2': q_design_mw,
            'coolant_exit_temperature_K':
                cooling.get('coolant_exit_temperature'),
            'temperature_rise_K':
                cooling.get('coolant_temperature_rise', 0.0),
            'pressure_drop_bar': cooling.get('cooling_pressure_drop', 0.0),
            'total_heat_to_coolant_kW':
                cooling.get('heat_load_to_regen_coolant', 0.0),
            'wall_temperature_assumed_K': t_hot,
            'wall_temperature_source':
                cooling.get('wall_temperature_source'),
        }
        march_row = {
            'peak_heat_flux_MW_m2': q_solved_mw,
            'coolant_exit_temperature_K': summary['coolant_exit_temp_K'],
            'temperature_rise_K': summary['coolant_dT_K'],
            'pressure_drop_bar': summary['total_pressure_drop_bar'],
            'total_heat_to_coolant_kW': summary['total_heat_kW'],
            'peak_wall_temperature_K': summary['max_wall_hot_K'],
        }
        # Marşın kendi enerji dengesi — ÖLÇÜM, varsayım değil.
        march_lhs_kw = (mdot_c * float(summary['coolant_cp_mean_J_kgK'])
                        * float(summary['coolant_dT_K']) / 1000.0)
        march_rhs_kw = float(summary['total_heat_kW'])
        # Tasarım-cidar akısını kanal filmi taşıyabilir mi? (h_c marştan)
        h_c_list = march.get('h_coolant_W_m2K') or []
        h_c_max = max((float(h) for h in h_c_list), default=0.0)
        film_dt_required = (q_design_mw * 1e6 / h_c_max
                            if h_c_max > 0 else None)
        film_dt_available = max(float(t_cold) - inlet_K, 0.0)
        supportable = (film_dt_required is not None
                       and film_dt_required <= film_dt_available)
        return {
            '_basis': (
                'the two rows are NOT the same quantity: bulk_chain '
                'evaluates the Bartz gas side AT the design wall '
                'temperature and sizes the coolant temperature rise from '
                'that load (a requirement); station_march SOLVES the '
                'coupled gas/wall/coolant balance of the as-built channels '
                '(an equilibrium). Each closes its own energy balance '
                'mdot*cp*dT = integral q dA (bulk chain by construction; '
                'the march closure is measured in march_energy_balance).'),
            'bulk_chain': bulk,
            'station_march': march_row,
            'peak_flux_ratio_bulk_over_march': (
                q_design_mw / q_solved_mw if q_solved_mw > 0 else None),
            'exit_temperature_difference_K': (
                float(bulk['coolant_exit_temperature_K'])
                - float(march_row['coolant_exit_temperature_K'])
                if bulk['coolant_exit_temperature_K'] is not None else None),
            'march_energy_balance': {
                'mdot_cp_dT_kW': march_lhs_kw,
                'integral_q_dA_kW': march_rhs_kw,
                'relative_gap': (abs(march_lhs_kw - march_rhs_kw)
                                 / march_rhs_kw if march_rhs_kw > 0
                                 else None),
            },
            'design_flux_film_dt_required_K': film_dt_required,
            'design_film_dt_available_K': film_dt_available,
            'design_flux_supportable_by_channels': supportable,
            'verdict': (
                'the as-built channels CAN hold the wall near its design '
                'temperature; the two rows should agree closely'
                if supportable else
                'the design-wall heat flux CANNOT be carried by the '
                'as-built coolant channels (the required coolant film '
                'temperature difference exceeds what the design wall '
                'allows), so the wall does not stay at its design '
                'temperature and the physically consistent state of this '
                'circuit is the station_march equilibrium — see '
                'station_march.peak_wall_temperature_K and its warnings'),
        }

    def _passive_thermal_protection(self, cooling):
        """Pasif ısıl koruma — hrma.analysis.thermal_protection (yol har. A5).

        KAPSAM AYRIMI (bilinçli, çakıştırma değil)
        ------------------------------------------
        Rejeneratif/film/dump soğutmada cidarı AKTİF bir soğutucu taşır ve
        onu ``regen_cooling`` + Bartz zinciri zaten çözüyor; oraya bir de
        ablasyon çekilmesi eklemek aynı cidar için İKİ ısıl koruma iddiası
        üretirdi. Bu blok yalnız PASİF soğutulan tasarımlarda çalışır:

          * ``ablative``  -> Seviye-1 Q* ablasyon boyutlandırması (astar
            kalınlığı) + çıplak cidar ısı-yutucu sıcaklık geçmişi,
          * ``radiative`` -> ışınım denge cidar sıcaklığı + ısı-yutucu
            geçmişi (ilk saniyelerde denge henüz kurulmamıştır).

        Şema, hibrit motorun ``_thermal_protection_block`` bağlamasıyla
        birebir aynı alan adlarını kullanır (chamber_liner,
        nozzle_entry_liner, wall_temperature_history) — iki motor aynı
        modülü iki ayrı isimle raporlamaz.

        GİRDİLER MOTORUN KENDİ ZİNCİRİNDEN: Bartz kamara/boğaz tasarım
        akıları ve sıcak cidar sıcaklığı ``calculate_cooling_requirements``
        sonucundan, yanma süresi ``_burn_time``dan, cidar kalınlığı/malzemesi
        yapısal tasarımdan. Girdi eksikse blok SAYI İÇERMEZ.
        """
        basis = (
            'passive thermal protection from hrma/analysis/'
            'thermal_protection.py: Level-1 Q* ablation sizing (NASA '
            'SP-8093-class band; Sutton & Biblarz 9th ed. Ch. 8.5), a 1-D '
            'explicit-FD bare-wall heat-sink history (Incropera & DeWitt 6th '
            'ed. Sec. 5.10) and, for a radiatively cooled wall, the '
            'radiation equilibrium balance (Sutton & Biblarz Ch. 8.6). All '
            "driving inputs are THIS run's values: the Bartz chamber and "
            'throat design fluxes, the hot-wall design temperature, the burn '
            'time and the structural wall thickness/material.')
        # ÖH defter P3B4-09 (Z5S/PK1): kapı "not in ('ablative','radiative')"
        # olduğu için TANINMAYAN her dize "cidar aktif soğutuluyor, ısıl
        # koruma çözümü budur" hükmünü alıyordu. ÖLÇÜLDÜ (10 kN / Pc=100):
        # cooling_type='banana' -> NOT_APPLICABLE + "the wall is actively
        # cooled ('banana')", cooling_channels = 0, coolant_velocity = 0,0 —
        # yani SOĞUTMASIZ bir cidar için soğutma hükmü. 'none' ve '' aynı.
        # Kapı artık TANINAN kümelere bakar; tanınmayan değer kendi
        # gerekçesiyle NOT_MODELLED olur ve hiçbir soğutma iddiası taşımaz.
        if self.cooling_type not in COOLING_TYPES_PASSIVE:
            if self.cooling_type in COOLING_TYPES_ACTIVE:
                return {
                    'passive_thermal_protection': {
                        'status': 'NOT_APPLICABLE',
                        '_basis': basis,
                        'cooling_type_recognised': True,
                        'reason': (
                            'the wall is actively cooled '
                            f"('{self.cooling_type}'): "
                            'the Bartz + channel-hydraulics chain above (and '
                            'the regen_cooling station march where it '
                            'applies) IS the thermal protection solution for '
                            'this design. Adding an ablation or heat-sink '
                            'sizing on the same wall would put two competing '
                            'thermal protection claims in one answer.'),
                    },
                }
            return {
                'passive_thermal_protection': {
                    'status': 'NOT_MODELLED',
                    '_basis': basis,
                    'cooling_type_recognised': False,
                    'cooling_type_supplied': str(self.cooling_type),
                    'cooling_type_options': list(COOLING_TYPES_RECOGNISED),
                    'reason': (
                        f"cooling type '{self.cooling_type}' is not one of "
                        'the cooling schemes HRMA models '
                        f'({", ".join(COOLING_TYPES_RECOGNISED)}), so no '
                        'thermal protection verdict is issued for this wall. '
                        'In particular NO active-cooling verdict is issued: '
                        'an unrecognised scheme sizes no cooling channels '
                        'and carries no coolant, so declaring the chain '
                        'above to be the thermal protection solution for '
                        'this wall would be a claim with nothing behind it. '
                        'Pick one of the modelled schemes, or read the '
                        'unrecognised-option warning in input_warnings.'),
                },
            }

        q_chamber_kw = cooling.get('chamber_heat_flux')     # kW/m^2
        q_throat_kw = cooling.get('peak_heat_flux')         # kW/m^2
        t_hot = cooling.get('wall_temperature_hot')         # K
        burn_time, burn_time_source = self._burn_time()
        eksik = [ad for ad, deger in (
            ('chamber_heat_flux', q_chamber_kw),
            ('peak_heat_flux', q_throat_kw),
            ('wall_temperature_hot', t_hot)) if not (
                deger is not None and np.isfinite(float(deger))
                and float(deger) > 0)]
        if eksik or not burn_time or burn_time <= 0:
            return {
                'passive_thermal_protection': {
                    'status': 'NOT_MODELLED',
                    '_basis': basis,
                    'reason': (
                        'the passive thermal protection sizing needs the '
                        'Bartz heat fluxes, the hot-wall temperature and a '
                        'positive burn time; missing or non-physical in this '
                        'run: ' + ', '.join(eksik + (
                            [] if burn_time and burn_time > 0
                            else ['burn_time']))),
                },
            }
        q_chamber = float(q_chamber_kw) * 1000.0            # W/m^2
        q_throat = float(q_throat_kw) * 1000.0              # W/m^2
        t_hot = float(t_hot)
        t_c = float(self.T_c)
        try:
            from hrma.analysis.thermal_protection import (
                ThermalProtectionAnalyzer)
            analyzer = ThermalProtectionAnalyzer()
        except Exception as exc:                           # pragma: no cover
            return {'passive_thermal_protection': {
                'status': 'NOT_MODELLED', '_basis': basis,
                'reason': f'thermal protection module unavailable: {exc}'}}

        material, mat_key = self._material_record()
        out = {
            'status': 'modelled',
            '_basis': basis,
            'cooling_type': self.cooling_type,
            'burn_time_s': float(burn_time),
            'burn_time_source': burn_time_source,
        }

        # --- İSTASYON GİRDİLERİ: gaz tarafı katsayısı + yarıçap ------------
        # (v2.6.27 ablasyon teşhisi) Astar artık ÇAĞIRANIN AKISIYLA değil,
        # yüzey ENERJİ DENGESİYLE boyutlandırılır ve bunun için iki girdi
        # gerekir: gaz tarafı ısı taşınım katsayısı ve sürücü (recovery)
        # sıcaklık. İKİSİ DE motorun KENDİ Bartz zincirinden gelir; burada
        # ikinci bir Bartz hesabı YAPILMAZ:
        #
        #   * KAMARA h_g: q_kamara/(T_c − T_cidar). Kamara akısı zaten
        #     ``h_g_chamber·(T_c − T_wall_hot)`` olarak kuruluyor
        #     (calculate_cooling_requirements, "q_dot_chamber" satırı), yani
        #     bu bölme Bartz'ın kamara katsayısını CEBİRSEL olarak geri verir
        #     (ölçüldü: geri çözüm ile zincirin kendi değeri arasında fark
        #     yok). AYNI katsayıyı aşağıdaki çıplak cidar ısı-yutucu geçmişi
        #     de kullanır — tek istasyon için iki farklı h_g olamaz.
        #   * BOĞAZ h_g: ``bartz_coefficient`` alanı Bartz korelasyonunun
        #     boğaz katsayısının ta kendisidir (geri çözüme gerek yok;
        #     ölçüldü: peak_heat_flux/(T_c − T_cidar) ile farkı 0,0).
        #   * SÜRÜCÜ SICAKLIK: her iki istasyonda da T_c. Kamarada M~0
        #     olduğu için T_aw ≈ T_c; boğaz/yakınsak istasyonda da zincirin
        #     KENDİSİ T_c kullanıyor (peak_heat_flux = h_g_throat·(T_c −
        #     T_wall_hot) ve lüle integralinde boğaz öncesi T_local = T_c
        #     olduğundan T_aw_local = T_c). Beslenen akıyla enerji dengesi
        #     böylece AYNI sürücü sıcaklığı üzerinde durur.
        #   * YARIÇAP: geometrik kapı için — astar, astarladığı geçitten
        #     kalın olamaz. Kamara için hazne iç yarıçapı (soğutma sonucunun
        #     kendi chamber_diameter'ı), boğaz için Bartz'ın kullandığı
        #     boğaz çapının yarısı. İkisi de bu koşunun çözülmüş ölçüleri.
        #
        # Girdi ELDE EDİLEMEZSE eski yola düşülür (parametreler hiç
        # geçilmez): çekirdek h_gas/T_recovery çiftini YARIM kabul etmez,
        # yalnız biri verilirse ValueError yükseltir.
        def _pozitif(deger, olcek=1.0):
            """Sonlu ve pozitifse ölçeklenmiş float, değilse None."""
            try:
                v = float(deger)
            except (TypeError, ValueError):
                return None
            return v * olcek if np.isfinite(v) and v > 0 else None

        h_eff = _pozitif(q_chamber / (t_c - t_hot)) if t_c - t_hot > 0 else None
        h_throat = _pozitif(cooling.get('bartz_coefficient'))
        r_chamber = _pozitif(cooling.get('chamber_diameter'), 1.0 / 2000.0)
        r_throat = _pozitif(getattr(self, 'd_t', None), 0.5)
        # v2.6.27 blokaj denetimi: kenar gazı c_p'si, Bartz katsayılarını
        # üreten zincirin KENDİ değeridir (calculate_cooling_requirements
        # "cp_g = self.cp_chamber" satırı) — B'yi bölen c_p ile h_g'yi
        # üreten c_p aynı olmak zorunda. Yoksa çekirdek psi = 1 (blokajsız,
        # konservatif) kullanır ve blockage_basis'te beyan eder.
        cp_gaz = _pozitif(getattr(self, 'cp_chamber', None))

        def _liner(station, function, q_w_m2, station_note,
                   h_gas, h_gas_source, radius_m, radius_source):
            """Tek istasyon astar boyutu — hibrit/katı ile AYNI alan adları.

            ``h_gas`` verilirse çekirdek yüzey enerji dengesini ÇÖZER ve
            geçerlilik kapısı bağlayıcıdır; verilmezse eski (çağıranın
            akısı) yolu birebir korunur.
            """
            ek = {}
            if h_gas is not None:
                # Çift HALİNDE geçilir: yarım geçiş çekirdekte ValueError.
                ek['h_gas_W_m2K'] = h_gas
                ek['T_recovery_K'] = t_c
                if cp_gaz is not None:
                    ek['gas_cp_J_kgK'] = cp_gaz
            if radius_m is not None:
                ek['station_radius_m'] = radius_m
            try:
                sizing = analyzer.ablative_thickness(
                    q_net_W_m2=q_w_m2,
                    burn_time_s=float(burn_time),
                    material=TPS_LINER_MATERIAL_DEFAULT,
                    **ek)
            except Exception as exc:
                return {
                    'material': TPS_LINER_MATERIAL_DEFAULT,
                    'thickness': None,
                    'thickness_status': 'NOT_MODELLED',
                    'function': function,
                    'basis': f'Ablative sizing failed at the {station}: {exc}',
                }
            enerji_dengesi = (
                sizing['flux_basis'] == 'surface_energy_balance')
            kalinlik_mm = sizing['required_thickness_mm']
            # Çekirdeğin hükmü AYNEN taşınır: kapı kalınlığı kesmişse burada
            # 'sized'a çevrilmez ve sayı uydurulmaz (katı motorun kapak
            # yalıtımıyla aynı NOT_MODELLED sözleşmesi).
            if kalinlik_mm is None:
                # Kalınlık YALNIZ enerji dengesi yolunda kesilebilir, yani
                # burada h_gas her zaman doludur; yarıçap ise olmayabilir
                # (kapı o zaman hız tavanından düşmüştür).
                yaricap_ifadesi = (
                    'no station radius was available, so only the recession '
                    'rate ceiling was checked' if radius_m is None else
                    f'station radius {radius_m * 1e3:.1f} mm '
                    f'({radius_source})')
                basis = (
                    f'Level-1 Q* ablation sizing was RUN at the {station} '
                    f'but published NO thickness. '
                    f"{sizing['validity_note']} "
                    f'Inputs are this run\'s solver values: gas-side '
                    f'coefficient {h_gas:.0f} W/m2K ({h_gas_source}), '
                    f'recovery temperature {t_c:.0f} K (the same driving '
                    f'temperature the Bartz flux of this station uses), '
                    f'burn time {float(burn_time):.2f} s, '
                    f'{yaricap_ifadesi}. ' + station_note)
            else:
                basis = (
                    f'Level-1 Q* ablation sizing at the {station}: required '
                    f'thickness = total recession x design margin '
                    f"{sizing['design_margin']:g}. "
                    + ((
                        f'The net surface flux is SOLVED here from an energy '
                        f'balance at the {sizing["T_surface_K"]:.0f} K steady '
                        f'ablation temperature (blowing blockage '
                        f'{sizing["blowing_blockage"]:g} x convection minus '
                        f're-radiation at emissivity '
                        f'{sizing["emissivity"]:g}), driven by this run\'s '
                        f'gas-side coefficient {h_gas:.0f} W/m2K '
                        f'({h_gas_source}) and recovery temperature '
                        f'{t_c:.0f} K. The cold-wall Bartz design flux '
                        f'({q_w_m2 / 1e3:.0f} kW/m2) is reported for '
                        f'COMPARISON only, it is not what sized this liner. ')
                       if enerji_dengesi else (
                        f'Heat flux ({q_w_m2 / 1e3:.0f} kW/m2) is this run\'s '
                        f'solver value and is used AS GIVEN: no surface '
                        f'energy balance was solved for this station. '))
                    + f'Burn time ({float(burn_time):.2f} s) is this run\'s '
                    f"solved value. Liner material "
                    f"'{TPS_LINER_MATERIAL_DEFAULT}' is a declared design "
                    f'choice, not a solved selection. ' + station_note)
            return {
                'material': sizing['material_name'],
                'thickness': (None if kalinlik_mm is None
                              else float(kalinlik_mm)),           # mm
                'thickness_status': sizing['thickness_status'],
                'function': function,
                'total_recession_mm': float(sizing['total_recession_mm']),
                'recession_rate_mm_s': float(sizing['recession_rate_mm_s']),
                'design_margin': float(sizing['design_margin']),
                'q_star_mj_kg': float(sizing['q_star_MJ_kg']),
                # Çağıranın (Bartz, soğuk cidar) akısı — YENİ yolda artık
                # boyutlandıran değer DEĞİL, karşılaştırma değeridir.
                'heat_flux_kw_m2': q_w_m2 / 1e3,
                'burn_time_s': float(burn_time),
                # --- v2.6.27: akı tabanı ve enerji dengesi dökümü ---
                'flux_basis': sizing['flux_basis'],
                'recession_regime': sizing['recession_regime'],
                'q_net_kw_m2': float(sizing['q_mean_W_m2']) / 1e3,
                'q_conv_blocked_kw_m2': (
                    None if sizing['q_conv_blocked_W_m2'] is None
                    else float(sizing['q_conv_blocked_W_m2']) / 1e3),
                'q_reradiated_kw_m2': (
                    None if sizing['q_reradiated_W_m2'] is None
                    else float(sizing['q_reradiated_W_m2']) / 1e3),
                'h_gas_W_m2K': sizing['h_gas_W_m2K'],
                'h_gas_source': h_gas_source if h_gas is not None else None,
                'T_recovery_K': sizing['T_recovery_K'],
                'T_surface_K': sizing['T_surface_K'],
                'emissivity': sizing['emissivity'],
                'emissivity_source': sizing['emissivity_source'],
                # v2.6.27 blokaj denetimi: psi artık sabit değil, B'den
                # çözülür; c_p bu bağlamada henüz geçilmediği için çekirdek
                # psi = 1 (blokajsız, konservatif) kullanır ve bunu
                # blockage_basis'te beyan eder.
                'blowing_blockage': sizing['blowing_blockage'],
                'b_prime': sizing['b_prime'],
                'blowing_lambda': sizing['blowing_lambda'],
                'blowing_gas_fraction': sizing['blowing_gas_fraction'],
                'blockage_basis': sizing['blockage_basis'],
                # --- v2.6.27: geçerlilik kapısı (çekirdeğin hükmü) ---
                'station_radius_m': sizing['station_radius_m'],
                'station_radius_source': (None if radius_m is None
                                          else radius_source),
                'model_valid': bool(sizing['model_valid']),
                'validity_note': sizing['validity_note'],
                'basis': basis,
                'model_note': sizing['model_note'],
                'source': sizing['source'],
                'surface_source': sizing['surface_source'],
            }

        if self.cooling_type == 'ablative':
            out['chamber_liner'] = _liner(
                'combustion chamber wall',
                'Protect the chamber wall, which sees combustion gas '
                'directly for the whole burn',
                q_chamber,
                'Flux is the Bartz CHAMBER-station design flux of this run.',
                h_eff,
                'Bartz chamber coefficient of this run, recovered from the '
                'chamber design flux: h_g = q_chamber/(T_c - T_wall_hot)',
                r_chamber,
                'chamber inner radius solved by this run (L* and contraction '
                'ratio chain)')
            out['nozzle_entry_liner'] = _liner(
                'throat / nozzle entry',
                'Protect the convergent entry and the throat, the highest '
                'flux station of the engine',
                q_throat,
                'Flux is the Bartz THROAT design flux, so the same thickness '
                'is a conservative UPPER bound for the convergent section '
                '(the same declaration the solid and hybrid engines make).',
                h_throat,
                "Bartz throat coefficient of this run "
                "(cooling result 'bartz_coefficient')",
                r_throat,
                'throat radius solved by this run (the same D_t the Bartz '
                'correlation is evaluated at)')

        # --- Çıplak (korumasız) cidar ısı-yutucu geçmişi ------------------
        # Sürücü katsayı motorun KENDİ kamara tasarım akısından geri çözülür:
        # h_eff = q_kamara/(T_c − T_cidar). Bu, Bartz zincirinin kamara
        # istasyonundaki h_g'sinin ta kendisidir (q = h_g·(T_aw − T_w) ve
        # haznede T_aw ≈ T_c); ikinci bir Bartz hesabı YAPILMAZ.
        if t_c - t_hot <= 0:
            out['wall_temperature_history'] = {
                'status': 'NOT_MODELLED',
                'reason': ('the chamber temperature does not exceed the '
                           'hot-wall design temperature; there is no '
                           'positive driving potential to reconstruct the '
                           'gas-side coefficient from.'),
            }
            h_eff = None
        else:
            h_eff = q_chamber / (t_c - t_hot)
            try:
                hs = analyzer.heat_sink_transient(
                    h_gas_W_m2K=h_eff,
                    T_recovery_K=t_c,
                    burn_time_s=float(burn_time),
                    wall_thickness_m=self._chamber_wall_thickness_m(),
                    wall_material=mat_key,
                    store_history=True)
            except Exception as exc:
                out['wall_temperature_history'] = {
                    'status': 'NOT_MODELLED',
                    'reason': f'heat-sink transient could not run: {exc}'}
            else:
                hist = hs.get('history') or {}
                t_list = list(hist.get('t_s') or [])
                tw_list = list(hist.get('T_inner_K') or [])
                idx = []
                if t_list:
                    stride = max(1, len(t_list) // TPS_WALL_HISTORY_MAX_POINTS)
                    idx = list(range(0, len(t_list), stride))
                    if idx[-1] != len(t_list) - 1:
                        idx.append(len(t_list) - 1)
                out['wall_temperature_history'] = {
                    'status': 'modelled',
                    'wall_material': hs['wall_material'],
                    'material_name': hs['material_name'],
                    'wall_thickness_m': hs['wall_thickness_m'],
                    'h_eff_W_m2K': float(h_eff),
                    'h_eff_basis': (
                        'effective gas-side coefficient recovered from the '
                        'cooling solution of this run: h_eff = chamber '
                        'design flux / (T_c - T_wall_hot). In the chamber '
                        'the recovery temperature is the chamber '
                        'temperature (M ~ 0), so this IS the Bartz chamber '
                        'coefficient - no second Bartz evaluation is made.'),
                    'T_recovery_K': hs['T_recovery_K'],
                    'T_initial_K': hs['T_initial_K'],
                    'time_s': [float(t_list[i]) for i in idx],
                    'wall_inner_temperature_K': [float(tw_list[i])
                                                 for i in idx],
                    'T_inner_final_K': hs['T_inner_K'],
                    'T_outer_final_K': hs['T_outer_K'],
                    'max_service_temp_K': hs['max_service_temp_K'],
                    'exceeds_limit': hs['exceeds_limit'],
                    'time_to_limit_s': hs['time_to_limit_s'],
                    'melting_point_K': hs['melting_point_K'],
                    'exceeds_melting': hs['exceeds_melting'],
                    'time_to_melting_s': hs['time_to_melting_s'],
                    'model_valid': hs['model_valid'],
                    'validity_note': hs['validity_note'],
                    'model_note': hs['model_note'],
                    'basis': (
                        'UNPROTECTED (bare) structural wall heat-sink '
                        'history: no liner credit, gas side directly on the '
                        'wall. For the ablative design it bounds the '
                        'no-liner case and shows why the liner sized above '
                        'is needed; for the radiative design it shows the '
                        'transient before the radiation equilibrium below '
                        'is reached. Liner ablation and wall conduction are '
                        'NOT coupled.'),
                }

        if self.cooling_type == 'radiative':
            if h_eff is None:
                out['radiation_equilibrium'] = {
                    'status': 'NOT_MODELLED',
                    'reason': ('the gas-side coefficient could not be '
                               'recovered (see wall_temperature_history), so '
                               'the radiation balance has no driving '
                               'coefficient.'),
                }
            else:
                try:
                    rad = analyzer.radiation_equilibrium(
                        h_gas_W_m2K=h_eff,
                        T_recovery_K=t_c,
                        material=mat_key)
                except Exception as exc:
                    out['radiation_equilibrium'] = {
                        'status': 'NOT_MODELLED',
                        'reason': ('radiation equilibrium could not be '
                                   f'solved: {exc}')}
                else:
                    rad = dict(rad)
                    rad['status'] = 'modelled'
                    rad['station'] = 'chamber'
                    rad['basis'] = (
                        'steady radiation balance h_g*(T_recovery - T_w) = '
                        'F*eps*sigma*T_w^4 at the CHAMBER station, with the '
                        'gas-side coefficient recovered from this run\'s '
                        'Bartz chamber flux. View factor 1 and zero incident '
                        'gas radiation are the module defaults: HRMA models '
                        'neither the extension half-angle nor a Leckner gas '
                        'radiation flux for the liquid engine, and the '
                        'module declares that this makes the wall '
                        'temperature UNCONSERVATIVE (see the '
                        'unconservative flag).')
                    out['radiation_equilibrium'] = rad
        # B4 (v2.6.27) DÜZELTMESİ — blok KENDİ adresinde yayımlanır.
        # ÖLÇÜLDÜ (11 Ağustos 2026): bu dal ``out``u ÇIPLAK döndürüyordu ve
        # çağıran ``result.update(...)`` ile onu ısıl koruma sözlüğünün
        # köküne serpiyordu. Üç sonucu vardı:
        #   1. Rejeneratifte ``passive_thermal_protection`` (NOT_APPLICABLE)
        #      varken, sizing'in GERÇEKTEN yapıldığı ablatif/radyatif koşuda
        #      o adres HİÇ yoktu — arayan tam da bulması gereken yerde
        #      bulamıyordu.
        #   2. ``cooling_type`` eziliyordu: sunum değeri 'Ablative' yerine
        #      ham 'ablative' yazılıyordu.
        #   3. Astar boyutlandırmasına ait ``status: modelled`` ve ``_basis``
        #      ısıl koruma bloğunun KÖKÜNE çıkıyordu; oradaki bir hüküm
        #      soğutma çözümünün tamamına aitmiş gibi okunurdu.
        # Diğer iki dal (NOT_APPLICABLE / NOT_MODELLED) zaten sarmalıydı;
        # doğru sözleşme onlarınkidir.
        return {'passive_thermal_protection': out}

    def _analyze_manufacturing_requirements(self, cooling=None, injector=None):
        """İmalat gereksinimleri — yalnız türetilmiş ya da etiketli bilgi.

        2026-07-28 dürüstlük denetimi (LIQ-MFG-4): bu fonksiyon dört sözlüğün
        tamamını literal döndürüyordu ve sonuç arayüzde (liquid.html imalat
        kartı) kullanıcıya gösteriliyordu — 10 N'lik itici de 2 MN'lik motor
        da aynı '$2M - $5M' geliştirme maliyetini ve aynı '18 months' tasarım
        süresini görüyordu. Maliyet ve termin için elimizde tedarikçi fiyatı,
        işçilik ücreti ya da program verisi YOK; ölçeklenen bir korelasyon
        uydurmak yerine alanlar KALDIRILDI (yokluğu MANUFACTURING_COST_STATUS
        ile açıkça raporlanır).

        Kalan iki alan gerçeğe bağlandı: üretim rotası motorun soğutma /
        enjektör / besleme seçimine göre seçilir (nitel, etiketli), toleranslar
        ise motorun HESAPLANMIŞ nominal ölçüsünden ISO 2768-1 tablosuyla
        aranır. Tolerans bir tasarım dağıtımı değildir, öyle etiketlenir.

        cooling/injector: çağıran zaten hesapladıysa geçirir (tekrar hesap
        yok); geçirmezse burada üretilir.
        """
        # ÖH D25 · OH-D24-13: çözülemeyen girdi yüzünden karttan DÜŞEN
        # kalemlerin listesi. Boşsa kart eksiksizdir.
        _withheld = []
        if cooling is None:
            # ÖH D25 · OH-D24-13: kapı hatası yutulmaz (aşağıdaki enjektör
            # dalıyla aynı gerekçe).
            try:
                cooling = self.calculate_cooling_requirements()
            except (UnsupportedPropellantPairError,
                    UnsupportedPropellantDensityError):
                raise
            except Exception as exc:
                cooling = {}
                _withheld.append(f'cooling ({type(exc).__name__})')
        if injector is None:
            # ÖH D25 · OH-D24-13. ÖLÇÜLDÜ (once.json ``OH-D24-13``,
            # injector_type='banana'): enjektör çözülemeyince ``{}`` konuyor
            # ve kartın kritik tolerans listesinden İKİ KALEM sessizce
            # düşüyordu — beş özellik (throat_diameter, chamber_diameter,
            # cooling_channel_width, fuel_injector_orifice 2,449 mm,
            # oxidizer_injector_orifice 2,494 mm) üçe iniyor, eksildiğini
            # söyleyen tek bir alan bile bulunmuyordu. Kapı hatası yükselir;
            # kapı dışı arızada liste eksilir ama EKSİLDİĞİ yazılır.
            try:
                injector = self.calculate_injector_design()
            except (UnsupportedInjectorTypeError,
                    UnsupportedPropellantPairError,
                    UnsupportedPropellantDensityError):
                raise
            except Exception as exc:
                injector = {}
                _withheld.append(f'injector ({type(exc).__name__})')
        cooling = cooling or {}
        injector = injector or {}

        processes = {
            'chamber': CHAMBER_PROCESS_BY_COOLING.get(
                self.cooling_type, CHAMBER_PROCESS_DEFAULT),
            'nozzle': NOZZLE_PROCESS_BY_COOLING.get(
                self.cooling_type, NOZZLE_PROCESS_DEFAULT),
            'injector': INJECTOR_PROCESS_BY_TYPE.get(
                self.injector_type, INJECTOR_PROCESS_DEFAULT),
            'feed_system': FEED_PROCESS_BY_TYPE.get(
                self.feed_system_type, FEED_PROCESS_DEFAULT),
        }

        d_t = getattr(self, 'd_t', None)
        features = {
            'throat_diameter': _iso2768_feature(
                d_t * 1000.0 if d_t else None, ISO2768_GRADE_PRECISION),
            'fuel_injector_orifice': _iso2768_feature(
                injector.get('fuel_orifice_diameter'),
                ISO2768_GRADE_PRECISION),
            'oxidizer_injector_orifice': _iso2768_feature(
                injector.get('ox_orifice_diameter'), ISO2768_GRADE_PRECISION),
            'chamber_diameter': _iso2768_feature(
                cooling.get('chamber_diameter'), ISO2768_GRADE_GENERAL),
        }
        if cooling.get('cooling_channels'):
            features['cooling_channel_width'] = _iso2768_feature(
                cooling.get('channel_width_mm'), ISO2768_GRADE_PRECISION)
        features = {k: v for k, v in features.items() if v is not None}

        # Boğaz toleransının performans karşılığı: A_t ~ D^2 olduğundan
        # dA/A = 2·dD/D. Boğaz alanı sabit mdot'ta doğrudan Pc'yi, sabit Pc'de
        # doğrudan itkiyi ölçekler; tolerans bandı bu yüzden anlamlı.
        throat = features.get('throat_diameter')
        if throat and throat.get('tolerance_mm'):
            throat['throat_area_variation_percent'] = round(
                200.0 * throat['tolerance_mm'] / throat['nominal_mm'], 2)

        return {
            'manufacturing_processes': processes,
            'manufacturing_processes_basis': MANUFACTURING_ROUTE_BASIS,
            'critical_tolerances': {
                'basis': ISO2768_TOLERANCE_BASIS,
                'features': features,
                # ÖH D25 · OH-D24-13: liste sessizce eksilmez. Boş liste =
                # hiçbir kalem çözülemediği için düşmedi.
                'withheld_inputs': list(_withheld),
                'withheld_inputs_basis': (
                    'the analyses named here could not be solved, so every '
                    'tolerance feature that depends on them is ABSENT from '
                    'this list rather than replaced by a substitute nominal'
                    if _withheld else
                    'no input analysis was withheld: the feature list is '
                    'complete for this engine'),
            },
            'cost_and_schedule_status': MANUFACTURING_COST_STATUS,
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
        # Kontrol/aviyonik kütlesi SABİT BİR PAYDIR ve öyle etiketlenir.
        # v2.6.26 beyan düzeltmesi: 'mass_method' bu kalemi besleme hattıyla
        # birlikte "empirical scaling with mass flow" diye bildiriyordu, oysa
        # değer hiçbir girdiyle değişmiyordu (15.0 kg). Vana/aktüatör kütlesi
        # zaten FEED_LINE_MASS_PER_KG_S içindedir (hat + vana); burada kalan
        # aviyonik kutusu, kablo demeti ve sensör payı ölçeklenmez.
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
                'feed_system': (
                    f'empirical scaling with mass flow '
                    f'({FEED_LINE_MASS_PER_KG_S:g} kg per kg/s, lines and '
                    f'valves) - estimate'),
                'controls_avionics': (
                    f'FIXED allowance of {CONTROLS_MASS_BASE_KG:g} kg '
                    '(avionics box, harness, sensors); NOT scaled with the '
                    'engine - valve/actuator mass is already inside the feed '
                    'system item'),
            },
            'component_dimensions': {
                'overall_length': l_chamber + l_conv + l_nozzle,  # m
                'maximum_diameter': d_c * 1000,  # mm
                'nozzle_length': l_nozzle * 1000,  # mm
                # P3B2-02: TEK KAYNAK — hazne hacmi (konverjan koni dâhil)
                # _chamber_volume_split'ten gelir; L*·A_t kopyası, taban L*
                # yükseltildiğinde çizilen gövdeden sapıyordu.
                'chamber_volume': self._chamber_volume_split()[0] * 1e6  # cm³
            },
            'mass_ratios': {
                'thrust_to_weight': self.F / (total_dry_mass * G_0),
                'power_to_weight': (pump_power_kw / total_dry_mass
                                    if total_dry_mass > 0 else 0.0),  # kW/kg
                'chamber_loading': self.F / chamber_mass  # N/kg
            }
        }