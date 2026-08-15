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
2b. DIŞ YÜZEY EĞRİLİK TABANI (yalnız "normal" kipte): normal öteleme,
   KONKAV (dıştan çukur) vadide dış eğrinin eğrilik yarıçapını Rn − t'ye
   küçültür; Rn → t limitinde dış eğri jilet-çentiğe dejenere olur ve
   inceltme yakınsamaz (ölçüldü: sıvı varsayılanında tepe vM turda %16-18
   büyümeye devam ediyordu). Bu iyi-konumsuzluk, dış eğriye yarıçapı
   ``floor = t`` olan YUVARLANAN-TOP düzeltmesiyle (morfolojik kapama:
   top-şekilli yapısal elemanla genişletme + aşındırma) giderilir. Kapama
   yalnız topun GİREMEDİĞİ konkav vadileri tam ``floor`` yarıçaplı yayla
   köprüler; konveks bölgeler ve iç yüzey HİÇ değişmez. Gerekçe: (a)
   iyi-konumluluk — normal öteleme Rn → t'de dejeneredir, taban problemi
   iyi-konumlu yapar; (b) fiziksel gerçeklik — dış profil t mertebesinde
   yarıçaplı takımla işlenebilir yüzeydir, jilet-vadi imal edilmez. Kapama
   n_axial'dan BAĞIMSIZ sabit yoğunlukta bir z-ızgarasında hesaplanır
   (inceltme turları aynı geometriye yakınsasın diye); yerel kalınlaşma
   ölçülür ve ``meta['dis_yuzey_egrilik_tabani']`` içinde beyan edilir.
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
* J. Serra, "Image Analysis and Mathematical Morphology", Academic Press,
  1982 — gri-ton morfolojik kapama (yuvarlanan-top düzeltmesinin temeli).
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

# ---------------------------------------------------------------------------
# Dış yüzey eğrilik tabanı (yuvarlanan-top kapaması) politikası — TEK tanım.
# ---------------------------------------------------------------------------
#: ``outer_curvature_floor`` için "tabanı cidar kalınlığından al" nöbetçisi:
#: floor = max(t). Kalınlık dizi verildiğinde en BÜYÜK değer alınır — taban
#: her istasyonda t'yi karşılasın diye konservatif seçimdir ve beyan edilir.
OUTER_CURVATURE_FLOOR_AUTO = "auto"

#: Kapama ızgarası adımı: dz = floor / CLOSING_STEP_DIVISOR. Topun yay
#: kordlama hatası ~ dz²/(2·floor) mertebesindedir. 256 bölme seçildi:
#: kapanmış eğri parçalı-doğrusal temsil edilir ve istasyon aralığı dz'nin
#: ALTINA inerse ölçülen ayrık konkav yarıçap H'nin KENDİ kırıklarını
#: görmeye başlar (ölçüldü: 32 bölmede dereceli ince istasyonlar tabanın
#: %27 altını rapor etti — geometri değil temsil kusuru). dz, dereceli en
#: ince istasyon aralığının altında kalacak kadar küçük tutulur.
CLOSING_STEP_DIVISOR = 256

#: Kapama ızgarası nokta sayısı sınırları (bellek/eski küçük geometri
#: koruması). Izgara yalnız kontur + taban'a bağlıdır, n_axial'a DEĞİL —
#: inceltme turları aynı kapanmış geometriye yakınsar.
CLOSING_GRID_MIN_POINTS = 2048
CLOSING_GRID_MAX_POINTS = 65536

#: Kaldırma eşiği: eps = floor / CLOSING_LIFT_EPS_DIVISOR (fiziksel ölçek;
#: 2 mm tabanda ~2 µm). Bundan küçük "kaldırmalar" düzeltme sayılmaz —
#: konveks/düz bölgeler bit-değişmeden kalır (doğru parçaları üzerinde
#: ayrık kapama zaten TAM özdeşliktir: dilate + erode aynı ayrık maksimumu
#: alıp geri verir). Sivri-ama-sığ köşeler bu eşiğe TAKILMAZ: onları
#: kaldırma değil geometrik tespit (tabanaltı çevrel yarıçap) yakalar.
CLOSING_LIFT_EPS_DIVISOR = 1024.0

#: Köşe komşuluğu politikası. Sivri-ama-sığ köşelerde (motor konturu bir
#: POLİGONDUR; tepe başına dönüş ~birkaç derece olabilir) top-köprü
#: kaldırması eps'in ALTINDA kalır ama köşe yine tabanın altındadır —
#: tespit bu yüzden kaldırmayla değil GEOMETRİYLE yapılır: yoğun dış
#: eğride ayrık konkav çevrel yarıçapı < taban olan tepeler işaretlenir.
#: İşaretli tepenin ± CORNER_NEIGHBORHOOD_STATIONS istasyonluk komşuluğu
#: da kapanmış eğriye oturtulur; çünkü merkezî-fark normali köşünün
#: komşusunda her inceltme turunda farklı "bulaşır" ve dış geometriyi
#: tur-bağımlı yapardı (ölçüldü: sıvı varsayılanında tepe vM turda %16-18
#: büyümeye devam ediyordu). Komşuluk yarıçapı kaba turlarda
#: CORNER_NEIGHBORHOOD_MAX_FLOORS · taban ile sınırlanır.
CORNER_NEIGHBORHOOD_STATIONS = 2
CORNER_NEIGHBORHOOD_MAX_FLOORS = 4.0

#: Dereceli eksenel örnekleme. İşaretli (tabanaltı) köşelerin gerilme
#: alanı, köşe/köprü ölçeğinde (poligon tepe aralığı, ölçülen ~0,3 mm)
#: değişir; tekdüze örnekleme bu ölçeği uç noktanın eleman bütçesi içinde
#: ÇÖZEMEZ (ölçüldü: sıvı varsayılanında tekdüze eksenel bölme na=1024'e
#: kadar %1'e inmiyor, bütçe na=256'da bitiyor). İşaretli köşenin
#: ± CORNER_REFINE_WINDOW_FLOORS · taban penceresinde istasyon yoğunluğu
#: CORNER_REFINE_FACTOR katına çıkarılır (ters-CDF yerleşimi). Ağırlık
#: yalnız geometriye bağlıdır (n_axial'a DEĞİL): her inceltme turu aynı
#: dereceli koordinatı böler, limit geometri sabittir. İşaretli köşe
#: yoksa örnekleme TEKDÜZEDİR ve eski davranışla bit-özdeştir.
CORNER_REFINE_FACTOR = 8.0
CORNER_REFINE_WINDOW_FLOORS = 4.0


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


def polyline_concave_radii(points):
    """Poligon zinciri üzerinde KONKAV köşelerin ayrık eğrilik yarıçapı.

    (z, r) düzleminde artan-z yönünde gezilen bir DIŞ yüzey zincirinde
    "vadi" (dıştan çukur, eğrilik merkezi dış tarafta) ardışık kenarların
    SAAT YÖNÜNÜN TERSİNE (CCW) dönmesidir: cross(e_k, e_{k+1}) > 0.
    Her iç köşe için üç noktanın çevrel çember yarıçapı döner — çember
    üzerindeki üç nokta için bu TAM olarak çemberin yarıçapıdır, yani yay
    örneklemesi ayrık ölçümü saptırmaz.

    Dönüş: (R, konkav) — ikisi de (N-2,) dizi; R çevrel yarıçap [m]
    (düz üçlüde inf), konkav bool maskesi (cross > 0).
    """
    P = np.asarray(points, dtype=float)
    if P.ndim != 2 or P.shape[1] != 2 or P.shape[0] < 3:
        raise ValueError("points (N, 2) biçiminde ve en az 3 noktalı olmalı.")
    e1 = P[1:-1] - P[:-2]
    e2 = P[2:] - P[1:-1]
    e3 = P[2:] - P[:-2]
    a = np.hypot(e1[:, 0], e1[:, 1])
    b = np.hypot(e2[:, 0], e2[:, 1])
    c = np.hypot(e3[:, 0], e3[:, 1])
    cross = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.where(np.abs(cross) > 0.0,
                     a * b * c / (2.0 * np.abs(cross)), np.inf)
    return R, cross > 0.0


def _upper_envelope_on_grid(curve: np.ndarray, z0: float, dz: float,
                            n_grid: int) -> np.ndarray:
    """Poligon zincirinin z-ızgarası üzerindeki ÜST ZARFI.

    Normal öteleme konkav vadide kendi üstüne katlanabilir (swallowtail);
    katlanmış eğrinin geçerli dış sınırı üst zarfıdır. Her doğru parçası
    kapsadığı ızgara düğümlerinde TAM lineer enterpolasyonla örneklenir ve
    düğüm başına maksimum alınır — kutu-içi maksimum kaydırması (bin max)
    yoktur, zarf ızgara düğümlerinde eğrinin kendisidir.
    """
    z = curve[:, 0]
    r = curve[:, 1]
    F = np.full(n_grid, -np.inf)
    za, zb = z[:-1], z[1:]
    ra, rb = r[:-1], r[1:]
    lo = np.minimum(za, zb)
    hi = np.maximum(za, zb)
    i0 = np.ceil((lo - z0) / dz - 1e-12).astype(np.int64)
    i1 = np.floor((hi - z0) / dz + 1e-12).astype(np.int64)
    i0 = np.clip(i0, 0, n_grid - 1)
    i1 = np.clip(i1, -1, n_grid - 1)
    cnt = np.maximum(i1 - i0 + 1, 0)
    total = int(cnt.sum())
    if total:
        seg = np.repeat(np.arange(cnt.size), cnt)
        offs = np.arange(total) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        gi = i0[seg] + offs
        zg = z0 + gi * dz
        dzseg = zb[seg] - za[seg]
        with np.errstate(divide="ignore", invalid="ignore"):
            tpar = np.where(dzseg != 0.0, (zg - za[seg]) / dzseg, 0.0)
        vals = ra[seg] + np.clip(tpar, 0.0, 1.0) * (rb[seg] - ra[seg])
        np.maximum.at(F, gi, vals)
    # Köşe NOKTALARI da zarfa katılır (iki ızgara düğümü arasına düşen
    # tepe kaybolmasın diye en yakın düğüme yansıtılır — yalnız yükseltir).
    gi_p = np.clip(np.rint((z - z0) / dz).astype(np.int64), 0, n_grid - 1)
    np.maximum.at(F, gi_p, r)
    mask = np.isfinite(F)
    if not mask.all():
        idx = np.arange(n_grid)
        F = np.interp(idx, idx[mask], F[mask])
    return F


def _rolling_ball_closing(F: np.ndarray, dz: float,
                          radius: float) -> np.ndarray:
    """r = F(z) fonksiyonuna disk (yuvarlanan top) morfolojik KAPAMASI.

    Kapama = top-şekilli yapısal elemanla genişletme (dilate, kayan
    maksimum) + aşındırma (erode, kayan minimum). Sonuç F'nin altına asla
    inmez; topun DIŞARIDAN giremediği (yerel eğrilik yarıçapı < radius)
    vadileri tam ``radius`` yarıçaplı yayla köprüler, dokunabildiği her
    yerde (konveks/düz/geniş konkav) F'yi aynen bırakır. Doğru parçaları
    üzerinde ayrık işlem TAM özdeşliktir: dilate'in eklediği sabit,
    erode'un çıkardığı aynı ayrık maksimumdur.

    Kaynak: J. Serra, "Image Analysis and Mathematical Morphology",
    Academic Press, 1982 (gri-ton kapama); görüntü işlemede "rolling ball
    background" olarak bilinen aynı yapı.
    """
    n = F.size
    m = int(np.ceil(radius / dz))
    # Uçlar TEĞET uzatılır (uç eğimiyle lineer ekstrapolasyon): pencere uçta
    # kırpılırsa top "kenardan düşer" ve düz/eğik uç kesitler sahte biçimde
    # kaldırılırdı (ölçüldü: eğik konide uç istasyonlar oynuyordu). Teğet
    # uzatmayla doğru parçaları üzerinde ayrık kapama uçta da TAM özdeştir.
    k = min(8, n - 1)
    slope_l = (F[k] - F[0]) / (k * dz)
    slope_r = (F[n - 1] - F[n - 1 - k]) / (k * dz)
    sol = F[0] + slope_l * (np.arange(-m, 0) * dz)
    sag = F[n - 1] + slope_r * (np.arange(1, m + 1) * dz)
    Fp = np.concatenate([sol, F, sag])
    npad = Fp.size
    j = np.arange(-m, m + 1)
    ball = np.sqrt(np.maximum(radius ** 2 - (j * dz) ** 2, 0.0))
    G = np.full(npad, -np.inf)
    for jj, b in zip(j, ball):
        t0, t1 = max(0, jj), min(npad, npad + jj)
        if t0 < t1:
            np.maximum(G[t0:t1], Fp[t0 - jj:t1 - jj] + b, out=G[t0:t1])
    H = np.full(npad, np.inf)
    for jj, b in zip(j, ball):
        t0, t1 = max(0, -jj), min(npad, npad - jj)
        if t0 < t1:
            np.minimum(H[t0:t1], G[t0 + jj:t1 + jj] - b, out=H[t0:t1])
    H = H[m:m + n]
    # Kapama tanım gereği F'nin altına inmez; yuvarlama mikro ihlal
    # üretmesin diye eşitlik zorlanır.
    return np.maximum(H, F)


def _closing_analysis(contour: np.ndarray, t_arr: np.ndarray, floor: float):
    """Faz A — İSTASYONDAN BAĞIMSIZ kapama analizi.

    Kapama, n_axial'dan BAĞIMSIZ yoğun bir örneklemede hesaplanır (adım ≈
    floor / CLOSING_STEP_DIVISOR): inceltme turları böylece SABİT bir
    geometriye yakınsar; istasyon sayısına bağlı bir kapama her turda
    farklı dış yüzey üretirdi ve yakınsama yine tanımsız kalırdı.

    Dönüş sözlüğü: z_grid/F/H/raised/eps (kapanmış dış eğri), z_flag ve
    s_flag (tabanaltı köşe tepeleri; z dış eksende, s iç yay koordinatında)
    + ölçüm künyesi alanları.
    """
    seg = np.diff(contour, axis=0)
    L = float(np.sum(np.hypot(seg[:, 0], seg[:, 1])))
    n_dense = int(np.clip(int(np.ceil(L / (floor / CLOSING_STEP_DIVISOR))),
                          CLOSING_GRID_MIN_POINTS, CLOSING_GRID_MAX_POINTS))
    s_d, z_d, r_d, t_d = _resample_contour(contour, t_arr, n_dense)
    dz_ds = np.gradient(z_d, s_d)
    dr_ds = np.gradient(r_d, s_d)
    mag = np.hypot(dz_ds, dr_ds)
    dense_outer = np.stack([z_d - t_d * dr_ds / mag,
                            r_d + t_d * dz_ds / mag], axis=1)

    # --- z-ızgarası + üst zarf + kapama -----------------------------------
    z0 = float(np.min(dense_outer[:, 0]))
    z1 = float(np.max(dense_outer[:, 0]))
    span = z1 - z0
    if span <= 0.0:
        raise ValueError("Dış eğri z-aralığı sıfır — kapama kurulamaz.")
    n_grid = int(np.clip(
        int(np.ceil(span / (floor / CLOSING_STEP_DIVISOR))) + 1,
        CLOSING_GRID_MIN_POINTS, CLOSING_GRID_MAX_POINTS))
    dz = span / (n_grid - 1)
    z_grid = z0 + dz * np.arange(n_grid)
    F = _upper_envelope_on_grid(dense_outer, z0, dz, n_grid)
    H = _rolling_ball_closing(F, dz, floor)

    # --- Tabanaltı köşe tespiti: GEOMETRİK (kaldırma değil) ---------------
    # Sivri-ama-sığ poligon köşelerinde top-köprü kaldırması eps'in altında
    # kalabilir; köşe yine tabanın altındadır. Yoğun eğride ayrık konkav
    # çevrel yarıçapı < taban olan tepeler işaretlenir (çember üzerindeki üç
    # nokta için çevrel yarıçap TAM çember yarıçapıdır — pürüzsüz, taban
    # üstü vadiler işaretlenmez).
    Rd, kd = polyline_concave_radii(dense_outer)
    tabanalti = kd & (Rd < floor)
    siralama = np.argsort(dense_outer[1:-1][tabanalti, 0])
    z_flag = dense_outer[1:-1][tabanalti, 0][siralama]
    s_flag = np.sort(s_d[1:-1][tabanalti])

    return {
        "L": L,
        "s_d": s_d,
        "z_grid": z_grid,
        "F": F,
        "H": H,
        "raised": H - F,
        "eps": max(floor / CLOSING_LIFT_EPS_DIVISOR, 1e-12),
        "z_flag": z_flag,
        "s_flag": s_flag,
        "izgara_adimi_m": float(dz),
        "izgara_nokta": int(n_grid),
        "yogun_ornekleme_nokta": int(n_dense) + 1,
        "tabanalti_kose_tepesi": int(np.count_nonzero(tabanalti)),
    }


def _graded_station_arcs(analysis: dict, n_axial: int, floor: float):
    """Dereceli istasyon yay konumları (ters-CDF yerleşimi).

    İşaretli köşelerin ± CORNER_REFINE_WINDOW_FLOORS·floor penceresinde
    yoğunluk CORNER_REFINE_FACTOR katıdır. Ağırlık yalnız geometriye
    bağlıdır; her tur aynı dereceli koordinatı böler (modül sabitleri
    bloğundaki gerekçe). İşaretli köşe yoksa None döner (tekdüze yol).
    """
    s_flag = analysis["s_flag"]
    if not s_flag.size:
        return None
    s_d = analysis["s_d"]
    W = CORNER_REFINE_WINDOW_FLOORS * floor
    w = np.ones(s_d.size)
    j = np.searchsorted(s_flag, s_d)
    sol = np.where(j > 0, s_d - s_flag[np.maximum(j - 1, 0)], np.inf)
    sag = np.where(j < s_flag.size,
                   s_flag[np.minimum(j, s_flag.size - 1)] - s_d, np.inf)
    w[np.minimum(sol, sag) <= W] = CORNER_REFINE_FACTOR
    cdf = np.concatenate([[0.0], np.cumsum(
        0.5 * (w[1:] + w[:-1]) * np.diff(s_d))])
    hedef = np.linspace(0.0, cdf[-1], int(n_axial) + 1)
    return np.interp(hedef, cdf, s_d)


def _resample_contour_at(contour: np.ndarray, thickness: np.ndarray,
                         s_new: np.ndarray):
    """Konturu VERİLEN yay konumlarında örnekler (dereceli yol).

    Tekdüze yol ``_resample_contour``'u kullanmaya devam eder (bit-özdeşlik
    korunur); bu yardımcı yalnız dereceli istasyon dizisi içindir.
    """
    seg = np.diff(contour, axis=0)
    ds = np.hypot(seg[:, 0], seg[:, 1])
    s = np.concatenate([[0.0], np.cumsum(ds)])
    z_i = np.interp(s_new, s, contour[:, 0])
    r_i = np.interp(s_new, s, contour[:, 1])
    t_i = np.interp(s_new, s, thickness)
    return z_i, r_i, t_i


def _outer_curvature_floor_correction(analysis: dict,
                                      floor: float,
                                      s_new: np.ndarray,
                                      inner_pts: np.ndarray,
                                      outer_raw: np.ndarray):
    """Faz B — istasyonların kapanmış eğriye oturtulması.

    Dönüş: (outer_corrected, duzeltildi_maskesi, rapor_dict).
    İç yüzeye ve düzeltilmeyen istasyonlara DOKUNULMAZ (bit-özdeş kalır).
    """
    z_grid = analysis["z_grid"]
    H = analysis["H"]
    raised = analysis["raised"]
    eps = analysis["eps"]
    s_flag = analysis["s_flag"]

    # --- İstasyon kararı ---------------------------------------------------
    # (a) kapamanın gerçekten yükselttiği bölge (pürüzsüz tabanaltı vadi),
    # (b) işaretli köşenin komşuluğu (merkezî-fark normalinin köşe bulaşması
    #     her turda değişir; komşuluk kapanmış eğriye oturtularak dış
    #     geometri tur-bağımsız yapılır).
    z_st = outer_raw[:, 0]
    lift_st = np.interp(z_st, z_grid, H) - outer_raw[:, 1]
    region_st = np.interp(z_st, z_grid, raised)
    duzeltildi = (lift_st > eps) & (region_st > eps)
    if s_flag.size:
        h_loc = np.gradient(s_new)
        j = np.searchsorted(s_flag, s_new)
        sol_uzak = np.where(j > 0, s_new - s_flag[np.maximum(j - 1, 0)],
                            np.inf)
        sag_uzak = np.where(j < s_flag.size,
                            s_flag[np.minimum(j, s_flag.size - 1)] - s_new,
                            np.inf)
        w = np.minimum(CORNER_NEIGHBORHOOD_STATIONS * h_loc,
                       CORNER_NEIGHBORHOOD_MAX_FLOORS * floor)
        duzeltildi |= np.minimum(sol_uzak, sag_uzak) <= w

    outer = outer_raw.copy()
    n_st = outer_raw.shape[0]
    if np.any(duzeltildi):
        idx = np.flatnonzero(duzeltildi)
        # Bitişik koşulara böl; her koşu, iki DEĞİŞMEMİŞ komşu istasyon
        # (çapa) arasındaki kapanmış eğri parçasına, İÇ yay-uzunluğu
        # oranlarıyla yerleştirilir. Katlanmış (z'si geri dönen) ham
        # öteleme burada z-monoton kapanmış eğriyle değiştirildiği için
        # dikey-kaldırma yerine yay eşlemesi kullanılır (dikey kaldırma
        # katlanmada istasyon sırasını bozar, elemanlar ters dönerdi).
        runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
        for run in runs:
            a, b = int(run[0]), int(run[-1])
            if a == 0 or b == n_st - 1:
                # Uç istasyona dayanan koşu: uçlar düz kesitlerdir, kapama
                # oralarda özdeşliktir; yine de genel durumda dürüst kal —
                # uç istasyon kapanmış eğriye DİKEY oturtulur.
                for k in range(a, b + 1):
                    outer[k, 1] = float(np.interp(outer_raw[k, 0],
                                                  z_grid, H))
                continue
            zL, rL = outer_raw[a - 1]
            zR, rR = outer_raw[b + 1]
            if not zL < zR:
                raise ValueError(
                    "Eğrilik tabanı koşusunun çapaları z'de sıralı değil — "
                    "kontur/kalınlık geometrisi kapama varsayımıyla uyumsuz "
                    "(dış eğri z'de ilerlemiyor).")
            ic = (z_grid > zL) & (z_grid < zR)
            Cz = np.concatenate([[zL], z_grid[ic], [zR]])
            Cr = np.concatenate([[rL], H[ic], [rR]])
            sC = np.concatenate([[0.0], np.cumsum(
                np.hypot(np.diff(Cz), np.diff(Cr)))])
            frac = ((s_new[a:b + 1] - s_new[a - 1])
                    / (s_new[b + 1] - s_new[a - 1]))
            outer[a:b + 1, 0] = np.interp(frac * sC[-1], sC, Cz)
            outer[a:b + 1, 1] = np.interp(frac * sC[-1], sC, Cr)

    # --- Uygulama bölgesi beyanı: bitişik düzeltme koşularının iç-z aralığı
    bolgeler = []
    if np.any(duzeltildi):
        idx = np.flatnonzero(duzeltildi)
        for run in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1):
            bolgeler.append([float(inner_pts[int(run[0]), 0]),
                             float(inner_pts[int(run[-1]), 0])])

    rapor = {
        "eps_m": float(eps),
        "izgara_adimi_m": analysis["izgara_adimi_m"],
        "izgara_nokta": analysis["izgara_nokta"],
        "yogun_ornekleme_nokta": analysis["yogun_ornekleme_nokta"],
        "tabanalti_kose_tepesi": analysis["tabanalti_kose_tepesi"],
        "bolgeler": bolgeler,
    }
    return outer, duzeltildi, rapor


def build_wall_mesh(contour,
                    thickness: Union[float, np.ndarray],
                    n_axial: int,
                    n_radial: int = DEFAULT_ELEMS_THROUGH_WALL,
                    offset_mode: str = "normal",
                    outer_curvature_floor=OUTER_CURVATURE_FLOOR_AUTO
                    ) -> AxisymMesh:
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
    outer_curvature_floor : yalnız "normal" kipte dış yüzeye uygulanan
        eğrilik tabanı [m]. ``OUTER_CURVATURE_FLOOR_AUTO`` (varsayılan) →
        taban = max(t); pozitif sayı → o değer; 0 → taban KAPALI (kapama
        atlanır, dejenere vadi riski beyansız kalmaz — meta yine yazılır).
        Gerekçe modül docstring'i madde 2b'dedir: (a) iyi-konumluluk,
        (b) dış profil t yarıçaplı takımla işlenebilir yüzeydir. Konkav
        vadiler ``floor`` yarıçaplı yayla köprülenir; KONVEKS bölgeler ve
        iç yüzey hiçbir koşulda değişmez.

    Dönüş
    -----
    AxisymMesh — düğümler, elemanlar, yüzey kenar/düğüm kümeleri ve üretim
    beyanı (meta; taban ölçümleri ``meta['dis_yuzey_egrilik_tabani']``).
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

    if isinstance(outer_curvature_floor, str):
        if outer_curvature_floor != OUTER_CURVATURE_FLOOR_AUTO:
            raise ValueError(
                "outer_curvature_floor sayı, 0 ya da "
                f"{OUTER_CURVATURE_FLOOR_AUTO!r} olmalı.")
        floor_m = float(np.max(t_arr))
        floor_kaynagi = ("auto: max(t) — taban her istasyonda cidar "
                         "kalınlığını karşılasın diye en büyük kalınlık")
    else:
        try:
            floor_m = float(outer_curvature_floor)
        except (TypeError, ValueError):
            raise ValueError("outer_curvature_floor sayıya çevrilemedi.")
        if not np.isfinite(floor_m) or floor_m < 0.0:
            raise ValueError("outer_curvature_floor sonlu ve >= 0 olmalı.")
        floor_kaynagi = ("çağıranın verdiği açık değer"
                         if floor_m > 0.0 else
                         "0 — taban çağıran tarafından KAPATILDI")

    n_radial_requested = int(n_radial)
    n_radial = max(n_radial_requested, MIN_ELEMS_THROUGH_WALL)

    # --- Faz A: istasyondan bağımsız kapama analizi (yalnız normal kip) ---
    analiz = None
    if offset_mode == "normal" and floor_m > 0.0:
        analiz = _closing_analysis(contour, t_arr, floor_m)

    # --- İstasyon yerleşimi: işaretli köşe varsa DERECELİ, yoksa tekdüze --
    # (dereceli örnekleme gerekçesi CORNER_REFINE_* sabitlerinin başındadır;
    # tekdüze yol eski davranışla bit-özdeştir).
    s_graded = (None if analiz is None
                else _graded_station_arcs(analiz, int(n_axial), floor_m))
    if s_graded is None:
        s_new, z_i, r_i, t_i = _resample_contour(contour, t_arr,
                                                 int(n_axial))
    else:
        s_new = s_graded
        z_i, r_i, t_i = _resample_contour_at(contour, t_arr, s_new)

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

    # Düğümler: node(i, j) = iç_i + (j / n_radial) * offset_i
    frac = np.arange(n_radial + 1) / n_radial            # (n_radial+1,)
    inner_pts = np.stack([z_i, r_i], axis=1)             # (n_axial+1, 2)
    offset = t_i[:, None] * normal                        # (n_axial+1, 2)

    # --- Dış yüzey eğrilik tabanı (modül docstring'i madde 2b) ------------
    # Yalnız "normal" kipte: radyal öteleme r(z)'yi dikey kaydırır, dış
    # eğrinin eğriliğini küçültmez — dejenerasyon mekanizması orada yoktur.
    taban_bolgeleri = []
    taban_rapor = None
    duzeltildi = np.zeros(n_axial + 1, dtype=bool)
    if analiz is not None:
        outer_raw = inner_pts + offset
        outer_fixed, duzeltildi, taban_rapor = \
            _outer_curvature_floor_correction(
                analiz, floor_m, s_new, inner_pts, outer_raw)
        taban_bolgeleri = taban_rapor["bolgeler"]
        if np.any(duzeltildi):
            # Yalnız düzeltilen istasyonların öteleme vektörü değişir;
            # dokunulmayan satırlar bit-özdeş kalır (iç yüzey HER ZAMAN).
            offset[duzeltildi] = (outer_fixed[duzeltildi]
                                  - inner_pts[duzeltildi])

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

    # --- Taban beyanı: yerel kalınlaşma ve dış eğri konkav yarıçapı ÖLÇÜLÜR
    t_eff = np.hypot(offset[:, 0], offset[:, 1])
    dis_zincir = inner_pts + offset
    if dis_zincir.shape[0] >= 3:
        kr, kk = polyline_concave_radii(dis_zincir)
        konkav_r = kr[kk & np.isfinite(kr)]
    else:
        konkav_r = np.empty(0)
    taban_meta = {
        "outer_curvature_floor_m": (float(floor_m)
                                    if offset_mode == "normal" else None),
        "taban_kaynagi": (floor_kaynagi if offset_mode == "normal" else
                          "radyal kip — dikey öteleme dış eğriliği "
                          "küçültmez, taban uygulanmaz"),
        "uygulama_bolgesi_z_m": taban_bolgeleri,
        "duzeltilen_istasyon": int(np.count_nonzero(duzeltildi)),
        "kalinlik_min_m": float(np.min(t_eff)),
        "kalinlik_maks_m": float(np.max(t_eff)),
        "dis_egri_min_konkav_yaricap_m": (float(np.min(konkav_r))
                                          if konkav_r.size else None),
        "_basis": (
            "dış yüzeye yuvarlanan-top eğrilik tabanı (morfolojik kapama, "
            "top yarıçapı = taban): (a) iyi-konumluluk — normal öteleme "
            "konkav vadide dış eğriliği Rn - t'ye düşürür, Rn → t'de "
            "dejenere olur ve inceltme yakınsamaz; (b) fiziksel gerçeklik "
            "— dış profil t mertebesinde yarıçaplı takımla işlenebilir düz "
            "yüzeydir, jilet-vadi imal edilmez. Konveks bölgeler ve iç "
            "yüzey DEĞİŞMEZ; kalınlaşma ölçülür (kalinlik_min/maks_m). "
            "Kapama n_axial'dan bağımsız sabit yoğunluklu ızgarada "
            "hesaplanır; dis_egri_min_konkav_yaricap_m bu mesh'in dış "
            "zincirinden ölçülmüştür."),
    }
    if taban_rapor is not None:
        taban_meta["kapama_olcumu"] = {
            k: v for k, v in taban_rapor.items() if k != "bolgeler"}
    taban_meta["dereceli_ornekleme"] = {
        "aktif": s_graded is not None,
        "carpan": (float(CORNER_REFINE_FACTOR) if s_graded is not None
                   else None),
        "pencere_m": (float(CORNER_REFINE_WINDOW_FLOORS * floor_m)
                      if s_graded is not None else None),
        "beyan": ("işaretli tabanaltı köşelerin penceresinde istasyon "
                  "yoğunluğu artırıldı (ters-CDF; iç yüzey yine kontur "
                  "poligonunun ÜZERİNDE örneklenir, yüzey değişmez)"
                  if s_graded is not None else
                  "tekdüze yay-uzunluğu örneklemesi (işaretli köşe yok)"),
    }

    meta = {
        "_source": "hrma.fea.mesh_axisym.build_wall_mesh",
        "_basis": ("iç kontur yay uzunluğu örneklemesi + "
                   f"{offset_mode} öteleme, yapısal quad"),
        "offset_mode": offset_mode,
        "n_axial": int(n_axial),
        "n_radial_istenen": n_radial_requested,
        "n_radial_kullanilan": int(n_radial),
        "n_radial_alt_sinira_cekildi": n_radial_requested < n_radial,
        "dis_yuzey_egrilik_tabani": taban_meta,
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
