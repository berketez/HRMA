# -*- coding: utf-8 -*-
"""V306/SIVI-CEKET-A — K5_KARAR EK7 ceket yayım kapısının bekçileri.

Ceketin GEÇERLİ ÇÖZÜMÜ yoksa ona doğrudan ya da dolaylı bağlı bütün sonuçlar
bekletilir (``None`` + neden kodu). Tek tetik
``LiquidRocketEngine.jacket_publication_trigger``; iki neden kodu
(model sınırı / ceket çözümü değerlendirilmedi); iki kapsam
(``cooling_circuit`` alan listesi, ``design``: açık çevrim defteri boğazı
türbin payından boyutladı). Gövdeler mühendis turunun gerçek gövdeleridir
(docs/scofield/raw/OH/V306/muhendis-turu/sivi/vakalar L4/L5) — kanıt
kapısına bağlı kalmasın diye burada yazılıdır.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from hrma.engines import liquid_rocket_engine as lre
from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADERS = {'Host': '127.0.0.1:8080'}
F1 = {
    "chamber_material": "inconel_718", "chamber_pressure": 66.53,
    "chamber_roughness": 3.2, "characteristic_length": 1.2,
    "combustion_efficiency": 97, "contraction_ratio": 4,
    "coolant_flow_percent": 100, "coolant_inlet_temp": 300,
    "cooling_type": "regenerative", "discharge_coefficient": 0.7,
    "engine_cycle": "gas_generator", "engine_life_cycles": 10,
    "film_cooling_percent": 0, "fuel_type": "rp1", "generator_gas_temp": 1000,
    "injector_pressure_drop": 13, "injector_type": "like_impinging",
    "max_burn_duration": 150, "max_wall_temp": 800, "min_throttle": 40,
    "mixture_ratio": 2.27, "nozzle_expansion_ratio": 16, "nozzle_type": "bell_80",
    "of_max": 3.2, "of_min": 2, "oxidizer_density": 1141.16,
    "oxidizer_type": "lox", "oxidizer_viscosity": 0.0001947,
    "safety_factor": 2.5, "thrust": 6672330, "turbine_expansion_ratio": 4,
    "turbine_inlet_pressure": 150, "turbopump_efficiency": 75}
RL10 = {
    "chamber_material": "cucrzr", "chamber_pressure": 32.75,
    "chamber_roughness": 3.2, "characteristic_length": 1.2,
    "combustion_efficiency": 97, "contraction_ratio": 4,
    "coolant_flow_percent": 100, "coolant_inlet_temp": 300,
    "cooling_type": "regenerative", "discharge_coefficient": 0.7,
    "engine_cycle": "expander", "engine_life_cycles": 10,
    "film_cooling_percent": 0, "fuel_density": 70.9495, "fuel_type": "lh2",
    "fuel_viscosity": 1.359e-05, "generator_gas_temp": 1000,
    "injector_elements": 216, "injector_pressure_drop": 6,
    "injector_type": "coaxial", "max_burn_duration": 700, "max_wall_temp": 800,
    "min_throttle": 40, "mixture_ratio": 5, "nozzle_expansion_ratio": 61,
    "nozzle_type": "bell_80", "of_max": 3.2, "of_min": 2,
    "oxidizer_density": 1141.16, "oxidizer_type": "lox",
    "oxidizer_viscosity": 0.0001947, "safety_factor": 2.5, "thrust": 51719,
    "turbine_expansion_ratio": 4, "turbine_inlet_pressure": 150,
    "turbopump_efficiency": 75}
#: V306/SIVI-CEKET-B: mühendis turu L2 (metan, basınç beslemeli) Pc 20 bar /
#: tank 32 bar türevi — süperkritik marş ceketin içinde doyma eğrisine
#: ulaşıyor (devrenin kendi çöküşü; sivi-ceket-b/olcum/govdeler.json).
L2_F32 = {
    "chamber_material": "cucrzr", "chamber_pressure": 20,
    "chamber_roughness": 3.2, "characteristic_length": 1.2,
    "combustion_efficiency": 97, "contraction_ratio": 4,
    "coolant_flow_percent": 100, "coolant_inlet_temp": 300,
    "cooling_type": "regenerative", "discharge_coefficient": 0.7,
    "engine_cycle": "pressure_fed", "engine_life_cycles": 10,
    "feed_pressure": 32, "film_cooling_percent": 0, "fuel_density": 422.352,
    "fuel_type": "methane", "fuel_viscosity": 0.0001169,
    "injector_elements": 18, "injector_pressure_drop": 7,
    "injector_type": "coaxial", "max_burn_duration": 18, "max_wall_temp": 800,
    "min_throttle": 40, "mixture_ratio": 3, "nozzle_expansion_ratio": 6,
    "nozzle_type": "bell_80", "of_max": 3.2, "of_min": 2,
    "oxidizer_density": 1141.16, "oxidizer_type": "lox",
    "oxidizer_viscosity": 0.0001947, "safety_factor": 2.5, "thrust": 2000}
SAYFA = dict(SAYFA_YUKLERI['liquid'])
GOVDELER = {
    'f1': F1,
    'f1_kademeli': dict(F1, engine_cycle='staged_combustion'),
    'rl10': RL10,
    'l2_f32': L2_F32,
    'gg': SAYFA,
    'gg_kalin_cidar': dict(SAYFA, chamber_wall_thickness=10,
                           chamber_material='stainless_304'),
}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


_YANIT = {}


def hesap(client, ad):
    if ad not in _YANIT:
        r = client.post('/calculate_liquid', headers=HEADERS,
                        json=dict(GOVDELER[ad], include_plots=False))
        assert r.status_code == 200, r.get_data()[:400]
        _YANIT[ad] = r.get_json()
    return _YANIT[ad]


def _kapi(js):
    return js.get('cooling_circuit_publication') or {}


# --- Kalem 1: tetik ------------------------------------------------------

def test_tetik_tek_yerde_ve_adiyla_cagrilir():
    assert callable(getattr(lre.LiquidRocketEngine,
                            'jacket_publication_trigger', None))
    kaynak = pathlib.Path(lre.__file__).read_text(encoding='utf-8')
    # Kapı tetiği yalnız tek işlevden okur (ikinci bir getattr ikilisi yok).
    gate = kaynak[kaynak.index('    def _cooling_circuit_publication_gate'):]
    gate = gate[:gate.index('\n    @staticmethod')]
    assert 'self.jacket_publication_trigger()' in gate
    assert "_cooling_circuit_failure" not in gate


def test_f1_model_siniri_neden_kodu_ve_design_kapsami(client):
    k = _kapi(hesap(client, 'f1'))
    assert k['status'] == 'not_solved'
    assert k['code'] == lre.JACKET_MODEL_LIMIT_CODE
    assert k['withheld_reason_code'] == lre.JACKET_GATE_REASON_MODEL_LIMIT
    assert k['withheld_reason'] == 'Withheld: jacket model limit'
    assert k['scope'] == lre.JACKET_GATE_SCOPE_DESIGN


def test_devre_cokusu_degerlendirilmedi_devre_kapsami(client):
    """Marş devrenin kendisinden çöktü -> 'değerlendirilmedi', devre kapsamı.

    V306/SIVI-CEKET-B ÇEVİRİSİ: bu bekçinin eski vakası RL10'du (L4 gövdesi,
    ε 61). Kalem 5'ten beri o gövde deniz seviyesinde ayrılan sabit lüle
    olarak ADLI RETLE döner (aşağıdaki bekçi); ayrılmayan ε ile aynı motorun
    ceketi artık çözülüyor (kalem 4: başlangıç derinliğinde basınç tükenmesi
    derinliği büyütür). Devre çöküşü vakası L2 Pc 20 bar / tank 32 bar
    metandır (süperkritik marş doyma eğrisine ulaşıyor).
    """
    k = _kapi(hesap(client, 'l2_f32'))
    assert k['withheld_reason_code'] == lre.JACKET_GATE_REASON_NOT_EVALUATED
    assert k['withheld_reason'] == 'Withheld: jacket solution not evaluated'
    assert k['scope'] == lre.JACKET_GATE_SCOPE_CIRCUIT


def test_rl10_l4_govdesi_ayrilan_sabit_lule_adli_ret(client):
    """V306/SIVI-CEKET-B kalem 5: RL10 L4 gövdesi (ε 61, 32,75 bar) deniz
    seviyesinde ayrılıyor -> tasarım yayımlanmaz, adlı ret."""
    r = client.post('/calculate_liquid', headers=HEADERS,
                    json=dict(RL10, include_plots=False))
    assert r.status_code == 422
    js = r.get_json()
    assert js['error_code'] == 'fixed_nozzle_separated_at_design_ambient'
    assert js['message_params']['eps'] == 61.0
    assert js['message_params']['eps_max'] < 61.0


def test_besleme_fizibilitesi_degerlendirilmedi_tek_basina_tetiklemez(client):
    js = hesap(client, 'gg')
    assert js['detailed_feed_system']['supply_feasibility']['status'] \
        == 'not_evaluated'
    assert _kapi(js) == {'status': 'solved'}
    assert isinstance(js['feed_system']['pressure_drops'][
        'pump_discharge_pressure_fuel'], float)


def test_model_zarfi_disinda_kosmayan_mars_tetiklemez(client):
    """Zarf reddiyle koşmayan marşta tek ceket sayısı beyanlı toplu zincir.

    Karar (RAPOR Kararlar 2): zarf reddi tetiğe katılırsa 5-10 mm çelik
    cidarlı sıradan gövdelerin BÜTÜN tasarımı bekletiliyordu (ölçüldü).
    Ceketin geçerli çözümü sorusu marşın çöktüğü / model sınırını aştığı
    durumdur; zarf reddi adlı uyarıyla durur.
    """
    js = hesap(client, 'gg_kalin_cidar')
    assert 'not run' in js['thermal_protection']['station_march_status']
    assert _kapi(js) == {'status': 'solved'}
    kodlar = {w['code'] for w in js['input_warnings']}
    assert 'warn.liquid.station_march_not_run' in kodlar
    assert js['feed_system']['pressure_drops']['regen_jacket_drop_status'] \
        == 'computed'


# --- Kalem 2 + 3: kapsam ve bağımsız sonuçlar -------------------------------

def test_f1_yalniz_ceketten_bagimsiz_alanlar_yayimlanir(client):
    js = hesap(client, 'f1')
    dolu = {k for k, v in js.items() if v is not None}
    assert dolu <= set(lre.JACKET_GATE_DESIGN_PUBLISHED_FIELDS), \
        sorted(dolu - set(lre.JACKET_GATE_DESIGN_PUBLISHED_FIELDS))
    for alan in ('isp_sea_level', 'isp_vacuum', 'thrust', 'thrust_vacuum',
                 'total_mass_flow', 'throat_diameter', 'feed_system',
                 'detailed_feed_system', 'turbopump_system', 'motor_geometry',
                 'engine_mass_estimate', 'altitude_performance',
                 'performance_maps', 'mass_flow_ledger', 'total_impulse'):
        assert js.get(alan) is None, alan
    assert js['chamber_pressure'] == F1['chamber_pressure']
    assert js['c_star'] > 0 and js['chamber_temperature'] > 0


def test_f1_itki_odasi_isp_si_tanimiyla_motor_isp_si_sessizce_donusmez(client):
    js = hesap(client, 'f1')
    tca = js['thrust_chamber_isp']
    assert tca['sea_level_s'] > 0 and tca['vacuum_s'] > tca['sea_level_s']
    assert 'F_TCA/(g0*mdot_TCA)' in tca['definition']
    assert 'gas-generator / turbine' in tca['definition']
    assert js['isp_sea_level'] is None and js['isp_vacuum'] is None
    # hedef itki girdi olarak, kendi adıyla
    assert js['target_thrust_input']['value_N'] == float(F1['thrust'])
    assert 'not a computed' in js['target_thrust_input']['basis']


def test_f1_eski_yanlis_sayilar_yanitta_yok(client):
    metin = json.dumps(hesap(client, 'f1'))
    for yasak in ('354.55', '265.30', '311.13', '123.91'):
        assert yasak not in metin, yasak


def test_f1_uyarilar_neden_ve_bagimsiz_kodlarla_sinirli(client):
    js = hesap(client, 'f1')
    kodlar = [w['code'] for w in js['input_warnings']]
    assert 'warn.liquid.jacket_model_limit' in kodlar
    assert 'warn.liquid.cooling_dependent_values_withheld' in kodlar
    assert set(kodlar) <= set(lre.JACKET_GATE_DESIGN_WARNING_CODES)
    # V306/ONARIM-SIVI (rc.1 CI): bekletilen ceket bağımlı uyarı örneği
    # astardır (SF 1,0217 ⟷ hedef 2,5; gerçek açık). Eski örnek
    # closeout_below_target yuvarlama gürültüsüydü: HRMA kabuğu hedefe TAM
    # boyutluyor, SF darwin'de 2,4999999999999996 (uyarı vardı), CI
    # linux'ta uyarı yoktu. Ürün düzeltmesi WALL_LAYER_SF_CLOSURE_RTOL;
    # bekçisi test_hedefe_tam_boyutlanan_katman_hukmu_platformdan_bagimsiz.
    bekletilen = _kapi(js)['withheld_warning_codes']
    assert 'warn.liquid.liner_below_target' in bekletilen
    assert 'warn.liquid.closeout_below_target' not in bekletilen


def test_hedefe_tam_boyutlanan_katman_hukmu_platformdan_bagimsiz():
    """Hedefe tam boyutlanan katmanın SF'si hedefin 1 ulp altında/üstünde
    kalabilir (ÖLÇÜLDÜ, F-1 kabuğu darwin/arm64: 2,4999999999999996);
    hüküm iki durumda da 'pass'. Gerçek açık (astar SF 1,0217) ve akma
    altı (SF < 1) hükümleri değişmez."""
    v = lre.LiquidRocketEngine._wall_layer_verdict
    hedef = 2.5
    assert v(2.4999999999999996, hedef, False) == 'pass'
    assert v(hedef, hedef, False) == 'pass'
    assert v(2.5000000000000004, hedef, False) == 'pass'
    assert v(hedef * (1.0 - 1e-9), hedef, False) == 'below_target'
    assert v(1.0217150317513075, hedef, False) == 'below_target'
    assert v(0.99, hedef, False) == 'fail'
    assert lre.WALL_LAYER_SF_CLOSURE_RTOL == 1e-12


def test_kapali_cevrimde_devre_kapsami_besleme_ve_cevrim_bekletilir(client):
    js = hesap(client, 'f1_kademeli')
    k = _kapi(js)
    assert k['scope'] == lre.JACKET_GATE_SCOPE_CIRCUIT
    pd = js['feed_system']['pressure_drops']
    assert pd['pump_discharge_pressure_fuel'] is None
    assert pd['total_fuel'] is None and pd['fuel_line']['regen_jacket'] is None
    # ceketten bağımsız oksitleyici hattı yayımlanır
    assert isinstance(pd['pump_discharge_pressure_ox'], float)
    dfs = js['detailed_feed_system']
    assert dfs['engine_cycle_solution']['status'] == 'withheld'
    assert dfs['supply_feasibility']['status'] == 'withheld'
    assert js['feed_system']['turbopump'] is None
    assert js['turbopump_system'] is None
    katman = [L for L in js['structural_analysis']['chamber_structure'][
        'wall_layers'] if L.get('role') == 'closeout'][0]
    assert katman['verdict'] == 'withheld' and katman['thickness_mm'] is None
    # kapalı çevrimde motor Isp'si ceketten bağımsız (bütün debi odadan)
    assert js['isp_sea_level'] > 0
    for yol in ('feed_system.pressure_drops.pump_discharge_pressure_fuel',
                'detailed_feed_system.engine_cycle_solution',
                'feed_system.turbopump'):
        assert yol in k['withheld_fields'], yol


def test_kapi_idempotent():
    import copy
    js = copy.deepcopy(_YANIT.get('f1_kademeli') or {})
    if not js:
        pytest.skip('önceki test yanıtı yok')
    once = json.dumps(js, sort_keys=True)
    lre.apply_jacket_publication_gate(js)
    assert json.dumps(js, sort_keys=True) == once


def test_ters_mutasyon_tetik_none_ise_f1_sayilari_yayimlanir(monkeypatch):
    """Bekçi: kapı tetiği okumazsa F-1 yanlış sayıları geri gelir."""
    from hrma.app import app
    app.config['TESTING'] = True
    monkeypatch.setattr(lre.LiquidRocketEngine, 'jacket_publication_trigger',
                        lambda self, results=None: None)
    r = app.test_client().post('/calculate_liquid', headers=HEADERS,
                               json=dict(F1, include_plots=False))
    js = r.get_json()
    assert js['feed_system']['pressure_drops'][
        'pump_discharge_pressure_fuel'] > 300.0


# --- Kalem 4: Excel "Feed system" ------------------------------------------

def test_api_hat_toplamlari_gorunen_kalemlerin_toplami(client):
    pd = hesap(client, 'gg')['feed_system']['pressure_drops']
    kal = ('tank_outlet', 'main_valve', 'filters', 'feed_lines', 'injector')
    assert abs(sum(pd['oxidizer_line'][k] for k in kal) - pd['total_ox']) \
        < 1e-9
    assert abs(sum(pd['fuel_line'][k] for k in kal + ('regen_jacket',))
               - pd['total_fuel']) < 1e-9


def _js_islev(kaynak, ad):
    i = kaynak.index('function ' + ad + '(')
    j = kaynak.index('{', i)
    derin, k, tirnak = 0, j, None
    while k < len(kaynak):
        ch = kaynak[k]
        if tirnak:
            if ch == '\\':
                k += 2
                continue
            if ch == tirnak:
                tirnak = None
        elif ch in '\'"`':
            tirnak = ch
        elif kaynak.startswith('//', k):
            k = kaynak.index('\n', k)
            continue
        elif ch == '{':
            derin += 1
        elif ch == '}':
            derin -= 1
            if derin == 0:
                bas = kaynak.rfind('\n', 0, i) + 1
                return kaynak[bas:k + 1]
        k += 1
    raise AssertionError(ad)


def _excel_sayfalari(js):
    if shutil.which('node') is None:
        pytest.skip('node yok')
    kaynak = (ROOT / 'hrma' / 'templates' / 'liquid.html').read_text(
        encoding='utf-8')
    islevler = '\n'.join(_js_islev(kaynak, ad) for ad in (
        'liqJacketGate', 'liqJacketGateScope', 'liqGateReasonText',
        'liqGateFieldText', 'exportLiquidExcel'))
    betik = """
const window = { currentResults: %s };
const T = (k, d) => d; const TF = (k, p, d) => d;
const numTxt = (v, d) => Number(v).toFixed(d);
const showWarning = () => {}, showSuccess = () => {}, showMessage = () => {};
const liquidCollectWarnings = () => [];
const _liquidMotorName = () => 'm', _liquidExportStatus = () => {};
const _triggerLiquidDownload = () => {}, _liquidSheetsToCsvBlob = () => null;
let yakalanan = null;
const fetch = async (u, o) => { yakalanan = JSON.parse(o.body);
  return { ok: true, blob: async () => null }; };
%s
exportLiquidExcel().then(() => process.stdout.write(JSON.stringify(yakalanan.sheets)));
""" % (json.dumps(js), islevler)
    # Betik argv ile değil stdin ile (tests/test_node_cagri_sozlesmesi.py).
    r = subprocess.run(['node'], input=betik, capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:800]
    return {s['name']: s['rows'] for s in json.loads(r.stdout)}


def _hat(satirlar, bas, son):
    i = [r[0] for r in satirlar].index(bas)
    j = [r[0] for r in satirlar].index(son)
    return satirlar[i + 1:j], satirlar[j]


def test_excel_her_hat_kendi_kalemleri_ve_toplami(client):
    s = _excel_sayfalari(hesap(client, 'gg'))['Feed system']
    ox, ox_top = _hat(s, 'Oxidizer line', 'Total oxidizer-side drop (bar)')
    fu, fu_top = _hat(s, 'Fuel line', 'Total fuel-side drop (bar)')
    assert 'Regenerative jacket drop (bar)' in [r[0] for r in fu]
    assert 'Regenerative jacket drop (bar)' not in [r[0] for r in ox]
    for kalemler, toplam in ((ox, ox_top), (fu, fu_top)):
        top = sum(float(r[1]) for r in kalemler)
        # kalemler ve toplam 3 ondalıkla basılır: yuvarlama payı
        assert abs(top - float(toplam[1])) <= 0.0005 * (len(kalemler) + 1)


def test_excel_bekletilen_hucre_adli_neden(client):
    s = _excel_sayfalari(hesap(client, 'f1_kademeli'))['Feed system']
    d = dict((r[0], r[1]) for r in s)
    neden = 'Withheld: jacket model limit'
    assert d['Regenerative jacket drop (bar)'] == neden
    assert d['Total fuel-side drop (bar)'] == neden
    assert d['Fuel pump discharge pressure (bar)'] == neden
    assert d['Oxidizer pump discharge pressure (bar)'] not in ('', neden)


# --- Kalem 5: doğrulama bağdaştırıcısı -------------------------------------

def test_dogrulama_kaydi_bekletilen_isp_de_cokmez():
    from hrma.validation.experiment_db import load_records
    from hrma.validation.record_adapters import adapt_record
    kayit = [r for r in load_records()
             if r.get('test_id') == 'liq-f1-sa503-1968-spec']
    if not kayit:
        pytest.skip('F-1 kaydı bu ağaçta yok')
    a = adapt_record(kayit[0])
    assert set(a['predictions']) == {'c_star'}
    assert a['withheld_predictions']['reason_code'] in (
        lre.JACKET_GATE_REASON_MODEL_LIMIT,
        lre.JACKET_GATE_REASON_NOT_EVALUATED)


# --- Rapor (PDF) -----------------------------------------------------------

def test_pdf_kapi_bolumu_yalniz_tetiklenince(client):
    from hrma.export.pdf_generator import PDFReportGenerator
    g = PDFReportGenerator()
    assert g._create_liquid_jacket_gate_section(hesap(client, 'gg')) == []
    assert g._create_liquid_jacket_gate_section(hesap(client, 'f1'))


def test_ekran_sozlugu_iki_neden_metni():
    sayfa = (ROOT / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    assert "'liq.gate.withheld_model_limit': 'Yayımlanmadı: ceket model " \
        "sınırı'" in sayfa
    assert "'liq.gate.withheld_not_evaluated': 'Yayımlanmadı: ceket " \
        "çözümü değerlendirilmedi'" in sayfa
    for anahtar in lre.JACKET_GATE_REASON_KEYS.values():
        assert len(re.findall(re.escape("'%s':" % anahtar), sayfa)) == 2
