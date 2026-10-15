# tests/cfd — eksenel simetrik Newton gerilme tensörü cebiri bekçileri
"""
Doğrulama merdiveni (docs/mimari/cfd-viskoz-tasarimi.md §7) BASAMAK 1:
tr(τ) = 0 özdeşliği — IZGARASIZ, cebirsel, rastgele-tohumlu durumlarda.

Neden bu bekçi keskin (§5.3): Stokes hipotezli (λ = −2/3 μ) Newton
gerilmesinin izi τ_zz + τ_rr + τ_θθ = 2μΘ − 3·(2/3)μΘ = 0'dır. Bu özdeşlik
eksenel simetrinin İKİ klasik hatasını birden yakalar:
  (a) çember (hoop) bileşeni τ_θθ = 2μ·u_r/r − (2/3)μΘ'yi unutmak,
  (b) ıraksamaya u_r/r terimini katmamak (Θ = ∂u_z/∂z + ∂u_r/∂r + u_r/r).
İkisi de burada pozitif kontrolle (kasıtlı bozuk değerle) ölçülür.

r → 0 tekilliği YOK: u_r/r hücre MERKEZİNDE değerlendirilir ve gerçek
ızgarada r_merkez daima pozitiftir (ölçülür, aşağıda). Seri açılım,
epsilon ya da kırpma yoktur; r ≤ 0 gelirse modül REDDEDER.
"""

import inspect
import re

import numpy as np
import pytest

from hrma.cfd import euler_core
from hrma.cfd import viscous_tensor as viskoz_mod
from hrma.cfd.gradients import green_gauss_gradient
from hrma.cfd.grid_axisym import build_grid_from_wall, build_nozzle_grid
from hrma.cfd.viscous_tensor import (
    STOKES_BULK_COEFF,
    hoop_momentum_source,
    stress_axisym,
    stress_from_gradients,
    stress_trace,
    thin_layer_stress_difference,
)
from hrma.engines.nozzle_design import sample_nozzle_inner_contour

from .conftest import LULE_L_CONV, LULE_L_DIV, lule_duvar_yaricapi

TWO_PI = 2.0 * np.pi


def _lule_grid(ni=60, nj=12):
    z = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, ni + 1)
    return build_grid_from_wall(z, lule_duvar_yaricapi(z), nj)


def _rastgele_durum(n=4096, tohum=20260818):
    """Izgarasız rastgele gradyan/viskozite durumu (ölçek roket sınıfı)."""
    rng = np.random.default_rng(tohum)
    duz_dz = rng.normal(0.0, 5.0e4, n)      # [1/s] — 300 m/s / 6 mm sınıfı
    duz_dr = rng.normal(0.0, 5.0e5, n)
    dur_dz = rng.normal(0.0, 5.0e4, n)
    dur_dr = rng.normal(0.0, 5.0e4, n)
    ur_over_r = rng.normal(0.0, 5.0e4, n)
    mu = rng.uniform(1.0e-5, 2.0e-4, n)     # [Pa·s] sıcak gaz + türbülans
    return duz_dz, duz_dr, dur_dz, dur_dr, ur_over_r, mu


# --------------------------------------------------------------------------
# BASAMAK 1 — tr(τ) = 0
# --------------------------------------------------------------------------

def test_iz_sifir_rastgele_tohumlu():
    """tr(τ) = τ_zz + τ_rr + τ_θθ = 0 (hoop dahil), makine sıfırı sınıfında.

    Ölçüt YUVARLAMA TABANINA göre kurulur: iz, üç normal bileşenin
    toplamıdır ve her bileşen 2μ·(türev) ile küresel payın farkıdır; bu
    yüzden erişilebilir en küçük artık eps·(2μΣ|türev| + 3|küresel pay|)
    mertebesindedir. ÖLÇÜLDÜ (4096 rastgele durum, tohum 20260818):
    maks |iz| = 2,49e-14 Pa, yuvarlama tabanının 0,90 katı, bileşen
    ölçeğine göre 2,06e-14.
    """
    duz_dz, duz_dr, dur_dz, dur_dr, ur_over_r, mu = _rastgele_durum()
    st = stress_axisym(duz_dz, duz_dr, dur_dz, dur_dr, ur_over_r, mu)
    iz = stress_trace(st)
    kuresel = STOKES_BULK_COEFF * mu * st.theta
    taban = (2.0 * mu * (np.abs(duz_dz) + np.abs(dur_dr) + np.abs(ur_over_r))
             + 3.0 * np.abs(kuresel))
    ulp_kati = float(np.max(np.abs(iz) / taban)) / np.finfo(float).eps
    assert ulp_kati < 4.0, (
        f'Stokes izi yuvarlama tabanının {ulp_kati:.2f} katı: τ_θθ ya da '
        f'eksenel simetrik ıraksama (u_r/r terimi) hatalı')
    olcek = np.maximum.reduce([np.abs(st.tau_zz), np.abs(st.tau_rr),
                               np.abs(st.tau_theta)])
    assert float(np.max(np.abs(iz) / olcek)) < 1e-13


def test_iz_hoop_isaret_hatasini_yakalar():
    """POZİTİF KONTROL: τ_θθ işareti ters çevrilirse iz bekçisi kırmızıya döner.

    Bu, bekçinin gerçekten ısırdığının kanıtıdır (kaynakta mutasyon
    yapmadan, aynı cebir üstünde ölçülür): iz = 2·τ_θθ olur.
    """
    durum = _rastgele_durum(n=512)
    st = stress_axisym(*durum)
    iz_bozuk = st.tau_zz + st.tau_rr - st.tau_theta
    olcek = np.maximum(np.abs(st.tau_theta), 1e-300)
    bagil = float(np.min(np.abs(iz_bozuk) / olcek))
    assert bagil > 1.0, (
        f'hoop işareti ters çevrildiğinde iz hâlâ küçük ({bagil:.3e}) — '
        f'bekçi hoop terimine kör')
    # τ_zz + τ_rr = −τ_θθ olduğundan işaret hatası izi tam −2τ_θθ yapar
    assert np.allclose(iz_bozuk, -2.0 * st.tau_theta, rtol=1e-13, atol=0.0)


def test_iz_stokes_katsayisi_kilidi():
    """POZİTİF KONTROL: hacimsel viskozite katsayısı 2/3 değilse iz sıfır olmaz."""
    assert STOKES_BULK_COEFF == 2.0 / 3.0
    duz_dz, duz_dr, dur_dz, dur_dr, ur_over_r, mu = _rastgele_durum(n=512)
    theta = duz_dz + dur_dr + ur_over_r
    yanlis = 1.0 / 3.0
    iz_bozuk = (2.0 * mu * (duz_dz + dur_dr + ur_over_r)
                - 3.0 * yanlis * mu * theta)
    olcek = np.abs(2.0 * mu * theta)
    assert float(np.min(np.abs(iz_bozuk) / olcek)) > 0.4, (
        'yanlış hacimsel viskozite katsayısı izi bozmuyor — bekçi kör'
    )


def test_iraksama_u_r_bolu_r_terimini_icerir():
    """Θ eksenel simetrik ıraksamadır: u_r/r katkısı ölçülebilir olmalı."""
    st = stress_axisym(0.0, 0.0, 0.0, 0.0, 7.5e4, 3.0e-5)
    assert st.theta == pytest.approx(7.5e4, rel=1e-15)
    # yalnız hoop kaynaklı ıraksamada τ_zz = τ_rr = −(2/3)μΘ, τ_θθ = (4/3)μΘ
    assert st.tau_zz == pytest.approx(-(2.0 / 3.0) * 3.0e-5 * 7.5e4, rel=1e-14)
    assert st.tau_theta == pytest.approx((4.0 / 3.0) * 3.0e-5 * 7.5e4,
                                         rel=1e-14)
    # birkaç ulp payı: iz üç bileşenin toplamıdır (ÖLÇÜLDÜ: 1,5 ulp)
    assert abs(stress_trace(st)) < 8.0 * np.finfo(float).eps * abs(st.tau_theta)


# --------------------------------------------------------------------------
# ANALİTİK VAKALAR
# --------------------------------------------------------------------------

def test_saf_eksenel_kayma_normal_gerilmeleri_sifir():
    """Hagen-Poiseuille profili (merdiven basamak 4'ün cebirsel ön adımı):
    u_z = u_max(1 − r²/R²), u_r = 0 → Θ = 0, yalnız τ_zr yaşar."""
    R = 0.025
    u_max = 120.0
    mu = 8.5e-5
    r = np.linspace(1.0e-4, R, 64)
    duz_dr = -2.0 * u_max * r / (R * R)
    st = stress_axisym(np.zeros_like(r), duz_dr, np.zeros_like(r),
                       np.zeros_like(r), np.zeros_like(r), mu)
    assert np.array_equal(st.theta, np.zeros_like(r))
    for bilesen in (st.tau_zz, st.tau_rr, st.tau_theta):
        assert np.array_equal(bilesen, np.zeros_like(r)), (
            'saf kaymada normal gerilme doğdu — ıraksama terimi sızıyor')
    assert np.allclose(st.tau_zr, mu * duz_dr, rtol=0.0, atol=0.0)


def test_radyal_genisleme_analitik():
    """u_r = a·r, u_z = 0 → Θ = 2a; τ_rr = τ_θθ = (2/3)μa, τ_zz = −(4/3)μa."""
    a = 4.2e3
    mu = 1.1e-4
    st = stress_axisym(0.0, 0.0, 0.0, a, a, mu)
    assert st.theta == pytest.approx(2.0 * a, rel=1e-15)
    assert st.tau_rr == pytest.approx((2.0 / 3.0) * mu * a, rel=1e-13)
    assert st.tau_theta == pytest.approx((2.0 / 3.0) * mu * a, rel=1e-13)
    assert st.tau_zz == pytest.approx(-(4.0 / 3.0) * mu * a, rel=1e-13)
    assert st.tau_zr == 0.0


def test_eksende_r_sifir_reddedilir_ve_gercek_izgarada_pozitif():
    """u_r/r hücre merkezinde; r ≤ 0 REDDEDİLİR (epsilon/kırpma yok).

    Gerçek ızgaralarda r_merkez pozitiftir — ölçülür ve raporlanır.
    """
    grid = _lule_grid(120, 24)
    assert float(np.min(grid.r_centers)) > 0.0
    points, _meta = sample_nozzle_inner_contour({})
    motor = build_nozzle_grid(points, ni=48, nj=10)
    assert float(np.min(motor.r_centers)) > 0.0

    grad_uz = np.zeros((2, 2, 2))
    grad_ur = np.zeros((2, 2, 2))
    ur = np.ones((2, 2))
    r_bozuk = np.array([[1.0, 1.0], [0.0, 1.0]])
    with pytest.raises(ValueError, match='r'):
        stress_from_gradients(grad_uz, grad_ur, ur, r_bozuk, 1e-5)

    kaynak = inspect.getsource(viskoz_mod)
    assert not re.search(r'np\.(clip|maximum)\s*\(\s*r', kaynak), (
        'r üstünde kırpma/epsilon bulundu — grid_axisym geometrik gerçek '
        'felsefesi ihlal edilmiş')


# --------------------------------------------------------------------------
# ÇEMBER (HOOP) KAYNAK TERİMİ — basınç kaynağının kardeşi
# --------------------------------------------------------------------------

def test_hoop_kaynagi_basinc_teriminin_kardesi():
    """−τ_θθ·2π·A_düzlem biçimi euler_core'un basınç kaynağıyla AYNI kalıpta.

    KOD KANITI: euler_core bugün r-momentumuna +p·2π·A_düzlem ekliyor.
    Viskoz karşılık aynı geometrik çarpanla ve TERS işaretle gelir
    (∫(p − τ_θθ)/r dV = 2π∫(p − τ_θθ) dA_düzlem). Çekirdek satırı değişirse
    bu bekçi kırmızıya döner ve kardeşlik iddiası yeniden ölçülür.
    """
    kaynak = inspect.getsource(euler_core)
    assert re.search(
        r'net\[\.\.\.,\s*2\]\s*\+=\s*w\[\.\.\.,\s*3\]\s*\*\s*_TWO_PI\s*\*\s*'
        r'grid\.area_planar', kaynak), (
        'euler_core basınç kaynak satırı bulunamadı — hoop teriminin '
        'işaret/çarpan kardeşliği artık koda dayanmıyor')

    grid = _lule_grid(20, 6)
    tau_theta = np.linspace(-1.0e3, 2.0e3, grid.ni * grid.nj).reshape(
        grid.ni, grid.nj)
    kaynak_terimi = hoop_momentum_source(tau_theta, grid)
    beklenen = -tau_theta * TWO_PI * grid.area_planar
    assert np.array_equal(kaynak_terimi, beklenen)
    # işaret: pozitif τ_θθ r-momentumunu AZALTIR (basınç tam tersi)
    assert float(np.max(kaynak_terimi[tau_theta > 0.0])) < 0.0


# --------------------------------------------------------------------------
# İNCE TABAKA (thin-layer) KARŞILAŞTIRMA YARDIMCISI — ölçüm aracı
# --------------------------------------------------------------------------

def test_ince_tabaka_farki_cebirsel_olarak_dogru():
    """Atılan eksenel türevlerin gerilmeye etkisi KAPALI FORMLA doğrulanır.

    τ_zz farkı = (4/3)μ ∂u_z/∂z, τ_rr = τ_θθ farkı = −(2/3)μ ∂u_z/∂z,
    τ_zr farkı = μ ∂u_r/∂z. Yardımcı bir uygulama DEĞİL, ölçüm aracıdır.
    """
    duz_dz, duz_dr, dur_dz, dur_dr, ur_over_r, mu = _rastgele_durum(n=1024)
    olcum = thin_layer_stress_difference(duz_dz, duz_dr, dur_dz, dur_dr,
                                         ur_over_r, mu)
    assert olcum['dropped_terms'] == ('duz_dz', 'dur_dz')
    assert olcum['_source'].endswith('thin_layer_stress_difference')
    assert olcum['max_abs_diff']['tau_zz'] == pytest.approx(
        float(np.max(np.abs((4.0 / 3.0) * mu * duz_dz))), rel=1e-13)
    assert olcum['max_abs_diff']['tau_rr'] == pytest.approx(
        float(np.max(np.abs((2.0 / 3.0) * mu * duz_dz))), rel=1e-13)
    assert olcum['max_abs_diff']['tau_zr'] == pytest.approx(
        float(np.max(np.abs(mu * dur_dz))), rel=1e-13)
    assert olcum['max_rel_diff'] > 0.0
    assert all(np.isfinite(v) for v in olcum['max_abs_diff'].values())


def test_ince_tabaka_farki_eksenel_turevsiz_alanda_tam_sifir():
    """∂/∂z ≡ 0 olan alanda ince tabaka biçimi tam gradyanla ÖZDEŞTİR."""
    n = 256
    rng = np.random.default_rng(7)
    olcum = thin_layer_stress_difference(
        np.zeros(n), rng.normal(0, 5e5, n), np.zeros(n),
        rng.normal(0, 5e4, n), rng.normal(0, 5e4, n), 6.0e-5)
    assert olcum['max_rel_diff'] == 0.0
    assert all(v == 0.0 for v in olcum['max_abs_diff'].values())


# --------------------------------------------------------------------------
# KÖPRÜ — gradyan operatörü + tensör cebiri birlikte
# --------------------------------------------------------------------------

def test_gercek_izgarada_gradyandan_gerilme_izi_sifir():
    """Gerçek ızgara + gerçek gradyan operatörüyle kurulan τ'nun izi sıfır.

    Basamak 1 (cebir) ile basamak 3'ü (gradyan) tek bekçide birleştirir:
    hız alanı analitik verilir, gradyanlar OPERATÖRDEN gelir, gerilme
    tensörü onlardan kurulur.
    """
    grid = _lule_grid(80, 16)
    z, r = grid.z_centers, grid.r_centers
    uz = 250.0 + 400.0 * z - 1.2e3 * r * r
    ur = 12.0 * r * (1.0 + 2.0 * z)
    grad_uz = green_gauss_gradient(grid, uz)
    grad_ur = green_gauss_gradient(grid, ur)
    mu = 8.0e-5 * np.ones_like(uz)
    st = stress_from_gradients(grad_uz, grad_ur, ur, r, mu)
    iz = stress_trace(st)
    olcek = np.maximum.reduce([np.abs(st.tau_zz), np.abs(st.tau_rr),
                               np.abs(st.tau_theta)])
    assert float(np.max(np.abs(iz) / olcek)) < 1e-14
