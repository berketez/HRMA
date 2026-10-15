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
        # ÖH D22 / defter P9B4-09 (ÇEVRİLEN BEKÇİ): bu sayı 18'de
        # DONDURULMUŞTU ve şemanın büyümesini engelliyordu. Kalemin ölçülen
        # kusuru tam olarak buydu: 18 zorunlu alanın hiçbiri kriyojenik/DBTT
        # değildi, hüküm modül düzeyindeki bir kümede yaşıyordu ve katalogdaki
        # 17 kayıt beyansız olarak "soğukta sünek kalır" sayılıyordu.
        # Sayı 19'a çıkarıldı; alan adı ayrıca aranıyor ki bekçi yalnız
        # "sayı" değil "hangi alan" sorusunu da sorsun.
        assert len(REQUIRED_FIELDS) == 19
        for f in ('name', 'source', 'derating_curve',
                  'thermal_conductivity', 'max_service_temperature',
                  'cryogenic_ductility'):
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
            # ÖH D19 · P13B3-05 — ÖLÜ BANT ÜSTÜNDE GEVŞEK EŞİK ÇEVRİLDİ.
            # Eski hâli ``rel=0.05`` idi ("±%5"). Ölçüldü (D19, taban
            # 60cd341): k_curve'ü olan 3 malzemenin 3'ünde de iki alan
            # BİT-ÖZDEŞ (fark = 0, ayrışan 0). Yani ilan edilen %5'lik bant
            # bir kez bile sınanmadı — ama sınanmadığı hâlde YARIN iki
            # kopyanın %5'e kadar ayrışmasını sessizce kabul edecekti.
            # Burada karşılaştırılan şey bir hesap değil, AYNI KAYITTAKİ İKİ
            # KOPYA (``k_curve`` oda sıcaklığı girdisi ⟷ ``thermal_
            # conductivity`` skaleri). Kopyaların ayrışması bu kampanyanın
            # kovaladığı kusur sınıfının ta kendisidir; band değil KİMLİK
            # gerekir. Kayan nokta zinciri yok (iki sözlük okuması), bu
            # yüzden depo gürültü tabanı 1e-12 platformlar arası güvenlidir.
            T0 = min(rec['k_curve'])
            assert rec['k_curve'][T0] == pytest.approx(
                rec['thermal_conductivity'], rel=1e-12), (
                f'{key}: k_curve[{T0}] = {rec["k_curve"][T0]} ile '
                f'thermal_conductivity = {rec["thermal_conductivity"]} '
                'ayrıştı — aynı kaydın iki kopyası tek sayı olmalı')

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
    """CAD katmanının malzeme sayıları merkezle çelişmemeli (v2.5.2).

    ÖH D24 / P9B1-29 (BEKÇİ ÇEVRİLDİ). Bu sınıf eskiden
    ``MotorCADDesigner().materials_db`` sözlüğünü merkezle karşılaştırıyordu.
    ÖLÇÜLDÜ (taban 88a29d3, ``once.json`` M4, AST taraması): o sözlüğün ÜRÜN
    kodunda **0 okuyucusu** vardı — tek okuyanı bu testti. Yani her
    ``MotorCADDesigner()`` kurulumu, hiç okunmayan bir tablo için sekiz
    ``get_material`` çağrısı yapıyor ve test yalnız kendisinin ayakta
    tuttuğu bir yapıyı doğruluyordu (totolojik bekçi). Tablo ve onu kuran
    ``_cad_material`` yardımcısı silindi.

    Sınıfın GERÇEK iddiası korundu ve CANLI yola bağlandı: CAD katmanının
    kullanıcıya yayımladığı malzeme spesifikasyonu
    (``_generate_material_specifications``) merkezî ``materials_db``den
    okunur ve 2026-07 keşfindeki çelişkiler (Inconel 1034 vs 1100 MPa,
    grafit 2200 vs 1800 kg/m³) merkezde de geri gelmemelidir.
    """

    #: 2026-07 keşfinin çeliştiği kayıtlar. CAD katmanı bu anahtarları
    #: merkezden okur; sayılar merkezde değişirse burası kırmızıya döner.
    CELISKILI_KAYITLAR = {
        'ss_304': ('density', 'yield_strength'),
        'aluminum_6061': ('density', 'yield_strength'),
        'inconel_718': ('density', 'yield_strength'),
        'graphite': ('density', 'melting_point'),
        'tungsten': ('density', 'melting_point'),
        'copper': ('density', 'melting_point'),
        'ss_316': ('density', 'yield_strength'),
        'titanium_6al4v': ('density', 'yield_strength'),
    }

    def test_cad_katmani_merkezden_okuyor(self):
        """CAD'in yayımladığı kamara malzemesi merkezî kaydın SAYISIDIR."""
        pytest.importorskip('trimesh')
        pytest.importorskip('plotly')
        from hrma.export.cad_visualization import MotorCADDesigner
        rec = get_material('aluminum_6061')
        spec = MotorCADDesigner()._generate_material_specifications({
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'chamber_material': 'aluminum_6061',
        })
        blok = spec['chamber_material']
        ozellik = blok['properties']
        # Merkezî kaydın SAYILARI, CAD çıktısında birebir görünmeli.
        assert ozellik['yield_strength'] == \
            '%.0f MPa' % (rec['yield_strength'] / 1e6), ozellik
        assert ozellik['density'] == \
            '%.2f g/cm3' % (rec['density'] / 1000.0), ozellik
        assert ozellik['melting_point'] == \
            '%.0f K' % rec['melting_point'], ozellik
        # Künye de merkezden gelir (metin uydurulmaz).
        assert rec['source'][:30] in blok['source'], blok['source']

    def test_prior_conflicts_are_gone(self):
        """2026-07 çelişkileri merkezde de geri gelmedi."""
        assert get_material('inconel_718')['yield_strength'] \
            == pytest.approx(1100e6)
        assert get_material('graphite')['density'] == pytest.approx(1800)

    def test_cad_anahtarlarinin_HEPSI_merkezde_var(self):
        """Silinen tablonun anahtarları merkezde çözülebilir olmalı."""
        for db_key, alanlar in self.CELISKILI_KAYITLAR.items():
            rec = get_material(db_key)
            for alan in alanlar:
                assert rec.get(alan) is not None, (db_key, alan)

    def test_olu_tablo_geri_gelmedi(self):
        """``materials_db`` tablosu ve ``_cad_material`` geri gelmesin."""
        pytest.importorskip('trimesh')
        pytest.importorskip('plotly')
        from hrma.export import cad_visualization as cv
        assert not hasattr(cv.MotorCADDesigner(), 'materials_db')
        assert not hasattr(cv, '_cad_material')


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
        # ÖH D16 / P9B4-14 — BEKÇİ ÇEVRİLDİ (ÖK-05).
        # Bu satır eskiden 2000 K'yi kilitliyordu: yani kaydın KENDİ erime
        # noktasının (1705 K) 295 K ÜSTÜNDEKİ bir servis klampını "eski ısı
        # tablosuyla uyum" gerekçesiyle koruyordu. Eski tabloyla birebirlik
        # FİZİKSEL DEĞİŞMEZİN üstünde tutulamaz: /calculate_liquid bu sayıyı
        # `material_service_limit_K = 2000` diye doğrudan basıyordu ve o
        # sıcaklıkta malzeme çoktan erimişti. Klamp erime noktasına indi;
        # iddia da ona bağlandı (kayıttan türetilir, ikinci kez yazılmaz).
        assert m['max_service_temperature'] == pytest.approx(m['melting_point'])
        assert m['max_service_temperature'] == pytest.approx(1705)

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

    def test_safety_analyzer_unknown_material_is_rejected(self):
        """ÖH D15 / P5B2-03 — BEKÇİ ÇEVRİLDİ (ÖK-05).

        Bu test eskiden ``test_safety_analyzer_unknown_material_falls_back_
        to_4130`` adıyla, bilinmeyen malzemenin SESSİZCE ``steel_4130``a
        düşmesini ZORUNLU KILIYORDU (``assert r['material'] ==
        'steel_4130'``). Yani kampanyanın KRİTİK P5B2-03 kalemini kilitleyen
        bekçiydi: onarım yapılsa test kırmızıya dönerdi ve "onarım testleri
        kırdı" diye geri alınırdı.

        Ölçülen kusur (once.json): ``'aluminum6061'`` (tek alt çizgi
        eksik) akma SF'yi 1,9643'ten 3,2857'ye çıkarıyor, hükmü UNSAFE
        yönünden uzaklaştırıyordu. Yedeğin YÖNÜ emniyetsizdi.

        Yeni sözleşme: çözülemeyen malzeme adı hüküm ÜRETMEZ, adıyla
        reddedilir. Ucun karşılığı zaten HTTP 422
        ``unresolved_material``dır (ölçüldü, aynı kanıt dosyası).
        """
        from hrma.analysis.safety_analysis import (SafetyAnalyzer,
                                                   UnresolvedChamberMaterial)
        sa = SafetyAnalyzer()
        motor = {'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
                 'wall_thickness': 0.005}
        with pytest.raises(UnresolvedChamberMaterial) as hata:
            sa._analyze_structural_safety(motor, 'not_a_material')
        assert 'not_a_material' in str(hata.value)
        # Tanınan ad hâlâ çalışır (onarım kapıyı tümden kapatmadı).
        r = sa._analyze_structural_safety(motor, 'steel_4130')
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
