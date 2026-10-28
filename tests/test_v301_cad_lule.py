"""V301 bilinen C1 — STEP ⟷ STL lülesi TEK kaynaktan (22 Eki 2026).

CHANGELOG bilinen sınırı: "aynı CAD paketindeki STEP ve STL lülesi farklı
hacim veriyor" (örnek hibrit STEP 157240 ⟷ STL 152425 mm³, %3,06).
ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/bilinen/cad/once_c1.json``):

* İki üretecin iç konturu AYNI noktalardan geçiyordu; farkın +%2,50'si
  STEP'i okuyan OCC VARSAYILAN hacim integraliydi (dönel B-spline yüzeyde),
  -%0,64'ü STL'in 32 kesitli çokgen açığı. Uyarlamalı integral analitik
  kâhine 1,4e-4 içinde.
* Et kuralı (dış kontur = iç kontur + et, aynı istasyonda) yine de ÜÇ yerde
  ayrı yazılıydı (STEP, STL, kütle dökümü). Artık tek işlev:
  ``cad_visualization.nozzle_wall_profile``.

Bekçiler:
1. Profil kuralı (iç = örnekleyici, et = çözümleyici, dış = iç + et).
2. Tek kaynak: kaynağı değiştir -> STEP, STL ve kütle BİRLİKTE değişir
   (bir üreteç kendi kopyasına dönerse kırmızı).
3. Üç örnek motorda STEP (uyarlamalı) ⟷ STL hacmi ``hacim_bagil`` içinde;
   STL hacmi analitik çokgen hacminin TAM 32 kesit katı.
4. STEP README hacim notu ölçümü taşır (varsayılan okuyucu sapması notta
   yazılandan büyük değil).
"""

import contextlib
import io
import math
import os

import pytest

from tests.test_example_projects import (
    ENDPOINTS, HEADERS, NAMES, calculate_payload, load_example_doc)
from tests.test_v3_cad_duzeltme import _step_hacim_uyarlamali, _tol

#: STL katısının analitik çokgen profiline oranı: trimesh revolve'u 32 kesit
#: kurar (``trimesh.creation.revolve`` varsayılanı); kesit alanı çokgen
#: katsayısıyla ölçeklenir: k = (32 / 2π)·sin(2π / 32).
STL_KESIT = 32
STL_COKGEN_KATSAYISI = (STL_KESIT / (2.0 * math.pi)) * math.sin(
    2.0 * math.pi / STL_KESIT)
#: STL köşeleri float32 yazılır (``TOLERANS['stl_mm']`` ile aynı köken):
#: 1e-5 bağıl, float32'nin 6e-8'inin çok üstünde, kesit sayısı 31 ya da 33
#: olsaydı oluşacak 1,3e-4 farkın çok altında.
STL_COKGEN_BAGIL = 1e-5
#: STEP lülesi (B-spline) ⟷ analitik çokgen kâhini. Eğri noktalardan TAM
#: geçer, aralarda kirişten ayrılır; ölçülen en büyük fark 1,34e-4 (sıvı
#: çan lüle). 1e-3, B-spline'ın kirişten sapmasını taşır, %0,64'lük çokgen
#: açığını ya da bir et hatasını taşımaz.
STEP_KAHIN_BAGIL = 1e-3
#: Varsayılan okuyucu sapması notta 2 ondalıkla yazılır; yuvarlama payı.
NOT_YUVARLAMA_PCT = 0.005
#: Tek kaynak bekçisinin ete eklediği sınama artışı [mm] (yalnız test).
ET_ARTISI_MM = 1.5


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


@pytest.fixture(scope='module')
def ornek_md(client):
    """Üç örnek motorun dışa aktarım gövdesi (ürün yolundan)."""
    out = {}
    for tip in ('hybrid', 'solid', 'liquid'):
        doc = load_example_doc(tip)
        r = _sessiz(client.post, ENDPOINTS[tip],
                    json=calculate_payload(tip, doc['inputs']['fields']),
                    headers=HEADERS)
        assert r.status_code == 200, (tip, r.status_code)
        body = r.get_json()
        if tip == 'hybrid':
            md = dict(body['motor'])
            md['motor_name'] = 'V301CAD_HIBRIT'
        else:
            md = dict(body['motor_geometry'])
            md.setdefault('motor_name', NAMES[tip])
        out[tip] = md
    return out


def _paket(md, tip, d):
    """Aynı gövdeden STEP lülesi + STL lülesi (dosyadan geri okunur)."""
    pytest.importorskip('build123d')
    trimesh = pytest.importorskip('trimesh')
    from hrma.export.cad_visualization import MotorCADDesigner
    from hrma.export.step_export import generate_step_assembly
    step = _sessiz(generate_step_assembly, md, out_dir=str(d / 'step'),
                   motor_type=tip)
    designer = MotorCADDesigner()
    cad = _sessiz(designer.generate_3d_motor_assembly, dict(md))
    assert not cad.get('error'), cad.get('error')
    _sessiz(designer.export_stl_files, cad['assembly_meshes'],
            output_dir=str(d / 'stl'))
    yol = str(d / 'stl' / 'nozzle.stl')
    # Dosyaya giden lüle mesh'i (bellekte, köşe birleştirmesinden önce):
    # kabuklar köşe paylaşmaz, ``split`` her kapalı kabuğu ayrı verir.
    lule_mesh = next(m for ad, m in cad['assembly_meshes']
                     if str(ad).lower() == 'nozzle')
    return {'step': step['nozzle'], 'stl': trimesh.load(yol),
            'stl_kabuklar': lule_mesh.split(only_watertight=False),
            'cad': cad}


def _analitik_mm3(md):
    """Kâhin: örnekleyicinin noktaları + çözümleyicinin eti ile
    pi*int(2*r*w + w^2)dz (doğrusal parçalarda TAM). Profil işlevini
    KULLANMAZ — bağımsız yol."""
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    from hrma.export.cad_visualization import _nozzle_wall_design
    from hrma.export.motor_geometry import normalise_export_geometry
    n, _ = normalise_export_geometry(md)
    pts, _meta = sample_nozzle_inner_contour(n)
    w = _nozzle_wall_design(n)['thickness_m'] * 1000.0
    return sum(math.pi * (w * (r0 + r1) + w * w) * (z1 - z0)
               for (z0, r0), (z1, r1) in zip(pts, pts[1:])), w, pts


@pytest.fixture(scope='module')
def paketler(ornek_md, tmp_path_factory):
    return {tip: _paket(md, tip, tmp_path_factory.mktemp(f'c1_{tip}'))
            for tip, md in ornek_md.items()}


# ===========================================================================
# 1) Profil kuralı
# ===========================================================================
class TestProfilKurali:
    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_ic_et_dis(self, ornek_md, tip):
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        from hrma.export.cad_visualization import (
            _nozzle_wall_design, nozzle_wall_profile)
        from hrma.export.motor_geometry import normalise_export_geometry
        md, _ = normalise_export_geometry(ornek_md[tip])
        pts, _meta = sample_nozzle_inner_contour(md)
        wd = _nozzle_wall_design(md)
        mm = nozzle_wall_profile(md, unit='mm')
        m = nozzle_wall_profile(md, unit='m')
        assert mm['inner'] == [tuple(p) for p in pts]
        assert mm['wall'] == wd['thickness_m'] * 1000.0
        assert m['wall'] == wd['thickness_m']
        assert mm['wall_design']['source'] == wd['source']
        for prof in (mm, m):
            assert len(prof['outer']) == len(prof['inner'])
            for (zi, ri), (zo, ro) in zip(prof['inner'], prof['outer']):
                assert zo == zi
                assert ro == ri + prof['wall']
        for (z, r), (zm, rm) in zip(mm['inner'], m['inner']):
            assert zm == z / 1000.0 and rm == r / 1000.0

    def test_bilinmeyen_birim_reddedilir(self, ornek_md):
        from hrma.export.cad_visualization import nozzle_wall_profile
        with pytest.raises(ValueError, match='unit'):
            nozzle_wall_profile(ornek_md['solid'], unit='cm')

    def test_istasyon_uyusmazligi_step_te_adli_ret(self):
        pytest.importorskip('build123d')
        from hrma.export.step_export import (
            StepExportDataError, _revolve_smooth_nozzle)
        ic = [(0.0, 20.0), (5.0, 12.0), (10.0, 10.0), (30.0, 18.0)]
        dis = [(z + 0.5, r + 3.0) for z, r in ic]
        with pytest.raises(StepExportDataError) as e:
            _revolve_smooth_nozzle(ic, dis, straight_tail=True)
        assert e.value.invalid_fields[0]['reason'] == \
            'contour_profile_not_closed'
        with pytest.raises(StepExportDataError):
            _revolve_smooth_nozzle(ic, dis[:-1], straight_tail=True)


# ===========================================================================
# 2) Tek kaynak: kaynağı değiştir, üç tüketici birlikte değişsin
# ===========================================================================
def test_uc_tuketici_profili_tek_kaynaktan_okur(ornek_md, monkeypatch,
                                                tmp_path):
    """``nozzle_wall_profile`` sınama için ETİ ``ET_ARTISI_MM`` kalınlaştırır.
    STEP katısı, STL katısı ve kütle dökümü bu artışı GÖRMELİ. Üreteçlerden
    biri örnekleyiciyi/et çözümleyicisini yeniden kendisi çağırırsa artışı
    görmez ve bu bekçi kırmızıya döner (ters mutasyon, RAPOR.md)."""
    from hrma.export import cad_visualization as cv
    asil = cv.nozzle_wall_profile

    def kalin(md, unit='mm', require_solved_length=False):
        p = asil(md, unit=unit, require_solved_length=require_solved_length)
        ek = ET_ARTISI_MM * (1.0 if unit == 'mm' else 1e-3)
        wd = dict(p['wall_design'])
        wd['thickness_m'] = wd['thickness_m'] + ET_ARTISI_MM / 1000.0
        return dict(p, wall=p['wall'] + ek, wall_design=wd,
                    outer=[(z, r + p['wall'] + ek) for z, r in p['inner']])

    monkeypatch.setattr(cv, 'nozzle_wall_profile', kalin)
    md = ornek_md['solid']
    _v_an, w, pts = _analitik_mm3(md)
    r_max = max(r for _z, r in pts) + w + ET_ARTISI_MM
    paket = _paket(md, 'solid', tmp_path)
    # STL (+X ekseninde yazılır): y/z zarfı = 2 x en büyük dış yarıçap
    # (32 kesitin köşeleri tam yarıçapta).
    stl_r = float(paket['stl'].extents[1]) / 2.0
    assert stl_r == pytest.approx(r_max, abs=_tol('stl_mm'))
    # STEP: uyarlamalı hacim, kalınlaştırılmış etin kâhinine eşit
    w2 = w + ET_ARTISI_MM
    v_kahin = sum(math.pi * (w2 * (r0 + r1) + w2 * w2) * (z1 - z0)
                  for (z0, r0), (z1, r1) in zip(pts, pts[1:]))
    v_step = _step_hacim_uyarlamali(paket['step'])
    assert abs(v_step / v_kahin - 1.0) <= STEP_KAHIN_BAGIL, (v_step, v_kahin)
    # Kütle dökümü: aynı halka x lüle yoğunluğu
    from hrma.export.motor_geometry import normalise_export_geometry
    n, _ = normalise_export_geometry(md)
    rho, _src = cv._nozzle_density_resolved(n)
    kutle = cv.MotorCADDesigner()._estimate_component_mass('nozzle', n)
    assert kutle == pytest.approx(v_kahin * 1e-9 * rho, rel=1e-9)


@pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
def test_montaj_plani_lulesi_tek_kaynaktan(ornek_md, monkeypatch, tip):
    """V301 CAD-2 kalem 1: montaj planının lülesi (``motor_assembly._lule``)
    da ``nozzle_wall_profile``i okur. Kaynak eti ``ET_ARTISI_MM``
    kalınlaşınca planın et ölçüsü ve dış konturu AYNI artışı görür; plan
    eti kendisi hesaplarsa (eski ``NOZZLE_WALL_GENERATOR_RULE`` kopyası)
    kırmızı."""
    from hrma.export import cad_visualization as cv
    from hrma.export.motor_assembly import build_plan
    from hrma.export.motor_geometry import normalise_export_geometry
    pid = {'solid': 'S09', 'hybrid': 'H10', 'liquid': 'L10'}[tip]
    md = ornek_md[tip]

    def _lule_parcasi():
        plan = _sessiz(build_plan, md, tip)
        return next(p for p in plan['parts'] if p['id'] == pid)

    taban = _lule_parcasi()
    n, _ = normalise_export_geometry(md)
    kaynak = cv.nozzle_wall_profile(n, unit='mm', require_solved_length=True)
    L = taban['geometry']['profile_rz_mm'][0][0] - kaynak['inner'][0][0]
    beklenen = ([[L + z, r] for z, r in kaynak['inner']]
                + [[L + z, r] for z, r in reversed(kaynak['outer'])])
    assert taban['geometry']['profile_rz_mm'] == beklenen
    assert taban['dims']['wall_thickness_mm']['value'] == kaynak['wall']

    asil = cv.nozzle_wall_profile

    def kalin(md_, unit='mm', require_solved_length=False):
        p = asil(md_, unit=unit, require_solved_length=require_solved_length)
        ek = ET_ARTISI_MM * (1.0 if unit == 'mm' else 1e-3)
        return dict(p, wall=p['wall'] + ek,
                    outer=[(z, r + p['wall'] + ek) for z, r in p['inner']])

    monkeypatch.setattr(cv, 'nozzle_wall_profile', kalin)
    parca = _lule_parcasi()
    assert parca['dims']['wall_thickness_mm']['value'] == pytest.approx(
        kaynak['wall'] + ET_ARTISI_MM, abs=1e-12)
    prof = parca['geometry']['profile_rz_mm']
    n_ic = len(kaynak['inner'])
    dis = list(reversed(prof[n_ic:]))
    for (x_i, r_i), (x_d, r_d) in zip(prof[:n_ic], dis):
        assert x_d == x_i
        assert r_d - r_i == pytest.approx(kaynak['wall'] + ET_ARTISI_MM,
                                          abs=1e-9)


# ===========================================================================
# 3) Hacim eşitliği — üç örnek motor
# ===========================================================================
@pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
class TestHacimEsitligi:
    def test_step_ile_stl_ayni_lule(self, paketler, tip):
        v_step = _step_hacim_uyarlamali(paketler[tip]['step'])
        v_stl = float(paketler[tip]['stl'].volume)
        assert abs(v_stl / v_step - 1.0) <= _tol('hacim_bagil'), (
            f'{tip}: STEP {v_step:.0f} mm³ ⟷ STL {v_stl:.0f} mm³')

    def test_step_kahine_esit(self, ornek_md, paketler, tip):
        v_an, _w, _pts = _analitik_mm3(ornek_md[tip])
        v_step = _step_hacim_uyarlamali(paketler[tip]['step'])
        assert abs(v_step / v_an - 1.0) <= STEP_KAHIN_BAGIL, (v_step, v_an)

    def test_stl_kahinin_tam_kesit_kati(self, ornek_md, paketler, tip):
        v_an, _w, _pts = _analitik_mm3(ornek_md[tip])
        v_stl = float(paketler[tip]['stl'].volume)
        # V301 CAD-2 kalem 8: iki katmanlı ceketli lüle STL'de iki kapalı
        # kabuktur (astar + kanal katmanı, dış kabuk; ara yüzde değerler).
        # Okuyucu çakışan köşeleri birleştirdiğinde ara yüz kenarı dört
        # yüzlü görünür; kapalılık her kabukta AYRI sınanır. Toplam hacim
        # kabukların işaretli hacmidir (ara yüz zıt yönlü, zarf kalır).
        kabuklar = paketler[tip]['stl_kabuklar']
        assert kabuklar and all(k.is_watertight for k in kabuklar)
        assert v_stl / v_an == pytest.approx(STL_COKGEN_KATSAYISI,
                                             abs=STL_COKGEN_BAGIL)

    def test_readme_notu_varsayilan_sapmayi_eksik_soylemez(self, paketler,
                                                         tip):
        """STEP README hacim notu (``STEP_NOZZLE_VOLUME_NOTE``) örnek
        lülelerde varsayılan okuyucunun sapmasını yazar; notun sayısı
        ölçülenden KÜÇÜK olamaz (kullanıcı uyarısı eksik kalmasın)."""
        from build123d import import_step
        from hrma.export.step_export import (
            STEP_NOZZLE_DEFAULT_VOLUME_ERROR_EXAMPLES_PCT as NOT_PCT,
            STEP_NOZZLE_VOLUME_NOTE)
        yol = paketler[tip]['step']
        v_def = sum(k.volume for k in import_step(yol).solids())
        v_ad = _step_hacim_uyarlamali(yol)
        sapma_pct = 100.0 * (v_def / v_ad - 1.0)
        assert sapma_pct <= NOT_PCT[tip] + NOT_YUVARLAMA_PCT, (
            f'{tip}: varsayılan okuyucu +{sapma_pct:.3f} %, notta '
            f'+{NOT_PCT[tip]:.2f} %')
        assert f'{NOT_PCT[tip]:.2f}' in STEP_NOZZLE_VOLUME_NOTE[0]
        assert f'{NOT_PCT[tip]:.2f}'.replace('.', ',') in \
            STEP_NOZZLE_VOLUME_NOTE[1]


# ===========================================================================
# 5) V301 CAD-2 kalem 6 — DXF lülesi tek kaynaktan, dış duvar çizili
# ===========================================================================
def _ayni_noktalar(a, b, tol=1e-9):
    """İki nokta dizisi aynı uzunlukta ve her koordinat ``tol`` içinde."""
    a = [tuple(map(float, p)) for p in a]
    b = [tuple(map(float, p)) for p in b]
    assert len(a) == len(b), (len(a), len(b))
    fark = max(max(abs(p[0] - q[0]), abs(p[1] - q[1])) for p, q in zip(a, b))
    assert fark <= tol, fark


def _dxf_lule(md, yol):
    ezdxf = pytest.importorskip('ezdxf')
    from hrma.export.drawing_generator import generate_dxf
    doc = ezdxf.readfile(_sessiz(generate_dxf, md, str(yol)))
    katman = {}
    for e in doc.modelspace():
        if e.dxftype() == 'LWPOLYLINE':
            katman.setdefault(e.dxf.layer, []).append(
                [tuple(p) for p in e.get_points('xy')])
    metin = [e.dxf.text for e in doc.modelspace() if e.dxftype() == 'TEXT']
    return katman, metin


@pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
def test_dxf_lule_dis_duvari_profilden(ornek_md, tmp_path, tip):
    """DXF lüle iç konturu ve DIŞ duvarı ``nozzle_wall_profile``in
    noktalarıdır (aynı istasyon, aynı et); giriş ve çıkış yüzleri iç ile dış
    konturu kapatır; ``NOZZLE WALL:`` satırı çizileni ve kaynağı söyler."""
    from hrma.export.cad_visualization import nozzle_wall_profile
    from hrma.export.drawing_generator import DXF_NOZZLE_WALL_LAYER
    from hrma.export.motor_geometry import normalise_export_geometry
    md = ornek_md[tip]
    katman, metin = _dxf_lule(md, tmp_path / 'k6.dxf')
    n, _ = normalise_export_geometry(md)
    prof = nozzle_wall_profile(n, unit='mm')
    kontur = max(katman['CONTOUR'], key=len)
    L = kontur[1][0] - prof['inner'][0][0]
    ic = [(L + z, r) for z, r in prof['inner']]
    dis = [(L + z, r) for z, r in prof['outer']]
    _ayni_noktalar(kontur[1:], ic)
    duvar = katman.get(DXF_NOZZLE_WALL_LAYER) or []
    ust = [p for p in duvar if len(p) > 2 and p[0][1] > 0]
    alt = [p for p in duvar if len(p) > 2 and p[0][1] < 0]
    assert len(ust) == 1 and len(alt) == 1, duvar
    _ayni_noktalar(ust[0], dis)
    _ayni_noktalar(alt[0], [(x, -r) for x, r in dis])
    yuzler = sorted(tuple(p) for p in duvar if len(p) == 2)
    beklenen = sorted([(ic[0], dis[0]), (ic[-1], dis[-1]),
                       ((ic[0][0], -ic[0][1]), (dis[0][0], -dis[0][1])),
                       ((ic[-1][0], -ic[-1][1]), (dis[-1][0], -dis[-1][1]))])
    assert len(yuzler) == 4
    for a, b in zip(yuzler, beklenen):
        _ayni_noktalar(a, b)
    satir = [t for t in metin if t.startswith('NOZZLE WALL:')]
    assert len(satir) == 1, satir
    assert 'DRAWN in this view' in satir[0]
    assert f"{prof['wall']:.2f} mm" in satir[0]
    assert prof['wall_design']['source'] in satir[0]
    assert 'belongs to the chamber only' in satir[0]


def test_dxf_lule_tek_kaynaktan_okur(ornek_md, monkeypatch, tmp_path):
    """Kaynak eti ``ET_ARTISI_MM`` kalınlaşınca DXF lüle duvarı da
    kalınlaşır; DXF örnekleyiciyi/et kuralını kendisi çağırırsa kırmızı."""
    from hrma.export import cad_visualization as cv
    from hrma.export.drawing_generator import DXF_NOZZLE_WALL_LAYER
    md = ornek_md['solid']
    k0, _ = _dxf_lule(md, tmp_path / 'a.dxf')
    asil = cv.nozzle_wall_profile

    def kalin(md_, unit='mm', require_solved_length=False):
        p = asil(md_, unit=unit, require_solved_length=require_solved_length)
        ek = ET_ARTISI_MM * (1.0 if unit == 'mm' else 1e-3)
        return dict(p, wall=p['wall'] + ek,
                    outer=[(z, r + p['wall'] + ek) for z, r in p['inner']])

    monkeypatch.setattr(cv, 'nozzle_wall_profile', kalin)
    k1, _ = _dxf_lule(md, tmp_path / 'b.dxf')
    u0 = max(k0[DXF_NOZZLE_WALL_LAYER], key=len)
    u1 = max(k1[DXF_NOZZLE_WALL_LAYER], key=len)
    u0 = u0 if u0[0][1] > 0 else [(x, -r) for x, r in u0]
    u1 = u1 if u1[0][1] > 0 else [(x, -r) for x, r in u1]
    for (x0, r0), (x1, r1) in zip(u0, u1):
        assert x1 == x0
        assert r1 - r0 == pytest.approx(ET_ARTISI_MM, abs=1e-9)
