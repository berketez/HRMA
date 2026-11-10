"""V306/BAYAT bekçileri — ekrandaki sonuç ekrandaki tasarıma aittir (3.0.6).

NR-9   katı Monte Carlo paneli motor koşusunun kaydına bağlı: yeni hesap
       farklı motoru hesapladıysa eski MC temizlenir ve nedeni yazılır;
       form son hesaptan sonra değiştiyse MC koşmaz; koşarken motor yeniden
       hesaplanırsa gelen yanıt çizilmez.
NR-15  başarılı → hatalı → hatalı → başarılı: tek hesap hatası kutusu, "ESKİ
       SONUÇ" şeridi üç sayfada aynı bileşen (hibrit app.js, katı, sıvı).

Kanıt: docs/scofield/raw/OH/V306/bayat/ (önce/sonra ölçümleri, RAPOR.md).
JS davranışı node ile, şablondan/kaynaktan sökülen işlevler üstünde koşar.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates'
node_gerekli = pytest.mark.skipif(shutil.which('node') is None,
                                  reason='node yok')


def _oku(yol):
    return pathlib.Path(yol).read_text(encoding='utf-8')


def _islev_sonu(metin, ad):
    """``function ad(`` (ya da ``async function ad(``) gövdesinin bitiş indisi."""
    bas = metin.index('function ' + ad + '(')
    derinlik, i = 0, metin.index('{', bas)
    for j in range(i, len(metin)):
        if metin[j] == '{':
            derinlik += 1
        elif metin[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return j + 1
    raise AssertionError('gövde kapanmadı: ' + ad)


def _islev(metin, ad):
    bas = metin.index('function ' + ad + '(')
    if metin[bas - 6:bas] == 'async ':
        bas -= 6
    return metin[bas:_islev_sonu(metin, ad)]


# Yalın DOM: id ile bulunan düğümler, innerHTML ile kurulan tek çocuk,
# öznitelik seçicisiyle querySelector/querySelectorAll.
_DOM = r"""
var DUGUMLER = {};
function oge(id) {
  var d = { id: id, style: {}, _oz: {}, children: [], parentNode: null, _metin: '' };
  d.setAttribute = function (k, v) { d._oz[k] = String(v); };
  d.getAttribute = function (k) { return (k in d._oz) ? d._oz[k] : null; };
  d.hasAttribute = function (k) { return k in d._oz; };
  d.appendChild = function (c) { c.parentNode = d; d.children.push(c); return c; };
  d.insertBefore = function (c, ref) { c.parentNode = d;
    var i = d.children.indexOf(ref); if (i < 0) d.children.push(c); else d.children.splice(i, 0, c); return c; };
  d.removeChild = function (c) { var i = d.children.indexOf(c); if (i >= 0) d.children.splice(i, 1);
    c.parentNode = null; if (DUGUMLER[c.id] === c) delete DUGUMLER[c.id]; return c; };
  Object.defineProperty(d, 'firstChild', { get: function () { return d.children[0] || null; } });
  Object.defineProperty(d, 'lastElementChild', { get: function () { return d.children[d.children.length - 1] || null; } });
  Object.defineProperty(d, 'textContent', {
    get: function () { return d._metin + d.children.map(function (c) { return c.textContent; }).join(''); },
    set: function (v) { d._metin = String(v); d.children = []; } });
  Object.defineProperty(d, 'innerHTML', {
    get: function () { return d._html || ''; },
    set: function (v) { d._html = String(v); d.children = []; d._metin = '';
      var m = /^<(\w+)([^>]*)>/.exec(String(v));
      if (m) { var c = oge(''); var oz = /([\w-]+)="([^"]*)"/g, x;
        while ((x = oz.exec(m[2]))) c._oz[x[1]] = x[2]; d.appendChild(c); } } });
  d.querySelectorAll = function (sec) {
    var m = /\[([\w-]+)(?:="([^"]*)")?\]$/.exec(sec);
    var out = [];
    (function gez(n) { n.children.forEach(function (c) {
      if (m && (m[1] in c._oz) && (m[2] === undefined || c._oz[m[1]] === m[2])) out.push(c); gez(c); }); })(d);
    return out; };
  d.querySelector = function (sec) { return d.querySelectorAll(sec)[0] || null; };
  return d;
}
function kur(id) { var e = oge(id); DUGUMLER[id] = e; return e; }
function bul(id) { if (DUGUMLER[id]) return DUGUMLER[id]; var s = null;
  Object.keys(DUGUMLER).forEach(function (k) { (function gez(n) { n.children.forEach(function (c) {
    if (!s && c.id === id) s = c; gez(c); }); })(DUGUMLER[k]); }); return s; }
var document = { getElementById: bul,
  createElement: function () { return oge(''); },
  addEventListener: function () {}, dispatchEvent: function () {},
  querySelectorAll: function (sec) { var y = DUGUMLER['toast-stack']; return y ? y.querySelectorAll(sec) : []; } };
var window = { document: document, localStorage: { getItem: function () { return null; } } };
global.window = window; global.document = document;
function T(k, fb) { return fb; }
function TF(k, p, fb) { return String(fb).replace(/\{(\w+)\}/g, function (b, a) { return (p && a in p) ? String(p[a]) : b; }); }
"""


def _node(govde):
    # Betik stdin'den verilir (test_node_cagri_sozlesmesi: argv ile betik
    # geçirmek Linux MAX_ARG_STRLEN / macOS ARG_MAX tavanına takılır).
    sonuc = subprocess.run(['node'], input=govde, capture_output=True,
                           text=True, timeout=60)
    assert sonuc.returncode == 0, sonuc.stderr
    return json.loads(sonuc.stdout.strip().splitlines()[-1])


# --------------------------------------------------------------------- NR-9

def _kati_mc_blogu():
    html = _oku(SABLON / 'solid.html')
    bas = html.index('let _solidMcKosusu = null;')
    return html[bas:_islev_sonu(html, 'runSolidMonteCarlo')]


def _mc_kosum(senaryo):
    return _node(_DOM + _oku(JS / 'flight_handoff.js') + r"""
      var FlightHandoff = window.FlightHandoff;
      var HRMAReject = { etiket: function (ad) { return ({propellant_type: 'Yakıt (katalog kaydı)'})[ad] || null; } };
      window.HRMAReject = HRMAReject;
      var box = kur('mc_results'); kur('mc_note'); kur('mc_run_btn');
      var CIZILEN = [], ISTEKLER = [], FORM = {propellant_type: 'kndx', chamber_pressure: 40};
      function collectAllParameters() { return Object.assign({}, FORM); }
      function renderSolidMonteCarlo(mc) { CIZILEN.push(mc.id); box.innerHTML = '<div data-mc="1"></div>'; }
      function showError() {}
      var BEKLEYEN = null;
      global.fetch = function (u, o) { ISTEKLER.push(JSON.parse(o.body)); return new Promise(function (coz) {
        BEKLEYEN = function () { coz({ ok: true, status: 200, json: function () {
          return Promise.resolve({ status: 'success', id: ISTEKLER.length }); } }); }; }); };
      var currentResults = null;
    """ + _kati_mc_blogu() + r"""
      function kayit(form) { var r = {unwired_inputs: {}}; return { results: r, form: Object.assign({}, form) }; }
      function durum() { var c = box.firstChild; return { cizilen: CIZILEN.slice(), istek: ISTEKLER.length,
          onceki: !!(c && c.hasAttribute('data-onceki-tasarim')), kutu: box.textContent,
          not: DUGUMLER.mc_note.textContent, kosu_bagli: _solidMcKosusu === window.ucusHesapFormu }; }
      (async function () { var out = {};
    """ + senaryo + r"""
      console.log(JSON.stringify(out)); })();
    """)


@node_gerekli
def test_kati_mc_ayni_motorun_yeniden_hesabinda_kalir_farkli_motorda_temizlenir():
    r = _mc_kosum(r"""
      var K1 = kayit(FORM); window.ucusHesapFormu = K1; window.currentResults = K1.results;
      var p = runSolidMonteCarlo(); BEKLEYEN(); await p;
      out.ilk = durum();
      // aynı form yeniden hesaplandı -> MC kalır, yeni kayda bağlanır
      var K2 = kayit(FORM); window.ucusHesapFormu = K2; window.currentResults = K2.results;
      _solidMcKosuyuDenetle(K2); out.ayni = durum();
      // yakıt değişti -> eski MC temizlenir, nedeni yazılır
      FORM.propellant_type = 'apcp';
      var K3 = kayit(FORM); window.ucusHesapFormu = K3; window.currentResults = K3.results;
      _solidMcKosuyuDenetle(K3); out.farkli = durum();
    """)
    assert r['ilk']['cizilen'] == [1] and r['ilk']['kosu_bagli'] is True
    assert r['ayni']['onceki'] is False and r['ayni']['kosu_bagli'] is True
    assert r['farkli']['onceki'] is True
    assert 'previous Monte Carlo result belonged to the earlier design' in r['farkli']['kutu']


@node_gerekli
def test_kati_mc_form_degistiyse_kosmaz_alanlari_etiketle_yazar():
    r = _mc_kosum(r"""
      var K1 = kayit(FORM); window.ucusHesapFormu = K1; window.currentResults = K1.results;
      FORM.propellant_type = 'apcp';                     // hesaplanmadı
      await runSolidMonteCarlo(); out.r = durum();
      window.currentResults = null;                      // hiç hesap yok
      await runSolidMonteCarlo(); out.hesapsiz = durum();
    """)
    assert r['r']['istek'] == 0, 'form değişmişken MC istek attı'
    assert 'Yakıt (katalog kaydı)' in r['r']['not']
    assert 'propellant_type' not in r['r']['not']
    assert r['hesapsiz']['istek'] == 0 and 'Run a motor calculation first' in r['hesapsiz']['not']


@node_gerekli
def test_kati_mc_kosarken_motor_degisirse_yanit_cizilmez():
    r = _mc_kosum(r"""
      var K1 = kayit(FORM); window.ucusHesapFormu = K1; window.currentResults = K1.results;
      var p = runSolidMonteCarlo();
      FORM.propellant_type = 'apcp';
      var K2 = kayit(FORM); window.ucusHesapFormu = K2; window.currentResults = K2.results;
      BEKLEYEN(); await p; out.r = durum();
    """)
    assert r['r']['istek'] == 1 and r['r']['cizilen'] == []
    assert r['r']['onceki'] is True


def test_kati_hesap_basarisi_kosu_kaydini_istek_formundan_kurar_ve_mc_yi_denetler():
    html = _oku(SABLON / 'solid.html')
    govde = _islev(html, 'calculateSolid')
    i = govde.index('window.ucusHesapFormu = { results: results, form: data };')
    j = govde.index('displayResults(results);')
    k = govde.index('_solidMcKosuyuDenetle(window.ucusHesapFormu)')
    assert i < j < k
    # Kayıt bir kez, istek formundan; ucusHesapFormunuKaydet aynı sonuç için ezmez.
    kaydet = _islev(html, 'ucusHesapFormunuKaydet')
    assert 'window.ucusHesapFormu.results === results) return;' in kaydet


def test_mc_anahtarlari_iki_dilde():
    src = _oku(JS / 'i18n_pages.js')
    for k in ('solid.msg.mc_stale_design', 'solid.msg.mc_needs_calc',
              'solid.msg.mc_stale_motor'):
        assert src.count("'%s':" % k) == 2, k
    tr = src[src.index("'solid.msg.mc_stale_design': 'Motor yeniden"):]
    assert 'temizlendi' in tr.split('\n')[0]


# -------------------------------------------------------------------- NR-15

def _hibrit_blogu():
    js = _oku(JS / 'app.js')
    parcalar = [re.search(r"const HESAP_HATASI_IMI = '[^']+';", js).group(0)]
    for ad in ('setExportResultsEnabled', 'invalidateStaleResults',
               'hesapHatasiGoster', 'eskiSonucBandi', 'clearErrorNotices'):
        parcalar.append(_islev(js, ad))
    return '\n'.join(parcalar)


@node_gerekli
def test_hibrit_basarili_hatali_hatali_basarili_dizisi():
    r = _node(_DOM + r"""
      var panel = kur('resultsPanel'); panel.style.display = 'block';
      panel.appendChild(oge('performanceMetrics'));
      var kap = kur('hrmaNotices');
      ['exportResultsBtn', 'exportSTLBtn', 'downloadEngBtn'].forEach(kur);
      var currentResults = {motor: {thrust: 3000}};
      function showError(m) { var k = oge(''); k.setAttribute('data-notice-type', 'error');
        k.textContent = m; kap.appendChild(k); }
      function showNotice(m) { var k = oge(''); k.setAttribute('data-notice-type', 'info');
        k.textContent = m; kap.appendChild(k); }
    """ + _hibrit_blogu() + r"""
      function adim() { var b = document.getElementById('hdEskiSonucBandi');
        return { kutular: kap.querySelectorAll('[data-notice-type="error"]').map(function (k) { return k.textContent; }),
                 bant: b ? b.textContent : null, bant_ilk: panel.firstChild === b,
                 panel: panel.style.display, sonuc: currentResults === null ? null : 'var',
                 disa: document.getElementById('exportResultsBtn').disabled };
      }
      var out = {};
      showNotice('yörünge bilgisi');                     // başka kaynaklı bildirim
      invalidateStaleResults(); hesapHatasiGoster(function () { showError('Eksik alan: İtki'); });
      out.hata1 = adim();
      invalidateStaleResults(); hesapHatasiGoster(function () { showError('Eksik alan: İtki • Eksik alan: Yanma Süresi'); });
      out.hata2 = adim();
      out.diger = kap.querySelectorAll('[data-notice-type="info"]').length;
      clearErrorNotices(); eskiSonucBandi(false); currentResults = {motor: {thrust: 3000}};
      out.basari = adim();
      // hiç başarılı hesap yokken (panel kapalı) şerit konmaz
      panel.style.display = 'none'; invalidateStaleResults(); out.kapali = adim();
      console.log(JSON.stringify(out));
    """)
    assert r['hata1']['kutular'] == ['Eksik alan: İtki']
    assert r['hata1']['bant'].startswith('OLD RESULT') and r['hata1']['bant_ilk']
    assert r['hata1']['panel'] == 'block', 'sonuç gizlendi; brif: aynı şeritle işaretlenir'
    assert r['hata1']['sonuc'] is None and r['hata1']['disa'] is True
    assert r['hata2']['kutular'] == ['Eksik alan: İtki • Eksik alan: Yanma Süresi']
    assert r['diger'] == 1, 'hesap hatası başka kaynaklı bildirimi sildi'
    assert r['basari']['kutular'] == [] and r['basari']['bant'] is None
    assert r['kapali']['bant'] is None


def test_hibrit_sayfa_dogrulayicisi_dali_da_isaretler():
    js = _oku(JS / 'app.js')
    govde = _islev(js, 'calculate')
    i = govde.index('if (Array.isArray(sayfaHatalari) && sayfaHatalari.length) {')
    dal = govde[i:govde.index('return;', i)]
    assert 'invalidateStaleResults();' in dal and 'hesapHatasiGoster(' in dal
    j = govde.index("handleError(error, 'Main Calculation Function')")
    assert 'hesapHatasiGoster(' in govde[j - 200:j]
    dogrula = _islev(js, 'validateInputs')
    assert 'hesapHatasiGoster(' in dogrula
    assert 'eskiSonucBandi(false)' in _islev(js, 'displayCalculationResults')


def _kati_sivi_hata_dizisi(sayfa, imi, islev):
    html = _oku(SABLON / (sayfa + '.html'))
    govde = _islev(html, islev)
    catch = govde[govde.index('} catch (error) {'):]
    return html, catch, imi


@pytest.mark.parametrize('sayfa,islev,imi,temizle', [
    ('solid', 'calculateSolid', 'data-solid-calc-error', "querySelectorAll('#toast-stack [data-solid-calc-error]')"),
    ('liquid', 'calculateLiquid', 'data-liquid-calc-error', '_liquidHesapHatalariniTemizle();'),
])
def test_kati_sivi_hata_kutusu_tek_ve_serit(sayfa, islev, imi, temizle):
    html = _oku(SABLON / (sayfa + '.html'))
    govde = _islev(html, islev)
    catch = govde[govde.index('} catch (error) {'):]
    # yeni hata, eskisini showError'dan ÖNCE kaldırır; şerit konur
    assert catch.index(temizle) < catch.index('showError(')
    assert imi in catch and '_eskiSonucBandi(true)' in catch
    # başarı şeridi kaldırır; şerit bileşeni üç sayfada aynı
    assert '_eskiSonucBandi(false)' in govde
    bant = _islev(html, '_eskiSonucBandi')
    for parca in ("bant.id = 'hdEskiSonucBandi'", "bant.className = 'hd-eski-sonuc-bandi'",
                  "'common.staleResults'"):
        assert parca in bant
    app = _islev(_oku(JS / 'app.js'), 'eskiSonucBandi')
    for parca in ("bant.id = 'hdEskiSonucBandi'", "bant.className = 'hd-eski-sonuc-bandi'",
                  "'common.staleResults'"):
        assert parca in app


# --------------------------------------------------------------------- NR-7

_TARAMA = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
           'chamber_pressure': 20.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
           'param_type': 'of_ratio', 'param_start': 4.0, 'param_end': 8.0,
           'param_steps': 4, 'time_budget_s': 300}


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _tara(istemci, **ek):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        r = istemci.post('/parametric-analysis', json=dict(_TARAMA, **ek))
    return r.status_code, r.get_json()


def test_surdurulen_tarama_tek_istekle_bit_ayni(istemci):
    """Aynı eksen, kaç istekte hesaplanırsa hesaplansın aynı noktalar."""
    d0, tam = _tara(istemci)
    assert d0 == 200 and tam['points_succeeded'] == 4
    assert [p['sweep_index'] for p in tam['results']] == [0, 1, 2, 3]
    assert tam['sweep_values'] == [4.0, 4.0 + 4 / 3, 4.0 + 8 / 3, 8.0]
    # Uçlar ayrı istekte; iç noktalar küçücük bütçeyle (yavaş makine):
    # sürdürme isteği erken reddedilmez, her istek EN AZ bir nokta ilerler.
    d1, a = _tara(istemci, param_indices=[0, 3])
    d2, b = _tara(istemci, param_indices=[1, 2], time_budget_s=1e-9)
    assert (d1, d2) == (200, 200)
    assert [p['sweep_index'] for p in b['results']] == [1]
    assert b['truncated_by_time_budget']['not_attempted_indices'] == [2]
    assert b['truncated_by_time_budget']['points_not_attempted'] == 1
    d3, c = _tara(istemci, param_indices=[2], time_budget_s=1e-9)
    assert d3 == 200 and 'truncated_by_time_budget' not in c
    birlesik = sorted(a['results'] + b['results'] + c['results'],
                      key=lambda p: p['sweep_index'])
    assert json.dumps(birlesik, sort_keys=True) == json.dumps(tam['results'], sort_keys=True)
    assert tam['plot_series'][0] == {'key': 'isp', 'divisor': 1.0}


def test_eksik_sira_grafikte_bosluktur(istemci):
    d, y = _tara(istemci, param_indices=[0, 3])
    assert d == 200
    iz = json.loads(y['plot'])['data']
    assert len(iz[0]['x']) == 4
    assert iz[0]['y'][1] is None and iz[0]['y'][2] is None
    assert iz[0]['y'][0] == y['results'][0]['isp']
    assert iz[0].get('connectgaps') in (None, False)


@pytest.mark.parametrize('kotu', [[], [4], [1, 1], 'x', [True], [0.5], [-1]])
def test_gecersiz_sira_listesi_adiyla_reddedilir(istemci, kotu):
    d, y = _tara(istemci, param_indices=kotu)
    assert d == 422 and y['error'] == 'invalid_sweep_indices'
    assert y['invalid_fields'][0]['field'] == 'param_indices'


def test_tarama_danisma_aramasini_atlar_ama_ilk_istek_kapisi_durur():
    src = _oku(KOK / 'hrma' / 'app.py')
    i = src.index('def parametric_analysis():')
    govde = src[i:src.index('\ndef ', i + 10)]
    assert 'uq_mode=True,' in govde
    # Donma koruması: ilk istekte en küçük tarama bütçeye sığmıyorsa 422 kalır.
    assert "and _sira_istegi is None):" in govde
    assert "'parametric_time_budget_exceeded'" in govde


_PAR_ORTAK = r"""
function isFiniteNum(x) { return typeof x === 'number' && isFinite(x); }
function i18nFmt(k, p, fb) { return String(fb).replace(/\{(\w+)\}/g, function (b, a) { return (p && a in p) ? String(p[a]) : b; }); }
function i18nText(k, fb) { return fb; }
var DURUMLAR = [];
function parametrikDurum(m) { DURUMLAR.push(m); }
function assertParametricMatchesRequest() {}
"""


def _par_islevleri():
    adv = _oku(SABLON / 'advanced.html')
    return _islev(adv, 'parametrikSurdur')


@node_gerekli
def test_arayuz_kesilen_taramayi_ayni_eksende_surdurur_ve_bosluk_birakir():
    sv = [1.5, 2.0, 2.5, 3.0]
    fig = {'data': [{'x': [1.5, 2.0, 2.5, 3.0], 'y': [10, None, None, 40]},
                    {'x': [1.5, 2.0, 2.5, 3.0], 'y': [1, None, None, 4]}], 'layout': {}}
    ilk = {'status': 'success', 'points_requested': 4, 'sweep_values': sv,
           'plot_series': [{'key': 'isp', 'divisor': 1}, {'key': 'thrust', 'divisor': 1}],
           'results': [{'sweep_index': 0, 'isp': 10, 'thrust': 1},
                       {'sweep_index': 3, 'isp': 40, 'thrust': 4}],
           'failed_points': [], 'points_failed': 0, 'warning': 'cut short',
           'truncated_by_time_budget': {'not_attempted_indices': [1, 2], 'points_not_attempted': 2},
           'plot': json.dumps(fig)}
    yanitlar = [
        # 1. sürdürme: yalnız sıra 1, sıra 2 yine kaldı
        {'status': 'success', 'results': [{'sweep_index': 1, 'isp': 20, 'thrust': 2}],
         'failed_points': [], 'truncated_by_time_budget': {'not_attempted_indices': [2]}},
        # 2. sürdürme: uç hata verdi -> sıra 2 boşluk kalır, döngü durur
        None,
    ]
    r = _node(_PAR_ORTAK + _par_islevleri() + r"""
      var YANITLAR = %s, ISTEKLER = [];
      global.fetch = function (u, o) { ISTEKLER.push(JSON.parse(o.body).param_indices);
        var y = YANITLAR.shift();
        return Promise.resolve({ ok: !!y, status: y ? 200 : 500,
          json: function () { return Promise.resolve(y || {error: 'x'}); } }); };
      var ILK = %s;
      parametrikSurdur(ILK, {param_type: 'of_ratio', param_start: 1.5, param_end: 3}).then(function (r) {
        var f = JSON.parse(r.plot);
        console.log(JSON.stringify({istekler: ISTEKLER, ok: r.points_succeeded,
          kesik: r.truncated_by_time_budget || null, y0: f.data[0].y, y1: f.data[1].y,
          x0: f.data[0].x, durum: DURUMLAR, uyari: r.warning || null}));
      });
    """ % (json.dumps(yanitlar), json.dumps(ilk)))
    assert r['istekler'] == [[1, 2], [2]]
    assert r['ok'] == 3
    assert r['y0'] == [10, 20, None, 40] and r['y1'] == [1, 2, None, 4]
    assert r['x0'] == sv
    assert r['kesik']['not_attempted_indices'] == [2]
    assert r['kesik']['points_not_attempted'] == 1
    assert 'continuing the sweep on the same axis' in r['durum'][0]


@node_gerekli
def test_arayuz_tamamlanan_surdurmede_kesik_ve_eski_uyari_kalkar():
    ilk = {'status': 'success', 'points_requested': 3, 'sweep_values': [1, 2, 3],
           'plot_series': [{'key': 'isp', 'divisor': 1}],
           'results': [{'sweep_index': 0, 'isp': 1}, {'sweep_index': 2, 'isp': 3}],
           'failed_points': [], 'warning': 'The sweep was cut short',
           'truncated_by_time_budget': {'not_attempted_indices': [1]},
           'plot': json.dumps({'data': [{'x': [1, 2, 3], 'y': [1, None, 3]}], 'layout': {}})}
    r = _node(_PAR_ORTAK + _par_islevleri() + r"""
      global.fetch = function () { return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve({status: 'success',
          results: [{sweep_index: 1, isp: 2}], failed_points: []}); } }); };
      parametrikSurdur(%s, {}).then(function (r) {
        console.log(JSON.stringify({kesik: 'truncated_by_time_budget' in r, uyari: 'warning' in r,
          y: JSON.parse(r.plot).data[0].y, ok: r.points_succeeded}));
      });
    """ % json.dumps(ilk))
    assert r == {'kesik': False, 'uyari': False, 'y': [1, 2, 3], 'ok': 3}


@node_gerekli
def test_hibrit_parametrik_tarama_farkli_tasarim_hesabinda_temizlenir():
    js = _oku(JS / 'app.js')
    adv = _oku(SABLON / 'advanced.html')
    bas = adv.index('let _parametrikTaban = null;')
    blok = adv[bas:adv.index('};', adv.index('window.parametrikTasarimDenetle')) + 2]
    r = _node(_DOM + _PAR_ORTAK
              + re.search(r"const YORUNGE_MOTOR_DISI_ALANLAR = \[.*?\];", js, re.S).group(0)
              + _islev(js, 'yorungeIcinDegisenMotorAlanlari') + blok + r"""
      var cizim = kur('parametric_plot'); kur('parametric_honesty'); kur('parametric_status');
      cizim.innerHTML = '<div data-plot="1"></div>';
      _parametrikTaban = _parametrikMotorFormu({thrust: 3000, of_ratio: 6, param_start: 4, motor_name: 'a'});
      var out = {};
      out.ayni = window.parametrikTasarimDenetle({thrust: 3000, of_ratio: 6, param_start: 9, motor_name: 'b',
                                                  vehicle_mass_dry: 7});
      out.ayni_cizim = !!cizim.querySelector('[data-plot]');
      out.farkli = window.parametrikTasarimDenetle({thrust: 2500, of_ratio: 6});
      out.onceki = !!cizim.querySelector('[data-onceki-tasarim]');
      out.metin = cizim.textContent;
      out.tekrar = window.parametrikTasarimDenetle({thrust: 2000});
      console.log(JSON.stringify(out));
    """)
    assert r['ayni'] is False and r['ayni_cizim'] is True
    assert r['farkli'] is True and r['onceki'] is True
    assert 'previous sweep belonged to the earlier design' in r['metin']
    assert r['tekrar'] is False


def test_hibrit_hesap_basarisi_parametrik_denetimi_cagirir():
    govde = _islev(_oku(JS / 'app.js'), 'calculate')
    i = govde.index('displayCalculationResults(results);')
    assert 'window.parametrikTasarimDenetle(data)' in govde[i:i + 700]


def test_parametrik_durustluk_kutusu_ham_anahtar_basmaz():
    adv = _oku(SABLON / 'advanced.html')
    govde = _islev(adv, 'runParametricAnalysis')
    assert "' — truncated_by_time_budget: '" not in govde
    assert "alan.push(k + ': ' + kesik[k])" not in govde
    assert "' sweep points could not be computed'" not in govde
    assert 'await parametrikSurdur(results, data);' in govde
    src = _oku(JS / 'i18n_advanced.js')
    for k in ('adv.js.parametricContinuing', 'adv.js.parametricFailedPoints',
              'adv.js.parametricIncomplete', 'adv.msg.parametricStaleDesign'):
        assert src.count("'%s':" % k) == 2, k


# --------------------------------------------------------------------- NR-8

def test_hibrit_3b_model_dugmesi_acilir_pencere_acmaz_step_uretir():
    adv = _oku(SABLON / 'advanced.html')
    assert 'window.open(' not in adv, 'about:blank özet penceresi geri geldi'
    assert 'displayCompleteDesignPackage' not in adv
    govde = _islev(adv, 'generateCAD')
    assert 'await exportSTEP()' in govde
    assert "secenek.indir === false" in govde
    # tam paket akışı STEP'i ikinci kez indirmez
    paket = _islev(adv, 'generateCompletePackage')
    assert 'generateCAD({ indir: false })' in paket
    # özetteki indirmelerin her biri ana sayfada kendi düğmesinde
    for cagri in ('onclick="exportDrawingsPDF()"', 'onclick="exportDXF()"',
                  'onclick="exportSTL()"', 'onclick="generateCompletePackage()"'):
        assert cagri in adv, cagri
    src = _oku(JS / 'i18n_advanced.js')
    kalan = sorted(set(re.findall(r"'(adv\.pop\.[\w.]+)':", src)))
    assert kalan == ['adv.pop.burnTime'], ('sökülen pencerenin anahtarları kaldı: %r' % kalan)
    assert src.count("'adv.txt.generate3dModel': '3B Model Üret (STEP)'") == 1
    for k in ('adv.txt.drawingsPdf', 'adv.txt.dxfDrawing', 'adv.js.cadDoneStep',
              'adv.js.cadDoneScene'):
        assert src.count("'%s':" % k) == 2, k


@node_gerekli
def test_hibrit_3b_model_kapisi_ve_hukmu():
    adv = _oku(SABLON / 'advanced.html')
    r = _node(_DOM + r"""
      var MESAJ = [], INDIRILEN = 0, STEP_OK = true;
      function showMessage(m, t) { MESAJ.push(t); }
      function i18nText(k, fb) { return fb; }
      function mountMotorViz() { return true; }
      async function exportSTEP() { INDIRILEN++; return STEP_OK; }
      var durum = kur('cadStatus'); kur('exportSTLBtn'); var sahne = kur('cad3DPanel');
      sahne.scrollIntoView = function () { sahne._kaydi = true; };
      document.querySelector = function () { return null; };
      var currentResults = null;
    """ + _islev(adv, 'generateCAD') + r"""
      (async function () { var out = {};
        out.hesapsiz = await generateCAD(); out.hesapsiz_indirilen = INDIRILEN;
        currentResults = { motor: { thrust: 3000 } };
        out.tam = await generateCAD(); out.tam_durum = durum.textContent; out.kaydi = !!sahne._kaydi;
        out.sahne = await generateCAD({ indir: false }); out.indirilen = INDIRILEN;
        STEP_OK = false; out.dustu = await generateCAD(); out.dustu_durum = durum.textContent;
        console.log(JSON.stringify(out)); })();
    """)
    assert r['hesapsiz'] is False and r['hesapsiz_indirilen'] == 0
    assert r['tam'] is True and 'STEP package' in r['tam_durum'] and r['kaydi'] is True
    assert r['sahne'] is True and r['indirilen'] == 1, 'tam paket akışı STEP indirdi'
    assert r['dustu'] is False and r['dustu_durum'] == 'Design generation failed'


# ------------------------------------------------------------------ kalem 5

def test_parametrik_aralik_kapisi_ham_oznitelik_basmaz():
    adv = _oku(SABLON / 'advanced.html')
    kapi = _islev(adv, 'paramRangeGate')
    assert 'data-param-type=' not in kapi and "' vs param_type='" not in kapi
    assert "i18nFmt('adv.js.parametricRangeOwner'" in kapi
    govde = _islev(adv, 'runParametricAnalysis')
    assert 'HRMAReject.metni(results, response.status)' in govde
    assert _oku(JS / 'i18n_advanced.js').count("'adv.js.parametricRangeOwner':") == 2


@node_gerekli
def test_kati_mc_kabul_olcutu_sozlukten_ve_etkin_dilin_ondaligiyla():
    html = _oku(SABLON / 'solid.html')
    govde = _islev(html, 'renderSolidMonteCarlo')
    i = govde.index('const kd = (mc.criteria_detail')
    blok = govde[i:govde.index('box.innerHTML = successCard')]
    r = _node(r"""
      function numTxt(v, d) { return v.toFixed(d).replace('.', ','); }
      function TF(k, p, fb) { return String(fb).replace(/\{(\w+)\}/g, function (b, a) { return (p && a in p) ? String(p[a]) : b; }); }
      function sar(mc) {
    """ + blok + r"""
        return criteriaText; }
      var kd = {thrust_band_rel: 0.1, isp_band_rel: 0.05, max_pressure_factor: 1.2,
                burn_rate_a_rel_sigma: 0.03, burn_rate_n_abs_sigma: 0.005,
                density_rel_sigma: 0.01, c_star_rel_sigma: 0.01, burn_rate_law: 'kndx'};
      console.log(JSON.stringify({tam: sar({criteria_detail: kd, criteria: 'TR metin'}),
        yok: sar({criteria: '<b>ham</b>'})}));
    """)
    assert 'thrust ±10%' in r['tam'] and 'n ±0,005' in r['tam'] and '× 1,2' in r['tam']
    assert ("piecewise 'kndx' law" in r['tam'] or 'piecewise &#39;kndx&#39; law' in r['tam'])
    assert 'TR metin' not in r['tam']
    assert '&lt;b&gt;' in r['yok'], 'ucun cümlesi HTML olarak basıldı'
    src = _oku(JS / 'i18n_pages.js')
    for k in ('solid.msg.mc_criteria', 'solid.msg.mc_criteria_law'):
        assert src.count("'%s':" % k) == 2, k


def test_eski_sonuc_seridi_dil_degisiminde_cevrilir():
    """Şerit üç sayfada data-i18n taşır: I18N.apply dil değişiminde çevirir."""
    for kaynak, ad in ((SABLON / 'solid.html', '_eskiSonucBandi'),
                       (SABLON / 'liquid.html', '_eskiSonucBandi'),
                       (JS / 'app.js', 'eskiSonucBandi')):
        govde = _islev(_oku(kaynak), ad)
        assert "bant.setAttribute('data-i18n', 'common.staleResults')" in govde, kaynak
    adv = _oku(SABLON / 'advanced.html')
    assert 'data-onceki-tasarim="1" data-i18n="adv.msg.parametricStaleDesign"' in adv


@node_gerekli
def test_arayuz_surdurmede_hepsi_dusen_parca_dusen_sayilir():
    ilk = {'status': 'success', 'points_requested': 3, 'sweep_values': [1, 2, 3],
           'plot_series': [{'key': 'isp', 'divisor': 1}],
           'results': [{'sweep_index': 0, 'isp': 1}], 'failed_points': [],
           'truncated_by_time_budget': {'not_attempted_indices': [1, 2]},
           'plot': json.dumps({'data': [{'x': [1, 2, 3], 'y': [1, None, None]}], 'layout': {}})}
    r = _node(_PAR_ORTAK + _par_islevleri() + r"""
      global.fetch = function () { return Promise.resolve({ ok: false, status: 422,
        json: function () { return Promise.resolve({status: 'error', results: [],
          failed_points: [{sweep_index: 1, sweep_value: 2, reason: 'x'},
                          {sweep_index: 2, sweep_value: 3, reason: 'y'}]}); } }); };
      parametrikSurdur(%s, {}).then(function (r) {
        console.log(JSON.stringify({kesik: 'truncated_by_time_budget' in r,
          dusen: r.points_failed, y: JSON.parse(r.plot).data[0].y}));
      });
    """ % json.dumps(ilk))
    assert r == {'kesik': False, 'dusen': 2, 'y': [1, None, None]}
