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
    'CHUG_GAIN_J_MAX',
    'chug_neutral_tau_ratio',
    'chug_neutral_frequency_hz',
    'chug_neutral_delay_s',
    'chug_rightmost_root',
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
_TAU_RATIO_NUMERIC_LIMIT = 500.0

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
    """
    j = _validate_gain(dp_ratio_j)
    target = 1.0 / (4.0 * j * j)            # (1/(2J))²
    a = tau_c_s * tau_c_s
    b = tau_f_s * tau_f_s
    if b == 0.0:
        return math.sqrt((target - 1.0) / a)
    # (1 + a·u)(1 + b·u) = target,  u ≡ ω²  →  ab·u² + (a+b)·u + (1−target) = 0
    disc = (a + b) ** 2 - 4.0 * a * b * (1.0 - target)
    u = (-(a + b) + math.sqrt(disc)) / (2.0 * a * b)
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


def _char_fn(s, gain, tau_s, tau_c_s, tau_f_s):
    """F(s) = (τ_c s + 1)(τ_f s + 1) + g·e^(−sτ)."""
    return ((tau_c_s * s + 1.0) * (tau_f_s * s + 1.0)
            + gain * cmath.exp(-s * tau_s))


def _char_dfn(s, gain, tau_s, tau_c_s, tau_f_s):
    """F'(s)."""
    return (tau_c_s * (tau_f_s * s + 1.0) + tau_f_s * (tau_c_s * s + 1.0)
            - gain * tau_s * cmath.exp(-s * tau_s))


def _newton(s0, gain, tau_s, tau_c_s, tau_f_s, iters=80, tol=1e-13):
    """Karakteristik denklemin kökünü Newton ile cilalar (kalıntı denetimli)."""
    s = complex(s0)
    for _ in range(iters):
        f = _char_fn(s, gain, tau_s, tau_c_s, tau_f_s)
        if abs(f) <= tol:
            return s
        d = _char_dfn(s, gain, tau_s, tau_c_s, tau_f_s)
        if d == 0:
            return None
        step = f / d
        s = s - step
        if not (math.isfinite(s.real) and math.isfinite(s.imag)):
            return None
    return s if abs(_char_fn(s, gain, tau_s, tau_c_s, tau_f_s)) <= 1e-8 else None


def chug_rightmost_root(dp_ratio_j, tau_s, tau_c_s, tau_f_s=0.0):
    """Karakteristik denklemin baskın (en sağdaki) kökü s [1/s] — karmaşık.

    τ_f = 0: kapalı form s = W₀(z)/τ − 1/τ_c (Lambert-W).
    τ_f > 0: aynı kökten başlayıp τ_f'de sürekli izleme (continuation) +
    Newton cilası; kalıntı sağlanmazsa None döner (uydurma sayı üretilmez).
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
        # Gecikmesiz özel hâl: (τ_c s+1)(τ_f s+1) + g = 0 (ikinci mertebe).
        if tau_f == 0.0:
            return complex(-(1.0 + gain) / tau_c, 0.0)
        disc = complex((tau_c + tau_f) ** 2 - 4.0 * tau_c * tau_f
                       * (1.0 + gain))
        root = (-(tau_c + tau_f) + cmath.sqrt(disc)) / (2.0 * tau_c * tau_f)
        return root

    if tau / tau_c > _TAU_RATIO_NUMERIC_LIMIT:
        raise ValueError(
            f'tau/tau_c = {tau / tau_c:.3g} exceeds the numerical range of '
            f'the closed-form root ({_TAU_RATIO_NUMERIC_LIMIT:g}); the '
            f'Lambert-W argument overflows. This is a numerical guard, not a '
            f'physical threshold.')

    z = -(tau / (2.0 * j * tau_c)) * math.exp(tau / tau_c)
    s0 = complex(lambertw(z, 0)) / tau - 1.0 / tau_c
    if tau_f == 0.0:
        return s0

    # Ataletli hâl: τ_f'yi 0'dan hedefe kademeli açıp kökü izle.
    s = s0
    steps = 12
    for k in range(1, steps + 1):
        tf = tau_f * k / steps
        polished = _newton(s, gain, tau, tau_c, tf)
        if polished is None:
            return None
        s = polished
    return s


def assess_chug(dp_ratio_j, tau_s, tau_c_s, tau_f_s=None,
                feed_line=None):
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

    root = chug_rightmost_root(j, tau, tau_c, tau_f)
    growth = None if root is None else float(root.real)
    frequency = (None if root is None
                 else abs(float(root.imag)) / (2.0 * math.pi))

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
