# -*- coding: utf-8 -*-
"""V301/E2 (Ayberk tur 1) — pintle DIŞI enjektörlerde tek kanon.

Ayberk: "Enjektör kısmı full hatalı düzeltilmeli." Ölçülen kusurlar
(docs/scofield/raw/OH/V301/ayberk1/enjektor-genel/once.json, 1 kN, Pc 20 bar,
N₂O/HTPB):

* çarpışmalı: ekran bloğu 2 çift × Ø1,541 mm (7,456 mm², tek fazlı SPI),
  devre 3 delik × Ø2,111 mm (10,495 mm², Dyer NHNE) — tek sayıda delik
  benzer-akışkan çifti olamaz, ekran alanı iki-fazlı akıda hedef debinin
  ~%71'ini teslim eder;
* swirl: ekran tek eleman d_o 5,40 mm, devre 7 eleman × 2,42 mm; formda
  ekran K 0,052 / θ 64,4°, devre K 0,326 / θ 45°;
* duş başlığı: ``n_holes`` ve delik çapı bandı devreye hiç girmiyordu;
* koaksiyel: iç jet payı bant dışında SESSİZCE kırpılıyordu;
* hibritte anlamsız alanlar (triplet deseni, yakıt/ox momentum oranı)
  HTTP 200 ile like-doublet sonucu alıyordu;
* kullanıcı tank basıncı kipinde plaka bloğu doymuş yoğunlukla hız
  basıyordu (60,7 ⟷ 59,3 m/s).
"""
import math

import pytest

from hrma.app import app

E2_HIBRIT_GOVDESI = {
    'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'expansion_ratio': 0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
}
_ONBELLEK = {}


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as ist:
        yield ist


def _kos(istemci, anahtar, **ek):
    if anahtar not in _ONBELLEK:
        r = istemci.post('/calculate', json=dict(E2_HIBRIT_GOVDESI, **ek))
        _ONBELLEK[anahtar] = (r.status_code, r.get_json() or {})
    return _ONBELLEK[anahtar]


def _tamam(istemci, anahtar, **ek):
    kod, j = _kos(istemci, anahtar, **ek)
    assert kod == 200, j
    return j


# ---------------------------------------------------------------------------
# Çarpışmalı (benzer-akışkan çift)
# ---------------------------------------------------------------------------
def test_carpismali_ekran_devrenin_planini_tuketir(istemci):
    j = _tamam(istemci, 'imp', injector_type='impingement')
    inj, ozet = j['injector'], j['motor']['injector_design']
    detay = j['motor']['injector_design_detail']
    assert inj['n_holes'] == ozet['number_of_orifices']
    assert inj['n_holes'] % 2 == 0, 'benzer-akışkan çift: delik sayısı çift'
    assert inj['n_pairs'] * 2 == inj['n_holes']
    assert inj['hole_diameter'] == pytest.approx(ozet['orifice_diameter_mm'],
                                                 rel=1e-12)
    assert inj['injection_area'] == pytest.approx(
        ozet['total_injector_area_mm2'], rel=1e-9)
    assert inj['exit_velocity'] == pytest.approx(
        ozet['injection_velocity_m_s'], rel=1e-9)
    tam = 2.0 * detay['pattern']['impingement']['half_angle_deg']
    assert inj['impingement_angle_deg'] == pytest.approx(tam)
    assert detay['pattern']['n_elements'] == inj['n_pairs']
    plan = ozet['element_plan']
    assert plan['hole_count'] == inj['n_holes']
    assert 'odd hole count' in plan['pair_count_source']


def test_carpismali_cift_sayisi_ve_aci_devreye_girer(istemci):
    j = _tamam(istemci, 'imp_p3', injector_type='impingement',
               element_pairs=3, impingement_angle=80)
    inj, detay = j['injector'], j['motor']['injector_design_detail']
    assert inj['n_holes'] == 6 == detay['ox_circuit']['n_orifices']
    assert detay['pattern']['impingement']['half_angle_deg'] == pytest.approx(40)
    assert inj['impingement_angle_deg'] == pytest.approx(80)
    assert 'from the request' in detay['pattern']['impingement'][
        'half_angle_deg_basis']
    # Alan devrenin akış alanıdır: 6·π·d²/4.
    assert 6 * math.pi * inj['hole_diameter'] ** 2 / 4 == pytest.approx(
        detay['ox_circuit']['total_area_mm2'], rel=1e-9)


def test_carpismali_delik_capi_tolerans_icinde_kabul(istemci):
    j = _tamam(istemci, 'imp_d08', injector_type='impingement',
               orifice_diameter=0.8)
    inj = j['injector']
    plan = j['motor']['injector_design']['element_plan']
    assert inj['hole_diameter_requested'] == pytest.approx(0.8)
    assert abs(plan['requested_flow_area_ratio'] - 1.0) <= plan['tolerance_rel']
    assert abs(inj['hole_diameter'] / 0.8 - 1.0) <= 0.03


def test_carpismali_asiri_belirlenmis_plan_422(istemci):
    kod, j = _kos(istemci, 'imp_asiri', injector_type='impingement',
                  element_pairs=1, orifice_diameter=2.0)
    assert kod == 422, j
    assert j['error'] == 'injector_element_rejected'
    kayit = j['invalid_fields'][0]
    assert kayit['reason'] == 'flow_mismatch'
    assert kayit['nearest_plans'] and all(
        'hole_d_mm_for_exact_flow' in p for p in kayit['nearest_plans'])
    assert 'injector' not in j


@pytest.mark.parametrize('desen', ['triplet', 'quadlet', 'shear_coaxial', 7])
def test_hibritte_uygulanamayan_desen_422(istemci, desen):
    kod, j = _kos(istemci, f'imp_desen_{desen}', injector_type='impingement',
                  impingement_pattern=desen)
    assert kod == 422, j
    kayit = j['invalid_fields'][0]
    assert kayit['field'] == 'impingement_pattern'
    assert kayit['reason'] in ('not_applicable_to_hybrid', 'not_a_string')


@pytest.mark.parametrize('desen', ['like_on_like', 'doublet'])
def test_benzer_akiskan_desen_kabul(istemci, desen):
    j = _tamam(istemci, f'imp_ok_{desen}', injector_type='impingement',
               impingement_pattern=desen)
    assert j['injector']['element_pattern'] == 'like_on_like_doublet'


def test_anlamsiz_alanlar_ust_duzey_inputs_not_used(istemci):
    j = _tamam(istemci, 'imp_unused', injector_type='impingement',
               momentum_ratio=1.0, impingement_distance=10)
    adlar = {k['field']: k for k in (j.get('inputs_not_used') or [])}
    assert 'momentum_ratio' in adlar and 'impingement_distance' in adlar
    assert 'ONE liquid stream' in adlar['momentum_ratio']['message']
    assert {u['field'] for u in j['injector']['unused_inputs']} == {
        'momentum_ratio', 'impingement_distance'}


@pytest.mark.parametrize('ek,alan,neden', [
    ({'impingement_angle': 0.0}, None, None),            # 0 = verilmedi
    ({'impingement_angle': 180}, 'impingement_angle', 'out_of_range'),
    ({'impingement_angle': -5}, 'impingement_angle', 'out_of_range'),
    ({'impingement_angle': 'x'}, 'impingement_angle', 'not_a_number'),
    ({'element_pairs': 2.5}, 'element_pairs', 'not_a_positive_whole_number'),
    ({'element_pairs': True}, 'element_pairs', 'not_a_number'),
    ({'element_pairs': 61}, 'element_pairs', 'out_of_range'),
    ({'orifice_diameter': -1}, 'orifice_diameter', 'not_positive'),
    ({'orifice_diameter': float('inf')}, 'orifice_diameter', None),
])
def test_carpismali_girdi_kapisi(istemci, ek, alan, neden):
    r = istemci.post('/calculate', json=dict(E2_HIBRIT_GOVDESI, injector_type='impingement',
                                             **ek))
    if alan is None and neden is None and 'impingement_angle' in ek:
        assert r.status_code == 200
        return
    assert r.status_code in (400, 422), r.get_json()
    if alan is not None and r.status_code == 422:
        kayit = r.get_json()['invalid_fields'][0]
        assert kayit['field'] == alan
        if neden:
            assert kayit['reason'] == neden


# ---------------------------------------------------------------------------
# Swirl
# ---------------------------------------------------------------------------
def test_swirl_ekran_devrenin_elemanini_tuketir(istemci):
    j = _tamam(istemci, 'sw', injector_type='swirl')
    inj, detay = j['injector'], j['motor']['injector_design_detail']
    sw, oxc = detay['swirl_geometry'], detay['ox_circuit']
    assert inj['n_elements'] == oxc['n_orifices']
    assert inj['exit_orifice_diameter'] == pytest.approx(oxc['orifice_d_mm'],
                                                         rel=1e-12)
    assert inj['atomizer_constant_K'] == pytest.approx(sw['K'], rel=1e-12)
    assert inj['spray_half_angle_deg'] == pytest.approx(
        detay['atomization']['spray_cone_half_angle_deg'], rel=1e-12)
    assert inj['injection_area'] == pytest.approx(oxc['total_area_mm2'],
                                                  rel=1e-9)
    assert inj['orifice_mean_velocity'] == pytest.approx(oxc['velocity_m_s'],
                                                         rel=1e-9)
    # Ucun beyanlı yuva sayısı varsayılanı devreye de gider (tek sayı).
    assert sw['tangential_inlets'] == inj['n_slots'] == 6
    assert inj['n_slots'] * inj['slot_width'] * inj['slot_height'] == \
        pytest.approx(sw['tangential_inlet_area_mm2'], rel=1e-9)


def test_swirl_hedef_aci_ve_oda_capi_devreye_girer(istemci):
    from hrma.engines.injector_design import swirl_K_from_theta
    j = _tamam(istemci, 'sw_t30', injector_type='swirl', swirl_angle=30,
               swirl_chamber_diameter=8, n_slots=4)
    sw = j['motor']['injector_design_detail']['swirl_geometry']
    inj = j['injector']
    assert sw['K'] == pytest.approx(swirl_K_from_theta(30), rel=1e-9)
    assert inj['spray_half_angle_deg'] == pytest.approx(30, rel=1e-9)
    assert sw['swirl_chamber_d_mm'] == pytest.approx(8)
    assert inj['swirl_chamber_diameter'] == pytest.approx(8)
    assert sw['tangential_inlets'] == 4 == inj['n_slots']


def test_swirl_yuva_olcusu_K_yi_devrede_belirler(istemci):
    j = _tamam(istemci, 'sw_yuva', injector_type='swirl', n_slots=6,
               slot_width=1.2, slot_height=0.6)
    sw = j['motor']['injector_design_detail']['swirl_geometry']
    inj = j['injector']
    assert sw['tangential_inlet_area_mm2'] == pytest.approx(6 * 1.2 * 0.6,
                                                            rel=1e-6)
    assert inj['slot_width'] == pytest.approx(1.2)
    assert inj['slot_height'] == pytest.approx(0.6)
    assert inj['atomizer_constant_K'] == pytest.approx(sw['K'], rel=1e-12)
    assert 'slot geometry' in inj['swirl_k_source']


@pytest.mark.parametrize('ek,neden', [
    ({'slot_width': 1.0}, 'incomplete_pair'),
    ({'slot_width': 1.2, 'slot_height': 0.6, 'swirl_angle': 40},
     'conflicts_with_slot_geometry'),
    ({'slot_width': 30, 'slot_height': 30}, 'outside_swirl_envelope'),
    ({'n_slots': 2.5}, 'not_a_positive_whole_number'),
])
def test_swirl_girdi_kapisi_422(istemci, ek, neden):
    r = istemci.post('/calculate', json=dict(E2_HIBRIT_GOVDESI, injector_type='swirl',
                                             **ek))
    assert r.status_code == 422, r.get_json()
    assert neden in [k['reason'] for k in r.get_json()['invalid_fields']]


def test_swirl_zarf_disi_aci_eski_govdeyle_422(istemci):
    r = istemci.post('/calculate', json=dict(E2_HIBRIT_GOVDESI, injector_type='swirl',
                                             swirl_angle=85))
    assert r.status_code == 422
    assert r.get_json()['error'] == 'swirl_angle_outside_solver_envelope'


# ---------------------------------------------------------------------------
# Duş başlığı: delik sayısı ve bant devreye
# ---------------------------------------------------------------------------
def test_dus_basligi_delik_sayisi_devreye_girer(istemci):
    j = _tamam(istemci, 'sh_n8', injector_type='showerhead', n_holes=8)
    inj, ozet = j['injector'], j['motor']['injector_design']
    assert inj['n_holes'] == ozet['number_of_orifices'] == 8
    assert inj['hole_diameter'] == pytest.approx(ozet['orifice_diameter_mm'],
                                                 rel=1e-12)


def test_dus_basligi_bant_devrenin_planini_belirler(istemci):
    j = _tamam(istemci, 'sh_bant', injector_type='showerhead',
               hole_diameter_min=1.0, hole_diameter_max=1.5)
    ozet = j['motor']['injector_design']
    assert 1.0 <= ozet['orifice_diameter_mm'] <= 1.5
    assert j['injector']['n_holes'] == ozet['number_of_orifices']
    bant = j['motor']['injector_design_detail']['orifice_band']
    assert (bant['d_min_mm'], bant['d_max_mm']) == (1.0, 1.5)
    assert bant['source'].startswith('caller-supplied')


def test_dus_basligi_ters_bant_422(istemci):
    r = istemci.post('/calculate', json=dict(E2_HIBRIT_GOVDESI, injector_type='showerhead',
                                             hole_diameter_min=2.0,
                                             hole_diameter_max=1.0))
    assert r.status_code == 422
    assert r.get_json()['invalid_fields'][0]['reason'] == 'band_inverted'


# ---------------------------------------------------------------------------
# Koaksiyel: pay kırpılmaz
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ek,neden', [
    ({'coaxial_inner_flow_fraction': 0.05}, 'out_of_range'),
    ({'coaxial_inner_flow_fraction': 0.95}, 'out_of_range'),
    ({'inner_diameter': 2, 'outer_annulus_diameter': 8}, 'out_of_range'),
    ({'inner_diameter': 5}, 'incomplete_pair'),
    ({'inner_diameter': 8, 'outer_annulus_diameter': 5},
     'not_larger_than_inner_diameter'),
    ({'coaxial_inner_flow_fraction': 0.5, 'inner_diameter': 5,
      'outer_annulus_diameter': 8}, 'conflicts_with_inner_outer_diameter'),
    ({'coaxial_inner_flow_fraction': 'yarim'}, 'not_a_number'),
])
def test_koaksiyel_pay_kapisi_422(istemci, ek, neden):
    r = istemci.post('/calculate', json=dict(E2_HIBRIT_GOVDESI, injector_type='coaxial',
                                             **ek))
    assert r.status_code == 422, r.get_json()
    assert r.get_json()['invalid_fields'][0]['reason'] == neden


def test_koaksiyel_varsayilan_pay_beyanli(istemci):
    from hrma.utils.injector_design import COAX_INNER_FLOW_FRACTION
    j = _tamam(istemci, 'coax', injector_type='coaxial')
    kunye = {k['field']: k for k in j.get('defaults_applied') or []}
    assert kunye['coaxial_inner_flow_fraction']['value'] == \
        COAX_INNER_FLOW_FRACTION
    inj = j['injector']
    assert inj['inner_flow_fraction'] == COAX_INNER_FLOW_FRACTION
    assert 'HRMA choice' in inj['inner_flow_fraction_source']
    # V301/H2 (beklenti değişti; gerekçe docs/scofield/raw/OH/V301/bilinen/
    # hibrit/RAPOR.md): devre artık tek akışkanlı koaksiyeli çözüyor ve
    # plaka bloğu onun geometrisini TÜKETİYOR (eskiden 'not_available').
    assert inj['circuit_solution'].startswith('consumed')


def test_koaksiyel_eski_cap_cifti_yalniz_payi_belirler(istemci):
    j = _tamam(istemci, 'coax_eski', injector_type='coaxial',
               inner_diameter=5, outer_annulus_diameter=8, recess_length=2,
               n_elements=19)
    inj = j['injector']
    assert inj['inner_flow_fraction'] == pytest.approx(25 / 64)
    assert 'ONLY the flow share' in inj['inner_flow_fraction_source']
    adlar = {k['field'] for k in j.get('inputs_not_used') or []}
    assert {'recess_length', 'n_elements'} <= adlar


def test_koaksiyel_setter_kirpmaz():
    from hrma.utils.injector_design import InjectorDesign
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        d = InjectorDesign(mdot_ox=0.4, chamber_pressure=20.0,
                           tank_pressure=50.0, injector_type='coaxial')
    with pytest.raises(ValueError, match='not clamped'):
        d.set_coaxial_params(inner_flow_fraction=0.05)


# ---------------------------------------------------------------------------
# Kullanıcı tank basıncı: plaka yoğunluğu devreden (madde 9)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('tip', ['showerhead', 'impingement', 'swirl'])
def test_kullanici_tank_kipinde_plaka_hizi_devreyle_ayni(istemci, tip):
    j = _tamam(istemci, f'tank_{tip}', injector_type=tip,
               tank_pressure_source='user', tank_pressure=60)
    inj, ozet = j['injector'], j['motor']['injector_design']
    giris = ozet['inlet_state']
    assert inj['density_source'].startswith('injector circuit inlet state')
    if tip == 'swirl':
        assert inj['orifice_mean_velocity'] == pytest.approx(
            ozet['injection_velocity_m_s'], rel=1e-9)
    else:
        assert inj['exit_velocity'] == pytest.approx(
            ozet['injection_velocity_m_s'], rel=1e-9)
    assert giris['liquid_density_kg_m3'] > 785.2   # sıkıştırılmış sıvı


def test_kullanici_tank_kipinde_istek_yogunlugu_beyan_edilir(istemci):
    j = _tamam(istemci, 'tank_rho', injector_type='showerhead',
               tank_pressure_source='user', tank_pressure=60,
               oxidizer_density=786.25)
    kayit = [k for k in j.get('inputs_not_used') or []
             if k['field'] == 'oxidizer_density']
    assert kayit and kayit[0]['reason'] == 'superseded_by_injector_inlet_state'


# ---------------------------------------------------------------------------
# Bant uyarıları: "optimal" kaynaksız kullanılmaz
# ---------------------------------------------------------------------------
def test_bant_uyarilari_bulussal_esik_diye_beyanli():
    """Hız, L/D ve çarpışma açısı bantlarının üçü de kaynaksız: metin
    "optimal" demez, HRMA buluşsal eşiği olduğunu ve (açı için) SP-8089'un
    60° önerdiğini söyler. Bant dışı değerler DOĞRUDAN beslenir (çalışma
    noktası bandın içine düşse bile bekçi ısırır)."""
    import contextlib
    import io
    from hrma.utils import injector_design as u
    with contextlib.redirect_stdout(io.StringIO()):
        d = u.InjectorDesign(mdot_ox=0.4, chamber_pressure=20.0,
                             tank_pressure=50.0)
    uyarilar = d._check_warnings(70.0, 1e6, 1.4)
    hiz = [w for w in uyarilar if w.startswith('Exit velocity')]
    ld = [w for w in uyarilar if w.startswith('L/D ratio')]
    assert len(hiz) == 1 and len(ld) == 1, uyarilar
    for w in hiz + ld:
        assert 'optimal' not in w.lower(), w
        assert 'HRMA heuristic threshold - no literature value' in w, w
    assert 'NASA SP-8089 p. 84' in ld[0]
    aci = u._carpisma_acisi_bant_metni(100)
    assert 'optimal' not in aci and 'typical' not in aci
    assert 'HRMA heuristic threshold' in aci
    assert 'NASA SP-8089 pp. 78-79 recommends 60 deg' in aci
    kaynak = open(u.__file__, encoding='utf-8').read()
    assert 'outside optimal range' not in kaynak


def test_bant_sabitleri_tek_yerde():
    from hrma.utils import injector_design as u
    assert u.INJECTION_VELOCITY_HEURISTIC_BAND_M_S == (20.0, 50.0)
    assert u.ORIFICE_LD_HEURISTIC_BAND == (3.0, 5.0)
    from hrma.engines import injector_design as e
    assert u.IMPINGEMENT_HALF_ANGLE_DEG is e.IMPINGE_HALF_ANGLE_DEG
    assert u.SWIRL_CHAMBER_D_RATIO is e.SWIRL_CHAMBER_D_OVER_DO


# ---------------------------------------------------------------------------
# ΔP açık ezmesi: kanon kullanılmaz, eleman girdisi devreye gitmez
# ---------------------------------------------------------------------------
def test_dp_ezmesinde_eleman_girdisi_devreye_gitmez(istemci):
    j = _tamam(istemci, 'imp_ezme', injector_type='impingement',
               element_pairs=1, orifice_diameter=2.0, pressure_drop=30.0,
               pressure_drop_source='user')
    assert j['injector']['pressure_drop_source'] == 'user override'
    assert j['motor']['injector_design']['element_plan'][
        'requested_pairs'] is None
