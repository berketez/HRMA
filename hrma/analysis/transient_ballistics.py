"""Hibrit motor zaman-çözümlü (transient) iç balistik: Pc(t) ve F(t).

Tasarım çözücüsü (HybridRocketEngine.calculate) sabit nokta etrafında
boyutlandırma yapar; bu modül boyutlandırılmış motoru zamanda yürüterek
GERÇEK kamara basıncı ve itki eğrilerini üretir:

  - Port büyümesi: Marxman G_total kapanışı (RegressionAnalyzer ile aynı
    fizik — tek tanım noktası, kopya formül yok)
  - Anlık O/F → anlık c*: motorun 0.05-çözünürlüklü denge önbelleği
    (HybridRocketEngine._instantaneous_performance) kullanılır
  - Yarı-kararlı kamara: P_c = ṁ_toplam · c* / (C_D · A_t)
    (kamara doldurma süresi ~L*/c_ses ≈ ms mertebesi; yanma süresi ~s
    mertebesinde olduğundan yarı-kararlılık geçerlidir)
  - İtki: F = C_F(P_c) · P_c · (C_D · A_t). Sabit geometri (ε sabit) ve
    sabit γ'da P_e/P_c oranı sabittir; C_F'in basınca bağımlılığı yalnız
    basınç-itki teriminden gelir: C_F = C_F,mom + ε·(P_e/P_c) − ε·P_a/P_c.
    C_D BURADA DA görünür çünkü kamara kapanışıyla AYNI sözleşmedir:
    C_D·A_t, aynı debiyi geçiren ideal (kayıpsız) lülenin etkin boğaz
    alanıdır ve c* tanımı gereği P_c·(C_D·A_t) = ṁ·c*'tır. İtkiyi geometrik
    A_t ile kurmak aynı C_D'yi bir kez daha saymak (1/C_D ≈ %2 şişme)
    demektir — bkz. aşağıdaki F3-1 künyesi.

Besleme modları:
  'regulated' : ṁ_ox sabit (regülatörlü/süperşarjlı besleme; tasarım değeri)
  'blowdown'  : N₂O kendinden-basınçlı tank (tank_blowdown.N2OTankBlowdown).
                Enjektör SPI orifis modeli: ṁ_ox = K·√(2·ρ_l(T)·ΔP),
                ΔP = P_tank − P_c. Etkin K = C_d·A_inj, t=0'da tasarım
                debisi + gerçek tank basıncından kalibre edilir (tasarım
                noktası tutarlılığı garanti).

Durdurma olayları: yakıt web'i bitti / tank sıvısı bitti / ΔP kararlılık
sınırının altına düştü (SP-8089: ΔP/P_c < 0.05 → yanma kararsızlığı) /
t_max aşıldı / boğaz erozyonla ε ≤ 1.2'ye büyüdü (erozyon açıkken).

Boğaz erozyonu (Dalga 3, opsiyonel — varsayılan KAPALI): ThroatErosionModel
ampirik ṙ = a_ref·(Pc/Pc_ref)^n modeliyle her adımda d_t büyütülür; Pc ve
F eğrileri buna göre düşer. Kapalıyken çözüm eski davranışla bit-özdeştir.
Üs n = THROAT_EROSION_PRESSURE_EXPONENT (1,0; künyesi Thakre & Yang 2008,
D28), referans basınç Pc_ref = THROAT_EROSION_PC_REF_BAR. (H-7, 6 Eki 2026:
bu başlık D28'den beri "^0.8" diyordu; kod 1,0 kullanıyor — 0,8 yalnız
Bartz taşınım ucunun üssüdür.)
"""

import re

import numpy as np
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid

from hrma.analysis.regression_analysis import (
    RegressionAnalyzer, fuel_mass_flow_kg_s)
from hrma.analysis.tank_blowdown import N2OTankBlowdown
from hrma.data.materials_db import get_material
# Ayrılma eşiği TEK tanım noktasından okunur (sayı kopyalanmaz); aynı sabiti
# hibrit motor da bu addan alır.
from hrma.flow.separation import SUMMERFIELD_FACTOR_DEFAULT
# Chug (besleme kuplajlı alçak frekans) tasarım kuralının eşiği de TEK tanım
# noktasından okunur. F2b-2 ÖNCESİ burada `DP_RATIO_WARN = 0.15` yazıyordu ve
# künyesi "SP-8089" idi; aynı sayı acoustic_modes'ta "Sutton + SP-194"
# künyesiyle duruyordu (aynı sayı, iki künye — parametre tutarlılığı ihlali).
# Sayı DEĞİŞMEDİ, tanım yeri tekleşti; künye hükmü ithal edilen yerdedir.
from hrma.analysis.acoustic_modes import (CHUG_DP_RATIO_MINIMUM,
                                          CHUG_THRESHOLD_CITATION)

# Chugging uyarı eşiği (ΔP/P_c): merkezî tanımın takma adı — burada YENİDEN
# TANIMLANMAZ. Ad korunur çünkü bu dosyanın uyarı metni ve i18n eşleşmesi
# (static/js/i18n_charts.js MSG_PATTERNS) bu değeri basıyor.
DP_RATIO_WARN = CHUG_DP_RATIO_MINIMUM

# ÇÖZÜCÜ GEÇERLİLİK TABANI — chug tasarım kuralı DEĞİLDİR (F2b-2 ayrımı):
# bu oranın altında enjektör kamara basıncından fiilen kopar, yarı-kararlı
# akış modeli geçersizleşir ve çözüm durur. Ne SP-8089'da ne başka bir
# kaynakta "0,05" diye yayımlanmış bir eşik olarak doğrulanmıştır; bu
# depodaki bir DURDURMA korumasıdır ve öyle beyan edilir. Yukarıdaki
# 0,15 ile aynı aileden sayılıp tek kaynağa taşınmadı: iki AYRI kavramdır.
DP_RATIO_UNSTABLE = 0.05  # bunun altında yarı-kararlı model geçersiz → dur

# Boğaz debi katsayısı C_D (tıkalı boğazdan geçen gerçek debinin ideal
# izentropik debiye oranı). Tasarım çözücüsü boğaz alanını
# A_t = ṁ·c*/(P_c·C_D) ile boyutlandırır; bu modül aynı sayıyı hem kamara
# kapanışında (P_c = ṁ·c*/(C_D·A_t)) hem itki denkleminde kullanır, yani
# TEK C_D sözleşmesi geçerlidir.
#
# NOT (tek kaynak borcu): aynı 0,98 hibrit çözücüde de yazılıdır
# (hybrid_rocket_engine.py, boğaz alanı boyutlandırması). O dosya bu iş
# kaleminin sahipliği dışındaydı; birleştirme ana modele bildirildi.
NOZZLE_DISCHARGE_COEFFICIENT = 0.98


# ---------------------------------------------------------------------------
# Boğaz erozyonu (Dalga 3, 2026-07-14) — ampirik, model-değiştirilebilir API
# ---------------------------------------------------------------------------
# Model:  ṙ_ero = a_ref · (Pc / Pc_ref)^n   [mm/s],  Pc_ref = 70 bar
#
# ÜSSÜN REJİMİ VE KAYNAĞI (D28/OH-D27-15). Grafit/C-C boğaz gerilemesi iki
# mekanizmanın SERİ birleşimidir ve her ucun basınç üssü ayrıdır:
#   (a) TAŞINIM UCU — oksitleyici türlerin (H2O, CO2, OH) cidara difüzyonu.
#       Kütle taşınım iletkenliği ısı taşınımıyla benzeşiktir (Chilton-
#       Colburn), Bartz korelasyonunda h_g ∝ Pc^0,8 olduğundan bu uç
#       ṙ ∝ Pc^0,8 verir. Tür KÜTLE KESİRLERİ basınçla neredeyse sabittir
#       (kaynak: "The species mass fractions remain nearly constant in the
#       pressure range of 6.9-45 MPa"), yani üssü yükselten şey bu uç değil.
#   (b) KİNETİK UCU — cidardaki heterojen yüzey tepkimeleri. Birinci
#       mertebeden kinetikte hız oksitleyicinin KISMİ BASINCIYLA ölçeklenir
#       (p_i = X_i·Pc, X_i ≈ sabit) ⇒ bu uç ṙ ∝ Pc^1,0 verir.
# Mekanizma bandı böylece n ∈ [0,8 ; 1,0]. Hangi ucun BASKIN olduğunu basınç
# değil CİDAR SICAKLIĞI belirler: kaynağın hükmü, geçişin ~2800 K yüzey
# sıcaklığında olduğu (metalize itergaçta difüzyon-kontrollü, metalize
# olmayanda kinetik-kontrollü). Kaynağın kendi hesabı ölçtüğü aralıkta
# (p_t = 6,9-45 MPa) İKİ REJİMDE DE hızı basınçla LİNEER verir — "Figure 14
# shows the linear variation of the graphite erosion rate at the nozzle
# throat with the chamber pressure" (s. 830) ve Sonuç bölümünde "The erosion
# rate increases linearly with the chamber pressure." (s. 832). Bu yüzden
# modelin üssü n = 1,0'dır; sayının TEK TANIM NOKTASI künyesidir
# (THROAT_EROSION_PRESSURE_EXPONENT_CITATION, aşağıda).
#
# D28'E KADARKİ DURUM (ölçüldü, docs/scofield/raw/OH/D28/kati/a1/once.json):
# üs 0,8 idi, elle yazılmış bir literaldi ve yalnız (a) ucuna — Bartz'ın ISI
# TRANSFERİ üssüne — dayanıyordu; erozyon literatürüne atfı YOKTU ve ürün
# yüzeyinde (describe(), katı motor erozyon tahmini) künyesiz yayımlanıyordu
# (exponent_source alanı hiç yoktu). Modül başlığı ayrıca Thakre & Yang'a
# "basınçla yaklaşık lineer-altı artar" dedirtiyordu; makale bunun TERSİNİ
# söyler (yukarıdaki iki alıntı). Sayısal yön: 0,8, kaynağın doğruladığı
# aralığın üst ucunda (45 MPa) lineer yasanın 0,689 katıdır, yani erozyonu
# %31 EKSİK — itki/basıncı FAZLA gösteren (güvensiz) yön.
#
# Kaynaklar:
#   - Thakre, P., Yang, V., "Chemical Erosion of Carbon-Carbon/Graphite
#     Nozzles in Solid-Propellant Rocket Motors", J. Propulsion and Power
#     24(4), 2008, s. 822-833, DOI 10.2514/1.34946 — üssün, grafit bandının
#     (Tablo 8) ve C-C çapasının (Tablo 5) ortak kaynağı. KÜNYE DÜZELTMESİ
#     (D28): depo bu makaleyi, Thakre'nin DOKTORA TEZİNİN başlığıyla
#     (refrakter metal lülelerden söz eden başlık; Penn State, 2008)
#     anıyordu. Makalenin başlığı yukarıdakidir; refrakter METAL çalışması
#     aynı yazarların AYRI bir yayınıdır (J. Prop. Power 25(1), 2009,
#     s. 40-50). Yanlış başlık burada TEKRARLANMAZ: tekrar edilirse depo
#     aramasında yine makaleye atfedilmiş görünür.
#   - Bartz, D.R., "A Simple Equation for Rapid Estimation of Rocket Nozzle
#     Convective Heat Transfer Coefficients", Jet Propulsion 27(1), 1957 —
#     yalnız (a) ucunun (h_g ∝ Pc^0,8) kaynağıdır; erozyon yasasının ÜSSÜ
#     DEĞİLDİR (D28'e kadar öyle kullanılıyordu).
#   - Geisler, R.L., "The Relationship Between Solid-Propellant Formulation
#     Variables and Nozzle Recession Rates", JANNAF Rocket Nozzle Technology
#     Subcommittee Meeting, Lancaster CA, 12-13 Temmuz 1978 — BATES motoru,
#     bulk grafit; ölçülen değerler Thakre & Yang 2008 Tablo 8 üzerinden
#     aktarılmıştır. Bandın SAYISAL DEĞERİ tek tanım noktası
#     GRAPHITE_A_REF_BAND_CITATION'dır (aşağıda), burada TEKRAR YAZILMAZ.
#   - Borie, J. ve ark. (SEP), karbon-karbon boğaz gerilemesi — Thakre &
#     Yang 2008 Tablo 5 / Şekil 18'deki TEK ölçüm noktası; C-C çapasının
#     tek tanım noktası CARBON_CARBON_A_REF_ANCHOR_CITATION'dır.
#
# a_ref bantları @ 70 bar sınıfı APPROXIMATE'tir: gerçek hız itki gazı
# oksitleyici kesrine (H2O+CO2+OH), alev sıcaklığına ve malzeme yoğunluğuna
# güçlü bağlıdır; ±%50 saçılım normaldir. Varsayılan = bandın KONSERVATİF
# (üst) ucu — ve bu kural KODLA UYGULANIR (bkz. aşağıdaki türetme döngüsü),
# elle yazılan ikinci bir sayı yoktur. Kesin tasarım için test verisi şarttır.
#
# D19/P2B4-09 (2026-09-03): grafit bandı ÜÇ AYRI yerde ÜÇ FARKLI şey
# söylüyordu — tuple (0.05, 0.15), kaydın kendi 'source' künyesi 0.05-0.25,
# modül başlığı 0.05-0.25. Varsayılan (0.15) 'bandın konservatif üst ucu'
# diye etiketliyken künyesinin üst ucunun %60'ıydı, yani erozyonu EKSİK
# tahmin ediyordu (itki/basıncı fazla gösteren yön) ve künyedeki bandın
# içinde kalan 0.20 mm/s gibi meşru bir kullanıcı katsayısına katı motor
# 'warn.solid.throat_erosion_coeff_off_band' uyarısı basıyordu. Depoda
# bandı ATFEDİLMİŞ tek sayı Geisler'in 0.05-0.25'idir; bant ona çekildi,
# varsayılan artık bandın üst ucundan TÜRETİLİYOR (elle yazılmıyor).
# D27/OH-D25-27 + OH-D24-11 (b,c) (2026-09-08): iki düzeltme.
#  (1) GRAFİT — künye Geisler'i "AIAA" diye anıyordu; kaynağın yayım yeri
#      JANNAF'tır (Thakre & Yang 2008, kaynakça [6]). Bandın sayısı da
#      deponun kendi dizgesiydi. Tablo 8'in ÖLÇÜLEN değerleri (BATES, bulk
#      grafit, p_t = 6,9 MPa, %15..%27 Al) alt uçta 0.069, üst uçta 0.353
#      mm/s'dir; deponun eski üst ucu (0.25) ölçülenin %70,8'iydi. Varsayılan
#      a_ref bandın üst ucundan türediği için erozyon EKSİK tahmin ediliyor,
#      yani itki/basınç FAZLA gösteriliyordu — GÜVENSİZ yön. Ölçülen band
#      künyesiyle birlikte yerine kondu; varsayılan +%41,2 arttı.
#  (2) C-C — eski (0.02, 0.10) tuple'ı depo-içi kestirimdi ve depodaki TEK
#      atfedilebilir C-C ölçümüyle ÇELİŞİYORDU: Borie ve ark. 4,9 MPa'da
#      0.139 mm/s ölçmüş; modelin KENDİ yasasıyla 70 bar'a taşınınca
#      0.185 mm/s eder, yani deponun üst ucu ölçülenin %54,1'iydi (yine
#      güvensiz yön). Kaynaksız sayı SÖKÜLDÜ. Tek ölçüm noktası bir BAND
#      vermez: 'a_ref_band_mm_s' artık None (bant-dışı uyarısının C-C'de
#      dayanağı yoktur, ateşlenmez) ve varsayılan ATFEDİLMİŞ TEK-NOKTA
#      ÇAPASINDAN türetilir. Literatür notu:
#      docs/arastirma/fizik/bogaz-erozyonu-grafit-cc-bandi.md
# --- Modelin referans noktası (TEK TANIM NOKTASI) --------------------------
# Referans basıncı ve üs iki yerde yazılmasın: hem sınıfın imza
# varsayılanları hem de aşağıdaki tek-nokta çapası bu adlardan okur.
THROAT_EROSION_PC_REF_BAR = 70.0


def _exponent_from_citation(kunye):
    """Basınç üssünü VE geçerlilik aralığını künye metninden okur.

    D28/OH-D27-15. Bandın (``_band_from_citation``) ve tek-nokta çapasının
    (``_anchor_from_citation``) kuralının ÜSTEKİ karşılığı: sayı künyesinden
    AYRILAMAZ, üssü değiştirmek ancak atfını da değiştirerek mümkündür.
    D28'e kadar üs kaynaksız bir literaldi (0,8, Bartz'ın ısı transferi
    üssü) ve erozyon literatürüne atfı yoktu.

    Döndürür: ``(n, (pc_alt_bar, pc_ust_bar))``. Aralık kaynağın ÖLÇTÜĞÜ
    basınç aralığıdır; dışında yasa EKSTRAPOLASYONDUR ve öyle beyan edilir
    (``ThroatErosionModel.exponent_extrapolated``).
    """
    m = re.search(r'exponent n = (\d+\.\d+)', kunye)
    if not m:
        raise ValueError(f"künyede üs yok: {kunye!r}")
    n = float(m.group(1))
    aralik = re.search(r'p_t = (\d+\.\d+)\s*-\s*(\d+\.\d+)\s*MPa', kunye)
    if not aralik:
        raise ValueError(f"künyede geçerlilik aralığı yok: {kunye!r}")
    alt = float(aralik.group(1)) * 10.0
    ust = float(aralik.group(2)) * 10.0
    if not (n > 0.0 and 0.0 < alt < ust):
        raise ValueError(f"künyedeki üs/aralık geçersiz: {kunye!r}")
    return n, (alt, ust)


THROAT_EROSION_PRESSURE_EXPONENT_CITATION = (
    'Thakre & Yang, J. Prop. Power 24(4) 2008 (DOI 10.2514/1.34946), '
    'Fig. 14 and Conclusions: the graphite throat erosion rate varies '
    'LINEARLY with chamber pressure, i.e. exponent n = 1.0, over the '
    'pressure range the study covers, p_t = 6.9-45.0 MPa, for both '
    'metallized (diffusion-controlled) and nonmetallized '
    '(kinetics-controlled) AP/HTPB. The Bartz (1957) h_g ~ Pc^0.8 scaling '
    'is the convective-transport limb alone, NOT the exponent of the '
    'erosion law')
(THROAT_EROSION_PRESSURE_EXPONENT,
 THROAT_EROSION_EXPONENT_VALID_PC_BAR) = _exponent_from_citation(
     THROAT_EROSION_PRESSURE_EXPONENT_CITATION)


# --- Bantların TEK TANIM NOKTASI ------------------------------------------
# Her bant BURADA bir kez yazılır; kayıt sözlüğü ve künye metinleri bu
# adlardan okur. Bandın üst ucu aynı zamanda varsayılan a_ref'tir (aşağıdaki
# türetme döngüsü) — ikinci bir literal YOKTUR.
#
# ATIF DURUMU (band_attributed): bandın sayısal değeri bir kaynağa
# atfedilebiliyor mu? Grafit → EVET (Geisler). C-C → HAYIR: depodaki hiçbir
# künye C-C için sayısal bant vermiyor; (0.02, 0.10) depo-içi mühendislik
# kestirimidir ve öyle beyan edilir (sayı DEĞİŞTİRİLMEDİ — kaynaksız bir
# sayıyı başka kaynaksız bir sayıyla değiştirmek onarım değildir; bu, ayrı
# bir kalem olarak raporlanmıştır).
# ^ D19'un durumudur; D27'de AŞILDI (aşağıdaki D27 notu): "ayrı kalem"
#   OH-D24-11 (b) olarak açıldı, kaynaksız (0.02, 0.10) SÖKÜLDÜ ve C-C
#   artık band yayımlamıyor; katsayı atfedilmiş tek ölçüme çapalı.
def _band_from_citation(kunye):
    """Sayısal bandı KÜNYE METNİNDEN okur — sayı künyesinden ayrılamasın.

    D19/P2B4-09'un kökü: bant bir yerde tuple, bir yerde künye metni, bir
    yerde modül başlığı olmak üzere ÜÇ KEZ yazılıydı ve üçü ayrışmıştı.
    Sayının tek tanım noktası artık künyenin KENDİSİDİR: bandı değiştirmek
    ancak atfı da değiştirerek mümkündür.
    """
    m = re.search(r'(\d+\.\d+)\s*-\s*(\d+\.\d+)\s*mm/s', kunye)
    if not m:
        raise ValueError(f"künyede sayısal bant yok: {kunye!r}")
    return (float(m.group(1)), float(m.group(2)))


GRAPHITE_A_REF_BAND_CITATION = (
    'Geisler JANNAF 1978 BATES bulk-graphite band 0.069-0.353 mm/s '
    '(measured, Thakre & Yang, J. Prop. Power 24(4) 2008, Table 8, '
    'p_t = 6.9 MPa, 15-27% Al AP/HTPB)')
GRAPHITE_A_REF_BAND_MM_S = _band_from_citation(GRAPHITE_A_REF_BAND_CITATION)


def _anchor_from_citation(kunye):
    """Tek-nokta çapayı KÜNYE METNİNDEN okur ve referans basınca taşır.

    Bandın kuralının (``_band_from_citation``) tek-nokta karşılığı: sayı
    künyesinden AYRILAMAZ. Ölçüm kendi basıncında verilir; modelin KENDİ
    yasasıyla (``(Pc_ref/Pc_olcum)^exponent``) referans basınca taşınır —
    ikinci bir ölçekleme kuralı yazılmaz.
    """
    m = re.search(r'(\d+\.\d+)\s*mm/s\s*at\s*(\d+\.\d+)\s*MPa', kunye)
    if not m:
        raise ValueError(f"künyede tek-nokta ölçüm yok: {kunye!r}")
    hiz = float(m.group(1))
    pc_olcum_bar = float(m.group(2)) * 10.0
    if not (hiz > 0.0 and pc_olcum_bar > 0.0):
        raise ValueError(f"künyedeki tek-nokta ölçüm geçersiz: {kunye!r}")
    return hiz * (THROAT_EROSION_PC_REF_BAR
                  / pc_olcum_bar) ** THROAT_EROSION_PRESSURE_EXPONENT


# C-C: depoda C-C için SAYISAL BAND veren künye yoktur ve olmayan bandın
# yerine depo-içi bir kestirim yazmak (eski hâli) sayı uydurmaktır. Elde
# atfedilebilir TEK ölçüm noktası vardır; band None kalır, çapa ondan gelir.
CARBON_CARBON_A_REF_BAND_MM_S = None
CARBON_CARBON_A_REF_BAND_CITATION = None   # BAND yok: tek nokta band değildir
CARBON_CARBON_A_REF_ANCHOR_CITATION = (
    'Borie et al. (SEP) carbon-carbon throat recession 0.139 mm/s at '
    '4.9 MPa (measured, Thakre & Yang, J. Prop. Power 24(4) 2008, Table 5 '
    'and Fig. 18); a SINGLE measured point, not a band, scaled to the '
    "model reference pressure by the model's own law")

THROAT_EROSION_MATERIALS = {
    'graphite': {
        'db_key': 'graphite',            # materials_db kaydı (görünen ad için)
        'display': 'Graphite (isostatic, nozzle insert grade)',
        'a_ref_band_mm_s': GRAPHITE_A_REF_BAND_MM_S,
        # 'a_ref_default_mm_s' ELLE YAZILMAZ — bandın üst ucundan türetilir
        # (dosyanın altındaki türetme döngüsü). Tek tanım noktası: bant.
        'recommended': True,
        'band_source': GRAPHITE_A_REF_BAND_CITATION,
        'band_attributed': True,
        'source': ('Thakre & Yang 2008 (J. Prop. Power 24-4), Table 8: '
                   'measured steady-state throat recession of bulk graphite '
                   'in BATES motors at 6.9 MPa, spanning 15-27% aluminium '
                   'AP/HTPB; '
                   f'{GRAPHITE_A_REF_BAND_CITATION}. Band approximate '
                   '(scatter of order 50% is normal).'),
    },
    'carbon_carbon': {
        'db_key': None,                  # materials_db'de kayıt yok
        'display': 'Carbon-carbon composite (C-C)',
        'a_ref_band_mm_s': CARBON_CARBON_A_REF_BAND_MM_S,   # None: band yok
        # 'a_ref_default_mm_s' ELLE YAZILMAZ — band varsa bandın üst ucundan,
        # yoksa atfedilmiş tek-nokta çapasından türetilir (aşağıdaki döngü).
        'recommended': True,
        'band_source': CARBON_CARBON_A_REF_BAND_CITATION,
        'band_attributed': False,
        # 'a_ref_anchor_mm_s' de ELLE YAZILMAZ — künyeden okunur.
        'anchor_source': CARBON_CARBON_A_REF_ANCHOR_CITATION,
        'anchor_attributed': True,
        'source': ('Thakre & Yang 2008, Table 5 / Fig. 18: a single measured '
                   'C-C throat recession point (Borie et al., SEP), scaled '
                   'to the model reference pressure. NOTE: no source in this '
                   'repository gives a NUMERIC BAND for C-C, so no band is '
                   'published and the off-band check is not applied to C-C; '
                   'the coefficient is anchored on ONE measurement and its '
                   'scatter is unknown. NOTE 2: the claim that dense C-C '
                   'erodes measurably less than bulk graphite is NOT '
                   'supported by these numbers - at comparable aluminium '
                   'loading the cited C-C point is the higher of the two. '
                   'Test data required.'),
    },
    'steel': {
        'db_key': 'steel',
        'display': 'Steel (uncooled)',
        'a_ref_band_mm_s': None,
        # varsayılan yok (bant yok) — türetme döngüsü None yazar
        'recommended': False,
        'band_source': None,
        'band_attributed': False,
        'warning': ('Uncooled steel throat is NOT RECOMMENDED: wall softens '
                    'and melts far below flame temperature (see materials_db '
                    'max_service_temp); the empirical pressure-scaled erosion '
                    'law r = a_ref*(Pc/Pc_ref)^n is not valid for melting '
                    'metals. Use graphite or C-C, '
                    'or supply a test-derived a_ref explicitly.'),
        'source': 'Engineering judgement; no validated coefficient.',
    },
    'copper': {
        'db_key': 'copper',
        'display': 'Copper (uncooled heat sink)',
        'a_ref_band_mm_s': None,
        # varsayılan yok (bant yok) — türetme döngüsü None yazar
        'recommended': False,
        'band_source': None,
        'band_attributed': False,
        'warning': ('Uncooled copper throat is NOT RECOMMENDED for sustained '
                    'burns: copper is a short-duration heat sink only '
                    '(melting point 1358 K, materials_db); the empirical '
                    'pressure-scaled erosion law r = a_ref*(Pc/Pc_ref)^n is '
                    'not valid for melting metals. '
                    'Use graphite or C-C, or supply a test-derived a_ref '
                    'explicitly.'),
        'source': 'Engineering judgement; no validated coefficient.',
    },
}

# --- Varsayılan a_ref'in TÜRETİLMESİ (elle yazılmaz) -----------------------
# Kuralı modül başlığı zaten söylüyordu: "Varsayılan = bandın KONSERVATİF
# (üst) ucu". D19/P2B4-09'a kadar bu kural YORUMDU ve grafitte tutmuyordu
# (bant üst ucu 0.15 iken künye 0.25 diyordu). Artık kural KOD:
# a_ref_default_mm_s hiçbir kayıtta elle yazılmaz, bandın üst ucundan
# üretilir; bandı değiştiren varsayılanı da otomatik değiştirir, ikisi bir
# daha AYRIŞAMAZ (TEK KAYNAK — CLAUDE.md k.11).
# D27: kural GENELLEŞTİ — bandı olmayan ama ATFEDİLMİŞ tek ölçüm noktası
# olan malzemede (C-C) varsayılan o çapadan gelir. Çapa da elle yazılmaz:
# sayı künyesinden okunur (_anchor_from_citation), böylece bir katsayıyı
# değiştirmek ancak atfını da değiştirerek mümkün olur.
for _rec in THROAT_EROSION_MATERIALS.values():
    for _yasak in ('a_ref_default_mm_s', 'a_ref_anchor_mm_s'):
        if _yasak in _rec:
            raise AssertionError(
                f"{_yasak} elle yazılamaz: künyeden türetilir")
    _band = _rec.get('a_ref_band_mm_s')
    _capa_kunye = _rec.get('anchor_source')
    _capa = (_anchor_from_citation(_capa_kunye) if _capa_kunye else None)
    _rec['a_ref_anchor_mm_s'] = _capa
    _rec['a_ref_default_mm_s'] = (float(_band[1]) if _band
                                  else (float(_capa) if _capa else None))
del _rec, _band, _capa, _capa_kunye, _yasak


# Yaygın ad/alias'lar → erozyon tablosu anahtarı
_EROSION_ALIASES = {
    'c-c': 'carbon_carbon', 'c_c': 'carbon_carbon', 'cc': 'carbon_carbon',
    'carbon-carbon': 'carbon_carbon', 'carboncarbon': 'carbon_carbon',
    'steel_4130': 'steel', 'ss_304': 'steel', 'ss_316': 'steel',
    'stainless': 'steel', 'stainless_304': 'steel', 'stainless_316': 'steel',
    'cucrzr': 'copper', 'cu_cr_zr': 'copper', 'cu': 'copper',
}


class ThroatErosionModel:
    """Ampirik boğaz erozyon modeli:  ṙ = a_ref·(Pc/Pc_ref)^exponent.

    Model-değiştirilebilir API: TransientBallistics kuplajı yalnız
    ``rate_m_s(Pc_pa)`` çağırır — aynı imzayı sağlayan HERHANGİ bir nesne
    (ör. Thakre-Yang tarzı kinetik model, test-verisi interpolasyonu)
    ``erosion_model=`` argümanıyla takılabilir.

    Varsayılan katsayı ve üs için kaynaklar modül başındaki blokta
    (Thakre & Yang 2008 = üs ve bantlar; Bartz 1957 = yalnız taşınım ucu;
    Geisler 1978 = grafit bandı). Bantlar approximate'tir. Üs künyesiyle
    birlikte yayımlanır (``describe()['exponent_source']``, D28).
    """

    def __init__(self, a_ref_mm_s,
                 pc_ref_bar=THROAT_EROSION_PC_REF_BAR,
                 exponent=THROAT_EROSION_PRESSURE_EXPONENT,
                 material='custom', material_display=None,
                 a_ref_band_mm_s=None, band_source=None,
                 band_attributed=False,
                 anchor_source=None, anchor_attributed=False,
                 exponent_source=None, exponent_valid_pc_bar=None,
                 source='user-supplied coefficient', warnings=None):
        a = float(a_ref_mm_s)
        if not np.isfinite(a) or a <= 0.0:
            raise ValueError("a_ref_mm_s must be a positive finite number")
        pc_ref = float(pc_ref_bar)
        if not np.isfinite(pc_ref) or pc_ref <= 0.0:
            raise ValueError("pc_ref_bar must be a positive finite number")
        self.a_ref_mm_s = a
        self.pc_ref_bar = pc_ref
        self.exponent = float(exponent)
        # Üssün KÜNYESİ (D28/OH-D27-15). Katsayının künyesi (band/çapa) D19
        # ve D27'de bağlanmıştı ama ÜS künyesiz yayımlanıyordu; okuyucu
        # 0,8'in nereden geldiğini modelden öğrenemiyordu. Kural katsayıyla
        # aynı: kullanıcı üssü DEĞİŞTİRDİYSE kaynağın atfı ona GEÇMEZ —
        # atıfsız üs 'exponent_attributed = False' ile beyan edilir ve
        # geçerlilik aralığı da yayımlanmaz (bilinmiyor).
        if (exponent_source is None
                and self.exponent == THROAT_EROSION_PRESSURE_EXPONENT):
            exponent_source = THROAT_EROSION_PRESSURE_EXPONENT_CITATION
            if exponent_valid_pc_bar is None:
                exponent_valid_pc_bar = THROAT_EROSION_EXPONENT_VALID_PC_BAR
        self.exponent_source = exponent_source
        self.exponent_attributed = bool(exponent_source)
        self.exponent_valid_pc_bar = (tuple(exponent_valid_pc_bar)
                                      if exponent_valid_pc_bar else None)
        self.material = str(material)
        self.material_display = material_display or str(material)
        self.a_ref_band_mm_s = (tuple(a_ref_band_mm_s)
                                if a_ref_band_mm_s else None)
        self.band_source = band_source
        self.band_attributed = bool(band_attributed)
        # Band YOKKEN katsayının nereden geldiği (tek-nokta ölçüm çapası):
        # 'band_attributed False' tek başına okunursa katsayı kaynaksız
        # sanılır — D27/OH-D24-11 (b). Çapa da adıyla yayımlanır.
        self.anchor_source = anchor_source
        self.anchor_attributed = bool(anchor_attributed)
        self.source = source
        self.warnings = list(warnings or [])

    @classmethod
    def for_material(cls, material, a_ref_mm_s=None):
        """Malzeme adından model kurar (tablo + materials_db görünen adı).

        Önerilmeyen malzemelerde (çelik/bakır soğutmasız) a_ref override'ı
        verilmemişse ValueError yükseltir; override verilirse model kurulur
        ama 'not recommended' uyarısı taşınır.
        """
        key = str(material).strip().lower().replace(' ', '_')
        key = _EROSION_ALIASES.get(key, key)
        if key not in THROAT_EROSION_MATERIALS:
            raise ValueError(
                f"No throat erosion data for material '{material}'. "
                f"Available: {sorted(THROAT_EROSION_MATERIALS)} "
                f"(or pass a_ref_mm_s for a custom material)")
        rec = THROAT_EROSION_MATERIALS[key]

        display = rec['display']
        if rec.get('db_key'):
            try:
                # Merkezi malzeme DB'sindeki görünen adı kullan (tek kaynak).
                display = get_material(rec['db_key'])['name']
            except KeyError:
                pass

        warns = []
        if not rec['recommended']:
            warns.append(rec['warning'])
            if a_ref_mm_s is None:
                raise ValueError(
                    f"Throat material '{key}': {rec['warning']}")
        a = a_ref_mm_s if a_ref_mm_s is not None else rec['a_ref_default_mm_s']
        return cls(a, material=key, material_display=display,
                   a_ref_band_mm_s=rec.get('a_ref_band_mm_s'),
                   band_source=rec.get('band_source'),
                   band_attributed=rec.get('band_attributed', False),
                   anchor_source=rec.get('anchor_source'),
                   anchor_attributed=rec.get('anchor_attributed', False),
                   source=rec['source'], warnings=warns)

    def exponent_extrapolated(self, pc_bar):
        """Verilen basınç, üssün kaynağının ÖLÇTÜĞÜ aralığın dışında mı?

        D28/OH-D27-15. Üç değerli: ``True``/``False``, ve üssün atfı yoksa
        (kullanıcı üssü) ``None`` — aralık bilinmediğinde "hayır" demek
        yanlış olurdu (SESSİZ VARSAYIM YASAĞI).
        """
        band = self.exponent_valid_pc_bar
        if not band:
            return None
        pc = float(pc_bar)
        return not (band[0] <= pc <= band[1])

    def rate_mm_s(self, pc_bar):
        """Erozyon hızı [mm/s] (yarıçapta gerileme), Pc [bar]."""
        pc = float(pc_bar)
        if pc <= 0.0:
            return 0.0
        return self.a_ref_mm_s * (pc / self.pc_ref_bar) ** self.exponent

    def rate_m_s(self, pc_pa):
        """Erozyon hızı [m/s] (yarıçapta gerileme), Pc [Pa]."""
        return self.rate_mm_s(float(pc_pa) / 1e5) / 1000.0

    def describe(self):
        """JSON-uyumlu model özeti (rapor/endpoint için)."""
        return {
            'model': (f"r_dot = a_ref*(Pc/{self.pc_ref_bar:g} bar)"
                      f"^{self.exponent:g} (empirical)"),
            'a_ref_mm_s': self.a_ref_mm_s,
            'pc_ref_bar': self.pc_ref_bar,
            'exponent': self.exponent,
            'material': self.material,
            'material_display': self.material_display,
            'a_ref_band_mm_s': (list(self.a_ref_band_mm_s)
                                if self.a_ref_band_mm_s else None),
            # Bandın KENDİ künyesi: 'source' iki atıf birden taşıyabildiği
            # için (biri hız sınıfı, biri bant) okuyucu bandın hangisinden
            # geldiğini ayırt edemiyordu — D19/P2B4-09. band_attributed
            # False ise bant hiçbir kaynağa atfedilmemiştir (depo-içi
            # kestirim); bu durum SAKLANMAZ, alan adıyla söylenir.
            'band_source': self.band_source,
            'band_attributed': bool(self.band_attributed),
            # Bandı olmayan ama ölçüme çapalanmış katsayının künyesi
            # (D27): band_attributed False iken bile katsayı atfedilmiş
            # olabilir; okuyucu ikisini ayırt edebilsin.
            'anchor_source': self.anchor_source,
            'anchor_attributed': bool(self.anchor_attributed),
            # ÜSSÜN künyesi (D28/OH-D27-15): 'exponent' D28'e kadar
            # kaynaksız yayımlanıyordu. Geçerlilik aralığı kaynağın ÖLÇTÜĞÜ
            # basınç aralığıdır; dışında yasa ekstrapolasyondur.
            'exponent_source': self.exponent_source,
            'exponent_attributed': bool(self.exponent_attributed),
            'exponent_valid_pc_bar': (list(self.exponent_valid_pc_bar)
                                      if self.exponent_valid_pc_bar
                                      else None),
            'source': self.source,
            'warnings': list(self.warnings),
        }


class TransientBallistics:
    """Boyutlandırılmış bir HybridRocketEngine'i zamanda yürütür."""

    def __init__(self, engine, feed_mode='regulated',
                 tank_temperature=293.15, liquid_fill_fraction=0.85,
                 n_steps=400, t_max_factor=1.6,
                 erosion_enabled=False, throat_material='graphite',
                 erosion_model=None):
        """
        Args:
            engine: calculate() çağrılmış HybridRocketEngine örneği
            feed_mode: 'regulated' | 'blowdown'
            tank_temperature: blowdown başlangıç tank sıcaklığı [K]
            liquid_fill_fraction: tank sıvı doluluk oranı (ullage payı)
            n_steps: nominal yanma süresi için adım sayısı
            t_max_factor: t_max = factor · t_b (blowdown uzayabilir)
            erosion_enabled: True → boğaz erozyonu kuplajı (her adımda d_t
                büyür, Pc/F eğrisi düşer). Varsayılan KAPALI — geriye dönük
                uyum: kapalıyken çözüm eski davranışla bit-özdeştir.
            throat_material: erozyon malzemesi ('graphite' | 'carbon_carbon';
                çelik/bakır soğutmasız → not-recommended, a_ref şart)
            erosion_model: opsiyonel özel model — rate_m_s(Pc_pa) sağlayan
                herhangi bir nesne (verilirse throat_material yok sayılır ve
                erozyon etkinleşir; model-değiştirilebilir API)
        """
        required = ('At', 'epsilon', 'gamma', 'D_port_initial', 'L_grain',
                    'rho_f', 'a', 'n', 'mdot_ox', 'C_star', 'P_c', 'P_a')
        missing = [attr for attr in required
                   if getattr(engine, attr, None) is None]
        if missing:
            raise ValueError(
                f"Motor boyutlandırılmamış görünüyor (calculate() çağrıldı mı?); "
                f"eksik: {missing}")
        if feed_mode not in ('regulated', 'blowdown'):
            raise ValueError("feed_mode 'regulated' ya da 'blowdown' olmalı")

        self.e = engine
        self.feed_mode = feed_mode
        self.dt = engine.t_b / n_steps
        self.t_max = t_max_factor * engine.t_b

        # Nozul sabitleri (sabit geometri): P_e/P_c oranı ve momentum C_F'i
        g = float(engine.gamma)
        eps = float(engine.epsilon)
        self._pe_ratio = self._exit_pressure_ratio(g, eps)
        self._cf_momentum = self._momentum_cf(g, self._pe_ratio)
        # --- ÖH D22 / OH-D21-02 · MOTORUN C_F SÖZLEŞMESİ TEK KAYNAK ----
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/D22/hibrit/a1/once.json, 3000 N /
        # 30 bar / O/F=6 / N2O-HTPB): t=0 itkisi 3056,0109 N ⟷ tasarım
        # 3000,0000 N (+%1,8670), iki bağımsız kökten:
        #   (a) KAYIP KÜMESİ TAŞINMIYORDU. D20/B1-12'den beri manşet C_F
        #       kayıpsız C_F'i η_sürtünme × η_iki-faz × η_kinetik ile
        #       çarpar (ölçülen çarpım 0,9817089); geçici seri yalnız
        #       diverjans çarpanını uyguluyordu -> +%1,8632 = 1/çarpım.
        #   (b) λ ÖLÜ BİR ALANDAN OKUNUYORDU. ``engine.lambda_divergence``
        #       hibrit motorda HİÇ TANIMLI DEĞİL (yalnız sıvı motorun
        #       nozzle_angles sözlüğünde bir ANAHTAR olarak var); getattr
        #       her koşuda None döndüğü için katalog sabiti 0,983
        #       kullanılıyordu. Motorun kendi λ'sı ise D21/P15B1-04'ten beri
        #       konturun geometrik değeridir (``lambda_eff``, ε'ye bağlı):
        #       0,983 / 0,9829629 = +%0,0038 — kalan farkın tamamı budur.
        # İkisi de aynı kusurun ayaklarıdır: geçici seri, tasarım noktasının
        # yayımladığı C_F sözleşmesini taşımıyordu.
        self._lambda = self._resolve_lambda(engine)
        self._loss_product, self._loss_set = self._resolve_loss_set(engine)
        # Boğaz debi katsayısı — tasarımla AYNI sayı, tek adlandırılmış yerden
        self._cd_nozzle = NOZZLE_DISCHARGE_COEFFICIENT

        # --- ÖH D33-2 · OH-UC-04 — REGÜLELİ KİPTE TANK DURUMUNUN ROLÜ ---
        #
        # ÖLÇÜLDÜ (``docs/scofield/raw/OH/D33-2/motorlar/a1/once.json``,
        # OH-UC-04; /api/transient-analysis, 1 kN / 20 bar HTPB-N2O):
        # ``feed_mode='regulated'`` ile ``tank_temperature`` 250 K ve
        # 293,15 K yanıtları **BİT-AYNI** (aynı sha256, 63.794 bayt);
        # T ile oynayan sayısal yaprak **0/19**. Yani kullanıcının
        # gönderdiği tank sıcaklığı bu kipte HAYALET bir alandı: kabul
        # ediliyor, hiçbir yere girmiyor ve yanıtta bunu söyleyen TEK BİR
        # alan yoktu (ölçüldü: tank sıcaklığından söz eden künye sayısı 0).
        #
        # Bu bir hesap hatası DEĞİL, sözleşme boşluğudur: regüleli kipte
        # ṁ_ox tasarım değerinde SABİT TUTULUR (modül künyesi, satır ~24),
        # yani tank durumu modele hiç girmez. Ama modelin dışında kalan
        # fizik gerçektir ve büyüklüğü ölçülebilir: gerçek bir regülatör
        # ullage BASINCINI sabitler, iticinin YOĞUNLUĞUNU değil; enjektör
        # debisi ṁ = C_d·A·√(2·ρ·ΔP) bağıntısıyla ρ(T)'ye bağlı kalır
        # (Sutton, "Rocket Propulsion Elements" 9. baskı, basınç-beslemeli
        # sistemler; Huzel & Huang, NASA SP-125, Böl. 5). Boyut denetimi:
        # C_d[-]·A[m²]·√(kg/m³ · kg/(m·s²)) = m²·kg/(m²·s) = kg/s ✓.
        # Dolayısıyla ṁ ∝ √ρ ve duyarlılık ÖLÇÜLEBİLİR — burada uydurma
        # bir sayı yazılmaz, AYNI özellik modelinden (blowdown yolunun
        # kullandığı ``N2OTankBlowdown.props.rho_l``, tek kaynak) okunur.
        self._tank_state_role = None
        if feed_mode == 'regulated':
            rho_duyarlilik = None
            duyarlilik_gerekce = None
            try:
                # TEK KAYNAK: referans sıcaklık ikinci kez yazılmaz; hibrit
                # motorun ``TANK_TEMPERATURE_DEFAULT_K`` sabiti ithal edilir.
                # İthal GEÇ yapılır (modül düzeyinde döngüsel import riski).
                from hrma.engines.hybrid_rocket_engine import (
                    TANK_TEMPERATURE_DEFAULT_K as _T_REF,
                )
                _props = N2OTankBlowdown.from_oxidizer_mass(
                    oxidizer_mass=float(engine.m_ox),
                    initial_temperature=float(tank_temperature),
                    liquid_fill_fraction=float(liquid_fill_fraction)).props
                _rho_t = float(_props.rho_l(float(tank_temperature)))
                _rho_ref = float(_props.rho_l(_T_REF))
                if (np.isfinite(_rho_t) and _rho_t > 0.0
                        and np.isfinite(_rho_ref) and _rho_ref > 0.0):
                    rho_duyarlilik = {
                        'tank_temperature_K': float(tank_temperature),
                        # ÖH V3 taban-b: anahtar ``reference_tank_temperature_K``
                        # (eski ``reference_temperature_K``): o ad yakıt-termal
                        # kaydının karar-4 künye alanıdır (stability/
                        # fuel_thermal.py) ve yayımlanmadığı bekçiyle ölçülür
                        # (test_fazb_serilestirici_esligi S3); buradaki alan
                        # tankın referans SICAKLIĞIDIR, kardeşi
                        # ``tank_temperature_K`` ile aynı adlandırma. Değer aynı.
                        'reference_tank_temperature_K': float(
                            _T_REF),
                        'liquid_density_kg_m3': _rho_t,
                        'reference_liquid_density_kg_m3': _rho_ref,
                        'implied_mdot_factor_sqrt_rho_ratio': float(
                            np.sqrt(_rho_t / _rho_ref)),
                        '_basis': (
                            'Measured with the SAME oxidizer property model '
                            'the blowdown path uses (single source), not a '
                            'second correlation. mdot = Cd*A*sqrt(2*rho*dP) '
                            'at a regulator-held dP, so the factor by which '
                            'a real regulated feed would differ from the '
                            'reference-temperature run is sqrt(rho(T)/'
                            'rho(T_ref)). It is NOT applied to any published '
                            'number - this run prescribes mdot_ox.'),
                    }
                else:
                    duyarlilik_gerekce = (
                        'The oxidizer property model returned a '
                        'non-physical liquid density at this temperature, '
                        'so no sensitivity factor is published.')
            except Exception as exc:
                duyarlilik_gerekce = (
                    'The oxidizer property model could not be evaluated at '
                    f'this tank temperature ({type(exc).__name__}: '
                    f'{str(exc)[:120]}), so no sensitivity factor is '
                    'published rather than implying the effect is zero.')
            self._tank_state_role = {
                'tank_temperature_K_received': float(tank_temperature),
                'liquid_fill_fraction_received': float(liquid_fill_fraction),
                'used_by_this_model': False,
                'reason': (
                    "In feed_mode='regulated' the oxidizer mass flow is "
                    'PRESCRIBED at its design value, so no tank state '
                    '(temperature, fill fraction, liquid density, vapour '
                    'pressure) enters the solution. The tank temperature you '
                    'supplied was accepted and is echoed here, but it '
                    'changes NO published number: the response is '
                    'bit-identical for every accepted tank temperature. Use '
                    "feed_mode='blowdown' to let the tank state drive the "
                    'flow.'),
                'not_modelled': (
                    'A real pressure regulator holds the ullage PRESSURE, '
                    'not the propellant density. The injector flow '
                    'mdot = Cd*A*sqrt(2*rho*dP) therefore keeps a rho(T) '
                    'dependence that this prescribed-flow model drops '
                    '(Sutton, Rocket Propulsion Elements 9th ed., '
                    'pressure-fed feed systems; Huzel & Huang, NASA SP-125, '
                    'Ch. 5). The size of what is dropped is measured in '
                    'regulated_flow_temperature_sensitivity.'),
                'regulated_flow_temperature_sensitivity': rho_duyarlilik,
                'regulated_flow_temperature_sensitivity_not_measured_reason':
                    duyarlilik_gerekce,
            }

        # Blowdown tankı + enjektör kalibrasyonu
        self.tank = None
        self._K_inj = None
        if feed_mode == 'blowdown':
            self.tank = N2OTankBlowdown.from_oxidizer_mass(
                oxidizer_mass=float(engine.m_ox),
                initial_temperature=tank_temperature,
                liquid_fill_fraction=liquid_fill_fraction)
            P_tank0 = self.tank.pressure                    # Pa
            Pc0 = float(engine.P_c) * 1e5                   # Pa
            dP0 = P_tank0 - Pc0
            if dP0 <= 0:
                raise ValueError(
                    f"Tank basıncı ({P_tank0/1e5:.1f} bar) tasarım kamara "
                    f"basıncının ({engine.P_c:.1f} bar) altında — blowdown "
                    f"beslemesi mümkün değil. Kamara basıncını düşürün ya da "
                    f"tankı ısıtın.")
            rho0 = self.tank.props.rho_l(tank_temperature)
            # Etkin C_d·A: t=0'da tasarım debisini gerçek ΔP'de verir
            self._K_inj = float(engine.mdot_ox) / np.sqrt(2.0 * rho0 * dP0)

        # Boğaz erozyonu (Dalga 3): varsayılan KAPALI — geriye dönük uyum.
        # erosion_model verilirse malzeme tablosuna bakılmaz (rate_m_s(Pc_pa)
        # sağlayan her nesne kabul edilir — model-değiştirilebilir API).
        self.erosion = None
        if erosion_model is not None:
            self.erosion = erosion_model
        elif erosion_enabled:
            self.erosion = ThroatErosionModel.for_material(throat_material)

        # Kaç adımda C_F ayrılma tabanına oturdu (kalem 3). Sıfırdan büyükse
        # eğrinin bir bölümü ekli-akış modelinin GEÇERLİLİK ARALIĞI DIŞINDA
        # geçmiştir ve bu sonuçta beyan edilir.
        self._separation_limited_steps = 0
        # Ekli-akış ifadesi negatife düşüp sıfıra kırpılan adım sayısı.
        self._negative_cf_steps = 0
        # ÖH D21 a1 (P2B4-11): çözücü TEK KULLANIMLIKTIR ve bunu artık
        # SÖYLER. Ayrıntı `solve()` künyesinde.
        self._solved = False

    # ---------------- motor sözleşmesi (ÖH D22 / OH-D21-02) -------------

    @staticmethod
    def _resolve_lambda(engine):
        """Diverjans verimi λ — motorun KENDİ değeri, tek kaynak.

        Sıra: ``lambda_eff`` (hibrit motorun çözdüğü kontur geometrisi,
        D21/P15B1-04'ten beri panelin kullandığı sayının kendisi) ->
        ``lambda_divergence`` (ördek-tipli çağıranlar için). İkisi de yoksa
        SAYI UYDURULMAZ: hangi alanın eksik olduğunu söyleyen bir hata
        atılır (fail-closed). Eskiden burada nozul tipine göre yazılmış bir
        katalog sözlüğü vardı; o sözlük hem ikinci bir tanım noktasıydı
        (hrma.constants.LAMBDA_*) hem de fiilen HER koşuda devreye giriyordu.
        """
        for ad in ('lambda_eff', 'lambda_divergence'):
            deger = getattr(engine, ad, None)
            try:
                deger = float(deger)
            except (TypeError, ValueError):
                continue
            if np.isfinite(deger) and 0.0 < deger <= 1.0:
                return deger
        raise ValueError(
            "The engine publishes no divergence efficiency: neither "
            "'lambda_eff' nor 'lambda_divergence' holds a finite value in "
            "(0, 1]. The transient thrust coefficient is not built on an "
            "invented catalogue constant; size the engine first "
            "(HybridRocketEngine.calculate) so that lambda_eff is resolved.")

    @staticmethod
    def _resolve_loss_set(engine):
        """(çarpım, künye) — manşet C_F'in taşıdığı kayıp kümesi.

        Motor kayıp kümesini ``headline_loss_set`` altında yayımlar
        (D20/B1-12). Üç durum vardır ve üçü de AÇIKÇA ayrılır:
          * ``loss_product`` sonlu bir sayı -> geçici seri AYNI çarpanı
            uygular (tek kaynak);
          * ``loss_product is None`` -> kullanıcı ``thrust_coefficient``
            vermiştir ve motor kümeyi ikinci kez uygulamaz; geçici seri de
            uygulamaz (çarpan 1,0, künyede gerekçesiyle);
          * alanın kendisi yoksa -> FAIL-CLOSED. Sessizce 1,0 varsaymak,
            tasarım noktasıyla %1,9 ayrışan bir itki eğrisi yayımlamak
            demektir; bu kalemin kusuru tam olarak buydu.

        Kayıp kümesi tasarım noktasında çözülür ve yörünge boyunca SABİT
        tutulur: η_kinetik gerçekte P_c'ye de bağlıdır (t_res ∝ 1/P_c,
        τ_kimya ∝ P_c^-2), ama onu her adımda yeniden çözmek denge yanma
        çözücüsünü adım başına çağırmak demektir. Model bunu İDDİA ETMEZ —
        kapsam ``loss_set.scope`` alanında yazılıdır.
        """
        kume = getattr(engine, 'headline_loss_set', None)
        if not isinstance(kume, dict) or 'loss_product' not in kume:
            raise ValueError(
                "The engine publishes no headline loss set "
                "('headline_loss_set.loss_product'), so the transient thrust "
                "coefficient cannot carry the same loss set the design point "
                "carries. No silent fallback is applied: size the engine "
                "first (HybridRocketEngine.calculate).")
        carpim = kume.get('loss_product')
        if carpim is None:
            return 1.0, {
                'loss_product': 1.0,
                'source': 'user_supplied_thrust_coefficient',
                'scope': ('the engine used a user-supplied thrust '
                          'coefficient, so the loss set is NOT applied a '
                          'second time on top of it - here either'),
            }
        carpim = float(carpim)
        if not (np.isfinite(carpim) and carpim > 0.0):
            raise ValueError(
                f"The engine's headline loss product is not a usable number "
                f"({carpim!r}); no transient thrust curve is published for "
                f"this operating point.")
        return carpim, {
            'loss_product': carpim,
            'friction_efficiency': kume.get('friction_efficiency'),
            'two_phase_efficiency': kume.get('two_phase_efficiency'),
            'kinetic_efficiency': kume.get('kinetic_efficiency'),
            'source': 'engine.headline_loss_set',
            'scope': ('resolved at the design point and held constant along '
                      'the trajectory; the kinetic efficiency also depends '
                      'on chamber pressure (t_res ~ 1/P_c, tau_chem ~ '
                      'P_c^-2, Bray 1959) and that dependence is NOT tracked '
                      'step by step'),
        }

    # ---------------- nozul yardımcıları ----------------

    @staticmethod
    def _exit_pressure_ratio(gamma, eps):
        """Sabit ε için süpersonik dal P_e/P_c oranı (izentropik)."""
        from scipy.optimize import brentq

        def area_ratio(M):
            return (1.0 / M) * ((2.0 / (gamma + 1.0))
                                * (1.0 + (gamma - 1.0) / 2.0 * M * M)) \
                   ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))) - eps

        # Alt sınır 1 DEĞİL 1.0001: alan oranı M=1'de dönüm yapar ve tipik
        # ε > 1 için denklemin İKİ kökü vardır (biri subsonik, biri
        # süpersonik). 1'in kesin üstünde başlayan aralık subsonik dalı
        # dışarıda bırakır; kalan aralıkta fonksiyon kesin monoton artan
        # olduğu için kök tektir. İkisi de Lean ile ispatlandı:
        # HRMA.areaRatio_strictMonoOn, HRMA.bracket_excludes_subsonic
        # (bkz. docs/BICIMSEL_ISPATLAR.md).
        Me = brentq(area_ratio, 1.0001, 50.0)
        return (1.0 + (gamma - 1.0) / 2.0 * Me * Me) ** (-gamma / (gamma - 1.0))

    @staticmethod
    def _momentum_cf(gamma, pe_ratio):
        """C_F'in momentum kısmı (Sutton Eq. 3-30, basınç-itki terimi hariç)."""
        return np.sqrt(2.0 * gamma ** 2 / (gamma - 1.0)
                       * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
                       * (1.0 - pe_ratio ** ((gamma - 1.0) / gamma)))

    @staticmethod
    def _mach_from_pressure_ratio(p_over_p0, gamma):
        """İzentropik p/p0 → Mach (kapalı form). Aralık dışıysa None."""
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

    def _separation_limited_cf(self, Pc_pa, gamma, Pa_pa):
        """Ayrılma istasyonunda kesilmiş lülenin C_F'i — fiziksel ALT SINIR.

        Aşırı genişlemiş lülede sınır tabaka P_e < k·P_a olduğunda ayrılır
        (Summerfield, k = 0,40; sabit hrma/flow/separation.py'de tanımlı).
        Ayrılma istasyonundan sonrası itkiye katkı vermediği için gerçek C_F,
        aynı lülenin O İSTASYONDA kesilmiş hâlinin C_F'inden aşağı inemez.
        Çözülemezse None döner ve taban UYGULANMAZ (sayı uydurulmaz).
        """
        if not (Pa_pa > 0.0 and Pc_pa > 0.0):
            return None
        M_sep = self._mach_from_pressure_ratio(
            SUMMERFIELD_FACTOR_DEFAULT * Pa_pa / Pc_pa, gamma)
        # Ayrılma istasyonu ancak SÜPERSONİK dalda anlamlıdır. M_sep <= 1
        # ise ayrılma noktası boğazın gerisine düşer, yani lüle o basınçta
        # zaten süpersonik akmıyordur — taban uydurulmaz, None döner.
        if M_sep is None or M_sep <= 1.0:
            return None
        eps_sep = self._area_ratio_from_mach(M_sep, gamma)
        if eps_sep is None or not np.isfinite(eps_sep) or eps_sep <= 1.0:
            return None
        try:
            pe_sep = self._exit_pressure_ratio(gamma, eps_sep)
            cfm_sep = self._momentum_cf(gamma, pe_sep)
        except (ValueError, FloatingPointError):
            return None
        cf = (self._lambda * cfm_sep + eps_sep * pe_sep
              - eps_sep * Pa_pa / Pc_pa)
        return float(cf) if np.isfinite(cf) else None

    def _thrust_coefficient(self, Pc_pa, eps=None, pe_ratio=None,
                            cf_momentum=None):
        """C_F(P_c) — manşetin kayıp kümesini TAŞIYAN itki katsayısı.

        ÖH D22 / OH-D21-02: kayıpsız değer ``_thrust_coefficient_lossless``
        ile çözülür, sonra tasarım noktasının uyguladığı AYNI kayıp kümesi
        (η_sürtünme × η_iki-faz × η_kinetik) ile çarpılır. Çarpan tek
        kaynaktır (``engine.headline_loss_set.loss_product``); burada ikinci
        bir kayıp modeli kurulmaz.
        """
        return self._thrust_coefficient_lossless(
            Pc_pa, eps=eps, pe_ratio=pe_ratio,
            cf_momentum=cf_momentum) * self._loss_product

    def _thrust_coefficient_lossless(self, Pc_pa, eps=None, pe_ratio=None,
                                     cf_momentum=None):
        """Kayıpsız C_F(P_c): sabit ε'da yalnız basınç-itki terimi değişir.

        Erozyon açıkken boğaz büyür → ε = A_e/A_t küçülür; çağıran güncel
        (eps, pe_ratio, cf_momentum) üçlüsünü geçirir. None → tasarım
        değerleri (eski davranış; erozyon kapalıyken bit-özdeş yol).

        v2.6.27 B1 (kalem 3) — AYRILMA TABANI. Eski ifadenin hiçbir alt
        sınırı yoktu ve Pc düştükçe ``− ε·P_a/P_c`` terimi sınırsız büyüyordu.
        ÖLÇÜLDÜ (ε = 25, P_a = 1 bar):
            Pc = 20 bar -> C_F = +0,5304
            Pc = 10 bar -> C_F = −0,7196
            Pc =  5 bar -> C_F = −3,2196
            Pc =  1 bar -> C_F = −23,2196
        Yani model, basınç düştükçe lülenin motoru GERİYE ittiğini söylüyordu.
        Gerçekte o rejimde akış çoktan ayrılmıştır ve C_F, ayrılma
        istasyonundaki değerin altına inemez. Taban yalnız ayrılma
        öngörüldüğünde devreye girer; ekli akışta sonuç bit-özdeştir.
        """
        if eps is None:
            eps = float(self.e.epsilon)
            pe_ratio = self._pe_ratio
            cf_momentum = self._cf_momentum
        Pa_pa = float(self.e.P_a) * 1e5
        if not (Pc_pa and np.isfinite(Pc_pa) and Pc_pa > 0.0):
            # Basınç sıfır/negatif/NaN ise C_F tanımsızdır. Eskiden burada
            # sessizce ±inf ya da NaN üretilip itki dizisine akıyordu.
            return 0.0
        cf_ekli = (self._lambda * cf_momentum
                   + eps * pe_ratio - eps * Pa_pa / Pc_pa)
        Pe_pa = pe_ratio * Pc_pa
        if Pa_pa > 0.0 and Pe_pa < SUMMERFIELD_FACTOR_DEFAULT * Pa_pa:
            cf_sep = self._separation_limited_cf(
                Pc_pa, float(self.e.gamma), Pa_pa)
            if cf_sep is not None and cf_sep > cf_ekli:
                self._separation_limited_steps += 1
                return float(max(cf_sep, 0.0))
        if not np.isfinite(cf_ekli):
            return 0.0
        if cf_ekli < 0.0:
            # SON DURAK. Bir roket lülesi aracı GERİYE itemez: negatif C_F
            # her zaman ekli-akış modelinin geçerlilik aralığı dışında
            # uygulanmasının bir eseridir. Sıfıra kırpmak sessiz kalmak
            # DEĞİLDİR: adım sayılır ve sonuçta beyan edilir. Pratikte bu dal
            # yalnız P_c ortam basıncının altına düştüğünde görülür ve solve()
            # o durumda zaten 'chamber_below_ambient' olayıyla durur.
            self._negative_cf_steps += 1
            return 0.0
        return float(cf_ekli)

    # ---------------- ana çözüm ----------------

    def _blowdown_kapanisi(self, D_port, A_port, N_port, At, Pc_tahmin):
        """Blowdown adımında Pc ↔ ṁ_ox yarı-kararlı kapanışının KÖKÜ.

        V301/H-PANEL (NK-9 / NK-50). Denklem:

            g(Pc) = Pc − (ṁ_ox(Pc) + ṁ_f(ṁ_ox)) · c*(O/F) / (C_D·A_t),
            ṁ_ox(Pc) = K·√(2·ρ_l(T_tank)·(P_tank − Pc))   (SPI)

        g, Pc'de kesin artandır: Pc büyüdükçe ΔP küçülür, ṁ_ox ve onunla
        ṁ_f = f(G_ox) küçülür, Pc_yeni küçülür. g(P_tank) = P_tank > 0
        (ΔP = 0 → akış yok → Pc_yeni = 0) ve g(0⁺) < 0 olduğu için
        (0, P_tank) aralığında TEK kök vardır. Eski 6 turluk sabit-nokta
        döngüsü, ΔP küçüldükçe |dPc_yeni/dPc| > 1 olduğundan ıraksıyor ve
        birbirini tutmayan (Pc, ṁ_ox) çifti yayımlıyordu — tank basıncı
        düşerken itki/Pc/ṁ_ox'un yükselmesinin kökü buydu.

        Yöntem: önceki adımın Pc'si başlangıç tahminidir; kök ondan köşeye
        alınır (gerekirse alt uç yarılanarak) ve Brent (scipy.optimize.
        brentq, xtol 1 Pa) ile çözülür. Arama sırasında denenen O/F
        değerleri motorun "katedilen O/F aralığı" tanısını (A9) GENİŞLETMEZ:
        tanı yalnız çözülen O/F'yi kaydeder.

        Döner: (Pc_pa, ṁ_ox, ṁ_f, O/F, ṙ, c*) — aynı çözümden, tutarlı.
        """
        from scipy.optimize import brentq

        e = self.e
        P_tank = float(self.tank.pressure)
        rho_l = self.tank.props.rho_l(self.tank.T)
        cd_at = self._cd_nozzle * At

        def akis(Pc):
            dP = P_tank - Pc
            if dP <= 0.0:
                return 0.0, 0.0, 0.0, 0.0, None
            mox = self._K_inj * np.sqrt(2.0 * rho_l * dP)
            reg = RegressionAnalyzer.regression_rate(
                e.a, e.n, mox / A_port, rho_f=e.rho_f,
                port_diameter=D_port, grain_length=e.L_grain,
                flux_mode=e.flux_mode)
            r = reg['r_dot']
            mf = fuel_mass_flow_kg_s(e.rho_f, D_port, e.L_grain, r,
                                     port_count=N_port)
            of = mox / max(mf, 1e-9)
            cs, _ = e._instantaneous_performance(of)
            return mox, mf, of, r, cs

        def g(Pc):
            mox, mf, _of, _r, cs = akis(Pc)
            if mox <= 0.0:
                return Pc
            return Pc - (mox + mf) * cs / cd_at

        if P_tank <= 0.0:
            return Pc_tahmin, 0.0, 0.0, 0.0, 0.0, None
        of_min0 = getattr(e, '_perf_of_min', None)
        of_max0 = getattr(e, '_perf_of_max', None)
        try:
            ust = P_tank
            alt = min(max(float(Pc_tahmin), 1.0), P_tank * (1.0 - 1e-9))
            if g(alt) >= 0.0:
                ust = alt
                while alt > 1.0 and g(alt) >= 0.0:
                    alt *= 0.5
            Pc = brentq(g, alt, ust, xtol=1.0, maxiter=200)
        finally:
            # Arama noktaları A9 tanısına girmez (yukarıdaki künye).
            if of_min0 is not None:
                e._perf_of_min = of_min0
            if of_max0 is not None:
                e._perf_of_max = of_max0
        mox, mf, of, r, cs = akis(Pc)
        return Pc, mox, mf, of, r, cs

    def solve(self):
        """Geçici iç balistik çözümünü koşar. **TEK KULLANIMLIKTIR.**

        ÖH D21 a1 (P2B4-11). Çözücü nesnesi kendi durumunu TÜKETİR:
        blowdown tankı (``self.tank``) koşu boyunca boşalır, erozyon
        modelinin uyarıları biriktirilir ve ayrılma/sıfır-kırpma
        sayaçları yalnız ``__init__``'te sıfırlanırdı. İkinci bir
        ``solve()`` çağrısı bunu SESSİZCE yapıyordu ve dejenere bir
        sonuç yayımlıyordu.

        ÖLÇÜLDÜ (docs/scofield/raw/OH/D21/kati/a1/once.json, hibrit
        blowdown, aynı nesnede ardışık üç çağrı):

            çağrı 1 -> steps_total = 404   (gerçek yanma)
            çağrı 2 -> steps_total = 1     (tank zaten boş)
            çağrı 3 -> steps_total = 1

        Sayaçlar biriktiği için uyarı metni bulucunun vakasında
        ``'406 of 1 steps ran over-expanded ...'`` gibi İMKÂNSIZ bir
        cümle kuruyordu: pay bütün koşuların toplamı, payda son koşunun
        adım sayısıydı. Sessiz yedek YASAK — ikinci çağrı artık açık
        bir ``RuntimeError`` ile reddedilir; yeni bir çözüm isteyen
        yeni bir ``TransientBallistics`` kurar (ürün yolu, ör.
        ``solid_rocket_engine`` ve ``app.py``, zaten her istekte yeni
        nesne kuruyor, bu yüzden ürün davranışı DEĞİŞMEZ).

        Raises:
            RuntimeError: aynı örnek üzerinde ikinci kez çağrılırsa.
        """
        if getattr(self, '_solved', False):
            raise RuntimeError(
                "TransientBallistics.solve() is single-use: this solver "
                "instance has already been run and its state is spent (the "
                "blowdown tank is drained and the separation counters hold "
                "the previous run's totals). Re-running it would publish a "
                "degenerate curve and impossible diagnostics such as "
                "'406 of 1 steps'. Build a new TransientBallistics for "
                "another solution.")
        self._solved = True

        e = self.e
        dt = self.dt
        D_port = float(e.D_port_initial)
        _web = web_limit(e)   # web sınırı tane zarfından (V301/A1)
        # ÖH D23 / OH-D21-08 — PORT SAYISI. Geçici seri motorun port
        # sayısını hiç taşımıyordu: yanma çevresi ve port alanı TEK portun
        # değeriydi, oysa motorun kendi tanımı N portludur
        # (A_port = N·π·(D/2)², mdot_f = N·ρ·π·D·L·r; F046). ÖLÇÜLDÜ
        # (7 portlu 3 kN motor, once.json): tasarım noktası mdot_f
        # 0,18373 kg/s ⟷ geçici seri t=0 0,07729 kg/s = 2,3772×. Tek portlu
        # motorda (varsayılan) N = 1 ve aritmetik BİT-ÖZDEŞTİR.
        N_port = int(getattr(e, 'port_count', 1) or 1)
        D_max = _web['port_diameter_m']
        fuel_available = _web['fuel_available_kg']

        # Boğaz durumu (Dalga 3): erozyon kapalıyken At tasarım değerinde
        # SABİT kalır (eski davranışla bit-özdeş aritmetik); açıkken her
        # adımda büyür → Pc = ṁ·c*/(Cd·At) düşer, ε = A_e/A_t küçülür.
        At = float(e.At)
        d_throat = 2.0 * np.sqrt(At / np.pi)
        d_throat0 = d_throat
        A_exit = float(e.epsilon) * At   # nozul çıkışı rijit (sabit alan)
        eps_cur = None    # None → tasarım ε / Pe-oranı / momentum-CF üçlüsü
        pe_cur = None
        cfm_cur = None

        t_arr, Pc_arr, F_arr = [], [], []
        mdot_ox_arr, mdot_f_arr, of_arr, D_arr = [], [], [], []
        dthr_arr = []
        tankP_arr, tankT_arr = [], []
        # ÖH D26 / OH-B4-04: tankın FAZI (two_phase | vapor) her adımda
        # kaydedilir. Bilgi çözücüde zaten vardı (döngü sonu `tank.phase`
        # okumasıyla yanmayı bitiriyor) ama dışarı yalnız `end_event`
        # üzerinden, faz ADI olmadan sızıyordu.
        tank_faz_arr = []
        vapor_gecis_s = None
        warnings_list = []
        if self.erosion is not None:
            warnings_list.extend(getattr(self.erosion, 'warnings', []))
        event = 'time_limit'

        Pc_pa = float(e.P_c) * 1e5   # yarı-kararlı iterasyon başlangıcı
        t = 0.0
        fuel_burned = 0.0

        while t < self.t_max:
            A_port = N_port * np.pi * (D_port / 2.0) ** 2

            # --- besleme + kamara yarı-kararlı kapanışı ---
            # V301/H-PANEL (NK-9/NK-50): blowdown'da Pc ↔ ṁ_ox kapanışı
            # KÖKLÜ (köşeli) çözülür, sabit-nokta iterasyonuyla değil.
            # ÖLÇÜLDÜ (örnek 3 kN N2O/HTPB, taban 52165c557): son ~0,5 s'de
            # eski 6 turluk Picard döngüsü YAKINSAMIYORDU — ΔP küçüldükçe
            # Pc_yeni(Pc) eşlemesinin eğimi |dPc_yeni/dPc| 1'i aşıyor ve
            # döngü salınıp ıraksıyor; yayımlanan (Pc, ṁ_ox) çifti birbirini
            # tutmuyordu (t=9,30 s: ṁ_ox 1,1835 kg/s, aynı Pc'de SPI
            # 0,4164 kg/s). Sonuç: tank basıncı düşerken Pc, ṁ_ox ve itki
            # YUKARI sıçrıyordu (3000 → 3124 N). Kök ``_blowdown_kapanisi``
            # künyesinde. Regüleli kip DEĞİŞMEDİ (aşağıdaki döngü; ṁ_ox
            # sabit olduğu için Pc_yeni Pc'den bağımsızdır) — bit-aynı.
            mdot_ox = float(e.mdot_ox)
            if self.feed_mode == 'blowdown':
                (Pc_pa, mdot_ox, mdot_f, of_inst, r_dot,
                 cstar_inst) = self._blowdown_kapanisi(
                    D_port, A_port, N_port, At, Pc_pa)
            for _ in range(6 if self.feed_mode != 'blowdown' else 0):
                G_ox = mdot_ox / A_port
                reg = RegressionAnalyzer.regression_rate(
                    e.a, e.n, G_ox, rho_f=e.rho_f, port_diameter=D_port,
                    grain_length=e.L_grain, flux_mode=e.flux_mode)
                r_dot = reg['r_dot']
                mdot_f = fuel_mass_flow_kg_s(
                    e.rho_f, D_port, e.L_grain, r_dot,
                    port_count=N_port)
                of_inst = mdot_ox / max(mdot_f, 1e-9)
                cstar_inst, _ = e._instantaneous_performance(of_inst)
                Pc_new = ((mdot_ox + mdot_f) * cstar_inst
                          / (self._cd_nozzle * At))
                if abs(Pc_new - Pc_pa) < 100.0:  # 1 mbar yakınsama
                    Pc_pa = Pc_new
                    break
                Pc_pa = Pc_new

            if mdot_ox <= 0.0:
                event = 'feed_pressure_lost'
                break

            # Hazne basıncı ortamın altına düştüyse lüle artık dışarı akış
            # süremez: yarı-kararlı süpersonik lüle modeli GEÇERSİZDİR.
            # Eskiden burada durak yoktu ve model, basınç düştükçe giderek
            # daha negatif bir C_F (ölçüldü: Pc=1 bar'da −23,2) üretmeye
            # devam ediyordu. Sayı uydurmak yerine çözüm durur.
            Pa_pa_stop = float(self.e.P_a) * 1e5
            if Pa_pa_stop > 0.0 and Pc_pa <= Pa_pa_stop:
                event = 'chamber_below_ambient'
                warnings_list.append(
                    f"t={t:.2f}s: Pc={Pc_pa/1e5:.2f} bar fell to or below the "
                    f"ambient pressure ({Pa_pa_stop/1e5:.2f} bar); the nozzle "
                    f"can no longer sustain supersonic outflow, simulation "
                    f"stopped")
                break

            # Enjektör kararlılığı (yalnız blowdown'da anlamlı).
            # ÖH D18 (P2B4-08): uyarı metni "(SP-8089)" diyordu; deponun
            # eşiği tanımlayan TEK kaynağı (acoustic_modes.
            # CHUG_THRESHOLD_SOURCE) o atfı açıkça GERİ ÇEKİYOR ("the band
            # has NOT been verified page-by-page inside it in this
            # repository, so the threshold is not attributed to it"). Sayı
            # (0,15) doğruydu, yanlış olan yalnız künyeydi. Künye artık
            # CHUG_THRESHOLD_CITATION'dan gelir — aynı yerden, aynı hükümle.
            # i18n_charts.js MSG_PATTERNS deseni künyeyi YAKALAR (sabit metne
            # bağlı değil), böylece bir daha ayrışamaz.
            if self.feed_mode == 'blowdown':
                dp_ratio = (self.tank.pressure - Pc_pa) / Pc_pa
                if dp_ratio < DP_RATIO_UNSTABLE:
                    event = 'injector_unstable'
                    # EN üretilir; TR çevirisi i18n_charts.js MSG_PATTERNS'te
                    warnings_list.append(
                        f"t={t:.2f}s: ΔP/Pc={dp_ratio:.3f} < "
                        f"{DP_RATIO_UNSTABLE} — combustion instability "
                        f"limit, simulation stopped")
                    break
                if dp_ratio < DP_RATIO_WARN and not any(
                        'chugging' in w for w in warnings_list):
                    warnings_list.append(
                        f"t={t:.2f}s: ΔP/Pc={dp_ratio:.2f} < {DP_RATIO_WARN} "
                        f"— chugging risk ({CHUG_THRESHOLD_CITATION})")

            # İtki — C_D SÖZLEŞMESİ TEK (bebek-Scofield F3-1).
            #
            # ÖLÇÜM (17 Ağustos 2026, HEAD f9d95eb; 3000 N / 30 bar / O/F=6
            # N2O-HTPB örnek motoru, blowdown serisi):
            #   t=0 itki  3061,2245 N  ⟷  tasarım noktası 3000,0 N
            #   oran      1,020408...  =  1/0,98  =  1/C_D  (tam)
            # A_t tasarımda A_t = ṁ·c*/(P_c·C_D) ile boyutlandırıldığı için
            # 1/C_D çarpanını ZATEN içerir. Kamara kapanışı (yukarıda) C_D'ye
            # bölerek bunu tam olarak götürüyor ve doğru P_c'yi veriyordu;
            # itki ise şişmiş A_t'yi ham kullandığından çarpan orada AYAKTA
            # kalıyordu. %2,04'lük fazlalık itki eğrisinden toplam impulse'a
            # ve teslim-Isp ortalamasına geçiyordu.
            #
            # Düzeltme: itki, kamara kapanışıyla AYNI etkin boğaz alanını
            # kullanır. C_D·A_t = ṁ·c*/P_c (c* tanımı), yani bu çarpım aynı
            # debiyi geçiren ideal lülenin boğaz alanıdır ve t=0'da seri
            # tasarım noktasının kendisini verir (ölçüldü: 3000,0000 N /
            # 30,00 bar).
            F = self._thrust_coefficient(Pc_pa, eps_cur, pe_cur, cfm_cur) \
                * Pc_pa * (self._cd_nozzle * At)

            # --- kayıt ---
            t += dt
            t_arr.append(t)
            Pc_arr.append(Pc_pa)
            F_arr.append(F)
            mdot_ox_arr.append(mdot_ox)
            mdot_f_arr.append(mdot_f)
            of_arr.append(of_inst)
            D_arr.append(D_port)
            dthr_arr.append(d_throat)
            if self.tank is not None:
                tankP_arr.append(self.tank.pressure)
                tankT_arr.append(self.tank.T)
                # OH-B4-04: basınç/sıcaklıkla AYNI anda, AYNI durumdan.
                tank_faz_arr.append(str(self.tank.phase))

            # --- durum ilerlet ---
            D_port += 2.0 * r_dot * dt
            fuel_burned += mdot_f * dt

            # Boğaz erozyonu: d_t büyür → At büyür → sonraki adımda Pc düşer.
            # Sabit çıkış alanlı (rijit) nozulda ε = A_e/A_t küçülür; Pe/Pc
            # ve momentum-CF izentropik bağıntılardan yeniden hesaplanır.
            if self.erosion is not None:
                r_ero = float(self.erosion.rate_m_s(Pc_pa))  # m/s (yarıçap)
                if r_ero > 0.0:
                    d_throat += 2.0 * r_ero * dt
                    At = np.pi * (d_throat / 2.0) ** 2
                    eps_new = A_exit / At
                    if eps_new <= 1.2:
                        event = 'throat_erosion_limit'
                        warnings_list.append(
                            f"t={t:.2f}s: throat eroded to expansion ratio "
                            f"{eps_new:.2f} <= 1.2 — nozzle no longer "
                            f"effective, simulation stopped")
                        break
                    eps_cur = eps_new
                    pe_cur = self._exit_pressure_ratio(float(e.gamma), eps_cur)
                    cfm_cur = self._momentum_cf(float(e.gamma), pe_cur)

            if D_port >= D_max or fuel_burned >= fuel_available:
                event = 'web_exhausted'
                break
            if self.feed_mode == 'blowdown':
                self.tank.step(mdot_ox, dt)
                if self.tank.phase == 'vapor':
                    # OH-B4-04: geçiş ANI adıyla kaydedilir. Adım [t, t+dt]
                    # aralığını kapattığı için buhar fazı t+dt'de başlar;
                    # t bu adımın kayıt anıdır (kayıt ilerletmeden ÖNCE).
                    vapor_gecis_s = float(t + dt)
                    event = 'oxidizer_depleted'
                    break
            elif t >= e.t_b - 0.5 * dt:
                event = 'burn_time_reached'
                break

        t_arr = np.array(t_arr)
        F_arr = np.array(F_arr)
        Pc_arr = np.array(Pc_arr)
        total_impulse = float(_trapezoid(F_arr, t_arr)) if len(t_arr) > 1 else 0.0

        # --- ÖH D28 / OH-D27-09: KESİLEN PAY ÖLÇÜLÜR --------------------
        # Yürüyüş ``tank.phase == 'vapor'`` olduğu anda kırılıyordu ve bunu
        # dışarı yalnız ``end_event = 'oxidizer_depleted'`` ETİKETİ ile
        # söylüyordu. ÖLÇÜLDÜ (``docs/scofield/raw/OH/D28/hibrit/a1/
        # once.json``, taban 7cd08bcc): altı senaryonun altısında da integre
        # edilen buhar adımı sayısı 0, ``vapor_model_valid`` altısında da
        # True — yani zarf bayrağı YAPISAL olarak doğruydu; ve tankta kalan
        # oksitleyici (nominalde 0,529 kg) ile onun taşıdığı impuls payı
        # (nominalde 1.256 N·s, yayımlanan toplamın %14,1'i) HİÇBİR alandan
        # okunamıyordu. Kesme meşru olabilir, ama SESSİZ olamaz.
        #
        # Ürün kararı: kuyruk fazı BURADA integre edilmez (tankın kendi
        # kuyruk modeli "order-of-magnitude estimate only" beyanıyla gelir
        # ve — aşağıdaki analitik zarf yoklaması gösteriyor ki — akış
        # durmadan ÖNCE üçlü noktanın altına iner; üstüne bir de sıvı için
        # kalibre edilmiş SPI enjektörünü buhara uygulamak gerekirdi).
        # Karşılığında kesilen pay SAYIYLA yayımlanır ve zarf kapısı
        # ateşlenebilir bir hükme bağlanır.
        vapor_integre = any(f == 'vapor' for f in tank_faz_arr)
        artik_ox = None
        artik_i = None
        artik_oran = None
        zarf_terk = None
        if self.tank is not None:
            # Yürüyüş durduğunda tankta kalan TÜM oksitleyici (sıvı + buhar):
            # yanma başka bir sebeple bittiyse (web_exhausted, injector
            # instability) sıvı da kalmış olabilir.
            artik_ox = float(self.tank.liquid_mass + self.tank.vapor_mass)
            if len(t_arr) and mdot_ox_arr and mdot_ox_arr[-1] > 0.0:
                # Kimlik: I = ∫F dt = ∫(F/ṁ_ox)·ṁ_ox dt. Kalan oksitleyici
                # SON İNTEGRE EDİLEN adımın oksitleyici-özgül impulsuyla
                # (F/ṁ_ox, birim N·s/kg) değerlenir — kesme anındaki hız
                # dondurulur, kuyruk dinamiği UYDURULMAZ.
                oran_son = float(F_arr[-1]) / float(mdot_ox_arr[-1])
                artik_i = artik_ox * oran_son
                artik_oran = (artik_i / total_impulse
                              if total_impulse > 0 else None)
            zarf = self.tank.vapor_tail_off_envelope(
                float(self.e.P_a) * 1e5 if self.e.P_a is not None else None)
            zarf_terk = zarf['leaves_envelope']
            if not vapor_integre and artik_i is not None and artik_ox > 0.0:
                # Metin kanalı da susmaz: panel `warnings` dizisini basıyor,
                # kesme oradan da okunur (alanlar programatik kapıdır).
                warnings_list.append(
                    f"TRUNCATED TAIL-OFF: the march stops the instant the "
                    f"liquid is exhausted, so no vapour step is integrated. "
                    f"{artik_ox:.3f} kg of oxidiser is still in the tank; "
                    f"valued at the oxidiser-specific impulse of the last "
                    f"integrated step (F/mdot_ox) that is worth "
                    f"{artik_i:.0f} N*s, "
                    f"{(artik_oran or 0.0) * 100:.1f} % of the impulse "
                    f"reported above. It is NOT modelled here" +
                    (f": the adiabatic vapour path would fall below the N2O "
                     f"triple point (mass ratio {zarf['mass_ratio_at_triple_point']:.3f}) "
                     f"before the flow could stop at ambient pressure "
                     f"(mass ratio {zarf['mass_ratio_at_flow_stop']:.3f}), "
                     f"i.e. the tank tail-off model is out of envelope there."
                     if zarf_terk else
                     " (the tail-off model is not integrated by this solver)."))

        # Ayrılma tabanı devreye girdiyse SESSİZ KALINMAZ: eğrinin o bölümü
        # ekli-akış modelinin geçerlilik aralığı dışında geçmiştir.
        if self._separation_limited_steps:
            warnings_list.append(
                f"{self._separation_limited_steps} of {len(t_arr)} steps ran "
                f"over-expanded past the Summerfield separation limit "
                f"(P_e < {SUMMERFIELD_FACTOR_DEFAULT}*P_a); the attached-flow "
                f"thrust coefficient is invalid there and C_F was floored at "
                f"its separation-station value")

        return {
            'time': t_arr,
            'chamber_pressure': Pc_arr,            # Pa
            'thrust': F_arr,                       # N
            'mdot_ox': np.array(mdot_ox_arr),
            'mdot_fuel': np.array(mdot_f_arr),
            'of_ratio': np.array(of_arr),
            'port_diameter': np.array(D_arr),
            'throat_diameter': np.array(dthr_arr),  # m (erozyon kapalı→sabit)
            # ÖH D21 a1 (P2B4-12): boğaz özeti KAYIT VARSA yayımlanır.
            # dthr_arr[-1] burada İKİ kez korumasızdı ve hiç örnek
            # kaydedilmeyen bir çözümde (ör. t_max_factor = 0.0) aynı
            # sözlük IndexError ile çöküyordu — oysa `len(t_arr)` koruması
            # bu fonksiyonda burn_duration ve average_thrust için ZATEN
            # kullanılıyordu; yalnız erozyon bloğu korumasızdı (ölçüldü:
            # once.json/P2B4-12, 'IndexError: list index out of range').
            # Sayı uydurulmaz: örnek yoksa alanlar None kalır ve gerekçe
            # `status` ile söylenir.
            'erosion': {
                'enabled': self.erosion is not None,
                'initial_throat_diameter_mm': d_throat0 * 1000.0,
                # Özet, KAYDEDİLEN dizinin son elemanından okunur — döngü
                # kayıt→ilerletme sıralı olduğundan d_throat değişkeni diziden
                # bir adım ilerideydi (2026-07-15 Dalga 3 test ajanı bulgusu)
                'final_throat_diameter_mm': (float(dthr_arr[-1]) * 1000.0
                                             if dthr_arr else None),
                # Gerileme yarıçapta ölçülür: (d_son - d_ilk)/2
                'total_recession_mm': (
                    (float(dthr_arr[-1]) - d_throat0) / 2.0 * 1000.0
                    if dthr_arr else None),
                'status': 'computed' if dthr_arr else 'no_samples',
                'basis': (
                    'final throat diameter is the last recorded sample of '
                    'the solved throat history; the recession is measured on '
                    'the RADIUS, (d_final - d_initial)/2.'
                    if dthr_arr else
                    'The solve recorded no time steps, so there is no final '
                    'throat state to report. The initial diameter above is '
                    'the design value the solver started from; no eroded '
                    'geometry is invented.'),
                'model': (self.erosion.describe()
                          if hasattr(self.erosion, 'describe') else None),
            },
            'tank_pressure': np.array(tankP_arr),  # Pa (blowdown)
            'tank_temperature': np.array(tankT_arr),
            # --- ÖH D26 / OH-B4-04: FAZ KANALI ------------------------------
            # Tankın fazı, basınç/sıcaklıkla aynı adımlarda ve aynı durumdan
            # okunur; regüleli kipte tank yoktur, seri boş kalır (sayı
            # uydurulmaz). `tank_phase_final` çözüm BİTTİKTEN sonraki tank
            # durumudur: 'vapor' ise sıvı tükenmiştir. `vapor_onset_s` sıvının
            # bittiği andır; hiç geçmediyse None'dır ve bu bir beyandır.
            'tank_phase': list(tank_faz_arr),
            'tank_phase_final': (str(self.tank.phase)
                                 if self.tank is not None else None),
            'vapor_onset_s': vapor_gecis_s,
            # --- ÖH D28 / OH-D27-09: KESİLEN PAY DEĞER OLARAK -------------
            # `vapor_phase_integrated` ÖLÇÜLÜR (kayıtlı faz serisinden),
            # varsayılmaz; `residual_*` üçlüsü kesmenin boyunu verir;
            # `vapor_tail_off_leaves_model_envelope` üçlü nokta kapısını
            # yürüyüşe gerek KALMADAN yoklar (bkz.
            # N2OTankBlowdown.vapor_tail_off_envelope). Tank yoksa (regüleli
            # kip) dördü de None/False kalır ve sayı uydurulmaz.
            'vapor_phase_integrated': bool(vapor_integre),
            'residual_oxidizer_kg': artik_ox,
            'residual_impulse_at_cutoff_rate_Ns': artik_i,
            'residual_impulse_fraction_at_cutoff_rate': artik_oran,
            'vapor_tail_off_leaves_model_envelope': zarf_terk,
            'feed_mode': self.feed_mode,
            # ÖH D33-2 · OH-UC-04: regüleli kipte tank durumunun rolü
            # ADIYLA yayımlanır (hayalet girdi bırakılmaz); blowdown kipinde
            # tank durumu ZATEN çözücüye girer, alan None kalır.
            'tank_state_role': self._tank_state_role,
            'flow_separation': {
                'criterion': 'summerfield',
                'factor': float(SUMMERFIELD_FACTOR_DEFAULT),
                'steps_floored': int(self._separation_limited_steps),
                'steps_zero_clamped': int(self._negative_cf_steps),
                'steps_total': int(len(t_arr)),
                'basis': (
                    'the attached-flow thrust coefficient is only valid while '
                    'the nozzle flows full. Where P_e falls below '
                    'factor*P_a the flow separates and C_F is floored at the '
                    'value of the same nozzle truncated at the separation '
                    'station, because the divergent section downstream of it '
                    'no longer produces thrust. steps_floored = 0 means the '
                    'whole curve stayed inside the attached-flow range and '
                    'the result is bit-identical to the unfloored model. '
                    'steps_zero_clamped counts the steps where even the '
                    'separation floor was unavailable and a negative '
                    'attached-flow C_F was clamped to zero — a rocket nozzle '
                    'cannot push the vehicle backwards.'),
            },
            'thrust_coefficient_contract': {
                'divergence_efficiency': float(self._lambda),
                'divergence_efficiency_source': (
                    'engine.lambda_eff'
                    if getattr(self.e, 'lambda_eff', None) else
                    'engine.lambda_divergence'),
                'loss_set': self._loss_set,
                'basis': (
                    'the transient thrust coefficient carries the SAME '
                    'contract the design point publishes: the divergence '
                    'factor on the momentum term (Sutton & Biblarz 9th ed. '
                    'Eq. 3-34) taken from the engine itself, times the same '
                    'loss set the headline coefficient applies. Before this '
                    'was fixed the curve started 1.87 % above the design '
                    'thrust because neither was carried.'),
            },
            'end_event': event,
            'burn_duration': float(t_arr[-1]) if len(t_arr) else 0.0,
            'total_impulse': total_impulse,
            'average_thrust': (total_impulse / float(t_arr[-1])
                               if len(t_arr) else 0.0),
            'warnings': warnings_list,
        }


# ---------------------------------------------------------------------------
# WEB SINIRI (v3.0.1, V301/A1) — yürüyüşün port üst sınırı tane zarfından
# ---------------------------------------------------------------------------
# ESKİ KURAL (kaynaksız): ``D_max = 0,8·D_ch``. v3.0.1 tane zarfıyla (kulvar
# P) tek portlu otomatik boyutta D_ch = D_port_son oldu; 0,8 katsayısı geçici
# yürüyüşü son port çapının %80'inde durduruyordu. ÖLÇÜLDÜ
# (docs/scofield/raw/OH/V301/makale1/A1/once.json, taban a367de3d2; 1 kN /
# 10 s / 20 bar / HTPB-N2O, N = 1): danışma blowdown eğrisi O/F 2,5'te
# 2,75 s'de, O/F 7,5'te 2,70 s'de ``web_exhausted`` ile bitiyordu (tasarım
# yanması 10 s), port 43,01 mm'de (= 0,8 × 53,77) duruyor, tankta 3,11 kg
# N2O kalıyordu; /api/transient-analysis düzenlenmiş koşusu 2,675 s'de aynı
# biçimde bitiyordu. N = 4'te tersine sınır 0,8·k(4)·D_son ≈ 1,93·D_son idi:
# tek halka yerleşiminde portlar D_son'da birbirine değer, ötesi model dışı.
#
# YENİ KURAL (ana model kararı): sınır tane zarfının TEK tanımından okunur —
# ``max_port_diameter_in_envelope_m(D_ch, N, t_artık)`` (hybrid_rocket_engine;
# burada yeniden yazılmaz). Otomatik boyutta bu tam olarak son port çapıdır;
# kullanıcı kamarasında N = 1 için D_ch − 2t, N >= 2 için zarfın kabul ettiği
# en büyük halka portu. Yakıt bütçesi aynı sınırdan:
# N·ρ_f·π/4·(D_web² − D_ilk²)·L_grain (``m_fuel`` verilmişse önceliklidir).
# ``D_ch`` taşımayan nesnelerde (ördek tipli taklitler) eski sayısal değer
# BİT-AYNI kalır: (10·D_ilk)·0,8.
#
# Yer: işlev modülün SONUNDADIR, çünkü formal/registry.json bu dosyada 890.
# satıra (``brentq`` çapası) altı Lean bağı tutar; sınıfın önüne eklemek o
# satırı kaydırırdı. ``solve()`` işlevi çalışma anında çağırır.


def _web_sayisi(deger, ad, kapi, birim):
    """Web sınırı girdisi için değer kapısı (dize de reddedilir).

    ``_input_guards`` kapıları sayı-benzeri dizeyi BİLEREK kabul eder (o
    modülün künyesi); bir motor özniteliği ise dize taşımaz — taşıyorsa
    nesne bozuktur ve sınır uydurulmaz.
    """
    if isinstance(deger, (str, bytes)):
        raise ValueError(
            f'{ad} must be a number, not text; got {str(deger)[:40]!r}. '
            'The transient web limit is not computed from a text value.')
    return kapi(deger, ad, birim)


def web_limit(engine):
    """Geçici yürüyüşün web sınırı: port üst çapı ve yanabilir yakıt.

    Döner: ``{'port_diameter_m', 'fuel_available_kg', 'source'}``.
    ``source`` ``'grain_envelope'`` (motor ``D_ch`` taşıyor) ya da
    ``'legacy_no_chamber_diameter'`` (taklit nesne; eski sayı bit-aynı).

    Fail-closed: ``D_ch`` / ``residual_web`` / ``m_fuel`` NaN, inf, bool,
    dize ya da işaretçe geçersizse ``ValueError``. Eskiden NaN sınır
    ``D >= NaN`` karşılaştırmasını hep False yapıp web sınırını SESSİZCE
    kapatıyordu.
    """
    from hrma.analysis._input_guards import (
        require_non_negative, require_positive)
    D_port = float(engine.D_port_initial)
    N_port = int(getattr(engine, 'port_count', 1) or 1)
    D_ch_ham = getattr(engine, 'D_ch', None)
    if D_ch_ham is None:
        D_max = float(D_port * 10) * 0.8
        kaynak = 'legacy_no_chamber_diameter'
    else:
        # İthal GEÇ yapılır (bu modüldeki öteki hibrit ithalleriyle aynı
        # desen: modül düzeyinde döngüsel import riski).
        from hrma.engines.hybrid_rocket_engine import (
            max_port_diameter_in_envelope_m)
        D_ch = _web_sayisi(D_ch_ham, 'D_ch', require_positive, '[m]')
        t_artik_ham = getattr(engine, 'residual_web', None)
        t_artik = (0.0 if t_artik_ham is None else _web_sayisi(
            t_artik_ham, 'residual_web', require_non_negative, '[m]'))
        D_max = float(max_port_diameter_in_envelope_m(D_ch, N_port, t_artik))
        kaynak = 'grain_envelope'
    m_fuel = getattr(engine, 'm_fuel', None)
    if m_fuel:
        # ``m_fuel`` verilmişse ÖNCELİKLİDİR (eski sözleşme; 0/None ->
        # geometri). Doğruluk değeri NaN/inf/bool/dize olan kütle sınırı
        # sessizce kapatırdı: kapıdan geçer.
        fuel_available = _web_sayisi(m_fuel, 'm_fuel', require_positive,
                                     '[kg]')
    else:
        fuel_available = float(N_port * engine.rho_f * np.pi / 4.0
                               * (D_max ** 2 - D_port ** 2) * engine.L_grain)
    return {'port_diameter_m': D_max, 'fuel_available_kg': fuel_available,
            'source': kaynak}
