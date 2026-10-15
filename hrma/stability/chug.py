# hrma/stability/chug.py — besleme kuplajlı alçak frekans (chug) çevrimi
"""Chug: konsantre parametreli besleme-kamara çevrimi, nötr eğri ve büyüme oranı.

NE YAPAR / NE YAPMAZ
--------------------
Bugünkü ürün chug'u bir EŞİK testiydi (ΔP_inj/P_c ≥ 0,20 → OK); gecikmeyi,
kamara hacmini ve L*'ı hiç görmez. Bu modül klasik Summerfield çevrimini
GERÇEKTEN kurar: kararsızlık hükmü, kamara zaman sabiti τ_c, yanma gecikmesi
τ ve enjektör kazancı J'nin birlikte belirlediği bir KÖK YERİ sorusuna döner.
Klasik %15-25 kuralı bu modelde bir NOKTA olarak ölçülür (hüküm değil, kayıt).

ÇEVRİM (tasarım belgesi §3.2'de türetildi)
------------------------------------------
- Enjektör (sıkıştırılamaz orifis, besleme basıncı sabit): ṁ ∝ √(P_f − P_c)
  ⇒ δṁ/ṁ = −(1/(2J))·δP_c/P_c,   J ≡ ΔP_inj/P_c
- Yanma gecikmesi τ (duyarlı zaman gecikmesi): δṁ_üretim(t) = δṁ_enj(t − τ)
- Kamara (chamber.py): τ_c·dx/dt + x = δṁ_üretim/ṁ,  x ≡ δP_c/P_c

Karakteristik denklem ve nötr kararlılık eğrisi:

    τ_c·s + 1 + (1/(2J))·e^(−sτ) = 0
    nötr (s = iω):  cos(ωτ) = −2J ,  sin(ωτ) = 2J·ω·τ_c
    ⇒ ω = √(1 − 4J²)/(2J·τ_c)            (J < 1/2 zorunlu)
    ⇒ τ/τ_c = 2J·arccos(−2J)/√(1 − 4J²)

Sayısal çapa (tasarım belgesi §3.2): J = 0,20 ⇒ τ/τ_c = 0,865152…

**J ≥ 1/2 durumu:** nötr çözüm YOKTUR (|cos| ≤ 1 sağlanamaz). τ = 0'da sistem
kararlıdır (s = −(1 + 1/(2J))/τ_c < 0) ve kökler τ ile sürekli hareket ettiği
için hayali ekseni hiç geçemez ⇒ bu mekanizmaya karşı KOŞULSUZ kararlıdır.
Yani "ΔP/P_c ≥ 0,5 ⇒ chug olmaz" bir tasarım kuralı değil, modelin teoremidir.
SINIRI (ÖH KU, SP-H2 4; beyan ``not_modelled['unconditional_stability_scope']``):
teorem bu modelin İÇİNDE geçerlidir. NASA SP-194 §6.2.3.1, s. 270 (Şekil
6.2.3a) gerçek bir motorda bir itkenin enjektör ΔP'sini artırmanın düşük
ΔP'de KARARSIZLAŞTIRICI olabildiğini gösterir (enjeksiyon hızının gecikmeye
etkisi); manifold kapasitansı (§6.2.3.2, s. 271-273), çift gecikme (§5.2.3,
s. 236-237) ve içsel düşük frekans modu (§5.3.1, s. 239) bu modelde yoktur.

BÜYÜME ORANI — KAPALI FORM (ataletsiz hâl)
------------------------------------------
Gecikmeli birinci mertebe denklemin EN SAĞDAKİ kökü Lambert-W ile kapalı
formdadır (uydurma sayısal arama yok):

    s = W₀(z)/τ − 1/τ_c ,   z = −(τ/(2J·τ_c))·e^(τ/τ_c)

τ → 0 limitinde s → −(1 + 1/(2J))/τ_c (analitik özel hâl olarak ayrıca yazılı).
Künye: Corless, R.M. ve ark., "On the Lambert W Function", *Advances in
Computational Mathematics* 5, 1996 (birinci mertebe gecikmeli denklemin
baskın kökü); çevrimin kendisi: Summerfield, M., "A Theory of Unstable
Combustion in Liquid Propellant Rocket Systems", *ARS Journal* 21(5), 1951;
Harrje, D.T. & Reardon, F.H. (ed.), NASA SP-194, 1972, Böl. 5-6.
DÜRÜSTLÜK NOTU: yukarıdaki türetim bu depoda yapılmıştır; Summerfield'ın
kendi yazımıyla bire bir eşleştiği DOĞRULANMADIĞI için ``basis`` alanında
"Summerfield'ın formu" denmez, "klasik besleme kuplajlı çevrim" denir.

BESLEME HATTI ATALETİ (karar 5 — VARSAYILAN YOK)
------------------------------------------------
Hat ataleti ikinci mertebe terim getirir:

    (ℓ/A)·dδṁ/dt = −δP_c − 2·ΔP_inj·(δṁ/ṁ)
    ⇒ τ_f·dy/dt + y = −(1/(2J))·x ,  τ_f ≡ ρ·ℓ·v̄/(2·ΔP_inj) = ℓ·ṁ/(2·A·ΔP_inj)
    ⇒ (τ_c·s + 1)(τ_f·s + 1) + (1/(2J))·e^(−sτ) = 0

Hat uzunluğu ve kesiti ÇÖZÜLMEZ; kullanıcı vermezse ataletsiz (τ_f = 0) model
koşar ve ``inertance_included: False`` beyanıyla döner. Depodaki
``FEED_LINE_LENGTH_DEFAULT_M = 2.5`` bir yerleşim varsayımıdır ve buraya
KOPYALANMAZ. L taraması için ``sweep_feed_line_length`` kancası vardır; hiçbir
varsayılan taramayla çağrılmaz (çağıran diziyi açıkça verir).

Genel nötr koşul (ataletli hâl de dahil), aynı D-ayrıştırma ile:

    √(1+ω²τ_c²)·√(1+ω²τ_f²) = 1/(2J)                    (tek ω > 0 kökü)
    τ_nötr = [π − arctan(ω·τ_c) − arctan(ω·τ_f)]/ω

τ_f = 0'da bu ifade yukarıdaki kapalı forma ÖZDEŞTİR (bekçili).
"""

import cmath
import math
import sys

from scipy.special import lambertw

from hrma.analysis.acoustic_modes import (
    CHUG_DP_RATIO_MINIMUM,
    CHUG_DP_RATIO_RECOMMENDED,
    CHUG_THRESHOLD_SOURCE,
)
from hrma.stability import (
    STABILITY_NOT_MODELLED,
    VERDICT_STABLE,
    VERDICT_UNSTABLE,
    make_verdict,
)
from hrma.stability.chamber import _positive

__all__ = [
    # Eşik çifti BURADA TANIMLI DEĞİLDİR — yukarıda acoustic_modes'ten ithal
    # edilir ve buradan yalnız YENİDEN YAYIMLANIR. Gerekçe (F2b-2, 17 Ağu
    # 2026): paketin dondurulmuş tip sözleşmesi (``hrma/stability/__init__``
    # §5) sayısal tanımın acoustic_modes'ta olduğunu YAZAR ve chug.py o
    # modülü zaten ithal eder; tanımı buraya taşımak (a) o sözleşme cümlesini
    # yalanlar, (b) katman yönünü ters çevirir (analysis -> stability), çünkü
    # eşiği acoustic_modes'un geri ithal etmesi gerekirdi. Bu yüzden tanım
    # yerinde bırakıldı; chug fiziğinin evinden okumak isteyen çağıran
    # ``from hrma.stability.chug import CHUG_DP_RATIO_MINIMUM`` yazabilir ve
    # ALDIĞI NESNE aynı nesnedir (kimlik bekçisi:
    # tests/test_stability_sivi.py::test_chug_esigi_tek_kaynak).
    'CHUG_DP_RATIO_MINIMUM',
    'CHUG_DP_RATIO_RECOMMENDED',
    'CHUG_THRESHOLD_SOURCE',
    'CHUG_GAIN_J_MAX',
    'chug_neutral_tau_ratio',
    'chug_neutral_frequency_hz',
    'chug_neutral_delay_s',
    'chug_rightmost_root',
    'chug_tau_sensitivity',
    'feed_inertance_time_constant',
    'assess_chug',
    'sweep_feed_line_length',
]

# Kazanç sınırı: J ≥ 1/2'de enjektör geri besleme kazancı 1/(2J) ≤ 1 olur ve
# karakteristik denklemin hayali eksen geçişi İMKÂNSIZLAŞIR. Bu bir tasarım
# kuralı ya da ölçülmüş eşik DEĞİL, modelin türevidir (|cos(ωτ)| ≤ 1).
CHUG_GAIN_J_MAX = 0.5

# Lambert-W yolunda e^(τ/τ_c) taşmasını önleyen SAYISAL menzil kapısı (fizik
# eşiği değil): τ/τ_c bu değerin üstündeyse kapalı form taşar ve sessizce
# yanlış sayı üretmek yerine reddedilir.
#
# P6B4-07: bu kapı YETMEZ, çünkü taşan büyüklük τ/τ_c DEĞİL, Lambert-W'nin
# ARGÜMANIDIR:   z = −(τ / (2·J·τ_c))·exp(τ/τ_c).
# İkinci çarpan τ/τ_c'ye bakar ama BİRİNCİ çarpan 1/J ile büyür. Ölçüldü
# (D25 a2, ``docs/scofield/raw/OH/D25/fea-cfd/a2/once_a2.json`` → P6B4-07):
# J = 1e−300, τ/τ_c = 499 (yani kapının ALTINDA) ⇒ z taşıyor ve fonksiyon
# ``(inf + nan·j)`` DÖNDÜRÜYOR — modülün "sessizce yanlış sayı üretmek
# yerine reddedilir" sözünün tam tersi. Aynı şey τ/τ_c = 100'de ve
# J = 1e−160 / τ/τ_c = 400'de de oluyor (3/4 vaka).
#
# Doğru kapı büyüklüğün KENDİSİNİ ölçer ve taşmadan ölçer:
#     ln|z| = ln(τ) − ln(2·J·τ_c) + τ/τ_c
# çift duyarlıklı en büyük sonlu sayının logaritmasını (≈ 709,78) aşarsa
# kapalı form kullanılamaz. τ/τ_c kapısı KALDIRILMAZ: ln|z| sonlu olsa bile
# çok büyük τ/τ_c'de ara terimler duyarlılığını yitirir, o yüzden iki kapı
# birlikte çalışır (mantıksal VEYA ile reddeder; yani eskisinden SIKI).
_TAU_RATIO_NUMERIC_LIMIT = 500.0

#: ln(sys.float_info.max) — kapalı formun taşma sınırı. Pay bırakılır ki
#: Lambert-W'nin kendi iç hesabı da taşmasın (W₀(z) ≈ ln z − ln ln z).
_LOG_ABS_Z_NUMERIC_LIMIT = math.log(sys.float_info.max) - 1.0

_MODEL_NAME = 'lumped_capacitance_resistance_delay'
_MODEL_NAME_INERTANCE = 'lumped_inertance_capacitance_resistance_delay'

_CHUG_MODEL_BASIS = (
    'Lumped feed-coupled chug loop: incompressible injector orifice at '
    'constant feed pressure (dmdot/mdot = -(1/2J) dPc/Pc with J = dP_inj/Pc), '
    'a sensitive time lag tau between injection and gas production, and the '
    'isothermal lumped chamber (tau_c dx/dt + x = y). Characteristic '
    'equation tau_c*s + 1 + (1/(2J)) exp(-s*tau) = 0; neutral curve '
    'tau/tau_c = 2J*arccos(-2J)/sqrt(1-4J^2), derived in '
    'docs/mimari/f2-yanma-tepkisi-tasarimi.md section 3.2. Classical '
    'background: Summerfield, ARS Journal 21(5), 1951; Harrje & Reardon '
    '(eds.), NASA SP-194, 1972, Ch. 5-6. The closed form above was derived '
    'in this repository and has NOT been matched line-by-line against '
    "Summerfield's own notation, so it is not attributed to his form.")


def _validate_gain(dp_ratio_j, allow_unconditional=False):
    """J = ΔP_inj/P_c kapısı. allow_unconditional=False ise J < 1/2 şart."""
    j = _positive('dp_ratio_j', dp_ratio_j)
    if not allow_unconditional and j >= CHUG_GAIN_J_MAX:
        raise ValueError(
            f'No neutral chug solution exists for dp_ratio_j >= '
            f'{CHUG_GAIN_J_MAX:g} (got {j!r}): the injector feedback gain '
            f'1/(2J) <= 1 cannot satisfy cos(omega*tau) = -2J. The loop is '
            f'unconditionally stable there — use assess_chug(), which '
            f'declares that case instead of failing.')
    return j


def chug_neutral_tau_ratio(dp_ratio_j):
    """Nötr kararlılık eğrisi: τ/τ_c = 2J·arccos(−2J)/√(1 − 4J²) (boyutsuz).

    J → 0⁺ limitinde π·J'ye (yani 0'a), J → 1/2⁻ limitinde +∞'a gider.
    J ≥ 1/2 ⇒ ValueError (nötr nokta yok; koşulsuz kararlı).
    """
    j = _validate_gain(dp_ratio_j)
    return 2.0 * j * math.acos(-2.0 * j) / math.sqrt(1.0 - 4.0 * j * j)


def chug_neutral_frequency_hz(dp_ratio_j, tau_c_s):
    """Nötr noktadaki salınım frekansı f = ω/2π, ω = √(1−4J²)/(2J·τ_c) [Hz]."""
    j = _validate_gain(dp_ratio_j)
    tau_c = _positive('tau_c_s', tau_c_s)
    omega = math.sqrt(1.0 - 4.0 * j * j) / (2.0 * j * tau_c)
    return omega / (2.0 * math.pi)


def _neutral_omega_general(dp_ratio_j, tau_c_s, tau_f_s):
    """Genel (ataletli) nötr geçiş açısal frekansı ω [rad/s].

    √(1+ω²τ_c²)·√(1+ω²τ_f²) = 1/(2J): sol taraf ω'da kesin artan olduğundan
    kök TEKTİR. τ_f = 0'da kapalı forma indirgenir; τ_f > 0'da bikuadratik
    denklem tam çözülür (sayısal arama yok).

    KÖK FORMU — ÖH defter P6B4-06. "TAM çözülür" iddiası doğruydu ama
    ``(−B + √disc)/(2ab)`` yazımı İPTALDEN ölüyordu: B = a+b, c = 1−target
    ve c < 0 olduğundan √disc > B'dir ve pay iki BÜYÜK, BİRBİRİNE ÇOK YAKIN
    sayının farkıdır. Ölçüldü (a2/once_p6b4_06.json; J = 0,30,
    τ_c = 2 ms; referans: aynı denklemin ikiye bölmeyle bulunan kökü):
        τ_f = 1e4 → ω bağıl hatası 2,290e-04
        τ_f = 1e5 → ω bağıl hatası 3,110e-02
        τ_f ≥ 1e6 → pay TAM 0,0 → ω = 0,0 → chug_neutral_delay_s'te
                    ``phase / omega`` ham ZeroDivisionError
                    (uçta HTTP 500; 3/9 vakada çöküş).
    Çare aynı denklemin İPTALSİZ (Citardauq) yazımıdır:
        u = 2c/(−B − √disc) = 2(target−1)/((a+b) + √disc)
    Payda iki POZİTİF sayının toplamıdır, iptal YOKTUR; ayrıca ``2ab``
    bölmesi kalktığı için b → ∞'da taşma da olmaz. Yeni eşik/katsayı
    YOKTUR — aynı kökün cebirsel olarak ÖZDEŞ ikinci yazımıdır.
    """
    j = _validate_gain(dp_ratio_j)
    target = 1.0 / (4.0 * j * j)            # (1/(2J))²
    a = tau_c_s * tau_c_s
    b = tau_f_s * tau_f_s
    if target <= 1.0:
        # J >= 0,5: nötr geçiş yoktur (sol taraf ω = 0'da zaten 1 >= 1/(2J)).
        # _validate_gain bu hâli reddeder; kapı burada da ADIYLA durur ki
        # sessiz bir 0,0 ya da NaN yayılmasın.
        raise ValueError(
            f'dp_ratio_j = {j!r}: 1/(2J) <= 1 olduğundan nötr geçiş '
            'açısal frekansı TANIMSIZ (sistem her ω için kararlı).')
    if b == 0.0:
        return math.sqrt((target - 1.0) / a)
    # (1 + a·u)(1 + b·u) = target,  u ≡ ω²  →  ab·u² + (a+b)·u + (1−target) = 0
    disc = (a + b) ** 2 - 4.0 * a * b * (1.0 - target)
    u = 2.0 * (target - 1.0) / ((a + b) + math.sqrt(disc))
    return math.sqrt(u)


def chug_neutral_delay_s(dp_ratio_j, tau_c_s, tau_f_s=0.0):
    """Nötrlüğü sağlayan EN KÜÇÜK pozitif gecikme τ [s] (ataletli hâl dahil).

    τ_nötr = [π − arctan(ω·τ_c) − arctan(ω·τ_f)]/ω. τ_f = 0'da
    ``chug_neutral_tau_ratio(J)·τ_c`` ile özdeştir (bekçili).
    """
    j = _validate_gain(dp_ratio_j)
    tau_c = _positive('tau_c_s', tau_c_s)
    tau_f = _feed_tau(tau_f_s)
    omega = _neutral_omega_general(j, tau_c, tau_f)
    phase = math.pi - math.atan(omega * tau_c) - math.atan(omega * tau_f)
    return phase / omega


def _feed_tau(tau_f_s):
    """τ_f kapısı: None/0 → ataletsiz; negatif ya da sonsuz → ValueError."""
    if tau_f_s is None:
        return 0.0
    if isinstance(tau_f_s, bool) or not isinstance(tau_f_s, (int, float)):
        raise ValueError(f"tau_f_s must be a finite number (got {tau_f_s!r}).")
    value = float(tau_f_s)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(
            f"tau_f_s must be finite and >= 0 (got {tau_f_s!r}).")
    return value


def feed_inertance_time_constant(line_length_m, line_area_m2,
                                 mass_flow_kg_s, dp_injector_Pa):
    """Besleme hattı atalet zaman sabiti τ_f = ℓ·ṁ/(2·A·ΔP_inj) [s].

    Hat momentum denkleminin ((ℓ/A)·dṁ/dt = ΔP_mevcut − kayıplar) enjektör
    orifis kaybı ΔP ∝ ṁ² etrafında doğrusallaştırılmasından gelir. Uydurma
    varsayılan YOKTUR: dördü de çağırandan gelir (karar 5).

    Args:
        line_length_m: gerçek besleme hattı uzunluğu ℓ [m].
        line_area_m2: hattın akış kesiti A [m²].
        mass_flow_kg_s: hattaki kararlı kütle debisi ṁ [kg/s].
        dp_injector_Pa: enjektör basınç düşümü ΔP_inj [Pa].
    """
    length = _positive('line_length_m', line_length_m)
    area = _positive('line_area_m2', line_area_m2)
    mdot = _positive('mass_flow_kg_s', mass_flow_kg_s)
    dp = _positive('dp_injector_Pa', dp_injector_Pa)
    return length * mdot / (2.0 * area * dp)


_TAU_MONOTONICITY_BASIS = (
    'The verdict compares tau with the neutral delay tau_neutral(J, tau_c, '
    'tau_f), which does NOT depend on tau. The verdict is therefore monotone '
    'in tau: enlarging tau can only move it toward "unstable", never back to '
    '"stable". Substituting the full breakup time for Crocco\'s '
    'pressure-sensitive lag (Crocco & Cheng, AGARDograph 8, 1956) is '
    'conservative for that reason - and this is measured, not asserted.')


def _char_fn(s, gain, tau_s, tau_c_s, tau_f_s):
    """F(s) = (τ_c s + 1)(τ_f s + 1) + g·e^(−sτ)."""
    return ((tau_c_s * s + 1.0) * (tau_f_s * s + 1.0)
            + gain * cmath.exp(-s * tau_s))


def _char_dfn(s, gain, tau_s, tau_c_s, tau_f_s):
    """F'(s)."""
    return (tau_c_s * (tau_f_s * s + 1.0) + tau_f_s * (tau_c_s * s + 1.0)
            - gain * tau_s * cmath.exp(-s * tau_s))


def _newton(s0, gain, tau_s, tau_c_s, tau_f_s, iters=80, tol=1e-13,
            diag=None):
    """Karakteristik denklemin kökünü Newton ile cilalar (kalıntı denetimli).

    ``diag`` verilirse başarısızlık VAKA-ÖZEL gerekçesiyle o sözlüğe yazılır
    (P6B4-15): "kalıntı sağlanmadı" demek yetmez, hangi eşiğin ne kadarla
    kaçırıldığı da söylenir.
    """
    s = complex(s0)
    for it in range(iters):
        f = _char_fn(s, gain, tau_s, tau_c_s, tau_f_s)
        if abs(f) <= tol:
            return s
        d = _char_dfn(s, gain, tau_s, tau_c_s, tau_f_s)
        if d == 0:
            if diag is not None:
                diag['newton_failure'] = (
                    f"F'(s) vanished at iteration {it} (s = {s!r}); the "
                    'Newton step is undefined there, so no root is polished.')
                diag['newton_iterations'] = it
            return None
        step = f / d
        s = s - step
        if not (math.isfinite(s.real) and math.isfinite(s.imag)):
            if diag is not None:
                diag['newton_failure'] = (
                    f'The Newton iterate left the finite plane at iteration '
                    f'{it} (step = {step!r}); no root is fabricated.')
                diag['newton_iterations'] = it
            return None
    residual = abs(_char_fn(s, gain, tau_s, tau_c_s, tau_f_s))
    if residual <= 1e-8:
        return s
    if diag is not None:
        diag['newton_failure'] = (
            f'Newton did not meet the residual check after {iters} '
            f'iterations: |F(s)| = {residual:.6g} > 1e-08 at s = {s!r}.')
        diag['newton_residual'] = residual
        diag['newton_iterations'] = iters
    return None


def _quadratic_rightmost_root(tau_c, tau_f, c_term):
    """a·s² + b·s + c = 0'ın EN SAĞDAKİ kökü (a = τ_c·τ_f, b = τ_c+τ_f).

    ÖH defter OH-FT-02. Buradaki yazım ``(−b + √disc)/(2a)`` idi; bu,
    ``_neutral_omega_general``de P6B4-06 ile sökülen İPTALLİ desenin tam
    ikiziydi. τ_f ≫ τ_c iken √disc ≈ b olduğundan pay iki BÜYÜK, birbirine
    ÇOK YAKIN sayının farkıdır ve anlamlı basamaklar erir. ÖLÇÜLDÜ
    (``docs/scofield/raw/OH/D31/fizik/a1/once_ft02.json``; J = 0,30,
    τ_c = 1 ms; referans: mpmath 60 basamak):
        τ_f = 1e6 s  → bağıl hata 5,862e-12
        τ_f = 1e9 s  → bağıl hata 1,238e-08
        τ_f = 1e12 s → bağıl hata 5,424e-06
        τ_f = 1e15 s → bağıl hata 1,581e-02  (%1,6)
        τ_f = 1e160 s→ ``(τ_c+τ_f)²`` çift duyarlığı TAŞIRIYOR:
                       ham ``OverflowError`` (kök sonlu olmasına rağmen)

    Çare, aynı kökün cebirsel olarak ÖZDEŞ, iptalsiz (Citardauq/Vieta)
    yazımıdır:  s₊ = −2c / (b + √(b²−4ac)).
    Payda iki POZİTİF büyüklüğün toplamıdır (b > 0, c ≥ 1 olduğundan gerçek
    dalda √disc < b ve toplam iptalsizdir), ayrıca ``2a`` bölmesi kalkar.

    Taşma, ölçekle birlikte kaldırılır: m = max(τ_c, τ_f), r = min/m ile
        b = m(1+r),  4ac = 4 m² r c  ⇒  √disc = m·√((1+r)² − 4rc)
        s₊ = −2c / ( m·[(1+r) + √((1+r)² − 4rc)] )
    Köşeli parantez O(1) olduğundan m ne kadar büyürse büyüsün ara değer
    taşmaz; m → ∞ limitinde s₊ → −c/m, yani doğru asimptot.

    Gerçek dalda (disc ≥ 0) iki kök de negatiftir ve |s₊| < |s₋| olduğundan
    s₊ EN SAĞDAKİ köktür; karmaşık dalda iki kökün gerçek kısmı eşittir ve
    bu yazım eskisiyle AYNI (pozitif sanal) eşleniği verir.

    BOYUT SAĞLAMASI: [c] = 1 (boyutsuz kazanç), [m] = s ⇒ [s₊] = 1/s ✔.

    Yeni eşik/katsayı YOKTUR; sayısal yazım dışında model değişmemiştir.
    """
    m = tau_f if tau_f > tau_c else tau_c
    r = (tau_c if tau_f > tau_c else tau_f) / m
    disc = complex((1.0 + r) ** 2 - 4.0 * r * c_term)
    return -2.0 * c_term / (m * ((1.0 + r) + cmath.sqrt(disc)))


def chug_rightmost_root(dp_ratio_j, tau_s, tau_c_s, tau_f_s=0.0,
                        diagnostics=None):
    """Karakteristik denklemin baskın (en sağdaki) kökü s [1/s] — karmaşık.

    τ_f = 0: kapalı form s = W₀(z)/τ − 1/τ_c (Lambert-W).
    τ_f > 0: aynı kökten başlayıp τ_f'de sürekli izleme (continuation) +
    Newton cilası; kalıntı sağlanmazsa None döner (uydurma sayı üretilmez).

    ``diagnostics`` bir sözlük verilirse ve kök çözülemezse, VAKA-ÖZEL
    gerekçe ``diagnostics['reason']`` alanına yazılır (P6B4-15): hangi
    süreklilik adımında, hangi τ_f değerinde ve hangi kalıntıyla
    bırakıldığı. Boş dönüşün "neden" alanı olmadığı sürece tüketici
    (ör. sürekli izleme taramaları) null'u gerekçelendiremiyordu.
    """
    j = _positive('dp_ratio_j', dp_ratio_j)
    tau_c = _positive('tau_c_s', tau_c_s)
    tau_f = _feed_tau(tau_f_s)
    if isinstance(tau_s, bool) or not isinstance(tau_s, (int, float)):
        raise ValueError(f"tau_s must be a finite number (got {tau_s!r}).")
    tau = float(tau_s)
    if not math.isfinite(tau) or tau < 0.0:
        raise ValueError(f"tau_s must be finite and >= 0 (got {tau_s!r}).")

    gain = 1.0 / (2.0 * j)

    if tau == 0.0:
        # Gecikmesiz özel hâl: (τ_c s+1)(τ_f s+1) + g = 0 (ikinci mertebe),
        # yani a·s² + b·s + c = 0 ile a = τ_c·τ_f, b = τ_c+τ_f, c = 1+g.
        if tau_f == 0.0:
            return complex(-(1.0 + gain) / tau_c, 0.0)
        return _quadratic_rightmost_root(tau_c, tau_f, 1.0 + gain)

    if tau / tau_c > _TAU_RATIO_NUMERIC_LIMIT:
        raise ValueError(
            f'tau/tau_c = {tau / tau_c:.3g} exceeds the numerical range of '
            f'the closed-form root ({_TAU_RATIO_NUMERIC_LIMIT:g}); the '
            f'Lambert-W argument overflows. This is a numerical guard, not a '
            f'physical threshold.')

    # P6B4-07: kapı, TAŞAN BÜYÜKLÜĞÜN kendisini ölçer — taşmadan, logaritma
    # uzayında. z = −(τ/(2·J·τ_c))·exp(τ/τ_c) olduğundan
    # ln|z| = ln τ − ln(2·J·τ_c) + τ/τ_c.
    log_abs_z = (math.log(tau) - math.log(2.0 * j * tau_c) + tau / tau_c)
    if log_abs_z > _LOG_ABS_Z_NUMERIC_LIMIT:
        raise ValueError(
            f'The Lambert-W argument of the closed-form root overflows '
            f'double precision: ln|z| = {log_abs_z:.6g} exceeds '
            f'{_LOG_ABS_Z_NUMERIC_LIMIT:.6g} (z = -(tau/(2*J*tau_c))*'
            f'exp(tau/tau_c), with J = {j:.6g}, tau/tau_c = '
            f'{tau / tau_c:.6g}). The magnitude that overflows is z, not '
            f'tau/tau_c alone: a small injector stiffness J inflates z even '
            f'when tau/tau_c is well inside its guard. This is a numerical '
            f'guard, not a physical threshold; no root is invented.')

    z = -(tau / (2.0 * j * tau_c)) * math.exp(tau / tau_c)
    s0 = complex(lambertw(z, 0)) / tau - 1.0 / tau_c
    if tau_f == 0.0:
        return s0

    # Ataletli hâl: τ_f'yi 0'dan hedefe kademeli açıp kökü izle.
    s = s0
    steps = 12
    for k in range(1, steps + 1):
        tf = tau_f * k / steps
        adim_diag = {} if diagnostics is not None else None
        polished = _newton(s, gain, tau, tau_c, tf, diag=adim_diag)
        if polished is None:
            if diagnostics is not None:
                diagnostics.update(adim_diag or {})
                diagnostics['reason'] = (
                    'The dominant root could not be continued in the feed '
                    f'inertance: the tracked root was lost at continuation '
                    f'step {k}/{steps} (tau_f = {tf:.6g} s of the requested '
                    f'{tau_f:.6g} s, J = {j:.6g}, tau/tau_c = '
                    f'{tau / tau_c:.6g}). '
                    + str(adim_diag.get('newton_failure', ''))
                    + ' No growth rate or frequency is published for this '
                    'point; the verdict itself comes from the exact '
                    'neutral-crossing comparison and is unaffected.')
                diagnostics['continuation_step'] = k
                diagnostics['continuation_steps'] = steps
                diagnostics['tau_f_reached_s'] = tf
            return None
        s = polished
    return s


def chug_tau_sensitivity(dp_ratio_j, tau_c_s, tau_f_s, tau_candidates):
    """Hükmün τ SEÇİMİNE duyarlılığı — ÖLÇÜLÜR, varsayılmaz (P6B4-03).

    ÖH defter P6B4-03: aynı yanıtta İKİ karışım zaman ölçeği yayımlanıyor
    (enjektörün ikincil parçalanma süresi τ_atomizasyon ⟷ enjektörün
    karışma kalış süresi ``mixing_residence_time``; ölçülen 4,489 ms ⟷
    1,264 ms, 3,55×) ve çevrim bunlardan YALNIZ BİRİNİ duyarlı gecikme
    olarak kullanıyor. Seçimin "KONSERVATİF" olduğu bugüne dek yalnız
    ``tau_source`` CÜMLESİNDE yazıyordu — ölçülmüyordu. Beyan çözüm
    değildir: burada aynı çevrim her aday τ ile FİİLEN koşulur ve hangi
    adayın daha kararsız hüküm verdiği SAYIYLA saptanır.

    Args:
        dp_ratio_j: J = ΔP_inj/P_c.
        tau_c_s: kamara zaman sabiti [s].
        tau_f_s: besleme atalet zaman sabiti [s] (None/0 → ataletsiz).
        tau_candidates: {ad: τ [s]} — adlar KAYNAK adıdır, uydurulmaz.

    Returns:
        dict: ``candidates`` (ad → hüküm/frekans/büyüme/τ), ``verdicts``
        (görülen farklı hükümler), ``verdict_is_tau_sensitive``,
        ``most_conservative`` (en kararsız hükmü veren ADAY) ve
        ``monotonicity_basis``. AYRICA (ÖH D32, kalemin (c) ayağı):
        ``frequency_hz_span`` (yayımlanan frekansın adaylar arasındaki
        ÖLÇÜLEN bandı: min/max/oran + hangi aday), ``frequency_is_tau_
        sensitive``; AYRICA (ÖH D33-2, OH-D32-08) ``growth_rate_1_s_span``
        (büyüme oranının ÖLÇÜLEN bandı: min/max/span_1_s + işaret sıfırı
        geçmiyorsa oran) ve ``growth_is_tau_sensitive``. Tüketicinin
        bakacağı tek bayrak ``is_tau_sensitive`` (hüküm VEYA frekans VEYA
        büyüme oranı). Geçerli aday yoksa ``None`` döner (uydurma alan
        yayımlanmaz).

    FREKANS ≠ HÜKÜM: aşağıdaki monotonluk savı HÜKMÜ kapsar, frekansı
    KAPSAMAZ. İki aday da aynı hükmü verse bile (``verdict_is_tau_
    sensitive`` False) yayımlanan frekans katlarca değişebilir — defterin
    ölçtüğü koşuda 90,67 Hz ⟷ 262,39 Hz (2,894×). Bu yüzden band ayrıca
    ölçülür; band ölçülemezse (iki adaydan azı frekans çözebildiyse)
    ``frequency_is_tau_sensitive`` False DEĞİL ``None`` olur ve gerekçe
    ``frequency_span_not_resolved_reason``da durur (fail-closed:
    "ölçülmedi" ile "duyarsız" aynı şey değildir). AYNI ŞEY BÜYÜME ORANI
    İÇİN DE GEÇERLİDİR (ÖH D33-2 · OH-D32-08): sav kökün gerçek kısmının
    BÜYÜKLÜĞÜNÜ kapsamaz, o yüzden ``growth_rate_1_s`` de ayrıca banda
    alınır; band ölçülemezse gerekçe ``growth_span_not_resolved_reason``da
    durur.

    MONOTONLUK (bu modelin KANITI, kalibrasyon değil): hüküm
    τ > τ_nötr(J, τ_c, τ_f) karşılaştırmasından gelir ve τ_nötr τ'dan
    BAĞIMSIZDIR. Dolayısıyla hüküm τ'da monotondur: τ'yu BÜYÜTMEK hükmü
    yalnız "unstable" yönüne taşıyabilir, asla geri getiremez. Crocco &
    Cheng (AGARDograph 8, 1956) duyarlı gecikmesi toplam gecikmenin
    yalnız basınca DUYARLI parçasıdır; tam zaman ölçeğini onun yerine
    koymak bu yüzden KONSERVATİFTİR — artık bu cümle bekçiyle ölçülür
    (tests/test_d31_fizik_a1.py).
    """
    j = _positive('dp_ratio_j', dp_ratio_j)
    tau_c = _positive('tau_c_s', tau_c_s)
    tau_f = _feed_tau(tau_f_s)
    if not isinstance(tau_candidates, dict) or not tau_candidates:
        return None
    adaylar = {}
    for ad, deger in tau_candidates.items():
        try:
            t = float(deger)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(t) and t > 0.0):
            continue
        try:
            h = assess_chug(dp_ratio_j=j, tau_s=t, tau_c_s=tau_c,
                            tau_f_s=tau_f)
        except ValueError:
            continue
        adaylar[str(ad)] = {
            'tau_s': t,
            'verdict': h.get('verdict'),
            'frequency_hz': h.get('frequency_hz'),
            'growth_rate_1_s': h.get('growth_rate_1_s'),
            'tau_over_tau_c': t / tau_c,
        }
    if not adaylar:
        return None
    hukumler = sorted({v['verdict'] for v in adaylar.values()})
    # En konservatif aday = EN BÜYÜK τ. Monotonluk gereği hüküm ondan daha
    # kararsız olamaz; eşitlikte ad sırası belirleyicidir (kararlı çıktı).
    en_buyuk = max(sorted(adaylar), key=lambda a: adaylar[a]['tau_s'])
    hukum_duyarli = len(hukumler) > 1

    # ÖH D33-2 · OH-D32-08 — ORTAK BAND ÖLÇERİ.
    # Frekans bandı (D32) ile büyüme oranı bandı (D33-2) AYNI kuralı
    # uygular: geçerli değeri olan adaylar toplanır, ikiden azsa band
    # YAYIMLANMAZ (None + gerekçe), aksi hâlde uçlar ADIYLA verilir.
    # Kural iki kez yazılmaz — eşik yok, duyarlılık iki sayının BİRBİRİNDEN
    # FARKLI olmasıdır.
    def _band(alan, gecerli_mi, min_ad, max_ad, temel, eksen_adi):
        cozulen_ = {ad: v[alan] for ad, v in adaylar.items()
                    if gecerli_mi(v[alan])}
        cozulmeyen_ = sorted(set(adaylar) - set(cozulen_))
        if len(cozulen_) < 2:
            # FAIL-CLOSED: ölçemediğimiz bandı "duyarsız" diye YAYIMLAMAYIZ.
            # False güven verir; burada ölçüm YOK, o yüzden None + gerekçe.
            return None, None, (
                f'{eksen_adi} band not measured: only '
                f'{len(cozulen_)} of {len(adaylar)} candidate(s) resolved a '
                'usable value'
                + (f' (unresolved: {", ".join(cozulmeyen_)})' if cozulmeyen_
                   else '')
                + '. No band is published rather than implying the quantity '
                  'is tau-insensitive.')
        dusuk_ad = min(sorted(cozulen_), key=lambda a: cozulen_[a])
        yuksek_ad = max(sorted(cozulen_), key=lambda a: cozulen_[a])
        return ({
            min_ad: cozulen_[dusuk_ad],
            max_ad: cozulen_[yuksek_ad],
            'min_candidate': dusuk_ad,
            'max_candidate': yuksek_ad,
            'resolved_candidates': sorted(cozulen_),
            'unresolved_candidates': cozulmeyen_,
            '_cozulen': cozulen_,
            '_basis': temel,
        }, cozulen_[yuksek_ad] > cozulen_[dusuk_ad], None)

    # ÖH D32 · P6B4-03 (c) — FREKANS BANDI ÖLÇÜLÜR.
    # Hüküm ölçekten ölçeğe DÖNMESE bile (iki aday da "unstable") yayımlanan
    # ``frequency_hz`` adaylar arasında katlarca değişebilir: defterin
    # ölçtüğü koşuda 90,67 Hz ⟷ 262,39 Hz (2,894×). O koşuda
    # ``verdict_is_tau_sensitive`` FALSE; yalnız o bayrağa bakan tüketici
    # yayımlanan tek frekansı kesinmiş gibi alır ve sönümleme/akustik boşluk
    # tasarımını 2,9× yanlış bir sayıya dayandırır. Monotonluk savı HÜKMÜ
    # kapsar, FREKANSI KAPSAMAZ; bant bu yüzden AYRICA ölçülür.
    # EŞİK YOK: duyarlılık, iki sayının BİRBİRİNDEN FARKLI olmasıdır.
    def _frekans_gecerli(f):
        return (isinstance(f, (int, float)) and not isinstance(f, bool)
                and math.isfinite(f) and f > 0.0)

    frekans_bandi, frekans_duyarli, bant_yok_gerekce = _band(
        'frequency_hz', _frekans_gecerli, 'min_hz', 'max_hz',
        'Measured spread of the published chug frequency across the '
        'candidate time scales - the SAME loop, only tau changes. '
        'The verdict can be identical for every candidate while this '
        'band is wide, so the verdict flag alone does not license '
        'treating the single published frequency_hz as determined.',
        'Frequency')
    if frekans_bandi is not None:
        _cozulen_f = frekans_bandi.pop('_cozulen')
        # Frekans POZİTİF tanımlıdır (band şartı f > 0), oran güvenlidir.
        frekans_bandi['ratio'] = (frekans_bandi['max_hz']
                                  / frekans_bandi['min_hz'])
        del _cozulen_f

    # ÖH D33-2 · OH-D32-08 — BÜYÜME ORANI BANDI DA ÖLÇÜLÜR.
    # D32 yalnız FREKANSI banda aldı. Oysa aynı bloğun aday başına
    # yayımladığı ``growth_rate_1_s`` de τ seçimiyle değişir ve SÖNÜMLEME
    # tasarımını o sayı sürer: gerekli sönümleme büyüme oranıyla
    # kıyaslanır (damping.total_damping_1_s). Ölçüldü (once.json
    # OH-D32-08; J = 0,12, τ_c = 2,0 ms, adaylar 4,489 ms ⟷ 1,264 ms):
    # 191,1397 1/s ⟷ 162,9580 1/s, yani 28,1816 1/s (%17,3) fark ve bunu
    # bildiren alan sayısı 0. Hüküm İKİ adayda da aynı ("unstable") olduğu
    # için ``verdict_is_tau_sensitive`` False; yalnız o bayrağa bakan
    # tüketici tek yayımlanan büyüme oranını kesinmiş gibi alır.
    # MONOTONLUK SAVI BÜYÜME ORANINI DA KAPSAMAZ: sav hükmün τ'da monoton
    # olduğunu söyler (τ_nötr karşılaştırması), kökün gerçek kısmının
    # BÜYÜKLÜĞÜ hakkında bir şey söylemez.
    def _buyume_gecerli(g):
        # Frekanstan FARKLI kural: büyüme oranı işaretlidir (kararlıda
        # negatif). "g > 0" şartı konursa kararlı adaylar sessizce banddan
        # düşer; geçerlilik ölçütü SONLU olmaktır.
        return (isinstance(g, (int, float)) and not isinstance(g, bool)
                and math.isfinite(g))

    buyume_bandi, buyume_duyarli, buyume_bant_yok_gerekce = _band(
        'growth_rate_1_s', _buyume_gecerli, 'min_1_s', 'max_1_s',
        'Measured spread of the published growth rate across the candidate '
        'time scales - the SAME loop, only tau changes. The growth rate is '
        'what a damping design is sized against (compare with '
        'combustion_stability damping totals), so a wide band here means '
        'the single published growth_rate_1_s is not determined even when '
        'every candidate returns the same verdict. The monotonicity '
        'argument covers the VERDICT only; it says nothing about the '
        'MAGNITUDE of the root real part.',
        'Growth rate')
    if buyume_bandi is not None:
        _cozulen_g = buyume_bandi.pop('_cozulen')
        buyume_bandi['span_1_s'] = (buyume_bandi['max_1_s']
                                    - buyume_bandi['min_1_s'])
        # Oran yalnız ARALIK SIFIRI GEÇMİYORSA anlamlıdır. İşaret değişen
        # ya da sıfırı içeren aralıkta "kat" sayısı uydurma olurdu
        # (fail-closed: sayı yerine gerekçe).
        if buyume_bandi['min_1_s'] > 0.0:
            buyume_bandi['ratio'] = (buyume_bandi['max_1_s']
                                     / buyume_bandi['min_1_s'])
            buyume_bandi['ratio_not_applicable_reason'] = None
        else:
            buyume_bandi['ratio'] = None
            buyume_bandi['ratio_not_applicable_reason'] = (
                'No ratio is published: the measured growth-rate band '
                f'[{buyume_bandi["min_1_s"]:.6g}, '
                f'{buyume_bandi["max_1_s"]:.6g}] 1/s reaches zero or '
                'changes sign, so a multiplicative factor would be '
                'meaningless. Read span_1_s (an additive 1/s spread) '
                'instead.')
        del _cozulen_g

    # Tüketicinin bakacağı TEK bayrak. Üç durumlu: ölçemediğimizde False
    # DEMEYİZ (None), çünkü "ölçülmedi" ile "duyarsız" aynı şey değildir.
    # ÖH D33-2 · OH-D32-08: bayrak artık ÜÇ ekseni birleştirir (hüküm VEYA
    # frekans VEYA büyüme oranı). Tek eksen ölçülemediyse ve kalanlar
    # duyarsızsa sonuç yine None'dır — "ölçülmedi" duyarsızlığa terfi
    # ETTİRİLMEZ.
    if hukum_duyarli or frekans_duyarli is True or buyume_duyarli is True:
        birlesik = True
    elif frekans_duyarli is False and buyume_duyarli is False:
        birlesik = False
    else:
        birlesik = None

    return {
        'candidates': adaylar,
        'verdicts': hukumler,
        'verdict_is_tau_sensitive': hukum_duyarli,
        'frequency_is_tau_sensitive': frekans_duyarli,
        'frequency_hz_span': frekans_bandi,
        'frequency_span_not_resolved_reason': bant_yok_gerekce,
        # ÖH D33-2 · OH-D32-08 — büyüme oranı ekseni.
        'growth_is_tau_sensitive': buyume_duyarli,
        'growth_rate_1_s_span': buyume_bandi,
        'growth_span_not_resolved_reason': buyume_bant_yok_gerekce,
        'is_tau_sensitive': birlesik,
        'most_conservative': en_buyuk,
        'monotonicity_basis': _TAU_MONOTONICITY_BASIS,
        '_basis': (
            'Measured sensitivity of the chug verdict to WHICH time scale is '
            'used as the Crocco-Cheng sensitive time lag. Every candidate is '
            'run through the SAME loop; nothing is assumed about which one '
            'is conservative - it is measured. The verdict is only ONE axis: '
            'the monotonicity argument covers the VERDICT, not the '
            'frequency and not the growth rate, so the published '
            'frequency_hz and growth_rate_1_s are banded separately in '
            '\'frequency_hz_span\' and \'growth_rate_1_s_span\'. Read '
            '\'is_tau_sensitive\' (verdict OR frequency OR growth rate; null '
            'when an axis could not be measured and the rest are '
            'insensitive) rather than \'verdict_is_tau_sensitive\' alone.'),
    }


def assess_chug(dp_ratio_j, tau_s, tau_c_s, tau_f_s=None,
                feed_line=None, alternative_taus=None):
    """Chug hükmü + kök yeri + klasik kural çaprazı (beyanlı sözlük).

    Hüküm, tam nötr geçiş karşılaştırmasından gelir (τ = 0'da sistem kararlı
    olduğundan kararsızlık ancak hayali ekseni geçmekle başlar):
    τ > τ_nötr ⇒ unstable, aksi hâlde stable. Kazanç J ≥ 1/2 ise nötr nokta
    yoktur ⇒ koşulsuz kararlı (bu mekanizma için).

    Args:
        dp_ratio_j: J = ΔP_inj/P_c (boyutsuz, > 0).
        tau_s: yanma duyarlı zaman gecikmesi τ [s] (> 0).
        tau_c_s: kamara zaman sabiti τ_c [s] (chamber.chamber_time_constant).
        tau_f_s: besleme atalet zaman sabiti [s]; None → ataletsiz model.
        feed_line: τ_f'nin türetildiği girdilerin yankısı (dict, opsiyonel);
            yalnız beyan içindir, hesaba girmez.

    Returns:
        dict: model, kök, frekans, nötr eğri, hüküm üçlüsü, klasik kural
        çaprazı, not_modelled, assumptions, inputs.
    """
    j = _positive('dp_ratio_j', dp_ratio_j)
    tau_c = _positive('tau_c_s', tau_c_s)
    tau = _positive('tau_s', tau_s)
    tau_f = _feed_tau(tau_f_s)
    inertance = tau_f > 0.0

    unconditional = j >= CHUG_GAIN_J_MAX
    if unconditional:
        neutral_tau = None
        neutral_ratio = None
        neutral_freq = None
    else:
        neutral_tau = chug_neutral_delay_s(j, tau_c, tau_f)
        neutral_ratio = neutral_tau / tau_c
        neutral_freq = (_neutral_omega_general(j, tau_c, tau_f)
                        / (2.0 * math.pi))

    kok_tani = {}
    root = chug_rightmost_root(j, tau, tau_c, tau_f, diagnostics=kok_tani)
    growth = None if root is None else float(root.real)
    frequency = (None if root is None
                 else abs(float(root.imag)) / (2.0 * math.pi))
    # P6B4-15: kök çözülemediğinde VAKA-ÖZEL gerekçe yayımlanır. Eskiden
    # growth_rate_1_s ve frequency_hz sessizce null dönüyordu (ölçüldü:
    # ataletli taramada 441 noktanın 31'i, %7,0) ve tüketici bunu genel
    # ``root_basis`` cümlesinden çıkarmak zorundaydı — oysa API ucu aynı
    # durumu ``skipped_points`` içinde nokta başına gerekçelendiriyor.
    root_not_resolved_reason = (kok_tani.get('reason') if root is None
                                else None)

    # Baskınlık tutarlılığı: izlenen kökün işareti, TAM nötr geçiş
    # karşılaştırmasıyla çelişiyorsa o kök baskın olmayabilir (ataletli yolda
    # ikinci kök çifti sağa geçmiş olabilir). Böyle bir durumda büyüme oranı
    # yayımlanmaz — yanlış sayı yerine beyan (hüküm zaten kökten değil,
    # geçiş karşılaştırmasından gelir).
    dominance_note = None
    if growth is not None and not unconditional:
        expect_positive = tau > neutral_tau
        if (growth > 0.0) != expect_positive and abs(growth) > 1e-9:
            dominance_note = (
                f'The tracked root (Re = {growth:.4g} 1/s) contradicts the '
                f'exact neutral-crossing comparison, so it is not the '
                f'dominant root here; no growth rate is published for this '
                f'point. The verdict itself comes from the crossing '
                f'comparison and is unaffected.')
            growth = None
            frequency = None
            # P6B4-15: bu da bir "çözülemedi" vakasıdır ve kendi gerekçesini
            # taşımalı — null alanın yanında gerekçe alanı BOŞ kalmaz.
            root_not_resolved_reason = dominance_note

    if unconditional:
        verdict_value = VERDICT_STABLE
        verdict_reason = (
            f'Injector gain 1/(2J) = {1.0 / (2.0 * j):.4g} <= 1 at J = '
            f'{j:.4g} >= {CHUG_GAIN_J_MAX:g}: the characteristic equation has '
            'no imaginary-axis crossing for ANY delay, so the loop is '
            'unconditionally stable in this model.')
    elif tau > neutral_tau:
        verdict_value = VERDICT_UNSTABLE
        verdict_reason = (
            f'Sensitive time lag tau = {tau:.4g} s exceeds the neutral delay '
            f'{neutral_tau:.4g} s at J = {j:.4g} (tau/tau_c = '
            f'{tau / tau_c:.4g} vs neutral {neutral_ratio:.4g}); the dominant '
            'root has crossed into the right half plane.')
    else:
        verdict_value = VERDICT_STABLE
        verdict_reason = (
            f'Sensitive time lag tau = {tau:.4g} s stays below the neutral '
            f'delay {neutral_tau:.4g} s at J = {j:.4g} (tau/tau_c = '
            f'{tau / tau_c:.4g} vs neutral {neutral_ratio:.4g}).')

    # P6B4-03: çağıran ikinci bir zaman ölçeği verdiyse hüküm onunla da
    # FİİLEN koşulur ve fark yayımlanır. Girdi yoksa alan HİÇ konmaz
    # (fail-closed: boş ya da uydurma duyarlılık alanı yayımlanmaz).
    tau_duyarlilik = None
    if alternative_taus:
        adaylar = dict(alternative_taus)
        adaylar.setdefault('selected', tau)
        tau_duyarlilik = chug_tau_sensitivity(j, tau_c, tau_f, adaylar)
        # ÖH D32 · P6B4-03 (d) — KIYASSIZ BLOK YAYIMLANMAZ.
        # ``setdefault`` koşunun KENDİ τ'sunu listeye ekler; çağıranın
        # verdiği adayların hepsi geçersizse (None/NaN/≤0, ya da çevrim o
        # τ'da ValueError verdiyse) geriye yalnız 'selected' kalır. O blok
        # hiçbir şey kıyaslamamıştır, ama ``most_conservative: 'selected'``
        # ve ``verdict_is_tau_sensitive: False`` diyerek "seçimimiz en
        # konservatif, ölçeğe duyarlı değil" diye OKUNUR. Fail-closed:
        # geçerli bir ALTERNATİF kalmadıysa alan hiç konmaz.
        if tau_duyarlilik is not None and not (
                set(tau_duyarlilik['candidates']) - {'selected'}):
            tau_duyarlilik = None

    scope = ('feed-coupled chug (modeled mechanism only)'
             + ('' if inertance else ', inertance-free feed line'))
    verdict = make_verdict(verdict_value, scope, verdict_reason)

    # Klasik %15-25 kuralının bu modelde NEREYE düştüğü — ölçüm, eşik değil.
    classical = {
        'rule_min_ratio': CHUG_DP_RATIO_MINIMUM,
        'rule_recommended_ratio': CHUG_DP_RATIO_RECOMMENDED,
        'rule_source': CHUG_THRESHOLD_SOURCE,
        'model_neutral_tau_over_tau_c_at_rule_min':
            chug_neutral_tau_ratio(CHUG_DP_RATIO_MINIMUM),
        'model_neutral_tau_over_tau_c_at_rule_recommended':
            chug_neutral_tau_ratio(CHUG_DP_RATIO_RECOMMENDED),
        'interpretation': (
            'Measurement, not a threshold test: it records where the classical '
            '15-25% injector pressure drop rule falls on this model\'s neutral '
            'curve. The thresholds themselves are imported from '
            'hrma.analysis.acoustic_modes (single source, not redefined).'),
    }

    return {
        'model': _MODEL_NAME_INERTANCE if inertance else _MODEL_NAME,
        'model_basis': _CHUG_MODEL_BASIS,
        'dp_ratio_j': j,
        'tau_s': tau,
        'tau_c_s': tau_c,
        'tau_over_tau_c': tau / tau_c,
        'neutral_delay_s': neutral_tau,
        'neutral_tau_over_tau_c': neutral_ratio,
        'neutral_frequency_hz': neutral_freq,
        'growth_rate_1_s': growth,
        'frequency_hz': frequency,
        # P6B4-15: null'un GEREKÇESİ (çözüldüyse None).
        'root_not_resolved_reason': root_not_resolved_reason,
        'root_not_resolved_detail': (dict(kok_tani) if root is None
                                     and kok_tani else None),
        'root_basis': (
            'Dominant (rightmost) root of the characteristic equation. With '
            'no feed inertance it is closed form via the Lambert W function, '
            's = W0(z)/tau - 1/tau_c with z = -(tau/(2 J tau_c)) '
            'exp(tau/tau_c) (Corless et al., Adv. Comput. Math. 5, 1996); '
            'with inertance the same root is continued in tau_f and polished '
            'by Newton iteration with a residual check (None if the residual '
            'is not met — no number is fabricated).'),
        'root_dominance_note': dominance_note,
        'unconditionally_stable': bool(unconditional),
        'inertance_included': bool(inertance),
        'tau_f_s': tau_f if inertance else None,
        'feed_line': dict(feed_line) if feed_line else None,
        'inertance_basis': (
            'Feed line inertance included: tau_f = l*mdot/(2*A*dP_inj) from '
            'the caller-supplied line length and area.' if inertance else
            'Feed line inertance NOT included: line length/area are not '
            'solved by HRMA and no layout default is assumed here (design '
            'decision 5). Supply feed_inertance_time_constant() output to '
            'switch the model to its second-order form.'),
        **verdict,
        'classical_rule_cross_check': classical,
        # P6B4-03: yalnız çağıran ikinci bir zaman ölçeği verdiyse konur.
        **({'tau_choice_sensitivity': tau_duyarlilik}
           if tau_duyarlilik else {}),
        'not_modelled': {
            'nonlinear_behaviour':
                STABILITY_NOT_MODELLED['nonlinear_behaviour'],
            'feed_system_compressibility': (
                'Feed system compressibility (trapped gas, cavitation, tank '
                'dynamics, regulator response) is NOT modelled: the feed '
                'pressure is held constant upstream of the injector.'),
            'delay_model': (
                'The sensitive time lag tau is an INPUT, not solved here: it '
                'is taken from the calling solver (e.g. atomisation/'
                'vaporisation time). Its own uncertainty propagates directly '
                'into this verdict.'),
            # ÖH KU (KC-12 / SP-H2 4, 14): SP-194'e göre eksik mekanizmalar.
            'manifold_capacitance': (
                'Injector manifold capacitance (and dissolved/trapped gas in '
                'the manifold) is NOT modelled; NASA SP-194 (1972) sec. '
                '6.2.3.2, pp. 271-273 shows it shifts the chug stability '
                'boundary.'),
            'double_time_lag': (
                'A single time lag is used. Separate oxidizer and fuel lags '
                '(NASA SP-194 sec. 5.2.3, pp. 236-237), mixture-ratio / c* '
                'oscillation and the effect of injection velocity on the lag '
                'are NOT modelled.'),
            'intrinsic_low_frequency_mode': (
                'Intrinsic low-frequency instability (possible even with no '
                'feed-system coupling, through the pressure sensitivity of '
                'the combustion lag; Crocco & Cheng, NASA SP-194 sec. 5.3.1, '
                'p. 239) is NOT modelled: this module covers feed-coupled '
                'chug only.'),
            'unconditional_stability_scope': (
                'The result "J >= 1/2 is unconditionally stable" is a '
                'theorem of THIS model, not a design rule: NASA SP-194 sec. '
                '6.2.3.1, p. 270 (Fig. 6.2.3a) shows that raising one '
                "propellant's injector pressure drop can be destabilizing at "
                'low pressure drop in a real engine, through mechanisms this '
                'model omits.'),
        },
        'assumptions': [
            'lumped_chamber',
            'isothermal',
            'incompressible_injector_orifice',
            'constant_feed_pressure',
            'single_sensitive_time_lag',
            'linear_small_perturbation',
        ],
        'inputs': {
            'dp_ratio_j': j,
            'tau_s': tau,
            'tau_c_s': tau_c,
            'tau_f_s': tau_f if inertance else None,
            '_basis': "Echo of the caller's inputs (SI).",
        },
    }


def sweep_feed_line_length(line_lengths_m, line_area_m2, mass_flow_kg_s,
                           dp_injector_Pa, dp_ratio_j, tau_s, tau_c_s):
    """Besleme hattı uzunluğu taraması kancası (karar 5 — varsayılan YOK).

    Çağıran taranacak uzunluk dizisini AÇIKÇA verir; bu fonksiyon hiçbir
    varsayılan tarama üretmez ve hiçbir yerden varsayılan tarama ile
    çağrılmaz. Amacı, "L = 0,5-5 m'de frekans nereye kayar" duyarlılık
    sorusunun ileride mimari değişiklik istememesidir.

    Returns:
        list[dict]: her uzunluk için {line_length_m, tau_f_s, ...assess_chug}.
    """
    if isinstance(line_lengths_m, (str, bytes)):
        raise ValueError('line_lengths_m must be a sequence of lengths [m].')
    try:
        lengths = [float(x) for x in line_lengths_m]
    except TypeError as exc:
        raise ValueError(
            'line_lengths_m must be an iterable of lengths [m].') from exc
    if not lengths:
        raise ValueError(
            'line_lengths_m is empty: the sweep grid must be supplied '
            'explicitly (no default sweep is fabricated).')

    rows = []
    for length in lengths:
        tau_f = feed_inertance_time_constant(
            length, line_area_m2, mass_flow_kg_s, dp_injector_Pa)
        row = assess_chug(
            dp_ratio_j, tau_s, tau_c_s, tau_f_s=tau_f,
            feed_line={'line_length_m': length,
                       'line_area_m2': float(line_area_m2),
                       'mass_flow_kg_s': float(mass_flow_kg_s),
                       'dp_injector_Pa': float(dp_injector_Pa)})
        row['line_length_m'] = length
        rows.append(row)
    return rows
