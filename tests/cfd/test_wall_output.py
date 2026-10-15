# tests/cfd — viskoz duvar çıktısının ÜRÜN köprüleri (basamak 12 + §8.1/§8.2)
"""``hrma.cfd.wall_output``: termal FEA profili ve sürtünme itki kaybı.

VAKA (bu dosyanın ve komşularının PAYLAŞTIĞI koşumlar)
------------------------------------------------------
conftest lülesi 64×16, laminer doğrulama akışkanı μ = 0,15 Pa·s (üs 0),
izotermal duvar T_w = 0,6·T₀, satır-örtük yol, başlangıç izantropik tahmin
(Euler ön koşusu YOK — kök başlangıçtan bağımsız, ölçüldü: Euler ön
koşusuyla ṁ 4,542455 ↔ ön koşusuz 4,542456, bağıl 2,6e-07).

Bu, V1-V3 KAPI vakasının (192×48) UCUZ İKİZİDİR; KAPI'nın kendi sayıları
aşağıda BEYAN edilir ve bantların ızgarayla nasıl kaydığı görülür.

ÖLÇÜLDÜ (M4 Max, numba, 2026-08-19):

    büyüklük                     64×16          192×48 (KAPI)
    ------------------------     -----------    --------------
    iterasyon / kalıntı          1926 / 1,6e-11 3171 / 2,1e-10
    ṁ [kg/s]                     4,542456       4,470615
    y⁺ maks                      4,3543         2,6301
    F_sürtünme [N]               2600,473       2655,534
    F_sürtünme (salt kayma) [N]  2593,090       2652,685
    normal gerilme payı          %0,2839        %0,1073
    kayıp kesri (F/F_momentum)   %35,979        %37,063
    entegral BL kesri            %45,959        %46,865
    CFD / entegral BL            0,78285        0,79084
    T_aw: kurtarma ↔ adyabatik   maks %0,953    maks %1,016
    h_g: kurtarma ↔ adyabatik    maks %2,468    maks %2,801
    enerji bütçesi kapanışı      6,67e-06       1,96e-09
    kütle bütçesi kapanışı       6,94e-06       2,16e-09

REJİM UYARISI — SUTTON BANDI BU VAKADA GEÇERSİZDİR (ölçüldü, gizlenmiyor)
------------------------------------------------------------------------
Doğrulama akışkanının viskozitesi μ = 0,15 Pa·s'tir; boğaz Reynolds sayısı
ÖLÇÜLDÜ: Re_D = 4ṁ/(π·D·μ) = **771**. Uçuş sınıfı bir roket lülesinde
Re_D ~ 10⁶-10⁷'dir. Laminer sürtünme kaybı ~Re^(−1/2) gittiğinden bu
vakanın kesri (%36-37) Sutton & Biblarz'ın %0,5-2 bandının ÇOK ÜSTÜNDEDİR
ve bu bir KUSUR DEĞİL, rejim farkıdır. Bandın kendisi TÜRBÜLANSLI sınır
tabakalı lüleler içindir; türbülanslı yol bu partide hâlâ açıktır (V3
defteri: SA açık lüle koşumu ıraksıyor, sebep ayrıştırıldı). Bu yüzden
basamak 12'nin ANLAMLI çaprazı Sutton bandı DEĞİL, AYNI vakada koşulan
entegral sınır tabakası marşıdır (hrma.flow.boundary_layer, laminer kip) —
iki BAĞIMSIZ yöntem aynı kuvvete bakar.

İKİ YÖNTEM NEDEN TAM ÖRTÜŞMEZ (ölçülen gerekçe, tahmin değil)
--------------------------------------------------------------
CFD/BL = 0,783 (64×16) ↔ 0,791 (192×48): entegral marş kuvveti ~%27 FAZLA
buluyor. Sebep ölçüldü: bu vakada sınır tabakası kanalı DOLDURUYOR —
CFD alanından çıkarılan δ₉₉/R çıkışta **0,78**, boğazda 0,031. Entegral
marş İNCE TABAKA varsayımına dayanır (δ ≪ R) ve bu vakada varsayım
kırılmıştır; aynı ölçümün ikinci tanığı momentum kalınlığıdır
(θ_CFD/θ_BL = 2,05 çıkışta). Yani ayrışma sayısal bir kusur değil, MODEL
kapsamı farkıdır ve bandı bu genişlikte kilitliyoruz.

MUTASYON KANITI (elle uygulandı, kırmızı ÖLÇÜLDÜ, TERS DEĞİŞTİRMEYLE geri
alındı — checkout ile değil; md5'ler ``hrma/cfd/wall_output.py`` dosyasına
ait, sağlam sürüm e21c00556d5485819ccce73515e6d37d):
  M1 "sürtünme işareti ters": ``F_traction = -float(ham)`` →
     ``float(ham)`` (mutant 73f5c78a7055a58df91df1db5da997c3)
     → 3 KIRMIZI (16 yeşil): test_surtunme_isaret_sozlesmesi_ve_ham_olcum,
       test_surtunme_IKI_TANIMI_yan_yana_olculur,
       test_BASAMAK12_cfd_entegral_bl_ve_Sutton_YAN_YANA.
  M2 "kurtarma rejimi sabitlenmiş (hep laminer)": ``_is_turbulent`` gövdesi
     → ``return False`` (mutant 35a39c295cf0570f3b23f66462459cd8)
     → 1 KIRMIZI: test_kurtarma_faktoru_TEK_kaynaktan_ve_kosumun_rejiminden.
     Bu mutasyon LAMİNER vakada SAYISAL OLARAK GÖRÜNMEZDİR (üs zaten
     laminer seçilir); onu yakalayan tek şey testin doktorlanmış türbülans
     beyanıyla yaptığı çapraz ölçümdür.
  M3 "h_g paydası T_aw (T_w çıkarılmamış)": ``q_w / delta_T`` →
     ``q_w / T_aw`` (mutant 1f5c72e299d668d9f8a30074c76e3da1)
     → 1 KIRMIZI: test_h_g_TANIMININ_kendisiyle_tutarli.
  M4 "salt-kayma biçimi tam çekişin KOPYASI": ``F_tan = ∮τ_w·n̂_r dA`` →
     ``F_tan = -float(ham)`` (mutant a29f52e990dc99f1a2361823905afdef)
     → 1 KIRMIZI: test_surtunme_IKI_TANIMI_yan_yana_olculur (normal
       gerilme payı sıfıra düşüyor; bant alt ucu bunu yakalıyor).
  M8 "duvar basıncı kenar kaynağı sessizce eksene düşüyor":
     ``if edge_source == EDGE_SOURCE_WALL_PRESSURE:`` → ``if False:``
     (mutant bf256a8108357a338f1c121ab8a8cc9a)
     → 1 KIRMIZI: test_kenar_kaynaklari_ayni_cevaba_yakinsar (iki kaynağın
       farkı SIFIRA düşüyor; bant alt ucu 0'ı kabul etmiyor).
  Beş mutasyonun her birinden sonra dosya md5
  e21c00556d5485819ccce73515e6d37d değerine bit-özdeş geri kondu.
"""

import numpy as np
import pytest

from hrma.cfd import wall_output as wo
from hrma.cfd.steady import ViscousOptions, solve_steady_axisym
from hrma.constants import NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT
from hrma.flow.boundary_layer import (
    TRANSITION_LAMINAR_ONLY, recovery_factor, solve_boundary_layer,
)

from .conftest import (
    LULE_GAMMA, LULE_P0, LULE_PB_SOK, LULE_R, LULE_T0, lule_duvar_yaricapi,
    lule_gridi,
)
from .test_viskoz_aki import transport as visk_transport

# --- vaka sabitleri: TEK tanım yeri (komşu dosyalar buradan ithal eder) ---
VLULE_NI = 64
VLULE_NJ = 16
VLULE_MU = 0.15                 #: Pa·s — laminer doğrulama akışkanı (üs 0)
VLULE_TW_ORANI = 0.6            #: T_w = 0,6·T₀ (izotermal duvar)

#: Ölçülen kök (64×16): sürücü değişirse bu satır kırılır — regresyon çıpası.
#:
#: YENİDEN ÖLÇÜLDÜ 2026-08-31 (ÖH defter OH-Z5-14): 4,542456 → 4,5422959.
#: SEBEP ÖLÇÜLDÜ, tahmin değil: örtük yolun öz-tutarlılık kapısı hükmü
#: geri çektiğinden koşu artık hüküm anında DURMUYOR, max_iters
#: tavanında bitiyor; alan minmod limit döngüsünün tavandaki fazıdır ve
#: kök bağıl 3,52e-05 kaydı. Çıpanın TOLERANSI GEVŞETİLMEDİ (rel=1e-6):
#: faz duyarlılığı ölçüldü (faz_duyarliligi.json — tavan 19999/20000/
#: 20001) ve debi bağıl 5,2e-11 oynuyor, yani 1e-6 bandı hâlâ dört
#: mertebe paylı. Kapı ÖNCESİ kök 4,542456 kayda geçer.
VLULE_MDOT = 4.5422959
VLULE_Y_PLUS_MAX = 4.3543

#: Koşum artık TAVANDA biter (kapı hükmü geri çekiyor) — çıpanın parçası.
VLULE_TAVAN_ITER = 20000
#: ŞEMANIN (canlı minmod) kendi kalıntısı, tavan durumu. ÖLÇÜLDÜ
#: 4,86809e-04 = tolun (1e-8) 48.681 katı. Çıpa YAYIMLANAN sayıya değil
#: BUNA konur: ÖLÇÜLEN faz duyarlılığı şemada 1,19e-09, yayımlanan
#: kalıntıda ise %3,42 — yayımlanan sayı çıpalanamaz.
#: ÖH D37 A3a cfd-kok-a (F-05 TRRS duvar akısı; Berke Sunum 3a onayı 24 Eyl):
#: yeniden ölçüldü 4,874264e-04 (eski 4,86809e-04, +%0,13); bant aynı.
VLULE_TAVAN_SEMA_KALINTI = 4.874264e-04

# --- basamak 12 bantları: ÖLÇÜLDÜ, sonra kilitlendi ----------------------
#: Sürtünme kuvveti (64×16). Bant ölçümün ~1e-4'ü: aynı kurulum aynı kökü
#: verir (iki koşumda bit-aynı ölçüldü); pay yalnız platform gürültüsü için.
FRIKSIYON_N = 2600.473
FRIKSIYON_REL = 2e-4

#: Salt kayma biçimi ile tam çekiş biçiminin farkı (normal viskoz gerilme
#: payı). ÖLÇÜLDÜ: 64×16'da %0,2839, 192×48'de %0,1073 — ızgara inceldikçe
#: KÜÇÜLÜYOR (fiziğin beklediği yön). Bant: pozitif ve %1'in altı.
NORMAL_PAY_BANDI = (0.0005, 0.01)

#: CFD ↔ entegral BL oranı. ÖLÇÜLDÜ 0,78285 (64×16) / 0,79084 (192×48).
#: Bant ölçümün etrafında %10 pay: iki BAĞIMSIZ modelin aynı kuvvete
#: bakması sınanır, birbirinin kopyası olmadıkları için daraltılmaz.
CFD_BL_ORAN_BANDI = (0.70, 0.90)

#: Kayıp kesri (64×16) — Sutton bandının DIŞINDA olduğu BEYANLA kilitli.
KAYIP_KESRI = 0.359792
KAYIP_KESRI_REL = 1e-3

# --- basamak 12'nin T_aw yarısı: iki yolun ÖLÇÜLEN farkı -----------------
#: Kurtarma faktörü yolu ↔ adyabatik eş-koşu (64×16). Bant ölçümün ~1,5
#: katı; İKİSİ AYNI ŞEY DEĞİLDİR (adyabatik koşu ayrı bir akış alanıdır —
#: ölçülen debi kayması %8,24), bu yüzden bant "yakınsama" değil "tanım
#: farkının büyüklüğü" ölçer.
T_AW_IKI_YOL_MAKS = 0.015
H_G_IKI_YOL_MAKS = 0.040
ADI_DEBI_KAYMASI = 0.0824      #: ölçüldü — iki koşum aynı akış DEĞİL

#: Kenar kaynağı (eksen kolonu ↔ duvar basıncından izantropik), 64×16.
KENAR_T_AW_MAKS = 0.010
KENAR_H_G_MAKS = 0.030

#: Ölçülen boğaz Reynolds sayısı (rejim beyanı; hüküm değil).
RE_D_BOGAZ = 770.8


# ===========================================================================
# Paylaşılan koşumlar (pahalı — session kapsamında BİR kez)
# ===========================================================================

def vlule_tasinim():
    """Vakanın taşınımı: TEK tanım (kopya kurulum yazılmaz)."""
    return visk_transport(exponent=0.0, mu_ref=VLULE_MU, gamma=LULE_GAMMA,
                          cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))


def vlule_kosum(*, wall_thermal='isothermal', Pb=None, ni=VLULE_NI,
                nj=VLULE_NJ):
    """Vakayı ÜRÜN sürücüsünden koşar: (grid, sonuç, taşınım)."""
    grid = lule_gridi(ni, nj)
    tr = vlule_tasinim()
    opt = ViscousOptions(
        transport=tr, wall_thermal=wall_thermal,
        T_wall=(None if wall_thermal == 'adiabatic'
                else VLULE_TW_ORANI * LULE_T0),
        T_wall_source=(None if wall_thermal == 'adiabatic'
                       else 'verification_case: T_w = 0,6·T₀'))
    res = solve_steady_axisym(
        grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R, Pb=Pb, viscous=opt,
        time_integrator='line_implicit_j', tol_res=1e-8, settle_tol=1e-9,
        freeze_settle_tol=1e-4, max_iters=20000)
    return grid, res, tr


@pytest.fixture(scope='session')
def viskoz_izo():
    """Tam-akan izotermal viskoz lüle: (grid, sonuç, taşınım). ~19 s."""
    return vlule_kosum()


@pytest.fixture(scope='session')
def viskoz_adi():
    """Adyabatik İKİZ (aynı ızgara, aynı çalışma noktası). ~29 s."""
    return vlule_kosum(wall_thermal='adiabatic')


@pytest.fixture(scope='session')
def viskoz_ayrilmali():
    """Aşırı-genişlemiş viskoz koşu — τ_w İŞARET DEĞİŞTİRİR. ~39 s.

    Arka basınç conftest'in şoklu vakasınınkidir (LULE_PB_SOK = 2,75 MPa);
    laminer duvarla birlikte ıraksak bölgede gerçek ayrılma doğar.
    ÖLÇÜLDÜ: 4342 iterasyonda yakınsıyor (kalıntı 6,6e-11), τ_w 23
    istasyonda negatif, ilk negatif istasyon i = 41.
    """
    return vlule_kosum(Pb=LULE_PB_SOK)


def entegral_bl_kuvveti(grid, res, tr):
    """AYNI vakanın entegral sınır tabakası marşı (bağımsız ikinci ölçüm).

    Kenar durumu CFD'nin EKSEN kolonundan verilir; marş LAMİNER kipte
    koşulur (vakanın kendi rejimi — türbülanslı kapanışla karşılaştırmak
    elmayla armut olurdu).
    """
    rw = 0.5 * (grid.R[:-1, -1] + grid.R[1:, -1])
    f = res['fields']
    return solve_boundary_layer(
        grid.z_centers[:, 0], rw, f['mach'][:, 0], f['pressure_Pa'][:, 0],
        f['temperature_K'][:, 0], gamma=LULE_GAMMA,
        gas_constant_J_kgK=LULE_R, prandtl=tr.prandtl,
        viscosity_fn=tr.viscosity,
        wall_temperature_K=res['viscous']['wall_temperature_K'],
        specific_heat_J_kgK=tr.cp, transition=TRANSITION_LAMINAR_ONLY)


def sentetik_motor(grid):
    """Köprünün istediği EN AZ motor sözlüğü — kontur ızgarayla AYNI.

    Uç (app.test_client) BU DOSYANIN İŞİ DEĞİL: sınanan şey
    ``hrma.fea.bridge``ın SÖZLEŞMESİDİR, o yüzden köprüye doğrudan
    beslenir. Kontur ızgaranın kendi düğümlerinden kurulur; böylece
    köprünün eksen uyuşması denetimi (THERMAL_PROFILE_DOMAIN_TOL) GERÇEK
    bir sınav olur, kurgu bir eksende değil.
    """
    z = grid.Z[:, 0]
    r = lule_duvar_yaricapi(z)
    return {
        'nozzle_contour': {
            'points': [[float(a), float(b)] for a, b in zip(z, r)],
            '_basis': 'tests/cfd/conftest.lule_duvar_yaricapi (analitik)'},
        'structural_analysis': {
            'chamber_analysis': {'wall_thickness_used_mm': 3.0,
                                 'design_mode': 'verification_case'},
            'design_parameters': {'material': 'steel_4130'},
            'material_properties': {'yield_strength': 460e6}},
        'chamber_pressure': 40.0,        # bar
        'burn_time': 5.0,                # s
    }


# ===========================================================================
# Sözleşme kapıları — sessiz varsayılana düşme yok
# ===========================================================================

def test_viskoz_olmayan_sonuc_reddedilir():
    """Euler koşusundan h_g/τ_w türetilmez (uydurma yok)."""
    with pytest.raises(ValueError, match=r"'viscous' anahtarı yok"):
        wo.thermal_axial_profile({'inputs': {}})
    with pytest.raises(ValueError, match=r'viskoz KAPALI koşuldu'):
        wo.thermal_axial_profile({'viscous': None})
    with pytest.raises(ValueError, match=r'sözlük olmalı'):
        wo.viscous_wall_block([1, 2, 3])


def test_adyabatik_kosu_h_g_VEREMEZ(viskoz_adi):
    """q_w ≡ 0 ve T_w = T_aw: h_g = 0/0. Kırpma yok, ADLI red var."""
    _, res, _ = viskoz_adi
    # Önce ölçüm: adyabatik duvarda q_w GERÇEKTEN bit-sıfır.
    q = np.asarray(res['viscous']['wall_heat_flux_W_m2'])
    assert np.all(q == 0.0), 'adyabatik duvarda q_w ayrık olarak tam sıfırdır'
    with pytest.raises(ValueError, match=r'ADYABATİK duvarlıdır'):
        wo.thermal_axial_profile(res)


def test_t_aw_kaynagi_BEYANLI_bir_secimdir(viskoz_izo, viskoz_adi):
    """Tanımsız temel, eşlikçisiz adyabatik yol ve yanlış ikiz REDDEDİLİR."""
    _, izo, _ = viskoz_izo
    _, adi, _ = viskoz_adi
    with pytest.raises(ValueError, match=r't_aw_basis .* tanımsız'):
        wo.thermal_axial_profile(izo, t_aw_basis='ne_olduğu_belirsiz')
    with pytest.raises(ValueError, match=r'adiabatic_result verilmedi'):
        wo.thermal_axial_profile(izo,
                                 t_aw_basis=wo.T_AW_BASIS_ADIABATIC)
    # İzotermal bir koşumun duvar sıcaklığı kurtarma sıcaklığı DEĞİLDİR.
    with pytest.raises(ValueError, match=r'ADYABATİK duvarlı bir koşu olmalı'):
        wo.thermal_axial_profile(izo, t_aw_basis=wo.T_AW_BASIS_ADIABATIC,
                                 adiabatic_result=izo)
    # Başka ızgaranın T_aw'si taşınmaz.
    _, kaba, _ = vlule_kosum(wall_thermal='adiabatic', ni=8, nj=4)
    with pytest.raises(ValueError, match=r'AYNI ızgarada değil|aynı '
                                         r'istasyonlarda|uzunluğu'):
        wo.thermal_axial_profile(izo, t_aw_basis=wo.T_AW_BASIS_ADIABATIC,
                                 adiabatic_result=kaba)


def test_kenar_kaynagi_adlidir(viskoz_izo):
    _, izo, _ = viskoz_izo
    with pytest.raises(ValueError, match=r'edge_source .* tanımsız'):
        wo.thermal_axial_profile(izo, edge_source='gözle_bakarak')


def test_T_aw_kucukse_h_g_UYDURULMAZ(viskoz_izo):
    """T_w ≥ T_aw olan istasyonda h_g işareti tanımsız → adlı red."""
    _, izo, _ = viskoz_izo
    bozuk = dict(izo)
    v = dict(izo['viscous'])
    tw = np.asarray(v['wall_temperature_K'], dtype=float).copy()
    tw[7] = 9999.0                       # kurtarma sıcaklığının üstünde
    v['wall_temperature_K'] = tw
    bozuk['viscous'] = v
    with pytest.raises(ValueError, match=r'T_aw ≤ T_w olan istasyon var'):
        wo.thermal_axial_profile(bozuk)


# ===========================================================================
# §8.1 — Termal FEA profili
# ===========================================================================

def test_profil_KOPRUNUN_sozlesmesini_saglar(viskoz_izo):
    """FEA köprüsünün üç zorunlu alanı + kesin artan eksen + pozitiflik."""
    _, izo, _ = viskoz_izo
    p = wo.thermal_axial_profile(izo)
    x = np.asarray(p['x_mm'], dtype=float)
    h = np.asarray(p['h_g'], dtype=float)
    t = np.asarray(p['T_recovery'], dtype=float)
    assert x.shape == h.shape == t.shape == (VLULE_NI,)
    assert np.all(np.isfinite(x)) and np.all(np.isfinite(h))
    assert np.all(np.isfinite(t))
    assert np.all(np.diff(x) > 0.0), 'x_mm kesin artan olmalı (köprü şartı)'
    assert np.all(h > 0.0) and np.all(t > 0.0)
    assert p['source'] == wo.THERMAL_PROFILE_SOURCE == 'cfd_viscous'
    assert p['t_aw_basis'] == wo.T_AW_BASIS_RECOVERY
    assert p['edge_source'] == wo.EDGE_SOURCE_AXIS
    assert p['recovery_regime'] == 'laminar'


def test_h_g_TANIMININ_kendisiyle_tutarli(viskoz_izo):
    """h_g·(T_aw − T_w) ≡ q_w: yayımlanan üçlü ÖLÇÜLEN akıyı geri verir.

    Bu bir totoloji DEĞİL, sözleşme bekçisidir: yayımlanan q_w, T_wall ve
    T_recovery dizileri h_g ile AYNI koşumdan gelmeli. Biri başka bir
    yerden (ör. Bartz) sızarsa özdeşlik kırılır.
    """
    _, izo, _ = viskoz_izo
    p = wo.thermal_axial_profile(izo)
    geri = (np.asarray(p['h_g']) * (np.asarray(p['T_recovery'])
                                    - np.asarray(p['T_wall_K'])))
    q = np.asarray(p['q_w_W_m2'])
    assert np.max(np.abs(geri - q) / np.abs(q)) < 1e-14
    # q_w çözücünün yayımladığı dizinin TA KENDİSİ (kopya değil, aynı sayı)
    assert np.array_equal(q, np.asarray(izo['viscous']
                                        ['wall_heat_flux_W_m2']))


def test_kurtarma_faktoru_TEK_kaynaktan_ve_kosumun_rejiminden(viskoz_izo):
    """r = Pr^(1/2) laminer / Pr^(1/3) türbülanslı — çağıran seçmez."""
    _, izo, _ = viskoz_izo
    p = wo.thermal_axial_profile(izo)
    pr = p['prandtl']
    assert p['recovery_factor'] == pytest.approx(
        recovery_factor(pr, turbulent=False), rel=0, abs=0)
    assert p['recovery_factor'] != recovery_factor(pr, turbulent=True)
    # Koşum türbülanslı BEYAN ederse üs değişmeli (rejim beyandan okunur).
    turb = dict(izo)
    v = dict(izo['viscous'])
    v['turbulence'] = {'model': 'sa_neg'}
    turb['viscous'] = v
    p2 = wo.thermal_axial_profile(turb)
    assert p2['recovery_regime'] == 'turbulent'
    assert p2['recovery_factor'] == pytest.approx(
        recovery_factor(pr, turbulent=True), rel=0, abs=0)


def test_kenar_kaynaklari_ayni_cevaba_yakinsar(viskoz_izo):
    """İki kenar tanımı arasındaki fark ÖLÇÜLÜR ve bantla kilitlenir.

    Ölçüldü (64×16): T_aw farkı maks %0,665 · h_g farkı maks %1,782.
    İkisi de bağımsız birer yaklaşımdır (eksen kolonu ÖLÇÜM, duvar
    basıncından izantropik kurulum P₀ KAYBININ ihmali) — birbirinin
    kopyası olmadıkları için bant daraltılmaz.
    """
    _, izo, _ = viskoz_izo
    a = wo.thermal_axial_profile(izo, edge_source=wo.EDGE_SOURCE_AXIS)
    b = wo.thermal_axial_profile(izo,
                                 edge_source=wo.EDGE_SOURCE_WALL_PRESSURE)
    ta, tb = np.asarray(a['T_recovery']), np.asarray(b['T_recovery'])
    ha, hb = np.asarray(a['h_g']), np.asarray(b['h_g'])
    t_fark = float(np.max(np.abs(ta - tb) / ta))
    h_fark = float(np.max(np.abs(ha - hb) / ha))
    assert 0.0 < t_fark < KENAR_T_AW_MAKS, (
        f'kenar kaynakları arası T_aw farkı {t_fark:.4%} bandın dışında')
    assert 0.0 < h_fark < KENAR_H_G_MAKS, (
        f'kenar kaynakları arası h_g farkı {h_fark:.4%} bandın dışında')
    assert b['edge_source'] == wo.EDGE_SOURCE_WALL_PRESSURE


def test_T_aw_IKI_YOLUN_farki_olculur_ve_beyanlidir(viskoz_izo, viskoz_adi):
    """Kurtarma faktörü ↔ adyabatik eş-koşu: fark ölçüldü, kilitlendi.

    ÖLÇÜLDÜ (64×16): T_aw maks %0,953 · ort %0,510; h_g maks %2,468 ·
    ort %1,330. (192×48 KAPI: %1,016 / %2,801 — ızgarayla kayıyor.)

    AYNI ŞEY DEĞİLLER ve bu testin ikinci ölçümü bunu KANITLAR: adyabatik
    ikiz AYRI bir çözümdür, debisi %8,24 kayar. Varsayılanın kurtarma
    faktörü yolu olmasının gerekçesi budur (tek koşu, aynı akış alanı).
    """
    _, izo, _ = viskoz_izo
    _, adi, _ = viskoz_adi
    p_rec = wo.thermal_axial_profile(izo)
    p_adi = wo.thermal_axial_profile(
        izo, t_aw_basis=wo.T_AW_BASIS_ADIABATIC, adiabatic_result=adi)
    assert p_adi['t_aw_basis'] == wo.T_AW_BASIS_ADIABATIC
    assert p_adi['edge_source'] is None, (
        'adyabatik yolda kenar durumu KULLANILMAZ; kullanıldığı '
        'izlenimi verilmemeli')
    t1 = np.asarray(p_rec['T_recovery'])
    t2 = np.asarray(p_adi['T_recovery'])
    h1 = np.asarray(p_rec['h_g'])
    h2 = np.asarray(p_adi['h_g'])
    t_maks = float(np.max(np.abs(t1 - t2) / t2))
    h_maks = float(np.max(np.abs(h1 - h2) / h2))
    assert 0.0 < t_maks < T_AW_IKI_YOL_MAKS, (
        f'iki yolun T_aw farkı {t_maks:.4%} ölçülen banttan çıktı')
    assert 0.0 < h_maks < H_G_IKI_YOL_MAKS, (
        f'iki yolun h_g farkı {h_maks:.4%} ölçülen banttan çıktı')
    # İKİ KOŞUM AYNI AKIŞ DEĞİL — beyanın dayanağı ölçülür.
    kayma = abs(adi['mass_flow_in_kg_s'] - izo['mass_flow_in_kg_s']) \
        / izo['mass_flow_in_kg_s']
    assert kayma == pytest.approx(ADI_DEBI_KAYMASI, rel=2e-2), (
        'adyabatik ikizin debi kayması beyandan saptı — "iki yol aynı '
        'akışı ölçüyor" iddiası bu sayıyla çürütülmüştü')
    assert 'AYNI AKIŞ ALANI DEĞİLDİR' in p_adi['t_aw_basis_detail']


def test_kunye_kosumu_ADIYLA_tasir(viskoz_izo):
    """Künyesiz profil yayımlanmaz: ızgara, y⁺, yakınsama görünür.

    HÜKÜM SÖZLEŞMESİ (ÖH defter OH-Z5-14; çevrildi 2026-08-31)
    ----------------------------------------------------------
    Test eskiden ``k['converged'] is True`` ve ``final_residual_scaled
    < 1e-8`` diyordu. İkisi de ürünün ARTIK VERMEDİĞİ iddialardır:
    öz-tutarlılık kapısı hükmü geri çekiyor ve koşu tavanda bitiyor
    (yayımlanan kalıntı 1,3203e-08 = tolun 1,32 katı).

    Künyenin İŞİ hüküm vermek DEĞİL, çözücüyü OLDUĞU GİBİ tekrarlamaktır.
    Bu yüzden çevrilen sınav bir KİMLİK sınavıdır: künyedeki her alan
    çözücünün yayımladığı alanın ta kendisi mi? Böylece "künye iyimser
    bir sayı gösteriyor" kusuru bir daha sessizce giremez.

    BEYAN — künyede makine-okur ``convergence_status`` YOKTUR (ölçüldü:
    once.json/izo/kunye/kunyede_convergence_status_var_mi = false).
    Hükümsüzlüğün cinsi bugün yalnız ``convergence_basis`` METNİNDE
    taşınıyor; alan olarak da taşınması ``hrma/cfd/wall_output.py``
    işidir ve bu kulvarın sahası DIŞINDADIR (devir kalemi).
    """
    _, izo, _ = viskoz_izo
    p = wo.thermal_axial_profile(izo)
    k = p['solution_basis']
    # --- KİMLİK: künye çözücüyü tekrarlar, hüküm ÜRETMEZ --------------
    assert k['converged'] is izo['converged']
    assert k['converged'] is False, k['convergence_basis']
    assert k['convergence_basis'] == izo['convergence_basis']
    assert k['iterations'] == izo['iterations'] == VLULE_TAVAN_ITER
    assert k['final_residual_scaled'] == pytest.approx(
        float(izo['residual_history'][-1]), rel=0, abs=0), (
        'künye çözücünün yayımladığı kalıntıdan AYRIŞTI — künye kendi '
        'sayısını üretiyor olabilir')
    # --- Hükümsüzlüğün SEBEBİ künyenin taşıdığı metinde ADIYLA var ----
    assert 'HÜKÜM VERİLMEDİ' in k['convergence_basis']
    assert 'scheme_residual_norm' in k['convergence_basis']
    assert 'residual_operator=frozen_slopes' in k['convergence_basis']
    # --- Künyenin geri kalanı DEĞİŞMEDİ (kapı ALANI değiştirmez) ------
    assert k['grid_ni'] == VLULE_NI and k['grid_nj'] == VLULE_NJ
    assert k['thermal_mode'] == 'isothermal'
    assert k['T_wall_source'] and 'verification_case' in k['T_wall_source']
    assert k['y_plus_achieved_max'] == pytest.approx(VLULE_Y_PLUS_MAX,
                                                     rel=1e-3)
    assert k['turbulence'] is None
    assert set(p['not_modelled']) == set(wo.WALL_OUTPUT_NOT_MODELLED)


def test_FEA_koprusu_COZUNMEMIS_duvari_REDDEDER(viskoz_izo):
    """ÖH D16 / P6B2-01 — çözünmemiş duvardan gelen h_g köprüye giremez.

    Bu bekçi eskiden ``test_FEA_koprusu_profili_KABUL_EDER`` adıyla tam
    KUSURU KİLİTLİYORDU: fikstürün y⁺'sı 4,35'tir (duvar-çözümlü kenarı
    y⁺ ≤ 1), yani duvar ÇÖZÜNMEMİŞTİR, ve test bu profilin köprüce KABUL
    edilmesini sözleşme yapıyordu. Üründe ölçülen y⁺ 268,86392 (coarse) /
    190,28189 (standard) ile h_g deponun kendi Bartz zincirinin %1-2'sine
    düşüyordu (oran ortalaması 0,0101073 / 0,0201732) ve hata yönü
    EMNİYETSİZDİ — o hâlde "kabul edilir" bir sözleşme olamaz. Test
    çevrildi: red artık sözleşmedir.

    SAYININ KAYNAĞI (ÖH D18, P6B2-01 ŞART): iki y⁺ değeri ürün ucundan
    (/api/cfd/nozzle, viskoz izotermal, T_wall = 1920 K) yeniden ölçülüp
    docs/scofield/raw/OH/D18/fea-cfd/a1/olcum_y_plus.json dosyasına
    yazıldı (üreteci .../olcum_p6b2_01.py); ilk ölçüm
    docs/scofield/raw/P06/H2-hakem.md tablosundadır.
    """
    from hrma.fea.bridge import (BRIDGE_STATUS_NOT_MODELLED,
                                 extract_thermal_inputs)

    grid, izo, _ = viskoz_izo
    p = wo.thermal_axial_profile(izo)
    assert p['wall_resolution']['resolved'] is False, (
        'fikstür beklenmedik biçimde duvar-çözümlü — bu bekçinin konusu '
        'çözünmemiş duvardır')
    ins = extract_thermal_inputs(sentetik_motor(grid), axial_profile=p)
    assert ins['status'] == BRIDGE_STATUS_NOT_MODELLED, (
        'çözünmemiş duvardan gelen h_g termal FEA sınır koşulu oldu')
    assert 'ÇÖZÜNMEMİŞ' in ins['reason']


def test_FEA_koprusu_profili_KABUL_EDER(viskoz_izo):
    """Basamak 12'nin ürün ayağı: bridge sözleşmesi GERÇEKTEN sağlanıyor.

    Uçtan (app) DEĞİL, köprüye DOĞRUDAN beslenir. Köprünün eksen uyuşması
    denetimi gerçek bir sınavdır: profil ekseni duvar YÜZLERİNİN orta
    noktalarıdır, kontur ise ızgara DÜĞÜMLERİDİR — aradaki yarım hücrelik
    kırpma köprünün kendi beyanıyla karşılanmalıdır.

    ÖH D16 / P6B2-01 — bu fikstürün duvarı çözünmemiştir (y⁺ = 4,35) ve
    köprü onu artık reddeder (yukarıdaki bekçi). Buradaki konu duvar
    çözünürlüğü DEĞİL eksen/sözleşme uyuşmasıdır, bu yüzden çözünürlük
    hükmü duvar-çözümlü koşumun değeriyle DEĞİŞTİRİLEREK aşağı yol
    açılır. Değiştirilen tek şey hükümdür; h_g, x_mm ve T_recovery
    dizileri koşumun ÖLÇÜMÜ olarak kalır (test fikstürü, ürün sayısı
    değil).

    TARİHÇE — "TABANDA DA KIRMIZI" KAYDI ÇÜRÜTÜLDÜ (ÖH D17 / D15-CFD-02).
    D16 fea-cfd a1 bu bekçiyi taban 6fde52b'de kırmızı ölçmüştü: köprünün
    P8B2-04 boğaz-hizası kapısı fikstürün h(z) tepesini z = 2,344 mm'de,
    konturun boğazını z = 121,875 mm'de görüp reddediyordu (sapma
    119,531 mm > tolerans 6,000 mm). Teşhis doğruydu ama kusur KAPIDAYDI:
    CFD ile ÇÖZÜLMÜŞ bir profilde h tepesi boğazda DEĞİL girişte olur
    (sınır tabakası orada sıfır kalınlıktan başlar), yani kapı GEÇERLİ
    girdiyi reddediyordu. D15 fix-3 (b2ba463) kapıya "boğaz imzası"
    ayrımını getirdi: tepe UÇ istasyondaysa profil boğaz iddiası
    YAYIMLAMIYOR demektir ve nirengi ÇALIŞTIRILAMAZ diye beyan edilir
    (kapı gevşetilmedi — tepe İÇ istasyondaysa hiza yine sınanır).
    ÖLÇÜLDÜ (ÖH D17, taban 2426b4d): bu test artık YEŞİL (1 passed,
    131,39 s). Ayrımın durduğunu ucuz yoldan kilitleyen bekçi:
    tests/test_d17_fea_cfd_a1.py::TestD15CFD02_TabandaKirmiziCurutuldu.
    """
    from hrma.fea.bridge import (BRIDGE_STATUS_OK, extract_thermal_inputs,
                                 run_thermal_from_motor)

    grid, izo, _ = viskoz_izo
    p = dict(wo.thermal_axial_profile(izo))
    p['wall_resolution'] = wo.wall_resolution_declaration(
        {'y_plus_achieved_max': wo.Y_PLUS_WALL_RESOLVED})
    motor = sentetik_motor(grid)
    ins = extract_thermal_inputs(motor, axial_profile=p)
    assert ins['status'] == BRIDGE_STATUS_OK, (
        f"köprü profili reddetti: {ins.get('reason')}")
    beyan = ins['_basis']['h_profili']
    assert beyan['nokta_sayisi'] == VLULE_NI
    assert 'SABİT' in beyan['uc_ekstrapolasyon'], (
        'yarım hücrelik kırpma köprünün BEYANINDA görünmeli')
    # Uçtan uca: çözücü gerçekten koşuyor (küçük mesh).
    run = run_thermal_from_motor(motor, axial_profile=p,
                                 ambient_temperature_K=293.15,
                                 n_axial=8, n_radial=3)
    assert run['status'] == BRIDGE_STATUS_OK, run.get('reason')
    assert np.isfinite(run['peak_wall_T_K']) and run['peak_wall_T_K'] > 293.15


# ===========================================================================
# §8.2 / basamak 12 — sürtünme itki kaybı
# ===========================================================================

def test_surtunme_isaret_sozlesmesi_ve_ham_olcum(viskoz_izo):
    """Yayımlanan kayıp POZİTİF; çözücünün ham ölçümü onun TERSİ."""
    grid, izo, _ = viskoz_izo
    fr = wo.friction_thrust_loss(izo, grid)
    ham = izo['viscous']['axial_friction_force_on_fluid_N']
    assert ham < 0.0, 'bağlı akışta akışkana etkiyen eksenel kuvvet negatif'
    assert fr['friction_force_N'] > 0.0
    assert fr['friction_force_N'] == pytest.approx(-ham, rel=0, abs=0)
    assert fr['axial_friction_force_on_fluid_N'] == ham
    assert fr['friction_source'] == wo.FRICTION_SOURCE == 'cfd_viscous_measured'


def test_surtunme_IKI_TANIMI_yan_yana_olculur(viskoz_izo):
    """∮(τ·n̂)_z dA ile ∮τ_w(t̂·ê_z) dA farkı ÖLÇÜLÜR, ihmal VARSAYILMAZ."""
    grid, izo, _ = viskoz_izo
    fr = wo.friction_thrust_loss(izo, grid)
    assert fr['friction_force_N'] == pytest.approx(FRIKSIYON_N,
                                                   rel=FRIKSIYON_REL)
    pay = fr['normal_stress_share']
    assert NORMAL_PAY_BANDI[0] < pay < NORMAL_PAY_BANDI[1], (
        f'normal gerilme payı {pay:.4%} ölçülen bandın dışında')
    # Salt kayma biçimi tam çekişten KÜÇÜK olmalı (fark pozitif pay).
    assert 0.0 < fr['friction_force_tangential_N'] < fr['friction_force_N']
    # Islak alan ızgaranın 2π'li yüzey vektörlerinden: analitik kontrol
    # olarak dönel yüzeyin kaba tahmininin mertebesinde olmalı.
    assert fr['wetted_area_m2'] > 0.0


def test_surtunme_izgarasi_DENETLENIR(viskoz_izo):
    """Başka ızgaranın normalleriyle kuvvet integrali alınmaz.

    İKİ AYRI KAPI var ve HANGİSİNİN ne yakaladığı ÖLÇÜLDÜ (ikisi de
    gerekli — biri diğerinin yerine geçmiyor):

      (a) DUVAR yüz alanı kapısı — kontur farklıysa ateşler.
      (b) ÇIKIŞ yüzü sayısı kapısı — kontur AYNI ama nj farklıysa ateşler.
          Bu vaka (a)'dan GEÇER, çünkü duvar yüz vektörü yalnız duvar
          düğümlerine bağlıdır ve nj'den bağımsızdır (ölçüldü). Yani
          sürtünme integrali o ızgarada DOĞRU olurdu; yanlış olan çıkış
          momentum akısıdır ve onu (b) yakalar.
    """
    from hrma.cfd.grid_axisym import build_grid_from_wall

    grid, izo, _ = viskoz_izo
    z = grid.Z[:, 0]

    # (a) BAŞKA KONTUR (aynı ni, nj): duvar alanları uyuşmaz.
    sisik = build_grid_from_wall(z, 1.1 * lule_duvar_yaricapi(z), VLULE_NJ)
    with pytest.raises(ValueError, match=r'wall_area_m2 dizisiyle\s+uyuşmuyor'):
        wo.friction_thrust_loss(izo, sisik)

    # (b) AYNI KONTUR, farklı nj: duvar yüzleri BİT-AYNI kalır (ölçülür),
    #     kapıyı çıkış yüzü sayısı açar.
    baska = lule_gridi(VLULE_NI, VLULE_NJ + 4)
    assert np.allclose(np.hypot(baska.face_j[:, -1, 0],
                                baska.face_j[:, -1, 1]),
                       izo['viscous']['wall_area_m2'], rtol=0, atol=0), (
        'duvar yüz vektörünün nj\'den bağımsızlığı VARSAYILMADI, ölçüldü — '
        'bu iddia kırılırsa aşağıdaki kapı beklentisi de yanlıştır')
    with pytest.raises(ValueError, match=r'Izgara çıkış yüzü sayısı'):
        wo.friction_thrust_loss(izo, baska)

    # (c) Farklı ni: istasyon sayısı bile tutmuyor.
    kisa = lule_gridi(VLULE_NI // 2, VLULE_NJ)
    with pytest.raises(ValueError, match=r'Izgara duvar yüzü sayısı'):
        wo.friction_thrust_loss(izo, kisa)


def test_BASAMAK12_cfd_entegral_bl_ve_Sutton_YAN_YANA(viskoz_izo):
    """Basamak 12: üç sayı aynı ekranda, anlam sınırları BEYANLI.

    (1) CFD ölçümü ↔ (2) entegral BL marşı (AYNI vaka, laminer kip) ↔
    (3) Sutton bandı. (1)-(2) çaprazı ANLAMLIDIR ve bantla kilitlidir;
    (3) bu vakada GEÇERSİZDİR (Re_D = 771) ve testin kendisi bunu
    BEYANLA sabitler — bant içine düşmüş gibi gösterilmesi bir daha
    mümkün olmasın diye.
    """
    grid, izo, tr = viskoz_izo
    fr = wo.friction_thrust_loss(izo, grid)
    bl = entegral_bl_kuvveti(grid, izo, tr)

    oran = fr['friction_force_N'] / bl['friction_drag_N']
    assert CFD_BL_ORAN_BANDI[0] < oran < CFD_BL_ORAN_BANDI[1], (
        f'CFD/entegral-BL oranı {oran:.4f} bandın dışında — iki bağımsız '
        f'yöntem aynı kuvvete bakmıyor '
        f'(CFD {fr["friction_force_N"]:.2f} N, '
        f'BL {bl["friction_drag_N"]:.2f} N)')
    assert bl['march']['status'] == 'completed'

    assert fr['friction_loss_fraction'] == pytest.approx(KAYIP_KESRI,
                                                         rel=KAYIP_KESRI_REL)
    # SUTTON: bandın DIŞINDA ve bu BEYANLA kilitli (dürüstlük bekçisi).
    assert fr['within_sutton_band'] is False, (
        'laminer doğrulama vakası Sutton bandına düşmemeli — düştüyse ya '
        'vaka ya bant değişmiştir, ikisi de beyanla yapılır')
    assert fr['sutton_band'] == (0.005, 0.02)
    for parca in ('TÜRBÜLANSLI', 'ANLAM SINIRI', 'hüküm değil BEYANDIR'):
        assert parca in fr['band_comparison_basis'], f'beyan eksik: {parca}'
    # Rejim gerçekten uçuş bandının dışında (beyanın dayanağı ölçülür).
    rw = 0.5 * (grid.R[:-1, -1] + grid.R[1:, -1])
    re_d = (4.0 * izo['mass_flow_in_kg_s']
            / (np.pi * 2.0 * rw[izo['throat']['i']] * VLULE_MU))
    assert re_d == pytest.approx(RE_D_BOGAZ, rel=1e-3)
    assert re_d < 1.0e4, 'vaka laminer doğrulama rejiminde olmalı'


def test_yari_1B_politikasi_DEGISMEDI(viskoz_izo):
    """Bu ölçüm hiçbir varsayılanı değiştirmez; defter sabiti İTHAL edilir."""
    grid, izo, _ = viskoz_izo
    fr = wo.friction_thrust_loss(izo, grid)
    assert fr['legacy_constant'] == NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT
    assert fr['legacy_constant'] == 0.015
    for parca in ('HİÇBİR VARSAYILANI DEĞİŞTİRMEZ', 'integral_bl_measured',
                  'legacy_constant', 'ÜÇÜNCÜ'):
        assert parca in fr['policy_basis'], f'politika beyanı eksik: {parca}'
    # Kaynak adı yarı-1B zincirin adlarıyla ÇAKIŞMAZ (dördüncü ad).
    assert fr['friction_source'] not in ('user', 'integral_bl_measured',
                                         'legacy_constant')


def test_referans_yuzey_yari_1B_ile_AYNI_secildi(viskoz_izo):
    """Kesir paydası çıkış momentum akısıdır (yan yana konabilsin diye)."""
    grid, izo, _ = viskoz_izo
    fr = wo.friction_thrust_loss(izo, grid)
    S = grid.face_i[-1]
    f = izo['fields']
    mdot_face = f['rho_kg_m3'][-1] * (f['u_z_m_s'][-1] * S[:, 0]
                                      + f['u_r_m_s'][-1] * S[:, 1])
    assert fr['exit_mass_flow_kg_s'] == pytest.approx(
        float(np.sum(mdot_face)), rel=1e-12)
    assert fr['exit_mass_flow_kg_s'] == pytest.approx(
        izo['mass_flow_out_kg_s'], rel=1e-9)
    assert fr['friction_loss_fraction'] == pytest.approx(
        fr['friction_force_N'] / fr['momentum_thrust_N'], rel=1e-15)
    assert 'momentum_thrust' in fr['reference_surface_basis']


def test_kok_regresyon_cipasi(viskoz_izo):
    """Vakanın kökü dondurulmuş: sürücü kayarsa bantlar anlamsızlaşır.

    HÜKÜM SÖZLEŞMESİ (ÖH defter OH-Z5-14; çevrildi 2026-08-31)
    ----------------------------------------------------------
    ``converged is True`` çıpası DÜŞTÜ: öz-tutarlılık kapısı hükmü geri
    çekiyor (şemanın kendi kalıntısı 4,868e-04 = tolun 48.681 katı) ve
    koşu tavanda bitiyor. Çıpa kaldırılmadı, YERİ DEĞİŞTİ: artık hükmün
    KENDİSİ değil, hükümsüzlüğün CİNSİ ve ölçülen kök dondurulur.

    Bu vaka PLATO DEĞİLDİR (ayrılmalı ikizinden farklı olarak): şema
    kalıntısı tavanda hâlâ oynuyor (ölçülen göreli yayılım 5,44e-02,
    eşik 1e-02), o yüzden "hedef ulaşılamaz" DENMEZ — fail-closed,
    "bilinmiyor" plato sayılmaz.
    """
    _, izo, _ = viskoz_izo
    # --- HÜKÜM: kazanılmadı, sebebi ADIYLA yayımlandı -----------------
    assert izo['converged'] is False, izo['convergence_basis']
    assert izo['convergence_status'] == 'not_converged', (
        izo['convergence_basis'])
    assert izo['scheme_residual_blocks_verdict'] is True
    assert izo['scheme_residual_exceeds_tol'] is True
    assert izo['residual_operator'] == 'frozen_slopes'
    assert izo['picard_selfconsistency_rejections'] > 0
    assert izo['iterations'] == VLULE_TAVAN_ITER
    assert izo['convergence_plateau']['detected'] is False
    assert 'yayılım' in izo['convergence_plateau']['reason']
    # --- ÇIPALAR: şema kalıntısı + kök (faz duyarlılığı ölçüldü) ------
    assert izo['scheme_residual_norm'] == pytest.approx(
        VLULE_TAVAN_SEMA_KALINTI, rel=1e-3), (
        'şemanın kendi kalıntısı ölçülen bandın dışına çıktı — limit '
        'döngüsünün tabanı kaymış, bu dosyanın bantları yeniden '
        'ölçülmelidir')
    assert izo['mass_flow_in_kg_s'] == pytest.approx(VLULE_MDOT, rel=1e-6)
    assert izo['viscous']['wall_y_plus_max'] == pytest.approx(
        VLULE_Y_PLUS_MAX, rel=1e-4)
