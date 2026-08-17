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
  değerleri (NASA SP-194; Abramowitz & Stegun, "Handbook of Mathematical
  Functions", Tablo 9.5): 1T alpha_11 = 1.8412, 2T = 3.0542, 1R = 3.8317,
  2R = 7.0156, 1T1R = 5.3314. m = teğetsel (çevresel) indis, n = radyal
  indis, q = boyuna indis.

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

      Sutton & Biblarz, 9. baskı, Bölüm 9'daki kararsızlık sınıflandırma
      tablosu; NASA SP-194 giriş bölümü. Sınırlar keskin değildir; motor
      boyutuna göre kayar. Büyük motorlarda 1T modu 1 kHz altına inebilir —
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
    'FREQ_BAND_CHUG_MAX_HZ',
    'FREQ_BAND_BUZZ_MAX_HZ',
    'NOT_MODELLED',
]

# Evrensel gaz sabiti [J/(kmol*K)] — CODATA 2018. Molekül ağırlığından
# spesifik gaz sabiti türetirken kullanılır (R = R_u / MW, MW g/mol = kg/kmol).
R_UNIVERSAL_J_KMOL_K = 8314.462618

# ---------------------------------------------------------------------------
# Kararlılık eşikleri — DEPODAKİ TEK SAYISAL TANIM, kaynak künyeli. Başka
# dosyada bu sayıları tekrar YAZMA; buradan ithal et (parametre tutarlılık
# kuralı). Bekçi: tests/test_stability_sivi.py::test_chug_esigi_tek_kaynak
# (dosya tarar; yeni kopya eklenirse KIRMIZI).
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
# oran < 0.15 -> chug riski (besleme-kamara kuplajı olası).
CHUG_DP_RATIO_RECOMMENDED = 0.20
CHUG_DP_RATIO_MINIMUM = 0.15
CHUG_THRESHOLD_SOURCE = (
    'Injector pressure drop is classically designed at 15-25% of chamber '
    'pressure to decouple the feed system from chamber pressure '
    'oscillations (Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed., '
    'Ch. 8 injector design; NASA SP-194, Harrje & Reardon eds., 1972, '
    'Ch. 5-6 feed-system-coupled low-frequency instability). Engineering '
    'rule of thumb, approximate — not a sharp physical boundary. '
    'This pair (0.20 / 0.15) is the ONLY numeric definition of the chug '
    'design rule in HRMA: the liquid engine, the injector-driven transient '
    'solver and hrma.stability.chug all import it from here. Other parts of '
    'the repository cite NASA SP-8089 (Gill & Nurick, "Liquid Rocket Engine '
    'Injectors", March 1976) for the same band; that document is verified to '
    'exist and to be about injectors (NTRS 19760023196), but the band has '
    'NOT been verified page-by-page inside it in this repository, so the '
    'threshold is not attributed to it. Where this rule falls on the solved '
    'chug neutral curve is measured, not assumed: see '
    'hrma.stability.chug.assess_chug -> classical_rule_cross_check.')

# Frekans bandı sınırları [Hz] — gösterge niteliğinde sınıflandırma.
FREQ_BAND_CHUG_MAX_HZ = 400.0
FREQ_BAND_BUZZ_MAX_HZ = 1000.0
FREQ_BAND_SOURCE = (
    'Indicative classification: chug (low frequency) < ~400 Hz, buzz '
    '(intermediate) ~400-1000 Hz, screech (high frequency, acoustic) '
    '> ~1000 Hz (Sutton & Biblarz, 9th ed., Ch. 9 instability '
    'classification; NASA SP-194 introduction). Boundaries are indicative, '
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
        'eigenvalues.'),
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


def transverse_root(m_tangential: int, n_radial: int) -> float:
    """Boyutsuz enine mod kökü alpha_mn: J'_m'in sıfırı (rijit cidar).

    m_tangential = teğetsel (çevresel) indis m >= 0,
    n_radial = radyal indis n >= 0; (m, n) = (0, 0) enine bileşen yok
    demektir ve burada anlamsızdır -> ValueError.

    Eşleme (`scipy.special.jnp_zeros(m, k)` J'_m'in ilk k sıfırını verir,
    m = 0 için x = 0 trivial kökü atlanmıştır):
      - saf teğetsel mT      (n=0): alpha = jnp_zeros(m, 1)[0]
      - saf radyal nR        (m=0): alpha = jnp_zeros(0, n)[n-1]
      - teğetsel-radyal mTnR      : alpha = jnp_zeros(m, n+1)[n]

    Literatür çapaları (NASA SP-194; Abramowitz & Stegun Tablo 9.5):
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

    # Mod havuzu üst sınırları: m (teğetsel), n (radyal), q (boyuna).
    # Havuzdan frekansa göre sıralanıp ilk n_modes alınır; sınırlar tipik
    # ilk 10-20 modu fazlasıyla kapsar.
    MAX_TANGENTIAL_INDEX = 3
    MAX_RADIAL_INDEX = 2
    MAX_LONGITUDINAL_INDEX = 6

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
        modes = self._build_mode_table(a, D, L, n_modes)

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
            'note': (
                'Transverse modes (especially 1T) are historically the most '
                'destructive in large engines (F-1 1T spinning instability, '
                'Oefelein & Yang 1993). Mode frequencies listed here are '
                'CANDIDATE resonances only — whether combustion drives them '
                'is NOT modelled (see not_modelled.combustion_response).'),
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
                f'{len(modes)} modes of the (m<={self.MAX_TANGENTIAL_INDEX}, '
                f'n<={self.MAX_RADIAL_INDEX}, '
                f'q<={self.MAX_LONGITUDINAL_INDEX}) pool.'),
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
    def _build_mode_table(self, a: float, D: float, L: float,
                          n_modes: int) -> List[Dict]:
        """(m, n, q) havuzunu üret, frekansa göre sırala, ilk n_modes'u al."""
        candidates: List[Dict] = []
        for m in range(0, self.MAX_TANGENTIAL_INDEX + 1):
            for n in range(0, self.MAX_RADIAL_INDEX + 1):
                for q in range(0, self.MAX_LONGITUDINAL_INDEX + 1):
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
        candidates.sort(key=lambda mode: mode['frequency_hz'])
        return candidates[:n_modes]

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

        return {
            'evaluated': ratio is not None,
            'injector_dp_ratio': (None if ratio is None else float(ratio)),
            'ratio_source': ratio_source,
            'recommended_min_ratio': CHUG_DP_RATIO_RECOMMENDED,
            'hard_min_ratio': CHUG_DP_RATIO_MINIMUM,
            'threshold_source': CHUG_THRESHOLD_SOURCE,
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

    return AcousticModeAnalyzer().analyze(
        chamber_temperature=float(engine_result['chamber_temperature']),
        gamma=float(engine_result['gamma']),
        gas_constant=gas_constant,
        chamber_diameter=float(engine_result['chamber_diameter']),
        chamber_length=float(engine_result['chamber_length']),
        chamber_pressure=(
            None if engine_result.get('chamber_pressure') in (None, '')
            else float(engine_result['chamber_pressure'])),
        injector_pressure_drop_bar=injector_pressure_drop_bar,
        injector_dp_ratio=injector_dp_ratio,
        n_modes=n_modes,
    )
