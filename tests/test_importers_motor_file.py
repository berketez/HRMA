"""RASP .eng / RockSim .rse içe aktarımı testleri (hrma.importers).

El hesabı çapaları (tests/fixtures/importers/hrma_single.eng):
- Örtük (0,0) ile eğri [0,0],[0.1,100],[1.9,100],[2.0,0]:
  I_t = 0.5*0.1*100 + 1.8*100 + 0.5*0.1*100 = 190 N·s (yamuk kuralı).
- Tepe itki 100 N; %5 eşik (NFPA 1125) kesişimleri t=0.005 ve t=1.995 →
  yanma süresi 1.99 s; ortalama itki 190/1.99 = 95.477 N.

Bozuk dosya sınıfları ValueError FIRLATMAZ; {"error": ...} döner ve API
katmanı 400'e çevirir (uydurma-veri-yasağı kimliği: sessiz düzeltme yok).
"""

import json
from pathlib import Path

import pytest
from flask import Flask

from hrma.importers import motor_file
from hrma.importers.api import importers_api, MOTOR_FILE_MAX_BYTES

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'importers'


def _read(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# parse_eng
# ---------------------------------------------------------------------------
class TestParseEng:
    def test_valid_fixture(self):
        motor = motor_file.parse_eng(_read('hrma_single.eng'))
        assert 'error' not in motor
        meta = motor['meta']
        assert meta['name'] == 'HRMA-K100'
        assert meta['mfg'] == 'HRMA'
        assert meta['diameter_mm'] == 54.0
        assert meta['length_mm'] == 400.0
        assert meta['delays'] == '0-6'
        assert meta['prop_mass_kg'] == 0.5
        assert meta['loaded_mass_kg'] == 1.2
        assert meta['type'] is None  # RASP başlığında tip alanı yok
        assert meta['source_format'] == 'rasp_eng'

    def test_implicit_ignition_point_prepended_and_reported(self):
        motor = motor_file.parse_eng(_read('hrma_single.eng'))
        assert motor['time'][0] == 0.0
        assert motor['thrust'][0] == 0.0
        assert any('Implicit RASP ignition point' in w
                   for w in motor['warnings'])

    def test_computed_metrics_hand_anchor(self):
        motor = motor_file.parse_eng(_read('hrma_single.eng'))
        comp = motor['computed']
        assert comp['total_impulse_ns'] == pytest.approx(190.0)
        assert comp['peak_thrust_n'] == pytest.approx(100.0)
        assert comp['burn_time_s'] == pytest.approx(1.99, abs=1e-9)
        assert comp['avg_thrust_n'] == pytest.approx(190.0 / 1.99)

    def test_turkish_decimal_comma_tolerated(self):
        text = ("HRMA-T1 38 250 0 0,2 0,5 HRMA\n"
                "0,1 50,0\n1,0 50,0\n1,1 0,0\n")
        motor = motor_file.parse_eng(text)
        assert 'error' not in motor
        assert motor['meta']['prop_mass_kg'] == pytest.approx(0.2)
        assert motor['thrust'][1] == pytest.approx(50.0)

    def test_multiple_pairs_on_one_line(self):
        text = ("HRMA-T2 38 250 0 0.2 0.5 HRMA\n"
                "0.1 50.0 1.0 50.0\n1.1 0.0\n")
        motor = motor_file.parse_eng(text)
        assert 'error' not in motor
        assert len(motor['time']) == 4  # örtük (0,0) + 3 nokta

    def test_nonzero_final_thrust_warns(self):
        text = "HRMA-T3 38 250 0 0.2 0.5 HRMA\n0.1 50.0\n1.0 40.0\n"
        motor = motor_file.parse_eng(text)
        assert 'error' not in motor
        assert any('expected to end near 0 N' in w
                   for w in motor['warnings'])

    def test_second_motor_block_ignored_with_warning(self):
        text = ("HRMA-A 38 250 0 0.2 0.5 HRMA\n0.1 50.0\n1.0 0.0\n"
                "HRMA-B 54 400 0 0.5 1.2 HRMA\n0.1 100.0\n2.0 0.0\n")
        motor = motor_file.parse_eng(text)
        assert 'error' not in motor
        assert motor['meta']['name'] == 'HRMA-A'
        assert any('more than one motor definition' in w
                   for w in motor['warnings'])

    def test_malformed_header_is_safe_error(self):
        result = motor_file.parse_eng("bozuk baslik satiri\n0.1 50\n")
        assert 'error' in result
        assert 'RASP header' in result['error']

    def test_empty_curve_is_safe_error(self):
        result = motor_file.parse_eng("HRMA-X 38 250 0 0.2 0.5 HRMA\n")
        assert 'error' in result

    def test_negative_thrust_is_safe_error(self):
        text = "HRMA-X 38 250 0 0.2 0.5 HRMA\n0.1 50.0\n0.5 -3.0\n1.0 0.0\n"
        result = motor_file.parse_eng(text)
        assert 'error' in result
        assert 'Negative thrust' in result['error']

    def test_non_chronological_time_is_safe_error(self):
        text = "HRMA-X 38 250 0 0.2 0.5 HRMA\n0.5 50.0\n0.1 60.0\n1.0 0.0\n"
        result = motor_file.parse_eng(text)
        assert 'error' in result
        assert 'chronological' in result['error']

    def test_zero_impulse_is_safe_error(self):
        text = "HRMA-X 38 250 0 0.2 0.5 HRMA\n0.1 0.0\n1.0 0.0\n"
        result = motor_file.parse_eng(text)
        assert 'error' in result
        assert 'impulse' in result['error'].lower()

    def test_prop_mass_exceeding_loaded_mass_warns(self):
        text = "HRMA-X 38 250 0 0.9 0.5 HRMA\n0.1 50.0\n1.0 0.0\n"
        motor = motor_file.parse_eng(text)
        assert 'error' not in motor
        assert any('exceeds loaded mass' in w for w in motor['warnings'])

    def test_non_text_input_is_safe_error(self):
        assert 'error' in motor_file.parse_eng(b'ikili veri')


# ---------------------------------------------------------------------------
# parse_rse
# ---------------------------------------------------------------------------
class TestParseRse:
    def test_multi_engine_fixture_returns_all_usable(self):
        parsed = motor_file.parse_rse(_read('hrma_multi.rse'))
        assert 'error' not in parsed
        # 3 motor tanımı: 2 kullanılabilir + 1 sıfır-impulslu (atlanır)
        assert len(parsed['motors']) == 2
        assert parsed['default_index'] == 0
        assert any('HRMA-BROKEN' in w for w in parsed['warnings'])
        assert any('3 engine definitions' in w for w in parsed['warnings'])

    def test_meta_units_grams_to_kg(self):
        parsed = motor_file.parse_rse(_read('hrma_multi.rse'))
        meta = parsed['motors'][0]['meta']
        assert meta['name'] == 'HRMA-K190'
        assert meta['loaded_mass_kg'] == pytest.approx(1.2)
        assert meta['prop_mass_kg'] == pytest.approx(0.5)
        assert meta['diameter_mm'] == pytest.approx(54.0)
        assert meta['type'] == 'Hybrid'
        assert meta['source_format'] == 'rse'
        assert meta['declared']['total_impulse_ns'] == pytest.approx(190.0)

    def test_mass_and_cg_curves_extracted(self):
        parsed = motor_file.parse_rse(_read('hrma_multi.rse'))
        motor = parsed['motors'][0]
        assert motor['mass_curve'][0] == {'t': 0.0, 'mass_g': 500.0}
        assert motor['cg_curve'][-1] == {'t': 2.0, 'cg_mm': 180.0}
        # İkinci motorda m/cg yok → eğriler hiç eklenmez (sessiz doldurma yok)
        assert 'mass_curve' not in parsed['motors'][1]
        assert 'cg_curve' not in parsed['motors'][1]

    def test_declared_impulse_mismatch_warns(self):
        parsed = motor_file.parse_rse(_read('hrma_multi.rse'))
        # Motor 1 beyanı tutarlı → uyarı yok; motor 2 beyanı (500) eğriden
        # (190) uzak → uyarı var
        assert not any('Declared total impulse' in w
                       for w in parsed['motors'][0]['warnings'])
        assert any('Declared total impulse' in w
                   for w in parsed['motors'][1]['warnings'])

    def test_bare_engine_root_accepted(self):
        text = ('<engine code="X" mfg="HRMA" dia="54" len="400">'
                '<data><eng-data t="0" f="0"/><eng-data t="1" f="10"/>'
                '<eng-data t="2" f="0"/></data></engine>')
        parsed = motor_file.parse_rse(text)
        assert 'error' not in parsed
        assert parsed['motors'][0]['meta']['name'] == 'X'

    def test_doctype_rejected_for_security(self):
        text = ('<!DOCTYPE engine [<!ENTITY x "y">]>'
                '<engine code="&x;"><data/></engine>')
        result = motor_file.parse_rse(text)
        assert 'error' in result
        assert 'security' in result['error']

    def test_invalid_xml_is_safe_error(self):
        assert 'error' in motor_file.parse_rse('<engine-database><engine')

    def test_no_engine_element_is_safe_error(self):
        result = motor_file.parse_rse('<engine-database/>')
        assert 'error' in result
        assert '<engine>' in result['error']

    def test_all_engines_broken_is_safe_error(self):
        text = ('<engine-database><engine-list>'
                '<engine code="Z"><data><eng-data t="0" f="0"/>'
                '<eng-data t="1" f="0"/></data></engine>'
                '</engine-list></engine-database>')
        result = motor_file.parse_rse(text)
        assert 'error' in result


# ---------------------------------------------------------------------------
# POST /api/import/motor-file — geçici Flask app ile (app.py'ye dokunmadan)
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(importers_api)
    with app.test_client() as test_client:
        yield test_client


class TestMotorFileEndpoint:
    def test_eng_success_with_source_and_warnings(self, client):
        response = client.post('/api/import/motor-file', json={
            'content': _read('hrma_single.eng'),
            'filename': 'hrma_single.eng',
        })
        assert response.status_code == 200
        body = response.get_json()
        assert body['status'] == 'success'
        assert body['source'] == 'rasp_eng'
        assert body['selected_index'] == 0
        assert body['motor']['computed']['total_impulse_ns'] == \
            pytest.approx(190.0)
        assert isinstance(body['warnings'], list)
        assert body['comparison'] is None

    def test_rse_success_returns_all_motors(self, client):
        response = client.post('/api/import/motor-file', json={
            'content': _read('hrma_multi.rse'),
            'filename': 'hrma_multi.rse',
        })
        assert response.status_code == 200
        body = response.get_json()
        assert body['source'] == 'rse'
        assert len(body['motors']) == 2
        assert body['motor']['meta']['name'] == 'HRMA-K190'

    def test_prediction_comparison_uses_csv_flow_metrics(self, client):
        response = client.post('/api/import/motor-file', json={
            'content': _read('hrma_single.eng'),
            'filename': 'hrma_single.eng',
            'prediction': {'time': [0.0, 0.1, 1.9, 2.0],
                           'thrust': [0.0, 100.0, 100.0, 0.0]},
        })
        assert response.status_code == 200
        comparison = response.get_json()['comparison']
        assert comparison['grade'] == 'excellent'
        metrics = comparison['metrics']
        # upload-csv akışıyla aynı metrik anahtarları (compare sözleşmesi)
        for key in ('total_impulse_diff_pct', 'peak_thrust_diff_pct',
                    'burn_time_diff_s', 'rmse_n', 'nrmse_pct'):
            assert key in metrics
        assert metrics['total_impulse_diff_pct'] == pytest.approx(0.0)

    def test_non_overlapping_prediction_is_400_with_motors(self, client):
        response = client.post('/api/import/motor-file', json={
            'content': _read('hrma_single.eng'),
            'filename': 'hrma_single.eng',
            'prediction': {'time': [10.0, 11.0], 'thrust': [50.0, 50.0]},
        })
        assert response.status_code == 400
        body = response.get_json()
        assert body['status'] == 'error'
        assert body['motors']  # dosya çözümü yanıtın içinde kalır

    def test_missing_content_is_400(self, client):
        response = client.post('/api/import/motor-file', json={})
        assert response.status_code == 400
        assert 'content' in response.get_json()['error']

    def test_extension_whitelist_enforced(self, client):
        response = client.post('/api/import/motor-file', json={
            'content': _read('hrma_single.eng'),
            'filename': 'hrma_single.txt',
        })
        assert response.status_code == 400
        assert '.eng' in response.get_json()['error']

    def test_path_in_filename_is_stripped_not_used(self, client):
        response = client.post('/api/import/motor-file', json={
            'content': _read('hrma_single.eng'),
            'filename': '..\\..\\etc\\hrma_single.eng',
        })
        assert response.status_code == 200
        assert response.get_json()['filename'] == 'hrma_single.eng'

    def test_broken_file_is_400_with_message(self, client):
        response = client.post('/api/import/motor-file', json={
            'content': 'HRMA-X 38 250 0 0.2 0.5 HRMA\n0.1 0.0\n1.0 0.0\n',
            'filename': 'broken.eng',
        })
        assert response.status_code == 400
        assert 'impulse' in response.get_json()['error'].lower()

    def test_oversize_content_is_413(self, client):
        response = client.post(
            '/api/import/motor-file',
            data=json.dumps({
                'content': 'x' * (MOTOR_FILE_MAX_BYTES + 16),
                'filename': 'big.eng',
            }),
            content_type='application/json')
        assert response.status_code == 413
