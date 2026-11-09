"""V306/SIVI-KÜTLE bekçileri — sıvı motorun kütle ve güvenlik sayıları (3.0.6).

Kalem 1 (M-SIVI-1)  kumanda / aviyonik motor kuru kütlesine girmez; araç
                    kalemi olarak uçuş dökümünde adıyla durur
Kalem 2 (M-SIVI-4)  tank basınç sınıfı önerilen paylı tank basıncının
                    altındaysa adıyla uyarı; tek tanım

Kanıt: docs/scofield/raw/OH/V306/sivi-kutle/ (önce/sonra ölçümleri, RAPOR.md).
Vaka gövdeleri mühendis turunun gerçek API gövdeleridir (L1 aşağıda satır
içi: kanıt dizini yayın dalında yoktur).
"""
import importlib.util
import json
import math
import pathlib
import re
import shutil

import pytest

from hrma.analysis import flight_vehicle as fv

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates'
G0 = 9.80665
node_gerekli = pytest.mark.skipif(shutil.which('node') is None,
                                  reason='node yok')

#: Mühendis turu L1 son tasarımı (800 N LOX/RP-1, basınç beslemeli, ablatif).
L1_GOVDE = {
    'chamber_material': 'steel_304', 'chamber_pressure': 15,
    'chamber_roughness': 3.2, 'characteristic_length': 1.2,
    'combustion_efficiency': 97, 'contraction_ratio': 4,
    'coolant_flow_percent': 100, 'coolant_inlet_temp': 300,
    'cooling_type': 'ablative', 'discharge_coefficient': 0.7,
    'engine_cycle': 'pressure_fed', 'engine_life_cycles': 10,
    'feed_pressure': 25, 'film_cooling_percent': 0, 'fuel_type': 'rp1',
    'injector_elements': 12, 'injector_pressure_drop': 3,
    'injector_type': 'unlike_impinging', 'max_burn_duration': 7.7,
    'max_wall_temp': 800, 'min_throttle': 40, 'mixture_ratio': 2.3,
    'nozzle_expansion_ratio': 3.5, 'nozzle_type': 'conical', 'of_max': 3.2,
    'of_min': 2, 'oxidizer_density': 1141.16, 'oxidizer_type': 'lox',
    'oxidizer_viscosity': 0.0001947, 'safety_factor': 2.5, 'thrust': 800,
}
ORNEK = KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma'


def _oku(yol):
    return pathlib.Path(yol).read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


def _hesap(client, govde):
    r = client.post('/calculate_liquid', json=govde,
                    headers={'Host': '127.0.0.1:8080'})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


@pytest.fixture(scope='module')
def l1(client):
    return _hesap(client, L1_GOVDE)


@pytest.fixture(scope='module')
def ornek(client):
    alanlar = json.loads(_oku(ORNEK))['inputs']['fields']
    return _hesap(client, dict(alanlar))


# ------------------------------------------------------------- kalem 1

def _bes_bilesen(cm):
    # V306/SIVI-MODEL kalem 4: plaka boyutlanmadıysa enjektör TARTILMAZ
    # (None, ``component_sizing.not_weighed``ta adıyla); toplam tartılan
    # bileşenlerindir.
    return sum(cm[k] for k in ('combustion_chamber', 'nozzle_assembly',
                               'injector_assembly', 'turbopump_assembly',
                               'feed_system') if cm[k] is not None)


@pytest.mark.parametrize('ad', ['l1', 'ornek'])
def test_motor_kuru_kutlesinde_sabit_aviyonik_payi_yok(ad, request):
    r = request.getfixturevalue(ad)
    cs = r['component_sizing']
    cm = cs['component_masses']
    # Kumanda / aviyonik motor kuru kütlesinin bir kalemi DEĞİL.
    assert 'controls_avionics' not in cm
    assert cm['total_dry_mass'] == pytest.approx(_bes_bilesen(cm), rel=1e-12)
    # Kalem adıyla, kütlesiz durur (sessizce kaybolmaz).
    assert cs['not_in_engine_dry_mass'] == [{
        'key': 'controls_avionics', 'mass_kg': None,
        'basis': cs['not_in_engine_dry_mass'][0]['basis']}]
    assert 'NOT part of the engine dry mass' in \
        cs['mass_method']['controls_avionics']
    # Yayımlanan motor kütlesi ve T/W aynı toplamdan.
    m = cm['total_dry_mass']
    assert r['engine_mass_estimate'] == m
    assert r['design_summary']['masses']['engine_mass_kg'] == m
    assert r['thrust_to_weight'] == pytest.approx(r['thrust'] / (m * G0),
                                                  rel=1e-9)


def test_kucuk_motorda_kuru_kutle_bilesen_olcegindedir(l1):
    """800 N motorda kuru kütle bileşenlerinden gelir (eskiden 16,877 kg'ın
    15,0 kg'ı sabit paydı). Ölçek denetimi: hiçbir tek kalem toplamın
    yarısını, ölçekten bağımsız bir sabitle geçmiyor; toplam 15 kg'ın
    altında (eski sabitin kendisi bile toplamdan büyüktü)."""
    cm = l1['component_sizing']['component_masses']
    assert cm['total_dry_mass'] < 15.0
    assert l1['thrust_to_weight'] > 10.0


def test_ucus_araci_cikan_kalemi_adiyla_tasir_iki_kez_saymaz(l1):
    v = fv.normalize('liquid', l1)
    assert v['vehicle_items_not_in_engine'] == [
        {'key': 'controls_avionics', 'mass_kg': None}]
    toplam = 0.0
    for k in v['engine_inert_mass_items']:
        toplam += k['mass_kg']
    assert v['engine_inert_mass'] == toplam
    kuru = [k for k in v['engine_inert_mass_items'] if k['key'] == 'engine_dry']
    assert kuru[0]['mass_kg'] == \
        l1['component_sizing']['component_masses']['total_dry_mass']
    assert v['engine_inert_mass_note'].endswith(
        fv.VEHICLE_ITEMS_NOT_IN_ENGINE_NOTE.format(
            items='controls / avionics (controller box, harness, sensors)'))


def test_eski_sonucta_arac_kalemi_uydurulmaz():
    """Listeyi yayımlamayan (eski) sonuçta araç kalemi eklenmez."""
    v = fv.normalize('liquid', {
        'thrust': 800.0, 'burn_time': 7.7,
        'design_summary': {'masses': {'engine_mass_kg': 16.877,
                                      'propellant_mass_kg': 2.833}}})
    assert v['vehicle_items_not_in_engine'] == []
    assert 'controls / avionics' not in v['engine_inert_mass_note']


def _ucus_node():
    spec = importlib.util.spec_from_file_location(
        '_ucus_bekci', KOK / 'tests' / 'test_v306_ucus.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._node


@node_gerekli
def test_kalem_satiri_cikan_arac_kalemini_adiyla_yazar():
    r = _ucus_node()(r"""
      var s = {engine_inert_mass: 4.155, engine_inert_mass_items: [
        {key: 'engine_dry', mass_kg: 1.877}, {key: 'tank_structure', mass_kg: 1.853},
        {key: 'reserve_propellant', mass_kg: 0.425}],
        vehicle_items_not_in_engine: [{key: 'controls_avionics', mass_kg: null}]};
      var e = {engine_inert_mass: 4.155, engine_inert_mass_items: s.engine_inert_mass_items};
      console.log(JSON.stringify({s: window.FlightHandoff.inertLedgerText(s, 4.155),
        f: window.FlightHandoff.inertLedgerText(s, 11.155),
        e: window.FlightHandoff.inertLedgerText(e, 4.155)}));
    """)
    assert '= 4.155 kg' in r['s']
    assert 'controls / avionics (controller box, harness, sensors)' in r['s']
    assert 'controls_avionics' not in r['s']
    assert 'Not in the engine mass' in r['s']
    assert 'Not in the engine mass' in r['f'] and 'not from the engine' in r['f']
    assert '..' not in r['f']
    assert 'Not in the engine mass' not in r['e']


def test_cikan_kalemin_metinleri_iki_dilde():
    kabuk = _oku(JS / 'i18n_shell.js')
    for k in ('flight.notInEngine', 'flight.vehicleItem.controls_avionics'):
        assert kabuk.count("'%s'" % k) == 2, k
    sayfa = _oku(JS / 'i18n_pages.js')
    assert sayfa.count("'liq.msg.controls_avionics_not_in_engine'") == 2
    # Fırlatma Sahası künyesinin eki TR desende (çevrilmezse İngilizce kalır).
    cizim = _oku(JS / 'i18n_charts.js')
    assert 'not in the engine dry mass: controls \\/ avionics' in cizim
    sablon = _oku(SABLON / 'liquid.html')
    assert 'not_in_engine_dry_mass' in sablon


# ------------------------------------------------------------- kalem 2

def test_tank_sinifi_onerinin_altindaysa_adiyla_uyarir(l1):
    inj = l1['injection_system']
    kodlar = {w['code']: w for w in l1['input_warnings']}
    for tank, taraf in (('oxidizer_tank', 'ox'), ('fuel_tank', 'fuel')):
        st = l1['propellant_tanks'][tank]['structural']
        oneri = inj[f'recommended_{taraf}_tank_pressure_with_margin']
        gerekli = inj[f'required_{taraf}_tank_pressure']
        # Tek tanım: sınıf = besleme basıncı; öneri = gerekli + pay.
        assert st['pressure_rating'] == 25.0
        assert st['pressure_rating_recommended_bar'] == oneri
        assert st['pressure_rating_required_bar'] == gerekli
        assert gerekli < st['pressure_rating'] < oneri
        assert st['pressure_rating_check'] == 'below_recommended'
        w = kodlar[f'warn.liquid.{taraf}_tank_rating_below_recommended']
        assert w['severity'] == 'warning'
        assert w['params']['rating_bar'] == 25.0
        assert w['params']['recommended_bar'] == round(oneri, 2)


def test_tank_sinifi_oneriyi_karsilarsa_uyari_yok(client):
    r = _hesap(client, dict(L1_GOVDE, feed_pressure=30))
    for tank in ('oxidizer_tank', 'fuel_tank'):
        assert r['propellant_tanks'][tank]['structural'][
            'pressure_rating_check'] == 'meets_recommended'
    assert not [w for w in r['input_warnings']
                if 'rating_below_recommended' in w['code']]


def test_turbopompali_cevrimde_karsilastirma_yok(ornek):
    for tank in ('oxidizer_tank', 'fuel_tank'):
        st = ornek['propellant_tanks'][tank]['structural']
        assert st['pressure_rating_check'] == 'not_applicable'
        assert 'pressure_rating_recommended_bar' not in st


def test_tank_sinifi_uyarisi_iki_dilde_ve_kartta():
    ortak = _oku(JS / 'i18n_common.js')
    for taraf in ('ox', 'fuel'):
        k = "'warn.liquid.%s_tank_rating_below_recommended'" % taraf
        assert ortak.count(k) == 2, k
    sayfa = _oku(JS / 'i18n_pages.js')
    assert sayfa.count("'liq.js.rating_below_recommended'") == 2
    sablon = _oku(SABLON / 'liquid.html')
    assert sablon.count('tankSinifNotu(tankData.') == 2


# ------------------------------------------------------------- kalem 3

#: SIVI-SOĞUTMA M-SIVI-11 vakası: L2 metan rejeneratif, Pc 20 / besleme
#: 32 bar -> marş doyma eğrisine düşer, soğutma devresi ÇÖZÜLMEZ.
L2_METAN_COZULMEZ = dict(
    L1_GOVDE, fuel_type='methane', fuel_density=422.352,
    fuel_viscosity=0.0001169, mixture_ratio=3, thrust=2000,
    chamber_pressure=20, feed_pressure=32, injector_type='coaxial',
    injector_pressure_drop=7, injector_elements=18, chamber_material='cucrzr',
    cooling_type='regenerative', nozzle_expansion_ratio=6,
    nozzle_type='bell_80', max_burn_duration=18)


def guvenlik_govdesi(r):
    """Güvenlik panelinin (safety_panel.js) sıvı gövdesi: tohumlar +
    hüküm bloğu bağlamı (motor_result / motor_verdict_inputs)."""
    cs = r['structural_analysis']['chamber_structure']
    g = {'motor_type': 'liquid', 'chamber_pressure': r['chamber_pressure'],
         'chamber_temperature': r['chamber_temperature'],
         'thrust': r['thrust'], 'burn_time': r['burn_time'],
         'chamber_diameter': r['chamber_diameter'] / 1000.0,
         'propellant_type': 'liquid_biprop',
         'propellant_mass': r['design_summary']['masses']['propellant_mass_kg'],
         'wall_thickness': cs['wall_thickness'] / 1000.0,
         'material': cs['material_key'],
         'motor_result': {'structural_analysis': {'chamber_structure': cs}}}
    g['motor_verdict_inputs'] = {k: g[k] for k in (
        'chamber_pressure', 'chamber_diameter', 'wall_thickness')}
    return g


@pytest.fixture(scope='module')
def cozulmez(client):
    r = _hesap(client, L2_METAN_COZULMEZ)
    s = client.post('/analyze_safety', json=guvenlik_govdesi(r),
                    headers={'Host': '127.0.0.1:8080'})
    assert s.status_code == 200, s.get_json()
    return r, s.get_json()['safety_analysis']


def test_cozulmeyen_devrenin_kabugu_guvenlikte_degerlendirilmez(cozulmez):
    r, sa = cozulmez
    cs = r['structural_analysis']['chamber_structure']
    # Motorun kendi kararı: devre çözülmedi, kabuk hükmü geri çekildi.
    assert cs['cooling_circuit_status'] == 'not_solved'
    ps = sa['pressure_safety']
    assert ps['vessel_status'] == 'NOT_EVALUATED'
    for alan in ('actual_burst_pressure_bar', 'burst_margin',
                 'burst_margin_vs_meop', 'required_burst_pressure_bar',
                 'proof_pressure_bar', 'wall_thickness_mm'):
        assert ps[alan] is None, alan
    assert ps['evaluated_layer'] == {
        'role': 'closeout', 'withheld': True,
        'withheld_code': 'cooling_circuit_not_solved'}
    assert 'not solved' in ps['pressure_layer_withheld']['withheld_basis']
    # Basınç ekseni değerlendirilmeyen eksendir (kısmi sepet), düşük değil.
    assert 'pressure' in sa['risk_assessment']['motor_axes_not_evaluated']


@pytest.mark.parametrize('blok_ek, kabuk_ek, kod', [
    ({'cooling_circuit_status': 'not_solved'}, {'verdict': 'withheld'},
     'cooling_circuit_not_solved'),
    ({}, {'verdict': 'withheld', 'withheld_reason': 'model validity'},
     'closeout_verdict_withheld'),
    ({}, {'verdict': 'not_evaluated', 'thickness_mm': None},
     'closeout_not_evaluated'),
])
def test_yayimlanmayan_kabuk_kodu_adiyla(blok_ek, kabuk_ek, kod):
    from hrma.analysis.safety_analysis import motor_pressure_bearing_layer
    k = {'role': 'closeout', 'material_key': 'inconel_718',
         'thickness_mm': 2.5, 'inner_radius_mm': 118.9,
         'max_temperature_K': 414.0, 'coolant_pressure_bar': 76.3,
         'stress_MPa': 370.5, 'verdict': 'pass'}
    k.update(kabuk_ek)
    blok = {'wall_model': 'two_layer_regenerative', 'wall_layers': [k]}
    blok.update(blok_ek)
    kayit = motor_pressure_bearing_layer(blok)
    assert kayit['withheld'] is True and kayit['withheld_code'] == kod
    assert 'thickness_mm' not in kayit and 'stress_MPa' not in kayit


def test_yayimlanmis_kabuk_degerlendirilmeye_devam_eder(client):
    """Rejeneratif L3 (devre çözülür, kabuk 'pass'): katman benimsenir."""
    r = _hesap(client, dict(L1_GOVDE, thrust=5000, chamber_pressure=30,
                            feed_pressure=45, cooling_type='regenerative',
                            chamber_material='cucrzr', max_burn_duration=36,
                            nozzle_expansion_ratio=8))
    if r['structural_analysis']['chamber_structure'].get(
            'cooling_circuit_status') == 'not_solved':
        pytest.skip('bu girdide devre çözülmedi')
    s = client.post('/analyze_safety', json=guvenlik_govdesi(r),
                    headers={'Host': '127.0.0.1:8080'}).get_json()
    ps = s['safety_analysis']['pressure_safety']
    assert ps['evaluated_layer']['role'] == 'closeout'
    assert ps['evaluated_layer'].get('withheld') is not True
    assert ps['vessel_status'] in ('PASS', 'MARGINAL', 'FAIL')


def test_geri_cekilmis_katman_metinleri_iki_dilde():
    ortak = _oku(JS / 'i18n_common.js')
    for kod in ('cooling_circuit_not_solved', 'closeout_verdict_withheld',
                'closeout_not_evaluated'):
        assert ortak.count("'panel.safety.layerWithheld.%s'" % kod) == 2
    assert ortak.count("'panel.safety.vesselStatus.NOT_EVALUATED'") == 2
    panel = _oku(JS / 'panels' / 'safety_panel.js')
    assert 'el.withheld === true' in panel


# ------------------------------------------------------------- kalem 4

def _katman(r, rol):
    return [k for k in r['structural_analysis']['chamber_structure'][
        'wall_layers'] if k['role'] == rol][0]


def test_dis_kabugun_mdpsi_ceketin_en_yuksek_sogutucu_basinci(ornek):
    """İki katmanlı örnek sıvı (RP-1): dış kabuğun MDP'si = ceketteki en
    yüksek soğutucu basıncı (bütçe = marş girişi), oda basıncı DEĞİL; çember
    denetimi aynı sayıyı kullanır; gereksinim bu MDP'den."""
    from hrma.engines.liquid_rocket_engine import (BURST_PRESSURE_FACTOR,
                                                   PROOF_PRESSURE_FACTOR)
    kabuk = _katman(ornek, 'closeout')
    p_butce = ornek['feed_system']['pressure_drops'][
        'pump_discharge_pressure_fuel']
    assert kabuk['mdp_bar'] == kabuk['coolant_pressure_bar'] == p_butce
    assert kabuk['mdp_bar'] > ornek['chamber_pressure']
    dr = ornek['structural_analysis']['design_requirements']
    assert dr['pressure_bearing_layer'] == 'closeout'
    assert dr['mdp_bar'] == kabuk['mdp_bar']
    assert dr['proof_pressure'] == pytest.approx(
        PROOF_PRESSURE_FACTOR * kabuk['mdp_bar'], rel=1e-12)
    assert dr['burst_pressure'] == pytest.approx(
        BURST_PRESSURE_FACTOR * kabuk['mdp_bar'], rel=1e-12)
    assert 'transients are not modelled' in kabuk['mdp_basis']


def test_astarin_mdpsi_yerel_fark_zarfi_yeriyle(ornek):
    astar = _katman(ornek, 'liner')
    kabuk = _katman(ornek, 'closeout')
    yer = astar['mdp_location']
    assert yer['source'] == 'station_march' and yer['x_mm'] is not None
    # Yerel fark üst sınırdan (ceket MDP'si − yerel gaz) büyük olamaz.
    assert 0 < astar['mdp_bar'] <= kabuk['mdp_bar']
    assert astar['stress_check_pressure_difference_bar'] == \
        astar['governing_station']['pressure_difference_bar']
    assert astar['reverse_difference_bar'] is None


def test_tek_cidarda_mdp_oda_basinci(l1):
    dr = l1['structural_analysis']['design_requirements']
    assert dr['pressure_bearing_layer'] == 'chamber_wall'
    assert dr['mdp_bar'] == l1['chamber_pressure']


def test_basinc_beslemeli_metan_kabugu_tank_basinciyla(client):
    """Basınç beslemeli süperkritik yolda marş cekete tank basıncıyla girer
    (55 bar) — dış kabuk eskiden bütçenin gerekli basıncıyla (27,3 bar)
    denetleniyordu. MDP ve çember denetimi artık ceketin gerçek en yüksek
    basıncı."""
    r = _hesap(client, dict(L2_METAN_COZULMEZ, feed_pressure=55))
    assert r['cooling_circuit_publication']['status'] == 'solved'
    kabuk = _katman(r, 'closeout')
    assert kabuk['mdp_bar'] == pytest.approx(55.0)
    assert kabuk['coolant_pressure_bar'] == kabuk['mdp_bar']
    # V306/SIVI-CEKET: ceket girişi devrenin kaynak düğümüdür (girilen tank
    # basıncı); marşın en yüksek basıncı (giriş) ona EŞİT olduğu için
    # kaynak adı tank girdisidir (sayı aynı: 55 bar).
    assert kabuk['mdp_location']['source'] == 'tank_pressure_input'
    p_butce = r['feed_system']['pressure_drops'][
        'pump_discharge_pressure_fuel']
    assert p_butce < kabuk['mdp_bar']


def test_cozulmeyen_devrede_gereksinim_yayimlanmaz(cozulmez):
    r, sa = cozulmez
    dr = r['structural_analysis']['design_requirements']
    for alan in ('mdp_bar', 'proof_pressure', 'burst_pressure', 'layers'):
        assert dr[alan] is None, alan


def test_guvenlik_gereksinimi_katmanin_mdpsinden(client, ornek):
    s = client.post('/analyze_safety', json=guvenlik_govdesi(ornek),
                    headers={'Host': '127.0.0.1:8080'}).get_json()
    ps = s['safety_analysis']['pressure_safety']
    dr = ornek['structural_analysis']['design_requirements']
    assert ps['mdp_bar'] == pytest.approx(dr['mdp_bar'])
    assert ps['proof_pressure_bar'] == pytest.approx(dr['proof_pressure'])
    assert ps['required_burst_pressure_bar'] == pytest.approx(
        dr['burst_pressure'])
    assert ps['burst_margin'] == pytest.approx(
        ps['actual_burst_pressure_bar'] / ps['required_burst_pressure_bar'])


# ------------------------------------------------------------- kalem 5

def test_5012c_katsayilari_tek_tabloda_kunyeli():
    from hrma.analysis import pressure_vessel as pv
    k = pv.CODE_PRESSURE_FACTORS['nasa_std_5012c']
    assert (k['proof'], k['burst'], k['qualification']) == (1.20, 1.50, 1.50)
    assert pv.CODE_PRESSURE_FACTORS['aiaa_s080']['proof'] == 1.5
    assert pv.CODE_PRESSURE_FACTORS['aiaa_s080']['burst'] == 2.0
    assert pv.LIQUID_ENGINE_HARDWARE_CODE == 'nasa_std_5012c'
    for parca in ('NASA-STD-5012C', '2025-12-31', 'Table 1', 'p. 19'):
        assert parca in pv.NASA_5012C_BASIS
    assert 'AIAA S-080A' in pv.NASA_5012C_SCOPE_BASIS


@pytest.mark.parametrize('ad', ['l1', 'ornek'])
def test_sivi_kamara_gereksinimi_5012c(ad, request):
    r = request.getfixturevalue(ad)
    dr = r['structural_analysis']['design_requirements']
    assert dr['code'] == 'nasa_std_5012c'
    mdp = dr['mdp_bar']
    assert dr['proof_pressure'] == pytest.approx(1.20 * mdp, rel=1e-12)
    assert dr['burst_pressure'] == pytest.approx(1.50 * mdp, rel=1e-12)
    assert dr['qualification_test_pressure'] == pytest.approx(1.50 * mdp,
                                                              rel=1e-12)


def test_sivi_tank_basincli_kabi_s080de_kalir(ornek):
    for tank in ('oxidizer_tank', 'fuel_tank'):
        kap = ornek['propellant_tanks'][tank]['pressure_vessel']
        assert kap['code_mode'] == 'aiaa_s080'


def test_bas_kapak_tasarim_basinci_degismedi():
    from hrma.engines import liquid_rocket_engine as lre
    assert lre.END_CAP_DESIGN_PRESSURE_FACTOR == 1.5


def test_guvenlik_sivi_5012c_hibrit_kati_s080(client, l1):
    s = client.post('/analyze_safety', json=guvenlik_govdesi(l1),
                    headers={'Host': '127.0.0.1:8080'}).get_json()
    ps = s['safety_analysis']['pressure_safety']
    dr = l1['structural_analysis']['design_requirements']
    assert ps['code_mode'] == 'nasa_std_5012c'
    assert ps['proof_pressure_bar'] == pytest.approx(dr['proof_pressure'])
    assert ps['required_burst_pressure_bar'] == pytest.approx(
        dr['burst_pressure'])
    assert ps['qualification_test_pressure_bar'] == pytest.approx(
        dr['qualification_test_pressure'])
    assert ps['hydrostatic_test_pressure_bar'] == ps['proof_pressure_bar']
    from hrma.analysis.safety_analysis import SafetyAnalyzer
    md = {'chamber_pressure': 40.0, 'chamber_temperature': 3000.0,
          'chamber_diameter': 0.1, 'wall_thickness': 0.003,
          'thrust': 2000.0, 'burn_time': 5.0}
    for mt in ('solid', 'hybrid'):
        r = SafetyAnalyzer().analyze_comprehensive_safety(
            md, 3.0, propellant_type='composite', material='steel_4130',
            motor_type=mt)
        ps = r['pressure_safety']
        assert ps['code_mode'] == 'aiaa_s080', mt
        assert ps['proof_pressure_bar'] == pytest.approx(60.0)
        assert ps['required_burst_pressure_bar'] == pytest.approx(80.0)
        assert ps['qualification_test_pressure_bar'] is None


def test_analizor_5012c_kipi():
    from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
    d = PressureVesselAnalyzer().analyze(
        meop_bar=60.0, inner_diameter_mm=150.0, material='steel_4130',
        wall_thickness_mm=3.0, code_mode='nasa_std_5012c')
    assert d['proof_pressure_bar'] == pytest.approx(72.0)
    assert d['required_burst_pressure_bar'] == pytest.approx(90.0)
    assert d['qualification_test_pressure_bar'] == pytest.approx(90.0)
    assert d['hydrostatic_test_pressure_bar'] == d['proof_pressure_bar']
    assert d['burst_margin'] == pytest.approx(
        d['actual_burst_pressure_bar'] / 90.0)
    a = PressureVesselAnalyzer().analyze(
        meop_bar=60.0, inner_diameter_mm=150.0, material='steel_4130',
        wall_thickness_mm=3.0, code_mode='aiaa_s080')
    assert a['qualification_test_pressure_bar'] is None
    assert a['proof_pressure_bar'] == pytest.approx(90.0)


def test_ekranda_standart_adiyla_iki_dilde():
    sayfa = _oku(JS / 'i18n_pages.js')
    for k in ('burst_pressure_5012c', 'qual_pressure_5012c',
              'proof_pressure_5012c', 'mdp_closeout', 'mdp_chamber_wall',
              'mdp_liner', 'mdp_liner_reverse'):
        assert sayfa.count("'liq.msg.%s'" % k) == 2, k
    ortak = _oku(JS / 'i18n_common.js')
    for k in ('panel.safety.pBurstTip5012', 'panel.safety.pProofHydroTip5012',
              'panel.safety.pQual', 'panel.safety.pMdp',
              'panel.safety.codeLabel', 'panel.safety.code5012',
              'vessel.code5012', 'panel.vessel.burstFactor5012',
              'panel.vessel.qualTest5012'):
        assert ortak.count("'%s'" % k) == 2, k
    assert "code_mode === 'nasa_std_5012c'" in _oku(
        JS / 'panels' / 'safety_panel.js')
    assert "'nasa_std_5012c'" in _oku(JS / 'panels' / 'vessel_panel.js')
    assert "d.code !== 'nasa_std_5012c'" in _oku(SABLON / 'liquid.html')
