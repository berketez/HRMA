"""V306/UÇUŞ bekçileri — motordan uçuşa aktarım zinciri (3.0.6).

NR-13  uçuş kuru kütlesi tek sayı, kalemli (engine_inert_mass_items)
NR-10  "elle yazıldı" yalnız gerçek yazmadır; tasarım değeri ezmez ama yazar
NR-12  Fırlatma Sahası gövdesi kaynaktan; örnek araç kendi gövdesiyle;
       itici gövdeye sığmıyorsa uç adıyla söyler
NK-14  6-DOF formu sayfa motorunu her hesapta gösterir, kilitli ve beyanlı

Kanıt: docs/scofield/raw/OH/V306/ucus/ (önce/sonra ölçümleri, RAPOR.md).
"""
import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

from hrma.analysis import flight_vehicle as fv

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates'
node_gerekli = pytest.mark.skipif(shutil.which('node') is None,
                                  reason='node yok')


def _oku(yol):
    return pathlib.Path(yol).read_text(encoding='utf-8')


# --------------------------------------------------------------------- NR-13

def _sivi_sonuc():
    return {
        'thrust': 25000.0, 'burn_time': 30.0, 'total_mass_flow': 9.915,
        'design_summary': {'masses': {'propellant_mass_kg': 297.45,
                                      'engine_mass_kg': 78.649},
                           'key_dimensions': {'overall_length_with_closure_mm': 900.0}},
        'propellant_tanks': {
            'oxidizer_tank': {'dimensions': {'diameter': 475.0, 'length': 1140.0,
                                             'volume': 202.0}},
            'fuel_tank': {'dimensions': {'diameter': 380.0, 'length': 912.0,
                                         'volume': 103.4}},
            'system_summary': {'total_tank_mass': 34.925,
                               'total_propellant_mass': 342.068,
                               'total_propellant_mass_nominal': 297.45}},
    }


def test_sivi_atil_kutle_kalemleri_toplami_yayimlanan_sayidir():
    v = fv.normalize('liquid', _sivi_sonuc())
    kalem = v['engine_inert_mass_items']
    assert [k['key'] for k in kalem] == ['engine_dry', 'tank_structure',
                                        'reserve_propellant']
    toplam = 0.0
    for k in kalem:
        toplam += k['mass_kg']
    # Toplam KALEMLERDEN kurulur: ekrandaki kalem satırı ile sayı tek hesap.
    assert v['engine_inert_mass'] == toplam
    assert v['engine_inert_mass'] == pytest.approx(78.649 + 34.925 + 44.618)
    # Künye aynı kalemleri söyler (eski metin biçimi korunur).
    assert 'propellant tank dry structure 34.925 kg' in v['engine_inert_mass_note']


def test_kati_ve_hibrit_tek_kalem():
    kati = fv.normalize('solid', {'design_summary': {'masses': {'dry_mass_kg': 3.734}}})
    assert kati['engine_inert_mass_items'] == [{'key': 'engine_dry', 'mass_kg': 3.734}]
    assert kati['propellant_volume_m3'] == 0.0
    hib = fv.normalize('hybrid', {'motor': {'design_summary': {'key_dimensions': {
        'dry_mass_estimate_kg': 13.284}}, 'propellant_mass_total': 14.56}})
    assert hib['engine_inert_mass_items'] == [
        {'key': 'engine_dry_estimate', 'mass_kg': 13.284}]
    # Tank geometrisi yayımlanmamış hibrit: hacim BİLİNMİYOR (uydurulmaz).
    assert hib['propellant_volume_m3'] is None


# --------------------------------------------------------------------- NR-12

def test_turetilen_govde_motoru_ve_tanklari_tasir():
    v = fv.normalize('liquid', dict(_sivi_sonuc(), chamber_diameter=246.0))
    g = v['airframe_resolved']
    assert g['source'] == 'derived'
    assert g['airframe_dry_mass_kg'] is None           # türetilmez
    assert g['body_diameter_m'] == pytest.approx(0.475)  # en geniş tank
    assert 'HRMA choice' in g['basis']
    # Türetilen gövde tankları KESİN taşır (hacim denetimi boş).
    burun = 0.5
    boy = burun + (g['length_behind_nose_m'] or 0.0)
    assert fv.airframe_volume_conflicts(
        v['propellant_volume_m3'], v['engine_length_m'], g['body_diameter_m'],
        boy, burun) == []


def test_tank_geometrisi_yoksa_sivi_govde_boyu_uydurulmaz():
    s = _sivi_sonuc()
    del s['propellant_tanks']
    v = fv.normalize('liquid', s)
    assert v['propellant_volume_m3'] is None
    assert v['airframe_resolved']['length_behind_nose_m'] is None


def test_sigmayan_itici_adiyla():
    c = fv.airframe_volume_conflicts(0.358, 0.9, 0.246, 3.0, 0.5)
    assert len(c) == 1 and c[0]['reason'] == 'propellant_does_not_fit'
    beklenen = math.pi / 4 * 0.246 ** 2 * (3.0 - 0.5 - 0.9)
    assert c[0]['body_volume_available_m3'] == pytest.approx(beklenen)
    # bilinmeyen hacim / gövde -> denetim yok
    assert fv.airframe_volume_conflicts(None, 0.9, 0.246, 3.0, 0.5) == []
    assert fv.airframe_volume_conflicts(0.3, 0.9, None, 3.0, 0.5) == []


def test_ornek_arac_kendi_govdesiyle_tek_tanim():
    ex = fv.EXAMPLE_VEHICLE
    g = ex['airframe_resolved']
    assert g['source'] == 'example'
    assert (g['body_diameter_m'], g['body_length_m'], g['airframe_dry_mass_kg']) == (
        0.15, 3.0, 18.0)
    html = _oku(SABLON / 'launch_site.html')
    # Şablonda ikinci bir sayı tablosu yok: tanım Jinja ile gömülür.
    assert 'id="ls-example-vehicle">{{ example_vehicle | tojson }}' in html
    assert 'thrust: 6500' not in html


def test_proje_govdesi_varsa_ondan():
    g = fv.project_airframe({'body_diameter': 0.2, 'body_length': 2.5,
                             'airframe_dry_mass': 9.0, 'baska': 'x'})
    assert g['source'] == 'project'
    assert (g['body_diameter_m'], g['body_length_m'], g['airframe_dry_mass_kg']) == (
        0.2, 2.5, 9.0)
    assert fv.project_airframe({'baska': 1}) is None


@pytest.fixture
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def test_ucus_sayfasi_ornek_araci_gomer(istemci):
    r = istemci.get('/launch-site')
    assert r.status_code == 200
    m = re.search(r'id="ls-example-vehicle">(.*?)</script>', r.get_data(as_text=True), re.S)
    assert m
    v = json.loads(m.group(1))
    assert v['airframe_resolved']['body_diameter_m'] == 0.15


def test_6dof_ucu_sigmazligi_yayimlar(istemci):
    govde = {'body_diameter': 0.246, 'body_length': 3.0, 'nose_length': 0.5,
             'dry_mass': 176.0, 'propellant_mass': 297.45, 'thrust': 25000.0,
             'burn_time': 30.0, 'engine_od_m': 0.243, 'engine_length_m': 0.9,
             'propellant_volume_m3': 0.358, 't_max': 120}
    r = istemci.post('/api/six-dof-analysis', json=govde)
    d = r.get_json()
    assert r.status_code == 200, d
    assert d['airframe_volume_conflicts'][0]['reason'] == 'propellant_does_not_fit'
    govde['propellant_volume_m3'] = -1
    assert istemci.post('/api/six-dof-analysis', json=govde).status_code == 422


# --------------------------------------------------------- NR-10 (JS, node)

_DOM = r"""
var DUGUMLER = {};
function oge(id) {
  var d = { id: id, value: '', dataset: {}, _cls: {}, style: {},
    classList: { toggle: function (c, on) { d._cls[c] = !!on; },
                 remove: function (c) { d._cls[c] = false; },
                 add: function (c) { d._cls[c] = true; } },
    insertAdjacentElement: function (yer, el) { DUGUMLER[el.id] = el; el.parentNode = {
        removeChild: function () { delete DUGUMLER[el.id]; } }; },
    remove: function () { delete DUGUMLER[d.id]; },
    appendChild: function (c) { (d._cocuk = d._cocuk || []).push(c); },
    addEventListener: function (n, f) { d['_on' + n] = f; },
    dispatchEvent: function () {} };
  Object.defineProperty(d, 'textContent', { get: function () {
      return (d._metin || '') + (d._cocuk || []).map(function (c) { return c.textContent; }).join(''); },
    set: function (v) { d._metin = v; d._cocuk = []; } });
  return d;
}
var document = { getElementById: function (id) { return DUGUMLER[id] || null; },
  createElement: function () { return oge('_' + Math.random()); },
  dispatchEvent: function () {} };
var window = { document: document, localStorage: { getItem: function () { return null; } } };
global.Event = function (n) { this.type = n; };
"""


def _node(govde):
    betik = _DOM + _oku(JS / 'flight_handoff.js') + '\n' + govde
    # Betik stdin'den verilir (test_node_cagri_sozlesmesi: argv ile betik
    # geçirmek Linux MAX_ARG_STRLEN / macOS ARG_MAX tavanına takılır).
    sonuc = subprocess.run(['node'], input=betik, capture_output=True, text=True,
                           timeout=30)
    assert sonuc.returncode == 0, sonuc.stderr
    return json.loads(sonuc.stdout.strip().splitlines()[-1])


@node_gerekli
def test_yapay_olay_elle_yazma_sayilmaz():
    r = _node("console.log(JSON.stringify({yapay: window.FlightHandoff.isUserEdit({isTrusted: false}),"
              " gercek: window.FlightHandoff.isUserEdit({isTrusted: true})}));")
    assert r == {'yapay': False, 'gercek': True}


@node_gerekli
def test_tohum_yazilmayani_gunceller_yazilani_korur_ve_yazar():
    r = _node(r"""
      var FH = window.FlightHandoff;
      var a = oge('a'); DUGUMLER.a = a; a.value = '6.141';
      var kalan = FH.seedField(a, 6.088995, 3, 'kg');
      var b = oge('b'); DUGUMLER.b = b; b.value = '4.5'; b.dataset.userOverride = 'true';
      var kalanB = FH.seedField(b, 3.734, 3, 'kg');
      var not = DUGUMLER['b_tasarim_notu'];
      var c = oge('c'); DUGUMLER.c = c; c.value = '7';
      FH.seedField(c, null, 3, 'kg');
      console.log(JSON.stringify({a: a.value, kalan: kalan, b: b.value, kalanB: kalanB,
        not: not ? not.textContent : null, farkli: !!b._cls['ucus-elle-farkli'], c: c.value}));
    """)
    assert r['a'] == '6.089' and r['kalan'] == pytest.approx(6.088995)
    assert r['b'] == '4.5' and r['kalanB'] == 4.5 and r['farkli'] is True
    assert '3.734' in r['not']
    assert r['c'] == ''          # motora ait sayı yoksa alan boşalır


@node_gerekli
def test_kalem_satiri_ve_fark():
    r = _node(r"""
      var v = {engine_inert_mass: 13.284, engine_inert_mass_items: [{key: 'engine_dry_estimate', mass_kg: 13.284}]};
      var s = {engine_inert_mass: 158.191, engine_inert_mass_items: [
        {key: 'engine_dry', mass_kg: 78.649}, {key: 'tank_structure', mass_kg: 34.925},
        {key: 'reserve_propellant', mass_kg: 44.617}]};
      console.log(JSON.stringify({h: window.FlightHandoff.inertLedgerText(v, 25),
        alt: window.FlightHandoff.inertLedgerText(v, 10),
        s: window.FlightHandoff.inertLedgerText(s, 158.191),
        yok: window.FlightHandoff.inertLedgerText(null, 5)}));
    """)
    assert '11.716' in r['h'] and 'not from the engine' in r['h']
    assert 'BELOW' in r['alt']
    assert '78.649' in r['s'] and '= 158.191 kg' in r['s'] and 'This field' not in r['s']
    assert r['yok'] == ''


def test_yorunge_dinleyicileri_yalniz_gercek_yazmayi_damgalar():
    for ad in ('solid.html', 'liquid.html'):
        html = _oku(SABLON / ad)
        i = html.index("t.id === 'traj_initial_mass'") if ad == 'liquid.html' \
            else html.index("'traj_ref_area', 'traj_burn_time'].forEach")
        blok = html[i:i + 900]
        assert 'FlightHandoff.isUserEdit(e)' in blok, ad


# --------------------------------------------------------------------- NK-14

def test_6dof_formu_her_hesapta_sayfa_motoruyla_dolar():
    js = _oku(JS / 'sixdof_panel.js')
    i = js.index("document.addEventListener('hrma:flight-vehicle'")
    assert 'sayfaMotorunuEsitle()' in js[i:i + 400]
    # sayfa motoru uçarken itki ve yanma süresi alanları kilitli
    j = js.index('function itkiAlanlariniKilitle')
    assert "el.readOnly = kilitli" in js[j:j + 400]
    # satır ham kimlik basmaz
    assert "id + ' = ' + sayiEkran" not in js
    assert "badge('max_speed '" not in js
