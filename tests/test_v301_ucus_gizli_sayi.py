"""V301/UÇUŞ C-25 + NK-47 — Fırlatma Sahası'nda gizli yedek sayı yok; gövde
⟷ motor hükmü 6-DOF ucunda TEK işlevle.

C-25 (NK-21/72 ailesi). ÖLÇÜLDÜ (taban 688bc30b2, ``launch_site.html``):
uçuş gövdesi ``num_(veh.thrust) || 6500``, ``num_(veh.propellant_mass) ||
18``, ``num_(veh.burn_time) || 7.5``, ``(num_(veh.engine_inert_mass) || 0)``,
``fieldNum('ls-a-drymass', 18)`` ve on gövde/çevre alanında aynı kalıpla
sayı gönderiyordu; araç seçilmemişken ``currentVehicle || EXAMPLE_VEHICLE``
örnek aracı sessizce uçuruyordu. Sıvı örnek (yanma süresi verilmemiş:
``burn_time = propellant_mass = None``) Fırlatma Sahası'nda 7,5 s / 18 kg ile
"uçuyordu".

Sonra: motor/araç büyüklüğü yoksa uçuş ADLI RET (alan işaretli, istek
gitmez); gövde/çevre alanı boşsa anahtar gönderilmez ve 6-DOF ucu kendi
beyanlı varsayılanını ``defaults_applied`` ile ADIYLA uygular (sayfa durum
satırında yazar); örnek araç yalnız Kaynak = "Örnek araç" seçilince uçar.
Kullanıcı yolculuğu Playwright ile ölçüldü (EN + TR):
``docs/scofield/raw/OH/V301/ucus/c25_sonra_{en,tr}.json``.

NK-47: 189,6 mm lüleli sıvı motor 0,15 m gövdeyle uyarısız 231 km'ye
uçuyordu; sıvı 6-DOF paneli aynı motoru işaretliyordu (iki yer, iki hüküm).
Hüküm artık ``flight_vehicle.airframe_fit_conflicts``te; ``/api/six-dof-
analysis`` istek motor zarfını taşıyorsa onu çağırır ve 422
``airframe_cannot_carry_engine`` döner. İki sayfa da zarfı gönderir.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from hrma.analysis import flight_vehicle as fv

KOK = pathlib.Path(__file__).resolve().parents[1]
LS = (KOK / 'hrma' / 'templates' / 'launch_site.html').read_text(
    encoding='utf-8')
LS_DIL_JS = (KOK / 'hrma' / 'static' / 'js' / 'i18n_launch_site.js').read_text(
    encoding='utf-8')
SIXDOF_PANEL_JS = (KOK / 'hrma' / 'static' / 'js' / 'sixdof_panel.js').read_text(
    encoding='utf-8')
HANDOFF_JS = (KOK / 'hrma' / 'static' / 'js' / 'flight_handoff.js').read_text(
    encoding='utf-8')
HEADERS = {'Host': '127.0.0.1:8080'}
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _yorumsuz(js):
    js = re.sub(r'/\*[\s\S]*?\*/', '', js)
    return re.sub(r'(?m)^\s*//.*$', '', js)


def _ucus_blogu():
    bas = LS.index("el('ls-fly').addEventListener('click'")
    return LS[bas:LS.index('// ---- Oynatım kontrolleri ----', bas)]


def _islev(ad):
    """Satır içi betikten ``function ad(...) { ... }`` gövdesini kes."""
    bas = LS.index('function ' + ad + '(')
    derinlik, i = 0, LS.index('{', bas)
    while True:
        if LS[i] == '{':
            derinlik += 1
        elif LS[i] == '}':
            derinlik -= 1
            if derinlik == 0:
                return LS[bas:i + 1]
        i += 1


# ---------------------------------------------------------------------------
# C-25 — uçuş gövdesinde yedek sayı yok
# ---------------------------------------------------------------------------

def test_ucus_govdesinde_arac_alanina_yedek_sayi_yok():
    blok = _yorumsuz(_ucus_blogu())
    kalan = re.findall(r'num_\(veh\.\w+\)\s*\|\|\s*[0-9]', blok)
    assert not kalan, f'araç alanına gizli yedek sayı: {kalan}'
    assert not re.search(r'fieldNum\(\s*\'[^\']+\'\s*,', blok), (
        'fieldNum yedek sayıyla çağrılıyor')
    assert 'currentVehicle || EXAMPLE_VEHICLE' not in LS


def _fieldNum_bildirimi():
    return re.search(r'^\s*(function fieldNum\(.*\})\s*$', LS, re.M).group(1)


def test_fieldNum_bos_alanda_null_doner():
    bildirim = _fieldNum_bildirimi()
    assert re.search(r'function fieldNum\(id\)', bildirim), bildirim
    assert bildirim.rstrip().endswith(': null; }'), bildirim


def test_null_anahtar_gonderilmez():
    blok = _yorumsuz(_ucus_blogu())
    assert re.search(r"if \(body\[k\] === null\) delete body\[k\]", blok)


def test_ornek_araca_sessiz_dusus_yok():
    for ad in ('loadSessionVehicle', 'loadProjectVehicle'):
        govde = _yorumsuz(_islev(ad))
        assert 'EXAMPLE_VEHICLE' not in govde, (
            f'{ad} hâlâ örnek araca düşüyor')
    secim = _yorumsuz(LS[LS.index("el('ls-vehicle-source').addEventListener"):])
    secim = secim[:secim.index('});')]
    assert "mode === 'example') applyVehicle(EXAMPLE_VEHICLE" in secim


def _ret_kosumu(veh, kuru='18'):
    kaynak = """
    var ISARET = [];
    var DOM = {'ls-a-drymass': {value: %s, classList: {
                   add: function () { ISARET.push('ls-a-drymass'); }, remove(){}},
               setAttribute(){}, removeAttribute(){}}};
    function el(id) {
        if (DOM[id]) return DOM[id];
        return {value: '', classList: {add: function () { ISARET.push(id); },
                remove(){}}, setAttribute(){}, removeAttribute(){}};
    }
    function t(k, fb) { return k + '|' + fb; }
    function tf(k, p, fb) { return k + '|' + JSON.stringify(p); }
    function num_(v) { var n = parseFloat(v); return isFinite(n) ? n : null; }
    %s
    var UCUS_ISARETLI = [];
    %s
    %s
    var r = ucusReddi(%s);
    console.log(JSON.stringify({ret: r, isaret: ISARET}));
    """ % (json.dumps(kuru), _fieldNum_bildirimi(),
        _islev('alanIsaretle'), _islev('ucusReddi'), json.dumps(veh))
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (tests/test_node_cagri_sozlesmesi.py).
    cikti = subprocess.run([NODE], input=kaynak, capture_output=True,
                           text=True, timeout=30)
    assert cikti.returncode == 0, cikti.stderr
    return json.loads(cikti.stdout.strip())


@needs_node
def test_arac_yoksa_adli_ret():
    r = _ret_kosumu(None)
    assert r['ret'].startswith('site.noVehicleToFly|')
    assert r['isaret'] == ['ls-vehicle-source']


@needs_node
def test_sivi_ornek_yanma_suresi_yoksa_adli_ret():
    """Ölçülen sıvı örnek aracı: itki var, süre ve itici YOK (None)."""
    veh = {'thrust': 25000.0, 'burn_time': None, 'propellant_mass': None,
           'engine_inert_mass': 71.17, 'thrust_curve': None}
    r = _ret_kosumu(veh)
    assert r['ret'].startswith('site.vehicleIncomplete|')
    assert json.loads(r['ret'].split('|', 1)[1]) == {
        'fields': 'burn_time, propellant_mass'}
    assert r['isaret'] == ['ls-v-burntime', 'ls-v-propmass']


@needs_node
def test_atil_kutle_yoksa_sifir_eklenmez_ret():
    veh = {'thrust': 3000.0, 'burn_time': 10.0, 'propellant_mass': 14.5,
           'engine_inert_mass': None}
    r = _ret_kosumu(veh)
    assert 'engine_inert_mass' in r['ret']
    assert r['isaret'] == ['ls-v-inertmass']


@needs_node
def test_egri_varsa_itki_suresi_istenmez_ama_itici_istenir():
    veh = {'thrust': None, 'burn_time': None, 'propellant_mass': 2.4,
           'engine_inert_mass': 3.1,
           'thrust_curve': {'time': [0, 1, 2], 'thrust': [0, 9, 0]}}
    assert _ret_kosumu(veh)['ret'] is None


@needs_node
def test_govde_kuru_kutlesi_bossa_adli_ret():
    veh = {'thrust': 3000.0, 'burn_time': 10.0, 'propellant_mass': 14.5,
           'engine_inert_mass': 11.2}
    r = _ret_kosumu(veh, kuru='')
    assert r['ret'].startswith('site.airframeDryMassEmpty|')
    assert r['isaret'] == ['ls-a-drymass']
    assert _ret_kosumu(veh)['ret'] is None


# ---------------------------------------------------------------------------
# İpuçları ve iletiler EN + TR; gizli sayı ipucundan da kalktı
# ---------------------------------------------------------------------------

_ESKI_GIZLI = ('the page sends 6500 N', 'the page sends 7.5 s',
               'the page sends 18 kg', '0 is added', '0.15 m is sent',
               '3.0 m is sent', '18 kg is used', '0.45 is sent',
               'Empty: 4 is sent', '0.11 m is sent', '270 is sent',
               '84 is sent', '90 is sent', 'showing the example vehicle',
               '6500 N gönderir', '7,5 s gönderir', '18 kg gönderir',
               '0 eklenir', 'örnek araç gösteriliyor')


@pytest.mark.parametrize('metin', [LS, LS_DIL_JS], ids=['sablon', 'sozluk'])
def test_ipuclari_gizli_sayiyi_artik_anmaz(metin):
    kalan = [k for k in _ESKI_GIZLI if k in metin]
    assert not kalan, kalan


@pytest.mark.parametrize('anahtar', [
    'site.noVehicleToFly', 'site.vehicleIncomplete',
    'site.airframeDryMassEmpty', 'site.serverDefaultsApplied'])
def test_yeni_iletiler_iki_dilde(anahtar):
    assert LS_DIL_JS.count("'" + anahtar + "':") == 2, anahtar


# ---------------------------------------------------------------------------
# NK-47 — gövde ⟷ motor hükmü TEK işlevde, 6-DOF ucunda
# ---------------------------------------------------------------------------

def test_tek_islev_cap_ve_boy():
    assert fv.airframe_fit_conflicts(0.1896, 0.52, 0.15, 3.0)[0]['reason'] \
        == 'body_narrower_than_engine'
    assert fv.airframe_fit_conflicts(0.083, 0.568, 0.2, 0.4)[0]['reason'] \
        == 'body_shorter_than_engine'
    assert fv.airframe_fit_conflicts(0.083, 0.568, 0.083, 0.568) == []
    # Zarf ya da gövde bilinmiyorsa denetim yapılmaz (sayı uydurulmaz).
    assert fv.airframe_fit_conflicts(None, None, 0.05, 0.1) == []
    assert fv.airframe_fit_conflicts(0.2, 1.0, None, None) == []


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


#: Ölçülen sıvı örnek aracı (25 kN LOX/RP-1, lüle çıkışı 189,55 mm) ile
#: NK-47'nin ekrandaki gövdesi (0,15 m × 3,0 m, 18 kg).
_NK47 = dict(body_diameter=0.15, body_length=3.0, nose_length=0.5,
             dry_mass=18 + 71.17, propellant_mass=273.59, thrust=25000.0,
             burn_time=30.0, cd0=0.45, fin_count=4, fin_span=0.11,
             launch_elevation_deg=84, launch_azimuth_deg=90, t_max=400)


def test_nk47_dar_govde_uctan_adli_ret(client):
    r = client.post('/api/six-dof-analysis', headers=HEADERS, json=dict(
        _NK47, engine_od_m=0.18955453428259522, engine_length_m=0.521))
    assert r.status_code == 422, r.get_data(as_text=True)[:300]
    g = r.get_json()
    assert g['error'] == 'airframe_cannot_carry_engine'
    assert [f['field'] for f in g['invalid_fields']] == ['body_diameter']
    assert 'summary' not in g and 'series' not in g


def test_motoru_saran_govde_ucar(client):
    r = client.post('/api/six-dof-analysis', headers=HEADERS, json=dict(
        _NK47, body_diameter=0.2, engine_od_m=0.18955453428259522,
        engine_length_m=0.521))
    assert r.status_code == 200
    assert r.get_json()['status'] == 'success'


def test_zarf_gelmezse_eski_sozlesme_aynen(client):
    """Zarf göndermeyen istemci (içe aktarılan motor, elle itki) etkilenmez."""
    r = client.post('/api/six-dof-analysis', headers=HEADERS, json=_NK47)
    assert r.status_code == 200


@pytest.mark.parametrize('deger', [-1, 0, 'genis', True, float('nan')])
def test_zarf_alani_dusman_degerde_422(client, deger):
    govde = dict(_NK47, engine_od_m=deger)
    r = client.post('/api/six-dof-analysis', headers=HEADERS,
                    data=json.dumps(govde).replace('NaN', '"NaN"'),
                    content_type='application/json')
    assert r.status_code == 422, (deger, r.get_data(as_text=True)[:200])


def test_iki_sayfa_da_zarfi_gonderir():
    blok = _yorumsuz(_ucus_blogu())
    assert 'engine_od_m: num_(veh.engine_od_m)' in blok
    assert 'engine_length_m: num_(veh.engine_length_m)' in blok
    panel = _yorumsuz(SIXDOF_PANEL_JS)
    assert 'FlightHandoff.vehicleFor(window.currentResults)' in panel
    assert 'payload.engine_od_m = zarfCap' in panel
    assert 'if (sayfaMotoru && window.FlightHandoff' in panel


@needs_node
def test_kopru_araci_yalniz_ayni_hesaba_doner():
    kaynak = """
    global.window = {location: {pathname: '/liquid'},
        localStorage: {getItem(){return null}, setItem(){}, removeItem(){}}};
    global.fetch = function () { return Promise.resolve({ok: true,
        json: function () { return Promise.resolve({status: 'success',
            vehicle: {engine_od_m: 0.19, thrust: 1}}); }}); };
    global.document = {getElementById: function () { return null; }};
    %s
    var sonuc = {thrust: 1}, baska = {thrust: 1};
    window.FlightHandoff.publish(sonuc, {motor_type: 'liquid'}).then(function () {
        console.log(JSON.stringify({ayni: window.FlightHandoff.vehicleFor(sonuc),
                                    baska: window.FlightHandoff.vehicleFor(baska)}));
    });
    """ % HANDOFF_JS
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (tests/test_node_cagri_sozlesmesi.py).
    cikti = subprocess.run([NODE], input=kaynak, capture_output=True,
                           text=True, timeout=30)
    assert cikti.returncode == 0, cikti.stderr
    r = json.loads(cikti.stdout.strip())
    assert r['ayni'] == {'engine_od_m': 0.19, 'thrust': 1}
    assert r['baska'] is None


# ---------------------------------------------------------------------------
# C-25 (yörünge panelleri) + K-C1 DEVİR 4 / AÇIK 6 (sıvı yörünge)
# ---------------------------------------------------------------------------

SOLID_HTML = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(
    encoding='utf-8')
LIQUID_HTML = (KOK / 'hrma' / 'templates' / 'liquid.html').read_text(
    encoding='utf-8')
APP_JS = (KOK / 'hrma' / 'static' / 'js' / 'app.js').read_text(
    encoding='utf-8')


def _islev_metin(kaynak, ad):
    m = re.search(r'(?:async\s+)?function\s+%s\s*\(' % re.escape(ad), kaynak)
    assert m, ad
    derinlik, i = 0, kaynak.index('{', m.start())
    while True:
        if kaynak[i] == '{':
            derinlik += 1
        elif kaynak[i] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[m.start():i + 1]
        i += 1


@pytest.mark.parametrize('kaynak, ad', [
    (SOLID_HTML, 'computeTrajectory'), (LIQUID_HTML, 'computeTrajectory'),
    (APP_JS, 'calculateTrajectory')], ids=['kati', 'sivi', 'hibrit'])
def test_yorunge_panellerinde_gizli_yedek_sayi_yok(kaynak, ad):
    govde = _yorumsuz(_islev_metin(kaynak, ad))
    kalan = re.findall(r"getv\('[^']+',\s*[0-9.]+\)", govde)
    kalan += re.findall(r"\?\.value \|\| [0-9.]+\)", govde)
    assert not kalan, f'{ad}: gizli yedek sayı kaldı: {kalan}'


def test_sivi_yorunge_lule_cikis_alanini_gonderir():
    """K-C1 DEVİR 4: sıvı yükü nozzle_exit_area + itkinin ortam basıncını
    taşır (katı/hibrit deseni); çıkış çapı adıyla mm alanından."""
    govde = _yorumsuz(_islev_metin(LIQUID_HTML, 'computeTrajectory'))
    assert 'body.nozzle_exit_area = Math.PI * Math.pow(_cikisMm / 2000, 2);' in govde
    assert 'cr.exit_diameter_mm' in govde
    assert 'body.thrust_reference_pressure = _pAmbBar * 1e5;' in govde


def test_sivi_yorunge_kutleleri_hesaptan_hemen_sonra_tohumlanir():
    """K-C1 AÇIK 6: tohumlama displayResults'tan da çağrılır; kullanıcı
    yazdıysa ezilmez; itici yoksa ilk kütle BOŞALTILIR (5000 kalmaz)."""
    assert 'liquidTrajectorySeed(results);' in _islev_metin(
        LIQUID_HTML, 'displayResults')
    tohum = _islev_metin(LIQUID_HTML, 'liquidTrajectorySeed')
    assert "el.dataset.userOverride === 'true'" in tohum
    assert ": null);" in tohum and "el.value = (deger === null) ? ''" in tohum


@pytest.fixture(scope='module')
def sivi_ornek_sonucu():
    from tests.test_example_projects import load_example_doc
    _mt, sonuc = fv.recompute_from_project(load_example_doc('liquid'))
    return sonuc


def test_sivi_lule_alani_uca_ulasir_ve_telafi_modellenir(client,
                                                        sivi_ornek_sonucu):
    """Sayfa gövdesinin kurduğu alan uçta itkiyi irtifayla telafi ettirir."""
    import math
    cr = sivi_ornek_sonucu
    perf = cr['design_summary']['performance']
    # Ölçülen birim: exit_diameter METRE, exit_diameter_mm mm (aynı çap).
    assert cr['exit_diameter_mm'] == pytest.approx(cr['exit_diameter'] * 1000,
                                                   rel=1e-12)
    m_son = cr['design_summary']['masses']['engine_mass_kg']
    m_bas = m_son + 275.65
    govde = dict(initial_mass=m_bas, final_mass=m_son, drag_coefficient=0.5,
                 reference_area=0.05,
                 burn_time=(m_bas - m_son) / cr['total_mass_flow'],
                 thrust=perf['thrust_sl_N'], isp=perf['isp_sl_s'])
    kapali = client.post('/api/trajectory-analysis', headers=HEADERS,
                         json=govde).get_json()
    govde['nozzle_exit_area'] = math.pi * (cr['exit_diameter_mm'] / 2000) ** 2
    govde['thrust_reference_pressure'] = (
        cr['nozzle_design']['performance']['ambient_pressure'] * 1e5)
    acik = client.post('/api/trajectory-analysis', headers=HEADERS,
                       json=govde).get_json()
    assert acik['status'] == 'success', acik
    def _modelled(j):
        def bul(d):
            if isinstance(d, dict):
                for k, v in d.items():
                    if k == 'thrust_altitude_compensation' and isinstance(v, dict):
                        return v.get('modelled')
                    r = bul(v)
                    if r is not None:
                        return r
            return None
        return bul(j)
    assert _modelled(kapali) is False
    assert _modelled(acik) is True


def test_okunmayan_hibrit_alanlari_adiyla_soylenir(client):
    govde = dict(thrust=3000, burn_time=10, isp=210, initial_mass=39.5,
                 final_mass=25, drag_coefficient=0.5, reference_area=0.0177,
                 launch_angle=90, wind_speed=0, trajectory_start_altitude=0)
    sade = client.post('/api/trajectory-analysis', headers=HEADERS,
                       json=govde).get_json()
    assert 'inputs_not_read' not in sade
    ek = client.post('/api/trajectory-analysis', headers=HEADERS, json=dict(
        govde, trajectory_end_altitude=10000, trajectory_points=20)).get_json()
    assert sorted(k['field'] for k in ek['inputs_not_read']) == [
        'trajectory_end_altitude', 'trajectory_points']
    # Sonuç sayıları değişmez (alanlar okunmuyor).
    assert ek['trajectory_data'] == sade['trajectory_data']


# ---------------------------------------------------------------------------
# NK-14 / NK-24 (üç motor tipi) — bayat motor yok; sıvıda tek kütle kaynağı
# ---------------------------------------------------------------------------

@needs_node
def test_degisen_motor_alanlari_cozucunun_okumadiklarini_saymaz():
    kaynak = """
    global.window = {location: {pathname: '/solid'},
        localStorage: {getItem(){return null}, setItem(){}, removeItem(){}}};
    %s
    var f = window.FlightHandoff.changedMotorFields;
    var sonuc = {wind_speed: 0, case_mass: 1.9, unwired_inputs: {
        informational: ['wind_speed'], structural_output: ['case_mass']},
        inputs_not_used: ['feed_pressure']};
    var son = {chamber_pressure: 40, wind_speed: 0, case_mass: 2.5, feed_pressure: 1};
    console.log(JSON.stringify({
        ayni: f(son, Object.assign({}, son, {wind_speed: 9, case_mass: 1.9,
                                              feed_pressure: 5}), sonuc),
        degisti: f(son, Object.assign({}, son, {chamber_pressure: 55}), sonuc),
        anliksiz: f(null, son, sonuc)}));
    """ % HANDOFF_JS
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (tests/test_node_cagri_sozlesmesi.py).
    cikti = subprocess.run([NODE], input=kaynak, capture_output=True,
                           text=True, timeout=30)
    assert cikti.returncode == 0, cikti.stderr
    r = json.loads(cikti.stdout.strip())
    assert r == {'ayni': [], 'degisti': ['chamber_pressure'], 'anliksiz': None}


@pytest.mark.parametrize('kaynak, anahtar', [
    (SOLID_HTML, 'solid.msg.trajectory_stale_motor'),
    (LIQUID_HTML, 'liq.js.trajectory_stale_motor')], ids=['kati', 'sivi'])
def test_kati_ve_sivi_yorunge_bayat_motoru_reddeder(kaynak, anahtar):
    govde = _yorumsuz(_islev_metin(kaynak, 'computeTrajectory'))
    assert 'FlightHandoff.changedMotorFields(_anlik.form' in govde
    assert anahtar in govde
    sozluk = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    assert sozluk.count("'" + anahtar + "':") == 2


def test_sivi_kutleleri_ucus_aracindan_tek_kaynak():
    tohum = _islev_metin(LIQUID_HTML, 'liquidTrajectorySeed')
    assert 'FlightHandoff.vehicleFor(cr)' in tohum
    assert 'arac.engine_inert_mass' in tohum and 'arac.propellant_mass' in tohum
    assert 'mas.engine_mass_kg' not in tohum, 'eski motor-yalnız kuralı kaldı'
    alti = _islev_metin(LIQUID_HTML, 'liquidSixDofSeed')
    for parca in ("yaz('sd_prop_m', arac.propellant_mass, 3);",
                  "yaz('sd_dry_m', arac.engine_inert_mass, 3);",
                  'arac.engine_od_m'):
        assert parca in alti, parca
    assert "addEventListener('hrma:flight-vehicle'" in LIQUID_HTML
    assert "new CustomEvent('hrma:flight-vehicle'" in HANDOFF_JS
