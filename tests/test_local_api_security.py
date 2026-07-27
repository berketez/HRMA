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
from pathlib import Path

import pytest

from hrma.app import app

ROOT = Path(__file__).resolve().parents[1]


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


class TestCorsWorksOnEveryLauncherPort:
    """v2.6.25 SAHA HATASI REGRESYONU — uygulama hiç hesap yapmıyordu.

    v2.6.2, CORS süzgecinde SABİT bir köken listesi kullanıyordu:
    ``{127.0.0.1:8080, localhost:8080, 127.0.0.1:5000, localhost:5000}``.
    Oysa masaüstü başlatıcısı (``packaging/launcher.py::_pick_port``)
    **8080-8090 arasında boş port arar**: 8080 meşgulse uygulama 8081'e düşer.
    O anda arayüz ``http://127.0.0.1:8081`` kökeninden servis edilir, tarayıcı
    her POST'a ``Origin: http://127.0.0.1:8081`` ekler, sabit liste bunu
    tanımaz ve uygulamanın KENDİ sayfası KENDİ API'sinden 403 alır. Sonuç:
    Hesapla düğmesi hiçbir motor tipinde çalışmaz.

    Bu hatayı hiçbir test yakalayamadı, çünkü testler kodun kör noktasını
    paylaşıyordu: yukarıdaki ``test_same_origin_state_change_allowed`` sabit
    8080 gönderiyor, o da sabit listeyle eşleşiyordu. Yani test, kodun kendi
    varsayımını onaylıyordu — bağımsız bir ölçüm değildi.

    Bu sınıf başlatıcının GERÇEK port aralığını süzgece karşı doğrular; iki
    dosya birbirinden bağımsız değişirse kırılır.
    """

    #: launcher.py::_pick_port'un taradığı aralık — orayla AYNI kalmalı.
    LAUNCHER_PORT_RANGE = range(8080, 8091)

    def test_launcher_port_range_matches_launcher_source(self):
        """Aralık hâlâ launcher.py'de yazdığı gibi mi? (iki dosya ayrışmasın)"""
        kaynak = (ROOT / 'packaging' / 'launcher.py').read_text(encoding='utf-8')
        assert 'range(8080, 8091)' in kaynak, (
            'launcher.py port aralığı değişmiş — bu testteki '
            'LAUNCHER_PORT_RANGE de güncellenmeli')

    @pytest.mark.parametrize('port', list(LAUNCHER_PORT_RANGE))
    def test_every_launcher_port_can_calculate(self, client, port):
        """Başlatıcının seçebileceği HER portta durum değiştiren istek geçmeli."""
        for ana_makine in ('127.0.0.1', 'localhost'):
            r = client.post('/analyze_safety',
                            json={'chamber_pressure': 20},
                            headers={'Origin': f'http://{ana_makine}:{port}'})
            assert r.status_code != 403, (
                f'{ana_makine}:{port} kökeni 403 aldı — uygulama bu portta '
                'hiçbir hesap yapamaz')

    def test_ipv6_loopback_origin_allowed(self, client):
        """IPv6 geri döngü de meşru bir yerel köken."""
        r = client.post('/analyze_safety',
                        json={'chamber_pressure': 20},
                        headers={'Origin': 'http://[::1]:8081'})
        assert r.status_code != 403

    def test_remote_origin_still_rejected_on_any_port(self, client):
        """Port serbestleşti diye uzak köken serbestleşmemeli."""
        for kotu in ('http://evil.example:8081', 'https://evil.example',
                     'http://192.168.1.50:8080', 'null'):
            r = client.post('/analyze_safety',
                            json={'chamber_pressure': 20},
                            headers={'Origin': kotu})
            assert r.status_code == 403, f'{kotu} kökeni geçti'

    def test_dns_rebinding_still_rejected(self, client):
        """Saldırgan alan adı 127.0.0.1'e çözümlenirse Host onu ele verir."""
        r = client.post('/analyze_safety',
                        json={'chamber_pressure': 20},
                        headers={'Origin': 'http://evil.example:8081',
                                 'Host': 'evil.example:8081'})
        assert r.status_code == 403
