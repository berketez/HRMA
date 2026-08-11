"""POST /api/fea/thermal bekçileri (D2 geçici termal FEA kullanıcı yüzü).

KAPATILAN BOŞLUK
----------------
Uç (``hrma/app.py::api_fea_thermal``) ve köprü işlevleri
(``hrma/fea/bridge.py::run_thermal_from_motor`` / ``extract_thermal_inputs``)
çalışma ağacında YAZILMIŞTI ama uçtan uca HİÇ koşturulmamış, testi de
yoktu — yani yayımlanmış ama denenmemiş bir uçtu. Bu dosya onu koşturur ve
sözleşmesini kilitler.

NE KİLİTLENİR
-------------
  1. GERÇEK koşu: ``/calculate`` hibrit sonucu +
     ``/api/analysis/wall-profile`` eksenel profili → HTTP 200,
     ``status='ok'``; düğüm sıcaklık alanı düğüm sayısıyla aynı uzunlukta,
     tepe cidar sıcaklığı ortam sıcaklığının ÜSTÜNDE ve sonlu, enerji
     bütçesi (dU = Q_iç + Q_dış) kendi içinde tutarlı.
  2. **EKSENEL PROFİL İSTEK GÖVDESİNDEN GELİR, MOTORDAN UYDURULMAZ.**
     Motor sonuç sözlüğünde h(z) alanı YOKTUR; hibrit yalnız BOĞAZ
     skalerini (``nozzle_material_analysis.throat_thermal``) yayımlar.
     Profil verilmediğinde uç, o skalerden bir profil TÜRETMEZ:
     NOT_MODELLED döner, eksiği adıyla söyler ve gövdede hiçbir sıcaklık
     alanı bulunmaz. Bu davranış hem skaleri TAŞIYAN hem taşımayan motor
     sözlüğüyle sınanır — "elimizde bir h vardı, onu yaydık" yolunun
     kapalı olduğu böyle kanıtlanır.
  3. Başka bir geometrinin profili bu mesh'e taşınmaz: profil ekseni
     konturla uyuşmuyorsa red.
  4. Ortam sıcaklığı ZORUNLUDUR (hiçbir motor çözücüsü yayımlamaz);
     verilmezse uydurulmaz, red edilir.
  5. Dış yüzey sınır koşulu verilmediğinde ADYABATİK alınır ve bu BEYAN
     edilir; verildiğinde dışarı gerçekten ısı çıkar (Q_dış < 0).
  6. Bütçeler: eleman ve sıcaklık-geçmişi tavanları uygulanır, kısıtlama
     ``limits`` içinde beyan edilir; tam T(t) geçmişi gövdeye KONMAZ ve bu
     da beyan edilir.

ÖLÇÜM YÖNTEMİ
-------------
Port bağlanmaz; Flask ``test_client``. Sayısal doğruluk bu dosyanın işi
değildir (o çözücünün kendi doğrulama testlerinin işidir); kilitlenen şey
sözleşme, dürüstlük kapıları ve zincirin sadakatidir. Hiçbir sıcaklık
sabit bir sayıya bağlanmamıştır.
"""

import contextlib
import io

import pytest

THERMAL_ENDPOINT = '/api/fea/thermal'

#: Redli (NOT_MODELLED / NOT_AVAILABLE) gövdede BULUNMAMASI zorunlu alanlar.
#: Bunlardan biri görünürse çözüm koşmadan sonuç yayımlanmış demektir.
REDDE_BULUNMAYACAK_ALANLAR = ('mesh', 'fields', 'history', 'scalars',
                              'energy', 'material_limits')

#: Küçük mesh — bekçinin işi hassasiyet değil, zincirin sadakati.
#: (Ad, yapısal ucun ``KUCUK_KOSU``suyla KARIŞTIRILMASIN: iki uç farklı
#: parametre adları alır — yapısal n_axial0/n_radial0/max_rounds, termal
#: n_axial/n_radial/max_halvings.)
TERMAL_KUCUK_KOSU = {'n_axial': 12, 'n_radial': 4, 'max_halvings': 3}

HIBRIT_GOVDE = {
    'motor_type': 'hybrid',
    'thrust': 5000,
    'burn_time': 10,
    'chamber_pressure': 20,
    'of_ratio': 2.5,
    'fuel_type': 'htpb',
    'oxidizer_type': 'n2o',
    'expansion_ratio': 4.0,
    'nozzle_type': 'conical',
    'chamber_material': 'steel_4130',
    'wall_thickness': 5,
}


def _quiet(fn, *args, **kwargs):
    """Motor/çözücü modülleri stdout'a bolca basıyor; testte sessize al."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def motor(client):
    """GERÇEK ``/calculate`` hibrit sonucu."""
    resp = _quiet(client.post, '/calculate', json=HIBRIT_GOVDE,
                  headers={'Host': '127.0.0.1:8080'})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()['motor']


@pytest.fixture(scope='module')
def profil(client, motor):
    """GERÇEK ``/api/analysis/wall-profile`` çıktısı — h(z) tek kaynağı."""
    resp = _quiet(client.post, '/api/analysis/wall-profile', json={
        'chamber_pressure': motor['chamber_pressure'],
        'chamber_temperature': motor['chamber_temperature'],
        'chamber_diameter': motor['chamber_diameter'],
        'chamber_length': motor['chamber_length'],
        'burn_time': motor['burn_time'],
        'mdot_total': motor['mdot_total'],
        'throat_diameter': motor['throat_diameter'],
        'exit_diameter': motor['exit_diameter'],
        'expansion_ratio': motor['expansion_ratio'],
        'nozzle_type': 'conical',
        'material': 'steel_4130',
        'wall_thickness': 0.005,
    }, headers={'Host': '127.0.0.1:8080'})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    wp = resp.get_json()['wall_profile']
    for anahtar in ('x_mm', 'h_g', 'T_recovery'):
        assert isinstance(wp[anahtar], list) and len(wp[anahtar]) >= 2
    return wp


def kos(client, **govde):
    """Ucu çağırır; (http_kodu, fea_bloğu | ham_gövde) döner."""
    yuk = dict(TERMAL_KUCUK_KOSU)
    yuk.update(govde)
    resp = _quiet(client.post, THERMAL_ENDPOINT, json=yuk,
                  headers={'Host': '127.0.0.1:8080'})
    body = resp.get_json()
    return resp.status_code, (body.get('fea') if isinstance(body, dict)
                              and 'fea' in body else body)


@pytest.fixture(scope='module')
def kosu(client, motor, profil):
    """Ortam sıcaklığı verilmiş, dış yüzeyi adyabatik tam koşu."""
    kod, fea = kos(client, motor=motor, axial_profile=profil,
                   ambient_temperature_K=293.15)
    assert kod == 200, fea
    assert fea['status'] == 'ok', fea
    return fea


# ---------------------------------------------------------------------------
# 1. GERÇEK zincir koştu mu?
# ---------------------------------------------------------------------------
class TestGercekKosu:

    def test_alanlar_mesh_ile_tutarli(self, kosu):
        mesh = kosu['mesh']
        n_nodes = mesh['n_nodes']
        assert n_nodes > 0
        assert len(mesh['nodes']) == n_nodes
        assert len(kosu['fields']['temperature_final_K']) == n_nodes
        # İç yüzey dizileri mesh'in eksenel istasyon sayısı kadar.
        n_istasyon = mesh['n_axial'] + 1
        assert len(kosu['fields']['inner_surface_z_m']) == n_istasyon
        assert len(kosu['fields']['inner_surface_T_final_K']) == n_istasyon

    def test_sicakliklar_fiziksel(self, kosu):
        ortam = kosu['scalars']['ambient_temperature_K']
        alan = kosu['fields']['temperature_final_K']
        assert all(isinstance(t, (int, float)) for t in alan)
        # Isıtılan bir cidar: hiçbir düğüm başlangıç sıcaklığının altına
        # düşemez (dış yüzey adyabatik, iç yüzey ısıtılıyor).
        assert min(alan) >= ortam - 1e-6
        tepe = kosu['scalars']['peak_wall_T_K']
        assert tepe > ortam
        assert tepe == pytest.approx(max(alan), rel=1e-9)
        assert 0 < kosu['scalars']['peak_time_s'] <= kosu['scalars'][
            'burn_time_s']

    def test_gecmis_uzunluklari_esit(self, kosu):
        assert len(kosu['history']['times_s']) == len(
            kosu['history']['peak_wall_T_history_K'])

    def test_enerji_butcesi_kapaniyor(self, kosu):
        """dU = Q_iç + Q_dış — çözücünün kendi bütçesi tutarlı olmalı."""
        e = kosu['energy']
        assert e['dU_J'] == pytest.approx(e['Q_inner_J'] + e['Q_outer_J'],
                                          rel=1e-6, abs=1.0)
        assert e['Q_inner_J'] > 0.0  # sıcak gaz cidarı ısıtıyor

    def test_malzeme_ve_kalinlik_motordan_geliyor(self, kosu, motor):
        """Sayılar uydurulmaz: malzeme ve cidar motor sonucundan okunur."""
        ca = motor['structural_analysis']['chamber_analysis']
        assert kosu['scalars']['material_key'] == motor[
            'structural_analysis']['design_parameters']['material']
        assert kosu['scalars']['wall_thickness_m'] == pytest.approx(
            ca['wall_thickness_used_mm'] / 1000.0, rel=1e-9)
        assert kosu['scalars']['burn_time_s'] == pytest.approx(
            motor['burn_time'], rel=1e-9)


# ---------------------------------------------------------------------------
# 2. EKSENEL PROFİL İSTEKTEN GELİR — motordan UYDURULMAZ
# ---------------------------------------------------------------------------
class TestProfilMotordanUydurulmuyor:

    def test_profilsiz_istek_reddediliyor(self, client, motor):
        kod, fea = kos(client, motor=motor, ambient_temperature_K=293.15)
        assert kod == 200
        assert fea['status'] == 'NOT_MODELLED'
        assert any('axial_profile' in str(m) for m in fea['missing']), \
            fea['missing']
        for alan in REDDE_BULUNMAYACAK_ALANLAR:
            assert alan not in fea, (
                f'Profil verilmediği hâlde {alan!r} yayımlandı — bir yerden '
                'sıcaklık üretilmiş')

    def test_bogaz_skaleri_varken_bile_profil_turetilmiyor(self, client,
                                                           motor):
        """Kritik kural: motorda h SKALERİ olması profil YERİNE geçmez.

        Hibrit motor ``nozzle_material_analysis.throat_thermal`` içinde
        boğaz ısı akısı ve gaz sıcaklığı yayımlar. Bu tek noktadır; h(z)
        değildir. Uç bunu görüp bir eksenel dağılım uydurursa test düşer.
        """
        skalerli = dict(motor)
        skalerli['nozzle_material_analysis'] = {'throat_thermal': {
            'status': 'analyzed',
            'throat_wall_temperature_K': 1200.0,
            'gas_recovery_temperature_K': 3000.0,
            'throat_heat_flux_MW_m2': 5.0,
        }}
        kod, fea = kos(client, motor=skalerli, ambient_temperature_K=293.15)
        assert kod == 200
        assert fea['status'] == 'NOT_MODELLED', (
            'Boğaz skaleri bir h(z) profili yerine kullanıldı')
        assert 'fields' not in fea and 'scalars' not in fea

    def test_eksik_profil_alani_adiyla_soyleniyor(self, client, motor,
                                                  profil):
        eksik = {k: v for k, v in profil.items() if k != 'T_recovery'}
        kod, fea = kos(client, motor=motor, axial_profile=eksik,
                       ambient_temperature_K=293.15)
        assert kod == 200
        assert fea['status'] == 'NOT_MODELLED'
        assert any('T_recovery' in str(m) for m in fea['missing']), \
            fea['missing']

    def test_baska_geometrinin_profili_tasinmiyor(self, client, motor,
                                                  profil):
        kaydirilmis = dict(profil)
        kaydirilmis['x_mm'] = [x + 500.0 for x in profil['x_mm']]
        kod, fea = kos(client, motor=motor, axial_profile=kaydirilmis,
                       ambient_temperature_K=293.15)
        assert kod == 200
        assert fea['status'] == 'NOT_MODELLED'
        assert any('uyuşmuyor' in str(m) or 'ekseni' in str(m)
                   for m in fea['missing']), fea['missing']

    def test_fiziksel_olmayan_profil_reddediliyor(self, client, motor,
                                                  profil):
        bozuk = dict(profil)
        bozuk['h_g'] = [-1.0] * len(profil['h_g'])
        kod, fea = kos(client, motor=motor, axial_profile=bozuk,
                       ambient_temperature_K=293.15)
        assert kod == 200
        assert fea['status'] == 'NOT_MODELLED'
        for alan in REDDE_BULUNMAYACAK_ALANLAR:
            assert alan not in fea


# ---------------------------------------------------------------------------
# 3. Ortam sıcaklığı ve dış yüzey sınır koşulu
# ---------------------------------------------------------------------------
class TestSinirKosullari:

    def test_ortam_sicakligi_zorunlu(self, client, motor, profil):
        """Hiçbir motor çözücüsü yayımlamaz; uydurulmaz, red edilir."""
        kod, fea = kos(client, motor=motor, axial_profile=profil)
        assert kod == 200
        assert fea['status'] == 'NOT_MODELLED'
        assert 'ambient_temperature_K' in fea['missing']
        for alan in REDDE_BULUNMAYACAK_ALANLAR:
            assert alan not in fea

    def test_dis_yuzey_adyabatik_ve_beyanli(self, kosu):
        """``outer_ambient`` verilmedi: dışarı ısı ÇIKMAZ ve bu yazılır."""
        assert kosu['energy']['Q_outer_J'] == pytest.approx(0.0, abs=1e-6)
        dis = kosu['meta']['sinir_kosullari_koprusu']['dis_yuzey']
        assert 'adyabat' in dis.lower(), (
            'Adyabatik dış yüzey varsayımı beyan edilmiyor: ' + str(dis))
        assert 'outer_ambient' in dis, (
            'Kullanıcıya gerçek dış koşulu nasıl vereceği söylenmiyor')

    def test_dis_ortam_verilince_isi_cikiyor(self, client, motor, profil):
        kod, fea = kos(client, motor=motor, axial_profile=profil,
                       ambient_temperature_K=293.15,
                       outer_ambient={'h_W_m2K': 10.0, 'T_ambient_K': 293.15,
                                      'emissivity': 0.3})
        assert kod == 200 and fea['status'] == 'ok'
        assert fea['energy']['Q_outer_J'] < 0.0, (
            'Dış ortam sınır koşulu verildi ama dışarı hiç ısı çıkmıyor')


# ---------------------------------------------------------------------------
# 4. Girdi kapıları ve bütçe beyanı
# ---------------------------------------------------------------------------
class TestKapilarVeButceler:

    def test_bos_govde_400(self, client):
        """Ortada motor YOKKEN 'başarılı ama boş' yanıt üretilmez."""
        resp = _quiet(client.post, THERMAL_ENDPOINT, json={},
                      headers={'Host': '127.0.0.1:8080'})
        assert resp.status_code == 400
        assert resp.get_json()['status'] == 'error'

    def test_yalniz_parametreli_govde_hukum_uretmiyor(self, client):
        """Motor alanı yok, yalnız mesh parametreleri var.

        Uç, gövdenin kendisini son aday olarak deniyor (bkz.
        ``_fea_pick_motor_results``); imza taşımadığı için köprü dürüst
        NOT_MODELLED üretmeli — sıcaklık alanı ÜRETMEMELİ.
        """
        kod, fea = kos(client)
        assert kod == 200
        assert fea['status'] == 'NOT_MODELLED'
        for alan in REDDE_BULUNMAYACAK_ALANLAR:
            assert alan not in fea

    def test_motor_imzasiz_sozluk_reddediliyor(self, client, profil):
        kod, fea = kos(client, motor={'foo': 1},
                       axial_profile=profil, ambient_temperature_K=293.15)
        assert kod == 200
        assert fea['status'] == 'NOT_MODELLED'
        assert fea['missing'], 'eksiğin adı söylenmiyor'

    def test_butce_beyani_var(self, kosu):
        limits = kosu['limits']
        assert limits['n_axial'] <= limits['n_axial_requested']
        assert limits['n_radial_effective'] >= limits['n_radial_requested'] \
            or limits['n_radial_effective'] > 0
        assert limits['temperature_history_in_payload'] is False
        assert isinstance(limits['clamped'], bool)
        assert limits['_basis']

    def test_zaman_adimi_beyani_var(self, kosu):
        ts = kosu['time_step']
        assert 'converged' in ts
        assert ts.get('beyan'), 'zaman adımı yakınsaması beyan edilmiyor'

    def test_girdinin_hangi_alandan_alindigi_yaziliyor(self, kosu):
        assert kosu['input_field'] in ('motor', 'motor_results', 'results',
                                       'body', 'motor.motor')
