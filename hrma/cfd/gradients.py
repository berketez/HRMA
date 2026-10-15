# hrma/cfd — düzlemsel Green-Gauss hücre gradyanı + düzeltmeli yüz gradyanı
"""
Viskoz katmanın gradyan operatörü (tasarım belgesi cfd-viskoz-tasarimi.md
§5.2 — BAĞLAYICI). Euler çekirdeğine DOKUNMAZ: kompozisyon ilkesi (§5.1)
gereği bu modül saf, ızgara-okur ve durum-okur bir operatördür.

DÜZLEMSEL, çünkü eksenel simetrik gerilme tensörünün (z, r) bileşenleri
düzlemsel türevlerdir; çember (hoop) bileşeni ayrı ve cebirseldir
(viscous_tensor.py). Kullanılan iki büyüklük — ``face_i_planar`` ve
``face_j_planar`` — ``AxisymGrid``'de ZATEN vardır ve Euler çözücüsünde
kullanılmaz (ÖLÇÜLDÜ: depoda tek kullanıcıları tests/cfd/test_grid.py
kapanış bekçisiydi). YENİ METRİK ÜRETİLMEZ; yüz orta noktaları ızgaranın
kendi köşe dizilerinden (Z, R) türetilir — düz kenarlı yüz için orta nokta
değeri, kenar üstündeki integral ortalamasının TAM karşılığıdır.

    ∇φ|_hücre = (1/A_düzlem) · Σ_yüz  φ_yüz · S_düzlem,yüz

SERBEST AKIM KORUNUMU BEDAVA: sabit alanda ifade φ·(Σ S)/A'ya iner ve
Σ S_düzlem = 0 özdeşliği ızgara tarafında zaten kanıtlıdır
(tests/cfd/test_grid.py::test_duzlemsel_kapanis). Bekçi bunun sayısal
yankısıdır (merdiven basamak 2).

ÇARPIKLIK DÜZELTMESİ (merdiven basamak 3'ün gereği, ÖLÇÜLDÜ): yüz değerini
komşu hücre değerlerinin salt ortalaması almak, yüz orta noktası ile hücre
merkezleri doğrusunun orta noktası ÇAKIŞMADIĞI her ızgarada doğrusal alanı
bozar. Gerçek motor konturu ızgarasında ölçülen sapma:

    ızgara (gerçek kontur)   çarpıklık (i/j)   düzeltmesiz bağıl hata
    48×10                    0,061 / 0,036     2,98e-02
    60×12                    0,070 / 0,028     5,98e-02
    30×40                    0,084 / 0,365     2,92e-01

Düzeltme, yüz değerini merkez-çifti orta noktasından yüz orta noktasına
gradyanla taşır:

    φ_yüz = ½(φ_L + φ_R) + ½(∇φ_L + ∇φ_R)·(x_yüz − ½(x_L + x_R))

Bu, gradyanın kendisine bağlı olduğundan sabit nokta süpürmeleriyle
çözülür. ÖLÇÜLEN daralma oranı: sınır değerleri verildiğinde ≈1e-2/süpürme
(DEFAULT_SKEW_TOL'e 3-12 süpürmede iner: lüle 400×4 → 3, lüle 120×24 → 4,
motor 48×10 → 7, motor 30×40 → 12), sınır değeri verilmeyip bir-yanlı
uzatma kullanıldığında ≈0,5/süpürme (39-42 süpürme; oran ızgaradan
bağımsız çıkar çünkü yavaş kipi sınır hücreleri belirler).
MAX_SKEW_ITERS bu ikinci (yavaş) kipe göre seçilmiştir; çözücü fiziksel
sınır değerlerini daima verir, hızlı yol odur.

SINIR YÜZLERİ: ``BoundaryFaceValues`` ile YÜZ ORTA NOKTASI değerleri
verilir (duvarda no-slip u=0, izotermal T_w, eksende simetri değeri,
girişte rezervuar durumu — hepsi V1'in işi). Verilmeyen sınırda bir-yanlı
DOĞRUSAL UZATMA kullanılır (φ_C + ∇φ_C·(x_yüz − x_C)); bu seçim doğrusal
alanı bozmaz (sıfırıncı mertebe uzatma bozardı: aynı ızgarada sınır
hücrelerinde ölçülen bağıl hata 4,7e-01) ve sabit alanda serbest akımı
korur.

YÜZ GRADYANI (Blazek, *CFD: Principles and Applications*, §5.3.2
"corrected average"):

    ∇φ|_yüz = avg(∇φ) − [ avg(∇φ)·t̂_LR − (φ_R − φ_L)/|LR| ] · t̂_LR

Düzeltme, yüz-normali türevini hücre-hücre KOMPAKT farka bağlar. Gerekçesi
doğrusal tamlık DEĞİLDİR (hücre gradyanları tamken salt ortalama da tamdır
— negatif kanıt bekçisi bunu kayda geçirir); gerekçe çift-tek (odd-even)
ayrışmasıdır: ÖLÇÜLDÜ, gerçek kontur 400×4 ızgarasında (−1)^i modunda
düzeltmeli biçim modu 2ε/Δz = 2,67e+03 ile görürken düzeltmesiz biçim
2,31e-01'de kalır — körlük oranı 1,15e+04.
"""

from dataclasses import dataclass

import numpy as np

__all__ = [
    'BoundaryFaceValues',
    'DEFAULT_SKEW_TOL',
    'MAX_SKEW_ITERS',
    'cell_centroids',
    'face_gradients',
    'face_midpoints',
    'green_gauss_gradient',
    'interpolate_to_faces',
    'precompute_gradient_geometry',
]

#: Çarpıklık süpürmesi durma ölçütü (bağıl güncelleme).
#: ÖLÇÜLDÜ (gerçek motor konturu 30×40, en çarpık vaka): güncelleme oranı
#: k=12'de 2,0e-13'e iner ve YUVARLAMA TABANI olan 1,1e-13'te durur —
#: bundan küçük bir ölçüt hiçbir zaman tetiklenmez ve süpürme sınırı boşa
#: yanar. Ölçüt tabanın ~10 katı seçilmiştir; o noktada ölçülen gerçek
#: gradyan hatası 2,2e-13 bağıldır (yani ölçüt ihtiyatlıdır, gevşek değil).
DEFAULT_SKEW_TOL = 1.0e-12

#: Üst sınır — yavaş (bir-yanlı uzatmalı) kipin ÖLÇÜLEN ihtiyacı 39-42
#: süpürme; pay bırakılmıştır. Sınır değeri verilen kipte 3-12 yeter.
MAX_SKEW_ITERS = 64


@dataclass(frozen=True)
class BoundaryFaceValues:
    """Sınır yüzlerinde φ'nin YÜZ ORTA NOKTASI değerleri (None → uzatma).

    i_lo : (nj,)  giriş yüzü sütunu  (i = 0)
    i_hi : (nj,)  çıkış yüzü sütunu  (i = ni)
    j_lo : (ni,)  eksen yüzü sırası  (j = 0, r = 0)
    j_hi : (ni,)  duvar yüzü sırası  (j = nj)
    """
    i_lo: np.ndarray = None
    i_hi: np.ndarray = None
    j_lo: np.ndarray = None
    j_hi: np.ndarray = None


def face_midpoints(grid):
    """Yüz orta noktaları ((ni+1, nj, 2), (ni, nj+1, 2)) — köşe gerçeğinden.

    Düz kenarlı yüzde ∫φ dl = φ(orta nokta)·L (doğrusal φ için TAM);
    Green-Gauss'un tamlığı bu noktada değerlendirmeyi ister.
    """
    mid_i = np.stack([0.5 * (grid.Z[:, :-1] + grid.Z[:, 1:]),
                      0.5 * (grid.R[:, :-1] + grid.R[:, 1:])], axis=-1)
    mid_j = np.stack([0.5 * (grid.Z[:-1, :] + grid.Z[1:, :]),
                      0.5 * (grid.R[:-1, :] + grid.R[1:, :])], axis=-1)
    return mid_i, mid_j


def cell_centroids(grid):
    """Hücre düzlemsel ağırlık merkezleri (ni, nj, 2) = (z, r).

    Hücre değeri φ_c, doğrusal alanda ağırlık merkezindeki değere EŞİTTİR
    (hücre ortalaması = ağırlık merkezi değeri); Green-Gauss'un doğrusal
    tamlığı bu eşitliğe dayanır.
    """
    return np.stack([grid.z_centers, grid.r_centers], axis=-1)


def precompute_gradient_geometry(grid):
    """Izgara SABİTİ gradyan geometrisi — bir kez hesaplanıp taşınır.

    (euler_core.precompute_geometry kalıbının kardeşi: sürücü bir kez
    hesaplar, her çağrıda yeniden kurulmaz.)
    """
    xc = cell_centroids(grid)
    mid_i, mid_j = face_midpoints(grid)

    d_i = xc[1:] - xc[:-1]                       # (ni-1, nj, 2)
    len_i = np.linalg.norm(d_i, axis=-1)
    d_j = xc[:, 1:] - xc[:, :-1]                 # (ni, nj-1, 2)
    len_j = np.linalg.norm(d_j, axis=-1)

    skew_i = mid_i[1:-1] - 0.5 * (xc[:-1] + xc[1:])
    skew_j = mid_j[:, 1:-1] - 0.5 * (xc[:, :-1] + xc[:, 1:])

    b_i_lo = mid_i[0] - xc[0]                    # (nj, 2) — merkez → yüz
    b_i_hi = mid_i[-1] - xc[-1]
    b_j_lo = mid_j[:, 0] - xc[:, 0]              # (ni, 2)
    b_j_hi = mid_j[:, -1] - xc[:, -1]

    def _unit(vec):
        length = np.linalg.norm(vec, axis=-1)
        return vec / length[..., None], length

    t_i, _ = _unit(d_i)
    t_j, _ = _unit(d_j)
    bt_i_lo, bl_i_lo = _unit(b_i_lo)
    bt_i_hi, bl_i_hi = _unit(b_i_hi)
    bt_j_lo, bl_j_lo = _unit(b_j_lo)
    bt_j_hi, bl_j_hi = _unit(b_j_hi)

    s_i = grid.face_i_planar
    s_j = grid.face_j_planar
    cevre = (np.linalg.norm(s_i[1:], axis=-1) + np.linalg.norm(s_i[:-1], axis=-1)
             + np.linalg.norm(s_j[:, 1:], axis=-1)
             + np.linalg.norm(s_j[:, :-1], axis=-1))

    return {
        'xc': xc, 'mid_i': mid_i, 'mid_j': mid_j,
        'skew_i': skew_i, 'skew_j': skew_j,
        't_i': t_i, 'len_i': len_i, 't_j': t_j, 'len_j': len_j,
        'bt_i_lo': bt_i_lo, 'bl_i_lo': bl_i_lo,
        'bt_i_hi': bt_i_hi, 'bl_i_hi': bl_i_hi,
        'bt_j_lo': bt_j_lo, 'bl_j_lo': bl_j_lo,
        'bt_j_hi': bt_j_hi, 'bl_j_hi': bl_j_hi,
        'b_i_lo': b_i_lo, 'b_i_hi': b_i_hi,
        'b_j_lo': b_j_lo, 'b_j_hi': b_j_hi,
        'inv_area': 1.0 / grid.area_planar,
        # gradyan gürültü tabanı ölçeği [1/m]: Σ|S| / A
        'grad_floor_scale': float(np.max(cevre / grid.area_planar)),
    }


def _check_field(grid, phi, ad='phi'):
    phi = np.asarray(phi, dtype=float)
    if phi.shape != (grid.ni, grid.nj):
        raise ValueError(
            f'{ad} biçimi ({grid.ni}, {grid.nj}) olmalı, gelen {phi.shape}.')
    # SONLULUK KAPISI (ÖH defter P6B2-07): biçim denetleniyordu, sonluluk
    # denetlenmiyordu — ölçüldü (D23 once.json K9), NaN taşıyan bir alan
    # sessizce geçip NaN gradyan üretiyordu ve hata ancak çok sonra, başka
    # bir modülde görünüyordu. Gradyan operatörünün girdisi ÇAĞIRANIN
    # verisidir; kusurlu girdi ADIYLA reddedilir (kırpma/yedek yok).
    if not np.all(np.isfinite(phi)):
        raise ValueError(
            f'{ad} her hücrede sonlu olmalı — '
            f'{int(np.count_nonzero(~np.isfinite(phi)))} hücrede NaN/inf '
            'var. Green-Gauss operatörü sonlu olmayan alanı sessizce '
            'taşımaz; girdi kusuru burada ADIYLA reddedilir.')
    return phi


def _check_bc(grid, bc):
    if bc is None:
        return BoundaryFaceValues()
    if not isinstance(bc, BoundaryFaceValues):
        raise ValueError('bc BoundaryFaceValues olmalı (sınır YÜZ değerleri).')
    beklenen = {'i_lo': grid.nj, 'i_hi': grid.nj,
                'j_lo': grid.ni, 'j_hi': grid.ni}
    for ad, n in beklenen.items():
        deger = getattr(bc, ad)
        if deger is None:
            continue
        dizi = np.asarray(deger, dtype=float)
        if dizi.shape != (n,):
            raise ValueError(
                f'bc.{ad} biçimi ({n},) olmalı, gelen {dizi.shape}.')
        # Sınır YÜZ değerleri de sonlu olmalı (ÖH defter P6B2-07): NaN bir
        # sınır değeri bütün alana yayılırdı ve iz bırakmazdı.
        if not np.all(np.isfinite(dizi)):
            raise ValueError(
                f'bc.{ad} sonlu olmalı — '
                f'{int(np.count_nonzero(~np.isfinite(dizi)))} yüzde NaN/inf '
                'var. Sınır yüz değeri ÇAĞIRANIN verisidir; sonlu olmayan '
                'sınır değeri gradyanı sessizce kirletirdi.')
    return bc


def interpolate_to_faces(grid, phi, grad, bc=None, geom=None):
    """Hücre değerlerini yüzlere taşır (çarpıklık düzeltmeli).

    Args:
        grid: AxisymGrid.
        phi: (ni, nj) hücre değerleri (ağırlık merkezinde).
        grad: (ni, nj, 2) hücre gradyanları — düzeltme terimi bunu kullanır
            (sıfır verilirse salt ortalama elde edilir).
        bc: BoundaryFaceValues veya None (None → bir-yanlı doğrusal uzatma).
        geom: precompute_gradient_geometry çıktısı veya None.

    Returns:
        (phi_i, phi_j): (ni+1, nj) ve (ni, nj+1) yüz değerleri.
    """
    phi = _check_field(grid, phi)
    grad = np.asarray(grad, dtype=float)
    if grad.shape != (grid.ni, grid.nj, 2):
        raise ValueError(
            f'grad biçimi ({grid.ni}, {grid.nj}, 2) olmalı, '
            f'gelen {grad.shape}.')
    bc = _check_bc(grid, bc)
    if geom is None:
        geom = precompute_gradient_geometry(grid)

    phi_i = np.empty((grid.ni + 1, grid.nj), dtype=float)
    phi_j = np.empty((grid.ni, grid.nj + 1), dtype=float)

    phi_i[1:-1] = (0.5 * (phi[:-1] + phi[1:])
                   + np.sum(0.5 * (grad[:-1] + grad[1:]) * geom['skew_i'],
                            axis=-1))
    phi_j[:, 1:-1] = (0.5 * (phi[:, :-1] + phi[:, 1:])
                      + np.sum(0.5 * (grad[:, :-1] + grad[:, 1:])
                               * geom['skew_j'], axis=-1))

    phi_i[0] = (np.asarray(bc.i_lo, dtype=float) if bc.i_lo is not None
                else phi[0] + np.sum(grad[0] * geom['b_i_lo'], axis=-1))
    phi_i[-1] = (np.asarray(bc.i_hi, dtype=float) if bc.i_hi is not None
                 else phi[-1] + np.sum(grad[-1] * geom['b_i_hi'], axis=-1))
    phi_j[:, 0] = (np.asarray(bc.j_lo, dtype=float) if bc.j_lo is not None
                   else phi[:, 0] + np.sum(grad[:, 0] * geom['b_j_lo'],
                                           axis=-1))
    phi_j[:, -1] = (np.asarray(bc.j_hi, dtype=float) if bc.j_hi is not None
                    else phi[:, -1] + np.sum(grad[:, -1] * geom['b_j_hi'],
                                             axis=-1))
    return phi_i, phi_j


def _green_gauss_sweep(grid, phi_i, phi_j, geom):
    """Bir Green-Gauss süpürmesi: (1/A) Σ_dışa φ_yüz · S_düzlem."""
    s_i = grid.face_i_planar
    s_j = grid.face_j_planar
    net = (phi_i[1:, :, None] * s_i[1:] - phi_i[:-1, :, None] * s_i[:-1]
           + phi_j[:, 1:, None] * s_j[:, 1:]
           - phi_j[:, :-1, None] * s_j[:, :-1])
    return net * geom['inv_area'][..., None]


def green_gauss_gradient(grid, phi, bc=None, skew_iters=None,
                         tol=DEFAULT_SKEW_TOL, geom=None, return_info=False):
    """Düzlemsel Green-Gauss hücre gradyanı (çarpıklık düzeltmeli).

    Args:
        grid: AxisymGrid.
        phi: (ni, nj) hücre değerleri.
        bc: BoundaryFaceValues veya None (uzatma kipi).
        skew_iters: None → yakınsayana dek (en çok MAX_SKEW_ITERS) süpür;
            tamsayı → tam olarak o kadar DÜZELTME süpürmesi (0 = düzeltmesiz
            klasik Green-Gauss; bekçi/mutasyon karşılaştırması için).
        tol: bağıl güncelleme durma ölçütü (adaptif kipte).
        geom: precompute_gradient_geometry çıktısı veya None.
        return_info: True → (grad, info) döndürür. info: kullanılan süpürme
            sayısı, son bağıl güncelleme, yakınsama hükmü, sınır kipi.

    Returns:
        (ni, nj, 2) gradyan; [..., 0] = ∂φ/∂z, [..., 1] = ∂φ/∂r.
        Bileşen sırası yüzey vektörleriyle (S_z, S_r) aynıdır.
    """
    phi = _check_field(grid, phi)
    bc = _check_bc(grid, bc)
    if geom is None:
        geom = precompute_gradient_geometry(grid)

    adaptif = skew_iters is None
    if adaptif:
        limit = MAX_SKEW_ITERS
    else:
        limit = int(skew_iters)
        if limit < 0:
            raise ValueError('skew_iters negatif olamaz (0 = düzeltmesiz).')

    # Gürültü tabanı: sabit alanda gradyan tam sıfır değil, Σ S kapanışının
    # yuvarlama artığı kadardır. Bağıl ölçüt bu tabana bölünmeli, yoksa
    # düzgün alanda "hiç yakınsamayan" bir ölçüt doğar.
    taban = (np.finfo(float).eps * float(np.max(np.abs(phi)))
             * geom['grad_floor_scale'])

    grad = np.zeros((grid.ni, grid.nj, 2), dtype=float)
    kullanilan = 0
    son_bagil = float('inf')
    for k in range(limit + 1):
        phi_i, phi_j = interpolate_to_faces(grid, phi, grad, bc=bc, geom=geom)
        yeni = _green_gauss_sweep(grid, phi_i, phi_j, geom)
        guncelleme = float(np.max(np.abs(yeni - grad)))
        olcek = max(float(np.max(np.abs(yeni))), taban)
        son_bagil = guncelleme / olcek if olcek > 0.0 else 0.0
        grad = yeni
        kullanilan = k
        if adaptif and k >= 1 and son_bagil <= tol:
            break

    if not return_info:
        return grad
    if bc.i_lo is bc.i_hi is bc.j_lo is bc.j_hi is None:
        sinir_kipi = 'extrapolated'
    elif all(getattr(bc, ad) is not None
             for ad in ('i_lo', 'i_hi', 'j_lo', 'j_hi')):
        sinir_kipi = 'dirichlet'
    else:
        sinir_kipi = 'mixed'
    info = {
        '_source': 'hrma.cfd.gradients.green_gauss_gradient',
        'skew_iters_used': kullanilan,
        'skew_iters_limit': limit,
        'adaptive': adaptif,
        'last_update_rel': son_bagil,
        'converged': bool(son_bagil <= tol),
        'boundary_mode': sinir_kipi,
    }
    return grad, info


def face_gradients(grid, phi, grad=None, bc=None, corrected=True, geom=None,
                   skew_iters=None):
    """Yüz gradyanları — Blazek §5.3.2 düzeltmeli ortalama.

    Args:
        grid, phi, bc, geom: green_gauss_gradient ile aynı.
        grad: (ni, nj, 2) hücre gradyanları; None → burada hesaplanır.
        corrected: False → salt ortalama (DÜZELTMESİZ; yalnız karşılaştırma
            ve bekçi için — çift-tek ayrışmasına açıktır, üretim yolu
            değildir).
        skew_iters: grad=None ise hücre gradyanına aktarılır.

    Returns:
        (grad_i, grad_j): (ni+1, nj, 2) ve (ni, nj+1, 2).
        Sınır yüzlerinde tek yanlı: komşu hücre gradyanı, düzeltmeli kipte
        merkez→yüz doğrultusundaki bileşeni sınır değerinden gelen kompakt
        farkla değiştirilmiş hâlde.
    """
    phi = _check_field(grid, phi)
    bc = _check_bc(grid, bc)
    if geom is None:
        geom = precompute_gradient_geometry(grid)
    if grad is None:
        grad = green_gauss_gradient(grid, phi, bc=bc, geom=geom,
                                    skew_iters=skew_iters)
    grad = np.asarray(grad, dtype=float)
    if grad.shape != (grid.ni, grid.nj, 2):
        raise ValueError(
            f'grad biçimi ({grid.ni}, {grid.nj}, 2) olmalı, '
            f'gelen {grad.shape}.')

    grad_i = np.empty((grid.ni + 1, grid.nj, 2), dtype=float)
    grad_i[1:-1] = 0.5 * (grad[:-1] + grad[1:])
    grad_i[0] = grad[0]
    grad_i[-1] = grad[-1]

    grad_j = np.empty((grid.ni, grid.nj + 1, 2), dtype=float)
    grad_j[:, 1:-1] = 0.5 * (grad[:, :-1] + grad[:, 1:])
    grad_j[:, 0] = grad[:, 0]
    grad_j[:, -1] = grad[:, -1]

    if not corrected:
        return grad_i, grad_j

    # --- iç yüzler: t̂ bileşenini KOMPAKT farkla değiştir ---
    t_i, len_i = geom['t_i'], geom['len_i']
    fark = (np.sum(grad_i[1:-1] * t_i, axis=-1)
            - (phi[1:] - phi[:-1]) / len_i)
    grad_i[1:-1] -= fark[..., None] * t_i

    t_j, len_j = geom['t_j'], geom['len_j']
    fark = (np.sum(grad_j[:, 1:-1] * t_j, axis=-1)
            - (phi[:, 1:] - phi[:, :-1]) / len_j)
    grad_j[:, 1:-1] -= fark[..., None] * t_j

    # --- sınır yüzleri: merkez → yüz doğrultusunda tek yanlı kompakt fark ---
    phi_i, phi_j = interpolate_to_faces(grid, phi, grad, bc=bc, geom=geom)
    for dilim, t_hat, uzunluk, yuz_deger, hucre_deger in (
            (grad_i[0], geom['bt_i_lo'], geom['bl_i_lo'], phi_i[0], phi[0]),
            (grad_i[-1], geom['bt_i_hi'], geom['bl_i_hi'], phi_i[-1], phi[-1]),
            (grad_j[:, 0], geom['bt_j_lo'], geom['bl_j_lo'],
             phi_j[:, 0], phi[:, 0]),
            (grad_j[:, -1], geom['bt_j_hi'], geom['bl_j_hi'],
             phi_j[:, -1], phi[:, -1])):
        fark = (np.sum(dilim * t_hat, axis=-1)
                - (yuz_deger - hucre_deger) / uzunluk)
        dilim -= fark[..., None] * t_hat

    return grad_i, grad_j
