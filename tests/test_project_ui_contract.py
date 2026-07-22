"""HRMA v2.5.5 frontend dalgası sözleşme testleri (2026-07-21).

Kapsam — üç yeni istemci modülü ve panel entegrasyonları:

  1. project_bar.js  — proje kaydet/yükle şeridi (backend:
     hrma/utils/projects_api.py). ARGE raporu davranış kararları kilitlenir:
     inputs.fields / dynamic.composition_rows / ui_state / dock_overrides
     serileştirmesi, geri yüklemede change olayı yayma zorunluluğu, dirty
     takibi + beforeunload, ?project= otomatik yükleme, 409 üzerine yazma
     akışı, istemci tarafı ad kuralı.
  2. import_ui.js + validation_panel.js — .eng/.rse motor dosyası importu
     (/api/import/motor-file), prediction ile CSV akışıyla aynı metrikler,
     çok motorlu seçici, meta + impuls sınıfı.
  3. sixdof_panel.js — itki kaynağı seçicisine "imported" seçeneği,
     .ork importu (/api/import/ork), mapping_report / estimated satır
     işareti / saved_simulations karşılaştırma kartı / gömülü motor.
  4. step_import_ui.js — STEP eşleme ekranı (/api/import/step): profile_2d
     kesiti, aday vurgusu, confidence rozetli öneri formu, "bulunamadı"
     davranışı (tahmin üretme YASAK), 501 dependency_missing mesajı,
     solid_index ile yeniden analiz.
  5. Şablon entegrasyonu: script sırası (plotly_dark + chart_captions
     SONRASI, sixdof_panel/validation_panel ÖNCESİ) ve landing şeridi.

Testler bilinçli olarak dosya-metni sözleşmeleridir (sayfa sözleşme testi
deseni): endpoint'ler test ortamında app'e kayıtlı olmayabilir, bu yüzden
Flask app import edilmez. Heuristikler dar tutuldu; kırılırlarsa davranış
gerçekten değişmiş demektir.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'

PROJECT_BAR = STATIC_JS / 'project_bar.js'
IMPORT_UI = STATIC_JS / 'import_ui.js'
STEP_UI = STATIC_JS / 'step_import_ui.js'
VALIDATION_PANEL = STATIC_JS / 'panels' / 'validation_panel.js'
SIXDOF_PANEL = STATIC_JS / 'sixdof_panel.js'
I18N_COMMON = STATIC_JS / 'i18n_common.js'

NEW_FILES = [PROJECT_BAR, IMPORT_UI, STEP_UI]
DESIGN_PAGES = [TEMPLATES / n for n in ('advanced.html', 'solid.html', 'liquid.html')]
INDEX_HTML = TEMPLATES / 'index.html'


def read(path):
    return path.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# 0. Varlık + sözdizimi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('path', NEW_FILES, ids=lambda p: p.name)
def test_new_module_exists_and_parses(path):
    assert path.exists(), '%s yok' % path.name
    assert len(read(path)) > 1000, '%s beklenenden küçük' % path.name
    if not shutil.which('node'):
        pytest.skip('node kurulu değil')
    result = subprocess.run([shutil.which('node'), '--check', str(path)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, '%s sözdizimi hatası:\n%s' % (path.name,
                                                                 result.stderr)


# ---------------------------------------------------------------------------
# 1. Proje şeridi — serileştirme / geri yükleme davranış sözleşmesi
# ---------------------------------------------------------------------------
def test_project_bar_talks_to_projects_api():
    src = read(PROJECT_BAR)
    assert "'/api/projects'" in src or '"/api/projects"' in src, \
        'proje listesi ucu kayboldu'
    assert '/api/projects/save' in src, 'kaydetme ucu kayboldu'
    assert '/api/projects/load/' in src, 'yükleme ucu kayboldu'
    # Belge şeması: format + format_version sabitleri istemciden gider
    assert "format: 'hrma-project'" in src, 'payload format etiketi kayboldu'
    assert 'format_version: 1' in src, 'payload format_version kayboldu'


def test_project_bar_serializes_special_sections():
    src = read(PROJECT_BAR)
    # Hibrit dinamik satırlar, sekme durumu ve güverte override'ları — ARGE
    # raporunun üç özel durumu; jenerik id-serileştirici bunları kaçırır
    assert 'composition_rows' in src, 'composition_rows özel durumu kayboldu'
    assert 'ui_state' in src, 'ui_state serileştirmesi kayboldu'
    assert 'dock_overrides' in src, 'dock_overrides serileştirmesi kayboldu'
    assert "ad_f_" in src, 'güverte alan öneki (ad_f_) okunmuyor'
    assert "dataset.dirty" in src, \
        'dock_overrides yalnız data-dirty=1 alanları içermeli / geri yüklemede işaretlemeli'


def test_project_bar_dispatches_change_on_restore():
    """ARGE raporu zorunluluğu: geri yüklenen HER alana olay yayılır."""
    src = read(PROJECT_BAR)
    assert "new Event('change'" in src, \
        'geri yüklemede change olayı yayılmıyor — bağımlı hesaplar güncellenmez'
    assert "new Event('input'" in src, \
        "geri yüklemede input olayı yayılmıyor (solid expansion ratio 'input' dinler)"


def test_project_bar_excludes_dynamic_panels_from_fields():
    src = read(PROJECT_BAR)
    for root in ('#analysisDock', '#sixDofPanel', '#injectorPanel', '#transientPanel'):
        assert root in src, \
            'dinamik panel kökü %s serileştirme dışlamasından çıkmış' % root


def test_project_bar_dirty_tracking_and_beforeunload():
    src = read(PROJECT_BAR)
    assert 'beforeunload' in src, 'beforeunload uyarısı kayboldu'
    assert re.search(r"addEventListener\('(input|change)'", src), \
        'form değişikliği dinleyicisi (dirty takibi) kayboldu'


def test_project_bar_client_side_name_rule():
    src = read(PROJECT_BAR)
    assert re.search(r'A-Za-z0-9 _\.\\?-', src), \
        'istemci tarafı ad beyaz listesi ([A-Za-z0-9 _.-]) kayboldu'
    assert '{1,80}' in src, 'ad uzunluk sınırı (1-80) kayboldu'


def test_project_bar_autoload_and_overwrite_flow():
    src = read(PROJECT_BAR)
    assert "get('project')" in src, '?project= otomatik yükleme kayboldu'
    assert '409' in src, '409 (ad çakışması) üzerine yazma akışı kayboldu'
    assert 'overwrite' in src, 'overwrite bayrağı gönderilmiyor'


def test_project_bar_results_summary_is_optional_and_never_injected():
    src = read(PROJECT_BAR)
    assert 'results_summary' in src, 'results_summary alanı kayboldu'
    # Özet yalnız KAYDEDİLİR/listelenir; currentResults'a atama yapılmamalı
    assert not re.search(r'window\.currentResults\s*=', src), \
        'project_bar.js currentResults YAZAMAZ (özet panellere enjekte edilemez)'


def test_project_bar_landing_strip_is_guarded():
    src = read(PROJECT_BAR)
    assert 'buildRecentStrip' in src, 'landing Recent Projects şeridi kayboldu'
    # Liste çağrısı başarısızsa şerit hiç kurulmamalı (return ile sessiz çıkış)
    strip = src[src.index('async function buildRecentStrip'):]
    strip = strip[:strip.index('\n    }')]
    assert 'catch' in strip and 'return' in strip, \
        'landing şeridi uç hatasında sessizce gizlenmiyor'


# ---------------------------------------------------------------------------
# 2. Motor dosyası importu (.eng/.rse)
# ---------------------------------------------------------------------------
def test_import_ui_endpoints_and_helpers():
    src = read(IMPORT_UI)
    assert '/api/import/motor-file' in src, 'motor-file ucu kayboldu'
    assert '/api/import/ork' in src, 'ork ucu kayboldu'
    assert 'impulseClass' in src, 'impuls sınıfı yardımcısı kayboldu'
    assert 'prop_mass_kg' in src, 'meta satırı yakıt kütlesini göstermiyor'


def test_validation_panel_accepts_motor_files():
    src = read(VALIDATION_PANEL)
    assert '.eng' in src and '.rse' in src, \
        'dosya kabulüne .eng/.rse eklenmemiş'
    assert 'postMotorFile' in src, 'motor dosyası importu panele bağlanmamış'
    # prediction: panelin CSV akışında kurduğu tahmin eğrisiyle aynı biçim
    assert re.search(r'prediction[^\n]*|postMotorFile\(', src)
    assert 'time: pred.time, thrust: pred.thrust' in src, \
        'prediction eğrisi {time, thrust} biçiminde gönderilmiyor'


def test_validation_panel_multi_motor_selector_recompares():
    src = read(VALIDATION_PANEL)
    assert 'vp_motor_select' in src, 'çok motorlu seçici kayboldu'
    assert 'recompareSelectedMotor' in src, \
        'seçim değişince yeniden karşılaştırma kayboldu'
    # Yeniden karşılaştırma CSV akışıyla AYNI compare() yolunu kullanır
    assert 'csvFromCurve' in src, \
        'seçili motor upload-csv üzerinden karşılaştırılmıyor'


def test_validation_panel_shows_meta_and_file_warnings():
    src = read(VALIDATION_PANEL)
    assert 'metaLineHtml' in src, 'meta satırı (ad/üretici/kütle/sınıf) kayboldu'
    assert 'fileWarnings' in src, 'dosya düzeyi uyarılar gösterilmiyor'


# ---------------------------------------------------------------------------
# 3. 6-DOF: itki kaynağı + .ork
# ---------------------------------------------------------------------------
def test_sixdof_imported_thrust_source():
    src = read(SIXDOF_PANEL)
    assert 'sd_thrust_src' in src, 'itki kaynağı seçici kayboldu'
    assert "'imported'" in src, "'Imported motor file' seçeneği kayboldu"
    assert 'sd_motor_file' in src, 'motor dosyası seçici kayboldu'
    assert 'payload.thrust_curve = importedCurve' in src, \
        'içe aktarılan eğri thrust_curve olarak gönderilmiyor'


def test_sixdof_prop_mass_is_suggested_not_silent():
    src = read(SIXDOF_PANEL)
    assert 'suggestPropMass' in src, 'prop kütle önerisi kayboldu'
    # Vurgulama: alan turuncu işaretlenir (sessiz yazma yasağı)
    seg = src[src.index('function suggestPropMass'):]
    seg = seg[:seg.index('\n    }')]
    assert 'COLORS.orange' in seg, 'önerilen prop kütlesi görsel vurgu taşımıyor'
    assert 'propMassSuggested' in seg, 'öneri kullanıcıya bildirilmiyor'


def test_sixdof_ork_import_contract():
    src = read(SIXDOF_PANEL)
    assert 'postOrk' in src, '.ork importu panele bağlanmamış'
    assert 'mapping_report' in src, 'mapping_report özeti gösterilmiyor'
    assert 'embedded_motors' in src, 'gömülü motor seçeneği kayboldu'
    assert 'saved_simulations' in src, 'saved_simulations saklanmıyor'
    assert 'renderOrkComparison' in src, \
        'Run sonrası OpenRocket vs HRMA karşılaştırma kartı kayboldu'
    # null aero alanlarına DOKUNULMAZ
    seg = src[src.index('function applyOrkAero'):]
    seg = seg[:seg.index('\n    }')]
    assert 'return' in seg and 'isFinite' in seg, \
        'null/sonlu olmayan aero değerleri atlanmıyor (null alana dokunma kuralı)'


def test_sixdof_estimated_component_rows_are_marked():
    src = read(SIXDOF_PANEL)
    seg = src[src.index('function compRowHtml'):]
    seg = seg[:seg.index('\n    }')]
    assert 'estimated' in seg, 'estimated satır işareti compRowHtml içinde yok'
    assert 'data-estimated' in seg, 'estimated satır DOM işareti (data-estimated) yok'


# ---------------------------------------------------------------------------
# 4. STEP eşleme ekranı
# ---------------------------------------------------------------------------
def test_step_ui_endpoint_and_flow():
    src = read(STEP_UI)
    assert '/api/import/step' in src, 'STEP ucu kayboldu'
    assert 'profile_2d' in src, 'kesit çizimi (profile_2d) kayboldu'
    assert 'solid_index' in src, 'montajda katı seçimi (solid_index) kayboldu'
    assert 'dependency_missing' in src, \
        '501 dependency_missing özel mesajı kayboldu'
    assert 'candidates' in src, 'aday listesi kayboldu'
    assert 'confidence' in src, 'öneri confidence rozeti kayboldu'


def test_step_ui_never_fabricates_missing_suggestions():
    """Gelmeyen öneri alanı boş + 'bulunamadı' etiketi alır; tahmin YOK."""
    src = read(STEP_UI)
    assert 'stepimp.notFound' in src, "'not found' etiketi kayboldu"
    # Öneri değeri yalnız backend'ten geliyorsa basılır (yoksa boş string)
    assert "typeof s.value === 'number' ? s.value : ''" in src, \
        'öneri alanı backend değeri yokken boş bırakılmıyor (tahmin riski)'


def test_step_ui_applies_to_form_with_events_and_expansion():
    src = read(STEP_UI)
    seg = src[src.index('function applyToForm'):]
    assert 'dispatchFieldEvents' in seg, \
        'Apply to form change/input olayı yaymıyor'
    assert 'expansionField' in src and 'Math.pow' in src, \
        'throat+exit -> expansion ratio hesabı kayboldu'
    assert 'HRMAProjectBar' in src and 'setSource' in src, \
        'STEP kaynağı proje şeridine bildirilmiyor'


def test_step_ui_page_maps_point_to_real_input_ids():
    """Eşleme haritasındaki her hedef id ilgili şablonda gerçekten var."""
    src = read(STEP_UI)
    maps = {
        'hybrid': TEMPLATES / 'advanced.html',
        'solid': TEMPLATES / 'solid.html',
        'liquid': TEMPLATES / 'liquid.html',
    }
    block = src[src.index('var PAGE_MAPS'):src.index('var SUGGESTION_KEYS')]
    for page, tpl in maps.items():
        seg = block[block.index(page + ':'):]
        # sayfa bloğu: bir sonraki sayfa adına ya da bloğun sonuna kadar
        ends = [seg.index(p + ':') for p in maps if p != page and (p + ':') in seg]
        seg = seg[:min(ends)] if ends else seg
        html = read(tpl)
        ids = re.findall(r"_mm:\s*'([\w]+)'", seg)
        eps = re.findall(r"expansionField:\s*'([\w]+)'", seg)
        assert ids, '%s için eşleme boş' % page
        for target in ids + eps:
            assert ('id="%s"' % target) in html, \
                '%s eşleme hedefi %s şablonda yok' % (page, target)


# ---------------------------------------------------------------------------
# 5. Şablon entegrasyonu
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('page', DESIGN_PAGES, ids=lambda p: p.name)
def test_design_pages_load_new_scripts_in_order(page):
    html = read(page)
    for name in ('import_ui.js', 'project_bar.js', 'step_import_ui.js'):
        assert ('/static/js/' + name) in html, '%s %s yüklemiyor' % (page.name, name)
    # Sıra: plotly_dark + chart_captions SONRASI, sixdof_panel ÖNCESİ
    # (import_ui.js, sixdof_panel.js kurulmadan önce tanımlı olmalı)
    pos = {name: html.index('/static/js/' + name) for name in
           ('plotly_dark.js', 'chart_captions.js', 'import_ui.js',
            'sixdof_panel.js', 'panels/validation_panel.js')}
    assert pos['plotly_dark.js'] < pos['import_ui.js'], \
        '%s: import_ui.js plotly_dark.js öncesinde' % page.name
    assert pos['chart_captions.js'] < pos['import_ui.js'], \
        '%s: import_ui.js chart_captions.js öncesinde' % page.name
    assert pos['import_ui.js'] < pos['sixdof_panel.js'], \
        '%s: import_ui.js sixdof_panel.js SONRASINDA — panel yardımcıları bulamaz' % page.name
    assert pos['import_ui.js'] < pos['panels/validation_panel.js'], \
        '%s: import_ui.js validation_panel.js SONRASINDA' % page.name


def test_index_loads_recent_projects_strip():
    html = read(INDEX_HTML)
    assert '/static/js/project_bar.js' in html, \
        'index.html Recent Projects şeridini yüklemiyor'
    assert '/static/js/i18n_common.js' in html, \
        'index.html proj.* anahtarları için i18n_common.js yüklemiyor'
    assert html.index('/static/js/i18n_common.js') \
        < html.index('/static/js/project_bar.js'), \
        'i18n_common.js project_bar.js SONRASINDA yükleniyor'


# ---------------------------------------------------------------------------
# 6. i18n bütünlüğü (hedefli hızlı kontrol; tam denetim test_i18n_common.py)
# ---------------------------------------------------------------------------
def test_new_key_prefixes_exist_in_both_languages():
    src = read(I18N_COMMON)
    for key in ("'proj.btnSave'", "'stepimp.title'", "'imp.metaLine'",
                "'sixdof.thrustSource'", "'panel.validation.motorSelect'"):
        assert src.count(key) == 2, \
            '%s anahtarı EN ve TR bloklarının ikisinde de olmalı' % key


if __name__ == '__main__':                  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, '-v']))
