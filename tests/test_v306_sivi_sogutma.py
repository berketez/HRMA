"""V306/SIVI-SOĞUTMA bekçisi (3 Kas 2026) — rejeneratif soğutma devresinin
çözüm durumu ve yayım kapısı.

Kalemler (docs/scofield/raw/OH/V306/ana-model/brif_02kas/SIVI_SOGUTMA.md):

* M-SIVI-24 — çözülemeyen soğutma devresinden motor kütlesi / T/W
  yayımlanmaz; RP-1 marşının giriş basıncı katman denetimiyle AYNI besleme
  bütçesi alanıdır; ceket çıkışı oda basıncını aşmıyorsa devre kapanmaz.
* M-SIVI-11 — basınç beslemeli metan ceketinin giriş basıncı kullanıcının
  besleme basıncıdır; doyma eğrisine düşen durum adıyla söylenir (ham
  CoolProp metni uyarıya girmez).
* M-SIVI-21 — RL10 ölçeğinde basınç tükenmesi adıyla (ham İngilizce değil).
* M-SIVI-22 — film soğutmanın istasyon marşına girmediği konumla beyan.
* M-SIVI-30 — TERMAL güverte ablatif sıvı motorda motorun kendi astar
  kararını taşır.

Vakalar mühendis turunun gerçek API gövdeleridir
(docs/scofield/raw/OH/V306/muhendis-turu/sivi/vakalar/L*.json).
"""
import json
import math
import pathlib

import pytest

from hrma.analysis.regen_cooling import (
    CIRCUIT_FAIL_PRESSURE_EXHAUSTED, CoolantCircuitNotSolved, RegenCooling)
from tests.support.kanit import kanit_gerekli

ROOT = pathlib.Path(__file__).resolve().parents[1]
VAKA = ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'V306' / 'muhendis-turu' \
    / 'sivi' / 'vakalar'
HEADERS = {'Host': '127.0.0.1:8080'}


def _govde(seviye, etiket):
    # Kanıt kapısı (test_kanit_atlama_kapisi): docs'suz yayın dalında atla,
    # HRMA_KANIT_ZORUNLU=1 iken HATA; okuma yalnız kapıdan geçer.
    d = json.loads(kanit_gerekli(VAKA / f'{seviye}.json').read_text(
        encoding='utf-8'))
    for r in d['istekler']:
        if r.get('yakalama_etiketi') == etiket and \
                r['uc'] == '/calculate_liquid':
            return dict(r['govde'])
    raise KeyError(etiket)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


_YANIT = {}


def hesap(client, ad):
    if ad not in _YANIT:
        if ad == 'f1':
            g = _govde('L5', 'f1-b')
        elif ad == 'rl10':
            g = _govde('L4', 'rl10-b')
        elif ad == 'l4_film5':
            g = dict(_govde('L4', 'l4d'), film_cooling_percent=5)
        elif ad.startswith('l2_'):
            pc, besleme = {'l2_pc20_f55': (20, 55),
                           'l2_pc20_f32': (20, 32)}[ad]
            g = dict(_govde('L2', 'l2f'), cooling_type='regenerative',
                     chamber_material='cucrzr', chamber_pressure=pc,
                     feed_pressure=besleme)
        elif ad == 'l1_ablatif':
            g = _govde('L1', 'l1t')
        else:
            raise KeyError(ad)
        r = client.post('/calculate_liquid', json=g, headers=HEADERS)
        assert r.status_code == 200, r.get_data()[:400]
        _YANIT[ad] = r.get_json()
    return _YANIT[ad]


def kodlar(js):
    return {w.get('code') for w in js.get('input_warnings') or []
            if isinstance(w, dict)}


def ham_metin_yok(js, *parcalar):
    for w in js.get('input_warnings') or []:
        if not isinstance(w, dict):
            continue
        metin = json.dumps(w.get('params') or {}, ensure_ascii=False)
        for p in parcalar:
            assert p not in metin, (w.get('code'), p)


# ---------------------------------------------------------------------------
# M-SIVI-24 — F-1: devre kapanmıyor, soğutmaya bağlı büyüklükler yayımlanmaz
# ---------------------------------------------------------------------------
def test_f1_cozulmeyen_devreden_kutle_ve_tw_yayimlanmaz(client):
    js = hesap(client, 'f1')
    yayim = js['cooling_circuit_publication']
    assert yayim['status'] == 'not_solved'
    assert yayim['code'] == 'does_not_close'
    assert js['engine_mass_estimate'] is None
    assert js['thrust_to_weight'] is None
    m = js['design_summary']['masses']
    assert m['engine_mass_kg'] is None and m['thrust_to_weight'] is None
    assert 'T/W=' not in js['design_summary']['recommendation']
    cm = js['component_sizing']['component_masses']
    for k in ('total_dry_mass', 'combustion_chamber', 'nozzle_assembly',
              'turbopump_assembly'):
        assert cm[k] is None, k
    assert js['component_sizing']['mass_ratios']['thrust_to_weight'] is None
    assert js['feed_system']['total_mass'] is None
    assert {'warn.liquid.jacket_does_not_close',
            'warn.liquid.cooling_dependent_values_withheld'} <= kodlar(js)
    # dış kabuk ceket basıncından boyutlanır: hüküm geri çekilir
    cs = js['structural_analysis']['chamber_structure']
    assert cs['cooling_circuit_status'] == 'not_solved'
    kabuk = [k for k in cs['wall_layers'] if k['role'] == 'closeout']
    assert kabuk and kabuk[0]['verdict'] == 'withheld'


def test_f1_ceket_cikisi_oda_basincinin_altinda(client):
    js = hesap(client, 'f1')
    sm = js['thermal_protection']['station_march']
    kap = sm['jacket_pressure_closure']
    assert kap['status'] == 'does_not_close'
    assert kap['jacket_exit_pressure_bar'] <= js['chamber_pressure']
    assert math.isclose(kap['jacket_inlet_pressure_bar']
                        - kap['solved_jacket_pressure_drop_bar'],
                        kap['jacket_exit_pressure_bar'], rel_tol=1e-9)


def test_f1_ucus_araci_motor_kutlesi_tasimaz(client):
    # V306/UÇUŞ-3 (SIVI-SOĞUTMA DEVİR): kütlesiz araç artık YAYIMLANMAZ —
    # eski bekçi HTTP 200 + engine_inert_mass None aracını kilitliyordu;
    # o araç 376 938 kg iticiyle uçabiliyordu. Uç adıyla reddeder.
    js = hesap(client, 'f1')
    r = client.post('/api/flight-vehicle', headers=HEADERS, json={
        'source': 'results', 'motor_type': 'liquid', 'motor_name': 'F1',
        'results': js})
    assert r.status_code == 422
    d = r.get_json()
    assert d['error'] == 'engine_mass_not_published'
    assert d['cause'] == 'cooling_circuit_not_solved'
    assert 'vehicle' not in d


def test_rp1_mars_girisi_katman_denetimiyle_tek_sayi(client):
    """Bir yanıtta tek ceket giriş basıncı (yayın kapısı 6)."""
    js = hesap(client, 'l4_film5')
    sm = js['thermal_protection']['station_march']
    katmanlar = js['structural_analysis']['chamber_structure']['wall_layers']
    for k in katmanlar:
        assert k['coolant_pressure_bar'] == sm['coolant_inlet_pressure_bar']
    assert 'pump_discharge_pressure_fuel' in sm['coolant_inlet_pressure_basis']
    assert js['cooling_circuit_publication'] == {'status': 'solved'}
    assert isinstance(js['engine_mass_estimate'], float)
    assert sm['jacket_pressure_closure']['status'] == 'closes'


# ---------------------------------------------------------------------------
# M-SIVI-11 — metan, basınç beslemeli: giriş = besleme basıncı
# ---------------------------------------------------------------------------
def test_metan_dusuk_pc_besleme_basinci_ceket_girisine_gider(client):
    js = hesap(client, 'l2_pc20_f55')
    sc = js['cooling_system']['regen_supercritical']
    assert isinstance(sc, dict), sc
    assert sc['inlet_pressure_bar'] == 55.0
    assert 'feed (tank) pressure you entered' in sc['inlet_pressure_basis']
    assert js['cooling_circuit_publication'] == {'status': 'solved'}
    assert 'warn.liquid.regen_march_failed' not in kodlar(js)


def test_metan_kritik_alti_besleme_adli_ret(client):
    js = hesap(client, 'l2_pc20_f32')
    assert js['cooling_circuit_publication']['code'] == \
        'coolant_reaches_saturation'
    assert 'warn.liquid.coolant_reaches_saturation' in kodlar(js)
    assert js['engine_mass_estimate'] is None
    ham_metin_yok(js, 'CoolProp', 'PropsSI', 'Saturation pressure')


# ---------------------------------------------------------------------------
# M-SIVI-21 — RL10: basınç tükenmesi adıyla, ham ileti yok
# ---------------------------------------------------------------------------
def test_rl10_basinc_tukenmesi_adiyla(client):
    js = hesap(client, 'rl10')
    assert js['cooling_circuit_publication']['code'] == \
        CIRCUIT_FAIL_PRESSURE_EXHAUSTED
    assert 'warn.liquid.coolant_pressure_exhausted' in kodlar(js)
    assert js['thrust_to_weight'] is None
    ham_metin_yok(js, 'Coolant pressure fell')


# ---------------------------------------------------------------------------
# M-SIVI-22 — film soğutma marşa girmez: konumla beyan
# ---------------------------------------------------------------------------
def test_film_marsa_girmedigi_konumla_beyan(client):
    js = hesap(client, 'l4_film5')
    fb = js['thermal_protection']['station_march']['film_cooling']
    assert fb['applied_to_station_march'] is False
    tepe = fb['peak_hot_wall_from_injector_face_mm']
    kaplanan = fb['film_covered_length_from_injector_face_mm']
    assert fb['peak_inside_film_covered_length'] is (tepe <= kaplanan)
    beklenen = ('warn.liquid.film_not_in_station_march_peak_covered'
                if tepe <= kaplanan else 'warn.liquid.film_not_in_station_march')
    assert beklenen in kodlar(js)


# ---------------------------------------------------------------------------
# regen_cooling — adlı çöküş sınıfı (eski yakalayıcılar çalışır)
# ---------------------------------------------------------------------------
def test_regen_basinc_tukenmesi_adli_istisna():
    rc = RegenCooling(chamber_pressure=50e5, chamber_temperature=3500.0,
                      gamma=1.2, molecular_weight=22.0,
                      throat_diameter=0.05, expansion_ratio=10.0,
                      coolant='rp1', coolant_mdot=3.0,
                      coolant_inlet_pressure=0.5e5, n_channels=60,
                      channel_width=1.0e-3, channel_height=1.0e-3,
                      wall_thickness=1.0e-3, wall_material='cucrzr')
    with pytest.raises(CoolantCircuitNotSolved) as hata:
        rc.solve()
    assert isinstance(hata.value, ValueError)
    assert hata.value.code == CIRCUIT_FAIL_PRESSURE_EXHAUSTED
    assert hata.value.params['inlet_pressure_Pa'] == 0.5e5


# ---------------------------------------------------------------------------
# M-SIVI-30 — TERMAL güverte: ablatif sıvı motorda korunan cidar
# ---------------------------------------------------------------------------
def test_termal_guverte_ablatif_sivi_motorda_astar(client):
    from tests.test_v301_ornek_panel import NODE, panel_kur
    if NODE is None:
        pytest.skip('node kurulu değil')
    js = hesap(client, 'l1_ablatif')
    assert js['cooling_type'] == 'ablative'
    p = panel_kur('liquid', js, ids=('thermal',))['thermal']
    assert p['payload']['wall_protection'] == 'ablative_liner'
    r = client.post('/analyze_thermal_safety', json=p['payload'],
                    headers=HEADERS)
    assert r.status_code == 200
    ta = r.get_json()['thermal_analysis']
    assert ta['chamber_liner_check']['status'] == 'applied'
    assert ta['safety_analysis']['risk_level'] != 'HIGH'
    assert ta['safety_analysis']['bare_wall_risk_level'] == 'HIGH'
