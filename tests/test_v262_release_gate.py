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
    def test_package_version_matches_changelog(self):
        """Paket sürümü ile changelog'un en üst girdisi AYNI olmalı.

        v2.6.25 değişikliği: burada eskiden '2.6.2' sabiti vardı. Sabit sürüm
        beklentisi her yayında elle güncellenmek zorunda kaldığı için gerçek
        bir kapı değil, bakım yüküydü. Şimdi iki kaynağın tutarlılığı
        sınanıyor — sürüm numarası ne olursa olsun kapı çalışır.
        """
        import hrma
        d = json.loads(_read('hrma/data/changelog.json'))
        top = d['versions'][0]
        assert hrma.__version__ == top['version'], (
            'hrma.__version__=%s ama changelog en üst girdi=%s'
            % (hrma.__version__, top['version']))

    def test_changelog_top_entry_is_bilingual_and_measured(self):
        d = json.loads(_read('hrma/data/changelog.json'))
        top = d['versions'][0]
        assert top.get('notes_en') and top.get('notes_tr')
        # Sürüm notu ölçülmüş sayı içermeli, pazarlama cümlesi değil
        assert re.search(r'\d', top['notes_en']), 'sürüm notunda tek sayı yok'
        assert re.search(r'\d', top['notes_tr'])

    def test_262_entry_still_present_with_its_numbers(self):
        """Geçmiş sürüm notları silinmemeli (changelog kümülatiftir)."""
        d = json.loads(_read('hrma/data/changelog.json'))
        girdi = {v['version']: v for v in d['versions']}.get('2.6.2')
        assert girdi is not None, '2.6.2 girdisi changelog\'dan düşmüş'
        assert '15.9' in girdi['notes_en'], 'swirl bulgusu sayısıyla anlatılmamış'
        assert '15,9' in girdi['notes_tr'] or '15.9' in girdi['notes_tr']


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


# ===========================================================================
# v2.6.25 — saha düzeltmesi kapıları
# ===========================================================================

class TestFieldFixV2625:
    """v2.6.2'yi kullanılamaz yapan sınıftan hataları kilitler."""

    def test_cors_filter_has_no_hardcoded_port_list(self):
        """Süzgeç sabit port listesine geri dönmemeli.

        v2.6.2'de ``_ALLOWED_HOSTS`` içinde '127.0.0.1:8080' gibi sabitler
        vardı; başlatıcı 8081'e düşünce uygulama kendi API'sinden 403 aldı ve
        hiçbir motor tipi hesap yapamadı. Kapı: kaynakta port taşıyan sabit
        köken kalmasın.
        """
        src = _read('hrma/app.py')
        assert '_ALLOWED_HOSTS' not in src, (
            'sabit köken listesi geri gelmiş — port değişince uygulama '
            'kendi kendini 403 ile reddeder')
        assert re.search(r'def _is_loopback', src), (
            'geri döngü denetimi yok; köken süzgeci porta bağımlı olmuş olabilir')

    def test_launcher_and_runner_share_the_same_port_range(self):
        """Port aralığı iki dosyada da AYNI olmalı (ayrışma bu hatayı doğurdu)."""
        launcher = _read('packaging/launcher.py')
        runner = _read('hrma/run.py')
        assert 'range(8080, 8091)' in launcher, 'launcher port aralığı değişmiş'
        assert 'range(8080, 8091)' in runner, (
            'hrma/run.py başlatıcının port aralığını paylaşmıyor — '
            '8080 meşgulken çöker')
        assert 'port=8080' not in runner, 'run.py içinde sabit 8080 kalmış'

    def test_release_notes_are_bilingual_with_markers(self):
        """Güncelleme penceresi arayüz dilini izleyebilsin diye iki dilli im.

        Notlar tek dilde yayımlanınca Türkçe arayüzde soru Türkçe, sürüm notu
        İngilizce çıkıyordu (Berke'nin saha bildirimi, 2026-07-27).
        """
        import hrma
        notlar = _read('packaging/release_notes_v%s.md' % hrma.__version__)
        for dil in ('en', 'tr'):
            assert '<!--HRMA-LANG:%s-->' % dil in notlar, (
                '%s dil imi yok — güncelleme penceresi tek dil gösterir' % dil)
        # İmlerin arası gerçekten o dilde olmalı (blokların karışmaması)
        parcalar = re.split(r'<!--HRMA-LANG:(\w+)-->', notlar)
        bolum = {parcalar[i]: parcalar[i + 1] for i in range(1, len(parcalar), 2)}
        assert not re.search(r'[çğıİöşüÇĞÖŞÜ]', bolum['en']), (
            'İngilizce bölümde Türkçe karakter var — bloklar karışmış')
        assert re.search(r'[çğıİöşüÇĞÖŞÜ]', bolum['tr']), (
            'Türkçe bölüm Türkçe karakter içermiyor — çeviri yapılmamış olabilir')

    def test_update_modal_picks_language_section(self):
        """İstemci tarafı imleri ayıklayan işlevi taşımalı."""
        src = _read('hrma/static/js/update_check.js')
        assert 'pickLanguageSection' in src, (
            'güncelleme penceresi dil ayıklama işlevini kaybetmiş')
        assert 'HRMA-LANG' in src, 'dil imi deseni yok'

    def test_bundle_icon_is_full_bleed(self):
        """macOS 26 (Tahoe) bundle simgesine kendi karo maskesini uygular.

        Sanat eserinin kendi yuvarlatılmış karosunu çizmesi ve tuvali
        doldurmaması "karo içinde karo" görüntüsü üretiyordu (uygulama
        KAPALIYKEN). Kapı: bundle simgesi tam taşma kalsın.
        """
        from PIL import Image
        png = ROOT / 'packaging' / 'icon_1024_fullbleed.png'
        assert png.is_file(), (
            'tam taşma simge kaynağı yok — packaging/make_icons.py çalıştırın')
        im = Image.open(png).convert('RGBA')
        kutu = im.split()[3].getbbox()
        assert kutu == (0, 0, im.width, im.height), (
            'bundle simgesi tuvali doldurmuyor (alfa kutusu %s); Tahoe bunu '
            'kendi gri karosunun içine gömer' % (kutu,))

    def test_release_gate_script_exists_and_is_wired(self):
        """Yayın betiği kapıyı çağırmadan release oluşturmamalı."""
        assert (ROOT / 'packaging' / 'release_gate.sh').is_file(), (
            'yayın kapısı betiği yok')
        publish = _read('packaging/publish_release.sh')
        assert 'release_gate.sh' in publish, (
            'publish_release.sh kapıyı çağırmıyor — v2.6.2 kırmızı CI ile '
            'bu yüzden yayınlandı')
        # Sıra denetimi YORUMLARI saymaz: betiğin baş açıklaması hem kapıdan
        # hem 'gh release create'ten söz ediyor; ham metinde arama yapmak
        # açıklamayı çalışan kod sanar (bu testin ilk hâli buna takıldı).
        kod = '\n'.join(satir for satir in publish.split('\n')
                        if not satir.lstrip().startswith('#'))
        assert 'gh release create' in kod, 'yayın çağrısı bulunamadı'
        assert kod.index('release_gate.sh') < kod.index('gh release create'), (
            'kapı, release oluşturulduktan SONRA çalışıyor')

    def test_no_icloud_conflict_copies_in_source(self):
        """iCloud çakışma kopyaları kaynak ağacında kalmamalı.

        Proje iCloud Masaüstü içinde durduğu için servis zaman zaman
        "dosya 2.py" biçiminde çakışma kopyaları üretiyor. Bunlar git'te
        izlenmez ama derleme betikleri dizinleri OLDUĞU GİBİ kopyaladığından
        kurulum paketine girerler. 2026-07-27'de pakete iki bayat kopya
        girmişti: 'combustion_analysis 2.py' (16 saat eski) ve
        'nozzle_design 2.py' (15 gün eski, gerçek dosyanın yarısı boyutunda).

        İçe aktarılamazlar (adlarında boşluk var), ama pakette bulunmaları
        kafa karıştırır ve bir sonraki geliştiricinin yanlış dosyayı
        düzenlemesine yol açar.
        """
        desen = re.compile(r' \d+\.(py|js|json|md|html|tex)$')
        bulunan = []
        for klasor in ('hrma', 'tests', 'docs'):
            for yol in (ROOT / klasor).rglob('*'):
                if yol.is_file() and desen.search(yol.name):
                    bulunan.append(str(yol.relative_to(ROOT)))
        assert not bulunan, (
            'iCloud çakışma kopyaları kaynak ağacında: %s' % bulunan[:10])

    def test_ci_check_cannot_be_skipped_in_gate(self):
        """Kapıda CI kontrolü atlanabilir OLMAMALI.

        v2.6.25 yayınında `HIZLI=1` hem yerel tam takımı hem CI kontrolünü
        atlıyordu; ikisi aynı bayrağın altındaydı. Oysa maliyetleri taban
        tabana zıt: tam takım yerelde 20-40 dakika, CI kontrolü tek bir API
        çağrısı. Aynı bayrağa bağlamak, "hızlı geçeyim" diyen kişinin farkında
        olmadan projenin EN GÜÇLÜ kanıtını (temiz makinede yeşil takım)
        atlamasına yol açar — v2.6.2'yi yayınlayan hatanın ta kendisi.

        O yayında CI elle teyit edildi; bir dahakine kimse teyit etmeyebilir.

        v2.6.26 güncellemesi: bölümler eskiden '3/5' gibi sabit sayaçlarla
        aranıyordu; kapıya yeni bir bölüm eklenince (6/6 macOS imzası) sayaç
        kaydı ve test kapının İÇERİĞİNE değil NUMARASINA kırılmış oldu.
        Bölümler artık ``baslik "..."`` çağrılarının BAŞLIK METNİYLE bulunur;
        kapı sayısı kaç olursa olsun denetim aynı kalır.
        """
        src = _read('packaging/release_gate.sh')

        def _kod(metin):
            """Yorum satırlarını eler — açıklama metni kod sayılmamalı.

            Bu adımın NEDEN atlanamaz olduğunu anlatan yorum doğal olarak
            'HIZLI' kelimesini içerir; ham metinde arama yapmak o açıklamayı
            çalışan kod sanar.
            """
            return '\n'.join(s for s in metin.split('\n')
                             if not s.lstrip().startswith('#'))

        def _bolum(baslik_parcasi):
            """Başlığı verilen bölümün gövdesi (bir sonraki bölüme kadar)."""
            parcalar = re.split(r'baslik\s+"([^"]*)"', src)
            basliklar = parcalar[1::2]
            eslesen = [i for i, b in enumerate(basliklar)
                       if baslik_parcasi in b]
            assert len(eslesen) == 1, (
                "kapıda '%s' başlıklı TEK bölüm beklenirdi, bulunan: %s"
                % (baslik_parcasi, [basliklar[i] for i in eslesen]))
            return parcalar[2 + 2 * eslesen[0]]

        ci_bolumu = _kod(_bolum('GitHub Actions'))
        for bayrak in ('HIZLI', 'TAKIMI_ATLA', 'KAPIYI_ATLA'):
            assert bayrak not in ci_bolumu, (
                'CI kontrolü %s bayrağıyla atlanabilir hâle gelmiş — '
                'bu adım koşulsuz çalışmalı' % bayrak)
        # CI yeşil değilse kapı GERÇEKTEN kapanmalı: bölümde hem başarısızlık
        # kaydı hem gerçek kontrol çağrısı (gh run list) bulunmalı.
        assert 'basarisiz' in ci_bolumu, (
            'CI bölümü başarısızlık kaydetmiyor — kapı kapanamaz')
        assert 'gh run list' in ci_bolumu, (
            'CI bölümü gerçek CI durumunu sorgulamıyor')
        # Yerel tam takım ise atlanabilir olmalı (CI zaten koşturuyor)
        takim_bolumu = _kod(_bolum('Tam test takımı'))
        assert 'TAKIMI_ATLA' in takim_bolumu, (
            'yerel tam takımı atlama seçeneği kaybolmuş')
