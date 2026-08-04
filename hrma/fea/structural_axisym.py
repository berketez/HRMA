"""
Eksenel simetrik lineer elastik FEM çözücüsü (4 düğümlü bilineer quad).

Formülasyon
-----------
Yer değiştirme alanı (u_z, u_r); şekil değiştirme vektörü:

    ε = [ε_z, ε_r, ε_θ, γ_rz]
    ε_z = ∂u_z/∂z,  ε_r = ∂u_r/∂r,  ε_θ = u_r / r,
    γ_rz = ∂u_z/∂r + ∂u_r/∂z

B matrisinin çember (hoop) satırı N_a/r terimi taşır; r = 0 ekseninde bu
terim tekildir. Bu çözücü CİDAR bölgesi içindir (r > 0): mesh_axisym
üreticisi r <= 0 düğüme izin vermez, çözücü de Gauss noktasında r <= 0
görürse hesaba devam etmez.

İzotropik malzeme matrisi (SI, Pa):

    D = E/((1+ν)(1-2ν)) · [[1-ν, ν,   ν,   0        ],
                            [ν,   1-ν, ν,   0        ],
                            [ν,   ν,   1-ν, 0        ],
                            [0,   0,   0,   (1-2ν)/2 ]]

Eleman rijitliği K_e = ∫ Bᵀ D B · 2π r dA, 2×2 Gauss kuadratürüyle. Tam
integrasyonlu bilineer quad'da kum saati (hourglass) modu yoktur; eksenel
simetride tek rijit cisim modu z ötelenmesidir, en az bir u_z kısıtı şarttır.

İç yüzey basıncı, kenar üstünde tutarlı (consistent) düğüm kuvvetlerine
çevrilir: f = ∫ Nᵀ p n̂ · 2π r ds; lineer kenarda ∫N_a r ds tam kapalı
formla alınır (Gauss'a gerek kalmadan kesin).

Gerilme geri kazanımı: birincil yol Zienkiewicz-Zhu süperyakınsak yama geri
kazanımıdır (SPR). Bilineer Q4 elemanda türev/gerilme süperyakınsaklık
noktası ELEMAN MERKEZİDİR (Barlow noktası; örn. ∂u_r/∂r eleman içinde r
yönünde sabittir, dolayısıyla 2×2 Gauss noktalarındaki σ_r değerleri
merkezden uzaklık kadar O(h) kayıklık taşır). Bu yüzden SPR örneklemesi ZZ
1992'nin lineer eleman kurgusuna uygun olarak eleman başına TEK merkez
değeriyle yapılır: her İÇ köşe düğümünün yaması = düğümü paylaşan 4 elemanın
merkez gerilmeleri; bileşen bileşen lineer EKK fiti; sınır düğümleri en
yakın iç yamanın fitinden değerlendirilir. Bu, sınırda O(h) hata bırakan
basit Gauss→köşe ekstrapolasyonundan farklı olarak yüzeyde de O(h²)
doğruluk verir — σ_r'nin iç yüzeyde -p sınır değerine oturması bunun
sayesindedir. Eksenel bölüm sayısı yama kurmaya yetmiyorsa (n_axial < 2)
Hinton-Campbell köşe ekstrapolasyonu + düğüm ortalamasına düşülür ve hangi
yolun kullanıldığı meta'da beyan edilir. "Maks von Mises" takibi her iki
durumda da doğrudan 2×2 Gauss noktaları üzerinden yapılır
(ekstrapolasyon/fit aşımlarından bağımsız).

Doğrulama (tests/fea/test_yapisal_dogrulama.py — D3'ün yapısal yarısı):
Lamé kalın cidarlı silindir analitiği, sabit gerinim patch testi ve mesh
yakınsama monotonluğu. Doğrulanmamış FEA yayımlanmaz (V2.7 dokümanı §5).

Kaynaklar
---------
* Zienkiewicz & Taylor, "The Finite Element Method", 5. baskı, Cilt 1,
  Böl. 5 (Axisymmetric stress analysis) — B matrisi ve 1/r hoop terimi;
  Böl. 10 (patch testi kavramı).
* Timoshenko & Goodier, "Theory of Elasticity", 3. baskı, Böl. 4 (kutupsal
  koordinatlarda eksenel simetrik gerilme; iç/dış basınçlı silindir — Lamé
  çözümü, doğrulama referansı).
* Cook, Malkus, Plesha & Witt, "Concepts and Applications of Finite Element
  Analysis", 4. baskı — dönel simetrik katılar ve Gauss→düğüm gerilme
  ekstrapolasyonu.
* Zienkiewicz & Zhu, "The superconvergent patch recovery and a posteriori
  error estimates. Part 1: The recovery technique", Int. J. Numer. Methods
  Eng. 33 (1992) 1331-1364 — SPR düğüm gerilmesi geri kazanımı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Tuple, Union

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve

from hrma.fea.mesh_axisym import (
    AxisymMesh,
    build_wall_mesh,
    DEFAULT_ELEMS_THROUGH_WALL,
)

# ---------------------------------------------------------------------------
# Merkezî sayısal politika sabitleri (testler buradan import eder; parametre
# tutarlılığı kuralı gereği başka yerde tekrarlanmaz).
# ---------------------------------------------------------------------------
DEFAULT_REFINE_TOL = 0.01        # maks von Mises bağıl değişim toleransı
REFINE_FACTOR = 2                # her turda eksenel/radyal bölüm çarpanı
DEFAULT_MAX_REFINE_ROUNDS = 4    # başlangıç mesh'i + en fazla bu kadar inceltme
DEFAULT_N_AXIAL0 = 16            # inceltme sürücüsünün başlangıç eksenel bölümü

_GAUSS_COORD = 1.0 / np.sqrt(3.0)
# Gauss noktası ve köşe işaret sırası AYNI dizilişte tutulur (ekstrapolasyon
# matrisi bu eşleşmeye dayanır): (-,-), (+,-), (+,+), (-,+).
_QUAD_SIGNS = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]])

AXIAL_FIX_MODES = ("both_ends", "z_min", "z_max")


@dataclass(frozen=True)
class Material:
    """İzotropik lineer elastik malzeme (SI).

    E : Young modülü [Pa], nu : Poisson oranı, yield_strength : akma
    dayanımı [Pa] (emniyet katsayısı alanı için; verilmezse SF hesaplanmaz
    ve sonuçta None olarak beyan edilir — uydurma değer konmaz).
    """
    E: float
    nu: float
    yield_strength: Optional[float] = None
    name: str = ""

    def __post_init__(self):
        if not (self.E > 0.0 and np.isfinite(self.E)):
            raise ValueError("E > 0 ve sonlu olmalı.")
        if not (0.0 < self.nu < 0.5):
            raise ValueError(
                "Poisson oranı (0, 0.5) aralığında olmalı (ν=0.5 sıkışmaz "
                "limit, bu formülasyonda tekil).")
        if self.yield_strength is not None and self.yield_strength <= 0.0:
            raise ValueError("yield_strength verilirse pozitif olmalı.")


@dataclass
class StructuralResult:
    """Tek mesh üstünde lineer elastik çözüm sonucu.

    displacement : (N, 2) [u_z, u_r], m.
    stress_nodal : (N, 4) [σ_z, σ_r, σ_θ, τ_rz], Pa — Zienkiewicz-Zhu SPR
        geri kazanımı (yedek yol: Gauss→köşe ekstrapolasyonu; hangisi
        kullanıldıysa meta'daki 'stress_nodal_kaynagi' beyan eder).
    stress_gauss : (M, 4, 4) — eleman × Gauss noktası × bileşen, Pa.
    von_mises_nodal : (N,), von_mises_gauss : (M, 4), Pa.
    max_von_mises : float, Pa — Gauss noktaları üzerinden maksimum
        (yakınsama takibinin ölçütü).
    safety_factor_nodal : (N,) veya None — yield / von Mises (malzemede
        akma dayanımı yoksa None; sahte değer üretilmez).
    min_safety_factor : float veya None — yield / max_von_mises.
    meta : dict — model temeli, alan kaynakları ve MODELLENMEYENLERİN
        açık beyanı (sahte veri yasağı).
    """
    displacement: np.ndarray
    stress_nodal: np.ndarray
    stress_gauss: np.ndarray
    von_mises_nodal: np.ndarray
    von_mises_gauss: np.ndarray
    max_von_mises: float
    safety_factor_nodal: Optional[np.ndarray]
    min_safety_factor: Optional[float]
    meta: dict = field(default_factory=dict)


@dataclass
class RefinementResult:
    """Ardışık inceltme sürücüsünün sonucu.

    result / mesh : son (en ince) turun çözümü ve mesh'i.
    converged : maks von Mises bağıl değişimi toleransın altına indi mi.
    history : her tur için {"n_elems", "n_axial", "n_radial",
        "max_von_mises", "rel_change"} kayıtları (ilk turda rel_change None).
    final_rel_change : son iki tur arasındaki bağıl değişim (tek tur
        koşulduysa None).
    meta : kullanıcıya gösterilecek dürüst beyan ("beyan" anahtarı: eleman
        sayısı + son iki tur farkı + yakınsayıp yakınsamadığı).
    """
    result: StructuralResult
    mesh: AxisymMesh
    converged: bool
    history: list
    final_rel_change: Optional[float]
    tol: float
    meta: dict = field(default_factory=dict)


def elasticity_matrix(E: float, nu: float) -> np.ndarray:
    """İzotropik eksenel simetrik D matrisi (4×4), ε=[ε_z, ε_r, ε_θ, γ_rz]."""
    c = E / ((1.0 + nu) * (1.0 - 2.0 * nu))
    return c * np.array([
        [1.0 - nu, nu,        nu,        0.0],
        [nu,       1.0 - nu,  nu,        0.0],
        [nu,       nu,        1.0 - nu,  0.0],
        [0.0,      0.0,       0.0,       (1.0 - 2.0 * nu) / 2.0],
    ])


def von_mises(stress: np.ndarray) -> np.ndarray:
    """von Mises eşdeğer gerilmesi; son eksen [σ_z, σ_r, σ_θ, τ_rz]."""
    s = np.asarray(stress, dtype=float)
    sz, sr, st, trz = s[..., 0], s[..., 1], s[..., 2], s[..., 3]
    return np.sqrt(0.5 * ((sz - sr) ** 2 + (sr - st) ** 2 + (st - sz) ** 2)
                   + 3.0 * trz ** 2)


def _shape_functions(xi: float, eta: float):
    """Bilineer şekil fonksiyonları ve doğal türevleri (köşe sırası CCW)."""
    signs = _QUAD_SIGNS
    N = 0.25 * (1.0 + xi * signs[:, 0]) * (1.0 + eta * signs[:, 1])
    dN = np.empty((4, 2))
    dN[:, 0] = 0.25 * signs[:, 0] * (1.0 + eta * signs[:, 1])   # d/dξ
    dN[:, 1] = 0.25 * signs[:, 1] * (1.0 + xi * signs[:, 0])    # d/dη
    return N, dN


def _element_dof_map(elems: np.ndarray) -> np.ndarray:
    """(M, 8) eleman serbestlik haritası; düğüm başına [u_z, u_r]."""
    edof = np.empty((elems.shape[0], 8), dtype=np.int64)
    edof[:, 0::2] = 2 * elems
    edof[:, 1::2] = 2 * elems + 1
    return edof


def _point_B_matrix(X: np.ndarray, xi: float, eta: float):
    """(ξ, η) noktasında B matrisi + det J + fiziksel koordinat (tüm elemanlar).

    Dönüş: (B (M, 4, 8), detJ (M,), xy (M, 2)).
    """
    N, dN = _shape_functions(xi, eta)
    # J[k, i] = Σ_a dN_a/dξ_k · X_a,i  (k: ξ/η, i: z/r)
    J = np.einsum('ak,eai->eki', dN, X)
    detJ = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
    if np.any(detJ <= 0.0):
        raise ValueError(
            "İntegrasyon noktasında det J <= 0: mesh ters dönmüş/dejenere "
            "eleman içeriyor.")
    invJ = np.empty_like(J)
    invJ[:, 0, 0] = J[:, 1, 1]
    invJ[:, 0, 1] = -J[:, 0, 1]
    invJ[:, 1, 0] = -J[:, 1, 0]
    invJ[:, 1, 1] = J[:, 0, 0]
    invJ /= detJ[:, None, None]
    # dNdx[e, i, a] = ∂N_a/∂x_i  (x_0=z, x_1=r)
    dNdx = np.einsum('eik,ak->eia', invJ, dN)
    r_p = X[:, :, 1] @ N                             # (M,)
    if np.any(r_p <= 0.0):
        raise ValueError(
            "İntegrasyon noktasında r <= 0: eksenel simetrik formülasyonun "
            "1/r hoop terimi eksende tekil; bu çözücü cidar (r > 0) "
            "bölgesi içindir.")

    M = X.shape[0]
    B = np.zeros((M, 4, 8))
    B[:, 0, 0::2] = dNdx[:, 0, :]                    # ε_z ← ∂u_z/∂z
    B[:, 1, 1::2] = dNdx[:, 1, :]                    # ε_r ← ∂u_r/∂r
    B[:, 2, 1::2] = N[None, :] / r_p[:, None]        # ε_θ ← u_r/r
    B[:, 3, 0::2] = dNdx[:, 1, :]                    # γ  ← ∂u_z/∂r
    B[:, 3, 1::2] = dNdx[:, 0, :]                    # γ  ← ∂u_r/∂z

    xy = np.stack([X[:, :, 0] @ N, r_p], axis=1)
    return B, detJ, xy


def _assemble_stiffness(mesh: AxisymMesh, D: np.ndarray):
    """Global rijitlik matrisi + gerilme geri kazanımı için önbellekler.

    Dönüş: (K csr, cache). cache alanları:
      B_gauss (M, 4gp, 4, 8), gauss_xy (M, 4gp, 2) — 2×2 Gauss noktaları;
      B_cent (M, 4, 8), cent_xy (M, 2) — eleman merkezi (Barlow noktası,
      SPR örneklemesi); edof (M, 8).
    """
    X = mesh.nodes[mesh.elems]                       # (M, 4, 2)
    M = mesh.n_elems
    Ke = np.zeros((M, 8, 8))
    B_gauss = np.zeros((M, 4, 4, 8))
    gauss_xy = np.zeros((M, 4, 2))

    for g, (sx, sy) in enumerate(_QUAD_SIGNS):
        xi, eta = _GAUSS_COORD * sx, _GAUSS_COORD * sy
        B, detJ, xy = _point_B_matrix(X, xi, eta)
        r_gp = xy[:, 1]
        w = 2.0 * np.pi * detJ * r_gp                # Gauss ağırlığı 1
        Ke += w[:, None, None] * np.einsum('esi,st,etj->eij', B, D, B)
        B_gauss[:, g] = B
        gauss_xy[:, g] = xy

    B_cent, _, cent_xy = _point_B_matrix(X, 0.0, 0.0)

    edof = _element_dof_map(mesh.elems)
    rows = np.repeat(edof, 8, axis=1).ravel()
    cols = np.tile(edof, (1, 8)).ravel()
    ndof = 2 * mesh.n_nodes
    K = sp.coo_matrix((Ke.ravel(), (rows, cols)), shape=(ndof, ndof)).tocsr()
    cache = {"B_gauss": B_gauss, "gauss_xy": gauss_xy,
             "B_cent": B_cent, "cent_xy": cent_xy, "edof": edof}
    return K, cache


def _add_edge_pressure(F: np.ndarray, nodes: np.ndarray, edges: np.ndarray,
                       p: float, normal_sign: float) -> None:
    """Kenar basıncının tutarlı düğüm kuvvetlerini F'ye ekler.

    Kenarlar artan istasyon sırasıyla verilir; bölge iç yüzeyin +r tarafında
    olduğundan basıncın bölgeye bakan normali iç yüzeyde +(-Δr, Δz), dış
    yüzeyde -(-Δr, Δz) yönündedir (normal_sign = +1 / -1).

    f_a = p n̂ · 2π ∫ N_a r ds; lineer kenarda ∫N_1 r ds = L(2r_1+r_2)/6,
    ∫N_2 r ds = L(r_1+2r_2)/6 — burada n̂L, normalize edilmemiş (-Δr, Δz)
    vektörünün kendisidir, yani L ile ayrıca çarpmaya gerek yoktur.
    """
    if p == 0.0 or edges.size == 0:
        return
    P1 = nodes[edges[:, 0]]
    P2 = nodes[edges[:, 1]]
    d = P2 - P1
    n_unnorm = normal_sign * np.stack([-d[:, 1], d[:, 0]], axis=1)  # |n|=L
    r1, r2 = P1[:, 1], P2[:, 1]
    c1 = 2.0 * np.pi * p * (2.0 * r1 + r2) / 6.0
    c2 = 2.0 * np.pi * p * (r1 + 2.0 * r2) / 6.0
    f1 = c1[:, None] * n_unnorm
    f2 = c2[:, None] * n_unnorm
    np.add.at(F, 2 * edges[:, 0], f1[:, 0])
    np.add.at(F, 2 * edges[:, 0] + 1, f1[:, 1])
    np.add.at(F, 2 * edges[:, 1], f2[:, 0])
    np.add.at(F, 2 * edges[:, 1] + 1, f2[:, 1])


def _nodal_stress_extrapolation(mesh: AxisymMesh,
                                sig_gauss: np.ndarray) -> np.ndarray:
    """Yedek yol: Gauss→köşe √3 ekstrapolasyonu + düğümde komşu ortalaması.

    Gauss değerleri (ξ, η)'da bilineer alan sayılır; köşe (±1, ±1) noktaları
    Gauss karesinde ±√3'e düşer (Hinton-Campbell). Sınır düğümlerinde tek
    taraflı kaldığı için oradaki hatası O(h)'dir; birincil yol SPR'dır.
    """
    sqrt3 = np.sqrt(3.0)
    Ex = 0.25 * ((1.0 + sqrt3 * np.outer(_QUAD_SIGNS[:, 0], _QUAD_SIGNS[:, 0]))
                 * (1.0 + sqrt3 * np.outer(_QUAD_SIGNS[:, 1], _QUAD_SIGNS[:, 1])))
    sig_corner = np.einsum('ag,egs->eas', Ex, sig_gauss)   # (M, 4köşe, 4)

    acc = np.zeros((mesh.n_nodes, 4))
    cnt = np.zeros(mesh.n_nodes)
    np.add.at(acc, mesh.elems.ravel(), sig_corner.reshape(-1, 4))
    np.add.at(cnt, mesh.elems.ravel(), 1.0)
    return acc / cnt[:, None]


def _nodal_stress_spr(mesh: AxisymMesh, sig_cent: np.ndarray,
                      cent_xy: np.ndarray):
    """Zienkiewicz-Zhu SPR düğüm gerilmesi geri kazanımı (Q4 kurgusu).

    Örnekleme noktası eleman MERKEZİDİR (bilineer elemanın Barlow noktası;
    2×2 Gauss noktalarındaki türev alanı merkezden uzaklık kadar O(h)
    kayıklık taşır — modül docstring'ine bakınız). Her iç köşe düğümü
    (yapısal grid'de 1<=i<=n_axial-1, 1<=j<=n_radial-1) için yama = düğümü
    paylaşan 4 elemanın merkez gerilmeleri. Her gerilme bileşenine
    σ(z, r) ≈ a0 + a1·ẑ + a2·r̂ lineer polinomu EKK ile uydurulur (ẑ, r̂:
    düğüm merkezli ve yama boyutuyla ölçeklenmiş koordinatlar — ince
    cidarda anizotropik eleman oranına karşı koşullama). İç düğümün değeri
    fitin düğümdeki değeridir; SINIR düğümleri en yakın iç yamanın fitinden
    değerlendirilir (Zienkiewicz & Zhu 1992'nin sınır önerisi).

    n_axial < 2 ise yama kurulamaz — None döner (çağıran yedek yola düşer).
    """
    n_ax, n_rad = mesh.n_axial, mesh.n_radial
    if n_ax < 2 or n_rad < 2:
        return None

    # Eleman (i, j) → e = i * n_rad + j (mesh_axisym'in ravel sırası).
    iv, jv = np.meshgrid(np.arange(1, n_ax), np.arange(1, n_rad),
                         indexing="ij")
    iv, jv = iv.ravel(), jv.ravel()                    # (P,) iç köşeler
    e00 = (iv - 1) * n_rad + (jv - 1)
    e01 = (iv - 1) * n_rad + jv
    e10 = iv * n_rad + (jv - 1)
    e11 = iv * n_rad + jv
    epatch = np.stack([e00, e01, e10, e11], axis=1)    # (P, 4)

    P = iv.size
    pts = cent_xy[epatch]                              # (P, 4, 2)
    vals = sig_cent[epatch]                            # (P, 4, 4)
    vtx = mesh.nodes[mesh.node_index_grid[iv, jv]]     # (P, 2)

    dz = pts[:, :, 0] - vtx[:, None, 0]
    dr = pts[:, :, 1] - vtx[:, None, 1]
    scale_z = np.abs(dz).max(axis=1)                   # (P,)
    scale_r = np.abs(dr).max(axis=1)
    if np.any(scale_z <= 0.0) or np.any(scale_r <= 0.0):
        return None                                     # dejenere yama
    Xd = np.stack([np.ones_like(dz), dz / scale_z[:, None],
                   dr / scale_r[:, None]], axis=2)      # (P, 4, 3)
    G = np.einsum('pki,pkj->pij', Xd, Xd)               # (P, 3, 3)
    rhs = np.einsum('pki,pks->pis', Xd, vals)           # (P, 3, 4)
    coef = np.linalg.solve(G, rhs)                      # (P, 3, 4)

    # Her düğüm (i, j), en yakın iç yamadan değerlendirilir; iç düğümün
    # en yakın yaması kendisidir (ẑ = r̂ = 0 → a0).
    ni, nj = np.meshgrid(np.arange(n_ax + 1), np.arange(n_rad + 1),
                         indexing="ij")
    ni, nj = ni.ravel(), nj.ravel()
    pi = np.clip(ni, 1, n_ax - 1)
    pj = np.clip(nj, 1, n_rad - 1)
    p_idx = (pi - 1) * (n_rad - 1) + (pj - 1)          # yama düz indeksi
    node_ids = mesh.node_index_grid[ni, nj]
    nzr = mesh.nodes[node_ids]                          # (N, 2)
    dzn = (nzr[:, 0] - vtx[p_idx, 0]) / scale_z[p_idx]
    drn = (nzr[:, 1] - vtx[p_idx, 1]) / scale_r[p_idx]
    vals_n = (coef[p_idx, 0, :]
              + coef[p_idx, 1, :] * dzn[:, None]
              + coef[p_idx, 2, :] * drn[:, None])       # (N, 4)

    stress_nodal = np.empty((mesh.n_nodes, 4))
    stress_nodal[node_ids] = vals_n
    return stress_nodal


def _recover_stresses(mesh: AxisymMesh, D: np.ndarray, cache: dict,
                      u: np.ndarray):
    """Gauss gerilmeleri + düğüm alanı (SPR; kurulamıyorsa ekstrapolasyon).

    Dönüş: (sig_gauss, stress_nodal, yontem_adi).
    """
    ue = u[cache["edof"]]                                  # (M, 8)
    eps_g = np.einsum('egsj,ej->egs', cache["B_gauss"], ue)
    sig_gauss = np.einsum('st,egt->egs', D, eps_g)         # (M, 4gp, 4)
    eps_c = np.einsum('esj,ej->es', cache["B_cent"], ue)
    sig_cent = eps_c @ D.T                                 # (M, 4)

    stress_nodal = _nodal_stress_spr(mesh, sig_cent, cache["cent_xy"])
    if stress_nodal is not None:
        yontem = ("Zienkiewicz-Zhu SPR: iç köşe yamalarında 4 eleman "
                  "merkezi (Barlow noktası) değerine lineer EKK; sınır "
                  "düğümleri en yakın iç yamadan (ZZ 1992)")
    else:
        stress_nodal = _nodal_stress_extrapolation(mesh, sig_gauss)
        yontem = ("Gauss→köşe sqrt(3) ekstrapolasyonu + düğüm ortalaması "
                  "(SPR yaması kurulamadı: n_axial < 2)")
    return sig_gauss, stress_nodal, yontem


def _result_meta() -> dict:
    """Sonuç alanlarının _basis/_source beyanı (sahte veri yasağı gereği)."""
    return {
        "_source": "hrma.fea.structural_axisym",
        "_basis": ("2B eksenel simetrik lineer elastik FEM; 4 düğümlü "
                   "bilineer quad, 2x2 Gauss, scipy.sparse doğrudan çözüm"),
        "max_von_mises_kaynagi": "Gauss noktaları üzerinden maksimum",
        "birimler": {"uzunluk": "m", "gerilme_basinc": "Pa",
                     "yer_degistirme": "m"},
        "not_modelled": [
            "termal gerilme (thermal_axisym sonraki dalga)",
            "plastisite / akma sonrası davranış",
            "burkulma",
            "geometrik nonlineerite (büyük yer değiştirme)",
            "dinamik / titreşim yükleri",
        ],
    }


def solve_linear(mesh: AxisymMesh,
                 material: Material,
                 dirichlet: Iterable[Tuple[int, int, float]],
                 inner_pressure: float = 0.0,
                 outer_pressure: float = 0.0) -> StructuralResult:
    """Genel giriş noktası: Dirichlet kısıtları + yüzey basınçlarıyla çözüm.

    Parametreler
    ------------
    dirichlet : (düğüm, serbestlik, değer) üçlüleri; serbestlik 0 = u_z,
        1 = u_r, değer metre cinsinden dayatılan yer değiştirme. Aynı
        serbestliğe çelişen iki değer verilirse hata. Eksenel simetride tek
        rijit cisim modu z ötelenmesi olduğundan en az bir u_z kısıtı şarttır.
    inner_pressure / outer_pressure : iç/dış yüzeye etkiyen mutlak basınç
        farkı yükü [Pa]; pozitif değer yüzeyden cidara doğru iter.
    """
    if mesh.nodes.ndim != 2 or mesh.nodes.shape[1] != 2:
        raise ValueError("mesh.nodes (N, 2) olmalı.")
    for p, ad in ((inner_pressure, "inner_pressure"),
                  (outer_pressure, "outer_pressure")):
        if not np.isfinite(p):
            raise ValueError(f"{ad} sonlu olmalı.")

    # Dirichlet derle + çelişki denetimi
    prescribed = {}
    for node, dof, value in dirichlet:
        node, dof = int(node), int(dof)
        if dof not in (0, 1):
            raise ValueError("Serbestlik 0 (u_z) veya 1 (u_r) olmalı.")
        if not (0 <= node < mesh.n_nodes):
            raise ValueError(f"Düğüm indeksi aralık dışı: {node}")
        key = 2 * node + dof
        if key in prescribed and prescribed[key] != float(value):
            raise ValueError(
                f"Düğüm {node} serbestlik {dof} için çelişen Dirichlet "
                "değerleri verildi.")
        prescribed[key] = float(value)

    if not prescribed:
        raise ValueError(
            "En az bir Dirichlet kısıtı gerekli: eksenel simetride z yönü "
            "rijit cisim modu ancak u_z kısıtıyla giderilir.")
    if not any(k % 2 == 0 for k in prescribed):
        raise ValueError(
            "Hiç u_z kısıtı yok; z ötelenmesi rijit cisim modu serbest "
            "kalır ve sistem tekildir.")

    D = elasticity_matrix(material.E, material.nu)
    K, cache = _assemble_stiffness(mesh, D)

    ndof = 2 * mesh.n_nodes
    F = np.zeros(ndof)
    _add_edge_pressure(F, mesh.nodes, mesh.inner_edges, inner_pressure, +1.0)
    _add_edge_pressure(F, mesh.nodes, mesh.outer_edges, outer_pressure, -1.0)

    fixed = np.zeros(ndof, dtype=bool)
    u = np.zeros(ndof)
    for key, val in prescribed.items():
        fixed[key] = True
        u[key] = val
    free = ~fixed

    K_ff = K[free][:, free]
    rhs = F[free] - K[free][:, fixed] @ u[fixed]
    u_free = spsolve(K_ff.tocsc(), rhs)
    if not np.all(np.isfinite(u_free)):
        raise RuntimeError(
            "Doğrusal sistem çözümü sonlu değil (tekil/kötü koşullu K); "
            "kısıtlar ve mesh gözden geçirilmeli.")
    u[free] = u_free

    sig_gauss, stress_nodal, recovery_method = _recover_stresses(
        mesh, D, cache, u)
    vm_gauss = von_mises(sig_gauss)
    vm_nodal = von_mises(stress_nodal)
    max_vm = float(vm_gauss.max())

    if material.yield_strength is not None:
        ys = material.yield_strength
        sf_nodal = np.where(vm_nodal > 0.0, ys / np.maximum(vm_nodal, 1e-300),
                            np.inf)
        min_sf = float(ys / max_vm) if max_vm > 0.0 else float("inf")
    else:
        sf_nodal = None
        min_sf = None

    meta = _result_meta()
    meta["stress_nodal_kaynagi"] = recovery_method
    meta["malzeme"] = {"E_Pa": material.E, "nu": material.nu,
                       "yield_Pa": material.yield_strength,
                       "ad": material.name}
    meta["yukler"] = {"inner_pressure_Pa": float(inner_pressure),
                      "outer_pressure_Pa": float(outer_pressure)}
    if material.yield_strength is None:
        meta["safety_factor_durumu"] = (
            "HESAPLANMADI — malzeme akma dayanımı verilmedi")

    return StructuralResult(
        displacement=u.reshape(-1, 2),
        stress_nodal=stress_nodal,
        stress_gauss=sig_gauss,
        von_mises_nodal=vm_nodal,
        von_mises_gauss=vm_gauss,
        max_von_mises=max_vm,
        safety_factor_nodal=sf_nodal,
        min_safety_factor=min_sf,
        meta=meta,
    )


def _axial_fix_dirichlet(mesh: AxisymMesh, axial_fix: str):
    """axial_fix kipini u_z = 0 Dirichlet listesine çevirir."""
    if axial_fix not in AXIAL_FIX_MODES:
        raise ValueError(
            f"axial_fix {AXIAL_FIX_MODES} içinden olmalı (rijit cisim "
            "kısıtı şart); verilen: {!r}".format(axial_fix))
    node_sets = {
        "z_min": [mesh.z_min_nodes],
        "z_max": [mesh.z_max_nodes],
        "both_ends": [mesh.z_min_nodes, mesh.z_max_nodes],
    }[axial_fix]
    dirichlet = []
    for ns in node_sets:
        dirichlet.extend((int(n), 0, 0.0) for n in ns)
    return dirichlet


def solve_pressure(mesh: AxisymMesh,
                   material: Material,
                   inner_pressure: float,
                   outer_pressure: float = 0.0,
                   axial_fix: str = "z_min") -> StructuralResult:
    """Basınç yüklü cidar için kolay giriş noktası.

    axial_fix : "z_min" (varsayılan; bağlantı flanşı benzetimi — z_min uç
        kesitinde u_z = 0), "z_max" veya "both_ends" (her iki uç kesitte
        u_z = 0; eksenel gerinimi bastırır, Lamé düzlem şekil değiştirme
        doğrulaması bu kiple koşulur). u_r her yerde serbesttir.
    """
    dirichlet = _axial_fix_dirichlet(mesh, axial_fix)
    result = solve_linear(mesh, material, dirichlet,
                          inner_pressure=inner_pressure,
                          outer_pressure=outer_pressure)
    result.meta["sinir_kosulu"] = f"u_z=0 @ {axial_fix}; u_r serbest"
    return result


def solve_with_refinement(contour,
                          thickness: Union[float, np.ndarray],
                          material: Material,
                          inner_pressure: float,
                          outer_pressure: float = 0.0,
                          tol: float = DEFAULT_REFINE_TOL,
                          axial_fix: str = "z_min",
                          n_axial0: int = DEFAULT_N_AXIAL0,
                          n_radial0: int = DEFAULT_ELEMS_THROUGH_WALL,
                          max_rounds: int = DEFAULT_MAX_REFINE_ROUNDS,
                          offset_mode: str = "normal") -> RefinementResult:
    """"Optimal mesh" sürücüsü: ardışık inceltme + yakınsama denetimi.

    Kullanıcıya mesh ayarı gösterilmez; "optimal" iddiasının dürüst karşılığı
    yakınsama kontrolüdür (V2.7 dokümanı §3): her turda eksenel ve radyal
    bölüm sayısı ``REFINE_FACTOR`` ile çarpılır, hedef büyüklük (maks von
    Mises, Gauss alanı) son iki tur arasında bağıl olarak ``tol`` altında
    değişince durulur. Eleman sayısı ve son fark ``history`` ile
    ``meta['beyan']`` içinde raporlanır; ``max_rounds`` içinde yakınsamazsa
    ``converged=False`` döner ve beyan bunu AÇIKÇA söyler — yakınsamamış
    sonuç yakınsamış gibi sunulmaz.

    Girdi saf geometri + malzeme + yüktür (motor sonuç sözlüğüne bağımlılık
    yok; motor köprüsü ayrı katmandır).
    """
    if not (0.0 < tol < 1.0):
        raise ValueError("tol (0, 1) aralığında bağıl değişim olmalı.")
    if max_rounds < 0:
        raise ValueError("max_rounds >= 0 olmalı.")

    history = []
    prev_vm = None
    rel_change = None
    converged = False
    result = None
    mesh = None

    for k in range(max_rounds + 1):
        n_ax = int(n_axial0) * REFINE_FACTOR ** k
        n_rad = int(n_radial0) * REFINE_FACTOR ** k
        mesh = build_wall_mesh(contour, thickness, n_ax, n_rad,
                               offset_mode=offset_mode)
        result = solve_pressure(mesh, material, inner_pressure,
                                outer_pressure=outer_pressure,
                                axial_fix=axial_fix)
        vm = result.max_von_mises
        if prev_vm is None:
            rel_change = None
        else:
            scale = max(abs(vm), abs(prev_vm), 1e-300)
            rel_change = abs(vm - prev_vm) / scale
        history.append({
            "n_elems": mesh.n_elems,
            "n_axial": mesh.n_axial,
            "n_radial": mesh.n_radial,
            "max_von_mises": vm,
            "rel_change": rel_change,
        })
        if rel_change is not None and rel_change < tol:
            converged = True
            break
        prev_vm = vm

    if converged:
        beyan = (f"Mesh yakınsadı: {mesh.n_elems} eleman; son iki inceltme "
                 f"turu arasında maks von Mises farkı "
                 f"%{100.0 * rel_change:.2f} (tolerans %{100.0 * tol:.2f}).")
    elif rel_change is None:
        beyan = (f"YAKINSAMA DENETLENEMEDİ: tek tur koşuldu "
                 f"({mesh.n_elems} eleman); karşılaştırılacak ikinci tur yok.")
    else:
        beyan = (f"YAKINSAMADI: {max_rounds + 1} turda son fark "
                 f"%{100.0 * rel_change:.2f} tolerans %{100.0 * tol:.2f} "
                 f"altına inmedi ({mesh.n_elems} eleman). Sonuç bu beyanla "
                 "birlikte değerlendirilmelidir.")

    meta = {
        "_source": "hrma.fea.structural_axisym.solve_with_refinement",
        "_basis": ("ardışık tekdüze inceltme; hedef büyüklük maks von Mises "
                   f"(Gauss), tolerans {tol} bağıl değişim, çarpan "
                   f"{REFINE_FACTOR}"),
        "beyan": beyan,
        "converged": converged,
        "n_elems_final": mesh.n_elems,
        "final_rel_change": rel_change,
        "tol": tol,
    }

    return RefinementResult(
        result=result,
        mesh=mesh,
        converged=converged,
        history=history,
        final_rel_change=rel_change,
        tol=tol,
        meta=meta,
    )
