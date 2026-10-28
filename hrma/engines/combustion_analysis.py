"""
Advanced Combustion Analysis Module
NASA CEA-style chemical equilibrium and performance calculations with Cantera integration
"""

import copy
import numpy as np
# ÖH D31 / P15B2-01 — yerel değer kapıları merkezden okur (tek kural).
from hrma.utils.input_guard import finite_number as _finite_number
# ÖH D17 / P15B2-08: katı yakıt yoğunlukları TEK KAYNAK.
from hrma.data.propellant_database import (
    HYBRID_FUEL_DENSITY_KG_M3 as _FUEL_RHO)
import json
import logging
import warnings
from typing import Dict, List, Tuple, Optional
from scipy.optimize import minimize_scalar, fsolve, brentq

# Cantera opsiyonel bağımlılık (paper: "where available").
# Kurulu değilse modül import edilebilir kalır ve ampirik yola düşer.
try:
    import cantera as ct
    CANTERA_AVAILABLE = True
except ImportError:
    ct = None
    CANTERA_AVAILABLE = False

from hrma.constants import (G_0, R_UNIVERSAL, PA_PER_BAR, BAR_PER_PA,
                            isa_pressure, isa_temperature)

logger = logging.getLogger(__name__)

#: ÖH D20 / B3-13 — ``sea_level_isp`` künyesi (kullanıcıya dönük: İngilizce).
_SEA_LEVEL_ISP_BASIS = (
    'specific impulse of the h = 0 row of the altitude sweep. It is looked '
    'up by altitude, NOT taken as the first row of the table: if the caller '
    'does not ask for sea level, the field is null rather than reporting '
    'some other altitude under the name "sea level".')

# Kuru hava O2/N2 KÜTLE kesirleri (Ar ve eser gazlar N2'ye katılmıştır).
# Kaynak: US Standard Atmosphere 1976 hacimsel bileşiminden
# (x_O2=0.2095, M_hava=28.9645 g/mol) -> Y_O2 = 0.2095*31.9988/28.9645 = 0.2314
AIR_O2_MASS_FRACTION = 0.2314
AIR_N2_MASS_FRACTION = 0.7686

# Kuru hava O2/N2 MOL kesirleri (US Standard Atmosphere 1976; Ar N2'ye dahil)
AIR_O2_MOLE_FRACTION = 0.21
AIR_N2_MOLE_FRACTION = 0.79

# ---------------------------------------------------------------------------
# ÖH D21 / OH-D17-10 — γ FİZİKSEL KABUL BANDI, TEK ADLANDIRILMIŞ SABİT.
#
# Bant iki yerde ADSIZ literal olarak yazılıydı (analyze_combustion'ın oda
# gamma'sı süzgeci ve _exit_pressure_from_expansion'ın ön kontrolü). İkisi
# aynı fiziksel iddiayı taşıyor: özgül ısı oranı ideal gazda γ = c_p/c_v > 1
# ve tek atomlu sınırda γ ≤ 5/3; 2.0 üst sınırı bu sınırın üstünde güvenli
# bir kesme olarak seçilmiştir (Sutton & Biblarz 9. baskı Böl. 3; NASA
# RP-1311 Part I §2). Adsız iki kopya birinin sessizce kaymasına açık
# kapıydı — B3-09'un kenar_tol'ü ile aynı desen.
GAMMA_PHYSICAL_MIN = 1.0
GAMMA_PHYSICAL_MAX = 2.0

#: ÖH D21 / P12bB3-02 — ÇÖZÜCÜNÜN ONURLANDIRDIĞI HİBRİT YAKIT KÜMESİ,
#: TEK KAYNAK. Liste eskiden İKİ yerde yazılıydı: fonksiyon içi ``FUEL_KEYS``
#: demeti ve reddin İngilizce metnindeki "Supported fuels: htpb, paraffin,
#: ..." kopyası. İkisi elle senkron tutuluyordu; bekçi (D15/a2) desteklenen
#: listeyi HATA METNİNDEN regex'le söküyordu, yani sözleşme insan cümlesine
#: asılıydı. Artık hem elemental katkı dalı, hem red mesajı, hem de bekçi bu
#: demeti okur. Üyelik ölçütü: yakıtın ``_REACTANT_FORMULAS`` içinde bir
#: kimyasal formülü olması — formülü olmayan anahtar elemental katkı
#: üretemez ve dengeyi çöple besler (fail-closed).
SUPPORTED_HYBRID_FUEL_KEYS = ('htpb', 'paraffin', 'pe', 'pmma', 'abs', 'pla',
                              'aluminum')

#: ÖH D31 / P12bB3-02 — REDDİN GEREKÇESİ ADIYLA SÖYLENİR (TEK KAYNAK).
#:
#: ÖLÇÜLDÜ (D31 hibrit a1 ``once.json`` K2, taban 9d70e9ed): arayüzün yakıt
#: menüsünde ``disabled`` duran DÖRT anahtarın (``carbon``, ``al2o3``,
#: ``mixture``, ``custom``) dördü de bu çözücüde AYNI genel gerekçeyle
#: (``unsupported_fuel_key``) ve AYNI cümleyle reddediliyordu — ayrı gerekçe
#: sayısı **1**. Oysa dördü ÜÇ FARKLI şeydir ve kullanıcının yapabileceği iş
#: de üçünde farklıdır:
#:   * ``al2o3`` bir KATEGORİ hatasıdır — alüminyum oksit tam oksitlenmiştir,
#:     yakıt tanesi değildir; egzozdaki yoğuşmuş fazdır. Veri beklemek
#:     anlamsızdır, bu anahtar hiçbir zaman desteklenmeyecektir.
#:   * ``carbon`` bir LİTERATÜR borcudur — hakemli bir karbon/grafit
#:     regresyon korelasyonu arandı ve bulunamadı (Berke karar dosyası, Veri
#:     eki B, 2026-09-14); ayrıca saf karbon polimerler gibi piroliz
#:     etmediği için ``r = a·G^n`` ailesinin uygulanabilirliği de açıktır.
#:   * ``mixture`` / ``custom`` bir SÖZLEŞME kararıdır — veri değil şema
#:     eksiktir: kullanıcının karışımı hangi alanlarla tarif edeceği
#:     tanımlanmamıştır. Bileşenler ayrı ayrı gönderilebilir.
#:
#: Gerekçe metinleri KULLANICIYA görünür (API yanıtı) -> İngilizce. Hiçbir
#: satır yeni bir SAYI açmaz; yalnız reddin sebebini adlandırır (fail-closed
#: korunur, doktrin 1).
HYBRID_FUEL_REJECTION_REASONS = {
    'al2o3': (
        'not_a_fuel',
        'Aluminium oxide is a fully oxidised combustion product, not a grain '
        'fuel: it carries no heat of combustion as a hybrid fuel. This key '
        'is a category error, not a missing-data item, and will not be '
        'supported. Use "aluminum" for a metal additive.'),
    'carbon': (
        'no_peer_reviewed_correlation',
        'No peer-reviewed r = a*G^n regression correlation was found for '
        'carbon/graphite hybrid grains, and pure carbon does not pyrolyse '
        'the way polymeric fuels do, so the applicability of that '
        'correlation family is itself open. No coefficients are invented '
        'here.'),
    'mixture': (
        'no_request_contract',
        'Composite grains are a request-schema gap, not a data gap: this API '
        'does not define how a mixture is described (which components, in '
        'what mass fractions). Send the components you want as separate '
        'supported fuel keys.'),
    'custom': (
        'no_request_contract',
        'A user-defined fuel is a request-schema gap, not a data gap: this '
        'API does not define which thermochemical fields a custom grain must '
        'supply (formula, density, heat of formation, regression pair). '
        'Nothing is assumed on your behalf.'),
}


def _unsupported_fuel_error(fuel_type):
    """Desteklenmeyen yakıt anahtarı için ADLANDIRILMIŞ red (P12bB3-02).

    TEK KAYNAK: her iki kapı da bu fonksiyonu çağırır; desteklenen liste ve
    gerekçe tablosu elle senkron tutulan ikinci kopya taşımaz.
    """
    gerekce, aciklama = HYBRID_FUEL_REJECTION_REASONS.get(
        fuel_type, ('unsupported_fuel_key', None))
    metin = ("Unsupported fuel key '%s'. Supported fuels: %s."
             % (fuel_type, ', '.join(SUPPORTED_HYBRID_FUEL_KEYS)))
    if aciklama:
        metin = '%s %s' % (metin, aciklama)
    hata = ValueError(metin)
    hata.field = 'fuel_type'
    hata.reason = gerekce
    hata.supported_fuels = list(SUPPORTED_HYBRID_FUEL_KEYS)
    if aciklama:
        hata.explanation = aciklama
    return hata


def gamma_is_physical(g) -> bool:
    """γ fiziksel kabul bandında mı (GAMMA_PHYSICAL_MIN < γ < MAX).

    ÖH D31 / P15B2-01 (OH-D30-08 dağıtımı, satır 31: bu sembol hibrit
    kulvarına düştü). YEREL DEĞER KAPISI MERKEZE BAĞLANDI: sayı okuma
    kuralı artık burada elle yazılmıyor, ``hrma.utils.input_guard
    .finite_number`` merkezinden geliyor — "sonlu sayı mı?" sorusunun
    deponun her yerinde TEK yanıtı olsun diye (``bool`` sayı sayılmaz,
    NaN/inf sayı sayılmaz, çevrilemeyen değer sayı sayılmaz).
    Band ölçütü (``GAMMA_PHYSICAL_MIN/MAX``) bu modülün kendi fiziğidir
    ve olduğu gibi kaldı; DAVRANIŞ DEĞİŞMEDİ (ölçüldü: aynı 12 girdide
    aynı 12 yanıt), değişen tek şey kuralın nereden geldiğidir.
    """
    parsed = _finite_number(g)
    if parsed is None:
        return False
    return bool(GAMMA_PHYSICAL_MIN < parsed < GAMMA_PHYSICAL_MAX)


# ---------------------------------------------------------------------------
# ÖH D24 / P15B1-05 — İSTASYON TABLOSUNUN BİRİMLERİ, TEK KAYNAK.
#
# ÖLÇÜLDÜ (once.json K2, taban 2e4d81f): hibrit yanıtında ``enthalpy``,
# ``entropy``, ``cp`` ve ``cv`` adları AYNI gövdede iki ayrı birimde
# yayımlanıyordu ve fark tam 1000 kattı —
#   motor.combustion_analysis.compositions.chamber.enthalpy
#       = 1 605 035,2237607732            [J/kg]   (denge çözücüsünün ham SI çıktısı)
#   motor.combustion_analysis.performance.thermodynamic_properties
#       .stations.chamber.enthalpy = 1 605,0352237607733  [kJ/kg]
# Aynı ikilik cp (1 609,44 ⟷ 1,60944), cv ve entropy (10 217,285 ⟷
# 10,217285) için de vardı. Ad birimi taşımadığından iki gövde ayırt
# edilemiyordu.
#
# ÇÖZÜM: kJ tabanlı istasyon tablosunun alan ADLARI birimi taşır
# (``enthalpy_kJ_kg`` vb.). ``compositions`` tarafı denge çözücüsünün ham
# SI çıktısıdır ve adı DEĞİŞMEZ (J/kg); artık aynı adı taşımadıkları için
# çakışma yoktur. Birim dizgileri burada BİR KEZ yazılır.
_STATION_UNITS = {
    'enthalpy_kJ_kg': 'kJ/kg',
    'entropy_kJ_kg_K': 'kJ/(kg*K)',
    'gibbs_energy_kJ_kg': 'kJ/kg',
    'cp_kJ_kg_K': 'kJ/(kg*K)',
    'cv_kJ_kg_K': 'kJ/(kg*K)',
    'gamma': '-',
    'molecular_weight': 'kg/kmol',
    'speed_of_sound': 'm/s',
    'density': 'kg/m^3',
    'temperature': 'K',
    'pressure': 'bar',
}

# ---------------------------------------------------------------------------
# ÖH D24 / P15B1-05 — ÇALIŞMA NOKTASI BEYANI (iki termokimya ağacı).
#
# ÖLÇÜLDÜ (once.json K2, taban 2e4d81f; htpb/n2o, O/F=6,0, Pc=20 bar):
# hibrit yanıtı aynı iskeleti İKİ ağaçta yayımlıyor —
#   motor.combustion_analysis.*          (273 sayısal yaprak)
#   motor.optimum_analysis.analysis.*    (271 yaprak)
# 271 ortak yolun 146'sı >%1, 43'ü >%10 ayrışıyor. Sebep TEK yaprakta:
# ``inputs.of_ratio`` = 6,0 ⟷ 6,078564148225201.
#
# ÖNEMLİ — BU BİR HESAP HATASI DEĞİL, BEYAN EKSİĞİYDİ. İki ağaç kasıtlı
# olarak FARKLI çalışma noktasındadır: birincisi kullanıcının TASARIM
# O/F'si, ikincisi ``find_optimum_of_ratio``un bulduğu OPTİMUM O/F'de
# yapılan DANIŞMA analizidir (bkz. hybrid_rocket_engine: "find_optimum_of_
# ratio yalnız danışma amaçlıdır ve tasarım O/F'sini DEĞİŞTİRMEZ").
# İkisini tek bir O/F kaynağına bağlamak — ilk bakışta "tek kaynak"
# onarımı gibi görünse de — optimum aramasını YOK EDERDİ: ya danışma
# tasarım noktasını tekrarlar (bilgi sıfır), ya da tasarım tablosu
# kullanıcının istemediği bir O/F'de yayımlanır (yanlış). Kusur,
# ağaçların çalışma noktasını İLAN ETMEMESİYDİ: ``chamber.temperature``
# okuyan iki tüketici farklı sayı alıyor, ikisi de haklı oluyor ve fark
# ancak of_ratio yaprağı okunarak görülebiliyordu. Onarım: her ağaç kendi
# çalışma noktasını ADIYLA taşır.
OPERATING_POINT_DESIGN = 'design_point'
OPERATING_POINT_OPTIMUM_SEARCH = 'optimum_of_search_result'
OPERATING_POINT_AS_REQUESTED = 'as_requested'

_OPERATING_POINT_BASIS = {
    OPERATING_POINT_DESIGN: (
        'the O/F ratio requested by the caller (design point). This is the '
        'operating point the motor is sized for.'),
    OPERATING_POINT_OPTIMUM_SEARCH: (
        'ADVISORY: the O/F ratio found by find_optimum_of_ratio, NOT the '
        'design point. Numbers in this tree describe a hypothetical motor '
        'at the Isp-optimal mixture ratio and differ from the design tree '
        'accordingly; the design O/F is NOT changed by this search.'),
    OPERATING_POINT_AS_REQUESTED: (
        'the O/F ratio passed to analyze_combustion by the caller; the '
        'caller did not declare which role this operating point plays.'),
}

#: ``compositions`` tarafının birimleri — denge çözücüsünün HAM SI çıktısı.
#: İstasyon tablosuyla aynı büyüklükleri taşır ama 1000 kat farklı tabanda;
#: bu sözlük o tabanı ADIYLA ilan eder.
_COMPOSITION_UNITS = {
    'enthalpy': 'J/kg',
    'entropy': 'J/(kg*K)',
    'cp': 'J/(kg*K)',
    'cv': 'J/(kg*K)',
    'gamma': '-',
    'molecular_weight': 'kg/kmol',
    'temperature': 'K',
    'density': 'kg/m^3',
}


# ---------------------------------------------------------------------------
# Optimum O/F arama önbelleği (v2.5.5 performans, davranış AYNI).
#
# find_optimum_of_ratio hibrit calculate() süresinin ~%85'idir (ölçüm:
# 630/730 ms — minimize_scalar 24+ denge çözümü tetikler). Arama, girdileri
# (yakıt bileşimi, oksitleyici, Pc, aralık, mekanizma) verilince
# DETERMİNİSTİKTİR: minimize_scalar 'bounded' sabit yol izler ve Cantera
# denge çözümü aynı girdiye aynı sonucu verir. Anahtar TAM değerlerle
# (yuvarlama YOK) kurulur; isabet yalnız birebir aynı girdide olur ve
# saklanan sonucun derin kopyası döner — çıktı bit-aynıdır. Modül
# seviyesindedir ki her isteğin yeni analizör kurduğu API yolunda art arda
# hesaplar (aynı yakıt/oksitleyici/Pc) aramayı yeniden ödemesin.
# ---------------------------------------------------------------------------
_OPTIMUM_OF_CACHE = {}
_OPTIMUM_OF_CACHE_MAX = 16

# Denge çözümü memoizasyonunun (CombustionAnalyzer.memoize) hücre üst sınırı.
# Faz 4B / bulgu A7: anahtar nicemlemesi kaldırıldığı için hücre sayısı artık
# yalnız BİREBİR aynı istekte paylaşılır ve bir üst sınır gerekir. Ölçülen en
# büyük gerçek iş yükü 25x25 = 625 noktalık Isp yüzeyidir
# (visualization._isp_surface_solve); bu sınır onun altı katından fazlasıdır.
EQUILIBRIUM_CACHE_MAX = 4096

# Cantera mekanizma zinciri: sırayla denenir, ilk YÜKLENEN kullanılır.
# Zincirin her basamağı gerçekten yüklenebilir bir mekanizma dosyasıdır ve
# başarısız her deneme loglanır (sessiz düşüş yok — bkz. __init__).
MECHANISM_CHAIN = ('gri30.yaml', 'h2o2.yaml')

# Adyabatik alev sıcaklığı kök aramasının parantezi [K].
# Alt uç: gri30 termo verisinin alt sınırı 200-300 K; 250 K altı hiçbir yanma
# probleminde anlamlı değildir. Üst uç: 5500 K, bilinen kimyasal itici
# çiftlerinin (H2/F2 dahil) adyabatik alev sıcaklıklarının üstündedir.
FLAME_T_BRACKET_K = (250.0, 5500.0)

# Alev sıcaklığı kök aramasının toleransları (brentq xtol [K], rtol [-]).
# v2.6.27'den beri aynı sayılar ``_estimate_flame_temperature`` içinde satır
# içi yazılıydı; V301/B7'de iki fazlı (gaz + C(gr)) ikinci kök araması da
# AYNI toleransı kullandığı için tek tanıma taşındı (değer aynı, bit-aynı).
FLAME_T_ROOT_XTOL_K = 1e-4
FLAME_T_ROOT_RTOL = 1e-10


# ---------------------------------------------------------------------------
# V301/B7 — YOĞUN FAZ KATI KARBON C(gr) (Ayberk tur 1 sonrası, makale 1)
# ---------------------------------------------------------------------------
# Kusur: gri30 yalnız GAZ fazı içerir. Yakıtça zengin N2O/HTPB'de (O/C < 1)
# dengede katı karbon çökmesi gerekirken karbon gaz türlerinde (C2H2, CH4,
# HCN ...) kalıyordu. ÖLÇÜLDÜ (20 Eki, HRMA'nın kendi CEA karşılaştırması,
# 20 bar): O/F 2,0'da Δc* −%6,73, ΔT_c −%11,49; 2,5'te −%4,64 / −%9,97.
# Ayrıntı ve önce/sonra: docs/scofield/raw/OH/V301/makale1/B7/RAPOR.md.
#
# Model (NASA RP-1311 Part I, Gordon & McBride 1994):
#   * Saf yoğun faz, kimyasal potansiyeli yalnız sıcaklığın işlevi:
#     μ_C(gr) = μ°_C(gr)(T)                                  (eş. 2.11, j > NG)
#   * Denge koşulu μ_j + Σ_i λ_i a_ij = 0 (eş. 2.10); yoğun türün dengeye
#     GİRME ölçütü, girişinin Gibbs enerjisini düşürmesidir (eş. 3.7). Bunun
#     karbon için karşılığı aktivite ölçütüdür:
#         ln a_C = (λ_C − μ°_C(gr)) / RT > 0
#     λ_C, gaz dengesinin karbon element potansiyelidir; μ_j = Σ_i a_ij λ_i
#     işaretiyle (eş. 2.10'daki çarpanın eksi işaretlisi) gaz türlerinin
#     kimyasal potansiyellerinden en küçük kareler ile çözülür. Eşik SIFIR
#     tanım gereğidir (a_C = 1 doymuşluk), ayarlanabilir sayı değildir.
#   * Durum denklemi PV = nRT, V ve n YALNIZ GAZA aittir, kütle tüm karışımın
#     kütlesidir; yoğun faz hacmi ihmal edilir (§2.2, eş. 2.1). Dolayısıyla
#     ρ = ρ_g/(1−ε), M = 1/n = M_g/(1−ε) (eş. 2.3a), h = Σ n_j H°_j (eş. 2.14).
#   * Donmuş karışım özellikleri Sutton & Biblarz 9. baskı §3.5 "Multiphase
#     Flow" (s. 84, eş. 3-35…3-39): V = V_g(1−β), R = (1−β)R_g,
#     k = [(1−β)c_p + βc_s]/[(1−β)c_v + βc_s]. Burada β = ε (yoğun kütle
#     kesri). Denge izentropik üssü RP-1311 eş. 2.71: γ_s = (∂lnP/∂lnρ)_s,
#     ses hızı eş. 2.74: a² = nRTγ_s = γ_s·P/ρ.
#
# Uygulama: iç içe tek boyutlu çözüm. Sabit T, P'de gaz karışımından ε kadar
# karbon çıkarılır ve mevcut SAĞLAM gaz dengesi (Cantera equilibrate('TP'))
# ile ln a_C(ε) = 0 köklenir (ε'da monoton azalan). Entalpi/entropi hedefli
# problemler (alev sıcaklığı, izentrop) bu TP çözümünün dışında T'de
# köklenir. Yoğun yol YALNIZ gaz dengesi aşırı doymuşsa devreye girer; aksi
# hâlde bütün yollar BİT-AYNI kalır (bekçi: tests/test_v301_yogun_karbon.py).
# Cantera MultiPhase (gaz + grafit) DENENDİ ve SEÇİLMEDİ (ölçüm RAPOR.md,
# 21 Eki): 'vcs' TP'de çalıştı ama HP ve SP'de CanteraError verdi; 'gibbs'
# O/F 2,5'te TP'de yakınsamadı, HP'de düştü, SP'de 7094-7652 K fiziksel
# olmayan sıcaklık döndürdü. Ayrıca graphite.yaml fazı sabit hacimli durum
# denklemi taşır (μ basınca bağlı), CEA'nın kabulü değil.

CONDENSED_PHASE_BASIS_TEXT = (
    'gas + pure condensed C(gr): density, molecular_weight (M = 1/n), '
    'enthalpy, entropy, cp and cv are mixture values per kg of mixture '
    '(condensed volume neglected, NASA RP-1311 Part I Sec. 2.2); species '
    'fractions are of the gas phase only')
"""İki fazlı istasyon bileşiminin künye metni (kullanıcıya görünür, İngilizce)."""

COMPOSITION_GAMMA_PRESSURE_PERTURBATION = 1.01
"""İstasyon bileşimindeki denge izentropik üssü n_s = dlnP/dlnρ|_s için
basınç pertürbasyonu (``_calculate_equilibrium_composition``). v2.x'ten beri
satır içi 1.01 idi; V301/B7 iki fazlı yolu da aynı sayıyı kullandığı için tek
tanıma taşındı (değer aynı, bit-aynı)."""

COMPOSITION_GAMMA_PHYSICAL_BAND = (1.05, 1.70)
"""n_s'in kabul bandı (dışındaysa donmuş c_p/c_v'ye düşülür). Satır içi
(1.05, 1.70) idi; aynı gerekçeyle tek tanıma taşındı (değer aynı)."""

CONDENSED_CARBON_SPECIES = 'C(gr)'
"""Dengeye kabul edilen tek yoğun tür (grafit)."""

CONDENSED_CARBON_THERMO_FILE = 'graphite.yaml'
"""C(gr) NASA-7 termo verisinin Cantera veri dosyası (NASA SP-273 / TM-4513;
dosyanın kendi künyesi). Yalnız TÜR termosu okunur: fazın sabit-hacim
durum denklemi KULLANILMAZ, çünkü RP-1311 eş. 2.11 yoğun türü basınçtan
bağımsız μ° ile alır (CEA ile aynı kabul)."""

CONDENSED_CARBON_LN_ACTIVITY_THRESHOLD = 0.0
"""Aşırı doymuşluk ölçütü ln a_C > 0 (RP-1311 eş. 3.7). Tanım: a_C = 1."""

CONDENSED_ELEMENT_POTENTIAL_X_FLOOR = 1e-10
"""Element potansiyeli en küçük kareler çözümüne giren türlerin mol kesri
tabanı. Bileşim yayınının tür tabanıyla AYNI sayı (``_calculate_equilibrium_
composition`` 'mole_fractions[i] > 1e-10'): tabanın altındaki türlerin
kimyasal potansiyeli Cantera'nın log(max(X, küçük)) kırpmasına yaklaşır ve
element potansiyelini bozar. Sayısal parametre, fizik değil."""

CONDENSED_EPS_UPPER_GAPS = (1e-3, 1e-6, 1e-9, 1e-12)
"""ε kökünün üst parantez adayları: ε_üst = Y_C·(1 − boşluk). Gaz karbonu
sıfıra yaklaştıkça ln a_C → −∞; ilk negatif aday parantezi kapatır.
Sayısal parametre."""

CONDENSED_EPS_WARM_BRACKET_REL = 1e-2
"""Sıcak başlangıçlı ε parantezinin bağıl genişliği (önceki çözümün
±%1'i). Yalnız hız içindir: parantez kapanmazsa tam parantezle çözülür."""

CONDENSED_EPS_XTOL_REL = 1e-13
"""ε kökünün mutlak toleransı, Y_C'ye göre bağıl. ε'daki 1e-13·Y_C hata
karışım entalpisine ~1e-6 J/kg yansır. Sayısal parametre."""

CONDENSED_T_ROOT_XTOL_REL = 1e-11
"""İki fazlı izentrop (s, P) çözümünde T kökünün bağıl toleransı. Denge ses
hızı 1e-3 basınç pertürbasyonuyla alınır; ρ'da 1e-11 hata n_s'e ~1e-8
yansır. Sayısal parametre."""

CONDENSED_T_WARM_BRACKET_REL = (0.02, 0.08, 0.3)
"""İki fazlı izentrop T kökü için tahmin etrafında denenen bağıl parantez
genişlikleri (genişleyerek). Sonuncusu da kapanmazsa
``FLAME_T_BRACKET_K`` tam parantezi kullanılır. Sayısal parametre."""

CONDENSED_SECANT_MAX_ITER = 8
"""İç (ε) ve dış (T) köklerde önce denenen PARANTEZSİZ kesen yönteminin
yineleme sınırı. Kesen sıcak başlangıçtan genellikle 3-5 adımda kapanır;
sınırda kapanmazsa ya da adım tanım aralığı dışına çıkarsa parantezli
brentq yoluna dönülür (sağlamlık ondan gelir). Yalnız hız parametresi."""

CONDENSED_LN_ACTIVITY_FTOL = 1e-11
"""İç kesen kabulü |ln a_C| ≤ 1e-11 ⇒ ε bağıl hatası ≲ 1e-12 (ölçülen eğim
d ln a_C / d ln ε ≈ −10, değer gürültüsü ~1e-14). Sayısal parametre."""

CONDENSED_ENTROPY_FTOL_REL = 1e-13
"""Dış kesen kabulü |s − s_0| ≤ 1e-13·|s_0| ⇒ T hatası ~1e-13·s_0·T/c_p
(≲ 1e-9 K). Sayısal parametre."""

CONDENSED_SECANT_FIRST_STEP_REL = (1e-3, 1e-4)
"""Kesenin ikinci noktası için bağıl adım: (ε için, T için). Hız parametresi."""

CONDENSED_FLAME_T_SECANT_STEP_REL = 0.05
"""İki fazlı alev sıcaklığı kesen denemesinde gaz-yalnız kökten bağıl ilk
adım (ölçülen iki fazlı yükselme +%2…+%14). Hız parametresi."""

CONDENSED_FROZEN_T_MAX_ITER = 40
"""Donmuş iki fazlı genişlemede (CEA nfz kipleri) sabit nokta yinelemesinin
üst sınırı. Daralma oranı ~ε·c_s/((1−ε)·c_p,g) ≈ 0,05: 12 adım 1e-15'e
iner, sınır yalnız patoloji korumasıdır."""


# ---------------------------------------------------------------------------
# Karışım oranı girdi kapısı (bebek-Scofield F4-5)
# ---------------------------------------------------------------------------
# ÖLÇÜM (17 Ağustos 2026, HEAD f9d95eb; htpb/N2O, Pc=20 bar):
#   analyze_combustion(..., of_ratio=-6.0, ...) TAM bir performans sonucu
#   döndürüyordu: equivalence_ratio = -1,4940, isp = 167,822 s ve
#   elemental_composition = {C: -0,1779, H: -0,0224, O: 0,4363, N: 0,7640}
#   — yani NEGATİF kütle kesirleri. of_ratio = -0,5 ise isp = 328,847 s
#   veriyordu, gerçek optimumun (231,7 s @ O/F=6) ÜSTÜNDE: kusur yalnız
#   anlamsız değil, kullanıcıyı iyimser yönde yanıltıyordu.
#   of_ratio = 0 ise ham ZeroDivisionError ile düşüyordu.
#
# BANDIN KAYNAĞI — tanımın kendisi (Sutton & Biblarz, "Rocket Propulsion
# Elements", 9. baskı, Böl. 6, karışım oranı tanımı: r = ṁ_oks / ṁ_yakıt).
# Bu iki debi de kütle akışıdır ve kütle akışı negatif olamaz; sıfır ise
# ortada oranlanacak bir akış yoktur. Dolayısıyla geçerli bant SONLU ve
# KESİN POZİTİF sayılardır. ÜST sınır BİLEREK konmadı: yayımlanmış,
# yakıt-oksitleyici çiftinden bağımsız bir üst kesme değeri yoktur ve
# uydurma bir tavan (ör. "10") bu deponun yasakladığı sahte sabit olurdu.
# Aşırı oksitleyici-zengin bölge fizikte anlamlıdır (yanma zayıflar), model
# de orada çalışmaya devam eder.
#: Karışım oranının tanım gereği geçerli bandı (alt sınır DIŞLAYICI).
OF_RATIO_MIN_EXCLUSIVE = 0.0


# ---------------------------------------------------------------------------
# Oda basıncı / oda sıcaklığı girdi kapısı (ÖH D16, kalem B3-08)
# ---------------------------------------------------------------------------
# ÖLÇÜM (1 Eylül 2026, taban 6fde52b; htpb/N2O, O/F=6):
#   chamber_pressure = -20.0  -> TAM sonuç yayımlandı: T_oda = 2132,0359 K,
#     BOĞAZ BASINCI = -11,118412 bar (negatif MUTLAK basınç), oda yoğunluğu
#     = -2,969325 kg/m³, c* = 1249,0271, isp = nan.
#   chamber_pressure = nan    -> her yaprak nan (T, P_boğaz, c*, isp).
#   chamber_pressure = inf    -> her yaprak inf.
#   chamber_pressure = 0.0    -> ham ZeroDivisionError (temiz hata değil).
#   chamber_temperature = -500.0 -> TAM sonuç: T_boğaz = -429,1845 K,
#     oda yoğunluğu = -12,661414 kg/m³ (mutlak sıfırın ALTINDA sıcaklık).
#   chamber_temperature = 0.0 -> ham ZeroDivisionError.
#   chamber_temperature = nan -> her yaprak nan.
# Aynı fonksiyonun of_ratio kapısı (F4-5) bu vakaların hepsini kendi alanı
# için zaten reddediyordu; kapının kendi metni "no combustion result is
# produced from an unreadable value" diyor. Aynı ilke Pc/T_c'ye uygulanmamıştı.
#
# BANDIN KAYNAĞI — TANIMIN KENDİSİ, uydurma eşik değil:
#   * Oda basıncı MUTLAK basınçtır (Sutton & Biblarz, "Rocket Propulsion
#     Elements", 9. baskı, Böl. 3: izentropik bağıntılar p_c/p_t mutlak
#     basınç oranıdır). Mutlak basınç tanım gereği negatif olamaz; sıfır ise
#     ortada genişletilecek bir gaz yoktur ve p_c/p_t oranı tanımsızdır.
#   * Oda sıcaklığı MUTLAK (Kelvin) sıcaklıktır. Termodinamiğin üçüncü yasası
#     gereği mutlak sıfırın altı yoktur; T = 0 K'de ρ = p/(R·T) tanımsızdır.
# ÜST SINIR BİLEREK KONMADI: yayımlanmış, itici çiftinden bağımsız bir üst
# kesme değeri yoktur; uydurma bir tavan bu deponun yasakladığı sahte sabit
# olurdu. (FLAME_T_BRACKET_K bir ÇÖZÜCÜ parantezidir, girdi kapısı değildir.)
#: Oda basıncının tanım gereği geçerli bandı (alt sınır DIŞLAYICI, bar).
CHAMBER_PRESSURE_MIN_EXCLUSIVE_BAR = 0.0
#: Oda sıcaklığının tanım gereği geçerli bandı (alt sınır DIŞLAYICI, K).
CHAMBER_TEMPERATURE_MIN_EXCLUSIVE_K = 0.0


def _dogrula_sonlu_pozitif(deger, alan_adi, birim, alt_sinir, gerekce):
    """``deger``i sonlu ve ``alt_sinir``dan BÜYÜK olarak doğrular.

    Kapı ``of_ratio`` kapısıyla (F4-5) aynı desendedir: okunamayan, sonsuz
    ya da banda düşmeyen girdiden KISMİ SONUÇ YAYIMLANMAZ; ``ValueError``
    yükselir ve çağıran uç bunu alan adıyla 422'ye çevirir.
    """
    try:
        sayi = float(deger)
    except (TypeError, ValueError):
        raise ValueError(
            f"{alan_adi} must be a finite number in {birim} "
            f"(got {deger!r}); no combustion result is produced from an "
            f"unreadable value")
    if not np.isfinite(sayi):
        raise ValueError(
            f"{alan_adi} must be finite (got {sayi!r}); a non-finite value "
            f"is not a measurement and every leaf of the combustion result "
            f"would inherit it")
    if sayi <= alt_sinir:
        raise ValueError(
            f"{alan_adi} must be greater than {alt_sinir} {birim} "
            f"(got {sayi!r}). {gerekce}")
    return sayi


def _dogrula_oda_basinci(chamber_pressure):
    """Oda basıncını sonlu-pozitif (mutlak, bar) olarak doğrular."""
    return _dogrula_sonlu_pozitif(
        chamber_pressure, 'chamber_pressure', 'bar',
        CHAMBER_PRESSURE_MIN_EXCLUSIVE_BAR,
        "Chamber pressure is an ABSOLUTE pressure (Sutton & Biblarz 9th ed., "
        "Ch. 3: p_c/p_t is a ratio of absolute pressures); a non-positive "
        "absolute pressure has no physical meaning and previously produced a "
        "negative absolute throat pressure and a negative gas density.")


def _dogrula_oda_sicakligi(chamber_temperature):
    """Oda sıcaklığını sonlu-pozitif (mutlak, K) olarak doğrular."""
    return _dogrula_sonlu_pozitif(
        chamber_temperature, 'chamber_temperature', 'K',
        CHAMBER_TEMPERATURE_MIN_EXCLUSIVE_K,
        "Chamber temperature is an ABSOLUTE (Kelvin) temperature; nothing "
        "exists below absolute zero and rho = p/(R*T) is undefined at T = 0. "
        "A non-positive value previously produced a negative absolute throat "
        "temperature and a negative gas density.")


def _dogrula_karisim_orani(of_ratio):
    """``of_ratio``yu sonlu-pozitif olarak doğrular; değilse ``ValueError``.

    Kapı gerekçesi ve ölçümü ``OF_RATIO_MIN_EXCLUSIVE`` künyesindedir.
    """
    try:
        deger = float(of_ratio)
    except (TypeError, ValueError):
        raise ValueError(
            f"of_ratio must be a finite positive number (got {of_ratio!r}); "
            f"it is the ratio of two mass flows and no combustion result is "
            f"produced from an unreadable value")
    if not np.isfinite(deger):
        raise ValueError(
            f"of_ratio must be finite (got {deger!r}); a non-finite mixture "
            f"ratio is not a measurement and no combustion result is "
            f"produced from it")
    if deger <= OF_RATIO_MIN_EXCLUSIVE:
        raise ValueError(
            f"of_ratio must be greater than {OF_RATIO_MIN_EXCLUSIVE} "
            f"(got {deger!r}). O/F is the oxidiser-to-fuel MASS ratio "
            f"(Sutton & Biblarz 9th ed., Ch. 6); a non-positive value has no "
            f"physical meaning and previously produced negative elemental "
            f"mass fractions and a negative equivalence ratio.")
    return deger


# --- ÖH D18 fizik-a1 / F1 (B3-05 + B3-02): kayan-denge istasyon çözücüsü ---
# Sektör pratiği (NASA RP-1311 Part I §6.2.2 ve §6.3.3; RPA v2.3 kılavuzu
# s.19): oda ve boğaz HER ZAMAN kimyasal denge (c* ve ṁ oradan gelir),
# boğaz→çıkış referans genişleme "kayan denge" (shifting equilibrium).
# Tek-γ izentropik bağıntı yalnız profil/ön tahmin içindir.
#
# Aşağıdaki sabitler çözücünün SAYISAL parametreleridir (fiziksel model
# değil); tek kaynak burasıdır, çözücü dışında kullanılmazlar.
EQ_STATION_SONIC_BRACKET = (0.30, 0.95)
"""Boğaz basınç oranı p_t/p_c için güvenli arama aralığı.

Tek-γ kritik oran 1,10 ≤ γ ≤ 1,40 için 0,528…0,581 arasındadır; kayan
dengede sapma %2 mertebesindedir, dolayısıyla bu aralık her yanma gazını
rahatça kapsar (P01 ``B3-repro-08.py`` aynı aralığı kullanıyordu).
"""

EQ_STATION_SOUND_SPEED_PERTURBATION = 1.001
"""Denge ses hızı için basınç pertürbasyonu: n_s = dlnP/dlnρ|_s,eq.

a_eq = sqrt(n_s·P/ρ). Donmuş γ değil DENGE üsteli kullanılır (RP-1311
§6.3.3): ayrışan türlerin yeniden birleşmesi ses hızını düşürür.
"""

EQ_STATION_PARABOLIC_STEPS = (0.01, 0.001)
"""Boğaz (maksimum kütle akısı) tepe aramasında bağıl adım dizisi.

Boğaz koşulu v = a_eq ile G = ρ·v maksimumu ÖZDEŞTİR (RP-1311 §6.3.3:
A/A_t minimumu ⇔ u = a). G(p) tepe civarında düzgün ve kuadratiktir, bu
yüzden üç noktalı parabol tepe kestirimi kullanılır: her tur 3 denge
çözümü. Tek-γ kritik orandan başlanır (bağıl hata ~%2), iki tur yeter —
ÖLÇÜLDÜ: sonik artık |v/a − 1| ≈ 2e-6 (bkz. ``sonic_residual``, yanıtta
beyan edilir). G tepe noktasında düz olduğundan p_t'deki 1e-6 hata c*'a
O(1e-12) yansır. (Kök arama yerine tepe araması
seçildi: a_eq'nun kendisi ikinci bir denge çözümü ister, tepe araması
çağrı başına maliyeti yarıya indirir.)
"""

EQ_STATION_EXIT_SECANT_MAX_ITER = 24
"""ε → p_e kesen (secant) çözümünde üst yineleme sınırı."""

EQ_STATION_EXIT_REL_TOL = 1e-10
"""ε → p_e çözümünün bağıl kapanış ölçütü (|ε_hesap/ε_hedef − 1|)."""

EQ_STATION_EXIT_PRESSURE_FLOOR_PA = 1.0
"""ε çözümünde çıkış basıncı tabanı [Pa] (~1e-5 bar).

``_exit_pressure_from_expansion`` içindeki 1e-6 bar tabanıyla aynı
gerekçe: mutlak sıfır basınç log/oran alan tüketicileri bozar.
"""

EQ_STATION_CACHE_MAX = 64
"""Boğaz çözümü önbelleğinin üst sınırı (FIFO).

Anahtar NİCEMLENMEZ (tam float): D16'da nicemlenmiş anahtar "kullanıcı
girdiyi değiştiriyor, cevap değişmiyor" kusurunu doğurmuştu.
"""


def _eps_ongoru(gecmis, T: float, varsayilan: Optional[float]) -> Optional[float]:
    """Dış kökte sıradaki T için ε sıcak başlangıcı: son iki (T, ε>0)
    noktasından ln ε'da doğrusal öngörü (yalnız hız; kök ipucundan
    bağımsızdır). Yeterli geçmiş yoksa ``varsayilan``."""
    if len(gecmis) >= 2:
        (T1, e1), (T2, e2) = gecmis[-2], gecmis[-1]
        if T2 != T1:
            ln_e = np.log(e2) + (np.log(e2) - np.log(e1)) * (T - T2) / (T2 - T1)
            if np.isfinite(ln_e):
                return float(np.exp(ln_e))
    return varsayilan


def _sekant_dene(f, x0: float, f0: float, x1: float, alt: float, ust: float,
                 xtol: float, ftol: float = 0.0,
                 max_iter: int = CONDENSED_SECANT_MAX_ITER):
    """Parantezsiz kesen (secant) denemesi — V301/B7 iki fazlı çözücü hızı.

    Kök bulunursa SON DEĞERLENDİRİLEN nokta döner (çağıranın değer belleğinde
    durumu vardır); adım (alt, ust) dışına çıkarsa, eğim sıfırlanırsa ya da
    ``max_iter`` adımda kapanmazsa None döner ve çağıran parantezli brentq
    yoluna geçer. Kabul: |f(x_k)| ≤ ftol ya da |x_{k+1} − x_k| ≤ xtol
    (kesen adımı köke uzaklığın kestirimidir).
    """
    if abs(f0) <= ftol:
        return x0
    f1 = f(x1)
    for _ in range(max_iter):
        if abs(f1) <= ftol:
            return x1
        if not np.isfinite(f1) or f1 == f0:
            return None
        x2 = x1 - f1 * (x1 - x0) / (f1 - f0)
        if not (np.isfinite(x2) and alt < x2 < ust):
            return None
        if abs(x2 - x1) <= xtol:
            return x1
        x0, f0 = x1, f1
        x1, f1 = x2, f(x2)
    return None


class CombustionAnalyzer:
    """Advanced combustion analysis with chemical equilibrium"""

    def __init__(self, memoize=False):
        # Gas constant (CODATA 2018) - merkezi sabit modulunden
        self.R_universal = R_UNIVERSAL  # J/(kmol·K)

        # Denge çözümü memoizasyonu (v2.5.0 UQ, ARGE spec 6.2): memoize=True
        # iken analyze_combustion sonuçları instance ömürlü önbelleğe alınır.
        #
        # Faz 4B (bulgu A7): anahtar artık TAM değerlerle kurulur. Eski anahtar
        # O/F'yi 0.01'e, Pc'yi 0.1 bar'a, T'yi 0.1 K'e, ε'yu 0.01'e NİCEMLİYORDU
        # ve bu, birbirinden fiziksel olarak AYRI istekleri aynı hücreye
        # düşürüyordu. Gerekçe ve ölçüm analyze_combustion içindeki anahtar
        # bloğunda yazılıdır.
        #
        # Üst sınır: tam anahtar, nicemli anahtardan daha çok hücre üretebilir
        # (yalnız birebir aynı istek isabet eder), bu yüzden önbellek artık
        # sınırlıdır. Aynı dosyadaki _OPTIMUM_OF_CACHE ile aynı desen: sınır
        # aşılınca en eski kayıt düşer (FIFO). 4096 hücre, ölçülen en büyük iş
        # yükünün (25x25 = 625 noktalık Isp yüzeyi) altı katından fazladır.
        self.memoize = bool(memoize)
        self._equilibrium_cache = {}
        self._equilibrium_cache_max = EQUILIBRIUM_CACHE_MAX

        # Cantera gaz objesi.
        # _mechanism_id: yüklenen mekanizmanın kimliği — optimum O/F önbellek
        # anahtarına girer (farklı mekanizma = farklı sonuç uzayı) ve analiz
        # sonucunda kullanıcıya BEYAN edilir ('mechanism').
        #
        # v2.6.27 — ÖLÜ DAL KALDIRILDI. Zincirin ilk basamağı Cantera'nın NASA
        # tür veritabanı YAML'ını ct.Solution ile açmayı deniyordu (dosya adı
        # bilerek yazılmıyor: bekçi testi o dizgenin bu dosyada kalmadığını
        # denetler). O dosya bir TÜR veritabanıdır — 'phases:' bölümü yoktur,
        # dolayısıyla Solution olarak HİÇBİR koşulda yüklenemez; ölçüldü,
        # CanteraError ile düşüyor. Dal SESSİZ bir except'in ardında
        # gizlendiğinden kod "önce NASA-CEA veritabanını dene" diyordu ama
        # gerçekte HER ZAMAN gri30 kullanılıyordu. Aynı eleme kinetik modülde
        # zaten bilinçliydi (hrma/analysis/kinetic_efficiency.py reaksiyonsuz
        # termo dosyalarını eler). Kalan her düşüş artık loglanır.
        self.gas = None
        self.cantera_available = False
        self._mechanism_id = 'empirical'
        self._mechanism_T_ceiling_K = None
        # ÖH D18 F1: boğaz (kayan-denge sonik nokta) çözümü önbelleği.
        # Anahtar (bileşim dizgesi, T_c, P_c) TAM float'tır; ε ve çıkış
        # basıncı anahtara GİRMEZ çünkü boğaz onlardan bağımsızdır — ε
        # taraması ve irtifa taraması aynı izentropu yeniden çözmez.
        self._eq_station_cache = {}
        # V301/B7: yoğun faz C(gr) verisi (gri30 kurulunca doldurulur).
        # None ise karbonca aşırı doymuş dengeler çözülemez; bu durum analiz
        # sonucunda 'condensed_phases' ile BEYAN edilir (sessiz düşüş yok).
        self._yk = None
        self._yk_neden = 'cantera_unavailable'
        self._yk_ipucu = None
        self._yk_eps_ipucu = None
        if CANTERA_AVAILABLE:
            for mech_file in MECHANISM_CHAIN:
                try:
                    self.gas = ct.Solution(mech_file)
                    self.cantera_available = True
                    self._mechanism_id = mech_file.split('.')[0]
                    break
                except Exception as exc:
                    logger.warning(
                        "Cantera mekanizması '%s' yüklenemedi (%s); zincirdeki "
                        "sıradaki mekanizma denenecek.", mech_file, exc)
            if self.cantera_available:
                self._mechanism_T_ceiling_K = self._mechanism_temperature_ceiling()
                self._yk, self._yk_neden = self._yogun_karbon_kur()
            else:
                logger.warning(
                    "Zincirdeki hiçbir Cantera mekanizması yüklenemedi (%s); "
                    "CombustionAnalyzer ampirik modellerle çalışacak.",
                    ", ".join(MECHANISM_CHAIN))
        else:
            logger.warning("Cantera kurulu değil; CombustionAnalyzer ampirik modellerle çalışacak.")
        
        # N2O/HTPB hibrit roket için özel propellant tanımları
        #
        # ÖH D16 / OH-Z1-01 — ``density_liquid`` ARTIK YOĞUNLUK KANALI DEĞİL.
        # Bu sözlükten yalnız ``enthalpy_formation`` ve ``molecular_weight``
        # okunuyor (ölçüldü: ``raw/OH/D16/sivi/a1/once.json``, depoda
        # ``density_liquid`` için TEK ÜRÜN SİTESİ bu iki tanım satırıydı,
        # tüketicisi 0). N2O satırındaki 1220 kg/m³ ise "20 °C" etiketiyle
        # duruyordu ve o sayı N₂O'nun NORMAL KAYNAMA NOKTASI (184,67 K ≈
        # −88 °C) değeridir; 20 °C'deki doymuş sıvı yoğunluğu 785,10 kg/m³
        # (+%55,4 hata). Yani ölü alan yanlış bir sayı ÖĞRETİYORDU.
        # Kardeş sözlükte (``data/external_data_fetcher._initialize_backup_
        # data``) aynı kusur Z1'de AYNI biçimde kapatıldı: anahtar KORUNUR
        # (şekil bozulmasın), değeri ``None`` olur, künyesi "tüketilmiyor"
        # der. Yoğunluk TEK KAYNAKTAN gelir:
        # ``data.external_data_fetcher.oxidizer_reference_density``.
        #
        # Kitap uyum B16 (Ö-1, §28; 6 Eki 2026) — N₂O GİRİŞ DURUMU.
        # Aşağıdaki 'n2o' ``enthalpy_formation`` alanı GAZ referansıdır
        # (298,15 K ideal gaz, +82,05 kJ/mol; durum etiketi
        # ``propellant_database.N2O_ENTHALPY_FORMATION_STATE``) ve artık
        # depodaki TEK TANIMA bağlıdır (``propellant_database.
        # N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL``; eskiden burada ikinci bir
        # 82.05 literali vardı). HP dengesine giren değer bu alan DEĞİL,
        # giriş durumundan türetilen atanmış entalpidir (RP-1311 §4.1;
        # ``hrma/engines/oxidizer_inlet.py``; ``_calculate_reactant_enthalpy``
        # N₂O dalı). Giriş durumu ``set_oxidizer_inlet_state`` ile verilir;
        # verilmezse varsayılan 293,15 K doymuş sıvıdır (hibrit
        # ``TANK_TEMPERATURE_DEFAULT_K``, tek kaynak).
        from hrma.engines.oxidizer_inlet import (
            N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL as _N2O_HF_GAZ)
        # None = varsayılan giriş durumu. Denge önbelleği giriş durumu başına
        # AYRI tutulur (``set_oxidizer_inlet_state``): aynı istek iki farklı
        # giriş entalpisiyle sorulursa bayat sonuç DÖNMEZ.
        self._oxidizer_inlet_signature = None
        self._oxidizer_inlet_request = (None, None)
        self._equilibrium_caches_by_inlet = {None: self._equilibrium_cache}
        self.propellant_specs = {
            'n2o': {
                'formula': 'N2O',
                'molecular_weight': 44.013,  # g/mol
                'density_liquid': None,  # TÜKETİLMİYOR (bkz. yukarıdaki not)
                'enthalpy_formation': _N2O_HF_GAZ  # kJ/mol — GAZ, 298,15 K
            },
            # D15/P1B3-03 — SIVI oksijenin kriyojenik entalpisi. TEK KAYNAK:
            # bu satır. NASA CEA'nın kendi LOX kartı (RocketCEA
            # input_cards.py, 'LOX'): "oxid O2(L) O 2 / h,cal=-3102.
            # t(k)=90.18 wt%=100." -> -3102 cal/mol x 4,184 J/cal
            # = -12 978,768 J/mol = -12,978768 kJ/mol (= -405,60 kJ/kg).
            # Gaz O2 için Hf = 0 (298,15 K referans hali) DOĞRUDUR ve ayrı
            # daldadır; sıvı oksijeni gaz referansıyla yakmak, buharlaşma
            # ısısını bedava enerji olarak sayar.
            'lox': {
                'formula': 'O2',
                'molecular_weight': 31.9988,  # g/mol
                'density_liquid': None,  # TÜKETİLMİYOR (bkz. yukarıdaki not)
                'enthalpy_formation': -12.978768  # kJ/mol (CEA O2(L) kartı)
            },
            'htpb': {
                'formula': 'C4H6',  # Simplified HTPB monomer
                # ÖH D19 (kalem B3-12): elle yazılı 54.09 KALKTI, yukarıdaki
                # 'formula' alanından türetiliyor (54.092 g/mol). Aynı dosyada
                # HTPB üç ayrı ağırlıkla yazılıydı (54.09 / 54.0 / 54.0).
                'molecular_weight': self._formula_molar_mass('htpb'),
                # ÖH D20 / P15B2-08 (Fable-D17 ŞARTI): dört tüketicinin
                # DÖRDÜ de merkezi kayıttan okur; çıplak literal kalmaz.
                'density': _FUEL_RHO['htpb'],  # kg/m³
                # CEA R-45 HTPB kartı (RocketCEA 'HTPB' FROM_RPL_DATA):
                # +1200 cal/100 g = +50.2 kJ/kg -> C4H6 birimi başına +2.7 kJ/mol.
                # Eski -125.0 kJ/mol '(estimated)' değeri -2311 kJ/kg demekti ve
                # yakıt-zengin bölgede T_c'yi ~300 K, c*'ı %4-10 düşük veriyordu
                # (2026-07-18 korelasyon fizik incelemesi). Kürlenmiş HTPB/IPDI
                # için literatür biraz daha negatiftir (~-0.3..-0.5 MJ/kg);
                # CEA kartı referans alındı ki CEA çapraz-doğrulaması tutarlı olsun.
                'enthalpy_formation': 2.7  # kJ/mol (CEA R-45 kartı, +50 kJ/kg)
            },
            'paraffin': {
                'formula': 'C12H26',  # Typical paraffin wax
                'molecular_weight': 170.33,  # g/mol
                'density': _FUEL_RHO['paraffin'],  # kg/m³
                # NIST WebBook: n-dodekan(l) ΔHf° = -350.9 kJ/mol. Eski -290.0
                # değeri kaynaksızdı ve karışımı ~%1-1.5 fazla enerjik yapıyordu.
                'enthalpy_formation': -350.9  # kJ/mol (NIST, n-dodekan sıvı)
            },
            # Aşağıdaki polimer ΔHf° değerleri KATI faz, tekrar birimi başına
            # (kJ/mol). Monomer-gaz değerleriyle KARIŞTIRILMAMALIDIR (ör. etilen
            # gazı +52 kJ/mol ama katı PE -54 kJ/mol). Değerler monomer ΔHf° +
            # polimerleşme ısısı yolundan türetilip yanma ısısı (HHV) kalorimetri
            # verisiyle %0-2 içinde çapraz-doğrulandı (Polymer Handbook; NIST).
            'pe': {
                'formula': 'C2H4',  # Polietilen tekrar birimi
                'molecular_weight': 28.05,  # g/mol
                # ÖH D17 / P15B2-08: bu alan TÜKETİLMİYOR (denge çözümü
                # yoğunluğu Cantera'dan alır) ama aynı adla üçüncü bir
                # sayı taşıyordu (940 ⟷ 950 ⟷ 960). Tek kaynağa bağlandı.
                'density': _FUEL_RHO['pe'],  # kg/m³ (HDPE)
                'enthalpy_formation': -54.3  # kJ/mol (katı PE; NBS bomba kal. / CEA deck std)
            },
            'pmma': {
                'formula': 'C5H8O2',  # PMMA tekrar birimi
                'molecular_weight': 100.12,  # g/mol
                'density': _FUEL_RHO['pmma'],  # kg/m³
                'enthalpy_formation': -446.3  # kJ/mol (MMA(l) -388.8 + polimerleşme -57.5)
            },
            'abs': {
                'formula': 'C8H8',  # Kodun ABS yaklaşımı (~stiren); ΔHf° polistiren değeri
                'molecular_weight': 104.15,  # g/mol
                'density': _FUEL_RHO['abs'],  # kg/m³
                'enthalpy_formation': 33.8  # kJ/mol (amorf PS; stiren(l) +103.8 + polim. -70.0)
            },
            'pla': {
                'formula': 'C3H4O2',  # PLA tekrar birimi
                'molecular_weight': 72.06,  # g/mol
                # ÖH D20 / OH-D19-10: aynı sayı, ama artık merkezi
                # kaynaklı kayıttan; motor tarafındaki 1250 düştü.
                'density': _FUEL_RHO['pla'],  # kg/m³
                'enthalpy_formation': -409.6  # kJ/mol (laktid(s) -792.0 üzerinden ROP)
            }
        }
        
        # Standart oluşum entalpileri (kJ/mol), 298 K. KULLANILMIYOR (ölü
        # veri). KU H-13 / KITAP-2a H5 (6 Eki 2026) — eski yorum "NIST-JANAF
        # güncel değerleri" diyordu; YANLIŞ. Değerler karışık kökenlidir ve
        # JANAF 4. baskı (Chase 1998) ile birebir değildir: ör. OH 39,46 ⟷
        # JANAF 4. bs. 38,99 (KITAP-2a notu) ⟷ RocketCEA thermo.inp 37,278
        # (Ruscic 2002; yerelde okundu). ÖLÇÜLDÜ (taban 9842af22): depoda bu
        # özniteliği okuyan satır YOK (grep: yalnız bu tanım) ve hibrit + sıvı
        # örnek projeler FORM yoluyla koşulurken 3 CombustionAnalyzer
        # örneğinde 0 erişim (erişim sayan sözlükle). Motor sayıları
        # RocketCEA/CEA kartlarından ve ``propellant_specs``ten gelir. Silme
        # kararı ayrı kalemdir (sözlük bu kulvarın satır bölgesini aşıyor).
        self.species_data = {
            # Major combustion products (çoğu JANAF değeriyle aynı; künyesiz)
            'CO2': {'Hf': -393.522, 'MW': 44.0095, 'phase': 'gas'},
            'CO': {'Hf': -110.527, 'MW': 28.0101, 'phase': 'gas'},
            'H2O': {'Hf': -241.826, 'MW': 18.01528, 'phase': 'gas'},
            'H2': {'Hf': 0.0, 'MW': 2.01588, 'phase': 'gas'},
            'N2': {'Hf': 0.0, 'MW': 28.0134, 'phase': 'gas'},
            'O2': {'Hf': 0.0, 'MW': 31.9988, 'phase': 'gas'},
            'OH': {'Hf': 39.46, 'MW': 17.01, 'phase': 'gas'},
            'H': {'Hf': 217.97, 'MW': 1.01, 'phase': 'gas'},
            'O': {'Hf': 249.17, 'MW': 16.00, 'phase': 'gas'},
            'NO': {'Hf': 90.25, 'MW': 30.01, 'phase': 'gas'},
            'NO2': {'Hf': 33.18, 'MW': 46.01, 'phase': 'gas'},
            
            # Condensed phases
            'AL2O3_s': {'Hf': -1675.7, 'MW': 101.96, 'phase': 'solid'},
            'AL2O3_l': {'Hf': -1582.0, 'MW': 101.96, 'phase': 'liquid'},
            'C_s': {'Hf': 0.0, 'MW': 12.01, 'phase': 'solid'},
            
            # Fuel components (propellant_specs ile aynı kaynaklar)
            'C12H26': {'Hf': -350.9, 'MW': 170.33, 'phase': 'liquid'},  # NIST n-dodekan(l)
            'AL': {'Hf': 0.0, 'MW': 26.98, 'phase': 'solid'},
            # ÖH D19 (kalem B3-12): elle yazılı 54.0 KALKTI — aynı C4H6
            # birimi, aynı tek kaynak (propellant_specs ile birebir aynı sayı).
            'HTPB': {'Hf': 2.7, 'MW': self._formula_molar_mass('htpb'),
                     'phase': 'solid'},  # CEA R-45 kartı (C4H6 birimi)
        }

    def _mechanism_temperature_ceiling(self) -> Optional[float]:
        """Yüklü mekanizmanın termo verisinin güvenli üst sıcaklığı [K].

        NASA polinomları TÜR BAŞINA bir geçerlilik aralığıyla gelir; karışımın
        tamamı için güvenli tavan, türler arasındaki EN DÜŞÜK üst sınırdır.
        Ölçüldü (Cantera 3.1.0): gri30 -> 3000 K (tavanı belirleyen tür CH3O),
        h2o2 -> 3500 K. Oda sıcaklığı bu tavanın üstüne çıktığında denge
        çözümü NASA polinomlarını EKSTRAPOLE eder (Cantera "outside valid
        range" uyarısı basar; çözüm yine yakınsar, sapma küçüktür — bkz.
        _calculate_equilibrium_composition içindeki SP pertürbasyon notu).
        Bu bilinçli kabul kullanıcıdan gizlenmez: değer analiz sonucunda
        'mechanism_T_ceiling_K' alanıyla BEYAN edilir.
        """
        try:
            return float(min(sp.thermo.max_temp for sp in self.gas.species()))
        except Exception as exc:
            logger.warning(
                "Mekanizma sıcaklık tavanı okunamadı (%s); beyan boş kalacak.",
                exc)
            return None

    def analyze_combustion(self, fuel_composition: Dict, oxidizer_type: str,
                          of_ratio: float, chamber_pressure: float,
                          chamber_temperature: float = None,
                          eta_c_star: Optional[float] = None,
                          expansion_ratio: Optional[float] = None,
                          operating_point: Optional[str] = None,
                          *, c_star_only: bool = False) -> Dict:
        """
        Comprehensive combustion analysis

        ``c_star_only=True`` (V301/B7 ardılı, 21 Eki — HIZ): yalnız denge c*'ı
        gereken çağıranlar için (hibrit c*(O/F) ızgarası ve ara değerleme
        tanısı yalnız ``performance['c_star']`` okur). Alev sıcaklığı, oda
        bileşimi ve kayan-denge BOĞAZ istasyonu aynen çözülür; boğaz/çıkış
        bileşimi, çıkış istasyonu ve Isp'ler atlanır. c* tam yolla BİT-AYNIDIR
        (aynı aşamalar, aşamalar ipucu taşımadan başlar). Denge boğazı
        çözülemezse (Cantera yok / ıraksama) kısayol kullanılmaz, tam yol
        koşar. Dönen sözlük ``c_star_only: True`` ile işaretlidir.

        Args:
            fuel_composition: {'formula': percentage} dict
            oxidizer_type: 'N2O', 'LOX', etc.
            of_ratio: Oxidizer/Fuel mass ratio
            chamber_pressure: Chamber pressure in bar
            chamber_temperature: Optional chamber temperature in K
            eta_c_star: Opsiyonel c* (yanma) verimi. None => teorik (ideal denge)
                varsayımı korunur. Verilirse performance['c_star_delivered'] =
                eta_c_star * c_star_teorik olarak raporlanır; teorik
                performance['c_star'] DEĞİŞMEZ. Gerçek hibrit motorlarda
                ölçülen c* verimi tipik olarak 0.90-0.97'dir (eksik karışma,
                sonlu kalış süresi, duvar ısı kaybı; Chiaverini & Kuo,
                "Fundamentals of Hybrid Rocket Combustion and Propulsion",
                AIAA Prog. Astro. & Aero. Vol. 218, 2007, Bölüm 1 ve 10;
                ayrıca Sutton & Biblarz 9. baskı, Eş. 3-31 c*-verimi tanımı).
            expansion_ratio: Opsiyonel lüle alan oranı ε = Ae/At. VERİLİRSE
                çıkış istasyonu (p_e, T_e, bileşim, isp, cf) bu ε'dan
                izentropik alan-Mach bağıntısıyla çözülür (Sutton & Biblarz
                9. baskı, Eş. 3-14). Verilmezse çıkış istasyonu ISA deniz
                seviyesi basıncına (1.01325 bar) çapalanır ve sonuç sözlüğünde
                conditions['exit']['basis'] = 'sea_level_default' olarak
                işaretlenir. (v2.6.2 öncesi bu değer SABİT 1.0 bar idi ve
                motorun gerçek ε'sını hiç görmüyordu — bulgu F034.)

        Returns:
            Complete combustion analysis results

        Raises:
            ValueError: ``of_ratio`` sonlu-pozitif değilse (F4-5 kapısı,
                bkz. ``OF_RATIO_MIN_EXCLUSIVE``). Kısmi sonuç YAYIMLANMAZ:
                elemental bileşimden eşdeğerlik oranına kadar her yaprak bu
                orandan türer.
            ValueError: ``chamber_pressure`` sonlu-pozitif (mutlak, bar)
                değilse ya da verilmişse ``chamber_temperature`` sonlu-pozitif
                (mutlak, K) değilse — ÖH D16 kalemi B3-08; bkz.
                ``CHAMBER_PRESSURE_MIN_EXCLUSIVE_BAR`` ve
                ``CHAMBER_TEMPERATURE_MIN_EXCLUSIVE_K``. Kapıdan önce bu
                girdiler negatif MUTLAK boğaz basıncı, mutlak sıfır altı
                boğaz sıcaklığı ve negatif gaz yoğunluğu yayımlıyordu.
        """
        # --- GİRDİ KAPISI (F4-5 + ÖH D16 B3-08) — anahtar kurulmadan ÖNCE -
        # V301/B7 ardılı (21 Eki) — ÇAĞRI DÜZEYİNDE BELİRLENİMCİLİK. İki fazlı
        # (gaz + C(gr)) kökler sıcak başlangıçla çözülür ve ipuçları analizör
        # nesnesinde tutulur. İpucu bir ÖNCEKİ çağrıdan kalırsa toleranslı kök
        # başka bir noktada durur ve aynı girdi çağrı geçmişine göre ~1e-13
        # bağıl farklı çıkar. ÖLÇÜLDÜ (D15 sağlıklı hibrit, O/F 2,5): yayımlanan
        # (γ, M, T) üçlüsünün kapalı form c*'ı motorun c*_tek-γ'sından
        # 1,375e-13 farklıydı ve yarı-1B kütle debisi çapraz denetimi bu
        # gürültüyü 'divergent' sayıyordu (gaz-yalnız yolda artık 1e-16).
        # İpuçları yalnız TEK çağrının içinde geçerlidir; her çağrı aynı
        # başlangıçtan çözer, böylece aynı girdi aynı biti verir.
        self._yk_ipucu_sifirla()
        of_ratio = _dogrula_karisim_orani(of_ratio)
        chamber_pressure = _dogrula_oda_basinci(chamber_pressure)
        if chamber_temperature is not None:
            chamber_temperature = _dogrula_oda_sicakligi(chamber_temperature)

        # ÖH D24 / P15B1-05 — çalışma noktası etiketi. Bilinmeyen etiket
        # SESSİZCE kabul edilmez: beyan alanının kendisi uydurma taşırsa
        # beyan işe yaramaz (fail-closed).
        _op_nokta = (OPERATING_POINT_AS_REQUESTED if operating_point is None
                     else str(operating_point))
        if _op_nokta not in _OPERATING_POINT_BASIS:
            # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
            raise ValueError(
                "Unknown operating_point %r; expected one of %s."
                % (operating_point, sorted(_OPERATING_POINT_BASIS)))

        # --- Memoizasyon (v2.5.0 UQ): anahtar eta_c_star İÇERMEZ, çünkü
        # eta yalnız iki türetilmiş alanı (eta_c_star, c_star_delivered)
        # etkiler ve isabet halinde kopya üstünde yeniden uygulanır. Böylece
        # UQ örnekleri arasında eta değişse de pahalı denge çözümü paylaşılır.
        #
        # --- ANAHTAR NİCEMLEMESİ KALDIRILDI (Faz 4B, bulgu A7) -------------
        # Eski anahtar O/F'yi 0.01'e, Pc'yi 0.1 bar'a, T'yi 0.1 K'e ve ε'yu
        # 0.01'e nicemliyordu. Bu, önbelleği "yaklaşık eşit girdiler aynı
        # cevabı alsın" hâline getiriyordu — yani KULLANICI GİRDİYİ
        # DEĞİŞTİRİYOR, CEVAP DEĞİŞMİYORDU.
        #
        # ÖLÇÜM (2 Ağustos 2026, HEAD a7ff1e7; htpb/N2O, O/F=6):
        #   memoize=True iken Pc=20.04 bar isteği Pc=20.00 sonucunu döndürüyor,
        #   c* bit-aynı. Aynısı O/F=6.004 için de geçerli.
        #   Nicemlemenin YUTTUĞU fark (memoize=False ile ölçüldü):
        #     inputs.chamber_pressure          20.00 -> 20.04  (%0.200)
        #     stations.chamber.pressure        20.00 -> 20.04  (%0.200)
        #     stations.chamber.density       1.85612 -> 1.85976 (%0.196)
        #     stations.throat.pressure       11.4419 -> 11.4647 (%0.199)
        #     performance.c_star                              (%0.0015)
        #   Yani sonuç sözlüğü, ÇÖZÜLMEYEN bir basıncı "girdi" diye geri
        #   bildiriyordu: hata c*'ta küçük, girdi yankısında ise tam bir yalan.
        #
        # ÖLÇÜT: nicemleme, çözümün duyarlılığından daha kaba olmamalı. Yoğunluk
        # Pc ile 1:1 ölçekleniyor (dρ/ρ = dPc/Pc), yani 0.1 bar nicemleme 20
        # bar'da %0.5'e kadar yoğunluk hatası demektir — sabitin kendisinden
        # büyük. Bu ölçütü sağlayan tek eşik "nicemleme yok"tur.
        #
        # İSABET ORANI ETKİSİ (aynı gün ölçüldü, gerçek çağrı izleriyle):
        #   O/F taraması (60 nokta):  nicemli %0.0 -> tam %0.0   (fark yok)
        #   Pc-O/F ızgarası (625):    nicemli %0.0 -> tam %0.0   (fark yok)
        #   UQ hibrit N=40 (84 çağrı): nicemli %47.6 -> tam %2.4
        # Görselleştirme yolları hiç etkilenmiyor (linspace noktaları zaten
        # birbirinden ayrı). UQ'da isabet düşüyor çünkü o "isabetler" fiziksel
        # olarak AYRI örneklerdi: Pc örnekler arasında 18.98-20.00 bar, ε ise
        # 3.68-3.82 aralığında değişiyordu ve nicemleme komşu örnekleri aynı
        # cevaba bağlıyordu — belirsizlik yayılımının tam da ölçmesi gereken
        # farkı siliyordu.
        #
        # --- BEDEL: ÖH D31 fizik-a1 / OH-D18-02 TAZE ÖLÇÜMÜ ----------------
        # Yukarıdaki "9,68 s / 60 s" kaydı (Faz 4B, 2 Ağustos 2026) BAYATTI
        # ve boşluğu 4,5 kat fazla gösteriyordu. Bugün ölçülen (14 Eylül
        # 2026, taban 9d70e9ed, M4; betik + ham sayılar:
        # docs/scofield/raw/OH/D31/fizik/a1/{olcum_d18_02.py, once_d18_02.
        # json}, kanıt raporu rapor.md):
        #   analyze_combustion tek çağrı  kayan denge 5,747 ms
        #                                  tek-γ      3,677 ms  -> 1,563x
        #                                  (çağrı başına 17 denge çözümü:
        #                                   12 izentrop + 1 ses + 3 bileşim
        #                                   + 1 oda)
        #   25 noktalı O/F taraması       0,140 s ⟷ 0,091 s
        #   625 noktalı ızgara kestirimi  3,50 s ⟷ 2,27 s (marj +1,23 s;
        #                                  PARAMETRIC_TIME_BUDGET_DEFAULT_S
        #                                  = 30 s'nin %4,1'i)
        #   test_hybrid_fast_budget_end_to_end  44,05 s / 60 s üst sınır
        #                                  (kayan denge KAPALI iken 23,77 s;
        #                                   yani bütçenin 20,3 s'si bu
        #                                   zincirin. Kalan boşluk 15,9 s)
        # İstasyon önbelleği O/F taramasında İŞE YARAMIYOR (6 nokta -> 6
        # hücre, isabet %0) — çünkü her noktada bileşim değişiyor. Çare
        # olarak önerilen "nicemlenmiş anahtar" bu blokta ölçülerek
        # REDDEDİLDİ ve karar iki bekçiyle kilitlendi
        # (tests/test_d31_fizik_a1.py::test_oh_d18_02_*). Hız için doğruluk
        # feda EDİLMEZ; bütçe kapısı zaten fail-closed'dır
        # (parametric_time_budget_exceeded).
        cache_key = None
        if self.memoize:
            try:
                anahtar_sayilari = [float(of_ratio), float(chamber_pressure)]
                if chamber_temperature is not None:
                    anahtar_sayilari.append(float(chamber_temperature))
                if expansion_ratio is not None:
                    anahtar_sayilari.append(float(expansion_ratio))
                bilesim = tuple(sorted((str(k).lower(), float(v))
                                       for k, v in fuel_composition.items()))
                anahtar_sayilari.extend(v for _, v in bilesim)
                if not all(np.isfinite(x) for x in anahtar_sayilari):
                    # NaN kendine eşit olmadığı için asla isabet etmez, ama
                    # her çağrıda yeni bir hücre açar. Önbelleksiz devam.
                    raise ValueError('non-finite cache key component')
                cache_key = (
                    bilesim,
                    str(oxidizer_type).lower(),
                    float(of_ratio),
                    float(chamber_pressure),
                    None if chamber_temperature is None
                    else float(chamber_temperature),
                    # ε çıkış istasyonunu (p_e, T_e, bileşim, isp, cf)
                    # değiştirdiği için anahtara GİRMELİDİR (v2.6.2/F034).
                    None if expansion_ratio is None
                    else float(expansion_ratio),
                    # ÖH D24 / P15B1-05: çalışma noktası etiketi GÖVDEDE
                    # yayımlandığı için anahtara da GİRMELİDİR — aynı O/F
                    # iki farklı rolle sorulursa önbellek yanlış etiketi
                    # geri verirdi.
                    _op_nokta,
                    # Kısmi (yalnız c*) sonuç tam isteğe dönmesin.
                    bool(c_star_only),
                )
            except (TypeError, ValueError):
                cache_key = None  # anahtarlanamayan girdi: önbelleksiz devam
            if cache_key is not None and cache_key in self._equilibrium_cache:
                result = copy.deepcopy(self._equilibrium_cache[cache_key])
                perf = result['performance']
                perf['eta_c_star'] = eta_c_star
                perf['c_star_delivered'] = (
                    eta_c_star * perf['c_star'] if eta_c_star is not None
                    else perf['c_star']
                )
                return result

        # Calculate elemental composition
        elements = self._calculate_elemental_composition(fuel_composition, oxidizer_type, of_ratio)
        
        # Calculate stoichiometric O/F ratio
        of_stoich = self._calculate_stoichiometric_of(fuel_composition, oxidizer_type)
        
        # Calculate chemical equilibrium
        if chamber_temperature is None:
            chamber_temperature, temperature_meta = self._estimate_flame_temperature(
                elements, chamber_pressure,
                fuel_composition=fuel_composition,
                oxidizer_type=oxidizer_type,
                of_ratio=of_ratio
            )
        else:
            # Oda sıcaklığını ÇAĞIRAN dayattı; burada hiçbir alev sıcaklığı
            # çözümü yapılmadı. Kaynağı 'equilibrium' saymak yanıltıcı olurdu.
            temperature_meta = {'temperature_source': 'user_specified',
                                'warning': None}

        # Calculate species concentrations at different stations using Cantera
        chamber_composition = self._calculate_equilibrium_composition(
            elements, chamber_pressure, chamber_temperature, 'chamber'
        )

        # Cantera'dan gerçek termodinamik değerleri al
        #
        # ÖH D16 / B3-08... (kalem B3-06) — KISA DEVRE KALDIRILDI.
        # Eski koşul `self.cantera_available and ...` idi. Cantera kapalı
        # (paketlenmiş/çevrimdışı/kırık kurulum) iken atom-dengesi yedeği
        # KENDİ gamma'sını üretip sözlüğe koyuyor, aşağıdaki :2016-2039 dalı
        # onu comp['gamma'] olarak okuyor ve c*/cf oradan geliyordu; ama bu
        # satır o gamma'yı ATIP 1,25 sabitini kullanıyordu. Sonuç: AYNI
        # yanıtta iki oda gamma'sı. ÖLÇÜLDÜ (1 Eylül 2026, taban 6fde52b;
        # htpb/N2O O/F=6 Pc=20 bar eps=4, CANTERA_AVAILABLE=False):
        #   compositions.chamber.gamma = performance.gamma_avg = 1,195914
        #   boğaz basıncından geri çözülen gamma  = 1,250000  (+%4,5226)
        #   boğaz sıcaklığından geri çözülen gamma = 1,250000
        #   yayımlanan P_boğaz 11,098579 bar / T_boğaz 2979,6954 K /
        #   P_çıkış 0,790319 bar — üçü de gamma_avg ile TUTARSIZ.
        # Artık istasyon bağıntıları, yanıtta YAYIMLANAN gamma'nın ta
        # kendisini kullanır; 1,25 yalnız hiç gamma üretilemediğinde kalır
        # (o durumu `mechanism` alanı zaten 'empirical' diye bildirir).
        # Cantera açıkken davranış DEĞİŞMEZ (çapa bit-aynı).
        _oda_gamma = None
        if isinstance(chamber_composition, dict):
            _oda_gamma = chamber_composition.get('gamma')
        if self.cantera_available and isinstance(chamber_composition, dict) \
                and 'temperature' in chamber_composition:
            chamber_temperature = chamber_composition['temperature']
        if _oda_gamma is not None and gamma_is_physical(_oda_gamma):
            gamma_chamber = float(_oda_gamma)
        else:
            # Fallback: tipik yanma gazı gamma'sı (Sutton & Biblarz 9. baskı, Bölüm 3)
            gamma_chamber = 1.25

        # Boğaz (kritik/choked) koşulları hesaplanan gamma'dan türetilir:
        # P_c/P_t = ((gamma+1)/2)^(gamma/(gamma-1)), T_t/T_c = 2/(gamma+1)
        # Sutton & Biblarz 9th ed., Eq. 3-20 ve 3-22
        #
        # --- ÖH D18 fizik-a1 / F1 (kalem B3-05) ---------------------------
        # Bu tek-γ çifti artık YALNIZ BAŞLANGIÇ TAHMİNİDİR. Sektör (NASA
        # RP-1311 Part I §6.2.2/§6.3.3; RPA v2.3 s.19) boğazı kimyasal
        # DENGEDE çözer: izentrop üzerinde kütle akısı G = ρv maksimumu
        # (⇔ v = a_eq). Eskiden boğaz istasyonu bu tek-γ bağıntısından
        # geliyordu — tam da dosyanın ÇIKIŞ için gerekçesiyle reddettiği
        # bağıntıdan. ÖLÇÜLDÜ (2 Eylül 2026, taban e726048; kayan-denge
        # sonik nokta referansına göre, 5 yakıt çifti):
        #     T_boğaz  −%0,95 … −%1,37   (30-50 K düşük)
        #     ρ_boğaz  +%1,39 … +%1,97
        #     v_boğaz  −%0,47 … −%0,92
        #   ve aynı yanıt içindeki süreklilik özdeşliği c* = P_c/(ρ_t v_t)
        #   KAPANMIYORDU: −%0,72 … −%1,02. (c*'ın kendisi kayan-denge
        #   referansına %0,08 içinde doğruydu; tutarsız olan boğaz
        #   istasyonuydu.) Ölçüm: docs/scofield/raw/OH/D18/fizik/a1/
        #   {olcum_f1.py, once_f1.json}.
        throat_pressure = chamber_pressure / (
            ((gamma_chamber + 1.0) / 2.0) ** (gamma_chamber / (gamma_chamber - 1.0))
        )
        throat_temperature = chamber_temperature * 2.0 / (gamma_chamber + 1.0)
        station_basis = 'single_gamma_chamber'
        eq_stations = None
        try:
            _comp_str = self._elements_to_cantera_composition(elements)
        except Exception:
            _comp_str = None
        if _comp_str:
            eq_stations = self._solve_equilibrium_throat(
                _comp_str, chamber_temperature, chamber_pressure,
                throat_pressure)
        if eq_stations is not None:
            throat_pressure = eq_stations['bogaz']['P'] / 1e5
            throat_temperature = eq_stations['bogaz']['T']
            station_basis = 'shifting_equilibrium'
            if c_star_only:
                # Tam yoldaki atamanın AYNISI (performance['c_star'] =
                # eq_stations['c_star']); sonrasında c* değiştirilmez.
                kisa = {
                    'c_star_only': True,
                    # Tam sonuçla AYNI düzen (conditions.chamber).
                    'conditions': {'chamber': {
                        'P': chamber_pressure, 'T': chamber_temperature}},
                    'performance': {
                        'c_star': eq_stations['c_star'],
                        'c_star_basis': 'shifting_equilibrium_throat',
                        'eta_c_star': eta_c_star,
                        'c_star_delivered': (
                            eta_c_star * eq_stations['c_star']
                            if eta_c_star is not None
                            else eq_stations['c_star']),
                    },
                    'condensed_phases': self._yk_beyan(chamber_composition),
                }
                if cache_key is not None:
                    if (cache_key not in self._equilibrium_cache
                            and len(self._equilibrium_cache)
                            >= self._equilibrium_cache_max):
                        self._equilibrium_cache.pop(
                            next(iter(self._equilibrium_cache)))
                    self._equilibrium_cache[cache_key] = copy.deepcopy(kisa)
                return kisa
        throat_composition = self._calculate_equilibrium_composition(
            elements, throat_pressure, throat_temperature, 'throat'
        )

        # --- Çıkış istasyonu basıncı ---
        # v2.6.2 FİZİK DENETİMİ (bulgu F034): burası SABİT 1.0 bar yazılıydı.
        # Yani raporlanan exit_temperature / exit_composition / performance
        # ['isp'] / ['cf'] ve calculate_altitude_performance tablosunun tamamı
        # kullanıcının girdiği ε ne olursa olsun 'deniz seviyesine eşlenik
        # lüle' değerleriydi (ölçüldü: htpb/n2o O/F=6 Pc=20 bar -> p_e=1.0 bar
        # sabitinden türeyen efektif ε yalnızca 3.74). Ayrıca ISA deniz
        # seviyesi 1.01325 bar'dır, 1.0 değil (hrma.constants içinde mevcut).
        #
        # Artık: expansion_ratio verilirse p_e izentropik alan-Mach
        # bağıntısından ε ve oda γ'sı ile çözülür (Sutton & Biblarz 9. baskı,
        # Eş. 3-14 + Eş. 3-7); verilmezse ISA deniz seviyesi çapası korunur ve
        # bu durum çıktıda 'exit_pressure_basis' ile dürüstçe bildirilir.
        #
        # --- ÖH D18 fizik-a1 / F1 (kalem B3-02) ---------------------------
        # Tek-γ alan-Mach çözümü + tek-γ çıkış SICAKLIĞI artık yalnız
        # başlangıç tahmini/geri dönüş yoludur. Kusur şuydu: çıkış HIZI
        # kayan-dengeden (enerji denklemi), çıkış SICAKLIĞI ve ε ise
        # reddedilen tek-γ bağıntısından geliyordu; ikisi
        # _fixed_nozzle_altitude_sweep'te A_e = ṁR_eT_e/(P_e v_e) ile
        # ÇARPILIYORDU. ÖLÇÜLDÜ (taban e726048, htpb/N2O O/F=6 Pc=20 bar;
        # kayan-denge referansına göre):
        #     ε= 2 → T_e +%0,27  | ε= 4 → +%5,25  | ε= 8 → +%11,55
        #     ε=16 → T_e +%18,46 | ε=40 → +%28,13
        #   ve aynı ε'da ürünün p_e'si denge hedefinden +%4,3…+%37,6 YÜKSEK,
        #   v_e ise −%0,85…−%1,40 düşük. Yön: A_e ve vakum Isp iyimser.
        # Artık ε DENGE ile boyutlandırılır (ε = G_t/G_e, süreklilik),
        # ε verilmezse ISA deniz seviyesi basıncındaki DENGE durumu alınır.
        if expansion_ratio is not None and float(expansion_ratio) > 1.0:
            exit_pressure = self._exit_pressure_from_expansion(
                float(expansion_ratio), gamma_chamber, chamber_pressure)
            exit_pressure_basis = 'expansion_ratio'
        else:
            exit_pressure = isa_pressure(0.0) * BAR_PER_PA  # 1.01325 bar (ISA)
            exit_pressure_basis = 'sea_level_default'
        exit_temperature = self._calculate_exit_temperature(
            chamber_temperature, chamber_pressure, exit_pressure, gamma=gamma_chamber
        )
        eq_exit = None
        if eq_stations is not None:
            if exit_pressure_basis == 'expansion_ratio':
                eq_exit = self._solve_equilibrium_exit(
                    eq_stations, float(expansion_ratio), exit_pressure)
            else:
                # ε yok: çıkış basıncı ISA deniz seviyesine çapalı, ama
                # istasyonun kendisi yine kayan-denge izentropundan gelir
                # (tek-γ T_e hatası burada da giderilir).
                self._yk_ipucu_sifirla()   # V301/B7 ardılı: belirlenimci başla
                eq_exit = self._equilibrium_isentrope_state(
                    eq_stations['s0'], eq_stations['h0'], exit_pressure * 1e5,
                    eq_stations.get('yk'))
        if eq_exit is not None:
            exit_pressure = eq_exit['P'] / 1e5
            exit_temperature = eq_exit['T']
            exit_pressure_basis = (
                'expansion_ratio_equilibrium'
                if station_basis == 'shifting_equilibrium'
                and expansion_ratio is not None and float(expansion_ratio) > 1.0
                else 'sea_level_default_equilibrium')
        exit_composition = self._calculate_equilibrium_composition(
            elements, exit_pressure, exit_temperature, 'exit'
        )
        
        # Calculate performance parameters
        performance = self._calculate_performance_parameters(
            chamber_composition, throat_composition, exit_composition,
            chamber_pressure, throat_pressure, exit_pressure,
            chamber_temperature, throat_temperature, exit_temperature
        )

        # Frozen vs shifting-equilibrium genişleme (NASA CEA "frozen" / "equilibrium"
        # ayrımı). Tek-gamma izentropik bağıntısı tüm lüleye ODA gamma'sını
        # uyguladığından (chamber gamma egzoz gazında düşüktür) çıkış hızını
        # sistematik olarak yanlış verir; doğru yöntem ENERJİ denklemidir:
        #   v_e = sqrt(2 * (h_oda - h_çıkış))     (Sutton & Biblarz 9. baskı, Eş. 3-15b;
        #   NASA RP-1311 Part I, lüle hız denklemi). h_çıkış izentropik genişlemeyle
        #   (s sabit) çıkış basıncında alınır:
        #     - frozen: çıkış bileşimi oda bileşimine DONDURULUR,
        #     - shifting: çıkış basıncında denge YENİDEN çözülür (gamma çıkış
        #       dengesinden gelir, böylece tek-gamma fazla-genişleme hatası giderilir).
        #
        # --- ÖH D18 fizik-a1 / F1: c*, boğaz hızı ve üçlü Isp yayını -------
        # c* artık kapalı-form tek-γ ifadesinden DEĞİL, çözülen boğaz
        # istasyonundan gelir: c* = P_c/(ρ_t v_t) (RP-1311 eş. 6.11). Böylece
        # ṁ = P_c A_t/c* ile ṁ = ρ_t v_t A_t ÖZDEŞ olur (süreklilik kapanışı
        # makine hassasiyetinde; bekçi: tests/test_d18_fizik_a1.py).
        isp_ucluk = None
        if eq_stations is not None:
            # Tek-γ kapalı formu SİLİNMEZ, ayrı anahtarda yayımlanır: yarı-1B
            # (kalorik mükemmel gaz) lüle çözücüsünün ürettiği ṁ tam olarak
            # P_c·A_t/c*_tek-γ'dır, dolayısıyla iki gaz modelini karşılaştıran
            # çapraz denetimin bilinen defter terimi budur
            # (hybrid_rocket_engine.mass_flow_c_star_model_ratio).
            performance['c_star_single_gamma'] = performance['c_star']
            performance['c_star'] = eq_stations['c_star']
            performance['velocities']['throat'] = eq_stations['bogaz']['v']
            performance['throat_sound_speed'] = eq_stations['bogaz']['a']
            performance['throat_mass_flux'] = eq_stations['bogaz']['G']
            performance['throat_sonic_residual'] = (
                eq_stations['sonic_residual'])
            performance['c_star_basis'] = 'shifting_equilibrium_throat'
            if eq_exit is not None:
                isp_ucluk = self._equilibrium_reference_isp(
                    eq_stations, eq_exit['P'], eq_exit['v'])
        else:
            performance['c_star_basis'] = 'single_gamma_closed_form'
        performance['station_basis'] = station_basis

        if isp_ucluk is not None:
            # Üçlü yayın (CEA nfz kipleri). 'isp_frozen' anahtarı SEKTÖRÜN
            # kötümser referansına (nfz=2, boğazda donmuş) bağlandı; odada
            # donmuş (nfz=1) değer mutlak alt sınır olarak AYRI anahtarda
            # yayımlanır. Kinetik verim bandı böylece frozen@throat–eq
            # arasıdır (MIT 16.512 L14 SSME: 435 / 451 / 465 s).
            performance.update(isp_ucluk)
            performance['isp_frozen'] = isp_ucluk['isp_frozen_throat']
            performance['isp_shifting'] = isp_ucluk['isp_equilibrium']
            performance['isp'] = isp_ucluk['isp_equilibrium']
            performance['velocities']['exit'] = eq_exit['v']
            if performance['c_star'] > 0:
                performance['cf'] = eq_exit['v'] / performance['c_star']
            performance['isp_reference_basis'] = {
                'isp_frozen': 'frozen_at_throat (CEA nfz=2)',
                'isp_shifting': 'shifting_equilibrium (CEA equilibrium)',
                'isp_frozen_chamber': 'frozen_at_chamber (CEA nfz=1, '
                                      'absolute lower bound)',
                'source': 'NASA RP-1311 Part I 6.2.2/6.3.3; RPA v2.3 p.19',
            }
            isp_frozen = performance['isp_frozen']
            isp_shifting = performance['isp_shifting']
            v_exit_shifting = eq_exit['v']
        else:
            isp_frozen, isp_shifting, v_exit_shifting = (
                self._calculate_frozen_shifting_isp(
                    elements, chamber_temperature, chamber_pressure,
                    exit_pressure))
        if isp_ucluk is None and isp_shifting is not None:
            performance['isp_frozen'] = isp_frozen
            performance['isp_shifting'] = isp_shifting
            # Mevcut 'isp' anahtarı gerçeğe daha yakın olan shifting-equilibrium
            # değerine güncellenir; eski tek-gamma değeri çıkış gamma'sını
            # kullanmadığından sistematik hatalıydı. Cf ve çıkış hızı da
            # tutarlı kalsın diye aynı v_exit'ten türetilir.
            performance['isp'] = isp_shifting
            performance['velocities']['exit'] = v_exit_shifting
            if performance['c_star'] > 0:
                performance['cf'] = v_exit_shifting / performance['c_star']

        # c* (yanma) verimi: teorik c_star KORUNUR, ayrı bir anahtarla teslim
        # edilen (gerçekçi) c* raporlanır. eta_c_star None ise teorik = teslim.
        performance['eta_c_star'] = eta_c_star
        if eta_c_star is not None:
            performance['c_star_delivered'] = eta_c_star * performance['c_star']
        else:
            performance['c_star_delivered'] = performance['c_star']

        # --- Oda sıcaklığının kaynağı (v2.6.27 dürüstlük alanı) -------------
        # _estimate_flame_temperature (T_ad, beyan) çifti döndürür; beyan
        # BURADA sonuca bağlanır. Bağlanmazsa ampirik zarfa düşen koşum
        # panelde denge çözümünden gelmiş gibi görünür — düzeltilen kusur
        # tam olarak buydu (yol düzeltildi ama beyan kanalı kopuktu).
        # DİKKAT: chamber_temperature yukarıda Cantera oda bileşiminin
        # 'temperature' alanıyla güncellenmiş olabilir; bu sözlük o YÜZDEN
        # burada, güncellemeden SONRA kurulur.
        chamber_conditions = {
            'P': chamber_pressure,
            'T': chamber_temperature,
            'temperature_source': temperature_meta['temperature_source'],
        }
        if temperature_meta.get('warning'):
            # Uyarı YALNIZCA gerçekten düşüş olduğunda konur (compositions
            # [station] ile aynı sözleşme: denge yolunda 'warning' anahtarı
            # hiç bulunmaz, boş/None bir uyarı taşınmaz).
            chamber_conditions['warning'] = temperature_meta['warning']

        result = {
            'stoichiometric_of': of_stoich,
            'equivalence_ratio': of_stoich / of_ratio,
            'elemental_composition': elements,
            # v2.6.26 — sifir degerler GERCEK hesap sonucudur, eksik
            # veri degil: katalogdaki hibrit yakitlarin hicbiri metal
            # icermedigi icin AL kesri 0 cikar. Metalize bir yakit
            # secilirse (fuel_type='aluminum') 0'dan farkli olur.
            'elemental_composition_basis': (
                'computed mass fractions of the elemental composition; '
                'a zero AL fraction is a real result - no catalogued '
                'hybrid fuel contains aluminium'),
            'compositions': {
                'chamber': chamber_composition,
                'throat': throat_composition,
                'exit': exit_composition
            },
            # --- Denge arka ucunun kimliği (v2.6.27 beyanı) ----------------
            # 'mechanism': bu koşumdaki denge çözümlerinin geldiği Cantera
            # mekanizması ('gri30' / 'h2o2'), Cantera yoksa 'empirical'.
            # Sonuçlar mekanizmaya BAĞLIDIR (tür listesi farklı = denge
            # farklı), bu yüzden hangi mekanizmanın kullanıldığı çıktının
            # parçasıdır — nitekim optimum O/F önbellek anahtarına da girer.
            #
            # 'mechanism_T_ceiling_K': mekanizmanın termo verisinin güvenli
            # üst sıcaklığı (türler arasındaki en düşük max_temp; gri30 ->
            # 3000 K). Oda sıcaklığı bunun ÜSTÜNDEYSE NASA polinomları
            # ekstrapole edilmiştir; bilinçli kabul kullanıcıdan gizlenmez.
            # Cantera yokken None (uydurma bir tavan konmaz).
            #
            # cantera_available, kurulumdan SONRA da kapatılabildiği için
            # (testler ve /calculate'in Cantera'sız yolu) beyan _mechanism_id
            # yerine ANLIK duruma bakar: kapalıysa gerçekten ampirik yol
            # çalışır, 'gri30' demek yalan olurdu.
            'mechanism': (self._mechanism_id if self.cantera_available
                          else 'empirical'),
            'mechanism_T_ceiling_K': (self._mechanism_T_ceiling_K
                                      if self.cantera_available else None),
            'conditions': {
                # 'temperature_source': oda sıcaklığının NEREDEN geldiği.
                #   'equilibrium'        -> entalpi hedefli denge kök araması
                #                           (_estimate_flame_temperature),
                #   'empirical_envelope' -> denge çözülemedi, ampirik zarf
                #                           (yanında 'warning' alanı olur),
                #   'user_specified'     -> çağıran chamber_temperature dayattı.
                # Aynı dürüstlük deseni bu sözlükte zaten iki yerde var:
                # conditions['exit']['basis'] ve compositions[station]['source'].
                'chamber': dict(chamber_conditions),
                # 'basis' (ÖH D18 F1 / B3-05): boğaz istasyonunun MODELİ.
                #   'shifting_equilibrium'  -> izentrop üzerinde kütle akısı
                #                              maksimumu (v = a_eq), c* aynı
                #                              istasyondan (RP-1311 §6.3.3),
                #   'single_gamma_chamber'  -> Cantera yok/çözüm ıraksadı,
                #                              tek-γ kritik oran bağıntısı
                #                              (Sutton Eş. 3-20/3-22).
                'throat': {'P': throat_pressure, 'T': throat_temperature,
                           'basis': station_basis},
                # 'basis': çıkış basıncının nereden geldiği (F034 dürüstlük
                # alanı; ÖH D18 F1 / B3-02 ile genişletildi).
                #   'expansion_ratio_equilibrium' = ε kayan-denge
                #       sürekliliğinden çözüldü (ε = G_t/G_e) — ANA YOL,
                #   'sea_level_default_equilibrium' = ε verilmedi; basınç ISA
                #       deniz seviyesine çapalı, istasyon yine kayan-dengeden,
                #   'expansion_ratio' / 'sea_level_default' = denge çözücüsü
                #       kullanılamadı, tek-γ alan-Mach bağıntısı (geri dönüş).
                'exit': {'P': exit_pressure, 'T': exit_temperature,
                         'basis': exit_pressure_basis}
            },
            'performance': performance,
            # Koşunun girdi kimliği: O/F tarama paneli gibi tüketiciler,
            # çağıran kimliği ayrıca geçirmediğinde taramayı bu bloktan
            # kurar (uydurma değil — çözücüye giren değerlerin kendisi).
            'inputs': {
                'fuel_composition': dict(fuel_composition),
                'oxidizer_type': oxidizer_type,
                'of_ratio': of_ratio,
                'chamber_pressure': chamber_pressure,
                # ÖH D24 / P15B1-05 — bu ağacın ÇALIŞMA NOKTASI. Aynı
                # iskelet yanıtta iki kez yayımlanıyor (tasarım O/F ve
                # danışma optimum O/F); hangisi olduğu artık okunabilir.
                'operating_point': _op_nokta,
                'operating_point_basis': _OPERATING_POINT_BASIS[_op_nokta],
            },
            # ÖH D24 / P15B1-05 — ``compositions`` HAM SI tabanındadır
            # (J/kg); istasyon tablosu kJ tabanındadır ve alan adlarında
            # birimi taşır. İki taban artık ad düzeyinde ayrıktır.
            'composition_units': dict(_COMPOSITION_UNITS),
            # V301/B7 — yoğun faz beyanı (gaz + C(gr) dengesi devrede mi?).
            'condensed_phases': self._yk_beyan(
                chamber_composition, throat_composition, exit_composition),
        }

        if cache_key is not None:
            # Faz 4B (bulgu A7): tam anahtarla hücre sayısı artabilir, bu yüzden
            # önbellek sınırlı — en eski kayıt düşer (FIFO; dict ekleme sırasını
            # korur). Aynı dosyadaki _OPTIMUM_OF_CACHE ile aynı desen.
            if (cache_key not in self._equilibrium_cache
                    and len(self._equilibrium_cache)
                    >= self._equilibrium_cache_max):
                self._equilibrium_cache.pop(
                    next(iter(self._equilibrium_cache)))
            # Kopya sakla: çağıran sonucu mutasyona uğratsa bile önbellek bozulmaz
            self._equilibrium_cache[cache_key] = copy.deepcopy(result)

        return result
    
    def _calculate_elemental_composition(self, fuel_composition: Dict, 
                                       oxidizer_type: str, of_ratio: float) -> Dict:
        """Calculate elemental mass composition of reactants"""
        
        elements = {'C': 0, 'H': 0, 'O': 0, 'N': 0, 'AL': 0}
        
        total_mass = 1.0 + of_ratio  # Fuel + oxidizer
        fuel_mass_fraction = 1.0 / total_mass
        oxidizer_mass_fraction = of_ratio / total_mass
        
        # Process fuel composition
        #
        # ÖH D19 (kalem B3-12): pay ve payda ARTIK AYNI KAYNAKTAN geliyor —
        # _REACTANT_FORMULAS (formül) + _ATOMIC_MASS (IUPAC 2021). Eskiden
        # her yakıt için atom kütleleri (12,01 / 1,01 / 16,00) ve molekül
        # ağırlığı (54,0 / 170,33 / 104,15 / 72,06 / 28,05 / 100,12) ayrı
        # ayrı elle yazılıydı; ikisi tutmadığı için kütle korunmuyordu
        # (HTPB'de +%0,1852). Yaklaşım formülleri (C4H6, C12H26, C8H8,
        # C3H4O2, C2H4, C5H8O2) DEĞİŞMEDİ, yalnız bölen türetiliyor.
        for fuel_type, percentage in fuel_composition.items():
            fuel_fraction = (percentage / 100.0) * fuel_mass_fraction

            if fuel_type in SUPPORTED_HYBRID_FUEL_KEYS:
                formul = self._REACTANT_FORMULAS[fuel_type]
                mw = self._formula_molar_mass(fuel_type)
                for element, atom_count in formul.items():
                    elements[element] += (
                        fuel_fraction * atom_count
                        * self._ATOMIC_MASS[element] / mw)
            else:
                # Sessiz düşme YASAK (oksitleyici dalındaki gerekçeyle aynı):
                # bilinmeyen yakıt elemental katkısız kalır ve denge çöp üretir.
                # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
                # Alan adı ve kabul kümesi MAKİNE-OKUR biçimde taşınır
                # (ÖH D21 / P12bB3-02): çağıran hangi ALANIN reddedildiğini
                # metni ayrıştırmadan öğrenir. Metin İngilizcedir ve
                # desteklenen liste tek kaynaktan (yukarıdaki demet)
                # üretilir — elle senkron tutulan ikinci kopya yoktur.
                # ÖH D31 / P12bB3-02: gerekçe ADIYLA (kategori hatası /
                # literatür borcu / şema borcu) — TEK KAYNAK.
                raise _unsupported_fuel_error(fuel_type)

        # Process oxidizer
        # ÖH D19 (kalem B3-12): yakıt dalıyla aynı tek kaynak. Hava kendi
        # dalında kalır çünkü elemental katkısı formülden değil KÜTLE
        # KESİRLERİNDEN (Y_O2 / Y_N2) türer.
        if oxidizer_type.lower() in ('n2o', 'h2o2'):
            anahtar = oxidizer_type.lower()
            formul = self._REACTANT_FORMULAS[anahtar]
            mw = self._formula_molar_mass(anahtar)
            for element, atom_count in formul.items():
                elements[element] += (
                    oxidizer_mass_fraction * atom_count
                    * self._ATOMIC_MASS[element] / mw)
        elif oxidizer_type.lower() in ('lox', 'gox', 'o2', 'oxygen'):
            # O2 (sıvı ya da gaz — elemental katkı aynı). 'gox' eskiden hiçbir
            # dala girmiyordu: elemental O=0 kalıyor, denge OKSİJENSİZ çözülüp
            # c*'ı ~%40 şişiriyordu (2026-07-18 korelasyon fizik incelemesi).
            # Saf O2'de pay/payda zaten sadeleşir (katkı tanım gereği 1,0).
            elements['O'] += oxidizer_mass_fraction * (
                2 * self._ATOMIC_MASS['O'] / self._formula_molar_mass('o2'))
        elif oxidizer_type.lower() == 'air':
            # Hava: elemental KÜTLE dengesi için KÜTLE kesirleri kullanılır
            # (Y_O2=0.2314, Y_N2=0.7686; US Standard Atmosphere 1976 bileşiminden).
            # Eski kodda mol kesirleri (0.21/0.79) kütle kesri gibi kullanılıyordu.
            # Y_O2 + Y_N2 = 1 olduğu ve her iki tür de kendi molekül ağırlığına
            # bölündüğü için toplam katkı yine tam olarak kütle kesridir.
            _mw_n2 = 2 * self._ATOMIC_MASS['N']
            elements['O'] += oxidizer_mass_fraction * AIR_O2_MASS_FRACTION * (
                2 * self._ATOMIC_MASS['O'] / self._formula_molar_mass('o2'))
            elements['N'] += oxidizer_mass_fraction * AIR_N2_MASS_FRACTION * (
                2 * self._ATOMIC_MASS['N'] / _mw_n2)
        else:
            # Sessiz düşme YASAK: bilinmeyen anahtar elemental katkısız kalır
            # ve denge fiziksel olmayan sonuç üretir ('gox' bugı aylarca böyle
            # gizlendi). Korelasyon koşucusu bu hatayı 'runner_error' olarak
            # etiketler; UI listeleri yalnız tanınan anahtarları sunar.
            # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
            raise ValueError(
                f"Unsupported oxidizer key '{oxidizer_type}'. Supported "
                f"oxidizers: n2o, lox, gox/o2/oxygen, h2o2, air.")

        return elements
    
    def _calculate_stoichiometric_of(self, fuel_composition: Dict, oxidizer_type: str) -> float:
        """Calculate stoichiometric O/F ratio"""
        
        # Calculate oxygen requirement for complete combustion
        oxygen_required = 0  # kg O2 per kg fuel
        
        # ÖH D19 (kalem B3-12): stokiyometrik O2 katsayısı ve yakıtın molekül
        # ağırlığı ARTIK ELLE YAZILMIYOR — ikisi de _REACTANT_FORMULAS'tan
        # türetiliyor. Bu, HTPB'nin DÖRDÜNCÜ elle yazılmış molekül ağırlığını
        # (54,0) kaldırır. Tam yanma stokiyometrisi CxHyOz için
        #     n_O2 = x + y/4 - z/2
        # (C -> CO2, H -> H2O, yakıttaki O ürün oksijenini karşılar); metalik
        # alüminyum için 2 Al + 1,5 O2 -> Al2O3, yani Al başına 3/4 O2.
        # DOĞRULAMA (türetilen ⟷ eski elle yazılan katsayı):
        #   C12H26 18,5 ⟷ 18,5 | C4H6 5,5 ⟷ 5,5 | C8H8 10 ⟷ 10
        #   C3H4O2 3 ⟷ 3 | C2H4 3 ⟷ 3 | C5H8O2 6 ⟷ 6 | Al 0,75 ⟷ 0,75
        # Katsayılar birebir aynı; değişen yalnız bölenlerin tek kaynaktan
        # gelmesidir (54,0 -> 54,092 vb.).
        # ÖH D25 (kalem B3-12, a2): SESSİZ DÜŞME KALDIRILDI. Eskiden bu döngü
        # tanımadığı yakıtı `continue` ile ATLIYOR, kardeş fonksiyon
        # _calculate_elemental_composition ise AYNI anahtarı adıyla
        # REDDEDİYORDU — tek modülde İKİ AYRI kabul kümesi (B3-12'nin "tek
        # kaynak" kusurunun kabul-kümesi biçimi). ÖLÇÜLDÜ (once.json K6,
        # taban cdf2106) — sessiz kol fiziksel olmayan sayı yayımlıyordu:
        #     yakıt 'n2o'      -> of_stoich = −0,3635062367936746  (NEGATİF)
        #     yakıt 'o2'       -> of_stoich = −1,0                 (NEGATİF)
        #     yakıt 'h2o2'     -> of_stoich = −0,4703651437643323  (NEGATİF)
        #     yakıt 'kerosene' -> of_stoich = 0                    (oksijensiz)
        # (Oksitleyici formülleri de _REACTANT_FORMULAS'ta olduğu için
        # z/2 terimi payı negatife çeviriyordu.) Kabul kümesi artık kardeş
        # fonksiyonla TEK KAYNAKTAN (SUPPORTED_HYBRID_FUEL_KEYS) gelir.
        # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
        _mw_o2 = self._formula_molar_mass('o2')
        for fuel_type, percentage in fuel_composition.items():
            fuel_fraction = percentage / 100.0

            if fuel_type not in SUPPORTED_HYBRID_FUEL_KEYS:
                # ÖH D31 / P12bB3-02: gerekçe ADIYLA (kategori hatası /
                # literatür borcu / şema borcu) — TEK KAYNAK.
                raise _unsupported_fuel_error(fuel_type)
            formul = self._REACTANT_FORMULAS[fuel_type]
            if formul.get('AL'):
                # 2 Al + 1.5 O2 → Al2O3
                n_o2 = 0.75 * formul['AL']
            else:
                n_o2 = (formul.get('C', 0)
                        + formul.get('H', 0) / 4.0
                        - formul.get('O', 0) / 2.0)
            oxygen_required += (
                fuel_fraction * n_o2 * _mw_o2
                / self._formula_molar_mass(fuel_type))


        # Convert to oxidizer mass
        #
        # ÖH D25 (kalem B3-12, Fable-D19 ŞART): oksitleyicinin KULLANILABİLİR
        # oksijen kütle kesri de ARTIK ELLE YAZILMIYOR. B3-12'nin kusur sınıfı
        # "pay tablodan, payda elle"ydi; D19 payı (n_O2) ve yakıt molekül
        # ağırlığını tek kaynağa bağladı ama oksitleyici tarafındaki bölen elle
        # kalmıştı, yani aynı kusur küçülmüş biçimde sürüyordu. ÖLÇÜLDÜ
        # (once.json K1/K2; taban cdf2106):
        #     N2O  elle 0.3636 ⟷ tablodan 0,3635062367936746  (+%0,0258)
        #     H2O2 elle 0.4704 ⟷ tablodan 0,4703651437643323  (+%0,0074)
        #   of_stoich(htpb/N2O) 8,948054274480175 ⟷ 8,950362346... ,
        #   yayımlanan ER 1,491342379080029 ⟷ 1,491727057... (−%0,0258).
        # 14 yakıt×oksitleyici çiftinin 14'ü tablodan sapıyordu; şimdi 0.
        #
        # Boyut analizi: pay ve payda [g/mol], oran BOYUTSUZ kütle kesridir
        # (kg kullanılabilir O2 / kg oksitleyici). oxygen_required [kg O2/kg
        # yakıt] bu kesre bölününce [kg oksitleyici / kg yakıt] = O/F kalır.
        if oxidizer_type.lower() == 'n2o':
            # N2O ayrışması:  N2O -> N2 + 1/2 O2  (Zucrow & Hoffman,
            # "Gas Dynamics" Vol.1; Sutton & Biblarz, "Rocket Propulsion
            # Elements" 9. baskı, hibrit oksitleyiciler bölümü). Azot N2
            # olarak inert ayrıldığı için N2O'nun oksijeninin TAMAMI yakıt
            # oksidasyonuna gider:
            #     m_O2 / m_N2O = (1/2 · M_O2) / M_N2O = M_O / M_N2O
            # Sadeleşme sayesinde tek atom kütlesi yeter; ikinci bir sayı
            # doğmaz. (M_N2O = 44,013 g/mol, propellant_specs ile birebir.)
            oxidizer_required = (
                oxygen_required
                / (self._ATOMIC_MASS['O'] / self._formula_molar_mass('n2o')))
        elif oxidizer_type.lower() in ('lox', 'gox', 'o2', 'oxygen'):
            # Saf oksijen (sıvı ya da gaz) — açık dal; sessiz else'e güvenilmez
            oxidizer_required = oxygen_required
        elif oxidizer_type.lower() == 'h2o2':
            # H2O2'de yakıt oksidasyonu için KULLANILABİLİR oksijen:
            #     2 H2O2 -> 2 H2O + O2
            # yani İKİ H2O2 molekülü başına BİR O2 açığa çıkar:
            #     m_O2 / m_H2O2 = M_O2 / (2 · M_H2O2)
            # (Toplam O kütle içeriği 0,9412'dir ama H, bir O atomunu H2O
            # olarak bağladığından yakıta gitmez — eski 0.9412 katsayısı bu
            # yüzden yanlıştı. Kaynak: Sutton & Biblarz, tek-itici/HTP
            # ayrışma stokiyometrisi.)
            oxidizer_required = (
                oxygen_required
                / (self._formula_molar_mass('o2')
                   / (2.0 * self._formula_molar_mass('h2o2'))))
        elif oxidizer_type.lower() == 'air':
            # Hava O2 kütle kesri (US Standard Atmosphere 1976 bileşiminden)
            oxidizer_required = oxygen_required / AIR_O2_MASS_FRACTION
        else:
            # ÖH D25 (kalem B3-12, a2): SESSİZ VARSAYILAN KALDIRILDI. Eski
            # kol tanımadığı HER oksitleyiciyi sessizce SAF OKSİJEN sayıyordu;
            # ÖLÇÜLDÜ (once.json K6): 'n2o4', 'nitrous' ve BOŞ dizge için
            # of_stoich = 3,253512534200991 — yani lox ile BİREBİR aynı sayı,
            # oysa kardeş _calculate_elemental_composition üçünü de adıyla
            # reddediyordu. Kabul kümesi artık iki fonksiyonda da aynıdır.
            # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
            hata = ValueError(
                f"Unsupported oxidizer key '{oxidizer_type}'. Supported "
                f"oxidizers: n2o, lox, gox/o2/oxygen, h2o2, air.")
            hata.field = 'oxidizer_type'
            hata.reason = 'unsupported_oxidizer_key'
            raise hata

        return oxidizer_required
    
    def _estimate_flame_temperature(self, elements: Dict, pressure: float,
                                    fuel_composition: Optional[Dict] = None,
                                    oxidizer_type: Optional[str] = None,
                                    of_ratio: Optional[float] = None
                                    ) -> Tuple[float, Dict]:
        """Adyabatik alev sıcaklığını hesaplar (NASA CEA yaklaşımı).

        (T_ad [K], beyan) çifti döndürür. 'beyan' sözlüğü sonucun HANGİ YOLDAN
        geldiğini taşır: {'temperature_source': ..., 'warning': ...|None}.
        Çağıran (analyze_combustion) bunu sonuç sözlüğüne aktarır — sıcaklığın
        denge çözümünden mi ampirik zarftan mı geldiği kullanıcıdan GİZLENMEZ.

        YÖNTEM (v2.6.27'de değişti) — entalpi hedefli sıcaklık kök araması:
            T_ad, şu kalıntının kökü olarak çözülür
                g(T) = h_denge(T, p) - h_reaktan
            burada h_denge(T, p) karışımın T'de TP dengesindeki kütlesel
            entalpisidir. Kök brentq ile FLAME_T_BRACKET_K parantezinde
            aranır. Bu, adyabatik alev sıcaklığının tanımının kendisidir
            (Gordon & McBride, NASA RP-1311 Part I) ve HP dengesiyle aynı
            denklemi çözer — ama bileşimi her T denemesinde YENİDEN dengeler.

        NEDEN DEĞİŞTİ (ölçülmüş kök neden):
            Eski kod önce 3000 K'de TP dengesi kurup ardından
            ``self.gas.HP = h_reactants, p`` ile HP dengesini çözüyordu.
            Cantera'nın HP setter'ı BİLEŞİMİ DONDURUP yalnız T için Newton
            iterasyonu yapar; 3000 K dengesinden gelen AYRIŞMIŞ karışımın
            (yakıt-zengin uçta kütlece ~%44'ü C2H2+HCN) donmuş entalpisi
            hiçbir T'de hedefe inemez (ölçüldü: htpb/n2o O/F=1'de erişilebilir
            en düşük 1.85 MJ/kg, hedef 0.96 MJ/kg) -> setter CanteraError
            fırlatır ve ``equilibrate('HP')`` satırına HİÇ ULAŞILAMAZ.
            312 noktalık haritada 36 nokta (%11.5) böyle düşüyordu, hepsi
            O/F <= 1.0'da; sessizce ampirik zarfa geçiliyor ve O/F=1'de Isp
            +10.6 s şişik raporlanıyordu.
            Kök araması bileşimi dondurmadığı için bu sorun yapısal olarak
            ortadan kalkar: ölçüldü, htpb/n2o O/F=1.0 / 30 bar'da doğru denge
            sıcaklığı 1137.45 K'dir.

        BİT-AYNILIK: HP'nin BUGÜN yakınsadığı noktalarda yeni yol aynı kökü
        bulur (ölçüldü: 176 noktada |ΔT| < 1e-4 K). tests/test_combustion.py
        içindeki bekçi bu eşdeğerliği kilitler; CEA çapaları kımıldamaz.

        Kök yoksa (parantez uçlarında g aynı işaretli — ör. çok yakıt-zengin
        uçta gri30'da katı karbon C(gr) bulunmadığı için denge eğrisi hedefe
        inemez) İSTİSNA FIRLATILMAZ: ampirik zarfa düşülür, ama artık BEYANLI.
        """
        self._yk_ipucu_sifirla()   # V301/B7 ardılı: aşama belirlenimci başlar
        if not self.cantera_available:
            return self._empirical_flame_temperature_declared(
                elements, pressure, of_ratio, 'cantera_unavailable')

        h_reactants = self._calculate_reactant_enthalpy(
            fuel_composition, oxidizer_type, of_ratio
        )
        if h_reactants is None:
            logger.warning(
                "Reaktan oluşum entalpisi hesaplanamadı (eksik Hf verisi); "
                "ampirik alev sıcaklığı modeli kullanılıyor."
            )
            return self._empirical_flame_temperature_declared(
                elements, pressure, of_ratio, 'missing_formation_enthalpy')

        p_pa = pressure * 1e5
        T_lo, T_hi = FLAME_T_BRACKET_K
        try:
            # Elemental KÜTLE kesirleri atomik türlerin kütle kesri olarak
            # atanır (TPY; TPX mol kesri ister — bkz. yardımcının docstring'i)
            # ve her T denemesinde TP dengesiyle moleküler ürün karışımına
            # getirilir.
            comp_str = self._elements_to_cantera_composition(elements)

            def _kalan(T: float) -> float:
                """g(T) = h_denge(T, p) - h_reaktan  [J/kg]"""
                self.gas.TPY = float(T), p_pa, comp_str
                self.gas.equilibrate('TP')
                return self.gas.enthalpy_mass - h_reactants

            # Parantezin üst ucu mekanizmanın termo tavanının (gri30: 3000 K)
            # üstündedir; Cantera orada "outside valid range" uyarısı basar.
            # Ekstrapolasyon bilinçli kabuldür ve kullanıcıya sonuçtaki
            # 'mechanism_T_ceiling_K' alanıyla bildirilir, bu yüzden uyarı
            # burada test/konsol gürültüsü yaratmasın diye filtrelenir
            # (_calculate_equilibrium_composition'daki SP bloğuyla aynı desen).
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    'ignore',
                    message=r'.*outside valid range.*',
                    category=UserWarning,
                )
                try:
                    T_ad = float(brentq(_kalan, T_lo, T_hi,
                                        xtol=FLAME_T_ROOT_XTOL_K,
                                        rtol=FLAME_T_ROOT_RTOL))
                except (ValueError, RuntimeError) as exc:
                    # Kök yok mu, gerçek çözücü hatası mı? Uçları ölçüp ayır
                    # (yalnız BAŞARISIZLIK yolunda ödenen iki denge çözümü).
                    reason = 'solver_error'
                    try:
                        if _kalan(T_lo) * _kalan(T_hi) > 0.0:
                            reason = 'no_enthalpy_root'
                    except Exception:
                        pass
                    logger.warning(
                        "Adyabatik alev sıcaklığı kök araması başarısız "
                        "(%s: %s; O/F=%s, p=%.3f bar); ampirik alev sıcaklığı "
                        "modeli kullanılıyor.", reason, exc, of_ratio, pressure)
                    return self._empirical_flame_temperature_declared(
                        elements, pressure, of_ratio, reason)

                # Gaz durumunu kökte DENGEDE bırak: brentq'ün son deneme
                # noktası kök olmak zorunda değildir ve akış aşağısındaki
                # gamma/MW okumaları bu durumdan devam eder.
                self.gas.TPY = T_ad, p_pa, comp_str
                self.gas.equilibrate('TP')

                # V301/B7 — gaz-yalnız kökte karbon aşırı doymuşsa (ln a_C >
                # 0) gerçek denge gaz + C(gr)'dir: entalpi kökü İKİ FAZLI
                # karışım entalpisiyle yeniden aranır. Doymamışsa bu blok
                # hiçbir şey yapmaz (bit-aynı): h(T) monoton olduğundan
                # kökte doymamış gaz dengesi iki fazlı problemin de tek
                # çözümüdür (RP-1311 eş. 3.7 ölçütü kökte sağlanmıyor).
                if self._gaz_karbon_asiri_doymus():
                    try:
                        T_ad = self._yk_alev_sicakligi(p_pa, h_reactants, T_ad)
                    except Exception as exc:  # noqa: BLE001 — beyanlı düşüş
                        logger.warning(
                            "İki fazlı (gaz + C(gr)) alev sıcaklığı çözülemedi "
                            "(%s; O/F=%s, p=%.3f bar); ampirik alev sıcaklığı "
                            "modeli kullanılıyor.", exc, of_ratio, pressure)
                        self._yk_geri_yukle(T=T_ad, P_pa=p_pa,
                                            y_el=self._yk_element_kutle())
                        return self._empirical_flame_temperature_declared(
                            elements, pressure, of_ratio,
                            'condensed_carbon_unsolved')

            if not (200.0 < T_ad < 6000.0):
                # Parantez zaten [250, 5500] olduğu için buraya ancak sayısal
                # bir patoloji düşürebilir; sessiz kabul etmek yerine beyanlı
                # ampirik yola gidilir.
                logger.warning(
                    "Fiziksel olmayan alev sıcaklığı: %.1f K (O/F=%s); "
                    "ampirik alev sıcaklığı modeli kullanılıyor.",
                    T_ad, of_ratio)
                return self._empirical_flame_temperature_declared(
                    elements, pressure, of_ratio, 'nonphysical_temperature')

            return T_ad, {'temperature_source': 'equilibrium', 'warning': None}
        except Exception as exc:
            # Denge kurulamayan girdi (ör. mekanizmada bulunmayan element:
            # gri30'da AL yoktur) ve beklenmeyen Cantera hataları.
            logger.warning(
                "Cantera denge çözümü kurulamadı (%s); "
                "ampirik alev sıcaklığı modeli kullanılıyor.", exc
            )
            return self._empirical_flame_temperature_declared(
                elements, pressure, of_ratio, 'solver_error')

    def _yk_alev_sicakligi(self, p_pa: float, h_reactants: float,
                           T_gaz: float) -> float:
        """Gaz + C(gr) dengesinde adyabatik alev sıcaklığı [K].

        g(T) = h_karışım(T, p) − h_reaktan kökü (RP-1311 eş. 2.13a, h ile
        eş. 2.14 tanımı, yoğun tür dahil). Parantez gaz-yalnız kökten
        başlar: g(T_gaz) < 0 ise kök üstte (C(gr) oluşumu ekzotermiktir,
        ölçülen bütün yakıtça zengin noktalarda böyle), değilse altta.
        Gaz nesnesi kökte TOPLAM bileşimli gaz dengesine bırakılır
        (çağıranın 'kökte dengede bırak' sözleşmesi).
        """
        y_el = self._yk_element_kutle()
        son = {'eps': None}
        bellek = {}   # T -> g: brentq uç yeniden değerlendirmesi
        gecmis = []   # (T, ε>0) — ε sıcak başlangıç öngörüsü için

        def g(T):
            if T in bellek:
                return bellek[T]
            d = self._yk_tp(T, p_pa, y_el, _eps_ongoru(gecmis, T, son['eps']))
            if d['eps'] > 0.0:
                son['eps'] = d['eps']
                gecmis.append((T, d['eps']))
            bellek[T] = d['h'] - h_reactants
            return bellek[T]

        T_lo, T_hi = FLAME_T_BRACKET_K
        g_gaz = g(T_gaz)
        yon = 1.0 if g_gaz < 0.0 else -1.0
        T_ad = _sekant_dene(
            g, T_gaz, g_gaz,
            T_gaz * (1.0 + yon * CONDENSED_FLAME_T_SECANT_STEP_REL),
            T_lo, T_hi, FLAME_T_ROOT_XTOL_K)
        if T_ad is None:
            a, b = (T_gaz, T_hi) if g_gaz < 0.0 else (T_lo, T_gaz)
            T_ad = float(brentq(g, a, b, xtol=FLAME_T_ROOT_XTOL_K,
                                rtol=FLAME_T_ROOT_RTOL))
        self._yk_geri_yukle(T=T_ad, P_pa=p_pa, y_el=y_el)
        return T_ad

    def _empirical_flame_temperature_declared(
            self, elements: Dict, pressure: float,
            of_ratio: Optional[float], reason: str) -> Tuple[float, Dict]:
        """Ampirik zarfa düşer ve bunu KULLANICIYA GÖRÜNÜR biçimde beyan eder.

        v2.6.27 öncesi bu düşüş yalnız sunucu günlüğüne yazılıyordu: sonuç
        sözlüğüne hiçbir iz sızmıyordu, dolayısıyla panelde ±%10 bandındaki
        kaba zarf değeri denge çözümünden gelmiş gibi görünüyordu. Beyan
        deseni aynı dosyadaki _fallback_equilibrium_composition ile birebir
        aynıdır ({'code', 'params', 'severity'}).

        reason ∈ {'cantera_unavailable', 'missing_formation_enthalpy',
                  'no_enthalpy_root', 'solver_error', 'nonphysical_temperature',
                  'condensed_carbon_unsolved'}
        ('condensed_carbon_unsolved', V301/B7: gaz dengesi karbonca aşırı
        doymuş ama gaz + C(gr) entalpi kökü çözülemedi.)
        """
        T = self._empirical_flame_temperature(elements, pressure)
        return T, {
            'temperature_source': 'empirical_envelope',
            'warning': {
                'code': 'warn.combustion.flame_temperature_empirical',
                'params': {
                    'reason': reason,
                    'of_ratio': None if of_ratio is None else float(of_ratio),
                },
                'severity': 'warning',
            },
        }

    def _empirical_flame_temperature(self, elements: Dict, pressure: float) -> float:
        """Ampirik alev sıcaklığı modeli (Cantera yokken / başarısızken).

        OPUS DENETİM DÜZELTMESİ (major): eski model karışım oranına tamamen
        duyarsızdı — aşırı yakıt-zengin uçlarda (Cantera HP'nin yakınsamadığı
        bölge) 3679 K sabit döndürüp optimum O/F aramasında sahte Isp tepesi
        üretiyordu (gerçek Tc ~1200-1600 K olmalıyken). Artık elemental
        oksijen dengesinden eşdeğerlik oranı φ türetilir ve sıcaklık
        stokiyometride tepe yapan bir zarf ile ölçeklenir:

          φ = O_gerekli / O_mevcut   (>1 yakıt-zengin, <1 fakir)
          f(φ) = 1 / (1 + a·ln²φ),  f ∈ [0.35, 1]

        Zarf, hidrokarbon/N₂O-LOX sistemlerinin CEA eğrilerinin kaba
        biçimini yakalar; fallback hassas değildir ama FİZİKSEL EĞİLİMİ taşır.

        v2.6.2 FİZİK DENETİMİ — KATSAYI YENİDEN KALİBRASYONU (bulgu F033).
        Eski katsayılar (a=0.25, basınç katsayısı k=0.05) kaynaksızdı ve
        RocketCEA referansına karşı SİSTEMATİK OLARAK SICAK veriyordu.
        Ölçülen (Pc=20 bar, N2O/HTPB + LOX/HTPB, 18 O/F noktası):
        eski model bağıl hata +%(-0.7 … +39.7), RMS %15.4 ve bias belirgin
        pozitif. Yeni katsayılar aynı 18 noktalık CEA taramasına en küçük
        kareler ile uyduruldu: RMS %6.1, bias ~sıfır.

          * Basınç katsayısı k: 0.05 -> 0.0413. RocketCEA ile 1-200 bar
            taraması (N2O/HTPB MR=6,7; LOX/HTPB MR=2.0,2.5; LOX/RP-1 MR=2.5;
            GOX/HTPB MR=2.2) T_c(200 bar)/T_c(1 bar) = 1.17…1.26 verir; bu
            altı taramaya uydurulan k ortalaması 0.0413'tür (eski 0.05, ilgili
            aralıkta %26.5 artış öngörüyordu, CEA %17-26).
          * Zarf keskinliği a: 0.25 -> 0.45. Eski değer yakıt-zengin uçta
            fazla sıcaktı (N2O/HTPB O/F=2'de +%18.5, LOX/HTPB O/F=0.8'de
            +%39.7); a=0.45 ile bu iki nokta -%10.2 ve +%7.9'a iner.

        Tepe konumu (φ=1) modelin yapısal kısıtıdır; gerçekte tepe hafif
        yakıt-zengin taraftadır (LOX/HTPB'de φ≈1.16). Tek parametreli zarf
        bunu taşıyamaz; kalan hata bandı (±%10) fallback için kabul edilmiştir.
        DOĞRU sonuç için Cantera (ya da RocketCEA yolu) kullanılmalıdır.
        """
        base_temp = 3200.0  # K (stokiyometriye yakın hidrokarbon/oksitleyici)
        if elements.get('AL', 0) > 0.1:
            base_temp += 500
        if elements.get('H', 0) > 0.1:
            base_temp += 200

        # Eşdeğerlik oranı: elemental kütle kesirlerinden oksijen dengesi.
        # Tam oksidasyon talebi (mol O atomu / kg karışım):
        #   C → CO₂ (2 O), H → H₂O (0.5 O), AL → Al₂O₃ (1.5 O)
        _M = {'C': 12.011e-3, 'H': 1.008e-3, 'O': 15.999e-3,
              'N': 14.007e-3, 'AL': 26.982e-3}
        n_C = elements.get('C', 0.0) / _M['C']
        n_H = elements.get('H', 0.0) / _M['H']
        n_O = elements.get('O', 0.0) / _M['O']
        n_AL = elements.get('AL', 0.0) / _M['AL']
        o_needed = 2.0 * n_C + 0.5 * n_H + 1.5 * n_AL
        if n_O > 1e-9 and o_needed > 1e-9:
            phi = o_needed / n_O
            factor = 1.0 / (1.0 + self._EMP_PHI_SHARPNESS * np.log(phi) ** 2)
            factor = float(np.clip(factor, 0.35, 1.0))
        else:
            factor = 1.0  # denge kurulamıyorsa eski davranış

        return base_temp * factor * (
            1.0 + self._EMP_PRESSURE_COEFF * np.log(max(pressure, 1e-3)))

    # ------------------------------------------------------------------
    # Kitap uyum B16 (Ö-1, §28) — N₂O GİRİŞ DURUMU
    # ------------------------------------------------------------------
    def set_oxidizer_inlet_state(self, temperature_k=None, phase=None):
        """N₂O oksitleyicinin giriş (enjektör) durumunu ayarlar.

        Args:
            temperature_k: giriş sıcaklığı [K]; ``None`` → hibrit motorun
                ``TANK_TEMPERATURE_DEFAULT_K`` sabiti (293,15 K, tek kaynak).
            phase: ``'liquid'`` (varsayılan, doymuş sıvı) ya da ``'gas'``
                (298,15 K standart hâl ideal gaz — kalem öncesi davranışla
                BİT-ÖZDEŞ).

        Geçersiz giriş (bilinmeyen faz; sıvıda kritik nokta üstü, üçlü nokta
        altı ya da sonlu olmayan sıcaklık) burada AÇIK HATAYLA reddedilir ve
        durum DEĞİŞMEZ (fail-closed).

        ÖNBELLEK: denge sonuçları giriş durumu başına AYRI sözlükte tutulur;
        durum değişince ``_equilibrium_cache`` o durumun sözlüğüne geçer.
        Böylece paylaşılan (UQ) bir analizör iki farklı giriş durumuyla
        sorulsa da bayat sonuç vermez ve önceki durumun hücreleri kaybolmaz.
        Boğaz istasyonu önbelleği (``_eq_station_cache``) fiziksel duruma
        (bileşim, T_c, P_c) göre anahtarlıdır; giriş entalpisi T_c'yi
        değiştirdiği için ayrı tutulması gerekmez.
        """
        from hrma.engines.oxidizer_inlet import (
            default_inlet_temperature_k, inlet_state_signature)
        T_istek = (default_inlet_temperature_k() if temperature_k is None
                   else temperature_k)
        imza = inlet_state_signature(T_istek, phase)  # doğrular; hata → çık
        varsayilan = inlet_state_signature(default_inlet_temperature_k(), None)
        if imza == varsayilan:
            imza = None  # varsayılan durum tek hücrede (kurucudaki sözlük)
        self._oxidizer_inlet_request = (temperature_k, phase)
        if imza == self._oxidizer_inlet_signature:
            return
        self._equilibrium_caches_by_inlet[
            self._oxidizer_inlet_signature] = self._equilibrium_cache
        self._equilibrium_cache = self._equilibrium_caches_by_inlet.setdefault(
            imza, {})
        self._oxidizer_inlet_signature = imza

    def oxidizer_inlet_is_default(self) -> bool:
        """Giriş durumu varsayılan mı (293,15 K doymuş sıvı)."""
        return self._oxidizer_inlet_signature is None

    def oxidizer_inlet_state(self, oxidizer_type: str = 'n2o') -> Dict:
        """HP dengesine giren oksitleyici giriş durumunun BEYANI.

        N₂O için sıcaklık, faz, kullanılan oluşum entalpisi [kJ/mol], yöntem
        ve kaynak döner (``oxidizer_inlet.n2o_inlet_state``). Diğer
        oksitleyicilerde giriş durumu ayarlanamaz; sabit referans hâli
        beyan edilir (sayı uydurulmaz, yalnız bugün kullanılanı söyler).
        """
        from hrma.engines.oxidizer_inlet import (
            default_inlet_temperature_k, n2o_inlet_state)
        ox_key = str(oxidizer_type or '').lower()
        if ox_key == 'n2o':
            if self._oxidizer_inlet_signature is None:
                durum = n2o_inlet_state(default_inlet_temperature_k(), None)
                durum['inlet_state_source'] = 'default'
            else:
                T_istek, faz = self._oxidizer_inlet_request
                if T_istek is None:
                    T_istek = default_inlet_temperature_k()
                durum = n2o_inlet_state(T_istek, faz)
                durum['inlet_state_source'] = 'configured'
            return durum
        sabit = {
            'lox': ('liquid', 'NASA CEA O2(L) card at 90.18 K '
                    '(RocketCEA input_cards.py LOX)'),
            'gox': ('gas', 'standard-state reference element, 298.15 K'),
            'o2': ('gas', 'standard-state reference element, 298.15 K'),
            'oxygen': ('gas', 'standard-state reference element, 298.15 K'),
            'h2o2': ('liquid', 'NIST Chemistry WebBook H2O2(l), 298.15 K'),
            'air': ('gas', 'standard-state reference elements, 298.15 K'),
        }.get(ox_key)
        return {
            'oxidizer': ox_key,
            'status': 'fixed_reference' if sabit else 'not_modelled',
            'phase': sabit[0] if sabit else None,
            'source': sabit[1] if sabit else None,
            'temperature_applied': False,
            'reason': ('the inlet state is configurable only for N2O; this '
                       'oxidizer is burned at the fixed reference state '
                       'named in "source".' if sabit else
                       'no reactant enthalpy is defined for this oxidizer.'),
        }

    def optimum_of_inlet_signature(self, oxidizer_type) -> tuple:
        """``find_optimum_of_ratio`` önbellek anahtarının GİRİŞ İMZASI.

        Kitap uyum B16, 2. tur (denetçi şartı Ş-5, karar §28-18). Modül
        düzeyi ``_OPTIMUM_OF_CACHE`` bütün analizörlerce paylaşılır; HP
        dengesine giren N₂O reaktan entalpisi analizörün giriş durumuna
        bağlıdır, dolayısıyla optimum O/F de. Anahtar bu imzayı taşımazsa
        farklı giriş durumlu iki istek AYNI anahtarla birbirinin sonucunu
        okur.

        1. turda bu, varsayılan dışı durumda önbelleği ``clear``/``update``
        ile GEÇİCİ olarak boşaltan bir yalıtım bağlamıyla (``isolated_
        optimum_of_cache``) çözülmüştü. O çözüm waitress ``threads=4``
        (``hrma/run.py``) altında YARIŞA açıktı: yalıtım sürerken öteki
        iş parçacığı boşaltılmış sözlüğü görüyor, bitişte geri konan yedek
        o arada eklenmiş girdileri siliyor ya da yalıtılmış aramanın
        sonucunu (aynı anahtarla) varsayılan duruma kalıcı sızdırabiliyordu.
        Anahtara imza girince yalıtım GEREKSİZLEŞTİ ve KALDIRILDI: sözlük
        artık yalnız ``in`` / ``[]`` / atama ile, farklı anahtarlarla
        kullanılır.

        İmza (N₂O): (faz, uygulanan sıcaklık [K], atanmış oluşum entalpisi
        [kJ/mol]) — üçü de ``oxidizer_inlet_state`` beyanından, yani HP
        dengesine FİİLEN giren değerden okunur. N₂O dışındaki
        oksitleyicilerde giriş durumu ayarlanamaz; imza sabittir.
        """
        ox_key = str(oxidizer_type or '').lower()
        if ox_key != 'n2o':
            return ('fixed_reference',)
        beyan = self.oxidizer_inlet_state('n2o')
        return (beyan['phase'], float(beyan['temperature_K']),
                float(beyan['formation_enthalpy_kJ_mol']))

    def _calculate_reactant_enthalpy(self, fuel_composition: Optional[Dict],
                                     oxidizer_type: Optional[str],
                                     of_ratio: Optional[float]) -> Optional[float]:
        """Reaktan karışımının kütle bazlı oluşum entalpisini döndürür (J/kg).

        h = Y_yakit * sum(w_i * Hf_i/MW_i) + Y_oks * Hf_oks/MW_oks
        (Hf [kJ/mol], MW [g/mol] -> J/kg dönüşümü: *1e6/MW)

        Yakıtlar 298,15 K oluşum entalpisiyle girer. Oksitleyici GİRİŞ
        DURUMUYLA girer: LOX sıvı (CEA O2(L) kartı, 90,18 K), H₂O₂ sıvı
        (298,15 K), N₂O ise ``set_oxidizer_inlet_state`` ile verilen durumla
        (varsayılan 293,15 K doymuş sıvı; B16).

        Eksik veri varsa None döner (çağıran ampirik yola düşer).
        """
        if not fuel_composition or not oxidizer_type or not of_ratio:
            return None

        ox_key = oxidizer_type.lower()
        if ox_key == 'n2o':
            # Kitap uyum B16 (Ö-1) — SIVI N₂O ARTIK SIVI OLARAK YAKILIYOR.
            # Burada eskiden ``spec['enthalpy_formation']`` (298,15 K ideal
            # GAZ, +82,05 kJ/mol) DOĞRUDAN okunuyordu; tank sıcaklığı ve faz
            # hiç girmiyordu. LOX dalının gerekçesi ("sıvıyı gaz referansıyla
            # yakmak buharlaşma ısısını bedava enerji sayar") N₂O için aynen
            # geçerlidir. ÖLÇÜLDÜ (KARS-TK bulgu 16, htpb/N₂O O/F 6, 30 bar,
            # ε 5): 293 K doymuş sıvıda ΔfH 70,82 kJ/mol, T_c −66 K, c*
            # −%1,43, Isp −%1,52; bağımsız NASA CEA ile −62 K, −%1,34,
            # −%1,59. Önce/sonra ve kanıt paketi:
            # docs/scofield/raw/OH/KITAP/p1a/rapor.md.
            # 'gas' fazı eski değeri BİT-ÖZDEŞ verir (bekçi testi var).
            hf_ox = self.oxidizer_inlet_state('n2o')[
                'formation_enthalpy_kJ_mol']
            mw_ox = self.propellant_specs['n2o']['molecular_weight']
        elif ox_key == 'lox':
            # D15/P1B3-03 — KRİYOJENİK ENTALPİ ARTIK DÜŞÜLÜYOR.
            # Burada eskiden `hf_ox = 0.0` yazılıydı, yani SIVI oksijen
            # 298,15 K'deki GAZ O2 referansıyla yakılıyordu; kodun kendi
            # yorumu farkı ("CEA'da ~ -0.4 MJ/kg") biliyor ama ne
            # düzeltiyor ne bildiriyordu.
            #
            # ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/hibrit/a1/once2.json ->
            # sonra2.json; aynı denge çözücüsü, tek fark reaktan entalpisi):
            #     htpb/lox   O/F 2,1  Pc 30  T_c 3601,86 K  c* 1814,63 m/s
            #     htpb/lox   O/F 2,5  Pc 50  T_c 3762,74 K  c* 1795,02 m/s
            #     paraffin/lox O/F 2,4 Pc 40 T_c 3557,87 K  c* 1830,53 m/s
            #     pe/lox     O/F 2,4  Pc 50  T_c 3612,03 K  c* 1821,00 m/s
            # Bu değerler CEA sözleşmeli çözümün +41…+48,5 K ÜSTÜNDEYDİ
            # (c* +%1,0…+1,1, Isp +%1,05…+1,21). Yön önemli: bu dosyanın
            # kendi gerekçesi T_c'yi DÜŞÜK vermenin motor boyutlandırmada
            # konservatif olduğunu söylüyor; LOX'ta tam tersi oluyordu —
            # her LOX çiftinde T_c/c*/Isp sistematik olarak İYİMSERDİ ve
            # yanıtta tek bir beyan yoktu. N2O kontrolü (+0,00 K)
            # sapmanın kaynağının bu dal olduğunu tek başına gösteriyor.
            #
            # Sayı `propellant_specs['lox']`ten okunur (tek kaynak); GOX
            # dalı bilerek ayrıdır, orada Hf = 0 doğrudur.
            spec = self.propellant_specs['lox']
            hf_ox, mw_ox = spec['enthalpy_formation'], spec['molecular_weight']
        elif ox_key in ('gox', 'o2', 'oxygen'):
            # Gaz O2, 298 K referans hali: Hf = 0 TAM doğrudur (lox'taki
            # kriyojenik yaklaşımdan farklı olarak duyulur düzeltme gerekmez).
            hf_ox, mw_ox = 0.0, 31.9988
        elif ox_key == 'h2o2':
            # Sıvı H2O2: Hf = -187.78 kJ/mol (NIST Chemistry WebBook)
            hf_ox, mw_ox = -187.78, 34.0147
        elif ox_key == 'air':
            # N2 ve O2 referans halleri, Hf = 0
            hf_ox, mw_ox = 0.0, 28.9645  # M_hava: US Standard Atmosphere 1976
        else:
            return None

        h_fuel = 0.0  # J/kg yakıt
        for fuel_type, percentage in fuel_composition.items():
            key = fuel_type.lower()
            spec = self.propellant_specs.get(key)
            if spec and 'enthalpy_formation' in spec and 'molecular_weight' in spec:
                h_fuel += (percentage / 100.0) * spec['enthalpy_formation'] * 1e6 / spec['molecular_weight']
            else:
                # Bu yakıt için Hf verisi yok -> güvenilir HP dengesi kurulamaz
                return None

        total_mass = 1.0 + of_ratio
        y_fuel = 1.0 / total_mass
        y_ox = of_ratio / total_mass

        h_ox = hf_ox * 1e6 / mw_ox  # J/kg oksitleyici
        return y_fuel * h_fuel + y_ox * h_ox

    def _elements_to_cantera_composition(self, elements: Dict) -> str:
        """Elemental KÜTLE kesirlerini Cantera atomik tür kütle-kesri string'ine çevirir.

        DİKKAT: Dönen değerler KÜTLE kesirleridir; Cantera'ya TPY/HPY gibi
        Y-tabanlı atamayla verilmelidir. Eski kod bu string'i TPX'e (mol
        kesri) veriyordu — atom ağırlıkları farklı olduğundan element mol
        oranları bozuluyordu (örn. HTPB/N2O'da C/H mol oranı ~12x hatalı).
        """
        comp_parts = []
        species_names = set(self.gas.species_names) if self.gas is not None else set()
        for element, mass_frac in elements.items():
            if mass_frac > 1e-10:  # Çok küçük değerleri filtrele
                if species_names and element not in species_names:
                    # Mekanizmada bu atomik tür yoksa (örn. AL gri30'da yok)
                    # denge çözülemez -> çağıran fallback'e düşsün
                    raise ValueError(f"Mekanizmada '{element}' türü tanımlı değil")
                comp_parts.append(f"{element}:{mass_frac:.6f}")
        return ",".join(comp_parts)
    
    # ------------------------------------------------------------------
    # V301/B7 — YOĞUN FAZ C(gr) YARDIMCILARI (model: modül başı not)
    # ------------------------------------------------------------------
    # DEĞİŞMEZ: bu yardımcılardan dönüldüğünde ``self.gas`` TOPLAM element
    # bileşimli bir GAZ dengesi durumundadır (iki fazlı çözüm gaz nesnesini
    # karbonu eksiltilmiş bileşimde bırakır; ``_yk_geri_yukle`` bunu geri
    # alır). Sebep: mevcut yollar ``gas.SP = s, P`` ile bileşimi nesneden
    # okur; eksiltilmiş bileşimle devam etmek SESSİZCE yanlış element
    # dengesi demek olurdu.
    def _yogun_karbon_kur(self):
        """C(gr) termosu ve element matrisi. Dönüş: (veri | None, neden | None)."""
        gas = self.gas
        try:
            if gas is None or 'C' not in gas.element_names:
                return None, 'mechanism_has_no_carbon'
            # Her element için TEK ATOMLU tür (bileşimi {e: 1}); ad eşlemesi
            # kullanılmaz (gri30'da element 'Ar', türü 'AR').
            atom = []
            for e in gas.element_names:
                adaylar = [k for k, sp in enumerate(gas.species())
                           if sp.composition == {e: 1.0}]
                if not adaylar:
                    return None, 'mechanism_lacks_atomic_species'
                atom.append(adaylar[0])
            turler = [sp for sp in ct.Species.list_from_file(
                CONDENSED_CARBON_THERMO_FILE)
                if sp.name == CONDENSED_CARBON_SPECIES]
            if len(turler) != 1:
                return None, 'condensed_species_not_found'
            A = np.array([[gas.n_atoms(k, m) for m in range(gas.n_elements)]
                          for k in range(gas.n_species)], dtype=float)
            iC = gas.element_index('C')
            return {
                'thermo': turler[0].thermo,
                # Gaz tarafının element kütle defteriyle AYNI atom kütlesi
                # (C(gr) bileşimi C:1); karbon kütlesi iki faz arasında
                # birebir korunur.
                'M': float(gas.atomic_weight('C')),
                'A': A,
                'iC': iC,
                'C_tur': A[:, iC] > 0.0,
                'atom_idx': np.array(atom, dtype=int),
            }, None
        except Exception as exc:  # noqa: BLE001 — beyanlı düşüş
            logger.warning(
                "Yoğun faz C(gr) termo verisi kurulamadı (%s); karbonca aşırı "
                "doymuş dengeler 'condensed_phases' beyanıyla bildirilecek.",
                exc)
            return None, 'condensed_thermo_unavailable'

    def _karbon_ln_aktivite(self) -> float:
        """Gaz nesnesi DENGEDEYKEN ln a_C(gr) = (λ_C − μ°_C(gr))/RT.

        λ (J/kmol) element potansiyelleri μ_j = Σ_i a_ij λ_i bağıntısından
        (RP-1311 eş. 2.10) mol kesri ``CONDENSED_ELEMENT_POTENTIAL_X_FLOOR``
        üstündeki türlerle en küçük kareler ile çözülür. μ°_C(gr) basınçtan
        bağımsızdır (eş. 2.11, j > NG). R, Cantera'nın kimyasal
        potansiyelleriyle AYNI sabittir (ct.gas_constant).

        BOYUT: [λ] = [μ°] = J/kmol, [RT] = J/kmol ⇒ ln a_C boyutsuz ✔.
        """
        yk = self._yk
        gas = self.gas
        X = gas.X
        mu = gas.chemical_potentials
        maske = X > CONDENSED_ELEMENT_POTENTIAL_X_FLOOR
        if not np.any(maske & yk['C_tur']):
            # Karbon taşıyan hiçbir tür tabanı aşmıyor: en bol karbonlu tür
            # eklenir (yoksa karbon aktivitesi sıfırdır).
            Xc = np.where(yk['C_tur'], X, 0.0)
            k = int(np.argmax(Xc))
            if not Xc[k] > 0.0:
                return float('-inf')
            maske = maske.copy()
            maske[k] = True
        lam = np.linalg.lstsq(yk['A'][maske], mu[maske], rcond=None)[0]
        T = float(gas.T)
        th = yk['thermo']
        g0 = th.h(T) - T * th.s(T)
        return float((lam[yk['iC']] - g0) / (ct.gas_constant * T))

    def _gaz_karbon_asiri_doymus(self) -> bool:
        """Gaz dengesi karbonca aşırı doymuş mu (ln a_C > 0)? Durumu değiştirmez."""
        if self._yk is None or self.gas is None:
            return False
        if not self.gas.elemental_mass_fraction('C') > 0.0:
            return False
        return (self._karbon_ln_aktivite()
                > CONDENSED_CARBON_LN_ACTIVITY_THRESHOLD)

    def _yk_element_kutle(self) -> np.ndarray:
        """Gaz nesnesindeki TOPLAM element kütle kesirleri (element sırası)."""
        gas = self.gas
        return np.array([gas.elemental_mass_fraction(e)
                         for e in gas.element_names], dtype=float)

    def _yk_gaz_kur(self, T: float, P_pa: float, y_el: np.ndarray,
                    eps: float) -> None:
        """Kütlece ε kadar karbonu çıkarılmış gazı T, P'de TP dengesine getirir."""
        yk = self._yk
        y = np.array(y_el, dtype=float)
        y[yk['iC']] -= eps
        y /= (1.0 - eps)
        Y = np.zeros(self.gas.n_species)
        Y[yk['atom_idx']] = np.maximum(y, 0.0)
        self.gas.TPY = float(T), float(P_pa), Y
        self.gas.equilibrate('TP')

    def _yk_karisim(self, eps: float) -> Dict:
        """Gaz nesnesinin GAZ FAZI durumu + ε kütle kesirli C(gr) → karışım.

        RP-1311 §2.2: hacim ve mol sayısı yalnız gaza, kütle tüm karışıma
        aittir ⇒ ρ = ρ_g/(1−ε), M = M_g/(1−ε) (eş. 2.3a: M = 1/n),
        h = (1−ε)h_g + ε·h_s (eş. 2.14), s = (1−ε)s_g + ε·s_s. Donmuş
        c_p, c_v Sutton & Biblarz 9. baskı eş. 3-39'un pay/paydası:
        (1−ε)c_p,g + ε·c_s, (1−ε)c_v,g + ε·c_s (yoğun fazda c_v ≈ c_p).

        BOYUT: [h_s] = (J/kmol)/(kg/kmol) = J/kg ✔; [ρ_g/(1−ε)] = kg/m³ ✔.
        """
        gas = self.gas
        yk = self._yk
        th = yk['thermo']
        M_C = yk['M']
        T = float(gas.T)
        g = 1.0 - eps
        h_s = th.h(T) / M_C
        s_s = th.s(T) / M_C
        c_s = th.cp(T) / M_C
        M_g = float(gas.mean_molecular_weight)
        n_gaz = g / M_g          # kmol gaz / kg karışım
        n_s = eps / M_C          # kmol C(gr) / kg karışım
        return {
            'T': T, 'P': float(gas.P), 'eps': float(eps),
            'h': g * float(gas.enthalpy_mass) + eps * h_s,
            's': g * float(gas.entropy_mass) + eps * s_s,
            'rho': float(gas.density) / g,
            'M': M_g / g,
            'M_gas': M_g,
            'rho_gas': float(gas.density),
            'cp': g * float(gas.cp_mass) + eps * c_s,
            'cv': g * float(gas.cv_mass) + eps * c_s,
            # CEA tanımı: yoğun tür mol kesri TÜM türlere göre (eş. 2.4b x_j)
            'x_s': n_s / (n_gaz + n_s),
            'Y_gas': np.array(gas.Y, dtype=float),
            'X_gas': np.array(gas.X, dtype=float),
        }

    def _yk_ipucu_sifirla(self) -> None:
        """İki fazlı sıcak başlangıç ipuçlarını sıfırlar (V301/B7 ardılı, 21 Eki).

        İpucu kullanan her aşama (alev sıcaklığı, istasyon bileşimi, boğaz,
        çıkış, üçlü Isp, donmuş/kayan Isp) ve ``analyze_combustion`` kendi
        başında çağırır. Gerekçe ölçüldü: boğaz istasyonu önbelleği
        (``_eq_station_cache``) bir aşamayı atladığında sonraki aşama başka
        bir ipucundan başlıyor, toleranslı kök ~1e-12 bağıl farklı bir noktada
        duruyor ve aynı girdi çağrı geçmişine göre farklı bit veriyordu. Aşama
        İÇİNDEKİ sıcak başlangıçlar (T kökünün ardışık denemeleri) korunur;
        yalnız aşamalar ARASI taşıma kesilir. Gaz-yalnız yol ipucu okumaz,
        bit-aynıdır.
        """
        self._yk_ipucu = None
        self._yk_eps_ipucu = None

    def _yk_tp(self, T: float, P_pa: float, y_el: np.ndarray,
               eps_ipucu: Optional[float] = None) -> Dict:
        """Sabit T, P'de gaz + C(gr) dengesi (iç tek boyutlu kök).

        ln a_C(ε) = 0 köklenir; f(ε) ε'da monoton azalır (gazdan karbon
        çıktıkça karbon aktivitesi düşer). f(0) ≤ 0 ise gaz doymamıştır ve
        ε = 0 döner (gaz-yalnız denge, RP-1311 eş. 3.7 ölçütü). Her
        değerlendirme MEVCUT gaz dengesidir (Cantera equilibrate('TP')).
        Gaz nesnesi GAZ FAZI dengesinde kalır (çağıran geri yükler).
        """
        yk = self._yk
        Y_C = float(y_el[yk['iC']])
        if not Y_C > 0.0:
            self._yk_gaz_kur(T, P_pa, y_el, 0.0)
            return self._yk_karisim(0.0)
        if eps_ipucu is None:
            # Aynı element bileşimiyle çözülmüş son ε (yalnız sıcak başlangıç;
            # sonuç ipucundan bağımsızdır — kök tektir).
            onceki = self._yk_eps_ipucu
            if onceki is not None and np.allclose(onceki[0], y_el,
                                                  rtol=1e-9, atol=0.0):
                eps_ipucu = onceki[1]
        esik = CONDENSED_CARBON_LN_ACTIVITY_THRESHOLD
        # Değer belleği: brentq parantez uçlarını YENİDEN değerlendirir;
        # aynı ε için aynı sayı dönsün (işaret kararlılığı).
        bellek = {}
        son_e = [None]   # gaz nesnesinin şu an kurulu olduğu ε

        def f(e):
            if e in bellek:
                return bellek[e]
            self._yk_gaz_kur(T, P_pa, y_el, e)
            son_e[0] = e
            deger = self._karbon_ln_aktivite() - esik
            bellek[e] = deger
            return deger

        xtol = CONDENSED_EPS_XTOL_REL * Y_C
        alt = ust = None
        if eps_ipucu is not None and 0.0 < eps_ipucu < Y_C:
            fe = f(eps_ipucu)
            # Hızlı yol: sıcak başlangıçtan kesen, u = ln ε değişkeninde
            # (ölçüldü: ln a_C kök komşuluğunda ln ε'a göre neredeyse
            # doğrusal, eğim ≈ −10). f monoton olduğundan (0, Y_C) içindeki
            # kök tektir; kesen kapanmazsa aşağıdaki parantezli yol (değer
            # belleği sayesinde ek maliyetsiz uçlarla) devralır.
            u_kok = _sekant_dene(
                lambda u: f(float(np.exp(u))), float(np.log(eps_ipucu)), fe,
                float(np.log(eps_ipucu)
                      + np.log1p(-CONDENSED_SECANT_FIRST_STEP_REL[0])),
                float('-inf'), float(np.log(Y_C)), CONDENSED_EPS_XTOL_REL,
                CONDENSED_LN_ACTIVITY_FTOL)
            if u_kok is not None:
                kok = float(np.exp(u_kok))
                if son_e[0] != kok:
                    self._yk_gaz_kur(T, P_pa, y_el, kok)
                self._yk_eps_ipucu = (y_el, kok)
                return self._yk_karisim(kok)
            if fe > 0.0:
                alt = eps_ipucu
                aday = eps_ipucu * (1.0 + CONDENSED_EPS_WARM_BRACKET_REL)
            else:
                ust = eps_ipucu
                aday = eps_ipucu * (1.0 - CONDENSED_EPS_WARM_BRACKET_REL)
            if 0.0 < aday < Y_C:
                fa = f(aday)
                if fa > 0.0:
                    alt = aday if alt is None else max(alt, aday)
                else:
                    ust = aday if ust is None else min(ust, aday)
        if alt is None:
            if not f(0.0) > 0.0:
                return self._yk_karisim(0.0)
            alt = 0.0
        if ust is None:
            for bosluk in CONDENSED_EPS_UPPER_GAPS:
                aday = Y_C * (1.0 - bosluk)
                if aday <= alt:
                    continue
                if f(aday) <= 0.0:
                    ust = aday
                    break
                alt = aday
            if ust is None:
                raise RuntimeError(
                    'condensed-carbon root not bracketed (T=%.3f K, '
                    'P=%.6g Pa)' % (T, P_pa))
        eps = float(brentq(f, alt, ust, xtol=xtol))
        # Gaz nesnesini KÖKTE bırak (bellekten dönen değer durumu kurmaz).
        if son_e[0] != eps:
            self._yk_gaz_kur(T, P_pa, y_el, eps)
        self._yk_eps_ipucu = (y_el, eps)
        return self._yk_karisim(eps)

    def _yk_sp(self, s_0: float, P_pa: float, y_el: np.ndarray,
               T_tahmin: Optional[float] = None,
               eps_tahmin: Optional[float] = None) -> Dict:
        """s = s_0 (KARIŞIM entropisi), P'de gaz + C(gr) dengesi.

        Dış kök T'de: s_karışım(T, P) − s_0 = 0; her T denemesi ``_yk_tp``.
        s(T) sabit P'de monoton artar (c_p,eq/T > 0). Tahmin verilmezse
        aynı izentroptaki son iki fazlı durumdan (``_yk_ipucu``) türetilir.
        Gaz nesnesi GAZ FAZI dengesinde kalır (çağıran geri yükler).
        """
        T_lo, T_hi = FLAME_T_BRACKET_K
        ipucu = getattr(self, '_yk_ipucu', None)
        if T_tahmin is None:
            if ipucu is not None and ipucu['s'] == s_0 and ipucu['P'] > 0:
                T_tahmin = ipucu['T'] * (P_pa / ipucu['P']) ** ipucu['kappa']
            elif ipucu is not None:
                T_tahmin = ipucu['T']
            else:
                T_tahmin = 0.5 * (T_lo + T_hi)
        if eps_tahmin is None and ipucu is not None:
            eps_tahmin = ipucu['eps'] if ipucu['eps'] > 0.0 else None
        son = {'eps': eps_tahmin, 'd': None}
        bellek = {}   # T -> (g, durum): brentq uç yeniden değerlendirmesi
        gecmis = []   # (T, ε>0) — ε sıcak başlangıç öngörüsü için

        def g(T):
            if T in bellek:
                son['d'] = bellek[T][1]
                return bellek[T][0]
            d = self._yk_tp(T, P_pa, y_el,
                            _eps_ongoru(gecmis, T, son['eps']))
            if d['eps'] > 0.0:
                son['eps'] = d['eps']
                gecmis.append((T, d['eps']))
            son['d'] = d
            bellek[T] = (d['s'] - s_0, d)
            return bellek[T][0]

        T0 = float(np.clip(T_tahmin, T_lo, T_hi))
        g0 = g(T0)
        kok = None
        if g0 != 0.0:
            kok = _sekant_dene(
                g, T0, g0, T0 * (1.0 + CONDENSED_SECANT_FIRST_STEP_REL[1]),
                T_lo, T_hi, CONDENSED_T_ROOT_XTOL_REL * T0,
                CONDENSED_ENTROPY_FTOL_REL * abs(s_0))
        if g0 == 0.0:
            d = son['d']
        elif kok is not None:
            d = bellek[kok][1]
        else:
            a = b = None
            for w in CONDENSED_T_WARM_BRACKET_REL:
                T1 = float(np.clip(T0 * (1.0 - w) if g0 > 0.0
                                   else T0 * (1.0 + w), T_lo, T_hi))
                if T1 == T0:
                    break
                g1 = g(T1)
                if (g1 > 0.0) != (g0 > 0.0) or g1 == 0.0:
                    a, b = min(T0, T1), max(T0, T1)
                    break
                T0, g0 = T1, g1
            if a is None:
                if (g(T_lo) > 0.0) == (g(T_hi) > 0.0):
                    raise RuntimeError(
                        'two-phase isentrope not bracketed (P=%.6g Pa)'
                        % P_pa)
                a, b = T_lo, T_hi
            T = float(brentq(g, a, b,
                             xtol=CONDENSED_T_ROOT_XTOL_REL * max(a, 1.0)))
            if T not in bellek:
                g(T)
            d = bellek[T][1]
        # NOT: gaz nesnesi son değerlendirilen durumda kalabilir; bütün
        # çağıranlar ``_yk_geri_yukle`` ile değişmezi geri kurar.
        # İpucu: aynı izentropta bir sonraki basınç için T ve (dlnT/dlnP)_s.
        kappa = None
        if ipucu is not None and ipucu['s'] == s_0 and ipucu['P'] != P_pa:
            try:
                kappa = (np.log(d['T'] / ipucu['T'])
                         / np.log(P_pa / ipucu['P']))
            except (FloatingPointError, ZeroDivisionError, ValueError):
                kappa = None
        if kappa is None or not np.isfinite(kappa):
            kappa = (d['cp'] - d['cv']) / d['cp']
        self._yk_ipucu = {'s': s_0, 'P': P_pa, 'T': d['T'],
                          'eps': d['eps'], 'kappa': float(kappa)}
        return d

    def _yk_geri_yukle(self, kayit=None, T=None, P_pa=None, y_el=None):
        """DEĞİŞMEZİ geri kurar: gaz nesnesi TOPLAM bileşimli gaz dengesinde.

        ``kayit`` = (T, P, Y) gaz-yalnız denge durumu (çözüm yok, yalnız
        atama); yoksa T, P'de toplam bileşimle gaz-yalnız TP dengesi kurulur.
        """
        if kayit is not None:
            self.gas.TPY = kayit
        else:
            self._yk_gaz_kur(T, P_pa, y_el, 0.0)

    def _yk_donmus_sp(self, Y_gaz: np.ndarray, eps: float, s_0: float,
                      P_pa: float, T_tahmin: float) -> Dict:
        """Bileşimi DONDURULMUŞ gaz + C(gr) karışımının s = s_0, P durumu.

        CEA donmuş kipleri (nfz): gaz bileşimi ve yoğun kütle kesri sabit,
        iki faz ısıl dengede. (1−ε)s_g(T, P) + ε·s_s(T) = s_0 sabit nokta
        yinelemesiyle çözülür: s_g hedefi (s_0 − ε·s_s(T_k))/(1−ε), T_{k+1}
        Cantera ``SP`` atamasıyla (bileşim sabit). Daralma oranı
        ~ε·c_s/((1−ε)c_p,g) ≪ 1. Gaz nesnesi o durumda kalır.
        """
        gas = self.gas
        th = self._yk['thermo']
        M_C = self._yk['M']
        g = 1.0 - eps
        T = float(T_tahmin)
        for _ in range(CONDENSED_FROZEN_T_MAX_ITER):
            s_hedef = (s_0 - eps * th.s(T) / M_C) / g
            gas.TPY = T, P_pa, Y_gaz
            gas.SP = s_hedef, P_pa
            T_yeni = float(gas.T)
            if abs(T_yeni - T) <= CONDENSED_T_ROOT_XTOL_REL * T:
                T = T_yeni
                break
            T = T_yeni
        else:
            raise RuntimeError('frozen two-phase expansion did not converge')
        return self._yk_karisim(eps)

    def _yk_bilesim(self, T: float, P_pa: float) -> Dict:
        """Gaz + C(gr) istasyon bileşimi (``_calculate_equilibrium_composition``
        sözleşmesi + yoğun faz beyanı).

        Çağrıldığında gaz nesnesi T, P'de TOPLAM bileşimli gaz-yalnız
        dengededir; dönüşte aynı duruma geri yüklenir.

        Yayımlanan alanlar KARIŞIM tanımındadır (RP-1311 §2.2 / CEA):
          density = ρ_g/(1−ε), molecular_weight = M = 1/n = M_g/(1−ε),
          enthalpy/entropy karışım, cp/cv donmuş karışım (Sutton eş. 3-39),
          gamma = γ_s = dlnP/dlnρ|_s,eq (eş. 2.71, iki fazlı izentrop),
          'species' GAZ FAZININ kesirleridir (toplamı 1), yoğun tür ayrı
          anahtarda: 'condensed_species' / 'condensed_mass_fraction'.
        """
        gas = self.gas
        kayit = (float(gas.T), float(gas.P), np.array(gas.Y, dtype=float))
        y_el = self._yk_element_kutle()
        try:
            d0 = self._yk_tp(T, P_pa, y_el)
            names = gas.species_names
            composition = {}
            for i, species in enumerate(names):
                if d0['X_gas'][i] > 1e-10:
                    composition[species] = {
                        'mole_fraction': d0['X_gas'][i],
                        'mass_fraction': d0['Y_gas'][i],
                    }
            gamma_frozen = d0['cp'] / d0['cv']
            gamma_eq = gamma_frozen
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        'ignore', message=r'.*outside valid range.*',
                        category=UserWarning)
                    d1 = self._yk_sp(
                        d0['s'], d0['P'] * COMPOSITION_GAMMA_PRESSURE_PERTURBATION,
                        y_el, T_tahmin=d0['T'],
                        eps_tahmin=d0['eps'] if d0['eps'] > 0.0 else None)
                n_s = np.log(d1['P'] / d0['P']) / np.log(d1['rho'] / d0['rho'])
                if (COMPOSITION_GAMMA_PHYSICAL_BAND[0] < n_s
                        < COMPOSITION_GAMMA_PHYSICAL_BAND[1]):
                    gamma_eq = float(n_s)
            except Exception:  # noqa: BLE001 — donmuş üsse düşülür (aynı sözleşme)
                gamma_eq = gamma_frozen
        finally:
            self._yk_geri_yukle(kayit)
        out = {
            'species': composition,
            'temperature': d0['T'],
            'pressure': d0['P'] / 1e5,
            'density': d0['rho'],
            'molecular_weight': d0['M'],
            'cp': d0['cp'],
            'cv': d0['cv'],
            'gamma': gamma_eq,
            'gamma_frozen': gamma_frozen,
            'enthalpy': d0['h'],
            'entropy': d0['s'],
        }
        if d0['eps'] > 0.0:
            out.update({
                'condensed_species': {CONDENSED_CARBON_SPECIES: {
                    'mass_fraction': d0['eps'],
                    'mole_fraction': d0['x_s'],
                }},
                'condensed_mass_fraction': d0['eps'],
                'gas_molecular_weight': d0['M_gas'],
                'gas_density': d0['rho_gas'],
                'phase_basis': CONDENSED_PHASE_BASIS_TEXT,
            })
        return out

    def _yk_beyan(self, *istasyonlar) -> Dict:
        """Analiz sonucunun 'condensed_phases' beyanı (V301/B7).

        status:
          'present'      — en az bir istasyon gaz + C(gr) dengesi; istasyon
                           başına yoğun kütle kesri yayımlanır,
          'absent'       — denge denetlendi, hiçbir istasyonda gaz karbonca
                           aşırı doymuş değil (yalnız metin; sayı yok),
          'unavailable'  — Cantera denge yolu var ama C(gr) verisi
                           kurulamadı (adlı gerekçe),
          'not_modelled' — Cantera yok, ampirik yol.
        """
        adlar = ('chamber', 'throat', 'exit')
        olcut = ('C(gr) enters the equilibrium where the gas-phase '
                 'equilibrium is carbon-supersaturated, ln a_C > 0 '
                 '(NASA RP-1311 Part I eq. 3.7); evaluated at every state')
        if not self.cantera_available:
            return {'status': 'not_modelled',
                    'reason': 'cantera_unavailable'}
        if self._yk is None:
            return {'status': 'unavailable', 'reason': self._yk_neden,
                    'species_admitted': CONDENSED_CARBON_SPECIES}
        kesir = {}
        for ad, comp in zip(adlar, istasyonlar):
            if isinstance(comp, dict) and 'condensed_mass_fraction' in comp:
                kesir[ad] = comp['condensed_mass_fraction']
        if not kesir:
            return {'status': 'absent',
                    'species_admitted': CONDENSED_CARBON_SPECIES,
                    'criterion': olcut}
        return {
            'status': 'present',
            'species_admitted': CONDENSED_CARBON_SPECIES,
            'criterion': olcut,
            'condensed_mass_fraction': {
                ad: kesir.get(ad, 0.0) for ad in adlar},
            'stations_with_condensed_phase': [
                ad for ad in adlar if ad in kesir],
            'basis': CONDENSED_PHASE_BASIS_TEXT,
        }

    def _denge_sp(self, s_0: float, P_pa: float, yk_baglam: Optional[Dict] = None,
                  T_tahmin: Optional[float] = None,
                  eps_tahmin: Optional[float] = None) -> Dict:
        """s = s_0, P'de denge durumu; gerekirse gaz + C(gr).

        * ``yk_baglam['aktif']`` (oda iki fazlı): doğrudan iki fazlı çözüm.
        * Aksi hâlde BUGÜNKÜ gaz-yalnız SP dengesi (bit-aynı işlem sırası);
          sonuç karbonca aşırı doymuşsa iki fazlı çözüme geçilir.
        Dönüş: {'P', 'T', 'rho', 'h', 'eps', 'Y_gas'}; gaz nesnesi değişmezde.
        """
        gas = self.gas
        if yk_baglam is not None and yk_baglam.get('aktif'):
            y_el = yk_baglam['y_el']
            d = self._yk_sp(s_0, P_pa, y_el, T_tahmin, eps_tahmin)
            self._yk_geri_yukle(T=d['T'], P_pa=d['P'], y_el=y_el)
            return d
        gas.SP = s_0, P_pa
        gas.equilibrate('SP')
        if self._gaz_karbon_asiri_doymus():
            kayit = (float(gas.T), float(gas.P), np.array(gas.Y, dtype=float))
            y_el = self._yk_element_kutle()
            try:
                d = self._yk_sp(s_0, P_pa, y_el,
                                T_tahmin if T_tahmin is not None
                                else kayit[0], eps_tahmin)
            finally:
                self._yk_geri_yukle(kayit)
            return d
        return {'P': float(gas.P), 'T': float(gas.T),
                'rho': float(gas.density), 'h': float(gas.enthalpy_mass),
                'eps': 0.0, 'Y_gas': None}

    def _calculate_equilibrium_composition(self, elements: Dict, pressure: float, 
                                         temperature: float, station: str) -> Dict:
        """Calculate chemical equilibrium composition using Cantera"""
        self._yk_ipucu_sifirla()   # V301/B7 ardılı: aşama belirlenimci başlar
        
        if not self.cantera_available:
            # Fallback basit model
            return self._fallback_equilibrium_composition(elements, pressure, temperature, station)
        
        try:
            # Cantera ile kimyasal denge hesaplama.
            # Elemental KÜTLE kesirleri atomik türlerin kütle kesri olarak
            # atanır -> TPY kullanılır (TPX mol kesri ister; eski TPX
            # kullanımı element oranlarını ~atom ağırlığı kadar bozuyordu).
            comp_str = self._elements_to_cantera_composition(elements)
            self.gas.TPY = temperature, pressure * 1e5, comp_str
            self.gas.equilibrate('TP')  # Constant temperature and pressure

            # V301/B7: gaz dengesi karbonca aşırı doymuşsa istasyon gaz +
            # C(gr) dengesidir. Doymamışsa aşağıdaki yol BİT-AYNI.
            if self._gaz_karbon_asiri_doymus():
                return self._yk_bilesim(temperature, pressure * 1e5)
            
            # Sonuçları çıkar
            composition = {}
            species_names = self.gas.species_names
            mole_fractions = self.gas.X
            mass_fractions = self.gas.Y
            
            for i, species in enumerate(species_names):
                if mole_fractions[i] > 1e-10:  # Sadece anlamlı miktarları dahil et
                    composition[species] = {
                        'mole_fraction': mole_fractions[i],
                        'mass_fraction': mass_fractions[i]
                    }

            # Denge durumu skalerlerini SP pertürbasyonundan ÖNCE oku
            T0 = self.gas.T
            P0 = self.gas.P
            rho0 = self.gas.density
            mw0 = self.gas.mean_molecular_weight
            cp0 = self.gas.cp
            cv0 = self.gas.cv
            h0 = self.gas.enthalpy_mass
            s0 = self.gas.entropy_mass
            Y0 = self.gas.Y

            # Isentropik üs (gamma): NASA CEA c*'ı "shifting equilibrium"
            # üssüyle hesaplar. Frozen cp/cv yüksek sıcaklıkta disosiyasyonu
            # (CO2<->CO+1/2 O2, H2O<->OH+1/2 H2 vb.) yok sayıp gamma'yı ~%7-9
            # fazla, dolayısıyla c*'ı ~%4 düşük verir. Sabit-entropili küçük
            # bir basınç pertürbasyonunda denge yeniden çözülerek
            # n_s = dlnP/dln(rho)|_s,eq hesaplanır (Gordon & McBride, NASA
            # RP-1311). Yakınsamazsa frozen cp/cv değerine düşülür.
            gamma_frozen = cp0 / cv0
            gamma_eq = gamma_frozen
            try:
                # GRI-Mech termo polinomları 300-3000 K için fit'li; denge
                # çözümü 3000-3025 K bandına <%1 taşabiliyor (Cantera
                # UserWarning basar). Ekstrapolasyon bilinçli kabul:
                # sapma küçük, yakınsamazsa zaten frozen gamma'ya düşülür.
                # Uyarı test/konsol gürültüsü yaratmasın diye burada filtreli.
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        'ignore',
                        message=r'.*outside valid range.*',
                        category=UserWarning,
                    )
                    self.gas.SP = s0, P0 * COMPOSITION_GAMMA_PRESSURE_PERTURBATION
                    self.gas.equilibrate('SP')
                    if self._gaz_karbon_asiri_doymus():
                        # V301/B7: pertürbe durum karbonca aşırı doymuş
                        # (sınır komşuluğu): o durum gaz + C(gr) dengesidir.
                        _y_el = self._yk_element_kutle()
                        _d1 = self._yk_sp(
                            s0, P0 * COMPOSITION_GAMMA_PRESSURE_PERTURBATION,
                            _y_el, T_tahmin=float(self.gas.T))
                        P1, rho1 = _d1['P'], _d1['rho']
                    else:
                        P1 = self.gas.P
                        rho1 = self.gas.density
                n_s = np.log(P1 / P0) / np.log(rho1 / rho0)
                if (COMPOSITION_GAMMA_PHYSICAL_BAND[0] < n_s
                        < COMPOSITION_GAMMA_PHYSICAL_BAND[1]):
                    # fiziksel yanma gazı bandı
                    gamma_eq = n_s
            except Exception:
                gamma_eq = gamma_frozen
            finally:
                # Gaz durumunu denge bileşimine geri yükle (sonraki çağrılar için)
                self.gas.TPY = T0, P0, Y0

            return {
                'species': composition,
                'temperature': T0,
                'pressure': P0 / 1e5,  # bar cinsinden
                'density': rho0,
                'molecular_weight': mw0,
                'cp': cp0,
                'cv': cv0,
                'gamma': gamma_eq,             # shifting-equilibrium isentropik üs
                'gamma_frozen': gamma_frozen,  # referans (frozen cp/cv)
                'enthalpy': h0,
                'entropy': s0
            }
            
        except Exception as e:
            # Hata durumunda fallback (durumu logla — sessiz yutma yok)
            logger.warning(
                "Cantera TP denge çözümü başarısız (istasyon=%s): %s; "
                "ampirik bileşim modeline düşülüyor.", station, e
            )
            return self._fallback_equilibrium_composition(elements, pressure, temperature, station)
    
    # Fallback yolunda kullanılan tür molekül ağırlıkları [kg/kmol] — NIST-JANAF
    _FALLBACK_SPECIES_MW = {
        'CO2': 44.0095, 'CO': 28.0101, 'H2O': 18.01528, 'H2': 2.01588,
        'N2': 28.0134, 'O2': 31.9988, 'OH': 17.007, 'H': 1.008, 'O': 15.999,
        'NO': 30.006, 'AL2O3_l': 101.96, 'AL2O3_s': 101.96, 'AL': 26.982,
    }

    # Atom kütleleri [g/mol] — IUPAC 2021 standart atom ağırlıkları
    _ATOMIC_MASS = {'C': 12.011, 'H': 1.008, 'O': 15.999,
                    'N': 14.007, 'AL': 26.982}

    # --- ÖH D19 (kalem B3-12) — REAKTAN MOLEKÜL AĞIRLIĞI TEK KAYNAK ------
    # Reaktanların elemental ayrıştırılmasında molekül ağırlığı ARTIK ELLE
    # YAZILMIYOR; buradaki formülden ve yukarıdaki _ATOMIC_MASS tablosundan
    # TÜRETİLİYOR. Kusur şuydu: pay (atom kütleleri) ile payda (molekül
    # ağırlığı) ayrı ayrı elle yazıldığı için elemental kütle kesirleri 1'e
    # KAPANMIYORDU. ÖLÇÜLDÜ (once.json, B3_12; taban 60cd341):
    #     saf yakıt Σ(kütle kesri):
    #       htpb 1,001851851851852 (+%0,1852)  <- 4·12,01/54,0 + 6·1,01/54,0
    #       pe   1,000356506238859  | paraffin 1,000293547818940
    #       pla  1,000138773244518  | abs      1,000096015362458
    #       pmma 1,000099880143827  | aluminum 1,0 (tek atom, tanım gereği)
    #     saf oksitleyici Σ: n2o 1,000227221085890 | h2o2 1,000294031167010
    #                        air 1,000274401999012 | lox  1,0
    #     dengeye giren efektif O/F (kullanıcı 6,0 istedi):
    #       htpb+n2o 5,990270233491716 (−%0,1622)
    #       htpb+lox 5,988909426987060 (−%0,1848)
    # Yani kullanıcının gönderdiği O/F çözülen O/F DEĞİLDİ (girdi yankısı
    # sınıfı). Ayrıca aynı dosyada HTPB üç molekül ağırlığıyla yazılıydı:
    # propellant_specs 54,09 ⟷ elemental bölen 54,0 ⟷ species_data 54,0;
    # dosyanın KENDİ atom kütleleriyle C4H6 = 54,092. Tek kaynak: formül.
    # (Çapraz doğrulama: N2O için türetilen 44,013 propellant_specs'teki
    # değerin BİREBİR aynısıdır — tablo IUPAC 2021 ile tutarlı.)
    _REACTANT_FORMULAS = {
        # Yakıtlar (yaklaşıklık notları _calculate_elemental_composition'da)
        'paraffin': {'C': 12, 'H': 26},    # C12H26 yaklaşımı
        'htpb': {'C': 4, 'H': 6},          # C4H6 monomer yaklaşımı
        'aluminum': {'AL': 1},
        'abs': {'C': 8, 'H': 8},           # C8H8 basitleştirmesi
        'pla': {'C': 3, 'H': 4, 'O': 2},   # C3H4O2
        'pe': {'C': 2, 'H': 4},            # C2H4
        'pmma': {'C': 5, 'H': 8, 'O': 2},  # C5H8O2
        # Oksitleyiciler
        'n2o': {'N': 2, 'O': 1},
        'o2': {'O': 2},
        'h2o2': {'H': 2, 'O': 2},
    }

    @classmethod
    def _formula_molar_mass(cls, species_key: str) -> float:
        """Formülden molekül ağırlığı [g/mol] — reaktanlar için TEK KAYNAK.

        Pay ve payda aynı tablodan geldiği için Σ(kütle kesri) tanım gereği
        1,0'dır (kütle korunumu float yuvarlamasına kadar kapanır).
        """
        formul = cls._REACTANT_FORMULAS[species_key]
        return sum(cls._ATOMIC_MASS[el] * n for el, n in formul.items())

    # Su-gaz kayması (water-gas shift) denge sabiti:
    #     CO + H2O <-> CO2 + H2 ,  K = (X_CO2·X_H2)/(X_CO·X_H2O)
    # ln K = A/T + B. Katsayılar NASA polinom termodinamiğinden (GRI-Mech 3.0
    # / NASA-JANAF standart Gibbs enerjileri) 1500-4000 K bandında en küçük
    # kareler ile çıkarıldı; bant içi en büyük sapma K'de %6.7'dir.
    # (Denge sabiti mol sayısı korunduğu için BASINÇTAN bağımsızdır.)
    _WGS_LNK_A = 2918.8606
    _WGS_LNK_B = -2.96062

    # Al2O3 ergime sıcaklığı [K] (NIST-JANAF) — yoğuşmuş faz etiketi için
    _AL2O3_MELT_K = 2327.0

    # Ampirik alev sıcaklığı zarfı katsayıları (yalnız Cantera YOKKEN etkin).
    # RocketCEA taramasına uydurulmuştur — gerekçe ve ölçüm için
    # _empirical_flame_temperature docstring'ine bakın (bulgu F033).
    _EMP_PRESSURE_COEFF = 0.0413   # T ~ (1 + k·ln P);  eski kaynaksız değer 0.05
    _EMP_PHI_SHARPNESS = 0.45      # f(φ) = 1/(1 + a·ln²φ); eski kaynaksız değer 0.25

    def _atom_balance_composition(self, elements: Dict,
                                  temperature: float) -> Dict[str, float]:
        """Elemental kütle kesirlerinden ürün MOL kesirlerini çözer.

        Bkz. _fallback_equilibrium_composition docstring'i (yöntem, kaynak,
        sınırlamalar). Döndürülen sözlük mol kesirleridir (toplam 1.0).

        Girdi `elements`: {'C','H','O','N','AL'} -> kg element / kg karışım.
        """
        m = self._ATOMIC_MASS
        # mol/kg karışım
        n_c = max(elements.get('C', 0.0), 0.0) * 1000.0 / m['C']
        n_h = max(elements.get('H', 0.0), 0.0) * 1000.0 / m['H']
        n_o = max(elements.get('O', 0.0), 0.0) * 1000.0 / m['O']
        n_n = max(elements.get('N', 0.0), 0.0) * 1000.0 / m['N']
        n_al = max(elements.get('AL', 0.0), 0.0) * 1000.0 / m['AL']

        moles: Dict[str, float] = {}

        # 1) Alüminyum: 2 Al + 3/2 O2 -> Al2O3 (O atom talebi 3 mol / mol Al2O3)
        n_al2o3 = min(n_al / 2.0, n_o / 3.0) if n_al > 0.0 else 0.0
        if n_al2o3 > 0.0:
            key = 'AL2O3_l' if temperature >= self._AL2O3_MELT_K else 'AL2O3_s'
            moles[key] = n_al2o3
            # Oksitlenemeyen alüminyum artığı (aşırı yakıt-zengin metalize)
            n_al_left = n_al - 2.0 * n_al2o3
            if n_al_left > 1e-9:
                moles['AL'] = n_al_left
        o_free = max(n_o - 3.0 * n_al2o3, 0.0)

        # 2) C ve H arasında oksijen paylaşımı
        o_needed = 2.0 * n_c + 0.5 * n_h          # tam oksidasyon talebi
        if o_free >= o_needed:
            # Oksijen fazlası (yakıt-fakir): tam oksidasyon + artık O2
            a, b = n_c, 0.0                        # CO2, CO
            c, d = n_h / 2.0, 0.0                  # H2O, H2
            o2_excess = 0.5 * (o_free - o_needed)
            if o2_excess > 1e-9:
                moles['O2'] = o2_excess
        elif n_c <= 1e-12:
            # Karbonsuz yakıt (ör. saf Al ya da H2): O tümüyle H2O'ya gider
            a = b = 0.0
            c = min(o_free, n_h / 2.0)
            d = max(n_h / 2.0 - c, 0.0)
        else:
            # Yakıt-zengin: su-gaz kayması dengesi
            # b = n_c - a ; c = o_free - n_c - a ; d = n_h/2 - c
            # K = a·d/(b·c)  ->  (1-K)a² + (P + K·o_free)a - K·n_c(o_free-n_c) = 0
            # (P = n_h/2 - o_free + n_c)
            k_wgs = float(np.exp(self._WGS_LNK_A / max(temperature, 300.0)
                                 + self._WGS_LNK_B))
            p_lin = n_h / 2.0 - o_free + n_c
            aa = 1.0 - k_wgs
            bb = p_lin + k_wgs * o_free
            cc = -k_wgs * n_c * (o_free - n_c)
            # a fiziksel bandı: CO2 hem karbonla hem oksijenle sınırlı
            a_max = max(min(n_c, 0.5 * o_free), 0.0)
            if abs(aa) < 1e-12:
                a = -cc / bb if abs(bb) > 1e-12 else 0.0
            else:
                disc = max(bb * bb - 4.0 * aa * cc, 0.0)
                root_hi = (-bb + np.sqrt(disc)) / (2.0 * aa)
                root_lo = (-bb - np.sqrt(disc)) / (2.0 * aa)
                a = root_hi if 0.0 <= root_hi <= a_max else root_lo
            a = float(np.clip(a, 0.0, a_max))
            b = max(n_c - a, 0.0)
            c = max(o_free - n_c - a, 0.0)
            d = max(n_h / 2.0 - c, 0.0)

        for name, val in (('CO2', a), ('CO', b), ('H2O', c), ('H2', d)):
            if val > 1e-12:
                moles[name] = val

        # 3) Azot -> N2 (fallback'te NO/NO2 ihmal, bkz. docstring sınırlamalar)
        if n_n > 1e-12:
            moles['N2'] = 0.5 * n_n

        total = sum(moles.values())
        if total <= 0.0:
            # Hiçbir ürün türetilemedi (tüm elementler sıfır): fiziksel olmayan
            # girdi. Sessizce sahte bileşim döndürmek yerine açık hata ver.
            raise ValueError(
                "Fallback equilibrium: elemental composition is empty; "
                "cannot derive product species.")
        return {sp: n / total for sp, n in moles.items()}

    def _fallback_equilibrium_composition(self, elements: Dict, pressure: float,
                                        temperature: float, station: str) -> Dict:
        """Cantera yokken kullanılan denge bileşimi modeli (atom dengesi + WGS).

        DÜZELTME (v2.6.2 fizik denetimi, bulgu F005). ESKİ DAVRANIŞ: istasyona
        göre SABİT bir tür sözlüğü ({'CO2':0.22,'CO':0.08,'H2O':0.12,
        'N2':0.54,...}) döndürülüyordu. Bileşim itici çiftinden TAMAMEN
        bağımsızdı: LOX/HTPB gibi hiç azot içermeyen bir çiftte bile ürünlerin
        %54'ü N2 sayılıyor, karışım molekül ağırlığı her çiftte 29.6 g/mol'e
        çakılıyordu. Ölçülen etki (RocketCEA referansına karşı, cantera kapalı):
        htpb/n2o O/F=6 Pc=20 bar c* -%4.4; htpb/lox O/F=2 Pc=40 bar c* -%13.4.
        Cantera requirements.txt'te OLMADIĞI için bu yol temiz kurulumda
        VARSAYILANDIR — yani hata gerçek kullanıcıya ulaşıyordu.

        YENİ DAVRANIŞ — elemental atom dengesinden türetilen kapalı-form çözüm:
          1) Al önce oksitlenir: 2 Al + 3/2 O2 -> Al2O3 (yoğuşmuş).
             (Al2O3 oluşum entalpisi tüm ana ürünlerden büyüktür; CEA
             çözümlerinde alüminyum pratikte tam oksitlenir — Sutton &
             Biblarz 9. baskı Böl. 12, metalize yakıtlar.)
          2) Kalan oksijen C ve H arasında paylaşılır. Oksijen fazlaysa tam
             oksidasyon (CO2 + H2O + artık O2), yakıt zenginse CO/CO2 ve
             H2/H2O dağılımı su-gaz kayması dengesinden çözülür:
                 C dengesi : a + b = n_C            (a=CO2, b=CO)
                 H dengesi : c + d = n_H/2          (c=H2O, d=H2)
                 O dengesi : 2a + b + c = n_O_kalan
                 WGS       : K(T) = a·d / (b·c)
             Bu dört denklem a için TEK bir ikinci derece denkleme indirgenir
             (aşağıda), yani iterasyon gerekmez.
          3) N tümüyle N2'ye gider (fallback'te NO/NO2 ihmal).

        BİLİNEN SINIRLAMA: ayrışma (OH, H, O, NO) modellenmez. Bu, karışım
        molekül ağırlığını gerçek denge değerinden SİSTEMATİK OLARAK ~%1.5-2
        YÜKSEK verir (ölçüldü: htpb/n2o 26.32 vs CEA 25.88 = +%1.7;
        htpb/lox 23.14 vs CEA 22.78 = +%1.6) ve dolayısıyla c*'ı biraz DÜŞÜK
        (konservatif) verir. Eski sabit sözlüğün hatası aynı vakalarda
        +%14.4 ve +%30.0 idi. Kesin sonuç için Cantera kurulmalıdır.

        Kaynak: kütle/atom korunumu (Gordon & McBride, NASA RP-1311 Part I,
        element denge kısıtları); su-gaz kayması dengesi için NASA-JANAF
        standart Gibbs enerjileri (bkz. _WGS_LNK_A/_WGS_LNK_B).

        SÖZLEŞME: Cantera yolu (_calculate_equilibrium_composition) ile AYNI
        şekilde döner: {'species', 'temperature', 'pressure', 'density',
        'molecular_weight', 'cp', 'cv', 'gamma', 'gamma_frozen', 'enthalpy',
        'entropy'}. (Eski sürüm yalnız düz tür-kesri sözlüğü döndürüyordu;
        tüketiciler comp['gamma'] okuduğu için Cantera'sız makinelerde
        /calculate KeyError('gamma') ile 400 dönüyordu — 2026-07-12 saha
        hatası.)
        """
        composition = self._atom_balance_composition(elements, temperature)

        # ---- Cantera sözleşmesiyle aynı şekle getir ----
        # Karışım molekül ağırlığı: MW = Σ X_i·M_i (mol kesirleri üzerinden)
        mw_mix = sum(x * self._FALLBACK_SPECIES_MW.get(sp, 28.0)
                     for sp, x in composition.items())
        mw_mix = max(mw_mix, 2.0)  # sayısal güvenlik

        # Kütle kesirleri: Y_i = X_i·M_i / MW
        species = {
            sp: {
                'mole_fraction': x,
                'mass_fraction': x * self._FALLBACK_SPECIES_MW.get(sp, 28.0) / mw_mix,
            }
            for sp, x in composition.items() if x > 1e-10
        }

        # Kaba, sıcaklığa bağlı izentropik üs tahmini (tipik yanma gazı:
        # ~1.25 @ 2000 K, ~1.21 @ 3000 K; Sutton & Biblarz 9. baskı Böl. 3
        # mertebeleriyle uyumlu). [1.18, 1.33] bandına kırpılır.
        gamma_est = min(1.33, max(1.18, 1.33 - 4.0e-5 * temperature))

        R_specific = self.R_universal / mw_mix          # J/(kg·K)
        cp_mass = gamma_est * R_specific / (gamma_est - 1.0)
        cv_mass = cp_mass / gamma_est
        p_pa = pressure * 1e5
        rho = p_pa / (R_specific * temperature)         # ideal gaz
        # Duyulur entalpi/entropi (298.15 K referanslı) — istasyonlar arası
        # FARKLAR anlamlıdır; mutlak değerler kaba tahmindir.
        h_mass = cp_mass * (temperature - 298.15)
        s_mass = (cp_mass * np.log(temperature / 298.15)
                  - R_specific * np.log(max(pressure, 1e-6) / 1.01325))

        return {
            'species': species,
            'temperature': temperature,
            'pressure': pressure,               # bar
            'density': rho,
            'molecular_weight': mw_mix,
            'cp': cp_mass,
            'cv': cv_mass,
            'gamma': gamma_est,
            'gamma_frozen': gamma_est,
            'enthalpy': h_mass,
            'entropy': s_mass,
            'source': 'atom_balance_fallback',
            # Kullanıcıya görünür dürüstlük bayrağı: bu istasyon Cantera denge
            # çözümünden DEĞİL, atom dengesi + su-gaz kayması yaklaşımından
            # gelmiştir (ayrışma modellenmez, MW ~%2 yüksek).
            'warning': {
                'code': 'warn.combustion.equilibrium_fallback',
                'params': {'station': station},
                'severity': 'warning',
            },
        }
    
    # ------------------------------------------------------------------
    # ÖH D18 fizik-a1 / F1 — kayan-denge istasyon çözücüsü (B3-05 + B3-02)
    # ------------------------------------------------------------------
    def _equilibrium_isentrope_state(self, s_0: float, h_0: float,
                                     P_pa: float,
                                     yk_baglam: Optional[Dict] = None) -> Dict:
        """s = s_0 izentropunda P_pa basıncındaki kayan-denge akış durumu.

        Döndürülen sözlük [SI]: P [Pa], T [K], rho [kg/m³], h [J/kg],
        v [m/s], G [kg/(m²·s)] = rho·v.

        Yöntem (NASA RP-1311 Part I §6.3.3; Sutton & Biblarz 9. baskı
        Eş. 3-15b): h(P) izentropik denge çözümünden (Cantera ``SP`` +
        ``equilibrate``) alınır, v = sqrt(2(h_0 − h)).

        BOYUT SAĞLAMASI: [h] = J/kg = m²/s² ⇒ [sqrt(2Δh)] = m/s ✔;
        [G] = (kg/m³)(m/s) = kg/(m²·s) ✔.
        (Betik: ``docs/scofield/raw/OH/D18/fizik/a1/boyut.py``)

        V301/B7: durum ``_denge_sp`` ile çözülür — gaz dengesi karbonca
        aşırı doymuşsa (ya da oda iki fazlıysa, ``yk_baglam``) gaz + C(gr);
        ρ ve h KARIŞIM değerleridir (RP-1311 §2.2), dolayısıyla G = ρv
        toplam kütle akısıdır (c* = P_c/G_t tanımı yoğun fazla da geçerli).
        Doymamış durumda işlem sırası ve sayılar bugünküyle BİT-AYNI.
        """
        d = self._denge_sp(s_0, P_pa, yk_baglam)
        P0 = d['P']
        rho0 = d['rho']
        h = d['h']
        v = float(np.sqrt(2.0 * max(h_0 - h, 0.0)))
        return {'P': P0, 'T': d['T'], 'rho': rho0, 'h': h, 'v': v,
                'G': rho0 * v, 'eps': d['eps']}

    def _equilibrium_sound_speed(self, s_0: float, durum: Dict,
                                 yk_baglam: Optional[Dict] = None) -> float:
        """``durum`` noktasında denge ses hızı a_eq [m/s].

        n_s = ln(P₂/P₁)/ln(ρ₂/ρ₁) sabit entropide sonlu farkla alınır
        (``EQ_STATION_SOUND_SPEED_PERTURBATION``); a = sqrt(n_s·P/ρ).
        Donmuş γ DEĞİL denge üsteli kullanılır (RP-1311 §6.3.3).

        BOYUT SAĞLAMASI: [n_s·P/ρ] = Pa·m³/kg = m²/s² ⇒ [a] = m/s ✔.

        V301/B7: iki fazlı durumda ρ karışım yoğunluğudur ve pertürbe durum
        da gaz + C(gr) dengesidir: a² = γ_s·P/ρ = nRTγ_s (RP-1311 eş. 2.74).
        """
        P0, rho0 = durum['P'], durum['rho']
        if durum.get('eps', 0.0) > 0.0 and not (
                yk_baglam is not None and yk_baglam.get('aktif')):
            # Gaz-yalnız odalı zincirde iki fazlı istasyon: pertürbe durum da
            # iki fazlı çözülür (gaz nesnesi toplam bileşimde — değişmez).
            y_el = self._yk_element_kutle()
            d1 = self._yk_sp(s_0, P0 * EQ_STATION_SOUND_SPEED_PERTURBATION,
                             y_el, T_tahmin=durum['T'],
                             eps_tahmin=durum['eps'])
            self._yk_geri_yukle(T=d1['T'], P_pa=d1['P'], y_el=y_el)
        else:
            d1 = self._denge_sp(s_0, P0 * EQ_STATION_SOUND_SPEED_PERTURBATION,
                                yk_baglam, T_tahmin=durum['T'],
                                eps_tahmin=durum.get('eps') or None)
        n_s = float(np.log(d1['P'] / P0) / np.log(d1['rho'] / rho0))
        return float(np.sqrt(max(n_s, 1e-9) * P0 / rho0))

    def _solve_equilibrium_throat(self, comp_str: str, T_c: float,
                                  P_c_bar: float,
                                  p_t_guess_bar: float) -> Optional[Dict]:
        """Oda dengesinden kayan-denge BOĞAZ istasyonunu çözer.

        Boğaz, izentrop üzerinde kütle akısı G = ρ·v'nin MAKSİMUM olduğu
        noktadır; bu, v = a_eq sonik koşuluyla özdeştir (RP-1311 §6.3.3:
        A/A_t minimumu ⇔ u = a). Üç noktalı parabol tepe kestirimi
        ``EQ_STATION_PARABOLIC_STEPS`` adımlarıyla daraltılır.

        Döndürülen sözlük: ``s0``, ``h0``, ``T0``, ``P_c`` (Pa), ``Y0``
        (oda denge bileşimi), ``bogaz`` (istasyon + ``a``), ``c_star``,
        ``sonic_residual``.

        c* TANIMI (RP-1311 eş. 6.11): c* = P_c·A_t/ṁ ve ṁ = ρ_t·v_t·A_t
        ⇒ c* = P_c/(ρ_t·v_t). A_t sadeleşir, yani SÜREKLİLİK ÖZDEŞLİĞİ
        yapı gereği kapanır. (ÖH D18 B3-05'in ölçtüğü −%0,72…−1,06 açığı
        buradan geliyordu: eski kod c*'ı tek-γ kapalı formundan, boğaz
        istasyonunu ise BAŞKA bir tek-γ bağıntısından alıyordu.)

        Cantera yoksa ya da çözüm ıraksarsa ``None`` döner; çağıran tek-γ
        yoluna düşer ve bunu ``conditions.throat.basis`` ile BEYAN eder.
        """
        self._yk_ipucu_sifirla()   # V301/B7 ardılı: aşama belirlenimci başlar
        if not self.cantera_available or self.gas is None:
            return None
        anahtar = (comp_str, float(T_c), float(P_c_bar))
        onbellek = self._eq_station_cache.get(anahtar)
        if onbellek is not None:
            return onbellek
        try:
            gas = self.gas
            P_c = float(P_c_bar) * 1e5
            gas.TPY = float(T_c), P_c, comp_str
            gas.equilibrate('TP')
            yk_baglam = None
            eps_0 = 0.0
            if self._gaz_karbon_asiri_doymus():
                # V301/B7: oda gaz + C(gr) dengesi. Durağan h_0, s_0 KARIŞIM
                # değerleridir; izentrop boyunca bütün durumlar iki fazlı
                # çözücüden geçer (yk_baglam['aktif']).
                kayit = (float(gas.T), float(gas.P),
                         np.array(gas.Y, dtype=float))
                y_el = self._yk_element_kutle()
                try:
                    d_0 = self._yk_tp(float(T_c), P_c, y_el)
                finally:
                    self._yk_geri_yukle(kayit)
                h_0, s_0, T_0 = d_0['h'], d_0['s'], d_0['T']
                Y_0 = d_0['Y_gas']
                eps_0 = d_0['eps']
                Y_0_toplam = kayit[2]
                yk_baglam = {'aktif': True, 'y_el': y_el}
                self._yk_ipucu = {'s': s_0, 'P': P_c, 'T': T_0, 'eps': eps_0,
                                  'kappa': (d_0['cp'] - d_0['cv']) / d_0['cp']}
            else:
                h_0 = float(gas.enthalpy_mass)
                s_0 = float(gas.entropy_mass)
                T_0 = float(gas.T)
                Y_0 = np.array(gas.Y, dtype=float)
                Y_0_toplam = Y_0

            alt = EQ_STATION_SONIC_BRACKET[0] * P_c
            ust = EQ_STATION_SONIC_BRACKET[1] * P_c
            p = float(np.clip(float(p_t_guess_bar) * 1e5, alt, ust))
            for adim in EQ_STATION_PARABOLIC_STEPS:
                x1, x2, x3 = [float(np.clip(p * (1.0 + k * adim), alt, ust))
                              for k in (-1.0, 0.0, 1.0)]
                if x1 >= x2 or x2 >= x3:
                    break
                y1, y2, y3 = [
                    self._equilibrium_isentrope_state(
                        s_0, h_0, x, yk_baglam)['G']
                    for x in (x1, x2, x3)]
                payda = (x1 - x2) * (y2 - y3) - (x2 - x3) * (y1 - y2)
                if not np.isfinite(payda) or abs(payda) < 1e-30:
                    break
                tepe = 0.5 * (((x1 * x1 - x2 * x2) * (y2 - y3)
                               - (x2 * x2 - x3 * x3) * (y1 - y2)) / payda)
                if not np.isfinite(tepe):
                    break
                yeni = float(np.clip(tepe, alt, ust))
                kapandi = abs(yeni / p - 1.0) < 1e-12
                p = yeni
                if kapandi:
                    break

            bogaz = self._equilibrium_isentrope_state(s_0, h_0, p, yk_baglam)
            bogaz['a'] = self._equilibrium_sound_speed(s_0, bogaz, yk_baglam)
            if not (bogaz['G'] > 0.0 and bogaz['v'] > 0.0
                    and np.isfinite(bogaz['T']) and bogaz['a'] > 0.0):
                return None
            sonuc = {
                's0': s_0, 'h0': h_0, 'T0': T_0, 'P_c': P_c, 'Y0': Y_0,
                # V301/B7: oda yoğun kütle kesri, toplam bileşimli gaz-yalnız
                # oda durumu (değişmez geri yüklemesi için) ve iki fazlı
                # bağlam. Gaz-yalnız odada eps0 = 0, Y0_total ≡ Y0, yk None.
                'eps0': eps_0, 'Y0_total': Y_0_toplam, 'yk': yk_baglam,
                'bogaz': bogaz,
                'c_star': P_c / bogaz['G'],
                # Sonik kapanış artığı |v/a − 1|: tepe araması yakınsadıysa
                # ~1e-5 mertebesindedir. BEYAN edilir, gizlenmez.
                'sonic_residual': abs(bogaz['v'] / bogaz['a'] - 1.0),
            }
            if len(self._eq_station_cache) >= EQ_STATION_CACHE_MAX:
                self._eq_station_cache.pop(next(iter(self._eq_station_cache)))
            self._eq_station_cache[anahtar] = sonuc
            return sonuc
        except Exception as exc:
            logger.warning(
                "Kayan-denge boğaz çözümü başarısız (%s); istasyonlar tek-γ "
                "bağıntısından kurulacak ve bu durum conditions.throat.basis "
                "ile bildirilecek.", exc)
            return None

    def _solve_equilibrium_exit(self, ist: Dict, expansion_ratio: float,
                                p_e_guess_bar: float) -> Optional[Dict]:
        """ε = A_e/A_t'den kayan-denge ÇIKIŞ istasyonunu çözer.

        Süreklilikten ε = (ρ_t v_t)/(ρ_e v_e) = G_t/G_e; G_e(p) süpersonik
        dalda p ile monoton arttığından ln p uzayında kesen (secant)
        yöntemi kullanılır. Böylece A_e DENGE ile boyutlandırılır
        (literatür raporu §2 madde 3), tek-γ ile değil.

        BOYUT SAĞLAMASI: ε = [kg/(m²s)]/[kg/(m²s)] = 1 ✔.
        """
        self._yk_ipucu_sifirla()   # V301/B7 ardılı: aşama belirlenimci başlar
        h0, s0 = ist['h0'], ist['s0']
        G_t = ist['bogaz']['G']
        hedef = float(expansion_ratio)
        log_ust = float(np.log(ist['bogaz']['P'] * (1.0 - 1e-9)))
        log_alt = float(np.log(EQ_STATION_EXIT_PRESSURE_FLOOR_PA))

        def artik(x_log):
            d = self._equilibrium_isentrope_state(s0, h0, float(np.exp(x_log)),
                                                  ist.get('yk'))
            if d['G'] <= 0.0:
                return None, d
            return float(np.log(G_t / d['G'] / hedef)), d

        try:
            x0 = float(np.clip(np.log(max(float(p_e_guess_bar) * 1e5,
                                          EQ_STATION_EXIT_PRESSURE_FLOOR_PA)),
                               log_alt, log_ust))
            f0, _ = artik(x0)
            if f0 is None:
                return None
            x1 = float(np.clip(x0 - 0.15, log_alt, log_ust))
            if x1 == x0:
                x1 = float(np.clip(x0 + 0.15, log_alt, log_ust))
            f1, d1 = artik(x1)
            if f1 is None:
                return None
            for _ in range(EQ_STATION_EXIT_SECANT_MAX_ITER):
                if abs(f1) < EQ_STATION_EXIT_REL_TOL:
                    break
                if not np.isfinite(f1 - f0) or abs(f1 - f0) < 1e-15:
                    break
                x2 = float(np.clip(x1 - f1 * (x1 - x0) / (f1 - f0),
                                   log_alt, log_ust))
                if x2 == x1:
                    break
                f2, d2 = artik(x2)
                if f2 is None:
                    return None
                x0, f0 = x1, f1
                x1, f1, d1 = x2, f2, d2
            if not (np.isfinite(f1) and abs(f1) < 1e-6):
                logger.warning(
                    "Kayan-denge ε çözümü kapanmadı (eps=%.4f, artık=%.3e); "
                    "çıkış istasyonu tek-γ yoluna bırakılıyor.", hedef, f1)
                return None
            d1['expansion_ratio_closure'] = float(np.exp(f1))
            return d1
        except Exception as exc:
            logger.warning(
                "Kayan-denge çıkış çözümü başarısız (%s); çıkış istasyonu "
                "tek-γ yoluna bırakılıyor.", exc)
            return None

    def _equilibrium_reference_isp(self, ist: Dict, P_e_pa: float,
                                   v_e_eq: float) -> Optional[Dict]:
        """Üçlü Isp yayını: denge / boğazda donmuş / odada donmuş.

        Sektör kipleri (NASA CEA ``nfz``; RP-1311 Part II; RPA v2.3 s.19):
          * ``equilibrium``       — tüm lülede kayan denge (üst referans),
          * ``frozen_at_throat``  — CEA ``nfz=2``: oda+boğaz denge, boğazdan
            sonra bileşim donmuş. SEKTÖRÜN kötümser referansı,
          * ``frozen_at_chamber`` — CEA ``nfz=1``: oda bileşimi tüm lülede
            donmuş. MUTLAK alt sınır (c* de donmuş olurdu), yalnız sınır
            beyanı olarak yayımlanır.

        Kinetik verim bandı ``frozen_at_throat``–``equilibrium`` arasıdır
        (MIT 16.512 L14, SSME: 435 / 451 / 465 s).
        """
        self._yk_ipucu_sifirla()   # V301/B7 ardılı: aşama belirlenimci başlar
        try:
            gas = self.gas
            h0, s0 = ist['h0'], ist['s0']
            bogaz = ist['bogaz']
            yk_baglam = ist.get('yk')
            eps_0 = ist.get('eps0', 0.0)

            # nfz=2 — boğaz denge bileşimini dondur, izentropik genişlet.
            # V301/B7: boğaz gaz + C(gr) ise yoğun kütle kesri de donar
            # (CEA donmuş kipi: bileşim sabit, iki faz ısıl dengede).
            d_t = self._denge_sp(s0, bogaz['P'], yk_baglam,
                                 T_tahmin=bogaz['T'],
                                 eps_tahmin=bogaz.get('eps') or None)
            if d_t['eps'] > 0.0:
                h_ft = self._yk_donmus_sp(d_t['Y_gas'], d_t['eps'], s0,
                                          P_e_pa, d_t['T'])['h']
            else:
                Y_t = np.array(gas.Y, dtype=float)
                gas.TPY = float(gas.T), bogaz['P'], Y_t
                gas.SP = s0, P_e_pa
                h_ft = float(gas.enthalpy_mass)
            v_ft = float(np.sqrt(2.0 * max(h0 - h_ft, 0.0)))

            # nfz=1 — oda denge bileşimini dondur (mutlak alt sınır).
            if eps_0 > 0.0:
                h_fc = self._yk_donmus_sp(ist['Y0'], eps_0, s0, P_e_pa,
                                          ist['T0'])['h']
            else:
                gas.TPY = ist['T0'], ist['P_c'], ist['Y0']
                gas.SP = s0, P_e_pa
                h_fc = float(gas.enthalpy_mass)
            v_fc = float(np.sqrt(2.0 * max(h0 - h_fc, 0.0)))

            # Gaz durumunu oda dengesine geri yükle (sonraki çağrılar temiz
            # başlasın — mevcut _calculate_frozen_shifting_isp ile aynı desen).
            # V301/B7: iki fazlı odada TOPLAM bileşimli gaz-yalnız oda durumu
            # (Y0_total); gaz-yalnız odada Y0_total ≡ Y0 (bit-aynı).
            gas.TPY = ist['T0'], ist['P_c'], ist.get('Y0_total', ist['Y0'])
            gas.equilibrate('TP')

            if not (v_e_eq >= v_ft >= v_fc > 0.0):
                # Fiziksel sıralama bozulduysa yakınsama bozulmuştur; üçlü
                # yayın YAPILMAZ (uydurma sıra yayımlamaktansa alan yok).
                logger.warning(
                    "Üçlü Isp sıralaması bozuk (eq=%.2f, nfz2=%.2f, nfz1=%.2f); "
                    "referans yayını atlanıyor.", v_e_eq, v_ft, v_fc)
                return None
            return {
                'isp_equilibrium': v_e_eq / G_0,
                'isp_frozen_throat': v_ft / G_0,
                'isp_frozen_chamber': v_fc / G_0,
            }
        except Exception as exc:
            logger.warning(
                "Üçlü Isp referansı hesaplanamadı (%s); yayın atlanıyor.", exc)
            return None

    def _exit_pressure_from_expansion(self, expansion_ratio: float, gamma: float,
                                      chamber_pressure: float) -> float:
        """ε = Ae/At ve γ'dan izentropik çıkış basıncını (bar) çözer.

        İzentropik alan-Mach bağıntısı (Sutton & Biblarz 9. baskı, Eş. 3-14):
            A_e/A_t = (1/M)·[ (2/(γ+1))·(1 + (γ-1)/2·M²) ] ^ ((γ+1)/(2(γ-1)))
        süpersonik kökü brentq ile çözülür, sonra izentropik basınç bağıntısı
        (Eş. 3-7) uygulanır:
            p_e = p_c / (1 + (γ-1)/2·M_e²) ^ (γ/(γ-1))

        Not: bu yöntem F034 düzeltmesinin (çıkış istasyonunu motorun gerçek
        genişleme oranına bağlama) sayısal çekirdeğidir; çağıran
        analyze_combustion'dır. ε <= 1 ya da yakınsama başarısızlığında oda
        basıncına eşlenik güvenli değer yerine ISA deniz seviyesi çapası
        döndürülür (çağıran zaten bu durumu 'sea_level_default' sayar).
        """
        eps = float(expansion_ratio)
        g = float(gamma)
        if eps <= 1.0 or not gamma_is_physical(g):
            return isa_pressure(0.0) * BAR_PER_PA

        exponent = (g + 1.0) / (2.0 * (g - 1.0))

        def area_ratio(M: float) -> float:
            return (1.0 / M) * ((2.0 / (g + 1.0))
                                * (1.0 + 0.5 * (g - 1.0) * M * M)) ** exponent

        try:
            M_e = brentq(lambda M: area_ratio(M) - eps, 1.0 + 1e-6, 60.0,
                         xtol=1e-10, maxiter=200)
        except (ValueError, RuntimeError):
            logger.warning(
                "Alan-Mach çözümü yakınsamadı (eps=%.3f, gamma=%.4f); "
                "çıkış basıncı ISA deniz seviyesine çapalanıyor.", eps, g)
            return isa_pressure(0.0) * BAR_PER_PA

        p_e = chamber_pressure / (
            (1.0 + 0.5 * (g - 1.0) * M_e * M_e) ** (g / (g - 1.0)))
        # Sayısal taban: mutlak sıfır basınç ileride log/oran alan tüketicileri
        # bozar. 1e-6 bar (~0.1 Pa) fiziksel olarak "vakum" mertebesidir.
        return float(max(p_e, 1e-6))

    def _calculate_exit_temperature(self, T_chamber: float, P_chamber: float, P_exit: float,
                                    gamma: Optional[float] = None) -> float:
        """Calculate exit temperature using isentropic expansion.

        gamma verilmezse fallback olarak 1.25 kullanılır (tipik yanma gazı,
        Sutton & Biblarz 9. baskı); Cantera mevcutken çağıran, hesaplanan
        oda gamma'sını geçirir (akış zincirinde tek gamma tutarlılığı).
        """
        if gamma is None:
            gamma = 1.25  # Fallback: tipik yanma gazı gamma'sı
        pressure_ratio = P_chamber / P_exit
        return T_chamber / (pressure_ratio ** ((gamma - 1) / gamma))

    def _calculate_frozen_shifting_isp(self, elements: Dict, T_c: float,
                                       P_c: float, P_e: float
                                       ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Frozen ve shifting-equilibrium özgül itki (Isp) ile shifting çıkış hızını hesaplar.

        Yöntem: enerji denklemiyle çıkış hızı (Sutton & Biblarz 9. baskı,
        Eş. 3-15b: v_e = sqrt(2 (h_0 - h_e)); NASA RP-1311 Part I lüle hız
        denklemi). Oda durağan entalpisi h_0 sabit, çıkış statik entalpisi
        h_e izentropik (s = s_oda) genişlemeyle P_e'de alınır:

          * SHIFTING: çıkış basıncında kimyasal denge YENİDEN çözülür
            (Cantera equilibrate('SP')). Çıkış gamma'sı çıkış dengesinden
            gelir -> tek-gamma fazla-genişleme hatası ortadan kalkar.
            Yüksek sıcaklıkta ayrışan türlerin (CO+1/2 O2->CO2, H+OH->H2O, ...)
            genişlerken yeniden birleşme entalpisi geri kazanılır; bu yüzden
            shifting Isp her zaman frozen'dan büyüktür.
          * FROZEN: bileşim oda değerine DONDURULUR (Cantera SP, equilibrate
            YOK -> sadece T ayarlanır); ayrışma entalpisi geri kazanılmaz.

        Bu, NASA CEA'nın frozen/equilibrium ayrımıyla aynı fiziktir. Doğru
        karşılaştırma referansı CEA'nın Pamb=P_e'deki basınç-eşleşmiş (optimum
        genişleme) Isp'idir; bu, RocketCEA'da estimate_Ambient_Isp(Pamb=P_e)
        çağrısıdır ve sayısal olarak M_çıkış * a_çıkış / g0 'a eşittir (yani
        v_e/g0). DİKKAT: RocketCEA get_Isp(eps) varsayılan olarak VAKUM Isp'i
        (sonsuz genişleme basınç-itki terimiyle) döndürür; v_e/g0 ile doğrudan
        kıyaslanmamalıdır.

        Doğrulama (tests/test_combustion_cea_validation.py, Pc=20 bar):
          N2O/HTPB  O/F=6.0:  frozen -3.1%, shifting -2.4% (CEA'ya göre)
          LOX/RP-1  O/F=2.5:  frozen +0.5%, shifting +2.2%
        Frozen/shifting genişleme MANTIĞI CEA tanımıyla birebir uyumludur.
        Yukarıdaki yüzdeler ESKİ bir ölçümdür. Bu paragraf eskiden "gri30
        fuel-rich N2O/HTPB için T_c'yi ~%3.4 düşük verir" diyordu; bugünkü
        kodla tutmuyor. v3.0.1'de (20 Eki 2026) /calculate yanıtındaki
        ``cea_comparison`` bloğuyla yeniden ölçüldü: aynı Pc, O/F ve ε,
        HRMA'nın kendi itici kartları, RocketCEA 1.2.1.
          N2O/HTPB Pc=20 bar O/F=6: Δc* +%0.020, ΔT_c +%0.057, ΔIsp_vac +%0.011
          N2O/HTPB Pc=20 bar O/F=7: Δc* +%0.017, ΔT_c +%0.044, ΔIsp_vac +%0.014
        Isp testlerinin %3.5 ve oda c* doğruluğunun %2.5 toleransları
        değiştirilmedi; artık geniş kalıyorlar. Daraltılması ayrı bir iş.

        Cantera yoksa veya denge çözülemezse (None, None, None) döner ve
        çağıran mevcut tek-gamma Isp değerini korur.
        """
        self._yk_ipucu_sifirla()   # V301/B7 ardılı: aşama belirlenimci başlar
        if not self.cantera_available or self.gas is None:
            return None, None, None
        try:
            comp_str = self._elements_to_cantera_composition(elements)
            gas = self.gas
            # Oda denge durumu (durağan koşul) — h_0, s_0, bileşim okunur.
            gas.TPY = T_c, P_c * 1e5, comp_str
            gas.equilibrate('TP')
            if self._gaz_karbon_asiri_doymus():
                # V301/B7: oda gaz + C(gr). Aynı enerji denklemi, KARIŞIM
                # entalpisi/entropisiyle (RP-1311 eş. 2.14); donmuş kipte
                # gaz bileşimi ve yoğun kütle kesri sabit.
                kayit = (float(gas.T), float(gas.P),
                         np.array(gas.Y, dtype=float))
                y_el = self._yk_element_kutle()
                try:
                    d_0 = self._yk_tp(float(T_c), P_c * 1e5, y_el)
                    d_e = self._yk_sp(d_0['s'], P_e * 1e5, y_el,
                                      eps_tahmin=d_0['eps'])
                    h_e_froz = self._yk_donmus_sp(
                        d_0['Y_gas'], d_0['eps'], d_0['s'], P_e * 1e5,
                        d_e['T'])['h']
                finally:
                    self._yk_geri_yukle(kayit)
                h_0 = d_0['h']
                v_shift = float(np.sqrt(2.0 * max(h_0 - d_e['h'], 0.0)))
                v_froz = float(np.sqrt(2.0 * max(h_0 - h_e_froz, 0.0)))
                isp_froz = v_froz / G_0
                isp_shift = v_shift / G_0
                if not (isp_shift >= isp_froz > 0):
                    return None, None, None
                return isp_froz, isp_shift, v_shift
            h_0 = gas.enthalpy_mass      # J/kg, durağan entalpi (Hf dahil)
            s_0 = gas.entropy_mass       # J/(kg·K)
            T_0 = gas.T
            Y_0 = gas.Y                  # oda denge bileşimi (frozen referans)

            # SHIFTING: çıkış basıncında dengeyi yeniden çöz (V301/B7:
            # karbonca aşırı doymuşsa gaz + C(gr); değilse bit-aynı).
            d_e = self._denge_sp(s_0, P_e * 1e5)
            h_e_shift = d_e['h']
            v_shift = float(np.sqrt(2.0 * max(h_0 - h_e_shift, 0.0)))

            # FROZEN: oda bileşimine dön, izentropik (equilibrate YOK).
            gas.TPY = T_0, P_c * 1e5, Y_0
            gas.SP = s_0, P_e * 1e5
            h_e_froz = gas.enthalpy_mass
            v_froz = float(np.sqrt(2.0 * max(h_0 - h_e_froz, 0.0)))

            # Gaz durumunu oda dengesine geri yükle (sonraki çağrılar için temiz başlangıç).
            gas.TPY = T_0, P_c * 1e5, Y_0
            gas.equilibrate('TP')

            isp_froz = v_froz / G_0
            isp_shift = v_shift / G_0
            # Fiziksel tutarlılık: shifting >= frozen olmalı; aksi halde
            # yakınsama bozulmuştur -> sessizce güvenli tarafa (None) düş.
            if not (isp_shift >= isp_froz > 0):
                return None, None, None
            return isp_froz, isp_shift, v_shift
        except Exception as exc:
            logger.warning(
                "Frozen/shifting Isp hesabı başarısız (%s); tek-gamma Isp korunuyor.",
                exc,
            )
            return None, None, None

    def _calculate_performance_parameters(self, chamber_comp: Dict, throat_comp: Dict,
                                        exit_comp: Dict, P_c: float, P_t: float, P_e: float,
                                        T_c: float, T_t: float, T_e: float) -> Dict:
        """Calculate performance parameters"""
        
        # Calculate average molecular weight (Cantera uyumlu)
        def calc_mw(composition):
            # ÖH D19 (kalem B3-11) — ÖLÜ SPECIES KOLU + UYDURMA MW=25 KALKTI.
            # Bu fonksiyonun 'species' kolu ve 'eski format' kolu ÖLÇÜLMÜŞ
            # BİÇİMDE ÖLÜYDÜ (sys.settrace, once.json B3_11: 0 satır; 8
            # itici çifti, hem Cantera AÇIK hem KAPALI). Her iki bileşim
            # üreticisi de 'molecular_weight' anahtarını doğrudan veriyor.
            # Ölü kolların ucundaki `return 25.0` ("veri yoksa tipik yanma
            # gazı MW'si") sessiz uydurmaydı: MW doğrudan R_c/R_t/R_e'ye ve
            # oradan c*, Isp ve tüm istasyon özelliklerine giriyor.
            # FAIL-CLOSED: alan yoksa sayı uydurulmaz, ADIYLA reddedilir.
            if isinstance(composition, dict) and 'molecular_weight' in composition:
                return composition['molecular_weight']
            # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
            raise ValueError(
                "Combustion composition does not carry a solved "
                "'molecular_weight'; the mixture gas constant is not "
                "published from an assumed typical value.")
        
        MW_c = calc_mw(chamber_comp)
        MW_t = calc_mw(throat_comp)
        MW_e = calc_mw(exit_comp)
        
        # Gas constants (güvenli bölme)
        R_c = self.R_universal / max(MW_c, 10.0)  # Minimum MW limit
        R_t = self.R_universal / max(MW_t, 10.0)
        R_e = self.R_universal / max(MW_e, 10.0)
        
        # Thermodynamic properties
        thermo_props = self._calculate_thermodynamic_properties(
            chamber_comp, throat_comp, exit_comp, T_c, T_t, T_e, P_c, P_t, P_e
        )
        
        # Characteristic velocity - use chamber gamma from thermodynamic properties
        # Access gamma from 'stations' -> 'chamber'
        gamma = thermo_props['stations']['chamber']['gamma']
        c_star = np.sqrt(R_c * T_c / gamma) / ((2/(gamma+1))**((gamma+1)/(2*(gamma-1))))
        
        # Throat velocity (choked)
        # DENETIM DUZELTMESI: Bogaz ses hizi YEREL (bogaz) gamma ile
        # hesaplanir: a_t = sqrt(γ_t·R_t·T_t). Oda gamma'sini bogaz R/T ile
        # karistirmak fiziksel istasyon tutarsizligiydi (Sutton & Biblarz
        # 9. baski, Eq. 3-10; bogaz gamma'si denge kaymasi+sicaklik nedeniyle
        # oda degerinden ~%1-2 farklidir).
        gamma_throat = thermo_props['stations']['throat']['gamma']
        v_throat = np.sqrt(gamma_throat * R_t * T_t)

        # Exit velocity (Sutton Eq. 3-15 / paper line 151):
        # v_e = sqrt( 2*gamma/(gamma-1) * R * T_c * [1 - (P_e/P_c)^((gamma-1)/gamma)] )
        # T_c (chamber stagnation) kullanilir, T_e (exit static) DEGIL.
        # Daha once T_e kullaniliyordu -> H-9 hatasi (paper ile celisiyordu).
        # R_c (chamber gas constant) tutarliligi acisindan dogru tercihtir,
        # cunku stagnation kosulu chamber kimyasi/MW'sine baglidir.
        v_exit = np.sqrt(2 * gamma * R_c * T_c / (gamma - 1) * (1 - (P_e/P_c)**((gamma-1)/gamma)))
        
        # Specific impulse (g_0 = 9.80665 m/s^2, BIPM standart)
        isp = v_exit / G_0
        
        # Thrust coefficient
        cf = v_exit / c_star
        
        return {
            'molecular_weights': {'chamber': MW_c, 'throat': MW_t, 'exit': MW_e},
            'gas_constants': {'chamber': R_c, 'throat': R_t, 'exit': R_e},
            'velocities': {'throat': v_throat, 'exit': v_exit},
            'c_star': c_star,
            'cf': cf,
            'isp': isp,
            # --- ÖH D22 / B3-13(c) · ADIN DOĞRUSU ÜRETİCİDE ---------------
            # ``gamma_avg`` bir ORTALAMA DEĞİLDİR: yukarıda okunan
            # ``thermo_props['stations']['chamber']['gamma']``, yani ODA
            # gamma'sıdır (boğaz/çıkış istasyonları ayrı gamma taşır ve bu
            # sayıya hiç girmez). D21 tüketici tarafını künyeye bağlamıştı
            # ("this is the CHAMBER gamma, not an average"); doğru adı
            # yayımlamak üreticinin işiydi ve bu ayak açılmamıştı.
            # ``chamber_gamma`` doğru addır. ``gamma_avg`` KOPYA DEĞİL,
            # aynı nesnenin geriye uyum takma adıdır: üç kardeş tüketici
            # (nozzle_flow_1d, regen_cooling, heat_transfer_analysis) bu adı
            # okur ve okuma sözleşmeleri D21'de zaten düzeltildi; adı tek
            # hamlede kaldırmak onların künyeli yolunu kırardı.
            'chamber_gamma': gamma,
            'gamma_avg': gamma,
            'gamma_avg_deprecated_alias_of': 'chamber_gamma',
            'thermodynamic_properties': thermo_props
        }
    
    def find_optimum_of_ratio(self, fuel_composition: Dict, oxidizer_type: str,
                             chamber_pressure: float,
                             of_range: Tuple[float, float] = (1.0, 10.0),
                             expansion_ratio: Optional[float] = None) -> Dict:
        """Find O/F ratio for maximum specific impulse.

        Desteklenmeyen yakit/oksitleyici anahtarinda _calculate_elemental_
        composition ValueError firlatir; tarama noktalari cezalandirilsa bile
        optimum noktadaki tam analiz ayni hatayi yeniden firlatir, yani
        cagirana Ingilizce ve aciklayici bir hata ulasir (sessiz varsayilan
        uretilmez).

        expansion_ratio: lüle alan oranı ε = Ae/At. v2.6.26'ya kadar bu arama
            ε'yi HİÇ görmüyordu: her O/F noktası ``analyze_combustion``a
            ε'sız gidiyor, çıkış istasyonu ISA deniz seviyesine (1,01325 bar)
            ÇAPALANIYORDU. Sonuç: ε=16 seçen kullanıcının "optimum O/F"
            tablosu hâlâ ε≈1 koşullarında hesaplanıyor, çıkış basıncı ve
            izentropik verim yaprakları 18 koşuda tek değerde kalıyordu.
            Aynı düzeltme ANA yolda (hybrid_rocket_engine calculate) v2.6.26
            başında yapılmıştı; bu arama aynı düzeltmeyi almamıştı.
            None -> eski davranış (deniz seviyesi çapası) korunur.
        """

        # --- Önbellek (v2.5.5): anahtar TAM girdilerle kurulur (yuvarlama
        # YOK) — isabet yalnız birebir aynı aramada olur ve arama
        # deterministik olduğundan dönen kopya taze hesapla bit-aynıdır.
        # Anahtarlanamayan girdi (ör. sıralanamayan bileşim) önbelleksiz yol.
        cache_key = None
        try:
            cache_key = (
                tuple(sorted((str(k), float(v))
                             for k, v in fuel_composition.items())),
                str(oxidizer_type),
                float(chamber_pressure),
                (float(of_range[0]), float(of_range[1])),
                self._mechanism_id,
                # ε çıkış istasyonunu (p_e, T_e, isp, cf) ve dolayısıyla
                # optimum O/F'yi değiştirir; anahtara GİRMELİDİR, aksi hâlde
                # farklı ε'lar aynı önbellek girdisini paylaşır.
                None if expansion_ratio is None
                else round(float(expansion_ratio), 4),
                # Kitap uyum B16, 2. tur (Ş-5): GİRİŞ İMZASI. HP dengesine
                # giren N₂O entalpisi analizörün giriş durumuna bağlıdır;
                # imza anahtarda yoksa farklı giriş durumlu iki istek aynı
                # girdiyi paylaşır (gerekçe: ``optimum_of_inlet_signature``).
                self.optimum_of_inlet_signature(oxidizer_type),
            )
        except (TypeError, ValueError, AttributeError, IndexError):
            cache_key = None
        if cache_key is not None and cache_key in _OPTIMUM_OF_CACHE:
            return copy.deepcopy(_OPTIMUM_OF_CACHE[cache_key])

        eps = (None if expansion_ratio is None
               else (float(expansion_ratio) if float(expansion_ratio) > 1.0
                     else None))

        def negative_isp(of_ratio):
            try:
                results = self.analyze_combustion(
                    fuel_composition, oxidizer_type, of_ratio, chamber_pressure,
                    expansion_ratio=eps)
                return -results['performance']['isp']  # Negative because we minimize
            except Exception:
                return 1000  # Large penalty for failed calculations

        # Optimize
        #
        # ÖH D16 (kalem B3-09) — SINIRA DAYANAN NOKTA ARTIK "OPTİMUM" DİYE
        # YAYIMLANMAZ. ÖLÇÜLDÜ (1 Eylül 2026, taban 6fde52b; htpb/hava,
        # Pc=20 bar, varsayılan bant (1,0-10,0)):
        #   yayımlanan optimum_of_ratio = 9,999929  (bandın ÜST KENARI)
        #   yayımlanan maximum_isp      = 172,93944 s
        #   gerçek optimum (bant 5-40)  = 14,035275 / 180,48780 s
        # yani "optimum" gerçeğin 4,04 birim uzağındaydı ve Isp'yi 7,55 s
        # (%4,18) EKSİK gösteriyordu; yanıtta bant/kenar beyanı yoktu
        # (anahtarlar yalnız analysis / maximum_isp / optimum_of_ratio).
        #
        # BANDIN FİZİK KAYNAĞI (uydurma tavan değil): kimyasal roketlerde
        # Isp optimumu STOKİYOMETRİK oranın ALTINDA, yakıtça zengin tarafta
        # kalır — daha düşük ortalama molekül ağırlığı c*'ı yükseltir
        # (Sutton & Biblarz, "Rocket Propulsion Elements", 9. baskı, Böl. 5;
        # NASA SP-8087). Dolayısıyla stokiyometrik oran, aramanın doğal ve
        # itici-çiftine özgü ÜST sınırıdır. Modül bu oranı zaten hesaplıyor
        # (_calculate_stoichiometric_of), yani ikinci bir sabit doğmuyor.
        of_lo, of_hi = float(of_range[0]), float(of_range[1])
        result = minimize_scalar(negative_isp, bounds=(of_lo, of_hi),
                                 method='bounded')
        kenar_tol = 1.0e-3 * (of_hi - of_lo)
        of_range_basis = (
            f'interior optimum inside the searched band '
            f'[{of_lo:.6g}, {of_hi:.6g}]')
        if result.x >= of_hi - kenar_tol:
            of_stoich = None
            try:
                of_stoich = float(self._calculate_stoichiometric_of(
                    fuel_composition, oxidizer_type))
            except Exception:
                of_stoich = None
            if (of_stoich is not None and np.isfinite(of_stoich)
                    and of_stoich > of_hi):
                genis_hi = of_stoich
                result = minimize_scalar(negative_isp,
                                         bounds=(of_lo, genis_hi),
                                         method='bounded')
                if result.x >= genis_hi - 1.0e-3 * (genis_hi - of_lo):
                    of_range_basis = (
                        f'CLAMPED at the stoichiometric ratio '
                        f'{genis_hi:.6g}: the search band was widened from '
                        f'[{of_lo:.6g}, {of_hi:.6g}] to [{of_lo:.6g}, '
                        f'{genis_hi:.6g}] and the maximum still sits on the '
                        f'upper bound, so this point is a BOUND, not an '
                        f'interior optimum')
                else:
                    of_range_basis = (
                        f'band widened from [{of_lo:.6g}, {of_hi:.6g}] to '
                        f'[{of_lo:.6g}, {genis_hi:.6g}] (stoichiometric O/F) '
                        f'because the maximum sat on the original upper '
                        f'bound; the reported point is interior to the '
                        f'widened band')
                of_hi = genis_hi
            else:
                of_range_basis = (
                    f'CLAMPED at the upper bound {of_hi:.6g}: the maximum '
                    f'sits on the edge of the searched band and the '
                    f'stoichiometric ratio does not lie above it, so this '
                    f'point is a BOUND, not an interior optimum')
        elif result.x <= of_lo + kenar_tol:
            of_range_basis = (
                f'CLAMPED at the lower bound {of_lo:.6g}: the maximum sits '
                f'on the edge of the searched band, so this point is a '
                f'BOUND, not an interior optimum')

        optimum_of = result.x
        max_isp = -result.fun

        # Get full analysis at optimum
        # ÖH D24 / P15B1-05: bu ağaç DANIŞMA amaçlıdır ve tasarım O/F'sinde
        # DEĞİL, bulunan optimum O/F'de durur. Etiket bunu gövdede ilan eder
        # (eskiden fark yalnız inputs.of_ratio okunarak görülebiliyordu).
        optimum_analysis = self.analyze_combustion(
            fuel_composition, oxidizer_type, optimum_of, chamber_pressure,
            expansion_ratio=eps,
            operating_point=OPERATING_POINT_OPTIMUM_SEARCH)

        out = {
            'optimum_of_ratio': optimum_of,
            'maximum_isp': max_isp,
            'of_range_searched': [of_lo, of_hi],
            'of_range_basis': of_range_basis,
            'analysis': optimum_analysis
        }
        if cache_key is not None:
            # Kopya sakla: çağıran sonucu değiştirse bile önbellek bozulmaz
            if len(_OPTIMUM_OF_CACHE) >= _OPTIMUM_OF_CACHE_MAX:
                _OPTIMUM_OF_CACHE.pop(next(iter(_OPTIMUM_OF_CACHE)))
            _OPTIMUM_OF_CACHE[cache_key] = copy.deepcopy(out)
        return out
    
    @staticmethod
    def _fixed_nozzle_altitude_sweep(mdot: float, v_exit: float, P_e_bar: float,
                                     T_e: float, R_e: float,
                                     altitudes: List[float],
                                     thrust_sea_level: Optional[float] = None
                                     ) -> Tuple[List[Dict], Dict]:
        """Sabit geometrili lülede irtifa taraması — TEK TANIM NOKTASI.

        T33 DÜZELTMESİ (2026-08-03). Aynı motor için sayfada İKİ irtifa
        tablosu vardı ve ikisi de farklı bir deniz seviyesi itkisi
        yayımlıyordu: ``calculate_altitude_performance`` çözücünün kütle
        debisini (0,548540 kg/s) İDEAL çıkış hızıyla çarpıp 1033,02 N,
        ``calculate_thrust_at_altitudes`` ise teslim edilen itkiyi (1000 N)
        İDEAL Isp'ye bölerek uydurma bir debi (0,531 kg/s) türetip 998,56 N
        diyordu (%3,45 fark). Manşet ise 1000 N / 185,90 s idi, yani hiçbiri
        manşetle uyuşmuyordu (Isp'de %3,30 fark).

        Kök neden TEK: lüle kayıpları (sapma, sürtünme, kinetik, iki-fazlı)
        bu tablolara hiç uygulanmıyordu. Kayıplar MOMENTUM terimini düşürür,
        basınç-alan terimini değil (geometri kayıptan etkilenmez):

            F(h) = eta_v · mdot · v_e_ideal + (P_e - P_a) · A_e
            A_e  = mdot · R_e · T_e / (P_e · v_e_ideal)      [süreklilik]

        eta_v bir başparmak kuralı DEĞİLDİR: çözücünün teslim ettiği deniz
        seviyesi itkisinden tek değerli olarak çözülür —

            eta_v = (F_dsl - (P_e - P_ISA0)·A_e) / (mdot · v_e_ideal)

        Böylece tarama 0 km'de manşetin sayısını AYNEN verir ve irtifa
        eğilimi doğru fizikte kalır. Çapa verilmezse eta_v = 1 (ideal) olur
        ve bu durum ``velocity_efficiency_basis`` ile açıkça bildirilir —
        sessizce ideal sayı yayımlanmaz.

        Dönüş: (satırlar, meta).
        """
        mdot = float(mdot)
        v_exit = float(v_exit)
        P_e_pa = float(P_e_bar) * PA_PER_BAR
        # Çıkış alanı süreklilikten: A_e = mdot/(rho_e·v_e), rho_e = Pe/(R_e·T_e)
        if P_e_pa > 0.0 and v_exit > 0.0:
            A_e = mdot * float(R_e) * float(T_e) / (P_e_pa * v_exit)   # m²
        else:
            A_e = 0.0

        P_sl_pa = isa_pressure(0.0)                                    # Pa
        eta_v = 1.0
        eta_raw = None
        if thrust_sea_level is not None and mdot > 0.0 and v_exit > 0.0:
            try:
                f_sl = float(thrust_sea_level)
            except (TypeError, ValueError):
                f_sl = float('nan')
            if np.isfinite(f_sl) and f_sl > 0.0:
                eta_raw = ((f_sl - (P_e_pa - P_sl_pa) * A_e)
                           / (mdot * v_exit))
        if eta_raw is not None and 0.5 <= eta_raw <= 1.0:
            eta_v = float(eta_raw)
            basis = ('nozzle loss factor solved from the delivered sea-level '
                     'thrust of this motor; applied to the momentum term only '
                     '(the pressure-area term is geometric)')
        elif eta_raw is not None:
            # Çapa çıkış istasyonuyla tutarsız: sessizce kırpmak yerine
            # ideal değere dönülür ve ham oran çıktıda bırakılır.
            basis = (f'delivered sea-level thrust anchor rejected: the '
                     f'implied nozzle loss factor is {eta_raw:.4f}, outside '
                     f'the physical range 0.5-1.0; the ideal (loss-free) '
                     f'exit velocity is used instead')
        else:
            basis = ('NOT_ANCHORED: no delivered sea-level thrust was '
                     'supplied, so the ideal (loss-free) exit velocity is '
                     'used and these numbers are upper bounds')

        # Vakum itkisi (P_a = 0) — irtifa verimlerinin paydası
        thrust_vacuum = eta_v * mdot * v_exit + P_e_pa * A_e

        rows = []
        for altitude in altitudes:
            # Standard atmosphere — merkezi ISA yardımcıları (hrma.constants)
            T = isa_temperature(altitude)              # K
            P = isa_pressure(altitude) * BAR_PER_PA    # bar
            thrust = eta_v * mdot * v_exit + (P_e_pa - P * PA_PER_BAR) * A_e
            isp = thrust / (mdot * G_0) if mdot > 0 else 0.0
            rows.append({
                'altitude': altitude,
                'pressure': P,
                'temperature': T,
                'thrust': thrust,
                'isp': isp,
                'exit_velocity': v_exit,
            })

        meta = {
            'mass_flow_kg_s': mdot,
            'exit_area_m2': A_e,
            'velocity_efficiency': eta_v,
            'velocity_efficiency_raw': eta_raw,
            'velocity_efficiency_basis': basis,
            'anchored_to_delivered_thrust': bool(eta_raw is not None
                                                 and 0.5 <= eta_raw <= 1.0),
            'thrust_vacuum_n': thrust_vacuum,
        }
        return rows, meta

    def calculate_altitude_performance(self, motor_data: Dict, altitudes: List[float]) -> Dict:
        """Calculate performance at different altitudes.

        DENETIM DUZELTMESI (Sutton & Biblarz 9. baski, Eq. 3-29): SABIT
        geometrili nozul. Ae/At sabit oldugundan cikis Mach'i, Pe ve v_exit
        SABITTIR; irtifa yalnizca (Pe - Pa)*Ae basinc-itki terimini
        degistirir.

        T33 (2026-08-03): itki/Isp artik ``_fixed_nozzle_altitude_sweep``
        TEK tanim noktasindan gelir ve motor_data['thrust_sea_level']
        verildiyse cozucunun TESLIM ETTIGI deniz seviyesi itkisine capalanir
        — kardes tablo ``calculate_thrust_at_altitudes`` ile ayni sayilari
        verir (eskiden 0 km'de 1033,02 N ve 998,56 N diye iki farkli cevap
        vardi, ikisi de mansetin 1000 N'undan farkliydi).
        """

        performance_data = []
        if not altitudes:
            return {'altitude_performance': [], 'sea_level_isp': None,
                    'sea_level_isp_basis': _SEA_LEVEL_ISP_BASIS,
                    'vacuum_isp': 0}

        v_exit = motor_data['performance']['velocities']['exit']  # m/s (SABIT, tasarim)
        P_e_bar = motor_data['conditions']['exit']['P']           # bar (tasarim cikis basinci)
        T_e = motor_data['conditions']['exit']['T']               # K (tasarim cikis statik)
        R_e = motor_data['gas_constants']['exit']                 # J/(kg·K)
        c_star = motor_data['performance']['c_star']              # m/s
        mdot = motor_data.get('mdot_total', 1.0)                  # kg/s

        rows, meta = self._fixed_nozzle_altitude_sweep(
            mdot, v_exit, P_e_bar, T_e, R_e, altitudes,
            thrust_sea_level=motor_data.get('thrust_sea_level'))

        for row in rows:
            # CF = F/(Pc*At); At = c_star*mdot/Pc -> CF = F/(mdot*c_star).
            cf = row['thrust'] / (mdot * c_star) if mdot * c_star else 0.0
            performance_data.append({
                'altitude': row['altitude'],
                'pressure': row['pressure'],
                'temperature': row['temperature'],
                'exit_velocity': row['exit_velocity'],
                'cf': cf,
                'isp': row['isp'],
                'thrust': row['thrust'],
            })

        # --- VAKUM Isp'si: P_a = 0 LİMİTİ (bebek-Scofield F3-3) -----------
        # ÖLÇÜM (17 Ağustos 2026, HEAD f9d95eb): burada
        # ``max(p['isp'] for p in performance_data)`` yazıyordu, yani
        # "vakum" diye yayımlanan sayı irtifa TABLOSUNUN EN ÜST SATIRIydı
        # (20 km, P = 0,0547 bar) — vakum değil, yalnızca listenin en
        # seyrek noktası. Ölçülen fark aynı motorda 268,1262 s (yayımlanan)
        # ile 269,6207 s (gerçek vakum) arasında 1,495 s idi; p_e = 0,5 bar
        # koşumunda 283,537 s ⟷ 286,112 s (%0,9). Kusurun ADI yanlıştı:
        # tablo 10 km'de kesilseydi aynı alan 262,4 s'yi "vakum" diye
        # basacaktı — yani yayımlanan büyüklük kullanıcının seçtiği irtifa
        # listesine bağlıydı.
        #
        # Doğrusu bu fonksiyonun KENDİ meta sözlüğünde zaten hesaplıydı:
        # ``thrust_vacuum = eta_v*mdot*v_e + P_e*A_e`` (P_a = 0 limiti,
        # Sutton & Biblarz 9. baskı Eq. 2-16 / 3-29). Isp tanımından
        # (Eq. 2-5) I_sp,vac = F_vac / (mdot * g0). Tek kaynak: sayı
        # ``_fixed_nozzle_altitude_sweep`` metasından okunur, burada
        # yeniden türetilmez.
        thrust_vacuum = float(meta.get('thrust_vacuum_n', 0.0))
        vacuum_isp = (thrust_vacuum / (mdot * G_0)) if mdot > 0 else 0.0

        return {
            'altitude_performance': performance_data,
            # --- ÖH D20 / B3-13 · 'sea_level_isp' ARTIK DENİZ SEVİYESİ ----
            # Burada ``performance_data[0]['isp']`` yazılıydı: listenin İLK
            # SATIRI, hangi irtifa olursa olsun (vacuum_isp'nin F3-3 kusuruyla
            # aynı sınıf — o, listenin EN ÜST satırını "vakum" diye
            # yayımlıyordu ve düzeltilmişti; ikizi burada kalmıştı).
            # Çağıran 5 km'den başlayan bir liste verdiğinde 5 km'nin Isp'si
            # 'sea_level_isp' adıyla manşete, karşılaştırma paneline ve
            # ürün özetine giriyordu. Artık irtifa = 0 satırı ARANIR;
            # yoksa sayı UYDURULMAZ, None döner ve gerekçesi söylenir.
            'sea_level_isp': next(
                (satir['isp'] for satir in performance_data
                 if float(satir.get('altitude', float('nan'))) == 0.0), None),
            'sea_level_isp_basis': _SEA_LEVEL_ISP_BASIS,
            'vacuum_isp': vacuum_isp,
            #: Vakum Isp'sinin dayanağı: irtifa tablosundan OKUNMAZ, P_a = 0
            #: limitinden gelir; bu yüzden irtifa listesi kısalsa/uzasa bile
            #: değişmez.
            'vacuum_isp_basis': (
                'vacuum specific impulse from the P_a = 0 thrust limit '
                '(F_vac = eta_v*mdot*v_e + P_e*A_e, Sutton & Biblarz 9th ed. '
                'Eq. 2-16/3-29) divided by mdot*g0, NOT the highest row of '
                'the altitude table: the published value must not depend on '
                'which altitudes the caller asked for.'),
            # T33: hangi kaybin uygulandigi (ya da uygulanmadigi) beyan edilir
            'nozzle_loss_model': meta,
        }
    
    def _calculate_thermodynamic_properties(self, chamber_comp: Dict, throat_comp: Dict, 
                                          exit_comp: Dict, T_c: float, T_t: float, T_e: float,
                                          P_c: float, P_t: float, P_e: float) -> Dict:
        """Calculate detailed thermodynamic properties"""
        
        # --- ÖH D19 (kalem B3-11) — ÖLÜ KOLLAR KALKTI, FAIL-CLOSED KONDU ---
        # Bu fonksiyonun içinde P01'in saydığı ~90 satırlık ölü kod vardı:
        # _species_mass_fractions gövdesi, calc_enthalpy ve calc_entropy'nin
        # "tür tablosundan elle topla" kolları ve istasyon döngüsünün
        # MW=30 / gamma=1,25 fallback'i (beşincisi calc_mw'nin species kolu,
        # _calculate_performance_parameters içinde).
        #
        # ÖLÇÜLDÜ (sys.settrace, once.json B3_11; 8 itici çifti, hem Cantera
        # AÇIK hem KAPALI koşumda): beş blokta da ÇALIŞAN SATIR 0 — tek
        # istisna _species_mass_fractions'ın `def` satırı, yani tanımın
        # kendisi. Karşılaştırma: aynı koşuda bu dosyanın 755 satırı çalıştı.
        # Sebep yapısal: her iki bileşim üreticisi de cp / cv / gamma /
        # molecular_weight / enthalpy / entropy ve `species` sözlüğünü
        # BİRLİKTE döndürüyor — Cantera KAPALIYKEN de (ölçülen anahtar
        # listesi rapor.md'de).
        #
        # Asıl zarar satır sayısı değildi. (1) Ölü kollar UYDURMA SAYI
        # üretiyordu: MW=30 kg/kmol, gamma=1,25, cp=1,0/1,4/1,2 kJ/(kg·K),
        # s0=200 J/(mol·K), MW=25 — yani ulaşılabilir olsalardı sessiz
        # varsayılan yayımlarlardı (FAIL-CLOSED doktrini bunu yasaklar).
        # (2) MW=30/gamma=1,25 bloğunun yorumu ULAŞILAMAZ bir garanti
        # veriyordu: "Böylece akış zincirindeki tüm fallback'ler TEK gamma
        # kullanır" — B3-06 ölçümü bunun yanlış olduğunu göstermişti
        # (Cantera'sız yolda 1,195914 ⟷ 1,25). Garantiyi doğrulayacak kod
        # hiç çalışmadığı için garanti hiç sınanamıyordu.
        #
        # Ölü kollar silindi; yerlerine eksik alanı ADIYLA söyleyen hata
        # kondu. Ürün davranışı değişmez (kollar ölçülmüş biçimde ölüydü);
        # değişen, ileride bir üretici alanı düşürürse SESSİZ UYDURMA yerine
        # ADLI RET alınmasıdır.
        _GEREKLI_TERMO_ALANLAR = ('cp', 'cv', 'gamma', 'molecular_weight')

        def _eksik_alanlar(composition, gerekli):
            if not isinstance(composition, dict):
                return list(gerekli)
            return [k for k in gerekli if k not in composition]

        def calc_enthalpy(composition: Dict, temperature: float) -> float:
            """Karışım entalpisi [kJ/kg] — ÇÖZÜLEN değerden doğrudan.

            Denge çözücüsünün karışım entalpisi (gas.enthalpy_mass, J/kg)
            1000'e bölünerek kJ/kg'ye çevrilir; oluşum entalpisi dahildir.

            ÖH D19 (B3-11): buradaki "tür tablosundan elle topla" kolu
            ÖLÇÜLMÜŞ BİÇİMDE ÖLÜYDÜ (0 satır, Cantera açık ve kapalı) ve
            tür başına cp=1,0/1,4/1,2 kJ/(kg·K) gibi uydurma sabitler
            taşıyordu. Silindi; alan yoksa artık ADLI RET veriliyor.
            """
            if ('enthalpy' in composition
                    and isinstance(composition.get('species'), dict)):
                return composition['enthalpy'] / 1000.0
            # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
            raise ValueError(
                "Combustion composition does not carry a solved mixture "
                "enthalpy (required fields: 'enthalpy' and a 'species' "
                "dict). Station enthalpy is not published from a "
                "simplified per-species table with assumed heat "
                "capacities.")


        def calc_entropy(composition: Dict, temperature: float, pressure: float) -> float:
            """Karışım entropisi [kJ/(kg·K)] — ÇÖZÜLEN değerden doğrudan.

            Denge çözücüsünün karışım entropisi (gas.entropy_mass,
            J/(kg·K)) 1000'e bölünerek kJ/(kg·K)'ye çevrilir.

            ÖH D19 (B3-11): buradaki "s0 tablosundan elle topla" kolu
            ÖLÇÜLMÜŞ BİÇİMDE ÖLÜYDÜ (0 satır, Cantera açık ve kapalı) ve
            tabloda olmayan tür için s0=200 J/(mol·K) uyduruyordu.
            Silindi; alan yoksa artık ADLI RET veriliyor.
            """
            if ('entropy' in composition
                    and isinstance(composition.get('species'), dict)):
                return composition['entropy'] / 1000.0
            # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
            raise ValueError(
                "Combustion composition does not carry a solved mixture "
                "entropy (required fields: 'entropy' and a 'species' dict). "
                "Station entropy is not published from a partial standard "
                "entropy table with an assumed default for missing species.")


        def calc_gibbs_energy(enthalpy: float, entropy: float, temperature: float) -> float:
            """Calculate Gibbs free energy"""
            return enthalpy - temperature * entropy
        
        # Calculate properties for each station
        properties = {}
        
        stations = [
            ('chamber', chamber_comp, T_c, P_c),
            ('throat', throat_comp, T_t, P_t),
            ('exit', exit_comp, T_e, P_e)
        ]
        
        for station_name, comp, T, P in stations:
            h = calc_enthalpy(comp, T)
            s = calc_entropy(comp, T, P)
            g = calc_gibbs_energy(h, s, T)

            if isinstance(comp, dict) and all(
                    k in comp for k in _GEREKLI_TERMO_ALANLAR):
                # Cantera denge çözümünden GERÇEK termodinamik değerler.
                # Eski kod bunları hesaplayıp atıyor, her istasyonda sabit
                # cp=1200 / gamma=1.3003 kullanıyordu (Bulgu 4).
                cp_j = comp['cp']                 # J/(kg·K) (frozen, rapor için)
                cv_j = max(comp['cv'], 1e-3)      # J/(kg·K), negatif koruması
                # Isentropik üs: denge çözümünden gelen shifting-equilibrium
                # değeri (comp['gamma']) kullanılır. cp_j/cv_j (frozen) yüksek
                # sıcaklıkta disosiyasyonu yok sayıp gamma'yı ~%7-9 fazla verir
                # ve c*'ı ~%4 düşük çıkarır (NASA CEA shifting-eq. kullanır).
                gamma_local = comp.get('gamma', cp_j / cv_j)
                R_mix = self.R_universal / comp['molecular_weight']  # J/(kg·K)
                rho = comp.get('density', P * 1e5 / (R_mix * max(T, 1.0)))  # kg/m³
            else:
                # ÖH D19 (kalem B3-11) — SESSİZ FALLBACK KALKTI.
                # Burada MW=30 kg/kmol ve gamma=1,25 uyduruluyor, üstelik
                # yorum "Böylece akış zincirindeki tüm fallback'ler TEK
                # gamma kullanır" diye ULAŞILAMAZ bir garanti veriyordu
                # (B3-06: Cantera'sız yolda 1,195914 ⟷ 1,25 ölçüldü).
                # Blok ölçülmüş biçimde ÖLÜ (0 satır, Cantera açık/kapalı),
                # bu yüzden ret ürün davranışını değiştirmez; değişen,
                # bir gün bir üretici alan düşürürse uydurma yerine ADLI
                # RET alınmasıdır.
                eksik = _eksik_alanlar(comp, _GEREKLI_TERMO_ALANLAR)
                # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
                raise ValueError(
                    "Combustion composition for station '%s' is missing the "
                    "solved thermodynamic fields: %s. Station gamma, cp, "
                    "density and speed of sound are not published from "
                    "assumed values (the retired fallback assumed "
                    "MW = 30 kg/kmol and gamma = 1.25)."
                    % (station_name, ', '.join(eksik) or 'unknown'))

            # Speed of sound (güvenli sqrt)
            T_safe = max(T, 300)  # Minimum 300K sıcaklık sınırı
            a = np.sqrt(gamma_local * R_mix * T_safe)

            # ÖH D24 / P15B1-05 — BİRİM ADIN İÇİNDE (1000× tuzağı kapatıldı).
            # ÖLÇÜLDÜ (once.json K2, taban 2e4d81f): aynı yanıtta DÖRT ad
            # iki ayrı birimde yayımlanıyordu ve fark TAM 1000 kattı —
            #   compositions.chamber.enthalpy = 1 605 035,2237607732  J/kg
            #   ...stations.chamber.enthalpy  =     1 605,0352237607733 kJ/kg
            # (cp, cv, entropy için de aynı ikilik). Ad birim taşımadığı
            # için iki gövde ayırt edilemiyordu; 'enthalpy' okuyan tüketici
            # hangisine düştüğünü bilemiyordu. Bu blok kJ tabanlı olan
            # taraftır, dolayısıyla ADI kJ'yi söyler. TEK AD yayımlanır
            # (eski ad ikizi BIRAKILMADI — iki ad tuzağı sürdürürdü);
            # birim dizgilerinin tek kaynağı aşağıdaki 'units' bloğudur.
            properties[station_name] = {
                'enthalpy_kJ_kg': h,
                'entropy_kJ_kg_K': s,
                'gibbs_energy_kJ_kg': g,
                'cp_kJ_kg_K': cp_j / 1000.0,
                'cv_kJ_kg_K': cv_j / 1000.0,
                'gamma': gamma_local,
                # v2.6.2 fizik denetimi, bulgu F095: istasyon MW'si artık
                # KAYDEDİLİYOR. R_mix zaten ondan türetiliyordu ama değerin
                # kendisi atılıyor, aşağıdaki ortalama da sabit 30.0 ile
                # dolduruluyordu. R_universal/R_mix özdeşliğiyle geri alınır.
                'molecular_weight': self.R_universal / R_mix,  # kg/kmol
                'speed_of_sound': a,  # m/s
                'density': rho,       # kg/m³
                'temperature': T,     # K
                'pressure': P         # bar
            }
        
        # Calculate property changes
        delta_h = (properties['exit']['enthalpy_kJ_kg']
                   - properties['chamber']['enthalpy_kJ_kg'])
        delta_s = (properties['exit']['entropy_kJ_kg_K']
                   - properties['chamber']['entropy_kJ_kg_K'])

        return {
            'stations': properties,
            # ÖH D24 / P15B1-05 — birim dizgilerinin TEK KAYNAĞI. İstasyon
            # alanları adlarında birimi taşır; bu blok makine tarafından
            # okunabilir karşılığıdır (tüketici birimi tahmin etmez).
            'station_units': dict(_STATION_UNITS),
            'deltas': {
                'enthalpy_change_kJ_kg': delta_h,
                'entropy_change_kJ_kg_K': delta_s,
                'pressure_ratio': P_c / P_e,
                'temperature_ratio': T_c / T_e
            },
            'isentropic_efficiency': self._calculate_isentropic_efficiency(properties),
            # --- ÖH D25 / OH-Z5-02 · ÖZDEŞLİĞİN YANITTA BEYANI -----------
            # Bu oran bir DONANIM kaybı ölçüsü değildir ve girdiyle
            # oynamaması kusur DEĞİL, istasyon tablosunun kuruluşunun
            # doğrudan sonucudur: boğaz ve çıkış istasyonları ODA
            # ENTROPİSİNDE çözülür (``gas.SP = s_0, P`` + ``equilibrate
            # ('SP')`` — _equilibrium_station / _solve_equilibrium_throat),
            # yani s_e − s_c YAPISAL olarak sıfırdır ve
            #     eta_s = Δh / (Δh + T_e·(s_e − s_c)) = Δh / Δh = 1
            # ALGEBRAİK bir özdeşliktir.
            # ÖLÇÜLDÜ (docs/scofield/raw/OH/D25/hibrit/a1/once.json, K1;
            # Pc = 10/20/40 bar × eps = 4/10/25, dokuz koşu): s_e − s_c'nin
            # en büyük mutlak değeri 5,51e-11 kJ/(kg·K) — oda entropisine
            # göre bağıl 5,5e-12, yani ``equilibrate('SP')`` yakınsama
            # artığı; ham oran 1'den en çok 4,2e-11 sapıyor.
            # Sayı yine de bilgi taşır — istasyon zinciri bir gün oda
            # izentropundan kayarsa oran 1'in ALTINA iner — bu yüzden
            # kaldırılmaz, NE OLDUĞU adıyla yayımlanır. Aynı sözlükteki
            # 'deltas.entropy_change' özdeşliğin ham kanıtını zaten taşır.
            'isentropic_efficiency_basis': (
                'IDENTITY, not a loss measurement: the throat and exit '
                'stations are solved AT THE CHAMBER ENTROPY (Cantera SP + '
                'equilibrate), so s_exit - s_chamber is structurally zero '
                'and eta_s = dh/(dh + T_e*ds) collapses to 1 by '
                'construction. Read it as a self-consistency residual of '
                'the station table (a value below 1 would mean the station '
                'chain drifted off the chamber isentrope), NOT as a '
                'hardware efficiency: the delivered specific impulse comes '
                'from performance.isp, not from this ratio.'),
            'flow_properties': {
                # --- ÖH D20 / B3-13 · AD ↔ DAVRANIŞ -----------------------
                # Bu üç alan 'mass_averaged_*' adını taşıyordu ama hiçbiri
                # kütleyle ağırlıklandırılmıyor: üç istasyonun (oda/boğaz/
                # çıkış) DÜZ ARİTMETİK ORTALAMASI alınıyor ve istasyonların
                # kütle payı diye bir büyüklük bu sözlükte hiç yok (sabit
                # geometrili nozulda üç istasyondan da AYNI ṁ geçer, yani
                # kütle ağırlığı zaten tanımsızdır). Ad düzeltildi;
                # ``/`` böleni de 3 sabitinden istasyon SAYISINA çevrildi
                # (üç istasyon varsayımı sessizce gömülüydü).
                # Depoda ürün tarafında tüketicisi yoktu (git grep
                # 'mass_averaged' -- hrma/ tests/ -> yalnız bu üç satır).
                'station_mean_gamma': (sum(p['gamma']
                                           for p in properties.values())
                                       / len(properties)),
                'station_mean_cp_kJ_kg_K': (
                    sum(p['cp_kJ_kg_K'] for p in properties.values())
                    / len(properties)),
                'station_mean_basis': (
                    'unweighted arithmetic mean over the chamber/throat/exit '
                    'stations of THIS expansion - not a mass-weighted '
                    'average: the same mass flow passes every station of a '
                    'fixed-geometry nozzle, so no mass weighting is defined.'),
                # v2.6.2 fizik denetimi, bulgu F095: burada
                # `sum(30.0 for _ in properties.values()) / 3` yazılıydı — yani
                # istasyon sayısı kadar 30.0 toplanıp bölünüyordu; sonuç HER
                # ZAMAN 30.0 ve hesaplanan bileşimle hiçbir ilgisi yok.
                # Gerçek istasyon MW'leri aynı fonksiyonda zaten mevcut.
                'station_mean_mw': (sum(p['molecular_weight']
                                        for p in properties.values())
                                    / len(properties))
            }
        }
    
    def _calculate_isentropic_efficiency(self, properties: Dict) -> float:
        """Tabloya yazılan oda->çıkış genişlemesinin izentropik verimi [-].

        DÜZELTME (v2.6.2 fizik denetimi, bulgu F032). ESKİ DAVRANIŞ: pay ile
        payda FARKLI tabandaydı. Pay h_oda - h_çıkış idi ve bu entalpiler
        oluşum entalpisini içeren KAYAN-DENGE (shifting) değerleridir —
        rekombinasyon ısısını da taşırlar. Payda ise DONMUŞ (frozen) cp ile
        cp_oda·(T_c - T_e,izentropik) olarak kuruluyordu. Oran bu yüzden
        yapısal olarak 1'in üstüne çıkıyor, [0.8, 1.0] kırpması bunu
        maskeliyordu; fonksiyon fiilen HER ZAMAN 1.0 döndürüyordu (ölçüldü:
        htpb/n2o O/F=6 Pc=20 bar, eps=10 -> ham oran 1.2539, raporlanan 1.0).

        YENİ TANIM — pay ve payda AYNI tabanda (istasyon tablosunun kendi
        entalpi/entropi fonksiyonları), Gibbs bağıntısından türetilir. Sabit
        basınçta dh = T·ds olduğundan, çıkış basıncında gerçek izentropik
        (s = s_oda) entalpi birinci mertebeden

            h_e,izentropik = h_e - T_e·(s_e - s_oda)

        yazılır ve

            eta_s = (h_oda - h_e) / [ (h_oda - h_e) + T_e·(s_e - s_oda) ]

        elde edilir. Entropi üretimi sıfırsa (ideal) eta_s = 1; entropi
        üretildikçe 1'in altına iner. Kırpma YOKTUR: sayı artık bilgi taşır.

        DOĞRULAMA (bu depoda ölçüldü, htpb/n2o O/F=6 Pc=20 bar; payda ayrıca
        Cantera'da gas.SP + equilibrate('SP') ile TAM izentropik denge
        çözülerek bağımsız hesaplandı):
            eps=4   eta_lin=0.9314  eta_tam=0.9330  (fark %0.2)
            eps=10  eta_lin=0.8917  eta_tam=0.8977  (fark %0.7)
            eps=25  eta_lin=0.8738  eta_tam=0.8846  (fark %1.2)
            eps=60  eta_lin=0.8669  eta_tam=0.8820  (fark %1.7)
        Doğrusallaştırma hatası genişleme oranıyla büyür ama %2'nin altında
        kalır; buna karşılık bu form Cantera'sız (atom dengesi) yolda da
        çalışır ve ek denge çözümü maliyeti getirmez.

        YORUM: değer, TABLOLANAN çıkış istasyonunun (tek-gamma izentropik
        sıcaklıktan türetilmiş) ideal genişlemeye göre verimidir; bir donanım
        kaybı ölçüsü DEĞİLDİR. Motorun raporlanan Isp'i buradan gelmez —
        performance['isp'] ayrıca _calculate_frozen_shifting_isp içinde tam
        izentropik denge çözümüyle (gas.SP + equilibrate) hesaplanır. Bu alan
        istasyon tablosunun kendi iç tutarlılığını gösterir.

        SINIRLAMA (Cantera kurulu DEĞİLKEN): istasyon entalpi/entropileri
        atom-dengesi yolundan (yalnız duyulur terim + kaba, sıcaklığa bağlı
        gamma tahmini) gelir. Bu zincir entropi-tutarlı değildir; ölçüldü
        (htpb/n2o O/F=6 Pc=20 bar): ham oran eps=None'da 1.907, eps=60'ta
        1.208 — yani s_çıkış < s_oda çıkıyor. Bu modelde entropi üretimi
        tanımsız olduğundan sonuç fiziksel üst sınır olan 1.0'a (ideal
        genişleme) sabitlenir; uydurma bir kayıp sayısı ÜRETİLMEZ. Anlamlı
        (1'den küçük) değer için Cantera gerekir.

        Kaynak: Gibbs bağıntısı dh = T·ds + v·dp (sabit p'de dh = T·ds);
        izentropik verim tanımı Sutton & Biblarz, "Rocket Propulsion
        Elements" 9. baskı Böl. 3 (ideal ve gerçek genişleme karşılaştırması).
        """
        h_c = properties['chamber']['enthalpy_kJ_kg']
        h_e = properties['exit']['enthalpy_kJ_kg']
        s_c = properties['chamber']['entropy_kJ_kg_K']
        s_e = properties['exit']['entropy_kJ_kg_K']
        T_e = properties['exit']['temperature']

        h_actual = h_c - h_e                       # kJ/kg
        ds_gen = s_e - s_c                         # kJ/(kg·K)
        h_isentropic = h_actual + T_e * ds_gen     # kJ/kg (aynı taban)

        if h_actual <= 0.0 or h_isentropic <= 0.0:
            # Genişleme yok / fiziksel olmayan istasyon çifti: sahte bir sayı
            # uydurmak yerine tanımsız-ama-nötr 1.0 döndürülür ve loglanır.
            logger.warning(
                "İzentropik verim tanımsız (h_act=%.3f, h_is=%.3f kJ/kg); "
                "1.0 raporlanıyor.", h_actual, h_isentropic)
            return 1.0

        eta_s = h_actual / h_isentropic
        # Üst sınır 1.0: ds_gen < 0 (entropi ÜRETİLMEMİŞ, yani istasyon
        # zinciri termodinamik olarak tutarsız) durumunda oran 1'i aşar.
        # Fiziksel üst sınır 1'dir; aşım bir MODEL tutarsızlığıdır, loglanır.
        if eta_s > 1.0:
            # Cantera'sız (atom dengesi) yolda BEKLENEN durum — bkz. docstring
            # "SINIRLAMA". Cantera varken görülürse istasyon zinciri gerçekten
            # tutarsızdır; her iki halde de fiziksel üst sınır 1.0 döndürülür.
            logger.debug(
                "İzentropik verim ham oranı 1'i aştı (%.4f): çıkış istasyonu "
                "entropisi oda entropisinden küçük; 1.0 (ideal) raporlanıyor.",
                eta_s)
            return 1.0
        return float(eta_s)


    def calculate_thrust_at_altitudes(self, total_impulse: float, motor_data: Dict, 
                                    altitudes: List[float]) -> Dict:
        """Calculate thrust at different altitudes from total impulse.

        T33 (2026-08-03) — KÜTLE DEBİSİ ARTIK UYDURULMUYOR. Eski kod
        ``base_mdot = teslim edilen itki / (İDEAL Isp · g0)`` diyordu; bu iki
        ayrı verim tanımını böler ve çözücünün gerçek debisiyle uyuşmayan bir
        sayı üretir (ölçüldü: 0,5312 kg/s ↔ çözücünün 0,548540 kg/s'i,
        %3,4 sapma). Debi artık ``motor_data['mdot_total']`` ile çözücüden
        gelir; verilmezse eski türetme korunur ve ``mass_flow_basis`` ile
        bildirilir. İrtifa taraması kardeş tabloyla AYNI tanım noktasından
        (``_fixed_nozzle_altitude_sweep``) yapılır.

        T32 (2026-08-03) — 'impulse_efficiency' %110'a çıkıyordu. Metrik
        deniz seviyesi tasarım impulsüne normalize ediliyordu
        (etkin/deniz-seviyesi), oysa panelin kendi açıklaması "vakum
        impulsünün fiilen teslim edilen yüzdesi" diyor ve bir VERİM
        göstergesi %100'ü aşamaz. Payda artık gerçek VAKUM impulsüdür
        (F_vac = eta_v·mdot·v_e + P_e·A_e, yani P_a = 0), dolayısıyla oran
        yapısı gereği ≤ 1'dir ve vakumda tam olarak 1 olur. Deniz seviyesine
        göre kazanç bilgisi kaybolmadı: ayrı ve DOĞRU adlandırılmış
        ``impulse_gain_vs_sea_level`` alanında duruyor.
        """

        thrust_data = []
        if not altitudes:
            return {'thrust_altitude_data': [], 'input_total_impulse': total_impulse,
                    'base_thrust_sea_level': 0, 'max_thrust': 0,
                    'max_thrust_altitude': None, 'vacuum_thrust': 0}

        # Base performance at sea level
        base_isp = motor_data['performance']['isp']
        # ÖH D36 / onemli2-sivi a2 — SÜRE UYDURULMAZ. Eski satır
        # ``motor_data.get('burn_time', 10)`` idi: süre verilmediğinde deniz
        # seviyesi itkisi toplam impuls / 10 s olarak UYDURULUYOR ve bütün
        # irtifa tablosu (itki, impuls verimi) o sayıdan kuruluyordu
        # (ölçüldü, a2/once.json K5: 21 000 N·s impulsla 'burn_time' yokken
        # base_thrust_sea_level = 2100,0 N, 10 s verilmişle BİT-AYNI). Süre
        # yoksa tablo ÇİZİLMEZ ve nedeni adıyla döner (durum sözcüğü deponun
        # hüküm sözcüğüdür: safety_analysis.THERMAL_VERDICT_NOT_EVALUATED ile
        # aynı dize). Süre verildiğinde hesap aynen koşar; tek çağıran
        # (hibrit motor) süreyi daima verir.
        burn_time = motor_data.get('burn_time')                        # s
        if burn_time is None or not float(burn_time) > 0.0:
            return {
                'status': 'NOT_EVALUATED',
                'reason': (
                    'burn time not supplied (motor_data has no positive '
                    'burn_time) and no duration is assumed, so the sea-level '
                    'thrust (total impulse / burn time) and the altitude '
                    'table built on it were not computed. The previous code '
                    'silently used 10 s here.'),
                'thrust_altitude_data': [],
                'input_total_impulse': total_impulse,
                'base_thrust_sea_level': None,
                'max_thrust': None,
                'max_thrust_altitude': None,
                'vacuum_thrust': None,
            }
        base_thrust = total_impulse / burn_time                        # N (TESLİM EDİLEN)
        solver_mdot = motor_data.get('mdot_total')
        if solver_mdot is not None and float(solver_mdot) > 0.0:
            base_mdot = float(solver_mdot)
            mass_flow_basis = ('mass flow taken from the solver '
                               '(mdot_total), not derived from Isp')
        else:
            base_mdot = base_thrust / (base_isp * G_0)
            mass_flow_basis = ('NOT_FROM_SOLVER: mdot_total was not supplied, '
                               'so the mass flow is derived as thrust / '
                               '(Isp x g0) and mixes two efficiency '
                               'definitions')

        v_exit = motor_data['performance']['velocities']['exit']   # m/s (SABIT, tasarim)
        P_e_bar = motor_data['conditions']['exit']['P']            # bar (tasarim cikis basinci)
        T_e = motor_data['conditions']['exit']['T']                # K
        R_e = motor_data['performance']['gas_constants']['exit']   # J/(kg·K)

        rows, meta = self._fixed_nozzle_altitude_sweep(
            base_mdot, v_exit, P_e_bar, T_e, R_e, altitudes,
            thrust_sea_level=base_thrust)
        meta['mass_flow_basis'] = mass_flow_basis

        # Vakum impulsü — irtifa veriminin PAYDASI (T32)
        vacuum_total_impulse = meta['thrust_vacuum_n'] * burn_time

        for row in rows:
            effective_total_impulse = row['thrust'] * burn_time
            thrust_data.append({
                'altitude': row['altitude'],
                'pressure': row['pressure'],
                'temperature': row['temperature'],
                'thrust': row['thrust'],
                'isp': row['isp'],
                'exit_velocity': row['exit_velocity'],
                'effective_total_impulse': effective_total_impulse,
                # ≤ 1 by construction: payda VAKUM impulsü (P_a = 0 halinde
                # bu motorun teslim edebileceği en büyük impuls).
                'impulse_efficiency': (effective_total_impulse
                                       / vacuum_total_impulse
                                       if vacuum_total_impulse else 0.0),
                # Eski (deniz seviyesine göre) oran — bir VERİM değil, KAZANÇ
                'impulse_gain_vs_sea_level': (effective_total_impulse
                                              / total_impulse
                                              if total_impulse else 0.0),
            })

        return {
            'thrust_altitude_data': thrust_data,
            'input_total_impulse': total_impulse,
            'base_thrust_sea_level': base_thrust,
            'vacuum_total_impulse': vacuum_total_impulse,
            'impulse_efficiency_basis': (
                'delivered impulse at that altitude divided by the VACUUM '
                'impulse of the same motor; 1.0 means nothing is lost to back '
                'pressure, so the value cannot exceed 1'),
            'nozzle_loss_model': meta,
            'max_thrust': max([p['thrust'] for p in thrust_data]),
            'max_thrust_altitude': thrust_data[np.argmax([p['thrust'] for p in thrust_data])]['altitude'],
            # v2.6.26 — bu bir SONUÇ gibi duruyor ama tarama
            # ızgarasının ucudur: sabit geometrili lülede itki irtifayla
            # monoton arttığı için argmax daima son noktaya düşer.
            # Kardeş 'max_thrust' gerçekten canlıdır.
            'max_thrust_altitude_basis': (
                'top of the altitude sweep grid, not an optimum: thrust '
                'increases monotonically with altitude for a fixed-geometry '
                'nozzle, so the argmax always lands on the last grid point'),
            # --- D15/P1B3-01 · VAKUM İTKİSİ IZGARANIN UCU DEĞİLDİR -------
            # ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/hibrit/a3/once.json,
            # B3_01): eski satır ``thrust_data[-1]['thrust']`` idi, yani
            # tarama IZGARASININ SON SATIRI. Ürünün sabit ızgarasında
            # (20 km) yayımlanan sayı 1109,9424 N, gerçek P_a=0 limiti ise
            # 1116,2222 N -> 6,2798 N / %0,5626 düşük. Daha kötüsü sayı
            # ÇAĞIRANIN ızgarasına bağlıydı: aynı motorda 10 km ızgarasında
            # 1085,8992 N, 80 km ızgarasında 1116,2212 N (yayılım 30,32 N).
            # Bu, kapanmış F3-3'ün (vacuum_isp) birebir ikiziydi; aynı
            # sözlükteki kardeşler zaten doğrusunu yapıyordu
            # (vacuum_total_impulse = meta['thrust_vacuum_n'] x burn_time).
            # Artık alan gerçek vakum limitidir ve ızgaranın ucu, adı
            # kendini söyleyen ayrı bir alanda durur.
            'vacuum_thrust': meta['thrust_vacuum_n'],
            'vacuum_thrust_basis': (
                'true vacuum limit of this fixed-geometry nozzle at P_a = 0 '
                '(F_vac = eta_v x mdot x v_e + P_e x A_e), taken from the '
                'same sweep metadata that feeds vacuum_total_impulse. It is '
                'NOT the last row of the altitude grid: that row is only as '
                'high as the caller happened to sweep and is published '
                'separately as top_of_grid_thrust.'),
            'top_of_grid_thrust': (thrust_data[-1]['thrust']
                                   if thrust_data else 0),
            'top_of_grid_altitude_m': (thrust_data[-1]['altitude']
                                       if thrust_data else None),
        }