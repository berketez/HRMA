"""v2.6.2 sürüm kapısı — "bitti" iddiasını mekanik olarak sınar.

Bu dosya bir özellik testi değil, bir KABUL KAPISIDIR. v2.6.2'nin ilan edilen
kapsamındaki her madde ve denetimlerden gelen her kritik bulgu burada tek tek
doğrulanır. Yeşilse sürüm çıkabilir; kırmızıysa hangi maddenin eksik olduğunu
adıyla söyler.

Var olma sebebi: bu projede "modül yazıldı" ile "kullanıcıya ulaşıyor" arasında
tekrar tekrar sessiz kopukluklar oluştu — ``input_guard.py`` yazıldı ama kimse
import etmedi (safe_name NameError'ı oradan çıktı), ``flight_vehicle.py`` ve
``tile_cache.py`` yazıldı ama hiçbir rotaya bağlanmadı, ``flight_handoff.js``
yazıldı ama hiçbir şablon yüklemedi. Bu kapı o kopuklukları yakalar.
"""

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


# ===========================================================================
# 1. Sürüm hijyeni
# ===========================================================================

class TestVersionHygiene:
    def test_package_version_is_262(self):
        import hrma
        assert hrma.__version__ == '2.6.2'

    def test_changelog_has_262_in_both_languages(self):
        d = json.loads(_read('hrma/data/changelog.json'))
        top = d['versions'][0]
        assert top['version'] == '2.6.2'
        assert top.get('notes_en') and top.get('notes_tr')
        # Sürüm notu ölçülmüş sayı içermeli, pazarlama cümlesi değil
        assert '15.9' in top['notes_en'], 'swirl bulgusu sayısıyla anlatılmamış'
        assert '15,9' in top['notes_tr'] or '15.9' in top['notes_tr']


# ===========================================================================
# 2. A1/A2/A3/B1 — v2.6.2'nin ilan edilen özellikleri
# ===========================================================================

class TestDeclaredFeatures:
    def test_all_new_routes_registered(self):
        from hrma.app import app
        rules = {str(r) for r in app.url_map.iter_rules()}
        for want in ('/api/flight-vehicle',
                     '/api/tile/<layer_key>/<int:z>/<int:x>/<int:y>',
                     '/api/tile/cache/status',
                     '/api/tile/cache/clear'):
            assert want in rules, f'{want} rotası kayıtlı değil'

    def test_flight_handoff_loaded_and_called(self):
        """A1: köprü betiği üç motor sayfasında yüklü VE çağrılıyor olmalı."""
        for rel in ('hrma/templates/advanced.html', 'hrma/templates/solid.html',
                    'hrma/templates/liquid.html'):
            assert 'flight_handoff.js' in _read(rel), f'{rel}: betik yüklenmiyor'
        for rel, mt in (('hrma/static/js/app.js', 'hybrid'),
                        ('hrma/templates/solid.html', 'solid'),
                        ('hrma/templates/liquid.html', 'liquid')):
            src = _read(rel)
            assert 'FlightHandoff.publish' in src, f'{rel}: publish çağrısı yok'
            assert f"motor_type: '{mt}'" in src, f'{rel}: motor tipi geçilmiyor'

    def test_launch_site_flies_real_vehicle_not_demo(self):
        """A1: sabit demo araç sökülmüş, gerçek araç bağlanmış olmalı."""
        src = _read('hrma/templates/launch_site.html')
        assert 'currentVehicle' in src
        assert 'EXAMPLE_VEHICLE' in src, 'örnek araç ayrı etiketlenmemiş'
        assert '/api/flight-vehicle' in src

    def test_coriolis_latitude_reaches_solver(self):
        """B1: saha enlemi 6-DOF çözücüsüne geçmeli (düz-Dünya varsayımı kalkar)."""
        assert 'latitude_deg: la' in _read('hrma/templates/launch_site.html')
        assert 'latitude_deg' in _read('hrma/app.py')

    def test_flight_controls_gated_on_solution(self):
        """A3: kontroller uçuş çözülene kadar kapalı; kararsız araçta açılmaz."""
        src = _read('hrma/templates/launch_site.html')
        assert 'setFlightControlsEnabled' in src
        assert 'static_margin_full' in src, 'kararlılık kapısı yok'
        assert 'tumble_detected' in src

    def test_tile_cache_ui_present(self):
        """A2: atıf ve önbellek yönetimi kullanıcıya görünmeli."""
        src = _read('hrma/templates/launch_site.html')
        assert 'ls-clear-tiles' in src
        assert '/api/tile/cache/clear' in src


# ===========================================================================
# 3. Denetim bulguları — kritik düzeltmeler geri gelmemeli
# ===========================================================================

class TestAuditFixesHold:
    def test_swirl_coefficient_not_inverted(self):
        import numpy as np
        from hrma.engines.injector_design import _SWIRL_GEOMETRIC_COEF
        assert _SWIRL_GEOMETRIC_COEF == pytest.approx(np.pi / (4 * np.sqrt(2)))

    def test_slosh_damping_has_amplitude_term(self):
        from hrma.analysis.slosh_analysis import CylindricalTankSlosh
        m = CylindricalTankSlosh(radius=0.5, fill_height=1.0)
        lo = m.baffle_damping(0.2, 0.1, amplitude_ratio=0.01)['damping_ratio']
        hi = m.baffle_damping(0.2, 0.1, amplitude_ratio=0.04)['damping_ratio']
        assert hi / lo == pytest.approx(2.0, rel=1e-9), 'sqrt(eta/R) terimi yok'

    def test_non_finite_never_becomes_zero(self):
        from hrma.app import sanitize_json_values
        assert sanitize_json_values(float('nan')) is None
        assert sanitize_json_values(float('inf')) is None
        assert sanitize_json_values(0.0) == 0.0   # gerçek sıfır korunur

    def test_no_process_wide_warning_suppression(self):
        """Süreç geneli catch-all filtre kalmamalı (sessiz NaN zincirinin başı)."""
        import warnings

        import hrma.app  # noqa: F401  (tüm motor modüllerini içe aktarır)

        catch_all = [f for f in warnings.filters
                     if f[0] == 'ignore' and f[1] is None
                     and f[2] is Warning and f[3] is None]
        assert not catch_all, (
            f'{len(catch_all)} adet süreç geneli ignore filtresi var — '
            'bir modül filterwarnings("ignore") çağırıyor')

    def test_compliance_never_claims_conformity(self):
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        comp = SafetyAnalyzer()._check_safety_compliance(
            {'acceptability': 'ACCEPTABLE', 'individual_risks': {}})
        for k in ('nfpa_compliance', 'osha_compliance', 'dot_compliance'):
            assert comp[k] == 'NOT_EVALUATED'

    def test_source_has_no_nan_coercion(self):
        import inspect

        import hrma.app as appmod
        src = inspect.getsource(appmod.sanitize_json_values)
        body = src[src.index('"""', src.index('"""') + 3) + 3:]
        assert not re.search(r'return\s+0\.0', body)
        assert '1e10' not in body


# ===========================================================================
# 4. Güvenlik kapıları
# ===========================================================================

class TestSecurityGates:
    @pytest.fixture
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_no_wildcard_cors(self):
        assert 'from flask_cors import CORS' not in _read('hrma/app.py')

    def test_cross_origin_state_change_rejected(self, client):
        r = client.post('/analyze_safety', json={'chamber_pressure': 20},
                        headers={'Origin': 'https://evil.example'})
        assert r.status_code == 403

    def test_stl_download_blocks_traversal(self, client):
        for bad in ('..\\..\\..\\Windows\\win.ini', '..%5cwindows%5cwin.ini'):
            assert client.get(f'/download/stl/{bad}').status_code in (400, 404)

    def test_request_body_is_bounded(self):
        from hrma.app import app
        assert app.config.get('MAX_CONTENT_LENGTH')

    def test_export_uses_safe_name(self):
        for rel in ('hrma/export/step_export.py',
                    'hrma/export/drawing_generator.py'):
            assert 'from hrma.utils.input_guard import safe_name' in _read(rel)


# ===========================================================================
# 5. D-track — uyarı sözleşmesi eksiksiz
# ===========================================================================

class TestWarningContract:
    @staticmethod
    def _is_warning_code(node):
        """İlk argüman geçerli bir uyarı kodu mu?

        İki biçim geçerlidir:
          _w('warn.x.y', ...)
          _w('warn.x.ox' if stream == 'ox' else 'warn.x.fuel', ...)
        İkincisi ox/fuel gibi ikiz kodlar için kullanılıyor ve DOĞRUDUR;
        koşullu ifadenin İKİ dalı da kod olmak zorundadır.
        """
        if isinstance(node, ast.Constant):
            return isinstance(node.value, str) and node.value.startswith('warn.')
        if isinstance(node, ast.IfExp):
            return (TestWarningContract._is_warning_code(node.body)
                    and TestWarningContract._is_warning_code(node.orelse))
        return False

    def test_no_raw_warnings_left_in_engines(self):
        """Motor modüllerinde ham metin uyarı kalmamalı."""
        raw = []
        for path in (ROOT / 'hrma' / 'engines').glob('*.py'):
            for n in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if not isinstance(n, ast.Call):
                    continue
                fn = getattr(n.func, 'attr', None) or getattr(n.func, 'id', None)
                if fn not in ('_w', '_warn', '_mk_warning') or not n.args:
                    continue
                if not self._is_warning_code(n.args[0]):
                    raw.append(f'{path.name}:{n.lineno}')
        assert not raw, f'ham uyarı kalmış: {raw}'

    def test_every_engine_code_translated(self):
        codes = set()
        for path in (ROOT / 'hrma' / 'engines').glob('*.py'):
            codes |= set(re.findall(r"'(warn\.[a-z0-9_.]+)'",
                                    path.read_text(encoding='utf-8')))
        js = _read('hrma/static/js/i18n_common.js')
        en = set(re.findall(r"'(warn\.[a-z0-9_.]+)'\s*:",
                            js[js.index('        en: {'):js.index('        tr: {')]))
        tr = set(re.findall(r"'(warn\.[a-z0-9_.]+)'\s*:",
                            js[js.index('        tr: {'):]))
        assert not (codes - en), f'EN çevirisi eksik: {sorted(codes - en)}'
        assert not (codes - tr), f'TR çevirisi eksik: {sorted(codes - tr)}'

    def test_frontend_consumers_translate_recursively(self):
        """İç içe uyarı kayıtları da çevrilmeli ([object Object] regresyonu)."""
        for rel in ('hrma/static/js/analysis_dock.js',
                    'hrma/templates/solid.html',
                    'hrma/static/js/app.js',
                    'hrma/templates/liquid.html'):
            src = _read(rel)
            assert ('warnText' in src or 'warnToText' in src
                    or 'localizeWarning' in src), f'{rel}: çevirici yok'


# ===========================================================================
# 6. Dürüstlük — uydurma çıktı kalmamalı
# ===========================================================================

class TestOutputHonesty:
    def test_stl_export_is_fail_closed(self):
        import ast as _ast
        import inspect

        import hrma.app as appmod
        src = inspect.getsource(appmod.export_stl)
        tree = _ast.parse(src).body[0]
        body = tree.body[1:] if (tree.body and isinstance(tree.body[0], _ast.Expr)) else tree.body
        called = {n.func.id for n in _ast.walk(_ast.Module(body=body, type_ignores=[]))
                  if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)}
        assert 'generate_basic_stl_content' not in called
        assert 'generate_fallback_cad_geometry' not in called

    def test_tank_checklist_labels_template_fields(self):
        src = _read('hrma/export/cad_export.py')
        assert 'manufacturing_checklist_TEMPLATE.json' in src
        assert "'source': 'template'" in src

    def test_tank_material_comes_from_database(self):
        """Tank dayanımı ve yoğunluğu satır içi sabit olmamalı.

        AST ile bakılır: aynı metin AÇIKLAMA YORUMUNDA geçebilir (düzeltmenin
        neden yapıldığını anlatan not), o yorum bir regresyon değildir.
        Aranan şey gerçek bir ATAMA ifadesidir.
        """
        src = _read('hrma/engines/liquid_rocket_engine.py')
        assert 'get_material_safe' in src, 'malzeme veritabanından okunmuyor'

        bad = []
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Assign):
                continue
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if not (names & {'material_strength', 'material_density',
                             'fuel_material_strength', 'fuel_material_density'}):
                continue
            # Sabit sayı ataması = satır içi malzeme özelliği (yasak).
            if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, (int, float)):
                bad.append(f'{sorted(names)} = {node.value.value} '
                           f'(satır {node.lineno})')
        assert not bad, f'satır içi malzeme sabiti kalmış: {bad}'
