# tests/cfd — j-yönü satır-örtük gevşetme katmanı bekçileri (V0 entegrasyonu)
"""
``hrma.cfd.relax_implicit`` + ``steady.solve_steady_axisym`` örtük yol
entegrasyonunun doğrulama merdiveni (viskoz tasarım belgesi §4.2/§5.6;
V0 ölçüm turu M4 Max, 2026-08-17 — betikler scratchpad, sayılar burada).

HÜKÜM-NÖTRLÜK SÖZLEŞMESİ (kırmızı çizgi): kararlı hâl kökü kalıntı = 0
ile tanımlıdır; örtük katman köke gidiş YOLUNU değiştirir, KÖKÜ
değiştirmez. Bekçileri (a) iki yolun yakınsadığı alanların alan-alan
eşitliği (bant ÖLÇÜMDEN), (b) hüküm ölçütlerinin (debi bandı + boğaz Mach
bandı + kalıntı eşiği üçlüsü) iki yolda aynı olması, (c) varsayılanın
AÇIK yol kalması (149 mevcut bekçinin bit-özdeşlik taşıyıcısı; örtük
opt-in — V0 kararı, gerekçe steady.TIME_INTEGRATORS yanında).

V0 ÖLÇÜM ÖZETİ (tablolar; conftest lülesi, aksi yazılmadıkça ürün tol):

  CFL taraması (60×12, i-yalnız Δt semantiği, K=25):
    1.mrt : cfl 2→1473, 5→1309, 10→1243, 25→1198, 50→1182, 100→1174 it
            (Δt→∞ Newton-benzeri: tekdüze düşüş + doyum — yaklaşık
            Jacobian nedeniyle kuadratik Newton İDDİA EDİLMEZ)
    MUSCL : cfl 25→4452, 50→5727, 100→8707 it (hepsi yeşil)
  K (eğim tazeleme) taraması (60×12 MUSCL): K=2 limit döngüsü, K=5
    1,5e-4'te asılı, K=10 12300, K=25 3605*, K=100 12306 it → varsayılan
    25 (* kaynak-örtük öncesi ölçüm; son kod: 4452).
  nj merdiveni (60×nj, 1.mrt, örtük/açık it): 12: 1198/2889 (2,4×),
    48: 2704/7252 (2,7×), 96: 4403/13817 (3,1×) — iterasyon kazancı
    nj ile BÜYÜYOR (belge §4.2 öngörüsünün V0 kanıtı).
  Şoklu vaka (120×24, Pb=2,75 MPa, tol 2e-6): açık 21870 it / örtük
    5573 it (3,9×; ÜRETİM TAVANI 20000'İN ALTINA İNDİ); debi bit-aynı
    4,811267; alan bandı 2,36e-4.
  DÜRÜST EKSİLER: (i) düşük-Mach CR 7,09 MUSCL (60×12 ve 120×24) örtük
    yakınsamıyor (kalıntı 2e-5/9,4e-5'te geveleme; S9 teşhisi doğru:
    kilit sınırlayıcı politikası + akustik/taşınım ölçek ayrışması —
    viskoz partisine düşük-Mach ön-koşullama notu). (ii) duvar-saati
    saf NumPy katman maliyetiyle sınırlı (örtük adım 2-7× pahalı; numba
    turu SONRAKİ parti, belge §5.9 ölç-sonra-hızlandır).

EŞİKLER ÖLÇÜMDEN (kalibrasyon koşusu, bu dosyanın vakalarıyla birebir):
  - Jacobian homojenlik maks bağıl fark 2,10e-15 → eşik 1e-13 (~50× pay)
  - Jacobian merkezi sonlu-fark maks ölçekli fark 1,67e-10 → eşik 1e-8
  - 1.mrt derin nötrlük: alan bandı 2,162e-12 → 1e-10; debi farkı
    1,296e-14 → 1e-12
  - MUSCL ürün nötrlük: alan bandı 5,411e-08 → 5e-6 (~100× pay); debi
    farkı 1,424e-11 → 1e-9
  - Örtük korunum bütçesi: kütle 3,27e-14 (1.mrt derin) / 1,04e-11
    (MUSCL) → eşik 1e-10 (açık yolun 1e-10 sınıfıyla aynı)
  - Newton limiti: it(cfl2)=1473 > it(cfl25)=1198 (fark %19)
  - 60×96 kaynak-örtük sağlık sondası: 500 iterasyonda kalıntı oranı
    1,164e-5 → eşik 1e-2 (~1000× pay)

MUTASYON KANITLARI (elle uygulandı, kırmızı ÖLÇÜLDÜ, md5 ile bit-özdeş
geri kondu; sağlam relax_implicit.py md5 b9470a1e6ab0b3fd92798a6a0b6d145e):
  M1 "yukarı-akış bölme işareti" — a_minus = 0.5*(a_hi − lam_eye) →
     0.5*(a_hi + lam_eye) (mutant md5 e180cd99a43d9f8eb65a72fec599cd9c):
     sönüm yönü bozulur → 7 KIRMIZI / 8 yeşil (kırmızılar: iki nötrlük,
     hüküm ölçütleri, donma beyanı, korunum, Newton, sağlık sondası;
     yeşil kalanlar beyanla tutarlı — cebirsel Jacobian bekçileri bölmeye
     dokunmaz, varsayılan-yol bekçileri örtük dalı hiç koşmaz).
  M2 "toplu çağrı yerine kolon-kolon döngü" (mutant md5
     a0a139afd02d4838cc980458c7ff0ebc): 15/15 YEŞİL KALDI — sonuç
     bit-aynı (implicit.py toplu/tek bit-özdeşlik sözleşmesinin canlı
     kanıtı); fark yalnız süre: 60×96 1.mrt 500-iter sondası 4,1 → 23,7 s
     (5,8×), test dosyası 25,1 → 95,1 s. Toplu-çağrı sözleşmesi
     performans sözleşmesidir, doğruluk sözleşmesi değil — ÖLÇÜLDÜ.
  M3 "kaynak-örtük söküm" — eksenel simetri kaynak Jacobian bloğu
     (diag[..., 2, :] satırları) silindi (mutant md5
     dc5cd72fd8507058464a09ed714498d3): eksen sertliği (kaynak/V = p/r̄
     ∝ nj) açık kalır → test_kaynak_ortuk_sagligi KIRMIZI, kalan 14
     yeşil — sondanın özgüllüğü: bu regresyonu 60×12 tabanlı hiçbir
     bekçi yakalayamaz (ölçülen desen: nj=12 etkilenmez).
"""

import numpy as np
import pytest

from .conftest import (LULE_GAMMA, LULE_R, LULE_P0, LULE_T0, LULE_PB,
                       LULE_L_CONV, LULE_L_DIV, lule_duvar_yaricapi)
from hrma.cfd.euler_core import (cons_to_prim_axisym, local_dt_axisym,
                                 precompute_geometry, prim_to_cons_axisym)
from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.relax_implicit import (convective_jacobian,
                                     line_implicit_delta, local_dt_axial)
from hrma.cfd.steady import (DEFAULT_CFL_IMPLICIT_MAX,
                             DEFAULT_IMPLICIT_SLOPE_REFRESH,
                             TIME_INTEGRATORS, solve_steady_axisym)

# Eşikler ÖLÇÜMDEN (modül docstring'i)
JAC_HOMOJENLIK_ESIK = 1e-13
JAC_SONLU_FARK_ESIK = 1e-8
NOTRLUK_1MRT_BANT = 1e-10
NOTRLUK_1MRT_DEBI = 1e-12
NOTRLUK_MUSCL_BANT = 5e-6
NOTRLUK_MUSCL_DEBI = 1e-9
KORUNUM_ESIK = 1e-10
SAGLIK_ORAN_ESIK = 1e-2

NI, NJ = 60, 12


def _grid(ni=NI, nj=NJ):
    z = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, ni + 1)
    return build_grid_from_wall(z, lule_duvar_yaricapi(z), nj)


_ORTAK = dict(P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA, R=LULE_R,
              Pb=LULE_PB)
_DERIN = dict(max_iters=20000, tol_res=1e-11, settle_tol=1e-12)


@pytest.fixture(scope='module')
def izgara():
    return _grid()


@pytest.fixture(scope='module')
def cift_1mrt(izgara):
    """1. mertebe derin çift: (açık, örtük). Kök TEKİL tanımlı (eğim/
    dondurma makinesi yok) → nötrlüğün KESKİN ölçümü."""
    ra = solve_steady_axisym(izgara, second_order=False, **_DERIN, **_ORTAK)
    rb = solve_steady_axisym(izgara, second_order=False,
                             time_integrator='line_implicit_j',
                             **_DERIN, **_ORTAK)
    return ra, rb


@pytest.fixture(scope='module')
def cift_muscl(izgara):
    """MUSCL ürün-tol çifti: (açık, örtük). Örtük yol oturma-tetikli
    dondurmayla yakınsar (kalibrasyon: donma 4253. iterasyonda, 4452
    iterasyonda yeşil — açık 6897)."""
    ra = solve_steady_axisym(izgara, max_iters=30000, **_ORTAK)
    rb = solve_steady_axisym(izgara, max_iters=30000,
                             time_integrator='line_implicit_j', **_ORTAK)
    return ra, rb


def _bant(ra, rb):
    return max(float(np.max(np.abs(fa - rb['fields'][ad]))
                     / np.max(np.abs(fa)))
               for ad, fa in ra['fields'].items())


def _debi_farki(ra, rb):
    return (abs(ra['mass_flow_in_kg_s'] - rb['mass_flow_in_kg_s'])
            / abs(ra['mass_flow_in_kg_s']))


# ---------------------------------------------------------------------------
# Jacobian doğruluğu (cebirsel — ızgarasız)
# ---------------------------------------------------------------------------

def _rastgele_durumlar(n_pts=50, tohum=7):
    rng = np.random.default_rng(tohum)
    rho = rng.uniform(0.05, 5.0, n_pts)
    uz = rng.uniform(-2000.0, 2000.0, n_pts)
    ur = rng.uniform(-800.0, 800.0, n_pts)
    p = rng.uniform(1e3, 8e6, n_pts)
    th = rng.uniform(0.0, 2.0 * np.pi, n_pts)
    n_hat = np.stack([np.cos(th), np.sin(th)], axis=-1)
    U = prim_to_cons_axisym(rho, uz, ur, p, LULE_GAMMA)
    return U, n_hat


def _aki_n(U, n_hat, g):
    w = cons_to_prim_axisym(U, g)
    vn = w[..., 1] * n_hat[..., 0] + w[..., 2] * n_hat[..., 1]
    return np.stack([w[..., 0] * vn,
                     w[..., 0] * w[..., 1] * vn + w[..., 3] * n_hat[..., 0],
                     w[..., 0] * w[..., 2] * vn + w[..., 3] * n_hat[..., 1],
                     (U[..., 3] + w[..., 3]) * vn], axis=-1)


def test_jacobian_homojenlik():
    """Euler akısı U'da 1. derece homojendir: A(U)·U = F(U)·n̂ (kapalı
    özdeşlik) — katsayı hatalarını tek kalemde yakalar."""
    U, n_hat = _rastgele_durumlar()
    w = cons_to_prim_axisym(U, LULE_GAMMA)
    A = convective_jacobian(w, n_hat, LULE_GAMMA)
    AU = np.einsum('...ij,...j->...i', A, U)
    FU = _aki_n(U, n_hat, LULE_GAMMA)
    rel = np.max(np.abs(AU - FU) / (np.abs(FU) + 1e-30))
    assert rel < JAC_HOMOJENLIK_ESIK


def test_jacobian_sonlu_fark():
    """Merkezi sonlu farkla sütun-sütun çapraz (ölçüm 1,67e-10)."""
    U, n_hat = _rastgele_durumlar()
    w = cons_to_prim_axisym(U, LULE_GAMMA)
    A = convective_jacobian(w, n_hat, LULE_GAMMA)
    worst = 0.0
    for k in range(4):
        h = 1e-6 * np.maximum(np.abs(U[..., k]), 1e-3)
        dU = np.zeros_like(U)
        dU[..., k] = h
        fd = (_aki_n(U + dU, n_hat, LULE_GAMMA)
              - _aki_n(U - dU, n_hat, LULE_GAMMA)) / (2.0 * h[..., None])
        an = A[..., :, k]
        worst = max(worst, float(np.max(np.abs(fd - an))
                                 / (np.max(np.abs(an)) + 1e-30)))
    assert worst < JAC_SONLU_FARK_ESIK


def test_dt_axial_gevsek(izgara):
    """i-yalnız Δt, tam-toplam Δt'den hücre hücre BÜYÜK-EŞİT olmalı
    (payda alt kümesi — cebirsel; belge §4.2: j kısıtı örtükle kalkar)."""
    from hrma.cfd.steady import _isentropic_initial_state
    U, _ = _isentropic_initial_state(izgara, LULE_P0, LULE_T0,
                                     LULE_GAMMA, LULE_R, Pb=LULE_PB)
    geom = precompute_geometry(izgara)
    dt_full = local_dt_axisym(U, izgara, LULE_GAMMA, 0.9,
                              geom['area_i'], geom['area_j'])
    dt_ax = local_dt_axial(U, izgara, LULE_GAMMA, 0.9, geom['area_i'])
    assert np.all(dt_ax >= dt_full)
    assert np.all(np.isfinite(dt_ax)) and np.all(dt_ax > 0.0)


# ---------------------------------------------------------------------------
# Hüküm-nötrlük (kırmızı çizgi bekçileri)
# ---------------------------------------------------------------------------

def test_notrluk_1mrt_ayni_kok(cift_1mrt):
    """KESKİN nötrlük: 1. mertebede kök tekil tanımlı — iki yol makine
    sınıfında aynı alana inmeli (ölçüm: bant 2,16e-12)."""
    ra, rb = cift_1mrt
    assert ra['converged'] and rb['converged']
    assert _bant(ra, rb) < NOTRLUK_1MRT_BANT
    assert _debi_farki(ra, rb) < NOTRLUK_1MRT_DEBI


def test_notrluk_muscl(cift_muscl):
    """MUSCL nötrlük (ürün tol): örtük yol oturma-dondurmalı Picard ile
    aynı köke inmeli (ölçüm: bant 5,41e-8, debi farkı 1,42e-11)."""
    ra, rb = cift_muscl
    assert ra['converged'] and rb['converged']
    assert _bant(ra, rb) < NOTRLUK_MUSCL_BANT
    assert _debi_farki(ra, rb) < NOTRLUK_MUSCL_DEBI


def test_notrluk_iterasyon_kazanci(cift_muscl, cift_1mrt):
    """Örtük yolun V0 kazancı bu vakada ÖLÇÜLÜDÜR: iterasyon sayısı açık
    yoldan az (kalibrasyon: MUSCL 4452<6897, 1.mrt 1826<4031). Bu bir
    performans İDDİASI değil regresyon çipasıdır: katmanı bozan ama
    yakınsamayı bozmayan mutasyon (ör. yanlış Jacobian ölçeği) kazancı
    siler ve burada yakalanır."""
    for ra, rb in (cift_muscl, cift_1mrt):
        assert rb['iterations'] < ra['iterations']


def test_hukum_olcutleri_degismez(cift_muscl):
    """Hüküm üçlüsü (debi bandı + Mach bandı + kalıntı eşiği) iki yolda
    AYNI beyanla: convergence_basis aynı ölçüt cümlesini taşır; örtük
    yol ayrı/ek ölçüt İCAT EDEMEZ."""
    ra, rb = cift_muscl
    for r in (ra, rb):
        basis = r['convergence_basis']
        assert 'Hüküm kullanıcı büyüklüklerinden' in basis
        assert 'debi bandı' in basis
        assert 'Mach bandı' in basis
        assert 'kalıntısı' in basis
    assert ra['time_integrator'] == 'ssp_rk2'
    assert rb['time_integrator'] == 'line_implicit_j'
    for r in (ra, rb):
        assert 'HÜKÜM-NÖTR' in r['time_integrator_basis']
        assert r['inputs']['time_integrator'] == r['time_integrator']
        assert r['inputs']['cfl_implicit_max'] == DEFAULT_CFL_IMPLICIT_MAX
        assert (r['inputs']['implicit_slope_refresh']
                == DEFAULT_IMPLICIT_SLOPE_REFRESH)


def test_ortuk_donma_beyani(cift_muscl):
    """Örtük MUSCL yolunun oturma-tetikli dondurması ÇIKTIDA beyanlı:
    dondurma anı + sebep cümlesi (kalibrasyon: donma 4253'te)."""
    _, rb = cift_muscl
    assert rb['limiter_frozen_at_iter'] is not None
    assert 'oturma tespiti' in rb['convergence_basis']


def test_acik_yol_plato_beyani_degismedi(cift_muscl):
    """Açık yolun dondurma beyan sözleşmesi el değmemiş: bu vakada açık
    yol HİÇ dondurmaz (kalibrasyon: donma=None) ve 'oturma tespiti'
    cümlesi açık yol beyanında GÖRÜNEMEZ."""
    ra, _ = cift_muscl
    assert ra['limiter_frozen_at_iter'] is None
    assert 'oturma tespiti' not in ra['convergence_basis']


# ---------------------------------------------------------------------------
# Korunum bütçesi (örtük yol, açık yolun 1e-10 sınıfı)
# ---------------------------------------------------------------------------

def test_ortuk_korunum_butcesi(cift_1mrt, cift_muscl):
    for _, rb in (cift_1mrt, cift_muscl):
        assert rb['mass_balance_rel'] < KORUNUM_ESIK
        assert rb['energy_balance_rel'] < KORUNUM_ESIK
        # Kayma duvarında kütle akısı ayrık sıfır (Euler sözleşmesi aynen)
        assert rb['wall_mass_flux_kg_s'] == 0.0


# ---------------------------------------------------------------------------
# Δt → ∞ limiti (Newton-benzeri davranış)
# ---------------------------------------------------------------------------

def test_newton_limiti(izgara):
    """CFL tavanı büyüdükçe iterasyon düşmeli (ölçüm: cfl2→1473,
    cfl25→1198; doyumlu düşüş — yaklaşık Jacobian, kuadratik Newton
    iddiası YOK, modül docstring tablosu)."""
    r2 = solve_steady_axisym(izgara, second_order=False,
                             time_integrator='line_implicit_j',
                             cfl_implicit_max=2.0, max_iters=20000,
                             **_ORTAK)
    r25 = solve_steady_axisym(izgara, second_order=False,
                              time_integrator='line_implicit_j',
                              cfl_implicit_max=25.0, max_iters=20000,
                              **_ORTAK)
    assert r2['converged'] and r25['converged']
    assert r25['iterations'] < r2['iterations']


# ---------------------------------------------------------------------------
# Varsayılan yol ve sözleşme kapıları
# ---------------------------------------------------------------------------

def test_varsayilan_acik_ve_bit_ozdes(izgara):
    """Varsayılan 'ssp_rk2' ve açıkça verilmesi bit-özdeş: örtük katman
    varsayılan yolu HİÇBİR bitte değiştiremez (149 mevcut bekçinin
    taşıyıcı sözleşmesi; kısa koşu yeter — aynı kod yolu)."""
    ra = solve_steady_axisym(izgara, max_iters=300, **_ORTAK)
    rb = solve_steady_axisym(izgara, max_iters=300,
                             time_integrator='ssp_rk2', **_ORTAK)
    assert ra['time_integrator'] == 'ssp_rk2'
    assert np.array_equal(ra['residual_history'], rb['residual_history'])
    for ad in ra['fields']:
        assert np.array_equal(ra['fields'][ad], rb['fields'][ad])


def test_gecersiz_integrator_reddi(izgara):
    with pytest.raises(ValueError, match='time_integrator'):
        solve_steady_axisym(izgara, time_integrator='backward_euler',
                            **_ORTAK)
    assert TIME_INTEGRATORS == ('ssp_rk2', 'line_implicit_j')


def test_asiri_cfl_istisna_sizdirmaz(izgara):
    """Aşırı CFL'de bile sürücü SÖZLEŞMELİ döner: implicit.py giriş
    kapısı (ValueError) sürücüden DIŞARI SIZMAZ — fiziksel olmayan durum
    Δt-sonluluk kapısında 'diverged' beyanına düşer (ölçülen regresyon:
    kapı öncesi CFL=100 taraması ValueError ile çakılıyordu). Koşunun
    yakınsayıp yakınsamaması bu bekçinin konusu değildir."""
    r = solve_steady_axisym(izgara, time_integrator='line_implicit_j',
                            cfl_implicit_max=1000.0, max_iters=1500,
                            **_ORTAK)
    assert isinstance(r, dict)
    assert isinstance(r['converged'], bool)
    assert 'convergence_basis' in r


# ---------------------------------------------------------------------------
# Kaynak-örtük sağlık sondası (eksen sertliği; mutasyon M3 hedefi)
# ---------------------------------------------------------------------------

def test_kaynak_ortuk_sagligi():
    """60×96 (eksen yakını r̄ küçük — kaynak/V = p/r̄ sertliği): kaynak
    Jacobian'ı köşegende OLMADAN örtük yol ~20-300 iterasyonda ıraksıyordu
    (ÖLÇÜLDÜ, V0 turu). Sonda: 500 iterasyonda kalıntı sonlu kalmalı ve
    başlangıcının 1e-2'sinin altına inmeli (ölçüm: 1,16e-5)."""
    g96 = _grid(60, 96)
    r = solve_steady_axisym(g96, second_order=False,
                            time_integrator='line_implicit_j',
                            max_iters=500, **_ORTAK)
    rh = np.asarray(r['residual_history'])
    assert np.all(np.isfinite(rh))
    assert rh[-1] / rh[0] < SAGLIK_ORAN_ESIK
