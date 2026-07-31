"""
PDF rapor entegrasyonu testleri (Dalga 2, 2026-07-14).

Kapsam (test_client — sunucuya port BAĞLANMAZ):
  1. /api/export-pdf/<tip> gerçek analiz sonuçlarını rapora basar:
     - motor.structural_analysis'ten GERÇEK SF değerleri (sabit 4.0 YOK),
     - motor.heat_transfer_analysis'ten gerçek cidar sıcaklığı / ısı akısı,
     - yapısal durum (SAFE/UNSAFE...) metni.
  2. Analiz yoksa bölüm hiç basılmaz — değer UYDURULMAZ.
  3. Sayfa sayısı/boyut makul (düzen bozulmadı).
  4. /api/generate-complete-package eski sabit 'safety_factor: 4.0'
     kalıntısını artık üretmez; gerçek sonuç ya da 'NOT ANALYZED'.

Analiz girdileri UYDURMA değildir: gerçek HeatTransferAnalyzer ve
StructuralAnalyzer çıktıları kullanılır (Berke kuralı).
"""

import io
import warnings

import pytest

warnings.filterwarnings('ignore')

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer

# Gerçekçi motor girdisi — analizörler gerçek sonuçları buradan üretir.
BASE_MOTOR = {
    'chamber_pressure': 30.0,       # bar
    'chamber_temperature': 3200.0,  # K
    'gamma': 1.22,
    'molecular_weight': 26.0,
    'mdot_total': 2.0,
    'chamber_diameter': 0.12,
    'chamber_length': 0.40,
    'burn_time': 8.0,
    'throat_diameter': 0.03,
}


def _pdf_text(pdf_bytes):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages), '\n'.join(
        page.extract_text() or '' for page in reader.pages
    )


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def real_analyses():
    """Gerçek analizör çıktıları — PDF'e girecek kaynak veriler."""
    heat = HeatTransferAnalyzer().analyze_heat_transfer(
        BASE_MOTOR, material='steel_4130', wall_thickness=0.006
    )
    structural = StructuralAnalyzer().analyze_structure(
        BASE_MOTOR, material='steel_4130'
    )
    return heat, structural


@pytest.fixture(scope='module')
def motor_with_analyses(real_analyses):
    heat, structural = real_analyses
    motor_data = dict(BASE_MOTOR)
    motor_data.update({
        'motor_type': 'hybrid',
        'motor_name': 'PDF-TEST',
        'thrust': 4200.0,
        'specific_impulse': 214.3,
        'total_impulse': 33600.0,
        'heat_transfer_analysis': heat,
        'structural_analysis': structural,
    })
    return motor_data


@pytest.fixture(scope='module')
def complete_pdf(client, motor_with_analyses):
    r = client.post('/api/export-pdf/complete', json={
        'motor_data': motor_with_analyses,
        'analysis_results': {},
        'charts': [],
    })
    assert r.status_code == 200
    return r.data


class TestPdfGeneration:
    def test_returns_valid_pdf(self, client, motor_with_analyses):
        r = client.post('/api/export-pdf/complete', json={
            'motor_data': motor_with_analyses,
            'analysis_results': {}, 'charts': [],
        })
        assert r.status_code == 200
        assert r.content_type == 'application/pdf'
        assert r.data[:5] == b'%PDF-'

    @pytest.mark.parametrize('report_type', ['summary', 'technical', 'complete'])
    def test_all_report_types_200(self, client, motor_with_analyses, report_type):
        r = client.post(f'/api/export-pdf/{report_type}', json={
            'motor_data': motor_with_analyses,
            'analysis_results': {}, 'charts': [],
        })
        assert r.status_code == 200
        assert r.data[:5] == b'%PDF-'

    def test_page_count_and_size_reasonable(self, complete_pdf):
        pages, _ = _pdf_text(complete_pdf)
        assert 3 <= pages <= 12, f"sayfa sayısı makul değil: {pages}"
        assert len(complete_pdf) < 1_500_000, "PDF boyutu şişmiş"


class TestRealValuesInPdf:
    def test_real_safety_factors_in_pdf(self, complete_pdf, real_analyses):
        _, structural = real_analyses
        _, text = _pdf_text(complete_pdf)
        assert 'Structural Analysis' in text
        # Gerçek SF değerleri ('{:.2f}' formatı) raporda geçmeli
        sf_pressure = f"{structural['safety_factor_pressure']:.2f}"
        sf_total = f"{structural['safety_factor_total']:.2f}"
        assert sf_pressure in text, f"gerçek SF_basınç ({sf_pressure}) PDF'te yok"
        assert sf_total in text, f"gerçek SF_toplam ({sf_total}) PDF'te yok"
        # Bu senaryonun gerçek SF'leri 4.0 değil — bunu fixture doğrular,
        # böylece aşağıdaki '4.00 yok' iddiası anlamlıdır.
        assert abs(structural['safety_factor_total'] - 4.0) > 0.05
        assert abs(structural['safety_factor_pressure'] - 4.0) > 0.05

    def test_no_fixed_sf_4_remnant(self, complete_pdf):
        # Eski dürüstlük sorunu: rapor katmanı sabit SF 4.0 basıyordu.
        # Gerçek SF'ler 4.0'dan uzak seçildiği için PDF'te '4.00' string'i
        # hiç görünmemeli (sabit değer geri sızarsa bu test kırılır).
        _, text = _pdf_text(complete_pdf)
        assert '4.00' not in text
        assert 'Standard aerospace safety factor' not in text

    def test_real_structural_status_in_pdf(self, complete_pdf, real_analyses):
        _, structural = real_analyses
        _, text = _pdf_text(complete_pdf)
        status = structural['safety_analysis']['status']
        assert status in text, f"gerçek yapısal durum ({status}) PDF'te yok"

    def test_real_thermal_values_in_pdf(self, complete_pdf, real_analyses):
        heat, _ = real_analyses
        _, text = _pdf_text(complete_pdf)
        assert 'Thermal Analysis' in text
        max_wall = f"{heat['wall_analysis']['max_temperature']:.1f}"
        heat_flux = f"{heat['gas_side_analysis']['heat_flux'] / 1e6:.2f}"
        assert max_wall in text, f"gerçek cidar sıcaklığı ({max_wall}) PDF'te yok"
        assert heat_flux in text, f"gerçek ısı akısı ({heat_flux}) PDF'te yok"

    def test_real_performance_values_in_pdf(self, complete_pdf):
        _, text = _pdf_text(complete_pdf)
        # Motor sonucundaki gerçek değerler (thrust*burn_time = 33600 değil
        # rastgele; total_impulse motor sonucundan geliyor)
        assert '4200.0' in text     # thrust
        assert '214.3' in text      # Isp
        assert '33600.0' in text    # gerçek toplam impuls

    def test_request_safety_summary_preserved(self, client, motor_with_analyses):
        """İstekle gelen GERÇEK risk sınıfları yönetici özetine girer.

        v2.6.26 (PDF-710-5): bu test eskiden ``{'overall_rating': 8.2}``
        gönderip PDF'te '8.2' ve 'ACCEPTABLE' arıyordu. O 0-10 ölçeğini
        depoda üreten HİÇBİR kod yoktu ve '>7/10 kabul edilebilir' eşiğinin
        hiçbir dayanağı yoktu — yani test, yalnız elle kurulmuş bir istekle
        ulaşılan uydurma bir damgayı sabitliyordu. Artık özet
        /analyze_safety'nin gerçek risk_assessment alanlarından basılır.
        """
        r = client.post('/api/export-pdf/complete', json={
            'motor_data': motor_with_analyses,
            'analysis_results': {
                'safety': {
                    'risk_assessment': {
                        'risk_level': 'MEDIUM',
                        'acceptability': 'ACCEPTABLE_WITH_CONTROLS',
                    },
                },
            },
            'charts': [],
        })
        assert r.status_code == 200
        _, text = _pdf_text(r.data)
        assert 'MEDIUM' in text
        assert 'ACCEPTABLE WITH CONTROLS' in text
        # Dayanaksız sayısal ölçek geri gelmemeli
        assert '/10' not in text

    def test_arbitrary_rating_no_longer_stamps_a_verdict(self, client,
                                                         motor_with_analyses):
        """Uydurma 'overall_rating' artık hüküm ürettiremez (regresyon bekçisi)."""
        r = client.post('/api/export-pdf/complete', json={
            'motor_data': motor_with_analyses,
            'analysis_results': {
                'safety': {'overall_rating': 9.9, 'critical_issues': []},
            },
            'charts': [],
        })
        assert r.status_code == 200
        _, text = _pdf_text(r.data)
        assert '9.9/10' not in text
        assert 'acceptance threshold' not in text.lower()


class TestNoFabricationWithoutData:
    def test_no_structural_section_without_analysis(self, client):
        # Analiz yoksa yapısal bölüm hiç basılmaz — SF uydurulmaz.
        r = client.post('/api/export-pdf/complete', json={
            'motor_data': {'motor_type': 'hybrid', 'motor_name': 'BARE',
                           'thrust': 1000.0, 'burn_time': 5.0},
            'analysis_results': {}, 'charts': [],
        })
        assert r.status_code == 200
        _, text = _pdf_text(r.data)
        assert 'Safety Factor (pressure' not in text
        assert '4.00' not in text

    def test_missing_values_render_na(self, client):
        # Performans alanları eksikse 0.0 sabiti yerine N/A basılır.
        r = client.post('/api/export-pdf/summary', json={
            'motor_data': {'motor_type': 'hybrid', 'motor_name': 'NA-TEST'},
            'analysis_results': {}, 'charts': [],
        })
        assert r.status_code == 200
        _, text = _pdf_text(r.data)
        assert 'N/A' in text


class TestCompletePackageHonesty:
    """/api/generate-complete-package sabit SF 4.0 kalıntısı temizliği."""

    PACKAGE_OPTIONS_ANALYSIS_ONLY = {
        'include_cad': False, 'include_openrocket': False,
        'include_analysis': True, 'include_manufacturing': False,
    }

    def test_real_sf_when_structural_present(self, client, motor_with_analyses,
                                             real_analyses):
        _, structural = real_analyses
        r = client.post('/api/generate-complete-package', json={
            'motor_data': motor_with_analyses,
            'package_options': self.PACKAGE_OPTIONS_ANALYSIS_ONLY,
        })
        assert r.status_code == 200
        section = r.get_json()['complete_package']['analysis']['safety_analysis']
        assert section['safety_factor'] == pytest.approx(
            structural['safety_factor'])
        assert section['status'] == structural['safety_analysis']['status']
        assert 'burst_pressure' not in section  # uydurma Pc*4.0 kaldırıldı
        assert 'material_limits' not in section

    def test_not_analyzed_when_structural_absent(self, client):
        r = client.post('/api/generate-complete-package', json={
            'motor_data': {'motor_name': 'BARE', 'chamber_pressure': 30.0},
            'package_options': self.PACKAGE_OPTIONS_ANALYSIS_ONLY,
        })
        assert r.status_code == 200
        section = r.get_json()['complete_package']['analysis']['safety_analysis']
        assert section['safety_factor'] is None
        assert section['status'] == 'NOT ANALYZED'
        assert 'burst_pressure' not in section
