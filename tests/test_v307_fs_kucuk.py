"""V307/FS-KÜÇÜK — Fırlatma Sahası: paraşüt açılışı olayı, apoje etiketi,
paraşüt girdi kuralı tek yerde, vakum tasarımlı motorun adlı köprü reddi,
6-DOF'a çalkantı bloğu.

ÖLÇÜLDÜ (docs/scofield/raw/OH/V307/fs-kucuk/olcum/api_once_*.json, taban
c2c455b4c):
  * kalem 1: sunucu paraşütlü uçuşta ``deploy`` olayını yayımlıyor (örnek
    araç, 3 m² / Cd 1,4 / 2 s: t 51,95 s, 15 479,7 m, 47,16 m/s) ama izleme
    ekranı tanımadığı olayı atlıyordu; sol/sağ olay listesinde ve kürede
    işaretçi yoktu.
  * kalem 3: düzlemsel uç ve 6-DOF ucu aynı paraşüt kuralını iki ayrı yerde
    yazıyordu (21 ret vakası önce/sonra yanıt sha256'sı aynı).
  * kalem 4: vakum tasarımlı sıvı motor (ε 40, P_e 0,0975 bar) köprüde genel
    'unflyable_vehicle' ile, dosya/proje kolunda HTTP 200 + itki None ile
    dönüyordu.

Bekçiler kalem kalem aşağıda; tarayıcı ölçümü kanıt dizinindedir.
"""
import contextlib
import inspect
import io
import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
ORNEKLER = KOK / 'examples'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')


def _oku(yol):
    return pathlib.Path(yol).read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, uc, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = istemci.post(uc, json=govde)
    return r.status_code, r.get_json()


# ===================================================================== kalem 3
#: Düzlemsel uç için geçerli en küçük gövde (paraşüt kapısına ulaşır).
DUZLEM = {'thrust': 1500.0, 'burn_time': 3.0, 'initial_mass': 12.0,
          'final_mass': 9.0, 'drag_coefficient': 0.5,
          'reference_area': 0.008, 'launch_angle': 85.0}
#: 6-DOF ucu için örnek araç düzeninde gövde (paraşüt kapısı çözücüden önce).
ALTI_SD = {'body_diameter': 0.15, 'body_length': 3.0, 'nose_length': 0.5,
           'nose_type': 'ogive', 'dry_mass': 25.0, 'propellant_mass': 18.0,
           'thrust': 6500.0, 'burn_time': 7.5, 'cd0': 0.45, 'fin_count': 4,
           'fin_root_chord': 0.2, 'fin_tip_chord': 0.1, 'fin_span': 0.112,
           'fin_sweep': 0.08, 'launch_elevation_deg': 84.0,
           'launch_azimuth_deg': 90.0, 'rail_length': 5.0, 'wind_speed': 0.0,
           'wind_direction_deg': 270.0, 't_max': 400.0,
           'latitude_deg': 28.6084, 'longitude_deg': -80.6043}

KURAL_VAKALARI = [
    ({'parachute_area': 0.0},
     [{'field': 'parachute_area', 'reason': 'must_be_positive', 'value': 0.0}]),
    ({'parachute_area': 3.0, 'parachute_cd': -1.4},
     [{'field': 'parachute_cd', 'reason': 'must_be_positive', 'value': -1.4}]),
    ({'parachute_area': 3.0, 'parachute_deploy_delay': -2.0},
     [{'field': 'parachute_deploy_delay', 'reason': 'must_be_non_negative',
       'value': -2.0}]),
    ({'parachute_area': -3.0, 'parachute_cd': 0.0, 'parachute_deploy_delay': -0.5},
     [{'field': 'parachute_area', 'reason': 'must_be_positive', 'value': -3.0},
      {'field': 'parachute_cd', 'reason': 'must_be_positive', 'value': 0.0},
      {'field': 'parachute_deploy_delay', 'reason': 'must_be_non_negative',
       'value': -0.5}]),
]


def test_parasut_kurali_tek_yerde_kaynak_denetimi():
    from hrma import app as uygulama
    from hrma.analysis import launch_site_flight as lsf
    for uc in (uygulama.trajectory_analysis, uygulama.six_dof_analysis):
        kaynak = inspect.getsource(uc)
        assert '_parasut_girdi_kapisi(' in kaynak, uc.__name__
        # Kuralın ikinci kopyası yok: alan listesi ve gerekçe kodları uçta yazılmaz.
        assert '_KURTARMA_ALANLARI' not in kaynak and '_parasut_alanlari' not in kaynak
        assert "'must_be_non_negative'" not in kaynak, uc.__name__
    kapı = inspect.getsource(uygulama._parasut_girdi_kapisi)
    assert 'parachute_input_defect(' in kapı and 'PARACHUTE_INPUT_FIELDS' in kapı
    assert 'parachute_input_defect(' in inspect.getsource(lsf.recovery_inputs)
    assert lsf.PARACHUTE_INPUT_FIELDS == (('parachute_area', True), ('parachute_cd', True),
                                          ('parachute_deploy_delay', False))


@pytest.mark.parametrize('ek,beklenen', KURAL_VAKALARI)
def test_parasut_iki_uc_ayni_ret(istemci, ek, beklenen):
    k1, d1 = _post(istemci, '/api/trajectory-analysis', dict(DUZLEM, **ek))
    k2, d2 = _post(istemci, '/api/six-dof-analysis',
                   dict(ALTI_SD, descent_model='parachute', **ek))
    assert k1 == k2 == 422
    # Gerekçe kodları ve kayıtları iki uçta BİREBİR aynı (ve önceki sürümle aynı).
    assert d1['invalid_fields'] == beklenen
    assert d2['invalid_fields'] == beklenen
    assert d1['error'] == 'invalid_launch_conditions'
    assert d2['error'] == 'invalid_six_dof_input'


def test_parasut_6dof_ozgu_kurallar_degismedi(istemci):
    k, d = _post(istemci, '/api/six-dof-analysis',
                 dict(ALTI_SD, descent_model='parachute', parachute_cd=1.2))
    assert k == 422 and d['invalid_fields'] == [
        {'field': 'parachute_area', 'reason': 'required_for_parachute_descent'}]
    k, d = _post(istemci, '/api/six-dof-analysis',
                 dict(ALTI_SD, descent_model='ballistic', parachute_area=3.0))
    assert k == 422 and d['invalid_fields'] == [
        {'field': 'parachute_area', 'reason': 'requires_parachute_descent_model'}]
    k, d = _post(istemci, '/api/six-dof-analysis',
                 dict(ALTI_SD, descent_model='parachute', parachute_area='uc'))
    assert k == 422 and d['invalid_fields'] == [
        {'field': 'parachute_area', 'reason': 'not_a_number', 'value': 'uc'}]


def test_kurtarma_tanimi_ayni_kurali_kullanir():
    from hrma.analysis import launch_site_flight as lsf
    for kotu in ((0.0, None, None), (3.0, -1.0, None), (3.0, None, -0.1),
                 (float('nan'), None, None), (3.0, None, float('inf'))):
        with pytest.raises(ValueError):
            lsf.recovery_inputs(*kotu)
    r = lsf.recovery_inputs(3.0, None, 0.0)
    assert r['deploy_delay_s'] == 0.0 and r['assumed'] == {'cd': True, 'deploy_delay': False}


# ===================================================================== kalem 4
def _sivi_belgesi(**alan):
    doc = json.loads((ORNEKLER / 'Example Liquid LOX-RP1 25kN.hrma')
                     .read_text(encoding='utf-8'))
    doc['inputs']['fields'].update(alan)
    return doc


@pytest.fixture(scope='module')
def vakum_sonucu():
    from hrma.analysis import flight_vehicle as fv
    doc = _sivi_belgesi(design_ambient_mode='vacuum', nozzle_expansion_ratio=40)
    with contextlib.redirect_stdout(io.StringIO()):
        mt, sonuc = fv.recompute_from_project(doc)
    assert mt == 'liquid'
    return doc, json.loads(json.dumps(sonuc, default=float).replace('NaN', 'null'))


def test_vakum_tasarimi_kopruden_adli_ret(istemci, vakum_sonucu):
    doc, sonuc = vakum_sonucu
    ds = sonuc['design_ambient']['sea_level']
    assert ds['status'] == 'separated'
    k1, d1 = _post(istemci, '/api/flight-vehicle',
                   {'source': 'results', 'motor_type': 'liquid', 'results': sonuc})
    k2, d2 = _post(istemci, '/api/flight-vehicle',
                   {'source': 'file', 'file_name': 'vakum.hrma',
                    'document_text': json.dumps(doc)})
    for k, d in ((k1, d1), (k2, d2)):
        assert k == 422, d
        assert d['error'] == 'sea_level_thrust_not_published'
        assert d['cause'] == 'nozzle_flow_separated_at_sea_level'
        assert d['design_ambient']['mode'] == 'vacuum'
        # Sayılar motorun kendi bloğundan, aynen (ikinci gerekçe yok).
        assert d['sea_level']['exit_pressure_bar'] == ds['exit_pressure_bar']
        assert d['sea_level']['separation_pressure_bar'] == ds['separation_pressure_bar']
        assert d['sea_level']['not_published_reason'] == ds['not_published_reason']
        assert 'vehicle' not in d
    assert d2['source'] == 'file' and d2['file_name'] == 'vakum.hrma'


def test_deniz_seviyesinde_yapisik_irtifa_tasarimi_yine_ucar(istemci):
    from hrma.analysis import flight_vehicle as fv
    doc = _sivi_belgesi(design_ambient_mode='altitude',
                        design_ambient_altitude_m=3000, nozzle_expansion_ratio=12)
    with contextlib.redirect_stdout(io.StringIO()):
        _mt, sonuc = fv.recompute_from_project(doc)
    sonuc = json.loads(json.dumps(sonuc, default=float).replace('NaN', 'null'))
    assert sonuc['design_ambient']['sea_level']['status'] == 'attached'
    k, d = _post(istemci, '/api/flight-vehicle',
                 {'source': 'results', 'motor_type': 'liquid', 'results': sonuc})
    assert k == 200, d
    assert d['vehicle']['thrust'] == sonuc['design_summary']['performance']['thrust_sl_N']


def test_kopru_ret_metni_tek_islevde_en_tr():
    js = _oku(JS / 'flight_handoff.js')
    assert "REFUSAL_CODE_SEA_LEVEL = 'sea_level_thrust_not_published'" in js
    assert 'b.error === REFUSAL_CODE_SEA_LEVEL' in js
    kabuk = _oku(JS / 'i18n_shell.js')
    for anahtar in ('flight.refusedSeaLevelSeparated', 'flight.refusedSeaLevelNotPublished',
                    'flight.ambientVacuum', 'flight.ambientAltitude',
                    'flight.ambientPressure', 'flight.ambientNonSeaLevel'):
        assert kabuk.count("'%s':" % anahtar) == 2, anahtar   # EN + TR
        assert anahtar in js
    anahtar = "'flight.refusedSeaLevelSeparated'"
    ikinci = kabuk.index(anahtar, kabuk.index(anahtar) + 1)
    assert 'deniz seviyesinde nozul akışı ayrılıyor' in kabuk[ikinci:ikinci + 400]  # tek terim: nozul (test_d28_arayuz_a2)
    saha = _oku(SABLON)
    # Fırlatma Sahası metni köprünün AYNI işlevinden (oturum, proje, dosya).
    assert saha.count('FlightHandoff.refusalText(') >= 2
    assert "durum.status === 'refused'" in saha
    assert 'kopruAdliReddi(d, httpDurum)' in saha
    i = saha.index("if (durum.status === 'refused')")
    assert 'flight.refusedCooling' not in saha[i:i + 600]


_DOM = r"""
var document = { getElementById: function () { return null; },
  dispatchEvent: function () {}, querySelector: function () { return null; } };
var window = { document: document, localStorage: { getItem: function () { return null; },
  setItem: function () {} } };
global.window = window; global.document = document;
"""


def _node(betik):
    sonuc = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                           timeout=30)
    assert sonuc.returncode == 0, sonuc.stderr
    return json.loads(sonuc.stdout.strip().splitlines()[-1])


@node_gerekli
def test_kopru_ret_metni_yanit_alanlarindan(vakum_sonucu, istemci):
    _doc, sonuc = vakum_sonucu
    _k, govde = _post(istemci, '/api/flight-vehicle',
                      {'source': 'results', 'motor_type': 'liquid', 'results': sonuc})
    r = _node(_DOM + _oku(JS / 'flight_handoff.js') + '\n'
              + 'var g = %s;\n' % json.dumps(govde)
              + 'var kayit = {code: g.error, cause: g.cause, design_ambient: g.design_ambient, '
                'sea_level: g.sea_level};\n'
              + 'console.log(JSON.stringify({a: window.FlightHandoff.refusalText(g), '
                'b: window.FlightHandoff.refusalText(kayit), '
                'c: window.FlightHandoff.REFUSAL_CODES}));')
    # Uç gövdesi ve köprü kaydı aynı metni verir (Fırlatma Sahası ⟷ motor sayfası).
    assert r['a'] == r['b']
    assert 'designed for vacuum' in r['a']
    pe = '%.4f' % govde['sea_level']['exit_pressure_bar']
    assert pe in r['a'] and '%.4f' % govde['sea_level']['separation_pressure_bar'] in r['a']
    assert r['c'] == ['engine_mass_not_published', 'sea_level_thrust_not_published']


# ===================================================================== kalem 1
@pytest.fixture(scope='module')
def parasutlu_ucus(istemci):
    """Örnek araç düzeninde paraşütlü Fırlatma Sahası uçuşu (sunucu izi)."""
    k, d = _post(istemci, '/api/six-dof-analysis',
                 dict(ALTI_SD, descent_model='parachute', parachute_area=3.0,
                      parachute_cd=1.4, parachute_deploy_delay=2.0))
    assert k == 200, d
    return d


def _sayfa_sozlesmesi(d):
    """launch_site.html ``ucusSonucuKur``un izleme ekranının okuduğu alanları
    (yanıtın kendisi; sayfa sayı üretmez)."""
    iz = d['track']
    return {'schema': 'hrma.launch_site.flight_result/1', 'status': 'solved',
            'playback_allowed': True, 'samples': iz['samples'],
            'events': iz['events'], 'descent': iz.get('descent'),
            'frame': iz['frame'],
            'solver': {'end_reason': d['summary']['end_reason'],
                       'static_margin_full': d['summary']['static_margin_full'],
                       'static_margin_empty': d['summary']['static_margin_empty']}}


def test_deploy_olayi_sunucuda_gercek_degerleriyle(parasutlu_ucus):
    ev = {e['key']: e for e in parasutlu_ucus['track']['events']}
    assert ['liftoff', 'burnout', 'max_q', 'apogee', 'deploy', 'landing'] == [
        e['key'] for e in parasutlu_ucus['track']['events']]
    assert ev['deploy']['t_s'] == pytest.approx(ev['apogee']['t_s'] + 2.0, abs=1e-9)
    assert ev['deploy']['source'] == 'apogee_plus_deploy_delay'
    assert ev['deploy']['altitude_agl_m'] > 0 and ev['deploy']['speed_mps'] > 0


@node_gerekli
def test_deploy_izleme_ekraninda_yanitla_ayni_sayi(parasutlu_ucus):
    c = _sayfa_sozlesmesi(parasutlu_ucus)
    betik = ('const C = require(%s);\nconst G = %s;\n'
             'const n = C.normalizeSozlesme(G);\n'
             'console.log(JSON.stringify({ok: n.ok, ev: C.olaylar(n.iz), renk: C.OLAY_RENGI}));'
             % (json.dumps(str(JS / 'launch_site_tracking.js')), json.dumps(c)))
    r = _node(betik)
    assert r['ok'] is True
    acilis = [e for e in r['ev'] if e['anahtar'] == 'deploy']
    assert len(acilis) == 1
    s = next(e for e in c['events'] if e['key'] == 'deploy')
    assert acilis[0]['t'] == s['t_s']                     # aynı sayı (===)
    assert acilis[0]['deger'] == s['altitude_agl_m']
    assert acilis[0]['hiz'] == s['speed_mps']
    assert acilis[0]['alan'].endswith('.t_s') and acilis[0]['hizAlan'].endswith('.speed_mps')
    # Paraşüt yoksa açılış satırı yok (uydurulmaz).
    c2 = dict(c, events=[e for e in c['events'] if e['key'] != 'deploy'])
    r2 = _node(betik.replace(json.dumps(c), json.dumps(c2)))
    assert not [e for e in r2['ev'] if e['anahtar'] == 'deploy']
    # Küre işaretçisinin rengi izleme rengiyle aynı.
    kure = _oku(JS / 'launch_site_globe.js')
    m = re.search(r"add\(di,\s*0x([0-9a-fA-F]{6}),\s*'deploy'", kure)
    assert m and int(m.group(1), 16) == r['renk']['deploy']


def test_deploy_kure_ve_sol_liste_sunucu_olayindan():
    kure = _oku(JS / 'launch_site_globe.js')
    i = kure.index('this.opts.deployTime != null')
    assert "add(di, 0xff7eb6, 'deploy', this)" in kure[i:i + 400]
    saha = _oku(SABLON)
    assert "e.key === 'deploy'; })[0]" in saha          # sözleşmenin olayından
    assert 'globe.opts.deployTime = (acilisOlayi' in saha
    i = saha.index('function renderEvents()')
    blok = saha[i:i + 6000]
    assert "deploy: 'site.deploy'" in blok
    assert 'site.deployAfterApogee' in blok and 's.speed_mps' in blok
    izleme = _oku(JS / 'launch_site_tracking.js')
    assert "deploy: 'deploy'" in izleme and "t('site.deploy', 'Parachute opens')" in izleme


# ===================================================================== kalem 2
def _sozluk(dil):
    metin = _oku(JS / 'i18n_launch_site.js')
    bas = metin.index('\n        %s: {' % dil)
    son = metin.index('\n        }', bas)
    return dict(re.findall(r"'(site\.[\w.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'", metin[bas:son]))


def test_apoje_etiketi_yalin_model_siniri_inis_basinda():
    en, tr = _sozluk('en'), _sozluk('tr')
    assert en['site.apogee'] == 'Apogee' and tr['site.apogee'] == 'Apoje'
    for s in (en, tr):
        assert not any('solver ends here' in v or 'çözücü burada biter' in v for v in s.values())
    for k in ('site.deploy', 'site.deployAfterApogee', 'site.descentModelNote',
              'site.descentModelParachute', 'site.descentModelBallistic'):
        assert k in en and k in tr, k
    assert 'apojede biter' in tr['site.descentModelNote']
    assert 'ends at apogee' in en['site.descentModelNote']
    saha = _oku(SABLON)
    i = saha.index('function renderEvents()')
    blok = saha[i:i + 6000]
    # Not, iniş satırlarının (açılış ya da yere iniş) BAŞINA bir kez konur.
    assert "if (inis && !inisNotuKondu && (e.key === 'deploy' || e.key === 'impact')) inisSinirNotu();" in blok
    assert blok.index('inisSinirNotu();') < blok.index('box.appendChild(row);', blok.index('inisSinirNotu();'))


# ===================================================================== kalem 5
SAHA = {'latitude_deg': 28.6084, 'longitude_deg': -80.6043}


@pytest.fixture(scope='module')
def sivi_dosya_araci(istemci):
    """Örnek sıvı, .hrma DOSYASINDAN (Fırlatma Sahası yolu) + motor sonucu."""
    doc = (ORNEKLER / 'Example Liquid LOX-RP1 25kN.hrma').read_text(encoding='utf-8')
    istek = {'source': 'file', 'file_name': 'sivi.hrma', 'document_text': doc}
    k1, d1 = _post(istemci, '/api/flight-vehicle', dict(istek, include_motor_result=True))
    k0, d0 = _post(istemci, '/api/flight-vehicle', istek)
    assert k1 == k0 == 200
    return d0, d1


def test_motor_sonucu_bayragi(istemci, sivi_dosya_araci):
    d0, d1 = sivi_dosya_araci
    assert 'motor_result' not in d0                     # bayrak yoksa yanıt değişmez
    assert d0['vehicle'] == d1['vehicle']
    ms = d1['motor_result']
    # Sayfanın hesap ucunun gövdesi (motor sayfasının currentResults'ı).
    assert isinstance(ms.get('design_summary'), dict) and isinstance(ms.get('propellant_tanks'), dict)
    for govde, beklenen in (({'source': 'file', 'file_name': 'a.hrma', 'document_text': '{}',
                              'include_motor_result': 'yes'}, 400),
                            ({'source': 'results', 'motor_type': 'liquid', 'results': {'thrust': 1.0},
                              'include_motor_result': True}, 400)):
        k, d = _post(istemci, '/api/flight-vehicle', govde)
        assert k == beklenen and d['field'] == 'include_motor_result', d


def _fs_govdesi(veh, kuru, **ek):
    """launch_site.html "Bu sahadan uçur" gövdesi (kanat alanları boş → kural)."""
    ft = veh.get('flight_thrust') or {}
    g = {'body_diameter': 0.5, 'body_length': 3.6,   # ÇALKANTI-ARAYÜZ kanıt gövdesi
         'nose_length': 0.5, 'nose_type': 'ogive',
         'dry_mass': kuru + veh['engine_inert_mass'] + (ft.get('propellant_residual_kg') or 0.0),
         'propellant_mass': ft.get('propellant_consumed_kg') or veh['propellant_mass'],
         'nozzle_exit_area': ft.get('nozzle_exit_area_m2'),
         'thrust_reference_pressure': ft.get('thrust_reference_pressure_pa'),
         'thrust': veh['thrust'], 'burn_time': veh['burn_time'], 'cd0': 0.45,
         'fin_count': 4, 'fin_geometry_rule': 'static_margin',
         'launch_elevation_deg': 84.0, 'launch_azimuth_deg': 90.0, 'rail_length': 5.0,
         'wind_speed': 0.0, 'wind_direction_deg': 270.0, 't_max': 400.0,
         'descent_model': 'ballistic', 'engine_od_m': veh.get('engine_od_m'),
         'engine_length_m': veh.get('engine_length_m'),
         'propellant_volume_m3': veh.get('propellant_volume_m3')}
    g.update(SAHA)
    g.update(ek)
    return {k: v for k, v in g.items() if v is not None}


@pytest.mark.slow
def test_fs_hukmu_motor_sayfasi_hukmuyle_ayni(istemci, sivi_dosya_araci):
    _d0, d1 = sivi_dosya_araci
    veh, ms = d1['vehicle'], d1['motor_result']
    blok = {'motor_type': 'liquid', 'motor_sonucu': ms,
            'arac_duzeni': {'ardisik': {'sira': ['oksitleyici', 'yakit']}}}
    k, fs = _post(istemci, '/api/six-dof-analysis', _fs_govdesi(veh, 60.0, calkanti=blok))
    assert k == 200, fs
    c = fs['calkanti']
    assert c['durum'] == 'BAGLANDI' and c['zaman'] is not None
    # Kural rijit uçuşlarla boyutladı, yayımlanan uçuş bağlaşık son uçuş.
    son = fs['fin_geometry']['sizing']['final_flight']
    assert son['model'] == 'coupled_slosh'
    # Aynı araç, aynı kanat, aynı blok: motor sayfasının 6-DOF gövdesi.
    g = {k2: v for k2, v in _fs_govdesi(veh, 60.0, calkanti=blok).items()
         if k2 not in ('fin_geometry_rule', 'descent_model', 'longitude_deg')}
    for ad, f in fs['fin_geometry']['fields'].items():
        g[ad] = f['value']
    assert g['fin_span'] == son['fin_span_m']
    k2, ms6 = _post(istemci, '/api/six-dof-analysis', g)
    assert k2 == 200, ms6
    assert ms6['calkanti']['slosh_stability'] == c['slosh_stability']     # tek hüküm
    assert ms6['calkanti']['tanklar'] == c['tanklar']
    assert ms6['summary']['apogee'] == fs['summary']['apogee']
    assert ms6['calkanti']['rijit_karsilastirma'] == c['rijit_karsilastirma']


def test_fs_dar_govdede_ret_adiyla_ve_ucus_rijit(istemci, sivi_dosya_araci):
    _d0, d1 = sivi_dosya_araci
    veh, ms = d1['vehicle'], d1['motor_result']
    blok = {'motor_type': 'liquid', 'motor_sonucu': ms,
            'arac_duzeni': {'ardisik': {'sira': ['oksitleyici', 'yakit']}}}
    dar = dict(body_diameter=0.242, body_length=2.0)
    k, d = _post(istemci, '/api/six-dof-analysis', _fs_govdesi(veh, 60.0, calkanti=blok, **dar))
    k0, d0 = _post(istemci, '/api/six-dof-analysis', _fs_govdesi(veh, 60.0, **dar))
    assert k == k0 == 200
    c = d['calkanti']
    assert c['durum'] == 'BAGLANMADI' and 'TANK_GOVDEDEN_GENIS' in c['sebep']
    assert c['zaman'] is None
    # Bağlanmayan tankta uçuş bloksuz uçuşla aynı (uydurma konum yok).
    assert d['summary'] == d0['summary'] and d['series'] == d0['series']
    assert 'final_flight' not in d['fin_geometry']['sizing']


def test_kati_motorda_tank_yok_ucus_bit_ayni(istemci):
    doc = (ORNEKLER / 'Example Solid KNDX BATES 75mm.hrma').read_text(encoding='utf-8')
    k, d = _post(istemci, '/api/flight-vehicle', {'source': 'file', 'file_name': 'k.hrma',
                                                   'document_text': doc, 'include_motor_result': True})
    assert k == 200
    veh = d['vehicle']
    g = _fs_govdesi(veh, 4.0, body_diameter=None, body_length=None)
    gr = veh['airframe_resolved']
    g['body_diameter'] = float('%.3f' % gr['body_diameter_m'])
    g['body_length'] = float('%.2f' % (gr.get('body_length_m') or 0.5 + gr['length_behind_nose_m']))
    k0, d0 = _post(istemci, '/api/six-dof-analysis', g)
    k1, d1 = _post(istemci, '/api/six-dof-analysis',
                   dict(g, calkanti={'motor_type': 'solid', 'motor_sonucu': d['motor_result']}))
    assert k0 == k1 == 200
    assert d1['calkanti']['durum'] == 'UYGULANMAZ' and d1['calkanti']['sebep'] == ['TANK_YOK']
    for anahtar in ('summary', 'series', 'track', 'fin_geometry'):
        assert d1[anahtar] == d0[anahtar], anahtar


def test_fs_ayni_blogu_kurar_kendi_hukum_kurali_yok():
    saha = _oku(SABLON)
    panel = _oku(JS / 'calkanti_panel.js')
    # Motor sayfasının bloğu: {motor_type, motor_sonucu, arac_duzeni}.
    i = panel.index('function sixdofBlok()')
    assert 'const b = { motor_type: mt, motor_sonucu: window.currentResults, arac_duzeni: duzen };' in panel[i:i + 600]
    i = saha.index('function calkantiBloguKur()')
    assert 'return { motor_type: mt, motor_sonucu: currentMotorResult, arac_duzeni: duzen };' in saha[i:i + 800]
    assert 'if (calkantiBlogu) body.calkanti = calkantiBlogu;' in saha
    # Hüküm, gerekçe ve kodlar motor sayfasının tablolarından; sayfada hüküm
    # kodu yazılı değil, hüküm kararı verilmiyor.
    i = saha.index('function calkantiSonucunuBas(')
    blok = saha[i:saha.index('</script>', i)]
    for kod in ("'KARARLI'", "'CALKANTI_KAYNAKLI_KARARSIZLIK'", "'HUKUM_YOK'", 'max_re >', 'max_re<', 'max_re >='):
        assert kod not in blok, kod
    assert "hk('hukum', h.genel_hukum)" in blok and 'H.kodMetni' in blok
    # V307/KÜÇÜKLER (kalem 1): tablolar kamu adıyla okunur (test kancası değil).
    assert '_HK' not in blok and '_kodMetni' not in blok
    assert re.search(r'(?<![_\w])HK: HK,', panel) and re.search(r'(?<![_\w])kodMetni: kodMetni,', panel)
    # Sözlük ve kod tabloları talep üzerine; açılış yükü değişmez.
    assert '<script src="/static/js/i18n_common.js"' not in saha
    assert '<script src="/static/js/calkanti_panel.js"' not in saha
    assert 'tag.onload = bitti; tag.onerror = bitti;' in saha
    # Motor sonucu proje ve dosya kaynağında istenir.
    assert saha.count('include_motor_result: true') == 2
