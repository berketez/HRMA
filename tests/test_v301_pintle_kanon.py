# -*- coding: utf-8 -*-
"""V301 / E1 (Ayberk tur 1) — pintle enjektörün TEK KANONİK geometrisi.

Ayberk'in maddeleri: "pintle için outer diameter istiyor ama nerenin outer
diameteri yazmıyor", "secondary holes girsek dahi ek input istemiyor",
"Enjektör kısmı full hatalı". ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/ayberk1/
enjektor-pintle/once.json``, 1 kN / Pc 20 bar / N2O-HTPB): ekran bloğu sunucunun
motordan bağımsız 25 mm yedeğiyle 437 × Ø0,104 mm delik + 0,047 mm anülüs,
devre çözücüsü D_p 5,639 mm ile 16 × Ø0,646 mm + 0,282 mm, motor özeti
``number_of_orifices = 3`` yayımlıyordu.

Bu dosya kilitler:
  A) ekran bloğu, devre ve motor özeti AYNI geometriyi anlatır (kanon);
  B) D_p boşsa akıştan boyutlandırılır (25 mm sabiti geri gelemez);
  C) gövde dış çapı boşsa BOYUTLANDIRILMAZ (None + beyan);
  D) ikincil delik girdileri devreye girer, akış payı geometriden kapanır;
  E) aşırı belirlenmiş / imkânsız / saldırgan girdi 422 (adlı alanlar);
  F) künye: Dressler & Bauer'e yanlış atıf yok;
  G) form, tablo ve 2B kesit kanonu ve adları taşır.
"""
import json
import re
from pathlib import Path

import pytest

from hrma.app import app
from hrma.engines.injector_design import (
    PINTLE_FLOW_MATCH_REL_TOL, PINTLE_HYBRID_RADIAL_FRACTION,
    PINTLE_RULE_BASIS, PintleGeometryInputError,
    pintle_tip_geometry, resolve_pintle_geometry)

KOK = Path(__file__).resolve().parents[1]

V301_PINTLE_GOVDESI = {
    'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'expansion_ratio': 0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'injector_type': 'pintle',
}

#: Ekran ⟷ devre eşitliği aranan geometri alanları.
V301_PINTLE_KANON_ALANLARI = (
    'd_pintle_mm', 'annulus_gap_mm', 'n_radial_holes', 'radial_hole_d_mm',
    'bf', 'skip_distance_mm', 'radial_flow_fraction', 'tmr',
    'spray_half_angle_deg', 'annulus_bore_diameter_mm',
    'housing_outer_diameter_mm', 'housing_wall_mm', 'secondary_holes',
    'radial_hole_area_mm2', 'annulus_area_mm2', 'total_flow_area_mm2')


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, **ek):
    r = istemci.post('/calculate', json=dict(V301_PINTLE_GOVDESI, **ek))
    return r.status_code, (r.get_json() or {})


@pytest.fixture(scope='module')
def varsayilan(istemci):
    kod, j = _post(istemci)
    assert kod == 200, str(j)[:300]
    return j


@pytest.fixture(scope='module')
def kullanici_nd(istemci):
    kod, j = _post(istemci, pintle_radial_hole_count=12,
                   pintle_radial_hole_diameter=0.6, outer_diameter=20.0)
    assert kod == 200, str(j)[:300]
    return j


def _uc(j):
    inj = j.get('injector') or {}
    motor = j.get('motor') or {}
    return (inj, inj.get('pintle_geometry') or {},
            (motor.get('injector_design_detail') or {}).get(
                'pintle_geometry') or {},
            motor.get('injector_design') or {})


def _kunye(j):
    return {k['field']: k for k in (j.get('defaults_applied') or [])
            if isinstance(k, dict) and 'field' in k}


# --------------------------------------------------------------------------
# A) Tek kanon
# --------------------------------------------------------------------------
@pytest.mark.parametrize('kosu', ['varsayilan', 'kullanici_nd'])
def test_ekran_devre_ve_motor_ozeti_ayni_geometri(kosu, request):
    inj, ekran, devre, ozet = _uc(request.getfixturevalue(kosu))
    assert devre, 'devre çözücüsü pintle geometrisi yayımlamıyor'
    for alan in V301_PINTLE_KANON_ALANLARI:
        assert ekran.get(alan) == devre.get(alan), (
            f'{alan}: ekran {ekran.get(alan)!r} ⟷ devre {devre.get(alan)!r}')
        assert ozet['pintle_geometry'].get(alan) == devre.get(alan), alan
    # Düz anahtarlar da kanondan (ikinci kopya değil, aynı sayı)
    assert inj['pintle_diameter'] == devre['d_pintle_mm']
    assert inj['gap'] == devre['annulus_gap_mm']
    assert inj['annulus_bore_diameter'] == devre['annulus_bore_diameter_mm']
    assert inj['pintle_geometry_is_canon'] is True


def test_motor_ozeti_esdeger_orifis_planini_beyan_eder(varsayilan):
    _inj, _e, devre, ozet = _uc(varsayilan)
    # 1 kN'de ölçülen kusur: özet "3 orifis" diyordu, pintle 16 delikli.
    assert ozet['number_of_orifices'] != devre['n_radial_holes']
    assert 'EQUIVALENT straight-orifice plan' in ozet['orifice_plan_basis']
    assert 'pintle_geometry' in ozet['orifice_plan_basis']


def test_toplam_alan_devrenin_alanidir(varsayilan, kullanici_nd):
    for j in (varsayilan, kullanici_nd):
        _i, _e, devre, _o = _uc(j)
        a_devre = j['motor']['injector_design_detail']['ox_circuit'][
            'total_area_mm2']
        assert devre['total_flow_area_mm2'] == pytest.approx(a_devre,
                                                            rel=1e-12)
        assert devre['flow_match']['mismatch_rel'] == pytest.approx(
            0.0, abs=1e-12)


# --------------------------------------------------------------------------
# B) D_p akıştan; 25 mm sabiti yok
# --------------------------------------------------------------------------
def test_varsayilan_dp_akistan_boyutlandirilir(varsayilan):
    _i, ekran, devre, _o = _uc(varsayilan)
    a = varsayilan['motor']['injector_design_detail']['ox_circuit'][
        'total_area_mm2'] * 1e-6
    f = PINTLE_HYBRID_RADIAL_FRACTION
    beklenen = pintle_tip_geometry(f * a, a - f * a)
    for alan, deger in beklenen.items():
        assert devre[alan] == deger, alan        # eski çağrıyla BİT-AYNI
    assert ekran['d_pintle_mm'] == beklenen['d_pintle_mm']
    assert ekran['sizing_sources']['d_pintle_mm'] == 'flow_sized_annulus_rule'
    k = _kunye(varsayilan)['pintle_diameter']
    assert k['value'] is None
    assert k['reason'] == 'not_supplied_solver_derives'


def test_dp_motor_boyutuyla_degisir(istemci, varsayilan):
    """Sabit yedek motor boyutundan bağımsızdı; akış boyutlandırması değil."""
    kod, j5 = _post(istemci, thrust=5000)
    assert kod == 200
    d1 = _uc(varsayilan)[1]['d_pintle_mm']
    d5 = _uc(j5)[1]['d_pintle_mm']
    assert d5 > 1.5 * d1, (d1, d5)
    assert 25.0 not in (d1, d5)


# --------------------------------------------------------------------------
# C) Gövde dış çapı boyutlandırılmaz
# --------------------------------------------------------------------------
def test_govde_dis_capi_boyutlandirilmaz_beyan_edilir(varsayilan):
    inj, ekran, _d, _o = _uc(varsayilan)
    assert inj['outer_diameter'] is None
    assert inj['body_wall_thickness'] is None
    assert inj['housing_sized'] is False
    assert ekran['housing_sized'] is False
    assert 'not sized' in ekran['housing_basis']
    k = _kunye(varsayilan)['outer_diameter']
    assert k['value'] is None and k['reason'] == 'not_supplied_not_sized'


def test_govde_verilirse_cidar_geometrik(kullanici_nd):
    inj, ekran, _d, _o = _uc(kullanici_nd)
    assert inj['outer_diameter'] == 20.0
    assert inj['body_wall_thickness'] == pytest.approx(
        (20.0 - ekran['annulus_bore_diameter_mm']) / 2.0, rel=1e-12)
    assert ekran['annulus_bore_diameter_mm'] == pytest.approx(
        ekran['d_pintle_mm'] + 2.0 * ekran['annulus_gap_mm'], rel=1e-12)


# --------------------------------------------------------------------------
# D) İkincil delik girdileri devreye girer
# --------------------------------------------------------------------------
def test_kullanici_n_d_kanona_girer_ve_akis_payi_kapanir(kullanici_nd):
    _i, ekran, devre, _o = _uc(kullanici_nd)
    assert devre['n_radial_holes'] == 12
    assert devre['radial_hole_d_mm'] == pytest.approx(0.6)
    a_r = devre['radial_hole_area_mm2']
    a_a = devre['annulus_area_mm2']
    assert a_r == pytest.approx(12 * 3.141592653589793 / 4 * 0.6 ** 2,
                                rel=1e-12)
    assert devre['radial_flow_fraction'] == pytest.approx(a_r / (a_r + a_a),
                                                          rel=1e-12)
    assert devre['tmr'] == pytest.approx(
        devre['radial_flow_fraction'] / (1 - devre['radial_flow_fraction']))
    assert devre['sizing_sources']['n_radial_holes'] == 'request'
    kunye = _kunye(kullanici_nd)
    assert 'pintle_radial_hole_count' not in kunye
    assert 'pintle_radial_hole_diameter' not in kunye


def test_kip_verilmezse_radial_beyanli(varsayilan):
    k = _kunye(varsayilan)['secondary_holes']
    assert k['value'] == 'radial' and k['reason'] == 'not_supplied'


def test_none_kipi_devrede_de_deliksiz(istemci):
    kod, j = _post(istemci, secondary_holes='none')
    assert kod == 200
    _i, ekran, devre, _o = _uc(j)
    assert devre['n_radial_holes'] == 0 and ekran['n_radial_holes'] == 0
    assert devre['tmr'] is None and devre['skip_distance_mm'] is None
    assert 'NOT_APPLICABLE' in devre['tmr_basis']
    atom = j['motor']['injector_design_detail']['atomization']
    assert atom['smd_ox_um'] is None
    assert atom['spray_cone_half_angle_deg'] is None
    kunye = _kunye(j)
    assert 'pintle_radial_hole_count' not in kunye   # deliksiz kipte anılmaz


def test_teget_kipinde_aci_geometri_olarak_tasinir(istemci):
    kod, j = _post(istemci, secondary_holes='tangential',
                   pintle_tangential_angle=30.0, skip_distance=8.0)
    assert kod == 200
    _i, ekran, devre, _o = _uc(j)
    assert devre['tangential_angle_deg'] == 30.0
    assert devre['tangential_momentum_modelled'] is False
    assert 'lower bound' in devre['tangential_basis']
    assert devre['skip_distance_mm'] == 8.0
    assert devre['ls_over_dp'] == pytest.approx(8.0 / devre['d_pintle_mm'])


# --------------------------------------------------------------------------
# E) 422 kapıları
# --------------------------------------------------------------------------
def test_asiri_belirlenmis_geometri_debi_uyusmazligiyla_reddedilir(istemci):
    kod, j = _post(istemci, pintle_diameter=10.0, annular_gap=1.0,
                   pintle_radial_hole_count=12,
                   pintle_radial_hole_diameter=0.6)
    assert kod == 422, str(j)[:300]
    alanlar = {f['field']: f for f in j['invalid_fields']}
    assert set(alanlar) == {'pintle_diameter', 'annular_gap',
                            'pintle_radial_hole_count',
                            'pintle_radial_hole_diameter'}
    kayit = alanlar['annular_gap']
    assert kayit['reason'] == 'geometry_does_not_deliver_target_flow'
    assert kayit['requested_mdot_kg_s'] > 0
    assert kayit['predicted_mdot_kg_s'] > kayit['requested_mdot_kg_s']
    assert abs(kayit['mismatch_rel']) > PINTLE_FLOW_MATCH_REL_TOL
    assert kayit['tolerance_rel'] == PINTLE_FLOW_MATCH_REL_TOL
    assert 'HRMA choice' in kayit['tolerance_basis']


@pytest.mark.parametrize('ek,alan,neden', [
    ({'pintle_diameter': 'beş'}, 'pintle_diameter', 'not_a_number'),
    ({'pintle_diameter': True}, 'pintle_diameter', 'not_a_number'),
    ({'pintle_diameter': -3}, 'pintle_diameter', 'not_positive'),
    ({'annular_gap': {'x': 1}}, 'annular_gap', 'not_a_number'),
    ({'pintle_radial_hole_count': 12.5}, 'pintle_radial_hole_count',
     'not_a_positive_whole_number'),
    ({'pintle_radial_hole_count': 0}, 'pintle_radial_hole_count',
     'not_a_positive_whole_number'),
    ({'secondary_holes': 'spiral'}, 'secondary_holes', 'invalid_choice'),
    ({'secondary_holes': 'none', 'pintle_radial_hole_count': 8},
     'pintle_radial_hole_count', 'conflicts_with_secondary_holes_none'),
    ({'pintle_tangential_angle': 30}, 'pintle_tangential_angle',
     'applies_only_to_tangential_holes'),
    ({'secondary_holes': 'tangential', 'pintle_tangential_angle': 90},
     'pintle_tangential_angle', 'out_of_range'),
    ({'outer_diameter': 3.0}, 'outer_diameter',
     'housing_does_not_enclose_bore'),
    ({'pintle_radial_hole_diameter': 5.0}, 'pintle_radial_hole_diameter',
     'tip_holes_exceed_flow_area'),
    ({'pintle_radial_hole_count': 100000}, 'pintle_radial_hole_count',
     'tip_holes_do_not_fit_circumference'),
    ({'pintle_diameter': 1.0e7}, 'pintle_diameter',
     'pintle_wider_than_chamber'),
    ({'pintle_diameter': 1.0e300}, 'pintle_diameter', 'not_computable'),
])
def test_gecersiz_pintle_girdisi_adli_422(istemci, ek, alan, neden):
    kod, j = _post(istemci, **ek)
    assert kod == 422, (ek, str(j)[:300])
    kayitlar = [f for f in j.get('invalid_fields') or []
                if f.get('field') == alan]
    assert kayitlar, j.get('invalid_fields')
    assert kayitlar[0]['reason'] == neden


def test_cozucu_dogrudan_cagrida_da_kapi(varsayilan):
    a = varsayilan['motor']['injector_design_detail']['ox_circuit'][
        'total_area_mm2'] * 1e-6
    with pytest.raises(PintleGeometryInputError) as ex:
        resolve_pintle_geometry(a, {'n_radial_holes': True})
    assert ex.value.invalid_fields[0]['field'] == 'pintle_radial_hole_count'


# --------------------------------------------------------------------------
# F) Künye
# --------------------------------------------------------------------------
def test_dressler_bauer_sayisal_kural_atfi_yok():
    src = (KOK / 'hrma' / 'engines' / 'injector_design.py').read_text(
        encoding='utf-8')
    assert 'TRW mirası (Dressler & Bauer' not in src
    assert 'L_s/D_p ≈ 1 (skip distance kuralı)' not in src
    for anahtar in ('annulus_t_over_dp', 'blockage_factor_target',
                    'radial_flow_fraction'):
        assert PINTLE_RULE_BASIS[anahtar].startswith('HRMA choice')
    assert 'NOT' in PINTLE_RULE_BASIS['blockage_factor_band']
    utils = (KOK / 'hrma' / 'utils' / 'injector_design.py').read_text(
        encoding='utf-8')
    assert 'TRW heritage band' not in utils


# --------------------------------------------------------------------------
# G) Form, tablo, 2B kesit
# --------------------------------------------------------------------------
def _pintle_dali():
    src = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    bas = src.index("} else if (type === 'pintle') {")
    son = src.index("} else if (type === 'swirl') {", bas)
    return src, src[bas:son]


def test_formda_her_pintle_girdisinin_olcu_tanimli_ipucu_var():
    _src, dal = _pintle_dali()
    kimlikler = re.findall(r'<(?:input|select)[^>]*\bid="([\w-]+)"', dal)
    assert set(kimlikler) == {
        'secondary_holes', 'pintle_diameter', 'annular_gap', 'outer_diameter',
        'pintle_radial_hole_count', 'pintle_radial_hole_diameter',
        'skip_distance', 'pintle_tangential_angle'}
    gruplar = dal.split('<div class="form-group"')[1:]
    for grup in gruplar:
        assert 'class="tooltip-text" data-i18n=' in grup, grup[:120]
    assert 'pintle_spray_angle' not in dal
    assert re.search(r'value="radial"[^>]*selected', dal)


def test_form_bos_alanin_anahtarini_gondermez_ve_sabit_yazmaz():
    src = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    bas = src.index("} else if (injectorType === 'pintle') {")
    son = src.index("} else if (injectorType === 'swirl') {", bas)
    dal = src[bas:son]
    for alan in ('outer_diameter', 'pintle_diameter', 'annular_gap',
                 'pintle_radial_hole_count', 'pintle_radial_hole_diameter',
                 'skip_distance', 'pintle_tangential_angle'):
        assert f"enjAta('{alan}')" in dal, alan
    assert '|| 50' not in dal and '|| 25' not in dal
    un = src[src.index('var HYBRID_UNWIRED_INPUTS = {'):]
    un = un[:un.index('};')]
    for alan in ('annular_gap', 'skip_distance', 'pintle_spray_angle'):
        assert f'{alan}:' not in un, alan


def test_tablo_kanon_alanlarini_okur():
    src = (KOK / 'hrma' / 'static' / 'js' / 'app.js').read_text(
        encoding='utf-8')
    bas = src.index('function displayInjectorTable(')
    dal = src[bas:src.index("} else if (injectorData.type === 'swirl')",
                            bas)]
    dal = dal[dal.index("injectorData.type === 'pintle'"):]
    for alan in ('pintle_geometry', 'n_radial_holes', 'radial_hole_d_mm',
                 'bf', 'radial_flow_fraction', 'tmr', 'spray_half_angle_deg',
                 'spray_angle_basis', 'skip_distance_mm',
                 'annulus_bore_diameter', 'body_wall_thickness',
                 'pintle_geometry_source'):
        assert alan in dal, alan


def _kesit(veri):
    from hrma.visualization.visualization import create_pintle_cross_section
    d = json.loads(create_pintle_cross_section(veri))
    metin = ' '.join(
        [str(a.get('text') or '') for a in d['layout'].get('annotations', [])]
        + [str(t.get('text') or '') for t in d['data']]
        + [str(t.get('name') or '') for t in d['data']])
    return d, metin


def test_kesit_kanondan_govde_boyutlandirilmadi_ve_ls(varsayilan):
    inj = varsayilan['injector']
    d, metin = _kesit(inj)
    g = inj['pintle_geometry']
    assert 'body OD: not sized' in metin
    assert 'Annulus bore (body not sized)' in metin
    # Gövde dış hattı UYDURULMAZ: dolgu gövde izi hiç yok.
    assert not [t for t in d['data'] if t.get('name') == 'Injector Body']
    assert 'Do not machine' not in metin
    assert f"D_p = {g['d_pintle_mm']:.2f} mm" in metin
    assert f"t = {g['annulus_gap_mm']:.3f} mm" in metin
    assert f"L_s = {g['skip_distance_mm']:.2f} mm" in metin
    assert f"{g['n_radial_holes']} radial tip holes x d " \
           f"{g['radial_hole_d_mm']:.3f} mm" in metin
    assert f"BF {g['bf']:.3f}" in metin
    # Delik sırası L_s'de çizilir (tek çevresel sıra)
    oklar = [a for a in d['layout']['annotations']
             if a.get('showarrow') and a.get('ax') == a.get('x')
             and a.get('arrowcolor') == '#ff8c33']
    assert oklar and all(a['x'] == pytest.approx(g['skip_distance_mm'])
                         for a in oklar)


def test_kesit_govde_verilince_cizilir(kullanici_nd):
    d, metin = _kesit(kullanici_nd['injector'])
    assert 'body OD = 20.0 mm' in metin
    govde = [t for t in d['data'] if t.get('name') == 'Injector Body']
    ys = [abs(v) for v in govde[0]['y'] if v is not None]
    assert max(ys) == pytest.approx(10.0)
