"""V301/PANEL-SAYI (28 Eki 2026) — analiz panellerinde gizli sayılar ve ana
sonuçla çelişen sayılar: bekçiler.

Kanıt: ``docs/scofield/raw/OH/V301/panel-sayi/RAPOR.md``.

Kalem 1 (S1) — Besleme paneli: Basınçlandırıcı ve Su Koçu alt sekmeleri
0,5 / 293 / 20 / 200 / 0,1 / 1,0 / 0,10 / 30 / 1,2 ve 20 / 25 / 2 / 20 / 5 /
50 ile DOĞUYORDU; motordan gelen yalnız Pc (tank / hat basıncı alanına —
yanlış büyüklük), hacim ve ṁ idi. Alanlar artık sayısız doğar; motorun
kendi sonucunda karşılığı olan büyüklük oradan BİT-AYNI tohumlanır;
karşılığı olmayan zorunlu alan boşsa uç adıyla reddeder; isteğe bağlı alan
boşsa modülün varsayılanı uygulanır ve ``defaults_applied`` ile beyan
edilir.

Fikstürlerdeki sayılar 28 Eki'de dağıtılan üç örneğin gerçek motor
sonucundan (``window.currentResults``) AYNEN kopyalandı
(``docs/scofield/raw/OH/V301/panel-sayi/olcum/``).
"""
import inspect
import json
import pathlib
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')

# --- gerçek örnek sonuçlarından (alt küme, sayılar AYNEN) -------------------
PANEL_SAYI_HIBRIT_ALTKUME = {
    'oxidizer_tank_slosh': {
        'status': 'modelled', 'tank_diameter_m': 0.2120908273275041,
        'fill_height_m': 0.4506930080709462, 'g_eff_m_s2': 9.80665,
        'liquid_density_kg_m3': 785.1039703874173,
        'slosh': {'baffle': {'depth_ratio': 0.1}}},
    'tank_blowdown': {'initial_pressure_bar': 50.52509283127987,
                      'tank_volume_m3': 0.018732491692487294,
                      'feed_mode': 'blowdown'},
    'chamber_pressure': 30,
    'mdot_ox': 1.2500910562567924,
    'injector_design': {'feed_pressure_bar': 50.543358499999975},
    'combustion_analysis': {'inputs': {'oxidizer_type': 'n2o'}},
    'combustion_stability': {'chug_loop': {'feed_line': None}},
}
PANEL_SAYI_SIVI_ALTKUME = {
    'chamber_pressure': 50,
    'oxidizer_flow': 6.610012030862943,
    'oxidizer_density': 1141.16,
    'propellant_tanks': {'oxidizer_tank': {
        'dimensions': {'volume': 210.3542056603267, 'diameter': 475.0,
                       'length': 1188.0},
        'propellant_data': {'volume_required': 199.83649537731034,
                            'ullage_volume': 10.517710283016346},
        'slosh': {'radius': 0.23747092328741232,
                  'fill_height': 1.1279868856152082, 'g_eff': 9.80665,
                  'f1_hz': 1.3877962867846818,
                  'baffle': {'width_ratio': 0.7499999999999999,
                             'depth_ratio': 1.4166666666666654}}}},
    'feed_system': {'tank_pressure_bar': 3.647085446646845,
                    'pressurization': {'type': 'helium'}},
    'detailed_feed_system': {'valve_feedline': {'oxidizer_line': {
        'inlet_pressure_bar': 72.81102026883069,
        'water_hammer_fluid_key': 'lox',
        'pipe_materials': {'structural_key': 'ss_304'},
        'line': {'inputs': {'line_id_m': 0.025, 'line_length_m': 2.5,
                            'mass_flow_kg_s': 6.610012030862943}}}}},
}
PANEL_SAYI_KATI_ALTKUME = {'chamber_pressure': 40, 'c_star': 868.7501711118585}

#: Sekmenin görünür SEÇİM varsayılanları (sayı değil; ekranda seçili duran
#: seçenek). Sayı alanlarının HEPSİ boş doğmalı.
SECIM_VARSAYILANI = {
    ('pressurant', 'mode'): 'regulated', ('pressurant', 'gas'): 'helium',
    ('water_hammer', 'fluid'): 'water',
    ('water_hammer', 'pipe_material'): 'ss_304',
    ('water_hammer', 'working_pressure_reference'): '',
}


def _node(tmp_path, govde):
    betik = tmp_path / 'k.js'
    betik.write_text(
        "global.window = global; global.document = {getElementById(){return null;},"
        " addEventListener(){}, readyState: 'complete'};\n"
        "require(%s); require(%s);\n" % (json.dumps(str(JS / 'analysis_dock.js')),
                                         json.dumps(str(JS / 'panels' / 'feed_panel.js')))
        + govde, encoding='utf-8')
    p = subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_besleme_uc_sekme_sayi_alanlari_sayisiz_dogar(tmp_path):
    o = _node(tmp_path,
              "process.stdout.write(JSON.stringify(window.FeedPanel._tabs.map(t =>"
              " [t.key, t.fields.map(f => [f[0], f[2], Array.isArray(f[3])])])));\n")
    sayili, secim = [], {}
    for sekme, alanlar in o:
        for ad, varsayilan, secim_mi in alanlar:
            if secim_mi:
                secim[(sekme, ad)] = varsayilan
            elif varsayilan != '':
                sayili.append((sekme, ad, varsayilan))
    assert not sayili, f'gizli sayıyla doğan alanlar: {sayili}'
    assert secim == SECIM_VARSAYILANI


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
@pytest.mark.parametrize('tip, motor, beklenen', [
    ('hybrid', PANEL_SAYI_HIBRIT_ALTKUME, {
        'slosh': {'radius': 0.2120908273275041 / 2,
                  'fill_height': 0.4506930080709462, 'g_eff': 9.80665,
                  'fluid_density': 785.1039703874173,
                  'baffle_depth_ratio': 0.1},
        # N2O tankı kendinden basınçlı: depolanmış gaz sisteminin karşılığı yok
        'pressurant': {},
        'water_hammer': {'fluid': 'n2o', 'mdot_kg_s': 1.2500910562567924,
                         'working_pressure_bar': 50.543358499999975}}),
    ('liquid', PANEL_SAYI_SIVI_ALTKUME, {
        'slosh': {'radius': 0.23747092328741232,
                  'fill_height': 1.1279868856152082, 'g_eff': 9.80665,
                  'baffle_width_ratio': 0.7499999999999999,
                  'baffle_depth_ratio': 1.4166666666666654,
                  'fluid_density': 1141.16},
        'pressurant': {'propellant_volume': 199.83649537731034 / 1000,
                       'initial_ullage_volume': 10.517710283016346 / 1000,
                       'tank_pressure': 3.647085446646845, 'gas': 'helium'},
        'water_hammer': {'fluid': 'lox', 'line_length_m': 2.5,
                         'line_id_mm': 0.025 * 1000,
                         'working_pressure_bar': 72.81102026883069,
                         'mdot_kg_s': 6.610012030862943,
                         'pipe_material': 'ss_304'}}),
    # Katı motorda sıvı besleme hattı yok: hiçbir alan doldurulmaz (eskiden
    # çalışma basıncına Pc = 40 bar yazılıyordu).
    ('solid', PANEL_SAYI_KATI_ALTKUME, {'water_hammer': {}}),
])
def test_besleme_tohumu_yalniz_motorun_kendi_sayisi(tmp_path, tip, motor, beklenen):
    o = _node(tmp_path,
              "const m = %s; const out = {};\n"
              "window.FeedPanel._tabs.forEach(t => { if (t.motorTypes.indexOf(%s) !== -1)"
              " out[t.key] = t.suggest(m); });\n"
              "process.stdout.write(JSON.stringify(out));\n"
              % (json.dumps(motor), json.dumps(tip)))
    assert set(o) == set(beklenen)
    for sekme, tohum in beklenen.items():
        # BİT-AYNI: tolerans yok (== ile); anahtar kümesi de tam.
        assert o[sekme] == tohum, (sekme, o[sekme])


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_besleme_tohumu_sayi_yuvarlamaz_ve_pc_yazmaz():
    src = (JS / 'panels' / 'feed_panel.js').read_text(encoding='utf-8')
    assert 'toPrecision(4)' not in src
    assert 'Math.round(rho)' not in src
    assert 'sug.tank_pressure = Number(m.chamber_pressure' not in src
    assert 'sug.working_pressure_bar = Number(m.chamber_pressure' not in src


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


def _post(istemci, yol, govde):
    r = istemci.post(yol, json=govde)
    return r.status_code, r.get_json()


@pytest.mark.parametrize('yol, govde, alan', [
    ('/api/pressurant-sizing', {'tank_pressure': 30}, 'propellant_volume'),
    ('/api/pressurant-sizing', {'propellant_volume': 0.5}, 'tank_pressure'),
    ('/api/pressurant-sizing', {'mode': 'blowdown', 'propellant_volume': 0.5,
                                'initial_pressure': 30}, 'initial_ullage_volume'),
    ('/api/pressurant-sizing', {'mode': 'blowdown', 'propellant_volume': 0.5,
                                'initial_ullage_volume': 0.1}, 'initial_pressure'),
    ('/api/water-hammer', {'line_id_mm': 25, 'wall_thickness_mm': 2,
                           'working_pressure_bar': 20, 'mdot_kg_s': 5},
     'line_length_m'),
    ('/api/water-hammer', {'line_length_m': 20, 'line_id_mm': 25,
                           'working_pressure_bar': 20, 'mdot_kg_s': 5},
     'wall_thickness_mm'),
    ('/api/water-hammer', {'line_length_m': 20, 'line_id_mm': 25,
                           'wall_thickness_mm': 2, 'mdot_kg_s': 5},
     'working_pressure_bar'),
    ('/api/slosh-analysis', {'fill_height': 0.3}, 'radius'),
])
def test_zorunlu_alan_bossa_adiyla_red(istemci, yol, govde, alan):
    kod, j = _post(istemci, yol, govde)
    assert kod == 400
    assert f"'{alan}' is required" in j['error']


def test_basinclandirici_bos_alan_varsayilani_beyanli_ve_tek_kaynak(istemci):
    from hrma.analysis import pressurant_sizing as ps
    sig = inspect.signature(ps.regulated_pressurant).parameters
    kod, j = _post(istemci, '/api/pressurant-sizing',
                   {'propellant_volume': 0.5, 'tank_pressure': 30})
    assert kod == 200
    beyan = {k['field']: k['value'] for k in j['defaults_applied']}
    assert beyan == {
        'mode': 'regulated', 'gas': sig['gas'].default,
        'initial_temperature': sig['initial_temperature'].default,
        'storage_pressure': sig['storage_pressure'].default / 1e5,
        'regulator_margin': sig['regulator_margin'].default,
        'collapse_factor': sig['collapse_factor'].default,
        'expulsion_efficiency': sig['expulsion_efficiency'].default}
    # Beyan edilen sayılar GERÇEKTEN uygulananlardır: aynı değerler açıkça
    # gönderildiğinde sonuç bit-aynı ve künye yok.
    acik = {'propellant_volume': 0.5, 'tank_pressure': 30, 'mode': 'regulated',
            'gas': 'helium', 'initial_temperature': 293.15,
            'storage_pressure': 200.0, 'regulator_margin': 0.1,
            'collapse_factor': 1.0, 'expulsion_efficiency': 0.95}
    kod2, j2 = _post(istemci, '/api/pressurant-sizing', acik)
    assert kod2 == 200 and 'defaults_applied' not in j2
    assert j2['pressurant'] == j['pressurant']

    sig_b = inspect.signature(ps.blowdown_pressurant).parameters
    kod, j = _post(istemci, '/api/pressurant-sizing', {
        'mode': 'blowdown', 'propellant_volume': 0.5,
        'initial_ullage_volume': 0.1, 'initial_pressure': 30})
    assert kod == 200
    assert {k['field']: k['value'] for k in j['defaults_applied']} == {
        'gas': sig_b['gas'].default,
        'initial_temperature': sig_b['initial_temperature'].default,
        'polytropic_n': sig_b['polytropic_n'].default}


def test_su_kocu_bos_alan_varsayilani_beyanli(istemci):
    from hrma.analysis import water_hammer as wh
    govde = {'line_length_m': 20, 'line_id_mm': 25, 'wall_thickness_mm': 2,
             'working_pressure_bar': 20, 'mdot_kg_s': 5}
    kod, j = _post(istemci, '/api/water-hammer', govde)
    assert kod == 200
    beyan = {k['field']: k['value'] for k in j['defaults_applied']}
    assert beyan == {'fluid': 'water', 'pipe_material': wh.DEFAULT_PIPE_MATERIAL,
                     'valve_closure_time_ms': None}
    assert j['water_hammer']['closure_regime'] == 'instantaneous'
    kod2, j2 = _post(istemci, '/api/water-hammer', dict(
        govde, fluid='water', pipe_material='ss_304', valve_closure_time_ms=50))
    assert kod2 == 200 and 'defaults_applied' not in j2


def test_calkalanma_bos_alan_varsayilani_beyanli_tek_kaynak(istemci):
    from hrma.analysis.slosh_analysis import CylindricalTankSlosh
    from hrma.constants import G_0
    d_r = inspect.signature(CylindricalTankSlosh.analyze).parameters[
        'baffle_depth_ratio'].default
    kod, j = _post(istemci, '/api/slosh-analysis',
                   {'radius': 0.1, 'fill_height': 0.3})
    assert kod == 200
    assert {k['field']: k['value'] for k in j['defaults_applied']} == {
        'g_eff': G_0, 'baffle_depth_ratio': d_r}
    kod2, j2 = _post(istemci, '/api/slosh-analysis', {
        'radius': 0.1, 'fill_height': 0.3, 'g_eff': G_0,
        'baffle_depth_ratio': d_r})
    assert 'defaults_applied' not in j2
    assert j2['slosh'] == j['slosh']


def test_sivi_calkalanma_tohumu_motor_blogu_ile_bit_ayni(istemci):
    """C2 AÇIK 4: sıvı tohumu tank boyu × 0,9 (HRMA seçimi) yerine motorun
    KENDİ bloğundan; panelin f1'i motor bloğunun f1'iyle BİT-AYNI."""
    s = PANEL_SAYI_SIVI_ALTKUME['propellant_tanks']['oxidizer_tank']['slosh']
    kod, j = _post(istemci, '/api/slosh-analysis', {
        'radius': s['radius'], 'fill_height': s['fill_height'],
        'g_eff': s['g_eff'], 'baffle_width_ratio': s['baffle']['width_ratio'],
        'baffle_depth_ratio': s['baffle']['depth_ratio'],
        'fluid_density': PANEL_SAYI_SIVI_ALTKUME['oxidizer_density']})
    assert kod == 200
    assert j['slosh']['f1_hz'] == s['f1_hz']


# ===========================================================================
# Kalem 2 (S1, yayın kapısı 6) — Nozul Akışı paneli ⟷ ana sonuç.
# ÖLÇÜLDÜ (``olcum/akis_once_tr.json``): kartlar çözücünün İDEAL sayılarını
# "İTKİ / KÜTLE DEBİSİ / C*" adlarıyla basıyordu (hibrit 3150 N / 1,323 kg/s /
# 1602 m/s ⟷ ana sonuç 3000 N / 1,458 kg/s / 1423 m/s). Çözümün sayıları artık
# İDEAL adıyla; motorun teslim ettiği dört sayı (itki, ṁ, c*, C_F) yanında,
# motor sonucundan AYNEN. Bekçi: 3 örnek × 4 büyüklük.
# ===========================================================================
AKIS_ORNEKLERI = {
    # tip: (motor sonucu alt kümesi, panelin gönderdiği girdiler [güverte
    # 6 anlamlı basamağa yuvarlar], beklenen teslim kartları)
    'hybrid': ({'motor': {
        'thrust': 3000, 'mdot_total': 1.4584395656329243,
        'c_star': 1423.4660813865244, 'cf': 1.445059381725385,
        'chamber_pressure': 30, 'chamber_temperature': 3279.1065982467817,
        'gamma': 1.1690051112174868, 'molecular_weight': 25.747551775840186,
        'throat_diameter': 0.029984663165237336,
        'exit_diameter': 0.06729136655547291}},
        {'chamber_pressure_Pa': 3000000.0, 'chamber_temperature_K': 3279.11,
         'gamma': 1.16901, 'molecular_weight_g_mol': 25.7476,
         'throat_diameter_m': 0.0299847, 'exit_diameter_m': 0.0672914},
        [('3000', 'N'), ('1.458', 'kg/s'), ('1423', 'm/s'), ('1.445', '')]),
    'liquid': ({
        'thrust': 25000, 'total_mass_flow': 9.915018046294414,
        'c_star': 1738.3017951696318,
        'isp_identity': {'thrust_coefficient_sea_level': 1.4215017434862889},
        'chamber_pressure': 50, 'chamber_temperature': 3328.4475602858874,
        'gamma': 1.2134176416309834, 'molecular_weight': 20.798693407243352,
        'throat_diameter': 0.06692160729816303,
        'exit_diameter': 0.2318232479291811},
        {'chamber_pressure_Pa': 5000000.0, 'chamber_temperature_K': 3328.45,
         'gamma': 1.21342, 'molecular_weight_g_mol': 20.7987,
         'throat_diameter_m': 0.0669216, 'exit_diameter_m': 0.231823},
        [('25000', 'N'), ('9.915', 'kg/s'), ('1738.3', 'm/s'), ('1.422', '')]),
    'solid': ({
        'design_summary': {'performance': {'peak_thrust_N': 1498.1941000586567}},
        'average_thrust': 1298.539636737809, 'c_star': 868.7501711118585,
        'nozzle_design': {'performance': {'thrust_coefficient': 1.4365945232758703}},
        'chamber_pressure': 40, 'chamber_temperature': 1695.9672585892881,
        'gamma': 1.1206313486780823,
        'thermochemistry': {'molecular_weight': 42.145468051754584},
        'throat_diameter': 18.404533333401833, 'exit_diameter': 47.81772109380214},
        {'chamber_pressure_Pa': 4000000.0, 'chamber_temperature_K': 1695.97,
         'gamma': 1.12063, 'molecular_weight_g_mol': 42.1455,
         'throat_diameter_m': 0.0184045, 'exit_diameter_m': 0.0478177},
        # katı: tasarım Pc'sindeki (tepe) itki; tasarım debisi başlık değil
        [('1498', 'N'), ('869', 'm/s'), ('1.437', '')]),
}


def _akis_node(tmp_path, tip, sonuc, girdi):
    betik = tmp_path / 'a.js'
    betik.write_text(
        "global.window = global; global.document = {getElementById(){return null;},"
        " addEventListener(){}, readyState: 'complete'};\n"
        "global.fetch = () => Promise.resolve({ok: false});\n"
        "require(%s); require(%s);\n" % (json.dumps(str(JS / 'analysis_dock.js')),
                                         json.dumps(str(JS / 'panels' / 'flow_panel.js')))
        + "window.AnalysisDock._setMotorType(%s);\n" % json.dumps(tip)
        + "window.currentResults = %s;\n" % json.dumps(sonuc)
        + "const h = window.FlowPanel._teslimBlogu({inputs: %s});\n" % json.dumps(girdi)
        + "const farkli = window.FlowPanel._teslimBlogu({inputs: Object.assign({}, %s,"
          " {chamber_pressure_Pa: 4100000.0})});\n" % json.dumps(girdi)
        + "process.stdout.write(JSON.stringify({h: h, farkli: farkli}));\n",
        encoding='utf-8')
    p = subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
@pytest.mark.parametrize('tip', sorted(AKIS_ORNEKLERI))
def test_akis_paneli_teslim_sayilari_ana_sonucla_ayni(tmp_path, tip):
    import re
    sonuc, girdi, beklenen = AKIS_ORNEKLERI[tip]
    o = _akis_node(tmp_path, tip, sonuc, girdi)
    kartlar = re.findall(r'>\s*([^<>]+?)<span[^>]*>\s*([^<]*)</span>', o['h'])
    degerler = [(d.strip(), b.strip()) for d, b in kartlar]
    assert degerler == beklenen, degerler
    # Girdi motorunkinden farklıysa motorun sayısı o çözümün yanına KONMAZ.
    assert 'differ from the motor result' in o['farkli']
    assert '<span' not in o['farkli']


def test_akis_paneli_ideal_sayilar_ideal_adiyla():
    src = (JS / 'panels' / 'flow_panel.js').read_text(encoding='utf-8')
    # Çıplak "THRUST" / "MASS FLOW" / "C*" kartı çözücünün ideal sayısını
    # BASMAZ (aynı ad ana sonuçta teslim sayısıdır).
    assert "U.statCard(T('common.thrust', 'THRUST'), U.fmt(perf.thrust_N" not in src
    assert "U.statCard(T('common.massFlow', 'MASS FLOW'), U.fmt(perf.mass_flow_kg_s" not in src
    assert "U.statCard('C*', U.fmt(perf.c_star_m_s" not in src
    for anahtar in ('panel.nzl.thrustIdeal', 'panel.nzl.massFlowIdeal',
                    'panel.nzl.cstarIdeal', 'panel.nzl.cf1d'):
        assert anahtar in src


def test_akis_paneli_yuksek_dogruluk_iddiasi_yok():
    """KILAVUZ P12: kinetik seçeneğinin adı modelin ne yaptığını söyler."""
    import re
    src = (JS / 'panels' / 'flow_panel.js').read_text(encoding='utf-8')
    assert not re.search(r'(?i)high[-\s]fidelity', src)
    sozluk = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    satirlar = [s for s in sozluk.splitlines() if "'nzl.kinHigh'" in s]
    assert len(satirlar) == 2
    for s in satirlar:
        assert not re.search(r'(?i)high[-\s]fidelity|yüksek doğruluk', s), s


# ===========================================================================
# Kalem 3 — Kararlılık paneli (FİZİK-2 DEVİR 5): yazı çakışması ve TR ekranda
# İngilizce. ÖLÇÜLDÜ (``olcum/kararlilik_sonra``; kapalı <details> içeriği
# sayılmadan, C2 kart_olcum.py süzgeci): önce 1280/1440 × TR/EN 4-5 çift
# (nötr eğri y-başlığı ⟷ grafik başlığı; kök yeri lejantı ⟷ x-başlığı),
# sonra 0. Kök neden: tema (plotly_dark.js YAZI_TABANI) eksen başlığını 14,
# tiki 12 px'e yükseltiyor, panel sarmayı 11 / 10 px ile yapıyordu; Plotly
# y <= 1/3'te lejantı ALT kenarından bağlıyordu.
# ===========================================================================
def _kararlilik_node(tmp_path, govde, i18n=None):
    betik = tmp_path / 'k.js'
    betik.write_text(
        "global.window = global; global.document = {getElementById(){return null;},"
        " addEventListener(){}, readyState: 'complete',"
        " createElement(){ return {getContext(){ return null; }}; }};\n"
        "window.AnalysisCenter = {registerTenant(){}, register(){}};\n"
        + (i18n or '')
        + "require(%s); require(%s);\n" % (
            json.dumps(str(JS / 'analysis_dock.js')),
            json.dumps(str(JS / 'panels' / 'stability_panel.js')))
        + govde, encoding='utf-8')
    p = subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_kararlilik_grafik_olcusu_tema_puntosuyla_ayni(tmp_path):
    import re
    tema = (JS / 'plotly_dark.js').read_text(encoding='utf-8')
    m = re.search(r'YAZI_TABANI\s*=\s*\{\s*tik:\s*(\d+),\s*eksenBasligi:\s*(\d+),'
                  r'\s*baslik:\s*(\d+)', tema)
    assert m, 'tema yazı tabanı bulunamadı'
    tik, eksen, baslik = (int(x) for x in m.groups())
    o = _kararlilik_node(tmp_path,
        "process.stdout.write(JSON.stringify(window.StabilityPanel._axisMetrics));\n")
    assert o['tickFontPx'] == tik
    assert o['titleFontPx'] == eksen
    assert o['chartTitleFontPx'] == baslik


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_kok_yeri_lejanti_x_basliginin_altinda(tmp_path):
    veri = {'mode': 'chug', 'assessment': {'frequency_hz': 115.7,
                                           'dp_ratio_j': 0.4},
            'root_locus': {'dp_ratio_j': [0.3, 0.4, 0.5],
                           'sigma_1_s': [-80.0, -57.5, -20.0],
                           'frequency_hz': [114.0, 115.7, 117.0]}}
    o = _kararlilik_node(tmp_path,
        "const f = window.StabilityPanel._rootLocusFigure(%s, 351);\n"
        "const m = window.StabilityPanel._axisMetrics;\n"
        "process.stdout.write(JSON.stringify({lay: f.layout, n: f.traces.length, m: m}));\n"
        % json.dumps(veri))
    lay, m = o['lay'], o['m']
    assert lay['legend']['yanchor'] == 'top'
    blok = m['legendGapPx'] + o['n'] * m['legendRowPx'] + m['legendPadPx']
    x_marj = lay['margin']['b'] - blok
    cizim_h = lay['height'] - lay['margin']['t'] - lay['margin']['b']
    # Lejant x-başlık bölgesinin ALTINDAN başlar ve kendi bloğu marja dahil.
    assert lay['legend']['y'] == pytest.approx(
        -(x_marj + m['legendGapPx']) / cizim_h, rel=1e-12)
    assert lay['margin']['t'] >= m['titledTopMarginPx']


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_kararlilik_hukum_rozeti_ekran_dilinde(tmp_path):
    # I18N taklidi: anahtarı döndürür — rozetin SÖZLÜKTEN kurulduğu ölçülür.
    taklit = ("window.I18N = {lang: 'tr', t: (k, f) => 'T[' + k + ']',"
              " tf: (k, p, f) => k + '|' + JSON.stringify(p),"
              " serverText: (x) => x};\n")
    veri = {'mode': 'chug', 'assessment': {
        'verdict': 'marginal',
        'verdict_scope': 'feed-coupled chug (modeled mechanism only), '
                         'inertance-free feed line'}}
    o = _kararlilik_node(tmp_path,
        "process.stdout.write(JSON.stringify(window.StabilityPanel._chugVerdict(%s)));\n"
        % json.dumps(veri), i18n=taklit)
    # Tanınan (hüküm, kapsam) çifti TEK anahtar, parametresiz: Analiz
    # Merkezi rozeti dil değişiminde {key} ile yeniden basar (parametre
    # koşumun diline donmaz).
    assert o['key'] == 'panel.stab.verdictBadge.marginalChugNoInertance'
    # parametreler ham (karar 1 disiplini), sözlük metni onları kullanmaz
    assert o['params'] == {'verdict': 'MARGINAL',
                           'scope': veri['assessment']['verdict_scope']}
    sozluk = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    assert ("'panel.stab.verdictBadge.marginalChugNoInertance': 'SINIRDA — "
            "besleme bağlaşımlı chug (yalnız modellenen mekanizma), ataletsiz "
            "besleme hattı'") in sozluk
    # Tanınmayan kapsam: genel kalıp, hüküm kelimesi yine sözlükten.
    veri['assessment']['verdict_scope'] = 'some future scope'
    o2 = _kararlilik_node(tmp_path,
        "process.stdout.write(JSON.stringify(window.StabilityPanel._chugVerdict(%s)));\n"
        % json.dumps(veri), i18n=taklit)
    assert o2['key'] == 'panel.stab.verdictScoped'
    assert o2['params']['verdict'] == 'T[panel.stab.verdictWord.marginal]'
    assert o2['params']['scope'] == 'some future scope'


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_akis_rejim_cumlesi_tr_ozet_ve_kapali_ayrinti(tmp_path):
    betik = tmp_path / 'r.js'
    betik.write_text(
        "global.window = global; global.document = {getElementById(){return null;},"
        " addEventListener(){}, readyState: 'complete'};\n"
        "global.fetch = () => Promise.resolve({ok: false});\n"
        "require(%s); require(%s);\n" % (json.dumps(str(JS / 'analysis_dock.js')),
                                         json.dumps(str(JS / 'panels' / 'flow_panel.js')))
        + "window.I18N = {lang: 'tr', t: (k, f) => 'T[' + k + ']'};\n"
        "const r = {type: 'perfectly_expanded', description: 'Perfectly expanded: x.'};\n"
        "const tr = window.FlowPanel._rejimCumlesiHtml(r);\n"
        "window.I18N.lang = 'en';\n"
        "const en = window.FlowPanel._rejimCumlesiHtml(r);\n"
        "process.stdout.write(JSON.stringify({tr: tr, en: en}));\n",
        encoding='utf-8')
    p = subprocess.run([NODE, str(betik)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout)
    assert o['tr'].startswith('T[panel.nzl.regimeDesc.perfectly_expanded]')
    assert '<details' in o['tr'] and 'Perfectly expanded: x.' in o['tr']
    assert o['en'] == 'Perfectly expanded: x.'


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_besleme_adli_ret_ekran_dilinde(tmp_path):
    """Alanlar sayısız doğduğu için boş zorunlu alanın adlı reddi olağan yol;
    ÖLÇÜLDÜ: TR ekranda "HATA: 'propellant_volume' is required (m^3)"
    basılıyordu. Ret, alanın EKRANDAKİ etiketiyle sözlükten basılır."""
    o = _node(tmp_path,
              "window.I18N = {lang: 'tr', t: (k, f) => 'T[' + k + ']',"
              " tf: (k, p, f) => k + '|' + JSON.stringify(p), serverText: (x) => x};\n"
              "const t = window.FeedPanel._tabs.filter(x => x.key === 'pressurant')[0];\n"
              "process.stdout.write(JSON.stringify({ret: window.FeedPanel._retMetni(t,"
              " {status: 'error', error: \"'propellant_volume' is required (m^3)\"}, 400)}));\n")
    assert o['ret'].startswith('panel.feed.requiredEmpty|')
    assert 'T[panel.feed.fPropVolume]' in o['ret']
    assert 'is required' not in o['ret']


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_besleme_cozucu_duzyazisi_tr_ekranda_kapali_ayrinti(tmp_path):
    o = _node(tmp_path,
              "const F = window.FeedPanel;\n"
              "window.I18N = {lang: 'tr', t: (k, f) => f, tf: (k, p, f) => k,"
              " serverText: (x) => x};\n"
              "const tr = F._duzyaziBlok('Model', ['Regulated stored-gas system sized'], 'dim');\n"
              "const kodlu = F._duzyaziBlok('W', [{code: 'warn.x', params: {}}], 'warn');\n"
              "window.I18N.lang = 'en';\n"
              "const en = F._duzyaziBlok('Model', ['Regulated stored-gas system sized'], 'dim');\n"
              "process.stdout.write(JSON.stringify({tr: tr, en: en, kodlu: kodlu}));\n")
    assert o['tr'].startswith('<details') and 'panel.feed.proseUntranslated' in o['tr']
    assert 'Regulated stored-gas system sized' in o['tr']      # metin AYNEN kutuda
    assert '<details' not in o['en']
    assert '<details' not in o['kodlu']                          # kodlu uyarı çevrilir
