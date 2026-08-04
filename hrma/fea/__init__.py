"""
hrma.fea — v2.7 analiz modülünün FEA çekirdeği (docs/V2.7_ANALIZ_MODULU.md).

Bu paket, uygulamanın zaten ürettiği eksenel simetrik geometri (kamara/lüle)
üstünde koşan sayısal çözücüleri taşır. gmsh gibi harici mesh bağımlılığı
YOKTUR; numpy + scipy.sparse yeterlidir (V2.7 dokümanı §3 ve §6 kararı).

Planlanan modül yerleşimi (yol haritasıyla birebir):

    mesh_axisym.py        (z, r) düzleminde yapısal quad mesh üreticisi
                          [BU DALGA — mevcut]
    structural_axisym.py  Eksenel simetrik lineer elastik çözücü + yakınsama
                          sürücüsü [BU DALGA — mevcut]
    thermal_axisym.py     Eksenel simetrik GEÇİCİ ısı iletimi çözücüsü
                          [SONRAKİ DALGA — henüz yok; V2.7 Aşama A]
    planar_grain.py       Katı yakıt tanesi kesiti için 2B düzlemsel kip
                          (star/finocyl eksenel simetrik değildir)
                          [V2.7 Aşama C — henüz yok]

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

# Çözücü kiplerinin dürüst durum beyanı (bkz. modül docstring'i).
MODULE_STATUS = {
    "mesh_axisym": "IMPLEMENTED",
    "structural_axisym": "IMPLEMENTED",
    "thermal_axisym": "NOT_IMPLEMENTED",   # sonraki dalga (V2.7 Aşama A)
    "planar_grain": "NOT_IMPLEMENTED",     # V2.7 Aşama C
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
    "MODULE_STATUS",
]
