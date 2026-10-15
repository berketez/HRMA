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
#: En fazla adım yarılama turu. ÖH D37 A2-1 termal / OH-DK-10: 8 (16 → 4096
#: adım) tavanı dik yüzey geçişlerinde DOLUYORDU (DK T3 Bi = 10: 8/8 yarılama,
#: %0,944 ile yakınsadı; örnek motor 300 s koşusu 4096 adımda %0,80) — bir
#: yarılama daha gerekseydi sürücü dürüstçe "YAKINSAMADI" derdi ama çözüm
#: bütçeden değil TAVANDAN durmuş olurdu. ÖLÇÜLDÜ (25 Eyl 2026, yüklü
#: makine, örnek hibrit 16×4 = 85 düğüm, docs/scofield/raw/OH/A2/termal/a1/
#: once/zaman_tavani_hibrit.json): 4096 adım 0,18 s · 8192 adım 0,32 s ·
#: 16384 adım 0,61 s; geçmiş 1,39e6 değer (< 2e6 bütçe). Tavan 10'a (16 →
#: 16384 adım) çıkarıldı; asıl sınır uç katmanının geçmiş bütçesidir
#: (app.py FEA_THERMAL_MAX_HISTORY_VALUES) ve o katman kısıtlarsa bunu
#: ``limits.clamped`` ile beyan eder — fail-closed korunur.
DEFAULT_MAX_DT_HALVINGS = 10   # en fazla adım yarılama turu (16 → 16384 adım)

#: UZAMSAL yakınsama toleransı — tepe cidar sıcaklığının mesh inceltmesiyle
#: bağıl değişimi (P8B1-10). Zaman ekseninin toleransıyla (DEFAULT_DT_TOL,
#: %1) AYNI büyüklük seçildi: iki eksen aynı hükmü besliyor, biri gevşek
#: bırakılırsa kazanılan yakınsama diğer eksende kaybolur.
#: ÖLÇÜLDÜ (taban 7751531, ``once_a3.json``; 300 mm × 3 mm SS304 cidar,
#: h = 5000 W/(m²K), T_gaz = 3000 K, t = 3 s):
#:     16×4 → 2191,8468 K · 32×8 → 2190,7475 K (%0,0502)
#:                        · 64×16 → 2190,4739 K (%0,0125)
#: Yani bu vaka sınıfında ürünün 16×4 mesh'i uzamsal olarak YAKINSAMIŞTIR —
#: ama bu, ölçülmeden BİLİNEMEZDİ ve ölçülmüyordu (P8B1-10).
DEFAULT_SPATIAL_TOL = 0.01

#: ÖH D37 A2-1 termal / F-02 + OH-DK-08 — UZAMSAL MERDİVEN üç seviyelidir.
#: ÖLÇÜLDÜ (DK kampanyası T7, docs/scofield/raw/OH/D37/dogrulama/termal/
#: rapor.md §c-B1; gerçek hibrit motor, cidar 23,08 mm, 512 adım sabit):
#: tepe cidar T 16×4 2582,9 → 32×8 2598,3 → 64×16 2609,6 → 128×32 2613,1 K.
#: Tek 2× inceltme (16×4 → 32×8) "%0,68 < %1, SAĞLANDI" diyordu; oysa kaba
#: üçlüde gözlenen mertebe p = 0,45 (boğazdaki dik gradyan 4 elemanla
#: çözülmüyor), ince üçlüde 1,69; Richardson dışdeğeri 2614,7 K → 16×4'ün
#: kalan hatası TAHMİNEN %1,39 (31,9 K), yönü EMNİYETSİZ (tepe düşük).
#: |ince − kaba| yalnız p ≈ 2 iken kalan hatanın 1/3'üdür; p < 1'de kalan
#: hata farkın KENDİSİNDEN büyüktür. Bu yüzden iki seviye hüküm veremez:
#: üç seviye (r = 2) ile Celik 2008 GCI (hrma/utils/gci.py TEK tanım)
#: kurulur, hüküm kilitli kuralla verilir (olcut_kulvar.json K1).
DEFAULT_SPATIAL_LEVELS = 3

#: Hüküm için gözlenen mertebenin alt sınırı. Q4 + düzgün çözümde formel
#: mertebe 2'dir (docstring; DK T1-T5 ölçümü p = 1,99-2,02). Gözlenen
#: mertebe formel mertebenin YARISININ altındaysa çözüm asimptotik aralıkta
#: değildir ve Richardson dışdeğeri güvenilmez (ASME V&V 20-2009 §2-4;
#: Oberkampf & Roy 2010 Böl. 8). ÖLÇÜLDÜ (DK T7): kaba üçlü p = 0,45 ile
#: T_ext ≈ 2641 K, ince üçlü p = 1,69 ile 2614,7 K — 26 K fark. Eşik sonuç
#: görülmeden kilitlendi (olcut_kulvar.json K1.P_MIN_ASYMPTOTIC).
SPATIAL_P_MIN_ASYMPTOTIC = 1.0

#: Hangi seviyenin SONUCU yayımlanır: 'finest' — çözülen en ince seviye
#: (GCI_fine21 o çözüme aittir; kalan hatası en küçük olan sayı yayımlanır)
#: ya da 'coarse' — istenen (kaba) ağ. Berke'nin Sunum 2 kararı tek satırla
#: değiştirir; her iki hâlde de merdivenin bütün seviyeleri beyan edilir.
SPATIAL_PUBLISH_LEVEL = "finest"

#: Alan geçmişi (T_history, (S+1)·N değer) bellek bütçesi — merdivenin ince
#: seviyeleri geçmişi TUTMAZ (yalnız son alan + tepe geçmişi + enerji);
#: yayımlanan seviye ancak bu bütçeye sığıyorsa geçmişini tutar ve tutmadıysa
#: bunu beyan eder. Uç katmanı (app.py FEA_THERMAL_MAX_HISTORY_VALUES) aynı
#: sayıyı taşır; değişecekse ikisi birlikte (parametre tutarlılığı).
DEFAULT_HISTORY_BUDGET_VALUES = 2_000_000

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

#: Çağıran ``ConvectionBC.h_basis`` vermediğinde künyeye yazılan cümle.
#: P8B1-11: burada BİR MODEL ADI (ör. "Bartz") YAZILMAZ — çözücü çağıranın
#: hangi korelasyonu kullandığını bilmez ve tahmin etmez.
H_KAYNAGI_BEYAN_EDILMEDI = (
    "ÇAĞIRAN BEYAN ETMEDİ: h(z) sayısal olarak verildi ama hangi "
    "korelasyondan/ölçümden geldiği bildirilmedi. Çözücü bir kaynak "
    "VARSAYMAZ (ConvectionBC.h_basis ile bildirilir).")


@dataclass(frozen=True)
class ConvectionBC:
    """Konveksiyon (Robin): q'' = h(z)·(T_inf(z) − T_cidar), cidara giren +.

    h [W/(m²·K)] ve T_inf [K], z [m] boyunca sabit ya da fonksiyon. Kenar
    integrallerinde h ve T_inf kenar ORTA NOKTASINDA değerlendirilir
    (O(h²) — beyan).

    P8B1-11 (ÖH D26 / fea-cfd a3) — h'NİN KAYNAĞI ÇAĞIRANINDIR.
    ÖLÇÜLDÜ (taban 7751531, ``once_a3.json``): çağıran SABİT 1234 W/(m²K)
    verdiğinde bile sonucun ``not_modelled`` künyesi "iç yüzeyde yalnız
    konveksiyon; **Bartz h**" diyordu. Yani beyan, çağıranın gerçekte
    gönderdiği katsayının kaynağını değil VARSAYILAN bir kaynağı ilan
    ediyordu — künye kendi bilmediği bir şeyi söylüyordu (P6B2-02
    borcunun canlı ucu, parti raporu §6). Artık kaynak ``h_basis`` ile
    çağırandan gelir; verilmezse künye "beyan edilmedi" der, model adı
    UYDURMAZ.

    h_basis : str|None — h(z)'nin kaynağının künyeli cümlesi (ör. "Bartz
        1965 Denk. 4, HeatTransferAnalyzer.analyze_axial_profile"). None
        ise :data:`H_KAYNAGI_BEYAN_EDILMEDI` yayımlanır.
    """
    h: PropertyLike
    T_inf: PropertyLike
    h_basis: Optional[str] = None


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
    #: ÖH D37 A2-1 F-02: otomatik sürücü yayımlanan seviyenin MESH'ini de
    #: döndürür (istenen mesh'ten farklı olabilir — SPATIAL_PUBLISH_LEVEL);
    #: çekirdek çözücü (solve_transient) bu alanı doldurmaz (None).
    published_mesh: Optional[AxisymMesh] = None


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


def _h_kaynagi_beyani(side: dict) -> str:
    """Bir yüzeyin h(z) kaynağının künyesi (P8B1-11).

    Robin (ConvectionBC) yüzeyinde çağıranın ``h_basis`` beyanı; verilmemişse
    :data:`H_KAYNAGI_BEYAN_EDILMEDI`. Konveksiyon olmayan yüzeyde h kavramı
    yoktur ve bu ADIYLA söylenir (boş dize bırakılmaz).
    """
    tip = side.get("type")
    if tip == "robin":
        bc = side.get("bc")
        beyan = getattr(bc, "h_basis", None)
        beyan = str(beyan).strip() if beyan else ""
        return beyan or H_KAYNAGI_BEYAN_EDILMEDI
    if tip == "ambient":
        bc = side.get("bc")
        return (f"doğal taşınım katsayısı çağırandan: h = {bc.h:g} "
                "W/(m²K) (AmbientBC)")
    return f"konveksiyon değil ({tip}) — h(z) kavramı bu yüzeyde yok"


def _m_matris_olcumu(K) -> dict:
    """K'nin M-matris olup olmadığını ÖLÇER (P8B1-08).

    Ayrık maksimum ilkesinin (geri Euler + topaklanmış kütle ile) koşulu
    iletim matrisinin köşegen-dışı girdilerinin ≤ 0 olmasıdır. Bilineer Q4
    elemanında bu koşul en-boy oranı √2'yi aştığında kırılır; ürünün
    kendi termal meshinde ortanca en-boy oranı 4-5 mertebesindedir.
    """
    A = K.tocoo()
    dis = A.row != A.col
    toplam = int(np.count_nonzero(dis))
    if toplam == 0:
        return {"olculdu": False,
                "beyan": "köşegen-dışı girdi yok — ölçüm anlamsız"}
    olcek = float(np.abs(A.data).max()) if A.data.size else 0.0
    esik = 1e-12 * max(olcek, 1.0)
    pozitif = int(np.count_nonzero(A.data[dis] > esik))
    return {
        "olculdu": True,
        "kosegen_disi_giris": toplam,
        "pozitif_giris": pozitif,
        "pozitif_oran": float(pozitif) / toplam,
        "en_buyuk_pozitif": (float(A.data[dis].max()) if toplam else None),
        "m_matris_mi": bool(pozitif == 0),
        "_basis": (
            "ayrık maksimum ilkesi K'nin M-matris olmasını (köşegen-dışı "
            "≤ 0) gerektirir; bilineer Q4'te en-boy oranı √2'yi aştığında "
            "kenar-komşusu girdi işaret değiştirir. Kütle topaklaması bu "
            "koşulu SAĞLAMAZ, yalnız zamansal kısmı düzeltir."),
    }


def _bc_surus_sicakliklari(side: dict):
    """Sınır koşulunun ALANI sürükleyebileceği sıcaklıklar [K].

    Dönüş: (liste, hepsi_bilinir). Dayatılmış AKI (Neumann) için sürüş
    sıcaklığı TANIMSIZDIR — o vakada kabul aralığı hesaplanamaz ve bu
    dürüstçe beyan edilir (uydurma sınır konmaz). Değerler ``_prepare_side``
    tarafından kenarlarda zaten örneklenmiştir; burada yeniden
    değerlendirilmez (tek kaynak).
    """
    tip = side.get("type")
    if tip == "adiabatic":
        return [], True
    if tip in ("robin", "ambient"):
        v = np.asarray(side["T_inf"], dtype=float)
    elif tip == "dirichlet":
        v = np.asarray(side["T_fixed"], dtype=float)
    else:                                   # flux
        return [], False
    if v.size == 0 or not np.all(np.isfinite(v)):
        return [], False
    return [float(v.min()), float(v.max())], True


def _aralik_denetimi(T_history, T_initial, inner_side, outer_side,
                     m_matris) -> dict:
    """Alan fiziksel olarak kabul edilebilir aralıkta mı (P8B1-08).

    Yalnız sürüş sıcaklıkları BİLİNEN sınır koşulu ailelerinde (Robin,
    Dirichlet, ortam, adyabatik) uygulanır: maksimum ilkesi gereği alan
    hiçbir anda [min(T₀, sürüş sıcaklıkları), max(T₀, sürüş sıcaklıkları)]
    dışına çıkmamalıdır. Çıkıyorsa bu SAYISAL bir yapaylıktır (K M-matris
    değil) ve sessizce geçilmez.
    """
    suruş = []
    bilinir = True
    for side in (inner_side, outer_side):
        vals, ok = _bc_surus_sicakliklari(side)
        bilinir = bilinir and ok
        if vals:
            suruş.extend(vals)
    # ÖH D37 A2-1: dizi (eski çağrı) ya da koşu sırasında izlenen
    # (min, maks) çifti (keep_history=False yolu) — aynı iki sayı.
    if isinstance(T_history, tuple) and len(T_history) == 2:
        T_min, T_maks = float(T_history[0]), float(T_history[1])
    else:
        T_min = float(np.min(T_history))
        T_maks = float(np.max(T_history))
    if not bilinir:
        return {
            "olculdu": False,
            "T_min": T_min, "T_maks": T_maks,
            "beyan": ("sınır koşullarından en az biri dayatılmış AKI "
                      "(Neumann); sürüş sıcaklığı tanımsız olduğu için "
                      "kabul aralığı ÖLÇÜLEMEZ — uydurma sınır konmaz"),
        }
    aday = list(suruş) + [float(T_initial)]
    alt, ust = min(aday), max(aday)
    # Sayısal tolerans: alan genliğinin 1e-9'u (kayan nokta gürültüsü).
    tol = 1e-9 * max(abs(ust - alt), 1.0)
    ihlal = bool(T_min < alt - tol or T_maks > ust + tol)
    return {
        "olculdu": True,
        "kabul_alt_K": alt,
        "kabul_ust_K": ust,
        "T_min": T_min,
        "T_maks": T_maks,
        "alt_asim_K": max(0.0, alt - T_min),
        "ust_asim_K": max(0.0, T_maks - ust),
        "ihlal": ihlal,
        "m_matris_mi": m_matris.get("m_matris_mi"),
        "_basis": (
            "yalnız ısıtan/soğutan sınır koşullarıyla alan, başlangıç "
            "sıcaklığı ile sürüş sıcaklıklarının kapsadığı aralığın dışına "
            "çıkamaz (sürekli maksimum ilkesi). Ayrık çözümde çıkıyorsa "
            "sebep K'nin M-matris olmamasıdır (bkz. meta['m_matris']) — "
            "sayı fiziksel değildir."),
    }


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
        # P8B1-11: h(z)'nin kaynağı ÇAĞIRANIN beyanıdır; çözücü model adı
        # uydurmaz (bkz. ConvectionBC.h_basis).
        "h_kaynagi": {
            "ic_yuzey": _h_kaynagi_beyani(inner_side),
            "dis_yuzey": _h_kaynagi_beyani(outer_side),
            "_basis": (
                "konveksiyon katsayısının hangi korelasyondan/ölçümden "
                "geldiğini yalnız ÇAĞIRAN bilir; ConvectionBC.h_basis ile "
                "bildirilir, bildirilmezse burada 'beyan edilmedi' yazar "
                "ve çözücü bir model adı VARSAYMAZ (P8B1-11)."),
        },
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
        # P8B1-08 (ÖH D15/a3): BU BEYAN ESKİDEN KOŞULSUZ "ayrık maksimum
        # ilkesi korunur" DİYORDU. Ayrık maksimum ilkesinin koşulu iletim
        # matrisi K'nin M-matris olmasıdır (köşegen-dışı ≤ 0); bilineer
        # Q4'te en-boy oranı √2'yi aştığında kenar-komşusu girdi işaret
        # değiştirir ve ÜRÜNÜN KENDİ meshinde köşegen-dışı girdilerin
        # %28,99'u POZİTİFTİR (ölçüldü: na=16/nr=4 termal varsayılan;
        # na=16/nr=16'da %25,76). Topaklama GEREKLİ koşuldur, YETERLİ
        # değildir. Beyan artık iddia etmiyor, ÖLÇÜYOR.
        "kutle_matrisi": ("satır toplamıyla topaklanmış (lumped); toplam ısı "
                          "sığası tutarlı kütleyle aynıdır. Topaklama ayrık "
                          "maksimum ilkesi için GEREKLİ koşuldur, YETERLİ "
                          "DEĞİLDİR: ilke ancak iletim matrisi K M-matris "
                          "ise (köşegen-dışı ≤ 0) garanti edilir; bu mesh "
                          "için ÖLÇÜM meta['m_matris'] alanındadır"),
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
            # P8B1-11: burada MODEL ADI yazılmaz — h'nin kaynağı çağıranın
            # beyanıdır ve meta['h_kaynagi'] alanında ADIYLA durur.
            "gaz tarafı ışıma (iç yüzeyde yalnız konveksiyon; h(z) "
            "çağıranın verdiği katsayıdır, kaynağı meta['h_kaynagi'])",
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
                    T_initial: float,
                    keep_history: bool = True) -> ThermalResult:
    """Verilen zaman ızgarasında geçici ısı iletimi çözümü (sayısal çekirdek).

    keep_history : False verilirse tam alan geçmişi ``T_history`` TUTULMAZ
        (``None`` döner; bellek ∝ N, (S+1)·N değil). Son alan, tepe cidar
        sıcaklığı geçmişi, enerji bütçesi ve aralık denetimi (koşu sırasında
        izlenen min/maks) yine tamdır. Uzamsal merdivenin ince seviyeleri bu
        kiple çözülür (ÖH D37 A2-1 F-02).

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
    T_history = np.empty((S + 1, n_nodes)) if keep_history else None
    if keep_history:
        T_history[0] = T
    # Geçmiş tutulmasa da tepe geçmişi, tepe düğümü ve aralık denetimi için
    # gereken istatistikler koşu SIRASINDA izlenir (aynı sayılar).
    peak_hist = np.empty(S + 1)
    peak_hist[0] = float(T_initial)
    peak_node_hist = np.zeros(S + 1, dtype=int)
    T_min_gozlenen = float(T_initial)
    T_maks_gozlenen = float(T_initial)
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
        # P8B1-06 FAIL-CLOSED — FİZİKSELLİK KAPISI.
        # Eskiden tek denetim ``isfinite``ti: çözücü MUTLAK SIFIRIN ALTINDA
        # sıcaklık alanı üretip (ölçüldü: −378,41 K, uç vakada −6,46e7 K)
        # bunu "Zaman adımı yakınsadı" beyanıyla döndürüyordu. Mutlak
        # sıcaklık termodinamikçe pozitif tanımlıdır (T [K] > 0); alanın
        # sıfırın altına inmesi bir SONUÇ değil, ayrıklaştırmanın çöktüğünün
        # kanıtıdır — üstelik ışıma lineerleştirmesi
        # h_ış = ε·σ·(T_s² + T_ort²)·(T_s + T_ort) T_s < −T_ort'ta NEGATİF
        # Robin katsayısı üretip modülün "koşulsuz kararlı geri Euler"
        # iddiasını da kırar. Sayı uydurulmaz, kırpılmaz: hüküm kazanılmadığı
        # için yayımlanmaz.
        T_min_yeni = float(np.min(T_new))
        if T_min_yeni <= 0.0:
            i_min = int(np.argmin(T_new))
            zr = mesh.nodes[i_min]
            raise RuntimeError(
                "FİZİKSEL OLMAYAN SICAKLIK ALANI: adım "
                f"{n + 1}/{S} sonunda (t = {times[n + 1]:.6g} s) en küçük "
                f"düğüm "
                f"sıcaklığı {T_min_yeni:.6g} K, yani mutlak sıfırın "
                f"altında (düğüm {i_min}, z = {zr[0]:.6g} m, "
                f"r = {zr[1]:.6g} m). Mutlak sıcaklık pozitif tanımlıdır; "
                "bu alan bir çözüm değil, ayrıklaştırmanın çöktüğünün "
                "kanıtıdır (aşırı yüzey akısı ve/veya çok büyük Δt; "
                "ışıma lineerleştirmesi T_s < −T_ortam'da NEGATİF Robin "
                "katsayısı üretir ve geri Euler'in koşulsuz kararlılık "
                "iddiası orada geçersizdir). Sonuç kırpılmaz ve "
                "yayımlanmaz: yüzey akısını küçültün ya da zaman adımını "
                "azaltın (P8B1-06).")

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
        if keep_history:
            T_history[n + 1] = T
        i_maks = int(np.argmax(T))
        peak_hist[n + 1] = float(T[i_maks])
        peak_node_hist[n + 1] = i_maks
        T_min_gozlenen = min(T_min_gozlenen, T_min_yeni)
        T_maks_gozlenen = max(T_maks_gozlenen, float(T[i_maks]))

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

    i_peak = int(np.argmax(peak_hist))
    peak_node = int(peak_node_hist[i_peak])

    meta = _result_meta(mesh, material, inner_side, outer_side, T_initial)
    meta["zaman_izgarasi"] = {"n_steps": S, "t_end_s": float(times[-1])}
    meta["alan_gecmisi_tutuldu"] = bool(keep_history)
    if not keep_history:
        meta["alan_gecmisi_beyani"] = (
            "T_history TUTULMADI (keep_history=False; bellek bütçesi): son "
            "alan, tepe cidar sıcaklığı geçmişi, enerji bütçesi ve aralık "
            "denetimi koşu sırasında izlenen aynı sayılardır; ara anların "
            "alanı bu sonuçtan okunamaz.")
    # --- P8B1-08: M-MATRİS ÖLÇÜMÜ + FİZİKSEL ARALIK DENETİMİ -------------
    meta["m_matris"] = _m_matris_olcumu(cache["K"])
    meta["aralik_denetimi"] = _aralik_denetimi(
        (T_min_gozlenen, T_maks_gozlenen), T_initial, inner_side, outer_side,
        meta["m_matris"])
    if meta["aralik_denetimi"].get("ihlal"):
        meta.setdefault("uyarilar", []).append({
            "code": "warn.fea.thermal_discrete_max_principle_violated",
            "params": {
                "t_min_K": round(meta["aralik_denetimi"]["T_min"], 4),
                "t_max_K": round(meta["aralik_denetimi"]["T_maks"], 4),
                "alt_sinir_K": round(
                    meta["aralik_denetimi"]["kabul_alt_K"], 4),
                "ust_sinir_K": round(
                    meta["aralik_denetimi"]["kabul_ust_K"], 4)}})

    return ThermalResult(
        times=times,
        T_history=T_history,
        T_final=T.copy(),
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

def _uzamsal_yakinsama(result, mesh, material, times, inner_bc, outer_bc,
                       T_initial, mesh_refiner, spatial_tol,
                       n_levels: int = DEFAULT_SPATIAL_LEVELS,
                       history_budget_values=DEFAULT_HISTORY_BUDGET_VALUES):
    """Üç seviyeli uzamsal merdiven + Celik 2008 GCI + kilitli hüküm (F-02).

    Dönüş: ``(blok, yayimlanan_sonuc, yayimlanan_mesh)``. ``mesh_refiner``
    yoksa ölçüm YAPILMAZ, bu ADIYLA beyan edilir ve kaba sonuç aynen döner;
    sayı uydurulmaz, "yakınsadı" denmez.

    Seviyeler: istenen ağ = seviye ``n_levels`` (kaba), her seviye
    n_axial ve n_radial'ı ikiye katlar (r = 2 tam, 2B: N oranı 4). Hepsi
    AYNI zaman ızgarasında çözülür (zaman yakınsaması kaba ağda kuruldu).
    Birincil QoI tepe cidar sıcaklığı YÜKSELİŞİ ΔT = peak_wall_T − T_initial
    (mutlak T değil: 2600 K ölçeğinde bağıl hata ΔT ölçeğindekinin ~0,9'u ve
    DK "ΔT'ye göre" ölçeğiyle aynı); ikincil QoI iç enerji değişimi dU_J
    (alan integrali — Dirichlet'e çivili tepeye kör değil, DK B7).

    Hüküm (olcut_kulvar.json K1, sonuç görülmeden kilitlendi):
      * ``converged``     — 3 seviye çözüldü, gci().status == 'monotonic',
                            p_signed ≥ SPATIAL_P_MIN_ASYMPTOTIC,
                            GCI_fine21 ≤ spatial_tol;
      * ``not_converged`` — 3 seviye çözüldü ama koşullardan biri sağlanmadı
                            (neden adıyla: sinif / p_dusuk / gci_buyuk);
      * ``degenerate``    — ardışık fark sıfır (QoI ağdan bağımsız ya da
                            sınıra çivili) — GCI yazılmaz;
      * ``not_evaluated`` — 3'ten az seviye çözüldü (refiner yok, ince koşu
                            hata verdi) — GCI yazılmaz.
    Yayımlanan seviye ``SPATIAL_PUBLISH_LEVEL`` ile seçilir; kaba seviyenin
    kalan hata kestirimi (Richardson dışdeğerine göre) ayrıca beyan edilir.
    Makine kanalı (denetçi Ş4/Ş7): ``neden_kodu`` (sinif / p_dusuk /
    gci_buyuk / dejenere / az_seviye / refiner_yok; converged'da None) ve
    ``richardson_guvenilir`` (None: dışdeğer yok; False: p < p_min — dışdeğer
    ve kalan hata yalnız yön göstergesi; True: asimptotik aralık).
    """
    import time as _time
    from hrma.utils.gci import gci as _gci

    T0 = float(T_initial)
    n_levels = int(n_levels)
    if n_levels < 3:
        raise ValueError("n_spatial_levels >= 3 olmalı (Celik 2008 üç ağ).")
    ortak = {
        "_source": "hrma.fea.thermal_axisym.solve_transient_auto",
        "yontem": (f"uzamsal merdiven: istenen ağ + {n_levels - 1} inceltme "
                   "(her seviyede n_axial ve n_radial ikiye katlanır, r = 2), "
                   "hepsi AYNI zaman ızgarasında; üç en ince seviyeden Celik "
                   "2008 GCI (hrma.utils.gci TEK tanım, işaretli p, Fs = "
                   "1,25); birincil QoI tepe cidar sıcaklığı yükselişi ΔT = "
                   "peak_wall_T − T_initial, ikincil QoI iç enerji dU_J"),
        "tol": float(spatial_tol),
        "p_min_asimptotik": float(SPATIAL_P_MIN_ASYMPTOTIC),
        "qoi": "peak_wall_T - T_initial",
        "kaba_mesh": {"n_axial": int(mesh.n_axial),
                      "n_radial": int(mesh.n_radial),
                      "n_nodes": int(mesh.n_nodes)},
        "yayimlanan_seviye_politikasi": SPATIAL_PUBLISH_LEVEL,
    }
    if mesh_refiner is None:
        ortak.update({
            "denetlendi": False,
            "converged": None,
            "rel_change": None,
            "hukum": "not_evaluated",
            "neden": "mesh_refiner yok",
            "neden_kodu": "refiner_yok",
            "richardson_guvenilir": None,
            "seviyeler": [],
            "beyan": (
                "UZAMSAL YAKINSAMA DENETLENMEDİ: mesh'i inceltecek bir "
                "üretici (mesh_refiner) verilmedi, bu yüzden tepe cidar "
                "sıcaklığının mesh'e duyarlılığı ÖLÇÜLMEMİŞTİR. Zaman "
                "ekseni yakınsamış olsa bile uzamsal hata bilinmiyor; "
                "sonuç bu beyanla birlikte okunmalıdır (P8B1-10)."),
        })
        return ortak, result, mesh

    S = int(np.asarray(times).size) - 1
    seviyeler = [{
        "seviye": n_levels, "n_axial": int(mesh.n_axial),
        "n_radial": int(mesh.n_radial), "n_elems": int(mesh.n_elems),
        "n_nodes": int(mesh.n_nodes), "peak_wall_T": float(result.peak_wall_T),
        "delta_T_peak": float(result.peak_wall_T) - T0,
        "dU_J": float(result.energy["dU_J"]), "sure_s": None,
        "gecmis_tutuldu": bool(result.T_history is not None),
        "hata": None,
    }]
    sonuclar = [(result, mesh)]
    hata = None
    for k in range(1, n_levels):
        na = int(mesh.n_axial) * 2 ** k
        nr = int(mesh.n_radial) * 2 ** k
        t0 = _time.perf_counter()
        try:
            ince = mesh_refiner(na, nr)
            # Yalnız yayımlanabilecek en ince seviye geçmiş tutar ve o da
            # ancak bütçeye sığıyorsa; ara seviyeler için geçmiş gereksiz.
            son_seviye = (k == n_levels - 1)
            tut = bool(son_seviye and SPATIAL_PUBLISH_LEVEL == "finest"
                       and history_budget_values is not None
                       and (S + 1) * int(ince.n_nodes)
                       <= int(history_budget_values))
            res_k = solve_transient(ince, material, times, inner_bc,
                                    outer_bc, T_initial, keep_history=tut)
        except Exception as exc:                          # noqa: BLE001
            hata = {"seviye": n_levels - k, "n_axial": na, "n_radial": nr,
                    "tip": type(exc).__name__, "mesaj": str(exc),
                    "sure_s": _time.perf_counter() - t0}
            break
        seviyeler.append({
            "seviye": n_levels - k, "n_axial": int(ince.n_axial),
            "n_radial": int(ince.n_radial), "n_elems": int(ince.n_elems),
            "n_nodes": int(ince.n_nodes),
            "peak_wall_T": float(res_k.peak_wall_T),
            "delta_T_peak": float(res_k.peak_wall_T) - T0,
            "dU_J": float(res_k.energy["dU_J"]),
            "sure_s": _time.perf_counter() - t0,
            "gecmis_tutuldu": bool(res_k.T_history is not None),
            "hata": None,
        })
        sonuclar.append((res_k, ince))

    # --- Eski iki-seviye alanları (P8B1-10 sözleşmesi, tüketiciler okuyor) --
    kaba_tepe = float(result.peak_wall_T)
    olcek = max(abs(kaba_tepe - T0), 1e-9 * abs(T0))
    if len(seviyeler) >= 2:
        ince_tepe = seviyeler[1]["peak_wall_T"]
        rel_pair = abs(ince_tepe - kaba_tepe) / olcek
        ortak.update({
            "ince_mesh": {"n_axial": seviyeler[1]["n_axial"],
                          "n_radial": seviyeler[1]["n_radial"],
                          "n_nodes": seviyeler[1]["n_nodes"]},
            "kaba_peak_wall_T": kaba_tepe,
            "ince_peak_wall_T": ince_tepe,
            "rel_change": float(rel_pair),
        })
    else:
        ortak.update({"kaba_peak_wall_T": kaba_tepe, "rel_change": None})

    ortak["seviyeler"] = seviyeler
    ortak["seviye_sayisi"] = len(seviyeler)
    ortak["inceltme_hatasi"] = hata

    # --- GCI (üç en ince seviye) ------------------------------------------
    gci_blok = None
    gci_dU = None
    hukum = "not_evaluated"
    neden = None
    # ÖH D37 A2-1 denetçi Ş4 — NEDEN KODU (makine kanalı). ``neden`` Türkçe
    # künye metnidir (eskiden iç kodla başlıyordu); ekran onu BASMAZ (EN
    # ekranda Türkçe metin ve 'p_dusuk' görünüyordu — ölçüldü, sonra/kare/
    # termal_panel_t7_1440.png). Panel yalnız bu kodu okur ve EN/TR i18n
    # anahtarından kendi dilinde kurar.
    neden_kodu = None
    if len(seviyeler) >= 3:
        # GCI ÜÇ EN İNCE seviyeden (4 seviyede 2.-4.); denetçi X2: en kaba
        # üçlü seçilirse a1 TestF02DortSeviye kırmızı verir.
        uclu = seviyeler[-3:]                     # kaba → ince sırada
        N = tuple(float(sv["n_elems"]) for sv in reversed(uclu))
        f_dT = tuple(float(sv["delta_T_peak"]) for sv in reversed(uclu))
        f_dU = tuple(float(sv["dU_J"]) for sv in reversed(uclu))
        gci_blok = _gci(N, f_dT, dim=2)
        try:
            gci_dU = _gci(N, f_dU, dim=2)
        except ValueError:
            gci_dU = None
        if gci_blok["status"] == "degenerate":
            hukum, neden_kodu, neden = "degenerate", "dejenere", (
                "ardışık seviyelerde ΔT_peak farkı sıfır — QoI ağdan "
                "bağımsız ya da sınıra çivili (Dirichlet); GCI yazılmaz, "
                "ikincil QoI (dU_J) beyanı okunmalı")
        # Ş4: insan metni iç kodu TAŞIMAZ (eskiden "p_dusuk: …" diye
        # başlıyordu ve künye/not_modelled satırından EN ekrana sızıyordu);
        # kod yalnız ``neden_kodu`` alanında.
        elif gci_blok["status"] != "monotonic":
            hukum, neden_kodu, neden = "not_converged", "sinif", (
                f"merdiven sınıfı {gci_blok['sinif']} ({gci_blok['status']}) "
                "— monoton yakınsama yok, GCI yazılmaz")
        elif gci_blok["p"] < SPATIAL_P_MIN_ASYMPTOTIC:
            hukum, neden_kodu, neden = "not_converged", "p_dusuk", (
                f"gözlenen mertebe {gci_blok['p']:.3f} < "
                f"{SPATIAL_P_MIN_ASYMPTOTIC:g} (formel 2'nin yarısı) — "
                "asimptotik aralık dışı, Richardson dışdeğeri güvenilmez")
        elif gci_blok["GCI_fine21"] > float(spatial_tol):
            hukum, neden_kodu, neden = "not_converged", "gci_buyuk", (
                f"GCI_fine21 = %{100.0 * gci_blok['GCI_fine21']:.3f}"
                f" > tolerans %{100.0 * float(spatial_tol):.2f}")
        else:
            hukum = "converged"
    else:
        neden_kodu = "az_seviye"
        neden = ("üç seviyeden azı çözüldü"
                 + (f" (inceltme hatası: {hata['tip']}: {hata['mesaj']})"
                    if hata else ""))

    ortak["gci"] = gci_blok
    ortak["gci_dU"] = gci_dU
    ortak["hukum"] = hukum
    ortak["neden"] = neden
    ortak["neden_kodu"] = neden_kodu
    ortak["denetlendi"] = bool(len(seviyeler) >= 3)
    ortak["converged"] = (True if hukum == "converged"
                          else False if hukum in ("not_converged", "degenerate")
                          else None)
    if gci_blok is not None and gci_blok.get("gci_valid"):
        f_ext = gci_blok["f_ext"]
        ortak["p"] = gci_blok["p"]
        ortak["GCI_fine21"] = gci_blok["GCI_fine21"]
        ortak["delta_T_ext_K"] = f_ext
        ortak["peak_wall_T_ext_K"] = T0 + f_ext
        # Her seviyenin Richardson dışdeğerine göre kalan hata kestirimi —
        # DK B1: kaba sonucun hatası |ince − kaba|'dan büyüktür (p < 2).
        for sv in seviyeler:
            sv["kalan_hata_kestirimi_K"] = float(f_ext - sv["delta_T_peak"])
            sv["kalan_hata_kestirimi_bagil"] = (
                float(abs(f_ext - sv["delta_T_peak"]) / abs(f_ext))
                if f_ext else None)
    else:
        ortak["p"] = None
        ortak["GCI_fine21"] = None
    # ÖH D37 A2-1 denetçi Ş7 — RICHARDSON GÜVENİLİRLİK BAYRAĞI. Dışdeğer ve
    # kalan hata kestirimleri p < SPATIAL_P_MIN_ASYMPTOTIC iken de sayı
    # olarak üretiliyordu (monoton üçlü) ama asimptotik aralık dışında
    # anlamsızdır — hüküm metni zaten "güvenilmez" diyordu, sayılar ise
    # bayraksız yayımlanıyordu (T7 eski gaz: dışdeğer 2640,21 K, kalan hata
    # +57,66 K). Sayılar DEĞİŞMEZ; yalnız bayrak: None = dışdeğer yok (monoton
    # değil / üç seviye yok), False = var ama güvenilmez, True = asimptotik.
    ortak["richardson_guvenilir"] = (
        None if not (gci_blok is not None and gci_blok.get("gci_valid"))
        else bool(gci_blok["p"] >= SPATIAL_P_MIN_ASYMPTOTIC))

    # --- Yayımlanan seviye ---------------------------------------------------
    if SPATIAL_PUBLISH_LEVEL == "finest":
        yay_res, yay_mesh = sonuclar[-1]
        yay_i = len(seviyeler) - 1
    else:
        yay_res, yay_mesh = sonuclar[0]
        yay_i = 0
    for i, sv in enumerate(seviyeler):
        sv["yayimlandi"] = (i == yay_i)
    ortak["yayimlanan_seviye"] = {
        "seviye": seviyeler[yay_i]["seviye"],
        "n_axial": seviyeler[yay_i]["n_axial"],
        "n_radial": seviyeler[yay_i]["n_radial"],
        "n_elems": seviyeler[yay_i]["n_elems"],
        "n_nodes": seviyeler[yay_i]["n_nodes"],
        "peak_wall_T": seviyeler[yay_i]["peak_wall_T"],
        "gecmis_tutuldu": seviyeler[yay_i]["gecmis_tutuldu"],
    }
    ortak["en_ince_mesh"] = {"n_axial": seviyeler[-1]["n_axial"],
                             "n_radial": seviyeler[-1]["n_radial"],
                             "n_nodes": seviyeler[-1]["n_nodes"]}

    # --- Beyan ----------------------------------------------------------------
    merdiven_metni = " → ".join(
        f"{sv['n_axial']}×{sv['n_radial']} {sv['peak_wall_T']:.4f} K"
        for sv in seviyeler)
    if hukum == "converged":
        beyan = (f"Uzamsal yakınsama SAĞLANDI (üç seviyeli merdiven + GCI): "
                 f"{merdiven_metni}; gözlenen mertebe p = {gci_blok['p']:.3f}, "
                 f"GCI_fine21 = %{100.0 * gci_blok['GCI_fine21']:.4f} "
                 f"(tolerans %{100.0 * float(spatial_tol):.2f}), Richardson "
                 f"dışdeğeri {T0 + gci_blok['f_ext']:.4f} K. Yayımlanan: "
                 f"{seviyeler[yay_i]['n_axial']}×{seviyeler[yay_i]['n_radial']}"
                 f" seviyesi.")
    elif hukum == "not_converged":
        beyan = (f"Uzamsal yakınsama SAĞLANMADI: {merdiven_metni}; {neden}. "
                 "Yayımlanan tepe sıcaklık mesh'e HÂLÂ duyarlıdır; sayı "
                 "silinmez ama yakınsamış sayılmaz (P8B1-10, OH-DK-08)."
                 + (f" Kaba seviyenin kalan hata kestirimi "
                    f"{seviyeler[0]['kalan_hata_kestirimi_K']:+.2f} K"
                    + (" (GÜVENİLMEZ: gözlenen mertebe asimptotik alt "
                       "sınırın altında — Richardson dışdeğeri ve kalan "
                       "hata yalnız yön göstergesidir, hata SINIRI değil)."
                       if ortak["richardson_guvenilir"] is False else ".")
                    if gci_blok is not None and gci_blok.get("gci_valid")
                    else ""))
    elif hukum == "degenerate":
        beyan = (f"Uzamsal yakınsama DEJENERE: {merdiven_metni}; {neden}."
                 + (f" İkincil QoI dU_J: {gci_dU['sinif']}"
                    + (f", p = {gci_dU['p']:.3f}, GCI_fine21 = "
                       f"%{100.0 * gci_dU['GCI_fine21']:.4f}"
                       if gci_dU.get("gci_valid") else "") + "."
                    if gci_dU is not None else ""))
    else:
        beyan = (f"UZAMSAL YAKINSAMA ÖLÇÜLEMEDİ: {merdiven_metni}; {neden}. "
                 "Üç seviye olmadan GCI kurulmaz; yayımlanan sonucun uzamsal "
                 "hatası bilinmiyor (P8B1-10).")
    ortak["beyan"] = beyan
    return ortak, yay_res, yay_mesh


def solve_transient_auto(mesh: AxisymMesh,
                         material: ThermalMaterial,
                         t_end: float,
                         inner_bc,
                         outer_bc,
                         T_initial: float,
                         tol: float = DEFAULT_DT_TOL,
                         n_steps0: int = DEFAULT_N_STEPS0,
                         max_halvings: int = DEFAULT_MAX_DT_HALVINGS,
                         mesh_refiner=None,
                         spatial_tol: float = DEFAULT_SPATIAL_TOL,
                         n_spatial_levels: int = DEFAULT_SPATIAL_LEVELS,
                         history_budget_values=DEFAULT_HISTORY_BUDGET_VALUES
                         ) -> ThermalResult:
    """Zaman adımını KENDİ seçen giriş noktası (kullanıcı ayar görmez).

    Adım sayısı ``n_steps0``'dan başlar ve her turda ikiye katlanır (adım
    yarılanır); ardışık iki koşunun TEPE CİDAR SICAKLIĞI GEÇMİŞİ ortak zaman
    noktalarında karşılaştırılır. Bağıl fark (ölçek: alanın başlangıçtan en
    büyük sapması) ``tol`` altına inince durulur. Sonuç, hangi adımın
    kullanıldığını, son farkı ve yakınsayıp yakınsamadığını
    ``meta['zaman_adimi']`` içinde AÇIKÇA beyan eder — yakınsamamış koşu
    yakınsamış gibi sunulmaz (V2.7 §3 felsefesi, zaman ekseni).

    P8B1-10 (ÖH D26 / fea-cfd a3) — UZAMSAL EKSEN DE ÖLÇÜLÜR.
    ÖLÇÜLDÜ (taban 7751531, ``once_a3.json``): bu modül kendini "V2.7 §3
    mesh yakınsama felsefesinin ZAMAN eksenindeki karşılığı" diye
    tanıtıyordu; kardeş YAPISAL zincir mesh'i inceltip yakınsamayı
    beyan ederken termal zincir sabit 16×4 mesh'te kalıyor ve uzamsal
    yakınsama hiç DENETLENMİYORDU — üstelik sonuç meta'sında bunun
    beyanı da yoktu (``meta`` anahtarları arasında ``zaman_adimi`` vardı,
    uzamsal karşılığı yoktu). Yakınsamamış olabileceği bilinmeyen bir
    sayı "tepe cidar sıcaklığı" diye yayımlanıyordu.

    Artık ``meta['uzamsal_yakinsama']`` HER koşuda vardır:
      * ``mesh_refiner`` verildiyse mesh bir kez inceltilir (n_axial ve
        n_radial ikiye katlanır), AYNI zaman ızgarasında çözülür ve tepe
        cidar sıcaklığının bağıl değişimi ``spatial_tol`` ile yargılanır;
      * verilmediyse blok ``denetlendi: False`` ile durur ve neyin
        bilinmediğini ADIYLA söyler (sessiz boşluk bırakılmaz).

    mesh_refiner : (n_axial, n_radial) → AxisymMesh çağrılabiliri. Mesh'i
        kuran katman (ör. ``hrma.fea.bridge``) verir; çözücü konturu
        bilmediği için mesh'i KENDİ inceltemez.
    spatial_tol : tepe cidar sıcaklığının kabul edilen bağıl değişimi.
    n_spatial_levels : merdiven seviye sayısı (≥ 3; F-02).
    history_budget_values : yayımlanan ince seviyenin alan geçmişini tutma
        bütçesi ((S+1)·N); None → tutulmaz.

    ÖH D37 A2-1 termal (F-02 + OH-DK-08, OH-DK-11):
      * uzamsal eksen artık ÜÇ seviyeli merdiven + Celik 2008 GCI ile
        hükme bağlanır (``_uzamsal_yakinsama``); yayımlanan sonuç
        ``SPATIAL_PUBLISH_LEVEL`` seviyesinin çözümüdür ve
        ``meta['uzamsal_yakinsama']['yayimlanan_seviye']`` bunu yazar;
      * zaman ölçütü tepe cidar sıcaklığı geçmişi DEĞİL, ortak zaman
        noktalarında bütün alanın L∞ farkıdır. ÖLÇÜLDÜ (DK T5a, iç yüz
        Dirichlet 800 K): tepe düğümü sınıra çivili olduğu için eski ölçüt
        rel = 0,0 ile 1. yarılamada (32 adım) "yakınsadı" diyordu, alan
        hatası t = 4 s'de 0,0133 θ idi (OH-DK-11). Alan normu tepe normunu
        her zaman ÜSTTEN sınırlar (|maks_i a − maks_i b| ≤ maks_i |a − b|),
        yani konvektif motor zincirinde hüküm gevşemez, sıkılaşabilir.
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
        # OH-DK-11: ALAN normu — ortak zaman noktalarında bütün düğümler.
        rel = float(np.max(np.abs(result.T_history[::2]
                                  - result_prev.T_history)) / scale)
        rel_peak = float(np.max(np.abs(result.peak_wall_T_history[::2]
                                       - result_prev.peak_wall_T_history))
                         / scale)
        history.append({"n_steps": n, "dt_s": t_end / n,
                        "peak_wall_T": result.peak_wall_T,
                        "rel_change": rel,
                        "rel_change_peak": rel_peak})
        result_prev = result
        if rel < tol:
            converged = True
            break

    result = result_prev
    dt_final = t_end / n
    if converged:
        beyan = (f"Zaman adımı yakınsadı: {n} adım (Δt = {dt_final:.6g} s); "
                 f"son iki koşu arasında alanın (bütün düğümler, ortak zaman "
                 f"noktaları) L∞ farkı %{100.0 * rel:.3f} "
                 f"(tolerans %{100.0 * tol:.2f}).")
    elif rel is None:
        beyan = (f"ZAMAN ADIMI YAKINSAMASI DENETLENEMEDİ: tek koşu yapıldı "
                 f"({n} adım, max_halvings = 0); karşılaştırılacak ikinci "
                 "koşu yok.")
    else:
        beyan = (f"ZAMAN ADIMI YAKINSAMADI: {len(history)} koşuda son fark "
                 f"%{100.0 * rel:.3f}, tolerans %{100.0 * tol:.2f} altına "
                 f"inmedi ({n} adım, Δt = {dt_final:.6g} s). Sonuç bu "
                 "beyanla birlikte değerlendirilmelidir.")

    # --- UZAMSAL EKSEN (P8B1-10 → F-02 üç seviyeli merdiven + GCI) --------
    uzamsal, result, yay_mesh = _uzamsal_yakinsama(
        result, mesh, material, np.linspace(0.0, t_end, n + 1),
        inner_bc, outer_bc, T_initial, mesh_refiner, spatial_tol,
        n_levels=n_spatial_levels,
        history_budget_values=history_budget_values)
    result.meta["uzamsal_yakinsama"] = uzamsal
    result.meta["yayimlanan_mesh"] = {
        "n_axial": int(yay_mesh.n_axial), "n_radial": int(yay_mesh.n_radial),
        "n_nodes": int(yay_mesh.n_nodes), "n_elems": int(yay_mesh.n_elems),
        "istenen_mesh": {"n_axial": int(mesh.n_axial),
                         "n_radial": int(mesh.n_radial)},
        "beyan": ("yayımlanan alan ve tepe sıcaklık BU mesh'in çözümüdür; "
                  "zaman adımı yakınsaması istenen (kaba) mesh'te kuruldu ve "
                  "aynı Δt ile bu mesh'te çözüldü (F-02)"),
    }
    result.published_mesh = yay_mesh

    result.meta["zaman_adimi"] = {
        "_source": "hrma.fea.thermal_axisym.solve_transient_auto",
        "yontem": ("adım ikiye bölme; ölçüt: ortak zaman noktalarında bütün "
                   "alanın L∞ farkı / alanın başlangıçtan en büyük sapması "
                   "(OH-DK-11; eski ölçüt yalnız tepe cidar T geçmişiydi — "
                   "her kayıtta rel_change_peak olarak da yazılır); "
                   "yakınsama istenen (kaba) mesh'te kuruldu"),
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
