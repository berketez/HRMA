"""N₂O tank blowdown modeli doğrulama testleri.

Fiziksel doğrulama çapaları:
- Psat(293.15 K) ≈ 50.5 bar (NIST/Span-Wagner)
- Tipik hibrit yanışında tank ~15-40 K soğur, basınç ~%30-60 düşer
  (Whitmore & Chandler JPP 2011; Zilliac & Karabeyoglu deneysel eğrileri)
- Kütle ve hacim korunumu her adımda makine hassasiyetine yakın tutmalı
"""

import numpy as np
import pytest

from hrma.analysis.tank_blowdown import (
    N2OSaturation, N2OTankBlowdown, COOLPROP_AVAILABLE,
)


class TestSaturationProperties:
    def test_psat_293K_matches_nist(self):
        props = N2OSaturation()
        assert props.psat(293.15) == pytest.approx(50.5e5, rel=0.02)

    def test_table_fallback_matches_coolprop(self):
        """Gömülü tablo, CoolProp EOS'una %2 içinde sadık kalmalı."""
        if not COOLPROP_AVAILABLE:
            pytest.skip("CoolProp yok; karşılaştırma yapılamaz")
        eos = N2OSaturation(use_coolprop=True)
        tab = N2OSaturation(use_coolprop=False)
        for T in (250.0, 273.0, 285.0, 293.0, 300.0):
            assert tab.psat(T) == pytest.approx(eos.psat(T), rel=0.02)
            assert tab.rho_l(T) == pytest.approx(eos.rho_l(T), rel=0.02)
            assert tab.h_v(T) == pytest.approx(eos.h_v(T), rel=0.02)

    def test_latent_heat_positive_and_decreasing(self):
        """Gizli ısı pozitif ve kritik noktaya yaklaşırken azalmalı."""
        props = N2OSaturation()
        L_250 = props.h_v(250.0) - props.h_l(250.0)
        L_300 = props.h_v(300.0) - props.h_l(300.0)
        assert L_250 > L_300 > 0


class TestTankBlowdown:
    def _make_tank(self, **kw):
        # Fig 7 temsili vakası: 16.5 kg N₂O, 293 K
        kw.setdefault('oxidizer_mass', 16.5)
        kw.setdefault('initial_temperature', 293.15)
        return N2OTankBlowdown.from_oxidizer_mass(**kw)

    def test_initial_pressure_is_saturation(self):
        tank = self._make_tank()
        assert tank.pressure == pytest.approx(50.5e5, rel=0.02)
        assert tank.liquid_mass == pytest.approx(16.5, rel=1e-6)

    def test_mass_conservation(self):
        """Tanktan çıkan kütle = tank envanterindeki azalma."""
        tank = self._make_tank()
        m0 = tank.liquid_mass + tank.vapor_mass
        hist = tank.simulate(mdot_out=1.2, duration=10.0, dt=0.05)
        m_end = hist['liquid_mass'][-1] + hist['vapor_mass'][-1]
        assert m0 - m_end == pytest.approx(1.2 * 10.0, rel=1e-3)

    def test_pressure_and_temperature_decrease(self):
        tank = self._make_tank()
        hist = tank.simulate(mdot_out=1.2, duration=10.0, dt=0.05)
        assert np.all(np.diff(hist['pressure']) <= 1e-6)
        assert np.all(np.diff(hist['temperature']) <= 1e-9)
        # Tipik blowdown bandı: 10 s'de belirgin ama sınırlı soğuma
        dT = hist['temperature'][0] - hist['temperature'][-1]
        assert 2.0 < dT < 60.0
        dP = (hist['pressure'][0] - hist['pressure'][-1]) / hist['pressure'][0]
        assert 0.05 < dP < 0.8

    def test_volume_consistency_each_step(self):
        """Her adımda m_l·v_l + m_v·v_v = V_tank tutmalı (denge kısıtı)."""
        tank = self._make_tank()
        for _ in range(50):
            s = tank.step(mdot_out=1.2, dt=0.1)
            if s['phase'] != 'two_phase':
                break
            V_calc = (s['m_liquid'] / tank.props.rho_l(s['T'])
                      + s['m_vapor'] / tank.props.rho_v(s['T']))
            assert V_calc == pytest.approx(tank.V, rel=1e-3)

    def test_liquid_depletion_switches_to_vapor_phase(self):
        tank = self._make_tank(oxidizer_mass=2.0)
        hist = tank.simulate(mdot_out=1.0, duration=5.0, dt=0.05)
        assert hist['phase'] == 'vapor'
        assert hist['liquid_mass'][-1] == 0.0
        # Buhar fazında basınç düşmeye devam etmeli
        assert hist['pressure'][-1] < hist['pressure'][0]

    def test_energy_balance_against_coolprop_uv_flash(self):
        """Denge çözümü CoolProp'un bağımsız U-V flash'ıyla uyuşmalı."""
        if not COOLPROP_AVAILABLE:
            pytest.skip("CoolProp yok")
        from CoolProp.CoolProp import PropsSI
        tank = self._make_tank()
        # 3 kg çekildikten sonraki durum
        for _ in range(60):
            s = tank.step(mdot_out=1.0, dt=0.05)
        m = s['m_liquid'] + s['m_vapor']
        rho = m / tank.V
        u = (s['m_liquid'] * tank.props.u_l(s['T'])
             + s['m_vapor'] * tank.props.u_v(s['T'])) / m
        # Bağımsız kontrol: aynı (rho, u) çiftinden CoolProp'un T'si
        T_flash = PropsSI('T', 'D', rho, 'U', u, 'N2O')
        assert s['T'] == pytest.approx(T_flash, abs=1.0)

    def test_fill_fraction_guard(self):
        with pytest.raises(ValueError):
            N2OTankBlowdown(tank_volume=0.03, liquid_fill_fraction=1.0)

    def test_temperature_band_guard(self):
        with pytest.raises(ValueError):
            N2OTankBlowdown(tank_volume=0.03, initial_temperature=320.0)
