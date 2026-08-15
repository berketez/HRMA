# tests/cfd — izantropik yakınsak-ıraksak lüle bekçisi (basamak 2)
"""
2B eksenel simetrik çözücü, analitik kosinüs konturlu lülede tam süpersonik
çalışmada sınanır (vaka conftest.py'de; motor sonucuna bağımlılık yok).

Bekçiler:
  (a) converged=True beyanı (hüküm kullanıcı büyüklüklerinden: debi + boğaz
      Mach oturması; kalıntı ikincil).
  (b) Boğaz kütle debisi analitik boğulmuş debiye ±%1 (görev sözleşmesi).
      Analitik formül TEST İÇİNDE kurulur:
        mdot = P0·A_t/√T0 · √(γ/R) · (2/(γ+1))^((γ+1)/(2(γ-1)))
      (Anderson, Modern Compressible Flow, 3. baskı, Eş. 5.23.)
  (c) Kesit-ortalamalı M(x), izantropik alan-Mach bağıntısının (Anderson
      Eş. 5.20) testin KENDİ bisection'ıyla terslenmiş değerine karşı;
      eşikler ölçümden.
  (d) flow/quasi1d.py çapraz karşılaştırması: quasi1d ÇAĞRILIR (değer
      kopyalanmaz), aynı geometri/γ/R'de M(x) ve debi karşılaştırılır.
  (e) Dürüstlük beyanları: not_modelled anahtarları ve kalıntı geçmişi.
"""

import numpy as np
import pytest

from hrma.flow.quasi1d import solve_nozzle

from .conftest import (
    LULE_GAMMA, LULE_R, LULE_P0, LULE_T0, LULE_PB,
    LULE_L_CONV, LULE_L_DIV, LULE_R_THROAT, lule_duvar_yaricapi,
)

# ÖLÇÜLDÜ (bu depo, M4 Max, 2026-08-15; 120×24 ızgara, derin yakınsama):
#   debi sapması: analitik boğulmuşa %0,0385; quasi1d'ye %0,0527
#   kesit-ort. M vs quasi1d: ort %0,317, maks %1,364 (maks boğaz kolonunda,
#   z=0,1213 m — 2B boğaz eğriliği gerçek fiziktir, sıfırlanamaz)
# Eşikler = ölçüm × ~2-3 payı; payın üstü kusur sayılır.
MDOT_REL_TOL = 0.01          # görev sözleşmesi: ±%1
MACH_MEAN_REL_TOL = 0.010
MACH_MAX_REL_TOL = 0.030


def _mach_alan_bagintisindan(area_ratio, gamma, supersonic):
    """A/A* → M: izantropik alan-Mach bağıntısını bisection ile tersler.

    Bağıntı (Anderson Eş. 5.20) testin içinde kurulur; quasi1d'nin
    fonksiyonu ÇAPRAZ katmanda ayrıca çağrılır (bağımsız iki referans).
    """
    def area_ratio_of(m):
        e = (gamma + 1.0) / (2.0 * (gamma - 1.0))
        return (1.0 / m) * ((2.0 / (gamma + 1.0))
                            * (1.0 + 0.5 * (gamma - 1.0) * m * m)) ** e

    lo, hi = (1.0 + 1e-12, 50.0) if supersonic else (1e-8, 1.0 - 1e-12)
    if area_ratio <= 1.0 + 1e-12:
        return 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if (area_ratio_of(mid) - area_ratio) * (
                area_ratio_of(lo) - area_ratio) <= 0.0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def test_yakinsama_beyani(lule_cozumu):
    _, res = lule_cozumu
    assert res['converged'] is True, (
        f"Çözüm yakınsamadı: {res['convergence_basis']} — kalıntı geçmişi "
        f"son değeri {res['residual_history'][-1]:.3e}")
    assert len(res['residual_history']) == res['iterations']


def test_bogaz_kutle_debisi_analitik(lule_cozumu):
    """Ölçülen debi (çıkış akısı), analitik boğulmuş debiye ±%1."""
    _, res = lule_cozumu
    g = LULE_GAMMA
    a_t = np.pi * LULE_R_THROAT ** 2
    mdot_analitik = (LULE_P0 * a_t / np.sqrt(LULE_T0)
                     * np.sqrt(g / LULE_R)
                     * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0))))
    for key in ('mass_flow_in_kg_s', 'mass_flow_out_kg_s'):
        rel = abs(res[key] - mdot_analitik) / mdot_analitik
        assert rel < MDOT_REL_TOL, (
            f'{key} = {res[key]:.6g} kg/s, analitik boğulmuş '
            f'{mdot_analitik:.6g} kg/s — bağıl sapma {rel:.3%} > '
            f'{MDOT_REL_TOL:.0%} (axisym kaynak terimi/geometri kusuru '
            f'debiye böyle yansır)')


def _kesit_mach_karsilastirma(lule_cozumu, referans_mach_fn):
    """Kesit-ortalamalı M(x) ile referans M(x) bağıl farkları döndürür."""
    _, res = lule_cozumu
    z = res['section_average']['z_m']
    m_cfd = res['section_average']['mach']
    m_ref = referans_mach_fn(z)
    rel = np.abs(m_cfd - m_ref) / m_ref
    return rel


def test_kesit_mach_izantropik(lule_cozumu):
    """Kesit-ortalamalı M(x), alan-Mach bağıntısına karşı (test bisection'ı)."""
    a_star = np.pi * LULE_R_THROAT ** 2

    def m_ref(z):
        area = np.pi * lule_duvar_yaricapi(z) ** 2
        return np.array([
            _mach_alan_bagintisindan(max(a / a_star, 1.0), LULE_GAMMA,
                                     supersonic=(zz > LULE_L_CONV))
            for a, zz in zip(area, z)])

    rel = _kesit_mach_karsilastirma(lule_cozumu, m_ref)
    assert float(np.mean(rel)) < MACH_MEAN_REL_TOL, (
        f'kesit-ort. M ortalama bağıl sapma {np.mean(rel):.3%} — izantropik '
        f'alan-Mach bağıntısından sapıldı')
    assert float(np.max(rel)) < MACH_MAX_REL_TOL, (
        f'kesit-ort. M maksimum bağıl sapma {np.max(rel):.3%} '
        f'(konum z={float(np.asarray(lule_cozumu[1]["section_average"]["z_m"])[int(np.argmax(rel))]):.4f} m)')


def test_kesit_mach_quasi1d_capraz(lule_cozumu):
    """quasi1d.solve_nozzle ÇAĞRILARAK çapraz karşılaştırma (aynı geometri,
    aynı γ/R; rejim tam süpersonik aile olmalı)."""
    _, res = lule_cozumu
    z = np.asarray(res['section_average']['z_m'])
    area = np.pi * lule_duvar_yaricapi(z) ** 2
    q1d = solve_nozzle(z, area, P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA,
                       R=LULE_R, Pb=LULE_PB)
    assert q1d['regime'] in ('underexpanded', 'perfectly_expanded',
                             'overexpanded'), (
        f"quasi1d rejimi {q1d['regime']} — vaka tam süpersonik kurulmalıydı")
    rel = np.abs(res['section_average']['mach'] - q1d['mach']) / q1d['mach']
    assert float(np.mean(rel)) < MACH_MEAN_REL_TOL
    assert float(np.max(rel)) < MACH_MAX_REL_TOL
    # Debi çaprazı: iki çözücü aynı boğulmuş debiyi görmeli (±%1)
    rel_mdot = (abs(res['mass_flow_out_kg_s'] - q1d['mass_flow_kg_s'])
                / q1d['mass_flow_kg_s'])
    assert rel_mdot < MDOT_REL_TOL, (
        f"CFD debisi {res['mass_flow_out_kg_s']:.6g} vs quasi1d "
        f"{q1d['mass_flow_kg_s']:.6g} kg/s (bağıl {rel_mdot:.3%})")


def test_durustluk_beyanlari(lule_cozumu):
    """not_modelled anahtarları ve kalıntı geçmişi beyanı (sahte veri yasağı)."""
    _, res = lule_cozumu
    for key in ('viscosity_turbulence', 'reaction_real_gas',
                'time_accuracy', 'separation_resolution'):
        assert key in res['not_modelled'], f'not_modelled eksik: {key}'
    hist = np.asarray(res['residual_history'])
    assert hist.ndim == 1 and hist.size > 10
    assert np.all(np.isfinite(hist))
    assert 'convergence_basis' in res and res['convergence_basis']
