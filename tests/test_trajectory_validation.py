"""
Trajectory Analysis Validation Tests
=====================================
HRMA trajectory modülünün (hrma.analysis.trajectory_analysis.TrajectoryAnalyzer)
fiziksel doğruluğunu referans vakalarla doğrular.

Düzeltilen kusurlar (2026-06):
  1. Fırlatma açısı konvansiyonu TERS idi (90° roketi yatay gönderiyordu).
     Düzeltildi: yükseliş açısı (ufuktan), 90° = dikey yukarı.
  2. Rüzgar hareket denklemlerine girmiyordu. Eklendi: bağıl hız sürüklemesi.
  3. Cd sabit idi. Eklendi: Mach-bağımlı Cd (subsonik/transonik/supersonik).
  4. Atmosfer >20 km keyfi exp() ile yaklaşıyordu. Düzeltildi: ISA_LAYERS tablosu.

Referans kaynaklar:
  - U.S. Standard Atmosphere 1976 (NOAA/NASA/USAF, Tablo 4) -- yoğunluk referans
  - McCoy, "Modern Exterior Ballistics" (1999) -- yükseliş açısı, rüzgar
  - Hoerner, "Fluid-Dynamic Drag" (1965) + OpenRocket Tech. Doc. -- Mach-Cd
  - Sutton & Biblarz, "Rocket Propulsion Elements" 9. baskı -- sürükleme formülü

Çalıştırma:
  cd <depo kökü> && MPLBACKEND=Agg PYTHONPATH=. \
      python3 -m pytest tests/test_trajectory_validation.py -v
"""

import numpy as np
import pytest

from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer

G = 9.80665  # m/s^2 (hrma.constants.G_0 ile tutarlı)


def _make_motor(thrust=3000.0, burn=5.0, mprop=8.0, isp=200.0):
    return {
        'thrust': thrust,
        'burn_time': burn,
        'total_impulse': thrust * burn,
        'isp': isp,
        'propellant_mass_total': mprop,
    }


def _run(launch_angle=90.0, wind_speed=0.0, wind_direction=0.0,
         mass_dry=20.0, diameter=0.15, cd0=0.5, motor=None):
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=mass_dry, diameter=diameter, drag_coefficient=cd0)
    if motor is None:
        motor = _make_motor()
    lp = {
        'launch_angle': launch_angle,
        'launch_altitude': 0.0,
        'wind_speed': wind_speed,
        'wind_direction': wind_direction,
    }
    return ta.calculate_trajectory(motor, lp)


# ---------------------------------------------------------------------------
# 1) LAUNCH-ANGLE KONVANSIYONU: 90° = dikey, 85° pozitif apogee (yere sokmaz)
# ---------------------------------------------------------------------------
class TestLaunchAngleConvention:

    def test_vertical_90deg_has_zero_downrange(self):
        """90° fırlatma tam dikey: menzil ~0, apogee pozitif ve büyük."""
        r = _run(launch_angle=90.0)
        m = r['performance']['trajectory_metrics']
        assert m['max_altitude'] > 1000.0, "90° apogee pozitif ve anlamlı olmalı"
        # Tam dikey fırlatmada (rüzgarsız) downrange ihmal edilebilir
        assert abs(m['range_distance']) < 1.0, (
            f"90° dikey fırlatmada menzil ~0 olmalı, bulunan={m['range_distance']:.2f} m"
        )

    def test_85deg_gives_positive_apogee_not_into_ground(self):
        """REGRESYON: 85° artık pozitif apogee verir (eskiden 0 m idi)."""
        r = _run(launch_angle=85.0)
        m = r['performance']['trajectory_metrics']
        assert m['max_altitude'] > 1000.0, (
            f"85° apogee pozitif olmalı (yere sokmamalı), bulunan={m['max_altitude']:.1f} m"
        )
        # 85° hafif eğik: küçük ama pozitif downrange
        assert m['range_distance'] > 0.0

    def test_lower_angle_lower_apogee(self):
        """Açı azaldıkça apogee düşer, menzil (orta açılarda) artar -- monoton fizik."""
        ap90 = _run(launch_angle=90.0)['performance']['trajectory_metrics']['max_altitude']
        ap70 = _run(launch_angle=70.0)['performance']['trajectory_metrics']['max_altitude']
        ap45 = _run(launch_angle=45.0)['performance']['trajectory_metrics']['max_altitude']
        assert ap90 > ap70 > ap45, (
            f"apogee açıyla monoton artmalı: 90={ap90:.0f}, 70={ap70:.0f}, 45={ap45:.0f}"
        )


# ---------------------------------------------------------------------------
# 2) DRAG-FREE DİKEY ATIŞ vs ANALİTİK ENERJİ TAHMİNİ
# ---------------------------------------------------------------------------
class TestEnergyConservation:

    def test_dragfree_apogee_matches_energy_bound(self):
        """Cd=0 dikey atış: apogee ≈ z_bo + v_bo^2/(2g) (sabit-g enerji), %2 içinde.

        Sapma altitude-bağımlı g'den gelir (sim biraz yüksek, beklenen yön).
        """
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15, drag_coefficient=0.0)
        r = ta.calculate_trajectory(_make_motor(), {
            'launch_angle': 90.0, 'launch_altitude': 0.0,
            'wind_speed': 0.0, 'wind_direction': 0.0,
        })
        apogee_sim = r['performance']['trajectory_metrics']['max_altitude']
        v_bo = r['performance']['motor_performance']['burnout_velocity']
        z_bo = r['performance']['motor_performance']['burnout_altitude']
        apogee_analytic = z_bo + v_bo ** 2 / (2.0 * G)
        rel_err = abs(apogee_sim - apogee_analytic) / apogee_analytic
        assert rel_err < 0.02, (
            f"drag-free apogee enerji tahminiyle %2 içinde olmalı: "
            f"sim={apogee_sim:.1f}, analitik={apogee_analytic:.1f}, err={rel_err*100:.2f}%"
        )

    def test_drag_reduces_apogee_below_dragfree(self):
        """Sürükleme apogee'yi drag-free değerin ALTINA çeker (konservatif)."""
        ap_dragfree = _run(cd0=0.0)['performance']['trajectory_metrics']['max_altitude']
        ap_drag = _run(cd0=0.5)['performance']['trajectory_metrics']['max_altitude']
        assert ap_drag < ap_dragfree, (
            f"drag'li apogee ({ap_drag:.0f}) < drag-free ({ap_dragfree:.0f}) olmalı"
        )

    def test_apogee_below_vmax_energy_upper_bound(self):
        """Apogee, max hızdan türetilen v_max^2/(2g) üst sınırının altında olmalı."""
        r = _run(cd0=0.5)
        m = r['performance']['trajectory_metrics']
        upper = m['max_velocity'] ** 2 / (2.0 * G)
        assert m['max_altitude'] < upper, (
            f"apogee ({m['max_altitude']:.0f}) < v_max^2/2g ({upper:.0f}) olmalı"
        )


# ---------------------------------------------------------------------------
# 3) RÜZGAR HAREKET DENKLEMLERİNE GİRİYOR MU?
# ---------------------------------------------------------------------------
class TestWindCoupling:

    def test_wind_produces_downwind_drift(self):
        """Dikey fırlatma + rüzgâr -> RÜZGÂRALTI yönde sürüklenme.

        KONVANSIYON (F082 düzeltmesi, v2.6.2): ``wind_direction`` rüzgârın
        GELDİĞİ yöndür — meteorolojik standart ("kuzey rüzgârı" kuzeyden eser).
        Dolayısıyla ``wind_direction=0`` +x'ten esen rüzgâr demektir ve araç
        −x yönüne, yani rüzgâraltına sürüklenir. NEGATİF menzil DOĞRUDUR.

        Bu test eskiden ``range10 > 100`` (pozitif) bekliyordu; o beklenti
        rüzgârın ESTİĞİ yön konvansiyonuna dayanıyordu ve six_dof_trajectory
        modülünün konvansiyonuyla ÇELİŞİYORDU (orada zaten
        ``wind = −V·[cos, sin, 0]`` kullanılıyordu). İki modül artık aynı
        konvansiyonu paylaşıyor — asıl düzeltilen tutarsızlık buydu.
        """
        r0 = _run(launch_angle=90.0, wind_speed=0.0)
        r10 = _run(launch_angle=90.0, wind_speed=10.0, wind_direction=0.0)
        range0 = r0['performance']['trajectory_metrics']['range_distance']
        range10 = r10['performance']['trajectory_metrics']['range_distance']
        assert abs(range0) < 1.0, 'rüzgârsız dikey: menzil ~0'
        assert abs(range10) > 100.0, (
            f'rüzgârlı dikey: belirgin sürüklenme olmalı, bulunan={range10:.1f} m')
        assert range10 < 0.0, (
            f'wind_direction=0 (kuzeyden) -> araç −x yönüne sürüklenmeli, '
            f'bulunan={range10:.1f} m (konvansiyon ters çevrilmiş olabilir)')

    def test_wind_direction_180_reverses_drift(self):
        """Ters yönden esen rüzgâr sürüklenmeyi ters çevirmeli.

        İşaret konvansiyonunun gerçekten yöne bağlı olduğunu kilitler —
        tek bir işareti sabitlemek yerine simetriyi sınar.
        """
        d0 = _run(launch_angle=90.0, wind_speed=10.0,
                  wind_direction=0.0)['performance']['trajectory_metrics']['range_distance']
        d180 = _run(launch_angle=90.0, wind_speed=10.0,
                    wind_direction=180.0)['performance']['trajectory_metrics']['range_distance']
        assert d0 * d180 < 0, f'yön 180° dönünce işaret değişmeli: {d0:.0f} / {d180:.0f}'
        assert abs(abs(d0) - abs(d180)) < 0.05 * abs(d0), 'büyüklükler simetrik olmalı'

    def test_more_wind_more_drift(self):
        """Daha fazla rüzgâr -> daha fazla sürüklenme (büyüklükçe monoton)."""
        d10 = _run(launch_angle=90.0, wind_speed=10.0)['performance']['trajectory_metrics']['range_distance']
        d20 = _run(launch_angle=90.0, wind_speed=20.0)['performance']['trajectory_metrics']['range_distance']
        assert abs(d20) > abs(d10) > 0.0, (
            f'sürüklenme rüzgârla artmalı: 10 m/s={d10:.0f}, 20 m/s={d20:.0f}')
        # Aynı yönde olmalı (işaret tutarlılığı)
        assert d10 * d20 > 0, 'iki rüzgâr hızı zıt yönlere sürüklüyor'


# ---------------------------------------------------------------------------
# 4) MACH-BAĞIMLI Cd MODELİ
# ---------------------------------------------------------------------------
class TestMachDragModel:

    def setup_method(self):
        self.ta = TrajectoryAnalyzer()
        self.ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15, drag_coefficient=0.5)

    def test_subsonic_plateau(self):
        """M<0.8: Cd ≈ Cd0 (sabit subsonik plato)."""
        for M in (0.0, 0.3, 0.6, 0.79):
            assert self.ta._drag_coefficient_mach(M) == pytest.approx(0.5, abs=1e-9)

    def test_transonic_peak(self):
        """Transonik tepe M≈1.05 civarı, Cd ≈ 1.5*Cd0 (Hoerner/OpenRocket)."""
        cd_peak = self.ta._drag_coefficient_mach(1.05)
        assert cd_peak == pytest.approx(0.75, abs=1e-6)
        # Tepe, subsonik ve yüksek-supersonik değerlerden büyük olmalı
        assert cd_peak > self.ta._drag_coefficient_mach(0.5)
        assert cd_peak > self.ta._drag_coefficient_mach(3.0)

    def test_supersonic_decays_toward_plateau(self):
        """Supersonikte Cd tepeden ~1.05*Cd0 platosuna doğru azalır."""
        cd_15 = self.ta._drag_coefficient_mach(1.5)
        cd_30 = self.ta._drag_coefficient_mach(3.0)
        cd_50 = self.ta._drag_coefficient_mach(5.0)
        assert cd_15 > cd_30 > cd_50, "supersonik Cd Mach ile azalmalı"
        # Yüksek-supersonik plato ~1.05*Cd0 üstünde kalmalı (dalga sürüklemesi)
        assert cd_50 > 0.5 * 1.0
        assert cd_50 < 0.75  # tepenin altında

    def test_cd_continuous(self):
        """Cd(M) bant sınırlarında sürekli olmalı (sıçrama yok)."""
        for M_edge in (0.8, 1.05, 1.2):
            left = self.ta._drag_coefficient_mach(M_edge - 1e-4)
            right = self.ta._drag_coefficient_mach(M_edge + 1e-4)
            assert abs(left - right) < 1e-2, f"M={M_edge} sınırında süreksizlik"


# ---------------------------------------------------------------------------
# 5) ISA ATMOSFER >20 km DOĞRULUĞU (constants.ISA_LAYERS ile tutarlı)
# ---------------------------------------------------------------------------
class TestISAAtmosphere:

    def setup_method(self):
        self.ta = TrajectoryAnalyzer()

    @pytest.mark.parametrize("alt,rho_ref,tol", [
        (0,      1.225000, 0.01),
        (11000,  0.363920, 0.01),
        (20000,  0.088035, 0.02),
        (30000,  0.018410, 0.02),   # >20 km -- eski kod burada YANLIŞTI
        (40000,  0.0039957, 0.02),  # >20 km
        (50000,  0.0010269, 0.02),  # >20 km
        (60000,  0.00030970, 0.02),  # >20 km
        (70000,  0.000082830, 0.02),  # >20 km
    ])
    def test_density_matches_us_standard_1976(self, alt, rho_ref, tol):
        """Yoğunluk US Standard Atmosphere 1976 referansıyla uyumlu (özellikle >20km)."""
        rho, _P, _T, _a = self.ta._atm_full(alt)
        rel_err = abs(rho - rho_ref) / rho_ref
        assert rel_err < tol, (
            f"{alt} m: rho_sim={rho:.6e}, rho_ref={rho_ref:.6e}, err={rel_err*100:.2f}% > {tol*100:.0f}%"
        )

    def test_density_monotonic_decrease(self):
        """Yoğunluk irtifa ile monoton azalmalı (0-70 km)."""
        alts = np.linspace(0, 70000, 50)
        rhos = [self.ta._atm_full(a)[0] for a in alts]
        assert all(rhos[i] > rhos[i + 1] for i in range(len(rhos) - 1)), \
            "yoğunluk irtifa ile monoton azalmalı"

    def test_speed_of_sound_sea_level(self):
        """Deniz seviyesi ses hızı ≈ 340.3 m/s."""
        a = self.ta._atm_full(0)[3]
        assert a == pytest.approx(340.3, abs=0.5)

    def test_atmosphere_consistent_with_solid_engine(self):
        """Atmosfer modeli solid_rocket_engine ile aynı ISA_LAYERS tablosunu kullanır.

        Yoğunluk-bazlı tutarlılık: aynı katman tablosu -> aynı T/P profili.
        """
        from hrma.constants import ISA_LAYERS, M_AIR, R_STAR_ICAO
        # Bağımsız hesap (solid_rocket_engine.calculate_altitude_performance ile aynı mantık)
        for alt in (5000, 15000, 25000, 45000):
            H = alt * 6356766 / (6356766 + alt)
            layer = ISA_LAYERS[0]
            for c in ISA_LAYERS:
                if H >= c[0]:
                    layer = c
                else:
                    break
            h_b, T_b, lapse, P_b = layer
            g0 = 9.80665
            if lapse == 0.0:
                T = T_b
                P = P_b * np.exp(-g0 * M_AIR * (H - h_b) / (R_STAR_ICAO * T_b))
            else:
                T = T_b + lapse * (H - h_b)
                P = P_b * (T / T_b) ** (-g0 * M_AIR / (R_STAR_ICAO * lapse))
            # Modülün T/P'si ile karşılaştır
            rho_mod, P_mod, T_mod, _ = self.ta._atm_full(alt)
            assert P_mod == pytest.approx(P, rel=1e-6), f"{alt} m: P tutarsız"
            assert T_mod == pytest.approx(T, rel=1e-6), f"{alt} m: T tutarsız"


# ---------------------------------------------------------------------------
# 6) BİLİNEN REFERANS VAKA: H-class HPR roketi (bağımsız integrator ile)
# ---------------------------------------------------------------------------
class TestKnownReferenceCase:

    def test_h_class_apogee_matches_independent_integrator(self):
        """H-class HPR roketi: HRMA modülü bağımsız RK4 integratörüyle %3 içinde.

        Vaka: H148-sınıfı motor, 1.4 kg kuru kütle, 54 mm çap, Cd0=0.45.
        Beklenen apogee bandı: ~400-900 m (OpenRocket-sınıfı HPR sim).
        """
        thrust, burn, mprop, mdry, dia, cd0 = 148.0, 1.45, 0.090, 1.4, 0.054, 0.45

        # Bağımsız referans integrator (sabit adımlı, dikey)
        def ref_apogee():
            A = np.pi * (dia / 2) ** 2
            R = 287.053; gam = 1.4; R_e = 6371000
            def rho_T(z):
                if z <= 11000:
                    T = 288.15 - 0.0065 * z
                    P = 101325 * (T / 288.15) ** (G * 0.0289644 / (8.31432 * 0.0065))
                else:
                    T = 216.65
                    P = 22632.1 * np.exp(-G * 0.0289644 * (z - 11000) / (8.31432 * T))
                return P / (R * T), T
            def cd_mach(M):
                if M < 0.8: return cd0
                if M < 1.05: return cd0 * (1 + (M - 0.8) / 0.25 * 0.5)
                if M < 1.2: return cd0 * (1.5 + (M - 1.05) / 0.15 * (1.3 - 1.5))
                return cd0 * (1.05 + (1.3 - 1.05) * np.exp(-(M - 1.2) / 2.0))
            z = 0.0; vz = 0.0; m = mdry + mprop; t = 0.0; dt = 0.001
            mdot = mprop / burn; apogee = 0.0
            while vz >= 0 or t < burn:
                rho, T = rho_T(max(z, 0)); a = np.sqrt(gam * R * T); M = abs(vz) / a
                cd = cd_mach(M)
                Th = thrust if t < burn else 0.0
                gz = G * (R_e / (R_e + max(z, 0))) ** 2
                drag = 0.5 * rho * vz * abs(vz) * cd * A
                az = (Th - drag) / m - gz
                vz += az * dt; z += vz * dt
                if t < burn: m -= mdot * dt
                t += dt
                apogee = max(apogee, z)
                if t > 200: break
            return apogee

        ref = ref_apogee()
        r = _run(launch_angle=90.0, mass_dry=mdry, diameter=dia, cd0=cd0,
                 motor=_make_motor(thrust=thrust, burn=burn, mprop=mprop))
        sim = r['performance']['trajectory_metrics']['max_altitude']

        # Beklenen band kontrolü
        assert 400.0 < sim < 1000.0, f"H-class apogee bandı dışı: {sim:.1f} m"
        # Bağımsız integrator ile uyum (%3)
        rel_err = abs(sim - ref) / ref
        assert rel_err < 0.03, (
            f"HRMA apogee bağımsız ref ile %3 içinde olmalı: "
            f"sim={sim:.1f}, ref={ref:.1f}, err={rel_err*100:.2f}%"
        )


# ---------------------------------------------------------------------------
# 7) API KORUNUMU: dönen sözlük anahtarları ve imzalar değişmedi
# ---------------------------------------------------------------------------
class TestAPIPreservation:

    def test_return_dict_structure_preserved(self):
        """calculate_trajectory dönen sözlüğün üst seviye anahtarları korundu."""
        r = _run()
        for key in ('trajectory', 'performance', 'motor_data', 'vehicle_parameters'):
            assert key in r, f"üst seviye anahtar eksik: {key}"
        traj = r['trajectory']
        for key in ('time', 'position_x', 'position_z', 'altitude',
                    'velocity_x', 'velocity_z', 'velocity_magnitude',
                    'acceleration', 'phases'):
            assert key in traj, f"trajectory anahtarı eksik: {key}"
        perf = r['performance']
        for key in ('trajectory_metrics', 'motor_performance', 'phase_breakdown'):
            assert key in perf, f"performance anahtarı eksik: {key}"
        for key in ('max_altitude', 'max_velocity', 'max_acceleration',
                    'max_g_force', 'total_flight_time', 'range_distance',
                    'landing_velocity'):
            assert key in perf['trajectory_metrics'], f"trajectory_metrics anahtarı eksik: {key}"

    def test_plot_generation_still_works(self):
        """create_trajectory_plots hâlâ JSON üretmeli (API korunumu)."""
        r = _run()
        out = TrajectoryAnalyzer().create_trajectory_plots(r)
        assert isinstance(out, str) and len(out) > 100


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
