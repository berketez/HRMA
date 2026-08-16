# hrma/stability/chamber.py — kamara zaman sabiti ve katı bulk (L*) modu
"""Kamara doldurma/boşaltma zaman sabiti τ_c ve gecikmesiz bulk mod ölçütü.

FİZİK VE KÜNYE
--------------
İzotermal, konsantre parametreli (lumped) kamara kütle dengesi:

    V/(R·T) · dP_c/dt = ṁ_üretim − P_c·A_t/c*
    ⟺ dP_c/dt + P_c/τ_c = (R·T/V)·ṁ_üretim

    τ_c ≡ L*/(c*·Γ²)      L* ≡ V/A_t      Γ² ≡ γ·(2/(γ+1))^((γ+1)/(γ−1))

Künye: Karabeyoglu, M.A., *AA284a Advanced Rocket Propulsion — Stability of
Chemical Propulsion Systems*, Stanford University ders notu, s. 5 (kamara gaz
dinamiği modeli; τ_c ve L* tanımları). Γ (Vandenkerckhove fonksiyonu) depoda
zaten aynı biçimde kullanılır: ``hrma/flow/quasi1d.py::choked_mass_flow``
(Γ/√R çarpanı) ve ``hrma/data/propellants_db.py`` (c* = √(R·T)/Γ, Sutton &
Biblarz 9. baskı Denk. 3-32). Bu modül aynı KAVRAMI ikinci bir sayı olarak
tanımlamaz; kapalı formu tek yerde (burada) yazar ve özdeşliği testle kilitler.

Özdeşlik (aynı Γ'nın iki yüzü):

    R·T = (c*·Γ)²   ⟺   c* = √(R·T)/Γ

Bu, τ_c'nin iki bağımsız yolunu birbirine bağlar:

    L*/(c*·Γ²)  ≡  V·c*/(A_t·R·T)

NEDEN MERKEZÎ BÜYÜKLÜK
----------------------
Chug (feed-coupled), katı L* bulk modu ve hibrit gaz dinamiği kutbu — üçü de
yukarıdaki TEK denklemin farklı kapanışlarıdır (tasarım belgesi §3.1).

KATI BULK (L*) MODU — GECİKMESİZ ÖZEL HÂL
------------------------------------------
Yarı-kararlı yanma hızı kuplajı (ṙ = a·P^n ⇒ δṁ/ṁ = n·δP/P) konursa:

    τ_c·d(δP)/dt + (1 − n)·δP = 0   ⇒   δP ∝ exp[(n − 1)·t/τ_c]

yani gecikmesiz limitte kararsızlık ölçütü **tam olarak n ≥ 1**'dir. HRMA katı
çözücüsündeki mevcut kritik uyarı (``solid_rocket_engine.py`` içindeki
``if self.n >= 1.0`` → ``warn.solid.burn_rate_exponent_ge_one``) bu özel hâlin
ta kendisidir; çapraz bekçi ``tests/test_stability_cekirdek.py`` içindedir.
Künye: Beckstead, M.W. & Price, E.W., "Nonacoustic Combustion Instability",
*AIAA Journal* 5(11), 1967 (L* modu); Karabeyoglu AA284a Ders 14, s. 5.

KAPSAM: katı fazdaki termal gecikme eklenince kararsızlık n < 1 için de
mümkündür (klasik L*/chuffing modu). O yol termal yayınırlık ister ve F2b'nin
kapılı işidir; burada verilen hüküm bu yüzden 'zero thermal lag' kapsamıyla
etiketlenir (çıplak hüküm yasağı, karar 1).
"""

import math

from hrma.stability import (
    STABILITY_NOT_MODELLED,
    VERDICT_STABLE,
    VERDICT_UNSTABLE,
    make_verdict,
)

__all__ = [
    'gamma_function',
    'gamma_function_sq',
    'chamber_time_constant',
    'tau_c_from_volume',
    'rt_from_cstar',
    'cstar_from_rt',
    'bulk_mode_zero_lag',
]

_TAU_C_BASIS = (
    'tau_c = L*/(c* * Gamma^2) with Gamma^2 = gamma*(2/(gamma+1))^'
    '((gamma+1)/(gamma-1)), from the isothermal lumped chamber mass balance '
    'V/(R*T) dP/dt = mdot_gen - P*A_t/c* (Karabeyoglu, AA284a Advanced Rocket '
    'Propulsion, Stanford lecture notes, chamber gas dynamic model, p. 5). '
    'Gamma is the Vandenkerckhove function already used by '
    'hrma.flow.quasi1d.choked_mass_flow and hrma.data.propellants_db '
    '(Sutton & Biblarz, RPE 9th ed., Eq. 3-32).')

_RT_IDENTITY_BASIS = (
    'R*T = (c* * Gamma)^2, the algebraic twin of c* = sqrt(R*T)/Gamma '
    '(Sutton & Biblarz, RPE 9th ed., Eq. 3-32). Same Gamma as tau_c, so the '
    'two independent routes to tau_c — L*/(c* Gamma^2) and V*c*/(A_t*R*T) — '
    'are identically equal.')


def _positive(name, value, upper=None):
    """Sonlu ve pozitif sayı kapısı (uydurma yedek yok: eksikse ValueError)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number (got {value!r}).")
    val = float(value)
    if not math.isfinite(val) or val <= 0.0:
        raise ValueError(f"{name} must be finite and > 0 (got {value!r}).")
    if upper is not None and val >= upper:
        raise ValueError(f"{name} must be < {upper:g} (got {value!r}).")
    return val


def _validate_gamma(gamma):
    """γ kapısı: (1, 2) — kalorik mükemmel gaz bandı (cfd/steady.py ile aynı)."""
    if isinstance(gamma, bool) or not isinstance(gamma, (int, float)):
        raise ValueError(f"gamma must be a finite number (got {gamma!r}).")
    g = float(gamma)
    if not math.isfinite(g) or not (1.0 < g < 2.0):
        raise ValueError(
            f"gamma must lie in (1, 2) for a caloric perfect gas "
            f"(got {gamma!r}).")
    return g


def gamma_function_sq(gamma):
    """Γ² = γ·(2/(γ+1))^((γ+1)/(γ−1)) — boyutsuz, (0, 1) aralığında.

    Γ² > 0 aşikâr; Γ² < 1 ise γ > 1 için kesindir (Lean adayı
    ``HRMA.gammaFunction_pos``, tasarım belgesi §7). Sayısal sonuç bu bandın
    dışına düşerse bu bir SAPMADIR ve sessiz kalmaz.
    """
    g = _validate_gamma(gamma)
    value = g * (2.0 / (g + 1.0)) ** ((g + 1.0) / (g - 1.0))
    if not (0.0 < value < 1.0):
        raise ValueError(
            f"Gamma^2 fell outside (0, 1) for gamma={g!r} (got {value!r}) — "
            f"this is a numerical anomaly, not a physical state.")
    return value


def gamma_function(gamma):
    """Γ = √γ·(2/(γ+1))^((γ+1)/(2(γ−1))) — Vandenkerckhove fonksiyonu."""
    return math.sqrt(gamma_function_sq(gamma))


def chamber_time_constant(l_star_m, c_star_m_s, gamma):
    """Kamara doldurma/boşaltma zaman sabiti τ_c [s] (beyanlı sözlük).

    Args:
        l_star_m: karakteristik kamara boyu L* = V/A_t [m].
        c_star_m_s: karakteristik hız c* [m/s].
        gamma: izantropik üs (1, 2).

    Returns:
        dict: ``tau_c_s``, ``l_star_m``, ``c_star_m_s``, ``gamma``,
        ``gamma_function_sq``, ``tau_c_basis``.
    """
    l_star = _positive('l_star_m', l_star_m)
    c_star = _positive('c_star_m_s', c_star_m_s)
    g2 = gamma_function_sq(gamma)
    return {
        'tau_c_s': l_star / (c_star * g2),
        'l_star_m': l_star,
        'c_star_m_s': c_star,
        'gamma': float(gamma),
        'gamma_function_sq': g2,
        'tau_c_basis': _TAU_C_BASIS,
    }


def tau_c_from_volume(chamber_volume_m3, throat_area_m2, c_star_m_s, gamma):
    """τ_c'nin ikinci (bağımsız) yolu: L* = V/A_t üzerinden.

    ``chamber_time_constant`` ile bit-özdeş olması gereken yol budur; özdeşlik
    bekçisi tests/test_stability_cekirdek.py içindedir.
    """
    volume = _positive('chamber_volume_m3', chamber_volume_m3)
    throat = _positive('throat_area_m2', throat_area_m2)
    result = chamber_time_constant(volume / throat, c_star_m_s, gamma)
    result['chamber_volume_m3'] = volume
    result['throat_area_m2'] = throat
    return result


def rt_from_cstar(c_star_m_s, gamma):
    """R·T = (c*·Γ)² [(m/s)² = J/kg] — özdeşlik yolu."""
    c_star = _positive('c_star_m_s', c_star_m_s)
    return (c_star * gamma_function(gamma)) ** 2


def cstar_from_rt(rt_m2_s2, gamma):
    """c* = √(R·T)/Γ [m/s] — ``rt_from_cstar``ın tersi."""
    rt = _positive('rt_m2_s2', rt_m2_s2)
    return math.sqrt(rt) / gamma_function(gamma)


def bulk_mode_zero_lag(burn_rate_exponent, tau_c_s=None):
    """Katı bulk (L*) modunun GECİKMESİZ limiti: kararsızlık ⟺ n ≥ 1.

    δP ∝ exp[(n − 1)·t/τ_c] olduğundan büyüme oranı (τ_c verilirse)
    ``(n − 1)/τ_c`` [1/s]'dir; n < 1'de negatif (sönen).

    Args:
        burn_rate_exponent: yanma hızı üsteli n (ṙ = a·P^n), boyutsuz ≥ 0.
        tau_c_s: kamara zaman sabiti [s]; verilirse büyüme oranı yayımlanır,
            verilmezse ``growth_rate_1_s`` None kalır (uydurma yok).

    Returns:
        dict: ölçüt + hüküm üçlüsü (kapsam etiketli) + beyanlar.
    """
    if (isinstance(burn_rate_exponent, bool)
            or not isinstance(burn_rate_exponent, (int, float))):
        raise ValueError(
            f"burn_rate_exponent must be a finite number "
            f"(got {burn_rate_exponent!r}).")
    n = float(burn_rate_exponent)
    if not math.isfinite(n) or n < 0.0:
        raise ValueError(
            f"burn_rate_exponent must be finite and >= 0 (got {n!r}).")

    tau_c = None if tau_c_s is None else _positive('tau_c_s', tau_c_s)
    unstable = n >= 1.0
    growth = None if tau_c is None else (n - 1.0) / tau_c

    verdict = make_verdict(
        VERDICT_UNSTABLE if unstable else VERDICT_STABLE,
        'solid bulk (L*) mode, zero thermal-lag limit — modeled mechanism '
        'only',
        (f'Zero-lag bulk mode criterion: burn rate exponent n = {n:.4g} '
         f'{">=" if unstable else "<"} 1, so the lumped chamber pole '
         f'(n-1)/tau_c is '
         f'{"non-negative (pressure runaway)" if unstable else "negative"}. '
         'This covers ONLY the zero thermal-lag limit: with a finite solid '
         'phase thermal lag, L*/chuffing instability is possible for n < 1 '
         'as well (that path needs propellant thermal diffusivity and is '
         'gated in F2b).'))

    return {
        'model': 'lumped_chamber_zero_lag_bulk_mode',
        'burn_rate_exponent': n,
        'criterion': 'n >= 1',
        'criterion_met': bool(unstable),
        'tau_c_s': tau_c,
        'growth_rate_1_s': growth,
        'thermal_lag': 'not_supplied',
        'criterion_basis': (
            'Substituting the quasi-steady burning rate law rdot = a*P^n '
            '(so dmdot/mdot = n*dP/P) into the lumped chamber balance gives '
            'tau_c d(dP)/dt + (1-n) dP = 0, hence growth if and only if '
            'n >= 1 (Beckstead & Price, "Nonacoustic Combustion '
            'Instability", AIAA Journal 5(11), 1967; Karabeyoglu, AA284a '
            'lecture notes, chamber gas dynamic model). This is exactly the '
            'criterion already gated in the HRMA solid solver '
            '(warn.solid.burn_rate_exponent_ge_one).'),
        **verdict,
        'not_modelled': {
            'thermal_lag': (
                'Solid-phase thermal lag is NOT modelled here: with it, '
                'L*/chuffing instability is possible at n < 1 (< 150 Hz '
                'band). Supplying propellant thermal diffusivity is an F2b '
                'gate; no default is fabricated.'),
            'nonlinear_behaviour':
                STABILITY_NOT_MODELLED['nonlinear_behaviour'],
        },
        'assumptions': [
            'lumped_chamber',        # tek noktada basınç (bulk mod)
            'isothermal',            # izotermal kamara gazı
            'quasi_steady_burning',  # yanma hızı anlık basınca uyar
            'zero_thermal_lag',      # katı fazda gecikme yok
        ],
    }
