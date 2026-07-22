"""OpenRocket .ork içe aktarımı testleri (hrma.importers.ork_import).

El hesabı çapaları (tests/fixtures/importers/hrma_basic.ork):
- Gövde: burun 0.3 m + tüp 1.2 m → body_length 1.5 m; tüp yarıçapı 'auto'
  → burun aftradius 0.05 m'den çözülür → body_diameter 0.1 m.
- Kanat konumu: tüp başlangıcı 0.3, boyu 1.2, bottom ofset 0, kök veter
  0.2 → hücum kenarı 0.3 + 1.2 + 0 - 0.2 = 1.3 m.
- Kütle tahminleri (dosyadaki yoğunluklarla):
  kanatlar 0.12*(0.2+0.1)/2 * 0.003 * 3 * 680 = 0.11016 kg;
  tüp pi*(0.05^2-0.0485^2)*1.2*680 = 0.37876 kg;
  burun ince kabuk pi*0.05*sqrt(0.3^2+0.05^2)*0.002*1050 = 0.10032 kg.
- Serbest kanat (hrma_freeform.ork) tam trapez çizgisidir: alan+MAC
  korunumu kök 0.2 / uç 0.1 / süpürme 0.05 değerlerini geri vermelidir.
"""

import base64
import gzip
import io
import zipfile
from pathlib import Path

import pytest
from flask import Flask

from hrma.importers import ork_import
from hrma.importers.api import importers_api, ORK_MAX_BYTES

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'importers'


def _read_bytes(name):
    return (FIXTURES / name).read_bytes()


def _zip_with(entries):
    """Bellekte sentetik ZIP kur: entries = {ad: bayt}."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Düz XML ayrıştırma — aero eşleme
# ---------------------------------------------------------------------------
class TestBasicAeroMapping:
    @pytest.fixture(scope='class')
    def result(self):
        return ork_import.parse_ork(_read_bytes('hrma_basic.ork'))

    def test_no_error_and_source_tag(self, result):
        assert 'error' not in result
        assert result['source'] == 'ork'

    def test_aero_keys_match_six_dof_contract(self, result):
        # /api/six-dof-analysis sözleşme anahtarları (metre, SI)
        assert set(result['aero'].keys()) == {
            'nose_length', 'nose_type', 'body_diameter', 'body_length',
            'fin_count', 'fin_root_chord', 'fin_tip_chord', 'fin_span',
            'fin_sweep', 'fin_position'}

    def test_nose_mapping(self, result):
        assert result['aero']['nose_length'] == pytest.approx(0.3)
        assert result['aero']['nose_type'] == 'ogive'

    def test_auto_radius_resolved_from_neighbor(self, result):
        assert result['aero']['body_diameter'] == pytest.approx(0.1)

    def test_body_length_is_nose_plus_tubes(self, result):
        assert result['aero']['body_length'] == pytest.approx(1.5)

    def test_fin_geometry_and_position(self, result):
        aero = result['aero']
        assert aero['fin_count'] == 3
        assert aero['fin_root_chord'] == pytest.approx(0.2)
        assert aero['fin_tip_chord'] == pytest.approx(0.1)
        assert aero['fin_span'] == pytest.approx(0.12)
        assert aero['fin_sweep'] == pytest.approx(0.05)
        assert aero['fin_position'] == pytest.approx(1.3)

    def test_mass_component_direct_not_estimated(self, result):
        avionics = next(c for c in result['components']
                        if c['name'] == 'Aviyonik')
        assert avionics['mass_kg'] == pytest.approx(0.35)
        assert avionics['estimated'] is False
        assert avionics['propellant'] is False
        assert avionics['source'] == 'masscomponent'
        # top ofset 0.2, paket boyu 0.1 → orta nokta 0.3+0.2+0.05 = 0.55
        assert avionics['x_m'] == pytest.approx(0.55)

    def test_structural_masses_estimated_from_file_density(self, result):
        by_name = {c['name']: c for c in result['components']}
        assert by_name['Kanatlar']['mass_kg'] == pytest.approx(0.11016,
                                                               rel=1e-3)
        assert by_name['Govde']['mass_kg'] == pytest.approx(0.37876,
                                                            rel=1e-3)
        assert by_name['Burun']['mass_kg'] == pytest.approx(0.10032,
                                                            rel=1e-3)
        for name in ('Kanatlar', 'Govde', 'Burun'):
            assert by_name[name]['estimated'] is True
            assert by_name[name]['source'] == 'geometry_density'

    def test_parachute_skipped_in_mapping_report(self, result):
        assert any('parachute' in item
                   for item in result['mapping_report']['skipped'])

    def test_saved_simulation_extracted(self, result):
        sims = result['saved_simulations']
        assert len(sims) == 1
        assert sims[0]['name'] == 'Simulasyon 1'
        assert sims[0]['apogee_m'] == pytest.approx(1234.5)
        assert sims[0]['time_to_apogee_s'] == pytest.approx(17.2)
        assert sims[0]['max_velocity_ms'] == pytest.approx(210.0)

    def test_mapping_report_structure(self, result):
        report = result['mapping_report']
        assert set(report.keys()) == {'mapped', 'approximated', 'skipped'}
        assert any('nosecone' in item for item in report['mapped'])
        # Kütle tahminleri şeffaf: approximated kayıtları var
        assert any('mass' in item for item in report['approximated'])


class TestMultiStage:
    def test_only_sustainer_imported_with_skip_record(self):
        result = ork_import.parse_ork(_read_bytes('hrma_two_stage.ork'))
        assert 'error' not in result
        assert any('sustainer' in w for w in result['warnings'])
        assert any("stage 'Booster'" in item
                   for item in result['mapping_report']['skipped'])
        # Gövde boyu yalnız sustainer: 0.25 + 0.8
        assert result['aero']['body_length'] == pytest.approx(1.05)
        # Booster tüpü kütle listesine girmez
        assert all(c['name'] != 'Alt govde' for c in result['components'])

    def test_old_position_element_resolved(self):
        result = ork_import.parse_ork(_read_bytes('hrma_two_stage.ork'))
        # bottom ofset 0: 0.25 + 0.8 - 0.12 = 0.93
        assert result['aero']['fin_position'] == pytest.approx(0.93)


class TestFreeformFin:
    def test_equivalent_trapezoid_preserves_area_and_mac(self):
        result = ork_import.parse_ork(_read_bytes('hrma_freeform.ork'))
        assert 'error' not in result
        aero = result['aero']
        # Çizgi tam trapez → eşdeğer dönüşüm aynı trapezi geri vermeli
        assert aero['fin_root_chord'] == pytest.approx(0.2, rel=1e-3)
        assert aero['fin_tip_chord'] == pytest.approx(0.1, rel=1e-3)
        assert aero['fin_span'] == pytest.approx(0.12)
        assert aero['fin_sweep'] == pytest.approx(0.05)
        assert any('equivalent trapezoid' in item
                   for item in result['mapping_report']['approximated'])

    def test_unmapped_nose_shape_approximated_as_parabolic(self):
        result = ork_import.parse_ork(_read_bytes('hrma_freeform.ork'))
        assert result['aero']['nose_type'] == 'parabolic'
        assert any("ellipsoid" in item
                   for item in result['mapping_report']['approximated'])

    def test_area_preservation_math(self):
        # Doğrudan dönüşüm fonksiyonu: alan korunumu toleransla
        points = [(0.0, 0.0), (0.05, 0.12), (0.15, 0.12), (0.2, 0.0)]
        trapezoid = ork_import._freeform_to_trapezoid(points)
        expected_area = 0.12 * (0.2 + 0.1) / 2.0
        assert trapezoid['area'] == pytest.approx(expected_area, rel=1e-4)
        recovered = trapezoid['span'] * \
            (trapezoid['root'] + trapezoid['tip']) / 2.0
        assert recovered == pytest.approx(expected_area, rel=1e-4)


# ---------------------------------------------------------------------------
# Kap biçimleri: ZIP / gzip + güvenlik
# ---------------------------------------------------------------------------
class TestContainers:
    def test_zip_with_rocket_ork(self):
        data = _zip_with({'rocket.ork': _read_bytes('hrma_basic.ork')})
        result = ork_import.parse_ork(data)
        assert 'error' not in result
        assert result['aero']['body_diameter'] == pytest.approx(0.1)

    def test_zip_with_embedded_rse_thrust_curve(self):
        data = _zip_with({
            'rocket.ork': _read_bytes('hrma_basic.ork'),
            'thrustcurves/hrma_multi.rse': _read_bytes('hrma_multi.rse'),
        })
        result = ork_import.parse_ork(data)
        assert 'error' not in result
        assert len(result['embedded_motors']) == 2  # 2 kullanılabilir motor
        motor = result['embedded_motors'][0]
        assert motor['meta']['source_file'] == 'thrustcurves/hrma_multi.rse'
        assert motor['computed']['total_impulse_ns'] == pytest.approx(190.0)

    def test_gzip_compressed_ork(self):
        data = gzip.compress(_read_bytes('hrma_basic.ork'))
        result = ork_import.parse_ork(data)
        assert 'error' not in result
        assert result['aero']['body_length'] == pytest.approx(1.5)

    def test_plain_xml_accepted(self):
        result = ork_import.parse_ork(_read_bytes('hrma_basic.ork'))
        assert 'error' not in result

    def test_zip_path_traversal_rejected(self):
        data = _zip_with({
            '../evil.ork': b'<openrocket/>',
            'rocket.ork': _read_bytes('hrma_basic.ork'),
        })
        result = ork_import.parse_ork(data)
        assert 'error' in result
        assert 'Unsafe path' in result['error']

    def test_zip_bomb_rejected_by_total_size(self, monkeypatch):
        monkeypatch.setattr(ork_import, 'ORK_MAX_UNCOMPRESSED_BYTES', 1000)
        data = _zip_with({'rocket.ork': b'0' * 5000})
        result = ork_import.parse_ork(data)
        assert 'error' in result
        assert 'zip bomb' in result['error']

    def test_gzip_bomb_rejected(self, monkeypatch):
        monkeypatch.setattr(ork_import, 'ORK_MAX_UNCOMPRESSED_BYTES', 1000)
        data = gzip.compress(b'0' * 5000)
        result = ork_import.parse_ork(data)
        assert 'error' in result

    def test_zip_without_rocket_ork_is_error(self):
        data = _zip_with({'readme.txt': b'bos'})
        result = ork_import.parse_ork(data)
        assert 'error' in result
        assert 'rocket.ork' in result['error']

    def test_doctype_rejected_for_security(self):
        xml = (b'<!DOCTYPE openrocket [<!ENTITY x "y">]>'
               b'<openrocket><rocket/></openrocket>')
        result = ork_import.parse_ork(xml)
        assert 'error' in result
        assert 'security' in result['error']

    def test_non_openrocket_root_is_error(self):
        result = ork_import.parse_ork(b'<rocksim/>')
        assert 'error' in result
        assert 'openrocket' in result['error']

    def test_garbage_bytes_is_safe_error(self):
        result = ork_import.parse_ork(b'\x00\x01bu xml degil')
        assert 'error' in result

    def test_empty_input_is_safe_error(self):
        assert 'error' in ork_import.parse_ork(b'')


# ---------------------------------------------------------------------------
# POST /api/import/ork — geçici Flask app ile (app.py'ye dokunmadan)
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(importers_api)
    with app.test_client() as test_client:
        yield test_client


class TestOrkEndpoint:
    def test_multipart_upload_success(self, client):
        data = _zip_with({'rocket.ork': _read_bytes('hrma_basic.ork')})
        response = client.post(
            '/api/import/ork',
            data={'file': (io.BytesIO(data), 'tasarim.ork')},
            content_type='multipart/form-data')
        assert response.status_code == 200
        body = response.get_json()
        assert body['status'] == 'success'
        assert body['source'] == 'ork'
        assert body['filename'] == 'tasarim.ork'
        assert body['aero']['body_diameter'] == pytest.approx(0.1)
        assert isinstance(body['warnings'], list)

    def test_base64_json_upload_success(self, client):
        encoded = base64.b64encode(
            _read_bytes('hrma_basic.ork')).decode('ascii')
        response = client.post('/api/import/ork', json={
            'content_base64': encoded, 'filename': 'tasarim.ork'})
        assert response.status_code == 200
        assert response.get_json()['aero']['body_length'] == \
            pytest.approx(1.5)

    def test_missing_content_is_400(self, client):
        response = client.post('/api/import/ork', json={})
        assert response.status_code == 400
        assert 'content_base64' in response.get_json()['error']

    def test_invalid_base64_is_400(self, client):
        response = client.post('/api/import/ork', json={
            'content_base64': 'bu base64 degil!!'})
        assert response.status_code == 400

    def test_extension_whitelist_enforced_when_filename_given(self, client):
        encoded = base64.b64encode(
            _read_bytes('hrma_basic.ork')).decode('ascii')
        response = client.post('/api/import/ork', json={
            'content_base64': encoded, 'filename': 'tasarim.exe'})
        assert response.status_code == 400
        assert '.ork' in response.get_json()['error']

    def test_broken_file_is_400(self, client):
        encoded = base64.b64encode(b'<rocksim/>').decode('ascii')
        response = client.post('/api/import/ork', json={
            'content_base64': encoded, 'filename': 'x.ork'})
        assert response.status_code == 400
        assert response.get_json()['status'] == 'error'

    def test_oversize_upload_is_413(self, client):
        blob = b'0' * (ORK_MAX_BYTES + 1024)
        response = client.post(
            '/api/import/ork',
            data={'file': (io.BytesIO(blob), 'buyuk.ork')},
            content_type='multipart/form-data')
        assert response.status_code == 413
