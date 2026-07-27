"""/api/export-stl fail-closed bekçisi (v2.6.2).

Neden bu test var:
Uç nokta eskiden DÖRT ayrı yedek yola sahipti ve dördü de HTTP 200 dönüyordu.
CAD üretimi çökerse basitleştirilmiş geometri; STL yazımı çökerse
``generate_basic_stl_content`` (toplam 6 üçgen — iki düzlemde birer
çeyrek-daire yelpazesi; kapalı katı değil, nozul yok, port yok, gövde yok);
o da çökerse TEK üçgenlik 10 mm'lik bir dosya. Ön yüz her durumda
"STL exported successfully" gösteriyordu.

Zarar "yanlış mühendislik kararı"ndan çok "işlem durumu hakkında yalan" ve
toplu/otomatik dışa aktarmada sessiz veri kaybıydı: başarısız bir export,
başarılı bir indirme gibi görünüyordu.

Ayrıca eksik alanlar motor tipine göre sessizce dolduruluyordu
(hybrid→HTPB/N2O, solid→APCP/BATES, liquid→RP-1/LOX) ve port çapı
``0.02·√(F/1000)`` ile tahmin ediliyordu — kaynaksız, üstelik aynı kavram
için kod tabanında üç ayrı sihirli sayı vardı (app.py, cad_visualization.py
x2) ve hiçbiri diğerini tutmuyordu.
"""

import pytest

from hrma.app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(client, motor_data):
    return client.post('/api/export-stl', json={'motor_data': motor_data})


class TestNoSilentDefaults:
    def test_missing_port_diameter_rejected_for_hybrid(self, client):
        """Hibritte port çapı tahmin EDİLMEMELİ — geometriyi o belirliyor."""
        r = _post(client, {
            'motor_type': 'hybrid',
            'chamber_diameter': 0.1,
            'chamber_length': 0.4,
            'thrust': 5000,
        })
        assert r.status_code == 422
        body = r.get_json()
        assert body['status'] == 'incomplete_geometry'
        assert 'port_diameter' in body['missing_fields']

    def test_missing_chamber_geometry_rejected(self, client):
        for motor_type in ('hybrid', 'solid', 'liquid'):
            r = _post(client, {'motor_type': motor_type})
            assert r.status_code in (400, 422), motor_type
            if r.status_code == 422:
                assert r.get_json()['status'] == 'incomplete_geometry'

    def test_zero_dimension_is_not_valid_geometry(self, client):
        """0 çap gerçek bir ölçü değil; sıfır kabul edilirse dejenere katı çıkar."""
        r = _post(client, {
            'motor_type': 'solid',
            'chamber_diameter': 0,
            'chamber_length': 0.4,
        })
        assert r.status_code in (400, 422)


class TestNoFakeStlOnFailure:
    def test_cad_failure_returns_error_not_200(self, client, monkeypatch):
        """CAD çökerse sahte katı DEĞİL, yapılandırılmış hata dönmeli."""
        import hrma.app as appmod

        def boom(*a, **k):
            raise RuntimeError('CAD kernel exploded')

        monkeypatch.setattr(appmod.cad_designer, 'generate_3d_motor_assembly', boom)
        r = _post(client, {
            'motor_type': 'solid',
            'chamber_diameter': 0.1,
            'chamber_length': 0.4,
        })
        assert r.status_code == 500
        assert r.mimetype != 'application/sla', 'çöküşte STL indirilmemeli'
        assert r.get_json()['status'] == 'failed'

    def test_empty_assembly_returns_error(self, client, monkeypatch):
        import hrma.app as appmod
        monkeypatch.setattr(appmod.cad_designer, 'generate_3d_motor_assembly',
                            lambda *a, **k: {})
        r = _post(client, {
            'motor_type': 'solid',
            'chamber_diameter': 0.1,
            'chamber_length': 0.4,
        })
        assert r.status_code == 500
        assert r.get_json()['status'] == 'cad_failed'

    def test_no_stl_written_returns_error(self, client, monkeypatch):
        import hrma.app as appmod
        monkeypatch.setattr(appmod.cad_designer, 'generate_3d_motor_assembly',
                            lambda *a, **k: {'assembly_meshes': {'x': object()}})
        monkeypatch.setattr(appmod.cad_designer, 'export_stl_files',
                            lambda *a, **k: [])
        r = _post(client, {
            'motor_type': 'solid',
            'chamber_diameter': 0.1,
            'chamber_length': 0.4,
        })
        assert r.status_code == 500
        assert r.get_json()['status'] == 'stl_write_failed'


class TestFilenameSafety:
    def test_motor_name_cannot_inject_header(self, client, monkeypatch):
        """motor_name Content-Disposition'a ham girmemeli."""
        import os
        import hrma.app as appmod

        def fake_export(meshes):
            path = os.path.join(os.getcwd(), 'motor_assembly_test.stl')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('solid m\nendsolid m\n')
            return [path]

        monkeypatch.setattr(appmod.cad_designer, 'generate_3d_motor_assembly',
                            lambda *a, **k: {'assembly_meshes': {'x': object()}})
        monkeypatch.setattr(appmod.cad_designer, 'export_stl_files', fake_export)
        r = _post(client, {
            'motor_type': 'solid',
            'chamber_diameter': 0.1,
            'chamber_length': 0.4,
            'motor_name': 'evil"\r\nX-Injected: 1',
        })
        assert r.status_code == 200
        cd = r.headers.get('Content-Disposition', '')
        assert '\r' not in cd and '\n' not in cd
        assert 'X-Injected' not in r.headers
        try:
            os.remove(os.path.join(os.getcwd(), 'motor_assembly_test.stl'))
        except OSError:
            pass


def test_basic_stl_helper_not_reachable_from_endpoint():
    """Sahte STL üreticisi artık uçtan çağrılmamalı.

    Fonksiyon geriye dönük uyumluluk için dosyada kalabilir, ama
    /api/export-stl gövdesinde adı geçmemeli.
    """
    import ast
    import inspect
    import hrma.app as appmod

    src = inspect.getsource(appmod.export_stl)
    tree = ast.parse(src)
    fn = tree.body[0]
    # Docstring'i çıkar — orada isimler AÇIKLAMA olarak geçiyor (geçmişin kaydı).
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant)
                           and isinstance(fn.body[0].value.value, str)) else fn.body
    called = {n.func.id for n in ast.walk(ast.Module(body=body, type_ignores=[]))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert 'generate_basic_stl_content' not in called
    assert 'generate_fallback_cad_geometry' not in called
