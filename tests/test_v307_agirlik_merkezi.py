"""V307/AĞIRLIK-MERKEZİ — türetilmiş gövdede ağırlık merkezi bileşenlerden.

Berke kararı (18 Kas, seçenek b): ağırlık merkezi ``flight_vehicle``'da TEK
tanımla motorun kütle kalemlerinden ve gövdenin dizilim tanımından kurulur;
sabit boy kesri (0,55·L / 0,50·L) bu yolda kalkar.

Ne kilitlenir (fizik ve sözleşme, bugünkü çıktı değil):
  * kütle korunumu: yerleşimin kuru toplamı motorun uçan atıl kütlesi +
    tankta kalan itici, yanan toplamı uçuşun yanan iticisidir;
  * ağırlık merkezi Σ m·x / Σ m'dir (elle kurulan küçük araçla); motordan
    gelmeyen kuru kütle L/2'de; sıvı sütunu tank tabanından h/2'de;
  * sıvı sütununun ağırlık merkezi çalkantı modelinin AYNI doluluk
    tanımından gelir (K1 silindir tablosunun z_km'iyle aynı sayı);
  * çözücü tabloyu kalan itici kütlesine göre okur; dolu/boş uçları tablodan;
  * uç: yerleşim varsa kaynak ``components``; kullanıcının x_cg'si
    ÖNCELİKLİ ve yanıt yerleşim hiç yokmuş gibi bit-aynı; uymayan kütle
    adıyla reddedilir (sayı uydurulmaz);
  * istemci yalnız yerleşimi taşır (ikinci ağırlık merkezi hesabı yok).
"""

import contextlib
import copy
import hashlib
import io
import json
import math
import pathlib

import pytest

from hrma.analysis import flight_vehicle as fv
from hrma.analysis import six_dof_trajectory as sdt

KOK = pathlib.Path(__file__).resolve().parents[1]

# Sentetik sıvı motor (yalnız bu testin fikstürü; ürün sayısı değil): iki
# tank, motor 0,6 m, tank iç ölçüleri ve baş kalınlıkları.
_TANKLAR = [
    {'key': 'oxidizer_tank', 'diameter_m': 0.40, 'length_m': 1.00,
     'volume_m3': math.pi / 4 * 0.40 ** 2 * 1.00,
     'wall_thickness_m': 0.003, 'end_closure_thickness_m': 0.003},
    {'key': 'fuel_tank', 'diameter_m': 0.36, 'length_m': 0.90,
     'volume_m3': math.pi / 4 * 0.36 ** 2 * 0.90,
     'wall_thickness_m': 0.003, 'end_closure_thickness_m': 0.003},
]
_SONUC = {'propellant_tanks': {
    'oxidizer_tank': {'structural': {'tank_mass': 12.0},
                      'propellant_data': {'mass': 115.0, 'mass_nominal': 100.0,
                                          'density': 1141.0}},
    'fuel_tank': {'structural': {'tank_mass': 8.0},
                  'propellant_data': {'mass': 46.0, 'mass_nominal': 40.0,
                                      'density': 815.0}},
}}
_MOTOR_BOYU = 0.6


def _sivi_arac():
    arac = {
        'motor_type': 'liquid',
        'engine_length_m': _MOTOR_BOYU,
        'engine_od_m': 0.25,
        'engine_inert_mass_items': [
            {'key': 'engine_dry', 'mass_kg': 50.0},
            {'key': 'tank_structure', 'mass_kg': 20.0},
            {'key': 'reserve_propellant', 'mass_kg': 21.0}],
        'flight_thrust': {'propellant_loaded_kg': 140.0,
                          'propellant_consumed_kg': 140.0,
                          'propellant_residual_kg': 0.0},
        'propellant_tanks': copy.deepcopy(_TANKLAR),
    }
    arac['engine_inert_mass'] = 91.0
    return arac


@pytest.fixture
def yerlesim():
    lay, neden = fv.mass_layout('liquid', _SONUC, _sivi_arac())
    assert neden is None, neden
    return lay


# --- yerleşim: kütle korunumu ve istasyonlar --------------------------------

def test_yerlesim_kutleyi_korur_ve_istasyonlar_dizilimden(yerlesim):
    # Kuru toplam = uçan atıl kütle (motor kuru + tank yapısı + yedek itici).
    assert yerlesim['dry_total_kg'] == pytest.approx(91.0, rel=1e-12)
    assert yerlesim['consumed_total_kg'] == pytest.approx(140.0, rel=1e-12)
    # Yedek itici sabit kalem DEĞİL, tanktaki sıvının parçası (iki kez yok).
    assert 'reserve_propellant' not in [k['key'] for k in yerlesim['inert']]
    yigin = fv.tank_stack(_TANKLAR, _MOTOR_BOYU)
    tabanlar = {t['key']: t['base_from_tail_m'] for t in yigin['tanks']}
    for p in yerlesim['propellant']:
        assert p['model'] == 'liquid_column'
        assert p['base_from_tail_m'] == tabanlar[p['key']]
    motor = [k for k in yerlesim['inert'] if k['key'] == 'engine_dry'][0]
    assert motor['x_from_tail_m'] == pytest.approx(_MOTOR_BOYU / 2)


def test_tank_yapisi_ayrimi_yayimlanmamissa_yerlesim_kurulmaz():
    sonuc = copy.deepcopy(_SONUC)
    del sonuc['propellant_tanks']['fuel_tank']['structural']['tank_mass']
    lay, neden = fv.mass_layout('liquid', sonuc, _sivi_arac())
    assert lay is None and neden == 'tank_structure_split_not_published'


# --- ağırlık merkezi: Σ m·x / Σ m -------------------------------------------

def _elle_cg(lay, L, ek, f):
    """Elle: sıvı sütunu tabandan h/2 (h = m/(ρ·π/4·D²)), ek kütle L/2."""
    m_top, mx = ek, ek * L / 2
    for k in lay['inert']:
        m_top += k['mass_kg']
        mx += k['mass_kg'] * k['x_from_tail_m']
    for p in lay['propellant']:
        m = p['loaded_kg'] - p['consumed_kg'] * f
        h = m / (p['density_kg_m3'] * math.pi / 4 * p['inner_diameter_m'] ** 2)
        m_top += m
        mx += m * (p['base_from_tail_m'] + h / 2)
    return L - mx / m_top


def test_agirlik_merkezi_bilesenlerden_elle_kurulanla_ayni(yerlesim):
    L, ek = 3.2, 15.0
    cg = fv.component_cg(yerlesim, L, 91.0 + ek, 140.0)
    assert cg['source'] == sdt.CG_SOURCE_COMPONENTS
    assert cg['airframe_dry_mass_not_from_engine_kg'] == pytest.approx(ek)
    assert cg['x_cg_full_m'] == pytest.approx(_elle_cg(yerlesim, L, ek, 0.0), abs=1e-9)
    assert cg['x_cg_empty_m'] == pytest.approx(_elle_cg(yerlesim, L, ek, 1.0), abs=1e-9)
    t = cg['table']
    assert t['propellant_kg'][0] == 0.0 and t['propellant_kg'][-1] == 140.0
    for P, x in zip(t['propellant_kg'], t['x_cg_m']):
        assert x == pytest.approx(_elle_cg(yerlesim, L, ek, 1.0 - P / 140.0), abs=1e-9)
    # Kesir tahmini bu yolda yok: boş araç motor ve yedek itici yüzünden kıça
    # yakındır (bu araçta 0,50·L'nin arkasında).
    assert cg['x_cg_empty_m'] > sdt.CG_ASSUMED_EMPTY_FRACTION * L


def test_sivi_sutunu_calkanti_modelinin_dolulugundan_ayni_sayi():
    from hrma.analysis import slosh_analysis as sa
    tablo = sa.silindir_tablosu('oksitleyici', 0.20, 1.00, 1141.0, 'LOX')
    for d in (0.05, 0.5, 0.95):
        m = d * 1141.0 * math.pi * 0.20 ** 2 * 1.00
        z = fv._liquid_column_centroid_m(0.40, 1.00, 1141.0, m)
        assert z == pytest.approx(tablo.ara(d)['z_km_m'], rel=1e-9)


@pytest.mark.parametrize('degisiklik, kod', [
    ({'propellant': 139.0}, 'PROPELLANT_MASS_DIFFERS'),
    ({'dry': 80.0}, 'DRY_MASS_BELOW_ENGINE'),
])
def test_uymayan_kutle_adiyla_reddedilir(yerlesim, degisiklik, kod):
    with pytest.raises(fv.CgLayoutRejected) as e:
        fv.component_cg(yerlesim, 3.2, degisiklik.get('dry', 91.0),
                        degisiklik.get('propellant', 140.0))
    assert e.value.code == kod


def test_sayfa_alani_yuvarlamasi_red_degil(yerlesim):
    # Panel kuru kütleyi 2, itici kütlesini 3 ondalıkla gönderir.
    cg = fv.component_cg(yerlesim, 3.2, 91.0 - 0.004, 140.0 + 0.0004)
    assert math.isfinite(cg['x_cg_full_m'])


@pytest.mark.parametrize('bozuk, kod', [
    (lambda y: y.update(schema='x'), 'LAYOUT_SCHEMA'),
    (lambda y: y['inert'].extend([{'key': 'k', 'mass_kg': 0.0,
                                   'x_from_tail_m': 0.1}] * 20), 'LAYOUT_SIZE'),
    (lambda y: y['inert'][0].update(mass_kg=float('nan')), 'LAYOUT_NUMBER_INVALID'),
    (lambda y: y['inert'][0].update(mass_kg=True), 'LAYOUT_NUMBER_INVALID'),
    (lambda y: y['propellant'][0].update(base_from_tail_m=9.0), 'ITEM_OUTSIDE_BODY'),
    (lambda y: y['propellant'][0].update(model='eval'), 'LAYOUT_SCHEMA'),
])
def test_yerlesim_kapisi_saldirgan_girdi(yerlesim, bozuk, kod):
    y = copy.deepcopy(yerlesim)
    bozuk(y)
    with pytest.raises(fv.CgLayoutRejected) as e:
        fv.component_cg(y, 3.2, 91.0, 140.0)
    assert e.value.code == kod


# --- çözücü: tablo -----------------------------------------------------------

def _aero(L=3.2):
    return sdt.BarrowmanAero(body_diameter=0.42, nose_length=0.5, body_length=L,
                             nose_type='ogive', fin_count=4, fin_root_chord=0.5,
                             fin_tip_chord=0.25, fin_span=0.6, fin_sweep=0.2)


def test_cozucu_tabloyu_kalan_itici_kutlesine_gore_okur(yerlesim):
    cg = fv.component_cg(yerlesim, 3.2, 106.0, 140.0)
    s = sdt.SixDOFTrajectory(_aero(), 106.0, 140.0, thrust=20000.0,
                             burn_time=10.0, x_cg_table=cg['table'])
    assert s.x_cg_source == sdt.CG_SOURCE_COMPONENTS
    assert s.x_cg_full == cg['x_cg_full_m'] and s.x_cg_empty == cg['x_cg_empty_m']
    assert s._cg_at(0.0) == pytest.approx(cg['x_cg_full_m'], abs=1e-12)
    assert s._cg_at(10.0) == pytest.approx(cg['x_cg_empty_m'], abs=1e-12)
    # Yanmanın ortasında tablo (sıvı sütunu + kütle ağırlıklı ortalama), uçların
    # doğrusal ara değeri değil.
    yarim = s._mass_at(5.0) - s.m_dry
    import numpy as np
    assert s._cg_at(5.0) == pytest.approx(float(np.interp(
        yarim, cg['table']['propellant_kg'], cg['table']['x_cg_m'])), abs=1e-12)


def test_cozucu_tablo_kapisi_ve_elle_cg_ile_birlikte_gelemez(yerlesim):
    cg = fv.component_cg(yerlesim, 3.2, 106.0, 140.0)
    with pytest.raises(ValueError):
        sdt.SixDOFTrajectory(_aero(), 106.0, 140.0, thrust=20000.0, burn_time=10.0,
                             x_cg_full=1.5, x_cg_empty=1.6, x_cg_table=cg['table'])
    kotu = {'propellant_kg': [0.0, 100.0], 'x_cg_m': [1.0, 1.0]}
    with pytest.raises(ValueError):
        sdt.SixDOFTrajectory(_aero(), 106.0, 140.0, thrust=20000.0, burn_time=10.0,
                             x_cg_table=kotu)
    disari = {'propellant_kg': [0.0, 140.0], 'x_cg_m': [1.0, 9.0]}
    with pytest.raises(ValueError):
        sdt.SixDOFTrajectory(_aero(), 106.0, 140.0, thrust=20000.0, burn_time=10.0,
                             x_cg_table=disari)


# --- uç ----------------------------------------------------------------------

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _istek(lay=None, **ek):
    g = {'body_diameter': 0.42, 'body_length': 3.2, 'nose_length': 0.5,
         'nose_type': 'ogive', 'fin_count': 4, 'fin_root_chord': 0.5,
         'fin_tip_chord': 0.25, 'fin_span': 0.6, 'fin_sweep': 0.2,
         'dry_mass': 106.0, 'propellant_mass': 140.0, 'thrust': 20000.0,
         'burn_time': 10.0, 'wind_speed': 0.0, 't_max': 120.0,
         'rail_length': 5.0}
    if lay is not None:
        g['mass_layout'] = lay
    g.update(ek)
    return g


def _post(client, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = client.post('/api/six-dof-analysis', json=govde)
    return r.status_code, r.get_json()


def _md5(y):
    return hashlib.md5(json.dumps({k: v for k, v in y.items()
                                   if k != 'solver_wall_time_s'},
                                  sort_keys=True, default=str).encode()).hexdigest()


def test_uc_yerlesimle_bilesen_agirlik_merkezi_kullanir(client, yerlesim):
    kod, y = _post(client, _istek(yerlesim))
    assert kod == 200, y
    cg = fv.component_cg(yerlesim, 3.2, 106.0, 140.0)
    assert y['stability_basis']['x_cg_source'] == 'components'
    assert y['summary']['x_cg_full'] == cg['x_cg_full_m']
    assert y['summary']['x_cg_empty'] == cg['x_cg_empty_m']
    assert y['stability_basis']['x_cg_components'][
        'airframe_dry_mass_not_from_engine_kg'] == pytest.approx(15.0)
    # Statik marj bu ağırlık merkezinden: (x_cp − x_cg)/d.
    s = y['summary']
    assert s['static_margin_empty'] == pytest.approx(
        (s['x_cp'] - cg['x_cg_empty_m']) / 0.42, abs=1e-9)


def test_uc_kullanicinin_agirlik_merkezi_oncelikli_ve_bit_ayni(client, yerlesim):
    kod1, y1 = _post(client, _istek(None, x_cg_full=1.6, x_cg_empty=1.7))
    kod2, y2 = _post(client, _istek(yerlesim, x_cg_full=1.6, x_cg_empty=1.7))
    assert kod1 == kod2 == 200
    assert y2['stability_basis']['x_cg_source'] == 'supplied'
    assert _md5(y1) == _md5(y2)


def test_uc_yerlesimsiz_istek_eski_kesir_yolunda(client):
    kod, y = _post(client, _istek(None))
    assert kod == 200
    assert y['stability_basis']['x_cg_source'] == 'assumed_length_fraction'
    assert y['summary']['x_cg_full'] == pytest.approx(
        sdt.CG_ASSUMED_FULL_FRACTION * 3.2)


def test_uc_uymayan_kutle_adli_422(client, yerlesim):
    kod, y = _post(client, _istek(yerlesim, propellant_mass=120.0))
    assert kod == 422
    assert y['error'] == 'centre_of_gravity_not_built'
    assert y['invalid_fields'][0]['reason'] == 'PROPELLANT_MASS_DIFFERS'
    kod, y = _post(client, _istek({'schema': 'x'}))
    assert kod == 422 and y['invalid_fields'][0]['reason'] == 'LAYOUT_SCHEMA'


# --- istemci: yalnız taşır ----------------------------------------------------

def test_panel_ve_firlatma_sahasi_yerlesimi_tasir_hesaplamaz():
    js = (KOK / 'hrma/static/js/sixdof_panel.js').read_text(encoding='utf-8')
    assert 'payload.mass_layout = yerlesim' in js
    assert 'arac.airframe_resolved.mass_layout' in js
    html = (KOK / 'hrma/templates/launch_site.html').read_text(encoding='utf-8')
    assert 'veh.airframe_resolved.mass_layout' in html
    # İstemcide ikinci bir sıvı sütunu / bileşen ağırlık merkezi hesabı yok.
    for kaynak in (js, html):
        assert 'base_from_tail_m' not in kaynak
        assert 'x_from_tail_m' not in kaynak


def test_ekran_metinleri_iki_dilde():
    i18n = (KOK / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    for anahtar in ('sixdof.cgComponents', 'sixdof.cgComponentsPending',
                    'sixdof.badgeCgComponents', 'sixdof.cgComponentsBasis'):
        assert i18n.count("'" + anahtar + "'") == 2, anahtar
    assert 'bileşenlerden (beyanlı yerleşim)' in i18n


def test_flight_vehicle_kesir_sabiti_tasimaz():
    src = (KOK / 'hrma/analysis/flight_vehicle.py').read_text(encoding='utf-8')
    assert 'CG_ASSUMED_FULL_FRACTION' not in src
    assert '0.55' not in src


# --- örnek motorlar: yerleşim gerçekten kuruluyor (sessiz kesir dönüşü yok) ---
# Yerleşim kurulamazsa istemci onu göndermez ve uç sessizce kesir tahminine
# düşerdi; örnek motorlarda bunun olmadığı burada kilitlenir.

@pytest.fixture(scope='module', params=['liquid', 'hybrid', 'solid'])
def ornek_arac(request):
    from tests.test_v307_ucus_govde import _coz
    mt = request.param
    return mt, fv.normalize(mt, _coz(mt))


def test_ornek_motorlarda_yerlesim_kurulur_ve_kutle_tutar(ornek_arac):
    mt, arac = ornek_arac
    af = arac['airframe_resolved']
    assert af['source'] == 'derived'
    assert af['mass_layout_not_built'] is None
    lay = af['mass_layout']
    ucus = arac['flight_thrust']
    beklenen_kuru = arac['engine_inert_mass'] + (ucus.get('propellant_residual_kg') or 0.0)
    assert lay['dry_total_kg'] == pytest.approx(beklenen_kuru, rel=1e-9)
    assert lay['consumed_total_kg'] == pytest.approx(ucus['propellant_consumed_kg'], rel=1e-9)
    L = af['nose_length_m'] + af['length_behind_nose_m']
    cg = fv.component_cg(lay, L, beklenen_kuru, ucus['propellant_consumed_kg'])
    assert 0.0 < cg['x_cg_full_m'] <= L and 0.0 < cg['x_cg_empty_m'] <= L
    if mt == 'liquid':
        # Motor ve tanklardaki yedek itici kıçta: boş araç kesir tahmininin
        # (0,50·L) gerisinde.
        assert cg['x_cg_empty_m'] > sdt.CG_ASSUMED_EMPTY_FRACTION * L
