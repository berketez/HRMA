"""Grafik ve sunucu mesajı çeviri katmanı testleri (2026-07-19).

Kapsam — hrma/static/js/i18n_charts.js + hrma/static/js/plotly_dark.js

Neden bu mimari: grafik metinleri (başlık, eksen, seri adı, anotasyon,
hover şablonu) sunucuda ~130, panel JS dosyalarında ~120 ayrı noktada
üretiliyor. Hepsini tek tek çevirmek yerine TEK BOĞAZDAN çevriliyor:
plotly_dark.js zaten Plotly.newPlot / Plotly.react çağrılarını sarmalıyor;
oradaki translateFigure() i18n_charts.js sözlüğünü uyguluyor.

Testler şunları kilitler:
  1. SÖZDİZİM — iki dosya da `node --check` geçer (node yoksa atlanır).
  2. SÖZLEŞME — plotly_dark.js'te çeviri geçişi, kaynak saklama ve dil
     değişimi kancası kaynak düzeyinde duruyor.
  3. DAVRANIŞ — gerçek dosyalar node'da Plotly/DOM taklidiyle çalıştırılır:
       - TR'de metin çevrilir, EN'de metne DOKUNULMAZ
       - sözlükte olmayan metin AYNEN korunur (anahtar/boş asla)
       - koyu tema geçişi (paper_bgcolor, automargin) bozulmaz
       - TR -> EN dönüşünde İngilizce kaynak birebir geri gelir
       - dil değişince ekrandaki grafikler Plotly.react ile tazelenir
  4. SÖZLÜK — EN/TR anahtar kümeleri birebir, dosya içi yinelenen yok,
     TR değerleri EN kopyası değil.
  5. KAPSAM BEKÇİSİ — /calculate yanıtındaki GERÇEK figür metinlerinin
     en az %80'i çeviriden geçmeli. Backend yeni bir grafik metni eklerse
     ve sözlüğe girmezse bu test kırmızıya döner (sessiz İngilizce kalıntı
     birikmesin diye).
"""

import json
import pathlib
import re
import shutil
import subprocess
import warnings

import pytest

warnings.filterwarnings('ignore')

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
I18N_JS = STATIC_JS / 'i18n.js'
CHARTS_JS = STATIC_JS / 'i18n_charts.js'
PLOTLY_DARK_JS = STATIC_JS / 'plotly_dark.js'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# Kapsam bekçisinde "çevrilmesi gerekmeyen" sayılan sözcükler: teknik
# kısaltmalar ve sembol adları. test_i18n.py'deki TECH_TOKENS'tan BİLEREK
# ayrı tutuldu — orası çeviri kopyası avlar, burası kapsam ölçer.
# Yeni yanlış pozitif çıkarsa sözcüğü BURAYA ekle, eşiği düşürme.
NON_TRANSLATABLE_WORDS = {
    'isp', 'htpb', 'apcp', 'lox', 'nasa', 'cea', 'nist', 'bates', 'nhne',
    'hrma', 'cad', 'stl', 'step', 'dxf', 'pdf', 'csv', 'json', 'cfd', 'rpa',
    'isa', 'bar', 'deg', 'sub', 'sup', 'extra', 'div', 'span', 'uzaytek',
    'mach', 'bartz', 'lame', 'shigley', 'monte', 'carlo', 'dittus',
    'boelter', 'spearman', 'mawp', 'tank', 'wall', 'coolant', 'cold', 'hot',
}

WORD_RE = re.compile(r'[A-Za-z]{3,}')


# ---------------------------------------------------------------------------
# Node koşum düzeneği
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');

const ROOT = process.argv[2];
const TEXTS_FILE = process.argv[3] || '';

/* ---- Asgari DOM taklidi (plotly_dark.js yalnız şunları kullanıyor) ---- */
function makeDoc(plotNodes) {
    const listeners = {};
    return {
        readyState: 'complete',
        documentElement: { setAttribute() {}, appendChild() {} },
        head: { appendChild() {} },
        createElement: () => ({ setAttribute() {}, appendChild() {}, style: {} }),
        getElementById: () => null,
        querySelector: (sel) => (sel.indexOf('i18n_charts.js') >= 0 ? {} : null),
        querySelectorAll: (sel) => (sel === '.js-plotly-plot' ? plotNodes : []),
        addEventListener: (name, fn) => { (listeners[name] = listeners[name] || []).push(fn); },
        dispatchEvent: (ev) => {
            (listeners[ev.type] || []).forEach((fn) => fn(ev));
            return true;
        },
        __listeners: listeners,
    };
}

function boot(plotNodes) {
    const calls = [];
    const sandbox = {
        console, setTimeout, clearTimeout, setInterval, clearInterval,
        JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error,
    };
    sandbox.window = sandbox;
    sandbox.self = sandbox;
    sandbox.document = makeDoc(plotNodes || []);
    sandbox.localStorage = null;                 // depolama yok: varsayılan dil
    sandbox.CustomEvent = function (type, init) {
        this.type = type;
        this.detail = (init && init.detail) || null;
    };
    sandbox.Plotly = {
        newPlot(el, data, layout, config) { calls.push({ fn: 'newPlot', el, data, layout }); },
        react(el, data, layout, config) { calls.push({ fn: 'react', el, data, layout }); },
    };
    vm.createContext(sandbox);
    for (const f of ['i18n.js', 'i18n_charts.js', 'plotly_dark.js']) {
        vm.runInContext(fs.readFileSync(ROOT + '/' + f, 'utf8'), sandbox, { filename: f });
    }
    return { sandbox, calls };
}

function figure() {
    return {
        data: [
            { name: 'Thrust', type: 'scatter',
              hovertemplate: 'Time: %{x:.1f} s<br>Altitude: %{y:.2f} km' },
            { name: 'Totally Unknown Series', type: 'scatter' },
        ],
        layout: {
            title: { text: 'Thrust & Chamber Pressure vs Time' },
            xaxis: { title: 'Time (s)' },
            yaxis: { title: { text: 'Thrust (N)' } },
            annotations: [{ text: 'Operating Point' }, { text: 'No Such Annotation' }],
        },
    };
}

const out = {};

/* ---- 1. TR çevirisi ---- */
{
    const { sandbox, calls } = boot();
    sandbox.I18N.setLang('tr');
    const f = figure();
    sandbox.Plotly.newPlot('div', f.data, f.layout);
    const c = calls[calls.length - 1];
    out.tr = {
        title: c.layout.title.text,
        xaxis: typeof c.layout.xaxis.title === 'string'
            ? c.layout.xaxis.title : c.layout.xaxis.title.text,
        yaxis: c.layout.yaxis.title.text,
        traceName: c.data[0].name,
        unknownTrace: c.data[1].name,
        hover: c.data[0].hovertemplate,
        annotation: c.layout.annotations[0].text,
        unknownAnnotation: c.layout.annotations[1].text,
        paperBg: c.layout.paper_bgcolor,
        automargin: c.layout.xaxis.automargin,
    };
}

/* ---- 2. EN dokunulmazlığı ---- */
{
    const { sandbox, calls } = boot();
    sandbox.I18N.setLang('en');
    const f = figure();
    sandbox.Plotly.newPlot('div', f.data, f.layout);
    const c = calls[calls.length - 1];
    out.en = {
        title: c.layout.title.text,
        traceName: c.data[0].name,
        hover: c.data[0].hovertemplate,
        paperBg: c.layout.paper_bgcolor,
    };
}

/* ---- 3. Dil gidiş-dönüşü: TR -> EN kaynağı bozmamalı ---- */
{
    const { sandbox, calls } = boot();
    const f = figure();
    sandbox.I18N.setLang('tr');
    sandbox.Plotly.newPlot('div', f.data, f.layout);
    sandbox.I18N.setLang('en');
    sandbox.Plotly.react('div', f.data, f.layout);
    sandbox.I18N.setLang('tr');
    sandbox.Plotly.react('div', f.data, f.layout);
    sandbox.I18N.setLang('en');
    sandbox.Plotly.react('div', f.data, f.layout);
    const c = calls[calls.length - 1];
    out.roundTrip = {
        title: c.layout.title.text,
        traceName: c.data[0].name,
        hover: c.data[0].hovertemplate,
    };
}

/* ---- 4. Dil değişince çizili grafikler tazelenir ---- */
{
    const f = figure();
    const gd = { _fullLayout: {}, data: f.data, layout: f.layout };
    const { sandbox, calls } = boot([gd]);
    sandbox.Plotly.newPlot(gd, f.data, f.layout);
    const before = calls.length;
    sandbox.I18N.setLang('tr');
    out.redraw = { pending: true, before };
    setTimeout(() => {
        const after = calls.slice(before);
        out.redraw = {
            reactCalls: after.filter((c) => c.fn === 'react').length,
            title: gd.layout.title.text,
        };
        finish();
    }, 30);
}

/* ---- 5. serverText sözleşmesi ---- */
{
    const { sandbox } = boot();
    sandbox.I18N.setLang('tr');
    out.serverTr = {
        exact: sandbox.I18N.serverText('Flash boiling risk detected'),
        pattern: sandbox.I18N.serverText('Thrust must be positive, given: -5'),
        unknown: sandbox.I18N.serverText('No dictionary entry for this one'),
        list: sandbox.I18N.serverTexts(['Improve cooling system', 'Nope nope nope']),
        nonString: sandbox.I18N.serverText(42),
    };
    sandbox.I18N.setLang('en');
    out.serverEn = { exact: sandbox.I18N.serverText('Flash boiling risk detected') };
}

/* ---- 6. Metin listesi çevirisi (kapsam bekçisi için) ----
   Aynı liste HEM chartText HEM serverText'ten geçirilir: figür metinleri
   birinciyi, API uyarıları ikinciyi kullanır ve iki boru hattının kural
   tabloları ayrıdır (PATTERNS vs MSG_PATTERNS). */
if (TEXTS_FILE) {
    const { sandbox } = boot();
    sandbox.I18N.setLang('tr');
    const texts = JSON.parse(fs.readFileSync(TEXTS_FILE, 'utf8'));
    out.translated = texts.map((s) => sandbox.I18N.chartText(s));
    out.translatedServer = texts.map((s) => sandbox.I18N.serverText(s));
}

function finish() {
    process.stdout.write(JSON.stringify(out));
}
"""


@pytest.fixture(scope='module')
def harness(tmp_path_factory):
    path = tmp_path_factory.mktemp('i18n_charts') / 'harness.js'
    path.write_text(HARNESS, encoding='utf-8')
    return path


def run_harness(harness_path, texts=None, tmp_path=None):
    args = [NODE, str(harness_path), str(STATIC_JS)]
    if texts is not None:
        texts_file = tmp_path / 'texts.json'
        texts_file.write_text(json.dumps(texts), encoding='utf-8')
        args.append(str(texts_file))
    proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'node düzeneği düştü:\n%s' % proc.stderr
    assert proc.stdout.strip(), 'node düzeneği çıktı üretmedi:\n%s' % proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture(scope='module')
def result(harness):
    if NODE is None:
        pytest.skip('node kurulu değil')
    return run_harness(harness)


# ---------------------------------------------------------------------------
# 1. Sözdizimi
# ---------------------------------------------------------------------------
@needs_node
@pytest.mark.parametrize('path', [CHARTS_JS, PLOTLY_DARK_JS], ids=lambda p: p.name)
def test_syntax_ok(path):
    proc = subprocess.run([NODE, '--check', str(path)], capture_output=True, text=True)
    assert proc.returncode == 0, '%s sözdizimi hatası:\n%s' % (path.name, proc.stderr)


# ---------------------------------------------------------------------------
# 2. Kaynak düzeyi sözleşme
# ---------------------------------------------------------------------------
def test_plotly_dark_ceviri_gecisini_tasiyor():
    """Çeviri geçişi sarmalayıcının İÇİNDE olmalı; yoksa hiçbir grafik çevrilmez."""
    src = PLOTLY_DARK_JS.read_text(encoding='utf-8')
    for gerekli in ('function translateFigure', 'translateFigure(data, layout);',
                    'chartText', '__hrmaEnSource', 'redrawAllPlots',
                    'js-plotly-plot', 'hrma:langchange'):
        assert gerekli in src, 'plotly_dark.js dil katmanında eksik: %s' % gerekli


def test_plotly_dark_koyu_tema_savunmalari_duruyor():
    """Dil katmanı eklenirken koyu tema geçişi kaybolmamalı (regresyon kalkanı)."""
    src = PLOTLY_DARK_JS.read_text(encoding='utf-8')
    for gerekli in ('applyDarkLayout(layout)', 'maybeBottomLegend',
                    'maybeUnifiedHover', 'automargin', 'colorway'):
        assert gerekli in src, 'plotly_dark.js koyu tema geçişinde eksik: %s' % gerekli


def test_charts_js_register_sozlesmesine_uyuyor():
    src = CHARTS_JS.read_text(encoding='utf-8')
    assert 'I18N.register(' in src, 'i18n_charts.js sözlüğü hiç kaydetmiyor'
    assert '__I18N_PENDING' in src, 'i18n_charts.js yükleme sırası korumasız'
    for member in ('chartText', 'serverText', 'serverTexts'):
        assert member in src, 'i18n_charts.js dışa açılan %s yardımcısını taşımıyor' % member


# ---------------------------------------------------------------------------
# 3. Sözlük bütünlüğü (bu dosya kendi kendine yeter; test_i18n.py ile örtüşür)
# ---------------------------------------------------------------------------
PAIR_RE = re.compile(r"^\s*'((?:[^'\\]|\\.)*)'\s*:\s*'((?:[^'\\]|\\.)*)'\s*,?\s*$", re.M)


def _lang_block(source, lang):
    match = re.search(r'\b%s\s*:\s*\{' % lang, source)
    assert match, "i18n_charts.js içinde '%s' sözlük bloğu yok" % lang
    idx, depth = match.end() - 1, 0
    quote, escaped = None, False
    while idx < len(source):
        ch = source[idx]
        if quote:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in '\'"`':
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return source[match.end():idx]
        idx += 1
    raise AssertionError("'%s' bloğu kapanmıyor" % lang)


@pytest.fixture(scope='module')
def dicts():
    src = CHARTS_JS.read_text(encoding='utf-8')
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return {lang: PAIR_RE.findall(_lang_block(src, lang)) for lang in ('en', 'tr')}


def test_sozluk_anahtarlari_birebir(dicts):
    en_keys = [k for k, _ in dicts['en']]
    tr_keys = [k for k, _ in dicts['tr']]
    assert en_keys, 'EN sözlüğü boş ayrıştırıldı (kalıp bozulmuş olabilir)'
    dup_en = sorted({k for k in en_keys if en_keys.count(k) > 1})
    dup_tr = sorted({k for k in tr_keys if tr_keys.count(k) > 1})
    assert not dup_en, 'EN sözlüğünde yinelenen anahtar: %s' % dup_en
    assert not dup_tr, 'TR sözlüğünde yinelenen anahtar: %s' % dup_tr
    assert not set(en_keys) - set(tr_keys), \
        'TR çevirisi eksik: %s' % sorted(set(en_keys) - set(tr_keys))[:20]
    assert not set(tr_keys) - set(en_keys), \
        "TR'de olup EN'de olmayan: %s" % sorted(set(tr_keys) - set(en_keys))[:20]


def test_en_degerleri_anahtarin_kendisi(dicts):
    """Anahtar = İngilizce metnin kendisi sözleşmesi.

    EN değeri anahtardan farklı olursa `chartText` İngilizce dilde metni
    sessizce başka bir şeye çevirir — sözleşme bu değil.
    """
    sapan = [k for k, v in dicts['en'] if k != v]
    assert not sapan, 'EN değeri anahtardan farklı: %s' % sapan[:20]


def test_tr_degerleri_kopya_degil(dicts):
    """TR değeri EN kopyası olmamalı; kopya = çevrilmemiş giriş."""
    en = dict(dicts['en'])
    kopya = [k for k, v in dicts['tr'] if en.get(k) == v]
    assert not kopya, 'TR değeri EN ile birebir aynı: %s' % kopya[:20]


def test_tr_degerlerinde_turkce_karakter_kaybi_yok(dicts):
    """'Basinc' gibi ASCII'ye kaçmış Türkçe kök kalmamalı."""
    kokler = re.compile(
        r'^(basinc|sicaklik|yogunluk|kutle|kalinlik|guvenlik|agirlik|genislik|'
        r'yukseklik|olcu|cozum|sonuc|baslangic|bitis|cikti|cikis|giris|deger|'
        r'katsayi|dogru|tasarim|akis|sogutma|yakit|enjektor|lule|bogaz|icin|'
        r'dusuk|yuksek|buyuk|kucuk|gorunum|ozgul|uyari|ozet|yaricap|hiz|'
        r'sinir|sekil|cok|tum|acik|sayi|kati|sivi)')
    kacislar = []
    for key, value in dicts['tr']:
        for word in re.findall(r'[0-9A-Za-zÇĞİÖŞÜçğıöşü]+', value):
            if len(word) > 1 and word.isupper():
                continue                      # 'YAKIT' meşru büyük harf
            if kokler.match(word.lower().replace('̇', '')):
                kacislar.append('%s = %r (şüpheli: %r)' % (key, value, word))
    assert not kacislar, 'Türkçe karakter kaybı:\n  ' + '\n  '.join(kacislar)


def test_sozlukte_emoji_yok(dicts):
    emoji = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF]')
    bulunan = [(k, v) for lang in ('en', 'tr') for k, v in dicts[lang] if emoji.search(v)]
    assert not bulunan, 'Sözlükte emoji: %s' % bulunan[:10]


# ---------------------------------------------------------------------------
# 4. Davranış (node + Plotly/DOM taklidi)
# ---------------------------------------------------------------------------
def test_tr_dilinde_grafik_metinleri_cevriliyor(result):
    tr = result['tr']
    assert tr['title'] == 'İtki ve Oda Basıncı - Zaman'
    assert tr['xaxis'] == 'Zaman (s)'
    assert tr['yaxis'] == 'İtki (N)'
    assert tr['traceName'] == 'İtki'
    assert tr['annotation'] == 'Çalışma Noktası'
    assert tr['hover'] == 'Zaman: %{x:.1f} s<br>İrtifa: %{y:.2f} km'


def test_sozlukte_olmayan_metin_aynen_kaliyor(result):
    """Eksik çeviri boş kutu veya anahtar göstermemeli — İngilizce kalmalı."""
    assert result['tr']['unknownTrace'] == 'Totally Unknown Series'
    assert result['tr']['unknownAnnotation'] == 'No Such Annotation'


def test_en_dilinde_metne_dokunulmuyor(result):
    en = result['en']
    assert en['title'] == 'Thrust & Chamber Pressure vs Time'
    assert en['traceName'] == 'Thrust'
    assert en['hover'] == 'Time: %{x:.1f} s<br>Altitude: %{y:.2f} km'


def test_koyu_tema_gecisi_bozulmadi(result):
    """Çeviri katmanı eklenince tema geçişi susmamalı."""
    assert result['tr']['paperBg'] == 'rgba(0,0,0,0)'
    assert result['en']['paperBg'] == 'rgba(0,0,0,0)'
    assert result['tr']['automargin'] is True


def test_dil_gidis_donusu_ingilizce_kaynagi_bozmuyor(result):
    """TR -> EN -> TR -> EN sonunda metin İNGİLİZCE aslına dönmeli.

    Çeviri saklanan İngilizce kaynaktan yapılmazsa ikinci turda Türkçe
    metin anahtar sanılır ve metin kilitlenir; bu test onu yakalar.
    """
    rt = result['roundTrip']
    assert rt['title'] == 'Thrust & Chamber Pressure vs Time'
    assert rt['traceName'] == 'Thrust'
    assert rt['hover'] == 'Time: %{x:.1f} s<br>Altitude: %{y:.2f} km'


def test_dil_degisince_cizili_grafikler_tazeleniyor(result):
    redraw = result['redraw']
    assert not redraw.get('pending'), 'yeniden çizim hiç tetiklenmedi'
    assert redraw['reactCalls'] >= 1, \
        'dil değişince Plotly.react çağrılmadı — çizili grafikler İngilizce kalır'
    assert redraw['title'] == 'İtki ve Oda Basıncı - Zaman'


# ---------------------------------------------------------------------------
# 5. serverText sözleşmesi
# ---------------------------------------------------------------------------
def test_server_text_birebir_ve_desenli_cevirir(result):
    s = result['serverTr']
    assert s['exact'] == 'Ani kaynama riski tespit edildi'
    assert s['pattern'] == 'İtki pozitif olmalı, girilen: -5'


def test_server_text_bilinmeyen_mesaji_aynen_dondurur(result):
    assert result['serverTr']['unknown'] == 'No dictionary entry for this one'
    assert result['serverTr']['nonString'] == 42


def test_server_texts_dizi_isler(result):
    liste = result['serverTr']['list']
    assert liste == ['Soğutma sistemini iyileştirin', 'Nope nope nope']


def test_server_text_en_dilinde_dokunmuyor(result):
    assert result['serverEn']['exact'] == 'Flash boiling risk detected'


# ---------------------------------------------------------------------------
# 6. Kapsam bekçisi — GERÇEK backend figürleri
# ---------------------------------------------------------------------------
HYBRID_PAYLOAD = {
    'motor_name': 'i18n-coverage', 'thrust': 1000, 'burn_time': 10,
    'chamber_pressure': 30, 'of_ratio': 6, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'expansion_ratio': 5,
}

# Uygulama yalnız geri döngü Host başlığına yanıt verir (DNS-rebinding kapısı)
CALC_HEADERS = {'Host': '127.0.0.1:8080'}

#: Katı ve sıvı uçların yükü ELDE UYDURULMAZ — depodaki gerçek örnek
#: projelerden okunur. Uydurma bir yük ya 422 alır (kapı reddeder) ya da
#: gerçekte hiç üretilmeyen bir figür kümesi çıkarır; ikisi de kapsamı
#: yanlış ölçer. tests/test_example_projects.py aynı dosyaları kullanıyor.
EXAMPLES_DIR = REPO_ROOT / 'examples'
EXAMPLE_NAMES = {
    '/calculate_solid': 'Example Solid KNDX BATES 75mm',
    '/calculate_liquid': 'Example Liquid LOX-RP1 25kN',
}


def _example_payload(endpoint):
    path = EXAMPLES_DIR / (EXAMPLE_NAMES[endpoint] + '.hrma')
    data = json.loads(path.read_text(encoding='utf-8'))
    return dict(data['inputs']['fields'])


#: Kapsam bekçisinin taradığı hesap uçları. Üçü de taranır: sözlük yalnız
#: hibrit yolda denendiği sürece katı/sıvı sayfalarına özgü figürler
#: (Kn eğrisi, rejeneratif soğutma panosu, grain regresyonu) sessizce
#: İngilizce kalıyordu — ÖLÇÜLDÜ, 2026-08-03.
COVERAGE_ENDPOINTS = ('/calculate', '/calculate_solid', '/calculate_liquid')

#: Çeviri kapsamı alt sınırı. DÜŞÜRMEK YASAK — düşük çıkarsa eksik metin
#: i18n_charts.js sözlüğüne (sabit metin) veya PATTERNS/MSG_PATTERNS
#: tablosuna (sayı taşıyan metin) eklenir.
COVERAGE_MIN = 0.95

#: Düz metin uyarı/öneri listelerini taşıyan yanıt alanları. Bunlar
#: {code, params} sözleşmesine geçmemiş uçlardan gelir ve istemcide
#: I18N.serverText'ten geçer (analysis_dock.js::warnText, app.js::SRV).
WARNING_FIELDS = ('warnings', 'recommendations', 'safety_notes',
                  'safety_devices_required', 'notes')


def _axis_title(node, sink):
    if not isinstance(node, dict):
        return
    title = node.get('title')
    if isinstance(title, str):
        sink.add(title)
    elif isinstance(title, dict) and isinstance(title.get('text'), str):
        sink.add(title['text'])


def _collect_figure_texts(figure, sink):
    if isinstance(figure, str):
        try:
            figure = json.loads(figure)
        except ValueError:
            return
    if not isinstance(figure, dict):
        return
    layout = figure.get('layout') or {}
    if isinstance(layout, dict):
        _axis_title(layout, sink)
        for key, value in layout.items():
            if re.match(r'^[xyz]axis\d*$', key):
                _axis_title(value, sink)
        for annotation in (layout.get('annotations') or []):
            if isinstance(annotation, dict) and isinstance(annotation.get('text'), str):
                sink.add(annotation['text'])
    for trace in (figure.get('data') or []):
        if not isinstance(trace, dict):
            continue
        for field in ('name', 'hovertemplate'):
            if isinstance(trace.get(field), str):
                sink.add(trace[field])


def _walk(node, sink, depth=0):
    if depth > 8:
        return
    if isinstance(node, dict):
        if 'data' in node and 'layout' in node:
            _collect_figure_texts(node, sink)
            return
        for value in node.values():
            _walk(value, sink, depth + 1)
    elif isinstance(node, list):
        for value in node[:60]:
            _walk(value, sink, depth + 1)
    elif isinstance(node, str) and node.strip().startswith('{') \
            and '"layout"' in node and '"data"' in node:
        _collect_figure_texts(node, sink)


def _collect_warning_texts(node, sink, depth=0):
    """Düz METİN uyarı/öneri satırlarını toplar.

    {code, params} sözlüğü olan uyarılar ATLANIR: onlar I18N.tf ile
    anahtardan çevriliyor ve kapsamları test_warning_contract.py'nin işi.
    Burada aranan, hâlâ düz İngilizce dize döndüren uçlar.
    """
    if depth > 10:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key in WARNING_FIELDS and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        sink.add(item)
            _collect_warning_texts(value, sink, depth + 1)
    elif isinstance(node, list):
        for value in node[:80]:
            _collect_warning_texts(value, sink, depth + 1)


def _translatable(text):
    """Çevrilmesi BEKLENEN metin mi? (salt sayı/sembol/teknik jeton değilse)"""
    stripped = re.sub(r'<[^>]*>', ' ', text)
    stripped = re.sub(r'%\{[^}]*\}', ' ', stripped)
    words = [w for w in WORD_RE.findall(stripped) if w.lower() not in NON_TRANSLATABLE_WORDS]
    return bool(words)


def _normalize(texts):
    out = {re.sub(r'\s+', ' ', t).strip() for t in texts}
    out.discard('')
    return out


@pytest.fixture(scope='module')
def hesap_yanitlari():
    """Üç hesap ucunu BİR KEZ koşturup figür + uyarı metinlerini toplar.

    Modül kapsamlı: sıvı uç ~4 s, hibrit ~2 s sürüyor; her testte yeniden
    koşturmak bu dosyanın süresini üçe katlardı.
    """
    from hrma.app import app

    client = app.test_client()
    toplanan = {}
    for endpoint in COVERAGE_ENDPOINTS:
        payload = (HYBRID_PAYLOAD if endpoint == '/calculate'
                   else _example_payload(endpoint))
        response = client.post(endpoint, json=payload, headers=CALC_HEADERS)
        figurler, uyarilar = set(), set()
        if response.status_code == 200:
            body = response.get_json()
            _walk(body, figurler)
            _collect_warning_texts(body, uyarilar)
        toplanan[endpoint] = {
            'status': response.status_code,
            'figur': _normalize(figurler),
            'uyari': _normalize(uyarilar),
        }
    return toplanan


def _kapsam_olc(harness, tmp_path, metinler, alan):
    """(oran, eksik_liste) — metinleri node düzeneğinden geçirip ölçer."""
    beklenen = sorted(t for t in metinler if _translatable(t))
    if not beklenen:
        return None, []
    sonuc = run_harness(harness, texts=beklenen, tmp_path=tmp_path)
    ceviriler = sonuc['translated' if alan == 'figur' else 'translatedServer']
    eksik = [t for t, c in zip(beklenen, ceviriler) if t == c]
    return 1.0 - len(eksik) / float(len(beklenen)), eksik


@needs_node
@pytest.mark.parametrize('endpoint', COVERAGE_ENDPOINTS)
def test_backend_figur_metinleri_kapsam_bekcisi(harness, tmp_path, hesap_yanitlari,
                                                endpoint):
    """Her hesap ucunun figür metinlerinin >= %95'i çeviriden geçmeli.

    Backend yeni bir grafik metni ekler ve sözlüğe girmezse bu test kırılır.
    DÜŞÜK ÇIKARSA EŞİĞİ DÜŞÜRME — eksik metinler assert iletisinde tek tek
    listeleniyor; sabit metinler i18n_charts.js sözlüğüne, sayı taşıyanlar
    PATTERNS tablosuna eklenir.
    """
    yanit = hesap_yanitlari[endpoint]
    assert yanit['status'] == 200, (
        '%s hesap ucu düştü (HTTP %s) — bu bir ÇEVİRİ hatası değil, uç '
        'bozuk. Önce ucu onarın; kapsam ölçülemedi.'
        % (endpoint, yanit['status'])
    )
    metinler = yanit['figur']
    assert len(metinler) >= 20, (
        '%s figürlerinden yeterli metin toplanamadı (%d) — toplayıcı bozulmuş '
        'olabilir' % (endpoint, len(metinler))
    )

    oran, eksik = _kapsam_olc(harness, tmp_path, metinler, 'figur')
    assert oran is not None, \
        '%s: çevrilebilir metin bulunamadı — toplayıcı bozulmuş olabilir' % endpoint
    assert oran >= COVERAGE_MIN, (
        '%s grafik çeviri kapsamı %%%.1f (>= %%%.0f olmalı). Çevrilemeyen %d '
        'metin:\n  %s'
        % (endpoint, 100 * oran, 100 * COVERAGE_MIN, len(eksik),
           '\n  '.join(eksik))
    )


@needs_node
def test_backend_uyari_metinleri_kapsam_bekcisi(harness, tmp_path, hesap_yanitlari):
    """Düz metin API uyarılarının >= %95'i serverText'ten geçmeli.

    Bu bekçi 2026-08-03'te eklendi: serverText Temmuz'da yazılmıştı ama
    hiçbir yerden ÇAĞRILMIYORDU, dolayısıyla MSG_PATTERNS tablosu ölü
    koddu ve düz-İngilizce uyarılar TR modda İngilizce kalıyordu. Kapsam
    ölçülmediği sürece aynı boşluk sessizce geri gelebilir.
    """
    tumu, dusen = set(), []
    for endpoint in COVERAGE_ENDPOINTS:
        yanit = hesap_yanitlari[endpoint]
        if yanit['status'] != 200:
            dusen.append('%s (HTTP %s)' % (endpoint, yanit['status']))
            continue
        tumu |= yanit['uyari']
    assert not dusen, (
        'Hesap uçları düştü, uyarı kapsamı ölçülemedi: %s — bu bir ÇEVİRİ '
        'hatası değil.' % ', '.join(dusen)
    )
    if not tumu:
        pytest.skip('bu koşuda düz metin uyarı üretilmedi')

    oran, eksik = _kapsam_olc(harness, tmp_path, tumu, 'uyari')
    if oran is None:
        pytest.skip('toplanan uyarıların hiçbiri çevrilebilir metin değil')
    assert oran >= COVERAGE_MIN, (
        'API uyarı çeviri kapsamı %%%.1f (>= %%%.0f olmalı). Çevrilemeyen %d '
        'mesaj:\n  %s'
        % (100 * oran, 100 * COVERAGE_MIN, len(eksik), '\n  '.join(eksik))
    )
