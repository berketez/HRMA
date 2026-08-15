# hrma/cfd — HLLC yaklaşık Riemann çözücüsü (v3 CFD, Aşama 1A)
"""
HLLC (Harten-Lax-van Leer-Contact) yaklaşık Riemann akısı — saf fonksiyon,
N kenar birden (vektörize), yüzey-normal çerçevesinde.

KAYNAK VE VARYANT BEYANI
------------------------
Akı yapısı: Toro, "Riemann Solvers and Numerical Methods for Fluid
Dynamics", 3. baskı (2009), §10.4:
    ara dalga hızı S*      : Eş. 10.37
    star bölge durumları   : Eş. 10.39 (U*_K)
    akı seçimi             : Eş. 10.26 (F = F_K + S_K (U*_K − U_K))
Dalga hızı kestirimi: Einfeldt tipi, Roe-ortalamalı sınırlar (Toro §10.5.1,
Eş. 10.49-10.54; B. Einfeldt, "On Godunov-type methods for gas dynamics",
SIAM J. Numer. Anal. 25(2), 1988):
    S_L = min(u_L − a_L,  ũ − ã),   S_R = max(u_R + a_R,  ũ + ã)
ũ ve ã Roe ortalamalarıdır (√ρ ağırlıklı hız ve toplam entalpi; ã² =
(γ−1)(H̃ − q̃²/2), q̃² teğetsel bileşeni de içerir). Bu seçim tek başına
sol/sağ ses hızlarından daha sağlam alt/üst sınır verir (Toro §10.5.1
tavsiyesi) ve pozitiflik açısından doğrudan basınç-tabanlı PVRS kestirimine
tercih edilmiştir.

ÇERÇEVE
-------
Girdi durumları yüzey-normal çerçevesindedir: un = u·n̂ (normal bileşen),
ut = teğet bileşen (1B problemde 0 geçilir ve teğet akı yok sayılır).
Teğet hız HLLC'de temas dalgası boyunca pasif taşınır (Toro §10.4, çok
boyutlu genişleme). Döndürme/çevirme İŞLEMLERİ çağıranın işidir
(euler_core); bu modül koordinat sisteminden habersizdir.

Kalorik olarak mükemmel gaz: E = p/(γ−1) + ρ(un²+ut²)/2. Uydurma taban
(floor) sabiti YOKTUR: negatif basınç/yoğunluk üreten girdi burada
maskelenmez, NaN üretir ve sürücü katmanı bunu ıraksama olarak DÜRÜSTÇE
raporlar (sahte kararlılık yasak).
"""

import numpy as np

__all__ = ['hllc_flux']


def hllc_flux(rho_l, un_l, ut_l, p_l, rho_r, un_r, ut_r, p_r, gamma):
    """N kenar için HLLC akısı — yüzey-normal çerçevesinde, vektörize.

    Args:
        rho_l, un_l, ut_l, p_l: Sol durum dizileri (yoğunluk [kg/m³],
            normal hız [m/s], teğet hız [m/s], basınç [Pa]). Aynı şekilli
            numpy dizileri (veya skaler).
        rho_r, un_r, ut_r, p_r: Sağ durum dizileri (aynı şekil).
        gamma: İzantropik üs (skaler, kalorik mükemmel gaz).

    Returns:
        (f_rho, f_mn, f_mt, f_e): Korunum değişkeni akıları
        [ρ, ρ·un, ρ·ut, E] için, girdiyle aynı şekilli diziler.
        1B kullanımda ut'ler 0 geçilir, f_mt yok sayılır.
    """
    g = float(gamma)
    rho_l = np.asarray(rho_l, dtype=float)
    un_l = np.asarray(un_l, dtype=float)
    ut_l = np.asarray(ut_l, dtype=float)
    p_l = np.asarray(p_l, dtype=float)
    rho_r = np.asarray(rho_r, dtype=float)
    un_r = np.asarray(un_r, dtype=float)
    ut_r = np.asarray(ut_r, dtype=float)
    p_r = np.asarray(p_r, dtype=float)

    # Ses hızları ve korunum/energetik büyüklükler
    a_l = np.sqrt(g * p_l / rho_l)
    a_r = np.sqrt(g * p_r / rho_r)
    e_l = p_l / (g - 1.0) + 0.5 * rho_l * (un_l * un_l + ut_l * ut_l)
    e_r = p_r / (g - 1.0) + 0.5 * rho_r * (un_r * un_r + ut_r * ut_r)
    h_l = (e_l + p_l) / rho_l          # toplam entalpi
    h_r = (e_r + p_r) / rho_r

    # Roe ortalamaları (Toro §10.5.1)
    sq_l = np.sqrt(rho_l)
    sq_r = np.sqrt(rho_r)
    inv = 1.0 / (sq_l + sq_r)
    un_roe = (sq_l * un_l + sq_r * un_r) * inv
    ut_roe = (sq_l * ut_l + sq_r * ut_r) * inv
    h_roe = (sq_l * h_l + sq_r * h_r) * inv
    a_roe_sq = (g - 1.0) * (h_roe - 0.5 * (un_roe * un_roe
                                           + ut_roe * ut_roe))
    a_roe = np.sqrt(np.maximum(a_roe_sq, 0.0))

    # Einfeldt/Roe dalga hızı sınırları (Eş. 10.52-10.54)
    s_l = np.minimum(un_l - a_l, un_roe - a_roe)
    s_r = np.maximum(un_r + a_r, un_roe + a_roe)

    # Ara dalga hızı S* (Eş. 10.37)
    dl = rho_l * (s_l - un_l)
    dr = rho_r * (s_r - un_r)
    s_star = (p_r - p_l + un_l * dl - un_r * dr) / (dl - dr)

    # Fiziksel akılar F(U_K)
    f_rho_l = rho_l * un_l
    f_mn_l = rho_l * un_l * un_l + p_l
    f_mt_l = rho_l * un_l * ut_l
    f_e_l = (e_l + p_l) * un_l
    f_rho_r = rho_r * un_r
    f_mn_r = rho_r * un_r * un_r + p_r
    f_mt_r = rho_r * un_r * ut_r
    f_e_r = (e_r + p_r) * un_r

    # Star bölge durumları U*_K (Eş. 10.39) ve F*_K = F_K + S_K (U*_K − U_K)
    def star_flux(rho_k, un_k, ut_k, p_k, e_k, s_k,
                  f_rho_k, f_mn_k, f_mt_k, f_e_k):
        denom = s_k - s_star
        # s_k == s_star yalnız dejenere (sıfır genişlikli star) hâlde olur;
        # o kenarların akısı zaten maskeyle K tarafından seçilir. Bölme
        # uyarısını önlemek için güvenli payda kullanılır, sonuç maskede
        # kullanılmaz.
        safe = np.where(np.abs(denom) < 1e-300, 1.0, denom)
        coef = rho_k * (s_k - un_k) / safe
        u_star_rho = coef
        u_star_mn = coef * s_star
        u_star_mt = coef * ut_k
        u_star_e = coef * (e_k / rho_k + (s_star - un_k)
                           * (s_star + p_k / (rho_k * (s_k - un_k))))
        f_rho = f_rho_k + s_k * (u_star_rho - rho_k)
        f_mn = f_mn_k + s_k * (u_star_mn - rho_k * un_k)
        f_mt = f_mt_k + s_k * (u_star_mt - rho_k * ut_k)
        f_e = f_e_k + s_k * (u_star_e - e_k)
        return f_rho, f_mn, f_mt, f_e

    fs_rho_l, fs_mn_l, fs_mt_l, fs_e_l = star_flux(
        rho_l, un_l, ut_l, p_l, e_l, s_l, f_rho_l, f_mn_l, f_mt_l, f_e_l)
    fs_rho_r, fs_mn_r, fs_mt_r, fs_e_r = star_flux(
        rho_r, un_r, ut_r, p_r, e_r, s_r, f_rho_r, f_mn_r, f_mt_r, f_e_r)

    # Akı seçimi (Eş. 10.26): x/t = 0 hangi dalga kolundaysa o akı
    cond_l = s_l >= 0.0            # tüm dalgalar sağa: F_L
    cond_sl = (s_l < 0.0) & (s_star >= 0.0)   # sol star kolu
    cond_sr = (s_star < 0.0) & (s_r >= 0.0)   # sağ star kolu
    # kalan: s_r < 0, tüm dalgalar sola: F_R

    def pick(fl, fsl, fsr, fr):
        return np.where(cond_l, fl,
                        np.where(cond_sl, fsl,
                                 np.where(cond_sr, fsr, fr)))

    return (pick(f_rho_l, fs_rho_l, fs_rho_r, f_rho_r),
            pick(f_mn_l, fs_mn_l, fs_mn_r, f_mn_r),
            pick(f_mt_l, fs_mt_l, fs_mt_r, f_mt_r),
            pick(f_e_l, fs_e_l, fs_e_r, f_e_r))
