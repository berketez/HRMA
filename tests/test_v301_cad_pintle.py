"""V301 bilinen C2 — CAD'de gerçek pintle (22 Eki 2026).

CHANGELOG bilinen sınırı: "CAD/STEP pintle'ı hâlâ eşdeğer orifisli düz plaka
olarak çiziyor". Kanonik pintle geometrisi (V301/E1) yanıtta
``injector_design.pintle_geometry``dedir (sıvıda dışa aktarım gövdesine
``motor_geometry.liquid_results_to_motor_geometry`` taşır). STEP ve STL artık
onu TEK çözümleyiciden (``cad_visualization.pintle_cad_geometry``) çizer:
merkez direk + uç, uçta gerçek radyal delikler, yüz plakası yayımlanmışsa
anülüs delikli plaka. Kanonik geometri yoksa / okunamıyorsa / çizilemiyorsa
ADLI ret; düz plakaya sessiz dönüş YOK.

Bekçiler:
1. İddia ⟷ CAD kapısı: direk çapı ve boyu, delik sayısı / çapı / açıları /
   L_s konumu, anülüs deliği — STEP (OCC sınıflayıcı) ve STL (ışın sayımı)
   dosyadan ÖLÇÜLÜR, kanonik sayıyla karşılaştırılır.
2. STEP katıları ``valid``, STL parçaları kapalı; STEP ⟷ STL hacmi eşit.
3. Künye neyin çizildiğini söyler; düz plaka yolu pintle'da kapalı.
4. Fail-closed ve saldırgan girdi; tek kaynak (çözümleyiciyi değiştir, iki
   üretici birlikte değişsin); sıvı gövdesi kanonik bloğu taşır.

Ölçüm notu: STL'in dönel katıları 32 kesitli çokgendir; çokgen yüzü
yarıçapın cos(pi/32) katına iner (%0,48). Yüzey yakınındaki yoklamalar bu
yüzden delik derinliğinin dörtte biri içeriden yapılır.
"""

import contextlib
import copy
import io
import math
import os
import re

import numpy as np
import pytest

from tests.test_example_projects import (
    ENDPOINTS, HEADERS, calculate_payload, load_example_doc)
from tests.test_v3_cad_duzeltme import _step_hacim_uyarlamali, _tol

#: Sınama yüz plakası kalınlığı [mm] — YALNIZ yüz plakası dalını sınamak
#: için dışa aktarım sözleşmesinin belgeli alanına
#: (``injector_results.plate_structural.plate_thickness_mm``) yazılır;
#: bugün hiçbir pintle çözücüsü plaka kalınlığı yayımlamaz.
SINAMA_PLAKA_MM = 4.0
#: Açısal yoklama sayısı (delik sayısının katı; her deliğe >= 8 yoklama).
ACI_YOKLAMA_KATSAYISI = 16


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


def _pintle_yaniti(client, tip):
    doc = load_example_doc(tip)
    alanlar = dict(doc['inputs']['fields'])
    alanlar['injector_type'] = 'pintle'
    r = _sessiz(client.post, ENDPOINTS[tip],
                json=calculate_payload(tip, alanlar), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def yanitlar(client):
    return {'hybrid': _pintle_yaniti(client, 'hybrid'),
            'liquid': _pintle_yaniti(client, 'liquid')}


@pytest.fixture(scope='module')
def govdeler(yanitlar):
    """Arayüzün dışa aktarıma gönderdiği gövdeler (+ yüz plakası sınaması)."""
    hib = dict(yanitlar['hybrid']['motor'])
    hib['motor_name'] = 'V301_PINTLE_HIBRIT'
    siv = dict(yanitlar['liquid']['motor_geometry'])
    siv['motor_name'] = 'V301_PINTLE_SIVI'
    plaka = copy.deepcopy(hib)
    plaka['motor_name'] = 'V301_PINTLE_PLAKA'
    plaka['injector_results'] = {'plate_structural': {
        'plate_thickness_mm': SINAMA_PLAKA_MM}}
    return {'hybrid': (hib, 'hybrid'), 'liquid': (siv, 'liquid'),
            'plaka': (plaka, 'hybrid')}


def _paket(md, tip, d):
    pytest.importorskip('build123d')
    trimesh = pytest.importorskip('trimesh')
    from hrma.export.cad_visualization import (
        MotorCADDesigner, pintle_cad_geometry)
    from hrma.export.motor_geometry import normalise_export_geometry
    from hrma.export.step_export import generate_step_assembly
    step = _sessiz(generate_step_assembly, md, out_dir=str(d / 'step'),
                   motor_type=tip)
    designer = MotorCADDesigner()
    cad = _sessiz(designer.generate_3d_motor_assembly, dict(md))
    assert not cad.get('error'), cad.get('error')
    _sessiz(designer.export_stl_files, cad['assembly_meshes'],
            output_dir=str(d / 'stl'))
    n, _ = normalise_export_geometry(md)
    return {'step': step, 'geo': pintle_cad_geometry(n),
            'stl': trimesh.load(str(d / 'stl' / 'injector.stl')),
            'cad': cad}


@pytest.fixture(scope='module')
def paketler(govdeler, tmp_path_factory):
    return {ad: _paket(md, tip, tmp_path_factory.mktemp(f'c2_{ad}'))
            for ad, (md, tip) in govdeler.items()}


# ---------------------------------------------------------------------------
# Ölçüm araçları — dosyadan, üreticiden bağımsız
# ---------------------------------------------------------------------------
def _step_ici(yol):
    """STEP dosyasındaki katılar için nokta -> içeride mi (OCC sınıflayıcı)."""
    from build123d import import_step
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_IN
    from OCP.gp import gp_Pnt
    katilar = [k.wrapped for k in import_step(yol).solids()]

    def ici(p):
        for k in katilar:
            s = BRepClass3d_SolidClassifier(k, gp_Pnt(*map(float, p)), 1e-7)
            if s.State() == TopAbs_IN:
                return True
        return False
    return lambda pts: np.array([ici(p) for p in pts])


def _stl_ici(mesh):
    """Kapalı STL için nokta -> içeride mi: ışın-üçgen kesişim sayısının
    tekliği (Möller-Trumbore, numpy; rtree gerektirmez). Bir ışın kenar ya
    da köşeden geçerse tekliği bozulabilir; bu yüzden birbirine eğik ÜÇ
    ışının çoğunluk oyu alınır."""
    tri = np.asarray(mesh.triangles, dtype=float)
    v0, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    yonler = [np.array(y) / np.linalg.norm(y) for y in (
        (0.5773, 0.6123, 0.5401), (-0.7071, 0.3162, 0.6325),
        (0.2673, -0.8018, 0.5345))]
    hazir = []
    for yon in yonler:
        pv = np.cross(yon, e2)
        det = np.einsum('ij,ij->i', e1, pv)
        gecerli = np.abs(det) > 1e-14
        inv = np.where(gecerli, 1.0 / np.where(gecerli, det, 1.0), 0.0)
        hazir.append((yon, pv, gecerli, inv))

    def tek(p, yon, pv, gecerli, inv):
        tv = p - v0
        u = np.einsum('ij,ij->i', tv, pv) * inv
        qv = np.cross(tv, e1)
        v = (qv @ yon) * inv
        t = np.einsum('ij,ij->i', e2, qv) * inv
        vur = gecerli & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
        return int(vur.sum()) % 2 == 1

    def ici(p):
        return sum(tek(p, *h) for h in hazir) >= 2
    return lambda pts: np.array([ici(np.asarray(p, float)) for p in pts])


def _yoklayici(paket, bicim):
    if bicim == 'STEP':
        return _step_ici(paket['step']['injector']), _tol('step_mm')
    return _stl_ici(paket['stl']), _tol('stl_mm')


def _nokta(x, r, a):
    """+X eksen sözleşmesi (STEP ve STL dosyası): (x, r cos a, r sin a)."""
    return (x, r * math.cos(a), r * math.sin(a))


PINTLE_BICIMLERI = ['STEP', 'STL']
PINTLE_VAKALARI = ['hybrid', 'liquid', 'plaka']


# ===========================================================================
# 1) İddia ⟷ CAD kapısı
# ===========================================================================
@pytest.mark.parametrize('bicim', PINTLE_BICIMLERI)
@pytest.mark.parametrize('vaka', PINTLE_VAKALARI)
class TestIddiaCAD:
    def test_kanonik_sayilar_cizimde(self, paketler, govdeler, vaka, bicim):
        """Çözümleyicinin taşıdığı sayılar yanıttaki kanonik bloğun AYNISI
        (kopya ya da yeniden türetme yok)."""
        geo = paketler[vaka]['geo']
        md, _tip = govdeler[vaka]
        pg = md['injector_design']['pintle_geometry']
        assert geo['d_post'] == float(pg['d_pintle_mm'])
        assert geo['gap'] == float(pg['annulus_gap_mm'])
        assert geo['n_holes'] == int(pg['n_radial_holes'])
        assert geo['d_hole'] == float(pg['radial_hole_d_mm'])
        assert geo['skip'] == float(pg['skip_distance_mm'])
        assert geo['bore'] == pytest.approx(
            float(pg['d_pintle_mm']) + 2.0 * float(pg['annulus_gap_mm']),
            rel=1e-12)

    def test_delik_sayisi_aci_ve_konum(self, paketler, vaka, bicim):
        geo = paketler[vaka]['geo']
        ici, tol = _yoklayici(paketler[vaka], bicim)
        n, d, x_h = geo['n_holes'], geo['d_hole'], geo['x_holes']
        assert x_h == pytest.approx(geo['x_face'] + geo['skip'], abs=1e-12)
        r_y = geo['d_post'] / 2.0 - 0.25 * geo['hole_depth']
        m = ACI_YOKLAMA_KATSAYISI * n
        acilar = [2.0 * math.pi * (k + 0.5) / m for k in range(m)]
        bos = ~ici([_nokta(x_h, r_y, a) for a in acilar])
        # Dairesel dizide boşluk (delik) koşularını say
        kosular = sum(1 for k in range(m) if bos[k] and not bos[k - 1])
        assert kosular == n, (vaka, bicim, kosular, n)
        # Her kanonik açıda delik var, iki delik arasında malzeme var
        for i in range(n):
            a = 2.0 * math.pi * i / n
            assert not ici([_nokta(x_h, r_y, a)])[0], (i, 'delik yok')
            assert ici([_nokta(x_h, r_y, a + math.pi / n)])[0], (
                i, 'delikler arası malzeme yok')

    def test_delik_capi_ekseni_boyunca(self, paketler, vaka, bicim):
        """Delik ekseninde, yüzeyin hemen altında: delik eksenel olarak
        [x_h - d/2, x_h + d/2] aralığını kaplar (tol içinde)."""
        geo = paketler[vaka]['geo']
        ici, tol = _yoklayici(paketler[vaka], bicim)
        d, x_h = geo['d_hole'], geo['x_holes']
        r_y = geo['d_post'] / 2.0 - 0.25 * geo['hole_depth']
        for i in range(geo['n_holes']):
            a = 2.0 * math.pi * i / geo['n_holes']
            ic, dis = ici([_nokta(x_h + s * (d / 2.0 - tol), r_y, a)
                           for s in (-1, 1)]), ici(
                [_nokta(x_h + s * (d / 2.0 + tol), r_y, a) for s in (-1, 1)])
            assert not ic.any(), (i, 'delik çaptan dar')
            assert dis.all(), (i, 'delik çaptan geniş')

    def test_delik_derinligi_beyanli_cizim_secimi(self, paketler, vaka,
                                                  bicim):
        """Delik dibi, beyanlı kuralın yerinde: komşu deliklerin değeceği
        yarıçapa (r_c = d / (2 sin(pi/n))) giden yolun
        ``PINTLE_CAD_TIP_HOLE_DEPTH_FRACTION``ı. Kural bu testte AYRICA
        hesaplanır (çözümleyicinin sayısına güvenilmez)."""
        from hrma.export.cad_visualization import (
            PINTLE_CAD_TIP_HOLE_DEPTH_FRACTION)
        geo = paketler[vaka]['geo']
        ici, tol = _yoklayici(paketler[vaka], bicim)
        n, d, r = geo['n_holes'], geo['d_hole'], geo['d_post'] / 2.0
        r_c = d / (2.0 * math.sin(math.pi / n)) if n > 1 else 0.0
        derinlik = PINTLE_CAD_TIP_HOLE_DEPTH_FRACTION * (r - r_c)
        assert geo['hole_depth'] == pytest.approx(derinlik, rel=1e-12)
        for i in range(n):
            a = 2.0 * math.pi * i / n
            assert not ici([_nokta(geo['x_holes'], r - derinlik + 2 * tol,
                                   a)])[0], (i, 'delik dipten sığ')
            assert ici([_nokta(geo['x_holes'], r - derinlik - 2 * tol,
                               a)])[0], (i, 'delik dipten derin')

    def test_direk_capi_kok_ve_uc(self, paketler, vaka, bicim):
        geo = paketler[vaka]['geo']
        ici, tol = _yoklayici(paketler[vaka], bicim)
        r = geo['d_post'] / 2.0
        x_orta = 0.5 * (geo['x_face'] + geo['x_holes'] - geo['d_hole'] / 2.0)
        if geo['plate_t'] is None:
            x_orta = 0.5 * (geo['x0'] + geo['x_holes'] - geo['d_hole'] / 2.0)
        # STL çokgeninin yüzü yarıçapın cos(pi/32) katına iner
        ic_r = r * math.cos(math.pi / 32) - tol
        for a in np.linspace(0.0, 2.0 * math.pi, 7)[:-1]:
            assert ici([_nokta(x_orta, ic_r, a)])[0]
            assert not ici([_nokta(x_orta, r + tol, a)])[0]
        # Kök kapak iç yüzünde, uç x_tip'te (eksen üzerinde yokla)
        assert ici([(geo['x0'] + tol, 0.0, 0.0),
                    (geo['x_tip'] - tol, 0.0, 0.0)]).all()
        assert not ici([(geo['x0'] - tol, 0.0, 0.0),
                        (geo['x_tip'] + tol, 0.0, 0.0)]).any()

    def test_anulus_deligi(self, paketler, vaka, bicim):
        geo = paketler[vaka]['geo']
        ici, tol = _yoklayici(paketler[vaka], bicim)
        x = 0.5 * (geo['x0'] + geo['x_face'])
        r_post, r_bore = geo['d_post'] / 2.0, geo['bore'] / 2.0
        if geo['plate_t'] is None:
            # Yüz plakası yayımlanmamış: plaka (ve içindeki anülüs deliği)
            # ÇİZİLMEZ — direğin dışında, yüz önünde hiçbir malzeme yok
            # (eski düz plaka / eşdeğer delik yolu dahil).
            x_on = geo['x0'] + 0.5 * (geo['x_holes'] - geo['d_hole'] / 2.0
                                      - geo['x0'])
            for a in np.linspace(0.0, 2.0 * math.pi, 5)[:-1]:
                assert not ici([_nokta(x_on, r, a) for r in (
                    r_post + 2 * tol, r_bore + 2 * tol,
                    3.0 * r_bore)]).any()
            return
        for a in np.linspace(0.0, 2.0 * math.pi, 5)[:-1]:
            # anülüs boşluğunun ortası: ne direk ne plaka
            assert not ici([_nokta(x, 0.5 * (r_post + r_bore), a)])[0]
            assert ici([_nokta(x, r_bore + 2 * tol, a),
                        _nokta(x, r_post * math.cos(math.pi / 32) - tol,
                               a)]).all()
            # Eşdeğer orifis planı DELİNMEMİŞ: eski düz plakanın ilk halkası
            # (0,7 R) dolu
            assert ici([_nokta(x, 0.7 * geo['plate_r'], a)])[0]


# ===========================================================================
# 2) Katı geçerliliği, kapalılık, hacim eşitliği
# ===========================================================================
@pytest.mark.parametrize('vaka', PINTLE_VAKALARI)
class TestKatilar:
    def test_step_katilari_gecerli(self, paketler, vaka):
        from build123d import import_step
        katilar = import_step(paketler[vaka]['step']['injector']).solids()
        beklenen = 1 if paketler[vaka]['geo']['plate_t'] is None else 2
        assert len(katilar) == beklenen
        for k in katilar:
            v = k.is_valid
            assert (v() if callable(v) else v)

    def test_stl_kapali(self, paketler, vaka):
        m = paketler[vaka]['stl']
        assert m.is_watertight and m.is_volume
        beklenen = 1 if paketler[vaka]['geo']['plate_t'] is None else 2
        assert len(m.split(only_watertight=False)) == beklenen

    def test_step_ile_stl_hacmi_esit(self, paketler, vaka):
        v_step = _step_hacim_uyarlamali(paketler[vaka]['step']['injector'])
        v_stl = float(paketler[vaka]['stl'].volume)
        assert abs(v_stl / v_step - 1.0) <= _tol('hacim_bagil'), (
            vaka, v_step, v_stl)

    def test_cad_sozlugu_ayni_parcayi_tartar(self, paketler, vaka):
        """3B görünümün (``/calculate`` cad_design) enjektör parçası da
        aynı çözümleyiciden: STL dosyasıyla aynı hacim (mm³ ⟷ m³)."""
        mesh = dict(paketler[vaka]['cad']['assembly_meshes'])['Injector']
        assert float(mesh.volume) * 1e9 == pytest.approx(
            float(paketler[vaka]['stl'].volume), rel=1e-5)


# ===========================================================================
# 3) Künye ve düz plaka yolunun kapalılığı
# ===========================================================================
def _step_adlari(yol):
    compact = ''.join(open(yol, encoding='utf-8', errors='ignore')
                      .read().split())
    return re.findall(r"PRODUCT\('((?:[^']|'')*)'", compact)


@pytest.mark.parametrize('vaka', PINTLE_VAKALARI)
def test_step_kunyesi_cizileni_soyler(paketler, vaka):
    geo = paketler[vaka]['geo']
    adlar = ' '.join(_step_adlari(paketler[vaka]['step']['injector']))
    assert 'injector(pintle;' in adlar
    assert 'canonicalgeometryinjector_design.pintle_geometry' in adlar
    assert f"{geo['n_holes']}xd{geo['d_hole']:.3f}mmtipholes" in adlar
    assert f"L_s={geo['skip']:.3f}mm" in adlar
    assert 'HRMAdrawingchoices,noliteraturevalue' in adlar
    assert 'isNOTdrilled' in adlar
    assert 'pintlepost(' in adlar
    if geo['plate_t'] is None:
        assert 'injectorfaceplate/bodyNOTmodelled' in adlar
        assert 'pintlefaceplate(' not in adlar
    else:
        assert 'pintlefaceplate(' in adlar
        assert 'withtheannulusbore' in adlar


def test_duz_plaka_yolu_pintle_da_kapali(govdeler):
    from hrma.export.cad_visualization import MotorCADDesigner
    from hrma.export.motor_geometry import normalise_export_geometry
    md, _ = normalise_export_geometry(govdeler['plaka'][0])
    with pytest.raises(ValueError, match='flat_plate_path_refused_for_pintle'):
        _sessiz(MotorCADDesigner()._create_injector_head,
                float(md['chamber_diameter']), md)


def test_pintle_disi_tip_bu_yola_girmez():
    from hrma.export.cad_visualization import (
        pintle_cad_geometry, pintle_type_claimed)
    md = {'injector_design': {'injector_type': 'showerhead',
                              'pintle_geometry': {'d_pintle_mm': 5.0}}}
    assert pintle_type_claimed(md) is False
    assert pintle_cad_geometry(md) is None


# ===========================================================================
# 4) Fail-closed, saldırgan girdi, tek kaynak, sıvı gövdesi
# ===========================================================================
def _bozuk(md, **pg):
    m = copy.deepcopy(md)
    blok = m['injector_design']['pintle_geometry']
    for k, v in pg.items():
        if v is _SIL:
            blok.pop(k, None)
        else:
            blok[k] = v
    return m


_SIL = object()


@pytest.mark.parametrize('degisiklik,neden', [
    ({'d_pintle_mm': 'abc'}, 'not_a_finite_positive_length'),
    ({'d_pintle_mm': float('nan')}, 'not_a_finite_positive_length'),
    ({'d_pintle_mm': -5.0}, 'not_a_finite_positive_length'),
    ({'d_pintle_mm': 1e300}, 'inconsistent_with_post'),
    ({'annulus_gap_mm': True}, 'not_a_finite_positive_length'),
    ({'n_radial_holes': 2.5}, 'not_a_positive_integer'),
    ({'n_radial_holes': True}, 'not_a_positive_integer'),
    ({'n_radial_holes': 10 ** 9}, 'too_many_tip_holes_to_draw'),
    ({'radial_hole_d_mm': 50.0}, 'tip_holes_overlap_on_post_surface'),
    ({'skip_distance_mm': 1e-6}, 'hole_row_inside_injector_face'),
    ({'secondary_holes': 'tangential'}, 'tangential_holes_not_drawable'),
    ({'secondary_holes': {'x': 1}}, 'unknown_tip_hole_mode'),
    ({'annulus_bore_diameter_mm': 99.0}, 'inconsistent_with_post'),
])
def test_bozuk_kanonik_blok_adli_ret(govdeler, degisiklik, neden):
    from hrma.export.cad_visualization import (
        PintleCADError, pintle_cad_geometry)
    md = _bozuk(govdeler['hybrid'][0], **degisiklik)
    with pytest.raises(PintleCADError) as e:
        pintle_cad_geometry(md)
    assert e.value.invalid_fields[0]['reason'] == neden
    # Ret metni istemci değerini yansıtmaz (yalnız tür izi)
    assert 'abc' not in str(e.value) or neden != \
        'not_a_finite_positive_length'


def test_kanonik_blok_yoksa_step_ve_stl_reddeder(govdeler, tmp_path):
    pytest.importorskip('build123d')
    from hrma.export.cad_visualization import MotorCADDesigner
    from hrma.export.step_export import (
        StepExportDataError, generate_step_assembly)
    md = copy.deepcopy(govdeler['hybrid'][0])
    del md['injector_design']['pintle_geometry']
    md['injector_design_detail'] = dict(md.get('injector_design_detail')
                                        or {})
    md['injector_design_detail'].pop('pintle_geometry', None)
    with pytest.raises(StepExportDataError) as e:
        _sessiz(generate_step_assembly, md, out_dir=str(tmp_path),
                motor_type='hybrid')
    assert e.value.invalid_fields[0]['reason'] == \
        'pintle_geometry_not_published'
    cad = _sessiz(MotorCADDesigner().generate_3d_motor_assembly, md)
    assert 'pintle_geometry_not_published' in (cad.get('error') or '')
    assert not cad['assembly_meshes']


def test_tip_celiskisi_reddedilir(govdeler):
    from hrma.export.cad_visualization import (
        PintleCADError, pintle_cad_geometry)
    md = copy.deepcopy(govdeler['hybrid'][0])
    md['injector_results'] = {'injector_type': 'showerhead'}
    with pytest.raises(PintleCADError) as e:
        pintle_cad_geometry(md)
    assert e.value.invalid_fields[0]['reason'] == 'injector_type_conflict'


def test_deliksiz_kip_direk_yuze_kadar(govdeler):
    from hrma.export.cad_visualization import (
        MotorCADDesigner, pintle_cad_geometry)
    md = _bozuk(govdeler['hybrid'][0], secondary_holes='none',
                n_radial_holes=0, skip_distance_mm=None)
    geo = pintle_cad_geometry(md)
    # Yüz plakası yok + deliksiz: çizilecek hacim yok -> parça uydurulmaz,
    # gerekçe adıyla taşınır
    assert geo['n_holes'] == 0 and geo['x_tip'] == geo['x_face']
    assert geo['not_drawn_reason'].startswith(
        'pintle_not_drawable_without_faceplate')
    md2 = copy.deepcopy(govdeler['plaka'][0])
    md2['injector_design']['pintle_geometry'].update(
        secondary_holes='none', n_radial_holes=0, skip_distance_mm=None)
    geo2 = pintle_cad_geometry(md2)
    assert geo2['not_drawn_reason'] is None
    mesh = MotorCADDesigner()._create_pintle_injector(geo2)
    assert mesh.is_volume
    assert float(mesh.bounds[1][2]) * 1000.0 == pytest.approx(
        geo2['x_face'], abs=_tol('stl_mm'))


def test_direk_tane_girisimi_ayni_hukum():
    from hrma.export.cad_visualization import pintle_assembly_refusal
    geo = {'x_tip': 30.0, 'd_post': 20.0, 'source_path': 'p'}
    assert pintle_assembly_refusal(geo, 100.0, 25.0, 12.0) is None
    red = pintle_assembly_refusal(geo, 100.0, 25.0, 8.0)
    assert red.invalid_fields[0]['reason'] == \
        'pintle_post_intersects_fuel_grain'
    red = pintle_assembly_refusal(geo, 20.0)
    assert red.invalid_fields[0]['reason'] == \
        'pintle_post_longer_than_chamber'


def test_iki_uretici_tek_cozumleyiciden_okur(govdeler, monkeypatch,
                                            tmp_path):
    """``pintle_cad_geometry`` sınama için direği %10 kalınlaştırır; STEP ve
    STL ikisi de bunu görmeli (biri kendi kopyasına dönerse kırmızı)."""
    from hrma.export import cad_visualization as cv
    asil = cv.pintle_cad_geometry

    def kalin(md, chamber_diameter_m=None):
        geo = asil(md, chamber_diameter_m)
        return dict(geo, d_post=geo['d_post'] * 1.1) if geo else geo

    monkeypatch.setattr(cv, 'pintle_cad_geometry', kalin)
    paket = _paket(govdeler['hybrid'][0], 'hybrid', tmp_path)
    beklenen = paket['geo']['d_post']
    assert beklenen == pytest.approx(
        1.1 * float(govdeler['hybrid'][0]['injector_design']
                    ['pintle_geometry']['d_pintle_mm']))
    from build123d import import_step
    b = import_step(paket['step']['injector']).bounding_box()
    assert b.size.Y == pytest.approx(beklenen, abs=_tol('step_mm'))
    r_stl = float(np.max(np.hypot(paket['stl'].vertices[:, 1],
                                  paket['stl'].vertices[:, 2])))
    assert 2.0 * r_stl == pytest.approx(beklenen, abs=2 * _tol('stl_mm'))


def test_sivi_govdesi_kanonik_blogu_aynen_tasir(yanitlar):
    from hrma.export.motor_geometry import liquid_results_to_motor_geometry
    ham = yanitlar['liquid']
    kanon = ham['injection_system']['injector_design_detail'][
        'pintle_geometry']
    mg = liquid_results_to_motor_geometry(ham)
    assert mg['injector_design']['pintle_geometry'] == kanon
    assert ham['motor_geometry']['injector_design']['pintle_geometry'] == \
        kanon
    # Pintle olmayan sıvıda blok YAZILMAZ (uydurulmaz)
    ham2 = copy.deepcopy(ham)
    ham2['injection_system']['injector_design_detail'].pop(
        'pintle_geometry')
    assert 'pintle_geometry' not in liquid_results_to_motor_geometry(
        ham2)['injector_design']


def test_hesap_yaniti_3b_gorunumu_pintle_cizer(yanitlar):
    """``/calculate`` 3B görünümü (cad_design) pintle'ı hatasız çizer."""
    cad = yanitlar['hybrid'].get('cad_design') or {}
    assert not cad.get('error'), cad.get('error')
    adlar = [p['name'] for p in cad.get('assembly_mesh_summary') or []]
    assert 'Injector' in adlar


# ===========================================================================
# 5) Çizim PDF'i: pintle yüz görünüşü ve ölçü tablosu (aynı çözümleyici)
# ===========================================================================
def test_cizim_yapragi_pintle_figurunu_basar(govdeler, monkeypatch):
    """Çizim paketinin enjektör yaprağı (``_injector_face_png``) pintle'da
    eşdeğer orifis desenini DEĞİL pintle yüz görünüşünü işler."""
    from hrma.export import drawing_generator as dg
    from hrma.export.motor_geometry import normalise_export_geometry
    md, _ = normalise_export_geometry(govdeler['hybrid'][0])
    yakalanan = []
    monkeypatch.setattr(dg, '_render_or_raise',
                        lambda fig, **_k: yakalanan.append(fig) or b'png')
    assert dg._injector_face_png(md) == b'png'
    baslik = yakalanan[0].layout.title.text
    assert 'post d' in baslik and 'is NOT drilled' in baslik


def test_cizim_yuz_gorunusu_pintle(govdeler):
    from hrma.export import drawing_generator as dg
    from hrma.export.cad_visualization import pintle_cad_geometry
    from hrma.export.motor_geometry import normalise_export_geometry
    for ad in ('hybrid', 'plaka'):
        md, _ = normalise_export_geometry(govdeler[ad][0])
        geo = pintle_cad_geometry(md)
        fig = dg._pintle_face_figure(md)
        baslik = fig.layout.title.text
        assert 'pintle' in baslik and 'is NOT drilled' in baslik
        assert f"{geo['n_holes']} x d{geo['d_hole']:.2f} mm" in baslik
        assert f"post d{geo['d_post']:.2f} mm" in baslik
        # Uç delikleri: tam n radyal çentik; eşdeğer plan dairesi YOK
        assert len([s for s in fig.layout.shapes if s.type == 'line']) == \
            geo['n_holes']
        assert not [s for s in fig.layout.shapes if s.type == 'circle']
        kesik = [t.line.dash for t in fig.data]
        assert kesik.count('dash') == (1 if geo['plate_t'] is None else 0)


def test_cizim_tablosu_pintle_satiri(govdeler):
    from hrma.export import drawing_generator as dg
    from hrma.export.cad_visualization import _injector_spec
    from hrma.export.motor_geometry import normalise_export_geometry
    md, _ = normalise_export_geometry(govdeler['hybrid'][0])
    deger = dg._pintle_schedule_value(md, _injector_spec(md))
    assert 'tip holes at L_s' in deger and 'NOT drilled' in deger
    bozuk = copy.deepcopy(md)
    del bozuk['injector_design']['pintle_geometry']
    bozuk.get('injector_design_detail', {}).pop('pintle_geometry', None)
    assert 'pintle_geometry_not_published' in dg._pintle_schedule_value(
        bozuk, _injector_spec(bozuk))


def test_cizim_pdf_pintle_yapragi(govdeler, tmp_path):
    pypdf = pytest.importorskip('pypdf')
    from hrma.export import drawing_generator as dg
    from hrma.export.motor_geometry import normalise_export_geometry
    md, _ = normalise_export_geometry(govdeler['hybrid'][0])
    yol = _sessiz(dg.generate_drawing_pdf, md,
                  out_path=str(tmp_path / 'p.pdf'))
    metin = '\n'.join(p.extract_text() or ''
                      for p in pypdf.PdfReader(yol).pages)
    assert 'INJECTOR FACE PATTERN' in metin
    assert 'Injector render failed' not in metin
    assert 'Injector (pintle)' in metin
    assert 'Injector orifices' not in metin


@pytest.mark.parametrize('vaka', PINTLE_VAKALARI)
def test_cizim_sozlugu_montajla_ayni_hukum(paketler, vaka):
    """``technical_drawings.injector`` (``/calculate`` cad_design) pintle'ı
    montajla AYNI çözümleyiciden anlatır: çizildiğini, sayılarını ve
    eşdeğer orifis planının DELİNMEDİĞİNİ söyler."""
    geo = paketler[vaka]['geo']
    inj = paketler[vaka]['cad']['technical_drawings']['injector']
    assert inj['present_in_this_run'] is True
    assert inj['not_drawn_reason'] is None
    p = inj['pintle']
    assert p['drawn'] is True
    assert (p['post_diameter_mm'], p['tip_hole_count'],
            p['tip_hole_diameter_mm'], p['skip_distance_mm']) == (
        geo['d_post'], geo['n_holes'], geo['d_hole'], geo['skip'])
    assert p['annulus_bore_drawn'] is (geo['plate_t'] is not None)
    assert 'is NOT drilled' in p['equivalent_orifice_plan']
