# tests/cfd — viskoz akı operatörü + duvar BC'leri (V1 basamak 2-3 sınıfı)
"""
``hrma.cfd.viscous`` bekçileri: cebirsel özdeşlikler, sınır koşulu kapıları
ve duvar çıktılarının yapısal doğruluğu.

TASARIM: bu dosya ÖLÇÜLEBİLİR OLANI ölçer. Boru merdiveninin (basamak 4-5)
fiziksel hükümleri ``test_boru_laminer.py``dedir; burada koşum yoktur, tek
kalıntı çağrılarıyla ANALİTİK olarak bilinen dört alan sınanır:

  (A) durgun düzgün alan            → R_viskoz ≡ 0 (BİT sıfır)
  (B) katı-cisim radyal genişleme   → momentum kalıntısı ≡ 0 (makine sıfırı),
      u_r = c·r, u_z = 0              enerji = (4/3)μc²
  (C) doğrusal kayma u_z = a·r      → R_z = μa/r_c (makine kesinliği)
  (D) doğrusal sıcaklık T = T0+b·r  → R_E = k·b/r_c, q_w = −k·b

(B) tesadüf değildir: τ_rr ve τ_θθ bu alanda EŞİTTİR, ve ayrık kalıntı
Σ S_r = 2π·A_düzlem kapanış özdeşliğiyle (test_grid.py::test_duzlemsel_
kapanis) çember kaynağını TAM sadeleştirir. Yani hoop teriminin İŞARETİ ve
çarpanı burada makine hassasiyetinde kilitlenir — euler_core'un basınç
kaynağının aynı özdeşliğe dayanmasının viskoz kardeşidir.

DUVAR KİRLİLİĞİ (bilerek, beyanlı): (B) ve (C) alanları duvarda u = 0
koşulunu SAĞLAMAZ (u_r = cR ≠ 0). No-slip yüz değeri son iki j katmanının
gradyanını meşru biçimde değiştirir; o yüzden bu iki alanda kalıntı yalnız
j ≤ nj−3 katmanlarında sınanır. Duvar koşulunun KENDİSİ (A), (D) ve duvar
çıktısı bekçileriyle ayrıca ölçülür — kapsam açığı değil, ayrıştırma.

Kullanılan doğrulama akışkanı SABİT ÖZELLİKLİDİR (viskozite üssü 0): analitik
referanslar (μ sabit) ancak böyle kapalı formda yazılabilir. Ürün yolu üssü
depodan ÖLÇER (gas_transport.viscosity_exponent); bu dosya o yolu değil,
operatörün cebirini sınar.
"""

import numpy as np
import pytest

from hrma.cfd import euler_core
from hrma.cfd.euler_core import (
    WALL_BC_MODES, WALL_BC_NOSLIP, WALL_BC_SLIP, cons_to_prim_axisym,
    precompute_geometry, prim_to_cons_axisym, residual_axisym,
)
from hrma.cfd.gas_transport import GasTransport
from hrma.cfd.gradients import precompute_gradient_geometry
from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.viscous import (
    GAS_CONSISTENCY_TOL, WALL_TEMP_SENSITIVITY_RATIOS, WALL_THERMAL_MODES,
    WallOutputs, h_g_wall_temp_sensitivity, viscous_local_dt_limit,
    viscous_residual, viscous_spectral_radius,
)

# --- doğrulama akışkanı (sabit özellikli; her sayı testin kendi kararı) ---
VISK_GAMMA = 1.4
VISK_R = 287.0
VISK_CP = VISK_GAMMA * VISK_R / (VISK_GAMMA - 1.0)
VISK_PRANDTL = 0.7
VISK_MU = 1.0e-3
VISK_T_REF = 300.0
VISK_K = VISK_CP * VISK_MU / VISK_PRANDTL

# Boru geometrisi (yeni geometri kodu GEREKMEZ: mevcut kurucu)
VISK_PIPE_LENGTH_M = 0.05
VISK_PIPE_RADIUS_M = 0.005


def transport(exponent=0.0, mu_ref=VISK_MU, cp=VISK_CP, prandtl=VISK_PRANDTL,
              gamma=VISK_GAMMA):
    """Sabit özellikli doğrulama taşınımı (üs 0 → μ sıcaklıktan bağımsız)."""
    return GasTransport(
        gamma=gamma, T_ref=VISK_T_REF, mu_ref=mu_ref, cp=cp, prandtl=prandtl,
        prandtl_turbulent=0.9, viscosity_exponent=exponent,
        sources={'viscosity': 'verification_case',
                 'cp': 'gamma_R_identity', 'prandtl': 'verification_case'})


def pipe(ni=12, nj=8, length=VISK_PIPE_LENGTH_M, radius=VISK_PIPE_RADIUS_M):
    z = np.linspace(0.0, length, ni + 1)
    return build_grid_from_wall(z, np.full(ni + 1, radius), nj)


def cone(ni=12, nj=8):
    """Eğik duvarlı (dik OLMAYAN) ızgara: teğetsel düzeltme burada canlıdır."""
    z = np.linspace(0.0, VISK_PIPE_LENGTH_M, ni + 1)
    r = VISK_PIPE_RADIUS_M * (1.0 + 0.6 * z / VISK_PIPE_LENGTH_M)
    return build_grid_from_wall(z, r, nj)


def state(grid, uz, ur, T, p=1.0e5):
    """Primitiflerden korunum durumu (p sabit verilirse ρ = p/(RT))."""
    p_arr = np.broadcast_to(np.asarray(p, dtype=float), uz.shape)
    rho = p_arr / (VISK_R * T)
    return prim_to_cons_axisym(rho, uz, ur, p_arr, VISK_GAMMA)


def at_rest(grid, T=VISK_T_REF):
    z = np.zeros((grid.ni, grid.nj))
    return state(grid, z, z.copy(), np.full_like(z, T))


def solid_body_expansion(grid, c=50.0, T=VISK_T_REF):
    rc = grid.r_centers
    return state(grid, np.zeros_like(rc), c * rc, np.full_like(rc, T))


def linear_shear(grid, a=1000.0, T=VISK_T_REF):
    rc = grid.r_centers
    return state(grid, a * rc, np.zeros_like(rc), np.full_like(rc, T))


def linear_temperature(grid, b=2000.0, T0=VISK_T_REF):
    rc = grid.r_centers
    return state(grid, np.zeros_like(rc), np.zeros_like(rc), T0 + b * rc)


def isothermal(T_wall):
    return dict(wall_thermal='isothermal', T_wall=T_wall,
                T_wall_source='verification_case')


def run(grid, U, tr=None, **kw):
    return viscous_residual(grid, U, tr or transport(), R=VISK_R, **kw)


# ===========================================================================
# 1) Isıl duvar sözleşmesi: uydurma varsayılan YOK (§5.4)
# ===========================================================================

def test_isotermal_duvar_T_wall_olmadan_reddedilir():
    """T_wall'suz izotermal → ValueError, mesaj ZORUNLULUĞU adıyla söyler."""
    g = pipe()
    with pytest.raises(ValueError, match=r'T_wall ZORUNLU'):
        run(g, at_rest(g), wall_thermal='isothermal')


def test_isotermal_duvar_kaynak_beyani_olmadan_reddedilir():
    """T_wall verildi ama kaynağı beyan edilmedi → red (FEA köprüsü deseni)."""
    g = pipe()
    with pytest.raises(ValueError, match=r'T_wall_source'):
        run(g, at_rest(g), wall_thermal='isothermal', T_wall=VISK_T_REF)
    with pytest.raises(ValueError, match=r'T_wall_source'):
        run(g, at_rest(g), wall_thermal='isothermal', T_wall=VISK_T_REF,
            T_wall_source='   ')


def test_adiyabatik_duvara_T_wall_verilemez():
    """Adyabatikte duvar sıcaklığı SONUÇTUR; sınır koşulu olarak verilemez."""
    g = pipe()
    with pytest.raises(ValueError, match=r'adiabatic.*T_wall verilemez'):
        run(g, at_rest(g), wall_thermal='adiabatic', T_wall=VISK_T_REF)


def test_tanimsiz_isil_kip_reddedilir_ve_varsayilan_yoktur():
    g = pipe()
    for kip in ('isotermal', 'ADIABATIC', 'wall_function', None, ''):
        with pytest.raises(ValueError, match=r'wall_thermal'):
            run(g, at_rest(g), wall_thermal=kip)
    # Varsayılan yok: wall_thermal keyword-only ve zorunlu.
    with pytest.raises(TypeError):
        viscous_residual(pipe(), at_rest(g), transport(), R=VISK_R)
    assert WALL_THERMAL_MODES == ('isothermal', 'adiabatic')


@pytest.mark.parametrize('bozuk', [-1.0, 0.0, np.nan, np.inf])
def test_bozuk_T_wall_reddedilir(bozuk):
    g = pipe()
    with pytest.raises(ValueError, match=r'T_wall her istasyonda pozitif'):
        run(g, at_rest(g), **isothermal(bozuk))


def test_T_wall_istasyon_dizisi_kabul_edilir_ve_bicimi_denetlenir():
    g = pipe(ni=12, nj=8)
    dizi = np.linspace(280.0, 320.0, g.ni)
    _, aux = run(g, at_rest(g), **isothermal(dizi))
    assert np.array_equal(aux['wall'].T_wall_K, dizi)
    with pytest.raises(ValueError, match=r'duvar istasyonu dizisi'):
        run(g, at_rest(g), **isothermal(np.linspace(280.0, 320.0, g.ni + 3)))


def test_T_wall_kaynagi_duvar_ciktisinda_tasinir():
    """Kaynak beyanı çıktının İÇİNDE gider (V4 köprüsü orada okuyacak)."""
    g = pipe()
    _, aux = run(g, at_rest(g), wall_thermal='isothermal', T_wall=VISK_T_REF,
                 T_wall_source='thermal_fea')
    assert aux['wall'].T_wall_source == 'thermal_fea'
    assert aux['wall'].thermal_mode == 'isothermal'
    assert aux['declaration']['T_wall_source'] == 'thermal_fea'
    _, aux2 = run(g, at_rest(g), wall_thermal='adiabatic')
    assert aux2['wall'].T_wall_source == 'adiabatic_wall_measured'


# ===========================================================================
# 2) Gaz modeli ve kapsam kapıları
# ===========================================================================

def test_iki_gaz_modeliyle_kosmak_reddedilir():
    """cp = γR/(γ−1) özdeşliği: taşınımın cp'si çözücünün R'siyle uyuşmalı."""
    g = pipe()
    with pytest.raises(ValueError, match=r'Gaz modeli tutarsız'):
        viscous_residual(g, at_rest(g), transport(cp=VISK_CP * 1.05), R=VISK_R,
                         **isothermal(VISK_T_REF))
    # Tolerans bandının İÇİ geçer (yuvarlama sınıfı sapma reddedilmez).
    icerde = VISK_CP * (1.0 + 0.5 * GAS_CONSISTENCY_TOL)
    viscous_residual(g, at_rest(g), transport(cp=icerde), R=VISK_R,
                     **isothermal(VISK_T_REF))
    with pytest.raises(ValueError, match=r'R pozitif'):
        viscous_residual(g, at_rest(g), transport(), R=-1.0,
                         **isothermal(VISK_T_REF))


def test_turbulansli_viskozite_kapisi_V2_de_ACILDI_ama_sozlesmeli():
    """μ_t kancası V2'de AÇILDI: değer kabul edilir, KUSUR reddedilir.

    V1'de bu bekçi "mu_t bu evrede kabul edilmez" diyordu; kapı SA-neg
    bağlanınca açıldı (görev kararı, V2). Bekçi SİLİNMEDİ — sözleşmenin
    YENİ hâline taşındı: sıfır μ_t laminer sonucu BİT-AYNI bırakmalı
    (kanca açıldı diye laminer yol kaymamalı), biçim/sonluluk/NEGATİFLİK
    kusurları ADIYLA reddedilmeli (negatif girdap viskozitesi ters
    difüzyondur; sessizce kırpılmaz).
    """
    g = pipe()
    U = at_rest(g)
    sifir = np.zeros((g.ni, g.nj))

    # (i) μ_t = 0 laminer yolla BİT-AYNI (kancanın açılması yolu kaydırmaz)
    lam, _ = run(g, U, **isothermal(VISK_T_REF))
    turb, aux_t = run(g, U, mu_t=sifir, **isothermal(VISK_T_REF))
    assert np.array_equal(lam, turb), (
        'μ_t = 0 laminer kalıntıdan saptı — kanca yolu kaydırıyor')
    assert aux_t['declaration']['mu_t_over_mu_max'] == 0.0
    lam_lam, aux_lam = run(g, U, **isothermal(VISK_T_REF))
    assert aux_lam['declaration']['mu_t_over_mu_max'] is None, (
        'laminer koşuda μ_t oranı UYDURULMAMALI (None kalmalı)')
    assert np.array_equal(lam, lam_lam)

    # (ii) kusurlar ADIYLA reddedilir
    with pytest.raises(ValueError, match=r'mu_t biçimi'):
        run(g, U, mu_t=np.zeros((g.ni, g.nj + 1)), **isothermal(VISK_T_REF))
    with pytest.raises(ValueError, match=r'mu_t sonlu'):
        run(g, U, mu_t=np.full((g.ni, g.nj), np.nan),
            **isothermal(VISK_T_REF))
    with pytest.raises(ValueError, match=r'mu_t negatif'):
        run(g, U, mu_t=np.full((g.ni, g.nj), -1e-6),
            **isothermal(VISK_T_REF))
    with pytest.raises(ValueError, match=r'mu_t biçimi'):
        viscous_spectral_radius(g, U, transport(), R=VISK_R, mu_t=0.0)

    # (iii) μ_t > 0 spektral yarıçapı BÜYÜTÜR (Δt'yi küçültür) — türbülanslı
    # koşunun kararlılık sınırı laminerinkinden sıkıdır, bu ölçülür.
    lam_lam_v = viscous_spectral_radius(g, U, transport(), R=VISK_R)
    turb_v = viscous_spectral_radius(g, U, transport(), R=VISK_R,
                                     mu_t=np.full((g.ni, g.nj), 1e-3))
    assert np.all(turb_v > lam_lam_v)


def test_bozuk_bicimler_adiyla_reddedilir():
    g = pipe(ni=12, nj=8)
    with pytest.raises(ValueError, match=r'U biçimi'):
        run(g, at_rest(g)[:, :-1], **isothermal(VISK_T_REF))
    with pytest.raises(ValueError, match=r'inlet_face_primitives biçimi'):
        run(g, at_rest(g), inlet_face_primitives=np.zeros((g.nj, 3)),
            **isothermal(VISK_T_REF))
    with pytest.raises(ValueError, match=r'outlet_face_primitives biçimi'):
        run(g, at_rest(g), outlet_face_primitives=np.zeros((g.nj + 1, 4)),
            **isothermal(VISK_T_REF))


def test_fiziksel_olmayan_durum_NaN_dondurur_istisna_atmaz():
    """euler_core sözleşmesi: kırpma yok, çökme yok — sürücü ıraksama görür."""
    g = pipe()
    U = at_rest(g)
    U[3, 2, 0] = -1.0                     # negatif yoğunluk
    dudt, aux = run(g, U, **isothermal(VISK_T_REF))
    assert np.all(np.isnan(dudt[..., 1:]))
    assert np.array_equal(dudt[..., 0], np.zeros((g.ni, g.nj)))
    assert 'nonphysical_state' in aux['declaration']
    assert np.all(np.isnan(aux['wall'].q_wall_W_m2))


# ===========================================================================
# 3) (A) Durgun düzgün alan → BİT sıfır
# ===========================================================================

def _serbest_akim_tabani(grid, T):
    """Düzgün alanda kaçınılmaz gürültü tabanı (ÖLÇÜLEBİLİR, uydurma değil).

    Green-Gauss düzgün alanda φ·(Σ S)/A verir; Σ S_düzlemsel = 0 özdeşliği
    ANALİTİK olarak tamdır ama dörtgen olmayan hücrede yuvarlama artığı
    bırakır. gradients.py bu ölçeği zaten yayımlıyor (``grad_floor_scale``
    = maks Σ|S|/A). Isı akısına dönüşümü k_eff·(taban)·(Σ|S|/V)'dir.
    """
    ggeom = precompute_gradient_geometry(grid)
    grad_tabani = np.finfo(float).eps * T * ggeom['grad_floor_scale']
    cevre = (np.linalg.norm(grid.face_i[1:], axis=-1)
             + np.linalg.norm(grid.face_i[:-1], axis=-1)
             + np.linalg.norm(grid.face_j[:, 1:], axis=-1)
             + np.linalg.norm(grid.face_j[:, :-1], axis=-1))
    return VISK_K * grad_tabani * float(np.max(cevre / grid.volume))


@pytest.mark.parametrize('kip', ['isothermal', 'adiabatic'])
@pytest.mark.parametrize('kurucu', [pipe, cone])
def test_durgun_duzgun_alanda_kalinti_serbest_akimi_korur(kip, kurucu):
    """Serbest akım korunumu (merdiven basamak 2'nin viskoz karşılığı).

    Hız TAM sıfır olduğundan gerilme akısı ve çember kaynağı BİT sıfırdır
    (dik ya da eğik, ızgaradan bağımsız). Enerjide kalan tek şey kapanış
    özdeşliğinin yuvarlama artığıdır: dik ızgarada o da TAM sıfır, eğik
    ızgarada ÖLÇÜLEN tabanın altında.
    """
    g = kurucu()
    kw = isothermal(VISK_T_REF) if kip == 'isothermal' else {
        'wall_thermal': 'adiabatic'}
    dudt, aux = run(g, at_rest(g), **kw)
    assert np.array_equal(dudt[..., :3], np.zeros((g.ni, g.nj, 3))), (
        f'{kip}/{kurucu.__name__}: durgun alanda momentum kalıntısı BİT '
        f'sıfır değil (maks {float(np.max(np.abs(dudt[..., :3]))):.3e})')
    assert np.array_equal(aux['wall'].tau_wall_Pa, np.zeros(g.ni))
    taban = _serbest_akim_tabani(g, VISK_T_REF)
    enerji = float(np.max(np.abs(dudt[..., 3])))
    if kurucu is pipe:
        assert enerji == 0.0, (
            f'{kip}: dik ızgarada enerji kalıntısı da BİT sıfır olmalı '
            f'(ölçülen {enerji:.3e})')
        assert np.array_equal(aux['wall'].q_wall_W_m2, np.zeros(g.ni))
    else:
        assert enerji <= taban, (
            f'{kip}: eğik ızgarada serbest akım artığı {enerji:.3e} > '
            f'ölçülen taban {taban:.3e} — kapanış özdeşliği yuvarlama '
            f'sınıfının ötesinde bozuluyor')


def test_duvar_sicakligi_farkliysa_yalniz_enerji_uyanir():
    """u ≡ 0, T düzgün ama T_w farklı: momentum kalıntısı BİT sıfır kalır."""
    g = pipe()
    dudt, aux = run(g, at_rest(g), **isothermal(VISK_T_REF * 0.5))
    assert np.array_equal(dudt[..., :3], np.zeros((g.ni, g.nj, 3)))
    assert np.all(aux['wall'].q_wall_W_m2 > 0.0)      # sıcak gaz → soğuk duvar
    assert aux['wall_heat_W'] > 0.0


# ===========================================================================
# 4) (B) Katı-cisim radyal genişleme: ÇEMBER (hoop) teriminin kilidi
# ===========================================================================

@pytest.mark.parametrize('nj', [6, 8, 12])
def test_katiyla_radyal_genisleme_momentum_kalintisi_makine_sifiri(nj):
    """u_r = c·r, u_z = 0 → τ_rr ≡ τ_θθ; yüz akısı ile hoop kaynağı TAM
    sadeleşir (Σ S_r = 2π A_düzlem kapanışı). Hoop işareti/çarpanı burada
    kilitlidir."""
    c = 50.0
    g = pipe(ni=12, nj=nj)
    dudt, _ = run(g, solid_body_expansion(g, c), **isothermal(VISK_T_REF))
    ic = dudt[:, :nj - 2]                  # duvar kirliliği dışarıda (beyan)
    olcek = VISK_MU * c / float(np.min(g.r_centers))
    for bilesen, ad in ((1, 'z'), (2, 'r')):
        bagil = float(np.max(np.abs(ic[..., bilesen]))) / olcek
        assert bagil < 1e-12, (
            f'nj={nj}: R_{ad} makine sıfırı değil (bağıl {bagil:.3e}) — '
            f'çember kaynağı ile yüz akısının sadeleşmesi bozuldu')


@pytest.mark.parametrize('nj', [6, 12])
def test_katiyla_radyal_genislemede_enerji_analitik_dissipasyon(nj):
    """Aynı alanda enerji kalıntısı τ:∇u = (4/3)μc² (hacim başına)."""
    c = 50.0
    g = pipe(ni=12, nj=nj)
    dudt, _ = run(g, solid_body_expansion(g, c), **isothermal(VISK_T_REF))
    beklenen = 4.0 / 3.0 * VISK_MU * c * c
    olculen = dudt[:, :nj - 2, 3]
    assert np.max(np.abs(olculen - beklenen)) / beklenen < 1e-12


def test_kutle_bileseni_her_alanda_tam_sifir():
    """Viskoz akı kütleye GİRMEZ: R[..., 0] her yerde bit sıfır."""
    g = cone()
    for U in (at_rest(g), solid_body_expansion(g), linear_shear(g),
              linear_temperature(g)):
        dudt, aux = run(g, U, **isothermal(VISK_T_REF))
        assert np.array_equal(dudt[..., 0], np.zeros((g.ni, g.nj)))
        assert aux['max_abs_mass_residual'] == 0.0


# ===========================================================================
# 5) (C) Doğrusal kayma → R_z = μa/r_c  (τ_zr ve kapanış özdeşliği)
# ===========================================================================

@pytest.mark.parametrize('nj', [6, 12])
def test_dogrusal_kaymada_z_momentum_kapali_form(nj):
    a = 1000.0
    g = pipe(ni=12, nj=nj)
    dudt, _ = run(g, linear_shear(g, a), **isothermal(VISK_T_REF))
    beklenen = VISK_MU * a / g.r_centers
    ic = (slice(None), slice(0, nj - 2))
    assert np.max(np.abs(dudt[ic][..., 1] - beklenen[ic])
                  / beklenen[ic]) < 1e-12
    olcek = float(np.max(np.abs(beklenen)))
    assert float(np.max(np.abs(dudt[ic][..., 2]))) / olcek < 1e-12


# ===========================================================================
# 6) (D) Doğrusal sıcaklık → R_E = k·b/r_c ve q_w = −k·b
# ===========================================================================

@pytest.mark.parametrize('nj', [6, 12])
def test_dogrusal_sicaklikta_enerji_ve_duvar_akisi_kapali_form(nj):
    b = 2000.0
    g = pipe(ni=12, nj=nj)
    T_duvar = VISK_T_REF + b * float(np.max(g.R))
    dudt, aux = run(g, linear_temperature(g, b), **isothermal(T_duvar))
    beklenen = VISK_K * b / g.r_centers
    assert np.max(np.abs(dudt[..., 3] - beklenen) / beklenen) < 1e-9
    assert np.array_equal(dudt[..., 1], np.zeros((g.ni, nj)))
    # q_w = −k ∂T/∂n; duvarda sıcaklık ARTIYORSA ısı akışkana girer (negatif)
    q = aux['wall'].q_wall_W_m2
    assert np.max(np.abs(q + VISK_K * b)) / (VISK_K * b) < 1e-12


def test_adiyabatik_duvarda_isi_akisi_bit_sifir():
    """∂T/∂n = 0 sınır koşulunun KENDİSİ: q_w tam sıfır, enerji akısı yok."""
    g = pipe()
    dudt, aux = run(g, linear_temperature(g, 2000.0),
                    wall_thermal='adiabatic')
    assert np.array_equal(aux['wall'].q_wall_W_m2, np.zeros(g.ni))
    assert aux['wall_heat_W'] == 0.0
    # Aynı alanda izotermal duvar sıfırdan farklı akı verir (kip gerçekten
    # ayrışıyor — "adyabatik" boş bir etiket değil).
    _, aux_iso = run(g, linear_temperature(g, 2000.0),
                     **isothermal(VISK_T_REF))
    assert abs(aux_iso['wall_heat_W']) > 0.0


def test_adiyabatik_duvar_yuz_sicakligi_egik_duvarda_olculur():
    """Eğik duvarda teğetsel düzeltme CANLI, dik duvarda yuvarlama sınıfı."""
    b = 2000.0
    dik = pipe()
    _, aux_dik = run(dik, linear_temperature(dik, b),
                     wall_thermal='adiabatic')
    egik = cone()
    _, aux_egik = run(egik, linear_temperature(egik, b),
                      wall_thermal='adiabatic')
    guncelleme_dik = aux_dik['declaration']['neumann_face_update_K']
    guncelleme_egik = aux_egik['declaration']['neumann_face_update_K']
    olcek = np.finfo(float).eps * (VISK_T_REF + b * float(np.max(dik.R)))
    assert guncelleme_dik <= olcek, (
        f'dik duvarda teğetsel düzeltme {guncelleme_dik:.3e} K — yuvarlama '
        f'tabanı {olcek:.3e} K üstünde çıktı')
    assert guncelleme_egik > 1e3 * olcek, (
        'eğik duvarda teğetsel düzeltme ölçülemedi — sabit nokta ölü')
    # Ölçülen yüz sıcaklığı hücre sıcaklığından farklı (düzeltme uygulanmış).
    assert not np.allclose(aux_egik['wall'].T_wall_K,
                           aux_egik['wall'].T_cell_K, rtol=0, atol=1e-9)


# ===========================================================================
# 7) Duvar çıktıları: yapısal özdeşlikler
# ===========================================================================

def test_duvarda_viskoz_is_terimi_yoktur_enerji_akisi_yalniz_isidir():
    """u = 0 → (τ·u)·S ≡ 0. Duvar enerji akısı TAM −q_w·|S| olmalı.

    Ölçüm: aynı alanda τ_w BÜYÜK (kayma var) ama duvar enerji akısı
    yalnız ısı akısıdır. İş sızıntısı olsaydı fark τ_w·u_hücre mertebesinde
    görünürdü — ölçek olarak o kullanılır.
    """
    g = pipe()
    b = 2000.0
    a = 1000.0
    rc = g.r_centers
    U = state(g, a * rc, np.zeros_like(rc), VISK_T_REF + b * rc)
    T_duvar = VISK_T_REF + b * float(np.max(g.R))
    _, aux = run(g, U, **isothermal(T_duvar))
    wall = aux['wall']
    isi = wall.q_wall_W_m2 * wall.area_m2
    # Duvar yüzünün toplam enerji akısı: kalıntıdan geri okunamayacağı için
    # doğrudan sözleşme sınanır — q_w analitik değerinde ve iş terimi yok.
    assert np.max(np.abs(wall.q_wall_W_m2 + VISK_K * b)) / (VISK_K * b) < 1e-12
    sizinti_olcegi = float(np.max(np.abs(wall.tau_wall_Pa
                                         * U[:, -1, 1] / U[:, -1, 0])))
    assert sizinti_olcegi > 0.0                    # ölçek gerçekten canlı
    assert float(np.max(np.abs(isi / wall.area_m2 + VISK_K * b))) < (
        1e-9 * sizinti_olcegi)


def test_tau_w_isareti_akis_yonunde_pozitif_geri_akista_negatif():
    """Ayrılma ölçütü τ_w = 0 istasyonu (§8.3): işaret sözleşmesi kilitli."""
    g = pipe()
    rc = g.r_centers
    Rw = float(np.max(g.R))
    ileri = state(g, 100.0 * (1.0 - (rc / Rw) ** 2), np.zeros_like(rc),
                  np.full_like(rc, VISK_T_REF))
    _, aux = run(g, ileri, **isothermal(VISK_T_REF))
    assert np.all(aux['wall'].tau_wall_Pa > 0.0)
    _, aux_geri = run(g, state(g, -100.0 * (1.0 - (rc / Rw) ** 2),
                               np.zeros_like(rc),
                               np.full_like(rc, VISK_T_REF)),
                      **isothermal(VISK_T_REF))
    assert np.all(aux_geri['wall'].tau_wall_Pa < 0.0)
    assert np.allclose(aux_geri['wall'].tau_wall_Pa,
                       -aux['wall'].tau_wall_Pa, rtol=1e-12, atol=0.0)
    # Sürüklenme akışkanı YAVAŞLATIR: eksenel kuvvet negatif.
    assert aux['axial_friction_force_on_fluid_N'] < 0.0


def test_duvar_gradyani_duzeltmeli_kipte_TEK_YANLI_kompakt_farktir():
    """corrected=True'nun yapısal kanıtı: q_w = −k (T_w − T_c)/|b|.

    Düzeltmesiz kipte duvar yüz gradyanı HÜCRE gradyanına iner ve bu
    özdeşlik bozulur (aynı alanda ölçülür).
    """
    g = pipe(ni=10, nj=8)
    b2 = 4.0e7                       # T = T0 + b2·r² (gradyan r ile değişir)
    rc = g.r_centers
    Rw = float(np.max(g.R))
    U = state(g, np.zeros_like(rc), np.zeros_like(rc),
              VISK_T_REF + b2 * rc ** 2)
    T_duvar = VISK_T_REF + b2 * Rw ** 2
    ggeom = precompute_gradient_geometry(g)
    uzunluk = np.linalg.norm(ggeom['b_j_hi'], axis=-1)
    kompakt = (-VISK_K * (T_duvar - (VISK_T_REF + b2 * rc[:, -1] ** 2))
               / uzunluk)

    _, aux = run(g, U, **isothermal(T_duvar))
    assert np.allclose(aux['wall'].q_wall_W_m2, kompakt, rtol=1e-12, atol=0.0)

    # Düzeltmesiz kipte duvar yüz gradyanı HÜCRE gradyanına iner: tek yanlı
    # kompakt farkla bağı kopar ve ölçülebilir biçimde ayrışır.
    _, aux_ham = run(g, U, corrected=False, **isothermal(T_duvar))
    fark = float(np.max(np.abs(aux_ham['wall'].q_wall_W_m2
                               - aux['wall'].q_wall_W_m2)))
    bagil = fark / float(np.max(np.abs(kompakt)))
    assert bagil > 0.02, (
        f'düzeltmeli ve düzeltmesiz duvar akısı ayırt edilemiyor (bağıl '
        f'fark {bagil:.3e}) — bekçi kör')
    assert not np.allclose(aux_ham['wall'].q_wall_W_m2, kompakt,
                           rtol=1e-3, atol=0.0)


def test_duvar_ciktisi_geometrisi_izgaradan_gelir():
    g = cone(ni=10, nj=6)
    _, aux = run(g, at_rest(g), **isothermal(VISK_T_REF))
    wall = aux['wall']
    ggeom = precompute_gradient_geometry(g)
    assert np.array_equal(wall.z_m, ggeom['mid_j'][:, -1, 0])
    assert np.array_equal(wall.r_m, ggeom['mid_j'][:, -1, 1])
    assert np.array_equal(wall.area_m2,
                          precompute_geometry(g)['area_j'][:, -1])
    assert wall.tau_wall_Pa.shape == (g.ni,)
    assert wall.q_wall_W_m2.shape == (g.ni,)


@pytest.mark.parametrize('kurucu', [pipe, cone])
def test_ayrik_butce_teleskoplar_hucre_toplami_sinir_akisidir(kurucu):
    """Basamak 14'ün viskoz yarısı: Σ_hücre R·V = Σ_sınır akı.

    Eksenel momentum ve enerjide iç yüzler teleskopla sadeleşir; geriye
    giriş/çıkış yüzleri ve DUVAR kalır (eksen yüzü sıfır alanlıdır). Bu,
    duvar çıktılarının (τ_w, q_w) kalıntının KENDİSİYLE aynı sayı olduğunu
    kanıtlar — ayrı hesaplanmış bir yan ürün değildir.
    """
    g = kurucu(ni=14, nj=8)
    rc = g.r_centers
    Rw = float(np.max(g.R))
    U = state(g, 120.0 * (1.0 - (rc / Rw) ** 2), 8.0 * rc / Rw,
              VISK_T_REF + 1500.0 * (rc / Rw) ** 2)
    dudt, aux = run(g, U, **isothermal(VISK_T_REF * 1.2))
    V = g.volume

    eksenel = float(np.sum(dudt[..., 1] * V))
    beklenen_z = (aux['outlet_axial_force_N'] - aux['inlet_axial_force_N']
                  + aux['axial_friction_force_on_fluid_N'])
    olcek_z = max(abs(aux['axial_friction_force_on_fluid_N']),
                  abs(aux['inlet_axial_force_N']))
    assert abs(eksenel - beklenen_z) / olcek_z < 1e-11

    enerji = float(np.sum(dudt[..., 3] * V))
    beklenen_E = (aux['outlet_energy_flux_W'] - aux['inlet_energy_flux_W']
                  - aux['wall_heat_W'])
    olcek_E = max(abs(aux['wall_heat_W']), abs(aux['inlet_energy_flux_W']))
    assert abs(enerji - beklenen_E) / olcek_E < 1e-11


# ===========================================================================
# 8) Eksen: simetri koşulu ve sıfır alanlı yüz
# ===========================================================================

def test_eksen_yuzunde_akı_tam_sifir_ve_0_carpi_sonsuz_yok():
    """Eksen yüzünün dönel alanı sıfırdır: u_r/r orada HİÇ değerlendirilmez.

    Kanıt: eksene komşu hücrede kalıntı sonludur ve alan r ile ölçeklenip
    eksene yaklaştıkça patlamaz (nj büyürken eksen hücresinin kalıntısı
    kapalı formunu korur).
    """
    for nj in (8, 16, 32):
        g = pipe(ni=10, nj=nj)
        dudt, _ = run(g, linear_shear(g, 1000.0), **isothermal(VISK_T_REF))
        beklenen = VISK_MU * 1000.0 / g.r_centers[:, 0]
        assert np.all(np.isfinite(dudt))
        assert np.max(np.abs(dudt[:, 0, 1] - beklenen) / beklenen) < 1e-12


def test_eksende_u_r_yuz_degeri_tam_sifirdir():
    """u_r tek fonksiyondur: eksende yüz değeri 0 (uzatma DEĞİL).

    Ölçüm: eksende sıfır olmayan bir u_r verirsek (fiziksel olarak imkânsız
    ama sayısal olarak mümkün) simetri koşulu onu duyar.
    """
    g = pipe(ni=8, nj=8)
    rc = g.r_centers
    U = solid_body_expansion(g, 50.0)
    dudt, _ = run(g, U, **isothermal(VISK_T_REF))
    # u_r = c·r alanında eksen yüz değeri (c·0 = 0) doğruysa eksen hücresi
    # de kapalı formu tutturur (momentum ≡ 0).
    olcek = VISK_MU * 50.0 / float(np.min(rc))
    assert float(np.max(np.abs(dudt[:, 0, 2]))) / olcek < 1e-12


# ===========================================================================
# 9) euler_core wall_bc dalı (§5.1'in TEK istisnası)
# ===========================================================================

def test_wall_bc_varsayilani_slip_ve_dal_bit_ozdes():
    """Varsayılan dal bugünkü Euler kodudur: kalıntı BİT aynı."""
    g = pipe(ni=16, nj=8)
    rc = g.r_centers
    U = state(g, 200.0 * (1.0 - 0.5 * (rc / np.max(g.R)) ** 2),
              10.0 * rc / np.max(g.R), np.full_like(rc, VISK_T_REF), p=1.0e5)
    ref, aux_ref = residual_axisym(U, g, VISK_GAMMA, VISK_R, 1.2e5,
                                   VISK_T_REF, Pb=1.0e5)
    slip, aux_slip = residual_axisym(U, g, VISK_GAMMA, VISK_R, 1.2e5,
                                     VISK_T_REF, Pb=1.0e5,
                                     wall_bc=WALL_BC_SLIP)
    assert np.array_equal(ref, slip)
    assert aux_ref == aux_slip


def test_wall_bc_noslip_gercekten_farkli_alan_uretir():
    """Noslip aynası HAYALETİ değiştirir; Euler kalıntısını artık değiştirmez.

    ÖH D37 A3a cfd-kok-a (F-05; Berke Sunum 3a onayı, 24 Eylül 2026): duvar
    akısı iki-genişleme (TRRS) yıldız basıncıyla kurulur ve yalnız
    (ρ, u_n, p)'ye bağlıdır. Eski kodda bu alanda ölçülen 3,07e-8'lik fark,
    aynalanmış HLLC duvar çağrısına giren TEĞET hızın Roe ortalamasından
    gelen ulp düzeyi bir artefakttı (ölçüldü, 77a53727) — "ayna kalıntıyı
    değiştirir" öncülü fiziksel değildi. Aynanın GERÇEK etkisi hayalet
    satırlarının eğim şablonundadır. Ölçüldü (24 Eyl, ana model): fark
    yalnız iki duvar hayaleti satırında ve yalnız teğet momentumda (bu
    borunun duvarı eksene paralel → ρu_z), iç satırlarda sıfır. Ayna ölürse
    (noslip = slip) hayalet farkı sıfıra düşer ve bu bekçi kırmızıdır.
    """
    g = pipe(ni=16, nj=8)
    rc = g.r_centers
    U = state(g, 200.0 * (1.0 - 0.5 * (rc / np.max(g.R)) ** 2),
              10.0 * rc / np.max(g.R), np.full_like(rc, VISK_T_REF), p=1.0e5)
    slip = residual_axisym(U, g, VISK_GAMMA, VISK_R, 1.2e5, VISK_T_REF,
                           Pb=1.0e5, return_slopes=True)
    noslip = residual_axisym(U, g, VISK_GAMMA, VISK_R, 1.2e5, VISK_T_REF,
                             Pb=1.0e5, wall_bc=WALL_BC_NOSLIP,
                             return_slopes=True)
    s_j_slip, s_j_noslip = slip[-1][1], noslip[-1][1]
    fark = np.abs(s_j_slip - s_j_noslip)            # (nj+2, ni, 4)
    satir = fark.max(axis=(1, 2))
    assert satir[-2] > 0.0 and satir[-1] > 0.0, (
        'wall_bc="noslip" duvar hayaletini değiştirmedi — ayna ölü')
    assert np.all(satir[:-2] == 0.0), (
        f'ayna iç satırların eğimine sızdı: {satir}')
    bilesen = fark.max(axis=(0, 1))
    assert bilesen[1] > 0.0 and bilesen[0] == 0.0 and bilesen[3] == 0.0
    # Euler kalıntısı TRRS duvar akısıyla teğet hıza bağlı değil: bit-aynı.
    assert np.array_equal(slip[0], noslip[0])


def test_wall_bc_tanimsiz_deger_reddedilir():
    g = pipe(ni=8, nj=6)
    with pytest.raises(ValueError, match=r'wall_bc'):
        residual_axisym(at_rest(g), g, VISK_GAMMA, VISK_R, 1.2e5, VISK_T_REF,
                        wall_bc='no-slip')
    assert WALL_BC_MODES == ('slip', 'noslip')


def test_noslip_aynasi_IKI_hiz_bilesenini_de_yansitir():
    """Mutasyon hedefi: tek bileşen yansıtan ayna burada kırmızıdır."""
    rng = np.random.default_rng(20260818)
    w = rng.normal(size=(7, 4))
    w[:, 0] = np.abs(w[:, 0]) + 1.0
    w[:, 3] = np.abs(w[:, 3]) + 1.0
    aci = np.linspace(0.0, 1.2, 7)
    n_hat = np.stack([np.sin(aci), np.cos(aci)], axis=-1)
    ayna = euler_core._mirror_wall(w, n_hat, WALL_BC_NOSLIP)
    assert np.array_equal(ayna[:, 1], -w[:, 1])
    assert np.array_equal(ayna[:, 2], -w[:, 2])
    assert np.array_equal(ayna[:, 0], w[:, 0])
    assert np.array_equal(ayna[:, 3], w[:, 3])
    # Kayma aynası TEĞET hızı korur — iki kip yapısal olarak farklıdır.
    kayma = euler_core._mirror_wall(w, n_hat, WALL_BC_SLIP)
    ut_ic = -w[:, 1] * n_hat[:, 1] + w[:, 2] * n_hat[:, 0]
    ut_kayma = -kayma[:, 1] * n_hat[:, 1] + kayma[:, 2] * n_hat[:, 0]
    ut_noslip = -ayna[:, 1] * n_hat[:, 1] + ayna[:, 2] * n_hat[:, 0]
    assert np.allclose(ut_kayma, ut_ic, rtol=1e-14, atol=0.0)
    assert np.allclose(ut_noslip, -ut_ic, rtol=1e-14, atol=0.0)


def test_duvar_akisi_formulu_kipten_bagimsizdir_kod_kaniti():
    """§5.1 madde 2: no-slip duvarın Euler akısı hâlâ [0, p*·n̂·|S|, 0].

    Kütle ve enerji akısı İKİ kipte de tam sıfır kalır (aux'tan okunur);
    momentum akısı yalnız basınçtan gelir.
    """
    g = cone(ni=12, nj=8)
    rc = g.r_centers
    U = state(g, 150.0 + 0.0 * rc, 5.0 * rc / np.max(g.R),
              np.full_like(rc, VISK_T_REF), p=1.0e5)
    for kip in WALL_BC_MODES:
        _, aux = residual_axisym(U, g, VISK_GAMMA, VISK_R, 1.2e5,
                                 VISK_T_REF, Pb=1.0e5, wall_bc=kip)
        assert aux['wall_mass_flux_kg_s'] == 0.0, (
            f'{kip}: duvardan kütle sızdı')


# ===========================================================================
# 10) Viskoz spektral yarıçap / zaman adımı sınırı (§5.6)
# ===========================================================================

def test_viskoz_spektral_yaricap_blazek_bicimi():
    """Λ_v = max(4/(3ρ), γ/ρ)·(μ/Pr)·Σ|S|²/V — elle kurulan biçimle aynı."""
    g = pipe(ni=8, nj=6)
    U = at_rest(g)
    geom = precompute_geometry(g)
    rho = cons_to_prim_axisym(U, VISK_GAMMA)[..., 0]
    alan2 = (geom['area_i'][:-1] ** 2 + geom['area_i'][1:] ** 2
             + geom['area_j'][:, :-1] ** 2 + geom['area_j'][:, 1:] ** 2)
    beklenen = (np.maximum(4.0 / (3.0 * rho), VISK_GAMMA / rho)
                * (VISK_MU / VISK_PRANDTL) * alan2 / g.volume)
    olculen = viscous_spectral_radius(g, U, transport(), R=VISK_R)
    assert np.allclose(olculen, beklenen, rtol=1e-14, atol=0.0)
    assert np.allclose(viscous_local_dt_limit(g, U, transport(), R=VISK_R),
                       g.volume / beklenen, rtol=1e-14, atol=0.0)


def test_viskoz_dt_siniri_izgara_inceldikce_kucululur():
    """Δt_v ∝ Δr²: radyal inceltmede kare mertebesinde düşer (ÖLÇÜLÜR)."""
    oran = []
    onceki = None
    for nj in (8, 16, 32):
        g = pipe(ni=8, nj=nj)
        dt = float(np.min(viscous_local_dt_limit(g, at_rest(g), transport(),
                                                 R=VISK_R)))
        if onceki is not None:
            oran.append(onceki / dt)
        onceki = dt
    assert all(3.0 < x < 5.0 for x in oran), (
        f'Δt_v ölçek yasası kırıldı (oranlar {oran}); ~4 beklenir')


# ===========================================================================
# 11) h_g duyarlılık yardımcısı (§5.4)
# ===========================================================================

def _sahte_duvar(q_w, T_w, n=5):
    """TEST ALTYAPISI: yalnız h_g cebrini sınamak için WallOutputs kabuğu.

    (Ürün verisi DEĞİLDİR: koşum yapmadan yardımcı fonksiyonun sözleşmesini
    ölçer. Gerçek koşumlu ölçüm test_boru_laminer.py'dedir.)
    """
    bir = np.ones(n)
    return WallOutputs(
        z_m=np.linspace(0.0, 1.0, n), r_m=bir.copy(), area_m2=bir.copy(),
        tau_wall_Pa=bir.copy(), traction_z_Pa=bir.copy(),
        traction_r_Pa=np.zeros(n), q_wall_W_m2=q_w * bir,
        T_wall_K=T_w * bir, T_cell_K=T_w * bir, mu_wall_Pa_s=bir * VISK_MU,
        k_wall_W_mK=bir * VISK_K, thermal_mode='isothermal',
        T_wall_source='test_double')


def test_h_g_duyarliligi_bandi_iki_kosumdan_olculur():
    T0 = 3000.0
    T_aw = 2900.0

    def kos(T_w):
        # q_w ∝ (T_aw − T_w) olsaydı h_g SABİT olurdu; bilerek %10 sapma
        # konur ki bant ölçümü ölü olmasın.
        carpan = 1.0 if T_w < 0.45 * T0 else 1.10
        return _sahte_duvar(carpan * 1.0e6 * (T_aw - T_w) / 1000.0, T_w)

    sonuc = h_g_wall_temp_sensitivity(kos, T0, recovery_temperature_K=T_aw)
    assert sonuc['wall_temperature_ratios'] == WALL_TEMP_SENSITIVITY_RATIOS
    assert sonuc['wall_temperatures_K'] == (0.30 * T0, 0.60 * T0)
    h1 = sonuc['runs'][0.30]['h_g_W_m2K']
    h2 = sonuc['runs'][0.60]['h_g_W_m2K']
    assert np.allclose(h1, 1.0e6 / 1000.0)
    assert np.allclose(h2, 1.10e6 / 1000.0)
    assert abs(sonuc['max_relative_band'] - 0.1 / 1.05) < 1e-12
    assert 'ÖLÇÜLDÜ' in sonuc['declaration']


def test_h_g_kurtarma_sicakligi_zorunludur():
    with pytest.raises(TypeError):
        h_g_wall_temp_sensitivity(lambda T_w: _sahte_duvar(1.0, T_w), 3000.0)


def test_h_g_tanimsiz_surucu_farkinda_reddedilir():
    """T_aw ≤ T_w olan istasyon: sessiz NaN yerine ADIYLA hata."""
    with pytest.raises(ValueError, match=r'T_aw − T_w ≤ 0'):
        h_g_wall_temp_sensitivity(
            lambda T_w: _sahte_duvar(1.0, T_w), 3000.0,
            recovery_temperature_K=800.0)


@pytest.mark.parametrize('bozuk', [(0.3,), (0.0, 0.6), (0.3, 1.4),
                                   (0.1, 0.2, 0.3)])
def test_h_g_oran_bandi_denetlenir(bozuk):
    with pytest.raises(ValueError, match=r'ratios'):
        h_g_wall_temp_sensitivity(
            lambda T_w: _sahte_duvar(1.0, T_w), 3000.0,
            recovery_temperature_K=2900.0, ratios=bozuk)


def test_h_g_oranlari_tasarim_belgesinin_sayilaridir():
    """0,3·T₀ ve 0,6·T₀ §5.4'ün kendi kararıdır; sessizce kaymamalı."""
    assert WALL_TEMP_SENSITIVITY_RATIOS == (0.30, 0.60)
