"""Katı yakıt sayfası (hrma/templates/solid.html) sözleşme testleri (2026-07-19).

Berke'nin katı sayfası için verdiği iş kalemlerini kalıcı olarak kilitler:

  1. SÖZDİZİM — sayfadaki TÜM inline <script> blokları `node --check` temiz
     (node yoksa test atlanır). Sayfa 3000+ satır; tek yazım hatası bütün
     sayfayı sessizce ölü bırakıyordu.
  2. YAKIT/MALZEME KATALOĞU — /api/propellants + /api/materials'ı tüketen
     tablolar, satır seçimi ve "user override" mantığı için gereken id'ler
     ve fonksiyonlar mevcut; katalog alan haritası yalnız SAYFADA VAR OLAN
     input id'lerine yazıyor; uç düşerse fallback listesi devrede kalıyor.
  3. PANEL ÇAPASI — SixDofPanel.init'e anchorId veriliyor. Bu sayfada
     `.results-grid` YOK; çapa verilmezse panel `.container`a düşüp hesap
     yapılmadan görünüyordu (doğrulanmış bug).
  4. EXPORT PARİTESİ — yeni Excel/DXF/STEP/ZIP butonlarının onclick'leri
     tanımlı ve çağırdıkları uçlar app.py'de gerçekten kayıtlı.
  5. GRAFİK KALİTESİ — .plot-container'da açık min-height, tek kaynaklı
     Plotly config (responsive + modebar), itki/basınç eğrilerinde veri
     bandına oturan y ekseni, layout'larda sabit width yok.
  6. TEK DİL — sayfada kullanıcıya görünen Türkçe metin yok (aksansız
     yazılmış Türkçe kelimeler dahil; kod yorumları bilinçli Türkçe kalır).

Canlı uç kontrolleri test_client ile yapılır (sunucuya port bağlanmaz).
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SOLID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'solid.html'
APP_PY = REPO_ROOT / 'hrma' / 'app.py'


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def html():
    return SOLID_HTML.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def inline_scripts(html):
    """src'siz <script> bloklarının gövdeleri."""
    return re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)


@pytest.fixture(scope='module')
def script_text(inline_scripts):
    return '\n'.join(inline_scripts)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def mask_comments(text):
    """JS blok/satır yorumlarını ve HTML yorumlarını boşlukla maskeler.

    Ofsetler korunur. Proje stili gereği kod yorumları Türkçe'dir; dil
    testi yalnız ekranda görünen metni kapsar.
    """
    def blank(m):
        return re.sub(r'[^\n]', ' ', m.group(0))

    text = re.sub(r'<!--.*?-->', blank, text, flags=re.S)
    text = re.sub(r'/\*.*?\*/', blank, text, flags=re.S)
    text = re.sub(r'(?m)^[ \t]*//[^\n]*', blank, text)
    text = re.sub(r'(?m)(?<=[;{},)\s])//[^\n]*$', blank, text)
    return text


# ---------------------------------------------------------------------------
# 1. Sözdizimi
# ---------------------------------------------------------------------------
def test_inline_scripts_parse(inline_scripts):
    if not shutil.which('node'):
        pytest.skip('node bulunamadı — sözdizim kontrolü atlandı')
    assert inline_scripts, 'solid.html içinde inline script bulunamadı'
    for idx, body in enumerate(inline_scripts):
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as fh:
            fh.write(body)
            path = fh.name
        try:
            proc = subprocess.run(['node', '--check', path],
                                  capture_output=True, text=True)
            assert proc.returncode == 0, (
                f'solid.html inline script #{idx} sözdizim hatası:\n'
                f'{proc.stderr[:1500]}')
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 2. Yakıt / malzeme kataloğu
# ---------------------------------------------------------------------------
CATALOG_IDS = (
    'propellantCatalogPanel',
    'propellantCatalogTable',
    'propellantCatalogStatus',
    'propellant_family_filter',
    'catalogOverrideBanner',
    'catalogOverrideText',
    'materialCatalogTable',
    'materialCatalogStatus',
    'material_catalog_target',
)


def test_catalog_dom_ids_present(html):
    for element_id in CATALOG_IDS:
        assert f'id="{element_id}"' in html, f'#{element_id} sayfada yok'


def test_catalog_scripts_loaded_before_page_script(html):
    """propellant_catalog.js + materials_catalog.js sayfa script'inden ÖNCE."""
    prop = html.index('/static/js/propellant_catalog.js')
    mat = html.index('/static/js/materials_catalog.js')
    first_inline = re.search(r'<script(?![^>]*\bsrc=)[^>]*>', html).start()
    assert prop < first_inline
    assert mat < first_inline


def test_catalog_functions_defined(script_text):
    required = (
        'function renderPropellantCatalog(',
        'function selectPropellantRow(',
        'function applyPropellantRecord(',
        'function renderMaterialCatalog(',
        'function selectMaterialRow(',
        'function applyMaterialRecord(',
        'function initCatalogs(',
        'function markFieldOverridden(',
        'function resetOverridesToCatalog(',
        'function dismissOverrideBanner(',
        'function updateOverrideBanner(',
    )
    for fn in required:
        assert fn in script_text, f'{fn} tanımlı değil'


def test_catalog_uses_central_wrappers(script_text):
    """Katalog verisi merkezi sarmalayıcılardan gelir, elle fetch edilmez."""
    assert 'window.HRMAPropellants' in script_text
    assert 'window.HRMAMaterials' in script_text
    assert "typeof window.HRMAPropellants !== 'undefined'" in script_text
    assert "typeof window.HRMAMaterials !== 'undefined'" in script_text


def test_catalog_fallback_present(script_text):
    """Sarmalayıcı/uç düşerse hardcoded liste devrede kalır."""
    assert 'FALLBACK_PROPELLANTS' in script_text
    assert script_text.count('_propellantRows = FALLBACK_PROPELLANTS') >= 2


def test_propellant_field_map_targets_existing_inputs(html, script_text):
    """Harita yalnız SAYFADA olan input id'lerine yazmalı."""
    block = re.search(r'var PROPELLANT_FIELD_MAP = \[(.*?)\];', script_text, re.S)
    assert block, 'PROPELLANT_FIELD_MAP bulunamadı'
    ids = re.findall(r"id:\s*'([^']+)'", block.group(1))
    fields = re.findall(r"field:\s*'([^']+)'", block.group(1))
    assert len(ids) >= 8, 'katalog en az 8 alanı doldurmalı'
    assert len(ids) == len(fields), 'her id bir katalog alanına bağlı olmalı'
    for element_id in ids:
        assert f'id="{element_id}"' in html, f'harita olmayan alana yazıyor: {element_id}'


def test_propellant_field_map_matches_api_contract(client, script_text):
    """Haritadaki katalog alanları /api/propellants kayıtlarında GERÇEKTEN var."""
    block = re.search(r'var PROPELLANT_FIELD_MAP = \[(.*?)\];', script_text, re.S)
    fields = re.findall(r"field:\s*'([^']+)'", block.group(1))

    resp = client.get('/api/propellants')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True and data['propellants']
    record = next(iter(data['propellants'].values()))
    for field in fields:
        assert field in record, f'/api/propellants kaydında {field} yok'


def test_material_map_units_and_backend_families(script_text, client):
    """yield_strength Pa→MPa ölçeklenir; gövde ailesi backend listesiyle uyumlu."""
    assert "field: 'yield_strength', scale: 1e-6" in script_text

    resp = client.get('/api/materials')
    assert resp.status_code == 200
    materials = resp.get_json()['materials']
    # Katalogta yield_strength Pa mertebesinde (MPa değil) olmalı — aksi halde
    # 1e-6 ölçeği yanlış olur.
    steel = materials.get('steel_4130') or next(iter(materials.values()))
    assert steel['yield_strength'] > 1e6

    from hrma.engines.solid_rocket_engine import SOLID_COST_PARAMS
    backend_families = set(SOLID_COST_PARAMS['case_materials'])
    mapped = set(re.findall(r"value: '(\w+)' \}",
                            re.search(r'var CASE_MATERIAL_FAMILY = \[(.*?)\];',
                                      script_text, re.S).group(1)))
    assert mapped, 'CASE_MATERIAL_FAMILY boş'
    assert mapped <= backend_families, (
        f'backend tanımıyor: {mapped - backend_families}')


def test_case_material_options_match_backend(html):
    """case_material seçenekleri backend maliyet tablosuyla birebir."""
    from hrma.engines.solid_rocket_engine import SOLID_COST_PARAMS
    block = re.search(r'<select id="case_material">(.*?)</select>', html, re.S)
    assert block
    options = set(re.findall(r'value="(\w+)"', block.group(1)))
    assert options <= set(SOLID_COST_PARAMS['case_materials']), (
        f'backend tanımıyor: {options - set(SOLID_COST_PARAMS["case_materials"])}')


def test_override_contract(html, script_text):
    """Elle düzenlenen alan işaretlenir, katalog seçimi onu ezmez."""
    # Görsel işaret + data attribute
    assert 'input.field-overridden' in html
    assert "el.dataset.userOverride = 'true'" in script_text
    assert "classList.add('field-overridden')" in script_text
    # Uygulama sırasında override'lı alan ATLANIR
    assert script_text.count("dataset.userOverride === 'true'") >= 3
    # Geri alma metni
    assert "' overridden - reset to catalog values?'" in script_text
    assert 'onclick="resetOverridesToCatalog()"' in html


# ---------------------------------------------------------------------------
# 3. Panel çapası
# ---------------------------------------------------------------------------
def test_sixdof_panel_gets_anchor(html, script_text):
    init = re.search(r'SixDofPanel\.init\(\{(.*?)\}\);', script_text, re.S)
    assert init, 'SixDofPanel.init çağrısı yok'
    assert "anchorId: 'analysis-dock-anchor'" in init.group(1), (
        'anchorId verilmemiş — panel .container fallback ile hesapsız görünür')
    assert 'id="analysis-dock-anchor"' in html
    # Çapa #results içinde olmalı ki hesap bitmeden görünmesin
    results_start = html.index('<div id="results" class="results">')
    assert html.index('id="analysis-dock-anchor"') > results_start


def test_analysis_dock_gets_anchor(script_text):
    init = re.search(r'AnalysisDock\.init\(\{(.*?)\}\);', script_text, re.S)
    assert init
    assert "anchorId: 'analysis-dock-anchor'" in init.group(1)


# ---------------------------------------------------------------------------
# 4. Export pariteleri
# ---------------------------------------------------------------------------
EXPORT_BUTTONS = {
    'exportSolidExcel': '/api/export-xlsx',
    'exportSolidDXF': '/api/export-dxf',
    'exportSolidSTEP': '/api/export-step',
    'exportSolidCompleteZip': '/api/export-complete-zip',
}


def test_export_buttons_wired(html, script_text):
    for fn in EXPORT_BUTTONS:
        assert f'onclick="{fn}()"' in html, f'{fn} butonu yok'
        assert (f'function {fn}(' in script_text
                or f'async function {fn}(' in script_text), f'{fn} tanımsız'


def test_export_endpoints_exist_in_app():
    app_src = APP_PY.read_text(encoding='utf-8')
    for endpoint in set(EXPORT_BUTTONS.values()) | {'/api/trajectory-analysis',
                                                    '/api/database-status'}:
        assert f"@app.route('{endpoint}'" in app_src, f'{endpoint} app.py\'de yok'


def test_exports_post_motor_geometry(script_text):
    """DXF/STEP/ZIP motor_data olarak SI birimli motor_geometry gönderir."""
    helper = re.search(r'async function _solidDownloadExport\((.*?)\n        \}',
                       script_text, re.S)
    assert helper
    assert 'motor_data: currentResults.motor_geometry' in helper.group(1)
    assert 'currentResults.motor_geometry' in helper.group(1)


def test_excel_sheets_cover_solid_motor(script_text):
    body = re.search(r'async function exportSolidExcel\(\)(.*?)\n        \}\n',
                     script_text, re.S)
    assert body
    for sheet in ("name: 'Performance'", "name: 'Geometry'",
                  "name: 'Grain'", "name: 'Thrust curve'"):
        assert sheet in body.group(1), f'{sheet} sayfası yok'
    for header in ('Time (s)', 'Thrust (N)', 'Pressure (bar)',
                   'Burn area (m2)', 'Mass flow (kg/s)'):
        assert header in body.group(1), f'{header} sütunu yok'


def test_solid_result_feeds_exports(client):
    """/calculate_solid gerçekten motor_geometry ve thrust_curve döndürüyor."""
    payload = {
        'chamber_diameter': 100, 'grain_length': 500, 'core_diameter': 30,
        'chamber_pressure': 40, 'burn_rate_a': 0.005, 'burn_rate_n': 0.35,
        'grain_type': 'bates',
    }
    resp = client.post('/calculate_solid', json=payload)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    data = resp.get_json()
    assert 'motor_geometry' in data, 'export butonları motor_geometry bekliyor'
    for key in ('throat_diameter', 'exit_diameter', 'chamber_diameter',
                'chamber_length', 'motor_name'):
        assert key in data['motor_geometry']
    tc = data['thrust_curve']
    for key in ('time', 'thrust', 'pressure', 'burn_area', 'mass_flow'):
        assert key in tc and len(tc[key]) == len(tc['time'])


def test_trajectory_wired(html, script_text):
    assert 'id="trajectory_plots"' in html
    assert 'onclick="computeTrajectory()"' in html
    assert 'async function computeTrajectory(' in script_text
    assert "'/api/trajectory-analysis'" in script_text
    for field in ('traj_initial_mass', 'traj_final_mass', 'traj_drag_coeff',
                  'traj_ref_area', 'traj_burn_time'):
        assert f'id="{field}"' in html


def test_database_badges_present(html, script_text):
    assert 'database-status' in html
    assert 'cea-status' in html and 'nist-status' in html
    assert '.status-connected' in html and '.status-disconnected' in html
    assert 'async function checkDatabaseStatus(' in script_text
    assert "fetch('/api/database-status')" in script_text


def test_warnings_panel_is_silent_without_data(html, script_text):
    """Uyarı paneli varsayılan GİZLİ; veri yoksa uydurma içerik basmaz."""
    assert 'id="warningsPanel"' in html
    panel = re.search(r'<div id="warningsPanel"[^>]*>', html).group(0)
    assert 'display: none' in panel
    body = re.search(r'function displaySolidWarnings\(results\)(.*?)\n        \}\n',
                     script_text, re.S).group(1)
    assert "panel.style.display = 'none'" in body
    assert 'results.warnings' in body


# ---------------------------------------------------------------------------
# 5. Grafik kalitesi
# ---------------------------------------------------------------------------
def test_plot_container_has_explicit_height(html):
    block = re.search(r'\.plot-container \{(.*?)\}', html, re.S)
    assert block, '.plot-container kuralı yok'
    assert 'min-height' in block.group(1)
    assert '--hrma-plot-min-h' in html, 'yükseklik tek kaynaktan gelmeli'


def test_single_plot_config_source(script_text):
    """Tüm Plotly çağrıları ortak config'i kullanmalı (responsive + modebar)."""
    cfg = re.search(r'var HRMA_PLOT_CONFIG = \{(.*?)\};', script_text, re.S)
    assert cfg
    assert 'responsive: true' in cfg.group(1)
    assert 'displayModeBar: true' in cfg.group(1)

    calls = re.findall(r'Plotly\.newPlot\(([^;]*?)\);', script_text, re.S)
    assert calls, 'Plotly.newPlot çağrısı yok'
    for call in calls:
        assert 'HRMA_PLOT_CONFIG' in call, (
            f'ortak config kullanılmayan çizim: {call[:120]}')


def test_thrust_and_pressure_axes_follow_data(script_text):
    """İtki/basınç eğrilerinde y ekseni veri bandına oturur (0'a zorlanmaz)."""
    assert 'function hrmaAxisRange(' in script_text
    assert 'HRMA_PLOT_Y_PAD_FRACTION' in script_text
    assert 'hrmaPlotLayout({' in script_text
    assert 'results.thrust_curve.thrust);' in script_text
    assert 'results.thrust_curve.pressure);' in script_text
    # rangemode 'tozero' kullanılmamalı — eğri düzleşir
    assert "rangemode: 'tozero'" not in script_text


def test_no_fixed_width_in_layouts(script_text):
    """Layout'ta sabit width responsive'i ezer — helper'lar siliyor olmalı."""
    assert script_text.count('delete out.width;') >= 2
    assert not re.search(r'\n\s*width:\s*\d+,\s*\n\s*height:\s*\d+', script_text)


def test_hover_and_spikes_enabled(script_text):
    layout = re.search(r'function hrmaPlotLayout\((.*?)\n        \}',
                       script_text, re.S).group(1)
    assert "hovermode: 'x unified'" in layout
    assert 'showspikes: true' in layout
    assert 'autosize: true' in layout


# ---------------------------------------------------------------------------
# 6. Tek dil (İngilizce)
# ---------------------------------------------------------------------------
# Türkçe karakter kümesi ve özel-isim istisnaları TEK yerde: test_i18n.py.
# (Aynı sabiti iki dosyada farklı değerle tanımlamak yasak.)
from tests.test_i18n import ALLOWED, TURKISH_CHARS  # noqa: E402

# Bu sayfaya özgü, AKSANSIZ yazılmış Türkçe kelimeler (test_i18n listesini
# tamamlar; oradaki genel liste karakter tabanlı taramayı kaçıranlar içindir).
SOLID_TURKISH_WORDS = re.compile(
    r'\b(Parametre|Birim|Kesiti|Spesifikasyonlar|Frekans|Tasarimi|'
    r'Hesapla|Yakit|Sonuc|Uyari|Deger|Kutle|Analizi|Basinc|Sicaklik)\b'
)

VISIBLE_ATTRS = re.compile(r'(?:title|placeholder|alt|aria-label)\s*=\s*"([^"]*)"')
TEXT_NODE = re.compile(r'>([^<>]+)<')
JS_STRING = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"")


def _offenders(fragment):
    hits = []
    for chunk in fragment:
        if not chunk:
            continue
        clean = chunk
        for allowed in ALLOWED:
            clean = clean.replace(allowed, '')
        if TURKISH_CHARS.search(clean) or SOLID_TURKISH_WORDS.search(clean):
            hits.append(chunk.strip()[:90])
    return hits


def test_no_turkish_visible_text(html, inline_scripts):
    masked_html = mask_comments(re.sub(r'<style[^>]*>.*?</style>',
                                       lambda m: re.sub(r'[^\n]', ' ', m.group(0)),
                                       html, flags=re.S))
    fragments = TEXT_NODE.findall(masked_html) + VISIBLE_ATTRS.findall(masked_html)
    offenders = _offenders(fragments)
    assert not offenders, f'HTML metninde Türkçe kaldı: {offenders}'


def test_no_turkish_in_js_strings(inline_scripts):
    fragments = []
    for body in inline_scripts:
        masked = mask_comments(body)
        for single, double in JS_STRING.findall(masked):
            fragments.append(single or double)
    offenders = _offenders(fragments)
    assert not offenders, f'JS string\'lerinde Türkçe kaldı: {offenders}'


def test_no_emoji_in_page(html):
    """Berke kuralı: kullanıcıya görünen metinde emoji yok."""
    emoji = re.compile('[\U0001F300-\U0001FAFF☀-➿️]')
    masked = mask_comments(html)
    found = emoji.findall(masked)
    assert not found, f'sayfada emoji var: {set(found)}'


# ---------------------------------------------------------------------------
# 7. Sayfa gerçekten servis ediliyor mu
# ---------------------------------------------------------------------------
def test_solid_page_serves_catalog_markup(client):
    resp = client.get('/solid')
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    for element_id in CATALOG_IDS:
        assert f'id="{element_id}"' in page
    assert '/static/js/propellant_catalog.js' in page
    assert '/static/js/materials_catalog.js' in page


def test_units_are_millimetres_for_small_lengths(html):
    """1 m altındaki mühendislik boyutları mm; büyük boyutlar (irtifa) metre."""
    mm_fields = ('web_thickness', 'outer_diameter', 'core_diameter',
                 'grain_length', 'grain_gap', 'insulation_thickness',
                 'chamber_diameter', 'liner_thickness', 'case_thickness',
                 'throat_diameter', 'exit_diameter', 'star_radius',
                 'star_fillet', 'fin_width', 'fin_length')
    for field in mm_fields:
        block = re.search(
            r'<label>(.*?)</label>\s*<input[^>]*id="%s"' % re.escape(field),
            html, re.S)
        assert block, f'{field} etiketi bulunamadı'
        assert '(mm)' in block.group(1), f'{field} etiketinde mm birimi yok'

    # İrtifa metre kalmalı (büyük boyut)
    alt = re.search(r'<label>(.*?)</label>\s*<input[^>]*id="test_altitude"',
                    html, re.S)
    assert alt and '(m)' in alt.group(1)
