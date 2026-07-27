"""v2.6.2 fizik denetimi kilitleri — 2B yörünge modülü (F028 / F080 / F082).

Bu dosya PHYSICS_AUDIT.md'deki üç bulgunun düzeltmesini kilitler:

F028 — Yanma-sonu (burnout) örnekleme anı.
    ``_calculate_performance_metrics`` yanma-sonu irtifasını güçlü fazın
    ``max_altitude_powered`` alanından (burn_time+2 s penceresinin TEPESİ),
    hızını ise pencerenin SON adımından okuyordu; iki büyüklük FARKLI
    anlardan geliyordu. ÖLÇÜLDÜ: 1487.0 m / 300.8 m/s raporlanıyordu,
    gerçek yanma-sonu 806.7 m / 399.7 m/s. Ayrıca ``apogee_time`` ofset
    olarak burn_time kullandığı için apojeyi 2 s ERKEN veriyordu
    (24.47 s yerine gerçek 26.47 s).

F080 — Paraşüt alanı araçtan bağımsız 2.0 m² sabit koduydu; buna rağmen
    ``landing_velocity`` bir güvenlik metriği olarak raporlanıyordu.
    Artık kullanıcı girdisi; verilmezse sonuç "varsayım" olarak
    işaretlenir ve uyarı üretilir.

F082 — ``wind_direction`` docstring'de "rüzgârın ESTİĞİ yön" deniyordu ve
    hava kütlesi vektörü +V·cos φ alınıyordu. Meteorolojik standart (WMO)
    rüzgâr yönünü GELDİĞİ yön olarak tanımlar; kardeş 6-DOF modülü zaten
    doğru konvansiyondaydı. Aynı girdi iki panelde TERS anlam taşıyordu.
"""

import numpy as np
import pytest

from hrma.analysis.trajectory_analysis import (
    DEFAULT_PARACHUTE_AREA_M2, TrajectoryAnalyzer,
)

MOTOR = {
    'thrust': 3000.0,
    'burn_time': 4.0,
    'total_impulse': 12000.0,
    'isp': 200.0,
    'propellant_mass_total': 8.0,
}


def _run(**launch_overrides):
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                              drag_coefficient=0.5)
    params = {'launch_angle': 85.0, 'launch_altitude': 0.0,
              'wind_speed': 0.0, 'wind_direction': 0.0}
    params.update(launch_overrides)
    return ta.calculate_trajectory(MOTOR, params)


# ---------------------------------------------------------------------------
# F028 — yanma-sonu eşzamanlı örnekleme
# ---------------------------------------------------------------------------
class TestBurnoutSampling:

    def test_metrics_read_burnout_fields_not_window_peak(self):
        """Metrikler t=burn_time'daki değerleri okumalı, pencere tepesini değil."""
        r = _run()
        powered = r['trajectory']['phases']['powered']
        mp = r['performance']['motor_performance']
        assert mp['burnout_altitude'] == pytest.approx(
            powered['burnout_altitude'], rel=1e-12)
        assert mp['burnout_velocity'] == pytest.approx(
            powered['burnout_velocity'], rel=1e-12)
        # Pencere tepesi yanma-sonu irtifasından BELİRGİN yüksek (2 s serbest
        # tırmanış) — eski hata tam olarak bu farktı.
        assert powered['max_altitude_powered'] > 1.5 * mp['burnout_altitude']

    def test_burnout_state_matches_trajectory_at_burn_time(self):
        """Yanma-sonu irtifa/hız, yörüngenin t=burn_time anıyla uyumlu."""
        r = _run()
        powered = r['trajectory']['phases']['powered']
        t_b = MOTOR['burn_time']
        z_at_tb = float(np.interp(t_b, powered['time'], powered['position_z']))
        vx = float(np.interp(t_b, powered['time'], powered['velocity_x']))
        vz = float(np.interp(t_b, powered['time'], powered['velocity_z']))
        mp = r['performance']['motor_performance']
        assert mp['burnout_altitude'] == pytest.approx(z_at_tb, rel=1e-9)
        assert mp['burnout_velocity'] == pytest.approx(np.hypot(vx, vz),
                                                       rel=1e-9)

    def test_burnout_velocity_is_flight_maximum_region(self):
        """İtki kesildiği an hız zirvededir; yanma-sonu hızı max hıza yakın.

        Eski hata hızı 2 s sonradan okuduğu için yanma-sonu hızını
        DÜŞÜK (300.8 m/s vs 399.7 m/s) gösteriyordu.
        """
        r = _run()
        v_max = r['performance']['trajectory_metrics']['max_velocity']
        v_bo = r['performance']['motor_performance']['burnout_velocity']
        assert v_bo == pytest.approx(v_max, rel=0.02)

    def test_apogee_time_matches_actual_peak(self):
        """phase_breakdown.apogee_time birleşik yörüngenin tepe zamanına eşit.

        Eski ofset (burn_time) güçlü fazın gerçek bitiş anını (burn_time+2)
        yerine kullandığı için apojeyi 2 s erken raporluyordu.
        """
        r = _run()
        t = np.asarray(r['trajectory']['time'])
        z = np.asarray(r['trajectory']['altitude'])
        t_peak = float(t[int(np.argmax(z))])
        assert r['performance']['phase_breakdown']['apogee_time'] == \
            pytest.approx(t_peak, abs=0.05)

    def test_altitude_efficiency_uses_true_burnout(self):
        """altitude_efficiency = burnout_altitude / apoje (şişirilmemiş)."""
        r = _run()
        mp = r['performance']['motor_performance']
        apogee = r['performance']['trajectory_metrics']['max_altitude']
        assert mp['altitude_efficiency'] == pytest.approx(
            mp['burnout_altitude'] / apogee * 100.0, rel=1e-9)
        # Bu araçta gerçek oran ~%20; eski hata ~%38 gösteriyordu.
        assert 10.0 < mp['altitude_efficiency'] < 30.0


# ---------------------------------------------------------------------------
# F080 — paraşüt alanı kullanıcı girdisi
# ---------------------------------------------------------------------------
class TestParachuteInput:

    def test_default_area_is_flagged_as_assumed(self):
        """Alan verilmezse metrik 'varsayım' işaretli ve uyarı üretilir."""
        r = _run()
        tm = r['performance']['trajectory_metrics']
        assert tm['landing_velocity_assumed'] is True
        assert tm['parachute_area_m2'] == pytest.approx(
            DEFAULT_PARACHUTE_AREA_M2)
        codes = [w['code'] for w in r.get('warnings', [])]
        assert 'warn.trajectory.parachute_area_assumed' in codes

    def test_user_area_removes_assumption_flag(self):
        r = _run(parachute_area=3.0)
        tm = r['performance']['trajectory_metrics']
        assert tm['landing_velocity_assumed'] is False
        assert tm['parachute_area_m2'] == pytest.approx(3.0)
        codes = [w['code'] for w in r.get('warnings', [])]
        assert 'warn.trajectory.parachute_area_assumed' not in codes

    def test_landing_velocity_scales_with_area(self):
        """v_iniş ∝ 1/sqrt(Cd·S): alan 4 katına çıkınca hız yarıya iner."""
        v_small = _run(parachute_area=1.0)[
            'performance']['trajectory_metrics']['landing_velocity']
        v_big = _run(parachute_area=4.0)[
            'performance']['trajectory_metrics']['landing_velocity']
        assert v_big == pytest.approx(v_small / 2.0, rel=0.05)

    def test_default_area_reproduces_legacy_number(self):
        """Geriye dönük kilit: alan verilmeyince eski 2.0 m² sonucu birebir."""
        v_default = _run()['performance']['trajectory_metrics']['landing_velocity']
        v_explicit = _run(parachute_area=DEFAULT_PARACHUTE_AREA_M2)[
            'performance']['trajectory_metrics']['landing_velocity']
        assert v_default == pytest.approx(v_explicit, rel=1e-12)

    def test_invalid_area_falls_back_to_assumption(self):
        """Negatif/geçersiz alan sessizce kullanılmaz, varsayıma düşülür."""
        r = _run(parachute_area=-1.0)
        assert r['performance']['trajectory_metrics'][
            'landing_velocity_assumed'] is True

    def test_parachute_cd_is_configurable(self):
        """Cd artırılınca iniş hızı düşer (aynı alanda)."""
        v_low = _run(parachute_area=2.0, parachute_cd=0.8)[
            'performance']['trajectory_metrics']['landing_velocity']
        v_high = _run(parachute_area=2.0, parachute_cd=1.4)[
            'performance']['trajectory_metrics']['landing_velocity']
        assert v_high < v_low


# ---------------------------------------------------------------------------
# F082 — meteorolojik rüzgâr yönü konvansiyonu
# ---------------------------------------------------------------------------
class TestWindDirectionConvention:

    def test_wind_vector_points_away_from_source_direction(self):
        """wind_direction = rüzgârın GELDİĞİ yön → vektör tersine bakar."""
        vx, vz = TrajectoryAnalyzer._wind_vector(10.0, 0.0)
        assert vx == pytest.approx(-10.0)
        assert vz == pytest.approx(0.0)
        vx180, _ = TrajectoryAnalyzer._wind_vector(10.0, np.pi)
        assert vx180 == pytest.approx(10.0)

    def test_matches_six_dof_sibling_convention(self):
        """Aynı girdi iki modülde AYNI hava-kütlesi vektörünü vermeli."""
        from hrma.analysis.six_dof_trajectory import (
            BarrowmanAero, SixDOFTrajectory)
        aero = BarrowmanAero(body_diameter=0.10, nose_length=0.40,
                             body_length=2.0, fin_count=4,
                             fin_root_chord=0.20, fin_tip_chord=0.10,
                             fin_span=0.11, fin_sweep=0.08)
        for wdir_deg in (0.0, 45.0, 90.0, 180.0, 270.0):
            solver = SixDOFTrajectory(
                aero=aero, dry_mass=8.0, propellant_mass=4.0,
                thrust=1200.0, burn_time=6.0, wind_speed=12.0,
                wind_direction_deg=wdir_deg, coriolis=False)
            vx2d, _ = TrajectoryAnalyzer._wind_vector(
                12.0, np.radians(wdir_deg))
            # 2B model 6-DOF'un kuzey (x) bileşeniyle karşılaştırılır
            assert vx2d == pytest.approx(float(solver.wind[0]), abs=1e-12)

    def test_north_wind_drifts_vehicle_south(self):
        """Kuzeyden (wind_direction=0) esen rüzgâr aracı güneye (−x) taşır."""
        r = _run(launch_angle=90.0, wind_speed=10.0, wind_direction=0.0)
        assert r['performance']['trajectory_metrics']['range_distance'] < -100.0

    def test_opposite_directions_mirror(self):
        """0° ve 180° rüzgâr, dik atışta simetrik sürüklenme üretir."""
        d0 = _run(launch_angle=90.0, wind_speed=10.0, wind_direction=0.0)[
            'performance']['trajectory_metrics']['range_distance']
        d180 = _run(launch_angle=90.0, wind_speed=10.0, wind_direction=180.0)[
            'performance']['trajectory_metrics']['range_distance']
        assert d0 == pytest.approx(-d180, rel=1e-6)

    def test_drift_magnitude_grows_with_wind(self):
        """Sürüklenme büyüklüğü rüzgârla monoton artar (yön konvansiyonundan
        bağımsız kilit — bu testin eski hâli işaret varsayıyordu)."""
        d10 = abs(_run(launch_angle=90.0, wind_speed=10.0)[
            'performance']['trajectory_metrics']['range_distance'])
        d20 = abs(_run(launch_angle=90.0, wind_speed=20.0)[
            'performance']['trajectory_metrics']['range_distance'])
        assert d20 > d10 > 100.0


# ---------------------------------------------------------------------------
# F080 ek — paylaşılan analizör örneğinde kurtarma durumu sızıntısı
# ---------------------------------------------------------------------------
class TestRecoveryStateIsolation:
    """Uygulama katmanı modül düzeyinde TEK bir ``TrajectoryAnalyzer``
    örneği paylaşıyor. F080 ile paraşüt alanı örnek durumuna (``self``)
    taşındığı için, bir isteğin girdisi sonraki isteğe sızabiliyordu:
    kullanıcı alanı hiç vermese (ya da açıkça ``null`` gönderse) bile bir
    önceki isteğin paraşütünden türetilmiş iniş hızını görürdü ve
    ``landing_velocity_assumed`` yanlışlıkla ``False`` kalırdı.

    Sözleşme: anahtar AÇIKÇA verilmişse o alan tamamen o isteğin
    girdisinden belirlenir; anahtar hiç yoksa ``set_recovery_parameters``
    ile ayarlanan programatik değer korunur (eski API davranışı).
    """

    @staticmethod
    def _analyzer():
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                                  drag_coefficient=0.5)
        return ta

    @staticmethod
    def _params(**over):
        p = {'launch_angle': 85.0, 'launch_altitude': 0.0,
             'wind_speed': 0.0, 'wind_direction': 0.0}
        p.update(over)
        return p

    def test_explicit_none_returns_to_assumption(self):
        """Aynı örnekte 2. istek ``parachute_area=None`` -> varsayıma döner."""
        ta = self._analyzer()
        first = ta.calculate_trajectory(MOTOR, self._params(parachute_area=5.0))
        assert first['performance']['trajectory_metrics'][
            'landing_velocity_assumed'] is False

        second = ta.calculate_trajectory(MOTOR,
                                         self._params(parachute_area=None))
        tm = second['performance']['trajectory_metrics']
        assert tm['landing_velocity_assumed'] is True
        assert tm['parachute_area_m2'] == pytest.approx(
            DEFAULT_PARACHUTE_AREA_M2)
        codes = [w['code'] for w in second.get('warnings', [])]
        assert 'warn.trajectory.parachute_area_assumed' in codes

    def test_cd_does_not_leak_between_requests(self):
        """Cd anahtarı verilen istek, önceki isteğin Cd'sini devralmaz."""
        ta = self._analyzer()
        ta.calculate_trajectory(MOTOR,
                                self._params(parachute_area=2.0,
                                             parachute_cd=0.6))
        second = ta.calculate_trajectory(MOTOR,
                                         self._params(parachute_area=2.0,
                                                      parachute_cd=None))
        ref = _run(parachute_area=2.0)  # temiz örnek, varsayılan Cd
        assert second['performance']['trajectory_metrics']['parachute_cd'] == \
            pytest.approx(ref['performance']['trajectory_metrics']['parachute_cd'])

    def test_setter_value_survives_when_key_absent(self):
        """Anahtar HİÇ verilmezse programatik setter değeri korunur."""
        ta = self._analyzer()
        ta.set_recovery_parameters(parachute_area=5.0)
        r = ta.calculate_trajectory(MOTOR, self._params())
        tm = r['performance']['trajectory_metrics']
        assert tm['parachute_area_m2'] == pytest.approx(5.0)
        assert tm['landing_velocity_assumed'] is False
