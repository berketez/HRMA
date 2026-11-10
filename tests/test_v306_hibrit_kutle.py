"""V306/HİBRİT-KÜTLE — hibrit motorda kütle, malzeme ve sayı tutarlılığı.

Kanıt: docs/scofield/raw/OH/V306/hibrit-kutle/ (olcum_once.json ⟷
olcum_sonra.json, k7_*.json, k8_*.json, RAPOR.md). Her bekçi ürünün bir
onarımını kilitler; beklenen değerler ürün sabitlerinden değil, aynı
yanıtın kendi alanlarından (kimlik) okunur.

Kalemler:
  1  ek + gövde lülesinde çizilen katının yoğunluk künyesi = kütle / hacim
  2  eksenel profil hibritte lüle bölgesinin malzemesini taşır
  4  N₂O ullage buharı yüklenen oksitleyicide (tek kütle bütçesi) +
     Tasarım Raporu "Total Propellant Mass (loaded)" tek taban
  5  Basınçlı Kap sekmesi hibritte kamara malzemesiyle tohumlanır
  6  kuru kütle enjektör plakasını içerir; CAD toplamından farkı = kapaklar
  7  patlayıcı hükmü beyansız geri çekilince Gurney türevleri yayımlanmaz
  8  çizilemeyen kamara boyu adlı ret: kod + sayılar, traceback yok
"""
import contextlib
import io
import json
import math
import os
import pathlib
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
H = {'Host': '127.0.0.1:8080'}

#: test_d24_hibrit_a1 HIBRIT_YUK (N₂O kendinden basınçlı tank, boşalma).
D24_YUK = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 1.0,
           'chamber_pressure': 20.0, 'fuel_type': 'htpb',
           'oxidizer_type': 'n2o'}


def _calculate(govde):
    from hrma.app import app
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = app.test_client().post('/calculate', json=govde, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def taban():
    """test_cad_geometry_consistency fikstürü (grafit ek + gövde, enjektör)."""
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    return _calculate(dict(HYBRID_BASE))


@pytest.fixture(scope='module')
def d24():
    return _calculate(dict(D24_YUK))


# ----------------------------------------------------------------- kalem 1
def test_k1_cizilen_katinin_yogunlugu_kutle_bolu_hacim(taban):
    ps = taban['cad_design']['performance_summary']
    mb, ms = ps['mass_breakdown'], ps['material_summary']
    yap = taban['motor']['nozzle_geometry']['nozzle_construction']
    assert yap['type'] == 'insert_plus_structural_housing'
    bil = ms['nozzle_mass_components']
    m = mb['nozzle_mass']
    assert bil['insert']['mass_kg'] + bil['housing']['mass_kg'] == \
        pytest.approx(m, rel=1e-12)
    assert ms['nozzle_mass_density_kg_m3'] * bil['drawn_volume_m3'] == \
        pytest.approx(m, rel=1e-12)
    # Ek seçilen malzemenin, gövde kamara malzemesinin yoğunluğunu taşır;
    # yayımlanan yoğunluk ikisinin arasındadır (tek malzemeye eşit değil).
    assert bil['insert']['density_kg_m3'] == yap['insert']['density_kg_m3']
    assert bil['housing']['density_kg_m3'] == yap['housing']['density_kg_m3']
    lo, hi = sorted((bil['insert']['density_kg_m3'],
                     bil['housing']['density_kg_m3']))
    assert lo < ms['nozzle_mass_density_kg_m3'] < hi
    assert 'INSERT' in ms['nozzle_mass_density_source']
    # Motorun kuru kütlesindeki lüle = CAD lülesi (tek sayı).
    assert taban['motor']['structural_analysis']['weight_analysis'][
        'nozzle_weight'] == m


def test_k1_tek_parca_lulede_kunye_degismez():
    from hrma.export.cad_visualization import (
        nozzle_insert_housing_declaration)
    assert nozzle_insert_housing_declaration({}) is None
    assert nozzle_insert_housing_declaration(
        {'nozzle_geometry': {'nozzle_construction': {'type': 'single'}}}) \
        is None


# ----------------------------------------------------------------- kalem 2
def test_k2_profil_hibritte_lule_malzemesini_tasir(taban):
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
    from hrma.fea import bridge
    m = taban['motor']
    with contextlib.redirect_stdout(io.StringIO()):
        prof = HeatTransferAnalyzer().analyze_axial_profile(m, n_stations=40)
        sonuc = bridge.extract_thermal_inputs(m, axial_profile=prof,
                                              include_chamber=False)
    lule = m['nozzle_material_analysis']['material']
    assert prof['material'] == lule
    assert 'nozzle_material_analysis.material' in prof['material_source']
    assert sonuc['status'] == bridge.BRIDGE_STATUS_OK, sonuc.get('reason')


def test_k2_acik_malzeme_ustundur_ve_tanisiz_sozluk_celik_kalir(taban):
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
    a = HeatTransferAnalyzer()
    with contextlib.redirect_stdout(io.StringIO()):
        acik = a.analyze_axial_profile(taban['motor'], n_stations=20,
                                       material='steel_4130')
        duz = {k: v for k, v in taban['motor'].items()
               if k != 'structural_analysis'}
        tanisiz = a.analyze_axial_profile(duz, n_stations=20)
    assert acik['material'] == 'steel_4130' and 'material_source' not in acik
    assert tanisiz['material'] == 'steel'
    assert 'material_source' not in tanisiz


# ----------------------------------------------------------------- kalem 4
def test_k4_yuklenen_ox_sivi_arti_buhar_tek_butce(d24):
    from hrma.analysis.flight_vehicle import motor_flight_thrust
    m = d24['motor']
    tb = m['tank_blowdown']
    assert tb['status'] == 'modelled' and tb['feed_mode'] == 'blowdown'
    env = tb['oxidizer_inventory']
    sivi, buhar = env['tank_initial_liquid_kg'], env['tank_initial_vapour_kg']
    assert buhar > 0.0
    assert m['oxidizer_ullage_vapour_kg'] == buhar
    assert m['oxidizer_liquid_loaded_kg'] == sivi
    assert m['oxidizer_mass'] == pytest.approx(env['tank_initial_kg'],
                                               rel=1e-12)
    assert m['oxidizer_mass'] == pytest.approx(sivi + buhar, rel=1e-12)
    assert m['propellant_mass_total'] == pytest.approx(
        m['oxidizer_mass'] + m['fuel_mass'], rel=1e-12)
    kd = m['design_summary']['key_dimensions']
    assert kd['total_mass_kg'] == pytest.approx(
        m['oxidizer_mass'] + m['fuel_mass_loaded']
        + kd['dry_mass_estimate_kg'], rel=1e-12)
    assert m['propellant_mass_loaded_kg'] == pytest.approx(
        m['oxidizer_mass'] + m['fuel_mass_loaded'], rel=1e-12)
    assert m['oxidizer_mass_residual_kg'] == pytest.approx(
        m['oxidizer_mass'] - m['oxidizer_mass_consumed_kg'], rel=1e-12)
    # Uçuşun taşıdığı kalan = tankta kalan ox + yanmayan yakıt.
    u = motor_flight_thrust('hybrid', d24)
    kalan_ucus = u['propellant_loaded_kg'] - u['propellant_consumed_kg']
    kalan_gercek = (m['oxidizer_mass_residual_kg']
                    + m['fuel_mass'] - m['fuel_mass_consumed_kg'])
    assert kalan_ucus == pytest.approx(kalan_gercek, rel=1e-9)
    # Tank sonu (çözücünün tank nesnesi) ile de kapanır (Δt/4 sınırı).
    assert m['oxidizer_mass_residual_kg'] == pytest.approx(
        env['tank_final_kg'], abs=1e-4)


def test_k4_rapor_toplam_itici_tek_taban():
    js = (JS / 'app.js').read_text(encoding='utf-8')
    i = js.index("T('app.rep.secPropellant'")
    blok = js[i:js.index('</tbody>', i)]
    assert "fieldTag('propellant_mass_loaded_kg')" in blok
    assert "fieldTag('propellant_mass_total')" not in blok
    for dosya in ('i18n_common.js',):
        s = (JS / dosya).read_text(encoding='utf-8')
        assert "'app.rep.propMassTotalLoaded': 'Total Propellant Mass (loaded)'" in s
        assert "'app.rep.propMassTotalLoaded': 'Toplam İtici Kütlesi (yüklü)'" in s


# ----------------------------------------------------------------- kalem 5
@pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
def test_k5_basincli_kap_hibritte_kamara_malzemesi():
    kod = """
global.window = {AnalysisDock: {ui: {readLengthMM: () => 106,
                   readChamberMaterial: (r) => r.mat, WITHHELD_KEY: '__withheld'},
                 register(s) { global.S = s; }, getMotorType() { return 'hybrid'; }}};
global.document = {};
require(%r);
console.log(JSON.stringify([S.fromResults({chamber_pressure: 20, mat: 'ss_304'}),
                            S.fromResults({chamber_pressure: 20})]));
""" % str(JS / 'panels' / 'vessel_panel.js')
    p = subprocess.run([shutil.which('node'), '-e', kod], capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    var, yok = json.loads(p.stdout.strip().splitlines()[-1])
    assert var['material'] == 'ss_304'
    assert 'chamber_material_not_in_results' in yok['__withheld']['material']


# ----------------------------------------------------------------- kalem 6
def test_k6_kuru_kutle_tek_tanim_enjektor_dahil(taban):
    m = taban['motor']
    w = m['structural_analysis']['weight_analysis']
    kd = m['design_summary']['key_dimensions']
    mb = taban['cad_design']['performance_summary']['mass_breakdown']
    assert mb['injector_mass'] > 0.0
    assert w['injector_weight'] == mb['injector_mass']
    assert kd['dry_mass_estimate_kg'] == pytest.approx(w['total_weight'],
                                                       rel=1e-12)
    assert w['total_weight'] == pytest.approx(
        w['chamber_weight'] + w['nozzle_weight'] + w['end_caps_weight']
        + w['injector_weight'], rel=1e-12)
    # İki toplamın farkı TAM olarak çizilmeyen uç kapaklarıdır.
    assert kd['dry_mass_estimate_kg'] - mb['total_dry_mass'] == \
        pytest.approx(w['end_caps_weight'], rel=1e-9)
    assert 'injector plate' in kd['dry_mass_basis']
    assert sum(w['weight_breakdown'].values()) == pytest.approx(100.0)


# ----------------------------------------------------------------- kalem 7
def test_k7_beyansiz_geri_cekmede_gurney_yayimlanmaz():
    from hrma.analysis.safety_analysis import (
        GURNEY_FRAGMENT_FIELDS, SafetyAnalyzer)
    with contextlib.redirect_stdout(io.StringIO()):
        sa = SafetyAnalyzer().analyze_comprehensive_safety(
            motor_data={'chamber_pressure': 30.0, 'thrust': 5000.0,
                        'burn_time': 10.0, 'chamber_diameter': 0.12,
                        'chamber_length': 0.6},
            propellant_mass=20.0, motor_type='hybrid', oxidizer_type='lox',
            fuel_type='htpb')
    eh = sa['explosive_hazards']
    assert eh['explosive_class'] is None
    assert eh['explosive_verdict_withheld_because']
    fh = eh['fragment_hazards']
    for alan in GURNEY_FRAGMENT_FIELDS:
        assert alan in fh and fh[alan] is None, alan
    assert fh['fragment_throw_status'] == 'withheld'
    assert 'Gurney' in fh['fragment_throw_reason']
    ex = sa['emergency_procedures']['explosion_response']
    assert ex['evacuation_distance'] is None
    assert ex['evacuation_distance_status'] == 'withheld'


# ----------------------------------------------------------------- kalem 8
def test_k8_cizilemeyen_kamara_boyu_adli_ret_traceback_yok(taban, capsys):
    from hrma.export.cad_visualization import (
        CHAMBER_LENGTH_MAX_M, MotorCADDesigner)
    m = dict(taban['motor'])
    # Uzunluk iki yerde yayımlanır (düz alan + motor_geometry SI bloğu);
    # tur L5'te (100 kN / 90 s) ikisi de 15,02 m idi.
    m['chamber_length'] = CHAMBER_LENGTH_MAX_M * 3.0
    m['motor_geometry'] = dict(m.get('motor_geometry') or {},
                               chamber_length=CHAMBER_LENGTH_MAX_M * 3.0)
    capsys.readouterr()
    cad = MotorCADDesigner().generate_3d_motor_assembly(m)
    cikti = capsys.readouterr()
    assert cad['error_code'] == 'chamber_length_out_of_range'
    assert cad['error_params']['max_m'] == CHAMBER_LENGTH_MAX_M
    assert cad['error_params']['chamber_length_m'] == pytest.approx(
        CHAMBER_LENGTH_MAX_M * 3.0)
    assert 'HRMA choice' in cad['error']
    assert 'Traceback' not in cikti.err and 'Traceback' not in cikti.out
