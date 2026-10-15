"""ÖH Dalga-23 / fea-cfd aşama-2 bekçileri — CFD katmanı (parti P06 + OH).

Her bekçi, onardığı kusuru TERS-MUTASYONLA görmüş bir bekçidir; kanıt
``docs/scofield/raw/OH/D23/fea-cfd/a2/mutasyon.json`` dosyasındadır.
Ölçüm dosyaları: ``once.json`` (taban ağacı, ef527ae) ve ``sonra.json``
(bu ağaç), üreteci ``olcum.py``.

Kapsanan kalemler:
  OH-D15-07  künyede hükümsüzlüğün CİNSİ makine-okur
  OH-D19-16  ``_settle_band_phase`` pencere tanım alanı
  P6B1-10    kayma duvarı yıldız basıncı p* pozitiflik kapısı
  P6B1-11    TAM oturmuş bant 0,0 yayımlar (NaN "ölçülmedi" demektir)
  P6B2-03    Sutton bandı muafiyetinin KOŞULLU olduğunun beyanı
  P6B2-05    duvar mesafesi yüzdesi ile PAYDASI eşleşir
  P6B2-06    hata yolunun beyan ANAHTAR KÜMESİ sağlam yolunkini kapsar
  P6B2-07    girdi kapıları: sonlu olmayan/pozitif olmayan girdi ADIYLA red
  P6B2-08    γ > 1 kapısı (ADSIZ ZeroDivisionError yerine ADLI ValueError)
  P6B3-05    ``radial_geometry_block`` künyesi uca bağlılığı DOĞRU söyler
"""

import json
import math
import os

import numpy as np
import pytest

from hrma.cfd import steady, wall_output as wo
from hrma.cfd.euler_core import residual_axisym
from hrma.cfd.gas_transport import GasTransport
from hrma.cfd.grid_axisym import build_grid_from_wall, radial_geometry_block
from hrma.cfd.riemann import hllc_flux
from tests.support.kanit import kanit_gerekli


KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D23',
                     'fea-cfd', 'a2')


def _olcum(ad):
    with open(kanit_gerekli(os.path.join(KANIT, ad)), encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------- OH-D15-07

def test_OH_D15_07_kunye_hukumsuzlugun_CINSINI_tasir():
    """Plato ile "bütçe yetmedi" künyeden MAKİNE-OKUR ayrılır.

    Kusur: ``steady.py`` ``convergence_status`` ve ``convergence_plateau``
    alanlarını ZATEN yayımlıyordu; ``solution_declaration`` künyesi onları
    TAŞIMIYORDU (ölçüldü: 18 anahtar, ikisi de yok) ve tüketici platoyu
    ancak ``convergence_basis`` CÜMLESİNİ ayrıştırarak ayırabiliyordu.
    """
    res = {
        'converged': False,
        'convergence_basis': 'kalıntı platoda durdu',
        'convergence_status': 'plateau',
        'convergence_plateau': {'detected': True, 'plateau_residual': 1.2e-4},
        'iterations': 4000,
        'residual_history': [1e-3, 1.2e-4],
        'inputs': {'grid_ni': 120, 'grid_nj': 24},
        'viscous': {'wall': {}, 'y_plus_loop': {}},
    }
    k = wo.solution_declaration(res)
    assert k['convergence_status'] == 'plateau'
    assert k['convergence_plateau']['detected'] is True
    assert k['convergence_plateau']['plateau_residual'] == pytest.approx(1.2e-4)
    # Plato hükmün YERİNE GEÇMEZ
    assert k['converged'] is False
    assert 'convergence_status' in k['_basis']


def test_OH_D15_07_alan_yoksa_UYDURULMAZ():
    """Koşum alanı yayımlamadıysa cins BİLİNMİYOR — 'plato' sayılmaz."""
    res = {'converged': True, 'convergence_basis': 'kalıntı hedefin altında',
           'iterations': 900, 'residual_history': [1e-9],
           'inputs': {}, 'viscous': {'wall': {}, 'y_plus_loop': {}}}
    k = wo.solution_declaration(res)
    assert k['convergence_status'] is None
    assert k['convergence_plateau'] is None


# ---------------------------------------------------------------- OH-D19-16

def test_OH_D19_16_faz_bandi_pencere_TANIM_ALANINI_korur():
    """window < MIN_SETTLE_WINDOW → NaN; ham bantla AYNI eşik.

    Kusur: ``_settle_band``e konan kapı kardeşine konmamıştı. window=0'da
    ``hist[-0:]`` TÜM geçmişi döndürüyor ve ``len(hist) < 0`` koruması hiç
    ateşlemiyordu — ölçüldü, ham bant NaN derken faz bandı sayı
    yayımlıyordu (taban: 0,9998).
    """
    hist = [1.0, 2.0] * 5 + [1.0000, 1.0001] * 5
    for w in (0, 1):
        assert math.isnan(steady._settle_band(hist, w))
        assert math.isnan(steady._settle_band_phase(hist, w, 2)), (
            f'window={w} tanımsızdır; faz bandı sayı yayımlamamalı')
    assert math.isnan(steady._settle_band_phase([], 10, 2))
    # Tanım alanı İÇİNDE sayı üretmeye devam eder (kapı fazla kapatmadı)
    uzun = [1.0 + 1e-6 * (i % 3) for i in range(200)]
    assert not math.isnan(steady._settle_band_phase(uzun, 100, 4))


# ---------------------------------------------------------------- P6B1-11

def test_P6B1_11_TAM_oturmus_bant_SIFIR_yayimlar():
    """0,0 (en iyi ölçüm) ile NaN (ölçüm yok) bir daha aynı sayıya düşmez.

    Kusur: dönüş ``en_kotu > 0.0`` koşuluna bağlıydı; bütün fazların bandı
    tam 0,0 çıkan (yani MÜKEMMEL oturmuş) bir büyüklük, hiçbir fazın örnek
    eşiğini dolduramamasıyla AYNI NaN'ı üretiyordu — oysa işlevin kendi
    sözleşmesinde NaN "ölçülmedi" demektir.
    """
    sabit = [3.14159] * 40
    assert steady._settle_band_phase(sabit, 20, 4) == 0.0
    # Örnek eşiği dolmuyorsa hâlâ NaN (iki hâl AYRI kaldı)
    assert math.isnan(steady._settle_band_phase(sabit, 4, 4))
    # Sözleşme docstring'de de yazılı
    assert 'NaN DEĞİL 0,0' in steady._settle_band_phase.__doc__


# ---------------------------------------------------------------- P6B1-10

_GAMMA = 1.2


def _duvar_p_star(mach_n, gamma=_GAMMA, rho=1.0, p=1.0e5):
    """Aynalanmış duruma HLLC — duvar yıldız basıncı."""
    a = math.sqrt(gamma * p / rho)
    un = mach_n * a
    _, f_mn, _, _ = hllc_flux(np.array([rho]), np.array([un]),
                              np.array([0.0]), np.array([p]),
                              np.array([rho]), np.array([-un]),
                              np.array([0.0]), np.array([p]), gamma)
    return float(f_mn[0])


def test_P6B1_10_p_star_ANALITIK_bicimi_p_1_gamma_M():
    """Kusurun cebri: duvar akısı p·(1 + γ·M_n)'dir, M_n < −1/γ'da negatif."""
    for M in (-0.25, -0.5, -1.25 / _GAMMA, -2.0):
        assert _duvar_p_star(M) == pytest.approx(1.0e5 * (1.0 + _GAMMA * M),
                                                 rel=1e-9, abs=1e-6)


def test_P6B1_10_kusur_ADIYLA_ve_OLCUSUYLE_beyanlidir():
    """P6B1-10 KAPATILDI — beyan ve çare sessizce silinemez.

    D23'te ölçülen kusur: akustik duvar yıldız basıncı p·(1 + γ·M_n),
    M_n < −1/γ'da negatife geçiyordu; fail-closed "p* ≤ 0 → NaN" kapısı
    sağlam koşumu kırdığı için geri alınmıştı (kusur AÇIK beyanlıydı).
    ÖH D37 A3a cfd-kok-a (F-05; Berke Sunum 3a onayı, 24 Eylül 2026): çare
    olan iki-genişleme (TRRS) kapalı biçimi işletiliyor — vakum sınırına
    kadar pozitif, NaN üretmez (Lean HRMA.wallStarTR_pos). Bu bekçi
    kapanışın BEYANININ ve çarenin sessizce silinmesini engeller; davranışı
    da ölçer.
    """
    import inspect
    import numpy as np
    from hrma.cfd import euler_core
    kaynak = inspect.getsource(euler_core.residual_axisym)
    assert 'P6B1-10' in kaynak
    assert 'p·(1 + γ·M_n)' in kaynak          # eski akustik biçim adıyla kıyas
    assert 'iki-genişleme' in kaynak
    assert 'wall_star_pressure_trrs' in kaynak  # çare GERÇEKTEN çağrılıyor
    assert 'KAPATILAN KUSUR' in euler_core.__doc__
    assert 'AÇIK KUSUR' not in euler_core.__doc__
    # Davranış: akustik biçimin negatife geçtiği bantta TRRS pozitif; vakum
    # sınırında (M_n = −2/(γ−1)) sıfır, ötesinde de NEGATİF DEĞİL.
    g = 1.4
    Mn = np.array([-0.5, -1.0 / g - 1e-3, -0.985, -3.0, -4.9, -5.0, -7.0])
    akustik = 1e5 * (1.0 + g * Mn)
    trrs = euler_core.wall_star_pressure_trrs(np.full_like(Mn, 1e5), Mn, g)
    assert (akustik[1:] < 0).all()             # kusurun bandı gerçekten orada
    assert (trrs[:5] > 0).all()
    assert 0.0 <= trrs[5] < 1e-90   # tam sınır: (γ−1)/2 kayan noktada 2,2e-16 artık bırakır
    assert trrs[6] == 0.0          # sınırın ötesi: taban < 0 → p* = 0 (negatif değil)
    assert np.isfinite(trrs).all()


def test_P6B1_10_saglam_kosum_ETKILENMEDI():
    """Geri alma gerçekten geri alındı: sağlam koşum tam bütçesini yürür.

    Izgara ve gaz, kapının kırdığı D21 vakasının AYNISIDIR (boğazlı lüle,
    41×8; `tests/test_d21_fea_cfd_a2.py::_kucuk_izgara`) — düz silindir
    fikstürü bu kusuru GÖREMİYOR (ölçüldü: kapı geri konduğunda silindir
    vakası yeşil kalıyor, boğazlı vaka 3 → 1 iterasyona düşüyor). Bekçi o
    yüzden BOĞAZLI vakayı kullanır.
    """
    from hrma.cfd.steady import solve_steady_axisym
    z = np.linspace(0.0, 0.30, 41)
    r = 0.05 - 0.03 * np.exp(-((z - 0.12) / 0.05) ** 2)
    grid = build_grid_from_wall(z, r, nj=8)
    s = solve_steady_axisym(grid=grid, P0=2.0e6, T0=2800.0, gamma=1.2,
                            R=320.0, max_iters=3)
    assert s['iterations'] == 3, (
        'koşum bütçesinden erken çıktı — duvar akısına konan bir kapı '
        'başlangıç geçicisini ıraksama sayıyor olabilir')


# ---------------------------------------------------------------- P6B2-03

def test_P6B2_03_bant_muafiyeti_KOSULLU_ilan_edilir():
    """'Bant dışı = KUSUR DEĞİL' hükmü koşulsuz verilemez.

    Kusur: beyan, bant dışılığı laminer/düşük-Re vakasına bağlamadan
    "KUSUR DEĞİL" ilan ediyordu; oysa ÜRÜNÜN KENDİ varsayılan koşumu
    Re_D = 1,67e+06 (uçuş sınıfı) ve kesir 3,06e-04, yani bandın alt
    ucunun 16,3 katı altında — orada muafiyet geçerli DEĞİL.
    """
    import inspect
    kaynak = inspect.getsource(wo.friction_thrust_loss)
    i = kaynak.find("'band_comparison_basis'")
    metin = kaynak[i:i + 2200]
    assert 'MUAFİYET KOŞULLUDUR' in metin
    assert '1,67e+06' in metin and '3,06e-04' in metin
    assert 'AÇIKLANMASI GEREKEN' in metin
    # Bandın alt ucu ile ölçülen kesrin oranı ölçümden gelir
    assert wo.SUTTON_FRICTION_BAND[0] / 3.06e-04 == pytest.approx(16.34,
                                                                  rel=1e-3)


# ---------------------------------------------------------------- P6B2-05

def test_P6B2_05_yuzde_PAYDASIYLA_eslesir():
    """Yayımlanan yüzde, yazdığı paydaya bölünerek çıkmalı.

    Kusur: '%0,78' ortalamanın payına yazılmıştı ama o sayı duvar
    sırasının MİNİMUMUNA aitti (ölçüldü: ortalamaya %0,597, minimuma
    %0,770).
    """
    from hrma.cfd import wall_distance as wd
    metin = wd.wall_distance_field.__doc__
    assert '%0,78' not in metin, 'paydayla uyuşmayan yüzde hâlâ yayımlanıyor'
    assert '%0,597' in metin and '6,7281e-04' in metin
    assert '%0,770' in metin and '5,2091e-04' in metin

    sonra = _olcum('sonra.json')['K7_P6B2_05']
    assert sonra['yuzde_ortalamaya'] == pytest.approx(0.597, abs=5e-3)
    assert sonra['yuzde_minimuma'] == pytest.approx(0.770, abs=5e-3)


def test_P6B2_05_olcum_YENIDEN_URETILEBILIR():
    """Yayımlanan iki payda ürünün kendi ızgarasından yeniden ölçülür."""
    from hrma.cfd.wall_distance import wall_distance_field
    from tests.cfd.conftest import (LULE_L_CONV, LULE_L_DIV, LULE_NI,
                                    LULE_NJ, lule_duvar_yaricapi)
    z = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, LULE_NI + 1)
    grid = build_grid_from_wall(z, lule_duvar_yaricapi(z), LULE_NJ)
    duvar = wall_distance_field(grid)[:, -1]
    assert float(duvar.mean()) == pytest.approx(6.7281e-04, rel=1e-4)
    assert float(duvar.min()) == pytest.approx(5.2091e-04, rel=1e-4)


# ---------------------------------------------------------------- P6B2-06

def _viskoz_hata_yolu():
    from hrma.cfd import viscous
    z = np.linspace(0.0, 0.2, 13)
    grid = build_grid_from_wall(z, np.full(13, 0.05), 6)
    t = GasTransport(gamma=1.2, T_ref=300.0, mu_ref=1.8e-5,
                     cp=1.2 * 287.0 / 0.2, prandtl=0.72,
                     prandtl_turbulent=0.9, viscosity_exponent=0.7,
                     sources={'viscosity': 'caller'})
    U = np.zeros((grid.ni, grid.nj, 4))
    U[..., 0] = -1.0                       # ρ < 0 → fiziksel değil
    U[..., 3] = 1.0e5
    _, aux = viscous.viscous_residual(grid, U, t, R=287.0,
                                      wall_thermal='adiabatic',
                                      T_wall_source=None)
    return aux['declaration']


def test_P6B2_06_viskoz_hata_yolu_SAGLAM_ANAHTARLARI_tasir():
    """Beyan bir düzey altında da ayrışmaz — özellikle 'transport'.

    Kusur: ``aux``ün kendi anahtar kümesi aynıydı ama ``declaration``
    sağlam yolda 11, hata yolunda 4 anahtara düşüyordu; düşenler arasında
    ``wall_output._prandtl``ın okuduğu ``transport`` da vardı.
    """
    dec = _viskoz_hata_yolu()
    saglam = {'_source', 'formulation', 'wall_thermal', 'T_wall_source',
              'face_gradient_corrected', 'boundary_mode_i',
              'neumann_face_update_K', 'turbulent_viscosity',
              'mu_t_over_mu_max', 'transport', 'not_modelled'}
    assert saglam <= set(dec), f'düşen anahtarlar: {sorted(saglam - set(dec))}'
    assert dec['transport'] is not None
    assert 'cp_J_per_kgK' in dec['transport']
    # ÖLÇÜM olan alanlar UYDURULMAZ
    assert dec['mu_t_over_mu_max'] is None
    assert dec['neumann_face_update_K'] is None
    assert dec['nonphysical_state']


def test_P6B2_06_sa_hata_yolu_SAGLAM_ANAHTARLARI_tasir():
    """SA hata yolu 2 anahtardan sağlam yolun 13'ünü kapsar hâle geldi."""
    from hrma.cfd import sa_neg
    z = np.linspace(0.0, 0.2, 13)
    grid = build_grid_from_wall(z, np.full(13, 0.05), 6)
    t = GasTransport(gamma=1.2, T_ref=300.0, mu_ref=1.8e-5,
                     cp=1.2 * 287.0 / 0.2, prandtl=0.72,
                     prandtl_turbulent=0.9, viscosity_exponent=0.7,
                     sources={})
    U = np.zeros((grid.ni, grid.nj, 4))
    U[..., 0] = -1.0
    U[..., 3] = 1.0e5
    _, aux = sa_neg.sa_residual(grid, U, t, R=287.0,
                                nu_tilde=np.full((grid.ni, grid.nj), 1e-5),
                                omega=np.full((grid.ni, grid.nj), 100.0))
    dec = aux['declaration']
    saglam = {'_source', 'model', 'convection_scheme',
              'density_correction_term', 'destruction_treatment',
              'production_treatment', 'modified_vorticity_limiter',
              'wall_distance_source', 'mass_flux_source',
              'rho_mu_face_boundary_mode', 'axis_neumann_update',
              'constants', 'not_modelled'}
    assert saglam <= set(dec), f'düşen anahtarlar: {sorted(saglam - set(dec))}'
    assert dec['convection_scheme'] == 'upwind1'
    assert dec['axis_neumann_update'] is None       # ölçülemedi, uydurulmadı


def test_P6B2_06_kunye_uretici_hata_yolunda_CALISIR():
    """``wall_output`` künye üreticisi hata yolundan gelen sonucu okuyabilir.

    Kusurun ÜRÜN sonucu buydu: düşen ``transport`` yüzünden künye katmanı
    ADLI bir ValueError'a çarpıyordu.
    """
    dec = _viskoz_hata_yolu()
    assert wo._prandtl({'declaration': dec}) == pytest.approx(0.72)


# ---------------------------------------------------------------- P6B2-07

def test_P6B2_07_girdi_kapilari_ADIYLA_reddeder():
    """Yedi yol sonluluk/pozitiflik denetimi olmadan geçiyordu."""
    from hrma.cfd import gradients, sa_neg, viscous
    z = np.linspace(0.0, 0.2, 13)
    grid = build_grid_from_wall(z, np.full(13, 0.05), 6)
    ni, nj = grid.ni, grid.nj
    nan = float('nan')

    yuz = np.zeros((nj, 4))
    yuz[:, 0] = 1.0
    yuz[:, 3] = 1.0e5
    yuz[0, 0] = nan
    with pytest.raises(ValueError, match='sonlu olmalı'):
        viscous._face_primitives('inlet_face_primitives', yuz, nj)
    yuz[0, 0] = 0.0
    with pytest.raises(ValueError, match=r'ρ > 0'):
        viscous._face_primitives('inlet_face_primitives', yuz, nj)

    with pytest.raises(ValueError, match='sonlu olmalı'):
        gradients.green_gauss_gradient(grid, np.full((ni, nj), nan))
    with pytest.raises(ValueError, match='sonlu olmalı'):
        gradients.green_gauss_gradient(
            grid, np.ones((ni, nj)),
            bc=gradients.BoundaryFaceValues(i_lo=np.full(nj, nan)))

    bir = np.ones((ni, nj))
    with pytest.raises(ValueError, match='Ω'):
        sa_neg.sa_source_terms(bir, bir * 1e-5, bir * 1e-5,
                               np.full((ni, nj), nan), bir * 1e-3)
    with pytest.raises(ValueError, match='μ'):
        sa_neg.sa_source_terms(bir, bir * 1e-5, np.zeros((ni, nj)),
                               bir * 100.0, bir * 1e-3)
    with pytest.raises(ValueError, match='ρ'):
        sa_neg.sa_source_terms(np.zeros((ni, nj)), bir * 1e-5, bir * 1e-5,
                               bir * 100.0, bir * 1e-3)


def test_P6B2_07_sa_kalintisinda_sonsuz_OMEGA_diverged_yolundan_doner():
    """Sürücüye istisna SIZMAZ: Ω NaN'ı da ortak NaN ölçütüne girer."""
    from hrma.cfd import sa_neg
    z = np.linspace(0.0, 0.2, 13)
    grid = build_grid_from_wall(z, np.full(13, 0.05), 6)
    t = GasTransport(gamma=1.2, T_ref=300.0, mu_ref=1.8e-5,
                     cp=1.2 * 287.0 / 0.2, prandtl=0.72,
                     prandtl_turbulent=0.9, viscosity_exponent=0.7,
                     sources={})
    U = np.zeros((grid.ni, grid.nj, 4))
    U[..., 0] = 1.0
    U[..., 3] = 1.0e5 / 0.2
    dudt, aux = sa_neg.sa_residual(
        grid, U, t, R=287.0,
        nu_tilde=np.full((grid.ni, grid.nj), 1e-5),
        omega=np.full((grid.ni, grid.nj), float('nan')))
    assert np.all(np.isnan(dudt))
    assert 'Ω' in aux['declaration']['nonphysical_state']


# ---------------------------------------------------------------- P6B2-08

def test_P6B2_08_gamma_1_ADLI_ValueError_ile_reddedilir():
    """γ = 1,0 ADSIZ ZeroDivisionError üretiyordu (cp = γR/(γ−1))."""
    with pytest.raises(ValueError, match='gamma'):
        GasTransport(gamma=1.0, T_ref=300.0, mu_ref=1.8e-5, cp=1000.0,
                     prandtl=0.72, prandtl_turbulent=0.9,
                     viscosity_exponent=0.7, sources={})
    for kotu in (0.0, -1.0, float('nan'), float('inf')):
        with pytest.raises(ValueError, match='gamma'):
            GasTransport(gamma=kotu, T_ref=300.0, mu_ref=1.8e-5, cp=1000.0,
                         prandtl=0.72, prandtl_turbulent=0.9,
                         viscosity_exponent=0.7, sources={})


def test_P6B2_08_check_gas_consistency_kendi_kapisini_tasir():
    """Sahte nesneyle gelen γ ≤ 1 de ADIYLA reddedilir (tek kaynak değil,
    iki bağımsız kapı — biri sınıfın, biri tüketicinin)."""
    from hrma.cfd import viscous

    class _Sahte:
        gamma = 1.0
        cp = 1000.0

    with pytest.raises(ValueError, match='γ > 1'):
        viscous._check_gas_consistency(_Sahte(), 287.0)


def test_P6B2_08_saglam_gaz_gecmeye_DEVAM_eder():
    """Kapı sağlam girdiyi reddetmez."""
    from hrma.cfd import viscous
    t = GasTransport(gamma=1.2, T_ref=300.0, mu_ref=1.8e-5,
                     cp=1.2 * 287.0 / 0.2, prandtl=0.72,
                     prandtl_turbulent=0.9, viscosity_exponent=0.7,
                     sources={})
    R, g = viscous._check_gas_consistency(t, 287.0)
    assert (R, g) == (287.0, 1.2)


# ---------------------------------------------------------------- P6B3-05

def test_P6B3_05_kunye_uca_BAGLILIGI_dogru_soyler():
    """Künye 'uca BAĞLANMADI' derken blok uçtan yayımlanıyordu.

    Ölçüldü: ``hrma/app.py`` alan bloğuna ``'radial_geometry':
    radial_geometry_block(...)`` satırıyla koyuyor; iki künye ise
    "YAYIMLANMADI" / "uca bağlanması B3'ün/V4'ün işidir" diyordu.
    """
    from hrma.cfd import grid_axisym
    import hrma.cfd as cfd_paket

    with open(os.path.join(KOK, 'hrma', 'app.py'), encoding='utf-8') as f:
        app_metni = f.read()
    assert "'radial_geometry': radial_geometry_block(" in app_metni, (
        'uç bloğu artık yayımlamıyorsa BU BEKÇİ değil künye güncellenmeli')

    assert 'UCA BAĞLIDIR' in grid_axisym.__doc__
    assert 'UCA BAĞLIDIR' in radial_geometry_block.__doc__
    with open(cfd_paket.__file__, encoding='utf-8') as f:
        assert 'UCA BAĞLIDIR' in f.read()

    # Kilit YERİNDE: bağlı olmayan şey GERDİRMEDİR, blok değil
    assert 'gerdirme' in radial_geometry_block.__doc__.lower()


def test_P6B3_05_iki_bayt_olcumunun_PAYDASI_adlandirildi():
    """'İki yerde iki sayı' → iki AYRI ölçüm, her biri neyi ölçtüğü yazılı."""
    from hrma.cfd.grid_axisym import radial_geometry_block as f
    assert 'BU İŞLEVİN ÇIKTISI TEK BAŞINA' in f.__doc__
    assert 'GERÇEK UÇ YANITINDA' in f.__doc__
    assert '15,8 KB' in f.__doc__ and '17,7 KB' in f.__doc__


def test_P6B3_05_blok_bayt_bedeli_OLCULUR():
    """Yükün boyutunu sınayan bekçi yoktu — kayıtsız büyüme yakalanmazdı."""
    z = np.linspace(0.0, 0.2, 61)
    grid = build_grid_from_wall(z, np.full(61, 0.05), 12)
    blok = radial_geometry_block(grid)
    bayt = len(json.dumps(blok, ensure_ascii=False).encode('utf-8'))
    # ÖLÇÜLDÜ (D23 once/sonra.json K11): 15414 B = 15,05 KB, 60×12
    assert 14000 < bayt < 17000, (
        f'blok bedeli {bayt} B — ölçülen 15414 B bandının dışında; '
        'yük sessizce büyümüş ya da küçülmüş olabilir')
    assert set(blok) >= {'r_nodes_m', 'shape', 'radial_uniform_rel_tol'}
