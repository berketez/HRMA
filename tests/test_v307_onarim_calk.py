"""3.0.7 ONARIM-ÇALK — mühendis turu (19 Kas) çalkantı bulgularının bekçileri.

Ne kilitlenir (fizik ve sözleşme, bugünkü çıktı değil):
  * M7-CALK-15: bağlanmayan tank varken çalkantı hükmü KARARLI olamaz; hüküm
    ve yayım kaydı bağlanmayan tankı adıyla taşır (yayımlanan koşu KISMİ
    bağlaşık); kararsızlık hükmü eksik tankla kalkmaz.
  * M7-UCUS-1: doğrusal sınır aşıldığında da rozetin üstünde köprü cümlesi
    vardır; statik marj satırındaki "KARARLI"nın yalnız marj bandı olduğunu
    söyler.
"""
import contextlib
import io
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from hrma.analysis import flight_vehicle as fv
from hrma.analysis import six_dof_slosh as k2
from tests.test_example_projects import NAMES

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
UC_6DOF = '/api/six-dof-analysis'


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


def _istek(arac, mt, sonuc, **ek):
    """Motor sayfası 6-DOF panelinin türetilmiş gövdeyle kurduğu istek
    (``tests/test_v307_ucus_govde.py`` ile aynı kurgu)."""
    g = arac['airframe_resolved']
    u = arac['flight_thrust']
    govde = {
        'body_diameter': g['body_diameter_m'],
        'body_length': g['nose_length_m'] + g['length_behind_nose_m'],
        'nose_length': g['nose_length_m'], 'nose_type': g['nose_type'],
        'fin_count': 4, 'fin_geometry_rule': 'static_margin',
        'cd0': 0.45, 'wind_speed': 5, 'wind_direction_deg': 0,
        'launch_elevation_deg': 90, 'launch_azimuth_deg': 0, 'rail_length': 5,
        'dry_mass': arac['engine_inert_mass']
        + (u.get('propellant_residual_kg') or 0.0),
        'propellant_mass': u['propellant_consumed_kg'],
        'thrust': arac['thrust'], 'burn_time': arac['burn_time'],
        'nozzle_exit_area': u['nozzle_exit_area_m2'],
        'thrust_reference_pressure': u['thrust_reference_pressure_pa'],
        'engine_od_m': arac['engine_od_m'],
        'engine_length_m': arac['engine_length_m'],
        'calkanti': {'motor_type': mt, 'motor_sonucu': sonuc,
                     'arac_duzeni': {'ardisik': {}}},
    }
    if arac['thrust_curve'] is not None:
        govde['thrust_curve'] = arac['thrust_curve']
    govde.update(ek)
    return {k: v for k, v in govde.items() if v is not None}


def _gonder(client, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = client.post(UC_6DOF, json=govde)
    return r.status_code, r.get_json()


def _js_islevi(kaynak, ad):
    """``function ad(...) { ... }`` gövdesini süslü ayraç sayarak kes."""
    bas = kaynak.index('function ' + ad + '(')
    i = kaynak.index('{', bas)
    derinlik = 0
    for j in range(i, len(kaynak)):
        if kaynak[j] == '{':
            derinlik += 1
        elif kaynak[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[bas:j + 1]
    raise AssertionError(ad + ' kapanmıyor')


def _sozluk_degeri(anahtar, dil):
    """i18n_common.js'te anahtarın EN (0) / TR (1) değeri."""
    metin = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    bulunan = re.findall(r"^\s*'%s': '((?:[^'\\]|\\.)*)',$" % re.escape(anahtar),
                         metin, re.M)
    assert len(bulunan) == 2, (anahtar, len(bulunan))
    return bulunan[{'en': 0, 'tr': 1}[dil]].replace("\\'", "'")


def _node(betik_metni, tmp_path):
    if shutil.which('node') is None:
        pytest.skip('node yok')
    betik = tmp_path / 'b.js'
    betik.write_text(betik_metni, encoding='utf-8')
    p = subprocess.run([shutil.which('node'), str(betik)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


# ===========================================================================
# M7-CALK-15 — kısmi bağlama
# ===========================================================================
class TestKismiBaglama:

    def _st(self, hukum):
        return {'genel_hukum': hukum, 'hukum': hukum, 'gerekce_kodu': 'X',
                'sebep': [], 'beyanlar': ['DONMUS_MODELDE_YERCEKIMI_KINEMATIGI_YOK']}

    def test_bagli_tank_eksikse_kararli_verilmez(self):
        st = k2.kismi_baglama_hukmu(self._st(k2.HUKUM_KARARLI), ['oksitleyici'])
        assert st['genel_hukum'] == st['hukum'] == k2.HUKUM_YOK
        assert st['gerekce_kodu'] == k2.GEREKCE_KISMI_BAGLAMA
        assert st['sebep'] == [k2.SEBEP_KISMI_BAGLAMA]
        assert st['baglanmayan_tanklar'] == ['oksitleyici']
        assert k2.BEYAN_KISMI_BAGLAMA in st['beyanlar']
        # kodlar sözleşme listelerinde ve beyan sözlüğünde
        assert k2.GEREKCE_KISMI_BAGLAMA in k2.GEREKCE_KODLARI
        assert k2.SEBEP_KISMI_BAGLAMA in k2.HUKUM_SEBEPLERI
        assert k2.K2_KODLARI[k2.BEYAN_KISMI_BAGLAMA][0] == k2.SINIF_BEYAN

    @pytest.mark.parametrize('hukum', [k2.HUKUM_CALKANTI_KARARSIZ,
                                       k2.HUKUM_RIJIT_KARARSIZ])
    def test_kararsizlik_eksik_tankla_kalkmaz(self, hukum):
        st = k2.kismi_baglama_hukmu(self._st(hukum), ['yakit'])
        assert st['genel_hukum'] == hukum
        assert st['baglanmayan_tanklar'] == ['yakit']
        assert k2.BEYAN_KISMI_BAGLAMA in st['beyanlar']

    def test_hicbir_tank_bagli_degilse_kismi_sayilmaz(self):
        st = k2.uygulanmaz_ciktisi('TANK_BAGLANMADI')
        k2.kismi_baglama_hukmu(st, ['n2o'])
        assert st['genel_hukum'] == k2.HUKUM_UYGULANMAZ
        assert 'baglanmayan_tanklar' not in st and st['beyanlar'] == []

    def test_hepsi_bagliysa_hukum_degismez(self):
        st = k2.kismi_baglama_hukmu(self._st(k2.HUKUM_KARARLI), [])
        assert st['genel_hukum'] == k2.HUKUM_KARARLI
        assert 'baglanmayan_tanklar' not in st

    def test_genis_lox_tanki_sigmayinca_kararli_ve_bagli_apoje_yok(
            self, client, sivi):
        """Mühendis adımı (M7-CALK-15): örnek sıvı motora R 0,30 m × H 0,80 m
        oksitleyici tankı (gövde dış çapı 0,480 m'ye sığmaz). ÖNCE: durum
        KISMI, hüküm KARARLI, apoje 'bağlaşık koşu (yayımlanan)'."""
        arac = fv.normalize('liquid', sivi)
        govde = _istek(arac, 'liquid', sivi)
        govde['calkanti']['tank_geometrileri'] = {'oksitleyici': {
            'profil_rz_m': [[0.0, 0.0], [0.3, 0.0], [0.3, 0.8], [0.0, 0.8]]}}
        kod, y = _gonder(client, govde)
        assert kod == 200, y
        c = y['calkanti']
        assert c['durum'] == 'KISMI'
        durum = {t['tank_id']: t['durum'] for t in c['tanklar']}
        assert durum['oksitleyici'] == 'BAGLANMADI'
        st = c['slosh_stability']
        assert st['genel_hukum'] != k2.HUKUM_KARARLI
        assert st['baglanmayan_tanklar'] == ['oksitleyici']
        assert k2.BEYAN_KISMI_BAGLAMA in st['beyanlar']
        yayim = c['yayim']
        assert yayim['kapsam'] == 'KISMI_BAGLASIK'
        assert yayim['baglanmayan_tanklar'] == ['oksitleyici']

    def test_panel_kismi_kapsami_adiyla_yazar(self, tmp_path):
        clk = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        for anahtar in ('panel.calkanti.hk.gerekce.BAGLANMAYAN_TANK_VAR',
                        'panel.calkanti.hk.sebep.TANK_KISMEN_BAGLANMADI',
                        'panel.calkanti.kod.HUKUM_YALNIZ_BAGLANAN_TANKLAR'):
            assert "'%s'" % anahtar in clk
            for dil in ('en', 'tr'):
                assert _sozluk_degeri(anahtar, dil)
        for anahtar in ('panel.calkanti.sd.apojeKismi',
                        'panel.calkanti.hk.kismiKapsam',
                        'panel.calkanti.hk.anaNotKismi'):
            for dil in ('en', 'tr'):
                assert '{tanklar}' in _sozluk_degeri(anahtar, dil)
        notlar = _node(
            "global.window = {location: {pathname: '/liquid'}};\n"
            "const eklenen = [];\n"
            "const rozet = {parentNode: {insertBefore: (d, r) => eklenen.push(d)}};\n"
            "global.document = {getElementById: (id) => (id === 'sd_badges' ? rozet : null),"
            " createElement: () => ({style: {}})};\n"
            "require(%r);\n"
            "const C = window.HRMACalkanti;\n"
            "C._hukumNotunuKoy({genel_hukum: 'HUKUM_YOK', gerekce_kodu: 'BAGLANMAYAN_TANK_VAR',"
            " pencereler: [], rijit_pencereler: [], baglanmayan_tanklar: ['oksitleyici']});\n"
            "C._hukumNotunuKoy({genel_hukum: 'KARARLI', pencereler: [], rijit_pencereler: []});\n"
            "process.stdout.write(JSON.stringify(eklenen.map(d => d.textContent)));\n"
            % str(JS / 'calkanti_panel.js'), tmp_path)
        assert len(notlar) == 1
        assert 'Oxidiser tank' in notlar[0] or 'Oxidizer tank' in notlar[0], notlar


# ===========================================================================
# M7-UCUS-1 — köprü cümlesi sınır aşımında da
# ===========================================================================
class TestKopruCumlesi:

    def test_sinir_asiminda_marj_bandi_notu(self, tmp_path):
        for dil, parca in (('tr', 'statik marjın bandıdır'),
                           ('en', 'static-margin band')):
            m = _sozluk_degeri('panel.calkanti.hk.anaNotSinir', dil)
            assert parca in m and '{hukum}' in m and '{pencere}' in m
        notlar = _node(
            "global.window = {location: {pathname: '/liquid'}};\n"
            "const eklenen = [];\n"
            "const rozet = {parentNode: {insertBefore: (d, r) => eklenen.push(d)}};\n"
            "global.document = {getElementById: (id) => (id === 'sd_badges' ? rozet : null),"
            " createElement: () => ({style: {}})};\n"
            "require(%r);\n"
            "const C = window.HRMACalkanti;\n"
            "C._hukumNotunuKoy({genel_hukum: 'CALKANTI_KAYNAKLI_KARARSIZLIK',"
            " pencereler: [{t1: 6.794, t2: 30.0}], rijit_pencereler: [],"
            " dogrusal_sinir: {asildi: true, t_ilk_asim_s: 27.93}});\n"
            "process.stdout.write(JSON.stringify(eklenen.map(d => d.textContent)));\n"
            % str(JS / 'calkanti_panel.js'), tmp_path)
        assert len(notlar) == 1
        assert 'static-margin band' in notlar[0] and '6.79' in notlar[0]


# ===========================================================================
# M7-CALK-1 — sığ dolulukta η ≥ h: yük yayımlanmaz
# ===========================================================================
class TestSigDolulukYukleri:

    def test_lox_tanki_doluluk_0005_el_hesabi(self):
        """Mühendis el hesabı: R 0,2367 m, h 0,0059 m, η = 0,2 R = 0,04734 m
        > h. ÖNCE: F1 2,33 N, p_dinamik 529,77 Pa, sebep []."""
        from hrma.analysis import slosh_analysis as sa
        y = sa.silindir_yukleri(0.2367, 0.0059, 1141.16, 9.80665)
        for ad in ('dogrusal_sinir', 'kirilma_ust_siniri'):
            d = y['duzeyler'][ad]
            assert sa.GENLIK_DERINLIK_KODU in d['sebep'], ad
            for alan in ('x1_m', 'F1_N', 'M1_km_Nm', 'p_dinamik_yuzey_Pa',
                         'p_taban_Pa', 'M_baglanti_Nm'):
                assert d[alan] is None, (ad, alan)
        # derin dolulukta doğrusal düzey yayımlanır (sınır η = h'de)
        y = sa.silindir_yukleri(0.2367, 0.2, 1141.16, 9.80665)
        d = y['duzeyler']['dogrusal_sinir']
        assert d['sebep'] == [] and d['F1_N'] > 0.0
        y = sa.silindir_yukleri(0.5, 0.1, 1000.0, 9.80665)   # η = 0,1 = h
        assert y['duzeyler']['dogrusal_sinir']['F1_N'] is None

    def test_kod_panelde_ve_sozlukte(self):
        clk = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        anahtar = 'panel.calkanti.kod.GENLIK_SIVI_DERINLIGINI_ASIYOR'
        assert "'%s'" % anahtar in clk
        assert 'η ≥ h' in _sozluk_degeri(anahtar, 'tr')
        assert 'η ≥ h' in _sozluk_degeri(anahtar, 'en')


# ===========================================================================
# M7-CALK-2 — perde önerisinin tasarım genliği ekranda ve aktarımda
# M7-CALK-13 — tek tank formu: perde sıvının dışındaysa sönüm yok, kod ekranda
# ===========================================================================
class TestPerdeGenligiVeGecerlilik:

    def test_tasarim_genligi_yayimlanir_ve_sonumu_uretir(self, client, sivi):
        """El hesabı (mühendis, Dodge 2000 Denk. (2.16)): γ = 2,83 e^(−4,6
        d/R) C1^1,5 √(η/R), C1 = (w/R)(2 − w/R); ekrandaki 0,0100 yalnız
        η/R = 0,05 ile çıkar."""
        import math
        r = client.post('/api/slosh-analysis', json={'tank_modeli': {
            'motor_type': 'liquid', 'motor_sonucu': sivi}})
        assert r.status_code == 200
        t = next(x for x in r.get_json()['tank_modeli']['tanklar']
                 if x['tank_id'] == 'oksitleyici')
        b = t['bafl']
        assert b['durum'] == 'HESAPLANDI'
        assert b['tasarim_genligi_eta_R'] == 0.05
        assert 'HRMA' in b['tasarim_genligi_kaynagi']
        w = b['oneri']['recommended_width_ratio']
        c1 = w * (2.0 - w)
        gamma = 2.83 * math.exp(-4.6 * b['derinlik_orani']) * c1 ** 1.5 \
            * math.sqrt(b['tasarim_genligi_eta_R'])
        assert b['degerlendirme']['damping_ratio'] == pytest.approx(gamma, rel=1e-12)
        # aktarım JSON'unda aynı öneri ve genlik
        r = client.post('/api/slosh-analysis/export', json={
            'tank_modeli': {'motor_type': 'liquid', 'motor_sonucu': sivi},
            'disa_aktarim': {'tank_id': 'oksitleyici', 'bicim': 'json'}})
        assert r.status_code == 200
        p = json.loads(r.data.decode('utf-8'))
        assert p['bafl_onerisi']['tasarim_genligi_eta_R'] == 0.05
        assert p['bafl_onerisi']['degerlendirme']['damping_ratio'] == \
            b['degerlendirme']['damping_ratio']

    def test_panel_genlik_satiri(self):
        clk = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        govde = _js_islevi(clk, 'baflHtml')
        assert "'panel.calkanti.bGenlik'" in govde
        assert 'b.tasarim_genligi_eta_R' in govde
        for dil in ('en', 'tr'):
            assert 'η/R' in _sozluk_degeri('panel.calkanti.bGenlik', dil)

    def test_perde_sivi_disinda_sonum_yok(self, client):
        """Mühendis adımı (M7-CALK-13): R 0,236698, h 0,001, w/R 0,75,
        d/R 1,41667. ÖNCE: 'Halka perde sönüm oranı 0,0008 (bant
        0,0004-0,0017)', kod ekranda yok."""
        from hrma.analysis import slosh_analysis as sa
        r = client.post('/api/slosh-analysis', json={
            'radius': 0.236698, 'fill_height': 0.001, 'g_eff': 9.80665,
            'fluid_density': 1141.16, 'baffle_width_ratio': 0.75,
            'baffle_depth_ratio': 1.41667})
        assert r.status_code == 200, r.get_json()
        b = r.get_json()['slosh']['baffle']
        assert b['damping_ratio'] is None
        assert b['damping_ratio_low'] is None and b['damping_ratio_high'] is None
        assert sa.BAFL_SIVI_DISINDA_KODU in b['validity_codes']
        assert 'BAFL_GECERLILIK_DISI' in b['validity_codes']
        assert b['amplitude_ratio'] == 0.05
        # dolu tankta aynı perde yayımlanır
        r = client.post('/api/slosh-analysis', json={
            'radius': 0.236698, 'fill_height': 1.0, 'g_eff': 9.80665,
            'fluid_density': 1141.16, 'baffle_width_ratio': 0.75,
            'baffle_depth_ratio': 1.41667})
        b = r.get_json()['slosh']['baffle']
        assert b['damping_ratio'] == pytest.approx(0.0008493160267395581, rel=1e-12)
        assert b['validity_codes'] == []

    def test_tek_tank_formu_kodlari_ve_genligi_yazar(self):
        feed = (JS / 'panels' / 'feed_panel.js').read_text(encoding='utf-8')
        for parca in ("BAFL_SIVI_DISINDA", "BAFL_GECERLILIK_DISI",
                      "'panel.feed.baffleAmplitude'", "'panel.feed.baffleNotReported'",
                      'baffle.validity_codes'):
            assert parca in feed, parca
        for anahtar in ('panel.feed.baffleAmplitude', 'panel.feed.baffleNotReported',
                        'panel.feed.baffleAmplitudeTip',
                        'panel.calkanti.kod.BAFL_SIVI_DISINDA'):
            assert _sozluk_degeri(anahtar, 'tr') != _sozluk_degeri(anahtar, 'en')


# ===========================================================================
# M7-CALK-5 — frekans haritasının hücre durumu ve Bond kodu ekranda
# ===========================================================================
class TestHaritaDurumu:

    def test_dusuk_g_haritasi_beyanli_ve_kod_ekranda(self, client, sivi, tmp_path):
        """Mühendis adımı: g_eff alt 0,001 m/s² (tek değer). ÖNCE: sunucu her
        hücreye BEYANLI + BOND_HESAPLANAMADI yazıyor, panel çizmiyordu."""
        r = client.post('/api/slosh-analysis', json={'tank_modeli': {
            'motor_type': 'liquid', 'motor_sonucu': sivi, 'g_eff_m_s2': 0.001}})
        assert r.status_code == 200, r.get_json()
        t = next(x for x in r.get_json()['tank_modeli']['tanklar']
                 if x['tank_id'] == 'oksitleyici')
        h = t['frekans_haritasi']
        assert all(d == 'BEYANLI' for satir in h['durum'] for d in satir)
        assert all('BOND_HESAPLANAMADI' in k for satir in h['sebep'] for k in satir)
        cikti = _node(
            "global.window = {location: {pathname: '/liquid'}};\n"
            "global.document = {};\n"
            "require(%r);\n"
            "const C = window.HRMACalkanti;\n"
            "const h = %s;\n"
            "process.stdout.write(JSON.stringify([C._haritaDurumHtml(h),"
            " C._haritaDurumHtml({durum: [['GECERLI']], sebep: [[[]]]})]));\n"
            % (str(JS / 'calkanti_panel.js'), json.dumps(h)), tmp_path)
        # node'da sözlük yok: kod metni yerine kodun kendisi (tarayıcıda EN/TR)
        assert 'BOND_HESAPLANAMADI' in cikti[0] and 'of 29 cells' in cikti[0], cikti[0][:300]
        assert cikti[1] == ''
        for anahtar in ('panel.calkanti.haritaDurum', 'panel.calkanti.yukBond'):
            for dil in ('en', 'tr'):
                assert _sozluk_degeri(anahtar, dil)
        clk = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        assert "'panel.calkanti.yukBond'" in _js_islevi(clk, 'yukHtml')


# ===========================================================================
# M7-UCUS-13 — aktarım zaman tablosunun frekansı sabit g_eff'te, adıyla
# ===========================================================================
class TestAktarimFrekansTanimi:

    def test_sutun_adi_ve_tanim_sabit_geffi_soyler(self, client, sivi):
        """ÖNCE: zaman CSV'sinde 'omega1_rad_s' / 'f1_hz' uçuş zamanına göre
        dolulukla yan yana, 1 g'de; tanım yalnız meta satırında g_eff."""
        import csv
        from hrma.analysis import calkanti_arayuz as ca
        adlar = [c for c, _ in ca.ZAMAN_SUTUNLARI]
        assert 'omega1_rad_s' not in adlar and 'f1_hz' not in adlar
        assert {'omega1_sabit_geff_rad_s', 'f1_sabit_geff_hz',
                'zeta_ceper_sabit_geff', 'kappa1_1m'} <= set(adlar)
        r = client.post('/api/slosh-analysis/export', json={
            'tank_modeli': {'motor_type': 'liquid', 'motor_sonucu': sivi},
            'disa_aktarim': {'tank_id': 'oksitleyici', 'bicim': 'csv_zaman'}})
        assert r.status_code == 200
        satirlar = r.data.decode('utf-8').split('\n')
        meta = json.loads(satirlar[1][len(ca.CSV_META_ONEKI):])
        ft = meta['frekans_tanimi']
        assert ft['kod'] == 'FREKANS_SABIT_GEFF'
        assert ft['g_eff_m_s2'] == meta['g_eff_m_s2'] == 9.80665
        assert 'a_eff' in ft['tanim_en'] and 'a_eff' in ft['tanim_tr']
        bas = next(csv.reader([satirlar[2]]))
        assert 'f1_sabit_geff_hz' in bas
        r = client.post('/api/slosh-analysis/export', json={
            'tank_modeli': {'motor_type': 'liquid', 'motor_sonucu': sivi},
            'disa_aktarim': {'tank_id': 'oksitleyici', 'bicim': 'json'}})
        p = json.loads(r.data.decode('utf-8'))
        assert p['zaman_ekseni']['frekans_tanimi']['kod'] == 'FREKANS_SABIT_GEFF'
        assert p['sema_surumu'] == ca.AKTARIM_SURUMU == 'v307-k5-2'

    def test_panel_tanimi_yazar(self):
        clk = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        govde = _js_islevi(clk, 'indirHtml')
        assert "'panel.calkanti.aktarimFrekans'" in govde
        assert 'f1_sabit_geff_hz' in _js_islevi(clk, 'zamanGrafigi')
        for dil in ('en', 'tr'):
            m = _sozluk_degeri('panel.calkanti.aktarimFrekans', dil)
            assert '{g}' in m and 'a_eff' in m and '_sabit_geff' in m


# ===========================================================================
# M7-UCUS-4 (yayım kuralı KARAR bekliyor) — görünürlük: genliğin tohuma bağlı
# olduğu ve sınıra yetecek başlangıç genliği yanıtın sayılarından yazılır
# ===========================================================================
class TestTohumBagimliligi:

    def test_pencere_varken_sinir_icinde_cumlesi_tohumu_soyler(self, tmp_path):
        """ÖLÇÜLDÜ (sıvı örnek, rüzgâr 0): pencere 6,805–30,000 s, büyüme
        üssü 4,1669 (e^x = 64,5), gerçekleşen η/R 2,44e-12; ÖNCE ekranda
        yalnız 'doğrusal sınırın içinde kaldı'."""
        for dil in ('en', 'tr'):
            m = _sozluk_degeri('panel.calkanti.hk.dogrusalTohum', dil)
            assert '{x}' in m and '{G}' in m and '{tohum}' in m
        cikti = _node(
            "global.window = {location: {pathname: '/liquid'}, AnalysisDock: {ui: {"
            " badge: (t) => t, sectionTitle: (t) => t, kvTable: () => '', listBlock: () => '',"
            " TD: '', TBL: '', num: (x, d) => (d === undefined ? String(x) : x.toFixed(d))}}};\n"
            "global.document = {};\n"
            "require(%r);\n"
            "const C = window.HRMACalkanti;\n"
            "const h = {genel_hukum: 'CALKANTI_KAYNAKLI_KARARSIZLIK', gerekce_kodu: 'X',"
            " pencereler: [{t1: 6.805, t2: 30.0, buyume_ussu: 4.166886591869002}],"
            " rijit_pencereler: [], dogrusal_sinir: {asildi: false, max_eta_R: 2.44e-12, sinir: 0.2}};\n"
            "const k = {genel_hukum: 'KARARLI', gerekce_kodu: 'X', pencereler: [],"
            " rijit_pencereler: [], dogrusal_sinir: {asildi: false, max_eta_R: 0.04, sinir: 0.2}};\n"
            "process.stdout.write(JSON.stringify([C._hukumHtml(h), C._hukumHtml(k)]));\n"
            % str(JS / 'calkanti_panel.js'), tmp_path)
        assert 'initial disturbance' in cikti[0], cikti[0][-600:]
        assert '64.5' in cikti[0] and '0.0031' in cikti[0]
        assert 'initial disturbance' not in cikti[1]


# ===========================================================================
# ONARIM-UÇUŞ DEVİR (M7-UCUS-16 ikinci yarısı) — rijit referans koşunun
# yayımlanmayan apojesi ve rijit pencere başlığı. Sözleşme: çözücü
# (ONARIM-UÇUŞ, six_dof_trajectory.solve) negatif marjda apojeyi None yapar ve
# nedeni ``apogee_withheld_because``'a yazar; alan yoksa bugünkü davranış.
# ===========================================================================
_UI_STUB = ("global.window = {location: {pathname: '/hybrid'}, AnalysisDock: {ui: {"
            " badge: (t) => t, sectionTitle: (t) => '[' + t + ']', kvTable: () => '',"
            " listBlock: () => '', TD: '', TBL: '',"
            " num: (x, d) => (d === undefined ? String(x) : x.toFixed(d))}}};\n"
            "global.document = {};\n")


class TestRijitReferansDevir:

    def test_referans_apoje_metni_sozlesmesi(self, tmp_path):
        cikti = _node(
            _UI_STUB + "require(%r);\n"
            "const C = window.HRMACalkanti;\n"
            "const neg = {static_margin_full: -3.20, static_margin_empty: -3.71};\n"
            "const poz = {static_margin_full: 2.01, static_margin_empty: 1.50};\n"
            "const r = [];\n"
            # alan yok: bugünkü davranış
            "C._sd.veri = {summary: neg};\n"
            "r.push(C._referansMetni({apogee: null, max_alpha_deg: 89.719}));\n"
            # alan var + negatif marj: adıyla
            "r.push(C._referansMetni({apogee: null, max_alpha_deg: 89.719,"
            " apogee_withheld_because: 'NEGATIVE STATIC MARGIN: ...'}));\n"
            # alan var, marj pozitif (ör. takla): yalnız raporlanmadı
            "C._sd.veri = {summary: poz};\n"
            "r.push(C._referansMetni({apogee: null, apogee_withheld_because: 'TUMBLE: ...'}));\n"
            # apoje var: sayı
            "r.push(C._referansMetni({apogee: 5153.9, max_alpha_deg: 3.3}));\n"
            "process.stdout.write(JSON.stringify(r));\n"
            % str(JS / 'calkanti_panel.js'), tmp_path)
        assert 'apogee not reached' in cikti[0]
        assert 'apogee not reported (negative static margin)' in cikti[1]
        assert 'not reached' not in cikti[1]
        assert 'apogee not reported (the reason' in cikti[2]
        assert 'apogee 5153.9 m' in cikti[3]
        for anahtar, parca in (('panel.calkanti.sd.referansApojeNegatifMarj', 'statik marj negatif'),
                               ('panel.calkanti.sd.referansApojeRaporlanmadi', 'raporlanmadı'),
                               ('panel.calkanti.hk.rijitBaslikHukumYok', 'yayımlanmadı')):
            assert parca in _sozluk_degeri(anahtar, 'tr')
            assert _sozluk_degeri(anahtar, 'en')

    def test_rijit_pencere_basligi_hukum_yoksa_bosa_isaret_etmez(self, tmp_path):
        cikti = _node(
            _UI_STUB + "require(%r);\n"
            "const C = window.HRMACalkanti;\n"
            "const h = {genel_hukum: 'RIJIT_GOVDE_KARARSIZ', gerekce_kodu: 'X', pencereler: [],"
            " rijit_pencereler: [{t1: 1.0, t2: 2.0, max_re: 0.5}], dogrusal_sinir: null};\n"
            "C._sd.veri = {summary: {stable: null}};\n"
            "const a = C._hukumHtml(h);\n"
            "C._sd.veri = {summary: {stable: false}};\n"
            "const b = C._hukumHtml(h);\n"
            "process.stdout.write(JSON.stringify([a, b]));\n"
            % str(JS / 'calkanti_panel.js'), tmp_path)
        assert 'is not reported' in cikti[0] and 'main verdict is the 6-DOF' not in cikti[0]
        assert 'main verdict is the 6-DOF flight verdict' in cikti[1]

    def test_sunucu_alani_referans_koşuya_tasir(self):
        """Çözücünün alanı (varsa) ``calkanti.rijit_karsilastirma``ya geçer;
        bu dalda çözücü alanı üretmiyorsa None (birleştirmede UÇUŞ'unkiyle)."""
        import inspect
        from hrma import app as app_mod
        kaynak = inspect.getsource(app_mod._calkanti_6dof_ciktisi)
        assert "'apogee_withheld_because': rc.get('apogee_withheld_because')" in kaynak
        kaynak = inspect.getsource(k2.cozum_ciktilari)
        assert "'apogee_withheld_because': rout.get('apogee_withheld_because')" in kaynak
