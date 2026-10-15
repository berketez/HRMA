"""ÖH Z5S / S7 — İHRACAT AİLESİNİN KAPI SÖZLEŞMESİ bekçileri.

KAPATILAN SINIF
---------------
"Hangi hükmü alacağın girdinin FİZİĞİNE değil UCUN KİMLİĞİNE bağlı." İhracat
ailesinin on beş üyesi aynı girdi sınıfına üç farklı cevap veriyordu: bir
kısmı adlı 422, bir kısmı ham 500, bir üyesi de sessiz 200 + indirilebilir
imalat dosyası.

ÖLÇÜM (28 Ağustos 2026, ``docs/scofield/raw/OH/Z5S/s7/once_supurme.json`` ↔
``sonra_supurme.json``; 15 uç × 19 sarsım = 285 hücre)
--------------------------------------------------------------------------
=================================  =====  =====
ölçüt                              önce   sonra
=================================  =====  =====
5xx dönen hücre                       68      6
geçersiz girdiye HTTP 200             59      0
=================================  =====  =====

Kalan altı 5xx'in tamamı TEK sarsım sınıfıdır (``chamber_diameter=1e-9``,
yani sonlu ama dejenere 1 nanometrelik kamara: geometri çekirdeği çöküyor).
O bir ÜRETİCİ dayanıklılığı kalemidir, kapı kalemi değil; bu turda
DEĞİŞMEDİ ve raporda ayrıca bildirildi.

Bu dosyanın kilitlediği kalemler
--------------------------------
* **P16B4-01 (KRİTİK)** — ``/api/export-cad`` kapısızdı. ÖLÇÜLDÜ:
  ``{'formats': ['technical_drawings']}`` gövdesi (hiç geometri yok) HTTP
  200 ve ``motor_name: "UZAYTEK-HRM-001"`` döndürüyordu; ``formats``
  içeriğine göre teknik resim / malzeme listesi / 3B model, ``stl``
  istendiğinde de dosya iniyordu — hepsi ŞABLON motorun.
* **P16B4-21** — aile envanteri: yukarıdaki matris.
* **P16B4-19** — gerekçeli istemci hatası 5xx ile veriliyordu
  (``/api/export-eng``, ``-openrocket``, ``-simulation``,
  ``/api/generate-complete-package``). Ret İÇERİĞİ doğruydu, taşıyıcı
  yanlıştı; izleme katmanları 5xx'i sunucu arızası sayar.
* **P16B4-18** — ``/api/detailed-cad/liquid`` gövdeye ÇIPLAK ``NaN``
  belirteci yazıyordu (``{"chamber_diameter": NaN}``): RFC 8259 dışı, yani
  tarayıcıda ``response.json()`` patlar. Ayrıca boş gövde 200 + 155.858 B
  şablon motor veriyordu.
* **P16B4-17** — ``/export_tank_cad`` ret gövdesinde Python sözlük anahtarı
  sızdırıyordu ("CAD export error: 'dimensions'") ve beklediği yapıyı hiç
  söylemiyordu.
* **P7B2-19 / P7B3-05** — ``/api/export-eng``, ``-openrocket``,
  ``-simulation`` dosya adını ``safe_name``'den geçirmiyordu.
* **P16B4-27** — ``/api/export-xlsx`` temizlenmiş sayfa adı ``..`` ile
  başlayabiliyordu.
* **P9B2-20 (F2a şartı)** — ``app._step_readme_text`` sabit metinle her
  koşuda dört parçayı sayıyordu.
* **P9B3-10 (F2a şartı)** — ``_get_motor_class(... , 10000)`` hayalet
  varsayılanı.
* **P9B3-09 (KRİTİK)** — katı sayfasının "Complete Report"unda yönetici
  özeti 4/4 ve performans tablosu 7/7 "N/A" basıyordu.

BEKÇİNİN SINAMADIĞI
-------------------
Sayısal doğruluk ve üretilen katının geometrisi. Bu dosya yalnız KAPI
SÖZLEŞMESİNİ ve BESLEME SÖZLEŞMESİNİ kilitler. Geçerli gövdenin
bit-aynılığı ayrı ölçüldü (``once_capa.json`` ↔ ``sonra_capa.json``:
36 çapa vakasının 29'u bit-aynı; farklı olan 7'sinin tamamı bu paketin
BEYANLI değişiklikleridir ve hepsi ihracat ailesindedir).
"""

import io
import json
import math

import pytest

from hrma.app import (
    _build_pdf_analysis_sections,
    _build_pdf_motor_data,
    _safe_sheet_title,
    _step_readme_text,
    app as flask_app,
)

NAN = float('nan')
INF = float('inf')

#: İmalata uygun geometri — kapı bunu ENGELLEMEMELİ (fazla agresif kapı da
#: bir kusurdur; ölçüm bunu ayrıca çapalıyor).
IYI_GEOMETRI = {
    'motor_name': 'S7-BEKCI',
    'motor_type': 'hybrid',
    'chamber_diameter': 100.0,
    'chamber_length': 500.0,
    'throat_diameter': 25.0,
    'exit_diameter': 60.0,
    'expansion_ratio': 5.76,
    'chamber_pressure': 20.0,
    'thrust': 1000.0,
    'burn_time': 10.0,
    'total_impulse': 10000.0,
    'specific_impulse': 220.0,
    'propellant_mass': 5.0,
}

#: Kapının aynı hükmü vermesi gereken uçlar (``motor_data`` sarmalı).
SARMALI_UCLAR = (
    '/api/export-cad',
    '/api/export-step',
    '/api/export-dxf',
    '/api/export-drawings-pdf',
    '/api/export-stl-zip',
    '/api/export-complete-zip',
    '/api/export-eng',
    '/api/export-openrocket',
    '/api/export-simulation',
)

#: Gövdeyi DÜZ okuyan uçlar (``liquid.html`` düz sözlük yollar).
DUZ_UCLAR = ('/api/detailed-cad/liquid', '/api/detailed-cad/solid')


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _post_ham(client, yol, govde):
    """NaN taşıyan gövde ``json=`` ile değil elle serileştirilir.

    ``json=`` yolu da NaN yazar ama açıkça serileştirmek, sınanan şeyin
    "gövdede gerçekten ham NaN vardı" olduğunu görünür kılar.
    """
    return client.post(yol, data=json.dumps(govde),
                       content_type='application/json')


# ===========================================================================
# P16B4-01 (KRİTİK) — /api/export-cad kapısı
# ===========================================================================
class TestExportCadKapisi:
    """Geometrisiz istekten imalat çıktısı ÜRETİLMEZ."""

    @pytest.mark.parametrize('formats', [
        ['technical_drawings'], ['materials'], ['3d_plot'], ['stl'], [],
        ['stl', 'technical_drawings'],
    ], ids=['cizim', 'malzeme', 'plot3d', 'stl', 'bos-liste', 'varsayilan'])
    def test_bos_govde_hicbir_formatta_uretmiyor(self, client, formats):
        """ÖLÇÜLDÜ (onarım öncesi): ilk üç format 200 + ŞABLON motor."""
        r = client.post('/api/export-cad', json={'formats': formats})
        assert r.status_code == 422, (
            f'formats={formats} -> {r.status_code}; '
            f'{r.get_data(as_text=True)[:200]}')
        govde = r.get_json()
        assert govde['error'] == 'missing_export_geometry'
        # Şablon motorun adı gövdeye SIZMAMALI.
        assert 'HRMA-001' not in r.get_data(as_text=True)

    def test_sablon_motor_adi_artik_donmuyor(self, client):
        r = client.post('/api/export-cad', json={'motor_data': {},
                                                 'formats': ['materials']})
        assert r.status_code == 422
        assert 'cad_exports' not in (r.get_json() or {})

    def test_gecerli_geometri_hala_200(self, client):
        """Kapı fazla agresif OLMAMALI."""
        r = client.post('/api/export-cad', json={
            'motor_data': dict(IYI_GEOMETRI),
            'formats': ['technical_drawings']})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert r.get_json()['status'] == 'success'


# ===========================================================================
# P16B4-21 — aile TEK sözleşme
# ===========================================================================
class TestAileTekSozlesme:
    """Aynı girdi sınıfı = aynı hüküm, ucun kimliğinden BAĞIMSIZ."""

    @pytest.mark.parametrize('yol', SARMALI_UCLAR)
    def test_sonlu_olmayan_olcu_her_ucta_422(self, client, yol):
        r = _post_ham(client, yol,
                      {'motor_data': dict(IYI_GEOMETRI,
                                          chamber_diameter=INF)})
        assert r.status_code == 422, (
            f'{yol} sonsuz çapa {r.status_code} döndü; '
            f'{r.get_data(as_text=True)[:200]}')
        assert r.get_json()['error'] == 'invalid_export_geometry'

    @pytest.mark.parametrize('yol', SARMALI_UCLAR)
    def test_metin_nan_her_ucta_422(self, client, yol):
        """ÖLÇÜLDÜ: gerçek Infinity 422 alırken metin "NaN" 500 alıyordu."""
        r = client.post(yol, json={'motor_data': dict(IYI_GEOMETRI,
                                                      chamber_diameter='NaN')})
        assert r.status_code == 422, (
            f'{yol} metin NaN -> {r.status_code}; '
            f'{r.get_data(as_text=True)[:200]}')

    @pytest.mark.parametrize('yol', SARMALI_UCLAR)
    def test_bool_olcu_her_ucta_422(self, client, yol):
        """``true`` bir ölçü değildir; ``float(True) == 1.0`` sessizce
        1 METRELİK kamara üretiyordu (ölçüldü: /api/export-stl, 288 KB)."""
        r = client.post(yol, json={'motor_data': dict(IYI_GEOMETRI,
                                                      chamber_diameter=True)})
        assert r.status_code == 422, (
            f'{yol} bool çapa {r.status_code} döndü')

    @pytest.mark.parametrize('yol', SARMALI_UCLAR)
    def test_bos_geometri_her_ucta_422(self, client, yol):
        r = client.post(yol, json={'motor_data': {}})
        assert r.status_code == 422, (
            f'{yol} boş geometriye {r.status_code} döndü')

    @pytest.mark.parametrize('yol', SARMALI_UCLAR)
    @pytest.mark.parametrize('deger', [[1, 2, 3], 'x', None, 42],
                             ids=['liste', 'dize', 'null', 'sayi'])
    def test_sozluk_olmayan_tasiyici_her_ucta_422(self, client, yol, deger):
        r = client.post(yol, json={'motor_data': deger})
        assert r.status_code == 422, (
            f'{yol} motor_data={deger!r} -> {r.status_code}')
        ham = r.get_data(as_text=True)
        assert 'has no attribute' not in ham, 'ham Python metni sızdı'
        assert 'Traceback' not in ham

    @pytest.mark.parametrize('yol', SARMALI_UCLAR)
    def test_5xx_kalmadi(self, client, yol):
        """Sarsım kümesinin tamamında sunucu arızası kodu YOK."""
        sarsimlar = [
            {}, dict(IYI_GEOMETRI, chamber_diameter=NAN),
            dict(IYI_GEOMETRI, chamber_length=NAN),
            dict(IYI_GEOMETRI, throat_diameter=INF),
            dict(IYI_GEOMETRI, chamber_diameter=-INF),
            dict(IYI_GEOMETRI, chamber_diameter='abc'),
            {'chamber_diameter': None, 'chamber_length': None,
             'throat_diameter': None},
            {'chamber_diameter': '', 'chamber_length': '',
             'throat_diameter': ''},
            {'chamber_diameter': 0.0, 'chamber_length': 0.0,
             'throat_diameter': 0.0},
        ]
        for md in sarsimlar:
            r = _post_ham(client, yol, {'motor_data': md})
            assert r.status_code < 500, (
                f'{yol} {list(md)[:3]} -> {r.status_code}; '
                f'{r.get_data(as_text=True)[:200]}')


# ===========================================================================
# P16B4-19 — gerekçeli istemci hatası 4xx taşıyıcıyla
# ===========================================================================
class TestOpenRocketRetTasiyicisi:
    """``OpenRocketExportDataError`` 500 değil 422 ile verilir."""

    #: İYİ geometri ama ``propellant_mass`` yok: .eng üretilemez, ret DOĞRU.
    #: Ölçüldü — bu gövde 19/19 vakada 500 alıyordu.
    EKSIK_KUTLE = {k: v for k, v in IYI_GEOMETRI.items()
                   if k != 'propellant_mass'}

    @pytest.mark.parametrize('yol', ['/api/export-eng',
                                     '/api/export-openrocket',
                                     '/api/export-simulation'])
    def test_iyi_geometri_eksik_alan_422(self, client, yol):
        r = client.post(yol, json={'motor_data': dict(self.EKSIK_KUTLE)})
        assert r.status_code == 422, (
            f'{yol} -> {r.status_code}; {r.get_data(as_text=True)[:200]}')
        govde = r.get_json()
        assert govde['error'] == 'missing_export_data'
        # Ret İÇERİĞİ korunur (mevcut bekçiler ve arayüz bu metni okuyor).
        assert 'NOT generated' in govde['message']
        # Makine-okur alanlar KAZANILDI.
        assert 'propellant_mass' in govde['missing_fields']
        assert govde['field_reasons'].get('propellant_mass')

    def test_complete_package_da_ayni_tasiyici(self, client):
        r = client.post('/api/generate-complete-package', json={
            'motor_data': dict(self.EKSIK_KUTLE),
            'package_options': {'include_cad': False,
                                'include_openrocket': True,
                                'include_analysis': False,
                                'include_manufacturing': False}})
        assert r.status_code == 422
        assert r.get_json()['error'] == 'missing_export_data'

    def test_analiz_only_paket_geometri_istemez(self, client):
        """Kapı YALNIZ imalat bölümü istendiğinde geometri arar."""
        r = client.post('/api/generate-complete-package', json={
            'motor_data': {'motor_name': 'BARE', 'chamber_pressure': 30.0},
            'package_options': {'include_cad': False,
                                'include_openrocket': False,
                                'include_analysis': True,
                                'include_manufacturing': False}})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]


# ===========================================================================
# P16B4-18 — RFC 8259 dışı gövde + kapısız detaylı CAD
# ===========================================================================
class TestDetayliCadGovdesi:

    DUZ_IYI = {'motor_name': 'S7-DUZ', 'chamber_diameter': 100.0,
               'chamber_length': 500.0, 'throat_diameter': 25.0,
               'exit_diameter': 60.0, 'nozzle_length': 150.0}

    @pytest.mark.parametrize('yol', DUZ_UCLAR)
    def test_nan_govdeye_ciplak_yazilmiyor(self, client, yol):
        r = _post_ham(client, yol, dict(self.DUZ_IYI, chamber_diameter=NAN))
        ham = r.get_data(as_text=True)
        # RFC 8259: NaN/Infinity JSON belirteci DEĞİLDİR.
        assert 'NaN' not in ham, f'{yol}: gövdede çıplak NaN belirteci var'
        assert 'Infinity' not in ham
        # Tarayıcının yaptığı iş: gövdeyi katı JSON olarak çözmek.
        json.loads(ham)
        assert r.status_code == 422
        assert r.get_json()['error'] == 'invalid_export_geometry'

    @pytest.mark.parametrize('yol', DUZ_UCLAR)
    def test_bos_govde_sablon_motor_cizmiyor(self, client, yol):
        """ÖLÇÜLDÜ: boş gövde 200 + 155.858 B üreteç varsayılanı."""
        r = client.post(yol, json={})
        assert r.status_code == 422, (
            f'{yol} boş gövdeye {r.status_code} döndü, '
            f'{len(r.get_data())} bayt')
        assert r.get_json()['error'] == 'missing_export_geometry'

    @pytest.mark.parametrize('yol', DUZ_UCLAR)
    def test_gecerli_govde_hala_ciziliyor(self, client, yol):
        """ÖH D16/kati (P16B4-06) — İDDİA YER DEĞİŞTİRDİ, ZAYIFLAMADI.

        Bu test eskiden İKİ uç için de ``200 + status == 'success'`` şart
        koşuyordu ve bununla P16B4-06'nın kusurunu KİLİTLİYORDU: katı
        üretici (``cad_visualization.generate_solid_motor_cad``) bir
        taslaktır ve ÜRETTİĞİ FİGÜRÜN İZ SAYISI 0'dır (ölçüldü:
        ``docs/scofield/raw/OH/D16/kati/a1/once.json``, P16B4-06 —
        beş FARKLI motor için 200 + 8.939 bayt BAYT-AYNI yanıt). Yani
        "hâlâ çiziliyor" iddiası katı uçta doğru değildi: çizilen bir şey
        yoktu, yalnız 'success' deniyordu.

        Yeni sözleşme ÖLÇÜME bağlıdır, motor tipine değil: gövdede gerçek
        geometri varsa 200 + ``trace_count > 0``; yoksa 501
        ``cad_not_modelled``. Üretici katıyı bir gün gerçekten çizerse bu
        test kendiliğinden 200 dalına geçer.
        """
        r = client.post(yol, json=dict(self.DUZ_IYI))
        cevap = r.get_json()
        if r.status_code == 501:
            assert cevap['error'] == 'cad_not_modelled', cevap
            assert cevap['trace_count'] == 0, cevap
            return
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert cevap['status'] == 'success'
        assert cevap['trace_count'] > 0, cevap
        # ``cad_data`` bir JSON DİZESİDİR; tarayıcı onu ayrıca çözer.
        json.loads(cevap['cad_data'])


# ===========================================================================
# P16B4-17 — /export_tank_cad sözleşmesi
# ===========================================================================
class TestTankCadSozlesmesi:

    IYI_TANK = {
        'dimensions': {'diameter': 150.0, 'length': 800.0,
                       'wall_thickness': 3.0},
        'structural': {'material': 'Aluminum 2219-T87',
                       'pressure_rating': 30.0},
        'internal_structures': {'slosh_baffles': [],
                                'anti_vortex_device': {'diameter': 0.05}},
    }

    def _tank_data(self, **degis):
        veri = {'oxidizer_tank': json.loads(json.dumps(self.IYI_TANK)),
                'fuel_tank': json.loads(json.dumps(self.IYI_TANK))}
        veri.update(degis)
        return veri

    def test_yanlis_blok_adli_422(self, client):
        """Çözücünün ``feed_system.tanks`` bloğu (düz alanlar) reddedilir."""
        yanlis = {'oxidizer_tank': {'volume': 0.77, 'pressure': 3.0,
                                    'material': 'Al'},
                  'fuel_tank': {'volume': 0.43, 'pressure': 3.0,
                                'material': 'Al'}}
        r = client.post('/export_tank_cad', json={'tank_data': yanlis})
        assert r.status_code == 422, r.get_data(as_text=True)[:200]
        govde = r.get_json()
        assert govde['error'] == 'invalid_tank_data'
        alanlar = {k['field'] for k in govde['invalid_fields']}
        assert 'oxidizer_tank.dimensions' in alanlar
        assert 'fuel_tank.dimensions' in alanlar
        # Sözleşme ret gövdesinde YAZILI (eskiden hiç söylenmiyordu).
        assert govde['required_shape']['tank_data']['oxidizer_tank']

    def test_ham_python_anahtari_sizmiyor(self, client):
        """ÖLÇÜLDÜ (onarım öncesi): {"error": "CAD export error: \'dimensions\'"}

        Ayrım önemli: alan ADININ ret gövdesinde geçmesi SÖZLEŞMEDİR (istemci
        neyi yollayacağını oradan okur). Kusur, ``error`` alanının ham bir
        ``KeyError`` metni olmasıydı — yani sunucunun iç durumunun hata kodu
        yerine geçmesi. Bekçi bu ikisini ayırır.
        """
        r = client.post('/export_tank_cad', json={'tank_data': {
            'oxidizer_tank': {'diameter': 0.15},
            'fuel_tank': {'diameter': 0.12}}})
        ham = r.get_data(as_text=True)
        assert r.status_code == 422
        assert 'CAD export error' not in ham, 'ham üretici metni sızdı'
        assert 'Traceback' not in ham
        govde = r.get_json()
        # ``error`` MAKİNE-OKUR bir kod olmalı, Python istisna metni değil.
        assert govde['error'] == 'invalid_tank_data'
        # Alan adları YAPILANDIRILMIŞ listede; ret metnine gömülü değil.
        alanlar = {k['field'] for k in govde['invalid_fields']}
        assert 'oxidizer_tank.dimensions' in alanlar

    @pytest.mark.parametrize('bozuk,beklenen', [
        (NAN, 'not_finite'), (INF, 'not_finite'),
        (0.0, 'not_positive'), (-5.0, 'not_positive'),
        ('abc', 'not_a_number'), (True, 'not_a_number'),
    ], ids=['nan', 'inf', 'sifir', 'eksi', 'metin', 'bool'])
    def test_bozuk_olcu_adiyla_reddediliyor(self, client, bozuk, beklenen):
        veri = self._tank_data()
        veri['oxidizer_tank']['dimensions']['diameter'] = bozuk
        r = _post_ham(client, '/export_tank_cad', {'tank_data': veri})
        assert r.status_code == 422
        kusurlu = r.get_json()['invalid_fields']
        assert any(k['field'] == 'oxidizer_tank.dimensions.diameter'
                   and k['reason'] == beklenen for k in kusurlu), kusurlu

    def test_gecerli_sozlesme_hala_zip_veriyor(self, client):
        r = client.post('/export_tank_cad',
                        json={'tank_data': self._tank_data()})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert 'zip' in (r.headers.get('Content-Type') or '')
        assert len(r.get_data()) > 1000

    def test_sozlesme_dogrulayicisi_urun_yukunu_gecirir(self):
        """Doğrulayıcı tek başına da sınanır (yardımcı ≠ çağıran)."""
        from hrma.export.cad_export import tank_data_contract_problem
        assert tank_data_contract_problem(self._tank_data()) is None
        assert tank_data_contract_problem({}) is not None
        assert tank_data_contract_problem([1, 2]) is not None


# ===========================================================================
# P7B2-19 / P7B3-05 — dosya adı temizliği (ÇAĞIRANDAN geçerek)
# ===========================================================================
class TestDosyaAdiTemizligi:
    """Bekçi ÇAĞIRAN uçtan geçer; ``safe_name``i tek başına sınamaz."""

    KOTU_AD = '../../../etc/passwd'

    #: .eng/.ork üretebilen TAM gövde (aksi halde kapı önce ateşlenir ve
    #: dosya adı hiç kurulmaz — totolojik bekçi tam olarak bu olurdu).
    TAM = dict(IYI_GEOMETRI)

    def test_export_eng_adi_yol_tasimiyor(self, client):
        r = client.post('/api/export-eng', json={
            'motor_data': dict(self.TAM, motor_name=self.KOTU_AD)})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        ad = r.get_json()['filename']
        assert '/' not in ad and '\\' not in ad and '..' not in ad, ad
        assert ad.endswith('.eng')

    def test_export_openrocket_indirme_adi_yol_tasimiyor(self, client):
        r = client.post('/api/export-openrocket', json={
            'motor_data': dict(self.TAM, motor_name=self.KOTU_AD)})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        ad = r.get_json()['download_filename']
        assert '/' not in ad and '..' not in ad, ad

    def test_export_simulation_adi_yol_tasimiyor(self, client):
        r = client.post('/api/export-simulation', json={
            'motor_data': dict(self.TAM, motor_name=self.KOTU_AD)})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        ad = r.get_json()['filename']
        assert '/' not in ad and '..' not in ad, ad
        assert ad.endswith('_simulation.json')

    @pytest.mark.parametrize('yol,alan', [
        ('/api/export-eng', 'filename'),
        ('/api/export-simulation', 'filename'),
    ])
    def test_mesru_ad_bozulmuyor(self, client, yol, alan):
        """Temizlik meşru adı DEĞİŞTİRMEZ (eski davranışla aynı sonuç)."""
        r = client.post(yol, json={
            'motor_data': dict(self.TAM, motor_name='UZAYTEK HRM 001')})
        assert r.status_code == 200
        assert r.get_json()[alan].startswith('UZAYTEK_HRM_001')


# ===========================================================================
# P16B4-27 — xlsx sayfa adı
# ===========================================================================
class TestXlsxSayfaAdi:

    def test_bastaki_nokta_dizisi_tasinmiyor(self):
        assert not _safe_sheet_title('../[]:*?/\\', 0).startswith('.')
        assert not _safe_sheet_title('..', 0).startswith('.')
        assert not _safe_sheet_title('...veri', 0).startswith('.')

    def test_mesru_ad_korunuyor(self):
        assert _safe_sheet_title('Regresyon', 0) == 'Regresyon'
        assert _safe_sheet_title('Thrust Curve', 1) == 'Thrust Curve'

    def test_tamamen_erimis_ad_numarali_yedege_duser(self):
        assert _safe_sheet_title('...', 4) == 'Sheet5'
        assert _safe_sheet_title('/', 0) == 'Sheet1'

    def test_uctan_gecerek_uretilen_kitapta_ad_temiz(self, client):
        openpyxl = pytest.importorskip('openpyxl')
        r = client.post('/api/export-xlsx', json={'sheets': [
            {'name': '../[]:*?/\\', 'headers': ['a'], 'rows': [[1]]}]})
        assert r.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(r.get_data()))
        assert all(not ad.startswith('.') for ad in wb.sheetnames), \
            wb.sheetnames


# ===========================================================================
# P9B2-20 (F2a şartı) — STEP README'si ÖLÇÜMDEN geliyor
# ===========================================================================
class TestStepReadmeOlcumden:

    def test_bos_arsiv_parca_IDDIA_ETMIYOR(self):
        """ÖLÇÜLDÜ (onarım öncesi): dosya olmasa da dört parça sayılıyordu."""
        metin = _step_readme_text([])
        assert 'fuel grain' not in metin
        assert 'injector plate' not in metin
        assert 'none could be listed' in metin

    def test_birim_satiri_KORUNDU(self):
        """Parça listesi üreticiden gelir, BİRİM çağıranın kendi ölçümüdür."""
        metin = _step_readme_text([])
        assert 'Length unit could not be read' in metin

    def test_cagiran_ureticiye_bagli(self):
        """``step_package_readme`` metni ``_step_readme_text``in İÇİNDE."""
        from hrma.export.step_export import step_package_readme
        uretici = step_package_readme([]).rstrip('\n')
        metin = _step_readme_text([])
        for satir in uretici.split('\n'):
            assert satir in metin, f'üretici satırı düşmüş: {satir[:60]}'

    def test_arsivde_OLMAYAN_parca_sayilmiyor(self, tmp_path):
        """Sıvı paketinde ``fuel grain``, katı paketinde ``injector plate``
        YOKTUR; README de saymaz.

        Üretici parçaları ARŞİVDEKİ DOSYA ADLARINDAN okur, bu yüzden bekçi
        build123d'ye gerek duymadan gerçek sözleşmeyi sınayabilir: dosyalar
        elle kurulur ve README'nin onları GÖRDÜĞÜ ölçülür.
        """
        def step_yaz(ad):
            yol = tmp_path / ad
            # Gerçek AP214 başlığı: birim satırı da bundan okunur.
            yol.write_text(
                "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
                "ENDSEC;\nDATA;\n#1 = ( LENGTH_UNIT() NAMED_UNIT(*) "
                "SI_UNIT(.MILLI.,.METRE.) );\nENDSEC;\nEND-ISO-10303-21;\n",
                encoding='utf-8')
            return str(yol)

        # SIVI paketi: kamara + nozul + enjektör + montaj (grain YOK).
        sivi = [step_yaz(f'M_{k}.step')
                for k in ('chamber', 'nozzle', 'injector', 'assembly')]
        metin = _step_readme_text(sivi)
        assert 'injector plate' in metin
        assert 'fuel grain' not in metin, metin
        assert 'millimetres' in metin

        # KATI paketi: kamara + nozul + grain + montaj (enjektör YOK).
        for yol in tmp_path.glob('*.step'):
            yol.unlink()
        kati = [step_yaz(f'M_{k}.step')
                for k in ('chamber', 'nozzle', 'fuel_grain', 'assembly')]
        metin = _step_readme_text(kati)
        assert 'fuel grain' in metin
        assert 'injector plate' not in metin, metin

    def test_diskte_OLMAYAN_yol_parca_saydirmaz(self, tmp_path):
        """Yol verilse bile dosya yoksa parça İDDİA EDİLMEZ (fail-closed)."""
        metin = _step_readme_text([str(tmp_path / 'M_injector.step')])
        assert 'injector plate' not in metin
        assert 'none could be listed' in metin


# ===========================================================================
# P9B3-10 (F2a şartı) — hayalet 10.000 N·s varsayılanı
# ===========================================================================
class TestMotorSinifiHayaletVarsayilani:

    TEMEL = {k: v for k, v in IYI_GEOMETRI.items() if k != 'total_impulse'}
    SECENEK = {'include_cad': False, 'include_openrocket': True,
               'include_analysis': False, 'include_manufacturing': False}

    def test_impuls_yoksa_sinif_iddia_edilmiyor(self, client):
        r = client.post('/api/generate-complete-package', json={
            'motor_data': dict(self.TEMEL), 'package_options': self.SECENEK})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        ork = r.get_json()['complete_package']['openrocket']
        assert ork['motor_class'] is None, (
            'ölçülmemiş impulstan sınıf harfi üretildi')
        assert 'NOT CLASSIFIED' in ork['motor_class_basis']

    def test_gercek_impulsta_sinif_hala_uretiliyor(self, client):
        r = client.post('/api/generate-complete-package', json={
            'motor_data': dict(self.TEMEL, total_impulse=10093.5),
            'package_options': self.SECENEK})
        assert r.status_code == 200
        ork = r.get_json()['complete_package']['openrocket']
        assert ork['motor_class'] == 'M'
        assert 'NOT CLASSIFIED' not in ork['motor_class_basis']

    def test_hicbir_get_cagrisinda_impuls_varsayilani_yok(self):
        """AST çapası: ``motor_data.get('total_impulse', <varsayilan>)``
        biçiminde İKİ ARGÜMANLI bir çağrı kalmamalı.

        Metin araması yerine AST kullanılır: yorum satırındaki ALINTI
        (onarımın gerekçesi eski satırı aynen yazıyor) bir kod kalıntısı
        değildir ve bekçiyi yanlış yere ateşlememelidir.
        """
        import ast
        import inspect
        import textwrap
        import hrma.app as appmod
        agac = ast.parse(textwrap.dedent(
            inspect.getsource(appmod.generate_complete_design_package)))
        suclu = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Call):
                continue
            islev = dugum.func
            if not (isinstance(islev, ast.Attribute) and islev.attr == 'get'):
                continue
            if len(dugum.args) < 2:
                continue
            ilk = dugum.args[0]
            if isinstance(ilk, ast.Constant) and ilk.value == 'total_impulse':
                suclu.append(ast.dump(dugum.args[1]))
        assert not suclu, (
            'total_impulse için varsayılan değer geri geldi: ' + str(suclu))


# ===========================================================================
# P9B3-09 (KRİTİK) — katı raporunun besleme sözleşmesi
# ===========================================================================
class TestPdfBeslemesiCozucuyuGoruyor:
    """Rapor sayıları ÇÖZÜCÜDEN gelir; yoksa 'N/A' kalır (uydurma YOK)."""

    #: ``solid.html``in gerçekten yolladığı ``motor_data``: FORM geometrisi.
    #: Performans alanı YOK — o, ``analysis_results``ın üst düzeyindedir.
    FORM_MOTOR_DATA = {
        'motor_name': 'S7-KATI', 'motor_type': 'solid',
        'propellant_type': 'APCP', 'grain_type': 'BATES',
        'chamber_diameter': 98.0, 'chamber_length': 500.0,
        'throat_diameter': 25.0, 'exit_diameter': 61.0,
        'grain_density': 1800.0, 'propellant_mass': 4.5,
        'expansion_ratio': 6.0,
    }
    #: ``window.currentResults`` — çözücünün KENDİ ad uzayı.
    COZUCU = {
        'max_thrust': 3491.478, 'specific_impulse': 248.526,
        'burn_time': 3.0114, 'total_impulse': 10093.54,
        'chamber_pressure': 50, 'propellant_mass': 4.1414, 'density': 1810,
    }

    def test_cozucu_ust_duzeyi_performansa_iniyor(self):
        bolumler = _build_pdf_analysis_sections(self.FORM_MOTOR_DATA,
                                                dict(self.COZUCU))
        perf = bolumler['performance']
        assert perf['thrust'] == pytest.approx(3491.478)
        assert perf['specific_impulse'] == pytest.approx(248.526)
        assert perf['burn_time'] == pytest.approx(3.0114)
        assert perf['total_impulse'] == pytest.approx(10093.54)
        assert perf['chamber_pressure'] == pytest.approx(50)

    def test_cozucude_olmayan_alan_UYDURULMUYOR(self):
        """Katı çözücü ``exit_velocity``/``mass_flow_rate`` yayımlamıyor."""
        bolumler = _build_pdf_analysis_sections(self.FORM_MOTOR_DATA,
                                                dict(self.COZUCU))
        perf = bolumler['performance']
        assert 'exit_velocity' not in perf
        assert 'mass_flow_rate' not in perf

    def test_motor_data_girdisi_hala_oncelikli(self):
        """Kullanıcının kendi girdisi çözücünün sayısını EZMEZ ama önce gelir."""
        bolumler = _build_pdf_analysis_sections(
            dict(self.FORM_MOTOR_DATA, thrust=1234.0), dict(self.COZUCU))
        assert bolumler['performance']['thrust'] == pytest.approx(1234.0)

    def test_yapilandirma_takma_adi_cozuluyor(self):
        """``density`` -> ``grain_density``, ``mixture_ratio`` -> ``of_ratio``."""
        md = _build_pdf_motor_data({'motor_type': 'liquid'},
                                   {'mixture_ratio': 2.3, 'density': 1810})
        assert md['of_ratio'] == pytest.approx(2.3)
        assert md['grain_density'] == pytest.approx(1810)

    def test_yapilandirma_kullanici_girdisini_EZMEZ(self):
        md = _build_pdf_motor_data({'of_ratio': 6.0},
                                   {'mixture_ratio': 2.3})
        assert md['of_ratio'] == pytest.approx(6.0)

    def test_bos_cozucude_sozluk_degismiyor(self):
        temel = {'motor_type': 'solid'}
        assert _build_pdf_motor_data(temel, {}) is temel

    def test_sonlu_olmayan_deger_tasinmiyor(self):
        bolumler = _build_pdf_analysis_sections(
            {}, {'max_thrust': NAN, 'total_impulse': INF,
                 'specific_impulse': 248.5})
        perf = bolumler.get('performance') or {}
        assert 'thrust' not in perf
        assert 'total_impulse' not in perf
        assert perf['specific_impulse'] == pytest.approx(248.5)

    def test_bool_sayi_sayilmiyor(self):
        bolumler = _build_pdf_analysis_sections({}, {'max_thrust': True})
        assert 'thrust' not in (bolumler.get('performance') or {})

    def test_rapor_uctan_gecince_ozet_sifir_degil(self, client):
        """Uçtan uca: PDF metninde dört özet sayısı da GERÇEK."""
        pypdf = pytest.importorskip('pypdf')
        r = client.post('/api/export-pdf/complete', json={
            'motor_data': dict(self.FORM_MOTOR_DATA),
            'analysis_results': dict(self.COZUCU), 'charts': []})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        okuyucu = pypdf.PdfReader(io.BytesIO(r.get_data()))
        metin = '\n'.join(s.extract_text() or '' for s in okuyucu.pages)
        ozet = metin[metin.find('Executive Summary'):
                     metin.find('Motor Configuration')]
        assert 'Maximum Thrust: N/A' not in ozet, ozet[:400]
        assert '3491.5' in ozet
        assert '248.5' in ozet
        assert '10093.5' in ozet


# ===========================================================================
# Yardımcı sözleşme: ``_reject_nonfinite_export_geometry`` yalnız SONLU
# olmayan değeri reddeder (eksikliği DEĞİL).
# ===========================================================================
class TestSonluOlmayanYarimKapi:

    def test_eksiklik_bu_kapidan_gecer(self):
        from hrma.app import _reject_nonfinite_export_geometry
        with flask_app.test_request_context():
            assert _reject_nonfinite_export_geometry({}) is None

    def test_sonlu_olmayan_deger_reddedilir(self):
        from hrma.app import _reject_nonfinite_export_geometry
        with flask_app.test_request_context():
            red = _reject_nonfinite_export_geometry(
                {'chamber_diameter': math.inf})
            assert red is not None and red[1] == 422
