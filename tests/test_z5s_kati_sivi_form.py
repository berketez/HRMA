"""ÖH Z5S / S5 — ``/calculate_solid`` + ``/calculate_liquid`` form sözleşmesi.

Kapatılan kalemler (ölçüm: ``docs/scofield/raw/OH/Z5S/s5/once_supurme.json``,
onarım sonrası: ``sonra_supurme.json``):

* **P16B2-01 (KRİTİK)** — katı tasarım noktasının ``requested_*`` alanları
  UYDURULUYORDU. ``thrust`` ∈ {0, -100, 1e9, inf, NaN, ``true``, ``"peynir"``}
  yedi vakanın YEDİSİNDE de HTTP 200 dönüyor, yanıt
  ``requested_average_thrust_N = 3063,784907572051`` (kullanıcının hiç
  yazmadığı bir sayı — öğretici geometrinin ÖLÇÜLEN taban itkisi) ve
  ``achieved = True`` diyordu. Kök ``solid_rocket_engine.
  _apply_design_point_sizing`` içindeydi: ``if thrust_target is None:
  thrust_target = base_thrust``, ve ``None`` "gönderilmedi" ile "reddedildi"
  arasında ayrım yapmıyordu.
* **P7B2-07** — ``use_tutorial_defaults`` bayrağı ``bool(...)`` ile
  kuruluyordu; ``"false"``, ``"0"``, ``"no"``, ``"off"`` (ve ``"peynir"``)
  öğretici kipi AÇIYORDU. Doğru yardımcı (``_json_bool``) aynı dosyadaydı.
* **P16B2-02** — geometri VE tasarım noktası birlikte gelince kullanıcının
  geometrisi SESSİZCE eziliyordu.
* **P16B2-03** — tasarım noktası kipinde geometri tohumu uç katmanının
  öğretici sayılarıydı ve bu hiçbir yerde yazmıyordu; boyutlandırma
  tutmayınca yayımlanan motor O TOHUMDU.
* **P16B2-04** — ``propellant_type`` katı uçta tipsiz/bantsızdı (sözlük,
  liste, ``-50``, ``true``, ``1e9``, 100 KB dize -> 200 + tam "Custom"
  tasarım; 100 KB dize 1,17 MB yanıt); kardeş sıvı uç altısını da 400
  veriyordu.
* **P16B2-09** — ``chamber_temperature`` iki uçta da TAMAMEN ÖLÜYDÜ
  (-1e9..1e9 arası yanıt bit-aynı) ve hiçbir beyan listesinde yoktu.
* **P16B2-11** — sayı-benzeri dizeler kaza eseri elenip kaza eseri geçiyordu:
  ``thrust="1000"`` katıda 200 (Isp 240,80), sıvıda/hibritte 400; katıda
  ``chamber_diameter="100"`` HAM ``TypeError`` metniyle 400.
* **P16B2-13** — ``mixture_ratio = true`` kabul ediliyor ve yanıtta JSON
  MANTIKSAL değeri olarak geri basılıyordu (``float(True) = 1,0`` banda
  düşüyor); ``false`` ise bant dışı kaldığı için zaten reddediliyordu.

Sözleşme (Berke karar listesi madde 5+8 — "tasarım yolu banda 400"):
bu iki uç TASARIM yoludur. Reddedilen alan için (a) HTTP sınıfı 4xx,
(b) gövdede makine-okur ALAN ADI, (c) gövdede Python istisna metni YOK.
Kabul edilen istekte sayı DEĞİŞMEZ; eklenen tek şey beyandır (kanıt:
``sonra_fizik.json`` — beyan alanları çıkarıldığında gövde bit-aynı).
"""

import json

import pytest

from hrma.app import app
from hrma.engines.solid_rocket_engine import (
    SOLID_DESIGN_POINT,
    SolidRocketEngine,
)

#: Gövdeye SIZMAMASI gereken Python iç metinleri (S2'nin ölçütü).
PYTHON_SIZINTISI = (
    'Traceback', 'not supported between', 'unsupported operand',
    'object of type', 'TypeError', 'KeyError', 'AttributeError',
    'NoneType', 'Unknown format code', 'could not convert string to float',
)

KATI_GEOMETRI = {'propellant_type': 'apcp', 'chamber_pressure': 40,
                 'chamber_diameter': 100.0, 'grain_length': 500.0,
                 'core_diameter': 30.0}
KATI_TASARIM_NOKTASI = {'propellant_type': 'apcp', 'chamber_pressure': 40,
                        'burn_time': 3.0}
SIVI_GECERLI = {'thrust': 10000, 'chamber_pressure': 100,
                'mixture_ratio': 2.5, 'fuel_type': 'rp1',
                'oxidizer_type': 'lox'}
HIBRIT_GECERLI = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                  'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
                  'chamber_pressure': 20.0}


@pytest.fixture(scope='module')
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _adli_ret(yanit, alan, beklenen_sinif=(400, 422)):
    """Reddin üç ayağını birden ölçer: sınıf, alan adı, sızıntı yokluğu."""
    assert yanit.status_code in beklenen_sinif, (
        'Fizik dışı / tipsiz girdi kabul edildi (HTTP %s)'
        % yanit.status_code)
    govde = yanit.get_json()
    metin = json.dumps(govde, ensure_ascii=False)
    sizanlar = [im for im in PYTHON_SIZINTISI if im in metin]
    assert not sizanlar, (
        'Gövdeye Python iç metni sızıyor %r: %s' % (sizanlar, metin[:400]))
    alanlar = [k.get('field') for k in (govde.get('invalid_fields') or [])]
    alanlar += govde.get('missing_fields') or []
    assert alan in alanlar, (
        "Ret gövdesi '%s' alanını adlandırmıyor: %s" % (alan, metin[:400]))
    return govde


# ---------------------------------------------------------------------------
# P16B2-01 (KRİTİK) — tasarım noktası hedefi UYDURULMAZ
# ---------------------------------------------------------------------------
class TestUydurulanTasarimNoktasi:

    @pytest.mark.parametrize('deger', [
        0, -100, 1e9, float('inf'), float('nan'), True, '1000', 'peynir',
    ])
    def test_fizik_disi_hedef_adli_4xx_alir(self, client, deger):
        """Çözülemeyen hedef 200 + uydurma sayı DEĞİL, adlı 4xx üretir."""
        yanit = client.post('/calculate_solid',
                            json=dict(KATI_TASARIM_NOKTASI, thrust=deger))
        _adli_ret(yanit, 'thrust')

    @pytest.mark.parametrize('deger', [0, -100, 1e9, float('inf'), True,
                                       'peynir'])
    def test_motor_reddedilen_hedefle_hukum_vermez(self, deger):
        """Çözücü katmanı da fail-closed: uydurulmuş 'requested' yok.

        Uç kapısı bu istekleri zaten reddediyor; bu bekçi motorun KENDİ
        sözleşmesini kilitler, çünkü motor uçtan bağımsız da kuruluyor
        (Monte Carlo, UQ, uçuş aracı, kayıt bağdaştırıcıları).
        """
        motor = SolidRocketEngine(
            propellant_type='apcp', chamber_pressure=40,
            chamber_diameter=100, grain_length=500, core_diameter=30,
            overrides={'thrust': deger, 'burn_time': 3.0})
        dp = motor.design_point
        assert dp['status'] == 'target_not_resolved', dp
        assert dp['requested_average_thrust_N'] is None, dp
        assert dp['sizing_applied'] is False, dp
        assert dp['achieved'] is None, (
            'Denenmemiş bir hedef için başarı hükmü basılıyor: %r' % dp)
        assert dp['rejected_targets'][0]['field'] == 'thrust', dp

    def test_olculen_eksen_requested_diye_yayimlanmaz(self, client):
        """Yalnız süre istendiğinde itki hedefi ÖLÇÜLMÜŞTÜR, istenmemiştir.

        ÖLÇÜLDÜ (onarım öncesi): geometri + ``burn_time`` gönderen istek
        ``requested_average_thrust_N = 3063,78`` diyordu — kullanıcı o sayıyı
        hiç yazmamıştı, sayı girilen geometrinin eğrisinden ölçülmüştü.
        """
        govde = client.post('/calculate_solid',
                            json=dict(KATI_GEOMETRI, burn_time=3.0)).get_json()
        dp = govde['design_point']
        assert dp['requested_average_thrust_N'] is None, dp
        assert dp['thrust_target_source'] == 'measured_from_input_geometry'
        assert dp['burn_time_target_source'] == 'request'
        assert dp['requested_burn_time_s'] == pytest.approx(3.0)
        # Sayı SİLİNMEDİ, adı düzeltildi: ölçülen hedef kendi adresinde.
        assert dp['thrust_target_N'] > 0

    def test_istenen_hedef_aynen_yayimlanir(self, client):
        """Gerçekten istenen hedef ``requested_*`` alanında AYNEN kalır."""
        govde = client.post('/calculate_solid', json=dict(
            KATI_TASARIM_NOKTASI, thrust=3000.0)).get_json()
        dp = govde['design_point']
        assert dp['requested_average_thrust_N'] == pytest.approx(3000.0)
        assert dp['thrust_target_source'] == 'request'
        assert dp['achieved'] is True

    def test_hedef_bandi_cozucunun_bandidir(self, client):
        """Uç kapısının bandı ``SOLID_DESIGN_POINT``tan gelir (tek kaynak)."""
        govde = client.post('/calculate_solid', json=dict(
            KATI_TASARIM_NOKTASI, thrust=0)).get_json()
        kunye = govde['invalid_fields'][0]
        assert kunye['accepted_range'] == [
            float(SOLID_DESIGN_POINT['min_target_thrust']),
            float(SOLID_DESIGN_POINT['max_target_thrust'])]
        assert kunye['unit'] == 'N'


# ---------------------------------------------------------------------------
# P7B2-07 — öğretici bayrağı
# ---------------------------------------------------------------------------
class TestOgreticiBayragi:

    @pytest.mark.parametrize('uc', ['/calculate_solid', '/calculate_liquid'])
    @pytest.mark.parametrize('deger', ['false', '0', 'no', 'off', False])
    def test_kapali_bayrak_ogretici_tasarim_uretmez(self, client, uc, deger):
        yanit = client.post(uc, json={'use_tutorial_defaults': deger})
        assert yanit.status_code == 422, (
            "Kapatma niyeti ('%s') öğretici kipi AÇTI (HTTP %s)"
            % (deger, yanit.status_code))
        govde = yanit.get_json()
        assert govde['status'] == 'incomplete_input'
        assert 'defaults_applied' not in govde
        assert govde['missing_fields']

    @pytest.mark.parametrize('uc', ['/calculate_solid', '/calculate_liquid'])
    @pytest.mark.parametrize('deger', [True, 'true', '1', 'yes', 'on', 1])
    def test_acik_bayrak_ogretici_kipi_calistirir(self, client, uc, deger):
        yanit = client.post(uc, json={'use_tutorial_defaults': deger})
        assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
        govde = yanit.get_json()
        assert govde['input_source'] == 'tutorial_defaults'
        assert govde['defaults_applied']

    @pytest.mark.parametrize('uc', ['/calculate_solid', '/calculate_liquid'])
    def test_mantiksal_olmayan_deger_adli_ret_alir(self, client, uc):
        yanit = client.post(uc, json={'use_tutorial_defaults': 'peynir'})
        _adli_ret(yanit, 'use_tutorial_defaults')


# ---------------------------------------------------------------------------
# P16B2-02 / P16B2-03 — geometri kaynağı BEYAN edilir
# ---------------------------------------------------------------------------
class TestGeometriBeyani:

    def test_ezilen_geometri_olculerek_bildirilir(self, client):
        """Boyutlandırma kullanıcının geometrisini ezdiyse ölçüm yayımlanır."""
        govde = client.post('/calculate_solid', json=dict(
            KATI_GEOMETRI, thrust=3000.0, burn_time=3.0)).get_json()
        dp = govde['design_point']
        assert dp['geometry_replaced_by_sizing'] is True, dp
        assert dp['published_geometry_source'] == 'sized_to_design_point'
        degisen = {k['field']: k for k in dp['geometry_fields_replaced']}
        assert 'core_diameter_mm' in degisen
        # Beyan ÖLÇÜMDÜR: gönderilen ile yayımlanan gerçekten farklı olmalı.
        for kayit in degisen.values():
            assert kayit['given_mm'] != pytest.approx(kayit['used_mm'])
        assert dp['input_geometry_mm']['chamber_diameter_mm'] == \
            pytest.approx(100.0)

    def test_ezilme_yoksa_beyan_da_yok(self, client):
        """Tasarım noktası verilmediğinde geometri beyanı üretilmez."""
        govde = client.post('/calculate_solid', json=KATI_GEOMETRI).get_json()
        assert govde.get('design_point') is None
        assert 'geometry_seed' not in govde

    def test_uc_tohumu_beyan_edilir(self, client):
        """Geometrisiz tasarım noktası isteğinde tohumun kaynağı yazılır."""
        govde = client.post('/calculate_solid', json=dict(
            KATI_TASARIM_NOKTASI, thrust=3000.0)).get_json()
        tohum = govde['geometry_seed']
        assert tohum['source'] == 'endpoint_default'
        assert set(tohum['fields']) == {'chamber_diameter', 'grain_length',
                                        'core_diameter'}

    def test_ulasilamaz_hedefte_yayimlanan_geometri_adlandirilir(self, client):
        """Boyutlandırma tutmazsa MOTOR YAYIMLANMAZ, tohum yine adlandırılır.

        ÖH D26 (defter P15B3-02, YÜKSEK) — ÇEVRİLDİ. Testin eski gövdesi
        yanıtın HTTP 200 olduğunu ve tohum motorunun yayımlandığını
        varsayıyordu; P16B2-03'ün kazanımı (yayımlanan geometrinin KAYNAĞI
        adıyla yazılır) o varsayımın üstüne kurulmuştu. Ölçüldü
        (``docs/scofield/raw/OH/D26/kati/a1/once.json``, taban 7751531):
        aynı daldan geçen 20 / 50 / 100 / 150 / 200 / 250 N istekleri
        BİT-ÖZDEŞ tek bir yanıt üretiyordu (1930,475099292884 N) — beyan
        doğruydu ama beyan çözüm değildir (Doktrin 1). Zarf kapısı artık
        fail-closed: hüküm yayımlanmaz (422). P16B2-03'ün kazanımı AYNEN
        korunur ve burada sınanır: reddin gövdesi hem
        ``published_geometry_source``ı hem de ``geometry_seed`` beyanını
        taşır (ÖK-22 — kazanılmış davranış gevşetilmez).
        """
        cevap = client.post('/calculate_solid', json=dict(
            KATI_TASARIM_NOKTASI, thrust=10.0))
        assert cevap.status_code == 422
        govde = cevap.get_json()
        dp = govde['design_point']
        assert dp['achieved'] is False
        assert dp['sizing_applied'] is False
        assert dp['published_geometry_source'] == 'unchanged_input_geometry'
        assert dp['geometry_replaced_by_sizing'] is False
        assert govde['geometry_seed']['source'] == 'endpoint_default'
        assert set(govde['geometry_seed']['fields']) == {
            'chamber_diameter', 'grain_length', 'core_diameter'}


# ---------------------------------------------------------------------------
# P16B2-04 — kimlik alanının TİPİ
# ---------------------------------------------------------------------------
class TestYakitKimligiTipi:

    @pytest.mark.parametrize('deger', [
        {'a': 1}, [1, 2], -50, True, 1e9, 'x' * 100000,
    ])
    def test_tipsiz_kimlik_adli_ret_alir(self, client, deger):
        yanit = client.post('/calculate_solid',
                            json=dict(KATI_GEOMETRI, propellant_type=deger))
        _adli_ret(yanit, 'propellant_type')

    @pytest.mark.parametrize('deger', [{'a': 1}, [1, 2], -50, True, 1e9])
    def test_kardes_sivi_uc_ayni_sinifi_reddeder(self, client, deger):
        """Aynı girdi sınıfı iki uçta da 4xx (kardeş kapı paritesi)."""
        yanit = client.post('/calculate_liquid',
                            json=dict(SIVI_GECERLI, fuel_type=deger))
        assert yanit.status_code in (400, 422), yanit.status_code

    def test_uzun_dize_dev_govde_uretmez(self, client):
        """100 KB'lik kimlik 1,17 MB yanıt üretiyordu; artık kısa ret."""
        yanit = client.post('/calculate_solid', json=dict(
            KATI_GEOMETRI, propellant_type='x' * 100000))
        assert yanit.status_code == 400
        assert len(yanit.get_data()) < 4096, len(yanit.get_data())

    def test_gecerli_katalog_anahtari_kabul_edilir(self, client):
        yanit = client.post('/calculate_solid',
                            json=dict(KATI_GEOMETRI, propellant_type='kndx'))
        assert yanit.status_code == 200


# ---------------------------------------------------------------------------
# P16B2-09 — çözücünün okumadığı alan BEYAN edilir
# ---------------------------------------------------------------------------
class TestOluGirdiBeyani:

    @pytest.mark.parametrize('uc,govde', [
        ('/calculate_solid', KATI_GEOMETRI),
        ('/calculate_liquid', SIVI_GECERLI),
    ])
    def test_chamber_temperature_olu_ilan_edilir(self, client, uc, govde):
        yanit = client.post(uc, json=dict(govde, chamber_temperature=3000.0))
        assert yanit.status_code == 200
        beyan = yanit.get_json().get('inputs_not_used') or []
        alanlar = {k['field']: k for k in beyan}
        assert 'chamber_temperature' in alanlar, (
            'Ölü girdi hâlâ sessiz: %s' % uc)
        kayit = alanlar['chamber_temperature']
        assert kayit['reason'] == 'solver_owned_output_name'
        assert kayit['submitted'] == pytest.approx(3000.0)

    def test_kati_uc_gercek_alan_adini_soyler(self, client):
        """'Girdiniz kullanılmadı' demek, doğrusunu söylemeden yarım kalır."""
        govde = client.post('/calculate_solid', json=dict(
            KATI_GEOMETRI, chamber_temperature=3000.0)).get_json()
        kayit = {k['field']: k for k in govde['inputs_not_used']}
        assert kayit['chamber_temperature']['use_instead'] == 'flame_temp'

    @pytest.mark.parametrize('uc,govde', [
        ('/calculate_solid', KATI_GEOMETRI),
        ('/calculate_liquid', SIVI_GECERLI),
    ])
    def test_gonderilmeyen_alan_icin_beyan_uretilmez(self, client, uc, govde):
        """Beyan ölçümle üretilir: alan yoksa yanlış alarm da yazılmaz."""
        yanit = client.post(uc, json=dict(govde))
        assert 'inputs_not_used' not in yanit.get_json()

    def test_yeni_beyan_cozucununkini_susturmaz(self, client):
        """Beyan EKLENİR, var olan beyan EZİLMEZ.

        ÖLÇÜLDÜ (S5 içi, düzeltmeden önce): uç katmanı
        ``inputs_not_used``a doğrudan atama yapınca sıvı çözücünün kendi
        ``expansion_ratio`` beyanı siliniyordu — bir beyan eklerken başka
        bir beyanı susturmak, kapatılan kusurun ta kendisidir.
        """
        yalniz = client.post('/calculate_liquid', json=dict(
            SIVI_GECERLI, expansion_ratio=99.0)).get_json()
        ikisi = client.post('/calculate_liquid', json=dict(
            SIVI_GECERLI, expansion_ratio=99.0,
            chamber_temperature=3000.0)).get_json()
        tek = {k['field'] for k in (yalniz.get('inputs_not_used') or [])}
        cift = {k['field'] for k in (ikisi.get('inputs_not_used') or [])}
        assert 'expansion_ratio' in tek, yalniz.get('inputs_not_used')
        assert tek <= cift, (
            'Yeni beyan çözücünün beyanını sildi: %s -> %s' % (tek, cift))
        assert 'chamber_temperature' in cift

    @pytest.mark.parametrize('uc,govde', [
        ('/calculate_solid', KATI_GEOMETRI),
        ('/calculate_liquid', SIVI_GECERLI),
    ])
    @pytest.mark.parametrize('deger', [float('inf'), float('nan')])
    def test_beyan_gecerli_json_uretir(self, client, uc, govde, deger):
        """Yankılanan değer RFC 8259 dışı belirteç basmamalı.

        ``Infinity`` / ``NaN`` belirteci tarayıcının ``JSON.parse``ını
        düşürür (deponun ihracat ailesinde ölçülmüş kusur sınıfı); beyan
        eklerken o sınıf geri getirilemez.
        """
        yanit = client.post(uc, json=dict(govde, chamber_temperature=deger))
        metin = yanit.get_data(as_text=True)
        assert 'Infinity' not in metin and 'NaN' not in metin, (
            'Gövdede RFC 8259 dışı sayısal belirteç var')
        json.loads(metin)  # katı ayrıştırıcı: patlarsa test kırmızı


# ---------------------------------------------------------------------------
# P16B2-11 — sayı-benzeri dize üç uçta da AYNI hükmü alır
# ---------------------------------------------------------------------------
class TestSayiBenzeriDize:

    @pytest.mark.parametrize('uc,govde,alan', [
        ('/calculate_solid', KATI_GEOMETRI, 'chamber_diameter'),
        ('/calculate_solid', KATI_GEOMETRI, 'chamber_pressure'),
        ('/calculate_solid', KATI_GEOMETRI, 'core_diameter'),
        ('/calculate_liquid', SIVI_GECERLI, 'thrust'),
        ('/calculate_liquid', SIVI_GECERLI, 'chamber_pressure'),
        ('/calculate_liquid', SIVI_GECERLI, 'mixture_ratio'),
    ])
    def test_dize_adli_ret_alir_ham_python_sizmaz(self, client, uc, govde,
                                                  alan):
        deger = str(govde[alan]) if alan in govde else '100'
        yanit = client.post(uc, json=dict(govde, **{alan: deger}))
        _adli_ret(yanit, alan)

    def test_kati_ve_kardesleri_ayni_hukmu_verir(self, client):
        """``thrust="1000"``: katıda 200 idi, sıvı/hibritte 400 (kaza kapı)."""
        kati = client.post('/calculate_solid',
                           json=dict(KATI_TASARIM_NOKTASI, thrust='1000'))
        sivi = client.post('/calculate_liquid',
                           json=dict(SIVI_GECERLI, thrust='1000'))
        hibrit = client.post('/calculate',
                             json=dict(HIBRIT_GECERLI, thrust='1000'),
                             headers={'Host': '127.0.0.1:8080'})
        siniflar = {kati.status_code // 100, sivi.status_code // 100,
                    hibrit.status_code // 100}
        assert siniflar == {4}, (
            'Aynı girdi sınıfı üç uçta üç farklı hüküm alıyor: %s'
            % [kati.status_code, sivi.status_code, hibrit.status_code])


# ---------------------------------------------------------------------------
# P16B2-13 — sayısal alan MANTIKSAL değer yutmaz
# ---------------------------------------------------------------------------
class TestYutulanBool:

    @pytest.mark.parametrize('deger', [True, False])
    def test_mixture_ratio_bool_reddedilir(self, client, deger):
        yanit = client.post('/calculate_liquid',
                            json=dict(SIVI_GECERLI, mixture_ratio=deger))
        govde = _adli_ret(yanit, 'mixture_ratio')
        assert govde['invalid_fields'][0]['reason'] == \
            'boolean_is_not_a_number', (
            'true ve false AYNI gerekçeyle reddedilmeli (biri banda düşüp '
            'geçiyordu): %s' % govde['invalid_fields'][0])

    @pytest.mark.parametrize('uc,govde,alan', [
        ('/calculate_solid', KATI_GEOMETRI, 'chamber_pressure'),
        ('/calculate_solid', KATI_GEOMETRI, 'chamber_diameter'),
        ('/calculate_solid', KATI_GEOMETRI, 'core_diameter'),
        ('/calculate_liquid', SIVI_GECERLI, 'thrust'),
    ])
    def test_sayisal_alan_bool_yutmaz(self, client, uc, govde, alan):
        yanit = client.post(uc, json=dict(govde, **{alan: True}))
        _adli_ret(yanit, alan)

    def test_yanit_sayisal_alanda_mantiksal_deger_basmaz(self, client):
        """Şema sözleşmesi: sayısal alan JSON boolean döndüremez."""
        govde = client.post('/calculate_liquid',
                            json=dict(SIVI_GECERLI)).get_json()
        for alan in ('mixture_ratio', 'thrust', 'chamber_pressure'):
            assert not isinstance(govde.get(alan), bool), (
                "'%s' yanıtta mantıksal değer taşıyor" % alan)
