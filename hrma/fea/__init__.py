"""
hrma.fea — v2.7 analiz modülünün FEA çekirdeği (docs/V2.7_ANALIZ_MODULU.md).

Bu paket, uygulamanın zaten ürettiği eksenel simetrik geometri (kamara/lüle)
üstünde koşan sayısal çözücüleri taşır. gmsh gibi harici mesh bağımlılığı
YOKTUR; numpy + scipy.sparse yeterlidir (V2.7 dokümanı §3 ve §6 kararı).

Planlanan modül yerleşimi (yol haritasıyla birebir):

    mesh_axisym.py        (z, r) düzleminde yapısal quad mesh üreticisi
                          [mevcut]
    structural_axisym.py  Eksenel simetrik lineer elastik çözücü + yakınsama
                          sürücüsü [mevcut]
    thermal_axisym.py     Eksenel simetrik GEÇİCİ ısı iletimi çözücüsü
                          (geri Euler, Bartz konveksiyon BC, otomatik zaman
                          adımı) [mevcut; V2.7 Aşama A]
    mesh_planar.py        Tane kesiti (port → dış yarıçap) 2B düzlemsel
                          yapısal quad mesh + poligon r(θ) örnekleyicisi
                          [mevcut; V2.7 Aşama C]
    planar_grain.py       Katı yakıt tanesi kesiti için 2B DÜZLEM ŞEKİL
                          DEĞİŞTİRME çözücüsü + yakınsama sürücüsü
                          (star/finocyl/slotted eksenel simetrik değildir;
                          B-bar ile ν→0.5 kilitlenme önlemi)
                          [BU DALGA — mevcut; V2.7 Aşama C; doğrulama:
                          tests/test_fea_planar_grain.py — Lamé + simetri
                          + yoğunlaşma yönü bekçileri]

MODULE_STATUS sözlüğü bu beyanın makine tarafından okunur halidir; UI veya
köprü katmanı "termal sonuç" göstermeye kalkmadan önce buradan durumu
doğrulayabilir (sahte veri yasağı: implement edilmemiş çözücünün çıktısı
çizilmez, NOT_IMPLEMENTED beyanı gösterilir).
"""

from hrma.fea.mesh_axisym import (
    AxisymMesh,
    build_wall_mesh,
    DEFAULT_ELEMS_THROUGH_WALL,
    MIN_ELEMS_THROUGH_WALL,
)
from hrma.fea.structural_axisym import (
    Material,
    RefinementResult,
    StructuralResult,
    DEFAULT_MAX_REFINE_ROUNDS,
    DEFAULT_N_AXIAL0,
    DEFAULT_REFINE_TOL,
    REFINE_FACTOR,
    solve_linear,
    solve_pressure,
    solve_with_refinement,
    von_mises,
)
from hrma.fea.thermal_axisym import (
    AdiabaticBC,
    AmbientBC,
    ConvectionBC,
    FixedTemperatureBC,
    HeatFluxBC,
    ThermalMaterial,
    ThermalResult,
    DEFAULT_DT_TOL,
    DEFAULT_MAX_DT_HALVINGS,
    DEFAULT_N_STEPS0,
    STEFAN_BOLTZMANN_W_M2K4,
    solve_transient,
    solve_transient_auto,
)
from hrma.fea.mesh_planar import (
    PlanarSectionMesh,
    build_grain_section_mesh,
    port_radius_sampler_from_polygon,
)
from hrma.fea.planar_grain import (
    DEFAULT_N_THETA0,
    GrainRefinementResult,
    PlanarGrainResult,
    elasticity_matrix_plane_strain,
    max_principal_plane_strain,
    solve_grain_with_refinement,
    solve_plane_strain_section,
    von_mises_plane_strain,
)

# Çözücü kiplerinin dürüst durum beyanı (bkz. modül docstring'i).
MODULE_STATUS = {
    "mesh_axisym": "IMPLEMENTED",
    "structural_axisym": "IMPLEMENTED",
    "thermal_axisym": "IMPLEMENTED",       # V2.7 Aşama A — doğrulama:
                                           # tests/fea/test_termal_dogrulama.py
    "planar_grain": "IMPLEMENTED",         # bu dalga (V2.7 Aşama C) —
                                           # doğrulama: tests/
                                           # test_fea_planar_grain.py
}

__all__ = [
    "AxisymMesh",
    "build_wall_mesh",
    "DEFAULT_ELEMS_THROUGH_WALL",
    "MIN_ELEMS_THROUGH_WALL",
    "Material",
    "RefinementResult",
    "StructuralResult",
    "DEFAULT_MAX_REFINE_ROUNDS",
    "DEFAULT_N_AXIAL0",
    "DEFAULT_REFINE_TOL",
    "REFINE_FACTOR",
    "solve_linear",
    "solve_pressure",
    "solve_with_refinement",
    "von_mises",
    "AdiabaticBC",
    "AmbientBC",
    "ConvectionBC",
    "FixedTemperatureBC",
    "HeatFluxBC",
    "ThermalMaterial",
    "ThermalResult",
    "DEFAULT_DT_TOL",
    "DEFAULT_MAX_DT_HALVINGS",
    "DEFAULT_N_STEPS0",
    "STEFAN_BOLTZMANN_W_M2K4",
    "solve_transient",
    "solve_transient_auto",
    "PlanarSectionMesh",
    "build_grain_section_mesh",
    "port_radius_sampler_from_polygon",
    "DEFAULT_N_THETA0",
    "GrainRefinementResult",
    "PlanarGrainResult",
    "elasticity_matrix_plane_strain",
    "max_principal_plane_strain",
    "solve_grain_with_refinement",
    "solve_plane_strain_section",
    "von_mises_plane_strain",
    "MODULE_STATUS",
]
