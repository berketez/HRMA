"""v3.0 CAD düzeltme kulvarı — A1: hibrit tek kaynak + imalat emniyet kapısı.

Kaynak: 7 Eki 2026 bağımsız CAD kontrolü (FreeCAD başsız;
``docs/scofield/raw/OH/CAD/kontrol-2026-10-07``) — topoloji sağlam, geometri
doğruluğunda 9 HATA. Karar ``berke_kararlari_2026-09-23.md`` §28-21 (CAD
maddeleri) ve §28-29. Rapor ve önce/sonra ölçümü:
``docs/scofield/raw/OH/V3/cad-duzeltme/``.

Bu dosya iki bekçi ailesi taşır:

1. **İddia ⟷ CAD kapısı (hibrit ayakları)** — CAD kontrolünün
   ``06_iddia_karsilastir.py`` mantığından: AYNI analiz yanıtının yayımladığı
   her ölçü, dışa aktarılan dosyadan ÖLÇÜLEN değere karşı aşağıdaki
   ``TOLERANS`` tablosuyla sınanır. Tablo ölçümden ÖNCE yazıldı, sonuca göre
   değiştirilmez.

   * STEP ayakları FreeCAD (``freecadcmd``, başsız) ile ölçülür. FreeCAD
     yoksa AYNI yöntem build123d/OCP ile uygulanır (``_occ_olcum``) — atlama
     yerine ölçüm: CI ``step-export`` işinin atlama bütçesi SIFIRDIR ve
     FreeCAD orada kurulu değildir. Hangi okuyucunun ölçtüğü kayıtta
     (``okuyucu``) taşınır. FreeCAD ile build123d aynı OCC çekirdeğidir
     (CAD kontrolü B9); bağımsızlık STL (trimesh) ayaklarından gelir.
   * STL ayakları ``trimesh`` ile her ortamda koşar.
   * DXF ayağı ``ezdxf`` ile.

   Kalemler: H2 lüle eti (yayımlanan ``nozzle_geometry.wall_thickness``),
   H3 tane segmentleri ve ön yüz konumu (``number_of_segments``,
   ``pre_chamber_length``), H8 enjektör plakasının eksenel yeri.

2. **İmalat emniyet kapısı (H5, karar §28-21 (i))** — dalları: SF < 1, SF
   eksik, sayısal değil, model geçerlilik sınırı dışında, SF çizilen cidara
   ait değil, cidar SF'si kurulamıyor; SF ≥ 1'de geçiş. Uç düzeyinde: örnek
   hibrit kapıya takılır (BEKLENEN — kök neden yapı SF kulvarında), katı ve
   sıvı örnek geçer. STL paketi ve çizim PDF'i de aynı kapıdan geçer (14 Eki
   imalat kapısı tutarlılığı; eski 'STL önizleme yolu kapı dışında' beyanı
   kaldırıldı).
"""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from tests.test_example_projects import (
    ENDPOINTS, HEADERS, NAMES, calculate_payload, load_example_doc)

# ---------------------------------------------------------------------------
# TOLERANS TABLOSU — ölçümden ÖNCE yazıldı (kural: sonuca göre değişmez)
# ---------------------------------------------------------------------------
#: Anahtar -> (değer, gerekçe).
TOLERANS = {
    # STEP katısı B-rep'tir: konum ve kalınlıklar yanıtın kayan noktalı
    # sayılarından birebir kurulur. FreeCAD sınır kutusu/kesit ölçümü
    # mikron altı oynar; 10 µm imalat çözünürlüğünün altındadır.
    'step_mm': (0.01, 'STEP B-rep konum/kalınlık; 10 µm'),
    # STL köşeleri float32 yazılır: 1 m mertebesinde ~6e-5 mm; profil
    # köşeleri eksenel konumda TAM, yarıçapta 32 kesitlik çokgenin köşesi.
    'stl_mm': (0.01, 'STL float32 köşe konumu; 10 µm'),
    # STL 32 kesitlik revolve'dur: iç çokgen alanı açığı
    # 1 - (32 / 2π)·sin(2π / 32) = %0,641. Aynı parçanın STEP ve STL hacmi
    # bu açık + %0,36 pay içinde eşit sayılır. CAD kontrolündeki hata
    # 2,53x (%153) idi.
    'hacim_bagil': (0.010, '32 kesitli revolve açığı %0,641 + pay'),
}


def _tol(ad):
    return TOLERANS[ad][0]


# ---------------------------------------------------------------------------
# Fikstürler — örnek hibrit, ÜRÜN yolundan (/calculate), CAD kontrolüyle aynı
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('projeler')))
    os.environ.setdefault('BROWSER', 'echo')
    from hrma.app import app
    return app.test_client()


def _sessiz(fn, *a, **k):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def hibrit_md(client):
    """Arayüzün dışa aktarıma gönderdiği gövde: ``currentResults.motor``."""
    doc = load_example_doc('hybrid')
    r = _sessiz(client.post, ENDPOINTS['hybrid'],
                json=calculate_payload('hybrid', doc['inputs']['fields']),
                headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    body = r.get_json()
    md = dict(body['motor'])
    md['motor_name'] = 'V3CAD_HIBRIT'
    return md


def _kati_veya_sivi_md(client, tip):
    doc = load_example_doc(tip)
    r = _sessiz(client.post, ENDPOINTS[tip],
                json=calculate_payload(tip, doc['inputs']['fields']),
                headers=HEADERS)
    assert r.status_code == 200
    md = dict(r.get_json()['motor_geometry'])
    md.setdefault('motor_name', NAMES[tip])
    return md


@pytest.fixture(scope='module')
def hibrit_paket(hibrit_md, tmp_path_factory):
    """Aynı gövdeden STEP (üreteç) + STL (üreteç) + DXF — bir kez."""
    pytest.importorskip('build123d')
    pytest.importorskip('trimesh')
    from hrma.export.cad_visualization import MotorCADDesigner
    from hrma.export.drawing_generator import generate_dxf
    from hrma.export.motor_geometry import normalise_export_geometry
    from hrma.export.step_export import generate_step_assembly

    out = tmp_path_factory.mktemp('v3cad_hibrit')
    step = _sessiz(generate_step_assembly, hibrit_md,
                   out_dir=str(out / 'step'), motor_type='hybrid')
    designer = MotorCADDesigner()
    cad = _sessiz(designer.generate_3d_motor_assembly, dict(hibrit_md))
    assert not cad.get('error'), cad.get('error')
    stl = _sessiz(designer.export_stl_files, cad['assembly_meshes'],
                  output_dir=str(out / 'stl'))
    dxf_md, _ = normalise_export_geometry(hibrit_md)
    dxf = _sessiz(generate_dxf, dxf_md, out_path=str(out / 'p.dxf'))
    return {'step': step, 'stl_dir': str(out / 'stl'), 'stl': stl,
            'dxf': dxf, 'dir': str(out)}


# ---------------------------------------------------------------------------
# FreeCAD ölçümü (STEP ayakları) — yoksa ADIYLA atlanır
# ---------------------------------------------------------------------------
_FREECAD_ADAYLARI = (
    os.environ.get('HRMA_FREECADCMD') or '',
    '/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd',
    shutil.which('freecadcmd') or '',
    shutil.which('FreeCADCmd') or '',
)

_FC_BETIK = r'''
import json, math, os
import FreeCAD as App
import Part
V = App.Vector
src = json.load(open(os.environ['V3CAD_GIRDI']))
def radii(s, x):
    try:
        w = s.slice(V(1, 0, 0), x)
    except Exception:
        return None
    # Kesit kenarının ÜSTÜNDEN örnek: B-spline kesitte sınır kutusu kutup
    # zarfıdır ve yarıçapı büyük ölçer (pürüzsüz yüzey turu, 14 Eki).
    rs = sorted(max(math.hypot(p.y, p.z) for p in q.discretize(64))
                for q in w)
    if not rs:
        return None
    return (rs[0] if len(rs) > 1 else 0.0), rs[-1]
out = {}
for ad, yol in src.items():
    shp = Part.read(yol)
    katilar = []
    for s in sorted(shp.Solids, key=lambda q: q.BoundBox.XMin):
        b = s.BoundBox
        r = radii(s, 0.5 * (b.XMin + b.XMax))
        katilar.append({'x_min': b.XMin, 'x_max': b.XMax,
                        'dy': b.YLength, 'volume': s.Volume,
                        'valid': s.isValid(),
                        'r_ic': r[0] if r else None,
                        'r_dis': r[1] if r else None})
    rec = {'solids': katilar, 'volume': sum(k['volume'] for k in katilar)}
    if ad == 'nozzle':
        s = shp.Solids[0]
        b = s.BoundBox
        eps = 1e-3 * b.XLength
        n = 200
        etler = []
        for i in range(n):
            x = b.XMin + eps + i * (b.XLength - 2 * eps) / (n - 1)
            r = radii(s, x)
            if r:
                etler.append(r[1] - r[0])
        rec['wall_min'] = min(etler)
        rec['wall_max'] = max(etler)
    out[ad] = rec
json.dump(out, open(os.environ['V3CAD_CIKTI'], 'w'))
'''


def _freecadcmd():
    # CI benzeri koşum (FreeCAD'siz) yerelde sınanabilsin diye:
    # HRMA_V3CAD_FREECAD_YOK=1 -> OCC yolu.
    if os.environ.get('HRMA_V3CAD_FREECAD_YOK') == '1':
        return None
    for aday in _FREECAD_ADAYLARI:
        if aday and os.path.isfile(aday) and os.access(aday, os.X_OK):
            return aday
    return None


def _occ_olcum(yollar):
    """FreeCAD YOKSA STEP ölçümü: aynı yöntem, build123d'nin OCC katmanıyla.

    FreeCAD de OpenCASCADE'dir (CAD kontrolü B9: STEP okumada ortak-mod
    sınırı); burada FreeCAD'in ``Part.read`` + ``Shape.slice`` adımları
    OCP ile birebir yapılır: dosya okunur, katılar x'e göre sıralanır,
    lüle X'e dik düzlemlerle kesilir ve kesit kenarlarının eksene en uzak
    noktaları iç/dış yarıçapı verir. CI'nın ``step-export`` işinde FreeCAD
    yoktur ve o işin ATLAMA BÜTÇESİ SIFIRDIR (``.github/workflows/tests.yml``);
    atlamak yerine ölçmek bu yüzden seçildi.
    """
    from build123d import import_step
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    def yaricaplar(kati, x):
        kesit = BRepAlgoAPI_Section(kati.wrapped,
                                    gp_Pln(gp_Pnt(x, 0, 0), gp_Dir(1, 0, 0)))
        kesit.Build()
        rs = []
        gez = TopExp_Explorer(kesit.Shape(), TopAbs_EDGE)
        while gez.More():
            kutu = Bnd_Box()
            BRepBndLib.Add_s(gez.Current(), kutu)
            _x0, y0, z0, _x1, y1, z1 = kutu.Get()
            rs.append(max(abs(y0), abs(y1), abs(z0), abs(z1)))
            gez.Next()
        return (min(rs), max(rs)) if len(rs) > 1 else None

    def _gecerli(k):
        # build123d sürümüne göre özellik ya da yöntem
        v = k.is_valid
        return bool(v() if callable(v) else v)

    out = {}
    for ad, yol in yollar.items():
        sekil = import_step(yol)
        katilar = sorted(sekil.solids(), key=lambda q: q.bounding_box().min.X)
        kayit = []
        for k in katilar:
            b = k.bounding_box()
            r = yaricaplar(k, 0.5 * (b.min.X + b.max.X))
            kayit.append({'x_min': b.min.X, 'x_max': b.max.X,
                          'dy': b.size.Y, 'volume': k.volume,
                          'valid': _gecerli(k),
                          'r_ic': r[0] if r else None,
                          'r_dis': r[1] if r else None})
        rec = {'solids': kayit, 'volume': sum(k['volume'] for k in kayit),
               'okuyucu': 'build123d/OCP (FreeCAD yok)'}
        if ad == 'nozzle':
            k = katilar[0]
            b = k.bounding_box()
            eps = 1e-3 * b.size.X
            n = 200
            etler = []
            for i in range(n):
                x = b.min.X + eps + i * (b.size.X - 2 * eps) / (n - 1)
                r = yaricaplar(k, x)
                if r:
                    etler.append(r[1] - r[0])
            rec['wall_min'] = min(etler)
            rec['wall_max'] = max(etler)
        out[ad] = rec
    return out


def _step_olc(yollar, d):
    """STEP ölçümü: FreeCAD varsa BAĞIMSIZ okuyucu olarak o (``freecadcmd``,
    başsız), yoksa aynı yöntem build123d/OCP ile (``_occ_olcum``).
    ``yollar``: ad -> STEP yolu; ``d``: çalışma dizini."""
    fc = _freecadcmd()
    if fc is None:
        return _occ_olcum(yollar)
    girdi = os.path.join(d, 'fc_girdi.json')
    cikti = os.path.join(d, 'fc_cikti.json')
    betik = os.path.join(d, 'fc_olcum.py')
    with open(girdi, 'w') as f:
        json.dump(yollar, f)
    with open(betik, 'w') as f:
        f.write(_FC_BETIK)
    env = dict(os.environ, V3CAD_GIRDI=girdi, V3CAD_CIKTI=cikti)
    p = subprocess.run([fc, betik], env=env, capture_output=True,
                       timeout=600)
    assert os.path.exists(cikti), (
        'FreeCAD ölçümü çıktı üretmedi: '
        + p.stdout.decode(errors='replace')[-800:]
        + p.stderr.decode(errors='replace')[-800:])
    olcum = json.load(open(cikti))
    for rec in olcum.values():
        rec['okuyucu'] = 'FreeCAD ' + fc
    return olcum


@pytest.fixture(scope='module')
def step_olcum(hibrit_paket):
    """Hibrit paketin STEP ölçümü (``_step_olc``)."""
    return _step_olc({k: v for k, v in hibrit_paket['step'].items()
                      if k != 'assembly'}, hibrit_paket['dir'])


def _stl(hibrit_paket, ad):
    trimesh = pytest.importorskip('trimesh')
    return trimesh.load(os.path.join(hibrit_paket['stl_dir'], ad + '.stl'))


def _step_adi(path):
    """STEP dosyasındaki ilk PRODUCT adı (boşluklar sıkıştırılmış)."""
    compact = ''.join(open(path, encoding='utf-8', errors='ignore')
                      .read().split())
    adlar = re.findall(r"PRODUCT\('([^']*)'", compact)
    return adlar[0] if adlar else ''


def _yayimlanan(md):
    """İddia tarafı: yanıtın kendi alanları (mm).

    Segment sayısı (ana model çevirisi, 14 Eki; dört koşul): hibrit kulvarı
    K-8'de (c3d1df8b) uydurma ``grain_design.number_of_segments``'i söktü
    ('segmentation: not_modelled'). Çözücü sayıyı yayımlamıyorsa kayıtlı
    kural (cad_visualization tane yığını, 'UYDURMA YOK') taneyi TEK PARÇA
    çizer ve künyede söyler -> beklenen 1. Yayımlıyorsa sayı aynen beklenir.
    """
    gd = md['grain_design']
    segment_yayimlandi = 'number_of_segments' in gd
    return {
        'lule_eti': float(md['nozzle_geometry']['wall_thickness']),
        'segment': (int(gd['number_of_segments']) if segment_yayimlandi
                    else 1),
        'segment_yayimlandi': segment_yayimlandi,
        'tane_boyu': float(gd['grain_length_mm']),
        'on_oda': float(md['pre_chamber_length']) * 1000.0,
        'art_oda': float(md['post_chamber_length']) * 1000.0,
        'kamara': float(md['chamber_length']) * 1000.0,
        'plaka': float(md['injector_design']['plate_thickness_mm']),
    }


# ===========================================================================
# 1) İddia ⟷ CAD kapısı — H2 lüle eti
# ===========================================================================
class TestH2LuleEti:
    def test_step_lulesi_yayimlanan_eti_cizer(self, hibrit_md, step_olcum):
        y = _yayimlanan(hibrit_md)
        noz = step_olcum['nozzle']
        assert noz['wall_min'] == pytest.approx(y['lule_eti'],
                                                abs=_tol('step_mm'))
        assert noz['wall_max'] == pytest.approx(y['lule_eti'],
                                                abs=_tol('step_mm'))

    def test_stl_lulesi_yayimlanan_eti_cizer(self, hibrit_md, hibrit_paket):
        """STL: dış yarıçap (giriş kesiti, en geniş) − iç kontur girişi."""
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        from hrma.export.motor_geometry import normalise_export_geometry
        md, _ = normalise_export_geometry(hibrit_md)
        pts, _meta = sample_nozzle_inner_contour(md)
        r_giris = max(r for _z, r in pts)
        mesh = _stl(hibrit_paket, 'nozzle')
        dis = float(mesh.extents[1]) / 2.0
        assert dis - r_giris == pytest.approx(_yayimlanan(hibrit_md)
                                              ['lule_eti'],
                                              abs=_tol('stl_mm'))

    def test_ayni_paketteki_iki_lule_hacmi_esit(self, hibrit_paket,
                                                step_olcum):
        v_step = step_olcum['nozzle']['volume']
        v_stl = float(_stl(hibrit_paket, 'nozzle').volume)
        assert abs(v_stl / v_step - 1.0) <= _tol('hacim_bagil'), (
            f'STEP {v_step:.0f} mm³ ⟷ STL {v_stl:.0f} mm³')

    def test_step_kunyesi_gercegi_soyler(self, hibrit_paket):
        ad = _step_adi(hibrit_paket['step']['nozzle'])
        assert 'nozzle_geometry.wall_thicknesspublishedbythisrun' in ad, ad
        assert 'thin_wall_hoop' in ad
        assert 'NOTfromastructuralorthermalanalysis' not in ad, (
            'yayımlanan et çizilirken künye hâlâ "analiz yok" diyor')


# ===========================================================================
# 1) İddia ⟷ CAD kapısı — H3 tane segmentleri ve konumu
# ===========================================================================
class TestH3HibritTane:
    def test_step_segment_sayisi_ve_boyu(self, hibrit_md, step_olcum):
        y = _yayimlanan(hibrit_md)
        katilar = step_olcum['fuel_grain']['solids']
        assert len(katilar) == y['segment']
        boy = y['tane_boyu'] / y['segment']
        for k in katilar:
            assert k['valid']
            assert k['x_max'] - k['x_min'] == pytest.approx(
                boy, abs=_tol('step_mm'))
        for a, b in zip(katilar, katilar[1:]):
            # Çözücü boşluk yayımlamaz; kamara L = ön + tane + art -> bitişik
            assert b['x_min'] - a['x_max'] == pytest.approx(
                0.0, abs=_tol('step_mm'))

    def test_step_on_yuz_cozucunun_konumunda(self, hibrit_md, step_olcum):
        y = _yayimlanan(hibrit_md)
        katilar = step_olcum['fuel_grain']['solids']
        assert katilar[0]['x_min'] == pytest.approx(y['on_oda'],
                                                    abs=_tol('step_mm'))
        # Kapanış: art oda = kamara − son yüz
        assert y['kamara'] - katilar[-1]['x_max'] == pytest.approx(
            y['art_oda'], abs=_tol('step_mm'))

    def test_stl_on_yuz_ve_boy(self, hibrit_md, hibrit_paket):
        y = _yayimlanan(hibrit_md)
        mesh = _stl(hibrit_paket, 'fuel_grain')
        assert float(mesh.bounds[0][0]) == pytest.approx(
            y['on_oda'], abs=_tol('stl_mm'))
        assert float(mesh.extents[0]) == pytest.approx(
            y['tane_boyu'], abs=_tol('stl_mm'))
        # Bitişik segmentler TEK kapalı kabuk: dosya manifold kalır
        assert mesh.is_watertight

    def test_step_ve_stl_tane_hacmi_esit(self, hibrit_paket, step_olcum):
        v_step = step_olcum['fuel_grain']['volume']
        v_stl = float(_stl(hibrit_paket, 'fuel_grain').volume)
        assert abs(v_stl / v_step - 1.0) <= _tol('hacim_bagil')

    def test_dxf_tane_cizgisi_ayni_konumda(self, hibrit_md, hibrit_paket):
        ezdxf = pytest.importorskip('ezdxf')
        y = _yayimlanan(hibrit_md)
        r_port = float(hibrit_md['grain_design']
                       ['port_diameter_initial_mm']) / 2.0
        msp = ezdxf.readfile(hibrit_paket['dxf']).modelspace()
        cizgiler = []
        for e in msp.query('LWPOLYLINE[layer=="OUTLINE"]'):
            pts = [tuple(p) for p in e.get_points('xy')]
            if len(pts) == 2 and abs(abs(pts[0][1]) - r_port) < 1e-6:
                cizgiler.append(pts)
        assert cizgiler, 'DXF tane port çizgisi bulunamadı'
        # ÖH V3 CAD A2 · H7: DXF segmentleri ayrı çizer (n segment -> port
        # çizgisi her yanda n parça; hibrit K-8 sonrası tek parça, n = 1);
        # yığın yine çözücünün ön yüzünden başlar ve tane boyunu kaplar.
        assert len(cizgiler) == 2 * y['segment'], len(cizgiler)
        xs = sorted(x for pts in cizgiler for x, _y in pts)
        assert xs[0] == pytest.approx(y['on_oda'], abs=_tol('step_mm'))
        assert xs[-1] == pytest.approx(y['on_oda'] + y['tane_boyu'],
                                       abs=_tol('step_mm'))
        metin = [e.dxf.text for e in msp if e.dxftype() == 'TEXT'
                 and e.dxf.text.startswith('GRAIN AXIAL POSITION:')]
        assert metin and 'pre_chamber_length' in metin[0]
        assert 'ASSUMED' not in metin[0]

    def test_step_kunyesi_yayimlanan_alanlari_soyler(self, hibrit_md,
                                                     hibrit_paket):
        ad = _step_adi(hibrit_paket['step']['fuel_grain'])
        y = _yayimlanan(hibrit_md)
        if y['segment_yayimlandi']:
            assert f"number_of_segments={y['segment']}published" in ad, ad
            assert 'doesnotpublishgrain_design.number_of_segments' not in ad
        else:
            # Hibrit K-8: sayı yayımlanmıyor -> künye bunu SÖYLER, sayı
            # uydurmaz, tek parça çizer.
            assert 'doesnotpublishgrain_design.number_of_segments' in ad, ad
            assert 'number_of_segments=' not in ad
            assert 'singlepiece' in ad
        assert 'pre_chamber_lengthpublishedbythisrun' in ad
        assert 'NOsolverpublishestheaxialposition' not in ad


# ===========================================================================
# 1) İddia ⟷ CAD kapısı — H8 enjektör plakası
# ===========================================================================
class TestH8EnjektorKonumu:
    def test_step_plakasi_kapak_ic_yuzunde(self, hibrit_md, step_olcum):
        y = _yayimlanan(hibrit_md)
        k = step_olcum['injector']['solids'][0]
        assert k['x_min'] == pytest.approx(0.0, abs=_tol('step_mm'))
        assert k['x_max'] == pytest.approx(y['plaka'], abs=_tol('step_mm'))

    def test_stl_plakasi_ayni_yerde(self, hibrit_md, hibrit_paket):
        y = _yayimlanan(hibrit_md)
        mesh = _stl(hibrit_paket, 'injector')
        assert float(mesh.bounds[0][0]) == pytest.approx(0.0,
                                                         abs=_tol('stl_mm'))
        assert float(mesh.bounds[1][0]) == pytest.approx(y['plaka'],
                                                         abs=_tol('stl_mm'))

    def test_step_ile_stl_ayni_eksenel_aralik(self, hibrit_paket, step_olcum):
        k = step_olcum['injector']['solids'][0]
        mesh = _stl(hibrit_paket, 'injector')
        assert float(mesh.bounds[0][0]) == pytest.approx(k['x_min'],
                                                         abs=_tol('stl_mm'))
        assert float(mesh.bounds[1][0]) == pytest.approx(k['x_max'],
                                                         abs=_tol('stl_mm'))

    def test_eski_uretec_ofseti_yok(self):
        from hrma.export import step_export
        assert not hasattr(step_export, 'INJECTOR_PLATE_AXIAL_OFFSET_MM')


# ===========================================================================
# 2) İmalat emniyet kapısı — dallar (birim düzeyi, CAD üretmeden)
# ===========================================================================
def _govde(**chamber):
    """Kapıyı geçen asgari gövde; dallar tek alan değiştirerek kurulur."""
    blok = {'wall_thickness_used_mm': 5.0, 'recommended_thickness': 5.0,
            'design_mode': 'verify', 'safety_factor_is_tautological': False,
            'safety_factor_total': 2.0}
    blok.update(chamber)
    return {'chamber_diameter': 0.1, 'chamber_length': 0.3,
            'throat_diameter': 0.03, 'exit_diameter': 0.06,
            'structural_analysis': {'chamber_analysis': blok}}


def _kapi(md):
    from hrma.export.cad_visualization import manufacturing_safety_refusals
    return manufacturing_safety_refusals(md)


def _nedenler(refusals, part='chamber'):
    return sorted(r['reason'] for r in refusals if r['part'] == part)


class TestH5KapiDallari:
    def test_sf_bir_ve_ustu_gecer(self):
        assert _kapi(_govde()) == []
        assert _kapi(_govde(safety_factor_total=1.0)) == [], (
            'SF = 1,0 sınırda geçmeli (kural: SF ≥ 1)')

    def test_sf_birin_altinda(self):
        r = _kapi(_govde(safety_factor_total=0.99))
        assert _nedenler(r) == ['sf_below_one']
        assert r[0]['safety_factor'] == pytest.approx(0.99)
        assert r[0]['drawn_wall_mm'] == pytest.approx(5.0)

    def test_sf_eksik(self):
        md = _govde()
        del md['structural_analysis']['chamber_analysis'][
            'safety_factor_total']
        assert _nedenler(_kapi(md)) == ['sf_missing']

    @pytest.mark.parametrize('deger', ['2.0', float('nan'), float('inf'),
                                       True, [2.0]])
    def test_sf_sayisal_degil(self, deger):
        assert _nedenler(_kapi(_govde(safety_factor_total=deger))) == [
            'sf_not_numeric']

    def test_model_gecerlilik_siniri_disinda(self):
        md = _govde()
        md['structural_analysis']['thermal_analysis'] = {
            'strength_derating': {'exceeds_melting_point': True}}
        r = _kapi(md)
        assert _nedenler(r) == ['outside_model_validity']
        assert r[0]['validity_field'] == (
            'structural_analysis.thermal_analysis.strength_derating'
            '.exceeds_melting_point')
        md['structural_analysis']['thermal_analysis']['strength_derating'][
            'exceeds_melting_point'] = False
        assert _kapi(md) == []
        # numpy mantıksal değeri de bayraktır; 1 / "true" kaçak biçim değildir
        import numpy as np
        sd = md['structural_analysis']['thermal_analysis']['strength_derating']
        sd['exceeds_melting_point'] = np.bool_(True)
        assert _nedenler(_kapi(md)) == ['outside_model_validity']
        for kacak in (1, 'true'):
            sd['exceeds_melting_point'] = kacak
            assert _kapi(md) == [], kacak

    def test_sf_cizilen_cidara_ait_degil(self):
        # Boyutlandırma kipinde ÇİZİLEN önerilen 6 mm; gerilmeler 5 mm'de.
        r = _kapi(_govde(design_mode='size', recommended_thickness=6.0))
        assert _nedenler(r) == ['sf_wall_mismatch']
        assert r[0]['drawn_wall_mm'] == pytest.approx(6.0)
        assert r[0]['sf_wall_mm'] == pytest.approx(5.0)

    def test_sf_cidari_kurulamiyor(self):
        md = _govde()
        del md['structural_analysis']['chamber_analysis'][
            'wall_thickness_used_mm']
        assert _nedenler(_kapi(md)) == ['sf_wall_not_established']

    def test_cidar_hic_cozulmuyorsa_kapi_konusmaz(self):
        """STEP o gövdeyi zaten adıyla reddeder; kapı ikinci ret yazmaz."""
        md = _govde()
        del md['structural_analysis']
        assert _kapi(md) == []

    def test_lule_sf_birin_altinda(self):
        md = _govde()
        md['nozzle_geometry'] = {'wall_thickness': 4.0,
                                 'wall_safety_factor': 0.7}
        assert _nedenler(_kapi(md), 'nozzle') == ['sf_below_one']

    def test_lule_sf_var_et_yok(self):
        md = _govde()
        md['nozzle_geometry'] = {'wall_safety_factor': 2.0}
        assert _nedenler(_kapi(md), 'nozzle') == ['sf_wall_not_established']

    def test_yapisal_lule_analizi_baska_cidarda(self):
        md = _govde()
        md['nozzle_geometry'] = {'wall_thickness': 4.0,
                                 'wall_safety_factor': 4.0}
        md['structural_analysis']['nozzle_analysis'] = {
            'safety_factor': 4.0, 'throat_thickness_used_mm': 1.2}
        r = [x for x in _kapi(md) if x['part'] == 'nozzle']
        assert [x['reason'] for x in r] == ['sf_wall_mismatch']
        assert r[0]['safety_factor_field'] == (
            'structural_analysis.nozzle_analysis.safety_factor')
        md['structural_analysis']['nozzle_analysis'][
            'throat_thickness_used_mm'] = 4.0
        assert [x for x in _kapi(md) if x['part'] == 'nozzle'] == []

    def test_tank_dallari(self):
        from hrma.export.cad_visualization import (
            tank_manufacturing_safety_refusals as tank)

        def t(sf=2.5, cizilen=3.0, pv=3.0):
            return {'dimensions': {'wall_thickness': cizilen},
                    'structural': {'safety_factor': sf},
                    'pressure_vessel': {'wall_thickness_used_mm': pv}}
        assert tank({'fuel_tank': t(), 'oxidizer_tank': t()}) == []
        r = tank({'fuel_tank': t(sf=0.8), 'oxidizer_tank': t(pv=2.0)})
        assert sorted((x['part'], x['reason']) for x in r) == [
            ('fuel_tank', 'sf_below_one'),
            ('oxidizer_tank', 'sf_wall_mismatch')]
        # SF yayımlamayan tank kapının dışındadır (karar: "yayımlıyorsa")
        bos = t()
        del bos['structural']['safety_factor']
        assert tank({'fuel_tank': bos}) == []
        # Basınç kabı bloğu yoksa SF ile çizilen cidar aynı tank kaydının
        # sözleşmesidir (dimensions.wall_thickness o SF ile boyutlanır)
        pvsiz = t()
        del pvsiz['pressure_vessel']
        assert tank({'fuel_tank': pvsiz}) == []
        pvsiz['structural']['safety_factor'] = 0.9
        assert [x['reason'] for x in tank({'fuel_tank': pvsiz})] == [
            'sf_below_one']

    def test_kapi_kunyenin_bastigi_sayiya_hukmeder(self, hibrit_md):
        """Kapı ile STEP künyesi aynı sayıyı okur (tek kaynak)."""
        from hrma.export.cad_visualization import _chamber_wall_design
        from hrma.export.motor_geometry import normalise_export_geometry
        md, _ = normalise_export_geometry(hibrit_md)
        sf_kunye = _chamber_wall_design(md)['safety_factor']
        r = [x for x in _kapi(hibrit_md)
             if x['part'] == 'chamber' and x['reason'] == 'sf_below_one']
        assert r and r[0]['safety_factor'] == pytest.approx(
            round(sf_kunye, 4))


# ===========================================================================
# 2) İmalat emniyet kapısı — uçlar
# ===========================================================================
def _post(client, uc, md, motor_type='hybrid'):
    return _sessiz(client.post, uc, json={'motor_data': md,
                                         'motor_type': motor_type},
                   headers=HEADERS)


class TestH5Uclar:
    @pytest.mark.parametrize('uc', ['/api/export-step', '/api/export-dxf',
                                    '/api/export-complete-zip'])
    def test_ornek_hibrit_imalat_dosyasi_almaz(self, client, hibrit_md, uc):
        r = _post(client, uc, hibrit_md)
        assert r.status_code == 422, r.status_code
        g = r.get_json()
        assert g['status'] == 'manufacturing_safety_gate_closed'
        assert g['message_key'] == 'out.export.sfGate.refused'
        kamara = {x['reason']: x for x in g['refusals']
                  if x['part'] == 'chamber'}
        assert 'sf_below_one' in kamara
        assert kamara['sf_below_one']['safety_factor'] < 1.0
        assert kamara['sf_below_one']['drawn_wall_mm'] == pytest.approx(
            hibrit_md['structural_analysis']['chamber_analysis']
            ['wall_thickness_used_mm'], abs=1e-3)
        assert 'outside_model_validity' in kamara
        assert all(x['reason_key'].startswith('out.export.sfGate.reason.')
                   for x in g['refusals'])
        assert {f['field'] for f in g['invalid_fields']}

    def test_sf_bir_ustunde_ayni_govde_gecer(self, client, hibrit_md):
        """Kapı GENELDİR: aynı hibrit gövde SF ≥ 1 ve geçerlilik içinde
        yayımlasaydı STEP inerdi (test girdisi; ürün sayısı değil)."""
        pytest.importorskip('build123d')
        md = json.loads(json.dumps(hibrit_md))
        ca = md['structural_analysis']['chamber_analysis']
        for k in ('safety_factor_total', 'hoop_safety_factor'):
            ca[k] = 1.5
        md['structural_analysis']['thermal_analysis']['strength_derating'][
            'exceeds_melting_point'] = False
        md['structural_analysis']['nozzle_analysis'][
            'throat_thickness_used_mm'] = md['nozzle_geometry'][
                'wall_thickness']
        r = _post(client, '/api/export-step', md)
        assert r.status_code == 200, r.get_data(as_text=True)[:600]
        assert r.headers['content-type'].startswith('application/zip')

    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    def test_ornek_kati_ve_sivi_gecer(self, client, tip):
        pytest.importorskip('build123d')
        md = _kati_veya_sivi_md(client, tip)
        assert _kapi(md) == []
        r = _post(client, '/api/export-step', md, motor_type=tip)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]

    def test_kapiya_takilan_istek_agir_cekirdegi_yuklemez(self, hibrit_md,
                                                         tmp_path):
        """H3-B14 ilkesi kapı için de geçerli: SF reddi build123d/OCC
        yığınını (+433 MB) yüklemeden verilir. Taze süreçte ölçülür."""
        govde = tmp_path / 'g.json'
        govde.write_text(json.dumps({'motor_data': hibrit_md,
                                     'motor_type': 'hybrid'}),
                         encoding='utf-8')
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        betik = (
            'import contextlib, io, json, os, sys\n'
            f'sys.path.insert(0, {kok!r})\n'
            'from hrma.app import app\n'
            f'g = json.load(open({str(govde)!r}))\n'
            'with contextlib.redirect_stdout(io.StringIO()):\n'
            '    r = app.test_client().post("/api/export-step", json=g,\n'
            '        headers={"Host": "127.0.0.1:8080"})\n'
            'print(json.dumps([r.status_code,\n'
            '    "hrma.export.step_export" in sys.modules,\n'
            '    "build123d" in sys.modules]))\n')
        env = dict(os.environ,
                   HRMA_PROJECTS_DIR=str(tmp_path / 'p'), BROWSER='echo')
        p = subprocess.run([sys.executable, '-c', betik], cwd=kok, env=env,
                           capture_output=True, text=True, timeout=300)
        satir = [s for s in p.stdout.splitlines() if s.startswith('[')]
        assert satir, p.stdout[-400:] + p.stderr[-400:]
        durum, step_yuklu, occ_yuklu = json.loads(satir[-1])
        assert durum == 422
        assert not step_yuklu and not occ_yuklu, (
            'imalat kapısı reddi build123d yığınını yükledi (H3-B14)')

    def test_stl_paketi_de_kapidan_gecer(self, client, hibrit_md):
        """14 Eki (ana model kararı; karar §28-21 (i) gerekçesi: etiket
        dosyayla dolaşmaz; KAB devir 8): STL eklemeli imalatta doğrudan
        kullanılır, 'önizleme' istisnası kaldırıldı. Eski beklenti (200)
        o istisnadan türemişti."""
        r = _post(client, '/api/export-stl-zip', hibrit_md)
        assert r.status_code == 422
        assert r.get_json()['refusals'] == _kapi(hibrit_md)


# ===========================================================================
# 2) i18n — anahtarlar EN = TR, yer tutucular kayıt alanlarından
# ===========================================================================
def _sozluk(dil):
    from tests.test_i18n_common import dict_block
    return dict_block(dil)


def test_kapi_anahtarlari_en_tr_sozlukte():
    from hrma.export import cad_visualization as cv
    anahtarlar = ([cv.SF_GATE_MESSAGE_KEY]
                  + list(cv.SF_GATE_REASON_KEYS.values())
                  + list(cv.SF_GATE_PART_KEYS.values()))
    en, tr = _sozluk('en'), _sozluk('tr')
    for k in anahtarlar:
        assert k in en, f'EN sözlükte yok: {k}'
        assert k in tr, f'TR sözlükte yok: {k}'
        yt = set(re.findall(r'\{(\w+)\}', en[k]))
        assert yt == set(re.findall(r'\{(\w+)\}', tr[k])), k
        assert en[k] != tr[k], f'{k} Türkçeye çevrilmemiş'


def test_gerekce_yer_tutuculari_kayitta_var(hibrit_md):
    """Her gerekçe metninin yer tutucusu ret kaydının alanıdır (ya da
    ``part``); arayüz eksik parametreyi ``{ad}`` olarak gösterirdi."""
    from hrma.export.cad_visualization import SF_GATE_REASON_KEYS
    en = _sozluk('en')
    ornek = {
        'sf_below_one': _kapi(_govde(safety_factor_total=0.5))[0],
        'sf_missing': _kapi(_govde(safety_factor_total=None))[0],
        'sf_not_numeric': _kapi(_govde(safety_factor_total='x'))[0],
        'sf_wall_mismatch': _kapi(_govde(design_mode='size',
                                         recommended_thickness=6.0))[0],
    }
    md = _govde()
    md['structural_analysis']['thermal_analysis'] = {
        'strength_derating': {'exceeds_melting_point': True}}
    ornek['outside_model_validity'] = _kapi(md)[0]
    md = _govde()
    del md['structural_analysis']['chamber_analysis']['wall_thickness_used_mm']
    ornek['sf_wall_not_established'] = _kapi(md)[0]
    assert set(ornek) == set(SF_GATE_REASON_KEYS)
    for neden, kayit in ornek.items():
        yt = set(re.findall(r'\{(\w+)\}', en[SF_GATE_REASON_KEYS[neden]]))
        eksik = yt - set(kayit) - {'part'}
        assert not eksik, f'{neden}: kayıtta olmayan yer tutucu {eksik}'


def test_ret_govdesi_arayuzde_turkce_basilir(client, hibrit_md, tmp_path):
    """reject_body.js gövdeyi sözlükten basar (node yoksa adıyla atlanır)."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: ön yüz çözücüsü bu ortamda koşturulamaz')
    g = _post(client, '/api/export-step', hibrit_md).get_json()
    govde = tmp_path / 'g.json'
    govde.write_text(json.dumps(g), encoding='utf-8')
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    betik = tmp_path / 'r.js'
    betik.write_text(r'''
const fs = require('fs'); const path = require('path');
const R = process.argv[2];
global.window = global;
global.localStorage = { getItem: () => null, setItem: () => {} };
global.document = { documentElement: { setAttribute(){}, lang: 'en' },
  addEventListener(){}, querySelectorAll: () => [], readyState: 'complete' };
global.navigator = { language: 'en' };
for (const f of ['i18n.js', 'i18n_common.js', 'reject_body.js']) {
  eval(fs.readFileSync(path.join(R, 'hrma/static/js', f), 'utf8'));
}
const g = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
window.I18N.setLang('tr');
process.stdout.write(window.HRMAReject.metni(g, 422));
''', encoding='utf-8')
    p = subprocess.run([node, str(betik), kok, str(govde)],
                       capture_output=True, timeout=60)
    metin = p.stdout.decode('utf-8')
    assert 'İmalat dışa aktarımı emniyet kapısında reddedildi' in metin, (
        metin + p.stderr.decode(errors='replace')[-400:])
    assert 'Kamara:' in metin and '1,0 değerinin altında' in metin
    assert 'refused' not in metin, 'TR kipinde İngilizce cümle kaldı'


# ###########################################################################
# BÖLÜM A2 — katı, tank, montaj (ÖH V3 CAD A2, 12 Eki 2026)
# ###########################################################################
#
# Kalemler (7 Eki CAD kontrolü): H1 yıldız/finocyl tane (ret kapısı), H7
# BATES segmentleri (STEP = STL = DXF), H6 katı astar (ölçüm + beyan), H4/H9
# tank (düz uçlu silindir; iç hacim = iddia; STL kabuk, ekseni STEP ile
# aynı), U4 montaj boyu uzlaştırması, U5 DXF kapak + ölçü varlıkları, D-A2-4
# eksen künyesi.
#
# TOLERANS EKİ — ölçümden ÖNCE yazıldı (sonuca göre değişmez):
TOLERANS.update({
    # 7 Eki CAD kontrolünün kütle/hacim UYUMLU eşiği (``06_iddia_karsilastir``
    # beyanı: |Δ| ≤ %3). Kütle = CAD hacmi x yanıtın KENDİ yoğunluğu.
    'kutle_bagil': (0.03, 'CAD kontrolü kütle UYUMLU eşiği %3'),
    # Tank boşluğu B-rep'tir ve yayımlanan hacimle aynı D ve L'den kurulur
    # (π·D²·L/4); ölçüm zarf silindiri eksi kabuk hacmidir. Okuyucunun hacim
    # tümlevi ~1e-9 bağıl; eşik imalat anlamında "eşit".
    'tank_hacim_bagil': (1e-6, 'B-rep boşluk ⟷ π·D²·L/4'),
    # Tank STL'si TANK_MESH_RESOLUTION = 30 kesitlik revolve'dur: iç çokgen
    # alan açığı 1 - (30 / 2π)·sin(2π / 30) = %0,729 (+ pay).
    'tank_stl_hacim_bagil': (0.010, '30 kesitli revolve açığı %0,729 + pay'),
})


def _kati_tam(client, alanlar=None):
    """Örnek katı, ÜRÜN yolundan (/calculate_solid) — tam yanıt."""
    doc = load_example_doc('solid')
    f = dict(doc['inputs']['fields'])
    f.update(alanlar or {})
    r = _sessiz(client.post, ENDPOINTS['solid'],
                json=calculate_payload('solid', f), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def kati_tam(client):
    return _kati_tam(client)


@pytest.fixture(scope='module')
def kati_md(kati_tam):
    """Arayüzün dışa aktarıma gönderdiği gövde: ``motor_geometry``."""
    md = dict(kati_tam['motor_geometry'])
    md.setdefault('motor_name', NAMES['solid'])
    return md


@pytest.fixture(scope='module')
def yildiz_tam(client):
    return _kati_tam(client, {'grain_type': 'star'})


@pytest.fixture(scope='module')
def kati_paket(kati_md, tmp_path_factory):
    """AYNI katı gövdeden STEP + STL + DXF (CAD kontrolünün yolu)."""
    pytest.importorskip('build123d')
    pytest.importorskip('trimesh')
    pytest.importorskip('ezdxf')
    from hrma.app import _declare_drawing_units
    from hrma.export.cad_visualization import MotorCADDesigner
    from hrma.export.drawing_generator import generate_dxf
    from hrma.export.step_export import generate_step_assembly

    out = tmp_path_factory.mktemp('v3cad_kati')
    step = _sessiz(generate_step_assembly, kati_md,
                   out_dir=str(out / 'step'), motor_type='solid')
    designer = MotorCADDesigner()
    cad = _sessiz(designer.generate_3d_motor_assembly, dict(kati_md))
    assert not cad.get('error'), cad.get('error')
    meshes = [(n, m) for n, m in cad['assembly_meshes'] if n != 'Injector']
    stl = _sessiz(designer.export_stl_files, meshes,
                  output_dir=str(out / 'stl'))
    dxf = _sessiz(generate_dxf, _declare_drawing_units(kati_md),
                  out_path=str(out / 'k.dxf'))
    olcum = _step_olc({k: v for k, v in step.items() if k != 'assembly'},
                      str(out))
    return {'step': step, 'stl_dir': str(out / 'stl'), 'stl': stl,
            'dxf': dxf, 'olcum': olcum, 'dir': str(out)}


def _stl_govdeleri_x(yol):
    """STL dosyasının ayrık gövdeleri — (x_min, x_max) sıralı (paket +X)."""
    trimesh = pytest.importorskip('trimesh')
    m = trimesh.load(yol)
    parcalar = m.split(only_watertight=False)
    return sorted((float(p.bounds[0][0]), float(p.bounds[1][0]))
                  for p in parcalar), m


def _dxf_tane_parcalari(yol, port_r):
    """DXF'teki tane port çizgileri (OUTLINE, y = +r_port) -> x aralıkları."""
    ezdxf = pytest.importorskip('ezdxf')
    doc = ezdxf.readfile(yol)
    araliklar = []
    for e in doc.modelspace():
        if e.dxftype() != 'LWPOLYLINE' or e.dxf.layer != 'OUTLINE':
            continue
        pts = list(e.get_points('xy'))
        if (len(pts) == 2 and abs(pts[0][1] - port_r) < 1e-6
                and abs(pts[1][1] - port_r) < 1e-6):
            araliklar.append((min(pts[0][0], pts[1][0]),
                              max(pts[0][0], pts[1][0])))
    return sorted(araliklar), doc


# ===========================================================================
# 3) H7 — BATES segmentleri: STEP = STL = DXF (ve iddia)
# ===========================================================================
class TestH7BatesUcBicim:
    def test_segment_sayisi_ve_araliklari_uc_bicimde_ayni(self, kati_md,
                                                          kati_paket):
        gd = kati_md['grain_design']
        n = int(gd['number_of_segments'])
        seg = float(gd['segment_length_mm'])
        bosluk = float(gd['grain_gap_mm'])
        step = [(k['x_min'], k['x_max'])
                for k in kati_paket['olcum']['fuel_grain']['solids']]
        stl, _m = _stl_govdeleri_x(
            os.path.join(kati_paket['stl_dir'], 'fuel_grain.stl'))
        dxf, _doc = _dxf_tane_parcalari(
            kati_paket['dxf'], float(gd['inner_diameter_mm']) / 2.0)
        assert len(step) == len(stl) == len(dxf) == n, (step, stl, dxf)
        for i in range(n):
            assert step[i][1] - step[i][0] == pytest.approx(
                seg, abs=_tol('step_mm'))
            for ad, diger, tol in (('STL', stl, _tol('stl_mm')),
                                   ('DXF', dxf, _tol('step_mm'))):
                assert diger[i][0] == pytest.approx(step[i][0], abs=tol), (
                    f'{ad} segment {i + 1} ön yüzü {diger[i][0]:.4f}, '
                    f'STEP {step[i][0]:.4f} mm')
                assert diger[i][1] == pytest.approx(step[i][1], abs=tol), (
                    f'{ad} segment {i + 1} arka yüzü {diger[i][1]:.4f}, '
                    f'STEP {step[i][1]:.4f} mm')
        for i in range(n - 1):
            assert step[i + 1][0] - step[i][1] == pytest.approx(
                bosluk, abs=_tol('step_mm'))

    def test_stl_segmentleri_kapali(self, kati_paket):
        _a, m = _stl_govdeleri_x(
            os.path.join(kati_paket['stl_dir'], 'fuel_grain.stl'))
        assert m.is_watertight and m.is_volume

    def test_tane_hacmi_ve_kutlesi_iddiaya_esit(self, kati_tam, kati_md,
                                                kati_paket):
        """İddia ⟷ CAD (katı tane): itici kütlesi = STEP hacmi x yanıtın
        yoğunluğu; tane dış/iç çapı yayımlanan ölçülere eşit."""
        gd = kati_md['grain_design']
        tane = kati_paket['olcum']['fuel_grain']
        rho = float(kati_tam['density'])
        kutle = tane['volume'] * 1e-9 * rho
        assert kutle == pytest.approx(float(kati_md['propellant_mass_total']),
                                      rel=_tol('kutle_bagil'))
        for k in tane['solids']:
            assert 2 * k['r_dis'] == pytest.approx(
                float(gd['outer_diameter_mm']), abs=_tol('step_mm'))
            assert 2 * k['r_ic'] == pytest.approx(
                float(gd['inner_diameter_mm']), abs=_tol('step_mm'))


# ===========================================================================
# 4) H6 — katı astar: ölçülür ve beyan edilir (çizilmez)
# ===========================================================================
class TestH6AstarBeyani:
    def test_radyal_pay_olculur_ve_kunyede_yazar(self, kati_paket):
        olc = kati_paket['olcum']
        bore = olc['chamber']['solids'][0]['r_ic']
        tane = olc['fuel_grain']['solids'][0]['r_dis']
        pay = bore - tane
        kunye = _step_adi(kati_paket['step']['fuel_grain'])
        assert (f'radialclearancebetweenthegrainoutersurfaceandthechamber'
                f'bore{pay:.2f}mm') in kunye.replace('_', ''), kunye[:600]
        assert 'noliner,insulationorloadingclearanceisdrawn' in (
            kunye.replace('_', ''))

    def test_iddia_edilen_astar_sigmiyorsa_soylenir(self, kati_tam):
        from hrma.export.cad_visualization import grain_radial_clearance_note
        md = {'thermal_analysis': kati_tam['thermal_analysis'],
              'design_summary': kati_tam['design_summary']}
        iddia = kati_tam['thermal_analysis']['heat_transfer'][
            'liner_thickness_mm']
        assert iddia > 0
        not_ = grain_radial_clearance_note(md, 37.5, 37.5)
        assert f'claims a {iddia:.2f} mm liner' in not_
        assert 'does NOT fit' in not_ and 'counted in the dry mass' in not_
        assert 'would fit' in grain_radial_clearance_note(md, 40.0, 37.5)


# ===========================================================================
# 5) H1 — tane kesiti kapısı (karar §28-21 (c))
# ===========================================================================
def _kesit(md):
    from hrma.export.cad_visualization import grain_section_refusals
    return grain_section_refusals(md)


def _tane_govdesi(**ek):
    gd = {'grain_length_mm': 360.0, 'outer_diameter_mm': 75.0,
          'inner_diameter_mm': 32.0}
    gd.update(ek)
    return {'grain_design': gd}


class TestH1KesitKapisiDallari:
    @pytest.mark.parametrize('tip', ['bates', 'cylindrical_bore', 'BATES '])
    def test_dairesel_port_gecer(self, tip):
        assert _kesit(_tane_govdesi(grain_type=tip)) == []

    @pytest.mark.parametrize('tip', ['star', 'finocyl', 'wagon_wheel',
                                     'slotted', 'end_burner', 'moon'])
    def test_cizilemeyen_tip_adiyla_reddedilir(self, tip):
        red = _kesit(_tane_govdesi(grain_type=tip))
        assert [r['reason'] for r in red] == ['grain_type_not_drawable']
        assert red[0]['grain_type'] == tip
        assert red[0]['grain_type_field'] == 'grain_design.grain_type'
        assert red[0]['reason_key'].startswith('out.export.grainGate.')

    def test_cok_portlu_hibrit_reddedilir(self):
        md = _tane_govdesi(grain_type='cylindrical_bore')
        md['port_count'] = 4
        red = _kesit(md)
        assert [r['reason'] for r in red] == ['port_count_not_one']
        assert red[0]['port_count'] == 4
        md['port_count'] = 1
        assert _kesit(md) == []

    @pytest.mark.parametrize('ham', ['iki', True, None])
    def test_port_sayisi_sayi_degilse_reddedilir(self, ham):
        md = _tane_govdesi(grain_type='bates')
        md['port_count'] = ham
        assert bool(_kesit(md)) is (ham is not None)

    def test_celisen_tipler_reddedilir(self):
        md = _tane_govdesi(grain_type='bates')
        md['grain_type'] = 'star'
        assert [r['reason'] for r in _kesit(md)] == ['grain_type_conflict']

    def test_tip_yayimlanmamissa_cizilir_ve_kunye_soyler(self):
        from hrma.export.cad_visualization import grain_section_note
        md = _tane_govdesi()
        assert _kesit(md) == []
        assert 'publishes no grain_type' in grain_section_note(md)

    def test_tane_yoksa_kapi_konusmaz(self):
        assert _kesit({'grain_type': 'star'}) == []


class TestH1KesitKapisiUclar:
    UCLAR = ('/api/export-step', '/api/export-stl-zip', '/api/export-dxf',
             '/api/export-drawings-pdf', '/api/export-complete-zip',
             '/api/export-cad', '/api/export-stl')

    @pytest.mark.parametrize('uc', UCLAR)
    def test_yildiz_tane_dosya_almaz(self, client, yildiz_tam, uc):
        md = dict(yildiz_tam['motor_geometry'])
        if uc == '/api/export-stl':
            # Bu ucun sözleşmesi tipi gövdenin İÇİNDE okur
            # (``motor_data.motor_type``, varsayılan 'hybrid').
            md['motor_type'] = 'solid'
        r = _post(client, uc, md, motor_type='solid')
        assert r.status_code == 422, (uc, r.status_code, r.get_data()[:300])
        g = r.get_json()
        assert g['status'] == 'grain_section_not_drawable'
        assert g['message_key'] == 'out.export.grainGate.refused'
        assert [x['grain_type'] for x in g['refusals']] == ['star']
        assert '"star"' in g['message']

    def test_kati_cad_paketi_almaz(self, client, yildiz_tam):
        r = _sessiz(client.post, '/export_solid_motor_cad',
                    json={'results': yildiz_tam}, headers=HEADERS)
        assert r.status_code == 422, r.get_data()[:300]
        assert r.get_json()['status'] == 'grain_section_not_drawable'

    def test_finocyl_de_reddedilir(self, client):
        tam = _kati_tam(client, {'grain_type': 'finocyl'})
        r = _post(client, '/api/export-step', dict(tam['motor_geometry']),
                  motor_type='solid')
        assert r.status_code == 422
        assert r.get_json()['refusals'][0]['grain_type'] == 'finocyl'

    def test_cok_portlu_hibrit_step_almaz(self, client, hibrit_md):
        md = json.loads(json.dumps(hibrit_md))
        md['port_count'] = 4
        r = _post(client, '/api/export-step', md)
        assert r.status_code == 422
        g = r.get_json()
        assert g['status'] == 'grain_section_not_drawable'
        assert g['refusals'][0]['reason'] == 'port_count_not_one'

    def test_bates_ornek_gecer(self, client, kati_md):
        pytest.importorskip('build123d')
        r = _post(client, '/api/export-step', kati_md, motor_type='solid')
        assert r.status_code == 200, r.get_data(as_text=True)[:300]

    def test_ureteclerin_ikinci_kapisi(self, yildiz_tam, tmp_path):
        """Uçtan geçmeyen doğrudan çağrı da tane tipini adıyla reddeder."""
        pytest.importorskip('build123d')
        from hrma.app import _declare_drawing_units
        from hrma.export.drawing_generator import (
            DrawingGeometryError, generate_drawing_pdf, generate_dxf)
        from hrma.export.step_export import (
            StepExportDataError, generate_step_assembly)
        md = dict(yildiz_tam['motor_geometry'])
        with pytest.raises(StepExportDataError, match='"star" grain'):
            _sessiz(generate_step_assembly, md, out_dir=str(tmp_path / 's'),
                    motor_type='solid')
        assert (not (tmp_path / 's').exists()
                or not os.listdir(tmp_path / 's')), (
            'reddedilen STEP yarım yazdı')
        for fn in (generate_dxf, generate_drawing_pdf):
            with pytest.raises(DrawingGeometryError, match='"star" grain'):
                _sessiz(fn, _declare_drawing_units(md),
                        out_path=str(tmp_path / ('x' + fn.__name__)))

    def test_kesit_reddi_agir_cekirdegi_yuklemez(self, yildiz_tam, tmp_path):
        """H3-B14: tane kesiti reddi build123d yığınını yüklemeden verilir."""
        govde = tmp_path / 'g.json'
        govde.write_text(json.dumps({'motor_data': dict(
            yildiz_tam['motor_geometry']), 'motor_type': 'solid'}),
            encoding='utf-8')
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        betik = (
            'import contextlib, io, json, os, sys\n'
            f'sys.path.insert(0, {kok!r})\n'
            'from hrma.app import app\n'
            f'g = json.load(open({str(govde)!r}))\n'
            'with contextlib.redirect_stdout(io.StringIO()):\n'
            '    r = app.test_client().post("/api/export-step", json=g,\n'
            '        headers={"Host": "127.0.0.1:8080"})\n'
            'print(json.dumps([r.status_code, r.get_json()["status"],\n'
            '    "hrma.export.step_export" in sys.modules,\n'
            '    "build123d" in sys.modules]))\n')
        env = dict(os.environ,
                   HRMA_PROJECTS_DIR=str(tmp_path / 'p'), BROWSER='echo')
        p = subprocess.run([sys.executable, '-c', betik], cwd=kok, env=env,
                           capture_output=True, text=True, timeout=300)
        satir = [s for s in p.stdout.splitlines() if s.startswith('[')]
        assert satir, p.stdout[-400:] + p.stderr[-400:]
        durum, kod, step_yuklu, occ_yuklu = json.loads(satir[-1])
        assert (durum, kod) == (422, 'grain_section_not_drawable')
        assert not step_yuklu and not occ_yuklu


def test_kesit_kapisi_anahtarlari_en_tr_ve_kayit_alanlari():
    from hrma.export import cad_visualization as cv
    en, tr = _sozluk('en'), _sozluk('tr')
    anahtarlar = ([cv.GRAIN_GATE_MESSAGE_KEY, cv.GRAIN_GATE_PART_KEY]
                  + list(cv.GRAIN_GATE_REASON_KEYS.values()))
    for k in anahtarlar:
        assert k in en and k in tr, k
        assert (set(re.findall(r'\{(\w+)\}', en[k]))
                == set(re.findall(r'\{(\w+)\}', tr[k]))), k
        assert en[k] != tr[k], f'{k} Türkçeye çevrilmemiş'
    ornek = {
        'grain_type_not_drawable': _kesit(_tane_govdesi(grain_type='star')),
        'grain_type_conflict': _kesit(dict(_tane_govdesi(grain_type='bates'),
                                           grain_type='star')),
        'port_count_not_one': _kesit(dict(_tane_govdesi(), port_count=2)),
    }
    assert set(ornek) == set(cv.GRAIN_GATE_REASON_KEYS)
    for neden, kayitlar in ornek.items():
        yt = set(re.findall(r'\{(\w+)\}',
                            en[cv.GRAIN_GATE_REASON_KEYS[neden]]))
        assert not (yt - set(kayitlar[0]) - {'part'}), neden


def test_kesit_reddi_arayuzde_turkce_basilir(client, yildiz_tam, tmp_path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: ön yüz çözücüsü bu ortamda koşturulamaz')
    g = _post(client, '/api/export-step', dict(yildiz_tam['motor_geometry']),
              motor_type='solid').get_json()
    govde = tmp_path / 'g.json'
    govde.write_text(json.dumps(g), encoding='utf-8')
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    betik = tmp_path / 'r.js'
    betik.write_text(r'''
const fs = require('fs'); const path = require('path');
const R = process.argv[2];
global.window = global;
global.localStorage = { getItem: () => null, setItem: () => {} };
global.document = { documentElement: { setAttribute(){}, lang: 'en' },
  addEventListener(){}, querySelectorAll: () => [], readyState: 'complete' };
global.navigator = { language: 'en' };
for (const f of ['i18n.js', 'i18n_common.js', 'reject_body.js']) {
  eval(fs.readFileSync(path.join(R, 'hrma/static/js', f), 'utf8'));
}
const g = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
window.I18N.setLang('tr');
process.stdout.write(window.HRMAReject.metni(g, 422));
''', encoding='utf-8')
    p = subprocess.run([node, str(betik), kok, str(govde)],
                       capture_output=True, timeout=60)
    metin = p.stdout.decode('utf-8')
    assert 'yakıt bloğu kesiti çizilemiyor' in metin, (
        metin + p.stderr.decode(errors='replace')[-400:])
    assert 'Yakıt bloğu: analiz "star" tipinde' in metin
    assert 'refused' not in metin


# ===========================================================================
# 6) H4 / H9 — tank: düz uçlu silindir, iç hacim = iddia, STL kabuk +X
# ===========================================================================
@pytest.fixture(scope='module')
def tank_paket(client, tmp_path_factory):
    """Sıvı örnek + ``max_burn_duration = 30`` (CAD kontrolünün vakası),
    sayfanın gövdesiyle ``/export_tank_cad``."""
    pytest.importorskip('build123d')
    pytest.importorskip('trimesh')
    import io
    import zipfile
    doc = load_example_doc('liquid')
    f = dict(doc['inputs']['fields'])
    f['max_burn_duration'] = 30
    r = _sessiz(client.post, ENDPOINTS['liquid'],
                json=calculate_payload('liquid', f), headers=HEADERS)
    assert r.status_code == 200
    pt = r.get_json()['propellant_tanks']
    rr = _sessiz(client.post, '/export_tank_cad', json={'tank_data': pt},
                 headers=HEADERS)
    assert rr.status_code == 200, rr.get_data(as_text=True)[:400]
    out = tmp_path_factory.mktemp('v3cad_tank')
    with zipfile.ZipFile(io.BytesIO(rr.data)) as z:
        z.extractall(out)
    olcum = _step_olc({k: str(out / f'{k}.step')
                       for k in ('fuel_tank', 'oxidizer_tank')}, str(out))
    return {'pt': pt, 'dir': str(out), 'olcum': olcum}


TANKLAR = ('fuel_tank', 'oxidizer_tank')


class TestH4Tank:
    @pytest.mark.parametrize('ad', TANKLAR)
    def test_ic_hacim_iddiaya_esit(self, tank_paket, ad):
        """Boşluk = π·(zarf/2)²·zarf boyu − kabuk hacmi (STEP ölçümü)."""
        import math
        k = tank_paket['olcum'][ad]['solids']
        assert len(k) == 1 and k[0]['valid']
        k = k[0]
        R = k['r_dis']
        assert k['dy'] == pytest.approx(2 * R, abs=_tol('step_mm')), (
            'dış zarf silindir değil')
        bosluk = math.pi * R * R * (k['x_max'] - k['x_min']) - k['volume']
        iddia = float(tank_paket['pt'][ad]['dimensions']['volume']) * 1e6
        assert bosluk == pytest.approx(iddia, rel=_tol('tank_hacim_bagil')), (
            f'{ad}: CAD boşluğu {bosluk / 1e6:.4f} L, iddia '
            f'{iddia / 1e6:.4f} L (yarıküre başlık 1,225x idi)')

    @pytest.mark.parametrize('ad', TANKLAR)
    def test_olculer_bosluk_arti_dis_cidar(self, tank_paket, ad):
        d = tank_paket['pt'][ad]['dimensions']
        k = tank_paket['olcum'][ad]['solids'][0]
        t = float(d['wall_thickness'])
        assert 2 * k['r_ic'] == pytest.approx(float(d['diameter']),
                                              abs=_tol('step_mm'))
        assert k['r_dis'] - k['r_ic'] == pytest.approx(t, abs=_tol('step_mm'))
        assert k['x_min'] == pytest.approx(-t, abs=_tol('step_mm'))
        assert k['x_max'] == pytest.approx(float(d['length']) + t,
                                           abs=_tol('step_mm'))

    @pytest.mark.parametrize('ad', TANKLAR)
    def test_kabuk_kutlesi_iddiaya_esit(self, tank_paket, ad):
        """Kabuk kütlesi = STEP hacmi x yanıtın yoğunluğu ⟷ tank kütlesi
        eksi iç yapılar (iddia ince kabuk formülüyle hesaplanır)."""
        tk = tank_paket['pt'][ad]
        rho = float(tk['structural']['density_kg_m3'])
        kabuk = (float(tk['structural']['tank_mass'])
                 - float(tk['internal_structures']['mass_breakdown']
                         ['total_mass']))
        cad = tank_paket['olcum'][ad]['volume'] * 1e-9 * rho
        assert cad == pytest.approx(kabuk, rel=_tol('kutle_bagil'))

    @pytest.mark.parametrize('ad', TANKLAR)
    def test_stl_kabuk_ve_ekseni_step_ile_ayni(self, tank_paket, ad):
        trimesh = pytest.importorskip('trimesh')
        m = trimesh.load(os.path.join(tank_paket['dir'], f'{ad}.stl'))
        k = tank_paket['olcum'][ad]['solids'][0]
        assert m.is_watertight and m.is_volume
        assert len(m.split(only_watertight=False)) == 2, (
            'kabuk = dış yüzey + iç boşluk yüzeyi; içi dolu katı geri gelmiş')
        assert float(m.bounds[0][0]) == pytest.approx(k['x_min'],
                                                      abs=_tol('stl_mm'))
        assert float(m.bounds[1][0]) == pytest.approx(k['x_max'],
                                                      abs=_tol('stl_mm'))
        assert m.volume == pytest.approx(
            tank_paket['olcum'][ad]['volume'],
            rel=_tol('tank_stl_hacim_bagil'))

    @pytest.mark.parametrize('ad', TANKLAR)
    def test_kunye_duz_kapagi_beyan_eder(self, tank_paket, ad):
        kunye = _step_adi(os.path.join(tank_paket['dir'], f'{ad}.step'))
        duz = kunye.replace('_', '')
        assert 'flat-endedcylinder' in duz
        assert 'structuraladequacyofthedrawnflatheadswasNOTcomputed' in duz
        hd = tank_paket['pt'][ad]['pressure_vessel']['head_type']
        assert f"evaluates{hd.replace('_', '')}heads" in duz
        assert 'hemisphericalheads-overall' not in duz

    def test_hacim_celiskisi_reddedilir(self, tmp_path):
        pytest.importorskip('build123d')
        from hrma.export.step_export import (
            StepExportDataError, generate_tank_step)
        td = {k: {'diameter': 300.0, 'length': 800.0, 'wall_thickness': 3.0,
                  'volume': 60.0} for k in TANKLAR}
        with pytest.raises(StepExportDataError, match='two different tanks'):
            generate_tank_step(td, out_dir=str(tmp_path))

    def test_cad_talimati_cizilen_kabugu_anlatir(self, tank_paket):
        g = json.load(open(os.path.join(tank_paket['dir'],
                                        'fuel_tank_geometry.json')))
        k = tank_paket['olcum']['fuel_tank']['solids'][0]
        s1 = g['cad_instructions']['step1_outer_cylinder']
        assert s1['diameter'] == pytest.approx(k['dy'], abs=_tol('step_mm'))
        assert s1['length'] == pytest.approx(k['x_max'] - k['x_min'],
                                             abs=_tol('step_mm'))


# ===========================================================================
# 7) U4 — montaj boyu uzlaştırması gerçekten koşar
# ===========================================================================
class TestU4MontajBoyu:
    def _not(self, kd, uzunluk=100.0, cap=10.0, conv=None):
        b123 = pytest.importorskip('build123d')
        from hrma.export.step_export import _assembly_length_note
        return _assembly_length_note(
            {'design_summary': {'key_dimensions': kd}},
            [b123.Box(uzunluk, 10, 10)], cap=cap, convergent_mm=conv)

    @pytest.mark.parametrize('alan', [
        'overall_length_mm', 'total_motor_length_chamber_nozzle_mm',
        'total_motor_length_mm', 'total_length_mm'])
    def test_her_cozucunun_alani_okunur(self, alan):
        n = self._not({alan: 90.0})
        assert f'the analysis publishes {alan} = 90.00 mm' in n
        assert 'reconciled' in n and 'MISMATCH' not in n

    def test_uyusmazlikta_uyari_basar(self):
        n = self._not({'total_motor_length_chamber_nozzle_mm': 60.0})
        assert 'LENGTH MISMATCH' in n and '+30.00 mm' in n

    def test_yakinsak_koni_farki_adlandirilir(self):
        n = self._not({'overall_length_mm': 70.0}, conv=20.0)
        assert 'convergent cone 20.00 mm' in n and 'reconciled' in n

    def test_alan_yoksa_uzlasmadi_der(self):
        n = self._not({})
        assert 'LENGTH NOT RECONCILED' in n

    @pytest.mark.parametrize('tip,alan', [('solid', 'total_length_mm'),
                                          ('liquid', 'overall_length_mm')])
    def test_paket_ucu_yayimlanan_boyu_tasir(self, client, tip, alan,
                                             tmp_path):
        """Paket uçları ham sonucu da alır: katı/sıvı STEP montajı
        yayımlanan boyla uzlaşır (önce: "LENGTH NOT RECONCILED")."""
        pytest.importorskip('build123d')
        import io
        import zipfile
        doc = load_example_doc(tip)
        r = _sessiz(client.post, ENDPOINTS[tip],
                    json=calculate_payload(tip, doc['inputs']['fields']),
                    headers=HEADERS)
        tam = r.get_json()
        uc = {'solid': '/export_solid_motor_cad',
              'liquid': '/export_liquid_cad'}[tip]
        rr = _sessiz(client.post, uc, json={'results': tam}, headers=HEADERS)
        assert rr.status_code == 200, rr.get_data(as_text=True)[:300]
        with zipfile.ZipFile(io.BytesIO(rr.data)) as z:
            ad = [n for n in z.namelist() if n.endswith('_assembly.step')][0]
            z.extract(ad, tmp_path)
            kunye = _step_adi(str(tmp_path / ad)).replace('_', '')
            if tip == 'solid':
                tn = [n for n in z.namelist()
                      if n.endswith('_fuel_grain.step')][0]
                z.extract(tn, tmp_path)
                tane = _step_adi(str(tmp_path / tn))
        assert f"theanalysispublishes{alan.replace('_', '')}=" in kunye, (
            kunye[-600:])
        assert 'reconciled' in kunye and 'MISMATCH' not in kunye
        if tip == 'solid':
            iddia = tam['thermal_analysis']['heat_transfer'][
                'liner_thickness_mm']
            assert f'claimsa{iddia:.2f}mmliner' in tane.replace('_', '')
            assert 'doesNOTfit' in tane.replace('_', '')

    def test_ornek_hibritte_kontrol_kosar(self, hibrit_paket, hibrit_md):
        kunye = _step_adi(hibrit_paket['step']['assembly']).replace('_', '')
        kd = hibrit_md['design_summary']['key_dimensions']
        assert ('theanalysispublishestotalmotorlengthchambernozzlemm='
                f"{kd['total_motor_length_chamber_nozzle_mm']:.2f}mm"
                ) in kunye.replace('_', ''), kunye[-900:]
        assert 'reconciled' in kunye
        assert 'totalmotorlengthwithcapsmm' in kunye


# ===========================================================================
# 8) U5 + D-A2-4 — DXF kapak, ölçü varlıkları, eksen künyesi
# ===========================================================================
class TestU5Dxf:
    def test_kapak_beyan_edilir_ve_olculer_varlik(self, kati_paket):
        """Kapak kalınlığı STEP'in çizdiği sayıyla yazılır (çizimi devirde);
        kamara boyu, delik çapı ve cidar ilişkisel DIMENSION varlığıdır."""
        ezdxf = pytest.importorskip('ezdxf')
        doc = ezdxf.readfile(kati_paket['dxf'])
        kamara = kati_paket['olcum']['chamber']['solids'][0]
        cap = -kamara['x_min']
        metin = [e.dxf.text for e in doc.modelspace()
                 if e.dxftype() == 'TEXT'
                 and e.dxf.text.startswith('CLOSURE HEAD')]
        assert metin and f'CLOSURE HEAD = {cap:.2f} mm' in metin[0], metin
        olculer = [e.get_measurement() for e in doc.modelspace()
                   if e.dxftype() == 'DIMENSION']
        for beklenen in (kamara['x_max'], 2 * kamara['r_ic'],
                         kamara['r_dis'] - kamara['r_ic']):
            assert any(abs(o - beklenen) < _tol('step_mm') for o in olculer), (
                beklenen, olculer)

    def test_eksen_kunyesi_dogru(self, kati_paket):
        ezdxf = pytest.importorskip('ezdxf')
        doc = ezdxf.readfile(kati_paket['dxf'])
        eksen = [e.dxf.text for e in doc.modelspace()
                 if e.dxftype() == 'TEXT'
                 and e.dxf.text.startswith('AXIS CONVENTION:')]
        assert eksen and 'rotate them' not in eksen[0]
        assert '(STEP and STL)' in eksen[0]
        from hrma.export.drawing_generator import AXIS_CONVENTION_ROW
        assert 'rotate them' not in AXIS_CONVENTION_ROW


# ###########################################################################
# ŞART TURU (13 Eki 2026) — ilk denetimin Ş1 ve Ş2 şartları
# ###########################################################################
#
# Ş1: ``/export_tank_cad`` ve katı/sıvı CAD paket uçlarındaki
# (``_motor_cad_zip_response``) SF kapısı çağrısını hiçbir test korumuyordu:
# denetçinin G6 (tank ucu kapısı silinir) ve G7 (paket ucu kapısı silinir)
# mutasyonları 1 175 düğümde bu kapıya ait hiçbir kırmızı üretmedi. Aşağıdaki
# bekçiler kapıyı UÇ düzeyinde sınar. Örneğin kapıdan geçtiği ön koşul olarak
# ayrıca doğrulanır: 422'yi yalnız testin bozduğu alan verir.
#
# Ş2 (güvenlik, karar §28-33): kapı ret gövdeleri istek metnini HAM
# yansıtıyordu (``'<img src=x onerror=alert(1)>'`` ``refusals[]`` ve
# ``message`` alanlarında etiketiyle; ``reject_body.js`` → ``showError`` →
# innerHTML). Gövdede artık yalnız ``^[a-z0-9_]{1,40}$`` belirteci ya da tür
# adı (+ uzunluk) bulunur.

#: Tanklı sıvı vakası: ``tank_paket`` fikstürünün CAD kontrolü vakası
#: (7 Eki, ``max_burn_duration = 30``); tank bloğu ancak yanma süresi
#: verilince yayımlanır. Aynı literal ``tank_paket``te de duruyor; o satır
#: bu turun izninde değil (yalnız ekleme), devir D-T4-1.
SART_TANK_YANMA_SURESI_S = 30
#: Tank cidar uyuşmazlığı vakasının farkı [mm]. ``WALL_MATCH_TOLERANCE_MM``
#: (1e-6) kayan nokta mertebesidir; 0,01 mm'lik fark eşiğin 0,5 mm'ye
#: gevşetilmesini de yakalar (denetçinin G3 notu).
SART_CIDAR_FARKI_MM = 0.01
#: SF < 1 vakasının emniyet katsayısı (``MANUFACTURING_SF_MIN`` = 1,0'ın
#: altında; test girdisi, ürün sayısı değil).
SART_SF_ALTINDA = 0.8
#: Ş2 sondası (denetçinin sondasıyla aynı) ve gövdede kalabilecek TEK izi:
#: tür adı + uzunluk. Beklenen iz kâhinden (sondanın kendi türü ve boyu)
#: kurulur, ürün sabitinden okunmaz.
SONDA_ETIKET = '<img src=x onerror=alert(1)>'
SONDA_IZI = f'str(len={len(SONDA_ETIKET)})'
SF_GATE = 'manufacturing_safety_gate_closed'
GRAIN_GATE = 'grain_section_not_drawable'


def _kopya(x):
    return json.loads(json.dumps(x))


@pytest.fixture(scope='module')
def sivi_tam_tankli(client):
    """Örnek sıvı + yanma süresi: ham ``/calculate_liquid`` yanıtı (tank
    bloğu ``propellant_tanks`` ve yapısal blok ``chamber_structure`` içinde).
    Ağır dışa aktarım gerektirmez."""
    doc = load_example_doc('liquid')
    f = dict(doc['inputs']['fields'])
    f['max_burn_duration'] = SART_TANK_YANMA_SURESI_S
    r = _sessiz(client.post, ENDPOINTS['liquid'],
                json=calculate_payload('liquid', f), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _uc_reddi(client, uc, govde, status):
    r = _sessiz(client.post, uc, json=govde, headers=HEADERS)
    # İleti BAYT olarak okunur: kapı açılırsa gövde ikili ZIP'tir (metin
    # çözümü iddia yerine UnicodeDecodeError ile kırmızı verirdi).
    assert r.status_code == 422, (uc, r.status_code, r.get_data()[:400])
    g = r.get_json()
    assert g['status'] == status, (uc, g.get('status'), g.get('error'))
    return r, g


class TestS1UcKapilari:
    """Ş1 — SF kapısı UÇ düzeyinde: tank paketi ve katı/sıvı CAD paketi."""

    def test_tank_sf_birin_altinda_paket_almaz(self, client,
                                                sivi_tam_tankli):
        from hrma.export.cad_visualization import (
            tank_manufacturing_safety_refusals)
        pt = _kopya(sivi_tam_tankli['propellant_tanks'])
        assert tank_manufacturing_safety_refusals(pt) == [], (
            'ön koşul: örnek tanklar kapıdan geçer')
        pt['fuel_tank']['structural']['safety_factor'] = SART_SF_ALTINDA
        _r, g = _uc_reddi(client, '/export_tank_cad', {'tank_data': pt},
                          SF_GATE)
        assert [(x['part'], x['reason']) for x in g['refusals']] == [
            ('fuel_tank', 'sf_below_one')]
        assert g['refusals'][0]['safety_factor'] == pytest.approx(
            SART_SF_ALTINDA)
        assert g['message_key'] == 'out.export.sfGate.refused'

    def test_tank_cidar_uyusmazligi_paket_almaz(self, client,
                                                 sivi_tam_tankli):
        pt = _kopya(sivi_tam_tankli['propellant_tanks'])
        ox = pt['oxidizer_tank']
        cizilen = float(ox['dimensions']['wall_thickness'])
        ox['pressure_vessel']['wall_thickness_used_mm'] = (
            cizilen + SART_CIDAR_FARKI_MM)
        _r, g = _uc_reddi(client, '/export_tank_cad', {'tank_data': pt},
                          SF_GATE)
        assert [(x['part'], x['reason']) for x in g['refusals']] == [
            ('oxidizer_tank', 'sf_wall_mismatch')]
        kayit = g['refusals'][0]
        assert kayit['drawn_wall_mm'] == pytest.approx(cizilen)
        assert kayit['sf_wall_mm'] == pytest.approx(
            cizilen + SART_CIDAR_FARKI_MM)

    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    def test_cad_paketi_sf_birin_altinda_almaz(self, client, kati_tam,
                                               sivi_tam_tankli, tip):
        from hrma.export.cad_visualization import (
            manufacturing_safety_refusals)
        from hrma.export.motor_geometry import (
            liquid_results_to_motor_geometry, solid_results_to_motor_geometry)
        tam, cevir, uc, blok = {
            'solid': (kati_tam, solid_results_to_motor_geometry,
                      '/export_solid_motor_cad', 'case_analysis'),
            'liquid': (sivi_tam_tankli, liquid_results_to_motor_geometry,
                       '/export_liquid_cad', 'chamber_structure'),
        }[tip]
        tam = _kopya(tam)
        assert manufacturing_safety_refusals(cevir(tam)) == [], (
            'ön koşul: örnek kapıdan geçer')
        b = tam['structural_analysis'][blok]
        alanlar = [k for k in ('safety_factor', 'hoop_safety_factor')
                   if k in b]
        assert alanlar, sorted(b)
        for k in alanlar:
            b[k] = SART_SF_ALTINDA
        _r, g = _uc_reddi(client, uc, {'results': tam}, SF_GATE)
        kamara = [x for x in g['refusals'] if x['part'] == 'chamber']
        assert [x['reason'] for x in kamara] == ['sf_below_one'], (
            g['refusals'])
        assert kamara[0]['safety_factor'] == pytest.approx(SART_SF_ALTINDA)
        assert kamara[0]['safety_factor_field'].startswith(
            f'structural_analysis.{blok}.')


# Ş2 — sonda: uç x alan. Alan -> (status, neden, kayıttaki yansıyan alan).
S2_UCLAR = ('/api/export-step', '/api/export-dxf', '/export_solid_motor_cad')
S2_ALANLAR = {
    'grain_type': (GRAIN_GATE, 'grain_type_not_drawable', 'grain_type'),
    'port_count': (GRAIN_GATE, 'port_count_not_one', 'port_count'),
    'safety_factor': (SF_GATE, 'sf_not_numeric', 'safety_factor_raw'),
}


def _sonda_govdesi(kati_tam, uc, alan):
    """Örnek katı gövdesi, tek alanına sonda konmuş: paket ucu ham sonucu
    (``results``), öbür uçlar arayüzün gönderdiği ``motor_geometry``yi
    alır."""
    if uc == '/export_solid_motor_cad':
        hedef = _kopya(kati_tam)
        govde = {'results': hedef}
    else:
        hedef = _kopya(kati_tam['motor_geometry'])
        govde = {'motor_data': hedef, 'motor_type': 'solid'}
    if alan == 'safety_factor':
        hedef['structural_analysis']['case_analysis']['safety_factor'] = (
            SONDA_ETIKET)
    else:
        hedef['grain_design'][alan] = SONDA_ETIKET
    return govde


def _etiketsiz(metin, ad):
    assert '<' not in metin and '>' not in metin, (ad, metin[:600])


class TestS2RetGovdesiYansitmaz:
    @pytest.mark.parametrize('alan', sorted(S2_ALANLAR))
    @pytest.mark.parametrize('uc', S2_UCLAR)
    def test_sonda_govdede_etiket_birakmaz(self, client, kati_tam, uc, alan):
        status, neden, kayit_alani = S2_ALANLAR[alan]
        r, g = _uc_reddi(client, uc, _sonda_govdesi(kati_tam, uc, alan),
                         status)
        assert [x['reason'] for x in g['refusals']] == [neden], g['refusals']
        assert g['refusals'][0][kayit_alani] == SONDA_IZI
        _etiketsiz(json.dumps(g, ensure_ascii=False), 'ayrıştırılmış gövde')
        _etiketsiz(r.get_data(as_text=True), 'ham gövde')

    @pytest.mark.parametrize('deger,iz', [
        (SONDA_ETIKET, SONDA_IZI),
        ('a' * 41, 'str(len=41)'),
        (['star'], 'list(len=1)'),
        ('Star!', 'str(len=5)'),
        ('a' * 40, 'a' * 40),
    ], ids=['etiket', 'uzun41', 'liste', 'noktalama', 'sinir40'])
    def test_kesit_kaydi_belirtec_ya_da_iz_tasir(self, deger, iz):
        red = _kesit(_tane_govdesi(grain_type=deger))
        assert [(r['reason'], r['grain_type']) for r in red] == [
            ('grain_type_not_drawable', iz)]

    def test_celiski_kaydi_iz_tasir(self):
        md = _tane_govdesi(grain_type='bates')
        md['grain_type'] = SONDA_ETIKET
        assert [(r['reason'], r['grain_type']) for r in _kesit(md)] == [
            ('grain_type_conflict', f'bates / {SONDA_IZI}')]

    def test_port_kaydi_tur_adi_tasir(self):
        md = _tane_govdesi(grain_type='bates')
        md['port_count'] = SONDA_ETIKET
        assert [(r['reason'], r['port_count']) for r in _kesit(md)] == [
            ('port_count_not_one', SONDA_IZI)]

    @pytest.mark.parametrize('deger,iz', [
        (SONDA_ETIKET, SONDA_IZI), (float('nan'), 'float'),
        ([2.0], 'list(len=1)'), (True, 'bool'),
    ], ids=['etiket', 'nan', 'liste', 'bool'])
    def test_sf_kaydi_tur_adi_tasir(self, deger, iz):
        r = _kapi(_govde(safety_factor_total=deger))
        assert [(x['reason'], x['safety_factor_raw']) for x in r] == [
            ('sf_not_numeric', iz)]

    @pytest.mark.parametrize('alan', sorted(S2_ALANLAR))
    def test_arayuz_metni_etiket_tasimaz(self, client, kati_tam, alan,
                                        tmp_path):
        """``reject_body.js`` çıktısı (``showError``ın innerHTML'e taşıdığı
        metin) EN ve TR'de etiketsizdir ve izi taşır."""
        node = shutil.which('node')
        if node is None:
            pytest.skip('node yok: ön yüz çözücüsü bu ortamda koşturulamaz')
        status = S2_ALANLAR[alan][0]
        _r, g = _uc_reddi(client, '/api/export-step',
                          _sonda_govdesi(kati_tam, '/api/export-step', alan),
                          status)
        govde = tmp_path / 'g.json'
        govde.write_text(json.dumps(g), encoding='utf-8')
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        betik = tmp_path / 'r.js'
        betik.write_text(r'''
const fs = require('fs'); const path = require('path');
const R = process.argv[2];
global.window = global;
global.localStorage = { getItem: () => null, setItem: () => {} };
global.document = { documentElement: { setAttribute(){}, lang: 'en' },
  addEventListener(){}, querySelectorAll: () => [], readyState: 'complete' };
global.navigator = { language: 'en' };
for (const f of ['i18n.js', 'i18n_common.js', 'reject_body.js']) {
  eval(fs.readFileSync(path.join(R, 'hrma/static/js', f), 'utf8'));
}
const g = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = {};
for (const dil of ['en', 'tr']) {
  window.I18N.setLang(dil);
  out[dil] = window.HRMAReject.metni(g, 422);
}
process.stdout.write(JSON.stringify(out));
''', encoding='utf-8')
        p = subprocess.run([node, str(betik), kok, str(govde)],
                           capture_output=True, timeout=60)
        metin = json.loads(p.stdout.decode('utf-8') or '{}')
        assert set(metin) == {'en', 'tr'}, p.stderr.decode(
            errors='replace')[-400:]
        for dil, m in metin.items():
            _etiketsiz(m, dil)
            assert SONDA_IZI in m, (dil, m)


# ===========================================================================
# Pürüzsüz yüzey (14 Eki 2026; karar §28-41) — lüle B-spline revolve
# ===========================================================================
# ÖLÇÜLDÜ (12 Eki; bu turun önce ölçümü ``docs/…/cad-duzeltme/kanit/t5``):
# lüle iç konturu çokgen olarak revolve ediliyordu — sıvı örnekte 130
# CONICAL_SURFACE + 2 PLANE, konik lülelerde 80 + 2; B-spline 0. Karar:
# AYNI kontur noktalarından B-spline revolve; yayımlanan ölçüler DEĞİŞMEZ.
#
# Ölçü ayakları kesit kenarının ÜSTÜNDEN örneklenir (FreeCAD ``discretize``,
# OCC ``BRepAdaptor_Curve``); sınır kutusu KULLANILMAZ: B-spline kesitin
# sınır kutusu kutup zarfıdır ve yarıçapı büyük ölçer (bu turda ölçüldü,
# FreeCAD: +0,03-0,04 mm). Hacim OCC'nin UYARLAMALI integraliyle ölçülür:
# FreeCAD/OCC'nin varsayılan ``Volume``ı dönel B-spline yüzeyde %0,2-1,5
# yanılır (okuyucunun integrali; geometri kâhinle 4e-6 içinde — rapor).
#: Lüle: iç ve dış yüz birer düzgün yüzey + iki uç halka düzlemi.
PURUZSUZ_LULE_YUZ_SAYISI = 4
PURUZSUZ_LULE_DUZLEM_SAYISI = 2
#: Kamara (düz cidar + baş kapak): zaten analitik; çokgene dönmesin.
PURUZSUZ_KAMARA_YUZEY = {'CYLINDRICAL_SURFACE': 2, 'PLANE': 3,
                         'CONICAL_SURFACE': 0}
#: Et ölçüm istasyonu sayısı; boğaz çevresi tarama yarı genişliği [mm] ve
#: nokta sayısı.
PURUZSUZ_ISTASYON = 40
PURUZSUZ_BOGAZ_TARAMA_MM = 2.0
PURUZSUZ_BOGAZ_TARAMA_N = 41
#: OCC uyarlamalı hacim integralinin bağıl hedefi (``BRepGProp`` eps).
PURUZSUZ_HACIM_EPS = 1e-9
#: Vakalar: hibrit (konik, yayımlanan et), katı (konik, üreteç eti), sıvı
#: (bell_80 — 130 konili vaka) ve sıvının KONİK ikizi (uzun tek kuyruk
#: aralığı: kuyruk interpolasyona girerse eğri salınır — ölçüldü).
PURUZSUZ_VAKALAR = ('hybrid', 'solid', 'liquid', 'liquid_conical')


def _step_varliklari(yol):
    """STEP metninden varlık türü sayıları ve dönel yüzeylerin üreteç türü."""
    metin = ''.join(open(yol, encoding='utf-8', errors='ignore')
                    .read().split())
    tur = dict(re.findall(r'#(\d+)=([A-Z_0-9]+)\(', metin))
    sayi = {}
    for t in tur.values():
        sayi[t] = sayi.get(t, 0) + 1
    uretec = [tur.get(c) for c in re.findall(
        r"=SURFACE_OF_REVOLUTION\('[^']*',#(\d+),", metin)]
    return sayi, uretec


_FC_PURUZSUZ = r'''
import json, math, os
import FreeCAD as App
import Part
V = App.Vector
src = json.load(open(os.environ['V3CAD_GIRDI']))
def ic_dis(s, x):
    try:
        tel = s.slice(V(1, 0, 0), x)
    except Exception:
        return None
    rs = []
    for w in tel:
        r = [math.hypot(p.y, p.z) for p in w.discretize(64)]
        rs.append((min(r), max(r)))
    rs.sort()
    return rs if len(rs) >= 2 else None
out = {}
for ad, g in src.items():
    shp = Part.read(g['yol'])
    s = shp.Solids[0]
    yuz, uc = {}, []
    for f in s.Faces:
        t = f.Surface.__class__.__name__
        yuz[t] = yuz.get(t, 0) + 1
        if t == 'Plane':
            uc.append({'x': f.Surface.Position.x,
                       'r': sorted(e.Curve.Radius for e in f.Edges
                                   if e.Curve.__class__.__name__ == 'Circle')})
    def mesafe(noktalar):
        return max(min(f.distToShape(Part.Vertex(V(x, r, 0)))[0]
                       for f in s.Faces) for x, r in noktalar)
    et = []
    for x in g['istasyon']:
        r = ic_dis(s, x)
        et.append(r[-1][0] - r[0][0] if r else None)
    tarama = []
    for x in g['tarama']:
        r = ic_dis(s, x)
        tarama.append(r[0][0] if r else None)
    out[ad] = {'kati_sayisi': len(shp.Solids), 'gecerli': s.isValid(),
               'yuz': yuz, 'uc': sorted(uc, key=lambda q: q['x']),
               'mesafe_ic': mesafe(g['ic']), 'mesafe_dis': mesafe(g['dis']),
               'et': et, 'tarama': tarama}
json.dump(out, open(os.environ['V3CAD_CIKTI'], 'w'))
'''


def _occ_puruzsuz(girdi):
    """FreeCAD YOKSA aynı ölçüm OCC ile (CI ``step-export``: atlama yok)."""
    from build123d import import_step
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    def ic_dis(kati, x):
        kesit = BRepAlgoAPI_Section(kati.wrapped,
                                    gp_Pln(gp_Pnt(x, 0, 0), gp_Dir(1, 0, 0)))
        kesit.Build()
        gez = TopExp_Explorer(kesit.Shape(), TopAbs_EDGE)
        rs = []
        while gez.More():
            c = BRepAdaptor_Curve(TopoDS.Edge_s(gez.Current()))
            u0, u1 = c.FirstParameter(), c.LastParameter()
            r = []
            for i in range(65):
                p = c.Value(u0 + (u1 - u0) * i / 64)
                r.append((p.Y() ** 2 + p.Z() ** 2) ** 0.5)
            rs.append((min(r), max(r)))
            gez.Next()
        rs.sort()
        return rs if len(rs) >= 2 else None

    out = {}
    for ad, g in girdi.items():
        sekil = import_step(g['yol'])
        katilar = sekil.solids()
        kati = katilar[0]
        yuz, uc = {}, []
        for f in kati.faces():
            ad_s = BRepAdaptor_Surface(f.wrapped)
            t = str(ad_s.GetType()).split('.')[-1].replace('GeomAbs_', '')
            yuz[t] = yuz.get(t, 0) + 1
            if t == 'Plane':
                rr = []
                for e in f.edges():
                    c = BRepAdaptor_Curve(e.wrapped)
                    if c.GetType() == GeomAbs_CurveType.GeomAbs_Circle:
                        rr.append(c.Circle().Radius())
                uc.append({'x': ad_s.Plane().Location().X(), 'r': sorted(rr)})

        def mesafe(noktalar):
            enb = 0.0
            for x, r in noktalar:
                v = BRepBuilderAPI_MakeVertex(gp_Pnt(x, r, 0)).Vertex()
                d = min(BRepExtrema_DistShapeShape(v, f.wrapped).Value()
                        for f in kati.faces())
                enb = max(enb, d)
            return enb

        v = kati.is_valid
        et, tarama = [], []
        for x in g['istasyon']:
            r = ic_dis(kati, x)
            et.append(r[-1][0] - r[0][0] if r else None)
        for x in g['tarama']:
            r = ic_dis(kati, x)
            tarama.append(r[0][0] if r else None)
        out[ad] = {'kati_sayisi': len(katilar),
                   'gecerli': bool(v() if callable(v) else v),
                   'yuz': yuz, 'uc': sorted(uc, key=lambda q: q['x']),
                   'mesafe_ic': mesafe(g['ic']),
                   'mesafe_dis': mesafe(g['dis']),
                   'et': et, 'tarama': tarama,
                   'okuyucu': 'build123d/OCP (FreeCAD yok)'}
    return out


def _puruzsuz_olc(girdi, d):
    fc = _freecadcmd()
    if fc is None:
        return _occ_puruzsuz(girdi)
    yol_g = os.path.join(d, 'fc_puruzsuz_girdi.json')
    yol_c = os.path.join(d, 'fc_puruzsuz_cikti.json')
    betik = os.path.join(d, 'fc_puruzsuz.py')
    with open(yol_g, 'w') as f:
        json.dump(girdi, f)
    with open(betik, 'w') as f:
        f.write(_FC_PURUZSUZ)
    env = dict(os.environ, V3CAD_GIRDI=yol_g, V3CAD_CIKTI=yol_c)
    p = subprocess.run([fc, betik], env=env, capture_output=True, timeout=600)
    assert os.path.exists(yol_c), (
        'FreeCAD ölçümü çıktı üretmedi: '
        + p.stdout.decode(errors='replace')[-800:]
        + p.stderr.decode(errors='replace')[-800:])
    olcum = json.load(open(yol_c))
    for rec in olcum.values():
        rec['okuyucu'] = 'FreeCAD ' + fc
    return olcum


def _kahin_konturu(md):
    """İddia tarafı: üretecin kullandığı normalize gövde + TEK kontur
    örnekleyicisi (``sample_nozzle_inner_contour``) + yayımlanan çaplar."""
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    from hrma.export.cad_visualization import _nozzle_wall_design
    from hrma.export.motor_geometry import normalise_export_geometry
    md_n, _ = normalise_export_geometry(md)
    pts, meta = sample_nozzle_inner_contour(md_n, require_solved_length=True)
    L = float(md_n['chamber_length']) * 1000.0
    return {
        'L': L, 'pts': pts, 'meta': meta,
        'r_bogaz': float(md_n['throat_diameter']) * 1000.0 / 2.0,
        'r_cikis': float(md_n['exit_diameter']) * 1000.0 / 2.0,
        'r_giris': float(md_n['chamber_diameter']) * 1000.0 / 2.0,
        'et': _nozzle_wall_design(md_n)['thickness_m'] * 1000.0,
        'md_n': md_n,
    }


@pytest.fixture(scope='module')
def puruzsuz_vakalar(client, hibrit_md, tmp_path_factory):
    """Dört vakanın lüle STEP'i + kâhin konturu + okuyucu ölçümü.

    Üretimi reddedilen vaka (``StepExportDataError``) kaydına ``hata`` yazılır
    ve ölçülmez; düğümleri iddia düzeyinde kırmızı olur (fikstür hatası
    bütün vakaları birlikte düşürmesin diye). Hibrit STEP'i de burada
    üretilir (``hibrit_paket`` ret yükseltir, kayıt tutmaz)."""
    pytest.importorskip('build123d')
    from hrma.export.step_export import (StepExportDataError,
                                         generate_step_assembly)
    out = tmp_path_factory.mktemp('v3cad_puruzsuz')
    sivi = _kati_veya_sivi_md(client, 'liquid')
    sivi_konik = _kopya(sivi)
    sivi_konik.setdefault('nozzle_contour', {}).setdefault(
        'divergent', {})['type'] = 'conical'
    govdeler = {'hybrid': (hibrit_md, 'hybrid'),
                'solid': (_kati_veya_sivi_md(client, 'solid'), 'solid'),
                'liquid': (sivi, 'liquid'),
                'liquid_conical': (sivi_konik, 'liquid')}
    vakalar, girdi = {}, {}
    for ad in PURUZSUZ_VAKALAR:
        md, tip = govdeler[ad]
        try:
            files = _sessiz(generate_step_assembly, md,
                            out_dir=str(out / ad), motor_type=tip)
        except StepExportDataError as e:
            vakalar[ad] = {'hata': [str(e), e.invalid_fields]}
            continue
        k = _kahin_konturu(md)
        L, et = k['L'], k['et']
        x0, x1 = L, L + k['meta']['z_exit']
        x_t = L + k['meta']['z_throat']
        girdi[ad] = {
            'yol': files['nozzle'],
            'ic': [[L + z, r] for z, r in k['pts']],
            'dis': [[L + z, r + et] for z, r in k['pts']],
            'istasyon': [x0 + (x1 - x0) * (i + 0.5) / PURUZSUZ_ISTASYON
                         for i in range(PURUZSUZ_ISTASYON)],
            'tarama': [x_t - PURUZSUZ_BOGAZ_TARAMA_MM
                       + 2 * PURUZSUZ_BOGAZ_TARAMA_MM * i
                       / (PURUZSUZ_BOGAZ_TARAMA_N - 1)
                       for i in range(PURUZSUZ_BOGAZ_TARAMA_N)]
            + [x_t]}
        vakalar[ad] = {'files': files, 'kahin': k, 'x0': x0, 'x1': x1,
                       'x_t': x_t}
    olcum = _puruzsuz_olc(girdi, str(out)) if girdi else {}
    for ad in girdi:
        vakalar[ad]['olcum'] = olcum[ad]
    return vakalar


def _vaka(puruzsuz_vakalar, vaka):
    v = puruzsuz_vakalar[vaka]
    assert 'hata' not in v, ('lüle STEP üretilmedi', vaka, v.get('hata'))
    return v


class TestPuruzsuzYuzey:
    """§28-41: lüle STEP'i aynı kontur noktalarından B-spline revolve."""

    @pytest.mark.parametrize('vaka', PURUZSUZ_VAKALAR)
    def test_lule_yuzleri_tek_duzgun_yuzey(self, puruzsuz_vakalar, vaka):
        sayi, uretec = _step_varliklari(
            _vaka(puruzsuz_vakalar, vaka)['files']['nozzle'])
        assert sayi.get('CONICAL_SURFACE', 0) == 0, sayi
        assert sayi.get('ADVANCED_FACE', 0) == PURUZSUZ_LULE_YUZ_SAYISI, sayi
        assert sayi.get('PLANE', 0) == PURUZSUZ_LULE_DUZLEM_SAYISI, sayi
        egri_yuz = (uretec.count('B_SPLINE_CURVE_WITH_KNOTS')
                    + sayi.get('B_SPLINE_SURFACE_WITH_KNOTS', 0))
        assert egri_yuz == (PURUZSUZ_LULE_YUZ_SAYISI
                            - PURUZSUZ_LULE_DUZLEM_SAYISI), (sayi, uretec)

    @pytest.mark.parametrize('vaka', PURUZSUZ_VAKALAR)
    def test_kamara_yuzeyleri_analitik_kalir(self, puruzsuz_vakalar, vaka):
        sayi, _ = _step_varliklari(
            _vaka(puruzsuz_vakalar, vaka)['files']['chamber'])
        for tur, n in PURUZSUZ_KAMARA_YUZEY.items():
            assert sayi.get(tur, 0) == n, (tur, sayi)

    @pytest.mark.parametrize('vaka', PURUZSUZ_VAKALAR)
    def test_basiz_okuyucu_acar_tek_gecerli_kati(self, puruzsuz_vakalar,
                                                 vaka):
        o = _vaka(puruzsuz_vakalar, vaka)['olcum']
        assert o['kati_sayisi'] == 1 and o['gecerli'], o
        assert sum(o['yuz'].values()) == PURUZSUZ_LULE_YUZ_SAYISI, o['yuz']
        assert o['yuz'].get('Plane') == PURUZSUZ_LULE_DUZLEM_SAYISI, o['yuz']
        assert 'Cone' not in o['yuz'], o['yuz']

    @pytest.mark.parametrize('vaka', PURUZSUZ_VAKALAR)
    def test_kontur_noktalari_yuzeyin_ustunde(self, puruzsuz_vakalar, vaka):
        """Profil noktaları AYNI: iç ve dış konturun her noktası katının
        yüzeyindedir (eğri noktalardan TAM geçer)."""
        o = _vaka(puruzsuz_vakalar, vaka)['olcum']
        assert o['mesafe_ic'] <= _tol('step_mm'), o['mesafe_ic']
        assert o['mesafe_dis'] <= _tol('step_mm'), o['mesafe_dis']

    @pytest.mark.parametrize('vaka', PURUZSUZ_VAKALAR)
    def test_yayimlanan_olculer_korunur(self, puruzsuz_vakalar, vaka):
        v = _vaka(puruzsuz_vakalar, vaka)
        o, k, tol = v['olcum'], v['kahin'], _tol('step_mm')
        giris, cikis = o['uc'][0], o['uc'][-1]
        assert giris['x'] == pytest.approx(v['x0'], abs=tol)
        assert cikis['x'] == pytest.approx(v['x1'], abs=tol)
        assert giris['r'][0] == pytest.approx(k['r_giris'], abs=tol)
        assert cikis['r'][0] == pytest.approx(k['r_cikis'], abs=tol)
        assert cikis['r'][-1] == pytest.approx(k['r_cikis'] + k['et'],
                                               abs=tol)
        # Boğaz: istasyonunda yayımlanan yarıçap; çevresinde daha dar değil.
        tarama = o['tarama']
        assert tarama[-1] == pytest.approx(k['r_bogaz'], abs=tol)
        assert min(t for t in tarama if t is not None) >= k['r_bogaz'] - tol

    @pytest.mark.parametrize('vaka', PURUZSUZ_VAKALAR)
    def test_et_her_istasyonda_ayni(self, puruzsuz_vakalar, vaka):
        v = _vaka(puruzsuz_vakalar, vaka)
        et = [e for e in v['olcum']['et'] if e is not None]
        assert len(et) == PURUZSUZ_ISTASYON, v['olcum']['et']
        assert min(et) == pytest.approx(v['kahin']['et'], abs=_tol('step_mm'))
        assert max(et) == pytest.approx(v['kahin']['et'], abs=_tol('step_mm'))

    @pytest.mark.parametrize('vaka', PURUZSUZ_VAKALAR)
    def test_hacim_kontur_integraliyle_ayni(self, puruzsuz_vakalar, vaka):
        """Kâhin: AYNI örnekleyicinin yoğun konturu (n_conv=4001,
        n_arc=2001, n_div=4001) üzerinden halka kesik koni toplamı
        π/3·Δz·(R1²+R1R2+R2²) dış − iç. STEP hacmi OCC uyarlamalı integral."""
        import numpy as np
        from build123d import import_step
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        v = _vaka(puruzsuz_vakalar, vaka)
        k = v['kahin']
        yogun, _ = sample_nozzle_inner_contour(
            k['md_n'], n_conv=4001, n_arc=2001, n_div=4001,
            require_solved_length=True)
        z = np.array([p[0] for p in yogun])
        r = np.array([p[1] for p in yogun])
        dz, r1, r2 = np.diff(z), r[:-1], r[1:]
        R1, R2 = r1 + k['et'], r2 + k['et']
        kahin = float(np.sum(np.pi / 3.0 * dz * ((R1 ** 2 + R1 * R2 + R2 ** 2)
                                                 - (r1 ** 2 + r1 * r2
                                                    + r2 ** 2))))
        kati = import_step(v['files']['nozzle']).solids()[0]
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(kati.wrapped, g, PURUZSUZ_HACIM_EPS,
                                     False)
        assert abs(g.Mass() / kahin - 1.0) <= _tol('hacim_bagil'), (
            g.Mass(), kahin)


class TestPuruzsuzKonturKapisi:
    """Yeni eğri yolu fail-closed: bozuk kontur sessiz bozuk yüzey olmaz."""

    @staticmethod
    def _sivi_konik_noktalari(client):
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        md = _kati_veya_sivi_md(client, 'liquid')
        md.setdefault('nozzle_contour', {}).setdefault(
            'divergent', {})['type'] = 'conical'
        return sample_nozzle_inner_contour(md, require_solved_length=True)

    def test_konik_kuyruk_interpolasyona_girerse_salinir_ret(self, client):
        """Ölçüldü: sıvı örneğin konik ikizinde uzun tek kuyruk aralığı
        interpolasyona sokulursa eğri eksen boyunca geri döner. Üreteç
        kuyruğu DOĞRU tutar (kurulur); kuyruk eğriye katılırsa ret."""
        pytest.importorskip('build123d')
        from hrma.export.step_export import (
            StepExportDataError, _contour_bspline_edge)
        pts, meta = self._sivi_konik_noktalari(client)
        assert meta['noz_type'] == 'conical'
        assert _contour_bspline_edge(pts, straight_tail=True) is not None
        with pytest.raises(StepExportDataError) as e:
            _contour_bspline_edge(pts, straight_tail=False)
        assert [x['reason'] for x in e.value.invalid_fields] == [
            'contour_interpolation_oscillates']

    @pytest.mark.parametrize('bozuk', [float('nan'), float('inf'), -1.0])
    def test_sonlu_olmayan_ya_da_eksi_yaricap_ret(self, bozuk):
        pytest.importorskip('build123d')
        from hrma.export.step_export import (
            StepExportDataError, _contour_bspline_edge)
        try:
            _contour_bspline_edge([(0.0, 10.0), (1.0, bozuk), (2.0, 12.0)],
                                  straight_tail=False)
        except StepExportDataError as e:
            gerekce = [x['reason'] for x in e.invalid_fields]
        except Exception as e:  # noqa: BLE001 — adlı ret yerine çekirdek
            pytest.fail(f'adlı ret yerine {type(e).__name__} (uçta 500)')
        else:
            pytest.fail(f'bozuk nokta ({bozuk!r}) kabul edildi')
        assert gerekce == ['non_finite_contour_point']

    def test_cakisik_noktalar_tek_nokta_sayilir(self):
        """Çakışık ardışık nokta interpolasyonu çökertir (OCC
        Standard_Failure, 500); bir nokta sayılır ve eğri kurulur."""
        pytest.importorskip('build123d')
        from hrma.export.step_export import _contour_bspline_edge
        try:
            e = _contour_bspline_edge([(0.0, 10.0), (1.0, 10.5), (1.0, 10.5),
                                       (2.0, 11.0)], straight_tail=False)
        except Exception as hata:  # noqa: BLE001 — çekirdek çöküşü ölçülür
            pytest.fail('çakışık nokta eğriyi kurdurmadı: '
                        f'{type(hata).__name__}')
        assert e.length > 2.0

    @pytest.mark.parametrize('rn, gerekce', [
        (0.0, 'contour_outside_point_envelope'),
        (-5.0, 'contour_interpolation_oscillates')])
    def test_bozuk_bogaz_yayi_ucta_adli_422(self, client, rn, gerekce):
        """Dışa aktarım ucu gövdeyi istemciden alır. Boğaz eğrilik
        yarıçapı 0 → eğri sivri boğazı yuvarlayıp DARALTIR (ölçüldü
        13-430 µm); −5 mm → yay geri döner. İkisi de ÖNCE OCC istisnasıyla
        500'dü; şimdi adlı 422, ileti istek değerini yansıtmaz."""
        pytest.importorskip('build123d')
        md = _kati_veya_sivi_md(client, 'solid')
        md.setdefault('nozzle_contour', {}).setdefault(
            'convergent', {})['throat_radius_curvature'] = rn
        r = _post(client, '/api/export-step', md, motor_type='solid')
        assert r.status_code == 422, r.get_data()[:400]
        g = r.get_json()
        assert g['error'] == 'incomplete_export_inputs'
        assert {(x['field'], x['reason']) for x in g['invalid_fields']} == {
            ('nozzle_contour', gerekce)}
        assert repr(rn) not in g['message'], g['message']


# ###########################################################################
# BÖLÜM İK — İMALAT KAPISI TUTARLILIĞI (ÖH V3 CAD, 14 Eki 2026)
# ###########################################################################
#
# Karar §28-21 (i) gerekçesi: "dosya adı/etiket dosyayla birlikte dolaşmayı
# garanti etmez". ÖLÇÜLDÜ (KAB 14 Eki, devir 8): örnek hibritin STEP, DXF ve
# tam paketi kapıda 422 alırken aynı motorun ``/api/export-drawings-pdf``
# (200) ve ``/api/export-stl-zip`` (200) çıktıları iniyordu. Ana model kararı:
# imalat amaçlı BÜTÜN çıktılar aynı kapıdan (aynı işlev, aynı gövde). CADP
# D-T5-5: bozuk boğaz yayı (0 / −5 mm) STEP'te adlı 422, DXF ve STL paketi
# 200 idi; lüle konturu kapısı TEK işlev (``nozzle_contour_gate``).
#: İmalat amaçlı uçlar (motor_data gövdesi). Analiz raporu PDF'i
#: (``/api/export-pdf/<tür>``), .eng/OpenRocket/simülasyon ve uygulama içi
#: 3B görünüm (``/api/generate-3d``) imalat çıktısı DEĞİLDİR; kapı dışında.
IMALAT_UCLARI = ('/api/export-step', '/api/export-dxf',
                 '/api/export-drawings-pdf', '/api/export-stl-zip',
                 '/api/export-stl', '/api/export-complete-zip',
                 '/api/export-cad')
#: Lüle konturu kapısı uç tarafında (çokgen) çalışan uçlar; STEP kapıyı
#: kendi B-spline eğrisiyle üreticinin içinde çağırır.
KONTUR_UCLARI = tuple(u for u in IMALAT_UCLARI if u != '/api/export-step')


def _post_tip(client, uc, md, tip):
    md = dict(md)
    if uc == '/api/export-stl':
        md['motor_type'] = tip       # bu uç tipi gövdenin içinde okur
        if tip == 'hybrid':
            # Bu ucun KENDİ sözleşmesi hibritte ``port_diameter`` ister
            # (``_STL_REQUIRED_FIELDS``); çözücü başlangıç portunu yayımlar.
            md['port_diameter'] = md['port_diameter_initial']
    return _post(client, uc, md, motor_type=tip)


def _bozuk_bogaz(md, rn):
    m = json.loads(json.dumps(md))
    m.setdefault('nozzle_contour', {}).setdefault(
        'convergent', {})['throat_radius_curvature'] = rn
    return m


class TestImalatKapisiTutarliligi:
    @pytest.mark.parametrize('uc', IMALAT_UCLARI)
    def test_ornek_hibrit_hicbir_imalat_ucundan_dosya_almaz(
            self, client, hibrit_md, uc):
        """Aynı kapı, aynı gövde: ret kayıtları STEP'inkiyle BİREBİR."""
        r = _post_tip(client, uc, hibrit_md, 'hybrid')
        assert r.status_code == 422, (uc, r.status_code, r.get_data()[:300])
        g = r.get_json()
        assert g['status'] == 'manufacturing_safety_gate_closed'
        assert g['message_key'] == 'out.export.sfGate.refused'
        assert g['refusals'] == _kapi(hibrit_md)
        assert g['refusals'], 'örnek hibrit kapıya takılmalı (KAB ölçümü)'

    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    @pytest.mark.parametrize('uc', ['/api/export-drawings-pdf',
                                    '/api/export-stl-zip', '/api/export-stl'])
    def test_ornek_kati_ve_sivi_imalat_ucundan_gecer(self, client, tip, uc):
        md = _kati_veya_sivi_md(client, tip)
        assert _kapi(md) == []
        r = _post_tip(client, uc, md, tip)
        assert r.status_code == 200, (uc, r.status_code, r.get_data()[:300])
        assert 'json' not in r.headers['content-type']
        assert len(r.get_data()) > 1000

    def test_uc_ici_3b_gorunum_kapinin_disinda(self, client, hibrit_md):
        """Uygulama içi 3B görünüm imalat çıktısı değildir: aynı hibrit."""
        r = _sessiz(client.post, '/api/generate-3d',
                    json={'motor_data': hibrit_md}, headers=HEADERS)
        assert r.status_code == 200, r.get_data()[:300]

    def test_kapi_reddi_agir_cekirdegi_yuklemez(self, hibrit_md, tmp_path):
        """STL paketi ve çizim PDF'i reddi build123d/OCC yüklemez (H3-B14)."""
        govde = tmp_path / 'g.json'
        govde.write_text(json.dumps({'motor_data': hibrit_md,
                                     'motor_type': 'hybrid'}),
                         encoding='utf-8')
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        betik = (
            'import contextlib, io, json, os, sys\n'
            f'sys.path.insert(0, {kok!r})\n'
            'from hrma.app import app\n'
            f'g = json.load(open({str(govde)!r}))\n'
            'c = app.test_client(); kod = []\n'
            'with contextlib.redirect_stdout(io.StringIO()):\n'
            '    for u in ("/api/export-stl-zip", "/api/export-drawings-pdf"):\n'
            '        kod.append(c.post(u, json=g, headers={"Host": '
            '"127.0.0.1:8080"}).status_code)\n'
            'print(json.dumps([kod, "hrma.export.step_export" in sys.modules,\n'
            '    "build123d" in sys.modules]))\n')
        env = dict(os.environ,
                   HRMA_PROJECTS_DIR=str(tmp_path / 'p'), BROWSER='echo')
        p = subprocess.run([sys.executable, '-c', betik], cwd=kok, env=env,
                           capture_output=True, text=True, timeout=300)
        satir = [s for s in p.stdout.splitlines() if s.startswith('[')]
        assert satir, p.stdout[-400:] + p.stderr[-400:]
        kod, step_yuklu, occ_yuklu = json.loads(satir[-1])
        assert kod == [422, 422]
        assert not step_yuklu and not occ_yuklu


#: Bozuk boğaz yayı -> uç tarafı (çokgen) kapının gerekçesi. −5 mm'de yay
#: eksen boyunca geri döner; 0'da yay tek noktaya çöker ve çokgen sivri
#: köşedir, ret yayımlanan boğaz yayının kendisidir.
KONTUR_BOZUK = ((0.0, 'throat_radius_curvature_not_positive'),
                (-5.0, 'contour_turns_back'))


class TestKonturKapisiUclar:
    @pytest.mark.parametrize('rn, gerekce', KONTUR_BOZUK)
    @pytest.mark.parametrize('uc', KONTUR_UCLARI)
    def test_bozuk_bogaz_yayi_adli_422(self, client, uc, rn, gerekce):
        md = _bozuk_bogaz(_kati_veya_sivi_md(client, 'solid'), rn)
        r = _post_tip(client, uc, md, 'solid')
        assert r.status_code == 422, (uc, r.status_code, r.get_data()[:300])
        g = r.get_json()
        assert g['error'] == 'incomplete_export_inputs'
        assert g['message_key'] == 'out.export.contourGate.refused'
        assert {(x['field'], x['reason']) for x in g['invalid_fields']} == {
            ('nozzle_contour', gerekce)}
        assert [x['reason_key'] for x in g['refusals']] == [
            f'out.export.contourGate.reason.{gerekce}']
        assert repr(rn) not in g['message'], g['message']

    @pytest.mark.parametrize('rn, gerekce', KONTUR_BOZUK)
    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    def test_cad_paketi_bozuk_konturda_stl_yalniz_inmez(
            self, client, tip, rn, gerekce):
        """Katı/sıvı CAD paketi (``_motor_cad_zip_response``) de aynı kapıdan.
        Ölçüldü: ``*_results_to_motor_geometry`` ``nozzle_contour``u
        taşımadığı için uçtan gelen bozuk yay bugün pakete ULAŞMAZ; kapı
        paket üreticisine verilen geometride sınanır (STEP reddedip paketin
        STL-yalnız inmesi eski davranıştı)."""
        from hrma.app import _motor_cad_zip_response, app
        from hrma.export.motor_geometry import normalise_export_geometry
        geo, _ = normalise_export_geometry(_kati_veya_sivi_md(client, tip))
        geo = _bozuk_bogaz(geo, rn)
        with app.test_request_context():
            yanit, kod = _sessiz(_motor_cad_zip_response, geo, tip, 'X')
        assert kod == 422
        assert {(x['field'], x['reason'])
                for x in yanit.get_json()['invalid_fields']} == {
            ('nozzle_contour', gerekce)}

    @pytest.mark.parametrize('ham', ['nan', 'inf', '1e400', True, 'abc'])
    @pytest.mark.parametrize('uc', ['/api/export-dxf', '/api/export-step'])
    def test_sonlu_olmayan_bogaz_yayi_sessiz_yedege_dusmez(
            self, client, uc, ham):
        """Ölçüldü (14 Eki): yayımlanmış ama sonlu olmayan boğaz yayı
        örnekleyicide Rao 0,382·rt'ye SESSİZCE düşüyor, DXF 200 iniyordu.
        Kapı yayımlanan değeri okur: adlı 422 (STEP de aynı işlevden)."""
        if uc == '/api/export-step':
            pytest.importorskip('build123d')
        md = _bozuk_bogaz(_kati_veya_sivi_md(client, 'solid'), ham)
        r = _post(client, uc, md, motor_type='solid')
        assert r.status_code == 422, (uc, r.status_code, r.get_data()[:300])
        assert {(x['field'], x['reason'])
                for x in r.get_json()['invalid_fields']} == {
            ('nozzle_contour', 'throat_radius_curvature_not_positive')}

    def test_step_kontur_reddi_sozluk_anahtari_tasir(self, client):
        """STEP'in mevcut gerekçeleri AYNEN (TestPuruzsuzKonturKapisi);
        gövde artık ``message_key`` + ``reason_key`` de taşır (D-T5-3)."""
        pytest.importorskip('build123d')
        md = _bozuk_bogaz(_kati_veya_sivi_md(client, 'solid'), -5.0)
        g = _post(client, '/api/export-step', md, motor_type='solid'
                  ).get_json()
        assert g['message_key'] == 'out.export.contourGate.refused'
        assert [x['reason'] for x in g['refusals']] == [
            'contour_interpolation_oscillates']
        assert 'refusing to emit a manufacturing STEP' in g['message']


class TestKonturKapisiTekIslev:
    def _kapi(self, pts, **k):
        from hrma.engines.nozzle_design import (
            NozzleContourError, nozzle_contour_gate)
        try:
            nozzle_contour_gate(pts, **k)
        except NozzleContourError as e:
            return e.reason
        return None

    def test_saglam_cokgen_gecer(self):
        assert self._kapi([(0.0, 20.0), (5.0, 10.0), (9.0, 10.5),
                           (30.0, 25.0)], throat_radius_curvature_mm=3.8) \
            is None

    @pytest.mark.parametrize('pts, k, neden', [
        ([(0.0, 20.0), (5.0, float('nan')), (9.0, 12.0)], {},
         'non_finite_contour_point'),
        ([(0.0, 20.0), (0.0, 20.0)], {}, 'too_few_contour_points'),
        ([(0.0, 20.0), (5.0, 10.0), (4.0, 9.0), (30.0, 25.0)], {},
         'contour_turns_back'),
        ([(0.0, 20.0), (5.0, 0.0), (30.0, 25.0)], {}, 'contour_turns_back'),
        ([(0.0, 20.0), (5.0, 10.0), (30.0, 25.0)],
         {'throat_radius_curvature_mm': 0.0},
         'throat_radius_curvature_not_positive'),
        ([(0.0, 20.0), (5.0, 10.0), (30.0, 25.0)],
         {'throat_radius_curvature_mm': float('inf')},
         'throat_radius_curvature_not_positive'),
    ])
    def test_cokgen_gerekceleri(self, pts, k, neden):
        assert self._kapi(pts, **k) == neden

    def test_egri_kipinde_zarf_ve_salinim(self):
        """Eğri kurucu (STEP) verilirse geri dönme gerekçesi B-spline'ınkidir
        ve zarf eğri örneklerinden ölçülür — aynı işlev."""
        import numpy as np
        pts = [(0.0, 20.0), (5.0, 10.0), (30.0, 25.0)]
        geri = lambda p: (None, np.array([0.0, 6.0, 5.0, 30.0]),  # noqa: E731
                          np.array([20.0, 10.0, 11.0, 25.0]))
        tasan = lambda p: (None, np.array([0.0, 5.0, 30.0]),  # noqa: E731
                           np.array([20.0, 9.0, 25.0]))
        assert self._kapi(pts, curve_builder=geri) == \
            'contour_interpolation_oscillates'
        assert self._kapi(pts, curve_builder=tasan) == \
            'contour_outside_point_envelope'

    def test_ornek_motorlar_kapidan_gecer(self, client):
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        from hrma.export.motor_geometry import normalise_export_geometry
        for tip in ('solid', 'liquid'):
            md, _ = normalise_export_geometry(_kati_veya_sivi_md(client, tip))
            pts, meta = sample_nozzle_inner_contour(md)
            assert self._kapi(pts, throat_radius_curvature_mm=meta[
                'throat_radius_curvature_mm']) is None, tip


def test_kontur_kapisi_anahtarlari_en_tr_sozlukte():
    from hrma.engines.nozzle_design import NOZZLE_CONTOUR_REASONS
    from hrma.export import cad_visualization as cv
    assert set(cv.CONTOUR_GATE_REASON_KEYS) == set(NOZZLE_CONTOUR_REASONS)
    en, tr = _sozluk('en'), _sozluk('tr')
    kayit = cv.contour_gate_body('contour_turns_back', 'x', 'y')[
        'refusals'][0]
    for k in [cv.CONTOUR_GATE_MESSAGE_KEY] + list(
            cv.CONTOUR_GATE_REASON_KEYS.values()):
        assert k in en and k in tr, k
        yt = set(re.findall(r'\{(\w+)\}', en[k]))
        assert yt == set(re.findall(r'\{(\w+)\}', tr[k])), k
        assert not yt - set(kayit), f'{k}: kayıtta olmayan yer tutucu'
        assert en[k] != tr[k], f'{k} Türkçeye çevrilmemiş'


def test_kontur_reddi_arayuzde_turkce_basilir(client, tmp_path):
    """reject_body.js kontur gövdesini sözlükten basar (node yoksa atlanır)."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: ön yüz çözücüsü bu ortamda koşturulamaz')
    md = _bozuk_bogaz(_kati_veya_sivi_md(client, 'solid'), -5.0)
    g = _post(client, '/api/export-stl-zip', md, motor_type='solid'
              ).get_json()
    govde = tmp_path / 'g.json'
    govde.write_text(json.dumps(g), encoding='utf-8')
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    betik = tmp_path / 'r.js'
    betik.write_text(r'''
const fs = require('fs'); const path = require('path');
const R = process.argv[2];
global.window = global;
global.localStorage = { getItem: () => null, setItem: () => {} };
global.document = { documentElement: { setAttribute(){}, lang: 'en' },
  addEventListener(){}, querySelectorAll: () => [], readyState: 'complete' };
global.navigator = { language: 'en' };
for (const f of ['i18n.js', 'i18n_common.js', 'reject_body.js']) {
  eval(fs.readFileSync(path.join(R, 'hrma/static/js', f), 'utf8'));
}
const g = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
window.I18N.setLang('tr');
process.stdout.write(window.HRMAReject.metni(g, 422));
''', encoding='utf-8')
    p = subprocess.run([node, str(betik), kok, str(govde)],
                       capture_output=True, timeout=60)
    metin = p.stdout.decode('utf-8')
    # ÖH 14 Eki (ana model): TR sözlüğün tek terim kuralı nozzle → 'nozul'
    # (test_d27_arayuz_a2 P12aB2-05, test_z5i18n_kalan); metin 'lüle' ile
    # yazılmıştı, main'de d27 bekçisini kırdı — çapa sözlükle birlikte çevrildi.
    assert 'İmalat dışa aktarımı reddedildi: nozul konturundan' in metin, (
        metin + p.stderr.decode(errors='replace')[-400:])
    assert 'Nozul: nozul konturu eksen boyunca geri dönüyor' in metin
    assert 'refused' not in metin and 'turns back' not in metin


class TestHacimNotuReadme:
    """CADP D-T5-2: lüle STEP'i olan pakette CAD hacim okuma notu (EN+TR)."""

    def test_lule_varsa_not_iki_dilde(self, tmp_path):
        from hrma.export import step_export
        yollar = []
        for ad in ('chamber', 'nozzle', 'assembly'):
            p = tmp_path / f'M_{ad}.step'
            p.write_text('ISO-10303-21;', encoding='utf-8')
            yollar.append(str(p))
        metin = step_export.step_package_readme(yollar)
        for satir in step_export.STEP_NOZZLE_VOLUME_NOTE:
            assert satir in metin
        assert 'Shape.Volume' in metin and 'mass_breakdown.nozzle_mass' in metin
        assert 'yüksek hassasiyetli' in metin

    def test_lule_yoksa_not_yok(self, tmp_path):
        from hrma.export import step_export
        p = tmp_path / 'M_chamber.step'
        p.write_text('ISO-10303-21;', encoding='utf-8')
        metin = step_export.step_package_readme([str(p)])
        assert step_export.STEP_NOZZLE_VOLUME_NOTE[0] not in metin


# ###########################################################################
# BÖLÜM CK — CAD KÜÇÜK KALEMLER (ÖH V3 CAD, 14 Eki 2026; CADI devirleri)
# ###########################################################################
#
# D-T6-4 (güvenlik): örnekleyicinin öteki istemci açı alanları sonlu
# değilse sessizce 30°/8°/15°/15°/30° varsayılanına düşüyordu; ölçüldü
# (kanit/t7/olcum/kiyas.txt): 5 alan x 5 bozuk değer DXF ve STL paketinde
# 25/25 HTTP 200, STEP ve katı/sıvı CAD paketinde 5/5 HTTP 200.
# D-T6-5 (tutarlılık): katı/sıvı CAD paketinin lülesi yayımlanan yayı
# taşımıyordu. D-T6-3 (ölü kod): advanced.html exportMotorSTL. D-T6-2
# (yeniden üretilebilirlik): DXF CLASSES sırası süreçten sürece.

#: Kapının adıyla bastığı açı alanları (tek kaynak ``nozzle_design``).
ACI_ALANLARI = (
    'nozzle_contour.divergent.throat_angle',
    'nozzle_contour.divergent.exit_angle',
    'nozzle_contour.divergent.half_angle',
    'nozzle_angles.divergent_half_angle_deg',
    'nozzle_angles.convergent_half_angle_deg')
#: Okunamayan değerler (CADP boğaz yayı ölçümündeki küme + yansıma izi).
ACI_BOZUK = ('nan', 'inf', '1e400', True, 'abc-yansima-izi')


def _aci_yaz(md, yol, ham):
    m = json.loads(json.dumps(md))
    parcalar = yol.split('.')
    dugum = m
    for p in parcalar[:-1]:
        dugum = dugum.setdefault(p, {})
    dugum[parcalar[-1]] = ham
    return m


class TestKonturAciAlanlari:
    """D-T6-4: yayımlanmış ama okunamayan açı -> adlı 422 (tek kapı)."""

    def test_alan_listesi_tek_kaynakta(self):
        from hrma.engines.nozzle_design import NOZZLE_CONTOUR_ANGLE_FIELDS
        assert NOZZLE_CONTOUR_ANGLE_FIELDS == ACI_ALANLARI

    @pytest.mark.parametrize('ham', ACI_BOZUK)
    @pytest.mark.parametrize('yol', ACI_ALANLARI)
    def test_ornekleyici_okunamayan_alani_adlandirir(self, client, yol, ham):
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        from hrma.export.motor_geometry import normalise_export_geometry
        md, _ = normalise_export_geometry(
            _aci_yaz(_kati_veya_sivi_md(client, 'solid'), yol, ham))
        _pts, meta = sample_nozzle_inner_contour(md)
        assert meta['unreadable_angle_fields'] == [yol]

    @pytest.mark.parametrize('yol', ACI_ALANLARI)
    def test_alan_yoksa_ya_da_sonluysa_liste_bos(self, client, yol):
        """Alan HİÇ yoksa (None) mevcut davranış: kayıtlı varsayılan."""
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        from hrma.export.motor_geometry import normalise_export_geometry
        for ham in (None, 12.0, '12.0'):
            md, _ = normalise_export_geometry(
                _aci_yaz(_kati_veya_sivi_md(client, 'solid'), yol, ham))
            assert sample_nozzle_inner_contour(md)[1][
                'unreadable_angle_fields'] == [], (yol, ham)

    def test_kapi_birim(self):
        from hrma.engines.nozzle_design import (
            NozzleContourError, nozzle_contour_gate)
        pts = [(0.0, 20.0), (5.0, 10.0), (9.0, 10.5), (30.0, 25.0)]
        nozzle_contour_gate(pts, unreadable_angle_fields=[])
        with pytest.raises(NozzleContourError) as e:
            nozzle_contour_gate(pts, unreadable_angle_fields=[
                'nozzle_angles.convergent_half_angle_deg'])
        assert e.value.reason == 'contour_angle_not_finite'
        assert 'nozzle_angles.convergent_half_angle_deg' in e.value.message
        # Listede olmayan ad (istekten gelebilecek metin) iletiye girmez.
        with pytest.raises(NozzleContourError) as e:
            nozzle_contour_gate(pts, unreadable_angle_fields=['<b>x</b>'])
        assert '<b>' not in e.value.message

    @pytest.mark.parametrize('yol', ACI_ALANLARI)
    @pytest.mark.parametrize('uc', KONTUR_UCLARI)
    def test_uclar_adli_422(self, client, uc, yol):
        md = _aci_yaz(_kati_veya_sivi_md(client, 'solid'), yol,
                      'abc-yansima-izi')
        r = _post_tip(client, uc, md, 'solid')
        assert r.status_code == 422, (uc, r.status_code, r.get_data()[:300])
        g = r.get_json()
        assert g['message_key'] == 'out.export.contourGate.refused'
        assert {(x['field'], x['reason']) for x in g['invalid_fields']} == {
            ('nozzle_contour', 'contour_angle_not_finite')}
        assert [x['reason_key'] for x in g['refusals']] == [
            'out.export.contourGate.reason.contour_angle_not_finite']
        assert 'yansima' not in r.get_data(as_text=True)

    @pytest.mark.parametrize('ham', ['nan', True])
    def test_step_ayni_kapidan(self, client, ham):
        pytest.importorskip('build123d')
        md = _aci_yaz(_kati_veya_sivi_md(client, 'solid'),
                      'nozzle_contour.divergent.exit_angle', ham)
        r = _post(client, '/api/export-step', md, motor_type='solid')
        assert r.status_code == 422, r.get_data()[:300]
        assert [x['reason'] for x in r.get_json()['refusals']] == [
            'contour_angle_not_finite']

    @pytest.mark.parametrize('tip, uc', [('solid', '/export_solid_motor_cad'),
                                         ('liquid', '/export_liquid_cad')])
    def test_cad_paketi_ayni_kapidan(self, client, tip, uc):
        """D-T6-5 ile birlikte: paket yayımlanan konturu taşıdığı için
        çözücü yanıtındaki okunamayan açı pakete de ulaşır (önce 200)."""
        doc = load_example_doc(tip)
        sonuc = _sessiz(client.post, ENDPOINTS[tip],
                        json=calculate_payload(tip, doc['inputs']['fields']),
                        headers=HEADERS).get_json()
        sonuc = _aci_yaz(sonuc, 'nozzle_contour.divergent.throat_angle',
                         'nan')
        r = _sessiz(client.post, uc, json={'results': sonuc},
                    headers=HEADERS)
        assert r.status_code == 422, (uc, r.status_code)
        assert {(x['field'], x['reason'])
                for x in r.get_json()['invalid_fields']} == {
            ('nozzle_contour', 'contour_angle_not_finite')}

    def test_ornek_motorlarda_dxf_degismez(self, client):
        for tip in ('solid', 'liquid'):
            r = _post(client, '/api/export-dxf',
                      _kati_veya_sivi_md(client, tip), motor_type=tip)
            assert r.status_code == 200, (tip, r.get_data()[:300])

    def test_ret_arayuzde_turkce(self):
        en, tr = _sozluk('en'), _sozluk('tr')
        k = 'out.export.contourGate.reason.contour_angle_not_finite'
        assert 'sonlu bir sayı değil' in tr[k]
        assert 'is not a finite number' in en[k]


class TestPaketKonturTekKaynak:
    """D-T6-5: katı/sıvı CAD paketi yayımlanan lüle konturunu taşır."""

    @pytest.mark.parametrize('donustur', ['solid', 'liquid'])
    def test_izdusum_tasinir(self, donustur):
        from hrma.export import motor_geometry as mg
        f = {'solid': mg.solid_results_to_motor_geometry,
             'liquid': mg.liquid_results_to_motor_geometry}[donustur]
        kontur = {'points': [[0.0, 0.05], [0.1, 0.02]], '_basis': 'x',
                  'convergent': {'throat_radius_curvature': 7.0},
                  'divergent': {'exit_angle': 11.0}}
        out = f({'nozzle_contour': kontur})
        assert out['nozzle_contour'] == {
            'convergent': {'throat_radius_curvature': 7.0},
            'divergent': {'exit_angle': 11.0}}
        # Çözücünün kendi nokta dökümü ikinci kez serileştirilmez.
        assert 'nozzle_contour' not in f(
            {'nozzle_contour': {'points': [[0.0, 0.05]], '_basis': 'x'}})
        assert 'nozzle_contour' not in f({})

    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    def test_yanit_blogu_degismedi(self, client, tip):
        """Örnek çözücü yanıtı yalnız ``points`` + ``_basis`` yayımlar:
        ``motor_geometry`` bloğuna kontur girmez (yanıt bayt-aynı)."""
        doc = load_example_doc(tip)
        sonuc = _sessiz(client.post, ENDPOINTS[tip],
                        json=calculate_payload(tip, doc['inputs']['fields']),
                        headers=HEADERS).get_json()
        assert sorted(sonuc['nozzle_contour']) == ['_basis', 'points']
        assert 'nozzle_contour' not in sonuc['motor_geometry']

    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    def test_paket_lulesi_tekil_uclarla_ayni(self, client, tip):
        """Yayımlanan yay 0,382·rt değilse paket ⟷ tekil uç aynı lüle.
        Kâhin: tekil uçların zaten okuduğu girdi (STEP/DXF/STL paketi)."""
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        from hrma.export import motor_geometry as mg
        doc = load_example_doc(tip)
        sonuc = _sessiz(client.post, ENDPOINTS[tip],
                        json=calculate_payload(tip, doc['inputs']['fields']),
                        headers=HEADERS).get_json()
        tekil, _ = mg.normalise_export_geometry(sonuc['motor_geometry'])
        rt = tekil['throat_diameter'] * 500.0
        ek = {'convergent': {'throat_radius_curvature': 1.0 * rt},
              'divergent': {'exit_angle': 12.0}}
        sonuc['nozzle_contour'].update(ek)
        tekil_md = dict(sonuc['motor_geometry'], nozzle_contour=ek)
        donustur = {'solid': mg.solid_results_to_motor_geometry,
                    'liquid': mg.liquid_results_to_motor_geometry}[tip]
        paket, _ = mg.normalise_export_geometry(donustur(sonuc))
        tekil, _ = mg.normalise_export_geometry(tekil_md)
        p_pts, p_meta = sample_nozzle_inner_contour(paket)
        t_pts, t_meta = sample_nozzle_inner_contour(tekil)
        assert p_meta['throat_radius_curvature_mm'] == pytest.approx(rt)
        assert p_pts == t_pts
        assert p_meta['divergent_length_mm'] == t_meta['divergent_length_mm']


class TestExportMotorStlSokuldu:
    """D-T6-3: advanced.html'deki bağlanmamış exportMotorSTL söküldü."""

    def test_islev_ve_cagri_yok(self):
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, 'hrma/templates/advanced.html'),
                  encoding='utf-8') as f:
            metin = f.read()
        assert 'function exportMotorSTL' not in metin
        assert "fetch('/api/export-stl'" not in metin
        # Bağlı STL düğmesi (exportSTL -> STL paketi) aynen duruyor.
        assert 'onclick="exportSTL()"' in metin
        assert "'/api/export-stl-zip'" in metin

    def test_yalniz_ona_ait_anahtarlar_sokuldu(self):
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, 'hrma/static/js/i18n_advanced.js'),
                  encoding='utf-8') as f:
            sozluk = f.read()
        for k in ('adv.msg.generatingExportingSTLFiles',
                  'adv.msg.stlFilesExportedSuccessfully',
                  'adv.msg.errorExportingSTL'):
            assert f"'{k}'" not in sozluk, k
        # Başka işlevlerin de kullandığı anahtar korunur.
        assert sozluk.count("'adv.msg.pleaseRunAnalysisFirst2'") == 2


#: DXF yazım sırası tohum ölçümü: önce 0 ve 4 iki FARKLI CLASSES sırası
#: üretiyordu (kanit/t7/olcum/dxf_tohum.txt).
DXF_TOHUMLARI = ('0', '4', '7')


class TestDxfBelirlenimci:
    """D-T6-2: aynı girdi -> aynı bayt (zaman damgası/GUID dışında)."""

    def _uret(self, tohum, tmp_path):
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        betik = (
            'import json, os, sys\n'
            'sys.path.insert(0, sys.argv[1])\n'
            'from hrma.export.drawing_generator import generate_dxf, '
            'canonicalize_dxf_text\n'
            "y = json.load(open(os.path.join(sys.argv[1], 'tests/support/"
            "uc_yukleri.json')))['/api/export-dxf']['motor_data']\n"
            'p = generate_dxf(y, sys.argv[2])\n'
            "sys.stdout.buffer.write(canonicalize_dxf_text(open(p, 'rb')"
            '.read()))\n')
        ortam = dict(os.environ, PYTHONHASHSEED=tohum,
                     HRMA_PROJECTS_DIR=str(tmp_path))
        p = subprocess.run([sys.executable, '-c', betik, kok,
                            str(tmp_path / f'd{tohum}.dxf')],
                           capture_output=True, env=ortam, timeout=240)
        assert p.returncode == 0, p.stderr.decode(errors='replace')[-600:]
        return p.stdout

    def test_tohumdan_bagimsiz_kanonik_bayt(self, tmp_path):
        ciktilar = {t: self._uret(t, tmp_path) for t in DXF_TOHUMLARI}
        assert len(set(ciktilar.values())) == 1, {
            t: len(b) for t, b in ciktilar.items()}
        metin = ciktilar['0'].decode()
        satirlar = [s.strip() for s in metin.splitlines()]
        siniflar = satirlar[satirlar.index('CLASSES'):
                            satirlar.index('TABLES')]
        assert siniflar.index('ACDBPLACEHOLDER') < siniflar.index('LAYOUT')

    def test_sinif_kumesi_ezdxf_ile_ayni(self, tmp_path):
        """Yalnız sıra sabitlenir: sınıf KÜMESİ ezdxf'in kendi yazımıyla
        aynıdır (eklenen/düşen sınıf yok)."""
        import ezdxf
        from hrma.export.drawing_generator import (
            register_dxf_classes_in_fixed_order)
        a = ezdxf.new('R2010', setup=True)
        b = ezdxf.new('R2010', setup=True)
        register_dxf_classes_in_fixed_order(a)
        a.saveas(str(tmp_path / 'a.dxf'))
        b.saveas(str(tmp_path / 'b.dxf'))
        assert {k for k in a.classes.classes} == {k for k in b.classes.classes}


#: Sözlük olmayan (dolu) blok -> kapı gerekçesi. Ölçüldü (14 Eki, katı
#: örnek; kanit/t7/olcum/cop_blok.txt): ilk ikisi DXF ve STL paketinde HTTP
#: 500 (AttributeError) idi, katı CAD paketi 200 ile çöpü yok sayıyordu.
BOZUK_BLOKLAR = (
    ('nozzle_contour', {'convergent': 5},
     'throat_radius_curvature_not_positive'),
    ('nozzle_contour', {'divergent': [1]}, 'contour_angle_not_finite'),
    ('nozzle_contour', [1], 'throat_radius_curvature_not_positive'),
    ('nozzle_angles', 'abc-yansima-izi', 'contour_angle_not_finite'),
)


class TestKonturBlokTipi:
    """Girdi yolu tip denetimi (fail-closed): 500 değil adlı 422."""

    @pytest.mark.parametrize('alan, blok, gerekce', BOZUK_BLOKLAR)
    @pytest.mark.parametrize('uc', ['/api/export-dxf', '/api/export-stl-zip',
                                    '/api/export-drawings-pdf'])
    def test_uclar(self, client, uc, alan, blok, gerekce):
        md = dict(_kati_veya_sivi_md(client, 'solid'), **{alan: blok})
        r = _post(client, uc, md, motor_type='solid')
        assert r.status_code == 422, (uc, r.status_code, r.get_data()[:300])
        assert {(x['field'], x['reason'])
                for x in r.get_json()['invalid_fields']} == {
            ('nozzle_contour', gerekce)}
        assert 'yansima' not in r.get_data(as_text=True)

    def test_paket_ayni_hukum(self, client):
        doc = load_example_doc('solid')
        sonuc = _sessiz(client.post, ENDPOINTS['solid'],
                        json=calculate_payload('solid',
                                               doc['inputs']['fields']),
                        headers=HEADERS).get_json()
        sonuc['nozzle_contour']['convergent'] = 5
        r = _sessiz(client.post, '/export_solid_motor_cad',
                    json={'results': sonuc}, headers=HEADERS)
        assert r.status_code == 422
        assert {(x['field'], x['reason'])
                for x in r.get_json()['invalid_fields']} == {
            ('nozzle_contour', 'throat_radius_curvature_not_positive')}

    def test_bos_blok_yok_sayilir(self, client):
        """Boş/yanlış-tipli BOŞ blok (``[]``, ``''``) eskisi gibi 'yok'."""
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        from hrma.export.motor_geometry import normalise_export_geometry
        for blok in ([], '', {}):
            md, _ = normalise_export_geometry(dict(
                _kati_veya_sivi_md(client, 'solid'), nozzle_contour=blok))
            meta = sample_nozzle_inner_contour(md)[1]
            assert meta['unreadable_angle_fields'] == []
            assert meta['throat_radius_curvature_mm'] > 0
