"""CAD imalat notları ve geometri özeti dürüstlük bekçisi.

Kapsanan bulgular (v2.6.26 denetimi):

  CAD-NOTES-6 — `_generate_manufacturing_notes(motor_data)` parametresini HİÇ
  okumuyordu: 22 satırlık sabit metin listesi döndürüyordu, 500 N'lik motorla
  50 kN'lik motorun imalat notları birebir aynıydı ("bore to final ID",
  "graphite blank", "1.5x operating pressure"). Komşu fonksiyonlar
  (_generate_technical_drawings, _generate_material_specifications) 2026-07-19
  denetiminde çözücüye bağlanmıştı; bu fonksiyon atlanmıştı.

  ZERO-PAT-8 — geometri özetinde `(_real_scalar(...) or 0.0)` zinciri
  _real_scalar'ın None'ını yutuyordu: geçersiz (NaN/eksik) kamara boyu toplam
  uzunluğa sessizce 0 mm katkı yapıyor, kullanıcı yalnız lüle boyundan ibaret
  bir "toplam boy" görüp bunun hesaplandığını sanıyordu.

Ölçüt her iki bulguda da aynı: "hesaplanmamış bir değer hesaplanmış gibi
gösterilemez"; sıfır ile "hesaplanamadı" aynı şey değildir.
"""

import contextlib
import inspect
import io
import math

import pytest

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.export.cad_visualization import (
    MANUFACTURING_NOTE_BASIS,
    MANUFACTURING_STANDARD_BASIS,
    NOT_AVAILABLE_SPEC,
    MotorCADDesigner,
)


def _silent(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return fn(*args, **kwargs)


def _run(**kwargs):
    return _silent(lambda: HybridRocketEngine(**kwargs).calculate())


@pytest.fixture(scope='module')
def small_motor():
    """Küçük amatör sınıfı motor (~500 N)."""
    return _run(thrust=500, burn_time=5, of_ratio=6.0, chamber_pressure=15)


@pytest.fixture(scope='module')
def big_motor():
    """Büyük motor (~50 kN) — notların gerçekten farklılaşması için."""
    return _run(thrust=50000, burn_time=20, of_ratio=6.0, chamber_pressure=60)


@pytest.fixture(scope='module')
def designer():
    return MotorCADDesigner()


def _joined(notes):
    return "\n".join(notes)


# ---------------------------------------------------------------------------
# CAD-NOTES-6 — notlar motora göre değişmeli
# ---------------------------------------------------------------------------

class TestManufacturingNotesUseMotorData:

    def test_notes_differ_between_two_motors(self, designer, small_motor, big_motor):
        """500 N ve 50 kN motorun notları BİREBİR aynı olamaz."""
        small = designer._generate_manufacturing_notes(small_motor)
        big = designer._generate_manufacturing_notes(big_motor)
        assert small != big, \
            'imalat notları motor verisinden bağımsız (sabit metin listesi)'

        # Ölçü taşıyan satırlar tek tek farklı olmalı, yalnız bir satır
        # değiştiği için testin geçmesi yeterli sayılmaz.
        differing = sum(1 for a, b in zip(small, big) if a != b)
        assert differing >= 3, \
            f'yalnız {differing} satır farklı; ölçüler çözücüye bağlanmamış'

    def test_notes_carry_real_chamber_and_throat_dimensions(
            self, designer, small_motor):
        """Kamara iç çapı ve boğaz çapı motor sonucundaki GERÇEK değer olmalı."""
        text = _joined(designer._generate_manufacturing_notes(small_motor))

        chamber_mm = small_motor['chamber_diameter'] * 1000.0
        throat_mm = small_motor['throat_diameter'] * 1000.0
        assert f"{chamber_mm:.1f} mm ID" in text
        assert f"{throat_mm:.2f} mm diameter" in text

    def test_notes_carry_structural_wall_thickness(self, designer, small_motor):
        """Cidar kalınlığı yapısal analizin önerisiyle aynı olmalı."""
        text = _joined(designer._generate_manufacturing_notes(small_motor))
        wall_mm = (small_motor['structural_analysis']['chamber_analysis']
                   ['recommended_thickness'])
        assert f"{wall_mm:.1f} mm wall" in text
        assert 'structural analysis' in text

    def test_pressure_test_note_uses_computed_pressures(
            self, designer, small_motor):
        """'1.5x operating pressure' yerine GERÇEK basınçlar yazılmalı."""
        text = _joined(designer._generate_manufacturing_notes(small_motor))

        pc_bar = small_motor['chamber_pressure']
        design_bar = (small_motor['structural_analysis']['design_parameters']
                      ['design_pressure'])
        assert f"operating pressure {pc_bar:.1f} bar" in text
        assert f"{design_bar:.1f} bar design pressure" in text
        # Eski uydurma ifade geri gelmemeli
        assert '1.5x operating pressure' not in text

    def test_injector_note_matches_single_source_of_truth(
            self, designer, small_motor):
        """Delik sayısı/çapı _injector_spec ile AYNI olmalı (çizimle çelişmesin)."""
        from hrma.export.cad_visualization import _injector_spec

        inj = _injector_spec(small_motor)
        text = _joined(designer._generate_manufacturing_notes(small_motor))
        assert inj['n_orifices'], 'test motoru enjektör verisi üretmeli'
        assert f"drill {inj['n_orifices']} orifices" in text
        assert f"{inj['orifice_diameter_mm']:.2f} mm diameter" in text

    def test_old_hardcoded_phrases_are_gone(self, designer, small_motor):
        """Motorla ilgisi olmayan eski sabit ifadeler dönmemeli."""
        text = _joined(designer._generate_manufacturing_notes(small_motor))
        for phrase in ('bore to final ID',
                       'graphite blank',
                       'diamond polish throat',
                       'carbide bits',
                       '1.5x operating pressure'):
            assert phrase not in text, f'sabit uydurma ifade geri gelmiş: {phrase}'

    def test_function_actually_reads_its_argument(self):
        """Kaynak seviyesinde bekçi: gövde motor_data'yı okumazsa test kırılır."""
        source = inspect.getsource(MotorCADDesigner._generate_manufacturing_notes)
        body = source.split('"""')[-1]
        assert 'motor_data' in body, \
            'fonksiyon motor_data parametresini yine kullanmıyor'


# ---------------------------------------------------------------------------
# CAD-NOTES-6 — bağlanamayan kısımlar ETİKETLİ olmalı
# ---------------------------------------------------------------------------

class TestManufacturingNotesLabelling:

    def test_generic_steps_carry_basis_label(self, designer, small_motor):
        """Hesaplanmayan adımlar 'genel atölye pratiği' diye etiketlenmeli."""
        notes = designer._generate_manufacturing_notes(small_motor)
        text = _joined(notes)
        assert 'BASIS:' in text
        assert MANUFACTURING_NOTE_BASIS in text

    def test_cited_standards_are_marked_unverified(self, designer, small_motor):
        """ANSI B1.1 / AWS D1.1 gerçek standartlar; uygulanabilirlik iddiası yok."""
        text = _joined(designer._generate_manufacturing_notes(small_motor))
        assert 'ANSI B1.1' in text and 'AWS D1.1' in text
        assert MANUFACTURING_STANDARD_BASIS in text
        assert 'does not verify' in MANUFACTURING_STANDARD_BASIS

    def test_missing_data_is_declared_not_invented(self, designer):
        """Veri yoksa sabit sayı uydurulmaz, NOT AVAILABLE yazılır."""
        notes = designer._generate_manufacturing_notes({})
        text = _joined(notes)
        assert text.count(NOT_AVAILABLE_SPEC) >= 3
        # Boş girdide hiçbir ölçü satırı sayı içermemeli
        measured = [n for n in notes
                    if n.startswith(('1. Chamber', '5. Pressure'))]
        assert measured, 'ölçü satırları kaybolmamalı'
        for line in measured:
            assert not any(ch.isdigit() for ch in line.split(':', 1)[1]
                           .replace('B1.1', '').replace('D1.1', '')), \
                f'boş girdide uydurma sayı: {line}'

    def test_notes_stay_a_list_of_strings(self, designer, small_motor):
        """API sözleşmesi: JSON yanıtı ve metin rapor düz metin listesi bekler."""
        notes = designer._generate_manufacturing_notes(small_motor)
        assert isinstance(notes, list)
        assert all(isinstance(n, str) for n in notes)


# ---------------------------------------------------------------------------
# ZERO-PAT-8 — geçersiz uzunluk 0 mm olamaz
# ---------------------------------------------------------------------------

class TestGeometrySummaryLength:

    def test_valid_motor_gives_real_total_length(self, designer, small_motor):
        summary = designer._generate_cad_performance_summary(small_motor)
        total = summary['geometry_summary']['total_length']
        assert total is not None and total > 0
        # Kamara boyundan büyük olmalı (lüle ekleniyor)
        assert total > small_motor['chamber_length'] * 1000.0

    def test_nan_chamber_length_gives_none_not_zero(self, designer, small_motor):
        """NaN kamara boyu sessizce 0 mm katkı yapamaz."""
        broken = dict(small_motor)
        broken['chamber_length'] = float('nan')
        total = (designer._generate_cad_performance_summary(broken)
                 ['geometry_summary']['total_length'])
        assert total is None, \
            f"geçersiz kamara boyu hesaplanmış gibi gösterildi: {total}"

    def test_missing_chamber_length_gives_none(self, designer, small_motor):
        broken = dict(small_motor)
        broken.pop('chamber_length', None)
        total = (designer._generate_cad_performance_summary(broken)
                 ['geometry_summary']['total_length'])
        assert total is None

    def test_zero_is_never_used_as_a_length_fallback(self, designer, small_motor):
        """Hiçbir geçersiz girdi 0.0 mm 'toplam boy' üretmemeli."""
        for bad_value in (float('nan'), None, 0.0, -1.0, 'abc'):
            broken = dict(small_motor)
            broken['chamber_length'] = bad_value
            total = (designer._generate_cad_performance_summary(broken)
                     ['geometry_summary']['total_length'])
            assert total is None, f"{bad_value!r} girdisinde total_length={total}"

    def test_drawing_nozzle_length_is_never_zero(self, designer, small_motor):
        """Teknik çizimde de aynı kural: boy ya gerçek ya NOT AVAILABLE."""
        drawings = designer._generate_technical_drawings(small_motor)
        length = drawings['nozzle']['length']
        assert length == NOT_AVAILABLE_SPEC or (
            isinstance(length, float) and length > 0 and math.isfinite(length))

    def test_text_report_labels_missing_length(self, designer, small_motor):
        """Metin raporda None, 'None' diye değil açık etiketle basılmalı."""
        broken = dict(small_motor)
        broken['chamber_length'] = float('nan')
        summary = designer._generate_cad_performance_summary(broken)
        assert summary['geometry_summary']['total_length'] is None

        report = _silent(designer.generate_cad_report, small_motor)
        assert 'CAD PERFORMANCE SUMMARY' in report
        assert 'total_length: None' not in report


# ---------------------------------------------------------------------------
# ZERO-PAT-8 (aynı kalıp) — geometri özetinin DİĞER alanları da uydurmamalı
#
# Eski kalıp `motor_data.get('chamber_diameter', 0.1)` iki ayrı yoldan
# yanlıştı: anahtar yoksa 100 mm çaplı / 500 mm boylu / 1000 N'lik UYDURMA bir
# motorun özetini hesaplanmış gibi basıyordu, anahtar varken değeri None ise
# çarpma TypeError ile patlıyordu.
# ---------------------------------------------------------------------------

class TestGeometrySummaryNeverFabricates:

    def test_empty_input_produces_no_numbers_at_all(self, designer):
        """Girdi yoksa özet sayı üretemez — varsayılan motor uydurulmaz."""
        summary = designer._generate_cad_performance_summary({})
        geo = summary['geometry_summary']
        assert geo['total_length'] is None
        assert geo['max_diameter'] is None
        assert geo['chamber_volume'] is None
        assert geo['thrust_to_weight'] is None

    @pytest.mark.parametrize('bad_value', [None, float('nan'), 0.0, -0.05, 'abc'])
    def test_invalid_diameter_gives_none_not_100mm(
            self, designer, small_motor, bad_value):
        """Geçersiz kamara çapı 100 mm'lik uydurma çapa düşmemeli (ve patlamamalı)."""
        broken = dict(small_motor)
        broken['chamber_diameter'] = bad_value
        geo = _silent(designer._generate_cad_performance_summary,
                      broken)['geometry_summary']
        assert geo['max_diameter'] is None, \
            f"{bad_value!r} girdisinde max_diameter={geo['max_diameter']}"
        assert geo['chamber_volume'] is None

    def test_missing_thrust_gives_none_not_1000n(self, designer, small_motor):
        """İtki yoksa T/W hesaplanamaz; 1000 N varsayılanı uydurulamaz."""
        broken = dict(small_motor)
        broken.pop('thrust', None)
        geo = _silent(designer._generate_cad_performance_summary,
                      broken)['geometry_summary']
        assert geo['thrust_to_weight'] is None

    def test_valid_motor_still_reports_every_field(self, designer, small_motor):
        """Dürüstlük düzeltmesi geçerli motorda alan kaybettirmemeli."""
        geo = designer._generate_cad_performance_summary(
            small_motor)['geometry_summary']
        for key in ('total_length', 'max_diameter', 'chamber_volume',
                    'thrust_to_weight'):
            value = geo[key]
            assert value is not None and math.isfinite(value) and value > 0, \
                f'{key} geçerli motorda üretilmedi: {value!r}'

        # Hacim gerçek çap ve boydan gelmeli (uydurma 0.1 m / 0.5 m değil)
        expected_cm3 = (math.pi * (small_motor['chamber_diameter'] / 2) ** 2
                        * small_motor['chamber_length'] * 1e6)
        assert geo['chamber_volume'] == pytest.approx(expected_cm3, rel=1e-9)
