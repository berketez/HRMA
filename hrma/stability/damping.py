# hrma/stability/damping.py — akustik sönüm bütçesi (F2a: lüle ayağı)
"""Mod başına akustik sönüm bütçesi; F2a'da lüle sönümü hesaplanır.

İŞARET SÖZLEŞMESİ
-----------------
``damping_1_s`` alanları BÜYÜME ORANI katkısıdır [1/s]: negatif değer sönüm,
pozitif değer sürükleme demektir (Culick & Yang'ın α tanımı). Toplam bütçe de
aynı işaretle taşınır; ``total_loss_1_s`` toplam kaybın BÜYÜKLÜĞÜDÜR.

LÜLE SÖNÜMÜ — KÜNYE VE SAYISAL DOĞRULAMA
-----------------------------------------
Culick, F.E.C. & Yang, V., "Prediction of the Stability of Unsteady Motions in
Solid-Propellant Rocket Motors", *Nonsteady Burning and Combustion Stability of
Solid Propellants* (AIAA Progress in Astronautics and Aeronautics, Vol. 143),
1990, ss. 719-779. Zincir:

    (100)  α_N = −(ā/(2·E_n²))·∬_lüle (A_N^(r) + M_N)·ψ_n² dS
    yarı-kararlı kısa lüle (s. 767):  A_N^(r) = (γ−1)·M_N/2 ,  A_N^(i) = 0
    düz tüp, ψ_n = cos(nπz/L), E_n² = S_N·L/2, ψ_n²(L) = 1
    ⇒  α_N = −(ā/L)·M_N·(γ + 1)/2                    (moddan BAĞIMSIZ)

Sayısal çapa (bu depoda ölçüldü): makalenin kendi örnek motorunun Ek verisiyle
(L = 0,5969 m, ā = 1075 m/s, γ̄ = 1,18, M_b = 0,00173, r_c = 0,0253 m ⇒
M_N = M_b·S_b/S_c = 0,08163) formül **−160,25 1/s** verir; makalenin Tablo 1'i
beş modun hepsi için **−160,1 1/s** yayımlar (%0,09 fark, Ek'teki yuvarlamalar
kadar). Modun numarasından bağımsız çıkması da tablonun kendi davranışıdır.

KAPSAM (F2a)
------------
Yalnız lüle terimi hesaplanır. Partikül sönümü (yoğuşmuş faz, Denk. 149a) katı
motorun iki-faz verisini ister ve F2b'nin işidir; viskoz/cidar ve yapısal
sönüm modellenmez. **Eksik kayıp terimleri kritik tepki eşiğini R_crit
KÖTÜMSER (düşük) yapar** — yani gerçek marj gösterilenden geniştir; bu yön
beyan alanında açıkça yazılır (tasarım belgesi §3.6).
"""

import math

from hrma.stability.chamber import _positive, _validate_gamma

__all__ = [
    'nozzle_damping_quasi_steady',
    'damping_budget',
    'DAMPING_NOT_MODELLED',
]

DAMPING_NOT_MODELLED = {
    'particle_damping': (
        'Particle (condensed phase) damping is NOT included in this core: it '
        'needs the solid motor two-phase data (condensed mass fraction and '
        'particle size) and is bound in F2b. Where it applies it is a LOSS, '
        'so leaving it out makes the critical response threshold pessimistic '
        '(too low).'),
    'viscous_wall_damping': (
        'Viscous / wall (acoustic boundary layer) damping is NOT modelled: '
        'the boundary layer is not solved. It is a loss term, so omitting it '
        'again biases the threshold pessimistically.'),
    'structural_damping': (
        'Structural / viscoelastic grain damping is NOT modelled: no '
        'viscoelastic grain model exists in this solver.'),
    'nozzle_unsteady_admittance': (
        'The nozzle admittance is taken in its QUASI-STEADY short-nozzle '
        'limit (imaginary part zero). Finite nozzle length and frequency '
        'dependence of the admittance are NOT modelled; at high frequency or '
        'with a long convergent section the real part can differ.'),
}

_NOZZLE_BASIS = (
    'Quasi-steady short-nozzle damping alpha_N = -(a/L)*M_N*(gamma+1)/2, '
    'from Culick & Yang, "Prediction of the Stability of Unsteady Motions in '
    'Solid-Propellant Rocket Motors", AIAA Progress in Astronautics and '
    'Aeronautics Vol. 143, 1990: Eq. (100) with the quasi-steady admittance '
    'A_N^(r) = (gamma-1)*M_N/2, A_N^(i) = 0 (p. 767), evaluated for a '
    'straight chamber with psi_n = cos(n*pi*z/L) and E_n^2 = S_N*L/2. It is '
    'independent of mode number. Cross-check against the paper\'s own worked '
    'example (Appendix data: L = 0.5969 m, a = 1075 m/s, gamma_mixture = '
    '1.18, M_N = 0.0816) reproduces its Table 1 value of -160.1 1/s to '
    'within 0.09%.')


def nozzle_damping_quasi_steady(sound_speed_m_s, chamber_length_m, gamma,
                                nozzle_entrance_mach):
    """Yarı-kararlı kısa lüle sönümü α_N [1/s] (negatif) — beyanlı sözlük.

    Args:
        sound_speed_m_s: kamara ses hızı ā [m/s] (gaz/partikül karışımıysa
            karışım değeri; γ de karışım değeri olmalıdır — çağıranın
            tutarlılığı, burada varsayılan yok).
        chamber_length_m: kamara boyu L [m].
        gamma: izantropik üs (karışım için γ̄).
        nozzle_entrance_mach: lüle girişindeki ortalama Mach M_N (< 1).

    Returns:
        dict: ``damping_1_s`` (negatif), ``admittance_real``, ``basis``.
    """
    a = _positive('sound_speed_m_s', sound_speed_m_s)
    length = _positive('chamber_length_m', chamber_length_m)
    g = _validate_gamma(gamma)
    mach = _positive('nozzle_entrance_mach', nozzle_entrance_mach, upper=1.0)

    admittance_real = (g - 1.0) * mach / 2.0
    alpha = -(a / length) * mach * (g + 1.0) / 2.0
    return {
        'term': 'nozzle',
        'damping_1_s': alpha,
        'admittance_real': admittance_real,
        'convective_term': mach,
        'mode_dependence': 'none (longitudinal modes, uniform chamber)',
        'basis': _NOZZLE_BASIS,
        'inputs': {
            'sound_speed_m_s': a,
            'chamber_length_m': length,
            'gamma': g,
            'nozzle_entrance_mach': mach,
            '_basis': "Echo of the caller's inputs (SI).",
        },
    }


def damping_budget(terms, extra_not_modelled=None):
    """Mod başına sönüm bütçesini toplar (beyanlı; uydurma terim eklemez).

    Args:
        terms: {ad: α [1/s]} sözlüğü ya da ``nozzle_damping_quasi_steady``
            biçimli sözlüklerin dizisi. Her α negatifse sönüm, pozitifse
            sürükleme sayılır; işaret çağıranındır.
        extra_not_modelled: bu koşuda ayrıca modellenmeyen terimlerin
            {ad: gerekçe} sözlüğü (opsiyonel).

    Returns:
        dict: ``terms``, ``total_damping_1_s`` (Σα), ``total_loss_1_s``
        (Σα < 0 ise |Σα|, aksi hâlde 0), ``not_modelled``, ``bias_basis``.
    """
    collected = {}
    if isinstance(terms, dict):
        items = terms.items()
    else:
        items = []
        for entry in terms or ():
            if not isinstance(entry, dict) or 'term' not in entry:
                raise ValueError(
                    'Each damping entry must be a dict with a "term" name and '
                    'a "damping_1_s" value (or pass a {name: value} mapping).')
            items.append((entry['term'], entry.get('damping_1_s')))
    for name, value in items:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f'Damping term name must be a string ({name!r}).')
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f'Damping term {name!r} must be a finite number [1/s] '
                f'(got {value!r}); a missing term is declared in '
                f'not_modelled, never defaulted to zero silently.')
        val = float(value)
        if not math.isfinite(val):
            raise ValueError(
                f'Damping term {name!r} must be finite (got {value!r}).')
        collected[name.strip()] = val

    if not collected:
        raise ValueError(
            'The damping budget is empty: supply at least one computed term '
            '(an empty budget would silently mean "no losses").')

    total = math.fsum(collected.values())
    not_modelled = dict(DAMPING_NOT_MODELLED)
    if extra_not_modelled:
        not_modelled.update(dict(extra_not_modelled))

    return {
        'terms': collected,
        'total_damping_1_s': total,
        'total_loss_1_s': -total if total < 0.0 else 0.0,
        'not_modelled': not_modelled,
        'sign_convention': (
            'damping_1_s is a growth-rate contribution [1/s]: negative = '
            'damping, positive = driving.'),
        'bias_basis': (
            'Loss terms that are NOT modelled bias the inverted critical '
            'response threshold R_crit LOW (pessimistic): with more losses '
            'accounted for, the combustion response needed to drive the mode '
            'would be HIGHER. The reported threshold is therefore a lower '
            'bound on what would be required, not a stability margin.'),
    }
