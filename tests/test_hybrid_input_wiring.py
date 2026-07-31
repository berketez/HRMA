"""v2.6.26 hibrit motor girdi bağlantısı bekçileri.

Kapattıkları ölçülmüş kusurlar:

* D1-HIBRIT-TERMAL-1 (KRİTİK) — v2.6.25'te ``chamber_material``,
  ``wall_thickness`` ve ``cooling_channels`` için "arka uca bağlandı"
  denmişti, ama ``advanced.html`` içindeki inline ``getFormData``
  bunları hiç göndermiyordu. Arka uç doğruydu, arayüz göndermiyordu;
  kullanıcı açısından üç girdi hâlâ ölüydü.
* Hibrit tasarım uyarıları hiç dönmüyordu — ``self.design_warnings``
  toplanıyor ama sonuç sözlüğüne konmuyordu. Ölçüldü:
  ``chamber_material='ZIRVAAA'`` isteği HTTP 200 dönüyor, sessizce
  ``steel_4130`` kullanılıyor, kullanıcı hiçbir uyarı görmüyordu.
* D1-HIBRIT-COMBTYPE-1 — ``combustion_type`` sınıfta yalnız atanıyor,
  hiç okunmuyordu; ``contraction_ratio`` motora hiç geçirilmiyordu.
  'finite' seçmek çıktının HİÇBİR yaprağını değiştirmiyordu.
"""

import math

import pytest


HEADERS = {'Host': '127.0.0.1:8080'}
BASE = {
    'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 6.0, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'l_star': 1.0, 'expansion_ratio': 4.0,
    'nozzle_type': 'conical', 'chamber_temperature': 3000,
}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


def _leaves(obj, path=''):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _leaves(value, f'{path}.{key}')
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from _leaves(value, f'{path}[{idx}]')
    else:
        yield path, obj


def _calc(client, **extra):
    resp = client.post('/calculate', json=dict(BASE, **extra), headers=HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return dict(_leaves(resp.get_json()))


def _changed(before, after):
    total = 0
    for key in set(before) | set(after):
        a, b = before.get(key), after.get(key)
        if (isinstance(a, (int, float)) and isinstance(b, (int, float))
                and not isinstance(a, bool) and not isinstance(b, bool)):
            if not math.isclose(a, b, rel_tol=1e-9):
                total += 1
        elif a != b:
            total += 1
    return total


@pytest.fixture(scope='module')
def baseline(client):
    return _calc(client)


class TestThermalInputsReachTheSolver:
    """Arka uç bağlı olsa bile arayüz göndermezse alan ÖLÜDÜR."""

    @pytest.mark.parametrize('field,value', [
        ('chamber_material', 'aluminum_6061'),
        ('chamber_material', 'inconel_718'),
        ('wall_thickness', 10.0),
        ('wall_thickness', 2.0),
        ('cooling_channels', 'radial'),
        ('cooling_channels', 'spiral'),
    ])
    def test_field_changes_the_result(self, client, baseline, field, value):
        changed = _changed(baseline, _calc(client, **{field: value}))
        assert changed > 0, f'{field}={value} hicbir seyi degistirmiyor (olu girdi)'

    def test_collector_actually_sends_them(self):
        """Şablon katmanı bekçisi: arka uç testi bunu YAKALAYAMAZDI.

        v2.6.25'in yarım düzeltmesinin dersi — HTTP katmanını test etmek
        yetmez, toplayıcının alanı gönderdiğini de doğrulamak gerekir.
        """
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        template = (root / 'hrma/templates/advanced.html').read_text(
            encoding='utf-8')
        collector = template.split('function getFormData')[-1]
        for field in ('chamber_material', 'wall_thickness', 'cooling_channels'):
            assert f"getElementById('{field}')" in collector, (
                f'{field} inline getFormData tarafindan gonderilmiyor')


class TestDesignWarningsReachTheUser:
    """Sessiz yedeğe düşmek yasak — uyarı kullanıcıya ulaşmalı."""

    @staticmethod
    def _warning_codes(data):
        return [value for key, value in data.items()
                if key.endswith('.code') and '.warnings[' in key]

    def test_unknown_material_produces_a_warning(self, client):
        data = _calc(client, chamber_material='ZIRVAAA')
        assert 'warn.hybrid.chamber_material_unknown' in self._warning_codes(data)

    def test_valid_material_produces_no_material_warning(self, client):
        data = _calc(client, chamber_material='aluminum_6061')
        assert ('warn.hybrid.chamber_material_unknown'
                not in self._warning_codes(data))

    def test_warnings_are_exposed_under_both_names(self, client):
        """Arayüz 'warnings', dış tüketiciler 'design_warnings' okuyor."""
        resp = client.post('/calculate', json=dict(BASE), headers=HEADERS)
        motor = resp.get_json()['motor']
        assert 'warnings' in motor
        assert 'design_warnings' in motor
        assert motor['warnings'] == motor['design_warnings']


class TestFiniteAreaCombustor:
    """combustion_type ve contraction_ratio artık gerçek fiziğe bağlı."""

    def test_finite_mode_changes_the_result(self, client, baseline):
        assert _changed(baseline, _calc(client, combustion_type='finite')) > 0

    def test_infinite_mode_produces_no_finite_area_block(self, client, baseline):
        assert not any('finite_area_combustor' in key for key in baseline)

    def test_finite_mode_produces_the_block(self, client):
        data = _calc(client, combustion_type='finite')
        assert any('finite_area_combustor' in key for key in data)

    @staticmethod
    def _block(data):
        return {key.split('.')[-1]: value for key, value in data.items()
                if '.finite_area_combustor.' in key}

    def test_contraction_ratio_is_live_in_its_own_context(self, client):
        low = self._block(_calc(client, combustion_type='finite',
                                contraction_ratio=2.0))
        high = self._block(_calc(client, combustion_type='finite',
                                 contraction_ratio=20.0))
        assert low['chamber_mach'] != high['chamber_mach']
        assert low['contraction_ratio_source'] == 'user input'

    def test_pressure_loss_falls_as_contraction_ratio_grows(self, client):
        """Fizik: CR buyudukce sonsuz-alan limitine yakinsamali."""
        losses = [self._block(_calc(client, combustion_type='finite',
                                    contraction_ratio=cr))['pressure_loss_percent']
                  for cr in (2.0, 4.0, 8.0, 20.0)]
        assert losses == sorted(losses, reverse=True), losses
        assert losses[-1] < 0.5, 'CR=20 pratikte sonsuz-alana yakinsamali'
        assert losses[0] > 1.0, 'CR=2 belirgin bir kayip vermeli'

    def test_injector_face_pressure_exceeds_chamber_pressure(self, client):
        block = self._block(_calc(client, combustion_type='finite',
                                  contraction_ratio=2.0))
        assert block['injector_face_pressure_bar'] > BASE['chamber_pressure']

    def test_chamber_mach_is_subsonic(self, client):
        for cr in (1.5, 2.0, 8.0):
            block = self._block(_calc(client, combustion_type='finite',
                                      contraction_ratio=cr))
            assert 0 < block['chamber_mach'] < 1.0, cr

    def test_ratio_is_derived_from_geometry_when_not_supplied(self, client):
        block = self._block(_calc(client, combustion_type='finite'))
        assert block['contraction_ratio_source'] == 'chamber geometry'
        assert block['contraction_ratio'] > 1.0

    def test_low_contraction_ratio_warns(self, client):
        data = _calc(client, combustion_type='finite', contraction_ratio=1.5)
        codes = [value for key, value in data.items()
                 if key.endswith('.code') and '.warnings[' in key]
        assert 'warn.hybrid.contraction_ratio_low' in codes

    def test_model_declares_its_basis(self, client):
        block = self._block(_calc(client, combustion_type='finite'))
        assert 'Sutton' in block['basis'] or 'isentropic' in block['basis'].lower()
