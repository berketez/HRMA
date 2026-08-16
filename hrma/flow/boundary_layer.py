"""
Entegral (momentum-integral) sınır tabakası — V5, viskoz CFD kulvarının
ilk uygulama partisi.

NE OLDUĞU / NE OLMADIĞI
-----------------------
Bu modül, lüle iç yüzeyi boyunca **sıkıştırılabilir eksenel simetrik
momentum-integral** sınır tabakası denklemini marşlar. Girdisi bir dış
(kenar/edge) akış çözümüdür — depoda ``hrma.flow.quasi1d.solve_nozzle`` ya
da ``hrma.analysis.nozzle_flow_1d.NozzleFlow1D`` bunu yayımlar; çıktısı
θ(x), δ*(x), c_f(x), τ_w(x) ve bunların yüzey integralinden gelen
**sürtünme itki kaybıdır**.

Bu bir Navier-Stokes çözücüsü DEĞİLDİR: sınır tabakası profili çözülmez,
kapanış korelasyonlarıyla (Thwaites / Head / Ludwieg-Tillmann) taşınır.
Ayrılma sonrası, şok-sınır tabaka etkileşimi, pürüzlülük ve ışıma
modellenmez (``BOUNDARY_LAYER_NOT_MODELLED``). Dış akışa geri besleme
(viskoz-viskozsuz çiftleme) YAPILMAZ: δ* hesaplanır ve yayımlanır ama
kenar koşullarını değiştirmez — bu tek yönlü (zayıf) bir katmandır.

Modül saf fiziktir: ``hrma.flow`` paketinin kuralı gereği motor sonuç
sözlüğünden, Flask katmanından ve ``hrma.analysis`` zincirinden bağımsızdır
(bkz. ``hrma/flow/__init__.py``). Gaz taşınım özelliği (μ) modülün İÇİNDE
tanımlanmaz; çağıran ``viscosity_fn(T) -> μ[Pa·s]`` geçirir. Böylece
depodaki tek viskozite kaynağı (``heat_transfer_analysis._get_gas_properties``,
Bartz 1957 üs yasası) kopyalanmadan kullanılabilir.

DENKLEM
-------
von Kármán momentum-integral denkleminin sıkıştırılabilir, eksenel simetrik
biçimi (Schlichting, "Boundary-Layer Theory", 8. baskı, Böl. 23; lüleye
uygulanışı: Elliott, D. G., Bartz, D. R., Silver, S., "Calculation of
turbulent boundary-layer growth and heat transfer in axi-symmetric nozzles",
JPL Technical Report 32-387, 1963):

    dθ/dx + θ·(H + 2 − M_e²)·(1/u_e)·(du_e/dx) + θ·(1/r)·(dr/dx) = c_f/2

    θ   : momentum kalınlığı   [m]      H = δ*/θ (sıkıştırılabilir)
    c_f : 2·τ_w/(ρ_e·u_e²)              M_e: kenar Mach sayısı
    r(x): dönel cidar yarıçapı [m]      (enine terim = Mangler dönüşümünün
                                         diferansiyel karşılığı)

Laminer bölgede aynı denklem Thwaites'in tek-parametreli kapanışıyla
kapatılır; türbülanslı bölgede Head'in entrainment denklemi ikinci
denklemi verir ve c_f Ludwieg-Tillmann bağıntısından gelir.

KAPANIŞLAR VE KÜNYELERİ
-----------------------
Laminer — Thwaites (1949), *Aeronautical Quarterly* 1(3):245-280,
DOI 10.1017/s0001925900000184 (Crossref ile doğrulandı, 16 Ağu 2026):
    d(θ²)/dx = 0.45·ν*/u_e − θ²·[6·(1/u_e)(du_e/dx) + 2·(1/r)(dr/dx)]
    λ = (θ²/ν*)·(du_e/dx),   S(λ) = τ_w·θ/(μ*·u_e)
S(λ) ve H(λ) uydurmaları: Cebeci, T. & Bradshaw, P., "Momentum Transfer in
Boundary Layers", Hemisphere/McGraw-Hill, 1977 (ders kitabı düzeyinde
standart uydurmalar; rapor/kitap künyesi Crossref'te indekslenmiyor).

Türbülanslı — Head, M. R., "Entrainment in the turbulent boundary layer",
ARC R&M 3152, 1958 (rapor; Crossref indekslemiyor):
    d(r·u_e·θ·H1)/dx = r·u_e·F(H1),   F(H1) = 0.0306·(H1 − 3.0)^(−0.6169)
H1(H) uydurması Cebeci & Bradshaw (1977) biçimindedir.
c_f kapanışı — Ludwieg, H. & Tillmann, W., "Investigation of the wall
shearing stress in turbulent boundary layers", NACA TM 1285, 1950
(*Ingenieur-Archiv* 17 (1949) 288-299 çevirisi; rapor künyesi Crossref'te
indekslenmiyor):
    c_f = 0.246·10^(−0.678·H_i)·Re_θ^(−0.268)

Sıkıştırılabilirlik — Eckert referans sıcaklığı yöntemi: Eckert, E. R. G.,
*Trans. ASME* 78(6), 1956, s. 1273-1283, DOI 10.1115/1.4014011:
    T* = T_e + 0.5·(T_w − T_e) + 0.22·r_f·(T_aw − T_e)
Kapanış korelasyonları ρ* = p_e/(R·T*) ve μ* = μ(T*) ile değerlendirilir;
τ_w = ½·ρ*·u_e²·c_f*, momentum denklemine giren c_f ise kenar yoğunluğuna
göre c_f = τ_w/(½·ρ_e·u_e²) olarak dönüştürülür. T* → T_e limitinde yöntem
sıkıştırılamaz hâle bit düzeyinde geri döner (bekçili).

Kurtarma sıcaklığı: T_aw = T_e·(1 + r_f·(γ−1)/2·M_e²), r_f = Pr^(1/2)
laminer / Pr^(1/3) türbülanslı (Sutton & Biblarz, 9. baskı, Böl. 8).
Bu, depodaki ``HeatTransferAnalyzer._adiabatic_wall_temperature`` ile AYNI
bağıntıdır (türbülanslı dalda bit-özdeşliği testle kilitlidir); modül
katman bağımsızlığı gereği bağıntıyı burada bağımsız taşır — aynı gerekçe
``quasi1d.py``'nin alan-Mach bağıntısı için de yazılıdır.

Sıkıştırılabilir şekil faktörü H = δ*/θ: hız profili kuvvet yasası
f = (y/δ)^(1/n), n = 2/(H_i − 1) (böylece sıkıştırılamaz limitte
H = H_i özdeş olarak sağlanır) ve sıcaklık profili Crocco-Busemann
bağıntısı (White, "Viscous Fluid Flow", 3. baskı, Böl. 7-4)

    T/T_e = T_w/T_e + (T_aw/T_e − T_w/T_e)·f − r_f·((γ−1)/2)·M_e²·f²

kabul edilerek δ* ve θ integralleri SAYISAL olarak alınır (Gauss-Legendre).
Yeni ampirik katsayı ÜRETİLMEZ — bu bir kabul (profil ailesi), uydurma
değil; sıkıştırılamaz limitte H = H_i bekçilidir.

Geçiş (laminer → türbülanslı): Michel kriteri (Michel, R., ONERA Rapport
1/1578A, 1951; kullanılan cebirsel biçim Cebeci, T. & Smith, A. M. O.,
"Analysis of Turbulent Boundary Layers", Academic Press, 1974):
    Re_θ,geçiş = 1.174·(1 + 22400/Re_x)·Re_x^0.46
Roket lülesinde varsayılan geçiş kipi ``turbulent_from_start``tır: kamara
akışı yanmadan gelen yüksek türbülans şiddetiyle zaten türbülanslıdır ve
doğal geçiş kriterleri (düşük serbest-akım türbülansı için kalibredir)
lülede geçişi HİÇ tetiklemez (bu partide ölçüldü). Kip beyanlıdır.

Yeniden laminerleşme UYARISI (modellenmez, ÖLÇÜLÜR): hızlanma parametresi
K = (ν_e/u_e²)·(du_e/dx) hesaplanır ve K > 3e-6 olan istasyonlar beyan
edilir — bu bantta türbülanslı kabul İYİMSER olabilir (Moretti, P. M. &
Kays, W. M., *Int. J. Heat Mass Transfer* 8(9), 1965; Jones, W. P. &
Launder, B. E., *Int. J. Heat Mass Transfer* 15(2), 1972). Back & Cuffel'in
lüle ölçümleri bu etkinin gerçek olduğunu gösterir.

Isı akısı (ikincil çıktı, ürüne bağlanmamıştır): Reynolds-Colburn analojisi
St = (c_f/2)·Pr^(−2/3) → q_w = ρ_e·u_e·c_p·St·(T_aw − T_w). Bartz
korelasyonundan BAĞIMSIZ ikinci ölçümdür; ikisinin farkı çağıranın
sorumluluğundadır (biri diğerinin yerine sessizce geçirilemez).

BİRİMLER: SI (m, Pa, K, kg/m³, N). Açı yok.
"""

import numpy as np
from typing import Callable, Dict, Optional, Sequence, Tuple, Union

from scipy.interpolate import PchipInterpolator

__all__ = [
    'BOUNDARY_LAYER_NOT_MODELLED',
    'STATE_LAMINAR',
    'STATE_TURBULENT',
    'TRANSITION_MICHEL',
    'TRANSITION_TURBULENT_FROM_START',
    'TRANSITION_LAMINAR_ONLY',
    'MARCH_COMPLETED',
    'MARCH_STOPPED_BY_CALLER',
    'MARCH_LAMINAR_SEPARATION',
    'MARCH_TURBULENT_SEPARATION',
    'MARCH_NUMERICAL_FAILURE',
    'compressible_shape_factor',
    'eckert_reference_temperature',
    'head_entrainment',
    'head_shape_from_h1',
    'head_shape_h1',
    'ludwieg_tillmann_cf',
    'michel_transition_re_theta',
    'recovery_factor',
    'recovery_temperature',
    'solve_boundary_layer',
    'thwaites_shape',
    'thwaites_shear',
]

# ===========================================================================
# Modül sabitleri — HER BİRİ KÜNYELİ, TEK TANIM YERİ
# (CLAUDE.md kural 11: bu katsayılar başka dosyaya KOPYALANMAZ, ithal edilir)
# ===========================================================================

# --- Thwaites (1949), Aeronautical Quarterly 1(3):245-280 ------------------
#: d(θ²)/dx bağıntısının korelasyon katsayısı (Thwaites'in "0.45"i).
THWAITES_CORRELATION_COEFF = 0.45
#: Aynı bağıntıdaki basınç-gradyanı üssü (u_e^6 ağırlığı).
THWAITES_PRESSURE_EXPONENT = 6.0
#: Eksenel simetri (Mangler) teriminin üssü: θ²·2·(1/r)(dr/dx).
THWAITES_RADIUS_EXPONENT = 2.0
#: S(λ) = (λ + 0.09)^0.62 kayma uydurması — Cebeci & Bradshaw (1977).
THWAITES_SHEAR_OFFSET = 0.09
THWAITES_SHEAR_EXPONENT = 0.62
#: λ = −0.09 laminer ayrılma noktasıdır (S = 0).
THWAITES_LAMBDA_SEPARATION = -0.09
#: Korelasyonun üst geçerlilik sınırı (Thwaites tablosunun kapsadığı bant).
THWAITES_LAMBDA_MAX = 0.25
#: H(λ) uydurması, λ ≥ 0 dalı: H = 2.61 − 3.75λ + 5.24λ² (Cebeci & Bradshaw).
THWAITES_SHAPE_POS = (2.61, -3.75, 5.24)
#: H(λ) uydurması, λ < 0 dalı: H = 2.088 + 0.0731/(λ + 0.14).
THWAITES_SHAPE_NEG = (2.088, 0.0731, 0.14)

# --- Head (1958), ARC R&M 3152 --------------------------------------------
#: F(H1) = 0.0306·(H1 − 3.0)^(−0.6169) entrainment fonksiyonu.
HEAD_ENTRAINMENT_COEFF = 0.0306
HEAD_ENTRAINMENT_OFFSET = 3.0
HEAD_ENTRAINMENT_EXPONENT = -0.6169
#: H1(H) uydurmasının düşey asimptotu: H → ∞ iken H1 → 3.3 (Cebeci & Bradshaw).
#: Marş H1 > 3.3 bandında tutulur; sınır ayrılmaya karşılık gelir.
HEAD_H1_ASYMPTOTE = 3.3
#: H ≤ 1.6 dalı: H1 = 3.3 + 0.8234·(H − 1.1)^(−1.287).
HEAD_H1_LOW = (0.8234, 1.1, -1.287)
#: H > 1.6 dalı: H1 = 3.3 + 1.5501·(H − 0.6778)^(−3.064).
HEAD_H1_HIGH = (1.5501, 0.6778, -3.064)
HEAD_H_BREAK = 1.6
#: Head yönteminde türbülanslı ayrılma ölçütü olarak kullanılan şekil
#: faktörü (Cebeci & Bradshaw 1977: H ≈ 2.4 civarı ayrılma bandı).
HEAD_SEPARATION_H = 2.4
#: H1(H) uydurmasının alt geçerlilik sınırı (H → 1.1 iken H1 → ∞).
HEAD_H_MIN = 1.1

# --- Ludwieg & Tillmann (1950), NACA TM 1285 ------------------------------
LUDWIEG_TILLMANN_COEFF = 0.246
LUDWIEG_TILLMANN_SHAPE_EXPONENT = -0.678
LUDWIEG_TILLMANN_REYNOLDS_EXPONENT = -0.268

# --- Eckert (1956), DOI 10.1115/1.4014011 ---------------------------------
ECKERT_WALL_WEIGHT = 0.5
ECKERT_RECOVERY_WEIGHT = 0.22

# --- Kurtarma faktörü üsleri (Sutton & Biblarz 9. baskı, Böl. 8) ----------
RECOVERY_EXPONENT_LAMINAR = 0.5
RECOVERY_EXPONENT_TURBULENT = 1.0 / 3.0

# --- Michel geçiş kriteri (ONERA 1/1578A 1951; Cebeci & Smith 1974) -------
MICHEL_COEFF = 1.174
MICHEL_OFFSET = 22400.0
MICHEL_EXPONENT = 0.46
#: Kriterin uydurulduğu Re_x bandı (Cebeci & Smith 1974); dışında
#: uygulanmaz ve bu beyan edilir.
MICHEL_RE_X_MIN = 1.0e5
MICHEL_RE_X_MAX = 4.0e7

#: Türbülanslı marşın başlangıç şekil faktörü. Düz levha türbülanslı
#: tabakanın orta-Reynolds tipik değeri (Schlichting 8. baskı, Böl. 21;
#: bu partide ÖLÇÜLDÜ: düz levha marşı başlangıç değerinden bağımsız
#: olarak H ≈ 1.34-1.40 dengesine oturuyor, 300 ≤ Re_θ0 ≤ 1000 için
#: c_f farkı %0.5'ten küçük).
TURBULENT_INITIAL_SHAPE_FACTOR = 1.4

#: Yeniden laminerleşme eşiği K = (ν/u²)(du/dx) > 3e-6 (Moretti & Kays
#: 1965; Jones & Launder 1972). MODELLENMEZ — yalnız ölçülüp beyan edilir.
RELAMINARIZATION_K_THRESHOLD = 3.0e-6

#: Reynolds-Colburn analojisinin Prandtl üssü: St = (c_f/2)·Pr^(−2/3).
COLBURN_PRANDTL_EXPONENT = -2.0 / 3.0

#: İstasyon aralığı başına marş alt adımı. ÖLÇÜLDÜ (45 istasyonlu gerçek
#: lülede, çözünürlük merdiveni bekçisi): 1 → 64 alt adım arasında sürtünme
#: integrali toplam %0.11 değişiyor (8 ile 64 arası %0.11'in altında).
#: Varsayılan 8 seçildi: maliyet/duyarlılık dengesi. Başlangıç tekilliğinin
#: analitik integrali olmasaydı yakınsama √Δx mertebesinde olurdu.
DEFAULT_SUBSTEPS = 8

#: Sıkıştırılabilir δ*/θ integrallerinin Gauss-Legendre nokta sayısı.
#: ÖLÇÜLDÜ (en zor dal, H_i = 2.61 → n = 1.24, integrandın uç noktada
#: sonsuz türevi var): 8 nokta 1.2e-3, 32 nokta 4.0e-5, 64 nokta 7.3e-6
#: bağıl hata (512 noktaya göre). Türbülanslı bantta (n ≥ 1.4) integrand
#: polinom benzeridir ve 16 nokta makine hassasiyeti verir.
SHAPE_QUADRATURE_POINTS = 64

# Marş durumları
STATE_LAMINAR = 'laminar'
STATE_TURBULENT = 'turbulent'

# Geçiş kipleri
TRANSITION_MICHEL = 'michel'
TRANSITION_TURBULENT_FROM_START = 'turbulent_from_start'
TRANSITION_LAMINAR_ONLY = 'laminar_only'

# Marş bitiş durumları
MARCH_COMPLETED = 'completed'
MARCH_STOPPED_BY_CALLER = 'stopped_by_caller'
MARCH_LAMINAR_SEPARATION = 'laminar_separation'
MARCH_TURBULENT_SEPARATION = 'turbulent_separation'
MARCH_NUMERICAL_FAILURE = 'numerical_failure'

_EPS = 1e-12

BOUNDARY_LAYER_NOT_MODELLED = {
    'separated_flow': (
        'Ayrılma SONRASI akış modellenmedi. Entegral yöntem ayrılma '
        'noktasına kadar geçerlidir; laminerde λ ≤ −0.09, türbülansta '
        'H ≥ 2.4 görülürse marş DURDURULUR ve bu beyan edilir. Ayrılmış '
        'bölgedeki sürtünme kaybı bu sayıya DAHİL DEĞİLDİR.'),
    'shock_boundary_layer_interaction': (
        'Şok-sınır tabaka etkileşimi (λ-şok, ayrılma kabarcığı, yeniden '
        'yapışma) modellenmedi. Kenar çözümü lüle içinde normal şok '
        'içeriyorsa marş şok istasyonunda durdurulur.'),
    'wall_roughness': (
        'Cidar pürüzlülüğü modellenmedi: Ludwieg-Tillmann kapanışı düz '
        'cidar içindir. Pürüzlü/ablatif cidarda gerçek sürtünme DAHA '
        'YÜKSEKTİR.'),
    'radiation_and_wall_energy_balance': (
        'Işıma ve cidar enerji dengesi modellenmedi; T_w bir GİRDİDİR. '
        'Yayımlanan q_w yalnız taşınım akısıdır.'),
    'viscous_inviscid_coupling': (
        'Zayıf çiftleme YOK: δ* hesaplanır ama kenar (dış) akış çözümüne '
        'geri beslenmez. Etkin alan daralmasının dış akışa etkisi '
        'modellenmedi.'),
    'transverse_curvature': (
        'Enine eğrilik (δ/r mertebesi) düzeltmesi modellenmedi; Mangler '
        'terimi δ ≪ r kabulüyle birinci mertebedendir. δ/r ölçülüp '
        'yayımlanır (stations.delta_star_over_radius).'),
    'chemical_reaction_and_variable_gamma': (
        'Donmuş, kalorik olarak mükemmel gaz; sınır tabakası içinde '
        'yeniden birleşme/ayrışma ve değişken γ modellenmedi.'),
    'relaminarization': (
        'Hızlanmayla yeniden laminerleşme MODELLENMEDİ; hızlanma '
        'parametresi K yalnız ÖLÇÜLÜP eşik aşımı beyan edilir.'),
    'upstream_history': (
        'Marş verilen ilk istasyondan başlar; kamara içinde gelişmiş '
        'tabakanın geçmişi modellenmedi. θ başlangıç değeri çağıranındır '
        '(varsayılan 0). ÖLÇÜLDÜ (70 bar / ε=25 lülesi): θ₀ = 0 yerine '
        '0.5/1/2 mm verildiğinde marş edilen yüzeydeki sürtünme kaybı '
        '%1.380 → %1.355 / %1.334 / %1.293 iner (kalın tabaka = düşük c_f). '
        'Yani θ₀ = 0 kabulü BU YÜZEYDEKİ sürtünmeyi yukarıdan sınırlar; '
        'kamaranın KENDİ sürtünmesi ise integrale hiç girmez.'),
}

_ASSUMPTIONS = (
    'steady',                        # kararlı akış
    'axisymmetric_thin_layer',       # δ ≪ r, birinci mertebe Mangler terimi
    'attached_boundary_layer',       # ayrılmaya kadar geçerli
    'calorically_perfect_gas',       # sabit γ, R, c_p
    'crocco_busemann_temperature',   # sıcaklık-hız bağıntısı kabulü
    'power_law_velocity_profile',    # δ*/θ integrallerinin profil ailesi
    'one_way_coupling',              # dış akışa geri besleme yok
)


# ===========================================================================
# Kapanış fonksiyonları (analitik, birim testli)
# ===========================================================================

def thwaites_shear(lam: float) -> float:
    """Thwaites kayma fonksiyonu S(λ) = τ_w·θ/(μ·u_e).

    S(λ) = (λ + 0.09)^0.62 (Cebeci & Bradshaw 1977 uydurması).
    λ = −0.09 laminer ayrılmadır (S = 0); altı TANIMSIZDIR ve hata verir.
    """
    lam = float(lam)
    if lam < THWAITES_LAMBDA_SEPARATION - _EPS:
        raise ValueError(
            f'λ = {lam:.6g} < {THWAITES_LAMBDA_SEPARATION} — Thwaites '
            f'kapanışı ayrılma noktasının ötesinde tanımsızdır.')
    return float(max(lam - THWAITES_LAMBDA_SEPARATION, 0.0)
                 ** THWAITES_SHEAR_EXPONENT)


def thwaites_shape(lam: float) -> float:
    """Thwaites şekil faktörü H_i(λ) (sıkıştırılamaz), Cebeci & Bradshaw."""
    lam = float(lam)
    if lam >= 0.0:
        a, b, c = THWAITES_SHAPE_POS
        return float(a + b * lam + c * lam * lam)
    a, b, c = THWAITES_SHAPE_NEG
    return float(a + b / (lam + c))


def head_shape_h1(shape_factor: float) -> float:
    """Head'in ikinci şekil parametresi H1(H) (Cebeci & Bradshaw uydurması)."""
    h = float(shape_factor)
    if h <= HEAD_H_MIN:
        raise ValueError(
            f'H = {h:.6g} ≤ {HEAD_H_MIN} — H1(H) uydurmasının geçerlilik '
            f'sınırının altında.')
    if h <= HEAD_H_BREAK:
        coeff, offset, exponent = HEAD_H1_LOW
    else:
        coeff, offset, exponent = HEAD_H1_HIGH
    return float(HEAD_H1_ASYMPTOTE + coeff * (h - offset) ** exponent)


def head_shape_from_h1(h1: float) -> float:
    """H1 → H ters çözümü (analitik; ``head_shape_h1``ın tam tersi)."""
    h1 = float(h1)
    if h1 <= HEAD_H1_ASYMPTOTE:
        raise ValueError(
            f'H1 = {h1:.6g} ≤ {HEAD_H1_ASYMPTOTE} — H1 uydurmasının düşey '
            f'asimptotunun altında (H → ∞, ayrılma).')
    if h1 >= head_shape_h1(HEAD_H_BREAK):
        coeff, offset, exponent = HEAD_H1_LOW
    else:
        coeff, offset, exponent = HEAD_H1_HIGH
    # H1 = asimptot + coeff·(H − offset)^exponent  ⇒
    # H = offset + (coeff/(H1 − asimptot))^(−1/exponent)   (exponent < 0)
    return float(offset + (coeff / (h1 - HEAD_H1_ASYMPTOTE))
                 ** (-1.0 / exponent))


def head_entrainment(h1: float) -> float:
    """Head'in entrainment fonksiyonu F(H1) = 0.0306·(H1 − 3.0)^(−0.6169)."""
    h1 = float(h1)
    if h1 <= HEAD_ENTRAINMENT_OFFSET:
        raise ValueError(
            f'H1 = {h1:.6g} ≤ {HEAD_ENTRAINMENT_OFFSET} — entrainment '
            f'fonksiyonu tanımsız.')
    return float(HEAD_ENTRAINMENT_COEFF
                 * (h1 - HEAD_ENTRAINMENT_OFFSET) ** HEAD_ENTRAINMENT_EXPONENT)


def ludwieg_tillmann_cf(re_theta: float, shape_factor: float) -> float:
    """Ludwieg-Tillmann cidar sürtünme katsayısı (sıkıştırılamaz biçim).

    c_f = 0.246·10^(−0.678·H)·Re_θ^(−0.268)   (NACA TM 1285, 1950)

    H burada SIKIŞTIRILAMAZ şekil faktörüdür; sıkıştırılabilirlik
    ``solve_boundary_layer`` içinde referans sıcaklık yöntemiyle
    (ρ*, μ*) verilir.
    """
    re_theta = float(re_theta)
    if re_theta <= 0.0:
        raise ValueError('Re_θ pozitif olmalı.')
    return float(LUDWIEG_TILLMANN_COEFF
                 * 10.0 ** (LUDWIEG_TILLMANN_SHAPE_EXPONENT * float(shape_factor))
                 * re_theta ** LUDWIEG_TILLMANN_REYNOLDS_EXPONENT)


def michel_transition_re_theta(re_x: float) -> float:
    """Michel geçiş ölçütü: geçişin gerçekleştiği kritik Re_θ.

    Re_θ,geçiş = 1.174·(1 + 22400/Re_x)·Re_x^0.46
    (Michel 1951; cebirsel biçim Cebeci & Smith 1974.)
    """
    re_x = float(re_x)
    if re_x <= 0.0:
        raise ValueError('Re_x pozitif olmalı.')
    return float(MICHEL_COEFF * (1.0 + MICHEL_OFFSET / re_x)
                 * re_x ** MICHEL_EXPONENT)


def recovery_factor(prandtl: float, turbulent: bool) -> float:
    """Kurtarma faktörü r_f = Pr^(1/3) (türbülanslı) / Pr^(1/2) (laminer)."""
    pr = float(prandtl)
    if pr <= 0.0:
        raise ValueError('Prandtl sayısı pozitif olmalı.')
    exponent = (RECOVERY_EXPONENT_TURBULENT if turbulent
                else RECOVERY_EXPONENT_LAMINAR)
    return float(pr ** exponent)


def recovery_temperature(edge_temperature: float, mach: float, gamma: float,
                         recovery: float) -> float:
    """Adyabatik cidar (kurtarma) sıcaklığı T_aw.

        T_aw = T_e·(1 + r_f·(γ−1)/2·M_e²)

    Bu, ``HeatTransferAnalyzer._adiabatic_wall_temperature``ın durma
    sıcaklığı cinsinden yazılmış biçimiyle cebirsel olarak AYNIDIR
    (T_e = T_0/(1 + (γ−1)/2·M²) konursa birebir çıkar); eşitlik testle
    kilitlidir. Katman bağımsızlığı gereği bağıntı burada taşınır.
    """
    return float(edge_temperature
                 * (1.0 + float(recovery) * 0.5 * (float(gamma) - 1.0)
                    * float(mach) ** 2))


def eckert_reference_temperature(edge_temperature: float,
                                 wall_temperature: float,
                                 recovery_temperature_K: float) -> float:
    """Eckert referans sıcaklığı T* (Eckert 1956, DOI 10.1115/1.4014011).

        T* = T_e + 0.5·(T_w − T_e) + 0.22·(T_aw − T_e)

    NOT: kurtarma faktörü T_aw'nin İÇİNDEDİR (T_aw − T_e = r_f·(γ−1)/2·M²·T_e),
    bu yüzden 0.22 katsayısı doğrudan (T_aw − T_e)'yi çarpar — Eckert'in
    özgün yazımı budur.
    """
    t_e = float(edge_temperature)
    return float(t_e
                 + ECKERT_WALL_WEIGHT * (float(wall_temperature) - t_e)
                 + ECKERT_RECOVERY_WEIGHT * (float(recovery_temperature_K) - t_e))


# --- Sıkıştırılabilir şekil faktörü (profil ailesi + Crocco) ---------------
_GL_NODES, _GL_WEIGHTS = np.polynomial.legendre.leggauss(SHAPE_QUADRATURE_POINTS)


def compressible_shape_factor(shape_incompressible: float,
                              edge_temperature: float,
                              wall_temperature: float,
                              recovery_temperature_K: float,
                              mach: float, gamma: float,
                              recovery: float) -> float:
    """Sıkıştırılabilir şekil faktörü H = δ*/θ.

    Kuvvet yasası hız profili f = (y/δ)^(1/n) ile n = 2/(H_i − 1) alınır —
    bu seçim sıkıştırılamaz limitte H = H_i özdeşliğini SAĞLAR (bekçili).
    Sıcaklık profili Crocco-Busemann bağıntısıdır; ρ/ρ_e = T_e/T.

        θ/δ  = ∫₀¹ (ρ/ρ_e)·f·(1 − f) d(y/δ)
        δ*/δ = ∫₀¹ (1 − (ρ/ρ_e)·f) d(y/δ)

    İntegraller Gauss-Legendre ile alınır. n ≥ 1 iken f değişkeninde
    (dy/δ = n·f^(n−1) df) integrand düzgündür; n < 1 iken aynı integral
    y/δ değişkeninde alınır (f = s^(1/n)) — orada f^(n−1) uç noktada
    integrallenebilir tekilliğe sahiptir ve kuadratür yavaşlar.
    """
    h_i = float(shape_incompressible)
    if h_i <= 1.0:
        raise ValueError(f'H_i = {h_i:.6g} ≤ 1 fiziksel değil.')
    n = 2.0 / (h_i - 1.0)
    unit = 0.5 * (_GL_NODES + 1.0)
    weights = 0.5 * _GL_WEIGHTS
    if n >= 1.0:
        f = unit
        jacobian = n * f ** (n - 1.0)
    else:
        f = unit ** (1.0 / n)
        jacobian = np.ones_like(unit)
    t_e = float(edge_temperature)
    t_w = float(wall_temperature)
    t_aw = float(recovery_temperature_K)
    # Crocco-Busemann: T(f) = T_w + (T_aw − T_w)·f − r_f·(γ−1)/2·M²·T_e·f²
    quad_term = (float(recovery) * 0.5 * (float(gamma) - 1.0)
                 * float(mach) ** 2 * t_e)
    temperature = t_w + (t_aw - t_w) * f - quad_term * f * f
    if np.any(temperature <= 0.0):
        raise ValueError('Crocco profili negatif sıcaklık verdi — girdi '
                         'durumları tutarsız (T_w, T_aw, M_e).')
    density_ratio = t_e / temperature
    theta_int = float(np.sum(weights * jacobian * density_ratio * f * (1.0 - f)))
    delta_star_int = float(np.sum(weights * jacobian
                                  * (1.0 - density_ratio * f)))
    if theta_int <= 0.0:
        raise ValueError('θ integrali pozitif değil — profil ailesi kabulü '
                         'bu durumda geçersiz.')
    return delta_star_int / theta_int


# ===========================================================================
# Kenar (edge) alanı: PCHIP ara değerleyiciler
# ===========================================================================

class _EdgeField:
    """Kenar koşullarının x'e göre türevlenebilir ara değerlemesi.

    PCHIP seçildi (kübik spline değil): tekdüzelik koruyucudur, lüle
    boğazındaki eğim kırılmasında salınım (overshoot) üretmez. Türevler
    aynı ara değerleyiciden analitik alınır — sonlu fark gürültüsü yok.
    """

    def __init__(self, x_m, radius_m, mach, pressure_Pa, temperature_K,
                 gamma: float, gas_constant: float):
        self.x = np.asarray(x_m, dtype=float)
        self.gamma = float(gamma)
        self.gas_constant = float(gas_constant)
        radius = np.asarray(radius_m, dtype=float)
        mach_arr = np.asarray(mach, dtype=float)
        temperature = np.asarray(temperature_K, dtype=float)
        pressure = np.asarray(pressure_Pa, dtype=float)
        velocity = mach_arr * np.sqrt(self.gamma * self.gas_constant
                                      * temperature)
        self._r = PchipInterpolator(self.x, radius)
        self._dr = self._r.derivative()
        self._u = PchipInterpolator(self.x, velocity)
        self._du = self._u.derivative()
        self._T = PchipInterpolator(self.x, temperature)
        self._p = PchipInterpolator(self.x, pressure)
        self._M = PchipInterpolator(self.x, mach_arr)

    def at(self, x: float) -> Dict[str, float]:
        radius = float(self._r(x))
        temperature = float(self._T(x))
        pressure = float(self._p(x))
        velocity = float(self._u(x))
        return {
            'radius_m': radius,
            'dradius_dx': float(self._dr(x)),
            'velocity_m_s': velocity,
            'dvelocity_dx': float(self._du(x)),
            'temperature_K': temperature,
            'pressure_Pa': pressure,
            'mach': float(self._M(x)),
            'density_kg_m3': pressure / (self.gas_constant * temperature),
        }

    def sample(self, x_query) -> list:
        """Verilen konumlarda kenar durumlarını TEK vektörel çağrıyla üretir.

        Skaler PCHIP çağrısı pahalıdır (ÖLÇÜLDÜ: marşın %50'sinden fazlası
        ara değerleme çağrı yükünde geçiyordu). Marş, RK4'ün ihtiyaç
        duyduğu tüm konumları (düğümler + orta noktalar) önceden burada
        üretir; sayısal sonuç aynıdır, yalnız çağrı yükü kalkar.
        """
        xq = np.asarray(x_query, dtype=float)
        radius = self._r(xq)
        dradius = self._dr(xq)
        velocity = self._u(xq)
        dvelocity = self._du(xq)
        temperature = self._T(xq)
        pressure = self._p(xq)
        mach_arr = self._M(xq)
        density = pressure / (self.gas_constant * temperature)
        return [{
            'radius_m': float(radius[i]),
            'dradius_dx': float(dradius[i]),
            'velocity_m_s': float(velocity[i]),
            'dvelocity_dx': float(dvelocity[i]),
            'temperature_K': float(temperature[i]),
            'pressure_Pa': float(pressure[i]),
            'mach': float(mach_arr[i]),
            'density_kg_m3': float(density[i]),
        } for i in range(xq.size)]


# ===========================================================================
# Ana çözücü
# ===========================================================================

def _local_closure(edge: Dict[str, float], theta: float, state: str,
                   h1: Optional[float], gamma: float, prandtl: float,
                   wall_temperature: float,
                   viscosity_fn: Callable[[float], float]) -> Dict[str, float]:
    """Bir istasyonda kapanışların tamamını değerlendirir.

    Hem RK4 türevi hem de yayımlanan teşhis dizileri BU fonksiyondan
    beslenir — iki ayrı uygulama yoktur (kopya yasağı).
    """
    turbulent = (state == STATE_TURBULENT)
    recovery = recovery_factor(prandtl, turbulent)
    t_e = edge['temperature_K']
    t_aw = recovery_temperature(t_e, edge['mach'], gamma, recovery)
    t_star = eckert_reference_temperature(t_e, wall_temperature, t_aw)
    mu_star = float(viscosity_fn(t_star))
    if not (mu_star > 0.0):
        raise ValueError('viscosity_fn pozitif olmayan μ döndürdü.')
    # Referans yoğunluk: sınır tabakası boyunca basınç sabit (ince tabaka),
    # dolayısıyla ρ* = p_e/(R·T*) = ρ_e·(T_e/T*).
    rho_star = edge['density_kg_m3'] * t_e / t_star
    nu_star = mu_star / rho_star
    velocity = edge['velocity_m_s']
    out = {
        'recovery_factor': recovery,
        'T_recovery_K': t_aw,
        'T_reference_K': t_star,
        'mu_reference_Pa_s': mu_star,
        'rho_reference_kg_m3': rho_star,
        'nu_reference_m2_s': nu_star,
    }
    if theta <= 0.0:
        out.update({'shape_incompressible': float('nan'),
                    'shape_factor': float('nan'),
                    'lambda_thwaites': float('nan'),
                    'cf': float('nan'),
                    'tau_wall_Pa': float('nan'),
                    're_theta_reference': float('nan')})
        return out

    if not turbulent:
        lam = theta * theta / nu_star * edge['dvelocity_dx']
        lam = min(max(lam, THWAITES_LAMBDA_SEPARATION), THWAITES_LAMBDA_MAX)
        shape_i = thwaites_shape(lam)
        tau_wall = thwaites_shear(lam) * mu_star * velocity / theta
        out['lambda_thwaites'] = lam
    else:
        h1_local = max(float(h1), HEAD_H1_ASYMPTOTE + 1e-9)
        shape_i = head_shape_from_h1(h1_local)
        re_theta_star = rho_star * velocity * theta / mu_star
        cf_star = ludwieg_tillmann_cf(re_theta_star, shape_i)
        tau_wall = 0.5 * rho_star * velocity * velocity * cf_star
        out['lambda_thwaites'] = float('nan')
        out['re_theta_reference'] = re_theta_star

    shape = compressible_shape_factor(
        shape_i, t_e, wall_temperature, t_aw, edge['mach'], gamma, recovery)
    rho_e = edge['density_kg_m3']
    out.update({
        'shape_incompressible': shape_i,
        'shape_factor': shape,
        'tau_wall_Pa': tau_wall,
        'cf': tau_wall / (0.5 * rho_e * velocity * velocity),
    })
    out.setdefault('re_theta_reference', rho_star * velocity * theta / mu_star)
    return out


def solve_boundary_layer(x_m: Sequence[float],
                         radius_m: Sequence[float],
                         mach: Sequence[float],
                         pressure_Pa: Sequence[float],
                         temperature_K: Sequence[float],
                         *,
                         gamma: float,
                         gas_constant_J_kgK: float,
                         prandtl: float,
                         viscosity_fn: Callable[[float], float],
                         wall_temperature_K: Union[float, Sequence[float]],
                         specific_heat_J_kgK: Optional[float] = None,
                         transition: str = TRANSITION_TURBULENT_FROM_START,
                         theta_initial_m: float = 0.0,
                         substeps: int = DEFAULT_SUBSTEPS,
                         stop_x_m: Optional[float] = None,
                         stop_reason: Optional[str] = None) -> Dict:
    """Lüle cidarı boyunca sıkıştırılabilir entegral sınır tabakası marşı.

    Args:
        x_m: Eksenel istasyonlar [m], kesin artan (kenar çözümünün ekseni).
        radius_m: Cidar yarıçapı r(x) [m] (aynı eksende).
        mach, pressure_Pa, temperature_K: Kenar (çekirdek akış) durumları.
        gamma, gas_constant_J_kgK, prandtl: Gaz özellikleri (donmuş).
        viscosity_fn: μ(T) [Pa·s] — çağıranın tek kaynağı; modül kendi
            viskozite yasasını YAZMAZ.
        wall_temperature_K: Skaler ya da istasyon başına dizi [K].
        specific_heat_J_kgK: c_p; verilirse q_w ve h_g yayımlanır.
        transition: ``turbulent_from_start`` (roket lülesi varsayılanı),
            ``michel`` (doğal geçiş kriteri) veya ``laminar_only``.
        theta_initial_m: İlk istasyondaki θ. 0 ise tabaka orada BAŞLAR ve
            ilk alt aralık analitik olarak integre edilir.
        substeps: İstasyon aralığı başına RK4 alt adımı.
        stop_x_m: Marşın durdurulacağı eksenel konum (şok/ayrılma).
        stop_reason: ``stop_x_m`` verildiyse gerekçe metni (beyan).

    Returns:
        Beyanlı sözlük: ``stations`` (θ, δ*, c_f, τ_w, H, T*, q_w, K, durum),
        ``friction_drag_N``, ``wetted_area_m2``, ``march`` (durum, geçiş
        konumu, alt adım), ``relaminarization``, ``not_modelled``,
        ``assumptions``, ``inputs``.
    """
    x = np.asarray(x_m, dtype=float)
    radius = np.asarray(radius_m, dtype=float)
    mach_arr = np.asarray(mach, dtype=float)
    pressure = np.asarray(pressure_Pa, dtype=float)
    temperature = np.asarray(temperature_K, dtype=float)
    n_st = x.size
    if n_st < 3:
        raise ValueError('En az 3 istasyon gerekir.')
    for name, arr in (('radius_m', radius), ('mach', mach_arr),
                      ('pressure_Pa', pressure),
                      ('temperature_K', temperature)):
        if arr.shape != x.shape:
            raise ValueError(f'{name} dizisi x_m ile aynı uzunlukta olmalı.')
    if np.any(np.diff(x) <= 0.0):
        raise ValueError('x_m kesin artan olmalı.')
    if np.any(radius <= 0.0):
        raise ValueError('radius_m pozitif olmalı.')
    if np.any(temperature <= 0.0) or np.any(pressure <= 0.0):
        raise ValueError('pressure_Pa ve temperature_K pozitif olmalı.')
    if np.any(mach_arr <= 0.0):
        raise ValueError('mach pozitif olmalı (durgun akışta tabaka marşı '
                         'tanımsız).')
    if transition not in (TRANSITION_MICHEL, TRANSITION_TURBULENT_FROM_START,
                          TRANSITION_LAMINAR_ONLY):
        raise ValueError(f'Bilinmeyen geçiş kipi: {transition!r}')
    substeps = int(substeps)
    if substeps < 1:
        raise ValueError('substeps ≥ 1 olmalı.')
    gamma = float(gamma)
    gas_constant = float(gas_constant_J_kgK)
    prandtl = float(prandtl)
    if not (1.0 < gamma < 2.0):
        raise ValueError('gamma (1, 2) aralığında olmalı.')
    if gas_constant <= 0.0 or prandtl <= 0.0:
        raise ValueError('gas_constant_J_kgK ve prandtl pozitif olmalı.')

    wall_temp_arr = np.asarray(wall_temperature_K, dtype=float)
    if wall_temp_arr.ndim == 0:
        wall_temp_arr = np.full(n_st, float(wall_temp_arr))
    elif wall_temp_arr.shape != x.shape:
        raise ValueError('wall_temperature_K skaler ya da istasyon dizisi '
                         'uzunluğunda olmalı.')
    if np.any(wall_temp_arr <= 0.0):
        raise ValueError('wall_temperature_K pozitif olmalı.')

    edge_field = _EdgeField(x, radius, mach_arr, pressure, temperature,
                            gamma, gas_constant)
    wall_temp_interp = PchipInterpolator(x, wall_temp_arr)

    # --- ince marş ızgarası: istasyon noktaları ÜZERİNDE kalır -------------
    x_end = float(x[-1]) if stop_x_m is None else float(min(stop_x_m, x[-1]))
    fine: list = []
    station_of_fine: list = []
    for i in range(n_st - 1):
        if x[i] >= x_end:
            break
        seg_end = min(float(x[i + 1]), x_end)
        seg = np.linspace(float(x[i]), seg_end, substeps + 1)[:-1]
        fine.extend(seg.tolist())
        station_of_fine.extend([i] + [-1] * (seg.size - 1))
        if seg_end < float(x[i + 1]):
            break
    fine.append(x_end)
    station_of_fine.append(n_st - 1 if x_end >= float(x[-1]) else -1)
    x_fine = np.asarray(fine, dtype=float)
    n_fine = x_fine.size
    if n_fine < 2:
        raise ValueError('stop_x_m ilk istasyona çok yakın — marş yapılamaz.')

    # RK4'ün dokunacağı TÜM konumlar önceden ve vektörel olarak örneklenir:
    # düğümler çift indekste (2k), aralık orta noktaları tek indekste (2k+1).
    # Böylece marş boyunca tek bir skaler ara değerleme çağrısı kalmaz.
    x_rk = np.empty(2 * n_fine - 1, dtype=float)
    x_rk[0::2] = x_fine
    x_rk[1::2] = 0.5 * (x_fine[:-1] + x_fine[1:])
    edge_samples = edge_field.sample(x_rk)
    wall_samples = np.asarray(wall_temp_interp(x_rk), dtype=float)

    # --- marş -------------------------------------------------------------
    theta = np.full(n_fine, np.nan)
    h1_state = np.full(n_fine, np.nan)
    states: list = [None] * n_fine
    state = (STATE_LAMINAR if transition in (TRANSITION_MICHEL,
                                             TRANSITION_LAMINAR_ONLY)
             else STATE_TURBULENT)
    status = MARCH_COMPLETED
    status_x: Optional[float] = None
    transition_x: Optional[float] = None
    clamped_h1 = 0

    theta[0] = float(theta_initial_m)
    states[0] = state
    if theta[0] > 0.0 and state == STATE_TURBULENT:
        h1_state[0] = head_shape_h1(TURBULENT_INITIAL_SHAPE_FACTOR)

    def derivative(rk_index: int, theta_q: float, h1_q: Optional[float],
                   state_q: str) -> Tuple[float, float]:
        """(dθ/dx, dG/dx) — G = θ·H1; laminerde ikinci bileşen 0."""
        edge = edge_samples[rk_index]
        closure = _local_closure(edge, theta_q, state_q, h1_q, gamma, prandtl,
                                 float(wall_samples[rk_index]), viscosity_fn)
        rel_du = edge['dvelocity_dx'] / edge['velocity_m_s']
        rel_dr = edge['dradius_dx'] / edge['radius_m']
        if state_q == STATE_LAMINAR:
            # Thwaites θ² formu (marş değişkeni θ olduğundan zincir kuralı)
            d_theta2 = (THWAITES_CORRELATION_COEFF * closure['nu_reference_m2_s']
                        / edge['velocity_m_s']
                        - theta_q * theta_q
                        * (THWAITES_PRESSURE_EXPONENT * rel_du
                           + THWAITES_RADIUS_EXPONENT * rel_dr))
            return d_theta2 / (2.0 * theta_q), 0.0
        d_theta = (closure['cf'] / 2.0
                   - theta_q * (closure['shape_factor'] + 2.0
                                - edge['mach'] ** 2) * rel_du
                   - theta_q * rel_dr)
        h1_local = max(float(h1_q), HEAD_H1_ASYMPTOTE + 1e-9)
        d_g = head_entrainment(h1_local) - theta_q * h1_local * (rel_du + rel_dr)
        return d_theta, d_g

    k_start = 0
    first_interval_exponent = None
    if theta[0] == 0.0:
        # θ = 0 tekilliği: ilk alt aralık ANALİTİK olarak atılır.
        #   laminer   : θ² = 0.45·ν*·Δx/u_e  (sabit özellik, du/dx→0 limiti)
        #   türbülans : dθ/dx = C·θ^(−0.268) ⇒ θ = (1.268·C·Δx)^(1/1.268)
        edge0 = edge_samples[0]
        closure0 = _local_closure(edge0, 0.0, state, None, gamma, prandtl,
                                  float(wall_samples[0]), viscosity_fn)
        step = float(x_fine[1] - x_fine[0])
        if state == STATE_LAMINAR:
            theta[1] = float(np.sqrt(THWAITES_CORRELATION_COEFF
                                     * closure0['nu_reference_m2_s']
                                     / edge0['velocity_m_s'] * step))
            first_interval_exponent = 0.5
        else:
            h_init = TURBULENT_INITIAL_SHAPE_FACTOR
            exponent = -LUDWIEG_TILLMANN_REYNOLDS_EXPONENT   # +0.268
            coeff = ((closure0['rho_reference_kg_m3'] / edge0['density_kg_m3'])
                     * LUDWIEG_TILLMANN_COEFF
                     * 10.0 ** (LUDWIEG_TILLMANN_SHAPE_EXPONENT * h_init)
                     * (closure0['rho_reference_kg_m3'] * edge0['velocity_m_s']
                        / closure0['mu_reference_Pa_s'])
                     ** LUDWIEG_TILLMANN_REYNOLDS_EXPONENT) / 2.0
            power = 1.0 + exponent
            theta[1] = float((power * coeff * step) ** (1.0 / power))
            h1_state[1] = head_shape_h1(h_init)
            first_interval_exponent = exponent / power
        states[1] = state
        k_start = 1
    elif state == STATE_TURBULENT and not np.isfinite(h1_state[0]):
        h1_state[0] = head_shape_h1(TURBULENT_INITIAL_SHAPE_FACTOR)

    for k in range(k_start, n_fine - 1):
        theta_k = theta[k]
        h1_k = h1_state[k]
        state_k = states[k]
        # --- geçiş denetimi (Michel) --------------------------------------
        if (state_k == STATE_LAMINAR and transition == TRANSITION_MICHEL
                and theta_k > 0.0):
            edge_k = edge_samples[2 * k]
            # Michel ölçütü sıkıştırılamaz veriye kalibredir: Reynolds
            # sayıları KENAR özellikleriyle kurulur (referans sıcaklıkla
            # değil) — bu seçim beyanlıdır.
            re_x = (edge_k['density_kg_m3'] * edge_k['velocity_m_s']
                    * (x_fine[k] - x_fine[0])
                    / viscosity_fn(edge_k['temperature_K']))
            if MICHEL_RE_X_MIN <= re_x <= MICHEL_RE_X_MAX:
                re_theta = (edge_k['density_kg_m3'] * edge_k['velocity_m_s']
                            * theta_k / viscosity_fn(edge_k['temperature_K']))
                if re_theta >= michel_transition_re_theta(re_x):
                    state_k = STATE_TURBULENT
                    states[k] = state_k
                    transition_x = float(x_fine[k])
                    h1_k = head_shape_h1(TURBULENT_INITIAL_SHAPE_FACTOR)
                    h1_state[k] = h1_k

        step = float(x_fine[k + 1] - x_fine[k])
        try:
            if state_k == STATE_LAMINAR:
                y = theta_k
                g = 0.0
            else:
                y = theta_k
                g = theta_k * h1_k
            k1 = derivative(2 * k, y, (g / y if y > 0 else np.nan), state_k)
            y2, g2 = y + 0.5 * step * k1[0], g + 0.5 * step * k1[1]
            k2 = derivative(2 * k + 1, y2,
                            (g2 / y2 if y2 > 0 else np.nan), state_k)
            y3, g3 = y + 0.5 * step * k2[0], g + 0.5 * step * k2[1]
            k3 = derivative(2 * k + 1, y3,
                            (g3 / y3 if y3 > 0 else np.nan), state_k)
            y4, g4 = y + step * k3[0], g + step * k3[1]
            k4 = derivative(2 * k + 2, y4,
                            (g4 / y4 if y4 > 0 else np.nan), state_k)
            theta_next = y + step / 6.0 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
            g_next = g + step / 6.0 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        except (ValueError, FloatingPointError) as exc:
            status = MARCH_NUMERICAL_FAILURE
            status_x = float(x_fine[k])
            stop_reason = (stop_reason or '') + f' | kapanış hatası: {exc}'
            break

        if not np.isfinite(theta_next) or theta_next <= 0.0:
            status = MARCH_NUMERICAL_FAILURE
            status_x = float(x_fine[k])
            break

        theta[k + 1] = theta_next
        states[k + 1] = state_k
        if state_k == STATE_TURBULENT:
            h1_next = g_next / theta_next
            if h1_next <= HEAD_H1_ASYMPTOTE:
                h1_next = HEAD_H1_ASYMPTOTE + 1e-9
                clamped_h1 += 1
            h1_state[k + 1] = h1_next
            if head_shape_from_h1(h1_next) >= HEAD_SEPARATION_H:
                status = MARCH_TURBULENT_SEPARATION
                status_x = float(x_fine[k + 1])
                break
        else:
            edge_n = edge_samples[2 * (k + 1)]
            closure_n = _local_closure(edge_n, theta_next, STATE_LAMINAR, None,
                                       gamma, prandtl,
                                       float(wall_samples[2 * (k + 1)]),
                                       viscosity_fn)
            lam_raw = (theta_next * theta_next / closure_n['nu_reference_m2_s']
                       * edge_n['dvelocity_dx'])
            if lam_raw <= THWAITES_LAMBDA_SEPARATION:
                status = MARCH_LAMINAR_SEPARATION
                status_x = float(x_fine[k + 1])
                break

    marched = int(np.count_nonzero(np.isfinite(theta)))
    if (status == MARCH_COMPLETED and stop_x_m is not None
            and x_end < float(x[-1])):
        status = MARCH_STOPPED_BY_CALLER
        status_x = x_end

    # --- teşhis geçişi (marşla AYNI kapanış fonksiyonundan) ---------------
    diag_keys = ('shape_incompressible', 'shape_factor', 'cf', 'tau_wall_Pa',
                 'T_reference_K', 'T_recovery_K', 're_theta_reference',
                 'recovery_factor', 'lambda_thwaites')
    diag = {key: np.full(n_fine, np.nan) for key in diag_keys}
    edge_cache = {'velocity_m_s': np.full(n_fine, np.nan),
                  'radius_m': np.full(n_fine, np.nan),
                  'mach': np.full(n_fine, np.nan),
                  'density_kg_m3': np.full(n_fine, np.nan),
                  'dvelocity_dx': np.full(n_fine, np.nan)}
    for k in range(marched):
        edge_k = edge_samples[2 * k]
        for key in edge_cache:
            edge_cache[key][k] = edge_k[key]
        closure_k = _local_closure(edge_k, theta[k], states[k],
                                   h1_state[k], gamma, prandtl,
                                   float(wall_samples[2 * k]), viscosity_fn)
        for key in diag_keys:
            diag[key][k] = closure_k.get(key, np.nan)

    delta_star = diag['shape_factor'] * theta

    # --- hızlanma parametresi K (ölçülür, modellenmez) --------------------
    mu_edge = np.full(n_fine, np.nan)
    for k in range(marched):
        mu_edge[k] = viscosity_fn(edge_samples[2 * k]['temperature_K'])
    nu_edge = mu_edge / edge_cache['density_kg_m3']
    accel_param = (nu_edge / edge_cache['velocity_m_s'] ** 2
                   * edge_cache['dvelocity_dx'])
    relam_mask = accel_param > RELAMINARIZATION_K_THRESHOLD
    relam_mask &= np.isfinite(accel_param)

    # --- sürtünme itki kaybı: F = ∮ τ_w·ê_z dA = ∫ 2π·r·τ_w dx -----------
    valid = np.isfinite(theta) & np.isfinite(diag['tau_wall_Pa'])
    idx = np.flatnonzero(valid)
    friction_drag = 0.0
    first_interval_drag = 0.0
    if idx.size >= 2:
        xs = x_fine[idx]
        integrand = 2.0 * np.pi * edge_cache['radius_m'][idx] * diag['tau_wall_Pa'][idx]
        friction_drag = float(np.trapz(integrand, xs))
        if first_interval_exponent is not None and idx[0] == 1:
            # τ_w ∝ x^(−q) tekilliği ANALİTİK integrallenir:
            #   ∫₀^Δ τ_w dx = τ_w(Δ)·Δ/(1 − q)
            step0 = float(x_fine[1] - x_fine[0])
            first_interval_drag = float(integrand[0] * step0
                                        / (1.0 - first_interval_exponent))
            friction_drag += first_interval_drag
    # Islak yüzey: dönel yüzey alanı ∮ 2π·r ds, ds = √(dx² + dr²).
    # Marşın ULAŞTIĞI bölge için hesaplanır (sürtünme integraliyle aynı bant).
    wetted = 0.0
    if marched >= 2:
        seg_x = x_fine[:marched]
        seg_r = edge_cache['radius_m'][:marched]
        dx_seg = np.diff(seg_x)
        dr_seg = np.diff(seg_r)
        ds_seg = np.sqrt(dx_seg ** 2 + dr_seg ** 2)
        r_mid = 0.5 * (seg_r[:-1] + seg_r[1:])
        wetted = float(np.sum(2.0 * np.pi * r_mid * ds_seg))

    # --- ısı akısı (Reynolds-Colburn analojisi; ikincil çıktı) ------------
    q_wall = np.full(n_fine, np.nan)
    h_gas = np.full(n_fine, np.nan)
    if specific_heat_J_kgK is not None:
        cp = float(specific_heat_J_kgK)
        if cp <= 0.0:
            raise ValueError('specific_heat_J_kgK pozitif olmalı.')
        stanton = (diag['cf'] / 2.0) * prandtl ** COLBURN_PRANDTL_EXPONENT
        h_gas = (edge_cache['density_kg_m3'] * edge_cache['velocity_m_s']
                 * cp * stanton)
        wall_fine = wall_samples[0::2]
        q_wall = h_gas * (diag['T_recovery_K'] - wall_fine)

    # --- istasyon (kaba ızgara) örneklemesi -------------------------------
    station_idx = [k for k in range(n_fine) if station_of_fine[k] >= 0]
    take = np.array([k for k in station_idx if k < marched], dtype=int)

    def _st(arr):
        return arr[take] if take.size else np.array([])

    stations = {
        'x_m': _st(x_fine),
        'radius_m': _st(edge_cache['radius_m']),
        'theta_m': _st(theta),
        'delta_star_m': _st(delta_star),
        'shape_factor': _st(diag['shape_factor']),
        'shape_factor_incompressible': _st(diag['shape_incompressible']),
        'cf': _st(diag['cf']),
        'tau_wall_Pa': _st(diag['tau_wall_Pa']),
        'T_reference_K': _st(diag['T_reference_K']),
        'T_recovery_K': _st(diag['T_recovery_K']),
        're_theta_reference': _st(diag['re_theta_reference']),
        'acceleration_parameter_K': _st(accel_param),
        'delta_star_over_radius': _st(delta_star / edge_cache['radius_m']),
        'state': [states[k] for k in take],
        'q_wall_W_m2': _st(q_wall),
        'h_gas_W_m2K': _st(h_gas),
        '_basis': (
            'θ: momentum-integral marşı (RK4, istasyon başına '
            f'{substeps} alt adım); δ* = H·θ; c_f = τ_w/(½·ρ_e·u_e²); '
            'T*: Eckert referans sıcaklığı; q_w: Reynolds-Colburn '
            'analojisi (yalnız c_p verildiyse). NaN = marşın ulaşmadığı '
            'ya da θ = 0 olan istasyon.'),
    }

    return {
        'model': 'integral_boundary_layer',
        'stations': stations,
        'friction_drag_N': friction_drag,
        'friction_drag_basis': (
            'F = ∮ τ_w·ê_z dA = ∫ 2π·r(x)·τ_w(x) dx (dönel yüzeyde kayma '
            'gerilmesinin EKSENEL bileşeni; teğet birim vektörün eksenel '
            'bileşeni dx/ds olduğundan yay uzunluğu sadeleşir). Trapez '
            'integrali ince marş ızgarasında alındı'
            + (f'; θ = 0 başlangıç tekilliği ilk alt aralıkta analitik '
               f'olarak integre edildi (τ_w ∝ x^(−{first_interval_exponent:.4g}), '
               f'katkı {first_interval_drag:.6g} N).'
               if first_interval_exponent is not None else '.')),
        'wetted_area_m2': wetted,
        'march': {
            'status': status,
            'status_x_m': status_x,
            'stop_reason': stop_reason,
            'transition_mode': transition,
            'transition_x_m': transition_x,
            'substeps': substeps,
            'fine_points': int(n_fine),
            'marched_points': marched,
            'marched_to_x_m': float(x_fine[marched - 1]) if marched else None,
            'completed_fraction': (float(x_fine[marched - 1] - x_fine[0])
                                   / float(x_fine[-1] - x_fine[0])
                                   if marched > 1 else 0.0),
            'h1_clamped_steps': clamped_h1,
            '_basis': (
                'status = completed | stopped_by_caller | '
                'laminar_separation | turbulent_separation | '
                'numerical_failure. Ayrılma ölçütleri: laminerde '
                f'λ ≤ {THWAITES_LAMBDA_SEPARATION}, türbülansta '
                f'H ≥ {HEAD_SEPARATION_H}. h1_clamped_steps > 0 ise Head '
                'kapanışı asimptota dayandı (ayrılmaya yakın).'),
        },
        'relaminarization': {
            'threshold_K': RELAMINARIZATION_K_THRESHOLD,
            'exceeded_station_count': int(np.count_nonzero(
                relam_mask[np.array(station_idx, dtype=int)]
                if station_idx else np.array([], dtype=bool))),
            'max_K': (float(np.nanmax(accel_param[:marched]))
                      if marched else None),
            '_basis': (
                'K = (ν_e/u_e²)·(du_e/dx); eşik 3e-6 (Moretti & Kays 1965; '
                'Jones & Launder 1972). MODELLENMEZ — eşiği aşan '
                'istasyonlarda türbülanslı kabul İYİMSER olabilir '
                '(yeniden laminerleşme sürtünmeyi ve ısı akısını '
                'DÜŞÜRÜR).'),
        },
        'closure_basis': {
            'laminar': ('Thwaites (1949) tek-parametreli kapanış; S(λ) ve '
                        'H(λ) uydurmaları Cebeci & Bradshaw (1977).'),
            'turbulent': ('Head (1958) entrainment + Ludwieg-Tillmann (1950) '
                          'c_f; H1(H) uydurması Cebeci & Bradshaw (1977).'),
            'compressibility': ('Eckert (1956) referans sıcaklık yöntemi; '
                                'kapanışlar ρ*, μ* ile değerlendirilir.'),
            'shape_factor': ('H = δ*/θ, kuvvet-yasası hız profili + '
                             'Crocco-Busemann sıcaklık profili üzerinden '
                             'sayısal integralle; sıkıştırılamaz limitte '
                             'H = H_i özdeş.'),
            'transition': ('turbulent_from_start: roket kamarası akışı '
                           'zaten türbülanslı kabul edilir (beyan). '
                           'michel: Michel (1951) doğal geçiş kriteri.'),
        },
        'not_modelled': dict(BOUNDARY_LAYER_NOT_MODELLED),
        'assumptions': list(_ASSUMPTIONS),
        'inputs': {
            'gamma': gamma,
            'gas_constant_J_kgK': gas_constant,
            'prandtl': prandtl,
            'wall_temperature_K': (float(wall_temp_arr[0])
                                   if np.all(wall_temp_arr == wall_temp_arr[0])
                                   else wall_temp_arr.tolist()),
            'theta_initial_m': float(theta_initial_m),
            'specific_heat_J_kgK': (None if specific_heat_J_kgK is None
                                    else float(specific_heat_J_kgK)),
            'x_start_m': float(x[0]),
            'x_end_m': float(x[-1]),
            '_basis': 'Çağıranın verdiği girdilerin yankısı (SI birimleri).',
        },
    }
