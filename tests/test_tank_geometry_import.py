"""3.0.7 K3a — tank_geometry_import (TANK §A, §B; §E.4 girdi zinciri).

Fikstürler ``tests/fixtures/tank_geometry/`` (üretici:
``docs/scofield/raw/OH/V307/tank-geometri/fikstur_uret.py``). Bellek içi
bulutlar ``tank_geometri_ornekleyici`` ile analitik yüzeyden, tohumlu.
"""

import math
import os
import struct
import sys

import numpy as np
import pytest

from hrma.analysis import slosh_tablo
from hrma.analysis import tank_mass_properties as mp
from hrma.importers import tank_geometry_import as tg

sys.path.insert(0, os.path.dirname(__file__))
import tank_geometri_ornekleyici as orn  # noqa: E402

FIK = os.path.join(os.path.dirname(__file__), 'fixtures', 'tank_geometry')
R = 0.5
UST = (0.0, 0.0, 1.0)
#: Sözleşme okuyucusunun hata türleri (SloshTabloHatasi). v307-2 (K6):
#: adlı sabit olarak sözleşmeden içe aktarılır; liste değişirse aşağıdaki
#: bekçi kırmızı olur.
OKUMA_KODLARI = slosh_tablo.OKUYUCU_HATA_KODLARI


def fik(ad):
    return os.path.join(FIK, ad)


def _profil_uzakligi(nokta, profil):
    a, b = profil[:-1], profil[1:]
    v = b - a
    L2 = (v ** 2).sum(1)
    t = np.clip(((nokta - a) * v).sum(1) / np.where(L2 > 0, L2, 1.0), 0, 1)
    return float(np.min(np.hypot(*(nokta - (a + t[:, None] * v)).T)))


def _sozlesme_uyumu(out):
    """Her sonuç: sebep sözleşmede, okuma kodu sözleşmenin türlerinden,
    metin anahtarı biçimli ve İngilizce yedeği tanımlı."""
    if out['durum'] != slosh_tablo.DURUM_RET:
        # v307-2 (K6): kabulde sebep, beyanların BEYAN sınıfı sözleşme
        # kodlarıdır (önceden her zaman boştu); durum kodlardan türer.
        assert out['sebep'] == [b['sebep'] for b in out['beyanlar']]
        for kod in out['sebep']:
            assert slosh_tablo.SEBEP_KODLARI[kod][0] == slosh_tablo.SINIF_BEYAN
        assert out['durum'] == slosh_tablo.durum_birlestir(out['sebep'])
        return
    if out['sebep']:
        assert len(out['sebep']) == 1
        assert out['sebep'][0] in slosh_tablo.SEBEP_KODLARI
        assert out['okuma_hatasi'] is None
        kod = out['sebep'][0]
    else:
        kod = out['okuma_hatasi']['kod']
        assert kod in OKUMA_KODLARI
        assert kod in slosh_tablo.SloshTabloHatasi.__doc__
    assert (kod, out['ayrinti']) in tg.YEDEK_METINLER
    assert out['mesaj_anahtari'] == (
        f'tank_geometry.{kod.lower()}.{out["ayrinti"]}')
    assert out['mesaj_en'] and '{' not in out['mesaj_en']


def ret(out, *, sebep=None, okuma=None, ayrinti=None, kapi=None):
    _sozlesme_uyumu(out)
    assert out['durum'] == 'RET', out
    if sebep is not None:
        assert out['sebep'] == [sebep], out
    if okuma is not None:
        assert out['okuma_hatasi']['kod'] == okuma, out
    if ayrinti is not None:
        assert out['ayrinti'] == ayrinti, out
    if kapi is not None:
        assert out['kapi'] == kapi, out
    return out


def kabul(out):
    _sozlesme_uyumu(out)
    assert out['durum'] in ('GECERLI', 'BEYANLI'), out
    p = np.asarray(out['profil_rz_m'])
    assert p[0, 1] == 0.0 and p[0, 0] == 0.0 and p[-1, 0] == 0.0
    assert np.all(np.diff(p[:, 1]) >= 0.0)
    assert out['geometri']['V_ic_m3'] == mp.ic_hacim(p)
    return out


# ---------------------------------------------------------------------------
# §E.4 sentetik nokta bulutu: profil ⟷ analitik, simetri kapısı
# ---------------------------------------------------------------------------
SENTETIK_PROFILLER = {
    'silindir': orn.silindir_duz(R, 2.0),
    'kure': orn.kure(R),
    'kubbeli': orn.kubbeli_silindir(R, 1.0),
}


@pytest.mark.parametrize('ad', sorted(SENTETIK_PROFILLER))
@pytest.mark.parametrize('sigma_oran', [0.0, 1e-4, 1e-3])
def test_sentetik_bulut_profili_analitikle_uyusur(ad, sigma_oran):
    """Düğümlerin analitik profile uzaklığı ≤ 2σ_n + eksen kestirim payı.

    Pay = ``TANK_DUGUM_KURULUM_PAYI_ORANI`` · R (10⁻⁵ R): gürültüsüz bulutta
    uydurulan eksenin kalan eğimi ~10⁻⁶ rad (modül künyesinde ölçüm).
    """
    prof = SENTETIK_PROFILLER[ad]
    P = orn.ornekle(prof, 60000, tohum=7, gurultu=sigma_oran * R)
    out = kabul(tg.nokta_bulutu_isle(P, ust_yon=UST))
    p = np.asarray(out['profil_rz_m'])
    pay = 2.0 * sigma_oran * R + tg.TANK_DUGUM_KURULUM_PAYI_ORANI * R
    # Keskin köşe (düz baş ⟷ çeper): köşeye denk gelen kutunun düğümü
    # köşeyi keser. Ölçüldü (iki tohum, 2·10⁴–2·10⁵ nokta): ≤ 1,24·10⁻³ R;
    # köşeden 0,02 R uzakta ≤ 4,1·10⁻⁶ R. Köşe payı ölçülenin 2 katı.
    # Açık iş (RAPOR): köşe farkındalıklı düğüm yerleşimi.
    koseler = [q for q in prof[1:-1]
               if ad == 'silindir']
    for q in p:
        kose_yakin = any(math.hypot(q[0] - k[0], q[1] - k[1]) <= 0.02 * R
                         for k in koseler)
        sinir = pay + (2.5e-3 * R if kose_yakin else 0.0)
        sapma = _profil_uzakligi(q, prof)
        assert sapma <= sinir, (q, sapma / R, sinir / R)
    V = out['geometri']['V_ic_m3']
    assert V == pytest.approx(mp.ic_hacim(prof), rel=1e-3)
    m = out['olcumler']
    assert m['eps_max'] <= m['esik_eps_max']
    assert m['eps_rms'] <= m['esik_eps_rms']


def test_eliptik_kesit_002_ret_0005_kabul():
    prof = SENTETIK_PROFILLER['kubbeli']
    r002 = ret(tg.nokta_bulutu_isle(orn.ornekle(prof, 60000, tohum=3,
                                                eps_cos2=0.02),
                                    ust_yon=UST),
               sebep='EKSENEL_SIMETRIK_DEGIL', kapi='B.3')
    prm = r002['mesaj_parametreleri']
    assert prm['eps_max'] > prm['esik_eps_max']
    kabul(tg.nokta_bulutu_isle(orn.ornekle(prof, 60000, tohum=3,
                                           eps_cos2=0.005), ust_yon=UST))


def test_gurultu_sistematik_asimetriyi_yutmaz():
    """σ̂_n hücre içi artıklardan kestirilir (tasarım düzeltmesi).

    Toplam artığın MAD'i ε cos 2θ bozulmasını gürültü sayar
    (σ̂ ≈ 1,05 ε R) ve ε = 0,02'yi kabul ettirirdi.
    """
    prof = SENTETIK_PROFILLER['kubbeli']
    out = tg.nokta_bulutu_isle(orn.ornekle(prof, 60000, tohum=3,
                                           eps_cos2=0.02), ust_yon=UST)
    ret(out, sebep='EKSENEL_SIMETRIK_DEGIL')
    assert out['mesaj_parametreleri']['esik_eps_max'] < 0.025


@pytest.mark.slow  # K6 denetimi: ≥ 2 s (V307 ORTAK_EK)
def test_eksenden_kaydirilmis_ve_donuk_silindir_kabul_ve_eksen():
    D = orn.donme(0.3, -0.2)
    P = orn.ornekle(SENTETIK_PROFILLER['kubbeli'], 60000, tohum=4, donus=D,
                    oteleme=(0.7, -0.2, 0.4))
    out = kabul(tg.nokta_bulutu_isle(P, ust_yon=D @ np.array(UST)))
    d = np.asarray(out['kunye']['eksen']['yon'])
    assert float(np.dot(d, D @ np.array(UST))) == pytest.approx(1.0,
                                                                abs=1e-9)
    alt = np.asarray(out['kunye']['eksen']['alt_kutup_m'])
    assert np.linalg.norm(alt - np.array([0.7, -0.2, 0.4])) <= 1e-4 * R


@pytest.mark.slow  # K6 denetimi: ≥ 2 s (V307 ORTAK_EK)
def test_kullanici_ekseni_ve_sigma():
    P = orn.ornekle(SENTETIK_PROFILLER['kubbeli'], 60000, tohum=5)
    out = kabul(tg.nokta_bulutu_isle(
        P, ust_yon=UST, eksen=((0.01, 0.0, 0.0), (0.01, 0.0, 1.0)),
        sigma_n_m=2e-4))
    assert out['olcumler']['eksen_baslangic'] == 'kullanici'
    assert out['olcumler']['sigma_n_kaynak'] == 'kullanici'
    assert out['olcumler']['sigma_n_m'] == 2e-4


def test_gurultu_beyani():
    P = orn.ornekle(SENTETIK_PROFILLER['kubbeli'], 60000, tohum=6,
                    gurultu=0.008 * R)
    out = kabul(tg.nokta_bulutu_isle(P, ust_yon=UST))
    assert out['durum'] == 'BEYANLI'
    b = out['beyanlar'][0]
    assert b['kod'] == 'gurultu_esikle_kiyaslanabilir'
    assert ('BEYAN', b['kod']) in tg.YEDEK_METINLER
    # v307-2 (K6): beyanın sözleşme kodu (K3a devri)
    assert b['sebep'] == 'GURULTU_ESIKLE_KIYASLANABILIR'
    assert out['sebep'] == ['GURULTU_ESIKLE_KIYASLANABILIR']


def test_okuyucu_hata_turleri_sozlesmenin_adli_sabitleri():
    """v307-2 (K6, K3a devri): içe aktarıcının ürettiği her okuyucu hata
    türü sözleşmenin ``OKUYUCU_HATA_KODLARI`` adlı sabitlerindendir. Kod
    yolu koşmasa bile ``_okuma(…, kod)`` çağrılarının hepsi AST'den
    denetlenir; YEDEK_METINLER anahtarları da aynı kümeden."""
    import ast
    assert OKUMA_KODLARI == ('BOYUT_SINIRI', 'BICIM_HATASI',
                             'DEGER_GECERSIZ', 'ALAN_EKSIK', 'TUR_HATASI')
    for kod in OKUMA_KODLARI:
        assert kod in slosh_tablo.HATA_KODLARI
    kaynak = open(tg.__file__, encoding='utf-8').read()
    kodlar = []
    for d in ast.walk(ast.parse(kaynak)):
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                and d.func.id == '_okuma'):
            arg = d.args[1] if len(d.args) > 1 else next(
                k.value for k in d.keywords if k.arg == 'kod')
            if (isinstance(arg, ast.Attribute)
                    and arg.attr == 'okuma_kodu'):
                continue   # ProfilHatasi'nden aktarım; kurucusu denetler
            assert isinstance(arg, ast.Constant), ast.dump(arg)
            kodlar.append(arg.value)
    assert len(kodlar) > 40
    assert set(kodlar) <= set(OKUMA_KODLARI), set(kodlar) - set(OKUMA_KODLARI)
    for kod, _ in tg.YEDEK_METINLER:
        assert (kod in OKUMA_KODLARI or kod in slosh_tablo.SEBEP_KODLARI
                or kod == 'BEYAN'), kod
    with pytest.raises(AssertionError):
        tg._okuma('x', 'UYDURMA_KOD')
    with pytest.raises(TypeError):
        mp.ProfilHatasi('x', ayrinti='x', okuma_kodu='UYDURMA_KOD')


@pytest.mark.slow  # K6 denetimi: ≥ 2 s (V307 ORTAK_EK)
def test_delik_eksik_bolge_dogru_pencere():
    P = orn.ornekle(SENTETIK_PROFILLER['kubbeli'], 60000, tohum=2)
    th = np.degrees(np.mod(np.arctan2(P[:, 1], P[:, 0]), 2 * np.pi))
    pencere = (th > 60) & (th < 120) & (P[:, 2] > 0.8) & (P[:, 2] < 1.2)
    out = ret(tg.nokta_bulutu_isle(P[~pencere], ust_yon=UST),
              sebep='EKSIK_BOLGE', ayrinti='kapsama', kapi='B.2')
    prm = out['mesaj_parametreleri']
    assert prm['dilimler'] == [[60.0, 90.0], [90.0, 120.0]]
    # Hücreler eşit sayılı z kutularıdır (~0,05 m): bildirilen pencere
    # silinen pencerenin (0,8–1,2 m) bir kutu payı içinde.
    assert 0.7 <= prm['z_min_m'] <= 0.9 and 1.1 <= prm['z_max_m'] <= 1.3
    # Referans +x'in eksene dik izdüşümü; eksen eğimi ~10⁻⁶ rad.
    assert prm['azimut_referansi'] == pytest.approx([1.0, 0.0, 0.0],
                                                    abs=1e-5)


def test_acik_uclu_tank_ret():
    prof = np.array([[0, 0], [R, 0], [R, 2.0], [R * 0.999999, 2.0]])
    assert ret(tg.nokta_bulutu_isle(orn.ornekle(prof, 60000, tohum=3),
                                    ust_yon=UST),
               sebep='YUZEY_KAPALI_DEGIL', ayrinti='bas_kapanmiyor')['durum'] == 'RET'


def test_toroid_iki_yuzey():
    t = np.linspace(0, 2 * np.pi, 721)
    tor = np.stack([1.0 + 0.3 * np.cos(t), 0.5 + 0.3 * np.sin(t)], 1)
    assert ret(tg.nokta_bulutu_isle(orn.ornekle(tor, 60000, tohum=4), ust_yon=UST),
               sebep='PROFIL_TEK_DEGERLI_DEGIL', ayrinti='iki_yuzey')['durum'] == 'RET'


def test_ice_donuk_ortak_perde_tek_degerli_degil():
    s = np.linspace(0, 1, 200)
    ust = np.stack([R * (1 - s), 2.0 - 0.3 * (1 - (1 - s) ** 2)], 1)
    perde = np.vstack([[[0, 0], [R, 0], [R, 2.0]], ust])
    perde[-1, 0] = 0
    out = ret(tg.nokta_bulutu_isle(orn.ornekle(perde, 60000, tohum=5),
                                   ust_yon=UST),
              sebep='PROFIL_TEK_DEGERLI_DEGIL', ayrinti='z_monoton_degil')
    assert out['mesaj_parametreleri']['z_m'] > 1.5


# ---------------------------------------------------------------------------
# Yüzlü girdi (STL / PLY / STEP)
# ---------------------------------------------------------------------------
def test_stl_ikili_kure_kabul_ve_hacim_tutarliligi():
    out = kabul(tg.tank_geometrisi_oku(fik('kure_r250mm_ikili.stl'), 'mm',
                                       ust_yon=UST))
    assert out['olcumler']['hacim_bagil_fark'] <= (
        tg.TANK_HACIM_TUTARLILIK_ESIGI)
    assert out['kunye']['ucgen_sayisi'] == 2208
    assert len(out['kunye']['sha256']) == 64


def test_stl_ascii_ve_ply_ascii_ayni_ag_ayni_sonuc():
    a = kabul(tg.tank_geometrisi_oku(fik('kure_r250mm_ascii.stl'), 'mm',
                                     ust_yon=UST))
    b = kabul(tg.tank_geometrisi_oku(fik('kure_ag_ascii_m.ply'), 'm',
                                     ust_yon=UST))
    assert a['geometri']['V_ic_m3'] == pytest.approx(
        b['geometri']['V_ic_m3'], rel=1e-7)


def test_stl_tek_ucgen_eksik_acik_kenar_3():
    out = ret(tg.tank_geometrisi_oku(fik('kure_bir_ucgen_eksik.stl'), 'mm',
                                     ust_yon=UST),
              sebep='YUZEY_KAPALI_DEGIL', ayrinti='acik_kenar', kapi='B.2')
    assert out['mesaj_parametreleri']['adet'] == 3
    assert len(out['mesaj_parametreleri']['konumlar_m']) == 3


def test_ag_ters_yonelim_ve_cok_govde():
    P, T = orn.kure_ucgen_agi(R, 12, 24)
    assert ret(tg.nokta_bulutu_isle(P, ucgenler=T[:, [0, 2, 1]], ust_yon=UST),
               sebep='YUZEY_KAPALI_DEGIL', ayrinti='ters_yonelim')['durum'] == 'RET'
    P2 = np.vstack([P, P + np.array([3.0, 0, 0])])
    T2 = np.vstack([T, T + P.shape[0]])
    assert ret(tg.nokta_bulutu_isle(P2, ucgenler=T2, ust_yon=UST),
               sebep='YUZEY_KAPALI_DEGIL', ayrinti='euler')['durum'] == 'RET'
    Tk = T.copy()
    Tk[5] = Tk[5, [0, 2, 1]]
    assert ret(tg.nokta_bulutu_isle(P, ucgenler=Tk, ust_yon=UST),
               sebep='YUZEY_KAPALI_DEGIL', ayrinti='yonelim_tutarsiz')['durum'] == 'RET'


def test_ag_inceltmede_hacim_yakinsamasi():
    """UV küre ağı inceltildikçe V_iç analitiğe ikinci mertebeden yaklaşır."""
    V_a = 4.0 / 3.0 * math.pi * R ** 3
    hatalar = []
    for n in (12, 24, 48):
        P, T = orn.kure_ucgen_agi(R, n, 2 * n)
        out = kabul(tg.nokta_bulutu_isle(P, ucgenler=T, ust_yon=UST))
        hatalar.append(abs(out['geometri']['V_ic_m3'] - V_a) / V_a)
    oran = [hatalar[i] / hatalar[i + 1] for i in range(2)]
    assert all(3.0 <= o <= 5.0 for o in oran), (hatalar, oran)
    assert hatalar[-1] <= 2e-3


@pytest.mark.slow  # K6 denetimi: ≥ 2 s (V307 ORTAK_EK)
def test_step_kubbeli_silindir():
    pytest.importorskip('build123d')
    out = kabul(tg.tank_geometrisi_oku(fik('kubbeli_silindir_mm.step'),
                                       ust_yon=UST))
    V_a = math.pi * 0.25 ** 2 * 0.5 + 4.0 / 3.0 * math.pi * 0.25 ** 3
    assert out['geometri']['V_ic_m3'] == pytest.approx(V_a, rel=1e-3)
    assert out['kunye']['birim'] == 'mm'
    ret(tg.tank_geometrisi_oku(fik('kubbeli_silindir_mm.step'), 'in',
                               ust_yon=UST),
        sebep='BIRIM_YOK', ayrinti='celiskili')


def test_step_mozaikleyici_yoksa_adli_ret(monkeypatch):
    from hrma.importers import step_import
    monkeypatch.setattr(step_import, '_load_deps',
                        lambda: (None, 'build123d/OCP is not available'))
    assert ret(tg.tank_geometrisi_oku(fik('kubbeli_silindir_mm.step'), 'mm',
                                      ust_yon=UST),
               sebep='STEP_MOZAIK_YOK', ayrinti='mozaikleyici_yok', kapi='B.1')['durum'] == 'RET'


# ---------------------------------------------------------------------------
# Nokta bulutu dosyaları ve birim
# ---------------------------------------------------------------------------
def test_ply_ikili_bulut_kabul():
    out = kabul(tg.tank_geometrisi_oku(fik('kubbeli_silindir_bulut_mm.ply'),
                                       'mm', ust_yon=UST))
    V_a = mp.ic_hacim(orn.kubbeli_silindir(0.25, 0.5))
    assert out['geometri']['V_ic_m3'] == pytest.approx(V_a, rel=2e-3)


def test_ply_ikili_eliptik_ret():
    assert ret(tg.tank_geometrisi_oku(fik('elips_002_bulut_mm.ply'), 'mm',
                                      ust_yon=UST),
               sebep='EKSENEL_SIMETRIK_DEGIL')['durum'] == 'RET'


def test_mm_csv_ile_m_xyz_ayni_sonuc():
    a = kabul(tg.tank_geometrisi_oku(fik('silindir_bulut_mm.csv'),
                                     ust_yon=UST))
    b = kabul(tg.tank_geometrisi_oku(fik('silindir_bulut_m.xyz'), 'm',
                                     ust_yon=UST))
    assert a['kunye']['birim'] == 'mm' and b['kunye']['birim'] == 'm'
    pa, pb = np.asarray(a['profil_rz_m']), np.asarray(b['profil_rz_m'])
    assert pa.shape == pb.shape
    assert np.max(np.abs(pa - pb)) <= 1e-6
    assert a['geometri']['V_ic_m3'] == pytest.approx(b['geometri']['V_ic_m3'],
                                                     rel=1e-5)


@pytest.mark.slow  # K6 denetimi: ≥ 2 s (V307 ORTAK_EK)
def test_inc_birimi(tmp_path):
    P = orn.ornekle(SENTETIK_PROFILLER['kubbeli'], 20000, tohum=8)
    yol = tmp_path / 'bulut.xyz'
    yol.write_text('\n'.join(f'{x:.9f} {y:.9f} {z:.9f}' for x, y, z in
                             P / tg.BIRIM_CARPANLARI['in']))
    a = kabul(tg.tank_geometrisi_oku(str(yol), 'in', ust_yon=UST))
    b = kabul(tg.nokta_bulutu_isle(P, ust_yon=UST))
    assert a['geometri']['V_ic_m3'] == pytest.approx(b['geometri']['V_ic_m3'],
                                                     rel=1e-6)


@pytest.mark.parametrize('ad, birim, ayrinti', [
    ('silindir_bulut_birimsiz.csv', None, 'yok'),
    ('kure_r250mm_ikili.stl', None, 'yok'),
    ('silindir_bulut_m.xyz', None, 'yok'),
    ('silindir_bulut_mm.csv', 'm', 'celiskili'),
    ('silindir_bulut_m.xyz', 'cm', 'desteklenmiyor'),
    ('silindir_bulut_m.xyz', 'MM', 'desteklenmiyor'),
])
def test_birim_zorunlu(ad, birim, ayrinti):
    assert ret(tg.tank_geometrisi_oku(fik(ad), birim, ust_yon=UST),
               sebep='BIRIM_YOK', ayrinti=ayrinti, kapi='B.1')['durum'] == 'RET'


def test_profil_csv_kabul_ve_red():
    out = kabul(tg.tank_geometrisi_oku(fik('profil_kubbeli_m.csv')))
    assert out['geometri']['V_ic_m3'] == pytest.approx(
        mp.ic_hacim(orn.kubbeli_silindir(0.25, 0.5, n=180)), rel=1e-11)
    ret(tg.tank_geometrisi_oku(fik('profil_geri_donen.csv')),
        sebep='PROFIL_TEK_DEGERLI_DEGIL', ayrinti='z_monoton_degil',
        kapi='B.4')


def test_ust_yon_zorunlu_ve_eksene_dik_ret():
    P = orn.ornekle(SENTETIK_PROFILLER['kubbeli'], 20000, tohum=1)
    assert ret(tg.nokta_bulutu_isle(P, ust_yon=None), okuma='ALAN_EKSIK',
               ayrinti='ust_yon_yok')['durum'] == 'RET'
    assert ret(tg.nokta_bulutu_isle(P, ust_yon=(1, 0, 0)), okuma='DEGER_GECERSIZ',
               ayrinti='ust_yon_eksene_dik')['durum'] == 'RET'
    for kotu in ((0, 0, 0), (0, 0), (True, 0, 1), ('a', 0, 1),
                 (0, 0, float('nan'))):
        assert ret(tg.nokta_bulutu_isle(P, ust_yon=kotu), okuma='DEGER_GECERSIZ',
                   ayrinti='ust_yon_gecersiz')['durum'] == 'RET'


@pytest.mark.slow  # K6 denetimi: ≥ 2 s (V307 ORTAK_EK)
def test_ters_ust_yon_ekseni_cevirir():
    """Üst yön ekseni seçer: ters verilince profil baş aşağı olur."""
    s = np.linspace(0, 1, 100)
    koni = np.vstack([[[0, 0], [R, 0]],
                      np.stack([R * (1 - s), 0.5 + 1.5 * s], 1)[:-1],
                      [[0, 2.0]]])
    P = orn.ornekle(koni, 60000, tohum=9)
    a = kabul(tg.nokta_bulutu_isle(P, ust_yon=UST))
    b = kabul(tg.nokta_bulutu_isle(P, ust_yon=(0, 0, -1)))
    za = mp.kesit_ozellikleri(a['profil_rz_m'], 1000.0, 0.25)['V_sivi_m3']
    zb = mp.kesit_ozellikleri(b['profil_rz_m'], 1000.0, 0.25)['V_sivi_m3']
    assert za > 5.0 * zb       # düz taban altta ⟷ sivri uç altta


def test_az_nokta():
    P = orn.ornekle(SENTETIK_PROFILLER['kubbeli'], 1000, tohum=1)
    assert ret(tg.nokta_bulutu_isle(P, ust_yon=UST), okuma='DEGER_GECERSIZ',
               ayrinti='nokta_az', kapi='B.1')['durum'] == 'RET'


# ---------------------------------------------------------------------------
# Saldırgan / bozuk girdi — adlı ret, istisna sızmaz
# ---------------------------------------------------------------------------
def test_kesik_ikili_stl():
    assert ret(tg.tank_geometrisi_oku(fik('kure_kesik.stl'), 'mm', ust_yon=UST),
               okuma='BICIM_HATASI', ayrinti='ikili_boyut_tutarsiz')['durum'] == 'RET'


def test_dev_ucgen_beyani():
    out = ret(tg.tank_geometrisi_oku(fik('dev_beyan.stl'), 'mm', ust_yon=UST),
              okuma='BICIM_HATASI', ayrinti='ikili_boyut_tutarsiz')
    assert out['mesaj_parametreleri']['beyan'] == 0xFFFFFFFF


def test_ucgen_ve_dosya_siniri(monkeypatch):
    monkeypatch.setattr(tg, 'TANK_UCGEN_SINIRI', 100)
    ret(tg.tank_geometrisi_oku(fik('kure_r250mm_ikili.stl'), 'mm',
                               ust_yon=UST),
        okuma='BOYUT_SINIRI', ayrinti='ucgen_siniri')
    monkeypatch.setattr(tg, 'TANK_DOSYA_BOYUT_SINIRI', 1000)
    out = ret(tg.tank_geometrisi_oku(fik('silindir_bulut_mm.csv'),
                                     ust_yon=UST),
              okuma='BOYUT_SINIRI', ayrinti='dosya_boyutu')
    assert out['mesaj_parametreleri']['sinir'] == 1000


def test_nan_csv():
    assert ret(tg.tank_geometrisi_oku(fik('nan_iceren.csv'), ust_yon=UST),
               okuma='DEGER_GECERSIZ', ayrinti='sonlu_olmayan')['durum'] == 'RET'


@pytest.mark.parametrize('icerik, okuma, ayrinti', [
    ('a,b,c\nm,m,m\n1,2,3\n', 'BICIM_HATASI', 'csv_baslik'),
    ('x,y,z\nm,m,m\n1,2\n', 'BICIM_HATASI', 'sutun_sayisi'),
    ('x,y,z\nm,m,m\n1,2,3\n\n4,5,6\n', 'DEGER_GECERSIZ', 'bos_satir'),
    ('x,y,z\nm,m,m\n1_000,2,3\n', 'BICIM_HATASI', 'sayi_degil'),
    ('x,y,z\nm,m,m\n0x10,2,3\n', 'BICIM_HATASI', 'sayi_degil'),
    ('x,y,z\nm,m,m\n1,inf,3\n', 'DEGER_GECERSIZ', 'sonlu_olmayan'),
    ('x,y,z\nm,mm,m\n1,2,3\n', None, None),
    ('', 'BICIM_HATASI', 'bos_dosya'),
])
def test_bozuk_csv(tmp_path, icerik, okuma, ayrinti):
    yol = tmp_path / 'b.csv'
    yol.write_text(icerik)
    out = tg.tank_geometrisi_oku(str(yol), ust_yon=UST)
    if okuma is None:
        assert ret(out, sebep='BIRIM_YOK', ayrinti='celiskili')['durum'] == 'RET'
    else:
        assert ret(out, okuma=okuma, ayrinti=ayrinti)['durum'] == 'RET'


@pytest.mark.parametrize('baslik, govde, okuma, ayrinti', [
    ('format binary_little_endian 1.0\nelement vertex 4000000000\n'
     'property float x\nproperty float y\nproperty float z\n', b'',
     'BOYUT_SINIRI', 'nokta_siniri'),
    ('format binary_little_endian 1.0\nelement vertex 100\n'
     'property float x\nproperty float y\nproperty float z\n', b'\x00' * 120,
     'BICIM_HATASI', 'ikili_boyut_tutarsiz'),
    ('format binary_big_endian 1.0\nelement vertex 1\n'
     'property float x\nproperty float y\nproperty float z\n', b'\x00' * 12,
     'BICIM_HATASI', 'ply_buyuk_endian'),
    ('format ascii 1.0\nelement vertex 1\nproperty float x\n'
     'property float y\n', b'1 2\n', 'BICIM_HATASI', 'ply_baslik'),
    ('format ascii 1.0\nelement vertex 3\nproperty float x\n'
     'property float y\nproperty float z\nelement face 1\n'
     'property list uchar int vertex_indices\n',
     b'0 0 0\n1 0 0\n0 1 0\n3 0 1 7\n', 'BICIM_HATASI',
     'yuz_indeksi_gecersiz'),
    ('format ascii 1.0\nelement vertex 3\nproperty float x\n'
     'property float y\nproperty float z\nelement face 1\n'
     'property list uchar int vertex_indices\n',
     b'0 0 0\n1 0 0\n0 1 0\n40 0 1 2\n', 'BICIM_HATASI', 'ply_yuz_kose'),
    ('format ascii 1.0\nelement vertex 2\nproperty float x\n'
     'property float y\nproperty float z\n', b'0 0 0\nnan 0 0\n',
     'DEGER_GECERSIZ', 'sonlu_olmayan'),
])
def test_bozuk_ply(tmp_path, baslik, govde, okuma, ayrinti):
    yol = tmp_path / 'b.ply'
    yol.write_bytes(b'ply\n' + baslik.encode() + b'end_header\n' + govde)
    assert ret(tg.tank_geometrisi_oku(str(yol), 'm', ust_yon=UST), okuma=okuma,
               ayrinti=ayrinti)['durum'] == 'RET'


def test_ply_ikili_kare_yuzler_yelpaze(tmp_path):
    """İkili PLY, dörtgen yüzlü küp: yelpaze üçgenlemesi kapalı ağ verir
    (yavaş yol); küp eksenel simetrik değildir → B.3 RET (B.2 geçti)."""
    v = np.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)],
                 dtype='<f4')
    yuzler = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3),
              (0, 4, 6, 2), (1, 3, 7, 5)]
    govde = v.tobytes() + b''.join(struct.pack('<B4i', 4, *f) for f in yuzler)
    yol = tmp_path / 'kup.ply'
    yol.write_bytes(b'ply\nformat binary_little_endian 1.0\nelement vertex 8\n'
                    b'property float x\nproperty float y\nproperty float z\n'
                    b'element face 6\nproperty list uchar int vertex_indices\n'
                    b'end_header\n' + govde)
    out = ret(tg.tank_geometrisi_oku(str(yol), 'm', ust_yon=UST))
    assert out['kapi'] in ('B.3', 'B.4'), out


@pytest.mark.parametrize('uzanti', ['.stl', '.ply', '.csv', '.xyz', '.step'])
def test_rastgele_bayt_istisna_sizdirmaz(tmp_path, uzanti):
    rng = np.random.default_rng(1)
    yol = tmp_path / ('rastgele' + uzanti)
    yol.write_bytes(rng.integers(0, 256, 5000, dtype=np.uint8).tobytes())
    out = ret(tg.tank_geometrisi_oku(str(yol), 'm', ust_yon=UST))
    assert out['kapi'] == 'B.1'


def test_desteklenmeyen_uzanti_ve_yok_dosya(tmp_path):
    yol = tmp_path / 'tank.obj'
    yol.write_text('v 0 0 0\n')
    assert ret(tg.tank_geometrisi_oku(str(yol), 'm', ust_yon=UST),
               okuma='BICIM_HATASI', ayrinti='bicim_desteklenmiyor')['durum'] == 'RET'
    assert ret(tg.tank_geometrisi_oku(str(tmp_path / 'yok.stl'), 'm', ust_yon=UST),
               okuma='BICIM_HATASI', ayrinti='bos_dosya')['durum'] == 'RET'
    assert ret(tg.tank_geometrisi_oku(12345, 'm', ust_yon=UST), okuma='BICIM_HATASI')['durum'] == 'RET'


def test_simetri_esigi_tek_yerde():
    assert tg.TANK_SIMETRI_ESIGI == 0.01
    assert tg.PROFIL_NOKTA_SINIRI is slosh_tablo.PROFIL_NOKTA_SINIRI
    assert tg.SEBEP_KODLARI is slosh_tablo.SEBEP_KODLARI
