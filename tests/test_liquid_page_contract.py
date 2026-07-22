"""Sıvı yakıt sayfası (liquid.html) sözleşme testleri — 2026-07-19 parite dalgası.

Bu dosya, sıvı sayfasında düzeltilen dört sınıf hatayı kalıcı olarak kilitler:

  1. PANEL YERLEŞİMİ
     SixDofPanel / InjectorPanel / AnalysisDock init çağrılarında
     `anchorId: 'analysis-dock-anchor'` VARDIR ve çapa #results kabının
     İÇİNDEDİR. anchorId verilmezse paneller `.results-grid` arar, bu sayfada
     öyle bir kap yoktur, `.container`a düşerler ve hesap yapılmadan görünür
     olurlar (2026-07-19 bulgusu; katı sayfada da aynı hata vardı).

  2. HİBRİT/KATI PARİTESİ
     NASA CEA + NIST rozetleri, motor kesiti lejant açıklaması, uyarı paneli,
     ve altı gerçek export butonu (.eng / çizim PDF / DXF / STEP / komple ZIP /
     Excel) sayfada VARDIR ve doğru uçlara gider.

  3. YANILTICI BOŞ KUTU YOK
     `#parametric_plots` bölümü tamamen kaldırıldı — /parametric-analysis ucu
     yalnız HybridRocketEngine kurar, sıvı motoru desteklemez.

  4. SESSİZ VERİ KAYBI YOK
     app.py'deki LiquidRocketEngine(...) çağrısı yalnız yedi alanı kabul eder.
     Şablon bunu hem toplu bir "Solver Input Scope" notuyla hem de bağlanmamış
     alanların yanındaki satır içi işaretle DÜRÜSTÇE gösterir. Test, şablondaki
     SOLVER_WIRED_INPUT_IDS listesinin app.py'nin gerçek imzasıyla birebir
     tuttuğunu doğrular — backend bir alanı bağlarsa test kırılır ve liste
     güncellenmeye zorlanır.

Ayrıca: satır içi script'ler `node --check` geçer (node varsa) ve kullanıcıya
görünen Türkçe metin kalmamıştır (kod yorumları bilinçli olarak Türkçedir).
"""

import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'
APP_PY = REPO_ROOT / 'hrma' / 'app.py'

DOCK_ANCHOR_ID = 'analysis-dock-anchor'

# Panellerin init çağrılarında anchorId ZORUNLU olan JS modülleri.
ANCHORED_PANELS = ['SixDofPanel', 'InjectorPanel', 'AnalysisDock']

# Sayfada bulunması gereken gerçek export uçları.
EXPORT_ENDPOINTS = [
    '/api/export-eng',
    '/api/export-drawings-pdf',
    '/api/export-dxf',
    '/api/export-step',
    '/api/export-complete-zip',
    '/api/export-xlsx',
]

# Export butonlarının çağırdığı fonksiyon adları (onclick içinde).
EXPORT_HANDLERS = [
    'downloadLiquidEng',
    'exportLiquidDrawingsPDF',
    'exportLiquidDXF',
    'exportLiquidSTEP',
    'exportLiquidCompleteZip',
    'exportLiquidExcel',
]

# app.py:1544 civarındaki LiquidRocketEngine(...) çağrısının GERÇEKTEN
# okuduğu form alanları. Şablondaki SOLVER_WIRED_INPUT_IDS bununla aynı olmalı.
EXPECTED_WIRED_FIELDS = {
    'fuel_type', 'oxidizer_type', 'thrust', 'chamber_pressure',
    'mixture_ratio', 'cooling_type', 'injector_type',
}

# Kesit lejantındaki renkler visualization.py paletinden birebir gelir.
CROSS_SECTION_COLORS = {
    'chamber wall': 'rgba(148,163,180,0.85)',   # C_CASE
    'injector plate': 'rgba(210,177,116,0.95)',  # C_INJ
    'nozzle': 'rgba(122,136,150,0.9)',           # C_NOZ
}

# Daha önce sayfada bulunan, kullanıcıya görünen Türkçe metinler.
FORBIDDEN_VISIBLE_TR = ['>Parametre<', '>Birim<', '>Motor Kesiti<', 'Referans Alan']

TURKISH_CHARS = re.compile(r'[çğıİöşüÇĞÖŞÜ]')
ALLOWED_TR_TOKENS = ('Tezgöçen', 'Türkçe')


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def html():
    return LIQUID_HTML.read_text(encoding='utf-8')


def inline_scripts(text):
    """src'siz <script> bloklarının gövdelerini döndürür."""
    return re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', text, re.S)


def mask_comments_and_style(text):
    """Yorumları ve <style> bloklarını aynı uzunlukta boşlukla değiştirir.

    Satır sayısı korunur (ofsetler bozulmasın diye newline'lar aynen bırakılır),
    böylece bulgu satır numarasıyla raporlanabilir. Türkçe KOD YORUMLARI proje
    tercihidir; testin kapsamı yalnız ekranda görünen metin.
    """
    out = list(text)
    patterns = [
        r'<!--[\s\S]*?-->',
        r'<style[\s\S]*?</style>',
        r'/\*[\s\S]*?\*/',
        r'(?m)^[ \t]*//[^\n]*$',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            for i in range(m.start(), m.end()):
                if out[i] != '\n':
                    out[i] = ' '
    return ''.join(out)


def strip_allowed(fragment):
    for token in ALLOWED_TR_TOKENS:
        fragment = fragment.replace(token, '')
    return fragment


# ---------------------------------------------------------------------------
# 1. Panel yerleşimi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('panel', ANCHORED_PANELS)
def test_panel_init_has_anchor_id(html, panel):
    """Her panel init'i anchorId ile çağrılır (yoksa .container'a düşer)."""
    m = re.search(re.escape(panel) + r'\.init\(\{(.*?)\n\s*\}\);', html, re.S)
    assert m, f'{panel}.init(...) çağrısı bulunamadı'
    body = m.group(1)
    assert f"anchorId: '{DOCK_ANCHOR_ID}'" in body, (
        f'{panel}.init içinde anchorId eksik — panel hesap yapılmadan görünür'
    )


def test_dock_anchor_is_inside_results_container(html):
    """Çapa #results kabının İÇİNDE olmalı ki hesap bitmeden görünmesin."""
    start = html.index('<div id="results" class="results">')
    anchor = html.index(f'<div id="{DOCK_ANCHOR_ID}"></div>')
    assert anchor > start, 'analysis-dock-anchor #results kabından önce geliyor'

    # #results ile çapa arasında kapanmamış <div> sayısı > 0 olmalı
    between = html[start:anchor]
    opens = len(re.findall(r'<div\b', between))
    closes = len(re.findall(r'</div>', between))
    assert opens > closes, 'analysis-dock-anchor #results kabının dışına düşmüş'


def test_results_grid_absent(html):
    """Panellerin yedek çapası .results-grid bu sayfada YOK — bug'ın kökü."""
    assert 'class="results-grid"' not in html


# ---------------------------------------------------------------------------
# 2. Parite: rozetler / kesit açıklaması / uyarı paneli / exportlar
# ---------------------------------------------------------------------------
def test_database_status_badges_present(html):
    assert 'class="database-status status-connected cea-status"' in html
    assert 'class="database-status status-connected nist-status"' in html
    assert '.status-connected' in html and '.status-disconnected' in html


def test_database_status_is_fetched(html):
    assert "fetch('/api/database-status')" in html
    assert 'function checkDatabaseStatus' in html
    assert 'checkDatabaseStatus();' in html, 'rozet güncelleyici hiç çağrılmıyor'


def test_cross_section_explanation_present(html):
    """Motor kesiti için renk-kutucuklu lejant açıklaması var."""
    assert 'id="liquid_kesit_explanation"' in html
    block = html[html.index('id="liquid_kesit_explanation"'):]
    block = block[:block.index('id="liquid_motor_kesit"')]
    low = block.lower()
    for label, color in CROSS_SECTION_COLORS.items():
        assert label in low, f'kesit lejantında "{label}" yok'
        assert color in block, f'"{label}" için visualization.py rengi ({color}) yok'
    assert 'legend-swatch' in block


def test_cross_section_explanation_has_no_grain(html):
    """Sıvı motorda yakıt grain'i/liner YOKTUR; lejant grain listelemez."""
    block = html[html.index('id="liquid_kesit_explanation"'):]
    block = block[:block.index('id="liquid_motor_kesit"')].lower()
    # 'no fuel grain or liner' cümlesi hariç, grain bir BİLEŞEN olarak geçmemeli
    assert 'rgba(178,116,68' not in block, 'grain rengi (C_GRAIN) sıvı lejantında olmamalı'


def test_warnings_panel_present_and_hidden_by_default(html):
    assert 'id="warningsPanel"' in html
    assert 'id="warningsList"' in html
    m = re.search(r'<div id="warningsPanel"[^>]*>', html)
    assert 'display: none' in m.group(0), 'uyarı paneli varsayılan olarak gizli olmalı'
    assert 'function displayLiquidWarnings' in html
    assert 'displayLiquidWarnings(results);' in html, 'uyarı paneli hiç doldurulmuyor'


@pytest.mark.parametrize('endpoint', EXPORT_ENDPOINTS)
def test_export_endpoint_referenced(html, endpoint):
    assert f"'{endpoint}'" in html, f'{endpoint} ucu sayfada kullanılmıyor'


@pytest.mark.parametrize('handler', EXPORT_HANDLERS)
def test_export_button_and_handler(html, handler):
    assert f'onclick="{handler}()"' in html, f'{handler} butonu yok'
    assert re.search(r'function\s+' + handler + r'\s*\(', html), \
        f'{handler} fonksiyonu tanımlı değil'


def test_excel_sheets_are_liquid_specific(html):
    """Excel çalışma kitabı sıvıya uygun sayfalar içerir."""
    block = html[html.index('async function exportLiquidExcel'):]
    block = block[:block.index('SESSİZ VERİ KAYBI KORUMASI')]
    for sheet in ("name: 'Performance'", "name: 'Geometry'",
                  "name: 'Injector'", "name: 'Feed system'"):
        assert sheet in block, f'Excel sayfası eksik: {sheet}'


def test_eng_export_uses_declared_burn_time(html):
    """Sıvı motorda yanma süresi çözücüden gelmez; alan açıkça okunur."""
    block = html[html.index('async function downloadLiquidEng'):]
    block = block[:block.index('async function exportLiquidExcel')]
    assert "getElementById('max_burn_duration')" in block
    assert 'total_impulse: thrust * burnTime' in block


# ---------------------------------------------------------------------------
# 3. Yanıltıcı boş kutu yok
# ---------------------------------------------------------------------------
def test_parametric_placeholder_removed(html):
    """#parametric_plots ve 'hesaplanmıyor' yer tutucusu tamamen kaldırıldı."""
    assert 'id="parametric_plots"' not in html
    assert 'id="parametric_trajectory_content"' not in html
    assert "showSubTab('parametric_trajectory')" not in html
    assert 'computed in this release' not in html


def test_no_dead_plot_containers(html):
    """Sayfadaki her Plotly hedefi ya doldurulur ya da hiç yoktur."""
    # generateParametricPlots yalnız gerçekten çizilen üç div'i doldurur
    assert 'function generateParametricPlots' in html
    block = html[html.index('function generateParametricPlots'):]
    block = block[:block.index('function hrmaFmt')]
    for div in ('drawSingleAltitudePlot', 'drawAltitudeProfilePlot', 'drawEngineDiagram'):
        assert div in block


# ---------------------------------------------------------------------------
# 4. Sessiz veri kaybı: bağlanmamış alanlar dürüstçe işaretli
# ---------------------------------------------------------------------------
def test_solver_wired_list_matches_app_py(html):
    """Şablondaki 'çözücüye bağlı alanlar' listesi app.py imzasıyla aynı."""
    m = re.search(r'const SOLVER_WIRED_INPUT_IDS = \[(.*?)\];', html, re.S)
    assert m, 'SOLVER_WIRED_INPUT_IDS listesi bulunamadı'
    declared = set(re.findall(r"'([^']+)'", m.group(1)))
    assert declared == EXPECTED_WIRED_FIELDS, (
        'Şablondaki bağlı-alan listesi app.py ile uyuşmuyor.\n'
        f'  şablon: {sorted(declared)}\n'
        f'  beklenen: {sorted(EXPECTED_WIRED_FIELDS)}'
    )

    # app.py gerçekten bu alanları mı okuyor?
    app_src = APP_PY.read_text(encoding='utf-8')
    call = re.search(r'engine = LiquidRocketEngine\((.*?)\n\s*\)', app_src, re.S)
    assert call, 'app.py içinde LiquidRocketEngine(...) çağrısı bulunamadı'
    used = set(re.findall(r"data\.get\('([^']+)'", call.group(1)))
    used |= {'thrust', 'chamber_pressure', 'mixture_ratio'}  # yerel değişkenler
    assert used == EXPECTED_WIRED_FIELDS, (
        'app.py artık farklı alanlar okuyor — liquid.html listesini güncelle.\n'
        f'  app.py: {sorted(used)}'
    )


def test_unwired_inputs_are_marked(html):
    """Çözücüye ulaşmayan alanlar arayüzde işaretlenir (sessiz kayıp yok)."""
    m = re.search(r'const UNWIRED_INPUT_IDS = \[(.*?)\];', html, re.S)
    assert m, 'UNWIRED_INPUT_IDS listesi bulunamadı'
    unwired = set(re.findall(r"'([^']+)'", m.group(1)))
    # Görev metninde açıkça adı geçen üç alan mutlaka listede olmalı
    for field in ('startup_sequence', 'min_throttle', 'throttle_response'):
        assert field in unwired, f'{field} bağlanmamış olduğu halde işaretlenmiyor'
    # Bağlı alanlar YANLIŞLIKLA işaretlenmemeli
    assert not (unwired & EXPECTED_WIRED_FIELDS)

    assert 'function markUnwiredInputs' in html
    assert 'markUnwiredInputs();' in html, 'işaretleyici hiç çağrılmıyor'
    assert 'not-wired-note' in html


def test_export_only_input_is_labelled_separately(html):
    """max_burn_duration çözücüyü etkilemez ama .eng exportunu besler."""
    assert 'const EXPORT_ONLY_INPUTS' in html
    assert 'max_burn_duration:' in html
    assert 'markExportOnlyInputs();' in html


def test_solver_scope_note_present(html):
    """Kullanıcı formu ayarlamadan önce kapsamı görür."""
    assert 'id="solver_scope_note"' in html
    block = html[html.index('id="solver_scope_note"'):]
    block = block[:block.index('<!-- 1. Propellant Data -->')]
    assert 'Solver Input Scope' in block
    assert 'does not change the computed result' in block


def test_pdf_report_geometry_comes_from_results(html):
    """PDF geometrisi kullanıcının yazdığı (yok sayılan) değerlerden okunmaz."""
    block = html[html.index('async function exportPDF'):]
    block = block[:block.index('GRAFİK KALİTESİ')]
    assert "getElementById('chamber_diameter')" not in block
    assert "getElementById('throat_diameter')" not in block
    assert 'chamber_diameter: cr.chamber_diameter' in block


# ---------------------------------------------------------------------------
# 5. Grafik kalitesi
# ---------------------------------------------------------------------------
def test_all_plots_go_through_shared_renderer(html):
    """Tek doğrudan Plotly.newPlot çağrısı liquidPlot'un KENDİSİ olmalı."""
    direct = re.findall(r'Plotly\.newPlot\(', html)
    assert len(direct) == 1, (
        f'{len(direct)} doğrudan Plotly.newPlot çağrısı var; hepsi liquidPlot()'
        ' üzerinden geçmeli (responsive + hovermode + min-height)'
    )
    assert 'return Plotly.newPlot(el, traces, lay, cfg);' in html


def test_shared_renderer_applies_quality_defaults(html):
    block = html[html.index('function liquidPlot('):]
    block = block[:block.index('function setNistStatus')]
    assert 'delete lay.width;' in block, 'sabit width kaldırılmıyor'
    assert "lay.hovermode = 'x unified'" in block
    assert 'responsive: true' in block
    assert 'LIQUID_PLOT_MIN_HEIGHT_PX' in block


def test_no_fixed_width_in_plot_layouts(html):
    """Layout literal'lerinde sabit piksel genişliği kalmadı."""
    assert not re.search(r'\n\s*width:\s*\d{3,}\s*,', html)


def test_plot_containers_have_min_height(html):
    """Her Plotly kabı CSS'te açık min-height alır (0 px'e ezilme koruması)."""
    css = html[html.index('<style>'):html.index('</style>')]
    assert 'min-height: 400px' in css
    for cid in ('#liquid_motor_kesit', '#altitude_analysis_plot',
                '#altitude_profile_plot', '#engine_diagram', '#trajectory_plots'):
        assert cid in css, f'{cid} için min-height kuralı yok'


# ---------------------------------------------------------------------------
# 6. Sözdizimi ve dil
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which('node') is None, reason='node kurulu değil')
def test_inline_scripts_parse(html):
    blocks = inline_scripts(html)
    assert len(blocks) >= 3, 'satır içi script blokları bulunamadı'
    for idx, body in enumerate(blocks):
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as fh:
            fh.write(body)
            path = fh.name
        proc = subprocess.run(['node', '--check', path],
                              capture_output=True, text=True)
        pathlib.Path(path).unlink(missing_ok=True)
        assert proc.returncode == 0, (
            f'{idx}. satır içi script sözdizimi hatalı:\n{proc.stderr}')


@pytest.mark.parametrize('needle', FORBIDDEN_VISIBLE_TR)
def test_known_turkish_strings_removed(html, needle):
    assert needle not in html, f'kullanıcıya görünen Türkçe metin kaldı: {needle}'


def test_no_visible_turkish_text(html):
    """Yorumlar/style hariç, görünen metinde Türkçe'ye özgü harf kalmadı."""
    masked = mask_comments_and_style(html)
    offenders = []
    for lineno, line in enumerate(masked.split('\n'), 1):
        for m in re.finditer(r'>([^<>]{2,200})<', line):
            frag = strip_allowed(m.group(1))
            if TURKISH_CHARS.search(frag):
                offenders.append((lineno, frag.strip()))
        for m in re.finditer(r'(?:title|placeholder|alt|aria-label)\s*=\s*"([^"]*)"',
                             line):
            frag = strip_allowed(m.group(1))
            if TURKISH_CHARS.search(frag):
                offenders.append((lineno, frag.strip()))
    assert not offenders, f'görünen Türkçe metin: {offenders[:5]}'


def test_no_emoji_in_template(html):
    """Emoji yasağı (Berke 2026-07-15)."""
    emoji = re.compile(
        '[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]')
    hits = emoji.findall(html)
    assert not hits, f'şablonda emoji var: {hits[:10]}'


# ---------------------------------------------------------------------------
# 7. Sayfa gerçekten servis ediliyor mu
# ---------------------------------------------------------------------------
def test_liquid_page_renders():
    from hrma.app import app
    client = app.test_client()
    resp = client.get('/liquid')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert f"anchorId: '{DOCK_ANCHOR_ID}'" in body
    assert 'id="liquid_export_panel"' in body
    assert 'id="warningsPanel"' in body
