"""Faz 6 / F2b — ``hrma/templates/liquid.html`` bekçi testleri.

Tarayıcı denetiminin sıvı sayfasında bulduğu ikinci küme kalemi KİLİTLER.
Her test kusuru YENİDEN ÜRETİR: düzeltme geri alınırsa test kırılır.

Kapsanan bulgular
-----------------
T44  Excel 'Geometry' sayfası ``Cooling channels | 80`` satırını hiçbir not
     düşmeden yazıyordu; oysa AYNI koşuda uygulamanın uyarı paneli "80 kanal
     30,8 mm boğaz çevresine sığmıyor, geometrik üst sınır 21" diyordu.
     Ekranda "imkânsız" denen sayı mühendislik teslimatına uyarısız geçiyordu.
T45  Ham float ekrana basılıyordu: '(Optimal: 2.806883164944784)' (16
     basamak), 'Chamber Temperature: 3707.0404366159974 K' (17 basamak),
     form alanında 'Oxidizer Density: 1141.1612390428575' ve enjeksiyon
     hızları 'Fuel Vel: 49.49747468305833 m/s'.
T46  3B tank grafiğinde 19 adlandırılmış iz vardı ama efsane HİÇ
     çizilmiyordu (ölçüldü: efsane kutusu 0 px): Plotly'de ``mesh3d`` izleri
     iz düzeyinde ``showlegend`` açılmadıkça efsaneye girmez. Ayrıca kap
     400 px, layout 600 px istiyordu — grafiğin altı kırpılıyordu.
T62  'Total Impulse' alt sekmesi toplam impulsü HİÇ göstermiyordu; altındaki
     beş grafik (karışım oranı, irtifa, yanma verimi, kayıp pastası, tank 3B)
     toplam impulsle ilgisizdi.
T63  Aynı irtifa eğrisi iki grafikte, aynı başlıkla, farklı çözünürlükte
     çiziliyordu: altitude_plot 8 nokta (0/1/5/10/20/50/80/100 km), altChart
     13 EŞİT aralıklı nokta. Eşit aralıklı örnekleme deniz seviyesindeki
     hızlı değişimi düz çizgiye indiriyordu.
T65  combustionChart'ın x ekseni başlığı ``null``'dı ve üçüncü çubuğu
     niteliksiz 'Overall' diye etiketliyordu; hemen yanındaki kayıp pastası
     da 'Overall Efficiency: 82.4%' diyor — iki FARKLI büyüklük, aynı ad.

Yöntem
------
Şablonun JS'i "yazılmış mı" diye taranmaz: ilgili fonksiyonlar ve HTML
şablon literalleri ``liquid.html``'den kesilip GERÇEK node içinde, GERÇEK
çözücü yanıtıyla çalıştırılır; ÜRETTİKLERİ ölçülür (Plotly çağrısının izleri
ve düzeni, /api/export-xlsx'e giden gövde, üretilen HTML). Yalnız teslim
edilen HTML'in kendisi (alt sekme düğmesi) doğrudan sayfadan okunur.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'
COMMON_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_common.js'

NODE = shutil.which('node')

#: Denetimin koştuğu tasarım noktası (sayfanın form varsayılanları).
LIQUID_FORM = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox',
    'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'nozzle_expansion_ratio': 50, 'max_burn_duration': 400,
    'combustion_efficiency': 97, 'contraction_ratio': 4,
    'characteristic_length': 1.2, 'chamber_wall_thickness': 5,
    'cooling_type': 'regenerative', 'injector_type': 'impinging',
    'engine_cycle': 'pressure_fed', 'safety_factor': 2.5,
    # Sığmayan kanal sayısı kusurun ÖN KOŞULU: sayfanın varsayılanı da budur.
    'cooling_channels': 80,
}

#: Sığmama uyarısının kodu (hrma/engines/liquid_rocket_engine.py::_cooling_channels).
COOLING_FIT_CODE = 'warn.liquid.cooling_channels_do_not_fit'


# ===========================================================================
# Şablondan JS kesme
# ===========================================================================

def _template_source():
    return LIQUID_HTML.read_text(encoding='utf-8')


def js_function(name, src=None):
    """Üst düzey bir fonksiyonun kaynağı (``async`` olanlar dahil).

    Şablonda üst düzey fonksiyonlar 8 boşluk girintili ve kapanış süslü
    ayracı kendi satırında; kesme sınırı budur.
    """
    src = src if src is not None else _template_source()
    for prefix in ('\n        function %s(', '\n        async function %s('):
        start = src.find(prefix % name)
        if start != -1:
            break
    assert start != -1, 'liquid.html içinde %s() yok' % name
    end = src.find('\n        }\n', start)
    assert end != -1, '%s() kapanışı bulunamadı' % name
    return src[start:end + len('\n        }\n')]


def js_const(name, src=None):
    """Üst düzey ``const`` bildirimi (çok satırlı olabilir)."""
    src = src if src is not None else _template_source()
    start = src.find('\n        const %s ' % name)
    assert start != -1, 'liquid.html içinde const %s yok' % name
    depth = 0
    i = start
    while i < len(src):
        ch = src[i]
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == ';' and depth == 0:
            return src[start:i + 1]
        i += 1
    raise AssertionError('const %s sonu bulunamadı' % name)


def js_template_literal(anchor, src=None):
    """``anchor`` ifadesinden sonraki DENGELİ şablon literalini döndürür.

    Sayfadaki büyük HTML blokları ``x.innerHTML = `...`;`` biçiminde
    yazılmış ve içlerinde ``${cond ? `...` : ''}`` gibi İÇ İÇE literaller
    var; bu yüzden ilk kapanış ters tırnağı aramak yetmez, ``${`` derinliği
    izlenir.
    """
    src = src if src is not None else _template_source()
    start = src.find(anchor)
    assert start != -1, 'liquid.html içinde %r yok' % anchor
    i = src.index('`', start)
    begin = i
    i += 1
    depth = 0                      # kaç tane açık ${ var
    while i < len(src):
        ch = src[i]
        if ch == '\\':
            i += 2
            continue
        if ch == '$' and src[i + 1:i + 2] == '{':
            depth += 1
            i += 2
            continue
        if ch == '}' and depth:
            depth -= 1
            i += 1
            continue
        if ch == '`':
            if depth == 0:
                return src[begin:i + 1]
            # iç literal: kendi kapanışına kadar atla
            j = i + 1
            inner = 0
            while j < len(src):
                c = src[j]
                if c == '\\':
                    j += 2
                    continue
                if c == '$' and src[j + 1:j + 2] == '{':
                    inner += 1
                    j += 2
                    continue
                if c == '}' and inner:
                    inner -= 1
                    j += 1
                    continue
                if c == '`' and inner == 0:
                    break
                j += 1
            i = j + 1
            continue
        i += 1
    raise AssertionError('%r için literal kapanışı bulunamadı' % anchor)


# ===========================================================================
# node koşum ortamı
# ===========================================================================

JS_PRELUDE = r"""
'use strict';
const fs = require('fs');
const __in = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

const __DICT = __in.sozluk || {};
function __interp(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (whole, name) {
        return (params && Object.prototype.hasOwnProperty.call(params, name))
            ? String(params[name]) : whole;
    });
}
function T(key, fallback) { return __DICT[key] || fallback || key; }
function TF(key, params, fallback) {
    return __interp(__DICT[key] || fallback || key, params);
}
// Sayfanın uyarı çeviricisi window.I18N.tf üzerinden geçer; uygulamadaki
// gibi kod + parametre alır ve sözlükten metni kurar.
const window = {
    currentResults: null,
    I18N: { tf: function (code, params, fallback) {
        return __interp(__DICT[code] || fallback || code, params); } }
};

const __nodes = {};
function __el(id) {
    if (!__nodes[id]) {
        __nodes[id] = { id: id, value: '', textContent: '', dataset: {},
                        style: {}, innerHTML: '', children: [],
                        appendChild: function (c) { this.children.push(c); },
                        insertBefore: function (c) { this.children.push(c); },
                        querySelector: function () { return null; } };
    }
    return __nodes[id];
}
const document = {
    getElementById: function (id) { return __nodes[id] || null; },
    createElement: function (tag) {
        return { tagName: tag, dataset: {}, style: {}, innerHTML: '',
                 textContent: '', children: [],
                 appendChild: function (c) { this.children.push(c); },
                 insertBefore: function (c) { this.children.push(c); } };
    },
    querySelector: function () { return null; }
};

// Plotly çağrısı YAKALANIR: izler ve düzen olduğu gibi ölçülür.
const __cizimler = {};
function liquidPlot(target, traces, layout) {
    const id = (typeof target === 'string') ? target : (target && target.id);
    __cizimler[id] = { traces: traces, layout: layout,
                       kapYuksekligi: (target && target.style)
                                      ? target.style.height : null };
    return null;
}
function createChartDiv(id) { return __el(id); }

// Dışa aktarma yardımcıları
const __istekler = [];
function fetch(url, opts) {
    __istekler.push({ url: url, body: JSON.parse(opts.body) });
    return Promise.resolve({ ok: true, blob: function () {
        return Promise.resolve({}); } });
}
function showWarning() {}
function showSuccess() {}
function showMessage() {}
function showError() {}
function _liquidExportStatus() {}
function _triggerLiquidDownload() {}
function _liquidSheetsToCsvBlob() { return {}; }
"""

JS_EPILOGUE = r"""
const senaryo = __in.senaryo;

function bitir(out) { process.stdout.write(JSON.stringify(out)); }

if (senaryo === 'excel') {
    window.currentResults = __in.cr;
    exportLiquidExcel().then(function () {
        const govde = __istekler.length ? __istekler[0].body : null;
        bitir({ istek_sayisi: __istekler.length, govde: govde });
    });
} else if (senaryo === 'tank') {
    createTankVisualization(__in.tanklar);
    const c = __cizimler['tankVisualization'];
    bitir({
        iz_sayisi: c.traces.length,
        efsanede: c.traces.filter(function (t) { return t.showlegend === true; })
                          .map(function (t) { return t.name; }),
        gizli: c.traces.filter(function (t) { return t.showlegend === false; })
                       .map(function (t) { return t.name; }),
        gruplar: c.traces.map(function (t) { return t.legendgroup || null; }),
        showlegend: c.layout.showlegend,
        yukseklik: c.layout.height,
        kap_yuksekligi: c.kapYuksekligi,
        margin: c.layout.margin || null
    });
} else if (senaryo === 'irtifa_haritasi') {
    createAltitudePerformanceChart(__in.harita, __in.cr);
    const c = __cizimler['altChart'];
    bitir({
        x: c.traces[0].x,
        y_sayisi: c.traces[0].y.length,
        baslik: c.layout.title,
        x_baslik: c.layout.xaxis.title,
        shapes: (c.layout.shapes || []).map(function (s) { return s.x0; }),
        ann: (c.layout.annotations || []).map(function (a) { return a.text; })
    });
} else if (senaryo === 'yanma') {
    displayCombustionEfficiency(__in.analiz);
    const c = __cizimler['combustionChart'];
    bitir({
        kategoriler: c.traces[0].x,
        degerler: c.traces[0].y,
        x_baslik: c.layout.xaxis ? c.layout.xaxis.title : null,
        y_baslik: c.layout.yaxis ? c.layout.yaxis.title : null,
        baslik: c.layout.title
    });
} else if (senaryo === 'kunye') {
    const results = __in.cr;
    bitir({ html: __KUNYE_LITERAL__ });
} else if (senaryo === 'altsistem') {
    const results = __in.cr;
    bitir({ html: __ALTSISTEM_LITERAL__ });
} else if (senaryo === 'tank_karti') {
    const tankData = __in.tanklar;
    bitir({ html: __TANKKART_LITERAL__ });
} else if (senaryo === 'basamak') {
    bitir({
        yogunluk: liquidSigFig(__in.deger_yogunluk, LIQUID_SIGFIG_DENSITY),
        viskozite: liquidSigFig(__in.deger_viskozite, LIQUID_SIGFIG_TRANSPORT),
        sifir: liquidSigFig(0, LIQUID_SIGFIG_DENSITY),
        gecersiz: liquidSigFig(NaN, LIQUID_SIGFIG_DENSITY)
    });
} else {
    throw new Error('bilinmeyen senaryo: ' + senaryo);
}
"""

#: node bağlamına konacak sabitler (bağımlılık sırasıyla).
JS_CONSTS = ['LIQUID_SIGFIG_DENSITY', 'LIQUID_SIGFIG_TRANSPORT',
             'LIQUID_DEC_TEMPERATURE_K', 'LIQUID_DEC_MIXTURE_RATIO',
             'LIQUID_DEC_VELOCITY_MS']

JS_FUNCS = ['liquidSigFig', 'hrmaFmt', 'liquidWarnText', 'liquidCollectWarnings',
            '_liquidMotorName', 'exportLiquidExcel', 'createCylinderTrace',
            # antiVortexMm: T13 (2026-08-03) ile eklendi ve
            # createTankVisualization ondan ÖNCE gelmeli — girdap önleyicinin
            # birimini çözen yardımcı. Listede yoksa node
            # 'antiVortexMm is not defined' ile düşer.
            'antiVortexMm',
            'createRingTrace', 'createTankVisualization',
            'createAltitudePerformanceChart', 'displayCombustionEfficiency']


def _common_dictionary():
    """i18n_common.js EN bloğu — uyarı kodlarının kullanıcıya görünen metni."""
    source = COMMON_JS.read_text(encoding='utf-8')
    match = re.search(r'^\s{8}en:\s*\{$', source, re.M)
    assert match, 'i18n_common.js içinde en bloğu yok'
    body = source[match.end():]
    body = body[:body.index('\n        }')]
    return dict(re.findall(r"^\s*'([^']+)':\s*'(.*?)',?$", body, re.M))


def run_js(tmp_path, payload):
    """Şablondan kesilen JS'i node içinde koşturur, JSON çıktısını döndürür."""
    src = _template_source()
    epilogue = JS_EPILOGUE.replace(
        '__KUNYE_LITERAL__', js_template_literal('reportDiv.innerHTML = ', src))
    epilogue = epilogue.replace(
        '__ALTSISTEM_LITERAL__',
        js_template_literal('subsystemsDiv.innerHTML = ', src))
    epilogue = epilogue.replace(
        '__TANKKART_LITERAL__',
        js_template_literal('internalsCard.innerHTML = ', src))
    parts = [JS_PRELUDE]
    parts += [js_const(name, src) for name in JS_CONSTS]
    parts += [js_function(name, src) for name in JS_FUNCS]
    parts.append(epilogue)
    harness = tmp_path / 'kosum.js'
    harness.write_text('\n'.join(parts), encoding='utf-8')
    payload = dict(payload)
    payload.setdefault('sozluk', _common_dictionary())
    girdi = tmp_path / 'girdi.json'
    girdi.write_text(json.dumps(payload), encoding='utf-8')
    proc = subprocess.run([NODE, str(harness), str(girdi)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, 'node hatası:\n%s' % proc.stderr[-2000:]
    return json.loads(proc.stdout)


pytestmark = pytest.mark.skipif(NODE is None, reason='node yok')


# ===========================================================================
# Ortak veri
# ===========================================================================

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture(scope='module')
def cr(client):
    """GERÇEK sıvı çözücü yanıtı (denetimin koştuğu tasarım noktası)."""
    resp = client.post('/calculate_liquid', json=LIQUID_FORM)
    assert resp.status_code == 200, resp.data[:400]
    data = resp.get_json()
    assert data and not data.get('error'), data
    for key in ('thrust', 'burn_time', 'chamber_temperature',
                'optimal_mixture_ratio', 'cooling_system', 'input_warnings',
                'altitude_performance', 'performance_maps', 'propellant_tanks',
                'combustion_analysis', 'injection_system'):
        assert data.get(key) is not None, 'çözücü yanıtında %s yok' % key
    return data


# ===========================================================================
# T44 — sığmayan kanal sayısı Excel'e uyarısız geçmez
# ===========================================================================

def test_t44_onkosul_cozucu_sigmama_uyarisini_uretiyor(cr):
    """Kusurun ön koşulu: bu tasarım noktasında uyarı GERÇEKTEN çıkıyor."""
    kodlar = [w.get('code') for w in cr['input_warnings']]
    assert COOLING_FIT_CODE in kodlar, kodlar
    kayit = next(w for w in cr['input_warnings'] if w['code'] == COOLING_FIT_CODE)
    assert kayit['params']['n'] == 80
    # Geometrik üst sınır girilen sayıdan KÜÇÜK olmalı, yoksa uyarı anlamsız
    assert kayit['params']['n_geom'] < kayit['params']['n']
    assert cr['cooling_system']['cooling_channels'] == 80


def test_t44_geometry_sayfasi_kanal_satirinin_altina_uyariyi_yazar(tmp_path, cr):
    """'Cooling channels' satırının HEMEN ARDINDAN uyarı satırı gelir."""
    out = run_js(tmp_path, {'senaryo': 'excel', 'cr': cr})
    assert out['istek_sayisi'] == 1
    sayfalar = {s['name']: s['rows'] for s in out['govde']['sheets']}
    geom = sayfalar['Geometry']
    etiketler = [r[0] for r in geom]
    i = etiketler.index('Cooling channels')
    assert geom[i][1] == '80'
    assert i + 1 < len(geom), 'kanal satırından sonra not YOK (kusur geri geldi)'
    not_satiri = geom[i + 1]
    # Uyarı metni çözücünün parametrelerini taşımalı: girilen sayı ve
    # geometrik üst sınır teslimatta okunabilmeli.
    kayit = next(w for w in cr['input_warnings'] if w['code'] == COOLING_FIT_CODE)
    assert '80' in not_satiri[1]
    assert str(kayit['params']['n_geom']) in not_satiri[1]
    assert not_satiri[0], 'uyarı satırının önem etiketi boş'


def test_t44_uyari_sayfasi_ekrandaki_tum_uyarilari_tasir(tmp_path, cr):
    """'Warnings' sayfası, uyarı panelinin gösterdiği her kalemi içerir."""
    out = run_js(tmp_path, {'senaryo': 'excel', 'cr': cr})
    sayfalar = {s['name']: s['rows'] for s in out['govde']['sheets']}
    assert 'Warnings' in sayfalar, 'uyarı sayfası eklenmemiş'
    metin = ' | '.join(r[1] for r in sayfalar['Warnings'])
    assert len(sayfalar['Warnings']) >= len(cr['input_warnings'])
    assert '80' in metin
    # Ekranda görünen diğer girdi uyarıları da dosyada olmalı (seçici aktarım
    # "her şey yolunda" izlenimi verirdi).
    assert 'Throat diameter' in metin or 'throat' in metin.lower()


def test_t44_uyari_yokken_bos_sayfa_eklenmez(tmp_path, cr):
    """Uyarısız koşuda 'Warnings' sayfası HİÇ açılmaz (boş sayfa yok)."""
    temiz = dict(cr)
    temiz['input_warnings'] = []
    temiz['warnings'] = []
    temiz['validation'] = {}
    out = run_js(tmp_path, {'senaryo': 'excel', 'cr': temiz})
    adlar = [s['name'] for s in out['govde']['sheets']]
    assert 'Warnings' not in adlar, adlar
    sayfalar = {s['name']: s['rows'] for s in out['govde']['sheets']}
    etiketler = [r[0] for r in sayfalar['Geometry']]
    assert etiketler[-1] == 'Nozzle length (mm)', etiketler


# ===========================================================================
# T45 — anlamlı basamak
# ===========================================================================

def test_t45_onkosul_cozucu_degerleri_gercekten_uzun(cr):
    """Kusurun ön koşulu: bu alanlar çözücüden 10+ ondalıkla geliyor."""
    for key in ('chamber_temperature', 'optimal_mixture_ratio'):
        ondalik = repr(float(cr[key])).split('.')[-1]
        assert len(ondalik) >= 10, '%s zaten kısa: %r' % (key, cr[key])
    hiz = cr['injection_system']['fuel_injection_velocity']
    assert len(repr(float(hiz)).split('.')[-1]) >= 10, hiz


def test_t45_kunye_yuvarlanmis_deger_basar(tmp_path, cr):
    """Motor künyesinde 7+ ondalıklı ham sayı KALMAZ."""
    out = run_js(tmp_path, {'senaryo': 'kunye', 'cr': cr})
    html = out['html']
    uzun = re.findall(r'\d+\.\d{7,}', html)
    assert not uzun, 'künyede ham float: %s' % uzun[:5]
    # Değer kaybolmadı, yalnız yuvarlandı
    assert '3707 K' in html
    assert '(Optimal: 2.807)' in html


def test_t45_altsistem_kartlarinda_ham_float_kalmadi(tmp_path, cr):
    """Enjeksiyon hızları da yuvarlanır (Fuel Vel / Ox Vel)."""
    out = run_js(tmp_path, {'senaryo': 'altsistem', 'cr': cr})
    uzun = re.findall(r'\d+\.\d{7,}', out['html'])
    assert not uzun, 'alt sistem kartlarında ham float: %s' % uzun[:5]
    # Değer kaybolmadı: çözücünün hızı iki ondalıkla basılı
    for alan in ('fuel_injection_velocity', 'ox_injection_velocity'):
        beklenen = '%.2f m/s' % cr['injection_system'][alan]
        assert beklenen in out['html'], beklenen


def test_t45_tank_ic_yapi_kartinda_ham_float_kalmadi(tmp_path, cr):
    """Tarama sayfanın TAMAMINDA yapıldı: emniyet valfi çapı da ham geliyordu."""
    ham = (cr['propellant_tanks']['oxidizer_tank']['internal_structures']
             ['instrumentation']['relief_valve']['diameter'])
    assert len(repr(float(ham)).split('.')[-1]) >= 10, 'değer zaten kısa: %r' % ham
    out = run_js(tmp_path, {'senaryo': 'tank_karti',
                            'tanklar': cr['propellant_tanks']})
    uzun = re.findall(r'\d+\.\d{7,}', out['html'])
    assert not uzun, 'tank iç yapı kartında ham float: %s' % uzun[:5]
    assert '%.2f mm' % ham in out['html']


def test_t45_sigfig_buyuklukten_bagimsiz_calisir(tmp_path, cr):
    """Yoğunluk ve viskozite AYNI kuralla, kendi büyüklüğünde kısalır."""
    out = run_js(tmp_path, {
        'senaryo': 'basamak',
        'deger_yogunluk': 1141.1612390428575,
        'deger_viskozite': 0.00019466085657300348,
    })
    assert out['yogunluk'] == 1141.16
    assert out['viskozite'] == pytest.approx(0.0001947, rel=1e-12)
    # Yuvarlama sapması ölçülebilir biçimde küçük kalmalı: bu sayılar
    # çözücüye GİRDİ olarak da gidiyor.
    assert abs(out['yogunluk'] / 1141.1612390428575 - 1) < 1e-5
    assert abs(out['viskozite'] / 0.00019466085657300348 - 1) < 1e-3
    assert out['sifir'] == 0
    assert out['gecersiz'] is None      # NaN JSON'da null olur


# ===========================================================================
# T46 — 3B tank efsanesi
# ===========================================================================

def test_t46_tank_izleri_efsaneye_girer(tmp_path, cr):
    """19 izin 7'si efsanede görünür, 12 perde deliği gruba bağlanır."""
    out = run_js(tmp_path, {'senaryo': 'tank', 'tanklar': cr['propellant_tanks']})
    assert out['showlegend'] is True
    assert out['iz_sayisi'] == 19, out['iz_sayisi']
    # Kusurun imzası: DÜZELTME ÖNCESİ bu liste BOŞTU (hiçbir iz efsanede
    # görünmüyordu), bu yüzden efsane kutusu 0 px ölçülmüştü.
    assert len(out['efsanede']) == 7, out['efsanede']
    assert 'Oxidizer Tank' in out['efsanede']
    assert 'Fuel Tank' in out['efsanede']
    assert 'Baffle 1' in out['efsanede'] and 'Baffle 2' in out['efsanede']
    # Delikler efsanede satır AÇMAZ ama izleri kaybolmaz
    assert len(out['gizli']) == 12, out['gizli']
    assert all('Hole' in ad for ad in out['gizli'])


def test_t46_delikler_perdesinin_legendgroup_una_bagli(tmp_path, cr):
    """Perdeye tıklamak deliklerini de kapatabilmeli (aynı legendgroup)."""
    out = run_js(tmp_path, {'senaryo': 'tank', 'tanklar': cr['propellant_tanks']})
    gruplar = [g for g in out['gruplar'] if g]
    assert gruplar.count('Baffle 1') == 7      # halka + 6 delik
    assert gruplar.count('Baffle 2') == 7


def test_t46_kap_yuksekligi_layout_ile_ayni(tmp_path, cr):
    """Kap 400 px kalıp layout 600 px isterse grafiğin altı kırpılır."""
    out = run_js(tmp_path, {'senaryo': 'tank', 'tanklar': cr['propellant_tanks']})
    assert out['yukseklik'] == 600
    assert out['kap_yuksekligi'] == '600px'
    assert out['margin'] is not None


# ===========================================================================
# T62 — 'Total Impulse' sekmesi
# ===========================================================================

def test_t62_alt_sekme_adi_icerigini_anlatir(client):
    """Sekme motor alt sistemlerini gösteriyorsa adı da onu söylemeli."""
    html = client.get('/liquid').get_data(as_text=True)
    dugme = re.search(
        r"<button[^>]*showSubTab\('total_impulse'\)[^>]*>", html)
    assert dugme, 'total_impulse alt sekme düğmesi bulunamadı'
    assert 'liq.ui.engine_subsystems' in dugme.group(0), dugme.group(0)
    assert 'liq.ui.total_impulse' not in dugme.group(0), (
        'sekme hâlâ toplam impuls vaat ediyor: %s' % dugme.group(0))


def test_t62_toplam_impuls_kunyede_carpanlariyla_gosterilir(tmp_path, cr):
    """Toplam impuls artık GERÇEKTEN gösteriliyor: I_t = F·t_b."""
    out = run_js(tmp_path, {'senaryo': 'kunye', 'cr': cr})
    html = out['html']
    assert 'Total Impulse' in html
    beklenen = cr['thrust'] * cr['burn_time'] / 1000.0
    assert '%.1f' % beklenen in html, html[-600:]
    # Çarpanlar da yazılır ki hangi yanma süresiyle çarpıldığı görünsün
    assert '%.1f' % cr['burn_time'] in html


def test_t62_carpanlardan_biri_yoksa_satir_basilmaz(tmp_path, cr):
    """Yanma süresi gelmediyse toplam impuls UYDURULMAZ, satır düşer."""
    eksik = dict(cr)
    eksik['burn_time'] = None
    out = run_js(tmp_path, {'senaryo': 'kunye', 'cr': eksik})
    assert 'Total Impulse' not in out['html']


# ===========================================================================
# T63 — irtifa eğrisinin ikinci kopyası
# ===========================================================================

def test_t63_onkosul_iki_izgara_farkli(cr):
    """Kusurun ön koşulu: harita 13 EŞİT aralıklı, kanonik dizi 8 nokta."""
    harita = cr['performance_maps']['altitude_performance']['altitude_range']
    kanonik = [p['altitude'] for p in cr['altitude_performance']]
    assert len(harita) != len(kanonik)
    adimlar = {round(harita[i + 1] - harita[i], 6) for i in range(len(harita) - 1)}
    assert len(adimlar) == 1, 'harita zaten eşit aralıklı değil'
    kanonik_adim = {round(kanonik[i + 1] - kanonik[i], 6)
                    for i in range(len(kanonik) - 1)}
    assert len(kanonik_adim) > 1, 'kanonik dizi de eşit aralıklı olmuş'


def test_t63_harita_kanonik_seriyi_cizer(tmp_path, cr):
    """altChart artık altitude_plot ile AYNI noktalardan geçer."""
    out = run_js(tmp_path, {
        'senaryo': 'irtifa_haritasi', 'cr': cr,
        'harita': cr['performance_maps']['altitude_performance']})
    kanonik_km = [p['altitude'] / 1000.0 for p in cr['altitude_performance']]
    assert out['x'] == pytest.approx(kanonik_km)
    assert out['y_sayisi'] == len(kanonik_km)


def test_t63_baslik_diger_irtifa_grafiginden_ayri(tmp_path, cr):
    """İki grafik aynı adı taşımaz."""
    out = run_js(tmp_path, {
        'senaryo': 'irtifa_haritasi', 'cr': cr,
        'harita': cr['performance_maps']['altitude_performance']})
    src = _template_source()
    diger = js_function('_buildAltitudeFigure', src)
    assert "T('liq.msg.engine_performance_vs_altitude'" in diger
    assert out['baslik'] != 'Engine Performance vs Altitude', out['baslik']
    assert out['x_baslik']


def test_t63_tam_genlesme_irtifasi_isaretlenir(tmp_path, cr):
    """Grafiğin kendine ait işi: çözücünün bildirdiği optimum irtifa."""
    harita = cr['performance_maps']['altitude_performance']
    out = run_js(tmp_path, {'senaryo': 'irtifa_haritasi', 'cr': cr,
                            'harita': harita})
    beklenen_km = harita['optimal_altitude'] / 1000.0
    assert out['shapes'] == pytest.approx([beklenen_km])
    assert out['ann'] and '%.1f' % beklenen_km in out['ann'][0]


def test_t63_optimum_irtifa_yoksa_isaret_cizilmez(tmp_path, cr):
    """Alan gelmezse uydurma çizgi konmaz."""
    harita = dict(cr['performance_maps']['altitude_performance'])
    harita.pop('optimal_altitude', None)
    out = run_js(tmp_path, {'senaryo': 'irtifa_haritasi', 'cr': cr,
                            'harita': harita})
    assert out['shapes'] == []
    assert out['ann'] == []


def test_t63_kanonik_dizi_yoksa_haritaya_duser(tmp_path, cr):
    """Kanonik seri gelmezse grafik yine çizilir (yedek ızgara)."""
    harita = cr['performance_maps']['altitude_performance']
    out = run_js(tmp_path, {'senaryo': 'irtifa_haritasi', 'cr': {},
                            'harita': harita})
    assert out['x'] == pytest.approx([a / 1000.0 for a in harita['altitude_range']])


# ===========================================================================
# T65 — yanma verimi grafiği
# ===========================================================================

def test_t65_x_ekseni_basligi_var(tmp_path, cr):
    """combustionChart'ın x ekseni başlığı ``null`` değil."""
    analiz = cr['combustion_analysis']['combustion_analysis']
    out = run_js(tmp_path, {'senaryo': 'yanma', 'analiz': analiz})
    assert out['x_baslik'], 'x ekseni başlığı hâlâ boş'
    assert out['y_baslik']


def test_t65_ucuncu_cubuk_niteliksiz_overall_degil(tmp_path, cr):
    """Etiket ne olduğunu söyler; kayıp pastasının 'Overall'ı ile karışmaz."""
    analiz = cr['combustion_analysis']['combustion_analysis']
    out = run_js(tmp_path, {'senaryo': 'yanma', 'analiz': analiz})
    assert out['kategoriler'][:2] == ['Mixing', 'Combustion']
    ucuncu = out['kategoriler'][2]
    assert ucuncu != 'Overall', 'niteliksiz Overall etiketi geri geldi'
    assert 'Mixing' in ucuncu and 'Combustion' in ucuncu, ucuncu
    # Etiket gerçekten çarpımı anlatıyor mu: sayı da öyle olmalı
    beklenen = (analiz['mixing_efficiency']
                * analiz['combustion_efficiency'] / 100.0)
    assert out['degerler'][2] == pytest.approx(beklenen)


def test_t65_bu_verim_pastanin_genel_verimi_degil(cr):
    """İki 'Overall' FARKLI büyüklüktü; sayıyla kanıtla."""
    analiz = cr['combustion_analysis']['combustion_analysis']
    yanma_carpimi = (analiz['mixing_efficiency']
                     * analiz['combustion_efficiency'] / 100.0)
    genel = cr['efficiency_breakdown']['overall_efficiency']
    assert abs(yanma_carpimi - genel) > 1.0, (
        'iki büyüklük aynı çıktı (%.3f ↔ %.3f); testin dayanağı kalmadı'
        % (yanma_carpimi, genel))
