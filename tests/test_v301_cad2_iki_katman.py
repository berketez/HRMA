"""V301 CAD-2 kalem 8 (27 Eki 2026) — iki katmanlı rejeneratif cidarın CAD'i.

L-KABUK DEVİR 1: sıvı rejeneratif cidar artık astar (kanallı, ``chamber_
material``) + dış kabuk (``closeout_material``); CAD yığını TEK katı gövde,
tek malzemeyle tartıyor, ceketli lüleyi ``nozzle_geometry`` / üreteç
kuralıyla çiziyordu (ölçüm ``docs/scofield/raw/OH/V301/bilinen/cad2/
once_k8.json``: lüle eti 6,69 mm kural ⟷ yığın 5,50 mm).

Onarım: ``cad_visualization.two_layer_wall_cad_geometry`` tek çözümleyici;
STEP iki katı (astar + kanal/kaburga zarfı, dış kabuk + kapak), STL iki
kabuk, DXF katman sınırları (``WALL_LAYERS``), kütle iki malzemeyle ve yerel
kaburga payıyla, ceketli lüle aynı yığınla (STEP/STL/DXF/kesit/3B sahne).
Kanallar KESİLMEZ (künyeli HRMA çizim seçimi; sayı/genişlik/derinlik
yanıtta).

Vaka: L-KABUK'un geçerli örnek tasarım noktası (RAPOR §7): CuCrZr 1 mm
astar, O/F 2,0, Pc 50, besleme 75.
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
from tests.test_v3_cad_duzeltme import _step_hacim_uyarlamali

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
#: L-KABUK RAPOR §7 — örnek dosyanın önerilen (geçerli) girdileri.
L_KABUK_GECERLI_NOKTA = {'chamber_material': 'cucrzr',
                         'chamber_wall_thickness': 1.0,
                         'mixture_ratio': 2.0, 'chamber_pressure': 50,
                         'feed_pressure': 75}
from tests.test_v301_cad2_plaka import (  # noqa: E402
    STL_COKGEN_KATSAYISI, STL_HACIM_BAGIL)
#: STEP B-spline lüle ⟷ doğrusal parça kâhini (C1 ölçümü 1,34e-4).
STEP_KAHIN_BAGIL = 1e-3
NODE = shutil.which('node')
D34_OLCUM = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D34'
             / 'js-davranis' / 'a1' / 'olcum.py')


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def yanit(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('projeler')))
    os.environ.setdefault('BROWSER', 'echo')
    from hrma.app import app
    f = dict(load_example_doc('liquid')['inputs']['fields'])
    f.update(L_KABUK_GECERLI_NOKTA)
    r = _sessiz(app.test_client().post, ENDPOINTS['liquid'],
                json=calculate_payload('liquid', f), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def govde(yanit):
    md = dict(yanit['motor_geometry'])
    md['motor_name'] = 'V301_CAD2_IKI_KATMAN'
    return md


@pytest.fixture(scope='module')
def paket(govde, tmp_path_factory):
    pytest.importorskip('build123d')
    trimesh = pytest.importorskip('trimesh')
    from hrma.export.cad_visualization import MotorCADDesigner
    from hrma.export.drawing_generator import generate_dxf
    from hrma.export.step_export import generate_step_assembly
    d = tmp_path_factory.mktemp('k8')
    step = _sessiz(generate_step_assembly, govde, out_dir=str(d / 'step'),
                   motor_type='liquid')
    des = MotorCADDesigner()
    cad = _sessiz(des.generate_3d_motor_assembly, dict(govde))
    assert not cad.get('error'), cad.get('error')
    _sessiz(des.export_stl_files, cad['assembly_meshes'],
            output_dir=str(d / 'stl'))
    return {'step': step, 'cad': cad,
            'stl': {a: trimesh.load(str(d / 'stl' / f'{a}.stl'),
                                    process=False)
                    for a in ('chamber', 'nozzle')},
            'dxf': _sessiz(generate_dxf, govde, str(d / 'k8.dxf'))}


def _geo(govde):
    from hrma.export.cad_visualization import two_layer_wall_cad_geometry
    from hrma.export.motor_geometry import normalise_export_geometry
    n, _ = normalise_export_geometry(govde)
    return n, two_layer_wall_cad_geometry(n)


def test_cozumleyici_yayimlanan_katmanlar(yanit, govde):
    from hrma.data.materials_db import get_material
    _n, g = _geo(govde)
    cs = yanit['motor_geometry']['structural_analysis']['chamber_structure']
    lin, clo = cs['wall_layers']
    assert g['liner_mm'] == lin['thickness_mm']
    assert g['closeout_mm'] == clo['thickness_mm']
    assert g['channel_mm'] == cs['channel_depth_mm']
    assert g['stack_mm'] == cs['wall_stack_thickness_mm']
    assert g['n_channels'] == yanit['cooling_system']['cooling_channels']
    assert g['liner']['density'] == get_material(lin['material_key'])['density']
    assert g['closeout']['density'] == get_material(
        clo['material_key'])['density']
    assert g['jacket_covers_nozzle'] is True


def test_step_kamara_ve_lule_iki_govde(paket, govde):
    from build123d import import_step
    from hrma.export.cad_visualization import nozzle_wall_profile
    n, g = _geo(govde)
    rc = n['chamber_diameter'] * 500.0
    L = n['chamber_length'] * 1000.0
    kamara = import_step(paket['step']['chamber']).solids()
    assert len(kamara) == 2
    v = sorted(_step_hacim_uyarlamali_kati(k) for k in kamara)
    astar = math.pi * ((rc + g['interface_mm']) ** 2 - rc ** 2) * L
    assert min(v, key=lambda x: abs(x - astar)) == pytest.approx(astar,
                                                                  rel=1e-6)
    lule = import_step(paket['step']['nozzle']).solids()
    assert len(lule) == 2
    prof = nozzle_wall_profile(n, unit='mm', require_solved_length=True)
    pts = prof['inner']

    def kahin(w):
        return sum(math.pi * (w * (r0 + r1) + w * w) * (z1 - z0)
                   for (z0, r0), (z1, r1) in zip(pts, pts[1:]))
    v_l = sorted(_step_hacim_uyarlamali_kati(k) for k in lule)
    beklenen = sorted([kahin(g['interface_mm']),
                       kahin(g['stack_mm']) - kahin(g['interface_mm'])])
    for a, b in zip(v_l, beklenen):
        assert abs(a / b - 1.0) <= STEP_KAHIN_BAGIL, (a, b)
    assert prof['wall'] == pytest.approx(g['stack_mm'], abs=1e-12)


def _step_hacim_uyarlamali_kati(kati):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    gp = GProp_GProps()
    BRepGProp.VolumeProperties_s(kati.wrapped, gp, 1e-7, True)
    return gp.Mass()


@pytest.mark.parametrize('parca', ['chamber', 'nozzle'])
def test_stl_hacmi_step_ile_ayni(paket, parca):
    """Kamara düz tüplerdir (32-gen katsayısı TAM); lüle B-spline ⟷ kiriş
    farkını da taşır (``STEP_KAHIN_BAGIL``)."""
    v_step = _step_hacim_uyarlamali(paket['step'][parca])
    v_stl = float(paket['stl'][parca].volume)
    tol = STL_HACIM_BAGIL if parca == 'chamber' else STEP_KAHIN_BAGIL
    assert abs(v_stl / v_step - STL_COKGEN_KATSAYISI) <= tol, (
        v_stl / v_step)


def test_kutle_iki_malzemeli(paket, govde):
    """Kamara kütlesi = astar + kaburga payı x kanal katmanı (astar ρ) +
    dış kabuk (kabuk ρ); kâhin bağımsız yazılır."""
    n, g = _geo(govde)
    rc = n['chamber_diameter'] * 500.0
    L = n['chamber_length'] * 1000.0
    r1, r2 = rc + g['liner_mm'], rc + g['interface_mm']
    r3 = rc + g['stack_mm']
    f = 1.0 - g['n_channels'] * g['channel_w_mm'] / (math.pi * (r1 + r2))
    kahin = (math.pi * L * 1e-9 * ((r1 ** 2 - rc ** 2 + f * (r2 ** 2 - r1 ** 2))
                                   * g['liner']['density']
                                   + (r3 ** 2 - r2 ** 2)
                                   * g['closeout']['density']))
    mb = paket['cad']['performance_summary']['mass_breakdown']
    assert mb['chamber_mass'] == pytest.approx(kahin, rel=1e-12)
    assert mb['two_layer_mass_basis_key'] == 'out.cad.twoLayerWall.massBasis'
    assert g['liner']['material'] in mb['mass_basis']


def test_dxf_katman_sinirlari(paket, govde):
    ezdxf = pytest.importorskip('ezdxf')
    from hrma.export.drawing_generator import DXF_WALL_LAYERS_LAYER
    n, g = _geo(govde)
    rc = n['chamber_diameter'] * 500.0
    doc = ezdxf.readfile(paket['dxf'])
    cizgi = [list(e.get_points('xy')) for e in doc.modelspace()
             if e.dxftype() == 'LWPOLYLINE'
             and e.dxf.layer == DXF_WALL_LAYERS_LAYER]
    duz = sorted({round(p[0][1], 6) for p in cizgi if len(p) == 2})
    assert duz == sorted({round(s * (rc + o), 6) for s in (1, -1)
                          for o in (g['liner_mm'], g['interface_mm'])})
    assert sum(1 for p in cizgi if len(p) > 2) == 4     # lüle: 2 sınır x 2 yan
    metin = [e.dxf.text for e in doc.modelspace() if e.dxftype() == 'TEXT'
             and e.dxf.text.startswith('TWO-LAYER WALL')]
    assert metin and 'NOT cut' in metin[0]


def test_kesit_ve_sahne_ayni_yigin(yanit, govde):
    from hrma.visualization.visualization import (
        create_improved_motor_cross_section)
    _n, g = _geo(govde)
    fig = json.loads(create_improved_motor_cross_section(
        dict(govde), 'liquid'))
    etler = [iz['y'][2 * (len(iz['y']) // 2) - 1] - iz['y'][0]
             for iz in fig['data'] if iz.get('name') == 'Nozzle'
             and iz['y'] and max(iz['y']) > 0]
    assert etler and etler[0] == pytest.approx(g['stack_mm'], abs=1e-9)
    if NODE is None:
        pytest.skip('node bulunamadı')
    from tests.support.kanit import kanit_gerekli
    spec = importlib.util.spec_from_file_location(
        'd34_js_olcum_k8', kanit_gerekli(D34_OLCUM))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Sahnenin sıvı gövdesi: liquid.html buildLiquidVizData structural_
    # analysis'i geçirir; çaplar metre.
    md = {'chamber_diameter': govde['chamber_diameter'],
          'chamber_length': govde['chamber_length'],
          'throat_diameter': govde['throat_diameter'],
          'exit_diameter': govde['exit_diameter'],
          'structural_analysis': govde['structural_analysis']}
    from hrma.export.motor_geometry import normalise_export_geometry
    n2, _ = normalise_export_geometry(md)
    md = {k: n2[k] for k in ('chamber_diameter', 'chamber_length',
                             'throat_diameter', 'exit_diameter')}
    md['structural_analysis'] = govde['structural_analysis']
    betik = mod._viz_onsoz() + """
var _d = extractDims(%s);
process.stdout.write(JSON.stringify({wall: _d.nozzleWall,
    src: (_d.srcDecl || {}).nozzle_wall || null}));
""" % json.dumps(md)
    res = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2000:]
    sahne = json.loads(res.stdout)
    assert sahne['wall'] == pytest.approx(g['stack_mm'], abs=1e-9)
    assert 'wall_stack_thickness_mm' in sahne['src']['basis']


def test_tek_kaynak_katman_bolumu_degisince_hepsi_izler(govde, tmp_path):
    """Yanıttaki astar/kanal bölünmesi değişince (yığın aynı) STEP ara yüzü,
    DXF sınırı ve kütle BİRLİKTE değişir; bir tüketici kendi sayısını
    yazsaydı izlemezdi."""
    pytest.importorskip('build123d')
    ezdxf = pytest.importorskip('ezdxf')
    from build123d import import_step
    from hrma.export.cad_visualization import MotorCADDesigner
    from hrma.export.drawing_generator import (
        DXF_WALL_LAYERS_LAYER, generate_dxf)
    from hrma.export.step_export import generate_step_assembly
    md = json.loads(json.dumps(govde))
    cs = md['structural_analysis']['chamber_structure']
    # Yığın aynı kalır; astar kalınlaşır, dış kabuk incelir -> ara yüz kayar.
    cs['wall_layers'][0]['thickness_mm'] += 0.5
    cs['wall_layers'][1]['thickness_mm'] -= 0.5
    n, g = _geo(md)
    rc = n['chamber_diameter'] * 500.0
    L = n['chamber_length'] * 1000.0
    step = _sessiz(generate_step_assembly, md, out_dir=str(tmp_path / 's'),
                   motor_type='liquid')
    v = [_step_hacim_uyarlamali_kati(k)
         for k in import_step(step['chamber']).solids()]
    astar = math.pi * ((rc + g['interface_mm']) ** 2 - rc ** 2) * L
    assert any(abs(x / astar - 1.0) < 1e-6 for x in v)
    doc = ezdxf.readfile(_sessiz(generate_dxf, md, str(tmp_path / 'a.dxf')))
    duz = {round(abs(list(e.get_points('xy'))[0][1]), 6)
           for e in doc.modelspace() if e.dxftype() == 'LWPOLYLINE'
           and e.dxf.layer == DXF_WALL_LAYERS_LAYER
           and len(list(e.get_points('xy'))) == 2}
    assert round(rc + g['liner_mm'], 6) in duz
    m0 = MotorCADDesigner()._estimate_component_mass('chamber', _geo(govde)[0])
    m1 = MotorCADDesigner()._estimate_component_mass('chamber', n)
    assert m1 != pytest.approx(m0, rel=1e-6)


def test_tek_katmanli_yolda_cozumleyici_none():
    from hrma.export.cad_visualization import (
        _nozzle_wall_design, two_layer_wall_cad_geometry)
    md = {'structural_analysis': {'chamber_structure': {
        'wall_thickness': 5.0}}, 'throat_diameter': 0.05}
    assert two_layer_wall_cad_geometry(md) is None
    assert 'two_layer' not in _nozzle_wall_design(md)


def test_eksik_yigin_adli_ret_ama_kapi_cokmez():
    from hrma.export.cad_visualization import (
        _nozzle_wall_design, two_layer_wall_cad_geometry)
    md = {'structural_analysis': {'chamber_structure': {
        'wall_model': 'two_layer_regenerative',
        'wall_layers': [{'role': 'liner', 'thickness_mm': 1.0,
                         'material_key': 'cucrzr'},
                        {'role': 'closeout', 'thickness_mm': None,
                         'material_key': 'inconel_718'}],
        'channel_depth_mm': 2.0, 'wall_stack_thickness_mm': None}},
        'throat_diameter': 0.05}
    with pytest.raises(ValueError, match='two_layer_wall_not_drawable'):
        two_layer_wall_cad_geometry(md)
    tasarim = _nozzle_wall_design(md)
    assert 'two_layer_wall_not_drawable' in tasarim['source']


@pytest.mark.parametrize('parca', ['chamber', 'nozzle'])
def test_stl_iki_kapali_kabuk(paket, parca):
    """STL parçası iki kapalı kabuktur (astar + kanal katmanı zarfı, dış
    kabuk); bellekteki mesh köşe paylaşmaz, her kabuk ayrı kapalıdır."""
    mesh = next(m for ad, m in paket['cad']['assembly_meshes']
                if str(ad).lower() == parca)
    kabuklar = mesh.split(only_watertight=False)
    assert len(kabuklar) == 2
    assert all(bool(k.is_watertight) for k in kabuklar)
