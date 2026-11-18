"""Tank geometrisi testleri için analitik yüzey örnekleyicisi (test altyapısı).

Dönel yüzey profili (r, z) çoklu çizgisinden ALAN DÜZGÜN nokta örnekler:
parça seçimi parça alanıyla (π (r_a + r_b) L) orantılı, parça içinde konum
r ile orantılı yoğunluktan (ters CDF), azimut düzgün. Tohumlu üreteç;
aynı tohum aynı bulutu verir. Ürün koduna girmez.
"""

import math

import numpy as np


def silindir_duz(R, H):
    return np.array([[0.0, 0.0], [R, 0.0], [R, H], [0.0, H]])


def kure(R, n=720):
    t = np.linspace(0.0, math.pi, n + 1)
    p = np.stack([R * np.sin(t), R * (1.0 - np.cos(t))], axis=1)
    p[0, 0] = 0.0
    p[-1, 0] = 0.0
    return p


def kubbeli_silindir(R, L, n=360):
    """Yarım küre alt ve üst başlı silindir: toplam yükseklik L + 2R."""
    t = np.linspace(0.0, 0.5 * math.pi, n + 1)
    alt = np.stack([R * np.sin(t), R * (1.0 - np.cos(t))], axis=1)
    ust = np.stack([R * np.cos(t), R + L + R * np.sin(t)], axis=1)
    p = np.concatenate([alt, ust])
    p[0, 0] = 0.0
    p[-1, 0] = 0.0
    return p


def ornekle(profil, n, tohum=0, eps_cos2=0.0, gurultu=0.0, donus=None,
            oteleme=(0.0, 0.0, 0.0)):
    """Profilin döndürülmesiyle oluşan yüzeyden n nokta (z ekseni etrafında).

    eps_cos2: r → r (1 + ε cos 2θ) eliptik bozulma; gurultu: her koordinata
    eklenen N(0, σ²); donus: 3×3 dönme matrisi; oteleme: öteleme.
    """
    rng = np.random.default_rng(tohum)
    p = np.asarray(profil, float)
    ra, za, rb, zb = p[:-1, 0], p[:-1, 1], p[1:, 0], p[1:, 1]
    L = np.hypot(rb - ra, zb - za)
    alan = math.pi * (ra + rb) * L
    sec = rng.choice(alan.size, size=n, p=alan / alan.sum())
    u = rng.random(n)
    r_a, r_b = ra[sec], rb[sec]
    d = r_b - r_a
    esit = np.abs(d) < 1e-15
    r = np.where(esit, r_a, np.sqrt(r_a ** 2 + u * (r_b ** 2 - r_a ** 2)))
    t = np.where(esit, u, (r - r_a) / np.where(esit, 1.0, d))
    z = za[sec] + t * (zb[sec] - za[sec])
    th = rng.random(n) * 2.0 * math.pi
    r = r * (1.0 + eps_cos2 * np.cos(2.0 * th))
    P = np.stack([r * np.cos(th), r * np.sin(th), z], axis=1)
    if gurultu:
        P = P + rng.normal(0.0, gurultu, size=P.shape)
    if donus is not None:
        P = P @ np.asarray(donus).T
    return P + np.asarray(oteleme)


def donme(ax, ay):
    """x etrafında ax, sonra y etrafında ay radyan dönme matrisi."""
    cx, sx, cy, sy = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    return Ry @ Rx


def kure_ucgen_agi(R, n_enlem=24, n_boylam=48):
    """UV küre üçgen ağı (dışa yönelimli, kapalı, kutuplar tek düğüm)."""
    nokta = [[0.0, 0.0, -R]]
    for i in range(1, n_enlem):
        t = math.pi * i / n_enlem
        for j in range(n_boylam):
            f = 2.0 * math.pi * j / n_boylam
            nokta.append([R * math.sin(t) * math.cos(f),
                          R * math.sin(t) * math.sin(f), -R * math.cos(t)])
    nokta.append([0.0, 0.0, R])
    P = np.array(nokta)
    ucgen = []

    def v(i, j):
        return 1 + (i - 1) * n_boylam + (j % n_boylam)
    for j in range(n_boylam):
        ucgen.append((0, v(1, j + 1), v(1, j)))
    for i in range(1, n_enlem - 1):
        for j in range(n_boylam):
            a, b = v(i, j), v(i, j + 1)
            c, d = v(i + 1, j), v(i + 1, j + 1)
            ucgen.append((a, b, d))
            ucgen.append((a, d, c))
    son = P.shape[0] - 1
    for j in range(n_boylam):
        ucgen.append((son, v(n_enlem - 1, j), v(n_enlem - 1, j + 1)))
    return P, np.array(ucgen, dtype=np.int64)


def ornekle_tabakali(profil, n_u, n_v, tohum=0, eps_cos2=0.0):
    """Tabakalı alan düzgün örnekleme: alan CDF'i n_u, azimut n_v tabaka;
    her tabakada tek nokta (seyrek dosya fikstürlerinde boş hücre olmaz)."""
    rng = np.random.default_rng(tohum)
    p = np.asarray(profil, float)
    ra, za, rb, zb = p[:-1, 0], p[:-1, 1], p[1:, 0], p[1:, 1]
    L = np.hypot(rb - ra, zb - za)
    alan = math.pi * (ra + rb) * L
    birikimli = np.concatenate(([0.0], np.cumsum(alan)))
    A = birikimli[-1]
    iu, iv = np.meshgrid(np.arange(n_u), np.arange(n_v), indexing='ij')
    u = (iu.ravel() + rng.random(iu.size)) / n_u * A
    th = (iv.ravel() + rng.random(iv.size)) / n_v * 2.0 * math.pi
    k = np.clip(np.searchsorted(birikimli, u, side='right') - 1, 0,
                alan.size - 1)
    w = np.clip((u - birikimli[k]) / np.where(alan[k] > 0, alan[k], 1.0),
                0.0, 1.0)
    r_a, r_b = ra[k], rb[k]
    d = r_b - r_a
    esit = np.abs(d) < 1e-15
    r = np.where(esit, r_a, np.sqrt(r_a ** 2 + w * (r_b ** 2 - r_a ** 2)))
    t = np.where(esit, w, (r - r_a) / np.where(esit, 1.0, d))
    z = za[k] + t * (zb[k] - za[k])
    r = r * (1.0 + eps_cos2 * np.cos(2.0 * th))
    return np.stack([r * np.cos(th), r * np.sin(th), z], axis=1)
