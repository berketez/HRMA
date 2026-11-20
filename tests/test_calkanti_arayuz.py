"""V307/ÇALKANTI-ARAYÜZ (KARTLAR K5) — çalkantı tank modeli uçları ve ekranı.

Ne kilitlenir (fizik ve sözleşme, bugünkü çıktı değil):
  * tablo yalnız tek girişten ve K4'ün 6-DOF'a verdiği tablonun AYNISI;
    motor kartının 1 g frekansıyla tablonunki tek sayı;
  * doluluk geçmişi motorun m(t) serisinden; t = 0'da yüklenen sıvı,
    yanma sonunda motorun yayımladığı kalıntı; ızgara düğümünde satır
    tablonun kendi satırı;
  * haritada f1 = √(κ1·g)/2π; formda verilen g_eff = hesaba giren g_eff;
  * dışa aktarılan tablo sözleşme okuyucusuyla geri okunur; zaman ekseni
    tablodan yeniden türetilebilir;
  * yükleme ucu: biçim beyaz listesi, birim zorunlu, boyut sınırı, yol
    geçişi yok, okuma hatası 400, geometri reddi 422 (simetrik olmayan tank
    "bu sürümde çözülmez"), 500 yok, geçici dizin silinir;
  * katıda "uygulanmaz"; ekran her sunucu kodunu EN + TR metne çevirir;
    her girdinin ipucu kodun sabitleriyle aynı sayıyı söyler.
"""

import ast
import contextlib
import shutil
import subprocess
import io
import json
import math
import pathlib
import re

import numpy as np
import pytest

from hrma.analysis import calkanti_arayuz as ca
from hrma.analysis import flight_vehicle as fv
from hrma.analysis import six_dof_slosh as k2
from hrma.analysis import slosh_motor_baglanti as smb
from hrma.analysis import slosh_tablo as st
from hrma.constants import G_0
from hrma.importers import tank_geometry_import as tg
from hrma.security.body_limit import REQUEST_BODY_MAX_BYTES
from tests.test_example_projects import NAMES

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
FIX = KOK / 'tests' / 'fixtures' / 'tank_geometry'
UC = '/api/slosh-analysis'
UC_YUKLE = '/api/slosh-analysis/tank-geometry'
UC_AKTAR = '/api/slosh-analysis/export'


def _coz(mt):
    from hrma.app import app  # noqa: F401  (uç kayıtları)
    doc = json.loads((KOK / 'examples' / (NAMES[mt] + '.hrma'))
                     .read_text(encoding='utf-8'))
    with contextlib.redirect_stdout(io.StringIO()):
        durum, govde = fv.run_page_calculation(
            mt, fv.page_payload(mt, doc['inputs']['fields']))
    assert durum == 200, govde
    return govde


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def sivi():
    return _coz('liquid')


@pytest.fixture(scope='module')
def hibrit():
    return _coz('hybrid')


def _model(client, govde):
    r = client.post(UC, json={'tank_modeli': govde})
    return r.status_code, r.get_json()


# ===========================================================================
# 1. /api/slosh-analysis — tank_modeli dalı (motor/tank görünümü)
# ===========================================================================
@pytest.mark.slow
class TestTankModeliSivi:

    def test_iki_tank_tablo_sozlesmeden_gecer(self, client, sivi):
        kod, j = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi})
        assert kod == 200, j
        g = j['tank_modeli']
        assert g['durum'] == 'HESAPLANDI' and g['sebep'] == []
        assert [t['tank_id'] for t in g['tanklar']] == ['oksitleyici', 'yakit']
        for t in g['tanklar']:
            st.dogrula(t['tablo'])          # sözleşme doğrulayıcısı
            assert t['tablo_yolu'] == 'silindir_kapali_bicim'
            assert len(t['tablo']['satirlar']) == len(st.DOLULUK_IZGARASI)

    def test_g_eff_verilmezse_g0_beyanli(self, client, sivi):
        _, j = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi})
        g = j['tank_modeli']
        assert g['g_eff_m_s2'] == [G_0]
        assert g['g_eff_kaynagi'] == 'varsayilan_g0'

    def test_tablo_k4un_6dofa_verdigi_tablonun_aynisi(self, client, sivi):
        _, j = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi})
        L = 3.3523
        bagli = smb.json_ozeti(smb.slosh_tanklari('liquid', sivi, arac_duzeni={
            'ardisik': {'sira': ['oksitleyici', 'yakit']},
            'govde_boyu_m': L}))
        k4 = {t['tank_id']: t['tablo'] for t in bagli['slosh_tanks']}
        assert set(k4) == {'oksitleyici', 'yakit'}
        for t in j['tank_modeli']['tanklar']:
            assert t['tablo'] == k4[t['tank_id']]

    def test_beyan_k4un_bagli_beyaniyla_ayni(self, client, sivi):
        _, j = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi})
        bagli = smb.slosh_tanklari('liquid', sivi, arac_duzeni={
            'ardisik': {'sira': ['oksitleyici', 'yakit']}, 'govde_boyu_m': 3.3523})
        yalniz_6dof = {'BAFL_SONUMU_UYGULANMADI',
                       'TANK_ISTASYONU_ARDISIK_DIZILIM'}
        k4 = {t['tank_id']: [b for b in t['beyan'] if b not in yalniz_6dof]
              for t in bagli['tanklar']}
        for t in j['tank_modeli']['tanklar']:
            assert t['beyan'] == k4[t['tank_id']]

    def test_tek_buyukluk_tek_sayi_motor_frekansi(self, client, sivi):
        _, j = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi})
        for t in j['tank_modeli']['tanklar']:
            f = t['f1_hz_1g']
            assert f['motor'] == f['tablo']

    def test_zaman_ekseni_motorun_serisinden(self, client, sivi):
        _, j = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi,
                               'g_eff_m_s2': 20.0})
        pt = sivi['propellant_tanks']
        anahtar = {'oksitleyici': 'oxidizer_tank', 'yakit': 'fuel_tank'}
        for t in j['tank_modeli']['tanklar']:
            pd = pt[anahtar[t['tank_id']]]['propellant_data']
            z = t['zaman']['satirlar']
            assert z[0]['t_s'] == 0.0 and z[0]['m_sivi_kg'] == pd['mass']
            assert z[-1]['m_sivi_kg'] == pytest.approx(
                pd['mass'] - pd['mass_nominal'], rel=1e-12)
            tablo = st.SloshTablo.sozlukten(t['tablo'])
            dugum = [r for r in z if r['doluluk'] in st.DOLULUK_IZGARASI]
            assert dugum, 'ızgara düğüm geçişi yok'
            for r in dugum:
                s = tablo.ara(r['doluluk'])
                assert r['kappa1_1m'] == s['kappa1_1m']
                assert r['m1_kg'] == pytest.approx(s['m1_oran'] * r['m_sivi_kg'],
                                                   rel=1e-15)
            # 3.0.7 ONARIM-ÇALK (M7-UCUS-13): alan adı sabit g_eff'i söyler
            for r in z:
                assert r['f1_sabit_geff_hz'] == pytest.approx(
                    math.sqrt(r['kappa1_1m'] * 20.0) / (2 * math.pi), rel=1e-14)
            ts = [r['t_s'] for r in z]
            assert ts == sorted(ts) and len(set(ts)) == len(ts)

    def test_harita_form_hesap_ayni_g(self, client, sivi):
        _, j = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi,
                               'g_eff_m_s2': [5.0, 25.0]})
        g = j['tank_modeli']
        assert len(g['g_eff_m_s2']) == ca.GEFF_ARALIK_NOKTA_SAYISI
        assert g['g_eff_m_s2'][0] == 5.0 and g['g_eff_m_s2'][-1] == 25.0
        t = g['tanklar'][0]
        h = t['frekans_haritasi']
        assert h['g_eff_m_s2'] == g['g_eff_m_s2']
        for i, s in enumerate(t['tablo']['satirlar']):
            for jj, gg in enumerate(h['g_eff_m_s2']):
                assert h['f1_hz'][i][jj] == pytest.approx(
                    math.sqrt(s['kappa1_1m'] * gg) / (2 * math.pi), rel=1e-14)
        assert t['yukler']['g_eff_m_s2'] == 25.0
        assert t['zaman']['sebep'] == ['CEPER_SONUMU_TEK_GEFF_ISTER']
        assert all(r['omega1_sabit_geff_rad_s'] is None
                   for r in t['zaman']['satirlar'])

    def test_yukler_iki_duzey_ve_g_ile_dogrusal(self, client, sivi):
        _, a = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi,
                               'g_eff_m_s2': 10.0})
        _, b = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi,
                               'g_eff_m_s2': 20.0})
        ya, yb = a['tank_modeli']['tanklar'][0]['yukler'], \
            b['tank_modeli']['tanklar'][0]['yukler']
        assert ya['durum'] == 'HESAPLANDI'
        for d in ('dogrusal_sinir', 'kirilma_ust_siniri'):
            for fa, fb in zip(ya['duzeyler'][d]['F1_N'], yb['duzeyler'][d]['F1_N']):
                # 3.0.7 ONARIM-ÇALK (M7-CALK-1): η ≥ h satırında yük
                # yayımlanmaz; η g'den bağımsız olduğu için iki g'de aynı satır
                if fa is None or fb is None:
                    assert fa is None and fb is None
                    continue
                assert fb == pytest.approx(2.0 * fa, rel=1e-12)

    def test_bafl_onerisi_yuklu_dolulukta_iki_kat_bant(self, client, sivi):
        _, j = _model(client, {'motor_type': 'liquid', 'motor_sonucu': sivi})
        b = j['tank_modeli']['tanklar'][0]['bafl']
        assert b['durum'] == 'HESAPLANDI'
        assert b['doluluk'] == j['tank_modeli']['tanklar'][0]['yuklu_doluluk']
        d = b['degerlendirme']
        assert d['damping_ratio'] == pytest.approx(
            b['oneri']['target_damping_ratio'], rel=1e-12)
        assert d['damping_ratio_high'] == pytest.approx(2 * d['damping_ratio'])
        assert d['damping_ratio_low'] == pytest.approx(d['damping_ratio'] / 2)


@pytest.mark.slow
class TestTankModeliHibrit:

    def test_bosalma_serisi_ve_tukenen_sivi(self, client, hibrit):
        kod, j = _model(client, {'motor_type': 'hybrid', 'motor_sonucu': hibrit})
        assert kod == 200, j
        t = j['tank_modeli']['tanklar'][0]
        assert t['tank_id'] == 'n2o'
        assert t['beyan'] == ['YOGUNLUK_SABIT', 'TUKETIM_BOSALMA_COZUMU']
        env = hibrit['motor']['tank_blowdown']['oxidizer_inventory']
        z = t['zaman']['satirlar']
        assert z[0]['m_sivi_kg'] == env['liquid_mass_kg'][0]
        assert z[-1]['m_sivi_kg'] == 0.0
        assert z[-1]['durum'] == 'RET' and z[-1]['sebep'] == ['IZGARA_DISI']
        assert z[-1]['m1_kg'] is None, 'tükenen sıvıda uydurma kütle yok'
        seri_t = set(env['liquid_mass_time_s'])
        assert seri_t <= {r['t_s'] for r in z}

    def test_tek_sayi_bir_ulp_icinde(self, client, hibrit):
        _, j = _model(client, {'motor_type': 'hybrid', 'motor_sonucu': hibrit})
        f = j['tank_modeli']['tanklar'][0]['f1_hz_1g']
        assert abs(f['motor'] - f['tablo']) <= 4 * np.spacing(f['motor'])

    def test_yuklenen_profil_se_ve_kaynak_dosyadan(self, client, hibrit):
        r = client.post(UC_YUKLE, data={
            'file': (io.BytesIO((FIX / 'kubbeli_silindir_bulut_mm.ply').read_bytes()),
                     'kubbeli.ply'), 'birim': 'mm', 'ust_yon': '0,0,1'},
            content_type='multipart/form-data')
        assert r.status_code == 200
        g = r.get_json()['geometri']
        kod, j = _model(client, {'motor_type': 'hybrid', 'motor_sonucu': hibrit,
                                 'tank_geometrileri': {'n2o': {
                                     'profil_rz_m': g['profil_rz_m'],
                                     'dosya_adi': g['kunye']['dosya_adi'],
                                     'sha256': g['kunye']['sha256'],
                                     'sebep': g['sebep']}}})
        assert kod == 200, j
        t = j['tank_modeli']['tanklar'][0]
        assert t['tablo_yolu'] == 'profil_sayisal_se'
        assert g['kunye']['sha256'] in t['geometri']['kaynak']
        # yük ve perde bağıntıları dik silindir içindir: adlı 'hesaplanmadı'
        assert t['yukler'] == {'durum': 'HESAPLANMADI',
                               'sebep': ['YUK_BAGINTISI_DIK_SILINDIR_ICIN']}
        assert t['bafl']['sebep'] == ['BAFL_BAGINTISI_DIK_SILINDIR_ICIN']

    def test_sigmayan_geometri_zaman_ekseni_kurmaz(self, client, hibrit):
        _, j = _model(client, {'motor_type': 'hybrid', 'motor_sonucu': hibrit,
                               'tank_geometrileri': {'n2o': {'profil_rz_m': [
                                   [0, 0], [0.05, 0], [0.05, 0.1], [0, 0.1]]}}})
        t = j['tank_modeli']['tanklar'][0]
        assert t['sebep'] == ['TANK_HACMI_YETERSIZ']
        assert t['zaman']['satirlar'] == []
        assert t['zaman']['sebep'] == ['ZAMAN_EKSENI_YOK']


class TestKatiVeKapilar:

    def test_kati_uygulanmaz(self, client):
        kod, j = _model(client, {'motor_type': 'solid'})
        assert kod == 200
        g = j['tank_modeli']
        assert g['durum'] == 'UYGULANMAZ' and g['sebep'] == ['TANK_YOK']
        assert g['tanklar'] == []

    def test_klasik_yanit_tank_modeli_tasimaz(self, client):
        r = client.post(UC, json={'radius': 0.5, 'fill_height': 1.0})
        assert r.status_code == 200
        assert 'tank_modeli' not in r.get_json()

    @pytest.mark.parametrize('govde,alan', [
        ({'tank_modeli': {'motor_type': 'x'}}, 'tank_modeli.motor_type'),
        ({'tank_modeli': {}}, 'tank_modeli.motor_type'),
        ({'tank_modeli': {'motor_type': 'liquid'}}, 'tank_modeli.motor_sonucu'),
        ({'tank_modeli': {'motor_type': 'solid', 'yol': '/etc'}}, 'tank_modeli.yol'),
        ({'tank_modeli': {'motor_type': 'solid'}, 'radius': 1}, 'radius'),
        ({'tank_modeli': 5}, 'tank_modeli'),
        ({'tank_modeli': {'motor_type': 'solid', 'g_eff_m_s2': True}}, 'g_eff_m_s2'),
        ({'tank_modeli': {'motor_type': 'solid', 'g_eff_m_s2': -1}}, 'g_eff_m_s2'),
        ({'tank_modeli': {'motor_type': 'solid', 'g_eff_m_s2': [5, 1]}}, 'g_eff_m_s2'),
        ({'tank_modeli': {'motor_type': 'solid', 'g_eff_m_s2': [1, 2, 3]}}, 'g_eff_m_s2'),
        ({'tank_modeli': {'motor_type': 'solid', 'g_eff_m_s2': 'x'}}, 'g_eff_m_s2'),
        ({'tank_modeli': {'motor_type': 'solid', 'yontem': 'eval'}}, 'tank_modeli.yontem'),
        ({'tank_modeli': {'motor_type': 'solid', 'tank_geometrileri': {
            'n2o': {'profil_rz_m': [[0, 0], [1, 0], [1, 1], [0, 1]]}}}},
         'tank_modeli.tank_geometrileri'),
    ])
    def test_adli_400(self, client, govde, alan):
        r = client.post(UC, json=govde)
        j = r.get_json()
        assert r.status_code == 400, j
        assert j['invalid_fields'][0]['field'] == alan

    @pytest.mark.parametrize('geo', [
        {'profil_rz_m': [[0, 0]], 'dosya_adi': '../../etc/passwd'},
        {'profil_rz_m': [[0, 0]], 'sha256': 'XYZ'},
        {'profil_rz_m': [[0, 0]], 'sebep': ['EKSENEL_SIMETRIK_DEGIL']},
        {'profil_rz_m': [[0, 0]], 'yol': '/tmp/x'},
        {'profil_rz_m': [[0, 0]] * (st.PROFIL_NOKTA_SINIRI + 1)},
        {'dosya_adi': 'a.csv'},
        {'profil_rz_m': 'r,z'},
    ])
    def test_geometri_girdisi_adli_400(self, client, geo):
        r = client.post(UC, json={'tank_modeli': {
            'motor_type': 'hybrid', 'motor_sonucu': {},
            'tank_geometrileri': {'n2o': geo}}})
        assert r.status_code == 400, r.get_json()
        assert r.get_json()['invalid_fields'][0]['field'].startswith(
            'tank_geometrileri')

    def test_bozuk_motor_sonucu_500_degil_adli_sebep(self, client):
        for sonuc in ({}, {'propellant_tanks': 5},
                      {'propellant_tanks': {'oxidizer_tank': {'propellant_data': 'x'}}},
                      {'motor': [1, 2]}, {'error': 'x'}):
            for mt in ('liquid', 'hybrid'):
                r = client.post(UC, json={'tank_modeli': {
                    'motor_type': mt, 'motor_sonucu': sonuc}})
                assert r.status_code in (200, 422), (mt, sonuc, r.get_json())
                j = r.get_json()
                if r.status_code == 200:
                    assert j['tank_modeli']['durum'] == 'HESAPLANMADI'
                    assert j['tank_modeli']['sebep']
                    assert all(t['tablo'] is None
                               for t in j['tank_modeli']['tanklar'])

    def test_yabanci_tank_kimligi_422(self, client):
        r = client.post(UC, json={'tank_modeli': {
            'motor_type': 'hybrid', 'motor_sonucu': {},
            'tank_geometrileri': {'yakit': {
                'profil_rz_m': [[0, 0], [1, 0], [1, 1], [0, 1]]}}}})
        assert r.status_code == 422
        assert r.get_json()['invalid_fields'][0]['reason'] == 'TANK_KIMLIGI'


# ===========================================================================
# 2. Tank geometrisi yükleme ucu — saldırgan dosya kümesi
# ===========================================================================
def _yukle(client, ad, veri, birim='mm', ust='0,0,1', ek=None):
    form = {'file': (io.BytesIO(veri), ad)}
    if birim is not None:
        form['birim'] = birim
    if ust is not None:
        form['ust_yon'] = ust
    form.update(ek or {})
    r = client.post(UC_YUKLE, data=form, content_type='multipart/form-data')
    return r.status_code, r.get_json()


class TestYuklemeUcu:

    def test_kabul_edilen_dosya_profil_ve_kunye(self, client):
        kod, j = _yukle(client, 'silindir_bulut_mm.csv',
                        (FIX / 'silindir_bulut_mm.csv').read_bytes())
        assert kod == 200, j
        g = j['geometri']
        assert g['durum'] in ('GECERLI', 'BEYANLI')
        assert g['kunye']['dosya_adi'] == 'silindir_bulut_mm.csv'
        assert re.fullmatch(r'[0-9a-f]{64}', g['kunye']['sha256'])
        assert g['geometri']['R_ref_m'] == pytest.approx(0.25, rel=1e-5)

    @pytest.mark.parametrize('ad,veri,kod,sebep', [
        ('bozuk.stl', b'\x00' * 84 + b'\xff\xff\xff\xff', 400, 'BICIM_HATASI'),
        ('nan.csv', b'r,z\n0,0\n1,nan\n0,1\n', 400, 'DEGER_GECERSIZ'),
        ('inf.xyz', b'0 0 0\n1 1 inf\n', 400, 'DEGER_GECERSIZ'),
        ('bos.csv', b'', 400, 'BICIM_HATASI'),
        ('ikili.csv', b'r,z\n\x00\x01\x02', 400, 'BICIM_HATASI'),
        ('a.exe', b'MZ\x90\x00', 400, 'BICIM_HATASI'),
        ('a.pkl', b'\x80\x04\x95', 400, 'BICIM_HATASI'),
        ('a.step', b'not a step', 400, 'BICIM_HATASI'),
    ])
    def test_bozuk_dosyalar_adli_400(self, client, ad, veri, kod, sebep):
        k, j = _yukle(client, ad, veri)
        assert k == kod, j
        assert j['kod'] == sebep
        assert j['status'] == 'error' and j['message']

    def test_asiri_buyuk_413(self, client):
        sinir = tg.TANK_STEP_BOYUT_SINIRI
        k, j = _yukle(client, 'dev.step', b'0' * (sinir + 2 * 1024 * 1024))
        assert k == 413 and j['kod'] == 'BOYUT_SINIRI'

    def test_govde_tavani_413(self, client):
        k, j = _yukle(client, 'dev.csv', b'0' * (REQUEST_BODY_MAX_BYTES + 10))
        assert k == 413

    def test_simetrik_olmayan_bulut_cozulmez_422(self, client):
        k, j = _yukle(client, 'elips.ply',
                      (FIX / 'elips_002_bulut_mm.ply').read_bytes())
        assert k == 422, j
        assert j['kod'] == 'EKSENEL_SIMETRIK_DEGIL'
        assert j['mesaj_anahtari'] == 'tank_geometry.eksenel_simetrik_degil.esik'
        assert 'not solved in this version' in j['message']

    def test_yol_gecisli_ad_temizlenir_ve_gecici_dizin_silinir(self, client,
                                                                monkeypatch):
        import tempfile
        dizinler = []
        gercek = tempfile.mkdtemp

        def kaydet(*a, **kw):
            d = gercek(*a, **kw)
            dizinler.append(d)
            return d
        monkeypatch.setattr(tempfile, 'mkdtemp', kaydet)
        k, j = _yukle(client, '../../../etc/passwd.csv',
                      b'r,z\n0,0\n1,0\n1,1\n0,1\n', birim='m', ust=None)
        assert k == 200, j
        ad = j['geometri']['kunye']['dosya_adi']
        assert '/' not in ad and '..' not in ad and ad.endswith('.csv')
        assert dizinler and not any(pathlib.Path(d).exists() for d in dizinler)

    @pytest.mark.parametrize('birim,ust,ek,alan', [
        (None, None, None, 'birim'),
        ('cm', None, None, 'birim'),
        ('m', 'a,b,c', None, 'ust_yon'),
        ('m', '0,0,0', None, 'ust_yon'),
        ('m', 'nan,0,1', None, 'ust_yon'),
        ('m', None, {'yol': '/etc/passwd'}, 'yol'),
    ])
    def test_form_kapilari_adli_400(self, client, birim, ust, ek, alan):
        k, j = _yukle(client, 'a.csv', b'r,z\n0,0\n1,0\n1,1\n0,1\n',
                      birim=birim, ust=ust, ek=ek)
        assert k == 400, j
        assert j['alan'] == alan

    def test_dosyasiz_ve_json_govde_500_degil(self, client):
        r = client.post(UC_YUKLE, data={'birim': 'm'},
                        content_type='multipart/form-data')
        assert r.status_code == 400 and r.get_json()['kod'] == 'ALAN_EKSIK'
        r = client.post(UC_YUKLE, json={'file': 'x'})
        assert r.status_code == 400

    def test_birim_celiskisi_422(self, client):
        k, j = _yukle(client, 'p.csv', (FIX / 'profil_kubbeli_m.csv').read_bytes(),
                      birim='mm')
        assert k == 422 and j['kod'] == 'BIRIM_YOK'

    def test_ikinci_okuyucu_eval_pickle_yok(self):
        for yol in (KOK / 'hrma' / 'analysis' / 'calkanti_arayuz.py',):
            agac = ast.parse(yol.read_text(encoding='utf-8'))
            adlar = {n.id for n in ast.walk(agac) if isinstance(n, ast.Name)}
            modul = {a.name for n in ast.walk(agac)
                     if isinstance(n, (ast.Import, ast.ImportFrom))
                     for a in n.names}
            assert not ({'eval', 'exec'} & adlar)
            assert 'pickle' not in modul
        app_src = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')
        agac = ast.parse(app_src)
        fn = next(n for n in agac.body if isinstance(n, ast.FunctionDef)
                  and n.name == 'slosh_tank_geometry_upload')
        cagri = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                f = n.func
                cagri.add(f.id if isinstance(f, ast.Name) else
                          f.attr if isinstance(f, ast.Attribute) else '')
        modul = {a.name for n in ast.walk(fn)
                 if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        assert 'tank_geometrisi_oku' in cagri       # yalnız K3 okuyucusu
        assert not ({'eval', 'exec', 'loads', 'load'} & cagri)
        assert not ({'pickle', 'marshal', 'shelve'} & modul)


# ===========================================================================
# 3. Dışa aktarım (araç ekibine aktarım tablosu)
# ===========================================================================
@pytest.mark.slow
class TestDisaAktarim:

    def _al(self, client, sonuc, bicim, tank='yakit', g=20.0):
        r = client.post(UC_AKTAR, json={
            'tank_modeli': {'motor_type': 'liquid', 'motor_sonucu': sonuc,
                            'g_eff_m_s2': g},
            'disa_aktarim': {'tank_id': tank, 'bicim': bicim}})
        return r

    def test_json_tablo_dogrulanir_zaman_turetilebilir(self, client, sivi):
        r = self._al(client, sivi, 'json')
        assert r.status_code == 200
        assert 'HRMA_calkanti_liquid_yakit_aktarim.json' in \
            r.headers['Content-Disposition']
        p = json.loads(r.data.decode('utf-8'))
        assert p['sema'] == ca.AKTARIM_SEMASI
        tablo = st.SloshTablo.sozlukten(p['esdeger_model_tablosu'])
        kunye = ' '.join(p['kunye'])
        # ONARIM2-ÇALK-SEKME (M7-CALK-7): varsayılan dil TR; TR künyede
        # kapsam dışı gerekçesi Türkçe (eskiden K2'nin İngilizce cümlesi).
        assert ca.KAPSAM_DISI_GEREKCE_TR in kunye
        assert k2.KAPSAM_DISI_GEREKCE not in kunye
        assert 'Eksen kuralı' in kunye
        z = p['zaman_ekseni']['satirlar']
        assert z
        for r_ in z:
            s = tablo.ara(r_['doluluk'])
            for alan in ('kappa1_1m', 'L1_m', 'z1_m', 'z_aski_m', 'z0_m',
                         'm1_oran', 'z_km_m', 'I_km_donmus_kgm2'):
                assert r_[alan] == s[alan]
        assert set(p['zaman_ekseni']['birimler']) == {
            c for c, _ in ca.ZAMAN_SUTUNLARI}

    def test_doluluk_csv_sozlesme_okuyucusundan_gecer(self, client, sivi):
        r = self._al(client, sivi, 'csv_doluluk')
        assert r.status_code == 200
        assert r.headers['Content-Type'].startswith('text/csv')
        tablo = st.csv_oku(r.data)
        p = json.loads(self._al(client, sivi, 'json').data.decode('utf-8'))
        assert tablo.sozluk() == st.SloshTablo.sozlukten(
            p['esdeger_model_tablosu']).sozluk()

    def test_zaman_csv_json_ile_ayni(self, client, sivi):
        metin = self._al(client, sivi, 'csv_zaman').data.decode('utf-8')
        satirlar = metin.split('\n')
        assert satirlar[0] == ca.CSV_ZAMAN_KIMLIGI
        meta = json.loads(satirlar[1][len(ca.CSV_META_ONEKI):])
        assert meta['tank_id'] == 'yakit' and meta['g_eff_m_s2'] == 20.0
        import csv
        okuyucu = list(csv.reader(io.StringIO('\n'.join(satirlar[2:]))))
        assert tuple(okuyucu[0]) == tuple(c for c, _ in ca.ZAMAN_SUTUNLARI)
        p = json.loads(self._al(client, sivi, 'json').data.decode('utf-8'))
        z = p['zaman_ekseni']['satirlar']
        veri = [r for r in okuyucu[1:] if r]
        assert len(veri) == len(z)
        for hucre, r_ in zip(veri, z):
            for c, v in zip(okuyucu[0], hucre):
                if r_[c] is None:
                    assert v == ''
                elif c == 'sebep':
                    assert v == ';'.join(r_[c])
                elif c in ('durum', 'I0_kaynak'):
                    assert v == r_[c]
                else:
                    assert float(v) == r_[c]

    def test_bilinmeyen_bicim_ve_tablosuz_tank_400(self, client, sivi):
        assert self._al(client, sivi, 'xml').status_code == 400
        assert self._al(client, sivi, 'json', tank='n2o').status_code == 400
        r = client.post(UC_AKTAR, json={'tank_modeli': {'motor_type': 'solid'},
                                        'disa_aktarim': {'tank_id': 'n2o',
                                                         'bicim': 'json'}})
        assert r.status_code == 400
        r = client.post(UC_AKTAR, json={'tank_modeli': {'motor_type': 'solid'}})
        assert r.status_code == 400


# ===========================================================================
# 4. Ekran sözleşmesi (kaynak düzeyi): kod → EN + TR metin, ipucu ⟷ kod
# ===========================================================================
def _sozluk(dil):
    src = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    bas = src.index('        %s: {' % dil)
    son = src.index('        tr: {') if dil == 'en' else len(src)
    out = {}
    for m in re.finditer(r"^            '([^']+)': '((?:[^'\\]|\\.)*)',$",
                         src[bas:son], re.M):
        out[m.group(1)] = m.group(2).replace("\\'", "'")
    return out


EN, TR = _sozluk('en'), _sozluk('tr')
CALKANTI_JS = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')


def _js_harita(ad):
    i = CALKANTI_JS.index('const %s = {' % ad)
    govde = CALKANTI_JS[i:CALKANTI_JS.index('\n    };', i)]
    return dict(re.findall(r"'?([\w.]+)'?: '(panel\.calkanti\.[\w.]+)'", govde))


def test_her_sunucu_kodu_ekranda_en_tr_metin():
    harita = _js_harita('KOD')
    kodlar = (set(smb.KODLAR) | set(st.SEBEP_KODLARI) | set(ca.K5_KODLARI)
              | set(k2.K2_KODLARI))
    eksik = sorted(kodlar - set(harita))
    assert not eksik, f'ekranda metni olmayan kod: {eksik}'
    for kod, anahtar in harita.items():
        assert anahtar in EN and anahtar in TR, anahtar
        assert TR[anahtar] != EN[anahtar]


def test_her_ice_aktarici_metni_ekranda_ve_yer_tutucular_esit():
    harita = _js_harita('GEO')
    ph = re.compile(r'\{(\w+)\}')
    for (kod, ayrinti), sablon in tg.YEDEK_METINLER.items():
        anahtar = f'tank_geometry.{kod.lower()}.{ayrinti}'
        assert anahtar in harita, anahtar
        hedef = harita[anahtar]
        assert set(ph.findall(EN[hedef])) == set(ph.findall(sablon)), anahtar
        assert set(ph.findall(TR[hedef])) == set(ph.findall(sablon)), anahtar


def test_kati_satiri_brifteki_metin():
    assert TR['panel.calkanti.katiSatir'] == \
        'Katı motorda sıvı itici yoktur; çalkantı uygulanmaz.'
    assert 'mountSolid' in CALKANTI_JS
    feed = (JS / 'panels' / 'feed_panel.js').read_text(encoding='utf-8')
    assert 'HRMACalkanti.mountSolid(root)' in feed
    assert 'HRMACalkanti.motorDegisti()' in feed


def test_kapsam_disi_metni_k2_ile_ayni():
    assert EN['panel.calkanti.kapsamDisi'] == k2.KAPSAM_DISI_GEREKCE
    assert TR['panel.calkanti.kapsamDisi'] == (
        'Kontrol döngüsü modellenmedi; güdümlü araçta asıl risk bu '
        'bağlaşımdır, aktarım tablosu araç ekibinin GNC aracında kullanılır.')


def test_her_girdinin_ipucu_var_ve_kod_sabitleriyle_ayni():
    girdiler = re.findall(r'id="(clk_[\w]+)"', CALKANTI_JS)
    alanlar = [g for g in girdiler if g.startswith(('clk_geff', 'clk_yontem',
                                                     'clk_geo_tank', 'clk_geo_file',
                                                     'clk_geo_unit', 'clk_geo_up'))]
    assert len(alanlar) == 7
    ipuclari = re.findall(r"'(panel\.calkanti\.help\.[\w]+)'", CALKANTI_JS)
    # Besleme bölümü 7 girdi + 6-DOF tank yeri formu 3 girdi (yer kaynağı,
    # sıra, tank başına taban istasyonu)
    assert len(set(ipuclari)) == 10
    for g in ('sd_clk_yer', 'sd_clk_sira', "sd_clk_x_' + tid"):
        assert ('id="%s' % g) in CALKANTI_JS, g
    for k in ipuclari:
        assert k in EN and k in TR
    # ipucundaki sayılar koddan
    g0 = f'{G_0:g}'
    assert g0 in EN['panel.calkanti.help.g_eff_min']
    assert g0.replace('.', ',') in TR['panel.calkanti.help.g_eff_min']
    n = str(ca.GEFF_ARALIK_NOKTA_SAYISI)
    for k in ('panel.calkanti.help.g_eff_min', 'panel.calkanti.help.g_eff_max'):
        assert f' {n} ' in EN[k] and f' {n} ' in TR[k]
    mb = REQUEST_BODY_MAX_BYTES // (1024 * 1024)
    step_mb = tg.TANK_STEP_BOYUT_SINIRI // (1024 * 1024)
    assert f'{mb} MB' in EN['panel.calkanti.help.geo_file']
    assert f'STEP {step_mb} MB' in EN['panel.calkanti.help.geo_file']
    assert f'{mb} MB' in TR['panel.calkanti.help.geo_file']
    aci = round(math.degrees(math.acos(tg.TANK_UST_YON_COS_ESIGI)))
    assert f'{aci}°' in EN['panel.calkanti.help.geo_up']
    assert f'{aci}°' in TR['panel.calkanti.help.geo_up']
    assert set(tg.BIRIM_CARPANLARI) == {'m', 'mm', 'in'}
    for b in tg.BIRIM_CARPANLARI:
        assert f"['{b}', '{b}', '']" in CALKANTI_JS


def test_panelde_uydurma_yedek_sayi_yok():
    yorumsuz = re.sub(r'//[^\n]*', '', CALKANTI_JS)
    assert not re.search(r'\|\|\s*0(?![.\d])', yorumsuz)
    assert not re.search(r'\?\?\s*0(?![.\d])', yorumsuz)


# ===========================================================================
# 5. 6-DOF çalkantı bloğu (B; hüküm YAYIMLANMAZ)
# ===========================================================================
UC_6DOF = '/api/six-dof-analysis'
#: Kanıt aracı (ürün sayısı değil): örnek sıvı motorun tanklarını taşıyan
#: gövde; kanat ölçüleri ve kuru gövde kütlesi Fırlatma Sahası varsayılanı
#: düzeninde (K4 uçtan uca kurgusu), t_max yanmayı kapsar.
GOVDE_KANIT = {'body_diameter': 0.5, 'body_length': 3.6, 'nose_length': 0.4,
               'nose_type': 'ogive', 'fin_count': 4, 'fin_root_chord': 0.2,
               'fin_tip_chord': 0.1, 'fin_span': 1.33, 'fin_sweep': 0.08,
               'cd0': 0.45, 'launch_elevation_deg': 84.0,
               'launch_azimuth_deg': 90.0, 'rail_length': 5.0,
               'wind_speed': 0.0, 'wind_direction_deg': 0.0, 't_max': 40.0}


def _6dof_govde(sonuc, mt='liquid', **ek):
    arac = fv.normalize(mt, sonuc)
    ucus = arac['flight_thrust']
    g = dict(GOVDE_KANIT)
    g.update({
        'dry_mass': 18.0 + arac['engine_inert_mass']
        + (ucus['propellant_residual_kg'] or 0.0),
        'propellant_mass': ucus['propellant_consumed_kg'],
        'thrust': arac['thrust'], 'burn_time': arac['burn_time'],
        'engine_od_m': arac['engine_od_m'],
        'engine_length_m': arac['engine_length_m'],
    })
    if arac.get('thrust_curve') is not None:
        g['thrust_curve'] = arac['thrust_curve']
    g.update(ek)
    return {k: v for k, v in g.items() if v is not None}


def _6dof(client, govde):
    r = client.post(UC_6DOF, json=govde)
    return r.status_code, r.get_json()


def _anahtarlar(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _anahtarlar(v)
    elif isinstance(o, list):
        for v in o:
            yield from _anahtarlar(v)


@pytest.mark.slow
class TestAltiSdCalkanti:

    def test_yer_yoksa_baglanmaz_ve_ucus_bit_ayni(self, client, sivi):
        g = _6dof_govde(sivi)
        k0, j0 = _6dof(client, g)
        k1, j1 = _6dof(client, dict(g, calkanti={
            'motor_type': 'liquid', 'motor_sonucu': sivi}))
        assert k0 == k1 == 200
        assert 'calkanti' not in j0
        c = j1['calkanti']
        assert c['durum'] == 'BAGLANMADI'
        assert c['sebep'] == ['TANK_ISTASYONU_VERILMEDI']
        assert c['zaman'] is None
        assert j0['summary'] == j1['summary'] and j0['series'] == j1['series']

    def test_ardisik_dizilim_baglar_zaman_alani_hukum_yok(self, client, sivi):
        g = _6dof_govde(sivi, calkanti={
            'motor_type': 'liquid', 'motor_sonucu': sivi,
            'arac_duzeni': {'ardisik': {'sira': ['oksitleyici', 'yakit']}}})
        k, j = _6dof(client, g)
        assert k == 200, j
        c = j['calkanti']
        assert c['durum'] == 'BAGLANDI'
        # gövde ölçüleri bu isteğin aracından (istemciden değil)
        d = c['arac_duzeni']
        assert d['govde_boyu_m'] == g['body_length']
        assert d['govde_capi_m'] == g['body_diameter']
        assert d['burun_boyu_m'] == g['nose_length']
        assert d['motor_boyu_m'] == g['engine_length_m']
        z = c['zaman']
        assert z['time_s'] == j['series']['time']
        assert [t['tank_id'] for t in z['tanklar']] == ['oksitleyici', 'yakit']
        for t in z['tanklar']:
            for alan in ('eta_y_m', 'aci_deg', 'ceper_genlik_orani',
                         'kuvvet_y_N', 'moment_z_Nm', 'doluluk', 'm1_kg'):
                assert len(t[alan]) == len(z['time_s'])
        assert z['genlik_dogrusal_sinir_orani'] == st.GENLIK_DOGRUSAL_SINIR_ORANI
        assert c['rijit_karsilastirma'] is not None
        assert set(c['tank_durum_kodlari']) == {'oksitleyici', 'yakit'}
        # Hüküm YALNIZ ÇALKANTI-KARARLILIK sözleşmesi biçimindeyse yayımlanır
        # (birleşik ağaçta); eski dört an hükmü (K2 ilk sürümü) hiç çıkmaz.
        from hrma.app import _CALKANTI_HUKUM_ALANLARI
        st_ = c.get('slosh_stability')
        if st_ is None:
            yasak = {'hukum', 'anlar', 'slosh_stability', 'zeta_min', 'pencere'}
            assert not (yasak & set(_anahtarlar(j)))
        else:
            assert all(k in st_ for k in _CALKANTI_HUKUM_ALANLARI)
            assert len(z['dogrusal_gecerli']) == len(z['time_s'])
        x_yakit = next(t['x_tank_taban_m'] for t in c['tanklar']
                       if t['tank_id'] == 'yakit')
        # V307/UÇUŞ-GÖVDE: en arkadaki tankın iç tabanı motorun ön yüzünden
        # o tankın baş kalınlığı kadar öndedir (dizilim gövde türetme
        # kuralının tek tanımından: flight_vehicle.tank_stack; baş kalınlığı
        # motorun aynı tank için yayımladığı basınçlı kap bloğundan). Eski
        # beklenti (taban = L − motor) başı yok sayıyordu.
        bas_yakit = next(
            t['end_closure_thickness_m']
            for t in fv.normalize('liquid', sivi)['propellant_tanks']
            if t['key'] == 'fuel_tank')
        assert bas_yakit is not None and bas_yakit > 0.0
        assert x_yakit == pytest.approx(
            g['body_length'] - g['engine_length_m'] - bas_yakit)

    def test_dar_govdede_adli_sebep_uydurma_konum_yok(self, client, sivi):
        g = _6dof_govde(sivi, body_diameter=0.242, body_length=2.0,
                        calkanti={'motor_type': 'liquid', 'motor_sonucu': sivi,
                                  'arac_duzeni': {'ardisik': {
                                      'sira': ['yakit', 'oksitleyici']}}})
        k, j = _6dof(client, g)
        assert k == 200
        c = j['calkanti']
        assert c['durum'] == 'BAGLANMADI'
        assert 'TANK_GOVDEDEN_GENIS' in c['sebep']
        assert c['zaman'] is None

    @pytest.mark.parametrize('blok,kod,alan', [
        ('x', 400, 'calkanti'),
        ({'motor_type': 'liquid', 'yol': 1}, 400, 'calkanti.yol'),
        ({'motor_type': 'liquid', 'arac_duzeni': {
            'ardisik': {'sira': ['oksitleyici', 'yakit']},
            'govde_boyu_m': 99.0}}, 400, 'calkanti.arac_duzeni.govde_boyu_m'),
        ({'motor_type': 'liquid', 'arac_duzeni': {
            'ardisik': {'sira': ['n2o']}}}, 422, 'calkanti.arac_duzeni.ardisik.sira'),
        ({'motor_type': 'solid', 'motor_sonucu': {}, 'arac_duzeni': {
            'ardisik': {'sira': ['n2o']}}}, 422, 'calkanti.arac_duzeni'),
        ({'motor_type': 'liquid', 'motor_sonucu': None, 'arac_duzeni': {
            'ardisik': {'sira': ['oksitleyici', 'yakit']}}}, 422,
         'calkanti.motor_sonucu'),
    ])
    def test_blok_kapilari(self, client, sivi, blok, kod, alan):
        if (isinstance(blok, dict) and blok.get('motor_type') == 'liquid'
                and 'motor_sonucu' not in blok):
            blok = dict(blok, motor_sonucu=sivi)
        k, j = _6dof(client, _6dof_govde(sivi, calkanti=blok))
        assert k == kod, j
        assert j['invalid_fields'][0]['field'] == alan


# ===========================================================================
# 6. Hüküm sözleşmesi (ÇALKANTI-KARARLILIK, HUKUM_SOZLESMESI.md) — fikstür:
#    o kulvarın gerçek koşu gövdeleri (tests/fixtures/calkanti_hukum/).
# ===========================================================================
HUKUM_FIX = KOK / 'tests' / 'fixtures' / 'calkanti_hukum'
HUKUM_GOVDELERI = ('hukum_sivi_ox_on.json', 'hukum_sivi_yakit_on.json',
                   'hukum_hibrit.json')
#: Sözleşmenin kapalı kod listeleri (§1, §2, §4, §6, §7, §8). Bu dalın K2'si
#: sözleşmeden önceki sürümdür; liste sözleşme metninden.
SOZLESME_HUKUMLER = ('UYGULANMAZ', 'HUKUM_YOK', 'RIJIT_GOVDE_KARARSIZ',
                     'CALKANTI_KAYNAKLI_KARARSIZLIK', 'KARARLI')
SOZLESME_GEREKCELER = ('YANMA_ICI_CALKANTI_KARARSIZLIK_PENCERESI',
                       'YANMA_ICI_RIJIT_GOVDE_KARARSIZ',
                       'TARAMADA_KARARSIZLIK_YOK', 'TARAMA_DEGERLENDIRILEMEDI',
                       'SAYISAL_TUTARSIZLIK', 'COZUM_YAKINSAMADI',
                       'UCUS_APOJEYE_VARMADI', 'TANK_YOK', 'TANK_BAGLANMADI')
SOZLESME_SEBEPLER = ('RAYDA', 'DONDURULMUS_KATSAYI_GECERSIZ',
                     'CALKANTI_KAPALI', 'KALKIS_ANI_ALFA_TANIMSIZ',
                     'AN_ULASILMADI', 'UCUS_APOJEYE_VARMADI',
                     'COZUM_YAKINSAMADI', 'SAYISAL_TUTARSIZLIK', 'TANK_YOK',
                     'TANK_BAGLANMADI')
SOZLESME_BEYANLAR = ('DONMUS_MODELDE_YERCEKIMI_KINEMATIGI_YOK',
                     'TARAMA_KISMI_KAPSAM', 'GENLIK_DOGRUSAL_SINIR_DISI',
                     'YARI_DURAGAN_DEGIL', 'ZETA_MIN_DOGRULANAMADI',
                     'I0_UYGULANMADI', 'CEPER_SONUMU_HESAPLANAMADI',
                     'TANK_TUKETIMI_ITKIYLE_ORANTILI', 'TANK_YOGUNLUGU_SERIDEN',
                     'SONUM_TOPLANABILIRLIGI', 'RAY_STATIK_EGIM_SINIR_DISI',
                     'BAFL_GECERLILIK_DISI', 'TANK_YOGUNLUK_SERISI_DISI')
SOZLESME_BAFL_SEBEPLERI = ('ZETA_MIN_UST_SINIR_USTU', 'GEOMETRI_SILINDIR_DEGIL',
                           'HEDEF_HALKA_DIZISIYLE_SAGLANAMIYOR')


def _hukum(ad):
    return json.loads((HUKUM_FIX / ad).read_text(encoding='utf-8'))[
        'slosh_stability']


def _hk_harita():
    i = CALKANTI_JS.index('const HK = {')
    govde = CALKANTI_JS[i:CALKANTI_JS.index('\n    };', i)]
    out = {}
    for tablo in ('hukum', 'gerekce', 'sebep', 'kenar', 'an', 'mod'):
        j = govde.index('        %s: {' % tablo)
        parca = govde[j:govde.index('\n        },', j)]
        out[tablo] = dict(re.findall(
            r"^\s+(\w+): \['(panel\.calkanti\.hk\.[\w.]+)'", parca, re.M))
    return out


def test_hukum_gecidi_yalniz_sozlesmeli_cikti():
    from hrma.app import _calkanti_hukum_blogu
    idx = np.array([0, 2, 4])
    eski = {'time': np.arange(5.0), 'slosh_stability': {
        'hukum': 'KARARLI', 'sebep': [], 'anlar': {}, 'tanklar': []}}
    assert _calkanti_hukum_blogu(eski, idx) == (None, None)
    for ad in HUKUM_GOVDELERI:
        st_ = _hukum(ad)
        res = {'time': np.arange(5.0), 'slosh_stability': st_,
               'slosh_linear_valid': np.array([1, 1, 1, 0, 0], dtype=bool)}
        h, maske = _calkanti_hukum_blogu(res, idx)
        assert h is st_
        assert maske == [True, True, False]
    # boyu tutmayan maske yayımlanmaz
    res = {'time': np.arange(5.0), 'slosh_stability': _hukum(HUKUM_GOVDELERI[0]),
           'slosh_linear_valid': np.ones(3, dtype=bool)}
    assert _calkanti_hukum_blogu(res, idx)[1] is None


def test_fikstur_govdeleri_sozlesme_alanlarini_tasiyor():
    from hrma.app import _CALKANTI_HUKUM_ALANLARI
    for ad in HUKUM_GOVDELERI:
        st_ = _hukum(ad)
        assert all(k in st_ for k in _CALKANTI_HUKUM_ALANLARI), ad
        assert st_['genel_hukum'] in SOZLESME_HUKUMLER
        assert st_['gerekce_kodu'] in SOZLESME_GEREKCELER


def test_sozlesmenin_her_kodu_ekranda_en_tr_metin():
    hk_ = _hk_harita()
    kod = _js_harita('KOD')
    for tablo, liste in (('hukum', SOZLESME_HUKUMLER),
                         ('gerekce', SOZLESME_GEREKCELER),
                         ('sebep', SOZLESME_SEBEPLER),
                         ('kenar', ('ISARET_DEGISIMI', 'DEGERLENDIRME_SINIRI')),
                         ('an', k2.ANLAR), ('mod', ('calkanti', 'govde'))):
        eksik = sorted(set(liste) - set(hk_[tablo]))
        assert not eksik, (tablo, eksik)
        for anahtar in hk_[tablo].values():
            assert anahtar in EN and anahtar in TR, anahtar
    eksik = sorted((set(SOZLESME_BEYANLAR) | set(SOZLESME_BAFL_SEBEPLERI))
                   - set(kod))
    assert not eksik, eksik


def _fikstur_kodlari(st_):
    """Bir hüküm gövdesinin ekrana inen bütün kodları: (tablo, kod)."""
    out = {('hukum', st_['genel_hukum']), ('gerekce', st_['gerekce_kodu'])}
    out |= {('sebep', k) for k in st_['sebep']}
    out |= {('KOD', k) for k in st_['beyanlar']}
    for w in st_['pencereler']:
        out |= {('kenar', w['t1_kenar']), ('kenar', w['t2_kenar']),
                ('mod', w['mod'])}
        out |= {('KOD', k) for k in w['beyanlar']}
    for a in st_['dort_an']:
        out |= {('an', a['an']), ('hukum', a['hukum'])}
        if a['sebep']:
            out.add(('sebep', a['sebep']))
    for a in st_['tarama']['kapsam']['hukum_verilemeyen']:
        out.add(('sebep', a['sebep']))
        out |= {('KOD', k) for k in a['kodlar']}
    b = st_['bafl_onerisi']
    if b:
        out |= {('KOD', k) for k in b.get('beyanlar') or []}
        for d in ('nominal', 'tutucu'):
            for t in (b.get(d) or {}).get('tanklar') or []:
                if t.get('sebep'):
                    out.add(('KOD', t['sebep']))
    for t in st_['tanklar']:
        out |= {('KOD', k) for k in t['kodlar']}
    return out


def test_fikstur_govdelerinin_her_kodu_ekranda():
    hk_ = _hk_harita()
    kod = _js_harita('KOD')
    for ad in HUKUM_GOVDELERI:
        for tablo, k in _fikstur_kodlari(_hukum(ad)):
            harita = kod if tablo == 'KOD' else hk_[tablo]
            assert k in harita, (ad, tablo, k)


@pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
def test_dogrusal_sinir_sonrasi_iz_kesik_ve_adli(tmp_path):
    betik = tmp_path / 'm.js'
    betik.write_text(
        "global.window = {location: {pathname: '/liquid'}};\n"
        "global.document = {};\n"
        "require(%r);\n"
        "const C = window.HRMACalkanti;\n"
        "const iz = C._maskeliIzler([{x: [0, 1, 2, 3], y: [1, 2, 3, 4], name: 'a', line: {}}],"
        " [true, true, false, false]);\n"
        "const tam = C._maskeliIzler([{x: [0, 1], y: [1, 2], name: 'b', line: {}}], [true, true]);\n"
        "process.stdout.write(JSON.stringify({iz: iz, tam: tam}));\n"
        % str(JS / 'calkanti_panel.js'), encoding='utf-8')
    p = subprocess.run([shutil.which('node'), str(betik)], capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    d = json.loads(p.stdout)
    gecerli, disi = d['iz']
    assert gecerli['y'] == [1, 2, None, None]
    assert disi['y'] == [None, 2, 3, 4]          # sınırdan önceki son nokta dahil
    assert disi['line']['dash'] == 'dash' and disi['opacity'] < 1
    assert 'outside the validity of the linear model' in disi['name']
    assert len(d['tam']) == 1 and d['tam'][0]['y'] == [1, 2]


def test_hukum_alani_ham_kod_basmaz_ve_kurala_uyar():
    """Kaynak düzeyi: hüküm çiziminde sunucu kodu doğrudan basılmaz; aşım
    varsa bağlaşık apoje/max α gerçek değer gibi basılmaz."""
    i = CALKANTI_JS.index('function hukumHtml(h')
    govde = CALKANTI_JS[i:CALKANTI_JS.index('function baflOnerisiHtml', i)]
    assert 'esc(h.genel_hukum)' not in govde and 'esc(w.mod)' not in govde
    assert "hk('hukum', h.genel_hukum)" in govde
    # V307/UÇUŞ-GÖVDE (kalem 6): sınır aşıldıysa bağlaşık koşunun apojesi
    # ve hücum açısı HİÇ basılmaz (yanıtta da null; eskiden "geçerlilik
    # dışı" yazısıyla aynı satırda duruyordu); yerine nedeni ve rijit
    # koşunun zorunlu referans etiketi. Bağlaşık sayı yalnız sınır
    # aşılmadığı dalda basılır.
    # ONARIM2-ÇALK-SEKME (M7-UCUS-4 a): dal koşulu artık yayım kaydının iki
    # neden kodundan (``yayimlanmaz``), yalnız sınır aşımından değil.
    blok = re.search(r'if \(yayimlanmaz\) \{(.*?)\} else \{(.*?)\n            \}',
                     CALKANTI_JS, re.S)
    assert blok, 'sixdofCiz apoje bloğu bulunamadı'
    asim, gecerli = blok.group(1), blok.group(2)
    assert 's.apogee' not in asim and 's.max_alpha_deg' not in asim
    assert 'panel.calkanti.sd.bagliYayimlanmadi' in asim
    assert 'referansMetni(rk)' in asim
    assert 'n(s.apogee, 1)' in gecerli and 'n(rk.apogee, 1)' in gecerli
    assert "maskeliIzler(" in CALKANTI_JS and 'dogrusal_gecerli' in CALKANTI_JS
