# tests/cfd — radyal ızgara gerdirme (viskoz tasarım §5.7): bekçiler
"""Duvara sıkıştırılmış radyal dağılımın bekçileri (V2, tasarım §5.7).

NE KANITLANIYOR
---------------
1. VARSAYILAN DEĞİŞMEDİ: ``first_cell_m=None`` dalı bugünkü düzgün
   dağılımın harfi harfine kendisidir (bit-özdeşlik; 17 Euler referans
   bekçisi bunun üstünde durur).
2. PARAMETRE ORAN DEĞİL KALINLIK: aynı ``first_cell_m`` ile nj
   ikiye katlandığında duvar hücresi DEĞİŞMEZ. Oran tabanlı bir parametre
   (büyüme çarpanı ya da "düzgünün k katı") bu bekçiyi kıramaz.
3. HEDEFE ULAŞIM ÖLÇÜLÜR: istenen kalınlık her istasyonda 1e-10 bağıl
   duyarlıkla tutturulur (ve tutturulan değer beyanda yayımlanır).
4. GEOMETRİK GERÇEKLER KORUNUR: eksen düğümü TAM 0.0, duvar düğümü TAM
   kontur yarıçapı, hacimler pozitif, kapanış özdeşlikleri (Σ S_z = 0,
   Σ S_r = 2π A) gerdirilmiş ızgarada da makine sıfırında.
5. YAYIN YOLU KİLİTLİ: uç (``app._cfd_build_grid``) düzgün dağılımı
   kurar — hem ÇALIŞTIRILARAK hem de YAPISAL olarak (AST) doğrulanır.
   Panelin radyal düzgünlük varsayımı (motor_viz3d.js
   ``CFD_RADIAL_UNIFORM_REL_TOL``) bu partide dokunulmadan kalır;
   gerdirmenin yayın yoluna taşınması V4'ün işidir.

AİLE SEÇİMİ — ÖLÇÜLDÜ (gerekçe grid_axisym.DEFAULT_RADIAL_STRETCH'te)
--------------------------------------------------------------------
ÜRÜN ÖLÇÜMÜ (laminer boru, merdiven basamağı 4; nj = 12, ilk hücre
104,17 µm = düzgünün 1/4'ü, adyabatik duvar, BORU_TOL_RES; M4 Max,
2026-08-18). Bu dosya o koşuyu KOŞMAZ (üç kararlı-hâl koşusu, ~9 dk);
sayılar burada beyanlıdır ve ucuz kesme-hatası ölçümü canlı koşulur:

    A) ilk hücre 104,17 µm (düzgünün 1/4'ü):
    dağılım     q_maks    f·Re      hata      parabol sapması   iter
    düzgün      1,0000   63,7042   −%0,462   6,98e-04          15400
    geometrik   1,2307   63,5036   −%0,776   2,51e-03          15150
    tanh        1,3031   63,5849   −%0,649   9,61e-05          14900

    B) ilk hücre 41,67 µm (düzgünün 1/10'u — daha agresif sıkıştırma):
    dağılım     q_maks    f·Re      hata      parabol sapması   iter
    düzgün      1,0000   63,7042   −%0,462   6,98e-04          15400
    geometrik   1,3762   62,9694   −%1,610   5,42e-03          15050
    tanh        1,4712   63,2685   −%1,143   5,57e-04          14900

İKİ noktada da tanh geometrikten daha iyi: f·Re hatasında %16 (A) ve
%29 (B) daha yakın, profil sapmasında 26 kat (A) ve 10 kat (B) daha iyi.
Geometrik yalnız maksimum büyüme oranında öndedir (1,2307 ↔ 1,3031;
1,3762 ↔ 1,4712). Varsayılan bu yüzden 'tanh'tır. Geometrik aile
SİLİNMEDİ: karşılaştırmanın kendisi ancak iki aile de koşulabilir
kaldığında tekrarlanabilir.

DÜRÜST OKUMA — bu tablo "gerdirme boruyu iyileştirir" DEMEZ: iki
gerdirilmiş dağılım da f·Re'de DÜZGÜN ızgaradan kötüdür ve olması
gereken budur (tam gelişmiş Poiseuille profilinin eğriliği ÇEKİRDEKTE;
duvara sıkıştırmak orada çözünürlük harcar). Tablonun ölçtüğü şey
AYNI ilk hücrede iki ailenin GÖRECELİ doğruluğudur — gerdirmenin
gerekçesi sınır tabakasıdır, boru değil (§5.7).

MALİYET: bu dosya cebirseldir (kararlı-hâl koşusu YOK), ~2 s.
"""

import ast
import inspect
import pathlib

import numpy as np
import pytest

from hrma.cfd.grid_axisym import (
    DEFAULT_RADIAL_STRETCH,
    RADIAL_DISTRIBUTIONS,
    RADIAL_UNIFORM_REL_TOL,
    AxisymGrid,
    build_grid_from_wall,
    radial_geometry_block,
    radial_nodes,
)

from .conftest import LULE_NJ, lule_duvar_yaricapi, lule_gridi

# Vaka: conftest lülesinin duvarı (r_w 25-40 mm arasında değişir — tek bir
# fiziksel kalınlığın istasyondan istasyona FARKLI orana karşılık geldiği,
# yani "oran değil kalınlık" ayrımının GÖRÜLDÜĞÜ geometri).
GERDIRME_NI = 40
GERDIRME_NJ = 16


def _duvar(ni=GERDIRME_NI):
    z = np.linspace(0.0, 0.30, ni + 1)
    return z, lule_duvar_yaricapi(z)


def _grid(nj=GERDIRME_NJ, first_cell_m=None, stretch=DEFAULT_RADIAL_STRETCH,
          ni=GERDIRME_NI):
    z, r = _duvar(ni)
    return build_grid_from_wall(z, r, nj, first_cell_m=first_cell_m,
                                stretch=stretch)


def _hedef_kalinlik(nj=GERDIRME_NJ, kat=0.25, ni=GERDIRME_NI):
    """En dar istasyonun düzgün hücresinin `kat` katı (kurulabilir hedef)."""
    _, r = _duvar(ni)
    return kat * float(np.min(r)) / nj


AILELER = tuple(s for s in RADIAL_DISTRIBUTIONS if s != 'uniform')


# ===========================================================================
# 1) VARSAYILAN DAL — bugünkü ifadenin harfi harfine kendisi
# ===========================================================================

def test_varsayilan_dagilim_duzgun_ve_beyani_boyle_soyluyor():
    g = _grid()
    assert g.radial_distribution == 'uniform'
    assert g.radial_stretch is None
    assert 'DÜZGÜN' in g._basis and 'linspace' in g._basis


def test_varsayilan_dugumler_dondurulmus_ifadeyle_BIT_AYNI():
    """R = r_w[:,None]·linspace(0,1,nj+1) — tek bir ulp bile fark yok.

    Bu, 17 Euler bit-özdeşlik bekçisinin ızgara ayağıdır: gerdirme kodu
    varsayılan dalda HİÇ çalışmaz, o yüzden dondurulmuş referanslar
    kayamaz.
    """
    z, r = _duvar()
    g = build_grid_from_wall(z, r, GERDIRME_NJ)
    beklenen = r[:, None] * np.linspace(0.0, 1.0, GERDIRME_NJ + 1)[None, :]
    assert np.array_equal(g.R, beklenen), (
        'düzgün radyal dağılım kaydı — Euler referansları bu ifadenin '
        'üstünde donduruldu')


def test_varsayilan_metrikler_bit_ayni_kalir():
    """Izgara metrikleri (hacim, yüzeyler, merkezler) de bit-özdeş."""
    a = lule_gridi(60, 12)
    b = lule_gridi(60, 12)
    for alan in ('R', 'Z', 'volume', 'area_planar', 'face_i', 'face_j',
                 'face_i_planar', 'face_j_planar', 'z_centers', 'r_centers'):
        assert np.array_equal(getattr(a, alan), getattr(b, alan)), alan


def test_sinif_varsayilani_beyan_metnini_tasir():
    """AxisymGrid._basis alanı varsayılanı taşır (kurucu onu kullanıyor)."""
    assert 'DÜZGÜN' in AxisymGrid._basis
    assert _grid()._basis == AxisymGrid._basis


# ===========================================================================
# 2) PARAMETRE ORAN DEĞİL KALINLIK (mutasyon yakalayıcı)
# ===========================================================================

@pytest.mark.parametrize('aile', AILELER)
def test_parametre_fiziksel_kalinliktir_nj_degisince_ayni_kalir(aile):
    """nj ikiye katlanınca duvar hücresi DEĞİŞMEZ — oran olsaydı yarılanırdı.

    MUTASYON KANITI: parametre "düzgünün k katı" ya da büyüme oranı gibi
    ORANSAL bir büyüklüğe dönerse duvar hücresi nj ile ölçeklenir ve bu
    bekçi kırmızıya düşer.
    """
    # Hedef EN İNCE merdiven basamağına göre kurulur: aynı fiziksel
    # kalınlık her nj'de kurulabilir olmalı (nj=64'te bile düzgünden ince).
    d1 = _hedef_kalinlik(nj=64, kat=0.25)
    kalin = []
    for nj in (16, 32, 64):
        g = _grid(nj=nj, first_cell_m=d1, stretch=aile)
        kalin.append(np.diff(g.R, axis=1)[:, -1])
    for k in kalin:
        assert np.allclose(k, d1, rtol=1e-10, atol=0.0), (
            f'{aile}: duvar hücresi nj ile kaydı — parametre kalınlık '
            f'olmaktan çıkmış (istenen {d1:g} m, ölçülen '
            f'{float(np.max(np.abs(k - d1))):g} m sapma)')
    # aynı kalınlık, FARKLI oran: nj büyüdükçe d1/(r_w/nj) oranı büyür
    _, r = _duvar()
    oranlar = [d1 / (float(np.min(r)) / nj) for nj in (16, 32, 64)]
    assert oranlar[0] < oranlar[1] < oranlar[2], (
        'vaka oran-ayrımını göstermiyor; bekçi kör olurdu')


@pytest.mark.parametrize('aile', AILELER)
def test_ayni_kalinlik_farkli_yaricapta_farkli_orana_karsilik_gelir(aile):
    """r_w istasyonla değiştiği için tek kalınlık = istasyona göre değişen ORAN.

    Bu, "parametre neden kalınlık" sorusunun geometrik cevabıdır: hedef
    y⁺ fiziksel bir mesafedir, oran değil.
    """
    d1 = _hedef_kalinlik(kat=0.2)
    g = _grid(first_cell_m=d1, stretch=aile)
    r_w = g.R[:, -1]
    oran = d1 / (r_w / GERDIRME_NJ)
    assert float(np.max(oran) / np.min(oran)) > 1.5, (
        'vaka duvar yarıçapı yeterince değişmiyor')
    kalinlik = np.diff(g.R, axis=1)[:, -1]
    assert np.allclose(kalinlik, d1, rtol=1e-10, atol=0.0)


# ===========================================================================
# 3) HEDEFE ULAŞIM + MONOTONLUK + BÜYÜME ORANI (ölçülü)
# ===========================================================================

@pytest.mark.parametrize('aile', AILELER)
@pytest.mark.parametrize('kat', (0.5, 0.25, 0.05, 0.01))
def test_ilk_hucre_hedefi_olculu_tutturulur(aile, kat):
    d1 = _hedef_kalinlik(kat=kat)
    g = _grid(first_cell_m=d1, stretch=aile)
    b = g.radial_stretch
    olculen = np.diff(g.R, axis=1)[:, -1]
    bagil = np.max(np.abs(olculen - d1)) / d1
    assert bagil < 1e-10, (
        f'{aile} kat={kat}: ilk hücre hedefi {bagil:.2e} bağıl sapmayla '
        'tutturuldu — kök çözücüsü ya da düğüm kurulumu bozuk')
    # BEYAN ölçümün kendisini taşımalı (uydurma sayı yok)
    assert b['first_cell_target_m'] == d1
    assert b['first_cell_achieved_min_m'] == pytest.approx(
        float(np.min(olculen)), rel=0.0, abs=0.0)
    assert b['first_cell_achieved_max_m'] == pytest.approx(
        float(np.max(olculen)), rel=0.0, abs=0.0)
    assert b['first_cell_rel_error_max'] == pytest.approx(bagil, rel=1e-12)


@pytest.mark.parametrize('aile', AILELER)
def test_dagilim_monoton_ve_duvara_dogru_inceliyor(aile):
    d1 = _hedef_kalinlik(kat=0.1)
    g = _grid(first_cell_m=d1, stretch=aile)
    dr = np.diff(g.R, axis=1)
    assert np.all(dr > 0.0), 'düğümler artan değil'
    # eksene doğru KALINLAŞIR: dr[j] <= dr[j-1] hiçbir yerde bozulmaz
    assert np.all(dr[:, :-1] >= dr[:, 1:]), (
        f'{aile}: hücre kalınlığı duvara doğru monoton incelmiyor')


@pytest.mark.parametrize('aile', AILELER)
def test_buyume_orani_beyani_izgaradan_yeniden_hesaplanabilir(aile):
    d1 = _hedef_kalinlik(kat=0.1)
    g = _grid(first_cell_m=d1, stretch=aile)
    dr = np.diff(g.R, axis=1)
    oran = dr[:, :-1] / dr[:, 1:]
    b = g.radial_stretch
    assert b['growth_ratio_max'] == pytest.approx(float(np.max(oran)),
                                                  rel=1e-12)
    assert b['growth_ratio_min'] == pytest.approx(float(np.min(oran)),
                                                  rel=1e-12)
    assert b['growth_ratio_min'] >= 1.0
    assert b['family'] == aile


def test_geometrik_ailenin_buyume_orani_SABITTIR_tanh_ninki_degil():
    """İki ailenin AYIRT EDİCİ yapısal imzası (ölçüm, iddia değil)."""
    d1 = _hedef_kalinlik(kat=0.1)
    b_geo = _grid(first_cell_m=d1, stretch='geometric').radial_stretch
    b_tanh = _grid(first_cell_m=d1, stretch='tanh').radial_stretch
    # geometrik: kolon içinde oran sabit (kolonlar arası r_w ile değişir)
    g = _grid(first_cell_m=d1, stretch='geometric')
    dr = np.diff(g.R, axis=1)
    oran = dr[:, :-1] / dr[:, 1:]
    kolon_ici = np.max(oran, axis=1) / np.min(oran, axis=1)
    assert np.all(kolon_ici < 1.0 + 1e-9), (
        'geometrik ailede kolon içi büyüme oranı sabit OLMALI')
    t = _grid(first_cell_m=d1, stretch='tanh')
    drt = np.diff(t.R, axis=1)
    orant = drt[:, :-1] / drt[:, 1:]
    assert float(np.max(np.max(orant, axis=1) / np.min(orant, axis=1))) > 1.05
    # ölçülen kalite farkı: geometriğin maks büyüme oranı DAHA KÜÇÜK
    assert b_geo['growth_ratio_max'] < b_tanh['growth_ratio_max']


def test_varsayilan_aile_tanh_ve_kesme_hatasi_bunu_dogruluyor():
    """Varsayılan seçim CANLI ölçümle sınanır (docstring'e güvenilmez).

    Ölçüt: radyal difüzyon operatörünün (hücre-merkezli, 3 noktalı)
    sınır-tabakası profili üstündeki L2 hatası — aynı ilk hücrede.
    """
    assert DEFAULT_RADIAL_STRETCH == 'tanh'

    def kesme_hatasi(y, lam=0.05):
        yc = 0.5 * (y[:-1] + y[1:])
        yy = 1.0 - yc
        u = 1.0 - np.exp(-yy / lam)
        yuz = np.concatenate([[0.0], np.diff(u) / np.diff(yc),
                              [(0.0 - u[-1]) / (1.0 - yc[-1])]])
        lap = np.diff(yuz) / np.diff(y)
        tam = -np.exp(-(1.0 - yc) / lam) / lam ** 2
        w = np.diff(y)
        return float(np.sqrt(np.sum((lap - tam) ** 2 * w) / np.sum(w)))

    for nj in (24, 48, 96):
        for kat in (0.5, 0.25, 0.1, 0.02):
            d1 = kat / nj
            y_geo, _ = radial_nodes(nj, np.array([1.0]), first_cell_m=d1,
                                    stretch='geometric')
            y_tanh, _ = radial_nodes(nj, np.array([1.0]), first_cell_m=d1,
                                     stretch='tanh')
            e_geo = kesme_hatasi(y_geo[0])
            e_tanh = kesme_hatasi(y_tanh[0])
            assert e_tanh < e_geo, (
                f'nj={nj} kat={kat}: tanh ({e_tanh:.4e}) geometrikten '
                f'({e_geo:.4e}) daha iyi ÇIKMADI — varsayılan aile seçimi '
                'artık ölçümle desteklenmiyor')


# ===========================================================================
# 4) GEOMETRİK GERÇEKLER — eksen, duvar, hacim, kapanış özdeşlikleri
# ===========================================================================

@pytest.mark.parametrize('aile', AILELER)
def test_eksen_dugumu_TAM_sifir_duvar_dugumu_TAM_kontur(aile):
    """r=0'da yüz alanı ayrık olarak TAM sıfır kalmalı (0/0 muamelesi yok)."""
    d1 = _hedef_kalinlik(kat=0.05)
    z, r = _duvar()
    g = build_grid_from_wall(z, r, GERDIRME_NJ, first_cell_m=d1,
                             stretch=aile)
    assert np.all(g.R[:, 0] == 0.0)
    assert np.array_equal(g.R[:, -1], r)
    assert np.all(np.linalg.norm(g.face_j[:, 0, :], axis=-1) == 0.0), (
        'eksen yüzünün alanı tam sıfır değil')
    assert np.all(g.volume > 0.0)
    assert np.all(g.area_planar > 0.0)


@pytest.mark.parametrize('aile', AILELER)
def test_kapanis_ozdeslikleri_gerdirilmis_izgarada_da_makine_sifirinda(aile):
    """Σ S_z = 0 ve Σ S_r = 2π·A_düzlem (test_grid.py sözleşmesi)."""
    d1 = _hedef_kalinlik(kat=0.05)
    g = _grid(first_cell_m=d1, stretch=aile)
    s_z = (g.face_i[1:, :, 0] - g.face_i[:-1, :, 0]
           + g.face_j[:, 1:, 0] - g.face_j[:, :-1, 0])
    s_r = (g.face_i[1:, :, 1] - g.face_i[:-1, :, 1]
           + g.face_j[:, 1:, 1] - g.face_j[:, :-1, 1])
    olcek = np.max(np.abs(g.face_j[:, 1:, 1]))
    assert np.max(np.abs(s_z)) < 1e-12 * olcek, 'Σ S_z ≠ 0'
    assert np.allclose(s_r, 2.0 * np.pi * g.area_planar, rtol=1e-12,
                       atol=1e-12 * olcek), 'Σ S_r ≠ 2π·A'


@pytest.mark.parametrize('aile', AILELER)
def test_hacimlerin_toplami_gerdirmeden_bagimsiz(aile):
    """Toplam hacim geometrik gerçektir; dağılım onu değiştiremez."""
    d1 = _hedef_kalinlik(kat=0.05)
    v_duz = float(np.sum(_grid().volume))
    v_ger = float(np.sum(_grid(first_cell_m=d1, stretch=aile).volume))
    assert v_ger == pytest.approx(v_duz, rel=1e-12)


# ===========================================================================
# 5) KAPILAR — sessiz düzgüne düşme YOK
# ===========================================================================

def test_duzgunden_kalin_hedef_REDDEDILIR():
    _, r = _duvar()
    duzgun = float(np.min(r)) / GERDIRME_NJ
    with pytest.raises(ValueError, match=r'DÜZGÜN hücre kalınlığından'):
        _grid(first_cell_m=duzgun)
    with pytest.raises(ValueError, match=r'DÜZGÜN hücre kalınlığından'):
        _grid(first_cell_m=1.5 * duzgun)


@pytest.mark.parametrize('bozuk', (0.0, -1e-5, float('nan'), float('inf')))
def test_pozitif_olmayan_kalinlik_REDDEDILIR(bozuk):
    with pytest.raises(ValueError, match=r'first_cell_m pozitif'):
        _grid(first_cell_m=bozuk)


def test_bilinmeyen_aile_ve_uniform_REDDEDILIR():
    with pytest.raises(ValueError, match=r'tanımsız'):
        _grid(first_cell_m=_hedef_kalinlik(), stretch='vinokur')
    with pytest.raises(ValueError, match=r"'uniform' gerdirme değildir"):
        _grid(first_cell_m=_hedef_kalinlik(), stretch='uniform')


def test_aile_listesi_dondurulmus():
    assert RADIAL_DISTRIBUTIONS == ('uniform', 'geometric', 'tanh')


# ===========================================================================
# 6) YAYIN YOLU KİLİDİ — panel radyal DÜZGÜNLÜK varsayar (V4'e kadar)
# ===========================================================================

def test_uc_izgarasi_DUZGUN_kurulur_calistirilarak():
    """app._cfd_build_grid gerdirme KULLANMAZ (koşularak doğrulanır)."""
    from hrma.app import _cfd_build_grid

    pts = np.stack([np.linspace(0.0, 0.30, 25),
                    lule_duvar_yaricapi(np.linspace(0.0, 0.30, 25))], axis=1)
    grid, _, _ = _cfd_build_grid(pts, 24, LULE_NJ)
    assert grid.radial_distribution == 'uniform'
    assert grid.radial_stretch is None


def test_uc_izgarasi_DUZGUN_kurulur_yapisal_olarak():
    """AST kilidi: çağrıda first_cell_m/stretch argümanı GEÇMEZ.

    Koşum bekçisi tek başına yetmez — biri gerdirmeyi koşul altında
    (ör. viskoz istekte) açsaydı yukarıdaki koşum yolu onu görmezdi.
    """
    from hrma import app

    kaynak = inspect.getsource(app._cfd_build_grid)
    agac = ast.parse(kaynak)
    cagrilar = [d for d in ast.walk(agac)
                if isinstance(d, ast.Call)
                and isinstance(d.func, ast.Name)
                and d.func.id == 'build_grid_from_wall']
    assert len(cagrilar) == 1, (
        '_cfd_build_grid içinde beklenen tek ızgara kurulumu bulunamadı')
    c = cagrilar[0]
    assert len(c.args) == 3 and not c.keywords, (
        'yayın yolu ızgarayı gerdirme argümanıyla kuruyor — panelin '
        'radyal düzgünlük varsayımı (motor_viz3d.js '
        'CFD_RADIAL_UNIFORM_REL_TOL) ve uç beyan metinleri bu partide '
        'DOKUNULMADI; gerdirmenin yayına taşınması V4 kalemidir')


def test_panelin_duzgunluk_olcutu_duzgun_izgarayi_GECER_gerdirilmisi_GECMEZ():
    """Kilidin YÜKLÜ olduğunun kanıtı: ölçüt gerçekten ayırt ediyor.

    motor_viz3d.js:cfdWallRadii'nin kuralı Python'da yeniden kurulmaz —
    JS sabitinin KENDİSİ okunur; burada ölçülen, aynı toleransın iki
    dağılımı ayırdığıdır.
    """
    js = (pathlib.Path(__file__).resolve().parents[2]
          / 'hrma' / 'static' / 'js' / 'motor_viz3d.js').read_text()
    satir = [s for s in js.splitlines()
             if 'CFD_RADIAL_UNIFORM_REL_TOL =' in s]
    assert len(satir) == 1, 'panel sabiti tek tanım olmalı'
    tol = float(satir[0].split('=')[1].strip().rstrip(';'))

    def duzgun_mu(r_merkez):
        d0 = r_merkez[1] - r_merkez[0]
        d = np.diff(r_merkez)
        return bool(np.all(np.abs(d - d0) <= tol * d0)
                    and abs(r_merkez[0] - 0.5 * d0) <= tol * d0)

    assert duzgun_mu(_grid().r_centers[0]), (
        'düzgün ızgara panelin ölçütünü geçmiyor — panel bugün duvar '
        'yarıçapını çizemiyor olurdu')
    d1 = _hedef_kalinlik(kat=0.25)
    for aile in AILELER:
        assert not duzgun_mu(_grid(first_cell_m=d1, stretch=aile
                                   ).r_centers[0]), (
            f'{aile}: gerdirilmiş ızgara panelin düzgünlük ölçütünü '
            'GEÇİYOR — o zaman kilit boş bir bekçi olurdu')


# ===========================================================================
# 7) DUVAR-NORMAL YAKA (V1b, parti 39 A4) — OPT-IN, ölçümle gerekçeli
#
# NE KANITLANIYOR (ve NE KANITLANMIYOR — ikisi de bekçili):
#   (a) VARSAYILAN DEĞİŞMEDİ: wall_collar=None dalı bugünkü ifadenin harfi
#       harfine kendisidir (düzgün ve gerdirilmiş yollar ayrı ayrı).
#   (b) SINIR DÜĞÜMLERİ KAYMAZ: duvar (boğaz/çıkış istasyonları) ve eksen
#       (r = 0) düğümleri TAM korunur — yaka yalnız İÇ düğümleri taşır.
#   (c) YAKANIN YAPTIĞI: duvar çarpıklığını düşürür ve ilk hücrenin
#       duvar-NORMAL kalınlığını istasyondan bağımsız hedefe oturtur
#       (H-ızgarada o kalınlık radyalin cos α katıydı).
#   (d) YAKANIN YAPMADIĞI: AR·Δα'yı KALDIRMAZ. Δα duvar KONTURUNUN
#       büyüklüğüdür ve duvar düğümleri kaymadığı için iki topolojide
#       BİREBİR aynıdır. Bu bekçi bilerek NEGATİF bir iddiayı kilitler:
#       ileride "yaka dinamik kararsızlığı çözer" diye yazan biri önce
#       bu ölçümü yalanlamak zorunda kalsın.
#   (e) HARMAN KENDİ TEPESİNİ ÜRETİR — ve genişlikle söner: dar harman
#       ölçülebilir biçimde kırılır (aşağıdaki tablo), varsayılan
#       genişlikte (nj//2) aralık oranı DEĞİŞİMİ yakasız tabana geri
#       döner (0,0120). Green-Gauss çarpıklığı orada bile tabanın biraz
#       üstünde kalır (0,0385 → 0,0447) — dürüst kalan pay budur.
#   (f) VARSAYILANLAR ÖLÇÜMDEN: layers = 4 hizalı bölgenin derinliğini,
#       blend = nj//2 harman payının doyma noktasını veriyor. İkisi de
#       ayrı bekçilerde tablolarıyla duruyor.
#
# ÖLÇÜLDÜ (M4 Max, 2026-08-19; betik p39_a4_yaka_tarama.py). Üç ızgara,
# tanh gerdirme, yaka (layers/blend) = 4/4:
#
#   ızgara                    duvar çarpıklığı   AR        AR·Δα     Δα
#   gerçek kontur 192×48      42,135° → 2,122°   172,1→127,6  17,969→17,690  10,494° (aynı)
#   gerçek kontur  48×24      42,074° → 19,724°  687,2→510,1  97,815→97,526  14,563° (aynı)
#   conftest lüle 192×48      11,108° → 0,194°  1074,7→1054,5  8,303→ 8,303   0,460° (aynı)
#
# İki okuma birlikte: çarpıklık 20-57 kat düşüyor (ni büyüdükçe daha da),
# AR·Δα ise yalnız 1/cos α kadar (%1,6) — conftest lülesinde 4 hanede HİÇ
# değişmiyor, çünkü AR·Δα'nın tepesi BOĞAZDA'dır ve orada duvar açısı
# zaten sıfırdan geçer. Yani yaka, parti 39 A1'in dinamik kararsızlık
# metriğine dokunmaz; bu ölçüm KAPI koşusundan ÖNCE elde vardı ve koşu
# onu doğruladı (p39_a4_rapor.md).
#
# HARMAN GENİŞLİĞİ — ölçülen kırılma (gerçek kontur 192×48, ilk hücre
# 10 µm; volR = ızgaranın maksimum radyal komşu hücre hacim oranı,
# yakasız taban 2,9740):
#
#   layers/blend   maks κ adımı   volR        harman aralık oranı
#   4/1            1,0000         188,99      2,9723
#   6/1            1,0000         HÜCRE ALANI NEGATİF (ValueError)
#   3/1            1,0000           5,7188    2,5383
#   6/2            0,5000           4,1577    1,8955
#   4/2            0,5000           2,9740 (taban)  1,5947
#   6/3            0,5802           3,7293    2,4757
#   4/4            0,3965           2,9740 (taban)  1,6403
#   8/4            0,3965           2,9740 (taban)  2,0279
#  12/6            0,2901           2,9740 (taban)  1,6520
#
# Harmanın metrik payını yöneten büyüklük κ'nın KATMAN BAŞINA adımıdır
# (beyanda max_kappa_step) — ve o adım blend_layers'ta MONOTON DEĞİLDİR:
# B = 3 (0,5802) B = 2'den (0,5000) kötüdür, çünkü tek sayıda katmanda
# orta örnek smootherstep'in en dik noktasına düşer. Bu yüzden "harmanı
# genişlet" tek başına bir çare değildir ve sayı beyanda yayımlanır.
# ===========================================================================

from hrma.cfd.grid_axisym import (                             # noqa: E402
    COLLAR_BLEND_PROFILE,
    WallCollar,
    build_nozzle_grid,
    collar_weights,
    wall_node_normals,
)

#: Gerçek motor konturu ölçümlerinin ızgarası (42,14° yakınsak duvar —
#: çarpıklığın GÖRÜLDÜĞÜ tek vaka; conftest lülesi yalnız 11,1°).
YAKA_D1 = 1.0e-5


def _gercek_kontur_mm():
    """Gerçek motor konturu [(z_mm, r_mm), ...] — ürünün örnekleyicisinden."""
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour

    return np.asarray(sample_nozzle_inner_contour({})[0], dtype=float)


def _gercek_duvar(ni):
    """Duvar dizileri [m] — ÖLÇÜM REFERANSI (ızgara kurmak için DEĞİL).

    Yeniden örnekleme kuralı burada elle yazılır çünkü bekçilerin ızgara
    düğümlerini karşılaştıracağı BAĞIMSIZ bir doğruluk kaynağı gerekir.
    Kural ürününkinden saparsa test_yaka_DUVAR_ve_EKSEN_dugumlerini_TAM_korur
    kırmızıya düşer (``g.R[:, -1] == r`` bit-eşitliği) — kopya sürüklenemez.
    Izgaralar ÜRÜN GİRİŞ NOKTASINDAN kurulur (``_yaka_grid``).
    """
    # ÖH D37 A3a cfd-kok-a (OH-DK-15; Berke Sunum 3a onayı 24 Eyl): ürün
    # kuralı değişti — konturun boğaz düğümü (ilk min r) ZORUNLU istasyon,
    # iki yanda düzgün parçalar (n_sol = round(ni·(z_t−z0)/L), 1 ≤ n_sol ≤
    # ni−1; boğaz bir düzgün istasyona bağıl 1e-12 içinde düşüyorsa düz
    # linspace). Kural burada ELLE ve bağımsız yazılır (bekçinin amacı);
    # kopya sürüklenirse düğüm bit-eşitliği kırmızıya düşer.
    pts = _gercek_kontur_mm()
    z0, z1 = float(pts[0, 0]), float(pts[-1, 0])
    z_t = float(pts[int(np.argmin(pts[:, 1])), 0])
    duz = np.linspace(z0, z1, ni + 1)
    if not (z0 < z_t < z1) or np.min(np.abs(duz - z_t)) <= 1e-12 * (z1 - z0):
        z_mm = duz
    else:
        n_sol = min(max(int(round(ni * (z_t - z0) / (z1 - z0))), 1), ni - 1)
        z_mm = np.concatenate([np.linspace(z0, z_t, n_sol + 1),
                               np.linspace(z_t, z1, ni - n_sol + 1)[1:]])
    return z_mm * 1e-3, np.interp(z_mm, pts[:, 0], pts[:, 1]) * 1e-3


def _yaka_grid(ni=192, nj=48, d1=YAKA_D1, yaka=None):
    """Gerçek kontur ızgarası — ÜRÜNÜN GİRİŞ NOKTASINDAN (çadır yok).

    Parti 38'in devir kalemi "build_nozzle_grid gerdirme parametresi
    taşımıyor, test tarafında yeniden örneklendi" idi; taşıma parti 39
    A4'te yazıldı ve bu yardımcı parti 40'ta ona bağlandı. Bağlamanın
    ölçülen bedeli SIFIR (elle yeniden örneklenmiş duvarla kurulan ızgara
    ile bit-aynı — test_lule_yardimcisi_gerdirmeyi_GERCEKTEN_tasiyor);
    kazancı, aşağıdaki BÜTÜN yaka/gerdirme ölçümlerinin artık ürünün
    kendi çağrı yolundan geçmesidir (anahtar-kelime düşürme mutasyonları
    M1-M3 bu yüzden kırmızı verir).
    """
    return build_nozzle_grid(_gercek_kontur_mm(), ni, nj, first_cell_m=d1,
                             stretch='tanh', wall_collar=yaka)


def _kalite(grid):
    from hrma.cfd import steady
    from hrma.cfd.euler_core import precompute_geometry
    from hrma.cfd.gradients import precompute_gradient_geometry

    return steady.wall_grid_quality(grid, precompute_geometry(grid),
                                    precompute_gradient_geometry(grid))


def test_yaka_KAPALIYKEN_dugumler_bit_ayni_iki_dalda_da():
    """(a) Varsayılan dal: yaka kodu HİÇ çalışmaz — düğümler bit-aynı."""
    z, r = _duvar()
    duz = build_grid_from_wall(z, r, GERDIRME_NJ)
    duz_ref = build_grid_from_wall(z, r, GERDIRME_NJ, wall_collar=None)
    assert np.array_equal(duz.Z, duz_ref.Z)
    assert np.array_equal(duz.R, duz_ref.R)
    assert duz.wall_collar is None
    # Düzgün dalın dondurulmuş ifadesi (Euler bit-özdeşliğinin ızgara ayağı)
    assert np.array_equal(
        duz.R, r[:, None] * np.linspace(0.0, 1.0, GERDIRME_NJ + 1)[None, :])
    assert np.array_equal(duz.Z, np.repeat(z[:, None], GERDIRME_NJ + 1, 1))
    # Gerdirilmiş dal da yaka kapalıyken kaymaz
    d1 = _hedef_kalinlik(kat=0.25)
    a = build_grid_from_wall(z, r, GERDIRME_NJ, first_cell_m=d1)
    b = build_grid_from_wall(z, r, GERDIRME_NJ, first_cell_m=d1,
                             wall_collar=None)
    for alan in ('Z', 'R', 'volume', 'face_i', 'face_j'):
        assert np.array_equal(getattr(a, alan), getattr(b, alan)), alan


def test_yaka_kapaliyken_lule_yardimcisi_da_BIT_AYNI():
    """build_nozzle_grid'in yeni anahtar-kelimeleri varsayılanda etkisiz."""
    pts = np.stack([np.linspace(0.0, 300.0, 41),
                    1e3 * lule_duvar_yaricapi(np.linspace(0.0, 0.30, 41))],
                   axis=1)
    a = build_nozzle_grid(pts, 32, 12)
    b = build_nozzle_grid(pts, 32, 12, first_cell_m=None, wall_collar=None)
    assert np.array_equal(a.R, b.R) and np.array_equal(a.Z, b.Z)
    assert a.radial_distribution == 'uniform' and a.wall_collar is None


def test_yaka_DUVAR_ve_EKSEN_dugumlerini_TAM_korur():
    """(b) Boğaz/çıkış istasyonları ve r = 0 sözleşmesi — yapısal gerçek."""
    z, r = _gercek_duvar(192)
    g = _yaka_grid(yaka=WallCollar())
    assert np.array_equal(g.R[:, -1], r), 'duvar düğümü konturdan kaydı'
    assert np.array_equal(g.Z[:, -1], z), 'duvar istasyonu kaydı (boğaz!)'
    assert np.all(g.R[:, 0] == 0.0), 'eksen düğümü TAM 0 değil'
    assert np.array_equal(g.Z[:, 0], z), 'eksen istasyonu kaydı'
    assert np.all(np.linalg.norm(g.face_j[:, 0, :], axis=-1) == 0.0)
    # Boğaz istasyonunun İNDİSİ de yerinde (çözücü onu r'den bulur)
    g0 = _yaka_grid()
    assert int(np.argmin(g.R[:-1, -1])) == int(np.argmin(g0.R[:-1, -1]))


def test_yaka_radyal_monoton_ve_hacimler_pozitif():
    """Çarpık gerçek konturda bile j yönü monoton, hücreler dönmemiş."""
    g = _yaka_grid(yaka=WallCollar())
    assert np.all(np.diff(g.R, axis=1) > 0.0)
    assert np.all(g.volume > 0.0) and np.all(g.area_planar > 0.0)


def test_yaka_hacmi_YALNIZ_giris_cikis_kolonlarindan_degistirir():
    """Yakanın alanı DEĞİŞTİRDİĞİ tek yer ölçülür ve beyanla sınırlanır.

    İç düğüm hareketi komşu hücrelerde birebir sadeleşir; sınır ise
    duvar (sabit) + eksen (sabit) + giriş/çıkış kolonlarıdır. Dolayısıyla
    hacim yalnız uç kolonlar kaydığı kadar değişir — ve uç segmentte
    duvar eğimi TAM sıfırsa hiç değişmez. İkisi de ÖLÇÜLÜR: silindirik
    uçlu konturda bit-özdeşlik, gerçek konturda (çıkış açısı 15°,
    varsayılan yaka 4/nj//2 = 4/24) bağıl 7,90e-05 — çıkış yüzü eksenel
    hücrenin %8'i kadar sapıyor. Bu, harman genişliğinin BEDELİDİR ve
    varsayılanı seçen ölçümün ikinci sütunudur (WallCollar docstring'i:
    harman eksene kadar açılsaydı sapma yarım hücreye, hacim 3,9e-03'e
    çıkardı).
    """
    zc = np.linspace(0.0, 0.2, 65)
    rc = np.where(zc < 0.05, 0.03,
                  np.where(zc > 0.15, 0.02, 0.03 - (zc - 0.05) * 0.1))
    ortak = dict(first_cell_m=1.0e-4, stretch='tanh')
    a = build_grid_from_wall(zc, rc, 24, **ortak)
    b = build_grid_from_wall(zc, rc, 24, wall_collar=WallCollar(2, 2),
                             **ortak)
    assert float(np.sum(a.volume)) == float(np.sum(b.volume)), (
        'silindirik uçlu konturda hacim BİT-ÖZDEŞ değil — o hâlde yaka '
        'iç düğümlerden de hacim sızdırıyor demektir')
    assert np.array_equal(a.Z[0], b.Z[0]) and np.array_equal(a.Z[-1], b.Z[-1])
    assert b.wall_collar['inlet_axial_shift_m'] == 0.0
    assert b.wall_collar['outlet_axial_shift_m'] == 0.0

    g = _yaka_grid(yaka=WallCollar())
    h = _yaka_grid()
    dv = abs(float(np.sum(g.volume)) - float(np.sum(h.volume))) \
        / float(np.sum(h.volume))
    assert dv == pytest.approx(7.90e-05, rel=5e-2)
    y = g.wall_collar
    assert y['blend_layers'] == 24 and y['blend_layers_requested'] is None
    assert y['outlet_axial_shift_m'] == pytest.approx(7.89e-05, rel=5e-3)
    assert y['outlet_axial_shift_m'] < 0.10 * float(g.Z[1, 0] - g.Z[0, 0])
    # Harman eksene kadar açılsaydı bedel büyürdü: çıkış yüzü sapması
    # 5,6 kat (7,89e-05 → 4,44e-04 m), hacim değişimi 50 kat (7,9e-05 →
    # 3,9e-03). Varsayılanın ikinci gerekçesi — ölçülür, iddia edilmez.
    genis = _yaka_grid(yaka=WallCollar(4, 44)).wall_collar
    assert genis['outlet_axial_shift_m'] > 5.0 * y['outlet_axial_shift_m']


def test_yaka_kapanis_ozdeslikleri_makine_sifirinda():
    """Σ S_z = 0 ve Σ S_r = 2π·A yakalı ızgarada da (metrikler genel)."""
    g = _yaka_grid(yaka=WallCollar())
    s_z = (g.face_i[1:, :, 0] - g.face_i[:-1, :, 0]
           + g.face_j[:, 1:, 0] - g.face_j[:, :-1, 0])
    s_r = (g.face_i[1:, :, 1] - g.face_i[:-1, :, 1]
           + g.face_j[:, 1:, 1] - g.face_j[:, :-1, 1])
    olcek = np.max(np.abs(g.face_j[:, 1:, 1]))
    assert np.max(np.abs(s_z)) < 1e-12 * olcek
    assert np.allclose(s_r, 2.0 * np.pi * g.area_planar, rtol=1e-12,
                       atol=1e-12 * olcek)


def test_yaka_ilk_hucre_NORMAL_kalinligi_hedefin_KENDISI_H_izgarada_cos_alfa_kati():
    """(c) Ölçüm: yakada ulaşılan normal kalınlık = first_cell_m.

    H-ızgarada aynı parametre RADYAL kalınlıktır ve duvar-normal karşılığı
    onun cos α katıdır — gerçek konturun en dar istasyonunda ÖLÇÜLDÜ:
    7,4156e-06 / 1,0e-05 = 0,7416 = cos(42,135°). y⁺ hedefi H-ızgarada
    bu yüzden istasyondan istasyona kayar; yakada kaymaz.
    """
    g = _yaka_grid(yaka=WallCollar())
    y = g.wall_collar
    assert y['first_cell_normal_m_min'] == pytest.approx(YAKA_D1, rel=2e-5)
    assert y['first_cell_normal_m_max'] == pytest.approx(YAKA_D1, rel=2e-5)
    h_min = y['first_cell_normal_without_collar_m_min']
    assert h_min == pytest.approx(YAKA_D1 * np.cos(np.radians(42.135)),
                                  rel=1e-3), (
        'H-ızgaranın duvar-normal ilk hücresi cos α katı DEĞİL — o hâlde '
        'yakanın y⁺ iddiasının dayanağı ölçülmemiş demektir')
    assert h_min / YAKA_D1 == pytest.approx(0.7416, abs=5e-4)
    # Beyan ızgaradan YENİDEN hesaplanabilir olmalı (kopya sayı değil)
    n_node, _ = wall_node_normals(*_gercek_duvar(192))
    v = np.stack([g.Z[:, -2] - g.Z[:, -1], g.R[:, -2] - g.R[:, -1]], axis=-1)
    elde = np.abs(v[:, 0] * n_node[:, 0] + v[:, 1] * n_node[:, 1])
    assert float(np.min(elde)) == pytest.approx(
        y['first_cell_normal_m_min'], rel=1e-12)


def test_yaka_carpikligi_dusurur_ama_AR_carpi_DELTA_ALFAYI_KALDIRMAZ():
    """(c)+(d) ÖLÇÜM: çarpıklık çöker, dinamik metrik neredeyse durur.

    Bu bekçi bir ÇAREYİ değil bir SINIRI kilitler. Δα duvar poliçizgisinin
    büyüklüğüdür ve duvar düğümleri kaymadığı için BİT-AYNI kalır; AR·Δα
    yalnız AR'nin 1/cos α kadar küçülmesi kadar iner. Yaka bu yüzden
    parti 39 A1'in ölçtüğü dinamik kararsızlığı çözemez — ve bu, koşudan
    ÖNCE bilinen bir ölçümdü.
    """
    h = _kalite(_yaka_grid())
    o = _kalite(_yaka_grid(yaka=WallCollar()))
    assert h['max_wall_skew_deg'] == pytest.approx(42.135, abs=0.01)
    # ÖH D37 A3a cfd-kok-a (OH-DK-15; Berke Sunum 3a onayı 24 Eyl): ızgara
    # artık boğaz düğümünü zorunlu istasyon yapıyor; aşağıdaki ölçülmüş
    # sayılar yeni istasyonlarla YENİDEN ÖLÇÜLDÜ (niteliksel iddialar aynen).
    assert o['max_wall_skew_deg'] == pytest.approx(2.097, abs=0.01), (
        'yakalı ızgarada duvar çarpıklığı ölçülen 2,097°\'den kaydı (eski istasyonlarla 2,122°)')
    assert o['max_wall_skew_deg'] < 0.06 * h['max_wall_skew_deg']
    # Δα: KONTUR büyüklüğü — bit-aynı
    assert o['max_wall_angle_change_deg'] == h['max_wall_angle_change_deg']
    # AR·Δα: yalnız AR'nin cos α payı kadar iner (%2 mertebesinde)
    oran = o['max_aspect_x_angle_change'] / h['max_aspect_x_angle_change']
    assert 0.95 < oran < 1.0, (
        f'AR·Δα oranı {oran:.4f} — yaka bu metriği ÖLÇÜLENDEN farklı '
        'biçimde değiştiriyor; dosyanın (d) iddiası güncellenmeli')
    # boğaz istasyonuyla yeniden ölçüldü (eski 17,969 / 17,690)
    assert h['max_aspect_x_angle_change'] == pytest.approx(17.192, rel=2e-3)
    assert o['max_aspect_x_angle_change'] == pytest.approx(17.153, rel=2e-3)


def test_yaka_conftest_lulesinde_dinamik_metrigi_4_HANEDE_degistirmez():
    """(d)'nin en sert hâli: KAPI vakasında AR·Δα HİÇ oynamıyor.

    Sebep ölçülü: AR·Δα'nın tepesi boğazda, orada duvar açısı sıfırdan
    geçiyor — yakanın taşıyacağı düğüm yok. Parti 39 A1'in ıraksama
    imzası da (i = 78-80, boğaz i = 77) tam orada.
    """
    z = np.linspace(0.0, 0.30, 193)
    r = lule_duvar_yaricapi(z)
    ortak = dict(first_cell_m=1.51e-6, stretch='tanh')
    h = _kalite(build_grid_from_wall(z, r, 48, **ortak))
    o = _kalite(build_grid_from_wall(z, r, 48, wall_collar=WallCollar(),
                                     **ortak))
    assert h['max_aspect_x_angle_change'] == pytest.approx(8.303, rel=1e-3)
    assert o['max_aspect_x_angle_change'] == pytest.approx(
        h['max_aspect_x_angle_change'], rel=1e-4)
    assert o['max_wall_skew_deg'] < 0.25 < 11.0 < h['max_wall_skew_deg']


def test_yaka_harman_DAR_olunca_metrik_TEPESI_uretir_genis_olunca_URETMEZ():
    """(e) Harmanın kendi tepesini üretmediği İDDİASI ölçülür.

    Taban: yakasız ızgaranın maksimum radyal komşu hacim oranı. Geniş
    harman bu tabanı AŞMAZ; dar harman ölçülebilir biçimde aşar ve en
    dar hâlde (blend = 1, derin yaka) hücre alanını NEGATİFE çevirir.
    """
    taban = _kalite(_yaka_grid())['max_cell_volume_ratio_j']
    assert taban == pytest.approx(2.9740, rel=1e-3)
    for L, B in ((4, 4), (8, 4), (12, 6), (4, 2)):
        oran = _kalite(_yaka_grid(yaka=WallCollar(L, B)))[
            'max_cell_volume_ratio_j']
        assert oran == pytest.approx(taban, rel=1e-9), (
            f'{L}/{B}: harman hacim oranını {oran:.4f} yaptı (taban '
            f'{taban:.4f}) — harman yeni bir değişim tepesi üretiyor')
    # ÖH D37 A3a cfd-kok-a (OH-DK-15; Berke Sunum 3a onayı 24 Eyl): ızgara
    # artık boğaz düğümünü zorunlu istasyon yapıyor; aşağıdaki ölçülmüş
    # sayılar yeni istasyonlarla YENİDEN ÖLÇÜLDÜ (niteliksel iddialar aynen).
    for L, B, beklenen in ((3, 1, 5.7224), (4, 1, 194.49), (6, 2, 4.1602),
                           (6, 3, 3.7330)):
        oran = _kalite(_yaka_grid(yaka=WallCollar(L, B)))[
            'max_cell_volume_ratio_j']
        assert oran == pytest.approx(beklenen, rel=5e-3)
        assert oran > 1.1 * taban
    # En sert hâl: dar harman + derin yaka ızgarayı KATLAR (alan kapısı)
    with pytest.raises(ValueError, match='Negatif/sıfır düzlemsel hücre'):
        _yaka_grid(yaka=WallCollar(6, 1))


def test_harmanin_URETTIGI_degisim_OLCULUR_ve_gizlenmez():
    """Kalemin asıl şartı: harman YENİ bir değişim tepesi üretiyor mu?

    Ölçü, aralık oranının KENDİSİ değil katman başına DEĞİŞİMİdir
    (parti 38-39: kıran şey seviye değil değişim). Yakasız gerdirilmiş
    ızgarada 0,0120; harman onu kaçınılmaz olarak yükseltir — DÜRÜST
    SONUÇ budur ve beyanda yayımlanır. En iyi ölçülen ayar 8/8 (0,1839),
    en kötüsü 3/1 (2,0165); sıralama κ'nın ayrık adımını izler.
    """
    s0 = np.hypot(np.diff(_yaka_grid().Z, axis=-1),
                  np.diff(_yaka_grid().R, axis=-1))
    o0 = s0[:, :-1] / s0[:, 1:]
    taban = float(np.max(np.abs(np.diff(o0, axis=-1))))
    assert taban == pytest.approx(0.0120, abs=5e-4)
    olculen = {}
    for L, B in ((1, 4), (4, 4), (8, 8), (12, 6), (3, 1)):
        y = _yaka_grid(yaka=WallCollar(L, B)).wall_collar
        olculen[(L, B)] = y['spacing_ratio_change_max']
        # Beyan ızgaradan yeniden hesaplanabilir olmalı
        g = _yaka_grid(yaka=WallCollar(L, B))
        s = np.hypot(np.diff(g.Z, axis=-1), np.diff(g.R, axis=-1))
        o = s[:, :-1] / s[:, 1:]
        assert y['spacing_ratio_change_max'] == pytest.approx(
            float(np.max(np.abs(np.diff(o, axis=-1)))), rel=1e-12)
    assert olculen[(8, 8)] == pytest.approx(0.1839, rel=2e-2)
    assert olculen[(4, 4)] == pytest.approx(0.6234, rel=2e-2)
    assert olculen[(3, 1)] == pytest.approx(2.0165, rel=2e-2)
    assert olculen[(8, 8)] < olculen[(12, 6)] < olculen[(1, 4)] \
        < olculen[(4, 4)] < olculen[(3, 1)], (
        'harman payının ölçülen sıralaması değişti — κ adımı açıklaması '
        'artık geçerli olmayabilir')
    assert all(v > 10.0 * taban for v in olculen.values()), (
        'harman tabana yakın bir değişim üretiyor görünüyor — bu ÖLÇÜLEN '
        'gerçek değil; dosyanın dürüst okuması yanlışlanmış olurdu')


def test_yaka_DERINLIGI_ic_katmanlarin_duvar_normaliyle_hizasini_belirler():
    """layers'ı seçen ölçüm: iç j-çizgilerinin duvar normaliyle açısı.

    Duvar YÜZÜNÜN çarpıklığı layers = 1'de doyar (duvara yalnız birinci
    hücre değer). Derinlik, sınır tabakasının İÇİNDEKİ arayüzler içindir:
    ayrık duvar-normal türev j çizgisi boyunca alınır. layers HİZALI
    BÖLGENİN DERİNLİĞİDİR — doyan bir kazanç değil; varsayılan 4'ün
    gerekçesi kapsadığı derinliktir (ilk hücrenin ~5,1 katı = y⁺ ≈ 1
    ızgarasında viskoz alt tabaka).
    """
    from hrma.cfd.gradients import cell_centroids
    from hrma.cfd.grid_axisym import wall_node_normals

    z, r = _gercek_duvar(192)
    _, n_seg = wall_node_normals(z, r)

    def aci_profili(g):
        xc = cell_centroids(g)
        v = xc[:, :-1] - xc[:, 1:]              # duvardan eksene doğru
        v = v / np.linalg.norm(v, axis=-1)[..., None]
        cos = np.abs(v[..., 0] * n_seg[:, None, 0]
                     + v[..., 1] * n_seg[:, None, 1])
        p = np.degrees(np.arccos(np.clip(cos, 0.0, 1.0))).max(axis=0)
        return p[::-1]                       # 0 = duvara EN YAKIN arayüz

    h = aci_profili(_yaka_grid())
    assert h[0] == pytest.approx(41.85, abs=0.05), (
        'H-ızgarada j çizgisi duvar normaliyle α açısı yapmalı')
    assert np.all(h[:8] > 41.8)                 # her katmanda aynı
    olcum = {L: aci_profili(_yaka_grid(yaka=WallCollar(L, 24)))
             for L in (1, 2, 4, 8)}
    for L in olcum:
        # yeni istasyonlarla yeniden ölçüldü (eski 2,25°): 2,516-2,519°
        assert olcum[L][0] == pytest.approx(2.517, abs=0.02), (
            'duvara en yakın arayüz layers\'tan bağımsız olmalı — duvar '
            'yüzü çarpıklığı L = 1\'de zaten doyuyor')
    # ALTINCI arayüz derinliği AYIRT EDİYOR (ölçülen tablo)
    altinci = {L: p[5] for L, p in olcum.items()}
    # ÖH D37 A3a cfd-kok-a (OH-DK-15; Berke Sunum 3a onayı 24 Eyl): ızgara
    # artık boğaz düğümünü zorunlu istasyon yapıyor; aşağıdaki ölçülmüş
    # sayılar yeni istasyonlarla YENİDEN ÖLÇÜLDÜ (niteliksel iddialar aynen).
    assert altinci[1] == pytest.approx(8.302, rel=2e-2)
    assert altinci[2] == pytest.approx(5.454, rel=2e-2)
    assert altinci[4] == pytest.approx(2.603, rel=2e-2)
    assert altinci[8] == pytest.approx(2.540, rel=2e-2)
    assert altinci[1] > altinci[2] > altinci[4] > altinci[8]
    assert olcum[1][7] == pytest.approx(17.21, rel=2e-2)
    assert olcum[4][7] == pytest.approx(6.261, rel=2e-2)
    # Varsayılan yaka bu profili veriyor ve 4 katmanın derinliği ilk
    # hücrenin ~5,1 katı (y⁺ ≈ 1 ızgarasında viskoz alt tabaka)
    v = _yaka_grid(yaka=WallCollar())
    assert aci_profili(v)[5] == pytest.approx(altinci[4], rel=1e-12)
    y = v.wall_collar
    assert y['collar_depth_m_max'] / y['first_cell_normal_m_max'] == \
        pytest.approx(5.1, rel=5e-2)


def test_DAR_harman_kendi_carpikligini_uretir_VARSAYILAN_genislik_bunun_olcumu():
    """Varsayılanı seçen ölçüm: harman genişliği ↔ Green-Gauss çarpıklığı.

    Yaka duvar çarpıklığını düşürürken DAR harmanda gradyan katmanının
    KENDİ çarpıklığını (|yüz orta − merkez çifti ortası| / |LR|) yükseltir
    — yani bir kusuru başka kusurla takas eder. Ölçülen doyma noktası
    B = nj//2'dir ve varsayılan odur. Bedeli de ölçülür: çıkış yüzünün
    eksenel sapması B ile büyür.
    """
    from hrma.cfd.gradients import cell_centroids, face_midpoints

    def gg_carpiklik(g):
        xc = cell_centroids(g)
        _, mj = face_midpoints(g)
        d = mj[:, 1:-1] - 0.5 * (xc[:, :-1] + xc[:, 1:])
        boy = np.linalg.norm(xc[:, 1:] - xc[:, :-1], axis=-1)
        return float(np.max(np.linalg.norm(d, axis=-1) / boy))

    taban = gg_carpiklik(_yaka_grid())
    assert taban == pytest.approx(0.0385, abs=5e-4)
    olcum = {B: gg_carpiklik(_yaka_grid(yaka=WallCollar(4, B)))
             for B in (4, 8, 12, 16, 20, 24)}
    assert olcum[4] == pytest.approx(0.2431, rel=2e-2)
    assert olcum[4] > 5.0 * taban, (
        'dar harman artık kendi çarpıklığını üretmiyor — varsayılanın '
        '(nj//2) gerekçesi ölçümle yalanlanmış olur')
    # ÖH D37 A3a cfd-kok-a (OH-DK-15; Berke Sunum 3a onayı 24 Eyl): ızgara
    # artık boğaz düğümünü zorunlu istasyon yapıyor; aşağıdaki ölçülmüş
    # sayılar yeni istasyonlarla YENİDEN ÖLÇÜLDÜ (niteliksel iddialar aynen).
    # Doyma noktası eski istasyonlarda B = 16'ydı; boğaz istasyonuyla B = 20'ye
    # kaydı (ölçüldü: B = 20…44 hepsi 0,04095). Varsayılan nj//2 = 24 doymuş
    # PLATODA — gerekçe aynen geçerli.
    assert olcum[4] > olcum[8] > olcum[12] > olcum[16] > olcum[20], 'doyma tersine dönmüş'
    assert olcum[20] == pytest.approx(olcum[24], rel=1e-3), (
        'B = nj//2 artık doymuş platoda değil')
    assert olcum[24] == pytest.approx(0.04095, rel=2e-2)
    # Varsayılan GERÇEKTEN nj//2 (ve doymuş değerin kendisi)
    varsayilan = _yaka_grid(yaka=WallCollar())
    assert varsayilan.wall_collar['blend_layers'] == 24
    assert gg_carpiklik(varsayilan) == pytest.approx(olcum[24], rel=1e-12)
    # nj değişince harman ONUNLA ölçekleniyor (katman sayısı sabit değil)
    kaba = _yaka_grid(ni=48, nj=24, yaka=WallCollar())
    assert kaba.wall_collar['blend_layers'] == 12
    assert WallCollar().effective_blend(64) == 32


def test_harman_agirligi_C2_ve_kappa_ADIMI_blend_ile_MONOTON_DEGIL():
    """κ profili: uçlarda 1/0, C² pürüzsüz; adım tablosu ölçülü.

    Adımın monoton olmayışı (B = 3 → 0,5802 > B = 2 → 0,5000) bir
    ayrıklaştırma gerçeğidir: tek sayıda katmanda orta örnek
    smootherstep'in en dik noktasına (t = 0,5) düşer. "Harmanı genişlet"
    reçetesinin tek başına yetmediği ancak bu ölçümle görülür.
    """
    assert COLLAR_BLEND_PROFILE == 'smootherstep'
    k = collar_weights(48, 4, 4)
    assert k.shape == (49,)
    assert k[-1] == 1.0 and k[-5] == 1.0            # duvar + 4 katman
    assert np.all(k[:48 - 8 + 1] == 0.0)            # harman EKSENE ulaşmaz
    assert np.all(np.diff(k) >= 0.0)
    # C² SÜREKLİ profildir; ayrık ikinci fark bu yüzden 1/B² gibi söner.
    # ÖLÇÜLÜR (B ikiye katlandıkça oran ~4): doğrusal harmanda bu oran 1
    # kalırdı (kenarda sabit bir sıçrama). Profilin mertebesi budur.
    d2 = [float(np.max(np.abs(np.diff(collar_weights(4 * B, 2, B), 2))))
          for B in (50, 100, 200)]
    assert d2[0] / d2[1] == pytest.approx(4.0, rel=0.05)
    assert d2[1] / d2[2] == pytest.approx(4.0, rel=0.05)
    adim = {B: float(np.max(np.abs(np.diff(collar_weights(48, 4, B)))))
            for B in (1, 2, 3, 4, 5, 6, 8, 12)}
    assert adim[1] == 1.0
    assert adim[2] == pytest.approx(0.5000, abs=5e-4)
    assert adim[3] == pytest.approx(0.5802, abs=5e-4)
    assert adim[3] > adim[2], 'κ adımı blend_layers\'ta monoton çıktı — '\
        'ölçülen ayrıklaştırma gerçeği kaybolmuş'
    assert adim[4] == pytest.approx(0.3965, abs=5e-4)
    assert adim[8] == pytest.approx(0.2248, abs=5e-4)
    g = _yaka_grid(yaka=WallCollar(4, 4))
    assert g.wall_collar['max_kappa_step'] == pytest.approx(adim[4], rel=1e-12)


def test_duvar_normali_ic_yonlu_ve_dejenerasyon_YAPISAL_olarak_imkansiz():
    """n_r < 0 her segmentte (z artan) → düğüm normali daima tanımlı."""
    z, r = _gercek_duvar(192)
    n_node, n_seg = wall_node_normals(z, r)
    assert np.all(n_seg[:, 1] < 0.0), 'segment normali eksene bakmıyor'
    assert np.all(n_node[:, 1] < 0.0)
    assert np.allclose(np.linalg.norm(n_node, axis=-1), 1.0, atol=1e-15)
    # Uç düğümler tek yanlı: komşu segmentin normalinin KENDİSİ
    assert np.array_equal(n_node[0], n_seg[0])
    assert np.array_equal(n_node[-1], n_seg[-1])
    # Düz koni: bütün normaller aynı, açı = koni açısı
    zc = np.linspace(0.0, 0.1, 33)
    nk, _ = wall_node_normals(zc, 0.02 + zc * np.tan(np.radians(42.135)))
    assert np.allclose(np.degrees(np.arccos(-nk[:, 1])), 42.135, atol=1e-9)


def test_yaka_KESISME_kapisi_ates_eder_ve_kapatilabilir():
    """Normal kesişme tavanı: içbükey yayda derin yaka REDDEDİLİR.

    Vaka: küçük yarıçaplı (5 mm) içbükey duvar yayı — normaller yayın
    merkezinde kesişir ve kesişme mesafesi ÖLÇÜLEN yarıçapın kendisidir.
    Kapı kapatılırsa ikinci savunma (hücre alanı) devreye girer: yani
    kapatmak SESSİZ katlanmış bir ızgara vermez, başka bir hata verir.
    """
    Rc = 0.005
    aci = np.linspace(0.0, 0.9, 41)
    z = Rc * np.sin(aci)
    r = 0.02 - Rc * (1.0 - np.cos(aci))
    ortak = dict(first_cell_m=2.0e-4, stretch='tanh')
    with pytest.raises(ValueError, match='kesişme mesafesini'):
        build_grid_from_wall(z, r, 26, wall_collar=WallCollar(20, 4), **ortak)
    with pytest.raises(ValueError, match='Negatif/sıfır düzlemsel hücre'):
        build_grid_from_wall(
            z, r, 26, wall_collar=WallCollar(
                20, 4, require_normal_clearance=False), **ortak)
    # Sığ yaka AYNI geometride geçer (tavan bir ÇARPIM değil MESAFEDİR) ve
    # ölçülen kesişme mesafesi yayın yarıçapıdır
    sig = build_grid_from_wall(z, r, 26, wall_collar=WallCollar(2, 2),
                               **ortak)
    assert sig.wall_collar['normal_crossing_min_m'] == pytest.approx(
        Rc, rel=1e-3)
    assert sig.wall_collar['normal_offset_to_crossing_ratio'] < 1.0


def test_yaka_kapilari_sessiz_varsayilana_DUSMEZ():
    """Katman sayıları, nj sığması ve tip kapısı."""
    z, r = _duvar()
    for bozuk in (0, -1, 2.5):
        with pytest.raises(ValueError, match='en az 1 olan bir TAM SAYI'):
            WallCollar(layers=bozuk)
        with pytest.raises(ValueError, match='en az 1 olan bir TAM SAYI'):
            WallCollar(blend_layers=bozuk)
    with pytest.raises(ValueError, match='radyal hücre sayısını'):
        build_grid_from_wall(z, r, 6, wall_collar=WallCollar(4, 4))
    with pytest.raises(ValueError, match='WallCollar örneği olmalı'):
        build_grid_from_wall(z, r, GERDIRME_NJ,
                             wall_collar={'layers': 4, 'blend_layers': 4})


def test_yaka_gerdirmesiz_de_kurulur_ve_beyan_iki_kaynagi_birlestirir():
    """Yaka gerdirmeden BAĞIMSIZ bir seçenektir (düzgün dağılımla da)."""
    z, r = _gercek_duvar(96)
    g = build_grid_from_wall(z, r, 24, wall_collar=WallCollar(2, 2))
    assert g.radial_distribution == 'uniform'
    assert g.radial_stretch is None and g.wall_collar is not None
    assert np.all(np.diff(g.R, axis=1) > 0.0) and np.all(g.volume > 0.0)
    ger = _yaka_grid(yaka=WallCollar())
    assert 'DÜZGÜN' not in ger._basis and 'GERDİRİLMİŞ' in ger._basis
    assert 'DUVAR-NORMAL YAKA' in ger._basis, (
        'yaka beyanı ızgaranın künyesine girmiyor — koşu çıktısını okuyan '
        'ızgaranın topolojisini göremez'
    )


# ===========================================================================
# 8) PARAMETRE TAŞIMA — build_nozzle_grid (parti 38 devri, parti 40 kapanışı)
#
# ÖLÇÜLEN KUSUR (parti 40, mutasyon M1-M3 taban sürümde koşuldu):
# taşıma parti 39 A4'te YAZILDI ama BEKÇİSİZDİ — üç anahtar-kelimenin
# HERHANGİ BİRİ çağrıdan düşürüldüğünde süit (62 test) YEŞİL kalıyordu.
# Sebep: tek bekçi (test_yaka_kapaliyken_lule_yardimcisi_da_BIT_AYNI)
# yalnız VARSAYILANIN etkisizliğini ölçüyordu; varsayılan zaten None
# olduğu için None'a sabitleyen mutasyon onu kıramazdı. Aşağıdaki üç
# bekçi VARSAYILAN DIŞI değerlerin gerçekten ulaştığını ölçer.
# ===========================================================================

def test_lule_yardimcisi_gerdirmeyi_GERCEKTEN_tasiyor():
    """first_cell_m + stretch build_grid_from_wall'a ULAŞIYOR (M1, M3)."""
    pts = _gercek_kontur_mm()
    ni, nj, d1 = 48, 24, YAKA_D1
    for aile in AILELER:
        g = build_nozzle_grid(pts, ni, nj, first_cell_m=d1, stretch=aile)
        # (a) gerdirme GERÇEKTEN kuruldu (düşürülseydi 'uniform' olurdu)
        assert g.radial_distribution == aile, (
            f'build_nozzle_grid stretch={aile!r} taşımıyor — '
            f'kurulan dağılım {g.radial_distribution!r}')
        assert g.radial_stretch is not None
        # (b) HEDEF tutturuldu (first_cell_m düşürülseydi dal hiç açılmazdı)
        assert g.radial_stretch['first_cell_rel_error_max'] < 1e-9
        assert g.radial_stretch['first_cell_target_m'] == d1
        # (c) elle yeniden örneklenmiş duvarla kurulan ızgarayla BİT-AYNI:
        #     yardımcının çadırı sökmesinin bedeli SIFIR
        z, r = _gercek_duvar(ni)
        el = build_grid_from_wall(z, r, nj, first_cell_m=d1, stretch=aile)
        assert np.array_equal(g.R, el.R) and np.array_equal(g.Z, el.Z)


def test_lule_yardimcisi_yakayi_GERCEKTEN_tasiyor():
    """wall_collar build_grid_from_wall'a ULAŞIYOR (M2)."""
    pts = _gercek_kontur_mm()
    yaka = WallCollar(2, 2)
    g = build_nozzle_grid(pts, 48, 24, first_cell_m=YAKA_D1, stretch='tanh',
                          wall_collar=yaka)
    assert g.wall_collar is not None, (
        'build_nozzle_grid wall_collar taşımıyor — yaka sessizce düştü')
    assert g.wall_collar['layers'] == 2 and g.wall_collar['blend_layers'] == 2
    # Yakanın ÖZÜ: iç düğümler eksenel kaydı (H ızgarada kayma TAM sıfırdır)
    assert g.wall_collar['max_axial_node_shift_m'] > 0.0
    z, r = _gercek_duvar(48)
    el = build_grid_from_wall(z, r, 24, first_cell_m=YAKA_D1, stretch='tanh',
                              wall_collar=yaka)
    assert np.array_equal(g.R, el.R) and np.array_equal(g.Z, el.Z)


def test_test_tarafi_CADIR_sokuldu_yapisal_olarak():
    """Yaka/gerdirme ölçümleri ÜRÜNÜN çağrı yolundan geçiyor.

    Yapısal kanıt: ızgara fabrikası build_nozzle_grid'i çağırır ve
    build_grid_from_wall'u ÇAĞIRMAZ. Çadır geri kurulursa (yardımcı yine
    elle örnekleyip build_grid_from_wall'a giderse) yukarıdaki üç
    mutasyon yeniden hayatta kalırdı — bu bekçi o gerilemeyi görür.
    """
    agac = ast.parse(inspect.getsource(_yaka_grid))
    adlar = {d.func.id for d in ast.walk(agac)
             if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)}
    assert 'build_nozzle_grid' in adlar, (
        '_yaka_grid ürünün giriş noktasını kullanmıyor — çadır geri geldi')
    assert 'build_grid_from_wall' not in adlar, (
        '_yaka_grid duvar dizileriyle doğrudan ızgara kuruyor: taşıma '
        'bekçileri yine yalnız varsayılanı ölçer hâle gelir')


# ===========================================================================
# 9) RADYAL GEOMETRİ YAYIN BLOĞU (parti 40) — ÜRETİCİ YAZILDI, BAĞLANMADI
#
# Kalemin ikinci yarısı: gerdirmenin yayın yoluna açılabilmesi için eksik
# olan şey TOLERANS DEĞİL VERİDİR. Tüketici (motor_viz3d.js:cfdWallRadii)
# hücre kenarlarını "radyal dağılım düzgündür" beyanından TÜRETİYOR;
# aynı formülün duvar yarıçapı sapması ÖLÇÜLDÜ (gerçek kontur 60×12):
# düzgünde 1,24e-03, tanh gerdirmesiyle 4,34e-02 — yani eşiği gevşetmek
# yanlış çizmeyi ONAYLAMAK olurdu. radial_geometry_block o veriyi üretir.
# Uca BAĞLANMASI ayrı kalemdir; yayın yolu kilidi (bölüm 6) yerinde.
# ===========================================================================

def _yayin_bloklu_izgaralar():
    """(ad, grid) — dört rejim: düzgün / gerdirme / yaka / yaka+gerdirme."""
    pts = _gercek_kontur_mm()
    return [
        ('düzgün', build_nozzle_grid(pts, 60, 12)),
        ('gerdirme', build_nozzle_grid(pts, 60, 12, first_cell_m=YAKA_D1,
                                       stretch='tanh')),
        ('yaka', build_nozzle_grid(pts, 60, 12, wall_collar=WallCollar())),
        ('yaka+gerdirme', build_nozzle_grid(pts, 60, 12,
                                            first_cell_m=YAKA_D1,
                                            stretch='tanh',
                                            wall_collar=WallCollar())),
    ]


def test_yayin_blogu_hucre_KOLONU_dugumlerini_verir_ucun_kendi_tanimiyla():
    """r_nodes_m = kolonu sınırlayan iki düğüm sütununun ortalaması.

    Bu, ucun ``grid`` bloğunun ZATEN beyan ettiği "CELL COLUMN wall radius
    (the mean of the two node radii bounding that column)" tanımının
    kendisidir — ikinci bir tanım yazılmadığının ölçüsü.
    """
    for ad, g in _yayin_bloklu_izgaralar():
        b = radial_geometry_block(g)
        R = np.asarray(b['r_nodes_m'], dtype=float)
        beklenen = 0.5 * (g.R[:-1, :] + g.R[1:, :])
        assert np.array_equal(R, beklenen), ad
        assert b['shape'] == [g.ni, g.nj + 1], ad
        assert b['nj'] == g.nj
        # İki geometrik gerçek satır satır korunur
        assert np.all(R[:, 0] == 0.0), f'{ad}: eksen düğümü TAM 0 değil'
        assert np.array_equal(R[:, -1],
                              0.5 * (g.R[:-1, -1] + g.R[1:, -1])), ad
        assert np.all(np.diff(R, axis=-1) > 0.0), f'{ad}: monoton değil'


def test_yayin_blogu_ucun_inceltme_dilimini_AYNEN_izler():
    """Satırlar alan bloğunun eksenel dilimiyle aynı sırada ve sayıda."""
    g = build_nozzle_grid(_gercek_kontur_mm(), 60, 12)
    idx = np.array([0, 7, 23, 59])
    b = radial_geometry_block(g, axial_indices=idx)
    tam = np.asarray(radial_geometry_block(g)['r_nodes_m'], dtype=float)
    assert b['shape'] == [4, 13]
    assert np.array_equal(np.asarray(b['r_nodes_m'], dtype=float), tam[idx])
    # Dilim sınırları kapılı: alan bloğuyla uyuşmayan indis SESSİZ geçmez
    with pytest.raises(ValueError, match='axial_indices'):
        radial_geometry_block(g, axial_indices=[0, 60])
    with pytest.raises(ValueError, match='axial_indices'):
        radial_geometry_block(g, axial_indices=[])


def test_yayin_blogu_DUZGUNLUK_hukmu_ADI_degil_GEOMETRIYI_olcer():
    """radial_distribution ADIDIR, radial_uniform ÖLÇÜMDÜR — ayrışırlar.

    Kritik vaka: düzgün dağılımın ÜSTÜNE kurulan yaka. Ad 'uniform'
    kalır ama düğümler artık eşit aralıklı DEĞİLDİR; adı okuyan tüketici
    yanlış çizerdi.
    """
    beklenen = {'düzgün': True, 'gerdirme': False,
                'yaka': False, 'yaka+gerdirme': False}
    olculen = {}
    for ad, g in _yayin_bloklu_izgaralar():
        b = radial_geometry_block(g)
        olculen[ad] = b['radial_uniform']
        assert b['radial_distribution'] == g.radial_distribution
        if ad == 'yaka':
            # AYRIŞMANIN KENDİSİ: ad düzgün, geometri düzgün DEĞİL
            assert b['radial_distribution'] == 'uniform'
            assert b['radial_uniform'] is False
            assert b['radial_spacing_rel_dev_max'] > 0.1
        if ad == 'düzgün':
            # Gürültü tabanı: eşiğin altı sadece float artığı olmalı
            assert b['radial_spacing_rel_dev_max'] < 1e-12
    assert olculen == beklenen


def test_yayin_blogu_EKSENEL_DUZLEMSELLIGI_olcup_beyan_eder():
    """Yaka düğüm sütununu düzlem olmaktan çıkarır — sayı gizlenmez.

    Panelin karo modeli iki DÜZ z kenarı olan yamuktur; yaka açıldığında
    o model yaklaşıklaşır ve bu bekçi yaklaşıklığın ÖLÇÜSÜNÜ kilitler.
    """
    for ad, g in _yayin_bloklu_izgaralar():
        b = radial_geometry_block(g)
        if 'yaka' in ad:
            assert b['axial_node_planar'] is False, ad
            assert b['axial_node_z_spread_m'] > 0.0
            # Sapma eksenel hücreyle KIYASLANABİLİR mertebede: "ihmal
            # edilebilir" diye geçiştirilemeyeceğinin ölçüsü
            assert b['axial_node_z_spread_cell_frac'] > 0.10, ad
        else:
            assert b['axial_node_planar'] is True, ad
            assert b['axial_node_z_spread_m'] == 0.0, ad
            assert b['axial_node_z_spread_cell_frac'] == 0.0, ad


def test_yayin_blogu_izgaranin_KENDI_beyanlarini_aynen_tasir():
    """radial_stretch / wall_collar KOPYALANMAZ, yeniden yazılmaz."""
    for ad, g in _yayin_bloklu_izgaralar():
        b = radial_geometry_block(g)
        assert b['radial_stretch'] is g.radial_stretch, ad
        assert b['wall_collar'] is g.wall_collar, ad
    import json
    for ad, g in _yayin_bloklu_izgaralar():
        json.dumps(radial_geometry_block(g))      # JSON'a hazır (numpy yok)


def test_yayin_blogu_TURETMENIN_yanildigini_olcer_kilidin_gerekcesi():
    """Bloğun VAROLUŞ GEREKÇESİ ölçülür: türetme gerdirmede yanılıyor.

    motor_viz3d.js:cfdWallRadii duvar yarıçapını hücre merkezlerinden
    ``r_c[nj-1]·nj/(nj-0,5)`` ile türetir. O formül burada yeniden
    kurulur ve yayımlanacak GERÇEK değerle karşılaştırılır: düzgün
    ızgarada sapma küçüktür (ve JS onu zaten beyan ediyor), gerdirilmişte
    iki mertebe büyür. Toleransı gevşetmek çare DEĞİLDİR — bu bekçi o
    kısayolun kapısını tutar.
    """
    def js_turetme(g):
        n = g.nj
        return g.r_centers[:, -1] * n / (n - 0.5)

    olcum = {}
    for ad, g in _yayin_bloklu_izgaralar():
        gercek = np.asarray(radial_geometry_block(g)['r_nodes_m'],
                            dtype=float)[:, -1]
        olcum[ad] = float(np.max(np.abs(js_turetme(g) / gercek - 1.0)))
    # Düzgün: ağırlık merkezi ↔ orta nokta payı (JS'in beyan ettiği bant)
    assert 5e-4 < olcum['düzgün'] < 5e-3, olcum
    # Gerdirilmiş: bir mertebe daha büyük — çizim gözle yanlış olurdu
    assert olcum['gerdirme'] > 20.0 * olcum['düzgün'], olcum
    assert olcum['gerdirme'] > 0.02, olcum


def test_yayin_blogu_esigi_PANELIN_esigiyle_AYNI_deger():
    """RADIAL_UNIFORM_REL_TOL ↔ motor_viz3d.js:CFD_RADIAL_UNIFORM_REL_TOL.

    İki taraf AYNI ızgara hakkında zıt hüküm veremez. JS sabitinin
    KENDİSİ okunur (kural Python'da yeniden kurulmaz); bağ koparsa bu
    bekçi kırmızıya düşer.
    """
    js = (pathlib.Path(__file__).resolve().parents[2]
          / 'hrma' / 'static' / 'js' / 'motor_viz3d.js').read_text()
    satir = [s for s in js.splitlines()
             if 'CFD_RADIAL_UNIFORM_REL_TOL =' in s]
    assert len(satir) == 1
    assert float(satir[0].split('=')[1].strip().rstrip(';')) == \
        RADIAL_UNIFORM_REL_TOL
    # Eşik blokta da yayımlanır: tüketici hükmü hangi payla verildiğini
    # okumadan kabul etmek zorunda kalmasın
    g = build_nozzle_grid(_gercek_kontur_mm(), 60, 12)
    assert radial_geometry_block(g)['radial_uniform_rel_tol'] == \
        RADIAL_UNIFORM_REL_TOL


def test_yayin_blogunun_BEDELI_olculur_ve_bantli():
    """Yükün ne kadar büyüdüğü ÖLÇÜLÜR (gizli maliyet yok).

    Ucun inceltme kuralıyla (CFD_FIELD_MAX_CELLS // nj) aynı dilim
    kurulur; blok mevcut beş alan dizisinin yanında tartılır.
    """
    import json
    from hrma.app import CFD_FIELD_MAX_CELLS, _cfd_decimate_indices

    oranlar = {}
    for seviye, (ni, nj) in (('coarse', (60, 12)), ('standard', (120, 24))):
        g = build_nozzle_grid(_gercek_kontur_mm(), ni, nj)
        idx = _cfd_decimate_indices(ni, max(2, CFD_FIELD_MAX_CELLS // nj))
        blok = radial_geometry_block(g, axial_indices=idx)
        b_yeni = len(json.dumps(blok['r_nodes_m']).encode())
        mevcut = {k: g.r_centers[idx].tolist() for k in
                  ('z_m', 'r_m', 'mach', 'pressure_Pa', 'temperature_K')}
        oranlar[seviye] = b_yeni / len(json.dumps(mevcut).encode())
        assert b_yeni < 64 * 1024, (seviye, b_yeni)
    # ÖLÇÜLDÜ: coarse %20,3 — standard %20,1 (nj+1 sütun ↔ 5×nj sütun)
    for seviye, oran in oranlar.items():
        assert 0.15 < oran < 0.30, (seviye, oran)


# ===========================================================================
# V1b MUTASYON KAYITLARI (uygulandı → kırmızı ÖLÇÜLDÜ → TERS-DEĞİŞTİRMEYLE
# geri alındı; md5'ler birebir döndü — checkout KULLANILMADI)
#
# Sağlam sürümler: hrma/cfd/grid_axisym.py = 22fae1bad1adc281e69efd43831bb67c
#                  hrma/cfd/steady.py      = 4617384f3b6e96658a1261bc569d0aaa
# (Kırmızı sayıları şu seçimle ölçüldü: bu iki dosya, -k "yaka or harman or
#  DINAMIK or duvar_normali or eksenel".)
#
#  M1 "duvar normali SAF RADYAL olsun" (grid_axisym: n_seg = (0, −dz)/|dz|;
#     mutant md5 46655790de32c62d7bdedbe86704868d)
#     → 13 KIRMIZI: yakanın ÖZÜNÜ silen mutasyon. Çarpıklık düşmüyor,
#       ulaşılan normal kalınlık hedefe oturmuyor, harman/derinlik
#       tabloları kayıyor, uç kolon kayması yok oluyor, normal yönü
#       bekçisi, kesişme kapısı ateşlemiyor, sürücü beyanı ve y⁺≈1
#       ölçümü düşüyor.
#  M2 "harman ağırlığı eksenel ötelemeye uygulanmasın" (grid_axisym:
#     Z = z + d·n_z; mutant md5 ca4996dc6599594d4749a6f02789b8ec)
#     → 15 KIRMIZI: eksen istasyonu kayıyor (r = 0 kolonu z'de kayar),
#       monotonluk/hacim, kapanış özdeşlikleri, uç kolon ölçümü, κ adımı,
#       harman ve derinlik ölçüleri, kesişme kapısı, beyan birleşimi.
#       Harmanın İKİ bileşene birden uygulanması gerektiğini ölçer.
#  M3 "harman profili DOĞRUSAL olsun" (grid_axisym: collar_weights → t;
#     mutant md5 5d1a713a359bc2e5c0e436e859320047)
#     → 6 KIRMIZI: κ adımı tablosu (0,3965 → 0,2500), harman payı
#       sıralaması, dar-harman tepeleri, GG çarpıklığı doyma tablosu,
#       derinlik profili, uç kolon hacim ölçümü. NOT: doğrusal harman
#       SEVİYE ölçütünde daha iyidir (bkz. COLLAR_BLEND_PROFILE tablosu) —
#       bekçiler bunu kalite hükmü olarak değil ÖLÇÜLEN SAYI olarak tutar.
#  M4 "harman varsayılanı nj ile ölçeklenmesin" (grid_axisym: blend = 4
#     sabiti; mutant md5 7bc6fda0e256af2e079d5580b2401775)
#     → 3 KIRMIZI: GG çarpıklığı doyma bekçisi, derinlik profili ve uç
#       kolon hacim ölçümü. Varsayılanın nj//2 OLMASININ ölçüsü budur:
#       sabit 4 katman ince ızgarada doymuyor.
#  M5 "kesişme kapısını öldür" (grid_axisym: if False and …;
#     mutant md5 67f0dd6e5dd253daba59939aea1a13b8)
#     → 1 KIRMIZI: test_yaka_KESISME_kapisi_ates_eder_ve_kapatilabilir.
#       Diğer yaka bekçileri YEŞİL kalır ve bu bilinçlidir: kapı yalnız
#       katlanma öncesi bir tavandır, ızgaranın kendisini değiştirmez.
#
# steady.py mutasyonları (M6, M7) test_viskoz_entegrasyon.py'de kayıtlıdır.
#
# NOT (parti 40): yukarıdaki "sağlam sürüm" md5'i parti 39 A4'ün bıraktığı
# hâlin künyesidir; parti 40 grid_axisym.py'ye yayın bloğunu ekledi, künye
# aşağıdaki kayıtta güncel değeriyle durur.
# ===========================================================================


# ===========================================================================
# PARTİ 40 MUTASYON KAYITLARI — parametre taşıma + yayın bloğu
#
# Sağlam sürüm: hrma/cfd/grid_axisym.py = 6e4414863beddeb13eedd31c16f6ed47
# Koşum kümesi: bu dosya + tests/cfd/test_grid.py (73 test).
# HEPSİ AYNA KOPYADA koşuldu (ürün dosyası mutasyona uğratılmadı — A3
# aynı dosyayı eş zamanlı okuyordu) ve TERS-DEĞİŞTİRMEYLE geri alındı;
# md5'ler birebir döndü, checkout KULLANILMADI.
#
# ÖN-ÖLÇÜM (mutasyonlardan önce, parti 39 tabanında): üç anahtar-kelimenin
# HERHANGİ BİRİ build_nozzle_grid'in çağrısından düşürüldüğünde süit
# (62 test) YEŞİL kalıyordu — taşıma yazılmış ama BEKÇİSİZDİ. Bölüm 8 o
# deliği kapatır ve aşağıdaki kırmızılar kapanışın ölçüsüdür.
#
#  M1 "first_cell_m düşürüldü" (build_nozzle_grid → first_cell_m=None;
#     mutant md5 e5d01097ccb54d65d2b9830118c0b670)  → 12 KIRMIZI
#  M2 "wall_collar düşürüldü" (→ wall_collar=None;
#     mutant md5 0ff6d3c9dff9e89cb35fb2172de41473)  → 12 KIRMIZI
#     M1/M2'nin 12'şer kırmızısı ÇADIR SÖKMENİN ölçülen kazancıdır:
#     _yaka_grid artık ürünün giriş noktasından geçtiği için mevcut
#     yaka/gerdirme bekçileri taşıma kusurunu KENDİLERİ yakalıyor.
#  M3 "stretch düşürüldü" (→ stretch='tanh' sabiti;
#     mutant md5 fbfdef2377f32bd7e80509ff80a7852d)  → 1 KIRMIZI
#     (yalnız 'geometric' ailesini ölçen bekçi; tek aile denenseydi
#      mutasyon hayatta kalırdı — bekçi iki aileyi de koşar.)
#  M4 "yayın bloğu hücre KOLONU yerine düğüm SÜTUNU verir"
#     (R_col = grid.R[:-1, :]; mutant md5 4331ab36fa6b716ba5d9a0039ef58f89)
#     → 2 KIRMIZI: kolon tanımı bekçisi + türetme ölçümü.
#  M5 "radial_uniform hükmü sabitlendi (hep True)"
#     (mutant md5 c8cc609b82c39abe2d3d51bda660001a) → 1 KIRMIZI
#     Ad ↔ ölçüm ayrışması bekçisi: yaka + düzgün dağılım vakası.
#  M6 "eksenel düzlemsellik EKSEN sütunundan ölçülür (hep 0)"
#     (mutant md5 7c6124fe5e995133fe4f4f25f889214e) → 1 KIRMIZI
#  M7 "eşik gevşetildi, JS sabitinden koparıldı" (1e-8 → 1e-2;
#     mutant md5 ab7b1718554d66672aa8364da2fb7fdb) → 1 KIRMIZI
#     Yalnız JS bağı bekçisi kırmızı verir ve bu DOĞRUDUR: 1e-2 ile de
#     gerdirilmiş ızgara (sapma 0,999) düzgün SAYILMAZ; kusur hükmün
#     kendisinde değil, iki tarafın AYNI ızgara hakkında farklı payla
#     hüküm verebilir hâle gelmesindedir.
# ===========================================================================
