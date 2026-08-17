# hrma/cfd — j-yönü satır-örtük gevşetme KATMANI (fizik ↔ blok-Thomas köprüsü)
"""
j-yönü (radyal) satır-örtük gevşetme: her i-kolonu için blok üç-köşegen
örtük sistemi kurar ve ``implicit.solve_block_tridiag`` ile TOPLU çözer.

YER (tasarım belgesi docs/mimari/cfd-viskoz-tasarimi.md §4.2, §5.6)
-------------------------------------------------------------------
Duvar-çözümlü RANS ızgarasında yerel-Δt açık sürücüsü çöker (belgede
ÖLÇÜLDÜ: iterasyon ∝ 1/Δt_min). Çare, Δt'yi kısıtlayan j yönünü ÖRTÜK
almaktır. Belgenin dosya düzeni (§11.1) bu işi ``implicit.py`` başlığında
toplar; cebir çekirdeği (blok-Thomas) orada AYRI ve dondurulmuş olduğundan
fizik katmanı bu dosyadadır — cebir fizik bilmez, bu katman cebire yalnız
kurulmuş sistemi verir (kompozisyon ilkesi, belge §5.1'in örtük karşılığı).

HÜKÜM-NÖTRLÜK SÖZLEŞMESİ (belge §4.2 — kırmızı çizgi)
-----------------------------------------------------
Kararlı hâl kökü kalıntı = 0 denklemiyle tanımlıdır. Bu katman köke GİDİŞ
YOLUNU değiştirir, KÖKÜ DEĞİŞTİRMEZ: yakınsamada ΔU → 0 olduğundan sol
taraftaki yaklaşık Jacobian çözümde İZ BIRAKMAZ. Bekçisi ölçülüdür
(tests/cfd/test_satir_ortuk.py: açık ve örtük yolun yakınsadığı alanlar
alan-alan karşılaştırılır; bant ölçümden kilitlidir).

SEÇİLEN JACOBIAN BİÇİMİ (belge §5.6: "taşınım kısmı spektral yarıçap
tabanlı yaklaşık — basit, sağlam"; kesin biçim belgede açık bırakıldı,
burada künyeyle seçildi ve beyanlıdır)
--------------------------------------------------------------------
Yüz akısının birinci-mertebe yukarı-akış doğrusallaştırması, spektral
yarıçap sınırlı bölme (split) ile:

    A± = ½ (A ± λ I),   λ = max(|u_L·n̂| + a_L, |u_R·n̂| + a_R)

    ∂F_yüz/∂U_L ≈ A⁺(U_L)·|S|,   ∂F_yüz/∂U_R ≈ A⁻(U_R)·|S|

(A: analitik taşınım akı Jacobian'ı, aşağıda ``convective_jacobian``;
künye: Jameson & Yoon, AIAA J. 25(7), 1987, DOI 10.2514/3.9724 — LU-SGS'in
spektral yarıçap yaklaşık Jacobian'ı; Blazek, *CFD: Principles and
Applications* 3. baskı §6.2'de satır/nokta-örtük şemaların standart
kuruluşu.) Gerçek akı HLLC olduğundan bu doğrusallaştırma YAKLAŞIKTIR —
hüküm-nötrlük sözleşmesi gereği bu serbestlik meşrudur (yalnız yol değişir).

Örtük sistem (kolon i, bilinmeyen ΔU_j, j = 0..nj−1):

    [V/Δt + D_i + D_duvar] I  +  Σ_iç-j-yüzleri (± A±·|S|)  →  M·ΔU = V·R

    satır j köşegeni : V_j/Δt_j·I + A⁺(U_j)|S|_üst − A⁻(U_j)|S|_alt + D·I
    üst bağlaşım     : +A⁻(U_{j+1})·|S|_üst   (ΔU_{j+1} katsayısı)
    alt bağlaşım     : −A⁺(U_{j−1})·|S|_alt   (ΔU_{j−1} katsayısı)

- İç j-yüzleri: TAM 4×4 blok bağlaşım (yukarıdaki A± ile).
- i-yüzleri: bağlaşım blokları ATILIR (sistem beş-köşegen olmasın diye),
  köşegene yalnız sönüm payı ½(λ|S|)_alt + ½(λ|S|)_üst eklenir — yönler
  arası gevşetme deseni (künye: Wright, Candler & Bose, "Data-Parallel
  Line Relaxation Method for the Navier-Stokes Equations", AIAA J. 36(9),
  1998, DOI 10.2514/2.586: çizgi-dışı terimlerin gevşetilmesi). λ hücrenin
  KENDİ durumuyla yüzlere atanır (local_dt_axisym ile aynı kural).
- Duvar j-yüzü: akı analitik [0, p*·n̂|S|, 0] (euler_core beyanı); tam
  doğrusallaştırma yerine spektral yarıçap sönümü ½λ|S| köşegene eklenir
  (yalnız sönüm katar — hüküm-nötr, beyanlı yaklaşıklık).
- Eksen j-yüzü: alanı geometrik olarak SIFIR (grid_axisym: r_orta = 0) —
  katkısı yok, terim kurulmaz.

Köşegen baskınlık: A⁺ özdeğerleri ≥ 0, −A⁻ özdeğerleri ≥ 0 ve V/Δt > 0
olduğundan blok köşegen yapısal olarak baskındır — implicit.py'nin
pivotsuz blok-Thomas sözleşmesinin şartı burada kurulumla sağlanır.

Δt → ∞ limiti: V/Δt → 0, sistem yaklaşık-Jacobian Newton adımına yaklaşır
(iterasyon sayısı düşer; ölçüm testte). Jacobian yaklaşık olduğundan tam
Newton kuadratik yakınsaması İDDİA EDİLMEZ.

TOPLU ÇAĞRI SÖZLEŞMESİ: tüm i-kolonları solve_block_tridiag'a TEK çağrıda
verilir (implicit.py ÖLÇÜMÜ: kolon başına ~10-20× ucuz). Kolon-kolon
döngü YASAK değil ama ölçülen israftır (mutasyon kanıtı testte).

numba YOK (bu parti): saf NumPy — belgenin ölç-sonra-hızlandır ilkesi
(§5.9); süreler V0 raporunda ölçüldü.
"""

import numpy as np

from hrma.cfd.euler_core import cons_to_prim_axisym
from hrma.cfd.implicit import solve_block_tridiag

__all__ = ['convective_jacobian', 'line_implicit_delta', 'local_dt_axial']

_EYE4 = np.eye(4)


def local_dt_axial(U, grid, gamma, cfl, area_i):
    """Yerel Δt — YALNIZ i (eksenel) yüz spektral yarıçapından.

    Satır-örtük yolda Δt'yi j yönü SINIRLAMAZ (o yön örtük); zaman adımı
    açık bırakılan yönden alınır: Δt_c = CFL·V_c / Σ_{i-yüzleri}(|u·n̂|+a)|S|
    (tasarım belgesi §4.2 "Δt artık yalnız eksenel yönle sınırlıdır"
    cümlesinin formülü; Blazek 3. baskı §6.2 satır-örtük şemalarda zaman
    adımının açık yönlerden kısıtlanması). Yüz hızı kuralı
    euler_core.local_dt_axisym ile AYNIDIR (hücre değerleri yüzlere
    atanır); tek fark j-yüz toplamının dışarıda bırakılmasıdır.

    ÖLÇÜLEN GEREKÇE (V0 turu, 2026-08-17): tam spektral toplam + büyük
    CFL, nj büyüdükçe i-yönü AÇIK kısmına taşınamaz adım verdi — 60×48 ve
    60×96'da ~300 iterasyonda ıraksama (1. mertebede bile). i-yalnız Δt
    ile aynı merdiven tablosu test_satir_ortuk.py docstring'indedir.
    """
    g = float(gamma)
    w = cons_to_prim_axisym(U, g)
    a = np.sqrt(g * w[..., 3] / w[..., 0])
    uz = w[..., 1]
    ur = w[..., 2]
    face_i = grid.face_i
    spd_dn = (np.abs(uz * face_i[:-1, ..., 0] + ur * face_i[:-1, ..., 1])
              + a * area_i[:-1])
    spd_up = (np.abs(uz * face_i[1:, ..., 0] + ur * face_i[1:, ..., 1])
              + a * area_i[1:])
    return cfl * grid.volume / (spd_dn + spd_up)


def convective_jacobian(w, n_hat, gamma):
    """Analitik taşınım akı Jacobian'ı A = ∂(F·n̂)/∂U, (..., 4, 4).

    Durum vektörü U = [ρ, ρu_z, ρu_r, E], akı normal bileşeni
    F·n̂ = [ρV_n, ρu_z V_n + p n_z, ρu_r V_n + p n_r, (E+p)V_n],
    V_n = u·n̂. Standart kapalı form (Blazek, 3. baskı, Ek A — 2B Euler
    taşınım Jacobian'ı; kalorik mükemmel gaz).

    Args:
        w: (..., 4) PRİMİTİF durum [ρ, u_z, u_r, p] (cons_to_prim çıktısı).
        n_hat: (..., 2) birim normal (z, r bileşenleri).
        gamma: kalorik mükemmel gaz oranı.

    Returns:
        (..., 4, 4) Jacobian. Doğruluk bekçileri (test_satir_ortuk):
        Euler akısının 1. derece homojenliği A·U = F·n̂ (kapalı özdeşlik)
        + merkezi sonlu-fark çaprazı.
    """
    g = float(gamma)
    g1 = g - 1.0
    rho = w[..., 0]
    uz = w[..., 1]
    ur = w[..., 2]
    p = w[..., 3]
    nz = n_hat[..., 0]
    nr = n_hat[..., 1]
    vn = uz * nz + ur * nr
    ke = 0.5 * (uz * uz + ur * ur)
    phi = g1 * ke
    # Toplam entalpi H = (E+p)/ρ = γp/((γ−1)ρ) + ke (kalorik mükemmel)
    H = g / g1 * p / rho + ke
    A = np.empty(w.shape[:-1] + (4, 4))
    A[..., 0, 0] = 0.0
    A[..., 0, 1] = nz
    A[..., 0, 2] = nr
    A[..., 0, 3] = 0.0
    A[..., 1, 0] = phi * nz - uz * vn
    A[..., 1, 1] = vn + (2.0 - g) * uz * nz
    A[..., 1, 2] = uz * nr - g1 * ur * nz
    A[..., 1, 3] = g1 * nz
    A[..., 2, 0] = phi * nr - ur * vn
    A[..., 2, 1] = ur * nz - g1 * uz * nr
    A[..., 2, 2] = vn + (2.0 - g) * ur * nr
    A[..., 2, 3] = g1 * nr
    A[..., 3, 0] = (phi - H) * vn
    A[..., 3, 1] = H * nz - g1 * uz * vn
    A[..., 3, 2] = H * nr - g1 * ur * vn
    A[..., 3, 3] = g * vn
    return A


def line_implicit_delta(U, dudt, grid, geom, gamma, dt):
    """Satır-örtük güncelleme adımı ΔU'yu döndürür (U'yu DEĞİŞTİRMEZ).

    Sistem (modül docstring'indeki kuruluş):

        M · ΔU = V · dudt        (kolon başına blok üç-köşegen, i toplu)

    Args:
        U: (ni, nj, 4) korunum durumu.
        dudt: residual_axisym çıktısı (ni, nj, 4) [birim/s] — kalıntı
            fonksiyonu SAF kalır (kompozisyon ilkesi: durum sokulmaz,
            burada yalnız TÜKETİLİR).
        grid: AxisymGrid.
        geom: euler_core.precompute_geometry(grid) çıktısı (sürücü bir
            kez hesaplar; ikinci kez hesaplanmaz).
        gamma: gaz oranı (çağırandan; varsayılan yok).
        dt: (ni, nj) yerel zaman adımı (local_dt_axisym; örtük yolda CFL
            açık sınırın üstüne çıkabilir — ölçülen tavan steady.py'de).

    Returns:
        ΔU, (ni, nj, 4). U + ΔU çağıranın işidir.

    Raises:
        np.linalg.LinAlgError / ValueError: implicit.py giriş kapısı ve
        tekillik beyanları aynen geçer (sessiz NaN yok). Fiziksel duruma
        sahip (ρ>0, p>0) sonlu alanda blok köşegen kurulum gereği
        baskındır; tekillik ancak bozuk durumla mümkündür ve sürücünün
        kalıntı-NaN kapısı ondan önce yakalar (steady.py).
    """
    g = float(gamma)
    w = cons_to_prim_axisym(U, g)
    ni, nj = grid.ni, grid.nj
    a = np.sqrt(g * w[..., 3] / w[..., 0])
    uz = w[..., 1]
    ur = w[..., 2]
    vol = grid.volume

    # --- i-yüzleri: skaler spektral sönüm (hücre durumu yüzlere atanır —
    # local_dt_axisym ile aynı kural; bağlaşım blokları gevşetme deseni
    # gereği atılır, docstring künyesi) ---
    face_i = grid.face_i
    area_i = geom['area_i']
    lam_i_dn = (np.abs(uz * face_i[:-1, ..., 0] + ur * face_i[:-1, ..., 1])
                + a * area_i[:-1])
    lam_i_up = (np.abs(uz * face_i[1:, ..., 0] + ur * face_i[1:, ..., 1])
                + a * area_i[1:])
    diag_scalar = vol / dt + 0.5 * (lam_i_dn + lam_i_up)

    # --- duvar j-yüzü: spektral sönüm payı (beyanlı yaklaşıklık) ---
    wall_n = geom['wall_n_hat']                       # (ni, 2)
    s_wall = geom['area_j'][:, -1]                    # (ni,)
    lam_wall = (np.abs(uz[:, -1] * wall_n[..., 0]
                       + ur[:, -1] * wall_n[..., 1])
                + a[:, -1]) * s_wall
    diag_scalar[:, -1] += 0.5 * lam_wall
    # Eksen j-yüzü (j=0 altı): alan geometrik SIFIR — terim yok.

    # --- iç j-yüzleri: tam 4×4 blok bağlaşım (A± spektral bölme) ---
    n_f = geom['n_hat_j'][:, 1:-1]                    # (ni, nj-1, 2)
    s_f = geom['area_j'][:, 1:-1]                     # (ni, nj-1)
    w_lo = w[:, :-1]                                  # alt hücre (L)
    w_hi = w[:, 1:]                                   # üst hücre (R)
    vn_lo = w_lo[..., 1] * n_f[..., 0] + w_lo[..., 2] * n_f[..., 1]
    vn_hi = w_hi[..., 1] * n_f[..., 0] + w_hi[..., 2] * n_f[..., 1]
    lam_f = np.maximum(np.abs(vn_lo) + a[:, :-1],
                       np.abs(vn_hi) + a[:, 1:])      # (ni, nj-1)
    a_lo = convective_jacobian(w_lo, n_f, g)
    a_hi = convective_jacobian(w_hi, n_f, g)
    lam_eye = lam_f[..., None, None] * _EYE4
    s_face = s_f[..., None, None]
    a_plus = 0.5 * (a_lo + lam_eye) * s_face          # A⁺(U_j)·|S|
    a_minus = 0.5 * (a_hi - lam_eye) * s_face         # A⁻(U_{j+1})·|S|

    diag = diag_scalar[..., None, None] * _EYE4       # (ni, nj, 4, 4)
    diag[:, :-1] += a_plus
    diag[:, 1:] -= a_minus

    # --- eksenel simetri kaynak teriminin NOKTA-ÖRTÜK Jacobian'ı ---
    # euler_core kaynak terimi: net[..., 2] += p·2π·A_düzlem. j-akıları
    # örtükleşince bu terim tek başına AÇIK kalırsa eksen yakınında
    # kaynak/V = p/r̄ oranı nj ile büyür (S_j ∝ r küçülür, A_düzlem
    # küçülmez) ve adımı taşıyamaz — ÖLÇÜLDÜ (V0 turu: i-yalnız Δt'yle
    # bile 60×48/96 ~150-300 iterasyonda ıraksadı; nj=12 yeşil — 1/r̄
    # sertlik deseni). Standart tedavi kaynak Jacobian'ının köşegene
    # alınmasıdır (Blazek 3. baskı §6.2, kaynak terimlerinin nokta-örtük
    # işlenişi): M[2,:] −= 2πA·∂p/∂U, ∂p/∂U = (γ−1)·[ke, −u_z, −u_r, 1].
    g1 = g - 1.0
    src = (2.0 * np.pi) * grid.area_planar * g1       # (ni, nj)
    ke = 0.5 * (uz * uz + ur * ur)
    diag[..., 2, 0] -= src * ke
    diag[..., 2, 1] += src * uz
    diag[..., 2, 2] += src * ur
    diag[..., 2, 3] -= src

    upper = a_minus                                   # satır j: ΔU_{j+1}
    lower = -a_plus                                   # satır j+1: ΔU_j
    rhs = vol[..., None] * dudt

    return solve_block_tridiag(lower, diag, upper, rhs)
