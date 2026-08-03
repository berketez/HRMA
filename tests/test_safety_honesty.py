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

    @staticmethod
    def _likelihood(wall_thickness):
        result = SafetyAnalyzer().analyze_comprehensive_safety(
            motor_data=dict(MOTOR, wall_thickness=wall_thickness),
            propellant_mass=5, propellant_type='composite',
            facility_type='test_stand', material='steel_4130')
        return (result.get('structural_safety') or {}).get(
            'failure_likelihood') or {}

    def test_likelihood_still_responds_to_the_design(self):
        """Nitel sınıf da olsa tasarımla değişmeli — sabit etiket olmasın.

        Faz 5 / H5-3 düzeltmesi — BEKÇİ KENDİ SÖZLEŞMESİNİ SINAMIYORDU:
        Bu test eskiden ``@parametrize('wall_thickness', [0.002, 0.005,
        0.020])`` ile üç AYRI koşu yapıp her birinde yalnız
        ``likelihood_class is not None`` bakıyordu. İki kusuru vardı:
        (1) parametrizasyon yüzünden üç değer birbiriyle HİÇ
        karşılaştırılmıyordu; (2) seçilen üç kalınlığın üçü de aynı banda
        düşüyordu.

        Ölçüm (3 Ağustos 2026, steel_4130, Pc=40 bar, D=100 mm):

            0,50 mm -> HIGH     2,00 mm -> LOW
            1,00 mm -> MEDIUM   5,00 mm -> LOW      20,0 mm -> LOW

        Yani eski testin seçtiği 2/5/20 mm'nin üçü de LOW; kod
        ``likelihood_class = 'LOW'`` diye SABİTLENSE test yine yeşil
        kalıyordu. Artık bant sınırlarını geçen üç kalınlık tek testte
        çözülür ve sınıfların GERÇEKTEN farklı olduğu iddia edilir.
        """
        siniflar = {wt: self._likelihood(wt).get('likelihood_class')
                    for wt in (0.0005, 0.001, 0.005)}
        assert None not in siniflar.values(), siniflar
        assert len(set(siniflar.values())) == 3, (
            f'nitel sınıf tasarımla değişmiyor (sabit etiket?): {siniflar}')

    def test_likelihood_does_not_get_worse_as_the_wall_gets_thicker(self):
        """Yön de doğru olmalı: kalın cidar daha KÖTÜ sınıf veremez."""
        sira = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
        kalinliklar = (0.0005, 0.001, 0.002, 0.005, 0.020)
        skorlar = [sira[self._likelihood(wt)['likelihood_class']]
                   for wt in kalinliklar]
        assert skorlar == sorted(skorlar, reverse=True), (
            f'cidar kalınlaştıkça risk sınıfı artıyor: '
            f'{dict(zip(kalinliklar, skorlar))}')


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


class TestSafetyLimitsHasNoUnreachableSurface:
    """H5-8 (Faz 5): ``safety_limits`` fiilen ölü koddan temizlendi.

    Ölçüm (3 Ağustos 2026, HEAD 9d3728e — temizlik öncesi, depo genelinde
    grep; kendi tanımı ve kendi dosyası hariç):

        comprehensive_check    -> üretim 0, test 0
        check_chamber_pressure -> üretim 0, test 0
        check_wall_temperature -> üretim 0, test 0
        check_thrust           -> üretim 0, test 0
        check_mass_flow_rate   -> üretim 0, test 0
        MotorValidator         -> depo genelinde 0 referans
        check_throat_diameter  -> üretim 1 (liquid_rocket_engine.py:2723)

    Dört ``check_*`` yalnız ``comprehensive_check`` içinden çağrılıyordu, o
    da hiç çağrılmıyordu: hiçbiri hiçbir zaman koşmadı. 361 satırlık modül
    "çalışan kapsamlı güvenlik denetimi" izlenimi veriyordu. Bu sınıf, ölü
    yüzeyin ÇAĞRI YERİ OLMADAN geri gelmesini engeller.
    """

    #: Üretimde çağrılan yüzey.
    URETIMDE_CANLI = {'check_throat_diameter'}
    #: Üretimde çağrılmayan ama BİLEREK korunan test yüzeyi (gerekçesi
    #: modülün docstring'inde): 2026-07-28 fail-open düzeltmesinin bekçileri.
    TEST_YUZEYI = {'generate_safety_report', 'clear_violations'}

    def test_public_surface_is_exactly_what_is_declared(self):
        genel = {ad for ad in vars(SafetyLimits)
                 if not ad.startswith('_') and callable(vars(SafetyLimits)[ad])}
        assert genel == self.URETIMDE_CANLI | self.TEST_YUZEYI, (
            'safety_limits genel yüzeyi beyanla uyuşmuyor; yeni bir metot '
            'eklendiyse ÇAĞRI YERİYLE birlikte gelmeli ve burada '
            f'beyan edilmeli (bulunan: {sorted(genel)})')

    def test_live_entry_point_is_still_wired(self):
        """Tek canlı çağrı yeri kaybolmamalı — kaybolursa modül tümden ölür."""
        import pathlib
        kaynak = (pathlib.Path(__file__).resolve().parents[1]
                  / 'hrma' / 'engines' / 'liquid_rocket_engine.py'
                  ).read_text(encoding='utf-8')
        assert 'safety.check_throat_diameter(' in kaynak, (
            'safety_limits modülünün üretimdeki TEK çağrı yeri kaybolmuş')

    def test_removed_dead_surface_did_not_come_back(self):
        import hrma.analysis.safety_limits as modul
        for ad in ('comprehensive_check', 'check_chamber_pressure',
                   'check_wall_temperature', 'check_thrust',
                   'check_mass_flow_rate'):
            assert not hasattr(SafetyLimits, ad), (
                f'{ad} geri gelmiş — üretim çağrısı olmadan eklenemez')
        assert not hasattr(modul, 'MotorValidator'), (
            'MotorValidator geri gelmiş — depo genelinde hiç referansı yoktu')


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
        """C1b: dize değil DESEN aranır.

        Ölçüm (2026-08-02): bu test yalnız 'conducted using NASA-standard
        methodologies' dizesini arıyordu. ``pdf_generator.py:992`` teknik
        ekte 'This analysis **employs** NASA-standard methodologies ...'
        yazıyordu; fiil farklı olduğu için yakalanmadı ve test kusur
        ayaktayken YEŞİL kaldı. Artık fiilden bağımsız bütün varyantlar
        (NASA-standard / NASA standard / NASA standards methodology|
        methodologies) yakalanır. Kaldırılan kusuru birebir alıntılayan
        düzeltme yorumları muaf tutulur (tools/iddia_lint.py ile aynı
        işaretler) — yoksa bu docstring'in kendisi testi kırardı.
        """
        import re

        pattern = re.compile(r'NASA[-\s]standards?\s+methodolog\w*',
                             re.IGNORECASE)
        hits = []
        exempt_block = False
        for index, line in enumerate(self._source().splitlines(), 1):
            if 'IDDIA-LINT-MUAF-BASLANGIC' in line:
                exempt_block = True
                continue
            if 'IDDIA-LINT-MUAF-BITIS' in line:
                exempt_block = False
                continue
            if exempt_block or 'IDDIA-LINT-MUAF' in line:
                continue
            if pattern.search(line):
                hits.append((index, line.strip()))
        assert not hits, hits

    def test_arbitrary_acceptance_threshold_removed(self):
        source = self._source()
        assert 'SAFETY_RATING_ACCEPTABLE = 7.0' not in source
        assert 'acceptance threshold' not in source
