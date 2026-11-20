"""V307/ONARIM-İTKİ-A — mühendis turu (19 Kas) itki bulgularının bekçileri.

Bulgular (ayrıntı: ~/HRMA-calisma/2026-11-19/MUHENDIS-ITKI/BULGULAR.md;
kanıt: docs/scofield/raw/OH/V307/onarim-itki-a/):

* M7-ITKI-12 — hibrit sayfası boş İrtifa + Ortam Basıncı alanında sessizce
  1,013 bar gönderiyordu (``|| 1.013``; ISA 1,01325 değil).
* M7-ITKI-7 — güverte PERFORMANS Mach konturu motorun tasarım ortamı
  kaydını okumuyor, vakum tasarımını 1 atm'de "separated" çiziyordu.
* M7-ITKI-8 — güvertenin ilk koşusu (3B yüzey) itici kimliğini taşımıyor,
  yüzey N2O/HTPB referans çiftiyle çözülüyordu; hibrit sonucunda üst düzey
  ``oxidizer_type`` yok.
* M7-ITKI-1 — "deniz seviyesinde yapışık kalan en büyük ε" girilen lülenin
  γ'sıyla çözülüyordu (13,36 ⟷ 13,51); kök artık γ(ε) ile öz-tutarlı.
"""
import contextlib
import io
import json
import pathlib
import re
import shutil
import subprocess
import warnings

import pytest

KOK = pathlib.Path(__file__).resolve().parent.parent
HOST = {'Host': '127.0.0.1:8080'}
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _js_islevi(html, ad):
    m = re.search(r'\n\s*function %s\s*\(' % re.escape(ad), html)
    assert m, ad
    i = html.index('{', m.end() - 1)
    d = 0
    for j in range(i, len(html)):
        d += {'{': 1, '}': -1}.get(html[j], 0)
        if d == 0:
            return html[m.start():j + 1]
    raise AssertionError(ad)


# ===========================================================================
# M7-ITKI-12 — hibrit tek irtifa kipinde gizli 1,013 bar yok
# ===========================================================================
def _advanced():
    return (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')


def test_itki12_tek_irtifa_kipinde_sayisal_yedek_yok():
    html = _advanced()
    i = html.index('// Single altitude mode - don\'t send altitude_profile')
    blok = html[i:html.index('// altitudeProfile stays null', i)]
    blok = re.sub(r'//[^\n]*', '', blok)          # yorumlar sayılmaz
    assert not re.search(r'\|\|\s*[0-9]', blok), blok
    assert not re.search(r'\?\?\s*[0-9]', blok), blok
    # Alanın kendi varsayılan değeri de sayı taşımaz (açılışta
    # updateSinglePressure irtifadan ISA basıncını yazar).
    alan = re.search(r'<input[^>]*id="single_pressure"[^>]*>', html).group(0)
    assert 'value=' not in alan, alan


@pytest.mark.skipif(NODE is None, reason='node yok')
@pytest.mark.parametrize('irtifa, basinc, beklenen', [
    ('', '', None),                 # ikisi boş -> null (adıyla ret)
    ('0', '', 1.01325),             # basınç boş, irtifa 0 -> ISA 0 m
    ('', '0.5', 0.5),               # girilen basınç aynen
])
def test_itki12_getformdata_tek_irtifa_basinci(irtifa, basinc, beklenen):
    html = _advanced()
    blok = re.search(r'var ISA_LAYERS_JS = \[.*?var ISA_TABLE_TOP_M_JS = '
                     r'[0-9.]+;', html, re.S).group(0)
    parca = [blok] + [_js_islevi(html, ad) for ad in
                      ('_isaLayerJS', '_isaPressurePaJS', 'altitudeToPressure',
                       'updateSinglePressure')]
    i = html.index('// Single altitude mode - don\'t send altitude_profile')
    tek = html[i:html.index('// altitudeProfile stays null', i)]
    kod = '\n'.join(parca) + r"""
var alanlar = {single_altitude: {value: %s}, single_pressure: {value: %s}};
var document = {getElementById: function (id) { return alanlar[id] || null; }};
var pressureIsSiteSpecific = false;
function refreshPressureModeLabels() {}
var ambientPressure = 'ayarlanmadi';
%s
// irtifa alanı boşaltılınca basınç alanına "NaN" yazılmaz
var once = alanlar.single_pressure.value;
alanlar.single_altitude.value = '';
updateSinglePressure();
console.log(JSON.stringify({p: ambientPressure, sonra: alanlar.single_pressure.value}));
""" % (json.dumps(irtifa), json.dumps(basinc), tek)
    cp = subprocess.run([NODE, '-'], input=kod, capture_output=True,
                        text=True, timeout=60)
    assert cp.returncode == 0, cp.stderr
    sonuc = json.loads(cp.stdout)
    assert sonuc['p'] == beklenen
    assert sonuc['sonra'] == ''


def test_itki12_bos_basinc_adiyla_reddedilir():
    """validateFormData ``atmospheric_pressure``'ı zorunlu sayar: null
    gövde istek gönderilmeden alanın adıyla durur (sayı varsayılmaz)."""
    html = _advanced()
    v = _js_islevi(html, 'validateFormData')
    assert re.search(r"'atmospheric_pressure':\s*\['adv\.js\.atmosphericPressure'",
                     v)


# ===========================================================================
# M7-ITKI-7 — Mach konturu motorun tasarım ortamını okur
# ===========================================================================
#: Mühendis turu L6_vak_perf panel isteği (sıvı örnek, ε 61, vakum).
ITKI7_L6_MACH = {
    'chamber_pressure': 50, 'optimal_of_ratio': 2, 'base_isp': 322.438,
    'expansion_ratio': 61, 'throat_area': 0.00274488,
    'chamber_length': 0.270135, 'burn_time': 30,
    'chamber_temperature': 3328.45, 'gamma': 1.21826,
    'molecular_weight': 20.7987, 'mdot_total': 7.90628,
    'chamber_diameter': 0.118235, 'fuel_type': 'rp1', 'oxidizer_type': 'lox',
    'analysis_type': 'nozzle_mach'}


def _mach_basligi(client, govde):
    r = _sessiz(client.post, '/api/advanced-performance-analysis',
                json=govde, headers=HOST)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    fig = json.loads(r.get_json()['plot_data'])
    return fig['layout']['title']['text']


def test_itki7_vakum_tasarimi_vakumda_cozulur(client):
    b = _mach_basligi(client, dict(ITKI7_L6_MACH, design_ambient={'mode': 'vacuum'}))
    assert 'regime: underexpanded' in b, b
    assert 'isentropic exit M = 4.66' in b, b
    assert 'separated' not in b and 'effective exit M' not in b, b
    assert 'ambient = 1 atm' not in b, b
    assert 'Ambient: design ambient of the motor, vacuum' in b, b


@pytest.mark.parametrize('kayit, etiket', [
    ({'mode': 'sea_level'}, 'sea level'),
    ({'mode': 'pressure', 'pressure_bar': 0.5}, '0.5000 bar design ambient'),
    ({'mode': 'altitude', 'altitude_m': 20000, 'pressure_bar': 0.0553},
     '20000 m design altitude (0.0553 bar)'),
])
def test_itki7_ortam_kaydi_adiyla_yazilir(client, kayit, etiket):
    b = _mach_basligi(client, dict(ITKI7_L6_MACH, design_ambient=kayit))
    assert 'Ambient: design ambient of the motor, ' + etiket in b, b
    assert 'ambient = 1 atm' not in b, b


def test_itki7_kayit_yoksa_varsayim_adiyla_kalir(client):
    b = _mach_basligi(client, dict(ITKI7_L6_MACH))
    assert 'ambient = 1 atm (sea level)' in b, b


def test_itki7_acik_basinc_kayittan_once_gelir(client):
    b = _mach_basligi(client, dict(ITKI7_L6_MACH, ambient_pressure_bar=1.01325,
                                   design_ambient={'mode': 'vacuum'}))
    assert 'Ambient: design ambient' not in b and 'separated' in b, b


def test_itki7_bozuk_kayit_adiyla_reddedilir(client):
    r = _sessiz(client.post, '/api/advanced-performance-analysis',
                json=dict(ITKI7_L6_MACH, design_ambient={'mode': 'mars'}),
                headers=HOST)
    assert r.status_code == 422
    alanlar = [x['field'] for x in r.get_json()['invalid_fields']]
    assert 'design_ambient.mode' in alanlar


def test_itki7_kayit_basinci_tek_tanimdan():
    from hrma.constants import P_SEA_LEVEL_PA, isa_pressure_geometric
    from hrma.visualization.visualization import design_ambient_pressure_pa
    assert design_ambient_pressure_pa({'mode': 'sea_level'}) == P_SEA_LEVEL_PA
    assert design_ambient_pressure_pa({'mode': 'vacuum'}) == 0.0
    assert design_ambient_pressure_pa(
        {'mode': 'altitude', 'altitude_m': 10000.0}) == \
        isa_pressure_geometric(10000.0)
    assert design_ambient_pressure_pa({'mode': 'undeclared'}) is None
    assert design_ambient_pressure_pa(None) is None


# ===========================================================================
# M7-ITKI-8 — güvertenin ilk koşusu itici kimliğini ve ortamı taşır
# ===========================================================================
_EV8 = r"""
var out = {};
window.AnalysisDock.init({motorType: body.tip,
    resultsProvider: function () { return body.sonuc; }});
var specP = window.AnalysisDock._registry.filter(function (s) {
    return s.id === 'performance'; })[0];
var gonderilen = [];
window.fetch = function (url, opts) {
    gonderilen.push({url: url, body: opts && opts.body});
    return new Promise(function () {});
};
var sug = specP.fromResults(body.sonuc);
out.contextVar = typeof specP.contextFromResults === 'function';
out.kimlik = window.PerformancePanel._propellantIdentity(body.sonuc.motor);
// Güvertenin kurduğu gövde = öneriler (applySuggestions + buildPayload).
out.baglam = out.contextVar ? specP.contextFromResults(body.sonuc, sug) : null;
var elle = JSON.parse(JSON.stringify(sug)); elle.base_isp = 250;
out.baglamElle = out.contextVar ? specP.contextFromResults(body.sonuc, elle) : null;
var root = document.createElement('div');
specP.render({status: 'success', plot_data: JSON.stringify({data: [], layout: {}})}, root);
out.ek = gonderilen.map(function (g) { return JSON.parse(g.body); });
return out;
"""


def _node8(data):
    from tests.support.kanit import kanit_gerekli
    import tests.test_v3_yapi_sf as T
    if NODE is None:
        pytest.skip('node yok')
    cfg = {'panelId': '_yok',
           'panelFiles': ['hrma/static/js/panels/performance_panel.js'],
           'dataInline': data, 'evalFn': _EV8}
    p = subprocess.run([NODE, kanit_gerekli(str(T._PANEL_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    ev = json.loads(p.stdout)['evaled']
    assert '_err' not in ev, ev.get('_err')
    return ev


#: Hibrit sonucunun ilgili alanları (mühendis turu H4_perf yanıtından):
#: üst düzey yalnız ``fuel_type``; oksitleyici çözücü girdisinde.
ITKI8_HIBRIT_SONUC = {'motor': {
    'fuel_type': 'htpb',
    'combustion_analysis': {'inputs': {'fuel_type': 'htpb',
                                       'oxidizer_type': 'n2o'}},
    'chamber_pressure': 30.0, 'of_ratio': 6.0, 'isp': 209.7279782241692,
    'expansion_ratio': 5.035480632429308, 'chamber_temperature': 3279.1,
    'gamma': 1.169, 'thrust': 3000.0, 'mdot_total': 1.4586,
    'design_ambient': {'mode': 'sea_level', 'is_sea_level': True,
                       'pressure_bar': 1.01325}}}

#: Sıvı vakum tasarımı (mühendis turu L6): üst düzey kimlik var.
ITKI8_SIVI_VAKUM_SONUC = {'motor': {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox',
    'chamber_pressure': 50.0, 'mixture_ratio': 2.0,
    'specific_impulse': 322.4384963773282, 'expansion_ratio': 61.0,
    'chamber_temperature': 3328.45, 'gamma': 1.21826,
    'thrust': 25000.0, 'mdot_total': 7.90628,
    'design_ambient': {'mode': 'vacuum', 'is_sea_level': False,
                       'pressure_bar': 0.0}}}


@node_gerekli
def test_itki8_hibrit_ilk_kosu_kimligi_cozucu_girdisinden():
    ev = _node8({'tip': 'hybrid', 'sonuc': ITKI8_HIBRIT_SONUC})
    assert ev['contextVar'] is True
    assert ev['kimlik'] == {'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}
    assert ev['baglam']['fuel_type'] == 'htpb'
    assert ev['baglam']['oxidizer_type'] == 'n2o'
    # Ek figür istekleri de aynı kimliği taşır.
    for g in ev['ek']:
        assert g['fuel_type'] == 'htpb' and g['oxidizer_type'] == 'n2o'


@node_gerekli
def test_itki8_ve_7_sivi_vakum_ilk_kosu_ve_mach_ortami():
    ev = _node8({'tip': 'liquid', 'sonuc': ITKI8_SIVI_VAKUM_SONUC})
    assert ev['baglam']['fuel_type'] == 'rp1'
    assert ev['baglam']['oxidizer_type'] == 'lox'
    assert ev['baglam']['design_ambient'] == {'mode': 'vacuum'}
    # Temel Isp elle değiştiyse ortam kaydı yüzeye gitmez (sayı motorun
    # tasarım ortamının Isp'si değil) — kimlik yine gider.
    assert 'design_ambient' not in ev['baglamElle']
    assert ev['baglamElle']['oxidizer_type'] == 'lox'
    mach = [g for g in ev['ek'] if g['analysis_type'] == 'nozzle_mach']
    assert len(mach) == 1 and mach[0]['design_ambient'] == {'mode': 'vacuum'}


def test_itki8_yuzey_kimlikle_cozulur_tasarim_noktasi_cizilir(client):
    """Kimlik gelince uç referans çifte düşmez; künye 'referans çift'
    demez ve tasarım noktası izi çizilir."""
    govde = {'chamber_pressure': 30, 'optimal_of_ratio': 6,
             'base_isp': 209.728, 'expansion_ratio': 5.03548,
             'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'grid_n': 5,
             'pc_range': [20, 40], 'of_range': [4, 8],
             'design_ambient': {'mode': 'sea_level'}}
    r = _sessiz(client.post, '/api/advanced-performance-analysis',
                json=govde, headers=HOST)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    fig = json.loads(r.get_json()['plot_data'])
    metin = json.dumps(fig['layout'].get('title'))
    assert 'reference pair' not in metin, metin
    adlar = [str(t.get('name')) for t in fig['data']]
    assert any('Design' in a for a in adlar), adlar


# ===========================================================================
# M7-ITKI-1 — yapışık en büyük ε: tek sayı, kabul ile ret aynı kökten
# ===========================================================================
def _sivi(client, **ek):
    from hrma.analysis import flight_vehicle as fv
    doc = json.loads((KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma')
                     .read_text(encoding='utf-8'))
    alan = dict(doc['inputs']['fields'], **ek)
    durum, g = _sessiz(fv.run_page_calculation, 'liquid',
                       fv.page_payload('liquid', alan))
    return durum, (g.get('motor', g) if isinstance(g, dict) else g)


@pytest.mark.slow
def test_itki1_en_buyuk_yapisik_eps_girilen_luleden_bagimsiz(client):
    sayilar = {}
    for ad, ek in (('e12', {'nozzle_expansion_ratio': 12}),
                   ('e61_vak', {'nozzle_expansion_ratio': 61,
                                'design_ambient_mode': 'vacuum'})):
        d, m = _sivi(client, **ek)
        assert d == 200, (ad, m)
        sl = m['design_ambient']['sea_level']
        assert sl['max_attached_expansion_ratio_status'] == 'solved'
        sayilar[ad] = sl['max_attached_expansion_ratio_2dp']
    assert sayilar['e12'] == sayilar['e61_vak'], sayilar
    eps_2dp = sayilar['e12']
    # Kabul: yayımlanan sayıdaki lüle deniz seviyesinde kabul edilir.
    d, m = _sivi(client, nozzle_expansion_ratio=eps_2dp)
    assert d == 200, m
    assert m['design_ambient']['design_point']['flow_separated'] is False
    # Ret: bir sonraki yüzdelik reddedilir ve ret aynı sayıyı söyler.
    for eps in (round(eps_2dp + 0.01, 2), 61):
        d, g = _sivi(client, nozzle_expansion_ratio=eps)
        assert d == 422, (eps, g)
        kayit = [x for x in g['invalid_fields']
                 if x.get('field') == 'nozzle_expansion_ratio'][0]
        assert kayit['max_attached_expansion_ratio'] == eps_2dp, kayit


def test_itki1_kok_oz_tutarli():
    """Kök P_e(ε, γ(ε)) = k·p_a'yı sağlar (γ ε'daki tasarımın kendi γ'sı)."""
    import numpy as np
    from hrma.engines import liquid_rocket_engine as L
    e = object.__new__(L.LiquidRocketEngine)
    e.P_c, e.MR, e.g0 = 50.0, 2.0, 9.80665
    e.fuel_type, e.oxidizer_type = 'rp1', 'lox'
    e.combustion_data_source = 'rocketcea'
    p_ds = L.SEA_LEVEL_PRESSURE_BAR
    esik = L.NOZZLE_SEPARATION_PRESSURE_RATIO * p_ds
    ust = float(L.LIQUID_INPUT_BANDS['nozzle_expansion_ratio'][1])
    kokler = []
    for g0 in (1.2134, 1.2183):            # iki farklı tasarımın γ'sı
        e.gamma = g0
        eps, durum = _sessiz(e._max_attached_expansion_ratio, p_ds, ust)
        assert durum == 'solved'
        g_k = _sessiz(e._gamma_equivalent_at, eps)
        pe = e._cf_ideal(eps, g_k, 0.0)[1]
        assert pe == pytest.approx(esik, rel=1e-5)
        kokler.append(eps)
    assert np.floor(kokler[0] * 100) == np.floor(kokler[1] * 100), kokler


def _tr_cevir(metinler):
    betik = r"""
const fs=require('fs');
global.window=global; global.I18N={lang:'tr', register:function(){}};
eval(fs.readFileSync(__YOL__,'utf8'));
const g=__VERI__;
process.stdout.write(JSON.stringify(g.map(function(s){return global.I18N.chartText(s);})));
"""
    betik = (betik.replace('__YOL__', json.dumps(
        str(KOK / 'hrma' / 'static' / 'js' / 'i18n_charts.js')))
        .replace('__VERI__', json.dumps(metinler)))
    p = subprocess.run([NODE], input=betik, capture_output=True,
                       text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


@node_gerekli
def test_itki7_mach_kunyesi_tr_ekranda_tr(client):
    """Künyenin her satırı TR'ye geçer (ham İngilizce kalmaz). Başlık
    tarayıcıdaki gibi BÜTÜN verilir: alt başlık <sub>…<br>…</sub> olarak
    <br>'den bölünür (ilk parça yalnız açılış, son parça yalnız kapanış
    etiketini taşır)."""
    basliklar = []
    for kayit in ({'mode': 'vacuum'}, None):
        govde = dict(ITKI7_L6_MACH)
        if kayit:
            govde['design_ambient'] = kayit
        basliklar.append(_mach_basligi(client, govde))
    tr = _tr_cevir(basliklar)
    for t in tr:
        assert not re.search(r'\b(regime|isentropic|solution|Ambient|'
                             r'Assumed|supplied|ambient|vacuum|sea level|'
                             r'separated|underexpanded)\b', t), t
    assert 'rejim: eksik genişlemiş' in tr[0], tr[0]
    assert 'Ortam: motorun tasarım ortamı, vakum</sub>' in tr[0], tr[0]
    assert 'Varsayılan (bu çağrı vermedi): ortam = 1 atm (deniz seviyesi)' \
        in tr[1], tr[1]
    assert 'rejim: ayrılmış (etkin çıkış M = ' in tr[1], tr[1]
    # Ondalık ayracı i18n.js'in decimalText kanonundan (bu düzenekte
    # yüklenmez; tarayıcı kanıtı: ekran/sonra_l6.png).


# ===========================================================================
# M7-ITKI-10 — dışa aktarılan geometri JSON'unda tasarım ortamı Isp'si
# ===========================================================================
@pytest.mark.slow
def test_itki10_vakum_tasariminda_isp_ortamin_adiyla(client):
    d, m = _sivi(client, nozzle_expansion_ratio=61,
                 design_ambient_mode='vacuum')
    assert d == 200, m
    geo = m['motor_geometry']
    assert geo['isp'] == m['isp_design_ambient']
    assert 'isp' not in (geo.get('geometry_unresolved') or {})
    assert geo['isp_basis']['quantity'] == 'isp_design_ambient'
    assert geo['isp_basis']['design_ambient_mode'] == 'vacuum'
    assert geo['isp_basis']['design_ambient_pressure_bar'] == 0.0
    # ε 61 deniz seviyesinde ayrılır: deniz seviyesi Isp'si yazılmaz.
    assert 'isp_sea_level' not in geo


@pytest.mark.slow
def test_itki10_deniz_seviyesi_tasarimi_bit_ayni(client):
    d, m = _sivi(client)
    assert d == 200, m
    geo = m['motor_geometry']
    assert geo['isp'] == m['isp_sea_level']
    assert 'isp_basis' not in geo and 'isp_sea_level' not in geo


def test_itki10_birim_ortam_yoksa_eski_kaynak():
    from hrma.export.motor_geometry import liquid_results_to_motor_geometry
    g = liquid_results_to_motor_geometry({'isp_sea_level': 250.0,
                                          'isp_design_ambient': 300.0})
    assert g['isp'] == 250.0 and 'isp_basis' not in g
    g = liquid_results_to_motor_geometry({
        'isp_sea_level': None, 'isp_design_ambient': 300.0,
        'design_ambient': {'is_sea_level': False, 'mode': 'altitude',
                           'pressure_bar': 0.0553, 'altitude_m': 20000}})
    assert g['isp'] == 300.0
    assert g['isp_basis']['design_ambient_altitude_m'] == 20000


# ===========================================================================
# M7-ITKI-13 — hibrit tasarım ortamı girilen irtifanın adıyla
# ===========================================================================
def _hibrit_kos(client, **ek):
    from tests.test_v307_hibrit_ortam import HIBRIT_ORTAM_GOVDE
    r = _sessiz(client.post, '/calculate', json=dict(HIBRIT_ORTAM_GOVDE, **ek),
                headers=HOST)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()['motor']


def _sayfa_basinci(h):
    """Sayfanın tek irtifa kipi: geometrik irtifa → ISA → toFixed(6)."""
    from hrma.constants import isa_pressure_geometric
    return float('%.6f' % (isa_pressure_geometric(h) / 1e5))


@pytest.mark.slow
def test_itki13_hibrit_irtifa_adiyla_yazilir(client):
    m = _hibrit_kos(client, atmospheric_pressure=_sayfa_basinci(10000.0),
                    design_ambient_altitude_m=10000)
    da = m['design_ambient']
    assert da['mode'] == 'altitude' and da['source'] == 'altitude_isa'
    assert da['altitude_m'] == 10000.0
    assert da['pressure_bar'] == _sayfa_basinci(10000.0)
    assert 'altitude_not_applied' not in da


@pytest.mark.slow
def test_itki13_irtifa_basinci_tutmazsa_ad_uygulanmaz_neden_yazilir(client):
    m = _hibrit_kos(client, atmospheric_pressure=0.5,
                    design_ambient_altitude_m=10000)
    da = m['design_ambient']
    assert da['mode'] == 'pressure' and da['altitude_m'] is None
    assert da['altitude_not_applied']['reason'] == \
        'pressure_is_not_the_isa_pressure_of_this_altitude'


@pytest.mark.slow
def test_itki13_irtifa_gonderilmezse_blok_bugunku_gibi(client):
    m = _hibrit_kos(client, atmospheric_pressure=_sayfa_basinci(10000.0))
    da = m['design_ambient']
    assert da['mode'] == 'pressure' and da['source'] == 'entered_pressure'
    assert 'altitude_not_applied' not in da


def test_itki13_manset_satiri_irtifa_ve_iki_dil():
    js = (KOK / 'hrma' / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
    assert "da.mode === 'altitude'" in js
    assert "'app.headline.designAmbientAltitude'" in js
    i18n = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    satirlar = [l for l in i18n.splitlines()
                if "'app.headline.designAmbientAltitude'" in l]
    assert len(satirlar) == 2
    assert 'Tasarım ortamı: {alt} m irtifa' in satirlar[1]
    sayfa = _advanced()
    assert 'data.design_ambient_altitude_m = tasarimIrtifasi' in sayfa


def test_itki13_sivi_karsilastirma_lulesi_tek_ad():
    """Sıvı: 'Uzay için iyileştirilmiş Isp' / 'Vakum genişleme oranı'
    tasarlanan lüleyle karışıyordu (vakum tasarımında 'vakum genişleme oranı'
    152,5 ⟷ tasarlanan ε 61). Aynı varsayımsal lüle her yerde tek adla."""
    i18n = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    anahtarlar = ('liq.js.vacuum_expansion_ratio',
                  'liq.msg.vacuum_expansion_ratio',
                  'liq.msg.vacuum_expansion_ratio_2',
                  'liq.msg.space_optimized_isp',
                  'liq.msg.space_optimised_isp_s')
    for a in anahtarlar:
        degerler = re.findall(r"'%s': '([^']*)'" % re.escape(a), i18n)
        assert len(degerler) == 2, (a, degerler)
        en, tr = degerler
        assert en.startswith('Comparison space-nozzle'), (a, en)
        # 3.0.7 rc.5 CI (20 Kas): Türkçe 'nozzle' karşılığı tek terim 'nozul'
        # (test_d27_arayuz_a2::test_p12ab205_tek_terim); etiket 'lülesi' →
        # 'nozulu' oldu, kilitlenen şey tek adın kendisi.
        assert tr.startswith('Karşılaştırma uzay nozulu'), (a, tr)
