"""v2.6.26 güvenlik bekçileri: arşiv girdi adı ve elektronik tablo enjeksiyonu.

Bu testler v2.6.26 doğrulama turunda AMPİRİK olarak sömürülen üç kusuru
kalıcı olarak kapalı tutar:

1. ZIP Slip — ``motor_name='../../EVIL'`` ile üretilen arşivde
   ``../EVIL_chamber.step`` ve ``openrocket/../../EVIL.eng`` girdileri çıkıyordu.
   Kara liste yetmez: ters bölü ve ``C:`` sürücü ön eki POSIX'te
   ``os.path.normpath``'ten kaçıyor (ölçüldü), bu yüzden beyaz liste sınanır.
2. XLSX formül enjeksiyonu — ``=1+1`` ile başlayan hücre ``data_type='f'``
   olarak saklanıyordu.
3. Yerel API güven sınırı — Host kapısı GET/HEAD/OPTIONS'ta hiç çalışmıyordu;
   ``Host: evil.example`` başlıklı düz bir GET tam tasarım belgesini
   döndürüyordu (DNS-rebinding).
"""

import io
import zipfile

import pytest

from hrma.utils.input_guard import is_safe_arcname, safe_arcname, safe_name


# --- Traversal varyantları: v2.6.26 turunda gerçekten denenen 12 giriş -----
TRAVERSAL_NAMES = [
    '../../EVIL',
    '../EVIL',
    '/tmp/EVIL',
    'C:\\EVIL',
    '..\\..\\EVIL',
    '../../../../../../../../tmp/EVIL',
    'EVIL\x00.step',
    '%2e%2e%2fEVIL',
    './../EVIL',
    'a/../../EVIL',
    '\u2024\u2024/EVIL',   # tek nokta benzeri Unicode (spoof)
    '....//EVIL',
]


class TestSafeArcname:
    """Beyaz liste doğrudan sınanır — HTTP katmanı olmadan."""

    @pytest.mark.parametrize('name', TRAVERSAL_NAMES)
    def test_traversal_name_never_survives_safe_name(self, name):
        cleaned = safe_name(name)
        assert '/' not in cleaned
        assert '\\' not in cleaned
        assert ':' not in cleaned
        assert '\x00' not in cleaned
        assert cleaned != '..'

    @pytest.mark.parametrize('name', TRAVERSAL_NAMES)
    def test_safe_arcname_output_is_accepted_by_guard(self, name):
        assert is_safe_arcname(safe_arcname('step', f'{name}_chamber.step'))

    @pytest.mark.parametrize('bad', [
        '../EVIL.step',
        'step/../../EVIL.step',
        '/abs/EVIL.step',
        'C:\\EVIL.step',
        'dir\\EVIL.step',
        'EVIL\x00.step',
        '',
        '..',
        'step//EVIL.step',
    ])
    def test_guard_rejects_unsafe(self, bad):
        assert not is_safe_arcname(bad)

    @pytest.mark.parametrize('good', [
        'MOTOR_chamber.step',
        'step/MOTOR_nozzle.step',
        'drawings/MOTOR_profile.dxf',
        'geometry/motor_geometry.json',
        'MANIFEST.txt',
    ])
    def test_guard_accepts_legitimate(self, good):
        assert is_safe_arcname(good)

    def test_zip_files_raises_on_unsafe_entry(self):
        """Bekçi çağıranın dikkatine değil koda bağlı olmalı.

        İleride eklenecek bir çağıran adı temizlemeyi unutursa ZIP üretimi
        sessizce traversal taşımak yerine PATLAMALI.
        """
        from hrma.app import _zip_files
        with pytest.raises(ValueError, match='unsafe archive entry name'):
            _zip_files({}, text_map={'../EVIL.txt': 'zararli'})


class TestSpreadsheetInjection:
    def test_formula_lead_is_escaped(self):
        from hrma.app import _spreadsheet_safe
        for raw in ['=1+1', '+2+2', '@SUM(A1)', '=cmd|\' /C calc\'!A0',
                    '\tTAB', '\rCR']:
            assert _spreadsheet_safe(raw).startswith("'"), raw

    def test_numbers_are_not_corrupted(self):
        """Negatif sayı '-' ile başlar; apostrof eklenirse veri bozulur."""
        from hrma.app import _spreadsheet_safe
        for raw in ['-5000', '-3.2', '+4.5', '-1.2e-3', '0', '42']:
            assert _spreadsheet_safe(raw) == raw, raw

    def test_plain_text_untouched(self):
        from hrma.app import _spreadsheet_safe
        assert _spreadsheet_safe('HRMA Motor') == 'HRMA Motor'

    def test_sheet_title_sanitised_not_500(self):
        from hrma.app import _safe_sheet_title
        title = _safe_sheet_title('Sheet/With:Bad*Chars[]', 0)
        assert not set(title) & set('\\/*?:[]')
        assert len(title) <= 31

    def test_xlsx_endpoint_writes_no_formula_cells(self):
        """Uçtan uca: üretilen çalışma kitabında formül hücresi olmamalı."""
        openpyxl = pytest.importorskip('openpyxl')
        from hrma.app import app

        client = app.test_client()
        resp = client.post('/api/export-xlsx', json={
            'filename': 'guard.xlsx',
            'sheets': [{
                'name': 'Bad/Name:Here',
                'headers': ['=1+1', '@SUM(A1)', 'normal'],
                'rows': [['=cmd|calc', '-5000', 'duz metin']],
            }],
        })
        assert resp.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(resp.data))
        ws = wb[wb.sheetnames[0]]
        formulas = [c.coordinate for row in ws.iter_rows()
                    for c in row if c.data_type == 'f']
        assert formulas == [], f'formul hucresi kaldi: {formulas}'


class TestLocalApiTrustBoundary:
    """v2.6.26: Host kapısı artık OKUMA isteklerinde de çalışıyor."""

    @staticmethod
    def _client():
        from hrma.app import app
        return app.test_client()

    @pytest.mark.parametrize('path', [
        '/', '/api/projects', '/api/correlation-report',
    ])
    def test_rebinding_get_is_rejected(self, path):
        resp = self._client().get(path, headers={'Host': 'evil.example:8080'})
        assert resp.status_code == 403, (
            f'{path} DNS-rebinding altinda veri sizdiriyor')

    @pytest.mark.parametrize('method', ['GET', 'HEAD', 'OPTIONS', 'POST'])
    def test_rebinding_rejected_for_every_method(self, method):
        resp = self._client().open('/api/projects', method=method,
                                   headers={'Host': 'evil.example:8080'})
        assert resp.status_code == 403

    @pytest.mark.parametrize('host', [
        '127.0.0.1:8080', '127.0.0.1:8081', 'localhost:8085', '[::1]:8090',
    ])
    def test_loopback_host_on_any_port_is_accepted(self, host):
        """v2.6.25 saha hatası: sabit port varsayımı uygulamayı kilitlemişti.

        Başlatıcı 8080-8090 arasında boş port arar; kapı hangi geri döngü
        portundan gelirse gelsin kendi sayfasını reddetmemeli.
        """
        resp = self._client().get('/api/projects', headers={'Host': host})
        assert resp.status_code != 403

    def test_security_headers_present(self):
        resp = self._client().get('/')
        assert resp.headers.get('X-Frame-Options') == 'DENY'
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
        assert 'frame-ancestors' in resp.headers.get(
            'Content-Security-Policy', '')

    def test_foreign_loopback_port_origin_is_rejected(self):
        """127.0.0.1'in BAŞKA portundaki sayfa bize CSRF yapamamalı."""
        from hrma.app import app
        previous = app.config.get('HRMA_SELF_PORT')
        app.config['HRMA_SELF_PORT'] = 8080
        try:
            resp = app.test_client().post(
                '/api/altitude-to-pressure',
                json={'altitude': 1000},
                headers={'Host': '127.0.0.1:8080',
                         'Origin': 'http://127.0.0.1:9999'})
            assert resp.status_code == 403
            ok = app.test_client().post(
                '/api/altitude-to-pressure',
                json={'altitude': 1000},
                headers={'Host': '127.0.0.1:8080',
                         'Origin': 'http://127.0.0.1:8080'})
            assert ok.status_code == 200
        finally:
            app.config['HRMA_SELF_PORT'] = previous

    def test_missing_self_port_falls_back_to_loopback_check(self):
        """Port bilinmiyorsa (geliştirme) kapı gevşer — saha hatası dönmesin."""
        from hrma.app import app
        previous = app.config.get('HRMA_SELF_PORT')
        app.config['HRMA_SELF_PORT'] = None
        try:
            resp = app.test_client().post(
                '/api/altitude-to-pressure',
                json={'altitude': 1000},
                headers={'Host': '127.0.0.1:8080',
                         'Origin': 'http://127.0.0.1:9999'})
            assert resp.status_code == 200
        finally:
            app.config['HRMA_SELF_PORT'] = previous


class TestClientSideCsvGuard:
    """İstemci CSV üreticilerinin dördü de formül kaçışı yapmalı.

    CSV sunucuda değil tarayıcıda üretiliyor; bu yüzden statik kaynak
    denetimi tek mekanik bekçi. Yeni bir kopya eklenirse burası kırmızı olur.
    """

    CSV_SOURCES = [
        'hrma/static/js/transient_panel.js',
        'hrma/templates/advanced.html',
        'hrma/templates/solid.html',
        'hrma/templates/liquid.html',
    ]

    @pytest.mark.parametrize('relpath', CSV_SOURCES)
    def test_source_has_formula_escape(self, relpath):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        text = (root / relpath).read_text(encoding='utf-8')
        assert 'text/csv' in text, f'{relpath} artik CSV uretmiyor mu?'
        assert '/^[=+\\-@\\t\\r]/' in text, (
            f'{relpath} icinde formul kacisi yok — CSV enjeksiyonu acik')

    def test_no_unguarded_csv_producer_added(self):
        """CSV üreten yeni bir dosya eklenirse listeye de eklenmeli."""
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        found = set()
        for pattern in ('hrma/static/js/*.js', 'hrma/templates/*.html'):
            for path in root.glob(pattern):
                if 'text/csv' in path.read_text(encoding='utf-8'):
                    found.add(str(path.relative_to(root)))
        assert found == set(self.CSV_SOURCES), (
            f'CSV ureten dosya listesi degisti: {found ^ set(self.CSV_SOURCES)}')
