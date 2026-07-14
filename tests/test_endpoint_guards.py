"""
Uç nokta bekçileri + Dalga 0 API onarımları testleri (2026-07-14).

Kapsam (test_client ile — sunucuya port BAĞLANMAZ):
  1. /api/kinetic-analysis, /api/cfd-analysis, /api/professional-analysis
     -> 501 'unavailable' bekçisi (kinetik çağrısı tek-worker masaüstünde
     uygulamayı saatlerce kilitleyebiliyordu; CFD çözücüsü ıraksıyordu).
  2. /api/advanced-analysis 'heat_transfer' tipi artık 200 döner
     (eski kod var olmayan analyze_chamber_thermal'ı çağırıp 500 veriyordu).
  3. /calculate yanıtı: motor.gamma + motor.molecular_weight üst seviyede;
     render edilmeyen plots.heat_transfer / plots.structural_analysis
     anahtarları YOK; motor içi heat/structural sonuçları KORUNUR
     (3D ısı haritası motor.heat_transfer_analysis'e bağlı).
  4. /analyze_safety malzeme parametresi merkezi materials_db'den okunur.
"""

import warnings

import pytest

warnings.filterwarnings('ignore')

GUARDED_ENDPOINTS = [
    '/api/kinetic-analysis',
    '/api/cfd-analysis',
    '/api/professional-analysis',
]


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestGuards501:
    @pytest.mark.parametrize('endpoint', GUARDED_ENDPOINTS)
    def test_returns_501_unavailable(self, client, endpoint):
        r = client.post(endpoint, json={})
        assert r.status_code == 501, f"{endpoint} must return 501"
        j = r.get_json()
        assert j['status'] == 'unavailable'
        assert 'rebuilt' in j['error']

    @pytest.mark.parametrize('endpoint', GUARDED_ENDPOINTS)
    def test_guard_fires_before_heavy_work(self, client, endpoint):
        """Bekçi, gövde ne olursa olsun ağır çözücüye girmeden dönmeli."""
        r = client.post(endpoint, json={
            'chamber_pressure': 2e6, 'chamber_temperature': 3000,
            'motor_type': 'hybrid'})
        assert r.status_code == 501


class TestAdvancedAnalysisHeatTransfer:
    def test_heat_transfer_type_returns_200(self, client):
        r = client.post('/api/advanced-analysis', json={
            'motor_data': {
                'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
                'chamber_diameter': 0.1, 'chamber_length': 0.5,
                'burn_time': 10.0, 'mdot_total': 1.0,
            },
            'analysis_types': ['heat_transfer'],
            'material_type': 'steel_4130',
        })
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'success'
        results = j['results']
        assert 'heat_analysis' in results
        assert 'heat_transfer_plot' in results
        # Gerçek analiz sözleşmesi (analyze_heat_transfer çıktısı)
        ha = results['heat_analysis']
        for key in ('heat_transfer_coefficients', 'gas_side_analysis',
                    'wall_analysis', 'safety_analysis'):
            assert key in ha, f"heat_analysis missing {key}"
        assert ha['heat_transfer_coefficients']['gas_side'] > 0

    def test_heat_transfer_with_empty_motor_data_uses_defaults(self, client):
        r = client.post('/api/advanced-analysis', json={
            'motor_data': {}, 'analysis_types': ['heat_transfer']})
        assert r.status_code == 200
        assert r.get_json()['status'] == 'success'


class TestCalculateResponseShape:
    @pytest.fixture(scope='class')
    def calc_json(self, request):
        from hrma.app import app
        app.config['TESTING'] = True
        c = app.test_client()
        r = c.post('/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o',
            # Yanıt şekli testinde gereksiz ağır adımları kapat
            'calculate_trajectory': False, 'generate_cad': False,
            'include_3d_visualization': False,
            'include_realtime_dashboard': False,
        })
        assert r.status_code == 200
        return r.get_json()

    def test_gamma_and_molecular_weight_top_level(self, calc_json):
        motor = calc_json['motor']
        assert 'gamma' in motor and 'molecular_weight' in motor
        assert 1.05 < motor['gamma'] < 1.45
        assert 10.0 < motor['molecular_weight'] < 60.0

    def test_dead_plot_keys_removed(self, calc_json):
        """Render edilmeyen çifte hesap plot'ları yanıtta OLMAMALI."""
        plots = calc_json['plots']
        assert 'heat_transfer' not in plots
        assert 'structural_analysis' not in plots

    def test_motor_internal_analyses_preserved(self, calc_json):
        """3D ısı haritası ve paneller motor.* sonuçlarına bağlı — kalmalı."""
        motor = calc_json['motor']
        assert 'heat_transfer_analysis' in motor
        assert 'structural_analysis' in motor
        assert 'wall_analysis' in motor['heat_transfer_analysis']
        st = motor['structural_analysis']
        assert 'safety_factor_pressure' in st
        assert 'safety_factor_total' in st


class TestAnalyzeSafetyMaterial:
    def test_material_passed_and_reported(self, client):
        r = client.post('/analyze_safety', json={
            'chamber_pressure': 30, 'chamber_diameter': 0.12,
            'wall_thickness': 0.004, 'propellant_mass': 8,
            'material': 'aluminum_6061'})
        assert r.status_code == 200
        ss = r.get_json()['safety_analysis']['structural_safety']
        assert ss['material'] == 'aluminum_6061'
        assert ss['yield_strength_mpa'] == pytest.approx(275.0)

    def test_default_material_is_steel_4130(self, client):
        r = client.post('/analyze_safety', json={
            'chamber_pressure': 30, 'chamber_diameter': 0.12,
            'wall_thickness': 0.004, 'propellant_mass': 8})
        assert r.status_code == 200
        ss = r.get_json()['safety_analysis']['structural_safety']
        assert ss['material'] == 'steel_4130'
        assert ss['yield_strength_mpa'] == pytest.approx(460.0)

    def test_material_changes_safety_factor(self, client):
        payload = {'chamber_pressure': 30, 'chamber_diameter': 0.12,
                   'wall_thickness': 0.004, 'propellant_mass': 8}
        r1 = client.post('/analyze_safety',
                         json={**payload, 'material': 'steel_4130'})
        r2 = client.post('/analyze_safety',
                         json={**payload, 'material': 'aluminum_6061'})
        sf1 = r1.get_json()['safety_analysis']['structural_safety']['yield_safety_factor']
        sf2 = r2.get_json()['safety_analysis']['structural_safety']['yield_safety_factor']
        # Aynı gerilme, farklı akma dayanımı -> SF oranı dayanım oranına eşit
        assert sf1 / sf2 == pytest.approx(460.0 / 275.0, rel=1e-6)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
