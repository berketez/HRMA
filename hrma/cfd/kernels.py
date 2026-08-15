# hrma/cfd — isteğe bağlı numba arka ucu (yönlü HLLC çekirdeği)
"""
Yönlü (döndür → HLLC → geri döndür → alanla çarp) akı hesabının numba ile
derlenmiş ÇEKİRDEĞİ — İSTEĞE BAĞLI hızlandırma katmanı (Aşama 1B
performans turu; tasarım belgesi §5: NumPy → ölç → numba merdiveni).

SÖZLEŞME (dürüstlük):
- numba ZORUNLU BAĞIMLILIK DEĞİLDİR: içe aktarılamazsa saf NumPy yolu
  (euler_core._directional_flux_numpy → riemann.hllc_flux) aynen çalışır ve
  arka uç steady.solve_steady_axisym çıktısında BEYAN edilir
  ('kernel_backend' alanı). requirements dosyalarına numba EKLENMEZ.
- HRMA_CFD_DISABLE_NUMBA=1 ortam değişkeni numba kurulu olsa da NumPy
  yolunu zorlar (arka uç eşdeğerlik bekçisi bunu kullanır:
  tests/cfd/test_performans.py).
- Aritmetik, riemann.hllc_flux ile AYNI işlem sırasıyla skaler yazılmıştır;
  fastmath KAPALIDIR (yeniden birleştirme/fma yok). Eşdeğerlik bekçisi iki
  yolun akısını karşılaştırır; ölçülen fark raporda (bit sınıfı).
- Sod (1B) yolu ve duvar akısı özel durumu her zaman saf NumPy
  hllc_flux'tadır: doğrulama merdiveninin referans yolu derlenmiş koda
  taşınmaz (yalnız 2B alan-içi yönlü akı hızlandırılır).
"""

import os

import numpy as np

__all__ = ['NUMBA_AVAILABLE', 'NUMBA_DISABLED_BY_ENV', 'directional_hllc']

NUMBA_DISABLED_BY_ENV = os.environ.get('HRMA_CFD_DISABLE_NUMBA', '') == '1'
NUMBA_AVAILABLE = False

if not NUMBA_DISABLED_BY_ENV:
    try:
        from numba import njit, prange
        NUMBA_AVAILABLE = True
    except ImportError:            # numba yok → NumPy yolu (beyanlı)
        NUMBA_AVAILABLE = False


if NUMBA_AVAILABLE:

    @njit(cache=True, parallel=True, fastmath=False)
    def _directional_hllc_kernel(rho_l, uz_l, ur_l, p_l,
                                 rho_r, uz_r, ur_r, p_r,
                                 nz, nr, area, g, out):
        """Yüz başına skaler HLLC — riemann.hllc_flux ile aynı işlem sırası.

        Girdiler düzleştirilmiş (n,) dizilerdir; out (n, 4) yazılır:
        [kütle, z-momentum, r-momentum, enerji] × alan (2π dahil).
        """
        n = rho_l.shape[0]
        for k in prange(n):
            nzk = nz[k]
            nrk = nr[k]
            # Döndürme (euler_core._directional_flux ile aynı)
            un_l = uz_l[k] * nzk + ur_l[k] * nrk
            ut_l = -uz_l[k] * nrk + ur_l[k] * nzk
            un_r = uz_r[k] * nzk + ur_r[k] * nrk
            ut_r = -uz_r[k] * nrk + ur_r[k] * nzk
            rl = rho_l[k]
            rr = rho_r[k]
            pl = p_l[k]
            pr = p_r[k]

            # Ses hızları, enerji, toplam entalpi (riemann.hllc_flux sırası)
            a_l = np.sqrt(g * pl / rl)
            a_r = np.sqrt(g * pr / rr)
            e_l = pl / (g - 1.0) + 0.5 * rl * (un_l * un_l + ut_l * ut_l)
            e_r = pr / (g - 1.0) + 0.5 * rr * (un_r * un_r + ut_r * ut_r)
            h_l = (e_l + pl) / rl
            h_r = (e_r + pr) / rr

            # Roe ortalamaları
            sq_l = np.sqrt(rl)
            sq_r = np.sqrt(rr)
            inv = 1.0 / (sq_l + sq_r)
            un_roe = (sq_l * un_l + sq_r * un_r) * inv
            ut_roe = (sq_l * ut_l + sq_r * ut_r) * inv
            h_roe = (sq_l * h_l + sq_r * h_r) * inv
            a_roe_sq = (g - 1.0) * (h_roe - 0.5 * (un_roe * un_roe
                                                   + ut_roe * ut_roe))
            a_roe = np.sqrt(max(a_roe_sq, 0.0))

            # Einfeldt/Roe dalga hızı sınırları
            s_l = min(un_l - a_l, un_roe - a_roe)
            s_r = max(un_r + a_r, un_roe + a_roe)

            # Ara dalga hızı S*
            dl = rl * (s_l - un_l)
            dr = rr * (s_r - un_r)
            s_star = (pr - pl + un_l * dl - un_r * dr) / (dl - dr)

            # Akı seçimi (riemann.hllc_flux'un maske ağacıyla aynı dallar;
            # NaN karşılaştırmaları False → F_R dalı, np.where ile özdeş)
            if s_l >= 0.0:
                f_rho = rl * un_l
                f_mn = rl * un_l * un_l + pl
                f_mt = rl * un_l * ut_l
                f_e = (e_l + pl) * un_l
            elif (s_l < 0.0) and (s_star >= 0.0):
                f_rho_l = rl * un_l
                f_mn_l = rl * un_l * un_l + pl
                f_mt_l = rl * un_l * ut_l
                f_e_l = (e_l + pl) * un_l
                denom = s_l - s_star
                safe = 1.0 if abs(denom) < 1e-300 else denom
                coef = rl * (s_l - un_l) / safe
                u_star_e = coef * (e_l / rl + (s_star - un_l)
                                   * (s_star + pl / (rl * (s_l - un_l))))
                f_rho = f_rho_l + s_l * (coef - rl)
                f_mn = f_mn_l + s_l * (coef * s_star - rl * un_l)
                f_mt = f_mt_l + s_l * (coef * ut_l - rl * ut_l)
                f_e = f_e_l + s_l * (u_star_e - e_l)
            elif (s_star < 0.0) and (s_r >= 0.0):
                f_rho_r = rr * un_r
                f_mn_r = rr * un_r * un_r + pr
                f_mt_r = rr * un_r * ut_r
                f_e_r = (e_r + pr) * un_r
                denom = s_r - s_star
                safe = 1.0 if abs(denom) < 1e-300 else denom
                coef = rr * (s_r - un_r) / safe
                u_star_e = coef * (e_r / rr + (s_star - un_r)
                                   * (s_star + pr / (rr * (s_r - un_r))))
                f_rho = f_rho_r + s_r * (coef - rr)
                f_mn = f_mn_r + s_r * (coef * s_star - rr * un_r)
                f_mt = f_mt_r + s_r * (coef * ut_r - rr * ut_r)
                f_e = f_e_r + s_r * (u_star_e - e_r)
            else:
                f_rho = rr * un_r
                f_mn = rr * un_r * un_r + pr
                f_mt = rr * un_r * ut_r
                f_e = (e_r + pr) * un_r

            # Geri döndürme + alan (euler_core._directional_flux sırası)
            ar = area[k]
            out[k, 0] = f_rho * ar
            out[k, 1] = (f_mn * nzk - f_mt * nrk) * ar
            out[k, 2] = (f_mn * nrk + f_mt * nzk) * ar
            out[k, 3] = f_e * ar


def directional_hllc(w_l, w_r, n_hat, area, gamma):
    """Numba çekirdeğine düzleştirilmiş sarmalayıcı.

    Girdi/çıktı sözleşmesi euler_core._directional_flux ile aynıdır:
    w_l/w_r (..., 4) primitif, n_hat (..., 2), area (...) →
    akı (..., 4). NUMBA_AVAILABLE=False iken ÇAĞRILMAMALIDIR (çağıran
    euler_core seçer; burada içe aktarma hatası gizlenmez).
    """
    shp = np.shape(area)
    n = int(np.prod(shp)) if shp else 1
    flat = (n,)
    out = np.empty((n, 4))
    _directional_hllc_kernel(
        np.ascontiguousarray(w_l[..., 0]).reshape(flat),
        np.ascontiguousarray(w_l[..., 1]).reshape(flat),
        np.ascontiguousarray(w_l[..., 2]).reshape(flat),
        np.ascontiguousarray(w_l[..., 3]).reshape(flat),
        np.ascontiguousarray(w_r[..., 0]).reshape(flat),
        np.ascontiguousarray(w_r[..., 1]).reshape(flat),
        np.ascontiguousarray(w_r[..., 2]).reshape(flat),
        np.ascontiguousarray(w_r[..., 3]).reshape(flat),
        np.ascontiguousarray(n_hat[..., 0]).reshape(flat),
        np.ascontiguousarray(n_hat[..., 1]).reshape(flat),
        np.ascontiguousarray(area).reshape(flat),
        float(gamma), out)
    return out.reshape(shp + (4,))
