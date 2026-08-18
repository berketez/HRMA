"""Egzoz plume'u çözücünün GERÇEK nozul çıkışından türer (v2.6.26).

Kapattığı kusur: 3B egzoz gösterimi çözücünün hesapladığı çıkış
büyüklüklerini hiç kullanmıyor, yerine uydurma sabitler kullanıyordu:

    parçacık hızı = model_uzunlugu x (2.2 + rastgele x 1.6)
    pe/pa         = (8 / eps) ** 1.15          <- 8 ve 1.15 dayanaksız
    şok aralığı   = de x (0.7 + 0.5 x sqrt(eps / 8))

Oysa çözücü ``exit_pressure``, ``ambient_pressure``, ``exit_mach``,
``exit_velocity`` ve ``gamma`` değerlerini zaten üretiyordu.

Şok hücre aralığı artık Prandtl-Pack bağıntısıyla hesaplanır:
``L_s = 1.306 * D_j * sqrt(Mj^2 - 1)`` (Prandtl 1904; Pack, Q. J. Mech.
Appl. Math. 3, 1950) — jet aeroakustiğinde yaygın doğrulanmış bir sonuç.

Ayrıca "uydurma alev yasağı": çözücü çıkış durumunu vermiyorsa plume HİÇ
çizilmez; eskiden bu durumda da akışkan bir alev gösteriliyordu.
"""

import json
import re
import shutil
import subprocess
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIZ_JS = ROOT / 'hrma/static/js/motor_viz3d.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadi')


def _extract(func_name):
    """motor_viz3d.js icinden tek bir fonksiyonu izole cikarir."""
    source = VIZ_JS.read_text(encoding='utf-8')
    start = source.index('function %s(' % func_name)
    depth, idx = 0, start
    while idx < len(source):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if depth == 0:
                return source[start:idx + 1]
        idx += 1
    raise AssertionError('%s kapanmiyor' % func_name)


def _run_read_nozzle_exit(motor_data):
    """readNozzleExit'i node ile izole calistirip sonucu doner."""
    script = (
        'function num(v, d) { var n = Number(v); '
        'return (v === null || v === undefined || !isFinite(n)) ? d : n; }\n'
        + _extract('readNozzleExit') + '\n'
        + 'const out = readNozzleExit(%s);\n' % json.dumps(motor_data)
        + 'process.stdout.write(JSON.stringify(out));\n'
    )
    result = subprocess.run([NODE], input=script, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr[:600]
    return json.loads(result.stdout)


# --- Gerçek çözücü çıktısından alınmış örnek (hibrit, Pc=20 bar, eps=4) ---
REAL_MOTOR = {
    'exit_diameter': 0.04317,
    'chamber_temperature': 3307.0,
    'nozzle_design': {'performance': {
        'exit_pressure': 0.9383,       # bar
        'ambient_pressure': 1.0,       # bar
        'exit_mach': 2.5623,
    }},
    'combustion_analysis': {'compositions': {'chamber': {'gamma': 1.1614}}},
    'altitude_performance': {'altitude_performance': [{'exit_velocity': 2272.2}]},
}


class TestSolverValuesAreUsed:

    def test_real_motor_yields_a_state(self):
        state = _run_read_nozzle_exit(REAL_MOTOR)
        assert state is not None

    def test_pressure_ratio_is_the_real_one(self):
        state = _run_read_nozzle_exit(REAL_MOTOR)
        assert state['pressureRatio'] == pytest.approx(0.9383 / 1.0, rel=1e-6)

    def test_exit_velocity_comes_from_the_solver(self):
        state = _run_read_nozzle_exit(REAL_MOTOR)
        assert state['exitVelocity'] == pytest.approx(2272.2)

    def test_exit_temperature_is_isentropic(self):
        """Te = Tc / (1 + (g-1)/2 * Me^2)"""
        state = _run_read_nozzle_exit(REAL_MOTOR)
        gamma, mach, tc = 1.1614, 2.5623, 3307.0
        expected = tc / (1 + 0.5 * (gamma - 1) * mach ** 2)
        assert state['exitTemperature'] == pytest.approx(expected, rel=1e-6)

    def test_slightly_overexpanded_is_detected(self):
        """pe=0.938 < pa=1.0 -> asiri genisleme."""
        assert _run_read_nozzle_exit(REAL_MOTOR)['expansionState'] == 'over'

    def test_underexpanded_is_detected(self):
        motor = json.loads(json.dumps(REAL_MOTOR))
        motor['nozzle_design']['performance']['exit_pressure'] = 2.0
        assert _run_read_nozzle_exit(motor)['expansionState'] == 'under'

    def test_ideal_expansion_is_detected(self):
        motor = json.loads(json.dumps(REAL_MOTOR))
        motor['nozzle_design']['performance']['exit_pressure'] = 1.0
        assert _run_read_nozzle_exit(motor)['expansionState'] == 'ideal'


class TestShockCellSpacing:
    """Prandtl-Pack: L_s = 1.306 * D_j * sqrt(Mj^2 - 1)"""

    def test_matches_the_published_relation(self):
        state = _run_read_nozzle_exit(REAL_MOTOR)
        expected = 1.306 * 0.04317 * 1000 * (state['jetMach'] ** 2 - 1) ** 0.5
        assert state['cellSpacingMm'] == pytest.approx(expected, rel=1e-6)

    def test_spacing_grows_with_jet_mach(self):
        spacings = []
        for pe in (0.5, 1.0, 2.0, 4.0):
            motor = json.loads(json.dumps(REAL_MOTOR))
            motor['nozzle_design']['performance']['exit_pressure'] = pe
            state = _run_read_nozzle_exit(motor)
            spacings.append(state['cellSpacingMm'])
        assert spacings == sorted(spacings), spacings

    def test_spacing_scales_with_exit_diameter(self):
        big = json.loads(json.dumps(REAL_MOTOR))
        big['exit_diameter'] = REAL_MOTOR['exit_diameter'] * 2
        ratio = (_run_read_nozzle_exit(big)['cellSpacingMm']
                 / _run_read_nozzle_exit(REAL_MOTOR)['cellSpacingMm'])
        assert ratio == pytest.approx(2.0, rel=1e-6)


class TestNoFabricatedFlame:
    """Cozucu verisi yoksa plume CIZILMEZ."""

    @pytest.mark.parametrize('drop', [
        ('nozzle_design',),
        ('combustion_analysis',),
        ('altitude_performance',),
    ])
    def test_missing_solver_block_yields_null(self, drop):
        motor = json.loads(json.dumps(REAL_MOTOR))
        motor.pop(drop[0])
        assert _run_read_nozzle_exit(motor) is None

    def test_empty_motor_yields_null(self):
        assert _run_read_nozzle_exit({}) is None

    @pytest.mark.parametrize('field,bad', [
        ('exit_pressure', 0),
        ('ambient_pressure', -1),
        ('exit_mach', 0.8),          # ses alti cikis: plume modeli gecersiz
    ])
    def test_invalid_values_yield_null(self, field, bad):
        motor = json.loads(json.dumps(REAL_MOTOR))
        motor['nozzle_design']['performance'][field] = bad
        assert _run_read_nozzle_exit(motor) is None


class TestNoInventedConstantsRemain:

    def test_fabricated_pressure_ratio_formula_is_gone(self):
        source = VIZ_JS.read_text(encoding='utf-8')
        assert 'Math.pow(IDEAL_EXPANSION_EPS' not in source
        assert '1.15)' not in source.split('_plumeAero')[-1][:1200]

    def test_particle_speed_uses_exit_velocity(self):
        source = VIZ_JS.read_text(encoding='utf-8')
        reset = source.split('_resetParticle = function')[1][:1600]
        assert 'exitVelocity' in reset, 'parcacik hizi cozucuye bagli degil'
        assert '2.2 + Math.random() * 1.6' not in reset

    def test_plume_is_hidden_without_solver_state(self):
        source = VIZ_JS.read_text(encoding='utf-8')
        update = source.split('_updatePlume = function')[1][:900]
        assert '_plumeInfo' in update and 'visible = false' in update
