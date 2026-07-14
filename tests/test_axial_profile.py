"""
Eksenel ısı profili testleri (Dalga 2, 2026-07-14).

Kapsam:
  1. HeatTransferAnalyzer.analyze_axial_profile fizik kuralları:
     - tüm diziler eşit uzunlukta ve n_stations'a uyar,
     - alan oranı A/A_t >= 1, minimumu (=1) tam boğaz istasyonunda,
     - Mach monotonik artar; boğazda 1, öncesi subsonik, sonrası süpersonik,
     - her istasyon izantropik alan-Mach bağıntısını sağlar (rezidü kontrolü),
     - q ve h_g maksimumu boğazda (Bartz (A_t/A)^0.9 alan terimi),
     - kurtarma sıcaklığı Tc'yi aşmaz; denge cidar T fiziksel bantta,
     - rejeneratif soğutma doğal soğutmadan daha soğuk cidar verir.
  2. POST /api/analysis/wall-profile endpoint'i (test_client — port YOK):
     200 + şema + dizi uzunlukları + boğaz fiziği + varsayılanlarla çalışma.
"""

import warnings

import numpy as np
import pytest

warnings.filterwarnings('ignore')

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer

# Gerçekçi hibrit motor girdisi (N2O/HTPB sınıfı): 30 bar, 3200 K,
# d_t=30 mm, d_e=90 mm (eps=9). Testler boyunca TEK ortak girdi.
MOTOR_DATA = {
    'chamber_pressure': 30.0,       # bar
    'chamber_temperature': 3200.0,  # K
    'gamma': 1.22,
    'molecular_weight': 26.0,       # g/mol
    'mdot_total': 2.0,              # kg/s
    'chamber_diameter': 0.10,       # m
    'chamber_length': 0.40,         # m
    'burn_time': 8.0,               # s
    'throat_diameter': 0.03,        # m
    'exit_diameter': 0.09,          # m
}

N_STATIONS = 40

PROFILE_ARRAY_KEYS = ('x_mm', 'area_ratio', 'mach', 'h_g', 'q_MW',
                      'T_wall_eq', 'T_recovery')


@pytest.fixture(scope='module')
def analyzer():
    return HeatTransferAnalyzer()


@pytest.fixture(scope='module')
def profile(analyzer):
    return analyzer.analyze_axial_profile(MOTOR_DATA, n_stations=N_STATIONS)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestProfileSchema:
    def test_all_arrays_same_length(self, profile):
        lengths = {key: len(profile[key]) for key in PROFILE_ARRAY_KEYS}
        assert len(set(lengths.values())) == 1, f"uzunluklar eşit değil: {lengths}"
        assert lengths['x_mm'] == N_STATIONS

    def test_required_scalar_meta(self, profile):
        assert profile['x_throat_mm'] > 0
        assert profile['x_exit_mm'] > profile['x_throat_mm']
        assert 0 < profile['throat_index'] < N_STATIONS - 1

    def test_n_stations_respected(self, analyzer):
        p = analyzer.analyze_axial_profile(MOTOR_DATA, n_stations=25)
        assert len(p['x_mm']) == 25
        assert len(p['q_MW']) == 25

    def test_x_monotonic_increasing(self, profile):
        x = np.asarray(profile['x_mm'])
        assert np.all(np.diff(x) > 0)
        assert x[0] == pytest.approx(0.0)
        assert x[-1] == pytest.approx(profile['x_exit_mm'])

    def test_all_values_finite(self, profile):
        for key in PROFILE_ARRAY_KEYS:
            arr = np.asarray(profile[key], dtype=float)
            assert np.all(np.isfinite(arr)), f"{key} sonlu olmayan değer içeriyor"


class TestProfilePhysics:
    def test_area_ratio_min_one_at_throat(self, profile):
        eps = np.asarray(profile['area_ratio'])
        ti = profile['throat_index']
        assert np.all(eps >= 1.0)
        assert eps[ti] == pytest.approx(1.0)
        assert int(np.argmin(eps)) == ti

    def test_exit_area_ratio_matches_geometry(self, profile):
        # eps_exit = (d_e/d_t)^2 = 9
        expected = (MOTOR_DATA['exit_diameter'] / MOTOR_DATA['throat_diameter']) ** 2
        assert profile['area_ratio'][-1] == pytest.approx(expected, rel=1e-6)

    def test_mach_unity_at_throat(self, profile):
        ti = profile['throat_index']
        assert profile['mach'][ti] == pytest.approx(1.0, abs=1e-6)

    def test_mach_branches(self, profile):
        mach = np.asarray(profile['mach'])
        ti = profile['throat_index']
        assert np.all(mach[:ti] < 1.0), "konverjan subsonik olmalı"
        assert np.all(mach[ti + 1:] > 1.0), "diverjan süpersonik olmalı"

    def test_mach_monotonic_nondecreasing(self, profile):
        mach = np.asarray(profile['mach'])
        assert np.all(np.diff(mach) >= -1e-9)

    def test_isentropic_area_mach_residual(self, profile):
        # Her istasyon A/A* bağıntısını sağlamalı (çözücü tutarlılığı).
        gamma = MOTOR_DATA['gamma']
        eps = np.asarray(profile['area_ratio'])
        mach = np.asarray(profile['mach'])
        exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))
        eps_from_mach = (1.0 / mach) * (
            (2.0 / (gamma + 1.0)) * (1.0 + (gamma - 1.0) / 2.0 * mach ** 2)
        ) ** exponent
        assert np.allclose(eps_from_mach, eps, rtol=1e-6)

    def test_heat_flux_peaks_at_throat(self, profile):
        q = np.asarray(profile['q_MW'])
        ti = profile['throat_index']
        assert int(np.argmax(q)) == ti, "q maksimumu boğazda olmalı"
        assert np.all(q > 0)

    def test_bartz_coefficient_peaks_at_throat(self, profile):
        h = np.asarray(profile['h_g'])
        ti = profile['throat_index']
        assert int(np.argmax(h)) == ti
        assert np.all(h > 0)
        # Boğaz katsayısı hazne çıkışındakinden belirgin büyük olmalı
        # (Bartz alan terimi (A_t/A)^0.9)
        assert h[ti] > 2.0 * h[0]

    def test_recovery_temperature_physical(self, profile):
        taw = np.asarray(profile['T_recovery'])
        tc = MOTOR_DATA['chamber_temperature']
        assert np.all(taw <= tc + 1e-6), "kurtarma sıcaklığı Tc'yi aşamaz"
        assert np.all(taw > 0.8 * tc), "kurtarma sıcaklığı Tc mertebesinde kalmalı"
        # M arttıkça Taw düşer (r < 1): çıkışta boğazdan düşük olmalı
        assert taw[-1] < taw[profile['throat_index']]

    def test_equilibrium_wall_temperature_band(self, profile):
        tw = np.asarray(profile['T_wall_eq'])
        taw = np.asarray(profile['T_recovery'])
        assert np.all(tw >= 293.15 - 1e-6)
        assert np.all(tw <= taw + 1e-6), "denge cidar T kurtarma T'yi aşamaz"

    def test_regenerative_cooling_cools_wall(self, analyzer):
        p_nat = analyzer.analyze_axial_profile(
            MOTOR_DATA, n_stations=N_STATIONS, cooling_type='natural')
        p_reg = analyzer.analyze_axial_profile(
            MOTOR_DATA, n_stations=N_STATIONS, cooling_type='regenerative')
        ti = p_nat['throat_index']
        assert p_reg['T_wall_eq'][ti] < p_nat['T_wall_eq'][ti], (
            "rejeneratif soğutma boğaz cidarını doğal soğutmadan soğuk tutmalı")

    def test_throat_hg_consistent_with_throat_analysis(self, analyzer, profile):
        # Boğaz istasyonu Bartz katsayısı, throat-analizinin gaz-yanı
        # katsayısıyla aynı mertebede olmalı (aynı korelasyon; yalnız sigma
        # için kullanılan referans cidar sıcaklığı farkı kadar sapabilir).
        full = analyzer.analyze_heat_transfer(MOTOR_DATA)
        h_throat_full = full['heat_transfer_coefficients']['gas_side']
        h_throat_profile = profile['h_g'][profile['throat_index']]
        assert h_throat_profile == pytest.approx(h_throat_full, rel=0.25)


class TestWallProfileEndpoint:
    # Termal panel formuyla aynı çekirdek alanlar (/analyze_thermal_safety)
    PAYLOAD = {
        'chamber_pressure': 30.0,
        'chamber_temperature': 3200.0,
        'chamber_diameter': 0.10,
        'chamber_length': 0.40,
        'burn_time': 8.0,
        'mdot_total': 2.0,
        'material': 'steel_4130',
        'wall_thickness': 0.006,
        'cooling_type': 'natural',
        # panel currentResults'tan tamamlar:
        'throat_diameter': 0.03,
        'exit_diameter': 0.09,
        'gamma': 1.22,
        'molecular_weight': 26.0,
        'n_stations': 40,
    }

    def test_endpoint_returns_200_with_schema(self, client):
        r = client.post('/api/analysis/wall-profile', json=self.PAYLOAD)
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'success'
        profile = j['wall_profile']
        for key in ('x_mm', 'area_ratio', 'mach', 'h_g', 'q_MW', 'T_wall_eq'):
            assert key in profile, f"şemada eksik anahtar: {key}"
            assert isinstance(profile[key], list)
        lengths = {len(profile[k]) for k in
                   ('x_mm', 'area_ratio', 'mach', 'h_g', 'q_MW', 'T_wall_eq')}
        assert lengths == {40}

    def test_endpoint_physics_throat_peak(self, client):
        r = client.post('/api/analysis/wall-profile', json=self.PAYLOAD)
        profile = r.get_json()['wall_profile']
        q = profile['q_MW']
        ti = profile['throat_index']
        assert int(np.argmax(np.asarray(q))) == ti
        assert profile['mach'][ti] == pytest.approx(1.0, abs=1e-6)
        # Boğaz konumu işaretçisi frontend için mm cinsinden gelir
        assert profile['x_mm'][ti] == pytest.approx(profile['x_throat_mm'])

    def test_endpoint_defaults_when_minimal_payload(self, client):
        # Yalnız çekirdek alanlar — geometri backend varsayılanlarından çözülür
        r = client.post('/api/analysis/wall-profile', json={
            'chamber_pressure': 25.0,
            'chamber_temperature': 3000.0,
            'mdot_total': 1.5,
        })
        assert r.status_code == 200
        profile = r.get_json()['wall_profile']
        assert len(profile['x_mm']) == 40  # varsayılan n_stations
        assert min(profile['area_ratio']) == pytest.approx(1.0)

    def test_endpoint_respects_n_stations(self, client):
        payload = dict(self.PAYLOAD, n_stations=60)
        r = client.post('/api/analysis/wall-profile', json=payload)
        assert r.status_code == 200
        assert len(r.get_json()['wall_profile']['x_mm']) == 60

    def test_endpoint_no_plot_keys(self, client):
        # Sözleşme: endpoint grafik ÇİZMEZ — Plotly/plot anahtarı dönmez.
        r = client.post('/api/analysis/wall-profile', json=self.PAYLOAD)
        j = r.get_json()
        assert 'plot' not in j and 'plot_json' not in j
        assert 'plot' not in j['wall_profile']
