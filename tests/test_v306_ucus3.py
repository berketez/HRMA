"""V306/UÇUŞ-3 bekçileri — ekrandaki her uçuş sayısı şu anki projenin şu anki
hesabına aittir; proje dosyası kullanıcının kurduğu uçuşu geri getirir
(3.0.6, mühendis turu 2 Kas).

K1  proje dosyası 6-DOF aracını ve Zaman Çözümlü ayarlarını taşır, açılışta
    geri kurar; "elle yazıldı" damgası da (M-SIVI-26, M-HIBRIT-35) — tarayıcı
K2  aynı tipte proje açmak sayfayı projeden kurar (temiz sayfa, ?project=);
    yapay olay "elle yazıldı" saymaz (M-HIBRIT-36, UÇUŞ DEVİR)
K3  sıvı yörünge: yazılan kütleler motorun iticisiyle çelişirse hangi
    değerin uçtuğu adıyla (M-SIVI-3)
K1b sıvı 6-DOF: motorun taşımadığı itici adıyla ret (yanma süresi denetimi)
K5  paraşüt alanları çözücüye ulaşır; geçersizi adıyla ret (M-KATI-12)
K6  Zaman Çözümlü: yeni motor hesabında eski eğri temizlenir; tank sıcaklığı
    motorun oksitleyici sıcaklığından (M-HIBRIT-17) — tarayıcı
K7  motor kütlesi yayımlanmadıysa araç kurulmaz (SIVI-SOĞUTMA DEVİR)

Kanıt, önce/sonra ölçümleri ve ters mutasyonlar:
docs/scofield/raw/OH/V306/ucus3/RAPOR.md.
"""
import contextlib
import io
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

from hrma.analysis import flight_vehicle as fv

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')


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


# ------------------------------------------------------------------- K7

def _sivi_sonuc_kutlesiz(soguma_cozulmedi=True):
    """Sıvı motorun yayımladığı sonuç yapısı; motor kütlesi geri çekilmiş."""
    r = {'thrust': 5000.0, 'burn_time': 30.0, 'total_mass_flow': 2.0,
         'design_summary': {'masses': {'propellant_mass_kg': 60.0,
                                       'engine_mass_kg': None},
                            'key_dimensions': {}},
         'engine_mass_estimate': None,
         'feed_system': {'total_mass': 18.0}}
    if soguma_cozulmedi:
        r['cooling_circuit_publication'] = {
            'status': 'not_solved', 'code': 'coolant_pressure_collapse',
            'reason': 'Coolant pressure fell to zero', 'basis': 'test'}
    return r


def test_K7_besleme_kutlesi_yedegi_yok():
    """Motor kütlesi yoksa atıl kütle besleme hattı alt kümesine DÜŞMEZ."""
    v = fv.normalize('liquid', _sivi_sonuc_kutlesiz())
    assert v['engine_inert_mass'] is None
    assert v['engine_inert_mass_note']


def test_K7_motor_kutlesi_yoksa_arac_kurulmaz():
    r = _sivi_sonuc_kutlesiz()
    v = fv.normalize('liquid', r)
    red = fv.vehicle_build_refusal('liquid', r, v)
    assert red['error'] == fv.VEHICLE_REFUSAL_ENGINE_MASS
    assert red['cause'] == 'cooling_circuit_not_solved'
    assert red['cooling_circuit_publication']['status'] == 'not_solved'
    # Kütle yayımlanmışsa kapı konuşmaz; tasarım sonucu olmayan kısmi
    # sözlükte de (bekçi düzenekleri) konuşmaz.
    r2 = _sivi_sonuc_kutlesiz(False)
    r2['design_summary']['masses']['engine_mass_kg'] = 40.0
    assert fv.vehicle_build_refusal('liquid', r2, fv.normalize('liquid', r2)) is None
    kismi = {'thrust': 100.0}
    assert fv.vehicle_build_refusal('liquid', kismi, fv.normalize('liquid', kismi)) is None


def test_K7_uc_adli_422(istemci):
    r = _post(istemci, '/api/flight-vehicle', {
        'source': 'results', 'motor_type': 'liquid', 'results': _sivi_sonuc_kutlesiz()})
    assert r.status_code == 422
    d = r.get_json()
    assert d['error'] == 'engine_mass_not_published'
    assert d['cause'] == 'cooling_circuit_not_solved'
    assert 'vehicle' not in d


def test_K7_sayfalar_reddi_okur():
    js = _oku(JS / 'flight_handoff.js')
    assert "b.error === REFUSAL_CODE" in js and "'hrma:flight-vehicle-refused'" in js
    sd = _oku(JS / 'sixdof_panel.js')
    i = sd.index('const sayfaMotoruIstendi')
    assert 'FlightHandoff.vehicleRefusalText(window.currentResults)' in sd[i:i + 500]
    sivi = _oku(SABLON / 'liquid.html')
    i = sivi.index('async function computeTrajectory()')
    assert 'FlightHandoff.vehicleRefusalText(cr)' in sivi[i:i + 9000]
    saha = _oku(SABLON / 'launch_site.html')
    assert "durum.status === 'refused'" in saha


# ------------------------------------------------------------------- K5

_YORUNGE = {'thrust': 1000.0, 'burn_time': 5.0, 'isp': 200.0,
            'initial_mass': 20.0, 'final_mass': 17.45,
            'drag_coefficient': 0.5, 'reference_area': 0.007854}


def test_K5_parasut_cozucuye_ulasir(istemci):
    yok = _post(istemci, '/api/trajectory-analysis', dict(_YORUNGE)).get_json()
    assert yok['trajectory_data']['recovery']['reason'] == 'recovery_not_supplied'
    hiz = {}
    for alan in (3.0, 9.0):
        d = _post(istemci, '/api/trajectory-analysis',
                  dict(_YORUNGE, parachute_area=alan, parachute_cd=1.4,
                       parachute_deploy_delay=2.0)).get_json()
        rec = d['trajectory_data']['recovery']
        assert rec['descent_model'] == 'parachute'
        assert rec['parachute_area_m2'] == alan and rec['parachute_cd'] == 1.4
        assert rec['parachute_deploy_delay_s'] == 2.0
        hiz[alan] = rec['landing_velocity_m_s']
    # Uç hız ~ 1/√A (paraşüt altında sürükleme baskın): 9 m² / 3 m² → √3.
    assert hiz[3.0] / hiz[9.0] == pytest.approx(math.sqrt(3.0), rel=1e-3)


@pytest.mark.parametrize('alan,deger,neden', [
    ('parachute_area', 0.0, 'must_be_positive'),
    ('parachute_cd', -1.0, 'must_be_positive'),
    ('parachute_deploy_delay', -1.0, 'must_be_non_negative')])
def test_K5_gecersiz_kurtarma_adiyla_ret(istemci, alan, deger, neden):
    govde = dict(_YORUNGE, parachute_area=3.0)
    govde[alan] = deger
    r = _post(istemci, '/api/trajectory-analysis', govde)
    assert r.status_code == 422
    f = r.get_json()['invalid_fields']
    assert {'field': alan, 'reason': neden, 'value': deger} in f



# ------------------------------------------------------- K3 / K1b (node)

def _node(betik):
    sonuc = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                           timeout=30)
    assert sonuc.returncode == 0, sonuc.stderr
    return json.loads(sonuc.stdout.strip().splitlines()[-1])


_DOM = r"""
var document = { getElementById: function () { return null; },
  dispatchEvent: function () {}, querySelector: function () { return null; } };
var window = { document: document, localStorage: { getItem: function () { return null; },
  setItem: function () {} } };
global.window = window; global.document = document;
"""


@node_gerekli
def test_K3_itici_butcesi_satiri():
    r = _node(_DOM + _oku(JS / 'flight_handoff.js') + r"""
      var FH = window.FlightHandoff;
      console.log(JSON.stringify({
        fark: FH.propellantBudgetLine(297.451, 148.725, 9.915),
        ayni: FH.propellantBudgetLine(148.7252, 148.725, 9.915),
        yok: FH.propellantBudgetLine(10, null, 9.915)}));
    """)
    metin, tur = r['fark']
    assert tur == 'warn'
    assert '297.451' in metin and '148.725' in metin
    assert '30.00' in metin and '15.00' in metin       # uçan ⟷ motorun yanma süresi
    assert r['ayni'] is None and r['yok'] is None


def _fonksiyon(kaynak, ad):
    i = kaynak.index('function %s(' % ad)
    j = kaynak.index('{', i)
    d = 0
    for k in range(j, len(kaynak)):
        d += {'{': 1, '}': -1}.get(kaynak[k], 0)
        if d == 0:
            return kaynak[i:k + 1]
    raise AssertionError(ad)


@node_gerekli
def test_K1b_sivi_6dof_motorun_tasimadigi_itici_reddedilir():
    sivi = _oku(SABLON / 'liquid.html')
    g0 = re.search(r'const LIQUID_G0 = [^;]+;', sivi).group(0)
    betik = (_DOM + _oku(JS / 'flight_handoff.js') + '\n' + g0 + '\n'
             + _fonksiyon(sivi, '_liqKutleToleransi') + '\n'
             + _fonksiyon(sivi, '_liquidSixDofDriveFrom') + r"""
      var cr = {thrust: 25000, total_mass_flow: 9.915};
      console.log(JSON.stringify({
        fazla: _liquidSixDofDriveFrom(cr, 376938, 297.451),
        esit: _liquidSixDofDriveFrom(cr, 297.451, 297.451),
        az: _liquidSixDofDriveFrom(cr, 100, 297.451),
        motorsuz: _liquidSixDofDriveFrom(cr, 376938)}));
    """)
    r = _node(betik)
    assert r['fazla']['reject'] == 'prop_exceeds_engine'
    assert r['fazla']['burn_time'] == pytest.approx(376938 / 9.915)
    assert r['fazla']['engine_burn_time'] == pytest.approx(297.451 / 9.915)
    assert 'reject' not in r['esit'] and 'reject' not in r['az']
    assert 'reject' not in r['motorsuz']       # motor itici yayımlamıyorsa denetim yok
    # Sağlayıcı reddi koşuya gitmez; panel cümleyi basar.
    assert "if (drive.reject) return { reject: _liquidSixDofRetMetni(drive) };" in sivi
    sd = _oku(JS / 'sixdof_panel.js')
    i = sd.index('if (provided && provided.reject) {')
    assert 'return;' in sd[i:i + 120]


# ----------------------------------------------- K2 (kaynak sözleşmesi)

def test_K2_ayni_tip_proje_temiz_sayfadan_acilir():
    js = _oku(JS / 'project_bar.js')
    i = js.index('function go() {')
    govde = js[i:js.index('}', js.index("location.href = hedefYol", i)) + 1]
    assert 'loadIntoPage(' not in govde
    assert "'?project=' + encodeURIComponent(p.name)" in govde


def test_K2_kati_6dof_damgasi_yalniz_gercek_yazma():
    html = _oku(SABLON / 'solid.html')
    i = html.index("['sd_thrust', 'sd_burn', 'sd_dry_m', 'sd_prop_m'].forEach")
    assert 'FlightHandoff.isUserEdit(e)' in html[i:i + 400]


# ------------------------------------------------ K1 / K2 / K6 (tarayıcı)

PORT = int(os.environ.get('UCUS3_PORT', '8839'))
URL = 'http://127.0.0.1:%d' % PORT
CALISMA = pathlib.Path(os.environ.get(
    'UCUS3_CALISMA', str(pathlib.Path.home() / 'HRMA-calisma' / 'ucus3-bekci')))


CHROME_1208 = ('/Users/apple/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/'
               'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')


def _hazir_mi(url):
    try:
        with urllib.request.urlopen(url + '/hybrid', timeout=2) as r:
            return r.status == 200
    except Exception:   # noqa: BLE001
        return False


@pytest.fixture(scope='module')
def sunucu():
    """Port doluysa (kulvarın kendi sunucusu) onu kullanır; boşsa açar."""
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


def _sayfa(tarayici, sunucu, yol):
    s = tarayici.new_page(viewport={'width': 1440, 'height': 1000})
    s.set_default_timeout(30000)
    s.goto(sunucu + yol, wait_until='networkidle')
    s.wait_for_function('() => window.SixDofPanel && document.getElementById("sd_dry_m")')
    return s


def _hesapla(s):
    """Sayfanın kendi Hesapla düğmesi (6-DOF paneli sonuç bölümünde görünür)."""
    s.evaluate('() => { window.__u3 = window.currentResults || null; }')
    s.locator('button[onclick="calculate()"]').first.click()
    s.wait_for_function('() => window.currentResults && window.currentResults !== window.__u3',
                        timeout=180000)


#: 6-DOF alanları sixdof_panel.js FIELDS listesinden (tek tanım).
def _sd_alanlari():
    js = _oku(JS / 'sixdof_panel.js')
    blok = js[js.index('const FIELDS = ['):js.index('];', js.index('const FIELDS = ['))]
    return re.findall(r"id: '(sd_[a-z0-9_]+)'", blok)


def test_K1_ucus_kurulumu_kayda_girer_ve_geri_kurulur(tarayici, sunucu):
    alanlar = _sd_alanlari()
    assert len(alanlar) >= 20
    s = _sayfa(tarayici, sunucu, '/hybrid')
    try:
        _hesapla(s)
        yazilan = {}
        for i, a in enumerate(alanlar):
            el = s.locator('#' + a)
            if el.evaluate('e => e.tagName') == 'SELECT':
                continue
            if el.evaluate('e => e.readOnly'):
                continue
            yazilan[a] = str(round(1.5 + 0.25 * i, 3))
            el.fill(yazilan[a])           # gerçek yazma (isTrusted)
        s.select_option('#tp_feed_mode', 'blowdown')
        s.locator('#tp_tank_temp').fill('285')
        ucus = s.evaluate("() => HRMAProjectBar._buildPayload('x').inputs.dynamic.flight")
        sd = ucus['sixdof']
        for a in alanlar:
            assert a in sd['fields'], a        # şemadaki her 6-DOF alanı kayıtta
        for a, v in yazilan.items():
            assert float(sd['fields'][a]) == float(v), a
            assert a in sd['user_typed'], a
        assert ucus['transient']['tank_temp'] == '285'
        assert ucus['transient']['tank_temp_user_typed'] is True
        assert ucus['transient']['feed_mode'] == 'blowdown'
    finally:
        s.close()
    # Temiz sayfa: önceki sayfanın hiçbir şeyi yok; durum geri kurulur.
    s = _sayfa(tarayici, sunucu, '/hybrid')
    try:
        bos = s.evaluate("() => document.getElementById('sd_dry_m').dataset.userOverride || null")
        assert bos is None
        s.evaluate('(u) => { SixDofPanel.projeDurumunuKur(u.sixdof);'
                   ' TransientPanel.projeDurumunuKur(u.transient); }', ucus)
        geri = s.evaluate("""(ids) => ids.map(id => { const e = document.getElementById(id);
            return [id, e.value, e.dataset.userOverride || null]; })""", list(yazilan))
        for a, v, damga in geri:
            assert float(v) == float(yazilan[a]) and damga == 'true', (a, v, damga)
        assert s.input_value('#tp_tank_temp') == '285'
        # Eski dosya (kurulum yok): panel sayfa varsayılanında kalır, adıyla söyler.
        s.evaluate('() => SixDofPanel.projeDurumunuKur(null)')
        assert '3.0.6' in s.inner_text('#sd_seed_note')
    finally:
        s.close()


def test_K2_yapay_olay_elle_yazma_saymaz(tarayici, sunucu):
    s = _sayfa(tarayici, sunucu, '/hybrid')
    try:
        _hesapla(s)
        yapay = s.evaluate("""() => { const e = document.getElementById('sd_dry_m');
            e.value = '7'; e.dispatchEvent(new Event('input', {bubbles: true}));
            e.dispatchEvent(new Event('change', {bubbles: true}));
            return e.dataset.userOverride || null; }""")
        assert yapay is None
        s.locator('#sd_dry_m').fill('8')
        assert s.evaluate("() => document.getElementById('sd_dry_m').dataset.userOverride") == 'true'
    finally:
        s.close()


def test_K6_zaman_cozumlu_yeni_hesapta_temizlenir_ve_tank_sicakligi_motordan(tarayici, sunucu):
    s = _sayfa(tarayici, sunucu, '/hybrid')
    try:
        hesapla = lambda: _hesapla(s)   # noqa: E731
        s.locator('#oxidizer_temp').fill('281.75')
        hesapla()
        assert float(s.input_value('#tp_tank_temp')) == pytest.approx(281.75)
        s.locator('#tp_run').click()
        s.wait_for_function("() => document.getElementById('tp_badges').innerText.trim().length > 0",
                            timeout=120000)
        s.locator('#thrust').fill('900')
        hesapla()
        assert s.inner_text('#tp_badges').strip() == ''
        assert s.evaluate("() => TransientPanel.result") is None
        assert 'temizlendi' in s.inner_text('#tp_status') or 'cleared' in s.inner_text('#tp_status')
    finally:
        s.close()
