"""
Merkezi malzeme veritabanı birim testleri (Dalga 0, 2026-07-14).

Doğrulananlar:
  1. Tüm kayıtlarda zorunlu mekanik + termal alanlar ve kaynak (source) var.
  2. Değerler fiziksel olarak anlamlı (pozitif, sıralı: yield < ultimate,
     allowable <= melting, derating eğrisi (0,1] bandında ve azalan).
  3. Eski modül tablolarındaki değerler bire bir taşındı (steel_4130
     mekanik = structural tablo; steel/copper termal = heat tablo).
  4. Alias çözümü (aluminum -> aluminum_6061 vb.) ve kopya güvenliği.
  5. Analizörler (StructuralAnalyzer / HeatTransferAnalyzer / SafetyAnalyzer)
     aynı merkezi kayıtları okuyor — üç modül tek doğruluk kaynağında.
"""

import pytest

from hrma.data.materials_db import (
    MATERIALS, ALIASES, REQUIRED_FIELDS, VALID_TAGS,
    get_material, get_material_safe, list_materials, build_materials_view
)

# Görev tanımındaki zorunlu malzeme seti
REQUIRED_MATERIALS = [
    'steel_4130', 'aluminum_6061', 'inconel_718', 'titanium_6al4v',
    'copper', 'cucrzr', 'ss_304', 'ss_316', 'graphite', 'ablative',
]

# v2.5.2 genişletmesiyle eklenen kayıtlar
NEW_MATERIALS_V252 = [
    'al_7075_t6', 'al_2024_t3', 'ss_17_4ph', 'steel_4340', 'inconel_625',
    'ti_grade2_cp', 'molybdenum_tzm', 'tungsten',
    'beryllium_copper_c17200', 'brass_c360', 'magnesium_az31b',
    'niobium_c103', 'carbon_carbon',
]

MECHANICAL_FIELDS = [
    'yield_strength', 'ultimate_strength', 'elastic_modulus', 'density',
    'poisson_ratio', 'fatigue_limit', 'safety_factor', 'thermal_expansion',
    'max_service_temp', 'derating_curve',
]

THERMAL_FIELDS = [
    'thermal_conductivity', 'specific_heat', 'melting_point', 'emissivity',
    'allowable_temperature', 'max_service_temperature',
]


class TestCatalog:
    def test_required_materials_present(self):
        names = list_materials()
        for name in REQUIRED_MATERIALS:
            assert name in names, f"missing required material: {name}"
        # Jenerik çelik de kalmalı (uygulama varsayılanı material='steel')
        assert 'steel' in names

    def test_all_records_have_mandatory_fields_and_source(self):
        for name in list_materials():
            rec = get_material(name)
            for field in MECHANICAL_FIELDS + THERMAL_FIELDS + ['name', 'source']:
                assert field in rec, f"{name} missing field {field}"
            assert isinstance(rec['source'], str) and len(rec['source']) > 20, (
                f"{name} source atfı boş/yetersiz")

    def test_values_physically_sensible(self):
        for name in list_materials():
            rec = get_material(name)
            # Pozitiflik
            for field in ('yield_strength', 'ultimate_strength',
                          'elastic_modulus', 'density', 'fatigue_limit',
                          'thermal_expansion', 'thermal_conductivity',
                          'specific_heat', 'melting_point'):
                assert rec[field] > 0, f"{name}.{field} must be positive"
            # Sıralamalar
            assert rec['yield_strength'] <= rec['ultimate_strength'], name
            assert 0.0 < rec['poisson_ratio'] < 0.5, name
            assert 0.0 < rec['emissivity'] <= 1.0, name
            assert rec['allowable_temperature'] <= rec['melting_point'], name
            assert rec['safety_factor'] >= 1.0, name

    def test_derating_curves_valid(self):
        for name in list_materials():
            curve = get_material(name)['derating_curve']
            assert len(curve) >= 2, f"{name} derating curve too short"
            temps = sorted(curve.keys())
            factors = [curve[t] for t in temps]
            assert all(0.0 < f <= 1.0 for f in factors), name
            # Azalan (grafit gibi düz olanlara eşitlik serbest)
            assert all(factors[i] >= factors[i + 1]
                       for i in range(len(factors) - 1)), (
                f"{name} derating curve must be non-increasing")
            # Oda sıcaklığı noktası tam dayanım
            assert curve[temps[0]] == pytest.approx(1.0)


class TestSchemaV252:
    """REQUIRED_FIELDS + tags + yeni kayıtlar (v2.5.2 genişletmesi)."""

    def test_required_fields_constant_matches_schema(self):
        # Docstring'deki 18 alanın tamamı sabitte
        assert len(REQUIRED_FIELDS) == 18
        for f in ('name', 'source', 'derating_curve',
                  'thermal_conductivity', 'max_service_temperature'):
            assert f in REQUIRED_FIELDS

    def test_all_records_carry_required_fields(self):
        for name, rec in MATERIALS.items():
            missing = [f for f in REQUIRED_FIELDS if f not in rec]
            assert not missing, f"{name} missing {missing}"

    def test_all_records_have_valid_tags(self):
        for name, rec in MATERIALS.items():
            tags = rec.get('tags')
            assert isinstance(tags, list) and tags, f"{name} tags eksik"
            bad = [t for t in tags if t not in VALID_TAGS]
            assert not bad, f"{name} geçersiz etiket(ler): {bad}"

    def test_new_materials_present(self):
        names = list_materials()
        for name in NEW_MATERIALS_V252:
            assert name in names, f"missing new material: {name}"

    def test_new_materials_physically_sensible(self):
        # Genel fiziksel bant kontrolleri tüm kayıtlar için
        # TestCatalog.test_values_physically_sensible'da; burada yeni
        # kayıtlar için açık (görev sözleşmesindeki) bantlar doğrulanır.
        for name in NEW_MATERIALS_V252:
            rec = get_material(name)
            assert rec['yield_strength'] < rec['ultimate_strength'] \
                or rec['yield_strength'] == rec['ultimate_strength'], name
            assert rec['density'] > 0, name
            assert 0.0 < rec['poisson_ratio'] < 0.5, name
            assert len(rec['derating_curve']) >= 2, name

    def test_new_materials_derating_at_least_three_points(self):
        # Görev: her yeni malzemede en az 3 noktalı gerçekçi eğri.
        # (carbon_carbon grafit gibi sabit-dayanımlıdır — 2 nokta, düz 1.0;
        # graphite emsaliyle tutarlı bilinçli istisna.)
        flat_ok = {'carbon_carbon'}
        for name in NEW_MATERIALS_V252:
            curve = get_material(name)['derating_curve']
            if name in flat_ok:
                assert all(v == pytest.approx(1.0) for v in curve.values())
                continue
            assert len(curve) >= 3, f"{name} derating curve too short"

    def test_silica_phenolic_resolves_to_ablative_record(self):
        # silica_phenolic ayrı kayıt DEĞİL, 'ablative' kaydının alias'ı —
        # thermal_protection.py yoğunluğu da aynı kayıttan okur (tek
        # doğruluk kaynağı, değer sapması imkânsız).
        rec, key = get_material_safe('silica_phenolic')
        assert key == 'ablative'
        assert rec == get_material('ablative')

    def test_radiation_extension_records_match_thermal_protection(self):
        # C-103 / C-C limitleri thermal_protection.py tablosuyla birebir
        from hrma.analysis.thermal_protection import (
            RADIATION_EXTENSION_MATERIALS)
        for key in ('niobium_c103', 'carbon_carbon'):
            rec = get_material(key)
            tp = RADIATION_EXTENSION_MATERIALS[key]
            assert rec['allowable_temperature'] == pytest.approx(
                tp['service_limit_K']), key
            assert rec['emissivity'] == pytest.approx(tp['emissivity']), key

    def test_optional_temperature_curves(self):
        # k_curve/cp_curve en az inconel_625 + cucrzr + tungsten'de dolu
        for key in ('inconel_625', 'cucrzr', 'tungsten'):
            rec = get_material(key)
            for curve_name in ('k_curve', 'cp_curve'):
                curve = rec.get(curve_name)
                assert isinstance(curve, dict) and len(curve) >= 3, (
                    f"{key}.{curve_name} eksik/kısa")
                for T, v in curve.items():
                    assert T > 0 and v > 0, f"{key}.{curve_name}[{T}]"
            # k_curve oda sıcaklığı değeri sabit alanla tutarlı (±%5)
            T0 = min(rec['k_curve'])
            assert rec['k_curve'][T0] == pytest.approx(
                rec['thermal_conductivity'], rel=0.05), key

    def test_get_material_safe_alias_and_error(self):
        rec, key = get_material_safe('17-4PH')
        assert key == 'ss_17_4ph'
        assert rec['yield_strength'] == pytest.approx(1170e6)
        rec, key = get_material_safe('tzm')
        assert key == 'molybdenum_tzm'
        with pytest.raises(KeyError) as ei:
            get_material_safe('unobtainium')
        assert 'unobtainium' in str(ei.value)
        assert 'aliases' in str(ei.value)

    def test_consumer_tag_coverage(self):
        """Panel filtreleri boş liste görmemeli: her tüketici etiketi
        en az bir kayıtta bulunmalı."""
        for tag in VALID_TAGS:
            hits = [n for n, r in MATERIALS.items() if tag in r['tags']]
            assert hits, f"no material carries tag '{tag}'"


class TestCadVisualizationParity:
    """cad_visualization yerel tablosu merkezle çelişmemeli (v2.5.2)."""

    def test_cad_material_table_matches_central_db(self):
        pytest.importorskip('trimesh')
        pytest.importorskip('plotly')
        from hrma.export.cad_visualization import MotorCADDesigner
        d = MotorCADDesigner()
        expected = {
            ('chamber', 'steel_304'): 'ss_304',
            ('chamber', 'aluminum_6061'): 'aluminum_6061',
            ('chamber', 'inconel_718'): 'inconel_718',
            ('nozzle', 'graphite'): 'graphite',
            ('nozzle', 'tungsten'): 'tungsten',
            ('nozzle', 'copper'): 'copper',
            ('injector', 'stainless_steel'): 'ss_316',
            ('injector', 'titanium'): 'titanium_6al4v',
        }
        for (group, local_key), db_key in expected.items():
            entry = d.materials_db[group][local_key]
            rec = get_material(db_key)
            for field, value in entry.items():
                if field == 'color':
                    continue
                assert value == rec[field], (
                    f"cad {group}/{local_key}.{field} = {value} "
                    f"!= central {db_key}.{field} = {rec[field]}")

    def test_prior_conflicts_are_gone(self):
        # 2026-07 keşfi: inconel yield 1034 vs 1100 MPa, grafit yoğunluk
        # 2200 vs 1800 — yerel tablo artık merkezden okur.
        pytest.importorskip('trimesh')
        pytest.importorskip('plotly')
        from hrma.export.cad_visualization import MotorCADDesigner
        d = MotorCADDesigner()
        assert d.materials_db['chamber']['inconel_718']['yield_strength'] \
            == pytest.approx(1100e6)
        assert d.materials_db['nozzle']['graphite']['density'] \
            == pytest.approx(1800)


class TestLegacyValueParity:
    """Değerler mevcut modül tablolarından bire bir taşındı mı?"""

    def test_steel_4130_mechanical_matches_prior_structural_table(self):
        m = get_material('steel_4130')
        assert m['yield_strength'] == pytest.approx(460e6)
        assert m['ultimate_strength'] == pytest.approx(730e6)
        assert m['elastic_modulus'] == pytest.approx(200e9)
        assert m['poisson_ratio'] == pytest.approx(0.27)
        assert m['fatigue_limit'] == pytest.approx(230e6)
        assert m['thermal_expansion'] == pytest.approx(12.3e-6)
        assert m['max_service_temp'] == pytest.approx(811.0)
        assert m['derating_curve'][500] == pytest.approx(0.44)

    def test_steel_4130_thermal_matches_prior_heat_table(self):
        m = get_material('steel_4130')
        assert m['thermal_conductivity'] == pytest.approx(42.7)
        assert m['specific_heat'] == pytest.approx(477)
        assert m['melting_point'] == pytest.approx(1705)
        assert m['allowable_temperature'] == pytest.approx(1000)
        assert m['max_service_temperature'] == pytest.approx(2000)

    def test_generic_steel_and_copper_thermal_preserved(self):
        s = get_material('steel')
        assert s['thermal_conductivity'] == pytest.approx(50.0)
        assert s['allowable_temperature'] == pytest.approx(1073)
        c = get_material('copper')
        assert c['thermal_conductivity'] == pytest.approx(401.0)
        assert c['melting_point'] == pytest.approx(1358)
        assert c['emissivity'] == pytest.approx(0.75)

    def test_generic_steel_matches_prior_safety_constants(self):
        # safety_analysis eski sabitleri 250/400 MPa idi — jenerik çelik
        # kaydı aynı değerleri (A36 minimumları) taşır.
        s = get_material('steel')
        assert s['yield_strength'] == pytest.approx(250e6)
        assert s['ultimate_strength'] == pytest.approx(400e6)


class TestApi:
    def test_aliases_resolve_to_canonical(self):
        assert get_material('aluminum') == get_material('aluminum_6061')
        assert get_material('inconel') == get_material('inconel_718')
        assert get_material('titanium') == get_material('titanium_6al4v')

    def test_unknown_material_raises_keyerror(self):
        with pytest.raises(KeyError):
            get_material('unobtainium')

    def test_get_material_returns_independent_copy(self):
        a = get_material('steel_4130')
        a['yield_strength'] = 1.0
        a['derating_curve'][20] = 0.0
        b = get_material('steel_4130')
        assert b['yield_strength'] == pytest.approx(460e6)
        assert b['derating_curve'][20] == pytest.approx(1.0)
        assert MATERIALS['steel_4130']['yield_strength'] == pytest.approx(460e6)

    def test_build_materials_view_contains_aliases_as_same_object(self):
        view = build_materials_view()
        for alias, target in ALIASES.items():
            assert view[alias] is view[target], (
                f"alias {alias} must reference the same record object "
                f"(identity-based reverse lookup relies on this)")

    def test_list_materials_returns_canonical_only(self):
        names = list_materials()
        for alias in ALIASES:
            assert alias not in names


class TestAnalyzerIntegration:
    """Üç analiz modülü de merkezi DB'den okuyor mu?"""

    def test_structural_analyzer_uses_central_db(self):
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        s = StructuralAnalyzer()
        for name in ('steel_4130', 'aluminum_6061', 'inconel_718',
                     'titanium_6al4v', 'ss_304', 'ss_316', 'cucrzr'):
            assert name in s.materials
            assert (s.materials[name]['yield_strength']
                    == get_material(name)['yield_strength'])

    def test_heat_analyzer_uses_central_db(self):
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        h = HeatTransferAnalyzer()
        for name in ('steel', 'steel_4130', 'copper', 'ablative', 'graphite',
                     'titanium_6al4v', 'ss_304'):
            assert name in h.materials
            assert (h.materials[name]['thermal_conductivity']
                    == get_material(name)['thermal_conductivity'])

    def test_safety_analyzer_uses_central_db(self):
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        sa = SafetyAnalyzer()
        motor = {'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
                 'wall_thickness': 0.005}
        r_4130 = sa._analyze_structural_safety(motor, 'steel_4130')
        r_alu = sa._analyze_structural_safety(motor, 'aluminum_6061')
        assert r_4130['yield_strength_mpa'] == pytest.approx(460.0)
        assert r_alu['yield_strength_mpa'] == pytest.approx(275.0)
        # SF malzemeyle orantılı değişmeli (aynı gerilme, farklı dayanım)
        assert (r_4130['yield_safety_factor']
                > r_alu['yield_safety_factor'])

    def test_safety_analyzer_unknown_material_falls_back_to_4130(self):
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        sa = SafetyAnalyzer()
        motor = {'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
                 'wall_thickness': 0.005}
        r = sa._analyze_structural_safety(motor, 'not_a_material')
        assert r['material'] == 'steel_4130'
        assert r['yield_strength_mpa'] == pytest.approx(460.0)

    def test_same_material_same_numbers_across_modules(self):
        """Dürüstlük çekirdeği: structural ve safety aynı motor + aynı
        malzeme için AYNI akma dayanımını kullanmalı (eski 460 vs 250 MPa
        tutarsızlığı kapandı)."""
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        s = StructuralAnalyzer()
        sa = SafetyAnalyzer()
        yield_struct = s.materials['steel_4130']['yield_strength']
        r = sa._analyze_structural_safety(
            {'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
             'wall_thickness': 0.005}, 'steel_4130')
        assert r['yield_strength_mpa'] == pytest.approx(yield_struct / 1e6)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
