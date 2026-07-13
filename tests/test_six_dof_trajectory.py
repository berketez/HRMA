"""6-DOF uçuş dinamiği doğrulama testleri.

Çapalar:
- Barrowman C_Nα/CP el hesabıyla birebir (standart 4-kanat örneği)
- Rüzgârsız dik atış: yörünge dikey kalmalı, apoje düzlemsel modelle uyumlu
- Rüzgârlı atış: kararlı roket rüzgâra döner (weathercock) ve apoje düşer
- Quaternion normu korunmalı; negatif statik marj kararsızlık üretmeli
"""

import numpy as np
import pytest

from hrma.analysis.six_dof_trajectory import (
    BarrowmanAero, SixDOFTrajectory, _quat_from_elevation_azimuth,
    _quat_to_dcm,
)


def _standard_rocket():
    """H-sınıfı temsili araç: d=10cm, L=2m, 4 trapez kanat."""
    return BarrowmanAero(
        body_diameter=0.10, nose_length=0.40, body_length=2.0,
        nose_type='ogive', fin_count=4, fin_root_chord=0.20,
        fin_tip_chord=0.10, fin_span=0.11, fin_sweep=0.08)


class TestBarrowman:
    def test_nose_only(self):
        """Yalnız burun: C_Nα=2, ogive CP=0.466·L_n (Barrowman)."""
        aero = BarrowmanAero(body_diameter=0.1, nose_length=0.4,
                             body_length=1.0, fin_count=0)
        assert aero.cn_alpha == pytest.approx(2.0)
        assert aero.x_cp == pytest.approx(0.466 * 0.4)

    def test_fin_term_hand_calculation(self):
        """4-kanat C_Nα'sı el hesabıyla birebir (Barrowman formülü)."""
        aero = _standard_rocket()
        s, cr, ct, m, d = 0.11, 0.20, 0.10, 0.08, 0.10
        l_mid = np.sqrt(s**2 + (m + (ct - cr) / 2.0)**2)
        cn_fins = (4 * 4 * (s / d)**2) / \
            (1 + np.sqrt(1 + (2 * l_mid / (cr + ct))**2))
        cn_fins *= 1 + (d / 2) / (s + d / 2)
        assert aero.cn_alpha_fins == pytest.approx(cn_fins, rel=1e-12)
        assert aero.cn_alpha == pytest.approx(2.0 + cn_fins, rel=1e-12)

    def test_cp_behind_cg_for_standard_rocket(self):
        """Standart araçta CP kanatlara yakın, gövde ortasının gerisinde."""
        aero = _standard_rocket()
        assert aero.x_cp > 0.5 * aero.L
        # Statik marj (CG=0.55L): pozitif ve makul bantta (1-6 kalibre)
        sm = aero.static_margin(0.55 * aero.L)
        assert 1.0 < sm < 6.0

    def test_conical_nose_cp(self):
        aero = BarrowmanAero(body_diameter=0.1, nose_length=0.3,
                             body_length=1.0, nose_type='conical',
                             fin_count=0)
        assert aero.x_cp == pytest.approx(0.2)  # (2/3)·0.3


class TestQuaternion:
    def test_vertical_launch_quaternion(self):
        """90° yükseliş: gövde +x atalet +z'ye dönmeli."""
        q = _quat_from_elevation_azimuth(90.0, 0.0)
        x_body = _quat_to_dcm(q)[:, 0]
        assert np.allclose(x_body, [0, 0, 1], atol=1e-9)

    def test_elevation_80_azimuth_90(self):
        q = _quat_from_elevation_azimuth(80.0, 90.0)
        x_body = _quat_to_dcm(q)[:, 0]
        expected = [np.cos(np.radians(80)) * 0.0,
                    np.cos(np.radians(80)) * 1.0,
                    np.sin(np.radians(80))]
        assert np.allclose(x_body, expected, atol=1e-9)


@pytest.fixture(scope='module')
def flight_no_wind():
    solver = SixDOFTrajectory(
        aero=_standard_rocket(), dry_mass=8.0, propellant_mass=4.0,
        thrust=1200.0, burn_time=6.0, cd0=0.45,
        wind_speed=0.0, launch_elevation_deg=90.0)
    return solver.solve(t_max=200.0)


@pytest.fixture(scope='module')
def flight_with_wind():
    solver = SixDOFTrajectory(
        aero=_standard_rocket(), dry_mass=8.0, propellant_mass=4.0,
        thrust=1200.0, burn_time=6.0, cd0=0.45,
        wind_speed=10.0, wind_direction_deg=0.0,  # kuzeyden 10 m/s
        launch_elevation_deg=90.0)
    return solver.solve(t_max=200.0)


class TestVerticalFlight:
    def test_stays_vertical_without_wind(self, flight_no_wind):
        """Rüzgârsız dik atışta yanal sapma apojenin küçük kesri olmalı."""
        r = flight_no_wind['position']
        apogee = flight_no_wind['apogee']
        lateral_at_apogee = np.hypot(
            r[0][np.argmax(r[2])], r[1][np.argmax(r[2])])
        assert lateral_at_apogee < 0.01 * apogee

    def test_apogee_reasonable(self, flight_no_wind):
        """~12 kg / 1.2 kN / 6 s araç için apoje km mertebesinde olmalı."""
        assert 1000.0 < flight_no_wind['apogee'] < 20000.0

    def test_quaternion_norm_preserved(self, flight_no_wind):
        q = flight_no_wind['quaternion']
        norms = np.linalg.norm(q, axis=0)
        assert np.all(np.abs(norms - 1.0) < 1e-3)

    def test_alpha_small_for_stable_vertical(self, flight_no_wind):
        assert flight_no_wind['max_alpha_deg'] < 5.0
        assert flight_no_wind['stable']

    def test_apogee_matches_planar_model(self, flight_no_wind):
        """6-DOF apojesi bağımsız düzlemsel enerji entegrasyonuyla uyumlu.

        Aynı kütle/itki/drag ile basit dikey 2. mertebe entegrasyon.
        """
        from hrma.analysis.six_dof_trajectory import (
            _atmosphere, _drag_coefficient_mach)
        m_dry, m_prop, F, tb, cd0 = 8.0, 4.0, 1200.0, 6.0, 0.45
        S = np.pi * 0.05**2
        dt, t, v, h = 0.005, 0.0, 0.0, 0.0
        while True:
            m = m_dry + m_prop * max(0.0, 1.0 - t / tb)
            rho, a = _atmosphere(h)
            cd = _drag_coefficient_mach(abs(v) / a, cd0)
            thrust = F if t < tb else 0.0
            drag = 0.5 * rho * v * abs(v) * cd * S
            g = 9.80665 * (6371000.0 / (6371000.0 + h))**2
            v += (thrust - drag - m * g) / m * dt
            h += v * dt
            t += dt
            if v < 0 and t > tb:
                break
        assert flight_no_wind['apogee'] == pytest.approx(h, rel=0.05)


class TestWindResponse:
    def test_weathercock_into_wind(self, flight_no_wind, flight_with_wind):
        """Kararlı roket rüzgâra doğru yatar → rüzgâr yönünde (kuzeye,
        rüzgârın geldiği tarafa) sürüklenme bileşeni oluşur ve apoje düşer."""
        assert flight_with_wind['apogee'] < flight_no_wind['apogee']
        # Kuzeyden esen rüzgârda weathercocking burnu kuzeye çevirir →
        # araç apojede kuzeye (x>0) kaymış olmalı
        r = flight_with_wind['position']
        x_at_apogee = r[0][np.argmax(r[2])]
        assert x_at_apogee > 0.0

    def test_alpha_bounded_for_stable_rocket(self, flight_with_wind):
        """10 m/s yan rüzgârda kararlı araç α'yı sınırlı tutmalı."""
        assert flight_with_wind['max_alpha_deg'] < 15.0

    def test_wind_direction_isotropy(self):
        """Dik atışta fizik rüzgâr yönünden bağımsız olmalı (izotropi).

        q̇ = ½·ω⊗q regresyonu: ters Hamilton sırası yalnız kuzey-rüzgârı
        senaryosunda doğru sonucu taklit eder; doğu rüzgârında apoje
        çöker (5178 m → 128 m) ve α patlar. Bu test o hatayı kilitler.
        """
        results = {}
        for name, wdir in [('north', 0.0), ('east', 90.0), ('ne', 45.0)]:
            solver = SixDOFTrajectory(
                aero=_standard_rocket(), dry_mass=8.0, propellant_mass=4.0,
                thrust=1200.0, burn_time=6.0, cd0=0.45,
                wind_speed=8.0, wind_direction_deg=wdir,
                launch_elevation_deg=90.0)
            results[name] = solver.solve(t_max=200.0)

        ap = {k: v['apogee'] for k, v in results.items()}
        al = {k: v['max_alpha_deg'] for k, v in results.items()}
        # Apoje ve max α her yönde aynı olmalı (%1 tolerans)
        assert ap['east'] == pytest.approx(ap['north'], rel=0.01)
        assert ap['ne'] == pytest.approx(ap['north'], rel=0.01)
        assert al['east'] == pytest.approx(al['north'], rel=0.02)
        # Sürüklenme rüzgârın geldiği yöne: kuzey rüzgârı → +x (kuzey),
        # doğu rüzgârı → +y (doğu); büyüklükler eşit olmalı
        r_n, r_e = results['north']['position'], results['east']['position']
        drift_n = r_n[0][np.argmax(r_n[2])]
        drift_e = r_e[1][np.argmax(r_e[2])]
        assert drift_n > 0 and drift_e > 0
        assert drift_e == pytest.approx(drift_n, rel=0.01)


class TestInstability:
    def test_negative_static_margin_flagged(self):
        """CP'nin önünde CG (kanatsız uzun araç) → kararsız işareti."""
        aero = BarrowmanAero(body_diameter=0.1, nose_length=0.4,
                             body_length=2.0, fin_count=0)  # kanat yok
        solver = SixDOFTrajectory(
            aero=aero, dry_mass=8.0, propellant_mass=4.0,
            thrust=1200.0, burn_time=6.0, cd0=0.45,
            wind_speed=3.0, launch_elevation_deg=88.0)
        res = solver.solve(t_max=60.0)
        # CP≈0.19m, CG≈1m → marj negatif
        assert res['static_margin_full'] < 0
        assert not res['stable']

    def test_transient_thrust_curve_accepted(self):
        """Transient çözücü çıktısı doğrudan itki eğrisi olarak kullanılabilir."""
        curve = {'time': np.linspace(0.05, 6.0, 60),
                 'thrust': np.linspace(1400, 900, 60)}  # blowdown benzeri
        solver = SixDOFTrajectory(
            aero=_standard_rocket(), dry_mass=8.0, propellant_mass=4.0,
            thrust_curve=curve, cd0=0.45, launch_elevation_deg=90.0)
        res = solver.solve(t_max=200.0)
        assert res['apogee'] > 1000.0
        assert res['stable']
