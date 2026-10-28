"""Faz 4B — dışa aktarım geometrisi ve birim bekçileri.

Kapatılan ölçülmüş kusurlar (denetim defteri: docs/FAZ4_CODEX_TEYIT.md):

* **A1** — STL METRE yazılıyordu, aynı parçanın STEP'i mm idi. Ölçüldü: aynı
  ZIP'te STEP zarfı 1069.62 mm, STL zarfı 1.0696. 1000× birim hatası.
* **A2** — DXF başlığı ``$INSUNITS = 6`` (METRE) idi, geometri mm. ezdxf'in
  ``new(setup=True)`` varsayılanı 6'dır ve depoda hiçbir yerde eziliyordu
  (``grep -rn INSUNITS`` -> boş).
* **A5** — Lüle ıraksak boyu bell konturda %42 kısa çıkıyordu: ortak geometri
  sözlüğü boyu hiç taşımıyor, tüketici de ``divergent_half_angle_deg``i
  (bell'de BOĞAZ açısı: 30° / 34°) konik yarı açı sanıyordu. Ölçüldü
  (10 kN sıvı motor): bell_80 çözücü 107.69 / export 62.48 mm (-41.99%),
  bell_60 80.77 / 53.48 mm (-33.79%), konik +0.78%.
* **A8** — Katı motor kasa cidarı imalata farklı gidiyordu: STEP katıda hiç
  yayımlanmayan ``chamber_analysis`` anahtarını arıyor, bulamayınca
  ``0.045·D_ch`` yedeğine düşüyordu. Ölçüldü (Ø100 mm): analiz 2.40 mm,
  STEP 4.50 mm.
* **A10** — ``export_stl_files``in döndürdüğü yolların sözleşmesi.
* **D1** — Eşzamanlı export'lar birbirinin dosyasını veriyordu (zaman damgalı
  ad + ``exist_ok=True``, üretimde waitress ``threads=8``).
* **D10** — /tmp birikmesi: 77 dizin / 17 MB, temizlik yolu yok.

Bu dosyadaki her sayı ÖLÇÜMDÜR; hiçbir beklenti elle uydurulmuş değildir.
"""

from __future__ import annotations

import contextlib
import io
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM

from hrma.engines.nozzle_design import sample_nozzle_inner_contour
from hrma.export import export_workspace
from hrma.export.cad_visualization import (
    MotorCADDesigner, _chamber_wall_thickness_m)
from hrma.export.motor_geometry import (
    liquid_results_to_motor_geometry, solid_results_to_motor_geometry)


# ---------------------------------------------------------------------------
# Gerçek çözümler — uydurma sözlük yok
# ---------------------------------------------------------------------------

def _quiet(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar, sonucu döndürür."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def hybrid_results():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    r = _quiet(HybridRocketEngine(
        thrust=3000, burn_time=10, of_ratio=7.96, chamber_pressure=20,
        fuel_type='paraffin', oxidizer_type='n2o', fuel_density=900,
        regression_a=1.17e-4, regression_n=0.62, expansion_ratio=0).calculate)
    r['motor_name'] = 'FAZ4B_HYBRID'
    return r


@pytest.fixture(scope='module')
def solid_results():
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    # v3.0.1 T-ÇAPA-B: eski çekirdek 30 mm @ 40 bar port boğulan motordu
    # (A_p/A_t 0,947); K-A kapısından beri 422. Konu port değil: geometri
    # tek tanım SOLID_DEFAULT_GEOMETRY_MM'den (kopyalanmaz).
    r = _quiet(SolidRocketEngine(
        **SOLID_DEFAULT_GEOMETRY_MM,
        chamber_pressure=40).calculate_performance)
    r['motor_name'] = 'FAZ4B_SOLID'
    return r


@pytest.fixture(scope='module')
def liquid_results_by_type():
    """nozzle_type -> gerçek /calculate_liquid sonucu (üç kontur tipi)."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    out = {}
    for noz in ('conical', 'bell_80', 'bell_60'):
        r = _quiet(LiquidRocketEngine(
            thrust=10000, chamber_pressure=50, mixture_ratio=2.3,
            overrides={'nozzle_type': noz}).calculate_performance)
        r['motor_name'] = f'FAZ4B_LIQUID_{noz}'
        out[noz] = r
    return out


# ---------------------------------------------------------------------------
# A5 — lüle ıraksak boyu: çözücü ile export aynı olmalı
# ---------------------------------------------------------------------------

class TestA5NozulUzunlugu:
    """Bell lülede export boyu çözücünün boyuyla %1 içinde eşleşmeli."""

    @pytest.mark.parametrize('noz_type', ['bell_80', 'bell_60', 'conical'])
    def test_export_divergent_length_matches_solver(
            self, liquid_results_by_type, noz_type):
        r = liquid_results_by_type[noz_type]
        solver_mm = r['nozzle_angles']['nozzle_length_mm']  # ıraksak boy (mm)
        geo = liquid_results_to_motor_geometry(r)
        _pts, meta = sample_nozzle_inner_contour(geo)
        export_mm = meta['z_exit'] - meta['z_throat']
        rel = abs(export_mm / solver_mm - 1.0)
        assert rel < 0.01, (
            f'{noz_type}: çözücü {solver_mm:.2f} mm, export {export_mm:.2f} mm '
            f'({100 * (export_mm / solver_mm - 1):+.2f}%). Bell lülede '
            "'divergent_half_angle_deg' BOĞAZ açısıdır, konik yarı açı değil.")

    def test_normalised_geometry_carries_the_solver_length(
            self, liquid_results_by_type, solid_results):
        """Ortak geometri sözlüğü lüle boyunu METRE olarak taşımalı."""
        geo = liquid_results_to_motor_geometry(
            liquid_results_by_type['bell_80'])
        assert 'nozzle_divergent_length' in geo, (
            'sıvı motor geometrisi ıraksak lüle boyunu taşımıyor — tüketici '
            'boyu yeniden türetmek zorunda kalır (A5 kökü)')
        assert geo['nozzle_divergent_length'] * 1000.0 == pytest.approx(
            liquid_results_by_type['bell_80']['nozzle_angles'][
                'nozzle_length_mm'], rel=1e-9)

        geo_s = solid_results_to_motor_geometry(solid_results)
        assert geo_s['nozzle_divergent_length'] * 1000.0 == pytest.approx(
            solid_results['nozzle_angles']['divergent_length_mm'], rel=1e-9)
        assert geo_s['nozzle_convergent_length'] * 1000.0 == pytest.approx(
            solid_results['nozzle_angles']['convergent_length_mm'], rel=1e-9)

    def test_unsolved_length_is_declared_not_invented(self):
        """Boy hesaplanmadıysa kaynak alanı bunu AÇIKÇA söylemeli."""
        bare = {'chamber_diameter': 0.1, 'throat_diameter': 0.03,
                'exit_diameter': 0.09,
                'nozzle_angles': {'nozzle_type': 'bell_80'}}
        _pts, meta = sample_nozzle_inner_contour(bare)
        assert meta['divergent_length_source'].startswith('NOT SOLVED'), (
            'çözücü boyu vermediğinde kaynak alanı bunu bildirmeli, '
            f"bulunan: {meta['divergent_length_source']!r}")

    def test_bell_fallback_does_not_use_the_throat_angle_as_a_cone_angle(self):
        """Yedek yol boğaz açısını konik yarı açı olarak KULLANMAMALI.

        Ölçüm: rt=15 mm, re=45 mm. Boğaz açısı 30° sanılırsa boy
        (45-15)/tan(30°) = 51.96 mm çıkar; doğru model %80 bell için
        0.80 x (45-15)/tan(15°) = 89.57 mm'dir.
        """
        bare = {'chamber_diameter': 0.1, 'throat_diameter': 0.030,
                'exit_diameter': 0.090,
                'nozzle_angles': {'nozzle_type': 'bell_80'}}
        _pts, meta = sample_nozzle_inner_contour(bare)
        drawn = meta['z_exit'] - meta['z_throat']
        wrong = (45.0 - 15.0) / math.tan(math.radians(30.0))
        expected = 0.80 * (45.0 - 15.0) / math.tan(math.radians(15.0))
        assert abs(drawn - wrong) > 1.0, (
            f'ıraksak boy {drawn:.2f} mm — boğaz açısı hâlâ konik yarı açı '
            'olarak kullanılıyor')
        assert drawn == pytest.approx(expected, rel=0.02), (
            f'ıraksak boy {drawn:.2f} mm, %80 bell modeli {expected:.2f} mm')

    def test_manufacturing_path_refuses_an_unsolved_length(self):
        """require_solved_length: hesaplanmamış boyla katı model üretilmez."""
        bare = {'chamber_diameter': 0.1, 'throat_diameter': 0.03,
                'exit_diameter': 0.09,
                'nozzle_angles': {'nozzle_type': 'bell_80'}}
        with pytest.raises(ValueError, match='divergent length'):
            sample_nozzle_inner_contour(bare, require_solved_length=True)

    def test_conical_angle_derivation_is_accepted_by_the_gate(self):
        """Konikte açı ile boy aynı bilgidir — kapı bunu reddetmemeli."""
        bare = {'chamber_diameter': 0.1, 'throat_diameter': 0.03,
                'exit_diameter': 0.09,
                'nozzle_angles': {'nozzle_type': 'conical'}}
        _pts, meta = sample_nozzle_inner_contour(bare,
                                                require_solved_length=True)
        assert meta['divergent_length_source'].startswith('derived')


# ---------------------------------------------------------------------------
# A8 — kasa/kamara cidarı: üç motor tipinin üç ayrı şeması
# ---------------------------------------------------------------------------

class TestA8CidarKalinligi:
    def test_solid_case_wall_reaches_the_step_generator(self, solid_results):
        """Katı motorun ANALİZ cidarı geometri sözlüğünden okunabilmeli."""
        geo = solid_results_to_motor_geometry(solid_results)
        wall_m, source = _chamber_wall_thickness_m(geo)
        analysis_mm = solid_results['structural_analysis']['case_analysis'][
            'wall_thickness_mm']
        assert wall_m is not None, (
            'katı motor cidarı bulunamadı — STEP 0.045·D uydurmasına düşer')
        assert wall_m * 1000.0 == pytest.approx(analysis_mm, rel=1e-9), (
            f'STEP cidarı {wall_m * 1000:.2f} mm, analiz {analysis_mm:.2f} mm')
        assert 'case_analysis' in source

    def test_liquid_chamber_wall_reaches_the_step_generator(
            self, liquid_results_by_type):
        geo = liquid_results_to_motor_geometry(
            liquid_results_by_type['bell_80'])
        wall_m, source = _chamber_wall_thickness_m(geo)
        analysis_mm = liquid_results_by_type['bell_80'][
            'structural_analysis']['chamber_structure']['wall_thickness']
        assert wall_m is not None
        assert wall_m * 1000.0 == pytest.approx(analysis_mm, rel=1e-9)
        assert 'chamber_structure' in source

    def test_step_is_fail_closed_without_a_structural_result(self):
        """Cidar bilinmiyorsa STEP üretilmez — uydurma yedeğe DÜŞÜLMEZ."""
        pytest.importorskip('build123d')
        from hrma.export.step_export import generate_step_assembly
        bare = {'motor_name': 'NO_STRUCT', 'chamber_diameter': 0.1,
                'chamber_length': 0.3, 'throat_diameter': 0.03,
                'exit_diameter': 0.09,
                'nozzle_angles': {'nozzle_type': 'conical'}}
        with pytest.raises(ValueError, match='wall thickness'):
            generate_step_assembly(bare, motor_type='liquid')

    def test_step_uses_the_analysis_wall_for_a_solid_motor(self, solid_results,
                                                           tmp_path):
        """İmalata giden STEP dış çapı analiz cidarını yansıtmalı.

        Dış yarıçap = iç yarıçap + cidar. Eski kod 0.045·D_ch kullanıyordu;
        Ø100 mm motorda bu 4.50 mm iken analiz 2.40 mm diyordu.
        """
        pytest.importorskip('build123d')
        from build123d import import_step
        from hrma.export.step_export import generate_step_assembly

        geo = solid_results_to_motor_geometry(solid_results)
        files = _quiet(generate_step_assembly, geo,
                       out_dir=str(tmp_path / 'step'), motor_type='solid')
        bb = import_step(files['chamber']).bounding_box()
        outer_d_mm = max(bb.size.Y, bb.size.Z)
        wall_mm = solid_results['structural_analysis']['case_analysis'][
            'wall_thickness_mm']
        expected = geo['chamber_diameter'] * 1000.0 + 2 * wall_mm
        assert outer_d_mm == pytest.approx(expected, rel=1e-6), (
            f'STEP dış çapı {outer_d_mm:.2f} mm; analiz cidarıyla '
            f'{expected:.2f} mm bekleniyordu')


# ---------------------------------------------------------------------------
# A2 — DXF birim başlığı
# ---------------------------------------------------------------------------

def _dxf_katman_kutusu(doc, layer):
    """Bir DXF katmanındaki LWPOLYLINE'ların (xmin, xmax, ymin, ymax)'ı."""
    xs, ys = [], []
    for e in doc.modelspace():
        if e.dxftype() != 'LWPOLYLINE' or e.dxf.layer != layer:
            continue
        for x, y in e.get_points('xy'):
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def _dxf_olcu_sayisi(doc, onek):
    """``'Ø_chamber = 183.3 mm'`` gibi bir ölçü metninden sayıyı çeker."""
    for e in doc.modelspace():
        if e.dxftype() != 'TEXT':
            continue
        text = e.dxf.text
        if text.startswith(onek):
            eslesme = re.search(r'(-?\d+(?:\.\d+)?)\s*mm', text)
            if eslesme:
                return float(eslesme.group(1)), text
    return None, None


class TestA2DxfBirimi:
    def test_insunits_is_millimetres(self, hybrid_results, tmp_path):
        ezdxf = pytest.importorskip('ezdxf')
        from hrma.export.drawing_generator import (
            DXF_INSUNITS_MILLIMETERS, generate_dxf)
        path = generate_dxf(hybrid_results, str(tmp_path / 'a2.dxf'))
        doc = ezdxf.readfile(path)
        assert doc.header.get('$INSUNITS') == DXF_INSUNITS_MILLIMETERS == 4, (
            f"$INSUNITS = {doc.header.get('$INSUNITS')} — 4 (mm) bekleniyordu; "
            'ezdxf varsayılanı 6 (metre) ve geometri mm')

    def test_geometry_is_consistent_with_the_declared_unit(
            self, hybrid_results, tmp_path):
        """Beyan mm ise KOORDİNATLAR da mm olmalı — X **ve** Y ekseninde.

        ÖH B-1/B16 (defter P14M1-03). Bu bekçi eskiden yalnız X açıklığını
        okuyordu ve bandı ``50 < span < 5000`` idi: 100 kat genişlikte bir
        bant, üstelik dış cidar poliçizgisi Y'de yaşadığı için cidar 2×
        büyütüldüğünde 633 test yeşil kalıyordu (mutasyonla ölçüldü).
        İddia artık çizimin KENDİ ölçü metinlerine çapalanır — imalatçının
        eline geçen dosyada sayı ile geometri aynı şeyi söylemek zorunda:

          * ``Ø_chamber`` metni  ⟷  CONTOUR katmanının Y açıklığı
          * ``L_chamber`` metni   ⟷  CONTOUR katmanının X açıklığı
            (lüle eklendiği için X açıklığı boydan büyük, 3 katından küçük)

        Metre yazılsaydı Ø_chamber metni 183,3 mm derken geometri 0,1833
        çıkardı; her iki çapraz da kırılır.
        """
        ezdxf = pytest.importorskip('ezdxf')
        from hrma.export.drawing_generator import generate_dxf
        doc = ezdxf.readfile(generate_dxf(hybrid_results,
                                          str(tmp_path / 'a2b.dxf')))

        cap_mm, cap_metni = _dxf_olcu_sayisi(doc, 'Ø_chamber')
        boy_mm, boy_metni = _dxf_olcu_sayisi(doc, 'L_chamber')
        assert cap_mm and boy_mm, (
            'çizimde Ø_chamber / L_chamber ölçü metni yok — geometri '
            'karşılaştırılacak bir beyan taşımıyor')

        kontur = _dxf_katman_kutusu(doc, 'CONTOUR')
        assert kontur is not None, 'CONTOUR katmanında poliçizgi yok'
        xmin, xmax, ymin, ymax = kontur

        # Y: iç akış yolunun en geniş yeri kamara çapıdır (metinle aynı sayı).
        assert (ymax - ymin) == pytest.approx(cap_mm, abs=0.1), (
            f'kontur Y açıklığı {ymax - ymin:.4f}, çizimin kendi ölçüsü '
            f'{cap_metni!r} — sayı ile geometri aynı birimde değil')
        assert ymax == pytest.approx(-ymin, rel=1e-9), 'kontur eksene simetrik değil'

        # X: kamara + lüle. Boydan küçük olamaz, 3 katını da geçemez.
        span = xmax - xmin
        assert boy_mm <= span < 3.0 * boy_mm, (
            f'çizim X açıklığı {span:.2f} mm; çizimin kendi ölçüsü '
            f'{boy_metni!r} (metre olsaydı açıklık < 1 çıkardı)')

    def test_outer_wall_polyline_matches_the_wall_thickness_dimension(
            self, hybrid_results, tmp_path):
        """Dış cidar poliçizgisi ``WALL THICKNESS`` ölçüsüyle AYNI olmalı.

        ÖH B-1/B16 (defter P14M1-03). Mutasyon ölçümü: dış cidar
        poliçizgisi 2× büyütüldüğünde 633 test yeşil kaldı, çünkü tek DXF
        bekçisi yalnız X açıklığını okuyordu ve cidar Y'de yaşıyor.
        Burada üç bacak birden kilitlenir:

          1. çizimde bir ``WALL THICKNESS`` ölçüsü VAR (sessiz atlama yok),
          2. OUTLINE katmanının Y yarı-açıklığı = iç konturun yarıçapı +
             o ölçü,
          3. aradaki fark, ölçünün kendi yazım hassasiyetinden (2 ondalık,
             yani ±0,005 mm) büyük olamaz.

        (2) tek başına cidarın poliçizgi tarafındaki her ölçek hatasını
        yakalar; ölçü metnindeki sayının analizden geldiğini kardeş test
        ``test_wall_thickness_dimension_carries_the_analysis_value`` sınar.

        Bu dalgada yeniden ölçüldü (yalnız OUTLINE poliçizgisinin y'si 2×):
        HEAD bekçileriyle 77 test **hepsi yeşil**; bu iki bekçiyle 2 kırmızı.
        """
        ezdxf = pytest.importorskip('ezdxf')
        from hrma.export.drawing_generator import generate_dxf
        doc = ezdxf.readfile(generate_dxf(hybrid_results,
                                          str(tmp_path / 'a2c.dxf')))

        cidar_mm, cidar_metni = _dxf_olcu_sayisi(doc, 'WALL THICKNESS')
        assert cidar_mm is not None, (
            'çizimde WALL THICKNESS ölçüsü yok — imalatçı et kalınlığını '
            'poliçizgiden ölçmek zorunda kalır')

        kontur = _dxf_katman_kutusu(doc, 'CONTOUR')
        dis = _dxf_katman_kutusu(doc, 'OUTLINE')
        assert dis is not None, (
            'OUTLINE katmanında poliçizgi yok — dış cidar çizilmemiş')
        ic_yaricap = kontur[3]
        _xmin, _xmax, ymin, ymax = dis
        beklenen = ic_yaricap + cidar_mm
        assert ymax == pytest.approx(beklenen, abs=0.005), (
            f'dış cidar poliçizgisi ±{ymax:.4f} mm konumunda; iç kontur '
            f'{ic_yaricap:.4f} + ölçü {cidar_mm:.4f} = {beklenen:.4f} mm '
            f'diyor ({cidar_metni!r})')
        assert ymax == pytest.approx(-ymin, rel=1e-9), (
            'dış cidar eksene simetrik değil')

    def test_wall_thickness_dimension_carries_the_analysis_value(self, tmp_path):
        """Ölçü metnindeki cidar, YAPISAL ANALİZİN as-designed kalınlığıdır.

        ÖH B-1/B16. Doğrulama (``verify``) modunda kullanıcının GERÇEK
        cidarı çizilir, yazılımın önerdiği kalınlık DEĞİL: gerilmeler ve
        emniyet katsayıları o kalınlığa aittir. Fikstür iki sayıyı bilerek
        AYIRIR (3,00 ⟷ 7,50 mm); eşit verilseydi hangisinin çizildiği
        ölçülemezdi — P14M1-03/-07'nin kökü tam olarak buydu.
        """
        ezdxf = pytest.importorskip('ezdxf')
        from hrma.export.drawing_generator import generate_dxf
        payload = _dxf_payload(0.120, 0.030)
        payload['structural_analysis'] = {
            'chamber_analysis': {'design_mode': 'verify',
                                 'wall_thickness_used_mm': 3.0,
                                 'recommended_thickness': 7.5}}
        doc = ezdxf.readfile(generate_dxf(payload, str(tmp_path / 'a2d.dxf')))

        cidar_mm, cidar_metni = _dxf_olcu_sayisi(doc, 'WALL THICKNESS')
        assert cidar_mm == pytest.approx(3.0, abs=1e-6), (
            f'ölçü {cidar_metni!r} — doğrulama modunda as-designed 3,00 mm '
            'çizilmeliydi; 7,50 mm yazıyorsa öneri çiziliyor demektir')
        dis = _dxf_katman_kutusu(doc, 'OUTLINE')
        assert dis[3] == pytest.approx(60.0 + 3.0, abs=1e-6), (
            f'dış cidar ±{dis[3]:.4f} mm — Ø120 mm kamarada 63,00 bekleniyordu')


# ---------------------------------------------------------------------------
# A1 — STL birimi STEP ile aynı olmalı
# ---------------------------------------------------------------------------

#: ÖH B-1/ÖK-13: zarflar artık İKİ parçadan okunur. Tek parça (``chamber``)
#: okumak, aynı ZIP'teki başka bir parçanın ayrışmasını görünmez kılıyordu
#: (P15B4-03'ün adresi ``fuel_grain``). İkisi de STEP ve STL'de aynı adla var.
STL_STEP_KARSILASTIRILAN_PARCALAR = ('chamber', 'fuel_grain')


class TestA1StlBirimi:
    @pytest.fixture(scope='class')
    def both_exports(self, hybrid_results, tmp_path_factory):
        """STEP ve STL zarfları — EKSEN KİMLİĞİ KORUNARAK.

        ÖH B-1 / ÖK-13 (P15-K2, defter P15B4-02). Bu fikstür eskiden iki
        zarfı da ``sorted()`` ile döndürüyordu: ölçümden ÖNCE hangi
        büyüklüğün hangi eksende olduğu siliniyordu. Ölçüldü (H1): STEP
        kamarayı X ekseninde, STL Z ekseninde yayımlıyor — sıralanmış
        üçlüler birebir aynı olduğu için 90° dönüklük yapısal olarak
        görünmezdi ve eksen onarımı da TERS onarım da yeşil kalırdı.
        Sıralama artık iddianın kendisinde, açıkça yapılır.

        Döner: {parça: (STEP (X,Y,Z), STL (X,Y,Z))}, STL yol listesi
        """
        pytest.importorskip('build123d')
        trimesh = pytest.importorskip('trimesh')
        from build123d import import_step
        from hrma.export.step_export import generate_step_assembly

        out = tmp_path_factory.mktemp('a1')
        step_files = _quiet(generate_step_assembly, hybrid_results,
                            out_dir=str(out / 'step'))
        designer = MotorCADDesigner()
        cad = _quiet(designer.generate_3d_motor_assembly, dict(hybrid_results))
        stl_files = _quiet(designer.export_stl_files, cad['assembly_meshes'],
                           output_dir=str(out / 'stl'))

        zarflar = {}
        for parca in STL_STEP_KARSILASTIRILAN_PARCALAR:
            stl_path = os.path.join(str(out / 'stl'), parca + '.stl')
            assert parca in step_files, f'STEP paketinde {parca} yok'
            assert os.path.exists(stl_path), f'STL paketinde {parca} yok'
            bb = import_step(step_files[parca]).bounding_box()
            mesh = trimesh.load(stl_path)
            zarflar[parca] = ((float(bb.size.X), float(bb.size.Y),
                               float(bb.size.Z)),
                              tuple(float(v) for v in mesh.extents))
        return zarflar, stl_files

    def test_step_and_stl_have_the_same_dimensions(self, both_exports):
        """Aynı parçanın iki dosyası aynı ÖLÇÜLERİ taşımalı (1000× bekçisi).

        Bu iddia bilerek EKSEN KÖRDÜR ve körlüğü burada beyan edilir: yalnız
        ölçü kümesini (A1'in birim hatası) sınar, yönelimi kardeş test
        ``test_step_and_stl_use_the_same_axis_convention`` sınar. Sıralama
        fikstürde değil, iddianın içinde yapılır (ÖK-13).
        """
        zarflar, _paths = both_exports
        for parca, (step_xyz, stl_xyz) in zarflar.items():
            for step_mm, stl_mm in zip(sorted(step_xyz), sorted(stl_xyz)):
                assert stl_mm == pytest.approx(step_mm, rel=0.01), (
                    f'{parca}: STEP {step_mm:.3f} mm, STL {stl_mm:.3f} — STL '
                    'hâlâ metre yazıyor olabilir (1000× birim hatası)')

    def test_step_and_stl_use_the_same_axis_convention(self, both_exports):
        """Aynı parçanın STEP ve STL'i AYNI eksende uzamalı.

        Ölçüldü (P15/H1, hibrit): chamber STEP (358,674; 221,592; 221,592)
        ⟷ STL (221,592; 221,592; 358,674) — sayılar birebir, eksen 90°
        dönük. Aynısı fuel_grain'de de var. Montajı bu iki dosyadan kuran
        kullanıcı parçaları çakıştıramaz.

        ÖH D26 / defter P15B4-01 — BORÇ İMİ KALDIRILDI. Bu iddia
        ``xfail(strict=True)`` ile "kusur ölçüldü, onarılmadı" diye
        duruyordu. Ayrışma üç motorun beş parçasında yeniden ölçüldü
        (``raw/OH/D26/ihracat/a1/once.json`` -> ``P15B4-01``,
        ``ayrisan_parca_sayisi = 5``) ve kapatıldı: paketin tek eksen
        sözleşmesi ``motor_geometry.EXPORT_AXIS`` (+X) oldu,
        ``export_stl_files`` dosyaya yazdığı kopyayı o sözleşmeye çevirir.
        Onarımdan sonra ``ayrisan_parca_sayisi = 0``.
        """
        zarflar, _paths = both_exports
        for parca, (step_xyz, stl_xyz) in zarflar.items():
            # İDDİANIN KENDİSİ: üç bileşen AYNI SIRADA eşleşmeli. Kardeş
            # iddia (test_step_and_stl_have_the_same_dimensions) sıralanmış
            # üçlüleri kıyaslar ve eksen körüdür; 90° dönüklüğü yalnız bu
            # sırasız kıyas görür.
            for eksen, step_mm, stl_mm in zip('XYZ', step_xyz, stl_xyz):
                assert stl_mm == pytest.approx(step_mm, rel=0.01), (
                    f'{parca}: {eksen} ekseninde STEP {step_mm:.3f} mm, '
                    f'STL {stl_mm:.3f} mm — iki dosya 90° dönük olabilir '
                    f'(STEP {step_xyz}, STL {stl_xyz})')
            # "EN UZUN EKSEN" kıyası YALNIZ ayırt edici olduğunda yapılır.
            # ÖH D26 / P15B4-01 onarımında ölçüldü: hibrit ``fuel_grain``
            # zarfı (182,889; 184,330; 184,330) mm — en büyük bileşen bir
            # ÇAP, üstelik iki çap birbirine eşit. ``list.index(max(...))``
            # böyle bir üçlüde ekseni kayan-nokta gürültüsüyle seçer (STEP
            # üçlüsünde iki çap 3e-14 ayrışıyordu -> 'Z', STL üçlüsünde tam
            # eşit -> 'Y') ve iki dosya BİREBİR ÇAKIŞIKKEN bile ayrı eksen
            # raporlanıyordu. Ayırt edicilik eşiği: en büyük bileşen
            # ikincisinden en az %1 uzun olmalı (kıyasın kendi rel=0.01
            # toleransı).
            for ad, xyz in (('STEP', step_xyz), ('STL', stl_xyz)):
                sirali = sorted(xyz, reverse=True)
                if sirali[0] <= sirali[1] * 1.01:
                    break
            else:
                step_eksen = 'XYZ'[step_xyz.index(max(step_xyz))]
                stl_eksen = 'XYZ'[stl_xyz.index(max(stl_xyz))]
                assert step_eksen == stl_eksen, (
                    f'{parca}: STEP en uzun eksen {step_eksen}, STL '
                    f'{stl_eksen} — STEP {step_xyz}, STL {stl_xyz}')

    def test_stl_is_not_metres(self, both_exports):
        zarflar, _paths = both_exports
        for parca, (_step_xyz, stl_xyz) in zarflar.items():
            assert max(stl_xyz) > 10.0, (
                f'{parca}: en büyük STL zarfı {max(stl_xyz):.4f} — mm '
                'bekleniyordu, metre bulundu')

    def test_export_returns_real_absolute_paths(self, both_exports):
        """A10 sözleşmesi: dönen yollar mutlak ve GERÇEKTEN var olmalı."""
        _zarflar, paths = both_exports
        assert paths, 'STL yolu dönmedi'
        for p in paths:
            assert os.path.isabs(p), f'göreli yol döndü: {p}'
            assert os.path.getsize(p) > 100, f'boş dosya: {p}'
        assert 'motor_assembly' in os.path.basename(paths[0]), (
            'birleşik montaj dosyası listenin başında olmalı')

    def test_source_meshes_are_not_mutated(self, hybrid_results, tmp_path):
        """Ölçekleme KOPYA üzerinde olmalı — Plotly ve kütle dökümü metre."""
        designer = MotorCADDesigner()
        cad = _quiet(designer.generate_3d_motor_assembly, dict(hybrid_results))
        before = {n: float(m.extents.max()) for n, m in cad['assembly_meshes']}
        _quiet(designer.export_stl_files, cad['assembly_meshes'],
               output_dir=str(tmp_path))
        after = {n: float(m.extents.max()) for n, m in cad['assembly_meshes']}
        assert before == after, (
            'çağıranın mesh nesneleri yerinde ölçeklenmiş — 3B görselleştirme '
            've kütle dökümü bozulur')


# ---------------------------------------------------------------------------
# D1 — eşzamanlı üretimde kirlenme yok
# ---------------------------------------------------------------------------

def _dxf_payload(chamber_d_m, throat_d_m):
    """Aynı ADI taşıyan ama FARKLI geometrili iki istek — çakışmanın koşulu."""
    return {
        'motor_name': 'RACE',  # kasıtlı olarak aynı ad
        'chamber_diameter': chamber_d_m, 'chamber_length': 0.4,
        'throat_diameter': throat_d_m, 'exit_diameter': 3 * throat_d_m,
        'nozzle_angles': {'nozzle_type': 'conical'},
        'structural_analysis': {
            'chamber_analysis': {'recommended_thickness': 4.0,
                                 'wall_thickness_used_mm': 4.0,
                                 'design_mode': 'size'}},
    }


class TestD1EszamanliUretim:
    def test_eight_concurrent_dxf_jobs_each_get_their_own_file(self):
        """8 paralel üretimde her çağıran KENDİ geometrisini almalı."""
        pytest.importorskip('ezdxf')
        import ezdxf
        from hrma.export.drawing_generator import generate_dxf

        jobs = []
        for i in range(8):
            # iki farklı motor, dördü A dördü B — hepsi aynı motor_name
            d_ch = 0.100 if i % 2 == 0 else 0.300
            d_t = 0.020 if i % 2 == 0 else 0.060
            jobs.append((i, _dxf_payload(d_ch, d_t), d_ch * 1000.0))

        def run(job):
            idx, payload, expected_d_mm = job
            path = generate_dxf(payload)      # varsayılan yol: kendi dizini
            try:
                doc = ezdxf.readfile(path)
                texts = [e.dxf.text for e in doc.modelspace()
                         if e.dxftype() == 'TEXT']
                got = [t for t in texts if 'Ø_chamber' in t]
                return idx, got[0] if got else '', expected_d_mm, path
            finally:
                export_workspace.cleanup_workspace(os.path.dirname(path))

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run, jobs))

        wrong = [(i, txt) for i, txt, exp, _p in results
                 if f'{exp:.1f} mm' not in txt]
        assert not wrong, (
            f'{len(wrong)} istek kendi geometrisini almadı: {wrong}')
        # Her iş ayrı dizinde olmalı — paylaşılan yol kalmadığının kanıtı
        dirs = {os.path.dirname(p) for _i, _t, _e, p in results}
        assert len(dirs) == len(results), (
            f'{len(results)} iş {len(dirs)} dizin paylaştı — çakışma mümkün')

    def test_default_output_dirs_are_unique_per_call(self, hybrid_results):
        """Aynı saniyedeki iki STEP çağrısı aynı dizine yazmamalı."""
        pytest.importorskip('build123d')
        from hrma.export.step_export import generate_step_assembly
        a = _quiet(generate_step_assembly, hybrid_results)
        b = _quiet(generate_step_assembly, hybrid_results)
        try:
            dir_a = os.path.dirname(a['assembly'])
            dir_b = os.path.dirname(b['assembly'])
            assert dir_a != dir_b, (
                'iki çağrı aynı dizini paylaştı — zaman damgalı ad geri gelmiş')
        finally:
            for files in (a, b):
                export_workspace.cleanup_workspace(
                    os.path.dirname(files['assembly']))


# ---------------------------------------------------------------------------
# D10 — geçici dizin temizliği
# ---------------------------------------------------------------------------

class TestD10GeciciDizinTemizligi:
    def test_stale_hrma_dirs_are_removed(self, tmp_path):
        old = tmp_path / 'hrma_step_old'
        old.mkdir()
        (old / 'x.step').write_text('x', encoding='utf-8')
        stale = time.time() - 48 * 3600
        os.utime(old, (stale, stale))

        fresh = tmp_path / 'hrma_step_fresh'
        fresh.mkdir()

        removed = export_workspace.purge_stale_workspaces(root=str(tmp_path))
        assert str(old) in removed
        assert not old.exists()
        assert fresh.exists(), 'taze dizin silinmemeli'

    def test_foreign_directories_are_never_touched(self, tmp_path):
        """Kullanıcının başka dosyalarına DOKUNULMAZ — yalnız kendi önekimiz."""
        foreign = tmp_path / 'important_user_data'
        foreign.mkdir()
        (foreign / 'thesis.tex').write_text('data', encoding='utf-8')
        stale = time.time() - 100 * 24 * 3600
        os.utime(foreign, (stale, stale))

        removed = export_workspace.purge_stale_workspaces(root=str(tmp_path))
        assert removed == []
        assert (foreign / 'thesis.tex').exists()

    def test_cleanup_refuses_paths_outside_our_prefixes(self, tmp_path):
        foreign = tmp_path / 'not_ours'
        foreign.mkdir()
        assert export_workspace.cleanup_workspace(str(foreign)) is False
        assert foreign.exists()

    def test_unknown_prefix_is_rejected_at_creation(self):
        """Tanınmayan önekle dizin açılamaz — yoksa temizleyici göremez."""
        with pytest.raises(ValueError, match='HRMA_TEMP_PREFIXES'):
            export_workspace.new_workspace('random_prefix_')

    def test_atomic_produce_leaves_no_partial_file_on_failure(self, tmp_path):
        target = tmp_path / 'out.bin'

        def writer(tmp):
            with open(tmp, 'wb') as fh:
                fh.write(b'yarim')
            raise IOError('üretici çöktü')

        with pytest.raises(IOError):
            export_workspace.atomic_produce(str(target), writer)
        assert not target.exists(), 'yarım dosya hedefe taşınmış'
        leftovers = [p for p in os.listdir(tmp_path) if p.startswith('.hrma_tmp_')]
        assert not leftovers, f'geçici dosya kaldı: {leftovers}'
