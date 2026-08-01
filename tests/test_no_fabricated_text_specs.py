"""BEKÇİ: mühendislik sayısı taşıyan METİN SABİTLERİ (v2.6.26 · P4).

Sayısal tarayıcılar bu kusur sınıfını göremez, çünkü değer bir ``float``
değil bir **dize**dir::

    'minimum_web_thickness': '15mm at star valleys'
    'requirement':           'Torque to 150 Nm'
    'operating_temperature': '2800°C'
    'diameter':              '+-0.1 mm'

Kullanıcı bunları hesap sonucu sanır; oysa 75 mm'lik amatör motorla 500 mm'lik
motorda birebir aynıdırlar. Ölçülen örnekler (bu turda kapatıldı):

* ``'15mm at star valleys'`` — aynı sözlükte ``web_thickness`` ZATEN
  hesaplanıyordu ve 75 mm gövdeli motorda **10,0 mm** çıkıyordu; metin %50
  daha kalın bir web vaat ediyordu.
* ``'10mm between cores'`` — çözücünün gerçekten yaktığı portta en ince web
  75 mm gövdede **6,25 mm**, 500 mm gövdede **50,0 mm**. Metin ikisine de
  10 mm diyordu. Kalemi hesaba bağlarken ikinci bir kusur ortaya çıktı:
  rapor bloğu çözücünün portundan BAŞKA bir yerleşim anlatıyordu
  (0,6·D_core çaplı uydular, (D_kasa−d)/4 yarıçapta → 75 mm gövdede
  çekirdekler 5,0 mm üst üste biniyordu); rapor artık ``_wagon_port_polygon``
  ile aynı geometriyi okuyor.
* ``'Torque to 150 Nm'`` — hesaplanan tork M6 8.8 için **10,5 Nm**, M8 8.8
  için **25,5 Nm**, M16 8.8 için **218,5 Nm**. M8 bir cıvatayı 150 Nm'ye
  sıkmak proof yükünü kat kat aşar: kullanıcı cıvatayı koparır.
* ``'2800°C'`` — gerçek boğaz gazı statik sıcaklığı KNSU'da **1345,9 °C**,
  APCP'de **3015,1 °C**.
* ``'+-0.1 mm'`` / ``'+-0.5 mm'`` — yanlarındaki künye "ISO 2768-m" diyordu
  ama o standardın tablosu ölçüyle değişir (Ø75 mm için f sınıfı ±0,15 mm,
  Ø500 mm için ±0,30 mm). Sayılar gösterilen kaynağa uymuyordu.

Bu dosya iki şey yapar:

1. **AST taraması** — hedef iki dosyada, sözlük değeri olarak yazılmış
   "rakam + birim/tolerans" içeren metin sabiti kalmadığını doğrular.
2. **Canlılık ölçümü** — kaldırılan sabitlerin yerine gelen değerlerin
   gerçekten girdiyle DEĞİŞTİĞİNİ ölçer. Sadece metni silmek yetmez; sabit
   bir metnin yerine sabit bir sayı koymak aynı kusurdur.

Dedektörün kendisi de sınanır: kaldırılan 18 metnin tamamı yakalanmalı
(negatif kontrol) ve kaynak künyeleri / standart adları / malzeme kodları
yakalanmamalı (pozitif kontrol).
"""

import ast
import contextlib
import io
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Bu bekçinin kapsadığı dosyalar.
TARGET_FILES = (
    'hrma/engines/solid_rocket_engine.py',
    'hrma/export/cad_visualization.py',
)

# ---------------------------------------------------------------------------
# Dedektör
# ---------------------------------------------------------------------------
#: Sayının ARDINDAN gelen ÇOK HARFLİ birim/ölçüt simgeleri. Bunlar sayıya
#: bitişik de yazılabilir ('15mm'), boşluklu da ('150 Nm').
#: Yalın 'C' (Celsius) BİLEREK yoktur: 'UN 1.3C' gibi mevzuat sınıf kodlarını
#: yakalardı. Sıcaklık için '°C' / 'deg C' aranır.
_UNIT_MULTI = (
    r'(?:mm/s|m/s|mm|cm³|cm3|cm|km|um|µm|μm|nm|deg\s*C|°C|°|'
    r'N·m|Nm|kN|MN|kg|lb|bar|psi|kPa|MPa|GPa|Pa|'
    r'sec(?:ond)?s?|minutes?|hours?|hrs?|days?|weeks?|months?|years?|'
    r'Ohms?|ohms?|kW|MW|kJ|MJ|kHz|Hz|%|Ra|m³|m3)'
)
#: TEK HARFLİ birimler yalnız ARADA BOŞLUK varsa sayılır. Sebep: standart ve
#: parça künyeleri harfi sayıya bitişik yazar ('NASA-STD-5020A', 'ISO 3506-1',
#: 'A2-70') ve bunlar ölçüm değil VERİ KAYDIdır. '3 A', '2800 K', '24 h'
#: biçimindeki gerçek ölçüler ise yakalanır.
_UNIT_SINGLE = r'(?:K|N|V|A|W|J|G|m|s|g|h)\b'

#: Ondalık ve bilimsel gösterim ("0.05", "1e-6", "2,5").
_NUM = r'[0-9]+(?:[.,][0-9]+)?(?:[eE][-+]?[0-9]+)?'

#: Sayı ile birim arasında en fazla BİR kısa nitelik olabilir
#: ('1e-6 std cm³/s' gibi).
_QUALIFIER = r'(?:[A-Za-z]{1,4}\s+)?'

_PATTERNS = (
    # 1) Tolerans işareti + sayı:  '±0.05mm', '+-0.1 mm', '+/-2%'
    re.compile(r'(?:±|\+-|\+/-)\s*' + _NUM),
    # 2) Sayı + çok harfli birim: '150 Nm', '2800°C', '24 hours', '15mm'
    re.compile(_NUM + r'\s*' + _QUALIFIER + _UNIT_MULTI),
    # 3) Sayı + BOŞLUK + tek harfli birim: '3 A', '2800 K', '0.5 m'
    re.compile(_NUM + r'\s+' + _QUALIFIER + _UNIT_SINGLE),
)

#: Açıklama alanları taranmaz. Bu bir kaçamak değil, projenin BEYAN
#: sözleşmesidir: kusur "sayının şartname/sonuç gibi sunulması"dır; bir
#: sayının neden ÜRETİLMEDİĞİNİ (ya da kaldırılan eski sabitin ne olduğunu)
#: anlatan düzyazı tam olarak bu kusurun ilacıdır. Bu alanların yanındaki
#: ASIL alan zaten taranıyor: 'cure_time' taranır, 'cure_time_basis' taranmaz.
_EXPLANATORY_EXACT = frozenset({
    'basis', 'note', 'source', 'status', 'model', 'model_note',
    'model_limitation', 'model_applied', 'reason', 'warning', 'docstring',
    'description', 'definition', 'caution', 'limitation',
})
_EXPLANATORY_SUFFIXES = (
    '_basis', '_note', '_source', '_status', '_definition', '_limitation',
    '_meaning', '_convention', '_assumption', '_model', '_reason',
    '_warning', '_description', '_caution', '_explanation',
)

#: MEŞRU İSTİSNALAR. Her kalem için gerekçe zorunludur.
#: Şu an BOŞ: hedef iki dosyada taranan alanların hiçbirinde meşru bir
#: "rakam + birim" metni kalmadı. Buraya bir şey eklenecekse gerekçesi
#: "bu bir VERİ KAYDIDIR (kaynak künyesi, katalog kodu, malzeme adı),
#: hesap çıktısı değildir" biçiminde olmalıdır.
ALLOWED_TEXT_SPECS = {
    # (dosya, anahtar, tam metin): gerekçe
}


def _describe(text):
    """Metin bir mühendislik sayısı taşıyorsa eşleşen parçayı döndürür."""
    for pattern in _PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def _is_explanatory(key):
    return (key in _EXPLANATORY_EXACT
            or any(key.endswith(suffix) for suffix in _EXPLANATORY_SUFFIXES))


def _string_leaves(node):
    """Bir sözlük değerindeki metin sabitleri (liste/tuple içi dahil)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for element in node.elts:
            yield from _string_leaves(element)


def scan_source(source, filename):
    """Sözlük değeri olarak yazılmış 'rakam + birim' metinlerini bulur."""
    findings = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        for key_node, value_node in zip(node.keys, node.values):
            if not (isinstance(key_node, ast.Constant)
                    and isinstance(key_node.value, str)):
                continue
            key = key_node.value
            if _is_explanatory(key):
                continue
            for leaf in _string_leaves(value_node):
                hit = _describe(leaf.value)
                if hit is None:
                    continue
                if (filename, key, leaf.value) in ALLOWED_TEXT_SPECS:
                    continue
                findings.append((leaf.lineno, key, leaf.value, hit))
    return findings


# ---------------------------------------------------------------------------
# 0) Dedektörün kendisi doğru mu?
# ---------------------------------------------------------------------------
#: Bu turda KALDIRILAN metinler. Dedektör bunların TAMAMINI yakalamalı;
#: aksi halde test yeşil kalırken kusur geri gelebilir.
REMOVED_FABRICATIONS = (
    '15mm at star valleys',
    '±0.05mm on star geometry',
    '10mm between cores',
    '±0.02mm core positioning',
    'Ra 0.8 μm',
    '±0.01mm',
    '±0.5°',
    '2800°C',
    '24 hours at 60°C',
    '8 hours at room temperature',
    'Torque to 150 Nm',
    '1.5x design pressure for 30 seconds',
    'Helium leak test <1e-6 std cm³/s',
    'Total mass within ±2%',
    'Continuity within 2.0±0.2 Ohms',
    '0-40°C storage',
    '+-0.1 mm',
    '+-0.5 mm',
    '24-48 hours',
    '4-6 hours',
)

#: Yakalanmaması gerekenler: kaynak künyesi, standart adı, mevzuat sınıfı,
#: malzeme/katalog kodu, formül açıklaması. Bunlar VERİ KAYDIdır.
LEGITIMATE_STRINGS = (
    'ISO 898-1:2013',
    "Shigley's Mechanical Engineering Design 10th ed. Ch. 8",
    'ISO 2768-1',
    'ISO 1302',
    'ANSI Y14.5M-1994',
    'AWS D1.1',
    'UN 1.3C',
    'NASA-STD-5020A Sec. 6.2',
    'NASA SP-8073',
    'UFC 3-340-02',
    'Sutton & Biblarz Eq. 3-30/3-31',
    'Wileman et al. (1991) J. Mech. Design 113',
    'steel_4130',
    'aluminum_6061',
    'AISI 304',
    'M8',
    'A2-70',
    'H7/f6 fit',
    '2A/2B thread class',
    'API 520 practice',
    'Shigley Eq. 8-27',
    'Star (6-pointed)',
    'Wagon Wheel (7 cores)',
    'CNC turning',
    'Electric match',
    'EPDM/phenolic insulation band (SOLID_INSULATION)',
)

#: scan_source için negatif kontrol: eski (kaldırılmış) kod parçası.
#: Bu kaynak taranınca 5 bulgu çıkmalı; 'basis' alanı ve kaynak künyesi
#: çıkmamalı. Böylece taramanın kendisi (sadece regex değil) sınanır.
_OLD_CODE_SAMPLE = '''
def eski():
    return {
        'structural_considerations': {
            'minimum_web_thickness': '15mm at star valleys',
            'manufacturing_tolerance': '±0.05mm on star geometry',
        },
        'manufacturing': {
            'surface_finish': 'Ra 0.8 μm',
            'machining_method': 'CNC turning',
        },
        'performance': {'operating_temperature': '2800°C'},
        'checks': ['Visual inspection', 'Torque to 150 Nm'],
        'basis': 'the previous fixed +/-0.01 mm value was not derived',
        'source': 'ISO 898-1:2013 Table 3',
    }
'''


@pytest.mark.parametrize('text', REMOVED_FABRICATIONS)
def test_detector_catches_every_removed_fabrication(text):
    assert _describe(text) is not None, (
        f'dedektör {text!r} metnini kaçırıyor — bekçi bu kusuru geri '
        'gelirse göremez')


@pytest.mark.parametrize('text', LEGITIMATE_STRINGS)
def test_detector_does_not_flag_data_records(text):
    assert _describe(text) is None, (
        f'{text!r} bir veri kaydı (kaynak/standart/malzeme adı) ama '
        'dedektör onu uydurma sanıyor — yanlış pozitif')


def test_scanner_finds_the_old_code_shape():
    """Tarama eski kodda 5 uydurmayı bulmalı, beyanı/künyeyi bulmamalı."""
    findings = scan_source(_OLD_CODE_SAMPLE, '<negatif-kontrol>')
    flagged_keys = sorted(key for _line, key, _value, _hit in findings)
    assert flagged_keys == ['checks', 'manufacturing_tolerance',
                           'minimum_web_thickness', 'operating_temperature',
                           'surface_finish'], flagged_keys


# ---------------------------------------------------------------------------
# 1) Asıl bekçi: kaynak taraması
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('relative', TARGET_FILES)
def test_no_fabricated_text_specs_in_dict_values(relative):
    path = ROOT / relative
    findings = scan_source(path.read_text(encoding='utf-8'), relative)
    report = '\n'.join(
        f'  {relative}:{line}  {key!r} = {value!r}   (eşleşme: {hit!r})'
        for line, key, value, hit in findings)
    assert not findings, (
        'Sözlük değeri olarak yazılmış mühendislik sayısı taşıyan metin '
        'sabitleri bulundu. Her biri için karar verin: HESAPLA (mevcut bir '
        'modele bağlayın), KALDIR (kapsam dışıysa silin) ya da BEYAN EDİN '
        '(sayıyı kaldırıp <alan>_basis ile gerekçe yazın).\n' + report)


def test_allowed_list_entries_carry_a_reason():
    for entry, reason in ALLOWED_TEXT_SPECS.items():
        assert isinstance(reason, str) and len(reason) > 20, (
            f'{entry} izin listesinde ama gerekçesi yok/yetersiz')


# ---------------------------------------------------------------------------
# Ölçüm yardımcıları
# ---------------------------------------------------------------------------
def _silent(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _engine(**kwargs):
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    return _silent(SolidRocketEngine, **kwargs)


SMALL = dict(chamber_diameter=75, grain_length=300, core_diameter=25,
             chamber_pressure=25)
LARGE = dict(chamber_diameter=500, grain_length=2000, core_diameter=150,
             chamber_pressure=70)


# ---------------------------------------------------------------------------
# 2) Yerine gelen değerler CANLI mı?
# ---------------------------------------------------------------------------
class TestStarGrainWeb:
    """'15mm at star valleys' -> gerçek en ince kesit."""

    def test_minimum_web_equals_the_computed_web(self):
        for geometry in (SMALL, LARGE):
            block = _silent(_engine(grain_type='star',
                                    **geometry)._analyze_star_grain)
            considerations = block['structural_considerations']
            assert considerations['minimum_web_thickness_mm'] == pytest.approx(
                block['web_thickness']), (
                'en ince kesit aynı sözlükteki web_thickness ile aynı '
                'geometriden gelmiyor')
            assert considerations['manufacturing_tolerance'] is None
            assert considerations['manufacturing_tolerance_status'] == 'NOT_MODELLED'

    def test_minimum_web_moves_with_geometry(self):
        small = _silent(_engine(grain_type='star',
                                **SMALL)._analyze_star_grain)
        large = _silent(_engine(grain_type='star',
                                **LARGE)._analyze_star_grain)
        small_web = small['structural_considerations']['minimum_web_thickness_mm']
        large_web = large['structural_considerations']['minimum_web_thickness_mm']
        assert large_web > small_web * 2, (
            f'75 mm ve 500 mm motorda web neredeyse aynı '
            f'({small_web:.2f} / {large_web:.2f} mm) — değer ölü')


class TestWagonWheelWeb:
    """'10mm between cores' -> gerçek çekirdek aralığı."""

    def test_minimum_web_is_computed_from_the_layout(self):
        block = _silent(_engine(grain_type='wagon_wheel',
                                **SMALL)._analyze_wagon_wheel_grain)
        challenges = block['structural_challenges']
        expected = min(challenges['web_center_to_satellite_mm'],
                       challenges['web_satellite_to_satellite_mm'],
                       challenges['web_satellite_to_case_mm'])
        assert challenges['minimum_web_mm'] == pytest.approx(expected)
        assert challenges['manufacturing_precision'] is None

    def test_overlap_status_never_contradicts_the_number(self):
        """Durum etiketi hesaplanan web ile çelişemez.

        Kusur KİLİTLENMEZ, GÖRÜNÜR olması istenir: çekirdekler bir gün üst
        üste binerse ``minimum_web_status`` bunu söylemek zorundadır.
        """
        for geometry in (SMALL, LARGE):
            challenges = _silent(_engine(
                grain_type='wagon_wheel',
                **geometry)._analyze_wagon_wheel_grain)['structural_challenges']
            web = challenges['minimum_web_mm']
            status = challenges['minimum_web_status']
            assert (status == 'cores_overlap') == (web <= 0), (
                'durum etiketi hesaplanan web ile çelişiyor')

    def test_reported_geometry_is_the_geometry_the_solver_burns(self):
        """Rapordaki delikler itki eğrisinin yaktığı portla AYNI olmalı.

        Öncesi: rapor 0,6·D_core çaplı uyduları (D_kasa−d)/4 yarıçapa
        koyuyordu; çözücü ise D_core/4 yarıçaplı yedi eşit deliği D_kasa/4
        yarıçapta yakıyordu. 75 mm gövde / 25 mm çekirdekte rapor 15 mm'lik
        delikleri 15 mm yarıçapa koyup 5,0 mm ÜST ÜSTE bindiriyordu.
        """
        engine = _engine(grain_type='wagon_wheel', **SMALL)
        block = _silent(engine._analyze_wagon_wheel_grain)
        hole_diameter_mm = engine.D_core / 4.0 * 2000.0
        assert block['center_core_diameter'] == pytest.approx(hole_diameter_mm)
        assert block['satellite_diameter'] == pytest.approx(hole_diameter_mm)
        assert block['satellite_positions'] == pytest.approx(
            engine.D_chamber / 4.0 * 1000.0)
        port = engine._wagon_port_polygon()
        assert block['total_core_area'] == pytest.approx(port.area, rel=1e-9)


class TestNozzleGasTemperature:
    """'2800°C' -> bu yakıtın gerçek boğaz gaz sıcaklığı."""

    def test_temperature_follows_the_propellant(self):
        sugar = _silent(_engine(propellant_type='knsu',
                                **SMALL)._design_nozzle_geometry)['performance']
        apcp = _silent(_engine(propellant_type='apcp',
                               **SMALL)._design_nozzle_geometry)['performance']
        assert (apcp['throat_gas_static_temperature_c']
                > sugar['throat_gas_static_temperature_c'] + 500), (
            'şeker ve APCP motorunda boğaz gaz sıcaklığı neredeyse aynı')

    def test_static_temperature_is_the_isentropic_sonic_value(self):
        engine = _engine(propellant_type='apcp', **LARGE)
        performance = _silent(engine._design_nozzle_geometry)['performance']
        expected = engine.T_c * 2.0 / (engine.gamma + 1.0)
        assert performance['throat_gas_static_temperature_k'] == pytest.approx(
            expected, rel=1e-9)
        assert performance['chamber_flame_temperature_k'] == pytest.approx(
            engine.T_c)

    def test_recovery_temperature_sits_between_static_and_flame(self):
        performance = _silent(_engine(propellant_type='apcp',
                                      **LARGE)._design_nozzle_geometry)['performance']
        recovery = performance['throat_recovery_temperature_k']
        if recovery is None:            # ısı transferi modülü yoksa sayı UYDURULMAZ
            pytest.skip('heat_transfer_analysis yok; alan None olarak beyan edildi')
        assert (performance['throat_gas_static_temperature_k'] < recovery
                <= performance['chamber_flame_temperature_k'])

    def test_manufacturing_specs_are_declared_not_invented(self):
        manufacturing = _silent(
            _engine(**SMALL)._design_nozzle_geometry)['manufacturing']
        assert manufacturing['status'] == 'NOT_MODELLED'
        for field in ('surface_finish', 'throat_tolerance', 'angle_tolerance'):
            assert manufacturing[field] is None, f'{field} hâlâ uyduruluyor'


class TestClosureTorque:
    """'Torque to 150 Nm' -> Shigley Denk. 8-27 (T = K·F_i·d)."""

    @staticmethod
    def _closure_step(engine):
        return _silent(engine._generate_assembly_sequence)['sequence'][4]

    def test_without_bolt_count_no_number_is_invented(self):
        step = self._closure_step(_engine(**SMALL))
        assert step['tightening_torque_nm'] is None
        assert step['requirement'] is None
        assert 'NOT_SIZED' in step['tightening_torque_basis']

    def test_torque_follows_bolt_size(self):
        torques = {}
        for size in ('M6', 'M8', 'M16'):
            engine = _engine(overrides={'closure_bolt_count': 8,
                                        'closure_bolt_size': size}, **SMALL)
            torques[size] = self._closure_step(engine)['tightening_torque_nm']
        assert torques['M6'] < torques['M8'] < torques['M16'], torques
        # M8 8.8 kuru sıkma torku yayımlanmış tablolarda ~25 Nm'dir; eski
        # sabit 150 Nm bu cıvatanın proof yükünün kat kat üstündeydi.
        assert 20.0 < torques['M8'] < 32.0, torques
        assert torques['M8'] < 150.0

    def test_torque_matches_the_bolted_joint_analyser(self):
        engine = _engine(overrides={'closure_bolt_count': 6,
                                    'closure_bolt_size': 'M10'}, **LARGE)
        joint = _silent(engine._closure_joint_analysis)
        step = self._closure_step(engine)
        assert step['tightening_torque_nm'] == pytest.approx(
            joint['tightening_torque_nm'])
        # T = K * F_i * d bağıntısı gerçekten kullanılmış mı?
        from hrma.analysis.bolted_joint import BoltedJointAnalyzer
        analyzer = BoltedJointAnalyzer(size='M10', property_class='8.8',
                                       bolt_count=6)
        expected = (joint['nut_factor_K'] * analyzer.preload()['preload_N']
                    * analyzer.d_mm * 1e-3)
        assert joint['tightening_torque_nm'] == pytest.approx(expected,
                                                              rel=1e-9)


class TestCureScheduleAndQuality:
    """Kürleme çizelgesi ve kabul ölçütleri: sayı yok, gerekçe var."""

    def test_cure_times_are_declared_not_modelled(self):
        sequence = _silent(_engine(**SMALL)._generate_assembly_sequence)['sequence']
        cure_steps = [s for s in sequence if 'cure_time' in s]
        assert len(cure_steps) == 2
        for step in cure_steps:
            assert step['cure_time'] is None
            assert 'NOT_MODELLED' in step['cure_time_basis']

    def test_acceptance_limits_are_not_invented(self):
        quality = _silent(_engine(**SMALL)._generate_quality_requirements)
        final = quality['final_inspection']
        assert final['status'] == 'NOT_MODELLED'
        for field in ('pressure_test', 'leak_test', 'weight_check'):
            assert final[field] is None, f'{field} hâlâ uyduruluyor'
            assert final[f'{field}_basis']
        assert quality['acceptance_criteria']['electrical_test'] is None

    def test_storage_temperature_band_is_not_invented(self):
        engine = _engine(**SMALL)
        curve = _silent(engine.calculate_performance)['thrust_curve']
        handling = _silent(engine._calculate_safety_analysis,
                           curve)['handling_safety']
        assert handling['temperature_limits'] is None
        assert handling['temperature_limits_status'] == 'NOT_MODELLED'
        assert 'strain_safety_factor' in handling['temperature_limits_basis']


class TestMonteCarloCriteriaText:
    """Açıklama metni ölçütün KENDİSİNDEN üretilmeli, elle yazılmamalı."""

    def test_text_follows_the_tolerance_table(self, monkeypatch):
        from hrma.engines import solid_rocket_engine as module
        table = dict(module.SOLID_MC_TOLERANCE_MODEL)
        table['thrust_band_rel'] = 0.20
        table['burn_rate_a_rel_sigma'] = 0.07
        monkeypatch.setattr(module, 'SOLID_MC_TOLERANCE_MODEL', table)
        result = _silent(_engine(**SMALL).run_monte_carlo, n_samples=20, seed=3)
        assert 'İtki ±%20' in result['criteria'], result['criteria']
        assert 'a ±%7' in result['criteria'], result['criteria']
        assert result['criteria_detail']['thrust_band_rel'] == 0.20

    def test_detail_block_is_machine_readable(self):
        from hrma.engines.solid_rocket_engine import SOLID_MC_TOLERANCE_MODEL
        result = _silent(_engine(**SMALL).run_monte_carlo, n_samples=20, seed=3)
        assert result['criteria_detail'] == dict(SOLID_MC_TOLERANCE_MODEL)


# ---------------------------------------------------------------------------
# 3) CAD tarafı
# ---------------------------------------------------------------------------
class TestCadDrawingTolerances:
    """'+-0.1 mm' / '+-0.5 mm' -> ISO 2768-1 tablosundan ÖLÇÜYE göre."""

    @staticmethod
    def _chamber(diameter_m, length_m, wall_m):
        from hrma.export.cad_visualization import MotorCADDesigner
        motor = {
            'chamber_diameter': diameter_m,
            'chamber_length': length_m,
            'wall_thickness': wall_m,
            'throat_diameter': diameter_m * 0.25,
            'exit_diameter': diameter_m * 0.5,
            'structural_analysis': {
                'chamber_analysis': {'wall_thickness': wall_m,
                                     'material': 'steel_4130'},
            },
        }
        drawings = _silent(MotorCADDesigner()._generate_technical_drawings,
                           motor)
        return drawings['chamber']

    def test_tolerance_scales_with_the_nominal_size(self):
        small = self._chamber(0.075, 0.30, 0.003)['tolerances']
        large = self._chamber(0.500, 2.00, 0.012)['tolerances']
        assert small['diameter']['tolerance_mm'] < large['diameter']['tolerance_mm']
        assert small['length']['tolerance_mm'] < large['length']['tolerance_mm']

    def test_tolerance_matches_the_single_iso_table_in_the_project(self):
        from hrma.engines.liquid_rocket_engine import (
            ISO2768_GRADE_GENERAL, ISO2768_GRADE_PRECISION,
            _iso2768_linear_tolerance_mm)
        chamber = self._chamber(0.075, 0.30, 0.003)
        tolerances = chamber['tolerances']
        assert tolerances['diameter']['nominal_mm'] == pytest.approx(75.0)
        assert tolerances['diameter']['tolerance_mm'] == pytest.approx(
            _iso2768_linear_tolerance_mm(75.0, ISO2768_GRADE_PRECISION))
        assert tolerances['length']['tolerance_mm'] == pytest.approx(
            _iso2768_linear_tolerance_mm(300.0, ISO2768_GRADE_GENERAL))
        # Eski sabit ±0.1 mm çap toleransı ISO 2768-f'in Ø75 mm satırından
        # (±0.15 mm) DAHA DAR idi: künye ile sayı çelişiyordu.
        assert tolerances['diameter']['tolerance_mm'] != pytest.approx(0.1)

    def test_tolerance_block_names_its_source(self):
        tolerances = self._chamber(0.075, 0.30, 0.003)['tolerances']
        assert 'ISO 2768-1' in tolerances['source']
        assert tolerances['basis']


class TestCadScheduleRemoved:
    """Termin alanları V2.6.26 planı §2.2 gereği KALDIRILDI."""

    def test_machining_and_assembly_time_fields_are_gone(self):
        from hrma.export.cad_visualization import MotorCADDesigner
        summary = _silent(
            MotorCADDesigner()._generate_cad_performance_summary,
            {'chamber_diameter': 0.075, 'chamber_length': 0.30,
             'wall_thickness': 0.003, 'throat_diameter': 0.02,
             'exit_diameter': 0.04, 'thrust': 500.0})
        complexity = summary['manufacturing_complexity']
        assert 'machining_time' not in complexity
        assert 'assembly_time' not in complexity
        assert 'not calculated' in complexity['effort_status']

    def test_no_schedule_literals_left_in_the_module(self):
        source = (ROOT / 'hrma/export/cad_visualization.py').read_text(
            encoding='utf-8')
        # Yalnız açıklama satırlarında (kaldırıldığını anlatan yorumda)
        # geçebilir; kod satırında geçemez.
        for line in source.splitlines():
            code = line.split('#', 1)[0]
            assert "'machining_time'" not in code, line
            assert "'assembly_time'" not in code, line
