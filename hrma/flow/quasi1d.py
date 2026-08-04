"""
Yarı-1B (quasi-1D) sıkıştırılabilir lüle iç akışı — F1, v3 CFD kulvarının temeli.

NE OLDUĞU / NE OLMADIĞI
-----------------------
Bu modül tam 2B/3B CFD çözücü DEĞİLDİR. Verilen alan profili A(x) üzerinde
sürtünmesiz, adyabatik, kalorik olarak mükemmel gaz için yarı-1B akışı çözer:
rejim sınıflandırması, izantropik ses-altı/ses-üstü dallar ve lüle içi normal
şok konumu. Sınır tabaka ayrılması AYRI modülde deneysel korelasyonlarla ele
alınır (``hrma.flow.separation``). Motor sonuç sözlüğünden ve Flask
katmanından bağımsız saf fiziktir; motor zincirine bağlama sonraki dalganın
işidir (docs/YOL_HARITASI_2.7_VE_SONRASI.md, F1). Tüm girdi/çıktılar SI
birimindedir (Pa, K, m, m², kg/s).

FORMÜL KAYNAKLARI
-----------------
İzantropik bağıntılar (T/T0, P/P0, rho/rho0):
    Anderson, "Modern Compressible Flow", 3. baskı, Eş. 3.28-3.31.
Alan-Mach bağıntısı (A/A*):
    Anderson, 3. baskı, Eş. 5.20; Sutton & Biblarz, "Rocket Propulsion
    Elements", 9. baskı, Eş. 3-14. Kök brentq ile bulunur — depodaki
    ``hrma/engines/nozzle_design.py`` ile aynı kalıp ve aynı bağıntı; bu
    modül motor katmanına bağımlılık taşımasın diye bağıntı burada bağımsız
    (tek başına çalışır biçimde) yazılmıştır.
Normal şok (Rankine-Hugoniot) bağıntıları:
    Anderson, 3. baskı, Eş. 3.51 (M2), 3.57 (P2/P1), 3.59 (T2/T1),
    3.63 (P02/P01); NACA Report 1135 (1953), Eş. 93-99.
Rejim sınıflandırması ve lüle içi şok konumu eşlemesi:
    Anderson, 3. baskı, Böl. 5.4 (kritik geri basınçlar; şok ardı ses-altı
    izantropik difüzyonun çıkışta geri basınca eşlenmesi).
Boğulmuş kütle debisi:
    Anderson, 3. baskı, Eş. 5.23; Sutton & Biblarz, 9. baskı, Eş. 3-24.

MODELLENMEYENLER (çıktıda ``not_modelled`` olarak da beyan edilir)
------------------------------------------------------------------
- ``wall_friction``: cidar sürtünmesi / sınır tabaka (Fanno etkisi yok).
- ``heat_loss``: cidara ısı kaybı (akış adyabatik, T0 sabit; Rayleigh yok).
- ``two_dimensional_effects``: akım çizgisi eğriliği, eğik şoklar,
  şok-sınır tabaka etkileşimi, lambda-şok yapısı.
- ``real_gas``: gerçek gaz, değişken gamma, kimyasal reaksiyon (donmuş,
  kalorik olarak mükemmel gaz varsayılır).
"""

import numpy as np
from typing import Dict, Optional, Sequence, Tuple

from scipy.optimize import brentq

__all__ = [
    'QUASI1D_NOT_MODELLED',
    'REGIME_NO_FLOW',
    'REGIME_SUBSONIC',
    'REGIME_CHOKED_SUBSONIC',
    'REGIME_NORMAL_SHOCK',
    'REGIME_OVEREXPANDED',
    'REGIME_PERFECT',
    'REGIME_UNDEREXPANDED',
    'isentropic_ratios',
    'area_ratio_from_mach',
    'mach_from_area_ratio',
    'mach_from_pressure_ratio',
    'normal_shock_relations',
    'choked_mass_flow',
    'critical_pressures',
    'solve_nozzle',
]

# --------------------------------------------------------------------------
# Modül sabitleri
# --------------------------------------------------------------------------

#: Alan-Mach kök aramasının ses-üstü üst sınırı. engines/nozzle_design.py
#: ile aynı değer (M=50, gamma=1.4 için A/A* ~ 1.4e6 — pratik lülelerin
#: tamamını kapsar). Bunun ötesi ValueError ile DÜRÜSTÇE reddedilir,
#: sessiz yaklaşıklığa düşülmez.
MACH_MAX = 50.0

_MACH_EPS = 1e-9          # M=1 tekilliğinden kaçınma payı (brentq braketi)
_BOUNDARY_RTOL = 1e-9     # rejim sınırı eşitlik toleransı (ölçü-sıfır rejimler)

# Rejim adları depo genelinde TEK sözlükle anılır: değerler
# hrma/analysis/nozzle_flow_1d.py'deki adlandırmayla bilinçli olarak
# aynıdır (parametre tutarlılığı kuralı — aynı kavram, aynı ad).
REGIME_NO_FLOW = 'no_flow'
REGIME_SUBSONIC = 'subsonic_unchoked'
REGIME_CHOKED_SUBSONIC = 'choked_subsonic_diffuser'
REGIME_NORMAL_SHOCK = 'normal_shock_in_nozzle'
REGIME_OVEREXPANDED = 'overexpanded'
REGIME_PERFECT = 'perfectly_expanded'
REGIME_UNDEREXPANDED = 'underexpanded'

_REGIME_DESCRIPTIONS = {
    REGIME_NO_FLOW: (
        'Akış yok: geri basınç rezervuar basıncına eşit veya üstünde. '
        'Pb > P0 için ters akış MODELLENMEDİ.'),
    REGIME_SUBSONIC: (
        'Tümü ses-altı (Venturi rejimi): boğaz boğulmamış, her istasyonda '
        'M < 1; çıkış statik basıncı geri basınca eşit.'),
    REGIME_CHOKED_SUBSONIC: (
        'Boğazda boğulmuş (M=1), ıraksak bölüm ses-altı difüzör olarak '
        'çalışır (birinci kritik nokta).'),
    REGIME_NORMAL_SHOCK: (
        'Iraksak bölümde normal şok: boğaz-şok arası ses-üstü, şok ardı '
        'ses-altı difüzyon çıkışta geri basıncı karşılar.'),
    REGIME_OVEREXPANDED: (
        'Lüle içinde tam ses-üstü, aşırı genleşme: çıkış basıncı geri '
        'basınçtan düşük; uyum lüle DIŞINDA eğik şoklarla olur '
        '(dış uyum MODELLENMEDİ). Sınır tabaka ayrılması riski için '
        'hrma.flow.separation kriterlerine bakılmalıdır.'),
    REGIME_PERFECT: (
        'Adapte (tasarım) genleşme: çıkış basıncı geri basınca eşit, '
        'lüle içinde tam ses-üstü.'),
    REGIME_UNDEREXPANDED: (
        'Eksik genleşme: çıkış basıncı geri basınçtan yüksek; genleşme '
        'lüle DIŞINDA genleşme fanlarıyla sürer (dış uyum MODELLENMEDİ).'),
}

# Depo kalıbı (launch_site.py, acoustic_modes.py ile aynı biçim):
# anahtar = modellenmeyen fizik, değer = açıklama. Çıktıya aynen kopyalanır.
# Ad, modüle özgüdür (QUASI1D_ öneki): depoda NOT_MODELLED adı hem sözlük
# (launch_site) hem çokuzlu (two_phase_loss) olarak kullanılıyor; üçüncü bir
# eşadlı tanım tutarlılık bekçisini haklı olarak rahatsız eder.
QUASI1D_NOT_MODELLED = {
    'wall_friction': (
        'Cidar sürtünmesi ve sınır tabaka yok sayılır (Fanno hattı etkisi '
        'modellenmedi); duvar basıncı izantropik çekirdek basıncına eşit '
        'kabul edilir.'),
    'heat_loss': (
        'Cidara ısı kaybı yok; akış adyabatik, durma sıcaklığı T0 sabit '
        '(Rayleigh hattı etkisi modellenmedi).'),
    'two_dimensional_effects': (
        'Akış her kesitte tek boyutlu üniform kabul edilir; akım çizgisi '
        'eğriliği, eğik şoklar, şok-sınır tabaka etkileşimi ve lambda-şok '
        'yapısı modellenmedi.'),
    'real_gas': (
        'Kalorik olarak mükemmel gaz: sabit gamma ve R, donmuş kimyasal '
        'kompozisyon; gerçek gaz ve sıcaklığa bağlı özgül ısı modellenmedi.'),
}

_ASSUMPTIONS = (
    'steady',                    # kararlı akış
    'quasi_one_dimensional',     # her kesitte üniform, A(x) yavaş değişir
    'inviscid',                  # sürtünmesiz (şok hariç tersinir)
    'adiabatic',                 # ısı alışverişi yok, T0 korunur
    'calorically_perfect_gas',   # sabit gamma ve R
)


# --------------------------------------------------------------------------
# Temel izantropik / şok bağıntıları
# --------------------------------------------------------------------------

def isentropic_ratios(mach: float, gamma: float) -> Tuple[float, float, float]:
    """(T/T0, P/P0, rho/rho0) statik/durma oranlarını döndürür.

    T0/T = 1 + (γ-1)/2·M²;  P0/P = (T0/T)^(γ/(γ-1));  ρ0/ρ = (T0/T)^(1/(γ-1))
    Kaynak: Anderson, "Modern Compressible Flow", 3. baskı, Eş. 3.28-3.31.
    """
    M = float(mach)
    g = float(gamma)
    if M < 0.0:
        raise ValueError('Mach sayısı negatif olamaz.')
    t_ratio = 1.0 / (1.0 + 0.5 * (g - 1.0) * M * M)
    p_ratio = t_ratio ** (g / (g - 1.0))
    rho_ratio = t_ratio ** (1.0 / (g - 1.0))
    return t_ratio, p_ratio, rho_ratio


def area_ratio_from_mach(mach: float, gamma: float) -> float:
    """A/A* oranını Mach sayısından hesaplar.

    A/A* = (1/M)·[(2/(γ+1))·(1 + (γ-1)/2·M²)]^((γ+1)/(2(γ-1)))
    Kaynak: Anderson, 3. baskı, Eş. 5.20; Sutton & Biblarz, 9. baskı,
    Eş. 3-14 (engines/nozzle_design.py ile aynı bağıntı).
    """
    M = float(mach)
    g = float(gamma)
    if M <= 0.0:
        raise ValueError('Alan-Mach bağıntısı için M > 0 gerekli.')
    exponent = (g + 1.0) / (2.0 * (g - 1.0))
    return float((1.0 / M) * ((2.0 / (g + 1.0))
                              * (1.0 + 0.5 * (g - 1.0) * M * M)) ** exponent)


def mach_from_area_ratio(area_ratio: float, gamma: float,
                         supersonic: bool = True) -> float:
    """İzantropik alan-Mach bağıntısını istenen dalda tersler (brentq).

    A/A* verilir, M döndürülür. ``supersonic=True`` ses-üstü dal
    (1 < M <= MACH_MAX), ``supersonic=False`` ses-altı dal (0 < M <= 1).
    A/A* <= 1 (sayısal tolerans içinde) için M = 1 döner.
    Kaynak: Anderson, 3. baskı, Eş. 5.20; kök arama kalıbı
    engines/nozzle_design.py ile aynıdır (brentq, sıkı tolerans).
    Braket dışına düşen istek sessiz yaklaşıklık YERİNE ValueError verir.
    """
    eps = float(area_ratio)
    g = float(gamma)
    if eps < 1.0 - 1e-9:
        raise ValueError(
            f'A/A* = {eps:.6g} < 1: izantropik akışta alan oranı sonik '
            f'alandan küçük olamaz.')
    if eps <= 1.0 + 1e-12:
        return 1.0

    def residual(M: float) -> float:
        return area_ratio_from_mach(M, g) - eps

    if supersonic:
        lo, hi = 1.0 + _MACH_EPS, MACH_MAX
    else:
        lo, hi = 1e-12, 1.0
    try:
        M_sol = brentq(residual, lo, hi, xtol=1e-13, rtol=8.9e-16,
                       maxiter=200)
    except ValueError as exc:
        raise ValueError(
            f'Alan-Mach kökü braket [{lo:.3g}, {hi:.3g}] içinde bulunamadı '
            f'(A/A*={eps:.6g}, gamma={g:.4g}, '
            f'dal={"ses-üstü" if supersonic else "ses-altı"}).') from exc
    return float(M_sol)


def mach_from_pressure_ratio(p0_over_p: float, gamma: float) -> float:
    """P0/P durma-statik basınç oranından izantropik Mach sayısını çözer.

    M = sqrt( 2/(γ-1)·[(P0/P)^((γ-1)/γ) − 1] )
    Kaynak: Anderson, 3. baskı, Eş. 3.30'un tersi; Sutton & Biblarz,
    9. baskı, Eş. 3-7.
    """
    pr = float(p0_over_p)
    g = float(gamma)
    if pr < 1.0:
        raise ValueError('P0/P >= 1 olmalı (statik basınç durma basıncını aşamaz).')
    return float(np.sqrt(max(2.0 / (g - 1.0)
                             * (pr ** ((g - 1.0) / g) - 1.0), 0.0)))


def normal_shock_relations(mach1: float,
                           gamma: float) -> Tuple[float, float, float, float]:
    """Normal şok (Rankine-Hugoniot) sıçrama bağıntıları.

    (M2, P2/P1, T2/T1, P02/P01) döndürür. Kaynaklar (Anderson, "Modern
    Compressible Flow", 3. baskı):
        M2²      = (1 + (γ-1)/2·M1²) / (γ·M1² − (γ-1)/2)          (Eş. 3.51)
        P2/P1    = 1 + 2γ/(γ+1)·(M1² − 1)                          (Eş. 3.57)
        T2/T1    = (P2/P1)·[(2 + (γ-1)M1²) / ((γ+1)M1²)]           (Eş. 3.59)
        P02/P01  = [((γ+1)M1²/(2+(γ-1)M1²))^(γ/(γ-1))]
                   · [((γ+1)/(2γM1²−(γ-1)))^(1/(γ-1))]             (Eş. 3.63)
    Ayrıca NACA Report 1135 (1953), Eş. 93-99.
    """
    M1 = float(mach1)
    g = float(gamma)
    if M1 <= 1.0:
        raise ValueError('Normal şok için şok öncesi M1 > 1 gerekli.')
    m1sq = M1 * M1
    m2sq = (1.0 + 0.5 * (g - 1.0) * m1sq) / (g * m1sq - 0.5 * (g - 1.0))
    mach2 = float(np.sqrt(m2sq))
    p2_p1 = 1.0 + 2.0 * g / (g + 1.0) * (m1sq - 1.0)
    T2_T1 = p2_p1 * (2.0 + (g - 1.0) * m1sq) / ((g + 1.0) * m1sq)
    p02_p01 = (((g + 1.0) * m1sq / (2.0 + (g - 1.0) * m1sq)) ** (g / (g - 1.0))
               * ((g + 1.0) / (2.0 * g * m1sq - (g - 1.0))) ** (1.0 / (g - 1.0)))
    return mach2, float(p2_p1), float(T2_T1), float(p02_p01)


def choked_mass_flow(P0: float, T0: float, gamma: float, R: float,
                     throat_area: float) -> float:
    """Boğulmuş (sonik boğaz) kütle debisi [kg/s].

    mdot = (P0·A*/√T0)·√(γ/R)·(2/(γ+1))^((γ+1)/(2(γ-1)))
    Kaynak: Anderson, 3. baskı, Eş. 5.23; Sutton & Biblarz, 9. baskı,
    Eş. 3-24. Boğulmamış akışta aynı özdeşlik FİKTİF sonik alan A*_eff ile
    kullanılır (izantropik akışta P0·A* değişmezi).
    """
    g = float(gamma)
    gamma_fn = np.sqrt(g / float(R)) * (2.0 / (g + 1.0)) ** (
        (g + 1.0) / (2.0 * (g - 1.0)))
    return float(float(P0) * float(throat_area) / np.sqrt(float(T0)) * gamma_fn)


# --------------------------------------------------------------------------
# Rejim sınıflandırması
# --------------------------------------------------------------------------

def critical_pressures(area_ratio_exit: float, P0: float,
                       gamma: float) -> Dict:
    """Çıkış alan oranı için üç kritik geri basıncı hesaplar [Pa].

    Anderson, 3. baskı, Böl. 5.4:
      - ``choked_subsonic_exit_Pa`` (birinci kritik): boğaz tam boğulmuş,
        ıraksak bölüm ses-altı; çıkışta ses-altı izantropik dal basıncı.
      - ``shock_at_exit_Pa``: normal şok tam çıkış düzleminde; ses-üstü dal
        çıkış basıncının şok ardı değeri (P_sup · P2/P1).
      - ``supersonic_exit_Pa`` (tasarım/adapte): tam ses-üstü izantropik
        genleşmenin çıkış basıncı.
    """
    eps_e = float(area_ratio_exit)
    if eps_e <= 1.0 + 1e-9:
        raise ValueError(
            'Kritik basınçlar için çıkış alan oranı A_e/A_t > 1 olmalı '
            '(ıraksak bölümü olmayan profil bu modülün kapsamı dışında).')
    M_sub = mach_from_area_ratio(eps_e, gamma, supersonic=False)
    M_sup = mach_from_area_ratio(eps_e, gamma, supersonic=True)
    P_sub = float(P0) * isentropic_ratios(M_sub, gamma)[1]
    P_sup = float(P0) * isentropic_ratios(M_sup, gamma)[1]
    _, p2_p1_exit, _, _ = normal_shock_relations(M_sup, gamma)
    P_shock_exit = P_sup * p2_p1_exit
    return {
        'choked_subsonic_exit_Pa': P_sub,
        'shock_at_exit_Pa': P_shock_exit,
        'supersonic_exit_Pa': P_sup,
        'mach_exit_subsonic': M_sub,
        'mach_exit_supersonic': M_sup,
        '_basis': (
            'Anderson, Modern Compressible Flow, 3. baskı, Böl. 5.4: çıkış '
            'alan oranının izantropik ses-altı/ses-üstü dalları (Eş. 5.20, '
            '3.30) ve çıkış düzleminde normal şok (Eş. 3.57).'),
    }


# --------------------------------------------------------------------------
# Girdi doğrulama
# --------------------------------------------------------------------------

def _validate_area_profile(x: Sequence[float],
                           area: Sequence[float]) -> Tuple[np.ndarray,
                                                           np.ndarray, int]:
    """Alan profilini doğrular; (x, area, boğaz indeksi) döndürür.

    Kapsam beyanı: tek boğazlı yakınsak-ıraksak profil zorunludur. Çift
    boğaz, düz kanal veya salt yakınsak profil bu modülün kapsamı dışındadır
    ve sessiz yanlış sonuç yerine ValueError ile reddedilir.
    """
    x_arr = np.asarray(x, dtype=float)
    a_arr = np.asarray(area, dtype=float)
    if x_arr.ndim != 1 or a_arr.shape != x_arr.shape:
        raise ValueError('x ve area aynı uzunlukta 1B diziler olmalı.')
    if x_arr.size < 5:
        raise ValueError('Alan profili için en az 5 istasyon gerekli.')
    if not (np.all(np.isfinite(x_arr)) and np.all(np.isfinite(a_arr))):
        raise ValueError('x ve area sonlu (finite) değerler içermeli.')
    if np.any(np.diff(x_arr) <= 0.0):
        raise ValueError('x kesin artan olmalı.')
    if np.any(a_arr <= 0.0):
        raise ValueError('Tüm kesit alanları pozitif olmalı.')
    throat_idx = int(np.argmin(a_arr))
    if throat_idx == 0 or throat_idx == x_arr.size - 1:
        raise ValueError(
            'Boğaz iç istasyonda olmalı: profil yakınsak-ıraksak değil '
            '(salt yakınsak/ıraksak kanal bu modülün kapsamı dışında).')
    if (np.any(np.diff(a_arr[:throat_idx + 1]) > 0.0)
            or np.any(np.diff(a_arr[throat_idx:]) < 0.0)):
        raise ValueError(
            'Alan profili tek boğazlı olmalı: boğaza kadar monoton azalan, '
            'boğazdan sonra monoton artan (çift boğaz kapsam dışı).')
    if (a_arr[-1] / a_arr[throat_idx] <= 1.0 + 1e-9
            or a_arr[0] / a_arr[throat_idx] <= 1.0 + 1e-9):
        raise ValueError(
            'Giriş ve çıkış alanları boğaz alanından belirgin büyük olmalı '
            '(A/A_t > 1).')
    return x_arr, a_arr, throat_idx


# --------------------------------------------------------------------------
# Ana çözücü
# --------------------------------------------------------------------------

def solve_nozzle(x: Sequence[float], area: Sequence[float], P0: float,
                 T0: float, gamma: float, R: float, Pb: float) -> Dict:
    """Yarı-1B lüle iç akışını rejim sınıflandırmasıyla çözer.

    Args:
        x: Eksenel istasyon konumları [m], kesin artan.
        area: Kesit alanı profili A(x) [m²], tek boğazlı yakınsak-ıraksak.
        P0: Rezervuar (durma) basıncı [Pa].
        T0: Rezervuar (durma) sıcaklığı [K].
        gamma: İzantropik üs (kalorik olarak mükemmel gaz, sabit).
        R: Özgül gaz sabiti [J/(kg·K)].
        Pb: Geri (ortam) basıncı [Pa].

    Returns:
        Beyanlı sözlük: ``regime`` (+ ``regime_basis``), ``x_m``,
        ``area_m2``, ``mach``, ``pressure_Pa``, ``temperature_K``,
        ``shock`` (normal şok rejiminde konum/sıçrama; yoksa None),
        ``critical_pressures``, ``exit``, ``mass_flow_kg_s``,
        ``mass_conservation_rel_residual``, ``not_modelled``,
        ``assumptions``, ``inputs``.

    Rejimler (Anderson, 3. baskı, Böl. 5.4):
        (a) ``subsonic_unchoked``     — tümü ses-altı, boğaz boğulmamış;
        (b) ``choked_subsonic_diffuser`` — boğazda M=1, ıraksak ses-altı;
        (c) ``normal_shock_in_nozzle``   — ıraksakta normal şok, konumu
            çıkışta P = Pb eşlemesiyle brentq ile çözülür;
        (d) ``overexpanded`` / ``perfectly_expanded`` / ``underexpanded``
            — lüle içinde tam ses-üstü.
        Ek: ``no_flow`` — Pb >= P0.

    Şok konumu çözümü (Anderson, Böl. 5.4): şok öncesi M1 bilinmeyendir;
    şok ardı durma basıncı P02 = P0·(P02/P01) ve YENİ sonik alan
    A2* = A_t·(P01/P02) ile (kütle korunumu: P0·A* değişmezi) çıkışa kadar
    ses-altı izantropik dal ilerletilir, çıkış statik basıncının Pb'ye
    eşitlenmesi M1'i tek başına belirler.
    """
    x_arr, area_arr, it = _validate_area_profile(x, area)
    P0 = float(P0)
    T0 = float(T0)
    g = float(gamma)
    Rs = float(R)
    Pb = float(Pb)
    if P0 <= 0.0 or T0 <= 0.0:
        raise ValueError('P0 ve T0 pozitif olmalı.')
    if Rs <= 0.0:
        raise ValueError('Özgül gaz sabiti R pozitif olmalı.')
    if not (1.0 < g < 2.0):
        raise ValueError('gamma (1, 2) aralığında olmalı (mükemmel gaz).')
    if Pb < 0.0:
        raise ValueError('Geri basınç Pb negatif olamaz.')

    A_t = float(area_arr[it])
    eps_local = area_arr / A_t
    eps_e = float(eps_local[-1])
    crit = critical_pressures(eps_e, P0, g)
    P_sub = crit['choked_subsonic_exit_Pa']
    P_shx = crit['shock_at_exit_Pa']
    P_sup = crit['supersonic_exit_Pa']

    # --- Rejim sınıflandırması (sıra önemli: ölçü-sıfır sınırlar önce) ---
    if Pb >= P0 * (1.0 - _BOUNDARY_RTOL):
        regime = REGIME_NO_FLOW
    elif np.isclose(Pb, P_sub, rtol=_BOUNDARY_RTOL):
        regime = REGIME_CHOKED_SUBSONIC
    elif Pb > P_sub:
        regime = REGIME_SUBSONIC
    elif np.isclose(Pb, P_sup, rtol=_BOUNDARY_RTOL):
        regime = REGIME_PERFECT
    elif Pb > P_shx:
        regime = REGIME_NORMAL_SHOCK
    elif Pb > P_sup:
        regime = REGIME_OVEREXPANDED
    else:
        regime = REGIME_UNDEREXPANDED

    n = x_arr.size
    M = np.zeros(n)
    p0_station = np.full(n, P0)   # şok ardında durma basıncı düşer
    shock: Optional[Dict] = None
    mdot = 0.0

    if regime == REGIME_NO_FLOW:
        # Akış yok: statik alan rezervuar koşullarında durur.
        pass

    elif regime in (REGIME_SUBSONIC, REGIME_CHOKED_SUBSONIC):
        if regime == REGIME_CHOKED_SUBSONIC:
            A_star = A_t
        else:
            # Çıkış Mach'i geri basınçtan; fiktif sonik alan çıkıştan geri
            # hesaplanır (boğulmamış akışta A*_eff < A_t).
            M_exit_sub = mach_from_pressure_ratio(P0 / Pb, g)
            A_star = float(area_arr[-1]) / area_ratio_from_mach(M_exit_sub, g)
        for i in range(n):
            M[i] = mach_from_area_ratio(area_arr[i] / A_star, g,
                                        supersonic=False)
        # Boğulmamışta da aynı özdeşlik, fiktif A*_eff ile (izantropik
        # P0·A* değişmezi) — bkz. choked_mass_flow docstring.
        mdot = choked_mass_flow(P0, T0, g, Rs, A_star)

    elif regime == REGIME_NORMAL_SHOCK:
        M_sup_e = crit['mach_exit_supersonic']

        def _exit_pressure_for_shock_mach(m1: float) -> float:
            """Şok öncesi M1 verildiğinde çıkış statik basıncı [Pa]."""
            _, _, _, p02_p01_l = normal_shock_relations(m1, g)
            # A_e/A2* = (A_e/A_t)·(A_t/A2*) = eps_e·(P02/P01)
            m_exit_sub = mach_from_area_ratio(eps_e * p02_p01_l, g,
                                              supersonic=False)
            return P0 * p02_p01_l * isentropic_ratios(m_exit_sub, g)[1]

        # M1→1⁺ limiti P_sub, M1→M_sup_e limiti P_shx verir; Pb bu bantta
        # olduğundan kök braket içinde ve tektir (monoton azalan).
        mach1 = brentq(lambda m: _exit_pressure_for_shock_mach(m) - Pb,
                       1.0 + _MACH_EPS, M_sup_e, xtol=1e-12, maxiter=200)
        mach2, p2_p1, T2_T1, p02_p01 = normal_shock_relations(mach1, g)
        P0_down = P0 * p02_p01
        A2_star = A_t / p02_p01
        eps_shock = area_ratio_from_mach(mach1, g)
        A_shock = A_t * eps_shock
        # Iraksak bölümde alan monoton arttığı için (doğrulandı) alan→x
        # doğrusal enterpolasyonu tek değerlidir.
        x_shock = float(np.interp(A_shock, area_arr[it:], x_arr[it:]))
        for i in range(n):
            if i <= it:
                M[i] = mach_from_area_ratio(eps_local[i], g, supersonic=False)
            elif x_arr[i] <= x_shock:
                M[i] = mach_from_area_ratio(eps_local[i], g, supersonic=True)
            else:
                M[i] = mach_from_area_ratio(area_arr[i] / A2_star, g,
                                            supersonic=False)
                p0_station[i] = P0_down
        mdot = choked_mass_flow(P0, T0, g, Rs, A_t)
        shock = {
            'x_m': x_shock,
            'area_m2': float(A_shock),
            'area_ratio': float(eps_shock),
            'mach_upstream': float(mach1),
            'mach_downstream': float(mach2),
            'p2_p1': p2_p1,
            'T2_T1': T2_T1,
            'p02_p01': p02_p01,
            'stagnation_pressure_downstream_Pa': float(P0_down),
            'sonic_area_downstream_m2': float(A2_star),
            '_basis': (
                'Rankine-Hugoniot sıçramaları (Anderson 3. baskı, '
                'Eş. 3.51/3.57/3.59/3.63); şok konumu, şok ardı ses-altı '
                'izantropik difüzyonun çıkışta P = Pb koşulunu sağlamasıyla '
                'brentq ile çözüldü (Anderson Böl. 5.4). T0 şok boyunca '
                'korunur (adyabatik).'),
        }

    else:  # tam ses-üstü aile: overexpanded / adapted / underexpanded
        for i in range(n):
            M[i] = mach_from_area_ratio(eps_local[i], g, supersonic=(i >= it))
        mdot = choked_mass_flow(P0, T0, g, Rs, A_t)

    # --- Statik alanlar (vektörel izantropik bağıntılar) ---
    # M=0 istasyonlarında formül kendiliğinden P=P0, T=T0 verir (no_flow).
    T = T0 / (1.0 + 0.5 * (g - 1.0) * M ** 2)
    P = p0_station * (T / T0) ** (g / (g - 1.0))

    # --- Kütle korunumu artığı (hesaplanan öz-denetim, uydurma değil) ---
    if mdot > 0.0:
        rho = P / (Rs * T)
        u = M * np.sqrt(g * Rs * T)
        flux = rho * u * area_arr
        mass_residual = float(np.max(np.abs(flux - mdot)) / mdot)
    else:
        mass_residual = 0.0

    M_e = float(M[-1])
    P_e = float(P[-1])
    T_e = float(T[-1])
    exit_state = {
        'mach': M_e,
        'pressure_Pa': P_e,
        'temperature_K': T_e,
        'velocity_m_s': float(M_e * np.sqrt(g * Rs * T_e)),
        # Hesaplanan karşılaştırma: çıkış statik basıncı geri basıncı
        # karşılıyor mu? (a)-(c) rejimlerinde True beklenir; ses-üstü
        # ailede uyum lüle dışındadır ve False döner.
        'back_pressure_match': bool(np.isclose(P_e, Pb, rtol=1e-6)),
        '_basis': (
            'Son istasyondaki çözümden okunan değerler; hız '
            'v = M·sqrt(γ·R·T) (Anderson Eş. 3.28 tabanlı).'),
    }

    return {
        'regime': regime,
        'regime_description': _REGIME_DESCRIPTIONS[regime],
        'regime_basis': (
            'Anderson, Modern Compressible Flow, 3. baskı, Böl. 5.4 kritik '
            f'geri basınç sınıflandırması: P_choked_subsonic={P_sub:.6g} Pa, '
            f'P_shock_at_exit={P_shx:.6g} Pa, P_supersonic={P_sup:.6g} Pa; '
            f'verilen Pb={Pb:.6g} Pa.'),
        'x_m': x_arr,
        'area_m2': area_arr,
        'mach': M,
        'pressure_Pa': P,
        'temperature_K': T,
        'profile_basis': (
            'İzantropik yarı-1B alan-Mach çözümü (Anderson Eş. 5.20 + '
            '3.28-3.31); normal şok rejiminde şok ardı istasyonlar '
            'düşürülmüş durma basıncı P02 ve büyümüş sonik alan A2* ile '
            'ses-altı daldan çözülür.'),
        'throat': {
            'index': it,
            'x_m': float(x_arr[it]),
            'area_m2': A_t,
            'choked': regime not in (REGIME_NO_FLOW, REGIME_SUBSONIC),
        },
        'critical_pressures': crit,
        'shock': shock,
        'exit': exit_state,
        'mass_flow_kg_s': float(mdot),
        'mass_flow_basis': (
            'Boğulmuş: mdot = P0·A_t/√T0·√(γ/R)·(2/(γ+1))^((γ+1)/(2(γ-1))) '
            '(Anderson Eş. 5.23; Sutton Eş. 3-24). Boğulmamış ses-altı '
            'rejimde aynı özdeşlik fiktif sonik alan A*_eff ile.'),
        'mass_conservation_rel_residual': mass_residual,
        'not_modelled': dict(QUASI1D_NOT_MODELLED),
        'assumptions': list(_ASSUMPTIONS),
        'inputs': {
            'P0_Pa': P0,
            'T0_K': T0,
            'gamma': g,
            'R_J_kgK': Rs,
            'Pb_Pa': Pb,
            '_basis': 'Çağıranın verdiği girdilerin yankısı (SI birimleri).',
        },
    }
