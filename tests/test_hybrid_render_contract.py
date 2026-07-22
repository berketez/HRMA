"""
Hibrit sayfa render sözleşmesi (W-HYBRID dalgası, 2026-07-19).

Neden var: /calculate her hesapta plots.altitude_performance,
plots.mass_fractions, plots.thrust_altitude, plots.combustion_analysis ve
plots.realtime_dashboard üretiyordu; hibrit sayfası (advanced.html + app.js)
bunların HİÇBİRİNİ çizmiyordu — üretilip atılan ölü yük, üstelik irtifa
performansı katı ve sıvı sayfalarda varken hibritte yoktu. Aynı şekilde
nozzle_angles / grain_design / design_summary blokları yanıtta geliyor ama
tabloya çıkmıyordu.

Kapsam:
  1. app.js ve advanced.html satır içi script'leri `node --check` ile geçer.
  2. Beş opsiyonel grafik anahtarının hepsi displayPlots içinde işlenir.
  3. Her grafiğin paneli ve çizim div'i advanced.html'de tanımlıdır,
     panel display:none başlar (veri yoksa boş kutu kalmasın).
  4. nozzle_angles / grain_design / design_summary displayDesignReport
     zincirinde geçer.
  5. renderOptionalPlot() izole çalıştırılır: boş yükte paneli GİZLER,
     dolu yükte AÇAR ve Plotly.newPlot çağırır.
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
APP_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'app.js'
ADVANCED_HTML = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'

NODE = shutil.which('node')

# Backend'in /calculate yanıtında ürettiği opsiyonel grafik anahtarları ve
# bunların advanced.html'deki panel / çizim div eşlemesi (tek kaynak).
OPTIONAL_PLOTS = {
    'altitude_performance': ('altitudePerformancePanel', 'altitude_performance_plot'),
    'thrust_altitude': ('thrustAltitudePanel', 'thrust_altitude_plot'),
    'mass_fractions': ('massFractionsPanel', 'mass_fractions_plot'),
    'combustion_analysis': ('combustionAnalysisPanel', 'combustion_analysis_plot'),
    'realtime_dashboard': ('realtimeDashboardPanel', 'realtime_dashboard_plot'),
}

# Yanıtta gelen ama hibritte hiç kullanılmayan tasarım blokları
DESIGN_BLOCKS = ('nozzle_angles', 'grain_design', 'design_summary')

INLINE_SCRIPT_RE = re.compile(
    r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)


def _read(path):
    return path.read_text(encoding='utf-8')


def _display_plots_body(source):
    """displayPlots gövdesini kaba ama yeterli biçimde ayıklar."""
    start = source.index('function displayPlots(')
    tail = source[start:]
    end = tail.index('\n}\n')
    return tail[:end]


def _design_report_body(source):
    start = source.index('function displayDesignReport(')
    tail = source[start:]
    end = tail.index('\n}\n')
    return tail[:end]


def _node_check(js_text, tmp_path, name):
    target = tmp_path / name
    target.write_text(js_text, encoding='utf-8')
    proc = subprocess.run([NODE, '--check', str(target)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f'{name} sözdizimi hatası:\n{proc.stderr}'


# --------------------------------------------------------------------------
# 1. Sözdizimi
# --------------------------------------------------------------------------

@pytest.mark.skipif(NODE is None, reason='node bulunamadı')
def test_app_js_syntax():
    proc = subprocess.run([NODE, '--check', str(APP_JS)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f'app.js sözdizimi hatası:\n{proc.stderr}'


@pytest.mark.skipif(NODE is None, reason='node bulunamadı')
def test_advanced_inline_scripts_syntax(tmp_path):
    html = _read(ADVANCED_HTML)
    blocks = INLINE_SCRIPT_RE.findall(html)
    assert blocks, 'advanced.html içinde satır içi script bulunamadı'

    checked = 0
    for i, block in enumerate(blocks):
        if not block.strip():
            continue
        # Jinja ifadesi taşıyan blok node ile derlenemez; atlanır.
        if '{{' in block or '{%' in block:
            continue
        _node_check(block, tmp_path, f'inline_{i}.js')
        checked += 1

    assert checked >= 1, 'Denetlenebilir satır içi script bulunamadı'


# --------------------------------------------------------------------------
# 2-3. Beş grafik: displayPlots'ta işleniyor + panel/div şablonda var
# --------------------------------------------------------------------------

def test_all_optional_plot_keys_handled_in_display_plots():
    body = _display_plots_body(_read(APP_JS))
    for key, (panel_id, div_id) in OPTIONAL_PLOTS.items():
        assert f'plots.{key}' in body, (
            f'plots.{key} displayPlots içinde işlenmiyor (ölü yük geri döndü)')
        assert panel_id in body, f'{panel_id} displayPlots içinde geçmiyor'
        assert div_id in body, f'{div_id} displayPlots içinde geçmiyor'


def test_optional_plot_containers_exist_and_start_hidden():
    html = _read(ADVANCED_HTML)
    for key, (panel_id, div_id) in OPTIONAL_PLOTS.items():
        panel_match = re.search(
            r'<div[^>]*id="%s"[^>]*>' % re.escape(panel_id), html)
        assert panel_match, f'{panel_id} paneli advanced.html içinde yok'
        panel_tag = panel_match.group(0)
        assert 'display: none' in panel_tag or 'display:none' in panel_tag, (
            f'{panel_id} display:none ile başlamıyor — veri gelmezse boş kutu kalır')

        div_match = re.search(
            r'<div[^>]*id="%s"[^>]*>' % re.escape(div_id), html)
        assert div_match, f'{div_id} çizim div\'i advanced.html içinde yok'
        assert 'min-height' in div_match.group(0), (
            f'{div_id} için açık min-height yok (grafik yüksekliği çöker)')


def test_optional_plot_panels_have_chart_explanation():
    """Her yeni panelde mevcut desendeki açıklama bloğu bulunmalı."""
    html = _read(ADVANCED_HTML)
    for key, (panel_id, div_id) in OPTIONAL_PLOTS.items():
        start = html.index(f'id="{panel_id}"')
        end = html.index(f'id="{div_id}"')
        assert 'chart-explanation' in html[start:end], (
            f'{panel_id} için chart-explanation bloğu yok')


# --------------------------------------------------------------------------
# 4. Tasarım blokları rapora çıkıyor
# --------------------------------------------------------------------------

def test_design_blocks_reach_design_report():
    source = _read(APP_JS)
    body = _design_report_body(source)
    for block in DESIGN_BLOCKS:
        assert block in body, (
            f'{block} displayDesignReport içinde kullanılmıyor')

    # Bölüm üreticileri gerçekten tanımlı mı?
    for fn in ('nozzleAnglesSection', 'grainDesignSection', 'designSummarySection'):
        assert f'function {fn}(' in source, f'{fn} tanımlı değil'


def test_design_summary_recommendation_not_rendered():
    """design_summary.recommendation motor tarafında Türkçe üretiliyor;
    arayüz metinleri İngilizce olduğu için basılmamalı."""
    source = _read(APP_JS)
    assert 'recommendation' not in _design_report_body(source)


# --------------------------------------------------------------------------
# 5. renderOptionalPlot izole davranış testi (node ile)
# --------------------------------------------------------------------------

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(process.argv[2], 'utf8');

const elements = {};
function makeElement(id) {
    return {
        id: id,
        style: {},
        innerHTML: '',
        querySelectorAll: function () { return []; },
        addEventListener: function () {}
    };
}
['panelX', 'plotX'].forEach(function (id) { elements[id] = makeElement(id); });

const plotted = [];
const sandbox = {
    console: console,
    JSON: JSON,
    Plotly: {
        newPlot: function (id) { plotted.push(id); }
    },
    document: {
        getElementById: function (id) { return elements[id] || null; },
        querySelector: function () { return null; },
        querySelectorAll: function () { return []; },
        addEventListener: function () {}
    }
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const figure = JSON.stringify({
    data: [{x: [0, 1], y: [1, 2], type: 'scatter'}],
    layout: {title: 'ok', height: 400}
});

const cases = [];
function record(name, payload) {
    plotted.length = 0;
    elements.panelX.style.display = '';
    const drawn = sandbox.renderOptionalPlot('panelX', 'plotX', payload);
    cases.push({
        name: name,
        drawn: drawn,
        display: elements.panelX.style.display,
        plotted: plotted.slice()
    });
}

record('null', null);
record('undefined', undefined);
record('empty_string', '');
record('null_string', 'null');
record('error_object', {error: 'boom'});
record('empty_data', JSON.stringify({data: [], layout: {}}));
record('broken_json', '{not json');
record('valid', figure);

console.log(JSON.stringify(cases));
"""


@pytest.mark.skipif(NODE is None, reason='node bulunamadı')
def test_render_optional_plot_hides_panel_when_empty(tmp_path):
    harness = tmp_path / 'harness.js'
    harness.write_text(HARNESS, encoding='utf-8')

    proc = subprocess.run([NODE, str(harness), str(APP_JS)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f'harness çalışmadı:\n{proc.stderr}'

    cases = {c['name']: c for c in json.loads(proc.stdout.strip().splitlines()[-1])}

    empty_cases = ['null', 'undefined', 'empty_string', 'null_string',
                   'error_object', 'empty_data', 'broken_json']
    for name in empty_cases:
        case = cases[name]
        assert case['drawn'] is False, f'{name}: boş yük çizilmiş'
        assert case['display'] == 'none', f'{name}: panel gizlenmemiş'
        assert case['plotted'] == [], f'{name}: Plotly çağrılmış'

    valid = cases['valid']
    assert valid['drawn'] is True, 'geçerli figür çizilmedi'
    assert valid['display'] == 'block', 'geçerli figürde panel açılmadı'
    assert valid['plotted'] == ['plotX'], 'Plotly.newPlot doğru div ile çağrılmadı'


# --------------------------------------------------------------------------
# Birim sözleşmesi: arayüz mm², backend m²
# --------------------------------------------------------------------------

def test_reference_area_is_mm2_in_ui_and_converted_in_js():
    html = _read(ADVANCED_HTML)
    assert 'Reference Area (mm²)' in html, 'Referans alan etiketi mm² değil'

    source = _read(APP_JS)
    assert 'const MM2_PER_M2' in source, 'Dönüşüm katsayısı tek yerde tanımlı değil'
    assert 'refAreaMm2 / MM2_PER_M2' in source, (
        'mm² -> m² dönüşümü yapılmıyor (backend m² bekliyor)')
