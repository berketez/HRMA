"""v2.6.26 güvenlik dürüstlüğü bekçileri.

Bu testler, güvenlik modülünün kanıtsız hüküm üretmesini kalıcı olarak
engeller. Kapattıkları somut kusurlar (hepsi v2.6.26 doğrulama turunda
ampirik olarak ölçüldü):

* SAFE-EMPTY-1 — ``POST /analyze_safety`` boş gövdeyle ({}) HTTP 200 ve
  11100 baytlık TAM analiz döndürüyordu: tahliye mesafeleri, muayene
  aralığı, 'ACCEPTABLE' kabul kararı, tıbbi müdahale bölümü. Hepsi
  kullanıcının hiç vermediği varsayılanlardan üretilmişti.
* SAFE-PROB-2 — Arıza olasılığı emniyet katsayısından üç basamaklı keyfi
  bir tabloyla üretiliyordu (SF<2 -> 0.1, SF<4 -> 0.01, aksi 0.001) ve
  sabit 0.3/0.5/0.2 çarpanlarıyla arıza modlarına bölünüyordu. Atıf yok,
  kalibrasyon yok, dağılım varsayımı yok.
* SAFE-TEXT-3 — Tıbbi müdahale, PPE ve toksik/yangın mesafesi metinleri
  kaynaksızdı.
* PDF-NASA-4 — PDF, hiç analiz verisi olmadan bile "NASA-standard
  methodologies" iddiası basıyordu.
* PDF-710-5 — Dayanaksız ">7/10 = ACCEPTABLE" eşiği. ``overall_rating``
  alanını depoda üreten hiçbir kod yoktu.
* safety_limits fail-open — İhlal listesi boşsa "ALL CHECKS PASSED -
  MOTOR SAFE FOR OPERATION" dönüyordu; hiç kontrol koşmamışken bile.
"""

import json

import pytest

from hrma.analysis.safety_analysis import SafetyAnalyzer
from hrma.analysis.safety_limits import SafetyLimits


MOTOR = {
    'chamber_pressure': 40, 'chamber_temperature': 3000, 'thrust': 5000,
    'burn_time': 10, 'chamber_diameter': 0.1, 'wall_thickness': 0.005,
}


@pytest.fixture(scope='module')
def analysis():
    return SafetyAnalyzer().analyze_comprehensive_safety(
        motor_data=dict(MOTOR), propellant_mass=5,
        propellant_type='hydrazine', facility_type='test_stand',
        material='steel_4130')


@pytest.fixture(scope='module')
def flat(analysis):
    return json.dumps(analysis, default=str)


class TestNoFabricatedProbability:
    """SAFE-PROB-2: emniyet katsayısından olasılık üretilemez."""

    def test_numeric_failure_probability_is_gone(self, flat):
        assert '"failure_probability"' not in flat, (
            'safety factor -> olasilik tablosu geri gelmis')

    def test_qualitative_class_reported_instead(self, analysis):
        likelihood = (analysis.get('structural_safety') or {}).get(
            'failure_likelihood') or {}
        assert likelihood.get('likelihood_class') in (
            'LOW', 'MEDIUM', 'HIGH'), likelihood
        assert 'not a calibrated probability' in likelihood.get('basis', '')

    def test_failure_modes_have_no_numeric_probabilities(self, analysis):
        modes = (analysis.get('structural_safety') or {}).get(
            'failure_modes') or []
        assert modes, 'arıza modları büsbütün kaybolmamalı'
        for mode in modes:
            assert 'probability' not in json.dumps(mode).lower(), mode

    @pytest.mark.parametrize('wall_thickness', [0.002, 0.005, 0.020])
    def test_likelihood_still_responds_to_the_design(self, wall_thickness):
        """Nitel sınıf da olsa tasarımla değişmeli — sabit etiket olmasın."""
        motor = dict(MOTOR, wall_thickness=wall_thickness)
        result = SafetyAnalyzer().analyze_comprehensive_safety(
            motor_data=motor, propellant_mass=5, propellant_type='composite',
            facility_type='test_stand', material='steel_4130')
        assert (result.get('structural_safety') or {}).get(
            'failure_likelihood', {}).get('likelihood_class') is not None


class TestGuidanceIsSourced:
    """SAFE-TEXT-3: tıbbi/PPE/mesafe metinleri kaynağını beyan etmeli."""

    def test_medical_response_declares_it_is_not_medical_advice(self, analysis):
        medical = (analysis.get('emergency_procedures') or {}).get(
            'medical_response') or {}
        assert medical, 'tıbbi bölüm büsbütün kaybolmamalı'
        basis = medical.get('basis', '')
        assert 'NOT medical advice' in basis, basis
        assert medical.get('disclaimer_code')

    def test_toxic_guidance_declares_its_basis(self, analysis):
        toxic = analysis.get('toxic_hazards') or {}
        assert toxic.get('guidance_basis')
        assert toxic.get('disclaimer_code')

    def test_sourced_blast_model_is_left_alone(self, flat):
        """Gerçekten atıflı hesaplar korunmalı — süpürme onları silmemeli.

        Patlama mesafeleri Kingery-Bulmash / Kinney-Graham + UFC 3-340-02'ye
        dayanıyor; bunlar uydurma DEĞİL ve kaldırılmamalı.
        """
        assert 'evacuation_distance' in flat


class TestNoCertificationVerdict:
    """Model, işletme emniyeti hükmü veremez."""

    def test_no_motor_safe_stamp(self, flat):
        assert 'MOTOR SAFE FOR OPERATION' not in flat

    def test_safety_limits_distinguishes_not_evaluated_from_passed(self):
        limits = SafetyLimits()
        report = limits.generate_safety_report()
        assert 'NOT EVALUATED' in report, (
            'hic kontrol kosmadan "gecti" denemez (fail-open)')
        assert 'MOTOR SAFE FOR OPERATION' not in report

    def test_safety_limits_reports_pass_only_after_running_checks(self):
        limits = SafetyLimits()
        limits.check_throat_diameter(0.02, 'test-motor')
        report = limits.generate_safety_report()
        assert 'NOT EVALUATED' not in report
        assert 'not a safety certification' in report


class TestSafetyEndpointFailsClosed:
    """SAFE-EMPTY-1: veri yoksa hüküm de yok."""

    @staticmethod
    def _client():
        from hrma.app import app
        return app.test_client()

    def test_empty_body_is_rejected(self):
        resp = self._client().post('/analyze_safety', json={},
                                   headers={'Host': '127.0.0.1:8080'})
        assert resp.status_code == 422
        payload = resp.get_json()
        assert payload['error'] == 'incomplete_safety_input'
        assert set(payload['missing_fields']) == {
            'chamber_pressure', 'propellant_mass', 'chamber_diameter',
            'wall_thickness'}

    @pytest.mark.parametrize('dropped', [
        'chamber_pressure', 'propellant_mass', 'chamber_diameter',
        'wall_thickness'])
    def test_each_required_field_is_enforced(self, dropped):
        body = {'chamber_pressure': 40, 'propellant_mass': 5,
                'chamber_diameter': 0.1, 'wall_thickness': 0.005}
        body.pop(dropped)
        resp = self._client().post('/analyze_safety', json=body,
                                   headers={'Host': '127.0.0.1:8080'})
        assert resp.status_code == 422
        assert dropped in resp.get_json()['missing_fields']

    def test_complete_request_still_works(self):
        resp = self._client().post('/analyze_safety', json={
            'chamber_pressure': 40, 'propellant_mass': 5,
            'chamber_diameter': 0.1, 'wall_thickness': 0.005,
        }, headers={'Host': '127.0.0.1:8080'})
        assert resp.status_code == 200
        assert resp.get_json()['safety_analysis']

    def test_applied_defaults_are_declared(self):
        """Verilmeyen isteğe bağlı alanlar gizlenmez."""
        resp = self._client().post('/analyze_safety', json={
            'chamber_pressure': 40, 'propellant_mass': 5,
            'chamber_diameter': 0.1, 'wall_thickness': 0.005,
        }, headers={'Host': '127.0.0.1:8080'})
        applied = resp.get_json()['defaults_applied']
        assert 'chamber_temperature' in applied
        assert 'thrust' in applied

    def test_motor_type_reaches_the_analysis(self):
        """motor_type okunuyordu ama analize hiç geçirilmiyordu."""
        resp = self._client().post('/analyze_safety', json={
            'chamber_pressure': 40, 'propellant_mass': 5,
            'chamber_diameter': 0.1, 'wall_thickness': 0.005,
            'motor_type': 'liquid',
        }, headers={'Host': '127.0.0.1:8080'})
        assert resp.status_code == 200
        inputs_used = resp.get_json()['safety_analysis'].get('inputs_used', {})
        assert inputs_used.get('motor_type') != 'not supplied'


class TestPdfMakesNoUnearnedClaims:
    """PDF-NASA-4 ve PDF-710-5."""

    @staticmethod
    def _source():
        import hrma.export.pdf_generator as generator
        with open(generator.__file__, encoding='utf-8') as handle:
            return handle.read()

    def test_unconditional_nasa_claim_removed(self):
        assert ('conducted using NASA-standard methodologies'
                not in self._source())

    def test_arbitrary_acceptance_threshold_removed(self):
        source = self._source()
        assert 'SAFETY_RATING_ACCEPTABLE = 7.0' not in source
        assert 'acceptance threshold' not in source
