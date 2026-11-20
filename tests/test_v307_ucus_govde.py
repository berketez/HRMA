"""V307/UÇUŞ-GÖVDE — türetilmiş gövde motorun tanklarını taşır; çalkantı
örnek motorlarda bağlanır; hüküm ve yayım kuralları.

Ne kilitlenir (fizik ve sözleşme, bugünkü çıktı değil):
  * gövde ⟷ tank sığma değişmezi: türetilmiş gövdenin dış çapı her tankın
    DIŞ çapından (iç çap + 2 × motorun yayımladığı cidar) küçük olamaz; tank
    aralıkları (iç boy + baş kalınlıkları) burun ile motor arasındadır; sayfa
    alanlarının yuvarlaması bu değişmezi bozmaz;
  * tek tanım: gövde boyu ve K4'ün ardışık dizilimi AYNI işlevden
    (``flight_vehicle.tank_stack``); motor sayfası 6-DOF paneli, uçuş köprüsü
    ve Fırlatma Sahası aynı ``airframe_resolved``i okur; burun tek sayıdır;
  * örnek sıvı ve hibrit motorda, hiçbir yer girdisi olmadan, tanklar bağlanır;
    katıda ``TANK_YOK``; kullanıcının dar gövdesinde adlı ret sürer;
  * kanat kuralıyla uçan araç çalkantıyı taşır (bağlaşık uçuş);
  * K4 raporu tabloyu bağlanmayan tankta da yayımlar; motor görünümü ikinci
    kez kurmaz;
  * kalem 5: apojeye varmama yalnız KARARLI'yı engeller; pencereler doğrusal
    sınırın ilk aşımına göre işaretlenir;
  * kalem 6: sınır aşıldıysa bağlaşık koşunun tüm-uçuş sayıları yayımlanmaz,
    rijit koşu referans etiketiyle durur; koşulsuz apoje alanı rijit sayıyla
    doldurulmaz.
"""

import contextlib
import io
import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

from hrma.analysis import calkanti_arayuz as ca
from hrma.analysis import flight_vehicle as fv
from hrma.analysis import six_dof_slosh as k2
from hrma.analysis import slosh_analysis as sa
from hrma.analysis import slosh_motor_baglanti as smb
from tests.test_example_projects import NAMES

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
UC_6DOF = '/api/six-dof-analysis'


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
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


@pytest.fixture(scope='module')
def kati():
    return _coz('solid')


def _tank(key, d, l, cidar=None, bas=None):
    return {'key': key, 'diameter_m': d, 'length_m': l,
            'volume_m3': math.pi / 4.0 * d * d * l,
            'wall_thickness_m': cidar, 'end_closure_thickness_m': bas}


def _arac(tanklar, od=0.24, boy=0.60, mt='liquid'):
    return {'motor_type': mt, 'engine_od_m': od, 'engine_length_m': boy,
            'propellant_tanks': tanklar}


def _govde_duzeni(arac, sira=None):
    """Türetilmiş gövdeyle K4 araç düzeni (6-DOF ucunun eklediği ölçüler)."""
    g = arac['airframe_resolved']
    return {'ardisik': ({} if sira is None else {'sira': sira}),
            'govde_boyu_m': g['nose_length_m'] + g['length_behind_nose_m'],
            'burun_boyu_m': g['nose_length_m'],
            'govde_capi_m': g['body_diameter_m'],
            'motor_boyu_m': arac['engine_length_m']}


def _istek(arac, mt, sonuc, **ek):
    """Motor sayfası 6-DOF panelinin türetilmiş gövdeyle kurduğu istek."""
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


# ===========================================================================
# 1. Gövde kuralı (tek tanım; birim testleri)
# ===========================================================================
class TestGovdeKurali:

    def test_dis_cap_tankin_dis_capini_tasir(self):
        arac = _arac([_tank('oxidizer_tank', 0.47339542625469216, 1.18,
                            cidar=0.003, bas=0.003)])
        g = fv.derive_airframe(arac)
        dis = 0.47339542625469216 + 2 * 0.003
        assert g['body_diameter_m'] >= dis
        # alan çözünürlüğüne YUKARI: en çok bir adım fazla
        assert g['body_diameter_m'] - dis < fv.DERIVED_AIRFRAME_DIAMETER_STEP_M
        assert g['body_diameter_m'] == 0.48

    def test_motor_zarfi_tanktan_genisse_zarf(self):
        arac = _arac([_tank('oxidizer_tank', 0.20, 0.5, 0.002, 0.002)], od=0.3004)
        assert fv.derive_airframe(arac)['body_diameter_m'] == 0.301

    def test_boy_ic_boy_arti_baslar_ve_yukari_yuvarlama(self):
        tanklar = [_tank('oxidizer_tank', 0.4, 1.1834885656367304, 0.003, 0.003),
                   _tank('fuel_tank', 0.4, 1.0705322319433663, 0.003, 0.003)]
        g = fv.derive_airframe(_arac(tanklar, boy=0.598257149790541))
        ham = 0.598257149790541 + sum(t['length_m'] + 2 * 0.003 for t in tanklar)
        assert g['length_behind_nose_m'] >= ham
        assert g['length_behind_nose_m'] - ham < fv.DERIVED_AIRFRAME_LENGTH_STEP_M
        assert g['length_behind_nose_m'] == 2.87

    def test_tank_araliklari_burun_ile_motor_arasinda_ve_cakismaz(self):
        tanklar = [_tank('oxidizer_tank', 0.4, 1.18, 0.003, 0.004),
                   _tank('fuel_tank', 0.4, 1.07, 0.003, 0.002)]
        arac = _arac(tanklar, boy=0.6)
        g = fv.derive_airframe(arac)
        ist = g['tank_stations']
        assert [i['key'] for i in ist] == g['tank_order'] == [
            'oxidizer_tank', 'fuel_tank']
        # ilk tankın dış tepesi (iç tepe − baş) burun tabanında ya da arkasında
        assert ist[0]['top_behind_nose_m'] - 0.004 >= -1e-12
        # son tankın dış tabanı motorun ön yüzünde
        assert ist[-1]['base_behind_nose_m'] + 0.002 == pytest.approx(
            g['length_behind_nose_m'] - 0.6, abs=1e-12)
        # komşu başlar temas hâlinde: taban + baş + baş = sonraki tepe
        assert ist[0]['base_behind_nose_m'] + 0.004 + 0.002 == pytest.approx(
            ist[1]['top_behind_nose_m'], abs=1e-12)
        for i, t in zip(ist, tanklar):
            assert i['base_behind_nose_m'] - i['top_behind_nose_m'] == \
                pytest.approx(t['length_m'], abs=1e-12)

    def test_yayimlanmayan_kabuk_adiyla_ve_alt_sinir(self):
        arac = _arac([_tank('oxidizer_tank', 0.4001, 1.0)])     # cidar/baş yok
        g = fv.derive_airframe(arac)
        assert g['tank_shell_not_published'] == ['oxidizer_tank']
        assert g['body_diameter_m'] == 0.401       # iç çap, yukarı yuvarlı
        assert 'tank_shell_not_published' in fv.AIRFRAME_DERIVATION_BASIS

    def test_tanksiz_arac_yuvarlanmaz(self):
        # katı / örnek araç: 3.0.6 ile bit-aynı (yuvarlama yalnız tanklıda)
        arac = _arac([], od=0.09099999999999998, boy=0.5620875978854171,
                     mt='solid')
        g = fv.derive_airframe(arac)
        assert g['body_diameter_m'] == 0.09099999999999998
        assert g['length_behind_nose_m'] == 0.5620875978854171
        assert g['tank_order'] == [] and g['tank_stations'] is None

    def test_tank_geometrisi_yoksa_boy_uydurulmaz(self):
        g = fv.derive_airframe(_arac(None))
        assert g['length_behind_nose_m'] is None and g['tank_order'] is None

    def test_sayfa_alani_yuvarlamasi_govdeyi_tanktan_dar_birakmaz(self):
        # Fırlatma Sahası alanı çapı 3, boyu 2 ondalıkla yazar (en yakına).
        tanklar = [_tank('oxidizer_tank', 0.47339542625469216,
                         1.1834885656367304, 0.003, 0.003),
                   _tank('fuel_tank', 0.42821289277734653,
                         1.0705322319433663, 0.003, 0.003)]
        g = fv.derive_airframe(_arac(tanklar, od=0.24144577209724824,
                                     boy=0.598257149790541))
        cap_alan = float('%.3f' % g['body_diameter_m'])
        boy_alan = float('%.2f' % (g['nose_length_m'] + g['length_behind_nose_m']))
        assert cap_alan == g['body_diameter_m']
        assert boy_alan == pytest.approx(
            g['nose_length_m'] + g['length_behind_nose_m'], abs=1e-12)
        assert all(cap_alan >= fv.tank_outer_diameter_m(t) for t in tanklar)

    def test_burun_firlatma_sahasinin_sabit_burnuyla_ayni_sayi(self):
        html = (KOK / 'hrma/templates/launch_site.html').read_text(encoding='utf-8')
        blok = re.search(r'var LS_FIXED_AIRFRAME = \{(.*?)\};', html, re.S).group(1)
        burun = float(re.search(r'nose_length:\s*([0-9.]+)', blok).group(1))
        tip = re.search(r"nose_type:\s*'(\w+)'", blok).group(1)
        assert burun == fv.DERIVED_AIRFRAME_NOSE_LENGTH_M
        assert tip == fv.DERIVED_AIRFRAME_NOSE_TYPE
        g = fv.derive_airframe(_arac([]))
        assert g['nose_length_m'] == burun and g['nose_type'] == tip

    def test_tank_stack_bilinmeyen_boyda_none(self):
        assert fv.tank_stack([{'key': 'a', 'length_m': None}], 0.5) is None
        assert fv.tank_stack([], None) is None


# ===========================================================================
# 2. Örnek motorlarda bağlanma (kullanıcı hiçbir yer girmeden)
# ===========================================================================
@pytest.mark.slow
class TestOrneklerdeBaglanma:

    @pytest.mark.parametrize('mt', ['liquid', 'hybrid'])
    def test_turetilmis_govde_tanklari_tasir_ve_baglanir(self, mt, sivi, hibrit):
        sonuc = {'liquid': sivi, 'hybrid': hibrit}[mt]
        arac = fv.normalize(mt, sonuc)
        g = arac['airframe_resolved']
        assert g['source'] == 'derived' and g['tank_shell_not_published'] == []
        b = smb.slosh_tanklari(mt, sonuc, arac_duzeni=_govde_duzeni(arac))
        assert b['durum'] == smb.DURUM_BAGLANDI and b['sebep'] == []
        L = g['nose_length_m'] + g['length_behind_nose_m']
        ucus = {t['key']: t for t in arac['propellant_tanks']}
        anahtar = dict((tid, k) for k, tid in smb.SIVI_TANKLARI)
        onceki_taban = None
        for t in b['tanklar']:                    # burundan kıça (liste sırası)
            kayit = ucus[anahtar.get(t['tank_id'], 'oxidizer_tank')]
            geo = t['geometri']
            # çap: tankın DIŞ çapı gövde dış çapını aşmaz
            assert 2 * geo['R_ref_m'] + 2 * kayit['wall_thickness_m'] \
                <= g['body_diameter_m']
            tepe = t['x_tank_taban_m'] - geo['H_ic_m']
            bas = kayit['end_closure_thickness_m']
            assert tepe - bas >= g['nose_length_m'] - 1e-12
            assert t['x_tank_taban_m'] + bas <= L - arac['engine_length_m'] + 1e-12
            if onceki_taban is not None:
                assert tepe >= onceki_taban
            onceki_taban = t['x_tank_taban_m']
            assert 'TANK_ISTASYONU_ARDISIK_DIZILIM' in t['beyan']

    def test_tek_tanim_govde_istasyonu_k4_istasyonuyla_ayni(self, sivi):
        arac = fv.normalize('liquid', sivi)
        g = arac['airframe_resolved']
        b = smb.slosh_tanklari('liquid', sivi, arac_duzeni=_govde_duzeni(arac))
        k4 = [t['x_tank_taban_m'] for t in b['tanklar']]
        govde = [g['nose_length_m'] + i['base_behind_nose_m']
                 for i in g['tank_stations']]
        assert k4 == pytest.approx(govde, abs=1e-12)
        # sıra verilmezse motorun tank listesi sırası: oksitleyici önde
        assert [t['tank_id'] for t in b['tanklar']] == ['oksitleyici', 'yakit']
        acik = smb.slosh_tanklari('liquid', sivi, arac_duzeni=_govde_duzeni(
            arac, sira=['oksitleyici', 'yakit']))
        assert [t['x_tank_taban_m'] for t in acik['tanklar']] == k4

    def test_kati_tank_yok(self, kati):
        arac = fv.normalize('solid', kati)
        assert arac['airframe_resolved']['tank_order'] == []
        b = smb.slosh_tanklari('solid', kati)
        assert b['durum'] == smb.DURUM_UYGULANMAZ and b['sebep'] == ['TANK_YOK']

    def test_kullanicinin_dar_govdesinde_adli_ret_surer(self, sivi):
        # 3.0.6 panel gövdesi: Ø0,242 × 2,0 m, burun 0,40 m
        b = smb.slosh_tanklari('liquid', sivi, arac_duzeni={
            'ardisik': {}, 'govde_boyu_m': 2.0, 'burun_boyu_m': 0.4,
            'govde_capi_m': 0.242})
        assert b['durum'] == smb.DURUM_BAGLANMADI
        assert 'TANK_GOVDEDEN_GENIS' in b['sebep']
        assert {'TANK_ARAC_DISI', 'TANK_BURUN_ICINDE'} & set(b['sebep'])

    def test_ic_cap_ile_dis_cap_arasindaki_govde_reddedilir(self, sivi):
        arac = fv.normalize('liquid', sivi)
        d = _govde_duzeni(arac)
        t0 = arac['propellant_tanks'][0]
        # iç çaptan geniş, dış çaptan dar gövde: tank kabuğu sığmaz
        d['govde_capi_m'] = t0['diameter_m'] + t0['wall_thickness_m']
        b = smb.slosh_tanklari('liquid', sivi, arac_duzeni=d)
        ox = next(t for t in b['tanklar'] if t['tank_id'] == 'oksitleyici')
        assert ox['sebep'] == ['TANK_GOVDEDEN_GENIS']

    def test_ucus_koprusu_ayni_govdeyi_yayimlar(self, client, sivi):
        r = client.post('/api/flight-vehicle',
                        json={'motor_type': 'liquid', 'results': sivi})
        assert r.status_code == 200, r.get_json()
        g_uc = r.get_json()['vehicle']['airframe_resolved']
        g = fv.normalize('liquid', sivi)['airframe_resolved']
        assert g_uc == json.loads(json.dumps(g))


# ===========================================================================
# 3. Motor sayfası paneli aynı gövdeyi kurar (kaynak + node)
# ===========================================================================
class TestPanelAyniGovde:

    def test_panel_govdeyi_airframe_resolveddan_okur(self):
        panel = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
        tg = _js_islevi(panel, 'tankliGovde')
        for alan in ('airframe_resolved', 'body_diameter_m',
                     'length_behind_nose_m', 'nose_length_m', 'tank_order'):
            assert alan in tg, alan
        kur = _js_islevi(panel, 'govdeyiMotordanTohumla')
        assert 'tankliGovde(arac)' in kur and 'tankliGovdeyiKur(tg)' in kur
        # sabit gövde sayısı yok: çap/boy/burun yalnız araçtan
        assert not re.search(r'\b0\.4[0-9]*\b|\b3\.[0-9]+\b', tg)

    def test_panel_govdesi_firlatma_sahasi_alanlariyla_ayni_sayi(self):
        if shutil.which('node') is None:
            pytest.skip('node yok')
        panel = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
        arac = _arac([_tank('oxidizer_tank', 0.47339542625469216,
                            1.1834885656367304, 0.003, 0.003),
                      _tank('fuel_tank', 0.42821289277734653,
                            1.0705322319433663, 0.003, 0.003)],
                     od=0.24144577209724824, boy=0.598257149790541)
        arac['airframe_resolved'] = fv.derive_airframe(arac)
        betik = (_js_islevi(panel, 'tankliGovde')
                 + '\nconst a = ' + json.dumps(arac) + ';'
                 + '\nconst t = tankliGovde(a);'
                 + '\nconsole.log(JSON.stringify([t.d.toFixed(3), t.boy.toFixed(2),'
                   ' t.burun.toFixed(2), t.burunTipi,'
                   ' tankliGovde({airframe_resolved: {source: "derived", tank_order: []}}),'
                   ' tankliGovde({airframe_resolved: Object.assign({}, a.airframe_resolved,'
                   ' {length_behind_nose_m: null})})]));')
        # Betik stdin'den (test_node_cagri_sozlesmesi: argv tavanı).
        cikti = subprocess.run([shutil.which('node')], input=betik,
                               capture_output=True, text=True, timeout=30)
        assert cikti.returncode == 0, cikti.stderr
        d, boy, burun, tip, tanksiz, eksik = json.loads(cikti.stdout)
        g = arac['airframe_resolved']
        # Fırlatma Sahası: çap toFixed(3); boy = sabit burun + burun arkası, toFixed(2)
        assert d == '%.3f' % g['body_diameter_m'] == '0.480'
        assert boy == '%.2f' % (fv.DERIVED_AIRFRAME_NOSE_LENGTH_M
                                + g['length_behind_nose_m']) == '3.37'
        assert burun == '0.50' and tip == 'ogive'
        # ölçüsüz kayıtta ve ölçüsü eksik gövdede kural devreye girmez (V307/
        # AĞIRLIK-MERKEZİ-2: ölçülü tanksız katı gövde artık kurulur —
        # tests/test_v307_agirlik_merkezi_2.py)
        assert tanksiz is None and eksik is None

    def test_kanat_kurali_bos_alani_gondermez(self):
        panel = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
        assert "payload.fin_geometry_rule = 'static_margin'" in panel
        alanlar = _js_islevi(panel, 'kanatKuraliAlanlari')
        for uc in ('fin_root_chord', 'fin_tip_chord', 'fin_span', 'fin_sweep',
                   'fin_position'):
            assert uc in alanlar
        yaz = _js_islevi(panel, 'kanatAlanlariniKuraldanYaz')
        # ölçüler yanıttan; kuraldan gelmeyen alan yazılmaz
        assert 'blok.fields' in yaz and "indexOf('rule_')" in yaz
        assert 'finRule' in yaz

    def test_varsayilan_sira_motorun_tank_sirasi(self):
        clk = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        form = _js_islevi(clk, 'sixdofForm')
        assert 'secenekler(siralar, siralar[0][0])' in form
        sivi_ilk = form.index("['oksitleyici,yakit'")
        assert sivi_ilk < form.index("['yakit,oksitleyici'") < form.index(
            "['', 'Not entered")

    def test_ipuclari_kodun_sabitleriyle_ayni(self):
        tr = _sozluk_degeri('sixdof.help.noseL', 'tr')
        en = _sozluk_degeri('sixdof.help.noseL', 'en')
        assert ('%.2f m' % fv.DERIVED_AIRFRAME_NOSE_LENGTH_M).replace('.', ',') in tr
        assert '%.2f m' % fv.DERIVED_AIRFRAME_NOSE_LENGTH_M in en
        for dil in ('tr', 'en'):
            assert '%g mm' % (fv.DERIVED_AIRFRAME_DIAMETER_STEP_M * 1000) in \
                _sozluk_degeri('sixdof.help.bodyD', dil)
            assert '%g mm' % (fv.DERIVED_AIRFRAME_LENGTH_STEP_M * 1000) in \
                _sozluk_degeri('sixdof.help.bodyL', dil)


# ===========================================================================
# 4. 6-DOF ucu: kanat kuralı + çalkantı, yayım kuralı (kalem 6)
# ===========================================================================
@pytest.mark.slow
class TestUcBaglasik:

    def test_hibrit_kanat_kuraliyla_baglasik_ucar_pencere_varken_yayimlanmaz(
            self, client, hibrit):
        # 3.0.7 (M7-UCUS-4 a, Berke 19 Kas "çözülsün"; ana model 20 Kas):
        # hibrit örnekte doğrusal sınır AŞILMIYOR ama yanma içinde çalkantı
        # kaynaklı kararsızlık penceresi var (3,5–10,3 s, büyüme ~6,5 kat).
        # Gerçekleşen genliğin sınırın içinde kalması başlangıç bozucusunun
        # büyüklüğüne bağlıdır; bağlaşık tüm-uçuş sayıları yayımlanmaz, rijit
        # koşu "çalkantısız referans koşu" etiketiyle durur. Bu test önceden
        # aynı koşuda yayim GECERLI ve bağlaşık apojeyi kilitliyordu — bugünkü
        # çıktıyı, doğru kuralı değil (ölçüm: onarim-calk/RAPOR.md §4).
        arac = fv.normalize('hybrid', hibrit)
        kod, y = _gonder(client, _istek(arac, 'hybrid', hibrit))
        assert kod == 200, y
        c = y['calkanti']
        assert c['durum'] == 'BAGLANDI'
        assert [t['tank_id'] for t in c['tanklar']] == ['n2o']
        # Uçuş bağlaşık koşuyla çözüldü (kayıt biçimi uygulamaya bağlı; ikisi
        # de kabul). Kilitlenen şey bağlaşık uçuşun kendisidir.
        boy = y['fin_geometry']['sizing']
        assert boy.get('coupled_flight') is True or (
            (boy.get('final_flight') or {}).get('model') == 'coupled_slosh'), boy
        assert c['zaman'] is not None
        st = c['slosh_stability']
        assert st['dogrusal_sinir']['asildi'] is False
        assert st['genel_hukum'] == k2.HUKUM_CALKANTI_KARARSIZ
        calk_pencere = [p for p in st['pencereler'] if p['mod'] == 'calkanti']
        assert calk_pencere, st['pencereler']
        yayim = c['yayim']
        assert yayim['kosu_turu'] == 'BAGLASIK'
        assert yayim['neden_kodu'] == 'BAGLASIK_KOSU_KARARSIZ_PENCERE'
        assert yayim['gecerlilik'] == 'KARARSIZ_PENCERE_GENLIK_TOHUMA_BAGLI'
        assert yayim['t_ilk_asim_s'] is None
        # geçerlilik sınırı: ilk çalkantı penceresinin başı
        assert yayim['t_gecersiz_bas_s'] == min(p['t1'] for p in calk_pencere)
        assert yayim['t_gecersiz_bas_s'] > 0
        assert yayim['referans_kosu']['etiket_kodu'] == 'CALKANTISIZ_REFERANS_KOSU'
        s, rk = y['summary'], c['rijit_karsilastirma']
        for alan in ('apogee', 'apogee_time', 'max_alpha_deg', 'max_speed',
                     'max_mach', 'stable'):
            assert s[alan] is None, alan
            assert alan in yayim['yayimlanmayan_alanlar'], alan
        assert s['flight_verdict']['stability'] == 'not_evaluated'
        # rijit referans koşu kendi bloğunda, sayısıyla; özet onunla DOLMAZ
        assert rk['apogee'] is not None
        # geometri (statik marj) yayımlanmaya devam eder
        assert s['static_margin_full'] is not None
        assert st['ucus_sonu']['apojeye_vardi'] is True
        assert st['tarama']['aralik']['t_bas_s'] == 0.0
        assert all(p['sinir_asimi_konumu'] == k2.SINIR_KONUM_ASILMADI
                   and p['buyume_ussu_sinir_oncesi'] == p['buyume_ussu']
                   for p in st['pencereler'])

    def test_sivi_sinir_asilinca_baglasik_sayilar_yayimlanmaz(self, client, sivi):
        arac = fv.normalize('liquid', sivi)
        kod, y = _gonder(client, _istek(arac, 'liquid', sivi))
        assert kod == 200, y
        c = y['calkanti']
        assert c['durum'] == 'BAGLANDI'
        ds = c['slosh_stability']['dogrusal_sinir']
        if not ds['asildi']:
            pytest.skip('bu araçta doğrusal sınır aşılmadı (yayım testi '
                        'aşım ister)')
        s, yayim, rk = y['summary'], c['yayim'], c['rijit_karsilastirma']
        for alan in ('apogee', 'apogee_time', 'max_alpha_deg', 'max_speed',
                     'max_mach', 'lateral_drift_at_end', 'stable'):
            assert s[alan] is None, alan
            assert alan in yayim['yayimlanmayan_alanlar'], alan
        assert s['flight_verdict']['stability'] == 'not_evaluated'
        assert yayim['gecerlilik'] == k2.DOGRUSAL_GECERLILIK_DISI
        assert yayim['neden_kodu'] == 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI'
        assert yayim['t_ilk_asim_s'] == ds['t_ilk_asim_s'] > 0
        # 3.0.7 (M7-UCUS-4 a): iki nedenin ortak geçerlilik sınırı alanı
        assert yayim['t_gecersiz_bas_s'] == yayim['t_ilk_asim_s']
        assert yayim['referans_kosu'] == {
            'kosu_turu': 'RIJIT', 'etiket_kodu': 'CALKANTISIZ_REFERANS_KOSU',
            'alan': 'calkanti.rijit_karsilastirma'}
        # rijit koşu kendi bloğunda, sayılarıyla; özet onunla DOLDURULMAZ
        assert rk['apogee'] is not None and rk['max_alpha_deg'] is not None
        assert rk['max_speed'] is not None and rk['apogee_time'] is not None
        # geometri (statik marj) yayımlanmaya devam eder
        assert s['static_margin_full'] is not None
        # hüküm susmaz; pencere aşım konumuyla işaretli
        st = c['slosh_stability']
        assert st['genel_hukum'] == k2.HUKUM_CALKANTI_KARARSIZ
        assert all(p['sinir_asimi_konumu'] in k2.SINIR_KONUMLARI[1:]
                   for p in st['pencereler'])


# ===========================================================================
# 5. Hüküm kuralı (kalem 5) — birim testleri
# ===========================================================================
def _tarama(pencereler=(), rijit=(), kararli=10):
    sayi = {s: 0 for s in k2.TARAMA_SINIFLARI}
    sayi[k2.TARAMA_KARARLI] = kararli
    return {'pencereler': list(pencereler), 'rijit_pencereler': list(rijit),
            'kapsam': {'sinif_sayilari': sayi}}


def _pencere(konum=k2.SINIR_KONUM_ASILMADI, tutarli=True):
    return {'sayisal_tutarli': tutarli, 'sinir_asimi_konumu': konum}


class TestHukumKurali:
    OUT = {'converged': True}

    def test_apojeye_varmayan_ucusta_pencere_varsa_hukum_susmaz(self):
        for ucus in ('tumble', 'ground_impact_before_apogee',
                     'ground_impact_under_power', 'time_limit'):
            h = k2._tarama_hukmu(_tarama([_pencere()]), self.OUT, ucus)
            assert h == (k2.HUKUM_CALKANTI_KARARSIZ, k2.GEREKCE_PENCERE, [])

    def test_apojeye_varmayan_ucusta_kararli_denmez(self):
        h = k2._tarama_hukmu(_tarama(), self.OUT, 'tumble')
        assert h == (k2.HUKUM_YOK, 'UCUS_APOJEYE_VARMADI',
                     ['UCUS_APOJEYE_VARMADI'])
        assert k2._tarama_hukmu(_tarama(), self.OUT, 'apogee')[0] == \
            k2.HUKUM_KARARLI

    def test_apojeye_varmayan_ucusta_rijit_kararsizlik_soylenir(self):
        h = k2._tarama_hukmu(_tarama(rijit=[{'t1': 1, 't2': 2, 'max_re': 0.1}]),
                             self.OUT, 'tumble')
        assert h[:2] == (k2.HUKUM_RIJIT_KARARSIZ, k2.GEREKCE_RIJIT)

    def test_yalniz_asim_sonrasi_pencere_gerekcede_soylenir(self):
        sonra = _pencere(k2.SINIR_KONUM_SONRA)
        h = k2._tarama_hukmu(_tarama([sonra, sonra]), self.OUT, 'apogee')
        assert h == (k2.HUKUM_CALKANTI_KARARSIZ,
                     k2.GEREKCE_PENCERE_SINIR_SONRASI, [])
        karisik = k2._tarama_hukmu(
            _tarama([sonra, _pencere(k2.SINIR_KONUM_KAPSIYOR)]), self.OUT,
            'tumble')
        assert karisik[1] == k2.GEREKCE_PENCERE
        assert k2.GEREKCE_PENCERE_SINIR_SONRASI in k2.GEREKCE_KODLARI

    def test_yakinsamayan_cozum_ve_tutarsiz_pencere_hukumsuz(self):
        assert k2._tarama_hukmu(_tarama([_pencere()]), {'converged': False},
                                'apogee')[0] == k2.HUKUM_YOK
        assert k2._tarama_hukmu(_tarama([_pencere(tutarli=False)]), self.OUT,
                                'tumble')[:2] == (k2.HUKUM_YOK,
                                                  'SAYISAL_TUTARSIZLIK')

    def test_pencere_sinir_isaretleri(self):
        orn = [{'t': 0.1 * i, 'max_re': 0.5} for i in range(21)]   # 0 … 2 s

        def pencere(a, b):
            return {'t1': orn[a]['t'], 't2': orn[b]['t'],
                    't1_kenar': k2.KENAR_DEGERLENDIRME_SINIRI,
                    'buyume_ussu': 0.5 * (orn[b]['t'] - orn[a]['t']),
                    '_ornek_araligi': (a, b)}
        t = {'ornekler': orn, 'pencereler': [pencere(0, 5), pencere(8, 14),
                                             pencere(16, 20)]}
        k2._pencere_sinir_isaretleri(t, 1.05)
        once, kapsar, sonra = t['pencereler']
        assert once['sinir_asimi_konumu'] == k2.SINIR_KONUM_ONCE
        assert once['buyume_ussu_sinir_oncesi'] == once['buyume_ussu']
        assert kapsar['sinir_asimi_konumu'] == k2.SINIR_KONUM_KAPSIYOR
        assert kapsar['ornek_sayisi_sinir_oncesi'] == 3        # t = 0,8 0,9 1,0
        assert kapsar['buyume_ussu_sinir_oncesi'] == pytest.approx(0.5 * 0.2)
        assert kapsar['buyume_ussu_sinir_oncesi'] < kapsar['buyume_ussu']
        assert sonra['sinir_asimi_konumu'] == k2.SINIR_KONUM_SONRA
        assert sonra['buyume_ussu_sinir_oncesi'] is None
        assert sonra['ornek_sayisi_sinir_oncesi'] == 0
        assert all('_ornek_araligi' not in p for p in t['pencereler'])
        # aşım yoksa bütün pencere geçerli bölgededir
        t2 = {'ornekler': orn, 'pencereler': [pencere(0, 5)]}
        k2._pencere_sinir_isaretleri(t2, None)
        assert t2['pencereler'][0]['sinir_asimi_konumu'] == \
            k2.SINIR_KONUM_ASILMADI

    def test_uygulanmaz_ciktisi_yeni_alanlari_tasir(self):
        u = k2.uygulanmaz_ciktisi('TANK_YOK')
        assert u['ucus_sonu'] is None
        assert u['hukum_kapsami']['kod'] == k2.HUKUM_KAPSAMI_KODU


@pytest.mark.slow
class TestTaklaAtanKosu:

    def test_takla_atan_baglasik_kosuda_hukum_ve_ucus_sonu_ayri(self, client, sivi):
        # Kullanıcının girdiği küçük kanat (açıklık 0,30 m): araç takla atar.
        arac = fv.normalize('liquid', sivi)
        govde = _istek(arac, 'liquid', sivi, fin_root_chord=0.64,
                       fin_tip_chord=0.32, fin_sweep=0.256, fin_span=0.30)
        govde.pop('fin_geometry_rule')
        govde['calkanti']['arac_duzeni'] = {
            'ardisik': {'sira': ['oksitleyici', 'yakit']}}
        kod, y = _gonder(client, govde)
        assert kod == 200, y
        st = y['calkanti']['slosh_stability']
        us = st['ucus_sonu']
        if us['apojeye_vardi']:
            pytest.skip('bu araç apojeye vardı (takla örneği değil)')
        assert us['ucus'] == y['summary']['flight_verdict']['flight'] != 'apogee'
        assert us['t_son_s'] > 0
        # pencere bulunduysa hüküm verilir; uçuşun sonu ayrı alandadır
        if st['pencereler']:
            assert st['genel_hukum'] == k2.HUKUM_CALKANTI_KARARSIZ
            assert st['sebep'] == []
        else:
            assert st['genel_hukum'] in (k2.HUKUM_YOK, k2.HUKUM_RIJIT_KARARSIZ)
        assert st['genel_hukum'] != k2.HUKUM_KARARLI
        assert st['hukum_kapsami']['kod'] == k2.HUKUM_KAPSAMI_KODU


# ===========================================================================
# 6. K4 DEVİR: tablo ve beyan bağlanmayan tankta da; görünüm ikinci kez kurmaz
# ===========================================================================
@pytest.mark.slow
class TestK4Tablo:

    def test_baglanmayan_tank_tablo_ve_beyan_yayimlar(self, sivi):
        yersiz = smb.slosh_tanklari('liquid', sivi)             # yer yok
        arac = fv.normalize('liquid', sivi)
        bagli = smb.slosh_tanklari('liquid', sivi,
                                   arac_duzeni=_govde_duzeni(arac))
        assert yersiz['durum'] == smb.DURUM_BAGLANMADI
        for t, b in zip(yersiz['tanklar'], bagli['slosh_tanks']):
            assert t['sebep'] == ['TANK_ISTASYONU_VERILMEDI']
            assert t['tablo'] is not None
            assert t['tablo'].sozluk() == b['tablo'].sozluk()
            assert 'TUKETIM_SABIT_DEBI' in t['beyan']
            assert t['satir_durumlari'] is not None
        oz = smb.json_ozeti(yersiz)
        json.dumps(oz, allow_nan=False)             # tablo sözlüğe çevrildi
        assert oz['tanklar'][0]['tablo'] == yersiz['tanklar'][0]['tablo'].sozluk()

    def test_motor_gorunumu_tabloyu_ikinci_kez_kurmaz(self, sivi, monkeypatch):
        sayac = {'n': 0}
        asil = sa.esdeger_model_tablosu

        def say(*a, **k):
            sayac['n'] += 1
            return asil(*a, **k)
        monkeypatch.setattr(sa, 'esdeger_model_tablosu', say)
        gorunum, tablolar = ca.tank_modeli(
            {'motor_type': 'liquid', 'motor_sonucu': sivi})
        assert gorunum['durum'] == 'HESAPLANDI'
        assert sayac['n'] == len(gorunum['tanklar']) == 2
        assert not hasattr(ca, '_tablo_yeniden')
        for t in gorunum['tanklar']:
            assert t['beyan'] == ['YOGUNLUK_SABIT', 'TUKETIM_SABIT_DEBI']

    def test_6dof_yaniti_tabloyu_tasimaz(self, client, hibrit):
        arac = fv.normalize('hybrid', hibrit)
        govde = _istek(arac, 'hybrid', hibrit, body_diameter=0.15,
                       body_length=2.0, nose_length=0.4)      # dar gövde: ret
        govde.pop('fin_geometry_rule')
        govde.update(fin_root_chord=0.2, fin_tip_chord=0.1, fin_span=0.11,
                     fin_sweep=0.08)
        kod, y = _gonder(client, govde)
        assert kod == 200, y
        t = y['calkanti']['tanklar'][0]
        assert t['durum'] == 'BAGLANMADI' and 'TANK_GOVDEDEN_GENIS' in t['sebep']
        assert 'tablo' not in t and t['beyan'] == []
        assert 'yayim' not in y['calkanti']         # hüküm yok: yayım kaydı yok
        assert y['summary']['apogee'] is not None   # rijit uçuş, olduğu gibi


# ===========================================================================
# 7. Ekran metni bekçileri (kalem 5-6)
# ===========================================================================
class TestEkranMetni:

    def test_referans_etiketi_zorunlu_anlami_tasir(self):
        tr = _sozluk_degeri('panel.calkanti.sd.referansEtiket', 'tr')
        en = _sozluk_degeri('panel.calkanti.sd.referansEtiket', 'en')
        assert 'Çalkantısız referans koşu' in tr
        assert 'performans tahmini değildir' in tr
        assert 'güvenli uçuş ya da tutucu sınır göstermez' in tr
        assert 'Slosh-free reference run' in en
        assert 'not a performance estimate' in en
        assert 'neither a safe flight nor a conservative bound' in en

    def test_sinir_asimi_rozeti_ilk_asim_anini_ve_gecersizligi_yazar(self):
        for dil, parcalar in (('tr', ('{t}', 'DOĞRUSAL GEÇERLİLİK SINIRINI AŞTI',
                                      'geçersiz', 'yayımlanmaz')),
                              ('en', ('{t}', 'LINEAR VALIDITY LIMIT', 'invalid',
                                      'not reported'))):
            metin = _sozluk_degeri('sixdof.coupledInvalid', dil)
            for p in parcalar:
                assert p in metin, (dil, p)
        panel = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
        assert "yayim.neden_kodu === 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI'" in panel
        # sınır aşımında "zirve bulunamadı" rozeti basılmaz
        assert re.search(r"\} else if \(!bagliGecersiz\) \{\s*html \+= badge\("
                         r"T\('sixdof\.apogeeNotReported'", panel)

    def test_buyume_ussu_garanti_gibi_okunmaz(self):
        tr = _sozluk_degeri('panel.calkanti.hk.buyumeKat', 'tr')
        en = _sozluk_degeri('panel.calkanti.hk.buyumeKat', 'en')
        assert 'en çok' not in tr and 'at most' not in en
        assert 'donmuş katsayılı yaklaşık modal büyüme' in tr
        assert 'garantisi değildir' in tr
        assert 'frozen-coefficient approximate modal growth' in en
        assert 'not a guaranteed amplitude gain' in en

    def test_ucus_sonu_cumlesi_neden_iddia_etmez(self):
        tr = _sozluk_degeri('panel.calkanti.hk.ucusSonu', 'tr')
        en = _sozluk_degeri('panel.calkanti.hk.ucusSonu', 'en')
        assert 'neden sona erdiğini söylemez' in tr
        assert 'does not say why the flight ended' in en
        clk = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        hukum = _js_islevi(clk, 'hukumHtml')
        assert 'us.apojeye_vardi === false' in hukum
        for kod in ('tumble', 'ground_impact_under_power',
                    'ground_impact_before_apogee', 'no_liftoff', 'time_limit',
                    'solver_failed', 'apogee'):
            assert "'panel.calkanti.hk.ucus.%s'" % kod in clk
            _sozluk_degeri('panel.calkanti.hk.ucus.' + kod, 'tr')
        for kod in k2.SINIR_KONUMLARI[1:]:
            assert "'panel.calkanti.hk.konum.%s'" % kod in clk
        for kod in k2.GEREKCE_KODLARI:
            assert "'panel.calkanti.hk.gerekce.%s'" % kod in clk, kod

    def test_gecersiz_bolge_golgesi_zaman_eksenini_acmaz(self, tmp_path):
        """Doğrusal geçerlilik dışı bölgenin gölgesi serinin sonunda biter.

        ÖLÇÜLDÜ (devralma, 17 Kas): şeklin sağ kenarı 1e9 s idi; Plotly
        otomatik aralığa şekilleri de kattığı için örnek sıvı motorda
        çalkantı grafikleri ile irtifa / hücum açısı grafiklerinin zaman
        ekseni milyar saniyeye açılıyor, çizgiler görünmüyordu."""
        if shutil.which('node') is None:
            pytest.skip('node yok')
        clk = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        govde = _js_islevi(clk, 'gecersizSekil')
        assert '1e9' not in govde and 'x1: t1' in govde
        betik = tmp_path / 'g.js'
        betik.write_text(
            "global.window = {location: {pathname: '/liquid'}};\n"
            "global.document = {};\n"
            "require(%r);\n"
            "const C = window.HRMACalkanti;\n"
            "const izler = [{x: [0, 1, 2.5]}, {x: [0, 4, null]}, {x: []}];\n"
            "process.stdout.write(JSON.stringify({son: C._seriSonu(izler),"
            " sekil: C._gecersizSekil(1.5, C._seriSonu(izler)),"
            " t0yok: C._gecersizSekil(null, 4), ters: C._gecersizSekil(5, 4),"
            " bos: C._seriSonu([])}));\n" % str(JS / 'calkanti_panel.js'),
            encoding='utf-8')
        p = subprocess.run([shutil.which('node'), str(betik)],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        d = json.loads(p.stdout)
        assert d['son'] == 4 and d['bos'] is None
        assert d['sekil']['x0'] == 1.5 and d['sekil']['x1'] == 4
        assert d['t0yok'] is None and d['ters'] is None

    def test_rozet_hukmu_ile_calkanti_hukmu_yan_yana(self, tmp_path):
        """Yayın kapısı 6 (iki tanım yan yana): 6-DOF rozetinin uçuş hükmü
        (statik marj + hücum açısı) ile çalkantı taramasının hükmü farklı
        tanımlardır. ÖLÇÜLDÜ (devralma, örnek hibrit): rozet "KARARLI", alt
        bölüm "ÇALKANTI KAYNAKLI KARARSIZLIK" — fark ve neden rozetin üstünde
        yazılır; tarama kararsızlık bulmadıysa not yok."""
        if shutil.which('node') is None:
            pytest.skip('node yok')
        for dil, parcalar in (('tr', ('{hukum}', '{pencere}', 'ayrı bir denetimdir',
                                      'statik marjı ve hücum açısı')),
                              ('en', ('{hukum}', '{pencere}', 'different check',
                                      'static margin and angle of attack'))):
            metin = _sozluk_degeri('panel.calkanti.hk.anaNot', dil)
            for p in parcalar:
                assert p in metin, (dil, p)
        betik = tmp_path / 'n.js'
        betik.write_text(
            "global.window = {location: {pathname: '/hybrid'}};\n"
            "const eklenen = [];\n"
            "const rozet = {parentNode: {insertBefore: (d, r) => eklenen.push(d)}};\n"
            "global.document = {getElementById: (id) => (id === 'sd_badges' ? rozet : null),"
            " createElement: () => ({style: {}})};\n"
            "require(%r);\n"
            "const C = window.HRMACalkanti;\n"
            "C._hukumNotunuKoy({genel_hukum: 'CALKANTI_KAYNAKLI_KARARSIZLIK',"
            " pencereler: [{t1: 4.9486, t2: 10.3187}], rijit_pencereler: []});\n"
            "C._hukumNotunuKoy({genel_hukum: 'KARARLI', pencereler: [], rijit_pencereler: []});\n"
            "C._hukumNotunuKoy({genel_hukum: 'HUKUM_YOK', pencereler: [{t1: 1, t2: 2}],"
            " rijit_pencereler: []});\n"
            # 3.0.7 ONARIM-ÇALK (M7-UCUS-1): sınır aşılınca rozette uçuş
            # hükmü yok (yayım kuralı) ama statik marj satırı ve şema marj
            # bandını ("KARARLI …") yazmayı sürdürüyor; köprü cümlesi bu
            # durumda da konur ve o nitelemenin yalnız marj bandı olduğunu
            # söyler (eski beklenti "not konmaz" mühendis turunda çelişen
            # hüküm görünümü olarak ölçüldü).
            "C._hukumNotunuKoy({genel_hukum: 'CALKANTI_KAYNAKLI_KARARSIZLIK',"
            " pencereler: [{t1: 2.8, t2: 29.1}], rijit_pencereler: [],"
            " dogrusal_sinir: {asildi: true, t_ilk_asim_s: 24.1}});\n"
            "process.stdout.write(JSON.stringify(eklenen.map(d => [d.id, d.textContent])));\n"
            % str(JS / 'calkanti_panel.js'), encoding='utf-8')
        p = subprocess.run([shutil.which('node'), str(betik)],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        notlar = json.loads(p.stdout)
        assert len(notlar) == 2 and notlar[0][0] == 'sd_clk_hukum_notu'
        assert 'SLOSH-INDUCED INSTABILITY' in notlar[0][1]
        assert '4.95' in notlar[0][1] and '10.32' in notlar[0][1]
        assert notlar[1][0] == 'sd_clk_hukum_notu'
        assert 'static-margin band' in notlar[1][1] and '2.80' in notlar[1][1]

    def test_irtifa_grafigi_basligi_sinir_asiminda_nedeni_yazar(self):
        """Kalem 6: sınır aşılınca ``summary.apogee`` null; başlık "BİTİŞ: —"
        yerine bağlaşık koşunun t = ilk aşım'dan sonra geçersiz olduğunu
        yazar (ölçüldü: örnek sıvı, TR 1280, devralma)."""
        if shutil.which('node') is None:
            pytest.skip('node yok')
        panel = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
        assert 'bagliGecersizBaslik(data)' in panel
        for dil, parca in (('tr', 'geçersiz'), ('en', 'not valid')):
            metin = _sozluk_degeri('sixdof.chartAltCoupledInvalid', dil)
            assert '{t}' in metin and parca in metin, dil
        betik = ("function TF(k, p, f) { return f.replace('{t}', p.t); }\n"
                 "function sayiEkran(v, n) { return v.toFixed(n); }\n"
                 + "function T(k, f) { return f; }\n"
                 + _js_islevi(panel, 'bagliGecersizBaslik')
                 # ONARIM2-UÇUŞ-PANEL (M7-UCUS-4 a): sınır artık ORTAK
                 # sözleşmenin tek alanı t_gecersiz_bas_s (aşımda =
                 # t_ilk_asim_s, b9065606f); alan yoksa FAIL-CLOSED başlık.
                 + "\nconsole.log(JSON.stringify(["
                   "bagliGecersizBaslik({calkanti: {yayim: {neden_kodu:"
                   " 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', t_ilk_asim_s: 24.089,"
                   " t_gecersiz_bas_s: 24.089}}}),"
                   " bagliGecersizBaslik({calkanti: {yayim: {neden_kodu: null,"
                   " t_ilk_asim_s: null}}}),"
                   " bagliGecersizBaslik({summary: {}})]));")
        cikti = subprocess.run([shutil.which('node')], input=betik,
                               capture_output=True, text=True, timeout=30)
        assert cikti.returncode == 0, cikti.stderr
        var, yok, blok_yok = json.loads(cikti.stdout)
        assert '24.09' in var and 'not valid' in var
        assert yok is None and blok_yok is None
