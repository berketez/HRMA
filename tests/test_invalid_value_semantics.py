"""'Hesaplanamadı' ile 'sıfır' ayrımının bekçileri (v2.6.26).

Kapsanan bulgular:
  SAN-ZERO-6   — motor_validation.sanitize_export_data eskiden None/NaN/Inf
                 değerleri 0'a çeviriyordu; NaN boğaz çapı sessizce 0 olup
                 İMALATA gidebilecek STL'nin geometrisini değiştiriyordu.
                 Yeni sözleşme: sonlu olmayan sayı None döner, 0 gerçek bir
                 ölçüm olarak korunur. Listelerdeki çıplak sayılar da taranır.
  SAN-INCONS-7 — app.py::sanitize_json_values (v2.6.2) ile motor_validation
                 arasındaki zıt semantik giderildi; iki fonksiyon aynı sayısal
                 girdiye aynı değeri üretmeli.
  ZERO-PAT-8   — openrocket uçuş önizlemesi çözülemeyen itici kütlesini 0 kg
                 sayıyordu; artık 'insufficient_data' ile atlanır. .eng
                 dosyası inert kütle yokken açık WARNING satırı taşır.

Ölçüt her yerde aynı: hesaplanmamış bir değer asla gerçek bir sayı gibi
görünmez. Bu testlerden herhangi biri, düzeltme geri alınırsa kırmızıya döner.
"""

import math
import warnings

import numpy as np
import pytest

from hrma.export.openrocket_integration import OpenRocketExporter
from hrma.validation.motor_validation import MotorDataValidator

warnings.filterwarnings('ignore')

NAN = float('nan')
INF = float('inf')


@pytest.fixture()
def validator():
    return MotorDataValidator()


# ---------------------------------------------------------------------------
# (a) SAN-ZERO-6: sanitize_export_data sözleşmesi
# ---------------------------------------------------------------------------

class TestSanitizeExportSemantics:

    def test_nan_becomes_none_not_zero(self, validator):
        """NaN 'hesaplanamadı'dır; 0 m boğaz çapı DEĞİLDİR."""
        out = validator.sanitize_export_data({'throat_diameter': NAN})
        assert out['throat_diameter'] is None
        assert out['throat_diameter'] != 0

    def test_inf_and_negative_inf_become_none(self, validator):
        out = validator.sanitize_export_data(
            {'chamber_pressure': INF, 'isp': -INF})
        assert out['chamber_pressure'] is None
        assert out['isp'] is None

    def test_none_stays_none(self, validator):
        out = validator.sanitize_export_data({'burn_time': None})
        assert out['burn_time'] is None

    def test_real_zero_is_preserved(self, validator):
        """0 gerçek bir ölçümdür; None'a ya da başka şeye dönüşmemeli."""
        out = validator.sanitize_export_data({'a': 0, 'b': 0.0})
        assert out['a'] == 0 and out['a'] is not None
        assert out['b'] == 0.0 and out['b'] is not None

    def test_finite_values_pass_through(self, validator):
        out = validator.sanitize_export_data(
            {'thrust': 2000.0, 'n': 7, 'name': 'HRM'})
        assert out['thrust'] == 2000.0
        assert out['n'] == 7
        assert out['name'] == 'HRM'

    def test_nested_dict_is_sanitized(self, validator):
        out = validator.sanitize_export_data(
            {'nested': {'wall_thickness': NAN, 'ok': 6.0}})
        assert out['nested']['wall_thickness'] is None
        assert out['nested']['ok'] == 6.0

    def test_bare_numbers_in_lists_are_sanitized(self, validator):
        """Eski kod listelerde yalnız dict elemanlarını geziyordu;
        listedeki çıplak NaN hayatta kalıyordu (SAN-ZERO-6 iç tutarsızlık)."""
        out = validator.sanitize_export_data({'curve': [1.0, NAN, 3.0, INF]})
        assert out['curve'] == [1.0, None, 3.0, None]

    def test_dicts_inside_lists_still_recursed(self, validator):
        out = validator.sanitize_export_data(
            {'items': [{'x': NAN}, {'x': 2.0}]})
        assert out['items'][0]['x'] is None
        assert out['items'][1]['x'] == 2.0

    def test_nested_lists_are_sanitized(self, validator):
        out = validator.sanitize_export_data({'grid': [[1.0, NAN], [INF]]})
        assert out['grid'] == [[1.0, None], [None]]

    def test_tuple_treated_as_list_not_stringified(self, validator):
        """Eski kod tuple'ı str() ile "(1.0, nan)" metnine çeviriyordu."""
        out = validator.sanitize_export_data({'pair': (1.0, NAN)})
        assert out['pair'] == [1.0, None]

    def test_numpy_scalars_are_numbers_not_strings(self, validator):
        out = validator.sanitize_export_data({
            'a': np.float64(NAN),
            'b': np.float32(2.5),
            'c': np.int64(7),
        })
        assert out['a'] is None
        assert out['b'] == pytest.approx(2.5)
        assert out['c'] == 7
        assert not isinstance(out['b'], str)
        assert not isinstance(out['c'], str)

    def test_numpy_array_elements_sanitized(self, validator):
        out = validator.sanitize_export_data({'arr': np.array([1.0, np.nan])})
        assert out['arr'] == [1.0, None]

    def test_bool_flags_are_preserved(self, validator):
        """bool int alt sınıfıdır; 1.0/0.0 float'ına dönüşmemeli."""
        out = validator.sanitize_export_data({'flag': True, 'off': False})
        assert out['flag'] is True
        assert out['off'] is False

    def test_null_bytes_stripped_from_strings(self, validator):
        out = validator.sanitize_export_data({'name': ' HRM\x00 '})
        assert out['name'] == 'HRM'


# ---------------------------------------------------------------------------
# (b) ZERO-PAT-8: uçuş önizlemesi çözülemeyen itici kütlesiyle koşmaz
# ---------------------------------------------------------------------------

class TestFlightProfileInsufficientData:

    @pytest.mark.parametrize('bad_mass', [NAN, INF, -2.0, 0.0, None, 'x'])
    def test_unresolvable_prop_mass_skips_simulation(self, bad_mass):
        """Eski kod `or 0.0` ile 0 kg iticiyle yörünge 'hesaplıyordu'."""
        motor = {'thrust': 2000.0, 'burn_time': 8.0,
                 'propellant_mass_total': bad_mass}
        profile = OpenRocketExporter().generate_flight_profile(motor)
        assert profile['status'] == 'insufficient_data'
        assert 'propellant_mass_total' in profile['missing_fields']
        assert profile['altitude_data'] == []
        assert profile['max_altitude'] is None
        assert profile['performance_summary'] is None

    def test_missing_prop_mass_key_skips_simulation(self):
        profile = OpenRocketExporter().generate_flight_profile(
            {'thrust': 2000.0, 'burn_time': 8.0})
        assert profile['status'] == 'insufficient_data'

    def test_valid_prop_mass_still_simulates(self):
        """Fazla agresif olunmadığının kanıtı: gerçek kütleyle profil çalışır."""
        motor = {'thrust': 2000.0, 'burn_time': 8.0,
                 'propellant_mass_total': 3.0, 'isp': 220.0}
        profile = OpenRocketExporter().generate_flight_profile(motor)
        assert profile['status'] == 'ok'
        assert profile['max_altitude'] > 0
        assert len(profile['altitude_data']) == len(profile['time_data'])
        assert all(math.isfinite(v) for v in profile['altitude_data'])


# ---------------------------------------------------------------------------
# (c) ZERO-PAT-8: .eng inert kütle uyarısı + katı sözdizim korunur
# ---------------------------------------------------------------------------

def _motor_line(eng: str) -> str:
    return [l for l in eng.splitlines() if l and not l.startswith(';')][0]


class TestEngInertMassDeclaration:

    BARE = {'motor_name': 'BARE', 'thrust': 1000.0, 'burn_time': 5.0,
            'propellant_mass_total': 2.0, 'throat_diameter': 0.02,
            'chamber_length': 0.3, 'total_impulse': 5000.0}

    def test_missing_inert_mass_writes_warning_comment(self):
        eng = OpenRocketExporter().export_motor_file(dict(self.BARE))
        assert 'WARNING: loaded mass EXCLUDES motor case mass' in eng
        # Uyarı motor satırından ÖNCE gelmeli (RASP: başlık yorumları üstte)
        warn_idx = eng.index('WARNING: loaded mass EXCLUDES')
        motor_idx = eng.index(_motor_line(eng))
        assert warn_idx < motor_idx

    def test_present_inert_mass_no_warning(self):
        data = dict(self.BARE)
        data['dry_mass'] = 4.0
        eng = OpenRocketExporter().export_motor_file(data)
        assert 'WARNING: loaded mass EXCLUDES' not in eng
        prop, loaded = (float(x) for x in _motor_line(eng).split()[4:6])
        assert loaded - prop == pytest.approx(4.0, abs=1e-6)

    def test_eng_syntax_stays_strict(self):
        """Uyarı satırı RASP sözdizimini bozmamalı: motor satırı 7 alan,
        veri satırları iki float, yorumlar ';' ile başlar."""
        eng = OpenRocketExporter().export_motor_file(dict(self.BARE))
        payload = [l for l in eng.splitlines() if l and not l.startswith(';')]
        motor_fields = payload[0].split()
        assert len(motor_fields) == 7
        for field in motor_fields[1:3] + motor_fields[4:6]:
            assert math.isfinite(float(field))
        for line in payload[1:]:
            t, f = (float(x) for x in line.split())
            assert math.isfinite(t) and math.isfinite(f)


# ---------------------------------------------------------------------------
# (d) SAN-INCONS-7 + uçtan uca: NaN gönderince sessiz 0 geometrili STL BİTTİ
#     (app importu yavaştır; bu sınıflar dosyanın sonunda koşar)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestSemanticsAlignedWithApp:

    def test_same_numeric_semantics_as_sanitize_json_values(self, client):
        """SAN-INCONS-7: JSON yanıt filtresi ile STL yolu artık aynı dili
        konuşur — sonlu olmayan sayı iki tarafta da null/None olur."""
        from hrma.app import sanitize_json_values
        payload = {'nan': NAN, 'inf': INF, 'ninf': -INF, 'none': None,
                   'zero': 0.0, 'val': 1.5, 'flag': True,
                   'list': [1.0, NAN], 'nested': {'x': INF}}
        via_app = sanitize_json_values(payload)
        via_validator = MotorDataValidator().sanitize_export_data(payload)
        assert via_app == via_validator


class TestExportStlNoSilentZeroGeometry:
    """Ampirik bulgu (v2.6.26 doğrulama turu): throat_diameter=NaN ile
    /api/export-stl HTTP 200 ve GERÇEK değerlerden FARKLI bir STL dönüyordu
    (md5 b59447a0... vs cc63ecca...). Bu sınıf o davranışın bittiğini kanıtlar.
    """

    GOOD = {
        'motor_type': 'hybrid',
        'motor_name': 'SEMTEST',
        'chamber_diameter': 0.15,
        'chamber_length': 0.5,
        'port_diameter': 0.05,
        'throat_diameter': 0.03,
        'exit_diameter': 0.06,
        'wall_thickness': 0.006,
        'thrust': 2000.0,
        'burn_time': 8.0,
    }

    def test_nan_in_optional_geometry_never_yields_stl(self, client):
        """NaN boğaz çapı ve cidar kalınlığı: yanıt STL OLAMAZ."""
        bad = dict(self.GOOD)
        bad['throat_diameter'] = NAN
        bad['wall_thickness'] = NAN
        r = client.post('/api/export-stl', json={'motor_data': bad})
        assert r.status_code != 200, \
            'NaN geometriden sessizce STL üretildi - SAN-ZERO-6 geri geldi'
        assert 'sla' not in (r.headers.get('Content-Type') or '')

    def test_nan_in_required_geometry_fails_closed(self, client):
        bad = dict(self.GOOD)
        bad['chamber_diameter'] = NAN
        r = client.post('/api/export-stl', json={'motor_data': bad})
        assert r.status_code == 422
        j = r.get_json()
        assert 'chamber_diameter' in j['missing_fields']

    def test_valid_geometry_still_exports_stl(self, client):
        """Düzeltme çalışan exportu KIRMAMALI: gerçek geometri STL verir."""
        pytest.importorskip('trimesh')
        r = client.post('/api/export-stl', json={'motor_data': dict(self.GOOD)})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert 'sla' in r.headers['Content-Type']
        assert len(r.data) > 10000


# ---------------------------------------------------------------------------
# (e) B11 (Faz 5): doğrulayıcı METİN sayıda çökmez
# ---------------------------------------------------------------------------

class TestValidatorSurvivesStringNumbers:
    """Sayısal alanın metin gelmesi doğrulayıcıyı DÜŞÜREMEZ.

    Ölçüm (3 Ağustos 2026, HEAD 9d3728e — düzeltme öncesi):
    ``validate_motor_data({... 'thrust': '1000' ...}, 'hybrid')``
    ``TypeError: '>' not supported between instances of 'str' and 'int'``
    ile çöküyordu; ``/calculate`` bu ham Python hatasını HTTP 400 gövdesinde
    kullanıcıya gösteriyordu. Aynısı ``burn_time``, ``chamber_temperature``
    ve ``throat_diameter`` için de ölçüldü.

    Sözleşme: doğrulayıcı istisna atmaz; sayısal olmayan alan için
    ANLAŞILIR bir hata mesajı üretir. Form gönderimi ve kayıtlı ``.hrma``
    projeleri sayıları metin taşıyabildiği için bu en olağan bozulmadır.
    """

    BASE = {'thrust': 1000, 'burn_time': 5, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o', 'of_ratio': 6.0, 'chamber_diameter': 0.1}

    @pytest.mark.parametrize('field', [
        'thrust', 'burn_time', 'chamber_temperature',
        'throat_diameter', 'exit_diameter', 'chamber_pressure'])
    def test_string_number_does_not_raise(self, validator, field):
        data = dict(self.BASE)
        data[field] = '1000' if field in ('thrust', 'chamber_temperature') \
            else '0.02'
        is_valid, messages = validator.validate_motor_data(data, 'hybrid')
        # İstisna atmadıysa buraya gelinir; ayrıca hüküm de tutarlı olmalı.
        assert isinstance(is_valid, bool)
        assert isinstance(messages, list)

    @pytest.mark.parametrize('field', [
        'thrust', 'burn_time', 'throat_diameter', 'exit_diameter'])
    def test_string_number_is_reported_as_non_numeric(self, validator, field):
        """Hata metni ham Python istisnası değil, alanı adlandıran cümledir."""
        data = dict(self.BASE)
        data[field] = '0.02'
        is_valid, messages = validator.validate_motor_data(data, 'hybrid')
        assert is_valid is False
        birlesik = ' | '.join(messages)
        assert f'{field} must be numeric' in birlesik, birlesik
        assert 'not supported between instances' not in birlesik, (
            'ham TypeError metni kullanıcıya sızıyor — B11 geri gelmiş')

    def test_numeric_path_still_emits_the_safety_warnings(self, validator):
        """Düzeltme uyarıları SUSTURMAMALI: eşikler hâlâ tetiklenmeli."""
        data = dict(self.BASE, thrust=60000, burn_time=90,
                    chamber_temperature=4000)
        is_valid, messages = validator.validate_motor_data(data, 'hybrid')
        assert is_valid is True
        birlesik = ' | '.join(messages).lower()
        assert 'high thrust' in birlesik
        assert 'extreme temperature' in birlesik
        assert 'long burn time' in birlesik

    def test_calculate_endpoint_returns_a_readable_message(self, client):
        """Uçtan uca: /calculate artık ham TypeError göstermez."""
        body = {'motor_type': 'hybrid', 'thrust': '1000', 'burn_time': 5,
                'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'of_ratio': 6.0}
        r = client.post('/calculate', json=body,
                        headers={'Host': '127.0.0.1:8080'})
        assert r.status_code == 400
        govde = r.get_data(as_text=True)
        assert 'thrust must be numeric' in govde, govde[:300]
        assert 'not supported between instances' not in govde
