"""V301/UÇUŞ C-1 — kullanıcı yolculuğu: sayfanın son hesabı ⟷ kayıtlı proje aracı.

Gerçek tarayıcıda (Chromium, WebGL KAPALI) üç örnek motor sayfası açılır,
Hesapla'ya basılır ve:

  * ``son hesap``  : FlightHandoff'un localStorage'a yazdığı araç (Fırlatma
                     Sahası "Son hesaplanan motor" kaynağı),
  * ``kaydedilen`` : proje şeridinin kaydettiği belge (HRMAProjectBar.
                     _buildPayload — kullanıcının "Kaydet"i) depoya yazılır ve
                     ``/api/flight-vehicle`` source='project' ile uçurulur,
  * ``örnek dosya``: aynı uç, paketle gelen örnek dosyanın kendisiyle.

Sözleşme (UCUS.md C-1): ikisi de son hesapla BİT-AYNI araç (itki, süre,
itici, atıl kütle, dış çap, boy, itki eğrisi).

ÖLÇÜLDÜ (27 Eki, ``docs/scofield/raw/OH/V301/ucus/c1_sayfa_once.json`` ve
``c1_ornek_duyarlilik_*.json``): kaydedilen proje üç tipte de bit-aynı. Örnek
DOSYA ise katı ve sıvıda sayfanın gönderdiği beş alanı taşımıyor (katı:
``convergent_angle``, ``discharge_coeff``, ``insulation_thickness``; sıvı:
``oxidizer_density`` (sayfa 1141,16 kg/m³ hesaplıyor, dosya 1141),
``oxidizer_viscosity``) ve bu alanlar aracı değiştiriyor: katı atıl 3,0898 ⟷
3,7344 kg, çap 83 ⟷ 89 mm, boy 0,5684 ⟷ 0,5472 m; sıvı atıl 71,1739 ⟷
71,1721 kg. Örnek dosyaları ana model üretir (``examples/generate_examples.py``;
UÇUŞ RAPOR DEVİR 1) — o düğüm örnekler yeniden üretilene dek KIRMIZIDIR ve
kırmızılığı gizlenmez.
"""

import importlib.util
import json
import pathlib
import shutil
import urllib.parse
import urllib.request

import pytest

from tests.test_example_projects import EXAMPLES_DIR, NAMES

KOK = pathlib.Path(__file__).resolve().parents[1]

#: motor tipi -> (sayfa yolu, hesap ucu, hesap çağrısı)
YOLCULUK_SAYFALARI = {
    'hybrid': ('/hybrid', '/calculate', 'calculate()'),
    'solid': ('/solid', '/calculate_solid', 'calculateSolid()'),
    'liquid': ('/liquid', '/calculate_liquid', 'calculateLiquid()'),
}
#: Karşılaştırılan araç alanları (C-1 bekçisiyle aynı küme).
YOLCULUK_ARAC_ALANLARI = ('thrust', 'burn_time', 'propellant_mass',
                          'engine_inert_mass', 'engine_od_m',
                          'engine_length_m', 'thrust_curve')
YOLCULUK_CHROME = pathlib.Path(
    '/Users/apple/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/'
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')


@pytest.fixture(scope='module')
def sunucu(tmp_path_factory):
    if importlib.util.find_spec('playwright') is None:
        pytest.skip('playwright paketi yok: tarayıcı yolculuğu ölçülemez')
    if not YOLCULUK_CHROME.exists():
        pytest.skip(f'Chromium yok: {YOLCULUK_CHROME}')
    depo = tmp_path_factory.mktemp('ucus_projeler')
    for ad in NAMES.values():
        shutil.copy(EXAMPLES_DIR / (ad + '.hrma'), depo / (ad + '.hrma'))
    import os
    eski = os.environ.get('HRMA_PROJECTS_DIR')
    os.environ['HRMA_PROJECTS_DIR'] = str(depo)
    from tools.browser_harness.sunucu import UygulamaSunucusu
    s = UygulamaSunucusu(gunluk_yolu=str(depo / 'sunucu.log'))
    try:
        s.baslat()
        yield s.temel_url
    finally:
        s.durdur()
        if eski is None:
            os.environ.pop('HRMA_PROJECTS_DIR', None)
        else:
            os.environ['HRMA_PROJECTS_DIR'] = eski


def _post(url, govde):
    istek = urllib.request.Request(
        url, data=json.dumps(govde).encode(), method='POST',
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(istek, timeout=120) as y:
            return y.status, json.loads(y.read())
    except urllib.error.HTTPError as h:
        return h.code, json.loads(h.read() or b'{}')


@pytest.fixture(scope='module')
def yolculuk(sunucu):
    """Her motor tipi için: son hesap aracı + kaydedilen belge."""
    from playwright.sync_api import sync_playwright
    sonuc = {}
    with sync_playwright() as p:
        tarayici = p.chromium.launch(
            executable_path=str(YOLCULUK_CHROME), headless=True,
            args=['--disable-3d-apis', '--disable-gpu', '--use-gl=disabled'])
        try:
            for mt, (yol, uc, cagri) in YOLCULUK_SAYFALARI.items():
                ad = NAMES[mt]
                s = tarayici.new_page(viewport={'width': 1440, 'height': 900})
                s.set_default_timeout(30000)
                s.goto(sunucu + yol + '?project=' + urllib.parse.quote(ad),
                       wait_until='networkidle')
                s.wait_for_function(
                    'window.HRMAProjectBar && HRMAProjectBar._state && '
                    'HRMAProjectBar._state.name === ' + json.dumps(ad))
                s.wait_for_timeout(800)
                s.evaluate("localStorage.removeItem('hrma.flight.lastVehicle')")
                with s.expect_response(lambda r, uc=uc: r.url.endswith(uc)
                                       and r.request.method == 'POST',
                                       timeout=120000):
                    s.evaluate(cagri)
                s.wait_for_function(
                    "localStorage.getItem('hrma.flight.lastVehicle')",
                    timeout=60000)
                arac = json.loads(s.evaluate(
                    "localStorage.getItem('hrma.flight.lastVehicle')"))['vehicle']
                kayit = s.evaluate('HRMAProjectBar._buildPayload('
                                   + json.dumps(ad + ' kayit') + ')')
                sonuc[mt] = {'son_hesap': arac, 'kayit': kayit}
                s.close()
        finally:
            tarayici.close()
    return sonuc


def _ayrisan(a, b):
    return [f'{k}: proje {a.get(k)!r} ⟷ son hesap {b.get(k)!r}'
            for k in YOLCULUK_ARAC_ALANLARI if a.get(k) != b.get(k)]


# kabul_ui: yerel Mac Chromium'una bağlı tarayıcı düğümü — Linux CI'da
# SEÇİLMEZ (tests.yml -m "not kabul_ui"); packaging/release_gate.sh 5/10
# yerelde koşar (28 Eki, v3.0.5).
@pytest.mark.kabul_ui
@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_kullanicinin_kaydettigi_proje_son_hesapla_bit_ayni(sunucu, yolculuk,
                                                            motor_type):
    """Kullanıcı Hesapla -> Kaydet -> Fırlatma Sahası: aynı motor uçar."""
    kayit = yolculuk[motor_type]['kayit']
    ad = kayit['name']
    d, g = _post(sunucu + '/api/projects/save',
                 {'name': ad, 'payload': kayit, 'overwrite': True})
    assert d == 200, g
    d, g = _post(sunucu + '/api/flight-vehicle',
                 {'source': 'project', 'name': ad})
    assert d == 200, g
    ayrisan = _ayrisan(g['vehicle'], yolculuk[motor_type]['son_hesap'])
    assert not ayrisan, '\n  '.join([motor_type + ':'] + ayrisan)


@pytest.mark.kabul_ui
@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_ornek_dosya_sayfanin_ucurdugu_motoru_tasir(sunucu, yolculuk,
                                                     motor_type):
    """Örnek DOSYA kayıtlı proje olarak seçilince de aynı motor uçar.

    Kırmızıysa kök ürün kodu değil örnek dosyadır: sayfa dosyada olmayan
    alanları şablon varsayılanıyla gönderiyor (modül belgesi). Onarım:
    örnekleri sayfanın kaydettiği tam alan kümesiyle yeniden üretmek.
    """
    d, g = _post(sunucu + '/api/flight-vehicle',
                 {'source': 'project', 'name': NAMES[motor_type]})
    assert d == 200, g
    ayrisan = _ayrisan(g['vehicle'], yolculuk[motor_type]['son_hesap'])
    assert not ayrisan, '\n  '.join(
        [motor_type + ' örnek dosyası sayfanın gönderdiği alanları taşımıyor '
         '(DEVİR: examples/generate_examples.py):'] + ayrisan)
