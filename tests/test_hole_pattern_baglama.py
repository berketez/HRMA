"""hole_pattern bağlaması — "kanal var kapı yok" kapanışının bekçileri.

Ölçülen kusur (14 Ağustos 2026): advanced.html'de desen seçicisi
(#hole_pattern) ve çizicide destek (visualization.py:4399,
SHOWERHEAD_PATTERNS doğrulamalı) VARDI ama seçim ne istek gövdesine
konuyor ne app.py tarafından okunuyordu — kullanıcının seçimi hiçbir
şeyi değiştirmiyordu.

Bağlama üç halka: form toplayıcısı (advanced.html) → istek sınırı
doğrulaması (app.py, geçersiz desene 400) → injector_results üzerinden
çizici. Desen yalnız plaka/CAD yerleşimini etkiler; performans modeli
yoktur ve arayüzdeki 'no_model' beyanı doğru kalmaya devam eder.
"""

import re
from pathlib import Path

import pytest

from tests.test_field_wiring_layer_b import HYBRID_BASE

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


def _hesapla(client, **overrides):
    return client.post('/calculate', json=dict(HYBRID_BASE, **overrides))


def test_gecerli_desen_yanita_ulasir(client):
    """hexagonal gönderilince injector_design bloğu deseni taşımalı.

    Bu, zincirin uçtan uca kanıtıdır: istek → app.py doğrulaması →
    injector_results → yanıt. Bağlama geri alınırsa (app.py istekten
    okumayı bırakırsa) bu test kırılır.
    """
    r = _hesapla(client, hole_pattern='hexagonal', include_plots=False)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    govde = r.get_json()
    # Yanıtta injector.calculate() sonuçları 'injector' anahtarında yaşar
    # (app.py ~:1885); 'injector_design' ise motorun kendi bloğudur.
    inj = govde.get('injector') or {}
    assert inj.get('hole_pattern') == 'hexagonal', (
        'hole_pattern isteği yanıttaki injector bloğuna ulaşmıyor — '
        'bağlama kopmuş.')


def test_gecersiz_desen_400_doner(client):
    """Sözlük dışı desen sessizce yutulmaz: 400 + adlandırılmış hata.

    Sessiz-200 kapısı deseniyle tutarlılık — geçersiz girdiye "başarı"
    döndürmek uydurmanın kapısıdır.
    """
    r = _hesapla(client, hole_pattern='fibonacci_spiral', include_plots=False)
    assert r.status_code == 400
    govde = r.get_json()
    assert govde.get('error') == 'invalid_hole_pattern'
    assert 'circular' in govde.get('message', '')


def test_desen_verilmeyince_davranis_degismez(client):
    """hole_pattern göndermeyen istek eskisi gibi çalışır; alan dayatılmaz.

    Çizici kendi varsayılanını (circular) kullanır; app.py yokluğu bir
    değere ÇEVİRMEZ (uydurma varsayılan basılmaz).
    """
    r = _hesapla(client, include_plots=False)
    assert r.status_code == 200
    inj = (r.get_json().get('injector') or {})
    assert 'hole_pattern' not in inj or inj.get('hole_pattern') in (
        'circular', 'hexagonal', 'square')


def test_form_toplayicisi_deseni_gonderiyor():
    """advanced.html payload toplayıcısı hole_pattern'ı içermeli.

    v2.6.26'da üç alan aynı sebepten ölüydü (toplayıcıya konmamıştı);
    aynı kusurun geri gelmemesi için kaynak-seviyesi kilit. Yorumda geçen
    metinle tatmin olmamak için gerçek kod satırı aranır.
    """
    html = (ROOT / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    assert re.search(
        r"^\s*if \(holePattern\) data\.hole_pattern = holePattern;",
        html, re.M), 'payload toplayıcısında hole_pattern satırı yok'


def test_app_dogrulamasi_tek_kaynaktan():
    """app.py desen listesini KOPYALAMAZ; SHOWERHEAD_PATTERNS import eder.

    Parametre tutarlılığı kuralı: çizicinin tanıdığı desen kümesi tek
    doğruluk kaynağıdır. app.py'de sabit desen listesi belirirse bu test
    kırılır (iki listenin sessizce ayrışması engellenir).
    """
    kaynak = (ROOT / 'hrma' / 'app.py').read_text(encoding='utf-8')
    assert 'SHOWERHEAD_PATTERNS' in kaynak
    govde = kaynak[kaynak.index('def calculate('):]
    blok = govde[:govde.index('def calculate_solid(')]
    assert re.search(r"if _hp not in SHOWERHEAD_PATTERNS", blok), (
        'app.py doğrulaması SHOWERHEAD_PATTERNS üzerinden yapılmıyor')
    assert not re.search(
        r"\(\s*'circular'\s*,\s*'hexagonal'", blok), (
        'app.py desen listesini kopyalamış — tek kaynak ihlali')
