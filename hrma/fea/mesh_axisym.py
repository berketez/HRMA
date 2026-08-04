"""
Eksenel simetrik (z, r) düzleminde yapısal quad mesh üreticisi.

Kamara/lüle cidarı gibi "iç kontur + cidar kalınlığı" ile tanımlı bölgeler
için i×j indeksli, tamamen yapısal (structured) dörtgen mesh üretir. Serbest
üçgenleme ve gmsh bağımlılığı bilinçli olarak YOKTUR (docs/V2.7_ANALIZ_MODULU.md
§3: süpürme profili elimizde olduğu için kendi yapısal quad mesh'imiz yeterli).

Yöntem
------
1. İç kontur [(z, r_iç)] yay uzunluğuna göre ``n_axial + 1`` istasyona yeniden
   örneklenir (dik/boğaz bölgelerinde z'ye göre örneklemeden daha dengeli).
2. Her istasyonda kontur teğeti merkezî farkla bulunur; cidar, teğete DİK
   doğrultuda (``offset_mode="normal"``, varsayılan) veya saf radyal
   doğrultuda (``offset_mode="radial"``) dışa ötelenir. Radyal kipte gerçek
   dik cidar kalınlığı eğimli bölgede t·cos(θ) olur — bu dürüstçe bilinmeli;
   varsayılan bu yüzden "normal" kiptir.
3. Kalınlık boyunca ``n_radial`` eleman katmanı serilir. İnce cidarda gerilme
   gradyanı çözülebilsin diye katman sayısı hiçbir koşulda
   ``MIN_ELEMS_THROUGH_WALL`` altına inmez (V2.7 §3: "cidar kalınlığı boyunca
   en az 3-4 eleman").
4. Her elemanın dört köşesinde bilineer dönüşümün Jacobian işareti denetlenir
   (bilineer eşlemede det J, ξ ve η'da ayrı ayrı lineerdir; dört köşede
   pozitiflik iç bölgede pozitifliği garantiler). Ters dönmüş/dejenere eleman
   üretilmişse mesh sessizce verilmez, hata fırlatılır.

Sınırlar
--------
* r ≤ 0 düğüm üretilmez (eksenel simetrik elastisite B matrisi 1/r terimi
  taşır; cidar bölgesi zaten ekseni içermez). Kontur r_iç ≤ 0 içeriyorsa hata.
* Kontur z boyunca ilerlemelidir (yeniden örneklenmiş z kesin artan olmalı).

Kaynaklar
---------
* docs/V2.7_ANALIZ_MODULU.md §3 — mesh politikası kararı.
* Zienkiewicz & Taylor, "The Finite Element Method", 5. baskı, Cilt 1,
  Böl. 5 (eksenel simetrik gerilme analizi) — eleman geometrisi bağlamı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

import numpy as np

# ---------------------------------------------------------------------------
# Cidar boyunca eleman sayısı politikası — MERKEZÎ tanım.
# Testler ve çözücü bu sabitleri import eder; sayı başka yerde tekrarlanmaz
# (parametre tutarlılığı kuralı).
# ---------------------------------------------------------------------------
MIN_ELEMS_THROUGH_WALL = 3       # V2.7 §3: "en az 3-4 eleman" alt sınırı
DEFAULT_ELEMS_THROUGH_WALL = 4   # varsayılan başlangıç katman sayısı

_OFFSET_MODES = ("normal", "radial")


@dataclass
class AxisymMesh:
    """(z, r) düzleminde yapısal 4-düğümlü quad mesh.

    Alanlar
    -------
    nodes : (N, 2) float — düğüm koordinatları [z, r], metre.
    elems : (M, 4) int — eleman bağlantıları, (z, r) düzleminde saat yönünün
        tersine (CCW) sıralı köşeler.
    node_index_grid : (n_axial+1, n_radial+1) int — yapısal (i, j) indeksinden
        düğüm numarasına harita. j=0 iç yüzey, j=n_radial dış yüzey.
    inner_edges / outer_edges : (n_axial, 2) int — iç/dış yüzey kenarları,
        artan istasyon (i → i+1) sırasıyla düğüm çiftleri. Basınç yükü bu
        kenarlara uygulanır; sıralama yön (normal) hesabında kullanılır.
    inner_nodes / outer_nodes / z_min_nodes / z_max_nodes : int dizileri —
        yüzey ve uç kesit düğüm kümeleri.
    meta : dict — üretim beyanı (_basis/_source): kaynak fonksiyon, öteleme
        kipi, istenen/kullanılan katman sayısı vb.
    """

    nodes: np.ndarray
    elems: np.ndarray
    node_index_grid: np.ndarray
    inner_edges: np.ndarray
    outer_edges: np.ndarray
    inner_nodes: np.ndarray
    outer_nodes: np.ndarray
    z_min_nodes: np.ndarray
    z_max_nodes: np.ndarray
    n_axial: int
    n_radial: int
    meta: dict = field(default_factory=dict)

    @property
    def n_nodes(self) -> int:
        return self.nodes.shape[0]

    @property
    def n_elems(self) -> int:
        return self.elems.shape[0]

    def boundary_nodes(self) -> np.ndarray:
        """Sınır (iç yüzey + dış yüzey + iki uç kesit) düğümleri, tekrarsız."""
        return np.unique(np.concatenate([
            self.inner_nodes, self.outer_nodes,
            self.z_min_nodes, self.z_max_nodes,
        ]))

    def interior_nodes(self) -> np.ndarray:
        """Sınırda olmayan düğümler."""
        return np.setdiff1d(np.arange(self.n_nodes), self.boundary_nodes())


def _resample_contour(contour: np.ndarray, thickness: np.ndarray,
                      n_axial: int):
    """Konturu yay uzunluğuna göre eşit aralıklı istasyonlara örnekler."""
    seg = np.diff(contour, axis=0)
    ds = np.hypot(seg[:, 0], seg[:, 1])
    if np.any(ds <= 0.0):
        raise ValueError(
            "Konturda üst üste binen (sıfır uzunluklu) ardışık nokta var; "
            "mesh üretilemez.")
    s = np.concatenate([[0.0], np.cumsum(ds)])
    s_new = np.linspace(0.0, s[-1], n_axial + 1)
    z_i = np.interp(s_new, s, contour[:, 0])
    r_i = np.interp(s_new, s, contour[:, 1])
    t_i = np.interp(s_new, s, thickness)
    return s_new, z_i, r_i, t_i


def _corner_jacobian_check(nodes: np.ndarray, elems: np.ndarray) -> None:
    """Her elemanın dört köşesinde bilineer det J > 0 denetimi.

    Bilineer eşlemede det J = A + Bξ + Cη (ξη terimi yok); dört köşede
    pozitifse eleman içinde her yerde pozitiftir. Köşe det J işareti, köşeden
    çıkan iki kenar vektörünün çapraz çarpımının işaretiyle aynıdır.
    """
    P = nodes[elems]                       # (M, 4, 2)
    e_next = np.roll(P, -1, axis=1) - P    # e_k = P_{k+1} - P_k (çıkan kenar)
    e_in = np.roll(e_next, 1, axis=1)      # e_{k-1} (köşeye gelen kenar)
    # CCW + dejenere olmayan eleman koşulu: cross(e_{k-1}, e_k) > 0.
    cross = e_in[:, :, 0] * e_next[:, :, 1] - e_in[:, :, 1] * e_next[:, :, 0]
    bad = np.any(cross <= 0.0, axis=1)
    if np.any(bad):
        raise ValueError(
            f"{int(bad.sum())} eleman ters dönmüş veya dejenere (köşe "
            "Jacobian'ı <= 0). Kontur eğriliği ile cidar kalınlığı/öteleme "
            "kipi uyumsuz; n_axial artırılabilir veya offset_mode='radial' "
            "denenebilir.")


def build_wall_mesh(contour,
                    thickness: Union[float, np.ndarray],
                    n_axial: int,
                    n_radial: int = DEFAULT_ELEMS_THROUGH_WALL,
                    offset_mode: str = "normal") -> AxisymMesh:
    """İç kontur + cidar kalınlığından yapısal quad mesh üretir.

    Parametreler
    ------------
    contour : (n, 2) dizi benzeri — iç yüzey noktaları [(z, r_iç)], metre.
        Cidar boyunca sıralı (akış yönünde) verilmelidir; r_iç > 0 zorunlu.
    thickness : float veya (n,) dizi — cidar kalınlığı t(z), metre. Dizi
        verilirse kontur noktalarıyla aynı sırada olmalıdır; istasyonlara
        yay uzunluğu üzerinden enterpole edilir.
    n_axial : int — eksenel (kontur boyu) eleman sayısı, >= 1.
    n_radial : int — kalınlık boyunca eleman sayısı. MIN_ELEMS_THROUGH_WALL
        altındaki istekler sessizce reddedilmez; alt sınıra ÇEKİLİR ve bu
        durum ``meta['n_radial_istenen']`` / ``meta['n_radial_kullanilan']``
        alanlarında beyan edilir.
    offset_mode : "normal" (varsayılan) — cidar kontur teğetine dik ötelenir,
        dik kalınlık tam t olur; "radial" — saf +r ötelemesi, eğimli bölgede
        dik kalınlık t·cos(θ).

    Dönüş
    -----
    AxisymMesh — düğümler, elemanlar, yüzey kenar/düğüm kümeleri ve üretim
    beyanı (meta).
    """
    contour = np.asarray(contour, dtype=float)
    if contour.ndim != 2 or contour.shape[1] != 2 or contour.shape[0] < 2:
        raise ValueError("contour (n, 2) biçiminde ve en az 2 noktalı olmalı.")
    if not np.all(np.isfinite(contour)):
        raise ValueError("contour sonlu olmayan değer içeriyor.")
    if np.any(contour[:, 1] <= 0.0):
        raise ValueError(
            "Kontur r <= 0 içeriyor. Eksenel simetrik cidar çözücüsü ekseni "
            "(r=0) kapsamaz; iç yarıçap kesin pozitif olmalı.")

    n_pts = contour.shape[0]
    t_arr = np.asarray(thickness, dtype=float)
    if t_arr.ndim == 0:
        t_arr = np.full(n_pts, float(t_arr))
    if t_arr.shape != (n_pts,):
        raise ValueError(
            "thickness skaler ya da kontur nokta sayısıyla aynı uzunlukta "
            "dizi olmalı.")
    if not np.all(np.isfinite(t_arr)) or np.any(t_arr <= 0.0):
        raise ValueError("Cidar kalınlığı sonlu ve kesin pozitif olmalı.")

    if not isinstance(n_axial, (int, np.integer)) or n_axial < 1:
        raise ValueError("n_axial >= 1 tam sayı olmalı.")
    if not isinstance(n_radial, (int, np.integer)) or n_radial < 1:
        raise ValueError("n_radial >= 1 tam sayı olmalı.")
    if offset_mode not in _OFFSET_MODES:
        raise ValueError(f"offset_mode {_OFFSET_MODES} içinden olmalı.")

    n_radial_requested = int(n_radial)
    n_radial = max(n_radial_requested, MIN_ELEMS_THROUGH_WALL)

    s_new, z_i, r_i, t_i = _resample_contour(contour, t_arr, int(n_axial))

    if not np.all(np.diff(z_i) > 0.0):
        raise ValueError(
            "Kontur z boyunca kesin artan değil. Bu üretici cidarı kontur "
            "boyunca süpürür; geri dönen/dikey kontur desteklenmez.")

    if offset_mode == "normal":
        dz_ds = np.gradient(z_i, s_new)
        dr_ds = np.gradient(r_i, s_new)
        mag = np.hypot(dz_ds, dr_ds)
        # Teğet birim vektörü (t_z, t_r); dışa normal = teğetin +90° dönüğü.
        normal = np.stack([-dr_ds / mag, dz_ds / mag], axis=1)
    else:  # "radial"
        normal = np.tile(np.array([0.0, 1.0]), (n_axial + 1, 1))

    # Düğümler: node(i, j) = iç_i + (j / n_radial) * t_i * n_i
    frac = np.arange(n_radial + 1) / n_radial            # (n_radial+1,)
    inner_pts = np.stack([z_i, r_i], axis=1)             # (n_axial+1, 2)
    offset = t_i[:, None] * normal                        # (n_axial+1, 2)
    # (n_axial+1, n_radial+1, 2)
    grid_pts = inner_pts[:, None, :] + frac[None, :, None] * offset[:, None, :]
    nodes = grid_pts.reshape(-1, 2)

    if np.any(nodes[:, 1] <= 0.0):
        raise ValueError(
            "Öteleme sonrası r <= 0 düğüm oluştu; kontur/cidar geometrisi "
            "eksenel simetrik cidar varsayımıyla uyumsuz.")

    node_index_grid = np.arange(nodes.shape[0]).reshape(n_axial + 1,
                                                        n_radial + 1)

    n00 = node_index_grid[:-1, :-1].ravel()
    n10 = node_index_grid[1:, :-1].ravel()
    n11 = node_index_grid[1:, 1:].ravel()
    n01 = node_index_grid[:-1, 1:].ravel()
    elems = np.stack([n00, n10, n11, n01], axis=1).astype(np.int64)

    _corner_jacobian_check(nodes, elems)

    inner_edges = np.stack([node_index_grid[:-1, 0],
                            node_index_grid[1:, 0]], axis=1).astype(np.int64)
    outer_edges = np.stack([node_index_grid[:-1, -1],
                            node_index_grid[1:, -1]], axis=1).astype(np.int64)

    meta = {
        "_source": "hrma.fea.mesh_axisym.build_wall_mesh",
        "_basis": ("iç kontur yay uzunluğu örneklemesi + "
                   f"{offset_mode} öteleme, yapısal quad"),
        "offset_mode": offset_mode,
        "n_axial": int(n_axial),
        "n_radial_istenen": n_radial_requested,
        "n_radial_kullanilan": int(n_radial),
        "n_radial_alt_sinira_cekildi": n_radial_requested < n_radial,
        "birimler": {"uzunluk": "m"},
    }

    return AxisymMesh(
        nodes=nodes,
        elems=elems,
        node_index_grid=node_index_grid,
        inner_edges=inner_edges,
        outer_edges=outer_edges,
        inner_nodes=node_index_grid[:, 0].copy(),
        outer_nodes=node_index_grid[:, -1].copy(),
        z_min_nodes=node_index_grid[0, :].copy(),
        z_max_nodes=node_index_grid[-1, :].copy(),
        n_axial=int(n_axial),
        n_radial=int(n_radial),
        meta=meta,
    )
