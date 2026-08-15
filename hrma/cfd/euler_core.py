# hrma/cfd — 1B / 2B eksenel simetrik FVM Euler güncelleme çekirdeği
"""
Hücre-merkezli sonlu hacim Euler çekirdeği (v3 CFD, Aşama 1A).

ŞEMA (tasarım belgesi docs/mimari/cfd-tasarimi.md §2 — kararlar kesin)
----------------------------------------------------------------------
- Akı: HLLC (hrma/cfd/riemann.py; Toro 3. baskı §10.4, Einfeldt/Roe
  dalga hızları).
- İkinci mertebe: MUSCL kenar dışdeğerlemesi PRİMİTİF değişkenlerde
  (ρ, u, p) + minmod sınırlayıcı (van Leer, "Towards the ultimate
  conservative difference scheme V", JCP 32, 1979; Toro §13.4). Primitif
  rekonstrüksiyon pozitifliği korunum değişkenlerine göre daha iyi korur ve
  beyan edilir. Eğim indeks uzayında alınır (yapısal ızgara; düzgün olmayan
  aralıkta biçimsel mertebe düz ızgarada ikincidir — Aşama 1 beyanı).
- Eksenel simetri: kaynak terimli korunum formu. Dönel hücre üstünde
  integral form (2π tam çarpanlarıyla):
      d(U·V)/dt = − Σ_yüzey F̂·S + [0, 0, p·2π·A_düzlem, 0]
  Tek kaynak r-momentumdaki basınç terimidir (∂p/∂r'nin silindirik hacim
  integralinden kalan parça); kütle ve enerjiye kaynak GİRMEZ. Yüzey
  vektörleri ve hacimler grid_axisym'den TAM dönel geometriyle gelir;
  Σ S_r = 2π·A_düzlem özdeşliği sayesinde düzgün basınç alanı + durgun gaz
  TAM korunur (serbest akım koruması, ayrık özdeşlik).
- Eksen r=0: j=0 yüzlerinin alanı geometrik olarak sıfır (akısız); MUSCL
  eğimi için eksen altına AYNA hücreleri (ρ, u_z, p çift; u_r tek) konur —
  simetri sınırı budur, 0/0 muamelesi yoktur.
- Zaman: SSP-RK2 (Heun/Shu-Osher; Gottlieb & Shu, Math. Comp. 67, 1998) —
  TVD-uyumlu iki aşama. 1B sürücü zaman-doğru (Sod); 2B kararlı-hâl
  sürücüsü (steady.py) yerel Δt ile aynı kalıntıyı kullanır.

SINIR KOŞULLARI (2B; tasarım belgesi §2)
----------------------------------------
- Giriş: rezervuar (P0, T0) + iç bölgeden statik basınç dışdeğerlemesi
  (ses-altı karakteristik sayısı 1: tek bilgi içeriden, gerisi rezervuar
  izantropiğinden; eksenel akış yönü). Basınç [p_sonik, P0) bandına
  kırpılır — bu bir fiziksel bant sınırıdır (ses-altı giriş beyanı),
  uydurma sabit değildir.
- Duvar: kayma (Euler) — hayalet hücrede hız duvar normaline göre
  yansıtılır; HLLC ayna durumda kütle/enerji akısını TAM sıfır, momentum
  akısını salt basınç verir.
- Çıkış: yüzey-normal Mach >= 1 ise sıfırıncı mertebe dışdeğerleme;
  ses-altıysa ve Pb verildiyse statik basınç Pb'ye bağlanır, gerisi
  dışdeğerlenir (basit ses-altı karakteristik yaklaşımı — beyanlı).

DÜRÜSTLÜK: pozitiflik tabanı/kırpma YOKTUR. Fiziksel olmayan durum (negatif
ρ veya p) NaN üretir; sürücü bunu ıraksama olarak raporlar (converged=False).
"""

import numpy as np

from hrma.cfd.riemann import hllc_flux

__all__ = [
    'prim_to_cons_1d', 'cons_to_prim_1d', 'minmod', 'residual_1d',
    'run_1d_transient', 'prim_to_cons_axisym', 'cons_to_prim_axisym',
    'residual_axisym', 'local_dt_axisym', 'inlet_state_from_stagnation',
]

_TWO_PI = 2.0 * np.pi


# --------------------------------------------------------------------------
# Durum dönüşümleri
# --------------------------------------------------------------------------

def prim_to_cons_1d(rho, u, p, gamma):
    """(ρ, u, p) → U = [ρ, ρu, E], E = p/(γ−1) + ρu²/2. Şekil: (n, 3)."""
    rho = np.asarray(rho, dtype=float)
    u = np.asarray(u, dtype=float)
    p = np.asarray(p, dtype=float)
    e = p / (float(gamma) - 1.0) + 0.5 * rho * u * u
    return np.stack([rho, rho * u, e], axis=-1)


def cons_to_prim_1d(U, gamma):
    """U = [ρ, ρu, E] → (ρ, u, p). Kırpma yok: bozuk durum NaN üretir."""
    rho = U[..., 0]
    u = U[..., 1] / rho
    p = (float(gamma) - 1.0) * (U[..., 2] - 0.5 * rho * u * u)
    return rho, u, p


def prim_to_cons_axisym(rho, uz, ur, p, gamma):
    """(ρ, u_z, u_r, p) → U = [ρ, ρu_z, ρu_r, E]."""
    rho = np.asarray(rho, dtype=float)
    uz = np.asarray(uz, dtype=float)
    ur = np.asarray(ur, dtype=float)
    p = np.asarray(p, dtype=float)
    e = p / (float(gamma) - 1.0) + 0.5 * rho * (uz * uz + ur * ur)
    return np.stack([rho, rho * uz, rho * ur, e], axis=-1)


def cons_to_prim_axisym(U, gamma):
    """U → W = [ρ, u_z, u_r, p] (aynı şekil, son eksen 4)."""
    rho = U[..., 0]
    uz = U[..., 1] / rho
    ur = U[..., 2] / rho
    p = (float(gamma) - 1.0) * (U[..., 3]
                                - 0.5 * rho * (uz * uz + ur * ur))
    return np.stack([rho, uz, ur, p], axis=-1)


def minmod(a, b):
    """minmod sınırlayıcı: işaretler aynıysa mutlakça küçüğü, değilse 0."""
    return 0.5 * (np.sign(a) + np.sign(b)) * np.minimum(np.abs(a),
                                                        np.abs(b))


def limited_slopes(w_ext):
    """2 hayalet katmanlı dizide minmod eğimleri (0. eksen boyunca).

    w_ext: (n+4, ..., nvar) → eğimler (n+2, ..., nvar) (ext hücre 1..n+2).
    """
    d = w_ext[1:] - w_ext[:-1]
    return minmod(d[:-1], d[1:])


def _edge_states(w_ext, slopes):
    """MUSCL kenar durumları; slopes=None → birinci mertebe.

    w_ext: (n+4, ..., nvar). Döner: (W_L, W_R), her biri (n+1, ..., nvar) —
    n+1 yüzün sol/sağ durumları.
    """
    if slopes is None:
        return w_ext[1:-2], w_ext[2:-1]
    return (w_ext[1:-2] + 0.5 * slopes[:-1],
            w_ext[2:-1] - 0.5 * slopes[1:])


# --------------------------------------------------------------------------
# 1B çekirdek (Sod merdiveni — basamak 1)
# --------------------------------------------------------------------------

def residual_1d(U, dx, gamma, second_order=True):
    """1B Euler dU/dt — geçirgen (transmissive) sınırlar, düzgün dx."""
    rho, u, p = cons_to_prim_1d(U, gamma)
    w = np.stack([rho, u, p], axis=-1)
    w_ext = np.concatenate([w[:1], w[:1], w, w[-1:], w[-1:]], axis=0)
    w_l, w_r = _edge_states(w_ext,
                            limited_slopes(w_ext) if second_order else None)
    zeros = np.zeros_like(w_l[..., 0])
    f_rho, f_mn, _, f_e = hllc_flux(
        w_l[..., 0], w_l[..., 1], zeros, w_l[..., 2],
        w_r[..., 0], w_r[..., 1], zeros, w_r[..., 2], gamma)
    flux = np.stack([f_rho, f_mn, f_e], axis=-1)      # (n+1, 3)
    return -(flux[1:] - flux[:-1]) / float(dx)


def run_1d_transient(U0, dx, gamma, t_end, cfl=0.8, second_order=True):
    """Zaman-doğru 1B koşum: SSP-RK2, global Δt (CFL), t_end'e tam varış."""
    U = np.array(U0, dtype=float, copy=True)
    g = float(gamma)
    t = 0.0
    t_end = float(t_end)
    while t < t_end:
        rho, u, p = cons_to_prim_1d(U, g)
        a = np.sqrt(g * p / rho)
        dt = float(cfl) * float(dx) / float(np.max(np.abs(u) + a))
        dt = min(dt, t_end - t)
        u1 = U + dt * residual_1d(U, dx, g, second_order)
        U = 0.5 * (U + u1 + dt * residual_1d(u1, dx, g, second_order))
        if not np.all(np.isfinite(U)):
            raise FloatingPointError(
                f'1B çekirdek t={t:.5f} adımında fiziksel olmayan duruma '
                f'düştü (NaN/Inf) — kırpma yok, dürüst hata.')
        t += dt
    return U


# --------------------------------------------------------------------------
# 2B eksenel simetrik sınır durumları
# --------------------------------------------------------------------------

def inlet_state_from_stagnation(w_int, gamma, R, P0, T0):
    """Rezervuar giriş hayalet durumu (ses-altı karakteristik, beyan yukarıda).

    w_int: iç ilk hücre primitifleri (nj, 4). Döner: (nj, 4) hayalet
    primitif — eksenel akış, izantropik (P0, T0) hattı üstünde, statik
    basınç içeriden.
    """
    g = float(gamma)
    p_sonic = float(P0) * (2.0 / (g + 1.0)) ** (g / (g - 1.0))
    p = np.clip(w_int[..., 3], p_sonic, float(P0) * (1.0 - 1e-12))
    mach = np.sqrt(2.0 / (g - 1.0)
                   * ((float(P0) / p) ** ((g - 1.0) / g) - 1.0))
    temp = float(T0) / (1.0 + 0.5 * (g - 1.0) * mach * mach)
    rho = p / (float(R) * temp)
    uz = mach * np.sqrt(g * float(R) * temp)
    out = np.empty_like(w_int)
    out[..., 0] = rho
    out[..., 1] = uz
    out[..., 2] = 0.0
    out[..., 3] = p
    return out


def _outlet_state(w_int, n_hat, gamma, Pb):
    """Çıkış hayaleti: normal Mach >= 1 → dışdeğerleme; ses-altı ve Pb
    verildiyse statik basınç Pb (gerisi dışdeğer)."""
    out = np.array(w_int, copy=True)
    if Pb is None:
        return out
    g = float(gamma)
    a = np.sqrt(g * w_int[..., 3] / w_int[..., 0])
    un = w_int[..., 1] * n_hat[..., 0] + w_int[..., 2] * n_hat[..., 1]
    subsonic = un / a < 1.0
    out[..., 3] = np.where(subsonic, float(Pb), out[..., 3])
    return out


def _mirror_axis(w_cells):
    """Eksen aynası: ρ, u_z, p çift; u_r tek (işaret değiştirir)."""
    out = np.array(w_cells, copy=True)
    out[..., 2] = -out[..., 2]
    return out


def _mirror_wall(w_cells, n_hat):
    """Kayma duvarı aynası: hız, duvar normaline göre yansıtılır."""
    out = np.array(w_cells, copy=True)
    vn = (w_cells[..., 1] * n_hat[..., 0]
          + w_cells[..., 2] * n_hat[..., 1])
    out[..., 1] = w_cells[..., 1] - 2.0 * vn * n_hat[..., 0]
    out[..., 2] = w_cells[..., 2] - 2.0 * vn * n_hat[..., 1]
    return out


def _unit_normals(face_vec):
    """Yüzey vektörlerinden (birim normal, alan) — sıfır alanlı yüz
    (eksen) güvenli: normal (0,1) atanır, akı zaten alanla çarpılıp
    sıfırlanır."""
    area = np.linalg.norm(face_vec, axis=-1)
    safe = np.where(area > 0.0, area, 1.0)[..., None]
    n_hat = face_vec / safe
    n_hat = np.where(area[..., None] > 0.0, n_hat,
                     np.array([0.0, 1.0]))
    return n_hat, area


def _directional_flux(w_l, w_r, n_hat, area, gamma):
    """Yüzey-normal çerçevesine döndür, HLLC çağır, geri çevir, alanla çarp.

    Döner: (n_face..., 4) — [kütle, z-momentum, r-momentum, enerji] akıları
    (gerçek birim: kg/s, N, W; alan 2π'yi içerir).
    """
    nz = n_hat[..., 0]
    nr = n_hat[..., 1]
    un_l = w_l[..., 1] * nz + w_l[..., 2] * nr
    ut_l = -w_l[..., 1] * nr + w_l[..., 2] * nz
    un_r = w_r[..., 1] * nz + w_r[..., 2] * nr
    ut_r = -w_r[..., 1] * nr + w_r[..., 2] * nz
    f_rho, f_mn, f_mt, f_e = hllc_flux(
        w_l[..., 0], un_l, ut_l, w_l[..., 3],
        w_r[..., 0], un_r, ut_r, w_r[..., 3], gamma)
    fz = f_mn * nz - f_mt * nr
    fr = f_mn * nr + f_mt * nz
    return np.stack([f_rho, fz, fr, f_e], axis=-1) * area[..., None]


# --------------------------------------------------------------------------
# 2B eksenel simetrik kalıntı
# --------------------------------------------------------------------------

def residual_axisym(U, grid, gamma, R, P0, T0, Pb=None, second_order=True,
                    slopes=None, return_slopes=False):
    """dU/dt kalıntısı ve akı bütçesi.

    Args:
        U: (ni, nj, 4) korunum durumu [ρ, ρu_z, ρu_r, E].
        grid: AxisymGrid (grid_axisym).
        gamma, R: gaz modeli (kalorik mükemmel; çağıran motor çözücüsünden
            getirir, burada varsayılan YOK).
        P0, T0: rezervuar giriş koşulu [Pa, K].
        Pb: geri basınç [Pa] veya None (tam dışdeğerleme çıkışı).
        second_order: MUSCL açık/kapalı (mertebe testi bunu kanıtlar).
        slopes: None → minmod eğimleri hesaplanır; (s_i, s_j) → verilen
            DONMUŞ eğimler kullanılır (steady.py sınırlayıcı dondurması:
            minmod salınımı kararlı-hâl kalıntısını platoda bırakır; plato
            tespitinde eğimler dondurulur — kararlı-hâl pratiğinde standart,
            Venkatakrishnan, AIAA J. 33(5), 1995 gerekçesi. Dondurma anı
            sürücü çıktısında BEYAN edilir).
        return_slopes: True → (dUdt, aux, (s_i, s_j)) döndürür (dondurma
            anında sürücünün eğimleri alması için).

    Returns:
        (dUdt, aux[, slopes]): dUdt (ni, nj, 4) [birim/s]; aux sözlüğü
        giriş/çıkış kütle ve enerji akıları (bütçe beyanı için).

    KAYMA DUVARI AKISI (ayrık hava geçirmezlik): duvar yüzünde sağ durum,
    sol REKONSTRÜKTE durumun duvar normaline göre aynasıdır (hayaletin ayrı
    rekonstrüksiyonu değil — ayna ile bileşen-bazlı minmod yer değiştirmez
    ve O(h²) kütle sızıntısı doğurur; ölçüldü). Simetrik Riemann probleminde
    S* = 0 ve kütle/enerji/teğet momentum akısı ANALİTİK olarak tam sıfırdır;
    ulp artıklarını da kapatmak için akı [0, p*·n̂·|S|, 0] olarak kurulur
    (Euler kayma duvarının fiziksel akısı budur; korunum bütçesi bekçisi
    tests/cfd/test_korunum.py bunu doğrular).
    """
    g = float(gamma)
    w = cons_to_prim_axisym(U, g)
    s_i_given, s_j_given = slopes if slopes is not None else (None, None)

    # ---- i yönü (eksenel) ----
    w_in = inlet_state_from_stagnation(w[0], g, R, P0, T0)      # (nj, 4)
    n_out_hat, _ = _unit_normals(grid.face_i[-1])               # (nj, 2)
    w_out = _outlet_state(w[-1], n_out_hat, g, Pb)
    w_ext_i = np.concatenate([w_in[None], w_in[None], w,
                              w_out[None], w_out[None]], axis=0)
    if s_i_given is not None:
        s_i = s_i_given
    else:
        s_i = limited_slopes(w_ext_i) if second_order else None
    w_l, w_r = _edge_states(w_ext_i, s_i)
    n_hat_i, area_i = _unit_normals(grid.face_i)
    flux_i = _directional_flux(w_l, w_r, n_hat_i, area_i, g)    # (ni+1,nj,4)

    # ---- j yönü (radyal) ----
    wall_n_hat, _ = _unit_normals(grid.face_j[:, -1])           # (ni, 2)
    w_axis1 = _mirror_axis(w[:, 0])
    w_axis2 = _mirror_axis(w[:, 1])
    w_wall1 = _mirror_wall(w[:, -1], wall_n_hat)
    w_wall2 = _mirror_wall(w[:, -2], wall_n_hat)
    w_ext_j = np.moveaxis(np.concatenate(
        [w_axis2[:, None], w_axis1[:, None], w,
         w_wall1[:, None], w_wall2[:, None]], axis=1), 1, 0)
    if s_j_given is not None:
        s_j = s_j_given
    else:
        s_j = limited_slopes(w_ext_j) if second_order else None
    w_l_j, w_r_j = _edge_states(w_ext_j, s_j)
    w_l_j = np.moveaxis(w_l_j, 0, 1)
    w_r_j = np.moveaxis(w_r_j, 0, 1)
    n_hat_j, area_j = _unit_normals(grid.face_j)
    flux_j = _directional_flux(w_l_j, w_r_j, n_hat_j, area_j, g)

    # ---- kayma duvarı: analitik hava geçirmez akı (docstring beyanı) ----
    w_lw = w_l_j[:, -1, :]
    nz_w = wall_n_hat[..., 0]
    nr_w = wall_n_hat[..., 1]
    un_lw = w_lw[..., 1] * nz_w + w_lw[..., 2] * nr_w
    ut_lw = -w_lw[..., 1] * nr_w + w_lw[..., 2] * nz_w
    _, f_mn_w, _, _ = hllc_flux(
        w_lw[..., 0], un_lw, ut_lw, w_lw[..., 3],
        w_lw[..., 0], -un_lw, ut_lw, w_lw[..., 3], g)
    area_w = area_j[:, -1]
    flux_j[:, -1, 0] = 0.0
    flux_j[:, -1, 1] = f_mn_w * nz_w * area_w
    flux_j[:, -1, 2] = f_mn_w * nr_w * area_w
    flux_j[:, -1, 3] = 0.0

    # ---- toplama + eksenel simetri kaynak terimi ----
    net = -(flux_i[1:] - flux_i[:-1]) - (flux_j[:, 1:] - flux_j[:, :-1])
    net[..., 2] += w[..., 3] * _TWO_PI * grid.area_planar
    dudt = net / grid.volume[..., None]

    aux = {
        'mass_flow_in_kg_s': float(np.sum(flux_i[0, :, 0])),
        'mass_flow_out_kg_s': float(np.sum(flux_i[-1, :, 0])),
        'energy_flux_in_W': float(np.sum(flux_i[0, :, 3])),
        'energy_flux_out_W': float(np.sum(flux_i[-1, :, 3])),
        'wall_mass_flux_kg_s': float(np.sum(flux_j[:, -1, 0])),
    }
    if return_slopes:
        return dudt, aux, (s_i, s_j)
    return dudt, aux


def local_dt_axisym(U, grid, gamma, cfl, area_i=None, area_j=None):
    """Yerel zaman adımı: Δt_c = CFL·V / Σ_yüzey (|u·n̂| + a)·|S|.

    area_i/area_j önceden hesaplanmış yüzey alanları (sürücü döngüde bir
    kez hesaplayıp geçirir; None ise burada hesaplanır).
    """
    g = float(gamma)
    w = cons_to_prim_axisym(U, g)
    a = np.sqrt(g * w[..., 3] / w[..., 0])
    if area_i is None:
        area_i = np.linalg.norm(grid.face_i, axis=-1)
    if area_j is None:
        area_j = np.linalg.norm(grid.face_j, axis=-1)
    # |u·S| yüz vektörüyle, a·|S| alanla — hücre değerleri yüzlere atanır
    uz = w[..., 1]
    ur = w[..., 2]

    def face_speed(face_vec, face_area):
        return np.abs(uz * face_vec[..., 0] + ur * face_vec[..., 1]) \
            + a * face_area

    spectral = (face_speed(grid.face_i[:-1], area_i[:-1])
                + face_speed(grid.face_i[1:], area_i[1:])
                + face_speed(grid.face_j[:, :-1], area_j[:, :-1])
                + face_speed(grid.face_j[:, 1:], area_j[:, 1:]))
    return float(cfl) * grid.volume / spectral
