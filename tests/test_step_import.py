"""STEP içe aktarma (hrma/importers/step_import.py + step_api.py) testleri.

Fixture stratejisi: STEP dosyaları TEST İÇİNDE build123d ile SENTETİK üretilir
(ağdan indirme yok) ve tests/fixtures/step/ altına yazılır. Bilinen ölçülü
eksenel simetrik "motor benzeri" katı çizilir, STEP'e yazılır, analyze_step
ile geri okunur ve öneriler bilinen ölçülerle +-%1 doğrulanır.

Modüller paket import'una BAĞIMLI OLMADAN dosya yolundan yüklenir
(hrma/importers/__init__.py başka bir ajanın dosyasıdır; çakışma yaratılmaz).
"""

import importlib.util
import io
import math
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMPORTERS_DIR = os.path.join(REPO_ROOT, 'hrma', 'importers')
FIXTURES_DIR = os.path.join(REPO_ROOT, 'tests', 'fixtures', 'step')

#: STEP ölçü doğrulama toleransı (görev tanımı: +-%1). Ad bilinçli olarak
#: benzersizdir (REL_TOL adı başka paketlerde farklı anlamda kullanılıyor).
DIM_CHECK_REL_TOL = 0.01


def _load_by_path(filename, modname):
    """Modülü dosya yolundan yükler (paket __init__ gerektirmez)."""
    spec = importlib.util.spec_from_file_location(
        modname, os.path.join(IMPORTERS_DIR, filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


step_import = _load_by_path('step_import.py', 'hrma_test_step_import')
step_api = _load_by_path('step_api.py', 'hrma_test_step_api')


def _approx(actual, expected):
    assert actual == pytest.approx(expected, rel=DIM_CHECK_REL_TOL), (
        f'{actual} != {expected} (+-{DIM_CHECK_REL_TOL * 100:.0f}%)')


# ---------------------------------------------------------------------------
# Sentetik fixture üretimi (build123d gerekir; yoksa ilgili testler atlanır)
# ---------------------------------------------------------------------------

#: Motor fixture'ının bilinen ölçüleri (mm) — üretim ve doğrulama tek kaynak.
MOTOR_DIMS = {
    'chamber_diameter': 100.0,   # oda iç çapı
    'chamber_length': 100.0,     # oda silindir boyu (z 0..100)
    'throat_diameter': 20.0,     # boğaz çapı (z=130)
    'exit_diameter': 50.0,       # çıkış çapı (z=190; 190..195 dudak silindiri)
    'wall_thickness': 5.0,       # dış yarıçap 55 - oda yarıçapı 50
}


def _dedup(points):
    out = [points[0]]
    for p in points[1:]:
        if p != out[-1]:
            out.append(p)
    return out


def _build_motor_solid(b3d):
    """Bilinen ölçülü eksenel simetrik motor benzeri katı (eksen = X)."""
    inner = [(0.0, 50.0), (100.0, 50.0), (130.0, 10.0), (190.0, 25.0)]
    outer_r = 55.0
    raw = ([(-5.0, 0.0), (-5.0, outer_r), (195.0, outer_r), (195.0, 25.0),
            (190.0, 25.0)]
           + [(z, r) for z, r in reversed(inner)] + [(0.0, 0.0)])
    profile = _dedup(raw)
    with b3d.BuildPart() as part:
        with b3d.BuildSketch(b3d.Plane.XY):
            with b3d.BuildLine():
                b3d.Polyline(*(profile + [profile[0]]))
            b3d.make_face()
        b3d.revolve(axis=b3d.Axis.X)
    return part.part


def _write_step_inch(b3d_solid, path):
    """Katıyı INCH birim bildirimiyle STEP'e yazar (OCC writer)."""
    from OCP.STEPControl import (STEPControl_Writer, STEPControl_AsIs,
                                 STEPControl_Controller)
    from OCP.Interface import Interface_Static
    STEPControl_Controller.Init_s()
    Interface_Static.SetCVal_s('write.step.unit', 'INCH')
    try:
        writer = STEPControl_Writer()
        writer.Transfer(b3d_solid.wrapped, STEPControl_AsIs)
        writer.Write(path)
    finally:
        Interface_Static.SetCVal_s('write.step.unit', 'MM')


@pytest.fixture(scope='module')
def b3d():
    return pytest.importorskip('build123d')


@pytest.fixture(scope='module')
def fixtures_dir():
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    return FIXTURES_DIR


@pytest.fixture(scope='module')
def motor_step(b3d, fixtures_dir):
    path = os.path.join(fixtures_dir, 'synthetic_motor.step')
    b3d.export_step(_build_motor_solid(b3d), path)
    return path


@pytest.fixture(scope='module')
def tube_solid(b3d):
    """Düz boru: dış çap 100, iç çap 40, boy 100 (boğazsız geometri)."""
    return (b3d.Cylinder(radius=50, height=100)
            - b3d.Cylinder(radius=20, height=120))


@pytest.fixture(scope='module')
def tube_inch_step(b3d, fixtures_dir, tube_solid):
    path = os.path.join(fixtures_dir, 'synthetic_tube_inch.step')
    _write_step_inch(tube_solid, path)
    return path


@pytest.fixture(scope='module')
def tube_mm_step(b3d, fixtures_dir, tube_solid):
    path = os.path.join(fixtures_dir, 'synthetic_tube_mm.step')
    b3d.export_step(tube_solid, path)
    return path


@pytest.fixture(scope='module')
def asym_step(b3d, fixtures_dir):
    """Eksen simetrik olmayan katı: X ekseninde gövde + Z ekseninde çıkıntı."""
    main = b3d.Pos(100, 0, 0) * b3d.Cylinder(
        radius=50, height=200, rotation=(0, 90, 0))
    boss = b3d.Pos(100, 0, 0) * b3d.Cylinder(radius=20, height=160)
    path = os.path.join(fixtures_dir, 'synthetic_asymmetric.step')
    b3d.export_step(main + boss, path)
    return path


@pytest.fixture(scope='module')
def assembly_step(b3d, fixtures_dir):
    """İki katılı montaj: 'body' (büyük) + 'boss' (küçük)."""
    body = b3d.Cylinder(radius=50, height=100)
    body.label = 'body'
    boss = b3d.Pos(200, 0, 0) * b3d.Cylinder(radius=10, height=30)
    boss.label = 'boss'
    asm = b3d.Compound(children=[body, boss], label='asm')
    path = os.path.join(fixtures_dir, 'synthetic_assembly.step')
    b3d.export_step(asm, path)
    return path


@pytest.fixture(scope='module')
def corrupt_step(fixtures_dir):
    """Başlıksız çöp içerik (build123d gerektirmez)."""
    path = os.path.join(fixtures_dir, 'synthetic_corrupt.step')
    with open(path, 'w') as fh:
        fh.write('this is not a step file at all\n' * 10)
    return path


@pytest.fixture(scope='module')
def corrupt_header_step(fixtures_dir):
    """Geçerli başlık + bozuk gövde (ayrıştırıcı hatası yolu)."""
    path = os.path.join(fixtures_dir, 'synthetic_corrupt_header.step')
    with open(path, 'w') as fh:
        fh.write('ISO-10303-21;\nHEADER;\ngarbage garbage;\nENDSEC;\n')
    return path


# ---------------------------------------------------------------------------
# analyze_step — motor geometrisi
# ---------------------------------------------------------------------------

class TestMotorAnalysis:
    @pytest.fixture(scope='class')
    def result(self, motor_step):
        return step_import.analyze_step(motor_step)

    def test_no_error_and_source(self, result):
        assert 'error' not in result, result.get('error')
        assert result['source'] == 'step_import'

    def test_unit_is_mm(self, result):
        assert result['unit'] == 'mm'

    def test_axis_found_along_x(self, result):
        axis = result['axis']
        assert axis is not None
        d = axis['direction']
        assert abs(abs(d[0]) - 1.0) < 1e-6  # X ekseni

    def test_symmetry_deviation_near_zero(self, result):
        assert result['symmetry_deviation'] < 0.02

    def test_candidates_shape(self, result):
        assert len(result['candidates']) >= 4
        for cand in result['candidates']:
            assert cand['kind'] in ('cylinder', 'cone')
            assert cand['surface'] in ('inner', 'outer', 'unknown')
            assert cand['z1_mm'] > cand['z0_mm']
            assert cand['area_mm2'] > 0
            if cand['kind'] == 'cone':
                assert 'd2_mm' in cand

    def test_suggestions_within_1pct(self, result):
        sug = result['suggestions']
        _approx(sug['throat_diameter_mm']['value'],
                MOTOR_DIMS['throat_diameter'])
        _approx(sug['exit_diameter_mm']['value'], MOTOR_DIMS['exit_diameter'])
        _approx(sug['chamber_diameter_mm']['value'],
                MOTOR_DIMS['chamber_diameter'])
        _approx(sug['chamber_length_mm']['value'],
                MOTOR_DIMS['chamber_length'])
        _approx(sug['wall_thickness_mm']['value'],
                MOTOR_DIMS['wall_thickness'])

    def test_suggestion_structure(self, result):
        for key, sug in result['suggestions'].items():
            assert set(sug) == {'value', 'candidate_index', 'confidence',
                                'estimated'}, key
            assert sug['confidence'] in ('high', 'medium', 'low')
            assert sug['estimated'] is True
            assert 0 <= sug['candidate_index'] < len(result['candidates'])

    def test_throat_confidence_high(self, result):
        # Yakınsak-ıraksak kontur: boğazın iki yanı da genişliyor.
        assert result['suggestions']['throat_diameter_mm']['confidence'] == 'high'

    def test_profile_2d(self, result):
        prof = result['profile_2d']
        assert len(prof['inner']) >= 4 and len(prof['outer']) >= 2
        inner_r = [r for _, r in prof['inner']]
        _approx(min(inner_r), MOTOR_DIMS['throat_diameter'] / 2)

    def test_unrecognized_ratio_zero(self, result):
        assert result['unrecognized_area_ratio'] < 0.01

    def test_z_axis_starts_at_zero(self, result):
        z0_min = min(c['z0_mm'] for c in result['candidates'])
        assert z0_min == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# analyze_step — birim, simetri, boğazsız boru, montaj, hata yolları
# ---------------------------------------------------------------------------

class TestUnitHandling:
    def test_inch_file_detected_and_converted(self, tube_inch_step):
        result = step_import.analyze_step(tube_inch_step)
        assert 'error' not in result, result.get('error')
        assert result['unit'] == 'inch'
        assert any('inch' in w.lower() and 'millimetre' in w.lower()
                   for w in result['warnings'])
        # Değerler mm cinsinden kalmalı (çekirdek çevirisi): dış 100, iç 40
        diams = sorted(c['d1_mm'] for c in result['candidates'])
        _approx(diams[0], 40.0)
        _approx(diams[-1], 100.0)


class TestNoFabrication:
    """Uydurma-veri-yasağı: bulunamayan alan sessizce doldurulmaz."""

    def test_straight_tube_has_no_throat_or_exit(self, tube_mm_step):
        result = step_import.analyze_step(tube_mm_step)
        assert 'error' not in result, result.get('error')
        assert 'throat_diameter_mm' not in result['suggestions']
        assert 'exit_diameter_mm' not in result['suggestions']
        assert any('throat' in w.lower() for w in result['warnings'])

    def test_all_suggestions_marked_estimated(self, motor_step):
        result = step_import.analyze_step(motor_step)
        for sug in result['suggestions'].values():
            assert sug['estimated'] is True


class TestSymmetry:
    def test_asymmetric_solid_raises_deviation(self, asym_step, motor_step):
        asym = step_import.analyze_step(asym_step)
        clean = step_import.analyze_step(motor_step)
        assert 'error' not in asym, asym.get('error')
        assert asym['symmetry_deviation'] > 0.05
        assert asym['symmetry_deviation'] > clean['symmetry_deviation']


class TestAssembly:
    def test_default_analyzes_largest_with_warning(self, assembly_step):
        result = step_import.analyze_step(assembly_step)
        assert 'error' not in result, result.get('error')
        assert len(result['solids']) == 2
        names = {s['name'] for s in result['solids']}
        assert names == {'body', 'boss'}
        assert any('assembly' in w for w in result['warnings'])
        chosen = result['solid_analyzed_index']
        volumes = [s['volume_mm3'] for s in result['solids']]
        assert volumes[chosen] == max(volumes)
        # Büyük katı: yarıçap 50 -> çap 100 adaylarda olmalı
        assert any(abs(c['d1_mm'] - 100.0) < 1.0
                   for c in result['candidates'])

    def test_explicit_solid_index(self, assembly_step):
        result = step_import.analyze_step(assembly_step)
        volumes = [s['volume_mm3'] for s in result['solids']]
        small = int(volumes.index(min(volumes)))
        result2 = step_import.analyze_step(assembly_step, solid_index=small)
        assert 'error' not in result2, result2.get('error')
        assert result2['solid_analyzed_index'] == small
        # Küçük katı: yarıçap 10 -> çap 20
        assert any(abs(c['d1_mm'] - 20.0) < 0.5
                   for c in result2['candidates'])

    def test_solid_index_out_of_range(self, assembly_step):
        result = step_import.analyze_step(assembly_step, solid_index=99)
        assert result.get('error_kind') == 'bad_request'
        assert 'out of range' in result['error']


class TestErrorPaths:
    def test_missing_file(self):
        result = step_import.analyze_step('/nonexistent/path/file.step')
        assert result['error_kind'] == 'invalid_file'
        assert result['candidates'] == []

    def test_corrupt_without_header(self, corrupt_step):
        result = step_import.analyze_step(corrupt_step)
        assert result['error_kind'] == 'invalid_file'
        assert 'ISO-10303-21' in result['error']
        assert result['candidates'] == []

    def test_corrupt_with_header(self, b3d, corrupt_header_step):
        result = step_import.analyze_step(corrupt_header_step)
        assert 'error' in result
        assert result['error_kind'] == 'invalid_file'
        assert result['candidates'] == []


# ---------------------------------------------------------------------------
# HTTP uç noktası (Blueprint tek başına asgari Flask uygulamasına takılır;
# hrma.app import EDİLMEZ — blueprint kaydını ana Claude yapacak)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def api_client():
    flask = pytest.importorskip('flask')
    app = flask.Flask(__name__)
    app.register_blueprint(step_api.step_import_api)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def _post_file(client, path, filename=None, extra=None):
    with open(path, 'rb') as fh:
        payload = io.BytesIO(fh.read())
    data = {'file': (payload, filename or os.path.basename(path))}
    if extra:
        data.update(extra)
    return client.post('/api/import/step', data=data,
                       content_type='multipart/form-data')


class TestStepApi:
    def test_success(self, api_client, motor_step):
        resp = _post_file(api_client, motor_step)
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body['source'] == 'step_import'
        assert body['filename'] == 'synthetic_motor.step'
        assert isinstance(body['analysis_seconds'], float)
        assert body['analysis_seconds'] >= 0
        _approx(body['suggestions']['throat_diameter_mm']['value'],
                MOTOR_DIMS['throat_diameter'])
        assert isinstance(body['warnings'], list)

    def test_solid_index_form_field(self, api_client, assembly_step):
        resp = _post_file(api_client, assembly_step,
                          extra={'solid_index': '1'})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()['solid_analyzed_index'] == 1

    def test_missing_file_field(self, api_client):
        resp = api_client.post('/api/import/step', data={},
                               content_type='multipart/form-data')
        assert resp.status_code == 400
        assert 'file' in resp.get_json()['error']

    def test_bad_extension(self, api_client, motor_step):
        resp = _post_file(api_client, motor_step, filename='motor.txt')
        assert resp.status_code == 400
        assert 'extension' in resp.get_json()['error']

    def test_bad_solid_index(self, api_client, motor_step):
        resp = _post_file(api_client, motor_step,
                          extra={'solid_index': 'abc'})
        assert resp.status_code == 400

    def test_negative_solid_index(self, api_client, motor_step):
        resp = _post_file(api_client, motor_step,
                          extra={'solid_index': '-1'})
        assert resp.status_code == 400

    def test_oversize_rejected(self, api_client, motor_step, monkeypatch):
        monkeypatch.setattr(step_api, 'MAX_UPLOAD_BYTES', 1024)
        resp = _post_file(api_client, motor_step)
        assert resp.status_code == 413
        assert 'too large' in resp.get_json()['error']

    def test_corrupt_step_422(self, api_client, corrupt_step):
        resp = _post_file(api_client, corrupt_step)
        assert resp.status_code == 422
        body = resp.get_json()
        assert 'error' in body
        assert body['candidates'] == []

    def test_empty_file(self, api_client, tmp_path):
        empty = tmp_path / 'empty.step'
        empty.write_bytes(b'')
        resp = _post_file(api_client, str(empty))
        assert resp.status_code == 400
        assert 'empty' in resp.get_json()['error']
