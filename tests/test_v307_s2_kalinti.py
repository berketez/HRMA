"""V307/S2-KALINTI — 3.0.6 son kullanıcı turunun (NK3, 9 Kas) kalan işlev
hataları.

Kalem 1 (NK3-H-3): hibrit sayfada Yörünge hesaplandıktan sonra her Hesapla'da
    kırmızı "Promise hatası: TypeError … '_redrawFromAutoMarginCount'"
    çıkıyordu. Kök: /calculate yörüngeyi AYNI yanıtta çiziyor (Plotly.newPlot
    asenkron sürerken) ve advanced.html'deki bayat grafik sarmalayıcısı aynı
    div'i Plotly.purge ediyordu; yeni motorun yörüngesi de "önceki yörünge
    temizlendi" diye siliniyordu. Onarım: grafiği bu yanıt çizdiyse grafik bu
    hesabındır (sahip güncellenir, purge yok); temizlik yalnız yörünge
    çizmeyen yanıtta — tarayıcı.
Kalem 2 (NK3-H-6): gaz N₂O beslemede motor "delik planı verilmiyor" derken
    enjektör bloğu (hrma/utils/injector_design.py) sıvı yoğunluğu + SPI ile
    delik planı, ΔP (otomatik %20·Pc = "şu an 1,70 bar") ve ona bağlı dört
    uyarı yayımlıyordu. Onarım: sıvı olmayan fazda blok boyutlandırmaz
    (``status: not_analyzed``, kod ``gas_phase_feed_not_modelled``, neden
    motorun tek cümlesi), ekran sayı satırı açmaz.

Kanıt, önce/sonra ölçümleri ve ters mutasyonlar:
docs/scofield/raw/OH/V307/s2-kalinti/RAPOR.md.
"""
import contextlib
import io
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates'

PORT = int(os.environ.get('S2K_PORT', '8918'))
URL = 'http://127.0.0.1:%d' % PORT
CALISMA = pathlib.Path(os.environ.get(
    'S2K_CALISMA', str(pathlib.Path.home() / 'HRMA-calisma' / 's2-kalinti-bekci')))
CHROME_1208 = ('/Users/apple/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/'
               'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')

#: Carmicino 2013 t01 (NK3-H-6 adımları): gaz N2O, kullanıcı tankı 16 bar.
CARMICINO = dict(chamber_pressure=8.52, of_ratio=3.9, combustion_efficiency=79,
                 thrust=72.7, burn_time=11, total_impulse=799.7,
                 initial_port_diameter=0.0117, tank_pressure_source='user',
                 tank_pressure=16, calculate_trajectory=False)


def _oku(yol):
    return pathlib.Path(yol).read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, uc, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        return istemci.post(uc, json=govde)


def _hibrit_govde(**ek):
    from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI
    g = dict(SAYFA_YUKLERI['hybrid'])
    g.update(ek)
    return g


# ---------------------------------------------------------------------------
# Tarayıcı düzeneği (port doluysa kulvarın sunucusu; boşsa açar)
# ---------------------------------------------------------------------------
def _hazir_mi(url):
    try:
        with urllib.request.urlopen(url + '/hybrid', timeout=2) as r:
            return r.status == 200
    except Exception:   # noqa: BLE001
        return False


@pytest.fixture(scope='module')
def sunucu():
    if _hazir_mi(URL):
        yield URL
        return
    depo = CALISMA / ('projeler-%d' % os.getpid())
    depo.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HRMA_PORT=str(PORT), BROWSER='echo',
               HRMA_PROJECTS_DIR=str(depo), PYTHONDONTWRITEBYTECODE='1')
    for k in ('OMP_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS',
              'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        env.setdefault(k, '2')
    env.setdefault('MPLBACKEND', 'Agg')
    # 3.0.7 birleşmesi (ana model): sunucu PYTEST_CURRENT_TEST görürse örnek
    # projeleri tohumlamaz (kullanıcının gerçek dizinini koruyan kanca,
    # app._seed_examples_once). Bu sunucunun proje dizini YALITILMIŞ (depo),
    # tohumlama güvenli; değişken alt sürece geçirilmez. Yoksa örnek proje 404
    # verir ve test yalnız dışarıda tohumlu bir sunucu açıkken geçer.
    env.pop('PYTEST_CURRENT_TEST', None)
    gunluk = open(CALISMA / ('sunucu-%d.log' % PORT), 'w')
    proc = subprocess.Popen([sys.executable, '-m', 'hrma.run'], cwd=str(KOK),
                            env=env, stdout=gunluk, stderr=subprocess.STDOUT)
    try:
        bitis = time.time() + 90
        while time.time() < bitis and not _hazir_mi(URL):
            assert proc.poll() is None, 'sunucu açılırken düştü: ' + gunluk.name
            time.sleep(0.5)
        assert _hazir_mi(URL), 'sunucu 90 s içinde yanıt vermedi'
        yield URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        gunluk.close()


@pytest.fixture(scope='module')
def tarayici():
    pw = pytest.importorskip('playwright.sync_api')
    from tests.test_v301_kabul_ui import KABUL_CHROME_YOLU, ARGS
    yol = next((y for y in (CHROME_1208, KABUL_CHROME_YOLU) if pathlib.Path(y).exists()), None)
    if yol is None:
        pytest.skip('chromium yok')
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=yol, args=ARGS)
        try:
            yield b
        finally:
            b.close()


#: Sayfanın unhandledrejection ve ileti kutusunu kayıt altına alan gözlemci
#: (ileti 5 s sonra kaybolur; gözlemci girişini yakalar).
_GOZLEMCI = r"""
window.__s2 = {iletiler: [], redler: []};
window.addEventListener('unhandledrejection', function (e) {
  var r = e && e.reason; window.__s2.redler.push(String(r && r.stack ? r.stack : r));
});
document.addEventListener('DOMContentLoaded', function () {
  var m = document.getElementById('messages');
  if (!m) return;
  new MutationObserver(function () {
    var t = m.innerText.trim(); if (t) window.__s2.iletiler.push(t);
  }).observe(m, {childList: true, subtree: true, characterData: true});
});
"""


def _sayfa(tarayici, sunucu, yol, dil='tr'):
    ctx = tarayici.new_context(viewport={'width': 1440, 'height': 1000})
    ctx.add_init_script("try{localStorage.setItem('hrma_lang','%s')}catch(e){}" % dil)
    ctx.add_init_script(_GOZLEMCI)
    s = ctx.new_page()
    s.set_default_timeout(30000)
    s.goto(sunucu + yol, wait_until='networkidle')
    return s


def _hibrit_hesapla(s):
    s.evaluate('() => { window.__s2h = window.currentResults || null; }')
    s.evaluate('() => { calculate(); }')
    s.wait_for_function('() => window.currentResults && window.currentResults !== window.__s2h',
                        timeout=180000)
    s.wait_for_function("() => getComputedStyle(document.getElementById('loading')).display === 'none'",
                        timeout=180000)
    s.wait_for_timeout(2500)     # Plotly'nin asenkron adımları + rejection


def _alan(s, kimlik, deger):
    s.evaluate("""([k, v]) => { const e = document.getElementById(k); e.value = v;
        e.dispatchEvent(new Event('input', {bubbles: true}));
        e.dispatchEvent(new Event('change', {bubbles: true})); }""", [kimlik, deger])


def _yorunge_cizili(s):
    return s.evaluate("() => !!(document.getElementById('trajectory_plot') || {}).data")


# ---------------------------------------------------------------------------
# Kalem 1 — NK3-H-3
# ---------------------------------------------------------------------------
def test_K1_sarmalayici_ciziminde_purge_yok_tek_kosul():
    """Statik: bayat-grafik sarmalayıcısı yanıtın çizip çizmediğini
    displayPlots ile AYNI işlevden okur; koşulsuz temizlik çağrısı yok."""
    sablon = _oku(SABLON / 'advanced.html')
    app_js = _oku(JS / 'app.js')
    assert 'function yanitYorungeyiCizer(plots)' in app_js
    assert "if (yanitYorungeyiCizer(plots)) {\n        safePlotCreate('trajectory_plot'" in app_js
    blok = sablon[sablon.index('window.displayCalculationResults = function (results) {\n'
                               '                var cikti = ozgun.apply'):]
    blok = blok[:blok.index('return cikti;')]
    assert 'trajCizimSahibiniKur(results);' in blok
    assert 'trajBayatCizimiTemizle();' not in blok
    sahip = sablon[sablon.index('function trajCizimSahibiniKur(results)'):]
    sahip = sahip[:sahip.index('function trajAraciEsitle()')]
    assert 'yanitYorungeyiCizer(results.plots)' in sahip
    assert sahip.index('_hibYorungeCizimSonucu = results;') < sahip.index('trajBayatCizimiTemizle();')


def test_K1_yorungeden_sonra_hesapla_promise_hatasi_yok(tarayici, sunucu):
    s = _sayfa(tarayici, sunucu, '/hybrid')
    try:
        _hibrit_hesapla(s)
        assert _yorunge_cizili(s), 'ilk Hesapla yörüngeyi çizmeliydi (onay kutusu açık)'
        s.evaluate('() => calculateTrajectory()')
        s.wait_for_function("() => getComputedStyle(document.getElementById('loading')).display === 'none'",
                            timeout=180000)
        s.wait_for_timeout(1500)
        assert _yorunge_cizili(s)
        _alan(s, 'thrust', '2600')
        _alan(s, 'burn_time', '14.5')
        _alan(s, 'chamber_pressure', '25')
        s.evaluate('() => { window.__s2.iletiler = []; window.__s2.redler = []; }')
        _hibrit_hesapla(s)
        iz = s.evaluate('() => window.__s2')
        assert iz['redler'] == [], iz['redler']
        assert not [m for m in iz['iletiler'] if 'Promise' in m], iz['iletiler']
        # Yeni motorun yörüngesi bu yanıtla çizildi; "temizlendi" yazmaz.
        assert _yorunge_cizili(s)
        metin = s.inner_text('#trajectory_plot')
        assert 'temizlendi' not in metin and 'was cleared' not in metin
        # İkinci kez (NK3: 2/2 yinelendi) — yine temiz.
        s.evaluate('() => { window.__s2.iletiler = []; window.__s2.redler = []; }')
        _hibrit_hesapla(s)
        assert s.evaluate('() => window.__s2.redler') == []
        assert _yorunge_cizili(s)
    finally:
        s.context.close()


def test_K1_yorunge_cizmeyen_hesapta_bayat_grafik_temizlenir(tarayici, sunucu):
    """Onay kutusu kapalıyken yanıt yörünge çizmez: eski grafik temizlenir,
    nedeni yazılır, yine Promise hatası yok (div'de bekleyen çizim yok)."""
    s = _sayfa(tarayici, sunucu, '/hybrid')
    try:
        _hibrit_hesapla(s)
        assert _yorunge_cizili(s)
        s.evaluate("() => { const c = document.getElementById('calculate_trajectory');"
                   " c.checked = false; c.dispatchEvent(new Event('change', {bubbles: true})); }")
        _alan(s, 'thrust', '1200')
        s.evaluate('() => { window.__s2.iletiler = []; window.__s2.redler = []; }')
        _hibrit_hesapla(s)
        assert s.evaluate('() => window.__s2.redler') == []
        assert not _yorunge_cizili(s)
        assert 'temizlendi' in s.inner_text('#trajectory_plot')
    finally:
        s.context.close()


# ---------------------------------------------------------------------------
# Kalem 2 — NK3-H-6
# ---------------------------------------------------------------------------
def _enjektor(faz, tip='showerhead', tank=16.0, pc=8.52):
    from hrma.utils.injector_design import InjectorDesign
    with contextlib.redirect_stdout(io.StringIO()):
        inj = InjectorDesign(mdot_ox=0.04, chamber_pressure=pc, oxidizer_phase=faz,
                             oxidizer_type='n2o', tank_pressure=tank,
                             oxidizer_temp=293.0, injector_type=tip)
        if tip == 'showerhead':
            inj.set_showerhead_params(target_velocity=30, plate_thickness=3.0)
        return inj.calculate()


def test_K2_gaz_fazda_enjektor_blogu_boyutlandirmaz():
    from hrma.engines.hybrid_rocket_engine import GAS_PHASE_FEED_NOT_MODELLED
    b = _enjektor('gas')
    assert b['status'] == 'not_analyzed'
    assert b['reason_code'] == 'gas_phase_feed_not_modelled'
    assert b['reason'] == GAS_PHASE_FEED_NOT_MODELLED          # tek cümle
    assert b['warnings'] == []
    for ad in ('n_holes', 'hole_diameter', 'exit_velocity', 'pressure_drop',
               'pressure_drop_bar', 'injection_area', 'reynolds_number',
               'pressure_drop_for_target_velocity_bar'):
        assert ad not in b, ad
    # Plaka kalınlığı (kullanıcı girdisi) künyesiyle kalır.
    assert b['plate_thickness'] == pytest.approx(3.0)
    assert b['plate_thickness_earned'] is True
    # Pintle da boyutlandırılmaz.
    assert _enjektor('gas', tip='pintle')['status'] == 'not_analyzed'


def test_K2_sivi_fazda_enjektor_blogu_aynen():
    b = _enjektor('liquid')
    assert b.get('status') is None and b['n_holes'] >= 1 and b['pressure_drop'] > 0


def test_K2_carmicino_gaz_yaniti_tek_hukum(istemci):
    r = _post(istemci, '/calculate', _hibrit_govde(oxidizer_phase='gas', **CARMICINO))
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    j = r.get_json()
    inj = j['injector']
    assert inj['status'] == 'not_analyzed'
    assert inj['reason_code'] == 'gas_phase_feed_not_modelled'
    assert 'n_holes' not in inj and 'pressure_drop' not in inj
    metin = ' '.join(str(w) for w in inj.get('warnings') or [])
    for parca in ('liquid-phase values', 'currently 1.70 bar', 'Exit velocity',
                  'Target injection velocity'):
        assert parca not in metin, parca
    kodlar = [w.get('code') for w in j['motor'].get('design_warnings') or []
              if isinstance(w, dict)]
    assert 'warn.hybrid.gas_phase_feed_not_modelled' in kodlar
    # Doğrulama ΔP/Pc hükmünü uydurmaz; plaka raporu da yükü bilinmeden vermez.
    assert j['validation']['injector_assessment']['pressure_drop_ratio']['status'] == 'not_evaluated'
    r2 = _post(istemci, '/calculate', _hibrit_govde(oxidizer_phase='gas',
                                                     injector_material='ss_316', **CARMICINO))
    ps = r2.get_json()['injector']['plate_structural']
    assert ps['status'] == 'not_analyzed' and ps['delta_P_source'] == 'unavailable'


def test_K2_ekran_sayi_satiri_acmaz_ceviri_var():
    app_js = _oku(JS / 'app.js')
    gov = app_js[app_js.index('function displayInjectorTable(injectorData, yalnizSatirlar) {'):]
    assert gov.index("if (injectorData.status === 'not_analyzed') {") < gov.index('const injectorRows = [')
    rapor = app_js[app_js.index('function displayDesignReport(motorData, injectorData) {'):]
    rapor = rapor[:rapor.index('displayInjectorTable(injectorData, true)')]
    assert "if (!(injectorData && injectorData.status === 'not_analyzed')) {" in rapor
    sozluk = _oku(JS / 'i18n_common.js')
    for k in ('app.rep.injOrificePlan', 'app.rep.injNotSizedGas', 'app.rep.injNotSizedReason'):
        assert sozluk.count("'%s':" % k) == 2, k            # EN + TR


@pytest.mark.skipif(__import__('shutil').which('node') is None, reason='node yok')
def test_K2_tablo_boyutlanmamis_blokta_sayi_satiri_yok():
    """displayInjectorTable GERÇEK gövdesi (test_v301_enjektor_genel_arayuz
    düzeneği): not_analyzed blokta iki satır, sayı/N/A yok."""
    from tests.test_v301_enjektor_genel_arayuz import _tablo_satirlari
    r = _tablo_satirlari({'type': 'showerhead', 'status': 'not_analyzed',
                          'reason_code': 'gas_phase_feed_not_modelled',
                          'reason': 'x', 'plate_thickness': 3.0})
    assert [s[0] for s in r['rows']] == ['Type', 'Orifice Plan']
    assert r['rows'][1][1].startswith('not sized: the gaseous oxidizer feed')
    assert 'N/A' not in str(r)
    diger = _tablo_satirlari({'type': 'pintle', 'status': 'not_analyzed',
                              'reason_code': 'baska', 'reason': 'neden metni'})
    assert diger['rows'][1][1] == 'not sized: neden metni'


def test_K2_hibrit_sayfada_gaz_n2o_raporu(tarayici, sunucu):
    s = _sayfa(tarayici, sunucu, '/hybrid')
    try:
        for k, v in (('oxidizer_phase', 'gas'), ('tank_pressure_source', 'user'),
                     ('tank_pressure', '16'), ('chamber_pressure', '8.52'),
                     ('of_ratio', '3.9'), ('combustion_efficiency', '79'),
                     ('thrust', '72.7'), ('burn_time', '11'),
                     ('initial_port_diameter', '11.7')):
            _alan(s, k, v)
        _hibrit_hesapla(s)
        uyarilar = s.inner_text('#warningsList')
        assert 'Gaz fazlı oksitleyici beslemesi' in uyarilar
        for parca in ('şu an 1,70 bar', 'Treat these hole sizes', 'liquid-phase',
                      'Hedef püskürtme hızı', 'Çıkış hızı ('):
            assert parca not in uyarilar, parca
        tablo = s.inner_text('#injector_table')
        assert 'Delik Planı' in tablo and 'boyutlandırılmadı' in tablo
        assert 'N/A' not in tablo
    finally:
        s.context.close()


# ---------------------------------------------------------------------------
# Kalem 3 — NK3-S-8: Coriolis notu ⟷ uçuş sonu yatay uzaklık (tek büyüklük)
# ---------------------------------------------------------------------------
NODE = __import__('shutil').which('node')


def test_K3_coriolis_notu_sifir_sapma_iddia_etmez():
    sozluk = _oku(JS / 'i18n_common.js')
    satirlar = [s for s in sozluk.splitlines()
                if "'warn.sixdof.coriolis_disabled_no_latitude':" in s]
    assert len(satirlar) == 2                                   # EN + TR
    metin = ' '.join(satirlar)
    for yasak in ('reported as zero', 'sıfır olarak raporlanıyor'):
        assert yasak not in metin, yasak
    assert 'no Coriolis deflection' in metin and 'Coriolis sapması içermez' in metin
    assert sozluk.count("'sixdof.badgeHorizDist':") == 2


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_K3_rozet_blogu_yatay_uzakligi_basar(tmp_path):
    """Rozet bloğu (tests/test_faz5_ui.py düzeneği) uçun alanını basar;
    alan yoksa rozet açmaz (sayı uydurulmaz)."""
    from tests.test_faz5_ui import _run_badge_block, SUMMARY_TIME_LIMIT
    s = dict(SUMMARY_TIME_LIMIT, lateral_drift_at_end=404.97)
    cikti = _run_badge_block(tmp_path, s, 's2k_drift')
    assert 'HORIZONTAL DISTANCE AT FLIGHT END 405 m' in cikti
    cikti_yok = _run_badge_block(tmp_path, dict(SUMMARY_TIME_LIMIT), 's2k_nodrift')
    assert 'HORIZONTAL DISTANCE' not in cikti_yok


def test_K3_sivi_6dof_ekraninda_tek_buyukluk(tarayici, sunucu):
    import urllib.parse
    s = _sayfa(tarayici, sunucu, '/liquid?project='
               + urllib.parse.quote('Example Liquid LOX-RP1 25kN'))
    yanit = []
    s.on('response', lambda r: yanit.append(r) if r.url.endswith('/api/six-dof-analysis') else None)
    try:
        s.wait_for_function('() => window.HRMAProjectBar && HRMAProjectBar._state'
                            ' && HRMAProjectBar._state.name')
        s.evaluate('() => { window.__s2h = window.currentResults || null; calculateLiquid(); }')
        s.wait_for_function('() => window.currentResults && window.currentResults !== window.__s2h',
                            timeout=180000)
        s.wait_for_timeout(1500)
        _alan(s, 'sd_wind', '5')
        s.evaluate('() => SixDofPanel.run()')
        s.wait_for_function("() => (document.getElementById('sd_badges') || {}).innerText",
                            timeout=120000)
        s.wait_for_timeout(1000)
        rozet = s.inner_text('#sd_badges')
        ozet = yanit[-1].json()['summary']
        assert 'warn.sixdof.coriolis_disabled_no_latitude' in [
            w.get('code') for w in ozet.get('warnings') or []]
        assert 'sıfır olarak raporlanıyor' not in rozet
        beklenen = s.evaluate('(v) => I18N.number(v, 0)', ozet['lateral_drift_at_end'])
        assert 'UÇUŞ SONU YATAY UZAKLIK %s m' % beklenen in rozet
    finally:
        s.context.close()


# ---------------------------------------------------------------------------
# Kalem 4 — hibrit örnek dosyası uçuş kurulumunu taşımıyordu (üretici düşürüyordu)
# ---------------------------------------------------------------------------
def _ornek_uretici():
    import importlib
    return importlib.import_module('examples.generate_examples')


def test_K4_uretici_ucus_kurulumunu_dusurmez():
    ge = _ornek_uretici()
    for tur in ('hybrid', 'solid', 'liquid'):
        assert 'dynamic' not in ge.KAYITTAN_DUSEN_BOLUMLER.get(tur, ()), tur
    belge = {'inputs': {
        'fields': {'thrust': '1000', 'total_impulse': '10000', 'param_start': '1',
                   'param_end': '4'},
        'ui_state': {'environment_tab': 'single'},
        'dynamic': {'flight': {'format': 1, 'sixdof': {'format': 1, 'fields': {},
                                                       'user_typed': []},
                               'trajectory_user_typed': []}}}}
    dusen = ge.kayittan_dusur('hybrid', belge)
    assert dusen == ['total_impulse', 'param_start', 'param_end']
    assert belge['inputs']['dynamic']['flight']['format'] == 1
    assert belge['inputs']['fields'] == {'thrust': '1000'}
    # Ana akış aynı işlevi çağırır ve uçuş kurulumu yoksa durur (fail-closed).
    kaynak = _oku(KOK / 'examples' / 'generate_examples.py')
    ana = kaynak[kaynak.index('def main('):]
    assert 'dusen = kayittan_dusur(motor_type, diskte)' in ana
    assert "get('flight')" in ana and 'raise SystemExit' in ana


@pytest.mark.parametrize('ad,tur', [
    ('Example Hybrid N2O-HTPB 3kN', 'hybrid'),
    ('Example Liquid LOX-RP1 25kN', 'liquid'),
    ('Example Solid KNDX BATES 75mm', 'solid')])
def test_K4_dagitilan_ornek_ucus_kurulumunu_tasir(ad, tur):
    import json
    belge = json.loads(_oku(KOK / 'examples' / (ad + '.hrma')))
    ucus = (belge['inputs'].get('dynamic') or {}).get('flight')
    if ucus is None and tur == 'hybrid' and belge.get('app_version') == '3.0.6':
        pytest.xfail('3.0.6 hibrit örneği eski üreticiyle üretildi; örnek yayın '
                     'treninde yeniden üretilecek (RAPOR kalem 4)')
    assert ucus and ucus.get('format') == 1 and 'sixdof' in ucus


# ---------------------------------------------------------------------------
# Kalem 5 — NK3-S-6: "VAKUM İTKİSİ 1,0 kN" (gerçek 953,6 N)
# ---------------------------------------------------------------------------
#: NK3-S L1 (9 Kas): 800 N / Pc 15 bar sıvı motorun sayfa gövdesi.
SIVI_L1 = {'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'oxidizer_density': 1141.16, 'oxidizer_viscosity': 0.0001947, 'mixture_ratio': 2.3, 'of_min': 2, 'of_max': 3.2, 'combustion_efficiency': 97, 'engine_cycle': 'pressure_fed', 'thrust': 800, 'chamber_pressure': 15, 'feed_pressure': 25, 'injector_type': 'unlike_impinging', 'injector_pressure_drop': 3, 'discharge_coefficient': 0.7, 'injector_elements': 12, 'characteristic_length': 1.2, 'contraction_ratio': 4, 'chamber_material': 'steel_304', 'chamber_roughness': 3.2, 'cooling_type': 'ablative', 'nozzle_expansion_ratio': 3.5, 'nozzle_type': 'conical', 'coolant_flow_percent': 100, 'film_cooling_percent': 0, 'coolant_inlet_temp': 300, 'max_wall_temp': 800, 'min_throttle': 40, 'max_burn_duration': 7.7, 'safety_factor': 2.5, 'engine_life_cycles': 10}


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_K5_anlamli_ondalik_kurali(tmp_path):
    """Kart ve metin yolu aynı kuraldan: en az 3 anlamlı basamak."""
    html = _oku(SABLON / 'liquid.html')
    i = html.index('const LIQ_ANLAMLI_BASAMAK')
    j = html.index('function liqAnlamliTxt', i)
    blok = html[i:j]
    assert 'function liqAnlamliOndalik(v, taban)' in blok
    betik = tmp_path / 'k5.js'
    betik.write_text(blok + r"""
process.stdout.write(JSON.stringify([
  liqAnlamliOndalik(0.9535829981, 1), liqAnlamliOndalik(29.36975, 1),
  liqAnlamliOndalik(0.0702, 2), liqAnlamliOndalik(250.2, 1), liqAnlamliOndalik(null, 1)]));
""", encoding='utf-8')
    import json
    s = json.loads(subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                                  timeout=60, check=True).stdout)
    assert s == [3, 1, 4, 1, 1], s


def test_K5_sabit_ondalikli_kN_kalmadi():
    html = _oku(SABLON / 'liquid.html')
    assert 'value: results.thrust_vacuum / 1000, decimals: 1' not in html
    assert 'decimals: liqAnlamliOndalik(results.thrust_vacuum / 1000, 1)' in html
    assert "numTxt((results.thrust/1000), 1)} kN" not in html
    assert "hrmaFmt(v / 1000, 2, 'kN')" not in html
    assert "hrmaFmt(mb.total_N_m / 1000, 2, 'kN·m')" not in html
    # Null kapısı (P5B4-18) korunur: moment satırı sayı değilse bölmez.
    assert "typeof ring.bending_moment_N_m === 'number'" in html


def test_K5_kucuk_motorda_vakum_itkisi_karti(tarayici, sunucu):
    govde = SIVI_L1
    s = _sayfa(tarayici, sunucu, '/liquid')
    try:
        for k, v in sorted(govde.items()):
            if s.evaluate('(k) => !!document.getElementById(k)', k):
                _alan(s, k, str(v))
        s.evaluate('() => { window.__s2h = window.currentResults || null; calculateLiquid(); }')
        s.wait_for_function('() => window.currentResults && window.currentResults !== window.__s2h',
                            timeout=180000)
        s.wait_for_timeout(3500)                      # HUD sayacı
        tv = s.evaluate('() => window.currentResults.thrust_vacuum')
        assert 900 < tv < 1000, tv                    # NK3-S L1: 953,6 N
        kartlar = s.evaluate("""() => [...document.querySelectorAll('#performanceMetrics .hd-metric')]
            .map(e => e.innerText.replace(/\\s+/g, ' ').trim())""")
        vakum = [k for k in kartlar if k.startswith('VAKUM İTKİSİ')]
        beklenen = s.evaluate('(v) => I18N.number(v, 3)', tv / 1000)
        assert vakum == ['VAKUM İTKİSİ %skN' % beklenen], (vakum, beklenen)
    finally:
        s.context.close()
