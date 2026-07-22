"""
Merkezi katı yakıt kataloğu testleri (v2.5.2).

Doğrulananlar:
  1. Şema: her kayıt zorunlu alanları taşır, aile geçerli, sayısal alanlar
     fiziksel bantta, alias hedefleri var.
  2. burn_rate_db ile TUTARLILIK: rejim yasası olan yakıtlarda (KNDX/KNSB)
     katalog a-n değerleri merkezi yasadan türetilir; ikinci bir doğruluk
     kaynağı oluşmaz.
  3. solid_rocket_engine referans setiyle çelişki YOK: motorun tablosunda
     bulunan yakıtların rho/c*/gamma/Tc/MW değerleri birebir aynıdır.
  4. Katalog değerleri motorun override bandından geçer (seçilen yakıt
     sessizce reddedilmez).
  5. /api/propellants ucu 200 döner ve sözleşme şekli doğrudur.
"""

import math

import pytest

from hrma.data import burn_rate_db
from hrma.data.propellants_db import (
    PROPELLANTS, ALIASES, REQUIRED_FIELDS, VALID_FAMILIES,
    PROPELLANT_REFERENCE_PRESSURE_BAR,
    get_propellant, get_propellant_safe, list_propellants,
    list_propellant_keys, build_propellants_view, resolve,
    burn_rate_mps, cstar_from_thermo, mm_mpa_to_m_bar,
)

# Görev tanımındaki zorunlu yakıt seti
REQUIRED_PROPELLANT_KEYS = [
    'apcp', 'knsb', 'kndx', 'knsu', 'kner', 'htpb_ap_al',
    'double_base', 'blue_thunder',
]

TEXT_FIELDS = ('key', 'name', 'family', 'oxidizer', 'fuel',
               'burn_rate_ref', 'source', 'notes')

NUMERIC_FIELDS = ('density', 'burn_rate_a', 'burn_rate_n', 'c_star',
                  'gamma', 'flame_temperature', 'molecular_weight')


class TestSchema:
    def test_required_keys_present(self):
        for key in REQUIRED_PROPELLANT_KEYS:
            assert key in PROPELLANTS, f'missing propellant {key}'

    def test_every_record_has_required_fields(self):
        for key, rec in PROPELLANTS.items():
            missing = [f for f in REQUIRED_FIELDS if f not in rec]
            assert not missing, f'{key} missing {missing}'

    def test_text_fields_non_empty(self):
        for key, rec in PROPELLANTS.items():
            for field in TEXT_FIELDS:
                assert str(rec[field]).strip(), f'{key}.{field} is empty'

    def test_key_field_matches_dict_key(self):
        for key, rec in PROPELLANTS.items():
            assert rec['key'] == key

    def test_families_valid(self):
        for key, rec in PROPELLANTS.items():
            assert rec['family'] in VALID_FAMILIES, key

    def test_numeric_fields_finite_and_positive(self):
        for key, rec in PROPELLANTS.items():
            for field in NUMERIC_FIELDS:
                value = float(rec[field])
                assert math.isfinite(value), f'{key}.{field} not finite'
                if field != 'burn_rate_n':
                    assert value > 0, f'{key}.{field} must be positive'

    def test_physical_bands(self):
        for key, rec in PROPELLANTS.items():
            assert 500 <= rec['density'] <= 3000, key
            assert 800 <= rec['c_star'] <= 2500, key
            assert 1.05 <= rec['gamma'] <= 1.5, key
            assert 1000 <= rec['flame_temperature'] <= 4500, key
            assert 10 <= rec['molecular_weight'] <= 80, key

    def test_uniform_record_shape(self):
        """Tüm kayıtlar aynı anahtar kümesini taşır (istemci sözleşmesi)."""
        shapes = {frozenset(rec) for rec in PROPELLANTS.values()}
        assert len(shapes) == 1, 'records do not share one key set'

    def test_aliases_point_to_existing_records(self):
        for alias, target in ALIASES.items():
            assert target in PROPELLANTS, f'{alias} -> {target}'
            assert alias not in PROPELLANTS, f'{alias} shadows a record'

    def test_schema_violation_is_rejected(self):
        """Şema doğrulaması gerçekten çalışıyor mu (sessiz geçmiyor)."""
        import hrma.data.propellants_db as mod
        broken = {k: dict(v) for k, v in PROPELLANTS.items()}
        broken['apcp'].pop('c_star')
        original = mod.PROPELLANTS
        try:
            mod.PROPELLANTS = broken
            with pytest.raises(ValueError):
                mod._validate_propellants()
        finally:
            mod.PROPELLANTS = original


class TestApi:
    def test_resolve_and_get(self):
        assert resolve('KNDX') == 'kndx'
        assert resolve('sorbitol') == 'knsb'
        assert resolve('pban') == 'pban_ap_al'
        with pytest.raises(KeyError):
            resolve('unobtanium')
        assert get_propellant_safe('unobtanium') is None
        assert get_propellant('bp')['key'] == 'black_powder'

    def test_get_returns_independent_copy(self):
        rec = get_propellant('apcp')
        rec['density'] = 1.0
        assert PROPELLANTS['apcp']['density'] != 1.0

    def test_list_filters_by_family(self):
        assert set(list_propellant_keys()) == set(PROPELLANTS)
        sugar = list_propellant_keys('sugar')
        assert {'kndx', 'knsb', 'knsu', 'kner'} <= set(sugar)
        for key in sugar:
            assert PROPELLANTS[key]['family'] == 'sugar'
        with pytest.raises(ValueError):
            list_propellant_keys('not_a_family')

    def test_list_propellants_returns_records(self):
        records = list_propellants('composite')
        assert records and all(r['family'] == 'composite' for r in records)
        assert all('name' in r and 'key' in r for r in records)

    def test_view_includes_aliases(self):
        view = build_propellants_view()
        assert 'sucrose' in view and view['sucrose']['key'] == 'knsu'


class TestBurnRateConsistency:
    def test_regime_law_propellants_derive_from_central_db(self):
        """KNDX/KNSB a-n değerleri merkezi burn_rate_db'den gelir."""
        for key in burn_rate_db.BURN_RATE_LAWS:
            assert key in PROPELLANTS, f'{key} missing from catalogue'
            rec = PROPELLANTS[key]
            coeffs = burn_rate_db.resolve_engine_coeffs(
                key, PROPELLANT_REFERENCE_PRESSURE_BAR)
            assert rec['burn_rate_a'] == pytest.approx(coeffs['a'], rel=1e-12)
            assert rec['burn_rate_n'] == pytest.approx(coeffs['n'], rel=1e-12)
            assert rec['has_regime_law'] is True
            assert rec['validated'] is True
            assert rec['burn_rate_reference_pressure_bar'] == \
                PROPELLANT_REFERENCE_PRESSURE_BAR

    def test_catalog_pair_reproduces_central_rate_at_reference_pressure(self):
        p = PROPELLANT_REFERENCE_PRESSURE_BAR
        for key in burn_rate_db.BURN_RATE_LAWS:
            rec = PROPELLANTS[key]
            catalog_rate = rec['burn_rate_a'] * p ** rec['burn_rate_n']
            central_rate = burn_rate_db.burn_rate_mps(key, p * 1e5)
            assert catalog_rate == pytest.approx(central_rate, rel=1e-9)

    def test_burn_rate_helper_uses_regime_law_off_reference_pressure(self):
        """Referans dışı basınçta yardımcı merkezi (parçalı) yasayı kullanır."""
        p_bar = 10.0  # 1 MPa -> KNDX'te farklı rejim
        rec = PROPELLANTS['kndx']
        naive = rec['burn_rate_a'] * p_bar ** rec['burn_rate_n']
        central = burn_rate_db.burn_rate_mps('kndx', p_bar * 1e5)
        assert burn_rate_mps('kndx', p_bar) == pytest.approx(central, rel=1e-9)
        assert naive != pytest.approx(central, rel=1e-3)

    def test_non_regime_propellants_use_own_pair(self):
        for key, rec in PROPELLANTS.items():
            if rec['has_regime_law']:
                continue
            expected = rec['burn_rate_a'] * 40.0 ** rec['burn_rate_n']
            assert burn_rate_mps(key, 40.0) == pytest.approx(expected)
            assert rec['validated'] is False

    def test_burn_rates_are_physically_plausible(self):
        """40 bar'da 1-40 mm/s bandı (katı yakıt pratiği)."""
        for key in PROPELLANTS:
            rate_mmps = burn_rate_mps(key, 40.0) * 1000.0
            assert 1.0 < rate_mmps < 40.0, f'{key}: {rate_mmps:.2f} mm/s'

    def test_unit_conversion_helper(self):
        # r[mm/s] = 8.0*(P[MPa])^0.4 -> 1 MPa = 10 bar'da aynı hız
        a = mm_mpa_to_m_bar(8.0, 0.4)
        assert a * 10.0 ** 0.4 == pytest.approx(8.0 / 1000.0, rel=1e-12)

    def test_negative_pressure_rejected(self):
        with pytest.raises(ValueError):
            burn_rate_mps('apcp', 0.0)


class TestEngineConsistency:
    """Katalog, motorun referans setiyle ÇELİŞMEZ."""

    @staticmethod
    def _engine_table():
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        table = {}
        for key in ('apcp', 'black_powder', 'sugar', 'knsu', 'double_base'):
            eng = SolidRocketEngine(propellant_type=key)
            table[key] = {
                'density': eng.rho_p, 'c_star': eng.c_star,
                'gamma': eng.gamma, 'flame_temperature': eng.T_c,
                'molecular_weight': eng.mw_exhaust,
            }
        return table

    def test_engine_reference_values_match_catalog(self):
        for key, engine_vals in self._engine_table().items():
            rec = PROPELLANTS[key]
            for field, value in engine_vals.items():
                assert rec[field] == pytest.approx(value, rel=1e-9), \
                    f'{key}.{field}: catalogue {rec[field]} vs engine {value}'

    def test_engine_key_field_points_to_a_real_engine_type(self):
        engine_types = set(self._engine_table())
        for key, rec in PROPELLANTS.items():
            if rec['engine_key'] is None:
                continue
            assert rec['engine_key'] in engine_types, key

    def test_catalog_values_survive_engine_override_bands(self):
        """Seçilen yakıt motora gönderilince sessizce reddedilmemeli."""
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        for key, rec in PROPELLANTS.items():
            eng = SolidRocketEngine(
                propellant_type='apcp',
                burn_rate_a=rec['burn_rate_a'], burn_rate_n=rec['burn_rate_n'],
                overrides={
                    'density': rec['density'],
                    'char_velocity': rec['c_star'],
                    'gamma': rec['gamma'],
                    'flame_temp': rec['flame_temperature'],
                })
            assert eng.rho_p == pytest.approx(rec['density']), key
            assert eng.c_star == pytest.approx(rec['c_star']), key
            assert eng.gamma == pytest.approx(rec['gamma']), key
            assert eng.T_c == pytest.approx(rec['flame_temperature']), key

    def test_cstar_never_exceeds_ideal_single_phase_value(self):
        """İki fazlı kayıplar c*'ı ideal Eq. 3-32 değerinin ÜSTÜNE çıkaramaz."""
        for key, rec in PROPELLANTS.items():
            ideal = cstar_from_thermo(rec['gamma'], rec['flame_temperature'],
                                      rec['molecular_weight'])
            assert rec['c_star'] <= ideal * 1.001, \
                f'{key}: c*={rec["c_star"]:.1f} > ideal {ideal:.1f}'

    def test_declared_eq332_records_match_the_identity(self):
        for key, rec in PROPELLANTS.items():
            if rec['c_star_basis'] not in ('eq3-32', 'cea'):
                continue
            ideal = cstar_from_thermo(rec['gamma'], rec['flame_temperature'],
                                      rec['molecular_weight'])
            if rec['c_star_basis'] == 'eq3-32':
                assert rec['c_star'] == pytest.approx(ideal, rel=1e-3), key


class TestEndpoint:
    @pytest.fixture(scope='class')
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_endpoint_contract(self, client):
        resp = client.get('/api/propellants')
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['ok'] is True
        assert isinstance(payload['propellants'], dict)
        assert isinstance(payload['aliases'], dict)
        assert set(payload['propellants']) == set(PROPELLANTS)
        assert set(payload['aliases']) == set(ALIASES)

    def test_endpoint_records_carry_every_field(self, client):
        payload = client.get('/api/propellants').get_json()
        for key, rec in payload['propellants'].items():
            for field in REQUIRED_FIELDS:
                assert field in rec, f'{key}.{field} missing over the wire'
            assert rec['key'] == key

    def test_endpoint_matches_module_values(self, client):
        payload = client.get('/api/propellants').get_json()
        for key, rec in payload['propellants'].items():
            for field in NUMERIC_FIELDS:
                assert rec[field] == pytest.approx(PROPELLANTS[key][field])
