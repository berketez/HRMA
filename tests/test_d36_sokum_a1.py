# -*- coding: utf-8 -*-
"""ÖH D36 · söküm bekçisi — ``/simple`` ve ``/uzaytek`` TAMAMEN söküldü.

Berke kararı (23 Eylül 2026): "he sil onları yav tamamen yok et". UI yeniden
yapılandırma B1 kararları 2 (iki öksüz sayfa sökülür) ve 6 (tek marka HRMA,
tek tema). Menüden hiçbir bağlantısı olmayan iki sayfa — ``simple.html``
(725 satır, İngilizce) ve ``uzaytek.html`` (1467 satır, "UZAYTEK - Hibrit
Roket Motoru Analizi", açık tema) — 28 Ağustos'ta eklenen rotalarıyla,
yalnız onlara ait ``simple.*`` / ``uzt.*`` sözlük anahtarlarıyla (EN 295 +
TR 295) ve yalnız onların yüklediği ``oxidizer_reference_density.js`` ile
birlikte kaldırıldı.

Bu dosya sökümün GERİ GELMESİNİ yasaklar:

* iki yol canlı uygulamada 404 verir ve yönlendirme tablosunda kural yoktur;
* iki şablon dosyası diskte yoktur;
* ``app.py`` içinde bu iki şablonu basan ``render_template`` çağrısı yoktur
  (AST + düz metin; ``inspect.getsource`` KULLANILMAZ — birleşmelerde kayan
  kaynak satırı bekçiyi kör ediyordu, 14 Eyl fix-34b dersi);
* hiçbir sözlük ``simple.`` / ``uzt.`` önekli anahtar tanımlamaz;
* ``oxidizer_reference_density.js`` yoktur ve hiçbir şablon onu yüklemez.

Kanıt: ``docs/scofield/raw/OH/D36/sokum/a1/`` (once.json, sonra.json,
mutasyon.md — her iddia ters mutasyonla kırmızıya çevrildi).
"""
import ast
import os
import pathlib
import re

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SABLON = KOK / 'hrma' / 'templates'
JS = KOK / 'hrma' / 'static' / 'js'
APP_PY = KOK / 'hrma' / 'app.py'

SOKULEN_YOLLAR = ('/simple', '/uzaytek')
SOKULEN_SABLONLAR = ('simple.html', 'uzaytek.html')
SOKULEN_ONEKLER = ('simple.', 'uzt.')
SOKULEN_BETIK = 'oxidizer_reference_density.js'


@pytest.fixture(scope='module')
def uygulama():
    os.environ.setdefault('HRMA_HEADLESS', '1')
    from hrma.app import app
    app.config['TESTING'] = True
    return app


# ---------------------------------------------------------------------------
# 1. Rotalar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('yol', SOKULEN_YOLLAR)
def test_sokulen_yol_404(uygulama, yol):
    with uygulama.test_client() as c:
        r = c.get(yol)
    assert r.status_code == 404, (
        '%s yeniden servis ediliyor (HTTP %d) — sayfa Berke kararıyla '
        '23 Eylül 2026\'da söküldü (dalga36/sokum)' % (yol, r.status_code))


def test_yonlendirme_tablosunda_kural_yok(uygulama):
    kurallar = {str(k.rule) for k in uygulama.url_map.iter_rules()}
    geri = sorted(set(SOKULEN_YOLLAR) & kurallar)
    assert not geri, 'sökülen yol yönlendirme tablosuna geri geldi: %s' % geri
    # Ölçütün kör olmadığı: canlı sayfa rotaları tabloda duruyor.
    assert {'/', '/hybrid', '/solid', '/liquid'} <= kurallar


# ---------------------------------------------------------------------------
# 2. Şablon dosyaları ve app.py çağrıları
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ad', SOKULEN_SABLONLAR)
def test_sablon_dosyasi_yok(ad):
    assert not (SABLON / ad).exists(), (
        '%s diskte yeniden var — söküm geri alınmış' % ad)


def _render_template_sabitleri():
    """``app.py`` AST'sinde ``render_template('<sabit>')`` ilk argümanları."""
    agac = ast.parse(APP_PY.read_text(encoding='utf-8'))
    out = []
    for dugum in ast.walk(agac):
        if (isinstance(dugum, ast.Call)
                and getattr(dugum.func, 'id', getattr(dugum.func, 'attr', None))
                == 'render_template'
                and dugum.args and isinstance(dugum.args[0], ast.Constant)):
            out.append(dugum.args[0].value)
    return out


def test_app_py_sokulen_sablonu_basmiyor():
    sabitler = _render_template_sabitleri()
    # Ölçütün kör olmadığı: canlı sayfaların çağrıları bulunuyor.
    assert {'advanced.html', 'solid.html', 'liquid.html'} <= set(sabitler), (
        'AST taraması render_template çağrılarını bulamıyor — ölçüt kırık')
    geri = sorted(set(SOKULEN_SABLONLAR) & set(sabitler))
    assert not geri, 'app.py sökülen şablonu yeniden basıyor: %s' % geri
    metin = APP_PY.read_text(encoding='utf-8')
    duz = re.findall(r"""render_template\(\s*['"](simple|uzaytek)\.html""",
                     metin)
    assert not duz, 'app.py metninde render_template(%s.html) var' % duz


# ---------------------------------------------------------------------------
# 3. Sözlük anahtarları
# ---------------------------------------------------------------------------
_ANAHTAR_TANIMI = re.compile(
    r"""^\s*(['"])((?:simple|uzt)\.[^'"]+)\1\s*:""", re.M)


def test_i18n_pages_sokulen_onekli_anahtar_tasimiyor():
    metin = (JS / 'i18n_pages.js').read_text(encoding='utf-8')
    kalan = sorted({m.group(2) for m in _ANAHTAR_TANIMI.finditer(metin)})
    assert not kalan, (
        'i18n_pages.js sökülen sayfaların anahtarlarını yeniden taşıyor '
        '(%d): %s' % (len(kalan), kalan[:10]))
    # Ölçütün kör olmadığı: aynı desen kalan sayfaların anahtarını yakalar.
    assert re.search(r"""^\s*'solid\.[^']+'\s*:""", metin, re.M)


def test_hicbir_sozluk_sokulen_onekli_anahtar_tanimlamiyor():
    ihlal = []
    for yol in sorted(JS.rglob('*.js')):
        metin = yol.read_text(encoding='utf-8', errors='replace')
        for m in _ANAHTAR_TANIMI.finditer(metin):
            ihlal.append('%s: %s' % (yol.relative_to(KOK), m.group(2)))
    assert not ihlal, 'sökülen önekli anahtar tanımı: %s' % ihlal[:10]


# ---------------------------------------------------------------------------
# 4. Yalnız iki sayfanın yüklediği betik
# ---------------------------------------------------------------------------
def test_oksitleyici_referans_betigi_yok():
    assert not (JS / SOKULEN_BETIK).exists(), (
        '%s yeniden var — tüketicisi olan iki sayfa söküldü' % SOKULEN_BETIK)


def test_hicbir_sablon_oksitleyici_referans_betigini_yuklemiyor():
    yukleyen = sorted(p.name for p in SABLON.glob('*.html')
                      if SOKULEN_BETIK in p.read_text(encoding='utf-8'))
    assert not yukleyen, (
        '%s şablon tarafından yükleniyor ama dosya söküldü (404): %s'
        % (SOKULEN_BETIK, yukleyen))
