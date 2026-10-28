# -*- coding: utf-8 -*-
"""v3.0.1 (V301/N-grafik G3) — grafik okunabilirliği bekçileri.

Berke (26 Eki): "bazı grafikler hala okunamaz durumda". Ölçüm (üç sayfa ×
TR/EN × bütün sekmeler + analiz güvertesi, 1440 × 900):
docs/scofield/raw/OH/V301/grafik/RAPOR.md (G2 önce/sonra).

1. TEMA TABANI (plotly_dark.js): her Plotly çizimi tek boğazdan geçer;
   tik ≥ 12 px, eksen başlığı ≥ 14 px, grafik başlığı ≥ 16 px, lejant
   ≥ 12 px. Sayfanın/sunucunun verdiği daha BÜYÜK boy korunur.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')

_TEMA_DUZENEGI = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const yakalanan = [];
const sandbox = { console, JSON, Object, Array, Math, Number, String,
                  isFinite, RegExp, Error, setTimeout: () => 0 };
sandbox.window = sandbox;
sandbox.document = { querySelector: () => null, querySelectorAll: () => [],
                     createElement: () => ({}), head: { appendChild() {} },
                     addEventListener() {}, getElementById: () => null };
sandbox.window.__HRMA_I18N_CHARTS = true;   // sözlük yükleyicisi devre dışı
sandbox.Plotly = {
    newPlot: (el, data, layout) => { yakalanan.push(layout); return layout; },
    react: (el, data, layout) => { yakalanan.push(layout); return layout; },
    Icons: { camera: {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(%(dosya)s, 'utf8'), sandbox,
                { filename: 'plotly_dark.js' });
const GIRDI = %(girdi)s;
GIRDI.forEach((g) => sandbox.Plotly.newPlot({}, g.data || [], g.layout));
process.stdout.write(JSON.stringify(yakalanan));
"""


def _tema(girdiler):
    betik = _TEMA_DUZENEGI % {
        'dosya': json.dumps(str(JS / 'plotly_dark.js')),
        'girdi': json.dumps(girdiler)}
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@node_gerekli
def test_tema_kucuk_boylari_tabana_ceker():
    out = _tema([{'layout': {
        'title': {'text': 'T', 'font': {'size': 10}},
        'xaxis': {'title': 'X', 'tickfont': {'size': 9}},
        'yaxis': {'title': {'text': 'Y', 'font': {'size': 11}},
                  'tickfont': {'size': 10}},
        'yaxis2': {'title': 'Y2', 'overlaying': 'y'},
        'legend': {'font': {'size': 9}},
    }}])[0]
    assert out['title']['font']['size'] == 16
    for ax in ('xaxis', 'yaxis', 'yaxis2'):
        assert out[ax]['tickfont']['size'] == 12, (ax, out[ax])
        assert out[ax]['title']['font']['size'] == 14, (ax, out[ax])
    assert out['legend']['font']['size'] == 12


@node_gerekli
def test_tema_buyuk_boylari_korur_ve_varsayilan_tabanda():
    out = _tema([
        {'layout': {'title': {'text': 'T', 'font': {'size': 22}},
                    'xaxis': {'title': {'text': 'X', 'font': {'size': 18}},
                              'tickfont': {'size': 15}},
                    'legend': {'font': {'size': 13}}}},
        {'layout': {'title': 'T', 'xaxis': {'title': 'X'}, 'yaxis': {}}},
        {'layout': {'title': 'T', 'font': {'size': 9}}},
    ])
    buyuk, varsayilan, kucuk_genel = out
    assert buyuk['title']['font']['size'] == 22
    assert buyuk['xaxis']['tickfont']['size'] == 15
    assert buyuk['xaxis']['title']['font']['size'] == 18
    assert buyuk['legend']['font']['size'] == 13
    assert varsayilan['xaxis']['tickfont']['size'] == 12
    assert varsayilan['yaxis']['tickfont']['size'] == 12
    assert varsayilan['xaxis']['title']['font']['size'] == 14
    assert varsayilan['legend']['font']['size'] == 12
    # Başlık boyu verilmemiş ve genel boy 12: Plotly varsayılanı 16,8 px
    # (tabanın üstünde) — dokunulmaz.
    assert 'size' not in varsayilan['title']['font']
    # Genel boy 9 verilmişse varsayılan başlık 12,6 px olurdu → tabana.
    assert kucuk_genel['title']['font']['size'] == 16
    assert kucuk_genel['legend']['font']['size'] == 12


def test_tema_tabani_tek_yerde():
    kaynak = (JS / 'plotly_dark.js').read_text(encoding='utf-8')
    assert ('var YAZI_TABANI = { tik: 12, eksenBasligi: 14, baslik: 16, '
            'lejant: 12 };') in kaynak
    # Eski sabit 11/12 px kalıntısı yok.
    assert "{ size: 11, family: MONO }" not in kaynak


# ---------------------------------------------------------------------------
# 2. Sunucu figürleri (visualization.py) — yerleşim sözleşmeleri
# ---------------------------------------------------------------------------
def _kati_pano_figuru():
    """test_faz6_guverte'deki T52 örnek katı panosu (A_t sabit → Kn tam
    orantılı; F/Pc Cf kadar gezinir)."""
    import math
    from hrma.visualization.visualization import create_performance_plots
    n = 60
    burn_area = [0.12 - 0.0004 * i for i in range(n)]
    pressure = [40.0 - 0.15 * i for i in range(n)]
    thrust = [p * (150.0 + 0.08 * i) for i, p in enumerate(pressure)]
    return json.loads(create_performance_plots({
        'motor_type': 'solid', 'chamber_pressure': 40.0,
        'throat_diameter': 41.123292,
        'thrust_curve': {'time': [i * 0.01 for i in range(n)],
                         'thrust': thrust, 'pressure': pressure,
                         'burn_area': burn_area, 'mass_flow': [1.0] * n},
    })), (thrust, pressure, [a * 1e4 for a in burn_area],
          [a / (math.pi * (41.123292 / 2000.0) ** 2) for a in burn_area])


def _iz(fig, ad):
    return next(t for t in fig['data'] if t.get('name') == ad)


def _normalize(ys, rg):
    return [(y - rg[0]) / (rg[1] - rg[0]) for y in ys]


@pytest.mark.parametrize('sol, sag', [('Thrust', 'Chamber Pressure'),
                                      ('Burn Area', 'Kn')])
def test_bicimce_ayni_iki_seri_ayri_bantlarda(sol, sag):
    fig, _ = _kati_pano_figuru()
    a, b = _iz(fig, sol), _iz(fig, sag)
    ya = fig['layout']['yaxis' + a['yaxis'][1:]]
    yb = fig['layout']['yaxis' + b['yaxis'][1:]]
    assert yb.get('overlaying') == a['yaxis'], 'çift eksen düzeni değişmiş'
    na, nb = _normalize(a['y'], ya['range']), _normalize(b['y'], yb['range'])
    # Sol seri üst bantta, sağ seri alt bantta; bantlar kesişmez.
    assert min(na) > max(nb), (min(na), max(nb))
    yakin = sum(1 for p, q in zip(na, nb) if abs(p - q) < 0.02) / len(na)
    assert yakin == 0.0, yakin
    # Sayılar değişmedi: eksen aralığı veri bandını kapsar.
    assert ya['range'][0] <= min(a['y']) and ya['range'][1] >= max(a['y'])
    assert yb['range'][0] <= min(b['y']) and yb['range'][1] >= max(b['y'])


def test_beyan_eksen_basliginda_degil_ipucunda():
    fig, _ = _kati_pano_figuru()
    for eksen in fig['layout']:
        if eksen.startswith('yaxis'):
            metin = ((fig['layout'][eksen].get('title') or {}).get('text') or '')
            assert '<sub>' not in metin, (eksen, metin)
    assert '= Burn Area' in _iz(fig, 'Kn')['hovertemplate']


def test_yanma_panosu_dipnotu_asagi_sarkar_ve_sarilir():
    from hrma.visualization.visualization import (
        PANO_DIPNOT_SATIR_KARAKTER, create_combustion_analysis_plots)
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    # test_d37_panel_a1 K6 ile aynı gerçek çözücü girdisi (hibrit örneği).
    cd = CombustionAnalyzer().analyze_combustion({'htpb': 100.0}, 'n2o',
                                                 7.0, 30.0)
    fig = json.loads(create_combustion_analysis_plots(cd))
    notlar = [a for a in fig['layout']['annotations']
              if str(a.get('text', '')).startswith('- ')]
    assert len(notlar) == 1, [a.get('text', '')[:40] for a in fig['layout']['annotations']]
    n = notlar[0]
    assert n['yanchor'] == 'top' and n['y'] == 0.0 and n['yshift'] < 0, n
    satirlar = n['text'].split('<br>')
    assert all(len(s) <= PANO_DIPNOT_SATIR_KARAKTER for s in satirlar), \
        max(len(s) for s in satirlar)
    # Lejant notların altında; alt kenar boşluğu notları ve lejantı alır.
    assert fig['layout']['legend']['y'] < 0
    assert fig['layout']['margin']['b'] >= -n['yshift'] + 15 * len(satirlar)


def test_nozul_mach_haritasi_etiket_ve_lejant_cakismaz():
    import inspect
    import hrma.visualization.visualization as v
    kaynak = inspect.getsource(v.create_nozzle_mach_area_ratio_contour)
    assert "annotation_position='bottom right'" in kaynak
    assert "legend=dict(orientation='h'" in kaynak
    assert "side='right'" in kaynak


# ---------------------------------------------------------------------------
# 3. Hibrit itki-zaman grafiği ve blowdown paneli (node)
# ---------------------------------------------------------------------------
_ITKI_DUZENEGI = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const cagrilar = [];
const ogeler = {};
const oge = (id) => ogeler[id] || (ogeler[id] = { id: id, style: {},
    remove() {}, appendChild() {}, setAttribute() {},
    querySelector: () => null });
const sandbox = { console, JSON, Object, Array, Math, Number, String,
                  isFinite, RegExp, Error, setTimeout: () => 0 };
sandbox.window = sandbox;
sandbox.document = { getElementById: oge, querySelector: () => null,
    querySelectorAll: () => [], addEventListener() {},
    createElement: () => oge('__yeni' + Math.random()) };
sandbox.Plotly = { newPlot: (el, d, l) => cagrilar.push({ id: el.id, data: d, layout: l }),
                   react: (el, d, l) => cagrilar.push({ id: el.id, data: d, layout: l }) };
vm.createContext(sandbox);
const kaynak = fs.readFileSync(%(dosya)s, 'utf8');
const bas = kaynak.indexOf('function renderHybridThrustCurve(');
let i = kaynak.indexOf('{', bas), d = 0;
for (;; i++) { if (kaynak[i] === '{') d++; else if (kaynak[i] === '}' && --d === 0) break; }
vm.runInContext('var T = (k, f) => f; var SRV = (s) => s; '
    + 'function thrustCurveDeclaration() {}\n' + kaynak.slice(bas, i + 1), sandbox);
sandbox.currentResults = { motor: { thrust_curve: %(egri)s } };
sandbox.renderHybridThrustCurve();
process.stdout.write(JSON.stringify(cagrilar));
"""


@node_gerekli
def test_hibrit_itki_basinc_debi_ayri_alt_grafiklerde():
    n = 50
    egri = {'time': [i * 0.2 for i in range(n)],
            'thrust': [3000.0 - i for i in range(n)],
            'pressure': [30.0 - 0.01 * i for i in range(n)],
            'mass_flow': [1.3 - 0.0005 * i for i in range(n)]}
    betik = _ITKI_DUZENEGI % {'dosya': json.dumps(str(JS / 'app.js')),
                              'egri': json.dumps(egri)}
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    c = json.loads(r.stdout)[0]
    lay = c['layout']
    assert [t['yaxis'] for t in c['data']] == ['y', 'y2', 'y3']
    assert all(t['x'] == egri['time'] for t in c['data'])
    alanlar = sorted(lay[k]['domain'] for k in ('yaxis', 'yaxis2', 'yaxis3'))
    for alt, ust in zip(alanlar, alanlar[1:]):
        assert alt[1] < ust[0], alanlar
    for k in ('yaxis', 'yaxis2', 'yaxis3'):
        assert 'overlaying' not in lay[k]
    assert lay['showlegend'] is False
    assert lay['xaxis2']['matches'] == 'x' and lay['xaxis3']['matches'] == 'x'


_BLOWDOWN_DUZENEGI = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const DIZIN = %(dizin)s;
const cagrilar = [];
const ogeler = {};
const oge = (id) => ogeler[id] || (ogeler[id] = { id: id, style: {},
    innerHTML: '', textContent: '', setAttribute() {}, getAttribute() { return null; },
    appendChild() {}, querySelector: () => null, querySelectorAll: () => [],
    addEventListener() {} });
const sandbox = { console, JSON, Object, Array, Math, Number, String,
                  isFinite, RegExp, Error, parseFloat, setTimeout: () => 0 };
sandbox.window = sandbox;
sandbox.document = { getElementById: oge, querySelector: () => null,
    querySelectorAll: () => [], addEventListener() {},
    createElement: () => oge('__yeni' + Math.random()) };
sandbox.Plotly = { newPlot: (el, d, l) => cagrilar.push({ id: el.id, layout: l }),
                   react: (el, d, l) => cagrilar.push({ id: el.id, layout: l }) };
sandbox.I18N = { t: (k, f) => f, has: () => true, number: (v, d) => Number(v).toFixed(d),
    tf: (k, p, f) => String(f).replace(/\{(\w+)\}/g, (w, n) => (p && n in p) ? String(p[n]) : w),
    onChange() {}, applyTo() {} };
vm.createContext(sandbox);
['units_constants.js', 'transient_panel.js', 'blowdown_panel.js'].forEach((d) =>
    vm.runInContext(fs.readFileSync(path.join(DIZIN, d), 'utf8'), sandbox, { filename: d }));
const IN = %(girdi)s;
const els = {};
['pressure', 'mdot', 'thrust', 'chip', 'badges', 'basis', 'decl', 'instability']
    .forEach((k) => { els[k] = oge('bd_' + k); });
const vmod = sandbox.BlowdownPanel.buildViewModel(IN.motor);
process.stdout.write(JSON.stringify({ vm: { mode: vmod.mode, tb: vmod.design_burn_time_s },
    zd: sandbox.TransientPanel.zamanEkseniDuzeni({ time: vmod.series.time_s, end_event: vmod.end_event },
        { burn_time: vmod.design_burn_time_s }, { bitisY: 0.02, bitisYanchor: 'bottom' }) }));
"""


@node_gerekli
def test_blowdown_paneli_zaman_ekseni_tasarim_suresini_kapsar():
    """Hibrit örneğinin /calculate gövdesi (gerçek uç) → blowdown görünüm
    modeli → ortak zaman düzeni: eksen t_b'yi kapsar, erken bitiş işaretli."""
    import contextlib, io, warnings
    from hrma.app import app
    d = json.loads((KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma')
                   .read_text(encoding='utf-8'))
    f = dict(d['inputs']['fields'])
    f['atmospheric_pressure'] = f.get('single_pressure', 1.01325)
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as c:
            r = c.post('/calculate', json=f)
    assert r.status_code == 200
    motor = r.get_json()['motor']
    bd = motor['tank_blowdown']
    assert bd['status'] == 'modelled', bd.get('status')
    betik = _BLOWDOWN_DUZENEGI % {'dizin': json.dumps(str(JS)),
                                  'girdi': json.dumps({'motor': motor})}
    p = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout)
    tb = motor['burn_time']
    assert out['vm']['tb'] == tb
    zd = out['zd']
    assert zd['xMax'] >= max(bd['time_s'][-1], tb)
    assert any(abs(s['x0'] - tb) < 1e-12 for s in zd['shapes'])
    if bd['time_s'][-1] < tb:
        assert zd['erken'] is True
        assert any(abs(s['x0'] - bd['time_s'][-1]) < 1e-12 for s in zd['shapes'])
    # Kaynak sözleşmesi: üç grafik de ortak düzeni kullanır.
    kaynak = (JS / 'blowdown_panel.js').read_text(encoding='utf-8')
    assert kaynak.count('xaxis: zamanXEkseni(timeTitle, zd),') == 3
    assert kaynak.count("shapes: isaretler(zd, 'shapes'),") == 3


def test_tema_alttan_kirpilan_metne_yer_acar():
    """Çizimden sonra alttan taşan metin ölçülür; yükseklik ve alt kenar
    boşluğu AYNI miktarda büyür (çizim alanı yerinde kalır), tek düzeltme."""
    kaynak = (JS / 'plotly_dark.js').read_text(encoding='utf-8')
    govde = kaynak[kaynak.index('function altTasmayiKapat('):]
    govde = govde[:govde.index('\n    function wrap(')]
    assert "Plotly.relayout(gd, { height: yeniH," in govde
    assert "'margin.b': ((L.margin && L.margin.b) || 0) + ek" in govde
    assert 'var yeniH = Math.round((L.height || rs.height) + ek);' in govde
    assert 'if (gd.__hrmaAltPay) return;' in govde
    # autosize figürlere dokunulmaz (katı Isp-irtifa çöküşü, ara ölçüm).
    assert "if (!(gd.layout && typeof gd.layout.height === 'number')) return;" in govde
    # Kabın yüksekliği yazılıysa dolgu payı eklenir (SVG kabın dibinden
    # dolgu kadar taşıyordu).
    assert 'var gerekli = yeniH + dikeyDolgu(gd);' in govde
    assert "gd.style.height = gerekli + 'px';" in govde
    # Kap yalnız büyütülür (sayfanın sonradan kurduğu yükseklik ezilmez).
    assert "gerekli > (parseFloat(gd.style.height) || 0)" in govde
    sarmal = kaynak[kaynak.index('    function wrap(fnName) {'):]
    assert 'altTasmayiKapat(gd);' in sarmal and "gd.on('plotly_afterplot'" in sarmal
