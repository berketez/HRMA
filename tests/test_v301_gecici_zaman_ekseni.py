# -*- coding: utf-8 -*-
"""v3.0.1 (V301/N-grafik G1) — geçici analiz paneli: zaman ekseni bekçisi.

Berke (26 Eki): "Transient analysis Pc(t)/F(t) analizinde yanma süresi kadar
değil de çok küçük bir zaman için grafik çıkarıyor." Kök v3.0.0'daki web
sınırıydı (kaynaksız 0,8; 10 s'lik yanma ~2,7 s'de ``web_exhausted``);
21 Eki V301/A1 tane zarfına bağladı (bekçi: ``test_v301_web_siniri.py``).
Bu dosya kökü UÇ ve EKRAN düzeyinde savunur:

1. UÇ: örnek hibrit proje (port 1 ve 4; regüleli ve blowdown). Çözücü
   erken bitirmediyse eğri tasarım yanma süresine ulaşır; erken bittiyse
   bitiş olayı FİZİKSEL bir olaydır (``time_limit`` değil).
2. EKRAN (node, panelin GERÇEK ``render``ı, gerçek uç gövdesi): zaman ekseni
   en az [0, max(t_son, t_b)]; t_b'de kesikli çizgi + etiket; erken bitişte
   bitiş anında işaret + olay etiketi; eğri yalnız çözücünün noktalarından
   (x dizisi ``transient.time`` ile AYNI, uydurma t = 0 yok); F(t) ile
   Pc(t) ayrı alt grafiklerde (dikey alanlar kesişmez, ``overlaying`` yok);
   lejant kapalı (başlığa binemez).
3. GİRDİ İPUÇLARI: üç girdinin "?" ipucu iki dilde; ipucundaki varsayılan
   ve kabul bandı sayıları kodun TEK kaynağıyla aynı; boş alan varsayılana,
   yazılan sayı AYNEN gider (eski ``|| 293.15`` 0'ı da yutuyordu).

Ölçüm ve önce/sonra görüntüleri: docs/scofield/raw/OH/V301/grafik/RAPOR.md.
"""
import contextlib
import io
import json
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
PANEL_JS = JS / 'transient_panel.js'
I18N_COMMON = JS / 'i18n_common.js'
ORNEK = KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')

#: Paneldeki olay tablosunun (END_EVENTS) fiziksel olmayan tek üyesi:
#: çözücünün güvenlik süresi tavanı. Erken bitiş bununla açıklanamaz.
FIZIKSEL_OLMAYAN = {'time_limit'}


def _ornek_govde(**ek):
    d = json.loads(ORNEK.read_text(encoding='utf-8'))
    f = dict(d['inputs']['fields'])
    f.pop('motor_name', None)
    f.pop('motor_description', None)
    f['atmospheric_pressure'] = f.pop('single_pressure')
    f.update(ek)
    return f


def _post(govde):
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as c:
            r = c.post('/api/transient-analysis', json=govde)
    return r.status_code, r.get_json() or {}


GECICI_ZAMAN_VAKALARI = {
    'reg_p1': dict(feed_mode='regulated'),
    'bd_p1': dict(feed_mode='blowdown'),
    'reg_p4': dict(feed_mode='regulated', port_count=4),
    'bd_p4': dict(feed_mode='blowdown', port_count=4),
}


@pytest.fixture(scope='module')
def yanitlar():
    out = {}
    for ad, ek in GECICI_ZAMAN_VAKALARI.items():
        kod, j = _post(_ornek_govde(tank_temperature=293.15,
                                    liquid_fill_fraction=0.85, **ek))
        assert kod == 200, (ad, kod, str(j)[:300])
        out[ad] = j
    return out


def _panel_olaylari():
    """END_EVENTS tablosundaki olay adları (paneldeki tek kaynak)."""
    kaynak = PANEL_JS.read_text(encoding='utf-8')
    blok = kaynak[kaynak.index('const END_EVENTS = {'):]
    blok = blok[:blok.index('};')]
    return set(re.findall(r'^\s*(\w+):\s*$', blok, flags=re.M))


# ---------------------------------------------------------------------------
# 1. UÇ
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ad', sorted(GECICI_ZAMAN_VAKALARI))
def test_uc_egri_tasarim_suresine_ulasir_ya_da_fiziksel_olayla_biter(
        yanitlar, ad):
    j = yanitlar[ad]
    tr = j['transient']
    tb = j['design_point']['burn_time']
    t = tr['time']
    adim = t[1] - t[0]
    olay = tr['end_event']
    assert olay in _panel_olaylari(), (ad, olay)
    if olay == 'burn_time_reached':
        assert abs(t[-1] - tb) <= adim + 1e-9, (ad, t[-1], tb)
    else:
        assert olay not in FIZIKSEL_OLMAYAN, (ad, olay)
    # v3.0.0 kusuru: 10 s'lik yanmada eğri ~2,7 s'de bitiyordu.
    assert t[-1] >= 0.5 * tb, (ad, t[-1], tb, olay)


@pytest.mark.parametrize('ad', ['reg_p1', 'reg_p4'])
def test_uc_regule_kipte_erken_bitis_yok(yanitlar, ad):
    tr = yanitlar[ad]['transient']
    assert tr['end_event'] == 'burn_time_reached', tr['end_event']


# ---------------------------------------------------------------------------
# 2. EKRAN — panelin gerçek render'ı (node, DOM saplaması)
# ---------------------------------------------------------------------------
_DUZENEK = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const DIZIN = %(dizin)s;
const IN = %(girdi)s;
const ogeler = {};
function oge(id) {
    if (!ogeler[id]) ogeler[id] = { id: id, style: {}, innerHTML: '',
        textContent: '', value: (IN.form || {})[id], disabled: false };
    return ogeler[id];
}
const cagrilar = [];
const sandbox = { console, JSON, Object, Array, Math, Number, String,
                  isFinite, parseFloat, NaN, RegExp, Error };
sandbox.window = sandbox;
sandbox.document = { getElementById: oge };
sandbox.Plotly = { react: (el, data, layout) => cagrilar.push(
    { id: el.id, data: data, layout: layout }) };
sandbox.I18N = {
    t: (k, f) => f, has: () => true,
    tf: (k, p, f) => String(f).replace(/\{(\w+)\}/g,
        (w, n) => (p && n in p) ? String(p[n]) : w),
    number: (v, d) => Number(v).toFixed(d),
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(DIZIN, 'units_constants.js'), 'utf8'),
                sandbox, { filename: 'units_constants.js' });
vm.runInContext(fs.readFileSync(path.join(DIZIN, 'transient_panel.js'), 'utf8'),
                sandbox, { filename: 'transient_panel.js' });
const TP = sandbox.TransientPanel;
let cikti;
if (IN.kip === 'render') {
    TP._render(IN.veri);
    cikti = cagrilar;
} else {
    cikti = (IN.alanlar || []).map((id) => TP._tankGirdisi(id, -1));
}
process.stdout.write(JSON.stringify(cikti));
"""


def _node(girdi):
    betik = _DUZENEK % {'dizin': json.dumps(str(JS)),
                        'girdi': json.dumps(girdi)}
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def _cizim(veri):
    cagrilar = _node({'kip': 'render', 'veri': veri})
    return {c['id']: c for c in cagrilar}


def _kesik_cizgiler(layout):
    return [s for s in layout.get('shapes', [])
            if s.get('type') == 'line' and s.get('x0') == s.get('x1')]


def _alt_grafikler_ayri(layout):
    y1, y2 = layout['yaxis'], layout['yaxis2']
    assert 'overlaying' not in y1 and 'overlaying' not in y2, (
        'iki iz yine aynı çizim alanında (overlaying) — üst üste biner')
    a, b = sorted([y1['domain'], y2['domain']])
    assert a[1] < b[0], ('alt grafiklerin dikey alanları kesişiyor', a, b)


def _ortak_denetim(c, tr, tb):
    lay = c['layout']
    t_son = tr['time'][-1]
    ust = max(t_son, tb)
    for ax in ('xaxis', 'xaxis2'):
        rg = lay[ax]['range']
        assert rg[0] == 0, (ax, rg)
        assert rg[1] >= ust - 1e-12, (ax, rg, 'max(t_son, t_b) =', ust)
    # Uydurma nokta yok: iki izin x'i çözücünün zaman dizisiyle AYNI.
    assert len(c['data']) == 2
    for iz in c['data']:
        assert iz['x'] == tr['time'], 'x dizisi transient.time değil'
    assert [iz['xaxis'] for iz in c['data']] == ['x', 'x2']
    assert [iz['yaxis'] for iz in c['data']] == ['y', 'y2']
    _alt_grafikler_ayri(lay)
    assert lay['showlegend'] is False
    # t_b dikey çizgisi + etiketi
    assert any(abs(s['x0'] - tb) < 1e-12 for s in _kesik_cizgiler(lay)), lay
    assert any('t_b = %.2f s' % tb in a['text']
               for a in lay.get('annotations', [])), lay.get('annotations')


@node_gerekli
def test_ekran_regule_eksen_tasarim_suresini_kapsar_ve_iki_alt_grafik(
        yanitlar):
    j = yanitlar['reg_p1']
    tr, tb = j['transient'], j['design_point']['burn_time']
    c = _cizim(j)
    assert set(c) == {'tp_plot'}, sorted(c)
    _ortak_denetim(c['tp_plot'], tr, tb)
    # Tasarım süresine ulaşan koşuda bitiş işareti YOK (yalnız t_b çizgisi).
    assert len(_kesik_cizgiler(c['tp_plot']['layout'])) == 1


@node_gerekli
def test_ekran_blowdown_erken_bitis_isaretli_ve_tank_grafigi_ayni_ilke(
        yanitlar):
    j = yanitlar['bd_p1']
    tr, tb = j['transient'], j['design_point']['burn_time']
    olay = tr['end_event']
    # V301/H-PANEL (NK-9/NK-50): eski "erken bitiş" (9,10 s,
    # injector_unstable) yakınsamayan Pc ↔ ṁ_ox döngüsünün YAPAYLIĞIYDI.
    # Kök onarımından sonra örnek blowdown sıvı tükenmesiyle t_b'den SONRA
    # biter (ölçüldü: 10,45 s, oxidizer_depleted). Denetlenen ilke aynı:
    # tasarım süresinden farklı biten koşunun bitiş anı işaretli ve eksen
    # max(t_son, t_b)'yi kapsar.
    assert olay != 'burn_time_reached' and abs(tr['time'][-1] - tb) > 1e-6, (
        'örnek blowdown tam tasarım süresinde bitiyor; bitiş işareti vakası '
        'için bu testi yeni bir örnekle kur', olay, tr['time'][-1])
    c = _cizim(j)
    assert set(c) == {'tp_plot', 'tp_tank_plot'}, sorted(c)
    for gid in ('tp_plot', 'tp_tank_plot'):
        _ortak_denetim(c[gid], tr, tb)
        lay = c[gid]['layout']
        assert any(abs(s['x0'] - tr['time'][-1]) < 1e-12
                   for s in _kesik_cizgiler(lay)), (gid, lay['shapes'])
        etiket = olay.upper()
        assert any(etiket in a['text'] and 't = %.2f s' % tr['time'][-1]
                   in a['text'] for a in lay['annotations']), (
            gid, lay['annotations'])


@node_gerekli
def test_ekran_cok_erken_biten_kosu_tasarim_suresine_gore_gorunur(yanitlar):
    """v3.0.0 kusurunun ekran izi: 10 s'lik tasarımda eğri ~2,7 s'de biter.

    Gerçek regüleli gövde ilk %27'sine kesilir ve olay ``web_exhausted``
    yapılır; eksen yine t_b'yi kapsar, bitiş anı etiketlidir.
    """
    j = json.loads(json.dumps(yanitlar['reg_p1']))
    tr = j['transient']
    n = int(len(tr['time']) * 0.27)
    for k, v in list(tr.items()):
        if isinstance(v, list) and len(v) == len(j['transient']['time']):
            tr[k] = v[:n]
    tr['end_event'] = 'web_exhausted'
    tb = j['design_point']['burn_time']
    c = _cizim(j)['tp_plot']
    _ortak_denetim(c, tr, tb)
    assert c['layout']['xaxis2']['range'][1] >= tb
    assert any('WEB_EXHAUSTED' in a['text'] for a in c['layout']['annotations'])


@node_gerekli
def test_ekran_tasarim_suresi_yoksa_cizgi_uydurulmaz(yanitlar):
    j = json.loads(json.dumps(yanitlar['reg_p1']))
    j['design_point'].pop('burn_time')
    lay = _cizim(j)['tp_plot']['layout']
    assert not any('t_b' in a['text'] for a in lay['annotations'])
    t_son = j['transient']['time'][-1]
    assert lay['xaxis2']['range'][1] >= t_son


# ---------------------------------------------------------------------------
# 3. GİRDİ İPUÇLARI — tek kaynak
# ---------------------------------------------------------------------------
def _js_sabiti(ad):
    m = re.search(r'const %s = (\[[^\]]*\]|[0-9.]+);' % ad,
                  PANEL_JS.read_text(encoding='utf-8'))
    assert m, ad
    return json.loads(m.group(1))


def test_ipucu_sayilari_kodun_tek_kaynagiyla_ayni():
    from hrma.analysis.tank_blowdown import (
        N2OTankBlowdown, SAT_TABLE_T_MAX, SAT_TABLE_T_MIN)
    from hrma.engines.hybrid_rocket_engine import (
        TANK_FILL_FRACTION_DEFAULT, TANK_TEMPERATURE_DEFAULT_K)
    assert _js_sabiti('BOS_TANK_SICAKLIGI_K') == TANK_TEMPERATURE_DEFAULT_K
    assert _js_sabiti('BOS_DOLULUK_ORANI') == TANK_FILL_FRACTION_DEFAULT
    assert _js_sabiti('TANK_T_BANDI_K') == [SAT_TABLE_T_MIN, SAT_TABLE_T_MAX]
    lo, hi = _js_sabiti('DOLULUK_BANDI')
    # Doluluk bandı tank modelinin kabul kapısıdır (adlı sabit yok):
    # davranıştan ölçülür — uçlar kabul, hemen dışı ret.
    N2OTankBlowdown(0.01, TANK_TEMPERATURE_DEFAULT_K, lo)
    N2OTankBlowdown(0.01, TANK_TEMPERATURE_DEFAULT_K, hi)
    for disari in (lo - 1e-4, hi + 1e-4):
        with pytest.raises(ValueError):
            N2OTankBlowdown(0.01, TANK_TEMPERATURE_DEFAULT_K, disari)


def test_ipucu_uc_girdinin_yaninda_ve_iki_dilde():
    kaynak = PANEL_JS.read_text(encoding='utf-8')
    for kimlik in ('tp_feed_mode_tip', 'tp_tank_temp_tip', 'tp_fill_tip'):
        assert "ipucuHtml('%s')" % kimlik in kaynak, kimlik
    assert 'class="tooltip"' in kaynak and 'class="tooltip-icon"' in kaynak
    metin = I18N_COMMON.read_text(encoding='utf-8')
    for anahtar in ('transient.feedModeTip', 'transient.tankTempTip',
                    'transient.fillFractionTip', 'transient.designBurnMarker',
                    'transient.endMarker'):
        assert metin.count("'%s':" % anahtar) == 2, anahtar
        assert ("T('%s'" % anahtar in kaynak
                or "TF('%s'" % anahtar in kaynak), anahtar
    for yer_tutucu in ('{t0}', '{tmin}', '{tmax}', '{f0}', '{fmin}', '{fmax}'):
        assert metin.count(yer_tutucu) >= 2, yer_tutucu
    assert 'Boş bırakılırsa {t0} K gönderilir' in metin
    assert 'tasarım yanma süresi t_b = {s} s' in metin


@node_gerekli
def test_bos_alan_varsayilana_yazilan_sayi_aynen_gider():
    cikti = _node({'kip': 'girdi', 'alanlar': ['a', 'b', 'c'],
                   'form': {'a': '', 'b': '0', 'c': '250.5'}})
    assert cikti == [-1, 0, 250.5], cikti


def test_bitis_isareti_rengi_rozetin_tema_rengiyle_ayni():
    kaynak = PANEL_JS.read_text(encoding='utf-8')
    blok = kaynak[kaynak.index('const OLAY_RENGI = {'):]
    blok = blok[:blok.index('};')]
    isaret = dict(re.findall(r"(\w+): '(#[0-9a-f]{6})'", blok))
    rozet = kaynak[kaynak.index('function badge('):]
    rozet = rozet[:rozet.index('};')]
    yedek = dict(re.findall(r"(\w+): 'var\(--hd-[a-z]+, (#[0-9a-f]{6})\)'", rozet))
    assert set(isaret) == {'ok', 'info', 'warn', 'err'}, isaret
    assert isaret == yedek, (isaret, yedek)
