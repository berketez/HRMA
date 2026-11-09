"""V306/SIVI-CEKET bekçisi (4 Kas 2026) — ceket basınç düşümü TEK sayı.

Karar: docs/scofield/raw/OH/V306/ana-model/K5_KARAR.md EK4; brif
docs/scofield/raw/OH/V306/ana-model/brif_04kas/SIVI_CEKET.md.

* Madde 1 — marş çözüldüyse besleme bütçesinin ceket kalemi = istasyon
  marşının ΔP'si; marşın girişi = bütçenin ceket girişi (devrenin kaynak
  düğümü). CH4/LH2: giriş ⟷ ΔP sabit noktası bağıl 1e-6. RP-1: ΔP girişten
  bağımsız (tek tur).
* Madde 2 — besleme basıncı GEREKSİNİMİ yayımlanır; fizibilite yalnız
  bağımsız sınırla (girilen tank basıncı, kapalı çevrimin güç dengesi),
  yoksa adıyla 'not_evaluated'.
* Madde 3 — eski kapanma hükmü MODEL SINIRI; hat kaybı büyüdükçe model
  sınırı kolaylaşmaz.

Gövdeler sıvı sayfasının gerçek yükü (tests/support/kabul_sayfa_yukleri) ve
türevleri; F-1 mühendis turunun gerçek gövdesi (kanıt kapısı).
"""
import json
import pathlib

import pytest

from hrma.analysis.regen_cooling import RegenCooling
from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI
from tests.support.kanit import kanit_gerekli

ROOT = pathlib.Path(__file__).resolve().parents[1]
VAKA = ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'V306' / 'muhendis-turu' \
    / 'sivi' / 'vakalar'
HEADERS = {'Host': '127.0.0.1:8080'}
SAYFA = dict(SAYFA_YUKLERI['liquid'])
GOVDELER = {
    'gg': SAYFA,
    'kademeli': dict(SAYFA, engine_cycle='staged_combustion'),
    'basinc': dict(SAYFA, engine_cycle='pressure_fed', feed_pressure=90),
    'gg_lh2': dict(SAYFA, fuel_type='lh2', mixture_ratio=6.0),
    'basinc_metan': dict(SAYFA, engine_cycle='pressure_fed',
                         fuel_type='methane', mixture_ratio=3.2,
                         chamber_wall_thickness=1.0, feed_pressure=90),
}


def _govde_f1():
    d = json.loads(kanit_gerekli(VAKA / 'L5.json').read_text(
        encoding='utf-8'))
    for r in d['istekler']:
        if r.get('yakalama_etiketi') == 'f1-b' and \
                r['uc'] == '/calculate_liquid':
            return dict(r['govde'])
    raise KeyError('f1-b')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


_YANIT = {}


def hesap(client, ad):
    if ad not in _YANIT:
        g = _govde_f1() if ad == 'f1' else GOVDELER[ad]
        r = client.post('/calculate_liquid', headers=HEADERS,
                        json=dict(g, include_plots=False))
        assert r.status_code == 200, r.get_data()[:400]
        _YANIT[ad] = r.get_json()
    return _YANIT[ad]


def _pd(js):
    return js['feed_system']['pressure_drops']


# ---------------------------------------------------------------------------
# Madde 1 — tek sayı
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ad', ['gg', 'kademeli'])
def test_rp1_butce_ceket_kalemi_marsin_dp_si(client, ad):
    js = hesap(client, ad)
    pd = _pd(js)
    sm = js['thermal_protection']['station_march']
    assert pd['regen_jacket_drop_status'] == 'computed'
    # bütçe = marş (bit düzeyinde aynı sayı)
    assert pd['fuel_line']['regen_jacket'] == sm['coolant_pressure_drop_bar']
    assert js['thermal_protection']['pressure_drop_station_march_bar'] == \
        sm['coolant_pressure_drop_bar']
    # marşın girişi = bütçenin ceket girişi (kaynak düğüm)
    assert sm['coolant_inlet_pressure_bar'] == \
        pd['pump_discharge_pressure_fuel']
    # toplu kestirim farklı bir tanımdır ve bütçeye girmez
    assert js['cooling_system']['cooling_pressure_drop'] != \
        pd['fuel_line']['regen_jacket']


def test_rp1_gg_cevrim_ayni_ceket_sayisiyla_kapanir(client):
    js = hesap(client, 'gg')
    pd = _pd(js)
    cyc = js['detailed_feed_system']['engine_cycle_solution']
    assert cyc['status'] == 'converged'
    assert cyc['pump_discharge_fuel_bar'] == pytest.approx(
        pd['pump_discharge_pressure_fuel'], rel=1e-12)


def test_rp1_mars_dp_si_giris_basincindan_bagimsiz(client):
    """Tek tur gerekçesi: RP-1 özellik tablosu basınca bağlı değil."""
    js = hesap(client, 'gg')
    sm = js['thermal_protection']['station_march']
    cs = js['cooling_system']
    ortak = dict(
        chamber_pressure=js['chamber_pressure'] * 1e5,
        chamber_temperature=float(js['chamber_temperature']),
        gamma=1.2, molecular_weight=22.0,
        throat_diameter=float(js['throat_diameter']),
        exit_diameter=float(js['exit_diameter']),
        coolant='rp1', coolant_mdot=float(cs['coolant_flow_rate']),
        coolant_inlet_temp=float(cs['coolant_inlet_temperature']),
        n_channels=int(cs['cooling_channels']),
        channel_width=float(cs['channel_width_mm']) / 1e3,
        channel_height=float(cs['channel_height_mm']) / 1e3,
        wall_thickness=float(
            cs['channel_count_fit']['hot_wall_thickness_mm']) / 1e3)
    a = RegenCooling(coolant_inlet_pressure=sm['coolant_inlet_pressure_bar']
                     * 1e5, **ortak).solve()['summary']
    b = RegenCooling(coolant_inlet_pressure=3.0 * sm[
        'coolant_inlet_pressure_bar'] * 1e5, **ortak).solve()['summary']
    for k in ('total_pressure_drop_bar', 'max_wall_hot_K',
              'coolant_exit_temp_K'):
        assert a[k] == b[k], k


def test_lh2_giris_sabit_noktasi_kapanir(client):
    js = hesap(client, 'gg_lh2')
    sc = js['cooling_system']['regen_supercritical']
    fp = sc['inlet_pressure_fixed_point']
    assert fp['converged'] is True
    assert fp['relative_residual'] <= 1e-6
    assert 2 <= fp['iterations'] <= fp['max_iterations']
    pd = _pd(js)
    # bütçe = marş (aynı sayı) ve giriş = bütçenin ceket girişi (bağıl 1e-6)
    assert pd['fuel_line']['regen_jacket'] == \
        sc['summary']['total_pressure_drop_bar']
    assert sc['inlet_pressure_bar'] == pytest.approx(
        pd['pump_discharge_pressure_fuel'], rel=1e-6)
    # ilk tur toplu tahminden başlar; son turun girişi öncekinden farklı
    gecmis = fp['history']
    assert gecmis[-1]['relative_residual'] <= 1e-6 < gecmis[0][
        'relative_residual']


def test_basinc_beslemeli_metan_giris_tank_basinci(client):
    """M-SIVI-11 korunur: basınç beslemelide kaynak düğüm = girilen tank."""
    js = hesap(client, 'basinc_metan')
    sc = js['cooling_system']['regen_supercritical']
    assert sc['inlet_pressure_bar'] == 90.0
    assert sc.get('inlet_pressure_fixed_point') is None
    assert _pd(js)['fuel_line']['regen_jacket'] == \
        sc['summary']['total_pressure_drop_bar']


def test_rp1_basinc_beslemeli_giris_tank_ve_katmanlar_ayni(client):
    js = hesap(client, 'basinc')
    sm = js['thermal_protection']['station_march']
    assert sm['coolant_inlet_pressure_bar'] == 90.0
    for k in js['structural_analysis']['chamber_structure']['wall_layers']:
        assert k['coolant_pressure_bar'] == 90.0
    assert _pd(js)['fuel_line']['regen_jacket'] == \
        sm['coolant_pressure_drop_bar']


# ---------------------------------------------------------------------------
# Madde 2 — gereksinim + fizibilite
# ---------------------------------------------------------------------------
def test_gg_fizibilite_degerlendirilmedi(client):
    sf = hesap(client, 'gg')['detailed_feed_system']['supply_feasibility']
    assert sf['status'] == 'not_evaluated'
    assert sf['bound'] is None
    assert 'does not model an independent supply-pressure limit' in \
        sf['basis']
    pd = _pd(hesap(client, 'gg'))
    assert sf['requirement_fuel_bar'] == pytest.approx(
        pd['pump_discharge_pressure_fuel'], rel=1e-12)


def test_basinc_beslemeli_fizibilite_tank_basincina_bagli(client):
    js = hesap(client, 'basinc')
    sf = js['detailed_feed_system']['supply_feasibility']
    cyc = js['detailed_feed_system']['engine_cycle_solution']
    assert sf['bound'] == 'user_tank_pressure'
    assert sf['available_bar'] == 90.0
    assert sf['margin_bar'] == cyc['tank_pressure_margin_bar']
    assert sf['status'] == ('feasible' if sf['margin_bar'] >= 0
                            else 'infeasible')


def test_kademeli_fizibilite_guc_dengesine_bagli(client):
    sf = hesap(client, 'kademeli')['detailed_feed_system'][
        'supply_feasibility']
    assert sf['bound'] == 'cycle_power_balance'
    assert sf['status'] == 'feasible'


# ---------------------------------------------------------------------------
# Madde 3 — model sınırı
# ---------------------------------------------------------------------------
def test_eski_ara_hukum_ve_kapanma_iddiasi_yok(client):
    for ad in ('gg', 'f1'):
        js = hesap(client, ad)
        metin = json.dumps(js, ensure_ascii=False)
        assert 'injector_dp_reduced' not in metin
        assert 'jacket_pressure_closure' not in metin
        assert 'cannot flow into the chamber' not in metin


def test_ornek_motor_model_siniri_icinde(client):
    sm = hesap(client, 'gg')['thermal_protection']['station_march']
    ml = sm['jacket_model_limit']
    assert ml['status'] == 'within_model_limit'
    assert ml['margin_bar'] > 0.0


def test_hat_kaybi_buyuyunce_model_siniri_kolaylasmaz(client, monkeypatch):
    """Hat kalemleri ceketten sonra bir kez sayılır: büyütülen hat kaybı
    girişe eklenip manifoldda geri düşülür. Basınç beslemeli RP-1'de
    debiler hattan bağımsız: pay bit düzeyine yakın aynı kalmalı."""
    from hrma.engines import liquid_rocket_engine as lre
    js0 = hesap(client, 'basinc')
    ml0 = js0['thermal_protection']['station_march']['jacket_model_limit']
    hat0 = ml0['line_items_after_jacket_bar']
    monkeypatch.setattr(lre, 'FEED_K_MAIN_VALVE',
                        lre.FEED_K_MAIN_VALVE * 40.0)
    r = client.post('/calculate_liquid', headers=HEADERS,
                    json=dict(GOVDELER['basinc'], include_plots=False))
    assert r.status_code == 200
    ml1 = r.get_json()['thermal_protection']['station_march'][
        'jacket_model_limit']
    assert ml1['line_items_after_jacket_bar'] > hat0 + 0.3
    assert ml1['margin_bar'] <= ml0['margin_bar'] + 1e-9


def test_pdf_satiri_butcenin_ceket_kalemini_okur(client):
    from hrma.export.pdf_generator import PDFReportGenerator
    satirlar = {r[1]: r for r in PDFReportGenerator.LIQUID_THERMAL_ROWS}
    assert 'fuel_line.regen_jacket' in satirlar
    assert satirlar['fuel_line.regen_jacket'][0] == 'pd'
    etiketler = ' '.join(r[2] for r in PDFReportGenerator.LIQUID_THERMAL_ROWS)
    assert 'bulk Bartz chain' not in etiketler


# ---------------------------------------------------------------------------
# Ek kalemler (sabahki atamadan): 7 künye, 8 bafl oranı, 9 güvenlik ucu
# ---------------------------------------------------------------------------
def test_k7_calkanti_g_eff_kunyesi_dodge_1_40():
    from hrma.engines import liquid_rocket_engine as lre
    assert 'Dodge (2000) Eq. (1.40)' in lre.TANK_SLOSH_G_EFF_BASIS
    assert 'SP-8009 Table I' in lre.TANK_SLOSH_G_EFF_BASIS
    assert 'SP-106 Eq. 2.4' not in lre.TANK_SLOSH_G_EFF_BASIS


def test_k8_bafl_orani_kirpilmaz_adiyla_uyarilir(client, monkeypatch):
    """Aralık dışı w/R sessizce 1'e kırpılmaz: sönüm yok + adlı uyarı."""
    from hrma.engines import liquid_rocket_engine as lre
    monkeypatch.setattr(lre, 'TANK_BAFFLE_OUTER_D_RATIO', 2.5)
    r = client.post('/calculate_liquid', headers=HEADERS,
                    json=dict(GOVDELER['basinc'], include_plots=False))
    assert r.status_code == 200
    js = r.get_json()
    kodlar = {w.get('code') for w in js.get('input_warnings') or []}
    assert 'warn.liquid.slosh_baffle_width_out_of_range' in kodlar
    tanklar = js['propellant_tanks']
    for ad in ('oxidizer_tank', 'fuel_tank'):
        sl = tanklar[ad]['slosh']
        assert sl['baffle_basis'].startswith('not evaluated'), ad


def test_k8_hrma_halka_geometrisinde_bafl_degerlendirilir(client):
    js = hesap(client, 'basinc')
    kodlar = {w.get('code') for w in js.get('input_warnings') or []}
    assert 'warn.liquid.slosh_baffle_width_out_of_range' not in kodlar


def test_k9_guvenlik_ucu_sivi_form_araligini_okur(client):
    from hrma.validation.motor_validation import FORM_LIMITS
    from hrma.engines.liquid_rocket_engine import BURN_TIME_MAX_S
    temel = {'motor_type': 'liquid', 'chamber_pressure': 66.5,
             'propellant_mass': 376938.0, 'chamber_diameter': 1.0,
             'wall_thickness': 0.02}
    # F-1 ölçeği (7,7 MN) ve RL10 süresi (700 s) artık adlı 422 değil
    for itki, sure in ((7.7e6, 160.0), (9.0e4, 700.0)):
        r = client.post('/analyze_safety', headers=HEADERS,
                        json=dict(temel, thrust=itki, burn_time=sure))
        assert r.status_code == 200, r.get_data()[:300]
    # sıvı formun üstü: aynı kaynaktan adlı ret
    r = client.post('/analyze_safety', headers=HEADERS,
                    json=dict(temel, thrust=2.0e7, burn_time=160.0))
    assert r.status_code == 422
    alan = r.get_json()['invalid_fields'][0]
    assert alan['field'] == 'thrust'
    assert alan['accepted_range'][1] == FORM_LIMITS['liquid']['thrust'][1]
    r = client.post('/analyze_safety', headers=HEADERS,
                    json=dict(temel, thrust=9.0e4,
                              burn_time=BURN_TIME_MAX_S * 2))
    assert r.status_code == 422
    assert r.get_json()['invalid_fields'][0]['accepted_range'][1] == \
        BURN_TIME_MAX_S
    # öteki motor türleri kanonik bantta (değişmedi)
    r = client.post('/analyze_safety', headers=HEADERS,
                    json=dict(temel, motor_type='hybrid', thrust=7.7e6,
                              burn_time=160.0))
    assert r.status_code == 422
