"""ÖH Z5S / S1 — GÖVDE-TİP KAPISI bekçileri.

KAPATILAN SINIF
---------------
İstemci hatasının SUNUCU ARIZASINA çevrilmesi. Bir uç JSON gövdesi okuyorsa
ve istek ya yanlış taşıyıcıyla (``Content-Type`` yok / ``text/plain`` /
form-encoded) ya da yanlış TİPTE bir iç nesneyle geliyorsa, bu bir 4xx
istemci hatasıdır. Ölçüm öncesinde bunların büyük kısmı HTTP 500 idi ve
gövdede Werkzeug'ün ya da Python'un iç metni yer alıyordu.

ÖLÇÜM (27 Ağu 2026, ``docs/scofield/raw/OH/Z5S/s1/once_supurme.json``;
80 POST/PUT/PATCH ucu × 8 gövde vakası)
--------------------------------------------------------------------------
``Content-Type`` gönderilmediğinde (aynı tablo ``text/plain`` ve
form-encoded'da da birebir çıkıyor):

    HTTP 500 + gövdede "415 Unsupported Media Type: Did not attempt to
    load JSON data because the request Content-Type was not ..."   50 uç
    HTTP 400 ama gövdede yine aynı iç metin                          6 uç

500'lerin altısı YANLIŞ SUÇLU gösteriyordu — kullanıcı, başlığı unuttuğu
için ``NASA CEA Database Error``, ``PDF generation failed``,
``CAD generation failed``, ``CAD export error``, ``STL export failed`` ya da
``Chart PDF export failed`` okuyordu.

Buradaki bekçiler yedi kalemi kilitler:

* **P7B2-16 / P7B3-32 / P7B4-03** — merkezî kapı artık Content-Type
  ekseninde de kapanıyor: 415 ``unsupported_media_type``, beklenen ve
  alınan tip adlandırılmış. Bekçi ROTA LİSTESİNİ ELLE TUTMAZ: uygulamanın
  kendi ``url_map``\'ini gezer, yani ileride eklenen her POST ucu da bu
  sözleşmeye tabidir. Kapsam dışı kalanlar uygulamanın kendi
  ``_NON_JSON_BODY_ENDPOINTS`` kümesinde sayılıdır ve o kümenin GEREKÇESİ
  de ayrıca sınanır (ürünün gövdesiz POST ettiği uçlar hâlâ çalışıyor).
* **P16B4-22** — sözlük olmayan iç içe ``motor_data`` / ``results``
  üç CAD ucunda 500 yerine 422 ``invalid_export_geometry``.
* **P16B1-24** — ``/api/regression-analysis`` altı ham çöküşü adlı 422.
* **P16B3-22** — ``/api/fea/thermal`` ve ``/api/fea/structural`` artık TEK
  sözleşme uyguluyor; gövdenin kendisi imzasız hâlde "motor sonucu"
  sayılmıyor.
* **P16B4-26** — ``/api/`` altındaki eşleşmeyen yol ve yanlış metot JSON
  hata döndürüyor; sayfa rotalarının HTML 404'ü korunuyor.

BEKÇİNİN SINAMADIĞI
-------------------
Sayısal doğruluk. Bu dosya yalnız HATA SÖZLEŞMESİNİ kilitler. Sağlıklı
yolun bit-aynılığı ayrı ölçüldü (``taban_capa.json`` ↔ ``sonra_capa.json``:
dokuz çapa koşumunun 200 dönen yedisinde 0 farklı yaprak; fark yalnız
bilerek adlandırılan iki 400 gövdesinde).
"""

import json

import pytest

from hrma.app import (
    _NON_JSON_BODY_ENDPOINTS,
    app as flask_app,
)


# Ölçümde YANLIŞ SUÇLU olarak basılan altı metin. Hiçbiri bir taşıyıcı
# hatasının yanıtında görünmemeli.
YANLIS_SUCLULAR = (
    'NASA CEA Database Error',
    'PDF generation failed',
    'CAD generation failed',
    'CAD export error',
    'STL export failed',
    'Chart PDF export failed',
)

# Werkzeug'ün gövdeye sızan iç metninin imzası.
WERKZEUG_SIZINTISI = 'Did not attempt to load JSON data'

# Yer tutuculu rotalar için somut değerler (rota gezilirken kullanılır).
YER_TUTUCULAR = {
    '<motor_type>': 'liquid',
    '<report_type>': 'summary',
}


@pytest.fixture(scope='module')
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _govde_tasiyan_rotalar():
    """``url_map``\'ten gövde taşıyan somut rotalar: (yol, uç adı)."""
    cikti = []
    for kural in flask_app.url_map.iter_rules():
        metotlar = kural.methods - {'HEAD', 'OPTIONS'}
        if not (metotlar & {'POST', 'PUT', 'PATCH'}):
            continue
        yol = str(kural.rule)
        for anahtar, deger in YER_TUTUCULAR.items():
            yol = yol.replace(anahtar, deger)
        if '<' in yol:          # eşleyemediğimiz dönüştürücü: atla
            continue
        cikti.append((yol, kural.endpoint))
    return sorted(cikti)


KAPILI_ROTALAR = [(y, u) for y, u in _govde_tasiyan_rotalar()
                  if u not in _NON_JSON_BODY_ENDPOINTS]
MUAF_ROTALAR = [(y, u) for y, u in _govde_tasiyan_rotalar()
                if u in _NON_JSON_BODY_ENDPOINTS]


# ===========================================================================
# P7B2-16 / P7B3-32 / P7B4-03 — taşıyıcı ekseni
# ===========================================================================
class TestTasiyiciKapisi:
    """JSON bekleyen her uç, JSON olmayan gövdeye adlı 415 döner."""

    @pytest.mark.parametrize('baslik', [
        None,
        'text/plain',
        'application/x-www-form-urlencoded',
    ], ids=['content_type_yok', 'text_plain', 'form_encoded'])
    @pytest.mark.parametrize('yol,uc', KAPILI_ROTALAR,
                             ids=[u for _, u in KAPILI_ROTALAR])
    def test_json_olmayan_tasiyici_415(self, client, yol, uc, baslik):
        basliklar = {'Content-Type': baslik} if baslik else {}
        r = client.post(yol, data=b'{"motor_name":"x"}', headers=basliklar)

        assert r.status_code == 415, (
            f'{yol} ({uc}) taşıyıcı hatasına {r.status_code} döndü; '
            f'gövde: {r.get_data(as_text=True)[:200]}')
        govde = r.get_json()
        assert govde is not None, f'{yol}: 415 gövdesi JSON değil'
        assert govde['status'] == 'error'
        assert govde['error'] == 'unsupported_media_type'
        # Alan adı + neden taşınır; değer uydurulmaz.
        assert govde['expected_content_type'] == 'application/json'
        assert govde['received_content_type'] == baslik

        ham = r.get_data(as_text=True)
        assert WERKZEUG_SIZINTISI not in ham, (
            f'{yol}: Werkzeug iç metni hâlâ gövdede')
        for suclu in YANLIS_SUCLULAR:
            assert suclu not in ham, f'{yol}: yanlış suçlu "{suclu}" basıldı'

    def test_hicbir_ucta_500_kalmadi(self, client):
        """Taşıyıcı hatası HİÇBİR uçta sunucu arızası sınıfına düşmüyor."""
        kalanlar = []
        for yol, uc in KAPILI_ROTALAR:
            r = client.post(yol, data=b'')
            if r.status_code >= 500:
                kalanlar.append((yol, uc, r.status_code))
        assert kalanlar == [], f'taşıyıcı hatası 5xx veren uçlar: {kalanlar}'

    def test_muafiyet_listesi_gerekcesiyle_yasiyor(self, client):
        """Muaf uçlar GERÇEKTEN gövdesiz/JSON olmayan çağrıyı kabul ediyor.

        Muafiyetin iki gerekçesi vardı ve ikisi de ölçülmüştü: ya ucun kendi
        taşıyıcısı var (multipart / text-csv), ya da ÜRÜNÜN KENDİ JS'i
        Content-Type göndermeden POST ediyor. Bekçi listeyi boş bir küme
        olarak kabul etmez ve muaf uçların 415 ALMADIĞINI doğrular — yani
        muafiyet kaldırılırsa ürünün beş düğmesi kırılacağı burada görünür.
        """
        assert MUAF_ROTALAR, 'muafiyet listesi rotalarla eşleşmiyor'
        for yol, uc in MUAF_ROTALAR:
            if uc == 'correlation_report':
                continue        # ağır korelasyon koşusu; sözleşme aşağıda
            r = client.post(yol, data=b'')
            assert r.status_code != 415, (
                f'{yol} ({uc}) muaf olmasına rağmen 415 aldı')
        assert 'correlation_report' in _NON_JSON_BODY_ENDPOINTS

    def test_urunun_govdesiz_post_ettigi_ucler_muaf(self):
        """Ölçülen beş çağrı (``fetch(..., {method:'POST'})``) listede.

        Kaynak taraması: update_check.js (üç uç), user_guide.js,
        launch_site.html. Bu uçlardan biri listeden düşerse ürünün düğmesi
        415 alır; bekçi o düşüşü yakalar.
        """
        for uc in ('update_download', 'update_install', 'update_open_download',
                   'user_guide_open', 'tile_cache_clear'):
            assert uc in _NON_JSON_BODY_ENDPOINTS, uc

    def test_kendi_tasiyicisi_olan_ucler_muaf(self, client):
        """text/csv gövdesi hâlâ okunuyor (``/api/validation/upload-csv``)."""
        r = client.post('/api/validation/upload-csv',
                        data=b'time,thrust\n0,0\n1,100\n2,0\n',
                        headers={'Content-Type': 'text/csv'})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert r.get_json()['parsed']['n_points'] == 3

    def test_json_tasiyicisiyla_gelen_bozuk_govde_hala_400(self, client):
        """Taşıyıcı ekseni, eski gövde ekseninin yerine GEÇMEZ."""
        for ham, kod in ((b'', 'empty_json_body'),
                         (b'{"a":', 'malformed_json_body'),
                         (b'[1,2,3]', 'body_not_an_object'),
                         (b'42', 'body_not_an_object')):
            r = client.post('/calculate', data=ham,
                            headers={'Content-Type': 'application/json'})
            assert r.status_code == 400, ham
            assert r.get_json()['error'] == kod, ham

    def test_get_istekleri_kapiya_ugramaz(self, client):
        """Kapı yalnız gövde taşıyan metotlarda çalışır."""
        r = client.get('/')
        assert r.status_code == 200


# ===========================================================================
# P16B4-22 — iç içe taşıyıcının tipi
# ===========================================================================
class TestIcIceGeometriTipi:
    """``motor_data`` / ``results`` sözlük değilse 500 değil adlı 422."""

    @pytest.mark.parametrize('yol,alan,deger', [
        ('/api/export-cad', 'motor_data', [1, 2, 3]),
        ('/api/export-cad', 'motor_data', 'x'),
        ('/api/export-cad', 'motor_data', None),
        ('/export_solid_motor_cad', 'motor_data', [1, 2, 3]),
        ('/export_solid_motor_cad', 'results', [1, 2, 3]),
        ('/export_liquid_cad', 'motor_data', [1, 2, 3]),
        ('/export_liquid_cad', 'results', 'x'),
    ])
    def test_sozluk_olmayan_tasiyici_422(self, client, yol, alan, deger):
        r = client.post(yol, json={alan: deger})
        assert r.status_code == 422, (
            f'{yol} {alan}={deger!r} -> {r.status_code}; '
            f'{r.get_data(as_text=True)[:200]}')
        govde = r.get_json()
        assert govde['error'] == 'invalid_export_geometry'
        kusurlu = govde['invalid_fields']
        assert kusurlu[0]['field'] == alan
        assert kusurlu[0]['reason'] == 'not_an_object'
        assert kusurlu[0]['received_type'] == type(deger).__name__
        # Ham Python metni sızmıyor.
        ham = r.get_data(as_text=True)
        assert 'has no attribute' not in ham
        assert 'CAD export error' not in ham

    def test_saglikli_geometri_hala_uretiliyor(self, client):
        """Kapı GEÇERLİ gövdeyi engellemiyor (bit-aynılık çapası)."""
        r = client.post('/api/export-cad', json={
            'motor_data': {'chamber_diameter': 0.1, 'chamber_length': 0.5,
                           'throat_diameter': 0.03, 'exit_diameter': 0.09,
                           'motor_name': 'CAPA-1'},
            'formats': ['technical_drawings'],
        })
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert r.get_json()['status'] == 'success'


# ===========================================================================
# P16B1-24 — /api/regression-analysis altı ham çöküşü
# ===========================================================================
class TestRegresyonGirdiKapisi:
    """Ölçülen altı 500'ün altısı da adlandırılmış 422'ye çevrildi."""

    @pytest.mark.parametrize('deger', [None, [1, 2, 3], 'x', 42, True],
                             ids=['null', 'liste', 'dize', 'sayi', 'bool'])
    def test_motor_data_sozluk_degilse_422(self, client, deger):
        r = client.post('/api/regression-analysis', json={'motor_data': deger})
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        govde = r.get_json()
        assert govde['error'] == 'invalid_motor_data'
        assert govde['invalid_fields'][0]['field'] == 'motor_data'
        assert govde['invalid_fields'][0]['reason'] == 'not_an_object'
        assert 'has no attribute' not in r.get_data(as_text=True)

    @pytest.mark.parametrize('alan,deger,neden', [
        ('burn_time', '10', 'not_a_number'),
        ('burn_time', True, 'not_a_number'),
        ('mdot_ox', [1], 'not_a_number'),
        ('burn_time', float('nan'), 'not_finite'),
        ('regression_a', float('inf'), 'not_finite'),
        ('port_diameter_initial', 0, 'not_positive'),
        ('port_diameter_initial', -0.01, 'not_positive'),
    ])
    def test_alan_tipi_ve_bandi(self, client, alan, deger, neden):
        r = client.post('/api/regression-analysis',
                        json={'motor_data': {alan: deger}})
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        govde = r.get_json()
        assert govde['error'] == 'invalid_regression_input'
        kusur = {k['field']: k for k in govde['invalid_fields']}
        assert alan in kusur, govde['invalid_fields']
        assert kusur[alan]['reason'] == neden
        ham = r.get_data(as_text=True)
        assert 'ufunc' not in ham
        assert 'division by zero' not in ham

    #: ÖH D15 birleştirme (1 Eyl 2026) — UCUN SÖZLEŞMESİ SIKILAŞTI.
    #: Yapısal kulvar (P5B4-01/-38) eğriyi YÖNETEN alanları zorunlu kıldı:
    #: ``burn_time`` / ``mdot_ox`` / ``port_diameter_initial`` ve
    #: ``fuel_type`` yoksa uç 422 verir, varsayılan uydurmaz. Kapı
    #: FAIL-CLOSED'dır ve kazanır. Aşağıdaki S1 bekçilerinin İDDİALARI
    #: (ham 500 yok; açık null "verilmedi" sayılır ve adıyla yazılır;
    #: sağlıklı gövde bit-aynı kalır) DEĞİŞMEDİ — yalnız gövdeleri yeni
    #: sözleşmeye taşındı, çünkü eski gövdeler artık kapıya takılıyor ve
    #: iddianın ölçtüğü dala hiç ulaşmıyordu.
    TAM_GOVDE = {'burn_time': 10.0, 'mdot_ox': 0.38,
                 'port_diameter_initial': 0.037, 'fuel_type': 'htpb'}

    def test_asiri_katsayi_ham_overflow_yerine_422(self, client):
        """``regression_n=1e9`` ham ``(34, 'Result too large')`` veriyordu.

        BANT KONMADI (yeni eşik icat etmek Berke kararı): yalnız istemci
        hatası olduğu adlandırılıyor ve işleme giren alanlar sayılıyor.

        ÖH D15: katsayı ARTIK TEK BAŞINA gönderilemez (zorunlu alan kapısı
        önce ateşlenir ve taşma dalına hiç inilmezdi). Gövde tamamlandı;
        ölçülen kusurun kendisi — taşmanın ham 500 yerine ADLI 422 olması —
        aynen sınanıyor.

        ÖH D20 / P5B4-05 — BU İDDİA ÇEVRİLDİ. Ölçülen kusur (ham 500
        yerine ADLI 422, ``regression_n`` işleme giren alanlar arasında)
        AYNEN sınanmaya devam ediyor; değişen yalnız RET SINIFIDIR ve yeni
        sınıf daha kesindir: eskiden yanıt "sonuç temsil edilemiyor"
        (``regression_result_not_representable``) diyerek suçu SONUCA
        atıyordu, artık hatalı ALANI adıyla söylüyor
        (``non_physical_regression_input`` / ``regression_n``).

        ``regression_n`` artık ``REGRESSION_EXPONENT_VALID = (0, 1)``
        bandına bağlı. Bu bant "yeni eşik" değil KORELASYONUN TANIMIDIR
        (``r = a·G^n`` difüzyon-limitli hibrit regresyonunda n > 0 zorunlu;
        n > 1 ise regresyon akıdan HIZLI büyür). ÖH D26 / OH-D25-15: bant
        ASİMETRİKTİR — alt uç dışlayıcı, üst uç KAPSAYICI; n = 1,0 tam
        değeri (akıyla tam orantılı, nötr sınır) KABUL edilir, n > 1
        reddedilir. Bu iddianın ölçtüğü ``1e9`` her iki tanımda da dışarıdadır. Gerekçenin tamamı
        ``tests/test_d16_yapisal_sistem_a1.py``deki
        ``test_regresyon_usu_n_TANIM_bandiyla_reddedilir`` docstring'inde.
        Ham taşma dalı (``OverflowError`` -> 422) SÖKÜLMEDİ; ``regression_a``
        üst uçtan bantsız olduğu için hâlâ ulaşılabilir.
        """
        r = client.post('/api/regression-analysis',
                        json={'motor_data': dict(self.TAM_GOVDE,
                                                 regression_n=1e9)})
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        govde = r.get_json()
        assert govde['error'] == 'non_physical_regression_input'
        assert any(k['field'] == 'regression_n'
                   for k in govde['invalid_fields']), govde
        ham = r.get_data(as_text=True)
        assert 'Result too large' not in ham
        assert 'Traceback' not in ham

    def test_acik_null_verilmedi_sayilir_ve_beyan_edilir(self, client):
        """Açık ``null`` 500 üretmez; "verilmedi" sayılır ve ADIYLA yazılır.

        İki ayak ayrı ayrı ölçülür, çünkü ÖH D15'ten sonra "verilmedi"nin
        SONUCU alanın zorunlu olup olmamasına bağlı:

        * ZORUNLU alanda null -> 422, ama ret gövdesi de alanın neden yok
          sayıldığını ADIYLA söyler (sessiz düşüş yok, ham 500 yok).
        * YÖNETMEYEN alanda null -> 200, ``inputs_treated_as_absent`` +
          ``defaults_applied``.
        """
        r = client.post('/api/regression-analysis',
                        json={'motor_data': dict(self.TAM_GOVDE,
                                                 burn_time=None,
                                                 mdot_ox=None)})
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        govde = r.get_json()
        assert govde['error'] == 'incomplete_regression_input'
        assert set(govde['inputs_treated_as_absent']) == {'burn_time',
                                                          'mdot_ox'}
        assert set(govde['missing_fields']) == {'burn_time', 'mdot_ox'}
        assert 'NoneType' not in r.get_data(as_text=True)

        r2 = client.post('/api/regression-analysis',
                         json={'motor_data': dict(self.TAM_GOVDE,
                                                  port_diameter_final=None)})
        assert r2.status_code == 200, r2.get_data(as_text=True)[:200]
        g2 = r2.get_json()
        assert g2['status'] == 'success'
        assert g2['inputs_treated_as_absent'] == ['port_diameter_final']
        assert {b['field'] for b in g2['defaults_applied']} == {
            'port_diameter_final'}

    def test_saglikli_yolda_beyan_alani_YOK(self, client):
        """Düşüş yoksa alan da yok — sağlıklı gövde bit-aynı kalır."""
        r = client.post('/api/regression-analysis', json={'motor_data': {
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'throat_diameter': 0.03, 'exit_diameter': 0.09,
            'motor_name': 'CAPA-1', 'chamber_pressure': 20.0,
            'burn_time': 10.0, 'mdot_ox': 0.38,
            'port_diameter_initial': 0.05, 'port_diameter_final': 0.08,
            'fuel_type': 'htpb',
        }})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        govde = r.get_json()
        assert 'inputs_treated_as_absent' not in govde
        assert 'defaults_applied' not in govde


# ===========================================================================
# P16B3-22 — FEA uçlarında TEK sözleşme
# ===========================================================================
class TestFeaMotorSecimSozlesmesi:
    """Gövdenin kendisi, motor imzası taşımadıkça "motor sonucu" değildir."""

    OLCULEN_200_LER = [
        {'motor': None},
        {'ambient_temperature_K': 300},
        {'motor_results': 0},
        {'motor_results': 'x'},
    ]

    @pytest.mark.parametrize('yol', ['/api/fea/thermal', '/api/fea/structural'])
    @pytest.mark.parametrize('govde', OLCULEN_200_LER + [
        {}, {'motor_results': {}},
    ])
    def test_tek_sozlesme(self, client, yol, govde):
        """Altı vakanın hepsi AYNI adlandırılmış reddi alır.

        Ölçüm öncesi ayrım keyfîydi: ``{}`` ve ``{'motor_results': {}}``
        400 alırken ``{'motor': null}`` 200 alıyor ve GÖVDENİN TAMAMI motor
        sonucu sayılıyordu.
        """
        r = client.post(yol, json=govde)
        assert r.status_code == 400, r.get_data(as_text=True)[:200]
        yanit = r.get_json()
        assert yanit['status'] == 'error'
        assert yanit['error'] == 'missing_motor_results'
        assert yanit['checked_fields'] == ['motor_results', 'motor', 'results']

    @pytest.mark.parametrize('yol', ['/api/fea/thermal', '/api/fea/structural'])
    def test_adi_konmus_alandaki_sozluk_adli_red_aliyor(self, client, yol):
        """Belgelenen sözleşmenin ikinci yarısı korunur.

        Motor sözlüğü VAR ama alanları eksikse köprü NOT_MODELLED üretir;
        hiçbir sayı uydurulmaz. P16B3-22'nin konusu 400 ⟷ 200 ayrımının
        KEYFÎLİĞİYDİ (gövdenin boş olup olmamasına bağlıydı) ve o ayrım
        burada hâlâ sınanıyor: ADI KONMUŞ alandaki sözlük "motor sözlüğü
        yok" (400) reddini ALMAZ.

        OH-D17-07 (ÖH D22): ``/api/fea/thermal`` için bu satır eskiden
        ``200 + status='success'`` diyordu ve kusuru KORUYORDU — köprü
        NOT_MODELLED derken zarf "başarılı" diyordu (ölçüldü, taban
        b84b10a: 5/5 vaka, ``once_oh_d17_07.json``). Zarfın hükmü artık
        köprünün hükmüdür: girdi eksikliği düzeltilebilir bir çağıran
        kusurudur → 422 + ``status='not_modelled'``.
        ``/api/fea/structural`` aynı kusuru taşır ama bu dalgada BAŞKA
        kulvarın kalemidir; sözleşmesi bilerek değiştirilmedi ve eski
        beklenti burada aynen sınanmaya devam eder.
        """
        r = client.post(yol, json={'motor_results': {'chamber_pressure': 20.0}})
        govde = r.get_json()
        if yol == '/api/fea/thermal':
            assert r.status_code == 422, r.get_data(as_text=True)[:200]
            assert govde['status'] == 'not_modelled'
            assert govde['fea']['status'] == 'NOT_MODELLED'
            assert govde['missing'], 'eksiğin adı söylenmiyor'
        else:
            assert r.status_code == 200, r.get_data(as_text=True)[:200]
            assert govde['status'] == 'success'

    def test_docstring_kod_ile_ayni_seyi_soyluyor(self):
        """Belge-davranış sapması kapandı (kalemin çekirdeği)."""
        from hrma.app import api_fea_thermal
        belge = api_fea_thermal.__doc__
        assert 'missing_motor_results' in belge
        assert 'axial_profile' in belge      # eski sözleşme çapaları korunur
        assert 'ZORUNLUDUR' in belge


# ===========================================================================
# P16B4-26 — /api/ altında tek hata sözleşmesi
# ===========================================================================
class TestApiHataSozlesmesi:
    @pytest.mark.parametrize('yol', [
        '/api/projects/load/../../etc/passwd',
        '/api/projects/load/a/b',
        '/api/hic_boyle_bir_uc_yok',
    ])
    def test_eslesmeyen_api_yolu_json_404(self, client, yol):
        r = client.get(yol)
        assert r.status_code == 404
        govde = r.get_json()
        assert govde is not None, r.get_data(as_text=True)[:120]
        assert govde['error'] == 'endpoint_not_found'
        assert govde['status'] == 'error'

    def test_yanlis_metot_json_405(self, client):
        r = client.get('/api/export-cad')
        assert r.status_code == 405
        govde = r.get_json()
        assert govde['error'] == 'method_not_allowed'
        assert 'POST' in govde['allowed_methods']

    def test_var_olan_proje_ucunun_kendi_kapilari_bozulmadi(self, client):
        """Rotaya EŞLEŞEN adlar kendi sözleşmesinde kalır."""
        r = client.get('/api/projects/load/..')
        assert r.status_code == 400
        assert r.get_json() is not None
        r = client.get('/api/projects/load/yok_boyle')
        assert r.status_code == 404
        assert r.get_json() is not None

    def test_sayfa_rotalari_hala_html(self, client):
        """``/api/`` dışındaki 404 HTML kalır — kapı dar tutuldu."""
        r = client.get('/hic_boyle_bir_sayfa_yok')
        assert r.status_code == 404
        with pytest.raises(Exception):
            json.loads(r.get_data(as_text=True))
