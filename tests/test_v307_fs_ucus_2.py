"""V307/FS-UÇUŞ-2 — Fırlatma Sahası: kaynaklı kanat kuralı, eşik künyesi,
paraşütlü iniş, yanma sonu tek tanımı, .hrma dosyasından içe aktarma.

ÖLÇÜLDÜ (docs/scofield/raw/OH/V307/fs-ucus-2/olcum/ucus_once.json, taban
c337a5765): sayfa kanadı gövdeden bağımsız sabit gönderiyordu (kök 0,20 /
uç 0,10 / ok 0,08 m, açıklık 0,11 m); örnek sıvı (Ø0,473 m) ve hibrit
(Ø0,212 m) araçta statik marj −1,86 / 0,45 kalibre → "araç kararsız —
oynatma kapalı", iniş çözülmüyordu.

Bekçiler:
  * kural: üç örnek araç (dosyadan içe aktarılmış GERÇEK araçlar) kanat
    alanları boşken kararlı uçar, iniş çözülür; her alan kaynağıyla; açıklık
    en küçük (bir adım eksiği ölçütü sağlamaz); verilen alan aynen kalır;
    kural sağlanamazsa / kök veteri sığmazsa adlı ret; kural istenmezse
    yanıt değişmez.
  * eşik: künye Niskanen 2013 §2.4 s. 12; çözücü eşiğiyle tek tanım.
  * paraşüt: düzlemsel çözücüyle AYNI sabitler ve AYNI sonuç (gecikme 0,
    dikey düşüş: iniş süresi/hızı bağıl 1e-3); uç terminal hıza yakınsar;
    girdi kapısı adlı 422.
  * yanma sonu: olay = çözücünün t_burn'ü = uçan itki girdisinin sonu.
  * içe aktarma: dosya ⟷ kayıtlı proje aracı aynı; saldırgan dosyalar 4xx.
  * D2: Coriolis iniş noktasını gerçekten kaydırır; not "modellenmiyor" demez.
  * sayfa (statik) + tarayıcı (WebGL kapalı): örnek araç kuralla kararlı uçar,
    kanat künyesi kaynağıyla ekranda.
"""
import importlib.util
import json
import math
import pathlib
import re

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
SOZLUK = KOK / 'hrma' / 'static' / 'js' / 'i18n_launch_site.js'
ORNEKLER = KOK / 'examples'
ORNEK_DOSYA = {
    'solid': 'Example Solid KNDX BATES 75mm.hrma',
    'liquid': 'Example Liquid LOX-RP1 25kN.hrma',
    'hybrid': 'Example Hybrid N2O-HTPB 3kN.hrma',
}
#: Gövde kuru kütlesi kullanıcı girdisidir (türetilmez); ölçümün girdisi.
GOVDE_KURU_KG = {'solid': 4.0, 'liquid': 60.0, 'hybrid': 10.0}
SAHA = {'latitude_deg': 28.6084, 'longitude_deg': -80.6043}
BURUN_M = 0.5


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def araclar(istemci):
    """Üç örnek motor, .hrma DOSYASINDAN içe aktarılmış uçan araç (A3 yolu)."""
    out = {}
    for mt, dosya in ORNEK_DOSYA.items():
        y = istemci.post('/api/flight-vehicle', json={
            'source': 'file', 'file_name': dosya,
            'document_text': (ORNEKLER / dosya).read_text(encoding='utf-8')})
        assert y.status_code == 200, (mt, y.get_json())
        out[mt] = y.get_json()['vehicle']
    return out


def sayfa_govdesi(veh, kuru, **ek):
    """launch_site.html "Fly this site" gövdesinin aynısı (kanat alanları boş)."""
    ft = veh.get('flight_thrust') or {}
    kalan = ft.get('propellant_residual_kg') or 0.0
    g = veh['airframe_resolved']
    L = g.get('body_length_m') or (BURUN_M + g['length_behind_nose_m'])
    body = {
        'body_diameter': float('%.3f' % g['body_diameter_m']),
        'body_length': float('%.2f' % L),
        'nose_length': BURUN_M, 'nose_type': 'ogive',
        'dry_mass': kuru + veh['engine_inert_mass'] + kalan,
        'propellant_mass': ft.get('propellant_consumed_kg') or veh['propellant_mass'],
        'thrust': veh['thrust'], 'burn_time': veh['burn_time'],
        'cd0': 0.45, 'fin_count': 4, 'fin_geometry_rule': 'static_margin',
        'launch_elevation_deg': 84, 'launch_azimuth_deg': 90, 'rail_length': 5,
        'wind_speed': 0, 'wind_direction_deg': 270, 't_max': 400,
        'descent_model': 'ballistic',
        'engine_od_m': veh.get('engine_od_m'), 'engine_length_m': veh.get('engine_length_m'),
    }
    body.update(SAHA)
    for a in ('nozzle_exit_area_m2', 'thrust_reference_pressure_pa'):
        if ft.get(a) is not None:
            body[{'nozzle_exit_area_m2': 'nozzle_exit_area',
                  'thrust_reference_pressure_pa': 'thrust_reference_pressure'}[a]] = ft[a]
    if veh.get('thrust_curve') and veh['thrust_curve'].get('time'):
        body['thrust_curve'] = veh['thrust_curve']
    body.update(ek)
    return {k: v for k, v in body.items() if v is not None}


@pytest.fixture(scope='module')
def kural_ucuslari(istemci, araclar):
    out = {}
    for mt, veh in araclar.items():
        y = istemci.post('/api/six-dof-analysis',
                         json=sayfa_govdesi(veh, GOVDE_KURU_KG[mt]))
        out[mt] = (y.status_code, y.get_json())
    return out


# ------------------------------------------------------------- A1 kanat kuralı
@pytest.mark.parametrize('mt', ['solid', 'liquid', 'hybrid'])
def test_ornek_araclar_kuralla_kararli_ucar(kural_ucuslari, mt):
    durum, d = kural_ucuslari[mt]
    assert durum == 200, d
    sm = d['summary']
    assert sm['stable'] is True and sm['end_reason'] == 'apogee', sm
    assert sm['flight_verdict']['stability'] == 'stable'
    fg = d['fin_geometry']
    alanlar = fg['fields']
    assert alanlar['fin_count']['source'] == 'supplied'
    for a in ('fin_root_chord', 'fin_tip_chord', 'fin_sweep'):
        assert alanlar[a]['source'] == 'rule_planform', a
    assert alanlar['fin_span']['source'] == 'rule_static_margin'
    assert fg['status'] == 'sized'
    assert fg['criterion_met_over_mach_range'] is True
    assert fg['min_margin_over_mach_range_cal'] > 1.0
    # Kanat HEDEFİ (ana model kararı 16 Kas): bandın ortası 1,5 kalibre;
    # 4·d içinde sağlanamazsa eşik (1,0) kullanılır ve adıyla yazılır.
    kr = fg['criterion']
    assert kr['target_cal'] == 1.5 and kr['threshold_cal'] == 1.0
    if mt == 'liquid':
        # Mach 4,26: Barrowman süpersonik düzeltmesiyle 4·d içinde 1,5 yok.
        assert kr['target_met'] is False and kr['target_used_cal'] == 1.0
        assert fg['target_met_over_mach_range'] is False
    else:
        assert kr['target_met'] is True and kr['target_used_cal'] == 1.5
        assert fg['min_margin_over_mach_range_cal'] >= 1.5
        assert fg['target_met_over_mach_range'] is True
    # Yayımlanan marj = çözücünün Mach 0 marjı (tek sayı).
    assert fg['margin_full_cal'] == pytest.approx(sm['static_margin_full'], rel=1e-12)
    assert d['track']['descent']['status'] == 'solved'
    assert 'fin_sizing' not in d          # kararlı araçta öneri yok
    # Kuralın uçuşları Mach aralığını kapsar.
    son = fg['sizing']['flights'][-1]
    assert son['flight_max_mach'] <= fg['sizing']['mach_range_max'] + 1e-9 \
        or son['sized_for_mach_max'] >= son['flight_max_mach'] - 1e-9


def test_planform_kurali_ornek_kanattan_olceklenir(kural_ucuslari, araclar):
    from hrma.analysis import launch_site_flight as lsf
    from hrma.analysis.flight_vehicle import EXAMPLE_VEHICLE
    d0 = EXAMPLE_VEHICLE['airframe_resolved']['body_diameter_m']
    p = lsf.EXAMPLE_FIN_PLANFORM_M
    _, d = kural_ucuslari['liquid']
    D = d['fin_geometry']['fields']
    govde = sayfa_govdesi(araclar['liquid'], 60.0)['body_diameter']
    assert D['fin_root_chord']['value'] == pytest.approx(p['fin_root_chord'] / d0 * govde, rel=1e-12)
    assert D['fin_tip_chord']['value'] == pytest.approx(
        D['fin_root_chord']['value'] * p['fin_tip_chord'] / p['fin_root_chord'], rel=1e-12)
    assert D['fin_sweep']['value'] == pytest.approx(
        D['fin_root_chord']['value'] * p['fin_sweep'] / p['fin_root_chord'], rel=1e-12)
    # Örnek aracın kendi gövdesinde kural örnek kanadı AYNEN verir.
    pl = lsf.fin_planform_by_rule(d0)
    for k, v in p.items():
        assert pl[k][0] == pytest.approx(v, rel=1e-12)


def test_aciklik_en_kucuk(kural_ucuslari, araclar):
    """Ölçüt kuralın açıklığında tutar, bir çözünürlük adımı eksikte tutmaz."""
    from hrma.analysis import launch_site_flight as lsf
    from hrma.analysis.six_dof_trajectory import (
        BarrowmanAero, CG_ASSUMED_EMPTY_FRACTION, CG_ASSUMED_FULL_FRACTION)
    for mt in ('liquid', 'hybrid'):
        _, d = kural_ucuslari[mt]
        f = d['fin_geometry']['fields']
        g = sayfa_govdesi(araclar[mt], GOVDE_KURU_KG[mt])
        L = g['body_length']
        args = dict(body_diameter=g['body_diameter'], nose_length=BURUN_M,
                    body_length=L, nose_type='ogive', fin_count=4,
                    fin_root_chord=f['fin_root_chord']['value'],
                    fin_tip_chord=f['fin_tip_chord']['value'],
                    fin_sweep=f['fin_sweep']['value'], fin_position=None)
        xf, xe = CG_ASSUMED_FULL_FRACTION * L, CG_ASSUMED_EMPTY_FRACTION * L
        _mm, machlar = lsf._mach_izgarasi(d['fin_geometry']['sizing']['mach_range_max'])
        acik = f['fin_span']['value']
        kr = d['fin_geometry']['criterion']
        hedefte = kr['target_met'] is True
        tut = lambda a, e=kr['target_used_cal'], k=hedefte: lsf._marj_tutar(
            BarrowmanAero(**dict(args, fin_span=a)), xf, xe, machlar, e, esit_kabul=k)
        assert tut(acik), mt
        assert not tut(round(acik - lsf.FIN_SPAN_SEARCH_STEP_M, 6)), mt
        if not hedefte:
            # Düşüş gerçek: hedef, aramanın üst sınırında (4·d) bile tutmuyor.
            ust = lsf.FIN_SPAN_SEARCH_MAX_CALIBERS * g['body_diameter']
            assert not tut(ust, lsf.FIN_TARGET_MARGIN_CAL, True), mt


def test_verilen_kanat_alani_aynen_kalir(istemci, araclar):
    g = sayfa_govdesi(araclar['hybrid'], 10.0, fin_root_chord=0.3)
    y = istemci.post('/api/six-dof-analysis', json=g)
    assert y.status_code == 200
    f = y.get_json()['fin_geometry']['fields']
    assert f['fin_root_chord'] == {'value': 0.3, 'unit': 'm', 'source': 'supplied'}
    # Eksik veterler verilen kökten (örnek oranları).
    assert f['fin_tip_chord']['value'] == pytest.approx(0.15, rel=1e-12)
    assert f['fin_tip_chord']['source'] == 'rule_planform'


def test_kullanici_acikligi_kararsizsa_neden_ve_oneri(istemci, araclar):
    g = sayfa_govdesi(araclar['liquid'], 60.0, fin_span=0.05)
    y = istemci.post('/api/six-dof-analysis', json=g)
    d = y.get_json()
    assert y.status_code == 200
    assert d['fin_geometry']['fields']['fin_span'] == {
        'value': 0.05, 'unit': 'm', 'source': 'supplied'}
    assert d['summary']['stable'] is False
    assert d['summary']['flight_verdict']['stability'] == 'static_margin_at_or_below_1_cal'
    assert d['fin_geometry']['criterion_met_over_mach_range'] is False
    assert d['fin_sizing']['min_fin_span_m'] > 0.05     # önerinin kendisi (FS-UÇUŞ)
    assert d['track']['descent']['reason'] == 'vehicle_not_statically_stable'


def test_kural_saglanamazsa_adli_ret(istemci, araclar):
    g = sayfa_govdesi(araclar['liquid'], 60.0, fin_root_chord=0.001, fin_tip_chord=0.0)
    y = istemci.post('/api/six-dof-analysis', json=g)
    d = y.get_json()
    assert y.status_code == 422 and d['error'] == 'fin_rule_not_met', d
    assert d['invalid_fields'][0]['field'] == 'fin_span'
    assert 'series' not in d


def test_kural_koku_govdeye_sigmazsa_adli_ret(istemci):
    g = {'body_diameter': 0.473, 'body_length': 0.9, 'nose_length': 0.5,
         'dry_mass': 50, 'propellant_mass': 20, 'thrust': 5000, 'burn_time': 5,
         'fin_count': 4, 'fin_geometry_rule': 'static_margin'}
    y = istemci.post('/api/six-dof-analysis', json=g)
    d = y.get_json()
    assert y.status_code == 422 and d['error'] == 'fin_rule_root_chord_does_not_fit', d
    f = d['invalid_fields'][0]
    assert f['field'] == 'fin_root_chord' and f['root_chord_m'] > f['available_m']


def test_taninmayan_kural_ve_kanatsiz_govde(istemci, araclar):
    g = sayfa_govdesi(araclar['solid'], 4.0, fin_geometry_rule='typical')
    y = istemci.post('/api/six-dof-analysis', json=g)
    assert y.status_code == 422
    assert y.get_json()['invalid_fields'] == [{'field': 'fin_geometry_rule',
                                               'reason': 'not_in_allowed_set'}]
    # Kanat sayısı 0: boyutlandırılacak kanat yok, kanatsız uçar (adıyla).
    y = istemci.post('/api/six-dof-analysis',
                     json=sayfa_govdesi(araclar['solid'], 4.0, fin_count=0))
    d = y.get_json()
    assert y.status_code == 200
    assert d['fin_geometry']['fields']['fin_span']['source'] == 'no_fins'
    # Kanatsız gövde takla atar: hüküm çözücünün (uçuş 'tumble').
    assert d['summary']['stable'] is not True
    assert d['summary']['flight_verdict']['flight'] == 'tumble'


def test_kural_istenmezse_yanit_ayni(istemci, araclar):
    """Bütün kanat alanları verilince kural hiçbir şeyi değiştirmez; kural
    alanı hiç gönderilmezse (motor sayfası 6-DOF paneli) blok da yok."""
    g = sayfa_govdesi(araclar['solid'], 4.0, fin_root_chord=0.2, fin_tip_chord=0.1,
                      fin_sweep=0.08, fin_span=0.11)
    y1 = istemci.post('/api/six-dof-analysis', json=g).get_json()
    g2 = dict(g)
    g2.pop('fin_geometry_rule')
    y2 = istemci.post('/api/six-dof-analysis', json=g2).get_json()
    assert 'fin_geometry' not in y2
    assert y1['summary'] == y2['summary']
    assert y1['series'] == y2['series']
    assert {a['source'] for a in y1['fin_geometry']['fields'].values()} == {'supplied'}


def test_hedef_sabiti_tek_yer_ve_hukum_esigi_degismedi(istemci, araclar):
    """Hedef bandın ortası (tek adlı sabit); kararlılık HÜKMÜ hâlâ 1 kalibre:
    marjı 1 ile 1,5 arasında olan kullanıcı kanadı 'kararlı' sayılır, öneri yok."""
    from hrma.analysis import launch_site_flight as lsf
    from hrma.analysis.six_dof_trajectory import STATIC_MARGIN_MIN_CAL
    assert lsf.FIN_TARGET_MARGIN_CAL == pytest.approx(sum(lsf.STATIC_MARGIN_BAND_CAL) / 2.0)
    assert STATIC_MARGIN_MIN_CAL == 1.0
    kaynak = (KOK / 'hrma' / 'analysis' / 'launch_site_flight.py').read_text(encoding='utf-8')
    assert len(re.findall(r'^FIN_TARGET_MARGIN_CAL\s*=', kaynak, re.M)) == 1
    assert 'HRMA choice' in lsf.FIN_TARGET_BASIS and 'section 2.4' in lsf.FIN_TARGET_BASIS
    # Hibrit: eşik ile hedef arasında kalan açıklık (0,160 m) → kararlı, öneri yok.
    # V307/UÇUŞ-GÖVDE: türetilmiş gövde N₂O tankının DIŞ çapını taşıyor
    # (Ø0,212 → 0,218 m); eski 0,140 m açıklık bu gövdede eşiğin altında
    # kalıyor (ölçülen en düşük marj 0,948), 0,160 m 1,269 veriyor.
    g = sayfa_govdesi(araclar['hybrid'], 10.0, fin_span=0.16)
    d = istemci.post('/api/six-dof-analysis', json=g).get_json()
    fg = d['fin_geometry']
    assert 1.0 < fg['min_margin_over_mach_range_cal'] < 1.5, fg['min_margin_over_mach_range_cal']
    assert d['summary']['stable'] is True and 'fin_sizing' not in d
    assert fg['criterion_met_over_mach_range'] is True
    assert fg['target_met_over_mach_range'] is False


# ------------------------------------------------------------- A2 eşik künyesi
def test_esik_kunyesi_ve_tek_tanim():
    from hrma.analysis import launch_site_flight as lsf
    from hrma.analysis.six_dof_trajectory import STATIC_MARGIN_MIN_CAL
    assert lsf.STATIC_MARGIN_BAND_CAL[0] is STATIC_MARGIN_MIN_CAL or \
        lsf.STATIC_MARGIN_BAND_CAL[0] == STATIC_MARGIN_MIN_CAL
    k = lsf.STATIC_MARGIN_SOURCE
    for parca in ('Niskanen', 'OpenRocket technical documentation', '2013',
                  'section 2.4', 'p. 12', '1-2 calibers'):
        assert parca in k, parca
    assert k in lsf.FIN_SPAN_RULE_BASIS
    kaynak = (KOK / 'hrma' / 'analysis' / 'six_dof_trajectory.py').read_text(encoding='utf-8')
    assert "birincil kaynak\n#: HRMA'da yazılı değil" not in kaynak
    assert 'Niskanen, OpenRocket tech. doc. 2013' in kaynak


# ------------------------------------------------------------- A4 paraşüt
def test_parasut_ayni_sabitler():
    from hrma.analysis import launch_site_flight as lsf
    from hrma.analysis import trajectory_analysis as ta
    assert lsf.DEFAULT_PARACHUTE_CD is ta.DEFAULT_PARACHUTE_CD
    assert lsf.DEFAULT_PARACHUTE_DEPLOY_DELAY_S is ta.DEFAULT_PARACHUTE_DEPLOY_DELAY_S
    assert lsf.DESCENT_TIME_LIMIT_S is ta.DESCENT_TIME_LIMIT_S
    r = lsf.recovery_inputs(2.0)
    assert r['cd'] == ta.DEFAULT_PARACHUTE_CD and r['assumed'] == {'cd': True, 'deploy_delay': True}


def test_parasutlu_inis_duzlemsel_cozucuyle_ayni():
    """Aynı apoje durumu, aynı alan/Cd, gecikme 0, rüzgârsız, dikey düşüş:
    6-DOF Fırlatma Sahası inişi ⟷ düzlemsel çözücünün inişi."""
    import numpy as np
    from hrma.analysis import launch_site_flight as lsf
    from hrma.analysis.six_dof_trajectory import BarrowmanAero, SixDOFTrajectory
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    aero = BarrowmanAero(body_diameter=0.15, nose_length=0.5, body_length=3.0,
                         fin_count=4, fin_root_chord=0.2, fin_tip_chord=0.1,
                         fin_span=0.11, fin_sweep=0.08)
    s = SixDOFTrajectory(aero=aero, dry_mass=25.0, propellant_mass=18.0,
                         thrust=6500.0, burn_time=7.5, cd0=0.45, wind_speed=0.0,
                         launch_elevation_deg=90.0, rail_length=5.0)
    res = s.solve(t_max=400)
    assert res['end_reason'] == 'apogee' and res['stable'] is True
    kurt = lsf.recovery_inputs(3.0, 1.4, 0.0)
    ini = lsf.descent_flight(s, res, kurt)
    assert ini['status'] == 'solved' and ini['recovery']['deployed'] is True
    h = float(res['altitude'][-1])
    m = float(s._mass_at(float(res['time'][-1])))
    ta = TrajectoryAnalyzer()
    ta.set_recovery_parameters(parachute_area=3.0, parachute_cd=1.4, deploy_delay=0.0)
    v = np.asarray(res['velocity'])[:, -1]
    dz = ta._calculate_descent_flight([0.0, h, 0.0, float(v[2]), m],
                                      float(aero.S_ref), (0.0, 0.0), 0.0)
    assert dz['landed']
    t6 = ini['impact']['t_s'] - float(res['time'][-1])
    assert t6 == pytest.approx(dz['landing_time'], rel=1e-3)
    assert ini['impact']['speed_mps'] == pytest.approx(dz['landing_velocity'], rel=1e-3)
    # Yere inişte terminal hız: v = sqrt(2 m g / (rho Cd A)).
    from hrma.analysis.six_dof_trajectory import _atmosphere
    rho, _a = _atmosphere(0.0)
    vt = math.sqrt(2.0 * m * s.g_surface / (rho * 1.4 * 3.0))
    assert ini['impact']['speed_mps'] == pytest.approx(vt, rel=2e-3)


def test_parasut_ucta_ve_olaylarda(istemci, araclar):
    g = sayfa_govdesi(araclar['hybrid'], 10.0, descent_model='parachute',
                      parachute_area=2.0)
    y = istemci.post('/api/six-dof-analysis', json=g)
    d = y.get_json()
    assert y.status_code == 200, d
    x = d['track']['descent']
    assert x['model'] == 'parachute_point_mass' and x['status'] == 'solved'
    k = x['recovery']
    assert k['assumed'] == {'cd': True, 'deploy_delay': True}
    from hrma.analysis.trajectory_analysis import (DEFAULT_PARACHUTE_CD,
                                                   DEFAULT_PARACHUTE_DEPLOY_DELAY_S)
    assert k['parachute_cd'] == DEFAULT_PARACHUTE_CD
    ev = {e['key']: e for e in d['track']['events']}
    assert ev['deploy']['t_s'] == pytest.approx(
        d['summary']['apogee_time'] + DEFAULT_PARACHUTE_DEPLOY_DELAY_S, rel=1e-12)
    assert ev['apogee']['t_s'] < ev['deploy']['t_s'] < ev['landing']['t_s']
    # Paraşütlü iniş balistikten çok yavaş biter.
    yb = istemci.post('/api/six-dof-analysis',
                      json=sayfa_govdesi(araclar['hybrid'], 10.0)).get_json()
    assert x['impact']['speed_mps'] < 0.2 * yb['track']['descent']['impact']['speed_mps']


@pytest.mark.parametrize('ek, alan, neden', [
    ({'descent_model': 'parachute'}, 'parachute_area', 'required_for_parachute_descent'),
    ({'descent_model': 'parachute', 'parachute_area': 0}, 'parachute_area', 'must_be_positive'),
    ({'descent_model': 'parachute', 'parachute_area': 2, 'parachute_cd': -1},
     'parachute_cd', 'must_be_positive'),
    ({'descent_model': 'parachute', 'parachute_area': 2, 'parachute_deploy_delay': -1},
     'parachute_deploy_delay', 'must_be_non_negative'),
    ({'descent_model': 'parachute', 'parachute_area': 'iki'}, 'parachute_area', 'not_a_number'),
    ({'parachute_area': 2}, 'parachute_area', 'requires_parachute_descent_model'),
])
def test_parasut_girdi_kapisi(istemci, ek, alan, neden):
    from tests.test_v307_fs_ucus import ORNEK_GOVDE
    y = istemci.post('/api/six-dof-analysis', json=dict(ORNEK_GOVDE, **SAHA, **ek))
    d = y.get_json()
    assert y.status_code == 422, d
    assert {'field': alan, 'reason': neden}.items() <= d['invalid_fields'][0].items()


# ------------------------------------------------------------- A5 yanma sonu
def test_yanma_sonu_tek_tanim(kural_ucuslari, araclar):
    for mt, (_, d) in kural_ucuslari.items():
        veh = araclar[mt]
        ev = {e['key']: e for e in d['track']['events']}
        assert ev['burnout']['source'] == 'thrust_input_end'
        assert ev['burnout']['t_s'] == pytest.approx(veh['burn_time'], rel=1e-12), mt
        assert d['summary']['flight_verdict']['burn_time_s'] == pytest.approx(
            veh['burn_time'], rel=1e-12)
        tc = veh.get('thrust_curve')
        if tc and tc.get('time'):
            assert tc['time'][-1] == pytest.approx(veh['burn_time'], rel=1e-12), mt


# ------------------------------------------------------------- A3 içe aktarma
def test_dosya_ve_kayitli_proje_ayni_arac(istemci, araclar, tmp_path, monkeypatch):
    import shutil
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(tmp_path))
    shutil.copy(ORNEKLER / ORNEK_DOSYA['hybrid'], tmp_path / ORNEK_DOSYA['hybrid'])
    y = istemci.post('/api/flight-vehicle', json={
        'source': 'project', 'name': ORNEK_DOSYA['hybrid'][:-5]})
    v = y.get_json()['vehicle']
    f = araclar['hybrid']
    assert f['source'] == 'file' and f['file_name'] == ORNEK_DOSYA['hybrid']
    farkli = [k for k in v if k not in ('source', 'airframe_resolved', 'sixdof_setup')
              and json.dumps(v[k], sort_keys=True) != json.dumps(f.get(k), sort_keys=True)]
    assert farkli == []
    # V307/ONARIM-UÇUŞ (M7-FS-14): 6-DOF kurulum bloğu, airframe_resolved gibi
    # kendi kaynağını taşır ('project' ⟷ 'file'); değerleri aynıdır.
    kv, kf = dict(v['sixdof_setup']), dict(f['sixdof_setup'])
    assert (kv.pop('source'), kf.pop('source')) == ('project', 'file')
    assert kv == kf and kv['cd0'] == 0.5


def test_load_project_document_yukleme_kapisiyla_ayni(tmp_path, monkeypatch):
    import shutil
    from hrma.utils import projects
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(tmp_path))
    ad = ORNEK_DOSYA['solid'][:-5]
    shutil.copy(ORNEKLER / ORNEK_DOSYA['solid'], tmp_path / ORNEK_DOSYA['solid'])
    d1, k1 = projects.load_project_records(ad)
    d2, k2 = projects.load_project_document(
        projects.parse_project_text((ORNEKLER / ORNEK_DOSYA['solid']).read_text(encoding='utf-8')))
    assert d1 == d2 and k1 == k2
    with pytest.raises(projects.ProjectValidationError):
        projects.load_project_document(['liste'])
    # Depo yolu: şema hatası yine ProjectCorruptError (davranış değişmedi).
    (tmp_path / 'bozuk.hrma').write_text('{"format": "x"}', encoding='utf-8')
    with pytest.raises(projects.ProjectCorruptError):
        projects.load_project_records('bozuk')


SALDIRGAN = [
    ('uzanti', {'file_name': 'a.json'}, 422, 'invalid_project_file_name'),
    ('yol', {'file_name': '../../etc/passwd.hrma'}, 422, 'invalid_project_file_name'),
    ('ters_bolu', {'file_name': 'C:\\x\\a.hrma'}, 422, 'invalid_project_file_name'),
    ('nul', {'file_name': 'a\x00.hrma'}, 422, 'invalid_project_file_name'),
    ('ad_yok', {'file_name': None}, 422, 'invalid_project_file_name'),
    ('uzun_ad', {'file_name': 'a' * 300 + '.hrma'}, 422, 'invalid_project_file_name'),
    ('buyuk', {'document_text': ' ' * (1024 * 1024 + 1)}, 413, 'project_file_too_large'),
    ('json_degil', {'document_text': 'import os; os.system("x")'}, 422, 'invalid_project_file'),
    ('pickle', {'document_text': "cos\nsystem\n(S'ls'\ntR."}, 422, 'invalid_project_file'),
    ('nan', {'document_text': '{"a": NaN}'}, 422, 'invalid_project_file'),
    ('sonsuz', {'document_text': '{"a": -Infinity}'}, 422, 'invalid_project_file'),
    ('derin', {'document_text': '[' * 200000 + ']' * 200000}, 422, 'invalid_project_file'),
    ('dizi_kok', {'document_text': '[1, 2]'}, 422, 'invalid_project_file'),
    ('sema', {'document_text': '{"format": "hrma-project"}'}, 422, 'invalid_project_file'),
    ('bilinmeyen_anahtar', {'document_text': json.dumps({
        'format': 'hrma-project', 'format_version': 1, 'motor_type': 'solid',
        'inputs': {'fields': {}}, '__class__': 'x'})}, 422, 'invalid_project_file'),
    ('metin_degil', {'document_text': 12}, 422, 'invalid_project_file'),
    ('vekil', {'document_text': '{"a": "\ud800"}'}, 422, 'invalid_project_file'),
]


@pytest.mark.parametrize('ad, ek, durum, hata', SALDIRGAN, ids=[s[0] for s in SALDIRGAN])
def test_saldirgan_dosya_adli_ret(istemci, ad, ek, durum, hata):
    govde = {'source': 'file', 'file_name': 'b.hrma', 'document_text': '{}'}
    govde.update(ek)
    y = istemci.post('/api/flight-vehicle', json=govde)
    d = y.get_json() or {}
    assert y.status_code == durum, (ad, y.status_code, d)
    assert d.get('error') == hata, (ad, d)
    assert 'vehicle' not in d


def test_ice_aktarma_diske_yazmaz(istemci, tmp_path, monkeypatch):
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(tmp_path))
    once = sorted(p.name for p in tmp_path.iterdir())
    y = istemci.post('/api/flight-vehicle', json={
        'source': 'file', 'file_name': ORNEK_DOSYA['solid'],
        'document_text': (ORNEKLER / ORNEK_DOSYA['solid']).read_text(encoding='utf-8')})
    assert y.status_code == 200
    assert sorted(p.name for p in tmp_path.iterdir()) == once


# ------------------------------------------------------------- D2 Dünya dönüşü
def test_coriolis_inisi_kaydirir_ve_not_dogru(kural_ucuslari, araclar, istemci):
    _, d = kural_ucuslari['liquid']
    g = sayfa_govdesi(araclar['liquid'], 60.0)
    g.pop('latitude_deg')
    g.pop('longitude_deg')
    d0 = istemci.post('/api/six-dof-analysis', json=g).get_json()
    a = d['track']['descent']['impact']
    b = d0['track']['descent']['impact']
    assert math.hypot(a['east_m'] - b['east_m'], a['north_m'] - b['north_m']) > 100.0
    s = SOZLUK.read_text(encoding='utf-8')
    for k in ('site.earthRotNote', 'site.groundTrackLabel'):
        for m in re.finditer(r"'%s': '([^']*)'" % re.escape(k), s):
            assert 'not modelled' not in m.group(1).lower()
            assert 'modellenm' not in m.group(1).lower()
            assert 'Coriolis' in m.group(1)


# ------------------------------------------------------------- sayfa (statik)
def _sablon():
    return SABLON.read_text(encoding='utf-8')


def test_kanat_ve_parasut_girdileri_ipuculu():
    s = _sablon()
    for kimlik, anahtar in (('ls-a-finroot', 'site.help.finRootChord'),
                            ('ls-a-fintip', 'site.help.finTipChord'),
                            ('ls-a-finsweep', 'site.help.finSweep'),
                            ('ls-a-finspan', 'site.help.finSpan'),
                            ('ls-a-chutearea', 'site.help.chuteArea'),
                            ('ls-a-chutecd', 'site.help.chuteCd'),
                            ('ls-a-chutedelay', 'site.help.chuteDelay'),
                            ('ls-file', 'site.help.projectFile')):
        i = s.index('id="%s"' % kimlik)
        kutu = s[s.rindex('<div class="ls-field"', 0, i):i]
        assert 'data-i18n="%s"' % anahtar in kutu, kimlik
        assert 'tooltip-icon' in kutu, kimlik
    # Kanat ölçüleri artık sabit değil, boş = kural (varsayılan değer yok).
    for kimlik in ('ls-a-finroot', 'ls-a-fintip', 'ls-a-finsweep', 'ls-a-finspan'):
        assert not re.search(r'id="%s"[^>]*value=' % kimlik, s), kimlik
    assert "fin_geometry_rule: 'static_margin'" in s
    assert 'accept=".hrma"' in s
    assert re.search(r"if \(typeof body\.parachute_area === 'number'\) body\.descent_model = 'parachute';", s)


def test_yeni_metinler_en_tr():
    s = _sablon()
    sozluk = SOZLUK.read_text(encoding='utf-8')
    en, tr = sozluk.split('\n        tr: {', 1)
    anahtarlar = set(re.findall(r"'(site\.(?:fin|chute|file|thrustSrc|burnoutFlown|"
                                r"flightDescentParachute|airframeFromFile|srcFile|"
                                r"selectFile|help\.(?:fin|chute|projectFile))[\w.]*)'", s))
    anahtarlar |= {'site.finSrc.supplied', 'site.finSrc.rule_planform',
                   'site.finSrc.rule_static_margin', 'site.finSrc.solver_default',
                   'site.finSrc.no_fins', 'site.thrustSrc.motor_blowdown',
                   'site.trackDescentParachute', 'site.trackLandingParachute',
                   'site.src.file'}
    assert len(anahtarlar) > 30
    for k in anahtarlar:
        if k.endswith('.'):
            continue
        assert ("'%s':" % k) in en, k
        assert ("'%s':" % k) in tr, k
    tr_satir = [ln for ln in tr.splitlines() if "'site.fin" in ln or "'site.chute" in ln]
    assert any(re.search('[çğıöşüİ]', ln) for ln in tr_satir)
    # Ölü anahtar kalmadı.
    assert 'site.burnoutFromInput' not in sozluk


# ------------------------------------------------------------- tarayıcı
CHROME = pathlib.Path(
    '/Users/apple/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/'
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')


@pytest.fixture(scope='module')
def sunucu(tmp_path_factory):
    if importlib.util.find_spec('playwright') is None:
        pytest.skip('playwright paketi yok')
    if not CHROME.exists():
        pytest.skip(f'Chromium yok: {CHROME}')
    import os
    depo = tmp_path_factory.mktemp('fs_ucus_2_projeler')
    eski = os.environ.get('HRMA_PROJECTS_DIR')
    os.environ['HRMA_PROJECTS_DIR'] = str(depo)
    from tools.browser_harness.sunucu import UygulamaSunucusu
    s = UygulamaSunucusu(gunluk_yolu=str(depo / 'sunucu.log'))
    try:
        s.baslat()
        yield s.temel_url
    finally:
        s.durdur()
        if eski is None:
            os.environ.pop('HRMA_PROJECTS_DIR', None)
        else:
            os.environ['HRMA_PROJECTS_DIR'] = eski


def test_tarayici_dosyadan_ice_aktarip_kuralla_kararli_ucar(sunucu):
    """Kullanıcı yolu: Kaynak = proje dosyası, hibrit örnek dosyası seçilir,
    gövde kuru kütlesi yazılır, kanat alanları boş → kural; uçuş kararlı,
    oynatma kapısı hükmü 'kararlı', kanat künyesi kaynağıyla ekranda."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=str(CHROME), headless=True,
                              args=['--disable-3d-apis', '--disable-gpu',
                                    '--use-gl=disabled'])
        try:
            s = b.new_page(viewport={'width': 1440, 'height': 900})
            s.set_default_timeout(60000)
            s.goto(sunucu + '/launch-site', wait_until='domcontentloaded')
            s.wait_for_function('document.getElementById("ls-fly")')
            s.select_option('#ls-vehicle-source', 'file')
            assert s.is_visible('#ls-file')
            with s.expect_response(lambda r: r.url.endswith('/api/flight-vehicle'),
                                   timeout=120000) as yanit:
                s.set_input_files('#ls-file', str(ORNEKLER / ORNEK_DOSYA['hybrid']))
            assert yanit.value.status == 200
            istek = yanit.value.request.post_data_json
            assert istek['source'] == 'file' and istek['file_name'] == ORNEK_DOSYA['hybrid']
            s.wait_for_function("document.getElementById('ls-v-thrust').value !== ''")
            assert s.input_value('#ls-a-finspan') == ''
            s.fill('#ls-a-drymass', '10')
            with s.expect_response(lambda r: '/api/six-dof-analysis' in r.url,
                                   timeout=120000) as uc:
                s.click('#ls-fly')
            govde = uc.value.request.post_data_json
            assert govde['fin_geometry_rule'] == 'static_margin'
            assert 'fin_span' not in govde and 'fin_root_chord' not in govde
            s.wait_for_function('window.LaunchSiteFlightResult !== null', timeout=30000)
            r = s.evaluate('window.LaunchSiteFlightResult')
            assert r['vehicle']['source'] == 'file'
            # V307/FS-YÜK (kalem 4): dosya kaynağında sayfa çalkantı bloğunu da
            # gönderir (FS-KÜÇÜK kalem 5). Hüküm sözleşmesi §11 (UÇUŞ-GÖVDE
            # kalem 6): bağlaşık koşu doğrusal geçerlilik sınırını aşarsa
            # kararlılık hükmü YAYIMLANMAZ (stable None, nedeni yayım kaydında);
            # aşmazsa yayımlanan hüküm bağlaşık koşunundur. ÖLÇÜLDÜ (fs-yuk/
            # tarayici/hibrit_dosya_en_1440.json): n2o tankı t = 4,51 s'de
            # sınırı aşıyor, rijit referans 'stable'. Kanat kuralının iddiası
            # (araç kuralla kararlı) rijit koşunun hükmünde ve statik marjda.
            y = uc.value.json()
            yayim = r['slosh_publication'] or {}
            if yayim.get('neden_kodu') == 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI':
                assert r['solver']['stable'] is None
                assert 'stable' in yayim['yayimlanmayan_alanlar']
            else:
                assert r['solver']['stable'] is True
            assert y['calkanti']['rijit_karsilastirma']['flight_verdict']['stability'] == 'stable'
            assert r['solver']['static_margin_full'] > 1.0
            assert r['solver']['static_margin_empty'] > 1.0
            assert r['playback_allowed'] is True
            not_ = s.text_content('#ls-fin-note')
            assert 'Niskanen' in not_ and 'rule: static margin criterion' in not_
            assert 'unstable' not in (s.text_content('#ls-status') or '').lower()
            # Araç değişince kanat künyesi silinir.
            s.select_option('#ls-vehicle-source', 'example')
            assert s.text_content('#ls-fin-note') == ''
            # Saldırgan dosya: tarayıcı kapısı uzantıyla durdurur (istek yok).
            s.select_option('#ls-vehicle-source', 'file')
            s.set_input_files('#ls-file', files=[{'name': 'x.json', 'mimeType': 'application/json',
                                                   'buffer': b'{}'}])
            assert 'not a .hrma project file' in s.text_content('#ls-vehicle-note')
        finally:
            b.close()
