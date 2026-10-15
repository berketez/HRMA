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
    MUSCL : cfl 25→4452, 50→5727, 100→8707 it (V0, KAPI ÖNCESİ;
            kapı sonrası 2026-09-07 ölçümü 5512/9970/10762 —
            hrma.cfd.steady.IMPLICIT_CALIBRATION, OH-B4-05)
  K (eğim tazeleme) taraması (60×12 MUSCL): K=2 limit döngüsü, K=5
    1,5e-4'te asılı, K=10 12300, K=25 3605*, K=100 12306 it → varsayılan
    25 (* kaynak-örtük öncesi ölçüm; V0 son kodu 4452, kapı sonrası
    5512 — OH-B4-05).
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
  M4 (V3, steady.py — tetik/hüküm ayrımı) "dairesel kilit geri":
     _freeze_settled eşiği freeze_settle_tol yerine yeniden settle_tol
     okur (sağlam steady.py md5 df5e633d37b8a09310a3cf8f09cac4b4,
     mutant 3c5e02cb93fa627164633b9d67e4e2f9) → 2 KIRMIZI:
     test_tetik_hukumden_bagimsiz_atesler (settle 1e-14'te donma hiç
     olmuyor) + test_tetik_esigi_beyanda_yayimlanir (dondurma gerekçesi
     doğmadığından eşik cümlesi beyanda yok); kalan 17 yeşil (varsayılan
     yol bit-özdeşliğiyle tutarlı — kilit varsayılanda zaten aynı eşik).
     Geri alma: md5 birebir döndü.
"""

import numpy as np
import pytest

from .conftest import (LULE_GAMMA, LULE_R, LULE_P0, LULE_T0, LULE_PB,
                       LULE_L_CONV, LULE_L_DIV, lule_duvar_yaricapi)
from hrma.cfd.euler_core import (cons_to_prim_axisym, local_dt_axisym,
                                 precompute_geometry, prim_to_cons_axisym,
                                 residual_axisym)
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
    dondurmayla yakınsar (kalibrasyon 2026-09-07, OH-B4-05: donma 4253.
    iterasyonda, 5512 iterasyonda yeşil — açık 6897; sayılar
    hrma.cfd.steady.IMPLICIT_CALIBRATION'dadır)."""
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
    """Örtük yolun kazancı bu vakada ÖLÇÜLÜDÜR: iterasyon sayısı açık
    yoldan az. Bu bir performans İDDİASI değil regresyon çipasıdır:
    katmanı bozan ama yakınsamayı bozmayan mutasyon (ör. yanlış Jacobian
    ölçeği) kazancı siler ve burada yakalanır.

    KAPSAM BEYANI — ÖH Faz B-4 (defter P6B1-08 ailesi, ölçüm 2026-08-27):
    o gün buradaki "iterasyon" iki yolda AYNI ŞEYİ ölçmüyordu, çünkü
    hükmü veren kalıntı iki yolda aynı operatörden gelmiyordu; şemanın
    kendi kalıntısıyla ölçülünce kazanç TERSİNE dönüyordu (açık 6897,
    örtük 8000-10000) ve yayımlanan 4452 bayat pencerenin erken hükmüydü.

    ONARIM (OH-B4-05, ÖH D26 / fea-cfd a3, ölçüm 2026-09-07): kusurun
    ÜRÜN ayağı ÖH D15'te (OH-Z5-14) zaten kapanmıştı — hüküm artık
    şemanın kendi kalıntısı da eşiğin altındayken veriliyor. Bugün AYNI
    vaka yeniden ölçüldü: örtük yol 4452'de DEĞİL **5512** iterasyonda
    duruyor ve o noktada şema kalıntısı 8,53e-09 < 1e-8; açık yol 6897
    (şema 9,86e-09). Yani ORTAK ölçüt altında kazanç TERSİNE DÖNMÜYOR,
    1,25× olarak duruyor — B-4'ün "tersine" teşhisi kapı ÖNCESİ koda
    aitti. Bayat olan yayımlanan SAYILARDI; onlar
    ``hrma.cfd.steady.IMPLICIT_CALIBRATION`` içinde tek kaynağa alındı ve
    bekçiye bağlandı (tests/test_d26_fea_cfd_a3.py)."""
    for ra, rb in (cift_muscl, cift_1mrt):
        assert rb['iterations'] < ra['iterations']


def test_hukum_olcutleri_degismez(cift_muscl):
    """Hüküm üçlüsü (debi bandı + Mach bandı + kalıntı eşiği) iki yolda
    AYNI beyanla: convergence_basis aynı ölçüt cümlesini taşır; örtük
    yol ayrı/ek ölçüt İCAT EDEMEZ.

    KAPSAM BEYANI — ÖH Faz B-4, defter P6B1-08 (orta). Bu bekçi ölçüt
    CÜMLESİNİN aynılığını sınar, ölçütü BESLEYEN SAYININ aynı operatörden
    geldiğini SINAMAZ: dört alt dizgi ("debi bandı", "Mach bandı",
    "kalıntısı", "HÜKÜM-NÖTR") iki yolda da bulunduğu için, örtük yolun
    hükmü 25 iterasyonluk Picard penceresinin BAYAT eğimli kalıntısını
    okusa bile burası yeşil kalır. Sayısal eksen aşağıya taşındı:
    :func:`test_ortuk_hukum_bayat_pencerenin_kalintisini_okuyor` (bugün
    xfail(strict), P6B1-08) ve :func:`test_donmus_operator_kalintisi_
    seman_kalintisi_degil` (P6B1-03). Bu bekçi SÖKÜLMEZ — cümle
    sözleşmesi kendi başına doğrudur, yalnız yetmez."""
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
    dondurma anı + sebep cümlesi (kalibrasyon: donma 4253'te).

    KAPSAM BEYANI — ÖH Faz B-4, defter P6B1-03 (yüksek). Bu bekçi
    dondurmanın OLDUĞUNU beyan ettirir; dondurmanın FİYATINI (o andan
    sonra yayımlanan kalıntının artık şemanın değil donmuş operatörün
    kalıntısı olduğunu) sormaz — üstelik ürün cümlesi aynı yerde "şema
    minmod" der (``steady.py:942-944``). Dondurmayı ŞART koştuğu için
    bu bekçi savcı sınıflandırmasında "yanlış değeri kilitliyor"dur;
    kilidi çözen sayısal eksen :func:`test_donmus_operator_kalintisi_
    seman_kalintisi_degil`de (bugün xfail(strict))."""
    _, rb = cift_muscl
    assert rb['limiter_frozen_at_iter'] is not None
    assert 'oturma tespiti' in rb['convergence_basis']


# ---------------------------------------------------------------------------
# ÖH FAZ B-4 — "YAYIMLANAN KALINTI KİMİN?" (defter P6B1-03, P6B1-08)
#
# Hüküm cümlesi kalıntıyı "yoğunluk L2 kalıntısı X < tol" diye yayımlar ve
# dondurma dalında "şema minmod" der. Örtük yolda bu sayı iki ayrı sebeple
# ŞEMANIN kalıntısı olmayabilir:
#   * P6B1-08 — eğim tazeleme periyodu 25'tir; pencerenin 24 iterasyonunda
#     kalıntı BAYAT eğimlerle ölçülür ve çevrim içinde düşer, şemanın canlı
#     kalıntısı düşmez. tol_res ikisinin arasına düşerse converged=True.
#   * P6B1-03 — sınırlayıcı donduktan sonra kalıntı DONMUŞ operatörle
#     ölçülür; ürün cümlesi yine "şema minmod" der.
#
# ÖLÇÜM (2026-08-27, bu depo, bu dosyanın kendi lülesi 60×12):
#   açık yol (ssp_rk2, cift_muscl) : yayım 9,862447e-09 = ŞEMA 9,862447e-09
#                                    (oran 1,000000× — sağlıklı taban)
#   örtük yol (cift_muscl, donma 4253'te, it 4452 — KAPI ÖNCESİ ölçüm;
#   kapı sonrası aynı vaka 5512 iterasyonda ve şema kalıntısı 8,53e-09):
#                                    yayım 4,368523e-11 ↔ ŞEMA 8,637525e-07
#                                    (19.770× ; ŞEMA/tol = 86,4)
#   örtük yol, dondurma ATEŞLEMEDEN (settle_tol=1e-3, freeze_settle_tol=
#   1e-30, tol_res=1e-6): it 1449, donma None,
#                                    yayım 9,8538e-07 ↔ ŞEMA 9,7286e-05
#                                    (98,7× ; ŞEMA/tol = 97,3)
#   aynı ayarla AÇIK yol kontrolü  : it 4920, yayım = ŞEMA (oran 1,000000×)
#
# Yani ölçüm aygıtının kendisi açık yolda BİT-DOĞRUDUR (aşağıdaki yeşil
# çapa bunu her koşuda yeniden kanıtlar); ayrışma örtük yola özgüdür.
# ---------------------------------------------------------------------------

def _sema_kalintisi(sonuc, izgara, second_order=True):
    """Geri dönen ALANIN, ŞEMANIN kendi (canlı minmod) operatörüyle ölçülen
    yoğunluk L2 kalıntısı — çözücünün yayımladığı sayıyla AYNI ölçekte
    (ρ0·a0/L), böylece iki sayı doğrudan karşılaştırılabilir.

    Eğim argümanı BİLEREK verilmez (``slopes=None`` → minmod yeniden
    hesaplanır): sorulan soru tam olarak "yayımlanan sayı, şemanın kendi
    operatörünün sayısı mı?"dır.
    """
    f = sonuc['fields']
    U = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                            f['pressure_Pa'], LULE_GAMMA)
    res, _ = residual_axisym(U, izgara, LULE_GAMMA, LULE_R, LULE_P0, LULE_T0,
                             Pb=LULE_PB, second_order=second_order,
                             geom=precompute_geometry(izgara))
    vol = izgara.volume
    olcek = ((LULE_P0 / (LULE_R * LULE_T0))
             * np.sqrt(LULE_GAMMA * LULE_R * LULE_T0)
             / float(izgara.Z[-1, 0] - izgara.Z[0, 0]))
    return float(np.sqrt(np.sum(res[..., 0] ** 2 * vol) / np.sum(vol))
                 / olcek)


#: Bayat-pencere vakasının ayarları (ölçümden; yorum bloğu). ``settle_tol``
#: gevşek seçilir ki hüküm oturma bacağında takılmasın, ``freeze_settle_tol``
#: erişilmez küçüklükte seçilir ki DONDURMA ateşlemesin — böylece kalan tek
#: mekanizma bayat eğim penceresidir (P6B1-08 mekanizmasının izolasyonu).
BAYAT_AYAR = dict(max_iters=20000, tol_res=1e-6, settle_tol=1e-3,
                  freeze_settle_tol=1e-30)


@pytest.fixture(scope='module')
def bayat_pencere(izgara):
    """Dondurma ATEŞLEMEDEN yakınsadı denen örtük koşu (~1,9 s ölçüldü)."""
    return solve_steady_axisym(izgara, time_integrator='line_implicit_j',
                               **BAYAT_AYAR, **_ORTAK)


def test_acik_yolda_yayimlanan_kalinti_semanindir(cift_muscl, izgara):
    """ÖLÇÜM AYGITININ ÇAPASI (yeşil): açık yolda yayımlanan kalıntı, geri
    dönen alanın ŞEMA kalıntısıyla makine sınıfında aynıdır.

    Bu bekçi olmadan aşağıdaki iki xfail "belki de yeniden hesaplama
    yanlıştır" itirazına açık kalırdı: burada aynı yeniden hesaplama, aynı
    ölçek ve aynı alanla ürünün kendi sayısını BİREBİR üretiyor
    (ölçüldü 2026-08-27: 9,862447e-09 ↔ 9,862447e-09, oran 1,000000×).
    """
    ra, _ = cift_muscl
    yayim = float(np.asarray(ra['residual_history'])[-1])
    sema = _sema_kalintisi(ra, izgara)
    assert ra['limiter_frozen_at_iter'] is None, (
        'açık yol bu vakada dondurmamalıydı — vaka değişmiş, çapa yeniden '
        'kalibre edilmeli')
    assert sema == pytest.approx(yayim, rel=1e-9), (
        f'açık yolda bile yayımlanan kalıntı ({yayim:.6e}) alanın şema '
        f'kalıntısından ({sema:.6e}) ayrışıyor — ölçüm aygıtı ya da '
        'çözücünün kalıntı tanımı değişmiş; aşağıdaki iki borç bekçisi bu '
        'çapa olmadan okunamaz')


# ÇEVİRİ (ÖH D15 birleşme düzeltmesi) — BORÇ İMİ KALKTI.
# Bu bekçi P6B1-03 borcunu xfail(strict) ile taşıyordu;
# imin kendi metni "onarım gelince bu im KALKAR" diyordu.
# Kusur ÖH D15 cfd-picard (OH-Z5-14) tarafından
# ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test
# GEÇİYOR ve strict im XPASS ile kırmızı veriyordu. İm
# kaldırıldı; iddia artık CANLI bekçidir — onarım geri
# alınırsa burası kırmızı verir.
#
# ÜRÜNDEKİ KANIT: hrma/cfd/steady.py:726 "YAYIMLANAN SAYI KİMİN? (ÖH
# defter P6B1-01/-03/-04/-08, onarım ...)"
#
# KALKAN İMİN GEREKÇESİ (kayıt için): ÖH defter P6B1-03 — ürün kusuru:
# sınırlayıcı donduktan sonra yayımlanan kalıntı donmuş operatörün,
# cümle ise aynı yerde "şema minmod" diyor. Faz B ürün onarımı YAPMAZ;
# bekçi borç imiyle yazılır, onarım dalgası bu imi kaldırır.
def test_donmus_operator_kalintisi_seman_kalintisi_degil(cift_muscl, izgara):
    """``converged=True`` hükmü ŞEMANIN kalıntısıyla desteklenmelidir.

    ÖH Faz B-4 — defter P6B1-03 (yüksek). Örtük MUSCL koşusu 4253.
    iterasyonda sınırlayıcıyı donduruyor ve 4452'de "yakınsadı" ilan
    ediyor; hükmü besleyen sayı (4,369e-11) donmuş Picard operatörünün
    kalıntısıdır. Aynı alanın ŞEMA (canlı minmod) kalıntısı 8,638e-07,
    yani ürünün kendi toleransının (1e-8) **86,4 katı** — şema o alanda
    yakınsamamıştır. Fark 19.770×.

    Kabul: ya hüküm şemanın kalıntısıyla verilir, ya da yayımlanan sayı
    dondurulmuş operatöre ait olduğunu ADIYLA beyan eder (bugün cümle
    tersini söylüyor: "şema minmod").

    ONARIM SİMÜLASYONU (ölçüldü 2026-08-27): dondurma bastırıldığında
    (``ramp_iters=1e7`` + ``freeze_settle_tol=1e-30``) koşu 5075
    iterasyonda yine ``converged=True`` diyor, yayım 9,815e-09 ↔ şema
    1,0837e-06 (tolun 108 katı) — yani **dondurma tek kanal değildir**,
    P6B1-08'in bayat penceresi bu vakada da canlıdır. Hedef ULAŞILABİLİR:
    aynı yol 12000 iterasyonda şema kalıntısını 2,234e-10'a indiriyor;
    kusur erken HÜKÜMdür, erişilemez bir eşik değil.
    """
    _, rb = cift_muscl
    assert rb['limiter_frozen_at_iter'] is not None, (
        'vaka dondurmuyor — bekçi yeniden kalibre edilmeli (P6B1-03 vakası '
        'dondurma ANINDAN sonrasını konu alır)')
    tol = rb['inputs']['tol_res']
    yayim = float(np.asarray(rb['residual_history'])[-1])
    sema = _sema_kalintisi(rb, izgara)
    assert not rb['converged'] or sema < tol, (
        f"converged=True yayımlandı (kalıntı {yayim:.4e} < tol {tol:g}) ama "
        f"alanın ŞEMA kalıntısı {sema:.4e} = tolun {sema / tol:.4g} katı; "
        f"yayımlanan sayı {sema / yayim:.4g}× küçük — donmuş operatörün "
        f"kalıntısı. Cümle: {rb['convergence_basis']}")


# ÇEVİRİ (ÖH D15 birleşme düzeltmesi) — BORÇ İMİ KALKTI.
# Bu bekçi P6B1-08 borcunu xfail(strict) ile taşıyordu;
# imin kendi metni "onarım gelince bu im KALKAR" diyordu.
# Kusur ÖH D15 cfd-picard (OH-Z5-14) tarafından
# ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test
# GEÇİYOR ve strict im XPASS ile kırmızı veriyordu. İm
# kaldırıldı; iddia artık CANLI bekçidir — onarım geri
# alınırsa burası kırmızı verir.
#
# ÜRÜNDEKİ KANIT: hrma/cfd/steady.py:726 aynı onarım bloğu (P6B1-08
# dahil)
#
# KALKAN İMİN GEREKÇESİ (kayıt için): ÖH defter P6B1-08 — ürün kusuru:
# örtük yolda hüküm, 25 iterasyonluk Picard penceresinin bayat eğimli
# kalıntısını okuyor. Faz B ürün onarımı YAPMAZ; bekçi borç imiyle
# yazılır, onarım dalgası bu imi kaldırır.
def test_ortuk_hukum_bayat_pencerenin_kalintisini_okuyor(bayat_pencere,
                                                         izgara):
    """Dondurma ATEŞLEMEDEN de hüküm bayat sayıya dayanabiliyor.

    ÖH Faz B-4 — defter P6B1-08 (orta). P6B1-03'ten AYRI mekanizma:
    burada sınırlayıcı hiç donmuyor (``limiter_frozen_at_iter is None``),
    ayrışmayı tek başına eğim tazeleme periyodu (25) üretiyor. Ölçüm
    (2026-08-27, bu lüle 60×12, ``BAYAT_AYAR``): 1449 iterasyon,
    yayımlanan 9,8538e-07 < tol 1e-6 → ``converged=True``; alanın ŞEMA
    kalıntısı 9,7286e-05, yani tolun **97,3 katı** (oran 98,7×).

    Aynı ayarlarla AÇIK yol kontrolü (ölçüldü): 4920 iterasyon,
    yayımlanan = şema (oran 1,000000×) — yani kusur örtük yola özgüdür,
    vakanın kendisine değil.
    """
    r = bayat_pencere
    assert r['limiter_frozen_at_iter'] is None, (
        'bu vakada dondurma ateşledi — P6B1-08 izolasyonu bozuldu, '
        'BAYAT_AYAR yeniden kalibre edilmeli')
    assert r['converged'] is True, (
        'vaka yakınsadı hükmü vermiyor — bekçi yeniden kalibre edilmeli')
    tol = r['inputs']['tol_res']
    yayim = float(np.asarray(r['residual_history'])[-1])
    sema = _sema_kalintisi(r, izgara)
    assert sema < tol, (
        f"converged=True yayımlandı (kalıntı {yayim:.4e} < tol {tol:g}) ama "
        f"alanın ŞEMA kalıntısı {sema:.4e} = tolun {sema / tol:.4g} katı "
        f"(oran {sema / yayim:.4g}×) — hüküm bayat eğimli pencerenin "
        f"sayısını okudu. Cümle: {r['convergence_basis']}")


def test_acik_yol_plato_beyani_degismedi(cift_muscl):
    """Açık yolun dondurma beyan sözleşmesi el değmemiş: bu vakada açık
    yol HİÇ dondurmaz (kalibrasyon: donma=None) ve 'oturma tespiti'
    cümlesi açık yol beyanında GÖRÜNEMEZ."""
    ra, _ = cift_muscl
    assert ra['limiter_frozen_at_iter'] is None
    assert 'oturma tespiti' not in ra['convergence_basis']


# ---------------------------------------------------------------------------
# V3 — eğim-dondurma TETİĞİ hükümden AYRI (dairesel kilidin kapanışı)
#
# Parti 38 ölçümü: tetik ile hüküm aynı settle_tol'u paylaşıyordu; KAPI
# vakasında (viskoz 192×48) tazeleme gevelemesi bandı 1,008e-05 tabanına
# kilitleyince tetik HİÇ ateşleyemiyordu (dondurma tam da o gevelemeyi
# gidermek için varken). V3: tetiğin AYRI, beyanlı eşiği var
# (freeze_settle_tol); hüküm aritmetiği (_settle_band) TEK yerde kaldı.
# Varsayılanın None (= settle_tol, tarihsel bit-özdeş) SEÇİLME sebebi
# ölçülmüş kök zehirlenmesidir (bu ızgarada freeze=1e-4 varsayılan olsaydı
# donma 4253 → 560'a çekilir, açık↔örtük alan bandı 5,41e-08 → 5,03e-04'e,
# debi farkı 1,42e-11 → 1,48e-06'ya bozulurdu — ÖLÇÜLDÜ, künye
# steady.DEFAULT_FREEZE_SETTLE_TOL).
# ---------------------------------------------------------------------------

def test_tetik_hukumden_bagimsiz_atesler(izgara):
    """(a) Tetik, hüküm erişilmezken ateşleyebilir (dairesel kilit yok).

    ÖLÇÜLDÜ (bu ızgara, MUSCL örtük, 800 iter): settle_tol=1e-14 (hüküm
    kasıtla erişilmez) + freeze_settle_tol=1e-4 → donma 560. iterasyonda,
    converged=False, kalıntı 1,22e-08. AYNI ayar tetik eşiği verilmeden
    (varsayılan = settle_tol = 1e-14) koşulursa donma HİÇ olmaz — dairesel
    kilit geri gelirse (tetik yeniden hüküm eşiğini okursa) bu bekçi
    kırmızıya düşer (mutasyon M4 kanıtı docstring'de).
    """
    ayrik = solve_steady_axisym(izgara, max_iters=800,
                                time_integrator='line_implicit_j',
                                settle_tol=1e-14, freeze_settle_tol=1e-4,
                                **_ORTAK)
    assert ayrik['converged'] is False, (
        'vaka 800 iterasyonda 1e-14 bandına oturamaz — oturduysa vaka '
        'değişmiş, bekçi yeniden kalibre edilmeli')
    assert ayrik['limiter_frozen_at_iter'] is not None, (
        'tetik, hüküm erişilmezken ateşleyemedi — tetik/hüküm ayrımı '
        '(dairesel kilit kapanışı) geri açılmış')
    kilitli = solve_steady_axisym(izgara, max_iters=800,
                                  time_integrator='line_implicit_j',
                                  settle_tol=1e-14, **_ORTAK)
    assert kilitli['limiter_frozen_at_iter'] is None, (
        'varsayılan (tetik = hüküm eşiği) bu vakada ateşlememeliydi — '
        'varsayılan davranış değişmiş')


def test_tetik_esigi_beyanda_yayimlanir(izgara, cift_muscl):
    """(b) Tetik eşiği koşum beyanında: inputs + dondurma gerekçesi."""
    r = solve_steady_axisym(izgara, max_iters=800,
                            time_integrator='line_implicit_j',
                            settle_tol=1e-14, freeze_settle_tol=1e-4,
                            **_ORTAK)
    assert r['inputs']['freeze_settle_tol'] == 1e-4
    assert 'freeze_settle_tol=0.0001' in r['convergence_basis'], (
        'dondurma gerekçesi tetik eşiğini ADIYLA söylemiyor')
    # Varsayılanda etkin eşik = settle_tol ve BEYAN bunu yankılar
    _, rb = cift_muscl
    assert rb['inputs']['freeze_settle_tol'] == rb['inputs']['settle_tol']


def test_tetik_varsayilani_bit_ozdes(izgara):
    """None (varsayılan) ↔ freeze_settle_tol=settle_tol BİT-ÖZDEŞ.

    Ayrımın kendisi varsayılan yolu tek bitte bile değiştiremez (ölçüldü:
    kalıntı izleri array_equal) — tarihsel kalibrasyonların (donma 4253,
    4452 it) taşıyıcısı budur.
    """
    ra = solve_steady_axisym(izgara, max_iters=300,
                             time_integrator='line_implicit_j', **_ORTAK)
    rb = solve_steady_axisym(izgara, max_iters=300,
                             time_integrator='line_implicit_j',
                             freeze_settle_tol=1e-9, **_ORTAK)
    assert np.array_equal(ra['residual_history'], rb['residual_history'])
    assert ra['inputs']['freeze_settle_tol'] == 1e-9


def test_tetik_gecersiz_esik_reddi(izgara):
    """Tetik eşiği kapılıdır: pozitif/sonlu olmayan değer ADIYLA reddedilir."""
    for bozuk in (0.0, -1e-4, float('nan'), float('inf')):
        with pytest.raises(ValueError, match='freeze_settle_tol'):
            solve_steady_axisym(izgara, time_integrator='line_implicit_j',
                                freeze_settle_tol=bozuk, **_ORTAK)


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
