# -*- coding: utf-8 -*-
"""V301/L-C — sıvı enjektör: etiket/tip (SV-06), pintle tek kanon (SV-07),
ayrı panel ⟷ ana tasarım (SV-13).

Kanıt: docs/scofield/raw/OH/V301/kati-sivi/L-C/ (once.json / sonra.json,
RAPOR.md). Denetim: docs/scofield/raw/OH/V301/kati-sivi/denetim/A-sivi/
RAPOR.md (SV-06, SV-07, SV-13).
"""
import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

from hrma.app import app

KOK = pathlib.Path(__file__).resolve().parents[1]
LIQUID_HTML = KOK / 'hrma' / 'templates' / 'liquid.html'
PANEL_JS = KOK / 'hrma' / 'static' / 'js' / 'injector_panel.js'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Sıvı formun gerçek yükünün enjektörle ilgili çekirdeği (denetim
#: yuk_form_en.json: eleman 100, ΔP 20 bar, Cd 0,7) + itki/Pc/O-F.
LC_GOVDE = {
    'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'fuel_type': 'rp1', 'oxidizer_type': 'lox',
    'cooling_type': 'regenerative', 'engine_cycle': 'pressure_fed',
    'feed_pressure': 130, 'injector_elements': 100,
    'injector_pressure_drop': 20, 'discharge_coefficient': 0.7,
}

_ONBELLEK = {}


@pytest.fixture(scope='module')
def ist():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _cagir(ist, **ez):
    govde = dict(LC_GOVDE)
    for k, v in ez.items():
        if v is None:
            govde.pop(k, None)
        else:
            govde[k] = v
    anahtar = json.dumps(govde, sort_keys=True)
    if anahtar not in _ONBELLEK:
        r = ist.post('/calculate_liquid', json=govde)
        _ONBELLEK[anahtar] = (r.status_code, r.get_json(), r.data)
    return _ONBELLEK[anahtar]


# ===========================================================================
# SV-06 — etiket gerçeği söyler; eski değer kanonik ada çözülür
# ===========================================================================
def _secenekler():
    metin = LIQUID_HTML.read_text(encoding='utf-8')
    blok = re.search(r'<select id="injector_type">(.*?)</select>', metin, re.S)
    assert blok
    return re.findall(r'<option value="([^"]+)"([^>]*)>([^<]*)<', blok.group(1))


def test_sv06_ilk_secenek_unlike_doublet_ve_etiketi_dogru():
    sec = _secenekler()
    deger, _, etiket = sec[0]
    assert deger == 'unlike_impinging'
    assert 'Unlike doublet' in etiket and 'F-O' in etiket
    # Yalan etiket yok: "Like-on-Like" yalnız GERÇEK benzer-akışkan çiftte.
    for d, _, e in sec:
        if 'like-on-like' in e.lower():
            assert d == 'like_impinging', (d, e)


def test_sv06_eski_deger_gizli_ve_gecerli():
    gizli = [d for d, nit, _ in _secenekler() if 'hidden' in nit]
    assert gizli == ['impinging']
    from hrma.engines.liquid_rocket_engine import (
        INJECTOR_TYPES_RECOGNISED, canonical_injector_type)
    assert 'impinging' in INJECTOR_TYPES_RECOGNISED
    assert canonical_injector_type('impinging') == 'unlike_impinging'
    assert canonical_injector_type('IMPINGING ') == 'unlike_impinging'
    assert canonical_injector_type('banana') == 'banana'


def test_sv06_eski_deger_kanonik_ile_BIT_AYNI(ist):
    st1, y1, raw1 = _cagir(ist, injector_type='impinging')
    st2, y2, raw2 = _cagir(ist, injector_type='unlike_impinging')
    assert st1 == st2 == 200
    assert y1['injection_system']['injector_type'] == 'unlike_impinging'
    assert raw1 == raw2


def test_sv06_benzer_akiskan_cift_her_devrede_cift_sayida_delik(ist):
    st, y, _ = _cagir(ist, injector_type='like_impinging',
                      injector_elements=None)
    assert st == 200, y
    det = y['injection_system']['injector_design_detail']
    assert det['injector_type'] == 'like_impinging'
    nox = det['ox_circuit']['n_orifices']
    nf = det['fuel_circuit']['n_orifices']
    assert nox % 2 == 0 and nf % 2 == 0
    plan = det['element_plan']
    assert plan['pairs'] == nox // 2 and plan['fuel_pairs'] == nf // 2
    assert 'like-doublets' in det['pattern']['description']
    assert det['pattern']['n_elements'] == nox // 2 + nf // 2
    # Benzer çiftte F-O momentum ölçütü yok (uydurulmaz).
    assert det['momentum'] is None
    assert det['atomization']['smd_fuel_um'] > 0


def test_sv06_benzer_cift_eleman_sayisi_devre_basina_cift(ist):
    st, y, _ = _cagir(ist, injector_type='like_impinging',
                      injector_elements=8)
    assert st == 200, y
    det = y['injection_system']['injector_design_detail']
    assert det['ox_circuit']['n_orifices'] == 16
    assert det['fuel_circuit']['n_orifices'] == 16
    codes = [w.get('params', {}).get('label') for w in y['input_warnings']
             if w.get('code') == 'warn.liquid.entered_value_is_comparison_only']
    assert 'Injector element count' not in codes


def test_sv06_benzer_cift_sinir_disi_422_adli(ist):
    st, y, _ = _cagir(ist, injector_type='like_impinging',
                      injector_elements=100)
    assert st == 422, y
    alanlar = [h['field'] for h in y['invalid_fields']]
    assert 'injector_elements' in alanlar


# ===========================================================================
# SV-07 — pintle: tek kanon geometri
# ===========================================================================
@pytest.mark.parametrize('n', [None, 1, 20, 100])
def test_sv07_ozet_blok_kanon_pintle_geometrisinden(ist, n):
    st, y, _ = _cagir(ist, injector_type='pintle', injector_elements=n)
    assert st == 200
    inj = y['injection_system']
    pg = inj['injector_design_detail']['pintle_geometry']
    assert inj['number_of_elements'] == 1
    assert inj['fuel_orifice_count'] == pg['n_radial_holes']
    assert inj['fuel_orifice_diameter'] == pg['radial_hole_d_mm']
    assert inj['ox_orifice_count'] is None
    assert inj['ox_orifice_diameter'] is None
    assert inj['ox_annulus_gap_mm'] == pg['annulus_gap_mm']
    assert inj['pintle_diameter_mm'] == pg['d_pintle_mm']
    # Delik alanı = yakıt devresi alanı; anülüs alanı = oks. devresi alanı.
    import math
    a_rad = pg['n_radial_holes'] * math.pi / 4 * pg['radial_hole_d_mm'] ** 2
    assert a_rad == pytest.approx(inj['fuel_injection_area'], rel=1e-9)
    a_ann = math.pi * (pg['d_pintle_mm'] + pg['annulus_gap_mm']) \
        * pg['annulus_gap_mm']
    assert a_ann == pytest.approx(inj['ox_injection_area'], rel=1e-9)
    desen = y['injector_pattern']
    assert desen['pattern_type'] == 'pintle'
    assert desen['n_holes'] == pg['n_radial_holes']
    assert desen['hole_diameter_m'] == pytest.approx(
        pg['radial_hole_d_mm'] / 1000.0, rel=1e-12)


def test_sv07_eleman_sayisi_pintle_geometrisini_ve_hukmu_degistirmez(ist):
    yan = [_cagir(ist, injector_type='pintle', injector_elements=n)[1]
           for n in (None, 1, 100)]
    pg = [y['injection_system']['injector_design_detail']['pintle_geometry']
          for y in yan]
    assert pg[0] == pg[1] == pg[2]
    tau = [y['combustion_analysis']['stability_analysis']['chug_loop']
           .get('tau_s') for y in yan]
    assert tau[0] == tau[1] == tau[2]


def test_sv07_pintle_olculeri_devreye_gider(ist):
    st, y, _ = _cagir(ist, injector_type='pintle', injector_elements=None,
                      pintle_radial_hole_count=24, pintle_diameter=21.0,
                      skip_distance=15.0)
    assert st == 200, y
    pg = y['injection_system']['injector_design_detail']['pintle_geometry']
    assert pg['n_radial_holes'] == 24
    assert pg['d_pintle_mm'] == pytest.approx(21.0, rel=1e-12)
    assert pg['skip_distance_mm'] == pytest.approx(15.0, rel=1e-12)
    assert y['injection_system']['fuel_orifice_count'] == 24


@pytest.mark.parametrize('ez,alan,neden', [
    ({'pintle_radial_hole_count': 24, 'pintle_radial_hole_diameter': 3.0},
     'pintle_radial_hole_diameter', 'flow_mismatch'),
    ({'pintle_diameter': 'yirmi'}, 'pintle_diameter', 'not_a_number'),
    ({'pintle_diameter': -3}, 'pintle_diameter', 'not_positive'),
    ({'pintle_radial_hole_count': 2.5}, 'pintle_radial_hole_count',
     'not_a_positive_whole_number'),
    ({'secondary_holes': 'none'}, 'secondary_holes',
     'not_applicable_to_liquid_pintle'),
    ({'pintle_diameter': 5000}, 'pintle_diameter', 'does_not_fit_chamber'),
])
def test_sv07_pintle_kapisi_adli_422(ist, ez, alan, neden):
    st, y, _ = _cagir(ist, injector_type='pintle', injector_elements=None,
                      **ez)
    assert st == 422, y
    assert any(h['field'] == alan and h['reason'] == neden
               for h in y['invalid_fields']), y['invalid_fields']


def test_sv07_pintle_olcusu_pintle_disinda_yok_sayilmaz(ist):
    st, y, _ = _cagir(ist, injector_type='unlike_impinging',
                      pintle_diameter=20)
    assert st == 422
    assert y['invalid_fields'][0]['reason'] == 'applies_only_to_pintle'


def test_sv07_cad_govdesi_kanon_pintle_geometrisini_tasir(ist):
    st, y, _ = _cagir(ist, injector_type='pintle', injector_elements=None)
    pg = y['injection_system']['injector_design_detail']['pintle_geometry']
    assert y['motor_geometry']['injector_design']['pintle_geometry'] == pg
    assert y['motor_geometry']['injector_design']['orifice_diameter_mm'] == \
        pytest.approx(pg['radial_hole_d_mm'], rel=1e-12)


def test_sv07_form_pintleda_eleman_ve_cap_gizli_ve_gonderilmez():
    metin = LIQUID_HTML.read_text(encoding='utf-8')
    for alan in ('injector_elements', 'fuel_orifice_diameter',
                 'oxidizer_orifice_diameter'):
        m = re.search(r'<div class="form-group"([^>]*)>\s*<label for="%s">'
                      % alan, metin)
        assert m and 'data-liq-inj-hide="pintle"' in m.group(1), alan
    for alan in ('pintle_diameter', 'annular_gap', 'pintle_radial_hole_count',
                 'pintle_radial_hole_diameter', 'skip_distance'):
        m = re.search(r'<div class="form-group"([^>]*)>\s*<label for="%s">'
                      % alan, metin)
        assert m and 'data-liq-inj-show="pintle"' in m.group(1), alan
        # ipucu var (EN) ve boş doğar
        assert re.search(r'id="%s" [^>]*placeholder=' % alan, metin)
    # Gönderim: tipe ait olmayan alan yüke girmez, boş alan gönderilmez.
    assert "injector_elements: parseFloat" not in metin
    assert '...liqInjectorFieldPayload()' in metin


# ===========================================================================
# SV-13 — ayrı panel ⟷ ana tasarım (rel 1e-9)
# ===========================================================================
PANEL_VAKALARI = {
    'unlike_varsayilan': {},
    'unlike_cdsiz_elsiz': {'discharge_coefficient': None,
                           'injector_elements': None},
    'like_elsiz': {'injector_type': 'like_impinging',
                   'injector_elements': None},
    'like_8cift': {'injector_type': 'like_impinging', 'injector_elements': 8},
    'dus': {'injector_type': 'showerhead'},
    'koaksiyel': {'injector_type': 'coaxial'},
    'pintle': {'injector_type': 'pintle', 'injector_elements': None},
    'pintle_olculu': {'injector_type': 'pintle', 'injector_elements': None,
                      'pintle_radial_hole_count': 24,
                      'pintle_diameter': 21.0},
    'swirl': {'injector_type': 'swirl'},
}


def _node_spec(sonuc):
    with tempfile.TemporaryDirectory() as td:
        veri = pathlib.Path(td) / 'veri.json'
        veri.write_text(json.dumps({'sonuc': sonuc}), encoding='utf-8')
        betik = pathlib.Path(td) / 'kos.js'
        betik.write_text(
            "global.window = global;\n"
            "const fs = require('fs');\n"
            f"require({json.dumps(str(PANEL_JS))});\n"
            f"const v = JSON.parse(fs.readFileSync({json.dumps(str(veri))}, 'utf8'));\n"
            "const d = window.InjectorPanel.engineValuesFromResults(v.sonuc);\n"
            "const spec = d ? window.InjectorPanel.specFromValues(d) : null;\n"
            "process.stdout.write(JSON.stringify({deger: d, spec: spec}));\n",
            encoding='utf-8')
        p = subprocess.run([NODE, str(betik)], capture_output=True,
                           text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)


@needs_node
@pytest.mark.parametrize('ad', sorted(PANEL_VAKALARI))
def test_sv13_panel_ana_tasarimin_devresini_birebir_uretir(ist, ad):
    st, sonuc, _ = _cagir(ist, **PANEL_VAKALARI[ad])
    assert st == 200, sonuc
    kur = _node_spec(sonuc)
    assert kur['spec'] is not None
    r = ist.post('/api/injector-design', json=kur['spec'])
    assert r.status_code == 200, (kur['spec'], r.get_json())
    tas = r.get_json()['design']
    ana = sonuc['injection_system']['injector_design_detail']
    assert tas['injector_type'] == ana['injector_type']
    for devre in ('ox_circuit', 'fuel_circuit'):
        a, b = tas[devre], ana[devre]
        assert a['n_orifices'] == b['n_orifices'], (ad, devre)
        for k in ('orifice_d_mm', 'total_area_mm2', 'delta_p_bar',
                  'velocity_m_s', 'cd'):
            assert a[k] == pytest.approx(b[k], rel=1e-9), (ad, devre, k)
    if ana.get('pintle_geometry'):
        for k in ('d_pintle_mm', 'annulus_gap_mm', 'radial_hole_d_mm', 'bf',
                  'skip_distance_mm'):
            assert tas['pintle_geometry'][k] == pytest.approx(
                ana['pintle_geometry'][k], rel=1e-9), (ad, k)
        assert tas['pintle_geometry']['n_radial_holes'] == \
            ana['pintle_geometry']['n_radial_holes']
    if ana.get('element_plan'):
        assert tas['element_plan']['pairs'] == ana['element_plan']['pairs']
        assert tas['element_plan'].get('fuel_pairs') == \
            ana['element_plan'].get('fuel_pairs')
    assert tas['pattern']['description'] == ana['pattern']['description']


@needs_node
def test_sv13_panel_tipi_motorun_eslemesiyle(ist):
    st, sonuc, _ = _cagir(ist, injector_type='pintle', injector_elements=None)
    kur = _node_spec(sonuc)
    assert kur['deger']['injector_type'] == 'pintle'
    from hrma.engines.liquid_rocket_engine import INJECTOR_TYPE_CIRCUIT_MODEL
    st, sonuc, _ = _cagir(ist)
    assert _node_spec(sonuc)['deger']['injector_type'] == \
        INJECTOR_TYPE_CIRCUIT_MODEL['unlike_impinging']
    # Kullanıcı Cd'si panele taşınır (motorla aynı uygulanır).
    assert _node_spec(sonuc)['deger']['cd'] == pytest.approx(0.7)


def test_sv13_sayfa_eski_bes_alanli_eslemeyi_tasimaz():
    metin = LIQUID_HTML.read_text(encoding='utf-8')
    assert 'LIQUID_INJECTOR_FIELDS' not in metin
    assert 'InjectorPanel.engineValuesFromResults(' in metin
    assert 'circuitModel:' in metin and 'liq_injector_circuit_model' in metin


def test_sv13_panel_ucu_sivi_cd_kapisi(ist):
    st, sonuc, _ = _cagir(ist)
    kur = _node_spec(sonuc) if NODE else None
    spec = dict(sonuc['injection_system']['circuit_request']['spec'], cd=1.5)
    r = ist.post('/api/injector-design', json=spec)
    assert r.status_code == 422
    assert r.get_json()['invalid_fields'][0]['field'] == 'cd'
    assert kur is None or kur['spec']['cd'] == pytest.approx(0.7)


# ===========================================================================
# SV-12 (enjektör kısmı) — enjektör plakası malzemesi + yapısal denetim
# ===========================================================================
def test_sv12_secenekler_tek_kaynaktan(ist):
    from hrma.app import _sivi_enjektor_malzeme_secenekleri
    kayit = _sivi_enjektor_malzeme_secenekleri()
    html = ist.get('/liquid').data.decode('utf-8')
    blok = re.search(r'<select id="injector_material"[^>]*>(.*?)</select>',
                     html, re.S).group(1)
    degerler = re.findall(r'<option value="([^"]*)"', blok)
    assert degerler == [''] + [o['value'] for o in kayit['options']]
    # Şablonda elle yazılmış seçenek yok (yalnız "seçilmedi").
    kaynak = LIQUID_HTML.read_text(encoding='utf-8')
    sb = re.search(r'<select id="injector_material"[^>]*>(.*?)</select>',
                   kaynak, re.S).group(1)
    assert len(re.findall(r'<option value="[a-z]', sb)) == 0


def test_sv12_secilmezse_denetim_kosmaz_ve_soylenir(ist):
    st, y, _ = _cagir(ist)
    assert y['injector_plate_structural']['status'] == 'not_requested'


def test_sv12_cozulemeyen_ad_422(ist):
    st, y, _ = _cagir(ist, injector_material='peynir')
    assert st == 422
    assert y['error'] == 'unresolved_material'
    assert y['invalid_fields'][0]['field'] == 'injector_material'


@pytest.mark.parametrize('tip', ['unlike_impinging', 'showerhead',
                                 'like_impinging'])
def test_sv12_delikli_yuzde_plaka_boyutlandirilir(ist, tip):
    ez = {'injector_material': 'stainless_steel', 'injector_type': tip}
    if tip == 'like_impinging':
        ez['injector_elements'] = None
    st, y, _ = _cagir(ist, **ez)
    assert st == 200, y
    b = y['injector_plate_structural']
    assert b['status'] == 'sized' and b['material_key'] == 'ss_316'
    det = y['injection_system']['injector_design_detail']
    oxc, fc = det['ox_circuit'], det['fuel_circuit']
    assert b['n_holes'] == oxc['n_orifices'] + fc['n_orifices']
    assert b['hole_diameter_mm'] == pytest.approx(
        max(oxc['orifice_d_mm'], fc['orifice_d_mm']), abs=1e-4)
    assert b['delta_P_bar'] == pytest.approx(
        max(oxc['delta_p_bar'], fc['delta_p_bar']), rel=1e-4)
    assert b['plate_diameter_mm'] == pytest.approx(
        y['chamber_diameter_mm'], rel=1e-4)
    # Kâhin: Roark 11.2 / 10b, t = sqrt(0,75 q a² SF / (σ_y η)).
    import math
    q = b['delta_P_bar'] * 1e5
    a = b['plate_diameter_mm'] / 2000.0
    t = math.sqrt(0.75 * q * a ** 2 * b['required_safety_factor']
                  / (b['yield_strength_MPa'] * 1e6 * b['ligament_efficiency']))
    assert b['required_thickness_mm'] == pytest.approx(t * 1000, rel=2e-3)


def test_sv12_pintle_plakasi_adli_not_analyzed(ist):
    st, y, _ = _cagir(ist, injector_type='pintle', injector_elements=None,
                      injector_material='stainless_steel')
    b = y['injector_plate_structural']
    assert b['status'] == 'not_analyzed'
    assert 'pintle' in b['reason'] and 'safety_factor' not in b


# ===========================================================================
# Ters mutasyon için güçlendirilmiş bekçiler
# ===========================================================================
@pytest.mark.parametrize('mdot_ox', [0.3, 0.4, 0.8])
def test_sv06_tek_sayili_otomatik_plan_iki_devrede_ciftlenir(mdot_ox):
    """Devre planlayıcısı tek sayı verdiğinde iki devre de çift sayıya geçer."""
    from hrma.engines.injector_design import (design_injector,
                                              design_like_doublet)
    s = {'motor_type': 'liquid', 'injector_type': 'like_impinging',
         'mdot_ox': mdot_ox, 'mdot_fuel': mdot_ox / 2.5, 'rho_ox': 1141.0,
         'rho_fuel': 815.0, 'Pc_bar': 50.0, 'dp_ratio_ox': 0.2,
         'dp_ratio_fuel': 0.2, 'fluid_ox': 'lox', 'fluid_fuel': 'rp1'}
    ham = design_injector(dict(s))
    assert (ham['ox_circuit']['n_orifices'] % 2
            or ham['fuel_circuit']['n_orifices'] % 2), 'vaka tek sayı vermiyor'
    det = design_like_doublet(dict(s))
    for devre in ('ox_circuit', 'fuel_circuit'):
        assert det[devre]['n_orifices'] % 2 == 0, devre
        # Alan aynı kalır (yalnız delik sayısı/çapı değişir).
        assert det[devre]['total_area_mm2'] == pytest.approx(
            ham[devre]['total_area_mm2'], rel=1e-9)


def test_sv07_devre_plani_eleman_sayisindan_bagimsiz(ist):
    nler = []
    for n in (None, 1, 100):
        det = _cagir(ist, injector_type='pintle', injector_elements=n)[1][
            'injection_system']['injector_design_detail']
        nler.append((det['ox_circuit']['n_orifices'],
                     det['fuel_circuit']['n_orifices']))
    assert nler[0] == nler[1] == nler[2]


def test_sv07_atomizasyon_olcegi_kanon_anulus_boslugu(ist):
    y = _cagir(ist, injector_type='pintle', injector_elements=None)[1]
    taban = y['combustion_analysis']['combustion_analysis']['mixing_time_basis']
    pg = y['injection_system']['injector_design_detail']['pintle_geometry']
    assert 'annular sheet thickness' in taban
    assert '%.3f mm' % pg['annulus_gap_mm'] in taban


@needs_node
def test_sv07_panel_pintle_esdeger_plan_notu():
    """Sıvı pintle panelinde devre tablosunun eşdeğer (delinmeyen) plan
    olduğu yazılır; hibrit panel çıktısı değişmez."""
    betik = (
        "global.window = global;\n"
        f"require({json.dumps(str(PANEL_JS))});\n"
        "const dz = {pintle_geometry: {d_pintle_mm: 19.5, n_radial_holes: 33,"
        " radial_hole_d_mm: 1.07, annulus_gap_mm: 0.98, bf: 0.58,"
        " skip_distance_mm: 19.5}, ox_circuit: {n_orifices: 12},"
        " fuel_circuit: {n_orifices: 6}, pattern: {}, atomization: {},"
        " stability: {}, warnings: [], assumptions: []};\n"
        "const s = window.InjectorPanel._renderHtml(Object.assign({motor_type: 'liquid'}, dz));\n"
        "const h = window.InjectorPanel._renderHtml(Object.assign({motor_type: 'hybrid'}, dz));\n"
        "process.stdout.write(JSON.stringify([/NOT drilled/.test(s), /NOT drilled/.test(h)]));\n")
    with tempfile.TemporaryDirectory() as td:
        yol = pathlib.Path(td) / 'k.js'
        yol.write_text(betik, encoding='utf-8')
        p = subprocess.run([NODE, str(yol)], capture_output=True, text=True,
                           timeout=60)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == [True, False]


# ===========================================================================
# Ana model kararı (27 Eki): pintle chug hükmü İKİ atomizasyon ölçeğiyle
# ===========================================================================
def _chug(ist, **ez):
    st, y, _ = _cagir(ist, injector_type='pintle', injector_elements=None,
                      **ez)
    assert st == 200, y
    return y, y['combustion_analysis']['stability_analysis']['chug_loop']


def test_pintle_chug_iki_olcek_adli_alanlarda(ist):
    y, L = _chug(ist)
    ch = L['atomisation_scale_check']
    assert ch['nominal_scale'] == 'annulus_gap_t'
    assert set(ch['scales']) == {'annulus_gap_t', 'radial_hole_d'}
    pg = y['injection_system']['injector_design_detail']['pintle_geometry']
    det = y['injection_system']['injector_design_detail']
    rho_g = (y['chamber_pressure'] * 1e5) / (8314.462618
                                             / y['molecular_weight']
                                             * y['chamber_temperature'])
    # Kâhin: t_b = 5·L/v·sqrt(ρ_l/ρ_g), her akımın kendi L, v, ρ_l'si.
    import math
    beklenen = {
        'annulus_gap_t': 5 * pg['annulus_gap_mm'] * 1e-3
        / det['ox_circuit']['velocity_m_s']
        * math.sqrt(y['oxidizer_density'] / rho_g),
        'radial_hole_d': 5 * pg['radial_hole_d_mm'] * 1e-3
        / det['fuel_circuit']['velocity_m_s']
        * math.sqrt(y['fuel_density'] / rho_g),
    }
    for ad, tau in beklenen.items():
        assert ch['scales'][ad]['tau_s'] == pytest.approx(tau, rel=1e-6), ad
    # Nominal ölçek çevrimin kendi τ'sudur.
    assert ch['scales']['annulus_gap_t']['tau_s'] == pytest.approx(
        L['tau_s'], rel=1e-12)
    # Künye seçimi ve kaynakları söyler; kaynaksız yüzde bandı yok.
    assert 'Pilch & Erdman' in ch['basis'] and 'TN D-4564' in ch['basis']
    assert '%' not in ch['basis']


def test_pintle_chug_hukumler_farkliysa_SINIRDA_nominal_gizlenmez(ist):
    # Bu gövdede ΔP 19 bar'da iki ölçek ayrışıyor (ölçüldü: t → unstable
    # +34 1/s, d → stable −81 1/s); 20 bar'da ikisi de kararlı.
    y, L = _chug(ist, injector_pressure_drop=19, feed_pressure=200)
    ch = L['atomisation_scale_check']
    nom = ch['scales']['annulus_gap_t']
    alt = ch['scales']['radial_hole_d']
    assert nom['verdict'] != alt['verdict']          # bu vakada ayrışıyor
    assert ch['verdicts_agree'] is False
    assert L['verdict'] == 'marginal' == ch['published_verdict']
    assert L['nominal_verdict'] == nom['verdict'] == 'unstable'
    # Nominal sayılar yerinde (gizlenmez).
    assert L['growth_rate_1_s'] == nom['growth_rate_1_s'] > 0
    assert L['tau_over_tau_c'] == nom['tau_over_tau_c']
    assert 'MARGINAL (sensitive to the atomisation scale)' in L['verdict_basis']
    assert '%+.3g' % nom['growth_rate_1_s'] in L['verdict_basis']
    kodlar = [w['code'] for w in y['input_warnings']]
    assert 'warn.liquid.chug_scale_sensitive_nominal_unstable' in kodlar
    assert L['rule_vs_loop']['loop_verdict'] == 'marginal'


@pytest.mark.parametrize('dp,hukum', [(16, 'unstable'), (22, 'stable')])
def test_pintle_chug_hukumler_ayniysa_o_yayimlanir(ist, dp, hukum):
    y, L = _chug(ist, injector_pressure_drop=dp, feed_pressure=200)
    ch = L['atomisation_scale_check']
    assert ch['verdicts_agree'] is True
    assert {v['verdict'] for v in ch['scales'].values()} == {hukum}
    assert L['verdict'] == hukum == ch['published_verdict']
    assert 'nominal_verdict' not in L
    assert not [w for w in y['input_warnings']
                if w['code'].startswith('warn.liquid.chug_scale_sensitive')]


@pytest.mark.parametrize('tip', ['unlike_impinging', 'showerhead',
                                 'coaxial'])
def test_pintle_disi_tipte_olcek_denetimi_yok(ist, tip):
    st, y, _ = _cagir(ist, injector_type=tip)
    L = y['combustion_analysis']['stability_analysis']['chug_loop']
    assert 'atomisation_scale_check' not in L
    assert L['verdict'] in ('stable', 'unstable')


def test_pintle_chug_uyari_metni_iki_dilde():
    metin = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    for kod in ('warn.liquid.chug_scale_sensitive_nominal_unstable',
                'warn.liquid.chug_scale_sensitive_nominal_stable'):
        satirlar = [s for s in metin.splitlines() if f"'{kod}':" in s]
        assert len(satirlar) == 2, kod
        assert 'MARGINAL' in satirlar[0] and 'SINIRDA' in satirlar[1]
        for s in satirlar:
            for p in ('{growth}', '{tau_ratio}', '{alt_growth}', '{t_mm}',
                      '{d_mm}'):
                assert p in s
