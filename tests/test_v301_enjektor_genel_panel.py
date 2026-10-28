# -*- coding: utf-8 -*-
"""V301/E2 — ayrı "Injector Design — Hybrid" paneli ana tasarımla AYNI sayılar.

ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ayberk1/enjektor-genel/once_en_ekran.json):
ana tasarımda pintle ve ṁ_ox 0,41 kg/s iken panel hesaptan sonra da
'Showerhead', ṁ_ox 2 kg/s ve duş başlığı şeması gösteriyordu (eski
``resultsProvider`` yalnız BOŞ alanı dolduruyordu, hibrit alanlar dolu
doğuyordu). Artık panel ``engineValuesFromResults`` ile devrenin girdilerini
alır ve ``specFromValues`` ile yükü kurar; bu bekçi o İKİ saf işlevi düğümde
(node) ürünün kendi dosyasından çalıştırır, yükü ``/api/injector-design``e
gönderir ve sayıları motorun devre çözümüyle karşılaştırır.

Ayrıca (E1 devri madde 5 + brif madde 8): panel ucu pintle ölçülerini
/calculate'in kapısından geçirir, ``radial_fraction`` sessizce kırpılmaz.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from hrma.app import app

KOK = pathlib.Path(__file__).resolve().parents[1]
PANEL_JS = KOK / 'hrma' / 'static' / 'js' / 'injector_panel.js'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

E2_PANEL_GOVDESI = {
    'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'expansion_ratio': 0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
}

PANEL_ESLEME_VAKALARI = {
    'pintle_varsayilan': {'injector_type': 'pintle'},
    'pintle_n_d': {'injector_type': 'pintle', 'secondary_holes': 'radial',
                   'pintle_radial_hole_count': 12,
                   'pintle_radial_hole_diameter': 0.6},
    'carpismali': {'injector_type': 'impingement'},
    'carpismali_p3_a80': {'injector_type': 'impingement', 'element_pairs': 3,
                          'impingement_angle': 80},
    'swirl': {'injector_type': 'swirl'},
    'swirl_t30': {'injector_type': 'swirl', 'swirl_angle': 30,
                  'swirl_chamber_diameter': 8, 'n_slots': 4},
    'swirl_yuva': {'injector_type': 'swirl', 'n_slots': 6, 'slot_width': 1.2,
                   'slot_height': 0.6},
    'dus_n8': {'injector_type': 'showerhead', 'n_holes': 8},
    'dus_bant_plaka': {'injector_type': 'showerhead', 'hole_diameter_min': 1.0,
                       'hole_diameter_max': 1.5, 'plate_thickness': 4.0},
    'dus_tank60': {'injector_type': 'showerhead',
                   'tank_pressure_source': 'user', 'tank_pressure': 60},
    # V301/H2: tek akışkanlı koaksiyel eleman artık devrede; panel aynı
    # girdilerle aynı elemanı çözer (eşitlik aşağıdaki bekçide).
    'koaksiyel': {'injector_type': 'coaxial'},
    'koaksiyel_pay04': {'injector_type': 'coaxial',
                        'coaxial_inner_flow_fraction': 0.4},
    'koaksiyel_eski_cap': {'injector_type': 'coaxial', 'inner_diameter': 5,
                           'outer_annulus_diameter': 8},
    'koaksiyel_tank60': {'injector_type': 'coaxial',
                         'tank_pressure_source': 'user', 'tank_pressure': 60},
}

_ONBELLEK = {}


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as ist:
        yield ist


def _node_spec(sonuc, istek):
    """Ürünün injector_panel.js'inden engineValuesFromResults + specFromValues."""
    with tempfile.TemporaryDirectory() as td:
        veri = pathlib.Path(td) / 'veri.json'
        veri.write_text(json.dumps({'sonuc': sonuc, 'istek': istek}),
                        encoding='utf-8')
        betik = pathlib.Path(td) / 'kos.js'
        betik.write_text(
            "global.window = global;\n"
            "const fs = require('fs');\n"
            f"require({json.dumps(str(PANEL_JS))});\n"
            f"const v = JSON.parse(fs.readFileSync({json.dumps(str(veri))}, 'utf8'));\n"
            "const deger = window.InjectorPanel.engineValuesFromResults(v.sonuc, v.istek);\n"
            "const spec = deger ? window.InjectorPanel.specFromValues(deger) : null;\n"
            "process.stdout.write(JSON.stringify({deger: deger, spec: spec}));\n",
            encoding='utf-8')
        p = subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                           timeout=60)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)


def _vaka(istemci, ad):
    if ad not in _ONBELLEK:
        istek = dict(E2_PANEL_GOVDESI, **PANEL_ESLEME_VAKALARI[ad])
        r = istemci.post('/calculate', json=istek)
        assert r.status_code == 200, r.get_json()
        sonuc = r.get_json()
        kur = _node_spec(sonuc, istek)
        p = istemci.post('/api/injector-design', json=kur['spec'])
        assert p.status_code == 200, (kur['spec'], p.get_json())
        _ONBELLEK[ad] = (sonuc, kur, p.get_json()['design'])
    return _ONBELLEK[ad]


@needs_node
@pytest.mark.parametrize('ad', sorted(PANEL_ESLEME_VAKALARI))
def test_panel_devrenin_sayilarini_birebir_uretir(istemci, ad):
    sonuc, kur, tasarim = _vaka(istemci, ad)
    motor_devre = sonuc['motor']['injector_design_detail']
    a, b = tasarim['ox_circuit'], motor_devre['ox_circuit']
    assert a['n_orifices'] == b['n_orifices']
    for k in ('orifice_d_mm', 'total_area_mm2', 'delta_p_bar', 'velocity_m_s',
              'cd'):
        assert a[k] == pytest.approx(b[k], rel=1e-9), (ad, k, a[k], b[k])
    assert a['flow_model'] == b['flow_model']
    assert tasarim['injector_type'] == motor_devre['injector_type']
    if motor_devre.get('pintle_geometry'):
        for k in ('d_pintle_mm', 'annulus_gap_mm', 'radial_hole_d_mm', 'bf',
                  'radial_flow_fraction'):
            assert tasarim['pintle_geometry'][k] == pytest.approx(
                motor_devre['pintle_geometry'][k], rel=1e-9), (ad, k)
        assert tasarim['pintle_geometry']['n_radial_holes'] == \
            motor_devre['pintle_geometry']['n_radial_holes']
    if motor_devre.get('swirl_geometry'):
        for k in ('K', 'inlet_d_mm', 'swirl_chamber_d_mm',
                  'tangential_inlet_area_mm2'):
            assert tasarim['swirl_geometry'][k] == pytest.approx(
                motor_devre['swirl_geometry'][k], rel=1e-9), (ad, k)
        assert tasarim['swirl_geometry']['tangential_inlets'] == \
            motor_devre['swirl_geometry']['tangential_inlets']
    if motor_devre.get('coaxial_geometry'):
        for k in ('total_flow_area_mm2', 'inner_flow_fraction',
                  'inner_jet_diameter_mm', 'annulus_inner_diameter_mm',
                  'annulus_outer_diameter_mm', 'annulus_gap_mm',
                  'recess_length_mm'):
            assert tasarim['coaxial_geometry'][k] == pytest.approx(
                motor_devre['coaxial_geometry'][k], rel=1e-9), (ad, k)
    imp = (motor_devre.get('pattern') or {}).get('impingement')
    if imp:
        assert tasarim['pattern']['impingement']['half_angle_deg'] == \
            pytest.approx(imp['half_angle_deg'])
        assert tasarim['pattern']['n_elements'] == motor_devre['pattern'][
            'n_elements']


@needs_node
def test_tip_ana_tasarimdan_ve_kullanici_tank_P1_tasinir(istemci):
    _s, kur, _t = _vaka(istemci, 'carpismali')
    assert kur['deger']['injector_type'] == 'like_impinging'
    _s, kur, _t = _vaka(istemci, 'dus_tank60')
    assert kur['spec']['p_feed_bar'] == pytest.approx(60.0)
    assert kur['spec']['rho_ox'] > 785.2           # sıkıştırılmış sıvı
    _s, kur, _t = _vaka(istemci, 'dus_bant_plaka')
    assert kur['spec']['orifice_constraints'] == {'d_min_mm': 1.0,
                                                  'd_max_mm': 1.5}
    assert kur['deger']['l_over_d'] is not None    # plaka verildi: kazanılmış


@needs_node
def test_plaka_verilmediyse_LD_bos_kalir(istemci):
    _s, kur, _t = _vaka(istemci, 'dus_n8')
    assert kur['deger']['l_over_d'] is None
    assert 'l_over_d' not in kur['spec']


@needs_node
def test_koaksiyel_panel_esler_ve_payi_devreden_alir(istemci):
    """V301/H2 (beklenti değişti; eskiden devre koaksiyeli çözemediği için
    panel değeri null'dı — docs/scofield/raw/OH/V301/bilinen/hibrit/
    RAPOR.md): panel tipi 'coaxial', iç jet payı devrenin KENDİ sayısı
    (istek payı, eski çap çiftinin payı ya da beyanlı varsayılan)."""
    _s, kur, _t = _vaka(istemci, 'koaksiyel')
    assert kur['deger']['injector_type'] == 'coaxial'
    assert kur['spec']['coaxial'] == {'inner_flow_fraction': 0.6}
    _s, kur, _t = _vaka(istemci, 'koaksiyel_eski_cap')
    assert kur['spec']['coaxial']['inner_flow_fraction'] == \
        pytest.approx(25 / 64, rel=1e-12)


# ---------------------------------------------------------------------------
# /api/injector-design kapısı (E1 devri madde 5, brif madde 8)
# ---------------------------------------------------------------------------
_PANEL_TABAN = {'motor_type': 'hybrid', 'mdot_ox': 0.4, 'Pc_bar': 20,
                'rho_ox': 785.1, 'fluid_ox': 'n2o', 'T_ox_K': 293.15}


@pytest.mark.parametrize('rf,beklenen', [(0.05, 422), (0.95, 422),
                                         ('yarim', 422), (0.5, 200),
                                         (0.1, 200), (0.9, 200)])
def test_radial_fraction_sessizce_kirpilmaz(istemci, rf, beklenen):
    r = istemci.post('/api/injector-design', json=dict(
        _PANEL_TABAN, injector_type='pintle', pintle={'radial_fraction': rf}))
    assert r.status_code == beklenen, r.get_json()
    if beklenen == 422:
        assert r.get_json()['invalid_fields'][0]['field'] == 'radial_fraction'


def test_radial_fraction_bandi_cekirdegin_kirpmasiyla_ayni():
    """Uç kapısının bandı, çekirdeğin (E1 bölgesi) kırpma bandıdır."""
    from hrma.engines.injector_design import (PINTLE_RADIAL_FRACTION_BAND,
                                              resolve_pintle_geometry)
    lo, hi = PINTLE_RADIAL_FRACTION_BAND
    alan = 10.5e-6
    alt = resolve_pintle_geometry(alan, {'radial_fraction': lo / 2})
    ust = resolve_pintle_geometry(alan, {'radial_fraction': (1 + hi) / 2})
    assert alt['radial_flow_fraction'] == pytest.approx(lo, rel=1e-12)
    assert ust['radial_flow_fraction'] == pytest.approx(hi, rel=1e-12)


@pytest.mark.parametrize('pin,neden', [
    ({'n_radial_holes': 12.5}, 'not_a_positive_whole_number'),
    ({'d_pintle_mm': -3}, 'not_positive'),
    ({'secondary_holes': 'spiral'}, 'invalid_choice'),
    ({'d_pintle_mm': 10, 'annulus_gap_mm': 1, 'n_radial_holes': 12,
      'radial_hole_d_mm': 0.6}, 'geometry_does_not_deliver_target_flow'),
])
def test_panel_pintle_olculeri_ana_tasarim_kapisindan_gecer(istemci, pin, neden):
    r = istemci.post('/api/injector-design', json=dict(
        _PANEL_TABAN, injector_type='pintle', pintle=pin))
    assert r.status_code == 422, r.get_json()
    assert neden in [k['reason'] for k in r.get_json()['invalid_fields']]


def test_panel_carpismali_cift_sayida_delik_ve_swirl_zarfi(istemci):
    r = istemci.post('/api/injector-design', json=dict(
        _PANEL_TABAN, injector_type='like_impinging'))
    assert r.status_code == 200
    assert r.get_json()['design']['ox_circuit']['n_orifices'] % 2 == 0
    r = istemci.post('/api/injector-design', json=dict(
        _PANEL_TABAN, injector_type='swirl', swirl={'theta_target_deg': 80}))
    assert r.status_code == 422
    assert r.get_json()['invalid_fields'][0]['reason'] == 'out_of_range'


def test_sivi_panel_yolu_degismedi(istemci):
    """Sıvı paneli: like_impinging/swirl eski çözücüden (design_injector)."""
    from hrma.engines.injector_design import design_injector
    govde = {'motor_type': 'liquid', 'injector_type': 'like_impinging',
             'mdot_ox': 1.0, 'mdot_fuel': 0.5, 'Pc_bar': 30, 'rho_ox': 1141,
             'rho_fuel': 810}
    r = istemci.post('/api/injector-design', json=govde)
    assert r.status_code == 200
    dogrudan = design_injector(dict(govde))
    assert r.get_json()['design']['ox_circuit']['n_orifices'] == \
        dogrudan['ox_circuit']['n_orifices']


# ---------------------------------------------------------------------------
# Panel kaynağı (statik): hibrit yük tek işlevden, sağlayıcı yazamıyor değil
# ---------------------------------------------------------------------------
def test_hibrit_yuk_tek_islevden_ve_eslenme_kancasi():
    src = PANEL_JS.read_text(encoding='utf-8')
    assert "if (cfg.motorType === 'hybrid') {" in src
    assert 'return specFromValues(readHybridValues());' in src
    sablon = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    assert 'InjectorPanel.engineValuesFromResults(results, istek)' in sablon
    assert 'InjectorPanel.followMainType(injAnaTipSecici.value)' in sablon
    app_js = (KOK / 'hrma' / 'static' / 'js' / 'app.js').read_text(
        encoding='utf-8')
    assert 'window.currentRequest = data;' in app_js
