"""Yanma odası akustik mod frekansları (silindirik kamara) + kararlılık marjı.

Yanma kararsızlığı analizinin DÜRÜST temeli: bu modül kapalı-kapalı, rijit
cidarlı silindirik bir yanma odasının akustik öz-frekanslarını hesaplar ve
enjektör basınç düşümü oranına dayalı klasik chug (düşük frekans) marjını
raporlar. Yanma tepki fonksiyonu (basınç/hız kuplajı, n-tau zaman gecikmesi
modelleri) ve Rayleigh kriteri değerlendirmesi MODELLENMEZ — modların NEREDE
olduğu söylenir, yanmanın onları sürükleyip sürüklemeyeceği SÖYLENMEZ. Sınır
`NOT_MODELLED` sözlüğüyle çıktıya konur.

Fizik ve referanslar
--------------------
Ses hızı (ideal gaz, kamara denge özellikleriyle):

    a = sqrt(gamma * R_spesifik * T_c)

      Sutton, G.P. & Biblarz, O., "Rocket Propulsion Elements", 9. baskı,
      Bölüm 3 (ideal lüle teorisi, ideal gaz ses hızı); Anderson, J.D.,
      "Modern Compressible Flow", Bölüm 3.

Rijit cidarlı, iki ucu kapalı silindirik kavitenin öz-frekansları:

    f_mnq = (a / (2*pi)) * sqrt( (2*alpha_mn / D)^2 + (q*pi / L)^2 )

      Kinsler, L.E. & Frey, A.R., "Fundamentals of Acoustics", 4. baskı,
      Bölüm 9 (silindirik kavite rezonatörleri); Harrje, D.T. & Reardon,
      F.H. (ed.), "Liquid Propellant Rocket Combustion Instability",
      NASA SP-194 (1972), Bölüm 3 (kamara akustiği ve mod adlandırması).

  Özel hâller (aynı formülün cebirsel indirgenmeleri):
    - Boyuna (mnq = 00q):   f_qL = q * a / (2*L)          (q = 1, 2, ...)
    - Enine (q = 0):        f_mn = a * alpha_mn / (pi*D)
    - Karma:                f = sqrt(f_enine^2 + f_boyuna^2)

  alpha_mn, J_m Bessel fonksiyonunun TÜREVİNİN köküdür (J'_m(alpha) = 0);
  rijit cidarda radyal parçacık hızının sıfır olması koşulundan gelir.
  Kökler `scipy.special.jnp_zeros` ile hesaplanır, elle yazılmaz. Literatür
  çapaları YALNIZ Abramowitz & Stegun, "Handbook of Mathematical Functions",
  Tablo 9.5'e dayanır: 1T alpha_11 = 1.8412, 2T = 3.0542, 1R = 3.8317,
  2R = 7.0156, 1T1R = 5.3314. (ÖH KU, KU-K5 / SP-H2 6: NASA SP-194 Tablo
  3.5.1, s. 143 bu değerlerin BASILI hâlini farklı verir — 1T 1,8413, 2T
  3,0543, 1T1R 5,3313 son basamak yuvarlaması ve 1T2R 8,5263 baskı hatası
  (doğrusu 8,5363; scipy 8,536316). Çapa ve bekçi o tablodan kopyalanmaz.)
  m = teğetsel (çevresel) indis, n = radyal indis, q = boyuna indis.

Chug (düşük frekans, besleme kuplajlı) marjı:

    oran = dP_enjektör / P_c

  Klasik tasarım kuralı: enjektör basınç düşümü kamara basıncının
  %15-25'i mertebesinde seçilir ki besleme sistemi kamara basınç
  salınımlarından ayrışsın (dekuplaj); oran düştükçe besleme-kamara
  kuplajı (chug) riski artar.
      Sutton & Biblarz, "Rocket Propulsion Elements", 9. baskı, Bölüm 8
      (enjektör basınç düşümü tasarım aralığı) ve Bölüm 9 (yanma
      kararsızlığı türleri); NASA SP-194, Bölüm 5-6 (besleme sistemi
      kuplajlı düşük frekanslı kararsızlık). Eşik MÜHENDİSLİK KURALIDIR,
      keskin bir fizik sınırı değildir ('approximate').

Frekans bandı sınıflandırması (gösterge niteliğinde):

    chug  < ~400 Hz  <  buzz  < ~1000 Hz  <  screech

      Sayıların dayanağı Sutton & Biblarz, 9. baskı, Tablo 9-2, s. 350
      (10-400 / 400-1000 / >1000 Hz). NASA SP-194 §1.2.2, s. 17 bu sayıları
      VERMEZ; yalnız düşük/ara/yüksek frekans sınıfları arasında keskin
      sınır olmadığını ve frekansla sınıflandırmanın karışıklık yarattığını
      söyler (ÖH KU, KU-K5; ikisi de yerel metinden doğrulandı). Sınırlar
      keskin değildir; motor boyutuna göre kayar. Büyük motorlarda 1T modu 1 kHz altına inebilir —
      F-1'de gözlenen 1T "spinning" kararsızlığı 440-540 Hz bandındaydı
      (Oefelein, J.C. & Yang, V., "Comprehensive Review of Liquid-Propellant
      Combustion Instabilities in F-1 Engines", J. Propulsion and Power 9(5),
      1993, s. 657-677; kamara yüz çapı 100 cm).

Girdi adlandırması hibrit motor sonuç şemasıyla uyumludur
(`chamber_temperature` [K], `gamma`, `chamber_diameter` [m],
`chamber_length` [m], `chamber_pressure` [bar]); modül motor kodundan
BAĞIMSIZ çalışır, hiçbir engine modülü ithal edilmez. Tüm kullanıcıya
görünen metinler İngilizce, çıktı JSON-güvenlidir.
"""

import functools
import math
from typing import Dict, List, Optional

from scipy.special import jnp_zeros

__all__ = [
    'AcousticModeAnalyzer',
    'sound_speed',
    'longitudinal_frequency',
    'transverse_root',
    'transverse_frequency',
    'combined_frequency',
    'analyze_from_engine_result',
    'CHUG_DP_RATIO_RECOMMENDED',
    'CHUG_DP_RATIO_MINIMUM',
    'CHUG_DP_RATIO_BAND_MAX',
    'CHUG_THRESHOLD_DEFINITION_POINT',
    'FREQ_BAND_CHUG_MAX_HZ',
    'FREQ_BAND_BUZZ_MAX_HZ',
    'NOT_MODELLED',
]

# Evrensel gaz sabiti [J/(kmol*K)] — CODATA 2018. Molekül ağırlığından
# spesifik gaz sabiti türetirken kullanılır (R = R_u / MW, MW g/mol = kg/kmol).
# ÖH P10B3-10 (tek kaynak): sayı burada TANIMLANMAZ, hrma.constants'tan gelir.
from hrma.constants import R_UNIVERSAL as R_UNIVERSAL_J_KMOL_K  # noqa: E402

# ---------------------------------------------------------------------------
# Kararlılık eşikleri — KANONİK tanım, kaynak künyeli. Başka dosyada bu
# sayıları tekrar YAZMA; buradan ithal et (parametre tutarlılık kuralı).
#
# DÜZELTME (ÖH FAZ B-1, P14 savcı §3.1-7): bu satırlarda eskiden "DEPODAKİ
# TEK SAYISAL TANIM" yazıyordu. YANLIŞTI ve ölçüldü: 0,20/0,15 çifti chug
# ΔP/Pc bağlamında ürün kodunda hâlâ SAYI olarak yaşıyor. Borç o gün 12
# SİTE / 6 DOSYA idi; ÖH Z5S + D20 + D21 üç siteyi tanım noktasına bağladı,
# ÖH D26 (OH-B1-03) ölçümü borcu **7 SİTE / 4 DOSYA** buldu
# (docs/scofield/raw/OH/D26/termo-ucus/a1/once.json, K2):
#   engines/cycle_power_balance.py   INJECTOR_DP_FRAC_GAS_DEFAULT      0,15
#   engines/cycle_power_balance.py   INJECTOR_DP_FRAC_PREBURNER_DEF.   0,15
#   engines/hybrid_rocket_engine.py  delta_P                           0,20
#   engines/hybrid_rocket_engine.py  dp_ratio_ox                       0,20
#   engines/injector_design.py       dp_ratio_ox                       0,20
#   engines/injector_design.py       dp_ratio_fuel                     0,20
#   engines/liquid_rocket_engine.py  INJECTOR_TYPE_DP_FRACTION_DEFAULT 0,20
# Burası KANONİK TANIM NOKTASIDIR, deponun TEK sayısı değildir; borç
# kapanana kadar bu ayrım hem yorumda hem YAYIMLANAN künyede yazılı kalır
# (kalan yedi site engines/ altındadır ve sıvı/katı/hibrit kulvarlarının
# sahasıdır — bu modülden tekilleştirilemez).
# Bekçiler: tests/test_stability_sivi.py::test_chug_esigi_tek_kaynak (eşik
# ADIYLA yeniden doğarsa KIRMIZI) + ::test_chug_orani_DEGER_duzeyinde_
# envanterli (envanter; yeni site de kapanan site de KIRMIZI) +
# ::test_yayimlanan_kunye_TEK_TANIM_diye_yalan_soylemiyor (künye borçla
# çelişirse KIRMIZI).
#
# F2b-2 ÖLÇÜMÜ (17 Ağu 2026) — aynı sayı çifti depoda DÖRT yerde tanımlıydı
# ve İKİ ayrı künyeyle savunuluyordu:
#   1. burası                                    0.20/0.15  Sutton + SP-194
#   2. engines/liquid_rocket_engine.py:452-453   0.15/0.20  SP-8089
#   3. engines/injector_design.py:62-63          0.15/0.20  SP-8089
#   4. analysis/transient_ballistics.py:45       0.15       SP-8089
# (Beşinci site utils/injector_design.py:187'de bir uyarı METNİNİN içinde
# "recommends >=15%" olarak gömülüdür — sabit değil, dize.)
#
# KÜNYE HÜKMÜ (kaynağa inilerek, F2b-2): iki künye ÇELİŞMİYOR, aynı klasik
# tasarım kuralının iki farklı yerde anılmasıdır; ama taşıdıkları kanıt eşit
# DEĞİLDİR ve HRMA'nın künye standardı ikisini ayırmayı gerektirir:
#   * Mekanizmanın kaynağı NASA SP-194 Böl. 5-6'dır (besleme kuplajlı alçak
#     frekans kararsızlığının kendisi orada türetilir) — "neden".
#   * Sayı bandının kaynağı tasarım pratiğidir (Sutton & Biblarz 9. baskı
#     Böl. 8) — "kaç".
#   * NASA SP-8089 (Gill & Nurick, "Liquid Rocket Engine Injectors", Mart
#     1976) bu depoda BELGE olarak doğrulanmıştır (docs/STANDART_ATIFLARI.md,
#     NTRS 19760023196) ama %15-20/%15-25 bandının SP-8089 içinde SAYFA
#     düzeyinde geçtiği bu depoda doğrulanmamıştır. Defterin kendi kuralı
#     ("doğrulayamıyorsan atfı koyma") gereği tek künye SP-8089'a
#     DAYANDIRILMAZ; atıf aşağıda anılır, bandın dayanağı yapılmaz.
# Sayı DEĞİŞMEDİ (0,20/0,15); değişen, dört yerde dört künye yerine tek
# yerde tek künye olmasıdır.
#
# Enjektör basınç düşümü oranı (dP_inj / P_c) tasarım kuralı:
# oran >= 0.20 -> besleme sistemi dekuplajı için tavsiye edilen değer;
# 0.15 <= oran < 0.20 -> marjinal (klasik aralığın alt ucu);
# oran < 0.15 -> chug riski (besleme-kamara kuplajı olası);
# oran >  0.25 -> klasik bandın ÜSTÜ (aşağıya bak).
CHUG_DP_RATIO_RECOMMENDED = 0.20
CHUG_DP_RATIO_MINIMUM = 0.15

# ÖH D26 · defter P4B4-16 — BANDIN ÜST UCU. ÖLÇÜLEN KUSUR (once.json, K4):
# modülün kendi künyesi bandı "15-25% of chamber pressure" diye YAYIMLARKEN
# üst uçta hiçbir kademe yoktu; 0,30 / 0,50 / 1,00 / 1,527 (gerçek hibrit
# koşumunda ölçülen oran) ve 12,0 — BEŞİ de "... meets the recommended
# >= 0.20 design rule" cümlesiyle TEMİZ ``STATUS_OK`` alıyordu. Yani ilan
# edilen bandın 48 katındaki bir tasarım, kullanıcıya bandın aşıldığı
# söylenmeden onaylanıyordu. Klasik kural İKİ TARAFLIDIR: alt uçta chug
# kuplajı, üst uçta besleme basıncı/pompa işi ve enjektör ΔP'sinin gerçekten
# teslim edilebilirliği. Kaynak, alt uçla AYNI: Sutton & Biblarz RPE 9. baskı
# Böl. 8 (%15-25 bandı). Sayı burada TANIMLANIR, başka dosyada yazılmaz.
#
# HÜKÜM AYRIMI (kasıtlı): chug MEKANİZMASI bakımından yüksek oran iyidir, bu
# yüzden ``status`` OK kalır — uydurma bir risk hükmü üretilmez. Değişen,
# hükmün YANINDAKİ beyandır: oran bandın üstündeyse not bunu SÖYLER ve
# ``above_design_band`` / ``design_band_excess_factor`` alanları yayımlanır.
CHUG_DP_RATIO_BAND_MAX = 0.25
CHUG_THRESHOLD_SOURCE = (
    'Injector pressure drop is classically designed at 15-25% of chamber '
    'pressure to decouple the feed system from chamber pressure '
    'oscillations (Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed., '
    'Ch. 8 injector design; NASA SP-194, Harrje & Reardon eds., 1972, '
    'Ch. 5-6 feed-system-coupled low-frequency instability). Engineering '
    'rule of thumb, approximate — not a sharp physical boundary. The band '
    'is TWO-SIDED: below 0.15 the feed system can couple with the chamber '
    '(chug); above 0.25 the drop is outside the classical design range and '
    'is paid for in feed pressure and pump work. This module is the '
    'DEFINITION POINT of the triple (0.15 / 0.20 / 0.25): the liquid engine, '
    'the injector-driven transient solver and hrma.stability.chug import it '
    'from here instead of re-declaring it. It is NOT the only place a '
    'delta_P/Pc number appears in the repository — several engine modules '
    'still carry their own context-specific defaults (per injector type, '
    'per power cycle). That remainder is an explicit, capped and '
    'non-decaying inventory, not a silent second definition: see '
    'tests/test_stability_sivi.py (test_chug_orani_DEGER_duzeyinde_'
    'envanterli). Other parts of '
    'the repository cite NASA SP-8089 (Gill & Nurick, "Liquid Rocket Engine '
    'Injectors", March 1976) for the same band; that document is verified to '
    'exist and to be about injectors (NTRS 19760023196), but the band has '
    'NOT been verified page-by-page inside it in this repository, so the '
    'threshold is not attributed to it. Where this rule falls on the solved '
    'chug neutral curve is measured, not assumed: see '
    'hrma.stability.chug.assess_chug -> classical_rule_cross_check.')

# Kullanıcıya giden KISA künye (rozet/uyarı metni). ÖH D18 (P2B4-08):
# transient çözücüsünün chug uyarısı '(SP-8089)' basıyordu, oysa hemen
# yukarıdaki CHUG_THRESHOLD_SOURCE bu atfı AÇIKÇA geri çekiyor. Kısa künye
# artık eşiğin gerçek dayanağını söyler ve TEK YERDE durur; metni basan her
# yer buradan okur, böylece uzun gerekçe ile kısa künye ayrışamaz.
CHUG_THRESHOLD_CITATION = (
    'Sutton & Biblarz 9th ed. Ch. 8; NASA SP-194 Ch. 5-6')

# ÖH D26 · OH-B1-03 — TANIM NOKTASININ YAPISAL KAYDI.
# Eski künye "depodaki TEK sayısal tanım" diye bir MÜNHASIRLIK iddiası
# taşıyordu ve bu iddia yalnız düzyazıydı: doğrulanamaz, bu yüzden çürüdü
# (ölçüm: 7 site / 4 dosya). Yerine, doğrulanabilir olan yayımlanır —
# tanımın SAHİBİ (modül + sembol adları) ve münhasır OLMADIĞI. Sahiplik
# ithalle sınanabilir; münhasırlık iddiası bir daha kurulmaz.
CHUG_THRESHOLD_DEFINITION_POINT = {
    'module': __name__,
    'symbols': ('CHUG_DP_RATIO_MINIMUM', 'CHUG_DP_RATIO_RECOMMENDED',
                'CHUG_DP_RATIO_BAND_MAX'),
    'exclusive_in_repository': False,
    'exclusivity_note': (
        'This module owns the definition; it is not the only place a '
        'delta_P/Pc number appears in the repository. Modules that still '
        'carry context-specific defaults are tracked as an explicit capped '
        'inventory in tests/test_stability_sivi.py, not assumed away.'),
}

# Frekans bandı sınırları [Hz] — gösterge niteliğinde sınıflandırma.
FREQ_BAND_CHUG_MAX_HZ = 400.0
FREQ_BAND_BUZZ_MAX_HZ = 1000.0
FREQ_BAND_SOURCE = (
    'Indicative classification: chug (low frequency) < ~400 Hz, buzz '
    '(intermediate) ~400-1000 Hz, screech (high frequency, acoustic) '
    '> ~1000 Hz (Sutton & Biblarz, 9th ed., Table 9-2, p. 350: 10-400 / '
    '400-1000 / >1000 Hz). NASA SP-194 (1972) sec. 1.2.2, p. 17 gives no '
    'numbers; it states there is no sharp dividing line between the low, '
    'intermediate and high frequency classes. Boundaries are indicative, '
    'not sharp; large engines can have acoustic modes below 1 kHz — the '
    'F-1 1T instability was observed at 440-540 Hz (Oefelein & Yang, '
    'J. Propulsion and Power 9(5), 1993).')

# ---------------------------------------------------------------------------
# Bilinçli olarak MODELLENMEYENLER. Bu sözlük çıktıya aynen konur;
# "sessizce yok sayıldı" durumu oluşmaz (sahte veri yasağı).
# ---------------------------------------------------------------------------
NOT_MODELLED = {
    'combustion_response': (
        'The combustion response function (pressure/velocity coupling, '
        'n-tau time-lag models) and the Rayleigh criterion evaluation are '
        'NOT modelled. This module reports WHERE the chamber acoustic modes '
        'lie, not WHETHER combustion will drive them unstable.'),
    'damping': (
        'Acoustic damping is NOT modelled: baffles, acoustic cavities/'
        'resonators, nozzle admittance and viscous/particulate losses are '
        'all outside this model. Frequencies are undamped rigid-wall '
        'eigenvalues. Note for transverse modes: the nozzle is not always a '
        'damper - NASA SP-194 (1972) sec. 3.6.2, p. 163 shows it can be '
        'destabilizing for transverse modes, and the linearized nozzle '
        'theory has been verified only for longitudinal modes (p. 165).'),
    'mean_flow_and_gradients': (
        'Mean chamber flow (finite Mach number) and axial temperature/'
        'sound-speed gradients are NOT modelled; a uniform quiescent gas at '
        'chamber equilibrium conditions is assumed. Measured transverse '
        'frequencies typically fall BELOW this estimate because the gas '
        'near the injector face is cooler than the equilibrium value '
        '(F-1: observed 1T 440-540 Hz vs the uniform hot-gas estimate; '
        'Oefelein & Yang 1993).'),
}


# ===========================================================================
# Modül-düzeyi saf fonksiyonlar (analitik, test edilebilir)
# ===========================================================================
def sound_speed(gamma: float, gas_constant: float,
                chamber_temperature: float) -> float:
    """İdeal gaz ses hızı a = sqrt(gamma * R * T_c) [m/s].

    Kaynak: Sutton & Biblarz, RPE 9. baskı, Bölüm 3 (ideal gaz);
    Anderson, "Modern Compressible Flow", Bölüm 3.
    """
    for name, val, lo in (('gamma', gamma, 1.0),
                          ('gas_constant', gas_constant, 0.0),
                          ('chamber_temperature', chamber_temperature, 0.0)):
        if not (isinstance(val, (int, float)) and math.isfinite(val)
                and val > lo):
            raise ValueError(
                f"{name} must be a finite value > {lo:g} (got {val!r}).")
    return math.sqrt(gamma * gas_constant * chamber_temperature)


def longitudinal_frequency(a: float, chamber_length: float, q: int) -> float:
    """Kapalı-kapalı boyuna mod frekansı f_qL = q * a / (2 * L) [Hz].

    Kaynak: Kinsler & Frey, "Fundamentals of Acoustics", 4. baskı, Bölüm 9;
    NASA SP-194, Bölüm 3.
    """
    if not (isinstance(a, (int, float)) and math.isfinite(a) and a > 0):
        raise ValueError(f"sound speed a must be positive [m/s] (got {a!r}).")
    if not (isinstance(chamber_length, (int, float))
            and math.isfinite(chamber_length) and chamber_length > 0):
        raise ValueError(
            f"chamber_length must be positive [m] (got {chamber_length!r}).")
    if not (isinstance(q, int) and q >= 1):
        raise ValueError(
            f"longitudinal index q must be an integer >= 1 (got {q!r}).")
    return q * a / (2.0 * chamber_length)


@functools.lru_cache(maxsize=4096)
def transverse_root(m_tangential: int, n_radial: int) -> float:
    """Boyutsuz enine mod kökü alpha_mn: J'_m'in sıfırı (rijit cidar).

    ÖH D26 / P4B4-14: havuz artık kesim frekansına göre BÜYÜTÜLDÜĞÜ için
    aynı (m, n) kökü bir analizde defalarca istenir. ``lru_cache`` yalnız
    tekrarları eler — dönen değer ``jnp_zeros``un verdiğinin AYNISIDIR
    (saf fonksiyon, girdi = iki tamsayı), sayısal etkisi yoktur.

    m_tangential = teğetsel (çevresel) indis m >= 0,
    n_radial = radyal indis n >= 0; (m, n) = (0, 0) enine bileşen yok
    demektir ve burada anlamsızdır -> ValueError.

    Eşleme (`scipy.special.jnp_zeros(m, k)` J'_m'in ilk k sıfırını verir,
    m = 0 için x = 0 trivial kökü atlanmıştır):
      - saf teğetsel mT      (n=0): alpha = jnp_zeros(m, 1)[0]
      - saf radyal nR        (m=0): alpha = jnp_zeros(0, n)[n-1]
      - teğetsel-radyal mTnR      : alpha = jnp_zeros(m, n+1)[n]

    Literatür çapaları (YALNIZ Abramowitz & Stegun Tablo 9.5; NASA SP-194
    Tablo 3.5.1'in basılı değerleri son basamakta farklı ve 1T2R'de baskı
    hatası var — bkz. modül başı notu):
    1T = 1.8412, 2T = 3.0542, 1R = 3.8317, 2R = 7.0156, 1T1R = 5.3314.
    """
    if not (isinstance(m_tangential, int) and m_tangential >= 0):
        raise ValueError(
            f"m_tangential must be an integer >= 0 (got {m_tangential!r}).")
    if not (isinstance(n_radial, int) and n_radial >= 0):
        raise ValueError(
            f"n_radial must be an integer >= 0 (got {n_radial!r}).")
    if m_tangential == 0 and n_radial == 0:
        raise ValueError(
            "(m, n) = (0, 0) has no transverse component — use "
            "longitudinal_frequency for pure longitudinal modes.")
    if m_tangential == 0:
        # Saf radyal: J'_0'ın n'inci sıfırı (scipy trivial x=0'ı atlar).
        return float(jnp_zeros(0, n_radial)[n_radial - 1])
    # Saf teğetsel (n=0) veya teğetsel-radyal (n>=1).
    return float(jnp_zeros(m_tangential, n_radial + 1)[n_radial])


def transverse_frequency(a: float, chamber_diameter: float,
                         alpha: float) -> float:
    """Enine (teğetsel/radyal) mod frekansı f = a * alpha / (pi * D) [Hz].

    Kaynak: NASA SP-194, Bölüm 3 (f = a*alpha_mn/(2*pi*R_c), R_c = D/2);
    Kinsler & Frey, Bölüm 9.
    """
    if not (isinstance(a, (int, float)) and math.isfinite(a) and a > 0):
        raise ValueError(f"sound speed a must be positive [m/s] (got {a!r}).")
    if not (isinstance(chamber_diameter, (int, float))
            and math.isfinite(chamber_diameter) and chamber_diameter > 0):
        raise ValueError(
            f"chamber_diameter must be positive [m] "
            f"(got {chamber_diameter!r}).")
    if not (isinstance(alpha, (int, float)) and math.isfinite(alpha)
            and alpha > 0):
        raise ValueError(f"alpha must be positive (got {alpha!r}).")
    return a * alpha / (math.pi * chamber_diameter)


def combined_frequency(f_transverse: float, f_longitudinal: float) -> float:
    """Karma mod frekansı f = sqrt(f_enine^2 + f_boyuna^2) [Hz].

    Silindirik kavitede öz-değerler dik bileşenlerin kareleri toplamıdır
    (ayrışabilir Helmholtz problemi). Kaynak: Kinsler & Frey, Bölüm 9.
    """
    for name, val in (('f_transverse', f_transverse),
                      ('f_longitudinal', f_longitudinal)):
        if not (isinstance(val, (int, float)) and math.isfinite(val)
                and val >= 0):
            raise ValueError(
                f"{name} must be a non-negative frequency [Hz] (got {val!r}).")
    return math.hypot(f_transverse, f_longitudinal)


def _frequency_band(freq_hz: float) -> str:
    """Frekansı gösterge bandına sınıfla (FREQ_BAND_SOURCE künyeli)."""
    if freq_hz < FREQ_BAND_CHUG_MAX_HZ:
        return 'chug_range'
    if freq_hz < FREQ_BAND_BUZZ_MAX_HZ:
        return 'buzz_range'
    return 'screech_range'


# ===========================================================================
# Analiz sınıfı
# ===========================================================================
class AcousticModeAnalyzer:
    """Silindirik yanma odası akustik mod tablosu + kararlılık marjı raporu.

    Girdi adları hibrit motor sonuç şemasıyla uyumludur (chamber_temperature,
    gamma, chamber_diameter, chamber_length, chamber_pressure); modül motor
    kodundan bağımsızdır.
    """

    STATUS_OK = 'OK'
    STATUS_MARGINAL = 'MARGINAL'
    STATUS_AT_RISK = 'AT_RISK'
    STATUS_NOT_EVALUATED = 'NOT_EVALUATED'

    # -----------------------------------------------------------------
    # Mod havuzu sınırları — ÖH D26 / defter P4B4-14
    # -----------------------------------------------------------------
    # ÖLÇÜLEN KUSUR (once.json, K3): bu üç sayı SABİT TAVAN'dı ve havuz
    # onlarla KIRPILIYORDU. "En düşük N mod" listesi bu yüzden uzun/ince
    # kavitelerde GERÇEK modları düşürüyordu: D=0,20 m, L=2,5 m, T=2000 K,
    # gamma=1,2, R=300 (a=848,53 m/s), n_modes=10 -> tablonun kendi en
    # yüksek frekansı 2538,06 Hz (1T3L) iken 7L..14L (1187,9-2375,9 Hz)
    # SEKİZ gerçek boyuna mod listeye HİÇ giremiyordu. n_modes=200 istense
    # bile havuz 83 modda tükeniyordu: kırpma n_modes ile aşılamıyordu.
    # Aynı geometride kayıp 84 moda kadar çıkıyordu. Kırpma modu FİZİKTEN
    # değil SABİTTEN düşürüyordu ve screech hükmü bu eksik havuzdan
    # türüyordu.
    #
    # ONARIM: bu üç sayı artık TAVAN değil TOHUM'dur. Havuz, tablonun
    # kendi kesim frekansı f_cut'un altında kalan HİÇBİR gerçek mod dışarıda
    # kalmayacak biçimde büyütülür (bkz. ``_build_mode_table``):
    #   boyuna   f_qL = q*a/(2L) <= f_cut  <=>  q <= f_cut*2L/a
    #   enine    f_mn = a*alpha_mn/(pi*D) <= f_cut  <=>  alpha_mn <= f_cut*pi*D/a
    # J'_m köklerinin hem m hem n ile monoton artması sayesinde m ve n
    # tavanlarını bağımsız aramak YETERLİDİR (alpha_{m,0} <= alpha_{m,n} ve
    # alpha_{0,n} <= alpha_{m,n}).
    MAX_TANGENTIAL_INDEX = 3
    MAX_RADIAL_INDEX = 2
    MAX_LONGITUDINAL_INDEX = 6

    # Güvenlik tavanları: büyütme sonsuza gitmez. Tavan gerçekten bağlarsa
    # bu SESSİZ KALMAZ -> ``mode_pool.truncated`` True olur ve hem
    # ``mode_table_basis`` hem screech notu kırpmayı BEYAN eder.
    POOL_HARD_MAX_TANGENTIAL = 40
    POOL_HARD_MAX_RADIAL = 40
    POOL_HARD_MAX_LONGITUDINAL = 4000
    POOL_HARD_MAX_CANDIDATES = 40000
    POOL_MAX_GROWTH_STEPS = 24

    def analyze(self,
                chamber_temperature: float,
                gamma: float,
                gas_constant: float,
                chamber_diameter: float,
                chamber_length: float,
                chamber_pressure: Optional[float] = None,
                injector_pressure_drop_bar: Optional[float] = None,
                injector_dp_ratio: Optional[float] = None,
                n_modes: int = 10) -> Dict:
        """Mod tablosu + chug marjı raporu üret (JSON-güvenli sözlük).

        Parameters
        ----------
        chamber_temperature : float
            Kamara denge sıcaklığı T_c [K] (hibrit şema alanı).
        gamma : float
            İzantropik üs (> 1) (hibrit şema alanı).
        gas_constant : float
            Spesifik gaz sabiti R [J/(kg*K)]. Motor sonucunda yoksa
            molekül ağırlığından türet: R = 8314.462618 / MW[g/mol]
            (bkz. analyze_from_engine_result).
        chamber_diameter, chamber_length : float
            Kamara iç çapı D [m] ve boyu L [m] (hibrit şema alanları).
        chamber_pressure : float, optional
            Kamara basıncı P_c [bar] — yalnız chug oranı için gerekir.
        injector_pressure_drop_bar : float, optional
            Enjektör basınç düşümü dP_inj [bar].
        injector_dp_ratio : float, optional
            dP_inj / P_c oranı doğrudan verilirse basınçlara gerek kalmaz
            (öncelikli).
        n_modes : int
            Tabloya konacak en düşük frekanslı mod sayısı (varsayılan 10).
        """
        # --- girdi doğrulama (İngilizce hata metinleri) ---
        a = sound_speed(gamma, gas_constant, chamber_temperature)
        for name, val in (('chamber_diameter', chamber_diameter),
                          ('chamber_length', chamber_length)):
            if not (isinstance(val, (int, float)) and math.isfinite(val)
                    and val > 0):
                raise ValueError(
                    f"{name} must be a positive finite length [m] "
                    f"(got {val!r}).")
        if not (isinstance(n_modes, int) and n_modes >= 1):
            raise ValueError(
                f"n_modes must be an integer >= 1 (got {n_modes!r}).")

        D = float(chamber_diameter)
        L = float(chamber_length)

        # --- mod havuzu: (m, n, q) kombinasyonları, frekansa göre sırala ---
        modes, mode_pool = self._build_mode_table(a, D, L, n_modes)

        # --- chug (besleme kuplajlı düşük frekans) marjı ---
        chug = self._chug_report(chamber_pressure,
                                 injector_pressure_drop_bar,
                                 injector_dp_ratio)

        # --- yüksek frekans (screech) adayları ---
        screech_labels = [m['label'] for m in modes
                          if m['band'] == 'screech_range']
        sub_screech_transverse = [
            m['label'] for m in modes
            if m['band'] != 'screech_range'
            and m['indices']['longitudinal_q'] == 0]

        high_freq = {
            'screech_band_min_hz': FREQ_BAND_BUZZ_MAX_HZ,
            'modes_in_screech_band': screech_labels,
            'transverse_modes_below_screech_band': sub_screech_transverse,
            'band_source': FREQ_BAND_SOURCE,
            # ÖH D26 / P4B4-14: bu hüküm mod havuzundan TÜRER; havuzun
            # eksiksiz olduğu (ya da kırpıldığı) hükmün yanında durur.
            'mode_pool_complete_below_hz': mode_pool['complete_below_hz'],
            'mode_pool_truncated': mode_pool['truncated'],
            # Enine aday, "en düşük N mod" listesine girmese bile ADIYLA
            # yayımlanır: 1T tarihsel olarak en yıkıcı moddur ve uzun/ince
            # kavitede listeye girmemesi "yok" demek değildir.
            'lowest_transverse_mode': mode_pool['lowest_transverse_mode'],
            'note': (
                'Transverse modes (especially 1T) are historically the most '
                'destructive in large engines (F-1 1T spinning instability, '
                'Oefelein & Yang 1993). Mode frequencies listed here are '
                'CANDIDATE resonances only — whether combustion drives them '
                'is NOT modelled (see not_modelled.combustion_response). '
                + ('WARNING: the candidate pool was TRUNCATED by its safety '
                   'caps, so real modes below the highest listed frequency '
                   'may be missing from this verdict.'
                   if mode_pool['truncated'] else
                   'This verdict is derived from a mode pool that is '
                   'complete below the highest listed frequency '
                   f'({mode_pool["complete_below_hz"]:.1f} Hz): no real '
                   'mode of the model was dropped by an index cap.')),
        }

        # --- çıktı (JSON-güvenli) ---
        return {
            'model': 'closed_closed_rigid_cylinder_acoustic_modes',
            'sound_speed_m_s': float(a),
            'sound_speed_basis': (
                'a = sqrt(gamma * R_specific * T_c), ideal gas at chamber '
                'equilibrium conditions (Sutton & Biblarz, RPE 9th ed., '
                'Ch. 3; Anderson, Modern Compressible Flow, Ch. 3).'),
            'modes': modes,
            'mode_table_basis': (
                'Rigid-wall closed-closed cylindrical cavity eigenfrequencies '
                'f_mnq = (a/(2*pi)) * sqrt((2*alpha_mn/D)^2 + (q*pi/L)^2); '
                'alpha_mn are zeros of the Bessel derivative J\'_m computed '
                'with scipy.special.jnp_zeros (Kinsler & Frey, Fundamentals '
                'of Acoustics, 4th ed., Ch. 9; NASA SP-194, Ch. 3). Lowest '
                f'{len(modes)} modes of the '
                f'(m<={mode_pool["tangential_max_m"]}, '
                f'n<={mode_pool["radial_max_n"]}, '
                f'q<={mode_pool["longitudinal_max_q"]}) pool. '
                + mode_pool['basis']),
            # ÖH D26 / P4B4-14: havuzun GERÇEK sınırları ve eksiksizlik
            # beyanı çıktıya konur; "en düşük N mod" listesinin neyi
            # kapsadığı kullanıcıdan gizlenmez.
            'mode_pool': mode_pool,
            'stability_report': {
                'chug': chug,
                'high_frequency': high_freq,
            },
            'not_modelled': dict(NOT_MODELLED),
            'inputs': {
                'chamber_temperature': float(chamber_temperature),
                'gamma': float(gamma),
                'gas_constant': float(gas_constant),
                'chamber_diameter': D,
                'chamber_length': L,
                'chamber_pressure': (None if chamber_pressure is None
                                     else float(chamber_pressure)),
                'injector_pressure_drop_bar': (
                    None if injector_pressure_drop_bar is None
                    else float(injector_pressure_drop_bar)),
                'injector_dp_ratio': (None if injector_dp_ratio is None
                                      else float(injector_dp_ratio)),
                'n_modes': int(n_modes),
            },
        }

    # ------------------------------------------------------------------
    def _needed_caps(self, a: float, D: float, L: float,
                     f_cut: float) -> tuple:
        """``f_cut`` altındaki HER gerçek modu kapsayan (m, n, q) tavanları.

        Kapalı formdan türetilir (uydurma yok):
          boyuna  f_qL = q*a/(2L)            -> q_max = floor(f_cut*2L/a)
          enine   f_mn = a*alpha_mn/(pi*D)   -> alpha_mn <= f_cut*pi*D/a
        J'_m köklerinin m ve n ile monoton artması sayesinde m ve n
        tavanları bağımsız aranabilir.

        ÖH D29 / OH-D28-01 — DÖRDÜNCÜ DÖNÜŞ DEĞERİ: ``ihtiyac_doydu``.
        Enine aramalar güvenlik tavanında DURUR (``while m_max <
        POOL_HARD_MAX_TANGENTIAL``), yani gerçek ihtiyaç tavanın üstündeyse
        döndürülen sayı ihtiyacı DEĞİL tavanı gösterir. Çağıran bunu
        ``m_need > m_cap`` kıyasıyla anlayamaz (ikisi de tavana eşittir) ve
        havuz eksik kaldığı hâlde ``truncated`` False kalıyordu — ÖLÇÜLDÜ
        (docs/scofield/raw/OH/D29/termo-ucus/a1/once_d2801.json, K6):
        D=1,20 m / L=1,00 m, enine güvenlik tavanı 2/1 iken 3T modu
        (1250,91 Hz) kesim frekansının (1444,65 Hz) ALTINDA kaldığı hâlde
        havuza giremiyor, buna rağmen yanıt ``truncated=false`` ve
        ``complete_below_hz=1444,65`` diyordu. Boyuna ailede bu kusur
        YOKTUR: ``q_max`` kapalı formdan KIRPILMADAN gelir, bu yüzden
        doyma ``q_need > q_cap`` kıyasıyla zaten görülür.
        """
        q_max = int(math.floor(f_cut * 2.0 * L / a + 1e-9))
        alpha_max = f_cut * math.pi * D / a
        m_max = 0
        while (m_max < self.POOL_HARD_MAX_TANGENTIAL
               and transverse_root(m_max + 1, 0) <= alpha_max):
            m_max += 1
        m_doydu = (m_max >= self.POOL_HARD_MAX_TANGENTIAL
                   and transverse_root(m_max + 1, 0) <= alpha_max)
        n_max = 0
        while (n_max < self.POOL_HARD_MAX_RADIAL
               and transverse_root(0, n_max + 1) <= alpha_max):
            n_max += 1
        n_doydu = (n_max >= self.POOL_HARD_MAX_RADIAL
                   and transverse_root(0, n_max + 1) <= alpha_max)
        return m_max, n_max, q_max, bool(m_doydu or n_doydu)

    # ------------------------------------------------------------------
    def _build_mode_table(self, a: float, D: float, L: float,
                          n_modes: int) -> tuple:
        """Frekansa göre sıralı ilk ``n_modes`` mod + havuz künyesi.

        ÖH D26 / P4B4-14: havuz artık SABİT tavanlarla kırpılmaz. Tohum
        tavanlarla kurulan havuzdan kesim frekansı okunur, o frekansın
        altında kalan her gerçek modu kapsayacak tavanlar kapalı formdan
        türetilir ve havuz yeniden kurulur; süreç sabit noktaya oturana
        kadar (en çok ``POOL_MAX_GROWTH_STEPS``) tekrarlanır. Güvenlik
        tavanı gerçekten bağlarsa sonuç ``truncated=True`` ile BEYAN edilir.
        """
        m_cap = self.MAX_TANGENTIAL_INDEX
        n_cap = self.MAX_RADIAL_INDEX
        q_cap = self.MAX_LONGITUDINAL_INDEX
        candidates: List[Dict] = []
        truncated = False
        for _adim in range(self.POOL_MAX_GROWTH_STEPS):
            candidates = self._pool(a, D, L, m_cap, n_cap, q_cap)
            kesim = candidates[min(n_modes, len(candidates)) - 1]
            f_cut = kesim['frequency_hz']
            m_need, n_need, q_need, ihtiyac_doydu = self._needed_caps(
                a, D, L, f_cut)
            # Talep havuzdan büyükse (n_modes > havuz) tavanları da büyüt:
            # aksi hâlde kesim frekansı havuzun en üstünde takılı kalır.
            if len(candidates) < n_modes:
                m_need = max(m_need, m_cap + 1)
                n_need = max(n_need, n_cap + 1)
                q_need = max(q_need, 2 * q_cap + 1)
            m_yeni = min(max(m_cap, m_need), self.POOL_HARD_MAX_TANGENTIAL)
            n_yeni = min(max(n_cap, n_need), self.POOL_HARD_MAX_RADIAL)
            q_yeni = min(max(q_cap, q_need), self.POOL_HARD_MAX_LONGITUDINAL)
            if (m_yeni, n_yeni, q_yeni) == (m_cap, n_cap, q_cap):
                # Sabit nokta: ya havuz eksiksiz ya da güvenlik tavanı bağlı.
                # ÖH D29 / OH-D28-01: ``ihtiyac_doydu`` DÖRDÜNCÜ KOŞULDUR ve
                # sessiz eksikliği kapatır — enine ihtiyaç araması güvenlik
                # tavanında doyduğunda ``m_need``/``n_need`` tavana EŞİT
                # döner, dolayısıyla ilk üç kıyas False verir ve havuz eksik
                # olduğu hâlde "eksiksiz" beyan edilirdi (fail-closed ihlali;
                # ölçüm: once_d2801.json K6).
                truncated = (m_need > m_cap or n_need > n_cap
                             or q_need > q_cap or ihtiyac_doydu)
                break
            if ((m_yeni + 1) * (n_yeni + 1) * (q_yeni + 1)
                    > self.POOL_HARD_MAX_CANDIDATES):
                truncated = True
                break
            m_cap, n_cap, q_cap = m_yeni, n_yeni, q_yeni
        else:
            truncated = True

        modes = candidates[:n_modes]
        f_cut = (modes[-1]['frequency_hz'] if modes else 0.0)
        # ÖH D26 / P4B4-14 YAN ETKİSİ (bilerek, beyanlı): havuz eksiksiz
        # olunca uzun/ince kavitede "en düşük N mod" listesi SAF BOYUNA
        # çıkabilir — çünkü gerçekten öyledir (katı motor orantısında ilk
        # on mod 1L..10L; 1T 2486,6 Hz'dedir). Eskiden listede enine mod
        # görünmesinin sebebi fizik değil, 7L..14L'in kırpılmasıydı.
        # Enine aday bilgisi KAYBOLMASIN diye havuzun en düşük enine modu
        # (q = 0, m veya n >= 1) her hâlükârda ADIYLA yayımlanır.
        _enine = [c for c in candidates
                  if c['indices']['longitudinal_q'] == 0]
        _tablodaki = {m['label'] for m in modes}
        en_dusuk_enine = (None if not _enine else {
            'label': _enine[0]['label'],
            'frequency_hz': _enine[0]['frequency_hz'],
            'band': _enine[0]['band'],
            'in_mode_table': _enine[0]['label'] in _tablodaki,
        })
        # ÖH D29 / OH-D28-01 — YAYIMLANAN TAVANIN KAYNAĞI ADIYLA DURUR.
        # Büyütme döngüsü tavanı yalnız BÜYÜTÜR (``max(cap, need)``), tohumun
        # ALTINA indirmez; bu yüzden ince/uzun kavitede enine ihtiyaç 0 olsa
        # bile yayımlanan tavan tohum tabanında durur. Okuyucu "analiz m=3'e
        # kadar mod GEREKTİ" sanmasın diye tavanın tohumdan mı geldiği yoksa
        # büyütülmüş mü olduğu her aile için makine okur biçimde beyan edilir.
        tohum = {'tangential_max_m': self.MAX_TANGENTIAL_INDEX,
                 'radial_max_n': self.MAX_RADIAL_INDEX,
                 'longitudinal_max_q': self.MAX_LONGITUDINAL_INDEX}
        yayimlanan_tavan = {'tangential_max_m': m_cap, 'radial_max_n': n_cap,
                            'longitudinal_max_q': q_cap}
        havuz = {
            'tangential_max_m': m_cap,
            'radial_max_n': n_cap,
            'longitudinal_max_q': q_cap,
            'cap_source': {
                k: ('grown_beyond_seed' if yayimlanan_tavan[k] > tohum[k]
                    else 'seed_floor')
                for k in tohum},
            'cap_basis': (
                'The published caps are the pool bounds actually used. They '
                'are grown from the declared seeds by the closed-form '
                'completeness condition and are NEVER shrunk below them, so '
                'a cap reading "seed_floor" in cap_source means the cavity '
                'needed FEWER indices than the seed, not more: the extra '
                'candidates are harmless and keep the transverse family '
                'represented (see lowest_transverse_mode). A cap is a step '
                'function of the cavity aspect ratio, not a fitted number - '
                'measured: D=0.15 m / L=1.00 m keeps m at the seed 3, while '
                'D=1.20 m / L=0.10 m grows it to 8.'),
            'seed_bounds': dict(tohum),
            'seed_bounds_basis': (
                'Declared search seeds of the analyser '
                '(AcousticModeAnalyzer.MAX_TANGENTIAL_INDEX / '
                'MAX_RADIAL_INDEX / MAX_LONGITUDINAL_INDEX), published so '
                'that the starting point of the growth is auditable. They '
                'are the single definition point of the seeds - the leaves '
                'follow the class attributes, they are not written into the '
                'response - and they are a floor, not a ceiling.'),
            'candidate_count': len(candidates),
            'requested_n_modes': int(n_modes),
            'returned_n_modes': len(modes),
            'mode_count_basis': (
                'requested_n_modes is the caller grid size (the engine asks '
                'for the lowest 10 modes; no input field feeds it, exactly '
                'like inputs.n_modes). returned_n_modes = min(requested, '
                'candidate_count) and the two can only differ when the '
                'candidate pool itself is smaller than the request, which '
                'always comes with truncated=true.'),
            'lowest_transverse_mode': en_dusuk_enine,
            'complete_below_hz': (None if truncated else float(f_cut)),
            'truncated': bool(truncated),
            'basis': (
                'The pool is grown until no real mode below the highest '
                'listed frequency can be missing: q <= f_cut*2L/a for the '
                'longitudinal family and alpha_mn <= f_cut*pi*D/a for the '
                'transverse family (closed form, Kinsler & Frey Ch. 9). '
                'Fixed index caps would drop real modes in long/slender '
                'cavities and no requested n_modes could recover them.'
                if not truncated else
                'TRUNCATED: the safety caps on the candidate pool bound the '
                'search before completeness was reached, so real modes below '
                'the highest listed frequency MAY be missing. The mode list '
                'and every verdict derived from it (screech candidates) are '
                'incomplete and this is declared rather than hidden.'),
        }
        return modes, havuz

    # ------------------------------------------------------------------
    def _pool(self, a: float, D: float, L: float,
              m_cap: int, n_cap: int, q_cap: int) -> List[Dict]:
        """(m, n, q) havuzunu verilen tavanlarla üret ve frekansa göre sırala."""
        candidates: List[Dict] = []
        for m in range(0, m_cap + 1):
            for n in range(0, n_cap + 1):
                for q in range(0, q_cap + 1):
                    if m == 0 and n == 0 and q == 0:
                        continue  # DC — mod değil
                    if m == 0 and n == 0:
                        # Saf boyuna
                        alpha = None
                        f_t = 0.0
                    else:
                        alpha = transverse_root(m, n)
                        f_t = transverse_frequency(a, D, alpha)
                    f_l = (longitudinal_frequency(a, L, q) if q >= 1 else 0.0)
                    freq = combined_frequency(f_t, f_l)

                    label_parts = []
                    type_parts = []
                    if m >= 1:
                        label_parts.append(f'{m}T')
                        type_parts.append('tangential')
                    if n >= 1:
                        label_parts.append(f'{n}R')
                        type_parts.append('radial')
                    if q >= 1:
                        label_parts.append(f'{q}L')
                        type_parts.append('longitudinal')

                    candidates.append({
                        'label': ''.join(label_parts),
                        'type': '_'.join(type_parts),
                        'frequency_hz': float(freq),
                        # Boyutsuz Bessel türev kökü; saf boyuna modda enine
                        # bileşen olmadığı için None (uydurma 0 yazılmaz).
                        'alpha': (None if alpha is None else float(alpha)),
                        'indices': {'tangential_m': m, 'radial_n': n,
                                    'longitudinal_q': q},
                        'band': _frequency_band(freq),
                    })
        candidates.sort(key=lambda mode: (mode['frequency_hz'],
                                          mode['indices']['tangential_m'],
                                          mode['indices']['radial_n'],
                                          mode['indices']['longitudinal_q']))
        return candidates

    # ------------------------------------------------------------------
    def _chug_report(self, chamber_pressure: Optional[float],
                     injector_pressure_drop_bar: Optional[float],
                     injector_dp_ratio: Optional[float]) -> Dict:
        """dP_inj/P_c oranına dayalı klasik chug marjı hükmü."""
        ratio: Optional[float] = None
        ratio_source: Optional[str] = None

        if injector_dp_ratio is not None:
            if not (isinstance(injector_dp_ratio, (int, float))
                    and math.isfinite(injector_dp_ratio)
                    and injector_dp_ratio > 0):
                raise ValueError(
                    "injector_dp_ratio must be a positive finite ratio "
                    f"(got {injector_dp_ratio!r}).")
            ratio = float(injector_dp_ratio)
            ratio_source = 'user_supplied_ratio'
        elif (injector_pressure_drop_bar is not None
              and chamber_pressure is not None):
            for name, val in (
                    ('injector_pressure_drop_bar', injector_pressure_drop_bar),
                    ('chamber_pressure', chamber_pressure)):
                if not (isinstance(val, (int, float)) and math.isfinite(val)
                        and val > 0):
                    raise ValueError(
                        f"{name} must be a positive finite pressure [bar] "
                        f"(got {val!r}).")
            ratio = float(injector_pressure_drop_bar) / float(chamber_pressure)
            ratio_source = 'delta_p_over_pc'

        if ratio is None:
            status = self.STATUS_NOT_EVALUATED
            note = ('Chug margin NOT evaluated: supply injector_dp_ratio, or '
                    'both injector_pressure_drop_bar and chamber_pressure '
                    '[bar]. No verdict is fabricated without the input.')
        elif ratio >= CHUG_DP_RATIO_RECOMMENDED:
            status = self.STATUS_OK
            note = (f'Injector pressure drop ratio {ratio:.3f} meets the '
                    f'recommended >= {CHUG_DP_RATIO_RECOMMENDED:.2f} design '
                    'rule — feed system is classically considered decoupled '
                    'from chamber pressure oscillations.')
            # ÖH D26 / P4B4-16: bandın ÜST ucu. Chug mekanizması bakımından
            # hüküm OK kalır (yüksek ΔP dekuplajı güçlendirir, uydurma bir
            # risk üretilmez); ama oran modülün KENDİ ilan ettiği klasik
            # bandın dışına çıkmışsa bu SÖYLENİR — eskiden 12,0 bile
            # "meets the recommended" cümlesiyle temiz geçiyordu.
            if ratio > CHUG_DP_RATIO_BAND_MAX:
                note += (
                    f' NOTE: the ratio also EXCEEDS the upper bound of the '
                    f'classical design band '
                    f'({CHUG_DP_RATIO_MINIMUM:.2f}-'
                    f'{CHUG_DP_RATIO_BAND_MAX:.2f}) by a factor of '
                    f'{ratio / CHUG_DP_RATIO_BAND_MAX:.2f}. The band is a '
                    'two-sided design rule: a drop this large buys chug '
                    'margin but is paid for in feed pressure, pump work and '
                    'injector structural load, and a ratio at or above 1.0 '
                    'means the injector drop equals or exceeds chamber '
                    'pressure — check that the input is the RATIO '
                    'dP_inj/P_c and that it is intended. Chug decoupling '
                    'itself is not in question here.')
        elif ratio >= CHUG_DP_RATIO_MINIMUM:
            status = self.STATUS_MARGINAL
            note = (f'Injector pressure drop ratio {ratio:.3f} sits in the '
                    f'marginal band [{CHUG_DP_RATIO_MINIMUM:.2f}, '
                    f'{CHUG_DP_RATIO_RECOMMENDED:.2f}) — the low end of the '
                    'classical design range; chug margin is thin, especially '
                    'at throttled (low-Pc) conditions.')
        else:
            status = self.STATUS_AT_RISK
            note = (f'Injector pressure drop ratio {ratio:.3f} is below the '
                    f'classical minimum {CHUG_DP_RATIO_MINIMUM:.2f} — the '
                    'feed system can couple with chamber pressure '
                    '(chug, low-frequency instability). Increase injector '
                    'pressure drop or reduce chamber pressure excursions.')

        band_ustunde = (ratio is not None
                        and ratio > CHUG_DP_RATIO_BAND_MAX)
        return {
            'evaluated': ratio is not None,
            'injector_dp_ratio': (None if ratio is None else float(ratio)),
            'ratio_source': ratio_source,
            'recommended_min_ratio': CHUG_DP_RATIO_RECOMMENDED,
            'hard_min_ratio': CHUG_DP_RATIO_MINIMUM,
            # ÖH D26 / P4B4-16: bandın üst ucu artık ALAN olarak yayımlanır;
            # eskiden yalnız künye düzyazısında geçiyordu, bu yüzden hiçbir
            # tüketici (panel, rapor, bekçi) üst ucu görmüyordu.
            'design_band_min_ratio': CHUG_DP_RATIO_MINIMUM,
            'design_band_max_ratio': CHUG_DP_RATIO_BAND_MAX,
            # ÖH D29 / OH-D28-01: bandın iki ucu YAYIMLANAN EŞİKTİR ve
            # künyesi yaprağın yanında durur — "hesaplanmış ama girdiye
            # bağlanmamış" bir sayı değildir.
            'design_band_basis': (
                'Both ends are declared design-rule thresholds read from '
                'the single definition point named in '
                'threshold_definition_point (CHUG_DP_RATIO_MINIMUM and '
                'CHUG_DP_RATIO_BAND_MAX); design_band_min_ratio is the same '
                'declared minimum as hard_min_ratio, published a second '
                'time as the lower end of the band rather than duplicated '
                'as a new number. A threshold that moved with the design '
                'inputs would not be a threshold. What IS computed here is '
                'the verdict against the band: injector_dp_ratio, status '
                'and design_band_excess_factor.'),
            'above_design_band': band_ustunde,
            'design_band_excess_factor': (
                float(ratio / CHUG_DP_RATIO_BAND_MAX) if band_ustunde
                else None),
            'threshold_source': CHUG_THRESHOLD_SOURCE,
            # ÖH D26 / OH-B1-03: münhasırlık iddiası düzyazıdan çıkarıldı;
            # yerine tanımın sahibi YAPISAL olarak yayımlanır.
            'threshold_definition_point': {
                k: (list(v) if isinstance(v, tuple) else v)
                for k, v in CHUG_THRESHOLD_DEFINITION_POINT.items()},
            'status': status,
            'note': note,
        }


# ===========================================================================
# Motor sonucu adaptörü (hibrit sonuç şeması -> analyze girdileri)
# ===========================================================================
def analyze_from_engine_result(engine_result: Dict,
                               injector_pressure_drop_bar: Optional[float] = None,
                               injector_dp_ratio: Optional[float] = None,
                               n_modes: int = 10) -> Dict:
    """Hibrit motor `calculate()` sonucundan akustik mod analizi üret.

    Şema alanları (hybrid_rocket_engine.calculate() üst seviyesi):
    chamber_temperature [K], gamma, molecular_weight [g/mol],
    chamber_diameter [m], chamber_length [m], chamber_pressure [bar].
    Spesifik gaz sabiti R = R_u / MW ile türetilir. Eksik alan için
    varsayılan UYDURULMAZ -> ValueError (sahte veri yasağı).
    """
    if not isinstance(engine_result, dict):
        raise ValueError(
            "engine_result must be a dict (engine calculate() output), "
            f"got {type(engine_result).__name__}.")

    required = ('chamber_temperature', 'gamma', 'molecular_weight',
                'chamber_diameter', 'chamber_length')
    missing = [k for k in required
               if engine_result.get(k) in (None, '', 0, 0.0)]
    if missing:
        raise ValueError(
            "engine_result is missing required fields for the acoustic "
            f"analysis: {missing}. No defaults are fabricated — supply the "
            "combustion/geometry outputs explicitly.")

    mw = float(engine_result['molecular_weight'])  # g/mol = kg/kmol
    gas_constant = R_UNIVERSAL_J_KMOL_K / mw       # J/(kg*K)

    chamber_length = float(engine_result['chamber_length'])
    nominal_diameter = float(engine_result['chamber_diameter'])

    # --- KAVİTE ÇAPI: GERÇEK SERBEST GAZ HACMİNDEN (ÖH D15, P4B4-06) ------
    # ÖLÇÜLEN KUSUR (üç gerçek hibrit koşumu, 20-31 Ağustos 2026): adaptör
    # kamara DIŞ/anma çapını olduğu gibi alıyordu; oysa aynı motor sonucu
    # GERÇEKLEŞEN serbest gaz hacmini (``chamber_volume_actual_m3``) ayrıca
    # yayımlıyor. pi/4*D^2*L ile kurulan kavite bu hacmin 2,51-2,68 KATIYDI:
    #     F=1   kN/20 bar: 0,0033360 m3 <-> 0,00128793 m3  (2,590 kat)
    #     F=5   kN/35 bar: 0,0169332 m3 <-> 0,00674    m3  (2,512 kat)
    #     F=0,3 kN/15 bar: 0,0006362 m3 <-> 0,000237   m3  (2,684 kat)
    # Enine (tanjansiyel/radyal) frekanslar f_T = a*alpha/(pi*D) ile çapa
    # TERS orantılı olduğundan 1T frekansı 1,58-1,64 kat DÜŞÜK çıkıyordu
    # (ölçüldü: 8.313,6 <-> 13.378,9 Hz). Modül frekansları banda
    # sınıflandırdığı (screech/buzz) için bu kayma modları yanlış banda
    # taşıyabiliyordu.
    #
    # DOĞRU REÇETE DEPODA ZATEN VAR: katı motor aynı modüle
    # ``d_eq = 2*sqrt(V_free/(pi*L))`` veriyor
    # (solid_rocket_engine._acoustic_modes_block) ve bunun bekçisi de var
    # (test_kati_baglama_dalga6::test_akustik_esdeger_kavite_gercek_hacmi_
    # ve_boyu_koruyor). Üç motorda TEK kavite tanımı olması gerekir; burada
    # o tanım kurulur. Hacim yayımlanmıyorsa sayı UYDURULMAZ: anma çapı
    # kullanılır ve künye bunun hacim koruyan bir çap OLMADIĞINI söyler.
    free_volume = engine_result.get('chamber_volume_actual_m3')
    if free_volume in (None, ''):
        free_volume = engine_result.get('chamber_volume_actual')
    try:
        free_volume = (None if free_volume in (None, '')
                       else float(free_volume))
    except (TypeError, ValueError):
        free_volume = None
    if free_volume is not None and not (math.isfinite(free_volume)
                                        and free_volume > 0.0):
        free_volume = None

    if free_volume is not None:
        cavity_diameter = 2.0 * math.sqrt(free_volume
                                          / (math.pi * chamber_length))
        cavity_basis = (
            'Equivalent right cylinder preserving BOTH the real chamber '
            'length and the REAL free gas volume reported by the solver '
            '(chamber_volume_actual_m3): D_eq = 2*sqrt(V_free/(pi*L)). The '
            'nominal chamber diameter describes the case, not the gas '
            'cavity; the transverse mode frequencies scale as 1/D, so using '
            'the nominal diameter reports frequencies that are too low. This '
            'is the SAME cavity definition the solid-motor path uses.')
        cavity_source = 'free_gas_volume'
    else:
        cavity_diameter = nominal_diameter
        cavity_basis = (
            'NOMINAL chamber diameter — the solver did not report a free gas '
            'volume (chamber_volume_actual_m3), so no volume-preserving '
            'equivalent cavity could be built and none is invented. If the '
            'real gas cavity is smaller than pi/4*D^2*L, the transverse '
            'frequencies reported here are LOWER than the physical ones.')
        cavity_source = 'nominal_chamber_diameter'

    result = AcousticModeAnalyzer().analyze(
        chamber_temperature=float(engine_result['chamber_temperature']),
        gamma=float(engine_result['gamma']),
        gas_constant=gas_constant,
        chamber_diameter=float(cavity_diameter),
        chamber_length=chamber_length,
        chamber_pressure=(
            None if engine_result.get('chamber_pressure') in (None, '')
            else float(engine_result['chamber_pressure'])),
        injector_pressure_drop_bar=injector_pressure_drop_bar,
        injector_dp_ratio=injector_dp_ratio,
        n_modes=n_modes,
    )
    result = dict(result)
    result['equivalent_cavity'] = {
        'length_m': float(chamber_length),
        'diameter_m': float(cavity_diameter),
        'nominal_chamber_diameter_m': float(nominal_diameter),
        'free_gas_volume_m3': (None if free_volume is None
                               else float(free_volume)),
        'diameter_source': cavity_source,
        'basis': cavity_basis,
    }
    return result
