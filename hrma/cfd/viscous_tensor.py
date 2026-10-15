# hrma/cfd — eksenel simetrik Newton gerilme tensörü cebiri (Stokes hipotezli)
"""
Viskoz katmanın tensör cebiri (tasarım belgesi cfd-viskoz-tasarimi.md §5.3 —
BAĞLAYICI). SAF cebir: ızgara gerektirmez, durum güncellemez, Euler
çekirdeğine dokunmaz (kompozisyon ilkesi §5.1).

    Θ    = ∂u_z/∂z + ∂u_r/∂r + u_r/r                 (eksenel simetrik ıraksama)
    τ_zz = 2μ ∂u_z/∂z − (2/3)μ Θ
    τ_rr = 2μ ∂u_r/∂r − (2/3)μ Θ
    τ_zr = μ (∂u_z/∂r + ∂u_r/∂z)
    τ_θθ = 2μ (u_r/r) − (2/3)μ Θ

μ burada μ_eff'tir (laminer + türbülanslı); modül μ'yü ÜRETMEZ, çağırandan
alır — gaz taşınım özellikleri tek kaynaktan gelir (§5.8), burada yeni
sabit tanımlanmaz. Tek sabit, Stokes hipotezinin hacimsel viskozite
katsayısıdır (λ = −2/3 μ).

r → 0 TEKİLLİĞİ YOK: u_r/r hücre MERKEZİNDE değerlendirilir; ``AxisymGrid``
merkez yarıçapları daima pozitiftir (geometrik gerçek; eksen yüzlerinin
alanı sıfırdır ama merkez yarıçapı sıfır değildir). Seri açılım, epsilon,
kırpma YOKTUR: r ≤ 0 gelirse ``stress_from_gradients`` REDDEDER.

ÇEMBER (HOOP) KAYNAĞI: dönel hacim üstündeki kaynak integrali
∫(p − τ_θθ)/r dV = 2π∫(p − τ_θθ) dA_düzlem'dir; 1/r hacim elemanının
r'siyle TAM sadeleşir. euler_core r-momentumuna bugün +p·2π·A_düzlem
ekliyor; viskoz karşılığı aynı çarpanla ters işaretlidir (bekçi:
tests/cfd/test_viskoz_tensor.py, çekirdek satırını KODDAN okur).

DOSYA ADI NOTU: tasarım belgesi §11.1 ``viscous.py`` dosyasını viskoz
AKI + duvar τ_w/q_w için ayırır (V1). Bu dosya yalnız V0'ın tensör
cebiridir; V1'in ``viscous.py``'si buradan içe aktarır, kopyalamaz.
"""

from typing import NamedTuple

import numpy as np

__all__ = [
    'STOKES_BULK_COEFF',
    'StressAxisym',
    'axisym_divergence',
    'hoop_momentum_source',
    'stress_axisym',
    'stress_from_gradients',
    'stress_trace',
    'thin_layer_stress_difference',
]

#: Stokes hipotezi: λ = −(2/3)μ → normal gerilmelerden düşen pay (2/3)μΘ.
#: tr(τ) = 2μΘ − 3·(2/3)μΘ = 0 özdeşliği bu katsayıya kilitlidir.
STOKES_BULK_COEFF = 2.0 / 3.0

_TWO_PI = 2.0 * np.pi


class StressAxisym(NamedTuple):
    """Eksenel simetrik Newton gerilmesi bileşenleri (hepsi [Pa])."""
    tau_zz: np.ndarray
    tau_rr: np.ndarray
    tau_zr: np.ndarray
    tau_theta: np.ndarray
    theta: np.ndarray          # ıraksama Θ [1/s] (τ değil, beyan için)


def axisym_divergence(duz_dz, dur_dr, ur_over_r):
    """Θ = ∂u_z/∂z + ∂u_r/∂r + u_r/r — çember terimi DAHİL."""
    return duz_dz + dur_dr + ur_over_r


def stress_axisym(duz_dz, duz_dr, dur_dz, dur_dr, ur_over_r, mu):
    """Gerilme bileşenleri; girdiler dizi ya da skaler olabilir (elementer).

    Args:
        duz_dz, duz_dr: ∂u_z/∂z, ∂u_z/∂r [1/s]
        dur_dz, dur_dr: ∂u_r/∂z, ∂u_r/∂r [1/s]
        ur_over_r: u_r/r [1/s] — hücre merkezinde değerlendirilmiş
        mu: μ_eff [Pa·s] (laminer + türbülanslı; çağıran verir)

    Returns:
        StressAxisym.
    """
    theta = axisym_divergence(duz_dz, dur_dr, ur_over_r)
    kuresel = STOKES_BULK_COEFF * mu * theta
    return StressAxisym(
        tau_zz=2.0 * mu * duz_dz - kuresel,
        tau_rr=2.0 * mu * dur_dr - kuresel,
        tau_zr=mu * (duz_dr + dur_dz),
        tau_theta=2.0 * mu * ur_over_r - kuresel,
        theta=theta)


def stress_from_gradients(grad_uz, grad_ur, ur, r, mu):
    """Gradyan dizilerinden gerilme (gradients.py çıktısıyla doğrudan uyumlu).

    Args:
        grad_uz, grad_ur: (..., 2) gradyanlar; [..., 0] = ∂/∂z, [..., 1] = ∂/∂r
            (hrma.cfd.gradients bileşen sırası).
        ur: (...) radyal hız [m/s].
        r: (...) değerlendirme yarıçapı [m] — POZİTİF olmalı.
        mu: (...) veya skaler μ_eff [Pa·s].

    Raises:
        ValueError: r ≤ 0 ya da biçimler tutmuyorsa (kırpma/epsilon YOK).
    """
    grad_uz = np.asarray(grad_uz, dtype=float)
    grad_ur = np.asarray(grad_ur, dtype=float)
    if grad_uz.shape[-1] != 2 or grad_ur.shape[-1] != 2:
        raise ValueError('grad_uz/grad_ur son ekseni 2 olmalı (∂/∂z, ∂/∂r).')
    if grad_uz.shape != grad_ur.shape:
        raise ValueError('grad_uz ve grad_ur aynı biçimde olmalı.')
    ur = np.asarray(ur, dtype=float)
    r = np.asarray(r, dtype=float)
    if ur.shape != grad_uz.shape[:-1] or r.shape != grad_uz.shape[:-1]:
        raise ValueError('ur ve r biçimi gradyanların hücre biçimiyle aynı '
                         'olmalı.')
    if np.any(r <= 0.0):
        raise ValueError(
            'r ≤ 0 bulundu: u_r/r hücre MERKEZİNDE değerlendirilir ve '
            'merkez yarıçapı pozitiftir (grid_axisym geometrik gerçeği). '
            'Epsilon/kırpma uygulanmaz — çağıran yanlış yarıçap veriyor.')
    return stress_axisym(grad_uz[..., 0], grad_uz[..., 1],
                         grad_ur[..., 0], grad_ur[..., 1], ur / r, mu)


def stress_trace(stress):
    """tr(τ) = τ_zz + τ_rr + τ_θθ — Stokes hipotezinde ÖZDEŞ olarak sıfır."""
    return stress.tau_zz + stress.tau_rr + stress.tau_theta


def hoop_momentum_source(tau_theta, grid):
    """r-momentumu çember kaynağı: −τ_θθ · 2π · A_düzlem [N].

    euler_core'un basınç kaynağının (+p·2π·A_düzlem) TAM kardeşi; işaret
    ters, çarpan aynı. Hücre başına net kuvvet katkısıdır (kalıntıya
    doğrudan eklenir — V1).
    """
    tau_theta = np.asarray(tau_theta, dtype=float)
    if tau_theta.shape != grid.area_planar.shape:
        raise ValueError(
            f'tau_theta biçimi {grid.area_planar.shape} olmalı, '
            f'gelen {tau_theta.shape}.')
    return -tau_theta * _TWO_PI * grid.area_planar


def thin_layer_stress_difference(duz_dz, duz_dr, dur_dz, dur_dr, ur_over_r,
                                 mu):
    """ÖLÇÜM ARACI: tam gradyan ↔ ince tabaka (thin-layer) biçimi farkı.

    İnce tabaka yaklaşımı EKSENEL türevleri (∂u_z/∂z, ∂u_r/∂z) atar. Bu
    modül o yaklaşımı UYGULAMAZ (tasarım belgesi §5.2: "uygulanmayacak ama
    BEKÇİ olarak hesaplanacak"); burada yalnız ihmal edilenin büyüklüğü
    ÖLÇÜLÜR ve beyan edilir — varsayılmaz.

    Returns:
        dict: bileşen başına maksimum mutlak fark [Pa], tam biçimin
        ölçeğine göre maksimum bağıl fark, atılan terimlerin adları ve
        kaynak künyesi. (Kapalı form: Δτ_zz = (4/3)μ ∂u_z/∂z,
        Δτ_rr = Δτ_θθ = −(2/3)μ ∂u_z/∂z, Δτ_zr = μ ∂u_r/∂z, ΔΘ = ∂u_z/∂z.)
    """
    tam = stress_axisym(duz_dz, duz_dr, dur_dz, dur_dr, ur_over_r, mu)
    sifir = np.zeros_like(np.asarray(duz_dz, dtype=float))
    ince = stress_axisym(sifir, duz_dr, sifir, dur_dr, ur_over_r, mu)

    bilesenler = ('tau_zz', 'tau_rr', 'tau_zr', 'tau_theta')
    mutlak = {}
    for ad in bilesenler:
        mutlak[ad] = float(np.max(np.abs(
            np.asarray(getattr(tam, ad)) - np.asarray(getattr(ince, ad)))))
    olcek = max(float(np.max(np.abs(np.asarray(getattr(tam, ad)))))
                for ad in bilesenler)
    return {
        '_source': 'hrma.cfd.viscous_tensor.thin_layer_stress_difference',
        'note': ('İnce tabaka biçimi UYGULANMAZ; bu yalnız ihmal edilen '
                 'eksenel viskoz türevlerin büyüklüğünü ölçer.'),
        'dropped_terms': ('duz_dz', 'dur_dz'),
        'max_abs_diff': mutlak,
        'max_rel_diff': (max(mutlak.values()) / olcek if olcek > 0.0 else 0.0),
        'full_form_scale_Pa': olcek,
        'theta_max_abs_diff': float(np.max(np.abs(
            np.asarray(tam.theta) - np.asarray(ince.theta)))),
    }
