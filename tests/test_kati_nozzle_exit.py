"""Bekçi: katı motorun egzoz (plume) çıkış şeması — motor_viz3d.js sözleşmesi.

Teşhis (2026-08-03): egzoz gösterimi (motor_viz3d.js readNozzleExit)
``nozzle_design.performance.{exit_pressure, ambient_pressure, exit_mach,
exit_velocity}``, ``md.gamma`` (ya da combustion_analysis bileşim gamması),
``md.chamber_temperature`` ve ``altitude_performance`` dizisinin ilk
elemanındaki ``exit_velocity`` alanlarını arar. Hibrit motor bunları
yayımlıyordu; KATI motorun nozzle_design bloğu salt geometriydi —
``performance`` alt bloğu hiç yoktu, bu yüzden katı sayfasında egzoz HİÇ
çizilmiyordu.

Bu dosya doğru davranışı kilitler:

  * Alan adları motor_viz3d.js'in okuduğu adlarla BİREBİR aynıdır ve JS
    kaynağına karşı da sınanır — iki taraftan biri adı değiştirirse test düşer.
  * Değerler çözücünün GERÇEK izentropik çözümünden gelir ve fiziksel olarak
    tutarlıdır (exit_mach > 1, exit_pressure < chamber_pressure,
    exit_velocity > 0, izentropik bağıntılar alanlar arasında kapanır).
  * Sayısal çözüm başarısızsa alanlar None kalır — sayı UYDURULMAZ, egzoz
    çizilmez.
"""

import math
import warnings
from pathlib import Path

import pytest

from hrma.constants import G_0, isa_pressure
from hrma.engines.solid_rocket_engine import SolidRocketEngine

ROOT = Path(__file__).resolve().parents[1]
VIZ_JS = ROOT / 'hrma' / 'static' / 'js' / 'motor_viz3d.js'


def _quiet(fn, *args, **kwargs):
    """Motor kurulum/koşu uyarılarını test çıktısından uzak tutar."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def results():
    """Varsayılan APCP/BATES motorunun GERÇEK hesap sonucu (tam koşu)."""
    motor = _quiet(SolidRocketEngine)
    out = _quiet(motor.calculate_performance)
    assert 'error' not in out, out.get('error')
    return out


@pytest.fixture(scope='module')
def exit_perf(results):
    return results['nozzle_design']['performance']


# ---------------------------------------------------------------------------
# 1) Şema adları motor_viz3d.js'in okuduğu adlarla birebir aynı mı
# ---------------------------------------------------------------------------
class TestSchemaMatchesTheViz:

    #: readNozzleExit'in gerçekten okuduğu erişim ifadeleri. Bunlardan biri
    #: JS'ten kaybolursa sözleşmenin İKİ ucu birden gözden geçirilmeli.
    JS_READS = (
        'md.nozzle_design',
        'perf.exit_pressure',
        'perf.ambient_pressure',
        'perf.exit_mach',
        'perf.exit_velocity',
        'md.chamber_temperature',
        'md.gamma',
        'alt[0].exit_velocity',
    )

    def test_js_still_reads_these_names(self):
        src = VIZ_JS.read_text(encoding='utf-8')
        for expr in self.JS_READS:
            assert expr in src, (
                f'motor_viz3d.js artık {expr!r} okumuyor — egzoz şeması '
                f'sözleşmesi değişmiş; bu testi ve katı şemayı birlikte '
                f'güncelle')

    def test_performance_block_has_the_exact_keys(self, exit_perf):
        for key in ('exit_pressure', 'ambient_pressure', 'exit_mach',
                    'exit_velocity'):
            assert key in exit_perf, f'nozzle_design.performance.{key} yok'

    def test_top_level_gamma_and_chamber_temperature(self, results):
        # readNozzleExit gamma'yı md.gamma yedeğinden, sıcaklığı
        # md.chamber_temperature'dan okur.
        assert isinstance(results['gamma'], float)
        assert isinstance(results['chamber_temperature'], (int, float))

    def test_first_altitude_row_has_exit_velocity(self, results):
        # Hibritteki dict-sarmalı yapının içindeki dizinin satır şemasıyla
        # uyumlu: ilk eleman (en düşük irtifa) exit_velocity taşır.
        rows = results['altitude_performance']
        assert isinstance(rows, list) and rows, 'irtifa tablosu boş'
        assert 'exit_velocity' in rows[0]

    def test_every_new_field_declares_its_basis(self, results, exit_perf):
        # Sahte veri yasağının ikizi: her yeni çıktı alanı temelini beyan eder.
        for key in ('exit_pressure', 'ambient_pressure', 'exit_mach',
                    'exit_velocity', 'exit_temperature_k'):
            assert exit_perf.get(f'{key}_basis' if key != 'exit_temperature_k'
                                 else 'exit_temperature_basis'), (
                f'{key} alanının _basis beyanı yok')
        assert results.get('gamma_basis')
        assert results['altitude_performance'][0].get('exit_velocity_basis')


# ---------------------------------------------------------------------------
# 2) Fiziksel tutarlılık — değerler gerçek çözümden mi geliyor
# ---------------------------------------------------------------------------
class TestPhysicalConsistency:

    def test_exit_mach_is_supersonic(self, exit_perf):
        assert exit_perf['exit_mach'] > 1.0

    def test_exit_pressure_below_chamber_pressure(self, results, exit_perf):
        assert 0.0 < exit_perf['exit_pressure'] < results['chamber_pressure']

    def test_exit_velocity_is_positive_and_plausible(self, exit_perf):
        # Kimyasal roket egzozu için makul bant (m/s)
        assert 500.0 < exit_perf['exit_velocity'] < 6000.0

    def test_ambient_pressure_is_positive(self, exit_perf):
        assert exit_perf['ambient_pressure'] > 0.0

    def test_exit_pressure_matches_isentropic_mach(self, results, exit_perf):
        """P_e/P_c = [1+(γ-1)/2·M_e²]^(-γ/(γ-1)) alanlar arasında kapanmalı."""
        g = results['gamma']
        me = exit_perf['exit_mach']
        expected = (1.0 + 0.5 * (g - 1.0) * me * me) ** (-g / (g - 1.0))
        assert exit_perf['exit_pressure'] / results['chamber_pressure'] == \
            pytest.approx(expected, rel=1e-6)

    def test_exit_temperature_is_isentropic(self, results, exit_perf):
        """T_e = T_c / (1+(γ-1)/2·M_e²) — readNozzleExit'in kendi bağıntısı."""
        g = results['gamma']
        me = exit_perf['exit_mach']
        expected = results['chamber_temperature'] / (
            1.0 + 0.5 * (g - 1.0) * me * me)
        assert exit_perf['exit_temperature_k'] == pytest.approx(expected,
                                                                rel=1e-6)

    def test_altitude_row_velocity_equals_isp_g0(self, results):
        """Optimum genişlemede v_e = Isp·g0 — satır kendi Isp'iyle tutarlı."""
        row = results['altitude_performance'][0]
        assert row['exit_velocity'] == pytest.approx(
            row['specific_impulse'] * G_0, rel=1e-9)

    def test_viz_gate_would_draw_the_plume(self, results, exit_perf):
        """readNozzleExit'in null kapısının Python kopyası: katı motor artık
        kapıdan GEÇMELİ (eskiden performance bloğu olmadığı için null dönüyor
        ve egzoz hiç çizilmiyordu)."""
        pe = exit_perf['exit_pressure']
        pa = exit_perf['ambient_pressure']
        me = exit_perf['exit_mach']
        gamma = results['gamma']
        tc = results['chamber_temperature']
        ve = results['altitude_performance'][0]['exit_velocity']
        values = (pe, pa, me, gamma, tc, ve)
        assert all(isinstance(v, (int, float)) and math.isfinite(v)
                   for v in values), values
        assert pe > 0 and pa > 0 and me > 1 and ve > 0


# ---------------------------------------------------------------------------
# 3) Ortam basıncı çözücünün gerçek geri basıncı mı (deniz seviyesi sabiti
#    geri gelmesin)
# ---------------------------------------------------------------------------
class TestAmbientFollowsTheInput:

    def test_ambient_pressure_tracks_test_altitude(self):
        motor = _quiet(SolidRocketEngine, overrides={'test_altitude': 5000})
        perf = _quiet(motor._design_nozzle_geometry)['performance']
        expected = float(isa_pressure(5000)) / 1e5  # bar
        assert perf['ambient_pressure'] == pytest.approx(expected, rel=1e-9)
        # Tasarım ε'su Pe = Pa verecek şekilde boyutlandırılır: çıkış basıncı
        # da kullanıcının ortamını izlemeli, deniz seviyesinde kalmamalı.
        assert perf['exit_pressure'] == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# 4) Çözüm başarısızsa sayı uydurulmaz
# ---------------------------------------------------------------------------
class TestNoFabricationOnSolverFailure:

    def test_failed_pressure_ratio_publishes_none(self):
        motor = _quiet(SolidRocketEngine)
        # _exit_pressure_ratio sayısal çözümü başaramadığında 0.0 döndürür
        # (sözleşmesi böyle); çıkış alanları bu durumda None kalmalı.
        motor._exit_pressure_ratio = lambda epsilon: 0.0
        perf = _quiet(motor._design_nozzle_geometry)['performance']
        assert perf['exit_pressure'] is None
        assert perf['exit_mach'] is None
        assert perf['exit_velocity'] is None
        assert perf['exit_temperature_k'] is None
