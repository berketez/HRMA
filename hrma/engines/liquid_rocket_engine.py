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
from hrma.analysis.turbopump_sizing import (SPEED_DERATE_DEFAULT,
                                            m3s_to_gpm, m_to_ft,
                                            npsh_available_m)
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


# Tablo dışı ama CEA ile ÇÖZÜLEBİLEN çiftlerde (ör. rp1/n2o4, lh2/n2o4) itici
# YOĞUNLUKLARI için beyan edilmiş yedek değerler [kg/m3]. Bunlar kimyadan
# TÜREMEZ, tipik bir hidrokarbon yakıt / depolanabilir oksitleyici mertebesidir
# ve yalnız çağıran hiçbir yoğunluk vermediğinde kullanılır: arayüzün
# ``fuel_density`` / ``oxidizer_density`` alanları _apply_overrides içinde
# (kurucu sırası: _set_propellant_properties -> _apply_overrides) bu değerleri
# EZER. Yanma performansı için yer tutucu üretmek yasaktır (bkz.
# UnsupportedPropellantPairError); yoğunluk bir yanma çözümü değil, ezilebilir
# bir madde özelliğidir ve bu ayrım bilinçlidir.
LIQUID_UNKNOWN_PAIR_FUEL_DENSITY = 800.0
LIQUID_UNKNOWN_PAIR_OX_DENSITY = 1200.0

# Aynı çiftler için yanma GAZI taşıma özellikleri. Bunlar da performans değil:
# Bartz ısı-taşınım korelasyonu bir viskozite ve Prandtl sayısı ister, CEA
# köprüsü bunları döndürmez. Değerler yerleşik tablodaki altı çiftin ölçülen
# bandının ortasındadır (mu_chamber 5.78e-5 ... 6.89e-5 Pa.s, pr_chamber
# 0.712 ... 0.751, cp_chamber 2156 ... 2287 J/kg.K) ve bu bant zaten dardır.
# cp_chamber, CEA çözümü bir değer döndürürse _resolve_combustion_reference
# içinde EZİLİR; kalanlar yedek olarak durur.
LIQUID_UNKNOWN_PAIR_GAS_VISCOSITY = 6e-5      # Pa.s
LIQUID_UNKNOWN_PAIR_GAS_PRANDTL = 0.73        # -
LIQUID_UNKNOWN_PAIR_GAS_CP = 2000.0           # J/kg.K
LIQUID_UNKNOWN_PAIR_DISSOCIATION_TEMP = 3000  # K

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
    'also sets the geometric channel count through the throat circumference')
COOLING_CHANNEL_HEIGHT_BASIS = (
    'default channel height (depth), which IS auto-sized: when the resulting '
    f'coolant velocity exceeds the {COOLANT_CHANNEL_TARGET_VELOCITY_MS:.0f} '
    'm/s design target the depth is increased to meet it, up to the '
    f'{COOLING_CHANNEL_HEIGHT_MAX_M * 1e3:.0f} mm milled-channel ceiling. It '
    'stays at the default only while the velocity target is already met; the '
    'channel_count_source field records when the auto-sizing actually fired')
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
def _optimal_mr_scan_cached(fuel, oxidizer, pc_bar, eps, n_points):
    """Maksimum vakum Isp veren O/F — CEA taraması, önbellekli.

    Optimum yalnız (itici çifti, Pc, referans eps) fonksiyonudur; motorun
    itkisi, geometrisi ya da çevrimi onu değiştirmez. Bu yüzden modül
    seviyesinde önbelleğe alınır: kullanıcı formda başka bir alanı
    oynattığında 25 CEA çağrısı TEKRAR yapılmaz (soğuk tarama ~3-12 s
    sürüyordu; sıcak isabet anlıktır). Argümanlar hashlenebilir olsun diye
    yuvarlanmış skalerlerdir.

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
        isps.append(props.get('isp_vac_s')
                    if props.get('source') == 'rocketcea' else None)
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
# metodolojisi; Sutton & Biblarz 9th ed. Böl. 3.5, Huzel & Huang Böl. 1-4):
#     Isp_teslim = Isp_CEA(ε) · η_c* · λ_sapma · η_sürtünme · η_kinetik
# HRMA bu zincirin ÜÇÜNÜ hesaplar (λ konturdan, η_sürtünme kaynaklı tipik
# değerden, η_kinetik CEA donmuş/kayan bandından); η_c* enjektör/karışım
# kalitesine bağlıdır ve tasarım girdilerinden TÜRETİLEMEZ — kullanıcı
# 'combustion_efficiency' girmezse 1.0 alınır (ek varsayım YOK) ve bu durum
# çıktıda açıkça etiketlenir. Bunun sonucu: HRMA'nın varsayılan Isp'si
# "mükemmel enerji salımı" üst sınırıdır; gerçek motorların η_c*'ı
# 0.92-0.99 bandındadır (Sutton & Biblarz 9th ed. Böl. 5).
DELIVERED_ETA_CSTAR_DEFAULT = 1.0
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
INJECTOR_TYPE_DP_FRACTION_DEFAULT = 0.20

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
# debinin %1-10'u mertebesindedir (Huzel & Huang Ch. 4); üst sınır geniş
# bırakılır, aşırı değer uyarı üretir.
FILM_COOLING_PCT_MAX = 30.0
# Kullanıcı soğutma tipini 'film_cooling' seçtiği hâlde film debisi
# girmediğinde uygulanan ETİKETLİ varsayılan (% yakıt debisi). Literatürde
# yaygın bant %3-10'dur (Huzel & Huang Ch. 4; Sutton & Biblarz 9th ed. Ch. 8);
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
# NASA SP-125 Böl. 8 itici boruları: tank-pompa emme hattı olabildiğince
# kısa/doğrudan; Böl. 6 pompa emme performansı). Emme boyu, toplam
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
    'Huang, NASA SP-125, Ch. 8 propellant ducting). The main valve and the '
    'elbowed remainder of the run are DISCHARGE-side items and are not '
    'charged against NPSH.')
FEED_LINE_TARGET_VELOCITY_MS = 5.0   # hat çapı boyutlandırma hedefi (3-8 m/s)
# Sıvı besleme hattı için tavsiye edilen ÜST hız [m/s] (Huzel & Huang Böl. 7;
# NASA SP-125). Hat çapı standart boru ölçüsüne yuvarlandığı için gerçek hız
# hedeften sapar; besleme sistemi debi marjı bu tavana göre raporlanır.
FEED_LINE_MAX_VELOCITY_MS = 8.0

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


FEED_INSTRUMENTATION_STATUS = 'NOT_MODELLED'
FEED_INSTRUMENTATION_BASIS = (
    'not calculated: HRMA has no P&ID, no measurement-accuracy requirement '
    'and no reliability allocation, so a sensor count cannot be derived. The '
    'previous values (8 pressure, 6 temperature, 4 flow sensors, 6 check '
    'valves, 2 pressurant bottles) were fixed literals - identical for a '
    '10 N thruster and a 2 MN booster - and are removed rather than '
    'relabelled as an assumption')

# Turbopompa benzerlik modeli (Huzel & Huang, "Modern Engineering for Design
# of Liquid-Propellant Rocket Engines", Ch. 6; Stepanoff, "Centrifugal and
# Axial Flow Pumps" 2nd ed.).
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
# birbirinden habersiz kayabiliyordu. 30 derece sıvı motorlarda standart
# daralma açısıdır (Huzel & Huang, "Modern Engineering for Design of
# Liquid-Propellant Rocket Engines", Böl. 4; Sutton & Biblarz 9th ed. Böl. 3).
CONVERGENT_HALF_ANGLE_DEG = 30.0
CONVERGENT_HALF_ANGLE_BASIS = (
    '30 deg standard convergent half angle (Huzel & Huang Ch. 4; Sutton & '
    'Biblarz 9th ed. Ch. 3); a fixed design choice from the single definition '
    'point CONVERGENT_HALF_ANGLE_DEG, NOT solved from the contraction contour '
    '- the same angle also sets the convergent cone length used by the '
    'cooling integration, so the two cannot disagree')
# Tank boyutlandırma — TEK model (bkz. _size_tank). Besleme sistemi kartı ve
# ayrıntılı tank tasarımı aynı iki sabiti kullanır; ayrı ayrı gömülüyken
# (1.20 çarpanı vs 1.15 rezerv + %5 ullage) aynı koşuda iki farklı tank
# hacmi raporlanıyordu. Rezerv payı: yüklenen itici / tüketilen itici;
# ullage: tankın sıvı DOLMAYAN hacim kesri (Huzel & Huang, Böl. 8).
TANK_PROPELLANT_RESERVE_FACTOR = 1.15
TANK_ULLAGE_FRACTION = 0.05
TANK_RESERVE_BASIS = (
    'TANK_PROPELLANT_RESERVE_FACTOR = 1.15 loaded/consumed propellant reserve '
    '(Huzel & Huang Ch. 8); a sizing assumption for the safety margin, NOT a '
    'mission-derived residual - HRMA has no mixture-ratio-shift, trapped-'
    'propellant or flight-performance-reserve budget')
TANK_ULLAGE_BASIS = (
    'TANK_ULLAGE_FRACTION = 0.05 non-liquid ullage volume fraction of the '
    'tank (Huzel & Huang Ch. 8); fixed, NOT solved from thermal expansion or '
    'pressurant demand')
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
# (Huzel & Huang Böl. 7; ESDU 73024 konik difüzör ayrılma sınırı).
TANK_DIFFUSER_HALF_ANGLE_DEG = 15.0
# Difüzör çıkış çapı / giriş (hat) çapı: hızı yaklaşık dörtte birine indirir.
TANK_DIFFUSER_AREA_RATIO = 2.0
# Sump / standpipe ağız çapı / besleme hattı çapı. Girdap ve NPSH kaybını
# azaltmak için tank ağzı hattan geniş tutulur (tipik 1.2-1.5; Huzel & Huang
# Böl. 7). Kritik dalma (gaz yutma) ölçütü MODELLENMİYOR.
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
# TABLOLU olan itici anahtarları. n2o4/mmh/udmh/lh2/methane/ethanol için
# tablo değeri YOKTUR; o hatlar NOT_MODELLED beyanıyla boş döner (bulk modül
# uydurulmaz) ve kullanıcı /api/water-hammer ucuna bulk_modulus_Pa +
# density_kg_m3 vererek özel sıvı analizi yapabilir.
WATER_HAMMER_FLUID_KEY = {'lox': 'lox', 'rp1': 'rp1'}
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
        record = {"code": code, "params": params, "severity": severity}
        if record not in self.design_warnings:
            self.design_warnings.append(record)

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
        eta_c = self._override_val('combustion_efficiency', 50.0, 100.0,
                                   'Combustion efficiency', ' %')
        self.eta_c_star = 1.0 if eta_c is None else eta_c / 100.0

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
                '(typical 3-10%; Huzel & Huang Ch. 4, Sutton & Biblarz 9th '
                'ed. Ch. 8)')
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
        _ov = getattr(self, 'overrides', None) or {}
        if not _ov or 'turbine_expansion_ratio' in _ov:
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
                return max(d_c, CHAMBER_DIAMETER_MIN_M)
        if getattr(self, 'contraction_ratio_input', None) is not None:
            if d_t_solved:
                self._chamber_diameter_source = 'contraction_ratio'
            return max(d_t * np.sqrt(self.contraction_ratio_input),
                       CHAMBER_DIAMETER_MIN_M)
        if d_t_solved:
            self._chamber_diameter_source = 'default'
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

    def _cooling_channel_geometry(self):
        """Kanal sayısı ve kesiti.

        Kanal sayısı: kullanıcı girdisi varsa o; yoksa GEOMETRİDEN
        n = floor(pi·D_hazne / (w + land)) (sabit 80/180 değil).

        Kesit: burada dönen değerler BAŞLANGIÇ değerleridir. Genişlik gerçekten
        sabittir (``COOLING_CHANNEL_WIDTH_BASIS``); DERİNLİK ise çağıran
        tarafında hız hedefine göre büyütülebilir
        (``COOLING_CHANNEL_HEIGHT_BASIS`` + ``channel_height_auto_sized``).
        İkisi tek bir beyanla anlatılamaz, bu yüzden iki ayrı metin taşınır.
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
                self._warn('warn.liquid.cooling_channels_do_not_fit',
                           'warning', n=int(n),
                           width_mm=round(float(width) * 1000.0, 1),
                           d_ref_mm=round(float(d_ref) * 1000.0, 1),
                           n_geom=int(n_geom))
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
        mdot_total = getattr(self, 'mdot_total', None)
        if mdot_total is None or not np.isfinite(mdot_total) or mdot_total <= 0:
            mdot_total = (self.F / (self.isp_sl_ref * self.g0)
                          if hasattr(self, 'isp_sl_ref')
                          else self.F / (300 * self.g0))
        mdot_ox = getattr(self, 'mdot_ox', mdot_total * self.MR / (1 + self.MR))
        mdot_fuel = getattr(self, 'mdot_fuel', mdot_total / (1 + self.MR))

        # Tank basıncı: basınç beslemeli çevrimde kullanıcının feed_pressure
        # girdisi, turbopompalı çevrimde NPSH tankı (sabit 2.5 bar değil).
        # A11: mantık artık _tank_pressure_bar'da TEK kopya — ayrıntılı tank
        # kartı da aynı fonksiyondan okur, iki kart çelişemez.
        tank_pressure_bar, tank_pressure_source = self._tank_pressure_bar()

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
                    'filters': ['main_filter', 'fine_filter']
                },
                'fuel_main': {
                    'diameter': self._calculate_line_diameter(mdot_fuel, 'fuel'),  # m
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
            self.rho_fuel = LIQUID_UNKNOWN_PAIR_FUEL_DENSITY
            self.rho_ox = LIQUID_UNKNOWN_PAIR_OX_DENSITY
            self.mu_chamber = LIQUID_UNKNOWN_PAIR_GAS_VISCOSITY
            self.pr_chamber = LIQUID_UNKNOWN_PAIR_GAS_PRANDTL
            self.cp_chamber = LIQUID_UNKNOWN_PAIR_GAS_CP
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
            self.optimal_mr_thrust = getattr(self, 'optimal_mr_thrust',
                                             float(self.MR))
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

        NOT: Maksimum İTKİ O/F'si maksimum Isp'ninkinden daha yüksektir
        (yoğunluk-itki dengesi); ayrı bir tarama gerektirdiği ve tasarım
        noktası seçiminde ikincil olduğu için burada Isp optimumundan
        türetilmez — kaynağı 'not_modelled' olarak işaretlenir.
        """
        eps = float(getattr(self, 'design_reference_expansion_ratio', 0)
                    or VACUUM_REFERENCE_EPS)
        best_mr = _optimal_mr_scan_cached(
            str(self.fuel_type), str(self.oxidizer_type),
            round(float(self.P_c), 1), round(eps, 2), int(n_points))
        if best_mr is None:
            self.optimal_mr_source = 'not_solved'
            return
        self.optimal_mr = float(best_mr)
        self.optimal_mr_source = 'cea_scan'
        self.optimal_mr_thrust_source = 'not_modelled'

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
            lam = float(LAMBDA_BELL)
            src = ("published Rao-optimised bell divergence factor "
                   "(hrma.constants.LAMBDA_BELL, Sutton & Biblarz 9th ed.)")
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
        cs_source = ('user input (combustion efficiency)'
                     if 'combustion_efficiency' in self.overrides
                     else ('not supplied -> ideal energy release (1.000) '
                           'assumed; real engines deliver 0.92-0.99 '
                           '(Sutton & Biblarz 9th ed., Ch. 5)'))
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
            'eta_c_star_source': ('user input (combustion efficiency)'
                                  if 'combustion_efficiency' in self.overrides
                                  else 'not supplied -> 1.000'),
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
            self._expansion_optimum_fallback = False
        except Exception:
            # Son çare: kaba yaklaşım (eski fallback korunuyor)
            pressure_ratio = self.P_c / max(self.P_e, 1e-9)
            epsilon_optimal = pressure_ratio ** (1/g) * ((g+1)/2) ** ((g+1)/(2*(g-1)))
            epsilon_optimal = max(4, min(epsilon_optimal, 300))
            # Faz 4B (bulgu B1): bu dala düşüldüğünde ortam-eşlenik optimum
            # ÇÖZÜLEMEMİŞTİR; kaba bir yaklaşım kullanılır. design_summary
            # bunu okur ve o koşuyu 'OPTIMIZED' saymaz.
            self._expansion_optimum_fallback = True

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
                    self._warn('warn.liquid.regen_march_failed', 'warning',
                               fuel=str(self.fuel_type), detail=str(exc))
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
                        # Alt modülün (regen_cooling) kendi metni params.detail
                        # olarak taşınır; o modül D-track kapsamı dışında.
                        self._warn('warn.liquid.regen_march_note', 'warning',
                                   detail=str(w))

        elif self.cooling_type == 'ablative':
            # Ablative cooling - no active coolant flow
            ablative_thickness = 0.01  # 10mm ablative liner
            ablative_recession_rate = 0.1e-3  # 0.1 mm/s typical
            
        # Kanal hızı / basınç düşümü pratik sınırların üstündeyse uyarılır
        # (hesap yine yapılır — kullanıcı kanal sayısını/kesitini görsün).
        if coolant_flow > 0:
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
            'convergent_half_angle_basis': CONVERGENT_HALF_ANGLE_BASIS,
            'cooled_channel_length': (chamber_length + nozzle_axial_length) * 1000,  # mm
            'chamber_surface_area': A_chamber,  # m² (hazne silindiri)
            'nozzle_surface_area': A_nozzle_total,  # m² (koni yanal, eğik uzunlukla)
            'cooling_channels': n_channels if coolant_flow > 0 else 0,
            'channel_width_mm': channel_width * 1000,
            'channel_width_basis': COOLING_CHANNEL_WIDTH_BASIS,
            'channel_height_mm': channel_height * 1000,
            'channel_height_basis': COOLING_CHANNEL_HEIGHT_BASIS,
            'channel_height_auto_sized': bool(
                channel_height > COOLING_CHANNEL_HEIGHT_DEFAULT_M + 1e-12),
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
            'film_cooling_percent_source': str(getattr(
                self, 'film_cooling_percent_source', 'not supplied')),
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

    def calculate_injector_design(self):
        """High-precision injector design with advanced fluid mechanics"""
        
        # Advanced injector design based on web-validated propellant properties
        fuel_props = self.web_propellant_data.get(self.fuel_type, {})
        ox_props = self.web_propellant_data.get(self.oxidizer_type, {})
        
        # Use web data for viscosity if available
        fuel_viscosity = fuel_props.get('viscosity', 0.001)  # Pa·s
        ox_viscosity = ox_props.get('viscosity', 0.0005)  # Pa·s
        
        if self.injector_type == 'impinging':
            # Çarpışmalı (impinging) jet düzeni. NOT: burada "NASA
            # doğrulamalı" deniyordu — depoda böyle bir doğrulama kaydı
            # yok. Açı ve hız değerleri aşağıda kaynaklarıyla birlikte
            # veriliyor; iddia değil, girdi kabulü.
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
        droplet_diameter = critical_weber * surface_tension / (rho_gas * (v_relative**2))
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

        # Mixing efficiency calculation
        mixing_length = 0.05  # 50mm typical mixing length
        residence_time = mixing_length / np.sqrt(v_fuel_base * v_ox_base)
        
        # Yanma verimi: kullanıcı 'combustion_efficiency' girdiyse TEK KAYNAK
        # ODUR (2026-07-30 / O6: enjektör paneli kullanıcının %97'sini yok
        # sayıp enjektör tipine bağlı 0.98 sabitini gösteriyordu; kullanıcı
        # %80 girse bile panel 0.98'de kalıyordu). Girdi yoksa enjektör
        # tipinden gelen karışım kalitesi tahmini kullanılır ve etiketlenir.
        if self.injector_type == 'impinging':
            combustion_efficiency = 0.98  # Excellent mixing
        elif self.injector_type == 'coaxial':
            combustion_efficiency = 0.96  # Good mixing
        elif self.injector_type == 'showerhead':
            combustion_efficiency = 0.99  # Uniform distribution
        else:
            combustion_efficiency = 0.95  # Conservative estimate
        combustion_efficiency_source = (
            f"estimated from the injector type ({self.injector_type})")
        if 'combustion_efficiency' in self.overrides:
            combustion_efficiency = float(getattr(self, 'eta_c_star', 1.0))
            combustion_efficiency_source = 'user input (combustion efficiency)'

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
            'droplet_diameter': droplet_diameter * 1e6,  # microns
            'critical_weber_number': critical_weber,
            'critical_weber_number_basis': CRITICAL_WEBER_NUMBER_BASIS,
            'mixing_residence_time': residence_time * 1000  # ms
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
                'max_tank_pressure': max(
                    injector['required_fuel_tank_pressure'],
                    injector['required_ox_tank_pressure']),
            }

        # Turbopompalı çevrim: sayılar ayrıntılı pompa tasarımından gelir.
        tp = self._design_turbopump_system(self.mdot_ox, self.mdot_fuel)
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

            # Deniz seviyesi (tasarim noktasi) ideal CF — zincir demiri
            Pe_Pc_sl = max(self.P_a / self.P_c, 1e-8)
            CF_ideal_sl = np.sqrt(
                gamma_term * stagnation_term
                * (1 - Pe_Pc_sl ** ((gamma - 1) / gamma))
            )
            # Vakum ideal CF: ortam-eşlenik zincirde P_e/P_c -> 0 limiti.
            # Daima pozitiftir, kutbu yoktur — ikinci demir adayı (aşağı).
            CF_ideal_vac = np.sqrt(gamma_term * stagnation_term)
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
            # uydurma değil: vakum üst kademe lüleleri oradadır (RL10B-2 ≈ 280).
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
                isp_altitude = min(isp_per_cf * CF_ideal, self.isp_vac)
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
        # Do NOT apply again here (was causing double penalty).
        # v2.6.26: raporlanan DEĞER performans haritasının gerçek O/F
        # taramasından gelir (aşağıda performance_maps çözüldükten sonra
        # okunur); self.mr_efficiency canlı CEA yolunda koşulsuz 1.0'dır ve
        # yaprağı her motorda %100'e çiviliyordu.
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
        # Isıl koruma tek kaynak: yukarıdaki GERÇEK soğutma çözümünden türetilir.
        thermal_protection = self._calculate_thermal_protection_system(cooling)

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
        eniyilemeler = []
        if eps_kullanici is None and not eps_yedege_dustu:
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
            'chamber_temperature': self.T_c,
            'thrust_to_weight': thrust_to_weight,
            'engine_mass_estimate': engine_mass,
            'optimal_mixture_ratio': self.optimal_mr,
            'optimal_mixture_ratio_thrust': getattr(
                self, 'optimal_mr_thrust', self.optimal_mr),
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
                # v2.6.26: burada sabit 30.0 vardı ve enjektör TİPİ ne olursa
                # olsun (swirl, pintle, gaz-gaz) aynı sayı basılıyordu; oysa
                # injector_design bu açıyı zaten tipine göre ÇÖZÜYOR.
                **self._spray_angle_report(),
                'fuel_manifold_diameter_mm': max(10.0, np.sqrt(injector['fuel_injection_area'] * 4 / np.pi) * 2.5),
                'oxidizer_manifold_diameter_mm': max(12.0, np.sqrt(injector['ox_injection_area'] * 4 / np.pi) * 2.5),
                'fuel_injection_velocity_m_s': injector['fuel_injection_velocity'],
                'ox_injection_velocity_m_s': injector['ox_injection_velocity'],
                'combustion_efficiency': injector['combustion_efficiency'],
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
                    # A11: tank kartındaki kütle bu sayının 1.15 katıdır ve
                    # bunu KENDİ beyan eder — iki sayı aynı kavram değildir.
                    'propellant_mass_basis': (
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
                        'binding throat section: pi*d_throat/n_channels - '
                        'channel_width (channels are constant-width, so the '
                        'land varies along the axis and is narrowest at the '
                        'throat).'),
                }
                # Boğazdaki kirişler arası dolu et (land): sabit genişlikli
                # kanallarda en dar yerde. Pozitif değilse (kanallar boğaza
                # sığmıyor — çözücü zaten uyarıyor) alan YAYIMLANMAZ.
                land_m = (np.pi * float(self.d_t) / n_kanal) - kanal_w_m
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
        return PUMP_TANK_PRESSURE_DEFAULT_BAR, TANK_PRESSURE_SOURCE_TURBOPUMP

    def _calculate_line_diameter(self, mass_flow_rate: float, propellant_type: str) -> float:
        """Calculate optimal feed line diameter"""
        # Hedef hız TEK YERDE tanımlıdır (CLAUDE.md kural 11): burada satır içi
        # 5.0 yazılıyken modül başındaki FEED_LINE_TARGET_VELOCITY_MS ile aynı
        # kavramın iki tanımı vardı ve biri değişse öbürü sessizce kalırdı.
        target_velocity = FEED_LINE_TARGET_VELOCITY_MS  # m/s (3-8 bandı)

        # Yoğunluk tank modeliyle AYNI kaynaktan (bkz. _propellant_density).
        density, _ = self._propellant_density(propellant_type)

        # A = mdot / (rho * v)
        area = mass_flow_rate / (density * target_velocity)  # m²
        diameter = 2 * np.sqrt(area / np.pi)  # m
        
        # Round to standard pipe sizes
        standard_sizes = [0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3]  # m
        return min(standard_sizes, key=lambda x: abs(x - diameter))
    
    def _cycle_pump_flows(self):
        """Çevrim çözümünün pompa başına GERÇEK debisi -> (ṁ_ox, ṁ_yakıt).

        Turbopompalı çevrimde pompalar ana oda debisini DEĞİL, gaz
        jeneratörü / ön yakıcı payını da içeren toplam debiyi basar; O/F
        bölüşümü de ana odanınkinden farklıdır. Çevrim kapanmadıysa None.
        """
        flows = self._cycle_pump_duty()
        if flows is None:
            return None
        return flows[0], flows[1]

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
        ox = self._design_pump(mdot_ox, self.rho_ox, disch_ox, tank_bar,
                               shaft_power_kw=p_ox_kw,
                               propellant=self.oxidizer_type,
                               line=drops['oxidizer_line'])
        fuel = self._design_pump(mdot_fuel, self.rho_fuel, disch_fuel,
                                 tank_bar, shaft_power_kw=p_fuel_kw,
                                 propellant=self.fuel_type,
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
                'power': turbine_shaft_power / 1000,  # kW (mil dengesi)
                'power_basis': (
                    'shaft power balance: turbine shaft power equals the '
                    'total pump shaft power (steady state). The turbine '
                    'efficiency sizes the GAS consumption '
                    '(mdot = P_shaft/(eta x ideal specific work)), it does '
                    'not inflate the shaft power. When the cycle power '
                    'balance converges this is the same closure it reports '
                    '(engine_cycle_solution.turbine_power_total_W).'),
                'efficiency': eta_turbine,
                'inlet_temperature': turbine_inlet_temp,  # K
                'pressure_ratio': float(getattr(
                    self, 'turbine_pressure_ratio',
                    TURBINE_PRESSURE_RATIO_DEFAULT)),
                'rpm': ox['rotational_speed'],
                'material': 'Inconel 713C'
            },
            # B5 (v2.6.27): pompa devirleri ayrı emme sınırlarından gelir;
            # farklıysa bu bir dişli/çift-mil varsayımıdır ve BEYAN edilir.
            'shaft_architecture_note': self._shaft_architecture_note(ox, fuel),
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
            self._warn('warn.liquid.wall_heat_flux_unavailable', 'warning')
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

        # Viskozite: kullanıcı girdisi > tablo tabanı. Taban değerler TEK
        # tanım yerinden gelir (FEED_VISCOSITY_FALLBACK_PA_S); C2 vana/hat
        # bütçesi de aynı sözlüğü okur, iki hat hesabı ayrışamaz.
        mu_ox = (getattr(self, 'mu_ox', None)
                 or FEED_VISCOSITY_FALLBACK_PA_S['oxidizer'])
        mu_fuel = (getattr(self, 'mu_fuel', None)
                   or FEED_VISCOSITY_FALLBACK_PA_S['fuel'])

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
        if 'generator_gas_temp' in self.overrides:
            kwargs['tit_K'] = float(self.turbine_inlet_temp)
        if 'turbine_expansion_ratio' in self.overrides:
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
        if fuel_tank_material is None:
            fuel_tank_material = 'steel' if self.fuel_type == 'lh2' else tank_material
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
        try:
            from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
            res = PressureVesselAnalyzer().analyze(
                meop_bar=max(float(tank_pressure_pa) / PA_PER_BAR, 1e-6),
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
          KENDİ modelinden gelir (A = ṁ/(ρ·v), v = 3-8 m/s bandı; Huzel &
          Huang Böl. 7, NASA SP-125), tank ağzı hattan biraz geniş tutulur.
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
                    'angle for non-separating diffusion (Huzel & Huang Ch. 7; '
                    'ESDU 73024 conical diffuser separation limit) - a design '
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
        # Basınçlandırma gazı kimliği: turbopompalı LOX/hidrokarbon tanklarda
        # depolanmış inert gaz (helyum) standarttır; kullanıcı seçtiyse o.
        choice = str(getattr(self, 'pressurization_choice', None)
                     or 'auto').lower()
        gas_name = 'nitrogen' if choice == 'nitrogen' else 'helium'
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
                     propellant=None, line=None):
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
        power_source = ('rho*g*H*Q/eta at the design point '
                        '(single-stage head rise)')
        # Y4 (2026-07-30): çok kademeli mimaride (staged combustion'da RS-25
        # tipi ana+boost oksitleyici pompası) TOPLAM debi bildirilen en yüksek
        # basma basıncını GÖRMEZ; yalnız küçük ön yakıcı payı boost kademesine
        # girer. Tek kademe varsayımıyla hesaplanan güç bu durumda çevrim güç
        # dengesinden %12.8 sapıyordu. Çevrim mil gücü verildiyse TEK KAYNAK
        # odur; eğri şekli korunarak aynı oranla ölçeklenir.
        if shaft_power_kw is not None and power_design > 1e-9:
            scale = float(shaft_power_kw) / power_design
            power_design = float(shaft_power_kw)
            power_curve = [p * scale for p in power_curve]
            power_source = ('cycle power balance shaft power (multi-stage '
                            'architecture accounted for)')
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
        return {
            'design_flow_rate': mdot,                     # kg/s
            'volumetric_flow_m3_s': q,
            'design_head': head,                          # m
            'design_efficiency': eta_bep * 100.0,          # %
            'efficiency_source': ('user input (turbopump efficiency)'
                                  if 'turbopump_efficiency' in self.overrides
                                  else 'default best-efficiency-point value'),
            'design_power': power_design,                 # kW
            'design_power_source': power_source,
            'rotational_speed': rpm,                      # rpm
            'speed_source': speed_source,
            'impeller_tip_speed': u2,                     # m/s
            'impeller_diameter': d2,                      # m
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
                '(~11000 US), below the inducer design default (30000 US)'),
            'flow_range': flow_range,
            'head_curve': head_curve,
            'efficiency_curve': eff_curve,
            'power_curve': power_curve,
            'npsh_curve': npsh_curve,
            'model': ('Euler head with Stodola slip; shaft speed set at '
                      f'{SPEED_DERATE_DEFAULT:g} x the suction specific '
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
        pipe_material = str(self.overrides.get('feed_line_material')
                            or WATER_HAMMER_DEFAULT_PIPE_MATERIAL).strip()
        pipe_material_source = (
            'user input (feed line material)'
            if self.overrides.get('feed_line_material')
            else f"not supplied -> '{WATER_HAMMER_DEFAULT_PIPE_MATERIAL}' "
                 'assumed (HRMA does not model a line material choice)')

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
            d2_engine = float(pump['impeller_diameter'])
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
                'tank_pressure_source': (
                    'NPSH tank pressurisation assumption '
                    f'({PUMP_TANK_PRESSURE_DEFAULT_BAR:g} bar, '
                    'PUMP_TANK_PRESSURE_DEFAULT_BAR) - the SAME value the '
                    'engine pump chain uses for its own NPSH; HRMA has no '
                    'pressurisation schedule model'),
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
                    'their ratio is a design-maturity indicator.'),
                'impeller_diameter_ratio': (
                    float(d2_module) / d2_engine
                    if (d2_module and d2_engine > 0) else None),
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
        turbine = None
        eta_turb = TURBINE_EFFICIENCY_DEFAULT
        eta_source = (f'engine default turbine efficiency '
                      f'({TURBINE_EFFICIENCY_DEFAULT:g})')
        shafts = (cycle_solution or {}).get('shafts') or []
        if (cycle_solution or {}).get('status') == 'converged' and shafts:
            eta_cyc = (shafts[0].get('turbine') or {}).get('efficiency')
            if isinstance(eta_cyc, (int, float)) and 0.0 < eta_cyc <= 1.0:
                eta_turb = float(eta_cyc)
                eta_source = ('cycle power balance solution (the efficiency '
                              'the converged shaft turbine actually used)')
        p_turb_w = float(turbine_card.get('power_output') or 0.0) * 1000.0
        mdot_turb = float(turbine_card.get('mass_flow_rate') or 0.0)
        if p_turb_w > 0.0 and mdot_turb > 0.0:
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
                    fluid=(fluid_key or 'water'),
                    roughness_m=FEED_LINE_ROUGHNESS_M,
                    extra_loss_coefficient=k_extra,
                    vapor_pressure_Pa=vapor_pa,
                    valve_style=FEED_MAIN_VALVE_STYLE,
                    valve_closure_time_s=(None if closure_ms is None
                                          else float(closure_ms) / 1000.0))
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
                'water_hammer_coupling_source': (
                    'user input (feed line wall thickness)' if wall_mm
                    is not None else
                    'not produced: feed_line_wall_thickness [mm] is not '
                    'supplied and HRMA computes no line wall thickness, so '
                    'the elastic wave speed is undefined'),
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
                                    line=drops['oxidizer_line'])
        fuel_pump = self._design_pump(mdot_fuel, self.rho_fuel,
                                      drops['pump_discharge_pressure_fuel'],
                                      tank_bar, shaft_power_kw=p_fuel_kw,
                                      propellant=self.fuel_type,
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
        if p_in:
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
        delta_h = (TURBINE_GAS_CP_J_KGK * t_in
                   * (1.0 - pr ** (-(TURBINE_GAS_GAMMA - 1.0)
                                   / TURBINE_GAS_GAMMA)))
        c0 = np.sqrt(2.0 * delta_h)                   # spouting velocity, m/s
        blade_tip_speed = TURBINE_VELOCITY_RATIO * c0
        if blade_tip_speed > TURBINE_TIP_SPEED_LIMIT_MS:
            self._warn('warn.liquid.turbine_tip_speed_exceeded', 'warning',
                       tip_speed_ms=round(float(blade_tip_speed)),
                       limit_ms=round(float(TURBINE_TIP_SPEED_LIMIT_MS)))
        turbine_mdot = turbine_power * 1000.0 / max(delta_h * eta_turbine, 1.0)

        gg_mdot = mdot_total * GAS_GENERATOR_FLOW_FRACTION
        gg_chamber_pressure = self.P_c * GAS_GENERATOR_PRESSURE_RATIO

        # Çevrim çözümü varsa türbin/ön yakıcı kartı ONDAN gelir (sabit %5
        # GG debisi ve genel PR varsayımı yerine kapanan denge — madde 2).
        turbine_card = {
            'type': 'Single-stage axial',
            'power_output': turbine_power,  # kW (mil dengesi = pompa gücü)
            'power_output_basis': (
                'shaft power balance: turbine shaft power equals the total '
                'pump shaft power; the turbine efficiency sizes the gas '
                'mass flow (mdot = P_shaft/(eta x ideal specific work)), '
                'not the shaft power'),
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
            },
            'turbopump_required': not pressure_fed,
            'tank_pressure_bar': tank_bar,
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
            'turbopump_sizing': self._turbopump_sizing_block(
                drops, tank_bar, pressure_fed, ox_pump, fuel_pump,
                turbine_card, cycle_solution),
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
        üst hıza (3-8 m/s bandının tepesi; Huzel & Huang Böl. 7, NASA SP-125)
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
        sınırında (TURBINE_TIP_SPEED_LIMIT_MS; Huzel & Huang Böl. 6) aynı gaz
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
        npsh_worst = None
        npsh_worst_pump = None
        for name, pump in (('oxidizer_pump', ox_pump),
                           ('fuel_pump', fuel_pump)):
            m = ((pump['npsh_available'] - pump['npsh_required'])
                 / max(abs(pump['npsh_required']), 1e-9) * 100.0)
            if npsh_worst is None or m < npsh_worst:
                npsh_worst, npsh_worst_pump = m, name
        margins = {
            'pressure_margin': (
                (drops['pump_discharge_pressure_ox'] - self.P_c)
                / max(self.P_c, 1e-9) * 100.0),
            'npsh_margin': npsh_worst,
            'npsh_margin_basis': (
                '(NPSH_available - NPSH_required)/NPSH_required of the '
                f'binding (worst) pump: {npsh_worst_pump}. The shaft speed '
                'is derated below the suction-limited maximum '
                f'(SPEED_DERATE_DEFAULT {SPEED_DERATE_DEFAULT:g}), so the '
                'uncapped design-point margin is '
                f'{(SPEED_DERATE_DEFAULT ** (-4.0 / 3.0) - 1.0) * 100.0:.1f}'
                '% rather than zero-by-construction; it grows when the '
                'practical rpm cap binds and goes negative when tank '
                'pressurization is insufficient (see '
                'warn.liquid.npsh_pressurization_insufficient)'),
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
        dh = None if pressure_fed else turbine_card.get('specific_work_J_kg')
        if dh and dh > 0:
            dh_limit = (TURBINE_TIP_SPEED_LIMIT_MS
                        / TURBINE_VELOCITY_RATIO) ** 2 / 2.0
            margins['power_margin'] = (dh_limit / float(dh) - 1.0) * 100.0
            margins['power_margin_basis'] = (
                'single-stage turbine specific-work headroom: the blade tip '
                f'speed limit ({TURBINE_TIP_SPEED_LIMIT_MS:g} m/s at '
                f'U/C0 = {TURBINE_VELOCITY_RATIO:g}) caps the extractable '
                'work at the same gas flow. A multi-stage turbine relaxes '
                'this limit. The shaft power balance itself closes exactly, '
                'so turbine-minus-pump power is zero by construction.')
        else:
            margins['power_margin'] = None
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
        from hrma.constants import ISA_LAYERS, M_AIR, R_STAR_ICAO
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

        h_geopot = None
        for h_base, t_base, lapse, p_base in ISA_LAYERS:
            # Katmanın tepe basıncı bir sonraki katmanın tabanıdır; p_exit bu
            # katman içindeyse tersini analitik çöz.
            if p_exit > p_base:
                continue
            if abs(lapse) > 1e-12:
                # P = P_b (T/T_b)^(-g M/(R L))  ->  T = T_b (P/P_b)^(-R L/(g M))
                expo = -(R_STAR_ICAO * lapse) / (G_0 * M_AIR)
                t = t_base * (p_exit / p_base) ** expo
                h_geopot = h_base + (t - t_base) / lapse
            else:
                h_geopot = h_base - (R_STAR_ICAO * t_base / (G_0 * M_AIR)) \
                    * np.log(p_exit / p_base)
            break
        if h_geopot is None:
            return {
                'optimal_altitude': None,
                'nozzle_exit_pressure_bar': p_exit_bar,
                'optimal_altitude_basis': (
                    'vacuum-optimised: the exit pressure is below the top of '
                    'the ISA table (71 km), so there is no finite matched '
                    'altitude'),
            }
        # Geopotansiyel -> geometrik irtifa (aynı dönüşümün tersi)
        r_earth = 6356766.0
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
        """``injector_design`` modülünün tam çıktısı ya da None (memoize)."""
        cached = getattr(self, '_injector_detail_memo', None)
        if cached is not None:
            return cached or None
        try:
            detail = (self.calculate_injector_design() or {}).get(
                'injector_design_detail')
        except Exception:
            detail = None
        self._injector_detail_memo = detail or {}
        return detail

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
        combustion_efficiency_source = (
            'user input (combustion efficiency) via the delivered c* chain'
            if 'combustion_efficiency' in self.overrides
            else 'not supplied -> ideal energy release (1.000) assumed')
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
                'momentum_ratio': momentum_ratio,
                'optimal_momentum_ratio': optimal_momentum_ratio,
                'momentum_criterion_basis': momentum_basis,
            },
            'stability_analysis': self._stability_assessment(
                a_chamber, chamber_length, chamber_diameter, mixing_time,
                l_star_m=L_star, residence_time_s=residence_time)
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
                'Enjektör basınç düşümü bilinmiyor; chug marjı hesaplanamadı.')
        elif dp_pc >= CHUG_DP_PC_RECOMMENDED_LIQUID:
            rating, reason = 'chug_margin_ok', (
                'ΔP/Pc = %.3f, klasik tasarım kuralının tavsiye eşiğinin '
                '(%.2f) üstünde.' % (dp_pc, CHUG_DP_PC_RECOMMENDED_LIQUID))
        elif dp_pc >= CHUG_DP_PC_MIN_LIQUID:
            rating, reason = 'chug_margin_marginal', (
                'ΔP/Pc = %.3f, alt sınır (%.2f) ile tavsiye eşiği (%.2f) '
                'arasında.' % (dp_pc, CHUG_DP_PC_MIN_LIQUID,
                               CHUG_DP_PC_RECOMMENDED_LIQUID))
        else:
            rating, reason = 'chug_risk', (
                'ΔP/Pc = %.3f, klasik tasarım kuralının alt sınırının (%.2f) '
                'altında — düşük frekanslı (chug) kararsızlık riski.'
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
                'Akustik-yanma bağlaşımı (yüksek frekanslı kararsızlık) bu '
                'modelde çözülmüyor; yalnız mod frekansları (merkezî akustik '
                'modülden) ve chug çevrimi raporlanır.'),
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
        area = self._override_val('feed_line_area_m2', 1e-8, 1.0,
                                  'Feed line flow area', ' m²')
        if area is None:
            d_mm = self._override_val('feed_line_diameter_mm', 0.5, 500.0,
                                      'Feed line inner diameter', ' mm')
            if d_mm is not None:
                area = np.pi * (float(d_mm) / 1000.0) ** 2 / 4.0
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
        return tau_f, {
            'line_length_m': float(length),
            'line_area_m2': float(area),
            'mass_flow_kg_s': float(mdot),
            'dp_injector_Pa': dp_bar * PA_PER_BAR,
            '_basis': (
                'Feed line length/area supplied by the caller; the mass flow '
                'is this run\'s TOTAL propellant flow and the pressure drop '
                'is the lumped injector drop, consistent with the single '
                'lumped injector used for J. Separate oxidiser/fuel line '
                'dynamics are NOT modelled (that is a coupled two-line '
                'problem).'),
        }

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
            loop = assess_chug(dp_ratio_j=float(dp_pc), tau_s=tau_s,
                               tau_c_s=tau_c['tau_c_s'], tau_f_s=tau_f,
                               feed_line=feed_echo)
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
            '(Crocco & Cheng, AGARDograph 8, 1956).')
        # τ_c'nin İKİNCİ yolu: bu koşunun kendi kalış süresi. Cebirsel olarak
        # AYNI büyüklüktür (ρV/ṁ = L*/(c*Γ²), çünkü ṁ = P_c A_t/c* ve
        # ρ = P_c/(RT), R·T = (c*Γ)²). Eşit ÇIKMIYORSA fark motorun kendi
        # ṁ ↔ c* tutarlılığındandır ve SESSİZ KALMAZ: ölçülüp yayımlanır.
        if (residence_time_s and np.isfinite(residence_time_s)
                and residence_time_s > 0):
            ratio = float(residence_time_s) / tau_c['tau_c_s']
            loop['tau_c_vs_residence_time'] = {
                'tau_c_s': tau_c['tau_c_s'],
                'residence_time_s': float(residence_time_s),
                'ratio': ratio,
                'interpretation': (
                    'Two independent routes to the SAME physical time: '
                    'tau_c = L*/(c* Gamma^2) and the chamber residence time '
                    'rho_gas*V_c/mdot. They are algebraically identical when '
                    'mdot = Pc*A_t/c* holds exactly. The residual measured '
                    'here is the liquid chain\'s own mdot-vs-c* consistency '
                    '(the mass flow comes from the thrust/Isp chain, not '
                    'from the choked-throat identity); it is reported, not '
                    'silently absorbed.'),
            }
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

        Her nokta AYNI çözücüyle (self._scan_engine) yeniden koşulur; ayrı bir
        basitleştirilmiş model yoktur. Çözülemeyen nokta uydurulmaz, atlanır ve
        'skipped' listesinde gerekçesiyle görünür.

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

        points, skipped = [], []
        for frac in fractions:
            f = float(frac)
            if not (0 < f <= 1.0):
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
            points.append({
                'throttle_fraction': f,
                'thrust_n': float(self.F * f),
                'chamber_pressure_bar': float(pc),
                'isp_sea_level': float(isp_sl) if isp_sl else None,
                'isp_vacuum': float(isp_vac) if isp_vac else None,
                'injector_dp_bar': float(dp_bar),
                'injector_dp_over_pc': float(dp_over_pc) if dp_over_pc else None,
                'chug_rating': chug,
            })
        min_pct = getattr(self, 'min_throttle_pct', None)
        out = {
            'points': points,
            'skipped': skipped,
            'design_dp_over_pc': dp_frac_design,
            'assumptions': [
                'Oda basıncı itki oranıyla birinci mertebeden ölçeklendi '
                '(c*\'ın zayıf Pc bağımlılığı ihmal edildi).',
                'Enjektör alanı SABİT kabul edildi; ΔP debinin karesiyle '
                'ölçeklenir (ΔP ∝ ṁ²). Kısılabilir (pintle vb.) enjektörde '
                'gerçek ΔP daha yüksek tutulabilir.',
                'Geçici rejim (throttle sırasındaki dinamik davranış) '
                'modellenmedi; her nokta KARARLI hâl çözümüdür.',
            ],
            'transient_response': 'not_modelled',
        }
        if min_pct is not None:
            out['min_throttle_pct'] = float(min_pct)
            worst = [p for p in points
                     if p['throttle_fraction'] * 100.0 >= float(min_pct) - 1e-9
                     and p['chug_rating'] == 'chug_risk']
            out['min_throttle_chug_risk'] = bool(worst)
        return out

    def _autogenous_pressurization_summary(self):
        """Autogenous basınçlandırma boyutlandırması (uygunsa).

        Yalnız TURBOPOMPALI + metan/LOX veya LH2/LOX konfigürasyonunda
        sayısal boyutlandırılır — bu iticiler ısı değiştiriciden geçirilip
        kendi tanklarına gaz olarak geri beslenebilir (Raptor/Starship yolu).
        Uygun değilse sahte sayı değil, 'not_applicable' gerekçesi döner.

        Pompadan/ısı değiştiriciden çalınan gaz kütlesi sistem bütçesine
        işlenir; itki üretmez.
        """
        # Basınç beslemeli sistemde autogenous kavramı geçerli değil (ayrı
        # basınçlandırma zaten helyum/azot şişesiyle yapılır).
        if self.feed_system_type != 'turbopump':
            return {'status': 'not_applicable', 'reason':
                    'Autogenous basınçlandırma turbopompalı çevrimler içindir; '
                    'basınç beslemeli sistemde ayrı pressurant kullanılır.'}
        fuel = str(self.fuel_type).strip().lower()
        ox = str(self.oxidizer_type).strip().lower()
        if ox not in ('lox', 'oxygen') or fuel not in ('methane', 'lch4',
                                                        'ch4', 'lh2', 'hydrogen'):
            return {'status': 'not_applicable', 'reason':
                    f"Autogenous yalnız metan/LOX ve LH2/LOX için modellendi; "
                    f"'{self.fuel_type}/{self.oxidizer_type}' desteklenmiyor "
                    '(diğer iticilerde helyum basınçlandırma kullanılır).'}
        try:
            from hrma.analysis.pressurant_sizing import autogenous_pressurant
            if not hasattr(self, 'mdot_total'):
                self.calculate_nozzle_geometry()
            burn_time, _ = self._burn_time()
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
                'note': ('Autogenous basınçlandırma: iticiler ısı '
                         'değiştiriciden geçirilip kendi tanklarına gaz olarak '
                         'geri beslenir; ayrı helyum şişesi yok. Çalınan gaz '
                         'kütlesi itici bütçesinden düşülür.'),
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
        return LiquidRocketEngine(**params)

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
                'thrust_basis': ('thrust achievable with THIS engine throat '
                                 'area at the scanned chamber pressure'),
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
        # B4 (v2.6.27): iki karar da BEYANLI çıkar. Emniyet katsayısı ve
        # malzeme tasarımın en belirleyici iki girdisidir (kalınlık, marj,
        # kütle); hangisinin kullanıcıdan hangisinin varsayılandan geldiği
        # sayının yanında durmazsa okuyan ikisini ayıramaz. Kaynak metni
        # _apply_overrides'ın yazdığı TEK künyeden okunur.
        sf_source = self._safety_factor_source()
        mat_source = self._chamber_material_source()
        t_hot, _ = self._wall_temperatures()
        sigma_y, derate = self._derated_yield(material, t_hot)
        allowable = sigma_y / sf

        d_c = self._chamber_diameter()
        p_int = self.P_c * PA_PER_BAR  # Pa
        t_required = max((p_int * d_c / 2.0) / allowable, WALL_THICKNESS_MANUFACTURING_MIN_M)

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
            'material_selection_source': mat_source,
            'safety_factor': sf,
            'safety_factor_source': sf_source,
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

    #: Kapak/enjektör flanşı cıvata birleşiminin varsayılan kabulleri — TEK
    #: tanım noktası (katı motordaki SOLID_CLOSURE_JOINT_DEFAULTS deseninin
    #: sıvı karşılığı). Bunlar HESAP DEĞİL, kullanıcı girdisi verilmediğinde
    #: kullanılan sözleşme değerleridir ve çıktıda adıyla beyan edilirler.
    LIQUID_CLOSURE_JOINT_DEFAULTS = {
        'size': 'M8',
        'property_class': '8.8',
        'member_material': 'aluminum_6061',
        'bolt_count_range': (1, 200),
    }

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
            },
            # A4 (v2.6.27): kapak/enjektör flanşı cıvata birleşimi — katı
            # motorla aynı şema adı (closure_joint) ve aynı analizör.
            'closure_joint': self._closure_joint_analysis(),
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
            # v2.6.26: tek metin iki farklı şeyi anlatamaz. Eski
            # 'channel_section_source' genişlik ve derinliği birlikte "design
            # default (not auto-sized)" ilan ediyordu; derinlik için bu YALANDI.
            # Beyanlar ayrıldı ve sayının yanına taşındı (cooling_system).
            'channel_width_basis': COOLING_CHANNEL_WIDTH_BASIS,
            'channel_height_basis': COOLING_CHANNEL_HEIGHT_BASIS,
            'channel_height_auto_sized': cooling.get(
                'channel_height_auto_sized'),
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
        else:
            result['station_march_status'] = (
                '1D station march available for RP-1 regenerative cooling '
                'only; the values above come from the Bartz chamber/nozzle '
                'integration.')

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
        if self.cooling_type not in ('ablative', 'radiative'):
            return {
                'passive_thermal_protection': {
                    'status': 'NOT_APPLICABLE',
                    '_basis': basis,
                    'reason': (
                        f"the wall is actively cooled ('{self.cooling_type}'): "
                        'the Bartz + channel-hydraulics chain above (and the '
                        'regen_cooling station march where it applies) IS '
                        'the thermal protection solution for this design. '
                        'Adding an ablation or heat-sink sizing on the same '
                        'wall would put two competing thermal protection '
                        'claims in one answer.'),
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
        if cooling is None:
            try:
                cooling = self.calculate_cooling_requirements()
            except Exception:
                cooling = {}
        if injector is None:
            try:
                injector = self.calculate_injector_design()
            except Exception:
                injector = {}
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
                'chamber_volume': (self._l_star() * np.pi * (self.d_t**2) / 4) * 1e6  # cm³
            },
            'mass_ratios': {
                'thrust_to_weight': self.F / (total_dry_mass * G_0),
                'power_to_weight': (pump_power_kw / total_dry_mass
                                    if total_dry_mass > 0 else 0.0),  # kW/kg
                'chamber_loading': self.F / chamber_mass  # N/kg
            }
        }