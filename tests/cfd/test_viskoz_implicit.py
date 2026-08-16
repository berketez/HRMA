# tests/cfd — blok üç-köşegen (blok-Thomas) çözücü bekçileri (viskoz kulvar, V1 hazırlığı)
"""
``hrma.cfd.implicit.solve_block_tridiag`` doğrulama merdiveni.

Tasarım belgesi (docs/mimari/cfd-viskoz-tasarimi.md §5.6): "Blok-Thomas'ın
kendi bekçisi cebirseldir: rastgele blok üç-köşegen sistem kurulur, çözücü
np.linalg.solve ile karşılaştırılır (makine hassasiyeti). Bu bekçi fizikten
bağımsızdır ve asla 'kusuru koruyan' bir teste dönüşemez." Merdiven:

(a) Rastgele iyi koşullu (blok köşegen baskın) sistemler: çözüm, YOĞUN
    kurulmuş aynı matrisin ``np.linalg.solve`` çözümüyle makine
    hassasiyetinde eş — tohumlu, N ve blok boyutu m taranarak.
(b) Tekil/kötü koşullu blokta davranış BEYANLI: sessiz NaN yok — tekil
    pivot bloğu k adımını söyleyen ``np.linalg.LinAlgError``; sonlu
    olmayan girdi ``ValueError`` (giriş kapısı).
(c) Kimlik sistemi (A = I) → x = b BİT-ÖZDEŞ (tobytes eşitliği).
(d) Toplu (i-kolonları) çağrı ile tek tek çağrı bit-özdeş — satır-örtük
    katmanın vektörize kullanım sözleşmesi.

EŞİKLER ÖLÇÜMDEN (M4 Max, NumPy 2.x/Accelerate, 2026-08-16, ölçüm betiği
scratchpad'de; sayılar aşağıda):
  - Yoğun çapraz en kötü göreli hata (N∈{1,2,3,5,24,96} × m∈{1,2,4,5} ×
    5 tohum taraması): 7,755e-17 → eşik 1e-14 (~130× pay; farklı
    BLAS/LAPACK sürümlerinde son bit davranışı değişebilir, mertebe
    değişemez).
  - Toplu/tek maks fark: 0,0 (bit-özdeş ÖLÇÜLDÜ) → np.array_equal.
  - Kimlik sistemi: tobytes eşitliği tüm (N, m) kombinasyonlarında
    ÖLÇÜLDÜ → bit-özdeşlik bekçisi.

MUTASYON KANITI (elle uygulandı, kırmızı ÖLÇÜLDÜ, geri alındı; md5'ler
hrma/cfd/implicit.py dosyasına ait — sağlam sürüm
e5360718d7510309a46263bdf6e31578):
  M1 "alt-köşegen ihmal" (bant yapısını bozan mutasyon): ileri elemede
     ``pivot = diag[..., k, :, :] - l_k @ c_prime[..., k-1, :, :]`` →
     ``pivot = diag[..., k, :, :]`` ve
     ``sag_vek = rhs[..., k, :] - einsum(l_k, d_prime)`` →
     ``sag_vek = rhs[..., k, :]``
     (mutant md5 a4292db78523c9505979d4232108d835)
     → 21 test KIRMIZI, 14 yeşil (ÖLÇÜLDÜ): tüm 20
       test_yogun_capraz_makine_hassasiyeti parametresi (yoğun çaprazla
       fark mertebe 1e-2..1e-1) + test_toplu_tek_bit_ozdes (testin
       İÇİNDEKİ yoğun çapraz denetimi; tek/toplu eşitliği mutasyonda da
       korunur, kırmızıyı yoğun denetim üretir).
     YEŞİL kalanlar beyanlı ve tanımla tutarlı: test_n_bir_yogun_capraz
     (N=1'de alt-köşegen yok), kimlik testleri (L=0 sistemde ihmalin
     etkisi yok), tekil/girdi/biçim denetimleri. Bekçi özgüllüğü: kimlik
     bekçisi bant mutasyonunu YAKALAYAMAZ, yoğun çapraz yakalar; ikisi
     birbirinin yerine geçemez.
  Mutasyondan sonra dosya md5 e5360718d7510309a46263bdf6e31578 değerine
  bit-özdeş geri kondu (cp + md5 doğrulaması).

Performans İDDİASI YOK: ölçülen değerler (N=24/96, 1000 çağrı) modül
docstring'inde ÖLÇÜLDÜ olarak; burada süre bekçisi kurulmaz (süre tavanı
yok kararı, belge §13 soru 1).
"""

import numpy as np
import pytest

from hrma.cfd.implicit import solve_block_tridiag

# Ölçümden kilitlenen eşik (docstring: 7,755e-17 ölçüldü, ~130× pay)
YOGUN_CAPRAZ_ESIK = 1e-14


def kur_sistem(rng, batch, n, m):
    """İyi koşullu (blok köşegen baskın) rastgele sistem kurar.

    Köşegen bloklara 3m·I eklenir: kenar blok girdileri [-1, 1] bandında
    olduğundan satır toplamı en çok ~2m + (m-1) < 3m kalır — baskınlık
    kurgu gereği sağlanır (uydurma tolerans değil, kuruluş garantisi).
    """
    lower = rng.uniform(-1.0, 1.0, size=batch + (max(n - 1, 0), m, m))
    upper = rng.uniform(-1.0, 1.0, size=batch + (max(n - 1, 0), m, m))
    diag = rng.uniform(-1.0, 1.0, size=batch + (n, m, m))
    diag = diag + (3.0 * m) * np.eye(m)
    rhs = rng.uniform(-1.0, 1.0, size=batch + (n, m))
    return lower, diag, upper, rhs


def yogun_kur(lower, diag, upper, rhs):
    """Aynı sistemi yoğun (Nm × Nm) matris olarak kurar — bağımsız yol."""
    n, m = diag.shape[0], diag.shape[-1]
    a_mat = np.zeros((n * m, n * m))
    for k in range(n):
        a_mat[k * m:(k + 1) * m, k * m:(k + 1) * m] = diag[k]
        if k > 0:
            a_mat[k * m:(k + 1) * m, (k - 1) * m:k * m] = lower[k - 1]
        if k < n - 1:
            a_mat[k * m:(k + 1) * m, (k + 1) * m:(k + 2) * m] = upper[k]
    return a_mat, rhs.reshape(n * m)


# ---------------------------------------------------------------- (a) yoğun çapraz

@pytest.mark.parametrize('n', [2, 3, 5, 24, 96])
@pytest.mark.parametrize('m', [1, 2, 4, 5])
def test_yogun_capraz_makine_hassasiyeti(n, m):
    """Rastgele iyi koşullu sistemde çözüm yoğun np.linalg.solve ile eş."""
    rng = np.random.default_rng(20260816 + 1000 * n + m)
    for _ in range(3):
        lower, diag, upper, rhs = kur_sistem(rng, (), n, m)
        x = solve_block_tridiag(lower, diag, upper, rhs)
        a_mat, b_vek = yogun_kur(lower, diag, upper, rhs)
        x_ref = np.linalg.solve(a_mat, b_vek).reshape(n, m)
        olcek = np.max(np.abs(x_ref)) + 1.0
        assert np.max(np.abs(x - x_ref)) / olcek < YOGUN_CAPRAZ_ESIK


def test_n_bir_yogun_capraz():
    """N=1 (tek blok satır, kenar blokları boş) desteklenir ve doğrudur."""
    rng = np.random.default_rng(11)
    lower, diag, upper, rhs = kur_sistem(rng, (), 1, 4)
    assert lower.shape == (0, 4, 4)
    x = solve_block_tridiag(lower, diag, upper, rhs)
    x_ref = np.linalg.solve(diag[0], rhs[0])
    assert np.max(np.abs(x[0] - x_ref)) < YOGUN_CAPRAZ_ESIK


# ---------------------------------------------------------------- (d) toplu sözleşme

def test_toplu_tek_bit_ozdes():
    """i-kolonları toplu çağrısı tek tek çağrılarla BİT-ÖZDEŞ.

    Satır-örtük katman kolonları toplu çözecek (belge §9.2 "i üstünde
    vektörize"); toplu yolun tek yoldan sapmaması sözleşmedir. Ayrıca her
    kolon yoğun çaprazla da denetlenir (toplu yol kendi başına doğru).
    ÖLÇÜLDÜ: maks fark 0,0 → np.array_equal.
    """
    rng = np.random.default_rng(7)
    b_say = 6
    lower, diag, upper, rhs = kur_sistem(rng, (b_say,), 24, 4)
    x_toplu = solve_block_tridiag(lower, diag, upper, rhs)
    assert x_toplu.shape == (b_say, 24, 4)
    for b in range(b_say):
        x_tek = solve_block_tridiag(lower[b], diag[b], upper[b], rhs[b])
        assert np.array_equal(x_tek, x_toplu[b])
        a_mat, b_vek = yogun_kur(lower[b], diag[b], upper[b], rhs[b])
        x_ref = np.linalg.solve(a_mat, b_vek).reshape(24, 4)
        olcek = np.max(np.abs(x_ref)) + 1.0
        assert np.max(np.abs(x_toplu[b] - x_ref)) / olcek < YOGUN_CAPRAZ_ESIK


# ---------------------------------------------------------------- (c) kimlik bit-özdeş

@pytest.mark.parametrize('n,m', [(1, 4), (5, 4), (24, 4), (96, 4),
                                 (24, 1), (24, 5)])
def test_kimlik_bit_ozdes(n, m):
    """A = I → x = b bit-özdeş (tobytes eşitliği; ÖLÇÜLDÜ, tüm kombinasyonlar)."""
    rng = np.random.default_rng(42 + n + m)
    diag = np.broadcast_to(np.eye(m), (n, m, m)).copy()
    lower = np.zeros((max(n - 1, 0), m, m))
    upper = np.zeros((max(n - 1, 0), m, m))
    rhs = rng.standard_normal((n, m)) * rng.uniform(1e-8, 1e8)
    x = solve_block_tridiag(lower, diag, upper, rhs)
    assert x.tobytes() == rhs.tobytes()


# ---------------------------------------------------------------- (b) beyanlı davranış

def test_tekil_pivot_k0_beyanli():
    """İlk köşegen blok tekil → LinAlgError, mesajda k=0 (sessiz NaN yok)."""
    diag = np.zeros((2, 3, 3))
    diag[1] = np.eye(3)
    lower = np.zeros((1, 3, 3))
    upper = np.zeros((1, 3, 3))
    rhs = np.ones((2, 3))
    with pytest.raises(np.linalg.LinAlgError, match='k=0'):
        solve_block_tridiag(lower, diag, upper, rhs)


def test_tekil_pivot_ic_adimda_beyanli():
    """İç adımda tekil pivot bloğu → LinAlgError, mesajda k=1."""
    diag = np.stack([np.eye(3), np.zeros((3, 3)), np.eye(3)])
    lower = np.zeros((2, 3, 3))
    upper = np.zeros((2, 3, 3))
    rhs = np.ones((3, 3))
    with pytest.raises(np.linalg.LinAlgError, match='k=1'):
        solve_block_tridiag(lower, diag, upper, rhs)


@pytest.mark.parametrize('bozuk', ['rhs_nan', 'diag_inf', 'lower_nan'])
def test_sonlu_olmayan_girdi_red(bozuk):
    """NaN/inf girdi ValueError ile reddedilir — sessiz NaN yasağı kapısı."""
    rng = np.random.default_rng(5)
    lower, diag, upper, rhs = kur_sistem(rng, (), 4, 2)
    if bozuk == 'rhs_nan':
        rhs[2, 1] = np.nan
    elif bozuk == 'diag_inf':
        diag[1, 0, 0] = np.inf
    else:
        lower[0, 1, 1] = np.nan
    with pytest.raises(ValueError, match='sonlu olmayan'):
        solve_block_tridiag(lower, diag, upper, rhs)


def test_bicim_sozlesmesi_red():
    """Biçim sözleşmesi ihlalleri gerekçeli ValueError."""
    rng = np.random.default_rng(9)
    lower, diag, upper, rhs = kur_sistem(rng, (), 4, 3)
    with pytest.raises(ValueError, match='kare'):
        solve_block_tridiag(lower, diag[..., :2], upper, rhs)
    with pytest.raises(ValueError, match='lower'):
        solve_block_tridiag(lower[:-1], diag, upper, rhs)
    with pytest.raises(ValueError, match='upper'):
        solve_block_tridiag(lower, diag, upper[:-1], rhs)
    with pytest.raises(ValueError, match='rhs'):
        solve_block_tridiag(lower, diag, upper, rhs[:-1])
    with pytest.raises(ValueError, match='en az 3 boyutlu'):
        solve_block_tridiag(lower, np.eye(3), upper, rhs)


def test_girdiler_degismez():
    """Çözücü girdileri yerinde DEĞİŞTİRMEZ (kopya sözleşmesi)."""
    rng = np.random.default_rng(13)
    lower, diag, upper, rhs = kur_sistem(rng, (), 8, 4)
    yedekler = [d.copy() for d in (lower, diag, upper, rhs)]
    solve_block_tridiag(lower, diag, upper, rhs)
    for asil, yedek in zip((lower, diag, upper, rhs), yedekler):
        assert np.array_equal(asil, yedek)
