"""
HUD / Analiz Güvertesi statik varlık testleri — BOL TEST dalgası (2026-07-14).

Kapsam (test_client ile — sunucuya port BAĞLANMAZ):
  1. Statik varlıklar servis edilir ve boş değildir:
     /static/js/hud.js, /static/css/results_hud.css,
     /static/js/analysis_dock.js, /static/js/panels/*.js
  2. hud.js sözleşmesi: window.HRMAHud tanımı + beklenen API üyeleri.
  3. results_hud.css yalnız TANIMLI --hd-* değişkenlerini kullanır:
     tanım kümesi = theme.css tanımları ∪ results_hud.css yerel tanımları
     (--hd-amber dosyanın kendi başlık yorumunda belgelenmiş tek yerel
     istisnadır). Tanımsız var(--hd-*) kullanımı sessizce fallback'e düşer
     ve tema kaymasına yol açar — regresyon burada yakalanır.
  4. app.js hijyeni: eski mor (#667eea) yok; sabit 4.0'lık SF export
     bloğu geri gelmedi (gerçek SF değerleri backend'den okunur).
  5. JS bütünlüğü: hrma/static/js altındaki TÜM .js dosyaları
     `node --check` ile sözdizimi doğrulamasından geçer (node varsa).
"""

import pathlib
import re
import shutil
import subprocess
import warnings

import pytest

warnings.filterwarnings('ignore')

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_DIR = REPO_ROOT / 'hrma' / 'static'
JS_DIR = STATIC_DIR / 'js'
PANELS_DIR = JS_DIR / 'panels'
THEME_CSS = STATIC_DIR / 'css' / 'theme.css'
RESULTS_HUD_CSS = STATIC_DIR / 'css' / 'results_hud.css'
APP_JS = JS_DIR / 'app.js'

# Sözleşmenin çekirdek varlıkları (yol -> URL)
CORE_ASSETS = [
    '/static/js/hud.js',
    '/static/css/results_hud.css',
    '/static/js/analysis_dock.js',
]

# Panel dosyaları dosya sisteminden numaralanır — yeni panel eklenirse
# test otomatik kapsar (parametre listesi import anında kurulur)
PANEL_URLS = sorted(
    '/static/js/panels/' + p.name for p in PANELS_DIR.glob('*.js')
)

ALL_JS_FILES = sorted(JS_DIR.rglob('*.js'))

# theme.css'in çekirdek değişken seti — tema dosyası güdükleşirse
# (yanlış birleştirme, kazayla silme) test yüksek sesle düşer
THEME_CORE_VARS = {
    '--hd-bg0', '--hd-panel', '--hd-inset', '--hd-line', '--hd-ink',
    '--hd-ink-dim', '--hd-cyan', '--hd-orange', '--hd-green', '--hd-red',
    '--hd-mono', '--hd-radius',
}

VAR_DEF_RE = re.compile(r'(--hd-[\w-]+)\s*:')
VAR_USE_RE = re.compile(r'var\(\s*(--hd-[\w-]+)')


def _css_definitions(path):
    return set(VAR_DEF_RE.findall(path.read_text(encoding='utf-8')))


def _css_usages(path):
    return set(VAR_USE_RE.findall(path.read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# 1. Statik varlıklar servis edilir + boş değil
# ---------------------------------------------------------------------------

class TestAssetsServed:
    @pytest.mark.parametrize('url', CORE_ASSETS + PANEL_URLS)
    def test_asset_200_and_nonempty(self, client, url):
        r = client.get(url)
        assert r.status_code == 200, f"{url} -> {r.status_code}"
        assert len(r.data) > 100, f"{url} şüpheli derecede küçük/boş"

    def test_panels_exist_on_disk(self):
        """En az 3 panel (structural/thermal/safety) diskte olmalı."""
        names = {p.rsplit('/', 1)[-1] for p in PANEL_URLS}
        assert {'structural_panel.js', 'thermal_panel.js',
                'safety_panel.js'} <= names, f"eksik panel: {names}"

    @pytest.mark.parametrize('url', PANEL_URLS)
    def test_panel_registers_itself(self, client, url):
        """Her panel AnalysisDock.register çağrısı içermeli — aksi halde
        güvertede sekmesi hiç görünmez."""
        body = client.get(url).get_data(as_text=True)
        assert 'AnalysisDock.register' in body, (
            f"{url} kendini AnalysisDock'a kaydetmiyor")


# ---------------------------------------------------------------------------
# 2. hud.js sözleşmesi
# ---------------------------------------------------------------------------

class TestHudJsContract:
    @pytest.fixture(scope='class')
    def hud_source(self, client):
        return client.get('/static/js/hud.js').get_data(as_text=True)

    def test_defines_hrmahud_global(self, hud_source):
        assert re.search(r'window\.HRMAHud\s*=', hud_source), (
            'hud.js window.HRMAHud tanımlamıyor')

    @pytest.mark.parametrize('member', ['countUp', 'termLog', 'bindState',
                                        'initAll'])
    def test_api_member_present(self, hud_source, member):
        assert member in hud_source, f"HRMAHud.{member} kayıp"


# ---------------------------------------------------------------------------
# 3. results_hud.css --hd-* değişken disiplini
# ---------------------------------------------------------------------------

class TestHudCssVariables:
    def test_theme_defines_core_set(self):
        defined = _css_definitions(THEME_CSS)
        missing = THEME_CORE_VARS - defined
        assert not missing, f"theme.css çekirdek değişkenleri kayıp: {missing}"

    def test_results_hud_uses_only_defined_vars(self):
        theme_defs = _css_definitions(THEME_CSS)
        local_defs = _css_definitions(RESULTS_HUD_CSS)
        used = _css_usages(RESULTS_HUD_CSS)
        undefined = used - theme_defs - local_defs
        assert not undefined, (
            f"results_hud.css tanımsız --hd-* kullanıyor: {sorted(undefined)} "
            "(theme.css'e ekle ya da yereldeki tanımı koru)")

    def test_local_exception_is_only_amber(self):
        """Yerel tanım istisnası belgelenmiş tek değişkenle sınırlı kalmalı;
        theme.css'te zaten tanımlı olanların yerelde EZİLMESİ de yasak
        (tema birliği kuralı)."""
        theme_defs = _css_definitions(THEME_CSS)
        local_defs = _css_definitions(RESULTS_HUD_CSS)
        assert local_defs <= {'--hd-amber'}, (
            f"results_hud.css beklenmeyen yerel --hd-* tanımlıyor: "
            f"{sorted(local_defs - {'--hd-amber'})}")
        assert not (local_defs & theme_defs), (
            'results_hud.css theme.css değişkenini eziyor')

    def test_all_static_css_use_defined_hd_vars(self):
        """Genişletilmiş disiplin: static/css altındaki her dosyanın
        var(--hd-*) kullanımı kendi + theme.css tanımlarıyla karşılanmalı."""
        theme_defs = _css_definitions(THEME_CSS)
        for css in sorted((STATIC_DIR / 'css').glob('*.css')):
            used = _css_usages(css)
            undefined = used - theme_defs - _css_definitions(css)
            assert not undefined, (
                f"{css.name} tanımsız --hd-* kullanıyor: {sorted(undefined)}")


# ---------------------------------------------------------------------------
# 4. app.js hijyeni
# ---------------------------------------------------------------------------

class TestAppJsHygiene:
    @pytest.fixture(scope='class')
    def app_js_source(self):
        return APP_JS.read_text(encoding='utf-8')

    def test_old_purple_gone(self, app_js_source):
        """Eski mor tema rengi (#667eea) koyu HUD temasıyla değiştirildi;
        geri gelmesi tema birliğini bozar."""
        assert not re.search(r'#667eea', app_js_source, re.IGNORECASE), (
            "app.js'te eski mor #667eea hâlâ var")

    def test_old_gradient_partner_gone(self, app_js_source):
        """#667eea'nın eski gradyan eşi #764ba2 de dönmemeli."""
        assert not re.search(r'#764ba2', app_js_source, re.IGNORECASE), (
            "app.js'te eski gradyan moru #764ba2 hâlâ var")

    def test_hardcoded_sf_export_gone(self, app_js_source):
        """Eski export bloğu SF'leri sabit 4.0/3.0 yazıyordu; şimdi gerçek
        backend değerleri (safety_factor_pressure/total) okunmalı.
        Not: regex yalnız atamaları yakalar; 'eski 4.0 kaldırıldı' gibi
        yorum satırlarını tetiklemez."""
        pattern = re.compile(
            r"(?:safety_factor\w*|SF_\w+|pressure_only|total_incl_thermal)"
            r"\s*[:=]\s*['\"]?[34]\.0\b")
        hits = pattern.findall(app_js_source)
        assert not hits, f"app.js'te sabit SF ataması geri gelmiş: {hits}"

    def test_real_sf_fields_exported(self, app_js_source):
        """Export bloğu gerçek çift-SF alanlarını okumalı."""
        assert 'safety_factor_pressure' in app_js_source
        assert 'safety_factor_total' in app_js_source


# ---------------------------------------------------------------------------
# 5. JS bütünlüğü — node --check
# ---------------------------------------------------------------------------

NODE = shutil.which('node')


@pytest.mark.skipif(NODE is None, reason='node bulunamadı')
class TestJsSyntax:
    @pytest.mark.parametrize(
        'js_file', ALL_JS_FILES,
        ids=[str(p.relative_to(JS_DIR)) for p in ALL_JS_FILES])
    def test_node_check_passes(self, js_file):
        proc = subprocess.run(
            [NODE, '--check', str(js_file)],
            capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, (
            f"node --check {js_file.name} başarısız:\n{proc.stderr[:800]}")

    def test_js_inventory_sane(self):
        """Çekirdek dosyalar envanterde olmalı (glob boş dönerse test
        sessizce 'hep yeşil'e düşmesin)."""
        names = {p.name for p in ALL_JS_FILES}
        assert {'app.js', 'hud.js', 'analysis_dock.js'} <= names


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
