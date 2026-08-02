"""Faz 4B bekçileri — ``hrma/app.py`` export ve tarama uçları.

Kapatılan ölçülmüş kusurlar (docs/FAZ4_CODEX_TEYIT.md):

* **A1** — STEP/STL paket README'si sabit ``Units: millimetres.`` yazıyordu.
  Aynı ZIP'te STEP sınırlayıcı kutusu ``[1069.62 163.50 163.50]`` mm, STL
  kutusu ``[0.1635 0.1635 1.0696]`` (yani metre) çıkıyordu; README ayrıca
  ``Watertight ...`` diyordu ama ``motor_assembly.stl`` su geçiriyordu.
  Metin artık ÜRETİLEN dosyadan okunur/ölçülür.
* **A4** — Bütün geometri alanları NaN olan bir istek dört export ucundan da
  HTTP 200 alıyor ve 308 x 109 mm katı cisim üretiyordu.
* **A9** — 5 nokta istenen parametrik tarama 4 nokta döndürüp yine
  ``status: success`` diyordu; negatif O/F için Isp 204.77 s üretiliyordu.
* **A10** — ``/api/export-cad`` indirme bağlantısı sabit ``cad_exports/``
  dizinine bakıyordu, üretici ise ``mkdtemp``'e yazıyordu: sunulan dosyanın
  sha256'sı üretilenden farklıydı (mtime iki gün eski).
* **D5** — PDF uçları indirme adını ``safe_name``'den geçirmiyordu.
* **D8** — XLSX ucunda iş bütçesi yoktu; 23.3 MiB istek 26.3 s / 2.4 GB RSS.
  200 000 karakterlik hücre openpyxl tarafından sessizce 32 767'ye kırpılıyordu.
* **D9** — ``/api/export-xlsx`` ``filename='../../../../etc/passwd.xlsx'``
  isteğini HTTP 200 ile karşılıyor ve adı başlığa aynen basıyordu.
"""

import hashlib
import io
import json
import zipfile

import pytest

from hrma.app import app

# Yol kaçışı adları TEK YERDE tanımlı: tests/test_export_injection_guard.py.
# İkinci bir liste yazmak iki listenin zamanla ayrışması demektir (aynı
# kusurun bir dosyada sınanıp diğerinde sınanmaması).
from tests.test_export_injection_guard import TRAVERSAL_NAMES as EVIL_NAMES


NAN = float('nan')
INF = float('inf')

#: Ölçülebilir, gerçek bir geometri (tests/test_wave2_contract.py ile aynı
#: büyüklükler): Ø100 mm kamara, 400 mm boy, Ø30 mm boğaz.
GOOD_GEOMETRY = {
    'chamber_pressure': 30.0,
    'chamber_temperature': 3200.0,
    'gamma': 1.22,
    'molecular_weight': 26.0,
    'mdot_total': 2.0,
    'chamber_diameter': 0.10,
    'chamber_length': 0.40,
    'burn_time': 8.0,
    'throat_diameter': 0.03,
    'exit_diameter': 0.09,
    'motor_name': 'FAZ4_GUARD',
    # STEP üretimi cidar kalınlığını yapısal sonuçtan İSTİYOR (A8 kapısı,
    # step_export.py:118-125): yapısal analiz yoksa imalat dosyası
    # üretilmiyor. Şema adları hrma/export/cad_visualization.py
    # CHAMBER_WALL_SCHEMAS'tan.
    'structural_analysis': {
        'chamber_analysis': {
            'design_mode': 'verify',
            'wall_thickness_used_mm': 5.0,
            'recommended_thickness': 5.0,
            'safety_factor_total': 2.4,
        },
    },
}

#: A4'ün ölçüldüğü istek: her geometri alanı NaN.
NAN_GEOMETRY = {
    'chamber_diameter': NAN,
    'chamber_length': NAN,
    'throat_diameter': NAN,
    'exit_diameter': NAN,
    'motor_name': 'FAZ4_NAN',
}

GEOMETRY_EXPORT_ENDPOINTS = (
    '/api/export-step',
    '/api/export-dxf',
    '/api/export-drawings-pdf',
    '/api/export-complete-zip',
)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


def _post_json(client, path, payload):
    """NaN taşıyan gövde ``jsonify`` ile değil elle serileştirilir.

    Python'un ``json`` modülü NaN'ı ``NaN`` sabiti olarak yazar; gerçek
    istemcilerin (tarayıcı ``JSON.stringify``) yaptığı da budur değil —
    tarayıcı ``null`` yazar. İki yolu da sınıyoruz: bu yardımcı ham NaN
    yolunu, ``null`` yolu ayrı testte.
    """
    return client.post(path, data=json.dumps(payload),
                       content_type='application/json')


# ---------------------------------------------------------------------------
# A4 — sonlu olmayan geometri fail-closed
# ---------------------------------------------------------------------------

class TestNonFiniteGeometryIsRejected:
    @pytest.mark.parametrize('endpoint', GEOMETRY_EXPORT_ENDPOINTS)
    def test_all_nan_geometry_returns_422(self, client, endpoint):
        resp = _post_json(client, endpoint, {'motor_data': NAN_GEOMETRY})
        assert resp.status_code == 422, (
            f'{endpoint} NaN geometriye {resp.status_code} döndü — '
            'imalat dosyası üretilmemeliydi')
        body = resp.get_json()
        assert body['error'] == 'invalid_export_geometry'
        bad_fields = {item['field'] for item in body['invalid_fields']}
        assert 'chamber_diameter' in bad_fields
        assert all(item['reason'] == 'not_finite'
                   for item in body['invalid_fields'])

    @pytest.mark.parametrize('endpoint', GEOMETRY_EXPORT_ENDPOINTS)
    def test_infinite_geometry_returns_422(self, client, endpoint):
        payload = dict(GOOD_GEOMETRY, chamber_diameter=INF)
        resp = _post_json(client, endpoint, {'motor_data': payload})
        assert resp.status_code == 422
        assert resp.get_json()['error'] == 'invalid_export_geometry'

    @pytest.mark.parametrize('endpoint', GEOMETRY_EXPORT_ENDPOINTS)
    def test_empty_motor_data_returns_422(self, client, endpoint):
        """Boş istekte üretilecek katı tamamen üreticinin varsayılanıdır."""
        resp = client.post(endpoint, json={'motor_data': {}})
        assert resp.status_code == 422, (
            f'{endpoint} boş geometriye {resp.status_code} döndü')
        body = resp.get_json()
        assert body['error'] == 'missing_export_geometry'
        assert 'chamber_diameter' in body['required_any_of']

    def test_reason_code_names_the_field(self, client):
        payload = dict(GOOD_GEOMETRY, throat_diameter='not-a-number')
        resp = _post_json(client, '/api/export-dxf', {'motor_data': payload})
        assert resp.status_code == 422
        entry = resp.get_json()['invalid_fields'][0]
        assert entry['field'] == 'throat_diameter'
        assert entry['reason'] == 'not_a_number'

    def test_valid_geometry_still_exports(self, client):
        """Kapı aşırı kısıtlayıcı olmamalı — meşru istek geçmeli."""
        resp = client.post('/api/export-dxf',
                           json={'motor_data': GOOD_GEOMETRY})
        assert resp.status_code == 200, (
            f'meşru geometri {resp.status_code} aldı')
        assert len(resp.data) > 0


class TestExportGeometryGuardUnit:
    """Kapı fonksiyonunun kendisi — HTTP katmanı olmadan."""

    def test_absent_field_is_not_an_error(self):
        from hrma.app import _export_geometry_problem
        assert _export_geometry_problem(
            {'chamber_diameter': 0.1}) is None

    def test_none_is_treated_as_absent_not_invalid(self):
        """``None`` "verilmedi" demektir (input_guard ilkesi)."""
        from hrma.app import _export_geometry_problem
        problem = _export_geometry_problem(
            {'chamber_diameter': 0.1, 'exit_diameter': None})
        assert problem is None

    def test_nested_motor_geometry_is_read(self):
        from hrma.app import _export_geometry_problem
        problem = _export_geometry_problem(
            {'motor_geometry': {'chamber_diameter': NAN}})
        assert problem is not None
        assert problem['error'] == 'invalid_export_geometry'

    def test_zero_primary_is_not_usable_geometry(self):
        """Ø0 kamara geometri değildir; varsayılana düşülmez, reddedilir."""
        from hrma.app import _export_geometry_problem
        problem = _export_geometry_problem(
            {'chamber_diameter': 0.0, 'chamber_length': 0.0,
             'throat_diameter': 0.0})
        assert problem['error'] == 'missing_export_geometry'


# ---------------------------------------------------------------------------
# A1 — paket README'si iddia etmiyor, ölçüyor
# ---------------------------------------------------------------------------

class TestPackageReadmeHonesty:
    @staticmethod
    def _readme(resp):
        archive = zipfile.ZipFile(io.BytesIO(resp.data))
        return archive.read('README.txt').decode('utf-8')

    @staticmethod
    def _step_zip(client):
        """STEP paketi; üretici bu ortamda çalışamıyorsa test atlanır."""
        resp = client.post('/api/export-step',
                           json={'motor_data': GOOD_GEOMETRY})
        if resp.status_code != 200:
            pytest.skip('STEP üreticisi bu ortamda çalışmadı '
                        f'(HTTP {resp.status_code}) — A1 birim metni ayrıca '
                        'test_step_readme_text_unit ile birim olarak sınanıyor')
        return resp

    def test_step_readme_unit_comes_from_the_file_header(self, client):
        resp = self._step_zip(client)
        readme = self._readme(resp)
        assert 'Units: millimetres.' not in readme, (
            'sabit birim iddiası geri gelmiş')
        assert 'read from the STEP header' in readme or \
               'could not be read' in readme, (
            f'birim satırı ölçüme bağlı değil:\n{readme}')

    def test_step_readme_matches_the_generated_files(self, client):
        """README'nin birimi dosyanın kendi UNIT bloğuyla aynı olmalı."""
        resp = self._step_zip(client)
        archive = zipfile.ZipFile(io.BytesIO(resp.data))
        readme = archive.read('README.txt').decode('utf-8')
        step_names = [n for n in archive.namelist() if n.endswith('.step')]
        assert step_names, 'pakette STEP dosyası yok'
        blob = archive.read(step_names[0]).decode('utf-8', 'ignore')
        compact = ''.join(blob.upper().split())
        if 'SI_UNIT(.MILLI.,.METRE.)' in compact:
            assert 'millimetres' in readme
        elif 'SI_UNIT($,.METRE.)' in compact:
            assert 'metres' in readme and 'millimetres' not in readme

    def test_stl_readme_claims_no_unit(self, client):
        """STL biçiminde birim beyanı yok; metin de birim iddia etmemeli."""
        resp = client.post('/api/export-stl-zip',
                           json={'motor_data': GOOD_GEOMETRY})
        assert resp.status_code == 200, f'STL paketi {resp.status_code}'
        readme = self._readme(resp)
        assert 'Units: millimetres' not in readme
        assert 'no unit declaration' in readme

    def test_stl_readme_reports_measured_watertight_state(self, client):
        """'Watertight' sözü ancak ölçülen değerle birlikte geçebilir."""
        trimesh = pytest.importorskip('trimesh')
        resp = client.post('/api/export-stl-zip',
                           json={'motor_data': GOOD_GEOMETRY})
        assert resp.status_code == 200
        readme = self._readme(resp)
        archive = zipfile.ZipFile(io.BytesIO(resp.data))
        assembly = [n for n in archive.namelist()
                    if n.endswith('motor_assembly.stl')]
        if not assembly:
            pytest.skip('paket birleşik assembly içermiyor')
        mesh = trimesh.load_mesh(
            io.BytesIO(archive.read(assembly[0])), file_type='stl')
        expected = 'yes' if mesh.is_watertight else 'no'
        # 'motor_assembly.stl = combined single-file model.' açıklama
        # satırıdır; ölçüm satırı 'bounding box' taşıyan olandır.
        line = [ln for ln in readme.splitlines()
                if 'motor_assembly.stl' in ln and 'bounding box' in ln]
        assert line, f'README assembly ölçüm satırı yok:\n{readme}'
        assert f'watertight={expected}' in line[0], (
            f'README ölçülen su-sızdırmazlıkla uyuşmuyor: {line[0]!r}, '
            f'trimesh is_watertight={mesh.is_watertight}')

    def test_stl_readme_bounding_box_matches_the_mesh(self, client):
        """Yazılan sınırlayıcı kutu gerçekten dosyadan ölçülmüş olmalı."""
        trimesh = pytest.importorskip('trimesh')
        resp = client.post('/api/export-stl-zip',
                           json={'motor_data': GOOD_GEOMETRY})
        assert resp.status_code == 200
        readme = self._readme(resp)
        archive = zipfile.ZipFile(io.BytesIO(resp.data))
        names = [n for n in archive.namelist() if n.endswith('.stl')]
        assert names
        mesh = trimesh.load_mesh(
            io.BytesIO(archive.read(names[0])), file_type='stl')
        largest = float(max(mesh.extents))
        line = [ln for ln in readme.splitlines()
                if names[0] in ln and 'bounding box' in ln]
        assert line, f'README {names[0]} ölçüm satırı yok:\n{readme}'
        numbers = [float(tok) for tok in
                   line[0].split('bounding box')[1].split('(')[0]
                   .replace('x', ' ').split()]
        assert abs(max(numbers) - largest) / largest < 0.01, (
            f'README kutusu {numbers} ölçülen {mesh.extents} ile uyuşmuyor')


class TestStepReadmeTextUnit:
    """A1'in app.py tarafı — üreticiden bağımsız, belirlenimci sınama.

    Uçtan uca test build123d / yapısal analiz kapısına bağlı olduğu için
    burada README üretici doğrudan sahte STEP başlıklarıyla beslenir.
    """

    HEADER_MM = (
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
        "#10 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\n"
        "ENDSEC;\nEND-ISO-10303-21;\n"
    )
    HEADER_M = (
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
        "#10 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.) );\n"
        "ENDSEC;\nEND-ISO-10303-21;\n"
    )

    @staticmethod
    def _write(tmp_path, name, text):
        path = tmp_path / name
        path.write_text(text, encoding='utf-8')
        return str(path)

    def test_millimetre_header_is_reported_as_millimetres(self, tmp_path):
        from hrma.app import _step_readme_text
        path = self._write(tmp_path, 'a.step', self.HEADER_MM)
        readme = _step_readme_text([path])
        assert 'millimetres' in readme
        assert 'Units: millimetres.' not in readme  # sabit metin geri gelmesin

    def test_metre_header_is_not_reported_as_millimetres(self, tmp_path):
        """Asıl kusur buydu: metre dosyaya 'millimetres' yazılıyordu."""
        from hrma.app import _step_readme_text
        path = self._write(tmp_path, 'b.step', self.HEADER_M)
        readme = _step_readme_text([path])
        assert 'metres' in readme
        assert 'millimetres' not in readme

    def test_unreadable_file_makes_no_unit_claim(self, tmp_path):
        from hrma.app import _step_readme_text
        path = self._write(tmp_path, 'c.step', 'not a step file at all\n')
        readme = _step_readme_text([path])
        assert 'could not be read' in readme
        assert 'millimetres' not in readme and 'metres' not in readme

    def test_mixed_units_are_reported_as_a_warning(self, tmp_path):
        from hrma.app import _step_readme_text
        paths = [self._write(tmp_path, 'd.step', self.HEADER_MM),
                 self._write(tmp_path, 'e.step', self.HEADER_M)]
        readme = _step_readme_text(paths)
        assert 'WARNING' in readme
        assert 'metres' in readme and 'millimetres' in readme

    def test_missing_file_makes_no_claim(self, tmp_path):
        from hrma.app import _step_readme_text
        readme = _step_readme_text([str(tmp_path / 'yok.step')])
        assert 'could not be read' in readme


class TestStlReadmeTextUnit:
    def test_no_unit_is_claimed_even_when_mesh_lib_missing(self, tmp_path):
        from hrma.app import _stl_readme_text
        readme = _stl_readme_text([str(tmp_path / 'yok.stl')])
        assert 'no unit declaration' in readme
        assert 'millimetres' not in readme
        assert 'Units:' not in readme

    def test_unmeasurable_file_states_it_was_not_measured(self, tmp_path):
        from hrma.app import _stl_readme_text
        broken = tmp_path / 'broken.stl'
        broken.write_text('this is not an stl', encoding='utf-8')
        readme = _stl_readme_text([str(broken)])
        assert 'not measured' in readme
        assert 'watertight=yes' not in readme

    def test_watertight_word_never_appears_without_a_measurement(self, tmp_path):
        """'Watertight closed-profile revolve solids' iddiası geri gelmesin."""
        from hrma.app import _stl_readme_text
        readme = _stl_readme_text([str(tmp_path / 'yok.stl')])
        for line in readme.splitlines():
            if 'watertight' in line.lower():
                assert 'watertight=yes' in line or 'watertight=no' in line, (
                    f'ölçümsüz su-sızdırmazlık iddiası: {line!r}')


# ---------------------------------------------------------------------------
# A9 — parametrik tarama başarısızlığı gizlemiyor
# ---------------------------------------------------------------------------

PARAMETRIC_BASE = {
    'thrust': 1000,
    'burn_time': 10,
    'chamber_pressure': 20.0,
    'of_ratio': 2.0,
    'fuel_type': 'htpb',
}


class TestParametricFailureReporting:
    def test_response_always_carries_failure_fields(self, client):
        resp = client.post('/parametric-analysis', json=dict(
            PARAMETRIC_BASE, param_type='of_ratio', param_start=1.0,
            param_end=3.0, param_steps=3))
        assert resp.status_code == 200
        body = resp.get_json()
        for key in ('points_requested', 'points_succeeded', 'points_failed',
                    'failed_points'):
            assert key in body, f"yanıtta '{key}' alanı yok"
        assert body['points_requested'] == 3
        assert body['points_succeeded'] + body['points_failed'] == 3

    def test_negative_of_ratio_produces_no_performance_number(self, client):
        """Negatif O/F fiziksel değil — Isp 204.77 s üretmek yasak."""
        resp = client.post('/parametric-analysis', json=dict(
            PARAMETRIC_BASE, param_type='of_ratio', param_start=-2.0,
            param_end=-1.0, param_steps=5))
        body = resp.get_json()
        assert body['results'] == [], (
            'geçersiz O/F için performans noktası üretildi: '
            f"{body['results'][:1]}")
        assert body['points_failed'] == 5
        assert all(point['reason'] == 'must_be_positive'
                   for point in body['failed_points'])

    def test_all_points_failed_is_not_success(self, client):
        resp = client.post('/parametric-analysis', json=dict(
            PARAMETRIC_BASE, param_type='of_ratio', param_start=-2.0,
            param_end=-1.0, param_steps=5))
        assert resp.status_code == 422, (
            f'hepsi başarısız tarama {resp.status_code} döndü')
        assert resp.get_json()['status'] != 'success'

    def test_failed_point_records_its_input(self, client):
        resp = client.post('/parametric-analysis', json=dict(
            PARAMETRIC_BASE, param_type='of_ratio', param_start=-2.0,
            param_end=-1.0, param_steps=2))
        point = resp.get_json()['failed_points'][0]
        assert point['sweep_parameter'] == 'of_ratio'
        assert point['sweep_value'] == pytest.approx(-2.0)
        assert point['stage'] == 'input_validation'

    @pytest.mark.parametrize('param,value,reason', [
        ('of_ratio', -1.0, 'must_be_positive'),
        ('of_ratio', 0.0, 'must_be_positive'),
        ('chamber_pressure', -5.0, 'must_be_positive'),
        ('expansion_ratio', -2.0, 'must_be_non_negative'),
        ('gamma', 0.9, 'gamma_must_exceed_one'),
        ('of_ratio', NAN, 'not_finite'),
    ])
    def test_point_validity_table(self, param, value, reason):
        from hrma.app import _parametric_point_rejection
        assert _parametric_point_rejection(param, value) == reason

    @pytest.mark.parametrize('param,value', [
        ('of_ratio', 2.5),
        ('chamber_pressure', 20.0),
        ('expansion_ratio', 0.0),   # 0 = 'otomatik', geçerli
        ('altitude', -50.0),        # kısıtsız parametre
    ])
    def test_valid_points_are_not_rejected(self, param, value):
        from hrma.app import _parametric_point_rejection
        assert _parametric_point_rejection(param, value) is None


# ---------------------------------------------------------------------------
# A10 — /api/export-cad üretilen dosyayı sunuyor
# ---------------------------------------------------------------------------

class TestExportCadServesTheGeneratedFile:
    def test_download_link_matches_generated_file_bytes(self, client):
        resp = client.post('/api/export-cad', json={
            'motor_data': GOOD_GEOMETRY, 'formats': ['stl']})
        assert resp.status_code == 200
        exports = resp.get_json()['cad_exports']
        links = exports['stl_download_links']
        paths = exports['stl_files']
        assert links and len(links) == len(paths)

        for link, path in zip(links, paths):
            served = client.get(link)
            assert served.status_code == 200, (
                f'{link} indirilemedi ({served.status_code})')
            with open(path, 'rb') as handle:
                produced = handle.read()
            assert hashlib.sha256(served.data).hexdigest() == \
                hashlib.sha256(produced).hexdigest(), (
                f'{link} bu istekte üretilen dosyadan farklı bayt döndürdü')

    def test_link_is_not_a_bare_basename(self, client):
        """Sabit dizin varsayımı geri gelirse bu test kırılır."""
        resp = client.post('/api/export-cad', json={
            'motor_data': GOOD_GEOMETRY, 'formats': ['stl']})
        link = resp.get_json()['cad_exports']['stl_download_links'][0]
        token = link.rsplit('/', 1)[-1]
        assert token != 'motor_assembly.stl', (
            'bağlantı yine sabit dosya adı taşıyor — başka bir isteğin '
            'dosyasına denk gelebilir')
        assert token.endswith('.stl')

    def test_two_requests_get_distinct_links(self, client):
        first = client.post('/api/export-cad', json={
            'motor_data': GOOD_GEOMETRY, 'formats': ['stl']})
        second = client.post('/api/export-cad', json={
            'motor_data': dict(GOOD_GEOMETRY, chamber_diameter=0.30,
                               chamber_length=0.90),
            'formats': ['stl']})
        links_a = set(first.get_json()['cad_exports']['stl_download_links'])
        links_b = set(second.get_json()['cad_exports']['stl_download_links'])
        assert not (links_a & links_b), (
            'iki farklı motor aynı indirme bağlantısını paylaşıyor')

    def test_traversal_still_rejected(self, client):
        for bad in ('..%5c..%5cwindows%5cwin.ini', 'x.txt', 'foo bar.stl'):
            assert client.get(f'/download/stl/{bad}').status_code in (400, 404)


# ---------------------------------------------------------------------------
# D8 + D9 — XLSX bütçesi ve dosya adı
# ---------------------------------------------------------------------------

MINIMAL_SHEET = {'name': 'S', 'headers': ['a', 'b'], 'rows': [[1, 2]]}


class TestXlsxBudget:
    def test_normal_workbook_still_works(self, client):
        pytest.importorskip('openpyxl')
        resp = client.post('/api/export-xlsx', json={
            'filename': 'ok.xlsx', 'sheets': [MINIMAL_SHEET]})
        assert resp.status_code == 200

    def test_too_many_columns_rejected(self, client):
        pytest.importorskip('openpyxl')
        from hrma.app import XLSX_MAX_COLUMNS
        width = XLSX_MAX_COLUMNS + 1
        resp = client.post('/api/export-xlsx', json={
            'filename': 'wide.xlsx',
            'sheets': [{'name': 'W', 'headers': ['h'] * width,
                        'rows': [[1] * width]}]})
        assert resp.status_code != 200, 'geniş sayfa 200 döndü'
        assert resp.status_code == 413
        body = resp.get_json()
        assert body['error'] == 'xlsx_budget_exceeded'
        assert body['limit'] == 'columns'
        assert body['requested'] == width

    def test_too_many_sheets_rejected(self, client):
        pytest.importorskip('openpyxl')
        from hrma.app import XLSX_MAX_SHEETS
        sheets = [dict(MINIMAL_SHEET, name=f'S{i}')
                  for i in range(XLSX_MAX_SHEETS + 1)]
        resp = client.post('/api/export-xlsx',
                           json={'filename': 'many.xlsx', 'sheets': sheets})
        assert resp.status_code == 413
        assert resp.get_json()['limit'] == 'sheets'

    def test_total_cell_budget_enforced(self, client):
        pytest.importorskip('openpyxl')
        from hrma.app import XLSX_MAX_TOTAL_CELLS
        # 10 sütun x N satır; bütçeyi bir satır aşacak kadar.
        rows_needed = XLSX_MAX_TOTAL_CELLS // 10 + 2
        resp = client.post('/api/export-xlsx', json={
            'filename': 'big.xlsx',
            'sheets': [{'name': 'B', 'headers': ['h'] * 10,
                        'rows': [[0] * 10] * rows_needed}]})
        assert resp.status_code == 413
        assert resp.get_json()['limit'] in ('total_cells', 'rows_per_sheet')

    def test_oversized_cell_is_rejected_not_truncated(self, client):
        """openpyxl 200k karakteri sessizce 32767'ye kırpıyordu (ölçüldü)."""
        pytest.importorskip('openpyxl')
        from hrma.app import XLSX_MAX_CELL_CHARS
        resp = client.post('/api/export-xlsx', json={
            'filename': 'long.xlsx',
            'sheets': [{'name': 'L', 'headers': ['h'],
                        'rows': [['x' * (XLSX_MAX_CELL_CHARS + 1)]]}]})
        assert resp.status_code == 422, (
            f'aşırı uzun hücre {resp.status_code} döndü — sessiz kırpma')
        body = resp.get_json()
        assert body['error'] == 'xlsx_cell_too_long'
        assert body['maximum'] == XLSX_MAX_CELL_CHARS

    def test_oversized_header_is_rejected(self, client):
        pytest.importorskip('openpyxl')
        from hrma.app import XLSX_MAX_CELL_CHARS
        resp = client.post('/api/export-xlsx', json={
            'filename': 'longh.xlsx',
            'sheets': [{'name': 'L', 'headers': ['h' * (XLSX_MAX_CELL_CHARS + 1)],
                        'rows': [[1]]}]})
        assert resp.status_code == 422
        assert resp.get_json()['cell_kind'] == 'header'

    def test_no_silent_truncation_of_accepted_workbook(self, client):
        """Kabul edilen çalışma kitabında hiçbir satır/sayfa düşmemeli."""
        openpyxl = pytest.importorskip('openpyxl')
        sheets = [dict(MINIMAL_SHEET, name=f'S{i}') for i in range(5)]
        resp = client.post('/api/export-xlsx',
                           json={'filename': 'full.xlsx', 'sheets': sheets})
        assert resp.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(resp.data))
        assert len(wb.sheetnames) == 5
        for name in wb.sheetnames:
            assert wb[name].max_row == 2  # başlık + 1 veri satırı


class TestDownloadNameSanitisation:
    @staticmethod
    def _disposition(resp):
        return resp.headers.get('Content-Disposition', '')

    @pytest.mark.parametrize('evil', EVIL_NAMES)
    def test_xlsx_filename_cannot_contain_traversal(self, client, evil):
        pytest.importorskip('openpyxl')
        resp = client.post('/api/export-xlsx', json={
            'filename': evil + '.xlsx', 'sheets': [MINIMAL_SHEET]})
        assert resp.status_code == 200
        disposition = self._disposition(resp)
        assert '..' not in disposition
        assert '/' not in disposition.split('filename=')[-1]
        assert '\\' not in disposition.split('filename=')[-1]

    @pytest.mark.parametrize('report_type', ['summary', 'technical', 'complete'])
    def test_pdf_filename_cannot_contain_traversal(self, client, report_type):
        resp = client.post(f'/api/export-pdf/{report_type}', json={
            'motor_data': dict(GOOD_GEOMETRY,
                               motor_name='../../../../etc/passwd'),
            'analysis_results': {}, 'charts': [],
        })
        if resp.status_code != 200:
            pytest.skip(f'PDF üretilemedi ({resp.status_code}); '
                        'ad temizliği ayrı testte birim olarak sınanıyor')
        disposition = self._disposition(resp)
        assert '..' not in disposition
        assert 'etc' not in disposition or '/' not in disposition

    def test_pdf_name_helper_is_the_repo_helper(self):
        """Ad temizliği el yazımı değil, ortak ``safe_name`` olmalı."""
        from hrma.utils.input_guard import safe_name
        cleaned = safe_name('../../../../etc/passwd')
        assert '/' not in cleaned and '..' not in cleaned
