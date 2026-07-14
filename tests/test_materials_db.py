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
    MATERIALS, ALIASES, get_material, list_materials, build_materials_view
)

# Görev tanımındaki zorunlu malzeme seti
REQUIRED_MATERIALS = [
    'steel_4130', 'aluminum_6061', 'inconel_718', 'titanium_6al4v',
    'copper', 'cucrzr', 'ss_304', 'ss_316', 'graphite', 'ablative',
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
