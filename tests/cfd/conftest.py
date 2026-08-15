# tests/cfd — ortak analitik lüle vakası ve paylaşılan kararlı-hâl çözümü
"""
İzantropik lüle ve korunum bekçilerinin ORTAK vakası: analitik, testin
kendi tanımladığı kosinüs geçişli yakınsak-ıraksak kontur (motor sonucuna
bağımlılık YOK) + tam süpersonik çalışma noktası.

Kararlı-hâl çözümü pahalı olduğundan session kapsamında BİR kez koşulur ve
iki test dosyası aynı çözümü sorgular (süit disiplini: hedefli, tekrarsız).

Vaka sabitleri LULE_ önekiyle adlandırılır: γ=1,2 roket gazı sınıfıdır ve
depodaki diğer test sabitleriyle kavram karışmasın diye önek zorunludur.
"""

import numpy as np
import pytest

# Çalışma noktası (roket sınıfı, kalorik mükemmel gaz)
LULE_GAMMA = 1.2
LULE_R = 350.0          # J/(kg·K)
LULE_P0 = 4.0e6         # Pa
LULE_T0 = 3200.0        # K
LULE_PB = 2.0e3         # Pa — derin eksik-genleşme: lüle içi tam süpersonik

# Analitik kontur (m): kosinüs geçişli, iki uçta sıfır eğim
LULE_L_CONV = 0.12
LULE_L_DIV = 0.18
LULE_R_CHAMBER = 0.040
LULE_R_THROAT = 0.025
LULE_R_EXIT = 0.040

# Izgara (test çözünürlüğü — performans koşusu ayrı, raporda)
LULE_NI = 120
LULE_NJ = 24


def lule_duvar_yaricapi(z):
    """Analitik duvar r_w(z): kosinüs yakınsak + kosinüs ıraksak [m]."""
    z = np.asarray(z, dtype=float)
    conv = LULE_R_THROAT + (LULE_R_CHAMBER - LULE_R_THROAT) * (
        0.5 + 0.5 * np.cos(np.pi * np.clip(z, 0.0, LULE_L_CONV)
                           / LULE_L_CONV))
    div = LULE_R_THROAT + (LULE_R_EXIT - LULE_R_THROAT) * (
        0.5 - 0.5 * np.cos(np.pi * np.clip(z - LULE_L_CONV, 0.0, LULE_L_DIV)
                           / LULE_L_DIV))
    return np.where(z < LULE_L_CONV, conv, div)


@pytest.fixture(scope='session')
def lule_cozumu():
    """Paylaşılan kararlı-hâl çözümü: (grid, sonuç sözlüğü)."""
    from hrma.cfd.grid_axisym import build_grid_from_wall
    from hrma.cfd.steady import solve_steady_axisym

    z_nodes = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, LULE_NI + 1)
    grid = build_grid_from_wall(z_nodes, lule_duvar_yaricapi(z_nodes),
                                LULE_NJ)
    # Derin yakınsama ayarı: korunum bütçesi bekçisi 1e-10 sınıfını ölçer
    # (tasarım belgesi basamak 4). ÖLÇÜLDÜ (M4 Max, 2026-08-15): 8972
    # iterasyon, ~15 s; kalıntı 6,9e-12'ye indi.
    result = solve_steady_axisym(grid, P0=LULE_P0, T0=LULE_T0,
                                 gamma=LULE_GAMMA, R=LULE_R, Pb=LULE_PB,
                                 max_iters=30000, tol_res=1e-10,
                                 settle_tol=1e-11)
    return grid, result
