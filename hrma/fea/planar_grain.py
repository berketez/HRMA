"""
Katı yakıt tanesi kesiti için 2B DÜZLEM ŞEKİL DEĞİŞTİRME (plane strain)
lineer elastik FEM çözücüsü (V2.7 Aşama C).

Neden düzlemsel kip: kamara/lüle cidarı eksenel simetriktir ve
structural_axisym o işi görür; ama star/finocyl/slotted tane kesitleri
eksenel simetrik DEĞİLDİR (docs/mimari/yol-haritasi.md §5). Bu çözücü,
mesh_planar'ın ürettiği kesit mesh'i üstünde port basıncı altındaki tane
gerilme/gerinim alanını çözer.

Varsayımlar (hepsi sonuç meta'sında beyan edilir):
  * DÜZLEM ŞEKİL DEĞİŞTİRME: tane uzun, uçlar tutulu kabul edilir
    (ε_z = 0). Kısa tanede uç etkileri modellenmez.
  * LİNEER ELASTİK malzeme: katı yakıtın gerçek davranışı VİSKOELASTİKTİR
    (NASA SP-8073); bu kip zaman/oran bağımlılığı olmayan bir ÖN
    BOYUTLANDIRMA aracıdır, kabul analizi değildir.
  * Birim kalınlık (1 m) — düzlemsel kesit başına sonuç.
  * Termal büzülme/genleşme MODELLENMEZ (motorun analitik
    _calculate_grain_structural bloğu kürleme soğumasını ayrıca verir).

Formülasyon
-----------
ε = [ε_x, ε_y, γ_xy]; izotropik düzlem şekil değiştirme matrisi

    D = E/((1+ν)(1-2ν)) · [[1-ν, ν,   0        ],
                            [ν,   1-ν, 0        ],
                            [0,   0,   (1-2ν)/2 ]]

4 düğümlü bilineer quad, 2×2 Gauss. Katı yakıt neredeyse SIKIŞTIRILAMAZ
(HTPB ν ≈ 0.4995): tam integrasyonlu Q4 bu rejimde hacimsel KİLİTLENİR
(volumetric locking). Bu yüzden B-bar (ortalama dilatasyon) yöntemi
kullanılır: B matrisinin dilatasyon kısmı her Gauss noktasında eleman
MERKEZİ değeriyle değiştirilir (B̄ = B_dev + B̄_dil). Sabit gerinim
alanında B̄ = B olduğundan patch testi bozulmaz; ν → 0.5 limitinde
kilitlenme kalkar (doğrulama: Lamé çember gerilmesi ν'den bağımsızdır,
tests/test_fea_planar_grain.py bunu ν = 0.4995'te de kilitler).

σ_z = ν(σ_x + σ_y) (düzlem şekil değiştirme); von Mises dört bileşenle
hesaplanır. Gerilme geri kazanımı structural_axisym ile aynı kurgudur:
birincil yol Zienkiewicz-Zhu SPR (eleman merkezi Barlow noktası örneklemesi,
iç köşe yamalarında lineer EKK, sınır düğümleri en yakın iç yamadan),
yedek yol Gauss→köşe ekstrapolasyonu + düğüm ortalaması.

Port yüzeyi GERİNİMİ: katı tane kabul ölçütü gerilme değil GERİNİMDİR
(NASA SP-8073) — port yüzeyi lif gerinimi, yüzey kenarlarının şekil
değiştirmiş/orijinal boy oranından DOĞRUDAN yer değiştirme alanından
hesaplanır (gerilme geri kazanım hatasından bağımsız) ve yakıtın kopma
uzaması (SOLID_GRAIN_MECHANICS 'strain_capability') ile oranlanır.

Sınır koşulları:
  * Port yüzeyi: sabit oda basıncı P_c (tutarlı kenar kuvvetleri).
  * Dış yüzey ('outer_bc'):
      - "bonded_rigid" (varsayılan): u = 0 — RİJİT kasaya yapışık tane
        (case-bonded). Kasanın kendi esnemesi MODELLENMEZ; esneyen kasa
        port gerinimini BÜYÜTÜR, yani bu seçim port gerinimi için
        alt-taraflı olabilir — beyan edilir (motorun analitik bloğu kasa
        esnemesini içerir, ikisi birlikte okunmalıdır).
      - "free": serbest dış yüzey — Lamé doğrulaması için (kartuş tane
        değil; doğrulama kipi olduğu beyan edilir).
  * Dilim kenarları: ayna simetrisi → kayar mesnet (düzleme dik bileşen
    sıfır). Eğik düzlemde kısıt, düğüm serbestliklerinin yerel (radyal,
    teğet) eksenlere DÖNDÜRÜLMESİYLE uygulanır (K̂ = RᵀKR standart
    dönüşümü; Cook ve ark., Böl. 13 — eğik mesnet).

Geçerlilik kapıları: ters/dejenere eleman mesh üreticisinde reddedilir;
tekil sistem (serbest rijit cisim modu bırakan BC bileşimi) çözümden ÖNCE
açık hatayla reddedilir; çözüm sonlu değilse RuntimeError.

Kaynaklar
---------
* Cook, Malkus, Plesha & Witt, "Concepts and Applications of Finite
  Element Analysis", 4. baskı — düzlem elastisite Q4 formülasyonu (Böl. 3,
  6), eğik mesnet dönüşümü (Böl. 13).
* Zienkiewicz & Taylor, "The Finite Element Method", 5. baskı, Cilt 1 —
  izoparametrik eleman ve sayısal integrasyon.
* T.J.R. Hughes, "Generalization of selective integration procedures to
  anisotropic and nonlinear media", Int. J. Numer. Methods Eng. 15 (1980)
  1413-1418; Hughes, "The Finite Element Method" (1987), Böl. 4 — B-bar /
  seçmeli azaltılmış integrasyon (sıkıştırılamaz limitte kilitlenme).
* Timoshenko & Goodier, "Theory of Elasticity", 3. baskı, Böl. 4 — iç
  basınçlı kalın cidarlı silindir (Lamé; doğrulama tabanı).
* NASA SP-8073 "Solid Propellant Grain Structural Integrity Analysis" —
  kabul ölçütünün gerinim olduğu ve viskoelastisite gerçeği.
* Zienkiewicz & Zhu, IJNME 33 (1992) 1331-1364 — SPR geri kazanımı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Union

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve

from hrma.fea.mesh_axisym import DEFAULT_ELEMS_THROUGH_WALL
from hrma.fea.mesh_planar import PlanarSectionMesh, build_grain_section_mesh
# Merkezî sayısal politika + eleman altyapısı structural_axisym'den paylaşılır
# (parametre tutarlılığı kuralı: inceltme çarpanı/toleransı ve Gauss/şekil
# fonksiyonu tanımları TEK yerde durur, burada tekrarlanmaz).
from hrma.fea.structural_axisym import (
    DEFAULT_MAX_REFINE_ROUNDS,
    DEFAULT_REFINE_TOL,
    Material,
    REFINE_FACTOR,
    _GAUSS_COORD,
    _QUAD_SIGNS,
    _element_dof_map,
    _shape_functions,
)

#: Yakınsama sürücüsünün başlangıç çevresel bölümü (dilim başına).
DEFAULT_N_THETA0 = 24

OUTER_BC_MODES = ("bonded_rigid", "free")


@dataclass
class PlanarGrainResult:
    """Tek mesh üstünde düzlem şekil değiştirme çözümü.

    displacement : (N, 2) [u_x, u_y], m.
    stress_nodal : (N, 4) [σ_x, σ_y, σ_z, τ_xy], Pa — SPR (yedek yol
        beyan edilir, meta['stress_nodal_kaynagi']).
    stress_gauss : (M, 4gp, 4) Pa.
    von_mises_nodal / von_mises_gauss : Pa; max_von_mises Gauss noktaları
        üzerinden, max_von_mises_nodal SPR düğüm alanı üzerinden maksimum.
        Tepe gerilme PORT SINIRINDADIR: Gauss noktası sınıra ancak O(h)
        yaklaşır, SPR sınır değeri O(h²) doğruluktadır (ölçüldü, bates:
        24 576 elemanda Gauss maks %2,4 değişmeye devam ederken düğüm maks
        %0,62'ye düşer) — yakınsama sürücüsünün hedefi bu yüzden düğüm
        maksimumudur ve beyan edilir.
    max_principal_nodal : (N,) Pa — maks asal gerilme (düzlem içi asal
        ile σ_z'nin büyüğü).
    bore_node_ids : (n_theta+1,) int — port yüzeyi istasyon düğümleri
        (artan θ; tam halkada son = ilk).
    bore_strain_edges : (n_theta,) — port yüzeyi kenar lif gerinimi
        (yer değiştirmeden doğrudan; birim, çekme +).
    bore_strain_nodal : (n_theta+1,) — komşu kenarların düğüm ortalaması.
    max_bore_strain : float — |gerinim| maksimumu (işareti korunur).
    strain_margin : float|None — strain_capability / |maks gerinim|
        (kabiliyet verilmemişse None; sahte değer üretilmez).
    meta : dict — varsayım ve NOT_MODELLED beyanları.
    """
    displacement: np.ndarray
    stress_nodal: np.ndarray
    stress_gauss: np.ndarray
    von_mises_nodal: np.ndarray
    von_mises_gauss: np.ndarray
    max_von_mises: float
    max_von_mises_nodal: float
    max_principal_nodal: np.ndarray
    bore_node_ids: np.ndarray
    bore_strain_edges: np.ndarray
    bore_strain_nodal: np.ndarray
    max_bore_strain: float
    strain_margin: Optional[float]
    meta: dict = field(default_factory=dict)


@dataclass
class GrainRefinementResult:
    """Ardışık inceltme sürücüsünün sonucu (structural_axisym deseni)."""
    result: PlanarGrainResult
    mesh: PlanarSectionMesh
    converged: bool
    history: list
    final_rel_change: Optional[float]
    tol: float
    meta: dict = field(default_factory=dict)


def elasticity_matrix_plane_strain(E: float, nu: float) -> np.ndarray:
    """İzotropik düzlem şekil değiştirme D matrisi (3×3), ε=[ε_x, ε_y, γ_xy]."""
    c = E / ((1.0 + nu) * (1.0 - 2.0 * nu))
    return c * np.array([
        [1.0 - nu, nu,       0.0],
        [nu,       1.0 - nu, 0.0],
        [0.0,      0.0,      (1.0 - 2.0 * nu) / 2.0],
    ])


def von_mises_plane_strain(stress: np.ndarray) -> np.ndarray:
    """von Mises; son eksen [σ_x, σ_y, σ_z, τ_xy]."""
    s = np.asarray(stress, dtype=float)
    sx, sy, sz, txy = s[..., 0], s[..., 1], s[..., 2], s[..., 3]
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                   + 3.0 * txy ** 2)


def max_principal_plane_strain(stress: np.ndarray) -> np.ndarray:
    """Maks asal gerilme: düzlem içi σ₁ ile σ_z'nin büyüğü."""
    s = np.asarray(stress, dtype=float)
    sx, sy, sz, txy = s[..., 0], s[..., 1], s[..., 2], s[..., 3]
    s1_ip = 0.5 * (sx + sy) + np.sqrt((0.5 * (sx - sy)) ** 2 + txy ** 2)
    return np.maximum(s1_ip, sz)


def _point_B_planar(X: np.ndarray, xi: float, eta: float):
    """(ξ, η) noktasında düzlemsel B (M, 3, 8) + det J (tüm elemanlar)."""
    _N, dN = _shape_functions(xi, eta)
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
    dNdx = np.einsum('eik,ak->eia', invJ, dN)      # (M, 2, 4)

    M = X.shape[0]
    B = np.zeros((M, 3, 8))
    B[:, 0, 0::2] = dNdx[:, 0, :]                  # ε_x ← ∂u_x/∂x
    B[:, 1, 1::2] = dNdx[:, 1, :]                  # ε_y ← ∂u_y/∂y
    B[:, 2, 0::2] = dNdx[:, 1, :]                  # γ  ← ∂u_x/∂y
    B[:, 2, 1::2] = dNdx[:, 0, :]                  # γ  ← ∂u_y/∂x
    return B, detJ


def _bbar(B: np.ndarray, b_dil_cent: np.ndarray) -> np.ndarray:
    """B-bar: dilatasyon satır katkısı eleman merkezi değeriyle değiştirilir.

    b_dil = B satır1 + satır2 (u_e → ε_x + ε_y). Düzlem şekil değiştirmede
    dilatasyon payı iki normal satıra 1/2'şer dağılır (Hughes 1980 ortalama
    dilatasyon, 2B hâli). Sabit gerinimde b_dil = b_dil_cent → B̄ = B.
    """
    b_dil = B[:, 0, :] + B[:, 1, :]                # (M, 8)
    Bbar = B.copy()
    duzeltme = 0.5 * (b_dil_cent - b_dil)          # (M, 8)
    Bbar[:, 0, :] += duzeltme
    Bbar[:, 1, :] += duzeltme
    return Bbar


def _assemble_stiffness_planar(mesh: PlanarSectionMesh, D: np.ndarray):
    """Global rijitlik (birim kalınlık) + geri kazanım önbellekleri.

    Dönüş: (K csr, cache) — cache: Bbar_gauss (M, 4gp, 3, 8),
    B_cent (M, 3, 8), cent_xy (M, 2), edof (M, 8).
    """
    X = mesh.nodes[mesh.elems]                     # (M, 4, 2)
    M = mesh.n_elems
    Ke = np.zeros((M, 8, 8))
    Bbar_gauss = np.zeros((M, 4, 3, 8))

    B_cent, _detJ_c = _point_B_planar(X, 0.0, 0.0)
    b_dil_cent = B_cent[:, 0, :] + B_cent[:, 1, :]
    N_c, _dN_c = _shape_functions(0.0, 0.0)
    cent_xy = np.einsum('a,eai->ei', N_c, X)

    for g, (sx, sy) in enumerate(_QUAD_SIGNS):
        xi, eta = _GAUSS_COORD * sx, _GAUSS_COORD * sy
        B, detJ = _point_B_planar(X, xi, eta)
        Bb = _bbar(B, b_dil_cent)
        # Gauss ağırlığı 1; birim kalınlık t = 1 m.
        Ke += detJ[:, None, None] * np.einsum('esi,st,etj->eij', Bb, D, Bb)
        Bbar_gauss[:, g] = Bb

    edof = _element_dof_map(mesh.elems)
    rows = np.repeat(edof, 8, axis=1).ravel()
    cols = np.tile(edof, (1, 8)).ravel()
    ndof = 2 * mesh.n_nodes
    K = sp.coo_matrix((Ke.ravel(), (rows, cols)), shape=(ndof, ndof)).tocsr()
    cache = {"Bbar_gauss": Bbar_gauss, "B_cent": B_cent,
             "cent_xy": cent_xy, "edof": edof}
    return K, cache


def _add_bore_pressure(F: np.ndarray, nodes: np.ndarray, edges: np.ndarray,
                       p: float) -> None:
    """Port basıncının tutarlı kenar kuvvetlerini F'ye ekler.

    Kenarlar artan θ sırasıyla verilir; tane bölgesi port sınırının +r
    tarafındadır. Kenar vektörü d = P2 − P1 (≈ ê_θ yönü); bölgeye bakan
    normal d'nin −90° dönüğüdür: (d_y, −d_x) (|n| = L). Lineer kenarda
    sabit basıncın tutarlı yükü her iki düğüme p·n/2.
    """
    if p == 0.0 or edges.size == 0:
        return
    P1 = nodes[edges[:, 0]]
    P2 = nodes[edges[:, 1]]
    d = P2 - P1
    n_unnorm = np.stack([d[:, 1], -d[:, 0]], axis=1)     # bölgeye bakan, |n|=L
    f_half = 0.5 * p * n_unnorm
    np.add.at(F, 2 * edges[:, 0], f_half[:, 0])
    np.add.at(F, 2 * edges[:, 0] + 1, f_half[:, 1])
    np.add.at(F, 2 * edges[:, 1], f_half[:, 0])
    np.add.at(F, 2 * edges[:, 1] + 1, f_half[:, 1])


def _symmetry_rotation(mesh: PlanarSectionMesh):
    """Eğik simetri kısıtı için düğüm dönüşü R ve yerel sabit serbestlikler.

    Dönüş: (R csr (2N×2N), sym_fixed_local: yerel çerçevede sıfırlanacak
    serbestlik indeksleri). R blokları [ê_r ê_t] sütunlarıdır; simetri
    kenarındaki düğümde yerel 2. serbestlik (düzleme dik bileşen, ê_t)
    sıfırlanır. Kenarda olmayan düğümlerde blok birimdir.
    """
    ndof = 2 * mesh.n_nodes
    diag = np.ones(ndof)
    rows = list(range(ndof))
    cols = list(range(ndof))
    vals = list(diag)
    sym_fixed = []

    def _apply(nodes_on_edge, angle):
        c, s = np.cos(angle), np.sin(angle)
        for n in np.asarray(nodes_on_edge, dtype=int):
            ix, iy = 2 * n, 2 * n + 1
            # Önce birim köşegeni sıfırla (aynı konuma toplanmasın diye
            # değerini geri alarak), sonra 2×2 bloğu yaz.
            vals[ix] = 0.0
            vals[iy] = 0.0
            rows.extend([ix, ix, iy, iy])
            cols.extend([ix, iy, ix, iy])
            vals.extend([c, -s, s, c])
            sym_fixed.append(iy)       # yerel 2. serbestlik = ê_t bileşeni

    if mesh.sym_start_nodes.size:
        _apply(mesh.sym_start_nodes, mesh.sym_start_angle)
    if mesh.sym_end_nodes.size:
        _apply(mesh.sym_end_nodes, mesh.sym_end_angle)

    R = sp.coo_matrix((vals, (rows, cols)), shape=(ndof, ndof)).tocsr()
    return R, sorted(set(sym_fixed))


def _check_well_posed(mesh: PlanarSectionMesh, outer_bc: str) -> None:
    """Rijit cisim modu bırakan BC bileşimlerini çözümden ÖNCE reddeder."""
    if outer_bc != "free":
        return
    if mesh.is_full:
        raise ValueError(
            "outer_bc='free' tam halkada tekildir: dönme rijit cisim modu "
            "hiçbir kısıtla tutulmaz. Serbest dış yüzey yalnız dilim "
            "kipinde (simetri kenarları dönmeyi tutar) çözülebilir.")
    span = mesh.sym_end_angle - mesh.sym_start_angle
    if abs(abs(span) - np.pi) < 1e-12:
        raise ValueError(
            "outer_bc='free' ve 180 derecelik dilim (N = 2) tekildir: iki "
            "simetri düzleminin normalleri paraleldir, düzlem boyu ötelenme "
            "rijit cisim modu serbest kalır. N >= 3 dilim ya da "
            "outer_bc='bonded_rigid' kullanılmalıdır.")


def _nodal_stress_spr_planar(mesh: PlanarSectionMesh, sig_cent: np.ndarray,
                             cent_xy: np.ndarray):
    """Zienkiewicz-Zhu SPR düğüm geri kazanımı (structural_axisym kurgusu).

    Örnekleme, bilineer Q4'ün süperyakınsak noktası olan eleman MERKEZİDİR;
    her iç köşe düğümünün yaması düğümü paylaşan 4 elemanın merkez
    değerleridir, bileşen bileşen lineer EKK fiti yapılır, sınır düğümleri
    en yakın iç yamadan değerlendirilir (ZZ 1992). Tam halkada seam sütunu
    sınır gibi ele alınır (çevresel yama sarımı yapılmaz; beyan meta'da).
    n_theta < 2 ya da n_radial < 2 ise None döner (çağıran yedek yola düşer).
    """
    n_th, n_rad = mesh.n_theta, mesh.n_radial
    if n_th < 2 or n_rad < 2:
        return None

    iv, jv = np.meshgrid(np.arange(1, n_th), np.arange(1, n_rad),
                         indexing="ij")
    iv, jv = iv.ravel(), jv.ravel()
    e00 = (iv - 1) * n_rad + (jv - 1)
    e01 = (iv - 1) * n_rad + jv
    e10 = iv * n_rad + (jv - 1)
    e11 = iv * n_rad + jv
    epatch = np.stack([e00, e01, e10, e11], axis=1)

    pts = cent_xy[epatch]                          # (P, 4, 2)
    vals = sig_cent[epatch]                        # (P, 4, C)
    vtx = mesh.nodes[mesh.node_index_grid[iv, jv]]

    dx = pts[:, :, 0] - vtx[:, None, 0]
    dy = pts[:, :, 1] - vtx[:, None, 1]
    scale_x = np.abs(dx).max(axis=1)
    scale_y = np.abs(dy).max(axis=1)
    if np.any(scale_x <= 0.0) or np.any(scale_y <= 0.0):
        return None
    Xd = np.stack([np.ones_like(dx), dx / scale_x[:, None],
                   dy / scale_y[:, None]], axis=2)
    G = np.einsum('pki,pkj->pij', Xd, Xd)
    rhs = np.einsum('pki,pks->pis', Xd, vals)
    coef = np.linalg.solve(G, rhs)

    # Değerlendirilecek istasyonlar: tam halkada seam kopyası (i = n_theta)
    # atlanır (aynı düğüm i = 0'da zaten yazılır).
    i_max = n_th if mesh.is_full else n_th + 1
    ni, nj = np.meshgrid(np.arange(i_max), np.arange(n_rad + 1),
                         indexing="ij")
    ni, nj = ni.ravel(), nj.ravel()
    pi = np.clip(ni, 1, n_th - 1)
    pj = np.clip(nj, 1, n_rad - 1)
    p_idx = (pi - 1) * (n_rad - 1) + (pj - 1)
    node_ids = mesh.node_index_grid[ni, nj]
    nxy = mesh.nodes[node_ids]
    dxn = (nxy[:, 0] - vtx[p_idx, 0]) / scale_x[p_idx]
    dyn = (nxy[:, 1] - vtx[p_idx, 1]) / scale_y[p_idx]
    vals_n = (coef[p_idx, 0, :]
              + coef[p_idx, 1, :] * dxn[:, None]
              + coef[p_idx, 2, :] * dyn[:, None])

    stress_nodal = np.empty((mesh.n_nodes, sig_cent.shape[1]))
    stress_nodal[node_ids] = vals_n
    return stress_nodal


def _nodal_stress_extrapolation_planar(mesh: PlanarSectionMesh,
                                       sig_gauss: np.ndarray) -> np.ndarray:
    """Yedek yol: Gauss→köşe √3 ekstrapolasyonu + düğüm ortalaması."""
    sqrt3 = np.sqrt(3.0)
    Ex = 0.25 * ((1.0 + sqrt3 * np.outer(_QUAD_SIGNS[:, 0], _QUAD_SIGNS[:, 0]))
                 * (1.0 + sqrt3 * np.outer(_QUAD_SIGNS[:, 1],
                                           _QUAD_SIGNS[:, 1])))
    sig_corner = np.einsum('ag,egs->eas', Ex, sig_gauss)
    C = sig_gauss.shape[-1]
    acc = np.zeros((mesh.n_nodes, C))
    cnt = np.zeros(mesh.n_nodes)
    np.add.at(acc, mesh.elems.ravel(), sig_corner.reshape(-1, C))
    np.add.at(cnt, mesh.elems.ravel(), 1.0)
    return acc / cnt[:, None]


def _bore_fiber_strain(mesh: PlanarSectionMesh, u: np.ndarray):
    """Port yüzeyi lif gerinimi — doğrudan yer değiştirme alanından.

    Her port kenarı için mühendislik gerinimi
        ε = (|P₂+u₂ − P₁−u₁| − |P₂−P₁|) / |P₂−P₁|
    (yüzey lifinin boy değişimi). Düğüm değeri komşu kenarların
    ortalamasıdır; tam halkada ilk/son istasyon aynı düğümdür ve sarımlı
    ortalama alınır.
    """
    edges = mesh.inner_edges
    P1 = mesh.nodes[edges[:, 0]]
    P2 = mesh.nodes[edges[:, 1]]
    U1 = u[edges[:, 0]]
    U2 = u[edges[:, 1]]
    L0 = np.hypot(*(P2 - P1).T)
    L1 = np.hypot(*((P2 + U2) - (P1 + U1)).T)
    eps_edge = (L1 - L0) / L0

    n_st = mesh.n_theta + 1
    eps_node = np.empty(n_st)
    if mesh.is_full:
        onceki = np.roll(eps_edge, 1)              # istasyon i'nin sol kenarı
        eps_node[:-1] = 0.5 * (onceki + eps_edge)
        eps_node[-1] = eps_node[0]
    else:
        eps_node[0] = eps_edge[0]
        eps_node[-1] = eps_edge[-1]
        eps_node[1:-1] = 0.5 * (eps_edge[:-1] + eps_edge[1:])
    return eps_edge, eps_node


def _result_meta_planar(outer_bc: str) -> dict:
    """Varsayım/NOT_MODELLED beyanı (sahte veri yasağı gereği)."""
    if outer_bc == "bonded_rigid":
        dis_beyan = (
            "u = 0 @ dış yüzey — RİJİT kasaya yapışık tane (case-bonded). "
            "Kasa esnemesi modellenmedi; esneyen kasa port gerinimini "
            "BÜYÜTÜR, bu seçim port gerinimi için alt-taraflı olabilir. "
            "Kasa esnemesini içeren analitik çözüm motorun "
            "grain_structural bloğundadır; ikisi birlikte okunmalıdır.")
    else:
        dis_beyan = ("dış yüzey SERBEST (traction-free) — Lamé doğrulama "
                     "kipi; gerçek case-bonded tane için 'bonded_rigid' "
                     "kullanılır.")
    return {
        "_source": "hrma.fea.planar_grain",
        "_basis": ("2B düzlem şekil değiştirme lineer elastik FEM; 4 düğümlü "
                   "bilineer quad + B-bar (ortalama dilatasyon, Hughes 1980 "
                   "— ν → 0.5 kilitlenme önlemi), 2x2 Gauss, scipy.sparse "
                   "doğrudan çözüm; birim kalınlık (1 m)"),
        "max_von_mises_kaynagi": "Gauss noktaları üzerinden maksimum",
        "bore_strain_kaynagi": (
            "port yüzeyi kenarlarının lif boy değişimi, doğrudan yer "
            "değiştirme alanından (gerilme geri kazanım hatasından "
            "bağımsız); kabul ölçütü NASA SP-8073 gereği GERİNİMDİR"),
        "sinir_kosullari": {
            "port": "sabit oda basıncı P_c (tutarlı kenar kuvvetleri)",
            "dis_yuzey": dis_beyan,
            "simetri": ("dilim kenarlarında kayar mesnet (ayna simetrisi; "
                        "eğik düzlemde RᵀKR dönüşümüyle)"),
        },
        "birimler": {"uzunluk": "m", "gerilme_basinc": "Pa",
                     "yer_degistirme": "m", "gerinim": "birim (m/m)"},
        "not_modelled": [
            "VİSKOELASTİSİTE — katı yakıt gerçekte viskoelastiktir (NASA "
            "SP-8073); bu kip lineer elastik ÖN BOYUTLANDIRMADIR, kabul "
            "analizi değildir",
            "termal büzülme/genleşme (kürleme soğuması) — motorun analitik "
            "grain_structural bloğu ayrıca verir",
            "kasa esnemesi (dış yüzey rijit tutulur)" if
            outer_bc == "bonded_rigid" else
            "kasa desteği (dış yüzey serbest bırakıldı — doğrulama kipi)",
            "uç etkileri / 3B eksenel değişim (düzlem şekil değiştirme: "
            "uzun tane, uçlar tutulu varsayımı)",
            "tane-kasa yapıştırma (bond) gerilmeleri",
            "yanma ile port büyümesi (t = 0 geometrisi çözülür)",
        ],
    }


def solve_plane_strain_section(mesh: PlanarSectionMesh,
                               material: Material,
                               bore_pressure_pa: float,
                               outer_bc: str = "bonded_rigid",
                               strain_capability: Optional[float] = None
                               ) -> PlanarGrainResult:
    """Tane kesiti için düzlem şekil değiştirme çözümü.

    Parametreler
    ------------
    mesh : mesh_planar.build_grain_section_mesh çıktısı.
    material : structural_axisym.Material (E, ν; akma alanı tane için
        kullanılmaz — kabul ölçütü gerinimdir).
    bore_pressure_pa : port iç yüzeyine etkiyen basınç [Pa] (>= 0).
    outer_bc : "bonded_rigid" (varsayılan) | "free" — modül docstring'i.
    strain_capability : yakıtın kopma uzaması (birim, 0-1) — verilirse
        gerinim emniyet katsayısı hesaplanır, verilmezse None beyan edilir.
    """
    if outer_bc not in OUTER_BC_MODES:
        raise ValueError(f"outer_bc {OUTER_BC_MODES} içinden olmalı.")
    p = float(bore_pressure_pa)
    if not np.isfinite(p) or p < 0.0:
        raise ValueError("bore_pressure_pa sonlu ve >= 0 olmalı.")
    if strain_capability is not None:
        strain_capability = float(strain_capability)
        if not np.isfinite(strain_capability) or strain_capability <= 0.0:
            raise ValueError("strain_capability verilirse sonlu ve > 0 "
                             "olmalı.")
    _check_well_posed(mesh, outer_bc)

    D = elasticity_matrix_plane_strain(material.E, material.nu)
    K, cache = _assemble_stiffness_planar(mesh, D)

    ndof = 2 * mesh.n_nodes
    F = np.zeros(ndof)
    _add_bore_pressure(F, mesh.nodes, mesh.inner_edges, p)

    # Eğik simetri kısıtı: yerel (ê_r, ê_t) çerçevesine dönüş.
    R, sym_fixed_local = _symmetry_rotation(mesh)
    K_hat = (R.T @ K @ R).tocsr()
    F_hat = R.T @ F

    fixed = np.zeros(ndof, dtype=bool)
    fixed[sym_fixed_local] = True
    if outer_bc == "bonded_rigid":
        fixed[2 * mesh.outer_nodes] = True
        fixed[2 * mesh.outer_nodes + 1] = True
    if not np.any(fixed):
        raise ValueError(
            "Hiç kısıt kalmadı (tam halka + serbest dış yüzey?): sistem "
            "tekil, çözüm denenmez.")

    free = ~fixed
    u_hat = np.zeros(ndof)
    K_ff = K_hat[free][:, free]
    u_free = spsolve(K_ff.tocsc(), F_hat[free])
    if not np.all(np.isfinite(u_free)):
        raise RuntimeError(
            "Doğrusal sistem çözümü sonlu değil (tekil/kötü koşullu K); "
            "sınır koşulları ve mesh gözden geçirilmeli.")
    u_hat[free] = u_free
    u = np.asarray(R @ u_hat)

    # Gerilmeler: σ̄ = D ε̄ (B-bar alanı); σ_z = ν(σ_x + σ_y).
    ue = u[cache["edof"]]                                  # (M, 8)
    eps_g = np.einsum('egsj,ej->egs', cache["Bbar_gauss"], ue)
    sig3_g = np.einsum('st,egt->egs', D, eps_g)            # (M, 4gp, 3)
    eps_c = np.einsum('esj,ej->es', cache["B_cent"], ue)
    sig3_c = eps_c @ D.T                                   # (M, 3)

    def _dort_bilesen(sig3):
        sz = material.nu * (sig3[..., 0] + sig3[..., 1])
        return np.stack([sig3[..., 0], sig3[..., 1], sz, sig3[..., 2]],
                        axis=-1)

    sig_gauss = _dort_bilesen(sig3_g)                      # (M, 4gp, 4)
    sig_cent = _dort_bilesen(sig3_c)                       # (M, 4)

    stress_nodal = _nodal_stress_spr_planar(mesh, sig_cent, cache["cent_xy"])
    if stress_nodal is not None:
        yontem = ("Zienkiewicz-Zhu SPR: iç köşe yamalarında 4 eleman merkezi "
                  "(Barlow noktası) değerine lineer EKK; sınır düğümleri en "
                  "yakın iç yamadan (ZZ 1992). Tam halkada seam sütunu sınır "
                  "gibi ele alınır (çevresel yama sarımı yok).")
    else:
        stress_nodal = _nodal_stress_extrapolation_planar(mesh, sig_gauss)
        yontem = ("Gauss→köşe sqrt(3) ekstrapolasyonu + düğüm ortalaması "
                  "(SPR yaması kurulamadı: n_theta < 2 ya da n_radial < 2)")

    vm_gauss = von_mises_plane_strain(sig_gauss)
    vm_nodal = von_mises_plane_strain(stress_nodal)
    max_vm = float(vm_gauss.max())
    max_vm_nodal = float(vm_nodal.max())
    sp_nodal = max_principal_plane_strain(stress_nodal)

    u2 = u.reshape(-1, 2)
    eps_edge, eps_node = _bore_fiber_strain(mesh, u2)
    i_max = int(np.argmax(np.abs(eps_node)))
    max_bore = float(eps_node[i_max])
    if strain_capability is not None and abs(max_bore) > 0.0:
        margin = float(strain_capability / abs(max_bore))
    elif strain_capability is not None:
        margin = float("inf")
    else:
        margin = None

    meta = _result_meta_planar(outer_bc)
    meta["stress_nodal_kaynagi"] = yontem
    meta["malzeme"] = {"E_Pa": material.E, "nu": material.nu,
                       "ad": material.name}
    meta["yukler"] = {"bore_pressure_Pa": p}
    meta["simetri"] = mesh.meta.get("simetri")
    if strain_capability is None:
        meta["strain_margin_durumu"] = (
            "HESAPLANMADI — kopma uzaması (strain_capability) verilmedi; "
            "uydurma değer konmaz")
    else:
        meta["strain_margin_temeli"] = (
            "strain_capability / |maks port lif gerinimi| — kopma uzaması "
            "çağıranın verdiği SOLID_GRAIN_MECHANICS kaydından")

    return PlanarGrainResult(
        displacement=u2,
        stress_nodal=stress_nodal,
        stress_gauss=sig_gauss,
        von_mises_nodal=vm_nodal,
        von_mises_gauss=vm_gauss,
        max_von_mises=max_vm,
        max_von_mises_nodal=max_vm_nodal,
        max_principal_nodal=sp_nodal,
        bore_node_ids=mesh.node_index_grid[:, 0].copy(),
        bore_strain_edges=eps_edge,
        bore_strain_nodal=eps_node,
        max_bore_strain=max_bore,
        strain_margin=margin,
        meta=meta,
    )


def solve_grain_with_refinement(r_inner: Union[float, Callable],
                                r_outer: float,
                                material: Material,
                                bore_pressure_pa: float,
                                symmetry_fraction: int = 1,
                                theta_start: float = 0.0,
                                outer_bc: str = "bonded_rigid",
                                strain_capability: Optional[float] = None,
                                tol: float = DEFAULT_REFINE_TOL,
                                n_theta0: int = DEFAULT_N_THETA0,
                                n_radial0: int = DEFAULT_ELEMS_THROUGH_WALL,
                                max_rounds: int = DEFAULT_MAX_REFINE_ROUNDS
                                ) -> GrainRefinementResult:
    """Ardışık inceltme sürücüsü (structural_axisym.solve_with_refinement
    deseni): her turda çevresel ve radyal bölüm REFINE_FACTOR ile çarpılır,
    hedef büyüklük son iki turda bağıl ``tol`` altında değişince durulur.
    Yakınsamazsa ``converged=False`` + açık beyan döner — yakınsamamış
    sonuç yakınsamış gibi sunulmaz.

    Hedef büyüklük MAKS DÜĞÜM von Mises'idir (SPR alanı): tane probleminde
    tepe gerilme PORT SINIRINDA oturur; Gauss noktası sınıra ancak O(h)
    yaklaştığı için Gauss maksimumu alan yakınsadıktan sonra bile tur
    başına ~%2 büyümeye devam eder (ölçüldü — PlanarGrainResult docstring'i),
    SPR sınır değeri ise O(h²) yakınsar. Gauss maksimumu yine hesaplanır ve
    geçmişte raporlanır; hedef seçimi beyanlıdır.

    DİKKAT (beyan): keskin iç köşeli kesitlerde (star ucu kökü gibi) tepe
    gerilme mesh inceldikçe BÜYÜMEYE devam edebilir — keskin köşe lineer
    elastisitede tekildir ve modelde fileto yarıçapı yoktur (motorun kendi
    kesit poligonu da modellemez). Böyle koşularda converged=False beyanı
    kusur değil, modelin dürüst sınırıdır.
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
        n_th = int(n_theta0) * REFINE_FACTOR ** k
        n_rad = int(n_radial0) * REFINE_FACTOR ** k
        mesh = build_grain_section_mesh(r_inner, r_outer, n_th, n_rad,
                                        symmetry_fraction=symmetry_fraction,
                                        theta_start=theta_start)
        result = solve_plane_strain_section(
            mesh, material, bore_pressure_pa, outer_bc=outer_bc,
            strain_capability=strain_capability)
        vm = result.max_von_mises_nodal        # hedef: SPR düğüm maksimumu
        if prev_vm is not None:
            scale = max(abs(vm), abs(prev_vm), 1e-300)
            rel_change = abs(vm - prev_vm) / scale
        history.append({
            "n_elems": mesh.n_elems,
            "n_theta": mesh.n_theta,
            "n_radial": mesh.n_radial,
            "max_von_mises": vm,               # hedef büyüklük (düğüm/SPR)
            "max_von_mises_gauss": result.max_von_mises,
            "max_bore_strain": result.max_bore_strain,
            "rel_change": rel_change,
        })
        if rel_change is not None and rel_change < tol:
            converged = True
            break
        prev_vm = vm

    if converged:
        beyan = (f"Mesh yakınsadı: {mesh.n_elems} eleman; son iki inceltme "
                 f"turu arasında maks von Mises (SPR düğüm alanı) farkı "
                 f"%{100.0 * rel_change:.2f} (tolerans %{100.0 * tol:.2f}).")
    elif rel_change is None:
        beyan = (f"YAKINSAMA DENETLENEMEDİ: tek tur koşuldu "
                 f"({mesh.n_elems} eleman); karşılaştırılacak ikinci tur yok.")
    else:
        beyan = (f"YAKINSAMADI: {max_rounds + 1} turda son fark "
                 f"%{100.0 * rel_change:.2f} tolerans %{100.0 * tol:.2f} "
                 f"altına inmedi ({mesh.n_elems} eleman). Keskin iç köşeli "
                 "kesitte (star ucu kökü) tepe gerilme lineer elastisitede "
                 "TEKİLDİR ve mesh ile büyümeye devam eder; sonuç bu beyanla "
                 "birlikte değerlendirilmelidir.")

    meta = {
        "_source": "hrma.fea.planar_grain.solve_grain_with_refinement",
        "_basis": ("ardışık tekdüze inceltme; hedef büyüklük maks von Mises "
                   "(SPR DÜĞÜM alanı — tepe port sınırında, Gauss maksimumu "
                   "sınıra O(h) yaklaştığı için hedef olamaz; ölçüm modül "
                   f"docstring'inde), tolerans {tol} bağıl değişim, çarpan "
                   f"{REFINE_FACTOR} (structural_axisym ile ortak politika)"),
        "beyan": beyan,
        "converged": converged,
        "n_elems_final": mesh.n_elems,
        "final_rel_change": rel_change,
        "tol": tol,
    }

    return GrainRefinementResult(
        result=result,
        mesh=mesh,
        converged=converged,
        history=history,
        final_rel_change=rel_change,
        tol=tol,
        meta=meta,
    )
