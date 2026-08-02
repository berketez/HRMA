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
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

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
    r = _quiet(SolidRocketEngine(
        chamber_diameter=100, grain_length=500, core_diameter=30,
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
        """Beyan mm ise koordinatlar da mm büyüklüğünde olmalı."""
        ezdxf = pytest.importorskip('ezdxf')
        from hrma.export.drawing_generator import generate_dxf
        doc = ezdxf.readfile(generate_dxf(hybrid_results,
                                          str(tmp_path / 'a2b.dxf')))
        xs = [p[0] for e in doc.modelspace()
              if e.dxftype() == 'LWPOLYLINE' for p in e.get_points('xy')]
        span = max(xs) - min(xs)
        assert 50.0 < span < 5000.0, (
            f'çizim X açıklığı {span:.2f} — mm ölçeğinde bir motor '
            'bekleniyordu (metre olsaydı < 10 çıkardı)')


# ---------------------------------------------------------------------------
# A1 — STL birimi STEP ile aynı olmalı
# ---------------------------------------------------------------------------

class TestA1StlBirimi:
    @pytest.fixture(scope='class')
    def both_exports(self, hybrid_results, tmp_path_factory):
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
        step_bb = import_step(step_files['chamber']).bounding_box()
        stl_mesh = trimesh.load(os.path.join(str(out / 'stl'), 'chamber.stl'))
        return (sorted((step_bb.size.X, step_bb.size.Y, step_bb.size.Z)),
                sorted(float(v) for v in stl_mesh.extents), stl_files)

    def test_step_and_stl_bounding_boxes_agree(self, both_exports):
        """Aynı parçanın iki dosyası aynı büyüklükte olmalı (1000× bekçisi)."""
        step_sizes, stl_sizes, _paths = both_exports
        for step_mm, stl_mm in zip(step_sizes, stl_sizes):
            assert stl_mm == pytest.approx(step_mm, rel=0.01), (
                f'STEP {step_mm:.3f} mm, STL {stl_mm:.3f} — STL hâlâ metre '
                'yazıyor olabilir (1000× birim hatası)')

    def test_stl_is_not_metres(self, both_exports):
        _step_sizes, stl_sizes, _paths = both_exports
        assert max(stl_sizes) > 10.0, (
            f'en büyük STL zarfı {max(stl_sizes):.4f} — mm bekleniyordu, '
            'metre bulundu')

    def test_export_returns_real_absolute_paths(self, both_exports):
        """A10 sözleşmesi: dönen yollar mutlak ve GERÇEKTEN var olmalı."""
        _s, _t, paths = both_exports
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
