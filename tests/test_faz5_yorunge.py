"""Faz 5 / yörünge bulguları — bekçi testleri (B1, B2, B3, B6, B7).

Bu dosya Faz 5 hata avında ÖLÇÜLEN beş kritik bulgunun düzeltmesini
kilitler. Her sınıfın docstring'i düzeltme ÖNCESİ ölçümü taşır; sayı
gerilerse test kırmızıya döner.

B1 — Çözücü olayı tetiklenmediğinde entegrasyon ufkunun SON NOKTASI
     "apoje"/"iniş" diye yayımlanıyordu. Ölçüldü (HEAD 9d3728e, 30° atış):
     apogee_altitude = −54 722,40 m, landing_time = 1000,00 s,
     total_flight_time = 1306,00 s = (t_b+2) + 300 + 1000, yani tam olarak
     üç zaman-aşımı tavanının toplamı. Uç HTTP 200 / status "success"
     dönüyor, tek uyarı paraşüt varsayımıydı.

B2 — Fırlatma rayı modellenmiyordu; itki v > 1 m/s olur olmaz hız
     vektörüne kilitleniyordu (keyfi eşik). Ölçüldü (600 N, T/W = 2,19,
     85° atış): apoje 13,86 m / uçuş 1306,00 s. Aynı atmosfer ve sürükleme
     fonksiyonuyla yazılmış bağımsız referanslar: itki rampa yönünde sabit
     → 286,86 m; 25 m/s ray çıkışından sonra yerçekimi dönüşü → 279,96 m.
     Yani apoje 20 kat eksik, uçuş süresi 75 kat fazlaydı.

B3 — Güçlü ve serbest fazlarda yer düzlemi kısıtı yoktu. Ölçüldü: araç
     95 261 m YERALTINA entegre ediliyor, ``_atm_full`` negatif irtifayı
     0'a kırptığı için orada deniz seviyesi yoğunluğunda "uçuyordu".

B6 — 6-DOF çözücüsünde ``end_reason = 'time_limit'`` sonucu geçerli sayı
     gibi yayımlanıyordu (``converged`` True olduğu için). Ölçüldü:
     t_max = 1 s → apogee 46,19 m @ 1,0 s; thrust = 1e7 N → apogee
     787 781 371 m @ 400,0 s. İkisinde de araç hâlâ tırmanıyordu.

B7 — Sonlu olmayan (NaN/Inf) girdi çözücüyü SÜRESİZ kilitliyordu. Ölçüldü:
     ``thrust = NaN`` ile ``solve(t_max=400)`` 60 s'de dönmedi (timeout
     çıkış kodu 124); sağlıklı çağrı 0,09 s. Aynı kilitlenme 2B modülde de
     ölçüldü (45 s'de dönmedi). Eski muhafız ``not thrust`` NaN'ı
     yakalamıyordu: ``not float('nan')`` Python'da False'tur.
"""

import time

import numpy as np
import pytest

import hrma.analysis.trajectory_analysis as TA
from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
from hrma.analysis.six_dof_trajectory import BarrowmanAero, SixDOFTrajectory

G = 9.80665

# Referans araç/motor — Faz 5 raporundaki ölçümlerle AYNI.
MOTOR = {
    'thrust': 3000.0,
    'burn_time': 4.0,
    'total_impulse': 12000.0,
    'isp': 200.0,
    'propellant_mass_total': 8.0,
}
MASS_DRY = 20.0
DIAMETER = 0.15
CD0 = 0.5


def _run(thrust=None, burn_time=None, mass_dry=MASS_DRY, cd0=CD0, **launch):
    motor = dict(MOTOR)
    if thrust is not None:
        motor['thrust'] = float(thrust)
    if burn_time is not None:
        motor['burn_time'] = float(burn_time)
    motor['total_impulse'] = motor['thrust'] * motor['burn_time']
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=mass_dry, diameter=DIAMETER,
                              drag_coefficient=cd0)
    params = {'launch_angle': 85.0, 'launch_altitude': 0.0,
              'wind_speed': 0.0, 'wind_direction': 0.0}
    params.update(launch)
    return ta.calculate_trajectory(motor, params)


def _codes(result):
    return [w['code'] for w in result.get('warnings', [])]


def _aero():
    return BarrowmanAero(body_diameter=0.1, nose_length=0.3, body_length=2.0,
                         nose_type='ogive', fin_count=4, fin_root_chord=0.15,
                         fin_tip_chord=0.075, fin_span=0.1, fin_sweep=0.05)


# ---------------------------------------------------------------------------
# B3 — YER DÜZLEMİ KISITI
# ---------------------------------------------------------------------------
class TestGroundConstraint:
    """Hiçbir faz zeminin altına inemez; temas SONLANDIRMA olayıdır."""

    @pytest.mark.parametrize('angle', list(range(0, 95, 5)))
    def test_no_phase_goes_underground(self, angle):
        r = _run(launch_angle=float(angle))
        z = np.asarray(r['trajectory']['altitude'])
        # Olay kökü brentq ile bulunduğu için mikro-negatif değer olabilir;
        # ÖLÇÜLEN en kötü sapma −0,0079 m. Eski kod −95 261 m veriyordu.
        assert z.min() > -0.05, (
            f"{angle}° atışta araç yeraltına indi: min z = {z.min():.3f} m")

    def test_flight_time_is_not_the_sum_of_solver_ceilings(self):
        """1306 s = (t_b+2) + 300 + 1000 imzası bir daha görülmemeli."""
        for angle in (0, 5, 10, 20, 30, 35):
            r = _run(launch_angle=float(angle))
            tof = r['performance']['trajectory_metrics']['total_flight_time']
            if tof is None:
                continue
            assert tof < 1000.0, (
                f"{angle}°: uçuş süresi {tof:.2f} s — zaman-aşımı tavanı imzası")

    def test_ground_impact_before_apogee_is_flagged_as_error(self):
        """T/W ≈ 1,09: araç apojeye varamadan yere çarpar, bu BEYAN edilir."""
        r = _run(thrust=300.0, launch_angle=85.0)
        fs = r['flight_status']
        assert fs['end_reason'] == 'ground_impact_before_apogee'
        assert fs['ground_impact_phase'] in ('powered', 'coasting')
        assert fs['apogee_reached'] is False
        errs = [w for w in r['warnings']
                if w['code'] == 'warn.trajectory.ground_impact_before_apogee']
        assert errs and errs[0]['severity'] == 'error'

    def test_apogee_time_is_the_real_peak_even_on_a_crash_flight(self):
        """Serbest faz apoje olayıyla bitmediyse apoje anı ÇARPMA anı olmaz."""
        r = _run(thrust=300.0, launch_angle=85.0)
        t = np.asarray(r['trajectory']['time'])
        z = np.asarray(r['trajectory']['altitude'])
        peak = float(t[int(np.argmax(z))])
        reported = r['performance']['phase_breakdown']['apogee_time']
        assert reported == pytest.approx(peak, abs=0.05)
        assert reported < float(t[-1]), "apoje anı çarpma anından önce olmalı"

    def test_ground_plane_follows_launch_site_elevation(self):
        """Zemin deniz seviyesi değil, FIRLATMA SAHASI kotudur."""
        r = _run(launch_angle=85.0, launch_altitude=1500.0)
        z = np.asarray(r['trajectory']['altitude'])
        assert z.min() > 1500.0 - 0.05, (
            f"1500 m rakımlı sahada araç saha kotunun altına indi: {z.min():.2f} m")


# ---------------------------------------------------------------------------
# B1 — ÇÖZÜCÜ OLAYI TETİKLENMEDİYSE SONUÇ YAYIMLANMAZ
# ---------------------------------------------------------------------------
class TestSolverEventGate:

    def test_every_phase_publishes_its_end_reason(self):
        r = _run()
        phases = r['trajectory']['phases']
        for name in ('powered', 'coasting', 'descent'):
            assert 'end_reason' in phases[name], f"{name}: end_reason yok"
        assert r['flight_status']['valid'] is True
        assert r['flight_status']['end_reason'] == 'landed'

    def test_coasting_time_limit_nulls_apogee(self, monkeypatch):
        """Serbest faz tavana çarptıysa apoje BİLİNMİYOR — sayı yayımlanmaz."""
        monkeypatch.setattr(TA, 'COASTING_TIME_LIMIT_S', 1.0)
        r = _run(launch_angle=85.0)
        fs = r['flight_status']
        assert fs['phase_end_reasons']['coasting'] == 'time_limit'
        assert fs['valid'] is False
        tm = r['performance']['trajectory_metrics']
        assert tm['max_altitude'] is None
        assert tm['total_flight_time'] is None
        assert tm['range_distance'] is None
        assert tm['landing_velocity'] is None
        assert r['performance']['phase_breakdown']['apogee_time'] is None
        assert r['performance']['motor_performance']['altitude_efficiency'] is None
        errs = [w for w in r['warnings']
                if w['code'] == 'warn.trajectory.solver_no_event']
        assert errs and errs[0]['severity'] == 'error'

    def test_descent_time_limit_keeps_apogee_but_nulls_landing(self, monkeypatch):
        """İniş tavana çarptıysa apoje GERÇEKTİR, iniş bilinmiyor."""
        monkeypatch.setattr(TA, 'DESCENT_TIME_LIMIT_S', 5.0)
        r = _run(launch_angle=85.0)
        fs = r['flight_status']
        assert fs['phase_end_reasons']['descent'] == 'time_limit'
        assert fs['valid'] is False
        tm = r['performance']['trajectory_metrics']
        assert tm['max_altitude'] is not None and tm['max_altitude'] > 1000.0
        assert tm['landing_velocity'] is None
        assert tm['total_flight_time'] is None
        assert r['trajectory']['phases']['descent']['landed'] is False

    def test_large_parachute_still_lands_within_the_horizon(self):
        """Gerçekçi büyük paraşüt (20 m², 3,4 m/s) artık ufka sığar.

        Eski 1000 s tavanında araç 1000 s sonunda hâlâ 185,11 m havadaydı
        ama kod ``landing_time = 1000,00 s`` yayımlıyordu.
        """
        r = _run(launch_angle=85.0, parachute_area=20.0)
        d = r['trajectory']['phases']['descent']
        assert d['end_reason'] == 'ground'
        assert d['landed'] is True
        assert 900.0 < d['landing_time'] < 1400.0
        assert r['performance']['trajectory_metrics']['landing_velocity'] < 4.0

    def test_healthy_flight_publishes_every_number(self):
        tm = _run()['performance']['trajectory_metrics']
        for key in ('max_altitude', 'max_velocity', 'total_flight_time',
                    'range_distance', 'landing_velocity'):
            assert tm[key] is not None, f"sağlıklı uçuşta {key} None olmamalı"


# ---------------------------------------------------------------------------
# B2 — FIRLATMA RAYI
# ---------------------------------------------------------------------------
class TestLaunchRail:

    def test_rail_absent_is_declared_not_modelled(self):
        r = _run()
        rail = r['launch_rail']
        assert rail['modelled'] is False
        assert rail['length_m'] is None
        assert rail['exit_velocity_m_s'] is None
        assert 'NOT_MODELLED' in rail['basis']
        assert 'warn.trajectory.launch_rail_not_modelled' in _codes(r)

    def test_rail_supplied_is_modelled_and_reported(self):
        r = _run(launch_rail_length=5.0)
        rail = r['launch_rail']
        assert rail['modelled'] is True
        assert rail['length_m'] == pytest.approx(5.0)
        assert rail['exit_velocity_m_s'] > 0.0
        assert rail['exit_time_s'] > 0.0
        assert 'warn.trajectory.launch_rail_not_modelled' not in _codes(r)

    def test_rail_exit_velocity_grows_with_rail_length(self):
        v = [_run(thrust=600.0, launch_rail_length=L)['launch_rail'][
            'exit_velocity_m_s'] for L in (3.0, 5.0, 10.0)]
        assert v[0] < v[1] < v[2], f"ray çıkış hızı ray boyuyla artmalı: {v}"

    def test_attitude_is_locked_on_the_rail(self):
        """Ray üstünde uçuş yolu açısı fırlatma açısında SABİT kalmalı."""
        r = _run(thrust=600.0, launch_angle=85.0, launch_rail_length=10.0)
        p = r['trajectory']['phases']['powered']
        t_exit = p['rail_exit_time']
        t = np.asarray(p['time'])
        vx = np.asarray(p['velocity_x'])
        vz = np.asarray(p['velocity_z'])
        on = (t > 0.0) & (t < t_exit)
        gamma = np.degrees(np.arctan2(vz[on], vx[on]))
        assert np.allclose(gamma, 85.0, atol=1e-6), (
            f"ray üstünde γ sabit olmalı: {gamma.min():.4f}..{gamma.max():.4f}")

    def test_low_thrust_to_weight_matches_independent_reference(self):
        """T/W = 2,19 (600 N, 85°) — Faz 5 raporundaki bağımsız referanslar.

        Ölçülen eski değer 13,86 m idi (referansın 1/20'si).
        """
        no_rail = _run(thrust=600.0, launch_angle=85.0)[
            'performance']['trajectory_metrics']['max_altitude']
        rail = _run(thrust=600.0, launch_angle=85.0, launch_rail_length=5.0)[
            'performance']['trajectory_metrics']['max_altitude']
        # Referans A (itki rampa yönünde sabit) = 286,86 m
        assert abs(no_rail - 286.86) / 286.86 < 0.05, (
            f"raysız model referans A'dan sapıyor: {no_rail:.2f} m")
        # Referans B (25 m/s ray çıkışı sonrası yerçekimi dönüşü) = 279,96 m
        assert abs(rail - 279.96) / 279.96 < 0.05, (
            f"raylı model referans B'den sapıyor: {rail:.2f} m")

    def test_no_magic_one_metre_per_second_threshold(self):
        """Kaynakta eski keyfi ``v_mag > 1.0`` eşiği kalmamalı."""
        import inspect
        src = inspect.getsource(TrajectoryAnalyzer._calculate_powered_flight)
        assert 'v_mag > 1.0' not in src

    def test_thrust_to_weight_band_is_physical(self):
        """T/W ≳ 1,5 olan her araç dik atışta POZİTİF apoje vermeli.

        Eski kod T/W < ~2,9 olan HER aracı çöktürüyordu (85°'de bile).
        """
        for F, expect_min in ((400.0, 50.0), (600.0, 200.0),
                              (800.0, 400.0), (1000.0, 700.0)):
            r = _run(thrust=F, launch_angle=85.0)
            ap = r['performance']['trajectory_metrics']['max_altitude']
            assert ap is not None and ap > expect_min, (
                f"F={F:.0f} N (T/W={F / (28 * G):.2f}): apoje {ap} m")


# ---------------------------------------------------------------------------
# KORUNUM / TUTARLILIK
# ---------------------------------------------------------------------------
class TestConservation:

    @pytest.mark.parametrize('angle', [45.0, 60.0, 75.0, 90.0])
    def test_dragfree_apogee_matches_energy_bound(self, angle):
        """Cd = 0: apoje ≈ z_bo + (v_bo·sin γ_bo)²/(2g), %3 içinde."""
        r = _run(cd0=0.0, launch_angle=angle)
        p = r['trajectory']['phases']['powered']
        vx, vz = float(p['burnout_state'][2]), float(p['burnout_state'][3])
        z_bo = float(p['burnout_altitude'])
        analytic = z_bo + vz ** 2 / (2.0 * G)
        sim = r['performance']['trajectory_metrics']['max_altitude']
        assert abs(sim - analytic) / analytic < 0.03, (
            f"{angle}°: sim={sim:.1f} m, analitik={analytic:.1f} m "
            f"(vx={vx:.1f}, vz={vz:.1f})")

    def test_apogee_stays_below_total_impulse_ceiling(self):
        """Apoje, toplam impulstan çıkan kaba tavanın ALTINDA kalmalı.

        c_eff = F/ṁ = 1500 m/s, Δv = c·ln(m0/mf) = 504,7 m/s, yerçekimi
        kaybı g·t_b = 39,2 m/s → kaba tavan (Δv−g·t_b)²/2g = 11 047 m.
        Sürüklemeli apoje bunun altında ve MAKUL bir kesirde olmalı.
        """
        c_eff = MOTOR['thrust'] / (MOTOR['propellant_mass_total'] / MOTOR['burn_time'])
        dv = c_eff * np.log((MASS_DRY + MOTOR['propellant_mass_total']) / MASS_DRY)
        ceiling = (dv - G * MOTOR['burn_time']) ** 2 / (2.0 * G)
        for angle in (30.0, 60.0, 85.0, 90.0):
            ap = _run(launch_angle=angle)[
                'performance']['trajectory_metrics']['max_altitude']
            frac = ap / (ceiling * np.sin(np.radians(angle)) ** 2)
            assert 0.2 < frac < 1.0, (
                f"{angle}°: apoje/kaba tavan = {frac:.3f} (apoje {ap:.1f} m)")

    def test_apogee_is_monotonic_in_launch_angle(self):
        apogees = []
        for angle in range(10, 95, 5):
            ap = _run(launch_angle=float(angle))[
                'performance']['trajectory_metrics']['max_altitude']
            apogees.append((angle, ap))
        for (a1, p1), (a2, p2) in zip(apogees, apogees[1:]):
            assert p2 > p1, f"apoje {a1}°→{a2}° arasında düştü: {p1} → {p2}"


# ---------------------------------------------------------------------------
# B7 — SONLU-DEĞER KAPISI (fail-closed)
# ---------------------------------------------------------------------------
class TestNonFiniteInputIsRejected:

    @pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf')])
    def test_2d_solver_rejects_non_finite_thrust_fast(self, bad):
        t0 = time.time()
        with pytest.raises(ValueError):
            _run(thrust=bad)
        assert time.time() - t0 < 5.0, "muhafız çözücüye girmeden dönmeli"

    def test_2d_solver_rejects_non_finite_launch_params(self):
        for key in ('launch_angle', 'wind_speed', 'parachute_area'):
            with pytest.raises(ValueError):
                _run(**{key: float('nan')})

    def test_2d_solver_rejects_zero_burn_time(self):
        """ṁ = m_yakıt/t_b sıfır bölendir."""
        with pytest.raises(ValueError):
            _run(burn_time=0.0)

    @pytest.mark.parametrize('bad', [float('nan'), float('inf')])
    def test_six_dof_rejects_non_finite_thrust_fast(self, bad):
        t0 = time.time()
        with pytest.raises(ValueError):
            SixDOFTrajectory(aero=_aero(), dry_mass=20.0, propellant_mass=10.0,
                             thrust=bad, burn_time=5.0)
        assert time.time() - t0 < 5.0

    def test_six_dof_rejects_non_finite_mass_and_cd(self):
        for kwargs in ({'dry_mass': float('nan')},
                       {'propellant_mass': float('inf')},
                       {'cd0': float('nan')},
                       {'wind_speed': float('inf')}):
            base = dict(aero=_aero(), dry_mass=20.0, propellant_mass=10.0,
                        thrust=3000.0, burn_time=5.0)
            base.update(kwargs)
            with pytest.raises(ValueError):
                SixDOFTrajectory(**base)

    def test_six_dof_rejects_non_positive_dry_mass(self):
        with pytest.raises(ValueError):
            SixDOFTrajectory(aero=_aero(), dry_mass=-5.0, propellant_mass=10.0,
                             thrust=3000.0, burn_time=5.0)

    def test_six_dof_rejects_non_finite_thrust_curve(self):
        with pytest.raises(ValueError):
            SixDOFTrajectory(
                aero=_aero(), dry_mass=20.0, propellant_mass=10.0,
                thrust_curve={'time': [0.0, 1.0, 2.0],
                              'thrust': [100.0, float('nan'), 100.0]})


# ---------------------------------------------------------------------------
# B6 — 6-DOF ZAMAN SINIRI SONUÇ DEĞİLDİR
# ---------------------------------------------------------------------------
class TestSixDofTimeLimit:

    @staticmethod
    def _solve(**kw):
        base = dict(aero=_aero(), dry_mass=20.0, propellant_mass=10.0,
                    thrust=3000.0, burn_time=5.0)
        t_max = kw.pop('t_max', 400.0)
        base.update(kw)
        return SixDOFTrajectory(**base).solve(t_max=t_max)

    def test_short_horizon_does_not_publish_an_apogee(self):
        res = self._solve(t_max=1.0)
        assert res['end_reason'] == 'time_limit'
        assert res['apogee'] is None
        assert res['apogee_time'] is None
        assert res['stable'] is None
        assert res['peak_values_are_lower_bounds'] is True
        # Ufuk içinde GERÇEKTEN ölçülen tepe hız korunur (alt sınır olarak).
        assert res['max_speed'] is not None and res['max_speed'] > 0.0
        codes = [w['code'] for w in res['warnings']]
        assert 'warn.sixdof.integration_time_limit' in codes

    def test_absurd_thrust_does_not_publish_an_apogee(self):
        """thrust = 1e7 N: eski kod 787 781 371 m'yi "apoje" diye veriyordu."""
        res = self._solve(thrust=1e7)
        assert res['end_reason'] == 'time_limit'
        assert res['apogee'] is None
        assert res['stable'] is None

    def test_normal_flight_still_publishes_apogee(self):
        res = self._solve()
        assert res['end_reason'] == 'apogee'
        assert res['apogee'] is not None and res['apogee'] > 1000.0
        assert res['stable'] is True
        assert res.get('peak_values_are_lower_bounds') is None

    def test_solve_warnings_do_not_accumulate(self):
        """Aynı örnekte iki kez solve → uyarılar birikmemeli."""
        solver = SixDOFTrajectory(aero=_aero(), dry_mass=20.0,
                                  propellant_mass=10.0, thrust=3000.0,
                                  burn_time=5.0)
        first = solver.solve(t_max=1.0)['warnings']
        second = solver.solve(t_max=1.0)['warnings']
        assert len(first) == len(second)


# ---------------------------------------------------------------------------
# GRAFİK KATMANI — None değerlerde çökmemeli
# ---------------------------------------------------------------------------
class TestPlotLayerSurvivesInvalidRun:

    def test_plot_json_is_produced_when_apogee_is_unknown(self, monkeypatch):
        monkeypatch.setattr(TA, 'COASTING_TIME_LIMIT_S', 1.0)
        r = _run(launch_angle=85.0)
        out = TrajectoryAnalyzer().create_trajectory_plots(r)
        assert isinstance(out, str) and len(out) > 100
        assert 'bdata' not in out

    def test_plot_json_is_produced_after_ground_impact(self):
        r = _run(thrust=300.0, launch_angle=85.0)
        out = TrajectoryAnalyzer().create_trajectory_plots(r)
        assert isinstance(out, str) and len(out) > 100


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
