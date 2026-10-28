"""V301/K-B bekçileri — katı malzeme, tane tipleri, ölü girdiler.

Kanıt ve önce/sonra: docs/scofield/raw/OH/V301/kati-sivi/K-B/RAPOR.md.
Kalemler: KT-04, KT-05, KT-07, KT-08, KT-09, KT-10, KT-11, KT-12, K-A
DEVİR'leri (sessiz kırpma, tam sayı kapısı, gizli sayılar), NK-28, NK-30.
"""
import re
from pathlib import Path

import pytest

from hrma.app import app
from hrma.engines.solid_rocket_engine import (
    SOLID_CASE_LIMIT_STATUS_NO_RECORD,
    SOLID_CASE_LIMIT_STATUS_RECORD,
    SOLID_WAGON_WHEEL_DEFAULTS,
    SolidRocketEngine,
    solid_case_material_record,
    solid_material_options,
    solid_nozzle_material_record,
)

KOK = Path(__file__).resolve().parents[1]
SABLON = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(encoding='utf-8')
SOZLUK = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
    encoding='utf-8')
ORTAK = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
    encoding='utf-8')

#: Sayfa biçimli en küçük geçerli gövde (geometri kipi, APCP).
TABAN = {'propellant_type': 'apcp', 'chamber_pressure': 40,
         'outer_diameter': 100, 'core_diameter': 48, 'grain_length': 500,
         'grain_type': 'bates'}


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, **ek):
    r = istemci.post('/calculate_solid', json=dict(TABAN, **ek))
    return r.status_code, r.get_json()


def _uyari_kodlari(js):
    return {w.get('code') for w in js.get('design_warnings') or []
            if isinstance(w, dict)}


def _sinirlar(js):
    return js['thermal_analysis']['thermal_management'][
        'material_temperature_limits']


# --------------------------------------------------------------------------
# KT-10 / KT-12 — seçenekler sunucudan, çözülemeyen ad 422
# --------------------------------------------------------------------------
class TestMalzemeSecenekleri:
    def test_sayfa_secenekleri_sunucu_kaydiyla_birebir(self, istemci):
        html = istemci.get('/solid').get_data(as_text=True)
        for alan in ('case_material', 'nozzle_material'):
            blok = re.search(r'<select id="%s"[^>]*>(.*?)</select>' % alan,
                             html, re.S).group(1)
            assert re.findall(r'value="([\w-]+)"', blok) == [
                o['value'] for o in solid_material_options(alan)]

    def test_sablonda_elle_secenek_yok_ve_fenolik_yok(self):
        for alan in ('case_material', 'nozzle_material'):
            blok = re.search(r'<select id="%s"[^>]*>(.*?)</select>' % alan,
                             SABLON, re.S).group(1)
            assert 'solid_materials.%s.options' % alan in blok
            assert not re.search(r'<option value="[a-z]', blok)
        assert all(o['value'] != 'phenolic'
                   for o in solid_material_options('nozzle_material'))

    def test_eski_form_degerleri_korunur(self):
        degerler = {o['value'] for o in solid_material_options('case_material')}
        assert {'steel', 'aluminum', 'titanium', 'composite'} <= degerler
        assert solid_case_material_record('aluminum')['material_key'] == \
            'aluminum_6061'

    def test_karbon_karbon_kendi_kaydi(self):
        kayit = solid_nozzle_material_record('carbon_carbon')
        assert kayit['material_key'] == 'carbon_carbon'
        assert solid_nozzle_material_record('c-c')['material_key'] == \
            'carbon_carbon'
        assert solid_nozzle_material_record('phenolic') is None

    @pytest.mark.parametrize('alan,deger', [
        ('nozzle_material', 'phenolic'), ('nozzle_material', 'peynir'),
        ('nozzle_material', 123), ('throat_material', 'peynir'),
        ('case_material', 'peynir'), ('case_material', True)])
    def test_cozulemeyen_ad_adli_422(self, istemci, alan, deger):
        kod, js = _post(istemci, **{alan: deger})
        assert kod == 422
        assert js['error'] == 'unresolved_material'
        assert js['invalid_fields'][0]['field'] == alan
        assert js['invalid_fields'][0]['page_options']

    def test_her_sunulan_secenek_hesaplanir(self, istemci):
        for alan in ('case_material', 'nozzle_material'):
            for o in solid_material_options(alan):
                kod, js = _post(istemci, **{alan: o['value']})
                assert kod == 200, (alan, o['value'], js)

    def test_kritik_lule_uyarisi_hicbir_secenekte_sessizce_kaybolmaz(
            self, istemci):
        for o in solid_material_options('nozzle_material'):
            kod, js = _post(istemci, nozzle_material=o['value'])
            nma = js['nozzle_material_analysis']
            assert nma['status'] == 'analyzed', o['value']
            asim = nma['verdict'] == 'EXCEEDS_ALLOWABLE'
            assert asim == ('warn.solid.nozzle_material_over_temp'
                            in _uyari_kodlari(js)), o['value']

    def test_cad_lule_adi_yer_tutucu_degil(self, istemci):
        kod, js = _post(istemci, nozzle_material='tungsten',
                        erosion_factor=0.05)
        assert js['cad_design']['nozzle_design']['material'] != \
            'User-supplied coefficient'


# --------------------------------------------------------------------------
# KT-11 — kompozit kasa: sessiz 811 K yok
# --------------------------------------------------------------------------
class TestKompozitIsilSinir:
    def test_kompozit_kayit_yok_hukum_degerlendirilmedi(self, istemci):
        kod, js = _post(istemci, case_material='composite')
        assert kod == 200
        s = _sinirlar(js)
        assert s['case_limit_status'] == SOLID_CASE_LIMIT_STATUS_NO_RECORD
        assert s['case_max_temp_k'] is None
        assert s['safety_margin_k'] is None
        assert 'warn.solid.case_thermal_not_evaluated' in _uyari_kodlari(js)
        assert js['thermal_analysis']['heat_transfer'][
            'thermal_protection_rating'].startswith('Not evaluated')

    def test_celik_kayittan(self, istemci):
        kod, js = _post(istemci, case_material='steel')
        s = _sinirlar(js)
        assert s['case_limit_status'] == SOLID_CASE_LIMIT_STATUS_RECORD
        assert s['case_max_temp_k'] == pytest.approx(811.0)
        assert isinstance(s['safety_margin_k'], float)

    def test_sinif_kodu_sayfada_cevrilir(self):
        assert ("'Not evaluated — no temperature limit on record for this "
                "case material':") in SABLON
        assert SOZLUK.count("'solid.js.class.not_evaluated_no_record'") == 2


# --------------------------------------------------------------------------
# KT-12 — akma kaynağı
# --------------------------------------------------------------------------
class TestAkmaKaynagi:
    @pytest.mark.parametrize('malzeme', ['aluminum', 'titanium', 'steel_4130'])
    def test_malzeme_kipi_kimlik_bolunmesi_yok(self, istemci, malzeme):
        kod, js = _post(istemci, case_material=malzeme,
                        yield_strength_source='material')
        ps = js['safety_analysis']['pressure_safety']
        assert ps['material_identity_consistent'] is True
        assert 'warn.solid.case_yield_differs_from_material' not in \
            _uyari_kodlari(js)

    def test_malzeme_kipinde_gonderilen_akma_uygulanmaz_ve_beyan(
            self, istemci):
        kod, js = _post(istemci, case_material='aluminum',
                        yield_strength_source='material', yield_strength=250)
        assert js['unwired_inputs']['overridden_by_material'] == [
            'yield_strength']
        assert js['safety_analysis']['pressure_safety'][
            'material_identity_consistent'] is True

    def test_kullanici_kipi_farkli_deger_adli_uyari(self, istemci):
        kod, js = _post(istemci, case_material='aluminum',
                        yield_strength_source='user', yield_strength=250)
        assert 'warn.solid.case_yield_differs_from_material' in \
            _uyari_kodlari(js)

    def test_eski_api_akma_yine_kullanici(self, istemci):
        kod, js = _post(istemci, case_material='steel', yield_strength=400)
        assert 'warn.solid.case_yield_differs_from_material' in \
            _uyari_kodlari(js)

    def test_taninmayan_kip_422(self, istemci):
        kod, js = _post(istemci, yield_strength_source='peynir')
        assert kod == 422
        assert js['invalid_fields'][0]['field'] == 'yield_strength_source'

    def test_toplayici_malzeme_kipinde_akma_gondermez(self):
        assert '...solidYieldFields(),' in SABLON
        govde = SABLON[SABLON.index('function solidYieldFields()'):]
        govde = govde[:govde.index('\n        }\n')]
        assert "if (deger === 'user')" in govde


# --------------------------------------------------------------------------
# KT-04 / KT-05 — erozif k ve σ kipi
# --------------------------------------------------------------------------
class TestKatsayiKipi:
    def test_bayraksiz_deger_uygulanmaz_ve_adiyla_beyan(self, istemci):
        kod, js = _post(istemci, erosive_k=0.002, temp_coeff=0.004)
        assert js['unwired_inputs']['overridden_by_catalogue'] == [
            'erosive_k', 'temp_coeff']

    def test_bayrakli_deger_uygulanir(self, istemci):
        kod0, js0 = _post(istemci)
        kod, js = _post(istemci, erosive_k=0.002, erosive_k_override=True)
        assert js['unwired_inputs']['overridden_by_catalogue'] == []
        assert js['average_thrust'] != js0['average_thrust']

    def test_kullanilan_sigma_yayimlanir(self, istemci):
        kod, js = _post(istemci)
        sig = js['environmental_analysis']['temperature_effects'][
            'sigma_p_per_k']
        assert sig == pytest.approx(0.0042)

    def test_sayfa_kip_secicileri_ve_toplayici(self):
        for alan in ('erosive_k', 'temp_coeff'):
            assert 'id="%s_source"' % alan in SABLON
            assert "...solidCoeffFields('%s'," % alan in SABLON
            assert "document.getElementById('%s_source')" % alan in SABLON
        assert "out[id + '_override'] = true;" in SABLON

    def test_sigma_ipucu_ustel_yasa(self):
        for blok in ('en', 'tr'):
            pass
        satirlar = [s for s in SOZLUK.splitlines() if
                    "'solid.ui.temperature_sensitivity_coefficient_for_burn_rat'"
                    in s]
        assert len(satirlar) == 2
        for s in satirlar:
            assert 'exp(σp·(T0 − T_ref))' in s
            assert '(1+σ·ΔT)' not in s


# --------------------------------------------------------------------------
# KT-07 — BATES dışı alanlar
# --------------------------------------------------------------------------
class TestBatesDisi:
    @pytest.mark.parametrize('tip', ['star', 'finocyl', 'slotted',
                                     'wagon_wheel', 'end_burner'])
    def test_gonderilirse_tip_kosullu_beyan(self, istemci, tip):
        kod, js = _post(istemci, grain_type=tip, grain_count=3, grain_gap=2,
                        inhibit_front=False, inhibit_rear=False,
                        inhibit_outer=True)
        assert kod == 200, js
        na = js['unwired_inputs']['not_applicable_to_grain_type']
        assert {'grain_count', 'grain_gap', 'inhibit_front', 'inhibit_rear',
                'inhibit_outer'} <= set(na)

    def test_bates_te_beyan_yok(self, istemci):
        kod, js = _post(istemci, grain_count=3, grain_gap=2)
        assert js['unwired_inputs']['not_applicable_to_grain_type'] == []

    def test_sayfa_bates_disinda_gondermez_ve_devre_disi(self):
        assert "grain_count: isBatesSelected() ? solOptNum('grain_count') : undefined" in SABLON
        assert 'function syncBatesOnlyFields(grainType)' in SABLON
        assert 'id="bates_only_note"' in SABLON


# --------------------------------------------------------------------------
# KT-08 — wagon wheel parametreleri
# --------------------------------------------------------------------------
class TestWagonWheel:
    def test_varsayilan_beyanli_ve_eski_geometri(self, istemci):
        kod, js = _post(istemci, grain_type='wagon_wheel')
        ww = js['grain_design']['wagon_wheel']
        assert ww['hole_count'] == SOLID_WAGON_WHEEL_DEFAULTS['hole_count']
        assert ww['hole_diameter_mm'] == pytest.approx(48 / 2)
        assert ww['pitch_diameter_mm'] == pytest.approx(100 / 2)
        assert 'HRMA selection' in ww['basis']
        assert set(js['grain_design']['assumed_defaults']) == {
            'wagon_hole_count', 'wagon_hole_diameter', 'wagon_pitch_diameter'}

    def test_kullanici_parametreleri_hesaba_girer(self, istemci):
        kod0, js0 = _post(istemci, grain_type='wagon_wheel')
        kod, js = _post(istemci, grain_type='wagon_wheel', wagon_hole_count=4,
                        wagon_hole_diameter=20, wagon_pitch_diameter=56)
        assert kod == 200, js
        assert js['grain_design']['wagon_wheel']['hole_count'] == 4
        assert js['grain_design']['assumed_defaults'] == []
        assert js['average_thrust'] != js0['average_thrust']

    def test_kesisen_delik_422_en_buyuk_degerle(self, istemci):
        kod, js = _post(istemci, grain_type='wagon_wheel', wagon_hole_count=6,
                        wagon_hole_diameter=30, wagon_pitch_diameter=50)
        assert kod == 422
        alan = js['invalid_fields'][0]
        assert alan['field'] == 'wagon_hole_diameter'
        assert alan['reason'] == 'wagon_holes_intersect'
        assert alan['accepted_range'][1] == pytest.approx(25.0)

    def test_kesirli_delik_sayisi_422(self, istemci):
        kod, js = _post(istemci, grain_type='wagon_wheel',
                        wagon_hole_count=5.5)
        assert kod == 422
        assert js['invalid_fields'][0]['reason'] == 'not_a_whole_number'

    def test_sayfa_paneli_ve_ipuclari(self):
        for alan in ('wagon_hole_count', 'wagon_hole_diameter',
                     'wagon_pitch_diameter'):
            assert 'id="%s"' % alan in SABLON
            assert "%s: solOptNum('%s')" % (alan, alan) in SABLON
            assert SOZLUK.count("'solid.ui.%s_tip'" % alan) == 2


# --------------------------------------------------------------------------
# KT-09 — finocyl kanatlı boy oranı + varsayım satırı
# --------------------------------------------------------------------------
class TestFinocyl:
    def test_varsayilan_beyanli(self, istemci):
        kod, js = _post(istemci, grain_type='finocyl')
        assert 'finned_length_fraction' in js['grain_design'][
            'assumed_defaults']
        assert js['grain_design']['finned_length_fraction'] == \
            pytest.approx(0.4)

    def test_kullanici_degeri_girer(self, istemci):
        kod0, js0 = _post(istemci, grain_type='finocyl')
        kod, js = _post(istemci, grain_type='finocyl',
                        finned_length_fraction=0.7)
        assert 'finned_length_fraction' not in js['grain_design'][
            'assumed_defaults']
        assert js['average_thrust'] != js0['average_thrust']

    def test_sayfa_alani_ve_varsayim_satiri(self):
        assert 'id="finned_length_fraction"' in SABLON
        assert 'function renderSolidAssumedLine(results)' in SABLON
        assert 'renderSolidAssumedLine(results);' in SABLON
        assert SOZLUK.count("'solid.msg.solver_assumed_inputs'") == 2


# --------------------------------------------------------------------------
# K-A DEVİR 8/9 — sessiz kırpma ve tam sayı kapısı
# --------------------------------------------------------------------------
class TestKirpmaVeTamSayi:
    @pytest.mark.parametrize('ek,alan,neden', [
        ({'grain_type': 'star', 'star_radius': 40}, 'star_radius',
         'exceeds_geometric_limit'),
        ({'grain_type': 'star', 'star_points': 6.5}, 'star_points',
         'not_a_whole_number'),
        ({'grain_type': 'slotted', 'slot_count': 4.5}, 'slot_count',
         'not_a_whole_number'),
        ({'grain_type': 'slotted', 'slot_depth': 25}, 'slot_depth',
         'exceeds_geometric_limit'),
        ({'grain_type': 'finocyl', 'fin_count': 3.2}, 'fin_count',
         'not_a_whole_number'),
        ({'grain_type': 'finocyl', 'fin_length': 40}, 'fin_length',
         'exceeds_geometric_limit'),
    ])
    def test_ret_422_adli(self, istemci, ek, alan, neden):
        kod, js = _post(istemci, **ek)
        assert kod == 422, js
        kayit = [f for f in js['invalid_fields'] if f['field'] == alan]
        assert kayit and kayit[0]['reason'] == neden
        if neden == 'exceeds_geometric_limit':
            assert kayit[0]['accepted_range'][1] > 0

    def test_sinir_icindeki_deger_kabul(self, istemci):
        kod, js = _post(istemci, grain_type='slotted', slot_depth=20)
        assert kod == 200
        assert js['grain_design']['clipped_inputs'] == []

    def test_sayfa_toplayicisinda_gizli_sayi_yok(self):
        govde = SABLON[SABLON.index('function collectAllParameters() {'):]
        govde = govde[:govde.index('// V301/K-A — hesap ucunun ret')]
        assert not re.search(
            r"parseFloat\([^;]*?\.value\)\s*\|\|\s*[0-9]", govde)


# --------------------------------------------------------------------------
# NK-28 — eğri sonu
# --------------------------------------------------------------------------
class TestEgriSonu:
    def test_tukenis_inisi_beyanli(self, istemci):
        kod, js = _post(istemci)
        tc = js['thrust_curve']
        son = tc['burnout_end']
        assert son['thrust_n'] == 0.0 and son['pressure_bar'] == 0.0
        assert son['time_s'] == pytest.approx(tc['time'][-1])
        assert son['time_s'] == pytest.approx(
            js['solver_diagnostics']['burnout_time_s'])

    def test_rejim_siniri_tutulan_aralik_kndx(self, istemci):
        kod, js = _post(istemci, propellant_type='kndx',
                        outer_diameter=75, core_diameter=32,
                        grain_length=360, burn_rate_preset='kndx',
                        burn_rate_a=0.0007876, burn_rate_n=0.688)
        pencere = js['thrust_curve']['regime_boundary_hold']
        tutulan = js['solver_diagnostics'][
            'pressure_solver_boundary_held_steps']
        assert sum(w['held_steps'] for w in pencere) == tutulan
        for w in pencere:
            assert w['t_end_s'] > w['t_start_s']

    def test_sayfa_inisi_ve_golgeyi_cizer(self):
        assert "solidCurveWithBurnout(results.thrust_curve, 'thrust')" in \
            SABLON
        assert 'solidAddHoldWindows(thrustLayout, results.thrust_curve);' in \
            SABLON
        assert 'font: { size: 12' in SABLON


# --------------------------------------------------------------------------
# NK-30 — kütle dökümünde astar
# --------------------------------------------------------------------------
class TestKutleDokumu:
    def test_astar_satiri_ve_motor_kuru_kutlesi(self, istemci):
        kod, js = _post(istemci)
        dok = js['design_summary']['masses']['inert_breakdown']
        parcalar = ('case_kg', 'nozzle_kg', 'insulation_kg', 'liner_kg',
                    'closure_kg', 'igniter_misc_kg')
        assert sum(dok[p] for p in parcalar) == pytest.approx(
            js['design_summary']['masses']['dry_mass_kg'], rel=1e-12)
        assert "parts: ['liner_kg']" in SABLON
        assert 'id="liner_mass"' in SABLON

    def test_toplam_kuru_kutle_aviyonigi_katmaz(self):
        govde = SABLON[SABLON.index('function updateTotalMasses() {'):]
        govde = govde[:govde.index('\n        }\n')]
        assert ('const dryMass = caseMass + nozzleMass + insulationMass + '
                'linerMass + closureMass;') in govde
        assert 'avionicsMass' not in govde


# --------------------------------------------------------------------------
# Yeni uyarı kodlarının EN + TR metni
# --------------------------------------------------------------------------
@pytest.mark.parametrize('kod', ['warn.solid.case_thermal_not_evaluated',
                                 'warn.solid.case_yield_differs_from_material'])
def test_yeni_uyari_kodlari_iki_dilde(kod):
    assert ORTAK.count("'%s'" % kod) == 2


def test_motor_dogrudan_kullanimda_fenolik_karar_uydurmaz():
    """Savunma hattı: doğrudan motor kullanımında kayıtsız ad 'not_analyzed'."""
    eng = SolidRocketEngine(chamber_diameter=100, grain_length=500,
                            core_diameter=48, chamber_pressure=40,
                            propellant_type='apcp',
                            overrides={'nozzle_material': 'phenolic'})
    assert eng.analyze_nozzle_material()['status'] == 'not_analyzed'
