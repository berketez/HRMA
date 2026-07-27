"""
Analiz Güvertesi (Analysis Dock) sözleşme testleri — BOL TEST dalgası (2026-07-14).

Kapsam (test_client ile — sunucuya port BAĞLANMAZ):
  1. Sayfa sözleşmesi: /, /hybrid, /solid, /liquid 200 döner; motor
     sayfalarında analysis_dock.js panellerden ÖNCE yüklenir ve
     #analysis-dock-anchor mevcuttur (analysis_dock.js başlık yorumundaki
     "entegrasyon sözleşmesi — DEĞİŞTİRME" bloğu).
  2. Panel yanıt sözleşmesi: /analyze_structural_safety,
     /analyze_thermal_safety, /analyze_safety gerçek payload'larla 200 döner
     ve panellerin render() içinde okuduğu anahtarlar yanıtta VARDIR
     (anahtar listeleri panels/*.js dosyalarından çıkarıldı — grep ile).
  3. 501 bekçileri: kinetic / cfd / professional-analysis dürüst 501 döner.
  4. /calculate: motor.gamma + motor.molecular_weight üst seviyede;
     ölü plots.heat_transfer / plots.structural_analysis anahtarları YOK;
     tam varsayılan hibrit akışı 30 sn altında tamamlanır.
  5. Uçtan uca duman: /calculate → structural panelin fromResults eşlemesi →
     /analyze_structural_safety → SF alanları sayısal ve tutarlı
     (SF_pressure >= SF_total; basınç-yalnız SF, termal içeren toplamdan
     küçük olamaz).

Panellerin okuduğu alan adları kaynakları:
  - panels/structural_panel.js  → structural_analysis.* anahtarları
  - panels/thermal_panel.js     → thermal_analysis.* anahtarları
  - panels/safety_panel.js      → safety_analysis.* anahtarları
"""

import math
import time
import warnings

import pytest

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Sabitler — panel varsayılanları panels/*.js `fields` listeleriyle birebir
# ---------------------------------------------------------------------------

MOTOR_PAGES = ['/hybrid', '/solid', '/liquid']
ALL_PAGES = ['/'] + MOTOR_PAGES

DOCK_SCRIPT = '/static/js/analysis_dock.js'
PANEL_SCRIPTS = [
    '/static/js/panels/structural_panel.js',
    '/static/js/panels/thermal_panel.js',
    '/static/js/panels/safety_panel.js',
]
HUD_SCRIPT = '/static/js/hud.js'
DOCK_ANCHOR_ID = 'analysis-dock-anchor'

GUARDED_501_ENDPOINTS = [
    '/api/kinetic-analysis',
    '/api/cfd-analysis',
    '/api/professional-analysis',
]

# structural_panel.js `fields` varsayılanları
STRUCTURAL_PAYLOAD = {
    'chamber_pressure': 40,      # bar
    'chamber_diameter': 0.1,     # m
    'chamber_length': 0.5,       # m
    'throat_diameter': 0.02,     # m
    'burn_time': 10,             # s
    'material': 'steel_4130',
}

# thermal_panel.js `fields` varsayılanları
THERMAL_PAYLOAD = {
    'chamber_pressure': 40,      # bar
    'chamber_temperature': 3000, # K
    'chamber_diameter': 0.1,     # m
    'chamber_length': 0.5,       # m
    'burn_time': 10,             # s
    'mdot_total': 1.0,           # kg/s
    'wall_thickness': 0.005,     # m
    'material': 'steel',
    'cooling_type': 'natural',
}

# safety_panel.js `fields` varsayılanları
SAFETY_PAYLOAD = {
    'motor_type': 'hybrid',
    'chamber_pressure': 40,      # bar
    'chamber_temperature': 3000, # K
    'thrust': 1000,              # N
    'burn_time': 10,             # s
    'propellant_mass': 5,        # kg
    'propellant_type': 'composite',
    'facility_type': 'test_stand',
    'chamber_diameter': 0.1,     # m
    'wall_thickness': 0.005,     # m
}

# /calculate — hibrit varsayılan akış (UI'nin gönderdiği çekirdek alanlar;
# ağır adımlar BİLEREK açık bırakıldı: süre sözleşmesi gerçek akışı ölçer)
CALCULATE_PAYLOAD = {
    'thrust': 1000,
    'burn_time': 10,
    'of_ratio': 6.0,
    'chamber_pressure': 20.0,
    'fuel_type': 'htpb',
    'oxidizer_type': 'n2o',
}

CALCULATE_TIME_BUDGET_S = 30.0


def _finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def _assert_keys(d, keys, where):
    missing = [k for k in keys if k not in d]
    assert not missing, f"{where} eksik anahtarlar: {missing}"


# ---------------------------------------------------------------------------
# Ortak fikstürler — ağır /calculate yalnız BİR kez koşar (modül kapsamı)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def calc_response(client):
    """Tam varsayılan hibrit /calculate — süre ölçümüyle birlikte."""
    t0 = time.monotonic()
    r = client.post('/calculate', json=CALCULATE_PAYLOAD)
    elapsed = time.monotonic() - t0
    assert r.status_code == 200, f"/calculate {r.status_code} döndü"
    return {'json': r.get_json(), 'elapsed': elapsed}


@pytest.fixture(scope='module')
def structural_json(client):
    r = client.post('/analyze_structural_safety', json=STRUCTURAL_PAYLOAD)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def thermal_json(client):
    r = client.post('/analyze_thermal_safety', json=THERMAL_PAYLOAD)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def safety_json(client):
    r = client.post('/analyze_safety', json=SAFETY_PAYLOAD)
    assert r.status_code == 200
    return r.get_json()


# ---------------------------------------------------------------------------
# 1. Sayfa sözleşmesi
# ---------------------------------------------------------------------------

class TestPageContract:
    @pytest.mark.parametrize('page', ALL_PAGES)
    def test_page_returns_200_html(self, client, page):
        r = client.get(page)
        assert r.status_code == 200, f"{page} -> {r.status_code}"
        assert 'text/html' in r.content_type
        assert len(r.data) > 500, f"{page} şüpheli derecede boş"

    @pytest.mark.parametrize('page', MOTOR_PAGES)
    def test_dock_loads_before_panels(self, client, page):
        """analysis_dock.js paneller kendilerini register edebilsin diye
        HER panel script'inden önce gelmeli (yükleme sırası sözleşmesi)."""
        html = client.get(page).get_data(as_text=True)
        dock_idx = html.find(DOCK_SCRIPT)
        assert dock_idx != -1, f"{page} sayfasında {DOCK_SCRIPT} yok"
        for panel in PANEL_SCRIPTS:
            p_idx = html.find(panel)
            assert p_idx != -1, f"{page} sayfasında {panel} yok"
            assert p_idx > dock_idx, (
                f"{page}: {panel} analysis_dock.js'ten ÖNCE yükleniyor — "
                "panel register edilemez (window.AnalysisDock tanımsız)")

    @pytest.mark.parametrize('page', MOTOR_PAGES)
    def test_hud_script_present_before_dock(self, client, page):
        """hud.js HUD katmanını kurar; dock'tan önce gelmeli."""
        html = client.get(page).get_data(as_text=True)
        hud_idx = html.find(HUD_SCRIPT)
        dock_idx = html.find(DOCK_SCRIPT)
        assert hud_idx != -1, f"{page} sayfasında {HUD_SCRIPT} yok"
        assert hud_idx < dock_idx

    @pytest.mark.parametrize('page', MOTOR_PAGES)
    def test_dock_anchor_present(self, client, page):
        html = client.get(page).get_data(as_text=True)
        assert f'id="{DOCK_ANCHOR_ID}"' in html, (
            f"{page}: #{DOCK_ANCHOR_ID} yok — AnalysisDock.init kurulamaz")

    @pytest.mark.parametrize('page', MOTOR_PAGES)
    def test_dock_init_wired_to_anchor(self, client, page):
        """AnalysisDock.init çağrısı anchor'a bağlanmış olmalı."""
        html = client.get(page).get_data(as_text=True)
        assert 'AnalysisDock.init' in html
        assert f"anchorId: '{DOCK_ANCHOR_ID}'" in html

    def test_landing_page_has_no_partial_dock(self, client):
        """Açılış sayfası (/) güverte içermez; yarım entegrasyon (script var,
        anchor yok gibi) regresyonunu yakalar."""
        html = client.get('/').get_data(as_text=True)
        if DOCK_SCRIPT in html:
            # Güverte eklenmişse sözleşmenin tamamı gelmeli
            assert f'id="{DOCK_ANCHOR_ID}"' in html
            for panel in PANEL_SCRIPTS:
                assert panel in html


# ---------------------------------------------------------------------------
# 2. Panel yanıt sözleşmeleri — panellerin render() içinde okuduğu anahtarlar
# ---------------------------------------------------------------------------

class TestStructuralResponseContract:
    def test_status_success(self, structural_json):
        assert structural_json['status'] == 'success'
        assert 'structural_analysis' in structural_json

    def test_sections_panel_reads(self, structural_json):
        sa = structural_json['structural_analysis']
        _assert_keys(sa, [
            'chamber_analysis', 'safety_analysis', 'buckling_analysis',
            'fatigue_analysis', 'fastener_analysis', 'end_cap_analysis',
            'material_properties', 'design_parameters', 'weight_analysis',
        ], 'structural_analysis')

    def test_chamber_analysis_keys(self, structural_json):
        ca = structural_json['structural_analysis']['chamber_analysis']
        _assert_keys(ca, [
            'von_mises_stress', 'von_mises_safety_factor',
            'pressure_hoop_stress', 'hoop_safety_factor',
            'thermal_hoop_stress', 'longitudinal_stress',
            'minimum_thickness', 'recommended_thickness',
            'governing_thermal_scenario', 'yield_strength_used_MPa',
            'pressure_hoop_model',
            # Dalga 0 çift-SF raporu (app.js exportu + panel bunları okur)
            'safety_factor_pressure', 'safety_factor_total',
        ], 'chamber_analysis')
        for k in ('von_mises_stress', 'von_mises_safety_factor',
                  'hoop_safety_factor', 'safety_factor_pressure',
                  'safety_factor_total'):
            assert _finite(ca[k]) and ca[k] > 0, f"chamber_analysis.{k} sayısal değil"

    def test_top_level_dual_sf_report(self, structural_json):
        """app.js SF exportu structural_analysis üst seviyesinden okur."""
        sa = structural_json['structural_analysis']
        _assert_keys(sa, ['safety_factor_pressure', 'safety_factor_total',
                          'safety_factor'], 'structural_analysis (üst seviye SF)')
        assert _finite(sa['safety_factor_pressure'])
        assert _finite(sa['safety_factor_total'])
        # Geriye dönük tek-SF alanı toplam SF'ye eşit olmalı
        assert sa['safety_factor'] == pytest.approx(sa['safety_factor_total'])

    def test_safety_analysis_keys(self, structural_json):
        sf = structural_json['structural_analysis']['safety_analysis']
        _assert_keys(sf, ['status', 'risk_level', 'minimum_safety_factor',
                          'safety_factors', 'recommendations'],
                     'safety_analysis')
        # Panel mod etiketleri: chamber_hoop / chamber_von_mises / end_cap /
        # nozzle / buckling_axial
        modes = sf['safety_factors']
        _assert_keys(modes, ['chamber_hoop', 'chamber_von_mises', 'end_cap',
                             'nozzle', 'buckling_axial'],
                     'safety_analysis.safety_factors')
        assert _finite(sf['minimum_safety_factor'])
        assert sf['minimum_safety_factor'] == pytest.approx(
            min(v for v in modes.values() if _finite(v)), rel=1e-9)

    def test_buckling_analysis_keys(self, structural_json):
        buck = structural_json['structural_analysis']['buckling_analysis']
        _assert_keys(buck, [
            'buckling_status', 'applied_axial_stress_MPa',
            'critical_axial_buckling_stress_MPa',
            'axial_buckling_safety_factor', 'knockdown_factor_gamma',
            'critical_external_pressure_bar', 'source',
        ], 'buckling_analysis')
        assert buck['buckling_status'] in ('SAFE', 'MARGINAL', 'CRITICAL')
        # NASA SP-8007 düşürme katsayısı fiziksel aralıkta
        assert 0.0 < buck['knockdown_factor_gamma'] <= 1.0

    def test_fatigue_fastener_endcap_keys(self, structural_json):
        sa = structural_json['structural_analysis']
        _assert_keys(sa['fatigue_analysis'],
                     ['fatigue_status', 'estimated_cycles', 'estimated_life',
                      'fatigue_safety_factor', 'fatigue_limit'],
                     'fatigue_analysis')
        _assert_keys(sa['fastener_analysis'],
                     ['num_bolts', 'recommended_bolt_size',
                      'bolt_safety_factor', 'force_per_bolt', 'total_force',
                      'bolt_spacing'],
                     'fastener_analysis')
        _assert_keys(sa['end_cap_analysis'],
                     ['recommended_type', 'dished_head_thickness',
                      'flat_head_thickness', 'head_safety_factor'],
                     'end_cap_analysis')

    def test_material_and_design_keys(self, structural_json):
        sa = structural_json['structural_analysis']
        # Panel "gerekli SF" değerini malzeme kartından okur
        assert _finite(sa['material_properties']['safety_factor'])
        dp = sa['design_parameters']
        _assert_keys(dp, ['material', 'design_pressure',
                          'design_pressure_factor'], 'design_parameters')
        assert dp['material'] == STRUCTURAL_PAYLOAD['material']
        # Tasarım basıncı = işletme x faktör (bar)
        assert dp['design_pressure'] == pytest.approx(
            STRUCTURAL_PAYLOAD['chamber_pressure'] * dp['design_pressure_factor'])

    def test_weight_analysis_keys(self, structural_json):
        wt = structural_json['structural_analysis']['weight_analysis']
        _assert_keys(wt, ['total_weight', 'chamber_weight', 'nozzle_weight',
                          'end_caps_weight'], 'weight_analysis')
        assert wt['total_weight'] == pytest.approx(
            wt['chamber_weight'] + wt['nozzle_weight'] + wt['end_caps_weight'])


class TestThermalResponseContract:
    def test_status_success(self, thermal_json):
        assert thermal_json['status'] == 'success'
        assert 'thermal_analysis' in thermal_json

    def test_sections_panel_reads(self, thermal_json):
        ta = thermal_json['thermal_analysis']
        _assert_keys(ta, [
            'heat_transfer_coefficients', 'gas_side_analysis',
            'wall_analysis', 'cooling_analysis', 'safety_analysis',
            'material_properties', 'design_parameters',
        ], 'thermal_analysis')

    def test_bartz_coefficient(self, thermal_json):
        htc = thermal_json['thermal_analysis']['heat_transfer_coefficients']
        _assert_keys(htc, ['gas_side', 'correlation'],
                     'heat_transfer_coefficients')
        assert _finite(htc['gas_side']) and htc['gas_side'] > 0
        assert 'Bartz' in str(htc['correlation'])

    def test_gas_side_keys(self, thermal_json):
        gsa = thermal_json['thermal_analysis']['gas_side_analysis']
        _assert_keys(gsa, ['gas_temperature', 'adiabatic_wall_temperature',
                           'throat_heat_flux', 'chamber_heat_flux',
                           'surface_area'], 'gas_side_analysis')
        # Boğaz akısı hazne akısından yüksek olmalı (Bartz ~ A_t/A oranı)
        assert gsa['throat_heat_flux'] > gsa['chamber_heat_flux'] > 0

    def test_wall_temperatures_ordered(self, thermal_json):
        ta = thermal_json['thermal_analysis']
        wa = ta['wall_analysis']
        gsa = ta['gas_side_analysis']
        _assert_keys(wa, ['inner_temperature', 'outer_temperature'],
                     'wall_analysis')
        # İç cidar dış cidardan sıcak; hiçbiri gaz sıcaklığını aşamaz
        assert wa['inner_temperature'] > wa['outer_temperature']
        assert wa['inner_temperature'] <= gsa['gas_temperature'] + 1e-6

    def test_cooling_keys(self, thermal_json):
        cool = thermal_json['thermal_analysis']['cooling_analysis']
        _assert_keys(cool, ['cooling_efficiency', 'peak_heat_rate',
                            'total_heat_energy', 'required_cooling_area',
                            'heat_sink_mass'], 'cooling_analysis')

    def test_thermal_safety_keys(self, thermal_json):
        safe = thermal_json['thermal_analysis']['safety_analysis']
        _assert_keys(safe, ['risk_level', 'melting_safety_factor',
                            'temperature_safety_factor',
                            'stress_safety_factor', 'thermal_stress'],
                     'thermal safety_analysis')
        matp = thermal_json['thermal_analysis']['material_properties']
        _assert_keys(matp, ['allowable_temperature', 'melting_point'],
                     'material_properties')
        # Ergime noktası izin verilen sıcaklıktan yüksek olmalı
        assert matp['melting_point'] > matp['allowable_temperature']

    def test_design_parameters_echo(self, thermal_json):
        dpp = thermal_json['thermal_analysis']['design_parameters']
        _assert_keys(dpp, ['cooling_type', 'wall_thickness', 'material'],
                     'thermal design_parameters')
        assert dpp['cooling_type'] == THERMAL_PAYLOAD['cooling_type']
        assert dpp['material'] == THERMAL_PAYLOAD['material']


class TestSafetyResponseContract:
    RISK_AREAS = ['structural', 'pressure', 'thermal', 'explosive',
                  'toxic', 'fire']

    def test_status_success(self, safety_json):
        assert safety_json['status'] == 'success'
        assert 'safety_analysis' in safety_json

    def test_risk_assessment_keys(self, safety_json):
        risk = safety_json['safety_analysis']['risk_assessment']
        _assert_keys(risk, ['risk_level', 'acceptability',
                            'overall_risk_score', 'individual_risks',
                            'mitigation_priority'], 'risk_assessment')
        assert risk['risk_level'] in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')

    def test_individual_risks_in_band(self, safety_json):
        risks = safety_json['safety_analysis']['risk_assessment']['individual_risks']
        _assert_keys(risks, self.RISK_AREAS, 'individual_risks')
        for area in self.RISK_AREAS:
            assert 1.0 <= risks[area] <= 5.0, f"{area} skoru 1-5 dışı"
        overall = safety_json['safety_analysis']['risk_assessment']['overall_risk_score']
        assert 1.0 <= overall <= 5.0

    def test_mitigation_priority_sorted(self, safety_json):
        pri = safety_json['safety_analysis']['risk_assessment']['mitigation_priority']
        assert isinstance(pri, list) and len(pri) >= 1
        for i, p in enumerate(pri, start=1):
            _assert_keys(p, ['priority', 'area', 'risk_score'],
                         'mitigation_priority öğesi')
            assert p['priority'] == i
        scores = [p['risk_score'] for p in pri]
        assert scores == sorted(scores, reverse=True), (
            'mitigation_priority skorları azalan sırada olmalı')

    def test_pressure_vessel_ladder(self, safety_json):
        press = safety_json['safety_analysis']['pressure_safety']
        _assert_keys(press, ['operating_pressure_bar', 'design_pressure_bar',
                             'proof_pressure_bar',
                             'hydrostatic_test_pressure_bar',
                             'required_burst_pressure_bar'],
                     'pressure_safety')
        # Basınç merdiveni: işletme < tasarım <= proof <= hidrostatik;
        # burst hedefi tasarımın üstünde
        assert press['operating_pressure_bar'] == pytest.approx(
            SAFETY_PAYLOAD['chamber_pressure'])
        assert press['operating_pressure_bar'] < press['design_pressure_bar']
        assert press['design_pressure_bar'] <= press['proof_pressure_bar']
        assert press['proof_pressure_bar'] <= press['hydrostatic_test_pressure_bar']
        assert press['required_burst_pressure_bar'] > press['design_pressure_bar']

    def test_compliance_and_recommendations(self, safety_json):
        s = safety_json['safety_analysis']
        comp = s['compliance']
        _assert_keys(comp, ['nfpa_compliance', 'osha_compliance',
                            'dot_compliance'], 'compliance')
        assert isinstance(s['recommendations'], list)

    def test_compliance_never_claims_conformity(self, safety_json):
        """Uygunluk alanları hüküm ÜRETMEMELİ — yalnız NOT_EVALUATED.

        Bu alanlar eskiden koşulsuz ``True`` dönüyor ve arayüzde yeşil
        "NFPA: OK" rozeti olarak çiziliyordu; backend'in kendi yorumları
        gerçek bir kontrol yapılmadığını söylüyordu. Gerçek uygunluk
        değerlendirmesi requirement karşılaştırması, saha bilgisi ve yetkili
        bir değerlendirici ister — hiçbiri yazılıma girdi değil.
        """
        comp = safety_json['safety_analysis']['compliance']
        for key in ('nfpa_compliance', 'osha_compliance', 'dot_compliance',
                    'local_regulations', 'insurance_requirements'):
            assert comp[key] == 'NOT_EVALUATED', (
                f'{key} bir uygunluk hükmü üretiyor ({comp[key]!r}); '
                'yazılım mevzuat uygunluğu değerlendiremez.'
            )
        # Model riski kabul edilebilirliği mevzuat uygunluğu DEĞİLDİR;
        # eski 'overall_compliance' adı bu ikisini karıştırıyordu.
        assert 'overall_compliance' not in comp
        assert 'model_risk_acceptability' in comp


# ---------------------------------------------------------------------------
# 3. 501 bekçileri
# ---------------------------------------------------------------------------

class TestGuards501:
    @pytest.mark.parametrize('endpoint', GUARDED_501_ENDPOINTS)
    def test_honest_501(self, client, endpoint):
        r = client.post(endpoint, json={'motor_type': 'hybrid'})
        assert r.status_code == 501, f"{endpoint} 501 dönmeli"
        j = r.get_json()
        assert j['status'] == 'unavailable'


# ---------------------------------------------------------------------------
# 4. /calculate sözleşmesi
# ---------------------------------------------------------------------------

class TestCalculateContract:
    def test_completes_within_budget(self, calc_response):
        assert calc_response['elapsed'] < CALCULATE_TIME_BUDGET_S, (
            f"/calculate {calc_response['elapsed']:.1f} sn sürdü "
            f"(bütçe {CALCULATE_TIME_BUDGET_S} sn)")

    def test_gamma_and_mw_top_level(self, calc_response):
        motor = calc_response['json']['motor']
        _assert_keys(motor, ['gamma', 'molecular_weight'], 'motor sonuçları')
        # Fiziksel aralıklar: yanma gazı için γ ve MW
        assert 1.05 < motor['gamma'] < 1.45
        assert 10.0 < motor['molecular_weight'] < 60.0

    def test_dead_plot_keys_absent(self, calc_response):
        plots = calc_response['json']['plots']
        assert 'heat_transfer' not in plots, (
            'plots.heat_transfer geri gelmiş — Dalga 0 ölü yük temizliği bozuldu')
        assert 'structural_analysis' not in plots, (
            'plots.structural_analysis geri gelmiş — Dalga 0 temizliği bozuldu')

    def test_panel_source_fields_present(self, calc_response):
        """Structural panelin fromResults() okuduğu motor alanları."""
        motor = calc_response['json']['motor']
        for k in ('chamber_pressure', 'chamber_diameter', 'chamber_length',
                  'throat_diameter', 'burn_time', 'mdot_total',
                  'chamber_temperature'):
            assert _finite(motor.get(k)) and motor[k] > 0, (
                f"motor.{k} yok ya da sayısal değil — panel önerileri boş kalır")


# ---------------------------------------------------------------------------
# 5. Uçtan uca duman: /calculate -> structural panel akışı
# ---------------------------------------------------------------------------

class TestEndToEndStructuralFlow:
    @pytest.fixture(scope='class')
    def flow_structural(self, client, calc_response):
        """structural_panel.js fromResults() eşlemesinin Python kopyası."""
        motor = calc_response['json']['motor']
        payload = {
            'chamber_pressure': motor['chamber_pressure'],
            'chamber_diameter': motor['chamber_diameter'],
            'chamber_length': motor['chamber_length'],
            'throat_diameter': motor['throat_diameter'],
            'burn_time': motor['burn_time'],
            'material': 'steel_4130',  # panel varsayılanı
        }
        r = client.post('/analyze_structural_safety', json=payload)
        assert r.status_code == 200, (
            f"/calculate değerleriyle yapısal analiz {r.status_code} döndü")
        return r.get_json()

    def test_sf_fields_numeric(self, flow_structural):
        sa = flow_structural['structural_analysis']
        for k in ('safety_factor_pressure', 'safety_factor_total'):
            assert _finite(sa[k]) and sa[k] > 0, f"{k} sayısal/pozitif değil"
        ca = sa['chamber_analysis']
        for k in ('von_mises_safety_factor', 'hoop_safety_factor'):
            assert _finite(ca[k]) and ca[k] > 0

    def test_sf_pressure_ge_sf_total(self, flow_structural):
        """Basınç-yalnız SF, termal gerilme içeren toplam SF'den küçük
        OLAMAZ (termal katkı gerilmeyi artırır, SF'yi düşürür)."""
        sa = flow_structural['structural_analysis']
        assert sa['safety_factor_pressure'] >= sa['safety_factor_total'] - 1e-9

    def test_top_level_matches_chamber_analysis(self, flow_structural):
        """Üst seviye SF raporu chamber_analysis ile tutarlı olmalı
        (app.js exportu üst seviyeden, panel chamber_analysis'ten okur)."""
        sa = flow_structural['structural_analysis']
        ca = sa['chamber_analysis']
        assert sa['safety_factor_pressure'] == pytest.approx(
            ca['safety_factor_pressure'])
        assert sa['safety_factor_total'] == pytest.approx(
            ca['safety_factor_total'])

    def test_minimum_sf_not_above_chamber_sf(self, flow_structural):
        """Tüm modların minimumu, hazne SF'lerinden büyük olamaz."""
        sa = flow_structural['structural_analysis']
        min_sf = sa['safety_analysis']['minimum_safety_factor']
        assert _finite(min_sf)
        assert min_sf <= sa['safety_factor_total'] + 1e-9


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
