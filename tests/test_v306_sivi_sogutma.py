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
    # V306/SIVI-CEKET (K5_KARAR EK4 madde 3): tetik aynı, etiket MODEL
    # SINIRI (eski 'does_not_close' fiziksel iddiası kalktı).
    assert yayim['code'] == 'jacket_model_limit'
    assert js['engine_mass_estimate'] is None
    assert js['thrust_to_weight'] is None
    m = js['design_summary']['masses']
    assert m['engine_mass_kg'] is None and m['thrust_to_weight'] is None
    # V306/SIVI-CEKET-A (K5_KARAR EK7): F-1 gaz jeneratörlü, boğazı açık
    # çevrim defteri türbin payından boyutluyor -> 'design' kapsamı: kütle,
    # yapı ve besleme blokları alan alan değil BÜTÜNÜYLE bekletilir (eski
    # beklenti blok içindeki alanların None olmasıydı; blok artık yok).
    # Dış kabuğun 'withheld' hükmü devre kapsamında sınanır
    # (tests/test_v306_sivi_ceket_a.py, F-1 kademeli türevi).
    assert yayim['scope'] == 'design'
    assert 'recommendation' not in js['design_summary']
    for blok in ('component_sizing', 'feed_system', 'structural_analysis'):
        assert js[blok] is None, blok
    assert {'warn.liquid.jacket_model_limit',
            'warn.liquid.cooling_dependent_values_withheld'} <= kodlar(js)
    assert 'warn.liquid.jacket_does_not_close' not in kodlar(js)


def test_f1_model_siniri_toplu_girisle_manifold_oda_basincinin_altinda(
        client):
    # V306/SIVI-CEKET: eski 'ceket çıkışı ≤ P_c' tetiği model sınırı olarak;
    # hat kalemleri ceketten sonra bir kez düşülür (manifold).
    js = hesap(client, 'f1')
    # V306/SIVI-CEKET-A (EK7): F-1'de ısıl koruma bloğu (geometriye bağlı)
    # bekletilir; model sınırı testinin sayıları kapı bloğunun kanıtı olarak
    # yayımlanır (cooling_circuit_publication.numbers = aynı blok).
    assert js['thermal_protection'] is None
    assert 'jacket_pressure_closure' not in json.dumps(js)
    kap = js['cooling_circuit_publication']['numbers']
    assert kap['status'] == 'model_limit_exceeded'
    assert kap['injector_manifold_pressure_at_lumped_inlet_bar'] <= \
        js['chamber_pressure']
    assert math.isclose(kap['lumped_feed_inlet_pressure_bar']
                        - kap['solved_jacket_pressure_drop_bar']
                        - kap['line_items_after_jacket_bar'],
                        kap['injector_manifold_pressure_at_lumped_inlet_bar'],
                        rel_tol=1e-9)


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
    # V306/SIVI-CEKET-A (K5_KARAR EK7): F-1'de ('design' kapsamı) motor
    # itkisi de bekletilir. 3.0.6 ana model (9 Kas, SIVI-CEKET-A DEVİR 1):
    # uç adlı kütle reddini genel 'unflyable_vehicle' reddinden ÖNCE sorar;
    # ret ceket nedenini adıyla taşır (istemci flight.refusedCooling basar).
    # Araç yine KURULMAZ. Bekçi: tests/test_v306_ucus_kapi_reddi.py.
    assert js['thrust'] is None and js['engine_mass_estimate'] is None
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
    assert 'fuel pump discharge' in sm['coolant_inlet_pressure_basis']
    assert js['cooling_circuit_publication'] == {'status': 'solved'}
    assert isinstance(js['engine_mass_estimate'], float)
    assert sm['jacket_model_limit']['status'] == 'within_model_limit'


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
def test_rl10_basinc_tukenmesi_adiyla(client, monkeypatch):
    """V306/SIVI-CEKET-B ÇEVİRİSİ: L4 gövdesi (ε 61) deniz seviyesinde
    ayrılan sabit lüle olarak adlı retle döner (kalem 5); ayrılmayan ε 10
    ile ceket artık çözülüyor (kalem 4: başlangıç derinliğinde tükenmede
    derinlik büyür). Basınç tükenmesinin ADLI yolu derinlik büyütmesi
    kapatılarak (``REGEN_MARCH_SIZING_MAX_ITER`` = 0) aynı motorda sınanır."""
    from hrma.engines import liquid_rocket_engine as lre
    g = dict(_govde('L4', 'rl10-b'), nozzle_expansion_ratio=10)
    monkeypatch.setattr(lre, 'REGEN_MARCH_SIZING_MAX_ITER', 0)
    r = client.post('/calculate_liquid', json=g, headers=HEADERS)
    assert r.status_code == 200, r.get_data()[:300]
    js = r.get_json()
    assert js['cooling_circuit_publication']['code'] == \
        CIRCUIT_FAIL_PRESSURE_EXHAUSTED
    assert 'warn.liquid.coolant_pressure_exhausted' in kodlar(js)
    assert js['thrust_to_weight'] is None
    ham_metin_yok(js, 'Coolant pressure fell')


def test_rl10_l4_ayrilan_lule_reddi_ve_ayrilmayan_lulede_ceket(client):
    """V306/SIVI-CEKET-B: L4 gövdesi adlı ret; ε 10 ile ceket çözülür."""
    r = client.post('/calculate_liquid', json=_govde('L4', 'rl10-b'),
                    headers=HEADERS)
    assert r.status_code == 422
    assert r.get_json()['error_code'] == \
        'fixed_nozzle_separated_at_design_ambient'
    r = client.post('/calculate_liquid', headers=HEADERS,
                    json=dict(_govde('L4', 'rl10-b'), nozzle_expansion_ratio=10))
    assert r.status_code == 200
    assert r.get_json()['cooling_circuit_publication'] == {'status': 'solved'}


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
