"""V306/SIVI-CEKET-B bekçileri (9 Kas 2026).

Kalem 1 (S1): yakıt-zengin kademeli / tam akışlı kademeli / genleşmeli
çevrimde ceket girişi ⟷ çevrimin yakıt pompası ana kademe çıkışı eşli sabit
noktası; bütçe çevrim merdivenini adıyla taşır (tek pompa çıkışı).
Kalem 2 (S2): CoolProp AbstractState hızlı yolu PropsSI ile bit-aynı;
aynı girdi aynı sayı.
Kalem 3 (S1): Soğutma güvertesi motorun marş girdileriyle aynı marşı kurar.
Kalem 5 (S1): deniz seviyesinde ayrılan sabit ε adlı retle döner.
Kanıt: docs/scofield/raw/OH/V306/sivi-ceket-b/RAPOR.md.
"""
import contextlib
import copy
import io
import json
import pathlib
import re
import warnings

import pytest

from hrma.engines import liquid_rocket_engine as lre
from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAYFA = dict(SAYFA_YUKLERI['liquid'])
GOVDELER = {
    'gg': SAYFA,
    'genlesmeli_lh2': dict(SAYFA, engine_cycle='expander', fuel_type='lh2',
                           mixture_ratio=6.0),
    'tam_akis_metan': dict(SAYFA, engine_cycle='full_flow_staged',
                           fuel_type='methane', mixture_ratio=3.2),
    'kademeli_rp1': dict(SAYFA, engine_cycle='staged_combustion'),
    'kademeli_ox': dict(SAYFA, engine_cycle='staged_combustion',
                        preburner_type='ox_rich'),
}
#: Mühendis turu L3 gövdesi, ε 50 (UÇUŞ-KÜTLE DEVİR 2): 30 bar, deniz
#: seviyesinde Summerfield ölçütüyle ayrılıyor.
L3_EPS50 = {
    "fuel_type": "rp1", "oxidizer_type": "lox", "oxidizer_density": 1141.16,
    "oxidizer_viscosity": 0.0001947, "mixture_ratio": 2.4, "of_min": 2,
    "of_max": 3.2, "combustion_efficiency": 97, "engine_cycle": "pressure_fed",
    "thrust": 5000, "chamber_pressure": 30, "feed_pressure": 45,
    "injector_type": "unlike_impinging", "injector_pressure_drop": 6,
    "discharge_coefficient": 0.7, "injector_elements": 36,
    "characteristic_length": 1.2, "contraction_ratio": 4,
    "chamber_material": "steel_4130", "chamber_roughness": 3.2,
    "cooling_type": "ablative", "nozzle_expansion_ratio": 50,
    "nozzle_type": "bell_80", "coolant_flow_percent": 100,
    "film_cooling_percent": 0, "coolant_inlet_temp": 300,
    "max_wall_temp": 800, "min_throttle": 40, "max_burn_duration": 36,
    "safety_factor": 2.5, "engine_life_cycles": 10}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


_YANIT = {}


def _post(client, govde, uc='/calculate_liquid'):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = client.post(uc, json=govde)
    return r.status_code, r.get_json()


def hesap(client, ad):
    if ad not in _YANIT:
        kod, js = _post(client, dict(GOVDELER[ad], include_plots=False))
        assert kod == 200, json.dumps(js)[:400]
        _YANIT[ad] = js
    return _YANIT[ad]


# ---------------------------------------------------------------------------
# Kalem 1 — ceket ⟷ çevrim eşli sabit noktası
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ad', ['genlesmeli_lh2', 'tam_akis_metan'])
def test_mars_girisi_cevrimin_yakit_pompasi_cikisi(client, ad):
    js = hesap(client, ad)
    pd = js['feed_system']['pressure_drops']
    fp = pd['jacket_cycle_fixed_point']
    assert fp['status'] == 'converged'
    assert fp['relative_residual'] <= lre.JACKET_INLET_FIXED_POINT_REL_TOL
    assert fp['iterations'] <= lre.JACKET_INLET_FIXED_POINT_MAX_ITER
    cyc = js['detailed_feed_system']['engine_cycle_solution']
    sc = js['cooling_system']['regen_supercritical']
    # Marş girişi = çevrimin yakıt pompası çıkışı (sabit nokta toleransıyla).
    assert sc['inlet_pressure_bar'] == pytest.approx(
        cyc['pump_discharge_fuel_bar'],
        rel=lre.JACKET_INLET_FIXED_POINT_REL_TOL)
    assert sc['inlet_pressure_basis'] == lre.JACKET_CYCLE_FIXED_POINT_BASIS
    # Tek pompa çıkışı: bütçe = çevrim (aynı sayı).
    assert pd['pump_discharge_pressure_fuel'] == cyc['pump_discharge_fuel_bar']
    # Bütçe merdiveni adıyla; toplam = görünen kalemlerin toplamı.
    fl = pd['fuel_line']
    assert fl['cycle_pressure_ladder'] > 0.0
    kal = ('tank_outlet', 'main_valve', 'filters', 'feed_lines', 'injector',
           'regen_jacket', 'cycle_pressure_ladder')
    assert sum(fl[k] for k in kal) == pytest.approx(pd['total_fuel'],
                                                    abs=1e-9)
    assert pd['cycle_pressure_ladder_basis'] == lre.JACKET_CYCLE_LADDER_BASIS
    # Çevrim marşın ΔP'siyle çözüldü (tek ceket sayısı).
    assert fl['regen_jacket'] == js['cooling_system']['cooling_pressure_drop']


def test_kademeli_rp1_istasyon_marsi_girisi_cevrimden(client):
    """RP-1: marş ΔP'si girişten bağımsız; giriş yine çevrimin pompasıdır."""
    js = hesap(client, 'kademeli_rp1')
    pd = js['feed_system']['pressure_drops']
    cyc = js['detailed_feed_system']['engine_cycle_solution']
    sm = js['thermal_protection']['station_march']
    assert sm['coolant_inlet_pressure_bar'] == cyc['pump_discharge_fuel_bar']
    assert sm['coolant_inlet_pressure_basis'] == \
        lre.JACKET_CYCLE_FIXED_POINT_BASIS
    assert pd['pump_discharge_pressure_fuel'] == cyc['pump_discharge_fuel_bar']
    assert pd['jacket_cycle_fixed_point']['status'] == 'converged'


@pytest.mark.parametrize('ad', ['gg', 'kademeli_ox'])
def test_eslenmeyen_cevrimde_blok_yok(client, ad):
    """GG ve oksitleyici-zengin kademeli: eşleme yok, yanıt eski yoldan."""
    pd = hesap(client, ad)['feed_system']['pressure_drops']
    assert 'jacket_cycle_fixed_point' not in pd
    assert 'cycle_pressure_ladder' not in pd['fuel_line']


def test_yakinsamazsa_adli_kayit_ve_kapi(client, monkeypatch):
    """Eşli döngü kapanmazsa sessiz son tur yok: kayıt + kritik uyarı +
    SIVI-CEKET-A tetiği (devre kapsamı, 'değerlendirilmedi')."""
    monkeypatch.setattr(lre, 'JACKET_INLET_FIXED_POINT_MAX_ITER', 1)
    kod, js = _post(client, dict(GOVDELER['genlesmeli_lh2'],
                                 include_plots=False))
    assert kod == 200
    kapi = js['cooling_circuit_publication']
    assert kapi['withheld_reason_code'] == lre.JACKET_GATE_REASON_NOT_EVALUATED
    assert kapi['code'] == lre.JACKET_CYCLE_NOT_CONVERGED_CODE
    kodlar = {w['code'] for w in js['input_warnings']}
    assert 'warn.liquid.jacket_cycle_not_converged' in kodlar
    pd = js['feed_system']['pressure_drops']
    assert pd['pump_discharge_pressure_fuel'] is None
    # Merdiven yalnız kapanmış eşli çözümde kurulur; kayıt kapıyla bekletilir.
    assert pd['fuel_line'].get('cycle_pressure_ladder') is None
    assert pd['jacket_cycle_fixed_point'] is None


# ---------------------------------------------------------------------------
# Kalem 2 — CoolProp hızlı yolu
# ---------------------------------------------------------------------------
def test_coolprop_hizli_yol_propssi_ile_bit_ayni():
    pytest.importorskip('CoolProp')
    from CoolProp.CoolProp import PropsSI
    from hrma.analysis import regen_cooling as rc
    for akiskan, noktalar in (
            ('ParaHydrogen', [(30.0, 80e5), (250.0, 120e5), (900.0, 200e5)]),
            ('Methane', [(120.0, 60e5), (400.0, 90e5), (800.0, 300e5)])):
        nesne = object.__new__(rc.RegenCooling)
        nesne._cp_fluid = akiskan
        for t, p in noktalar:
            for cikti in ('D', 'C', 'L', 'V', 'Hmass'):
                assert nesne._cp_call(cikti, 'T', t, 'P', p) == float(
                    PropsSI(cikti, 'T', t, 'P', p, akiskan))
            h = float(PropsSI('Hmass', 'T', t, 'P', p, akiskan))
            for cikti in ('T', 'D'):
                assert nesne._cp_call(cikti, 'P', p, 'Hmass', h) == float(
                    PropsSI(cikti, 'P', p, 'Hmass', h, akiskan))


def test_ayni_girdi_ayni_sayi(client):
    """Belirlenimcilik: aynı gövde iki kez → aynı yanıt (süperkritik eşli)."""
    a = _post(client, dict(GOVDELER['genlesmeli_lh2'], include_plots=False))[1]
    b = _post(client, dict(GOVDELER['genlesmeli_lh2'], include_plots=False))[1]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------------------
# Kalem 3 — Soğutma güvertesi ⟷ motor
# ---------------------------------------------------------------------------
def _guverte_govdesi(js):
    """cooling_panel.js fromResults + contextFromResults (march_inputs)."""
    cs = js['cooling_system']
    sc = cs.get('regen_supercritical')
    sm = (js.get('thermal_protection') or {}).get('station_march') or {}
    mi = (sc.get('march_inputs') if isinstance(sc, dict) else None) \
        or sm.get('march_inputs')
    assert isinstance(mi, dict)
    g = {'chamber_pressure': mi['chamber_pressure'] * 1e-5,
         'chamber_temperature': mi['chamber_temperature'],
         'throat_diameter': mi['throat_diameter'],
         'gamma': mi['gamma'], 'molecular_weight': mi['molecular_weight'],
         'coolant': js['fuel_type'], 'coolant_mdot': mi['coolant_mdot'],
         'coolant_inlet_temp': mi['coolant_inlet_temp'],
         'coolant_inlet_pressure': mi['coolant_inlet_pressure'] * 1e-5,
         'n_channels': mi['n_channels'],
         'channel_width': mi['channel_width'] * 1e3,
         'channel_height': mi['channel_height'] * 1e3,
         'wall_thickness': mi['wall_thickness'] * 1e3,
         'wall_material': mi['wall_material'],
         'flow_direction': 'counterflow', 'engine_march': mi}
    if 'expansion_ratio' in mi:
        g['expansion_ratio'] = mi['expansion_ratio']
    else:
        g['expansion_ratio'] = (mi['exit_diameter'] / mi['throat_diameter']) \
            * (mi['exit_diameter'] / mi['throat_diameter'])
    return g


@pytest.mark.parametrize('ad', ['gg', 'genlesmeli_lh2'])
def test_guverte_motorla_bit_ayni(client, ad):
    js = hesap(client, ad)
    kod, g = _post(client, _guverte_govdesi(js), '/api/regen-cooling')
    assert kod == 200, g
    assert g['engine_march_comparison']['status'] == 'same_inputs'
    assert g['engine_march_comparison']['changed_fields'] == []
    dp = g['cooling']['summary']['total_pressure_drop_bar']
    assert dp == js['feed_system']['pressure_drops']['fuel_line'][
        'regen_jacket']


def test_guvertede_degisen_girdi_adiyla(client):
    js = hesap(client, 'gg')
    govde = _guverte_govdesi(js)
    govde['channel_height'] = govde['channel_height'] * 1.1
    kod, g = _post(client, govde, '/api/regen-cooling')
    assert kod == 200
    k = g['engine_march_comparison']
    assert k['status'] == 'inputs_changed'
    assert [d['field'] for d in k['changed_fields']] == ['channel_height']
    assert g['cooling']['summary']['total_pressure_drop_bar'] != \
        js['feed_system']['pressure_drops']['fuel_line']['regen_jacket']


def test_guverte_motor_marsi_bilinmeyen_alan_adli_ret(client):
    js = hesap(client, 'gg')
    govde = _guverte_govdesi(js)
    govde['engine_march'] = dict(govde['engine_march'], kotu_alan=1)
    kod, g = _post(client, govde, '/api/regen-cooling')
    assert kod == 400
    assert 'kotu_alan' in g['error']


def test_guverte_baglamsiz_yanit_karsilastirma_tasimaz(client):
    js = hesap(client, 'gg')
    govde = _guverte_govdesi(js)
    govde.pop('engine_march')
    kod, g = _post(client, govde, '/api/regen-cooling')
    assert kod == 200
    assert 'engine_march_comparison' not in g


def test_panel_baglami_motor_marsi_girdileri():
    kaynak = (ROOT / 'hrma' / 'static' / 'js' / 'panels'
              / 'cooling_panel.js').read_text(encoding='utf-8')
    assert 'contextFromResults: function (r)' in kaynak
    assert 'engine_march: mi' in kaynak
    assert "T('panel.regen.jdpSame'" in kaynak
    assert "U.tf('panel.regen.jdpChanged'" in kaynak


# ---------------------------------------------------------------------------
# Kalem 5 — deniz seviyesinde ayrılan sabit ε
# ---------------------------------------------------------------------------
def test_ayrilan_sabit_lule_adli_ret(client):
    kod, js = _post(client, dict(L3_EPS50, include_plots=False))
    assert kod == 422
    assert js['error_code'] == lre.FIXED_NOZZLE_SEPARATED_CODE
    assert js['message_key'] == 'err.liquid.fixed_nozzle_separated'
    p = js['message_params']
    assert p['eps'] == 50.0 and p['pc_bar'] == 30.0
    assert p['pe_bar'] < p['sep_bar']
    assert p['eps_max'] == pytest.approx(10.35, abs=0.005)
    assert 'HTTP' not in js['message'] and '422' not in js['message']
    # Tasarım sayısı yayımlanmaz.
    for alan in ('thrust', 'isp_sea_level', 'total_mass_flow',
                 'engine_mass_estimate'):
        assert alan not in js


def test_ayrilmayan_en_buyuk_eps_yayimlanir(client):
    kod, js = _post(client, dict(L3_EPS50, include_plots=False,
                                 nozzle_expansion_ratio=10.35))
    assert kod == 200
    assert 'warn.liquid.flow_separation' not in {
        w['code'] for w in js['input_warnings']}


def test_ret_metni_en_tr_sozlukte():
    kaynak = (ROOT / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    for anahtar in ('err.liquid.fixed_nozzle_separated',
                    'err.liquid.fixed_nozzle_separated_no_max',
                    'warn.liquid.jacket_cycle_not_converged',
                    'panel.regen.jdpSame', 'panel.regen.jdpChanged'):
        assert len(re.findall(r"'" + re.escape(anahtar) + r"':", kaynak)) \
            == 2, anahtar
    # Excel satır etiketi sayfa sözlüğünde (liquid.html anahtarları orada).
    sayfa = (ROOT / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    assert len(re.findall(r"'liq\.cyc\.pressure_ladder_bar':", sayfa)) == 2
