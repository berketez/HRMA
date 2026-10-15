import numpy as np
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid
from typing import Dict
from scipy.optimize import fminbound, minimize_scalar, brentq
from hrma.engines.combustion_analysis import (
    CombustionAnalyzer, OPERATING_POINT_DESIGN)
from hrma.engines.nozzle_design import (
    NozzleDesigner, sample_nozzle_inner_contour,
    NOZZLE_FRICTION_EFFICIENCY_DEFAULT)
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
# ÖH D17 / P15B2-08: hibrit yakıt yoğunlukları TEK KAYNAK.
from hrma.data.propellant_database import (
    HYBRID_FUEL_DENSITY_KG_M3 as _FUEL_RHO)
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.regression_analysis import (
    RegressionAnalyzer, fuel_mass_flow_kg_s,
    grain_length_for_fuel_mass_flow_m)
# Yayımlanan eğrilerin tepeyi koruyan seyreltmesi — katı ile AYNI algoritma,
# TEK tanım noktası (bkz. hrma/analysis/curve_sampling.py: ölçülen kusur
# port 5 mm + t_b 50 s -> 17 317 nokta / 1,29 MB idi).
from hrma.analysis.curve_sampling import (
    decimate_curve_indices as _ortak_seyreltme_indeksleri,
    sampling_block as _ornekleme_blogu,
)
from hrma.data.external_data_fetcher import data_fetcher
from hrma.data.propellant_database import (
    HYBRID_REGRESSION_COEFFICIENTS,
    # ÖH D33-3 / OH-D33-46: G_ox-fit katsayının G_total kapanışı altında
    # getirdiği sistematik yükseltme bandı. Sayı orada YAŞAR, buraya
    # kopyalanmaz (CLAUDE.md kural 11).
    HYBRID_GOX_FIT_UNDER_GTOTAL_LIFT_PCT,
    # ÖH D31 / OH-D21-04: ödünç alınmış (a, n) çiftini ADIYLA bildirmek için
    # künye tablosu TEK KAYNAKTAN okunur; buraya kopyalanmaz.
    HYBRID_REGRESSION_SOURCES,
    N2O_LIQUID_DENSITY_SAT_25C,
)
from hrma.constants import (G_0, LAMBDA_BELL, LAMBDA_PARABOLIC,
                            LAMBDA_CONICAL_15DEG, C_STAR_PLAUSIBLE_BAND_MPS,
                            C_STAR_BAND_DEFAULT_MPS, R_UNIVERSAL, PA_PER_BAR,
                            AMBIENT_TEMPERATURE_BAND_K)
# Ayrılma eşiği TEK tanım noktasından gelir (magic-number yasağı): aynı 0,40
# hrma/flow/separation.py ve engines/nozzle_design.py içinde de bu addan
# türetilir. Buraya sayı KOPYALANMAZ.
from hrma.flow.separation import SUMMERFIELD_FACTOR_DEFAULT
# Kullanıcı Cd bandı TEK tanım noktasından (bkz. USER_CD_RANGE künyesi):
# hibrit ve sıvı motor kullanıcıya farklı kapı açamaz. Sayı KOPYALANMAZ.
from hrma.engines.injector_design import USER_CD_RANGE
# ÖH D26 / P14M2-05(+b): enjektör ΔP/Pc TASARIM oranı TEK tanım noktasından
# gelir (hrma/analysis/acoustic_modes.CHUG_DP_RATIO_RECOMMENDED). Buraya sayı
# KOPYALANMAZ — kopya, eşik değiştiğinde kullanıcıya ESKİ sayıyla boyutlanmış
# bir enjektör vermeye devam ederdi. ÖLÇÜLDÜ (once.json/P14M2-05): eşik
# koşum sırasında 0,40'a da 0,02'ye de çekildiğinde ΔP 4,0 barda (0,2·Pc)
# çakılı kaldı; türetme İKİ YÖNDE de yoktu.
from hrma.analysis.acoustic_modes import CHUG_DP_RATIO_RECOMMENDED
from hrma.utils import input_guard
import warnings

#: ÖH D21 / P15B1-04 — manşet Isp'sinin künyesi (kullanıcıya dönük: İngilizce).
_ISP_HEADLINE_BASIS = (
    'DELIVERED specific impulse at the design point, sea level: '
    'Isp = CF * c_star / g0 with the headline thrust coefficient, which '
    'carries the divergence efficiency of THIS contour and the same loss set '
    'the nozzle panel applies (friction x two-phase x kinetic). This is the '
    'number the screen, the report and the AI export all show. The other Isp '
    'leaves of this response are DIFFERENT QUANTITIES, not competing answers '
    'to one question: nozzle_design.performance.kinetic.isp_shifting_s / '
    'isp_frozen_s / isp_predicted_s are the ideal shifting and frozen '
    'expansion limits and the kinetic blend between them; '
    'combustion_analysis.performance.isp is the ideal equilibrium value of '
    'the combustion solver; nozzle_design.performance.specific_impulse is '
    'the nozzle module\'s own coefficient times its OWN single-gamma '
    'characteristic velocity, so it differs from this field by the c_star '
    'definition (measured 1.00075x on the default hybrid run) and, away from '
    'adapted expansion, by where the divergence factor multiplies the '
    'pressure-thrust term - both gaps are quantified in '
    'thrust_coefficient_cross_check.')

# --- Kamara boyu bölümlendirme katsayıları (v2.5.2 L* modeli) ---
# Ön-yanma odası boyu = PRE_CHAMBER_D_FACTOR · D_kamara (sabit oran).
# Art-yanma odası boyu L* hacminden çözülür; aşağıdaki oranlarla
# kelepçelenir (çok kısa = yanma tamamlanmaz, çok uzun = ölü ağırlık).
# Kaynak: Sutton & Biblarz 9. baskı Böl. 8/16; Chiaverini & Kuo (2007).
# Yanma integrasyonu adım sayısı ÜST SINIRI (2026-07-23 kararlılık denetimi).
# Adım sayısı t_b ve port çapından türetiliyor ve tavansızdı: uç girdilerde
# (burn_time=1e12 -> 5.6 trilyon adım) süreç fiilen kilitleniyor, dakikalarca
# dönüp megabaytlarca uyarı günlüğü üretiyordu. Geçerli tasarım aralığının en
# kötü hâli ~17 000 adımdır; bu tavan onun on katından fazla olduğu için
# meşru hesapların çözünürlüğünü ETKİLEMEZ, yalnız kilitlenmeyi keser.
MAX_BURN_INTEGRATION_STEPS = 200_000

# Kullanıcının gönderdiği regresyon katsayısının "aslında katalog değeri"
# sayılacağı bağıl tolerans. Arayüz alanı katalog değeriyle ÖN-DOLDURULUYOR
# ve bir tur sonra ekranda 3.680e-05 gibi yuvarlanmış hâlde gösteriliyor
# (advanced.html:3062); kullanıcı hiçbir şey yapmadan bu yuvarlanmış değer
# geri gönderilebiliyor. %1 bandında katsayı fiilen yerleşik katsayıdır, bu
# yüzden yerleşik katsayının ölçülen sapma uyarısı bu bantta da geçerlidir.
REGRESSION_COEFF_CATALOG_MATCH_RTOL = 0.01

PRE_CHAMBER_D_FACTOR = 0.5
POST_CHAMBER_D_FACTOR_MIN = 0.3
POST_CHAMBER_D_FACTOR_MAX = 3.0

# --- Grain/kamara narinlik (L/D) uyarı eşiği (v2.6.27, yol haritası A10) ---
# ÖLÇÜLDÜ (bu depo, 2026-08-03): varsayılan girdiler (1000 N, 10 s, O/F 2,5,
# Pc 20 bar, tek port, G_ox = 350 kg/m²·s) grain L/D = 18,9 ve kamara
# L/D = 19,7 üretiyor — 80 mm çapında 1,58 m'lik bir boru — ve HİÇBİR uyarı
# çıkmıyordu. Düşük O/F'de daha da kötü: O/F = 2,0'de L/D = 26,3 ölçüldü.
# Tek-port hibrit pratiğinde bu narinlikte grain'ler çok-porta geçirilir
# (Sutton & Biblarz 9. baskı Böl. 16 — çok portlu grain gerekçesi;
# Chiaverini & Kuo 2007 — hacimsel verim/port yerleşimi). Eşik bir mühendislik
# pratiği bandıdır, tek bir yayımlanmış sabit değildir; TEK yerde tanımlanır
# ve uyarı parametresi olarak aynen yayımlanır (kopya eşik yasak). Aynı koşuda
# port_count = 4 seçilince L/D 8,6'ya düşüyor — öneri metninin dayanağı budur.
GRAIN_LD_WARN_THRESHOLD = 10.0

# Port oksitleyici kütle akısının FLOODING eşiği [kg/m²·s] (D15/P1B1-06).
# Bu sayı iki ayrı yerde ÇIPLAK LİTERAL olarak yazılıydı (kurucudaki
# ``initial_gox`` denetimi ve ``_design_fuel_grain`` içindeki başlangıç akısı
# denetimi); ikisi de aynı fiziği söylüyor, ikisi de ayrı ayrı değişebiliyordu.
# Tek kaynak buraya alındı ve hüküm defterinde (``design_gate_checks``) sayı
# olarak yayımlanır.
#
# KÜNYE VE GEREKÇE (KU-K4, 6 Eki 2026; 600 DEĞİŞMEDİ): eski yorum "Sutton &
# Biblarz 9. baskı Böl. 16 — flooding ~600-700 kg/m²·s'te başlar" diyordu.
# Sutton 9 s. 600-601 (Şekil 16-6) flooding sınırını yalnız NİTEL anlatır,
# SAYI VERMEZ (metin araması); aynı sayfadaki tek akı sayısı oksijenli
# hibritin TİPİK çalışma akısıdır (0,3-0,67 lbm/(s·in²) ≈ 211-471 kg/m²·s),
# sınır değil. 600 için KAYNAKLI bir eşik YOKTUR: literatürde 500-700
# kg/m²·s "pratik tasarım tavanı" olarak anılır (Fraters & Cervone, J.
# Propul. Power 32 (2016) 958-966, doi 10.2514/1.B35485, giriş bölümü;
# yazarlar bu değerlerin çoğunun türetimini ikna edici bulmaz). 600 o
# pratiğin içinde seçilmiş bir ERKEN UYARI eşiğidir. "Üstünde alev söner"
# gerekçesi de deneyle çelişir: aynı çalışma N₂O-PMMA'da 1370 kg/m²·s'e
# kadar sönme (blow-off) BULMADI; gözlenen etki yanma kararsızlığı ve c*
# veriminin düşmesidir. Yani bu eşik bir flooding/sönme sınırı DEĞİL,
# kararsızlık/verim kaybı riski için pratik tavandır. (Kullanıcıya giden
# 'basis' dizgeleri bu kulvarın satır bölgesi dışında — devir listesinde.)
OX_FLUX_FLOODING_WARN_KG_M2S = 600.0

# --- ÖH D17 / B1-11 (Fable-D15 ŞARTI) · ODA BASINCI YER TUTUCUSU [bar] -----
# Bu sayı bir TASARIM DEĞERİ DEĞİLDİR: ``chamber_pressure`` hiç verilmediğinde
# hesabın yürüyebilmesi için konan yer tutucudur ve kullanıldığı her koşuda
# ``_defaults_used`` / ``defaults_applied`` künyesiyle BEYAN EDİLİR (ÖK-19).
#
# ÖLÇÜLDÜ (a1/once.json, ``B1_11``): aynı yer tutucu ÇIPLAK LİTERAL olarak
# 10 ayrı yerde yazılıydı — motorda 2 (kurucu imzası + kapı yedeği), uç
# katmanında 8. Sayı hiçbir yerden okunmuyordu; her site kendi 20,0'ını
# taşıyordu ve birini değiştiren diğerlerini sessizce ayırıyordu.
# TEK KAYNAK BURASIDIR; ``hrma/app.py::_CALCULATE_PC_DEFAULT_BAR`` bunu
# içe aktarır.
#
# SAYI DEĞİŞTİRİLMEDİ — bu kalem bir TEKİLLEŞTİRMEDİR, fizik değişikliği
# değil. Değeri ileride değiştirmek isteyen tek satırı değiştirir; motor,
# uç ve künye üçü birden aynı sayıyı söyler.
CHAMBER_PRESSURE_PLACEHOLDER_BAR = 20.0

# c* (yanma) veriminin fiziksel bandı (D15/P1B1-06). Eşik çifti kurucudaki
# denetimde çıplak literal olarak duruyordu; hüküm defteri aynı sayıyı
# yayımladığı için TEK kaynağa alındı. Ölçülen hibrit c* verimi tipik olarak
# 0,90-0,97'dir (Chiaverini & Kuo 2007, Böl. 1 ve 10; Sutton & Biblarz 9.
# baskı Eş. 3-31); bant, ölçüm saçılımı ve düşük verimli deneysel motorlar
# için genişletilmiş savunulabilir aralıktır.
ETA_C_STAR_PHYSICAL_BAND = (0.5, 1.05)

# --- O/F -> performans ızgarası (v2.6.27, yol haritası A9) ------------------
# Hibritte yakıt regresyonu r = a·G_ox^n olduğundan port büyüdükçe akı düşer,
# yakıt debisi değişir ve O/F YANMA BOYUNCA KAYAR. Bu yüzden c* ve Isp her
# zaman adımında yeniden çözülmelidir. Her adımda Cantera dengesi çözmek
# pahalıdır (varsayılan koşuda 200 adım, uzun yanmalarda on binlerce), bu
# yüzden denge çözümü SABİT bir O/F ızgarasının düğümlerinde bir kez
# hesaplanır ve ara değerler ARA DEĞERLEMEYLE bulunur.
#
# ÖLÇÜLDÜ (bu depo, 2026-08-04, HTPB/N2O, Pc = 20 bar): önceki kod ara değeri
# EN YAKIN düğüme YUVARLIYORDU ve bu yaklaşımın hatası hiçbir yerde beyan
# edilmiyordu. Aynı O/F noktalarında c* hatası:
#     O/F = 2,42 -> en yakın düğüm  -0,2367 %    doğrusal  +0,0010 %
#     O/F = 2,47 -> en yakın düğüm  -0,2394 %    doğrusal  +0,0015 %
#     O/F = 2,53 -> en yakın düğüm  +0,2487 %    doğrusal  +0,0024 %
#     O/F = 2,58 -> en yakın düğüm  +0,2568 %    doğrusal  +0,0031 %
# Yuvarlama, ızgara adımının yarısı kadar (±0,025) O/F hatası demektir;
# c*'ta ±%0,26'ya varan sıçrama üretir ve Isp(t) eğrisinde ızgara geçişlerinde
# BASAMAK olarak görünür. Doğrusal ara değerleme AYNI düğüm sayısıyla (aynı
# denge çözümü maliyeti) hatayı iki mertebe düşürür.
OF_PERF_GRID_STEP = 0.05
# Ara değerleme hatası için BEYAN EDİLEN üst sınır [%]. Ölçülen en kötü değer
# (%0,004) bunun bir mertebe altındadır; sınır ölçüme DEĞİL, ölçümün rahatça
# altında kaldığı bir beyana bağlanır — böylece ızgara, yakıt ya da yanma
# çözücüsü değişince bekçi kusuru kilitlemez (bir kalem gerçekten modellenince
# sayı değişebilir, bekçi sabit sayıya bağlanmaz).
OF_PERF_INTERP_ERROR_BOUND_PCT = 0.05
# Hata ölçümü için düğümler ARASI (doğrusal ara değerlemenin en kötü konumu:
# aralık ortası) örnek sayısı. Her örnek bir EK denge çözümüdür (ölçüldü:
# ~20 ms/çözüm); 5 örnek ~0,1 s ek maliyet demektir.
OF_PERF_ERROR_PROBE_COUNT = 5
# Izgaranın alt ucu: O/F -> 0 kimyasal dengede anlamsızdır (yakıt yok). Eski
# kod aynı korumayı `max(of_key, 0.1)` ile satır içinde yapıyordu; burada adlı
# sabit olur (CLAUDE.md kural 11 — tek tanım yeri).
OF_PERF_MIN = 0.1

# --- O/F kayması uyarı eşiği (v2.6.27, yol haritası A9) --------------------
# O/F(t) tasarım O/F'sinden bu ORANDAN fazla saparsa kullanıcı uyarılır:
# manşetteki "tasarım Isp"si artık yanmanın tamamını temsil etmiyordur.
#
# Eşik bir MÜHENDİSLİK PRATİĞİ bandıdır, yayımlanmış tek bir sabit değildir
# (GRAIN_LD_WARN_THRESHOLD ile aynı dürüstlük); TEK yerde tanımlanır ve uyarı
# parametresi olarak aynen yayımlanır. Gerekçesi ölçülmüştür (bu depo,
# 2026-08-04, HTPB/N2O, Pc = 20 bar):
#   * c*'ın O/F duyarlılığı d ln c*/d ln(O/F): O/F = 2,5'te +0,304;
#     4,0'da +0,206; optimum 6,8 civarında -0,059; 8,0'de -0,093.
#     Yani eğrinin yalın (lean) tarafında %15 O/F sapması ~%4,6 c* (ve Isp)
#     demektir — lüle + kinetik kayıp bütçesinin tamamıyla aynı mertebe.
#     Optimum düzlüğünde aynı sapma %1'in altında kalır, orada uyarı gürültü
#     olurdu; sabit O/F bandı bu iki durumu birlikte karşılar.
#   * Ölçülen kaymalar: varsayılan koşu (regüleli besleme) +%3,83;
#     aynı koşunun blowdown beslemesi -%7,22; 30 s yanma +%7,74;
#     n = 0,75'e çıkarılmış regresyon üssü +%37,6 (ortalama Isp tasarım
#     Isp'sinden +%8,0 farklı). Eşik bu bandın neresinde durduğunu ayırır.
OF_SHIFT_WARN_FRACTION = 0.15

# --- N2O tank blowdown bloğu sabitleri (v2.6.27, yol haritası A1) ---
# Doluluk oranı: tank_blowdown/transient_ballistics imzalarındaki 0,85 ile
# aynı değer, ama burada ADLI sabit olarak beyan edilir ve bloğa açıkça
# geçirilir (hibrit sayfasında henüz doluluk girdisi yok; varsayılan
# kullanıldığı sonuçta beyan edilir). Adım sayısı: t_b/200 çözünürlük 10 s
# yanmada 50 ms'dir; blok danışma amaçlıdır, tasarım noktası sayılarını
# DEĞİŞTİRMEZ. Nokta sayısı tavanı port_history'deki ~200 örnekleme
# deseniyle aynı gerekçeyle yanıt boyutunu sınırlar.
TANK_FILL_FRACTION_DEFAULT = 0.85
TANK_BLOWDOWN_N_STEPS = 200
TANK_BLOWDOWN_MAX_POINTS = 240
# Enjektör modülüyle AYNI doymuş depolama varsayımı (bkz. _compile_results
# içindeki inj_spec['T_ox_K'] dalı): kullanıcı tank sıcaklığı vermezse iki
# modül de aynı 293,15 K değerini kullanır — tek kaynak, iki kopya sayı yok.
TANK_TEMPERATURE_DEFAULT_K = 293.15
# ÖH D37 A2 hibrit · YB-04 — ``injector_design.feed_pressure_source``un
# kendinden basınçlı N₂O değeri (tek tanım; bloğu kuran dal ve 7. turun
# ``tank_pressure_not_used_warning``ı bu addan okur).
FEED_PRESSURE_SOURCE_N2O_SAT = 'n2o_saturation_at_tank_temperature'
# ÖH D37 A2 hibrit · 7. tur YB-04 (ana model kararı, karar dosyası §28-25):
# kendinden basınçlı N₂O kipinde istekteki ``tank_pressure`` devreye GİRMEZ
# (P₁ = P_sat(T_tank)). İstek reddedilmez (kayıtlı projeler ve form alanı
# gönderiyor; geriye uyum); değer P_sat'tan bu paydan fazla saparsa adlı
# uyarı basılır. Pay HRMA SEÇİMİDİR — literatür değeri yok. Bağlam (künye
# değil, ölçüm): 293 K'de N₂O için d(ln P_sat)/dT ≈ %2,3/K, yani pay kabaca
# 1 K'lik tank sıcaklığı farkının basınç karşılığıdır (rapor 7. tur YB-04).
TANK_PRESSURE_PSAT_REL_TOL = 0.02

# --- A2/A5 modül bağlama sabitleri (v2.6.27, yol haritası) ------------------
# Oksitleyici tankı boy/çap oranı. Sıvı motordaki TANK_LD_RATIO ile AYNI
# değerdir; çapraz import bilinçli olarak yapılmaz (bkz. yukarıdaki durum
# sözlüğü notu: motor dosyaları birbirinin import zincirini çekmez). İki
# kopyanın eşit kaldığı bekçiyle denetlenir:
#   tests/test_hibrit_baglama_a5a8a2.py::test_tank_ld_orani_sivi_motorla_ayni
OX_TANK_LD_RATIO = 2.5
OX_TANK_LD_RATIO_BASIS = (
    'length/diameter ratio L/D = 2.5, a structural-efficiency design choice '
    'for a cylindrical tank (the same declared value the liquid engine uses '
    'as TANK_LD_RATIO); NOT optimised against buckling or vehicle packaging '
    '- neither is modelled here. The tank diameter and length follow from '
    'this ratio and the required volume')
# Hibrit kamara yalıtım astarı varsayılan malzemesi. thermal_protection
# modülünün tanıdığı üç ablatiften biri; silika-fenolik, hibrit/katı kamara
# yalıtımında yaygın seçimdir (NASA SP-8093 sınıfı bant, modül tablosu).
# TASARIM SEÇİMİDİR, çözüm değildir — çıktıda adıyla beyan edilir.
LINER_MATERIAL_DEFAULT = 'silica_phenolic'
# Cidar sıcaklık geçmişi örnekleme tavanı: port_history'deki ~200 nokta
# deseniyle aynı gerekçe (yanıt boyutu sınırlanır, son nokta korunur).
WALL_HISTORY_MAX_POINTS = 200

# --- A3 bağlama sabiti (v2.6.27 Dalga 6): oksitleyici tankı malzemesi ------
# Sıvı motorun tank boyutlandırmasındaki varsayılan tank malzemesiyle AYNI
# kayıt (liquid_rocket_engine._size_tank: 'al_2024_t3'); iki motor aynı
# adı taşıyan parçaya iki farklı malzeme ilan edemez. TASARIM SEÇİMİDİR,
# hesap DEĞİLDİR: hibrit sayfasında henüz tank malzemesi alanı yoktur ve
# değer çıktıda adıyla + kaynağıyla beyan edilir (kamara malzemesiyle
# KARIŞTIRILMAZ — kullanıcının seçtiği chamber_material kamaranındır).
OX_TANK_MATERIAL_DEFAULT = 'al_2024_t3'

# --- A4 bağlama sabitleri: kapak cıvata birleşimi --------------------------
# Katı motordaki SOLID_CLOSURE_JOINT_DEFAULTS ile aynı sözleşme: bunlar
# HESAP DEĞİL, kullanıcı girdisi verilmediğinde kullanılan beyanlı
# değerlerdir. Cıvata SAYISI'nın varsayılanı YOKTUR — sayı verilmezse
# birleşim boyutlandırılmaz (uydurma cıvata sayısı yasak).
#
# ÖH D18 (kalem P15B2-09) — SÖZLEŞME ARTIK BURADA YAZILI DEĞİL, İTHAL.
# Aynı dört alan üç motor dosyasında üç kez yazılıydı ve eşitliği sınayan
# bekçi yoktu (ölçüm: docs/scofield/raw/OH/D18/hibrit/a1/once.json,
# P15B2_09 — kopya sayısı 3, ortak alan 3, bugün ayrışan 0). Tek tanım
# noktası birleşimi ÇÖZEN modüldedir (hrma/analysis/bolted_joint.py), yani
# değerleri kullanan yerle aynı yerde; motor dosyaları birbirini import
# etmez (mevcut doktrin), ortak çözümleyiciyi ise zaten import ediyorlar.
from hrma.analysis.bolted_joint import (  # noqa: E402
    CLOSURE_JOINT_DEFAULTS as _BOLTED_JOINT_CLOSURE_DEFAULTS,
    CLOSURE_JOINT_MEMBER_MATERIAL_DEFAULT as _BOLTED_JOINT_MEMBER_MATERIAL,
)

CLOSURE_JOINT_DEFAULTS = dict(
    _BOLTED_JOINT_CLOSURE_DEFAULTS,
    # Üye malzemesi: hibritte henüz kullanıcı kanalı yok, beyanlı varsayılan
    # tek kaynaktan gelir (katı motor bunu bilerek kullanmaz — bkz. modül
    # notu ve D15/P2B2-12).
    member_material=_BOLTED_JOINT_MEMBER_MATERIAL,
)

# --- Yarı-1B lüle akışı bağlaması (hrma.flow) ------------------------------
# İstasyon dizisi yanıt boyutu tavanı (port_history/blowdown deseni).
NOZZLE_FLOW_MAX_POINTS = 120

# --- Chug atalet kapıları (F2b hibrit ayağı, parti 28 ikizi) ---------------
# Anahtar adları hibritin YAYIMLANMIŞ adlarıdır (feed_water_hammer bloğunun
# required_inputs listesi bu adları 2026-08-05'ten beri duyuruyor):
# feed_line_length_m + feed_line_inner_diameter_mm. Sıvı motorun aynı kanalı
# feed_line_diameter_mm adını taşır — AD AYRIŞMASI bilinçli olarak korunur
# (yayımlanmış sözleşme kırılmaz; birleştirme ayrı bir karar, bkz. defter).
# Bantlar sıvıdaki _override_val çağrılarıyla BİREBİR aynıdır
# (liquid_rocket_engine._feed_line_inertance_inputs: 0,05-50 m; 0,5-500 mm);
# çapraz eşitlik bekçisi tests/test_stability_hibrit_chug.py içindedir.
FEED_LINE_LENGTH_RANGE_M = (0.05, 50.0)
FEED_LINE_INNER_DIAMETER_RANGE_MM = (0.5, 500.0)


# ---------------------------------------------------------------------------
# TASARIM ÖZETİ DURUM SÖZLÜĞÜ (Faz 4B, bulgu B1/B2/A3)
#
# Aynı sözlük üç motor dosyasında da BİREBİR tanımlıdır (hybrid / liquid /
# solid). Çapraz import bilinçli olarak YAPILMAZ: katı ve sıvı motor, hibridin
# Cantera'ya kadar uzanan import zincirini çekmek zorunda kalmamalıdır. Üç
# dosyadaki değerlerin aynı kaldığı makinece denetlenir:
#   tests/test_faz4_motor_kapilari.py::test_durum_sozlugu_uc_motorda_ayni
#
# Kötüden iyiye sıra — aynı koşuda birden çok durum geçerliyse EN KÖTÜSÜ yazılır:
#   NOT_CONVERGED > UNVALIDATED_ESTIMATE > TARGET_NOT_MET
#   > ESTIMATED_WITH_DEFAULTS > CALCULATED > OPTIMIZED
#
# Anlamlar:
#   OPTIMIZED               gerçek bir eniyileme çağrıldı ve BAŞARIYLA döndü
#   CALCULATED              kullanıcı girdisinden deterministik çözüm; eniyileme
#                           çalışmadı ama uydurulan girdi de yok
#   ESTIMATED_WITH_DEFAULTS kritik bir girdi verilmedi, yerleşik varsayılanla
#                           dolduruldu (bkz. _defaults_used)
#   TARGET_NOT_MET          çözüm yakınsadı ama istenen tasarım hedefi
#                           (ör. yanma süresi) tutturulamadı
#   UNVALIDATED_ESTIMATE    bu girdi çifti için fizik modellenmiyor; sayılar
#                           yer tutucudur, mühendislik değeri yoktur
#   NOT_CONVERGED           sayısal çözüm yakınsamadı; sonuç kullanılamaz
#
# ÖLÇÜM (2 Ağustos 2026, HEAD a7ff1e7) — sözlüğün var oluş sebebi: hibrit motor
# itki/süre verilmeden koşturulduğunda _defaults_used listesi
# ['nozzle_material', 'thrust', 'burn_time'] doluyor, buna rağmen
# design_summary.status koşulsuz 'OPTIMIZED' yazıyordu ve liste sonuç
# JSON'unda HİÇ görünmüyordu (14 append, 0 okuma, 0 yayım).
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


def _worst_design_status(*statuses):
    """Verilen durumların EN KÖTÜSÜNÜ döndürür.

    Bilinmeyen bir etiket gelirse en kötü kabul edilir: sözlüğe yeni bir durum
    eklenip sıralamaya yazılmadığında sonuç iyimser tarafa kayamaz.
    """
    en_kotu = DESIGN_STATUS_OPTIMIZED
    bilinmeyen = len(DESIGN_STATUS_SEVERITY)
    for durum in statuses:
        if durum is None:
            continue
        if (DESIGN_STATUS_SEVERITY.get(durum, bilinmeyen)
                > DESIGN_STATUS_SEVERITY.get(en_kotu, bilinmeyen)):
            en_kotu = durum
    return en_kotu


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: dile bağlı sabit metin YERİNE yapısal kayıt.

    Sözleşme solid_rocket_engine.py::_w ile BİREBİR aynıdır:
    ``{"code", "params", "severity"}``, severity ∈ {critical, warning, info}.
    Kod adlandırması: ``warn.hybrid.<slug>``.

    v2.6.2 GEREKÇE (Codex denetim bulgusu): hibrit motorda kullanıcıya uyarı
    ULAŞTIRAN KANAL YOKTU — her uyarı ``warnings.warn`` ile sunucu konsoluna
    gidiyordu. Enjektör modülü çöküp basit Bernoulli hesabına düşse bile
    kullanıcı bunu göremiyordu. Artık tüm uyarılar sonuç sözlüğündeki
    ``warnings`` listesine de konur (katı/sıvı motorlarla aynı sözleşme).

    ÖH D32 fix-35d: parametreler JSON'un KENDİ tipleriyle yayımlanır
    (:func:`hrma.engines.warning_records.json_native_params`). Demet JSON'da
    yoktur; gövde gidiş-dönüşte liste olarak geri geldiği için yayımlanan
    kayıt ile istemcinin okuduğu kayıt AYNI NESNE DEĞİLDİ (ölçüldü,
    ``docs/scofield/raw/OH/D32/fix35/d/hibrit_once.json``). Sayı, alan adı
    ve alan sayısı DEĞİŞMEZ — yalnız kap tipi indirgenir.
    """
    return {"code": code, "params": _json_yerli_params(params),
            "severity": severity}


def tank_pressure_not_used_warning(tank_pressure_bar, injector_design_block):
    """İstekteki ``tank_pressure`` kullanılan besleme basıncından sapıyorsa uyarı.

    ÖH D37 A2 hibrit · 7. tur YB-04 (ana model kararı, karar dosyası §28-25;
    Astra danışması 4). ÖLÇÜLDÜ (rapor YB-04): kendinden basınçlı N₂O
    kipinde enjektör devresi P₁ = P_sat(T_tank) alır; isteğin
    ``tank_pressure`` alanı devreye GİRMEZ (50 → 80 bar: devre, plaka, ΔP,
    chug bit-aynı). Kullanıcı 80 bar senaryosunu hesapladığını sanmasın diye
    değer P_sat'tan ``TANK_PRESSURE_PSAT_REL_TOL``dan fazla saparsa adlı
    uyarı (``warn.hybrid.tank_pressure_not_used``) döner; istek REDDEDİLMEZ
    (kayıtlı projeler ve form alanı gönderiyor; geriye uyum). Beyan
    ``injector_design.feed_pressure_basis`` yerinde kalır.

    Yalnız ``feed_pressure_source`` ``FEED_PRESSURE_SOURCE_N2O_SAT`` iken
    ölçülür: o kipte fiziksel tank basıncı doyma basıncıdır ve kıyas
    anlamlıdır. Değer sonlu pozitif sayı değilse, blok yoksa ya da başka
    kipteyse ``None`` döner — uyarı uydurulmaz. Uyarıyı /calculate yanıtının
    motor uyarı kanalına uç katmanı ekler (motor bu alanı almaz).
    """
    if not isinstance(injector_design_block, dict) or (
            injector_design_block.get('feed_pressure_source')
            != FEED_PRESSURE_SOURCE_N2O_SAT):
        return None
    try:
        p_tank = float(tank_pressure_bar)
        p_sat = float(injector_design_block.get('feed_pressure_bar'))
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(p_tank) and np.isfinite(p_sat)
            and p_tank > 0.0 and p_sat > 0.0):
        return None
    sapma = (p_tank - p_sat) / p_sat
    if abs(sapma) <= TANK_PRESSURE_PSAT_REL_TOL:
        return None
    return _w('warn.hybrid.tank_pressure_not_used', 'warning',
              tank_pressure_bar=round(p_tank, 3),
              feed_pressure_bar=round(p_sat, 3),
              deviation_pct=round(sapma * 100.0, 1),
              tol_pct=int(round(TANK_PRESSURE_PSAT_REL_TOL * 100)))


# Uyarı kaydının TEKİLLİK anahtarı — TANIM BURADA DEĞİL (ÖH D30/OH-Z3-04).
# Eski docstring "sözleşme solid_rocket_engine.py::_warning_identity ile
# BİREBİR aynıdır (iki motor dosyası birbirini ithal etmez)" diyordu; iki
# kopyanın eşitliği yorumla korunuyordu, kodla değil. İki motor da artık
# tek tanım noktasını (``hrma.engines.warning_records``) ithal eder — o
# modül hiçbir motoru ithal etmediği için döngüsel bağımlılık doğmaz.
from hrma.engines.warning_records import (  # noqa: E402
    json_native_params as _json_yerli_params,
    warning_identity as _warning_identity)


def _critical_thermal_verdicts(*blocks):
    """Termal blokların ürettiği ``severity: critical`` hükümlerin listesi.

    NEDEN VAR (ÖH P16S1-07): motor katmanı ``severity: critical`` termal
    hükümler üretiyor, iki dile de çevrilmiş durumdalar, ama hiçbiri
    kullanıcıya ULAŞMIYORDU. Ölçüldü (5 kN hibrit, VARSAYILAN girdiler):
    ``heat_transfer_analysis`` içinde ``warn.thermal.wall_exceeds_melting``
    (T_wall 3283 K ⟷ steel_4130 erime 1705 K) ve
    ``warn.thermal.wall_pinned_adiabatic`` kritikleri duruyor; alüminyum lüle
    seçilirse buna ``warn.hybrid.nozzle_material_over_temp`` ekleniyor. Üst
    düzey ``warnings`` listesinde ise SIFIR kritik vardı — ekran katmanı
    (``app.js`` ``displayWarnings``) yalnız o listeyi okur.

    İşlev hükmü ÜRETMEZ, YENİDEN YAZMAZ, ÖZETLEMEZ: bloklardan gelen kaydın
    ta kendisini (kod + parametre + ciddiyet) taşır. Kapsam bilinçli olarak
    ``critical`` ile sınırlıdır; daha düşük ciddiyetteki termal notlar kendi
    bloklarında kalır (tüketicileri ilgili panellerdir).
    """
    found, seen = [], set()

    def _gez(node, depth=0):
        if depth > 3 or not isinstance(node, dict):
            return
        for record in (node.get('warnings') or []):
            if isinstance(record, dict):
                critical = str(record.get('severity', '')).lower() == 'critical'
            elif isinstance(record, str):
                critical = record.strip().upper().startswith('CRITICAL')
            else:
                continue
            if not critical:
                continue
            key = _warning_identity(record)
            if key in seen:
                continue
            seen.add(key)
            found.append(record)
        for value in node.values():
            if isinstance(value, dict):
                _gez(value, depth + 1)

    for block in blocks:
        _gez(block)
    return found


# Regresyon katsayısı tablosunun (hrma/data/propellant_database.py ->
# HYBRID_REGRESSION_COEFFICIENTS) her satırının HANGİ OKSİTLEYİCİ ile
# ölçüldüğü. Sayısal değil, kaynak/kapsam meta verisidir; o dosyadaki atıf
# yorumlarından birebir okunur:
#   htpb    -> N2O  (Doran et al., AIAA 2007-5352)
#   abs     -> N2O  (Whitmore & Peterson, JPP 29(3) 2013)
#   paraffin-> GOX  (Karabeyoglu et al., JPP 20(6) 2004 SP-1a;
#                    Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2)
#   pe      -> O2   (HDPE/O2, Zilliac & Karabeyoglu Tablo 2)
#   pmma    -> O2   (Greiner & Frederick verisi, aynı tablo)
# v2.6.2 fizik denetimi bulgusu F020: kod bugüne dek oksitleyiciyi HİÇ
# kullanmıyordu; N2O katsayılarını LOX/GOX motorlarına sessizce uyguluyordu.
# Hibrit regresyon oksitleyiciye kuvvetle bağlıdır (alev sıcaklığı, blowing
# parametresi ve radyasyon payı farklıdır; HTPB/GOX ile HTPB/N2O arasında a
# tipik olarak 2 kata varan fark gösterir) — Sutton & Biblarz 9. baskı Böl. 16;
# Chiaverini & Kuo, AIAA Progress Vol. 218 (2007).
REGRESSION_COEFF_OXIDIZER_BASIS = {
    'htpb': 'n2o',
    'abs': 'n2o',
    'paraffin': 'gox',
    'pe': 'o2',
    'pmma': 'o2',
}

# Aynı tabloda "yayınlanmış, hakemli bir korelasyon bulunamadı" notuyla
# DOĞRULANMAMIŞ olarak korunan yakıtlar. Tasarım için kullanılmamalıdır;
# kullanıcı bunu görmeliydi ama hiçbir yerde söylenmiyordu (F020 eki).
UNVALIDATED_REGRESSION_FUELS = ('pla', 'carbon', 'aluminum', 'al2o3')

# HTPB katsayısının doğrulama veritabanına karşı ÖLÇÜLEN sapması (F019).
# n=0.555 sabit tutulup DB'nin HTPB kayıtlarına (n=43 test, carmicino2013 ve
# rezaei2018 kampanyaları) en iyi a arandığında a=6.24e-5 çıkıyor; koddaki
# 3.68e-5 değerinin 1.70 KATI. Bu, koddaki modelin HTPB regresyonunu
# sistematik olarak DÜŞÜK tahmin ettiği anlamına gelir (bias −%39.5,
# medAPE %46.6) — ve bu GÜVENLİ OLMAYAN yöndür: yakıt debisi düşük, O/F
# yüksek tahmin edilir, grain ~%25 fazla uzun boyutlandırılır ve web
# gerçekte tahminden ~%25 ERKEN tükenir.
# Katsayı DEĞİŞTİRİLMEDİ (birincil kaynak Doran et al. AIAA 2007-5352'nin
# tam metni doğrulanamadı; "asla uydurma" ilkesi gereği ölçülen sapma
# uyarı olarak bildirilir, sessizce yeni bir sayı uydurulmaz).
HTPB_COEFF_DB_BIAS_PCT = -39.5
HTPB_COEFF_DB_MEDAPE_PCT = 46.6

# ---------------------------------------------------------------------------
# ÖH D31 / OH-B1-05 — TEK YANLILIK SAYISI TEK BAŞINA YAYIMLANMAZ
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (D31 hibrit a1 ``once.json`` K3): uyarı yalnız iki alan taşıyordu
# (``bias_pct=-39,5``, ``medape_pct=46,6``) ve bu tek sayı, BAĞIMSIZ ölçümün
# kampanya gövdesinin DIŞINDA duruyordu — en hafif kampanya −%41,8, yani
# 2,3 puanlık uzlaştırılmamış bir fark. Kullanıcı tek bir sayı görüyor ve
# onu kesinmiş sanıyordu: kazanılmamış bir kesinlik iddiası.
#
# Onarım katsayıya DOKUNMAZ (o bir fizik/veri kararıdır ve kaynak eşleşmesi
# yoktur; aşağıdaki nota bak). Onarım, kazanılmamış kesinlik iddiasını
# KALDIRIR: ürün kendi 43 kayıtlı ölçümünü yayımlarken bağımsız ölçümün ÜÇ
# HTPB/N₂O kampanyasını da ADIYLA ve uzlaşmadığını SÖYLEYEREK yayımlar.
#
# KAYNAK: docs/arastirma/fizik/A3-hibrit-regresyon.md (2026-08-22),
#   :187-192 kampanya bazında HRMA yanlılığı,
#   :288-293 46 noktalı havuz (üç kampanya, saf HTPB, anomali bayraklı ve
#            metal/karbon yüklü grainler hariç).
# Sayılar o dosyadan BİREBİR alındı; burada yeni bir fit yapılmadı.
#
# ASTRA UYARISI (14 Eylül 2026) — BU SAYILAR KATSAYIYI DEĞİŞTİRMEZ:
# A3'ün aynı tablosundaki Zilliac & Karabeyoglu 2006 Tablo 2 satırları
# OKSİJEN (GOX/LOX) deneyleridir; HTPB/N₂O katsayısını (Doran et al., AIAA
# 2007-5352) tek başına ÇÜRÜTEMEZ. Oksitleyici eşleşmediği için o satırlar
# bu beyanda KULLANILMAZ ve hiçbir yerde "doğrulandı" denmez. Yayımlanan üç
# kampanyanın üçü de HTPB/N₂O'dur.
#: Bağımsız (ürün kodundan bağımsız) HTPB/N₂O kampanyaları — A3:187-192.
HTPB_INDEPENDENT_CAMPAIGNS = (
    {'campaign': 'Rezaei 2018', 'oxidizer': 'n2o', 'points': 29,
     'bias_pct': -50.6, 'medape_pct': 50.9},
    {'campaign': 'Carmicino 2013', 'oxidizer': 'n2o', 'points': 16,
     'bias_pct': -41.8, 'medape_pct': 43.5},
    {'campaign': 'Heydari 2017', 'oxidizer': 'n2o', 'points': 1,
     'bias_pct': -50.3, 'medape_pct': None},
)
#: Üç kampanyanın GÖVDESİ (en hafif ... en ağır) — A3:187-192.
HTPB_INDEPENDENT_CAMPAIGN_BIAS_BAND_PCT = (-50.6, -41.8)
#: 46 noktalı birleşik havuz — A3:288-293.
HTPB_INDEPENDENT_POOL_POINTS = 46
HTPB_INDEPENDENT_POOL_BIAS_PCT = -47.6
HTPB_INDEPENDENT_POOL_MEDAPE_PCT = 49.4
#: Ürünün KENDİ ölçümünün havuzu (F019; carmicino2013 + rezaei2018 kayıtları).
HTPB_OWN_POOL_POINTS = 43
#: Yayımlanan yanlılık gövdesinin OKSİTLEYİCİ ZARFI — elle yazılmaz,
#: kampanya kayıtlarından TÜRETİLİR (doktrin 4). Kampanya listesine başka
#: oksitleyicili bir satır eklenirse zarf kendiliğinde büyür.
#:
#: ÖH D32 / OH-B1-05 — ASTRA KAYNAK EŞLEŞMESİ ŞARTININ ÜRÜN AYAĞI.
#: ÖLÇÜLDÜ (D32 hibrit a1 ``once.json`` C, taban ``dd1dcddc``): uyarı
#: ``oxidizer_type`` ne olursa olsun AYNI gövdeyle ateşleniyordu —
#:     n2o  -> bias_var=True   (kampanyalar n2o, EŞLEŞİYOR)
#:     lox  -> bias_var=True   (kampanyalar n2o, EŞLEŞMİYOR)
#:     h2o2 -> bias_var=True   (kampanyalar n2o, EŞLEŞMİYOR)
#: Yani N₂O ile ÖLÇÜLMÜŞ bir yanlılık bandı, LOX/H₂O₂ koşusunda da o koşuya
#: aitmiş gibi yayımlanıyordu. Yukarıdaki ASTRA UYARISI bunu ZATEN yasaklıyor
#: ("oksitleyici eşleşmediği için ... KULLANILMAZ"), fakat kural yalnız
#: yorumda duruyordu, kodda kapısı yoktu. Katsayıya DOKUNULMAZ ve bant
#: DEĞİŞMEZ; eklenen tek şey, bandın hangi zarfta ölçüldüğünün ve bu koşunun
#: o zarfın İÇİNDE olup olmadığının makine-okur SÖYLENMESİDİR.
HTPB_INDEPENDENT_CAMPAIGN_OXIDIZERS = tuple(sorted(
    {k['oxidizer'] for k in HTPB_INDEPENDENT_CAMPAIGNS}))
#: İki ölçümün neden birebir eşit BEKLENMEDİĞİ — ölçülmüş iki aday, ikisi de
#: uzlaştırılmadı (bu yüzden ``reconciled: False`` yayımlanır).
#:
#: ÖH D33-3 / OH-D33-46 — GEREKÇELER ARTIK NESİR DEĞİL, KAYIT.
#: ÖLÇÜLDÜ (bu depo, 16 Eylül 2026; varsayılan hibrit koşusu, node içinde
#: ürünün KENDİ ``warnToText``i): bu iki gerekçe Türkçe uyarı panelinde
#: İngilizce basılıyordu —
#:     "... ölçülen gerekçeler: record pools differ (43 own vs 46
#:      independent points) · the product path runs a G_ox-fitted
#:      coefficient under a G_total flux closure, which lifts the predicted
#:      regression by +10-18% (propellant_database.py header)."
#: — ve bu hâliyle Türkçe kullanma kılavuzunun uyarı paneli ekran karesine
#: (``docs/user_guide/img/tr-07-warnings.png``) girdi. Kök, kanalın değil
#: KABIN kusuruydu: gerekçeler Python tarafında İNGİLİZCE CÜMLE olarak
#: üretiliyordu, oysa bu deponun ``warn.*`` kanonu "sayı ve olgu Python'dan,
#: DİL JS'ten" der. Artık her gerekçe ``{code, params, severity}`` kaydıdır;
#: ``app.js::warnToText`` / ``analysis_dock.js::warnText`` iç içe kayıtları
#: ZATEN özyinelemeli çeviriyordu (kanal vardı, kap yanlıştı).
#:
#: SAYI DEĞİŞMEDİ: 43 ⟷ 46 havuz farkı ve +%10-18 yükseltme bandı aynı
#: sayılardır; yalnız nesrin içinden çıkıp ada kavuştular (band artık
#: ``propellant_database.HYBRID_GOX_FIT_UNDER_GTOTAL_LIFT_PCT``ten okunur).
HTPB_BIAS_UNRECONCILED_REASONS = (
    {'code': 'warn.hybrid.htpb_bias_unreconciled_pools',
     'severity': 'info',
     'params': {'own_pool_points': HTPB_OWN_POOL_POINTS,
                'independent_pool_points': HTPB_INDEPENDENT_POOL_POINTS}},
    {'code': 'warn.hybrid.htpb_bias_unreconciled_flux_closure',
     'severity': 'info',
     'params': {'lift_low_pct': HYBRID_GOX_FIT_UNDER_GTOTAL_LIFT_PCT[0],
                'lift_high_pct': HYBRID_GOX_FIT_UNDER_GTOTAL_LIFT_PCT[1],
                'source': 'propellant_database.py'}},
)

#: ÖH D33-3 / OH-D33-46 — KAMPANYA SATIRLARI EKRANDA HAM JSON'DU.
#: ÖLÇÜLDÜ (aynı koşu): ``independent_campaigns`` ekrana
#: ``{"campaign":"Rezaei 2018","oxidizer":"n2o","points":29,...}`` diye
#: basılıyordu — hem TR hem EN arayüzde. Sebep mekanik: ``warnToText``
#: ``code`` TAŞIMAYAN bir sözlüğü ``JSON.stringify`` ile yazıya döküyor.
#: Kayıtlar artık kodlarını taşıyor, yani okunur bir cümleye çevriliyorlar.
#:
#: DÜZ ALANLAR YERİNDE KALIR: ``campaign`` / ``oxidizer`` / ``points`` /
#: ``bias_pct`` / ``medape_pct`` makine tüketicilerinin (PDF eki, ``app.py``
#: JSON yükü, ``tests/test_d31_hibrit_a1.py``) okuduğu sözleşmedir ve
#: DEĞİŞMEZ; eklenen tek şey aynı satırın ÇEVRİLEBİLİR kabıdır. ``params``
#: aynı beş alanın kopyası değil, aynı sözlükten TÜRETİLİR — iki yerde iki
#: ayrı sayı tutulmaz.
#:
#: ``medape_pct`` yayımlamayan kampanya (Heydari 2017, tek nokta) AYRI bir
#: kod alır: "medyan mutlak hata %None" basmaktansa "bildirilmedi" demek
#: fail-closed davranıştır ve o alan params'a hiç konmaz.
HTPB_CAMPAIGN_ENTRY_CODE = 'warn.hybrid.htpb_campaign_entry'
HTPB_CAMPAIGN_ENTRY_CODE_NO_MEDAPE = 'warn.hybrid.htpb_campaign_entry_no_medape'


def _htpb_kampanya_kaydi(kampanya):
    """Kampanya satırını HEM makine alanlarıyla HEM çeviri kaydıyla verir."""
    params = {ad: deger for ad, deger in kampanya.items() if deger is not None}
    kod = (HTPB_CAMPAIGN_ENTRY_CODE if kampanya.get('medape_pct') is not None
           else HTPB_CAMPAIGN_ENTRY_CODE_NO_MEDAPE)
    return dict(kampanya, code=kod, severity='info', params=params)


#: Yayımlanan kampanya gövdesi — TÜRETİLİR, elle yazılmaz (doktrin 4).
HTPB_INDEPENDENT_CAMPAIGN_RECORDS = tuple(
    _htpb_kampanya_kaydi(k) for k in HTPB_INDEPENDENT_CAMPAIGNS)

#: Uyarı yükündeki İKİLİ (bool) alanların arayüzdeki SÖZCÜK karşılıkları.
#:
#: ÖH D33-3 / OH-D33-46. ÖLÇÜLDÜ: Türkçe panelde "uzlaştırıldı mı: false" ve
#: "zarf eşleşmesi: true" yazıyordu — ham JSON ikilisi, iki dilde de
#: kullanıcıya basılamaz. Çeviri ``i18n_common.js``teki ``I18N.tf``
#: sarmalayıcısında yapılır (dil JS'in işidir), fakat HANGİ anahtarların
#: kullanılacağı burada yazılıdır: ikili alanı YAYIMLAYAN taraf burasıdır ve
#: ``tests/test_i18n_common.py`` kullanım taraması sözlük dosyalarının
#: DIŞINI tarar — anahtar yalnız sözlükte kalsaydı "ölü çeviri" sayılırdı.
#: Bekçisi: ``tests/test_d33_htpb_beyani.py``.
#:
#: Bu modülün üç uyarısı ikili alan yayımlar: ``htpb_coeff_bias``
#: (``reconciled``, ``campaign_scope_match``), ``cooling_channels_assumed``
#: (``geometry_modelled``), ``regression_coeff_borrowed``
#: (``independent_fit``).
WARNING_BOOL_I18N_KEYS = {True: 'common.bool.true', False: 'common.bool.false'}

# Port çapının kamara iç çapına oranı için üst sınır. Yakıt grain'i portu
# SARDIĞINDAN port her zaman kamaradan küçüktür; kalan et kalınlığı
# (D_ch − D_port)/2 yapısal ve yanma açısından gereklidir. Web tükenmesi bu
# orana ulaşınca ilan edilir. TEK TANIM YERİ (CLAUDE.md kural 11): hem
# time-marching sınırı hem de girdi doğrulaması bu sabiti kullanır.
PORT_TO_CHAMBER_MAX_RATIO = 0.8

#: FIRLATMA SAHASI GİRDİ BANTLARI (D15/P1B2-06). TEK TANIM YERİ
#: (CLAUDE.md kural 11): ``_launch_site_block`` kapısı yalnız buradan okur.
#:
#: Rakım [m]: bir fırlatma sahası Dünya'nın KATI YÜZEYİNDE durur. Alt uç
#: kara üzerindeki en alçak nokta olan Lut Gölü kıyısıdır (≈ −430 m,
#: yuvarlanarak −500 m); üst uç en yüksek zirvenin (8849 m) üstüdür.
#: Bandın dışı bir saha değil, bir girdi hatasıdır: ölçüldü (a3/once.json
#: B2_06) −100 km rakım ortam basıncını 50,1 MPa'ya çıkarıp itkiyi
#: −175 193,63 N yapıyordu.
#: ÖH D19 / P4B3-18 — TEK KAYNAK: aynı bant artık saha fiziğinin sahibi
#: olan ``hrma.analysis.launch_site``ta tanımlıdır ve ``resolve_launch_site``
#: kullanıcının verdiği ``elevation_m``i o bantla reddeder. Burada yalnız
#: içe aktarılır; iki tanım tutulmaz.
from hrma.analysis.launch_site import (  # noqa: E402
    SITE_ELEVATION_RANGE_M as LAUNCH_SITE_ELEVATION_RANGE_M,
)

#: Saha yüzey sıcaklığı [K]: WMO'nun tanıdığı Dünya yüzey hava sıcaklığı
#: uçları — Vostok −89,2 °C = 183,95 K ve Furnace Creek 56,7 °C = 329,85 K
#: — tam dereceye genişletilmiştir. Negatif mutlak sıcaklık (ölçülen:
#: temperature_k = −300 aynen yayımlanıyordu) fizikte yoktur.
LAUNCH_SITE_TEMPERATURE_RANGE_K = (180.0, 340.0)

# Tasarım noktasında grain BOYU ile regresyon hızı arasındaki sabit-nokta
# iterasyonunun durdurma ölçütleri (v2.6.2 fizik denetimi, bulgu F133).
# TEK TANIM YERİ (CLAUDE.md kural 11). Bağıl tolerans, iç (r_dot) çözücünün
# 1e-6 bağıl toleransından belirgin biçimde gevşek TUTULMAZ ama onun sayısal
# gürültüsünün altına da inilmez: 1e-8, iki mertebe altında kalıp iç çözücünün
# adım-sayısı sıçramalarından etkilenmeyecek güvenli aralıktır.
GRAIN_LENGTH_FIXED_POINT_TOL = 1e-8
GRAIN_LENGTH_FIXED_POINT_MAX_ITER = 60


#: Arayüzdeki "Include Cooling Channels" seçeneklerinin ısı transferi
#: modelindeki soğutma tipine eşlemesi (v2.6.25).
#:
#: HeatTransferAnalyzer._coolant_side_coefficient üç sınıf tanır ve her birine
#: bir soğutucu-tarafı film katsayısı verir: doğal taşınım 25, zorlanmış hava
#: 100, sıvı rejeneratif 20 000 W/(m²·K) (Huzel & Huang Böl. 4). Arayüz ise
#: kanal GEOMETRİSİ soruyor (radyal / sarmal). Her iki geometri de cidara
#: sıvı soğutucu dolaştırır, yani ikisi de rejeneratif sınıfa girer;
#: aralarındaki fark bu modelin çözünürlüğünün altındadır (kanal en-boy oranı,
#: hız ve basınç düşüşü girdi olarak alınmıyor).
#:
#: Bu yüzden kanal seçildiğinde ayrıca warn.hybrid.cooling_channels_assumed
#: uyarısı verilir: film katsayısı literatür aralığından ALINMIŞTIR, soğutucu
#: debisi ve kaynama marjı DOĞRULANMAMIŞTIR.
COOLING_CHANNEL_TO_TYPE = {
    'none': 'natural',
    'radial': 'regenerative',
    'spiral': 'regenerative',
    # Doğrudan ısı-transferi terimleri de kabul edilir (API çağrıları)
    'natural': 'natural',
    'forced': 'forced',
    'regenerative': 'regenerative',
}

# ---------------------------------------------------------------------------
# ÖH D31 / OH-D26-04 — KANAL GEOMETRİSİ MODELLENMİYOR, BU ADIYLA SÖYLENİR
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (D26 sivi a1, ``radial_spiral.json``; D31 hibrit a1 ``once.json`` K1):
# ``cooling_channels='radial'`` ile ``'spiral'`` gönderen iki koşu motorun
# 8.337 ortak yaprağının 8.335'inde BİREBİR aynı; ayrışan 2 yaprak yalnızca
# uyarının kullanıcı kelimesini geri okuduğu ``params.geometry`` alanıdır
# (``/calculate`` gövdesinde aynı echo 6 yaprak eder — openrocket/trajectory
# kopyalarıyla). FİZİK yaprağı farkı: 0.
#
# Kök sebep ürünün kendi çözünürlüğüdür, bir kaçak değil:
# ``HeatTransferAnalyzer._coolant_side_coefficient`` SINIF düzeyinde çalışır
# (doğal / zorlanmış / rejeneratif film katsayısı), menü ise GEOMETRİ düzeyinde
# seçenek sunar. Radyal ile sarmal kanalı ayıran fizik (eğrilik kaynaklı Dean
# girdapları; Manlapaz & Churchill 1980, Schmidt 1967 sarmal boru Nusselt
# düzeltmesi) sarmal çapı, hidrolik çap, soğutucu hızı ve debisini GİRDİ olarak
# ister — bu dördü üründe hiçbir uçta toplanmıyor. Girdisi olmayan bir düzeltme
# katsayısı üretmek sayı uydurmak olurdu (doktrin 1/6), o yüzden yapılmadı:
# fark MODELLENMİYOR ve yanıt bunu makine-okur biçimde SÖYLÜYOR.
#
# NOT (kaynak eşleşmesi): Zilliac & Karabeyoglu tarzı kanal-geometrisi
# korelasyonları bu ürünün sınıf modeline bağlanamaz; eşleşmeyen kaynakla
# "doğrulandı" denmesi yasaktır.
#
# Aşağıdaki iki yapı ELLE YAZILMAZ, eşlemeden TÜRETİLİR (doktrin 4): menüye
# yeni bir geometri eklenip aynı sınıfa düşerse beyan kendiliğinden büyür.

#: Menüde GEOMETRİ olarak sunulan seçimler (adı ısı-transferi sınıfının
#: kendisi olmayan anahtarlar).
COOLING_CHANNEL_GEOMETRY_SELECTIONS = tuple(
    sorted(k for k, v in COOLING_CHANNEL_TO_TYPE.items() if k != v))

#: Isı-transferi sınıfı -> o sınıfa düşen geometri seçimleri. Bir sınıfta
#: birden çok seçim varsa o seçimler BİRBİRİNDEN AYIRT EDİLMİYOR demektir.
COOLING_GEOMETRY_EQUIVALENCE = {
    sinif: tuple(sorted(k for k in COOLING_CHANNEL_GEOMETRY_SELECTIONS
                        if COOLING_CHANNEL_TO_TYPE[k] == sinif))
    for sinif in sorted(set(COOLING_CHANNEL_TO_TYPE.values()))
}
COOLING_GEOMETRY_EQUIVALENCE = {
    k: v for k, v in COOLING_GEOMETRY_EQUIVALENCE.items() if v}

#: Geometri farkının modellenmesi için ürünün TOPLAMADIĞI girdiler.
COOLING_GEOMETRY_MISSING_INPUTS = (
    'coil_diameter', 'channel_hydraulic_diameter', 'coolant_velocity',
    'coolant_mass_flow')

#: Cidar kalınlığı için kabul edilen aralık [m]. Arayüz mm gönderir; dönüşüm
#: app.py'de yapılır. 0.5 mm altı imal edilemez, 100 mm üstü bu sınıf motorda
#: girdi hatasıdır (birim karışıklığının işareti).
# Kullanıcının GİRDİĞİ cidar kalınlığı için kabul alt sınırı [m].
# Sıvı motordaki WALL_THICKNESS_MANUFACTURING_MIN_M ile KARIŞTIRILMAMALI:
# o, hesaplanan kalınlığın altına inemeyeceği İMALAT tabanıdır (2 mm);
# bu ise kullanıcının elle girebileceği en ince değerdir (0.5 mm).
# İkisi farklı kavram olduğu için ayrı adlandırıldı (aynı ad iki
# dosyada iki farklı anlamda kullanılıyordu).
WALL_THICKNESS_INPUT_MIN_M = 0.0005
WALL_THICKNESS_MAX_M = 0.100

#: Kamara cidarı sabit-nokta boyutlandırması (bebek-Scofield F5-1).
#: Kullanıcı cidar VERMEDİĞİNDE cidarın tek kaynağı yapısal boyutlandırmadır
#: ve ısı zinciri onu TÜKETİR: ısı(t) -> cidar sıcaklıkları -> dayanım
#: derating'i -> boyutlandırılan t. İki zincir bit-eşitliğe (ya da aşağıdaki
#: bağıl kalıntıya) oturana kadar yinelenir. ÖLÇÜLDÜ (örnek 3 kN N2O/HTPB
#: motoru): 2. adımda bit-eşit yakınsıyor (doğal soğutmada cidar adyabatik
#: sıcaklığa kenetlendiği için derating doyuyor). Tavan, doyumsuz
#: (rejeneratif) durumlar için paylıdır; adım maliyeti ölçüldü ~22 ms.
WALL_SIZING_MAX_ITERS = 8
#: Bit-eşitlik yakalanamazsa kabul edilen bağıl kalıntı; üstünde kalırsa
#: warn.hybrid.wall_sizing_not_converged uyarısı verilir ve kalıntı
#: chamber_wall_policy bloğunda BEYAN edilir (sessiz kabul yok).
WALL_SIZING_REL_TOL = 1e-6

#: Boğaz debi katsayısı C_D — TEK SÖZLEŞME (bebek-Scofield F3-1): debiyi
#: C_D taşır (ṁ = C_D·Pc·At/c*), boğaz alanı GEOMETRİKTİR ve boyutlandırma
#: At = ṁ·c*/(Pc·C_D) ile kurulur. Debiden Pc GERİ OKUYAN her satır aynı
#: sabiti kullanmak ZORUNDADIR: Pc = ṁ·c*/(C_D·At). Eskiden thrust_curve
#: geri okuması C_D'siz yapılıyordu ve t=0 basıncı tasarımın tam 0,98 katı
#: çıkıyordu (ölçüldü: 29,40 / 30,00 bar). 0,98 keskin kenarlı boğaz için
#: tipik değerdir (Sutton & Biblarz 9. baskı, Böl. 3).
#: NOT: hrma/analysis/transient_ballistics.py::NOZZLE_DISCHARGE_COEFFICIENT
#: aynı sözleşmenin öteki ucudur (o dosyanın sahibi bu partide ayrı ajan;
#: iki adın TEK tanıma indirilmesi ana modele bildirildi). İki sabitin
#: eşitliği bekçilidir: tests/test_scofield_hibrit.py::
#: test_cd_sozlesmesi_iki_uc_ayni_sayi — biri kayarsa test kırmızıya döner.
THROAT_DISCHARGE_COEFFICIENT = 0.98

# --- ÖH D20 / B1-12 · KAYIP KÜMESİ SABİT NOKTA YİNELEMESİ -----------------
# Manşet C_F kinetik verimi de uygular; kinetik verim boğaz çapına, boğaz
# çapı manşet C_F'e bağlı olduğu için zincir sabit noktaya yinelenir.
# Tavan cömerttir (ölçülen yakınsama 3 geçiş); yakınsamazsa FAIL-CLOSED.
HYBRID_LOSS_SIZING_MAX_PASSES = 12
# Bağıl boğaz çapı toleransı. Platform float sözleşmesi gereği gürültü
# tabanının (1e-12) üstünde, ürün anlamının (mikron altı) altında.
HYBRID_LOSS_SIZING_TOL = 1e-11

# --- ÖH D22 / OH-D21-03 · GERÇEKLEŞEN L* SABİT NOKTA YİNELEMESİ -----------
# Kinetik verim kalış süresinden, kalış süresi GERÇEKLEŞEN karakteristik
# boydan (L*_ach = V_c_actual / A_t) gelir; gerçekleşen boy ise
# boyutlandırmanın sonucudur. Zincir bu yüzden sabit noktaya yinelenir.
# Ölçülen daralma çarpanı ~1/680 (girdideki %67 fark çıktıda %0,098),
# yani birkaç geçişte kapanır; tavan yine de cömert tutulur.
HYBRID_KINETIC_LSTAR_MAX_PASSES = 12
# Bağıl L* toleransı: platform float gürültü tabanının (1e-12) üstünde,
# ürün anlamının (mikron altı kamara hacmi) altında.
HYBRID_KINETIC_LSTAR_TOL = 1e-11
# Manşet/panel C_F çapraz denetiminin bandı [%]. Kayıp kümesi D20'de
# birleştirildikten sonra GERİYE KALAN fark ölçülmüştür (en büyüğü
# -%0,4879, eps=40): bandı bunun altına çekmek yanlış "pass" üretir,
# üstüne çekmek kusuru gizler. Kalan farkın kökleri ``remaining_causes``
# alanında adıyla yazılıdır.
HYBRID_CF_CROSS_CHECK_TOL_PCT = 0.001

#: τ_c ↔ kalış süresi çaprazının HİBRİT kalıntı gerekçesi (v2.6.27 parti 31).
#: Ortak alan biçimi liquid_rocket_engine.tau_c_vs_residence_time_field'dan
#: gelir; motora ÖZGÜ olan yalnız bu cümledir.
#:
#: ÖH D37 A2 hibrit · F-09 (= OH-D31-09) — KALINTI ARTIK ÖLÇÜLÜR, İDDİA
#: EDİLMEZ. Eski metin "beklenen artık TAM OLARAK 1/C_D" diyordu; ÖLÇÜLDÜ
#: (docs/scofield/raw/OH/A2/hibrit/a1/once/ozet.json K3, taban koşusu
#: thrust 1000 N / Pc 20 bar / O/F 2,5): oran 1,028589, 1/C_D = 1,020408 —
#: geriye %0,80 kalıyordu ve o kalan sıvı motorun ZATEN adlandırdığı ikinci
#: terimdi: R·T özdeşliğinin tüketicide kırılması, (c*Γ)²/((R_u/MW)·T_c) =
#: 1,008017 (Ornek-H1'de 1,001257). İki terimin çarpımı oranı 1e-14
#: bağıl hassasiyetle yeniden üretir (``unexplained_pct`` ≈ 0); C_D terimi
#: dışarıda bırakılırsa %2,04 açıklanamaz kalır (karar tablosu raporda).
#: Sayılar METNE KOPYALANMAZ: terimler ``residual_decomposition`` alanında
#: her koşunun KENDİ sayılarından yayımlanır (``_tau_c_residual_terms``).
HYBRID_TAU_C_RESIDUAL = (
    'NOT an unexplained inconsistency: it factorises into two named terms, '
    'published in residual_decomposition. (1) The throat discharge '
    'coefficient: the hybrid chain sizes the throat with '
    f'C_D = {THROAT_DISCHARGE_COEFFICIENT:g} (mdot = C_D*Pc*A_t/c*), while '
    'the identity above assumes the ideal choked throat (C_D = 1), so the '
    'ratio carries a factor 1/C_D. (2) The R*T identity break at the '
    'CONSUMER: the residence time builds rho_gas from (R_universal/MW)*T_c '
    'of this run, whereas tau_c builds the same quantity from c* through '
    'R*T = (c*Gamma)^2; the two must agree and do not exactly. Their '
    'product reproduces the published ratio; the leftover is published as '
    'unexplained_pct, not silently absorbed.')

#: Tasarım emniyet katsayısı için kabul edilen aralık. Arayüz 2-6 sunar;
#: API daha geniş kabul eder ama 1.05 altı (fiilen emniyet payı yok) ve
#: 10 üstü (kütle cezası anlamsız) girdi hatasıdır.
SAFETY_FACTOR_MIN = 1.05
SAFETY_FACTOR_MAX = 10.0

#: Lüle (boğaz) malzemesinin soğutma varsayımı. Arayüzün KENDİ etiketi
#: "Copper (Regeneratively Cooled)" olduğu için bakır rejeneratif soğutmalı
#: kabul edilir; grafit/tungsten/C-C soğutmasız (ısı emici + ışıma) çalışır.
#: Bu bir modelleme kararı değil, arayüzün beyanının okunmasıdır.
NOZZLE_MATERIAL_COOLING = {
    'graphite': 'natural',
    'tungsten': 'natural',
    'carbon_carbon': 'natural',
    'molybdenum_tzm': 'natural',
    'niobium_c103': 'natural',
    'copper': 'regenerative',
    'cucrzr': 'regenerative',
}
#: Arayüz enjektör tipi -> ``engines/injector_design.py`` sözcüğü.
#: İki modül aynı kavram için farklı ad kullanıyor; eşleme olmadan devre
#: modeli ValueError atıyor ve motor uydurma yedeğe düşüyordu.
#:  - 'impingement': arayüz tek akışkanlı (yalnız oksitleyici) çarpışmalı
#:    enjektör sunar; modülün karşılığı 'like_impinging' (benzer-akışkan
#:    doublet). 'impinging_doublet' FARKLI-akışkan çarpışmasıdır ve hibritte
#:    yakıt sıvı olmadığı için uygulanamaz.
#:
#: 'coaxial' BİLEREK eşlenmemiştir: devre modeli hibritte koaksiyel
#: desteklemiyor ("'coax_swirl' hibritte desteklenmez (tek akışkan)";
#: 'gas_gas_coaxial' yalnız sıvı kademeli yanma motorları için). Zorlama bir
#: eşleme kullanıcıya "gas_gas_coaxial yalnız sıvı motor içindir" gibi
#: sormadığı bir tipe dair hata gösterirdi. Bu tipte devre ayrıntısı
#: üretilmez ve nedeni söylenir; enjektörün kendisi ``utils/injector_design``
#: içindeki tek akışkanlı koaksiyel modelle (iç jet + dış anülüs) yine
#: boyutlandırılır, yani kullanıcı sonuçsuz kalmaz.
INJECTOR_TYPE_TO_MODULE = {
    'impingement': 'like_impinging',
}

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

#: Lüle termal profilinde kullanılan istasyon sayısı. Boğaz istasyonunun
#: çözünürlüğü için 20 yeterli (ölçüldü: 12 ve 20 istasyonda boğaz denge
#: cidar sıcaklığı aynı, 2971 K).
NOZZLE_THERMAL_STATIONS = 20
#: Lüle cidar kalınlığı verilmediğinde kullanılan pay: boğaz insertinde
#: et kalınlığı kamara cidarıyla aynı mertebededir; ayrı bir girdi
#: olmadığı için kamara cidarı kullanılır ve rapor bunu AÇIKÇA yazar.


class HybridRocketEngine:
    def __init__(self, thrust=None, burn_time=None, total_impulse=None, of_ratio=1.0,
                 chamber_pressure=CHAMBER_PRESSURE_PLACEHOLDER_BAR,
                 atmospheric_pressure=1.0, chamber_temperature=None,
                 gamma=1.15, gas_constant=None, l_star=1.0,
                 expansion_ratio=0, nozzle_type='conical',
                 thrust_coefficient=0, regression_a=None,
                 regression_n=None, fuel_density=None, 
                 combustion_type='infinite', chamber_diameter_input=0,
                 contraction_ratio=0,
                 fuel_type='htpb', motor_name='', motor_description='',
                 initial_gox=None, flux_mode='ox', track_performance=True,
                 oxidizer_type='n2o', uq_mode=False, combustion_analyzer=None,
                 eta_c_star=None, precomputed_optimum_of=None,
                 injector_type='showerhead', initial_port_diameter=None,
                 tank_temperature=None, port_count=1,
                 throat_erosion_rate=None,
                 chamber_material=None, wall_thickness=None,
                 cooling_type='natural',
                 safety_factor=None, chamber_length_override=None,
                 nozzle_material=None, ambient_temperature=None,
                 plate_thickness=None, orifice_inlet=None,
                 launch_site=None, closure_bolt_count=None,
                 feed_line_length_m=None, feed_line_inner_diameter_mm=None,
                 discharge_coefficient=None, oxidizer_phase=None):
        
        # Tasarım uyarıları (v2.6.2): kullanıcıya ULAŞAN kanal. Liste her
        # şeyden ÖNCE kurulur; aksi hâlde erken üretilen uyarılar kaybolur
        # (katı motorda aynı tuzağa düşülmüştü, bkz. solid __init__ yorumu).
        self.design_warnings = []
        # ÖH D15 / P1B1-06 — MAKULLÜK KAPILARININ HÜKÜM DEFTERİ.
        #
        # Bölgedeki 8 ``warnings.warn`` noktasının yalnız 2'si bir ``_w()``
        # kaydıyla eşleşiyordu; kalan 6'sı SUNUCU KONSOLUNA gidiyordu ve
        # kullanıcıya HİÇ ulaşmıyordu (ölçüldü, a2/once.json B1-06:
        # ``of_ratio=1.0`` -> konsolda "Anormal c* değeri: 941 m/s", yanıtın
        # ``warnings`` listesinde o kod YOK; ``initial_gox=900`` ve
        # ``eta_c_star=0.30`` için de aynı). Modülün kendi künyesi (:277)
        # "artık TÜM uyarılar sonuç sözlüğüne de konur" diyordu — tutulmamış
        # bir sözdü.
        #
        # Kanal neden ``_w()`` DEĞİL: ``_w()`` kayıtları çeviri sözlüğüne
        # (``hrma/static/js/i18n_common.js``) bağlıdır ve o dosya bu iş
        # kaleminde yazılamaz kapsamdadır (yeni kod + sözlük girdisi olmadan
        # ``tests/test_engine_warning_i18n.py`` haklı olarak kırmızıya döner:
        # kullanıcı ham anahtar görürdü). Bu yüzden hükümler ÇEVİRİSİZ,
        # makine-okur bir VERİ ALANI olarak yayımlanır: her kayıt ölçülen
        # sayıyı, bandı ve hükmü kendi taşır — metin değil, sayı.
        #
        # Biçim: ``{'gate', 'status', 'quantity', 'value', 'band'|'limit',
        # 'unit', 'basis'}``; ``status`` ∈ {'pass', 'out_of_band', 'clamped',
        # 'fallback'}.
        # ÖH D17 / OH-Z5-02: hazne dengesinden okunan ışıyan tür mol
        # kesirleri; ``_calculate_c_star`` doldurur. None = denge henüz
        # çözülmedi (ısı modülüne gönderilmez).
        self.x_H2O_chamber = None
        self.x_CO2_chamber = None
        self.design_gate_checks = []
        # ÖH D20 / B1-06 (Fable-D17 ŞARTI) — her hükmün EVRESİ.
        # 'construction' = kullanıcının GİRDİSİNE ait, koşumdan
        # bağımsız; 'run' = bu ``calculate()`` koşumunun hükmü.
        # Evre kaydı yanıta GİRMEZ (defterin şekli değişmez), yalnız
        # koşum başında hangi kayıtların düşeceğini belirler.
        self._defter_evreleri = {}
        self._defter_evresi = 'construction'
        # Varsayılan/eksik girdiyle mi çalışıldı? design_summary.status bu
        # bayrağı okur — eksik girdiyle "OPTIMIZED" demek yanlıştır.
        self._defaults_used = []
        # Bir alt modül çöküp yedek (fallback) yola düşüldü mü?
        self._fallback_used = []

        # --- Termal sınır koşulları (v2.6.25'te bağlandı) -------------------
        # Bunlar önceden analyze_heat_transfer çağrısında sabit yazılıydı;
        # kullanıcının seçtiği malzeme/kalınlık/soğutma termal modele hiç
        # ulaşmıyordu. Ayrıntılı gerekçe o çağrının başındaki yorumda.
        self.chamber_material = self._resolve_chamber_material(chamber_material)
        # v2.6.26 — KURUCU VARSAYILANI "KULLANICI GİRDİSİ" SAYILMAZ.
        # v2.6.27 (bebek-Scofield F5-1) — CİDARIN TEK KAYNAĞI VARDIR.
        # Eski durumda değer verilmediğinde ısı zinciri SESSİZCE 0,005 m ile
        # koşuyor, yapısal/CAD zinciri ise kendi boyutlandırdığı cidarı
        # (ölçülen örnekte 18,79 mm) çiziyordu: aynı motorda iki cidar, ve
        # "çizilen cidarda SF" ısı zincirinin HİÇ GÖRMEDİĞİ bir cidara
        # aitti. Yeni sözleşme:
        #   * Kullanıcı AÇIKÇA bir cidar verdiyse o kazanır; yapısal taraf
        #     DOĞRULAMA kipine geçer (verify).
        #   * Verilmediyse cidarı yapısal boyutlandırma üretir ve ısı zinciri
        #     onu TÜKETİR (calculate() içindeki sabit-nokta bloğu). Sessiz
        #     5 mm YOK; boyutlandırma çökerse hesap BEYANLI reddedilir.
        # Hangi yolun seçildiği chamber_wall_policy bloğunda ADIYLA yayımlanır.
        # _resolve_wall_thickness geçersiz/aralık dışı girdiyi UYARIP None'a
        # düşürür — eskiden aralık dışı girdi 0,005 m'ye düşüyor ve üstelik
        # "kullanıcı verdi" bayrağı düşüşten ÖNCE hesaplandığı için 5 mm
        # kullanıcının cidarıymış gibi DOĞRULANIYORDU (app.py
        # _motor_structural_design_basis ölçümü).
        self.wall_thickness = self._resolve_wall_thickness(wall_thickness)
        self.wall_thickness_user_supplied = self.wall_thickness is not None
        #: calculate() doldurur: {'policy', 'wall_thickness_m', ...} beyanı.
        self.wall_thickness_policy = None
        #: ÖH D31 / OH-D26-04 — kanal geometrisi beyanı; _resolve_cooling_type
        #: doldurur, calculate() yayımlar.
        self._cooling_geometry_block = None
        self.cooling_type = self._resolve_cooling_type(cooling_type)

        # --- v2.6.26'da bağlanan üç ölü girdi ---------------------------------
        # Üçü de arayüzde VARDI, kullanıcı değerini giriyordu ve hiçbiri
        # hiçbir hesaba ulaşmıyordu (Katman A taraması: 0 yaprak değişimi).
        #   safety_factor          -> yapısal analizin tasarım SF hedefi
        #   chamber_length_override-> L* ile türetilen kamara boyunu ezer
        #   nozzle_material        -> boğaz termal + erozyon değerlendirmesi
        self.design_safety_factor = self._resolve_safety_factor(safety_factor)
        self.chamber_length_override = self._resolve_chamber_length_override(
            chamber_length_override)
        self.nozzle_material = self._resolve_nozzle_material(nozzle_material)

        # --- v2.6.26 ikinci tur: iki sözleşme girdisi -----------------------
        # ambient_temperature [K]: ısı ve yapısal modüller AYNI ortam
        #   sıcaklığını görmelidir. Verilmezse None kalır ve ısı modülünün
        #   kendi varsayılanı tek kaynak olur (buradan sayı uydurulmaz).
        # plate_thickness [m]: enjektör plaka kalınlığı. Orifis L/D = t/d
        #   oranı deşarj katsayısını (Cd) belirler; verilmezse devre çözücüsü
        #   kendi beyan edilen L/D varsayımında kalır.
        self.ambient_temperature = self._resolve_ambient_temperature(
            ambient_temperature)
        self.injector_plate_thickness = self._resolve_plate_thickness(
            plate_thickness)
        self.injector_orifice_inlet = self._resolve_orifice_inlet(
            orifice_inlet)

        # --- Kapak cıvata sayısı (v2.6.27 Dalga 6, yol haritası A4) --------
        # Katı/sıvı motorda bu değer overrides sözlüğünden okunuyor
        # (``closure_bolt_count``); hibrit motorun overrides kanalı yoktur,
        # bu yüzden kurucu parametresi olarak alınır. VARSAYILANI YOKTUR:
        # verilmezse birleşim boyutlandırılmaz ve closure_joint bloğu
        # NOT_MODELLED beyanıyla eksik girdinin ADINI söyler.
        self.closure_bolt_count = self._resolve_closure_bolt_count(
            closure_bolt_count)

        # --- Besleme hattı atalet kapıları (v2.6.27, F2b hibrit chug) ------
        # Sıvıdaki karar 5'in ikizi: hat uzunluğu/çapı ÇÖZÜLMEZ ve
        # VARSAYILANI YOKTUR. İkisi de verilirse chug çevrimi ikinci mertebe
        # (hat ataletli) forma geçer; verilmezse ataletsiz koşar ve bunu
        # beyan eder (uydurma yerleşim yasak). Anahtar adları hibritin
        # yayımlanmış adlarıdır — gerekçe FEED_LINE_LENGTH_RANGE_M yorumunda.
        self.feed_line_length_m = self._resolve_feed_line_length(
            feed_line_length_m)
        self.feed_line_inner_diameter_mm = \
            self._resolve_feed_line_inner_diameter(feed_line_inner_diameter_mm)

        # --- Kullanıcının ölçtüğü deşarj katsayısı (v2.6.27 parti 31) -------
        # Defter kalemi: AD ÇAKIŞMASI. Kullanıcı 0,70 gönderirken yanıttaki
        # injector_design.discharge_coefficient 0,78 yazıyordu — çünkü o alan
        # devre çözücüsünün GEOMETRİDEN seçtiği Cd'ydi ve kullanıcının değeri
        # hibrit motora HİÇ ulaşmıyordu (ayrı bir blokta, 'injector' altında
        # duruyordu). Değer artık motora girer ve devre çözücüsüne GİRDİ
        # olarak verilir; verilmezse alan yine tablodan gelir ve gerekçesi
        # (cd_basis) bunu söyler. Sıvı motorla AYNI band (USER_CD_RANGE).
        self.injector_cd_input = self._resolve_discharge_coefficient(
            discharge_coefficient)

        # --- Fırlatma sahası girdisi (v2.6.27, yol haritası A8) -------------
        # resolve_launch_site() çıktısı ya da en az {'elevation_m'} veya
        # {'latitude_deg','longitude_deg'} taşıyan bir sözlük beklenir.
        # Verilmezse None kalır ve launch_site_performance bloğu gerekçesiyle
        # boş döner (sayı uydurulmaz). Sözlük OLMAYAN girdi sessizce
        # yutulmaz: ham hâliyle saklanır ve bloğun NOT_MODELLED gerekçesi
        # kullanıcıya neyin kullanılamadığını söyler (kullanıcıya ULAŞAN
        # kanal bloğun kendisidir; yeni bir warn.* kodu gerektirmez).
        if isinstance(launch_site, dict) and launch_site:
            self.launch_site_input = dict(launch_site)
            self._launch_site_raw_invalid = None
        else:
            self.launch_site_input = None
            self._launch_site_raw_invalid = (
                None if launch_site is None else str(launch_site)[:80])

        # --- Girdi kapısı (bebek-Scofield F4-3): 0 ≠ "verilmedi" -------------
        # Deponun kendi sözleşmesi (hrma/utils/input_guard.py): yalnız None
        # ve '' varsayılana düşer. Eski satır ``thrust if thrust else 1000``
        # tam da input_guard'ın ÖRNEK olarak verdiği hataydı: thrust=0
        # sessizce 1000 N oluyor, üstelik yanıt supplied=['thrust'] diyerek
        # atılan değeri "kullanıcı verdi" diye raporluyordu (ölçüldü).
        # 0 burada fiziksel olarak da geçersizdir (ṁ = F/(g0·Isp) = 0 →
        # A_t = 0 → bölme hatası); sessizce atılmaz, ADIYLA reddedilir.
        # input_guard.num() '' ve None'ı varsayılana düşürür, sayı olmayanı
        # ve NaN/Inf'i InputError (ValueError alt sınıfı → HTTP 400) yapar.
        _itki_ham = {'thrust': thrust, 'burn_time': burn_time,
                     'total_impulse': total_impulse}
        thrust = input_guard.num(_itki_ham, 'thrust', unit='N')
        burn_time = input_guard.num(_itki_ham, 'burn_time', unit='s')
        total_impulse = input_guard.num(_itki_ham, 'total_impulse',
                                        unit='N*s')
        for _ad, _deger in (('thrust', thrust), ('burn_time', burn_time),
                            ('total_impulse', total_impulse)):
            if _deger is not None and _deger <= 0.0:
                raise input_guard.InputError(
                    f"'{_ad}' must be a positive number; got {_deger:g}. "
                    f"Zero or negative is physically meaningless here and "
                    f"is NOT treated as 'not supplied' - omit the field "
                    f"entirely to use the declared placeholder design "
                    f"point instead.")

        # --- İtki / süre / toplam impuls: AŞIRI BELİRLENMİŞ GİRDİ ------------
        # I = F · t_b üç bilinmeyenli TEK denklemdir: ikisi verilince üçüncüsü
        # ÇÖZÜLÜR. Kullanıcı üçünü birden gönderirse biri mutlaka ezilir.
        #
        # ÖLÇÜLDÜ (v2.6.27 B1 öncesi, bu dosya değişmeden):
        #   {thrust: 500,  burn_time: 20, total_impulse: 7500}  -> t_b = 15,00 s
        #   {thrust: 1000, burn_time: 20, total_impulse: 15000} -> t_b = 15,00 s
        #   {thrust: 500,  burn_time: 20, total_impulse: yok}   -> t_b = 20,00 s
        # İlk iki koşuda kullanıcının 20 s'i SESSİZCE yok oluyordu: uyarı yok,
        # ``defaults_used`` boş, sonuçta hiçbir iz yok. Sayı doğruydu (7500/500
        # gerçekten 15 s eder), YOK OLAN kullanıcının niyetiydi.
        #
        # Bu blok sayıyı DEĞİŞTİRMEZ — önceliği YAZILI hâle getirir ve ezilen
        # girdiyi beyan eder. Öncelik sırası ve gerekçesi:
        #   1) total_impulse + thrust  -> t_b çözülür.  Toplam impuls bir GÖREV
        #      gereksinimidir (ΔV bütçesinden gelir), itki ise besleme/enjektör
        #      donanımının sınırıdır; ikisi de dışarıdan dayatılır, süre ise
        #      bunların SONUCUDUR.
        #   2) total_impulse + burn_time -> F çözülür (itki verilmemişse).
        #   3) total_impulse tek başına -> yer tutucu 10 s (beyanlı varsayılan).
        #   4) total_impulse yok        -> F ve t_b doğrudan kullanılır.
        # Uç katmanındaki beyan (app.py::_CALCULATE_SOLVER_OWNED_FIELDS) bu
        # mantığın SONUCUNU kullanıcıya söyler; buradaki kayıt ise motorun
        # kendi çıktısında da iz bırakır (uç kullanılmadan da görünür olsun).
        if total_impulse is None:
            # Bu dalda eksik girdi yerine sabit yer tutucu (1000 N / 10 s)
            # kullanılır; kullanıcı bunun bir TASARIM olmadığını bilmelidir.
            if thrust is None:
                self._defaults_used.append('thrust')
            if burn_time is None:
                self._defaults_used.append('burn_time')
        elif thrust is None and burn_time is None:
            self._defaults_used.append('burn_time')

        verilen = [ad for ad, deger in (('thrust', thrust),
                                        ('burn_time', burn_time),
                                        ('total_impulse', total_impulse))
                   if deger is not None]
        if total_impulse is not None:
            self.I_total = total_impulse  # N*s
            if thrust is not None:
                self.F = thrust  # N
                self.t_b = total_impulse / thrust  # s
                bagimsiz, turetilen = ('total_impulse', 'thrust'), 'burn_time'
            elif burn_time is not None:
                self.t_b = burn_time  # s
                self.F = total_impulse / burn_time  # N
                bagimsiz, turetilen = ('total_impulse', 'burn_time'), 'thrust'
            else:
                # Default assumption: moderate thrust for given impulse
                self.F = total_impulse / 10  # Default 10s burn time
                self.t_b = 10  # s
                bagimsiz, turetilen = ('total_impulse',), 'thrust'
        else:
            # F4-3: 'verilmedi' testi AÇIKÇA ``is None`` iledir. 0 ve ''
            # buraya ulaşamaz (yukarıdaki input_guard kapısı: '' → None,
            # 0/negatif → InputError). Yer tutucular beyanlıdır
            # (_defaults_used yukarıda dolduruldu).
            self.F = thrust if thrust is not None else 1000  # N
            self.t_b = burn_time if burn_time is not None else 10  # s
            self.I_total = self.F * self.t_b  # N*s
            bagimsiz, turetilen = ('thrust', 'burn_time'), 'total_impulse'

        self.impulse_input_resolution = {
            'supplied': verilen,
            'independent_inputs': list(bagimsiz),
            'derived_quantity': turetilen,
            'thrust_N': float(self.F),
            'burn_time_s': float(self.t_b),
            'total_impulse_Ns': float(self.I_total),
            'priority_basis': (
                'I = F * t_b is one equation in three quantities, so at most '
                'two of {thrust, burn_time, total_impulse} can be independent. '
                'Priority: total_impulse + thrust win and the burn time is '
                'derived; if thrust is absent, total_impulse + burn_time win '
                'and thrust is derived. Rationale: total impulse is a mission '
                'requirement and thrust is a feed-system limit — both are '
                'imposed from outside, whereas the burn time is their '
                'consequence.'),
        }
        # Kullanıcı üçünü birden verdiyse ve verdiği süre çözülenle
        # uyuşmuyorsa: ezme SESSİZ KALMAZ.
        if len(verilen) == 3 and burn_time is not None:
            if not np.isclose(float(burn_time), float(self.t_b), rtol=1e-9):
                self.impulse_input_resolution['overridden'] = {
                    'field': 'burn_time',
                    'submitted_s': float(burn_time),
                    'used_s': float(self.t_b),
                }
                self.design_warnings.append(_w(
                    'warn.hybrid.burn_time_overridden_by_impulse', 'warning',
                    submitted_s=round(float(burn_time), 3),
                    used_s=round(float(self.t_b), 3),
                    thrust_N=round(float(self.F), 1),
                    total_impulse_Ns=round(float(self.I_total), 1)))


        self.OF = of_ratio
        # --- D15/P1B1-11 · KAMARA BASINCI KAPISI --------------------------
        # ÖLÇÜLDÜ (a3/once.json, B1_11): motorun KENDİ kapısı yoktu.
        #   chamber_pressure=0   -> ham ``ZeroDivisionError: float division
        #                            by zero`` (ValueError DEĞİL, yani rota
        #                            katmanı 400'e çeviremez, 500 olur)
        #   chamber_pressure=-20 -> ValueError ama mesaj boğaz tıkanmasını
        #                            anlatıyor; kullanıcı hangi ALANI
        #                            düzelteceğini mesajın gövdesinden
        #                            çıkarmak zorunda.
        # Kardeş kanal (thrust/burn_time/total_impulse) kapısı zaten bu
        # dosyada ve ADIYLA reddediyor; aynı sözleşme buraya da uygulanır:
        # 0 ve negatif "verilmedi" DEĞİLDİR, ADIYLA reddedilir. Sayısal bant
        # ([1, 500] bar) uç katmanının işidir (validation/motor_validation.py,
        # tek kaynak); motor yalnız FİZİKSEL olanaksızı (P_c <= 0 ve
        # NaN/Inf) keser — iki yerde iki bant tutulmaz.
        self.P_c = input_guard.num(
            {'chamber_pressure': chamber_pressure}, 'chamber_pressure',
            unit='bar', default=None)
        if self.P_c is None:
            # ÖH D17 / B1-11 ŞARTI: yer tutucu TEK sabitten okunur.
            self.P_c = CHAMBER_PRESSURE_PLACEHOLDER_BAR
            self._defaults_used.append('chamber_pressure')
        elif self.P_c <= 0.0:
            raise input_guard.InputError(
                f"'chamber_pressure' must be a positive number (bar); got "
                f"{self.P_c:g}. Zero or negative chamber pressure is "
                f"physically meaningless (the throat cannot choke and the "
                f"mass flow divides by it) and is NOT treated as 'not "
                f"supplied' - omit the field entirely to use the declared "
                f"placeholder design point instead.")
        self.P_a = atmospheric_pressure  # bar
        self.fuel_type = fuel_type  # Set fuel_type early
        self.oxidizer_type = oxidizer_type  # 'n2o' | 'lox' | 'h2o2' ...

        # Regresyon akı tabanı (H-7 / KARS-YP B12, 6 Eki 2026). VARSAYILAN
        # 'ox' (imza varsayılanı ve regression_analysis.DEFAULT_FLUX_MODE):
        # r = a·G_ox^n. Depodaki (a, n) çiftleri G_ox tabanlı fitlerdir; G_ox
        # fitini G_total ile beslemek yakıt akısını İKİ KEZ sayar (F018,
        # ölçüldü: O/F 6'da +%9,8, O/F 2'de +%32,6). 'total' (Marxman
        # G_total = G_ox + G_fuel) yalnız G_total tabanlı fitlerle anlamlıdır.
        # Künye: Karabeyoglu, Cantwell & Zilliac, J. Propul. Power 23(4)
        # 2007, §III.A-B (iki taban ayrı türetilir; katsayı hangi tabanda
        # fit edildiyse o tabanla kullanılır); Sutton 9 Eş. 16-2 s. 602;
        # Mishra Eş. 9.13 s. 320. (Eski yorum 'total'ı VARSAYILAN, 'ox'u
        # "geriye uyum" diye anlatıyordu — F018'den beri yanlıştı.)
        #
        # Fail-closed: dize girdi TEK çözücüden geçer (resolve_flux_mode:
        # kırpma + küçük harf + tanınmayanı UnresolvedFluxMode ile RET).
        # Eskiden 'OX', 'G_ox' gibi her tanınmayan dize sessizce 'total'a
        # düşüyordu (KARS-YP ölçümü, varsayılan nokta: ṙ₀ +%25,3, tane boyu
        # −%20,1). Web ucu zaten reddediyordu; değişen yalnız Python API.
        # None için eski yedek ('total') KORUNDU: o yedek DEFAULT_FLUX_MODE
        # ('ox') ile çelişir ama bir bekçi bu ifadeyi kilitliyor
        # (tests/test_d29_arayuz_panel_a2.py) — devir listesinde.
        if flux_mode is not None:
            from hrma.analysis.regression_analysis import resolve_flux_mode
            flux_mode = resolve_flux_mode(flux_mode)
        self.flux_mode = flux_mode if flux_mode in ('total', 'ox') else 'total'
        # O/F kayması -> anlık c*/Isp izleme (denetim bulgusu #2). False ise
        # performans tasarım O/F'sinde donar (eski hızlı davranış).
        self.track_performance = bool(track_performance)
        # Anlık O/F->c* tablo önbelleği: anahtar IZGARA DÜĞÜM İNDİSİ (tam
        # sayı), değer teslim edilen c* [m/s]. Isp saklanmaz — CF ile
        # türetildiği için sonradan değişen bir CF'yle tutarsız kalabilirdi.
        self._perf_cache = {}
        # Yanma boyunca GERÇEKTEN katedilen O/F aralığı: ara değerleme hatası
        # yalnız bu aralıkta ölçülür (uğranmamış bantta hata beyanı anlamsız).
        self._perf_of_min = float('inf')
        self._perf_of_max = float('-inf')
        # Denge çözücüsü bir düğümde çöküp tasarım c*'ına düşüldü mü?
        # Teşhis bloğu bunu beyan eder (sessiz yedeğe düşme yasak).
        self._perf_solver_failed = False
        
        # Use None as marker for default values to be set by fuel type
        self.T_c = chamber_temperature  # K
        self.gamma = gamma
        self.R = gas_constant  # J/kg·K
        # --- D15/P1B1-09 · KARAKTERİSTİK BOY L* KAPISI --------------------
        # ÖLÇÜLDÜ (a3/once.json, B1_09): l_star hiç denetlenmiyordu ve
        # V_c = L*·A_t (bu dosyada, kamara boyu bloğunda) doğrudan dışarı
        # çıkıyordu: l_star=-1,0 -> chamber_volume = chamber_volume_m3 =
        # -6,963969e-04 m³; l_star=-1e6 -> -696,397 m³. Dördünde de TAM
        # sonuç sözlüğü 200 ile dönüyor, tek uyarı yok, ``defaults_used``
        # boş, ``design_gate_checks`` boş. NEGATİF HACİM fiziksel olarak
        # yoktur; "kullanıcı böyle istedi" diye yayımlanamaz.
        #
        # Kapı FAIL-CLOSED'dır ve kardeş kapılarla (thrust/burn_time/
        # total_impulse, yukarıda) AYNI sözleşmeyi kullanır: yalnız None ve
        # '' "verilmedi" sayılır ve imza varsayılanına düşer; 0 ve negatif
        # ADIYLA reddedilir (0 ≠ 'verilmedi', hrma/utils/input_guard.py).
        # Üst bant KONULMADI: hibritte L* tasarıma göre çok geniş bir
        # aralıkta gezer ve uydurma bir tavan, gerçekleşen L*'ı zaten
        # yayımlayan (l_star_achieved / l_star_note) dürüst kanalı bozar.
        self.L_star = self._resolve_l_star(l_star)  # m
        self.epsilon = expansion_ratio if expansion_ratio > 0 else None
        self.nozzle_type = nozzle_type
        self.CF = thrust_coefficient if thrust_coefficient > 0 else None
        # D15/P1B1-02: λ (diverjans verimi) lülenin GEOMETRİK özelliğidir ve
        # C_F'in kim tarafından verildiğinden bağımsızdır; bu yüzden burada,
        # ``_calculate_thrust_coefficient`` çağrılsa da çağrılmasa da çözülür.
        # ``self.CF_source`` C_F'in kaynağını söyler: kullanıcı bir C_F
        # dayattığında yayımlanan λ o sayının İÇİNDE olmayabilir ve yanıtın
        # bunu susması, kullanıcının λ'yı uygulanmış sanmasına yol açar.
        self.lambda_eff = self._resolve_divergence_efficiency()
        self.CF_source = ('user_supplied' if self.CF is not None
                          else 'computed_isentropic')
        self.a = regression_a
        self.n = regression_n
        self.rho_f = fuel_density  # kg/m³
        self.combustion_type = combustion_type
        # v2.6.26: kullanıcının kontraksiyon oranı girdisi. Eskiden motora
        # HİÇ geçirilmiyordu (app.py /calculate bu anahtarı okumuyordu bile),
        # dolayısıyla arayüzdeki alan tamamen ölüydü.
        self.contraction_ratio_input = contraction_ratio
        self.chamber_diameter_input = chamber_diameter_input / 1000 if chamber_diameter_input > 0 else 0  # Convert mm to m
        self.motor_name = motor_name
        self.motor_description = motor_description

        # Başlangıç port oksitleyici kütle akısı G_ox [kg/m²·s] — TASARIM
        # parametresidir (denetim bulgusu #1): port kesit alanı bu akıdan
        # boyutlandırılır (A_port = mdot_ox / G_ox). Enjektör orifis akısıyla
        # KARIŞTIRILMAZ. Tipik N2O/HTPB başlangıç değeri 100-500 kg/m²·s,
        # flooding sınırı ~600-700 kg/m²·s (Sutton & Biblarz, Rocket Propulsion
        # Elements 9. baskı, Böl. 16 — hibrit itki).
        if initial_gox is not None and initial_gox > 0:
            self.G_ox_design = float(initial_gox)
            if self.G_ox_design > OX_FLUX_FLOODING_WARN_KG_M2S:
                warnings.warn(
                    f"G_ox = {self.G_ox_design:.0f} kg/m²·s flooding sınırına "
                    "(~600-700 kg/m²·s) yakın/üstünde — Sutton & Biblarz 9. baskı, Böl. 16"
                )
                # D15/P1B1-06: konsol yetmez — hüküm yanıta da girer.
                self._hukum_kaydet({
                    'gate': 'oxidizer_flux_flooding',
                    'status': 'out_of_band',
                    'quantity': 'G_ox_design',
                    'value': float(self.G_ox_design),
                    'limit': float(OX_FLUX_FLOODING_WARN_KG_M2S),
                    'unit': 'kg/m^2.s',
                    'source': 'initial_gox (design flux you supplied)',
                    'basis': ('Sutton & Biblarz 9th ed. Ch.16: hybrid port '
                              'flooding sets in around 600-700 kg/m^2.s; '
                              'above it the flame is blown off the fuel '
                              'surface and the regression correlation no '
                              'longer describes the motor.'),
                })
        else:
            self.G_ox_design = 350.0  # kg/m²·s — tipik tasarım orta noktası

        # --- v2.5.2 kullanıcı girdisi bağlantıları (UI sözleşmesi) ---
        # Eskiden bu üç büyüklük hesap zincirinde SABİT gömülüydü: enjektör
        # her zaman 'showerhead' tasarlanıyor, N2O tank sıcaklığı hep 293.15 K
        # varsayılıyor ve başlangıç port çapı yalnızca G_ox tasarım akısından
        # türetiliyordu. Kullanıcı arayüzde bunları değiştirse bile sonuç
        # değişmiyordu (kullanıcı şikayeti).
        self.injector_type = (injector_type or 'showerhead').lower()
        # Başlangıç port çapı [m]: verilirse A_port doğrudan bundan gelir ve
        # G_ox_design türetmesi devre dışı kalır (bkz. _design_fuel_grain).
        if initial_port_diameter is not None and float(initial_port_diameter) > 0:
            self.initial_port_diameter = float(initial_port_diameter)
        else:
            self.initial_port_diameter = None
        # Oksitleyici tank sıcaklığı [K]: N2O doyma özellikleri (Dyer NHNE)
        # buna bağlıdır. None ise enjektör modülü varsayılanı kullanılır.
        # ÖH D29 / P16B1-44 — ÇIPLAK ``float()`` HAM PYTHON HATASI SIZDIRIYORDU.
        # ÖLÇÜLDÜ (``a2/once.json`` K5, taban ``4dc63c11``): ``/calculate``a
        # ``oxidizer_temp = [1, 2]`` gönderildiğinde HTTP 500 + gövdede
        # "float() argument must be a string or a real number, not 'list'".
        # Alan adı yok, ne yapılacağı yok — sunucu arızası gibi görünüyordu.
        # Kural İCAT EDİLMEDİ: değer katmanının tek kaynağı
        # ``input_guard.finite_number``dır (bu dosya onu zaten içe aktarıyor).
        if tank_temperature is None:
            self.tank_temperature = None
        else:
            _T_tank = input_guard.finite_number(tank_temperature)
            if _T_tank is None:
                raise ValueError(
                    'tank_temperature must be a finite number in kelvin (K), '
                    f'given: {type(tank_temperature).__name__} '
                    f'{str(tank_temperature)[:40]!r}. No temperature is '
                    'assumed in its place: the oxidizer saturation state '
                    'that feeds the injector is read at this temperature.')
            self.tank_temperature = _T_tank

        # Kitap uyum B16 (Ö-1, §28) — OKSİTLEYİCİ GİRİŞ FAZI GİRDİ OLDU.
        # N₂O'nun HP dengesine giren reaktan entalpisi giriş durumuna
        # (sıcaklık = ``tank_temperature``, faz = bu alan) bağlıdır:
        # 'liquid' (varsayılan, kendinden basınçlı hibritte enjektöre giren
        # doymuş sıvı) ya da 'gas' (298,15 K standart hâl — kalem öncesi
        # davranış, BİT-ÖZDEŞ). Bilinmeyen ad burada ADIYLA reddedilir; sıvı
        # sıcaklığının zarf kapısı (üçlü nokta ≤ T < kritik nokta) ilk yanma
        # çağrısında uygulanır (``_sync_oxidizer_inlet_state``). Alan
        # yalnız N₂O'da hesaba girer; diğer oksitleyiciler sabit referans
        # hâliyle yakılır ve yanıttaki ``oxidizer_inlet_state`` bunu söyler.
        from hrma.engines.oxidizer_inlet import normalize_inlet_phase
        self._oxidizer_phase_given = oxidizer_phase is not None
        self.oxidizer_phase = normalize_inlet_phase(oxidizer_phase)

        # --- Port sayısı N (v2.6.2 fizik denetimi, bulgu F046) ---
        # Eskiden model TÜM grain'leri tek dairesel port varsayıyordu; port
        # sayısı ne girdi ne çıktıydı. N portlu grain'de her portun akısı
        # G_ox = mdot_ox/(N·A_tek_port), yanma çevresi ise N·π·D'dir. Tek-port
        # varsayımı N portlu geometride G_ox'u N kat büyütür, çevreyi N kat
        # küçültür: r ∝ N^n, mdot_f ∝ N^(n−1) (n=0.555, N=4 için r ~2.2 kat
        # yüksek, mdot_f ~%45 düşük). Doğrulama DB'sinde çok portlu kayıt VAR
        # (hyb-amroc1993-htpb-lox-dm01-*), bunlar tek-port modeliyle koşuluyordu.
        # Kaynak: Sutton & Biblarz 9. baskı Böl. 16 (çok portlu grain akı
        # dağılımı); Story, "Large-Scale Hybrid Motor Testing", NTRS 20060047689.
        # D15/P1B1-10 — AYNI DEĞER TİPİNE GÖRE İKİ FARKLI HÜKÜM ALAMAZ.
        # ÖLÇÜLDÜ (a3/once.json, B1_10): eski satır
        # ``int(port_count) if port_count else 1`` idi; ``0`` Python'da
        # falsy olduğu için altındaki "positive integer" dalı sıfır için
        # ERİŞİLEMEZDİ. Sonuç: 0 (int) ve 0.0 SESSİZCE 1 oluyordu (uyarı
        # yok, defaults_used'da iz yok), ama AYNI değer HTML formundan
        # geldiği gibi '0' dizgisiyle gelince ValueError ile REDDEDİLİYORDU.
        # Ayrıca 2.7 sessizce 2'ye kırpılıyordu (kullanıcı 3 port sandığı
        # geometriyi 2 portla alıyordu). Depo sözleşmesi
        # (hrma/utils/input_guard.py) bu iki davranışı da yasaklıyor:
        # yalnız None ve '' "verilmedi"dir; 0 ADIYLA reddedilir; kesirli
        # değer sessizce yuvarlanmaz. ``input_guard.integer`` tam olarak
        # bu sözleşmedir ve tip farkını ortadan kaldırır (0 da '0' da
        # float'a çevrilip aynı kapıdan geçer).
        _port_ham = input_guard.integer({'port_count': port_count},
                                        'port_count', lo=1, default=None)
        if _port_ham is None:
            self.port_count = 1
        else:
            self.port_count = int(_port_ham)
        if self.port_count > 1:
            # Çok portlu grain'de portlar arası etkileşim, kanat (web) kalınlığı
            # ve merkezi port yerleşimi modellenmiyor: N eşdeğer dairesel port
            # varsayılır. Bu, alan/çevre ölçeklemesini DOĞRU yapar ama port
            # birleşmesini (burn-through) yakalamaz.
            self.design_warnings.append(_w(
                'warn.hybrid.multi_port_equivalent_model', 'info',
                port_count=self.port_count))

        # --- Boğaz erozyonu [m/s, YARIÇAP artış hızı] (bulgu F047) ---
        # Hibritte grafit/fenolik boğaz oksitleyici-zengin akışta erozyona
        # uğrar; At büyüdükçe Pc = mdot·c*/At düşer, CF ve Isp düşer. Katı
        # motor modülünde erozyon modeli var, hibritte YOKTU ve tasarım noktası
        # sabit-Pc raporladığı için kullanıcı bu düşüşü hiç görmüyordu.
        #
        # DURUM BEYANI (H-7 / KARS-YP K17, 6 Eki 2026): bu girdi ÇÖZÜME
        # BAĞLI DEĞİLDİR. Kabul edilip saklanır ama depoda (hrma/ altı) onu
        # okuyan hiçbir hesap yok; app.py de geçirmiyor. Eski yorumdaki
        # "None/0 => modellenmiyor (açık uyarı üretilir)" iddiası yanlıştı:
        # hibritte öyle bir uyarı kodu yoktu. Bağlama kararı açık (KC-9;
        # zaman çözümlü erozyon yalnız transient_ballistics'te, varsayılan
        # KAPALI). Kullanıcı sıfırdan farklı bir değer verirse hüküm
        # defterine 'not_coupled' kaydı düşer — sayı değişmez, yalnız
        # girdinin kullanılmadığı söylenir.
        if throat_erosion_rate is None:
            self.throat_erosion_rate = 0.0
        else:
            self.throat_erosion_rate = max(0.0, float(throat_erosion_rate))
        if (np.isfinite(self.throat_erosion_rate)
                and self.throat_erosion_rate > 0.0):
            self._hukum_kaydet({
                'gate': 'throat_erosion_rate_input',
                'status': 'not_coupled',
                'quantity': 'throat_erosion_rate',
                'value': float(self.throat_erosion_rate),
                'unit': 'm/s',
                'source': 'throat_erosion_rate (input you supplied)',
                'applied': False,
                'basis': ('this input is accepted but NOT used: no '
                          'design-point or burn-time result of this engine '
                          'reads it, so every published number is computed '
                          'with a rigid (non-eroding) throat. Time-resolved '
                          'throat erosion exists only in the transient '
                          'analysis, where it is off by default.'),
            })

        self.g0 = G_0  # m/s^2 (BIPM standart, hrma.constants)

        # --- UQ modu (v2.5.0, ARGE spec 2.3/6.2) ---
        # uq_mode=True: danışma amaçlı find_optimum_of_ratio araması (profilde
        # ~%70 süre) ve irtifa/itki-irtifa tabloları ATLANIR — ana çıktılar
        # (Isp, c*, CF, geometri, grain, kütleler) bire bir aynı kalır (bu
        # eşdeğerlik test kilidi altındadır). Varsayılan False: nominal
        # davranış değişmez.
        self.uq_mode = bool(uq_mode)
        # Nominal koşudan enjekte edilebilir optimum-O/F sonucu: uq_mode'da
        # arama atlanınca çıktı sözleşmesindeki optimum_of alanını doldurmak
        # için (None ise alan atlanır ve nota düşülür).
        self._precomputed_optimum_of = precomputed_optimum_of
        # c* (yanma) verimi: None => teorik denge c*'ı (mevcut davranış).
        # Verilirse teslim edilen c* = eta_c_star * c*_teorik tüm performans
        # zincirine (Isp, mdot, boğaz) uygulanır. Tipik hibrit 0.85-0.95
        # (Sutton & Biblarz 9. baskı, Böl. 5/16; Chiaverini & Kuo 2007).
        self.eta_c_star = None if eta_c_star is None else float(eta_c_star)
        if (self.eta_c_star is not None
                and not (ETA_C_STAR_PHYSICAL_BAND[0] <= self.eta_c_star
                         <= ETA_C_STAR_PHYSICAL_BAND[1])):
            warnings.warn(
                f"eta_c_star = {self.eta_c_star:.3f} fiziksel bandın "
                f"({ETA_C_STAR_PHYSICAL_BAND[0]}-"
                f"{ETA_C_STAR_PHYSICAL_BAND[1]}) dışında — yine de uygulanacak"
            )
            # D15/P1B1-06: bu hüküm konsolda kalıyordu. Bant dışı bir verim
            # TESLİM EDİLEN c*'ı doğrudan ölçekler (ölçüldü: eta = 0,300 ->
            # teslim c* = 398,46 m/s, teorik 1328,19) ve o sayı Isp'ye, ṁ'ye,
            # boğaz alanına gider. Kullanıcı bant dışında olduğunu bilmeli.
            self._hukum_kaydet({
                'gate': 'c_star_efficiency_band',
                'status': 'out_of_band',
                'quantity': 'eta_c_star',
                'value': float(self.eta_c_star),
                'band': [float(ETA_C_STAR_PHYSICAL_BAND[0]),
                         float(ETA_C_STAR_PHYSICAL_BAND[1])],
                'unit': '',
                'applied': True,
                'basis': ('measured hybrid c* efficiency is typically '
                          '0.90-0.97 (Chiaverini & Kuo 2007 Ch.1/10; Sutton & '
                          'Biblarz 9th ed. Eq. 3-31). The value you supplied '
                          'is outside the physically defensible band but is '
                          'APPLIED as given - it scales the delivered c*, and '
                          'through it Isp, mass flow and throat area.'),
            })

        # Initialize advanced analysis modules
        # combustion_analyzer enjeksiyonu (UQ): örnekler arası paylaşılan
        # memoizasyonlu CombustionAnalyzer geçirilebilir; None ise her motor
        # kendi analizörünü kurar (mevcut davranış).
        self.combustion_analyzer = (combustion_analyzer
                                    if combustion_analyzer is not None
                                    else CombustionAnalyzer())
        self.nozzle_designer = NozzleDesigner()
        self.heat_transfer_analyzer = HeatTransferAnalyzer()
        self.structural_analyzer = StructuralAnalyzer()
        
        # Set fuel-specific properties
        self._set_fuel_properties()

        # Kurucu bitti: bundan sonra yazılan her hüküm KOŞUM hükmüdür.
        self._defter_evresi = 'run'

    # --- ÖH D17 / B1-06 (Fable-D15 ŞARTI) · HÜKÜM DEFTERİ TEKİLLEŞTİRMESİ ---
    # Defter D15'te ``list.append`` ile yazılıyordu ve HİÇ sıfırlanmıyordu.
    # ÖLÇÜLDÜ (a1/once.json, ``B1_06``): aynı örnek üzerinde ``calculate()``
    # iki kez koşunca ``c_star_plausibility`` kaydı 1 → 2 oluyordu. Aynı
    # kapının aynı büyüklük için İKİ hükmü yan yana yayımlanıyor, üstelik
    # ikisi ayrışabiliyordu (arada bir alan değiştiyse birincisi BAYAT).
    # Defter "bu koşunun hükümleri" diye okunduğu için bu, sayıyı değil
    # ANLAMI bozuyordu.
    #
    # ŞART iki şık veriyordu: (a) ``calculate()`` başında sıfırla, (b)
    # ``gate``+``quantity`` anahtarıyla tekilleştir. (b) seçildi, çünkü (a)
    # kurucu-zamanı hükümlerini (``oxidizer_flux_flooding``/``G_ox_design``,
    # ``c_star_efficiency_band``) siler — onlar ``__init__`` içinde yazılır ve
    # kullanıcının GİRDİSİNE aittir, koşuya değil.
    #
    # Anahtar (gate, quantity) ÇİFTİDİR; ``gate`` tek başına YETMEZ: aynı
    # dosyada ``oxidizer_flux_flooding`` iki ayrı büyüklük için yazılıyor
    # (``G_ox_design`` kullanıcının verdiği akı, ``G_ox_initial`` port
    # çapından türeyen akı) ve ikisi de meşru, ayrı hükümlerdir.
    #
    # SON YAZAN KAZANIR: ikinci koşum birincinin sayısını taşır, sıra korunur
    # (kayıt YERİNDE güncellenir, listenin sonuna taşınmaz) — böylece defterin
    # okuma sırası koşumdan koşuma oynamaz.
    def _hukum_kaydet(self, kayit):
        """Tasarım kapısı hükmünü deftere (gate, quantity) anahtarıyla yazar."""
        anahtar = (kayit.get('gate'), kayit.get('quantity'))
        # ÖH D20 / B1-06: hükmün evresi ayrı bir sözlükte tutulur. Yeni bir
        # koşum-zamanı kapısı eklendiğinde LİSTEYE eklenmesi gerekmez —
        # ``__init__`` dışında yazılan her hüküm tanım gereği 'run'dur.
        self._defter_evreleri[anahtar] = getattr(
            self, '_defter_evresi', 'run')
        for i, mevcut in enumerate(self.design_gate_checks):
            if (mevcut.get('gate'), mevcut.get('quantity')) == anahtar:
                self.design_gate_checks[i] = kayit
                return kayit
        self.design_gate_checks.append(kayit)
        return kayit

    # --- ÖH D20 / B1-06 · KOŞUM HÜKÜMLERİ KOŞUM BAŞINDA DÜŞER -------------
    # D17 tekilleştirmesi (gate, quantity) anahtarını getirdi ve aynı kapının
    # iki kaydını bitirdi, ama KOŞULLU bir hükmün BAYATLAMASINI bitirmedi:
    # ÖLÇÜLDÜ (D20 a1/once.json ``B1_06``) — t_b = 3e5 ile koşulunca defterde
    # ``burn_integration_steps/clamped`` yazılıyor, aynı örnek t_b = 10 ile
    # yeniden koşulunca kırpma OLMADIĞI hâlde o kayıt DEFTERDE KALIYORDU.
    # Defter "bu koşunun hükümleri" diye okunur; kalan kayıt yalan söyler.
    #
    # ŞARTIN birinci şıkkı uygulandı: ``calculate()`` başında YALNIZ
    # koşum-zamanı kayıtları düşer. Kurucu-zamanı hükümleri
    # (``oxidizer_flux_flooding``/``G_ox_design``, ``c_star_efficiency_band``)
    # kullanıcının GİRDİSİNE aittir, koşuya değil — onlar KORUNUR.
    # Ayırt etme kapı ADINA göre değil YAZILDIĞI EVREYE göre yapılır, yani
    # yeni bir koşum kapısı eklendiğinde burada bir liste güncellemek
    # gerekmez (unutulan kapı = bayat hüküm tuzağı kapanır).
    def _kosum_hukumlerini_dus(self):
        """Önceki koşumun hükümlerini defterden siler; kurucununkiler kalır."""
        evreler = getattr(self, '_defter_evreleri', None)
        if evreler is None:
            self._defter_evreleri = evreler = {}
        kalan = []
        for kayit in list(getattr(self, 'design_gate_checks', []) or []):
            anahtar = (kayit.get('gate'), kayit.get('quantity'))
            if evreler.get(anahtar, 'run') == 'construction':
                kalan.append(kayit)
            else:
                evreler.pop(anahtar, None)
        self.design_gate_checks = kalan

    def _set_fuel_properties(self):
        """Set fuel-specific regression rate parameters and density

        Regresyon katsayıları (a, n) merkezi tablodan gelir:
        hrma/data/propellant_database.py -> HYBRID_REGRESSION_COEFFICIENTS
        (SI birimler: r [m/s] = a * (G_ox [kg/m²·s])^n; kaynak atıfları orada).
        """
        # Default properties for different fuel types
        fuel_properties = {
            'htpb': {
                'density': _FUEL_RHO['htpb'],  # kg/m³
                'combustion_temp': 3200,  # K
                'gas_constant': 415  # J/kg·K
            },
            'pe': {  # Polyethylene (HDPE)
                # ÖH D17 / P15B2-08: yoğunluk TEK KAYNAKTAN
                # (propellant_database.HYBRID_FUEL_DENSITY_KG_M3). Buradaki
                # çıplak 950 kaynaksızdı ve merkezi kayıttan (960)
                # ayrışıyordu; rho_f -> m_f -> O/F -> c* -> Isp zincirine
                # %1,05 giriyordu.
                'density': _FUEL_RHO['pe'],
                'combustion_temp': 3100,
                'gas_constant': 420
            },
            'pmma': {  # PMMA
                'density': _FUEL_RHO['pmma'],
                'combustion_temp': 2900,
                'gas_constant': 380
            },
            'paraffin': {
                'density': _FUEL_RHO['paraffin'],
                'combustion_temp': 3000,
                'gas_constant': 450
            },
            'abs': {
                # ÖH D17 / P15B2-08 (aynı kök): 1040 diğer üç sitede
                # 1050'ydi; merkezi kayıt kazandı.
                'density': _FUEL_RHO['abs'],
                'combustion_temp': 2800,
                'gas_constant': 390
            },
            'pla': {
                # ÖH D20 / OH-D19-10: çıplak 1250 kaynaksızdı ve yanma
                # çözücüsünün 1240'ıyla ayrışıyordu (rho_f -> m_f -> O/F ->
                # c* -> Isp). Merkezi kaynaklı kayıt kazandı.
                'density': _FUEL_RHO['pla'],
                'combustion_temp': 2700,
                'gas_constant': 370
            },
            'carbon': {
                'density': 2200,
                'combustion_temp': 3500,
                'gas_constant': 350
            },
            'aluminum': {
                'density': 2700,
                'combustion_temp': 3800,
                'gas_constant': 320
            },
            'al2o3': {
                'density': 3950,
                'combustion_temp': 3400,
                'gas_constant': 300
            }
        }

        # Get properties for selected fuel type (default to HTPB if not found)
        fuel_key = self.fuel_type.lower()
        # v2.6.2: bilinmeyen yakıt SESSİZCE HTPB'ye düşüyordu. Kullanıcı
        # "PLA seçtim" sanırken HTPB regresyon katsayılarıyla koşuyordu;
        # design_summary.status bunu 'OPTIMIZED' diye rapor ediyordu.
        if fuel_key not in fuel_properties:
            self._defaults_used.append(f'fuel_properties({fuel_key}->htpb)')
        if (fuel_key not in HYBRID_REGRESSION_COEFFICIENTS
                and (self.a is None or self.n is None)):
            # (a, n) kullanıcıdan gelmediyse ve tabloda karşılığı yoksa
            # HTPB katsayısı KULLANILIYOR demektir — sessiz kalmak yasak.
            self._defaults_used.append(f'regression_coefficients({fuel_key}->htpb)')
            self.design_warnings.append(_w(
                'warn.hybrid.fuel_regression_fallback', 'warning',
                fuel=fuel_key))
        # v2.6.2 (F020 eki): UNVALIDATED_REGRESSION_FUELS listesi tanımlıydı ama
        # HİÇ OKUNMUYORDU. Tabloda karşılığı OLAN ama hakemli kaynağı OLMAYAN
        # yakıtlar (pla/carbon/aluminum/al2o3) sessizce tasarım için
        # kullanılıyor, kullanıcı katsayının doğrulanmamış olduğunu hiçbir
        # yerde görmüyordu.
        if (fuel_key in UNVALIDATED_REGRESSION_FUELS
                and (self.a is None or self.n is None)):
            self.design_warnings.append(_w(
                'warn.hybrid.unvalidated_regression_fuel', 'warning',
                fuel=fuel_key))
        # v2.6.2 (F019): HTPB katsayısının doğrulama veritabanına karşı ÖLÇÜLEN
        # sapması. Sabitler tanımlıydı ama hiçbir uyarıya bağlanmamıştı; katsayı
        # bilinçli olarak DEĞİŞTİRİLMEDİĞİ için (bkz. HTPB_COEFF_DB_BIAS_PCT
        # yorumu) sapmanın kullanıcıya bildirilmesi tek dürüst yoldur.
        #
        # v2.6.27 B1 — KAPI ÜRÜNDE ÖLÜYDÜ. Eski koşul ``self.a is None or
        # self.n is None`` idi; oysa advanced.html regresyon alanlarını
        # 0.0000368 / 0.555 ile ÖNCEDEN DOLDURUYOR (:1256, :1267) ve her
        # istekte gönderiyor (:3684-3685). Yani a/n hiçbir zaman None değil
        # ve uyarı hiç ateşlenmiyordu. ÖLÇÜLDÜ (Flask test istemcisi,
        # 2026-08-11, bu değişiklikten önce):
        #     a/n gönderilmeden -> warn.hybrid.htpb_coeff_bias VAR
        #     a/n gönderilerek  -> uyarı YOK
        # Ürünün gerçek akışı ikinci satırdır. Kullanıcı "regresyon oranı çok
        # yüksek" derken, ürünün KENDİ ölçtüğü sapmayı kendisine
        # söylememesinden şikâyetçiydi.
        #
        # Yeni kapı: kullanıcı a/n gönderse bile gönderdiği değer katalog
        # değerine EŞİTSE (yani fiilen kendi katsayısını seçmemiş, formun
        # ön-dolgusunu geri göndermiş) sapma bildirilir. Gerçekten kendi
        # katsayısını girmişse bu uyarı susar — çünkü artık yerleşik katsayı
        # kullanılmıyor — ama sapmanın YÖNÜ ve BÜYÜKLÜĞÜ ayrıca bildirilir.
        katalog_kat = HYBRID_REGRESSION_COEFFICIENTS.get(fuel_key)
        kullanici_verdi = self.a is not None and self.n is not None
        katalogla_ayni = bool(
            kullanici_verdi and katalog_kat
            and np.isclose(float(self.a), float(katalog_kat['a']),
                           rtol=REGRESSION_COEFF_CATALOG_MATCH_RTOL)
            and np.isclose(float(self.n), float(katalog_kat['n']),
                           rtol=REGRESSION_COEFF_CATALOG_MATCH_RTOL))
        # ÖH D18 (kalem B1-13) — KAPI ARTIK YAKIT ADINA DEĞİL, FİİLEN
        # KULLANILAN KATSAYIYA BAKIYOR. Eski koşul ``fuel_key in
        # ('htpb', 'abs')`` elle yazılmış bir AD listesiydi; oysa iki satır
        # aşağıdaki ``HYBRID_REGRESSION_COEFFICIENTS.get(fuel_key,
        # ...['htpb'])`` tabloda karşılığı OLMAYAN HER yakıtı aynı HTPB
        # katsayısına düşürüyor. ÖLÇÜLDÜ (once.json, B1_13; taban 9071a64):
        #   htpb    -> a=3,680e-05 n=0,5550, HTPB katsayısı EVET, uyarı EVET
        #   abs     -> a=3,680e-05 n=0,5550, HTPB katsayısı EVET, uyarı EVET
        #   sorbitol-> a=3,680e-05 n=0,5550, HTPB katsayısı EVET, uyarı YOK
        #   wax_xyz -> a=3,680e-05 n=0,5550, HTPB katsayısı EVET, uyarı YOK
        #   pla/paraffin/pmma/pe -> kendi katsayısı, uyarı YOK (doğru)
        # `sorbitol` ürünün KENDİ geçerli hibrit yakıt listesindedir
        # (hrma/validation/motor_validation.py). Aynı katsayı, aynı ölçülen
        # −%39,5 sapma, farklı beyan. Ölçüt artık türetiliyor: uyarı, motorun
        # FİİLEN koştuğu (a, n) çiftinin HTPB katalog satırı olmasına bağlı.
        # Böylece tabloya yeni yakıt eklendiğinde/çıkarıldığında liste
        # çürümez (elle-liste çürümesi sınıfı).
        _htpb_kat = HYBRID_REGRESSION_COEFFICIENTS['htpb']
        _yururlukteki = katalog_kat if katalog_kat else _htpb_kat
        htpb_katsayisi_yururlukte = bool(
            np.isclose(float(_yururlukteki['a']), float(_htpb_kat['a']),
                       rtol=REGRESSION_COEFF_CATALOG_MATCH_RTOL)
            and np.isclose(float(_yururlukteki['n']), float(_htpb_kat['n']),
                           rtol=REGRESSION_COEFF_CATALOG_MATCH_RTOL))
        # Tabloda karşılığı olmayan yakıtta kullanıcı a/n gönderse bile
        # "katalogla aynı" ölçütünün dayanağı HTPB satırıdır (fiilen o
        # kullanılıyor), yoksa uyarı yine sessiz kalırdı.
        if not katalog_kat and kullanici_verdi:
            katalogla_ayni = bool(
                np.isclose(float(self.a), float(_htpb_kat['a']),
                           rtol=REGRESSION_COEFF_CATALOG_MATCH_RTOL)
                and np.isclose(float(self.n), float(_htpb_kat['n']),
                               rtol=REGRESSION_COEFF_CATALOG_MATCH_RTOL))
        if htpb_katsayisi_yururlukte and (not kullanici_verdi
                                          or katalogla_ayni):
            # ÖH D31 / OH-B1-05 — TEK SAYI TEK BAŞINA ÇIKMAZ. Ürünün kendi
            # 43 kayıtlı ölçümünün yanında, bağımsız ÜÇ HTPB/N₂O kampanyası
            # ADIYLA ve iki ölçümün UZLAŞMADIĞI söylenerek yayımlanır.
            # Katsayı değişmedi; değişen tek şey, kazanılmamış kesinlik
            # iddiasının kaldırılmasıdır.
            # ÖH D32 / OH-B1-05 — BANDIN OKSİTLEYİCİ ZARFI ADIYLA ÇIKAR.
            # Kampanyaların üçü de HTPB/N₂O'dur; koşu başka bir oksitleyici
            # ile yapılıyorsa bant BU KOŞUYA AİT DEĞİLDİR. Bant susturulmaz
            # (yürürlükteki katsayı yine HTPB katalog satırıdır ve yanlılığı
            # ölçülmüştür), fakat "eşleşiyor" diye okunması ENGELLENİR:
            # tüketici ``campaign_scope_match`` alanına bakarak bandı bu
            # koşuya uygulayıp uygulayamayacağını bilir. Sayı uydurulmaz,
            # yeni bant türetilmez (doktrin 1/6).
            _kosum_oks = str(getattr(self, 'oxidizer_type', '') or '').lower()
            _zarf_icinde = _kosum_oks in HTPB_INDEPENDENT_CAMPAIGN_OXIDIZERS
            self.design_warnings.append(_w(
                'warn.hybrid.htpb_coeff_bias', 'warning',
                run_oxidizer=_kosum_oks,
                campaign_oxidizer_scope=HTPB_INDEPENDENT_CAMPAIGN_OXIDIZERS,
                campaign_scope_match=_zarf_icinde,
                campaign_scope_reason=(
                    None if _zarf_icinde else
                    'The published bias body was measured on HTPB/%s '
                    'campaigns only; this run uses %r, which is outside that '
                    'envelope. The band is reported for the coefficient in '
                    'force, NOT as a validated bias for this oxidizer. No '
                    'bias was extrapolated.' % (
                        '/'.join(HTPB_INDEPENDENT_CAMPAIGN_OXIDIZERS),
                        _kosum_oks or None)),
                bias_pct=HTPB_COEFF_DB_BIAS_PCT,
                medape_pct=HTPB_COEFF_DB_MEDAPE_PCT,
                own_pool_points=HTPB_OWN_POOL_POINTS,
                # ÖH D33-3 / OH-D33-46: aynı üç satır, aynı beş alan —
                # üstüne çevrilebilir kabı (``code``/``params``) takılmış
                # hâli. Ekranda ham JSON yerine cümle çıkar.
                independent_campaigns=HTPB_INDEPENDENT_CAMPAIGN_RECORDS,
                independent_campaign_bias_band_pct=(
                    HTPB_INDEPENDENT_CAMPAIGN_BIAS_BAND_PCT),
                independent_pool_points=HTPB_INDEPENDENT_POOL_POINTS,
                independent_pool_bias_pct=HTPB_INDEPENDENT_POOL_BIAS_PCT,
                independent_pool_medape_pct=(
                    HTPB_INDEPENDENT_POOL_MEDAPE_PCT),
                reconciled=False,
                unreconciled_reasons=HTPB_BIAS_UNRECONCILED_REASONS,
                source='docs/arastirma/fizik/A3-hibrit-regresyon.md'))
        elif kullanici_verdi and not katalogla_ayni:
            # Kullanıcı yerleşik katsayıyı GERÇEKTEN ezdi: ne kadar ezdiğini
            # görmeli. Sapma hesaplanır, yorum yapılmaz (kullanıcının kendi
            # static-fire verisi katalogdan iyi olabilir).
            # ÖH D18 (B1-13 eki): dayanak artık YÜRÜRLÜKTEKİ satırdır. Eski
            # koşuldaki ``and katalog_kat`` tabloda karşılığı OLMAYAN yakıtı
            # (sorbitol/wax_xyz) bu daldan da düşürüyordu: kullanıcı kendi
            # a/n'sini girse bile ne bias uyarısı ne de override bilgisi
            # çıkıyordu — sapma hiçbir yerde görünmüyordu.
            self.design_warnings.append(_w(
                'warn.hybrid.regression_coeff_user_override', 'info',
                fuel=fuel_key,
                a_pct=round(float((float(self.a) / float(_yururlukteki['a'])
                                   - 1.0) * 100.0), 1),
                n_pct=round(float((float(self.n) / float(_yururlukteki['n'])
                                   - 1.0) * 100.0), 1)))
        # ÖH D31 / OH-D21-04 — ÖDÜNÇ KATSAYI KULLANICIYA SÖYLENİR.
        # ÖLÇÜLDÜ (``once.json`` K4): ``abs`` ile ``htpb`` BİREBİR aynı
        # (a, n) = (3,68e-05, 0,555) çiftini taşıyor; künye veri katmanında
        # "BORROWED ... not an independent ABS regression fit" diyor ama ABS
        # seçen kullanıcının koşusunda bunu söyleyen TEK BİR UYARI YOKTU
        # (abs koşusunun uyarı kodları arasında ödünç bildirimi yok).
        # ``UNVALIDATED_REGRESSION_FUELS`` bu yakıtı kapsamaz — o liste
        # "hakemli korelasyon YOK" demektir; ABS'de korelasyon VAR ama
        # BAŞKA YAKITIN korelasyonudur. İki durum ayrı ve ikisi de söylenir.
        #
        # Bağış veren yakıt ELLE YAZILMAZ, katalogdan türetilir: aynı çifti
        # taşıyan ve künyesi ``independent: True`` olan satır. Tabloya üçüncü
        # bir ikiz eklenirse beyan kendiliğinden doğru kalır.
        _kunye = HYBRID_REGRESSION_SOURCES.get(fuel_key)
        if (katalog_kat and _kunye and not _kunye.get('independent')
                and _kunye.get('citation')
                and (not kullanici_verdi or katalogla_ayni)):
            _verenler = tuple(sorted(
                ad for ad, c in HYBRID_REGRESSION_COEFFICIENTS.items()
                if ad != fuel_key
                and (c['a'], c['n']) == (katalog_kat['a'], katalog_kat['n'])
                and HYBRID_REGRESSION_SOURCES.get(ad, {}).get('independent')))
            self.design_warnings.append(_w(
                'warn.hybrid.regression_coeff_borrowed', 'warning',
                fuel=fuel_key,
                borrowed_from=_verenler,
                citation=_kunye.get('citation'),
                basis=_kunye.get('basis'),
                independent_fit=False))

        props = fuel_properties.get(fuel_key, fuel_properties['htpb'])
        regression = HYBRID_REGRESSION_COEFFICIENTS.get(
            fuel_key, HYBRID_REGRESSION_COEFFICIENTS['htpb']
        )

        # Set properties - use fuel-specific values if user didn't provide them
        if self.rho_f is None:
            self.rho_f = props['density']
        if self.a is None:
            self.a = regression['a']
        if self.n is None:
            self.n = regression['n']
        if self.T_c is None:
            self.T_c = props['combustion_temp']
        if self.R is None:
            self.R = props['gas_constant']
        
    def _resolve_chamber_material(self, name):
        """Malzeme adını KANONİK materials_db anahtarına çözer; verilmediyse ya da
        tanınmıyorsa HYBRID_CHAMBER_MATERIAL_DEFAULT'a düşer (tanınmayanda UYARIR).

        Sessiz yedeğe düşmek yasak: kullanıcı Inconel seçip çelik sonucu
        görürse bunu fark etmesinin hiçbir yolu olmaz.

        D15/P10B3-08 — TAKMA AD DEĞİL KANONİK AD YAYIMLANIR.
        ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/hibrit/a1/once.json): arayüz
        (advanced.html:2249) 'steel_304' gönderiyor; bu ad materials_db'de
        bir ALIAS'tır ('steel_304' -> 'ss_304'). Eski kod aday adı OLDUĞU
        GİBİ saklıyordu ve aynı motorun malzemesi tek yanıtta İKİ ADLA
        dolaşıyordu:
            structural_analysis.design_parameters.material    = 'steel_304'
            heat_transfer_analysis.design_parameters.material = 'ss_304'
        Panel malzemeyi BİRİNCİ yoldan okuyor (analysis_dock.js:1068
        CHAMBER_MATERIAL_PATHS.hybrid) ve select'inin seçenek listesi
        KANONİK adlardan kurulu (structural_panel.js:23 MATERIALS ->
        'ss_304'). Listede olmayan bir değer atanınca select sessizce ilk
        seçenekte (steel_4130) kalıyordu: aynı oda için SF 0,2841 (ss_304,
        GÜVENSİZ) yerine 0,9593 (4130) gösteriliyordu — 3,3768 kat iyimser.
        Çözüm ADI tek kaynağa bağlamaktır; ekranı uyarı basarak idare etmek
        değil. Ham istek ``chamber_material_requested``ta görünür kalır.
        """
        from hrma.data.materials_db import get_material_safe
        aday = str(name or '').strip() or HYBRID_CHAMBER_MATERIAL_DEFAULT
        self.chamber_material_requested = aday
        try:
            _rec, kanonik = get_material_safe(aday)
            self.chamber_material_resolution = (
                'exact' if kanonik == aday.lower() else 'alias')
            return kanonik
        except (KeyError, ValueError):
            self.chamber_material_resolution = 'unknown_fell_back'
            self.design_warnings.append(_w(
                'warn.hybrid.chamber_material_unknown', 'warning',
                requested=aday, used=HYBRID_CHAMBER_MATERIAL_DEFAULT))
            return get_material_safe(HYBRID_CHAMBER_MATERIAL_DEFAULT)[1]

    def _resolve_wall_thickness(self, value):
        """Kamara cidarını [m] doğrular. None = 'kullanıcı vermedi'.

        F5-1 (bebek-Scofield): eskiden her geçersiz/boş değer SESSİZCE
        0,005 m oluyordu ve ısı zinciri bu 5 mm ile koşarken yapısal/CAD
        zinciri kendi boyutlandırdığı cidarı çiziyordu — aynı motorda iki
        cidar. Artık buradan sayı uydurulmaz: geçerli bir kullanıcı değeri
        yoksa None döner ve cidarı calculate() içindeki yapısal
        boyutlandırma üretir (ısı zinciri onu tüketir). Geçersiz ve aralık
        dışı girdiler UYARIYLA düşer — sessiz düşüş yok.
        """
        if value is None or value == '':
            return None
        try:
            t = float(value)
        except (TypeError, ValueError):
            self.design_warnings.append(_w(
                'warn.hybrid.wall_thickness_invalid', 'warning',
                requested=str(value)[:40]))
            return None
        if not (WALL_THICKNESS_INPUT_MIN_M <= t <= WALL_THICKNESS_MAX_M):
            self.design_warnings.append(_w(
                'warn.hybrid.wall_thickness_out_of_range', 'warning',
                requested_mm=round(t * 1000.0, 3),
                min_mm=WALL_THICKNESS_INPUT_MIN_M * 1000.0,
                max_mm=WALL_THICKNESS_MAX_M * 1000.0))
            return None
        return t

    def _resolve_cooling_type(self, value):
        """Arayüzün kanal seçimini ısı transferi soğutma tipine çevirir.

        Kanal seçildiğinde film katsayısının literatürden alındığını ve
        soğutucu debisinin doğrulanmadığını AÇIKÇA bildirir.
        """
        ham = str(value or 'none').strip().lower()
        tip = COOLING_CHANNEL_TO_TYPE.get(ham)
        if tip is None:
            self.design_warnings.append(_w(
                'warn.hybrid.cooling_type_unknown', 'warning',
                requested=ham, used='natural'))
            self._cooling_geometry_block = self._cooling_geometry_beyani(
                None, 'natural')
            return 'natural'
        # ÖH D31 / OH-D26-04: seçim hangi sınıfa düştüğünü ve o sınıfta
        # KENDİSİNDEN AYIRT EDİLEMEYEN başka seçimler olup olmadığını
        # yayımlar. Beyan sonucun kendi bloğunda durur (uyarıya gömülü
        # değil), çünkü onu tüketen arayüz uyarı listesini ayrıştırmak
        # zorunda kalmamalı.
        self._cooling_geometry_block = self._cooling_geometry_beyani(ham, tip)
        if tip == 'regenerative':
            esler = COOLING_GEOMETRY_EQUIVALENCE.get(tip, ())
            self.design_warnings.append(_w(
                'warn.hybrid.cooling_channels_assumed', 'warning',
                geometry=ham, h_coolant=20000,
                # OH-D26-04: kelimeyi geri okuyan alanın YANINDA, o kelimenin
                # hiçbir sayıya girmediği MAKİNE-OKUR biçimde durur.
                geometry_modelled=False,
                resolved_class=tip,
                indistinguishable_from=tuple(
                    x for x in esler if x != ham)))
        return tip

    def _cooling_geometry_beyani(self, secim, sinif):
        """Kanal geometrisinin modellenip modellenmediğini yayımlar.

        ÖH D31 / OH-D26-04. Menü geometri (radyal/sarmal) soruyor, ısı
        transferi modeli SINIF (doğal/zorlanmış/rejeneratif) çözüyor. Aynı
        sınıfa düşen iki geometri seçimi BİREBİR aynı sayıları üretir
        (ölçüldü: 8.337 yaprağın 8.335'i aynı, fark yalnız kelimenin echo'su).
        Bu blok o gerçeği söyler; bir düzeltme katsayısı UYDURMAZ.
        """
        esler = COOLING_GEOMETRY_EQUIVALENCE.get(sinif, ())
        ayirt_edilemeyen = tuple(x for x in esler if x != secim)
        return {
            'requested': secim,
            'resolved_class': sinif,
            # Sınıfta tek seçim varsa ayırt edilecek bir şey yoktur.
            'modelled': not ayirt_edilemeyen,
            'status': ('NOT_MODELLED' if ayirt_edilemeyen else 'CLASS_ONLY'),
            'indistinguishable_from': ayirt_edilemeyen,
            'equivalence_classes': {
                k: list(v) for k, v in COOLING_GEOMETRY_EQUIVALENCE.items()},
            'missing_inputs_for_geometry_model': list(
                COOLING_GEOMETRY_MISSING_INPUTS),
            'reason': (
                'The coolant-side film coefficient is resolved at CLASS level '
                '(natural / forced / regenerative). Channel geometry '
                '(radial vs spiral) would need a curvature correlation '
                '(Dean-number based, e.g. Manlapaz & Churchill 1980) whose '
                'inputs - coil diameter, channel hydraulic diameter, coolant '
                'velocity and mass flow - are not collected anywhere in this '
                'product. No enhancement factor was invented; selections that '
                'fall in the same class return identical numbers.'),
        }

    def _resolve_safety_factor(self, value):
        """Tasarım emniyet katsayısını doğrular; aralık dışıysa UYARIR.

        None döndürmek 'kullanıcı vermedi' demektir; o durumda yapısal modül
        eski davranışını (malzeme kaydındaki değer) sürdürür. Bilinçli bir
        varsayılan enjekte edilmez ki kullanıcının girdiği ile motorun
        varsaydığı ayrılabilsin.
        """
        if value is None or value == '':
            return None
        try:
            sf = float(value)
        except (TypeError, ValueError):
            self.design_warnings.append(_w(
                'warn.hybrid.safety_factor_invalid', 'warning',
                requested=str(value)))
            return None
        if not (SAFETY_FACTOR_MIN <= sf <= SAFETY_FACTOR_MAX):
            self.design_warnings.append(_w(
                'warn.hybrid.safety_factor_out_of_range', 'warning',
                requested=round(sf, 3),
                min_value=SAFETY_FACTOR_MIN, max_value=SAFETY_FACTOR_MAX))
            return None
        return sf

    def _resolve_ambient_temperature(self, value):
        """Ortam sıcaklığını [K] doğrular; geçersizse None döner.

        None = 'kullanıcı vermedi'. O durumda ısı transferi modülünün kendi
        varsayılanı kullanılır ve AYNI değer yapısal modüle geri okunur —
        iki modülün farklı ortam sıcaklığı varsayması bu sürümde kapatılan
        kusur sınıfıdır (ölçüldü: ısı 293,15 K, yapısal 300,0 K).
        """
        if value is None or value == '':
            return None
        try:
            T = float(value)
        except (TypeError, ValueError):
            self._defaults_used.append(f'ambient_temperature(invalid:{value!r})')
            return None
        # Fiziksel zarf: Dünya yüzeyi çalışma bandının cömert bir üst kümesi
        # (Vostok -89 °C ... Ölüm Vadisi +57 °C). Dışı birim karışıklığının
        # işaretidir (kullanıcı °C girmiş olabilir).
        # ÖH D29 / P16B1-44 — SAYI BURADAN ALINDI, DEĞİŞMEDİ: aynı zarfı
        # artık değer kapısı da (``validation.motor_validation``) okuyor,
        # yani iki yerde iki sayı duramaz (Doktrin 4).
        _zarf_alt, _zarf_ust = AMBIENT_TEMPERATURE_BAND_K
        if not (_zarf_alt <= T <= _zarf_ust):
            self._defaults_used.append(
                f'ambient_temperature(out_of_range:{T:.2f}K)')
            return None
        return T

    def _resolve_plate_thickness(self, value):
        """Enjektör plaka kalınlığını [m] doğrular; geçersizse None döner."""
        if value is None or value == '':
            return None
        try:
            t = float(value)
        except (TypeError, ValueError):
            self._defaults_used.append(f'plate_thickness(invalid:{value!r})')
            return None
        if not (0.0002 <= t <= 0.1):   # 0,2 mm - 100 mm
            self._defaults_used.append(
                f'plate_thickness(out_of_range:{t * 1000.0:.3f}mm)')
            return None
        return t

    def _resolve_orifice_inlet(self, value):
        """Orifis giriş tipini ('sharp'/'radiused') doğrular; yoksa None."""
        if value is None or value == '':
            return None
        aday = str(value).strip().lower()
        if aday in ('sharp', 'radiused'):
            return aday
        self._defaults_used.append(f'orifice_inlet(unknown:{aday})')
        return None

    def _resolve_closure_bolt_count(self, value):
        """Kapak cıvata sayısını doğrular; verilmezse/geçersizse None.

        Katı motorun ``_override_val('closure_bolt_count', 1, 200)``
        kapısıyla aynı bant. None dönmesi bir hata değil, bir BEYAN
        sebebidir: birleşim boyutlandırılmaz.
        """
        if value is None or value == '':
            return None
        try:
            n = int(float(value))
        except (TypeError, ValueError):
            self._defaults_used.append(f'closure_bolt_count(invalid:{value!r})')
            return None
        lo, hi = CLOSURE_JOINT_DEFAULTS['bolt_count_range']
        if not (lo <= n <= hi):
            self._defaults_used.append(
                f'closure_bolt_count(out_of_range:{n})')
            return None
        return n

    def _resolve_feed_line_length(self, value):
        """Besleme hattı uzunluğunu [m] doğrular; verilmezse/geçersizse None.

        None dönmesi hata değil BEYAN sebebidir: chug çevrimi ataletsiz
        koşar ve bunu söyler. Bant dışı değer sessizce kırpılmaz —
        ``_defaults_used`` kaydıyla düşürülür (closure_bolt_count deseni).
        """
        if value is None or value == '':
            return None
        try:
            length = float(value)
        except (TypeError, ValueError):
            self._defaults_used.append(
                f'feed_line_length_m(invalid:{value!r})')
            return None
        lo, hi = FEED_LINE_LENGTH_RANGE_M
        if not (np.isfinite(length) and lo <= length <= hi):
            self._defaults_used.append(
                f'feed_line_length_m(out_of_range:{length!r})')
            return None
        return length

    def _resolve_feed_line_inner_diameter(self, value):
        """Besleme hattı iç çapını [mm] doğrular; verilmezse/geçersizse None.

        Akış kesiti bu çaptan DAİRESEL kesitle türetilir; dairesel olmayan
        kanal için ikinci bir alan (m²) BİLEREK açılmadı (sıvıdaki
        feed_line_area_m2 kanalının hibritte açılmaması ayrı karardır).
        """
        if value is None or value == '':
            return None
        try:
            d_mm = float(value)
        except (TypeError, ValueError):
            self._defaults_used.append(
                f'feed_line_inner_diameter_mm(invalid:{value!r})')
            return None
        lo, hi = FEED_LINE_INNER_DIAMETER_RANGE_MM
        if not (np.isfinite(d_mm) and lo <= d_mm <= hi):
            self._defaults_used.append(
                f'feed_line_inner_diameter_mm(out_of_range:{d_mm!r})')
            return None
        return d_mm

    def _resolve_discharge_coefficient(self, value):
        """Kullanıcının Cd'sini doğrular; verilmezse/geçersizse None.

        None dönmesi hata değildir: devre çözücüsü Cd'yi giriş geometrisi +
        L/D tablosundan seçer ve gerekçesini (``cd_basis``) yazar. Bant dışı
        değer sessizce KIRPILMAZ — ``_defaults_used`` kaydıyla düşürülür
        (feed_line_* kapılarının deseni). Band sıvı motorunkiyle AYNI
        nesneden okunur (injector_design.USER_CD_RANGE).
        """
        if value is None or value == '':
            return None
        try:
            cd = float(value)
        except (TypeError, ValueError):
            self._defaults_used.append(
                f'discharge_coefficient(invalid:{value!r})')
            return None
        lo, hi = USER_CD_RANGE
        if not (np.isfinite(cd) and lo <= cd <= hi):
            self._defaults_used.append(
                f'discharge_coefficient(out_of_range:{cd!r})')
            return None
        return cd

    def _resolve_l_star(self, value):
        """Karakteristik boy L* [m] kapısı (D15/P1B1-09).

        FAIL-CLOSED. ``None``/``''`` "verilmedi" sayılır ve imza
        varsayılanı (1,0 m) beyanla kullanılır; ``0`` ve negatif ADIYLA
        reddedilir. Gerekçe: kamara hacmi V_c = L*·A_t doğrudan bu sayıdan
        gelir ve negatif L* NEGATİF HACİM yayımlar (ölçüm: a3/once.json
        ``B1_09_l_star_kapisi``). Kardeş kapılar (thrust / burn_time /
        total_impulse) aynı sözleşmeyi kullanır.
        """
        cozulen = input_guard.num({'l_star': value}, 'l_star', unit='m',
                                  default=None)
        if cozulen is None:
            self._defaults_used.append('l_star')
            return 1.0
        if cozulen <= 0.0:
            raise input_guard.InputError(
                f"'l_star' must be a positive number (m); got {cozulen:g}. "
                f"The chamber volume is V_c = L* x A_throat, so a zero or "
                f"negative characteristic length publishes a zero or "
                f"negative chamber volume. Zero is NOT treated as 'not "
                f"supplied' - omit the field entirely to use the declared "
                f"placeholder value instead.")
        return float(cozulen)

    def _resolve_chamber_length_override(self, value):
        """Kullanıcının kamara boyu ezmesini [m] doğrular.

        Geometrik tutarlılık (override >= L_grain + L_pre) burada
        BİLİNEMEZ — grain daha hesaplanmamıştır. Bu yüzden burada yalnız
        işaret/birim kontrolü yapılır; geometrik kapı geometri kurulduktan
        sonra _apply_chamber_length_override'da uygulanır.
        """
        if value is None or value == '':
            return None
        try:
            L = float(value)
        except (TypeError, ValueError):
            self.design_warnings.append(_w(
                'warn.hybrid.chamber_length_override_invalid', 'warning',
                requested=str(value)))
            return None
        if L <= 0:
            return None  # 0/boş = otomatik (L* ile türet) — uyarı gerekmez
        if L > 20.0:
            # 20 m üstü bu sınıf motorda birim karışıklığının işareti
            # (kullanıcı mm yerine m girmiş olabilir).
            self.design_warnings.append(_w(
                'warn.hybrid.chamber_length_override_out_of_range', 'warning',
                requested_m=round(L, 3), max_m=20.0))
            return None
        return L

    def _resolve_nozzle_material(self, name):
        """Lüle/boğaz malzemesini doğrular; tanınmıyorsa grafite düşer + UYARIR.

        None döndürmez: lüle termal değerlendirmesi her koşuda yapılır.
        Grafit varsayılanı seçilirken bunun bir VARSAYIM olduğu
        _defaults_used ile işaretlenir.
        """
        from hrma.data.materials_db import get_material
        if name is None or str(name).strip() == '':
            self._defaults_used.append('nozzle_material')
            return 'graphite'
        aday = str(name).strip().lower().replace(' ', '_')
        try:
            get_material(aday)
            return aday
        except (KeyError, ValueError):
            self.design_warnings.append(_w(
                'warn.hybrid.nozzle_material_unknown', 'warning',
                requested=aday, used='graphite'))
            return 'graphite'

    def _kinetic_efficiency(self, combustion_results,
                            throat_diameter=None,
                            characteristic_length=None):
        """(η_kinetik, teşhis) — sonlu-hız kimyası (rekombinasyon) kaybı.

        v2.6.26 — ÇAPRAZ-MOTOR TUTARSIZLIĞI KAPATILDI. Aynı fiziksel kayıp
        SIVI motorda gerçekten hesaplanıyordu
        (``liquid_rocket_engine._kinetic_efficiency`` ->
        ``hrma.analysis.kinetic_efficiency.KineticEfficiency``), hibritte ise
        ``design_nozzle`` imza varsayılanı olan SABİT 0,995 geçiyordu — 18/18
        koşuda hiç değişmedi. Oysa modelin iki girdisi (donmuş ve kayan denge
        Isp'si) hibritin kendi yanma çözümünde ZATEN üretiliyor
        (``combustion_analysis`` performance.isp_frozen / isp_shifting).

        Gerçek lüle akışı donmuş (ODF) ile kayan denge (ODE) arasındadır;
        harman kesri Damköhler benzeri bir parametreden gelir (oda kalış
        süresi t_res = L*·ρ_c·c*/P_c, Sutton & Biblarz 9. baskı Eş. 8-9;
        üç-cisimli rekombinasyon zamanı ∝ P^-2, Bray 1959). Buradaki hiçbir
        katsayı bu görevde ayarlanmadı — modül bu görevden ÖNCE yazılmış ve
        kaynaklandırılmıştır.

        Donmuş/kayan çift çözülemezse η = 1,0 ve 'not_modelled' döner:
        uydurma bir kayıp uygulanmaz (sıvı yolun sözleşmesiyle aynı).

        ÖH D22 / OH-D21-03 — ``characteristic_length`` ARGÜMANI. Kalış süresi
        t_res = V_c·ρ_c/ṁ = L*·ρ_c·c*/P_c bağıntısındaki L*, kamaranın
        GERÇEKLEŞEN karakteristik boyudur. Hibritte port hacmi çoğu zaman
        istenen L*'ın gerektirdiği hacmi tek başına aşar; o rejimde kamara
        küçültülemez ve gerçekleşen L* istenenden büyüktür. Argüman
        verilmezse (motor dışı çağrılar) istenen L* okunur — çağıranın kendi
        sözleşmesi korunur.
        """
        perf = (combustion_results or {}).get('performance') or {}
        isp_frozen = perf.get('isp_frozen')
        isp_shifting = perf.get('isp_shifting')
        if (not isp_frozen or not isp_shifting
                or isp_frozen >= isp_shifting):
            return 1.0, {
                'model': 'not_modelled',
                'note': ('frozen/shifting expansion pair unavailable; the '
                         'finite-rate (kinetic) loss is not resolved and no '
                         'loss is applied.')}
        try:
            from hrma.analysis.kinetic_efficiency import KineticEfficiency
            res = KineticEfficiency().evaluate(
                combustion_results=combustion_results,
                fidelity='engineering',
                chamber_pressure=float(self.P_c),
                characteristic_length=float(
                    characteristic_length if characteristic_length is not None
                    else self.L_star),
                throat_diameter=(
                    float(throat_diameter) if throat_diameter
                    else (float(getattr(self, 'd_t', 0.0)) or None)))
            eta = float(res['isp_predicted']) / float(isp_shifting)
        except Exception as exc:  # korelasyon kurulamadı -> kayıp uygulanmaz
            return 1.0, {'model': 'not_modelled',
                         'note': f'kinetic correlation unavailable ({exc})'}
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

    def _analyze_nozzle_material(self, heat_transfer_results=None):
        """Seçilen lüle/boğaz malzemesinin termal ve erozyon değerlendirmesi.

        v2.6.26 — arayüzdeki 'Nozzle Material' seçicisi bu sürüme kadar
        hiçbir hesaba girmiyordu (grafit / tungsten / bakır seçmek hiçbir
        çıktıyı değiştirmiyordu). Bu fonksiyon o alanı iki gerçek çıktıya
        bağlar:

        1) **Boğaz cidar sıcaklığı ve malzeme sınırı.** Bartz tabanlı eksenel
           profil BOĞAZ istasyonunda çözülür; profil LÜLE malzemesiyle
           koşulur (kamara malzemesiyle değil — ikisi farklı parçadır).
           Soğutma varsayımı arayüzün kendi beyanından gelir
           (NOZZLE_MATERIAL_COOLING; "Copper (Regeneratively Cooled)").
           Denge cidar sıcaklığı malzemenin izin verilen sıcaklığıyla
           karşılaştırılır.

        2) **Erozyon.** Yayımlanmış katsayı bandı OLAN malzemeler için
           (grafit, C-C) ThroatErosionModel ile gerileme hızı ve yanma
           süresince toplam boğaz büyümesi hesaplanır. Bandı olmayan
           malzemede (tungsten) katsayı UYDURULMAZ; 'no published data'
           denir. Soğutmasız metal boğaz için modelin geçerli olmadığı
           açıkça bildirilir.

        Ölçüm gerekçesi: aynı motorda grafit 2971 K denge sıcaklığında
        3300 K sınırının altında kalırken tungsten (2473 K) ve soğutmasız
        bakır (1000 K) sınırı aşar — yani seçim sonucu gerçekten değiştirir.
        """
        from hrma.data.materials_db import get_material

        material = self.nozzle_material
        cooling = NOZZLE_MATERIAL_COOLING.get(material)
        if cooling is None:
            # Tabloda yoksa soğutmasız kabul edilir (konservatif) ve bu
            # varsayım raporda görünür.
            cooling = 'natural'
        try:
            mat = get_material(material)
        except (KeyError, ValueError):
            return {'status': 'not_analyzed',
                    'reason': f"material '{material}' not in materials_db"}

        result = {
            'status': 'analyzed',
            'material': material,
            'material_name': mat.get('name', material),
            'cooling_assumption': cooling,
            'cooling_assumption_basis': (
                'regeneratively cooled (declared by the material selection)'
                if cooling == 'regenerative'
                else 'uncooled heat-sink / radiation-cooled throat'),
            'wall_thickness_mm': self.wall_thickness * 1000.0,
            'wall_thickness_basis': (
                'chamber wall thickness - single source: the user input if '
                'one was supplied, otherwise the structural sizing the '
                'thermal chain consumed (see chamber_wall_policy). No '
                'separate nozzle wall thickness field exists.'),
            'warnings': [],
        }

        # --- 1. Boğaz termal durumu -----------------------------------------
        try:
            profile = self.heat_transfer_analyzer.analyze_axial_profile(
                {
                    'chamber_pressure': self.P_c,
                    'chamber_temperature': self.T_c,
                    'chamber_diameter': self.D_ch,
                    'chamber_length': self.L,
                    'burn_time': self.t_b,
                    'mdot_total': self.mdot_total,
                    'throat_diameter': self.d_t,
                    'nozzle_type': self.nozzle_type,
                },
                n_stations=NOZZLE_THERMAL_STATIONS,
                material=material,
                wall_thickness=self.wall_thickness,
                cooling_type=cooling,
            )
            i = int(profile['throat_index'])
            t_wall = float(profile['T_wall_eq'][i])
            q_throat = float(profile['q_MW'][i])
            t_recovery = float(profile['T_recovery'][i])
        except Exception as exc:  # profil çözülemezse sessiz kalınmaz
            self._fallback_used.append('nozzle_thermal_profile')
            result['throat_thermal'] = {
                'status': 'not_analyzed',
                'reason': f'axial thermal profile failed: {exc}'}
        else:
            # ÖH D37 A2-1 / F-01 + M2 (patch/motor_m2.patch): lüle malzeme
            # eşiği TEK fonksiyondan — merdivenin İZİN basamağı
            # min(allowable_temperature, max_service_temp). Eski okuma alan
            # ADINA bakıyordu (allowable, yoksa max_service_temp); graphite'te
            # 3300 = 3300 (sayı bit-aynı), 4130'da 1000 → 811 olurdu.
            from hrma.data.materials_db import temperature_limits
            allowable = temperature_limits(mat)['allowable_K']
            thermal = {
                'status': 'analyzed',
                'throat_wall_temperature_K': t_wall,
                'gas_recovery_temperature_K': t_recovery,
                'throat_heat_flux_MW_m2': q_throat,
                'allowable_temperature_K': (float(allowable)
                                            if allowable else None),
            }
            if allowable:
                allowable = float(allowable)
                thermal['temperature_margin_K'] = allowable - t_wall
                thermal['utilization'] = (t_wall / allowable
                                         if allowable > 0 else None)
                thermal['verdict'] = ('SAFE' if t_wall <= allowable
                                      else 'EXCEEDS_ALLOWABLE')
                if t_wall > allowable:
                    result['warnings'].append(_w(
                        'warn.hybrid.nozzle_material_over_temp', 'critical',
                        material=result['material_name'],
                        wall_K=round(t_wall),
                        allowable_K=round(allowable),
                        cooling=cooling))
            else:
                thermal['verdict'] = 'NOT_EVALUATED'
                thermal['reason'] = (
                    'no allowable temperature in the material record')
            result['throat_thermal'] = thermal

        # --- 2. Erozyon ------------------------------------------------------
        from hrma.analysis.transient_ballistics import ThroatErosionModel
        try:
            model = ThroatErosionModel.for_material(material)
        except ValueError as exc:
            # Yayımlanmış bant yok (tungsten) veya soğutmasız metal için
            # model geçersiz (çelik/bakır). Katsayı UYDURULMAZ.
            result['erosion'] = {
                'status': 'no_published_data',
                'reason': str(exc),
                'assumption': 'rigid throat (no erosion applied)',
            }
        else:
            rate_mm_s = model.rate_mm_s(self.P_c)
            recession_mm = rate_mm_s * self.t_b
            r0 = self.d_t / 2.0
            r1 = r0 + recession_mm / 1000.0
            area_growth = (r1 / r0) ** 2 - 1.0 if r0 > 0 else 0.0
            result['erosion'] = {
                'status': 'analyzed',
                'radial_recession_rate_mm_s': rate_mm_s,
                'total_radial_recession_mm': recession_mm,
                'throat_diameter_initial_mm': self.d_t * 1000.0,
                'throat_diameter_final_mm': 2.0 * r1 * 1000.0,
                'throat_area_growth_fraction': area_growth,
                'coupled_to_performance': False,
                'coupling_note': (
                    'Reported only; the steady-state performance solution '
                    'assumes a rigid throat. Use the transient solver for '
                    'erosion-coupled thrust and pressure histories.'),
                'model': model.describe(),
            }
            if model.warnings:
                result['erosion']['material_warnings'] = list(model.warnings)
        return result

    def _apply_chamber_length_override(self, L_auto, L_grain, L_pre):
        """Kamara boyu ezmesini geometrik kapıdan geçirerek uygular.

        Döndürür: (L_kullanılan, L_post_kullanılan). Ezme yoksa otomatik
        değerler aynen döner.

        Fiziksel alt sınır L_grain + L_pre'dir: yakıt grain'i ve ön-yanma
        odası kamaranın İÇİNDE olmak zorundadır. Altında bir değer verilirse
        sessizce kırpmak yerine ezme REDDEDİLİR ve neden söylenir — çünkü
        kırpılmış bir değer kullanıcının girdiğinden farklı bir motor demektir
        ve kullanıcı bunu ekranda göremez.
        """
        if self.chamber_length_override is None:
            return L_auto, L_auto - L_grain - L_pre
        L_user = self.chamber_length_override
        L_min = L_grain + L_pre
        if L_user < L_min:
            self.design_warnings.append(_w(
                'warn.hybrid.chamber_length_override_too_short', 'warning',
                requested_mm=round(L_user * 1000.0, 1),
                min_mm=round(L_min * 1000.0, 1),
                grain_mm=round(L_grain * 1000.0, 1),
                pre_mm=round(L_pre * 1000.0, 1)))
            return L_auto, L_auto - L_grain - L_pre
        # Ezme kabul edildi: art-yanma odası kalan boydan gelir.
        return L_user, L_user - L_grain - L_pre

    def _gate_choked_throat(self):
        """Boğazın TIKANIK olduğunu doğrular; değilse sayı üretilmez.

        D15/P1B1-04 — TIKANMAMIŞ REJİMDE TAM TASARIM YAYIMLANIYORDU.
        Boğaz ancak Pc/Pa >= ((γ+1)/2)^(γ/(γ−1)) iken tıkanır. Bu koşulun
        altında hem At = ṁ·c*/(Pc·C_D) (calculate() içindeki boyutlandırma)
        hem de C_F için kullanılan alan-Mach bağıntısı (Sutton & Biblarz
        9. baskı Eş. 3-30) TANIMSIZDIR: boğazda M = 1 yoktur, süpersonik
        ıraksak kısım kurulmaz.

        ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/hibrit/a1/once.json, Pa = 1,0 bar,
        γ ≈ 1,136 → kritik oran 1,7322): Pc = 1,0 bar'da ε = 250,000
        (TAVANA dayanmış), d_t = 272,8 mm, d_e = 4313,1 mm — yani 1 kN'luk
        bir motora 4,3 m çıkış çapı — ve TEK uyarı yok. ε(Pc) monoton bile
        değildi (250,000 → 1,2432 → 1,0214 → 1,0100 → 1,0143 → 1,1624),
        oysa eşlenik genişleme oranı Pc/Pa ile monoton artmak zorundadır.
        Bu geometri doğrudan STL/STEP/DXF ihracına ve atölyeye gidiyordu.

        Erişim ürünün KENDİ izin verdiği banttadır: motor_validation.py
        chamber_pressure için [1, 500] bar kabul ediyor, atmospheric_pressure
        için hiçbir bant yok ve varsayılan Pa = 1,0 bar. Bu yüzden kapı
        burada, sayının doğduğu yerde kurulur. Uyarı basıp tasarımı yine
        yayımlamak beyandır, çözüm değildir: yayımlanan çap yanlıştır.
        """
        try:
            gamma = float(self.gamma)
            p_c = float(self.P_c)
            p_a = float(self.P_a)
        except (TypeError, ValueError):
            return
        if not (np.isfinite(gamma) and gamma > 1.0):
            return
        if not np.isfinite(p_a) or p_a <= 0.0:
            # Vakum (Pa = 0): oran sonsuz, boğaz her zaman tıkanık.
            return
        kritik_oran = ((gamma + 1.0) / 2.0) ** (gamma / (gamma - 1.0))
        self.choked_pressure_ratio_required = float(kritik_oran)
        self.choked_pressure_ratio = float(p_c / p_a)
        if self.choked_pressure_ratio >= kritik_oran:
            self.throat_choked = True
            return
        self.throat_choked = False
        raise ValueError(
            f'The nozzle throat is not choked at this operating point, so no '
            f'supersonic nozzle can be sized for it: the chamber pressure is '
            f'{p_c:.4f} bar against an ambient pressure of {p_a:.4f} bar '
            f'(pressure ratio {p_c / p_a:.4f}), but choking requires '
            f'Pc/Pa >= ((gamma+1)/2)^(gamma/(gamma-1)) = {kritik_oran:.4f} '
            f'for gamma = {gamma:.4f}. Below that ratio the throat area '
            f'relation At = mdot*c_star/(Pc*Cd) and the area-Mach thrust '
            f'coefficient (Sutton & Biblarz 9th ed. Eq. 3-30) are undefined, '
            f'so the throat and exit diameters would not be physical. Raise '
            f'chamber_pressure above {kritik_oran * p_a:.4f} bar or lower '
            f'atmospheric_pressure (analyse the motor at altitude).')

    def calculate(self):
        # ÖH D20 / B1-06 (Fable-D17 ŞARTI): önceki koşumun hükümleri düşer.
        self._kosum_hukumlerini_dus()

        # Calculate characteristic velocity
        self.C_star = self._calculate_c_star()

        # Boğaz tıkanma kapısı — buradan SONRAKİ her geometri bağıntısı
        # tıkanık boğaz varsayar (bkz. _gate_choked_throat künyesi).
        self._gate_choked_throat()

        # Calculate expansion ratio if not provided
        if self.epsilon is None:
            self.epsilon = self._calculate_expansion_ratio()
        # ÖH D21 / P15B1-04: λ geometriden gelir ve geometri ε'yi bekler.
        # Kurucuda ε yoksa katalog sabiti künyeli yedek olarak konmuştu;
        # ε çözüldüğü an λ da lüle panelinin kaynağından yeniden çözülür.
        self.lambda_eff = self._resolve_divergence_efficiency()
        
        # Advanced combustion analysis with Cantera (kendi yanma çözücümüz)
        fuel_composition = {self.fuel_type: 100.0}  # Simplified for now
        ox = getattr(self, 'oxidizer_type', None) or 'N2O'
        # v2.6.26 — GENİŞLEME ORANI ARTIK GEÇİRİLİYOR.
        # `analyze_combustion` bu argümanı ZATEN destekliyordu; verilmediğinde
        # çıkış basıncını ISA deniz seviyesine (1,01325 bar) çapalıyor ve bunu
        # `exit_pressure_basis: 'sea_level_default'` ile dürüstçe bildiriyor.
        # Ama hibrit çağrısı hiç göndermediği için "İrtifa Performansı" paneli
        # her zaman "deniz seviyesinde tam genişlemiş nozul" varsayıyordu:
        # ölçüldü, ε 2/4/8/16 süpürüldüğünde sea_level_isp ve vacuum_isp 15
        # hane boyunca SABİT kaldı (191,976 / 211,809 s) ve ε=16'da motor
        # paneli Isp 125,8 s derken irtifa paneli 192,0 s gösteriyordu (%53).
        # Kullanıcı nozul genişlemesini büyütüp irtifa kazancını göremiyordu.
        self._sync_oxidizer_inlet_state()  # B16: giriş durumu yanmaya gider
        combustion_results = self.combustion_analyzer.analyze_combustion(
            fuel_composition, ox, self.OF, self.P_c, None,
            eta_c_star=self.eta_c_star,
            expansion_ratio=self.epsilon,
            # ÖH D24 / P15B1-05: bu ağaç TASARIM noktasıdır (self.OF).
            # Yanıtta kardeşi 'optimum_analysis.analysis' danışma amaçlı
            # OPTİMUM O/F'de duruyor; ikisi artık adıyla ayrılıyor.
            operating_point=OPERATING_POINT_DESIGN,
        )
        # B16: beyanın dürüstlüğü — giriş entalpisi YALNIZ denge (HP) yolunda
        # oda sıcaklığına girer; ampirik zarfa düşülmüşse (ör. yakıtın Hf'si
        # yok) beyan bunu söyler.
        self._combustion_temperature_source = (
            (combustion_results.get('conditions') or {}).get('chamber') or {}
        ).get('temperature_source')

        # Gerçek termodinamik değerler CombustionAnalyzer denge çözümünden alınır.
        # DİKKAT: gamma/MW/sıcaklık 'compositions'->'chamber' altındadır
        # ('conditions'->'chamber' yalnızca {'P','T'} içerir; eski kod yanlış
        # anahtara baktığı için bu güncelleme hiç çalışmıyordu).
        if 'compositions' in combustion_results and 'chamber' in combustion_results['compositions']:
            chamber_data = combustion_results['compositions']['chamber']
            if 'gamma' in chamber_data:
                self.gamma = chamber_data['gamma']  # shifting-equilibrium isentropik üs
            if 'molecular_weight' in chamber_data:
                self.R = self.combustion_analyzer.R_universal / chamber_data['molecular_weight']
            if 'temperature' in chamber_data:
                self.T_c = chamber_data['temperature']  # HP dengesinden alev sıcaklığı

        # --- ÖH D20 / B1-12 · TEK KAYIP KÜMESİ, İKİ GEÇİŞLİ BOYUTLANDIRMA ---
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/D20/fizik/a1/once.json): aynı yanıtta
        # aynı lüle için İKİ C_F ve İKİ Isp yayımlanıyordu ve manşet DAİMA
        # iyimser olandı. Kök sebep ayrılma modeli DEĞİL (D15 iki tarafın
        # ayrılmayı 16 hane özdeş çözdüğünü ölçmüştü) KAYIP KÜMESİYDİ:
        #   manşet C_F  -> yalnız diverjans verimi lambda
        #   lüle paneli -> lambda x eta_friction x eta_2phase x eta_kinetic
        # Ölçülen fark (Pc=30 bar, HTPB/N2O, O/F=6): eps=6,5 +%1,860;
        # eps=12 +%1,794; eps=40 +%2,010; eps=otomatik +%1,872 — manşet Isp
        # sırasıyla 241,16 / 231,24 / 231,24 / 242,45 s.
        #
        # Onarım: manşet C_F artık AYNI kayıp kümesini uygular. Kinetik verim
        # (sonlu-hız kimyası) boğaz çapına bağlıdır, boğaz çapı ise manşet
        # C_F'ten türer; zincir bu yüzden SABİT NOKTAYA yinelenir. Yineleme
        # yalnız (eta_kinetik -> C_F -> Isp -> mdot -> At -> d_t) çekirdeğini
        # kapsar; geometri/uyarı üreten bloklar bir kez, yakınsamış d_t ile
        # koşar. Kayıpsız C_F d_t'den BAĞIMSIZ olduğu için bir kez çözülür
        # (ayrılma uyarısı da böylece bir kez üretilir).
        #
        # Kaynak: Sutton & Biblarz 9. baskı Böl. 3 (düzeltme çarpanları:
        # diverjans, sürtünme, iki-faz, kinetik ayrı ayrı ve ÇARPIM olarak
        # uygulanır); NASA SP-8120. Sıvı motorda aynı küme zaten tek yerden
        # uygulanıyor.
        # --- ÖH D22 / OH-D21-03 · η_kin GERÇEKLEŞEN L* İLE BESLENİR ------
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/D22/hibrit/a1/once.json): kinetik
        # verim İSTENEN L*'ı okuyordu, gerçekleşeni değil. Hibritte port
        # hacmi çoğu zaman istenen L*'ın gerektirdiği hacmi TEK BAŞINA aşar
        # (``chamber_length_source == 'grain_limited'``); o rejimde kamara
        # küçültülemez, yani istenen L* FİİLEN UYGULANMAZ — ama sayı yine de
        # kalış süresine giriyor ve geometriyi oynatıyordu:
        #   l_star = 1 / 2 / 3 m  ->  d_t = 21,8410 / 21,8055 / 21,7836 mm
        #                             L   = 0,69122 / 0,69012 / 0,68944 m
        #                     L*_achieved = 3,55036 / 3,54686 / 3,54470 m
        # Üç koşunun üçü de aynı kamarayı boyutlandırıyor; fark yalnızca
        # ULAŞILAMAYAN bir L*'ın kayıp modeline sızmasından geliyordu
        # (hayalî geometri). Kalış süresi tanımı gereği GERÇEK hacimden
        # gelir: t_res = V_c·ρ_c/ṁ = (V_c/A_t)·ρ_c·c*/P_c = L*_ach·ρ_c·c*/P_c
        # (Sutton & Biblarz 9. baskı Eş. 8-9).
        #
        # Gerçekleşen L* boyutlandırmanın SONUCUDUR (V_c_actual / A_t) ve
        # kayıp kümesi üzerinden boyutlandırmayı besler; zincir bu yüzden
        # SABİT NOKTAYA yinelenir. Yineleme daralmalıdır (ölçülen daralma
        # çarpanı ~1/680: girdideki %67'lik fark çıktıda %0,098'e iniyor),
        # bu yüzden birkaç geçişte kapanır. Yakınsamazsa FAIL-CLOSED.
        #
        # Yan etki disiplini: her geçiş uyarı/hüküm üretebilir. Hüküm defteri
        # (gate, quantity) anahtarıyla ÜZERİNE YAZAR (``_hukum_kaydet``), bu
        # yüzden kendiliğinden son geçişi tutar. ``design_warnings`` düz bir
        # listedir; ara geçişlerin ekledikleri SİLİNİR, yalnız yakınsayan
        # geçişin uyarıları kalır (kullanıcıya giden kanal budur).
        _cf_kullanici_girdisi = self.CF
        _l_star_kin = float(self.L_star)
        _ls_yakinsadi = False
        _ls_onceki_fark = None
        for _ls_gecis in range(1, HYBRID_KINETIC_LSTAR_MAX_PASSES + 1):
            _uyari_isareti = len(self.design_warnings)
            self.CF = _cf_kullanici_girdisi
            eta_friction_manset = NOZZLE_FRICTION_EFFICIENCY_DEFAULT
            # Hibrit egzozu gaz fazıdır: yoğuşmuş faz kesri 0 -> eta_2phase = 1,0.
            # Sayı UYDURULMAZ; panelin kullandığı kesirle aynı kaynaktan gelir.
            eta_two_phase_manset = 1.0
            kayip_yineleme = {
                'friction_efficiency': float(eta_friction_manset),
                'two_phase_efficiency': float(eta_two_phase_manset),
            }
            if self.CF is None:
                cf_kayipsiz = self._calculate_thrust_coefficient()
                d_t_tahmin = None
                eta_kin = 1.0
                kin_diag = None
                yakinsadi = False
                for _gecis in range(1, HYBRID_LOSS_SIZING_MAX_PASSES + 1):
                    eta_kin, kin_diag = self._kinetic_efficiency(
                        combustion_results, throat_diameter=d_t_tahmin,
                    characteristic_length=_l_star_kin)
                    eta_kayip = (eta_friction_manset * eta_two_phase_manset
                                 * float(eta_kin))
                    cf_yeni = float(cf_kayipsiz) * eta_kayip
                    isp_yeni = cf_yeni * self.C_star / self.g0
                    mdot_yeni = self.F / (self.g0 * isp_yeni)
                    at_yeni = (mdot_yeni * self.C_star
                               / (self.P_c * 1e5 * THROAT_DISCHARGE_COEFFICIENT))
                    d_t_yeni = 2.0 * np.sqrt(at_yeni / np.pi)
                    if d_t_tahmin is not None and abs(
                            d_t_yeni / d_t_tahmin - 1.0) <= HYBRID_LOSS_SIZING_TOL:
                        d_t_tahmin = d_t_yeni
                        yakinsadi = True
                        break
                    d_t_tahmin = d_t_yeni
                if not yakinsadi:
                    # FAIL-CLOSED: yakınsamayan bir boyutlandırma yayımlanmaz.
                    raise ValueError(
                        f'The hybrid sizing loop that resolves the kinetic '
                        f'efficiency together with the throat diameter did not '
                        f'converge in {HYBRID_LOSS_SIZING_MAX_PASSES} passes '
                        f'(relative throat-diameter change still above '
                        f'{HYBRID_LOSS_SIZING_TOL:g}); no thrust coefficient is '
                        f'published for this operating point.')
                self.CF_lossless = float(cf_kayipsiz)
                self.CF = float(cf_kayipsiz) * (
                    eta_friction_manset * eta_two_phase_manset * float(eta_kin))
                kayip_yineleme.update({
                    'kinetic_efficiency': float(eta_kin),
                    'thrust_coefficient_lossless': float(cf_kayipsiz),
                    'loss_product': float(eta_friction_manset
                                          * eta_two_phase_manset * float(eta_kin)),
                    'passes': int(_gecis),
                    'converged': True,
                    'throat_diameter_m': float(d_t_tahmin),
                    'basis': (
                        'headline thrust coefficient = lossless CF (Sutton & '
                        'Biblarz 9th ed. Eq. 3-30 with the divergence factor on '
                        'the momentum term, Eq. 3-34) times the SAME loss set the '
                        'nozzle panel applies (friction x two-phase x kinetic). '
                        'The kinetic efficiency depends on the throat diameter, '
                        'which depends on the headline coefficient, so the pair '
                        'is iterated to a fixed point; the loop does not '
                        'converge silently - it raises'),
                })
            else:
                # Kullanıcı C_F verdiyse o sayı OLDUĞU GİBİ kullanılır (kayıp
                # kümesi ikinci kez uygulanmaz); kinetik verim yine de panel için
                # çözülür ve künyede kaynağı yazılır.
                eta_kin, kin_diag = self._kinetic_efficiency(
                combustion_results,
                characteristic_length=_l_star_kin)
                self.CF_lossless = None
                kayip_yineleme.update({
                    'kinetic_efficiency': float(eta_kin),
                    'thrust_coefficient_lossless': None,
                    'loss_product': None,
                    'passes': 0,
                    'converged': True,
                    'throat_diameter_m': None,
                    'basis': ('user-supplied thrust coefficient: the loss set is '
                              'NOT applied a second time on top of it'),
                })
            self.headline_loss_set = kayip_yineleme
            self.kinetic_efficiency_headline = float(eta_kin)
            self.kinetic_diagnostics_headline = kin_diag

            # Calculate specific impulse FIRST (before mass flow)
            self.Isp = self.CF * self.C_star / self.g0
        
            # Calculate mass flow rates using correct rocket equation
            # F = mdot * g0 * Isp => mdot = F / (g0 * Isp)
            self.mdot_total = self.F / (self.g0 * self.Isp)
        
            # Split mass flow between oxidizer and fuel
            self.mdot_ox = self.mdot_total * self.OF / (1 + self.OF)
            self.mdot_f = self.mdot_total / (1 + self.OF)
        
            # Calculate throat geometry using correct formula
            # At = mdot * C* / (Pc * CD) — C_D sözleşmesinin boyutlandırma ucu
            # (tanım ve tek kaynak: THROAT_DISCHARGE_COEFFICIENT künyesi).
            CD = THROAT_DISCHARGE_COEFFICIENT
            self.At = self.mdot_total * self.C_star / (self.P_c * 1e5 * CD)  # m²
            self.d_t = 2 * np.sqrt(self.At / np.pi)
        
            # Calculate exit geometry
            self.Ae = self.At * self.epsilon
            self.d_e = 2 * np.sqrt(self.Ae / np.pi)
        
            # Calculate chamber volume
            self.V_c = self.L_star * self.At
        
            # Design fuel grain
            self._design_fuel_grain()
        
            # Calculate chamber dimensions
            if self.chamber_diameter_input > 0:
                self.D_ch = self.chamber_diameter_input
            else:
                # N portlu grain'de kamara, N portun TOPLAM alanını sarmalıdır:
                # eşdeğer port çapı sqrt(N)·D_tek (F046).
                self.D_ch = self.D_port_final * np.sqrt(self.port_count) * 1.5
            # v2.5.2 (Codex bulgusu hybrid:827) — SON kapı: grain portu sarmalı.
            # Yüklenen yakıt kütlesi (π/4)·(D_ch² − D_port_ilk²)·L_grain ile
            # hesaplandığından D_ch <= D_port_ilk durumunda NEGATİF kütle çıkar.
            # Time-marching girişindeki doğrulama bunu zaten reddeder; burası
            # kullanıcı kamara çapı vermeyip portun beklenmedik biçimde büyüdüğü
            # yolları da kapatır. Sessiz kırpma YOK — açık hata.
            if self.D_ch <= self.D_port_initial:
                raise ValueError(
                    f"Chamber diameter {self.D_ch * 1000:.1f} mm is not larger "
                    f"than the initial port diameter "
                    f"{self.D_port_initial * 1000:.1f} mm; the fuel grain would "
                    f"have negative volume. Increase the chamber diameter or "
                    f"reduce the port diameter / oxidizer mass flux."
                )
            # --- Kamara boyu (v2.5.2 L* modeli) ---
            # ESKİ MODEL: L = max(4·V_c/(π·D_ch²), L_grain). Hibritte grain boyu
            # neredeyse her zaman baskın olduğundan max(...) daima L_grain'i
            # seçiyor ve L* girdisi geometriyi HİÇ değiştirmiyordu (kullanıcı
            # şikayeti: "L* geometriyi değiştirmiyor").
            #
            # YENİ MODEL — hibrit kamara üç bölümden oluşur:
            #     L = L_grain + L_pre + L_post
            #   L_pre  : ön-yanma odası (pre-combustion chamber). Enjektör
            #            püskürtmesinin gelişmesi ve akışın düzelmesi için
            #            standart mühendislik ölçüsü ~0.5·D_ch.
            #   L_post : art-yanma odası (post-combustion chamber). Karışmamış
            #            yakıt/oksitleyicinin yanmasını tamamlaması için gereken
            #            EK hacimden gelir: L* karakteristik boyu toplam kamara
            #            hacmini (V_c = L*·At) belirler; portun içerdiği hacim
            #            düşülünce kalan hacim art-yanma odasına verilir.
            # Böylece L* ARTTIKÇA kamara boyu ölçülebilir biçimde artar.
            # Kaynak: Sutton & Biblarz 9. baskı Böl. 8/16; Chiaverini & Kuo,
            # "Fundamentals of Hybrid Rocket Combustion and Propulsion" (2007),
            # ön/art-yanma odası boyutlandırma pratiği.
            A_ch = np.pi / 4.0 * self.D_ch ** 2
            L_pre = PRE_CHAMBER_D_FACTOR * self.D_ch
            D_port_avg = 0.5 * (self.D_port_initial + self.D_port_final)
            V_port_avg = np.pi / 4.0 * D_port_avg ** 2 * self.L_grain
            L_post_raw = (self.V_c - V_port_avg) / A_ch if A_ch > 0 else 0.0
            L_post = float(np.clip(L_post_raw,
                                   POST_CHAMBER_D_FACTOR_MIN * self.D_ch,
                                   POST_CHAMBER_D_FACTOR_MAX * self.D_ch))
            L_auto = self.L_grain + L_pre + L_post
            # v2.6.26: "Chamber Length Override (mm)" alanı bu sürüme kadar
            # tamamen ölüydü (arayüzde vardı, hiçbir yere gitmiyordu). Artık
            # L* ile türetilen boyu ezer; geometrik alt sınır kapısı
            # _apply_chamber_length_override içinde.
            self.L, L_post = self._apply_chamber_length_override(
                L_auto, self.L_grain, L_pre)
            self.L_pre_chamber = L_pre
            self.L_post_chamber = L_post
            self.chamber_length_auto = L_auto
            # v2.6.26 — ETİKET ÜÇÜNCÜ DURUMU DA SÖYLÜYOR.
            # Eskiden yalnız iki değer vardı ve ezme yoksa her koşuda
            # 'l_star_derived' yazıyordu. Oysa hibritte port hacmi çoğu zaman
            # istenen L*'ın gerektirdiği hacmi TEK BAŞINA aşar; o durumda art-yanma
            # odası geometrik alt sınıra kelepçelenir ve kamara boyu fiilen
            # GRAIN UZUNLUĞUNDAN gelir, L*'tan değil. Ölçüldü: varsayılan koşuda
            # L_post/D_ch tam 0,3000 (alt sınırın kendisi) çıkarken etiket hâlâ
            # "L* ile türetildi" diyordu. l_star_note bu durumu zaten dürüstçe
            # anlatıyordu ama makinece okunan alan yanlış cevap veriyordu.
            if abs(self.L - L_auto) > 1e-9:
                self.chamber_length_source = 'user_override'
            elif abs(L_post - POST_CHAMBER_D_FACTOR_MIN * self.D_ch) < 1e-9:
                self.chamber_length_source = 'grain_limited'
            elif abs(L_post - POST_CHAMBER_D_FACTOR_MAX * self.D_ch) < 1e-9:
                self.chamber_length_source = 'post_chamber_clamped_high'
            else:
                self.chamber_length_source = 'l_star_derived'

            # GERÇEKLEŞEN L*: hibritte port hacmi tek başına büyük olduğundan
            # istenen L* çoğu zaman geometrik alt sınırın ALTINDA kalır; bu
            # durumda kamara küçültülemez ve gerçekleşen L* istenenden büyüktür.
            # Sessiz kalmak yerine dürüstçe raporlanır (kullanıcı "L* hiçbir şeyi
            # değiştirmiyor" derken tam olarak bu kelepçeyi görüyordu).
            V_chamber_actual = V_port_avg + (L_pre + L_post) * A_ch
            self.V_c_actual = V_chamber_actual
            self.L_star_achieved = (V_chamber_actual / self.At
                                    if self.At > 0 else self.L_star)
            # Not: bu durum hibritlerde KURALDIR (port hacmi büyüktür), bu yüzden
            # her koşuda uyarı üretmek gürültü olur; bilgi sonuç sözlüğüne not
            # olarak konur ve arayüz gösterir.
            if self.L_star_achieved > self.L_star * 1.02:
                self.l_star_clamped_high = False
                self.l_star_note = (
                    f"Requested L* = {self.L_star:.2f} m is below the volume the "
                    f"grain port geometry already provides; achieved L* is "
                    f"{self.L_star_achieved:.2f} m. Increase L* above that value "
                    f"to lengthen the post-combustion chamber."
                )
            elif self.L_star_achieved < self.L_star * 0.98:
                # --- ÖH D23 / OH-D22-01 · ÜST TARAFTA DA NOT YAZILIR ------
                # Kırpma İKİ yönde de oluyordu ama not YALNIZ küçük tarafta
                # yazılıyordu: büyük tarafta kullanıcının sayısı yanıt
                # ağacının üç yerinde yankılanıp not BOŞ kalıyordu (ölçüldü:
                # l_star = 1e3 ve 1e9 -> achieved 6,385 m, note ""). Boş
                # beyan, beyanın hiç olmamasıdır. Tavan bir literatür bandı
                # DEĞİL, bu kamaranın kendi geometrisidir: art-yanma odası
                # POST_CHAMBER_D_FACTOR_MAX x D_ch'te kelepçelenir.
                self.l_star_clamped_high = True
                self.l_star_note = (
                    f"Requested L* = {self.L_star:.2f} m is above the volume "
                    f"this chamber can enclose: the post-combustion chamber "
                    f"is clamped at {POST_CHAMBER_D_FACTOR_MAX:g} x the "
                    f"chamber diameter ({self.D_ch * 1000.0:.1f} mm), so the "
                    f"achieved L* is {self.L_star_achieved:.2f} m. The "
                    f"requested value was NOT applied."
                )
            else:
                self.l_star_clamped_high = False
                self.l_star_note = ''

            _l_star_ach = float(self.L_star_achieved)
            _ls_fark = (abs(_l_star_ach / _l_star_kin - 1.0)
                        if _l_star_kin > 0.0 else 0.0)
            if _ls_fark <= HYBRID_KINETIC_LSTAR_TOL:
                _ls_yakinsadi = True
                # BİT-KARARLILIK. Tolerans karşılandıktan sonra da, sayı
                # değişmeyi bırakana kadar yinelenir. Sebep ölçüldü: aynı
                # geometrik tabana çarpan iki koşum (l_star = 1 ⟷ 2 m) 1e-11
                # toleransında durunca kamara boyunda 4,5e-15 m'lik bir YOL
                # FARKI bırakıyordu (0,6891707442737663 ⟷ ...618). Fark
                # gürültü tabanının (1e-12) altındadır ama iki koşum AYNI
                # kamarayı boyutlandırdığı için aynı sayıyı vermelidir.
                # İlerleme durursa (son-bit salınımı) döngü yine kapanır.
                if (_l_star_ach == _l_star_kin
                        or (_ls_onceki_fark is not None
                            and _ls_fark >= _ls_onceki_fark)):
                    break
            del self.design_warnings[_uyari_isareti:]
            _ls_onceki_fark = _ls_fark
            _l_star_kin = _l_star_ach
        if not _ls_yakinsadi:
            # FAIL-CLOSED: kapanmayan bir kamara/kayıp zinciri yayımlanmaz.
            raise ValueError(
                f'The hybrid sizing loop that resolves the achieved '
                f'characteristic length L* together with the kinetic '
                f'efficiency did not converge in '
                f'{HYBRID_KINETIC_LSTAR_MAX_PASSES} passes (relative L* '
                f'change still above {HYBRID_KINETIC_LSTAR_TOL:g}); no '
                f'chamber geometry is published for this operating point.')
        self.l_star_kinetic_passes = int(_ls_gecis)
        self.l_star_kinetic_input_m = float(_l_star_kin)

        # --- Grain/kamara narinlik (L/D) uyarısı (v2.6.27, yol haritası) ---
        # TEŞHİS KANITI: varsayılan girdiler L/D ≈ 19,7'lik bir boru üretiyor
        # ve kullanıcıya hiçbir uyarı çıkmıyordu (ölçüm GRAIN_LD_WARN_THRESHOLD
        # sabitinin başındaki yorumda). Kamara L/D her zaman grain L/D'den
        # büyüktür (L = L_grain + ön + art oda); ikisi de raporlanır ki
        # kullanıcı hangi büyüklüğün eşiği aştığını görsün.
        #
        # Uyarı kodu 'warn.' önekiyle sözlük sözleşmesine bağlıdır: EN/TR
        # karşılıkları hrma/static/js/i18n_common.js'te durur (ilk sürümde
        # sözlük dosyası başka bir değişikliğin kapsamındayken geçici bir
        # 'fallback' metniyle ve motor önekiyle yayımlanmıştı; 2026-08-04'te
        # sözlük kayıtları eklendi, kod warn. önekine taşındı, fallback
        # kaldırıldı).
        grain_ld = (self.L_grain / self.D_ch) if self.D_ch > 0 else 0.0
        chamber_ld = (self.L / self.D_ch) if self.D_ch > 0 else 0.0
        if max(grain_ld, chamber_ld) > GRAIN_LD_WARN_THRESHOLD:
            ld_uyari = _w('warn.hybrid.grain_slenderness_high', 'warning',
                          grain_ld=round(float(grain_ld), 1),
                          chamber_ld=round(float(chamber_ld), 1),
                          threshold=GRAIN_LD_WARN_THRESHOLD)
            self.design_warnings.append(ld_uyari)

        # Calculate propellant masses
        self.m_ox = self.mdot_ox * self.t_b
        # Yakıt kütlesi grain geometrisinden (denetim bulgusu #6):
        # m_f = rho_f · (π/4) · (D_final² − D_initial²) · L_grain.
        # Eski mdot_f·t_b değeri grain'in fiilen ürettiği kütleyle
        # eşitlenmiyordu (3-4 kat tutarsızlık).
        self.m_f = self.m_f_grain
        self.m_total = self.m_ox + self.m_f
        # OPUS DENETİM DÜZELTMESİ (major): m_f YANAN yakıttır; grain dış
        # çapı kamara iç çapına kadar döküldüğünden YÜKLENEN yakıt daha
        # büyüktür (yanmayan sliver kalır). İkisi ayrı raporlanır ki araç
        # kütle bütçesi (yüklenen) ile performans bütçesi (yanan)
        # karıştırılmasın.
        # D15/P1B1-01: PORT SAYISI. Yanan kütle (``m_f_grain``) N'i
        # kullanıyordu, yüklenen kütle KULLANMIYORDU — aynı fonksiyon
        # çiftinde N bir kez var bir kez yoktu. N portlu grain'de kamara
        # kesitinden N tane port kesiti düşülür:
        #     m_f_loaded = rho_f · (π/4) · (D_ch² − N·D_port_ilk²) · L_grain
        # N=1'de ifade eskisiyle BİREBİR aynıdır. Terimin pozitifliği
        # ``_design_fuel_grain`` kapısıyla garantidir: kullanıcı kamara çapı
        # verdiyse N·D_i² ≤ (0,8·D_ch)², vermediyse D_ch = 1,5·√N·D_port_son
        # ve D_port_son > D_port_ilk.
        # Ölçülen sapma (F=3 kN, t_b=8 s, O/F=2,5, Pc=25 bar, D_i=30 mm):
        # N=2 +%10,47 · N=4 +%20,46 · N=7 +%28,29 — sayı
        # ``fuel_mass_loaded`` ve ``key_dimensions.total_mass_kg`` ile
        # YAYIMLANIYORDU.
        r_grain_outer = self.D_ch / 2.0
        self.m_f_loaded = self.rho_f * np.pi / 4.0 * (
            (2.0 * r_grain_outer) ** 2
            - self.port_count * self.D_port_initial ** 2
        ) * self.L_grain
        self.fuel_sliver_fraction = max(
            0.0, 1.0 - self.m_f / max(self.m_f_loaded, 1e-9))
        
        # ÖH D20 / B1-12: yanma çözümü ve gerçek (gamma, R, T_c) aktarımı
        # BOYUTLANDIRMANIN ÖNÜNE alındı (yukarı taşındı) — manşet C_F'in
        # kayıp kümesi kinetik verimi içerdiği için o verim boğaz
        # çapından ÖNCE çözülmek zorunda. ``combustion_results`` bu
        # noktada zaten hazırdır.
        
        # Advanced nozzle design — gerçek yanma değerlerini (gamma, R, T_c)
        # geçir; aksi halde design_nozzle eski hardcoded 1.25/300/3000'e düşer
        # ve CF/Isp motorun geri kalanıyla tutarsız olur (entegrasyon gap fix).
        # v2.6.26 — İKİ ÖLÇÜLMÜŞ KOPUKLUK burada kapatıldı:
        #
        # 1) contraction_area_ratio geçirilmiyordu: lüle tasarımcısı kendi
        #    varsayılanına (A_c/A_t = 2.25) düşüyor, kullanıcının daralma
        #    oranı yakınsak kontura hiç ulaşmıyordu. Aynı yanıtta iki farklı
        #    daralma oranı görünüyordu.
        # 2) wall_material geçirilmiyordu: cidar kalınlığı/kütlesi ne seçilirse
        #    seçilsin ÇELİKTEN (7850 kg/m³, 250 MPa) hesaplanıyordu. Kullanıcı
        #    tungsten seçtiğinde sonuçta 'nozzle_material: tungsten' yazarken
        #    lüle kütlesi çelik yoğunluğundan çıkıyordu. nozzle_design.py:730
        #    bu hatayı kendi yorumunda tarif etmiş ama çağıran düzeltilmemişti.
        #
        # 3) (v2.6.26, ikinci tur) wall_safety_factor ve kinetic_efficiency
        #    geçirilmiyordu:
        #    - Lüle cidarı DAİMA malzeme kaydının kendi emniyet katsayısıyla
        #      (çelikte 4,0) boyutlanıyordu; kullanıcının 'Safety Factor'
        #      girdisi hazne cidarına uygulanırken lüleye hiç ulaşmıyordu.
        #      ÖLÇÜLDÜ: safety_factor=2,0 ile wall_safety_factor 4,0 kaldı.
        #    - Kinetik (sonlu-hız kimyası) verimi imza varsayılanı 0,995'te
        #      sabitti; oysa AYNI büyüklük sıvı motorda gerçekten hesaplanıyor
        #      (liquid_rocket_engine._kinetic_efficiency -> KineticEfficiency).
        _cr, _ = self._resolve_contraction_ratio()
        # ÖH D20 / B1-12: kinetik verim İKİNCİ kez çözülmez — manşet kayıp
        # kümesinin sabit-nokta yinelemesinde çözülen değer TEK kaynaktır
        # (yakınsamış boğaz çapıyla hesaplanmıştır). Sürtünme verimi de aynı
        # tanım noktasından geçirilir, imza varsayılanına bırakılmaz.
        eta_kin = self.kinetic_efficiency_headline
        kin_diag = self.kinetic_diagnostics_headline
        nozzle_results = self.nozzle_designer.design_nozzle(
            self.At, self.epsilon, self.P_c, self.P_a, self.nozzle_type,
            gamma=self.gamma, R_specific=self.R, T_chamber=self.T_c,
            contraction_area_ratio=_cr,
            wall_material=getattr(self, 'nozzle_material', None),
            wall_safety_factor=self.design_safety_factor,
            kinetic_efficiency=eta_kin,
            friction_efficiency=NOZZLE_FRICTION_EFFICIENCY_DEFAULT,
        )
        # Kinetik verimin NEREDEN geldiği çıktıda taşınır (sıvı motordaki
        # 'kinetic' teşhis bloğuyla aynı sözleşme). Çözülemediğinde eta=1,0
        # ve 'not_modelled' denir — sessizce 0,995 uydurulmaz.
        try:
            nozzle_results['performance']['kinetic'] = kin_diag
        except (KeyError, TypeError):
            pass

        # --- ÖH D20 / B1-12 · AYNI LÜLENİN İKİ C_F'İ: ARTIK TEK KAYIP KÜMESİ
        # D15 kalemin ilk yarısını (iki BAĞIMSIZ ayrılma modeli) çürütmüştü:
        # iki taraf ayrılmayı 16 hane özdeş çözüyor. Ayakta kalan yarı KAYIP
        # KÜMESİYDİ ve D20'de kapatıldı — manşet C_F artık lüle panelinin
        # uyguladığı kümenin AYNISINI uygular (yukarıdaki sabit-nokta
        # yinelemesi). Ölçülen etki (Pc=30 bar, HTPB/N2O, O/F=6):
        #   eps      manşet/panel farkı        manşet Isp [s]
        #   6,5      +%1,8601 -> -%0,0652      241,162 -> 236,616
        #   12       +%1,7940 -> -%0,2454      231,239 -> 226,620
        #   40       +%2,0102 -> -%0,2454      231,239 -> 226,144
        #   otomatik +%1,8716 -> +%0,0038      242,452 -> 238,017
        # Manşet artık iyimser olan DEĞİL, kötümser olan taraftır.
        #
        # GERİYE KALAN fark ölçülmüş ve adlandırılmıştır (kayıt aşağıda):
        #  1) lambda'nın UYGULAMA YERİ. Sutton & Biblarz 9. baskı Denk. 3-34
        #     diverjans çarpanını YALNIZ momentum itkisine uygular
        #     (F = lambda*mdot*v2 + (p2-p3)*A2); manşet böyle yapar, lüle
        #     paneli lambda'yı basınç-itki terimi DÂHİL tüm C_F ile çarpar.
        #     Ölçülen: -%0,0690 (eps=6,5), -%0,2818 (12), -%0,4879 (40),
        #     0 (adapte genleşme; basınç terimi zaten sıfır).
        #  2) lambda'nın KAYNAĞI. Manşet katalog sabitini (konik 0,983),
        #     panel konturun geometrik değerini ((1+cos15°)/2 = 0,9829629)
        #     kullanır: +%0,0038.
        #  3) Ayrılmış bantta iki tarafın ayrılma-istasyonu C_F'ini kuruş
        #     biçimi (eps_sep ile eps_effective) son hanelerde ayrışır.
        # Bunların üçü de nozzle_design.py'nin sahasıdır ve bu aşamada
        # AÇILMADI; kayıt sayıyı yayımlar, ÇÖZDÜĞÜNÜ İDDİA ETMEZ.
        try:
            _np = nozzle_results.get('performance') or {}
            _cf_panel = _np.get('thrust_coefficient_actual')
            _cf_manset = getattr(self, 'CF', None)
            if (_cf_panel is not None and _cf_manset is not None
                    and float(_cf_panel) > 0.0):
                _kume_panel = 1.0
                for _ad_k in ('friction_efficiency', 'two_phase_efficiency',
                              'kinetic_efficiency'):
                    _v = _np.get(_ad_k)
                    if _v is not None and float(_v) > 0.0:
                        _kume_panel *= float(_v)
                _kume_manset = (self.headline_loss_set or {}).get(
                    'loss_product')
                _lam_h = float(getattr(self, 'lambda_eff', 0.0) or 0.0)
                _lam_p = float(_np.get('divergence_efficiency') or 0.0)
                _bagil = 100.0 * (float(_cf_manset) / float(_cf_panel) - 1.0)
                self.thrust_coefficient_cross_check = ({
                    'gate': 'thrust_coefficient_loss_set_consistency',
                    'status': ('pass' if abs(_bagil)
                               <= HYBRID_CF_CROSS_CHECK_TOL_PCT
                               else 'out_of_band'),
                    'tolerance_percent': float(
                        HYBRID_CF_CROSS_CHECK_TOL_PCT),
                    # --- ÖH D25 / OH-Z5-02 · EŞİĞİN KAYNAĞI ADIYLA -------
                    # Bu sayı kapının SÖZLEŞMESİDİR, bir hesabın sonucu
                    # değil: girdiyle oynamaması beklenen davranıştır.
                    # Tek tanım noktası HYBRID_CF_CROSS_CHECK_TOL_PCT
                    # (bu dosya, :597) ve ölçülen büyüklük kardeş
                    # 'relative_gap_percent' alanıdır — o CANLIDIR
                    # (Katman B sarsımında sabit yaprak listesinde YOK).
                    'tolerance_percent_basis': (
                        'declared gate threshold, not a computed result: '
                        'single definition point '
                        'hybrid_rocket_engine.HYBRID_CF_CROSS_CHECK_TOL_PCT. '
                        'The measured quantity this gate judges is the '
                        'sibling relative_gap_percent.'),
                    'quantity': 'thrust_coefficient',
                    'value': float(_cf_manset),
                    'panel_value': float(_cf_panel),
                    'relative_gap_percent': _bagil,
                    'unit': '-',
                    'source': ('headline cf (this motor chain) vs '
                               'nozzle_design.performance.'
                               'thrust_coefficient_actual (nozzle module)'),
                    'loss_set_headline': _kume_manset,
                    'loss_set_panel': float(_kume_panel),
                    'loss_sets_identical': (
                        _kume_manset is not None
                        and abs(float(_kume_manset) / float(_kume_panel) - 1.0)
                        <= 1e-12),
                    'divergence_efficiency_headline': _lam_h or None,
                    'divergence_efficiency_panel': _np.get(
                        'divergence_efficiency'),
                    'divergence_efficiencies_identical': (
                        _lam_h > 0.0 and _lam_p > 0.0
                        and abs(_lam_h / _lam_p - 1.0) <= 1e-12),
                    # ÖH D23 / P15B1-04 — KAPANDI. Kalan iki kök de ölçüldü
                    # ve kapatıldı; kapanan kökü "kalan" diye yayımlamak
                    # yalan olurdu, bu yüzden liste ARTIK BOŞ olabilir ve
                    # kapanan kökler ayrı bir alanda kayıt altındadır.
                    # Eşik YENİ SAYI DEĞİLDİR: kapının kendi toleransının
                    # binde biri (1e-6 %, yani 1e-8 bağıl). Ölçülen kayan
                    # nokta tabanı 1e-11 bağıl mertebesinde, en küçük GERÇEK
                    # model farkı ise %0,0458 idi - eşik ikisinin arasında
                    # dört kat büyüklük payıyla durur.
                    'remaining_causes': (
                        [] if abs(_bagil) <= HYBRID_CF_CROSS_CHECK_TOL_PCT * 1e-3
                        else [
                        'unresolved: the two chains no longer differ by any '
                        'named model term; a gap above the floating-point '
                        'floor means one of the two sides was changed without '
                        'the other',
                    ]),
                    'closed_causes': [
                        'divergence factor application point (Sutton & '
                        'Biblarz 9th ed. Eq. 3-34: lambda on the momentum '
                        'thrust alone, never on the pressure thrust) - the '
                        'nozzle panel used to apply it to the FULL '
                        'coefficient; closed in D23/P15B1-04. Measured gap '
                        'before: -0.0458% (eps=4), +0.0883% (6.5), +0.2827% '
                        '(12), +0.4733% (40), +0.5793% (100).',
                        'divergence factor SOURCE (headline read a catalogue '
                        'constant, panel read the contour geometry); closed '
                        'in D21/P15B1-04, measured +0.0038%.',
                        'loss set (friction x two-phase x kinetic) carried by '
                        'the headline only; closed in D20/B1-12, measured '
                        'up to +2.0102%.',
                        'separated band: the two sides build the '
                        'separation-station coefficient from their own area '
                        'ratio solution - measured identical to the '
                        'floating-point floor once the application point was '
                        'unified (2.2e-16 absolute at eps = 12, 40, 100).',
                    ],
                    'basis': (
                        'Both numbers describe the SAME nozzle of this run, '
                        'both solve flow separation identically (measured '
                        'identical to 16 digits), both apply the SAME loss '
                        'set (friction x two-phase x kinetic, since D20) and '
                        'both now read the SAME divergence efficiency from '
                        'the contour geometry (since D21 / P15B1-04: the '
                        'headline used to read a catalogue constant that did '
                        'not move with the expansion ratio; measured 24 of 24 '
                        '(type, eps) points diverging, up to 2.0253%). Since D23 '
                        'both also apply the divergence factor at the SAME '
                        'place (momentum thrust only, Eq. 3-34), so the two '
                        'coefficients agree to the floating-point floor; what '
                        'has been closed is listed in closed_causes and '
                        'anything still open in remaining_causes. Neither '
                        'side is the optimistic one any more.'),
                })
        except (TypeError, ValueError, ZeroDivisionError):
            pass

        # Altitude performance — uq_mode'da atlanır (danışma tablosu; ana
        # çıktıları beslemez, MC örneğinde gereksiz maliyet — ARGE spec 6.2)
        altitude_performance = None
        if not self.uq_mode:
            altitudes = [0, 1000, 5000, 10000, 15000, 20000]  # m
            altitude_performance = self.combustion_analyzer.calculate_altitude_performance(
                {
                    'chamber_pressure': self.P_c,
                    'gas_constants': combustion_results['performance']['gas_constants'],
                    'conditions': combustion_results['conditions'],
                    'performance': combustion_results['performance'],
                    # ÖH D22 / B3-13(c): doğru addan okunur (üretici artık
                    # 'chamber_gamma' yayımlıyor); anahtar adı irtifa
                    # tablosunun kendi sözleşmesidir, orada değişmedi.
                    'gamma_avg': combustion_results['performance'][
                        'chamber_gamma'],
                    'mdot_total': self.mdot_total,
                    # T33 (2026-08-03): irtifa tablosu artık motorun TESLİM
                    # ETTİĞİ deniz seviyesi itkisine çapalanır. Bu alan
                    # olmadan tablo lüle kayıplarını hiç uygulamıyor ve
                    # 0 km'de manşetin 1000 N'u yerine ideal 1033,02 N
                    # yazıyordu (%3,45; Isp'de 192,04 s ↔ manşet 185,90 s).
                    'thrust_sea_level': self.F,
                },
                altitudes
            )

        # Optimum O/F ratio — oksitleyiciyi 'ox' (self.oxidizer_type) ile geçir
        # (denetim bulgusu #294). Eski 'N2O' sabiti LOX/H2O2 motorlarında yanlış
        # kimya/stokiyometri kullanıp optimum O/F'yi ve max Isp'yi kaydırıyordu
        # (HTPB stok. O/F: N2O~7-8, LOX~2). combustion analyzer adı .lower() ile
        # normalize ettiğinden n2o motorlarında sonuç değişmez (test güvenli).
        # uq_mode'da bu DANIŞMA amaçlı arama atlanır (profilde tek hesabın
        # ~%70'i); nominal koşudan enjekte edilen sonuç varsa o kullanılır.
        if self.uq_mode:
            optimum_of = self._precomputed_optimum_of
        else:
            # v2.6.26 — GENİŞLEME ORANI OPTİMUM O/F ARAMASINA DA GEÇİYOR.
            # Ana çağrı (yukarıda) ε'yi alıyordu ama bu arama almıyordu:
            # her O/F noktası çıkış istasyonunu ISA deniz seviyesine
            # çapalıyor, dolayısıyla ε=16 seçen kullanıcının optimum O/F
            # tablosu hâlâ ε≈1 koşullarında hesaplanıyordu. ÖLÇÜLDÜ
            # (HTPB/N2O, Pc=20 bar): ε yokken O/F* = 6,845 ve çıkış basıncı
            # 1,01325 bar SABİT; ε=4 -> O/F* = 6,661 / 0,9567 bar;
            # ε=16 -> O/F* = 7,841 / 0,1613 bar. Aynı yanıtta iki çelişkili
            # genişleme varsayımı vardı.
            # B16: arama motorun giriş durumuyla koşar. Modül düzeyi optimum
            # önbelleğinin anahtarı giriş imzasını TAŞIR (2. tur Ş-5:
            # ``CombustionAnalyzer.optimum_of_inlet_signature``); 1. turdaki
            # önbelleği geçici boşaltan yalıtım bağlamı eşzamanlı isteklerde
            # yarışa açıktı ve kaldırıldı.
            self._sync_oxidizer_inlet_state()
            optimum_of = self.combustion_analyzer.find_optimum_of_ratio(
                fuel_composition, ox, self.P_c,
                expansion_ratio=self.epsilon
            )

        # Total impulse to thrust at altitudes — uq_mode'da atlanır (danışma)
        thrust_altitude_analysis = None
        if not self.uq_mode and hasattr(self, 'I_total') and self.I_total > 0:
            altitudes_thrust = [0, 1000, 5000, 10000, 15000, 20000]  # m
            thrust_altitude_analysis = self.combustion_analyzer.calculate_thrust_at_altitudes(
                self.I_total, {
                    'performance': combustion_results['performance'],
                    'conditions': combustion_results['conditions'],
                    'chamber_pressure': self.P_c,
                    'burn_time': self.t_b,
                    # T33: debi ARTIK Isp'den türetilmiyor, çözücüden geliyor
                    # (eski türetme 0,5312 kg/s veriyordu, çözücününki
                    # 0,548540 kg/s — aynı motor için iki farklı kütle akışı).
                    'mdot_total': self.mdot_total,
                }, altitudes_thrust
            )
        
        # Isı transferi analizi
        #
        # v2.6.25 DÜZELTMESİ — ÜÇ KULLANICI GİRDİSİ BURAYA HİÇ ULAŞMIYORDU.
        # Bu çağrıda malzeme 'steel_4130', cidar 5 mm ve soğutma 'natural'
        # SABİT YAZILMIŞTI. Hibrit sayfasındaki "Chamber Material",
        # "Wall Thickness" ve "Include Cooling Channels" seçicileri
        # serileştirilip sunucuya gidiyor, ama termal model onları hiç
        # görmüyordu: kullanıcı Inconel 718 + 8 mm cidar + radyal kanal seçse
        # bile hesap 5 mm 4130 çelik ve soğutmasız yapılıyordu.
        #
        # Sonucu sessiz değildi, YANLIŞTI: soğutucu tarafı film katsayısı
        # doğal taşınımda 25 W/m²K'dır, yani ısıyı dışarı atacak yol yok
        # sayılır. Denge cidar sıcaklığı adyabatik alev sıcaklığına yapışıyor
        # (warn.thermal.wall_pinned_adiabatic) ve GERÇEKÇİ HER TASARIM
        # "cidar eriyor" kritiği veriyordu. Kullanıcı soğutma ekleyerek bunu
        # düzeltmeye çalıştığında ekranda hiçbir şey değişmiyordu.
        #
        # Not: arayüzün 'steel_304' değeri materials_db'de yoktu (kayıt adı
        # 'ss_304'); takma ad v2.6.25'te eklendi, aksi hâlde varsayılan
        # malzeme seçimi burada çözülemezdi.
        # v2.6.26 — SÖZLEŞME BOŞLUĞU KAPATILDI. Bu çağrı yalnız altı anahtar
        # gönderiyordu; ısı modülü bulamadığı büyüklükleri KENDİ genel
        # varsayılanlarından türetiyordu ve motorun gerçek çözümüyle
        # çelişiyordu (ölçüldü, aynı koşu):
        #     c*     motor 1325,00 m/s  <-> ısı modülü 1251,38 m/s  (-%5,6)
        #     boğaz  motor   48,69 mm   <-> ısı modülü   46,85 mm   (-%3,8)
        #     gamma  motor    1,2378    <-> ısı modülü    1,20      (varsayılan)
        #     MW     motor   20,94 g/mol<-> ısı modülü   24,0       (varsayılan)
        # Bileşik Bartz etkisi ~%20 h_g sapması; ayrıca termal panelin
        # gösterdiği boğaz çapı nozul panelininkiyle çelişiyordu.
        # Aynı dosyadaki _analyze_nozzle_material çağrısı boğaz çapını ZATEN
        # doğru geçiriyordu — yani sözleşme bir çağrıda kurulu, diğerinde
        # atlanmıştı.
        ht_input = {
            'chamber_pressure': self.P_c,
            'chamber_temperature': self.T_c,
            'chamber_diameter': self.D_ch,
            'chamber_length': self.L,
            'burn_time': self.t_b,
            'mdot_total': self.mdot_total,
            'throat_diameter': self.d_t,
            'throat_area': self.At,
            'c_star': self.C_star,
            'gamma': self.gamma,
        }
        # Molekül ağırlığı: R spesifikten türetilir (M = R_evrensel/R).
        # Yoksa GÖNDERİLMEZ — ısı modülü kendi Bartz tahminine düşer ve bunu
        # kendi içinde beyan eder; buradan uydurma bir sayı geçirmek yasak.
        if getattr(self, 'R', None):
            ht_input['molecular_weight'] = R_UNIVERSAL / self.R
        # ÖH D17 / OH-Z5-02: ışıyan tür mol kesirleri (yukarıdaki denge
        # çözümünden). Çözüm kurulamadıysa GÖNDERİLMEZ — ısı modülü kendi
        # varsayılanına düşer ve bunu ``radiation_composition_source``
        # alanında beyan eder. İkisi birlikte geçer ya da hiçbiri geçmez:
        # tek kesirle Leckner çifti eksik kalır.
        _x_h2o = getattr(self, 'x_H2O_chamber', None)
        _x_co2 = getattr(self, 'x_CO2_chamber', None)
        if _x_h2o is not None and _x_co2 is not None:
            ht_input['x_H2O'] = float(_x_h2o)
            ht_input['x_CO2'] = float(_x_co2)
        # v2.6.26 — ORTAM SICAKLIĞI TEK KAYNAK. Kullanıcı bir değer verdiyse
        # o geçirilir; vermediyse ısı modülünün KENDİ varsayılanı kullanılır
        # (buradan ikinci bir sayı uydurulmaz). Aşağıda yapısal modüle
        # geçirilen değer, ısı modülünün fiilen kullandığı sayıdan geri
        # okunur — eskiden burada 300,0 K SABİT yazılıydı ve tek motor
        # sonucunda iki farklı ortam sıcaklığı (293,15 K ısı / 300 K yapısal)
        # dolaşıyordu.
        ht_kwargs = {}
        if self.ambient_temperature is not None:
            ht_kwargs['ambient_temp'] = float(self.ambient_temperature)

        def _isi_kosumu(cidar_m):
            """Isı zincirini VERİLEN cidarla koşar (tek çağrı noktası)."""
            return self.heat_transfer_analyzer.analyze_heat_transfer(
                ht_input,
                material=self.chamber_material,
                wall_thickness=float(cidar_m),
                cooling_type=self.cooling_type,
                **ht_kwargs
            )

        def _yapisal_girdi(isi_sonucu, isi_cidar_m=None):
            """Yapısal analiz girdisini kurar; ısı sonucu varsa cidar
            sıcaklıkları ve FİİLEN kullanılan ortam sıcaklığı ondan okunur.

            chamber_temperature GEÇİLMELİ; aksi halde structural modülü
            ortam (300 K) varsayıp termal gerilme=0 ve mukavemet
            deratingi=yok ile çalışır, emniyet faktörünü tehlikeli şekilde
            yüksek gösterir (entegrasyon gap fix). Isı sonucu yoksa T_c'den
            konservatif tahmin devrede kalır — o dal artık yalnız cidar
            boyutlandırmasının TOHUM adımında kullanılır.
            """
            girdi = {
                'chamber_pressure': self.P_c,
                'chamber_temperature': self.T_c,
                'chamber_diameter': self.D_ch,
                'chamber_length': self.L,
                'throat_diameter': self.d_t,
                'nozzle_type': self.nozzle_type,
                'burn_time': self.t_b,
                # v2.6.26: EKSENEL İTKİ YÜKÜ. structural_analysis.py:523
                # burkulma kontrolü bunu `motor_data['thrust']` diye okuyor;
                # anahtar eksikken her motorda 0 N geliyor ve NASA SP-8007
                # burkulma kontrolü fiilen kapalı kalıyordu.
                'thrust': self.F,
            }
            # Ortam sıcaklığı ısı modülünün FİİLEN kullandığı değerden geri
            # okunur (tek kaynak; eskiden burada 300,0 K SABİT yazılıydı ve
            # tek motor sonucunda iki farklı ortam sıcaklığı dolaşıyordu).
            ortam = None
            try:
                ortam = float(
                    isi_sonucu['design_parameters']['ambient_temperature'])
            except (KeyError, TypeError, ValueError):
                ortam = self.ambient_temperature
            if ortam is not None:
                girdi['ambient_temperature'] = float(ortam)
            # ISI -> YAPISAL ZİNCİR (Dalga 0, 2026-07-14): ısı analizinin
            # hesapladığı GERÇEK iç/dış cidar sıcaklıkları geçirilir;
            # structural_analysis._estimate_wall_delta_T bunları birinci
            # öncelikle okur.
            try:
                cidar = isi_sonucu['wall_analysis']
                t_hot = float(cidar['inner_temperature'])
                t_cold = float(cidar['outer_temperature'])
                if np.isfinite(t_hot) and np.isfinite(t_cold) and t_hot > 0:
                    girdi['wall_temperature_hot'] = t_hot
                    girdi['wall_temperature_cold'] = max(t_cold, 0.0)
                    # V3 yapi-sf: sıcaklıkların HESAPLANDIĞI cidar. Yapısal
                    # boyutlandırma ısıl gradyanı (sabit akı, ΔT ∝ t) bu
                    # cidardan boyutlandırdığı cidara ölçekler; böylece
                    # "kalınlaşan cidar daha büyük ısıl gerilme taşır"
                    # boyutlandırmanın İÇİNDE hesaba katılır.
                    if isi_cidar_m is not None:
                        girdi['wall_temperature_reference_thickness'] = \
                            float(isi_cidar_m)
            except (KeyError, TypeError, ValueError):
                pass
            return girdi

        def _yapisal_kosumu(isi_sonucu, gercek_cidar_m, isi_cidar_m=None):
            """Yapısal analizi koşar (tek çağrı noktası).

            v2.6.26 — iki kopukluk burada kapalı kalır: kullanıcının kamara
            malzemesi ve tasarım SF hedefi her koşuda geçirilir;
            ``actual_wall_thickness`` verilirse modül DOĞRULAMA (verify)
            kipinde, verilmezse BOYUTLANDIRMA (size) kipindedir.
            """
            return self.structural_analyzer.analyze_structure(
                _yapisal_girdi(isi_sonucu, isi_cidar_m),
                material=self.chamber_material,
                design_pressure_factor=1.5,
                design_safety_factor=self.design_safety_factor,
                actual_wall_thickness=gercek_cidar_m,
            )

        # --- CİDAR SÖZLEŞMESİ (bebek-Scofield F5-1): TEK KAYNAK -------------
        # Eski akış ısı zincirini sessiz 0,005 m ile koşuyor, yapısal zincir
        # ise kendi boyutlandırdığı cidarı (ölçülen örnekte 18,79 mm)
        # çiziyordu; "çizilen cidarda SF = 2,152" ısı zincirinin hiç
        # görmediği bir cidara aitti. Ölçülen gerçek: aynı örnekte çizilen
        # cidar KENDİ termal durumuyla değerlendirilince SF_total 0,941'e
        # düşüyor — eski çift-cidar durumu tehlikeyi MASKELİYORDU.
        if self.wall_thickness_user_supplied:
            # YOL A — kullanıcının AÇIKÇA verdiği cidar kazanır: ısı zinciri
            # onunla koşar, yapısal taraf DOĞRULAMA kipine geçer.
            heat_transfer_results = _isi_kosumu(self.wall_thickness)
            structural_results = _yapisal_kosumu(heat_transfer_results,
                                                 self.wall_thickness,
                                                 self.wall_thickness)
            self.wall_thickness_policy = {
                'policy': 'user_supplied',
                'wall_thickness_m': float(self.wall_thickness),
                'wall_thickness_mm': float(self.wall_thickness) * 1000.0,
                'sizing_iterations': None,
                'sizing_residual_rel': None,
                'converged': True,
            }
        else:
            # YOL B — cidarın TEK kaynağı yapısal boyutlandırmadır ve ısı
            # zinciri onu TÜKETİR. İki zincir birbirine bağlıdır (ısı(t) →
            # cidar sıcaklıkları → dayanım derating'i → boyutlandırılan t),
            # bu yüzden sabit noktaya YİNELENİR. Sessiz 5 mm yok.
            #
            # Tohum: ısı verisi OLMADAN boyutlandırma (yapısal modülün kendi
            # beyanlı konservatif T_c tahmini). Tohum yalnız ilk ısı
            # koşumunun cidarını verir; yayımlanan sonuç döngünün son
            # (ısı, yapısal) çiftidir.
            tohum = _yapisal_kosumu(None, None)
            try:
                cidar_m = float(
                    tohum['chamber_analysis']['recommended_thickness']) / 1000.0
            except (KeyError, TypeError, ValueError):
                cidar_m = float('nan')
            if not (np.isfinite(cidar_m) and cidar_m > 0):
                # BEYANLI RET: boyutlandırma yoksa ısı zinciri 0,005 m'ye
                # düşmez — bir cidar uydurmak bu bulgunun ta kendisiydi.
                raise ValueError(
                    'chamber wall thickness could not be determined: no '
                    'wall_thickness was supplied and the structural sizing '
                    'did not produce a usable thickness. Supply '
                    'wall_thickness (m) explicitly; the thermal chain does '
                    'NOT fall back to a silent 5 mm default.')
            yineleme = 0
            kalinti_rel = None
            heat_transfer_results = None
            structural_results = None
            for yineleme in range(1, WALL_SIZING_MAX_ITERS + 1):
                heat_transfer_results = _isi_kosumu(cidar_m)
                structural_results = _yapisal_kosumu(heat_transfer_results,
                                                     None, cidar_m)
                cidar_yeni_m = float(
                    structural_results['chamber_analysis']
                    ['recommended_thickness']) / 1000.0
                if not (np.isfinite(cidar_yeni_m) and cidar_yeni_m > 0):
                    raise ValueError(
                        'chamber wall sizing produced a non-physical '
                        f'thickness ({cidar_yeni_m!r} m) at iteration '
                        f'{yineleme}; the run is rejected instead of '
                        'falling back to an invented wall.')
                kalinti_rel = abs(cidar_yeni_m - cidar_m) / cidar_m
                if cidar_yeni_m == cidar_m:
                    # Bit-eşit sabit nokta: yayımlanan ısı ve yapısal
                    # cidarları AYNI sayıdır (ölçüldü: örnek motor 2. adımda
                    # bit-eşit oturuyor).
                    break
                cidar_m = cidar_yeni_m
            if kalinti_rel is not None and kalinti_rel > WALL_SIZING_REL_TOL:
                # Sessiz kabul yok: kalıntı beyan edilir ve uyarılır.
                self.design_warnings.append(_w(
                    'warn.hybrid.wall_sizing_not_converged', 'warning',
                    residual_rel=float(kalinti_rel),
                    iterations=int(yineleme),
                    wall_mm=round(cidar_m * 1000.0, 3)))
            # Tek sayı: ısı zincirinin tükettiği / yapısalın boyutlandırdığı
            # cidar bundan sonra motorun cidarıdır (lüle termal profili,
            # heat-sink bloğu ve CAD hepsi bunu okur).
            self.wall_thickness = cidar_m
            self.wall_thickness_policy = {
                'policy': 'sized_by_structural_analysis',
                'wall_thickness_m': float(cidar_m),
                'wall_thickness_mm': float(cidar_m) * 1000.0,
                'sizing_iterations': int(yineleme),
                'sizing_residual_rel': (float(kalinti_rel)
                                        if kalinti_rel is not None else None),
                'converged': bool(kalinti_rel == 0.0),
            }
        self.wall_thickness_policy['basis'] = (
            'SINGLE-SOURCE wall contract (F5-1): the chamber wall thickness '
            'has exactly one owner. If the user supplies wall_thickness, '
            'that value wins - the thermal chain runs with it and the '
            'structural module verifies it (design_mode=verify). If not, '
            'the structural sizing is the source and the thermal chain '
            'CONSUMES it: heat(t) -> wall temperatures -> strength derating '
            '-> sized t, iterated to a fixed point, so the published '
            'thermal, structural and CAD walls are the same number. The '
            'former silent 0.005 m thermal default is gone; if the sizing '
            'cannot produce a wall, the run is rejected with this reason '
            'instead of inventing one.')

        # Lüle/boğaz malzemesinin termal + erozyon değerlendirmesi (v2.6.26'da
        # bağlanan üçüncü ölü girdi).
        nozzle_material_results = self._analyze_nozzle_material(
            heat_transfer_results)

        return self._compile_results(combustion_results, nozzle_results,
                                   altitude_performance, optimum_of, thrust_altitude_analysis,
                                   heat_transfer_results, structural_results,
                                   nozzle_material_results)
    
    def _calculate_c_star(self):
        """Karakteristik hızı (c*) KENDİ yanma çözücümüzle hesaplar.

        Hibrit motor termokimyası CombustionAnalyzer (Cantera gri30 dengesi +
        shifting-equilibrium isentropik üs) ile çözülür. NASA CEA'ya BAĞLI
        DEĞİLDİR — kod kendi kimyasal dengesini kurar; CEA yalnızca bağımsız
        doğrulama referansıdır. Bu çözücünün c*'ı N2O/LOX/H2O2 ile HTPB,
        paraffin, PE, PMMA, ABS, PLA için NASA CEA'ya %0-1.5 içinde doğrulanmıştır
        (tasarım O/F bandı, Pc=20 bar). Eski sürüm RocketCEA'yı doğrudan çağırıp
        sonucu c* olarak alıyordu (CEA bağımlılığı) — bu kaldırıldı.
        """
        fuel_composition = {self.fuel_type: 100.0}
        ox = getattr(self, 'oxidizer_type', None) or 'n2o'

        # T_c=None geçilir ki CombustionAnalyzer adyabatik alev sıcaklığını
        # KENDİ HP dengesinden hesaplasın (sabit tablo değeri yerine).
        self._sync_oxidizer_inlet_state()  # B16: giriş durumu yanmaya gider
        results = self.combustion_analyzer.analyze_combustion(
            fuel_composition, ox, self.OF, self.P_c, None
        )
        perf = results['performance']
        chamber = results['compositions']['chamber']

        # Gerçek denge değerlerini sınıfa aktar (shifting-eq. gamma, doğru T_c, MW)
        self.gamma = chamber['gamma']
        self.R = self.combustion_analyzer.R_universal / chamber['molecular_weight']
        self.T_c = chamber['temperature']

        # --- ÖH D17 / OH-Z5-02 (radyasyon ayağı) · IŞIYAN TÜR KESİRLERİ ----
        # ``heat_transfer_analysis`` gaz radyasyonunu (Leckner) H2O ve CO2 mol
        # kesirlerinden çözer ve sözleşmesini modül künyesinde ilan eder:
        # "RocketCEA / Cantera kompozisyonu motor_data['x_H2O'] / ['x_CO2']
        # ile geçilirse bu varsayımlar devre dışı kalır" (:79-81).
        #
        # KANAL VARDI, KAPI YOKTU. Motor dengeyi ZATEN bu satırda çözüyor ama
        # kesirleri ısı modülüne HİÇ göndermiyordu; modül her koşuda kendi
        # DEFAULT_X_H2O=0,25 / DEFAULT_X_CO2=0,15 sabitlerine düşüyor ve
        # yanıtta ``radiation_composition_source`` alanına "module default
        # (hydrocarbon/N2O class) — no x_H2O/x_CO2 was supplied" yazıyordu.
        # ÖLÇÜLDÜ (a1/once.json, ``OH_Z5_02``): HTPB/N2O O/F=6,0 dengesinde
        # gerçek kesirler x_H2O = 0,128582 ve x_CO2 = 0,061211 — yani modülün
        # kullandığı sabitlerin sırasıyla 1/1,94'ü ve 1/2,45'i. Radyasyon
        # terimi tasarım ısı akısının İÇİNE girdiği için bu, beyan kusuru
        # değil SAYI kusuruydu: yayımlanan akı, bu motorun gazının değil
        # bir sınıf ortalamasının ışımasını içeriyordu.
        #
        # FAIL-CLOSED: kesirler yalnız denge çözümü onları GERÇEKTEN
        # verdiğinde saklanır. Tür listede yoksa (mol kesri 1e-10 eşiğinin
        # altında kalıp elenmişse) o tür 0,0 ile geçer — bu bir uydurma
        # değil, çözücünün ölçtüğü değerdir. Çözüm hiç kurulamazsa alan
        # None kalır ve ısı modülüne GÖNDERİLMEZ; modül kendi varsayılanına
        # düşer ve bunu kendi künyesinde beyan eder (buradan sahte bir sayı
        # geçirmek yasak).
        _turler = chamber.get('species') or {}
        if _turler:
            self.x_H2O_chamber = float(
                (_turler.get('H2O') or {}).get('mole_fraction', 0.0) or 0.0)
            self.x_CO2_chamber = float(
                (_turler.get('CO2') or {}).get('mole_fraction', 0.0) or 0.0)
        else:
            self.x_H2O_chamber = None
            self.x_CO2_chamber = None

        c_star = perf['c_star']

        # c* validasyonu — oksitleyici-farkında fiziksel bant (v2.5.0 G4).
        # Eski tek bant (1000-1900) N2O-merkezliydi: GOX/LOX'ta meşru ~1830
        # değerler tavana dayanıyor, N2O'da 1700+ gerçek anomaliler kaçıyordu.
        band = C_STAR_PLAUSIBLE_BAND_MPS.get(str(ox).lower(),
                                             C_STAR_BAND_DEFAULT_MPS)
        if not (band[0] < c_star < band[1]):
            warnings.warn(
                f"Anormal c* değeri: {c_star:.0f} m/s "
                f"({ox} için beklenen bant {band[0]:.0f}-{band[1]:.0f} m/s)")

        # c* verimi (v2.5.0 UQ): teslim edilen c* = eta * c*_teorik. Teorik
        # değer ayrıca saklanır (raporlama). eta None ise davranış değişmez.
        self.C_star_theoretical = c_star
        # ÖH D18 fizik-a1 / F1: kayan-denge c*'ın yanında tek-γ kapalı-form
        # değeri de saklanır. Yarı-1B lüle çözücüsü kalorik mükemmel gazla
        # çalıştığı için ṁ'si P_c·A_t/c*_tek-γ'dır; iki gaz modelini
        # karşılaştıran çapraz denetimin BİLİNEN defter terimi bu orandır.
        _c_star_1g = perf.get('c_star_single_gamma')
        self.C_star_single_gamma = (float(_c_star_1g)
                                    if isinstance(_c_star_1g, (int, float))
                                    else None)
        if self.eta_c_star is not None:
            c_star = self.eta_c_star * c_star

        # D15/P1B1-06 — KAPI SIRASI. Makullük bandı yukarıda TEORİK c*'a
        # uygulanıyordu; oysa motorun geri kalanına (Isp, ṁ, boğaz alanı,
        # port çapı) giden sayı TESLİM EDİLEN c*'tır. Ölçüldü
        # (``eta_c_star=0.30``): teslim edilen c* = 398,46 m/s — bandın çok
        # altında — ve HİÇBİR kapıdan geçmiyor, tek uyarı çıkmıyordu, çünkü
        # bandı gören tek denetim η uygulanmadan ÖNCE çalışıyordu. Hüküm
        # artık iki değeri de taşır ve her koşuda yayımlanır ('pass' dâhil):
        # geçtiğini görmek, geçip geçmediğini bilmemekten farklıdır.
        self._hukum_kaydet({
            'gate': 'c_star_plausibility',
            'status': ('pass' if band[0] < c_star < band[1]
                       else 'out_of_band'),
            'quantity': 'c_star_delivered',
            'value': float(c_star),
            'c_star_theoretical': float(self.C_star_theoretical),
            'eta_c_star': (None if self.eta_c_star is None
                           else float(self.eta_c_star)),
            'band': [float(band[0]), float(band[1])],
            'unit': 'm/s',
            'oxidizer': str(ox).lower(),
            'basis': ('oxidiser-aware plausibility band for the characteristic '
                      'velocity. The band is checked on the DELIVERED c* '
                      '(after the c* efficiency), because that is the number '
                      'the rest of the motor is sized from.'),
        })

        return c_star

    # ------------------------------------------------------------------
    # Kitap uyum B16 (Ö-1, §28) — oksitleyici GİRİŞ DURUMU
    # ------------------------------------------------------------------
    def _oxidizer_inlet_request(self):
        """(sıcaklık [K], faz) — yanma çözücüsüne giden giriş durumu.

        TEK KAYNAK: sıcaklık ``self.tank_temperature``dır; verilmemişse
        ``TANK_TEMPERATURE_DEFAULT_K`` (enjektör, tank blowdown ve geçici
        çözücünün okuduğu AYNI sabit). Zaman çözümlü blowdown kipinde bu
        sıcaklık İLK tank sıcaklığıdır; giriş entalpisi yanma boyunca sabit
        tutulur (zamanla değişen giriş entalpisi bu kalemin işi değil —
        devir listesinde).
        """
        T = (float(self.tank_temperature)
             if getattr(self, 'tank_temperature', None) is not None
             else TANK_TEMPERATURE_DEFAULT_K)
        return T, getattr(self, 'oxidizer_phase', None)

    def _oxidizer_inlet_cache_key(self):
        """Önbellek anahtarı için giriş durumu imzası (N₂O dışında sabit)."""
        ox = (getattr(self, 'oxidizer_type', None) or 'n2o').lower()
        if ox != 'n2o':
            return ('fixed_reference', ox)
        from hrma.engines.oxidizer_inlet import inlet_state_signature
        T, faz = self._oxidizer_inlet_request()
        return inlet_state_signature(T, faz)

    def _sync_oxidizer_inlet_state(self):
        """Motorun giriş durumunu yanma çözücüsüne iletir (her çağrıdan önce).

        Analizör UQ'da örnekler arasında PAYLAŞILABİLDİĞİ için durum her
        yanma çağrısından hemen önce yeniden ayarlanır (aynıysa maliyetsiz).
        Geçersiz giriş (ör. kritik nokta üstü sıvı) ``ValueError`` ile
        ADIYLA reddedilir; yaklaşık değer üretilmez.
        """
        ox = (getattr(self, 'oxidizer_type', None) or 'n2o').lower()
        if ox != 'n2o':
            return
        T, faz = self._oxidizer_inlet_request()
        try:
            self.combustion_analyzer.set_oxidizer_inlet_state(T, faz)
        except ValueError as exc:
            raise ValueError(
                f'tank_temperature = {T:.2f} K cannot be used as the N2O '
                f'inlet state: {exc}') from None

    def apply_oxidizer_inlet_state_to(self, analyzer):
        """Motorun giriş durumunu BAĞIMSIZ bir analizöre iletir (2. tur Ş-7).

        Aynı istekte motorun yanında kendi ``CombustionAnalyzer``ını kuran
        yan çözümler (``/calculate`` yanma grafiği ve O/F taraması) motorla
        AYNI giriş durumunu kullanmalıdır; aksi hâlde grafik ana sonuçtan
        ayrışır. Tek kaynak ``_oxidizer_inlet_request``tır. N₂O dışında
        hiçbir şey yapılmaz.

        Returns:
            bool — analizörün durumu varsayılan DIŞINA ayarlandı mı (çağıran,
            modül düzeyi önbellekli yolları yalnız bu durumda atlar).
        """
        ox = (getattr(self, 'oxidizer_type', None) or 'n2o').lower()
        if ox != 'n2o':
            return False
        T, faz = self._oxidizer_inlet_request()
        analyzer.set_oxidizer_inlet_state(T, faz)
        return not analyzer.oxidizer_inlet_is_default()

    def _oxidizer_inlet_state_block(self):
        """Yanıttaki ``oxidizer_inlet_state`` beyanı (B16)."""
        ox = (getattr(self, 'oxidizer_type', None) or 'n2o').lower()
        self._sync_oxidizer_inlet_state()
        blok = dict(self.combustion_analyzer.oxidizer_inlet_state(ox))
        kaynak = getattr(self, '_combustion_temperature_source', None)
        blok['chamber_temperature_source'] = kaynak
        blok['entered_equilibrium'] = kaynak == 'equilibrium'
        if kaynak != 'equilibrium':
            blok['note'] = (
                'the chamber temperature of this run did not come from the '
                'enthalpy-balanced equilibrium (source: %s), so the inlet '
                'enthalpy declared here did not enter it.' % (kaynak,))
        if ox == 'n2o':
            blok['inlet_temperature_source'] = (
                'user input (tank_temperature)'
                if getattr(self, 'tank_temperature', None) is not None
                else f'default {TANK_TEMPERATURE_DEFAULT_K} K saturated-'
                     f'storage assumption (same default the injector and '
                     f'tank blowdown use)')
            blok['inlet_phase_source'] = ('user input (oxidizer_phase)'
                                    if self._oxidizer_phase_given
                                    else 'default (saturated liquid)')
        return blok

    def _perf_grid_c_star(self, node):
        """O/F ızgarasının ``node`` düğümündeki teslim edilen c* [m/s].

        Düğüm başına TEK denge çözümü yapılır ve sonuç düğüm İNDİSİYLE
        (tam sayı) önbelleğe alınır. Anahtarın tam sayı olması bilinçlidir:
        kayan noktalı O/F anahtarı 2.3000000000000003 gibi ikizler üretip aynı
        düğümü iki kez çözdürebiliyordu.

        Denge çözülemezse tasarım noktası c*'ına düşülür ve bu düşüş
        ``_perf_solver_failed`` ile kaydedilir; ara değerleme teşhis bloğu bunu
        beyan eder (sessiz yedeğe düşme yasak).
        """
        # Kitap uyum B16: anahtar GİRİŞ DURUMUNU da taşır. Düğüm c*'ı reaktan
        # entalpisine bağlıdır; tank sıcaklığı ya da faz değişirse eski
        # düğüm değeri BAYATTIR ve geri verilmez (bekçi:
        # tests/test_kitap_p1a.py).
        self._sync_oxidizer_inlet_state()
        anahtar = (self._oxidizer_inlet_cache_key(), node)
        cached = self._perf_cache.get(anahtar)
        if cached is not None:
            return cached
        of_node = max(node * OF_PERF_GRID_STEP, OF_PERF_MIN)
        try:
            results = self.combustion_analyzer.analyze_combustion(
                {self.fuel_type: 100.0},
                getattr(self, 'oxidizer_type', None) or 'n2o',
                of_node, self.P_c, None
            )
            c_node = float(results['performance']['c_star'])
            # c* verimi tasarım noktasıyla tutarlı uygulanır (v2.5.0 UQ)
            if self.eta_c_star is not None:
                c_node = self.eta_c_star * c_node
        except Exception:
            c_node = float(getattr(self, 'C_star', None) or 1500.0)
            self._perf_solver_failed = True
        self._perf_cache[anahtar] = c_node
        return c_node

    def _instantaneous_performance(self, of_ratio):
        """Anlık O/F'den anlık (c*, Isp) döndürür (denetim bulgusu #2; A9).

        O/F kayması performansa yansıtılır: yanma çözücü her O/F için c*'ı
        verir; Isp ise mevcut CF (nozul geometrisi sabit) ile c*'tan ölçeklenir
        (Isp = CF · c* / g0). CF burada O/F ile küçük değiştiği için tasarım
        CF'si kullanılır — bu, c*'taki (çok daha büyük) O/F duyarlılığını
        yakalamak için yeterlidir ve nozul yeniden çözümünden kaçınır. Bu sınır
        ``of_shift`` bloğunun kendi beyanında yazılıdır.

        YÖNTEM (v2.6.27, A9): c*(O/F) tablosu ``OF_PERF_GRID_STEP`` adımlı
        düzgün bir ızgarada TEK KEZ çözülür, ara değer o aralığın iki düğümü
        arasında DOĞRUSAL ARA DEĞERLEMEYLE bulunur. Önceki sürüm en yakın
        düğüme yuvarlıyordu: aynı düğüm sayısıyla (aynı maliyetle) c*'ta
        ±%0,26'ya varan hata ve Isp(t) eğrisinde ızgara geçişlerinde basamak
        üretiyordu (ölçüm OF_PERF_GRID_STEP yorumunda). Ara değerleme hatası
        UYDURULMAZ, ölçülür: ``_of_interpolation_diagnostics``.

        c* düğümlerde saklanır, Isp saklanmaz: Isp = CF·c*/g0 olduğundan
        önbelleğe alınmış bir Isp, sonradan değişen bir CF ile tutarsız
        kalabilirdi.
        """
        of = float(of_ratio)
        if not np.isfinite(of):
            of = float(self.OF)
        of = max(of, OF_PERF_MIN)

        # Katedilen O/F aralığı: ara değerleme hatası TAM BU aralıkta ölçülür
        # (hiç uğranmamış bir O/F bandında hata beyan etmek anlamsızdır).
        if of < self._perf_of_min:
            self._perf_of_min = of
        if of > self._perf_of_max:
            self._perf_of_max = of

        lo_node = int(np.floor(of / OF_PERF_GRID_STEP))
        c_lo = self._perf_grid_c_star(lo_node)
        c_hi = self._perf_grid_c_star(lo_node + 1)
        w = (of - lo_node * OF_PERF_GRID_STEP) / OF_PERF_GRID_STEP
        cstar_inst = c_lo + (c_hi - c_lo) * w

        # CF tasarım değeri (calculate() önce CF'yi hesaplar); yoksa nominal.
        cf = getattr(self, 'CF', None)
        if cf is None or not np.isfinite(cf):
            cf = 1.5  # tipik hibrit deniz seviyesi CF (Sutton & Biblarz 9th ed.)
        return cstar_inst, cf * cstar_inst / self.g0

    def _of_interpolation_diagnostics(self):
        """c*(O/F) ara değerlemesinin ÖLÇÜLEN hatası (yol haritası A9-2).

        Yöntem: katedilen O/F aralığındaki ızgara aralıklarının ORTASINDA
        (doğrusal ara değerlemenin en kötü konumu) tam denge çözümü yapılır ve
        ara değerlemeyle karşılaştırılır. Hata beyan edilen sınırla birlikte
        yayımlanır; sınır aşılırsa durum açıkça 'exceeds_declared_bound' olur.

        Hiç anlık performans değerlendirilmediyse (track_performance kapalı)
        ölçülecek bir şey yoktur: sayı UYDURULMAZ, NOT_MODELLED döner.
        """
        basis = (
            'measured, not assumed: the equilibrium c*(O/F) table is solved on '
            'a uniform O/F grid of step {step} and read back by piecewise-'
            'linear interpolation; Isp(t) = CF_design * c*(t) / g0. The error '
            'reported here is the relative difference between the interpolated '
            'c* and a full equilibrium solution at the mid-point of grid '
            'intervals (the worst position for linear interpolation), sampled '
            'inside the O/F range the burn actually traverses.'
        ).format(step=OF_PERF_GRID_STEP)
        lo = self._perf_of_min
        hi = self._perf_of_max
        if not (np.isfinite(lo) and np.isfinite(hi)):
            return {
                'status': 'NOT_MODELLED',
                'basis': basis,
                'reason': ('no instantaneous performance point was evaluated '
                           'in this run (track_performance is off), so there '
                           'is no interpolation to measure.'),
                'grid_step_of': OF_PERF_GRID_STEP,
                'error_bound_pct': OF_PERF_INTERP_ERROR_BOUND_PCT,
            }

        node_lo = int(np.floor(lo / OF_PERF_GRID_STEP))
        node_hi = int(np.floor(hi / OF_PERF_GRID_STEP))
        aralikar = list(range(node_lo, max(node_hi, node_lo) + 1))
        if len(aralikar) > OF_PERF_ERROR_PROBE_COUNT:
            adim = len(aralikar) / float(OF_PERF_ERROR_PROBE_COUNT)
            aralikar = [aralikar[int(k * adim)]
                        for k in range(OF_PERF_ERROR_PROBE_COUNT)]

        hatalar = []
        for node in aralikar:
            of_probe = (node + 0.5) * OF_PERF_GRID_STEP
            if of_probe < OF_PERF_MIN:
                continue
            try:
                self._sync_oxidizer_inlet_state()  # B16
                results = self.combustion_analyzer.analyze_combustion(
                    {self.fuel_type: 100.0},
                    getattr(self, 'oxidizer_type', None) or 'n2o',
                    of_probe, self.P_c, None
                )
                c_exact = float(results['performance']['c_star'])
            except Exception:
                continue
            if self.eta_c_star is not None:
                c_exact = self.eta_c_star * c_exact
            if not np.isfinite(c_exact) or c_exact <= 0:
                continue
            c_interp = 0.5 * (self._perf_grid_c_star(node)
                              + self._perf_grid_c_star(node + 1))
            hatalar.append(abs(c_interp / c_exact - 1.0) * 100.0)

        if not hatalar:
            return {
                'status': 'NOT_MODELLED',
                'basis': basis,
                'reason': ('the equilibrium solver could not be evaluated at '
                           'any probe point, so the interpolation error was '
                           'not measured; it is not estimated either.'),
                'grid_step_of': OF_PERF_GRID_STEP,
                'of_range_traversed': [float(lo), float(hi)],
                'error_bound_pct': OF_PERF_INTERP_ERROR_BOUND_PCT,
            }

        en_buyuk = float(max(hatalar))
        return {
            'status': 'modelled',
            'basis': basis,
            'method': ('piecewise-linear interpolation of the equilibrium '
                       'c*(O/F) table on a uniform grid'),
            'grid_step_of': OF_PERF_GRID_STEP,
            'grid_nodes_solved': len(self._perf_cache),
            'of_range_traversed': [float(lo), float(hi)],
            'error_probe_count': len(hatalar),
            'error_max_pct': en_buyuk,
            'error_mean_pct': float(sum(hatalar) / len(hatalar)),
            'error_bound_pct': OF_PERF_INTERP_ERROR_BOUND_PCT,
            'within_declared_bound': bool(
                en_buyuk <= OF_PERF_INTERP_ERROR_BOUND_PCT),
            'error_status': ('within_declared_bound'
                             if en_buyuk <= OF_PERF_INTERP_ERROR_BOUND_PCT
                             else 'exceeds_declared_bound'),
            'equilibrium_solver_fallback_used': bool(
                getattr(self, '_perf_solver_failed', False)),
        }


    def _calculate_expansion_ratio(self):
        """Calculate optimal expansion ratio using correct isentropic formula

        D15/P1B1-08 — VAKUM KAPISI. Bu fonksiyon ``P_e = P_a`` eşleşmesini
        çözer; ``P_a = 0`` iken eşleşen genişleme oranı SINIRSIZDIR (bir
        vakum lülesi hiçbir sonlu ε'da tam genişlemez), yani çözülecek bir
        sayı yoktur. Eski kod bunu ``ZeroDivisionError`` ile bildiriyordu:
        istisna ``ValueError`` olmadığı için girdi hatası sınıfına düşmüyor
        ve kullanıcı hiçbir alan adı geçmeyen "float division by zero"
        mesajını görüyordu. Aynı koşuda motorun öteki yarısı
        (``_apply_separation_limit``) vakumu ADIYLA işliyor
        ("separation is undefined at zero ambient pressure") — yani model
        vakumu tanıyor, yalnız bu kapı yoktu.

        Uydurulmuş bir tavan (ör. ε = 250) YAZILMAZ: fail-closed, alan adıyla
        reddedilir. Kullanıcı ``expansion_ratio`` verdiğinde bu fonksiyon
        zaten çağrılmaz, dolayısıyla vakum tasarımı yapılabilir hâlde kalır
        (ölçüldü: P_a=0 + ε=8 -> C_F=1,6692, Isp=226,07 s).
        """
        if not (self.P_a is not None and np.isfinite(self.P_a)
                and self.P_a > 0.0):
            raise ValueError(
                "'expansion_ratio' is required when 'atmospheric_pressure' is "
                f"{self.P_a} bar: the pressure-matched expansion ratio solves "
                "P_e = P_a, and that ratio grows without bound as the ambient "
                "pressure goes to zero, so there is no optimum to compute. "
                "Enter the nozzle area ratio you want to design for (a vacuum "
                "nozzle is sized by mass and envelope, not by pressure "
                "matching), or give a positive ambient pressure.")
        pressure_ratio = self.P_c / self.P_a  # Pc/Pe
        gamma = self.gamma
        
        # Correct isentropic formula: optimal expansion for Pe = Pa
        # Calculate Mach number from pressure ratio: Pc/Pe = [1 + (γ-1)/2 * Me²]^(γ/(γ-1))
        # Then area ratio: ε = (1/Me) * [(2/(γ+1)) * (1 + (γ-1)/2 * Me²)]^((γ+1)/(2*(γ-1)))
        
        # Iterative solution: find Mach number
        from scipy.optimize import fsolve
        
        def pressure_mach_relation(M):
            return (1 + (gamma - 1) / 2 * M**2)**(gamma / (gamma - 1)) - pressure_ratio
        
        # Initial guess: high Mach number
        M_exit_guess = np.sqrt(2 / (gamma - 1) * (pressure_ratio**((gamma - 1) / gamma) - 1))
        M_exit = fsolve(pressure_mach_relation, max(1.1, M_exit_guess))[0]
        
        # Calculate area ratio (correct isentropic formula)
        epsilon = (1 / M_exit) * ((2 / (gamma + 1)) * (1 + (gamma - 1) / 2 * M_exit**2))**((gamma + 1) / (2 * (gamma - 1)))
        
        # Eslenik (matched, Pe = Pa) genlesme orani oldugu gibi kullanilir
        # (denetim bulgusu #8): eski max(4, ...) tabani, Pc/Pa orani kucuk
        # motorlarda nozulu tasarim noktasinda asiri genlesmis hale getiriyordu.
        # Alt sinir yalnizca matematiksel gecerlilik icindir (suporsonik nozul
        # icin Ae/At > 1); ust sinir 250 vakum nozullari icin pratik limittir.
        # Kullanici epsilon verirse bu fonksiyon zaten cagrilmaz (calculate()).
        return max(1.01, min(epsilon, 250))

    def _resolve_divergence_efficiency(self, epsilon=None):
        """Diverjans (yarım açı) verimi λ — TEK tanım noktası.

        Diverjans duzeltme faktorleri (hrma.constants'tan):
            bell      -> 0.985 (Rao optimize)
            parabolic -> 0.975
            conical   -> 0.983 (15 deg, (1+cos(15°))/2 = 0.98296)
        Onceki kodda conical icin 0.955 yaziliyordu; bu 30 deg'lik kabaca bir
        degerdi ve (1+cos(15°))/2 formuluyle uyumsuzdu. Sutton & Biblarz 9th
        ed. Tablo 3-3 ile uyumlu olarak 0.983 kullanilir.

        D15/P1B1-02 — bu fonksiyonun VAR OLMA SEBEBİ. λ eskiden yalnız
        ``_calculate_thrust_coefficient`` gövdesinde türetiliyordu ve
        ``self.lambda_eff`` orada atanıyordu. Kullanıcı ``thrust_coefficient``
        verdiğinde ``calculate()`` o fonksiyonu ATLIYOR (``if self.CF is
        None``), dolayısıyla ``self.lambda_eff`` hiç var olmuyordu ve
        ``_compile_results`` (``nozzle_angles.divergence_efficiency``)
        ``AttributeError`` fırlatıyordu. Ölçüldü: CF ∈ {1,2; 1,4; 1,6; 1,8;
        2,0} beşte beş çöküyor, ``isinstance(exc, ValueError)`` False olduğu
        için kullanıcı hiçbir alan adı geçmeyen bir mesaj görüyordu — oysa
        alan ``PARAMETRIC_NON_NEGATIVE_PARAMS`` üyesidir, yani
        ``/parametric-analysis`` bu parametreyi süpürmeye açıkça izin verir.
        λ artık kurucuda çözülür; lülenin geometrik verimi, C_F'in nereden
        geldiğinden BAĞIMSIZ bir donanım özelliğidir.
        """
        # --- ÖH D21 / P15B1-04 · λ'NIN TEK KAYNAĞI ---------------------
        # Buradaki üç katalog sabiti (LAMBDA_BELL / LAMBDA_PARABOLIC /
        # LAMBDA_CONICAL_15DEG) aynı lülenin İKİNCİ λ'sıydı: lüle paneli
        # λ'yı konturun kendi açısından hesaplıyor (Rao %80 tablosu, ε'ye
        # bağlı), manşet ise ε'den bağımsız sabiti okuyordu. ÖLÇÜLDÜ
        # (docs/scofield/raw/OH/D21/hibrit/a1/once_lambda.json): 3 tip × 8 ε
        # = 24 noktanın 24'ü ayrışıyor, en büyük bağıl fark %2,0253; uçtan
        # uca 4 koşumun 4'ünde ``thrust_coefficient_loss_set_consistency``
        # kapısı ``out_of_band`` (bant %0,001, ölçülen %0,0038…%0,2880) ve
        # manşet Isp ile panel Isp'si %0,0712…%0,3627 ayrışıyordu.
        # λ artık panelin kullandığı AYNI geometrik kaynaktan gelir.
        #
        # ε bu noktada henüz çözülmemiş olabilir (kurucuda çağrılıyor,
        # ``expansion_ratio`` verilmediyse ``self.epsilon`` None). O durumda
        # geometri sorulamaz; katalog sabiti KÜNYELİ yedek olarak kalır ve
        # ε çözülür çözülmez λ yeniden çözülür (calculate() içinde).
        tip = (self.nozzle_type if self.nozzle_type in ('bell', 'parabolic')
               else 'conical')
        eps = self.epsilon if epsilon is None else epsilon
        try:
            eps = float(eps)
        except (TypeError, ValueError):
            eps = None
        if eps is not None and np.isfinite(eps) and eps > 1.0:
            self.lambda_basis = 'contour_geometry'
            return NozzleDesigner.divergence_efficiency_from_expansion(
                tip, eps)
        self.lambda_basis = 'catalogue_constant_expansion_ratio_unresolved'
        if tip == 'bell':
            return LAMBDA_BELL
        if tip == 'parabolic':
            return LAMBDA_PARABOLIC
        return LAMBDA_CONICAL_15DEG

    def _calculate_thrust_coefficient(self, epsilon=None, chamber_pressure=None):
        """Calculate thrust coefficient using isentropic nozzle flow (Sutton Eq. 3-30).

        Exit Mach number is solved from the area-Mach relation via Brent's method,
        then Pe is computed from isentropic pressure relation.  The old code set
        Pe = Pa (perfect expansion) which zeroed out the pressure thrust term.

        v2.6.2 (bulgu F047): epsilon / chamber_pressure DIŞARIDAN verilebilir.
        Boğaz erozyonu At'yi büyüttüğünde geometri (Ae sabit) ε'yi ve kütle
        dengesi Pc'yi değiştirir; CF bu yeni noktada YENİDEN hesaplanmalıdır.
        Argüman verilmezse tasarım noktası (self.epsilon, self.P_c) kullanılır
        ve davranış birebir eskisiyle aynı kalır.
        """
        # D15/P1B1-02: λ artık BURADA türetilmiyor; tek kaynak
        # ``_resolve_divergence_efficiency`` (kurucuda da çağrılır, böylece
        # kullanıcı CF verip bu fonksiyon hiç çalışmadığında da
        # ``self.lambda_eff`` vardır).
        lambda_eff = self._resolve_divergence_efficiency()

        gamma = self.gamma
        eps = self.epsilon if epsilon is None else float(epsilon)
        P_c = self.P_c if chamber_pressure is None else float(chamber_pressure)

        # --- Step 1: Solve exit Mach number from area-Mach relation ---
        # A/A* = (1/Me) * [ (2/(gamma+1)) * (1 + (gamma-1)/2 * Me^2) ]^((gamma+1)/(2*(gamma-1)))
        gp1 = gamma + 1
        gm1 = gamma - 1
        exponent = gp1 / (2.0 * gm1)

        def area_mach_residual(M):
            """Returns A/A*(M) - epsilon.  Root at M = Me (supersonic branch)."""
            return (1.0 / M) * ((2.0 / gp1) * (1.0 + 0.5 * gm1 * M**2))**exponent - eps

        # Supersonic root lies in (1, ~large).  Upper bound from epsilon.
        # For very high expansion ratios the Mach number can be large;
        # eps < 250 (clamped elsewhere) so Me < ~25 is safe.
        try:
            Me = brentq(area_mach_residual, 1.0 + 1e-6, 50.0, xtol=1e-10, maxiter=200)
        except ValueError:
            # Fallback: if brentq fails (e.g. epsilon < 1), use subsonic solution
            try:
                Me = brentq(area_mach_residual, 1e-4, 1.0 - 1e-6, xtol=1e-10, maxiter=200)
            except ValueError:
                Me = 1.0  # sonic -- degenerate case

        # --- Step 2: Exit pressure from isentropic relation ---
        # Pe = Pc * (1 + (gamma-1)/2 * Me^2) ^ (-gamma/(gamma-1))
        # D15/P1B1-05: BURADA ``P_c`` (yerel) okunur, ``self.P_c`` DEĞİL.
        # Yerel değer 2577'de yazılıyor ama üç bağıntının hiçbiri onu
        # okumuyordu (AST: 1 yazma / 0 okuma), yani ``chamber_pressure=``
        # argümanı hem ölü hem bozuktu: docstring'in vaat ettiği boğaz
        # erozyonu eşlemesi bağlandığı gün CF sessizce tasarım noktasının
        # değerini verecekti (ölçüldü: Pc 20→5 bar süpürmesinde ürün CF
        # 1,41327 sabit, el hesabı 1,3728→0,7656; sapma %2,95→%84,60).
        Pe = P_c * (1.0 + 0.5 * gm1 * Me**2) ** (-gamma / gm1)

        # --- Step 3: Thrust coefficient (Sutton Eq. 3-30) ---
        # CF = lambda * sqrt( (2*gamma^2/(gamma-1)) * (2/(gamma+1))^((gamma+1)/(gamma-1))
        #                      * (1 - (Pe/Pc)^((gamma-1)/gamma)) )
        #      + (Pe - Pa) * epsilon / Pc
        gamma_term = 2.0 * gamma**2 / gm1
        isentropic_term = (2.0 / gp1) ** (gp1 / gm1)
        pressure_ratio_term = 1.0 - (Pe / P_c) ** (gm1 / gamma)

        CF_momentum = lambda_eff * np.sqrt(gamma_term * isentropic_term * pressure_ratio_term)
        CF_pressure = (Pe - self.P_a) * eps / P_c

        CF_ekli = CF_momentum + CF_pressure
        return self._apply_separation_limit(CF_ekli, eps, Pe, lambda_eff,
                                            chamber_pressure=P_c)

    # ------------------------------------------------------------------
    # Aşırı genişleme / akış ayrılması (v2.6.27 B1, kalem 3)
    # ------------------------------------------------------------------
    @staticmethod
    def _mach_from_pressure_ratio(p_over_p0, gamma):
        """İzentropik p/p0 -> Mach (kapalı form, kök arama YOK).

        M = sqrt( 2/(γ-1) · ((p0/p)^((γ-1)/γ) − 1) ).  p/p0 ∈ (0, 1] dışıysa
        akış tanımsızdır; NaN üretmek yerine None döner (çağıran karar verir).
        """
        if not (p_over_p0 > 0.0) or p_over_p0 > 1.0:
            return None
        return float(np.sqrt(2.0 / (gamma - 1.0)
                             * ((1.0 / p_over_p0) ** ((gamma - 1.0) / gamma)
                                - 1.0)))

    @staticmethod
    def _area_ratio_from_mach(M, gamma):
        """Süpersonik dal alan oranı A/A* (kapalı form)."""
        if M is None or not (M > 0.0):
            return None
        return float((1.0 / M)
                     * ((2.0 / (gamma + 1.0))
                        * (1.0 + 0.5 * (gamma - 1.0) * M * M))
                     ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))))

    def _cf_attached(self, eps, gamma, lambda_eff, chamber_pressure=None):
        """Verilen ε'da EKLİ AKIŞ C_F'i ve çıkış basıncı — tek formül noktası.

        D15/P1B1-05: ``chamber_pressure`` verilirse oda basıncı O NOKTADAN
        alınır (boğaz erozyonu eşlemesi). Verilmezse tasarım noktası
        (``self.P_c``) kullanılır ve davranış birebir eskisiyle aynıdır.
        """
        pr = self._pressure_ratio_at_area_ratio(eps, gamma)
        if pr is None:
            return None, None
        P_c = self.P_c if chamber_pressure is None else float(chamber_pressure)
        Pe = P_c * pr
        mom = lambda_eff * np.sqrt(
            2.0 * gamma ** 2 / (gamma - 1.0)
            * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
            * (1.0 - pr ** ((gamma - 1.0) / gamma)))
        return float(mom + (Pe - self.P_a) * eps / P_c), float(Pe)

    def _pressure_ratio_at_area_ratio(self, eps, gamma):
        """ε -> süpersonik dal P_e/P_c (kök arama; başarısızsa None)."""
        if not (eps and np.isfinite(eps) and eps > 1.0):
            return None
        gp1, gm1 = gamma + 1.0, gamma - 1.0
        ust = gp1 / (2.0 * gm1)

        def kalinti(M):
            return (1.0 / M) * ((2.0 / gp1) * (1.0 + 0.5 * gm1 * M * M)) ** ust - eps

        try:
            Me = brentq(kalinti, 1.0 + 1e-9, 100.0, xtol=1e-12, maxiter=300)
        except ValueError:
            return None
        return float((1.0 + 0.5 * gm1 * Me * Me) ** (-gamma / gm1))

    def _apply_separation_limit(self, cf_attached, eps, Pe, lambda_eff,
                                chamber_pressure=None):
        """Ekli-akış C_F'ini GEÇERLİLİK ARALIĞI ile sınırlar.

        SORUN (ölçüldü, v2.6.27 B1 öncesi; Pc = 20 bar, deniz seviyesi,
        HTPB/N2O):
            ε=8  -> C_F=1,2677  Isp=171,3 s
            ε=20 -> C_F=0,7615  Isp=102,9 s
            ε=30 -> C_F=0,2948  Isp= 39,8 s
            ε=35 -> C_F=0,0564  Isp=  7,6 s   (HTTP 200 dönüyordu)
            ε=36 -> C_F=0,0084  Isp=  1,1 s   -> ardından NaN -> anlamsız 400
            ε=40 -> C_F=-0,1840             (NEGATİF itki katsayısı)
        Bu sayılar Sutton Eş. 3-30'un doğru aritmetiğidir; yanlış olan
        formülün GEÇERLİ OLMADIĞI yerde uygulanmasıdır. Aşırı genişlemiş
        lülede sınır tabaka ayrılır: akış çıkışa kadar dolu akmaz, ayrılma
        istasyonundan sonrası ortam basıncını görür ve itkiye katkı vermez.
        Ayrılmış lülenin gerçek C_F'i, aynı lülenin AYRILMA İSTASYONUNDA
        kesilmiş hâlinin C_F'inden AŞAĞI inemez — çünkü genişleyen kısmın
        kalanı fiilen yoktur. Dolayısıyla ekli-akış değeri o noktadan sonra
        fiziksel ALT SINIRIN altına düşen bir tahmindir.

        UYGULANAN SINIR: P_e < k·P_a ise (Summerfield, k = 0,40 — tek tanım
        noktası hrma/flow/separation.SUMMERFIELD_FACTOR_DEFAULT) ayrılma
        öngörülür; ε_sep, P_e = k·P_a veren alan oranıdır ve C_F, ε_sep'teki
        değere taban yapılır. Ayrılma öngörülmeyen tasarımlarda (ε ≤ ε_sep)
        HİÇBİR SAYI DEĞİŞMEZ — eski davranışla bit-özdeştir.

        Kaynak: Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl.
        3.4 (aşırı genişleme ve ayrılma); Summerfield, Foster & Swan, Jet
        Propulsion 1954. Sıvı motorda aynı ölçüt yalnız UYARI üretiyor
        (liquid_rocket_engine.NOZZLE_SEPARATION_PRESSURE_RATIO); hibritte
        uyarı da verilir, ayrıca ekli-akış değeri sınırlanır — çünkü hibrit
        zincirinde C_F doğrudan Isp'ye, oradan ṁ ve port çapına gidiyor ve
        sınırsız C_F ölçülebilir saçmalık üretiyordu (port çapı ε=35'te
        243 mm'ye fırlıyordu).
        """
        gamma = self.gamma
        # D15/P1B1-05: ekranın ve ε_sep'in oda basıncı, C_F'in hesaplandığı
        # NOKTANIN basıncıdır (erozyon eşlemesinde tasarım noktası değil).
        P_c = self.P_c if chamber_pressure is None else float(chamber_pressure)
        self.cf_attached_flow = float(cf_attached)
        self.cf_separation_limited = False
        ekran = {
            'expansion_ratio': float(eps),
            'exit_pressure_bar': float(Pe),
            'ambient_pressure_bar': float(self.P_a),
            'summerfield_factor': float(SUMMERFIELD_FACTOR_DEFAULT),
            'cf_attached_flow': float(cf_attached),
            'criterion': 'summerfield',
            'basis': (
                'over-expansion screen: the attached-flow thrust coefficient '
                '(Sutton Eq. 3-30) is only valid while the nozzle flows full. '
                'Summerfield predicts boundary-layer separation once '
                'P_e < k*P_a with k = '
                f'{SUMMERFIELD_FACTOR_DEFAULT} (source of the constant: '
                'hrma/flow/separation.py). Beyond that station the divergent '
                'section no longer contributes thrust, so the attached-flow '
                'value is BELOW what the hardware can physically deliver and '
                'is floored at the separation-station value.'),
        }

        # Vakumda (P_a = 0) ayrılma tanımsızdır — ölçüt uygulanmaz.
        if not (self.P_a and self.P_a > 0.0):
            ekran['separation_predicted'] = False
            ekran['not_applicable_reason'] = (
                'separation is undefined at zero ambient pressure (vacuum)')
            ekran['cf_used'] = float(cf_attached)
            self.nozzle_expansion_screen = ekran
            return self._gate_finite_cf(cf_attached, ekran)

        p_sep = SUMMERFIELD_FACTOR_DEFAULT * self.P_a          # bar
        ekran['separation_pressure_bar'] = float(p_sep)

        # ε_sep: P_e = p_sep veren alan oranı (kapalı form, kök arama yok).
        M_sep = self._mach_from_pressure_ratio(p_sep / P_c, gamma)
        eps_sep = self._area_ratio_from_mach(M_sep, gamma)
        ekran['separation_limit_expansion_ratio'] = (
            float(eps_sep) if eps_sep else None)

        if Pe >= p_sep or eps_sep is None or not (eps > eps_sep):
            ekran['separation_predicted'] = False
            ekran['cf_used'] = float(cf_attached)
            self.nozzle_expansion_screen = ekran
            return self._gate_finite_cf(cf_attached, ekran)

        # Ayrılma öngörüldü: uyar (sayı değişmese bile kullanıcı bilmeli).
        ekran['separation_predicted'] = True
        self.design_warnings.append(_w(
            'warn.hybrid.nozzle_flow_separation', 'critical',
            eps=round(float(eps), 2),
            eps_separation_limit=round(float(eps_sep), 2),
            pe_bar=round(float(Pe), 4),
            pa_bar=round(float(self.P_a), 4),
            factor=float(SUMMERFIELD_FACTOR_DEFAULT)))

        cf_sep, pe_sep = self._cf_attached(eps_sep, gamma, lambda_eff,
                                           chamber_pressure=P_c)
        ekran['cf_at_separation_limit'] = (
            float(cf_sep) if cf_sep is not None else None)
        if cf_sep is None or not np.isfinite(cf_sep):
            ekran['cf_used'] = float(cf_attached)
            ekran['floor_applied'] = False
            ekran['floor_not_applied_reason'] = (
                'the separation-station area ratio could not be solved, so no '
                'floor is invented; the attached-flow value is published as '
                'is and the separation warning stands')
            self.nozzle_expansion_screen = ekran
            return self._gate_finite_cf(cf_attached, ekran)

        if cf_attached < cf_sep:
            self.cf_separation_limited = True
            ekran['floor_applied'] = True
            ekran['cf_used'] = float(cf_sep)
            ekran['cf_shortfall_pct'] = float(
                (cf_attached / cf_sep - 1.0) * 100.0)
            self.nozzle_expansion_screen = ekran
            return self._gate_finite_cf(cf_sep, ekran)

        ekran['floor_applied'] = False
        ekran['cf_used'] = float(cf_attached)
        self.nozzle_expansion_screen = ekran
        return self._gate_finite_cf(cf_attached, ekran)

    @staticmethod
    def _gate_finite_cf(cf, ekran):
        """C_F sonluluk/pozitiflik kapısı — NaN aşağı akmaz.

        ÖLÇÜLDÜ: ε ≥ 36'da C_F sıfıra yaklaşıp negatife geçiyor, Isp ile
        bölünen ṁ patlıyor ve çözüm ilerideki bir ``int(NaN)`` çağrısında
        ``cannot convert float NaN to integer`` diye ölüyordu — kullanıcıya
        giden 400 mesajı sorunun ne olduğu hakkında hiçbir şey söylemiyordu.
        Kapı burada, sayının doğduğu yerde kurulur ve NEDENİ söyler.
        """
        if cf is not None and np.isfinite(cf) and cf > 0.0:
            return float(cf)
        eps = ekran.get('expansion_ratio')
        pe = ekran.get('exit_pressure_bar')
        pa = ekran.get('ambient_pressure_bar')
        eps_lim = ekran.get('separation_limit_expansion_ratio')
        oneri = (f' At this chamber pressure the flow separation limit is '
                 f'eps <= {eps_lim:.2f}.' if eps_lim else '')
        raise ValueError(
            f'The nozzle is so heavily over-expanded that the thrust '
            f'coefficient is not physical (C_F = {cf}): with an expansion '
            f'ratio of {eps:.2f} the exit pressure is {pe:.4f} bar against an '
            f'ambient pressure of {pa:.4f} bar, so the nozzle would be pushed '
            f'backwards rather than forwards.{oneri} Reduce the expansion '
            f'ratio, raise the chamber pressure, or analyse the motor at '
            f'altitude.')

    def _get_oxidizer_density(self):
        """Sıvı oksitleyici besleme yoğunluğu [kg/m³] — self.oxidizer_type'a göre.

        Faz, O/F oranından DEĞİL besleme (tank) koşulundan belirlenir
        (denetim bulgusu #2): sıvı-faz besleme varsayılır. Yoğunluk enjeksiyon
        hızına (v=√(2ΔP/ρ)) ve orifis alanına (A=mdot/(Cd·√(2ρΔP))) beslendiği
        için oksitleyiciye göre DOĞRU değer kullanılmalıdır (denetim bulgusu
        #550): eski kod her oksitleyicide N2O yoğunluğu döndürüp LOX/H2O2
        enjektör hız/orifis boyutunu ~%20-30 hatalı veriyordu.

        - N2O: self-pressurized, KULLANICININ tank sıcaklığındaki doygun
          sıvı. Kaynak, tank blowdown bloğunun okuduğu AYNI doygunluk
          modelidir (``hrma.analysis.tank_blowdown.N2OSaturation``);
          erişilemezse external_data_fetcher, o da yoksa
          N2O_LIQUID_DENSITY_SAT_25C (≈745 kg/m³, NIST WebBook,
          Lemmon & Span 2006).
        - LOX / H2O2 / diğer: merkezi oksitleyici tablosundan
          (PropellantDatabase) işletme sıvı yoğunluğu (LOX≈1141 kg/m³ @ 90 K,
          H2O2 %98 =1438,1 kg/m³ @ 293,15 K — 28 Ağu düzeltmesi; buradaki eski
          "≈1450 @ 25°C" %100 SAF H₂O₂'nin değeriydi, %98'in değil).
          fetch_nist_oxidizer_properties bu
          akışkanları desteklemeyip sessizce N2O'ya düştüğünden (ve LOX 25°C'de
          kritik-üstü/gaz olacağından) tek doğruluk kaynağı olarak merkezi
          tablo okunur — magic-number tekrarından da kaçınılır.
        """
        ox_name = (getattr(self, 'oxidizer_type', None) or 'n2o').lower()

        if ox_name == 'n2o':
            # D15/P1B1-03 — TANK SICAKLIĞI ENJEKTÖR ZİNCİRİNE BAĞLANDI.
            # ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/hibrit/a1/once.json): burada
            # ``T_tank = 298.15`` SABİT yazılıydı ve self.tank_temperature
            # hiç okunmuyordu. tank_temperature = None/280/293,15/305 K'nin
            # DÖRDÜNDE de enjektör 742,933 kg/m³ görüyordu (ayrık yoğunluk
            # sayısı = 1), oysa AYNI yanıttaki blowdown bloğu sırasıyla
            # 785,10 / 870,44 / 785,10 / 661,16 kg/m³ yayımlıyordu — 280 K'de
            # %14,65 fark. Modülün kendi künyesi (bkz. yukarıdaki
            # TANK_TEMPERATURE_DEFAULT_K yorumu) "iki modül de aynı 293,15 K
            # değerini kullanır — tek kaynak" diyordu; kod tersini yapıyordu.
            # Artık sıcaklık kullanıcıdan gelir ve yoğunluk, tank bloğunun
            # okuduğu AYNI doygunluk modelinden çözülür: tek kaynak, tek sayı.
            T_tank = (float(self.tank_temperature)
                      if getattr(self, 'tank_temperature', None) is not None
                      else TANK_TEMPERATURE_DEFAULT_K)
            try:
                from hrma.analysis.tank_blowdown import N2OSaturation
                rho = float(N2OSaturation().rho_l(T_tank))
                if np.isfinite(rho) and rho > 0.0:
                    return rho
            except ImportError:
                pass
            except ValueError:
                # Doyma zarfının dışı (kritik nokta üstü / üçlü nokta altı).
                # Burada sayı UYDURULMAZ: doygun sıvı N2O yoktur, dolayısıyla
                # self-pressurized besleme varsayımı da yoktur. Fail-closed —
                # hata çağıranın kapısına kadar çıkar ve alanı adıyla söyler.
                raise ValueError(
                    f'tank_temperature = {T_tank:.2f} K is outside the '
                    f'saturated-liquid envelope of N2O, so there is no '
                    f'liquid feed density to size the injector with. Supply '
                    f'a tank temperature between the triple point and the '
                    f'critical point (182.33 K < T < 309.52 K, NIST '
                    f'WebBook).')
            # ÖH D18 (kalem OH-Z1-06) — ESKİ GEREKÇE BAYATTI, YENİDEN
            # TÜRETİLDİ. Buradaki yorum şunu diyordu: "doygunluk basıncının
            # üzerinde besleme basıncı ver ki SIVI DAL çözülsün". O gerekçe
            # Z1 onarımından (2026-08-27) önce doğruydu: fetch_nist_oxidizer_
            # properties o zaman CoolProp'a PropsSI(T, P) soruyordu ve P
            # doyma basıncının altına düşerse BUHAR dalı çözülüyordu (ölçülen
            # 434 katlık faz sızıntısı). Z1'den beri yoğunluk sorulan
            # SICAKLIKTAKİ DOYMUŞ SIVI değeridir ve basınç argümanı çözüme
            # HİÇ GİRMEZ — bu bloğun 1,2·Pc / 60 bar seçimi artık hiçbir dalı
            # açmıyor. ÖLÇÜLDÜ (once.json, OH_Z1_06; taban 9071a64,
            # T=293,15 K): pressure = 1 / 30 / 60 / 200 / 1e6 bar için
            # yoğunluk BİREBİR 785,1039703874175 kg/m³ (benzersiz değer 1).
            # Değer imza uyumluluğu için korunur ve bu fonksiyondan DIŞARI
            # ÇIKMAZ (çağıran yalnız props['density'] okur); künyeye giren
            # 'pressure' yankısı da bu yerel çağrının içinde kalır.
            # Bağımsızlık bekçisi: tests/test_d18_hibrit_a1.py::
            # TestOHZ106BasincYogunluguEtkilemiyor.
            P_kunye_bar = max(1.2 * self.P_c, 60.0)  # bar — yalnız imza dolgusu
            try:
                props = data_fetcher.fetch_nist_oxidizer_properties(
                    'n2o', temperature=T_tank, pressure=P_kunye_bar
                )
                rho = float(props.get('density', 0.0))
                # Sıvı faz makulluk penceresi: doygun sıvı N2O 25°C'de ~745,
                # 20°C'de ~785 kg/m³ (NIST WebBook). Pencere dışı → fallback.
                if 500.0 < rho < 1000.0:
                    return rho
            except Exception:
                pass
            return N2O_LIQUID_DENSITY_SAT_25C  # NIST WebBook (Lemmon & Span 2006)

        # LOX / H2O2 / diğer: merkezi tablodan işletme sıvı yoğunluğu.
        try:
            from hrma.data.propellant_database import PropellantDatabase
            props = PropellantDatabase().get_propellant_properties(ox_name)
            if props and props.get('density'):
                rho = float(props['density'])
                if 300.0 < rho < 2000.0:  # sıvı oksitleyici makulluk penceresi
                    return rho
        except Exception:
            pass

        warnings.warn(
            f"Bilinmeyen/erişilemeyen oksitleyici yoğunluğu '{ox_name}' — "
            "N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir"
        )
        # D15/P1B1-06: SESSİZ YEDEK OLMAZ. Bu dal başka bir itici için N₂O'nun
        # yoğunluğunu kullanıyor ve o sayı enjektör orifis alanına, akış
        # hızına ve atomizasyona giriyor; hüküm konsolda kalırsa kullanıcı
        # kendi oksitleyicisinin boyutlandırıldığını sanır.
        self._hukum_kaydet({
            'gate': 'oxidizer_density_resolution',
            'status': 'fallback',
            'quantity': 'oxidizer_liquid_density',
            'requested': str(ox_name),
            'value': float(N2O_LIQUID_DENSITY_SAT_25C),
            'used_instead': 'n2o',
            'unit': 'kg/m^3',
            'basis': ('the density of the oxidiser you selected could not be '
                      'resolved from the propellant database, so the saturated '
                      'N2O value at 25 C was used. Injector orifice area, '
                      'injection velocity and atomisation are sized from this '
                      'number and therefore describe N2O, not the selected '
                      'oxidiser.'),
        })
        return N2O_LIQUID_DENSITY_SAT_25C

    def _design_fuel_grain(self):
        """Design fuel grain geometry using correct hybrid rocket equations.

        Port oksitleyici akısı G_ox = mdot_ox / A_port bir TASARIM
        parametresidir ve enjektör orifis akısından (rho·v_enjeksiyon)
        tamamen ayrıdır (denetim bulgusu #1). Grain boyu, yakıt üretim
        kapanışından çözülür: mdot_f = rho_f · π · D_port · L · r_dot
        (Sutton & Biblarz 9. baskı, Böl. 16, yakıt üretim denklemi).
        """
        # --- Enjektör parametreleri (YALNIZ enjektör tasarımı için) ---
        # ÖH D26 / P14M2-05(+b): oran ÇIPLAK 0,2 literaliydi; artık chug
        # kararlılık ölçütünün TEK kaynağından türetiliyor (NASA SP-8089
        # tavsiyesi ΔP/Pc >= %20 — aynı sayı ürünün uyarı/karar zincirinde
        # zaten CHUG_DP_RATIO_RECOMMENDED adıyla yaşıyor). Sayı bugün AYNI
        # (0,20), değişen tek şey KAYNAĞI: eşik kıpırdadığında enjektör de
        # kıpırdar. Sutton & Biblarz 9. baskı Böl. 8 aynı %20 mertebesini
        # tipik tasarım düşümü olarak verir.
        delta_P = CHUG_DP_RATIO_RECOMMENDED * self.P_c  # bar
        rho_ox = self._get_oxidizer_density()  # kg/m³ — oxidizer_type'a göre sıvı besleme yoğunluğu
        # Bernoulli: v = sqrt(2·ΔP/ρ) — yoğunluk, akan akışkanın yoğunluğuyla
        # TUTARLI (denetim bulgusu #3; eski kodda 1220 hardcoded idi)
        injection_velocity = np.sqrt(2 * delta_P * 1e5 / rho_ox)  # m/s

        # Store injector parameters for results output
        self._inj_delta_P = delta_P          # bar
        self._inj_velocity = injection_velocity  # m/s
        self._inj_rho_ox = rho_ox            # kg/m³

        # --- Port boyutlandırma ---
        # Öncelik (v2.5.2): kullanıcı başlangıç port ÇAPINI verdiyse geometri
        # doğrudan ondan gelir; G_ox tasarım akısı bu durumda SONUÇtur
        # (G_ox = mdot_ox / A_port), girdi değil. Çap verilmediyse eski yol:
        # G_ox = mdot_ox / A_port  =>  A_port = mdot_ox / G_ox_design
        # (bulgu #1 düzeltmesi; G_ox_design varsayılanı 350 kg/m²·s).
        # v2.6.2 (F046): N portlu grain. D_port TEK portun çapıdır; akı toplam
        # port alanından hesaplanır: G_ox = mdot_ox / (N · A_tek).
        N_port = self.port_count
        if self.initial_port_diameter is not None:
            self.D_port_initial = self.initial_port_diameter
            A_single_initial = np.pi * (self.D_port_initial / 2.0) ** 2
            A_port_initial = N_port * A_single_initial
            G_ox_initial = self.mdot_ox / A_port_initial
            self.G_ox_design = G_ox_initial
            if G_ox_initial > OX_FLUX_FLOODING_WARN_KG_M2S:
                warnings.warn(
                    f"G_ox = {G_ox_initial:.0f} kg/m²·s flooding sınırına "
                    "(~600-700 kg/m²·s) yakın/üstünde — başlangıç port çapını "
                    "büyütün (Sutton & Biblarz 9. baskı, Böl. 16)"
                )
                # D15/P1B1-06: kullanıcının verdiği port çapından TÜREYEN akı.
                self._hukum_kaydet({
                    'gate': 'oxidizer_flux_flooding',
                    'status': 'out_of_band',
                    'quantity': 'G_ox_initial',
                    'value': float(G_ox_initial),
                    'limit': float(OX_FLUX_FLOODING_WARN_KG_M2S),
                    'unit': 'kg/m^2.s',
                    'source': ('derived from the initial port diameter you '
                               'supplied'),
                    'port_diameter_m': float(self.D_port_initial),
                    'basis': ('Sutton & Biblarz 9th ed. Ch.16: above roughly '
                              '600-700 kg/m^2.s the hybrid port floods, the '
                              'flame lifts off the fuel surface and the '
                              'regression correlation stops describing the '
                              'motor. Enlarge the initial port diameter.'),
                })
        else:
            G_ox_initial = self.G_ox_design  # kg/m²·s
            A_port_initial = self.mdot_ox / G_ox_initial   # TOPLAM port alanı
            A_single_initial = A_port_initial / N_port
            self.D_port_initial = 2 * np.sqrt(A_single_initial / np.pi)

        # --- Regresyon hızı: akı tabanı self.flux_mode (H-7, 6 Eki 2026) ---
        # VARSAYILAN 'ox': r = a·G_ox^n — depodaki katsayılar G_ox tabanlı
        # fitlerdir (Karabeyoglu ve ark. 2007 §III.A; Sutton 9 Eş. 16-2
        # s. 602; Mishra Eş. 9.13 s. 320). 'total' seçilirse Marxman biçimi
        # r = a·G_total^n, G_total = G_ox + G_fuel (Marxman & Gilbert 1963)
        # koşar; G_fuel r'ye bağlı olduğundan iteratif kapanış yapılır. Eski
        # yorumun "yalnız G_ox r'yi DÜŞÜK tahmin eder, güvenli olmayan yön"
        # gerekçesi F018'de ÇÜRÜTÜLDÜ: G_ox fitini G_total ile beslemek çift
        # sayımdır (regression_analysis modül başlığı).
        # Not: ilk grain boyu tahmini gerektiğinden, L_grain'i önce mdot_f
        # hedefinden (tasarım O/F) türetip sonra Marxman ile tutarlılaştırırız.
        # Başlangıç L_grain tahmini (yalnız G_ox ile, alt sınır):
        # N portlu grain'de yanma çevresi N·π·D'dir (F046).
        r_dot_ox_only = self.a * G_ox_initial ** self.n
        # ÖH D23 / OH-D21-08: bağıntı TEK TANIM NOKTASINDAN
        # (regression_analysis) çözülür; elle yazılmış kopya yok.
        self.L_grain = grain_length_for_fuel_mass_flow_m(
            self.mdot_f, self.rho_f, self.D_port_initial,
            r_dot_ox_only, port_count=N_port)

        # --- Grain boyu <-> regresyon hızı SABİT-NOKTA kapanışı ---
        # v2.6.2 fizik denetimi, bulgu F133: flux_mode='total' iken L_grain ile
        # r_dot KARŞILIKLI bağımlıdır — L → mdot_f → G_fuel → G_total → r → L.
        # Eski kod bu çevrimi TEK GEÇİŞ yapıyordu: r_dot yalnız-G_ox ile
        # kurulan (daha uzun) başlangıç L'sinde bir kez hesaplanıyor, ardından
        # L bu r ile yeniden çözülüyor ama r GERİ GÜNCELLENMİYORDU. Sonuçta
        # saklanan (r_dot_initial, G_total_initial) ikilisi saklanan L_grain
        # ile tutarsız kalıyor, yakıt üretim kapanışı
        # mdot_f = rho_f·N·π·D·L·r_dot bozuluyordu.
        # Çevrim şu haritanın sabit noktasıyla kapatılır:
        #     L_{k+1} = mdot_f / (rho_f · N · π · D · r(L_k))
        # Harita büzülmedir: d ln r / d ln L = n·φ/(1 − n·φ) (φ = G_fuel/G_total,
        # tasarım noktasında φ ≈ (sf/OF)/(1 + sf/OF), O/F=6 için ~0.08), yani
        # eğim |−x| « 1 ve birkaç adımda yakınsar.
        # flux_mode='ox' iken r, L'den bağımsızdır: harita ilk adımda sabit
        # noktaya oturur, eski davranış BİREBİR korunur (etki sıfır).
        # Kaynak: iç tutarlılık gereği (yakıt üretim kapanışı, Sutton & Biblarz
        # 9. baskı Böl. 16) — harici katsayı/korelasyon eklenmemiştir.
        L_iter = self.L_grain
        reg0 = None
        grain_iterations = 0
        grain_converged = False
        for grain_iterations in range(1, GRAIN_LENGTH_FIXED_POINT_MAX_ITER + 1):
            reg0 = RegressionAnalyzer.regression_rate(
                self.a, self.n, G_ox_initial,
                rho_f=self.rho_f, port_diameter=self.D_port_initial,
                grain_length=L_iter, flux_mode=self.flux_mode
            )
            L_next = grain_length_for_fuel_mass_flow_m(
                self.mdot_f, self.rho_f, self.D_port_initial,
                reg0['r_dot'], port_count=N_port)
            rel_change = abs(L_next - L_iter) / max(abs(L_next), 1e-12)
            L_iter = L_next
            if rel_change < GRAIN_LENGTH_FIXED_POINT_TOL:
                grain_converged = True
                break

        self.L_grain = L_iter
        # Yakınsanan L ile SON değerlendirme: saklanan r_dot/G_total artık
        # saklanan L_grain'in tam karşılığıdır (tutarsızlık kalmaz).
        reg0 = RegressionAnalyzer.regression_rate(
            self.a, self.n, G_ox_initial,
            rho_f=self.rho_f, port_diameter=self.D_port_initial,
            grain_length=self.L_grain, flux_mode=self.flux_mode
        )
        self.r_dot_initial = reg0['r_dot']
        self.r_dot = self.r_dot_initial  # For compatibility
        self.G_total_initial = reg0['G_total']
        self._grain_length_iterations = grain_iterations
        self._grain_length_converged = bool(grain_converged)
        if not grain_converged:
            # Sessiz yakınsamama yasak: son iterat kullanılıyorsa kullanıcı
            # bunu bilmeli (aynı sözleşme regression_analysis.py'de de var).
            warnings.warn(
                f"Grain boyu <-> regresyon hızı sabit-nokta iterasyonu "
                f"{GRAIN_LENGTH_FIXED_POINT_MAX_ITER} adımda yakınsamadı "
                f"(n={self.n}, son bağıl değişim {rel_change:.2e}); son "
                f"iterat kullanılıyor.",
                RuntimeWarning
            )
            self.design_warnings.append(_w(
                'warn.hybrid.grain_length_not_converged', 'warning',
                max_iter=GRAIN_LENGTH_FIXED_POINT_MAX_ITER,
                n=round(float(self.n), 3),
                rel_change=float(f"{rel_change:.3e}")))

        # --- Euler time-marching (denetim bulgusu #5 düzeltmesi) ---
        # Sabit 10 adım yerine dt = t_b/200 taban çözünürlüğü; ek olarak ilk
        # adımdaki çap artışı başlangıç çapının %1'ini geçmeyecek şekilde adım
        # sayısı artırılır (ilk adım sıçraması koruması).
        # ÜST SINIR ZORUNLU (2026-07-23 kararlılık denetimi): bu ifade tavansızdı
        # ve uç girdilerde programı fiilen kilitliyordu — burn_time=1e12 için
        # 5.6 TRİLYON adım, thrust=1e-9 için 56 milyon adım hesaplanıyor, süreç
        # dakikalarca dönüp megabaytlarca hata günlüğü üretiyordu (paketli
        # uygulamada bu, kullanıcının Belgeler klasörüne akıyor).
        # 200 000 adım, geçerli tasarım aralığının en kötü hâlinin (~17 000)
        # on katından fazlasıdır; sayısal çözünürlük kaybı yok, kilitlenme yok.
        # Sınıra dayanılırsa sessiz geçilmez: uyarı üretilir.
        num_steps = max(
            200,
            int(np.ceil(self.t_b * 2 * self.r_dot_initial / (0.01 * self.D_port_initial)))
        )
        if num_steps > MAX_BURN_INTEGRATION_STEPS:
            warnings.warn(
                f"Yanma integrasyonu {num_steps:,} adım isteyecekti; "
                f"{MAX_BURN_INTEGRATION_STEPS:,} adımda sınırlandırıldı. "
                "Bu, girdilerin (yanma süresi / itki / port çapı) fiziksel "
                "aralık dışında olduğunu gösterir; sonuçlar güvenilir değildir."
            )
            # D15/P1B1-06: "sonuçlar güvenilir değildir" cümlesi SUNUCU
            # KONSOLUNDA kalıyordu — yani kullanıcı, çözünürlüğü kırpılmış bir
            # integrasyonun sonuçlarını hiçbir işaret görmeden okuyordu.
            self._hukum_kaydet({
                'gate': 'burn_integration_steps',
                'status': 'clamped',
                'quantity': 'integration_steps',
                'requested': int(num_steps),
                'value': int(MAX_BURN_INTEGRATION_STEPS),
                'limit': int(MAX_BURN_INTEGRATION_STEPS),
                'unit': 'steps',
                'basis': ('the time step is chosen so the first port-diameter '
                          'increment stays below 1% of the initial diameter. '
                          'Needing more steps than the cap means the inputs '
                          '(burn time / thrust / port diameter) are outside '
                          'the physical range; the integration was clamped, so '
                          'the burn history is under-resolved.'),
            })
            num_steps = MAX_BURN_INTEGRATION_STEPS
        dt = self.t_b / num_steps
        D_port = self.D_port_initial

        # Fiziksel sınır: port çapı kamara çapının %80'ini geçmemeli.
        # Eski koddaki hasattr(self, 'D_ch') kontrolü İLK çağrıda her zaman
        # False idi (D_ch grain tasarımından SONRA atanıyor) → ölü kod; ikinci
        # çağrıda ise bayat D_ch kullanılıyordu. Düzeltme: sınır yalnızca
        # kullanıcı kamara çapı verdiyse uygulanabilir; verilmediyse kamara
        # çapı port sonundan türetildiği için (D_ch = 1.5·D_port_final,
        # yani D_port_final ≈ 0.67·D_ch < 0.8·D_ch) sınır kendiliğinden sağlanır.
        if self.chamber_diameter_input > 0:
            # N portlu grain'de sınır ALAN üzerinden kurulur: toplam port alanı
            # kamara kesitinin (0.8)² katını geçmemeli. Tek port çapı cinsinden
            # bu, D_tek <= 0.8·D_ch/sqrt(N) demektir (N=1'de eski ifadeyle
            # birebir aynı).
            max_port = (PORT_TO_CHAMBER_MAX_RATIO
                        * self.chamber_diameter_input / np.sqrt(N_port))
            if max_port <= self.D_port_initial:
                # v2.5.2 DÜZELTMESİ (Codex bulgusu, hybrid:827): eski kod
                # burada UYARIP sınırı sonsuza çekiyordu. Bu, imkansız
                # geometriyi (port >= kamara) hesaba devam ettiriyordu:
                # yüklenen yakıt kütlesi m_f_loaded = rho·(π/4)·(D_ch² −
                # D_port_ilk²)·L_grain olduğundan D_port_ilk > D_ch iken
                # NEGATİF kütle, negatif sliver ve anlamsız kamara hacmi
                # üretiliyordu. Sessizce devam etmek yerine reddedilir;
                # /calculate ve /api/quick-geometry bunu HTTP 400'e çevirir.
                raise ValueError(
                    f"Chamber diameter {self.chamber_diameter_input * 1000:.1f} mm "
                    f"is too small for the initial port diameter "
                    f"{self.D_port_initial * 1000:.1f} mm. The fuel grain must "
                    f"surround the port, so the chamber diameter has to exceed "
                    f"the port diameter divided by "
                    f"{PORT_TO_CHAMBER_MAX_RATIO:g} "
                    f"(minimum "
                    f"{self.D_port_initial * np.sqrt(N_port) / PORT_TO_CHAMBER_MAX_RATIO * 1000:.1f} mm "
                    f"for {N_port} port(s)). "
                    f"Increase the chamber diameter or reduce the port "
                    f"diameter / oxidizer mass flux."
                )
        else:
            max_port = np.inf

        # O/F kayması izleme: anlık mdot_f / O/F / c* / Isp her adımda.
        # Anlık c*/Isp, anlık O/F'den combustion analyzer ile hesaplanır
        # (denetim bulgusu #2): O/F kayması performansa YANSITILIR; eski kod
        # c*/Isp'yi tasarım O/F'sinde donduruyordu. Pahalı denge çözümünü her
        # adımda tekrarlamamak için O/F->c*/Isp tablosu önbelleğe alınır
        # (track_performance=True ise).
        web_exhausted = False
        self._of_history = []
        self._cstar_history = []
        self._isp_history = []
        self._time_history = []
        # Port çapı zaman serisi: 3D yanma animasyonu D_port(t)'yi buradan okur
        # (track_performance'dan bağımsız tutulur — geometri her zaman lazım)
        self._port_time_history = []
        self._port_diameter_history = []
        # v2.6.26 — İTKİ-ZAMAN EĞRİSİ. Katı motorda bu eğri vardı, hibritte
        # YOKTU; oysa zaman-adımlı çözücü gereken her şeyi zaten hesaplıyordu
        # (anlık yakıt debisi, anlık c*, anlık Isp) ve yalnızca dışarı
        # vermiyordu. Eğri UYDURULMAZ: her nokta bu döngünün kendi
        # durumundan gelir.
        #     ṁ_toplam(t) = ṁ_ox + ṁ_yakıt(t)          (süreklilik)
        #     F(t)        = ṁ_toplam(t)·Isp(t)·g0       (itki tanımı)
        #     Pc(t)       = ṁ_toplam(t)·c*(t)/(C_D·At)  (debi C_D taşır)
        # Hibritte ṁ_ox sabit, ṁ_yakıt port çapıyla değişir; eğrinin
        # regresif/progresif biçimi bu fizikten çıkar, elle çizilmez.
        self._mdot_total_history = []
        self._thrust_history = []
        self._pc_history = []
        # A9: anlık YAKIT debisi ayrıca saklanır. Bu koşuda ṁ_ox sabit
        # olduğundan ṁ_f = ṁ_toplam − ṁ_ox çıkarılabilirdi; ama O/F bloğu
        # ṁ_ox'un DEĞİŞTİĞİ blowdown durumuyla aynı sözleşmeyi kullanır ve
        # orada böyle bir çıkarma yanlış olurdu. İki durum aynı alan adlarını
        # taşısın diye seri burada da açıkça tutulur.
        self._mdot_f_history = []

        for i in range(num_steps):
            t_now = i * dt
            self._port_time_history.append(t_now)
            self._port_diameter_history.append(D_port)
            A_port = N_port * np.pi * (D_port / 2)**2   # TOPLAM port alanı
            G_ox = self.mdot_ox / A_port  # kg/m²·s oksitleyici akış yoğunluğu

            # Marxman regresyon hızı: r = a · G_total^n (G_total iteratif).
            reg = RegressionAnalyzer.regression_rate(
                self.a, self.n, G_ox,
                rho_f=self.rho_f, port_diameter=D_port,
                grain_length=self.L_grain, flux_mode=self.flux_mode
            )
            r_dot = reg['r_dot']  # m/s

            # Anlık yakıt üretimi ve O/F (kayma izleme) — N portun toplamı
            mdot_f_inst = fuel_mass_flow_kg_s(
                self.rho_f, D_port, self.L_grain, r_dot,
                port_count=N_port)
            of_inst = self.mdot_ox / mdot_f_inst if mdot_f_inst > 0 else self.OF

            # Anlık c*/Isp (O/F shift -> performans, bulgu #2). Tablo
            # önbelleği ile (track_performance açıkken).
            if self.track_performance:
                cstar_inst, isp_inst = self._instantaneous_performance(of_inst)
                self._of_history.append(of_inst)
                self._cstar_history.append(cstar_inst)
                self._isp_history.append(isp_inst)
                self._time_history.append(t_now)

                # İtki ve oda basıncı, bu adımın KENDİ durumundan türer.
                # At bu noktada hesaplanmıştır (calculate() sırası:
                # At -> _design_fuel_grain); yine de savunmacı davranılır,
                # çünkü At yoksa Pc uydurulamaz — o nokta atlanır.
                mdot_total_inst = self.mdot_ox + mdot_f_inst
                self._mdot_total_history.append(mdot_total_inst)
                self._mdot_f_history.append(mdot_f_inst)
                self._thrust_history.append(
                    mdot_total_inst * isp_inst * self.g0)
                # Pc BAR cinsinden saklanır: katı motorun thrust_curve
                # sözleşmesi bar kullanıyor (ölçüldü) ve tek bir çizim kodu
                # üç sayfayı da beslediği için birimler AYNI olmak zorunda.
                # c* tanımı Pa verir; 1e5'e bölünür.
                # F3-1 (bebek-Scofield): geri okuma C_D SÖZLEŞMESİYLE —
                # boyutlandırma At = ṁ·c*/(Pc·C_D) olduğundan geri okuma
                # Pc = ṁ·c*/(C_D·At) olmak zorundadır. C_D'siz okuma t=0
                # basıncını tasarımın 0,98 katına düşürüyordu (ölçüldü:
                # 29,40 / 30,00 bar).
                at = getattr(self, 'At', None)
                self._pc_history.append(
                    mdot_total_inst * cstar_inst
                    / (THROAT_DISCHARGE_COEFFICIENT * at) / 1e5
                    if at and at > 0 else float('nan'))

            # Port yarıçapını artır (çap artışı = 2 · yarıçap artışı)
            D_port += 2 * r_dot * dt

            if D_port >= max_port:
                D_port = max_port
                web_exhausted = True
                warnings.warn(
                    "Port çapı 0.8·D_kamara sınırına ulaştı — web yanma süresi "
                    "bitmeden tükendi, grain tasarımını gözden geçirin"
                )
                # v2.6.2: bu, tasarımın İSTENEN yanma süresini tutturamadığı
                # anlamına gelir; design_summary.status bunu okur.
                self.design_warnings.append(_w(
                    'warn.hybrid.web_exhausted_early', 'critical',
                    t_web=round(float(t_now + dt), 2),
                    t_burn=round(float(self.t_b), 2)))
                break

        self.D_port_final = D_port
        # Seriye son noktayı ekle (erken web tükenmesinde son adım zamanı)
        t_end = t_now + dt if web_exhausted else self.t_b
        self.t_burn_effective = t_end
        self._port_time_history.append(t_end)
        self._port_diameter_history.append(D_port)

        # Final oxidizer flux hesaplama (TOPLAM port alanı, F046)
        A_port_final = N_port * np.pi * (self.D_port_final / 2)**2
        self.G_ox_final = self.mdot_ox / A_port_final

        # Yanma sonu Marxman regresyonu ve anlık yakıt debisi / O/F (bulgu #6)
        reg_final = RegressionAnalyzer.regression_rate(
            self.a, self.n, self.G_ox_final,
            rho_f=self.rho_f, port_diameter=self.D_port_final,
            grain_length=self.L_grain, flux_mode=self.flux_mode
        )
        r_dot_final = reg_final['r_dot']
        self.G_total_final = reg_final['G_total']
        self.mdot_f_final = fuel_mass_flow_kg_s(
            self.rho_f, self.D_port_final, self.L_grain,
            r_dot_final, port_count=N_port)
        self.OF_final = self.mdot_ox / self.mdot_f_final if self.mdot_f_final > 0 else self.OF

        # --- Zaman serisinin SON NOKTASI (v2.6.27 B1, kalem 4) -------------
        # Döngü t_now = i·dt'yi adımı ATMADAN ÖNCE kaydediyor, bu yüzden itki/
        # basınç/O-F serileri son adımın BAŞINDA bitiyordu. ÖLÇÜLDÜ (t_b = 20 s,
        # kırpılma yok): thrust_curve son t = 19,9 s, port_history son t = 20,0 s
        # — aynı koşunun iki serisi yanma süresi konusunda anlaşmıyordu ve
        # kullanıcı hangisinin doğru olduğunu bilemiyordu. Port serisi zaten
        # son noktayı ekliyordu (yukarıda); performans serileri eklemiyordu.
        # Son nokta UYDURULMAZ: yanma sonu durumu (D_port_final -> G_ox_final ->
        # ṁ_f_final -> O/F_final) bu noktanın hemen üstünde ZATEN çözülmüştür.
        if self.track_performance and self._time_history:
            cstar_son, isp_son = self._instantaneous_performance(self.OF_final)
            mdot_toplam_son = self.mdot_ox + self.mdot_f_final
            self._time_history.append(t_end)
            self._of_history.append(self.OF_final)
            self._cstar_history.append(cstar_son)
            self._isp_history.append(isp_son)
            self._mdot_total_history.append(mdot_toplam_son)
            self._mdot_f_history.append(self.mdot_f_final)
            self._thrust_history.append(mdot_toplam_son * isp_son * self.g0)
            at_son = getattr(self, 'At', None)
            # F3-1: son nokta da AYNI C_D sözleşmesiyle (yukarıdaki not).
            self._pc_history.append(
                mdot_toplam_son * cstar_son
                / (THROAT_DISCHARGE_COEFFICIENT * at_son) / 1e5
                if at_son and at_son > 0 else float('nan'))

        # --- Ortalama regresyon hızı (v2.6.2 FİZİK DENETİMİ, bulgu F045) ---
        # ESKİ TANIM: uç noktaların ARİTMETİK ORTALAMA AKISINDA değerlendirilen
        # ANLIK regresyon (r = a·G_ort^n). Bu, deneysel literatürün ve
        # doğrulama veritabanının measured.regression_rate_avg alanının
        # raporladığı büyüklük DEĞİLDİR; oradaki büyüklük UZAY-ZAMAN
        # ORTALAMASIDIR: r̄ = (D_final − D_initial)/(2·t_b).
        # İki tanım aynı değildir: (i) r = a·G^n, n<1 için G'de içbükeydir,
        # Jensen eşitsizliği gereği a·ort(G)^n >= ort(a·G^n); (ii) G_ox(t) ∝ D⁻²
        # azalan-dışbükey olduğundan uç nokta aritmetik ortalaması gerçek zaman
        # ortalamasının üstündedir. Sonuç: eski tanım modelin gerçek sapmasını
        # sistematik olarak MASKELİYORDU.
        # DOĞRULAMA: veritabanında hem r̄ hem D_i/D_f/t_b veren 4 kayıtta
        # (D_f−D_i)/(2·t_b) ile yayımlanan r̄ arasındaki medAPE %0.11 —
        # yani ölçülen büyüklüğün tanımı budur, tartışmaya yer yok.
        # Model D_final'ı ZATEN hesapladığı için bu tanım bedelsiz ve tam
        # tutarlıdır (aynı zamanda m_f_grain ile birebir uyumludur).
        # Kaynak: Chiaverini & Kuo, "Fundamentals of Hybrid Rocket Combustion
        # and Propulsion", AIAA Progress Vol. 218 (2007), Böl. 2; Karabeyoglu
        # et al., JPP 20(6) 2004 — veri indirgeme (çap ölçümü) bölümü.
        # Web erken tükendiyse GERÇEK yanma süresi kullanılır (aksi hâlde
        # ortalama, hiç yaşanmamış bir süreye bölünürdü).
        self.r_dot_avg = ((self.D_port_final - self.D_port_initial)
                          / (2.0 * t_end)) if t_end > 0 else self.r_dot_initial
        # Akı-ortalama tanımı da şeffaflık için saklanır (eski çıktı; hangi
        # tanımın raporlandığı karşılaştırılabilsin diye).
        G_ox_avg = (G_ox_initial + self.G_ox_final) / 2
        reg_avg = RegressionAnalyzer.regression_rate(
            self.a, self.n, G_ox_avg,
            rho_f=self.rho_f, port_diameter=(self.D_port_initial + self.D_port_final) / 2,
            grain_length=self.L_grain, flux_mode=self.flux_mode
        )
        self.r_dot_at_avg_flux = reg_avg['r_dot']

        # Grain'in fiilen ürettiği yakıt kütlesi (denetim bulgusu #6):
        # m_f = rho_f · N · (V_port_final − V_port_initial)
        #     = rho_f · N · (π/4) · (D_final² − D_initial²) · L_grain
        self.m_f_grain = (
            self.rho_f * N_port * (np.pi / 4.0)
            * (self.D_port_final**2 - self.D_port_initial**2)
            * self.L_grain
        )
        self._web_exhausted = web_exhausted

        # Store for results
        self.G_ox_initial = G_ox_initial
    
    def _resolve_contraction_ratio(self):
        """(A_c/A_t, kaynak) — daralma oranının TEK tanım noktası.

        Kullanıcı bir değer verdiyse o geçerlidir; vermediyse oda kesiti grain
        dış zarfından bilindiği için geometriden türetilir.

        v2.6.26: bu çözüm yalnız `_finite_area_combustor` içinde duruyordu ve
        lüle tasarımcısına HİÇ geçirilmiyordu. Ölçüldü: kullanıcı 4.0
        girdiğinde yanıtın bir yerinde `finite_area_combustor.contraction_ratio
        = 4.0 (user input)` yazarken lüle konturunda
        `convergent.contraction_ratio = 2.25` kalıyor ve yakınsak koni boyu hiç
        değişmiyordu — tek sonuçta iki çelişkili daralma oranı. Tek kaynağa
        indirildi.
        """
        cr_user = getattr(self, 'contraction_ratio_input', None)
        cr_geom = None
        if getattr(self, 'D_ch', 0) and getattr(self, 'd_t', 0):
            cr_geom = (self.D_ch / self.d_t) ** 2
        kullanici_verdi = bool(cr_user and float(cr_user) > 1.0)
        cr = float(cr_user) if kullanici_verdi else cr_geom
        if not cr or cr <= 1.0:
            return None, None
        return cr, ('user input' if kullanici_verdi else 'chamber geometry')

    def _finite_area_combustor(self):
        """Sonlu alanlı yanma odası: kontraksiyon oranından basınç kaybı.

        v2.6.26 — ÖLÜ ALAN DÜZELTMESİ. Arayüzdeki ``combustion_type``
        seçicisi ve ``contraction_ratio`` alanı ölçümde çıktının HİÇBİR
        yaprağını değiştirmiyordu: ``self.combustion_type`` sınıfta yalnız
        bir kez ATANIYOR, hiç okunmuyordu; ``contraction_ratio`` ise motora
        hiç geçirilmiyordu. Kullanıcı bir yanma modeli seçtiğini sanıyordu.

        Fizik (Sutton & Biblarz, Roket Tahrik Elemanları, Böl. 3; Huzel &
        Huang, NASA SP-125, Böl. 4): sonsuz alanlı oda varsayımında odadaki
        akış hızı sıfır kabul edilir ve enjektör yüzü basıncı ile nozul
        durgunluk basıncı eşittir. Gerçek odada kesit sonludur; akış boğaza
        doğru hızlanır, odada sonlu bir Mach sayısı oluşur ve enjektör
        yüzündeki basınç nozul girişindekinden YÜKSEKTİR. Oda Mach sayısı,
        izentropik alan bağıntısının ses altı kökünden gelir:

            A_c/A_t = (1/M)·[ (2/(g+1))·(1 + (g-1)/2·M²) ]^((g+1)/(2(g-1)))

        Enjektör yüzü / nozul durgunluk basıncı oranı ise sıkıştırılabilir
        akışın durgunluk bağıntısıdır:

            p_inj/p_c = (1 + (g-1)/2·M_c²)^(g/(g-1))

        CR büyüdükçe M_c -> 0 ve oran -> 1; yani sonsuz alan çözümü bu
        modelin limit hâlidir. Bu, bir uydurma düzeltme katsayısı DEĞİL,
        aynı denklemin sonlu kesit için çözülmüş hâlidir.

        Döndürür: ``None`` (model uygulanmadı) veya sonuç sözlüğü.
        """
        if str(getattr(self, 'combustion_type', 'infinite')).lower() != 'finite':
            return None
        gamma = float(getattr(self, 'gamma', 1.2) or 1.2)
        if not (1.0 < gamma < 2.0):
            return None

        # Kontraksiyon oranı TEK KAYNAKTAN (_resolve_contraction_ratio):
        # eskiden bu blok yalnız buradaydı ve lüle konturu aynı sayıyı
        # görmüyordu — aynı yanıtta iki farklı daralma oranı çıkıyordu.
        cr, source = self._resolve_contraction_ratio()
        if not cr:
            return None

        # İzentropik alan bağıntısının SES ALTI kökü (ikiye bölme; A/A* alan
        # oranı M<1 bölgesinde M ile monoton azalır, kök tektir).
        exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))

        def area_ratio(mach):
            return (1.0 / mach) * ((2.0 / (gamma + 1.0))
                                   * (1.0 + 0.5 * (gamma - 1.0) * mach ** 2)) ** exponent

        lo, hi = 1e-6, 1.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if area_ratio(mid) > cr:
                lo = mid
            else:
                hi = mid
        mach_c = 0.5 * (lo + hi)

        stagnation_ratio = (1.0 + 0.5 * (gamma - 1.0) * mach_c ** 2) ** (
            gamma / (gamma - 1.0))
        injector_face_bar = self.P_c * stagnation_ratio

        # Çok küçük kontraksiyonda oda tıkanmaya yaklaşır — uyar, kırpma.
        if cr < 2.0:
            self.design_warnings.append(_w(
                'warn.hybrid.contraction_ratio_low', 'warning',
                contraction_ratio=round(cr, 2),
                chamber_mach=round(mach_c, 3)))

        return {
            'model': 'finite-area combustor',
            'contraction_ratio': round(cr, 3),
            'contraction_ratio_source': source,
            'chamber_mach': round(mach_c, 4),
            'injector_face_pressure_bar': round(injector_face_bar, 3),
            'stagnation_pressure_ratio': round(stagnation_ratio, 5),
            'pressure_loss_percent': round((stagnation_ratio - 1.0) * 100.0, 3),
            'basis': ('Isentropic area-Mach relation (subsonic root) plus the '
                      'compressible stagnation relation; Sutton & Biblarz Ch.3, '
                      'Huzel & Huang NASA SP-125 Ch.4. The infinite-area '
                      'assumption is the CR -> infinity limit of this model.'),
        }

    def _tank_blowdown_block(self):
        """N₂O kendinden-basınçlı tank blowdown bloğu (yol haritası A1).

        hrma/analysis/tank_blowdown.py bu sürüme kadar motor sonucuna HİÇ
        bağlı değildi (yalnız injector_design N2OSaturation'ı ve app.py'nin
        ayrı transient uç noktası kullanıyordu); hibrit sayfası regülatörlü
        (sabit ṁ_ox) beslemeyi sessizce varsayıyordu. Oysa N₂O hibritlerin
        büyük bölümü regülatörsüz uçar: tank basıncı yanma boyunca düşer,
        ṁ_ox ve itki onunla düşer — hibritin en karakteristik davranışı.

        Blok, ÇÖZÜCÜNÜN GERÇEK değerlerinden kurulur (m_ox, ṁ_ox, Pc, At,
        grain geometrisi) ve TransientBallistics'in blowdown modunu kullanır:
        denge iki-faz N₂O tankı (Whitmore & Chandler, JPP 27(4) 2011) +
        tasarım noktasında kalibre edilmiş SPI enjektör orifisi + yarı-kararlı
        kamara kapanışı. Şekil verilmez, eğri uydurulmaz.

        Girdi eksik ya da model uygulanamazsa (N₂O dışı oksitleyici, tank
        sıcaklığı model bandı dışı, Pc ≥ tank basıncı, uq_mode) blok sayı
        İÇERMEZ: status NOT_MODELLED + gerekçe döner. Sahte eğri, eğrisizlikten
        kötüdür.
        """
        basis = (
            'equilibrium two-phase N2O tank blowdown '
            '(hrma/analysis/tank_blowdown.N2OTankBlowdown; Whitmore & '
            'Chandler, JPP 27(4) 2011) coupled by '
            'hrma/analysis/transient_ballistics.TransientBallistics: an SPI '
            'injector orifice (mdot = K*sqrt(2*rho_l*dP)) calibrated to '
            'deliver the solver design mdot_ox at the real initial tank '
            'pressure, and a quasi-steady chamber '
            'Pc = mdot_total*c*(O/F)/(Cd*At) with the port regressing per '
            'Marxman. All inputs (m_ox, mdot_ox, Pc, At, grain geometry) are '
            'the solver values of THIS run. Tank wall is adiabatic; throat '
            'erosion is off in this advisory block. The headline design '
            'numbers (thrust, Isp, Pc) remain the regulated design point and '
            'are NOT re-rated by this block.')
        if self.uq_mode:
            return {
                'status': 'NOT_MODELLED',
                'basis': basis,
                'reason': ('skipped in uq_mode (advisory block, same policy '
                           'as the optimum-O/F search and altitude tables); '
                           'run the nominal design for the blowdown curve.'),
            }
        ox = (getattr(self, 'oxidizer_type', None) or '').lower()
        if ox != 'n2o':
            return {
                'status': 'NOT_MODELLED',
                'basis': basis,
                'reason': (
                    f'the self-pressurised blowdown model in '
                    f'hrma/analysis/tank_blowdown.py is N2O-specific '
                    f'(N2O saturation table / CoolProp N2O EOS); no tank '
                    f'model exists for oxidizer "{ox}". The design point '
                    f'assumes a regulated (constant mdot_ox) feed.'),
            }
        if self.tank_temperature is not None:
            t_tank = float(self.tank_temperature)
            t_tank_source = 'user input (tank_temperature)'
        else:
            t_tank = TANK_TEMPERATURE_DEFAULT_K
            t_tank_source = (
                f'default {TANK_TEMPERATURE_DEFAULT_K} K saturated-storage '
                f'assumption (same default the injector module uses)')
        try:
            # Ertelenmiş import: transient_ballistics kendisi bu modülü
            # import eder (motor tipine bakmadan); modül seviyesinde çapraz
            # import döngüsü kurmamak için _analyze_nozzle_material'daki
            # ThroatErosionModel deseniyle aynı yol izlenir.
            from hrma.analysis.transient_ballistics import TransientBallistics
            tb = TransientBallistics(
                self, feed_mode='blowdown',
                tank_temperature=t_tank,
                liquid_fill_fraction=TANK_FILL_FRACTION_DEFAULT,
                n_steps=TANK_BLOWDOWN_N_STEPS)
            sol = tb.solve()
        except Exception as exc:
            # Tipik meşru sebepler: Pc >= Psat(T_tank) (blowdown beslemesi
            # fiziksel olarak imkânsız) ya da tank sıcaklığı 240-306 K model
            # bandı dışında. Hesap zinciri KIRILMAZ; blok gerekçeyle boş kalır.
            return {
                'status': 'NOT_MODELLED',
                'basis': basis,
                'reason': (f'the blowdown model could not run for this '
                           f'design: {exc}'),
                'initial_temperature_K': t_tank,
                'initial_temperature_source': t_tank_source,
            }
        n = len(sol['time'])
        if n == 0:
            return {
                'status': 'NOT_MODELLED',
                'basis': basis,
                'reason': (f'the blowdown solver stopped before the first '
                           f'step (end event: {sol["end_event"]}); no curve '
                           f'exists to publish.'),
                'end_event': sol['end_event'],
                'initial_temperature_K': t_tank,
                'initial_temperature_source': t_tank_source,
            }

        # ~TANK_BLOWDOWN_MAX_POINTS noktaya seyreltme (port_history deseni):
        # yanıt boyutu sınırlanır, son nokta daima korunur.
        stride = max(1, n // TANK_BLOWDOWN_MAX_POINTS)
        idx = list(range(0, n, stride))
        if idx[-1] != n - 1:
            idx.append(n - 1)

        def _pick(arr, scale=1.0):
            return [float(arr[i]) * scale for i in idx]

        def _pick_etiket(arr):
            """Seyreltme, SAYISAL OLMAYAN seri için (ÖH D26 / OH-B4-04).

            Faz bir etikettir; ``float()`` süzgecinden geçirilemez. Aynı
            ``idx`` kullanılır ki zaman ekseniyle nokta nokta hizalı kalsın.
            """
            return [str(arr[i]) for i in idx] if arr else []

        # Tankın KENDİ zarf uyarıları (bant kenetlenmesi, ideal-gaz kuyruğu,
        # üçlü nokta tabanı) solve() uyarılarına dahil değildir — burada
        # birleştirilir ki zarf ihlali kullanıcıdan saklanmasın.
        blok_uyarilari = list(sol.get('warnings') or [])
        for tank_uyari in (getattr(tb.tank, 'warnings', None) or []):
            if tank_uyari not in blok_uyarilari:
                blok_uyarilari.append(tank_uyari)

        f0 = float(sol['thrust'][0])
        f_son = float(sol['thrust'][-1])

        # --- A9: bu bloğun KENDİ O/F kayması --------------------------------
        # Regüleli tasarım noktasında ṁ_ox sabittir ve O/F yalnız port
        # büyümesiyle kayar. Blowdown'da ṁ_ox da düşer, yani O/F'yi İKİ etki
        # birden sürükler. Bu blok zaten ṁ_ox(t) ve ṁ_yakıt(t) serilerini
        # çözüyordu ama yalnız ṁ_ox'u yayımlıyordu; O/F(t) dışarı hiç
        # çıkmıyordu. Değerler çözücünün KENDİ dizilerinden gelir — of_shift
        # bloğu bunları yeniden hesaplamaz, BURADAN okur (tek kaynak).
        of_dizi = np.asarray(sol['of_ratio'], dtype=float)
        mdot_f_dizi = np.asarray(sol['mdot_fuel'], dtype=float)
        mdot_ox_dizi = np.asarray(sol['mdot_ox'], dtype=float)
        of_tasarim = float(self.OF)
        of_min = float(np.min(of_dizi))
        of_max = float(np.max(of_dizi))
        of_sapma = max(abs(of_min / of_tasarim - 1.0),
                       abs(of_max / of_tasarim - 1.0)) if of_tasarim > 0 else None
        # Teslim edilen ortalama Isp: toplam impuls / (harcanan itici · g0).
        # Harcanan kütle, itki integraliyle AYNI kuralla (trapez) çözücünün
        # kendi dizilerinden alınır; başka bir yerden kütle getirilirse
        # I = Isp·m·g0 özdeşliği bozulurdu.
        t_dizi = np.asarray(sol['time'], dtype=float)
        m_harcanan = (float(_trapezoid(mdot_ox_dizi + mdot_f_dizi, t_dizi))
                      if len(t_dizi) > 1 else 0.0)
        isp_teslim = (float(sol['total_impulse']) / (m_harcanan * self.g0)
                      if m_harcanan > 0 else None)

        return {
            'status': 'modelled',
            'basis': basis,
            'feed_mode': 'blowdown',
            'tank_volume_m3': float(tb.tank.V),
            'tank_volume_basis': (
                'tank volume sized from the solver oxidizer mass: '
                'V = (m_ox / rho_l(T_tank)) / liquid fill fraction; m_ox and '
                'rho_l are solver/EOS values of this run, not assumptions'),
            'liquid_fill_fraction': TANK_FILL_FRACTION_DEFAULT,
            'liquid_fill_fraction_basis': (
                'declared default (ullage margin for liquid thermal '
                'expansion); the hybrid page has no tank fill input yet'),
            'initial_temperature_K': t_tank,
            'initial_temperature_source': t_tank_source,
            'initial_pressure_bar': float(sol['tank_pressure'][0]) / 1e5,
            'initial_pressure_basis': (
                'N2O saturation pressure at the initial tank temperature '
                '(CoolProp / embedded Span-Wagner saturation table)'),
            'time_s': _pick(sol['time']),
            'tank_pressure_bar': _pick(sol['tank_pressure'], 1e-5),
            'tank_temperature_K': _pick(sol['tank_temperature']),

            # --- ÖH D26 / OH-B4-04: FAZ KANALI ALAN OLARAK ----------------
            # ÖLÇÜLEN KUSUR (once.json/OH-B4-04): 36 anahtarlık bu blokta
            # 'phase'/'tail_off'/'vapor_transition' desenine uyan TEK alan
            # yoktu; tankın fazı (two_phase | vapor) yalnız geçiş anında
            # doğan bir uyarı METNİNE ("IDEAL-GAS TAIL-OFF") gömülüydü.
            # Programatik tüketici kuyruk fazının nerede başladığını
            # okuyamıyor, ekran da eğrinin hangi bölümünün ideal-gaz kuyruğu
            # olduğunu gösteremiyordu. Değerler ÇÖZÜCÜNÜN kendi adım
            # kaydından gelir; burada yeniden türetilmez (tek kaynak).
            'tank_phase': _pick_etiket(sol.get('tank_phase')),
            'tank_phase_final': sol.get('tank_phase_final'),
            'vapor_onset_s': sol.get('vapor_onset_s'),
            'tank_phase_basis': (
                'the phase of the N2O tank at each published sample, read '
                'from the same solver step that produced the pressure and '
                'temperature above ("two_phase" = saturated liquid + vapour, '
                '"vapor" = the liquid is gone). "tank_phase_final" is the '
                'tank state AFTER the last step: "vapor" means the burn '
                'ended because the liquid ran out, which is also why '
                'end_event reads "oxidizer_depleted". "vapor_onset_s" is the '
                'instant the liquid was exhausted; it is null when the run '
                'ended for another reason, and no time is invented for that '
                'case. Beyond the onset the ideal-gas tail-off warning '
                'applies and the curve is an order-of-magnitude estimate '
                'only — that limit is stated in "warnings", this field says '
                'WHERE it starts.'),

            # --- ÖH D27 / P13B4-04: MODEL ZARFI BAYRAĞI ALAN OLARAK -------
            # ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D27/hibrit/a1/once.json``,
            # taban ``709a235e``): tankın adım durumu (``_pack_state``, 8
            # anahtar) ``vapor_model_valid`` üretiyor, bu blok 40 anahtar
            # yayımlıyordu ve bayrak İÇLERİNDE YOKTU. Çözücü dürüst bir zarf
            # bayrağı kuruyor, serileştirici onu düşürüyordu: programatik
            # tüketici yayımlanan P(t)/T(t) örneklerinin fiziksel çözüm mü
            # yoksa kenetlenmiş zarf kenarı mı olduğunu HİÇBİR alandan
            # okuyamıyordu (bilgi yalnız uyarı METNİNDEYDİ).
            #
            # İKİ AYRI ZARF ÖLÇÜLDÜ, İKİSİ DE DEĞER OLARAK YAYIMLANIR
            # (``once.json`` + ``zarf_taramasi``): ``vapor_model_valid`` bu
            # blokta YAPISAL OLARAK True'dur (yürüyüş sıvı bitince durur,
            # buhar adımı hiç integre edilmez) ve bu, gizlenmesi değil
            # SÖYLENMESİ gereken bir şeydir — künye bunu ADIYLA yazar; asıl
            # ateşlenebilen zarf, doygunluk bandı kenetlenmesidir
            # (8 bar / 245 K: 208 örneğin 70'i kenetli, ölçüldü).
            #
            # Değerler tankın KENDİ nesnesinden okunur — burada yeniden
            # türetilmez (tek kaynak; ``warnings`` birleşimiyle aynı nesne).
            'vapor_model_valid': bool(tb.tank.vapor_model_valid),
            'tank_saturation_band_clamped': bool(tb.tank.out_of_band),
            #
            # ÖH D27 fix-27a — KÜNYE METNİNDE TAAHHÜT DİLİ KULLANILMAZ.
            # Bu künyeyi ``d44f9548`` (ÖH D27 hibrit a1, defter P13B4-04)
            # getirdi ve ``vapor_model_valid`` bayrağını bir TAAHHÜT gibi
            # anlatan bir cümle taşıyordu. ``tools/iddia_lint.py``ın garanti
            # dili kuralı o satırı KAYITSIZ isabet saydı ve üç kapıyı birden
            # kırmızıya çevirdi. Satır kayıt defterine yazılarak
            # susturulabilirdi; YAZILMADI. Sebep: cümlenin söylediği şey bir
            # taahhüt değil, HANGİ KOD YOLUNUN koştuğunun beyanıdır —
            # yürüyüş sıvı bitince durur, bu yüzden buhar adımı hiç integre
            # edilmez. Kod yolu bir gün değişirse taahhüt dili metni yalan
            # kılardı, olgu dili kılmaz. Anlam korundu, yalnız kip değişti.
            'tank_model_envelope_basis': (
                'whether the tank states published above are physical '
                'solutions or clamped envelope edges. Two separate limits '
                'exist and this block reports both as VALUES, not only as '
                'warning text. (1) "vapor_model_valid" is false when the '
                'vapour tail-off ran below the N2O triple point (182.33 K / '
                '87.84 kPa, NIST WebBook), where the adiabatic ideal-gas '
                'expansion is no longer valid and pressure and temperature '
                'are clamped there. In THIS block the march stops the '
                'instant the liquid is exhausted (end_event '
                '"oxidizer_depleted"), so no vapour step is ever integrated '
                '("vapor_phase_integrated" is the measured statement of that, '
                'not an assumption) and the flag reads true for every curve '
                'this block publishes: it records which code path ran (no sample '
                'above is a triple-point-clamped value) rather than '
                'raising a live alarm. What the stop COSTS is published as numbers '
                'rather than left to the reader: "residual_oxidizer_kg" is '
                'the oxidiser still in the tank when the march stops, and '
                '"residual_impulse_at_cutoff_rate_Ns" values it at the '
                'oxidiser-specific impulse (F / mdot_ox) of the last '
                'integrated step, so the identity I = integral of '
                '(F/mdot_ox)*mdot_ox dt is applied with the cutoff rate '
                'frozen; no tail-off dynamics are invented. '
                '"residual_impulse_fraction_at_cutoff_rate" is that number '
                'over the impulse reported above (measured in this '
                'repository: 0.53 kg and 14.1 % for a 1 kN / 20 bar / '
                '293.15 K design). The reason the tail-off is not integrated '
                'is itself a decidable question and is answered in '
                '"vapor_tail_off_leaves_model_envelope": the adiabatic '
                'vapour path depends only on the remaining mass ratio '
                'r = m/m0 (P/P0 = r^gamma, T/T0 = r^(gamma-1)), so the triple '
                'point is reached at a fixed r while the flow can only stop '
                'when the tank falls to ambient pressure at another fixed r. '
                'True means the tail-off would leave the validity envelope of '
                'the tank model before the flow could stop, i.e. integrating '
                'it would publish thrust from a model that is out of envelope '
                '(measured: true in six of six scenarios). '
                '(2) "tank_saturation_band_clamped" is the limit '
                'that CAN fire here: true means at least one published '
                'sample was clamped to the edge of the 240-306 K '
                'saturation-table band (CoolProp / embedded Span-Wagner '
                'data; N2O critical point 309.52 K, NIST WebBook) and its '
                'pressure and temperature are band-edge values rather than a '
                'physical solution. Measured in this repository: a 20 bar '
                'chamber on a 293.15 K tank clamps no sample, while an 8 bar '
                'chamber on a 245 K tank clamps 70 of its 208 published '
                'samples. The clamp also raises a text warning in '
                '"warnings"; this field is the programmatic gate for it.'),

            # --- ÖH D28 / OH-D27-09: KESİLEN PAYIN DEĞER KANALI -----------
            # ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D28/hibrit/a1/once.json``,
            # taban ``7cd08bcc``): 43 anahtarlık bu blokta kesmenin BOYUNU
            # veren tek alan yoktu — altı senaryonun altısında da integre
            # edilen buhar adımı 0, ``vapor_model_valid`` altısında da True,
            # ve tankta kalan oksitleyici (nominal 0,529 kg = yayımlanan
            # impulsun %14,1'i) hiçbir kanaldan okunamıyordu. Kesme bir ürün
            # kararıdır (kuyruk modeli kendi zarfını terk ediyor), ama SESSİZ
            # olamaz. Değerler çözücünün KENDİ dönüşünden okunur — burada
            # yeniden türetilmez (tek kaynak).
            'vapor_phase_integrated': bool(sol['vapor_phase_integrated']),
            'residual_oxidizer_kg': sol['residual_oxidizer_kg'],
            'residual_impulse_at_cutoff_rate_Ns':
                sol['residual_impulse_at_cutoff_rate_Ns'],
            'residual_impulse_fraction_at_cutoff_rate':
                sol['residual_impulse_fraction_at_cutoff_rate'],
            'vapor_tail_off_leaves_model_envelope':
                sol['vapor_tail_off_leaves_model_envelope'],

            'mdot_ox_kg_s': _pick(sol['mdot_ox']),
            'thrust_N': _pick(sol['thrust']),
            'chamber_pressure_bar': _pick(sol['chamber_pressure'], 1e-5),
            'thrust_initial_N': f0,
            'thrust_final_N': f_son,
            'thrust_decay_fraction': (1.0 - f_son / f0) if f0 > 0 else None,
            'burn_duration_s': float(sol['burn_duration']),
            'total_impulse_Ns': float(sol['total_impulse']),
            'end_event': sol['end_event'],
            'warnings': blok_uyarilari,

            # --- A9: O/F kayması (bu bloğun kendi çözümünden) --------------
            'mdot_fuel_kg_s': _pick(sol['mdot_fuel']),
            'of_ratio': _pick(sol['of_ratio']),
            'of_ratio_basis': (
                'O/F(t) = mdot_ox(t) / mdot_fuel(t) taken from THIS blowdown '
                'solution: the oxidiser flow follows the falling tank '
                'pressure and the fuel flow follows the regressing port, so '
                'both drivers of the shift are present. The design point '
                'assumes a regulated feed and therefore only sees the port '
                'driver.'),
            'of_ratio_design': of_tasarim,
            'of_ratio_initial': float(of_dizi[0]),
            'of_ratio_final': float(of_dizi[-1]),
            'of_ratio_min': of_min,
            'of_ratio_max': of_max,
            'of_shift_fraction': of_sapma,
            'propellant_consumed_kg': m_harcanan,
            'isp_delivered_avg_s': isp_teslim,
            'isp_delivered_avg_basis': (
                'burn-averaged delivered specific impulse of THIS blowdown '
                'run: total impulse divided by the propellant actually '
                'consumed in the same solution (I = Isp * m * g0 holds '
                'exactly). It is NOT the design-point Isp.'),
        }

    def _of_shift_block(self, blowdown_block=None):
        """O/F'nin yanma boyunca kayması ve bunun performansa bedeli (A9).

        NEDEN VAR
        ---------
        Hibritte yakıt regresyon hızı r = a·G_ox^n olduğundan port çapı
        büyüdükçe G_ox düşer, yakıt debisi değişir ve O/F yanma boyunca KAYAR.
        Bu, hibridin en karakteristik davranışıdır — katı ve sıvı motorda
        karşılığı yoktur. Çözücü O/F(t), c*(t) ve Isp(t) serilerini zaten
        üretiyordu ama kullanıcıya yalnız dizi olarak veriyordu: "tasarım
        Isp'si" ile "yanma boyunca GERÇEKLEŞEN ortalama Isp" arasındaki farkı
        kimse hesaplamıyordu. Bu blok o farkı açıkça yayımlar.

        İKİ BESLEME DURUMU
        ------------------
        * ``regulated``: tasarım noktası çözümü — ṁ_ox SABİT, O/F'yi yalnız
          port büyümesi sürükler. Manşetteki sayılar (itki, Isp, Pc) bu
          durumun tasarım noktasıdır.
        * ``blowdown``: kendinden-basınçlı besleme — ṁ_ox da düşer, O/F'yi
          iki etki birden sürükler. Diziler ``tank_blowdown`` bloğundan
          OKUNUR, burada yeniden çözülmez (tek kaynak); blok modellenmemişse
          bu durum gerekçesiyle boş kalır ve sayı uydurulmaz.

        FARK NASIL ÖLÇÜLÜR
        ------------------
        Toplam impuls, zaman-adımlı çözümün KENDİ noktalarından trapez
        kuralıyla toplanır. v2.6.27'den ÖNCE seriler son adımın BAŞINDA
        bitiyordu (ölçüldü: itki serisi 19,9 s, port serisi 20,0 s) ve trapez
        gerçekten son dt'yi düşürüyordu; o eksiklik sol-Riemann toplamıyla
        telafi ediliyordu. Şimdi yanma sonu noktası da kaydedildiği için
        aralık [0, t_burn_effective] tam kapanıyor ve doğru integral trapez.
        Teslim edilen ortalama Isp aynı eğrinin harcadığı kütleden alınır ki
        I = Isp·m·g0 özdeşliği tutsun.
        """
        basis = (
            'the hybrid O/F shift: r = a*G_ox^n, so as the port grows G_ox '
            'falls, the fuel flow changes and O/F drifts through the burn. '
            'Every number here comes from the time-marching solution of THIS '
            'run (port regression, instantaneous fuel flow, equilibrium '
            'c*(O/F) table); nothing is shaped or assumed. Two limits are '
            'declared rather than hidden: (1) the thrust coefficient is held '
            'at its design value, so only the (much larger) c* sensitivity to '
            'O/F is captured, and (2) c* is read from an interpolated '
            'equilibrium grid whose measured error is published in the '
            '"interpolation" field. The headline design numbers are NOT '
            're-rated by this block.')

        zaman = list(getattr(self, '_time_history', []) or [])
        of_gecmis = list(getattr(self, '_of_history', []) or [])
        isp_gecmis = list(getattr(self, '_isp_history', []) or [])
        cstar_gecmis = list(getattr(self, '_cstar_history', []) or [])
        itki_gecmis = list(getattr(self, '_thrust_history', []) or [])
        mdot_gecmis = list(getattr(self, '_mdot_total_history', []) or [])
        mdot_f_gecmis = list(getattr(self, '_mdot_f_history', []) or [])

        tasarim = {
            'of_ratio': float(self.OF),
            'isp_s': float(getattr(self, 'Isp', float('nan'))),
            'c_star_m_s': float(getattr(self, 'C_star', float('nan'))),
            'burn_time_s': float(self.t_b),
            'total_impulse_Ns': float(self.F) * float(self.t_b),
            'basis': ('the design point: performance evaluated once at the '
                      'design O/F with a regulated (constant) oxidiser flow. '
                      'These are the numbers the headline panels show.'),
        }

        def _sapma_yuzde(gercek, referans):
            if gercek is None or referans in (None, 0) or not np.isfinite(referans):
                return None
            return float((gercek / referans - 1.0) * 100.0)

        if not (of_gecmis and isp_gecmis and itki_gecmis):
            # Regüleli seri yoksa blok TAMAMEN susmaz: blowdown durumu
            # bağımsız çözülmüştür ve ṁ_ox(t) oradan gelir. Susmak, var olan
            # bir hesabı kullanıcıdan saklamak olurdu.
            regulated = {
                'status': 'NOT_MODELLED',
                'reason': ('the instantaneous performance history is empty '
                           '(track_performance is off), so the regulated '
                           'O/F(t), Isp(t) and burn-averaged performance were '
                           'not computed; they are not estimated either. Run '
                           'with track_performance=True.'),
            }
            blowdown = self._of_shift_blowdown_case(
                blowdown_block, tasarim, _sapma_yuzde)
            var_mi = blowdown.get('status') != 'NOT_MODELLED'
            blok = {
                'status': 'modelled' if var_mi else 'NOT_MODELLED',
                'basis': basis,
                'design_point': tasarim,
                'regulated': regulated,
                'blowdown': blowdown,
                'interpolation': self._of_interpolation_diagnostics(),
            }
            if var_mi:
                self._emit_of_shift_warning(blok)
            return blok

        n_ornek = len(itki_gecmis)
        t_son = float(getattr(self, 't_burn_effective', self.t_b))
        # v2.6.27 B1 (kalem 4): seriler artık yanma sonu noktasını DA taşıyor
        # (t = 0, dt, ..., t_son). Eskiden son adım hiç kaydedilmiyordu ve
        # bu yüzden trapez kuralı gerçekten son dt'yi düşürüyordu; o eksikliği
        # kapatmak için sol-Riemann toplamı (Σ F_i·dt) kullanılıyordu. Aralık
        # artık tam kapandığı için doğru integral trapezdir ve iki seri (itki
        # ve port) aynı süre üzerinde tanımlıdır. Zaman dizisi ÖLÇÜLEN
        # noktalardan gelir; eşit aralık VARSAYILMAZ.
        if len(zaman) == n_ornek and n_ornek > 1:
            toplam_impuls = float(_trapezoid(itki_gecmis, zaman))
            harcanan_kutle = (float(_trapezoid(mdot_gecmis, zaman))
                              if len(mdot_gecmis) == n_ornek else 0.0)
        else:
            # Zaman dizisi eşleşmiyorsa (beklenmedik durum) tek tip adım
            # varsayımıyla sol-Riemann'a düşülür ve bu AÇIKÇA yazılır.
            dt = t_son / n_ornek if n_ornek else 0.0
            toplam_impuls = float(sum(itki_gecmis) * dt)
            harcanan_kutle = float(sum(mdot_gecmis) * dt) if mdot_gecmis else 0.0
        isp_kutle_ort = (toplam_impuls / (harcanan_kutle * self.g0)
                         if harcanan_kutle > 0 else None)
        isp_zaman_ort = float(np.mean(isp_gecmis))
        cstar_zaman_ort = float(np.mean(cstar_gecmis)) if cstar_gecmis else None

        of_tasarim = float(self.OF)
        of_min = float(min(of_gecmis))
        of_max = float(max(of_gecmis))

        regulated = {
            'feed_basis': ('regulated feed: the oxidiser mass flow is held at '
                           'the design value, so the O/F drift comes purely '
                           'from the regressing port geometry.'),
            'of_ratio_design': of_tasarim,
            'of_ratio_initial': float(of_gecmis[0]),
            'of_ratio_final': float(of_gecmis[-1]),
            'of_ratio_min': of_min,
            'of_ratio_max': of_max,
            'of_shift_fraction': (
                max(abs(of_min / of_tasarim - 1.0),
                    abs(of_max / of_tasarim - 1.0))
                if of_tasarim > 0 else None),
            'of_shift_basis': (
                'O/F(t) = mdot_ox / mdot_fuel(t) with mdot_fuel(t) = rho_f * '
                'N_port * pi * D_port(t) * L_grain * r_dot(t) from the '
                'time-marching solution. Because mdot_fuel scales as '
                'D^(1-2n), the drift direction follows the regression '
                'exponent: O/F rises for n > 0.5, falls for n < 0.5 and is '
                'flat at n = 0.5.'),
            'regression_exponent_n': float(self.n),
            'burn_time_effective_s': t_son,
            'samples': n_ornek,

            'isp_time_avg_s': isp_zaman_ort,
            'isp_mass_avg_s': isp_kutle_ort,
            'isp_mass_avg_basis': (
                'delivered burn-averaged Isp: total impulse of the curve '
                'divided by the propellant the same curve consumes '
                '(I = Isp * m * g0 holds exactly). This is the number to '
                'compare against a static-fire result; isp_time_avg_s is the '
                'unweighted time average of the instantaneous curve.'),
            'c_star_time_avg_m_s': cstar_zaman_ort,
            'total_impulse_Ns': toplam_impuls,
            'total_impulse_basis': (
                'I = trapz(F(t), t) over the time-marching samples. The '
                'series now carry the end-of-burn sample as well, so the '
                'interval [0, t_burn_effective] is fully covered and the '
                'trapezoidal rule no longer drops the final step. (Before '
                'v2.6.27 the thrust series stopped one step short of the port '
                'series — measured 19.9 s against 20.0 s on the same run — '
                'and a left-Riemann sum was used to compensate.)'),
            'propellant_consumed_kg': harcanan_kutle,

            'isp_delta_vs_design_pct': _sapma_yuzde(isp_kutle_ort,
                                                    tasarim['isp_s']),
            'isp_time_avg_delta_vs_design_pct': _sapma_yuzde(
                isp_zaman_ort, tasarim['isp_s']),
            'c_star_delta_vs_design_pct': _sapma_yuzde(
                cstar_zaman_ort, tasarim['c_star_m_s']),
            'total_impulse_delta_vs_design_pct': _sapma_yuzde(
                toplam_impuls, tasarim['total_impulse_Ns']),
            'delta_basis': (
                'each delta is (realised - design) / design x 100 with the '
                'design values in the design_point field. A non-zero delta is '
                'the cost of the O/F shift, not an error: the design point is '
                'a single instant, the realised value is the whole burn.'),
        }

        blowdown = self._of_shift_blowdown_case(
            blowdown_block, tasarim, _sapma_yuzde)

        blok = {
            'status': 'modelled',
            'basis': basis,
            'design_point': tasarim,
            'regulated': regulated,
            'blowdown': blowdown,
            'interpolation': self._of_interpolation_diagnostics(),
            'series_location': (
                'the full regulated O/F(t), c*(t) and Isp(t) series are '
                'published under of_shift_performance; this block carries the '
                'summary, the blowdown case and the interpolation diagnosis '
                'so the series are not duplicated in the response.'),
        }
        self._emit_of_shift_warning(blok)
        return blok

    @staticmethod
    def _of_shift_blowdown_case(blowdown_block, design_point, delta_pct):
        """Blowdown besleme durumunun O/F özeti — ``tank_blowdown``dan OKUNUR.

        Diziler burada YENİDEN ÇÖZÜLMEZ: ṁ_ox(t), ṁ_yakıt(t) ve O/F(t) aynı
        koşunun blowdown çözümünden gelir. İki blokta iki farklı ṁ_ox dolaşması
        (aynı motor için iki gerçeklik) bu sürümde kapatılan hata sınıfının ta
        kendisidir. Blok modellenmemişse gerekçesi taşınır, eğri uydurulmaz.
        """
        if not (isinstance(blowdown_block, dict)
                and blowdown_block.get('status') == 'modelled'
                and blowdown_block.get('of_ratio')):
            gerekce = 'no blowdown solution exists for this design'
            if isinstance(blowdown_block, dict):
                gerekce = blowdown_block.get('reason') or gerekce
            return {
                'status': 'NOT_MODELLED',
                'reason': (
                    f'the blowdown O/F history is not available: {gerekce}. '
                    f'A blowdown curve is not estimated from the regulated '
                    f'one.'),
            }
        bd_isp = blowdown_block.get('isp_delivered_avg_s')
        return {
            'feed_basis': (
                'self-pressurised (blowdown) feed: mdot_ox(t) comes from the '
                'tank_blowdown block of THIS run — the same arrays, not a '
                'second solution — so the falling tank pressure and the '
                'regressing port drive the O/F together.'),
            'source_block': 'tank_blowdown',
            'time_s': list(blowdown_block.get('time_s') or []),
            'of_ratio': list(blowdown_block['of_ratio']),
            'mdot_ox_kg_s': list(blowdown_block.get('mdot_ox_kg_s') or []),
            'mdot_fuel_kg_s': list(blowdown_block.get('mdot_fuel_kg_s') or []),
            'of_ratio_design': blowdown_block.get('of_ratio_design'),
            'of_ratio_initial': blowdown_block.get('of_ratio_initial'),
            'of_ratio_final': blowdown_block.get('of_ratio_final'),
            'of_ratio_min': blowdown_block.get('of_ratio_min'),
            'of_ratio_max': blowdown_block.get('of_ratio_max'),
            'of_shift_fraction': blowdown_block.get('of_shift_fraction'),
            'isp_delivered_avg_s': bd_isp,
            'total_impulse_Ns': blowdown_block.get('total_impulse_Ns'),
            'burn_duration_s': blowdown_block.get('burn_duration_s'),
            'end_event': blowdown_block.get('end_event'),
            'isp_delta_vs_design_pct': delta_pct(bd_isp,
                                                 design_point['isp_s']),
            'total_impulse_delta_vs_design_pct': delta_pct(
                blowdown_block.get('total_impulse_Ns'),
                design_point['total_impulse_Ns']),
        }

    def _emit_of_shift_warning(self, of_shift_block):
        """O/F kayması eşiği aşılırsa kullanıcıya ULAŞAN uyarıyı üretir (A9-4).

        Eşik ``OF_SHIFT_WARN_FRACTION`` TEK yerde tanımlıdır ve uyarı
        parametresi olarak aynen yayımlanır (kopya eşik yasak). Modellenen
        besleme durumlarının EN KÖTÜSÜ karar verir: regüleli beslemede kayma
        eşiğin altında kalıp blowdown'da aşılabilir, o durumda susmak
        kullanıcıyı yanıltırdı.

        ``_compile_results`` birden çok kez çağrılabildiği için aynı uyarı
        iki kez eklenmez.

        Bir besleme durumu ancak Isp sapmasını da SAYIYLA verebiliyorsa aday
        olur: sözlük metni ``{isp_delta_pct}`` yer tutucusunu taşıdığından
        sayısız bir uyarı ekranda "%None" basardı. Hiçbir aday kalmazsa uyarı
        üretilmez ve nedeni bloğa yazılır — sessizce yutulmaz.
        """
        kod = 'warn.hybrid.of_shift_large'
        mevcut = getattr(self, 'design_warnings', None)
        if mevcut is None:
            return
        if any(k.get('code') == kod for k in mevcut):
            return

        en_kotu = None
        eksik_isp = []
        for ad in ('regulated', 'blowdown'):
            durum = of_shift_block.get(ad)
            if not isinstance(durum, dict):
                continue
            oran = durum.get('of_shift_fraction')
            if oran is None or not np.isfinite(oran):
                continue
            if oran <= OF_SHIFT_WARN_FRACTION:
                continue
            isp_sapma = durum.get('isp_delta_vs_design_pct')
            if isp_sapma is None:
                isp_sapma = durum.get('isp_time_avg_delta_vs_design_pct')
            if isp_sapma is None or not np.isfinite(isp_sapma):
                eksik_isp.append(ad)
                continue
            if en_kotu is None or oran > en_kotu[1]:
                en_kotu = (ad, float(oran), durum, float(isp_sapma))

        if en_kotu is None:
            if eksik_isp:
                of_shift_block['warning_suppressed_reason'] = (
                    'the O/F excursion exceeds the threshold in '
                    f'{", ".join(eksik_isp)}, but the burn-averaged Isp of '
                    'that case could not be computed, so the warning would '
                    'have carried an empty performance figure. The excursion '
                    'itself is reported in this block.')
            return

        ad, oran, durum, isp_sapma = en_kotu
        # Kod BURADA sabit yazılır (yukarıdaki `kod` değişkeni yalnız
        # yinelenme denetimi içindir): yayın kapısı ham metin uyarı avında
        # `_w`nin ilk argümanını STATİK olarak okur ve yerel değişkeni
        # izleyemez, izlemesi de istenmez — değişken üzerinden geçmek
        # denetimi kör eder (test_v262_release_gate.TestWarningContract).
        mevcut.append(_w(
            'warn.hybrid.of_shift_large', 'warning',
            feed_mode=ad,
            of_design=round(float(self.OF), 2),
            of_min=round(float(durum.get('of_ratio_min', self.OF)), 2),
            of_max=round(float(durum.get('of_ratio_max', self.OF)), 2),
            shift_pct=round(oran * 100.0, 1),
            threshold_pct=round(OF_SHIFT_WARN_FRACTION * 100.0, 1),
            isp_delta_pct=round(isp_sapma, 2)))

    def _thermal_protection_block(self, heat_transfer_results):
        """Kamara yalıtım astarı + çıplak cidar ısı-yutucu geçmişi (A5).

        FİZİK KÜNYESİ
        -------------
        * Astar boyutlandırma: Seviye-1 Q* (ablasyon ısısı) modeli,
          ṡ = q_net/(ρ·Q*), gereken kalınlık = toplam çekilme × tasarım payı
          (NASA SP-8093 sınıfı; Sutton & Biblarz 9. baskı Böl. 8.5) —
          hrma.analysis.thermal_protection.ThermalProtectionAnalyzer.
          ablative_thickness. Katı motorun kapak yalıtımı bağlanma deseniyle
          AYNI şema (alan adları solid _ablative_liner_sizing ile birebir).
        * Cidar sıcaklık geçmişi: 1B explicit FD ısı-yutucu çözümü
          (Incropera & DeWitt 6. baskı §5.10; Sutton & Biblarz Böl. 8.4) —
          aynı modülün heat_sink_transient'i, store_history=True.

        GİRDİLER MOTORUN KENDİ ZİNCİRİNDEN GELİR: kamara/boğaz ısı akıları,
        kurtarma sıcaklığı ve referans cidar sıcaklığı analyze_heat_transfer
        sonucundan (Bartz + Leckner), yanma süresi zaman-adımlı çözücünün
        etkin süresi, cidar kalınlığı/malzemesi kullanıcının termal modele
        giden değerleridir. Girdi eksikse blok SAYI İÇERMEZ: status
        NOT_MODELLED + gerekçe döner (sahte kalınlık, kalınlıksızlıktan
        kötüdür).
        """
        basis = (
            'chamber insulation liner sized with the Level-1 Q* ablation '
            'model (hrma/analysis/thermal_protection.py, NASA SP-8093-class '
            'band; Sutton & Biblarz 9th ed. Ch. 8.5) and a bare-wall 1-D '
            'explicit-FD heat-sink temperature history (same module, '
            'Incropera & DeWitt 6th ed. Sec. 5.10). All driving inputs are '
            'THIS run\'s solver values: Bartz+Leckner chamber/throat design '
            'fluxes, the recovery temperature and the reference wall '
            'temperature from the heat transfer analysis, the effective '
            'time-marching burn time, and the user wall thickness/material. '
            'The liner sizing and the wall history are NOT coupled: the '
            'history is the UNPROTECTED wall (no liner credit) and shows '
            'why the liner is needed.')
        if self.uq_mode:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': ('skipped in uq_mode (advisory block, same policy '
                           'as the blowdown and altitude tables); run the '
                           'nominal design for the thermal protection '
                           'sizing.'),
            }
        gs = (heat_transfer_results or {}).get('gas_side_analysis') or {}
        q_chamber = gs.get('chamber_heat_flux')      # W/m²
        q_throat = gs.get('throat_heat_flux')        # W/m²
        taw = gs.get('adiabatic_wall_temperature')   # K
        tw_ref = gs.get('reference_wall_temperature')  # K
        t_burn = float(getattr(self, 't_burn_effective', 0.0)
                       or getattr(self, 't_b', 0.0) or 0.0)
        eksik = [ad for ad, deger in (
            ('chamber_heat_flux', q_chamber), ('throat_heat_flux', q_throat),
            ('adiabatic_wall_temperature', taw),
            ('reference_wall_temperature', tw_ref)) if not (
                deger is not None and np.isfinite(float(deger))
                and float(deger) > 0)]
        if eksik or t_burn <= 0:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (
                    'the thermal protection sizing needs the heat transfer '
                    'analysis (Bartz fluxes / recovery temperature) and a '
                    'positive burn time; missing or non-physical in this '
                    'run: ' + ', '.join(eksik + (
                        ['burn_time'] if t_burn <= 0 else []))),
            }
        q_chamber = float(q_chamber)
        q_throat = float(q_throat)
        taw = float(taw)
        tw_ref = float(tw_ref)
        try:
            from hrma.analysis.thermal_protection import (
                ThermalProtectionAnalyzer)
            analyzer = ThermalProtectionAnalyzer()
        except Exception as exc:                       # pragma: no cover
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': f'thermal protection module unavailable: {exc}',
            }

        # --- İSTASYON GİRDİLERİ: gaz tarafı katsayısı + yarıçap ------------
        # (v2.6.27 ablasyon teşhisi — sıvı motorla AYNI şema.) Astar artık
        # çağıranın soğuk-cidar akısıyla değil YÜZEY ENERJİ DENGESİYLE
        # boyutlandırılır. Katsayılar bu koşunun kendi akılarından CEBİRSEL
        # geri çözümdür (ikinci bir Bartz hesabı yapılmaz; ısı-yutucu geçmişi
        # de aynı kamara katsayısını kullanır — tek istasyon, tek h_g):
        #   h_kamara = q_kamara/(T_aw − T_cidar_ref)
        #   h_boğaz  = q_boğaz /(T_aw − T_cidar_ref)
        # Sürücü sıcaklık: T_aw (ısı analizinin kendi kurtarma sıcaklığı).
        # Yarıçaplar geometrik kapı içindir: kamara için hazne iç yarıçapı,
        # lüle girişi için boğaz yarıçapı — giriş kesiti boğazdan geniştir,
        # yani kapı MUHAFAZAKÂR alt sınırla denetler (akı beyanıyla tutarlı:
        # o da boğaz akısıyla ÜST sınırdan boyutlar). Sürücü fark pozitif
        # değilse parametreler HİÇ geçilmez (çekirdek yarım çifti kabul
        # etmez) ve eski yol beyanlı biçimde korunur.
        def _pozitif(deger, olcek=1.0):
            try:
                v = float(deger)
            except (TypeError, ValueError):
                return None
            return v * olcek if np.isfinite(v) and v > 0 else None

        _fark = taw - tw_ref
        h_kamara = _pozitif(q_chamber / _fark) if _fark > 0 else None
        h_bogaz = _pozitif(q_throat / _fark) if _fark > 0 else None
        r_kamara = _pozitif(getattr(self, 'D_ch', None), 0.5)
        r_bogaz = _pozitif(getattr(self, 'd_t', None), 0.5)
        # v2.6.27 blokaj denetimi: kenar gazı c_p'si, akıları üreten AYNI
        # ısı transferi analizinin kendi gaz özelliklerinden gelir (B'yi
        # bölen c_p ile h_g'yi üreten c_p aynı olmak zorunda — parametre
        # tutarlılığı). Yoksa çekirdek psi = 1 (blokajsız, konservatif)
        # kullanır ve blockage_basis'te beyan eder.
        cp_gaz = _pozitif(((heat_transfer_results or {})
                           .get('heat_transfer_coefficients') or {})
                          .get('gas_cp'))

        def _liner(station, function, q_W_m2, station_note,
                   h_gas, h_gas_source, radius_m, radius_source):
            """Tek istasyon astar boyutu — sıvı/katı ile AYNI alan adları.

            ``h_gas`` verilirse çekirdek yüzey enerji dengesini çözer ve
            geçerlilik kapısı bağlayıcıdır (NOT_MODELLED hükmü AYNEN taşınır,
            sayı uydurulmaz); verilmezse eski yol birebir korunur.
            """
            ek = {}
            if h_gas is not None:
                # Çift HALİNDE geçilir: yarım geçiş çekirdekte ValueError.
                ek['h_gas_W_m2K'] = h_gas
                ek['T_recovery_K'] = taw
                if cp_gaz is not None:
                    ek['gas_cp_J_kgK'] = cp_gaz
            if radius_m is not None:
                ek['station_radius_m'] = radius_m
            try:
                sizing = analyzer.ablative_thickness(
                    q_net_W_m2=q_W_m2,
                    burn_time_s=t_burn,
                    material=LINER_MATERIAL_DEFAULT,
                    **ek)
            except Exception as exc:
                return {
                    'material': LINER_MATERIAL_DEFAULT,
                    'thickness': None,
                    'thickness_status': 'NOT_MODELLED',
                    'function': function,
                    'basis': f'Ablative sizing failed at the {station}: {exc}',
                }
            enerji_dengesi = (
                sizing['flux_basis'] == 'surface_energy_balance')
            kalinlik_mm = sizing['required_thickness_mm']
            if kalinlik_mm is None:
                # Çekirdeğin kapısı kalınlığı kesti: hüküm 'sized'a
                # çevrilmez, gerekçe kullanıcıya aynen taşınır.
                yaricap_ifadesi = (
                    'no station radius was available, so only the recession '
                    'rate ceiling was checked' if radius_m is None else
                    f'station radius {radius_m * 1e3:.1f} mm '
                    f'({radius_source})')
                liner_basis = (
                    f'Level-1 Q* ablation sizing was RUN at the {station} '
                    f'but published NO thickness. '
                    f"{sizing['validity_note']} "
                    f'Inputs are this run\'s solver values: gas-side '
                    f'coefficient {h_gas:.0f} W/m2K ({h_gas_source}), '
                    f'recovery temperature {taw:.0f} K (the heat transfer '
                    f'analysis of this run), burn time {t_burn:.2f} s, '
                    f'{yaricap_ifadesi}. ' + station_note)
            else:
                liner_basis = (
                    f"Level-1 Q* ablation sizing at the {station}: required "
                    f"thickness = total recession x design margin "
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
                        f'{taw:.0f} K. The cold-wall design flux '
                        f'({q_W_m2 / 1e3:.0f} kW/m2) is reported for '
                        f'COMPARISON only, it is not what sized this liner. ')
                       if enerji_dengesi else (
                        f'Heat flux ({q_W_m2 / 1e3:.0f} kW/m2) is this run\'s '
                        f'solver value and is used AS GIVEN: no surface '
                        f'energy balance was solved for this station. '))
                    + f'Burn time ({t_burn:.2f} s) is this run\'s effective '
                    f"time-marching value. Liner material "
                    f"'{LINER_MATERIAL_DEFAULT}' is a declared design "
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
                # Çağıranın (soğuk cidar) akısı — yeni yolda karşılaştırma
                # değeridir, boyutlandıran değer değildir.
                'heat_flux_kw_m2': q_W_m2 / 1e3,
                'burn_time_s': t_burn,
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
                'station_radius_m': sizing['station_radius_m'],
                'station_radius_source': (None if radius_m is None
                                          else radius_source),
                'model_valid': bool(sizing['model_valid']),
                'validity_note': sizing['validity_note'],
                'basis': liner_basis,
                'model_note': sizing['model_note'],
                'source': sizing['source'],
                'surface_source': sizing['surface_source'],
            }

        chamber_liner = _liner(
            'pre/post-combustion chamber wall',
            'Protect the chamber sections whose wall sees combustion gas '
            'directly (pre- and post-combustion chambers)',
            q_chamber,
            'Over the grain itself the FUEL is the ablator; this liner '
            'covers the chamber sections not shielded by fuel. Flux is the '
            'Bartz CHAMBER-station design flux of this run.',
            h_kamara,
            'chamber coefficient of this run, recovered from the chamber '
            'design flux: h_g = q_chamber/(T_aw - T_wall_ref)',
            r_kamara,
            'chamber inner radius of this run')
        nozzle_entry_liner = _liner(
            'aft mixing chamber / nozzle entry',
            'Protect the convergent entry region ahead of the throat',
            q_throat,
            'Flux is the Bartz THROAT design flux: the nozzle-entry flux is '
            'below the throat value, so this thickness is a conservative '
            'UPPER bound, not a station-resolved value (same declaration '
            'the solid engine makes for its closures). The geometric gate '
            'uses the THROAT radius, a conservative lower bound of the '
            'entry passage.',
            h_bogaz,
            'throat coefficient of this run, recovered from the throat '
            'design flux: h_g = q_throat/(T_aw - T_wall_ref)',
            r_bogaz,
            'throat radius solved by this run')

        # --- Çıplak cidar ısı-yutucu sıcaklık geçmişi ----------------------
        # Sürücü katsayı, ısı modülünün KENDİ kamara tasarım akısından geri
        # çözülür: h_eff = q_kamara/(Taw − Tw_ref). Bu, Leckner gaz
        # radyasyonunu da taşınım katsayısına KATLANMIŞ hâlde taşır ve öyle
        # beyan edilir (ikinci bir Bartz hesabı YAPILMAZ — tek kaynak).
        wall_history = None
        if taw - tw_ref <= 0:
            wall_history = {
                'status': 'NOT_MODELLED',
                'reason': ('recovery temperature does not exceed the '
                           'reference wall temperature; no positive driving '
                           'potential exists to reconstruct h_eff from.'),
            }
        else:
            h_eff = q_chamber / (taw - tw_ref)
            # Ortam/başlangıç sıcaklığı ısı modülünün FİİLEN kullandığı
            # değerden okunur (tek kaynak; iki modül iki farklı ortam
            # varsayamaz). Yoksa parametre hiç GEÇİLMEZ ve modülün kendi
            # varsayılanı geçerli olur — buradan ikinci sayı uydurulmaz.
            hs_kwargs = {}
            t_initial_source = ('thermal_protection module default '
                                '(no ambient value was available from the '
                                'heat transfer analysis)')
            try:
                t0 = float(heat_transfer_results['design_parameters']
                           ['ambient_temperature'])
                if np.isfinite(t0) and t0 > 0:
                    hs_kwargs['T_initial_K'] = t0
                    t_initial_source = (
                        'the ambient temperature the heat transfer analysis '
                        'actually used (single source)')
            except (KeyError, TypeError, ValueError):
                pass
            try:
                hs = analyzer.heat_sink_transient(
                    h_gas_W_m2K=h_eff,
                    T_recovery_K=taw,
                    burn_time_s=t_burn,
                    wall_thickness_m=float(self.wall_thickness),
                    wall_material=self.chamber_material,
                    store_history=True,
                    **hs_kwargs)
            except Exception as exc:
                wall_history = {
                    'status': 'NOT_MODELLED',
                    'reason': f'heat-sink transient could not run: {exc}',
                }
            else:
                # ~WALL_HISTORY_MAX_POINTS noktaya seyreltme (port_history
                # deseni): son nokta daima korunur.
                hist = hs.get('history') or {}
                t_list = list(hist.get('t_s') or [])
                tw_list = list(hist.get('T_inner_K') or [])
                idx = []
                if t_list:
                    stride = max(1, len(t_list) // WALL_HISTORY_MAX_POINTS)
                    idx = list(range(0, len(t_list), stride))
                    if idx[-1] != len(t_list) - 1:
                        idx.append(len(t_list) - 1)
                wall_history = {
                    'status': 'modelled',
                    'wall_material': hs['wall_material'],
                    'material_name': hs['material_name'],
                    'wall_thickness_m': hs['wall_thickness_m'],
                    'h_eff_W_m2K': float(h_eff),
                    'h_eff_basis': (
                        'effective gas-side coefficient reconstructed from '
                        'the heat transfer analysis of this run: h_eff = '
                        'chamber design flux / (T_recovery - T_wall_ref). '
                        'It therefore LUMPS the Leckner gas-radiation share '
                        'into a convection coefficient; no second Bartz '
                        'evaluation is made (single source).'),
                    'T_recovery_K': hs['T_recovery_K'],
                    'T_initial_K': hs['T_initial_K'],
                    'T_initial_source': t_initial_source,
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
                        'history — no liner credit, gas side directly on '
                        'the wall. It bounds the no-liner case and shows '
                        'why the liner sized above is needed; liner '
                        'ablation and wall conduction are NOT coupled.'),
                }

        return {
            'status': 'modelled',
            '_basis': basis,
            'burn_time_s': t_burn,
            'burn_time_source': (
                'effective time-marching burn time (web/oxidizer limited)'
                if getattr(self, '_web_exhausted', False)
                else 'design burn time (time-marching completed the full '
                     'requested burn)'),
            'chamber_liner': chamber_liner,
            'nozzle_entry_liner': nozzle_entry_liner,
            'wall_temperature_history': wall_history,
        }

    def _launch_site_block(self):
        """Fırlatma sahası rakım/ortam düzeltmesi (yol haritası A8).

        FİZİK KÜNYESİ
        -------------
        * Saha atmosferi: USSA 1976 (hrma.constants ISA yardımcıları,
          hrma.analysis.launch_site.atmosphere_at üzerinden — sıvı/katı
          irtifa tablolarının kullandığı AYNI tek kaynak).
        * Yerel yerçekimi: WGS84 Somigliana + serbest-hava açılımı
          (NIMA TR8350.2 Denk. 4-1/4-3, launch_site.local_gravity).
        * İtki düzeltmesi: F = ṁ·v_e + (P_e − P_a)·A_e (Sutton & Biblarz
          9. baskı Denk. 2-14). Ortam basıncı yalnız basınç-itki terimine
          girer; ṁ, Pc, c* kamara büyüklükleridir ve değişmez. Dolayısıyla
          F_saha − F_tasarım = (P_a,tasarım − P_a,saha)·A_e — genişleme
          oranı kullanıcı vermiş olsun olmasın geçerli bir özdeşliktir.

        KRİTİK AYRIM (launch_site modülünün sözleşmesi): Isp ZİNCİRİ
        STANDART g0 = 9.80665 İLE KALIR. Yerel g yalnız ağırlık/T-W
        büyüklüklerine girer; burada hiçbir Isp yerel g ile bölünmez.

        Saha girdisi yoksa blok sayı içermez (status NOT_MODELLED).
        """
        basis = (
            'site ambient correction of the delivered design point using '
            'hrma/analysis/launch_site.py (USSA 1976 atmosphere via the '
            'same central ISA helpers the liquid/solid altitude tables '
            'use; WGS84 normal gravity, NIMA TR8350.2). Thrust correction '
            'is the pressure-thrust identity F_site = F_design + '
            '(P_a_design - P_a_site) * A_e (Sutton & Biblarz 9th ed. '
            'Eq. 2-14): ambient pressure enters ONLY the pressure-thrust '
            'term; mdot, Pc and c* are chamber quantities and unchanged. '
            'Isp is reported with STANDARD g0 = 9.80665 m/s2 regardless '
            'of the site (Isp is an engine property, not a site property); '
            'local gravity is published separately for weight/T-W use.')
        if self.uq_mode:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': ('skipped in uq_mode (advisory block, same policy '
                           'as the blowdown and altitude tables).'),
            }
        site = self.launch_site_input
        if not site:
            gecersiz = getattr(self, '_launch_site_raw_invalid', None)
            if gecersiz is not None:
                sebep = (
                    f'the launch_site input was not a usable dict '
                    f'(got {gecersiz!r}); expected a resolve_launch_site() '
                    f'result or at least elevation_m or latitude_deg + '
                    f'longitude_deg. The design point keeps the constructor '
                    f'ambient pressure P_a as-is.')
            else:
                sebep = ('no launch site was supplied (launch_site input '
                         'absent); the design point keeps the constructor '
                         'ambient pressure P_a as-is.')
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': sebep,
            }
        ae = getattr(self, 'Ae', None)
        mdot = getattr(self, 'mdot_total', None)
        if not (ae and np.isfinite(float(ae)) and float(ae) > 0
                and mdot and np.isfinite(float(mdot)) and float(mdot) > 0):
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': ('the nozzle exit area / mass flow are not solved '
                           'yet; run calculate() before the site '
                           'correction.'),
            }
        try:
            from hrma.analysis.launch_site import (
                atmosphere_at, local_gravity, resolve_launch_site)
        except Exception as exc:                       # pragma: no cover
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': f'launch_site module unavailable: {exc}',
            }

        def _num(anahtar):
            deger = site.get(anahtar)
            try:
                deger = float(deger)
            except (TypeError, ValueError):
                return None
            return deger if np.isfinite(deger) else None

        lat = _num('latitude_deg')
        lon = _num('longitude_deg')
        elev = _num('elevation_m')
        p_site_pa = _num('pressure_pa')
        t_site_k = _num('temperature_k')
        g_local = _num('gravity_local_m_s2')

        # --- D15/P1B2-06 · SAHA GİRDİSİ KAPISI ---------------------------
        # ÖLÇÜLDÜ (a3/once.json, B2_06): bu blokta HİÇBİR girdi kapısı
        # yoktu; kurucu yalnız "boş olmayan sözlük mü" diye bakıyordu.
        # Sonuç, hepsi status='modelled' ve tek uyarısız:
        #   elevation_m = -100000 -> ambient 50 137 275,8 Pa,
        #                            thrust_site_N = -175 193,63 N,
        #                            isp_site_s   = -14 171,99 s
        #   pressure_pa = 1e9     -> thrust_site_N = -3 557 861,59 N,
        #                            isp_site_s   = -287 807,14 s
        #   pressure_pa = -50000  -> ambient_pressure_pa = -50 000,0 ile
        #                            F_site = 3534,18 N (tasarımdan yüksek)
        #   temperature_k = -300  -> aynen yayımlanıyor
        #   latitude_deg = 400    -> sessizce kutba kelepçelenip
        #                            g_local = 9,832185 üretiliyor
        # NEGATİF İTKİ ve NEGATİF ÖZGÜL İMPULS fiziksel olarak yoktur.
        # Kardeş kanallar (closure_bolt_count, feed_line_length_m) bandı
        # aşan girdiyi zaten reddedip ``_defaults_used``'a
        # ``alan(out_of_range:değer)`` iziyle yazıyor; desen depoda VAR,
        # bu kanala uygulanmamıştı.
        #
        # Bantların TEK KAYNAĞI: yeni sayı UYDURULMAZ.
        #   * rakım      -> LAUNCH_SITE_ELEVATION_RANGE_M (aşağıda, kaynaklı)
        #   * basınç     -> AYNI atmosfer modelinin o rakım bandındaki
        #                   kendi değerleri (atmosphere_at ile türetilir)
        #   * sıcaklık   -> LAUNCH_SITE_TEMPERATURE_RANGE_K (WMO uçları)
        #   * enlem/boylam -> geometrik tanım ([-90,90] / [-180,180])
        #   * yerel g    -> WGS84 normal yerçekiminin kendi uçları
        #                   (normal_gravity(0) .. normal_gravity(90))
        _el_lo, _el_hi = LAUNCH_SITE_ELEVATION_RANGE_M
        _t_lo, _t_hi = LAUNCH_SITE_TEMPERATURE_RANGE_K
        try:
            _p_hi = float(atmosphere_at(_el_lo)['pressure_pa'])
            _p_lo = float(atmosphere_at(_el_hi)['pressure_pa'])
            _g_lo = float(local_gravity(0.0, _el_hi))
            _g_hi = float(local_gravity(90.0, _el_lo))
        except Exception as exc:                       # pragma: no cover
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': ('the launch-site input bands could not be '
                           f'derived from the atmosphere model: {exc}'),
            }
        _kapilar = (
            ('elevation_m', elev, _el_lo, _el_hi, 'm',
             'a launch site stands on the solid surface of the Earth; the '
             'band spans the lowest dry land (Dead Sea shore) to above the '
             'highest summit'),
            ('pressure_pa', p_site_pa, _p_lo, _p_hi, 'Pa',
             'the band is the SAME USSA 1976 atmosphere used by this block, '
             'evaluated at the two ends of the elevation band - no separate '
             'pressure limit is invented'),
            ('temperature_k', t_site_k, _t_lo, _t_hi, 'K',
             'WMO-recognised extremes of surface air temperature on Earth '
             '(Vostok 184.0 K, Furnace Creek 329.9 K), widened to whole '
             'degrees'),
            ('latitude_deg', lat, -90.0, 90.0, 'deg',
             'geometric definition of geodetic latitude'),
            ('longitude_deg', lon, -180.0, 180.0, 'deg',
             'geometric definition of longitude'),
            ('gravity_local_m_s2', g_local, _g_lo, _g_hi, 'm/s2',
             'WGS84 normal gravity spans equator to pole; nothing on Earth '
             'lies outside it'),
        )
        for _ad, _deger, _lo, _hi, _birim, _dayanak in _kapilar:
            if _deger is None:
                continue
            if not (_lo <= _deger <= _hi):
                self._defaults_used.append(
                    f'launch_site.{_ad}(out_of_range:{_deger:g})')
                return {
                    'status': 'NOT_MODELLED',
                    '_basis': basis,
                    'reason': (
                        f"launch_site.{_ad} = {_deger:g} {_birim} is outside "
                        f"the physically possible band [{_lo:g}, {_hi:g}] "
                        f"{_birim}, so no site correction is published for "
                        f"this run ({_dayanak}). Correct the field or omit "
                        f"it; the site thrust and specific impulse are NOT "
                        f"extrapolated outside the band."),
                    'rejected_field': f'launch_site.{_ad}',
                    'rejected_value': float(_deger),
                    'accepted_band': [float(_lo), float(_hi)],
                    'accepted_band_unit': _birim,
                }
        # Ham sözlükte sayıya çevrilemeyen anahtar varsa sessizce
        # yutulmaz: alan adıyla bildirilir (0 veya '' bir SAYI DEĞİLDİR
        # ama None ile aynı anlama da gelmez).
        for _ad in ('elevation_m', 'pressure_pa', 'temperature_k',
                    'latitude_deg', 'longitude_deg', 'gravity_local_m_s2'):
            if _ad in site and site.get(_ad) is not None \
                    and _num(_ad) is None:
                self._defaults_used.append(
                    f'launch_site.{_ad}(invalid:{site.get(_ad)!r})')
                return {
                    'status': 'NOT_MODELLED',
                    '_basis': basis,
                    'reason': (
                        f"launch_site.{_ad} = {site.get(_ad)!r} is not a "
                        f"finite number, so no site correction is published "
                        f"for this run. Correct the field or omit it."),
                    'rejected_field': f'launch_site.{_ad}',
                }
        try:
            if p_site_pa is not None and t_site_k is not None:
                site_source = ('caller-resolved site dict '
                               '(resolve_launch_site schema: pressure and '
                               'temperature taken as given)')
                if elev is None:
                    elev = 0.0
                    site_source += ('; elevation_m was not supplied and is '
                                    'reported as 0')
            elif elev is not None:
                atm = atmosphere_at(elev)
                p_site_pa = atm['pressure_pa']
                t_site_k = atm['temperature_k']
                site_source = ('ISA (USSA 1976) standard-day atmosphere at '
                               'the supplied site elevation')
            elif lat is not None and lon is not None:
                cozum = resolve_launch_site(lat, lon, use_online=False)
                elev = float(cozum['elevation_m'])
                p_site_pa = float(cozum['pressure_pa'])
                t_site_k = float(cozum['temperature_k'])
                if g_local is None:
                    g_local = float(cozum['gravity_local_m_s2'])
                site_source = (
                    'resolve_launch_site(lat, lon) offline: '
                    f"elevation source '{cozum['elevation_source']}', "
                    f"atmosphere source '{cozum['atmosphere_source']}'")
            else:
                return {
                    'status': 'NOT_MODELLED',
                    '_basis': basis,
                    'reason': (
                        'the launch_site dict carries none of the usable '
                        'key sets: {pressure_pa, temperature_k}, '
                        '{elevation_m} or {latitude_deg, longitude_deg}.'),
                }
            if g_local is None and lat is not None:
                g_local = float(local_gravity(lat, elev or 0.0))
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': f'the site could not be resolved: {exc}',
            }

        p_design_pa = float(self.P_a) * 1e5
        ae = float(ae)
        mdot = float(mdot)
        thrust_delta = (p_design_pa - float(p_site_pa)) * ae
        f_site = float(self.F) + thrust_delta
        isp_site = f_site / (mdot * self.g0)
        return {
            'status': 'modelled',
            '_basis': basis,
            'site_source': site_source,
            'elevation_m': float(elev) if elev is not None else None,
            'latitude_deg': lat,
            'longitude_deg': lon,
            'ambient_pressure_pa': float(p_site_pa),
            'ambient_pressure_bar': float(p_site_pa) / 1e5,
            'ambient_temperature_k': float(t_site_k),
            'design_ambient_pressure_bar': float(self.P_a),
            'design_ambient_pressure_basis': (
                'the constructor atmospheric_pressure input the nozzle was '
                'expanded against; the delta below is measured from it'),
            'thrust_design_N': float(self.F),
            'thrust_site_N': float(f_site),
            'thrust_delta_N': float(thrust_delta),
            'thrust_change_percent': (100.0 * thrust_delta / float(self.F)
                                      if self.F else None),
            'isp_design_s': float(self.Isp),
            'isp_site_s': float(isp_site),
            'gravity_standard_m_s2': float(self.g0),
            'gravity_local_m_s2': (float(g_local) if g_local is not None
                                   else None),
            'gravity_basis': (
                'Isp and the ideal delta-v chain use STANDARD g0 = 9.80665 '
                'm/s2 at every site (BIPM definition; the launch_site '
                'module contract). gravity_local_m_s2 is the WGS84 '
                'Somigliana + free-air value for weight and thrust-to-'
                'weight use only'
                + ('' if g_local is not None else
                   '; it is None because no latitude was supplied and '
                   'local gravity is latitude-dependent — it is not '
                   'fabricated')),
            'not_modelled': [
                'nozzle flow separation is not re-assessed at the site '
                'ambient pressure; the nozzle design block carries its own '
                'separation check at the design ambient',
                'range safety / trajectory coupling of the site is the '
                'launch-site page, not this block',
            ],
        }

    def _oxidizer_tank_slosh_block(self, blowdown_block=None):
        """Oksitleyici tankı çalkantı (slosh) analizi (yol haritası A2).

        FİZİK KÜNYESİ
        -------------
        Dik dairesel silindirik tankta doğrusal serbest yüzey çalkantısı:
        ω₁² = (λ₁·g/R)·tanh(λ₁·h/R), kütle oranı SP-106 eşdeğer mekanik
        modeli, Miles (1958) halka bafl sönümleme kestirimi — NASA SP-106
        (Abramson 1966) / Dodge 2000 / NASA SP-8009;
        hrma.analysis.slosh_analysis.analyze_slosh (app.py'nin
        /api/slosh-analysis ucuyla AYNI çözücü ve şema).

        GİRDİLER: tank hacmi ve doluluk oranı blowdown bloğundan (aynı
        tank için iki farklı hacim OLAMAZ; blowdown koşamadıysa aynı
        boyutlandırma formülü beyanla uygulanır), sıvı kütlesi çözücünün
        m_ox'u, tank çapı beyanlı L/D tasarım oranından. g_eff SABİT 1 g'dir
        ve öyle beyan edilir — uçuş ivmesiyle (g_eff = T/m) bağlaşım
        yörünge bağlamasına bırakılmıştır (NOT_MODELLED notu blokta).
        """
        basis = (
            'linear free-surface slosh of the oxidizer liquid in an upright '
            'rigid circular-cylindrical tank '
            '(hrma/analysis/slosh_analysis.py: NASA SP-106 / Dodge 2000 '
            'modal relations, Miles 1958 ring-baffle damping estimate; the '
            'same solver and schema as the /api/slosh-analysis endpoint). '
            'Tank volume and fill fraction come from the tank_blowdown '
            'block of THIS run (one tank, one volume); the tank diameter '
            'follows from the declared L/D design ratio; the liquid mass '
            'is the solver m_ox. g_eff is the constant standard 1-g value '
            '(see g_eff_basis).')
        if self.uq_mode:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': ('skipped in uq_mode (advisory block, same policy '
                           'as the blowdown and altitude tables).'),
            }
        m_ox = getattr(self, 'm_ox', None)
        if not (m_ox and np.isfinite(float(m_ox)) and float(m_ox) > 0):
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': ('the oxidizer mass is not solved yet; run '
                           'calculate() before the slosh block.'),
            }
        m_ox = float(m_ox)

        # --- Tank hacmi: blowdown bloğu tek doğruluk kaynağı ---------------
        blowdown = blowdown_block or {}
        v_tank = None
        fill = None
        if blowdown.get('status') == 'modelled':
            try:
                v_tank = float(blowdown['tank_volume_m3'])
                fill = float(blowdown['liquid_fill_fraction'])
            except (KeyError, TypeError, ValueError):
                v_tank = None
        if v_tank and v_tank > 0 and fill and 0 < fill <= 1:
            v_liquid = v_tank * fill
            rho_liquid = m_ox / v_liquid
            volume_source = (
                'tank_blowdown block of this run (one tank, one volume); '
                'the liquid density is the value implied by that sizing '
                '(m_ox / liquid volume, i.e. the N2O EOS rho_l at the tank '
                'temperature)')
        else:
            # Blowdown koşamadı (ör. N2O dışı oksitleyici): AYNI formül,
            # çözücünün besleme sıvı yoğunluğuyla — V = (m_ox/rho_l)/doluluk.
            rho_liquid = getattr(self, '_inj_rho_ox', None)
            try:
                rho_liquid = float(rho_liquid)
            except (TypeError, ValueError):
                rho_liquid = None
            if not (rho_liquid and np.isfinite(rho_liquid)
                    and rho_liquid > 0):
                rho_liquid = float(self._get_oxidizer_density())
            fill = TANK_FILL_FRACTION_DEFAULT
            v_liquid = m_ox / rho_liquid
            v_tank = v_liquid / fill
            volume_source = (
                'the blowdown model did not run for this design, so the '
                'SAME sizing formula is applied directly: V = (m_ox / '
                'rho_l) / liquid fill fraction, with the feed liquid '
                'density the solver used for injector sizing and the '
                'declared default fill fraction')

        # --- Tank geometrisi: beyanlı L/D oranından ------------------------
        # V = (π/4)·D²·L = (π/4)·D³·(L/D)  →  D = (4V/(π·(L/D)))^(1/3)
        # (sıvı motorun tank boyutlandırmasıyla AYNI şema).
        d_tank = (4.0 * v_tank / (np.pi * OX_TANK_LD_RATIO)) ** (1.0 / 3.0)
        l_tank = d_tank * OX_TANK_LD_RATIO
        r_tank = d_tank / 2.0
        h_fill = v_liquid / (np.pi * r_tank ** 2)  # = fill · L_tank

        try:
            from hrma.analysis.slosh_analysis import analyze_slosh
            slosh = analyze_slosh(radius=r_tank, fill_height=h_fill,
                                  g_eff=self.g0, liquid_mass=m_ox)
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': f'the slosh model could not run: {exc}',
                'tank_volume_m3': float(v_tank),
                'tank_volume_source': volume_source,
            }

        return {
            'status': 'modelled',
            '_basis': basis,
            'tank_volume_m3': float(v_tank),
            'tank_volume_source': volume_source,
            'tank_diameter_m': float(d_tank),
            'tank_length_m': float(l_tank),
            'tank_ld_ratio': OX_TANK_LD_RATIO,
            'tank_ld_ratio_basis': OX_TANK_LD_RATIO_BASIS,
            'liquid_fill_fraction': float(fill),
            'fill_height_m': float(h_fill),
            'liquid_mass_kg': m_ox,
            'liquid_mass_basis': 'the solver oxidizer mass of this run',
            'liquid_density_kg_m3': float(rho_liquid),
            'g_eff_m_s2': float(self.g0),
            'g_eff_basis': (
                'constant standard 1-g axial acceleration (ground / hover '
                'condition). NOT_MODELLED: coupling g_eff to the flight '
                'acceleration profile (g_eff = T/m during boost, which '
                'raises the slosh frequency as sqrt(g_eff)) is not wired '
                'to the trajectory yet — that is the follow-on work item; '
                'the fill_sweep inside the slosh result covers the '
                'draining-level dependence at 1 g only.'),
            'slosh': slosh,
        }

    # ======================================================================
    # v2.6.27 Dalga 6 — yazılı ama bağlanmamış modüllerin motor akışına
    # bağlanması (A3 basınçlı kap, A4 cıvata birleşimi, A6 su koçu, akustik
    # modlar, yarı-1B lüle akışı + ayrılma, ateşleyici boyutlandırma).
    #
    # ORTAK SÖZLEŞME (bu dalganın tek kuralı): modüle giden HER girdi
    # çözücünün GERÇEK hesabından gelir. Girdi yoksa modül ÇAĞRILMAZ ve blok
    # sayı İÇERMEDEN, eksik girdinin ADIYLA birlikte NOT_MODELLED döner.
    # Varsayılan/literatür değeri uydurup modülü "çalışır" göstermek yasaktır.
    # ======================================================================

    def _oxidizer_tank_vessel_block(self, blowdown_block=None,
                                    slosh_block=None):
        """Oksitleyici tankı basınçlı kap analizi (yol haritası A3).

        FİZİK KÜNYESİ
        -------------
        hrma/analysis/pressure_vessel.py — AIAA S-080A-2018 metalik basınçlı
        kap modu: proof = 1,5 x MEOP, burst = 2,0 x MEOP, ortalama yarıçap
        membran hoop formundan gerekli kalınlık; gerçek kopma basıncı
        min(Faupel kalın cidar, ince cidar plastik limiti). Katı motorun
        emniyet panelinin ve sıvı motorun tank kartının kullandığı
        ÇÖZÜCÜNÜN AYNISI (solid ``_calculate_safety_analysis`` /
        liquid ``_tank_pressure_vessel_analysis``).

        GİRDİ ENVANTERİ (kod okunarak çıkarıldı — hangileri GERÇEKTEN
        hesaplanıyor):
          * MEOP: blowdown bloğunun tank basınç serisinin MAKSİMUMU —
            N2O doyma basıncından gelen GERÇEK değer. Blowdown koşmadıysa
            (N2O dışı oksitleyici, uq_mode, model bandı dışı) hibritte tank
            basıncını hesaplayan BAŞKA bir yol YOKTUR -> NOT_MODELLED.
          * İç çap: slosh bloğunun tank geometrisi (aynı tank hacmi + beyanlı
            L/D). İki blok aynı tank için iki farklı çap yayımlayamaz.
          * Cidar tasarım sıcaklığı: blowdown tank sıcaklık serisinin
            MAKSİMUMU (dayanım derating'i sıcakta kötüleşir).
          * Malzeme: OX_TANK_MATERIAL_DEFAULT — beyanlı TASARIM SEÇİMİ,
            hesap değil (hibrit sayfasında tank malzemesi alanı yok).
          * Cidar kalınlığı: hibritte HİÇBİR YERDE hesaplanmıyor -> modül
            BOYUTLANDIRMA modunda çalışır (wall_thickness_mm=None) ve
            GEREKLİ kalınlığı kendisi çözer; doğrulanacak bir cidar
            olmadığı 'auto_sized' alanıyla modülün kendisi tarafından
            beyan edilir.
        """
        basis = (
            'oxidizer tank pressure-vessel sizing by '
            'hrma/analysis/pressure_vessel.py (AIAA S-080A-2018 metallic '
            'vessel mode: proof = 1.5 x MEOP, burst = 2.0 x MEOP, mean-radius '
            'membrane hoop thickness; actual burst = min(Faupel thick-wall, '
            'thin-wall plastic limit)) — the same analyser the solid motor '
            'safety panel and the liquid tank card use. MEOP and the wall '
            'design temperature are the maxima of the tank_blowdown solution '
            'of THIS run; the diameter is the tank geometry the '
            'oxidizer_tank_slosh block publishes (one tank, one geometry). '
            'No wall thickness is computed anywhere in the hybrid solver, so '
            'the module runs in SIZING mode and returns the REQUIRED '
            'thickness — there is no as-built wall here to verify.')
        blowdown = blowdown_block or {}
        slosh = slosh_block or {}

        eksik = []
        if blowdown.get('status') != 'modelled':
            eksik.append(
                'oxidizer tank operating pressure (MEOP): the hybrid solver '
                'computes a tank pressure ONLY through the self-pressurised '
                'blowdown model, and that model did not run for this design '
                '(reason in the tank_blowdown block). A pressure-fed tank '
                'pressure input does not exist on the hybrid page')
        if slosh.get('status') != 'modelled' or not slosh.get(
                'tank_diameter_m'):
            eksik.append(
                'oxidizer tank inner diameter: it follows from the tank '
                'volume and the declared L/D ratio in the '
                'oxidizer_tank_slosh block, which did not produce a geometry '
                'for this design')
        if eksik:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': ('the vessel analysis was not run and no numbers '
                           'are invented; missing input(s): '
                           + ' | '.join(eksik)),
            }

        try:
            p_seri = [float(p) for p in (blowdown.get('tank_pressure_bar')
                                         or [])]
            t_seri = [float(t) for t in (blowdown.get('tank_temperature_K')
                                         or [])]
            meop_bar = max(p_seri) if p_seri else float(
                blowdown['initial_pressure_bar'])
            t_design = (max(t_seri) if t_seri
                        else float(blowdown['initial_temperature_K']))
            d_inner = float(slosh['tank_diameter_m'])
        except (KeyError, TypeError, ValueError) as exc:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (f'the tank state published by this run could not '
                           f'be read: {exc}'),
            }

        try:
            from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
            vessel = PressureVesselAnalyzer().analyze(
                meop_bar=meop_bar,
                inner_diameter_mm=d_inner * 1000.0,
                material=OX_TANK_MATERIAL_DEFAULT,
                wall_thickness_mm=None,
                temperature_K=t_design)
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (f'the pressure-vessel analyser rejected the tank '
                           f'inputs: {exc}'),
                'meop_bar': float(meop_bar),
                'inner_diameter_m': float(d_inner),
            }

        return {
            'status': 'modelled',
            '_basis': basis,
            'meop_bar': float(meop_bar),
            'meop_source': (
                'maximum tank pressure of the tank_blowdown solution of this '
                'run (N2O saturation pressure at the tank temperature). '
                'NOT_MODELLED: a thermal soak / solar heating case that '
                'could raise the storage pressure above this value is not '
                'computed anywhere in HRMA'),
            'inner_diameter_m': float(d_inner),
            'inner_diameter_source': (
                'oxidizer_tank_slosh block of this run (tank volume from the '
                'blowdown sizing, diameter from the declared L/D ratio) - '
                'one tank, one geometry'),
            'design_temperature_K': float(t_design),
            'design_temperature_source': (
                'maximum tank temperature of the blowdown solution (strength '
                'derating is worst at the hottest wall state)'),
            'material': OX_TANK_MATERIAL_DEFAULT,
            'material_source': (
                'DECLARED DESIGN CHOICE, not a computed result and not a '
                'user input: the hybrid page has no oxidizer-tank material '
                'field yet. The same record the liquid engine uses as its '
                'default tank material. It is NOT the chamber material you '
                'selected - that one belongs to the combustion chamber'),
            'wall_thickness_source': (
                'not supplied and not computed anywhere in the hybrid '
                'solver, so the module ran in sizing mode: '
                'required_thickness_mm is what the code form demands and '
                'wall_thickness_used_mm is what the analyser sized to meet '
                'the burst margin. Nothing here verifies an as-built wall'),
            'pressure_vessel': vessel,
        }

    def _closure_joint_block(self):
        """Kapak cıvata birleşimi — hrma.analysis.bolted_joint (A4).

        Katı ve sıvı motordaki ``_closure_joint_analysis`` deseninin hibrit
        karşılığı: ayırıcı yük = kamara basıncı x sızdırmazlık alanı
        (sızdırmazlık çapı KAMARA İÇ ÇAPI), emniyet katsayıları
        Shigley Böl. 8 / ISO 898-1 / NASA-STD-5020A ön-yük saçılımıyla.

        Basınç ve çap çözücünün GERÇEK değerleridir; cıvata SAYISI hiçbir
        yerde hesaplanmaz (bir tasarım kararıdır) ve varsayılanı YOKTUR —
        verilmezse birleşim boyutlandırılmaz.
        """
        basis = (
            'closure-bolt joint sized by hrma/analysis/bolted_joint.py '
            '(Shigley 10th ed. Ch. 8 member/bolt stiffness + ISO 898-1 proof '
            'strength + NASA-STD-5020A preload scatter) - the same analyser '
            'the solid and liquid engines call for their closure joints and '
            'the /api/bolted-joint endpoint serves. The separating load is '
            'the chamber pressure of THIS design acting on the chamber inner '
            'diameter.')
        count = getattr(self, 'closure_bolt_count', None)
        if not count:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (
                    'the joint is not sized and no bolt plan is invented; '
                    'missing input: closure_bolt_count (number of closure '
                    'bolts). It is a design decision, not a computed '
                    'quantity - the solver derives it nowhere. The sealing '
                    'diameter (chamber inner diameter) and the sealed '
                    'pressure (chamber pressure) ARE available.'),
                'required_inputs': ['closure_bolt_count'],
            }
        d_seal_mm = float(self.D_ch) * 1000.0
        try:
            from hrma.analysis.bolted_joint import analyze_bolted_joint
            res = analyze_bolted_joint(
                pressure_bar=float(self.P_c),
                seal_diameter_mm=d_seal_mm,
                bolt_count=int(count),
                size=CLOSURE_JOINT_DEFAULTS['size'],
                property_class=CLOSURE_JOINT_DEFAULTS['property_class'],
                member_material=CLOSURE_JOINT_DEFAULTS['member_material'])
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': f'the bolted-joint analyser rejected the inputs: {exc}',
                'bolt_count': int(count),
            }
        sf = res.get('safety_factors') or {}
        sep = res.get('separation') or {}
        tq = res.get('torque') or {}
        return {
            'status': 'modelled',
            '_basis': basis,
            'bolt_count': int(count),
            'bolt_size': CLOSURE_JOINT_DEFAULTS['size'],
            'property_class': CLOSURE_JOINT_DEFAULTS['property_class'],
            'member_material': CLOSURE_JOINT_DEFAULTS['member_material'],
            'hardware_source': (
                'DECLARED DEFAULTS (bolt size, property class, member '
                'material), not computed and not user inputs: the hybrid '
                'page carries no closure-bolt hardware fields. Only the bolt '
                'COUNT is taken from the caller. The same declared set the '
                'solid engine uses (SOLID_CLOSURE_JOINT_DEFAULTS)'),
            'seal_diameter_mm': d_seal_mm,
            'seal_diameter_source': (
                'chamber inner diameter of this design (the area the chamber '
                'pressure pushes the closure off with)'),
            'pressure_bar': float(self.P_c),
            'tightening_torque_nm': tq.get('recommended_torque_Nm'),
            'nut_factor_K': tq.get('K_nut_factor'),
            'preload_scatter_percent': tq.get('preload_uncertainty_pct'),
            'proof_safety_factor': sf.get('proof_SF_min'),
            'separation_factor': sf.get('separation_factor_n0_min'),
            'overload_factor': sf.get('overload_factor_nL_min'),
            'separated': sep.get('separated'),
            'governing_basis': sf.get('governing_basis'),
            'assumptions': res.get('assumptions'),
            'warnings': res.get('warnings'),
            'source': res.get('source'),
        }

    def _feed_water_hammer_block(self):
        """Oksitleyici besleme hattı su koçu (yol haritası A6).

        Sıvı motordaki ``_feed_water_hammer_analysis`` deseni hibritte
        UYGULANAMIYOR ve bunun sebebi sayı uydurarak gizlenmez.

        Sıvı motor su koçunu çözebiliyor çünkü orada hat çapı ve hat hızı
        GERÇEKTEN hesaplanıyor (``_calculate_line_diameter`` /
        ``_line_pressure_drops``: A = ṁ/(ρ·v)) ve hat uzunluğu tek tanımlı
        bir yerleşim varsayımı olarak beyan ediliyor. Hibrit çözücüde bu
        zincirin HİÇBİR halkası yoktur: 2026-08-05 taraması, bu dosyada
        besleme hattı çapı/hızı/uzunluğu HESAPLAYAN tek bir satır
        bulmamıştır. Cidar kalınlığı ve vana kapanma süresi sıvı motorda
        bile KULLANICI GİRDİSİDİR ve hibrit sayfasında böyle bir alan
        yoktur.

        ÖH D19 (kalem B2-08 artığı): bu docstring ve aşağıdaki ``reason``
        metni "çözülen tek besleme öğesi enjektör orifis planıdır" diyordu.
        Aynı cümle D18'de ``_not_modelled_declarations()['feed_system']``
        beyanından KALDIRILMIŞTI (çözülen ikinci öğe var: kullanıcı
        feed_line_length_m / feed_line_inner_diameter_mm verdiğinde chug
        döngüsünün TOPAKLANMIŞ hat ataleti), ama kardeş blokta bir kopyası
        kalmıştı ve o kopya da ürün yanıtına giriyordu. ÖLÇÜLDÜ (once.json,
        D18_DEVRI.B2_08; taban 60cd341): daraltılmış beyanda cümle YOK
        (False) ama dosyada 1 kopya duruyor (True), aynı yanıtta
        chug_loop.tau_f_s = 0,002473428029274475 s ve chug_loop.feed_line
        çözülü. Cümle o yüzden burada da düzeltildi; ``reason``ın kalan
        iddiası (HESAPLANAN hat geometrisi yok, dolayısıyla dalga hızı /
        Joukowsky basınç sıçraması / kapanma rejimi yok) ölçümle uyumludur.
        """
        return {
            'status': 'NOT_MODELLED',
            '_basis': (
                'Joukowsky/Allievi lumped-parameter water hammer + Michaud '
                'slow closure + column-separation check '
                '(hrma/analysis/water_hammer.py, served by /api/water-hammer '
                'and wired to the liquid engine feed lines). It is NOT '
                'evaluated for the hybrid oxidizer feed line because the '
                'inputs do not exist in this solver - they are not '
                'fabricated.'),
            'reason': (
                'the hybrid solver sizes no feed line at all: no line '
                'diameter, no line velocity and no line length are computed '
                'anywhere. Without a line there is no wave speed, no '
                'Joukowsky pressure rise and no closure regime to report. '
                'The feed elements that ARE solved are the injector orifice '
                'plan (injector_design_detail) and - when the user supplies '
                'feed_line_length_m and feed_line_inner_diameter_mm - the '
                'lumped inertance of that one line inside the chug loop '
                '(combustion_stability.chug_loop), but water hammer '
                'additionally needs the wall thickness and the valve closure '
                'time, which have no input channel in this solver.'),
            'required_inputs': [
                'feed_line_length_m',
                'feed_line_inner_diameter_mm',
                'feed_line_wall_thickness_mm',
                'valve_closure_time_ms',
            ],
            'oxidizer_line': {
                'status': 'NOT_MODELLED',
                'reason': (
                    'same as above - the oxidizer line geometry is not part '
                    'of the hybrid design solution. Use /api/water-hammer '
                    'with your own line geometry, or the liquid engine, for '
                    'a transient estimate.'),
            },
        }

    def _acoustic_modes_block(self, basic_results):
        """Kamara akustik modları + chug marjı (hrma.analysis.acoustic_modes).

        Modülün giriş sözleşmesi ZATEN hibrit sonuç şemasına göre yazılmıştı
        (``analyze_from_engine_result``: chamber_temperature, gamma,
        molecular_weight, chamber_diameter, chamber_length,
        chamber_pressure) ama motor onu hiç çağırmıyordu; hibrit sonucu
        bunun yerine "akustik mod analizi YOK" diye beyan ediyordu. Beyan bu
        bağlamayla ÇÜRÜDÜ ve _not_modelled_declarations'tan kaldırıldı.

        Chug oranı için enjektör basınç düşümü çözücünün GERÇEK değeridir
        (injector_design bloğu); enjektör çözülemediyse oran verilmez ve
        modül chug hükmünü 'NOT_EVALUATED' bırakır (uydurma oran yok).
        """
        basis = (
            'chamber acoustic eigenfrequencies and the classical feed-'
            'coupled (chug) margin from hrma/analysis/acoustic_modes.py: '
            'rigid-wall closed-closed cylindrical cavity modes '
            'f_mnq = (a/2pi)*sqrt((2*alpha_mn/D)^2 + (q*pi/L)^2) with '
            'a = sqrt(gamma*R*T_c) (Kinsler & Frey Ch. 9; NASA SP-194 Ch. 3; '
            'Sutton & Biblarz 9th ed. Ch. 9). Chamber temperature, gamma and '
            'molecular weight are the combustion-equilibrium values of THIS '
            'run, the diameter and length are the solved chamber geometry, '
            'and the chug ratio uses the injector pressure drop the injector '
            'circuit model actually computed. The module reports WHERE the '
            'modes lie, NOT whether combustion drives them (see '
            'not_modelled.combustion_response inside the block).')
        eksik = [ad for ad in ('chamber_temperature', 'gamma',
                               'molecular_weight', 'chamber_diameter',
                               'chamber_length')
                 if not basic_results.get(ad)]
        if eksik:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': ('the acoustic analysis was not run and no '
                           'frequencies are invented; missing solver '
                           f'output(s): {eksik}'),
            }

        inj = basic_results.get('injector_design') or {}
        dp_bar = inj.get('injection_pressure_drop_bar')
        try:
            dp_bar = float(dp_bar)
        except (TypeError, ValueError):
            dp_bar = None
        if dp_bar is not None and not (np.isfinite(dp_bar) and dp_bar > 0):
            dp_bar = None

        try:
            from hrma.analysis.acoustic_modes import analyze_from_engine_result
            res = analyze_from_engine_result(
                basic_results, injector_pressure_drop_bar=dp_bar)
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (f'the acoustic-mode analyser rejected the '
                           f'chamber state: {exc}'),
            }

        res = dict(res)
        res.update({
            'status': 'modelled',
            '_basis': basis,
            'injector_dp_source': (
                'injection_pressure_drop_bar of the injector_design block '
                '(the circuit model solution of this run)' if dp_bar
                else 'the injector circuit did not produce a pressure drop '
                     'for this design, so no chug ratio is formed - the chug '
                     'verdict stays NOT_EVALUATED rather than being guessed'),
            'geometry_source': (
                'solved chamber inner diameter and total chamber length '
                '(grain + pre-combustion + post-combustion sections). The '
                'cavity is idealised as a plain closed-closed cylinder: the '
                'fuel port, the grain step and the nozzle convergent volume '
                'are NOT part of the acoustic model'),
        })
        return res

    # ------------------------------------------------------------------
    # F2b-1 — yanma kararlılığı bağlaması (hrma/stability çekirdeği)
    # ------------------------------------------------------------------
    def _pure_longitudinal_modes(self, acoustic_block):
        """Akustik blok tablosundan SAF BOYUNA modlar (m = n = 0, q >= 1).

        Neden yalnız boyuna: bağlanan iki kapalı form da boyuna modda
        türetilmiştir — lüle sönümü ψ_n = cos(nπz/L) ve ψ_n²(L) = 1 ile
        (Culick & Yang 1990, Denk. 100 yarı-kararlı limiti; modülün kendi
        ``mode_dependence`` alanı bunu yazıyor) ve tepki kazancı aynı mod
        şekliyle. Enine/karma modlarda ne lüle admitans integrali ne de
        yanma yüzeyi üstündeki ⟨ψ²⟩ bu kapanışla geçerlidir; o modlar
        eşik tablosuna KONMAZ ve gerekçesiyle listelenir (uydurma yok).
        """
        modlar = []
        for mod in (acoustic_block.get('modes') or []):
            idx = mod.get('indices') or {}
            if (idx.get('tangential_m') == 0 and idx.get('radial_n') == 0
                    and int(idx.get('longitudinal_q') or 0) >= 1):
                modlar.append(mod)
        return modlar

    @staticmethod
    def _mode_shape_mean_square(q, cavity_length_m, z_start_m, z_end_m):
        """⟨ψ²⟩: cos²(qπz/L)'nin [z1, z2] penceresindeki TAM ortalaması.

        Kapalı-kapalı kavitede mod şekli ψ_q = cos(qπz/L)'dir (akustik
        modülün kendi tablosu). Yanma yüzeyi kavitenin TAMAMINI kaplamıyorsa
        (hibritte yakıt portu ön/art yanma odalarını kapsamaz) kazanç
        integralindeki ortalama 1/2 DEĞİLDİR; kapalı formu:

            ⟨ψ²⟩ = 1/2 + L·[sin(2qπz2/L) − sin(2qπz1/L)] / (4qπ(z2 − z1))

        Pencere tüm kaviteyse (z1 = 0, z2 = L) sonuç tam olarak 1/2'dir —
        yani çekirdeğin varsayılanı bu formülün özel hâlidir, ikinci bir
        tanım değil. Uydurma yok: pencere çözücünün YAYIMLADIĞI ön/art
        yanma odası boylarından gelir.
        """
        length = float(cavity_length_m)
        z1 = float(z_start_m)
        z2 = float(z_end_m)
        if not (length > 0 and z2 > z1):
            return None
        span = z2 - z1
        katsayi = length / (4.0 * np.pi * int(q) * span)
        deger = 0.5 + katsayi * (np.sin(2.0 * np.pi * int(q) * z2 / length)
                                 - np.sin(2.0 * np.pi * int(q) * z1 / length))
        deger = float(deger)
        if not (np.isfinite(deger) and 0.0 < deger <= 1.0):
            return None
        return deger

    def _hybrid_lfi_block(self, basic_results):
        """Hibrit alçak frekans kararsızlığı (LFI) — Karabeyoglu ve ark. 2005.

        ÇÖZÜCÜ YENİ GİRDİ İSTEMEZ (ölçüldü, bu koşunun kendi yayınından):
        ``g_ox_initial`` [kg/(m²·s)], ``grain_length`` [m],
        ``chamber_pressure`` [bar], ``of_ratio_initial`` ve motorun
        ``oxidizer_type``'ı. Beşi de tasarım anının (t = 0) büyüklükleridir;
        akı ile O/F aynı ANDAN alınır, karışık bir çift kurulmaz.

        R·T_av KORELASYONUN KALİBRE SABİTİDİR (tasarım kararı 2): çözücünün
        kendi R·T_c'si YERİNE KONMAZ, yalnızca tanı oranı olarak yanında
        yayımlanır. Desteklenmeyen oksitleyicide (H₂O₂, N₂O₄, nytrox...)
        sabit UYDURULMAZ: blok NOT_EVALUATED döner ve nedenini söyler.

        HÜKÜM ÇEKİRDEKTEN GELDİĞİ GİBİ TAŞINIR: motor katmanı yeniden
        hükümleştirmez. Çekirdek kapsam etiketli 'marginal' verir (mekanizma
        VARLIĞI + frekansı modellenir, GENLİĞİ modellenmez) — bu, kaynağın
        kendi sonuçlarının okumasıdır, burada gevşetilemez.
        """
        basis = (
            'Hybrid low-frequency instability from hrma/stability/'
            'hybrid_lfi.py: the TCG-coupled universal scaling law of '
            'Karabeyoglu, De Zilwa, Cantwell & Zilliac, "Modeling of Hybrid '
            'Rocket Low Frequency Instabilities", J. Propulsion and Power '
            '21(6), 2005, Eq. 15, fitted to 43 motor tests. Every input is a '
            'quantity THIS run already publishes at its design instant '
            '(t = 0): initial oxidizer port flux g_ox_initial, grain_length, '
            'chamber_pressure, of_ratio_initial and the motor oxidizer type. '
            'The verdict is carried verbatim from the core; the engine layer '
            'does not re-judge it.')
        gerekli = {
            'grain_length': basic_results.get('grain_length'),
            'chamber_pressure': basic_results.get('chamber_pressure'),
            'g_ox_initial': basic_results.get('g_ox_initial'),
            'of_ratio_initial': basic_results.get('of_ratio_initial'),
        }
        eksik = [ad for ad, deger in gerekli.items()
                 if not (isinstance(deger, (int, float))
                         and np.isfinite(float(deger)) and float(deger) > 0)]
        ox = getattr(self, 'oxidizer_type', None)
        if not (isinstance(ox, str) and ox.strip()):
            eksik.append('oxidizer_type')
        if eksik:
            return {
                'status': 'NOT_EVALUATED',
                'missing_inputs': eksik,
                '_basis': basis,
                'reason': ('no low-frequency mode is reported and no '
                           'frequency is invented; missing solver '
                           f'output(s): {eksik}'),
            }

        # Tanı oranı için çözücünün kendi R·T_c'si (varsa). Korelasyona
        # GİRMEZ — çekirdek onu ayrı alanda tanı olarak taşır. Evrensel gaz
        # sabiti akustik modülün TEK tanımından gelir (sayı kopyalanmaz).
        from hrma.analysis.acoustic_modes import R_UNIVERSAL_J_KMOL_K
        rt_thermo = None
        mw = basic_results.get('molecular_weight')
        t_c = basic_results.get('chamber_temperature')
        try:
            if (mw and t_c and float(mw) > 0 and float(t_c) > 0):
                rt_thermo = (R_UNIVERSAL_J_KMOL_K / float(mw)) * float(t_c)
        except (TypeError, ValueError):
            rt_thermo = None

        # 1L akustik mod (varsa): ayrışma dekadı için. Akustik blok
        # çözülmediyse alan hiç kurulmaz (uydurma frekans yok).
        f_1l = None
        akustik = basic_results.get('acoustic_modes') or {}
        for mod in self._pure_longitudinal_modes(akustik):
            if int((mod.get('indices') or {}).get('longitudinal_q') or 0) == 1:
                f_1l = float(mod.get('frequency_hz') or 0.0) or None
                break

        try:
            from hrma.stability import assess_hybrid_lfi
            sonuc = assess_hybrid_lfi(
                oxidizer_type=ox,
                grain_length_m=float(gerekli['grain_length']),
                chamber_pressure_Pa=float(gerekli['chamber_pressure']) * 1e5,
                oxidizer_flux_kg_m2_s=float(gerekli['g_ox_initial']),
                of_ratio=float(gerekli['of_ratio_initial']),
                rt_thermo_m2_s2=rt_thermo,
                acoustic_first_longitudinal_hz=f_1l)
        except ValueError as exc:
            return {
                'status': 'NOT_EVALUATED',
                'missing_inputs': [f'calibrated R*Tav for oxidizer {ox!r}'],
                '_basis': basis,
                'reason': (f'the hybrid LFI correlation refused this operating '
                           f'point: {exc}'),
            }

        sonuc = dict(sonuc)
        sonuc['status'] = 'modelled'
        sonuc['_basis'] = basis
        sonuc['input_source'] = (
            'g_ox_initial / grain_length / chamber_pressure / '
            'of_ratio_initial of this run (design instant t = 0) and the '
            'motor oxidizer_type; the first longitudinal acoustic frequency '
            'comes from the acoustic_modes block of the SAME run, so the two '
            'blocks cannot disagree about where 1L sits.')
        return sonuc

    def _acoustic_response_threshold_block(self, basic_results):
        """Mod başına KRİTİK YANMA TEPKİSİ eşiği R_crit (HÜKÜM YOK).

        Tasarım belgesi §3.0'ın F2 omurgası: sönüm tarafı hesaplanır, kazanç
        tarafı TERS ÇEVRİLİR — "bu mod nötr olsun diye basınç kuplajlı yanma
        tepkisi NE KADAR olmalıydı?". Tepki fonksiyonu ölçülür (T-burner),
        türetilmez; HRMA'nın elinde o ölçüm yoktur, bu yüzden bu yolda
        hüküm YASAKTIR ve blok ``forbid_verdict_key`` ile taranır.

        BÜYÜKLÜKLERİN KAYNAĞI (hepsi bu koşunun kendi çözümünden):
          * ā, mod tablosu: acoustic_modes bloğu (ikinci bir tablo üretilmez),
          * ρ_c = P_c/(R·T_c), R = R_u/MW: akustik bloğun kullandığı AYNI çift,
          * M_N = ṁ_toplam/(ρ_c·ā·S_c) — Culick'in M_N'i zaten kütle-akısı
            oranıdır (M_b·S_b/S_c), yani bu bir yeniden tanım değil özdeşlik,
          * M_b = ṁ_yakıt/(ρ_c·ā·S_b): kazanç YALNIZ yanan yüzeyden giren
            kütleye aittir. Hibritte oksitleyici baş taraftan girer, yakıt
            port cidarından gelir; toplam debiyi kazanca koymak tepkiyi
            (1 + O/F) katı abartırdı.

        ÖLÇÜLEN ÖZDEŞLİK: yalnız lüle sönümü modellendiğinde
        R_crit = ((γ+1)/γ)·(ṁ_toplam/ṁ_yakıt)·(1/2)/⟨ψ²⟩ — kavite
        idealleştirmesi (S_c) pay ve paydada birlikte gittiği için eşikten
        DÜŞER. Eksik kayıp terimleri (partikül, viskoz, yapısal) eşiği
        KÖTÜMSER yapar; yön beyan alanındadır.
        """
        basis = (
            'Per-mode critical combustion response threshold R_crit from '
            'hrma/stability: the quasi-steady short-nozzle damping of Culick '
            '& Yang (AIAA Progress in Astronautics and Aeronautics Vol. 143, '
            '1990, Eq. 100) is inverted against the pressure-coupled driving '
            'gain of their Eq. 99, giving the response the combustion WOULD '
            'have to deliver for the mode to be neutral. This is a threshold, '
            'never a verdict: HRMA does not measure the response function '
            '(design doc section 3.0), so no stability judgement is issued on '
            'this path and the block is scanned for a forbidden "verdict" '
            'key. Sound speed and the mode table are read from the '
            'acoustic_modes block of this run; the mean-flow group M_N is the '
            'mass-flux ratio mdot/(rho*a*S_c) — Culick\'s own definition of '
            'M_N = M_b*S_b/S_c — and the driving gain uses the FUEL mass flow '
            'only, because in a hybrid the oxidizer does not enter through '
            'the responding surface.')
        akustik = basic_results.get('acoustic_modes') or {}
        eksik = []
        if akustik.get('status') != 'modelled':
            eksik.append('acoustic_modes (mode table and sound speed)')
        alanlar = {
            'chamber_length': basic_results.get('chamber_length'),
            'chamber_diameter': basic_results.get('chamber_diameter'),
            'gamma': basic_results.get('gamma'),
            'molecular_weight': basic_results.get('molecular_weight'),
            'chamber_temperature': basic_results.get('chamber_temperature'),
            'chamber_pressure': basic_results.get('chamber_pressure'),
            'mdot_total': basic_results.get('mdot_total'),
            'mdot_f': basic_results.get('mdot_f'),
            'port_diameter_initial': basic_results.get('port_diameter_initial'),
            'grain_length': basic_results.get('grain_length'),
            # ÖH D18 (kalem B2-07): yanma yüzeyi PORT SAYISINI görmek
            # zorunda; aşağıdaki S_b bu alandan kurulur. Yayımlanan
            # port_count okunur (kapıdan geçmiş, çıktıda görünen değerle
            # AYNI sayı — tek kaynak).
            'port_count': basic_results.get('port_count'),
        }
        for ad, deger in alanlar.items():
            if not (isinstance(deger, (int, float))
                    and np.isfinite(float(deger)) and float(deger) > 0):
                eksik.append(ad)
        if eksik:
            return {
                'status': 'NOT_MODELLED',
                'missing_inputs': eksik,
                '_basis': basis,
                'reason': ('no damping budget and no critical response '
                           'threshold are reported; missing solver '
                           f'output(s): {eksik}'),
            }

        from hrma.analysis.acoustic_modes import R_UNIVERSAL_J_KMOL_K
        from hrma.stability import (
            critical_response_real,
            damping_budget,
            forbid_verdict_key,
            nozzle_damping_quasi_steady,
            response_gain_uniform_chamber,
        )
        from hrma.stability.damping import DAMPING_NOT_MODELLED

        a_ses = float(akustik.get('sound_speed_m_s') or 0.0)
        l_kamara = float(alanlar['chamber_length'])
        d_kamara = float(alanlar['chamber_diameter'])
        gamma = float(alanlar['gamma'])
        r_gaz = R_UNIVERSAL_J_KMOL_K / float(alanlar['molecular_weight'])
        rho_c = (float(alanlar['chamber_pressure']) * 1e5
                 / (r_gaz * float(alanlar['chamber_temperature'])))
        s_c = np.pi * d_kamara ** 2 / 4.0
        # ÖH D18 (kalem B2-07) — S_b ARTIK N PORTU GÖRÜYOR.
        # Eski satır ``np.pi * D_port * L_grain`` idi: tek port varsayıyordu.
        # Çözücünün kendisi anlık yakıt debisini N·π·D·L·ṙ ile hesaplıyor
        # (bkz. _design_fuel_grain / zaman yürüyüşü), yani N bu blokta
        # DÜŞÜRÜLMÜŞTÜ. ÖLÇÜLDÜ (once.json, B2_07; taban 9071a64, 3 kN
        # N2O/HTPB): fiziksel N·π·D·L / yayımlanan S_b oranı N=1'de 1,0000 ·
        # N=2'de 2,0000 · N=4'te 4,0000 · N=7'de 7,0000 — yani sapma tam N
        # katıydı ve M_b = ṁ_f/(ρ·a·S_b) aynı çarpanla şişiyordu
        # (N=7: 0,00030951 yerine 0,00236076, 7,00 kat).
        # R_crit'in KENDİSİ etkilenmez (S_b hem kazançta hem sönümde
        # sadeleşir), ama bloğun kullanıcıyı çağırdığı VARSAYIM DENETİMİ
        # (mach_basis: "M_N is published so that assumption can be checked
        # against this motor") tam da bu sayılarla yapılıyor.
        n_port_akustik = float(alanlar['port_count'])
        s_b = n_port_akustik * np.pi \
            * float(alanlar['port_diameter_initial']) \
            * float(alanlar['grain_length'])
        if not (a_ses > 0 and rho_c > 0 and s_c > 0 and s_b > 0):
            return {
                'status': 'NOT_MODELLED',
                'missing_inputs': ['chamber gas state'],
                '_basis': basis,
                'reason': ('the chamber gas state produced a non-physical '
                           'density or cavity area, so no damping budget is '
                           'formed'),
            }
        mach_n = float(alanlar['mdot_total']) / (rho_c * a_ses * s_c)
        mach_b = float(alanlar['mdot_f']) / (rho_c * a_ses * s_b)

        try:
            lule = nozzle_damping_quasi_steady(a_ses, l_kamara, gamma, mach_n)
            butce = damping_budget([lule])
        except ValueError as exc:
            return {
                'status': 'NOT_MODELLED',
                'missing_inputs': [],
                '_basis': basis,
                'reason': (f'the damping core rejected this chamber state: '
                           f'{exc}'),
            }

        z1 = float(basic_results.get('pre_chamber_length') or 0.0)
        z2 = z1 + float(alanlar['grain_length'])
        boyuna = self._pure_longitudinal_modes(akustik)
        boyuna_etiketleri = {mod.get('label') for mod in boyuna}
        satirlar = []
        atlanan = []
        esik_beyanlari = {}
        for mod in boyuna:
            q = int((mod.get('indices') or {}).get('longitudinal_q') or 0)
            psi2 = self._mode_shape_mean_square(q, l_kamara, z1, z2)
            if psi2 is None:
                atlanan.append({
                    'label': mod.get('label'),
                    'reason': ('the mean square of the mode shape over the '
                               'fuel port window is not a usable average for '
                               'this mode (non-positive or non-finite), so no '
                               'threshold is fabricated for it'),
                })
                continue
            try:
                kazanc = response_gain_uniform_chamber(
                    a_ses, l_kamara, s_b, s_c, mach_b, gamma,
                    mode_shape_mean_square=psi2)
                satir = critical_response_real(butce['total_damping_1_s'],
                                               kazanc['gain_1_s'])
            except ValueError as exc:
                atlanan.append({'label': mod.get('label'),
                                'reason': f'the response core refused: {exc}'})
                continue
            # Uzun beyan metinleri blok düzeyinde TEK KEZ taşınır (satır
            # başına tekrarlanmaz): aynı cümle mod sayısı kadar kopyalanırsa
            # yanıt şişer ve tek kaynak ilkesi bozulur. Metin KAYBOLMAZ —
            # çekirdeğin sözlüğü olduğu gibi bloğa taşınır.
            esik_beyanlari.update(satir.pop('not_modelled', None) or {})
            satir.pop('interpretation_basis', None)
            satir['label'] = mod.get('label')
            satir['frequency_hz'] = float(mod.get('frequency_hz'))
            satir['mode_shape_mean_square'] = psi2
            satir['damping'] = dict(butce['terms'])
            satirlar.append(satir)

        if not satirlar:
            # Tek bir eşik satırı bile kurulamadıysa blok SAYI TAŞIMAZ:
            # "NOT_MODELLED ama sayılar var" hâli tutarsızdır.
            return {
                'status': 'NOT_MODELLED',
                'missing_inputs': [],
                '_basis': basis,
                'reason': ('no longitudinal mode produced a usable threshold '
                           f'on this run: {atlanan}'),
            }
        blok = {
            'status': 'modelled',
            '_basis': basis,
            'model': 'nozzle_damping_budget_inverted_to_critical_response',
            'interpretation': 'threshold_not_verdict',
            'interpretation_basis': (
                'R_crit is the response the combustion WOULD have to deliver '
                'for the mode to be neutral — a comparison yardstick, never a '
                'stability verdict. No verdict key exists anywhere on this '
                'path (structurally enforced by '
                'hrma.stability.forbid_verdict_key).'),
            'sound_speed_m_s': a_ses,
            'chamber_gas_density_kg_m3': float(rho_c),
            'acoustic_cavity_area_m2': float(s_c),
            'burning_surface_area_m2': float(s_b),
            'mean_flow_mach_M_N': float(mach_n),
            'surface_mach_M_b': float(mach_b),
            'mach_basis': (
                'M_N = mdot_total/(rho_c*a*S_c) and M_b = mdot_fuel/'
                '(rho_c*a*S_b) are mass-flux ratios, which is exactly how '
                'Culick & Yang define them (their M_N = M_b*S_b/S_c). S_c is '
                'the cross-section of the SAME idealised cylinder the mode '
                'table uses (chamber inner diameter), because the mode-shape '
                'normalisation E_n^2 = S_c*L/2 must match the published '
                'modes; the real gas cross-section is the fuel port, which is '
                'smaller. That idealisation cancels out of R_crit (it divides '
                'both the damping and the gain) but it does NOT cancel out of '
                'the individual alpha and gain values printed here. The '
                'quasi-steady short-nozzle limit assumes a small mean-flow '
                'Mach number; M_N is published so that assumption can be '
                'checked against this motor.'),
            'burning_surface_basis': (
                'S_b = port_count * pi * initial port diameter * grain '
                'length, the fuel port wall at the design instant summed '
                'over ALL ports of the grain (the same N * pi * D * L the '
                'grain solver integrates for the instantaneous fuel mass '
                f'flow; this run uses port_count = {int(n_port_akustik)}). '
                'Only the FUEL mass flow is injected through it (mdot_f), '
                'so the driving gain uses mdot_f while the nozzle damping '
                'uses the total mdot.'),
            'mode_shape_basis': (
                'The pressure-coupled gain integrates the mode shape over the '
                'BURNING surface. The fuel port does not span the whole '
                'acoustic cavity (pre- and post-combustion chambers are gas '
                'only), so <psi^2> is the exact mean of cos^2(q*pi*z/L) over '
                'the published port window [pre_chamber_length, '
                'pre_chamber_length + grain_length] rather than the '
                'full-length value 1/2. It is mode dependent, so R_crit is '
                'too.'),
            'damping': {
                'terms': dict(butce['terms']),
                'total_damping_1_s': butce['total_damping_1_s'],
                'total_loss_1_s': butce['total_loss_1_s'],
                'sign_convention': butce['sign_convention'],
                'bias_basis': butce['bias_basis'],
                'nozzle_term': {
                    'damping_1_s': lule['damping_1_s'],
                    'admittance_real': lule['admittance_real'],
                    'basis': lule['basis'],
                },
                'not_modelled': dict(DAMPING_NOT_MODELLED),
            },
            'modes': satirlar,
            'modes_not_evaluated': atlanan,
            'transverse_modes_not_evaluated': [
                mod.get('label') for mod in (akustik.get('modes') or [])
                if mod.get('label') not in boyuna_etiketleri],
            'transverse_modes_basis': (
                'Only pure longitudinal modes carry a threshold: both closed '
                'forms bound here (nozzle admittance integral and the '
                'burning-surface gain) are derived for psi = cos(q*pi*z/L). '
                'For tangential/radial modes neither the nozzle integral nor '
                'the mean square over the burning surface holds, and no '
                'number is fabricated for them.'),
            'not_modelled': esik_beyanlari,
        }
        return forbid_verdict_key(
            blok, 'hybrid combustion_stability.acoustic_response_threshold')

    def _feed_line_inertance_inputs(self, basic_results):
        """Besleme hattı ataleti girdileri — sıvıdaki KARAR 5'in hibrit ikizi.

        Hat uzunluğu ve iç çapı ÇÖZÜLMEZ; kullanıcı ikisini de verirse chug
        çevrimi ikinci mertebe (ataletli) forma geçer, vermezse ataletsiz
        koşar ve bunu beyan eder. Hiçbir yerleşim varsayımı buraya
        KOPYALANMAZ — uydurma varsayılan yasağı.

        Sıvıdan İKİ bilinçli fark:
          * debi TOPLAM değil OKSİTLEYİCİ debisidir — hibritte hattan yalnız
            oksitleyici akar, yakıt katıdır ve grenden gelir;
          * feed_line_area_m2 kanalı AÇILMAZ (sıvıda API kanalı olarak var);
            kesit iç çaptan dairesel kesitle türetilir.

        Returns:
            (tau_f_s veya None, beyan sözlüğü veya None)
        """
        length = self.feed_line_length_m
        d_mm = self.feed_line_inner_diameter_mm
        if length is None or d_mm is None:
            return None, None
        area = np.pi * (float(d_mm) / 1000.0) ** 2 / 4.0
        mdot_ox = basic_results.get('mdot_ox')
        inj = basic_results.get('injector_design') or {}
        dp_bar = inj.get('injection_pressure_drop_bar')
        try:
            dp_bar = float(dp_bar)
        except (TypeError, ValueError):
            dp_bar = None
        if not (mdot_ox and np.isfinite(mdot_ox) and mdot_ox > 0) or \
                not (dp_bar and np.isfinite(dp_bar) and dp_bar > 0):
            return None, None
        from hrma.stability.chug import feed_inertance_time_constant
        tau_f = feed_inertance_time_constant(
            line_length_m=float(length), line_area_m2=float(area),
            mass_flow_kg_s=float(mdot_ox), dp_injector_Pa=dp_bar * 1e5)
        return tau_f, {
            'line_length_m': float(length),
            'line_inner_diameter_mm': float(d_mm),
            'line_area_m2': float(area),
            'mass_flow_kg_s': float(mdot_ox),
            'dp_injector_Pa': dp_bar * 1e5,
            '_basis': (
                'Feed line length and inner diameter supplied by the caller '
                '(published hybrid input names feed_line_length_m / '
                'feed_line_inner_diameter_mm; no layout default exists). The '
                'flow area is the circular section of that diameter. The '
                'mass flow is the OXIDIZER flow of this run — in a hybrid '
                'only the oxidizer travels through a feed line, the fuel is '
                'solid — and the pressure drop is the injector circuit drop '
                'of the SAME run, consistent with the ratio J the chug '
                'report uses.'),
        }

    def _chamber_gas_density(self, basic_results):
        """Oda gazı yoğunluğu ρ = P_c/(R·T_c) [kg/m³] — TEK tanım noktası.

        İdeal gaz, denge özellikleriyle: R = R_evrensel/MW. Yayımlanmış üç
        alandan (chamber_pressure [bar], chamber_temperature [K],
        molecular_weight [g/mol]) okunur; biri eksik/geçersizse SAYI
        UYDURULMAZ, None döner ve çağıran beyanına düşer.

        Bu fonksiyon v2.6.27 parti 31'de ``_oxidizer_atomisation_time``
        içinden ÇIKARILDI: kalış süresi çaprazı aynı yoğunluğu istiyordu ve
        formülün ikinci bir kopyası iki alanı sessizce ayrıştırabilirdi.
        """
        mw = basic_results.get('molecular_weight')
        t_c = basic_results.get('chamber_temperature')
        p_c = basic_results.get('chamber_pressure')
        try:
            rho_gas = (float(p_c) * PA_PER_BAR
                       / ((R_UNIVERSAL / float(mw)) * float(t_c)))
        except (TypeError, ValueError, ZeroDivisionError):
            return None
        if not (rho_gas and np.isfinite(rho_gas) and rho_gas > 0):
            return None
        return float(rho_gas)

    def _tau_c_residual_terms(self, basic_results, tau_c, residence_s):
        """τ_c ↔ kalış süresi oranının ADLI çarpanları — ya tam sözlük ya None.

        ÖH D37 A2 hibrit · F-09 (= OH-D31-09). Cebir (Lean:
        ``formal/LeanLab/HRMAInjector.lean`` ``tauC_ratio_factorises``):
        ṁ = C_D·Pc·A_t/c*, ρ = Pc/(R·T), τ_c = L*/(c*·Γ²), L* = V/A_t ⇒

            (ρ·V/ṁ) / τ_c = (1/C_D) · (c*·Γ)² / (R·T)

        Terim 1 boğaz debi katsayısı (``THROAT_DISCHARGE_COEFFICIENT``,
        boğazı kuran AYNI sabit); terim 2 R·T özdeşliğinin tüketicide
        kırılması — ρ_gaz ``_chamber_gas_density`` ile (R_u/MW)·T_c'den,
        τ_c ise c*'tan kurulur. İkisinin çarpımı ``explained_ratio``;
        ``unexplained_pct`` geriye kalandır ve SIFIRKEN DE yayımlanır
        (kapanış: explained·(1 + unexplained/100) = ratio, Lean
        ``residual_decomposition_closes``). Anahtar kümesi ve künye sıvı
        motorunkiyle AYNI (``TAU_C_RESIDUAL_DECOMPOSITION_BASIS`` tek tanım);
        girdi eksikse None (alan konmaz, oran yine yayımlanır).

        ÖLÇÜLDÜ (once K3): oran 1,028589 = 1,020408 (1/C_D) × 1,008017
        (R·T kırığı); C_D terimi olmadan %2,04 açıklanamaz kalırdı.
        """
        try:
            from hrma.stability.chamber import rt_from_cstar
            from hrma.engines.liquid_rocket_engine import (
                TAU_C_RESIDUAL_DECOMPOSITION_BASIS,
            )
            _cd = float(THROAT_DISCHARGE_COEFFICIENT)
            _rt_cstar = float(rt_from_cstar(float(tau_c['c_star_m_s']),
                                            float(tau_c['gamma'])))
            _rt_direct = float(
                (R_UNIVERSAL / float(basic_results['molecular_weight']))
                * float(basic_results['chamber_temperature']))
            _oran = float(residence_s) / float(tau_c['tau_c_s'])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None
        if not (_cd > 0 and _rt_direct > 0 and _rt_cstar > 0
                and np.isfinite(_oran)):
            return None
        _cd_terim = 1.0 / _cd
        _rt_terim = _rt_cstar / _rt_direct
        _aciklanan = _cd_terim * _rt_terim
        return {
            'discharge_coefficient_term': _cd_terim,
            'throat_discharge_coefficient': _cd,
            'rt_identity_term': _rt_terim,
            'rt_from_cstar_m2_s2': _rt_cstar,
            'rt_from_cea_m2_s2': _rt_direct,
            'rt_identity_break_pct': (_rt_direct - _rt_cstar) / _rt_cstar
            * 100.0,
            'explained_ratio': _aciklanan,
            'unexplained_pct': (_oran - _aciklanan) / _aciklanan * 100.0,
            '_basis': TAU_C_RESIDUAL_DECOMPOSITION_BASIS,
        }

    def _chamber_residence_time(self, basic_results):
        """Kalış süresi τ = ρ_gaz·V_c/ṁ [s] — τ_c'nin İKİNCİ yolu.

        Hacim GERÇEKLEŞEN serbest hacimdir (``chamber_volume_actual_m3``,
        yani L*_achieved'in hesaplandığı hacim) — tasarım hedefi V_c değil;
        aksi hâlde çapraz kendi kendini doğrulayan bir özdeşliğe dönerdi.
        Debi TOPLAM debidir (ox + gerileme kaynaklı yakıt): odayı dolduran
        kütle akışı odur.

        Girdilerden biri yoksa None döner (uydurma sayı yasağı).
        """
        rho_gas = self._chamber_gas_density(basic_results)
        v_c = basic_results.get('chamber_volume_actual_m3')
        mdot = basic_results.get('mdot_total')
        if rho_gas is None:
            return None
        try:
            v_c = float(v_c)
            mdot = float(mdot)
        except (TypeError, ValueError):
            return None
        if not (np.isfinite(v_c) and v_c > 0 and np.isfinite(mdot)
                and mdot > 0):
            return None
        return float(v_c * rho_gas / mdot)

    def _oxidizer_atomisation_time(self, basic_results):
        """(t_atomizasyon [s] | None, gerekçe) — sıvıdaki ikincil parçalanma ikizi.

        Duyarlı zaman gecikmesi τ için hibrit çözümünde MEVCUT olan zaman
        ölçeği, enjektör devre çözümünün kendi jetinden türeyen ikincil
        (aerodinamik) parçalanma süresidir:

            t_b = T*·d_jet/v_jet·√(ρ_sıvı/ρ_gaz)

        Sıvı motordaki ``_atomisation_time`` ile AYNI bağıntı ve AYNI sabit
        (T* = DROPLET_BREAKUP_TIME_CONST, Pilch & Erdman 1987; Nicholls
        1972) — sabit oradan İTHAL edilir, ikinci bir kopya yazılmaz.
        Jet çapı/hızı enjektör tasarım modelinin KENDİ çözümünden gelir;
        çözüm yoksa süre uydurulmaz, None döner ve çağıran NOT_EVALUATED
        beyanına düşer.
        """
        inj = basic_results.get('injector_design') or {}
        d_jet_mm = inj.get('orifice_diameter_mm')
        v_jet = inj.get('injection_velocity_m_s')
        if not d_jet_mm or not v_jet:
            return None, ('not_modelled: the injector circuit did not solve '
                          'a jet diameter/velocity on this run, so the '
                          'atomisation time scale is not resolved')
        rho_l = getattr(self, '_inj_rho_ox', None)
        if not (rho_l and np.isfinite(rho_l) and rho_l > 0):
            return None, 'not_modelled: liquid oxidizer density unavailable'
        rho_gas = self._chamber_gas_density(basic_results)
        if rho_gas is None:
            return None, ('not_modelled: the chamber gas state (P_c, T_c, '
                          'MW) did not produce a usable gas density')
        from hrma.engines.liquid_rocket_engine import (
            DROPLET_BREAKUP_TIME_CONST,
        )
        t_b = (DROPLET_BREAKUP_TIME_CONST * (float(d_jet_mm) * 1e-3)
               / float(v_jet) * np.sqrt(float(rho_l) / rho_gas))
        return float(t_b), (
            f'secondary (aerodynamic) breakup time t = T*·d_jet/v_jet·'
            f'sqrt(rho_l/rho_gas) with T* = {DROPLET_BREAKUP_TIME_CONST:g} '
            f'(Pilch & Erdman 1987; Nicholls 1972 — the same constant the '
            f'liquid engine imports, not a second copy); d_jet = '
            f'{float(d_jet_mm):.3f} mm and v_jet = {float(v_jet):.1f} m/s '
            f'come from the injector circuit solution of THIS run, the '
            f'liquid density is the oxidizer injection density and the gas '
            f'density is P_c/(R*T_c) of the same run')

    def _chug_tau_candidates(self, basic_results):
        """({ad: τ [s]}, arama kaydı) — çevrime verilecek İKİNCİ zaman ölçeği.

        ÖH D33-2 · **OH-D32-07** (defter P6B4-03 / OH-D31-08 hibrit ayağı).
        Sıvı motorda çevrim, aynı yanıtta yayımlanan İKİNCİ karışım zaman
        ölçeğini (``injection_system.mixing_residence_time``) aday olarak
        alır ve ``tau_choice_sensitivity`` bloğunu üretir. Hibrit ayağında
        ``assess_chug`` ``alternative_taus`` HİÇ almıyordu ve blok sessizce
        yok oluyordu: tüketici, alanın yokluğunu "ölçüldü, duyarsız" diye
        okuyabiliyordu.

        ÖLÇÜLDÜ (``docs/scofield/raw/OH/D33-2/motorlar/a1/once.json``,
        OH-D32-07; 1 kN / 20 bar HTPB-N2O): yanıtın TAMAMINDA
        ``tau_choice_sensitivity`` **0** kez, ``mixing_residence_time``
        **0** kez geçiyor. Yani hibrit enjektör bloğu bugün ikinci bir
        karışma zaman ölçeği YAYIMLAMIYOR.

        Bu yüzden burada ikinci bir ölçek ÜRETİLMEZ (sayı uydurma yasağı);
        aranan kaynaklar tek tek yoklanır ve her REDDİN gerekçesi kayda
        geçer. Çağıran, geçerli aday çıkmadıysa bunu ADIYLA yayımlar —
        alanın yokluğu sessiz kalmaz.

        Aday OLMAYANLAR da bilerek kayda geçer:

        * ``combustion_stability.lfi.boundary_layer_delay_s`` — hibrit LFI'nin
          yakıt buharlaşma ısıl gecikmesi. AYRI bir mekanizmadır
          (``mechanism_scope``: bu çevrim oksitleyici besleme hattı +
          enjektör üzerinden kapanır, LFI yakıt sınır tabakası üzerinden);
          onu bu çevrime τ adayı yapmak iki mekanizmayı ÇİFT SAYMAK olurdu.
        * ``chug_loop.tau_c_vs_residence_time.residence_time_s`` — odanın
          kalış süresi. O, τ_c'nin İKİNCİ YOLUDUR (ρ·V_c/ṁ), yanma
          gecikmesi değil; τ adayı yapmak τ ile τ_c'yi aynı büyüklüğe
          indirir.
        """
        adaylar = {}
        arama = []
        inj = basic_results.get('injector_design') or {}
        ms = inj.get('mixing_residence_time')
        saniye = None
        if ms is not None:
            try:
                saniye = float(ms) / 1000.0     # ms -> s (blok ms yayımlar)
            except (TypeError, ValueError):
                saniye = None
            if saniye is not None and not (np.isfinite(saniye)
                                           and saniye > 0.0):
                saniye = None
        if saniye is not None:
            adaylar['mixing_residence_time'] = saniye
            arama.append(
                'injector_design.mixing_residence_time: accepted as a '
                'candidate (read from the injector block of THIS run, not '
                'recomputed here)')
        else:
            arama.append(
                'injector_design.mixing_residence_time: NOT published by the '
                'hybrid injector block on this run, so there is no second '
                'mixing time scale to compare against; none is invented')
        arama.append(
            'combustion_stability.lfi.boundary_layer_delay_s: deliberately '
            'NOT a candidate - it belongs to the fuel-vaporisation LFI '
            'mechanism, which this loop explicitly does not cover '
            '(mechanism_scope); using it here would double count two '
            'separate mechanisms')
        arama.append(
            'chug_loop.tau_c_vs_residence_time.residence_time_s: '
            'deliberately NOT a candidate - it is the SECOND ROUTE to the '
            'chamber time constant tau_c (rho*V_c/mdot), not a combustion '
            'delay')
        return adaylar, arama

    def _chug_loop_block(self, basic_results):
        """Gerçek chug çevrimi (hrma.stability.chug) + oran kuralıyla İLİŞKİ.

        Sıvı motordaki ``_chug_loop_block`` deseninin hibrit ikizi. Oran
        kuralı (ΔP/Pc eşiği, acoustic_modes.stability_report.chug — TEK
        KAYNAK, burada tekrarlanmaz) yalnız enjektör kazancına bakar;
        gecikmeyi (τ) ve kamara zaman sabitini (τ_c) HİÇ görmez. Çevrim
        üçünü birden kullanır. İkisi çeliştiğinde HRMA birini diğerine
        EZDİRMEZ: ikisi de yayımlanır ve ilişki ``rule_vs_loop`` alanında
        ölçülür.

        J değeri oran kuralının KENDİ ölçtüğü orandır (aynı sözlükten
        okunur): kural ile çevrim aynı büyüklüğe iki ayrı sayı veremez.
        """
        rule = ((basic_results.get('acoustic_modes') or {})
                .get('stability_report') or {}).get('chug') or {}
        missing = []
        dp_pc = rule.get('injector_dp_ratio') if rule.get('evaluated') else None
        if not (dp_pc and np.isfinite(dp_pc) and dp_pc > 0):
            dp_pc = None
            missing.append('injector_dp_over_pc (J = dP_inj/Pc, from '
                           'acoustic_modes.stability_report.chug)')
        tau, tau_basis = self._oxidizer_atomisation_time(basic_results)
        if tau is None:
            missing.append(f'sensitive time lag tau ({tau_basis})')
        l_star = basic_results.get('l_star_achieved')
        if not (l_star and np.isfinite(l_star) and l_star > 0):
            missing.append('l_star_achieved')
            l_star = None
        c_star = basic_results.get('c_star')
        if not (c_star and np.isfinite(c_star) and c_star > 0):
            missing.append('c_star_m_s')
            c_star = None
        gamma = basic_results.get('gamma')
        if not (gamma and np.isfinite(gamma) and 1.0 < gamma < 2.0):
            missing.append('gamma')
            gamma = None
        if missing:
            return {
                'status': 'NOT_EVALUATED',
                'missing_inputs': missing,
                '_basis': (
                    'The oxidizer feed-coupled chug loop needs J, the '
                    'sensitive time lag tau, L* and c*. One or more were not '
                    'solved on this run, so no loop result is fabricated.'),
            }

        from hrma.stability.chamber import chamber_time_constant
        from hrma.stability.chug import assess_chug

        try:
            tau_c = chamber_time_constant(l_star_m=float(l_star),
                                          c_star_m_s=float(c_star),
                                          gamma=float(gamma))
            tau_f, feed_echo = self._feed_line_inertance_inputs(basic_results)
            # ÖH D33-2 · OH-D32-07 — SEÇİMİN BEDELİ HİBRİTTE DE ÖLÇÜLÜR.
            # Sıvı ayağındaki desenin ikizi: yanıtta MEVCUT olan ikinci
            # zaman ölçeği çevrime ADAY olarak verilir; çekirdek her adayı
            # AYNI çevrimle fiilen koşar. Fail-closed: aday çözülemezse
            # liste boş kalır, alan HİÇ konmaz ve yokluğun gerekçesi
            # aşağıda ADIYLA yayımlanır (uydurma aday yok).
            aday_taular, aday_arama = self._chug_tau_candidates(basic_results)
            loop = assess_chug(dp_ratio_j=float(dp_pc), tau_s=tau,
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
        # ÖH D33-2 · OH-D32-07 — ALANIN YOKLUĞU SESSİZ KALMAZ.
        # ``tau_choice_sensitivity`` yalnız GEÇERLİ bir alternatif aday
        # varken konur. Yokluğunda tüketici bunu "ölçüldü, duyarsız" diye
        # okuyamamalı: hangi kaynakların yoklandığı ve her REDDİN gerekçesi
        # yayımlanır. "Ölçülmedi" ile "duyarsız" aynı şey değildir
        # (aynı doktrin: chug.frequency_span_not_resolved_reason).
        if 'tau_choice_sensitivity' not in loop:
            loop['tau_choice_not_measured'] = {
                'reason': (
                    'The tau-choice sensitivity block is NOT published: this '
                    'run resolved no SECOND time scale that belongs to this '
                    'mechanism, so there was nothing to run the loop '
                    'against. This is "not measured", NOT "measured and '
                    'insensitive" - the single published tau_s carries its '
                    'full uncertainty into verdict, frequency_hz and '
                    'growth_rate_1_s.'),
                'candidate_sources_examined': aday_arama,
                'liquid_engine_cross_reference': (
                    'The liquid engine publishes tau_choice_sensitivity '
                    'because its injector block publishes a second scale '
                    '(mixing_residence_time); the hybrid injector block does '
                    'not. The two responses differ because the INPUTS '
                    'differ, not because the hybrid verdict is better '
                    'determined.'),
            }
        loop['chamber_time_constant'] = tau_c
        loop['tau_c_source'] = (
            'tau_c = L*/(c* Gamma^2) with the ACHIEVED L* of this run '
            '(l_star_achieved = actual free chamber volume / throat area, '
            'the volume the lumped chamber balance actually fills), the '
            'delivered c* and the equilibrium gamma of the same run.')
        loop['tau_source'] = (
            'atomisation (secondary breakup) time of this run\'s OXIDIZER '
            'injector solution, used as the sensitive time lag; its own '
            'uncertainty propagates DIRECTLY into the verdict. This is a '
            'CONSERVATIVE choice with a known direction: the sensitive lag '
            'is only the pressure-sensitive part of the total delay, while '
            'the breakup time is the full time scale, so substituting it '
            'can only move the verdict toward "unstable", never away from '
            'it (Crocco & Cheng, AGARDograph 8, 1956). ' + tau_basis)
        # --- τ_c'nin İKİNCİ yolu: bu koşunun kendi kalış süresi -------------
        # Sıvı ayağındaki çaprazın hibrit İKİZİ (v2.6.27 parti 31). Alan
        # biçimi ORTAK yardımcıdan gelir (tau_c_vs_residence_time_field) —
        # ikinci bir sözlük tanımı yazılmaz; motora ÖZGÜ olan yalnız kalıntı
        # gerekçesidir. Girdi eksikse alan HİÇ konmaz.
        residence_s = self._chamber_residence_time(basic_results)
        if residence_s is not None:
            from hrma.engines.liquid_rocket_engine import (
                tau_c_vs_residence_time_field,
            )
            # ÖH D37 A2 hibrit · F-09 (= OH-D31-09): kalıntı iki adlı terime
            # AYRIŞTIRILIR (sıvı ayağının ikizi); terimler çözülemezse alan
            # HİÇ konmaz (uydurma yok), oran yine yayımlanır.
            loop['tau_c_vs_residence_time'] = tau_c_vs_residence_time_field(
                tau_c['tau_c_s'], residence_s, HYBRID_TAU_C_RESIDUAL,
                residual_terms=self._tau_c_residual_terms(
                    basic_results, tau_c, residence_s))
        # --- LFI ile ÇİFT SAYIM YOK beyanı (mekanizma kapsamı) -------------
        loop['mechanism_scope'] = (
            'oxidizer feed-coupled chug; the fuel-vaporisation LFI '
            'mechanism is assessed separately in combustion_stability.lfi')
        loop['mechanism_scope_basis'] = (
            'Two DIFFERENT low-frequency mechanisms are published side by '
            'side and neither includes the other: this loop closes through '
            'the oxidizer feed line and injector (delta_mdot_ox responding '
            'to delta_Pc through the orifice gain 1/(2J)), while the hybrid '
            'LFI of Karabeyoglu et al. closes through the thermal lag of '
            'fuel vaporisation in the port boundary layer and involves no '
            'feed-line quantity. Both verdicts are scope-labelled so '
            'neither can be read as covering the other mechanism.')
        # --- oran kuralı ile çevrimin İLİŞKİSİ (ölçülür, varsayılmaz) ------
        rule_status = rule.get('status')
        rule_says_safe = rule_status in ('OK', 'MARGINAL')
        loop_says_stable = loop.get('verdict') == 'stable'
        loop['rule_vs_loop'] = {
            'ratio_rule_status': rule_status,
            'ratio_rule_source': 'acoustic_modes.stability_report.chug '
                                 '(single source; not repeated here)',
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
                'atomisation correlation, not a measurement), while the '
                'rule is an engineering rule of thumb with decades of '
                'practice behind it and no explicit validity envelope.'),
        }
        return loop

    def _combustion_stability_block(self, basic_results):
        """Yanma kararlılığı bloğu (F2b-1 hibrit ayağı) — üç yol, tek çekirdek.

        Ayaklar birbirinden YAPISAL olarak farklıdır ve bu ayrım tasarım
        belgesi §3.0'ın kendisidir:

          * ``lfi`` — çevrimin KAPANDIĞI yer: gecikme de kazanç da çözücünün
            kendi büyüklüklerinden gelir, bu yüzden burada HÜKÜM verilir
            (kapsam etiketiyle, çekirdekten olduğu gibi taşınarak).
          * ``chug_loop`` — çevrimin KAPANDIĞI ikinci yer (v2.6.27, sıvı
            ayağının ikizi): oksitleyici besleme kuplajı; hüküm kapsam
            etiketlidir ve LFI'den AYRI bir mekanizmayı bağlar
            (``mechanism_scope`` beyanı çift sayımı reddeder).
          * ``acoustic_response_threshold`` — çevrimin kapanMADIĞI yer: yanma
            tepki fonksiyonu ölçülür, HRMA'da yok. Bu yolda yalnız EŞİK
            vardır ve 'verdict' anahtarı yapısal olarak yasaktır.

        CHUG ÇEVRİMİ BAĞLANDI (v2.6.27, sıvı ayağının ikizi): klasik
        enjektör basınç düşümü oranı marjı ``acoustic_modes.
        stability_report.chug`` içinde kalır ve TEK KAYNAK odur; buradaki
        ``chug_loop`` o oranı AYNI sözlükten okuyarak konsantre-parametreli
        çevrimi (τ, τ_c, J birlikte — hrma.stability.chug) kurar. Aynı
        büyüklük iki blokta iki ayrı tanımla yayımlanmaz; kural ile
        çevrimin ilişkisi ``chug_loop.rule_vs_loop`` alanında ölçülür.
        """
        from hrma.stability import STABILITY_NOT_MODELLED

        return {
            'model': 'hrma.stability F2b hybrid binding',
            '_basis': (
                'Combustion stability binding of the hrma/stability core to '
                'the hybrid solver. The mode table itself is NOT reproduced '
                'here: it stays in the acoustic_modes block and is read from '
                'there. Two paths with different epistemic status are '
                'published side by side: a VERDICT where the feedback loop '
                'closes from solver quantities (hybrid LFI and the oxidizer '
                'feed-coupled chug loop) and a THRESHOLD where it does not '
                '(acoustic critical response). The classical chug RATIO RULE '
                'is not repeated here; it stays in '
                'acoustic_modes.stability_report.chug (single source) and '
                'chug_loop reads its ratio from that very dictionary — the '
                'relation between rule and loop is measured in '
                'chug_loop.rule_vs_loop.'),
            'operating_point': 'design_instant_t0',
            'operating_point_basis': (
                'Both paths are evaluated at the design instant (t = 0): the '
                'initial oxidizer flux with the initial O/F, the ignition '
                'chamber geometry and the design chamber pressure. The port '
                'grows during the burn, so both the LFI frequency and the '
                'damping budget move with it; no time history is claimed.'),
            'lfi': self._hybrid_lfi_block(basic_results),
            'acoustic_response_threshold':
                self._acoustic_response_threshold_block(basic_results),
            # Oksitleyici besleme kuplajlı chug çevrimi (sıvı ayağının
            # ikizi). Oran KURALI burada tekrarlanmaz — çevrim, kuralın
            # kendi ölçtüğü J'yi acoustic_modes.stability_report.chug
            # sözlüğünden okur ve ilişkiyi rule_vs_loop ile ölçer.
            'chug_loop': self._chug_loop_block(basic_results),
            'not_modelled': {
                ad: STABILITY_NOT_MODELLED[ad] for ad in (
                    'detailed_flame_dynamics', 'vortex_shedding', 'pogo',
                    'injection_coupled_hf', 'three_dimensional_acoustics',
                    'damping_devices')
            },
            'not_modelled_basis': (
                'Scope-level declarations carried verbatim from '
                'hrma.stability.STABILITY_NOT_MODELLED. Limits that belong to '
                'a single mechanism (oscillation amplitude, nonlinear '
                'triggering, the missing response measurement, the damping '
                'terms that are not in the budget) are declared INSIDE the '
                'sub-block they belong to and are not repeated here.'),
        }

    def _nozzle_flow_block(self, basic_results):
        """Yarı-1B lüle iç akışı + ayrılma denetimi (hrma.flow).

        hrma/flow/quasi1d.py (rejim sınıflandırması, izantropik dallar, lüle
        içi normal şok konumu — Anderson 3. baskı Böl. 3/5) ve
        hrma/flow/separation.py (Summerfield / Schmucker / Kalt-Badal
        ayrılma kriterleri) motor zincirine HİÇ bağlı değildi: paket
        docstring'i bunu "bağlama sonraki dalganın işidir" diye yazıyordu.

        GİRDİLER — hepsi bu koşunun gerçek çözümünden:
          * alan profili: ekrandaki 2B kesitin, 3B sahnenin ve STL/STEP
            çıktısının kullandığı AYNI örnekleyiciden
            (nozzle_design.sample_nozzle_inner_contour) A(x) = pi*r(x)^2,
          * P0/T0: kamara basıncı ve denge kamara sıcaklığı,
          * gamma ve R: yanma dengesinin kamara kaydından (R = R_u/MW) —
            akustik blokla AYNI çift, iki blok aynı gaz için iki farklı
            özellik kullanamaz,
          * geri basınç: tasarım ortam basıncı.

        Kütle debisi çapraz denetimi yayımlanır: yarı-1B boğulmuş debi ile
        çözücünün ṁ_toplam'ı AYNI olmak zorunda değildir (biri kalorik
        mükemmel gaz, diğeri denge c* + c* verimi) ve fark GİZLENMEZ.
        """
        basis = (
            'quasi-one-dimensional compressible nozzle flow (hrma/flow/'
            'quasi1d.py: isentropic area-Mach solution with back-pressure '
            'regime classification and in-nozzle normal-shock location, '
            'Anderson "Modern Compressible Flow" 3rd ed. Ch. 3 and 5) plus '
            'the boundary-layer separation screen (hrma/flow/separation.py: '
            'Summerfield / Schmucker / Kalt-Badal criteria with declared '
            'validity bands). The area profile A(x) = pi*r(x)^2 is sampled '
            'from the SAME inner-contour sampler the 2D section, the 3D '
            'scene and the STL/STEP exports consume, so the flow solution '
            'and the drawn hardware cannot diverge. P0/T0 are the chamber '
            'pressure and equilibrium chamber temperature of this run; gamma '
            'and R = R_u/MW come from the combustion chamber record (the '
            'same pair the acoustic block uses); the back pressure is the '
            'design ambient pressure.')

        gamma = basic_results.get('gamma')
        mw = basic_results.get('molecular_weight')
        t_c = basic_results.get('chamber_temperature')
        eksik = []
        if not (gamma and 1.0 < float(gamma) < 2.0):
            eksik.append('chamber gamma')
        if not (mw and float(mw) > 0):
            eksik.append('chamber molecular_weight (needed for R = R_u/MW)')
        if not (t_c and float(t_c) > 0):
            eksik.append('chamber_temperature')
        if not (self.P_c and float(self.P_c) > 0):
            eksik.append('chamber_pressure')
        if eksik:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': ('the nozzle flow was not solved and no regime is '
                           'invented; missing solver output(s): '
                           + ', '.join(eksik)),
            }

        try:
            pts_mm, _meta = sample_nozzle_inner_contour(basic_results)
            x_m = np.asarray([float(z) / 1000.0 for z, _r in pts_mm])
            r_m = np.asarray([float(r) / 1000.0 for _z, r in pts_mm])
            area = np.pi * r_m ** 2
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (f'the nozzle inner contour could not be sampled '
                           f'for this design, so no area profile exists to '
                           f'solve: {exc}'),
            }

        p0 = float(self.P_c) * 1e5              # bar -> Pa
        pb = float(self.P_a) * 1e5              # bar -> Pa
        gamma = float(gamma)
        # ÖH D24 / P10B3-10: tek kaynak (hrma.constants.R_UNIVERSAL,
        # :28'de ithal). SAYI AYNI (8 314,462618).
        r_specific = R_UNIVERSAL / float(mw)    # J/(kg*K)

        try:
            from hrma.flow import assess_separation, solve_nozzle
            sol = solve_nozzle(x_m, area, P0=p0, T0=float(t_c), gamma=gamma,
                               R=r_specific, Pb=pb)
        except Exception as exc:
            return {
                'status': 'NOT_MODELLED',
                '_basis': basis,
                'reason': (f'the quasi-1D solver rejected this nozzle: '
                           f'{exc}'),
            }

        n = len(sol['x_m'])
        stride = max(1, n // NOZZLE_FLOW_MAX_POINTS)
        idx = list(range(0, n, stride))
        if idx[-1] != n - 1:
            idx.append(n - 1)

        def _pick(dizi, olcek=1.0):
            return [float(dizi[i]) * olcek for i in idx]

        sok = sol.get('shock')
        sok_blok = None
        if isinstance(sok, dict):
            sok_blok = {
                'x_m': float(sok['x_m']),
                'area_ratio': float(sok['area_ratio']),
                'mach_upstream': float(sok['mach_upstream']),
                'mach_downstream': float(sok['mach_downstream']),
                'stagnation_pressure_ratio': float(sok['p02_p01']),
                'stagnation_pressure_downstream_Pa': float(
                    sok['stagnation_pressure_downstream_Pa']),
                '_basis': (
                    'Rankine-Hugoniot jump; the shock station is the one '
                    'whose downstream subsonic diffusion matches the back '
                    'pressure at the exit (Anderson Ch. 5.4)'),
            }

        mdot_flow = float(sol['mass_flow_kg_s'])
        mdot_solver = float(getattr(self, 'mdot_total', 0.0) or 0.0)
        # D15/P1B2-05: beklenen kalıntının payı. eta_c* verilmediyse 1,0'dır
        # (c* verimi uygulanmamış demektir), uydurma bir sayı KONULMAZ.
        _eta_cs = (1.0 if getattr(self, 'eta_c_star', None) is None
                   else float(self.eta_c_star))

        # --- D16/OH-Z5-07 · ÇAPRAZ DENETİMİN ÇÖZÜNÜRLÜĞÜ VE HÜKMÜ ---------
        # ÖLÇÜLDÜ (a2/once.json): `mass_flow_rel_diff` beş çalışma noktasında
        # da eta_c*/C_D - 1 ile 13+ hane örtüşüyor (fark 1,2e-16 ... 3,4e-16),
        # yani TEK BAŞINA totolojiktir — yaprağın kendisi bunu söylemeliydi,
        # söylemiyordu (yalnız uzun `mass_flow_check_basis` metni söylüyordu).
        # ÖLÇÜLDÜ (a2/once.json, totoloji_sinamasi): artık yaprağı ise CANLI —
        # gamma %5 kaydırılınca 0,0178, %5 düşürülünce -0,0186, MW %5
        # kaydırılınca 0,0252 oluyor. Yani "izlenecek sayı" gerçekten bir
        # sensördür; ama İZLEYEN YOKTU (kanal var, kapı yok).
        # ÖLÇÜLDÜ: çözücünün KENDİ kütle korunum artığı 2,6e-14 ... 1,0e-12,
        # yani gaz-modeli artığından 2-4 kat büyüklük mertebesi BÜYÜK. Bu
        # yüzden eski künyedeki "sıfırdan her sapma gerçek bir ayrışmadır"
        # cümlesi FAZLA İDDİALIYDI: çözücünün kendi sayısal gürültüsünün
        # altındaki bir sapma ayırt edilemez. Çözünürlük tabanı UYDURULMAZ,
        # çözücünün kendi yayımladığı artıktan okunur (tek kaynak).
        #
        # --- ÖH D18 fizik-a1 / F1 · c* GAZ-MODELİ ORANI defterin parçasıdır -
        # D18'e kadar yayımlanan c* tek-γ kapalı formundan geliyordu ve
        # yarı-1B çözücü de aynı (γ, R, T_c) üçlüsünü kullandığından
        # mdot_flow ≡ P_c·A_t/c*_tek-γ oluyordu — yani "artık" YAPI GEREĞİ
        # sıfırdı. F1'den sonra manşet c* kayan-denge boğaz istasyonundan
        # geliyor (B3-05), dolayısıyla iki zincir arasında BİLİNEN bir
        # model oranı var: c*_denge/c*_tek-γ. ÖLÇÜLDÜ (bu depoda, D15
        # sağlıklı koşum motoru): oran 1,003868, artık 3,946e-03 —
        # kapının 'divergent' demesine yeten ama TAMAMEN AÇIKLANABİLİR bir
        # fark. Beklenen kalıntı bu oranı da içerir; geriye kalan sayı
        # yine gerçek ayrışmanın sensörüdür (D15 ölçümü: γ %5 kayınca
        # 0,0178). Oran okunamıyorsa (ampirik yol) 1,0 alınır ve bu
        # 'mass_flow_c_star_model_ratio' alanıyla görülür.
        _c_star_eq = getattr(self, 'C_star_theoretical', None)
        _c_star_1g = getattr(self, 'C_star_single_gamma', None)
        _c_star_orani = (
            float(_c_star_eq) / float(_c_star_1g)
            if (isinstance(_c_star_eq, (int, float))
                and isinstance(_c_star_1g, (int, float))
                and float(_c_star_1g) > 0.0)
            else 1.0)
        _mdot_rel = ((mdot_flow - mdot_solver) / mdot_solver
                     if mdot_solver > 0 else None)
        _mdot_beklenen = ((_eta_cs * _c_star_orani
                           / THROAT_DISCHARGE_COEFFICIENT - 1.0)
                          if mdot_solver > 0 else None)
        _mdot_artik = (None if (_mdot_rel is None or _mdot_beklenen is None)
                       else _mdot_rel - _mdot_beklenen)
        _cozunurluk = abs(float(sol['mass_conservation_rel_residual']))
        if _mdot_artik is None:
            _capraz_hukum = 'not_applicable'
        elif abs(_mdot_artik) > _cozunurluk:
            _capraz_hukum = 'divergent'
        else:
            _capraz_hukum = 'pass'
        blok = {
            'status': 'modelled',
            '_basis': basis,
            'regime': sol['regime'],
            'regime_basis': (
                'back-pressure classification against the three critical '
                'exit pressures of this area ratio (choked-subsonic, '
                'shock-at-exit, fully supersonic); the numeric thresholds '
                'are in critical_pressures'),
            'critical_pressures': {
                k: float(v) for k, v in (sol['critical_pressures'] or {}).items()
                if isinstance(v, (int, float))},
            'throat': {
                'x_m': float(sol['throat']['x_m']),
                'area_m2': float(sol['throat']['area_m2']),
                'choked': bool(sol['throat']['choked']),
            },
            'shock': sok_blok,
            'exit': {
                'mach': float(sol['exit']['mach']),
                'pressure_Pa': float(sol['exit']['pressure_Pa']),
                'temperature_K': float(sol['exit']['temperature_K']),
                'velocity_m_s': float(sol['exit']['velocity_m_s']),
                'back_pressure_match': bool(
                    sol['exit']['back_pressure_match']),
            },
            'stations': {
                'x_m': _pick(sol['x_m']),
                'area_m2': _pick(sol['area_m2']),
                'mach': _pick(sol['mach']),
                'pressure_Pa': _pick(sol['pressure_Pa']),
                'temperature_K': _pick(sol['temperature_K']),
                '_basis': (
                    'stations of the sampled inner contour (thinned to at '
                    f'most ~{NOZZLE_FLOW_MAX_POINTS} points, last station '
                    'always kept)'),
            },
            'mass_flow_kg_s': mdot_flow,
            'mass_flow_solver_kg_s': mdot_solver,
            'mass_flow_rel_diff': _mdot_rel,
            # D16/OH-Z5-07: yaprağın KENDİ künyesi. Bu sayıyı tek başına
            # okuyan bir tüketici onu "çapraz denetim" sanıyordu; oysa
            # YAPISI GEREĞİ SABİTTİR ve hiçbir girdiyle oynamaz.
            'mass_flow_rel_diff_basis': (
                'STRUCTURALLY CONSTANT, not an independent comparison. Both '
                'mass flows are built from the same chamber state, so this '
                'ratio reduces identically to eta_c*/C_D - 1 '
                '(mass_flow_expected_rel_diff) and stays there whatever the '
                'thrust, chamber pressure, expansion ratio or propellant. '
                'Measured across five unrelated design points it agreed with '
                'that identity to 13+ digits. The number that actually '
                'compares the two gas models is '
                'mass_flow_gas_model_rel_residual, and the verdict on it is '
                'in mass_flow_cross_check.'),
            # --- D15/P1B2-05 · ÇAPRAZ DENETİMİN GERÇEK KALINTISI ----------
            # ÖLÇÜLDÜ (a3/once.json, B2_05): eski gerekçe farkı "kalorik
            # mükemmel gaz <-> denge c* zinciri"ne bağlıyordu. Üç TAMAMEN
            # farklı tasarımda (F=3000/Pc=30/eps=4/HTPB, F=800/Pc=15/
            # eps=2,5/HTPB, F=12000/Pc=45/eps=12/parafin) mass_flow_rel_diff
            # ALTI HANE aynı çıktı: %2,0408163 = 1/C_D - 1; eta_c*=0,92 ile
            # %-6,1224490 = eta/C_D - 1. Gaz modelinin katkısı ölçülen
            # 1,8e-16 (yani SIFIR). Yani eski beyan yanlıştı ve çapraz
            # denetim KÖRDÜ: gerçek bir gaz-modeli ayrışması sabit %2,04
            # kaymanın içinde görünmezdi.
            #
            # Artık üç sayı ayrı ayrı yayımlanır:
            #   * beklenen kalıntı  = eta_c*/C_D - 1  (tanım gereği)
            #   * kalan (ARTIK) kalıntı = ölçülen - beklenen  -> gaz modeli
            #     ayrışmasının GERÇEK göstergesi; sıfırdan uzaklaşırsa
            #     gerçekten iki gaz modeli ayrışmıştır.
            # Aynı dosya doğrusunu zaten biliyordu: HYBRID_TAU_C_RESIDUAL
            # künyesi "the expected residual is exactly 1/C_D" diyor.
            'mass_flow_expected_rel_diff': _mdot_beklenen,
            # ÖH D18 F1: beklenen kalıntının İKİNCİ defter terimi. 1,0'dan
            # farkı, kayan-denge c* ile tek-γ kapalı formu arasındaki gaz
            # modeli farkıdır (B3-05); ampirik yolda 1,0 kalır.
            'mass_flow_c_star_model_ratio': float(_c_star_orani),
            'mass_flow_c_star_model_ratio_basis': (
                'c_star (shifting-equilibrium throat station, RP-1311 eq. '
                '6.11) divided by c_star_single_gamma (calorically perfect '
                'closed form built from the chamber gamma, R and T). The '
                'quasi-1D solver runs the same calorically perfect gas, so '
                'this ratio is bookkeeping between the two gas models, not '
                'a divergence.'),
            'mass_flow_gas_model_rel_residual': _mdot_artik,
            # D16/OH-Z5-07 — KAPI. Artık yaprağı D15'te yayımlanmıştı ama
            # hiçbir hüküm ona bağlı değildi. Çözünürlük tabanı çözücünün
            # KENDİ kütle korunum artığıdır (yeni sabit doğmaz); bu tabanın
            # altındaki bir sapma sayısal gürültüden ayırt EDİLEMEZ, o yüzden
            # 'pass' hükmü "ayrışma yok" değil "ayırt edilebilir ayrışma yok"
            # demektir ve künyesi bunu böyle söyler.
            'mass_flow_cross_check': {
                'status': _capraz_hukum,
                'residual': _mdot_artik,
                'resolution': _cozunurluk,
                'resolution_source': (
                    'mass_conservation_rel_residual of this same quasi-1D '
                    'solution: the solver\'s own relative mass-flow '
                    'inconsistency. A gas-model residual below it cannot be '
                    'told apart from the integration noise.'),
                'basis': (
                    'PASS means no gas-model divergence is resolvable at this '
                    'run\'s numerical resolution - it is not a claim that the '
                    'two models agree exactly. DIVERGENT means the residual '
                    'left after removing the eta_c*/C_D bookkeeping exceeds '
                    'the solver\'s own mass-conservation residual, so the '
                    'quasi-1D calorically perfect gas and the equilibrium c* '
                    'chain really are describing different gases and the '
                    'nozzle flow stations should not be read as the same gas '
                    'as the chamber record.'),
            },
            'mass_flow_check_basis': (
                'CROSS-CHECK, not a correction. The whole of the expected '
                'difference is BOOKKEEPING, not physics: the quasi-1D solver '
                'integrates the geometric throat area with no discharge '
                'coefficient, while the headline mdot_total carries both the '
                'throat discharge coefficient C_D = '
                f'{THROAT_DISCHARGE_COEFFICIENT:g} and the c* efficiency '
                f'eta_c* = {_eta_cs:g}. The expected residual is therefore '
                'exactly eta_c*/C_D - 1 (mass_flow_expected_rel_diff), the '
                'same identity HYBRID_TAU_C_RESIDUAL states for the chamber '
                'time constant. The gas model (calorically perfect gamma, R '
                'against the equilibrium c* chain) contributes only what is '
                'LEFT OVER after that identity is removed: that leftover is '
                'mass_flow_gas_model_rel_residual and it is the number to '
                'watch - measured at the 1e-16 level on this build. It is '
                'watched by mass_flow_cross_check, whose threshold is this '
                'solution\'s own mass_conservation_rel_residual rather than '
                'zero: the solver\'s integration noise sits two to four '
                'orders of magnitude above the leftover, so a departure '
                'smaller than that floor is not resolvable and is not '
                'reported as a divergence.'),
            'mass_conservation_rel_residual': float(
                sol['mass_conservation_rel_residual']),
            'inputs': {
                'P0_Pa': p0,
                'T0_K': float(t_c),
                'gamma': gamma,
                'R_J_kgK': r_specific,
                'Pb_Pa': pb,
                'back_pressure_source': (
                    'design ambient pressure of this run (atmospheric_'
                    'pressure input, bar)'),
                'gas_property_source': (
                    'combustion equilibrium chamber record: gamma directly, '
                    'R = 8314.462618 / molecular_weight'),
            },
            'not_modelled': {
                'wall_friction': (
                    'NOT_MODELLED: wall friction and the boundary layer are '
                    'ignored (inviscid core); the wall pressure is taken as '
                    'the isentropic core pressure.'),
                'heat_loss': (
                    'NOT_MODELLED: the flow is adiabatic, T0 is constant; '
                    'heat loss to the wall is not coupled here (the heat '
                    'transfer block solves that separately).'),
                'two_dimensional_effects': (
                    'NOT_MODELLED: uniform one-dimensional stations only - '
                    'streamline curvature, oblique shocks, shock/boundary-'
                    'layer interaction and lambda-shock structure are '
                    'absent.'),
                'real_gas': (
                    'NOT_MODELLED: calorically perfect gas with frozen '
                    'composition (constant gamma and R); the equilibrium '
                    'composition shift along the nozzle is not solved here.'),
                'external_adaptation': (
                    'NOT_MODELLED: outside the exit plane nothing is solved '
                    '- the oblique-shock (overexpanded) or expansion-fan '
                    '(underexpanded) adaptation happens beyond this model.'),
            },
        }

        # --- Ayrılma denetimi: aynı profil, aynı gamma ---------------------
        try:
            sep = assess_separation(p0, pb, gamma, x=x_m, area=area)
        except Exception as exc:
            blok['separation'] = {
                'status': 'NOT_MODELLED',
                'reason': (f'the separation criteria rejected these exit '
                           f'conditions: {exc}'),
            }
            return blok

        kriterler = {}
        for ad, kayit in (sep.get('criteria') or {}).items():
            kriterler[ad] = {
                'separated': bool(kayit.get('separated')),
                'wall_pressure_sep_Pa': kayit.get('wall_pressure_sep_Pa'),
                'pressure_ratio_threshold': kayit.get(
                    'pressure_ratio_threshold'),
                'mach_sep': kayit.get('mach_sep'),
                'area_ratio_sep': kayit.get('area_ratio_sep'),
                'x_sep_m': kayit.get('x_sep_m'),
                'outside_validity_band': bool(kayit.get('validity_warning')),
            }
        # ÖH D20 / OH-D17-05 — ``separated`` ÜÇ DEĞERLİDİR.
        # Ayrılma modülü hükmü KAZANAMADIĞINDA (boğaz boğulmamış: üç ölçüt de
        # aşırı genleşmiş SES-ÜSTÜ duvar sınır tabakası deneylerinden
        # kalibreli, ses-altı rejimde tanımsız) ``separated=None`` döndürür ve
        # gerekçesini ``not_applicable_reason`` ile söyler. Buradaki
        # ``bool(...)`` o None'ı FALSE'a çeviriyordu, yani "hüküm verilmedi"
        # ekrana "AYRILMA YOK" diye çıkıyordu — hüküm kazanılmadan yayım
        # (P6B3-01 sınıfı). Artık None AYNEN taşınır; ``status`` zaten
        # 'not_applicable' diyor ve gerekçe de birlikte yayımlanır.
        blok['separation'] = {
            'status': ('not_applicable' if sep.get('not_applicable_reason')
                       else 'modelled'),
            'separated': (None if sep.get('separated') is None
                          else bool(sep.get('separated'))),
            'not_applicable_reason': sep.get('not_applicable_reason'),
            'separated_verdict_basis': (
                'null means the separation criteria were NOT APPLICABLE on '
                'this run (see not_applicable_reason) - it does NOT mean '
                '"no separation". false means the criteria were evaluated '
                'and none of them predicts separation.'),
            'separated_criteria': list(sep.get('separated_criteria') or []),
            'controlling_criterion': sep.get('controlling_criterion'),
            'x_sep_m': sep.get('x_sep_m'),
            'area_ratio_sep': sep.get('area_ratio_sep'),
            'full_flow_exit_mach': (sep.get('full_flow_exit') or {}).get(
                'mach'),
            'criteria': kriterler,
            '_basis': (
                'three published separation correlations evaluated against '
                'the full-flowing isentropic wall pressure of THIS contour; '
                'the criterion that predicts separation furthest upstream '
                '(smallest A/A_t) controls (conservative choice). '
                '"outside_validity_band" flags a criterion evaluated outside '
                'its derivation band - the bands themselves are documented '
                'in hrma/flow/separation.py. NOT_MODELLED: separation side '
                'loads, free/restricted shock separation (FSS/RSS) '
                'distinction, the boundary-layer state itself and ignition/ '
                'shutdown separation hysteresis.'),
        }
        if sep.get('not_applicable_reason'):
            # ÖH D16 / P6B3-01 — GEREKÇE ARTIK SABİT CÜMLE DEĞİL. Buraya
            # "vakumda tanımsız" metni GÖMÜLÜYDÜ; modülün 'not applicable'
            # dalı o gün tek daldı. Modüle boğulmamış-rejim dalı eklenince
            # (hrma/flow/separation.py) sabit cümle YALAN söyleyecekti:
            # boğulmamış bir lüleye "vakum" gerekçesi basılırdı. Gerekçe
            # artık vakaya göre seçilir ve modülün KENDİ metni
            # not_applicable_basis ile yanında taşınır (ikinci gerçek kaynağı
            # olmasın diye).
            blok['separation']['not_applicable_reason'] = (
                'separation is undefined in vacuum (Pa = 0): the criteria '
                'are all defined against an ambient pressure'
                if pb <= 0.0 else
                'the throat is NOT choked at this back pressure, so there '
                'is no supersonic core anywhere in the nozzle; the three '
                'criteria are calibrated for over-expanded SUPERSONIC wall '
                'boundary layers and do not apply here. No separation '
                'verdict and no full-flowing supersonic exit state are '
                'published')
            blok['separation']['not_applicable_basis'] = (
                sep['not_applicable_reason'])
        return blok

    def _igniter_sizing_block(self, basic_results):
        """Ateşleyici boyutlandırma (hrma.analysis.igniter_sizing).

        Modül torç ve piroteknik ateşleyiciyi boyutlandırır ve sert başlangıç
        (hard start) penceresini denetler. Hibritte ÇAĞRILAMIYOR ve sebebi
        gizlenmiyor: modülün zorunlu girdilerinin çoğu bu çözücüde YOK.

        VAR OLANLAR: kamara serbest hacmi (V_c_actual — portun sardığı gerçek
        serbest hacim), ana kütle debisi (mdot_total), kamara basıncı, alev
        sıcaklığı ve gaz molekül ağırlığı.
        YOK OLANLAR: ateşleme penceresi (tasarım girdisi — sayfada alan yok),
        iticinin özgül ısısı ve TUTUŞMA SICAKLIĞI (hibrit yakıt tablosu
        yalnız yoğunluk, yanma sıcaklığı ve gaz sabiti taşır), torç ısı
        salımı ya da piroteknik şarj gaz özellikleri.
        """
        return {
            'status': 'NOT_MODELLED',
            '_basis': (
                'igniter sizing core (hrma/analysis/igniter_sizing.py): '
                'sensible-heat ignition energy, torch propellant flow, '
                'pyrotechnic charge mass from free-volume pressurisation and '
                'the constant-volume hard-start window (Sutton & Biblarz 9th '
                'ed. Ch. 8/15; NASA SP-8051). It is NOT evaluated here - the '
                'inputs it requires are not computed by the hybrid solver '
                'and are not fabricated.'),
            'reason': (
                'the hybrid solver has no ignition model and no propellant '
                'ignition data: the fuel property table carries density, '
                'combustion temperature and gas constant only - no specific '
                'heat and no ignition temperature - and there is no ignition-'
                'window input on the hybrid page. Without them neither the '
                'required ignition energy nor the hard-start window can be '
                'formed.'),
            'required_inputs': [
                'ignition_window_s',
                'propellant_specific_heat_J_kg_K',
                'propellant_ignition_temperature_K',
                'torch_heat_release_J_kg (torch) or charge gas properties '
                '(pyrotechnic)',
            ],
            'available_inputs': {
                'chamber_free_volume_m3': basic_results.get(
                    'chamber_volume_actual_m3'),
                'main_mass_flow_kg_s': basic_results.get('mdot_total'),
                'chamber_pressure_bar': basic_results.get('chamber_pressure'),
                'main_flame_temperature_K': basic_results.get(
                    'chamber_temperature'),
                'main_gas_molecular_weight_g_mol': basic_results.get(
                    'molecular_weight'),
                '_basis': (
                    'the inputs the solver DOES compute, listed so the gap '
                    'is auditable: only the propellant ignition data and the '
                    'ignition window are missing.'),
            },
        }

    def _not_modelled_declarations(self):
        """Modellenmeyen fizik kalemlerinin AÇIK beyanı (yol haritası A10).

        Sıvı motor 50'den fazla, katı motor onlarca beyan taşırken hibrit
        4 beyanla geziyordu: kullanıcı hibritte sessiz varsayımlarla
        karşılaşıyordu. Buradaki HER kalem iki koşulu birden sağlar:

          1. Sıvı/katı motorun beyan ettiği (ya da bağladığı) ve hibritte de
             fiziksel olarak geçerli bir kalemdir;
          2. Hibrit çözücüde o hesabın GERÇEKTEN var olmadığı kod okunarak
             doğrulanmıştır (2026-08-03 taraması: bu dosyada ignit*/valve/
             feed_line/acoustic için sıfır eşleşme; 2026-08-04 A5/A2
             bağlamalarıyla liner/ablat*/insulat* ve slosh beyanları
             ÇÜRÜDÜ ve kaldırıldı/daraltıldı — bkz. _thermal_protection_block
             ve _oxidizer_tank_slosh_block).

        Beyan uydurulmaz: modellenen bir şeyi "modellenmiyor" ilan etmek de
        yalandır (sıvı motorda min_throttle beyanı böyle çürümüştü). Bu
        yüzden yalnız yokluğu doğrulanan kalemler listelenir; zaten kendi
        bloğunda beyanlı olanlar (boğaz erozyonu 'rigid throat', kinetik
        verim 'not_modelled' teşhisi, çok-port eşdeğer modeli uyarısı,
        slosh bloğunun sabit-1g beyanı, astar bloğunun kuple olmayan cidar
        geçmişi beyanı) BURADA TEKRARLANMAZ — tek kaynak ilkesi.
        """
        return {
            # ÖH D18 (kalem B2-08) — BEYAN DARALDI.
            # Eski metin "the oxidizer feed system (feed lines, ...) is not
            # modelled anywhere in the hybrid solver; the only feed element
            # solved is the injector orifice plan" diyordu. ÖLÇÜLDÜ
            # (once.json, B2_08; taban 9071a64, feed_line_length_m=1,5 /
            # feed_line_inner_diameter_mm=12,0): AYNI yanıtta
            # combustion_stability.chug_loop.tau_f_s = 0,00286859921673454 s
            # ve chug_loop.feed_line = {line_length_m: 1,5,
            # line_inner_diameter_mm: 12,0, line_area_m2: 1,1309733552923255e-4,
            # mass_flow_kg_s: 1,1049407340402102, dp_injector_Pa: 2554335,85}
            # çözülüyordu. Bu bloğun KENDİ kuralı (yukarıdaki docstring)
            # bunu yasaklıyor: "modellenen bir şeyi 'modellenmiyor' ilan
            # etmek de yalandır". Doğru cümle aynı dosyada zaten vardı
            # (_feed_water_hammer_block reason metni) — beyan şimdi onunla
            # aynı sınırı çiziyor: TOPAKLANMIŞ ATALET çözülür, HAT/DONANIM
            # çözülmez.
            'feed_system': (
                'NOT_MODELLED: the oxidizer feed system as a plumbing system '
                '(valves, regulator, line routing and sizing, '
                'instrumentation) is not modelled; component and sensor '
                'counts cannot be derived without a P&ID model, so none are '
                'published — the liquid engine declares the same limit. The '
                'feed elements that ARE solved, and the only ones, are the '
                'injector orifice plan (injector_design_detail) and — when '
                'the user supplies feed_line_length_m and '
                'feed_line_inner_diameter_mm — the LUMPED INERTANCE of that '
                'one line inside the chug loop '
                '(combustion_stability.chug_loop.feed_line, feed time '
                'constant tau_f_s). Those two user numbers give no line '
                'pressure drop, no wave speed, no wall thickness and no '
                'valve closure law, which is why water hammer stays '
                'NOT_MODELLED (feed_water_hammer).'),
            'ignition_startup_transient': (
                'NOT_MODELLED: there is no igniter model and no start-up '
                'ramp; the time-marching burn and the published thrust_curve '
                'start at the design operating point at t=0. Ignition delay, '
                'flame spreading over the grain and the chamber-filling '
                'pressurisation transient are absent.'),
            'shutdown_transient': (
                'NOT_MODELLED: there is no commanded shutdown (oxidizer '
                'valve closing) model; the simulated burn ends only at fuel '
                'web or oxidizer exhaustion. The blowdown vapour tail-off in '
                'the tank_blowdown block carries its own order-of-magnitude '
                'declaration.'),
            # v2.6.27 Dalga 6 bağlaması: 'combustion_stability_acoustics'
            # beyanı KALDIRILDI — kamara akustik modları ve chug marjı artık
            # acoustic_modes bloğunda GERÇEKTEN hesaplanıyor (modülün giriş
            # sözleşmesi zaten hibrit şemasına göre yazılmıştı). Kalan sınır
            # (yanma tepki fonksiyonu / Rayleigh ölçütü modellenmiyor,
            # sönümleme yok) bloğun KENDİ not_modelled sözlüğündedir — tek
            # kaynak ilkesi; hibride özgü düşük frekanslı (sınır tabaka
            # kuplajlı) kararsızlık ise aşağıdaki ayrı kalemde beyanlıdır.
            # v2.6.27 F2b-1 bağlaması: bu beyan DARALDI. Hibride özgü alçak
            # frekanslı mod artık KONUMLANIYOR (combustion_stability.lfi:
            # Karabeyoglu ve ark. 2005 Denk. 15, kalibre sabitle) — eski
            # metnin ilk cümlesi ("modellenmiyor") o bağlamayla YALAN hâline
            # gelirdi. Geriye ÖLÇÜLMÜŞ bir yokluk kalıyor: yakıt sınır
            # tabakasının yanma TEPKİ FONKSİYONU hâlâ hiçbir yerde
            # çözülmüyor, dolayısıyla büyüme oranı ve genlik yok.
            'hybrid_boundary_layer_instability': (
                'NOT_MODELLED: the combustion RESPONSE FUNCTION of the fuel '
                'boundary layer (thermal lag of the regressing surface) is '
                'not solved anywhere in this solver, so neither a growth rate '
                'nor an oscillation amplitude is reported for the hybrid '
                'low-frequency instability. What IS modelled is where the '
                'mode sits: combustion_stability.lfi predicts its frequency '
                'from the calibrated scaling law of Karabeyoglu et al. (2005) '
                'and carries that correlation\'s own scope-limited verdict, '
                'while acoustic_modes locates the chamber acoustic modes and '
                'screens the classical feed-coupled chug ratio. The missing '
                'piece is the measured response that would turn those '
                'frequencies into a growth rate; the critical response '
                'THRESHOLD published beside them is a yardstick, not that '
                'measurement.'),
            # v2.6.27 A5 bağlaması: 'thermal_protection_liner' beyanı
            # KALDIRILDI — astar boyutlandırma ve cidar sıcaklık geçmişi
            # artık thermal_protection bloğunda GERÇEKTEN hesaplanıyor;
            # çürümüş beyan taşımak beyansızlıktan kötüdür (bu bloğun kendi
            # ilkesi). Kalan sınırlar (astar-cidar kuplajı yok, malzeme
            # seçimi tasarım kararı) bloğun KENDİ beyanlarındadır.
            # v2.6.27 Dalga 6 (A3): beyan DARALDI — cidar boyutlandırması
            # artık oxidizer_tank_pressure_vessel bloğunda GERÇEKTEN
            # hesaplanıyor. Kalan yokluk tank KÜTLESİ ve bağlantı yapısıdır.
            'oxidizer_tank_structural_mass': (
                'NOT_MODELLED: the oxidizer tank STRUCTURAL MASS and its '
                'mounting hardware (domes/skirts/brackets, weld lands, '
                'insulation and the dry-mass budget entry that would follow '
                'from them) are not computed; neither is a tank material '
                'selection - the pressure-vessel block sizes the wall for a '
                'DECLARED material. The wall sizing itself IS now modelled '
                '(oxidizer_tank_pressure_vessel, roadmap A3), slosh is '
                'modelled in oxidizer_tank_slosh (A2) and the tank contents '
                'state in tank_blowdown (A1).'),
            'throttle_response_restart': (
                'NOT_MODELLED: no throttle response model and no restart '
                'capability model; oxidizer flow-control hardware does not '
                'exist in this solver. The liquid engine declares the same '
                'items in its transient_not_modelled list.'),
        }

    def _compile_results(self, combustion_results=None, nozzle_results=None,
                        altitude_performance=None, optimum_of=None, thrust_altitude_analysis=None,
                        heat_transfer_results=None, structural_results=None,
                        nozzle_material_results=None):
        """Compile all results into a comprehensive dictionary"""

        # --- GERÇEK yanma süresi ve teslim edilen impuls (v2.6.27 B1) -------
        # ÖLÇÜLDÜ (B1 öncesi): yakıt web'i istenen süreden önce tükendiğinde
        # çözücü GERÇEK süreyi (``t_burn_effective``) hesaplıyor ama manşete
        # HİÇ bağlamıyordu. Aynı yanıtta ``burn_time = 20`` ve
        # ``total_impulse = 100000 Ns`` yayımlanırken
        # ``of_shift.regulated.burn_time_effective_s = 14,3`` ve eğrinin kendi
        # impulsu 71529 Ns yazıyordu — doğru sayı yanıtın İÇİNDEYDİ, manşete
        # bağlanmamıştı. Kullanıcı manşete bakar.
        #
        # SÖZLEŞME: ``burn_time`` ve ``total_impulse`` TESLİM EDİLEN değerdir.
        # Kırpılma yoksa (t_eff == t_b) sayılar eskisiyle BİREBİR aynıdır —
        # normal koşuda hiçbir şey değişmez. Kırpılma varsa istenen değerler
        # ``*_requested`` alanlarında ayrıca durur, yani ikisi de görünür.
        t_istenen = float(self.t_b)
        t_etkin = float(getattr(self, 't_burn_effective', self.t_b) or t_istenen)
        kirpildi = t_etkin < t_istenen * (1.0 - 1e-9)
        itki_gecmisi = list(getattr(self, '_thrust_history', []) or [])
        zaman_gecmisi = list(getattr(self, '_time_history', []) or [])
        if (len(itki_gecmisi) == len(zaman_gecmisi) and len(itki_gecmisi) > 1):
            impuls_teslim = float(_trapezoid(itki_gecmisi, zaman_gecmisi))
            impuls_temeli = ('trapz(F(t), t) of this run\'s own thrust curve '
                             'over [0, burn_time_effective_s]')
        else:
            impuls_teslim = float(self.F) * t_etkin
            impuls_temeli = ('design thrust times the effective burn time; '
                             'no time-marching thrust curve was available in '
                             'this run (track_performance is off)')
        # Oksitleyici tankı İSTENEN süreye göre yüklenir (m_ox = ṁ_ox·t_b) ve
        # bu BİLİNÇLİDİR: tank donanımdır, grain tükendi diye küçülmez. Ama
        # kırpılan yanmada bir kısmı harcanmadan kalır; iki büyüklük ayrı ayrı
        # yayımlanmazsa kütle bütçesi (yüklenen) ile performans bütçesi
        # (harcanan) sessizce karışır. Karar artık YAZILI.
        mdot_ox = float(getattr(self, 'mdot_ox', 0.0) or 0.0)
        ox_harcanan = mdot_ox * t_etkin
        ox_yuklenen = float(getattr(self, 'm_ox', mdot_ox * t_istenen))
        ox_artik = max(0.0, ox_yuklenen - ox_harcanan)

        # --- ÖH D24 / OH-D23-18 · TESLİM EDİLEN Isp ÜST SEVİYEDE YAYIMLANIR
        #
        # ÖLÇÜLDÜ (taban ``88a29d3``, ``once.json`` A_OH_D23_18; F = 1000 N,
        # t_b = 10 s, N2O/HTPB, Pc = 20 bar):
        #   O/F = 1,0 -> isp 132,485521 s ⟷ bütçeden 134,098453 s (%1,2028)
        #   O/F = 3,0 -> isp 195,301343 s ⟷ bütçeden 196,939864 s (%0,8320)
        #   O/F = 6,0 -> isp 226,077783 s ⟷ bütçeden 226,028833 s (%0,0217)
        # Yanma boyunca port büyüdükçe O/F kayıyor (1,000 -> 1,039), c* ve
        # dolayısıyla Isp değişiyor; yani ``isp`` (tasarım ANI) ile motorun
        # kendi ``total_impulse`` / ``propellant_mass_total`` bütçesinden
        # türeyen ORTALAMA Isp aynı sayı DEĞİLDİR. İkisi de doğrudur, ama
        # yanıt ikincisini HİÇ yayımlamıyordu: tüketici (yörünge çözücüsü,
        # ihracat, yapay zekâ özeti) bütçeyi ``isp`` ile kapatmaya çalışınca
        # iki tarif çelişiyor ve fail-closed kapı O/F = 1,0 kolunda
        # ``/calculate`` yörüngesini ADIYLA "hesaplanamadı" yapıyordu.
        #
        # Sayı UYDURULMAZ ve İKİNCİ KEZ TANIMLANMAZ: aşağıdaki değer, motorun
        # KENDİ yayımladığı iki alandan (``total_impulse_delivered_Ns`` ve
        # ``propellant_mass_total``) tam olarak yörünge çözücüsünün kullandığı
        # işlemle (I / (m · g0), aynı ``hrma.constants.G_0``) türetilir; yani
        # özdeşlik bit düzeyinde kapanır ve tüketicinin ayrıca hesap yapması
        # gerekmez. Tasarım noktası kümesi (thrust, mdot_total, c_star, cf,
        # isp) DOKUNULMADAN kalır — o küme de kendi içinde kapalıdır.
        # ``of_shift.regulated.isp_mass_avg_s`` AYNI büyüklüğü çözücünün
        # trapez ile entegre ettiği harcanan kütleden hesaplar; iki paydanın
        # farkı aynı ṁ'nin kapalı-biçim toplamı ile sayısal karesi
        # arasındaki farktır ve ``propellant_mass_consumed_kg`` alanında
        # görünür.
        _m_toplam = float(getattr(self, 'm_total', 0.0) or 0.0)
        isp_teslim_ort = None
        isp_tasarim_sapma_pct = None
        if _m_toplam > 0.0 and np.isfinite(impuls_teslim) and impuls_teslim > 0.0:
            isp_teslim_ort = impuls_teslim / (_m_toplam * self.g0)
            _isp_tasarim = float(getattr(self, 'Isp', float('nan')))
            if isp_teslim_ort > 0.0 and np.isfinite(_isp_tasarim):
                isp_tasarim_sapma_pct = (
                    (_isp_tasarim / isp_teslim_ort - 1.0) * 100.0)

        # Basic performance and geometry
        basic_results = {
            # --- ÖH D15 / harita H1a · BİRİM BEYANI, TAHMİN DEĞİL --------
            # ÖLÇÜLDÜ (once.json, taban d6575f1, HYBRID_BASE tek alan
            # sarsımı): hibrit motor sonucu uzunluk BİRİMİNİ beyan etmiyordu.
            # Dışa aktarım katmanı bu yüzden BÜYÜKLÜKTEN çıkarım yapıyor
            # (``motor_geometry.length_in_meters``, eşik LENGTH_SI_MAX_M =
            # 5 m): 5 m'yi aşan bir uzunluk "demek ki milimetredir" sayılıp
            # 1000'e BÖLÜNÜYORDU. Uzun grain'li ama tamamen geçerli
            # tasarımlarda kamara boyu 5 m'yi aşıyor ve çıkarım ters dönüyor:
            #   of_ratio 1,25   -> L = 6,733 m   -> okundu 6,7 mm
            #   fuel_density 460-> L = 6,897 m   -> okundu 6,9 mm
            #   regression_n 0,2775 -> L = 17,318 m -> okundu 17,3 mm
            # Sonuç zinciri: .eng RASP başlığı 142,4 x 17,3 mm zarfı yazmaya
            # çalışıyor, 27,623 kg itici o zarfa 100.082 kg/m3 bulk yoğunluk
            # ima ediyor, P9B3-11 kapısı (doğru olarak) reddediyor ve
            # /calculate'in TAMAMI HTTP 400 dönüyordu; aynı yanlış okuma
            # CAD'i de "chamber length 0,0173 m band [0,02; 5] dışında"
            # diye düşürüyordu. Motorun kendi sayısı DOĞRUYDU (17,318 m;
            # L/D = 130 zaten warn.hybrid ile bildiriliyor) — kaybolan tek
            # şey BİRİMDİ.
            # Çözüm çıkarımı iyileştirmek değil, ÜRETİCİNİN BEYAN ETMESİ:
            # aşağıdaki tüm uzunluk alanları (chamber_length, grain_length,
            # chamber_diameter, throat_diameter, exit_diameter,
            # port_diameter_initial/final) METREdir. Beyan varken
            # ``motor_geometry.resolve_length_m`` 'declared:m' yolunu seçer
            # ve büyüklük eşiğine hiç bakmaz.
            'length_units': 'm',
            # Performance
            'thrust': self.F,
            # --- D15/P1B2-03 · 'TESLİM EDİLEN' ALAN TESLİM EDİLENİ TAŞIR --
            # ÖLÇÜLDÜ (a3/once.json, B2_03): eski satır
            # ``impuls_teslim if kirpildi else self.I_total`` idi, yani
            # KIRPILMAYAN koşuda alan İSTENEN impulsü taşıyordu; hemen
            # altındaki künye ise birebir "total_impulse is the DELIVERED
            # impulse" diyordu. Ölçüm (F=3000 N / t=20 s / D0=50 mm):
            # total_impulse = 60000,0000 Ns iken eğrinin kendi impulsü
            # total_impulse_delivered_Ns = 59999,9998 Ns. İki sayı aynı
            # yanıtta duruyordu ve MANŞETE (design_summary.performance
            # .total_impulse_Ns -> arayüz tablosu ve yapay zekâ özeti)
            # yanlış olan gidiyordu. Bugünkü sapma küçüktür (bu taban
            # koşusunda %3,6e-07..%4,9e-06); kusur BÜYÜKLÜKTE değil
            # SÖZLEŞMEDE: alan adı ve künyesi teslim edileni vaat ediyor.
            # İstenen değer kaybolmaz, adıyla yanında durur.
            'total_impulse': impuls_teslim,
            'total_impulse_requested_Ns': float(self.I_total),
            'total_impulse_delivered_Ns': impuls_teslim,
            'total_impulse_basis': (
                'total_impulse is the DELIVERED impulse of this run in EVERY '
                'case: it is always the same number as '
                'total_impulse_delivered_Ns, never the requested value. '
                'total_impulse_requested_Ns carries the design intent '
                '(thrust x requested burn time) and the two differ whenever '
                'the thrust curve is not perfectly flat - most visibly when '
                'the fuel web is exhausted early and burn_time_clipped is '
                'true. Delivered basis: ' + impuls_temeli + '.'),
            'burn_time_requested_s': t_istenen,
            'burn_time_effective_s': t_etkin,
            'burn_time_clipped': bool(kirpildi),
            'burn_time_basis': (
                'burn_time is the burn the motor actually sustains. It equals '
                'burn_time_requested_s unless the fuel web is exhausted '
                'first, in which case burn_time_clipped is true, the '
                'warn.hybrid.web_exhausted_early warning is raised and the '
                'requested value stays visible in burn_time_requested_s.'),
            'oxidizer_mass_consumed_kg': ox_harcanan,
            'oxidizer_mass_residual_kg': ox_artik,
            'oxidizer_mass_basis': (
                'oxidizer_mass is the LOADED mass: the tank is sized for the '
                'REQUESTED burn time (m_ox = mdot_ox x burn_time_requested_s) '
                'because the tank is hardware and does not shrink when the '
                'grain runs out early. oxidizer_mass_consumed_kg is what the '
                'burn actually uses and oxidizer_mass_residual_kg is the '
                'unburnt remainder that flies as dead weight. The mass budget '
                'must use the loaded value, the performance budget the '
                'consumed one.'),
            'impulse_input_resolution': getattr(
                self, 'impulse_input_resolution', None),
            'nozzle_expansion_screen': getattr(
                self, 'nozzle_expansion_screen', None),
            'isp': self.Isp,
            # ÖH D24 / OH-D23-18 — bkz. yukarıdaki türetim notu. Çözülemezse
            # (kütle ya da impuls yoksa) ALAN None kalır; sayı uydurulmaz.
            'isp_delivered_avg_s': isp_teslim_ort,
            'isp_design_point_delta_pct': isp_tasarim_sapma_pct,
            'isp_delivered_avg_basis': (
                'DELIVERED burn-averaged specific impulse of THIS run: '
                'total_impulse_delivered_Ns / (propellant_mass_total * g0) '
                'with the BIPM standard gravity. The identity '
                'I = Isp * m * g0 closes exactly against the two fields '
                'named here, so a consumer never has to choose between two '
                'descriptions of the same burn. It is NOT the same quantity '
                'as the headline isp: that one is the design-point instant '
                '(CF * c_star / g0) and belongs to the closed design set '
                '(thrust, mdot_total, c_star, cf, isp). The two differ '
                'because the O/F of a hybrid drifts as the port regresses; '
                'isp_design_point_delta_pct reports that cost as a '
                'percentage, and of_shift.regulated carries the whole '
                'history. of_shift.regulated.isp_mass_avg_s is this same '
                'burn-averaged quantity taken over the solver trapezoid mass '
                '(propellant_mass_consumed_kg) instead of the published '
                'propellant_mass_total.'),
            'c_star': self.C_star,
            'cf': self.CF,
            'mdot_total': self.mdot_total,
            'mdot_ox': self.mdot_ox,
            'mdot_f': self.mdot_f,
            
            # Geometry
            'throat_area': self.At,
            'throat_diameter': self.d_t,
            'exit_area': self.Ae,
            'exit_diameter': self.d_e,
            'expansion_ratio': self.epsilon,
            # FAZ 5 / H4-9 — "chamber_volume" adı depoda ÜÇ farklı büyüklüğü
            # ve İKİ farklı birimi taşıyor. Ölçüm (aynı hibrit motor):
            #   motor.chamber_volume         0,00073161 m³ =  731,6 cm³
            #       -> L*_istenen x A_t, yani TASARIM HEDEFİ
            #   motor.chamber_volume_actual  0,00322147 m³ = 3221,5 cm³
            #       -> portun sardığı GERÇEK serbest hacim (4,4 kat büyük)
            #   cad_design...geometry_summary.chamber_volume  8011,58 cm³
            #       -> pi/4·D²·L BRÜT silindir (grain'i hiç saymıyor)
            # Adın kendisi hangi büyüklük olduğunu söylemediği için tüketiciler
            # (panel, CAD, rapor) farklı sayıları aynı etiketle gösteriyordu.
            # Motor tarafı artık birimini ve TANIMINI açıkça yayımlar; eski
            # anahtarlar geriye uyum için aynen korunur.
            'chamber_volume': self.V_c,
            'chamber_volume_m3': self.V_c,
            'chamber_volume_basis': (
                'DESIGN TARGET chamber volume in m^3: requested L* times '
                'throat area (L* x A_t). NOT the free volume of the built '
                'chamber and NOT the gross cylinder swept by the case.'),
            'chamber_diameter': self.D_ch,
            'chamber_length': self.L,
            # L* modeli (v2.5.2): kamara boyu = grain + ön-yanma + art-yanma.
            'pre_chamber_length': getattr(self, 'L_pre_chamber', 0.0),
            'post_chamber_length': getattr(self, 'L_post_chamber', 0.0),
            # D15/P1B1-12 — aynı lülenin iki C_F'i: ayrışım kaydı.
            'thrust_coefficient_cross_check': getattr(
                self, 'thrust_coefficient_cross_check', None),
            'l_star': self.L_star,
            'l_star_achieved': getattr(self, 'L_star_achieved', self.L_star),
            # D15/P1B1-10: port sayısı BU SÜRÜME KADAR yayımlanmıyordu
            # (yalnız warn.hybrid.multi_port_equivalent_model parametresinde
            # görünüyordu). Kullanılan N ekranda görünmediği için kapıdan
            # geçen değerin gerçekten kullanılan değer olduğu doğrulanamıyordu.
            'port_count': int(self.port_count),
            'port_count_basis': (
                'number of equivalent circular combustion ports actually used '
                'by the grain model of this run. It is the value the port '
                'gate accepted: zero, negative and fractional inputs are '
                'rejected by name rather than silently rounded, and an '
                'omitted input means one port.'),
            'l_star_note': getattr(self, 'l_star_note', ''),
            # ÖH D23 / OH-D22-01: istenen L*'ın FİİLEN uygulanıp
            # uygulanmadığı MAKİNECE okunur olmalı; uç kapısı bu alanı
            # okur ve bir literatür bandı yerine modelin kendi tavanına
            # dayanır.
            'l_star_clamped_high': bool(getattr(self, 'l_star_clamped_high',
                                                False)),
            'l_star_ceiling_basis': (
                'the post-combustion chamber length is clamped to '
                f'[{POST_CHAMBER_D_FACTOR_MIN:g}, {POST_CHAMBER_D_FACTOR_MAX:g}]'
                ' x chamber diameter, so the achievable L* of a hybrid is set '
                'by the grain port volume and that clamp - NOT by the liquid '
                'engine literature band. l_star_achieved is the value this '
                'run actually built.'),
            # v2.6.26: kamara boyunun kullanıcı ezmesinden mi L*'dan mı
            # geldiği görünür olmalı (ezme kabul edilmediyse kullanıcı bunu
            # uyarıdan ve bu alandan anlar).
            'chamber_length_source': getattr(self, 'chamber_length_source',
                                             'l_star_derived'),
            'chamber_length_auto': getattr(self, 'chamber_length_auto',
                                           self.L),
            'design_safety_factor_input': self.design_safety_factor,
            'nozzle_material': self.nozzle_material,
            'chamber_volume_actual': getattr(self, 'V_c_actual', self.V_c),
            'chamber_volume_actual_m3': getattr(self, 'V_c_actual', self.V_c),
            'chamber_volume_actual_basis': (
                'ACTUAL free volume in m^3 enclosed by the fuel port plus the '
                'pre/post-combustion chambers at the design instant; this is '
                'what L*_achieved is computed from.'),
            
            # Fuel grain
            'port_diameter_initial': self.D_port_initial,
            'port_diameter_final': self.D_port_final,
            'regression_rate': self.r_dot,
            'regression_rate_avg': self.r_dot_avg,
            'g_ox_initial': self.G_ox_initial,
            'g_ox_final': self.G_ox_final,
            
            # Propellant
            'propellant_mass_total': self.m_total,
            'oxidizer_mass': self.m_ox,
            'fuel_mass': self.m_f,                      # YANAN yakıt (performans bütçesi)
            'fuel_mass_loaded': getattr(self, 'm_f_loaded', self.m_f),  # yüklenen (kütle bütçesi)
            'fuel_sliver_fraction': getattr(self, 'fuel_sliver_fraction', 0.0),
            
            # Operating conditions
            'chamber_pressure': self.P_c,
            'chamber_temperature': self.T_c,
            # TESLİM EDİLEN süre (bkz. burn_time_basis). Kırpılma yoksa
            # self.t_b ile birebir aynıdır.
            'burn_time': t_etkin if kirpildi else self.t_b,
            'of_ratio': self.OF,

            # O/F kayması (denetim bulgusu #6): port büyüdükçe mdot_f değişir;
            # başlangıç O/F tasarım değeridir, yanma sonu O/F time-marching
            # içindeki anlık mdot_f'den gelir.
            'of_ratio_initial': self.OF,
            'of_ratio_final': self.OF_final,
            'fuel_mass_flow_final': self.mdot_f_final,
            'grain_length': self.L_grain,
            'g_ox_design': self.G_ox_design,

            # Marxman toplam akı (denetim bulgusu #1): regresyon G_total ile
            # hesaplanır; G_ox-only'ye göre düşük-O/F rejiminde daha yüksek
            # (konservatif) r verir.
            'regression_flux_mode': self.flux_mode,
            'g_total_initial': getattr(self, 'G_total_initial', self.G_ox_initial),
            'g_total_final': getattr(self, 'G_total_final', self.G_ox_final),
        }

        # gamma + molecular_weight ÜST SEVİYEDE (Dalga 0, 2026-07-14):
        # Bartz ve lüle tüketicileri artık compositions->chamber'a inmek
        # ya da varsayılana (gamma=1.20, MW=24) düşmek zorunda kalmaz.
        # Öncelik: yanma dengesinin chamber kaydı; yoksa sınıf değerleri
        # (self.gamma, MW = R_evrensel / self.R).
        gamma_top = self.gamma
        mw_top = None
        if getattr(self, 'R', None):
            mw_top = self.combustion_analyzer.R_universal / self.R  # g/mol
        if combustion_results:
            chamber_comp = combustion_results.get(
                'compositions', {}).get('chamber', {})
            gamma_top = chamber_comp.get('gamma', gamma_top)
            mw_top = chamber_comp.get('molecular_weight', mw_top)
        basic_results['gamma'] = gamma_top
        basic_results['molecular_weight'] = mw_top
        # D15/P1B1-07: ÖZGÜL GAZ SABİTİ artık üst seviyede de yayımlanır.
        # ``gamma`` ve ``molecular_weight`` yankılanıyordu, R yankılanmıyordu;
        # oysa R kurucuda bir GİRDİ adı taşıyor (``gas_constant``) ve çözücü
        # tarafından koşulsuz eziliyor. Yankı olmadan uç katmanı "gönderilen
        # ⟷ kullanılan" karşılaştırmasını yapamıyor, dolayısıyla kullanıcıya
        # "bu alan okunmadı" diyemiyordu. Sayı uydurulmuyor: R = R_evrensel /
        # MW, MW yukarıdaki denge kaydının kendi molekül ağırlığıdır.
        basic_results['gas_constant'] = (
            self.combustion_analyzer.R_universal / mw_top
            if mw_top else getattr(self, 'R', None))

        # D15/P1B1-06 — MAKULLÜK KAPILARININ HÜKÜM DEFTERİ yanıta girer.
        # Bkz. __init__ içindeki gerekçe: bu bölgedeki 8 uyarı noktasının
        # 6'sı yalnız ``warnings.warn`` ile sunucu konsoluna gidiyordu.
        # Kayıtlar çevirisizdir (sayı + bant + hüküm) — i18n sözlüğü bu iş
        # kaleminde yazılamaz kapsamdadır ve ham anahtar göstermek
        # çeviriden de kötüdür.
        basic_results['design_gate_checks'] = list(
            getattr(self, 'design_gate_checks', []) or [])

        # --- UQ modu izleri (v2.5.0): atlanan danışma blokları dürüstçe not
        # edilir; ana çıktılar uq_mode'dan ETKİLENMEZ (test kilidi altında).
        if self.uq_mode:
            basic_results['uq_mode'] = True
            if optimum_of is None:
                basic_results['optimum_of_note'] = (
                    'optimum O/F search skipped in uq_mode (advisory output); '
                    'inject precomputed_optimum_of from the nominal run to '
                    'populate optimum_analysis/optimum_of_ratio.'
                )
        # c* verimi raporu: teslim edilen c* basic_results['c_star'] içindedir;
        # teorik değer ayrıca verilir ki verim varsayımı şeffaf kalsın.
        if self.eta_c_star is not None:
            basic_results['eta_c_star'] = self.eta_c_star
            basic_results['c_star_theoretical'] = getattr(
                self, 'C_star_theoretical', self.C_star)

        # --- Yayın seyreltmesi (B2-4) --------------------------------------
        # Ölçülen kusur: port 5 mm + t_b 50 s -> thrust_curve 17 317 nokta /
        # 1,29 MB + of_shift_performance 17 317 nokta / 1,28 MB (yanıtın
        # %94'ü). Çözücü adımı DEĞİŞMEZ; yalnız yayımlanan diziler inceltilir
        # ve TEK indeks kümesi iki seriye birden uygulanır — thrust_curve ile
        # of_shift_performance aynı zaman tabanında kalır (seri tutarsızlığı
        # kusuru 8. partide kapatılmıştı, yeniden açılamaz). Zorunlu taşınan
        # örnekler: itki tepesi + tepe basınç (ortak modül) ve O/F ile Isp'nin
        # uç değerleri (aşağıda) — kaymanın zarfı grafikte kaybolmaz.
        # Ortalamalar ve türetilmiş sayılar TAM çözünürlükten hesaplanır.
        _yayin_idx = None
        _yayin_n = 0
        _cozucu_adim_s = None
        if getattr(self, '_thrust_history', None):
            _yayin_n = len(self._thrust_history)
            _zaman_dizisi = np.asarray(self._time_history, dtype=float)
            if _zaman_dizisi.size > 1:
                # Adım beyanı seriden ÖLÇÜLÜR (ayrı bir sabitten kopyalanmaz).
                _cozucu_adim_s = float(np.median(np.diff(_zaman_dizisi)))
            _zorunlu = []
            if self.track_performance and getattr(self, '_of_history', None):
                for _dizi in (self._of_history, self._isp_history):
                    _d = np.asarray(_dizi, dtype=float)
                    if _d.size == _yayin_n and bool(np.isfinite(_d).any()):
                        _m = np.isfinite(_d)
                        _zorunlu.append(int(np.nanargmax(
                            np.where(_m, _d, -np.inf))))
                        _zorunlu.append(int(np.nanargmin(
                            np.where(_m, _d, np.inf))))
            _yayin_idx = _ortak_seyreltme_indeksleri(
                self._thrust_history, pressure=self._pc_history,
                keep=_zorunlu)

        def _seyrelt(dizi):
            # Yalnız itki dizisiyle AYNI uzunluktaki seriler seyreltilir;
            # farklı uzunluk = farklı taban, dokunulmaz (hizalama uydurulmaz).
            if _yayin_idx is None or len(dizi) != _yayin_n:
                return [float(x) for x in dizi]
            return [float(dizi[i]) for i in _yayin_idx]

        # O/F kaymasının performansa etkisi (denetim bulgusu #2): time-marching
        # boyunca anlık O/F'den hesaplanan c*/Isp dizileri ve zaman-ortalamaları.
        if self.track_performance and getattr(self, '_cstar_history', None):
            cstar_hist = self._cstar_history
            isp_hist = self._isp_history
            basic_results['of_shift_performance'] = {
                'time': _seyrelt(self._time_history),
                'of_ratio': _seyrelt(self._of_history),
                'c_star': _seyrelt(cstar_hist),
                'isp': _seyrelt(isp_hist),
                # Ortalamalar TAM çözünürlüklü geçmişten — seyreltmeden ÖNCE.
                'c_star_time_avg': float(np.mean(cstar_hist)) if cstar_hist else self.C_star,
                'isp_time_avg': float(np.mean(isp_hist)) if isp_hist else self.Isp,
                'c_star_design_of': self.C_star,
                'isp_design_of': self.Isp,
                'sampling': _ornekleme_blogu(
                    len(_seyrelt(self._time_history)), _yayin_n or
                    len(self._time_history), _cozucu_adim_s,
                    'the O/F-ratio extremes and the specific-impulse extremes',
                    'time-averaged c*, time-averaged Isp, O/F shift statistics'),
            }

        # İtki-zaman eğrisi (v2.6.26). Katı motorla AYNI sözleşme
        # ({time, thrust, pressure, mass_flow}) kullanılır ki üç sayfa aynı
        # çizim kodunu paylaşabilsin. Değerlerin tamamı zaman-adımlı
        # çözücünün kendi durumundan gelir; şekil verilmez.
        if getattr(self, '_thrust_history', None):
            basic_results['thrust_curve'] = {
                'time': _seyrelt(self._time_history),
                'thrust': _seyrelt(self._thrust_history),
                'pressure': _seyrelt(self._pc_history),
                'mass_flow': _seyrelt(self._mdot_total_history),
                'basis': ('time-marching solution: F = mdot_total(t)*Isp(t)*g0, '
                          'Pc = mdot_total(t)*c_star(t)/(Cd*At) with the same '
                          'throat discharge coefficient the throat was sized '
                          'with (single C_D contract: the mass flow carries '
                          'Cd, the throat area is geometric); oxidiser flow '
                          'is constant, fuel flow follows the regressing '
                          'port'),
                'sampling': _ornekleme_blogu(
                    len(_seyrelt(self._time_history)), _yayin_n,
                    _cozucu_adim_s,
                    'the O/F-ratio extremes and the specific-impulse extremes',
                    'total impulse, burn time, average thrust, O/F shift '
                    'statistics, warnings'),
            }

        # Port çapı zaman serisi (3D yanma animasyonu için, metre + saniye).
        # Yanıt boyutunu sınırlamak için ~200 noktaya seyreltilir.
        if getattr(self, '_port_diameter_history', None):
            pt = self._port_time_history
            pd = self._port_diameter_history
            stride = max(1, len(pt) // 200)
            idx = list(range(0, len(pt), stride))
            if idx[-1] != len(pt) - 1:
                idx.append(len(pt) - 1)
            basic_results['port_history'] = {
                'time': [float(pt[i]) for i in idx],
                'port_diameter': [float(pd[i]) for i in idx],
            }

        # --- 1. Nozzle Angles ---
        nozzle_type = self.nozzle_type
        basic_results['nozzle_angles'] = {
            'convergent_half_angle_deg': 30.0 if nozzle_type == 'conical' else 45.0,
            'divergent_half_angle_deg': 15.0 if nozzle_type == 'conical' else 11.0,
            'nozzle_type': nozzle_type,
            'divergence_efficiency': self.lambda_eff,
            # D15/P1B1-02 — λ'nın C_F'e UYGULANIP UYGULANMADIĞI. Kullanıcı
            # kendi itki katsayısını verirse motor λ'yı hesaba KATMAZ (C_F
            # olduğu gibi kullanılır); λ yine yayımlanır çünkü çizilen lülenin
            # geometrik verimidir, ama iki alan aynı sayıya ait değildir.
            'thrust_coefficient_source': self.CF_source,
            'divergence_efficiency_applied_to_cf': (
                self.CF_source == 'computed_isentropic'),
            # ÖH D21 / P15B1-04 — λ'NIN NEREDEN GELDİĞİ. 'contour_geometry' =
            # lüle panelinin okuduğu AYNI kaynak (bu konturun kendi açısı;
            # bell/parabolikte Rao %80 tablosuyla genişleme oranına bağlı).
            # 'catalogue_constant_expansion_ratio_unresolved' = genişleme
            # oranı hiç çözülemediği için geometri sorulamadı ve katalog
            # sabitine düşüldü; bu düşüş SESSİZ DEĞİLDİR, alan onu söyler.
            'divergence_efficiency_basis': getattr(
                self, 'lambda_basis', None),
        }

        # --- 2. Grain Design ---
        # Grain boyu yakıt üretim kapanışından gelir (denetim bulgusu #6),
        # kamara boyundan DEĞİL: mdot_f = rho_f·π·D_port·L_grain·r_dot
        fuel_length = self.L_grain
        chamber_diameter = self.D_ch
        basic_results['grain_design'] = {
            'grain_type': 'cylindrical_bore',
            'web_thickness_mm': (self.D_port_final - self.D_port_initial) / 2 * 1000,
            'port_diameter_initial_mm': self.D_port_initial * 1000,
            'port_diameter_final_mm': self.D_port_final * 1000,
            'grain_length_mm': fuel_length * 1000,
            'grain_outer_diameter_mm': chamber_diameter * 1000,
            # ÖH D37 A2 hibrit · K-8 (CAD B1 H07) — SEGMENT SAYISI UYDURULMAZ.
            # Eskiden 'number_of_segments': max(1, int(L/0,3 m)) yayımlanıyordu:
            # kaynaksız bir 0,3 m kuralı; fiziğe (gerileme, kalış süresi, Kn)
            # hiç girmiyor, ama rapor/CAD/STEP onu "n parçalı tane" diye
            # okuyordu. ÖLÇÜLDÜ (docs/scofield/raw/OH/A2/hibrit/a1/once/
            # ozet.json K3: L = 1520 mm → 5 "segment"; K1 Ornek-H1 511 mm → 1).
            # Hibrit çözücü tek parça, tek portlu tane modeller; segmentleme
            # MODELLENMEZ → alan yayımlanmaz, yokluğu adıyla beyan edilir.
            # Tüketiciler fail-closed: step_export._grain_segment_plan → None
            # (tek parça + künye, artık doğru), app.js reportNum → '—',
            # cad_visualization → NOT_AVAILABLE_SPEC, visualization → 1.
            'segmentation': 'not_modelled',
            'segmentation_basis': (
                'the hybrid solver models one continuous single-port grain; '
                'it does not size grain segments, so no number_of_segments / '
                'segment_length_mm is published. The former segment count '
                'max(1, int(L/0.3 m)) had no source and entered no physics.'),
            'inhibitor': 'outer_surface',
            'L_over_D': fuel_length / chamber_diameter if chamber_diameter > 0 else 0,
        }

        # --- 3. Injector Design ---
        # Gerçek tasarım: injector_design modülü (docs/10_Enjektor_ARGE.md).
        # N2O'da Dyer NHNE iki-faz debisi, Cd gerekçesi, delik planı, SMD,
        # chug/flip kontrolleri. Modül hata verirse eski basit Bernoulli
        # hesabına düşülür (hesap zinciri kırılmaz).
        delta_P_inj = self._inj_delta_P  # bar (stored from _design_fuel_grain)
        rho_ox = self._inj_rho_ox        # kg/m³
        try:
            from hrma.engines.injector_design import design_injector
            inj_spec = {
                'motor_type': 'hybrid',
                # v2.5.2: kullanıcının seçtiği enjektör tipi (eskiden sabit
                # 'showerhead' idi, seçim sonucu hiç etkilemiyordu)
                # v2.6.26: ARAYÜZ SÖZCÜĞÜ İLE MODÜL SÖZCÜĞÜ AYRIYDI. Arayüz
                # 'impingement' / 'coaxial' gönderiyor, bu modül
                # 'like_impinging' / 'gas_gas_coaxial' bekliyor. Eşleme
                # olmadığı için beş enjektör tipinin İKİSİNDE çağrı
                # ValueError atıyor ve aşağıdaki yedek yola düşülüyordu —
                # yedek yol da 12 delikli showerhead SABİTİ üretiyordu.
                # Yani pintle-dışı iki tipte kullanıcı, seçtiği tipin
                # etiketini taşıyan uydurma bir showerhead sonucu görüyordu.
                'injector_type': INJECTOR_TYPE_TO_MODULE.get(
                    self.injector_type, self.injector_type),
                'mdot_ox': self.mdot_ox,
                'rho_ox': rho_ox,
                'Pc_bar': self.P_c,
                # ÖH D26 / P14M2-05: yedek dal da ÇIPLAK 0,20 taşıyordu —
                # aynı sayının ikinci kopyası. Tek kaynaktan okunur.
                'dp_ratio_ox': (delta_P_inj / self.P_c if self.P_c > 0
                                else CHUG_DP_RATIO_RECOMMENDED),
            }
            # v2.6.26 — DEŞARJ KATSAYISI ARTIK GEOMETRİDEN GELİYOR.
            # Devre çözücüsü Cd'yi discharge_coefficient(giriş, L/D) ile
            # ZATEN seçiyordu, ama hibrit sözlüğü ne 'inlet_ox' ne
            # 'orifice_length_m' anahtarını taşıdığı için her koşuda
            # giriş='sharp', L/D=4,0 varsayımına düşülüyor ve Cd 0,78'de
            # SABİT kalıyordu (17/17 koşu). Cd doğrudan delik alanına girer
            # (A = ṁ/(Cd·√(2ρΔP))): tablonun 0,63-0,92 bandı uçtan uca
            # ~%46 alan farkı demektir. Plaka kalınlığı arayüzde ZATEN var.
            if self.injector_plate_thickness:
                inj_spec['orifice_length_m'] = self.injector_plate_thickness
            if self.injector_orifice_inlet:
                inj_spec['inlet_ox'] = self.injector_orifice_inlet
            # v2.6.27 parti 31 — KULLANICININ Cd'si devre çözücüsüne GİRDİ.
            # Verilmezse anahtar hiç konmaz (çözücü tabloyu kullanır ve
            # gerekçesini yazar); verilirse ṁ = Cd·A·√(2ρΔP) cebri Cd'yi
            # doğrudan alır, sonradan ölçekleme YAPILMAZ. Plaka kalınlığı da
            # verilmişse L/D yinelemesi devre dışı kalır: kullanıcının ölçtüğü
            # Cd, tablodan türetilen Cd'yi EZER (ölçüm > korelasyon) ve bu
            # 'user_cd' beyanıyla görünür olur.
            if self.injector_cd_input is not None:
                inj_spec['cd'] = self.injector_cd_input
            ox_name = (getattr(self, 'oxidizer_type', None) or 'n2o').lower()
            if ox_name == 'n2o':
                # Tank sıcaklığı v2.5.2'de motor girdisi; verilmezse doymuş
                # depolama varsayımı — tank_blowdown bloğuyla AYNI adlı
                # sabitten (v2.6.27: 293,15 literali merkezileşti; iki modül
                # farklı varsayılan sıcaklık kullanamaz).
                inj_spec['fluid_ox'] = 'n2o'
                inj_spec['T_ox_K'] = (self.tank_temperature
                                      if self.tank_temperature is not None
                                      else TANK_TEMPERATURE_DEFAULT_K)
            # Oda gazı yoğunluğu (SMD için): T_c ve MW = R_evrensel/R_spesifik
            if getattr(self, 'T_c', None) and getattr(self, 'R', None):
                inj_spec['T_c_K'] = self.T_c
                inj_spec['mw_gas'] = R_UNIVERSAL / self.R
            detail = design_injector(inj_spec)
            if detail.get('status') != 'success':
                raise ValueError(detail.get('error', 'enjektör tasarım hatası'))
            oxc = detail['ox_circuit']
            basic_results['injector_design'] = {
                # Kullanıcının SEÇTİĞİ ad birincil; modülün iç sözcüğü ayrı
                # alanda verilir (eşleme yapıldığında kullanıcı 'impingement'
                # seçip sonuçta 'like_impinging' görmemeli).
                'injector_type': self.injector_type,
                'model_injector_type': detail['injector_type'],
                'oxidizer_flow_rate_kg_s': self.mdot_ox,
                'injection_velocity_m_s': oxc['velocity_m_s'],
                'number_of_orifices': oxc['n_orifices'],
                'orifice_diameter_mm': oxc['orifice_d_mm'],
                'injection_pressure_drop_bar': oxc['delta_p_bar'],
                'manifold_diameter_mm': oxc['manifold']['d_mm'],
                'discharge_coefficient': oxc['cd'],
                # v2.6.26 — ÖZET BLOK SAYIYI GEREKÇESİZ KOPYALIYORDU.
                # Aynı yanıtta injector_design_detail.ox_circuit.cd_basis
                # Cd'nin nereden geldiğini (giriş geometrisi + L/D tablosu)
                # zaten yazıyor; özet blok yalnız sayıyı taşıyordu ve orada
                # 0,78 gerekçesiz bir sabit gibi duruyordu. Metin YENİDEN
                # YAZILMAZ, TEK kaynaktan (devre çözücüsü) okunur — iki yerde
                # iki farklı gerekçe olamaz.
                'discharge_coefficient_basis': oxc.get('cd_basis'),
                # v2.6.27 parti 31 — AD ÇAKIŞMASININ kapanış beyanı.
                # Kullanıcı Cd göndermediyse None (uydurma beyan yok);
                # gönderdiyse {'value','applied','basis'} ile UYGULANDI mı
                # sorusunu adıyla yanıtlar. Sözlük devre çözücüsünden
                # OLDUĞU GİBİ taşınır — motor tarafında ikinci bir gerekçe
                # metni YAZILMAZ (tek kaynak).
                'discharge_coefficient_input': detail.get('user_cd'),
                'total_injector_area_mm2': oxc['total_area_mm2'],
                # ÖH D37 A2 hibrit · YB-04 (OH-ON-01 §6) — BESLEME BASINCININ
                # KAYNAĞI BEYANLI. ÖLÇÜLDÜ (docs/scofield/raw/OH/A2/hibrit/a1/
                # once/ozet.json K2/K4): N₂O devresi P₁ = P_sat(T_tank) alır;
                # isteğin ``tank_pressure`` alanı bu devreye HİÇ girmez
                # (50 → 80 bar: enjektör yaprakları bit-aynı, yalnız yankı
                # alanları değişir). ``p_feed_bar`` verilseydi Ornek-H1'de
                # ΔP 30,543 → 30,000 bar, d 2,1115 → 2,1201 mm olurdu —
                # yayımlanan sayı değişir → Berke kararı (Sunum 2). Bugün
                # sayı DEĞİŞMEZ; P₁ = Pc + ΔP özdeşliğiyle okunur ve kaynağı
                # adıyla söylenir (sessiz yok sayma biter).
                'feed_pressure_bar': (float(self.P_c)
                                      + float(oxc['delta_p_bar'])),
                'feed_pressure_source': (
                    FEED_PRESSURE_SOURCE_N2O_SAT
                    if inj_spec.get('fluid_ox') == 'n2o'
                    else 'chamber_pressure_plus_design_pressure_drop'),
                'feed_pressure_basis': (
                    'P_1 = P_c + delta_p of the injector circuit solution. '
                    + ('For self-pressurised N2O the circuit takes P_1 = '
                       'P_sat(T_tank) from the saturation table; '
                       if inj_spec.get('fluid_ox') == 'n2o' else
                       'The circuit takes P_1 = P_c*(1 + dp_ratio) from the '
                       'design pressure-drop ratio; ')
                    + 'the request\'s tank_pressure field is NOT an input '
                    'of this circuit (measured: changing it leaves the '
                    'injector solution bit-identical). Feeding an externally '
                    'supplied tank pressure into the circuit would change '
                    'the published pressure drop and orifice plan, so it is '
                    'not done silently here.'),
            }
            basic_results['injector_design_detail'] = detail
        except Exception as _inj_err:
            # v2.6.26 — UYDURMA YEDEK KALDIRILDI.
            #
            # Eski yedek yol, devre modeli hata verdiğinde şu SABİTLERİ
            # üretiyordu: n_orifices = 12 ("typical showerhead pattern"),
            # Cd = 0.65 ve manifold çapı = 2 x başlangıç port çapı. Bu
            # sayıların hiçbiri kullanıcının seçtiği enjektör tipinden
            # gelmiyordu; yine de sonuç ``injector_type`` alanında
            # kullanıcının seçimiyle ETİKETLENİYORDU. Yani pintle/swirl
            # dışındaki iki tipte kullanıcı, "coaxial" yazan bir 12 delikli
            # showerhead görüyordu. Uyarı yalnız ``warnings.warn`` ile
            # sunucu günlüğüne gidiyordu; ekranda hiçbir iz yoktu.
            #
            # Yeni sözleşme: delik planı üretilemiyorsa ÜRETİLMEZ. Blok
            # 'status: not_analyzed' ile ve nedeniyle döner, uyarı
            # kullanıcıya ULAŞIR. Geometri uydurmak, geometri vermemekten
            # daha kötüdür — kullanıcı bu sayıları imalata götürüyor.
            self._fallback_used.append('injector_design_detail')
            self.design_warnings.append(_w(
                'warn.hybrid.injector_detail_unavailable', 'warning',
                injector_type=self.injector_type,
                reason=str(_inj_err)[:200]))
            basic_results['injector_design'] = {
                'status': 'not_analyzed',
                'injector_type': self.injector_type,
                'reason': (f'the detailed injector circuit model could not '
                           f'size this injector: {_inj_err}'),
                # Cozucunun GERCEKTEN hesapladiklari korunur; uydurulan
                # (delik sayisi, delik capi, manifold capi, Cd) verilmez.
                'oxidizer_flow_rate_kg_s': self.mdot_ox,
                'injection_pressure_drop_bar': delta_P_inj,
            }

        # --- 4. Design Summary ---
        # Total motor length estimate: chamber + convergent + divergent sections
        conv_half_angle = basic_results['nozzle_angles']['convergent_half_angle_deg']
        div_half_angle = basic_results['nozzle_angles']['divergent_half_angle_deg']
        L_conv = (chamber_diameter / 2 - self.d_t / 2) / np.tan(np.radians(conv_half_angle))
        # D15/P1B2-02 — YAYIMLANAN IRAKSAK BOY, ÇİZİLEN KONTURUN BOYUDUR.
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/hibrit/a1/once.json; 3 kN,
        # Pc = 30 bar, ε = 8, yalnız nozzle_type değişiyor):
        #   conical   102,5423 ⟷ kontur 102,5423 mm   (%0,00)
        #   bell      141,1969 ⟷ kontur  84,3150 mm   (+%67,46)
        #   parabolic 141,9794 ⟷ kontur  87,5476 mm   (+%62,17)
        # Kök: L_div burada SABİT yarı açıdan türetiliyordu ve o açı
        # bell/parabolik için 11,0° yazılıydı (nozzle_angles satırı), oysa
        # konturun kendi kaydı throat_angle = 23,5° / exit_angle = 14,0°.
        # Bell konturunda "yarı açı" diye tek bir sayı YOKTUR; açıdan boy
        # türetmek tanım gereği yanlış. Sonuç: design_summary 141,20 mm
        # yayımlarken STL/STEP/DXF, 2B kesit, 3B sahne ve Bartz istasyonları
        # 84,32 mm'lik konturu kullanıyordu — atölyeye giden boy ile ihraç
        # edilen katı 56,88 mm ayrışıyordu.
        # Artık ÇÖZÜCÜNÜN konturu tek kaynaktır; kontur yoksa koni bağıntısı
        # kullanılır ve kaynağı ADIYLA beyan edilir (uydurma yedek yok).
        L_div_kontur_mm = None
        if isinstance(nozzle_results, dict):
            _kont = (nozzle_results.get('contour') or {})
            _div = (_kont.get('divergent') or {}) if isinstance(_kont, dict) else {}
            try:
                _v = float(_div.get('length'))
                if np.isfinite(_v) and _v > 0.0:
                    L_div_kontur_mm = _v
            except (TypeError, ValueError):
                L_div_kontur_mm = None
        if L_div_kontur_mm is not None:
            L_div = L_div_kontur_mm / 1000.0
            L_div_source = 'solver (nozzle_contour.divergent.length)'
        else:
            L_div = (self.d_e / 2 - self.d_t / 2) / np.tan(np.radians(div_half_angle))
            L_div_source = (
                f'derived from the published divergent half angle '
                f'({div_half_angle:.1f} deg) because the nozzle solver did '
                f'not return a contour in this run; exact for a cone, an '
                f'approximation for contoured nozzles')
        total_motor_length = self.L + L_conv + L_div
        # Total mass estimate: propellant + dry mass (~25% of propellant for small motors)
        # v2.6.26 — KURU KÜTLE ARTIK GEOMETRİDEN HESAPLANIYOR.
        #
        # Burada `dry_mass_est = 0.25 * m_total` yazıyordu: itergaç kütlesinin
        # dörtte biri alınan bir başparmak kuralı. Kullanıcının cidar
        # kalınlığından, malzemesinden ve motorun kendi geometrisinden
        # TAMAMEN kopuktu — ölçüldü: cidar 3 mm'den 20 mm'ye çıkarıldığında
        # bu sayı 1,366 kg'da SABİT kaldı, malzeme değişimi de etkilemedi.
        # Aynı koşuda CAD kütle dökümü gerçek geometri × yoğunlukla
        # 32,02 kg veriyordu; iki sayı 23 KAT farklıydı ve ikisi de "kuru
        # kütle" adıyla kullanıcıya gösteriliyordu. İtki/ağırlık oranı bu
        # sayıdan çıktığı için uçuş bütçesi de yanlış oluyordu.
        #
        # Yeni davranış: yapısal analizin hesapladığı GERÇEK kamara kütlesi
        # kullanılır. Yapısal sonuç yoksa sayı UYDURULMAZ — None döner ve
        # nedeni beyan edilir (0 yazmak "kütlesiz motor" demek olurdu).
        dry_mass_est = None
        dry_mass_basis = 'structural analysis not available'
        try:
            weight = (structural_results or {}).get('weight_analysis') or {}
            for key in ('total_mass', 'total_weight', 'total_structural_mass'):
                candidate = weight.get(key)
                if candidate is not None and np.isfinite(float(candidate)):
                    dry_mass_est = float(candidate)
                    # FAZ 5 / H4-7 — bu metin motorun kuru kütlesinin
                    # KAPSAMINI yanlış anlatıyordu ("real geometry" diyor ama
                    # lüle payı %30 başparmak kuralı, enjektör ise hiç yok).
                    # Ölçüm (2 kN N2O/HTPB hibrit): aynı yanıtta İKİ ayrı
                    # "kuru kütle" var ve %22,8 ayrışıyorlar:
                    #   structural...weight_analysis.total_weight  16,8366 kg
                    #       kamara + kapaklar + %30-kuralı lüle, ENJEKTÖR YOK
                    #   cad_design...mass_breakdown.total_dry_mass 13,7130 kg
                    #       kamara + ÇİZİLEN lüle + enjektör, KAPAKLAR YOK
                    # OTORİTE burada BEYAN edilir: uçuş zinciri (.eng dosyası,
                    # yörünge, T/W) yapısal analizin toplamını kullanır, çünkü
                    # kapakları ve kullanıcının gerçek cidar kalınlığını içeren
                    # tek toplam odur. Lüle KÜTLESİ için otorite ise çizilen
                    # katıdır (bkz. openrocket_integration.dry_mass_
                    # reconciliation) — %30 kuralı kaynağında "ESTIMATE"
                    # olarak beyanlıdır.
                    dry_mass_basis = (
                        'AUTHORITATIVE dry mass for the flight chain (.eng, '
                        'trajectory, T/W): structural_analysis.weight_analysis'
                        '.total_weight = chamber shell (real wall thickness x '
                        'material density) + end closures + nozzle. SCOPE '
                        'LIMITS: the nozzle share is a 30%-of-chamber rule of '
                        'thumb (see nozzle_weight_basis), and the injector is '
                        'NOT included. The CAD mass breakdown '
                        '(cad_design.performance_summary.mass_breakdown.'
                        'total_dry_mass) is a DIFFERENT total: it uses the '
                        'as-drawn nozzle and the injector but omits the '
                        'closures, so the two do not agree.')
                    break
        except (TypeError, ValueError, AttributeError):
            dry_mass_est = None
        # F3-2 (bebek-Scofield): KÜTLE bütçesi YÜKLENEN değerlerle kurulur.
        # Eski satır self.m_total (= yüklenen oksitleyici + YANAN yakıt)
        # kullanıyordu: yanmayan sliver (grain'in kamara cidarına dökülen ama
        # web tükenince yanmadan kalan kısmı) araçta UÇAR ama toplam kütlede
        # SAYILMIYORDU — ölçüldü (örnek 3 kN motor): 97,2327 kg yayımlanırken
        # gerçek yüklü kütle 102,4798 kg (fark 5,247 kg = sliver, %5,1).
        # Aynı yanıtın oxidizer_mass_basis alanı kuralı zaten yazıyordu:
        # "The mass budget must use the loaded value, the performance budget
        # the consumed one." dry_mass_basis bu alanı uçuş zinciri (T/W, araç
        # bütçesi) için YETKİLİ ilan ettiğinden yüklenen taraf seçildi;
        # yanan-yakıt bütçesi fuel_mass / propellant_mass_total alanlarında
        # ayrıca durur.
        _m_f_yuklu = float(getattr(self, 'm_f_loaded', self.m_f))
        total_mass = (float(self.m_ox) + _m_f_yuklu + dry_mass_est
                      if dry_mass_est is not None else None)

        # --- T60 kalıntısı (v2.6.27): "toplam motor boyu" İKİ tanımla
        # geziyordu. total_motor_length (yukarıda) kamara + yakınsak +
        # ıraksak toplamıdır ve ÖN KAPAĞI İÇERMEZ; 3B görünümün "L" etiketi
        # ise kapak DAHİL ölçer (motor_viz3d.js: zExit + capT). Aynı ad
        # altında iki tanım, atölyede yanlış boy demektir. İki büyüklük de
        # AÇIK adla ve beyanla yayımlanır; eski alan geriye uyum için kalır.
        # Kapak boyu UYDURULMAZ: yapısal kapak analizinin gerçekten
        # boyutlandırdığı eksenel kalınlık (head_thickness_used_mm) yoksa
        # kapaklı boy None kalır ve beyanı nedenini söyler.
        cap_len_m = None
        try:
            _ec = (structural_results or {}).get('end_cap_analysis') or {}
            _cap_mm = _ec.get('head_thickness_used_mm')
            if _cap_mm is not None and np.isfinite(float(_cap_mm)) \
                    and float(_cap_mm) > 0:
                cap_len_m = float(_cap_mm) / 1000.0
        except (TypeError, ValueError, AttributeError):
            cap_len_m = None
        total_motor_length_with_caps = (
            total_motor_length + cap_len_m if cap_len_m is not None else None)

        # --- Tasarım durumu: beyan kanalını OKUYAN kapı (Faz 4B, bulgu B1) ---
        # Burada koşulsuz 'OPTIMIZED' yazıyordu. Kurucudaki :223-227 yorumu
        # "design_summary.status bu bayrağı okur" diyordu ama okuyan yoktu:
        # ölçüldü (2 Ağustos 2026), itki/süre verilmeden koşulan hibritte
        # _defaults_used = ['nozzle_material', 'thrust', 'burn_time'] dolu,
        # status yine 'OPTIMIZED'. Aynı ölü kanal :1930'da bir kez daha
        # bildirilmişti (erken web tükenmesi de status'a girmiyordu).
        #
        # Hibritte GERÇEK bir tasarım eniyileyicisi ÇALIŞMAZ: find_optimum_of_ratio
        # yalnız danışma amaçlıdır, sonucu 'optimum_analysis' olarak raporlanır ve
        # tasarım O/F'sini DEĞİŞTİRMEZ (bkz. bu fonksiyonda optimum_of'un tek
        # kullanımı: :2568 civarı rapor alanları). Bu yüzden hibrit motorun en iyi
        # durumu 'CALCULATED'tir; 'OPTIMIZED' hiçbir koşulda üretilmez.
        durum_gerekce = []
        durum = DESIGN_STATUS_CALCULATED
        defaults_used = list(getattr(self, '_defaults_used', []) or [])
        fallbacks_used = list(getattr(self, '_fallback_used', []) or [])
        if defaults_used:
            durum = _worst_design_status(
                durum, DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS)
            durum_gerekce.append(
                'critical inputs were not supplied and fall back to built-in '
                'defaults: ' + ', '.join(defaults_used))
        if fallbacks_used:
            # Alt modül çöküp yedek yola düşmek de "tam çözüm" değildir.
            durum = _worst_design_status(
                durum, DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS)
            durum_gerekce.append(
                'a sub-model failed and a fallback path was used: '
                + ', '.join(fallbacks_used))
        if getattr(self, '_web_exhausted', False):
            # Port çapı sınırına yanma süresi dolmadan ulaşıldı: istenen
            # yanma süresi TUTTURULAMADI (bkz. :1930 yorumu).
            durum = _worst_design_status(durum, DESIGN_STATUS_TARGET_NOT_MET)
            durum_gerekce.append(
                f'the fuel web was exhausted at '
                f'{float(getattr(self, "t_burn_effective", self.t_b)):.3f} s, '
                f'before the requested burn time of {float(self.t_b):.3f} s')

        # Listeler ÜST DÜZEYDE de yayımlanır: arayüz ve dış tüketiciler
        # (PDF/CAD/export) design_summary'ye inmeden bakabilsin.
        basic_results['defaults_used'] = defaults_used
        basic_results['fallbacks_used'] = fallbacks_used

        basic_results['design_summary'] = {
            'title': f'{self.motor_name or "Hybrid Motor"} - Design Summary',
            'status': durum,
            # Durumun NEDEN o etiket olduğu okunabilir olmalı; etiketin tek
            # başına gezinmesi bu bulgunun ta kendisiydi.
            'status_basis': (durum_gerekce if durum_gerekce else
                             ['all critical inputs were supplied by the user; '
                              'no optimiser is applied to a hybrid design, so '
                              'the best attainable status is '
                              + DESIGN_STATUS_CALCULATED]),
            'defaults_used': defaults_used,
            'fallbacks_used': fallbacks_used,
            'key_dimensions': {
                'chamber_diameter_mm': chamber_diameter * 1000,
                'chamber_length_mm': self.L * 1000,
                'nozzle_throat_diameter_mm': self.d_t * 1000,
                'nozzle_exit_diameter_mm': self.d_e * 1000,
                'total_motor_length_mm': total_motor_length * 1000,
                # T60: eski alanın kapsamı adında görünmüyordu; iki açık ad.
                'total_motor_length_chamber_nozzle_mm':
                    total_motor_length * 1000,
                'total_motor_length_with_caps_mm': (
                    total_motor_length_with_caps * 1000
                    if total_motor_length_with_caps is not None else None),
                'forward_closure_length_mm': (
                    cap_len_m * 1000 if cap_len_m is not None else None),
                'total_motor_length_basis': (
                    'total_motor_length_chamber_nozzle_mm (= the legacy '
                    'total_motor_length_mm) is chamber + convergent + '
                    'divergent nozzle sections and EXCLUDES the forward '
                    'closure (end cap). total_motor_length_with_caps_mm '
                    'additionally includes the forward closure axial '
                    'thickness taken from the structural end-cap analysis '
                    '(head_thickness_used_mm); the aft end of a hybrid is '
                    'the nozzle itself, no separate aft cap length exists. '
                    'The 3D view total-length label is cap-inclusive, so it '
                    'corresponds to the with-caps definition (its cap depth '
                    'is a display heuristic, not this structural value).'
                    + ('' if cap_len_m is not None else
                       ' with_caps is None because the structural end-cap '
                       'analysis is unavailable in this run; the length is '
                       'not fabricated.')),
                'total_mass_kg': total_mass,
                # F3-2: kütle bütçesi tanımı ADIYLA — tüketici (T/W, araç
                # bütçesi, rapor) hangi kütleyi okuduğunu bilmek zorunda.
                'total_mass_basis': (
                    'LOADED lift-off mass: dry mass + LOADED oxidizer '
                    '(oxidizer_mass) + LOADED fuel grain (fuel_mass_loaded, '
                    'which includes the unburnt sliver that flies as dead '
                    'weight). The mass budget uses loaded values; the '
                    'performance budget uses the consumed ones (fuel_mass, '
                    'oxidizer_mass_consumed_kg) - same rule as '
                    'oxidizer_mass_basis.'),
                'dry_mass_estimate_kg': dry_mass_est,
                # Kütlenin nereden geldiği görünür olmalı: eskiden bu alan
                # bir başparmak kuralıydı ve kullanıcı bunu bilmiyordu.
                'dry_mass_basis': dry_mass_basis,
            },
            # D15/P1B2-01 — ÖZET MANŞETLE AYNI SAYIYI YAYIMLAR.
            # ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/hibrit/a1/once.json; 3 kN
            # N2O/HTPB, burn_time = 40 s, port 50 mm, kamara 70 mm):
            # burn_time_clipped = True iken üst düzey burn_time = 2,8000 s
            # ⟷ design_summary.performance.burn_time_s = 40,0000 s
            # (+%1328,57); üst düzey total_impulse = 8391,7 Ns ⟷ özet
            # 120000,0 Ns (+%1329,98 = 14,3 kat). Aynı yanıt
            # status = TARGET_NOT_MET diyor ve warn.hybrid.web_exhausted_early
            # taşıyordu; özet bloğunda tek bir *_basis alanı yoktu. Panelin
            # "Design Summary" tablosu (app.js designSummarySection) BU
            # bloktan besleniyor, aynı sayfadaki itki-zaman eğrisi ise 2,8
            # s'de bitiyordu — tek ekranda iki süre.
            #
            # Kök: blok self.t_b / self.I_total (İSTENEN) okuyordu; manşet
            # v2.6.27'de TESLİM EDİLEN değere bağlanmış ama özet bloğu
            # bağlanmamıştı. Artık iki uç AYNI değişkenden beslenir —
            # basic_results'ın kendisinden okunur ki bir daha ayrışamasın.
            'performance': {
                'thrust_N': self.F,
                'specific_impulse_s': self.Isp,
                # ÖH D21 / P15B1-04 — HANGİ SAYININ TESLİM EDİLEN OLDUĞU.
                # Kalem, aynı yanıtta tasarım noktası Isp'si iddia eden
                # birden çok yaprak bulunduğunu ve hiçbirinin "teslim edilen
                # bu" demediğini ölçmüştü. Manşet artık kendini tanımlar;
                # yanındaki diğer Isp yaprakları AYNI SORUNUN İKİNCİ CEVABI
                # DEĞİL, farklı büyüklüklerdir ve burada adlarıyla anılır.
                # (Kullanıcıya dönük alan -> İngilizce.)
                'specific_impulse_basis': _ISP_HEADLINE_BASIS,
                'burn_time_s': basic_results['burn_time'],
                'total_impulse_Ns': basic_results['total_impulse'],
                'burn_time_requested_s': basic_results[
                    'burn_time_requested_s'],
                'burn_time_effective_s': basic_results[
                    'burn_time_effective_s'],
                'burn_time_clipped': basic_results['burn_time_clipped'],
                'total_impulse_requested_Ns': basic_results[
                    'total_impulse_requested_Ns'],
                'total_impulse_delivered_Ns': basic_results[
                    'total_impulse_delivered_Ns'],
                'burn_time_basis': basic_results['burn_time_basis'],
                'total_impulse_basis': basic_results['total_impulse_basis'],
                'characteristic_velocity_m_s': self.C_star,
                'thrust_coefficient': self.CF,
            },
            'nozzle': {
                'convergent_length_mm': L_conv * 1000,
                'divergent_length_mm': L_div * 1000,
                # D15/P1B2-02: bu boyun NEREDEN geldiği alan adıyla taşınır —
                # 'solver (...)' ile başlıyorsa çizilen/ihraç edilen konturun
                # ta kendisidir, 'derived ...' ile başlıyorsa türetmedir.
                'divergent_length_source': L_div_source,
            },
            # v2.6.26 (bulgu B1): metin "Optimised design ..." diyordu; hibritte
            # hiçbir tasarım eniyileyicisi çalışmadığı için bu iddia yanlıştı.
            # Boyutlandırma yapılır, eniyileme yapılmaz.
            'recommendation': ('Design sized for the given parameters. Nozzle '
                               'angles and grain geometry are sized to the '
                               'design point; no design optimiser is applied.'),
        }

        # Add advanced analysis results if available
        if combustion_results:
            basic_results['combustion_analysis'] = combustion_results
            basic_results['stoichiometric_of'] = combustion_results['stoichiometric_of']
            basic_results['equivalence_ratio'] = combustion_results['equivalence_ratio']
            basic_results['mass_fractions'] = combustion_results['compositions']
        
        if nozzle_results:
            basic_results['nozzle_design'] = nozzle_results
            basic_results['nozzle_geometry'] = nozzle_results['geometry']
            basic_results['nozzle_contour'] = nozzle_results['contour']
        
        if altitude_performance:
            basic_results['altitude_performance'] = altitude_performance
            basic_results['sea_level_isp'] = altitude_performance['sea_level_isp']
            basic_results['vacuum_isp'] = altitude_performance['vacuum_isp']
        
        if optimum_of:
            basic_results['optimum_analysis'] = optimum_of
            basic_results['optimum_of_ratio'] = optimum_of['optimum_of_ratio']
            basic_results['maximum_isp'] = optimum_of['maximum_isp']
        
        if thrust_altitude_analysis:
            basic_results['thrust_altitude_analysis'] = thrust_altitude_analysis
        
        if heat_transfer_results:
            basic_results['heat_transfer_analysis'] = heat_transfer_results
        
        if structural_results:
            basic_results['structural_analysis'] = structural_results

        # F5-1 (bebek-Scofield): cidarın TEK kaynağı ve seçilen yol ADIYLA
        # yayımlanır — ısı, yapısal ve CAD zincirleri hangi cidarı
        # paylaşıyor, kim seçti, boyutlandırma kaç adımda oturdu.
        if getattr(self, 'wall_thickness_policy', None):
            basic_results['chamber_wall_policy'] = dict(
                self.wall_thickness_policy)

        # ÖH D31 / OH-D26-04: soğutma KANAL GEOMETRİSİ menüde sorulup modelde
        # çözülmediği için, hangi seçimin hangi sınıfa düştüğü ve o sınıfta
        # kendisinden ayırt EDİLEMEYEN başka seçim olup olmadığı ADIYLA
        # yayımlanır. Beyan bir düzeltme katsayısının yerini TUTMAZ; eksik
        # olanı gizlemez.
        if getattr(self, '_cooling_geometry_block', None):
            basic_results['cooling_channel_geometry'] = dict(
                self._cooling_geometry_block)

        if nozzle_material_results:
            basic_results['nozzle_material_analysis'] = nozzle_material_results

        # --- A1 (yol haritası): N₂O kendinden-basınçlı tank blowdown bloğu.
        # Çözücünün gerçek değerlerinden kurulur; uygulanamazsa NOT_MODELLED
        # gerekçesiyle boş döner (ayrıntı _tank_blowdown_block docstring'i).
        basic_results['tank_blowdown'] = self._tank_blowdown_block()
        # Kitap uyum B16: HP dengesine giren oksitleyici giriş durumu
        # (sıcaklık, faz, oluşum entalpisi [kJ/mol], yöntem, kaynak).
        basic_results['oxidizer_inlet_state'] = (
            self._oxidizer_inlet_state_block())

        # --- A5 (yol haritası): kamara yalıtım astarı + çıplak cidar sıcaklık
        # geçmişi — ısı transferi sonucunun gerçek akı/sıcaklıklarıyla beslenir;
        # girdi yoksa NOT_MODELLED gerekçesiyle boş döner.
        basic_results['thermal_protection'] = self._thermal_protection_block(
            heat_transfer_results)

        # --- A8 (yol haritası): fırlatma sahası rakım/ortam düzeltmesi —
        # yalnız kullanıcı bir saha verdiyse; verilmediyse beyanla boş.
        basic_results['launch_site_performance'] = self._launch_site_block()

        # --- A2 (yol haritası): oksitleyici tankı slosh analizi — tank hacmi
        # blowdown bloğundan (tek tank, tek hacim), g_eff sabit-1g beyanıyla.
        basic_results['oxidizer_tank_slosh'] = self._oxidizer_tank_slosh_block(
            basic_results['tank_blowdown'])

        # --- A9 (yol haritası): O/F kayması ve tasarım noktasıyla farkı.
        # ṁ_ox(t) blowdown bloğu modellendiyse ORADAN okunur (tek kaynak);
        # okunamıyorsa blowdown durumu gerekçesiyle boş kalır. Uyarı bu çağrı
        # içinde üretildiği için design_warnings anlık görüntüsünden ÖNCE
        # yapılmalıdır (aşağıdaki warnings_list satırı).
        basic_results['of_shift'] = self._of_shift_block(
            basic_results['tank_blowdown'])
        # ÖH D24 / OH-D23-18 — EĞRİNİN KENDİ HARCADIĞI KÜTLE ÜST SEVİYEDE.
        # ``isp_delivered_avg_basis`` bu alanın adını anıyor; alan yoksa künye
        # olmayan bir şeyi işaret ederdi. Sayı BURADA HESAPLANMAZ, yalnız
        # blokta zaten çözülmüş olandan okunur (tek kaynak). Blok
        # modellenmemişse alan None kalır — uydurma yok.
        _reg_ozet = basic_results['of_shift'].get('regulated')
        basic_results['propellant_mass_consumed_kg'] = (
            _reg_ozet.get('propellant_consumed_kg')
            if isinstance(_reg_ozet, dict) else None)
        # Eski tüketiciler (motor_viz3d.js of_shift_performance okuyor) için
        # farklar aynı blokta da yayımlanır; DİZİLER İKİ KEZ TAŞINMAZ.
        of_perf = basic_results.get('of_shift_performance')
        reg_ozet = basic_results['of_shift'].get('regulated')
        if isinstance(of_perf, dict) and isinstance(reg_ozet, dict):
            of_perf['of_ratio_design'] = reg_ozet['of_ratio_design']
            of_perf['isp_mass_avg'] = reg_ozet['isp_mass_avg_s']
            of_perf['isp_delta_vs_design_pct'] = \
                reg_ozet['isp_delta_vs_design_pct']
            of_perf['c_star_delta_vs_design_pct'] = \
                reg_ozet['c_star_delta_vs_design_pct']
            of_perf['total_impulse_Ns'] = reg_ozet['total_impulse_Ns']
            of_perf['total_impulse_delta_vs_design_pct'] = \
                reg_ozet['total_impulse_delta_vs_design_pct']
            of_perf['summary_block'] = 'of_shift'

        # --- A10 (yol haritası): modellenmeyen fizik açıkça beyan edilir.
        basic_results['not_modelled'] = self._not_modelled_declarations()
        basic_results['not_modelled_basis'] = (
            'explicit declarations of physics this hybrid solver does NOT '
            'compute (roadmap A10; the pattern the liquid and solid engines '
            'already follow). Every entry was verified against the code: the '
            'named computation exists nowhere in the hybrid chain, and items '
            'already declared at their own source (rigid-throat erosion, '
            'kinetic-efficiency diagnosis, multi-port equivalent-model '
            'warning) are not duplicated here. A declared absence is honest; '
            'a fabricated number is not.')

        # v2.6.26: hibrit motor uyarıları TOPLUYOR ama sonuç sözlüğüne HİÇ
        # koymuyordu; ``self.design_warnings`` listesi nesneyle birlikte
        # ölüyordu. Ölçüldü: chamber_material='ZIRVAAA' gönderilen bir istek
        # HTTP 200 dönüyor, sessizce steel_4130 kullanılıyor ve kullanıcıya
        # HİÇBİR uyarı ulaşmıyordu — yani "sessiz yedeğe düşme yasak" diyen
        # _resolve_chamber_material'ın uyarısı fiilen yok hükmündeydi.
        # Katı motorda olduğu gibi iki adla birden verilir: arayüz panelleri
        # 'warnings', dış tüketiciler 'design_warnings' okuyor.
        finite_area = self._finite_area_combustor()
        if finite_area:
            basic_results['finite_area_combustor'] = finite_area

        warnings_list = list(getattr(self, 'design_warnings', []) or [])
        # ÖH P16S1-07 — TERMAL HÜKMÜN TESLİM KANALI. Termal blokların
        # ürettiği ``severity: critical`` hükümler (lüle malzemesi boğaz
        # aşımı + ısı transferi zincirinin erime/servis aşımı hükümleri)
        # kendi bloklarında KALIYORDU. Ekran katmanı yalnız bu listeyi
        # okuduğu için hüküm hiçbir yerde görünmüyordu; hüküm burada
        # yeniden yazılmaz, kaydın ta kendisi taşınır ve kimliğine göre
        # yinelenmez (aynı kayıt gas_side + safety_analysis'te iki kez var).
        _mevcut = {_warning_identity(w) for w in warnings_list}
        warnings_list += [
            w for w in _critical_thermal_verdicts(
                basic_results.get('nozzle_material_analysis'),
                basic_results.get('heat_transfer_analysis'))
            if _warning_identity(w) not in _mevcut]
        basic_results['design_warnings'] = warnings_list
        basic_results['warnings'] = warnings_list

        # D15/P10B3-08 — MALZEME ADININ KÜNYESİ. Motor artık her yerde
        # KANONİK materials_db anahtarını kullanıyor (bkz.
        # _resolve_chamber_material); kullanıcının yazdığı ham ad burada
        # görünür kalır ki "ben steel_304 seçmiştim, ekran ss_304 diyor"
        # sorusunun cevabı yanıtın içinde olsun. Alan düzeni
        # /analyze_structural_safety'nin `material_resolution` bloğuyla
        # birebir aynıdır (tek sözleşme, iki uç).
        basic_results['chamber_material'] = self.chamber_material
        basic_results['chamber_material_resolution'] = {
            'field': 'chamber_material',
            'requested': getattr(self, 'chamber_material_requested', None),
            'resolved_to': self.chamber_material,
            'resolution': getattr(self, 'chamber_material_resolution', None),
        }

        # --- v2.6.27 (B3): lüle iç konturu TEK kaynaktan yayımlanır --------
        # motor_viz3d.js selectNozzleContour bu bloğu okur; blok yoksa sahne
        # yerel üretime düşer ve bunu çipiyle beyan eder. Örnekleyici, 2B
        # kesit / 3B sahne / STL-STEP dışa aktarımının kullandığı fonksiyonun
        # AYNISIDIR (nozzle_design.sample_nozzle_inner_contour) — ekrandaki
        # kontur ile imalata giden kontur ayrışamaz. Hibrit sonuç sözlüğü üst
        # düzeyde METRE taşıdığı için örnekleyiciye doğrudan verilir; çağrı,
        # 'nozzle_contour' (NozzleDesigner) ve 'design_summary.nozzle'
        # yerleştirildikten SONRA yapılır ki ıraksak boy çözücüden okunsun.
        #
        # ORİJİN SÖZLEŞMESİ (doğrulandı): örnekleyicinin ilk noktası
        # konverjan GİRİŞİDİR (kamara-lüle birleşimi) — s=0'da
        # r = rt + (rc-rt)·(0.5+0.5·cos 0) = rc, z = 0; z çıkışa doğru artar.
        # viz3d bu varsayımla çizer; boğaz-orijinli bir seri yayımlamak lüleyi
        # yanlış konumlandırır. Bekçi: tests/test_motor_geometri_yayimi.py.
        # Örnekleyici başarısız olursa blok yayımlanmaz (uydurma kontur yok);
        # NozzleDesigner bloğu points'siz aynen kalır.
        try:
            pts_mm, kontur_meta = sample_nozzle_inner_contour(basic_results)
            onceki_kontur = basic_results.get('nozzle_contour')
            kontur_blok = (dict(onceki_kontur)
                           if isinstance(onceki_kontur, dict) else {})
            kontur_blok['points'] = [
                [float(z) / 1000.0, float(r) / 1000.0] for z, r in pts_mm]
            kontur_blok['_basis'] = (
                'sampled inner flow-path contour from hrma.engines.'
                'nozzle_design.sample_nozzle_inner_contour — the same sampler '
                'the 2D cross-section, the 3D scene and the STL/STEP exports '
                'consume. points are [z_m, r_m] pairs in metres; the FIRST '
                'point is the convergent inlet (chamber-nozzle junction, '
                'z = 0, r = chamber radius) and z increases toward the nozzle '
                'exit. Divergent length source: '
                + str(kontur_meta.get('divergent_length_source')))
            basic_results['nozzle_contour'] = kontur_blok
        except Exception:
            # Fail-closed: kontur üretilemiyorsa ÜRETİLMEZ; viz yerel üretime
            # düşer ve kaynağı 'kontur: yerel üretim' çipiyle beyan eder.
            pass

        # --- V3 yapi-sf (7 Eki 2026): LÜLE KÜTLESİ TEK KAYNAK ------------
        # ÖLÇÜLDÜ (main 393960ce, örnek 3 kN hibrit): aynı yanıtta üç lüle
        # kütlesi vardı — 0,4275 kg (cad_design dökümü: çizilen katı),
        # 0,3248 kg (nozzle_geometry.estimated_mass: lüle tasarımcısının
        # KENDİ yakınsak konisi, ≈1,5·r_boğaz kamara yarıçapıyla — çizilen
        # lüle DEĞİL) ve 24,78 kg (weight_analysis.nozzle_weight: kamara
        # kütlesinin %30'u; kalın kamara cidarı 82,61 kg verdiği için).
        # Kuru kütle (108,21 kg; .eng, T/W) %30 kuralını taşıyordu.
        # Tek kaynak: ÇİZİLEN katı — yukarıdaki örnekleyicinin aynı
        # konturu, yayımlanan lüle eti, seçilen lüle malzemesi. Kütle
        # dökümü ve estimated_mass ondan türer; kesik koni yaklaşımı
        # açık adla ayrı alanda kalır. Kontur/et/malzeme yoksa dokunulmaz
        # (eski beyanlı yol sürer, sayı uydurulmaz).
        # 2. tur (denetim bloklamayan not 1): değerler ÖNCE hesaplanır,
        # SONRA birlikte atanır — hesap yarıda bir istisnayla kesilirse döküm
        # ile kuru kütle sessizce ayrışmaz (ya hepsi ya hiçbiri).
        _plan = None
        try:
            from hrma.analysis.structural_analysis import (
                drawn_nozzle_shell_mass_kg, DRAWN_NOZZLE_MASS_BASIS,
                FRUSTUM_APPROXIMATION_MASS_BASIS, DRY_MASS_BASIS_DRAWN_NOZZLE,
                DRY_MASS_BASIS_DRAWN_NOZZLE_OUTSIDE_VALIDITY)
            from hrma.data.materials_db import get_material
            _ng = basic_results.get('nozzle_geometry')
            _yap = basic_results.get('structural_analysis')
            _mal = (basic_results.get('nozzle_material')
                    or basic_results.get('throat_material'))
            _et_mm = (float(_ng.get('wall_thickness'))
                      if isinstance(_ng, dict)
                      and _ng.get('wall_thickness') is not None else None)
            if (_mal and _et_mm is not None and np.isfinite(_et_mm)
                    and _et_mm > 0 and isinstance(_yap, dict)
                    and isinstance(_yap.get('weight_analysis'), dict)):
                _rho = float(get_material(str(_mal))['density'])
                _pts, _meta = sample_nozzle_inner_contour(basic_results)
                _m_lule = drawn_nozzle_shell_mass_kg(
                    _pts, _et_mm / 1000.0, _rho)
                if np.isfinite(_m_lule) and _m_lule > 0:
                    _yeni_w = self.structural_analyzer.apply_drawn_nozzle_mass(
                        _yap['weight_analysis'], _m_lule,
                        DRAWN_NOZZLE_MASS_BASIS)
                    _kuru = float(_yeni_w['total_weight'])
                    _gecersiz = bool(
                        _yeni_w.get('model_validity_limit_exceeded'))
                    _plan = {
                        'yap': _yap, 'w': _yeni_w, 'ng': _ng,
                        'm_lule': _m_lule, 'kuru': _kuru,
                        'kalkis': (float(self.m_ox)
                                   + float(getattr(self, 'm_f_loaded',
                                                   self.m_f))
                                   + _kuru),
                        'gecersiz': _gecersiz,
                        'kuru_taban': (
                            DRY_MASS_BASIS_DRAWN_NOZZLE_OUTSIDE_VALIDITY
                            if _gecersiz else DRY_MASS_BASIS_DRAWN_NOZZLE),
                        'frustum_taban': FRUSTUM_APPROXIMATION_MASS_BASIS,
                        'lule_taban': DRAWN_NOZZLE_MASS_BASIS,
                    }
        except Exception:
            # Fail-closed: yeniden tartım kurulamazsa eski beyanlı döküm
            # (nozzle_weight_source = rule_of_thumb_fraction_of_chamber)
            # aynen kalır; sayı uydurulmaz.
            _plan = None
        _kd = (basic_results.get('design_summary') or {}).get(
            'key_dimensions')
        if _plan is not None:
            _ng = _plan['ng']
            _m_lule = _plan['m_lule']
            _plan['yap']['weight_analysis'] = _plan['w']
            if isinstance(_ng, dict):
                _ng['frustum_approximation_mass_kg'] = \
                    _ng.get('estimated_mass')
                _ng['frustum_approximation_mass_basis'] = \
                    _plan['frustum_taban']
                _ng['estimated_mass'] = _m_lule
                _ng['estimated_mass_basis'] = _plan['lule_taban']
            # Kuru kütle ve kalkış kütlesi aynı dökümden yeniden.
            if isinstance(_kd, dict) and np.isfinite(_plan['kuru']):
                _kd['dry_mass_estimate_kg'] = _plan['kuru']
                _kd['total_mass_kg'] = _plan['kalkis']
                _kd['dry_mass_basis'] = _plan['kuru_taban']
        # V3 yapi-sf 2. tur (karar §28-24 (C)): kuru kütlenin geçerlilik
        # bayrağı makine-okur (uçuş zinciri tüketicileri için); kaynak
        # yapısal kütle dökümünün kendi bayrağı.
        _w_son = ((basic_results.get('structural_analysis') or {})
                  .get('weight_analysis'))
        if isinstance(_kd, dict) and isinstance(_w_son, dict):
            _kd['dry_mass_model_validity_limit_exceeded'] = bool(
                _w_son.get('model_validity_limit_exceeded'))

        # --- v2.6.27 (B2): enjektör delik deseni — yalnız GERÇEK çözümden --
        # motor_viz3d.js readInjectorPattern sözleşmesi: {n_holes,
        # hole_diameter_m, pattern_type, impingement_angle_deg?, _basis}.
        # Kaynak devre modelinin başarılı çözümüdür (injector_design_detail);
        # 'not_analyzed' yolunda blok YOKTUR — delik planı üretilemeyen
        # tasarıma desen çizdirilmez. n_rings hiçbir yerde hesaplanmadığı
        # için hiçbir koşulda yayımlanmaz (hesaplanmayan alan konmaz).
        detay = basic_results.get('injector_design_detail')
        if isinstance(detay, dict) and detay.get('status') == 'success':
            oxc = detay.get('ox_circuit') or {}
            desen_sozcugu = INJECTOR_PATTERN_WORD.get(
                str(detay.get('injector_type') or '').lower())
            n_delik = int(oxc.get('n_orifices') or 0)
            d_delik_mm = float(oxc.get('orifice_d_mm') or 0.0)
            if desen_sozcugu and n_delik >= 1:
                desen = {
                    'n_holes': n_delik,
                    'pattern_type': desen_sozcugu,
                    '_basis': (
                        'oxidizer-circuit orifice plan from the injector '
                        'design model (injector_design_detail.ox_circuit): a '
                        'hybrid injects only the oxidizer, so the face '
                        'pattern is the single oxidizer circuit. n_rings is '
                        'not computed by any solver and is therefore not '
                        'published.'),
                }
                if d_delik_mm > 0:
                    desen['hole_diameter_m'] = d_delik_mm / 1000.0
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
                basic_results['injector_pattern'] = desen

        # ==================================================================
        # v2.6.27 Dalga 6 — YAZILMIŞ AMA BAĞLANMAMIŞ ALTI MODÜLÜN BAĞLANMASI
        #
        # Bu altı üretici metot dosyada tanımlıydı ama sonuç sözlüğüne hiç
        # konmuyordu: yani ölü koddu — kullanıcı ne sonucu ne de yokluk
        # beyanını görüyordu. Bağlama burada, sonuç sözlüğünün SONUNDA
        # yapılır çünkü iki bağımlılık zinciri vardır:
        #   * A3 basınçlı kap, tank_blowdown (A1) ve oxidizer_tank_slosh (A2)
        #     bloklarının ÇÖZÜLMÜŞ hâlini okur (tek tank, tek durum);
        #   * yarı-1B lüle akışı, birkaç satır yukarıda yayımlanan iç kontur
        #     kaynağının AYNISINI örnekler, yani design_summary.nozzle ve
        #     nozzle_contour yerleştirildikten sonra çağrılmalıdır.
        #
        # ORTAK SÖZLEŞME: girdi yoksa blok sayı İÇERMEDEN NOT_MODELLED döner
        # ve eksik girdinin ADINI söyler (metotların kendi kapıları). Hiçbiri
        # itki/Isp/geometri sonucuna geri beslenmez — hepsi rapor katmanıdır.
        # ==================================================================

        # A3 — oksitleyici tankı basınçlı kap boyutlandırması. MEOP ve cidar
        # tasarım sıcaklığı blowdown çözümünün MAKSİMUMLARI, çap slosh
        # bloğunun tank geometrisi.
        basic_results['oxidizer_tank_pressure_vessel'] = \
            self._oxidizer_tank_vessel_block(
                basic_results.get('tank_blowdown'),
                basic_results.get('oxidizer_tank_slosh'))

        # A4 — kapak cıvata birleşimi. Sızdırmazlık çapı ve basınç çözücünün
        # gerçek değerleri; cıvata SAYISI tasarım kararıdır ve varsayılanı
        # yoktur, verilmediyse blok kendi eksik girdisini adıyla beyan eder.
        basic_results['closure_joint'] = self._closure_joint_block()

        # A6 — oksitleyici besleme hattı su koçu. Hibrit çözücüde besleme
        # hattı GEOMETRİSİ hiç yoktur; blok bunu sayı uydurmadan beyan eder.
        # Beyanın kendisi bir sonuçtur: kullanıcı boşluğu görebilmelidir.
        basic_results['feed_water_hammer'] = self._feed_water_hammer_block()

        # Kamara akustik modları + chug marjı. Bu bağlama, A10 listesindeki
        # 'combustion_stability_acoustics' beyanını ÇÜRÜTTÜ; beyan
        # _not_modelled_declarations'tan kaldırıldı (bkz. oradaki not).
        basic_results['acoustic_modes'] = self._acoustic_modes_block(
            basic_results)

        # F2b-1 — yanma kararlılığı (hrma/stability çekirdeği). Akustik
        # bloktan SONRA çağrılır: hem LFI'nin ayrışma dekadı hem de kritik
        # tepki eşiği o bloğun mod tablosunu ve ses hızını okur (ikinci bir
        # mod tablosu üretilmez). Bu blok da rapor katmanıdır: itki, Isp ya
        # da geometri sonucuna geri BESLENMEZ.
        basic_results['combustion_stability'] = \
            self._combustion_stability_block(basic_results)

        # Yarı-1B lüle iç akışı (rejim, şok konumu) + ayrılma denetimi.
        # Ayrılma sonucu bloğun İÇİNDE ('separation') taşınır; katı motorun
        # iki ayrı anahtarının (nozzle_flow_quasi1d / nozzle_flow_separation)
        # aksine burada tek blok yayımlanır — aynı veri iki kez taşınmaz.
        basic_results['nozzle_flow_quasi1d'] = self._nozzle_flow_block(
            basic_results)

        # D16/OH-Z5-07 — çapraz denetim hükmü TASARIM KAPISI DEFTERİNE de
        # düşer. Defter yukarıda (design_gate_checks) zaten yayımlandı ve
        # bu blok ondan SONRA çözülüyor, o yüzden kayıt doğrudan yayımlanan
        # listeye eklenir; `self.design_gate_checks`e eklemek bu koşuda geç
        # kalırdı (ölçüldü: defter anlık görüntüsü daha önce alınıyor).
        # Yalnız AYIRT EDİLEBİLİR ayrışma deftere girer — 'pass' hükmü
        # bloğun içinde durur, uyarı üretmez.
        _capraz = (basic_results['nozzle_flow_quasi1d'] or {}).get(
            'mass_flow_cross_check') or {}
        if _capraz.get('status') == 'divergent':
            basic_results.setdefault('design_gate_checks', []).append({
                'gate': 'nozzle_flow_gas_model_agreement',
                'status': 'out_of_band',
                'quantity': 'mass_flow_gas_model_rel_residual',
                'value': float(_capraz.get('residual')),
                'limit': float(_capraz.get('resolution')),
                'unit': '',
                'source': ('quasi-1D nozzle solution against the equilibrium '
                           'c* chain of the same run'),
                'basis': _capraz.get('basis'),
            })

        # Ateşleyici boyutlandırma. Modülün zorunlu girdilerinin çoğu bu
        # çözücüde yoktur; blok neyin VAR neyin YOK olduğunu denetlenebilir
        # biçimde listeler (available_inputs / required_inputs).
        basic_results['igniter_sizing'] = self._igniter_sizing_block(
            basic_results)

        return basic_results


# ---------------------------------------------------------------------------
# ÖH D37 A2 hibrit · 10. tur — kamara malzemesinin TEK varsayılanı.
# Bu blok BİLEREK modül sonundadır: yukarıdaki satır numaraları
# ``formal/registry.json`` Lean çapalarıdır (7470, 7482).
# ---------------------------------------------------------------------------
#: Kamara malzemesi istekte verilmediğinde (ya da tanınmadığında) kullanılan
#: TEK varsayılan. ÖLÇÜLDÜ (KAB 14 Eki, ``docs/kabul/kanit_2026-10-14``):
#: ``/calculate`` alan yokken ``steel_4130`` kullanıyor ve beyan etmiyordu;
#: hibrit sayfasının malzeme seçicisi ise ``steel_304``'ü (AISI 304) seçili
#: GÖSTERİYORDU — iki ayrı varsayılan (CLAUDE.md §11). Ana model kararı
#: (10. tur): değer ekranda görünen seçenek; motor, uç künyesi, şablonun
#: seçili seçeneği (``advanced.html``) ve örnek proje bu addan okur.
#: Ad materials_db'de ``ss_304``ün takma adıdır; motor kanonik ada çözer.
HYBRID_CHAMBER_MATERIAL_DEFAULT = 'steel_304'
