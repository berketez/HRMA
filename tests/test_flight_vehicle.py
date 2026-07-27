"""
hrma/analysis/flight_vehicle.py + hrma/utils/projects.py airframe testleri.

Kapsam:
  1. normalize() — üç motor tipi (hybrid/solid/liquid) için sentetik sonuç
     sözlüğü -> tek uçan-araç şeması. BİRİM doğruluğu (hybrid OD metre / solid+
     liquid OD milimetre-> metre), thrust_curve kaynağı, ad çözümü.
  2. ÇİFT-SAYIM (spec TUZAK2): engine_inert_mass HER tipte propelanı DIŞLAR.
  3. recompute_from_project() — .hrma girdilerinden gerçek motoru yeniden
     hesaplama (katı motor, çevrimdışı/hızlı) + dispatch redleri.
  4. projects.py airframe gidiş-dönüşü (kaydet -> yükle -> byte-eşit) ve şema
     redleri (iç içe nesne / None reddi).

Sentetik sözlüklerdeki alan adları/birimleri motor sonuç dict'lerinden
(hrma/engines/*_rocket_engine.py) DOĞRUDAN türetilmiştir; kod değişirse bu
testler kırılmalıdır.
"""

import pytest

from hrma.analysis import flight_vehicle as fv
from hrma.utils import projects as store


# ---------------------------------------------------------------------------
# Sentetik motor sonuç sözlükleri (gerçek şemaların minimal karşılıkları)
# ---------------------------------------------------------------------------

def hybrid_results(**over):
    """/calculate hibrit yanıtı: motor alt-sözlüğü sarmalı.

    Gerçek anahtarlar: motor.thrust (:997), motor.burn_time (:1041),
    motor.propellant_mass_total (:1032), motor.chamber_diameter (:1013, METRE),
    motor.design_summary.key_dimensions.{dry_mass_estimate_kg (:1242, =0.25*prop),
    total_motor_length_mm (:1240)}, motor.transient {time, thrust}.
    """
    motor = {
        'thrust': 5000.0,
        'burn_time': 8.0,
        'propellant_mass_total': 12.0,
        'chamber_diameter': 0.15,  # METRE (self.D_ch)
        'transient': {
            'time': [0.0, 1.0, 2.0, 3.0, 4.0],
            'thrust': [100.0, 200.0, 300.0, 200.0, 100.0],
        },
        'design_summary': {
            'key_dimensions': {
                'dry_mass_estimate_kg': 3.0,       # = 0.25 * 12.0
                'total_motor_length_mm': 1200.0,   # mm
            },
        },
    }
    motor.update(over.pop('motor', {}))
    doc = {'motor': motor}
    doc.update(over)
    return doc


def solid_results(**over):
    """/calculate_solid yanıtı: düz (top-level) sözlük.

    Gerçek anahtarlar: average_thrust (:4357), burn_time (:4356),
    propellant_mass (:4363), thrust_curve {time, thrust, ...} (:4381),
    design_summary.masses.dry_mass_kg (:4322), design_summary.key_dimensions.
    total_length_mm (:4306), cad_design.case_design.outer_diameter (:2483, MM).
    """
    r = {
        'average_thrust': 6800.0,
        'burn_time': 2.2,
        'propellant_mass': 6.5,
        'chamber_diameter': 100.0,  # MM
        'thrust_curve': {
            'time': [0.0, 0.5, 1.0, 1.5, 2.0],
            'thrust': [7000.0, 6900.0, 6800.0, 6700.0, 500.0],
            'pressure': [40.0, 39.0, 38.0, 37.0, 5.0],
        },
        'cad_design': {'case_design': {'outer_diameter': 116.0}},  # MM
        'design_summary': {
            'masses': {'dry_mass_kg': 5.5, 'propellant_mass_kg': 6.5},
            'key_dimensions': {'total_length_mm': 773.0},           # mm
        },
    }
    r.update(over)
    return r


def liquid_results(**over):
    """/calculate_liquid yanıtı: düz (top-level) sözlük.

    Gerçek anahtarlar: thrust (:3625), burn_time (:3702), chamber_diameter
    (:3658, MM), total_mass_flow (:3648), design_summary.masses.
    {propellant_mass_kg (:3770), engine_mass_kg (:3766)}, design_summary.
    key_dimensions.overall_length_mm (:3763), feed_system.total_mass (:1225).
    """
    r = {
        'thrust': 10000.0,
        'burn_time': 300.0,
        'chamber_diameter': 99.2,   # MM
        'total_mass_flow': 3.4,
        'engine_mass_estimate': 43.5,
        'feed_system': {'total_mass': 18.0},  # ALT KÜME (feed+turbopump)
        'design_summary': {
            'masses': {
                'propellant_mass_kg': 1025.0,
                'engine_mass_kg': 43.5,        # TAM motor kuru kütlesi
            },
            'key_dimensions': {'overall_length_mm': 209.0},  # mm
        },
    }
    r.update(over)
    return r


# ---------------------------------------------------------------------------
# 1. normalize — hibrit
# ---------------------------------------------------------------------------

class TestNormalizeHybrid:
    def test_schema_and_values(self):
        v = fv.normalize('hybrid', hybrid_results(), motor_name='H1')
        assert v['motor_type'] == 'hybrid'
        assert v['motor_name'] == 'H1'
        assert v['source'] == 'results'
        assert v['thrust'] == 5000.0
        assert v['burn_time'] == 8.0
        assert v['propellant_mass'] == 12.0
        assert v['engine_inert_mass'] == 3.0

    def test_od_stays_in_meters_no_division(self):
        # Hibrit chamber_diameter ZATEN metre; ortak /1000 uygulanmamalı.
        v = fv.normalize('hybrid', hybrid_results())
        assert v['engine_od_m'] == 0.15

    def test_length_mm_to_m(self):
        v = fv.normalize('hybrid', hybrid_results())
        assert v['engine_length_m'] == pytest.approx(1.2)

    def test_inert_flagged_estimate(self):
        v = fv.normalize('hybrid', hybrid_results())
        assert v['engine_inert_mass_is_estimate'] is True
        assert v['engine_inert_mass_note']

    def test_thrust_curve_from_transient(self):
        v = fv.normalize('hybrid', hybrid_results())
        assert v['thrust_curve'] is not None
        assert v['thrust_curve']['time'] == [0.0, 1.0, 2.0, 3.0, 4.0]
        assert v['thrust_curve']['thrust'][2] == 300.0

    def test_no_transient_yields_null_curve(self):
        doc = hybrid_results()
        doc['motor'].pop('transient')
        v = fv.normalize('hybrid', doc)
        assert v['thrust_curve'] is None

    def test_unwrapped_motor_dict_also_accepted(self):
        # recompute doğrudan derlenmiş motor dict'i döndürür (motor sarmalı yok).
        eng = hybrid_results()['motor']
        v = fv.normalize('hybrid', eng)
        assert v['thrust'] == 5000.0
        assert v['engine_od_m'] == 0.15


# ---------------------------------------------------------------------------
# 2. normalize — katı
# ---------------------------------------------------------------------------

class TestNormalizeSolid:
    def test_schema_and_values(self):
        v = fv.normalize('solid', solid_results(), motor_name='S1')
        assert v['motor_type'] == 'solid'
        assert v['thrust'] == 6800.0       # average_thrust
        assert v['burn_time'] == 2.2
        assert v['propellant_mass'] == 6.5
        assert v['engine_inert_mass'] == 5.5   # dry_mass_kg (propelan HARİÇ)

    def test_od_prefers_case_outer_diameter_mm_to_m(self):
        v = fv.normalize('solid', solid_results())
        assert v['engine_od_m'] == pytest.approx(0.116)  # 116 mm -> m

    def test_od_falls_back_to_chamber_diameter(self):
        r = solid_results()
        r.pop('cad_design')
        v = fv.normalize('solid', r)
        assert v['engine_od_m'] == pytest.approx(0.100)  # 100 mm -> m

    def test_length_mm_to_m(self):
        v = fv.normalize('solid', solid_results())
        assert v['engine_length_m'] == pytest.approx(0.773)

    def test_thrust_curve_extracts_time_thrust_only(self):
        v = fv.normalize('solid', solid_results())
        assert v['thrust_curve'] is not None
        assert set(v['thrust_curve'].keys()) == {'time', 'thrust'}
        assert len(v['thrust_curve']['time']) == 5

    def test_inert_not_estimate(self):
        v = fv.normalize('solid', solid_results())
        assert v['engine_inert_mass_is_estimate'] is False


# ---------------------------------------------------------------------------
# 3. normalize — sıvı
# ---------------------------------------------------------------------------

class TestNormalizeLiquid:
    def test_schema_and_values(self):
        v = fv.normalize('liquid', liquid_results(), motor_name='L1')
        assert v['motor_type'] == 'liquid'
        assert v['thrust'] == 10000.0
        assert v['burn_time'] == 300.0
        assert v['propellant_mass'] == 1025.0

    def test_thrust_curve_is_null(self):
        v = fv.normalize('liquid', liquid_results())
        assert v['thrust_curve'] is None

    def test_od_mm_to_m(self):
        v = fv.normalize('liquid', liquid_results())
        assert v['engine_od_m'] == pytest.approx(0.0992)

    def test_length_mm_to_m(self):
        v = fv.normalize('liquid', liquid_results())
        assert v['engine_length_m'] == pytest.approx(0.209)

    def test_inert_uses_full_engine_dry_mass_not_feed_subset(self):
        # engine_mass_kg (tam kuru kütle) tercih; feed_system.total_mass (18)
        # yalnız alt küme -> KULLANILMAMALI.
        v = fv.normalize('liquid', liquid_results())
        assert v['engine_inert_mass'] == 43.5
        assert v['engine_inert_mass'] != 18.0

    def test_inert_falls_back_to_feed_system_when_no_engine_mass(self):
        r = liquid_results()
        r['design_summary']['masses'].pop('engine_mass_kg')
        r.pop('engine_mass_estimate')
        v = fv.normalize('liquid', r)
        assert v['engine_inert_mass'] == 18.0  # son çare: feed_system.total_mass

    def test_propellant_falls_back_to_mdot_times_burn(self):
        r = liquid_results()
        r['design_summary']['masses'].pop('propellant_mass_kg')
        v = fv.normalize('liquid', r)
        assert v['propellant_mass'] == pytest.approx(3.4 * 300.0)


# ---------------------------------------------------------------------------
# 4. ÇİFT-SAYIM — engine_inert propelanı İÇERMEZ (spec TUZAK2)
# ---------------------------------------------------------------------------

class TestNoDoubleCounting:
    """engine_inert_mass + propellant_mass = ıslak; inert TEK BAŞINA kuru olmalı.

    Çözücü toplam kuru kütleyi airframe_dry + engine_inert alır, propelanı
    AYRI ekler. engine_inert propelanı çoktan içeriyorsa propelan iki kez
    sayılır. Testler: normalize'ın inert alanı SADECE kuru kütle alanına eşit,
    propelanı toplamıyor.
    """

    def test_solid_inert_equals_pure_dry_not_wet(self):
        r = solid_results()
        r['design_summary']['masses']['dry_mass_kg'] = 5.0
        r['propellant_mass'] = 20.0
        v = fv.normalize('solid', r)
        assert v['engine_inert_mass'] == 5.0            # saf kuru
        assert v['propellant_mass'] == 20.0
        # ıslak (25.0) DEĞİL; toplam kütle çözücüde ayrı hesaplanır.
        assert v['engine_inert_mass'] != 25.0
        assert v['engine_inert_mass'] < v['propellant_mass']

    def test_hybrid_inert_is_dry_estimate_excluding_propellant(self):
        r = hybrid_results()
        r['motor']['propellant_mass_total'] = 40.0
        r['motor']['design_summary']['key_dimensions']['dry_mass_estimate_kg'] = 10.0
        v = fv.normalize('hybrid', r)
        assert v['engine_inert_mass'] == 10.0
        assert v['propellant_mass'] == 40.0
        assert v['engine_inert_mass'] + v['propellant_mass'] == 50.0  # ıslak, ayrı

    def test_liquid_inert_excludes_propellant(self):
        v = fv.normalize('liquid', liquid_results())
        # engine dry (43.5) << propellant (1025) — inert asla propelanı içermez.
        assert v['engine_inert_mass'] == 43.5
        assert v['engine_inert_mass'] < v['propellant_mass']

    @pytest.mark.parametrize('mt, factory', [
        ('hybrid', hybrid_results),
        ('solid', solid_results),
        ('liquid', liquid_results),
    ])
    def test_inert_and_propellant_are_distinct_fields(self, mt, factory):
        v = fv.normalize(mt, factory())
        assert v['engine_inert_mass'] is not None
        assert v['propellant_mass'] is not None
        # İki ayrı, birbirine eşit olmayan alan (kuru != islak != propelan).
        assert v['engine_inert_mass'] != v['propellant_mass']


# ---------------------------------------------------------------------------
# 5. Şema / hata yolları / ad çözümü
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    'motor_type', 'motor_name', 'thrust_curve', 'thrust', 'burn_time',
    'propellant_mass', 'engine_inert_mass', 'engine_inert_mass_is_estimate',
    'engine_inert_mass_note', 'engine_od_m', 'engine_length_m', 'source',
}


class TestSchemaAndErrors:
    @pytest.mark.parametrize('mt, factory', [
        ('hybrid', hybrid_results),
        ('solid', solid_results),
        ('liquid', liquid_results),
    ])
    def test_all_required_keys_present(self, mt, factory):
        v = fv.normalize(mt, factory())
        assert REQUIRED_KEYS <= set(v.keys())

    def test_source_passthrough(self):
        v = fv.normalize('solid', solid_results(), source='project')
        assert v['source'] == 'project'

    def test_unknown_motor_type_raises(self):
        with pytest.raises(ValueError):
            fv.normalize('plasma', solid_results())

    def test_non_dict_results_raises(self):
        with pytest.raises(TypeError):
            fv.normalize('solid', [1, 2, 3])

    def test_name_resolution_priority(self):
        # açık ad > sonuç sözlüğü > varsayılan
        assert fv.normalize('solid', solid_results(), motor_name='X')['motor_name'] == 'X'
        r = solid_results(motor_name='FromResults')
        assert fv.normalize('solid', r)['motor_name'] == 'FromResults'
        assert fv.normalize('solid', solid_results())['motor_name'] == 'Solid Motor'

    def test_missing_fields_become_none_not_zero(self):
        # Uydurma-veri-yasağı: eksik alan None; sessizce 0 sayılmaz.
        v = fv.normalize('solid', {'average_thrust': 100.0})
        assert v['thrust'] == 100.0
        assert v['propellant_mass'] is None
        assert v['engine_inert_mass'] is None
        assert v['engine_length_m'] is None


# ---------------------------------------------------------------------------
# 6. recompute_from_project — gerçek katı motor (çevrimdışı, hızlı)
# ---------------------------------------------------------------------------

class TestRecomputeProjectSolid:
    def test_solid_recompute_end_to_end(self):
        doc = {
            'motor_type': 'solid',
            'inputs': {'fields': {
                'grain_type': 'bates', 'propellant_type': 'apcp',
                'chamber_diameter': 100, 'grain_length': 500,
                'core_diameter': 30, 'chamber_pressure': 40,
                'burn_rate_a': 0.005, 'burn_rate_n': 0.35,
            }},
        }
        motor_type, results = fv.recompute_from_project(doc)
        assert motor_type == 'solid'
        v = fv.normalize(motor_type, results, source='project')

        assert v['source'] == 'project'
        assert v['thrust'] and v['thrust'] > 1000.0
        assert v['burn_time'] and v['burn_time'] > 0.0
        assert v['propellant_mass'] and 1.0 < v['propellant_mass'] < 100.0
        assert v['engine_inert_mass'] and v['engine_inert_mass'] > 0.0
        # Dış çap kasa (100 mm hazne + cidar) -> ~0.10-0.15 m aralığı.
        assert 0.10 <= v['engine_od_m'] <= 0.20
        assert v['engine_length_m'] and v['engine_length_m'] > 0.3
        # Katı motorda gerçek itki eğrisi taşınır.
        assert v['thrust_curve'] is not None
        assert len(v['thrust_curve']['time']) > 3


class TestRecomputeDispatch:
    def test_unknown_motor_type_raises(self):
        with pytest.raises(ValueError):
            fv.recompute_from_project({'motor_type': 'plasma',
                                       'inputs': {'fields': {}}})

    def test_non_dict_doc_raises(self):
        with pytest.raises(TypeError):
            fv.recompute_from_project(['not', 'a', 'doc'])


# ---------------------------------------------------------------------------
# 7. projects.py — airframe gidiş-dönüşü + şema redleri
# ---------------------------------------------------------------------------

@pytest.fixture()
def proj_dir(tmp_path, monkeypatch):
    """İzole proje dizini (env override) — test_projects_store.py deseni."""
    d = tmp_path / 'projects'
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(d))
    return d


def airframe_payload(airframe, **over):
    """airframe içeren geçerli, sentetik proje yükü."""
    payload = {
        'format': 'hrma-project',
        'format_version': 1,
        'motor_type': 'hybrid',
        'inputs': {
            'fields': {'thrust': 1000.0, 'burn_time': 10.0},
            'airframe': airframe,
        },
        'results_summary': {'isp': 245.0},
    }
    payload.update(over)
    return payload


class TestAirframeProjectRoundTrip:
    def test_airframe_saved_and_loaded_byte_equal(self, proj_dir):
        airframe = {
            'body_diameter': 0.15,
            'body_length': 2.5,
            'nose_type': 'ogive',
            'nose_length': 0.40,
            'fin_count': 4,
            'fin_root': 0.20,
            'fin_tip': 0.10,
            'fin_span': 0.11,
            'fin_sweep': 0.08,
            'fin_position': 1.80,
            'airframe_dry_mass': 8.0,
            'cd0': 0.45,
            'launch_elevation': 84.0,
            'launch_azimuth': 90.0,
            'rail_length': 5.0,
            'latitude_deg': 39.0,
            'default_fins': True,
        }
        store.save_project('flying', airframe_payload(airframe))
        doc, _warnings = store.load_project('flying')
        assert doc['inputs']['airframe'] == airframe

    def test_airframe_optional_absent_still_valid(self, proj_dir):
        payload = {
            'format': 'hrma-project', 'format_version': 1,
            'motor_type': 'solid',
            'inputs': {'fields': {'chamber_diameter': 100.0}},
        }
        store.save_project('noair', payload)
        doc, _ = store.load_project('noair')
        assert 'airframe' not in doc['inputs']

    def test_airframe_rejects_nested_object(self, proj_dir):
        with pytest.raises(store.ProjectValidationError):
            store.validate_payload(airframe_payload({'fins': {'count': 4}}))

    def test_airframe_rejects_none_value(self, proj_dir):
        with pytest.raises(store.ProjectValidationError):
            store.validate_payload(airframe_payload({'body_diameter': None}))

    def test_airframe_rejects_non_finite(self, proj_dir):
        with pytest.raises(store.ProjectValidationError):
            store.validate_payload(airframe_payload({'cd0': float('inf')}))

    def test_airframe_must_be_object(self, proj_dir):
        payload = airframe_payload({})
        payload['inputs']['airframe'] = [1, 2, 3]
        with pytest.raises(store.ProjectValidationError):
            store.validate_payload(payload)

    def test_airframe_accepts_scalars_only(self, proj_dir):
        # str/num/bool serbest; overwrite gidiş-dönüşü de korunur.
        af = {'nose_type': 'vonKarman', 'fin_count': 3, 'default_fins': False,
              'cd0': 0.5}
        store.save_project('af2', airframe_payload(af))
        store.save_project('af2', airframe_payload({**af, 'cd0': 0.6}),
                            overwrite=True)
        doc, _ = store.load_project('af2')
        assert doc['inputs']['airframe']['cd0'] == 0.6
