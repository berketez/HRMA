"""V306/TERMAL-KONTUR bekçileri — Termal Güvenlik panelinin ıslak alanı
motorun KENDİ nozulundan (3.0.6 bakım hattı, KILAVUZ K-P4, 9 Kas 2026).

Kusur (ölçüldü, taban 085d9adf7, docs/scofield/raw/OH/V306/termal-kontur/
olcum/once_ornek.json): ``/analyze_thermal_safety`` nozul geometrisini beyaz
listesine almıyor, panel de göndermiyordu; ıslak alan integrali (sıcak gaz
yüzeyi → toplam ısı gücü → ısı enerjisi → ısı kuyusu kütlesi) her koşuda
örnekleyicinin JENERİK çıkış çapı ve lüle tipiyle alınıyordu.

Kâhinler üründen türetilmez: ıslak lüle alanı yayımlanan konturun KENDİ
noktaları üstünde bağımsız yamuk integraliyle (2πr·ds) karşılaştırılır;
uç sonucu modülün doğrudan çağrısıyla bit-aynı olmalıdır (uç konturu
dönüştürmeden geçirir). Ölçüm ve kanıt: docs/scofield/raw/OH/V306/
termal-kontur/ (RAPOR.md).
"""
import json
import math
import pathlib
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'P11' / 'B4-repro-03.js'
THERMAL_JS = 'hrma/static/js/panels/thermal_panel.js'
H = {'Host': '127.0.0.1:8080'}
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None, reason='node kurulu değil: panel davranışı ölçülemez')

#: Islak lüle alanının (41 istasyon, kontur üstünde enterpolasyon) konturun
#: kendi noktalarındaki yamuk integralinden sapması. ÖLÇÜLDÜ (üç örnek
#: motor, olcum/alan_kahini.json): ≤ 7,1e-4 bağıl. Jenerik lüleyle alınan
#: alan ise motorun lülesinden +%113 (katı), −%82 (sıvı), +%21 (hibrit)
#: ayrışıyordu. Eşik istasyon ayrıklaştırmasını geçirir, başka lüleyi geçirmez.
ALAN_AYRIKLASTIRMA_TOL = 5e-3

_HESAP_UCU = {'solid': '/calculate_solid', 'liquid': '/calculate_liquid',
              'hybrid': '/calculate'}


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    import os
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('hrma_projeler_tk')))
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def motorlar(client):
    """Üç örnek projenin GERÇEK motor sözlüğü (hibritte ``.motor``)."""
    from tests.test_example_projects import NAMES, calculate_payload
    out = {}
    for tur in ('solid', 'liquid', 'hybrid'):
        with open(REPO_ROOT / 'examples' / (NAMES[tur] + '.hrma'),
                  encoding='utf-8') as f:
            fields = json.load(f)['inputs']['fields']
        if tur == 'solid':
            r = client.post('/calculate_solid',
                            json=calculate_payload(tur, fields), headers=H)
        elif tur == 'liquid':
            r = client.post('/calculate_liquid',
                            json=calculate_payload(tur, fields), headers=H)
        else:
            r = client.post('/calculate',
                            json=calculate_payload(tur, fields), headers=H)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        js = r.get_json()
        out[tur] = js.get('motor') if isinstance(js.get('motor'), dict) else js
    return out


def _govde(m, **ek):
    """Termal ucun çekirdek gövdesi motorun SI geometri bloğundan."""
    g = m['motor_geometry']
    b = {'chamber_pressure': 30.0, 'chamber_temperature': 3000.0,
         'chamber_diameter': g['chamber_diameter'],
         'chamber_length': g['chamber_length'], 'burn_time': 5.0,
         'mdot_total': 1.0, 'wall_thickness': 0.003,
         'throat_diameter': g['throat_diameter']}
    b.update(ek)
    return b


def _kontur(m):
    return {'points': m['nozzle_contour']['points']}


def _uc(client, govde):
    return client.post('/analyze_thermal_safety', json=govde, headers=H)


def _ham_lule_alani(pts):
    return sum(2.0 * math.pi * 0.5 * (a[1] + b[1])
               * math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(pts, pts[1:]))


# ---------------------------------------------------------------------------
# Kalem 1 — uç motorun nozul geometrisini kabul eder
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('tur', ['solid', 'liquid', 'hybrid'])
def test_kontur_islak_alana_girer(client, motorlar, tur):
    m = motorlar[tur]
    pts = m['nozzle_contour']['points']
    r = _uc(client, _govde(m, nozzle_contour=_kontur(m),
                           nozzle_type=m['nozzle_angles']['nozzle_type']))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    gsa = r.get_json()['thermal_analysis']['gas_side_analysis']
    wib = gsa['wetted_integral_contour_basis']
    assert wib['origin'] == 'motor_published_contour'
    assert wib['generic_defaults_used'] == []
    assert wib['contour_points'] == len(pts)
    ham = _ham_lule_alani(pts)
    assert abs(gsa['nozzle_wetted_area'] - ham) / ham < ALAN_AYRIKLASTIRMA_TOL
    # Toplam = silindirik gövde + enjektör yüzü + lüle (analitik parça).
    g = m['motor_geometry']
    govde_alani = (math.pi * g['chamber_diameter'] * g['chamber_length']
                   + math.pi * (g['chamber_diameter'] / 2.0) ** 2)
    assert gsa['surface_area'] == pytest.approx(
        govde_alani + gsa['nozzle_wetted_area'], rel=1e-12)


def test_uc_konturu_donusturmeden_gecirir(client, motorlar):
    """Tek büyüklük, tek sayı: uç ile modülün doğrudan çağrısı bit-aynı."""
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
    m = motorlar['liquid']
    govde = _govde(m, nozzle_contour=_kontur(m), nozzle_type='bell_80',
                   material='steel', cooling_type='natural')
    js = _uc(client, govde).get_json()['thermal_analysis']
    md = {k: v for k, v in govde.items()
          if k not in ('material', 'cooling_type', 'wall_thickness')}
    dogrudan = HeatTransferAnalyzer().analyze_heat_transfer(
        md, material='steel', wall_thickness=0.003, cooling_type='natural')
    for yol in (('gas_side_analysis', 'surface_area'),
                ('gas_side_analysis', 'total_heat_rate'),
                ('cooling_analysis', 'peak_heat_rate'),
                ('cooling_analysis', 'total_heat_energy'),
                ('cooling_analysis', 'heat_sink_mass')):
        assert js[yol[0]][yol[1]] == dogrudan[yol[0]][yol[1]], yol


def test_genlesme_orani_ve_tip_jenerik_birakmaz(client, motorlar):
    m = motorlar['solid']
    js = _uc(client, _govde(m, expansion_ratio=m['expansion_ratio'],
                            nozzle_type='conical')).get_json()
    wib = js['thermal_analysis']['gas_side_analysis'][
        'wetted_integral_contour_basis']
    assert wib['origin'] == 'sampled_from_geometry_fields'
    assert wib['generic_defaults_used'] == []
    assert 'expansion_ratio' in wib['exit_diameter_source']


def test_geometri_yoksa_beyanli_jenerik_yol_kalir(client, motorlar):
    js = _uc(client, _govde(motorlar['solid'])).get_json()
    wib = js['thermal_analysis']['gas_side_analysis'][
        'wetted_integral_contour_basis']
    assert wib['origin'] == 'sampled_from_geometry_fields'
    assert wib['generic_defaults_used'] == ['exit_diameter', 'nozzle_type']
    assert 'nozzle_contour_fields_not_read' not in js


def test_kontur_blogunun_okunmayan_anahtarlari_adiyla(client, motorlar):
    m = motorlar['hybrid']
    js = _uc(client, _govde(m, nozzle_contour=m['nozzle_contour'])).get_json()
    assert js['status'] == 'success'
    assert set(js['nozzle_contour_fields_not_read']['fields']) == (
        set(m['nozzle_contour']) - {'points'})


def _bozuk(m):
    pts = [list(p) for p in m['nozzle_contour']['points']]
    g = m['motor_geometry']
    return {
        'not_an_object': {'nozzle_contour': [1, 2, 3]},
        'points_missing_or_too_few': {'nozzle_contour': {'points': pts[:2]}},
        'point_not_a_finite_pair': {'nozzle_contour': {
            'points': pts[:5] + [[pts[5][0], 'nan']] + pts[6:]}},
        'point_not_a_finite_pair#bool': {'nozzle_contour': {
            'points': [[True, 0.04]] + pts[1:]}},
        'z_not_strictly_increasing': {'nozzle_contour': {
            'points': [pts[1]] + [pts[0]] + pts[2:]}},
        'radius_not_positive': {'nozzle_contour': {
            'points': pts[:3] + [[pts[3][0], -0.01]] + pts[4:]}},
        'no_interior_throat': {'nozzle_contour': {
            'points': [p for p in pts if p[0] <= pts[min(
                range(len(pts)), key=lambda i: pts[i][1])][0]]}},
        # Birim hatası: milimetre kontur hazne çapıyla 1000 kat çelişir.
        'conflicting_values#mm': {'nozzle_contour': {
            'points': [[p[0] * 1000.0, p[1] * 1000.0] for p in pts]}},
        'conflicting_values#bogaz': {'nozzle_contour': {'points': pts},
                                     'throat_diameter':
                                         g['throat_diameter'] * 1.01},
        'conflicting_values#cikis': {'nozzle_contour': {'points': pts},
                                     'exit_diameter': g['exit_diameter'] * 1.02},
        'conflicting_values#eps': {'nozzle_contour': {'points': pts},
                                   'expansion_ratio':
                                       m['expansion_ratio'] * 1.05},
        'unsupported_value': {'nozzle_type': 'peynir'},
        'must_exceed_unity': {'expansion_ratio': 0.9},
        'not_above_throat_diameter': {
            'exit_diameter': g['throat_diameter'] * 0.5},
        'both_supplied_without_throat_diameter': {
            'throat_diameter': None, 'exit_diameter': g['exit_diameter'],
            'expansion_ratio': m['expansion_ratio']},
    }


_BOZUK_DURUMLAR = (
    'not_an_object', 'points_missing_or_too_few', 'point_not_a_finite_pair',
    'point_not_a_finite_pair#bool', 'z_not_strictly_increasing',
    'radius_not_positive', 'no_interior_throat', 'conflicting_values#mm',
    'conflicting_values#bogaz', 'conflicting_values#cikis',
    'conflicting_values#eps', 'unsupported_value', 'must_exceed_unity',
    'not_above_throat_diameter', 'both_supplied_without_throat_diameter')


@pytest.mark.parametrize('durum', _BOZUK_DURUMLAR)
def test_bozuk_geometri_adiyla_reddedilir(client, motorlar, durum):
    m = motorlar['solid']
    tablo = _bozuk(m)
    assert set(tablo) == set(_BOZUK_DURUMLAR)
    ek = tablo[durum]
    govde = _govde(m)
    for k, v in ek.items():
        if v is None:
            govde.pop(k, None)
        else:
            govde[k] = v
    r = _uc(client, govde)
    assert r.status_code == 422, (durum, r.status_code,
                                  r.get_data(as_text=True)[:300])
    js = r.get_json()
    assert js['error'] == 'invalid_thermal_input'
    neden = durum.split('#')[0]
    assert neden in {k['reason'] for k in js['invalid_fields']}, js
    assert 'thermal_analysis' not in js


def test_celiski_artik_500_degil(client, motorlar):
    """Modülün throat_diameter ⟷ throat_area çelişkisi: 500 → 422 (alan adıyla)."""
    m = motorlar['solid']
    d_t = m['motor_geometry']['throat_diameter']
    r = _uc(client, _govde(m, throat_area=0.9 * math.pi * (d_t / 2.0) ** 2))
    assert r.status_code == 422, r.get_data(as_text=True)[:300]
    js = r.get_json()
    assert js['error'] == 'invalid_thermal_input'
    assert set(js['conflicting_fields'][0]['fields']) == {
        'throat_diameter', 'throat_area'}


# ---------------------------------------------------------------------------
# Kalem 2 — panel motorun geometrisini gönderir; künye kaynağı söyler
# ---------------------------------------------------------------------------
_BAGLAM_EV = (
    "var spec = window.AnalysisDock._registry.filter(function (s) {"
    "  return s.id === 'thermal'; })[0];"
    "try { window.AnalysisDock.init({motorType: body.motorType,"
    "  resultsProvider: function () { return body.sonuc; }}); } catch (e) {}"
    "var temiz = spec.contextFromResults(body.sonuc);"
    "window.currentResults = body.sonuc;"
    "var eksenel = window.ThermalPanel._readAxialPayload();"
    "document.getElementById('ad_f_thermal_throat_diameter').dataset.dirty = '1';"
    "var kirli = spec.contextFromResults(body.sonuc);"
    "var eksenelKirli = window.ThermalPanel._readAxialPayload();"
    "return {temiz: temiz, kirli: kirli, eksenel: eksenel,"
    "        eksenelKirli: eksenelKirli};")


def _node(cfg):
    from tests.support.kanit import kanit_gerekli
    p = subprocess.run([NODE, kanit_gerekli(str(HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=180, cwd=str(REPO_ROOT))
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


@node_gerekli
@pytest.mark.parametrize('tur', ['solid', 'liquid', 'hybrid'])
def test_panel_motorun_konturunu_gonderir(motorlar, tur):
    import tests.test_v3_yapi_sf as T
    m = motorlar[tur]
    # Hibrit yanıtı `.motor` altında iç içedir; katı/sıvı düzdür (güverte
    # motorDict sözleşmesi) — panel aynı yolu okumalı.
    sonuc = {'motor': m} if tur == 'hybrid' else m
    out = _node({'panelId': '_yok', 'panelFiles': [THERMAL_JS],
                 'dataInline': {'motorType': tur,
                                'sonuc': T._json_guvenli(sonuc)},
                 'evalFn': _BAGLAM_EV})['evaled']
    assert '_err' not in out, out
    tip = m['nozzle_angles']['nozzle_type']
    assert out['temiz']['nozzle_contour']['points'] == m['nozzle_contour']['points']
    assert out['temiz']['nozzle_type'] == tip
    assert 'expansion_ratio' not in out['temiz']
    # Eksenel profil aynı geometriyi gönderir (tek kaynak).
    assert out['eksenel']['nozzle_contour']['points'] == m['nozzle_contour']['points']
    # Boğaz kutusu elle değiştirildi: motorun konturu o boğaza ait değil.
    assert 'nozzle_contour' not in out['kirli']
    assert out['kirli']['expansion_ratio'] == m['expansion_ratio']
    assert out['kirli']['nozzle_type'] == tip
    assert 'nozzle_contour' not in out['eksenelKirli']


def _render(veri):
    return _node({'panelId': 'thermal', 'panelFiles': [THERMAL_JS],
                  'dataInline': veri})


@node_gerekli
def test_kunye_motorun_nozulu_der(client, motorlar):
    m = motorlar['liquid']
    veri = _uc(client, _govde(m, nozzle_contour=_kontur(m),
                              nozzle_type='bell_80')).get_json()
    out = _render(veri)
    assert out['error'] is None, out['error']
    n = len(m['nozzle_contour']['points'])
    assert ("motor's nozzle (published contour, %d points)" % n) in out['text']
    assert 'data-thermal-contour-origin="motor_published_contour"' in out['html']
    assert 'data-thermal-generic-contour' not in out['html']
    assert 'data-thermal-derived-generic' not in out['html']
    assert 'generic nozzle contour' not in out['text']


@node_gerekli
def test_kunye_tr(client, motorlar):
    from tests.test_v3_kucuk import _panel_tr
    m = motorlar['liquid']
    veri = _uc(client, _govde(m, nozzle_contour=_kontur(m),
                              nozzle_type='bell_80')).get_json()
    n = len(m['nozzle_contour']['points'])
    metin = _panel_tr('thermal', THERMAL_JS, veri)
    assert ('motorun nozulu (yayımlanan kontur, %d nokta)' % n) in metin
    assert 'jenerik nozul konturu' not in metin
    veri2 = _uc(client, _govde(m, expansion_ratio=m['expansion_ratio'],
                               nozzle_type='bell_80')).get_json()
    assert ('nozul konturu verilen nozul boyutu ve tipinden çizildi'
            in _panel_tr('thermal', THERMAL_JS, veri2))
    assert ('nozzle contour drawn from the supplied nozzle size and type'
            in _panel_tr('thermal', THERMAL_JS, veri2, dil='en'))


@node_gerekli
def test_koken_alani_yoksa_kunye_iddia_etmez(client, motorlar):
    m = motorlar['liquid']
    veri = _uc(client, _govde(m, nozzle_contour=_kontur(m))).get_json()
    veri['thermal_analysis']['gas_side_analysis'][
        'wetted_integral_contour_basis'].pop('origin')
    out = _render(veri)
    assert 'data-thermal-contour-origin' not in out['html']
    assert "motor's nozzle" not in out['text']
