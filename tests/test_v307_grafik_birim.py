"""V307/GRAFİK-BİRİM (19 Kas) — figür MW'si, belirsizlik birimi, grafik metinleri.

Bütün düğümler Flask test istemcisi, kaynak okuması ya da node ile koşar:
docs kanıtına, tarayıcıya, yalnız macOS'a bağlı test YOK (CI'da atlanmaz;
node CI'da kurulu, ``release.yml`` / ``tests.yml`` "node PATH içinde" teyidi).
Ölçümler: ``docs/scofield/raw/OH/V307/grafik-birim/olcum/``.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
PERF_JS = JS / 'panels' / 'performance_panel.js'
THERMAL_JS = JS / 'panels' / 'thermal_panel.js'
I18N_COMMON = JS / 'i18n_common.js'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')
H = {'Host': '127.0.0.1:8080'}


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _apa(c, govde):
    """/api/advanced-performance-analysis (rota literal: test_d24 tarayıcısı
    çözülemeyen çağrı saymasın)."""
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = c.post('/api/advanced-performance-analysis', json=govde, headers=H)
    return r.status_code, (r.get_json() or {})


def _alt_baslik(g):
    f = json.loads(g['plot_data'])
    return (f['layout'].get('title') or {}).get('text', '')


# ---------------------------------------------------------------- kalem 2
# Mach / ısı akısı figürünün MW'si: panel motorun yayımladığı MW'yi gönderir;
# uç MW'yi kapıdan okur; NozzleFlow1D.from_motor_data 20 bar / 24 g/mol
# yedekleri (üründen ulaşılmıyordu, k2_erisim.json) adlı rete döndü.

FIGUR_GOVDE = {'throat_area': 0.001, 'expansion_ratio': 16,
               'chamber_pressure': 30.0, 'chamber_temperature': 3000.0,
               'burn_time': 5.0, 'chamber_length': 0.5, 'gamma': 1.2}


@pytest.mark.parametrize('alan', ['chamber_pressure', 'molecular_weight'])
@pytest.mark.parametrize('deger', [None, 0.0, -3.0, 'NaN', True])
def test_k2_from_motor_data_pc_mw_varsaymaz(alan, deger):
    from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
    md = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
          'gamma': 1.2, 'molecular_weight': 24.0,
          'throat_diameter': 0.02, 'expansion_ratio': 5.0}
    if deger is None:
        md.pop(alan)
    else:
        md[alan] = deger
    with pytest.raises(ValueError, match=alan):
        NozzleFlow1D.from_motor_data(md)


def test_k2_from_motor_data_verilen_degeri_aynen_kullanir():
    from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
    nf = NozzleFlow1D.from_motor_data({
        'chamber_pressure': 31.0, 'chamber_temperature': 3200.0,
        'gamma': 1.2, 'molecular_weight': 25.5,
        'throat_diameter': 0.02, 'expansion_ratio': 5.0})
    assert nf.molecular_weight == 25.5
    assert nf.chamber_pressure == pytest.approx(31.0e5)


def test_k2_kaynakta_20_bar_24_gmol_yedegi_yok():
    """AST: ``from_motor_data`` gövdesinde varsayılanlı ``md.get(alan, sayı)``
    çağrısı yok (yorum/künye metni sayılmaz)."""
    import ast
    agac = ast.parse((KOK / 'hrma' / 'analysis' / 'nozzle_flow_1d.py')
                     .read_text(encoding='utf-8'))
    fmd = [n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef)
           and n.name == 'from_motor_data']
    assert len(fmd) == 1
    yedekli = [ast.unparse(n) for n in ast.walk(fmd[0])
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == 'get' and len(n.args) == 2
               and isinstance(n.args[1], ast.Constant)
               and isinstance(n.args[1].value, (int, float))]
    assert yedekli == []


@pytest.mark.parametrize('tur', ['nozzle_mach', 'heat_flux'])
@pytest.mark.parametrize('deger,neden', [
    (-5.0, 'out_of_range'), (0.0, 'out_of_range'),
    ('abc', 'not_a_json_number'), (True, 'boolean_is_not_a_number')])
def test_k2_figur_ucu_mw_adiyla_reddeder(istemci, tur, deger, neden):
    """ÖNCE (k2_once.json ``bozuk``): heat_flux −5 / 0 → 500; metin / true
    sessizce 24 g/mol varsayımına düşüyordu."""
    kod, g = _apa(istemci, dict(FIGUR_GOVDE, analysis_type=tur, molecular_weight=deger))
    assert kod == 422, (kod, g)
    assert g['error'] == 'invalid_figure_input'
    assert g['invalid_fields'] == [{'field': 'molecular_weight',
                                    'reason': neden, 'unit': 'g/mol'}]


@pytest.mark.parametrize('tur', ['nozzle_mach', 'heat_flux'])
def test_k2_mw_verilince_varsayim_yazilmaz_verilmezse_beyanli(istemci, tur):
    kod, g = _apa(istemci, dict(FIGUR_GOVDE, analysis_type=tur, molecular_weight=25.75))
    assert kod == 200, g
    assert 'MW = 24' not in _alt_baslik(g)
    kod, g = _apa(istemci, dict(FIGUR_GOVDE, analysis_type=tur))
    assert kod == 200, g
    assert 'MW = 24 g/mol' in _alt_baslik(g)


def test_k2_isi_akisi_mw_ile_degisir_mach_degismez(istemci):
    """MW gaz sabitini belirler: ısı akısı değişir, alan-Mach çözümü değişmez
    (ipucu metninin iddiası)."""
    def sayilar(tur, mw):
        kod, g = _apa(istemci, dict(FIGUR_GOVDE, analysis_type=tur, molecular_weight=mw))
        assert kod == 200, g
        return _alt_baslik(g)
    isi_a, isi_b = sayilar('heat_flux', 20.0), sayilar('heat_flux', 40.0)
    tepe = r'peak surface flux ([\d.]+) MW/m2'
    assert re.search(tepe, isi_a).group(1) != re.search(tepe, isi_b).group(1)
    mach = r'isentropic exit M = ([\d.]+)'
    assert (re.search(mach, sayilar('nozzle_mach', 20.0)).group(1)
            == re.search(mach, sayilar('nozzle_mach', 40.0)).group(1))


def _dizi(kaynak, ad):
    m = re.search(r'const %s = \[(.*?)\];' % ad, kaynak, re.S)
    assert m, ad
    return re.findall(r"'([^']+)'", m.group(1))


def test_k2_mw_yollari_termal_panelle_ayni_sira():
    perf = PERF_JS.read_text(encoding='utf-8')
    term = THERMAL_JS.read_text(encoding='utf-8')
    assert _dizi(perf, 'MW_YOLLARI') == _dizi(term, 'MW_YOLLARI')


def test_k2_alan_var_istege_bagli_ve_ipucu_en_tr():
    perf = PERF_JS.read_text(encoding='utf-8')
    assert re.search(r"\['molecular_weight', 'Molecular Weight \(g/mol\)', '', "
                     r"[\d.]+, 'common\.f\.molecularWeight', "
                     r"'panel\.performance\.help\.molecular_weight'\]", perf)
    assert 'molecular_weight' not in _dizi(perf, 'PERF_REQUIRED')
    i18n = I18N_COMMON.read_text(encoding='utf-8')
    satirlar = [s for s in i18n.splitlines()
                if "'panel.performance.help.molecular_weight':" in s]
    assert len(satirlar) == 2                       # EN + TR
    assert 'g/mol' in satirlar[0] and '0\\\'dan büyük' in satirlar[1]


def _panel_tohumu(motor, tur='hybrid'):
    betik = r"""
const fs=require('fs');
function El(t){this.tagName=String(t||'div').toUpperCase();this.children=[];this.style={};this.dataset={};this._attrs={};this.innerHTML='';this.textContent='';}
El.prototype.appendChild=function(c){this.children.push(c);return c;};
El.prototype.setAttribute=function(k,v){this._attrs[k]=String(v);};
El.prototype.getAttribute=function(k){return Object.prototype.hasOwnProperty.call(this._attrs,k)?this._attrs[k]:null;};
El.prototype.querySelectorAll=function(){return [];};
El.prototype.querySelector=function(){return null;};
El.prototype.addEventListener=function(){};
global.document={head:new El('head'),body:new El('body'),readyState:'complete',createElement:function(t){return new El(t);},querySelector:function(){return null;},querySelectorAll:function(){return [];},getElementById:function(){return null;},addEventListener:function(){}};
global.window=global;
const D=__D__;
eval(fs.readFileSync(D+'/units_constants.js','utf8'));
eval(fs.readFileSync(D+'/analysis_dock.js','utf8'));
global.window.AnalysisDock._setMotorType(__TUR__);
eval(fs.readFileSync(D+'/panels/performance_panel.js','utf8'));
const r=__VERI__;
process.stdout.write(JSON.stringify(window.PerformancePanel._fromResults(r)));
"""
    # node çağrı sözleşmesi: betik argv ile DEĞİL stdin ile (test_node_cagri_sozlesmesi).
    betik = (betik.replace('__D__', json.dumps(str(JS)))
             .replace('__TUR__', json.dumps(tur))
             .replace('__VERI__', json.dumps(motor)))
    p = subprocess.run([NODE], input=betik,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


@node_gerekli
@pytest.mark.parametrize('motor,beklenen', [
    ({'molecular_weight': 25.747551775840186}, 25.747551775840186),
    ({'molecular_weight': 30.0, 'heat_transfer_analysis': {
        'bartz_gas_properties': {'molecular_weight': 42.145468051754584}}},
     42.145468051754584),
    ({'thermochemistry': {'molecular_weight': 42.1}}, 42.1),
    ({'molecular_weight': -1.0}, None),
    ({}, None),
])
def test_k2_panel_motorun_mw_sini_tohumlar(motor, beklenen):
    sug = _panel_tohumu({'motor': dict(motor, chamber_temperature=3000.0)})
    if beklenen is None:
        assert 'molecular_weight' not in sug, sug
    else:
        assert sug['molecular_weight'] == beklenen


# ---------------------------------------------------------------- kalem 3
# Belirsizlik kartlarında birim: sözleşmede çıktı başına ``unit`` (üreticinin
# tek tablosu ``uq_adapters.CONTRACT_OUTPUT_UNITS``); panel birimi basar,
# ortalama regresyon hızını sayfanın geri kalanı gibi mm/s gösterir.

UQ_PANEL_JS = JS / 'panels' / 'uncertainty_panel.js'


def test_k3_her_kontrat_ciktisinin_birimi_var():
    """Bekçi: birimsiz çıktı → KIRMIZI (tablo kontrat kümesini tam örter)."""
    from hrma.analysis import uq_adapters as uqa
    assert set(uqa.CONTRACT_OUTPUT_UNITS) == set(uqa.CONTRACT_OUTPUTS)
    for tur, ciktilar in uqa.CONTRACT_OUTPUTS.items():
        birimler = uqa.CONTRACT_OUTPUT_UNITS[tur]
        assert set(birimler) == set(ciktilar), tur
        assert all(isinstance(u, str) and u.strip() for u in birimler.values())
        for ad in ciktilar:
            assert uqa.output_unit(tur, ad) == birimler[ad]
    assert uqa.output_unit('hybrid', 'yok_boyle_cikti') is None


def test_k3_birimler_motor_alaninin_kendi_birimi():
    """Sayı çevrilmez: kontrat birimi motor alanının birimidir (regresyon
    hızı m/s, basınçlar bar; ölçüm k3_birim.json)."""
    from hrma.analysis import uq_adapters as uqa
    t = uqa.CONTRACT_OUTPUT_UNITS
    assert t['hybrid']['regression_rate_avg'] == 'm/s'
    assert t['hybrid']['chamber_pressure'] == 'bar'
    assert t['solid']['max_pressure'] == 'bar'
    assert t['liquid']['mdot_total'] == 'kg/s'
    assert {t[k]['isp'] for k in t} == {'s'}
    assert {t[k]['c_star'] for k in t} == {'m/s'}


# Uçtan uca bekçi (gerçek fast koşuları, üç motor türü):
# tests/test_uq_endpoint.py::test_v307_her_cikti_blogunda_ureticinin_birimi.


def _uq_panel_kart(cikti, anahtar):
    betik = r"""
const fs=require('fs');
function El(t){this.tagName=String(t||'div').toUpperCase();this.children=[];this.style={};this.dataset={};this._attrs={};this.innerHTML='';this.textContent='';}
El.prototype.appendChild=function(c){this.children.push(c);return c;};
El.prototype.setAttribute=function(k,v){this._attrs[k]=String(v);};
El.prototype.getAttribute=function(k){return null;};
El.prototype.querySelectorAll=function(){return [];};
El.prototype.querySelector=function(){return null;};
El.prototype.addEventListener=function(){};
global.document={head:new El('head'),body:new El('body'),readyState:'complete',createElement:function(t){return new El(t);},querySelector:function(){return null;},querySelectorAll:function(){return [];},getElementById:function(){return null;},addEventListener:function(){}};
global.window=global;
const D=__D__;
eval(fs.readFileSync(D+'/units_constants.js','utf8'));
eval(fs.readFileSync(D+'/analysis_dock.js','utf8'));
eval(fs.readFileSync(D+'/panels/uncertainty_panel.js','utf8'));
const g=__VERI__;
const P=window.UncertaintyPanel||{};
const f=P._ciCard||P.ciCard;
if(!f){throw new Error('ciCard disari acik degil: '+Object.keys(P).join(','));}
process.stdout.write(f(g.anahtar,g.cikti));
"""
    betik = (betik.replace('__D__', json.dumps(str(JS)))
             .replace('__VERI__', json.dumps({'cikti': cikti, 'anahtar': anahtar})))
    p = subprocess.run([NODE], input=betik,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-1500:]
    return p.stdout


UQ_BLOK = {'nominal': 0.0011717, 'mean': 0.00117, 'std': 0.00005,
           'p5': 0.00110, 'p25': 0.00114, 'p50': 0.00117, 'p75': 0.00120,
           'p95': 0.00125, 'histogram': {'edges': [0.0011, 0.00125],
                                         'counts': [10]}}


@node_gerekli
def test_k3_panel_regresyonu_mm_s_basar():
    html = _uq_panel_kart(dict(UQ_BLOK, unit='m/s'), 'regression_rate_avg')
    birimler = re.findall(r'data-uq-unit="1"[^>]*>([^<]*)<', html)
    assert birimler and set(birimler) == {'mm/s'}, html
    # 0,00117 m/s × 1000 = 1,17 mm/s (ölçeksiz olsaydı "1.170e-3" basılırdı)
    assert re.search(r'1[.,]17(?![0-9e])', html), html
    assert re.search(r'1[.,]25(?![0-9e])', html), html   # P95 0,00125 × 1000
    assert 'e-3' not in html, html


@node_gerekli
def test_k3_panel_beyan_edilen_birimi_basar_birimsizde_basmaz():
    html = _uq_panel_kart(dict(UQ_BLOK, nominal=1423.0, p50=1420.0, p5=1400.0,
                               p95=1440.0, std=10.0, unit='m/s'), 'c_star')
    assert set(re.findall(r'data-uq-unit="1"[^>]*>([^<]*)<', html)) == {'m/s'}
    html = _uq_panel_kart(dict(UQ_BLOK, nominal=26838.0, p50=26800.0,
                               p5=26000.0, p95=27500.0, std=100.0,
                               unit='N*s'), 'total_impulse')
    assert set(re.findall(r'data-uq-unit="1"[^>]*>([^<]*)<', html)) == {'N·s'}
    html = _uq_panel_kart(dict(UQ_BLOK), 'regression_rate_avg')   # birimsiz
    assert 'data-uq-unit' not in html
    assert '0.0011' in html or '0,0011' in html or 'e-3' in html, html


# ---------------------------------------------------------------- kalem 4-5
# PERFORMANS 3B yüzey künyesi: not madde madde SARILIR (kesilmez), yazı
# ≥ 12 px, alt boşluk satır sayısıyla büyür; TR ekranda künye (not, alt
# başlık, iz adı, ipucu) ve karşılaştırma figürünün panel başlıkları çevrili.

YUZEY = {'analysis_type': '3d_surface', 'fuel_type': 'htpb',
         'oxidizer_type': 'N2O', 'chamber_pressure': 30.0,
         'optimal_of_ratio': 6.0, 'expansion_ratio': 16.0, 'grid_n': 3,
         'design_ambient': {'mode': 'sea_level'}}
YUZEY_VAKALARI = {
    'uyusmaz': dict(YUZEY, base_isp=230.0),
    'kimliksiz': {k: v for k, v in dict(YUZEY, base_isp=230.0).items()
                  if k not in ('fuel_type', 'oxidizer_type')},
    'tavan_ustu': dict(YUZEY, base_isp=400.0),
}


@pytest.fixture(scope='module')
def yuzeyler(istemci):
    out = {}
    for ad, govde in YUZEY_VAKALARI.items():
        kod, g = _apa(istemci, govde)
        assert kod == 200, (ad, g)
        out[ad] = json.loads(g['plot_data'])
    return out


def _yuzey_notu(fig):
    notlar = [a for a in fig['layout'].get('annotations', [])
              if str(a.get('text', '')).startswith('- ')]
    assert len(notlar) == 1, [a.get('text') for a in fig['layout']['annotations']]
    return notlar[0]


@pytest.mark.parametrize('ad', sorted(YUZEY_VAKALARI))
def test_k4_yuzey_notu_sarili_12px_ve_alt_bosluk(yuzeyler, ad):
    from hrma.visualization import visualization as v
    fig = yuzeyler[ad]
    a = _yuzey_notu(fig)
    satirlar = a['text'].split('<br>')
    assert len(satirlar) >= 3
    assert a['font']['size'] >= 12
    assert all(len(s) <= v.PERF_SURFACE_NOTE_WRAP_CHARS + 2 for s in satirlar), satirlar
    assert all(s.startswith('- ') or s.startswith('  ') for s in satirlar)
    assert (a['yanchor'], a['y'], a['yref']) == ('top', 0.0, 'paper')
    assert fig['layout']['margin']['b'] >= (
        v.PERF_SURFACE_NOTE_OFFSET_PX + v.PERF_SURFACE_NOTE_LINE_PX * len(satirlar))
    # Renk çubuğu alttan başlar; üstteki pay lejantın (başlığı lejantın
    # altında kalıyordu — olcum/k45_tarayici_ara.json + ekran görüntüsü).
    cb = [t for t in fig['data'] if t.get('type') == 'surface'][0]['colorbar']
    assert (cb['len'], cb['y'], cb['yanchor']) == (
        v.PERF_SURFACE_COLORBAR_LEN, 0.0, 'bottom')
    assert v.PERF_SURFACE_COLORBAR_LEN < 1.0
    # Tek sözcüklük devam satırı yok ("6.00);" artığı, '; ' bölmesinden).
    assert all(len(s.split()) > 1 for s in satirlar), satirlar


def test_k4_not_metni_kisaltilmadi(yuzeyler):
    a = _yuzey_notu(yuzeyler['uyusmaz'])
    duz = re.sub(r'<br>  ', ' ', a['text']).replace('<br>- ', ' ')
    for parca in ("The design-point cross is drawn at THIS surface's expansion basis",
                  'design ambient: sea level',
                  'expansion-basis difference, not a distance from this surface\'s optimum.',
                  'Combustion-instability bands are NOT modeled here; the earlier shaded '
                  'band had no sourced criterion and was removed.',
                  'Sea-level expansion (Pe = 1 bar) is used for Isp.'):
        assert parca in duz, (parca, duz)


def _tr_cevir(metinler):
    betik = r"""
const fs=require('fs');
global.window=global; global.I18N={lang:'tr', register:function(){}};
eval(fs.readFileSync(__YOL__,'utf8'));
const g=__VERI__;
process.stdout.write(JSON.stringify(g.map(function(s){return global.I18N.chartText(s);})));
"""
    betik = (betik.replace('__YOL__', json.dumps(str(JS / 'i18n_charts.js')))
             .replace('__VERI__', json.dumps(metinler)))
    p = subprocess.run([NODE], input=betik, capture_output=True,
                       text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


#: TR çıktısında kalmaması gereken İngilizce sözcükler (künye cümlelerinden).
INGILIZCE = re.compile(r'\b(drawn|surface|design|basis|nodes|sweep|solver|'
                       r'Difference|Comparison|Total|Thrust|Combustion|'
                       r'expansion|supplied|reported)\b')


@node_gerekli
def test_k5_karsilastirma_panel_basliklari_tr():
    kaynak = ['Thrust Comparison', 'Isp Comparison', 'Total Impulse Comparison',
              'Isp vs Total Mass', 'Isp Comparison<br>sea level']
    tr = _tr_cevir(kaynak)
    assert tr == ['İtki Karşılaştırması', 'Isp Karşılaştırması',
                  'Toplam İtki Karşılaştırması', 'Isp - Toplam Kütle',
                  'Isp Karşılaştırması<br>deniz seviyesi']


@node_gerekli
@pytest.mark.parametrize('ad', sorted(YUZEY_VAKALARI))
def test_k5_yuzey_kunyesi_tr_ekranda_ingilizce_kalmaz(yuzeyler, ad):
    fig = yuzeyler[ad]
    metinler = [fig['layout']['title']['text'], _yuzey_notu(fig)['text']]
    metinler += [t['name'] for t in fig['data'] if t.get('name')]
    metinler += [t['hovertemplate'] for t in fig['data']
                 if t.get('hovertemplate')]
    tr = _tr_cevir(metinler)
    for en, t in zip(metinler, tr):
        gorunen = re.sub(r'<[^>]+>|%\{[^}]*\}', ' ', t)
        assert not INGILIZCE.search(gorunen), (en, t)


# ---------------------------------------------------------------- kalem 6
# η_c* göstergesi: fark ("▼−11,00") ayrı 'delta' göstergesinde, hücrenin alt
# şeridinde — sayı ile kutuları kesişmez (tarayıcı ölçümü
# olcum/k6_gosterge_{once,sonra}.json: 4,1–5,4 px kesişme → 12 px boşluk).

def test_k6_verim_farki_ayri_seritte_sayiyla_kesismez():
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    from hrma.visualization import visualization as v
    with contextlib.redirect_stdout(io.StringIO()):
        cd = CombustionAnalyzer().analyze_combustion({'htpb': 100.0}, 'n2o',
                                                     7.0, 30.0)
        fig = json.loads(v.create_combustion_analysis_plots(cd))
    gost = [t for t in fig['data'] if t.get('type') == 'indicator']
    sayi = [t for t in gost if 'number' in t.get('mode', '')]
    fark = [t for t in gost if t.get('mode') == 'delta']
    assert len(sayi) == 1 and len(fark) == 1, [t.get('mode') for t in gost]
    assert 'delta' not in sayi[0]['mode']
    assert fark[0]['delta']['reference'] == 100.0
    assert fark[0]['value'] == sayi[0]['value']
    assert fark[0]['delta']['font']['size'] == v.ETA_GAUGE_DELTA_FONT_PX
    gs, fs = sayi[0]['domain'], fark[0]['domain']
    assert gs['x'] == fs['x']
    assert fs['y'][1] <= gs['y'][0]                     # şerit sayının altında
    assert fs['y'][1] - fs['y'][0] > 0


# ---------------------------------------------------------------- kalem 7
# Hibrit itki eğrisi grafiği: yükseklik kaba da sabitlenir; pencere yeniden
# boyutlanınca plotly ``responsive`` yüksekliği kaptan okuyup grafiği
# künyenin üstüne taşırıyordu (tarayıcı ölçümü olcum/k67_sayfa_*.json:
# 1440 px'te 4 çakışma → 0; 1280 / 1366 / 1440 / 1920 px, TR + EN).

def test_k7_itki_egrisi_kap_yuksekligi_cizimden_once_sabit():
    app_js = (JS / 'app.js').read_text(encoding='utf-8')
    bas = app_js.index('function renderHybridThrustCurve()')
    govde = app_js[bas:app_js.index('\n}\n', bas)]
    sabit = govde.find("host.style.height = layout.height + 'px';")
    cizim = govde.find('Plotly.newPlot(host, traces, layout')
    assert sabit != -1 and cizim != -1 and sabit < cizim
    assert re.search(r'height: 480 \+ 120 \* \(n - 1\)', govde)
