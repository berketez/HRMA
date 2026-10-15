"""
Uç nokta bekçileri + Dalga 0 API onarımları testleri (2026-07-14).

Kapsam (test_client ile — sunucuya port BAĞLANMAZ):
  1. /api/kinetic-analysis, /api/cfd-analysis, /api/professional-analysis
     -> 501 'unavailable' bekçisi (kinetik çağrısı tek-worker masaüstünde
     uygulamayı saatlerce kilitleyebiliyordu; CFD çözücüsü ıraksıyordu).
  2. /api/advanced-analysis 'heat_transfer' tipi GERÇEK motor verisiyle 200
     döner (eski kod var olmayan analyze_chamber_thermal'ı çağırıp 500
     veriyordu); girdisiz istekte ise fail-closed olmalıdır — ÖH Faz B / B3
     ile taşınan bekçi (defter P13B2-02, P4B1-01) bugün xfail(strict) borç
     imiyle duruyor.
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

#: ``/api/advanced-analysis``'in ``heat_transfer`` dalının ürün tarafında
#: VARSAYILANLA doldurduğu girdiler (``hrma/app.py:4730-4735``). Liste testin
#: kendi ölçümüdür — ürün sabitini ithal ETMEZ, çünkü sınanan şey tam da
#: ürünün bu alanları uydurma hakkıdır.
ADVANCED_HEAT_INPUTS = (
    'chamber_pressure', 'chamber_temperature', 'chamber_diameter',
    'chamber_length', 'burn_time', 'mdot_total',
)


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
        """SAĞLIKLI YOL — gövde ÖH D16 / OH-Z3-02 ile GÜNCELLENDİ.

        Eski gövde ``wall_thickness`` GÖNDERMİYORDU ve 200 bekliyordu; uç
        o alanı ``data.get('wall_thickness', 0.005)`` ile UYDURUYORDU
        (ölçüldü, ``docs/scofield/raw/OH/D16/yapisal-sistem/a1/once.json``
        K8: cidar gönderilen ve gönderilmeyen gövde BİREBİR aynı yanıtı
        veriyor, ``design_parameters.wall_thickness = 5.0`` mm). Kardeş uç
        ``/analyze_thermal_safety`` aynı gövdeyi zaten 422 ile reddediyordu.
        Bu iddia, güncellenmeseydi, F4-1 varsayılanını ŞART KOŞAN bir bekçi
        olurdu — hemen altındaki ``test_empty_motor_data_is_rejected_
        fail_closed``ın kaldırdığı kilidin aynısı. İddianın KENDİSİ
        (sağlıklı gövde -> 200 + gerçek analiz sözleşmesi) korunur; yalnız
        cidar artık AÇIKÇA gönderilir.
        """
        r = client.post('/api/advanced-analysis', json={
            'motor_data': {
                'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
                'chamber_diameter': 0.1, 'chamber_length': 0.5,
                'burn_time': 10.0, 'mdot_total': 1.0,
            },
            'analysis_types': ['heat_transfer'],
            'material_type': 'steel_4130',
            'wall_thickness': 0.005,
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

    # Z3 onarımı (2026-08-27): boş motor_data 422 + missing_fields; sağlıklı
    # yol bit-aynı (14.661.635,924841596 çapası korunuyor) — im düştü.
    @pytest.mark.parametrize('body', [
        {'motor_data': {}, 'analysis_types': ['heat_transfer']},
        {'analysis_types': ['heat_transfer']},
    ], ids=['bos_motor_data', 'motor_data_anahtari_yok'])
    def test_empty_motor_data_is_rejected_fail_closed(self, client, body):
        """Girdisiz ısı transferi analizi ÜRETİLMEZ (fail-closed).

        **Bu bekçi TAŞINDI (ÖH Faz B, adım B3 — Tip-T).**

        Eski hâli ``test_heat_transfer_with_empty_motor_data_uses_defaults``
        idi ve gövdesinin TAMAMI iki iddiaydı::

            assert r.status_code == 200
            assert r.get_json()['status'] == 'success'

        Yani boş ``motor_data`` ile ÇALIŞMAYI ŞART KOŞUYORDU. Bugün ölçülen
        (27 Ağu 2026, HEAD 344714d) davranış:

        =========================  ====  ==============================
        gövde                      HTTP  ``heat_flux`` [W/m²]
        =========================  ====  ==============================
        ``motor_data: {}``         200   **13 027 380,540100738**
        ``motor_data`` yok         200   **13 027 380,540100738**
        gerçek motor (Tc 3200 K)   200   14 661 635,924841596
        =========================  ====  ==============================

        Uydurulan sayı ``app.py:4730-4735``'in varsayılanlarından doğuyor
        (Pc 20 bar, Tc 3000 K, Ø 0,1 m, L 0,5 m, t_b 10 s, ṁ 1,0 kg/s) ve
        ``heat_analysis`` içinde bunu bildiren TEK BİR beyan alanı yok
        (ölçüldü: ``default``/``declared``/``assumed`` içeren anahtar 0).
        ``risk_level`` yine ``HIGH`` basılıyor: kullanıcının vermediği bir
        motor için güvenlik hükmü.

        Savcı ölçümü (P13 §2.4-c) rotanın ürün tüketicisinin **0** olduğunu
        gösterdi — yani bu rotanın davranışını tanımlayan tek merci test
        süiti. Eski iddia o merciyi fail-open'ı ŞART KOŞACAK biçimde
        kullanıyordu; kusuru kilitleyen bekçi olduğu için SİLİNDİ.

        Beklenen davranış deponun kendi sağlıklı deseni: ``/calculate_solid``
        (``app.py:3701-3722``) ve ``/api/thermal-protection`` eksik girdide
        4xx + ``missing_fields`` ile eksik alanı ADIYLA söylüyor.

        Defter: P13B2-02 (yüksek) · P4B1-01 (kritik) kardeş ucu.
        """
        r = client.post('/api/advanced-analysis', json=body)

        assert 400 <= r.status_code < 500, (
            'girdisiz istek reddedilmeli; alınan HTTP '
            f'{r.status_code}, gövde {r.get_data(as_text=True)[:200]}')
        j = r.get_json()
        assert j.get('status') != 'success'
        assert j.get('error'), 'ret makine-okur bir "error" kodu taşımalı'

        missing = j.get('missing_fields')
        assert missing, ('eksik girdiler ADIYLA bildirilmeli '
                         '(/calculate_solid deseni)')
        assert all(isinstance(ad, str) for ad in missing)
        assert set(missing) & (set(ADVANCED_HEAT_INPUTS) | {'motor_data'}), (
            f'bildirilen eksik alanlar ürünün girdi adlarından olmalı: '
            f'{missing}')

        # Reddedilen istekten hüküm de grafik de çıkmaz.
        results = j.get('results') or {}
        assert 'heat_analysis' not in results
        assert 'heat_transfer_plot' not in results


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
