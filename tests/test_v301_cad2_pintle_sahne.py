"""V301 CAD-2 kalem 2-3-4 (27 Eki 2026) — pintle: 3B sahne, direk kütlesi,
yüz plakası.

ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/bilinen/cad2/once_k234.json``):
* plaka analizi pintle'da devrenin EŞDEĞER orifis planıyla (8 x Ø2,46 mm)
  kuruluyor ve kalınlık YAYIMLAMIYORDU (yalnız ``required_thickness_mm``);
  ürün yolunda yüz plakası hiç çizilmiyordu;
* kütle dökümünde enjektör 0 kg (plaka yok), çizilen direk tartılmıyordu;
* 3B sahne pintle'ı ancak plaka varsa ve sezgisel ölçülerle (clamp, 24
  delik sınırı, 1,6 x çap) çiziyordu; ürün yolunda hiç çizmiyordu.

Onarım: plaka TEK delikle (kanonik anülüs deliği) analiz edilir, hedef SF'ye
boyutlandırılıp o kalınlıkta doğrulanır ve kalınlık motor bloğuna yazılır;
kütle = çizilen direk (net hacim) + yüz plakası x SEÇİLEN enjektör malzemesi
(seçilmemişse tartılmaz, künye söyler); sahne ``injector_design.pintle_cad``
(``pintle_cad_geometry``) verisinden çizer.
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
NODE = shutil.which('node')
D34_OLCUM = (REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D34'
             / 'js-davranis' / 'a1' / 'olcum.py')
#: Hibrit sayfasının enjektör malzemesi seçeneği (``advanced.html``).
ENJEKTOR_MALZEMESI = 'stainless_steel'


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
    for ad, ezme in (('malzemeli', {'injector_type': 'pintle',
                                    'injector_material': ENJEKTOR_MALZEMESI}),
                     ('malzemesiz', {'injector_type': 'pintle'}),
                     ('showerhead', {})):
        f = dict(load_example_doc('hybrid')['inputs']['fields'])
        f.update(ezme)
        r = _sessiz(c.post, ENDPOINTS['hybrid'],
                    json=calculate_payload('hybrid', f), headers=HEADERS)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        out[ad] = r.get_json()
    return out


def _geo(motor):
    from hrma.export.cad_visualization import pintle_cad_geometry
    from hrma.export.motor_geometry import normalise_export_geometry
    n, _ = normalise_export_geometry(motor)
    return n, pintle_cad_geometry(n)


# ---------------------------------------------------------------------------
# Kalem 4 — yüz plakası
# ---------------------------------------------------------------------------
def test_plaka_anulus_deligiyle_boyutlanir_ve_yayimlanir(yanitlar):
    y = yanitlar['malzemeli']
    ps = y['injector']['plate_structural']
    _n, g = _geo(y['motor'])
    assert ps['hole_plan_source'] == 'pintle_annulus_bore'
    assert ps['n_holes'] == 1
    assert ps['hole_diameter_mm'] == pytest.approx(g['bore'], abs=1e-4)
    assert ps['status'] == 'analyzed'
    assert ps['plate_thickness_source'] == 'sized_to_target_safety_factor'
    assert ps['plate_thickness_mm'] == pytest.approx(
        ps['required_thickness_mm'], abs=1e-9)
    assert ps['safety_factor'] == pytest.approx(
        ps['required_safety_factor'], rel=2e-3)
    inj = y['motor']['injector_design']
    assert inj['plate_thickness_mm'] == ps['plate_thickness_mm']
    assert inj['plate_thickness_source'] == 'sized_to_target_safety_factor'
    assert inj['plate_material_key'] == ps['material_key']
    # CAD kendiliğinden çizer: yüz plakası kanonik kalınlıkta
    assert g['plate_t'] == pytest.approx(ps['plate_thickness_mm'], abs=1e-12)


def test_malzeme_yoksa_plaka_analiz_edilmez_kalinlik_uydurulmaz(yanitlar):
    y = yanitlar['malzemesiz']
    assert 'plate_structural' not in (y.get('injector') or {})
    inj = y['motor']['injector_design']
    assert inj.get('plate_thickness_mm') is None
    assert inj['plate_thickness_source'] == 'not_earned'
    _n, g = _geo(y['motor'])
    assert g['plate_t'] is None                  # direk yüzden çizilir


def test_step_plaka_ve_direk(yanitlar, tmp_path):
    pytest.importorskip('build123d')
    from build123d import import_step
    from hrma.export.cad_visualization import pintle_post_volume_mm3
    from hrma.export.step_export import generate_step_assembly
    m = yanitlar['malzemeli']['motor']
    _n, g = _geo(m)
    step = _sessiz(generate_step_assembly, m, out_dir=str(tmp_path),
                   motor_type='hybrid')
    v = sorted(k.volume for k in import_step(step['injector']).solids())
    plaka = math.pi * (g['plate_r'] ** 2 - (g['bore'] / 2) ** 2) * g['plate_t']
    assert len(v) == 2
    assert v[1] == pytest.approx(plaka, rel=1e-6)
    assert v[0] == pytest.approx(pintle_post_volume_mm3(g), rel=1e-4)


# ---------------------------------------------------------------------------
# Kalem 3 — kütle
# ---------------------------------------------------------------------------
def test_kutle_direk_ve_plaka_secilen_malzemeyle(yanitlar):
    from hrma.data.materials_db import get_material
    from hrma.export.cad_visualization import pintle_post_volume_mm3
    y = yanitlar['malzemeli']
    _n, g = _geo(y['motor'])
    rho = get_material(y['injector']['plate_structural']['material_key'])[
        'density']
    plaka = math.pi * (g['plate_r'] ** 2 - (g['bore'] / 2) ** 2) * g['plate_t']
    mb = y['cad_design']['performance_summary']['mass_breakdown']
    # /calculate yolunun plakası plaka analizinin yuvarlanmış çapını
    # (``plate_diameter_mm``, 3 ondalık) okur; dışa aktarım gövdesi kamara
    # deliğini. Fark ≤ 5e-4 mm çap: bağıl ~1e-5.
    assert mb['injector_mass'] == pytest.approx(
        (pintle_post_volume_mm3(g) + plaka) * 1e-9 * rho, rel=1e-4)
    assert 'drawn post' in mb['injector_mass_basis']


def test_malzemesiz_direk_tartilmaz_ve_soylenir(yanitlar):
    mb = yanitlar['malzemesiz']['cad_design']['performance_summary'][
        'mass_breakdown']
    assert mb['injector_mass'] == 0.0
    assert 'NOT weighed' in mb['injector_mass_basis']


def test_direk_hacmi_kahini():
    """Delik integrali: a << R iken ∫2√(a²−y²)(√(R²−y²) − r_dip)dy =
    π a² h − π a⁴/(8R) + O(a⁶/R³) (eğri yüzey düzeltmesi; kâhin bağımsız
    seri açılımı)."""
    from hrma.export.cad_visualization import pintle_post_volume_mm3
    R, a, h = 500.0, 1.0, 3.0
    g = {'d_post': 2 * R, 'x0': 0.0, 'x_tip': 10.0, 'n_holes': 1,
         'd_hole': 2 * a, 'hole_depth': h}
    v = pintle_post_volume_mm3(g)
    delik = math.pi * a * a * h - math.pi * a ** 4 / (8.0 * R)
    assert math.pi * R ** 2 * 10.0 - v == pytest.approx(delik, rel=1e-6)


def test_showerhead_bit_ayni_alan_eklenmez(yanitlar):
    y = yanitlar['showerhead']
    assert 'pintle_cad' not in y['motor']['injector_design']
    assert 'injector_mass_basis' not in y['cad_design'][
        'performance_summary']['mass_breakdown']


# ---------------------------------------------------------------------------
# Kalem 2 — 3B sahne verisi ve çizimi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('vaka', ['malzemeli', 'malzemesiz'])
def test_sahne_verisi_kanonik_cozumleyiciden(yanitlar, vaka):
    m = yanitlar[vaka]['motor']
    pc = m['injector_design']['pintle_cad']
    _n, g = _geo(m)
    assert pc['drawn'] is True
    assert pc['post_diameter_mm'] == g['d_post']
    assert pc['post_root_x_mm'] == g['x0']
    assert pc['post_tip_x_mm'] == g['x_tip']
    assert pc['tip_hole_row_x_mm'] == g['x_holes']
    assert pc['tip_hole_count'] == g['n_holes']
    assert pc['tip_hole_diameter_mm'] == g['d_hole']
    assert pc['tip_hole_depth_mm'] == g['hole_depth']
    assert pc['annulus_bore_mm'] == g['bore']
    assert pc['faceplate_thickness_mm'] == g['plate_t']
    assert len(pc['tip_hole_angles_deg']) == g['n_holes']


def _three_stub():
    return r"""
var _log = [];
var THREE = {
  MathUtils: { degToRad: function (d) { return d * Math.PI / 180; } },
  Group: function () { this.children = []; this.userData = {};
    this.add = function (c) { this.children.push(c); }; },
  CylinderGeometry: function (r1, r2, h) { this.r1 = r1; this.r2 = r2;
    this.h = h; },
  Vector3: function (x, y, z) { this.x = x; this.y = y; this.z = z; },
  Mesh: function (geo, mat) { this.geometry = geo; this.userData = {};
    var self = this;
    this.position = { y: 0, set: function (x, y, z) {
      self.position.x = x; self.position.y = y; self.position.z = z; } };
    this.quaternion = { setFromUnitVectors: function (a, b) {
      self.axis = [b.x, b.y, b.z]; } }; }
};
"""


def test_sahne_pintle_cizimi_kanonik_sayilarla(yanitlar):
    """GERÇEK ``buildPintle`` (node, THREE kaydedici taslağıyla): direk
    yarıçapı/boyu/yeri ve her deliğin çapı, derinliği, yönü, eksenel yeri
    yanıttaki sayılardır; sezgisel kesir yok."""
    if NODE is None:
        pytest.skip('node bulunamadı')
    from tests.support.kanit import kanit_gerekli
    spec = importlib.util.spec_from_file_location(
        'd34_js_olcum_k2', kanit_gerekli(D34_OLCUM))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = mod.oku(mod.VIZ_JS)
    govde = mod.govde(src, 'buildPintle')
    assert govde, 'buildPintle bulunamadı'
    pc = yanitlar['malzemeli']['motor']['injector_design']['pintle_cad']
    betik = _three_stub() + govde + """
var g = buildPintle(%s, {injector: 'M', orifice: 'O'}, false);
var post = g.children[0];
var holes = g.children.slice(1).map(function (h) { return {
  r: h.geometry.r1, h: h.geometry.h, axis: h.axis,
  x: h.position.x, y: h.position.y, z: h.position.z}; });
process.stdout.write(JSON.stringify({postR: post.geometry.r1,
  postH: post.geometry.h, postY: post.position.y, holes: holes}));
""" % json.dumps(pc)
    res = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=120)
    assert res.returncode == 0, res.stderr[-2000:]
    o = json.loads(res.stdout)
    R = pc['post_diameter_mm'] / 2
    assert o['postR'] == pytest.approx(R, abs=1e-12)
    assert o['postH'] == pytest.approx(pc['post_tip_x_mm']
                                       - pc['post_root_x_mm'], abs=1e-12)
    assert o['postY'] == pytest.approx((pc['post_tip_x_mm']
                                        + pc['post_root_x_mm']) / 2, abs=1e-12)
    assert len(o['holes']) == pc['tip_hole_count']
    for h, aci in zip(o['holes'], pc['tip_hole_angles_deg']):
        a = math.radians(aci)
        assert h['r'] == pytest.approx(pc['tip_hole_diameter_mm'] / 2)
        assert h['h'] == pytest.approx(pc['tip_hole_depth_mm'])
        assert h['axis'] == pytest.approx([math.cos(a), 0.0, math.sin(a)],
                                          abs=1e-12)
        assert h['y'] == pytest.approx(pc['tip_hole_row_x_mm'])
        assert math.hypot(h['x'], h['z']) == pytest.approx(
            R - pc['tip_hole_depth_mm'] / 2 + 0.01, abs=1e-9)


def test_sahne_extractdims_pintle_verisini_tasir(yanitlar):
    if NODE is None:
        pytest.skip('node bulunamadı')
    from tests.support.kanit import kanit_gerekli
    spec = importlib.util.spec_from_file_location(
        'd34_js_olcum_k2b', kanit_gerekli(D34_OLCUM))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = dict(yanitlar['malzemeli']['motor'], viz_motor_type='hybrid')
    betik = mod._viz_onsoz() + """
var d = extractDims(%s);
process.stdout.write(JSON.stringify(d.pintleCad));
""" % json.dumps(m)
    res = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=120)
    assert res.returncode == 0, res.stderr[-2000:]
    assert json.loads(res.stdout) == m['injector_design']['pintle_cad']


def test_montaj_plani_pintle_plakasi_anulus_delikli(yanitlar):
    """Montaj planının yüz plakası da tek anülüs delikli (eşdeğer orifis
    deseni delinmez)."""
    from hrma.export.motor_assembly import build_plan
    m = yanitlar['malzemeli']['motor']
    _n, g = _geo(m)
    plan = _sessiz(build_plan, m, 'hybrid')
    h3 = next(p for p in plan['parts'] if p['id'] == 'H03')
    assert h3['bbox_mm']['r_mm'][0] == pytest.approx(g['bore'] / 2, abs=1e-12)
    assert not h3['geometry'].get('holes')
    assert h3['bbox_mm']['x_mm'][1] - h3['bbox_mm']['x_mm'][0] == \
        pytest.approx(g['plate_t'], abs=1e-12)
