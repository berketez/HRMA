"""3.0.7 K6 — çalkantı TEK GİRİŞ (``slosh_analysis.esdeger_model_tablosu``).

Kalem 1: tank tanımına göre yol seçimi (dik silindir → kapalı biçim;
profilli eksenel simetrik tank → SE; açıkça istenirse kubbeli tankta
silindir formülü h_eş ile, kubbe bölgesi RET; geometri kapısında RET →
tablo yok, içe aktarıcının adlı kodu). Her yolun tablosu sözleşme
doğrulayıcısından geçer. Ayrıca K2'nin içe aktardığı genel imzaların
geriye uyumu ve geometri beyanının satırlara yayılması.

Tasarım: CALKANTI_6DOF_TASARIM §A.1.1–A.1.3, TANK_GEOMETRI_TASARIM §D.6.
"""

import inspect
import math
import os
import sys

import numpy as np
import pytest

from hrma.analysis import slosh_analysis as sa
from hrma.analysis import slosh_fem_axisym as se
from hrma.analysis import slosh_tablo as T
from hrma.analysis import tank_mass_properties as mp
from hrma.importers import tank_geometry_import as tg

sys.path.insert(0, os.path.dirname(__file__))
import tank_geometri_ornekleyici as orn  # noqa: E402

FIK = os.path.join(os.path.dirname(__file__), 'fixtures', 'tank_geometry')
SIVI = {'ad': 'LOX', 'rho_kg_m3': 1141.0}
UST = (0.0, 0.0, 1.0)


def elips_basli_silindir(R, L, k, n=256):
    """Alt ve üst baş yarı ekseni k·R olan elips başlı silindir (k = 0,5:
    2:1 elips, k = 1: yarım küre). Silindir bölümünün iki ucu tam r = R."""
    t = np.linspace(0.0, 0.5 * math.pi, n + 1)
    alt = np.stack([R * np.sin(t), k * R * (1.0 - np.cos(t))], axis=1)
    ust = np.stack([R * np.cos(t), k * R + L + k * R * np.sin(t)], axis=1)
    p = np.concatenate([alt, ust])
    p[0, 0] = 0.0
    p[-1, 0] = 0.0
    return p


def _tablo_sozlesmeli(t):
    """Tablo doğrulanmış ve JSON/CSV gidiş-dönüşü bit aynı."""
    assert isinstance(t, T.SloshTablo)
    assert T.json_oku(T.json_yaz(t)).sozluk() == t.sozluk()
    assert T.csv_oku(T.csv_yaz(t)).sozluk() == t.sozluk()
    assert t.sozluk()['sema_surumu'] == T.SEMA_SURUMU


# ---------------------------------------------------------------------------
# Yol seçimi
# ---------------------------------------------------------------------------
class TestDikSilindir:
    @pytest.mark.parametrize('yontem', ('otomatik', 'kapali_bicim'))
    def test_kapali_bicim_ureticisiyle_bit_ayni(self, yontem):
        s = sa.esdeger_model_tablosu(
            'yakit', {'tur': 'dik_silindir', 'R_m': 0.5, 'H_m': 2.0},
            dict(SIVI, sigma_N_m=0.013, nu_m2_s=1.7e-7), yontem=yontem)
        assert s['yol'] == sa.YOL_SILINDIR_KAPALI_BICIM
        assert s['yontem'] == T.YONTEM_KAPALI_BICIM
        assert s['oneri_yontem'] is None and s['geometri_girdisi'] is None
        assert s['satir_durumlari'] == {'GECERLI': 29, 'BEYANLI': 0,
                                        'RET': 0}
        ref = sa.silindir_tablosu('yakit', 0.5, 2.0, 1141.0, 'LOX',
                                  sigma=0.013, nu=1.7e-7)
        assert s['tablo'].sozluk() == ref.sozluk()
        _tablo_sozlesmeli(s['tablo'])

    def test_tam_dikdortgen_profil_kapali_bicime_gider(self):
        R, H = 0.4, 1.5
        for prof in ([[0, 0], [R, 0], [R, H], [0, H]],
                     [[0, 0], [R / 2, 0], [R, 0], [R, 0.7], [R, H],
                      [0, H]]):
            s = sa.esdeger_model_tablosu(
                'oksitleyici', {'tur': 'profil', 'profil_rz_m': prof}, SIVI)
            assert s['yol'] == sa.YOL_SILINDIR_KAPALI_BICIM
            assert s['tablo'].geometri['tur'] == T.GEOMETRI_DIK_SILINDIR
            ref = sa.silindir_tablosu('oksitleyici', R, H, 1141.0, 'LOX')
            assert s['tablo'].satirlar == ref.satirlar

    def test_dikdortgen_taninmasi_tam_esitlik(self):
        R, H = 0.4, 1.5
        p = np.array([[0, 0], [R, 0], [R, H], [0, H]], dtype=float)
        assert sa._dik_silindir_profili_mi(p)
        q = p.copy()
        q[2, 0] = R * (1.0 - 1e-12)                  # eğik çeper
        assert not sa._dik_silindir_profili_mi(q)
        koni = np.array([[0, 0], [R / 2, 0], [R, H / 2], [R, H], [0, H]])
        assert not sa._dik_silindir_profili_mi(koni)
        assert not sa._dik_silindir_profili_mi(elips_basli_silindir(R, 1, 1))

    @pytest.mark.slow
    def test_sayisal_istenirse_se_ve_kapali_bicimle_uyusur(self):
        R, H = 0.5, 2.0
        s = sa.esdeger_model_tablosu(
            'yakit', {'tur': 'dik_silindir', 'R_m': R, 'H_m': H}, SIVI,
            yontem='sayisal')
        assert s['yol'] == sa.YOL_PROFIL_SAYISAL_SE
        assert s['yontem'] == T.YONTEM_SAYISAL_SE
        ref = sa.silindir_tablosu('yakit', R, H, 1141.0, 'LOX')
        for a, b in zip(s['tablo'].satirlar, ref.satirlar):
            # kök toleransı 1e-12 V_iç (TANK §C) → |Δh| ≤ 1e-12 H
            assert a['h_m'] == pytest.approx(b['h_m'], abs=1e-12 * H)
            assert a['kappa1_1m'] == pytest.approx(b['kappa1_1m'], rel=1e-6)
            assert a['m1_oran'] == pytest.approx(b['m1_oran'], rel=1e-6)
            assert a['z1_m'] == pytest.approx(b['z1_m'], abs=1e-6 * R)
        _tablo_sozlesmeli(s['tablo'])


class TestProfilKapaliBicimHes:
    """Açıkça istenen silindir formülü (CALKANTI §A.1.3, TANK §D.6)."""

    @pytest.fixture(scope='class')
    def elips21(self):
        p = elips_basli_silindir(0.5, 1.0, 0.5)
        return p, sa.esdeger_model_tablosu(
            'oksitleyici', {'tur': 'profil', 'profil_rz_m': p.tolist()},
            SIVI, yontem='kapali_bicim')

    def test_kubbe_bolgesi_ret_silindir_bolgesi_beyanli(self, elips21):
        p, s = elips21
        assert s['yol'] == sa.YOL_PROFIL_KAPALI_BICIM_H_ES
        assert s['yontem'] == T.YONTEM_KAPALI_BICIM
        assert s['oneri_yontem'] == sa.YONTEM_SECIMI_SAYISAL
        t = s['tablo']
        assert t.geometri['tur'] == T.GEOMETRI_PROFIL
        R = 0.5
        V_alt = 2.0 / 3.0 * math.pi * R * R * 0.5 * R      # 2:1 elips baş
        V_ic = t.geometri['V_ic_m3']
        for satir in t.satirlar:
            V = satir['V_sivi_m3']
            if V < V_alt * (1 - 1e-3) or V > (V_ic - V_alt) * (1 + 1e-3):
                assert satir['durum'] == T.DURUM_RET
                assert satir['sebep'] == ['KUBBE_BOLGESI_SILINDIR_FORMULU_YOK']
                assert all(satir[k] is None for k in T.SATIR_MODEL)
            elif V_alt * (1 + 1e-3) < V < (V_ic - V_alt) * (1 - 1e-3):
                assert satir['durum'] == T.DURUM_BEYANLI
                assert satir['sebep'] == ['TANK_BASLARI_MODELLENMEDI']
        assert s['satir_durumlari']['RET'] > 0
        assert s['satir_durumlari']['BEYANLI'] > 0
        _tablo_sozlesmeli(t)

    def test_geometri_profilden_model_h_es_silindirinden(self, elips21):
        p, s = elips21
        km = mp.kutle_ozellikleri_tablosu(p, 1141.0)['satirlar']
        R = 0.5
        for satir, k in zip(s['tablo'].satirlar, km):
            for alan in T.SATIR_GEOMETRI:
                assert satir[alan] == k[alan]          # gerçek tank
            if satir['durum'] == T.DURUM_RET:
                continue
            h_es = k['V_sivi_m3'] / (math.pi * R * R)
            m = sa.silindir_esdeger_model(R, h_es)
            assert satir['kappa1_1m'] == m['kappa1_1m']
            assert satir['m1_oran'] == m['m1_oran']
            assert satir['Gamma1'] == m['Gamma1']
            # konum serbest yüzeye göre taşınır
            assert (satir['z1_m'] - satir['h_m']) == pytest.approx(
                m['z1_m'] - h_es, abs=1e-14)
            assert satir['z_aski_m'] == satir['z1_m'] + satir['L1_m']
            # z0 gerçek KM'den (Dodge (3.2)), h_eş/2'den değil
            assert (satir['m0_oran'] * satir['z0_m']
                    + satir['m1_oran'] * satir['z1_m']) == pytest.approx(
                        satir['z_km_m'], abs=1e-13)
            assert satir['I0_kgm2'] is None
            assert satir['I0_kaynak'] == sa.I0_KAYNAK_H_ES

    def test_silindir_bolumu_yoksa_butun_satirlar_ret(self):
        s = sa.esdeger_model_tablosu(
            'n2o', {'tur': 'profil', 'profil_rz_m': orn.kure(0.3).tolist()},
            SIVI, yontem='kapali_bicim')
        assert s['satir_durumlari'] == {'GECERLI': 0, 'BEYANLI': 0,
                                        'RET': 29}
        assert s['oneri_yontem'] == sa.YONTEM_SECIMI_SAYISAL
        assert any('bütün satırlar RET' in k
                   for k in s['tablo'].sozluk()['kunye'])

    def test_ust_bas_duz_alt_bas_kubbeli(self):
        R, L = 0.5, 1.0
        p = elips_basli_silindir(R, L, 1.0)
        alt = p[p[:, 1] <= R + 1e-12]
        p2 = np.concatenate([alt, [[R, R + L], [0.0, R + L]]])
        s = sa.esdeger_model_tablosu(
            'yakit', {'tur': 'profil', 'profil_rz_m': p2.tolist()}, SIVI,
            yontem='kapali_bicim')
        sat = s['tablo'].satirlar
        assert sat[-1]['durum'] == T.DURUM_BEYANLI      # üst düz: kubbe yok
        assert sat[0]['durum'] == T.DURUM_RET           # alt kubbe

    @pytest.mark.slow
    @pytest.mark.parametrize('k, onek', ((0.5, 'elips21'),
                                         (1.0, 'yarim_kure')))
    def test_h_es_ile_se_farki_beyanin_icinde(self, k, onek):
        """Ürün yolunun (h_eş) SE'den sapması TANK_BASLARI_BEYANI
        sınırlarının içinde (beyan bu yol için doğru)."""
        R = 0.5
        p = elips_basli_silindir(R, 2.0 * R, k)
        tanim = {'tur': 'profil', 'profil_rz_m': p.tolist()}
        hes = sa.esdeger_model_tablosu('yakit', tanim, SIVI,
                                       yontem='kapali_bicim')['tablo']
        sev = sa.esdeger_model_tablosu('yakit', tanim, SIVI)
        assert sev['yol'] == sa.YOL_PROFIL_SAYISAL_SE    # otomatik → SE
        par = se.TANK_BASLARI_BEYANI['parametreler']
        n = 0
        for a, b in zip(hes.satirlar, sev['tablo'].satirlar):
            if a['durum'] == T.DURUM_RET:
                continue
            n += 1
            f1 = abs(math.sqrt(a['kappa1_1m'] / b['kappa1_1m']) - 1) * 100
            m1 = abs(a['m1_oran'] / b['m1_oran'] - 1) * 100
            assert f1 <= par[f'{onek}_f1_yuzde']
            assert m1 <= par[f'{onek}_m1_yuzde']
            assert abs(a['z1_m'] - b['z1_m']) <= par[f'{onek}_z1_R'] * R
            assert abs(a['z_aski_m'] - b['z_aski_m']) <= \
                par[f'{onek}_aski_R'] * R
        assert n >= 10


# ---------------------------------------------------------------------------
# Dosya / içe aktarıcı sonucu
# ---------------------------------------------------------------------------
class TestGeometriGirdisi:
    def test_simetrik_olmayan_tank_ret_ve_kod(self):
        s = sa.esdeger_model_tablosu(
            'oksitleyici', {'tur': 'dosya',
                            'yol': os.path.join(FIK, 'elips_002_bulut_mm.ply'),
                            'birim': 'mm', 'ust_yon': UST}, SIVI)
        assert s['yol'] == sa.YOL_GEOMETRI_RET
        assert s['tablo'] is None and s['yontem'] is None
        g = s['geometri_girdisi']
        assert g['durum'] == T.DURUM_RET
        assert g['sebep'] == ['EKSENEL_SIMETRIK_DEGIL']
        assert g['mesaj_anahtari'] == 'tank_geometry.eksenel_simetrik_degil.esik'
        assert 'profil_rz_m' not in g
        assert s['satir_durumlari'] == {'GECERLI': 0, 'BEYANLI': 0, 'RET': 0}

    @pytest.mark.parametrize('ad, kod', (('x.obj', 'BICIM_HATASI'),
                                         ('yok_boyle.stl', 'BICIM_HATASI')))
    def test_okuma_hatasi_ret(self, tmp_path, ad, kod):
        yol = tmp_path / ad
        if ad.endswith('.obj'):
            yol.write_text('v 0 0 0\n')
        s = sa.esdeger_model_tablosu(
            'yakit', {'tur': 'dosya', 'yol': str(yol), 'birim': 'm',
                      'ust_yon': UST}, SIVI)
        assert s['yol'] == sa.YOL_GEOMETRI_RET
        assert s['geometri_girdisi']['okuma_hatasi']['kod'] == kod
        assert kod in T.OKUYUCU_HATA_KODLARI

    def test_profil_kapisi_ret(self):
        s = sa.esdeger_model_tablosu(
            'yakit', {'tur': 'profil',
                      'profil_rz_m': [[0, 0], [1, 0.5], [1, 0.2], [0, 1]]},
            SIVI)
        assert s['yol'] == sa.YOL_GEOMETRI_RET
        assert s['geometri_girdisi']['sebep'] == ['PROFIL_TEK_DEGERLI_DEGIL']

    def test_geometri_beyani_butun_satirlara_yayilir(self):
        """K3a gürültü beyanı (v307-2 kodu) tablonun her satırına geçer."""
        p = elips_basli_silindir(0.5, 1.0, 0.5)
        g = tg.profil_girdisi_isle(p.tolist())
        assert g['durum'] == T.DURUM_GECERLI
        g = dict(g, durum=T.DURUM_BEYANLI,
                 sebep=['GURULTU_ESIKLE_KIYASLANABILIR'])
        s = sa.esdeger_model_tablosu(
            'oksitleyici', {'tur': 'geometri_sonucu', 'sonuc': g}, SIVI,
            yontem='kapali_bicim')
        for satir in s['tablo'].satirlar:
            assert 'GURULTU_ESIKLE_KIYASLANABILIR' in satir['sebep']
            assert satir['durum'] in (T.DURUM_BEYANLI, T.DURUM_RET)
        assert s['satir_durumlari']['GECERLI'] == 0
        assert any('GURULTU_ESIKLE_KIYASLANABILIR' in k
                   for k in s['tablo'].sozluk()['kunye'])
        _tablo_sozlesmeli(s['tablo'])

    def test_disaridan_gelen_sonuc_yeniden_kapidan_gecer(self):
        bozuk = {'durum': 'GECERLI', 'sebep': [],
                 'profil_rz_m': [[0, 0], [1, 0.5], [1, 0.2], [0, 1]]}
        s = sa.esdeger_model_tablosu(
            'yakit', {'tur': 'geometri_sonucu', 'sonuc': bozuk}, SIVI)
        assert s['yol'] == sa.YOL_GEOMETRI_RET
        p = elips_basli_silindir(0.5, 1.0, 0.5).tolist()
        ret_kodu = {'durum': 'GECERLI', 'sebep': ['EKSENEL_SIMETRIK_DEGIL'],
                    'profil_rz_m': p}
        with pytest.raises(T.SloshTabloHatasi) as e:
            sa.esdeger_model_tablosu(
                'yakit', {'tur': 'geometri_sonucu', 'sonuc': ret_kodu}, SIVI,
                yontem='kapali_bicim')
        assert e.value.kod == 'DEGER_GECERSIZ'

    @pytest.mark.slow
    def test_stl_kure_dosyasi_se_ve_kunye(self):
        yol = os.path.join(FIK, 'kure_r250mm_ikili.stl')
        s = sa.esdeger_model_tablosu(
            'n2o', {'tur': 'dosya', 'yol': yol, 'birim': 'mm',
                    'ust_yon': UST}, {'ad': 'N2O', 'rho_kg_m3': 785.0})
        assert s['yol'] == sa.YOL_PROFIL_SAYISAL_SE
        t = s['tablo']
        assert t.geometri['kaynak'].startswith('kure_r250mm_ikili.stl (sha256 ')
        assert s['geometri_girdisi']['kunye']['bicim'] == 'stl'
        assert s['satir_durumlari']['RET'] == 0
        _tablo_sozlesmeli(t)

    @pytest.mark.slow
    def test_gurultulu_bulut_beyani_se_tablosuna_yayilir(self):
        P = orn.ornekle(orn.kubbeli_silindir(0.5, 1.0), 60000, tohum=6,
                        gurultu=0.008 * 0.5)
        g = tg.nokta_bulutu_isle(P, ust_yon=UST)
        assert g['sebep'] == ['GURULTU_ESIKLE_KIYASLANABILIR']
        s = sa.esdeger_model_tablosu(
            'oksitleyici', {'tur': 'geometri_sonucu', 'sonuc': g}, SIVI)
        assert s['yol'] == sa.YOL_PROFIL_SAYISAL_SE
        for satir in s['tablo'].satirlar:
            assert 'GURULTU_ESIKLE_KIYASLANABILIR' in satir['sebep']
            assert satir['durum'] != T.DURUM_GECERLI


# ---------------------------------------------------------------------------
# Girdi kapıları (adlı ret, 500 yok)
# ---------------------------------------------------------------------------
class TestGirdiKapilari:
    SIL = {'tur': 'dik_silindir', 'R_m': 0.5, 'H_m': 2.0}

    @pytest.mark.parametrize('tank_id, tank, sivi, yontem, alan, sebep', (
        ('roket', SIL, SIVI, 'otomatik', 'tank_id', 'unknown_tank'),
        ('yakit', SIL, SIVI, 'tahmin', 'yontem', 'unknown_method'),
        ('yakit', [1, 2], SIVI, 'otomatik', 'tank', 'not_a_mapping'),
        ('yakit', {'tur': 'kup'}, SIVI, 'otomatik', 'tank.tur',
         'unknown_type'),
        ('yakit', dict(SIL, ek=1), SIVI, 'otomatik', 'tank.ek',
         'unknown_field'),
        ('yakit', {'tur': 'dik_silindir', 'R_m': 0.5}, SIVI, 'otomatik',
         'tank.H_m', 'missing_field'),
        ('yakit', dict(SIL, R_m=float('nan')), SIVI, 'otomatik', 'radius',
         'not_finite'),
        ('yakit', dict(SIL, H_m=-1.0), SIVI, 'otomatik', 'tank_height',
         'not_positive'),
        ('yakit', dict(SIL, R_m='0.5x'), SIVI, 'otomatik', 'radius',
         'not_a_number'),
        ('yakit', SIL, {'ad': 'x'}, 'otomatik', 'sivi.rho_kg_m3',
         'missing_field'),
        ('yakit', SIL, dict(SIVI, rho_kg_m3=0.0), 'otomatik',
         'fluid_density', 'not_positive'),
        ('yakit', SIL, dict(SIVI, sigma_N_m=float('inf')), 'otomatik',
         'surface_tension', 'not_finite'),
        ('yakit', SIL, dict(SIVI, renk='mavi'), 'otomatik', 'sivi.renk',
         'unknown_field'),
        ('yakit', SIL, dict(SIVI, ad=''), 'otomatik', 'sivi.ad',
         'out_of_range'),
        ('yakit', SIL, 'LOX', 'otomatik', 'sivi', 'not_a_mapping'),
        ('yakit', {'tur': 'profil', 'profil_rz_m': 'abc'}, SIVI, 'otomatik',
         'tank.profil_rz_m', 'not_a_list'),
        ('yakit', {'tur': 'profil',
                   'profil_rz_m': [[0, 0]] * (T.PROFIL_NOKTA_SINIRI + 1)},
         SIVI, 'otomatik', 'tank.profil_rz_m', 'above_size_limit'),
        ('yakit', {'tur': 'geometri_sonucu', 'sonuc': 5}, SIVI, 'otomatik',
         'tank.sonuc', 'not_a_mapping'),
    ))
    def test_adli_ret(self, tank_id, tank, sivi, yontem, alan, sebep):
        with pytest.raises(sa.SloshGirdiHatasi) as e:
            sa.esdeger_model_tablosu(tank_id, tank, sivi, yontem=yontem)
        assert (e.value.field, e.value.reason) == (alan, sebep)
        assert isinstance(e.value, ValueError)

    def test_kaynak_metni_kapisi(self):
        with pytest.raises(sa.SloshGirdiHatasi) as e:
            sa.esdeger_model_tablosu('yakit', self.SIL, SIVI,
                                     kaynak='x' * (T.METIN_BOY_SINIRI + 1))
        assert e.value.field == 'kaynak'


# ---------------------------------------------------------------------------
# Geriye uyum: K2'nin ve mevcut tüketicilerin içe aktardığı imzalar
# ---------------------------------------------------------------------------
IMZALAR = {
    (sa, 'analyze_slosh'): ['radius', 'fill_height', 'g_eff',
                            'fluid_density', 'liquid_mass', 'kwargs'],
    (sa.CylindricalTankSlosh, '__init__'): [
        'self', 'radius', 'fill_height', 'g_eff', 'fluid_density',
        'liquid_mass'],
    (sa.CylindricalTankSlosh, 'analyze'): [
        'self', 'control_frequencies', 'structural_frequencies',
        'coincidence_margin', 'baffle_width_ratio', 'baffle_depth_ratio',
        'sweep_heights', 'baffle_amplitude_ratio', 'surface_tension'],
    (sa.CylindricalTankSlosh, 'esdeger_model'): [
        'self', 'kinematic_viscosity', 'attachment_height'],
    (sa.CylindricalTankSlosh, 'recommend_baffle'): [
        'self', 'target_damping', 'depth_ratio', 'amplitude_ratio'],
    (sa, 'silindir_esdeger_model'): ['R', 'h'],
    (sa, 'silindir_tablosu'): ['tank_id', 'R', 'H', 'rho', 'sivi_adi',
                               'sigma', 'nu', 'kaynak'],
    (sa, 'duz_ceper_sonumu'): ['R', 'h', 'nu', 'g_eff'],
    (sa, 'silindir_yukleri'): ['R', 'h', 'rho', 'g_eff', 'z_baglanti_m'],
    (sa, 'kubbe_bolgesi_degerlendir'): ['V_sivi_m3', 'V_ic_m3',
                                        'V_alt_kubbe_m3', 'V_ust_kubbe_m3'],
    (sa, 'geff_frekans_haritasi'): ['tablo', 'g_eff_degerleri'],
    (se, 'se_tablosu'): ['tank_id', 'profil', 'rho_kg_m3', 'sivi_adi',
                         'sigma_N_m', 'nu_m2_s', 'kaynak', 'n_r', 'n_z',
                         'buyume'],
    (T, 'tablo_olustur'): ['tank_id', 'geometri', 'sivi', 'yontem',
                           'satirlar', 'kunye'],
    (T, 'bond_degerlendir'): ['rho_kg_m3', 'g_eff', 'R_m', 'sigma_N_m'],
    (T, 'omega1'): ['kappa1_1m', 'g_eff'],
    (T.SloshTablo, 'ara'): ['self', 'doluluk'],
    (T, 'json_oku'): ['metin_ya_da_bayt'],
    (T, 'csv_oku'): ['metin_ya_da_bayt'],
}


@pytest.mark.parametrize('sahip, ad', list(IMZALAR))
def test_genel_imzalar_degismedi(sahip, ad):
    beklenen = IMZALAR[(sahip, ad)]
    assert list(inspect.signature(getattr(sahip, ad)).parameters) == beklenen


def test_k2_cakisma_bandi_varsayilani_okunur():
    """K2 (six_dof_slosh) bandı imzadan okur; değer ve yer korunur."""
    v = inspect.signature(sa.CylindricalTankSlosh.analyze).parameters[
        'coincidence_margin'].default
    assert v == 0.20 and 0.0 < v <= sa.COINCIDENCE_MARGIN_MAX
