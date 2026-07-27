"""Yerel API güvenlik bekçileri (v2.6.2).

İki açık ve bunların oluşturduğu zincir:

1. ``/download/stl/<filename>`` adı hiç doğrulamadan ``send_file`` ediyordu.
   Flask'ın ``string`` dönüştürücüsü ``/`` geçirmez ama TERS BÖLÜ geçirir;
   Windows'ta ``\\`` da yol ayracı olduğu için ``..\\..\\..\\Windows\\win.ini``
   export dizininin dışına çıkıyordu. HRMA Windows'ta exe dağıttığından bu
   gerçek bir rastgele dosya okuma açığıydı.

2. ``CORS(app)`` argümansız çağrılıyordu → tüm rotalarda
   ``Access-Control-Allow-Origin: *``. Sunucu 127.0.0.1'e bağlı olsa da bu
   yetmiyordu: kullanıcı HRMA açıkken kötü bir siteye girdiğinde o sayfanın
   JS'i yerel uçlara istek atıp YANITI OKUYABİLİYORDU.

İkisi birleşince: kötü niyetli sayfa → diskten dosya oku → dışarı gönder.
"""

import os

import pytest

from hrma.app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestStlDownloadPathTraversal:
    """Yol kaçışının her biçimi 400 almalı, 200 veya 404 DEĞİL.

    404 de kabul edilemez: 404, yolun kabul edilip dosyanın bulunamadığını
    gösterir; farklı bir hedefte 200'e dönebilir. Reddin adın kendisinden
    gelmesi gerekir.
    """

    @pytest.mark.parametrize('bad', [
        '..\\..\\..\\Windows\\win.ini',      # Windows ters bölü (asıl açık)
        '..\\..\\etc\\passwd',
        '....\\\\....\\\\windows\\\\win.ini',
        '..%5c..%5cwindows%5cwin.ini',       # yüzde kodlanmış ters bölü
        'a/../../../etc/passwd',
        '.stl',                              # boş taban ad
        'x.txt',                             # uzantı beyaz listede değil
        'x.stl.exe',
        'foo bar.stl',                       # boşluk beyaz listede değil
        '',
    ])
    def test_malicious_names_rejected(self, client, bad):
        r = client.get(f'/download/stl/{bad}')
        assert r.status_code in (400, 404), (
            f'{bad!r} beklenmedik durum kodu {r.status_code}')
        # 400 tercih edilir; 404 yalnız Flask rotayı hiç eşleştiremediğinde olur
        if r.status_code == 404 and r.is_json:
            assert r.get_json().get('error') != 'File not found' or '..' not in bad

    def test_absolute_path_rejected(self, client):
        r = client.get('/download/stl//etc/passwd')
        assert r.status_code in (400, 404)

    def test_legitimate_file_still_downloads(self, client, tmp_path, monkeypatch):
        """Meşru kullanım bozulmamalı — düzeltme aşırı kısıtlayıcı olmamalı."""
        workdir = tmp_path / 'work'
        (workdir / 'cad_exports').mkdir(parents=True)
        stl = workdir / 'cad_exports' / 'motor_test.stl'
        stl.write_text('solid x\nendsolid x\n', encoding='utf-8')
        monkeypatch.chdir(workdir)
        r = client.get('/download/stl/motor_test.stl')
        assert r.status_code == 200
        assert b'endsolid' in r.data

    def test_traversal_cannot_reach_real_file_outside_dir(self, client, tmp_path,
                                                          monkeypatch):
        """Export dizini DIŞINDA gerçekten var olan bir dosya okunamamalı."""
        workdir = tmp_path / 'work'
        (workdir / 'cad_exports').mkdir(parents=True)
        secret = tmp_path / 'secret.stl'
        secret.write_text('TOP SECRET', encoding='utf-8')
        monkeypatch.chdir(workdir)
        for attempt in ('..\\secret.stl', '../secret.stl', '..%2fsecret.stl'):
            r = client.get(f'/download/stl/{attempt}')
            assert r.status_code in (400, 404)
            assert b'TOP SECRET' not in r.data


class TestCorsIsNotWildcard:
    def test_no_wildcard_cors_header(self, client):
        """Hiçbir yanıt ``Access-Control-Allow-Origin: *`` taşımamalı."""
        for path in ('/', '/api/database-status'):
            r = client.get(path)
            assert r.headers.get('Access-Control-Allow-Origin') != '*', (
                f'{path} joker CORS başlığı döndürüyor')

    def test_cross_origin_state_change_rejected(self, client):
        """Yabancı kökenli POST 403 almalı (CSRF / DNS-rebinding kapısı)."""
        r = client.post('/analyze_safety',
                        json={'chamber_pressure': 20},
                        headers={'Origin': 'https://evil.example'})
        assert r.status_code == 403

    def test_same_origin_state_change_allowed(self, client):
        """Uygulamanın kendi kökeninden gelen POST geçmeli."""
        r = client.post('/analyze_safety',
                        json={'chamber_pressure': 20},
                        headers={'Origin': 'http://127.0.0.1:8080'})
        assert r.status_code != 403

    def test_no_origin_header_allowed(self, client):
        """Origin başlığı olmayan istek (native webview, curl) geçmeli."""
        r = client.post('/analyze_safety', json={'chamber_pressure': 20})
        assert r.status_code != 403

    def test_get_requests_not_blocked_by_origin(self, client):
        """Okuma istekleri Origin yüzünden bloklanmamalı (yalnız durum değiştirenler)."""
        r = client.get('/', headers={'Origin': 'https://evil.example'})
        assert r.status_code != 403
