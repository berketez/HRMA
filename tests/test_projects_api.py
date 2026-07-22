"""
hrma/utils/projects_api.py Blueprint testleri (geçici Flask app ile).

Kapsam:
  - GET /api/projects (boş + dolu + bozuk dosya işareti)
  - POST /api/projects/save (başarı, 409 overwrite koruması, 400 şema/ad,
    413 boyut, JSON olmayan gövde)
  - GET /api/projects/load/<name> (source etiketi + warnings + estimated,
    404, 422 bozuk dosya)
  - POST /api/projects/delete (.trash'e taşıma, 404)

Blueprint gerçek app.py'ye DOKUNMADAN geçici bir Flask uygulamasına
kaydedilerek test edilir. Tüm veriler sentetiktir.
"""

import json
import os

import pytest
from flask import Flask

from hrma.utils import projects as store
from hrma.utils.projects_api import projects_api


@pytest.fixture()
def proj_dir(tmp_path, monkeypatch):
    d = tmp_path / 'projects'
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(d))
    return d


@pytest.fixture()
def client(proj_dir):
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(projects_api)
    with app.test_client() as c:
        yield c


def make_payload(**overrides):
    payload = {
        'format': 'hrma-project',
        'format_version': 1,
        'motor_type': 'liquid',
        'inputs': {
            'fields': {'thrust': 5000.0, 'oxidizer': 'lox', 'stages': 1},
        },
        'results_summary': {'isp': 311.0},
    }
    payload.update(overrides)
    return payload


class TestList:
    def test_empty_list(self, client):
        r = client.get('/api/projects')
        assert r.status_code == 200
        j = r.get_json()
        assert j == {'projects': [], 'count': 0}

    def test_list_after_save(self, client):
        client.post('/api/projects/save',
                    json={'name': 'listem', 'payload': make_payload()})
        r = client.get('/api/projects')
        j = r.get_json()
        assert j['count'] == 1
        assert j['projects'][0]['name'] == 'listem'
        assert j['projects'][0]['motor_type'] == 'liquid'
        assert j['projects'][0]['corrupt'] is False

    def test_corrupt_file_marked_not_fatal(self, client, proj_dir):
        client.post('/api/projects/save',
                    json={'name': 'saglam', 'payload': make_payload()})
        with open(proj_dir / 'kirik.hrma', 'w', encoding='utf-8') as f:
            f.write('{gecersiz json')
        r = client.get('/api/projects')
        assert r.status_code == 200
        by_name = {i['name']: i for i in r.get_json()['projects']}
        assert by_name['kirik']['corrupt'] is True
        assert by_name['saglam']['corrupt'] is False


class TestSave:
    def test_save_ok(self, client, proj_dir):
        r = client.post('/api/projects/save',
                        json={'name': 'yeni motor', 'payload': make_payload()})
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'saved'
        assert j['name'] == 'yeni motor'
        assert j['app_version']
        assert j['created_at'] and j['updated_at']
        assert (proj_dir / 'yeni motor.hrma').exists()

    def test_duplicate_without_overwrite_409(self, client):
        body = {'name': 'cift', 'payload': make_payload()}
        assert client.post('/api/projects/save', json=body).status_code == 200
        r = client.post('/api/projects/save', json=body)
        assert r.status_code == 409
        assert 'overwrite' in r.get_json()['error']

    def test_duplicate_with_overwrite_200(self, client):
        body = {'name': 'cift2', 'payload': make_payload()}
        assert client.post('/api/projects/save', json=body).status_code == 200
        body['overwrite'] = True
        body['payload'] = make_payload(motor_type='solid')
        r = client.post('/api/projects/save', json=body)
        assert r.status_code == 200
        r2 = client.get('/api/projects/load/cift2')
        assert r2.get_json()['project']['motor_type'] == 'solid'

    @pytest.mark.parametrize('name', ['../kacis', '/mutlak/yol', '.gizli', 'CON', 'a' * 81])
    def test_bad_name_400(self, client, name):
        r = client.post('/api/projects/save',
                        json={'name': name, 'payload': make_payload()})
        assert r.status_code == 400
        assert 'error' in r.get_json()

    def test_bad_schema_400(self, client):
        r = client.post('/api/projects/save',
                        json={'name': 'sema', 'payload': {'format': 'yanlis'}})
        assert r.status_code == 400
        assert 'error' in r.get_json()

    def test_missing_fields_400(self, client):
        assert client.post('/api/projects/save',
                           json={'payload': make_payload()}).status_code == 400
        assert client.post('/api/projects/save',
                           json={'name': 'x'}).status_code == 400

    def test_non_json_body_400(self, client):
        r = client.post('/api/projects/save', data='duz metin',
                        content_type='text/plain')
        assert r.status_code == 400

    def test_overwrite_must_be_boolean(self, client):
        r = client.post('/api/projects/save', json={
            'name': 'bayrak', 'payload': make_payload(), 'overwrite': 'evet'})
        assert r.status_code == 400

    def test_payload_over_limit_413(self, client):
        payload = make_payload()
        payload['inputs']['ui_state'] = {'big': 'x' * (store.MAX_PROJECT_BYTES + 100)}
        r = client.post('/api/projects/save',
                        json={'name': 'devasa', 'payload': payload})
        assert r.status_code == 413


class TestLoad:
    def test_load_roundtrip_with_source_and_warnings(self, client):
        payload = make_payload()
        client.post('/api/projects/save', json={'name': 'tur', 'payload': payload})
        r = client.get('/api/projects/load/tur')
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'loaded'
        assert j['source'] == 'hrma-project-file'
        assert j['warnings'] == []
        assert j['estimated'] == []  # sessiz doldurma yok
        # inputs byte-eşit gidiş-dönüş
        sent = json.dumps(payload['inputs'], sort_keys=True).encode('utf-8')
        got = json.dumps(j['project']['inputs'], sort_keys=True).encode('utf-8')
        assert sent == got

    def test_load_version_mismatch_warning(self, client, proj_dir):
        client.post('/api/projects/save',
                    json={'name': 'eski', 'payload': make_payload()})
        path = proj_dir / 'eski.hrma'
        doc = json.load(open(path, encoding='utf-8'))
        doc['app_version'] = '0.0.1'
        json.dump(doc, open(path, 'w', encoding='utf-8'))
        r = client.get('/api/projects/load/eski')
        assert r.status_code == 200
        assert any('0.0.1' in w for w in r.get_json()['warnings'])

    def test_load_missing_404(self, client):
        r = client.get('/api/projects/load/olmayan proje')
        assert r.status_code == 404
        assert 'error' in r.get_json()

    def test_load_bad_name_400(self, client):
        r = client.get('/api/projects/load/.gizli')
        assert r.status_code == 400

    def test_load_corrupt_422(self, client, proj_dir):
        store.projects_dir()
        with open(proj_dir / 'kirik.hrma', 'w', encoding='utf-8') as f:
            f.write('{bozuk')
        r = client.get('/api/projects/load/kirik')
        assert r.status_code == 422
        assert 'error' in r.get_json()


class TestDelete:
    def test_delete_moves_to_trash(self, client, proj_dir):
        client.post('/api/projects/save',
                    json={'name': 'gidici', 'payload': make_payload()})
        r = client.post('/api/projects/delete', json={'name': 'gidici'})
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'deleted'
        assert j['trashed_to'].startswith('.trash')
        assert not (proj_dir / 'gidici.hrma').exists()
        assert (proj_dir / j['trashed_to']).exists()  # kalıcı silinmedi

    def test_delete_missing_404(self, client):
        r = client.post('/api/projects/delete', json={'name': 'hayalet'})
        assert r.status_code == 404

    def test_delete_missing_name_400(self, client):
        r = client.post('/api/projects/delete', json={})
        assert r.status_code == 400

    def test_delete_bad_name_400(self, client):
        r = client.post('/api/projects/delete', json={'name': '../kacis'})
        assert r.status_code == 400
