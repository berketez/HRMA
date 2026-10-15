"""ÖH Dalga-27 · app-api · aşama-4 bekçileri.

Onbir kalem: P7B4-11, P7B4-12, P7B4-18, P7B4-19, P7B4-21, P16B1-22,
P16B1-25, P16B1-26, P16B1-27, P16B1-28, P16B1-29.

Ölçüm: ``docs/scofield/raw/OH/D27/app-api/a4/once.json`` (taban ``8f083ca0``,
ORTAK taban ağacında koşuldu) ve ``sonra.json`` (bu worktree).
Ters-mutasyon: ``a4/mutasyon.json``.
"""
import ast
import io
import json
import math
import os

import pytest

from hrma.app import app

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _uc_kaynagi(baslangic, bitis):
    """``hrma/app.py``in bir dilimini metin olarak verir."""
    metin = io.open(os.path.join(KOK, 'hrma', 'app.py'),
                    encoding='utf-8').read()
    i = metin.index(baslangic)
    return metin[i:metin.index(bitis, i)]


# ===========================================================================
# P7B4-11 — enjekte edilen sabit 'assumed' beyanını etkisizleştiriyordu
# ===========================================================================
class TestP7B411EnjekteSabitler:
    """Uç, figürün ZORUNLU saydığı alanları artık uydurmuyor."""

    UC = "@app.route('/api/advanced-performance-analysis', methods=['POST'])"

    def test_ucun_kaynaginda_enjekte_varsayilan_YOK(self):
        """ÖLÇÜLDÜ (once.json K1): 7 ``default=`` enjeksiyonu vardı."""
        uc = _uc_kaynagi(self.UC, '# PDF Export Endpoints')
        for ad in ('throat_area', 'nozzle_length', 'expansion_ratio',
                   'burn_time', 'chamber_length', 'base_heat_flux',
                   'critical_heat_flux'):
            assert f"'{ad}', default=" not in uc, ad
            assert f"data, '{ad}', default=" not in uc, ad
        assert "data.get('nozzle_length', 0.1)" not in uc

    def test_nozzle_mach_bos_govde_CIZILMEZ(self, istemci):
        """ÖLÇÜLDÜ: 200 + 35.255 bayt figür, "Ae/At = 16.0" OLGU olarak."""
        r = istemci.post('/api/advanced-performance-analysis',
                         json={'analysis_type': 'nozzle_mach'})
        assert r.status_code == 422
        g = r.get_json()
        assert g['error'] == 'incomplete_figure_input'
        eksik = [tuple(x) for x in g['missing_fields']]
        assert ('throat_area', 'throat_diameter') in eksik
        assert ('expansion_ratio', 'exit_diameter') in eksik
        assert 'plot_data' not in g

    def test_gaz_hali_verilse_de_geometri_uydurulmaz(self, istemci):
        """Assumed listesi doluyken bile ε/A_t uydurulmaz (kalemin özü)."""
        r = istemci.post('/api/advanced-performance-analysis',
                         json={'analysis_type': 'nozzle_mach',
                               'gamma': 1.18, 'molecular_weight': 22.0,
                               'chamber_pressure': 35.0,
                               'chamber_temperature': 3100.0})
        assert r.status_code == 422

    def test_heat_flux_zaman_ekseni_ADIYLA_istenir(self, istemci):
        r = istemci.post('/api/advanced-performance-analysis',
                         json={'analysis_type': 'heat_flux'})
        assert r.status_code == 422
        eksik = [tuple(x) for x in r.get_json()['missing_fields']]
        assert ('burn_time',) in eksik

    def test_tam_istek_KULLANICININ_alan_oranini_cizer(self, istemci):
        """Sağlıklı yol: yayımlanan Ae/At GÖNDERİLEN sayıdır (16 DEĞİL)."""
        r = istemci.post('/api/advanced-performance-analysis',
                         json={'analysis_type': 'nozzle_mach',
                               'throat_area': 0.0004,
                               'expansion_ratio': 6.0,
                               'gamma': 1.18, 'molecular_weight': 22.0,
                               'chamber_pressure': 35.0,
                               'chamber_temperature': 3100.0})
        assert r.status_code == 200
        plot = r.get_json()['plot_data']
        assert 'Ae/At = 6.0' in plot
        assert 'Ae/At = 16.0' not in plot

    def test_okunamayan_alan_500_DEGIL(self, istemci):
        r = istemci.post('/api/advanced-performance-analysis',
                         json={'analysis_type': 'nozzle_mach',
                               'throat_area': 'genis',
                               'expansion_ratio': 6.0})
        assert r.status_code == 422
        assert 'throat_area' in r.get_json()['message']

    def test_modulun_kendi_kapisi_hala_AYNI_iki_kosul(self):
        """``_APA_REQUIRED_ANY_OF`` modülün ikizidir; kayarsa kırmızı."""
        from hrma.app import _APA_REQUIRED_ANY_OF
        from hrma.visualization import visualization as viz
        kaynak = io.open(viz.__file__, encoding='utf-8').read()
        i = kaynak.index('def _nozzle_fig_motor_data')
        govde = kaynak[i:kaynak.index('\ndef ', i + 10)]
        assert 'throat_area (m^2) or throat_diameter (m)' in govde
        assert 'expansion_ratio > 1 (or exit_diameter)' in govde
        assert _APA_REQUIRED_ANY_OF['nozzle_mach'] == (
            ('throat_area', 'throat_diameter'),
            ('expansion_ratio', 'exit_diameter'))


# ===========================================================================
# P7B4-12 — /api/chemical-species
# ===========================================================================
class TestP7B412TurAdi:
    """Eksik alan "bulunamadı" değildir; geçersiz JSON iddiası çürük."""

    @pytest.mark.parametrize('govde', [
        {'temperature': 800},
        {'species_name': '', 'temperature': 800},
        {'species_name': None, 'temperature': 800},
    ])
    def test_ad_verilmediginde_422_ve_ALAN_ADI(self, istemci, govde):
        r = istemci.post('/api/chemical-species', json=govde)
        assert r.status_code == 422
        g = r.get_json()
        assert g['error'] == 'species_name_not_supplied'
        assert g['missing_fields'] == ['species_name']
        assert g['invalid_fields'][0]['field'] == 'species_name'

    def test_TANINMAYAN_ad_hala_404(self, istemci):
        """Sözleşme daraltılmadı: gerçekten bulunamayan tür 404 kalır."""
        r = istemci.post('/api/chemical-species',
                         json={'species_name': 'peynir', 'temperature': 800})
        assert r.status_code == 404

    def test_saglikli_yol_BIT_AYNI(self, istemci):
        r = istemci.post('/api/chemical-species',
                         json={'species_name': 'CO', 'temperature': 800})
        assert r.status_code == 200
        g = r.get_json()
        assert g['status'] == 'success'
        tp = g['species_data']['thermodynamic_properties']
        assert math.isclose(tp['cp'], 31.893833238604202, rel_tol=1e-9)

    @pytest.mark.parametrize('t', [-500, 0])
    def test_gecersiz_JSON_iddiasi_CURUK(self, istemci, t):
        """Kalem "NaN / -Infinity gövdeye ham giriyor" diyordu; girmiyor."""
        r = istemci.post('/api/chemical-species',
                         json={'species_name': 'CO', 'temperature': t})
        assert r.status_code == 422
        ham = r.get_data(as_text=True)
        assert 'NaN' not in ham and 'Infinity' not in ham
        json.loads(ham)      # geçerli JSON

    def test_ust_uc_iddiasi_CURUK(self, istemci):
        """T = 1e9 K'de cp yayımlanmıyor (status='unavailable')."""
        r = istemci.post('/api/chemical-species',
                         json={'species_name': 'CO', 'temperature': 1e9})
        assert r.status_code == 200
        g = r.get_json()
        assert g['status'] == 'unavailable'
        assert g['species_data']['thermodynamic_properties']['cp'] is None


# ===========================================================================
# P7B4-19 — /api/uncertainty-analysis motor girdisi kapısı
# ===========================================================================
def _uq_govde(motor_type='hybrid', **ic):
    taban = {'thrust': 1000.0, 'chamber_pressure': 20.0, 'burn_time': 10.0}
    if motor_type == 'hybrid':
        taban['of_ratio'] = 6.0
    taban.update(ic)
    return {'motor_type': motor_type, 'level': 'fast', 'seed': 7,
            'n_samples': 12, 'inputs': taban}


class TestP7B419GirdiKapisi:

    @pytest.mark.parametrize('motor_type', ['hybrid', 'solid', 'liquid'])
    def test_negatif_oda_basinci_UC_TIPTE_DE_ayni_cevap(self, istemci,
                                                        motor_type):
        """ÖLÇÜLDÜ: liquid ham 500 'float division by zero' veriyordu."""
        r = istemci.post('/api/uncertainty-analysis',
                         json=_uq_govde(motor_type, chamber_pressure=-50.0))
        assert r.status_code == 422
        g = r.get_json()
        assert g['error'] == 'non_physical_uncertainty_input'
        alanlar = [f['field'] for f in g['invalid_fields']]
        assert 'chamber_pressure' in alanlar
        assert g['invalid_fields'][0]['container'] == 'inputs'

    def test_of_orani_negatif_KUYRUGA_GIRMEDEN_reddedilir(self, istemci):
        """P7B4-21'in ikinci yarısı: async yol senkronla aynı hükmü verir."""
        for seviye in ('fast', 'high_fidelity'):
            govde = _uq_govde(of_ratio=-5.0)
            govde['level'] = seviye
            govde.pop('n_samples', None)
            r = istemci.post('/api/uncertainty-analysis', json=govde)
            assert r.status_code == 422, seviye
            assert 'of_ratio' in [f['field']
                                  for f in r.get_json()['invalid_fields']]

    def test_sonlu_olmayan_deger_ADIYLA_duser(self, istemci):
        r = istemci.post('/api/uncertainty-analysis',
                         json=_uq_govde(chamber_pressure=float('inf')))
        assert r.status_code == 422
        assert r.get_json()['invalid_fields'][0]['reason'] == 'not_finite'

    def test_taninmayan_alan_SESSIZCE_yutulmaz(self, istemci):
        r = istemci.post('/api/uncertainty-analysis',
                         json=_uq_govde(peynir_orani=42.0))
        assert r.status_code == 200
        okunmayan = r.get_json().get('inputs_not_read') or []
        assert [f['field'] for f in okunmayan] == ['peynir_orani']
        assert okunmayan[0]['reason'] == 'field_not_read'

    def test_saglikli_govde_BEYAN_TASIMAZ(self, istemci):
        r = istemci.post('/api/uncertainty-analysis', json=_uq_govde())
        assert r.status_code == 200
        assert 'inputs_not_read' not in r.get_json()

    def test_okunan_alan_kumesi_fabrikalarla_UYUMLU(self):
        """AST bekçisi: ilan edilen küme ``data.get`` çağrılarının aynısı."""
        from hrma.analysis import uq_adapters as uqa
        kaynak = io.open(uqa.__file__, encoding='utf-8').read()
        agac = ast.parse(kaynak)
        olculen = {}
        for fn in ast.walk(agac):
            if not (isinstance(fn, ast.FunctionDef)
                    and fn.name.startswith('make_')
                    and fn.name.endswith('_factory')):
                continue
            adlar = set()
            for n in ast.walk(fn):
                if (isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr == 'get'
                        and isinstance(n.func.value, ast.Name)
                        and n.func.value.id == 'data' and n.args
                        and isinstance(n.args[0], ast.Constant)):
                    adlar.add(n.args[0].value)
            if adlar:
                olculen[fn.name.split('_')[1]] = adlar
        for tip, ilan in uqa.FACTORY_INPUT_FIELDS.items():
            assert set(ilan) == olculen[tip], tip
        # ``solid`` kapalı küme TAŞIMAZ: overrides=data ile tüm sözlük motora
        # geçer, "okunmadı" hükmü bu katmandan kazanılamaz.
        assert 'solid' not in uqa.FACTORY_INPUT_FIELDS


# ===========================================================================
# P7B4-21 — başarısız iş dış zarfta 'success' diyordu
# ===========================================================================
class TestP7B421IsZarfi:

    def test_tip_adi_oneki_soyulur(self):
        from hrma.app import _job_hata_metni
        assert _job_hata_metni('_UQAnalysisError: patladi') == 'patladi'
        assert _job_hata_metni('ValueError: of_ratio must be > 0') == (
            'of_ratio must be > 0')
        # Ön ek DEĞİL olanlar bit-aynı kalır
        assert _job_hata_metni('Nominal referans: hesap yok') == (
            'Nominal referans: hesap yok')
        assert _job_hata_metni('bir mesaj') == 'bir mesaj'
        assert _job_hata_metni(None) is None

    def test_basarisiz_is_dis_zarfta_SUCCESS_demez(self, istemci,
                                                  monkeypatch):
        """ÖLÇÜLDÜ: job.state='error' iken dış zarf status='success'."""
        from hrma import app as app_mod

        class _SahteRunner:
            def status(self, job_id):
                return {'state': 'error', 'job_id': job_id,
                        'error': "_UQAnalysisError: Nominal referans "
                                 "hesabi basarisiz"}

        monkeypatch.setattr(app_mod, 'job_runner', _SahteRunner())
        r = istemci.get('/api/jobs/deneme')
        assert r.status_code == 200
        g = r.get_json()
        assert g['status'] == 'error'
        assert g['job']['state'] == 'error'
        assert not g['job']['error'].startswith('_UQAnalysisError')

    def test_saglikli_is_SUCCESS_kalir(self, istemci, monkeypatch):
        from hrma import app as app_mod

        class _SahteRunner:
            def status(self, job_id):
                return {'state': 'done', 'job_id': job_id,
                        'result': {'status': 'ok'}}

        monkeypatch.setattr(app_mod, 'job_runner', _SahteRunner())
        g = istemci.get('/api/jobs/deneme').get_json()
        assert g['status'] == 'success'
        assert g['job']['state'] == 'done'

    def test_bilinmeyen_is_404_kalir(self, istemci):
        r = istemci.get('/api/jobs/yok-boyle-bir-is')
        assert r.status_code == 404


# ===========================================================================
# P16B1-22 — regression_a / regression_n ayna kapıları
# ===========================================================================
def _hibrit(**ek):
    g = {'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
         'chamber_pressure': 20, 'of_ratio': 6.0,
         'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}
    g.update(ek)
    return g


class TestP16B122UsBandi:
    """n bandı çözücüden ÖNCE uygulanır — ham OverflowError yok."""

    @pytest.mark.parametrize('n', [1e9, 1e300, 10.0, -5.0, 0.0])
    def test_bant_disi_us_ADIYLA_reddedilir(self, istemci, n):
        r = istemci.post('/calculate', json=_hibrit(regression_n=n))
        assert r.status_code == 400
        g = r.get_json()
        alanlar = [f['field'] for f in g.get('invalid_fields') or []]
        assert 'regression_n' in alanlar, g.get('error')
        assert 'Result too large' not in json.dumps(g)

    def test_ret_govdesi_bandi_TEK_KAYNAKTAN_soyler(self, istemci):
        from hrma.analysis.regression_analysis import (
            REGRESSION_EXPONENT_BAND_INCLUSIVE, REGRESSION_EXPONENT_VALID)
        r = istemci.post('/calculate', json=_hibrit(regression_n=1e9))
        kunye = r.get_json()['invalid_fields'][0]
        assert kunye['accepted_range'] == list(REGRESSION_EXPONENT_VALID)
        assert kunye['accepted_range_inclusive'] == list(
            REGRESSION_EXPONENT_BAND_INCLUSIVE)
        assert kunye['accepted_range_source'].endswith(
            'REGRESSION_EXPONENT_VALID')

    def test_bant_ICI_us_saglikli_kosar(self, istemci):
        r = istemci.post('/calculate', json=_hibrit(regression_n=0.5))
        assert r.status_code == 200

    def test_regression_a_ALT_kapisi_duruyor(self, istemci):
        for a in (0, -1e-4):
            r = istemci.post('/calculate', json=_hibrit(regression_a=a))
            assert r.status_code == 400
            assert r.get_json()['invalid_fields'][0]['field'] == \
                'regression_a'


# ===========================================================================
# P16B1-26 — doğru gerekçe, doğru HTTP sınıfı
# ===========================================================================
class TestP16B126HttpSinifi:

    @pytest.mark.parametrize('md,alan', [
        ({'fuel_type': 'peynir', 'oxidizer_type': 'n2o', 'of_ratio': 6.0,
          'chamber_pressure': 20}, 'fuel_type'),
        ({'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'of_ratio': -5.0,
          'chamber_pressure': 20}, 'of_ratio'),
        ({'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'of_ratio': 6.0,
          'chamber_pressure': 0}, 'chamber_pressure'),
    ])
    def test_cozucu_reddi_500_DEGIL_422(self, istemci, md, alan):
        """ÖLÇÜLDÜ: üçü de HTTP 500 ile dönüyordu (kardeş uç 422 veriyor)."""
        r = istemci.post('/api/advanced-analysis',
                         json={'analysis_types': ['combustion'],
                               'motor_data': md})
        assert r.status_code == 422
        g = r.get_json()
        assert g['error'] == 'invalid_motor_input'
        assert alan in [f['field'] for f in g['invalid_fields']]

    def test_gercek_sunucu_arizasi_500_KALIR(self):
        """Sınıflandırma ``ValueError`` iledir; ``TypeError`` 500 kalır."""
        uc = _uc_kaynagi("@app.route('/api/advanced-analysis'",
                         "@app.route('/api/oxidizer-properties'")
        assert 'except ValueError as _adv_ve:' in uc
        assert "except Exception as e:" in uc
        assert uc.index('except ValueError as _adv_ve:') < uc.index(
            'except Exception as e:')

    def test_kardes_uc_ile_AYNI_sinif(self, istemci):
        """``/api/find-optimum-of`` aynı sınıfa 422 veriyor."""
        r = istemci.post('/api/find-optimum-of',
                         json={'motor_type': 'hybrid', 'fuel': 'htpb',
                               'oxidizer': 'n2o', 'chamber_pressure': 0})
        assert r.status_code == 422


# ===========================================================================
# P16B1-28 — /api/generate-3d
# ===========================================================================
def _3d_govde(**ek):
    md = {'chamber_diameter': 0.1, 'chamber_length': 0.3,
          'port_diameter_initial': 0.03, 'throat_diameter': 0.02,
          'exit_diameter': 0.08}
    md.update(ek)
    return {'motor_data': md}


class TestP16B128PortCapi:

    def test_takma_ad_SESSIZCE_yutulmaz(self, istemci):
        """ÖLÇÜLDÜ: ``port_diameter`` gönderilen istek, gönderilmeyeniyle
        BAYT ÖZDEŞ (426.343 bayt, sha 245f8b2e24e72604) idi."""
        r = istemci.post('/api/generate-3d', json=_3d_govde(
            port_diameter=0.05))
        assert r.status_code == 200
        cizilmeyen = r.get_json().get('inputs_not_used') or []
        adlar = [f['field'] for f in cizilmeyen]
        assert 'port_diameter' in adlar

    def test_gonderilmezse_govde_BEYAN_TASIMAZ(self, istemci):
        g = istemci.post('/api/generate-3d', json=_3d_govde()).get_json()
        assert not (g.get('inputs_not_used') or [])

    def test_port_capi_sahnede_CANLI_iddia_curuk(self, istemci):
        """Kalem "port_diameter sahnede ÖLÜ" diyordu; iki çap iki sahne."""
        a = istemci.post('/api/generate-3d',
                         json=_3d_govde(port_diameter_initial=0.02))
        b = istemci.post('/api/generate-3d',
                         json=_3d_govde(port_diameter_initial=0.05))
        assert a.get_data() != b.get_data()

    def test_NaN_ve_Infinity_ayni_yuk_DEGIL_iddia_curuk(self, istemci):
        a = istemci.post('/api/generate-3d',
                         json=_3d_govde(chamber_diameter=float('nan')))
        b = istemci.post('/api/generate-3d',
                         json=_3d_govde(chamber_diameter=float('inf')))
        assert a.status_code == b.status_code == 422
        assert a.get_data() != b.get_data()


# ===========================================================================
# ÇÜRÜTÜLEN KALEMLER — başlık ölçümle düştü, bekçi yönü DÖNDÜ
# ===========================================================================
class TestCurutulenKalemler:

    def test_P16B125_ret_gerekcesi_DOGRU_alani_sucluyor(self, istemci):
        """Kalem: "400 + 'Missing required inputs: chamber_length'"."""
        r = istemci.post('/calculate', json=_hibrit(regression_a=0))
        assert r.status_code == 400
        g = r.get_json()
        assert g['invalid_fields'][0]['field'] == 'regression_a'
        assert 'chamber_length' not in json.dumps(g)

    def test_P16B127_bos_dize_sicaklik_ham_500_DEGIL(self, istemci):
        """Kalem: "ham 500 'could not convert string to float:'"."""
        r = istemci.post('/api/advanced-analysis', json={
            'analysis_types': ['heat_transfer'], 'wall_thickness': 0.005,
            'motor_data': {'chamber_pressure': 20, 'chamber_temperature': '',
                           'chamber_diameter': 0.1, 'chamber_length': 0.5,
                           'burn_time': 10, 'mdot_total': 1.0}})
        assert r.status_code == 422
        g = r.get_json()
        assert g['error'] == 'incomplete_thermal_input'
        assert 'could not convert' not in json.dumps(g)

    @pytest.mark.parametrize('pc', [0, -20, float('nan')])
    def test_P16B129_ucu_de_ADIYLA_ve_AYNI_reddedilir(self, istemci, pc):
        """Kalem: "üç geçersiz değer üç farklı davranış; itici suçlanıyor"."""
        r = istemci.post('/api/find-optimum-of',
                         json={'motor_type': 'hybrid', 'fuel': 'htpb',
                               'oxidizer': 'n2o', 'chamber_pressure': pc})
        assert r.status_code == 422
        g = r.get_json()
        assert g['error_code'] == 'invalid_chamber_pressure'
        assert [f['field'] for f in g['invalid_fields']] == \
            ['chamber_pressure']
        assert 'No reliable combustion data' not in g['error']

    def test_P7B418_bos_inputs_MonteCarlo_kosmaz(self, istemci):
        """Kalemin birinci yarısı çürük: boş ``inputs`` 422 alıyor."""
        r = istemci.post('/api/uncertainty-analysis',
                         json={'motor_type': 'hybrid', 'level': 'fast'})
        assert r.status_code == 422
        assert r.get_json()['error'] == 'incomplete_uncertainty_input'
