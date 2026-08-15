# tests/cfd — kaba→ince çözünürlük çalışması bekçisi (tasarım belgesi §3)
"""
Şoklu vaka (LULE_PB_SOK) üç çözünürlükte çözülür: 30×6, 60×12 (bu dosyada)
+ 120×24 (sok_cozumu oturum fikstürü — süit disiplini: ince basamak yeniden
çözülmez). Bekçiler İYİLEŞMEYİ kilitler:

  (1) her basamak converged=True (şok sensörü + sınırlayıcı tazelemesiyle
      üç basamak da yakınsar — ölçüldü; kolon-bazlı sensör öncesi 30×6 ve
      80×16 kalıntı platosunda takılıyordu, gerekçe euler_core'da),
  (2) debi hatası (analitik boğulmuş debiye karşı, formül TEST İÇİNDE)
      inceltmeyle KESİN azalır,
  (3) şok konumu hatası hücre boyu ölçeğinde kalır (|Δz| ≤ 0,5·h) ve en
      ince basamak en kabadan belirgin iyidir.

ÖLÇÜLDÜ (bu depo, M4 Max, 2026-08-15; Pb=2,747 MPa koşusu, eşik payları
Pb=2,75 MPa vakasını da kapsar):
  30×6 : conv @  7307 iter (~3 s)  |Δz|=2,35 mm (h=10 mm)   debi %0,247
  60×12: conv @ 17568 iter (~9 s)  |Δz|=0,07 mm (h=5 mm)    debi %0,079
  120×24: conv @ ~29500 iter (~27 s) |Δz|=0,27 mm (h=2,5 mm) debi %0,038
Şok konumu hatası MONOTON DEĞİL (60×12 basamağı ara değerleme şansıyla
anormal iyi) — bu yüzden konum bekçisi 'her basamakta ≤ 0,5·h' + 'en ince
< 0,5 × en kaba' biçiminde kurulur; debi hatası monoton (bekçi kesin
azalma). Ölçülen |Δz|/h en kötüsü 0,235; debi oranları 0,32 ve 0,48.
"""

import numpy as np
import pytest

from .conftest import (
    LULE_GAMMA, LULE_P0, LULE_PB_SOK, LULE_R, LULE_T0,
    LULE_L_CONV, LULE_L_DIV, LULE_R_THROAT, lule_duvar_yaricapi,
)
from .test_normal_sok import sok_konumu_mach, analitik_sok_konumu

# Kaba basamaklar (ince basamak = sok_cozumu, 120×24). Ayarlar ölçümden:
# tol_res=1e-5 + settle_tol=1e-6 ile her ikisi de erken ve temiz yakınsar.
KABA_BASAMAKLAR = ((30, 6), (60, 12))
DEBI_AZALMA_ORANI = 0.8      # ölçülen oranlar 0,32 ve 0,48 — pay ~2×
KONUM_HUCRE_ORANI = 0.5      # ölçülen en kötü |Δz|/h = 0,235 — pay ~2×
INCE_KABA_ORANI = 0.5        # ölçülen 0,27/2,35 = 0,115 — pay ~4×
INCE_DEBI_TOL = 0.001        # en ince debi hatası; ölçüm %0,038 × ~2,6


@pytest.fixture(scope='module')
def merdiven(sok_cozumu):
    """[(ni, nj, sonuç), ...] kaba→ince; ince basamak oturum fikstüründen."""
    from hrma.cfd.grid_axisym import build_grid_from_wall
    from hrma.cfd.steady import solve_steady_axisym

    basamaklar = []
    for ni, nj in KABA_BASAMAKLAR:
        z_nodes = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, ni + 1)
        grid = build_grid_from_wall(z_nodes, lule_duvar_yaricapi(z_nodes),
                                    nj)
        res = solve_steady_axisym(grid, P0=LULE_P0, T0=LULE_T0,
                                  gamma=LULE_GAMMA, R=LULE_R,
                                  Pb=LULE_PB_SOK, max_iters=30000,
                                  tol_res=1e-5, settle_tol=1e-6)
        basamaklar.append((ni, nj, res))
    grid_ince, res_ince = sok_cozumu
    basamaklar.append((grid_ince.ni, grid_ince.nj, res_ince))
    return basamaklar


def _analitik_debi():
    """Boğulmuş debi (Anderson Eş. 5.23) — test içinde kurulur."""
    g = LULE_GAMMA
    a_t = np.pi * LULE_R_THROAT ** 2
    return (LULE_P0 * a_t / np.sqrt(LULE_T0) * np.sqrt(g / LULE_R)
            * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0))))


def test_her_basamak_yakinsar(merdiven):
    for ni, nj, res in merdiven:
        assert res['converged'] is True, (
            f"{ni}×{nj} basamağı yakınsamadı: {res['convergence_basis']}")


def test_debi_hatasi_inceltmeyle_azalir(merdiven):
    """Debi hatası kesin azalır + en incede eşik altı (iyileşme kilidi)."""
    mdot_ref = _analitik_debi()
    hatalar = [abs(res['mass_flow_out_kg_s'] - mdot_ref) / mdot_ref
               for _, _, res in merdiven]
    for k in range(len(hatalar) - 1):
        assert hatalar[k + 1] < DEBI_AZALMA_ORANI * hatalar[k], (
            f'debi hatası inceltmeyle düşmedi: basamak {k} → {k + 1}: '
            f'{hatalar[k]:.4%} → {hatalar[k + 1]:.4%} (ölçülen oranlar '
            f'0,32/0,48 idi; eşik {DEBI_AZALMA_ORANI})')
    assert hatalar[-1] < INCE_DEBI_TOL, (
        f'en ince basamak debi hatası {hatalar[-1]:.4%} >= '
        f'{INCE_DEBI_TOL:.1%} (ölçüm %0,038 idi)')


def test_sok_konumu_inceltmeyle_iyilesir(merdiven):
    """|Δz| her basamakta hücre boyu ölçeğinde + en ince, en kabadan iyi.
    (Kesin monotonluk BİLEREK istenmez: 60×12 ara değerleme şansıyla
    anormal iyi ölçüldü — dosya başı ölçüm bloğu.)"""
    z_ref = analitik_sok_konumu(LULE_PB_SOK, LULE_GAMMA)
    L = LULE_L_CONV + LULE_L_DIV
    hatalar = []
    for ni, nj, res in merdiven:
        z_cfd = sok_konumu_mach(res)
        assert z_cfd is not None, f'{ni}×{nj}: iç şok bulunamadı'
        h = L / ni
        hata = abs(z_cfd - z_ref)
        hatalar.append(hata)
        assert hata <= KONUM_HUCRE_ORANI * h, (
            f'{ni}×{nj}: şok konumu hatası {hata * 1e3:.2f} mm > '
            f'{KONUM_HUCRE_ORANI} hücre ({h * 1e3:.1f} mm) — şok hücre '
            f'ölçeğinde çözülmüyor')
    assert hatalar[-1] < INCE_KABA_ORANI * hatalar[0], (
        f'en ince basamak ({hatalar[-1] * 1e3:.2f} mm) en kabadan '
        f'({hatalar[0] * 1e3:.2f} mm) yeterince iyi değil '
        f'(eşik oran {INCE_KABA_ORANI}; ölçüm 0,115)')
