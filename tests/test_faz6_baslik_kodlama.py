"""Faz 6 / T54-ek — HTTP başlıklarına latin-1 dışı karakter sızmasın.

Arıza sınıfı (3 Ağustos 2026'da karo ucunda ölçüldü): bir yanıt başlığına
veriden gelen düz yazı konuyordu ("NASA GIBS — Blue Marble ...").  HTTP başlık
satırları latin-1 ile kodlanır; em-dash (U+2014) latin-1'de yoktur.  werkzeug
durum satırını yazdıktan SONRA ``send_header`` içinde ``UnicodeEncodeError``
atıyor — yani:

* sunucu günlüğüne "200" düşüyor (yanıltıcı),
* istemciye TEK BAYT gitmiyor (``curl`` exit 28, 0 bayt, zaman aşımı),
* karo diske yazıldığı için önbellek büyüyor, "çalışıyor" izlenimi veriyor,
* tarayıcıda host başına 6 bağlantı asılı kalınca sayfanın tüm ağı kilitleniyor.

Bu yüzden bekçi tek bir uca değil, **veriden başlık üreten her uca** bakar.
"""

import re

import pytest

from hrma.app import app


# Değeri veriden türeyebilecek uçlar. Karo ucu arızanın çıktığı yerdi; diğerleri
# aynı kalıbın tekrar edebileceği yerler.
UCLAR = [
    '/api/tile/bluemarble/2/1/1',
    '/api/tile/cache/status',
    '/launch-site',
    '/',
]


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _latin1_disi(deger):
    """Değerin latin-1'e kodlanamayan karakterlerini döndürür."""
    kotu = []
    for ch in deger:
        try:
            ch.encode('latin-1', 'strict')
        except UnicodeEncodeError:
            kotu.append(ch)
    return kotu


@pytest.mark.parametrize('yol', UCLAR)
def test_baslik_degerleri_latin1_kodlanabilir(istemci, yol):
    """Hiçbir yanıt başlığı latin-1 dışı karakter taşımamalı.

    Taşırsa gerçek sunucu (werkzeug) yanıtı başlıklardan sonra düşürür; test
    istemcisi bu kodlamayı yapmadığı için arıza ancak böyle yakalanır.
    """
    yanit = istemci.get(yol)
    for ad, deger in yanit.headers.items():
        kotu = _latin1_disi(str(deger))
        assert not kotu, (
            "%s -> '%s' başlığı latin-1 dışı karakter taşıyor: %r. "
            "Gerçek sunucuda bu yanıt istemciye HİÇ ulaşmaz (werkzeug "
            "send_header UnicodeEncodeError atar). Düz yazıyı başlığa değil "
            "JSON gövdesine koyun." % (yol, ad, kotu))


def test_karo_ucu_govde_donduruyor(istemci):
    """Karo ucu gerçekten bayt döndürmeli — 200 demek yetmez.

    Arıza sırasında durum 200 görünüyordu ama gövde istemciye ulaşmıyordu.
    """
    yanit = istemci.get('/api/tile/bluemarble/2/1/1')
    if yanit.status_code != 200:
        pytest.skip('karo indirilemedi (ağ yok veya önbellek boş): %s'
                    % yanit.status_code)
    assert len(yanit.data) > 0, 'karo ucu 200 dedi ama gövde boş'


def test_atif_metni_govdede_yayimlaniyor(istemci):
    """Başlıktan kaldırılan atıf, JSON gövdesinde yayımlanmaya devam etmeli.

    Atıf NASA GIBS kullanım şartı; kaldırılırsa yerine başka bir kanal
    konmalıydı. Bu test o kanalın açık kaldığını kilitler.
    """
    yanit = istemci.get('/api/tile/cache/status')
    assert yanit.status_code == 200
    veri = yanit.get_json()
    katmanlar = (veri.get('layers') or {}).get('layers') or {}
    assert katmanlar, 'cache/status katman listesi boş'
    for ad, cfg in katmanlar.items():
        atif = cfg.get('attribution') or ''
        assert 'NASA GIBS' in atif, (
            "'%s' katmanının atfı gövdede yok: %r" % (ad, atif))


def test_baslikta_duz_yazi_basligi_geri_gelmemis():
    """``X-Tile-Attribution`` başlığı geri eklenmemeli.

    Kaynak taraması: kod değiştiğinde çalışma zamanı testi ağ gerektirebilir,
    bu bekçi ağsız da düşer.
    """
    import inspect

    import hrma.app as modul

    kaynak = inspect.getsource(modul)
    assert not re.search(r"headers\[\s*['\"]X-Tile-Attribution['\"]\s*\]", kaynak), (
        "X-Tile-Attribution başlığı geri eklenmiş. Atıf metni em-dash içeriyor "
        "ve HTTP başlıkları latin-1 kodlanıyor; bu başlık karo ucunu tamamen "
        "öldürür. Atıf /api/tile/cache/status gövdesinde yayımlanır.")
