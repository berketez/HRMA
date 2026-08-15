"""
Katı yakıt tanesi KESİTİ için 2B düzlemsel yapısal quad mesh üreticisi
(V2.7 Aşama C — docs/mimari/yol-haritasi.md §5: star/finocyl/slotted
kesitleri eksenel simetrik DEĞİLDİR, ayrı düzlemsel kip gerekir).

Bölge: iç sınır = port çevresi, dış sınır = tane dış yarıçapı (kasa iç
yüzeyi). Port sınırı ORİJİNE GÖRE YILDIZ-ŞEKİLLİ (star-shaped) olmalıdır:
orijinden çıkan her ışın port sınırını tam bir kez keser, yani sınır tek
değerli bir r_iç(θ) fonksiyonudur. Motorun ürettiği kesitlerin hepsi bu
sınıftadır — bates (daire), star (zikzak çokgen), slotted/finocyl (merkez
daire ∪ merkezden çıkan radyal dörtgenler; orijine göre yıldız-şekilli
kümelerin birleşimi yine yıldız-şekillidir). Wagon-wheel (ayrık delikler)
bu sınıfta DEĞİLDİR ve bu üretici onu desteklemez; köprü katmanı bunu
beyanla reddeder.

Yöntem
------
1. θ ∈ [θ₀, θ₀ + 2π/N] yayı ``n_theta + 1`` istasyona bölünür (N =
   ``symmetry_fraction``; N = 1 tam halka, seam düğümleri birleştirilir).
2. Her istasyonda iç yarıçap r_iç(θ_i) örneklenir: skaler (daire),
   çağrılabilir, ya da ``port_radius_sampler_from_polygon`` ile motor
   poligonundan ışın-kesişimiyle. Radyal doğrultuda r_iç → r_dış arası
   ``n_radial`` eşit katman serilir.
3. Eleman köşeleri CCW sıralanır; her elemanın dört köşesinde bilineer
   Jacobian işareti denetlenir (mesh_axisym ile AYNI denetim — ters/dejenere
   eleman sessizce verilmez, hata fırlatılır).

Simetri beyanı
--------------
Dilim kipinde (N > 1) iki radyal kenar AYNA SİMETRİ DÜZLEMİ varsayılır:
çağıran, θ₀ ve θ₀ + 2π/N açılarının kesitin gerçek ayna düzlemlerinden
geçtiğini garanti etmelidir (motor kesitlerinde uç/yuva merkezi θ = 0
eksenindedir; bkz. solid_rocket_engine._cached_star_polygon /
_cached_slot_quads kuruluşu). Simetri kenar düğüm kümeleri mesh üstünde
yayımlanır; kayar mesnet (roller) sınır koşulunu çözücü uygular.

Kalınlık boyunca eleman alt sınırı mesh_axisym'in MERKEZÎ sabitidir
(MIN_ELEMS_THROUGH_WALL) — parametre tutarlılığı kuralı gereği burada
sayı tekrarlanmaz.

Kaynaklar
---------
* Zienkiewicz & Taylor, "The Finite Element Method", 5. baskı, Cilt 1,
  Böl. 8-9 (izoparametrik dörtgen eleman geometrisi) — eleman bağlamı.
* docs/V2.7_ANALIZ_MODULU.md §3 — harici mesh bağımlılığı yok kararı
  (numpy yeterli; yapısal grid).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Union

import numpy as np

from hrma.fea.mesh_axisym import (
    MIN_ELEMS_THROUGH_WALL,
    _corner_jacobian_check,
)

#: Tam halka (N = 1) kipinde izin verilen en az çevresel bölüm — üçgenimsi
#: aşırı çarpık quad üretimini baştan keser (Jacobian denetimi son savunmadır).
MIN_THETA_DIVISIONS_FULL = 8

#: Dilim kipinde en az çevresel bölüm (tek elemanlı yay, köşe gerilmesini
#: temsil edemez; yakınsama sürücüsü zaten katlar).
MIN_THETA_DIVISIONS_WEDGE = 2

#: Işın-poligon kesişim toleransı (parametrik t için). Köşeden geçen ışın
#: iki komşu parçayı da yakalayabilir; en dıştaki kesişim alınır.
_RAY_T_TOL = 1e-9


@dataclass
class PlanarSectionMesh:
    """(x, y) düzleminde tane kesiti yapısal 4-düğümlü quad mesh.

    Alanlar
    -------
    nodes : (N, 2) float — düğüm koordinatları [x, y], metre.
    elems : (M, 4) int — CCW köşe bağlantıları.
    node_index_grid : (n_theta+1, n_radial+1) int — yapısal (i, j)
        indeksinden düğüm numarasına harita. i çevresel istasyon (artan θ),
        j radyal katman (j = 0 PORT yüzeyi, j = n_radial dış yüzey).
        Tam halkada son sütun ilk sütunun düğümleridir (seam birleşik).
    inner_edges / outer_edges : (n_theta, 2) int — port/dış yüzey kenarları,
        artan θ sırasıyla düğüm çiftleri (basınç yükü bu sıralamaya dayanır).
    inner_nodes / outer_nodes : int dizileri — tekrarsız yüzey düğümleri.
    sym_start_nodes / sym_end_nodes : int dizileri — dilim kipinde iki
        simetri kenarının düğümleri (tam halkada boş).
    sym_start_angle / sym_end_angle : simetri düzlemlerinin açıları [rad].
    symmetry_fraction : int — N; 1 = tam halka.
    meta : dict — üretim beyanı (_basis/_source, simetri varsayımı).
    """

    nodes: np.ndarray
    elems: np.ndarray
    node_index_grid: np.ndarray
    inner_edges: np.ndarray
    outer_edges: np.ndarray
    inner_nodes: np.ndarray
    outer_nodes: np.ndarray
    sym_start_nodes: np.ndarray
    sym_end_nodes: np.ndarray
    sym_start_angle: float
    sym_end_angle: float
    n_theta: int
    n_radial: int
    symmetry_fraction: int
    meta: dict = field(default_factory=dict)

    @property
    def n_nodes(self) -> int:
        return self.nodes.shape[0]

    @property
    def n_elems(self) -> int:
        return self.elems.shape[0]

    @property
    def is_full(self) -> bool:
        return self.symmetry_fraction == 1


def port_radius_sampler_from_polygon(coords) -> Callable[[np.ndarray],
                                                         np.ndarray]:
    """Kapalı port çokgeninden r_iç(θ) örnekleyicisi (ışın kesişimi).

    coords : (n, 2) dizi benzeri — port sınırının köşeleri (kapalı halka;
        ilk = son nokta tekrarına gerek yok, varsa zararsız). Kaynak, motorun
        KENDİ poligon fonksiyonlarıdır (shapely ``exterior.coords``) —
        geometri burada yeniden türetilmez.

    Sınır orijine göre yıldız-şekilli olmalıdır: her θ için orijinden çıkan
    ışın sınırı kesmelidir. Kesmeyen açı bulunursa hata fırlatılır (kesit
    bu üreticinin varsayımı dışındadır; sessiz uydurma yok). Köşeden geçen
    ışında en dıştaki kesişim alınır (port sınırı = en dış kesişim).
    """
    pts = np.asarray(coords, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or pts.shape[0] < 3:
        raise ValueError("Port çokgeni (n, 2) biçiminde ve en az 3 noktalı "
                         "olmalı.")
    if not np.all(np.isfinite(pts)):
        raise ValueError("Port çokgeni sonlu olmayan koordinat içeriyor.")
    # Kapalı halka: son nokta ilkini tekrarlamıyorsa kapat.
    if not np.allclose(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[0]])
    A = pts[:-1]                       # (S, 2) parça başları
    E = pts[1:] - pts[:-1]             # (S, 2) parça vektörleri

    def sampler(thetas):
        th = np.atleast_1d(np.asarray(thetas, dtype=float))
        d = np.stack([np.cos(th), np.sin(th)], axis=1)        # (K, 2)
        # s·d = A + t·E  →  s = cross(A, E)/cross(d, E), t = cross(A, d)/cross(d, E)
        cross_dE = d[:, None, 0] * E[None, :, 1] - d[:, None, 1] * E[None, :, 0]
        cross_AE = A[None, :, 0] * E[None, :, 1] - A[None, :, 1] * E[None, :, 0]
        cross_Ad = (A[None, :, 0] * d[:, None, 1]
                    - A[None, :, 1] * d[:, None, 0])
        # s·d = A + t·E; E ile çapraz: s(d×E) = A×E; d ile çapraz:
        # 0 = (A×d) + t(E×d) → t = (A×d)/(d×E).
        with np.errstate(divide="ignore", invalid="ignore"):
            s = cross_AE / cross_dE
            t = cross_Ad / cross_dE
        ok = (np.abs(cross_dE) > 0.0) & (t >= -_RAY_T_TOL) \
            & (t <= 1.0 + _RAY_T_TOL) & (s > 0.0) & np.isfinite(s)
        s = np.where(ok, s, -np.inf)
        r = s.max(axis=1)
        if np.any(~np.isfinite(r)) or np.any(r <= 0.0):
            kotu = th[~np.isfinite(r) | (r <= 0.0)]
            raise ValueError(
                "Port sınırı bazı açılarda orijin ışınıyla kesişmiyor "
                f"(örn. θ = {float(kotu[0]):.6f} rad): kesit orijine göre "
                "yıldız-şekilli değil ya da orijin port dışında. Bu üretici "
                "yalnız tek değerli r(θ) sınırları destekler.")
        return r if np.ndim(thetas) else float(r[0])

    return sampler


def _resolve_inner_radius(r_inner, thetas: np.ndarray) -> np.ndarray:
    """r_inner (skaler | çağrılabilir) → istasyon dizisi; geçerlilik denetimli."""
    if callable(r_inner):
        r = np.asarray(r_inner(thetas), dtype=float)
        if r.shape != thetas.shape:
            raise ValueError("r_inner çağrılabiliri istasyon sayısı kadar "
                             "değer döndürmeli.")
    else:
        r = np.full_like(thetas, float(r_inner))
    if not np.all(np.isfinite(r)) or np.any(r <= 0.0):
        raise ValueError("İç (port) yarıçapı her istasyonda sonlu ve kesin "
                         "pozitif olmalı.")
    return r


def build_grain_section_mesh(r_inner: Union[float, Callable],
                             r_outer: float,
                             n_theta: int,
                             n_radial: int,
                             symmetry_fraction: int = 1,
                             theta_start: float = 0.0) -> PlanarSectionMesh:
    """Tane kesiti (port → dış yarıçap) yapısal quad mesh'i üretir.

    Parametreler
    ------------
    r_inner : float veya çağrılabilir θ→r [m] — port sınırı. Çokgen için
        ``port_radius_sampler_from_polygon`` kullanılır.
    r_outer : float [m] — tane dış yarıçapı (kasa iç yüzeyi).
    n_theta : int — çevresel eleman sayısı (dilim başına).
    n_radial : int — web boyunca eleman sayısı; MIN_ELEMS_THROUGH_WALL
        altındaki istekler alt sınıra ÇEKİLİR ve meta'da beyan edilir
        (mesh_axisym ile aynı politika).
    symmetry_fraction : int — N. N > 1: 1/N dilim, radyal kenarlar ayna
        simetri düzlemi VARSAYILIR (beyan meta'da). N = 1: tam halka,
        seam düğümleri birleştirilir.
    theta_start : float [rad] — dilimin başlangıç açısı (varsayılan 0;
        motor kesitlerinde uç/yuva merkezi θ = 0 düzlemindedir).

    Dönüş: PlanarSectionMesh. Ters/dejenere eleman ve negatif web (port
    sınırı dış yarıçapı aşan istasyon) durumlarında ValueError.
    """
    if not isinstance(symmetry_fraction, (int, np.integer)) \
            or symmetry_fraction < 1:
        raise ValueError("symmetry_fraction >= 1 tam sayı olmalı.")
    if not isinstance(n_theta, (int, np.integer)) or n_theta < 1:
        raise ValueError("n_theta >= 1 tam sayı olmalı.")
    if not isinstance(n_radial, (int, np.integer)) or n_radial < 1:
        raise ValueError("n_radial >= 1 tam sayı olmalı.")
    r_outer = float(r_outer)
    if not np.isfinite(r_outer) or r_outer <= 0.0:
        raise ValueError("r_outer sonlu ve kesin pozitif olmalı.")

    full = (symmetry_fraction == 1)
    min_theta = MIN_THETA_DIVISIONS_FULL if full else MIN_THETA_DIVISIONS_WEDGE
    n_theta_requested = int(n_theta)
    n_theta = max(n_theta_requested, min_theta)
    n_radial_requested = int(n_radial)
    n_radial = max(n_radial_requested, MIN_ELEMS_THROUGH_WALL)

    span = 2.0 * np.pi / symmetry_fraction
    thetas = float(theta_start) + np.linspace(0.0, span, n_theta + 1)
    r_in = _resolve_inner_radius(r_inner, thetas)

    if full:
        # Seam istasyonu (θ₀ + 2π) fiziksel olarak θ₀'dır; r_iç örneklemesi
        # sayısal olarak da aynı olmalı — değilse sınır tek değerli değildir.
        if not np.isclose(r_in[0], r_in[-1], rtol=1e-9, atol=0.0):
            raise ValueError(
                "Tam halkada r_iç(θ₀) ile r_iç(θ₀ + 2π) uyuşmuyor: port "
                "sınırı kapalı/tek değerli değil.")
        r_in[-1] = r_in[0]

    # Negatif web denetimi: port sınırı hiçbir istasyonda dış yarıçapa
    # dayanamaz/aşamaz (tane webi kesin pozitif olmalı).
    if np.any(r_in >= r_outer):
        i_kotu = int(np.argmax(r_in))
        raise ValueError(
            "Negatif/sıfır web: port yarıçapı "
            f"({float(r_in[i_kotu]):.6f} m @ θ = {float(thetas[i_kotu]):.4f} "
            f"rad) tane dış yarıçapını ({r_outer:.6f} m) aşıyor ya da ona "
            "dayanıyor. Geometri fiziksel değil; mesh üretilmez.")

    # Düğümler: node(i, j) = [r_iç(θ_i) + (j/n_radial)(r_dış − r_iç(θ_i))]·ê_r(θ_i)
    frac = np.arange(n_radial + 1) / n_radial                  # (n_radial+1,)
    radii = r_in[:, None] + frac[None, :] * (r_outer - r_in[:, None])
    ct, st = np.cos(thetas), np.sin(thetas)
    grid_pts = np.stack([radii * ct[:, None], radii * st[:, None]], axis=2)

    if full:
        # Seam birleşik: son istasyonun düğümleri ilkinin kendisidir.
        nodes = grid_pts[:-1].reshape(-1, 2)
        node_index_grid = np.empty((n_theta + 1, n_radial + 1), dtype=np.int64)
        node_index_grid[:-1] = np.arange(
            n_theta * (n_radial + 1)).reshape(n_theta, n_radial + 1)
        node_index_grid[-1] = node_index_grid[0]
    else:
        nodes = grid_pts.reshape(-1, 2)
        node_index_grid = np.arange(nodes.shape[0]).reshape(n_theta + 1,
                                                            n_radial + 1)

    # CCW köşe sırası: (+r, +θ, −r, −θ) turu — (ê_r, ê_θ) sağ el çifti.
    n00 = node_index_grid[:-1, :-1].ravel()
    n01 = node_index_grid[:-1, 1:].ravel()
    n11 = node_index_grid[1:, 1:].ravel()
    n10 = node_index_grid[1:, :-1].ravel()
    elems = np.stack([n00, n01, n11, n10], axis=1).astype(np.int64)

    _corner_jacobian_check(nodes, elems)

    inner_edges = np.stack([node_index_grid[:-1, 0],
                            node_index_grid[1:, 0]], axis=1).astype(np.int64)
    outer_edges = np.stack([node_index_grid[:-1, -1],
                            node_index_grid[1:, -1]], axis=1).astype(np.int64)

    if full:
        sym_start = np.empty(0, dtype=np.int64)
        sym_end = np.empty(0, dtype=np.int64)
        simetri_beyani = ("tam halka (N = 1): simetri kenarı yok, seam "
                         "düğümleri birleştirildi")
    else:
        sym_start = node_index_grid[0, :].copy()
        sym_end = node_index_grid[-1, :].copy()
        simetri_beyani = (
            f"1/{symmetry_fraction} dilim: θ = {float(thetas[0]):.6f} ve "
            f"θ = {float(thetas[-1]):.6f} rad radyal kenarları AYNA SİMETRİ "
            "DÜZLEMİ varsayılır (kayar mesnet çözücüde uygulanır); çağıran "
            "bu açıların kesitin gerçek ayna düzlemleri olduğunu garanti "
            "etmelidir")

    meta = {
        "_source": "hrma.fea.mesh_planar.build_grain_section_mesh",
        "_basis": ("çevresel istasyon × radyal katman yapısal quad; iç sınır "
                   "r_iç(θ) örneklemesi, dış sınır sabit yarıçap; köşe "
                   "Jacobian denetimi mesh_axisym ile ortak"),
        "symmetry_fraction": int(symmetry_fraction),
        "simetri": simetri_beyani,
        "n_theta_istenen": n_theta_requested,
        "n_theta_kullanilan": int(n_theta),
        "n_radial_istenen": n_radial_requested,
        "n_radial_kullanilan": int(n_radial),
        "n_radial_alt_sinira_cekildi": n_radial_requested < n_radial,
        "birimler": {"uzunluk": "m"},
    }

    return PlanarSectionMesh(
        nodes=nodes,
        elems=elems,
        node_index_grid=node_index_grid,
        inner_edges=inner_edges,
        outer_edges=outer_edges,
        inner_nodes=np.unique(node_index_grid[:, 0]),
        outer_nodes=np.unique(node_index_grid[:, -1]),
        sym_start_nodes=sym_start,
        sym_end_nodes=sym_end,
        sym_start_angle=float(thetas[0]),
        sym_end_angle=float(thetas[-1]),
        n_theta=int(n_theta),
        n_radial=int(n_radial),
        symmetry_fraction=int(symmetry_fraction),
        meta=meta,
    )
