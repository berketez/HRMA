"""Export üreticileri round-trip doğrulaması (DXF / çizim PDF / STEP / STL).

Her üretici GERÇEK dosya üretir ve ilgili kütüphaneyle GERİ OKUNARAK
doğrulanır (sahte/boş çıktı yakalanır — 2026-07-12 denetiminde popup
butonlarının alert'ten ibaret olduğu, hata fallback'inin tek-üçgen sahte
STL yazdığı bulunmuştu).
"""

import io
import os
import contextlib

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine


@pytest.fixture(scope='module')
def motor_results():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        e = HybridRocketEngine(
            thrust=3000, burn_time=10, of_ratio=7.96, chamber_pressure=20,
            fuel_type='paraffin', oxidizer_type='n2o', fuel_density=900,
            regression_a=1.17e-4, regression_n=0.62, expansion_ratio=0)
        r = e.calculate()
    r['motor_name'] = 'EXPORT_TEST'
    return r


class TestDXF:
    def test_dxf_roundtrip(self, motor_results, tmp_path):
        ezdxf = pytest.importorskip('ezdxf')
        from hrma.export.drawing_generator import generate_dxf
        path = generate_dxf(motor_results, str(tmp_path / 'test.dxf'))
        doc = ezdxf.readfile(path)
        ents = list(doc.modelspace())
        layers = {e.dxf.layer for e in ents}
        # Kontur + dış hat + eksen + metin katmanları dolu olmalı
        assert {'CONTOUR', 'OUTLINE', 'CENTERLINE', 'TEXT'} <= layers
        assert len(ents) >= 10
        # Kontur polyline'ı gerçek nozul geometrisini taşımalı (örnekleyici
        # ~40+ nokta üretir; düz-çizgi sahtesi <10 olurdu)
        polys = [e for e in ents if e.dxftype() == 'LWPOLYLINE'
                 and e.dxf.layer == 'CONTOUR']
        assert polys and max(len(p) for p in polys) > 30


class TestDrawingPDF:
    def test_pdf_generated_with_pages(self, motor_results, tmp_path):
        pytest.importorskip('reportlab')
        from hrma.export.drawing_generator import generate_drawing_pdf
        path = generate_drawing_pdf(motor_results, str(tmp_path / 'test.pdf'))
        data = open(path, 'rb').read()
        assert data[:5] == b'%PDF-'
        # 3 sayfa: kesit + enjektör + tablo
        assert data.count(b'/Type /Page') >= 3 or data.count(b'/Type/Page') >= 3
        # Kesit görüntüsü gömüldüyse dosya küçük olamaz (kaleido çalıştı)
        assert len(data) > 50_000


class TestSTEP:
    def test_step_assembly_roundtrip(self, motor_results, tmp_path):
        b123d = pytest.importorskip('build123d')
        from hrma.export.step_export import generate_step_assembly
        files = generate_step_assembly(motor_results, str(tmp_path))
        assert set(files) == {'chamber', 'nozzle', 'fuel_grain',
                              'injector', 'assembly'}
        for k, p in files.items():
            head = open(p, 'r', errors='ignore').read(200)
            assert 'ISO-10303' in head, f'{k} geçerli STEP değil'
            assert os.path.getsize(p) > 2000
        # Geri okuma: assembly import edilebilir olmalı
        from build123d import import_step
        solid = import_step(files['assembly'])
        assert solid is not None


class TestSTLQuality:
    def test_injector_orifices_actually_drilled(self, motor_results):
        """manifold3d boolean'ı: delikler STL katısında GERÇEKTEN açık olmalı
        (eski durum: boolean backend yokken delikler sessizce düşüyordu)."""
        pytest.importorskip('manifold3d')
        import trimesh
        from hrma.export.cad_visualization import MotorCADDesigner
        designer = MotorCADDesigner()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cad = designer.generate_3d_motor_assembly(dict(motor_results))
        meshes = dict(cad['assembly_meshes'])
        inj = meshes.get('Injector') or meshes.get('injector')
        assert inj is not None
        D_ch = float(motor_results['chamber_diameter'])
        plate_vol = np.pi * (D_ch / 2) ** 2 * 0.03  # 30mm plaka
        assert inj.volume < plate_vol * 0.999, 'orifis delikleri açılmamış'
        assert inj.is_watertight

    def test_export_raises_instead_of_fake_stl(self, tmp_path):
        """Bozuk mesh sahte tek-üçgen STL yerine hata yükseltmeli."""
        from hrma.export.cad_visualization import MotorCADDesigner
        designer = MotorCADDesigner()

        class Broken:
            def export(self, *_a, **_k):
                raise IOError('bozuk mesh')
        with pytest.raises(RuntimeError):
            designer.export_stl_files([('Broken', Broken())],
                                      output_dir=str(tmp_path))
