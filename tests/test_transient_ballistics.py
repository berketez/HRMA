"""Transient iç balistik doğrulama testleri.

Çapalar:
- t=0 tutarlılığı: transient çözüm tasarım noktasından başlamalı
  (Pc(0) ≈ tasarım Pc, F(0) ≈ tasarım itkisi — yarı-kararlı kapanış aynı
  c*/At ilişkisini kullandığından bu bir kimliktir, sapma model hatasıdır)
- Yarı-kararlılık kimliği her adımda: Pc·Cd·At = ṁ·c*
- Regülatörlü modda O/F kayması hibrit literatürüyle uyumlu yönde
- Blowdown modunda basınç/itki monoton düşmeli, tank fiziğiyle tutarlı
"""

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.analysis.transient_ballistics import TransientBallistics


@pytest.fixture(scope='module')
def engine():
    """Fig 7 temsili vakası: 3 kN N₂O/parafin, 20 bar, optimum O/F."""
    e = HybridRocketEngine(
        thrust=3000, burn_time=10, of_ratio=7.96,
        chamber_pressure=20, atmospheric_pressure=1.01325,
        fuel_type='paraffin', oxidizer_type='n2o',
        fuel_density=900, regression_a=1.17e-4, regression_n=0.62,
        l_star=1.0, expansion_ratio=0, nozzle_type='conical')
    e.calculate()
    return e


class TestRegulatedMode:
    @pytest.fixture(scope='class')
    def result(self, engine):
        return TransientBallistics(engine, feed_mode='regulated').solve()

    def test_initial_point_matches_design(self, engine, result):
        assert result['chamber_pressure'][0] == pytest.approx(
            engine.P_c * 1e5, rel=0.08)
        assert result['thrust'][0] == pytest.approx(engine.F, rel=0.10)

    def test_quasi_steady_identity_each_step(self, engine, result):
        """Pc·Cd·At = ṁ·c*(O/F) her adımda tutmalı (kapanış kimliği)."""
        for i in range(0, len(result['time']), 40):
            mdot = result['mdot_ox'][i] + result['mdot_fuel'][i]
            cstar, _ = engine._instantaneous_performance(result['of_ratio'][i])
            lhs = result['chamber_pressure'][i] * 0.98 * engine.At
            assert lhs == pytest.approx(mdot * cstar, rel=0.02)

    def test_of_shift_direction(self, result):
        """Sabit ṁ_ox + büyüyen portta O/F artmalı (G düşer → ṁ_f düşer)."""
        assert result['of_ratio'][-1] > result['of_ratio'][0]

    def test_port_growth_monotonic(self, result):
        assert np.all(np.diff(result['port_diameter']) > 0)

    def test_total_impulse_reasonable(self, engine, result):
        """Toplam impuls tasarım F·t_b'nin ±%25 bandında olmalı
        (O/F kayması + basınç sürüklenmesi sapma yaratır ama sınırlı)."""
        nominal = engine.F * engine.t_b
        assert 0.75 * nominal < result['total_impulse'] < 1.25 * nominal

    def test_ends_by_time_or_web(self, result):
        assert result['end_event'] in ('burn_time_reached', 'web_exhausted')


class TestBlowdownMode:
    @pytest.fixture(scope='class')
    def result(self, engine):
        return TransientBallistics(
            engine, feed_mode='blowdown', tank_temperature=293.15).solve()

    def test_initial_point_matches_design(self, engine, result):
        """Enjektör K'sı t=0'da tasarım debisine kalibre edilir."""
        assert result['mdot_ox'][0] == pytest.approx(engine.mdot_ox, rel=0.05)
        assert result['chamber_pressure'][0] == pytest.approx(
            engine.P_c * 1e5, rel=0.08)

    def test_pressure_and_thrust_decay(self, result):
        """Blowdown imzası: tank boşaldıkça Pc ve F düşer."""
        n = len(result['time'])
        assert n > 10
        assert result['chamber_pressure'][-1] < result['chamber_pressure'][0]
        assert result['thrust'][-1] < result['thrust'][0]
        assert result['tank_pressure'][-1] < result['tank_pressure'][0]

    def test_injector_model_consistency(self, result):
        """ṁ_ox = K·√(2ρΔP) SPI modeli: ΔP düşerken debi de düşmeli."""
        assert result['mdot_ox'][-1] < result['mdot_ox'][0]
        # ΔP her kayıtlı adımda pozitif (aksi durumda çözüm durmuş olmalı)
        dP = result['tank_pressure'] - result['chamber_pressure']
        assert np.all(dP > 0)

    def test_tank_cooldown(self, result):
        dT = result['tank_temperature'][0] - result['tank_temperature'][-1]
        assert dT > 1.0  # buharlaşma soğuması görünür olmalı

    def test_end_event_physical(self, result):
        assert result['end_event'] in (
            'web_exhausted', 'oxidizer_depleted', 'injector_unstable',
            'feed_pressure_lost', 'time_limit')


class TestGuards:
    def test_unsized_engine_rejected(self):
        e = HybridRocketEngine(thrust=3000, burn_time=10, of_ratio=7.0,
                               chamber_pressure=20, fuel_type='paraffin',
                               oxidizer_type='n2o')
        # calculate() ÇAĞRILMADAN transient kurulamamalı
        with pytest.raises(ValueError):
            TransientBallistics(e)

    def test_blowdown_needs_feasible_tank_pressure(self, engine):
        """Kamara basıncı tank doygunluğunun üstündeyse blowdown reddedilir."""
        engine_hp = HybridRocketEngine(
            thrust=3000, burn_time=10, of_ratio=7.96,
            chamber_pressure=60,  # > Psat(293K)=50.5 bar
            fuel_type='paraffin', oxidizer_type='n2o',
            fuel_density=900, regression_a=1.17e-4, regression_n=0.62)
        engine_hp.calculate()
        with pytest.raises(ValueError):
            TransientBallistics(engine_hp, feed_mode='blowdown')
