"""V301 CAD-2 / KABUL K4 (27 Eki 2026) — lüle eti TEK kuraldan, çizilen et =
SF'nin ait olduğu et.

ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/bilinen/cad2/once_sf.json``,
``once_sf2.json``): örnek hibritte yapısal analiz boğazı KAMARA malzemesiyle
(ss_304, 215 MPa) 1,5·Pc + SCF 2,0 ile 2,5063 mm'ye boyutluyor (totolojik
SF 4,0), lüle tasarımcısı grafit lüleyi 1,0·Pc, SCF'siz hoop ile 7,1846 mm'ye
boyutluyordu; CAD 7,1846 mm çiziyordu. İmalat kapısı beş dışa aktarımı
``sf_wall_mismatch`` ile reddediyordu (DXF, çizim PDF'i, STEP, STL paketi,
tam paket — hepsi 422).

Onarım (ana model onayı, seçenek B): çizilen lüle eti yapısal modülün boğaz
kuralından (``structural_analysis.nozzle_throat_wall_sizing``; tasarım
basıncı Pc x ``STRUCTURAL_DESIGN_PRESSURE_FACTOR``, boğaz SCF'si) lülenin
KENDİ malzemesiyle gelir; yapısal analiz o eti DOĞRULAR.

Bekçiler:
1. Örnek hibrit (O/F 7,0 dosyadaki; O/F 6,0 günün sonundaki yeniden üretim)
   -> beş dışa aktarım 200.
2. Çizilen et = yapısal SF'nin ait olduğu et; aynı malzeme; kural tek.
3. Aynı et: lüle tasarımı, yapısal analiz, kütle dökümü, ``nozzle_wall_profile``
   (STEP/STL/DXF/montaj planı), Motor Kesiti, 3B sahne (node altında GERÇEK
   ``extractDims``).
4. Tek kaynak: kuralı değiştir -> çizilen et ve yapısal doğrulama BİRLİKTE
   değişir.
"""

import contextlib
import importlib.util
import io
import json
import math
import os
import pathlib
import shutil
import subprocess

import pytest

from tests.test_example_projects import (
    ENDPOINTS, HEADERS, calculate_payload, load_example_doc)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HIBRIT_DISA_AKTARIM_UCLARI = ('/api/export-dxf', '/api/export-drawings-pdf', '/api/export-step',
         '/api/export-stl-zip', '/api/export-complete-zip')
#: Örnek hibritin günün sonunda yeniden üretileceği O/F (ana model, 27 Eki).
OF_YENIDEN_URETIM = 6.0
NODE = shutil.which('node')
D34_OLCUM = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D34'
             / 'js-davranis' / 'a1' / 'olcum.py')


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('projeler')))
    os.environ.setdefault('BROWSER', 'echo')
    from hrma.app import app
    return app.test_client()


def _hibrit(client, **ezme):
    f = dict(load_example_doc('hybrid')['inputs']['fields'])
    f.update(ezme)
    r = _sessiz(client.post, ENDPOINTS['hybrid'],
                json=calculate_payload('hybrid', f), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def yanitlar(client):
    return {'of7': _hibrit(client),
            'of6': _hibrit(client, of_ratio=OF_YENIDEN_URETIM)}


# ---------------------------------------------------------------------------
# 1) Beş dışa aktarım
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('vaka', ['of7', 'of6'])
@pytest.mark.parametrize('uc', HIBRIT_DISA_AKTARIM_UCLARI)
def test_ornek_hibrit_bes_disa_aktarim_200(client, yanitlar, vaka, uc):
    if uc == '/api/export-step':
        # STEP üretimi build123d ister. Ana CI `pytest` işi build123d'yi BİLEREK
        # kurmaz (numpy<2 pini); bu düğüm orada devredilmiş atlama olur ve
        # build123d KURULU `step-export` işinde (tests.yml) sıfır atlama
        # bütçesiyle koşar — tools/atlama_kapisi.py STEP_DEVIR_DESENI.
        pytest.importorskip('build123d')
    govde = {'motor_data': yanitlar[vaka]['motor'],
             'motor_name': 'V301_CAD2_SF', 'motor_type': 'hybrid'}
    r = _sessiz(client.post, uc, json=govde, headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    assert len(r.data) > 1000


# ---------------------------------------------------------------------------
# 2) Çizilen et = SF'nin ait olduğu et; kural tek
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('vaka', ['of7', 'of6'])
def test_cizilen_et_yapisal_sf_nin_eti(yanitlar, vaka):
    from hrma.analysis.structural_analysis import (
        STRUCTURAL_DESIGN_PRESSURE_FACTOR, StructuralAnalyzer,
        nozzle_throat_wall_sizing)
    m = yanitlar[vaka]['motor']
    ng = m['nozzle_geometry']
    na = m['structural_analysis']['nozzle_analysis']
    et = ng['wall_thickness']
    assert na['design_mode'] == 'verify'
    assert na['throat_thickness_used_mm'] == et
    assert 'nozzle_geometry.wall_thickness' in na['throat_thickness_source']
    # Aynı malzeme: lülenin kendi malzemesi (kamara malzemesi DEĞİL)
    assert na['material_key'] == m['nozzle_material'] == ng['wall_material']
    kayit = StructuralAnalyzer().materials[m['nozzle_material']]
    assert na['yield_strength_used_MPa'] == pytest.approx(
        kayit['yield_strength'] / 1e6, rel=1e-12)
    assert ng['wall_yield_strength'] == kayit['yield_strength']
    # Tek kural: çizilen et yapısal boğaz kuralının sonucu
    assert ng['wall_thickness_basis'] == 'structural_throat_rule'
    beklenen = nozzle_throat_wall_sizing(
        m['chamber_pressure'] * 1e5 * STRUCTURAL_DESIGN_PRESSURE_FACTOR,
        ng['throat_radius'] / 1000.0, ng['wall_yield_strength'],
        ng['wall_safety_factor'], m['nozzle_type'])
    assert et == pytest.approx(
        beklenen['required_throat_thickness_m'] * 1000.0, rel=1e-12)
    assert ng['wall_stress_concentration_factor'] == \
        beklenen['stress_concentration_factor']
    assert ng['wall_design_pressure_factor'] == \
        STRUCTURAL_DESIGN_PRESSURE_FACTOR
    # Yapısal doğrulama, hedefle boyutlanan eti hedefte bulur (aynı model)
    assert na['safety_factor'] == pytest.approx(ng['wall_safety_factor'],
                                                rel=1e-9)
    # Künye: iki HRMA seçimi adlarıyla
    assert 'HRMA choice' in ng['wall_sizing_rule']


def test_kati_ve_sivi_yapisal_cagrisi_eski_yol(client):
    """Lüle malzemesi/eti geçmeyen çağıran (katı, sıvı, uç) eski yolda kalır:
    künye alanları yazılmaz, boğaz kamara malzemesiyle boyutlanır."""
    from hrma.analysis.structural_analysis import StructuralAnalyzer
    md = {'chamber_pressure': 30.0, 'chamber_diameter': 0.08,
          'chamber_length': 0.4, 'throat_diameter': 0.03,
          'nozzle_type': 'conical'}
    na = StructuralAnalyzer().analyze_structure(
        md, material='ss_304')['nozzle_analysis']
    assert na['design_mode'] == 'size'
    for alan in ('material_key', 'material_source', 'throat_thickness_source'):
        assert alan not in na
    with pytest.raises(ValueError, match='nozzle_material'):
        StructuralAnalyzer().analyze_structure(
            md, material='ss_304', nozzle_material='yok_boyle_malzeme',
            actual_throat_thickness=0.005)


# ---------------------------------------------------------------------------
# 3) Aynı et: tasarım, yapısal, kütle, CAD, kesit, 3B sahne
# ---------------------------------------------------------------------------
def _kesit_lule_eti(motor):
    """Motor Kesiti (plotly JSON) 'Nozzle' izinden çizilen et [mm]."""
    from hrma.visualization.visualization import (
        create_improved_motor_cross_section)
    fig = json.loads(create_improved_motor_cross_section(motor, 'hybrid'))
    etler = []
    for iz in fig['data']:
        if iz.get('name') != 'Nozzle':
            continue
        y = iz['y']
        if not y or max(y) <= 0:
            continue
        n = len(y) // 2
        etler.append(y[2 * n - 1] - y[0])
    assert etler, 'kesitte Nozzle izi yok'
    return etler[0]


def _sahne_lule_eti(motor):
    """3B sahne: node altında GERÇEK ``extractDims`` (D34 ön sözü)."""
    if NODE is None:
        pytest.skip('node bulunamadı')
    from tests.support.kanit import kanit_gerekli
    spec = importlib.util.spec_from_file_location(
        'd34_js_olcum_cad2', kanit_gerekli(D34_OLCUM))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    betik = mod._viz_onsoz() + """
var _md = %s;
var _d = extractDims(_md);
process.stdout.write(JSON.stringify({wall: _d.nozzleWall,
    src: (_d.srcDecl || {}).nozzle_wall || null}));
""" % json.dumps(motor)
    res = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


@pytest.mark.parametrize('vaka', ['of7', 'of6'])
def test_ayni_et_her_tuketicide(yanitlar, vaka):
    from hrma.export.cad_visualization import nozzle_wall_profile
    from hrma.export.motor_assembly import build_plan
    from hrma.export.motor_geometry import normalise_export_geometry
    y = yanitlar[vaka]
    m = y['motor']
    et = m['nozzle_geometry']['wall_thickness']
    # Yapısal + kütle dökümü
    assert m['structural_analysis']['nozzle_analysis'][
        'throat_thickness_used_mm'] == et
    gs = y['cad_design']['performance_summary']['geometry_summary']
    assert gs['nozzle_wall_thickness_mm'] == pytest.approx(et, rel=1e-12)
    # STEP/STL/DXF/kütle/plan ortak profili
    n, _ = normalise_export_geometry(m)
    prof = nozzle_wall_profile(n, unit='mm', require_solved_length=True)
    assert prof['wall'] == pytest.approx(et, rel=1e-12)
    plan = _sessiz(build_plan, m, 'hybrid')
    lule = next(p for p in plan['parts'] if p['id'] == 'H10')
    assert lule['dims']['wall_thickness_mm']['value'] == pytest.approx(
        et, rel=1e-12)
    # Motor Kesiti
    assert _kesit_lule_eti(m) == pytest.approx(et, abs=1e-9)
    # 3B sahne: yayımlanan et KIRPILMADAN
    sahne = _sahne_lule_eti(m)
    assert sahne['wall'] == pytest.approx(et, abs=1e-9)
    assert sahne['src']['kind'] == 'computed'


# ---------------------------------------------------------------------------
# 4) Tek kaynak: kuralı değiştir -> çizilen et ve doğrulama birlikte
# ---------------------------------------------------------------------------
def test_kural_degisince_cizilen_et_ve_dogrulama_birlikte(client, yanitlar,
                                                          monkeypatch):
    """``nozzle_throat_wall_sizing`` sınama için gereken eti %10 artırır. Lüle
    tasarımcısı kuralı kendisi yazsaydı çizilen et değişmezdi; yapısal
    analiz çizilen eti okumasaydı doğrulanan et değişmezdi."""
    from hrma.analysis import structural_analysis as sa
    asil = sa.nozzle_throat_wall_sizing

    def kalin(*a, **k):
        r = dict(asil(*a, **k))
        r['required_throat_thickness_m'] *= 1.1
        return r

    monkeypatch.setattr(sa, 'nozzle_throat_wall_sizing', kalin)
    m = _hibrit(client)['motor']
    et0 = yanitlar['of7']['motor']['nozzle_geometry']['wall_thickness']
    et1 = m['nozzle_geometry']['wall_thickness']
    assert et1 == pytest.approx(et0 * 1.1, rel=1e-9)
    na = m['structural_analysis']['nozzle_analysis']
    assert na['throat_thickness_used_mm'] == et1
    assert not math.isclose(na['safety_factor'], 4.0, rel_tol=1e-6)
