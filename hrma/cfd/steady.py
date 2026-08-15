# hrma/cfd — kararlı-hâl sürücüsü: yerel Δt, CFL rampası, hüküm beyanı
"""
2B eksenel simetrik Euler çözücüsünün kararlı-hâl sürücüsü (Aşama 1A).

YÖNTEM
------
- Yerel zaman adımı: Δt_c = CFL·V_c / Σ_yüzey (|u·n̂|+a)|S| (hücre başına;
  zaman doğruluğu YOK — kararlı hâle en dik iniş; not_modelled beyanında).
- CFL rampası: 0,5 → 0,9 (tasarım belgesi §2), ramp_iters boyunca doğrusal.
- Zaman entegrasyonu: SSP-RK2 (euler_core ile aynı kalıntı).
- Başlangıç tahmini: kolon bazlı izantropik alan-Mach çözümü. Alan-Mach
  terslemesi hrma.flow.quasi1d.mach_from_area_ratio'dan ÇAĞRILIR (parametre
  tutarlılığı: aynı bağıntı ikinci kez yazılmaz). Bu yalnız BAŞLANGIÇ
  tahminidir; doğrulama bağımsızlığını bozmaz — hüküm, binlerce iterasyon
  sonra oturan duruma ve analitik referanslara karşıdır (tests/cfd).

HÜKÜM (converged) BEYANI — FEA kabul-ölçütü dersinin izdüşümü
-------------------------------------------------------------
Hüküm KULLANICI BÜYÜKLÜKLERİNDEN verilir; kalıntı ikincildir:
  (1) kütle debisi (giriş VE çıkış akısı) son `window` iterasyonda bağıl
      bant < settle_tol içinde OTURMUŞ,
  (2) boğaz kesit-ortalamalı Mach aynı bantta OTURMUŞ,
  (3) yoğunluk kalıntısının hacim-ağırlıklı L2 normu (ρ₀·a₀/L ölçeğiyle
      boyutsuzlaştırılmış) tol_res altına İNMİŞ.
Üçü birden sağlanmadan converged=True denmez. Yakınsamayan koşu sonuç +
converged=False + kalıntı geçmişiyle döner (FEA beyan deseni: sonuç
gizlenmez, hüküm de verilmez). Fiziksel olmayan duruma düşen koşu (NaN)
'diverged' beyanıyla, bilinen son sonlu alanla döner.

Uydurma sabit YOK: γ ve R çağırandan gelir (motor çözücüsünün yayımladığı
değerler; köprü katmanı eksikse REDDEDER, burada varsayılan yazılmaz).
"""

import time

import numpy as np

from hrma.cfd import kernels as _kernels
from hrma.cfd.euler_core import (
    cons_to_prim_axisym,
    local_dt_axisym,
    precompute_geometry,
    prim_to_cons_axisym,
    residual_axisym,
    shock_column_flag,
)
from hrma.flow.quasi1d import isentropic_ratios, mach_from_area_ratio

__all__ = ['solve_steady_axisym', 'DEFAULT_CFL_START', 'DEFAULT_CFL_MAX',
           'DEFAULT_RAMP_ITERS', 'DEFAULT_MAX_ITERS', 'DEFAULT_TOL_RES',
           'DEFAULT_SETTLE_WINDOW', 'DEFAULT_SETTLE_TOL']

# Sürücü varsayılanları (tasarım belgesi §2: CFL 0,5→0,9). tol/settle
# değerleri tests/cfd ölçümleriyle sabitlendi (korunum artığı 1e-10 sınıfına
# bu eşiklerde iniliyor; rapor).
DEFAULT_CFL_START = 0.5
DEFAULT_CFL_MAX = 0.9
DEFAULT_RAMP_ITERS = 400
DEFAULT_MAX_ITERS = 20000
DEFAULT_TOL_RES = 1e-8
DEFAULT_SETTLE_WINDOW = 200
DEFAULT_SETTLE_TOL = 1e-9

_ASSUMPTIONS = (
    'steady',                    # kararlı hâl (yerel Δt, zaman doğru değil)
    'axisymmetric',              # 2B eksenel simetri, döngüsüz (swirl yok)
    'inviscid',                  # Euler: viskozite/sınır tabaka yok
    'adiabatic',                 # cidara ısı kaybı yok
    'calorically_perfect_gas',   # sabit gamma ve R
)


def _column_wall_radius(grid):
    """Kolon başına duvar yarıçapı (hücre kolonunun iki düğümünün ortalaması)."""
    r_wall_nodes = grid.R[:, -1]
    return 0.5 * (r_wall_nodes[:-1] + r_wall_nodes[1:])


def _isentropic_initial_state(grid, P0, T0, gamma, R, Pb=None):
    """Kolon bazlı izantropik başlangıç alanı (yalnız tahmin; beyan üstte).

    IRAKSAK DAL SEÇİMİ (Aşama 1B, ölçülen gerekçe): varsayılan süpersonik
    dal. Pb verilmişse ve tam-süpersonik çözümün çıkış statik basıncından
    BÜYÜKSE ıraksak bölge SES-ALTI dalda başlatılır — aksi hâlde çıkış
    kolonu ses-üstü doğar, çıkış BC'si Pb'yi hiç uygulamaz (ses-üstü çıkış
    = tam dışdeğerleme) ve tam-süpersonik alan ayrık SABİT NOKTA olarak
    kalırdı: iç şok hiç oluşmaz (ölçüldü; arka-basınç vakası testinin
    varlık sebebi). Bu yalnız başlangıç TAHMİNİDİR: şokun yeri/varlığı
    çözücünün kendi dinamiğiyle oturur ve analitik 1B referansa karşı
    bağımsız test edilir (tests/cfd/test_normal_sok.py)."""
    g = float(gamma)
    r_w = _column_wall_radius(grid)
    area = np.pi * r_w ** 2
    i_throat = int(np.argmin(area))
    a_star = float(area[i_throat])
    ni, nj = grid.ni, grid.nj
    divergent_supersonic = True
    if Pb is not None:
        ratio_exit = max(float(area[-1] / a_star), 1.0)
        m_exit_sup = mach_from_area_ratio(ratio_exit, g, supersonic=True)
        _, p_ratio_exit, _ = isentropic_ratios(m_exit_sup, g)
        divergent_supersonic = bool(float(Pb) <= float(P0) * p_ratio_exit)
    w = np.empty((ni, nj, 4))
    for i in range(ni):
        ratio = max(float(area[i] / a_star), 1.0)
        mach = mach_from_area_ratio(
            ratio, g, supersonic=(divergent_supersonic and i > i_throat))
        t_ratio, p_ratio, _ = isentropic_ratios(mach, g)
        temp = float(T0) * t_ratio
        p = float(P0) * p_ratio
        rho = p / (float(R) * temp)
        w[i, :, 0] = rho
        w[i, :, 1] = mach * np.sqrt(g * float(R) * temp)
        w[i, :, 2] = 0.0
        w[i, :, 3] = p
    return prim_to_cons_axisym(w[..., 0], w[..., 1], w[..., 2], w[..., 3],
                               g), i_throat


def _section_averages(U, grid, gamma):
    """Kolon (kesit) ortalamaları — hacim ağırlıklı (beyan: kesit ortalaması
    hücre hacmi ağırlığıyla; ince kolonda alan ağırlığına eşdeğer)."""
    g = float(gamma)
    w = cons_to_prim_axisym(U, g)
    a = np.sqrt(g * w[..., 3] / w[..., 0])
    mach = np.sqrt(w[..., 1] ** 2 + w[..., 2] ** 2) / a
    vol = grid.volume
    wsum = np.sum(vol, axis=1)
    m_avg = np.sum(mach * vol, axis=1) / wsum
    p_avg = np.sum(w[..., 3] * vol, axis=1) / wsum
    z_avg = np.sum(grid.z_centers * vol, axis=1) / wsum
    return z_avg, m_avg, p_avg


def solve_steady_axisym(grid, P0, T0, gamma, R, Pb=None,
                        cfl_start=DEFAULT_CFL_START,
                        cfl_max=DEFAULT_CFL_MAX,
                        ramp_iters=DEFAULT_RAMP_ITERS,
                        max_iters=DEFAULT_MAX_ITERS,
                        tol_res=DEFAULT_TOL_RES,
                        settle_window=DEFAULT_SETTLE_WINDOW,
                        settle_tol=DEFAULT_SETTLE_TOL,
                        second_order=True):
    """Lüle iç akışını kararlı hâle sürer; beyanlı sonuç sözlüğü döndürür.

    Args:
        grid: AxisymGrid (grid_axisym; kontur → sample_nozzle_inner_contour).
        P0, T0: rezervuar durma basıncı [Pa] ve sıcaklığı [K].
        gamma, R: kalorik mükemmel gaz sabitleri (motor çözücüsünden;
            varsayılan yok, eksikse çağıran reddetmeli).
        Pb: geri basınç [Pa]; None → çıkışta tam dışdeğerleme (süpersonik).
        Diğerleri: sürücü ayarları (modül sabitlerinde beyanlı).

    Returns:
        dict: converged, convergence_basis, iterations, residual_history,
        korunum bütçesi (kütle/enerji akıları + bağıl artıklar), fields
        (ρ, u_z, u_r, p, T, M), section_average, throat, wall_pressure_Pa,
        not_modelled, assumptions, inputs, runtime_s. Yakınsamasa da sonuç
        döner (converged=False); NaN'da 'diverged' beyanı.
    """
    t_start = time.perf_counter()
    g = float(gamma)
    P0 = float(P0)
    T0 = float(T0)
    Rs = float(R)
    if P0 <= 0.0 or T0 <= 0.0 or Rs <= 0.0:
        raise ValueError('P0, T0 ve R pozitif olmalı (uydurma yedek yok).')
    if not (1.0 < g < 2.0):
        raise ValueError('gamma (1, 2) aralığında olmalı (mükemmel gaz).')

    U, i_throat = _isentropic_initial_state(grid, P0, T0, g, Rs, Pb=Pb)
    # Izgara sabiti yüzey geometrisi BİR kez (hoist; bit-özdeşlik bekçili —
    # tests/cfd/test_performans.py). area_i/area_j aynı diziden dilimlenir.
    geom = precompute_geometry(grid)
    area_i = geom['area_i']
    area_j = geom['area_j']

    # Kalıntı ölçeği: ρ₀·a₀/L (boyutsuzlaştırma beyanı — docstring)
    rho0 = P0 / (Rs * T0)
    a0 = np.sqrt(g * Rs * T0)
    length = float(grid.Z[-1, 0] - grid.Z[0, 0])
    res_scale = rho0 * a0 / length
    vol = grid.volume
    vol_sum = float(np.sum(vol))

    res_hist = []
    mdot_in_hist = []
    mdot_out_hist = []
    mach_throat_hist = []
    diverged = False
    U_last_finite = U.copy()

    # Sınırlayıcı dondurma (limiter freezing): minmod salınımı kararlı-hâl
    # kalıntısını platoda bırakır (ölçüldü: 120×24'te ~1e-4'te takılma).
    # Plato tespitinde eğimler DONDURULUR ve iterasyon derin yakınsamaya
    # sürülür — kararlı-hâl pratiğinde standart (Venkatakrishnan, AIAA J.
    # 33(5), 1995 gerekçesi). Dondurma anı çıktıda beyan edilir; şema minmod
    # kalır (mertebe kanıtı tests/cfd/test_sod.py'de, zaman-doğru koşumda).
    #
    # TAZELEME (Aşama 1B, ölçülen gerekçe): iç şoklu vakada plato, şok daha
    # yerine OTURMADAN tetiklenebilir (ölçüldü, 120×24 arka-basınç vakası:
    # 1698. iterasyonda donan BAYAT eğimler kalıntıyı 6e-3 bandında salınıma
    # kilitledi). Donduktan sonra plato SÜRÜYORSA eğimler güncel durumdan
    # YENİDEN alınır (Picard tarzı tazeleme); durum oturunca tazeleme
    # kendiliğinden kendi-tutarlı hâle gelir ve kalıntı derine iner
    # (ölçüldü: aynı vaka 5,4e-11'e indi). İzantropik (şoksuz) vakada donma
    # sonrası kalıntı inişte olduğundan plato yeniden tetiklenmez — davranış
    # 1A ile aynı kalır (bekçiler: tests/cfd/test_izantropik_lule.py).
    # Son dondurma anı + tazeleme sayısı çıktıda beyan edilir.
    frozen_slopes = None
    frozen_at = None
    freeze_count = 0
    plateau_window = 300

    def _settled(hist):
        band = hist[-settle_window:]
        ref = abs(band[-1])
        return (len(hist) >= settle_window and ref > 0.0
                and (max(band) - min(band)) / ref < settle_tol)

    it = 0
    while it < max_iters:
        cfl = cfl_start + (cfl_max - cfl_start) * min(1.0,
                                                     it / float(ramp_iters))
        r1, aux = residual_axisym(U, grid, g, Rs, P0, T0, Pb=Pb,
                                  second_order=second_order,
                                  slopes=frozen_slopes, geom=geom)
        res_norm = float(np.sqrt(np.sum(r1[..., 0] ** 2 * vol) / vol_sum)
                         / res_scale)
        _, m_sec, _ = _section_averages(U, grid, g)
        res_hist.append(res_norm)
        mdot_in_hist.append(aux['mass_flow_in_kg_s'])
        mdot_out_hist.append(aux['mass_flow_out_kg_s'])
        mach_throat_hist.append(float(m_sec[i_throat]))
        it += 1

        if not np.isfinite(res_norm):
            diverged = True
            break
        U_last_finite = U.copy()

        if (res_norm < tol_res and _settled(mdot_in_hist)
                and _settled(mdot_out_hist)
                and _settled(mach_throat_hist)):
            break

        # Plato tespiti: rampa bitmiş + iki ardışık pencerede kalıntı
        # anlamlı düşmüyor → eğimleri dondur; donmuşken plato SÜRÜYORSA
        # güncel durumdan TAZELE (beyan yukarıda; şoklu vaka gerekçesi).
        if (second_order and it > ramp_iters + 2 * plateau_window
                and (frozen_at is None
                     or it >= frozen_at + 2 * plateau_window)):
            recent = min(res_hist[-plateau_window:])
            before = min(res_hist[-2 * plateau_window:-plateau_window])
            if recent > 0.9 * before:
                _, _, frozen_slopes = residual_axisym(
                    U, grid, g, Rs, P0, T0, Pb=Pb,
                    second_order=second_order, return_slopes=True,
                    geom=geom)
                frozen_at = it
                freeze_count += 1

        # SSP-RK2 (yerel Δt)
        dt = local_dt_axisym(U, grid, g, cfl, area_i, area_j)
        u1 = U + dt[..., None] * r1
        r2, _ = residual_axisym(u1, grid, g, Rs, P0, T0, Pb=Pb,
                                second_order=second_order,
                                slopes=frozen_slopes, geom=geom)
        U = 0.5 * (U + u1 + dt[..., None] * r2)
        if not np.all(np.isfinite(U)):
            diverged = True
            break

    if diverged:
        U = U_last_finite

    # Nihai durum bütçesi (son duruma ait akılar — geçmişin son kaydı değil)
    _, aux_final = residual_axisym(U, grid, g, Rs, P0, T0, Pb=Pb,
                                   second_order=second_order,
                                   slopes=frozen_slopes, geom=geom)
    mdot_in = aux_final['mass_flow_in_kg_s']
    mdot_out = aux_final['mass_flow_out_kg_s']
    e_in = aux_final['energy_flux_in_W']
    e_out = aux_final['energy_flux_out_W']
    mass_rel = abs(mdot_in - mdot_out) / max(abs(mdot_in), 1e-300)
    energy_rel = abs(e_in - e_out) / max(abs(e_in), 1e-300)

    settled_ok = (_settled(mdot_in_hist) and _settled(mdot_out_hist)
                  and _settled(mach_throat_hist))
    res_ok = bool(res_hist and np.isfinite(res_hist[-1])
                  and res_hist[-1] < tol_res)
    converged = bool((not diverged) and settled_ok and res_ok
                     and it < max_iters + 1)
    if diverged:
        basis = (f'DIVERGED: iterasyon {it} içinde fiziksel olmayan durum '
                 f'(NaN/Inf) — bilinen son sonlu alan raporlandı, hüküm yok.')
    else:
        basis = (
            f'Hüküm kullanıcı büyüklüklerinden: debi bandı (giriş/çıkış, '
            f'son {settle_window} iter) '
            f'{"OTURDU" if settled_ok else "OTURMADI"}, boğaz Mach bandı '
            f'{"OTURDU" if settled_ok else "OTURMADI"} '
            f'(settle_tol={settle_tol:g}); yoğunluk L2 kalıntısı '
            f'{res_hist[-1]:.3e} '
            f'{"<" if res_ok else ">="} tol {tol_res:g} (ölçek ρ0·a0/L). '
            f'{it} iterasyon.'
            + (f' Sınırlayıcı son olarak {frozen_at}. iterasyonda '
               f'donduruldu (plato tespiti, {freeze_count} dondurma/'
               f'tazeleme; şema minmod).' if frozen_at is not None
               else ''))

    w = cons_to_prim_axisym(U, g)
    temp = w[..., 3] / (Rs * w[..., 0])
    a_snd = np.sqrt(g * Rs * temp)
    mach = np.sqrt(w[..., 1] ** 2 + w[..., 2] ** 2) / a_snd
    z_sec, m_sec, p_sec = _section_averages(U, grid, g)
    r_w = _column_wall_radius(grid)

    # Aşama 1B köprüsü: separation.py'nin isteyeceği duvar basıncı beyanı —
    # duvara komşu hücre merkezinin basıncı (hücre-merkezli çözücüde duvar
    # değeri dışdeğerlenmemiş ham komşu değerdir; beyan).
    wall_pressure = w[:, -1, 3].copy()

    # Sensör beyan sayısı SON alandan doğrudan (donmuş eğimli bütçe
    # çağrısında sensör bloğu atlanır — aux_final'den alınsa şoklu vakada
    # yanlış 0 beyan edilirdi).
    _sensor_flag = shock_column_flag(w[..., 3]) if second_order else None
    sensor_columns = 0 if _sensor_flag is None else int(np.sum(_sensor_flag))

    # NOT_MODELLED tek kaynağı paket köküdür; döngüsel içe aktarmayı önlemek
    # için çağrı anında alınır (fonksiyon çağrılırken paket tam yüklüdür).
    from hrma.cfd import CFD_NOT_MODELLED

    return {
        'converged': converged,
        'convergence_basis': basis,
        'iterations': it,
        'limiter_frozen_at_iter': frozen_at,
        'limiter_freeze_count': freeze_count,
        'residual_history': np.asarray(res_hist),
        'mass_flow_in_kg_s': mdot_in,
        'mass_flow_out_kg_s': mdot_out,
        'mass_balance_rel': mass_rel,
        'energy_flux_in_W': e_in,
        'energy_flux_out_W': e_out,
        'energy_balance_rel': energy_rel,
        'wall_mass_flux_kg_s': aux_final['wall_mass_flux_kg_s'],
        'budget_basis': (
            'Korunum bütçesi: giriş/çıkış yüzey akıları HLLC yüzey '
            'integrallerinden (2π dahil, gerçek birim); bağıl artıklar '
            '|giriş−çıkış|/giriş. Duvar kütle akısı kayma sınırında ayrık '
            'olarak tam sıfırdır (ayna durumda HLLC kütle akısı özdeş 0).'),
        'fields': {
            'rho_kg_m3': w[..., 0],
            'u_z_m_s': w[..., 1],
            'u_r_m_s': w[..., 2],
            'pressure_Pa': w[..., 3],
            'temperature_K': temp,
            'mach': mach,
        },
        'z_centers_m': grid.z_centers,
        'r_centers_m': grid.r_centers,
        'section_average': {
            'z_m': z_sec,
            'mach': m_sec,
            'pressure_Pa': p_sec,
            '_basis': 'Hacim ağırlıklı kolon ortalaması (beyan: '
                      '_section_averages docstring).',
        },
        'throat': {
            'i': i_throat,
            'z_m': float(z_sec[i_throat]),
            'radius_m': float(r_w[i_throat]),
            'area_m2': float(np.pi * r_w[i_throat] ** 2),
            'mach_section_avg': float(m_sec[i_throat]),
        },
        'wall_pressure_Pa': wall_pressure,
        'wall_pressure_z_m': grid.z_centers[:, -1].copy(),
        'wall_pressure_basis': (
            'Duvara komşu hücre merkezi basıncı (hücre-merkezli FVM ham '
            'değeri); ekseni wall_pressure_z_m — duvara komşu hücre '
            'merkezlerinin z koordinatı [m], aynı uzunlukta (ni,). '
            'Aşama 1B: separation.py girdisi bu beyanla bağlanır.'),
        'shock_sensor_columns': sensor_columns,
        'shock_sensor_basis': (
            'Şok sensörü (euler_core.SHOCK_SENSOR_THRESHOLD, eksenel yüz '
            '|Δp|/min(p) eşiği, ölçümden): bayraklı kolonlarda MUSCL '
            'eğimleri sıfırlanır (yerel birinci mertebe — şok stall '
            'tedavisi, gerekçe residual_axisym docstring). Pürüzsüz akışta '
            'hiç tetiklenmez (0 kolon = sonuç sensörsüz yolla bit-özdeş); '
            'sayı son duruma aittir.'),
        'kernel_backend': ('numba' if _kernels.NUMBA_AVAILABLE
                           else 'numpy'),
        'kernel_backend_basis': (
            'Yönlü HLLC akısının arka ucu (kernels.py): numba isteğe bağlı '
            'hızlandırmadır, kurulu değilse (ya da HRMA_CFD_DISABLE_NUMBA=1) '
            'saf NumPy yolu aynı sonucu üretir (eşdeğerlik bekçili; '
            'tests/cfd/test_performans.py).'),
        'not_modelled': dict(CFD_NOT_MODELLED),
        'assumptions': list(_ASSUMPTIONS),
        'inputs': {
            'P0_Pa': P0, 'T0_K': T0, 'gamma': g, 'R_J_kgK': Rs,
            'Pb_Pa': None if Pb is None else float(Pb),
            'grid_ni': grid.ni, 'grid_nj': grid.nj,
            'cfl_start': float(cfl_start), 'cfl_max': float(cfl_max),
            'tol_res': float(tol_res), 'settle_tol': float(settle_tol),
            '_basis': 'Çağıranın verdiği girdilerin yankısı (SI).',
        },
        'runtime_s': time.perf_counter() - t_start,
    }
