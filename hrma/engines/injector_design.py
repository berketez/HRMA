# -*- coding: utf-8 -*-
"""Enjektör tasarım modülü — hibrit (yalnız oksitleyici) ve sıvı (çift yakıt).

TEK gerçek kaynak: docs/10_Enjektor_ARGE.md (2026-07-13 ARGE + API sözleşmesi).
Bu modül saf hesaptır: Flask/HTTP içermez; `design_injector(spec)` sözlük alır,
sözlük döner (şema: spec Bölüm B.2).

Ana fizik:
- Orifis akışı: ṁ = Cd·A·√(2ρΔP) (SPI; Sutton & Biblarz 9. baskı Böl. 8,
  NASA SP-8089).
- Kendinden basınçlı N₂O: Dyer NHNE — ṁ = (κ·ṁ_SPI + ṁ_HEM)/(1+κ),
  κ = √((P₁−P₂)/(P_v−P₂)) (Dyer/Doran/Dunn/Zilliac AIAA 2007-5702;
  deneysel doğrulama ±%15). Doyma özellikleri tank_blowdown.N2OSaturation
  ile paylaşılır; izentropik HEM için doyma entropisi bu modülde tablo olarak
  tutulur (CoolProp/Span-Wagner'dan üretildi, 2026-07-13).
- Atomizasyon SMD: Elkotb 1982 (düz orifis), Lefebvre (basınç-swirl),
  We^(−1/3) eğilimli impinging (C_imp=2.6, kalibre edilebilir).
  Ortam yoğunluğu HER ZAMAN oda gazı yoğunluğudur.
- Kararlılık: ΔP/Pc ≥ 0.15-0.20 chug kuralı (SP-8089); Nurick kavitasyon
  sayısıyla hydraulic-flip bayrağı; N₂O besleme kuplajı notu (NTRS 20190001326).
"""

import numpy as np

from hrma.constants import R_UNIVERSAL, PA_PER_BAR
from hrma.analysis.tank_blowdown import N2OSaturation

# ---------------------------------------------------------------------------
# Modül sabitleri (ARGE raporu A.2-A.9)
# ---------------------------------------------------------------------------

# Cd seçim tablosu: (giriş tipi, L/D bandı) → (Cd, gerekçe)  [SP-8089; Lefebvre
# & McDonell 2. baskı Böl. 5]
CD_TABLE = [
    # (inlet, l_over_d_min, l_over_d_max, cd, aciklama)
    ('sharp',    0.0,  1.0, 0.63, 'keskin giriş, kısa (L/D<1): vena contracta hakim'),
    ('sharp',    1.0,  5.0, 0.78, 'keskin giriş, yeniden yapışan (L/D 1-5)'),
    ('sharp',    5.0, 99.0, 0.84, 'keskin giriş, uzun (L/D 5-10): sürtünme artar'),
    ('radiused', 0.0,  2.0, 0.90, 'radüslü giriş (r/d ≥ 0.15), kısa'),
    ('radiused', 2.0, 99.0, 0.92, 'radüslü giriş (r/d ≥ 0.15): kararlı Cd'),
]

CHUG_DP_PC_MIN = 0.15          # NASA SP-8089 alt sınırı
CHUG_DP_PC_RECOMMENDED = 0.20  # doymuş N₂O'da önerilen
FLIP_KC_LIMIT = 1.5            # Nurick 1976: K_c < 1.5 + keskin giriş → flip riski
MANIFOLD_V_RATIO_TARGET = 0.1  # manifold/orifis hız oranı hedefi (≤%2 sapma)
MANIFOLD_V_RATIO_MAX = 0.2     # kabul edilebilir üst sınır (uyarıyla)
MANIFOLD_AREA_RATIO_MIN = 4.0  # Huzel & Huang Böl. 4 pratiği
IMPINGE_HALF_ANGLE_DEG = 30.0  # tipik 2θ = 60° (SP-8089)
FREE_JET_LD = 6.0              # impingement mesafesi 5-7·d_j ortası
ELEMENT_SPACING_D = 3.0        # eleman merkez aralığı ≥ 3·d
MR_BAND = (0.7, 1.3)           # doublet momentum oranı / Rupe pratik bandı
C_IMP_SMD = 2.6                # impinging SMD sabiti (band 2-4; Ingebo TN 3265 eğilimi)
PINTLE_BF_BAND = (0.3, 0.74)   # TRW mirası (Dressler & Bauer AIAA 2000-3871)
PINTLE_SKIP_LS_DP = 1.0        # skip distance kuralı L_s/D_p ≈ 1
# Hibrit (tek akışkan, ox-merkezli) pintle: oksitleyici alanının radyal
# deliklere giden payı; kalanı anülüsten eksenel tabaka olarak akar.
# 0.5 → radyal/anüler momentum oranı 1 (aynı akışkan, aynı ΔP) → θ ≈ 60°.
PINTLE_HYBRID_RADIAL_FRACTION = 0.5
PINTLE_ANNULUS_T_OVER_DP = 0.05  # D_p verilmezse anülüs boşluk/çap kuralı
ANNULUS_GAP_MIN_MM = 0.3       # imalat alt sınırı
RHO_GAS_DEFAULT = 5.0          # kg/m³ — T_c/MW verilmezse varsayılan oda gazı
ORIFICE_D_PREF_MM = (0.5, 2.5) # tercih edilen delik çapı bandı
DEFAULT_CONSTRAINTS = {'d_min_mm': 0.3, 'd_max_mm': 3.0, 'n_max': 120}

# N₂O doyma ENTROPİSİ [J/(kg·K)]: T[K], s_l, s_v — CoolProp/Span-Wagner'dan
# üretildi (2026-07-13); tank_blowdown._SAT_TABLE ile aynı sıcaklık ızgarası.
# İzentropik HEM çıkış hâli (s₂=s₁) için gereklidir; ana doyma tablosunda
# entropi yoktur.
_N2O_ENTROPY_TABLE = np.array([
    (240.0, 461.5, 1711.4),
    (243.0, 484.5, 1698.2),
    (246.0, 507.5, 1685.1),
    (249.0, 530.4, 1672.2),
    (252.0, 553.3, 1659.3),
    (255.0, 576.1, 1646.4),
    (258.0, 598.9, 1633.6),
    (261.0, 621.7, 1620.7),
    (264.0, 644.6, 1607.6),
    (267.0, 667.5, 1594.5),
    (270.0, 690.5, 1581.1),
    (273.0, 713.7, 1567.4),
    (276.0, 737.1, 1553.3),
    (279.0, 760.7, 1538.8),
    (282.0, 784.7, 1523.7),
    (285.0, 809.2, 1507.8),
    (288.0, 834.2, 1490.9),
    (291.0, 860.0, 1472.8),
    (294.0, 886.8, 1452.9),
    (297.0, 915.1, 1430.8),
    (300.0, 945.6, 1405.2),
    (303.0, 979.8, 1374.1),
    (306.0, 1021.7, 1332.0),
])

_SAT = N2OSaturation(use_coolprop=False)  # tabloyla deterministik (test tekrarlanabilirliği)

REFERENCES = [
    'NASA SP-8089 (1976) — Liquid Rocket Engine Injectors',
    'Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 8-9',
    'Huzel & Huang, Böl. 4 (manifold pratiği)',
    'Lefebvre & McDonell, Atomization and Sprays 2. baskı',
    'Dyer ve ark., AIAA 2007-5702 (NHNE)',
    'Nurick, ASME J. Fluids Eng. 1976 (kavitasyon/flip)',
    'Rupe, JPL 20-195 (1953) — karışım kriteri',
    'Elkotb, PECS 1982 (SMD)',
    'Giffen & Muraszew (1953) — swirl teorisi',
    'Casiano/Hulka/Yang, JPP 26(5) 2010 + Cheng 2017 + AIAA 2000-3871 (pintle)',
    'NASA NTRS 20190001326 (N₂O enjektör izolasyonu)',
]


# ---------------------------------------------------------------------------
# Saf yardımcı fonksiyonlar (dışa açık, test edilebilir)
# ---------------------------------------------------------------------------

def spi_mass_flow(cd, area_m2, rho, dp_pa):
    """Tek fazlı sıkıştırılamaz orifis debisi: ṁ = Cd·A·√(2ρΔP) [kg/s]."""
    if dp_pa <= 0:
        return 0.0
    return float(cd * area_m2 * np.sqrt(2.0 * rho * dp_pa))


def _n2o_s_l(T):
    T = float(np.clip(T, _N2O_ENTROPY_TABLE[0, 0], _N2O_ENTROPY_TABLE[-1, 0]))
    return float(np.interp(T, _N2O_ENTROPY_TABLE[:, 0], _N2O_ENTROPY_TABLE[:, 1]))


def _n2o_s_v(T):
    T = float(np.clip(T, _N2O_ENTROPY_TABLE[0, 0], _N2O_ENTROPY_TABLE[-1, 0]))
    return float(np.interp(T, _N2O_ENTROPY_TABLE[:, 0], _N2O_ENTROPY_TABLE[:, 2]))


def _n2o_tsat_from_p(p_pa):
    """Doyma sıcaklığı P'den (tablo ters interpolasyonu)."""
    grid_T = np.arange(240.0, 306.5, 0.5)
    grid_P = np.array([_SAT.psat(t) for t in grid_T])
    p = float(np.clip(p_pa, grid_P[0], grid_P[-1]))
    return float(np.interp(p, grid_P, grid_T))


def hem_mass_flow(cd, area_m2, fluid_state):
    """Homojen denge modeli (HEM) debisi [kg/s] — izentropik çıkış, boğulma taramalı.

    ṁ = Cd·A·G,  G(P_t) = ρ₂(P_t)·√(2(h₁−h₂(P_t))),  s₂ = s₁.
    G, P_t ∈ [P₂, P₁] üzerinde taranır; maksimum P₂'den önce geliyorsa akış
    boğulmuştur ve G = G_maks alınır (Solomon 2011 uygulama deseni).

    fluid_state: {'T1_K', 'p1_pa', 'p2_pa'} — doymuş/az-soğutulmuş N₂O girişi.
    """
    T1 = float(fluid_state['T1_K'])
    p1 = float(fluid_state['p1_pa'])
    p2 = float(fluid_state['p2_pa'])
    p_v = _SAT.psat(T1)

    # Giriş hâli: doymuş sıvı entropisi/entalpisi; az-soğutulmuşsa sıvı
    # sıkıştırılamaz kabul edilir (s₁≈s_l(T₁), h₁≈h_l(T₁)+ΔP/ρ_l)
    rho_l1 = _SAT.rho_l(T1)
    h1 = _SAT.h_l(T1) + max(p1 - p_v, 0.0) / rho_l1
    s1 = _n2o_s_l(T1)

    if p2 >= p_v:
        # Çıkışta flaşlama yok → tek fazlı sıvı: SPI ile özdeş
        return spi_mass_flow(cd, area_m2, rho_l1, p1 - p2)

    def G_at(pt_pa):
        Tt = _n2o_tsat_from_p(pt_pa)
        s_l, s_v = _n2o_s_l(Tt), _n2o_s_v(Tt)
        x = (s1 - s_l) / max(s_v - s_l, 1e-9)
        x = float(np.clip(x, 0.0, 1.0))
        h2 = _SAT.h_l(Tt) + x * (_SAT.h_v(Tt) - _SAT.h_l(Tt))
        rho2 = 1.0 / ((1.0 - x) / _SAT.rho_l(Tt) + x / max(_SAT.rho_v(Tt), 1e-9))
        dh = max(h1 - h2, 0.0)
        return rho2 * np.sqrt(2.0 * dh), x

    # Boğulma taraması: P_t'yi P₂ → P₁ arasında tara, G maksimumunu bul
    pts = np.linspace(p2, min(p1, p_v) * 0.999, 60)
    G_vals = [G_at(pt)[0] for pt in pts]
    i_max = int(np.argmax(G_vals))
    G = G_vals[0] if G_vals[i_max] <= G_vals[0] else G_vals[i_max]
    return float(cd * area_m2 * G)


def _hem_exit_quality(T1_K, p1_pa, p2_pa):
    """HEM çıkış kalitesi x₂ (arka basınçta) — rapor alanı için."""
    p_v = _SAT.psat(T1_K)
    if p2_pa >= p_v:
        return 0.0
    s1 = _n2o_s_l(T1_K)
    Tt = _n2o_tsat_from_p(p2_pa)
    x = (s1 - _n2o_s_l(Tt)) / max(_n2o_s_v(Tt) - _n2o_s_l(Tt), 1e-9)
    return float(np.clip(x, 0.0, 1.0))


def nhne_mass_flow(cd, area_m2, p1_bar, p2_bar, pv_bar, T1_K, rho_l=None):
    """Dyer NHNE debisi ve bileşenleri.

    κ = √((P₁−P₂)/(P_v−P₂));  ṁ = (κ·ṁ_SPI + ṁ_HEM)/(1+κ).
    P₂ ≥ P_v ise flaşlama yok → saf SPI (κ anlamsız, inf raporlanır).

    Döner: {'mdot_kg_s','kappa','mdot_spi_kg_s','mdot_hem_kg_s','quality_out'}
    """
    p1, p2, pv = (p1_bar * PA_PER_BAR, p2_bar * PA_PER_BAR, pv_bar * PA_PER_BAR)
    if rho_l is None:
        rho_l = _SAT.rho_l(T1_K)
    m_spi = spi_mass_flow(cd, area_m2, rho_l, p1 - p2)

    if p2 >= pv:  # aşırı soğutulmuş / arka basınç doymanın üstünde: iki faz yok
        return {'mdot_kg_s': m_spi, 'kappa': float('inf'),
                'mdot_spi_kg_s': m_spi, 'mdot_hem_kg_s': m_spi,
                'quality_out': 0.0}

    m_hem = hem_mass_flow(cd, area_m2,
                          {'T1_K': T1_K, 'p1_pa': p1, 'p2_pa': p2})
    kappa = float(np.sqrt(max(p1 - p2, 0.0) / max(pv - p2, 1e-9)))
    m_nhne = (kappa * m_spi + m_hem) / (1.0 + kappa)
    return {'mdot_kg_s': float(m_nhne), 'kappa': kappa,
            'mdot_spi_kg_s': float(m_spi), 'mdot_hem_kg_s': float(m_hem),
            'quality_out': _hem_exit_quality(T1_K, p1, p2)}


def discharge_coefficient(inlet, l_over_d):
    """Cd seçimi + gerekçe (SP-8089 / Lefebvre tablosu). → (cd, gerekçe_str)."""
    inlet = str(inlet).lower()
    if inlet not in ('sharp', 'radiused'):
        raise ValueError(f"Geçersiz orifis giriş tipi: '{inlet}' "
                         "(beklenen: 'sharp' veya 'radiused')")
    for tip, lo, hi, cd, why in CD_TABLE:
        if tip == inlet and lo <= l_over_d < hi:
            return cd, (f"{why}; L/D={l_over_d:g} → Cd={cd} "
                        f"(SP-8089 / Lefebvre & McDonell Böl. 5)")
    # l_over_d bandların dışına taşarsa en yakın uç
    cd, why = (0.84, 'keskin giriş, uzun') if inlet == 'sharp' else \
              (0.92, 'radüslü giriş, uzun')
    return cd, f"{why}; L/D={l_over_d:g} → Cd={cd} (tablo dışı, uç değer)"


def hydraulic_flip_risk(inlet, l_over_d, cavitation_number):
    """Nurick flip kuralı: keskin giriş + L/D 1-5 + K_c < 1.5 → riskli."""
    return bool(str(inlet).lower() == 'sharp'
                and 1.0 <= l_over_d <= 5.0
                and cavitation_number < FLIP_KC_LIMIT)


def smd_elkotb(nu_l_m2s, sigma_n_m, rho_l, rho_gas, dp_pa):
    """Elkotb (1982) düz orifis SMD [m]:
    SMD = 3.08·ν^0.385·(σρ_l)^0.737·ρ_A^0.06·ΔP^(−0.54)."""
    return float(3.08 * nu_l_m2s ** 0.385 * (sigma_n_m * rho_l) ** 0.737
                 * rho_gas ** 0.06 * dp_pa ** (-0.54))


def smd_lefebvre_swirl(sigma_n_m, mu_l_pas, mdot_l, dp_pa, rho_gas):
    """Lefebvre basınç-swirl SMD [m]:
    SMD = 2.25·σ^0.25·μ^0.25·ṁ^0.25·ΔP^(−0.5)·ρ_A^(−0.25)."""
    return float(2.25 * sigma_n_m ** 0.25 * mu_l_pas ** 0.25
                 * mdot_l ** 0.25 * dp_pa ** (-0.5) * rho_gas ** (-0.25))


def smd_impinging(d_jet_m, v_jet, rho_l, sigma_n_m, c_imp=C_IMP_SMD):
    """Impinging SMD [m]: D₃₂ = C_imp·d_j·We_j^(−1/3), We_j = ρ_l·v²·d_j/σ.
    C_imp=2.6 varsayılan (band 2-4; test verisiyle kalibre edilebilir)."""
    we = rho_l * v_jet ** 2 * d_jet_m / sigma_n_m
    return float(c_imp * d_jet_m * we ** (-1.0 / 3.0))


def swirl_solve(K):
    """Giffen–Muraszew çözümü: K → {'X','cd','theta_deg','film_t_ratio'}.

    K = √(32/π²)·√((1−X)³/X²) bağıntısından X kök araması (0<X<1);
    Cd = √((1−X)³/(1+X));  sinθ = (π/2)·Cd/(K·(1+√X));
    film kalınlığı oranı t/r_o = 1−√X.
    """
    if K <= 0:
        raise ValueError('Swirl atomizör sabiti K pozitif olmalı')
    coef = np.sqrt(32.0 / np.pi ** 2)

    def f(x):
        return coef * np.sqrt((1.0 - x) ** 3 / x ** 2) - K

    lo, hi = 1e-6, 1.0 - 1e-6
    for _ in range(200):  # bisection — f monoton azalan
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    X = 0.5 * (lo + hi)
    cd = float(np.sqrt((1.0 - X) ** 3 / (1.0 + X)))
    sin_theta = float(np.clip((np.pi / 2.0) * cd / (K * (1.0 + np.sqrt(X))),
                              -1.0, 1.0))
    return {'X': float(X), 'cd': cd,
            'theta_deg': float(np.degrees(np.arcsin(sin_theta))),
            'film_t_ratio': float(1.0 - np.sqrt(X))}


def swirl_K_from_theta(theta_target_deg):
    """Hedef sprey yarı açısından K çöz (iç içe kök araması, monoton)."""
    lo, hi = 0.02, 20.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        th = swirl_solve(mid)['theta_deg']
        if th > theta_target_deg:  # K büyüdükçe θ küçülür
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def pintle_spray_angle(tmr):
    """Pintle sprey yarı açısı [deg]: θ = arccos(1/(1+TMR)) (Cheng 2017)."""
    if tmr < 0:
        raise ValueError('TMR negatif olamaz')
    return float(np.degrees(np.arccos(1.0 / (1.0 + tmr))))


# ---------------------------------------------------------------------------
# Delik planı ve manifold
# ---------------------------------------------------------------------------

def _plan_orifices(total_area_m2, constraints, warnings_tr, n_fixed=None):
    """Toplam alanı, çapı tercihen 0.5-2.5 mm bandına oturtan n deliğe böl.

    n_fixed verilirse delik sayısı sabitlenir (yalnız çap çözülür) — kullanıcı
    plan kısıtı veya doğrulama senaryoları için.
    """
    d_min = constraints.get('d_min_mm', 0.3) * 1e-3
    d_max = constraints.get('d_max_mm', 3.0) * 1e-3
    n_max = int(constraints.get('n_max', 120))
    d_lo, d_hi = ORIFICE_D_PREF_MM[0] * 1e-3, ORIFICE_D_PREF_MM[1] * 1e-3

    if n_fixed is not None:
        n = int(n_fixed)
        if n < 1:
            raise ValueError('Delik sayısı en az 1 olmalı')
        d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))
        if not (d_min <= d <= d_max):
            warnings_tr.append(
                f"Sabitlenen n={n} ile delik çapı d={d*1e3:.2f} mm imalat "
                f"bandının ({d_min*1e3:.1f}-{d_max*1e3:.1f} mm) dışında.")
        elif not (d_lo <= d <= d_hi):
            warnings_tr.append(
                f"Sabitlenen n={n} ile d={d*1e3:.2f} mm tercih bandının "
                "(0.5-2.5 mm) dışında.")
        return n, float(d)

    best = None
    for n in range(1, n_max + 1):
        d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))
        if d_lo <= d <= d_hi:
            best = (n, d)   # bandın içindeki EN KÜÇÜK n (en büyük d) → dur
            break
    if best is None:
        # Band tutturulamadı: kısıt sınırında en yakın çözüm
        n = n_max
        d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))
        if d > d_max:
            warnings_tr.append(
                f"Delik kısıtlarıyla (n≤{n_max}, d≤{d_max*1e3:.1f} mm) istenen"
                f" debi tek katmanda sağlanamıyor: d={d*1e3:.2f} mm gerekti."
                " Delik sayısı üst sınırını artırın veya ΔP'yi yükseltin.")
        elif d > d_hi:
            warnings_tr.append(
                f"Delik çapı tercih bandının (0.5-2.5 mm) üstünde: "
                f"d={d*1e3:.2f} mm (n üst sınırı {n_max} yetersiz).")
        elif d < d_min:
            n = max(1, int(np.floor(4.0 * total_area_m2 / (np.pi * d_min ** 2))))
            n = min(n, n_max)
            d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))
            warnings_tr.append(
                f"Delik çapı tercih bandının (0.5-2.5 mm) altında:"
                f" d={d*1e3:.2f} mm (imalat alt sınırına yakın).")
        best = (n, d)
    n, d = best
    return int(n), float(d)


def _manifold(mdot, rho, v_orifice):
    """Manifold boyutlandırma: hız oranı hedefi 0.1 → çap ve oranlar."""
    v_man = MANIFOLD_V_RATIO_TARGET * v_orifice
    a_man = mdot / max(rho * v_man, 1e-12)
    d_man = np.sqrt(4.0 * a_man / np.pi)
    return {'d_mm': float(d_man * 1e3), 'velocity_m_s': float(v_man),
            'v_ratio': float(v_man / max(v_orifice, 1e-9)),
            'area_ratio': float(1.0 / MANIFOLD_V_RATIO_TARGET)}


# ---------------------------------------------------------------------------
# Devre çözümü (ox veya fuel)
# ---------------------------------------------------------------------------

def _solve_circuit(name, mdot, rho, pc_bar, dp_ratio, p_feed_bar, fluid,
                   T_K, inlet, l_over_d, constraints, warnings_tr,
                   assumptions_tr, cd_override=None, cd_basis_override=None,
                   n_fixed=None):
    """Tek devre (ox/fuel) akış + delik planı + manifold + flip çözümü."""
    spec_p_feed_given = p_feed_bar is not None
    if p_feed_bar is None:
        p_feed_bar = pc_bar * (1.0 + dp_ratio)

    is_n2o = (fluid == 'n2o')
    p_sat_bar = None
    if is_n2o:
        if T_K is None:
            raise ValueError("N₂O devresi için T_ox_K (doyma sıcaklığı) zorunlu")
        p_sat_bar = _SAT.psat(T_K) / PA_PER_BAR
        # Kendinden basınçlı doymuş tank: p_feed verilmemişse P₁ = P_sat
        # (ARGE Ö2 örneğiyle tutarlı — ΔP burada tasarım değişkeni değil,
        # tank sıcaklığının sonucudur). Verilmişse doymayı aşamaz.
        if spec_p_feed_given:
            p1_bar = min(p_feed_bar, p_sat_bar)
        else:
            p1_bar = p_sat_bar
        if rho is None:
            rho = _SAT.rho_l(T_K)
            assumptions_tr.append(
                f"ρ_ox doyma tablosundan alındı: {rho:.0f} kg/m³ (T={T_K:.1f} K)")
    else:
        p1_bar = p_feed_bar
        if rho is None:
            raise ValueError(f"{name} devresi için yoğunluk (rho) zorunlu")

    dp_bar = p1_bar - pc_bar
    if dp_bar <= 0:
        raise ValueError(
            f"{name} devresinde ΔP ≤ 0 (P₁={p1_bar:.1f} bar, Pc={pc_bar:.1f} "
            "bar): besleme basıncı oda basıncını aşmalı")
    dp_pa = dp_bar * PA_PER_BAR

    if cd_override is not None:
        cd, cd_basis = cd_override, (cd_basis_override or 'tip özel Cd')
    else:
        cd, cd_basis = discharge_coefficient(inlet, l_over_d)

    # Birim alan debisi → toplam alan
    if is_n2o:
        probe = nhne_mass_flow(cd, 1.0, p1_bar, pc_bar, p_sat_bar, T_K, rho)
        g_eff = probe['mdot_kg_s']  # kg/s başına m² (Cd dahil)
        flow_model = 'NHNE'
    else:
        g_eff = spi_mass_flow(cd, 1.0, rho, dp_pa)
        flow_model = 'SPI'
    total_area = mdot / max(g_eff, 1e-12)

    n, d = _plan_orifices(total_area, constraints, warnings_tr, n_fixed=n_fixed)
    a_total = n * np.pi * d ** 2 / 4.0
    # Efektif enjeksiyon hızı (SPI özdeşliğinden; NHNE'de sıvı giriş hızı)
    v_inj = float(cd * np.sqrt(2.0 * dp_pa / rho))

    nhne_block = None
    if is_n2o:
        full = nhne_mass_flow(cd, a_total, p1_bar, pc_bar, p_sat_bar, T_K, rho)
        nhne_block = {'kappa': full['kappa'],
                      'mdot_spi_kg_s': full['mdot_spi_kg_s'],
                      'mdot_hem_kg_s': full['mdot_hem_kg_s'],
                      'p_sat_bar': float(p_sat_bar),
                      'quality_out': full['quality_out']}

    # Nurick kavitasyon sayısı: K_c = (P₁ − P_v)/(P₁ − P₂)
    if is_n2o:
        p_v_bar = p_sat_bar
    else:
        p_v_bar = 0.05  # depolanabilir sıvılar için ~hava basıncı altı varsayım
        assumptions_tr.append(
            f"{name}: buhar basıncı ~{p_v_bar} bar varsayıldı (K_c hesabı)")
    k_c = (p1_bar - p_v_bar) / max(p1_bar - pc_bar, 1e-9)
    flip = hydraulic_flip_risk(inlet, l_over_d, k_c)
    if flip:
        warnings_tr.append(
            f"{name}: hydraulic flip riski (keskin giriş, L/D={l_over_d:g}, "
            f"K_c={k_c:.2f} < {FLIP_KC_LIMIT}). Çözüm: radüslü giriş veya L/D ≥ 5.")

    return {
        'mdot_kg_s': float(mdot),
        'delta_p_bar': float(dp_bar),
        'dp_pc_ratio': float(dp_bar / pc_bar),
        'velocity_m_s': v_inj,
        'cd': float(cd), 'cd_basis': cd_basis,
        'n_orifices': int(n),
        'orifice_d_mm': float(d * 1e3),
        'total_area_mm2': float(a_total * 1e6),
        'flow_model': flow_model,
        'nhne': nhne_block,
        'cavitation_number': float(k_c),
        'hydraulic_flip_risk': flip,
        'manifold': _manifold(mdot, rho, v_inj),
        '_rho': float(rho),  # iç kullanım (tip geometrisi); çıktıda kalır, zararsız
    }


# ---------------------------------------------------------------------------
# Ana giriş noktası
# ---------------------------------------------------------------------------

_VALID_TYPES = ('showerhead', 'impinging_doublet', 'impinging_triplet',
                'like_impinging', 'pintle', 'coax_swirl', 'swirl')


def design_injector(spec):
    """Enjektör tasarımı — docs/10_Enjektor_ARGE.md B sözleşmesi.

    Girdi/çıktı şeması için ARGE raporuna bakınız. Doğrulama hatasında
    Türkçe mesajlı ValueError; fiziksel imkânsızlıkta
    {'status':'error','error': ...} döner.
    """
    if not isinstance(spec, dict):
        raise ValueError('spec bir sözlük olmalı')

    motor_type = spec.get('motor_type')
    if motor_type not in ('hybrid', 'liquid'):
        raise ValueError("motor_type 'hybrid' veya 'liquid' olmalı")

    inj_type = spec.get('injector_type') or \
        ('showerhead' if motor_type == 'hybrid' else 'impinging_doublet')
    if inj_type not in _VALID_TYPES:
        raise ValueError(f"Geçersiz injector_type: '{inj_type}' "
                         f"(geçerli: {', '.join(_VALID_TYPES)})")

    mdot_ox = spec.get('mdot_ox')
    if not mdot_ox or mdot_ox <= 0:
        raise ValueError('mdot_ox pozitif olmalı (kg/s)')
    pc_bar = spec.get('Pc_bar')
    if not pc_bar or pc_bar <= 0:
        raise ValueError('Pc_bar pozitif olmalı (bar)')

    mdot_fuel = spec.get('mdot_fuel')
    if motor_type == 'liquid':
        if not mdot_fuel or mdot_fuel <= 0:
            raise ValueError('Sıvı motorda mdot_fuel zorunludur (kg/s, > 0)')
    else:
        mdot_fuel = None
        # Pintle hibritte MEŞRUDUR: oksitleyici-merkezli tek akışkan düzen
        # (merkez pintle gövdesi + anülüs ox akışı). Yakıt grain'den geldiği
        # için TMR/mdot_fuel gerekmez — BF, anülüs boşluğu ve skip distance
        # yine raporlanır (Dressler & Bauer AIAA 2000-3871 geometri pratiği).
        if inj_type in ('impinging_doublet', 'impinging_triplet', 'coax_swirl'):
            raise ValueError(
                f"'{inj_type}' hibritte desteklenmez (tek akışkan): "
                "showerhead, swirl, pintle veya like_impinging kullanın")

    warnings_tr, assumptions_tr = [], []
    constraints = dict(DEFAULT_CONSTRAINTS)
    constraints.update(spec.get('orifice_constraints') or {})

    dp_ox = spec.get('dp_ratio_ox', 0.20)
    dp_f = spec.get('dp_ratio_fuel', 0.20)
    fluid_ox = spec.get('fluid_ox', 'generic')
    inlet_ox = spec.get('inlet_ox', 'sharp')
    inlet_f = spec.get('inlet_fuel', 'sharp')
    l_over_d = spec.get('l_over_d', 4.0)

    # Swirl tiplerinde efektif Cd Giffen–Muraszew'den gelir (orifis Cd yerine)
    swirl_geom = None
    cd_override = None
    cd_basis_override = None
    if inj_type in ('swirl', 'coax_swirl'):
        sw_in = spec.get('swirl') or {}
        K = sw_in.get('K')
        theta_t = sw_in.get('theta_target_deg', 45.0)
        if K is None:
            # Giffen–Muraszew sinθ bağıntısının tavanı ~18°: bunun üstündeki
            # hedefler çözülemez (K→0, Cd→0 çöküşü). Ulaşılamaz hedefte tipik
            # atomizör sabiti K=1'e düşülür ve uyarı verilir.
            if theta_t > 16.0:
                K = 1.0
                warnings_tr.append(
                    f"Swirl sprey yarı açısı hedefi {theta_t:.0f}° "
                    "Giffen–Muraszew bağıntısının tavanının (~18°) üstünde; "
                    "tipik K=1.0 ile tasarlandı (θ≈13°). Daha geniş koni için "
                    "deneysel kalibrasyon gerekir.")
            else:
                K = swirl_K_from_theta(theta_t)
        sw = swirl_solve(K)
        cd_override = sw['cd']
        cd_basis_override = (f"Giffen–Muraszew swirl: K={K:.3f} → X={sw['X']:.3f}"
                             f" → Cd={sw['cd']:.3f} (düz orifisten düşük olması"
                             " fizikseldir)")
        swirl_geom = (K, sw)

    try:
        ox = _solve_circuit(
            'oksitleyici', mdot_ox, spec.get('rho_ox'), pc_bar, dp_ox,
            spec.get('p_feed_bar'), fluid_ox, spec.get('T_ox_K'),
            inlet_ox, l_over_d, constraints, warnings_tr, assumptions_tr,
            cd_override=cd_override, cd_basis_override=cd_basis_override,
            n_fixed=spec.get('n_orifices_ox'))
        fuel = None
        if mdot_fuel:
            fuel = _solve_circuit(
                'yakıt', mdot_fuel, spec.get('rho_fuel'), pc_bar, dp_f,
                spec.get('p_feed_bar_fuel'), 'generic', None,
                inlet_f, l_over_d, constraints, warnings_tr, assumptions_tr,
                n_fixed=spec.get('n_orifices_fuel'))
    except ValueError:
        raise
    except Exception as exc:  # fiziksel imkânsızlık / sayısal çöküş
        return {'status': 'error', 'error': f'Tasarım çözülemedi: {exc}'}

    # ------------------------------------------------------------------
    # Ortam gazı yoğunluğu (atomizasyon)
    # ------------------------------------------------------------------
    T_c = spec.get('T_c_K')
    mw = spec.get('mw_gas')
    if T_c and mw:
        rho_gas = pc_bar * PA_PER_BAR / ((R_UNIVERSAL / mw) * T_c)
    else:
        rho_gas = RHO_GAS_DEFAULT
        assumptions_tr.append(
            f"Oda gazı yoğunluğu varsayıldı: {RHO_GAS_DEFAULT} kg/m³ "
            "(T_c_K + mw_gas verilirse hesaplanır)")

    sigma_ox = spec.get('sigma_ox', 0.02)
    sigma_f = spec.get('sigma_fuel', 0.02)
    mu_ox = spec.get('mu_ox', 2e-4)
    mu_f = spec.get('mu_fuel', 2e-4)

    # ------------------------------------------------------------------
    # Tip özel geometri + momentum + atomizasyon
    # ------------------------------------------------------------------
    momentum = None
    pintle_geometry = None
    swirl_geometry = None
    impingement = None
    spray_half = None
    smd_fuel_um = None
    n_elements = ox['n_orifices']

    d_ox_m = ox['orifice_d_mm'] * 1e-3
    v_ox = ox['velocity_m_s']
    rho_ox_l = ox['_rho']

    if inj_type == 'showerhead':
        nu_ox = mu_ox / rho_ox_l
        smd_ox = smd_elkotb(nu_ox, sigma_ox, rho_ox_l, rho_gas,
                            ox['delta_p_bar'] * PA_PER_BAR)
        correlation = 'Elkotb-1982'
        if fuel is not None:
            nu_f = mu_f / fuel['_rho']
            smd_fuel_um = smd_elkotb(nu_f, sigma_f, fuel['_rho'], rho_gas,
                                     fuel['delta_p_bar'] * PA_PER_BAR) * 1e6
        desc = (f"{ox['n_orifices']} delikli showerhead "
                f"(d={ox['orifice_d_mm']:.2f} mm, eksenel paralel jetler)")

    elif inj_type in ('impinging_doublet', 'impinging_triplet', 'like_impinging'):
        smd_ox = smd_impinging(d_ox_m, v_ox, rho_ox_l, sigma_ox)
        correlation = 'impinging-We13'
        half = IMPINGE_HALF_ANGLE_DEG
        impingement = {
            'half_angle_deg': half,
            'free_jet_length_mm': float(FREE_JET_LD * d_ox_m * 1e3),
            'element_spacing_mm': float(ELEMENT_SPACING_D
                                        * max(d_ox_m, 1e-9) * 1e3),
        }
        if inj_type == 'impinging_doublet' and fuel is not None:
            d_f_m = fuel['orifice_d_mm'] * 1e-3
            v_f = fuel['velocity_m_s']
            rho_f_l = fuel['_rho']
            smd_fuel_um = smd_impinging(d_f_m, v_f, rho_f_l, sigma_f) * 1e6
            mr = (mdot_fuel * v_f) / (mdot_ox * v_ox)
            rupe = (rho_f_l * v_f ** 2 * d_f_m) / (rho_ox_l * v_ox ** 2 * d_ox_m)
            target = spec.get('target_velocity_ratio', 1.0)
            ok = MR_BAND[0] <= mr <= MR_BAND[1]
            momentum = {'momentum_ratio': float(mr), 'rupe_factor': float(rupe),
                        'tmr': None, 'target': float(target), 'ok': bool(ok)}
            if not ok:
                warnings_tr.append(
                    f"Doublet momentum oranı MR={mr:.2f} hedef bandın "
                    f"({MR_BAND[0]}-{MR_BAND[1]}) dışında: bileşke fan eksenden "
                    "sapar. Yakıt ΔP'sini/delik planını ayarlayın.")
            if not (MR_BAND[0] <= rupe <= MR_BAND[1]):
                warnings_tr.append(
                    f"Rupe karışım faktörü {rupe:.2f} optimum banttan "
                    "(0.7-1.3) uzak: karışım verimi düşer (Rupe, JPL 1953).")
            n_elements = min(ox['n_orifices'], fuel['n_orifices'])
            desc = (f"{n_elements} çift unlike doublet, 2θ={2*half:.0f}°, "
                    f"serbest jet {FREE_JET_LD:.0f}·d_j")
        elif inj_type == 'impinging_triplet' and fuel is not None:
            d_f_m = fuel['orifice_d_mm'] * 1e-3
            v_f = fuel['velocity_m_s']
            rho_f_l = fuel['_rho']
            smd_fuel_um = smd_impinging(d_f_m, v_f, rho_f_l, sigma_f) * 1e6
            # O-F-O: dış = oksitleyici (2 jet), orta = yakıt
            tmr = (2.0 * mdot_ox * v_ox * np.sin(np.radians(half))) \
                / max(mdot_fuel * v_f, 1e-12)
            ok = MR_BAND[0] <= tmr <= 2.0  # triplet doğal olarak O/F ile büyür
            momentum = {'momentum_ratio': None, 'rupe_factor': None,
                        'tmr': float(tmr), 'target': 1.0, 'ok': bool(ok)}
            n_elements = max(1, min(ox['n_orifices'] // 2, fuel['n_orifices']))
            desc = (f"{n_elements} adet O-F-O triplet (dış 2×oks., orta yakıt), "
                    f"2θ={2*half:.0f}°")
            if not ok:
                warnings_tr.append(
                    f"Triplet TMR={tmr:.2f} bandın dışında; dış/orta momentum "
                    "dengesini gözden geçirin.")
        else:  # like_impinging (kendi içinde çarpışan çiftler)
            n_elements = max(1, ox['n_orifices'] // 2)
            desc = (f"{n_elements} adet like-doublet (aynı akışkan çiftleri), "
                    f"2θ={2*half:.0f}° — blowapart riski yok")
            assumptions_tr.append(
                'Like-impinging: MR/Rupe unlike çarpışmaya özgüdür, raporlanmaz')

    elif inj_type == 'pintle' and fuel is None:
        # Hibrit (tek akışkan) pintle: yakıt grain'den geldiği için pintle
        # YALNIZ oksitleyiciyi taşır. Oksitleyici alanı ikiye bölünür:
        #   - radyal delikler (pintle ucunda, çevresel dizi) → BF
        #   - anülüs (pintle gövdesi çevresinde eksenel tabaka)
        # Sprey açısı, iki ox akımının momentum oranından (Cheng 2017
        # bağıntısı) gelir; aynı akışkan + aynı ΔP olduğu için hız eşittir,
        # dolayısıyla TMR = f/(1−f) (f = radyal pay).
        pin = spec.get('pintle') or {}
        bf_target = pin.get('bf_target', 0.58)
        f_rad = float(pin.get('radial_fraction', PINTLE_HYBRID_RADIAL_FRACTION))
        f_rad = float(np.clip(f_rad, 0.1, 0.9))

        a_total = ox['total_area_mm2'] * 1e-6
        a_rad = f_rad * a_total          # radyal delikler
        a_ann = a_total - a_rad          # anülüs

        d_p = pin.get('d_pintle_mm')
        if d_p is None:
            # Anülüs boşluğu t ≈ 0.05·D_p kuralıyla kendinden tutarlı D_p
            d_p_m = np.sqrt(a_ann / (np.pi * PINTLE_ANNULUS_T_OVER_DP))
        else:
            d_p_m = d_p * 1e-3
        # BF hedefi: n·d = BF·π·D_p ve n·(π/4)d² = A_rad → d, n çöz
        d_hole = (4.0 * a_rad / np.pi) / max(bf_target * np.pi * d_p_m, 1e-9)
        n_holes = max(4, int(round(bf_target * np.pi * d_p_m / max(d_hole, 1e-9))))
        d_hole = np.sqrt(4.0 * a_rad / (np.pi * n_holes))
        bf = n_holes * d_hole / (np.pi * d_p_m)
        t_ann = (np.sqrt(d_p_m ** 2 + 4.0 * a_ann / np.pi) - d_p_m) / 2.0
        if t_ann * 1e3 < ANNULUS_GAP_MIN_MM:
            warnings_tr.append(
                f"Pintle anülüs boşluğu {t_ann*1e3:.2f} mm < "
                f"{ANNULUS_GAP_MIN_MM} mm imalat sınırı")
        tmr = f_rad / max(1.0 - f_rad, 1e-9)
        theta = pintle_spray_angle(tmr)
        momentum = {'momentum_ratio': None, 'rupe_factor': None,
                    'tmr': float(tmr), 'target': pin.get('tmr_target', 1.0),
                    'ok': bool(0.5 <= tmr <= 2.0)}
        pintle_geometry = {
            'd_pintle_mm': float(d_p_m * 1e3),
            'skip_distance_mm': float(PINTLE_SKIP_LS_DP * d_p_m * 1e3),
            'ls_over_dp': float(PINTLE_SKIP_LS_DP),
            'bf': float(bf),
            'annulus_gap_mm': float(t_ann * 1e3),
            'n_radial_holes': int(n_holes),
            'radial_hole_d_mm': float(d_hole * 1e3),
            'radial_flow_fraction': f_rad,
            'single_fluid': True,
        }
        if not (PINTLE_BF_BAND[0] <= bf <= PINTLE_BF_BAND[1]):
            warnings_tr.append(
                f"Pintle BF={bf:.2f} TRW bandının ({PINTLE_BF_BAND[0]}-"
                f"{PINTLE_BF_BAND[1]}) dışında")
        assumptions_tr.append(
            f"Hibrit pintle tek akışkanlıdır: oksitleyici alanının %{f_rad*100:.0f}"
            "'i radyal deliklere, kalanı anülüse ayrıldı; sprey açısı bu iki "
            "ox akımının momentum oranından türetildi (yakıt grain'den gelir).")
        smd_ox = smd_impinging(d_hole, v_ox, rho_ox_l, sigma_ox)
        correlation = 'impinging-We13'
        spray_half = theta
        n_elements = 1
        desc = (f"Oksitleyici merkezli hibrit pintle: D_p={d_p_m*1e3:.1f} mm, "
                f"{n_holes}×{d_hole*1e3:.2f} mm radyal delik, anülüs "
                f"{t_ann*1e3:.2f} mm, TMR={tmr:.2f} → θ={theta:.0f}°")

    elif inj_type == 'pintle':
        # Yakıt merkezli TRW/Merlin düzeni: radyal iç jetler = yakıt,
        # anülüs dış akış = oksitleyici
        pin = spec.get('pintle') or {}
        bf_target = pin.get('bf_target', 0.58)
        d_f_m = fuel['orifice_d_mm'] * 1e-3
        v_f = fuel['velocity_m_s']
        rho_f_l = fuel['_rho']
        a_ann = ox['total_area_mm2'] * 1e-6      # anülüs = oks. toplam alanı
        a_rad = fuel['total_area_mm2'] * 1e-6    # radyal delikler = yakıt

        d_p = pin.get('d_pintle_mm')
        if d_p is None:
            # Anülüs boşluğu t ≈ 0.05·D_p kuralıyla kendinden tutarlı D_p
            d_p_m = np.sqrt(a_ann / (np.pi * 0.05))
        else:
            d_p_m = d_p * 1e-3
        # BF hedefi: n·d = BF·π·D_p ve n·(π/4)d² = A_rad → d, n çöz
        d_hole = (4.0 * a_rad / np.pi) / max(bf_target * np.pi * d_p_m, 1e-9)
        n_holes = max(4, int(round(bf_target * np.pi * d_p_m / max(d_hole, 1e-9))))
        d_hole = np.sqrt(4.0 * a_rad / (np.pi * n_holes))
        bf = n_holes * d_hole / (np.pi * d_p_m)
        t_ann = (np.sqrt(d_p_m ** 2 + 4.0 * a_ann / np.pi) - d_p_m) / 2.0
        if t_ann * 1e3 < ANNULUS_GAP_MIN_MM:
            warnings_tr.append(
                f"Pintle anülüs boşluğu {t_ann*1e3:.2f} mm < "
                f"{ANNULUS_GAP_MIN_MM} mm imalat sınırı")
        tmr = (mdot_fuel * v_f) / max(mdot_ox * v_ox, 1e-12)
        theta = pintle_spray_angle(tmr)
        momentum = {'momentum_ratio': None, 'rupe_factor': None,
                    'tmr': float(tmr), 'target': pin.get('tmr_target', 1.0),
                    'ok': bool(0.5 <= tmr <= 2.0)}
        pintle_geometry = {
            'd_pintle_mm': float(d_p_m * 1e3),
            'skip_distance_mm': float(PINTLE_SKIP_LS_DP * d_p_m * 1e3),
            'ls_over_dp': float(PINTLE_SKIP_LS_DP),
            'bf': float(bf),
            'annulus_gap_mm': float(t_ann * 1e3),
            'n_radial_holes': int(n_holes),
            'radial_hole_d_mm': float(d_hole * 1e3),
        }
        if not (PINTLE_BF_BAND[0] <= bf <= PINTLE_BF_BAND[1]):
            warnings_tr.append(
                f"Pintle BF={bf:.2f} TRW bandının ({PINTLE_BF_BAND[0]}-"
                f"{PINTLE_BF_BAND[1]}) dışında")
        smd_ox = smd_impinging(d_hole, np.hypot(v_ox, v_f), rho_f_l, sigma_f)
        smd_fuel_um = smd_ox * 1e6  # çarpışan tabaka ortak kırılımı
        correlation = 'impinging-We13'
        spray_half = theta
        n_elements = 1
        desc = (f"Yakıt merkezli pintle: D_p={d_p_m*1e3:.1f} mm, "
                f"{n_holes}×{d_hole*1e3:.2f} mm radyal delik, TMR={tmr:.2f} "
                f"→ θ={theta:.0f}°")

    else:  # swirl / coax_swirl
        K, sw = swirl_geom
        r_o = d_ox_m / 2.0
        r_s = 2.5 * r_o                     # tipik swirl odası oranı
        a_p = K * np.pi * r_s * r_o         # teğet giriş toplam alanı
        n_inlets = 3
        d_inlet = np.sqrt(4.0 * a_p / (np.pi * n_inlets))
        swirl_geometry = {
            'K': float(K), 'X_air_core': sw['X'], 'cd_swirl': sw['cd'],
            'swirl_number': float(np.pi * r_o * r_s / max(a_p, 1e-12)),
            'film_thickness_mm': float(sw['film_t_ratio'] * r_o * 1e3),
            'tangential_inlets': n_inlets,
            'inlet_d_mm': float(d_inlet * 1e3),
        }
        spray_half = sw['theta_deg']
        smd_ox = smd_lefebvre_swirl(sigma_ox, mu_ox, mdot_ox,
                                    ox['delta_p_bar'] * PA_PER_BAR, rho_gas)
        correlation = 'Lefebvre-swirl'
        assumptions_tr.append('Swirl odası yarıçapı r_s = 2.5·r_o varsayıldı')
        desc = (f"{'Koaksiyel ' if inj_type == 'coax_swirl' else ''}basınç-swirl: "
                f"K={K:.3f}, 2θ={2*sw['theta_deg']:.0f}°, "
                f"film {sw['film_t_ratio']*r_o*1e3:.2f} mm")
        if fuel is not None:
            nu_f = mu_f / fuel['_rho']
            smd_fuel_um = smd_elkotb(nu_f, sigma_f, fuel['_rho'], rho_gas,
                                     fuel['delta_p_bar'] * PA_PER_BAR) * 1e6
            assumptions_tr.append(
                'Swirl (sıvı): merkez oksitleyici swirl, yakıt dış devre (SPI)')

    # ------------------------------------------------------------------
    # Kararlılık
    # ------------------------------------------------------------------
    dp_pc_ox = ox['dp_pc_ratio']
    dp_pc_f = fuel['dp_pc_ratio'] if fuel else None
    chug_ok = dp_pc_ox >= CHUG_DP_PC_MIN and \
        (dp_pc_f is None or dp_pc_f >= CHUG_DP_PC_MIN)
    if not chug_ok:
        worst = min([r for r in (dp_pc_ox, dp_pc_f) if r is not None])
        warnings_tr.append(
            f"ΔP/Pc = {worst:.2f} < {CHUG_DP_PC_MIN} → chug (düşük frekans "
            "kararsızlık) riski. Enjektör basınç düşümünü artırın "
            "(NASA SP-8089).")

    feed_note = None
    if fluid_ox == 'n2o':
        if dp_pc_ox < CHUG_DP_PC_RECOMMENDED:
            feed_note = ("Kendinden basınçlı N₂O'da ΔP/Pc ≥ 0.20 önerilir; "
                         "iki-faz boğulmuş orifis akustik izolasyon sağlar "
                         "(NTRS 20190001326). Mevcut oran düşük: tank-besleme "
                         "kuplajı riski.")
            warnings_tr.append(feed_note)
        else:
            feed_note = ("N₂O orifisi doymuş girişte boğulur; boğulmuş akış "
                         "besleme sistemini odadan akustik olarak izole eder "
                         "(NTRS 20190001326).")

    stability = {
        'dp_pc_ratio_ox': float(dp_pc_ox),
        'dp_pc_ratio_fuel': (float(dp_pc_f) if dp_pc_f is not None else None),
        'chug_ok': bool(chug_ok),
        'chug_rule': 'dP/Pc >= 0.15-0.20 (NASA SP-8089)',
        'feed_coupling_warning_tr': feed_note,
        'acoustic_note_tr': ('Yüksek frekans (akustik) analiz kapsam dışı; '
                             'Pc > 50 bar ve F > 5 kN tasarımlarda baffle/'
                             'kavite literatürüne bakınız.'),
    }

    # İç kullanım alanını sözleşme dışı tutmak için temizle
    ox.pop('_rho', None)
    if fuel is not None:
        fuel.pop('_rho', None)

    return {
        'status': 'success',
        'motor_type': motor_type,
        'injector_type': inj_type,
        'ox_circuit': ox,
        'fuel_circuit': fuel,
        'pattern': {
            'description_tr': desc,
            'n_elements': int(n_elements),
            'impingement': impingement,
        },
        'atomization': {
            'smd_ox_um': float(smd_ox * 1e6),
            'smd_fuel_um': (float(smd_fuel_um) if smd_fuel_um is not None
                            else None),
            'correlation': correlation,
            'spray_cone_half_angle_deg': (float(spray_half)
                                          if spray_half is not None else None),
        },
        'momentum': momentum,
        'pintle_geometry': pintle_geometry,
        'swirl_geometry': swirl_geometry,
        'stability': stability,
        'warnings_tr': warnings_tr,
        'assumptions_tr': assumptions_tr,
        'references': REFERENCES,
    }
