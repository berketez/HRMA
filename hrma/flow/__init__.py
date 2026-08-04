"""Yarı-1B sıkıştırılabilir lüle iç akışı paketi (F1 — v3 CFD kulvarının temeli).

Saf fizik: motor sonuç sözlüğünden ve Flask katmanından bağımsızdır; tüm
girdi/çıktılar SI birimindedir (Pa, K, m, m², kg/s). Motor zincirine bağlama
sonraki dalganın işidir (docs/YOL_HARITASI_2.7_VE_SONRASI.md, F1).

Modüller:
  - ``quasi1d``: rejim sınıflandırması, izantropik dallar, lüle içi normal
    şok konumu (Anderson, "Modern Compressible Flow", 3. baskı, Böl. 3 ve 5).
  - ``separation``: Summerfield / Schmucker / Kalt-Badal ayrılma kriterleri
    (geçerlilik aralıkları beyanlı).
"""

from hrma.flow.quasi1d import (
    QUASI1D_NOT_MODELLED,
    REGIME_CHOKED_SUBSONIC,
    REGIME_NO_FLOW,
    REGIME_NORMAL_SHOCK,
    REGIME_OVEREXPANDED,
    REGIME_PERFECT,
    REGIME_SUBSONIC,
    REGIME_UNDEREXPANDED,
    area_ratio_from_mach,
    choked_mass_flow,
    critical_pressures,
    isentropic_ratios,
    mach_from_area_ratio,
    mach_from_pressure_ratio,
    normal_shock_relations,
    solve_nozzle,
)
from hrma.flow.separation import (
    CRITERION_KALT_BADAL,
    CRITERION_SCHMUCKER,
    CRITERION_SUMMERFIELD,
    SEPARATION_NOT_MODELLED,
    SUMMERFIELD_FACTOR_BAND,
    SUMMERFIELD_FACTOR_DEFAULT,
    assess_separation,
    kalt_badal_pressure_ratio,
    schmucker_pressure_ratio,
    summerfield_pressure_ratio,
)

__all__ = [
    'QUASI1D_NOT_MODELLED',
    'REGIME_CHOKED_SUBSONIC',
    'REGIME_NO_FLOW',
    'REGIME_NORMAL_SHOCK',
    'REGIME_OVEREXPANDED',
    'REGIME_PERFECT',
    'REGIME_SUBSONIC',
    'REGIME_UNDEREXPANDED',
    'area_ratio_from_mach',
    'choked_mass_flow',
    'critical_pressures',
    'isentropic_ratios',
    'mach_from_area_ratio',
    'mach_from_pressure_ratio',
    'normal_shock_relations',
    'solve_nozzle',
    'CRITERION_KALT_BADAL',
    'CRITERION_SCHMUCKER',
    'CRITERION_SUMMERFIELD',
    'SEPARATION_NOT_MODELLED',
    'SUMMERFIELD_FACTOR_BAND',
    'SUMMERFIELD_FACTOR_DEFAULT',
    'assess_separation',
    'kalt_badal_pressure_ratio',
    'schmucker_pressure_ratio',
    'summerfield_pressure_ratio',
]
