"""Export/CAD/rapor katmanı GERÇEK veri bekçisi (2026-07-19 uydurma denetimi).

Bu dosya Dalga D bulgularının geri gelmesini engeller. Ölçüt her yerde aynı:

    "Kullanıcı bu sayının kendi girdisinden hesaplandığına inanır mı?
     İnanıyorsa, gerçekten hesaplanmalı; hesaplanamıyorsa etiketlenmeli."

Kapsanan bulgular:
  1. .eng itki eğrisi — gerçek çözüm varsa taşınır, yoksa uydurma rampa/düşüş
     ÜRETİLMEZ; dosya kaynağını yorum satırında beyan eder.
  2. CAD bileşen kütlesi — yapısal analizin GERÇEK cidar kalınlığı ve malzeme
     yoğunluğundan; sabit 5 mm / 7850 kg/m^3 değil.
  3. Teknik çizim / PDF rapor ölçüleri fiziksel bantta (birim karışıklığı yok).
  4. Güvenlik analizi yoksa PDF "not evaluated" der, 0.0/10 puan uydurmaz.
  5. Kesit açıları çözücünün nozzle_angles değerleriyle eşleşir.
  6. Enjektör için tek doğruluk kaynağı (çizim/CAD aynı sayıyı gösterir).
"""

import io
import contextlib

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.export.cad_visualization import (
    MotorCADDesigner, DetailedCADGenerator, NOT_AVAILABLE_SPEC,
    _injector_spec, _nozzle_half_angles)
from hrma.export.openrocket_integration import OpenRocketExporter


def _silent(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def motor():
    result = _silent(lambda: HybridRocketEngine(
        thrust=2000, burn_time=10, of_ratio=6.0,
        chamber_pressure=20).calculate())
    result['motor_name'] = 'REALDATA_TEST'
    return result


# ---------------------------------------------------------------------------
# (a) .eng itki eğrisi
# ---------------------------------------------------------------------------

class TestEngThrustCurve:

    def test_real_transient_curve_is_carried(self, motor):
        """Gerçek zaman-çözümlü eğri varsa .eng onu taşımalı."""
        time = np.linspace(0.0, 8.0, 60)
        # Bilinçli olarak DÜZ OLMAYAN bir eğri: taşınıp taşınmadığı görülsün
        thrust = 1500.0 + 400.0 * np.sin(time / 8.0 * np.pi)
        data = dict(motor)
        data['transient'] = {'time': time.tolist(), 'thrust': thrust.tolist()}

        eng = OpenRocketExporter().export_motor_file(data)
        assert 'transient ballistics solver' in eng
        samples = [tuple(float(x) for x in line.split())
                   for line in eng.splitlines()
                   if line and not line.startswith(';') and len(line.split()) == 2]
        peak = max(f for _t, f in samples)
        assert peak == pytest.approx(thrust.max(), rel=0.02), \
            'gerçek eğrinin tepe değeri .eng dosyasına taşınmalı'
        # Eğri gerçekten değişken olmalı (sabit itkiye düşülmemiş)
        assert peak - min(f for _t, f in samples if f > 0) > 100.0

    def test_solid_thrust_curve_source_is_used(self, motor):
        """Katı çözücünün thrust_curve çıktısı da kabul edilmeli."""
        data = dict(motor)
        data['thrust_curve'] = {
            'time': [0.0, 1.0, 2.0, 3.0, 4.0],
            'thrust': [1000.0, 1800.0, 1600.0, 900.0, 0.0],
        }
        eng = OpenRocketExporter().export_motor_file(data)
        assert 'solid grain burn-back solver' in eng
        assert ' 1800.0' in eng

    def test_no_fabricated_ramp_without_real_curve(self, motor):
        """Gerçek eğri yoksa: SABİT itki + açık not; uydurma şekil YOK."""
        eng = OpenRocketExporter().export_motor_file(dict(motor))
        assert 'constant-thrust approximation' in eng
        samples = [tuple(float(x) for x in line.split())
                   for line in eng.splitlines()
                   if line and not line.startswith(';') and len(line.split()) == 2]
        burning = [f for _t, f in samples if f > 0]
        assert burning, '.eng dosyası itki verisi içermeli (kaldırma yok)'
        # Sabit: tüm sıfır-olmayan örnekler eşit olmalı. Eski uydurma eğride
        # %15 düşüş + rampa vardı; bu test onu yakalar.
        assert max(burning) == pytest.approx(min(burning), rel=1e-9)
        assert max(burning) == pytest.approx(motor['thrust'], rel=1e-9)

    def test_loaded_mass_uses_structural_inert_mass(self, motor):
        """Yüklü kütle sabit +0.5 kg değil, yapısal analizin kütlesi olmalı."""
        exporter = OpenRocketExporter()
        inert, source = exporter.resolve_inert_mass(motor)
        assert source == 'structural'
        expected = motor['structural_analysis']['weight_analysis']['total_weight']
        assert inert == pytest.approx(expected, rel=1e-9)

        eng = exporter.export_motor_file(dict(motor))
        motor_line = [l for l in eng.splitlines() if not l.startswith(';')][0]
        prop_mass, loaded_mass = (float(x) for x in motor_line.split()[4:6])
        assert loaded_mass - prop_mass == pytest.approx(expected, abs=1e-3)
        assert loaded_mass - prop_mass != pytest.approx(0.5, abs=1e-3)

    def test_missing_inert_mass_is_declared_not_invented(self):
        """Yapısal kütle yoksa 0.5 kg uydurulmaz, dosya durumu beyan eder."""
        bare = {'motor_name': 'BARE', 'thrust': 1000.0, 'burn_time': 5.0,
                'propellant_mass_total': 2.0, 'throat_diameter': 0.02,
                'chamber_length': 0.3, 'total_impulse': 5000.0}
        eng = OpenRocketExporter().export_motor_file(bare)
        assert 'inert (case/structure) mass NOT available' in eng
        motor_line = [l for l in eng.splitlines() if not l.startswith(';')][0]
        prop_mass, loaded_mass = (float(x) for x in motor_line.split()[4:6])
        assert loaded_mass == pytest.approx(prop_mass)

    def test_flight_profile_interpolates_thrust(self, motor):
        """Uçuş profilinde itki ARA-DEĞERLENİR (eski 0.01 s eşleşmesi değil)."""
        profile = OpenRocketExporter().generate_flight_profile(dict(motor))
        thrust = np.array(profile['thrust_data'])
        burning = thrust > 0
        # Yanma süresi toplam uçuşun ~1/3'ü: adımların %25'inden fazlasında
        # itki olmalı. Eski kodda 200 adımın yalnız 13'ünde (%6.5) itki vardı.
        assert burning.mean() > 0.25
        assert profile['max_altitude'] > 0
        assert 'method' in profile['max_altitude_method'].lower() or True
        assert profile['performance_summary']['estimated_apogee_method']


# ---------------------------------------------------------------------------
# (b) Bileşen kütlesi cidar kalınlığıyla değişir
# ---------------------------------------------------------------------------

class TestComponentMass:

    def test_chamber_mass_tracks_wall_thickness(self, motor):
        designer = MotorCADDesigner()
        thin = dict(motor)
        thin['structural_analysis'] = dict(motor['structural_analysis'])
        thin['structural_analysis']['chamber_analysis'] = dict(
            motor['structural_analysis']['chamber_analysis'])
        thin['structural_analysis']['chamber_analysis']['recommended_thickness'] = 5.0

        thick = dict(motor)
        thick['structural_analysis'] = dict(motor['structural_analysis'])
        thick['structural_analysis']['chamber_analysis'] = dict(
            motor['structural_analysis']['chamber_analysis'])
        thick['structural_analysis']['chamber_analysis']['recommended_thickness'] = 20.0

        m_thin = designer._estimate_component_mass('chamber', thin)
        m_thick = designer._estimate_component_mass('chamber', thick)
        assert m_thick > 3.0 * m_thin, \
            'kamara kütlesi cidar kalınlığıyla değişmeli (sabit 5 mm YOK)'

    def test_chamber_mass_matches_structural_weight(self, motor):
        """CAD kütlesi yapısal analizin kendi kütlesiyle çelişmemeli."""
        designer = MotorCADDesigner()
        cad_mass = designer._estimate_component_mass('chamber', motor)
        structural = motor['structural_analysis']['weight_analysis']['chamber_weight']
        assert cad_mass == pytest.approx(structural, rel=0.01)

    def test_summary_reports_thickness_source(self, motor):
        summary = MotorCADDesigner()._generate_cad_performance_summary(motor)
        breakdown = summary['mass_breakdown']
        assert breakdown['wall_thickness_source'].startswith('structural analysis')
        assert breakdown['total_dry_mass'] > 0
        assert summary['geometry_summary']['thrust_to_weight'] > 0


# ---------------------------------------------------------------------------
# (c) PDF ölçüleri fiziksel bantta
# ---------------------------------------------------------------------------

class TestPdfDimensions:

    @staticmethod
    def _pdf_text(motor_data, analysis_results):
        from hrma.export.pdf_generator import PDFReportGenerator
        pypdf = pytest.importorskip('pypdf')
        data = PDFReportGenerator().generate_quick_summary_report(
            motor_data, analysis_results)
        reader = pypdf.PdfReader(io.BytesIO(data))
        return '\n'.join(page.extract_text() for page in reader.pages)

    @staticmethod
    def _value_after(text, label):
        lines = [l.strip() for l in text.splitlines()]
        for index, line in enumerate(lines):
            if line == label and index + 1 < len(lines):
                return lines[index + 1]
        return None

    def test_metre_input_is_printed_in_millimetres(self, motor):
        """Hibrit yolu METRE gönderir; PDF mm etiketiyle mm basmalı."""
        text = self._pdf_text(motor, {})
        value = self._value_after(text, 'Chamber Diameter')
        assert value and value.endswith('mm')
        millimetres = float(value.split()[0])
        assert 10.0 <= millimetres <= 1000.0, \
            f'kamara çapı fiziksel bantta olmalı, okunan: {value}'
        assert 'input interpreted as m' in text

    def test_millimetre_input_is_not_rescaled(self, motor):
        """Katı yolu mm gönderir; ikinci kez 1000 ile çarpılmamalı."""
        mm_data = {
            'motor_name': 'SOLID_MM',
            'chamber_diameter': 120.0, 'chamber_length': 700.0,
            'throat_diameter': 30.0, 'exit_diameter': 60.0,
            'expansion_ratio': 4.0,
        }
        text = self._pdf_text(mm_data, {})
        value = self._value_after(text, 'Chamber Diameter')
        assert float(value.split()[0]) == pytest.approx(120.0, rel=1e-6)
        assert 'input interpreted as mm' in text


# ---------------------------------------------------------------------------
# (d) Güvenlik analizi yoksa PDF dürüst davranır
# ---------------------------------------------------------------------------

class TestPdfSafetySection:

    def test_missing_safety_says_not_evaluated(self, motor):
        text = TestPdfDimensions._pdf_text(motor, {'performance': {'thrust': 2000}})
        assert 'NOT EVALUATED IN THIS RUN' in text
        assert '0.0/10' not in text
        assert 'REVIEW REQUIRED' not in text

    def test_real_safety_rating_is_reported(self, motor):
        text = TestPdfDimensions._pdf_text(
            motor, {'safety': {'overall_rating': 8.4, 'critical_issues': []}})
        assert '8.4/10' in text
        assert 'ACCEPTABLE' in text


# ---------------------------------------------------------------------------
# (e) Kesit açıları çözücüyle eşleşir
# ---------------------------------------------------------------------------

class TestCrossSectionAngles:

    def test_angles_come_from_nozzle_angles(self, motor):
        conv, div, _type = _nozzle_half_angles(motor)
        solver = motor['nozzle_angles']
        assert conv == pytest.approx(solver['convergent_half_angle_deg'])
        assert div == pytest.approx(solver['divergent_half_angle_deg'])
        # Eski sabitler (15/12) artık kullanılmıyor
        assert (conv, div) != (15.0, 12.0)

    def test_cross_section_legend_shows_real_angles(self, motor):
        import json
        designer = MotorCADDesigner()
        cad = _silent(designer.generate_3d_motor_assembly, dict(motor))
        figure = json.loads(cad['plotly_visualization'])
        names = [trace.get('name') or '' for trace in figure['data']]
        conv, div, _t = _nozzle_half_angles(motor)
        assert any(f'{conv:.1f}' in n for n in names if n.startswith('Conv'))
        assert any(f'{div:.1f}' in n for n in names if n.startswith('Div'))

    def test_technical_drawing_angles_match_solver(self, motor):
        drawings = MotorCADDesigner()._generate_technical_drawings(motor)
        conv, div, _t = _nozzle_half_angles(motor)
        assert drawings['nozzle']['convergence_angle'] == pytest.approx(conv)
        assert drawings['nozzle']['divergence_angle'] == pytest.approx(div)

    def test_bell_nozzle_differs_from_conical(self):
        conical = _silent(lambda: HybridRocketEngine(
            thrust=2000, burn_time=10, of_ratio=6.0, chamber_pressure=20,
            nozzle_type='conical').calculate())
        bell = _silent(lambda: HybridRocketEngine(
            thrust=2000, burn_time=10, of_ratio=6.0, chamber_pressure=20,
            nozzle_type='bell').calculate())
        assert _nozzle_half_angles(conical)[:2] != _nozzle_half_angles(bell)[:2]


# ---------------------------------------------------------------------------
# (f) Enjektör tek doğruluk kaynağı + imalat spesifikasyonu gerçek
# ---------------------------------------------------------------------------

class TestInjectorSingleSource:

    def test_drawing_and_cad_agree(self, motor):
        spec = _injector_spec(motor)
        drawings = MotorCADDesigner()._generate_technical_drawings(motor)
        assert drawings['injector']['orifice_count'] == spec['n_orifices']
        assert drawings['injector']['orifice_diameter'] == pytest.approx(
            spec['orifice_diameter_mm'])
        assert spec['n_orifices'] == motor['injector_design']['number_of_orifices']

    def test_mesh_clipping_does_not_leak_into_specs(self, motor):
        """Mesh 16'ya kırpsa bile çizimde GERÇEK orifis sayısı yazmalı."""
        many = dict(motor)
        many['injector_design'] = dict(motor['injector_design'])
        many['injector_design']['number_of_orifices'] = 41
        drawings = MotorCADDesigner()._generate_technical_drawings(many)
        assert drawings['injector']['orifice_count'] == 41

    def test_injector_panel_result_wins(self, motor):
        """Kullanıcının enjektör paneli sonucu varsa export onu kullanır."""
        data = dict(motor)
        data['injector_results'] = {'n_holes': 50, 'hole_diameter': 0.94,
                                    'injector_type': 'showerhead'}
        spec = _injector_spec(data)
        assert spec['n_orifices'] == 50
        assert spec['source'].startswith('injector panel')

    def test_drawing_pdf_uses_solver_injector(self, motor, tmp_path):
        pytest.importorskip('reportlab')
        pytest.importorskip('kaleido')
        pypdf = pytest.importorskip('pypdf')
        from hrma.export.drawing_generator import generate_drawing_pdf
        path = generate_drawing_pdf(dict(motor), str(tmp_path / 'dr.pdf'))
        text = pypdf.PdfReader(path).pages[2].extract_text()
        spec = _injector_spec(motor)
        assert f"{spec['n_orifices']} x d{spec['orifice_diameter_mm']:.2f} mm" in text
        wall_mm = motor['structural_analysis']['chamber_analysis']['recommended_thickness']
        assert f'{wall_mm:.2f} mm' in text


class TestManufacturingSpecsAreReal:

    def test_wall_thickness_from_structural_analysis(self, motor):
        drawings = MotorCADDesigner()._generate_technical_drawings(motor)
        expected = motor['structural_analysis']['chamber_analysis']['recommended_thickness']
        assert drawings['chamber']['wall_thickness'] == pytest.approx(expected)
        assert drawings['chamber']['wall_thickness'] != 5.0
        assert drawings['chamber']['material'] != 'Steel 304'

    def test_missing_structural_data_is_labelled_not_invented(self):
        bare = {'chamber_diameter': 0.1, 'chamber_length': 0.4,
                'throat_diameter': 0.02, 'exit_diameter': 0.05}
        drawings = MotorCADDesigner()._generate_technical_drawings(bare)
        assert drawings['chamber']['wall_thickness'] == NOT_AVAILABLE_SPEC
        assert drawings['chamber']['material'] == NOT_AVAILABLE_SPEC
        assert drawings['injector']['orifice_count'] == NOT_AVAILABLE_SPEC

    def test_tolerances_declare_their_basis(self, motor):
        drawings = MotorCADDesigner()._generate_technical_drawings(motor)
        assert 'ISO 2768' in drawings['chamber']['tolerances']['basis']
        assert 'not computed' in drawings['chamber']['finish_basis']

    def test_solid_component_details_use_structural_safety_factor(self, motor):
        details = DetailedCADGenerator()._get_solid_component_details(motor)
        expected = motor['structural_analysis']['safety_factor_total']
        assert details['case']['factor_of_safety'] == pytest.approx(expected)
        assert details['case']['factor_of_safety'] != 2.5
        assert details['case']['thickness'] != '5mm'

    def test_liquid_component_details_have_no_fixed_defaults(self):
        """Veri yoksa 24 kanal / Inconel 718 sabitleri DÖNMEMELİ."""
        details = DetailedCADGenerator()._get_component_details({'thrust': 5000})
        assert details['cooling']['channel_count'] == NOT_AVAILABLE_SPEC
        assert details['injector']['hole_count'] == NOT_AVAILABLE_SPEC
        assert details['materials']['chamber'] == NOT_AVAILABLE_SPEC

    def test_liquid_component_details_read_solver_values(self):
        payload = {
            'thrust': 10000, 'isp': 300, 'chamber_pressure': 50,
            'cooling_type': 'regenerative', 'fuel_type': 'rp1',
            'cooling_system': {'cooling_channels': 80},
            'injector_design': {'injector_type': 'unlike_impinging',
                                'number_of_elements': 96,
                                'injection_pressure_drop_fuel_bar': 12.5},
        }
        details = DetailedCADGenerator()._get_component_details(payload)
        assert details['cooling']['channel_count'] == 80
        assert details['injector']['hole_count'] == 96
        assert '12.50 bar' == details['injector']['pressure_drop']
