"""Faz 5B / H4 — çizim birimi ve motor tipine göre çizim içeriği bekçileri.

Kapatılan ÖLÇÜLMÜŞ kusurlar (denetim raporu: H4_birim.md, taban HEAD 9d3728e):

* **H4-1 (KRİTİK)** — Sıvı motorun imalat çiziminde OLMAYAN bir yakıt grain'i
  çiziliyordu. ``drawing_generator._dims_mm`` grain boyu/portu için sabit
  yedek taşıyordu (0.24 m / 0.03 m / 0.05 m); sıvı çift yakıtlı motorda grain
  YOKTUR ve yedekler devreye girip çizime "240 mm boyunda, Ø30→50 mm portlu"
  bir katı yakıt bloğu koyuyordu — ölçü tablosunda gerçek ölçülerle aynı
  sütunda, dayanak beyanı olmadan. Aynı uydurma blok STEP montajına
  (``fuel_grain.step``, 85.22 mm) ve STL'e (95.22 x 95.22 x 47.96 mm) de
  giriyordu.
* **H4-2 (KRİTİK)** — Dışa aktarım ucunun birim sözleşmesi beyansızdı ve
  üreticiler girdiyi KOŞULSUZ metre kabul ediyordu. Ölçüldü, ham
  ``/calculate_solid`` yanıtı doğrudan uca verildiğinde:

      DXF   Ø_chamber = 100000.0 mm (gerçek 100.0), Ø_throat = 47927.25 mm
            (gerçek 47.93), Ø_exit = 116727.68 mm, L_chamber = 300.0
            (gerçek 600.0 — 300 sabit yedekti)
      STEP  montaj zarfı 174992.84 x 98156.57 mm (gerçek 782.68 x 98.16)
      STL   montaj zarfı 126313 x 126313 x 174992 mm (gerçek 126.31 x
            126.31 x 782.69)

  Ham ``/calculate_liquid`` yanıtında ise kamara 1000× büyük, boğaz/çıkış
  doğruydu — yani TEK çizimde iki farklı ölçek. Dosya başlığı yine
  ``$INSUNITS = 4`` ve çizim notu "ALL DIMENSIONS IN MILLIMETRES" diyordu.
* **H4-3 (CİDDİ)** — Rapor PDF'i sıvı motorda boğaz/çıkış çapını 1000× küçük
  basıyordu: ``Throat Diameter 0.03 mm`` (gerçek 28.34), ``Exit Diameter
  0.10 mm`` (gerçek 103.06). Sebep: motorun EN BÜYÜK uzunluk alanına bakıp
  TÜM alanlara tek ölçek uygulanması; sıvı yanıtı aynı sözlükte iki birim
  taşıyor.
* **H4-7 (ORTA)** — Aynı motorun iki kuru kütlesi (%22,8 fark) ve üç lüle
  kütlesi (24,5× fark) beyansız yayımlanıyordu.

Bu dosyadaki her beklenti ÖLÇÜMDÜR; hiçbiri elle uydurulmuş değildir.
"""

from __future__ import annotations

import contextlib
import io
import os

import pytest

from hrma.export.drawing_generator import (
    DrawingGeometryError, _dims_mm, generate_dxf)
from hrma.export.motor_geometry import (
    GRAIN_NOT_IN_RESULT, liquid_results_to_motor_geometry,
    normalise_export_geometry, resolve_grain_m, resolve_length_m,
    solid_results_to_motor_geometry)


def _quiet(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar, sonucu döndürür."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Gerçek çözümler — uydurma sözlük yok. app.py'nin yaptığı gibi normalize
# 'motor_geometry' bloğu sonuca eklenir (app.py:2522, :2655).
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def hybrid_results():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    r = _quiet(HybridRocketEngine(
        thrust=2000, burn_time=10, of_ratio=6.0, chamber_pressure=20,
        fuel_type='htpb', oxidizer_type='n2o').calculate)
    r['motor_name'] = 'FAZ5_HYBRID'
    return r


@pytest.fixture(scope='module')
def solid_results():
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    r = _quiet(SolidRocketEngine(
        chamber_diameter=100, grain_length=500, core_diameter=30,
        chamber_pressure=40).calculate_performance)
    r['motor_name'] = 'FAZ5_SOLID'
    r['motor_geometry'] = solid_results_to_motor_geometry(r)
    return r


@pytest.fixture(scope='module')
def liquid_results():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    r = _quiet(LiquidRocketEngine(
        thrust=10000, chamber_pressure=100,
        mixture_ratio=2.5).calculate_performance)
    r['motor_name'] = 'FAZ5_LIQUID'
    r['motor_geometry'] = liquid_results_to_motor_geometry(r)
    return r


def _dxf_body_bbox(path):
    """CONTOUR + OUTLINE katmanlarının zarfı (mm). Metin katmanı sayılmaz."""
    import ezdxf
    doc = ezdxf.readfile(path)
    xs, ys = [], []
    for e in doc.modelspace():
        if e.dxf.layer not in ('CONTOUR', 'OUTLINE'):
            continue
        if e.dxftype() == 'LWPOLYLINE':
            for p in e.get_points('xy'):
                xs.append(p[0])
                ys.append(p[1])
    assert xs, 'çizimde hiç gövde geometrisi yok'
    return max(xs) - min(xs), max(ys) - min(ys)


def _dxf_texts(path):
    import ezdxf
    doc = ezdxf.readfile(path)
    return [e.dxf.text for e in doc.modelspace() if e.dxftype() == 'TEXT']


# ---------------------------------------------------------------------------
# H4-2 — birim sözleşmesi tek noktada çözülür
# ---------------------------------------------------------------------------

class TestH4_2BirimSozlesmesi:

    def test_solid_raw_result_resolves_to_metres(self, solid_results):
        """Katı rotası mm döndürür; çözüm SI metre vermeli."""
        md, report = normalise_export_geometry(solid_results)
        geo = solid_results['motor_geometry']
        assert md['chamber_diameter'] == pytest.approx(
            geo['chamber_diameter'], rel=1e-12)
        assert md['chamber_length'] == pytest.approx(
            geo['chamber_length'], rel=1e-12)
        assert md['throat_diameter'] == pytest.approx(
            geo['throat_diameter'], rel=1e-12)
        assert md['length_units'] == 'm'
        assert report['fields']['chamber_diameter'] == 'motor_geometry'

    def test_liquid_mixed_units_are_resolved_per_field(self, liquid_results):
        """Sıvı yanıtı AYNI sözlükte iki birim taşır; ikisi de doğru çözülmeli.

        Ölçüldü (10 kN LOX/RP-1): chamber_diameter/chamber_length MM,
        throat_diameter/exit_diameter METRE yayımlanıyor.
        """
        raw_d = float(liquid_results['chamber_diameter'])
        raw_t = float(liquid_results['throat_diameter'])
        assert raw_d > 10.0, 'ölçüm değişti: kamara çapı artık mm değil'
        assert raw_t < 1.0, 'ölçüm değişti: boğaz çapı artık metre değil'

        md, _report = normalise_export_geometry(liquid_results)
        assert md['chamber_diameter'] == pytest.approx(raw_d / 1000.0, rel=1e-12)
        assert md['throat_diameter'] == pytest.approx(raw_t, rel=1e-12)
        # exit_diameter < chamber_diameter görüntüsü (0.103 < 99.19) kalkmalı
        assert md['exit_diameter'] > md['throat_diameter']

    def test_normalisation_is_idempotent(self, solid_results, liquid_results):
        for results in (solid_results, liquid_results):
            once, _r1 = normalise_export_geometry(results)
            twice, _r2 = normalise_export_geometry(once)
            for key in ('chamber_diameter', 'chamber_length', 'throat_diameter',
                        'exit_diameter'):
                assert twice[key] == pytest.approx(once[key], rel=1e-15), key

    def test_magnitude_inference_thresholds(self):
        """Beyansız girdide birim büyüklükten çıkarılır (eşikler tek yerde)."""
        assert resolve_length_m({'chamber_diameter': 0.1},
                                'chamber_diameter') == (0.1, 'si')
        assert resolve_length_m({'chamber_diameter': 100.0},
                                'chamber_diameter') == (0.1, 'mm')
        # Açık beyan çıkarımı EZER
        assert resolve_length_m({'chamber_diameter': 100.0,
                                 'length_units': 'mm'},
                                'chamber_diameter') == (0.1, 'declared:mm')

    def test_dxf_labels_use_millimetres_not_metres_times_1000(
            self, solid_results, tmp_path):
        """H4-2 ölçümü: Ø_chamber 100000.0 mm yazıyordu, 100.0 olmalı."""
        pytest.importorskip('ezdxf')
        path = _quiet(generate_dxf, solid_results, str(tmp_path / 's.dxf'))
        texts = _dxf_texts(path)
        chamber = [t for t in texts if t.startswith('Ø_chamber')]
        assert chamber, texts
        value = float(chamber[0].split('=')[1].replace('mm', '').strip())
        expected = solid_results['motor_geometry']['chamber_diameter'] * 1000.0
        assert value == pytest.approx(expected, rel=1e-3), (
            f'Ø_chamber = {value} mm; {expected:.1f} mm bekleniyordu '
            '(1000× birim hatası geri geldi)')
        assert value < 1000.0, 'çap hâlâ metre gibi 1000 ile çarpılıyor'

    @pytest.mark.parametrize('kind', ['solid', 'liquid'])
    def test_raw_and_normalised_input_draw_the_same_motor(
            self, solid_results, liquid_results, kind, tmp_path):
        """Ham yanıt ile normalize geometri AYNI çizimi vermeli.

        Kusurun özü buydu: arayüz ``motor_geometry`` gönderdiği için tarayıcı
        yolu doğru, belgelenmiş hesap yanıtını uca veren her program çağrısı
        1000× yanlış çizim alıyordu.
        """
        pytest.importorskip('ezdxf')
        results = solid_results if kind == 'solid' else liquid_results
        geo = dict(results['motor_geometry'])
        geo['motor_name'] = f'{kind.upper()}_GEO'
        raw_bb = _dxf_body_bbox(
            _quiet(generate_dxf, results, str(tmp_path / f'{kind}_raw.dxf')))
        geo_bb = _dxf_body_bbox(
            _quiet(generate_dxf, geo, str(tmp_path / f'{kind}_geo.dxf')))
        for raw, norm in zip(raw_bb, geo_bb):
            assert raw == pytest.approx(norm, rel=1e-9), (
                f'{kind}: ham yanıttan {raw:.3f} mm, normalize geometriden '
                f'{norm:.3f} mm — birim sözleşmesi hâlâ girdiye bağlı')

    def test_drawing_declares_the_resolved_input_unit(self, solid_results,
                                                      tmp_path):
        pytest.importorskip('ezdxf')
        path = _quiet(generate_dxf, solid_results, str(tmp_path / 'u.dxf'))
        texts = ' | '.join(_dxf_texts(path))
        assert 'INPUT UNITS:' in texts, (
            'çizim hangi girdi biriminden çevrildiğini beyan etmiyor')
        assert 'ALL DIMENSIONS IN MILLIMETRES ($INSUNITS=4)' in texts

    def test_missing_chamber_geometry_is_refused_not_invented(self, tmp_path):
        """Kamara ölçüsü çözülemiyorsa çizim ÜRETİLMEZ (fail-closed)."""
        pytest.importorskip('ezdxf')
        with pytest.raises(DrawingGeometryError):
            generate_dxf({'motor_name': 'BOS', 'throat_diameter': 0.02},
                         str(tmp_path / 'bos.dxf'))


# ---------------------------------------------------------------------------
# H4-1 — grain yalnız gerçekten varsa çizilir
# ---------------------------------------------------------------------------

class TestH4_1SiviMotordaGrainYok:

    def test_liquid_result_has_no_grain(self, liquid_results):
        grain, reason = resolve_grain_m(liquid_results)
        assert grain is None, (
            'sıvı çift yakıtlı motorda katı yakıt bloğu yoktur; çözümleyici '
            f'yine de bir grain buldu: {grain}')
        assert reason == GRAIN_NOT_IN_RESULT

    def test_solid_and_hybrid_grain_is_real_not_a_fallback(
            self, solid_results, hybrid_results):
        """Gerçek grain'ler ÇÖZÜCÜDEN gelmeli, eski sabit yedekten değil."""
        solid_grain, _r = resolve_grain_m(solid_results)
        gd = solid_results['grain_design']
        assert solid_grain['length'] == pytest.approx(
            gd['grain_length_mm'] / 1000.0, rel=1e-12)
        assert solid_grain['port_initial'] == pytest.approx(
            gd['inner_diameter_mm'] / 1000.0, rel=1e-12)
        # Eski yedekler: 0.24 m boy, Ø0.03 / Ø0.05 m port
        hybrid_grain, _r2 = resolve_grain_m(hybrid_results)
        assert hybrid_grain['length'] == pytest.approx(
            hybrid_results['grain_design']['grain_length_mm'] / 1000.0,
            rel=1e-12)
        assert hybrid_grain['length'] != pytest.approx(0.24, abs=1e-9)

    def test_liquid_dxf_draws_no_grain_and_says_why(self, liquid_results,
                                                    tmp_path):
        pytest.importorskip('ezdxf')
        path = _quiet(generate_dxf, liquid_results, str(tmp_path / 'l.dxf'))
        texts = _dxf_texts(path)
        joined = ' | '.join(texts)
        assert not any(t.startswith('grain ') for t in texts), (
            f'sıvı motor çiziminde hâlâ grain ölçüsü var: {joined}')
        assert '240.0 mm' not in joined, (
            'eski sabit yedek (240 mm grain) çizime geri geldi')
        assert 'SOLID GRAIN: NOT MODELLED' in joined, (
            'grain çizilmedi ama nedeni beyan edilmedi')

    def test_liquid_dims_expose_the_missing_grain(self, liquid_results):
        d = _dims_mm(liquid_results)
        assert d['grain'] is None
        assert d['grain_reason'] == GRAIN_NOT_IN_RESULT
        # Ölçüler yine de çözülmüş olmalı (grain'in yokluğu diğerlerini
        # etkilemez)
        assert d['D_ch'] == pytest.approx(
            liquid_results['motor_geometry']['chamber_diameter'] * 1000.0,
            rel=1e-9)

    def test_solid_dxf_still_draws_its_real_grain(self, solid_results,
                                                 tmp_path):
        pytest.importorskip('ezdxf')
        path = _quiet(generate_dxf, solid_results, str(tmp_path / 's2.dxf'))
        grain_lines = [t for t in _dxf_texts(path) if t.startswith('grain ')]
        assert grain_lines, 'katı motorda grain çizilmiyor — aşırı düzeltme'
        boy = float(grain_lines[0].split()[1])
        assert boy == pytest.approx(
            solid_results['grain_design']['grain_length_mm'], rel=1e-3)

    def test_liquid_step_assembly_has_no_fuel_grain_part(self, liquid_results,
                                                         tmp_path):
        pytest.importorskip('build123d')
        from hrma.export.step_export import generate_step_assembly
        files = _quiet(generate_step_assembly, liquid_results,
                       out_dir=str(tmp_path / 'step'), motor_type='liquid')
        assert 'fuel_grain' not in files, (
            'sıvı motor STEP montajında yakıt grain parçası var: '
            f'{sorted(files)}')
        assert {'chamber', 'nozzle', 'injector', 'assembly'} <= set(files)

    def test_liquid_step_has_no_grain_even_with_default_motor_type(
            self, liquid_results, tmp_path):
        """Rota katmanı ``motor_type`` geçmiyor; varsayılan 'hybrid'.

        Kusurun tetikleyicisi buydu: app.py ``generate_step_assembly(md)``
        çağırıyor, varsayılan 'hybrid' olduğu için sıvı motorda da
        ``fuel_grain.step`` üretiliyordu.
        """
        pytest.importorskip('build123d')
        from hrma.export.step_export import generate_step_assembly
        files = _quiet(generate_step_assembly, liquid_results,
                       out_dir=str(tmp_path / 'step_default'))
        assert 'fuel_grain' not in files, sorted(files)

    def test_liquid_stl_assembly_has_no_grain_mesh(self, liquid_results,
                                                   tmp_path):
        pytest.importorskip('trimesh')
        from hrma.export.cad_visualization import MotorCADDesigner
        cad = _quiet(MotorCADDesigner().generate_3d_motor_assembly,
                     dict(liquid_results))
        names = [n for n, _m in cad['assembly_meshes']]
        assert 'Fuel Grain' not in names, (
            f'sıvı motorun 3B montajında yakıt grain\'i var: {names}')
        assert 'Chamber' in names and 'Nozzle' in names

    def test_solid_stl_assembly_keeps_its_grain(self, solid_results):
        pytest.importorskip('trimesh')
        from hrma.export.cad_visualization import MotorCADDesigner
        cad = _quiet(MotorCADDesigner().generate_3d_motor_assembly,
                     dict(solid_results))
        names = [n for n, _m in cad['assembly_meshes']]
        assert 'Fuel Grain' in names, f'katı motorda grain kayboldu: {names}'


# ---------------------------------------------------------------------------
# H4-2 doğrulaması — üç imalat dosyası aynı motoru anlatmalı
# ---------------------------------------------------------------------------

class TestUcDosyaAyniMotor:

    @pytest.mark.parametrize('kind', ['solid', 'liquid'])
    def test_step_and_stl_envelopes_agree_within_one_percent(
            self, solid_results, liquid_results, kind, tmp_path):
        build123d = pytest.importorskip('build123d')
        trimesh = pytest.importorskip('trimesh')
        from hrma.export.cad_visualization import MotorCADDesigner
        from hrma.export.step_export import generate_step_assembly

        results = solid_results if kind == 'solid' else liquid_results
        files = _quiet(generate_step_assembly, results,
                       out_dir=str(tmp_path / 'step'))
        bb = build123d.import_step(files['assembly']).bounding_box()
        step_sizes = sorted(float(v) for v in (bb.size.X, bb.size.Y, bb.size.Z))

        designer = MotorCADDesigner()
        cad = _quiet(designer.generate_3d_motor_assembly, dict(results))
        stl_dir = str(tmp_path / 'stl')
        _quiet(designer.export_stl_files, cad['assembly_meshes'],
               output_dir=stl_dir)
        mesh = _quiet(trimesh.load,
                      os.path.join(stl_dir, 'motor_assembly.stl'))
        stl_sizes = sorted(float(v) for v in mesh.extents)

        for step_mm, stl_mm in zip(step_sizes, stl_sizes):
            assert stl_mm == pytest.approx(step_mm, rel=0.01), (
                f'{kind}: STEP {step_mm:.3f} mm, STL {stl_mm:.3f} mm — '
                'iki imalat dosyası aynı motoru anlatmıyor')

    @pytest.mark.parametrize('kind', ['solid', 'liquid'])
    def test_dxf_axial_span_matches_the_step_solid(
            self, solid_results, liquid_results, kind, tmp_path):
        """DXF eksenel açıklığı ile STEP katısının farkı YALNIZ baş kapaktır.

        STEP profili baş kapağı z = -cap'e taşar (step_export.py, chamber
        profili), DXF ise kamarayı z = 0'dan çizer. Fark bu yüzden tam olarak
        ``cap`` kadardır; başka hiçbir sapma kabul edilmez — 1000× birim
        hatası bu eşitliği anında kırar.
        """
        build123d = pytest.importorskip('build123d')
        pytest.importorskip('ezdxf')
        from hrma.export.cad_visualization import _chamber_wall_thickness_m
        from hrma.export.step_export import generate_step_assembly

        results = solid_results if kind == 'solid' else liquid_results
        dxf_x, _dxf_y = _dxf_body_bbox(
            _quiet(generate_dxf, results, str(tmp_path / f'{kind}.dxf')))
        files = _quiet(generate_step_assembly, results,
                       out_dir=str(tmp_path / 'step'))
        step_x = float(build123d.import_step(files['assembly'])
                       .bounding_box().size.X)

        md, _report = normalise_export_geometry(results)
        wall_mm = _chamber_wall_thickness_m(md)[0] * 1000.0
        rc_mm = md['chamber_diameter'] * 1000.0 / 2.0
        cap_mm = min(max(1.6 * wall_mm, 8.0), 0.3 * rc_mm + 8.0)
        assert step_x - dxf_x == pytest.approx(cap_mm, abs=1e-6), (
            f'{kind}: DXF {dxf_x:.2f} mm, STEP {step_x:.2f} mm; fark '
            f'{step_x - dxf_x:.3f} mm, baş kapak {cap_mm:.3f} mm olmalıydı')


# ---------------------------------------------------------------------------
# H4-3 — rapor PDF'i her ölçüyü kendi biriminden çevirir
# ---------------------------------------------------------------------------

class TestH4_3RaporPdfBirimi:

    @pytest.fixture(scope='class')
    def generator(self):
        pytest.importorskip('reportlab')
        from hrma.export.pdf_generator import PDFReportGenerator
        return PDFReportGenerator()

    def test_liquid_throat_and_exit_are_not_1000x_small(self, generator,
                                                        liquid_results):
        """Ölçüldü: 0.03 mm / 0.10 mm basılıyordu; 28.34 / 103.06 olmalı."""
        geo = liquid_results['motor_geometry']
        throat = generator._fmt_length_mm(liquid_results, 'throat_diameter')
        exit_d = generator._fmt_length_mm(liquid_results, 'exit_diameter')
        assert float(throat.split()[0]) == pytest.approx(
            geo['throat_diameter'] * 1000.0, rel=1e-3), throat
        assert float(exit_d.split()[0]) == pytest.approx(
            geo['exit_diameter'] * 1000.0, rel=1e-3), exit_d
        assert float(throat.split()[0]) > 1.0, (
            'boğaz çapı hâlâ metre değeri mm etiketiyle basılıyor')

    def test_liquid_chamber_rows_stay_correct(self, generator, liquid_results):
        """Alan başına çözüm kamara satırlarını bozmamalı."""
        geo = liquid_results['motor_geometry']
        for key in ('chamber_diameter', 'chamber_length'):
            text = generator._fmt_length_mm(liquid_results, key)
            assert float(text.split()[0]) == pytest.approx(
                geo[key] * 1000.0, rel=1e-3), f'{key}: {text}'

    def test_hybrid_and_solid_rows_stay_correct(self, generator,
                                                hybrid_results, solid_results):
        text = generator._fmt_length_mm(hybrid_results, 'chamber_diameter')
        assert float(text.split()[0]) == pytest.approx(
            hybrid_results['chamber_diameter'] * 1000.0, rel=1e-3)
        text = generator._fmt_length_mm(solid_results, 'throat_diameter')
        assert float(text.split()[0]) == pytest.approx(
            solid_results['motor_geometry']['throat_diameter'] * 1000.0,
            rel=1e-3)

    def test_unit_row_no_longer_claims_a_single_unit(self, generator,
                                                     liquid_results):
        """Karışık birimli sıvı yanıtında TEK birim teminatı basılmamalı.

        Normalize ``motor_geometry`` bloğu OLMADAN (çözücünün ham çıktısı)
        kamara mm, boğaz/çıkış metre gelir; eski satır yine de "input
        interpreted as mm" diyordu.
        """
        raw = {k: v for k, v in liquid_results.items() if k != 'motor_geometry'}
        note = generator._length_unit_note(raw)
        assert 'per field' in note, note
        assert 'input interpreted as' not in note
        assert 'throat_diameter=inferred m' in note
        assert 'chamber_diameter=inferred mm' in note

    def test_uniform_input_still_gets_a_single_line(self, generator,
                                                    hybrid_results):
        """Tüm alanlar aynı yoldan çözülüyorsa tek satırlık beyan kalır."""
        note = generator._length_unit_note(hybrid_results)
        assert note == 'mm (input interpreted as m)', note

    def test_raw_liquid_throat_is_still_right_without_motor_geometry(
            self, generator, liquid_results):
        """Alan başına çözüm normalize blok olmadan da doğru olmalı."""
        raw = {k: v for k, v in liquid_results.items() if k != 'motor_geometry'}
        text = generator._fmt_length_mm(raw, 'throat_diameter')
        # Satır iki ondalıkla basılır; karşılaştırma o çözünürlükte yapılır.
        assert float(text.split()[0]) == pytest.approx(
            float(liquid_results['throat_diameter']) * 1000.0, abs=0.005), text


# ---------------------------------------------------------------------------
# H4-7 — iki kuru kütle / üç lüle kütlesi beyan edilir
# ---------------------------------------------------------------------------

class TestH4_7KutleOtoritesi:

    @pytest.fixture(scope='class')
    def hybrid_with_cad(self, hybrid_results):
        from hrma.export.cad_visualization import MotorCADDesigner
        md = dict(hybrid_results)
        cad = _quiet(MotorCADDesigner().generate_3d_motor_assembly, dict(md))
        md['cad_design'] = {'performance_summary': cad['performance_summary']}
        return md

    def test_cad_declares_the_authoritative_nozzle_mass(self, hybrid_with_cad):
        breakdown = hybrid_with_cad['cad_design']['performance_summary'][
            'mass_breakdown']
        assert 'AUTHORITATIVE' in breakdown['nozzle_mass_basis']
        assert 'frustum-annulus' in breakdown['nozzle_mass_basis']

    def test_cad_total_declares_what_it_leaves_out(self, hybrid_with_cad):
        breakdown = hybrid_with_cad['cad_design']['performance_summary'][
            'mass_breakdown']
        scope = breakdown['total_dry_mass_scope']
        assert 'Closures' in scope and 'NOT included' in scope

    def test_reconciliation_names_both_totals(self, hybrid_with_cad):
        from hrma.export.openrocket_integration import OpenRocketExporter
        rec = OpenRocketExporter.dry_mass_reconciliation(hybrid_with_cad)
        assert rec is not None
        struct = hybrid_with_cad['structural_analysis']['weight_analysis']
        cad_bd = hybrid_with_cad['cad_design']['performance_summary'][
            'mass_breakdown']
        assert rec['eng_total_kg'] == pytest.approx(struct['total_weight'])
        assert rec['cad_total_kg'] == pytest.approx(cad_bd['total_dry_mass'])
        assert rec['nozzle_authoritative_kg'] == pytest.approx(
            cad_bd['nozzle_mass'])
        # Ölçülen ayrışma: %20'den büyük, sıfır değil
        assert rec['difference_percent'] > 1.0

    def test_eng_file_carries_the_discrepancy(self, hybrid_with_cad):
        from hrma.export.openrocket_integration import OpenRocketExporter
        eng = _quiet(OpenRocketExporter().export_motor_file,
                     dict(hybrid_with_cad))
        assert 'two dry masses exist' in eng, (
            '.eng dosyası hangi kuru kütlenin yazıldığını ve ikinci toplamla '
            'farkını beyan etmiyor')
        assert 'AUTHORITATIVE nozzle mass' in eng

    def test_inert_mass_contract_unchanged(self, hybrid_results):
        """Beyan eklendi, DEĞER değişmedi — .eng yüklü kütlesi aynı kaynaktan."""
        from hrma.export.openrocket_integration import OpenRocketExporter
        mass, source = OpenRocketExporter.resolve_inert_mass(hybrid_results)
        assert source == 'structural'
        assert mass == pytest.approx(
            hybrid_results['structural_analysis']['weight_analysis'][
                'total_weight'])
