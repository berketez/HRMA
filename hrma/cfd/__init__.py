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
    AxisymGrid,
    build_grid_from_wall,
    build_nozzle_grid,
)
from hrma.cfd.euler_core import (
    cons_to_prim_1d,
    cons_to_prim_axisym,
    minmod,
    prim_to_cons_1d,
    prim_to_cons_axisym,
    residual_1d,
    residual_axisym,
    run_1d_transient,
)
from hrma.cfd.steady import (
    DEFAULT_CFL_MAX,
    DEFAULT_CFL_START,
    DEFAULT_MAX_ITERS,
    DEFAULT_TOL_RES,
    solve_steady_axisym,
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
]
