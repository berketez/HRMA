"""V301 CAD-2 kalem 5 (27 Eki 2026) — delikli enjektör plakasında STEP ⟷ STL.

ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/bilinen/cad2/once_k5.json``; dört
enjektör tipi x hibrit/sıvı): aynı paketin iki plakası ayrışıyordu —
STL delikleri dosyada -90° dönmüştü (13 delikli örnek hibritte 20,77°
kayma), STEP plakası ``rc - 0,5 mm`` (beyansız), STL ``rc``; STL plakası
``MESH_MAX_INJECTOR_ORIFICES = 16`` ile kırpılıyordu (24 / 25 / 78 delikli
vakalarda 16 delik). STL/STEP hacmi +%1,2 … +%4,6 farklıydı.

Onarım: yerleşim TEK çözümleyiciden (``injector_plate_hole_layout``):
halka, açı, delinen çap, plaka yarıçapı; sınır 512 (HRMA koruması), üstü
adlı ret. Bekçi: aynı paketteki STEP ve STL plakası dosyadan geri okunur;
delik sayısı, açıları, halka yarıçapı ve hacmi (32 kesitli çokgen katsayısı
içinde) eşit.
"""

import contextlib
import io
import math
import os

import numpy as np
import pytest

from tests.test_example_projects import (
    ENDPOINTS, HEADERS, calculate_payload, load_example_doc)
from tests.test_v3_cad_duzeltme import _step_hacim_uyarlamali

#: STL dönel katıları 32 kesitlidir; dairesel kesitin çokgen katsayısı
#: k = (32 / 2π) sin(2π / 32). Plaka ve delikleri aynı katsayıyla küçülür.
STL_KESIT = 32
STL_COKGEN_KATSAYISI = (STL_KESIT / (2.0 * math.pi)) * math.sin(
    2.0 * math.pi / STL_KESIT)
#: STL köşeleri float32 (``TOLERANS['stl_mm']`` kökeni); ölçülen sapma 3,5e-6.
STL_HACIM_BAGIL = 1e-5
#: Delik açısı / halka yarıçapı: STL delik merkezi 32-gen kesitin ağırlık
#: merkezinden okunur (ölçülen en büyük sapma 0,04°, 0,03 mm).
ACI_TOL_DERECE = 0.1
HALKA_TOL_MM = 0.05
#: Sınama yüz plakası [mm] — sıvı motor plaka kalınlığı yayımlamaz (F-CAD-9);
#: belgeli dışa aktarım alanına yalnız bu bekçide yazılır.
SINAMA_PLAKA_MM = 4.0


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


PLAKA_VAKALARI = {
    # ürün yolu: örnek hibrit, plaka kalınlığı kazanılmış (13 delik)
    'hibrit_ornek': ('hybrid', {}),
    # 16'nın üstü (eski mesh kırpması) ve 4'ün katı olmayan sayı
    'hibrit_swirl': ('hybrid', {'injector_type': 'swirl'}),
    'sivi_koaksiyel': ('liquid', {'injector_type': 'coaxial'}),
}


def _govde(client, tip, ezme):
    from hrma.export.cad_visualization import _injector_plate_design
    f = dict(load_example_doc(tip)['inputs']['fields'])
    f.update(ezme)
    r = _sessiz(client.post, ENDPOINTS[tip],
                json=calculate_payload(tip, f), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    y = r.get_json()
    md = dict(y['motor'] if tip == 'hybrid' else y['motor_geometry'])
    md['motor_name'] = 'V301_CAD2_PLAKA'
    if _injector_plate_design(md)['thickness_m'] is None:
        md['injector_results'] = {'plate_structural': {
            'plate_thickness_mm': SINAMA_PLAKA_MM}}
    return md


@pytest.fixture(scope='module')
def paketler(client, tmp_path_factory):
    pytest.importorskip('build123d')
    trimesh = pytest.importorskip('trimesh')
    from hrma.export.cad_visualization import MotorCADDesigner
    from hrma.export.step_export import generate_step_assembly
    out = {}
    for ad, (tip, ezme) in PLAKA_VAKALARI.items():
        md = _govde(client, tip, ezme)
        d = tmp_path_factory.mktemp(f'k5_{ad}')
        step = _sessiz(generate_step_assembly, md, out_dir=str(d / 'step'),
                       motor_type=tip)
        des = MotorCADDesigner()
        cad = _sessiz(des.generate_3d_motor_assembly, dict(md))
        _sessiz(des.export_stl_files, cad['assembly_meshes'],
                output_dir=str(d / 'stl'))
        out[ad] = {'md': md, 'step': step['injector'],
                   'stl': trimesh.load(str(d / 'stl' / 'injector.stl'))}
    return out


def _step_delikleri(yol):
    """STEP: eksen dışı çember kenarları -> {(açı°, halka mm, çap mm)}."""
    from build123d import GeomType, import_step
    sekil = import_step(yol)
    delik, dis_r = {}, 0.0
    for e in sekil.edges().filter_by(GeomType.CIRCLE):
        c = e.arc_center
        rr = math.hypot(c.Y, c.Z)
        if rr < 1e-6:
            dis_r = max(dis_r, e.radius)
            continue
        # İki yüzdeki kenar aynı deliktir; 0° ile 359,9999999° aynı açı.
        a = round(math.degrees(math.atan2(c.Z, c.Y)) % 360.0, 6) % 360.0
        delik[(a, round(rr, 6))] = 2.0 * e.radius
    return sorted((a, r, d) for (a, r), d in delik.items()), dis_r


def _stl_delikleri(mesh, plaka_r):
    """STL: plaka orta düzlem kesiti -> iç halkalar (delikler)."""
    x0, x1 = float(mesh.bounds[0][0]), float(mesh.bounds[1][0])
    kesit = mesh.section(plane_origin=[(x0 + x1) / 2.0, 0, 0],
                         plane_normal=[1, 0, 0])
    out = []
    for halka in kesit.discrete:
        yz = np.asarray(halka)[:, 1:]
        if np.max(np.hypot(*yz.T)) > 0.9 * plaka_r:
            continue                        # plakanın dış kenarı
        m = yz.mean(axis=0)
        out.append((math.degrees(math.atan2(m[1], m[0])) % 360.0,
                    float(np.hypot(*m))))
    return sorted(out)


def _aci_farki(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


@pytest.mark.parametrize('ad', list(PLAKA_VAKALARI))
def test_step_ve_stl_plakasi_ayni_delikler(paketler, ad):
    from hrma.export.cad_visualization import (
        _injector_plate_design, injector_plate_hole_layout)
    from hrma.export.motor_geometry import normalise_export_geometry
    from hrma.export.step_export import resolve_injector_plan
    p = paketler[ad]
    tip = PLAKA_VAKALARI[ad][0]
    n_md, _ = normalise_export_geometry(p['md'])
    plan = resolve_injector_plan(n_md, motor_type=tip)
    R = _injector_plate_design(n_md)['radius_m'] * 1000.0
    kahin = injector_plate_hole_layout(n_md, plan['circuits'], R)
    n_tasarim = sum(c['n'] for c in kahin)
    step, step_r = _step_delikleri(p['step'])
    stl = _stl_delikleri(p['stl'], R)
    assert len(step) == len(stl) == n_tasarim, (len(step), len(stl),
                                                n_tasarim)
    assert step_r == pytest.approx(R, abs=1e-6)
    beklenen = sorted(
        (math.degrees(a) % 360.0, c['ring_r_mm'], c['d_drill_mm'])
        for c in kahin for a in c['angles_rad'])
    for (a_s, r_s, d_s), (a_k, r_k, d_k) in zip(step, beklenen):
        assert _aci_farki(a_s, a_k) < 1e-6 and r_s == pytest.approx(
            r_k, abs=1e-6) and d_s == pytest.approx(d_k, abs=1e-6)
    # STL: her STEP deliğinin karşılığı aynı açı ve halkada
    for a_s, r_s, _d in step:
        en_yakin = min(stl, key=lambda h: _aci_farki(h[0], a_s)
                       + abs(h[1] - r_s))
        assert _aci_farki(en_yakin[0], a_s) < ACI_TOL_DERECE, (a_s, en_yakin)
        assert abs(en_yakin[1] - r_s) < HALKA_TOL_MM, (r_s, en_yakin)


@pytest.mark.parametrize('ad', list(PLAKA_VAKALARI))
def test_step_ve_stl_plakasi_ayni_hacim(paketler, ad):
    p = paketler[ad]
    v_step = _step_hacim_uyarlamali(p['step'])
    v_stl = float(p['stl'].volume)
    assert bool(p['stl'].is_watertight)
    assert abs(v_stl / v_step - STL_COKGEN_KATSAYISI) <= STL_HACIM_BAGIL, (
        v_stl / v_step, STL_COKGEN_KATSAYISI)


def test_yerlesim_sinir_ustunde_adli_ret():
    from hrma.export.cad_visualization import (
        MESH_MAX_INJECTOR_ORIFICES, InjectorPlateLayoutError,
        injector_plate_hole_layout)
    devre = [{'name': 'oxidizer', 'n': MESH_MAX_INJECTOR_ORIFICES + 1,
              'd_mm': 0.6}]
    with pytest.raises(InjectorPlateLayoutError,
                       match='injector_orifices_exceed_cad_limit'):
        injector_plate_hole_layout({}, devre, 50.0)
    with pytest.raises(InjectorPlateLayoutError,
                       match='injector_plate_radius_not_resolved'):
        injector_plate_hole_layout({}, [{'name': 'oxidizer', 'n': 4,
                                         'd_mm': 1.0}], None)
    ok = injector_plate_hole_layout(
        {}, [{'name': 'oxidizer', 'n': MESH_MAX_INJECTOR_ORIFICES,
              'd_mm': 0.6}], 50.0)
    assert sum(c['n'] for c in ok) == MESH_MAX_INJECTOR_ORIFICES


def test_stl_plaka_kirpilmis_planla_delinmez(paketler):
    """Tasarımın gerçek delik sayısı sınırı aşarsa STL plakası kırpılmış
    planla DELİNMEZ: adlı ret (sessiz kırpma yok)."""
    from hrma.export.cad_visualization import (
        MESH_MAX_INJECTOR_ORIFICES, MotorCADDesigner)
    md = dict(paketler['hibrit_ornek']['md'])
    md['injector_orifices_real'] = MESH_MAX_INJECTOR_ORIFICES + 1
    md['injector_mesh_circuits'] = [{'name': 'oxidizer', 'n': 16,
                                     'd_mm': 1.0}]
    with pytest.raises(ValueError, match='injector_orifices_exceed_cad_limit'):
        _sessiz(MotorCADDesigner()._create_injector_head, 0.0848, md)
