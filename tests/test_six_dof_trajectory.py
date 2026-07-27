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
        """80° yükseliş, 90° azimut (doğuya) — (E,N,U) çerçevesinde.

        v2.6.25 DÜZELTMESİ — TESTİN BİLEŞEN SIRASI YANLIŞTI, KOD DOĞRUYDU.
        Beklenen vektör eskiden (N,E,U) sırasına göre yazılmıştı: doğu
        bileşeni indis 1'de aranıyordu. v2.6.2'nin F167 refaktörü çerçeveyi
        sağ-elli (E,N,U) yaptı ve ``_quat_from_elevation_azimuth`` bunu
        docstring'inde açıkça ilan ediyor (doğu = cosθ·sin(az),
        kuzey = cosθ·cos(az)).

        El hesabı (yükseliş 80°, azimut 90°, azimut kuzeyden saat yönünde):
            Doğu   = cos(80°)·sin(90°) = cos(80°)  = 0.173648
            Kuzey  = cos(80°)·cos(90°) = 0
            Yukarı = sin(80°)                      = 0.984808
        Azimut 90° tanımı gereği tam doğu olduğundan kuzey bileşeni sıfırdır;
        eski beklenti doğu değerini kuzey yuvasına koyuyordu.
        """
        q = _quat_from_elevation_azimuth(80.0, 90.0)
        x_body = _quat_to_dcm(q)[:, 0]
        expected = [np.cos(np.radians(80)) * 1.0,   # doğu
                    np.cos(np.radians(80)) * 0.0,   # kuzey
                    np.sin(np.radians(80))]         # yukarı
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
                launch_elevation_deg=90.0,
                # Coriolis izotropiyi KIRAR (doğu sürüklenmesi rüzgâr yönünden
                # bağımsız eklenir) → bu test yalnız q̇ Hamilton-sırası aero
                # izotropisini denetler, o yüzden Coriolis'siz koşulur.
                coriolis=False)
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


class TestMassProperties:
    """Kütle & denge katmanı (UI 'Mass & Balance' bileşen tablosunun karşılığı).

    CG konumu statik marjı gerçekten sürmeli; bileşen listesi verildiğinde
    pitch/yaw ataleti nokta-kütle toplamından kurulmalı; liste verilmediğinde
    eski tekdüze model birebir korunmalı.
    """

    def test_cg_shift_changes_static_margin(self):
        """x_cg_full/empty gerçekten kullanılıyor: CG öne alınırsa marj artar.

        Bileşen tablosu (UI Component modu) bu anahtarları gönderir; sessizce
        yok sayılırsa marj CG'den bağımsız kalırdı.
        """
        aero = _standard_rocket()
        base = SixDOFTrajectory(
            aero=aero, dry_mass=8.0, propellant_mass=4.0,
            thrust=1200.0, burn_time=6.0,
            x_cg_full=1.20, x_cg_empty=1.10)
        fwd = SixDOFTrajectory(
            aero=aero, dry_mass=8.0, propellant_mass=4.0,
            thrust=1200.0, burn_time=6.0,
            x_cg_full=0.90, x_cg_empty=0.85)   # CG buruna yakın
        # Marj = (x_cp − x_cg)/d — CG 0.30 m öne gidince 3 kalibre artmalı
        assert aero.static_margin(0.90) - aero.static_margin(1.20) == \
            pytest.approx(0.30 / aero.d, rel=1e-12)
        assert fwd.aero.static_margin(fwd.x_cg_full) > \
            base.aero.static_margin(base.x_cg_full)
        # Fallback (0.55·L / 0.50·L) devre dışı: verilen değerler korunmalı
        assert base.x_cg_full == pytest.approx(1.20)
        assert base.x_cg_empty == pytest.approx(1.10)

    def test_component_inertia_differs_from_uniform(self):
        """components verilince pitch ataleti bileşen toplamından kurulur."""
        aero = _standard_rocket()
        comps = [
            {'mass': 0.5, 'x': 0.20, 'propellant': False},   # burun
            {'mass': 3.0, 'x': 1.20, 'propellant': False},   # gövde
            {'mass': 0.5, 'x': 1.90, 'propellant': False},   # kanatlar
            {'mass': 4.0, 'x': 1.70, 'propellant': False},   # motor (kuru)
            {'mass': 4.0, 'x': 1.55, 'propellant': True},    # yakıt
        ]
        m_all = sum(c['mass'] for c in comps)
        x_cg_full = sum(c['mass'] * c['x'] for c in comps) / m_all
        dry = [c for c in comps if not c['propellant']]
        x_cg_empty = sum(c['mass'] * c['x'] for c in dry) / \
            sum(c['mass'] for c in dry)

        uniform = SixDOFTrajectory(
            aero=aero, dry_mass=8.0, propellant_mass=4.0,
            thrust=1200.0, burn_time=6.0,
            x_cg_full=x_cg_full, x_cg_empty=x_cg_empty)
        lumped = SixDOFTrajectory(
            aero=aero, dry_mass=8.0, propellant_mass=4.0,
            thrust=1200.0, burn_time=6.0,
            x_cg_full=x_cg_full, x_cg_empty=x_cg_empty, components=comps)

        m0 = lumped._mass_at(0.0)
        _, I_uniform = uniform._inertia(m0, x_cg_full)
        I_x_c, I_comp = lumped._inertia(m0, x_cg_full)
        assert I_comp > 0.0 and I_x_c > 0.0
        assert I_comp != pytest.approx(I_uniform, rel=1e-9)

        # El hesabı: Σ m_i (x_i − x_cg)² + m(3r²)/12
        r = aero.d / 2.0
        expected = m0 * (3.0 * r * r) / 12.0 + \
            sum(c['mass'] * (c['x'] - x_cg_full) ** 2 for c in comps)
        assert I_comp == pytest.approx(expected, rel=1e-12)
        # Roll ataleti bileşen modelinden etkilenmez
        assert I_x_c == pytest.approx(0.5 * m0 * r * r, rel=1e-12)

        # Uçuş çözülebilmeli ve kararlı kalmalı
        res = lumped.solve(t_max=200.0)
        assert res['apogee'] > 1000.0
        assert res['static_margin_full'] > 1.0

    def test_components_none_matches_legacy(self):
        """components=None → eski tekdüze model birebir (geriye dönük uyum)."""
        aero = _standard_rocket()
        kw = dict(dry_mass=8.0, propellant_mass=4.0, thrust=1200.0,
                  burn_time=6.0, cd0=0.45, wind_speed=4.0,
                  wind_direction_deg=30.0, launch_elevation_deg=89.0)
        legacy = SixDOFTrajectory(aero=aero, **kw)
        explicit = SixDOFTrajectory(aero=aero, components=None, **kw)

        m = 10.0
        r = aero.d / 2.0
        assert legacy._inertia(m) == explicit._inertia(m)
        assert legacy._inertia(m)[1] == pytest.approx(
            m * (3.0 * r * r + aero.L ** 2) / 12.0, rel=1e-12)

        a = legacy.solve(t_max=200.0)
        b = explicit.solve(t_max=200.0)
        assert a['apogee'] == pytest.approx(b['apogee'], rel=1e-12)
        assert a['max_alpha_deg'] == pytest.approx(b['max_alpha_deg'], rel=1e-12)
        assert a['static_margin_full'] == pytest.approx(
            b['static_margin_full'], rel=1e-12)

    def test_empty_component_list_falls_back_to_uniform(self):
        """Boş / geçersiz bileşen listesi tekdüze modele düşmeli."""
        aero = _standard_rocket()
        solver = SixDOFTrajectory(
            aero=aero, dry_mass=8.0, propellant_mass=4.0,
            thrust=1200.0, burn_time=6.0,
            components=[{'mass': 0.0, 'x': 1.0},
                        {'mass': -2.0, 'x': 0.5}])
        assert solver.components is None
        m, r = 10.0, aero.d / 2.0
        assert solver._inertia(m)[1] == pytest.approx(
            m * (3.0 * r * r + aero.L ** 2) / 12.0, rel=1e-12)


# ---------------------------------------------------------------------------
# F061 — pitch/yaw sönüm katsayısı C_mq
# ---------------------------------------------------------------------------
class TestPitchDamping:
    """v2.6.2 fizik denetimi bulgusu F061 kilidi.

    Eski kod ``c_mq = −C_Nα·(arm/d)²`` kullanıyordu; doğru türev
    ``C_mq = −2·C_Nα·(arm/d)²``. Türetme: q pitch hızı CP'de Δα = q·l/V
    indükler → M = −q̄·S·C_Nα·l²·q/V; M = q̄·S·d·C_mq·(q·d/2V) ile
    eşitlenince 2 çarpanı çıkar. ÖLÇÜLDÜ: kod/analitik oranı tam 0.5000
    (α=0, q=1 rad/s, V=250 m/s, h=1000 m).
    """

    @staticmethod
    def _pitch_moment(q_rate, V=250.0, h=1000.0, t=7.0):
        """_derivatives'in uyguladığı pitch momentini w_dot'tan geri çıkarır."""
        solver = SixDOFTrajectory(
            aero=_standard_rocket(), dry_mass=8.0, propellant_mass=4.0,
            thrust=1200.0, burn_time=6.0, cd0=0.45,
            wind_speed=0.0, launch_elevation_deg=90.0, coriolis=False)
        solver._r0 = np.zeros(3)
        q = _quat_from_elevation_azimuth(90.0, 0.0)
        # Dik atış, hız tamamen +z → gövde ekseniyle hizalı, α = 0
        y = np.concatenate([[0.0, 0.0, h], [0.0, 0.0, V], q,
                            [0.0, q_rate, 0.0]])
        m = solver._mass_at(t)
        x_cg = solver._cg_at(t)
        I = np.array(solver._inertia(m, x_cg))[[0, 1, 1]]
        w_b = y[10:13]
        w_dot = solver._derivatives(t, y)[10:13]
        M_b = w_dot * I + np.cross(w_b, I * w_b)
        return float(M_b[1]), solver, x_cg, m

    def test_matches_analytic_damping_moment(self):
        """Uygulanan sönüm momenti analitik −q̄·S·C_Nα·l²·q/V ile birebir."""
        from hrma.analysis.six_dof_trajectory import _atmosphere
        V, h, q_rate = 250.0, 1000.0, 1.0
        M_code, solver, x_cg, _ = self._pitch_moment(q_rate, V=V, h=h)
        aero = solver.aero
        rho, _ = _atmosphere(h + solver.launch_altitude)
        arm = aero.x_cp - x_cg
        M_analytic = -(0.5 * rho * V ** 2) * aero.S_ref * \
            aero.cn_alpha * arm ** 2 * q_rate / V
        assert M_code == pytest.approx(M_analytic, rel=1e-12)
        # Eski (yarım) katsayı artık kabul edilmiyor
        assert M_code != pytest.approx(0.5 * M_analytic, rel=1e-6)

    def test_damping_opposes_rotation(self):
        """Sönüm momenti dönüş yönüne KARŞI ve hıza doğrusal."""
        M_pos, _, _, _ = self._pitch_moment(1.0)
        M_neg, _, _, _ = self._pitch_moment(-1.0)
        M_double, _, _, _ = self._pitch_moment(2.0)
        assert M_pos < 0.0 < M_neg
        assert M_neg == pytest.approx(-M_pos, rel=1e-12)
        assert M_double == pytest.approx(2.0 * M_pos, rel=1e-12)

    def test_zero_rate_gives_zero_damping(self):
        """q=0 → sönüm momenti sıfır (α=0'da toplam pitch momenti de sıfır)."""
        M_zero, _, _, _ = self._pitch_moment(0.0)
        assert M_zero == pytest.approx(0.0, abs=1e-12)
