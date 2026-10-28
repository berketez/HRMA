"""ÖH Dalga-31 · app-api-uc a1 bekçileri.

Her sınıf TEK bir kalemi kilitler; hepsi ters-mutasyonla kırmızı
kanıtlanmıştır (``docs/scofield/raw/OH/D31/app-api-uc/a1/mutasyon.json``).
"""
import json

import pytest

from hrma.app import app


@pytest.fixture()
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


SAFETY_TABANI = {
    'chamber_pressure': 50, 'propellant_mass': 50,
    'chamber_diameter': 0.1, 'wall_thickness': 0.005,
}
YAPISAL_TABANI = {
    'chamber_pressure': 50, 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'throat_diameter': 0.04, 'material': 'steel_4130',
}


class TestOHD3011MotorTipiKunyedeSayilir:
    """OH-D30-11 — KISMEN. Bu aşamada ÖDENEN ayak: ``motor_type`` künyesi.

    Kalemin tam onarımı (patlayıcı ekseninin GERİ ÇEKİLMESİ) bu aşamada
    YAPILMADI ve gerekçesi ``hrma/app.py``de OH-D30-11 bloğunda yazılıdır:
    denenen "sınıf kazanılmadıysa 422" kapısı, ucun ÖH Z5S'te kurulmuş
    EKSEN-BAZLI geri çekme sözleşmesini yıkıyor —
    ``tests/test_z5s_hukum_kanali.py`` 10 bekçiyle kırmızıya düştü ve
    bunların ikisi (``hydrazine``, ``n2o4``) TOKSİK ekseni KAZANMIŞ
    isteklerdi. Kapı geri alındı; kusur ölçümü ``once.json`` K1'de durur.

    Aşağıdaki bekçi, ödenen ayağı kilitler: kullanıcının vermediği
    ``motor_type`` künyede ADIYLA sayılır. Bu bir BEYANDIR, doktrin 1
    uyarınca çözüm değildir — ama beyan da kaybolmamalıdır.
    """

    def test_motor_type_ARTIK_VARSAYILANA_DUSMUYOR(self, istemci):
        """ÖH D35 / OH-ON-06 — BEKÇİ ÇEVRİLDİ (gerekçeli).

        D31'de ödenen ayak BEYAN idi: ``motor_type`` künyede ADIYLA
        sayılıyordu ama uç yine de ``'hybrid'``e düşüyor ve o değer
        yayımlanan TNT eşdeğerini seçiyordu. Bu aşamada varsayılanın
        KENDİSİ kalktı; artık sayılacak bir varsayılan YOK, dolayısıyla
        künyede anılması YALAN olurdu. Bekçinin konusu ("vermediğin alan
        sessizce hüküm kazanmasın") daha güçlü biçimde korunuyor:
        alan verilmediğinde patlayıcı ekseni ADIYLA geri çekiliyor.
        """
        j = istemci.post('/analyze_safety', json=dict(
            SAFETY_TABANI, propellant_type='composite')).get_json()
        assert 'motor_type' not in j['defaults_applied'], (
            'uç, uygulamadığı bir varsayılanı künyede sayıyor')

    def test_kusur_HALA_DURUYOR_devir_capasi(self, istemci):
        """DEVİR ÇAPASI — kalem kapanmadı, kusur ölçülebilir durumda.

        Bu bekçi bir onarımı değil, AÇIK BORCU kilitler: vermediğiniz
        ``motor_type`` hâlâ yayımlanan TNT eşdeğerini değiştiriyor.
        Geri çekme ayağı yapıldığında bu bekçi XPASS/kırmızı olur ve
        o aşamada GEREKÇEYLE çevrilir — sessizce kapanmaz.
        """
        ortak = dict(SAFETY_TABANI, propellant_type='apcp')
        yok = istemci.post('/analyze_safety', json=ortak).get_json()
        kati = istemci.post('/analyze_safety',
                            json=dict(ortak, motor_type='solid')).get_json()
        a = yok['safety_analysis']['explosive_hazards']
        b = kati['safety_analysis']['explosive_hazards']
        # ÖH D35 / OH-ON-06 — ÇAPA ÇEVRİLDİ: BORÇ KAPANDI.
        # Eski iddia "kusur HÂLÂ DURUYOR" idi (vermediğin motor_type
        # yayımlanan TNT'yi değiştiriyordu) ve bu bekçinin kendi
        # belgesi çevirmeyi ŞART koşuyordu. Ölçüldü (D31 once.json K1):
        # ``apcp`` + motor tipi yok -> hibrit N2O sınıfı, 22,2775 kg TNT,
        # 7,7363 m ölümcül mesafe; ``motor_type='solid'`` ile 21,0 kg ve
        # 7,5855 m. Artık kimliksiz istek HİÇ TNT yayımlamıyor.
        assert 'tnt_equivalent_kg' not in a, (
            'motor_type verilmeden hâlâ TNT eşdeğeri yayımlanıyor: %r'
            % a.get('tnt_equivalent_kg'))
        assert a.get('explosive_verdict_withheld_because'), (
            'eksen sessizce düştü — geri çekme gerekçesi yok')
        # Kimlik VERİLDİĞİNDE hüküm yine kazanılıyor (fail-closed bedeli
        # "hiç hüküm yok" değildir).
        assert b['explosive_class'] == 'composite'
        assert b['tnt_equivalent_kg'] > 0
        assert 'motor_type' not in yok['defaults_applied']


class TestP12bB206UcVarsayilanlariBeyanEdilir:
    """P12bB2-06 (ÖK-21 uç ayağı) — ``/calculate_solid`` 200 yolunda künye."""

    def test_gonderilmeyen_alanlar_defaults_applied_ile_sayilir(self, istemci):
        yanit = istemci.post('/calculate_solid', json={
            'chamber_pressure': 40, 'propellant_type': 'apcp',
            'thrust': 1000, 'burn_time': 3})
        assert yanit.status_code == 200
        j = yanit.get_json()
        assert j.get('input_source') == 'endpoint_defaults'
        kunye = {k['field']: k for k in j['defaults_applied']}
        # Form katmanı söküldüğünde bu alanlar gelmeyecek; künye onları
        # ADIYLA ve DEĞERİYLE sayar.
        assert {'chamber_diameter', 'grain_length', 'core_diameter',
                'grain_type'} <= set(kunye)
        for ad, k in kunye.items():
            assert k['value'] is not None
            assert k['reason'] == 'endpoint_default'
            # Künye YALAN söylememeli: öğretici bayrağı gönderilmedi.
            assert 'use_tutorial_defaults' not in k['message']

    def test_tam_yuk_varsayilan_beyani_uretmez(self, istemci):
        """TAM gövde varsayılan beyanı üretmez.

        ÖH D37 A1a uc-kapi (OH-D32-02 kanonik künye; ana model kararı,
        rapor ``docs/scofield/raw/OH/A1a/uc-kapi/a1/rapor.md`` §1.5) —
        BEKÇİ ÇEVRİLDİ, gerekçesi: altı alanlık gövde "tam" sayılıyordu,
        çünkü motor kurucusunda okunan yedi çift-katman alanı
        (``ambient_temp`` … ``igniter_pressure_fraction``) gönderilmeyince
        SESSİZCE dolduruluyordu. Kanonik künye o sessizliği kaldırdı; altı
        alanlık gövde artık TAM DEĞİL ve künye bunu ADIYLA söylüyor.
        İki yoldan ("tam yük" gerçekten tam yapılır ⟷ "gövdedeki alan
        künyelenmez") ilki seçildi: testin asıl önermesi TAM gövdede
        ``defaults_applied`` ve ``input_source``un HİÇ doğmamasıdır; ikinci
        yol o önermeyi düşürürdü ve ``test_d27_kati_a2::
        test_varsayilan_YOKSA_alan_hic_yazilmiyor``in kopyası olurdu.
        Tam gövdenin değerleri ucun KENDİ künyesinden okunur (elle sayı
        yazılmaz; form ön-dolgusu K6 sökümünde kalkacak).
        """
        from hrma.app import _KATI_KANONIK_VARSAYILAN_OKUYUCULARI
        from hrma.engines.solid_rocket_engine import (
            SOLID_DEFAULT_GEOMETRY_MM)
        # V301/K-A (22 Eki): eski çapa A_p/A_t = 0,947'lik boğulan portlu varsayılan motoru kilitliyordu.
        alti = {'chamber_pressure': 40, 'propellant_type': 'apcp',
                'chamber_diameter': 100, 'grain_length': 500,
                'core_diameter': SOLID_DEFAULT_GEOMETRY_MM['core_diameter'],
                'grain_type': 'bates'}
        j_alti = istemci.post('/calculate_solid', json=alti).get_json()
        beyan = {k['field']: k['value']
                 for k in j_alti.get('defaults_applied') or []}
        assert set(beyan) == set(_KATI_KANONIK_VARSAYILAN_OKUYUCULARI), (
            'altı alanlık gövdede künye, gövdede OLMAYAN kanonik alanlardan '
            f'başka bir şeyi de anıyor ya da eksik: {sorted(beyan)}')
        assert not set(beyan) & set(alti), beyan
        j = istemci.post('/calculate_solid',
                         json=dict(alti, **beyan)).get_json()
        assert j.get('defaults_applied') is None
        assert j.get('input_source') is None

    def test_grain_type_tek_kaynaktan(self, istemci):
        """Yedek 'bates' iki yerde literal yazılı KALMAZ (doktrin 4)."""
        import inspect
        from hrma import app as app_modulu
        kaynak = inspect.getsource(app_modulu.calculate_solid)
        assert "data.get('grain_type', 'bates')" not in kaynak

    # --- ÖK-21 (a) KOLU: zorunlu alan eksikse 422 gövdesi ALANI ANAR -----
    # ÖLÇÜLDÜ (once.json K7, taban 9d70e9ed): üç istek de 422 alıyordu ama
    # gövde yalnız ``missing_fields`` düz ad listesi taşıyordu; ailenin
    # ``invalid_fields`` sözleşmesi (field + reason) bu kolda YOKTU
    # (invalid_fields_YOK 5/5). Form sökümü sonrası bu kapı ERİŞİLİR olur.
    @pytest.mark.parametrize('govde,beklenen', [
        ({}, {'chamber_pressure', 'propellant_type', 'chamber_diameter',
              'grain_length', 'core_diameter'}),
        ({'chamber_pressure': 40}, {'propellant_type', 'chamber_diameter',
                                    'grain_length', 'core_diameter'}),
        ({'chamber_pressure': 40, 'propellant_type': 'apcp',
          'chamber_diameter': 100}, {'grain_length', 'core_diameter'}),
    ])
    def test_zorunlu_eksikse_invalid_fields_alani_anar(self, istemci, govde,
                                                       beklenen):
        yanit = istemci.post('/calculate_solid', json=govde)
        assert yanit.status_code == 422
        j = yanit.get_json()
        iv = j.get('invalid_fields')
        assert isinstance(iv, list) and iv, (
            '422 gövdesi aile sözleşmesindeki invalid_fields listesini '
            'taşımıyor; istemci eksikliği yalnız düz ad listesinden okuyor')
        assert {r['field'] for r in iv} == beklenen
        for r in iv:
            assert r['reason'] == 'not_supplied'
            assert r['required'] is True
            # "Ne gönderdiniz" yankısı: alan gerçekten YOK.
            assert r['submitted'] is None

    def test_invalid_fields_missing_fields_ile_AYNI_kaynaktan(self, istemci):
        """İkinci bir gerçek yazılmadı: iki liste birebir örtüşür."""
        j = istemci.post('/calculate_solid',
                         json={'chamber_pressure': 40}).get_json()
        assert [r['field'] for r in j['invalid_fields']] == j['missing_fields']

    def test_zorunlu_alan_beyanla_doldurulMAZ(self, istemci):
        """ÖK-21 (a) ⟷ (b) ayrımı: reddedilen alan varsayılan ALMAZ."""
        yanit = istemci.post('/calculate_solid', json={'chamber_pressure': 40})
        assert yanit.status_code == 422
        j = yanit.get_json()
        assert 'defaults_applied' not in j
        assert j.get('input_source') is None


class TestOHD3003CidarKabulBandiKunyesi:
    """OH-D30-03 — bandın asimetrisi ADIYLA yayımlanır."""

    def test_kabul_bandi_kunyesi_yayimlanir(self, istemci):
        j = istemci.post('/analyze_structural_safety', json=dict(
            YAPISAL_TABANI, wall_thickness=0.005)).get_json()
        bant = j['design_basis']['wall_thickness_accepted_range']
        assert bant['unit'] == 'm'
        assert bant['lower_bound'] == 0.0
        assert bant['lower_bound_inclusive'] is False
        # Üst uç UYDURULMAZ: kullanıcının kendi çapından türer.
        assert bant['upper_bound'] == pytest.approx(0.05)
        assert 'chamber_diameter' in bant['upper_bound_basis']
        # Alt uçta imalat tabanı YOK — ve bu SÖYLENİR ("band yok" beyanı).
        assert bant['manufacturability_floor'] == 'not_modelled'
        assert bant['manufacturability_floor_reason']

    def test_asiri_ince_cidar_kunyesiyle_birlikte_doner(self, istemci):
        """1 nm cidar geçer (imalat tabanı yok) ama künye bunu ilan eder."""
        yanit = istemci.post('/analyze_structural_safety', json=dict(
            YAPISAL_TABANI, wall_thickness=1e-9))
        assert yanit.status_code == 200
        j = yanit.get_json()
        assert j['design_basis']['wall_thickness_accepted_range'][
            'manufacturability_floor'] == 'not_modelled'
        # Hüküm KAZANILMIŞTIR: emniyet katsayısı gerçekten hesaplandı.
        oda = j['structural_analysis']['chamber_analysis']
        assert oda['hoop_safety_factor'] < 1.0

    def test_ust_uc_hala_reddedilir(self, istemci):
        yanit = istemci.post('/analyze_structural_safety', json=dict(
            YAPISAL_TABANI, wall_thickness=1e9))
        assert yanit.status_code == 422
        assert yanit.get_json()['invalid_fields'][0][
            'reason'] == 'exceeds_chamber_radius'


class TestOHD3007RetGovdeleriMakineOkur:
    """OH-D30-07 — ihracat ailesinin ORTAK ret gövdeleri."""

    @pytest.mark.parametrize('yol', [
        '/api/export-step', '/api/export-dxf', '/api/export-cad',
        '/api/export-eng', '/api/export-openrocket', '/api/export-simulation',
        '/api/generate-complete-package',
    ])
    @pytest.mark.parametrize('govde', [{}, {'motor_data': {}}])
    def test_eksik_geometri_invalid_fields_tasir(self, istemci, yol, govde):
        yanit = istemci.post(yol, json=govde)
        assert yanit.status_code >= 400
        j = yanit.get_json()
        assert j.get('invalid_fields'), (
            f'{yol} {govde} reddediyor ama hangi alanın neden geçersiz '
            'olduğunu makine-okur biçimde söylemiyor')
        for k in j['invalid_fields']:
            assert k.get('field') and k.get('reason')

    @pytest.mark.parametrize('yol', ['/export_solid_motor_cad',
                                     '/export_liquid_cad'])
    def test_cad_uclari_kod_ve_alan_tasir(self, istemci, yol):
        j = istemci.post(yol, json={}).get_json()
        assert j.get('status') == 'error'
        # ``error`` MAKİNE-OKUR koddur, İngilizce cümle değil.
        assert ' ' not in j['error']
        assert j['message'] == 'Motor data not found'
        assert j['invalid_fields'][0]['field'] == 'results'

    def test_generate_3d_error_alani_koddur(self, istemci):
        j = istemci.post('/api/generate-3d', json={}).get_json()
        assert j['status'] == 'incomplete_geometry'
        assert ' ' not in j['error'], (
            'kardeş uçlar bu alanda kod taşıyor; cümle message alanına ait')
        assert 'Cannot draw the motor' in j['message']

    def test_sozluk_olmayan_tasiyici_alan_adiyla_reddedilir(self, istemci):
        j = istemci.post('/api/export-cad',
                         json={'motor_data': [1, 2, 3]}).get_json()
        assert j['invalid_fields'][0]['field'] == 'motor_data'
        assert j['invalid_fields'][0]['reason'] == 'not_an_object'


class TestOHD3012UQKosullulukBeyani:
    """OH-D30-12 — P5/P95 bandının kapsamı sonucun yanında."""

    def test_kosulluluk_blogu_yuzdeliklerle_birlikte_doner(self):
        from hrma.analysis import uncertainty as U

        dagilimlar = {
            'mdot': U.UncertainInput(
                name='mdot', dist='truncnorm', mode='multiplier',
                mean=1.0, sigma=0.05, low=0.8, high=1.2),
            'cstar_eff': U.UncertainInput(
                name='cstar_eff', dist='truncnorm', mode='multiplier',
                mean=1.0, sigma=0.03, low=0.85, high=1.15),
        }
        sonuc = U.run_uncertainty(
            lambda s: {'thrust': 1000.0 * s['mdot'],
                       'isp': 250.0 * s['cstar_eff']},
            dagilimlar, n_samples=24, seed=7,
            output_keys=['thrust', 'isp'])
        assert sonuc['status'] == 'success'
        assert sonuc['outputs']['thrust']['p95'] is not None
        kosul = sonuc['conditionality']
        assert set(kosul['conditional_on_inputs']) == {'mdot', 'cstar_eff'}
        assert kosul['model_form_uncertainty_included'] is False
        assert 'independent' in kosul['input_correlation_assumed']
        assert 'not a confidence interval' in kosul['interpretation'].lower()
        assert 'not listed' in kosul['frozen_at_nominal']
        assert kosul['applies_to'].startswith('outputs')


class TestOHD3009GonderilenCidarKunyedeYankilanir:
    """OH-D30-09 — ``submitted_raw_m`` /calculate ve hızlı geometri kolları."""

    CALC = {'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 5,
            'chamber_pressure': 20, 'oxidizer_type': 'n2o',
            'fuel_type': 'htpb', 'of_ratio': 6.0}

    @pytest.mark.parametrize('yol', ['/calculate', '/api/quick-geometry'])
    def test_okunamayan_deger_kunyede_gorunur(self, istemci, yol):
        j = istemci.post(yol, json=dict(self.CALC,
                                        wall_thickness=-5)).get_json()
        temel = self._temel(j)
        assert temel['wall_thickness_source'] == 'user_value_not_applied'
        assert temel['submitted_wall_thickness_mm'] == pytest.approx(-5.0), (
            'künye "gönderdiğiniz cidar değerlendirilen değildi" diyor ama '
            'hangi sayıyı gönderdiğinizi söylemiyordu')

    @pytest.mark.parametrize('yol', ['/calculate', '/api/quick-geometry'])
    def test_gecerli_deger_degismedi(self, istemci, yol):
        j = istemci.post(yol, json=dict(self.CALC,
                                        wall_thickness=5)).get_json()
        temel = self._temel(j)
        assert temel['wall_thickness_source'] == 'user_supplied'
        assert temel['submitted_wall_thickness_mm'] == pytest.approx(5.0)

    @staticmethod
    def _temel(j):
        for yol in (('structural_design_basis',),
                    ('results', 'structural_design_basis')):
            d = j
            for p in yol:
                d = d.get(p) if isinstance(d, dict) else None
            if isinstance(d, dict):
                return d
        raise AssertionError('structural_design_basis bulunamadı: '
                             + json.dumps(sorted(j))[:200])
