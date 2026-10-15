# hrma/cfd — v3 gerçek CFD paketi (Aşama 1A): sürüm + NOT_MODELLED beyanı
"""
hrma.cfd — 2B eksenel simetrik, sıkıştırılabilir Euler çözücüsü (v3 CFD).

Tasarım belgesi: docs/mimari/cfd-tasarimi.md (BAĞLAYICI — şema kararları
orada: FVM hücre-merkezli, HLLC, MUSCL+minmod, eksenel simetri kaynak
terimli form, yerel Δt + CFL rampası, kalorik mükemmel gaz).

TARİHÇE VE DÜRÜSTLÜK ÇITASI: eski cfd_analysis.py kütle korunumsuz ve
ıraksaktı; SİLİNDİ (2.6.27 parti 16, c48628b). Bu paket onun halefi
DEĞİLDİR — sıfırdan, doğrulama-önce kuruldu (tests/cfd doğrulama merdiveni:
Sod analitik Riemann, izantropik lüle + quasi1d çaprazı, korunum bütçesi,
ızgara metrik sağlığı; mutasyon kanıtlı).

Her koşu not_modelled beyanı + korunum bütçesi yayımlar; yakınsamayan koşu
converged=False + kalıntı geçmişiyle döner (FEA beyan deseni).

Modüller:
    riemann.py      HLLC yaklaşık Riemann akısı (Toro §10.4; Einfeldt/Roe
                    dalga hızları) — saf, vektörize
    euler_core.py   1B/2B FVM güncelleme çekirdeği (MUSCL+minmod, SSP-RK2)
    grid_axisym.py  kontur → yapısal H-tipi ızgara + TAM dönel metrikler
    steady.py       yerel-Δt sürücüsü, CFL rampası, hüküm beyanı
"""

__version__ = '0.1.0'          # Aşama 1A çekirdeği (UI/uç bağlaması YOK)

# Depo kalıbı (quasi1d, launch_site ile aynı biçim): anahtar = modellenmeyen
# fizik, değer = açıklama. steady.solve_steady_axisym çıktısına aynen
# kopyalanır. Tasarım belgesi §1 kapsam-dışı sütunuyla birebir.
CFD_NOT_MODELLED = {
    'viscosity_turbulence': (
        'Viskozite, sınır tabakası ve türbülans yok (Euler): cidar kayma '
        'gerilmesi, ısı taşınımı ve şok-sınır tabaka etkileşimi '
        'modellenmedi (Aşama 2: RANS-SA ya da entegral BL kararı).'),
    'reaction_real_gas': (
        'Kimyasal tepkime ve gerçek gaz yok: kalorik mükemmel gaz, sabit '
        'gamma ve R (motor çözücüsünün yayımladığı değerler; donmuş '
        'kompozisyon).'),
    'time_accuracy': (
        'Zaman doğruluğu yok: yerel zaman adımıyla kararlı hâle sürülür; '
        'ateşleme/söndürme geçişleri (start-up transient) modellenmedi.'),
    'separation_resolution': (
        'Ayrılmış bölgenin kendisi ÇÖZÜLMEZ (Euler ayrılmayı çözemez): '
        'duvar basınç dağılımı hrma.flow.separation ampirik kriterlerine '
        'GİRDİ olur (Aşama 1B), ayrılma sonrası akış alanı modellenmedi.'),
}

from hrma.cfd.riemann import hllc_flux
from hrma.cfd.grid_axisym import (
    COLLAR_BLEND_PROFILE,
    DEFAULT_RADIAL_STRETCH,
    RADIAL_DISTRIBUTIONS,
    RADIAL_UNIFORM_REL_TOL,
    AxisymGrid,
    WallCollar,
    build_grid_from_wall,
    build_nozzle_grid,
    collar_weights,
    radial_geometry_block,
    radial_nodes,
    wall_node_normals,
)
from hrma.cfd.euler_core import (
    OUTLET_ANCHOR_BASIS,
    OUTLET_ANCHOR_CORE_PRESSURE,
    OUTLET_ANCHOR_EXTRAPOLATE,
    OUTLET_ANCHOR_MODES,
    WALL_BC_MODES,
    WALL_BC_NOSLIP,
    WALL_BC_SLIP,
    cons_to_prim_1d,
    cons_to_prim_axisym,
    minmod,
    prim_to_cons_1d,
    prim_to_cons_axisym,
    residual_1d,
    residual_axisym,
    run_1d_transient,
)
from hrma.cfd.gas_transport import (
    GasTransport,
    PRANDTL_TURBULENT,
    PRANDTL_TURBULENT_BAND,
    PRANDTL_TURBULENT_CITATION,
    VISCOSITY_LAW_SOURCE,
    effective_conductivity,
    frozen_prandtl,
    resolve_gas_transport,
    viscosity_exponent,
    viscosity_power_law,
)
from hrma.cfd.gradients import (
    BoundaryFaceValues,
    MAX_SKEW_ITERS,
    face_gradients,
    green_gauss_gradient,
    interpolate_to_faces,
)
from hrma.cfd.viscous_tensor import (
    STOKES_BULK_COEFF,
    StressAxisym,
    hoop_momentum_source,
    stress_axisym,
    stress_from_gradients,
    stress_trace,
    thin_layer_stress_difference,
)
from hrma.cfd.viscous import (
    TURBULENCE_CLOSED_BY_MU_T,
    VISCOUS_NOT_MODELLED,
    WALL_TEMP_SENSITIVITY_RATIOS,
    WALL_THERMAL_MODES,
    WallOutputs,
    h_g_wall_temp_sensitivity,
    nonphysical_state,
    viscous_local_dt_limit,
    viscous_residual,
    viscous_spectral_radius,
)
from hrma.cfd.wall_distance import (
    point_polyline_distance,
    wall_distance_field,
)
from hrma.cfd.sa_neg import (
    SA_CITATIONS,
    SA_CONVECTION_SCHEMES,
    SA_FREESTREAM_CHI_BAND,
    SA_NOT_MODELLED,
    SASource,
    sa_constants,
    sa_convective_residual,
    sa_diffusive_residual,
    sa_point_implicit_delta,
    sa_residual,
    sa_source_terms,
    turbulent_viscosity,
    vorticity_magnitude,
)
from hrma.cfd.relax_implicit import viscous_jacobian_blocks
from hrma.cfd.steady import (
    DEFAULT_C_VISC,
    DEFAULT_CFL_MAX,
    DEFAULT_CFL_START,
    DEFAULT_MAX_ITERS,
    DEFAULT_TOL_RES,
    TURBULENCE_MODELS,
    TURBULENCE_NONE,
    TURBULENCE_SA_NEG,
    ViscousOptions,
    first_cell_for_y_plus,
    solve_steady_axisym,
    solve_with_y_plus_target,
    wall_grid_quality,
)
# Viskoz evre V4 — ÜRÜN köprüleri (§8.1 termal FEA profili, §8.2 itki
# kaybı). AYRILMA köprüsü (separation.py) BİLEREK dışa verilmez: hrma.flow
# de ``assess_separation`` adını taşır ve buradan da verilirse sessiz
# gölgeleme doğar (o modülün docstring'indeki ad çakışması uyarısı) —
# çağıran ``from hrma.cfd.separation import assess_separation as
# assess_cfd_separation`` biçiminde, TAKMA ADLA almalıdır.
from hrma.cfd.wall_output import (
    EDGE_SOURCE_AXIS,
    EDGE_SOURCE_WALL_PRESSURE,
    EDGE_SOURCES,
    FRICTION_SOURCE,
    SUTTON_FRICTION_BAND,
    SUTTON_FRICTION_BAND_CITATION,
    T_AW_BASES,
    T_AW_BASIS_ADIABATIC,
    T_AW_BASIS_RECOVERY,
    THERMAL_PROFILE_SOURCE,
    WALL_OUTPUT_NOT_MODELLED,
    friction_thrust_loss,
    solution_declaration,
    thermal_axial_profile,
    viscous_wall_block,
)

__all__ = [
    '__version__',
    'CFD_NOT_MODELLED',
    'hllc_flux',
    'AxisymGrid',
    'build_grid_from_wall',
    'build_nozzle_grid',
    'cons_to_prim_1d',
    'cons_to_prim_axisym',
    'minmod',
    'prim_to_cons_1d',
    'prim_to_cons_axisym',
    'residual_1d',
    'residual_axisym',
    'run_1d_transient',
    'DEFAULT_CFL_MAX',
    'DEFAULT_CFL_START',
    'DEFAULT_MAX_ITERS',
    'DEFAULT_TOL_RES',
    'solve_steady_axisym',
    # Viskoz evre V0 — gaz taşınım sarmalayıcısı (tasarım belgesi §5.8)
    'GasTransport',
    'PRANDTL_TURBULENT',
    'PRANDTL_TURBULENT_BAND',
    'PRANDTL_TURBULENT_CITATION',
    'VISCOSITY_LAW_SOURCE',
    'effective_conductivity',
    'frozen_prandtl',
    'resolve_gas_transport',
    'viscosity_exponent',
    'viscosity_power_law',
    # Viskoz evre V0 — gradyan operatörü (§5.2) ve gerilme cebiri (§5.3)
    'BoundaryFaceValues',
    'MAX_SKEW_ITERS',
    'face_gradients',
    'green_gauss_gradient',
    'interpolate_to_faces',
    'STOKES_BULK_COEFF',
    'StressAxisym',
    'hoop_momentum_source',
    'stress_axisym',
    'stress_from_gradients',
    'stress_trace',
    'thin_layer_stress_difference',
    # Viskoz evre V1 — laminer viskoz kalıntı + duvar BC'leri (§5.1, §5.4)
    'VISCOUS_NOT_MODELLED',
    'WALL_BC_MODES',
    'WALL_BC_NOSLIP',
    'WALL_BC_SLIP',
    'WALL_TEMP_SENSITIVITY_RATIOS',
    'WALL_THERMAL_MODES',
    'WallOutputs',
    'h_g_wall_temp_sensitivity',
    'viscous_local_dt_limit',
    'viscous_residual',
    'viscous_spectral_radius',
    # Viskoz evre V1 — sürücü bağlaması (§5.6): opt-in viskoz koşu,
    # viskoz yerel Δt katsayısı ve j-satır örtük viskoz Jacobian bloğu
    'DEFAULT_C_VISC',
    'ViscousOptions',
    'viscous_jacobian_blocks',
    # Viskoz evre V2 — ızgara gerdirme (§5.7), dürüst y⁺ döngüsü (§5.7) ve
    # ses-altı çıkış çapası (devir kusuru #2). ÜÇÜ DE OPT-IN: varsayılan
    # yol (düzgün ızgara + dışdeğerleme çıkışı) bit-özdeş kalır.
    'DEFAULT_RADIAL_STRETCH',
    'RADIAL_DISTRIBUTIONS',
    'radial_nodes',
    # Viskoz evre V1b — duvar-normal yaka (parti 39). OPT-IN: wall_collar
    # verilmedikçe düğümler bugünkü ifadenin harfi harfine kendisidir.
    'COLLAR_BLEND_PROFILE',
    'WallCollar',
    'collar_weights',
    'wall_node_normals',
    # Gerdirilmiş/yakalı ızgaranın tüketiciye TÜRETTİRMEDEN verilecek
    # radyal geometrisi (üretici parti 40). UCA BAĞLIDIR: /api/cfd/nozzle
    # alan bloğunda 'radial_geometry' adıyla yayımlanır (app.py
    # _cfd_field_block). ÖH defter P6B3-05 (D23): bu yorum "uca
    # BAĞLANMADI" diyordu, ölçüm yayımlandığını gösterdi ve beyan
    # düzeltildi. Bağlı OLMAYAN şey ızgara GERDİRMESİDİR — yayın yolu
    # düzgün ızgara kurar (kilit bekçisi tests/cfd/test_izgara_gerdirme.py).
    'RADIAL_UNIFORM_REL_TOL',
    'radial_geometry_block',
    'OUTLET_ANCHOR_BASIS',
    'OUTLET_ANCHOR_CORE_PRESSURE',
    'OUTLET_ANCHOR_EXTRAPOLATE',
    'OUTLET_ANCHOR_MODES',
    'first_cell_for_y_plus',
    'solve_with_y_plus_target',
    # Viskoz evre V2 — SA-neg türbülans çekirdeği (§5.5) + duvar mesafesi.
    # nonphysical_state: viskoz/SA/Δt yollarının ORTAK fiziksel-olmayan
    # durum ölçütü (tek sözleşme; parti 38 devir kusuru #1'in kapanışı).
    'nonphysical_state',
    'point_polyline_distance',
    'wall_distance_field',
    'SA_CITATIONS',
    'SA_CONVECTION_SCHEMES',
    'SA_FREESTREAM_CHI_BAND',
    'SA_NOT_MODELLED',
    'SASource',
    'sa_constants',
    'sa_convective_residual',
    'sa_diffusive_residual',
    'sa_point_implicit_delta',
    'sa_residual',
    'sa_source_terms',
    'turbulent_viscosity',
    'vorticity_magnitude',
    # Viskoz evre V2 — SA'nın SÜRÜCÜYE bağlanması (§5.5) + §5.7 ızgara
    # kalitesi beyanı. Türbülans OPT-IN: ViscousOptions(turbulence=...)
    # varsayılanı 'none'dır ve o dalda laminer yol bit-özdeştir.
    'TURBULENCE_MODELS',
    'TURBULENCE_NONE',
    'TURBULENCE_SA_NEG',
    'TURBULENCE_CLOSED_BY_MU_T',
    'wall_grid_quality',
    # Viskoz evre V4 — ürün köprüleri (§8.1 / §8.2). Ayrılma köprüsü
    # (hrma.cfd.separation) ad çakışması yüzünden BURADAN VERİLMEZ.
    'EDGE_SOURCE_AXIS',
    'EDGE_SOURCE_WALL_PRESSURE',
    'EDGE_SOURCES',
    'FRICTION_SOURCE',
    'SUTTON_FRICTION_BAND',
    'SUTTON_FRICTION_BAND_CITATION',
    'T_AW_BASES',
    'T_AW_BASIS_ADIABATIC',
    'T_AW_BASIS_RECOVERY',
    'THERMAL_PROFILE_SOURCE',
    'WALL_OUTPUT_NOT_MODELLED',
    'friction_thrust_loss',
    'solution_declaration',
    'thermal_axial_profile',
    'viscous_wall_block',
]
