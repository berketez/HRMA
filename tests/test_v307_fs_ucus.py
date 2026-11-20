"""V307/FS-UÇUŞ — Fırlatma Sahası: içe aktarılan araçla uçuş + sonuç sözleşmesi.

Berke (9 Kas 2026): "import edilen motorun bide roketin bilgilerine göre uçuş
simülasyonu … hiç bişey yüklenmiyor … sadece çizgi şeklinde gidiyor".

ÖLÇÜLDÜ (docs/scofield/raw/OH/V307/fs-ucus/olcum/saha_once.json):
  K1  Kaynak = "Kayıtlı proje" seçilince /api/flight-vehicle HİÇ çağrılmıyordu
      (liste zaman uyumsuz doluyor, araç aynı anda boş adla isteniyordu);
      listede ilk proje seçili görünüyor ama yüklenmiyordu.
  K2  Çizilen yol yalnız kalkış → apoje koluydu (6-DOF apojede durur); iniş,
      enlem/boylam ve olay zamanları hiçbir istemci nesnesinde yoktu.

Bekçiler:
  * uç: ``descent_model`` istenince ``track`` (yükseliş + iniş, enlem/boylam,
    olaylar); istenmezse yanıt eskisi gibi (motor sayfası 6-DOF paneli);
    tanınmayan model adıyla 422; kararsız araçta iniş adıyla çözülmez.
  * fizik: sürüklemesiz balistik iniş kapalı biçimle (düşme süresi, yatay yol).
  * sayfa: proje kaynağı liste dolunca seçili projeyi yükler; sözleşme
    ``window.LaunchSiteFlightResult`` + ``hrma:launch-site-flight`` yayımlanır;
    yeni ``site.flight*`` metinleri EN + TR.
  * tarayıcı (WebGL kapalı): tek kayıtlı proje Kaynak seçilince yüklenir
    (K1 kullanıcı yolu) ve uçuşta sözleşme dolar.
"""
import importlib.util
import math
import pathlib
import re
import shutil

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
SOZLUK = KOK / 'hrma' / 'static' / 'js' / 'i18n_launch_site.js'

#: Örnek aracın (flight_vehicle.EXAMPLE_VEHICLE) Fırlatma Sahası gövdesi.
ORNEK_GOVDE = dict(
    body_diameter=0.15, body_length=3.0, nose_length=0.5, nose_type='ogive',
    dry_mass=25.0, propellant_mass=18.0, thrust=6500.0, burn_time=7.5,
    cd0=0.45, fin_count=4, fin_root_chord=0.2, fin_tip_chord=0.1,
    fin_span=0.11, fin_sweep=0.08, launch_elevation_deg=84,
    launch_azimuth_deg=90, rail_length=5, wind_speed=0,
    wind_direction_deg=270, t_max=400)
SAHA = {'latitude_deg': 28.6084, 'longitude_deg': -80.6043}
IZ_ORNEK_ANAHTARLARI = {
    'time_s', 'phase', 'latitude_deg', 'longitude_deg', 'altitude_agl_m',
    'altitude_msl_m', 'north_m', 'east_m', 'downrange_m', 'speed_mps',
    'mach', 'dynamic_pressure_pa'}


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


def _uc(istemci, **ek):
    govde = dict(ORNEK_GOVDE)
    govde.update(ek)
    y = istemci.post('/api/six-dof-analysis', json=govde)
    return y.status_code, y.get_json()


@pytest.fixture(scope='module')
def ucus(istemci):
    return _uc(istemci, descent_model='ballistic', **SAHA)


def test_iz_yukselis_ve_inis_tek_seride(ucus):
    durum, d = ucus
    assert durum == 200 and d['status'] == 'success'
    iz = d['track']
    assert iz['schema'] == 'hrma.six_dof.track/1'
    o = iz['samples']
    assert set(o) == IZ_ORNEK_ANAHTARLARI
    n = len(o['time_s'])
    assert all(len(o[k]) == n for k in o)
    assert all(b > a for a, b in zip(o['time_s'], o['time_s'][1:])), 'zaman artmıyor'
    assert iz['descent']['status'] == 'solved', iz['descent']
    assert set(o['phase']) == {'powered', 'coast', 'descent'}
    # İz yere kadar iner (K2: eskiden apojede biten tek kol).
    assert o['altitude_agl_m'][-1] == pytest.approx(0.0, abs=1e-6)
    assert max(o['altitude_agl_m']) == pytest.approx(d['summary']['apogee'], rel=1e-9)
    # Yükseliş kolu 6-DOF serisinin KENDİSİ (sayı uydurulmaz / değişmez).
    m = len(d['series']['time'])
    assert o['time_s'][:m] == d['series']['time']
    assert o['altitude_agl_m'][:m] == d['series']['altitude']
    assert o['north_m'][:m] == d['series']['north']
    # Enlem/boylam saha noktasından başlar; tek kaynak enu_to_geodetic.
    assert o['latitude_deg'][0] == pytest.approx(SAHA['latitude_deg'], abs=1e-12)
    assert o['longitude_deg'][0] == pytest.approx(SAHA['longitude_deg'], abs=1e-12)
    from hrma.analysis.launch_site import enu_to_geodetic
    la, lo, _ = enu_to_geodetic(SAHA['latitude_deg'], SAHA['longitude_deg'], 0.0,
                                o['north_m'][-1], o['east_m'][-1], 0.0)
    assert o['latitude_deg'][-1] == pytest.approx(float(la), abs=1e-12)
    assert o['longitude_deg'][-1] == pytest.approx(float(lo), abs=1e-12)


def test_olaylar_cozumden_ve_sirali(ucus):
    _, d = ucus
    ev = d['track']['events']
    anahtar = [e['key'] for e in ev]
    assert set(anahtar) == {'liftoff', 'burnout', 'max_q', 'apogee', 'landing'}
    t = [e['t_s'] for e in ev]
    assert t == sorted(t)
    olay = {e['key']: e for e in ev}
    assert olay['apogee']['t_s'] == pytest.approx(d['summary']['apogee_time'], rel=1e-12)
    assert olay['burnout']['t_s'] == pytest.approx(ORNEK_GOVDE['burn_time'], rel=1e-12)
    assert olay['landing']['t_s'] == pytest.approx(d['track']['samples']['time_s'][-1], rel=1e-12)
    assert olay['landing']['t_s'] == pytest.approx(d['track']['descent']['impact']['t_s'], rel=1e-12)
    assert olay['landing']['altitude_agl_m'] == pytest.approx(0.0, abs=1e-6)
    q = d['track']['samples']['dynamic_pressure_pa']
    assert olay['max_q']['dynamic_pressure_pa'] >= max(q) * (1 - 1e-9)


def test_istenmezse_yanit_degismez(istemci, ucus):
    """Motor sayfası 6-DOF paneli descent_model göndermez: track yok, seri aynı."""
    durum, d = _uc(istemci, **SAHA)
    assert durum == 200
    assert 'track' not in d
    assert d['series'] == ucus[1]['series']
    assert d['summary'] == ucus[1]['summary']


def test_taninmayan_inis_modeli_adiyla_reddedilir(istemci):
    # V307/FS-UÇUŞ-2 (A4): 'parachute' artık TANINAN modeldir (düzlemsel
    # çözücünün kurtarma modeli; alansız istek kendi adlı reddini alır —
    # tests/test_v307_fs_ucus_2.py). Tanınmayan örnek: 'glider'.
    durum, d = _uc(istemci, descent_model='glider', **SAHA)
    assert durum == 422
    assert [f['field'] for f in d['invalid_fields']] == ['descent_model']


def test_kararsiz_aracta_inis_cozulmez_nedeni_adli(istemci):
    # Kanatsız gövde: statik marj negatif (ölçüm K4'teki sıvı/hibrit gibi).
    durum, d = _uc(istemci, descent_model='ballistic', fin_count=0, **SAHA)
    assert durum == 200
    x = d['track']['descent']
    assert x['status'] == 'not_solved'
    assert x['reason'] in ('vehicle_not_statically_stable',
                           'ascent_did_not_end_at_apogee')
    assert 'landing' not in [e['key'] for e in d['track']['events']]
    assert set(d['track']['samples']['phase']) <= {'powered', 'coast'}


def test_suruklemesiz_balistik_inis_kapali_bicim(istemci):
    """cd0 = 0, rüzgârsız, enlem yok (Coriolis kapalı, g = G0·(R/(R+h))²).

    Düşey hareket 1-B ters-kare düşüşe ayrışır; apojeden (v ≈ 0) yere düşme
    süresi radyal Kepler kapalı biçimi:
        t = √(r₁³/(2μ)) · [√(x(1−x)) + arccos √x],  x = r₀/r₁, μ = g₀·R²
    (sürüklemesiz araç ~100 km'ye çıkar; √(2H/g₀) orada %1,4 sapar, ölçüldü).
    Yatay hız sürükleme ve Coriolis olmadan korunur: yatay yol = vₓ·t."""
    durum, d = _uc(istemci, descent_model='ballistic', cd0=0.0)
    assert durum == 200
    x = d['track']['descent']
    assert x['status'] == 'solved', x
    from hrma.analysis.six_dof_trajectory import G0
    o = d['track']['samples']
    i_ap = o['altitude_agl_m'].index(max(o['altitude_agl_m']))
    son_yukselis = len(d['series']['time']) - 1
    H = o['altitude_agl_m'][son_yukselis]
    t_ap = o['time_s'][son_yukselis]
    assert i_ap <= son_yukselis
    t_dus = x['impact']['t_s'] - t_ap
    # Apoje durumunda dikey hız ~0 (çözücünün apoje olayı); kapalı biçim:
    from hrma.analysis.six_dof_trajectory import R_EARTH
    r0, r1 = R_EARTH, R_EARTH + H
    mu = G0 * R_EARTH ** 2
    x_ = r0 / r1
    t_kepler = math.sqrt(r1 ** 3 / (2.0 * mu)) * (
        math.sqrt(x_ * (1.0 - x_)) + math.acos(math.sqrt(x_)))
    assert t_dus == pytest.approx(t_kepler, rel=1e-4)
    # Yatay hız korunur (sürükleme yok, Coriolis yok).
    vy = (o['east_m'][son_yukselis] - o['east_m'][son_yukselis - 1]) / (
        o['time_s'][son_yukselis] - o['time_s'][son_yukselis - 1])
    assert x['impact']['east_m'] - o['east_m'][son_yukselis] == pytest.approx(
        vy * t_dus, rel=2e-2, abs=1.0)


#: Sıvı örneğin türetilmiş gövdesi (ölçüm K4: Ø0,473 m, 3,35 m; marj −1,86).
SIVI_GOVDE = dict(body_diameter=0.473, body_length=3.35, dry_mass=203.346,
                  propellant_mass=300.168, thrust=25000.0, burn_time=30.0)
#: Hibrit örneğin türetilmiş gövdesi (ölçüm K4: Ø0,212 m, 1,93 m; marj 0,45),
#: sabit itkiyle. V307/FS-UÇUŞ-2 (16 Kas): öneri artık kanat HEDEFİNE
#: (bandın ortası, 1,5 kalibre) göre boyutlanır; sıvı gövdede 0,20/0,10 m
#: veterle 4·d içinde hiçbir açıklık Mach aralığında ≥ 1 kalibre bile
#: vermediği için (ölçüldü: Mach 3,40'ta 1,892 m'de en düşük 1,0965 değil,
#: hedef 1,5; Mach 4,26'da 1,0 da yok) bulunan-öneri yolu hibrit gövdeyle
#: sınanır, sıvı gövdenin adlı "bulunamadı" sonucu ayrıca kilitlenir.
HIBRIT_GOVDE = dict(body_diameter=0.212, body_length=1.93, dry_mass=24.412,
                    propellant_mass=13.306, thrust=3000.0, burn_time=10.414)


def test_kucuk_veterli_sivi_govdede_oneri_adiyla_bulunamaz(istemci):
    durum, d = _uc(istemci, descent_model='ballistic', **SIVI_GOVDE, **SAHA)
    assert durum == 200
    fs = d['fin_sizing']
    assert fs['min_fin_span_m'] is None
    assert fs['reason'] == 'criterion_not_met_within_search_limit'
    assert fs['target_met'] is False and fs['margin_target_used_cal'] == 1.0


def test_kararsiz_aracta_kanat_onerisi_ayni_modelle_olcutu_saglar(istemci):
    """K4: kararsız araçta öneri — Mach aralığında marj hedefte, en küçük
    açıklık, ve öneriyle AYNI girdilerde uçuşun hükmü yanıtla birlikte."""
    durum, d = _uc(istemci, descent_model='ballistic', **HIBRIT_GOVDE, **SAHA)
    assert durum == 200
    assert d['summary']['static_margin_full'] < 1.0
    fs = d['fin_sizing']
    assert fs['current_margin_full_cal'] == pytest.approx(
        d['summary']['static_margin_full'], rel=1e-12)
    acik = fs['min_fin_span_m']
    assert acik is not None and acik > ORNEK_GOVDE['fin_span']
    dg = fs['verification']
    assert dg['status'] == 'flown' and dg['verdict'] == 'stable', dg
    # Ölçüt öneride tutar, bir çözünürlük adımı eksikte tutmaz (en küçük).
    from hrma.analysis import launch_site_flight as lsf
    from hrma.analysis.six_dof_trajectory import (
        BarrowmanAero, CG_ASSUMED_EMPTY_FRACTION, CG_ASSUMED_FULL_FRACTION)
    L = HIBRIT_GOVDE['body_length']
    args = dict(body_diameter=HIBRIT_GOVDE['body_diameter'], nose_length=0.5,
                body_length=L, nose_type='ogive', fin_count=4,
                fin_root_chord=0.2, fin_tip_chord=0.1, fin_sweep=0.08,
                fin_position=None)
    xf, xe = CG_ASSUMED_FULL_FRACTION * L, CG_ASSUMED_EMPTY_FRACTION * L
    m = fs['mach_range_max']
    machlar = [0.0] + [k * lsf.FIN_SIZING_MACH_STEP
                       for k in range(1, int(m / lsf.FIN_SIZING_MACH_STEP) + 1)] + [m]
    # V307/FS-UÇUŞ-2 (16 Kas): öneri kanat HEDEFİNE (bandın ortası, ≥) göre;
    # 4·d içinde sağlanamazsa eşiğe (> 1 kalibre) düşer — yanıt hangisini
    # kullandığını adıyla yazar, minimallik o ölçütle sınanır.
    hedefte = fs['target_met'] is True
    assert fs['margin_target_used_cal'] == (lsf.FIN_TARGET_MARGIN_CAL if hedefte else 1.0)
    tut = lambda a: lsf._marj_tutar(BarrowmanAero(**dict(args, fin_span=a)),
                                    xf, xe, machlar, fs['margin_target_used_cal'],
                                    esit_kabul=hedefte)
    assert tut(acik)
    assert not tut(round(acik - fs['resolution_m'], 6))
    # Kullanıcı öneriyi kullanıp yeniden uçurur: çözücünün hükmü kararlı,
    # apoje doğrulama uçuşununkiyle aynı, iniş çözülür, öneri artık yok.
    assert hedefte, fs     # hibrit gövdede hedef sağlanır
    durum, d2 = _uc(istemci, descent_model='ballistic',
                    **dict(HIBRIT_GOVDE, fin_span=acik), **SAHA)
    assert durum == 200
    assert d2['summary']['stable'] is True
    assert d2['summary']['apogee'] == pytest.approx(dg['apogee_m'], rel=1e-12)
    assert d2['track']['descent']['status'] == 'solved'
    assert 'fin_sizing' not in d2


def test_kanat_onerisi_yalniz_saha_modunda_ve_gerekince(istemci, ucus):
    assert 'fin_sizing' not in ucus[1]                      # kararlı araç
    durum, d = _uc(istemci, **SIVI_GOVDE, **SAHA)           # motor sayfası paneli
    assert durum == 200 and 'fin_sizing' not in d


# ------------------------------------------------------------- sayfa (statik)
def _sablon():
    return SABLON.read_text(encoding='utf-8')


def test_proje_kaynagi_liste_dolunca_secili_projeyi_yukler():
    s = _sablon()
    # K1 kusurunun imzası: liste beklenmeden boş seçimle araç isteği.
    assert "loadProjectList(); loadProjectVehicle(el('ls-project').value);" not in s
    assert re.search(r"loadProjectList\(\)\.then\(function \(ad\)", s)
    assert 'return fetch(\'/api/projects\')' in s


def test_ucus_istegi_iz_ister_ve_sozlesme_yayimlanir():
    s = _sablon()
    assert "descent_model: 'ballistic'" in s
    assert 'longitude_deg: lo' in s
    assert "window.LaunchSiteFlightResult = ucusSonucuKur(" in s
    assert "'hrma:launch-site-flight'" in s
    assert "UCUS_SONUCU_SEMASI = 'hrma.launch_site.flight_result/1'" in s
    # Sözleşme çizimden ÖNCE yayımlanır (WebGL yoksa da dolu).
    assert s.index('ucusSonucuOlayi(window.LaunchSiteFlightResult)') < s.index(
        'globe.setFlightPath(seri, la, lo, h0)')


def test_eski_yanit_yeni_secimi_ezmez():
    """Araç değişince (geçersiz kılma) sürmekte olan uçuşun yanıtı atılır;
    proje aracı yanıtı da sırası geçtiyse uygulanmaz."""
    s = _sablon()
    gecersiz = s[s.index('function ucusSonucunuGecersizKil('):]
    gecersiz = gecersiz[:gecersiz.index('\n    }\n')]
    assert 'ucusSirasi++' in gecersiz
    assert 'globe.clearFlightPath()' in gecersiz
    assert s.count('if (benimUcus !== ucusSirasi) return;') == 2
    assert 'if (benim !== aracSecimi) return;' in s


def test_yeni_metinler_en_tr():
    s = _sablon()
    sozluk = SOZLUK.read_text(encoding='utf-8')
    en, tr = sozluk.split('\n        tr: {', 1)
    kullanilan = set(re.findall(r"'(site\.flight[A-Z]\w+)'", s))
    assert {'site.flightDescentSolved', 'site.flightDescentUnstable',
            'site.flightProjectLoading', 'site.flightNoProjectToLoad'} <= kullanilan
    for k in kullanilan:
        assert ("'%s':" % k) in en, k
        assert ("'%s':" % k) in tr, k
    tr_satir = [ln for ln in tr.splitlines() if "'site.flightDescent" in ln]
    assert any(re.search('[çğıöşüİ]', ln) for ln in tr_satir)


# ------------------------------------------------------------- tarayıcı
CHROME = pathlib.Path(
    '/Users/apple/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/'
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')


@pytest.fixture(scope='module')
def sunucu(tmp_path_factory):
    if importlib.util.find_spec('playwright') is None:
        pytest.skip('playwright paketi yok')
    if not CHROME.exists():
        pytest.skip(f'Chromium yok: {CHROME}')
    from tests.test_example_projects import EXAMPLES_DIR, NAMES
    depo = tmp_path_factory.mktemp('fs_ucus_projeler')
    ad = NAMES['solid']
    shutil.copy(EXAMPLES_DIR / (ad + '.hrma'), depo / (ad + '.hrma'))
    import os
    eski = os.environ.get('HRMA_PROJECTS_DIR')
    os.environ['HRMA_PROJECTS_DIR'] = str(depo)
    from tools.browser_harness.sunucu import UygulamaSunucusu
    s = UygulamaSunucusu(gunluk_yolu=str(depo / 'sunucu.log'))
    try:
        s.baslat()
        yield s.temel_url, ad
    finally:
        s.durdur()
        if eski is None:
            os.environ.pop('HRMA_PROJECTS_DIR', None)
        else:
            os.environ['HRMA_PROJECTS_DIR'] = eski


def test_tarayici_tek_proje_kaynak_secilince_yuklenir_ve_ucar(sunucu):
    from playwright.sync_api import sync_playwright
    temel, ad = sunucu
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=str(CHROME), headless=True,
                              args=['--disable-3d-apis', '--disable-gpu',
                                    '--use-gl=disabled'])
        try:
            s = b.new_page(viewport={'width': 1440, 'height': 900})
            s.set_default_timeout(60000)
            s.goto(temel + '/launch-site', wait_until='domcontentloaded')
            s.wait_for_function('window.FlightHandoff && document.getElementById("ls-fly")')
            olaylar = s.evaluate("""() => { window.__fsOlay = [];
                document.addEventListener('hrma:launch-site-flight',
                    e => window.__fsOlay.push(e.detail ? e.detail.schema : null));
                return window.LaunchSiteFlightResult; }""")
            assert olaylar is None
            with s.expect_response(lambda r: r.url.endswith('/api/flight-vehicle'),
                                   timeout=120000) as yanit:
                s.select_option('#ls-vehicle-source', 'project')
            assert yanit.value.status == 200
            assert (yanit.value.request.post_data_json or {}).get('name') == ad
            s.wait_for_function(
                "document.getElementById('ls-v-thrust').value !== ''", timeout=60000)
            assert ad in s.text_content('#ls-vehicle-name')
            s.fill('#ls-a-drymass', '4')
            with s.expect_response(lambda r: '/api/six-dof-analysis' in r.url,
                                   timeout=120000):
                s.click('#ls-fly')
            s.wait_for_function('window.LaunchSiteFlightResult !== null', timeout=30000)
            r = s.evaluate('window.LaunchSiteFlightResult')
            assert r['schema'] == 'hrma.launch_site.flight_result/1'
            assert r['vehicle']['source'] == 'project'
            assert r['vehicle']['motor_name'] == ad
            assert r['request']['descent_model'] == 'ballistic'
            assert r['samples']['time_s'] and len(r['samples']['latitude_deg']) == len(
                r['samples']['time_s'])
            assert [e['key'] for e in r['events']][0] == 'liftoff'
            # WebGL kapalı: yol çizilemedi → sonuç yine yayımlı, oynatma kapalı.
            assert s.evaluate('window.launchGlobe._flight') is None
            assert s.is_disabled('#ls-playpause')
            assert s.evaluate('window.__fsOlay') == ['hrma.launch_site.flight_result/1']
            # Araç kaynağı değişince sonuç geçersiz: null + olay.
            s.select_option('#ls-vehicle-source', 'example')
            assert s.evaluate('window.LaunchSiteFlightResult') is None
            assert s.evaluate('window.__fsOlay')[-1] is None
        finally:
            b.close()
