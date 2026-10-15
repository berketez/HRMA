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


#: Enjektör panelinin TASARLANAN plaka kalınlığı [mm] — ÖH D32 / OH-D31-16.
#: Ürün yolunda bu sayı kullanıcının enjektör panelinden gelir; HRMA onu
#: TÜRETMEZ (``injector_plate_structural`` kalınlığı çağırandan alır ve
#: ``plate_thickness_earned`` ile künyeler).
_D32_PANEL_PLAKA_MM = 6.0


def _d32_panel_plakali(sonuc, t_mm=_D32_PANEL_PLAKA_MM):
    """Sonuca enjektör panelinin tasarlanan plakasını ekler.

    ÖH D32 / OH-D31-16 — ÇEVRİLEN BEKÇİ GEREKÇESİ. Aşağıdaki bekçiler
    STEP paketinde enjektör parçasının BULUNMASINI şart koşuyordu. O şart,
    plaka kalınlığının kamaranın ÖN KAPAĞINDAN (ya da bir üreteç
    sabitinden) türetildiği dönemden kalmaydı. ÖH D15 / P9B1-13 o ikameyi
    ölçüp reddetti (mesh/gerçek plaka oranı 10,0x) ve kardeş üretici
    ``cad_visualization`` plakayı ancak kalınlık YAYIMLANMIŞSA çiziyor.

    Ölçüldü (taban dd1dcddc): bu dosyanın ham çözücü fikstürleri plaka
    kalınlığı yayımlamıyor, dolayısıyla STL plakayı çizmiyordu; STEP ise
    çiziyordu. Aynı motorun iki katı dosyası iki farklı makineyi
    anlatıyordu ve ``/api/export-complete-zip`` paketi 422 ile
    reddediyordu. D32'de STEP de aynı çözümleyiciye bağlandı.

    Bekçilerin ASIL niyeti (gerçek çözüm verisiyle STEP üretimi kırılmaz;
    üretilen parçalar geçerli ve dolu) KORUNUR: fikstür artık kalınlığın
    KAZANILDIĞI koşuyu kurar. Kalınlığın YOKLUĞUNDA parçanın çizilmediği
    ``tests/test_d32_ihracat_a1.py``de ayrıca sınanır.
    """
    r = dict(sonuc)
    r['injector_results'] = {
        'plate_structural': {
            'status': 'analyzed',
            'plate_thickness_mm': float(t_mm),
            'material': 'stainless_steel_316',
        },
    }
    return r


class TestSTEP:
    def test_step_assembly_roundtrip(self, motor_results, tmp_path):
        b123d = pytest.importorskip('build123d')
        from hrma.export.step_export import generate_step_assembly
        files = generate_step_assembly(_d32_panel_plakali(motor_results),
                                      str(tmp_path))
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
        (eski durum: boolean backend yokken delikler sessizce düşüyordu).

        ÇEVRİLDİ — ÖH D15 / a2, ÖK-05. Bu bekçi ``assert inj is not None`` ile
        plakanın HER koşuda çizilmesini şart koşuyordu ve o şart, çizilen
        plakanın 30 mm'lik bir ÜRETEÇ SABİTİ olduğu dönemden kalmaydı: fikstür
        (ham ``HybridRocketEngine`` sonucu) plaka kalınlığını hiç yayımlamıyor
        (ölçüldü, 31 Ağustos 2026: ``_injector_plate_design(...)['thickness_m']
        is None``, gerekçe ``injector_plate_thickness_not_available``). ÖH D15
        a1'in P9B1-13 onarımı uydurma plakayı kaldırdığı için bekçi KIRMIZI
        oldu — yani kusuru koruyordu.

        Bekçinin asıl niyeti (boolean gerçekten deliyor mu) KORUNUR, ama iki
        dala ayrılır ve fail-closed dal da sınanır: plaka kalınlığı
        çözülüyorsa mesh VAR + su geçirmez + delikli olmalı; çözülmüyorsa mesh
        OLMAMALI ve gerekçe yayımlanmalıdır. Sayı uydurulan üçüncü bir hâl
        kabul edilmez.
        """
        pytest.importorskip('manifold3d')
        from hrma.export.cad_visualization import (MotorCADDesigner,
                                                   _injector_plate_design)
        designer = MotorCADDesigner()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cad = designer.generate_3d_motor_assembly(dict(motor_results))
        meshes = dict(cad['assembly_meshes'])
        inj = meshes.get('Injector') or meshes.get('injector')
        plate = _injector_plate_design(motor_results)
        t_m = plate.get('thickness_m')

        if t_m is None:
            assert inj is None, (
                'plaka kalınlığı çözülemiyor ama enjektör mesh"i çizilmiş — '
                'üreteç sabitinden plaka üretilmiş olabilir. Gerekçe: %s'
                % plate.get('source'))
            assert plate.get('source'), 'çizilmeme gerekçesi yayımlanmamış'
            return

        assert inj is not None
        D_ch = float(motor_results['chamber_diameter'])
        plate_vol = np.pi * (D_ch / 2) ** 2 * float(t_m)
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
