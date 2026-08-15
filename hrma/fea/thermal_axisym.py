"""
Eksenel simetrik GEÇİCİ ısı iletimi çözücüsü (4 düğümlü bilineer quad).

Formülasyon
-----------
(z, r) düzleminde eksenel simetrik ısı iletimi:

    ρ(T) c_p(T) ∂T/∂t = ∂/∂z (k ∂T/∂z) + (1/r) ∂/∂r (k r ∂T/∂r)

Galerkin zayıf formu (hacim ölçüsü 2π r dA):

    M Ṫ + K T = F_sınır
    M_ab = ∫ ρ c_p N_a N_b · 2πr dA     → satır toplamıyla TOPAKLANIR (beyan)
    K_ab = ∫ k ∇N_a·∇N_b · 2πr dA       (2×2 Gauss)

Kütle topaklama (row-sum lumping) bilinçli tercihtir: geri Euler ile birlikte
ayrık maksimum ilkesini korur; tutarlı kütle + küçük zaman adımı, basamak
sınır koşulunda fiziksel olmayan yerel salınım üretebilir (Rank, Katz &
Werner 1983). Düzgün çözümde doğruluk O(h²) kalır; satır toplamı tutarlı
kütlenin toplam ısı sığasını AYNEN korur (enerji bütçesi bundan etkilenmez).

Zaman integrasyonu: GERİ EULER — koşulsuz kararlı, 1. mertebe. Sıcaklığa
bağlı özellikler (ρ, c_p, k) ve ışıma katsayısı bir önceki adım sıcaklığında
dondurulur (yarı-kapalı Picard lineerleştirmesi): her adım TEK doğrusal
çözümdür. Kararlı hâl limitinde bu yineleme tam doğrusal olmayan denklemin
sabit noktasına oturur (K(T*)T* = F).

Sınır koşulları
---------------
* İç yüzey (gaz tarafı): ``ConvectionBC`` — q'' = h(z)·(T_gaz(z) − T_cidar).
  h(z) Bartz katsayısıdır; katsayının KENDİSİ motor modülünde hesaplanır, bu
  çözücü hazır h(z) ve T_gaz(z) alır (köprü katmanı ayrı iştir).
  ``HeatFluxBC`` (dayatılmış akı) ve ``FixedTemperatureBC`` (doğrulama
  vakaları) da desteklenir.
* Dış yüzey: ``AmbientBC`` — doğal taşınım + LİNEERLEŞTİRİLMİŞ ışıma:
  q''_ış = εσ(T_s² + T_ort²)(T_s + T_ort)·(T_ort − T); katsayı önceki zaman
  adımının yüzey sıcaklığında değerlendirilir. Lineerleştirme hatası O(Δt)
  olup otomatik zaman adımı yakınsamasıyla sınırlanır (meta'da beyan).
* Uç kesitler (z_min, z_max): ADYABATİK (doğal sınır koşulu — beyan).
* Sınır koşulları ZAMAN İÇİNDE SABİTTİR: ateşleme süresince kararlı çalışma
  varsayımı (throttle/kapama geçişleri NOT_MODELLED).

Başlangıç koşulu: TEKDÜZE ortam sıcaklığı, t = 0 ateşleme anı
(docs/V2.7_ANALIZ_MODULU.md §4.1).

Zaman adımı seçimi: kullanıcı ayar görmez — ``solve_transient_auto`` adım
sayısını ikiye katlayarak TEPE CİDAR SICAKLIĞI GEÇMİŞİ toleransın altında
değişene kadar yineler ve sonucu beyan eder (V2.7 §3'teki mesh yakınsama
felsefesinin zaman eksenindeki karşılığı).

Enerji bütçesi: her koşuda sınırdan giren/çıkan ısı ve iç enerji değişimi
ayrık şemayla TUTARLI biçimde hesaplanıp ``ThermalResult.energy`` içinde
raporlanır. Ayrık şemada bütçe makine hassasiyetinde kapanmak zorundadır;
kapanmıyorsa montaj/işaret hatası vardır (doğrulama testi bekçidir).

Doğrulama (tests/fea/test_termal_dogrulama.py):
yarı-sonsuz katı erfc (basamak yüzey sıcaklığı) ve ierfc (sabit akı) vakaları
(data/validation/thermal_semiinf_*.json), kapalı enerji bütçesi ve uzun süre
limitinde 1B silindirik kabuk analitik profili. Doğrulanmamış FEA
yayımlanmaz (V2.7 §5).

Kaynaklar
---------
* H. S. Carslaw & J. C. Jaeger, "Conduction of Heat in Solids", 2. baskı,
  Oxford, 1959, Böl. 2 — yarı-sonsuz katı erfc/ierfc analitikleri; Böl. 7 —
  silindirik geometri (doğrulama referansları).
* Zienkiewicz & Taylor, "The Finite Element Method", 5. baskı, Cilt 1 —
  alan (potansiyel/ısı) problemleri, eksenel simetrik integrasyon.
* Lewis, Morgan, Thomas & Seetharamu, "The Finite Element Method in Heat
  Transfer Analysis", Wiley, 1996 — geçici iletim, Robin sınır matrisi,
  kütle topaklama pratiği.
* E. Rank, C. Katz & H. Werner, "On the importance of the discrete maximum
  principle in transient analysis using finite element methods",
  Int. J. Numer. Methods Eng. 19 (1983) 1771-1782 — tutarlı kütle salınımı,
  topaklama gerekçesi.
* D. R. Bartz, "A Simple Equation for Rapid Estimation of Rocket Nozzle
  Convective Heat Transfer Coefficients", Jet Propulsion 27 (1957) 49-51 —
  gaz tarafı h(z) kavramsal kaynağı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Union

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

from hrma.constants import STEFAN_BOLTZMANN

from hrma.fea.mesh_axisym import AxisymMesh

# ---------------------------------------------------------------------------
# Merkezî sayısal politika sabitleri (testler buradan import eder; parametre
# tutarlılığı kuralı gereği başka yerde tekrarlanmaz).
# ---------------------------------------------------------------------------
DEFAULT_N_STEPS0 = 16          # otomatik sürücünün başlangıç adım sayısı
DEFAULT_DT_TOL = 0.01          # tepe sıcaklık geçmişi bağıl değişim toleransı
DEFAULT_MAX_DT_HALVINGS = 8    # en fazla adım yarılama turu (16 → 4096 adım)

# Stefan-Boltzmann sabiti — v2.6.27'de merkezîleştirildi: değer artık
# hrma/constants.py'den gelir (eski not "merkezî tanımı YOK" diyordu, kapandı).
# Birimli yerel ad korunur (fea API'si bu adı dışa veriyor).
STEFAN_BOLTZMANN_W_M2K4 = STEFAN_BOLTZMANN

_GAUSS_COORD = 1.0 / np.sqrt(3.0)
# Köşe işaret sırası mesh_axisym'in CCW köşe dizilişiyle aynıdır:
# (-,-), (+,-), (+,+), (-,+).
_QUAD_SIGNS = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]])

# Malzeme özellikleri ve sınır koşulu alanları: sabit (float) ya da
# fonksiyon (özellikler T dizisi, BC alanları z dizisi alır).
PropertyLike = Union[float, Callable[[np.ndarray], np.ndarray]]


# ---------------------------------------------------------------------------
# Malzeme
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ThermalMaterial:
    """Isıl malzeme (SI): ρ [kg/m³], c_p [J/(kg·K)], k [W/(m·K)].

    Her alan sabit sayı ya da sıcaklığın fonksiyonu (T [K] dizisi → dizi)
    olabilir. Fonksiyon verilen özellikler her zaman adımında BİR ÖNCEKİ
    adımın sıcaklığında değerlendirilir (yarı-kapalı Picard — modül
    docstring'i). Fonksiyonun döndürdüğü değerler her değerlendirmede
    sonluluk + pozitiflik bekçisinden geçer; negatif/sıfır özellik üreten
    fonksiyon sessizce kullanılmaz, hata fırlatılır.
    """
    rho: PropertyLike
    cp: PropertyLike
    k: PropertyLike
    name: str = ""

    def __post_init__(self):
        for ad, deger in (("rho", self.rho), ("cp", self.cp), ("k", self.k)):
            if not callable(deger):
                v = float(deger)
                if not (np.isfinite(v) and v > 0.0):
                    raise ValueError(
                        f"ThermalMaterial.{ad} sonlu ve kesin pozitif olmalı "
                        f"(verilen: {deger!r}).")

    def is_temperature_dependent(self) -> bool:
        return any(callable(v) for v in (self.rho, self.cp, self.k))


def _eval_property(prop: PropertyLike, T: np.ndarray, ad: str) -> np.ndarray:
    """Özelliği T dizisinde değerlendirir; sonluluk + pozitiflik bekçisi."""
    if callable(prop):
        v = np.broadcast_to(np.asarray(prop(T), dtype=float), T.shape).copy()
    else:
        v = np.full(T.shape, float(prop))
    if not np.all(np.isfinite(v)) or np.any(v <= 0.0):
        raise ValueError(
            f"Malzeme özelliği '{ad}' değerlendirmede sonlu/pozitif değil "
            f"(min={np.nanmin(v):.6g}). Sıcaklığa bağlı özellik fonksiyonu "
            "çözülen sıcaklık aralığında fiziksel değer üretmiyor.")
    return v


# ---------------------------------------------------------------------------
# Sınır koşulu türleri
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConvectionBC:
    """Konveksiyon (Robin): q'' = h(z)·(T_inf(z) − T_cidar), cidara giren +.

    Gaz tarafı Bartz katsayısı bu sınıfla verilir: h [W/(m²·K)] ve
    T_inf [K], z [m] boyunca sabit ya da fonksiyon. Kenar integrallerinde
    h ve T_inf kenar ORTA NOKTASINDA değerlendirilir (O(h²) — beyan).
    """
    h: PropertyLike
    T_inf: PropertyLike


@dataclass(frozen=True)
class HeatFluxBC:
    """Dayatılmış akı (Neumann): q''(z) [W/m²], cidara GİREN pozitif."""
    q: PropertyLike


@dataclass(frozen=True)
class FixedTemperatureBC:
    """Dayatılmış yüzey sıcaklığı (Dirichlet): T(z) [K].

    Fiziksel motor vakası konveksiyondur; bu kip doğrulama analitikleri
    (basamak yüzey sıcaklığı) ve özel durumlar içindir.
    """
    T: PropertyLike


@dataclass(frozen=True)
class AdiabaticBC:
    """Yalıtılmış yüzey: q'' = 0 (doğal sınır koşulu — hiçbir terim eklenmez)."""


@dataclass(frozen=True)
class AmbientBC:
    """Dış yüzey ortam koşulu: doğal taşınım + lineerleştirilmiş ışıma.

    q'' = [h + h_ış(T_s)]·(T_ort − T),
    h_ış = ε·σ·(T_s² + T_ort²)(T_s + T_ort);  T_s önceki adım yüzey sıcaklığı
    (kenar orta noktası). ε = 0 → yalnız doğal taşınım. Lineerleştirme hatası
    meta'da beyan edilir.
    """
    h: float
    T_ambient: float
    emissivity: float = 0.0

    def __post_init__(self):
        if not (np.isfinite(self.h) and self.h >= 0.0):
            raise ValueError("AmbientBC.h sonlu ve >= 0 olmalı.")
        if not (np.isfinite(self.T_ambient) and self.T_ambient > 0.0):
            raise ValueError("AmbientBC.T_ambient [K] kesin pozitif olmalı.")
        if not (0.0 <= self.emissivity <= 1.0):
            raise ValueError("AmbientBC.emissivity [0, 1] aralığında olmalı.")


_BC_TYPES = (ConvectionBC, HeatFluxBC, FixedTemperatureBC, AdiabaticBC,
             AmbientBC)


# ---------------------------------------------------------------------------
# Sonuç
# ---------------------------------------------------------------------------

@dataclass
class ThermalResult:
    """Geçici ısı iletimi çözümü.

    times : (S+1,) [s] — t=0 ateşleme anı dahil zaman noktaları.
    T_history : (S+1, N) [K] — her zaman noktasında düğüm sıcaklık alanı
        (T(r, z, t) alanının ayrık hali; satır 0 başlangıç koşuludur).
    T_final : (N,) [K] — son andaki alan.
    peak_wall_T_history : (S+1,) [K] — her anda düğümler üzerindeki maksimum
        cidar sıcaklığı (tepe cidar sıcaklığı geçmişi).
    peak_wall_T : float [K], peak_time_s : float [s], peak_node : int —
        tüm zamanların tepe değeri, anı ve düğümü.
    energy : dict — kapalı enerji bütçesi (işaret uzlaşımı: cidara GİREN +):
        Q_inner_J / Q_outer_J (iç/dış yüzeyden cidara giren toplam ısı),
        dU_J (iç enerji değişimi), residual_J / residual_rel (kapanma),
        qdot_inner_W / qdot_outer_W ((S,) adım aralığı güçleri, geri Euler
        uzlaşımıyla aralık SONU sıcaklığında).
    meta : dict — model temeli, sınır koşulu ve NOT_MODELLED beyanları.
    """
    times: np.ndarray
    T_history: np.ndarray
    T_final: np.ndarray
    peak_wall_T_history: np.ndarray
    peak_wall_T: float
    peak_time_s: float
    peak_node: int
    energy: dict
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Eleman montajı (skaler alan)
# ---------------------------------------------------------------------------

def _shape_functions(xi: float, eta: float):
    """Bilineer şekil fonksiyonları ve doğal türevleri (köşe sırası CCW)."""
    signs = _QUAD_SIGNS
    N = 0.25 * (1.0 + xi * signs[:, 0]) * (1.0 + eta * signs[:, 1])
    dN = np.empty((4, 2))
    dN[:, 0] = 0.25 * signs[:, 0] * (1.0 + eta * signs[:, 1])   # d/dξ
    dN[:, 1] = 0.25 * signs[:, 1] * (1.0 + xi * signs[:, 0])    # d/dη
    return N, dN


def _assemble_domain(mesh: AxisymMesh, material: ThermalMaterial,
                     T_nodal: np.ndarray):
    """İletim matrisi K (csr) + topaklanmış kütle köşegeni M_diag (N,).

    Özellikler Gauss noktası sıcaklığında (T_nodal alanından enterpole)
    değerlendirilir; T_nodal bir önceki zaman adımının alanıdır (yarı-kapalı
    lineerleştirme — modül docstring'i).
    """
    X = mesh.nodes[mesh.elems]                     # (M, 4, 2)
    Te = T_nodal[mesh.elems]                       # (M, 4)
    n_el = mesh.n_elems
    Ke = np.zeros((n_el, 4, 4))
    Me_diag = np.zeros((n_el, 4))

    for sx, sy in _QUAD_SIGNS:
        xi, eta = _GAUSS_COORD * sx, _GAUSS_COORD * sy
        N, dN = _shape_functions(xi, eta)
        # J[k, i] = Σ_a dN_a/dξ_k · X_a,i  (k: ξ/η, i: z/r)
        J = np.einsum('ak,eai->eki', dN, X)
        detJ = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
        if np.any(detJ <= 0.0):
            raise ValueError(
                "İntegrasyon noktasında det J <= 0: mesh ters dönmüş/"
                "dejenere eleman içeriyor.")
        invJ = np.empty_like(J)
        invJ[:, 0, 0] = J[:, 1, 1]
        invJ[:, 0, 1] = -J[:, 0, 1]
        invJ[:, 1, 0] = -J[:, 1, 0]
        invJ[:, 1, 1] = J[:, 0, 0]
        invJ /= detJ[:, None, None]
        dNdx = np.einsum('eik,ak->eia', invJ, dN)  # (M, 2, 4) ∂N_a/∂x_i
        r_gp = X[:, :, 1] @ N                      # (M,)
        if np.any(r_gp <= 0.0):
            raise ValueError(
                "İntegrasyon noktasında r <= 0: eksenel simetrik hacim "
                "ölçüsü 2πr eksende sıfırlanır; bu çözücü cidar (r > 0) "
                "bölgesi içindir.")
        w = 2.0 * np.pi * detJ * r_gp              # Gauss ağırlığı 1
        T_gp = Te @ N
        k_gp = _eval_property(material.k, T_gp, "k")
        rc_gp = (_eval_property(material.rho, T_gp, "rho")
                 * _eval_property(material.cp, T_gp, "cp"))
        Ke += (w * k_gp)[:, None, None] * np.einsum('eia,eib->eab',
                                                    dNdx, dNdx)
        # Topaklanmış kütle: tutarlı satır toplamı Σ_b ∫ρc N_a N_b = ∫ρc N_a
        # (Σ_b N_b = 1); doğrudan bu integral biriktirilir.
        Me_diag += (w * rc_gp)[:, None] * N[None, :]

    rows = np.repeat(mesh.elems, 4, axis=1).ravel()
    cols = np.tile(mesh.elems, (1, 4)).ravel()
    K = sp.coo_matrix((Ke.ravel(), (rows, cols)),
                      shape=(mesh.n_nodes, mesh.n_nodes)).tocsr()
    M_diag = np.zeros(mesh.n_nodes)
    np.add.at(M_diag, mesh.elems.ravel(), Me_diag.ravel())
    return K, M_diag


# ---------------------------------------------------------------------------
# Yüzey (kenar) integralleri
# ---------------------------------------------------------------------------

def _edge_geometry(nodes: np.ndarray, edges: np.ndarray):
    """Kenar geometrisi: uzunluk L, uç yarıçapları r1/r2, orta nokta z'si."""
    P1 = nodes[edges[:, 0]]
    P2 = nodes[edges[:, 1]]
    d = P2 - P1
    L = np.hypot(d[:, 0], d[:, 1])
    return L, P1[:, 1], P2[:, 1], 0.5 * (P1[:, 0] + P2[:, 0])


def _eval_on_edges(val: PropertyLike, z_mid: np.ndarray, ad: str,
                   pozitif: bool = False, negatif_olabilir: bool = True):
    """z'ye bağlı BC alanını kenar orta noktalarında değerlendirir."""
    if callable(val):
        v = np.broadcast_to(np.asarray(val(z_mid), dtype=float),
                            z_mid.shape).copy()
    else:
        v = np.full(z_mid.shape, float(val))
    if not np.all(np.isfinite(v)):
        raise ValueError(f"Sınır koşulu alanı '{ad}' sonlu değil.")
    if pozitif and np.any(v <= 0.0):
        raise ValueError(f"Sınır koşulu alanı '{ad}' kesin pozitif olmalı.")
    if not negatif_olabilir and np.any(v < 0.0):
        raise ValueError(f"Sınır koşulu alanı '{ad}' negatif olamaz.")
    return v


def _robin_surface(n_nodes: int, edges: np.ndarray, L, r1, r2,
                   h_edge: np.ndarray, T_inf_edge: np.ndarray):
    """Robin kenar matrisi H (csr) ve yükü F: ∫ h N_a N_b 2πr ds, ∫ h T_inf N_a 2πr ds.

    Lineer kenarda r(s) lineer olduğundan integraller kapalı formda TAMDIR:
    ∫N₁²  r ds = L(3r₁+r₂)/12,  ∫N₁N₂ r ds = L(r₁+r₂)/12,
    ∫N₂²  r ds = L(r₁+3r₂)/12,  ∫N₁ r ds = L(2r₁+r₂)/6, ∫N₂ r ds = L(r₁+2r₂)/6.
    """
    c = 2.0 * np.pi * h_edge
    h11 = c * L * (3.0 * r1 + r2) / 12.0
    h12 = c * L * (r1 + r2) / 12.0
    h22 = c * L * (r1 + 3.0 * r2) / 12.0
    rows = np.concatenate([edges[:, 0], edges[:, 0], edges[:, 1], edges[:, 1]])
    cols = np.concatenate([edges[:, 0], edges[:, 1], edges[:, 0], edges[:, 1]])
    vals = np.concatenate([h11, h12, h12, h22])
    H = sp.coo_matrix((vals, (rows, cols)), shape=(n_nodes, n_nodes)).tocsr()

    F = np.zeros(n_nodes)
    f1 = c * T_inf_edge * L * (2.0 * r1 + r2) / 6.0
    f2 = c * T_inf_edge * L * (r1 + 2.0 * r2) / 6.0
    np.add.at(F, edges[:, 0], f1)
    np.add.at(F, edges[:, 1], f2)
    return H, F


def _flux_load(n_nodes: int, edges: np.ndarray, L, r1, r2,
               q_edge: np.ndarray) -> np.ndarray:
    """Dayatılmış akının tutarlı düğüm yükü: F_a = ∫ q N_a 2πr ds (kapalı form)."""
    c = 2.0 * np.pi * q_edge
    F = np.zeros(n_nodes)
    np.add.at(F, edges[:, 0], c * L * (2.0 * r1 + r2) / 6.0)
    np.add.at(F, edges[:, 1], c * L * (r1 + 2.0 * r2) / 6.0)
    return F


# ---------------------------------------------------------------------------
# Yüzey hazırlığı (BC → ayrık veri)
# ---------------------------------------------------------------------------

def _prepare_side(bc, mesh: AxisymMesh, edges: np.ndarray,
                  surface_nodes: np.ndarray, side_name: str) -> dict:
    """Bir yüzeyin BC'sini montaja hazır ayrık veriye çevirir."""
    if not isinstance(bc, _BC_TYPES):
        raise TypeError(
            f"{side_name} sınır koşulu {[t.__name__ for t in _BC_TYPES]} "
            f"türlerinden biri olmalı; verilen: {type(bc).__name__}.")
    L, r1, r2, z_mid = _edge_geometry(mesh.nodes, edges)
    side = {"bc": bc, "edges": edges, "L": L, "r1": r1, "r2": r2,
            "nodes": surface_nodes, "name": side_name}
    if isinstance(bc, ConvectionBC):
        side["type"] = "robin"
        side["h"] = _eval_on_edges(bc.h, z_mid, f"{side_name}.h",
                                   negatif_olabilir=False)
        side["T_inf"] = _eval_on_edges(bc.T_inf, z_mid, f"{side_name}.T_inf",
                                       pozitif=True)
    elif isinstance(bc, AmbientBC):
        # Doğal taşınım kısmı sabit; ışıma katsayısı adım içinde güncellenir.
        side["type"] = "ambient"
        side["h_nat"] = np.full(edges.shape[0], bc.h)
        side["T_inf"] = np.full(edges.shape[0], bc.T_ambient)
    elif isinstance(bc, HeatFluxBC):
        side["type"] = "flux"
        side["q"] = _eval_on_edges(bc.q, z_mid, f"{side_name}.q")
    elif isinstance(bc, FixedTemperatureBC):
        side["type"] = "dirichlet"
        z_node = mesh.nodes[surface_nodes, 0]
        if callable(bc.T):
            Tv = np.broadcast_to(np.asarray(bc.T(z_node), dtype=float),
                                 z_node.shape).copy()
        else:
            Tv = np.full(z_node.shape, float(bc.T))
        if not np.all(np.isfinite(Tv)) or np.any(Tv <= 0.0):
            raise ValueError(
                f"{side_name} dayatılmış sıcaklık [K] sonlu ve pozitif olmalı.")
        side["T_fixed"] = Tv
    else:  # AdiabaticBC
        side["type"] = "adiabatic"
    return side


def _side_surface_terms(side: dict, n_nodes: int,
                        T_prev: np.ndarray):
    """Yüzeyin H, F katkısı. Işıma katsayısı T_prev yüzeyinde donar."""
    tip = side["type"]
    if tip == "robin":
        return _robin_surface(n_nodes, side["edges"], side["L"],
                              side["r1"], side["r2"],
                              side["h"], side["T_inf"])
    if tip == "ambient":
        bc: AmbientBC = side["bc"]
        h_eff = side["h_nat"].copy()
        if bc.emissivity > 0.0:
            # Önceki adım kenar orta nokta yüzey sıcaklığı (lineerleştirme).
            T_s = 0.5 * (T_prev[side["edges"][:, 0]]
                         + T_prev[side["edges"][:, 1]])
            T_a = bc.T_ambient
            h_eff = h_eff + (bc.emissivity * STEFAN_BOLTZMANN_W_M2K4
                             * (T_s ** 2 + T_a ** 2) * (T_s + T_a))
        return _robin_surface(n_nodes, side["edges"], side["L"],
                              side["r1"], side["r2"],
                              h_eff, side["T_inf"])
    if tip == "flux":
        F = _flux_load(n_nodes, side["edges"], side["L"],
                       side["r1"], side["r2"], side["q"])
        return None, F
    # dirichlet / adiabatic: yüzey integrali yok
    return None, None


def _side_is_static(side: dict) -> bool:
    """Yüzey matrisi zaman içinde sabit mi? (Işıma sıcaklığa bağlıdır.)"""
    if side["type"] == "ambient":
        return side["bc"].emissivity == 0.0
    return True


# ---------------------------------------------------------------------------
# Meta beyanı
# ---------------------------------------------------------------------------

def _bc_beyan(side: dict) -> str:
    tip = side["type"]
    if tip == "robin":
        return ("konveksiyon (Robin): q'' = h(z)·(T_inf(z) − T); h/T_inf "
                "kenar orta noktasında, zamanla sabit")
    if tip == "ambient":
        bc: AmbientBC = side["bc"]
        s = f"doğal taşınım h = {bc.h:g} W/(m²K), T_ort = {bc.T_ambient:g} K"
        if bc.emissivity > 0.0:
            s += (f"; ışıma ε = {bc.emissivity:g} LİNEERLEŞTİRİLMİŞ: "
                  "h_ış = εσ(T_s²+T_ort²)(T_s+T_ort), T_s önceki zaman "
                  "adımının yüzey sıcaklığı (hata O(Δt))")
        else:
            s += "; ışıma YOK (ε = 0)"
        return s
    if tip == "flux":
        return "dayatılmış akı (Neumann): q''(z), cidara giren pozitif"
    if tip == "dirichlet":
        return "dayatılmış yüzey sıcaklığı (Dirichlet)"
    return "adyabatik (q'' = 0)"


def _result_meta(mesh: AxisymMesh, material: ThermalMaterial,
                 inner_side: dict, outer_side: dict,
                 T_initial: float) -> dict:
    """Sonucun _basis/_source ve NOT_MODELLED beyanı (sahte veri yasağı)."""
    has_radiation = (inner_side["type"] == "ambient"
                     and inner_side["bc"].emissivity > 0.0) or (
                     outer_side["type"] == "ambient"
                     and outer_side["bc"].emissivity > 0.0)
    meta = {
        "_source": "hrma.fea.thermal_axisym.solve_transient",
        "_basis": ("2B eksenel simetrik geçici ısı iletimi FEM; 4 düğümlü "
                   "bilineer quad, 2×2 Gauss iletim matrisi, satır toplamıyla "
                   "topaklanmış kütle, geri Euler (koşulsuz kararlı) zaman "
                   "adımı; scipy.sparse doğrudan çözüm"),
        "birimler": {"uzunluk": "m", "zaman": "s", "sicaklik": "K",
                     "isi_akisi": "W/m²", "guc": "W", "enerji": "J"},
        "baslangic_kosulu": (f"tekdüze T = {T_initial:g} K (ortam); "
                             "t = 0 ateşleme anı"),
        "sinir_kosullari": {
            "ic_yuzey": _bc_beyan(inner_side),
            "dis_yuzey": _bc_beyan(outer_side),
            "uc_kesitler": "adyabatik (doğal sınır koşulu — beyan)",
            "zamanla_degisim": ("YOK — h, T_gaz, T_ort ateşleme boyunca "
                                "sabit alınır (kararlı çalışma varsayımı)"),
        },
        "zaman_semasi": ("geri Euler; sıcaklığa bağlı özellikler ve ışıma "
                         "katsayısı bir önceki adım sıcaklığında donduruldu "
                         "(yarı-kapalı Picard lineerleştirmesi)"),
        "kutle_matrisi": ("satır toplamıyla topaklanmış (lumped) — geri "
                          "Euler ile ayrık maksimum ilkesi korunur; toplam "
                          "ısı sığası tutarlı kütleyle aynıdır"),
        "eksenel_iletim": ("MODELLENIYOR — 2B (z, r) formülasyonu eksenel "
                           "iletimi içerir; ihmal YOK"),
        "sicakliga_bagli_ozellikler": (
            "fonksiyon verilen ρ/c_p/k Gauss noktası sıcaklığında, önceki "
            "adım alanından değerlendirilir"
            if material.is_temperature_dependent()
            else "sabit (fonksiyon verilmedi)"),
        "not_modelled": [
            "ablasyon / yüzey gerilemesi",
            "faz değişimi (erime, süblimleşme, ayrışma) — alan erime "
            "sıcaklığını aşarsa çözücü bunu bilmez; malzeme sınırı "
            "denetimi çağıran katmanın işidir",
            "gaz tarafı ışıma (iç yüzeyde yalnız konveksiyon; Bartz h)",
            "soğutma kanalları / rejeneratif-film soğutma",
            "sınır koşullarının zamanla değişimi (throttle, kapama geçişi)",
            "katmanlar arası kontak direnci (tek parça cidar varsayımı)",
        ],
    }
    if has_radiation:
        meta["isima_lineerlestirme_hatasi"] = (
            "h_ış önceki adım yüzey sıcaklığında dondurulur; adım başına "
            "hata O(Δt·|dT_s/dt|·∂h_ış/∂T) olup otomatik zaman adımı "
            "yakınsaması (solve_transient_auto) tarafından sınırlanır")
    return meta


# ---------------------------------------------------------------------------
# Çekirdek: verilen zaman ızgarasında geri Euler
# ---------------------------------------------------------------------------

def solve_transient(mesh: AxisymMesh,
                    material: ThermalMaterial,
                    times,
                    inner_bc,
                    outer_bc,
                    T_initial: float) -> ThermalResult:
    """Verilen zaman ızgarasında geçici ısı iletimi çözümü (sayısal çekirdek).

    Parametreler
    ------------
    times : (S+1,) artan zaman noktaları [s]; times[0] = 0 (ateşleme anı)
        zorunludur — başlangıç koşulu bu anda tekdüze T_initial'dır.
    inner_bc / outer_bc : ConvectionBC | HeatFluxBC | FixedTemperatureBC |
        AdiabaticBC | AmbientBC.
    T_initial : tekdüze başlangıç (ortam) sıcaklığı [K].

    Kullanıcıya dönük giriş noktası ``solve_transient_auto``'dur (zaman
    adımını kendi seçer ve beyan eder); bu fonksiyon doğrulama testlerinin
    ve sürücünün çekirdeğidir.
    """
    times = np.asarray(times, dtype=float)
    if times.ndim != 1 or times.size < 2:
        raise ValueError("times en az 2 noktalı 1B dizi olmalı.")
    if not np.all(np.isfinite(times)):
        raise ValueError("times sonlu olmayan değer içeriyor.")
    if times[0] != 0.0:
        raise ValueError(
            "times[0] = 0 olmalı: t = 0 ateşleme anıdır ve başlangıç "
            "koşulu (tekdüze ortam sıcaklığı) bu anda tanımlıdır.")
    if not np.all(np.diff(times) > 0.0):
        raise ValueError("times kesin artan olmalı.")
    if not (np.isfinite(T_initial) and T_initial > 0.0):
        raise ValueError("T_initial [K] sonlu ve kesin pozitif olmalı.")

    n_nodes = mesh.n_nodes
    inner_side = _prepare_side(inner_bc, mesh, mesh.inner_edges,
                               mesh.inner_nodes, "ic_yuzey")
    outer_side = _prepare_side(outer_bc, mesh, mesh.outer_edges,
                               mesh.outer_nodes, "dis_yuzey")

    # Dirichlet kümesi (iç/dış yüzey düğümleri ayrıktır: j=0 ve j=n_radial).
    fixed_mask = np.zeros(n_nodes, dtype=bool)
    fixed_values = np.zeros(n_nodes)
    for side in (inner_side, outer_side):
        if side["type"] == "dirichlet":
            fixed_mask[side["nodes"]] = True
            fixed_values[side["nodes"]] = side["T_fixed"]
    free_mask = ~fixed_mask
    free_idx = np.flatnonzero(free_mask)
    fixed_idx = np.flatnonzero(fixed_mask)

    static_domain = not material.is_temperature_dependent()
    static_surface = _side_is_static(inner_side) and _side_is_static(
        outer_side)

    S = times.size - 1
    T = np.full(n_nodes, float(T_initial))
    T_history = np.empty((S + 1, n_nodes))
    T_history[0] = T
    qdot_inner = np.zeros(S)
    qdot_outer = np.zeros(S)
    dU_total = 0.0
    Q_inner = 0.0
    Q_outer = 0.0

    # Önbellek: sistem tamamen statikse (sabit özellik + ışıma yok) ve dt
    # değişmiyorsa A yalnız bir kez kurulur ve BİR KEZ çarpanlara ayrılır.
    cache = {"dt": None, "A": None, "lu": None, "A_fc": None,
             "K": None, "M_diag": None, "H": {}, "F": {}}

    for n in range(S):
        dt = times[n + 1] - times[n]

        if cache["K"] is None or not static_domain:
            cache["K"], cache["M_diag"] = _assemble_domain(mesh, material, T)
        for side in (inner_side, outer_side):
            key = side["name"]
            if key not in cache["H"] or not _side_is_static(side):
                H_s, F_s = _side_surface_terms(side, n_nodes, T)
                cache["H"][key] = H_s
                cache["F"][key] = F_s

        system_static = static_domain and static_surface
        if (cache["lu"] is None or not system_static
                or dt != cache["dt"]):
            A = sp.diags(cache["M_diag"] / dt) + cache["K"]
            for H_s in cache["H"].values():
                if H_s is not None:
                    A = A + H_s
            A = A.tocsr()
            cache["A"] = A
            cache["dt"] = dt
            if fixed_idx.size:
                cache["A_fc"] = A[free_idx][:, fixed_idx]
            cache["lu"] = splu(A[free_idx][:, free_idx].tocsc())

        b = cache["M_diag"] * T / dt
        for F_s in cache["F"].values():
            if F_s is not None:
                b = b + F_s

        rhs = b[free_idx]
        if fixed_idx.size:
            rhs = rhs - cache["A_fc"] @ fixed_values[fixed_idx]
        T_new = np.empty(n_nodes)
        T_new[free_idx] = cache["lu"].solve(rhs)
        T_new[fixed_idx] = fixed_values[fixed_idx]
        if not np.all(np.isfinite(T_new)):
            raise RuntimeError(
                "Zaman adımı çözümü sonlu değil (tekil/kötü koşullu sistem); "
                "mesh ve sınır koşulları gözden geçirilmeli.")

        # ---- Enerji muhasebesi (ayrık şemayla tutarlı; cidara giren +) ----
        reaction = None
        for side, qdot_arr in ((inner_side, qdot_inner),
                               (outer_side, qdot_outer)):
            tip = side["type"]
            if tip in ("robin", "ambient"):
                H_s = cache["H"][side["name"]]
                F_s = cache["F"][side["name"]]
                qdot = float(F_s.sum() - (H_s @ T_new).sum())
            elif tip == "flux":
                qdot = float(cache["F"][side["name"]].sum())
            elif tip == "dirichlet":
                if reaction is None:
                    reaction = cache["A"] @ T_new - b
                qdot = float(reaction[side["nodes"]].sum())
            else:  # adiabatic
                qdot = 0.0
            qdot_arr[n] = qdot

        dU_step = float((cache["M_diag"] * (T_new - T)).sum())
        dU_total += dU_step
        Q_inner += qdot_inner[n] * dt
        Q_outer += qdot_outer[n] * dt

        T = T_new
        T_history[n + 1] = T

    residual = Q_inner + Q_outer - dU_total
    scale = max(abs(Q_inner), abs(Q_outer), abs(dU_total), 1e-300)
    energy = {
        "_basis": ("ayrık geri Euler bütçesi; sınır güçleri adım SONU "
                   "sıcaklığında (Robin/akı yüzey integrali, Dirichlet'te "
                   "reaksiyon); işaret uzlaşımı: cidara giren +"),
        "Q_inner_J": Q_inner,
        "Q_outer_J": Q_outer,
        "dU_J": dU_total,
        "residual_J": residual,
        "residual_rel": abs(residual) / scale,
        "qdot_inner_W": qdot_inner,
        "qdot_outer_W": qdot_outer,
    }

    peak_hist = T_history.max(axis=1)
    i_peak = int(np.argmax(peak_hist))
    peak_node = int(np.argmax(T_history[i_peak]))

    meta = _result_meta(mesh, material, inner_side, outer_side, T_initial)
    meta["zaman_izgarasi"] = {"n_steps": S, "t_end_s": float(times[-1])}

    return ThermalResult(
        times=times,
        T_history=T_history,
        T_final=T_history[-1].copy(),
        peak_wall_T_history=peak_hist,
        peak_wall_T=float(peak_hist[i_peak]),
        peak_time_s=float(times[i_peak]),
        peak_node=peak_node,
        energy=energy,
        meta=meta,
    )


# ---------------------------------------------------------------------------
# Kullanıcıya dönük sürücü: otomatik zaman adımı + beyan
# ---------------------------------------------------------------------------

def solve_transient_auto(mesh: AxisymMesh,
                         material: ThermalMaterial,
                         t_end: float,
                         inner_bc,
                         outer_bc,
                         T_initial: float,
                         tol: float = DEFAULT_DT_TOL,
                         n_steps0: int = DEFAULT_N_STEPS0,
                         max_halvings: int = DEFAULT_MAX_DT_HALVINGS
                         ) -> ThermalResult:
    """Zaman adımını KENDİ seçen giriş noktası (kullanıcı ayar görmez).

    Adım sayısı ``n_steps0``'dan başlar ve her turda ikiye katlanır (adım
    yarılanır); ardışık iki koşunun TEPE CİDAR SICAKLIĞI GEÇMİŞİ ortak zaman
    noktalarında karşılaştırılır. Bağıl fark (ölçek: alanın başlangıçtan en
    büyük sapması) ``tol`` altına inince durulur. Sonuç, hangi adımın
    kullanıldığını, son farkı ve yakınsayıp yakınsamadığını
    ``meta['zaman_adimi']`` içinde AÇIKÇA beyan eder — yakınsamamış koşu
    yakınsamış gibi sunulmaz (V2.7 §3 felsefesi, zaman ekseni).
    """
    if not (np.isfinite(t_end) and t_end > 0.0):
        raise ValueError("t_end > 0 olmalı.")
    if not (0.0 < tol < 1.0):
        raise ValueError("tol (0, 1) aralığında bağıl değişim olmalı.")
    if not isinstance(n_steps0, (int, np.integer)) or n_steps0 < 1:
        raise ValueError("n_steps0 >= 1 tam sayı olmalı.")
    if max_halvings < 0:
        raise ValueError("max_halvings >= 0 olmalı.")

    n = int(n_steps0)
    result_prev = solve_transient(mesh, material,
                                  np.linspace(0.0, t_end, n + 1),
                                  inner_bc, outer_bc, T_initial)
    history = [{"n_steps": n, "dt_s": t_end / n,
                "peak_wall_T": result_prev.peak_wall_T, "rel_change": None}]
    converged = False
    rel = None
    for _ in range(int(max_halvings)):
        n *= 2
        result = solve_transient(mesh, material,
                                 np.linspace(0.0, t_end, n + 1),
                                 inner_bc, outer_bc, T_initial)
        # Kaba koşunun zaman noktaları ince koşunun her 2. noktasıdır
        # (aynı t_end, adım tam ikiye katlandı) — enterpolasyonsuz kıyas.
        # Ölçek: alanın başlangıçtan en büyük sapması. Sapma sıcaklık
        # büyüklüğüne göre yuvarlama gürültüsü mertebesindeyse (alan fiilen
        # değişmiyorsa) gürültünün gürültüye bölünmesini önlemek için dürüst
        # bir taban kullanılır: 1e-9·|T_initial| altı sapma sayısal olarak
        # anlamsızdır.
        dev = float(np.max(np.abs(result.T_history - T_initial)))
        scale = max(dev, 1e-9 * abs(T_initial))
        rel = float(np.max(np.abs(result.peak_wall_T_history[::2]
                                  - result_prev.peak_wall_T_history))
                    / scale)
        history.append({"n_steps": n, "dt_s": t_end / n,
                        "peak_wall_T": result.peak_wall_T,
                        "rel_change": rel})
        result_prev = result
        if rel < tol:
            converged = True
            break

    result = result_prev
    dt_final = t_end / n
    if converged:
        beyan = (f"Zaman adımı yakınsadı: {n} adım (Δt = {dt_final:.6g} s); "
                 f"son iki koşu arasında tepe cidar sıcaklığı geçmişi farkı "
                 f"%{100.0 * rel:.3f} (tolerans %{100.0 * tol:.2f}).")
    elif rel is None:
        beyan = (f"ZAMAN ADIMI YAKINSAMASI DENETLENEMEDİ: tek koşu yapıldı "
                 f"({n} adım, max_halvings = 0); karşılaştırılacak ikinci "
                 "koşu yok.")
    else:
        beyan = (f"ZAMAN ADIMI YAKINSAMADI: {len(history)} koşuda son fark "
                 f"%{100.0 * rel:.3f}, tolerans %{100.0 * tol:.2f} altına "
                 f"inmedi ({n} adım, Δt = {dt_final:.6g} s). Sonuç bu "
                 "beyanla birlikte değerlendirilmelidir.")

    result.meta["zaman_adimi"] = {
        "_source": "hrma.fea.thermal_axisym.solve_transient_auto",
        "yontem": ("adım ikiye bölme; ölçüt: tepe cidar sıcaklığı geçmişinin "
                   "ortak zaman noktalarındaki bağıl değişimi"),
        "n_steps0": int(n_steps0),
        "n_steps": n,
        "dt_s": dt_final,
        "halvings": len(history) - 1,
        "rel_change": rel,
        "tol": tol,
        "converged": converged,
        "history": history,
        "beyan": beyan,
    }
    return result
