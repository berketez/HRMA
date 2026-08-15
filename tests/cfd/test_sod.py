# tests/cfd — Sod şok tüpü bekçisi (doğrulama merdiveni basamak 1)
"""
1B Euler çekirdeği (HLLC + MUSCL/minmod) Sod şok tüpünde ANALİTİK Riemann
çözümüne karşı sınanır.

Analitik referans bu dosyanın İÇİNDE kurulur (literatürden sayı kopyalanmaz):
star bölgesi basıncı Toro, "Riemann Solvers and Numerical Methods for Fluid
Dynamics", 3. baskı, §4.2-4.3'teki basınç fonksiyonunun köküyle (brentq),
örnekleme §4.5'teki dalga deseni ağacıyla yapılır. Kapalı formüller:

  şok kolu (p > pK):      f_K = (p-pK)·sqrt(A_K/(p+B_K)),
                          A_K = 2/((γ+1)ρ_K), B_K = pK(γ-1)/(γ+1)   (Eş. 4.21)
  genleşme kolu (p ≤ pK): f_K = 2a_K/(γ-1)·[(p/pK)^((γ-1)/2γ) − 1]  (Eş. 4.26)
  u* = (u_L+u_R)/2 + (f_R−f_L)/2                                    (Eş. 4.9)

Bekçiler:
  (a) 100 hücrede L1(ρ) hatası eşik altında (eşik ÖLÇÜMDEN konuldu, aşağıda
      ölçüm değeri yorumda),
  (b) 100→400 hücrede L1(ρ) yakınsama mertebesi > 0,8 (görev sözleşmesi;
      minmod sökülüp birinci mertebeye düşülürse KIRMIZI olmalı),
  (c) toplam kütle korunumu (dalgalar sınırlara varmadan) makine hassasiyeti.
"""

import numpy as np
import pytest
from scipy.optimize import brentq

from hrma.cfd.euler_core import prim_to_cons_1d, run_1d_transient

GAMMA_SOD = 1.4  # Sod vakasının kanonik gazı (hava); lüle testlerindeki 1,2'den BİLİNÇLİ farklı
T_END = 0.2
X_LEFT, X_RIGHT, X_DIAPHRAGM = 0.0, 1.0, 0.5
RHO_L, U_L, P_L = 1.0, 0.0, 1.0
RHO_R, U_R, P_R = 0.125, 0.0, 0.1

# ÖLÇÜLDÜ (bu depo, M4 Max, 2026-08-15): N=100 → L1(ρ)=0,008252;
# N=400 → L1(ρ)=0,002498; mertebe = 0,862. Eşik = ölçüm × ~1,15 payı.
# (minmod TVD sınırlayıcıların en yayıcısıdır; Sod'da 100 hücrede ~0,008
# sınıfı L1 bu şema için beklenen banttır — Toro §13-14 şema kıyasları.)
L1_LIMIT_100 = 0.0095
ORDER_MIN = 0.8          # görev sözleşmesi (sabit, ölçümden bağımsız)


# --------------------------------------------------------------------------
# Analitik Riemann çözümü (Toro §4.2-4.5, testin içinde kurulur)
# --------------------------------------------------------------------------

def _pressure_fn(p, rho_k, p_k, gamma):
    """Tek taraf basınç fonksiyonu f_K(p) (Toro Eş. 4.21 / 4.26)."""
    a_k = np.sqrt(gamma * p_k / rho_k)
    if p > p_k:  # şok kolu
        A = 2.0 / ((gamma + 1.0) * rho_k)
        B = p_k * (gamma - 1.0) / (gamma + 1.0)
        return (p - p_k) * np.sqrt(A / (p + B))
    # genleşme (izantropik) kolu
    return (2.0 * a_k / (gamma - 1.0)) * (
        (p / p_k) ** ((gamma - 1.0) / (2.0 * gamma)) - 1.0)


def _solve_star(gamma):
    """(p*, u*) — basınç fonksiyonu kökü brentq ile (Toro Eş. 4.5, 4.9)."""

    def total(p):
        return (_pressure_fn(p, RHO_L, P_L, gamma)
                + _pressure_fn(p, RHO_R, P_R, gamma) + (U_R - U_L))

    p_star = brentq(total, 1e-10, 10.0 * max(P_L, P_R), xtol=1e-14,
                    rtol=8.9e-16, maxiter=200)
    u_star = 0.5 * (U_L + U_R) + 0.5 * (
        _pressure_fn(p_star, RHO_R, P_R, gamma)
        - _pressure_fn(p_star, RHO_L, P_L, gamma))
    return p_star, u_star


def _sample_exact(xi, gamma):
    """Benzerlik değişkeni xi = (x-x0)/t için (ρ, u, p) — Toro §4.5 ağacı.

    Sod deseninde sol dalga genleşme, sağ dalga şoktur; ama ağaç genel
    yazılmıştır (p* ile pK karşılaştırmasından dal seçilir, desen
    varsayılmaz).
    """
    p_star, u_star = _solve_star(gamma)
    g = gamma
    if xi <= u_star:  # temas yüzeyinin solu
        rho_k, u_k, p_k = RHO_L, U_L, P_L
        a_k = np.sqrt(g * p_k / rho_k)
        if p_star > p_k:  # sol şok
            s_l = u_k - a_k * np.sqrt((g + 1.0) / (2.0 * g) * p_star / p_k
                                      + (g - 1.0) / (2.0 * g))
            if xi <= s_l:
                return rho_k, u_k, p_k
            gr = (g - 1.0) / (g + 1.0)
            rho = rho_k * ((p_star / p_k + gr) / (gr * p_star / p_k + 1.0))
            return rho, u_star, p_star
        # sol genleşme fanı
        a_star = a_k * (p_star / p_k) ** ((g - 1.0) / (2.0 * g))
        head, tail = u_k - a_k, u_star - a_star
        if xi <= head:
            return rho_k, u_k, p_k
        if xi >= tail:
            rho = rho_k * (p_star / p_k) ** (1.0 / g)
            return rho, u_star, p_star
        u = 2.0 / (g + 1.0) * (a_k + 0.5 * (g - 1.0) * u_k + xi)
        a = 2.0 / (g + 1.0) * (a_k + 0.5 * (g - 1.0) * (u_k - xi))
        rho = rho_k * (a / a_k) ** (2.0 / (g - 1.0))
        p = p_k * (a / a_k) ** (2.0 * g / (g - 1.0))
        return rho, u, p
    # temas yüzeyinin sağı
    rho_k, u_k, p_k = RHO_R, U_R, P_R
    a_k = np.sqrt(g * p_k / rho_k)
    if p_star > p_k:  # sağ şok
        s_r = u_k + a_k * np.sqrt((g + 1.0) / (2.0 * g) * p_star / p_k
                                  + (g - 1.0) / (2.0 * g))
        if xi >= s_r:
            return rho_k, u_k, p_k
        gr = (g - 1.0) / (g + 1.0)
        rho = rho_k * ((p_star / p_k + gr) / (gr * p_star / p_k + 1.0))
        return rho, u_star, p_star
    # sağ genleşme fanı
    a_star = a_k * (p_star / p_k) ** ((g - 1.0) / (2.0 * g))
    head, tail = u_k + a_k, u_star + a_star
    if xi >= head:
        return rho_k, u_k, p_k
    if xi <= tail:
        rho = rho_k * (p_star / p_k) ** (1.0 / g)
        return rho, u_star, p_star
    u = 2.0 / (g + 1.0) * (-a_k + 0.5 * (g - 1.0) * u_k + xi)
    a = 2.0 / (g + 1.0) * (a_k - 0.5 * (g - 1.0) * (u_k - xi))
    rho = rho_k * (a / a_k) ** (2.0 / (g - 1.0))
    p = p_k * (a / a_k) ** (2.0 * g / (g - 1.0))
    return rho, u, p


def _exact_density(x_centers, gamma, t):
    return np.array([_sample_exact((x - X_DIAPHRAGM) / t, gamma)[0]
                     for x in x_centers])


# --------------------------------------------------------------------------
# Sayısal koşum yardımcıları
# --------------------------------------------------------------------------

def _run_sod(n_cells, second_order=True):
    dx = (X_RIGHT - X_LEFT) / n_cells
    x_c = X_LEFT + (np.arange(n_cells) + 0.5) * dx
    left = x_c < X_DIAPHRAGM
    rho = np.where(left, RHO_L, RHO_R)
    u = np.where(left, U_L, U_R)
    p = np.where(left, P_L, P_R)
    U0 = prim_to_cons_1d(rho, u, p, GAMMA_SOD)
    U = run_1d_transient(U0, dx, GAMMA_SOD, T_END, cfl=0.8,
                         second_order=second_order)
    return x_c, dx, U0, U


def _l1_density_error(n_cells):
    x_c, dx, _, U = _run_sod(n_cells)
    rho_num = U[:, 0]
    rho_ex = _exact_density(x_c, GAMMA_SOD, T_END)
    return float(np.sum(np.abs(rho_num - rho_ex)) * dx)


# --------------------------------------------------------------------------
# Bekçiler
# --------------------------------------------------------------------------

@pytest.fixture(scope='module')
def l1_errors():
    """100 ve 400 hücre L1(ρ) hataları (modül başına bir kez koşulur)."""
    return {100: _l1_density_error(100), 400: _l1_density_error(400)}


def test_sod_l1_yogunluk_hatasi(l1_errors):
    """100 hücrede L1(ρ) ölçülmüş eşiğin altında kalmalı."""
    assert l1_errors[100] < L1_LIMIT_100, (
        f'Sod L1(rho) hatası {l1_errors[100]:.5f} >= eşik {L1_LIMIT_100} — '
        f'HLLC/MUSCL çekirdeği analitik Riemann çözümünden saptı.')


def test_sod_yakinsama_mertebesi(l1_errors):
    """100→400 hücrede ölçülen L1 mertebesi > 0,8 (ikinci mertebe kanıtı).

    minmod sökülüp birinci mertebeye düşülürse bu bekçi KIRMIZI olmalı
    (mutasyon kanıtı raporda).
    """
    order = np.log(l1_errors[100] / l1_errors[400]) / np.log(4.0)
    assert order > ORDER_MIN, (
        f'Ölçülen yakınsama mertebesi {order:.3f} <= {ORDER_MIN} '
        f'(L1_100={l1_errors[100]:.5f}, L1_400={l1_errors[400]:.5f}) — '
        f'şema ikinci mertebe davranışını kaybetti.')


def test_sod_kutle_korunumu():
    """Dalgalar sınırlara varmadan toplam kütle makine hassasiyetinde sabit.

    t=0,2'de en hızlı dalgalar (şok ~x=0,85, fan başı ~x=0,26) tüp içinde;
    geçirgen sınırdan akı çıkmadığı için Σρ·dx birebir korunmalı.

    Çift görev BEYANI (ölçüldü, 2026-08-15): bekçi hem korunum formunu hem
    sayısal yayılım disiplinini sınar. İkinci mertebede fark 2,0e-16
    (makine); minmod sökülüp birinci mertebeye düşülünce şokun sayısal
    öncüsü N=100'de sınıra ulaşır ve geçirgen sınırdan 3,4e-10 bağıl kütle
    çıkar — bu da KIRMIZI'dır ve mutasyon C'yi ayrıca yakalar (aşırı
    yayılım kusurdur; korunum formunun kendisi her iki mertebede de kapalı).
    """
    _, dx, U0, U = _run_sod(100)
    mass0 = float(np.sum(U0[:, 0]) * dx)
    mass1 = float(np.sum(U[:, 0]) * dx)
    assert abs(mass1 - mass0) / mass0 < 1e-12, (
        f'1B çekirdek kütle kaybediyor: bağıl fark '
        f'{abs(mass1 - mass0) / mass0:.3e}')


def test_sod_ara_dalga_yapisi(l1_errors):
    """Temas ve star bölgesi doğru yerde: HLLC ara-dalga kolu bozulursa
    (S* dalı, mutasyon kanıtı) L1 patlar; ayrıca star basıncı platosu
    analitik p* değerini vurmalı."""
    x_c, _, _, U = _run_sod(400)
    p_star, u_star = _solve_star(GAMMA_SOD)
    rho = U[:, 0]
    mom = U[:, 1]
    ene = U[:, 2]
    u = mom / rho
    p = (GAMMA_SOD - 1.0) * (ene - 0.5 * rho * u * u)
    # Star bölgesinin içinde (temasın iki yanından uzak) bir pencere:
    # temas x = 0,5 + u*·t; şok x = 0,5 + S_R·t. Pencere temasın sağı.
    x_contact = X_DIAPHRAGM + u_star * T_END
    window = (x_c > x_contact + 0.05) & (x_c < x_contact + 0.12)
    assert window.any(), 'star penceresi boş — test kurulumu hatalı'
    p_win = float(np.median(p[window]))
    assert abs(p_win - p_star) / p_star < 0.01, (
        f'Star bölgesi basıncı {p_win:.5f}, analitik p*={p_star:.5f} — '
        f'ara dalga (temas/star) yapısı yanlış.')
