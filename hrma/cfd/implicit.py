# hrma/cfd — blok üç-köşegen (blok-Thomas) çözücü: j-yönü satır-örtük gevşetmenin çekirdeği
"""
Blok üç-köşegen doğrusal sistem çözücüsü (blok-Thomas / blok-LU eleme).

AMAÇ (tasarım belgesi docs/mimari/cfd-viskoz-tasarimi.md §4.2, §5.6)
--------------------------------------------------------------------
Duvar-çözümlü (y⁺ ≲ 1) RANS ızgarasında yerel-Δt açık sürücüsü çöker
(belgede ÖLÇÜLDÜ: iterasyon ∝ 1/Δt_min; saat mertebesi). Çare, Δt'yi
kısıtlayan j (radyal/duvar-normal) yönünü ÖRTÜK almaktır: her i-kolonu
için (I/Δt + ∂R/∂U)ΔU = R sisteminin j-yönü blok üç-köşegen parçası
çözülür. Bu modül o cebirsel çekirdektir — fizik bilmez, Jacobi kurmaz;
yalnız verilen blok üç-köşegen sistemi çözer. Örtük katman hüküm-nötrdür
(§4.2): kararlı hâl kökü kalıntı = 0 ile tanımlıdır, bu çözücü yalnız köke
gidiş yolunu hızlandırır.

ALGORİTMA (künye)
-----------------
Blok-Thomas: bloklar arası PİVOTSUZ, SABİT SIRALI ileri eleme + geri
yerine koyma (Golub & Van Loan, *Matrix Computations* 4. baskı §4.5.1
"block tridiagonal systems"; Blazek, *CFD: Principles and Applications*
3. baskı §6.2, satır-örtük şemaların standart çekirdeği):

    k = 0:      C'_0 = D_0⁻¹ U_0,          d'_0 = D_0⁻¹ b_0
    k = 1..N-1: M_k  = D_k − L_k C'_{k-1}
                C'_k = M_k⁻¹ U_k (k<N-1),  d'_k = M_k⁻¹ (b_k − L_k d'_{k-1})
    geri:       x_{N-1} = d'_{N-1};  x_k = d'_k − C'_k x_{k+1}

Blok-İÇİ çözümler ``np.linalg.solve`` (LAPACK ``gesv``, kısmi pivotlu LU)
ile yapılır: m×m bloğun KENDİ içindeki pivot LAPACK'ındır ve
deterministiktir; bloklar ARASINDA pivot yoktur (sabit k sırası). İşlem
sırası her çağrıda aynıdır (saf NumPy, tasarım belgesi §5.9 birinci
sözleşme sınıfı; numba turu sonraki iş).

BEYANLI DAVRANIŞ — tekillik ve koşullanma (sessiz NaN YOK)
----------------------------------------------------------
- Girdide sonlu olmayan değer (NaN/inf) → ``ValueError`` (giriş kapısı).
- Eleme sırasında pivot bloğu M_k LAPACK'a göre TEKİL ise →
  ``np.linalg.LinAlgError``, hangi k adımında olduğu mesajda. Sessizce
  NaN'lı alan döndürülmez.
- Kötü koşullu ama sayısal tekil OLMAYAN blokta LAPACK sonlu bir çözüm
  döndürür; burada koşul sayısı eşiği KONMAZ (uydurma tolerans yasağı).
  Blok-düzeyi pivotsuz elemenin kararlılığı çağıranın kurduğu sistemin
  blok köşegen baskınlığına dayanır — örtük sistemde I/Δt katkısı bunu
  yapısal olarak sağlar (tasarım belgesi §5.6; Golub & Van Loan §4.5.1
  aynı şartı verir). Bu bir varsayım değil sözleşmedir ve burada beyanlıdır.

BİÇİM SÖZLEŞMESİ
----------------
Öncü toplu boyutlar serbesttir (…): j-satır gevşetmesi tüm i-kolonlarını
tek çağrıda, N (=nj) üstünde sıralı ama kolonlar üstünde vektörize çözer
(tasarım belgesi §9.2 "i üstünde vektörize"). Blok boyutu m parametriktir:
eksenel simetrik ortalama akış m=4; ayrık (segregated) SA skaleri m=1
(tasarım belgesi §5.5 "ν̃ ayrık skaler üç-köşegen" — ayrı kod yolu
GEREKMEZ, aynı rutin).

ÖLÇÜLDÜ (M4 Max, 2026-08-16, saf NumPy, blok m=4, 1000 çağrı ortalaması;
rastgele iyi koşullu sistem, test merdiveniyle aynı kuruluş):
    N=24,  tek sistem      : 0,328 ms/çağrı
    N=96,  tek sistem      : 0,701 ms/çağrı
    N=24,  120 kolon toplu : 1,980 ms/çağrı  (kolon başına 0,017 ms)
    N=96,  120 kolon toplu : 8,120 ms/çağrı  (kolon başına 0,068 ms)
Yorum: toplu çağrı kolon başına maliyeti ~10-20× düşürüyor — satır-örtük
katman kolonları TOPLU çağırmalıdır. Optimizasyon (numba, yerinde eleme)
SONRAKİ tur; önce ölçüldü (mimari karar: ölç → sonra hızlandır).
"""

import numpy as np

__all__ = ['solve_block_tridiag']


def _validate_shapes(lower, diag, upper, rhs):
    """Biçim sözleşmesini denetler; (batch, N, m) döndürür."""
    if diag.ndim < 3:
        raise ValueError('diag en az 3 boyutlu olmalı: (..., N, m, m); '
                         f'gelen ndim={diag.ndim}.')
    m = diag.shape[-1]
    if diag.shape[-2] != m:
        raise ValueError('Köşegen bloklar kare olmalı: (..., N, m, m); '
                         f'gelen son iki boyut {diag.shape[-2:]}.')
    n = diag.shape[-3]
    if n < 1:
        raise ValueError('En az bir blok satır gerekli (N >= 1).')
    batch = diag.shape[:-3]
    beklenen_kenar = batch + (n - 1, m, m)
    if lower.shape != beklenen_kenar:
        raise ValueError('lower biçimi (..., N-1, m, m) olmalı: beklenen '
                         f'{beklenen_kenar}, gelen {lower.shape}.')
    if upper.shape != beklenen_kenar:
        raise ValueError('upper biçimi (..., N-1, m, m) olmalı: beklenen '
                         f'{beklenen_kenar}, gelen {upper.shape}.')
    beklenen_rhs = batch + (n, m)
    if rhs.shape != beklenen_rhs:
        raise ValueError('rhs biçimi (..., N, m) olmalı: beklenen '
                         f'{beklenen_rhs}, gelen {rhs.shape}.')
    return batch, n, m


def solve_block_tridiag(lower, diag, upper, rhs):
    """Blok üç-köşegen sistemi blok-Thomas elemesiyle çözer.

    Sistem (blok satır k = 0..N-1; L ve U kenar blokları):

        L_k · x_{k-1} + D_k · x_k + U_k · x_{k+1} = b_k

    Args:
        lower: Alt-köşegen bloklar L_1..L_{N-1}, biçim (..., N-1, m, m).
            ``lower[..., k, :, :]`` blok satır k+1'in x_k çarpanıdır.
        diag: Köşegen bloklar D_0..D_{N-1}, biçim (..., N, m, m).
        upper: Üst-köşegen bloklar U_0..U_{N-2}, biçim (..., N-1, m, m).
            ``upper[..., k, :, :]`` blok satır k'nin x_{k+1} çarpanıdır.
        rhs: Sağ taraf b_0..b_{N-1}, biçim (..., N, m).

    Öncü (...) toplu boyutlar dördünde de AYNI olmalıdır (yayınlama yok —
    sözleşme açık). N=1 desteklenir (kenar blokları boş: (..., 0, m, m)).

    Returns:
        x, biçim (..., N, m). Girdiler değiştirilmez.

    Raises:
        ValueError: Biçim sözleşmesi bozuksa ya da girdide sonlu olmayan
            değer varsa (sessiz NaN yasağının giriş kapısı).
        np.linalg.LinAlgError: Eleme sırasında pivot bloğu tekilse
            (mesajda k adımı; modül docstring'indeki beyan).
    """
    lower = np.asarray(lower, dtype=float)
    diag = np.asarray(diag, dtype=float)
    upper = np.asarray(upper, dtype=float)
    rhs = np.asarray(rhs, dtype=float)
    batch, n, m = _validate_shapes(lower, diag, upper, rhs)
    for ad, dizi in (('lower', lower), ('diag', diag),
                     ('upper', upper), ('rhs', rhs)):
        if not np.all(np.isfinite(dizi)):
            raise ValueError(f'{ad} sonlu olmayan değer içeriyor '
                             '(NaN/inf) — sessiz NaN yasağı, giriş kapısı.')

    def _blok_coz(mat, sag, k, kaci):
        """Blok-içi LAPACK çözümü; tekillikte k adımını beyan eder."""
        try:
            return np.linalg.solve(mat, sag)
        except np.linalg.LinAlgError as hata:
            raise np.linalg.LinAlgError(
                f'Blok-Thomas: k={k} adımında pivot bloğu tekil ({kaci}). '
                'Sistem blok köşegen baskın değil — örtük sistem kuruluşunu '
                'denetle (I/Δt katkısı; modül docstring beyanı).') from hata

    # İleri eleme. C'_k ve d'_k saklanır (geri adım için).
    # Faktörizasyon tasarrufu: U_k ve b_k AYNI çağrıda çözülür
    # (sağ taraf (m, m+1) olarak birleştirilir; tek LU, iki geri çözüm).
    c_prime = np.empty(batch + (max(n - 1, 0), m, m), dtype=float)
    d_prime = np.empty(batch + (n, m), dtype=float)

    pivot = diag[..., 0, :, :]
    if n > 1:
        birlesik = np.concatenate(
            [upper[..., 0, :, :], rhs[..., 0, :, None]], axis=-1)
        cozum = _blok_coz(pivot, birlesik, 0, 'ileri eleme')
        c_prime[..., 0, :, :] = cozum[..., :m]
        d_prime[..., 0, :] = cozum[..., m]
    else:
        d_prime[..., 0, :] = _blok_coz(pivot, rhs[..., 0, :], 0,
                                       'ileri eleme')

    for k in range(1, n):
        l_k = lower[..., k - 1, :, :]
        pivot = diag[..., k, :, :] - l_k @ c_prime[..., k - 1, :, :]
        sag_vek = rhs[..., k, :] - np.einsum(
            '...ij,...j->...i', l_k, d_prime[..., k - 1, :])
        if k < n - 1:
            birlesik = np.concatenate(
                [upper[..., k, :, :], sag_vek[..., None]], axis=-1)
            cozum = _blok_coz(pivot, birlesik, k, 'ileri eleme')
            c_prime[..., k, :, :] = cozum[..., :m]
            d_prime[..., k, :] = cozum[..., m]
        else:
            d_prime[..., k, :] = _blok_coz(pivot, sag_vek, k,
                                           'ileri eleme')

    # Geri yerine koyma.
    x = np.empty(batch + (n, m), dtype=float)
    x[..., n - 1, :] = d_prime[..., n - 1, :]
    for k in range(n - 2, -1, -1):
        x[..., k, :] = d_prime[..., k, :] - np.einsum(
            '...ij,...j->...i', c_prime[..., k, :, :], x[..., k + 1, :])
    return x
