# hrma/cfd — kontur → yapısal H-tipi eksenel simetrik ızgara + metrikler
"""
Lüle iç konturundan (z, r) düzleminde yapısal H-tipi ızgara üretir ve
sonlu-hacim metriklerini GERÇEK dönel geometriden hesaplar.

GEOMETRİK SÖZLEŞME (seri açılım YOK, tam formüller)
---------------------------------------------------
Hücre (i,j) köşeleri saat yönünün tersine (CCW) sıralı düzlem dörtgendir.
- Düzlemsel alan: ayakkabı bağı (shoelace) formülü — düz kenarlı çokgen
  için TAM.
- Dönel hacim: V = 2π ∫∫ r dA; ∫∫ r dA çokgen birinci momenti
  (1/6)·Σ (r_i + r_{i+1})(z_i r_{i+1} − z_{i+1} r_i) ile TAM hesaplanır
  (Pappus; düz kenarlı çokgen için kapalı formül).
- Yüzey vektörü: düz doğru parçasının dönel yüzeyi için
  S = 2π · r_orta · (Δr, −Δz) yönlendirilmiş alan TAMDIR
  (∫ r dl = r_orta·L, kesik koni yanal alanı π(r_a+r_b)·L özdeşliği).

KAPANIŞ ÖZDEŞLİĞİ (test_grid.py sözleşmesi): kapalı hücre çevresinde
    Σ S_z = 2π·Σ Δr·r_orta = π·Σ(r_b²−r_a²) = 0            (teleskopik, tam)
    Σ S_r = −2π·Σ Δz·r_orta = 2π·A_düzlem                   (Green, tam)
İkincisi, eksenel simetrik basınç kaynak teriminin (p·2π·A_düzlem,
r-momentum) serbest akımı TAM korumasının geometrik yarısıdır.

Eksen r=0 bir sınır koşulu değil geometrik gerçektir: j=0 yüzlerinin
r_orta=0 olduğundan alanı sıfırdır (akısız); eksene komşu hücre hacimleri
pozitiftir; hiçbir yerde r'ye bölme yoktur (0/0 muamelesi geometrik).

Yön kuralı: i ekseni +z (akış yönü), j ekseni +r. face_i[i,j] (i,j)-(i,j+1)
köşe doğrusu üstünde +i yönlü; face_j[i,j] (i,j)-(i+1,j) üstünde +j yönlü.

Aşama 1: radyal dağılım DÜZGÜN (tasarım belgesi §3; duvara sıkıştırma
Aşama 2 sınır tabakası hazırlığıdır).
"""

from dataclasses import dataclass, field

import numpy as np

__all__ = ['AxisymGrid', 'build_grid_from_wall', 'build_nozzle_grid']

_TWO_PI = 2.0 * np.pi


@dataclass(frozen=True)
class AxisymGrid:
    """Yapısal H-tipi eksenel simetrik ızgara ve FVM metrikleri.

    Alanlar (hepsi SI, metre tabanlı; yüzey vektörleri 2π çarpanını İÇERİR,
    yani akı toplamları gerçek [kg/s, N, W] birimindedir):
        Z, R          : köşe koordinatları, (ni+1, nj+1)
        area_planar   : hücre düzlemsel alanı, (ni, nj) [m²]
        volume        : hücre dönel hacmi, (ni, nj) [m³]
        face_i        : +i yönlü yüzey vektörleri (S_z, S_r), (ni+1, nj, 2)
        face_j        : +j yönlü yüzey vektörleri, (ni, nj+1, 2)
        face_i_planar : r ağırlıksız (düzlemsel) yüzey vektörleri (kapanış
                        bekçisi için), (ni+1, nj, 2)
        face_j_planar : (ni, nj+1, 2)
        z_centers     : hücre merkez z'si (düzlemsel ağırlık merkezi), (ni, nj)
        r_centers     : hücre merkez r'si, (ni, nj)
    """
    Z: np.ndarray
    R: np.ndarray
    area_planar: np.ndarray
    volume: np.ndarray
    face_i: np.ndarray
    face_j: np.ndarray
    face_i_planar: np.ndarray
    face_j_planar: np.ndarray
    z_centers: np.ndarray
    r_centers: np.ndarray
    ni: int = field(default=0)
    nj: int = field(default=0)


def _face_vectors(za, ra, zb, rb, orient):
    """(a→b) düz parçasının dönel yüzey vektörü ve düzlemsel vektörü.

    orient='+i': normal +z ağırlıklı → S = 2π·r_orta·(Δr, −Δz)
    orient='+j': normal +r ağırlıklı → S = 2π·r_orta·(−Δr, +Δz)
    """
    dz = zb - za
    dr = rb - ra
    r_mid = 0.5 * (ra + rb)
    if orient == '+i':
        s_pl = np.stack([dr, -dz], axis=-1)
    else:
        s_pl = np.stack([-dr, dz], axis=-1)
    return _TWO_PI * r_mid[..., None] * s_pl, s_pl


def build_grid_from_wall(z_nodes, r_wall, nj):
    """Duvar polilinesinden yapısal ızgara kurar.

    Args:
        z_nodes: Eksenel köşe istasyonları [m], kesin artan, uzunluk ni+1.
        r_wall: Her istasyonda duvar yarıçapı [m], pozitif, uzunluk ni+1.
        nj: Radyal hücre sayısı (Aşama 1: düzgün dağılım, eksenden duvara).

    Returns:
        AxisymGrid.
    """
    z_nodes = np.asarray(z_nodes, dtype=float)
    r_wall = np.asarray(r_wall, dtype=float)
    if z_nodes.ndim != 1 or z_nodes.shape != r_wall.shape:
        raise ValueError('z_nodes ve r_wall aynı uzunlukta 1B dizi olmalı.')
    if z_nodes.size < 2:
        raise ValueError('En az 2 eksenel istasyon gerekli.')
    if np.any(np.diff(z_nodes) <= 0.0):
        raise ValueError('z_nodes kesin artan olmalı.')
    if np.any(~np.isfinite(z_nodes)) or np.any(~np.isfinite(r_wall)):
        raise ValueError('İstasyonlar sonlu olmalı.')
    if np.any(r_wall <= 0.0):
        raise ValueError('Duvar yarıçapı her istasyonda pozitif olmalı.')
    nj = int(nj)
    if nj < 2:
        raise ValueError('nj >= 2 olmalı (eksen ve duvar arasında hücre).')

    ni = z_nodes.size - 1
    eta = np.linspace(0.0, 1.0, nj + 1)          # Aşama 1: düzgün radyal
    Z = np.repeat(z_nodes[:, None], nj + 1, axis=1)
    R = r_wall[:, None] * eta[None, :]

    # Hücre köşeleri (CCW): v00=(i,j) v10=(i+1,j) v11=(i+1,j+1) v01=(i,j+1)
    z00, r00 = Z[:-1, :-1], R[:-1, :-1]
    z10, r10 = Z[1:, :-1], R[1:, :-1]
    z11, r11 = Z[1:, 1:], R[1:, 1:]
    z01, r01 = Z[:-1, 1:], R[:-1, 1:]

    def _loop(fn):
        """CCW kenar döngüsü üstünde Σ fn(a, b) (a→b kenarları)."""
        return (fn(z00, r00, z10, r10) + fn(z10, r10, z11, r11)
                + fn(z11, r11, z01, r01) + fn(z01, r01, z00, r00))

    # Shoelace alanı ve birinci moment (∫∫ r dA) — düz kenarda TAM
    cross = _loop(lambda za, ra, zb, rb: za * rb - zb * ra)
    area_planar = 0.5 * cross
    r_moment = _loop(lambda za, ra, zb, rb: (ra + rb) * (za * rb - zb * ra)) / 6.0
    z_moment = _loop(lambda za, ra, zb, rb: (za + zb) * (za * rb - zb * ra)) / 6.0
    if np.any(area_planar <= 0.0):
        raise ValueError('Negatif/sıfır düzlemsel hücre alanı: kontur '
                         'kendini kesiyor veya sıralama bozuk.')
    volume = _TWO_PI * r_moment
    z_centers = z_moment / area_planar
    r_centers = r_moment / area_planar

    # Yüzey vektörleri
    face_i, face_i_planar = _face_vectors(
        Z[:, :-1], R[:, :-1], Z[:, 1:], R[:, 1:], '+i')      # (ni+1, nj, 2)
    face_j, face_j_planar = _face_vectors(
        Z[:-1, :], R[:-1, :], Z[1:, :], R[1:, :], '+j')      # (ni, nj+1, 2)

    return AxisymGrid(Z=Z, R=R, area_planar=area_planar, volume=volume,
                      face_i=face_i, face_j=face_j,
                      face_i_planar=face_i_planar,
                      face_j_planar=face_j_planar,
                      z_centers=z_centers, r_centers=r_centers,
                      ni=ni, nj=nj)


def build_nozzle_grid(contour_points_mm, ni, nj):
    """sample_nozzle_inner_contour çıktısından ızgara kurar.

    Args:
        contour_points_mm: [(z_mm, r_mm), ...] iç kontur polilinesi
            (hrma/engines/nozzle_design.py:sample_nozzle_inner_contour
            deseni; z artan). Birim MİLİMETRE — burada metreye çevrilir.
        ni: Eksenel hücre sayısı (duvar, ni+1 düzgün z istasyonuna doğrusal
            polilineden yeniden örneklenir; H-tipi dikey ızgara çizgileri).
        nj: Radyal hücre sayısı (düzgün, Aşama 1).

    Returns:
        AxisymGrid (SI, metre).
    """
    pts = np.asarray(contour_points_mm, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or pts.shape[0] < 2:
        raise ValueError('Kontur [(z_mm, r_mm), ...] biçiminde olmalı.')
    z_mm = pts[:, 0]
    r_mm = pts[:, 1]
    if np.any(np.diff(z_mm) < 0.0):
        raise ValueError('Kontur z koordinatı artan olmalı '
                         '(sample_nozzle_inner_contour sözleşmesi).')
    ni = int(ni)
    if ni < 4:
        raise ValueError('ni >= 4 olmalı.')
    z_nodes_mm = np.linspace(z_mm[0], z_mm[-1], ni + 1)
    r_nodes_mm = np.interp(z_nodes_mm, z_mm, r_mm)
    return build_grid_from_wall(z_nodes_mm * 1e-3, r_nodes_mm * 1e-3, nj)
