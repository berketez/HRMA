# -*- coding: utf-8 -*-
"""V307/GÜVERTE-ORTAM bekçileri (17 Kas 2026) — sıvının tasarım ortamı
güverteye, belirsizliğe, PDF'e ve .eng dosyasına; katı YAPISAL sekmede iki
gereken cidarın farkı ve EK renk eşiği.

3.0.7'de sıvı motorun tasarım ortamı girdidir (deniz seviyesi / irtifa /
basınç / vakum; çözücü ``design_ambient`` bloğunda beyan eder). Motor sayfası
doğruydu; sonucu okuyan öbür yerler "her şey deniz seviyesi" varsayıyordu.

Bu dosya FİZİĞİ ve SÖZLEŞMEYİ kilitler, bugünkü çıktıyı değil:

* deniz seviyesi tasarımında her kalemde sayı, gövde ve metin bugünküyle
  aynı (etiket yok, satır yok, anahtar yok);
* deniz seviyesi dışındaki tasarımda okunan sayı TASARIM ORTAMININ sayısıdır
  (yanıtın ``isp_design_ambient``/``specific_impulse``ı) ve ortam adıyla
  yazılır; iki farklı ortamın itki / Isp / impulsu aynı sıralamaya girmez;
* ``None`` hiçbir yerde "0", "--" ya da boş hücre olarak basılmaz;
* YAPISAL: renk hükmü istasyonun hükmüyle aynı tabana (bu koşumun tasarım
  hedefi) karşı verilir.

Akış gerçektir: /calculate_liquid ve /calculate_solid (gerçek uç) → panelin
GERÇEK JS'i (node, docs/scofield/raw/P11/B4-repro-03.js) → güverte ucu.
Ölçüm ve kanıt: docs/scofield/raw/OH/V307/guverte-ortam/ (RAPOR.md).
"""
import contextlib
import copy
import io
import json
import re
import shutil
import subprocess
import warnings

import pytest

import tests.test_v3_yapi_sf as T
import tests.test_v307_sekme_guverte as SG
import tests.test_v307_sivi_ortam as SO
from tests.support.kanit import kanit_gerekli

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None,
                                  reason='node yok: panel ölçümü koşamaz')
HOST = {'Host': '127.0.0.1:8080'}

#: Mühendis turu L3 gövdesi (basınç beslemeli, ablatif; 5 kN, 30 bar) —
#: tek kaynak tests/test_v307_sivi_ortam.L3 — ε 8 (deniz seviyesinde
#: yapışık) ve %5 film (PDF film satırları için). ε 50 deniz seviyesinde
#: ayrılır.
L3_FILM = dict(SO.L3, nozzle_expansion_ratio=8, film_cooling_percent=5)

ORTAM_VAKALARI = {
    'ds': {},                                              # deniz seviyesi
    'vak8': {'design_ambient_mode': 'vacuum'},             # DS'de yapışık
    'vak50': {'design_ambient_mode': 'vacuum',             # DS'de ayrık
              'nozzle_expansion_ratio': 50},
    'irt20': {'design_ambient_mode': 'altitude',
              'design_ambient_altitude_m': 20000},
}


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


@pytest.fixture(scope='module')
def yanit(client):
    """Dört vakanın GERÇEK /calculate_liquid yanıtı (JSON güvenli)."""
    out = {}
    for ad, ek in ORTAM_VAKALARI.items():
        r = _sessiz(client.post, '/calculate_liquid', json=dict(L3_FILM, **ek),
                    headers=HOST)
        assert r.status_code == 200, (ad, r.get_data(as_text=True)[:300])
        out[ad] = T._json_guvenli(r.get_json())
    # Ölçümün önkoşulu: vakaların ortam beyanı beklenen hâlde.
    assert out['ds']['design_ambient']['is_sea_level'] is True
    assert out['vak8']['design_ambient']['sea_level']['status'] == 'attached'
    assert out['vak50']['design_ambient']['sea_level']['status'] == 'separated'
    assert out['vak50']['isp_sea_level'] is None
    assert out['irt20']['design_ambient']['altitude_m'] == 20000
    return out


# ---------------------------------------------------------------------------
# node: KARŞILAŞTIRMA + PERFORMANS + BELİRSİZLİK panelleri (gerçek dosyalar)
# ---------------------------------------------------------------------------
_EV = r"""
var out = {};
window.AnalysisDock.init({motorType: 'liquid',
    resultsProvider: function () { return window.currentResults; }});
if (body.ortamOkuyucusuYok) { delete window.HRMAIspAmbient; }
var CP = window.ComparativePanel, UQ = window.UncertaintyPanel;
var specP = window.AnalysisDock._registry.filter(function (s) {
    return s.id === 'performance'; })[0];
var gonderilen = [];
window.fetch = function (url, opts) {
    gonderilen.push({url: url, body: opts && opts.body});
    return new Promise(function () {});
};
out.tek = {};
Object.keys(body.yanit).forEach(function (v) {
    window.currentResults = body.yanit[v];
    var r = {metrics: CP._currentMetrics(), ortam: CP._lastAmbient()};
    var sec = document.getElementById('ad_sec_performance');
    sec.children = [];
    r.perf = specP.fromResults(body.yanit[v]);
    r.perfOrtam = window.PerformancePanel._baseIspAmbient();
    var notlar = (sec.children || []).filter(function (c) {
        return c.getAttribute && c.getAttribute('data-perf-isp-ambient'); });
    r.perfNot = notlar.length ? String(notlar[notlar.length - 1].innerHTML) : null;
    out.tek[v] = r;
});
out.cift = {};
(body.ciftler || []).forEach(function (c) {
    CP._snapshots.length = 0;
    c.forEach(function (v, i) {
        window.currentResults = body.yanit[v];
        document.getElementById('cmp_name').value = v + '_' + i;
        CP.snapshot();
    });
    var liste = document.getElementById('cmp_list').innerHTML;
    var satirlar = CP._overlayRows(CP._snapshots[0], CP._snapshots[1]);
    var tablo = CP._overlayTableHtml(CP._snapshots[0], CP._snapshots[1]);
    gonderilen.length = 0;
    CP.run();
    var govde = gonderilen.length ? JSON.parse(gonderilen[0].body) : null;
    var root = document.createElement('div');
    if (body.analizler && body.analizler[c.join('+')]) {
        CP._render({analysis: body.analizler[c.join('+')], plot: null}, root);
    }
    var h = '';
    (function walk(n) { h += String(n.innerHTML || '');
        (n.children || []).forEach(walk); })(root);
    out.cift[c.join('+')] = {liste: liste, satirlar: satirlar, tablo: tablo,
        govde: govde, karisik: CP._ambientMixed(), ozet: h};
});
out.uq = {};
(body.uqGirdileri || []).forEach(function (g, i) {
    UQ._setOutputAmbientFromInputs(g);
    out.uq[i] = {isp: UQ._labelFor('isp'), thrust: UQ._labelFor('thrust'),
                 c_star: UQ._labelFor('c_star'),
                 mdot: UQ._labelFor('mdot_total'), ortam: UQ.outputAmbient};
});
return out;
"""


def _node(data):
    if NODE is None:
        pytest.skip('node yok: panel ölçümü koşamaz (gerekçeli atlama)')
    cfg = {'panelId': '_yok',
           'panelFiles': ['hrma/static/js/panels/performance_panel.js',
                          'hrma/static/js/panels/comparative_panel.js',
                          'hrma/static/js/panels/uncertainty_panel.js'],
           'dataInline': data, 'evalFn': _EV}
    p = subprocess.run([NODE, kanit_gerekli(str(T._PANEL_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=240)
    assert p.returncode == 0, p.stderr[-2000:]
    ev = json.loads(p.stdout)['evaled']
    assert '_err' not in ev, ev.get('_err')
    return ev


def _metin(html):
    h = re.sub(r'<span[^>]*\bhidden\b[^>]*>.*?</span>', ' ', html or '',
               flags=re.S)
    return ' '.join(re.sub(r'<[^>]*>', ' ', h).split())


@pytest.fixture(scope='module')
def panel(yanit, client):
    ciftler = [['ds', 'ds'], ['ds', 'vak50'], ['vak8', 'vak50'],
               ['ds', 'irt20']]
    ilk = _node({'yanit': yanit, 'ciftler': ciftler})
    # Gövdeler GERÇEK karşılaştırma ucuna gider; özet o yanıtla çizilir.
    analizler = {}
    for ad, c in ilk['cift'].items():
        if c['govde']:
            r = client.post('/api/comparative-analysis', json=c['govde'])
            assert r.status_code == 200, r.get_data(as_text=True)[:300]
            analizler[ad] = r.get_json()['analysis']
    ev = _node({'yanit': yanit, 'ciftler': ciftler, 'analizler': analizler,
                'uqGirdileri': [
                    {},
                    {'design_ambient_mode': 'vacuum'},
                    {'design_ambient_mode': 'altitude',
                     'design_ambient_altitude_m': 20000},
                    {'design_ambient_mode': 'pressure',
                     'design_ambient_pressure_bar': 0.5},
                ]})
    ev['analizler'] = analizler
    return ev


# ---------------------------------------------------------------------------
# Kalem 1 — KARŞILAŞTIRMA
# ---------------------------------------------------------------------------
@node_gerekli
def test_k1_deniz_seviyesi_tasarimi_bugunku_gibi(panel, yanit):
    t = panel['tek']['ds']
    assert t['ortam'] is None
    assert t['metrics']['isp'] == yanit['ds']['isp_sea_level']
    assert t['metrics']['isp_basis'] == 'isp_sea_level'
    assert t['metrics']['thrust'] == yanit['ds']['thrust']
    c = panel['cift']['ds+ds']
    assert c['karisik'] is False
    # Gövde anlık görüntülerin metrik sözlüğünün AYNISI (ortam gövdeye girmez).
    for cfg in c['govde']['motor_configs'].values():
        assert cfg == t['metrics']
    assert 'design ambient' not in _metin(c['liste'])
    assert 'data-cmp-ambient' not in c['ozet']
    assert all(not r.get('ambientDiffers') for r in c['satirlar'])


@node_gerekli
@pytest.mark.parametrize('v', ['vak8', 'vak50', 'irt20'])
def test_k1_deniz_seviyesi_disinda_isp_tasarim_ortaminin(panel, yanit, v):
    t = panel['tek'][v]
    assert t['metrics']['isp'] == yanit[v]['isp_design_ambient']
    assert t['metrics']['isp_basis'] == 'isp_design_ambient'
    # İtki ve impuls çözücünün kendi (tasarım ortamı) sayıları; değişmedi.
    assert t['metrics']['thrust'] == yanit[v]['thrust']
    assert t['ortam']['kind'] in ('vacuum', 'altitudeP')
    if v == 'irt20':
        assert t['ortam']['h'] == 20000
        assert t['ortam']['p'] == yanit[v]['design_ambient']['pressure_bar']


@node_gerekli
def test_k1_farkli_ortamlar_siralanmaz_ve_adiyla_yazilir(panel):
    c = panel['cift']['ds+vak50']
    assert c['karisik'] is True
    for cfg in c['govde']['motor_configs'].values():
        for k in ('thrust', 'isp', 'isp_basis', 'total_impulse'):
            assert k not in cfg
        assert 'total_mass' in cfg          # ortamdan bağımsız metrik kalır
    a = panel['analizler']['ds+vak50']
    assert a['best_isp'] is None and a['best_thrust'] is None
    oz = _metin(c['ozet'])
    assert 'not ranked' in oz and 'vacuum' in oz and 'sea level' in oz
    assert 'Not computed: the stored designs are at different design ambients' \
        in c['ozet']
    # Uca ortama bağlı metrik gitmedi: boş eksenli figür çizilmez, neden yazar.
    assert 'Chart not drawn: thrust, Isp and total impulse of these designs' in oz
    farkli = {r['metric'] for r in c['satirlar'] if r.get('ambientDiffers')}
    assert farkli == {'thrust', 'isp', 'total_impulse'}
    for r in c['satirlar']:
        if r.get('ambientDiffers'):
            assert r['delta'] is None and r['rel'] is None
    tablo = _metin(c['tablo'])
    assert tablo.count('not compared: the two designs are at different '
                       'design ambients') == 3
    liste = _metin(c['liste'])
    assert 'design ambient of F, Isp, It: vacuum' in liste


@node_gerekli
def test_k1_ayni_ortam_siralanir_ve_ortam_yazilir(panel, yanit):
    c = panel['cift']['vak8+vak50']
    assert c['karisik'] is False
    cfgs = c['govde']['motor_configs']
    assert cfgs['vak8_0']['isp'] == yanit['vak8']['isp_design_ambient']
    assert cfgs['vak50_1']['isp'] == yanit['vak50']['isp_design_ambient']
    a = panel['analizler']['vak8+vak50']
    beklenen = 'vak50_1' if (yanit['vak50']['isp_design_ambient']
                             > yanit['vak8']['isp_design_ambient']) else 'vak8_0'
    assert a['best_isp'] == beklenen
    assert 'Thrust, Isp and total impulse of every compared design are at ' \
           'its design ambient' in _metin(c['ozet'])
    assert re.search(r'Isp \(\s*vacuum\s*\)', _metin(c['tablo']))


@node_gerekli
def test_k1_ortam_okuyucusu_yoksa_ortama_bagli_metrik_gonderilmez(yanit):
    ev = _node({'yanit': {'vak50': yanit['vak50'], 'ds': yanit['ds']},
                'ortamOkuyucusuYok': True})
    m = ev['tek']['vak50']['metrics']
    for k in ('thrust', 'isp', 'total_impulse'):
        assert k not in m
    assert 'total_mass' in m
    # Deniz seviyesi tasarımı okuyucudan bağımsız.
    assert ev['tek']['ds']['metrics']['isp'] == yanit['ds']['isp_sea_level']


# ---------------------------------------------------------------------------
# Kalem 1 — PERFORMANS (Temel Isp alanı)
# ---------------------------------------------------------------------------
@node_gerekli
def test_k1_performans_temel_isp_ortami(panel, yanit):
    ds = panel['tek']['ds']
    assert ds['perf']['base_isp'] == yanit['ds']['isp_sea_level']
    assert ds['perfOrtam'] is None and ds['perfNot'] is None
    for v in ('vak8', 'vak50', 'irt20'):
        t = panel['tek'][v]
        assert t['perf']['base_isp'] == yanit[v]['isp_design_ambient']
        assert t['perfOrtam'] is not None
        assert 'not at sea level' in _metin(t['perfNot'])
    assert 'vacuum' in _metin(panel['tek']['vak50']['perfNot'])
    irt = _metin(panel['tek']['irt20']['perfNot'])
    assert '20000 m design altitude (0.0553 bar)' in irt


# ---------------------------------------------------------------------------
# Kalem 2 — BELİRSİZLİK
# ---------------------------------------------------------------------------
def test_k2_uq_isp_deniz_seviyesinde_bit_ayni_disinda_tasarim_ortami(yanit):
    from hrma.analysis import uq_adapters as uqa
    for v, r in yanit.items():
        beklenen = (r['isp_sea_level'] if v == 'ds'
                    else r['isp_design_ambient'])
        assert uqa.liquid_uq_isp(r) == beklenen
        assert uqa.liquid_uq_isp(r) is not None
    # Deniz seviyesi alanı ayrık vakum tasarımında None'dur; çıktı yine var.
    assert yanit['vak50']['isp_sea_level'] is None


def test_k2_uc_nominal_isp_ciktisi(client, yanit):
    """Gerçek belirsizlik ucu (2 örnek): ayrık vakum tasarımında Isp çıktısı
    VAR ve nominali tasarım ortamı Isp'si; deniz seviyesinde manşetle aynı."""
    for v in ('ds', 'vak50'):
        govde = {'motor_type': 'liquid', 'level': 'fast', 'seed': 7,
                 'n_samples': 2, 'inputs': dict(L3_FILM, **ORTAM_VAKALARI[v])}
        r = _sessiz(client.post, '/api/uncertainty-analysis', json=govde)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        js = r.get_json()
        assert 'isp' in js['outputs'], (v, sorted(js['outputs']))
        beklenen = (yanit[v]['isp_sea_level'] if v == 'ds'
                    else yanit[v]['isp_design_ambient'])
        assert js['outputs']['isp']['nominal'] == pytest.approx(
            beklenen, rel=1e-12)


@node_gerekli
def test_k2_panel_cikti_adi_ortami_soyler(panel):
    uq = panel['uq']
    assert uq['0'] == {'isp': 'Isp', 'thrust': 'Thrust', 'c_star': 'C*',
                       'mdot': 'Total Mass Flow', 'ortam': None}
    assert uq['1']['isp'] == 'Isp · vacuum'
    assert uq['1']['thrust'] == 'Thrust · vacuum'
    assert uq['1']['c_star'] == 'C*' and uq['1']['mdot'] == 'Total Mass Flow'
    assert uq['2']['isp'] == 'Isp · 20000 m design altitude'
    assert uq['3']['isp'] == 'Isp · 0.5000 bar design ambient'


# ---------------------------------------------------------------------------
# Kalem 3 — PDF film satırları
# ---------------------------------------------------------------------------
def _film_satirlari(r):
    from hrma.export.pdf_generator import PDFReportGenerator
    hikaye = PDFReportGenerator()._create_liquid_thermal_section(
        r, {'motor_type': 'liquid'})
    for o in hikaye:
        hucreler = getattr(o, '_cellvalues', None) or []
        if hucreler and any('Film flow' in str(s[0]) for s in hucreler):
            return [[str(h) for h in s] for s in hucreler[1:]]
    raise AssertionError('film tablosu yok')


def test_k3_deniz_seviyesinde_film_tablosu_bugunku_gibi(yanit):
    from hrma.export.pdf_generator import PDFReportGenerator as G
    satirlar = _film_satirlari(yanit['ds'])
    assert [s[0] for s in satirlar] == [r[1] for r in G.LIQUID_FILM_ROWS]
    perf = yanit['ds']['cooling_system']['film_cooling']['performance']
    assert satirlar[4][1] == '%.2f' % perf['isp_core_sea_level_s']
    assert satirlar[5][1] == '%.2f' % perf['isp_delivered_sea_level_s']


@pytest.mark.parametrize('v', ['vak8', 'vak50', 'irt20'])
def test_k3_tasarim_ortami_satirlari_ve_bos_hucre_yok(yanit, v):
    satirlar = _film_satirlari(yanit[v])
    sozluk = {s[0]: s[1] for s in satirlar}
    perf = yanit[v]['cooling_system']['film_cooling']['performance']
    assert sozluk['Design ambient pressure'] == '%.4f' % (
        yanit[v]['design_ambient']['pressure_bar'])
    assert sozluk['Core Isp (design ambient)'] == '%.2f' % (
        perf['isp_core_design_ambient_s'])
    assert sozluk['Delivered Isp (design ambient, film charged)'] == \
        '%.2f' % perf['isp_delivered_design_ambient_s']
    for s in satirlar:
        assert s[1].strip() not in ('', '0', '--', 'None'), s
    ds_satiri = sozluk['Core Isp (sea level)']
    if yanit[v]['design_ambient']['sea_level']['status'] == 'separated':
        assert ds_satiri == ('not published: the nozzle flow separates at '
                             'sea level')
    else:
        assert ds_satiri == '%.2f' % perf['isp_core_sea_level_s']


def test_k3_rapor_sozlugunde_tr_karsiliklari():
    from hrma.export import rapor_sozluk
    tr = rapor_sozluk.ters_sozluk('tr')
    for en, tr_beklenen in (
            ('Core Isp (design ambient)', 'Çekirdek Isp (tasarım ortamı)'),
            ('Delivered Isp (design ambient, film charged)',
             'Teslim edilen Isp (tasarım ortamı, film kaybı dahil)'),
            ('Design ambient pressure', 'Tasarım ortamı basıncı'),
            ('not published: the nozzle flow separates at sea level',
             'yayımlanmadı: nozulda akış deniz seviyesinde ayrılır')):
        assert tr.get(rapor_sozluk.normalize(en)) == tr_beklenen


# ---------------------------------------------------------------------------
# Kalem 4 — .eng
# ---------------------------------------------------------------------------
def _eng(client, r):
    js = _sessiz(client.post, '/api/export-eng',
                 json={'motor_data': dict(r, motor_name='GO')}).get_json()
    assert js['status'] == 'success', js
    return js


def test_k4_deniz_seviyesinde_dosya_ve_govde_bugunku_gibi(client, yanit):
    js = _eng(client, yanit['ds'])
    assert 'eng_design_ambient' not in js
    assert 'design ambient' not in js['content']


@pytest.mark.parametrize('v', ['vak8', 'vak50', 'irt20'])
def test_k4_ortam_beyani_ve_itki_degismez(client, yanit, v):
    js = _eng(client, yanit[v])
    k = js['eng_design_ambient']
    assert k['mode'] == yanit[v]['design_ambient']['mode']
    assert k['pressure_bar'] == yanit[v]['design_ambient']['pressure_bar']
    yorum = [s for s in js['content'].splitlines() if s.startswith(';')]
    assert any(s.startswith('; design ambient: ') for s in yorum)
    assert any('flown from a sea-level launch pad' in s for s in yorum)
    ds = yanit[v]['design_ambient']['sea_level']
    if ds['status'] == 'separated':
        assert any('the flow separates (Summerfield criterion)' in s
                   for s in yorum)
    else:
        assert any(('thrust %.1f N (attached' % ds['thrust_N']) in s
                   for s in yorum)
    # İtki sayıları DEĞİŞMEZ: ortam beyanı kaldırılmış aynı yanıtın
    # dosyasıyla, yalnız yeni yorum satırları farklı.
    r0 = copy.deepcopy(yanit[v])
    r0['design_ambient']['is_sea_level'] = True
    js0 = _eng(client, r0)
    yeni = [s for s in js['content'].splitlines()
            if s not in js0['content'].splitlines()]
    assert len(yeni) == 3 and all(s.startswith(';') for s in yeni)
    assert [s for s in js['content'].splitlines() if not s.startswith(';')] \
        == [s for s in js0['content'].splitlines() if not s.startswith(';')]


def test_k4_sayfa_durum_satiri_ve_sozluk():
    from tests.test_v307_sivi_ortam import SABLON, SAYFA_SOZLUK
    html = SABLON.read_text(encoding='utf-8')
    sozluk = SAYFA_SOZLUK.read_text(encoding='utf-8')
    for k in ('liq.msg.eng_downloaded_detail_vacuum',
              'liq.msg.eng_downloaded_detail_altitude',
              'liq.msg.eng_downloaded_detail_pressure',
              'liq.msg.eng_downloaded_detail_ambient_undeclared'):
        assert ("TF('%s'" % k) in html, k
        en_tr = re.findall(r"'" + re.escape(k) + r"':\s*'((?:[^'\\]|\\.)*)'",
                           sozluk)
        assert len(en_tr) == 2 and en_tr[0] != en_tr[1], k
    assert 'result.eng_design_ambient' in html


# ---------------------------------------------------------------------------
# Kalem 5–6 — YAPISAL sekme (örnek katı proje: hedef EK 2,5, 6061 kaydı 4,0)
# ---------------------------------------------------------------------------
_RENK = {'--hd-green': 'ok', '--hd-orange': 'warn', '--hd-red': 'err',
         '--hd-ink-dim': 'dim'}
_HUCRE = re.compile(r'<span style="color:var\((--hd-[a-z-]+), [^)]*\); '
                    r'font-family:var\(--hd-mono\);">([0-9.,\-]+)</span>')


@pytest.fixture(scope='module')
def kati():
    motor = SG._motor_yaniti('solid', {})
    sug = SG._node('solid', motor, ['structural'])['structural']
    yuk, eksik = SG._yuk(sug, sug.get('suggested'))
    assert not eksik, eksik
    return motor, yuk


def _yapisal_render(motor, yuk):
    kod, yanit = SG._uc('/analyze_structural_safety', yuk)
    assert kod == 200, str(yanit)[:300]
    ren = SG._node('solid', motor, ['structural'],
                   data={'structural': yanit})['structural']
    return yanit, ren['html']


def _hucreler(html):
    return [(_RENK.get(m.group(1), m.group(1)), float(m.group(2)))
            for m in _HUCRE.finditer(html or '')]


def _beklenen_renk(sf, hedef):
    if sf < 1.0:
        return 'err'
    return 'ok' if sf >= hedef * (1 - 1e-9) else 'warn'


@node_gerekli
def test_k5_iki_gereken_cidar_ve_farkin_nedeni(kati):
    motor, yuk = kati
    yanit, html = _yapisal_render(motor, yuk)
    gor = SG._gorunur(html)
    ca = yanit['structural_analysis']['chamber_analysis']
    dp = yanit['structural_analysis']['design_parameters']
    # Sayılar değişmedi: sekmenin gereken cidarı ve motorun gereken cidarı.
    assert ('Minimum required %.2f mm' % ca['minimum_thickness']) in gor
    m_ca = motor['structural_analysis']['case_analysis']
    assert ('Required wall — motor result %.2f mm'
            % m_ca['wall_thickness_hoop_required_mm']) in gor
    assert 'Why the two required walls differ' in gor
    assert ('at the design pressure %.1f bar (%.2f × chamber pressure; an '
            'HRMA design margin, not a code factor)'
            % (dp['design_pressure'], dp['design_pressure_factor'])) in gor
    assert ('at the chamber pressure %.1f bar (MEOP)'
            % (dp['design_pressure'] / dp['design_pressure_factor'])) in gor


@node_gerekli
@pytest.mark.parametrize('ek', [None, {'safety_factor': 5.0,
                                       'wall_thickness': 0.0046}])
def test_k6_renk_istasyon_hukmuyle_ayni_tabanda(kati, ek):
    """Renk eşiği bu koşumun tasarım hedefi: hedefin altındaki katsayı yeşil,
    hedefi tutan katsayı turuncu basılmaz (malzeme kaydı 4,0 eşik değil).
    İkinci vaka: hedef 5,0 ve 4,6 mm cidar — çember EK'sı 4 ile 5 arasında
    (malzeme eşiğine göre yeşil, hedefe göre turuncu)."""
    motor, yuk = kati
    yuk = dict(yuk, **(ek or {}))
    yanit, html = _yapisal_render(motor, yuk)
    sa = yanit['structural_analysis']
    hedef = sa['safety_analysis']['design_target_assessment'][
        'design_safety_factor_target']
    assert hedef == yuk['safety_factor']
    assert sa['material_properties']['safety_factor'] == 4.0
    hc = _hucreler(html)
    assert hc
    for renk, sf in hc:
        if renk in ('ok', 'warn'):
            assert renk == _beklenen_renk(sf, hedef), (renk, sf, hedef)
    if ek:
        assert any(4.0 < sf < 5.0 and renk == 'warn' for renk, sf in hc)
    gor = SG._gorunur(html)
    assert ('the colours in this tab compare each safety factor with the '
            'design target %.2f' % hedef) in gor
    assert 'Required design SF (material) 4.0' in gor


def test_k6_ve_k1_metinleri_iki_dilde():
    from tests.test_v307_sivi_ortam import ORTAK_SOZLUK
    s = ORTAK_SOZLUK.read_text(encoding='utf-8')
    for k in ('panel.ambient.vacuum', 'panel.ambient.altitudeP',
              'panel.ambient.altitude', 'panel.ambient.pressure',
              'panel.ambient.undeclared', 'panel.performance.baseIspAmbient',
              'panel.performance.baseIspAmbientSurface',
              'panel.comparative.bestAmbientTip',
              'panel.comparative.ambientMixed',
              'panel.comparative.ambientCommon',
              'panel.comparative.ambientNotCompared',
              'panel.comparative.ambientSeaLevel',
              'panel.comparative.snapAmbient',
              'panel.comparative.chartAmbientMixed',
              'panel.structural.wallDefinitionsLabel',
              'panel.structural.wallDefinitionsDiffer',
              'panel.structural.sfColourBasis'):
        en_tr = re.findall(r"'" + re.escape(k) + r"':\s*'((?:[^'\\]|\\.)*)'",
                           s)
        assert len(en_tr) == 2 and en_tr[0] != en_tr[1], k
