"""V301 CAD-2 kalem 7 (27 Eki 2026) — toplam motor uzunluğu TEK tanım (NK-6).

ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/bilinen/cad2/once_k7.json``, örnek
hibrit): aynı motor için Tasarım Özeti 1160,2 (oda + lüle) / 1163,8 (kapak
dahil: önerilen DİŞLİ kapağın cidar kalınlığı 3,58 mm), Motor Kesiti 1169
(kendi kapak kesri), STEP 1174,57 (çizilen DÜZ kapak 13,63 mm + çizilen
lüle; konik lülede Rao yayı çıkışı 0,75 mm öteler).

Tek tanım: toplam boy = çizilen düz ön kapak (``end_cap_analysis
.flat_head_thickness``) + oda + ÇİZİLEN lüle (tek kontur örnekleyicisi).
Tasarım Özeti, Motor Kesiti, 3B sahne ve STEP aynı sayıyı verir; oda + lüle
(kapak hariç) ayrı adla yayımlanır. Kesit, hibrit termal kolunun beyan ettiği
ön/son oda astarını çizer (lejant "Koyu gri: Fenolik astar / yalıtım").
"""

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_example_projects import (
    ENDPOINTS, HEADERS, calculate_payload, load_example_doc)
from tests.test_v301_cad2_lule_sf import OF_YENIDEN_URETIM

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
NODE = shutil.which('node')
D34_OLCUM = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D34'
             / 'js-davranis' / 'a1' / 'olcum.py')
#: Kesit etiketi tam sayıya yuvarlanır (``L_total = {:.0f} mm``).
KESIT_ETIKET_TOL_MM = 0.5


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def yanitlar(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('projeler')))
    os.environ.setdefault('BROWSER', 'echo')
    from hrma.app import app
    c = app.test_client()
    out = {}
    for ad, ezme in (('of7', {}), ('of6', {'of_ratio': OF_YENIDEN_URETIM})):
        f = dict(load_example_doc('hybrid')['inputs']['fields'])
        f.update(ezme)
        r = _sessiz(c.post, ENDPOINTS['hybrid'],
                    json=calculate_payload('hybrid', f), headers=HEADERS)
        assert r.status_code == 200
        out[ad] = r.get_json()
    return out


def _sahne_toplam(motor):
    if NODE is None:
        pytest.skip('node bulunamadı')
    from tests.support.kanit import kanit_gerekli
    spec = importlib.util.spec_from_file_location(
        'd34_js_olcum_k7', kanit_gerekli(D34_OLCUM))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = mod.oku(mod.VIZ_JS)
    on = mod._viz_onsoz()
    for ad in mod._bagimliliklar(src, 'nozzleProfile'):
        g = mod.govde(src, ad)
        if g and g not in on:
            on += '\n' + g
    md = dict(motor, viz_motor_type='hybrid')
    betik = on + """
var d = extractDims(%s);
var np = nozzleProfile(d);
process.stdout.write(JSON.stringify(np.zExit + (d.capT > 0 ? d.capT : 0)));
""" % json.dumps(md)
    res = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


@pytest.mark.parametrize('vaka', ['of7', 'of6'])
def test_dort_yuzey_ayni_toplam_boy(yanitlar, vaka, tmp_path):
    pytest.importorskip('build123d')
    from build123d import import_step
    from hrma.export.cad_visualization import (
        _chamber_wall_design, _front_cap_design, nozzle_wall_profile)
    from hrma.export.motor_geometry import normalise_export_geometry
    from hrma.export.step_export import generate_step_assembly
    from hrma.visualization.visualization import (
        create_improved_motor_cross_section)
    y = yanitlar[vaka]
    m = y['motor']
    kd = y['design_summary']['key_dimensions']
    toplam = kd['total_motor_length_with_caps_mm']
    # Bileşenler beyanlı ve çizilenin kendisi
    ec = m['structural_analysis']['end_cap_analysis']
    assert kd['forward_closure_length_mm'] == ec['flat_head_thickness']
    n, _ = normalise_export_geometry(m)
    w = _chamber_wall_design(n)['thickness_m'] * 1000.0
    kapak = _front_cap_design(n, wall_mm=w,
                              bore_radius_mm=n['chamber_diameter'] * 500.0)
    assert kapak['thickness_mm'] == pytest.approx(
        kd['forward_closure_length_mm'], abs=1e-9)
    prof = nozzle_wall_profile(n, unit='mm', require_solved_length=True)
    assert kd['nozzle_drawn_length_mm'] == pytest.approx(
        prof['inner'][-1][0] - prof['inner'][0][0], abs=1e-9)
    assert kd['total_motor_length_chamber_nozzle_mm'] == pytest.approx(
        kd['chamber_length_mm'] + kd['nozzle_drawn_length_mm'], abs=1e-9)
    assert toplam == pytest.approx(
        kd['total_motor_length_chamber_nozzle_mm']
        + kd['forward_closure_length_mm'], abs=1e-9)
    # STEP montajı
    step = _sessiz(generate_step_assembly, m, out_dir=str(tmp_path),
                   motor_type='hybrid')
    bb = import_step(step['assembly']).bounding_box()
    assert bb.max.X - bb.min.X == pytest.approx(toplam, abs=1e-5)
    # Motor Kesiti etiketi
    fig = json.loads(create_improved_motor_cross_section(m, 'hybrid'))
    etiket = [str(a.get('text')) for a in fig['layout'].get('annotations', [])
              if 'total' in str(a.get('text'))]
    mm = float(re.findall(r'= (\d+) mm', etiket[0])[0])
    assert abs(mm - toplam) <= KESIT_ETIKET_TOL_MM, (mm, toplam)
    # 3B sahne
    assert _sahne_toplam(m) == pytest.approx(toplam, abs=1e-6)


def test_kesit_beyanli_astari_cizer(yanitlar):
    """Lejant 'Koyu gri: Fenolik astar / yalıtım' — kesit hibrit termal
    kolunun ön/son oda astarını yayımlanan kalınlıkla çizer."""
    from hrma.visualization.visualization import (
        create_improved_motor_cross_section)
    m = yanitlar['of7']['motor']
    t = m['thermal_protection']['chamber_liner']['thickness']
    fig = json.loads(create_improved_motor_cross_section(m, 'hybrid'))
    izler = [iz for iz in fig['data'] if iz.get('name') == 'Chamber liner']
    assert len(izler) == 4                       # ön + son, iki yan
    rc = m['chamber_diameter'] * 500.0
    ust = [iz for iz in izler if max(iz['y']) > 0]
    for iz in ust:
        assert min(iz['y']) == pytest.approx(rc - t, abs=1e-9)
        assert max(iz['y']) == pytest.approx(rc, abs=1e-9)
    on = min(ust, key=lambda iz: min(iz['x']))
    assert max(on['x']) == pytest.approx(m['pre_chamber_length'] * 1000.0,
                                         abs=1e-9)
