"""Export/CAD/rapor katmanı GERÇEK veri bekçisi (2026-07-19 uydurma denetimi).

Bu dosya Dalga D bulgularının geri gelmesini engeller. Ölçüt her yerde aynı:

    "Kullanıcı bu sayının kendi girdisinden hesaplandığına inanır mı?
     İnanıyorsa, gerçekten hesaplanmalı; hesaplanamıyorsa etiketlenmeli."

Kapsanan bulgular:
  1. .eng itki eğrisi — gerçek çözüm varsa taşınır, yoksa uydurma rampa/düşüş
     ÜRETİLMEZ; dosya kaynağını yorum satırında beyan eder.
  2. CAD bileşen kütlesi — yapısal analizin GERÇEK cidar kalınlığı ve malzeme
     yoğunluğundan; sabit 5 mm / 7850 kg/m^3 değil.
  3. Teknik çizim / PDF rapor ölçüleri fiziksel bantta (birim karışıklığı yok).
  4. Güvenlik analizi yoksa PDF "not evaluated" der, 0.0/10 puan uydurmaz.
  5. Kesit açıları çözücünün nozzle_angles değerleriyle eşleşir.
  6. Enjektör için tek doğruluk kaynağı (çizim/CAD aynı sayıyı gösterir).
  7. PDF'in "Minimum Safety Factor (verified stations)" satırı GERÇEKTEN
     doğrulanmış istasyonların MİNİMUMUDUR (ÖH B-1/B14; P14M1-12/-13).
"""

import io
import contextlib
import math
import re

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.export.cad_visualization import (
    MotorCADDesigner, DetailedCADGenerator, NOT_AVAILABLE_SPEC,
    _injector_spec, _nozzle_half_angles)
from hrma.export.openrocket_integration import OpenRocketExporter


def _silent(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def motor():
    result = _silent(lambda: HybridRocketEngine(
        thrust=2000, burn_time=10, of_ratio=6.0,
        chamber_pressure=20).calculate())
    result['motor_name'] = 'REALDATA_TEST'
    return result


# ---------------------------------------------------------------------------
# (a) .eng itki eğrisi
# ---------------------------------------------------------------------------

class TestEngThrustCurve:

    def test_real_transient_curve_is_carried(self, motor):
        """Gerçek zaman-çözümlü eğri varsa .eng onu taşımalı."""
        time = np.linspace(0.0, 8.0, 60)
        # Bilinçli olarak DÜZ OLMAYAN bir eğri: taşınıp taşınmadığı görülsün
        thrust = 1500.0 + 400.0 * np.sin(time / 8.0 * np.pi)
        data = dict(motor)
        data['transient'] = {'time': time.tolist(), 'thrust': thrust.tolist()}

        eng = OpenRocketExporter().export_motor_file(data)
        assert 'transient ballistics solver' in eng
        samples = [tuple(float(x) for x in line.split())
                   for line in eng.splitlines()
                   if line and not line.startswith(';') and len(line.split()) == 2]
        peak = max(f for _t, f in samples)
        assert peak == pytest.approx(thrust.max(), rel=0.02), \
            'gerçek eğrinin tepe değeri .eng dosyasına taşınmalı'
        # Eğri gerçekten değişken olmalı (sabit itkiye düşülmemiş)
        assert peak - min(f for _t, f in samples if f > 0) > 100.0

    def test_solid_thrust_curve_source_is_used(self, motor):
        """Katı çözücünün thrust_curve çıktısı da kabul edilmeli."""
        data = dict(motor)
        data['thrust_curve'] = {
            'time': [0.0, 1.0, 2.0, 3.0, 4.0],
            'thrust': [1000.0, 1800.0, 1600.0, 900.0, 0.0],
        }
        eng = OpenRocketExporter().export_motor_file(data)
        # Etiketten "solid" kelimesi v2.6.26'da çıkarıldı: `thrust_curve` artık
        # hibritte de üretiliyor, motor tipi eğrinin kendisinden bilinemez.
        # Eğri `basis` beyanı taşıyorsa o eklenir (burada taşımıyor).
        assert 'grain burn-back solver' in eng
        assert ' 1800.0' in eng

    def test_no_fabricated_ramp_without_real_curve(self, motor):
        """Gerçek eğri YOKSA: SABİT itki + açık not; uydurma şekil YOK.

        v2.6.26'da hibrit motor da zaman-adımlı itki eğrisi üretmeye başladı
        (eskiden yalnız katıda vardı), yani fixture artık GERÇEK eğri taşıyor.
        Bu testin konusu eğrisiz sonuç olduğu için eğri bilerek çıkarılır;
        aksi hâlde test kendi konusunu ölçmez olurdu.
        """
        data = {k: v for k, v in motor.items()
                if k not in ('thrust_curve', 'transient')}
        eng = OpenRocketExporter().export_motor_file(data)
        assert 'constant-thrust approximation' in eng
        samples = [tuple(float(x) for x in line.split())
                   for line in eng.splitlines()
                   if line and not line.startswith(';') and len(line.split()) == 2]
        burning = [f for _t, f in samples if f > 0]
        assert burning, '.eng dosyası itki verisi içermeli (kaldırma yok)'
        # Sabit: tüm sıfır-olmayan örnekler eşit olmalı. Eski uydurma eğride
        # %15 düşüş + rampa vardı; bu test onu yakalar.
        assert max(burning) == pytest.approx(min(burning), rel=1e-9)
        assert max(burning) == pytest.approx(motor['thrust'], rel=1e-9)

    def test_hybrid_curve_is_not_labelled_as_solid(self, motor):
        """Hibrit eğri KATI çözücüsü diye etiketlenmemeli (v2.6.26 bekçisi).

        `thrust_curve` eskiden yalnız katı motorda vardı ve .eng etiketi
        "solid grain burn-back solver" diye SABİTTİ. Aynı sürümde hibrit de
        eğri üretmeye başlayınca hibrit dosyalar katı çözücüsüyle üretilmiş
        gibi etiketlendi. Etiket artık eğrinin kendi `basis` beyanını taşır.
        """
        assert motor.get('thrust_curve'), 'fixture gerçek eğri taşımalı'
        eng = OpenRocketExporter().export_motor_file(dict(motor))
        etiket = [l for l in eng.splitlines() if l.startswith('; thrust curve:')]
        assert etiket, '.eng itki eğrisi kaynağını beyan etmeli'
        satir = etiket[0]
        assert 'solid' not in satir.lower(), (
            'hibrit motorun eğrisi KATI çözücüsü diye etiketlenmiş: %s' % satir)
        # Motorun kendi beyanı taşınmalı (uydurma etiket değil).
        basis = motor['thrust_curve'].get('basis')
        if basis:
            assert basis.split(':')[0].strip()[:20] in satir, satir


    def test_loaded_mass_uses_structural_inert_mass(self, motor):
        """Yüklü kütle sabit +0.5 kg değil, yapısal analizin kütlesi olmalı."""
        exporter = OpenRocketExporter()
        inert, source = exporter.resolve_inert_mass(motor)
        assert source == 'structural'
        expected = motor['structural_analysis']['weight_analysis']['total_weight']
        assert inert == pytest.approx(expected, rel=1e-9)

        eng = exporter.export_motor_file(dict(motor))
        motor_line = [l for l in eng.splitlines() if not l.startswith(';')][0]
        prop_mass, loaded_mass = (float(x) for x in motor_line.split()[4:6])
        assert loaded_mass - prop_mass == pytest.approx(expected, abs=1e-3)
        assert loaded_mass - prop_mass != pytest.approx(0.5, abs=1e-3)

    def test_missing_inert_mass_is_declared_not_invented(self):
        """Yapısal kütle yoksa 0.5 kg uydurulmaz, dosya durumu beyan eder."""
        # ÖH D15 / P9B3-11: fikstüre ``chamber_diameter`` EKLENDİ.
        # Eski hâli yalnız boğaz çapı (Ø20 mm) veriyordu, bu yüzden RASP
        # başlığının zarfı Ø20 x 300 mm oluyor ve 2 kg itici ima edilen
        # 21.220 kg/m³'lük FİZİKSEL OLARAK İMKÂNSIZ bir bulk yoğunluk
        # üretiyordu (osmiyumun ~1 katı değil, ~1 kat üstü). Testin
        # KONUSU bu değil — konu "yapısal kütle yoksa 0,5 kg uydurulmaz"
        # sözleşmesi; fikstür yalnızca imkânsız bir motoru tarif ettiği
        # için yeni zarf kapısına takılıyordu. Ø100 mm kamara ile ima
        # edilen yoğunluk 849 kg/m³ (bantta) ve Isp = 5000/(2 x 9,81) =
        # 255 s (gerçekçi). Testin iddiası DEĞİŞMEDİ.
        bare = {'motor_name': 'BARE', 'thrust': 1000.0, 'burn_time': 5.0,
                'propellant_mass_total': 2.0, 'throat_diameter': 0.02,
                'chamber_diameter': 0.10,
                'chamber_length': 0.3, 'total_impulse': 5000.0}
        eng = OpenRocketExporter().export_motor_file(bare)
        assert 'inert (case/structure) mass NOT available' in eng
        motor_line = [l for l in eng.splitlines() if not l.startswith(';')][0]
        prop_mass, loaded_mass = (float(x) for x in motor_line.split()[4:6])
        assert loaded_mass == pytest.approx(prop_mass)

    def test_flight_profile_interpolates_thrust(self, motor):
        """Uçuş profilinde itki ARA-DEĞERLENİR (eski 0.01 s eşleşmesi değil)."""
        profile = OpenRocketExporter().generate_flight_profile(dict(motor))
        thrust = np.array(profile['thrust_data'])
        burning = thrust > 0
        # Yanma süresi toplam uçuşun ~1/3'ü: adımların %25'inden fazlasında
        # itki olmalı. Eski kodda 200 adımın yalnız 13'ünde (%6.5) itki vardı.
        assert burning.mean() > 0.25
        assert profile['max_altitude'] > 0

        # Faz 4 denetimi (F): buradaki iki assertion BOŞTU — biri `or True`
        # ile her hâlde geçiyordu, öteki yalnız dizenin boş olmadığına
        # bakıyordu. Oysa asıl korunması gereken sözleşme şu: aynı yanıtta İKİ
        # AYRI apoje sayısı dönüyor ve hangisinin hangi modelden geldiği
        # okunabilmeli.
        #
        # Ölçüm (2000 N / 10 s / O_F 6,0 hibrit): sürüklemeli 1-DOF entegrasyon
        # 13 800 m, sürüklemesiz kapalı form 257 977 m — 18,7 kat fark. Etiket
        # okunmazsa aynı yanıttaki iki sayı aynı şeyin iki ölçümü sanılır.
        zaman_cozumlu = profile['max_altitude_method']
        kapali_form = profile['performance_summary']['estimated_apogee_method']
        assert 'integration' in zaman_cozumlu.lower(), zaman_cozumlu
        assert 'drag' in zaman_cozumlu.lower(), zaman_cozumlu
        # Kapalı form sürüklemeyi HİÇ modellemediğini beyan etmeli, yoksa
        # okuyucu iki sayıyı aynı şeyin iki ölçümü sanar.
        assert 'no drag' in kapali_form.lower(), kapali_form
        assert 'upper bound' in kapali_form.lower(), kapali_form
        assert zaman_cozumlu != kapali_form

        # Fizik: sürüklemesiz kapalı form, sürüklemeli entegrasyonun ÜST
        # SINIRIDIR. Ters dönerse ya etiketler karışmıştır ya da sürükleme
        # terimi işaret hatasıyla itki gibi davranıyordur.
        ust_sinir = profile['performance_summary']['estimated_apogee']
        assert profile['max_altitude'] < ust_sinir, (
            f"sürüklemeli apoje {profile['max_altitude']:.0f} m, sürüklemesiz "
            f"üst sınır {ust_sinir:.0f} m — üst sınır aşıldı")


# ---------------------------------------------------------------------------
# (b) Bileşen kütlesi cidar kalınlığıyla değişir
# ---------------------------------------------------------------------------

class TestComponentMass:

    def test_chamber_mass_tracks_wall_thickness(self, motor):
        designer = MotorCADDesigner()
        thin = dict(motor)
        thin['structural_analysis'] = dict(motor['structural_analysis'])
        thin['structural_analysis']['chamber_analysis'] = dict(
            motor['structural_analysis']['chamber_analysis'])
        thin['structural_analysis']['chamber_analysis']['recommended_thickness'] = 5.0

        thick = dict(motor)
        thick['structural_analysis'] = dict(motor['structural_analysis'])
        thick['structural_analysis']['chamber_analysis'] = dict(
            motor['structural_analysis']['chamber_analysis'])
        thick['structural_analysis']['chamber_analysis']['recommended_thickness'] = 20.0

        m_thin = designer._estimate_component_mass('chamber', thin)
        m_thick = designer._estimate_component_mass('chamber', thick)
        assert m_thick > 3.0 * m_thin, \
            'kamara kütlesi cidar kalınlığıyla değişmeli (sabit 5 mm YOK)'

    def test_chamber_mass_matches_structural_weight(self, motor):
        """CAD kütlesi yapısal analizin kendi kütlesiyle çelişmemeli."""
        designer = MotorCADDesigner()
        cad_mass = designer._estimate_component_mass('chamber', motor)
        structural = motor['structural_analysis']['weight_analysis']['chamber_weight']
        assert cad_mass == pytest.approx(structural, rel=0.01)

    def test_summary_reports_thickness_source(self, motor):
        summary = MotorCADDesigner()._generate_cad_performance_summary(motor)
        breakdown = summary['mass_breakdown']
        # ÖH D29 (P15B4-12): kalınlık künyesi UZUNLUK sözlüğünde.
        assert summary['geometry_summary']['wall_thickness_source'].startswith(
            'structural analysis')
        assert breakdown['total_dry_mass'] > 0
        assert summary['geometry_summary']['thrust_to_weight'] > 0


# ---------------------------------------------------------------------------
# (c) PDF ölçüleri fiziksel bantta
# ---------------------------------------------------------------------------

class TestPdfDimensions:

    @staticmethod
    def _pdf_text(motor_data, analysis_results):
        from hrma.export.pdf_generator import PDFReportGenerator
        pypdf = pytest.importorskip('pypdf')
        data = PDFReportGenerator().generate_quick_summary_report(
            motor_data, analysis_results)
        reader = pypdf.PdfReader(io.BytesIO(data))
        return '\n'.join(page.extract_text() for page in reader.pages)

    @staticmethod
    def _value_after(text, label):
        lines = [l.strip() for l in text.splitlines()]
        for index, line in enumerate(lines):
            if line == label and index + 1 < len(lines):
                return lines[index + 1]
        return None

    def test_metre_input_is_printed_in_millimetres(self, motor):
        """Hibrit yolu METRE gönderir; PDF mm etiketiyle mm basmalı."""
        text = self._pdf_text(motor, {})
        value = self._value_after(text, 'Chamber Diameter')
        assert value and value.endswith('mm')
        millimetres = float(value.split()[0])
        assert 10.0 <= millimetres <= 1000.0, \
            f'kamara çapı fiziksel bantta olmalı, okunan: {value}'
        assert 'input interpreted as m' in text

    def test_millimetre_input_is_not_rescaled(self, motor):
        """Katı yolu mm gönderir; ikinci kez 1000 ile çarpılmamalı."""
        mm_data = {
            'motor_name': 'SOLID_MM',
            'chamber_diameter': 120.0, 'chamber_length': 700.0,
            'throat_diameter': 30.0, 'exit_diameter': 60.0,
            'expansion_ratio': 4.0,
        }
        text = self._pdf_text(mm_data, {})
        value = self._value_after(text, 'Chamber Diameter')
        assert float(value.split()[0]) == pytest.approx(120.0, rel=1e-6)
        assert 'input interpreted as mm' in text


# ---------------------------------------------------------------------------
# (d) Güvenlik analizi yoksa PDF dürüst davranır
# ---------------------------------------------------------------------------

class TestPdfSafetySection:

    def test_missing_safety_says_not_evaluated(self, motor):
        text = TestPdfDimensions._pdf_text(motor, {'performance': {'thrust': 2000}})
        assert 'NOT EVALUATED IN THIS RUN' in text
        assert '0.0/10' not in text
        assert 'REVIEW REQUIRED' not in text

    def test_real_risk_classes_are_reported(self, motor):
        """Gerçek risk sınıfları raporlanır; dayanaksız 0-10 ölçeği değil.

        v2.6.26 (PDF-710-5): bu test eskiden ``overall_rating: 8.4``
        gönderip PDF'te '8.4/10 ACCEPTABLE' arıyordu. Ölçeği üreten kod
        depoda yoktu; eşik dayanaksızdı. Bkz. tests/test_pdf_analysis.py.
        """
        text = TestPdfDimensions._pdf_text(
            motor, {'safety': {'risk_assessment': {
                'risk_level': 'LOW', 'acceptability': 'ACCEPTABLE'}}})
        assert 'LOW' in text
        assert 'ACCEPTABLE' in text
        assert '/10' not in text


# ---------------------------------------------------------------------------
# (e) Kesit açıları çözücüyle eşleşir
# ---------------------------------------------------------------------------

class TestCrossSectionAngles:

    def test_angles_come_from_nozzle_angles(self, motor):
        conv, div, _type = _nozzle_half_angles(motor)
        solver = motor['nozzle_angles']
        assert conv == pytest.approx(solver['convergent_half_angle_deg'])
        assert div == pytest.approx(solver['divergent_half_angle_deg'])
        # Eski sabitler (15/12) artık kullanılmıyor
        assert (conv, div) != (15.0, 12.0)

    def test_cross_section_legend_shows_real_angles(self, motor):
        import json
        designer = MotorCADDesigner()
        cad = _silent(designer.generate_3d_motor_assembly, dict(motor))
        figure = json.loads(cad['plotly_visualization'])
        names = [trace.get('name') or '' for trace in figure['data']]
        conv, div, _t = _nozzle_half_angles(motor)
        assert any(f'{conv:.1f}' in n for n in names if n.startswith('Conv'))
        assert any(f'{div:.1f}' in n for n in names if n.startswith('Div'))

    def test_technical_drawing_angles_match_solver(self, motor):
        drawings = MotorCADDesigner()._generate_technical_drawings(motor)
        conv, div, _t = _nozzle_half_angles(motor)
        assert drawings['nozzle']['convergence_angle'] == pytest.approx(conv)
        assert drawings['nozzle']['divergence_angle'] == pytest.approx(div)

    def test_bell_nozzle_differs_from_conical(self):
        conical = _silent(lambda: HybridRocketEngine(
            thrust=2000, burn_time=10, of_ratio=6.0, chamber_pressure=20,
            nozzle_type='conical').calculate())
        bell = _silent(lambda: HybridRocketEngine(
            thrust=2000, burn_time=10, of_ratio=6.0, chamber_pressure=20,
            nozzle_type='bell').calculate())
        assert _nozzle_half_angles(conical)[:2] != _nozzle_half_angles(bell)[:2]


# ---------------------------------------------------------------------------
# (f) Enjektör tek doğruluk kaynağı + imalat spesifikasyonu gerçek
# ---------------------------------------------------------------------------

class TestInjectorSingleSource:

    def test_drawing_and_cad_agree(self, motor):
        spec = _injector_spec(motor)
        drawings = MotorCADDesigner()._generate_technical_drawings(motor)
        assert drawings['injector']['orifice_count'] == spec['n_orifices']
        assert drawings['injector']['orifice_diameter'] == pytest.approx(
            spec['orifice_diameter_mm'])
        assert spec['n_orifices'] == motor['injector_design']['number_of_orifices']

    def test_mesh_clipping_does_not_leak_into_specs(self, motor):
        """Mesh 16'ya kırpsa bile çizimde GERÇEK orifis sayısı yazmalı.

        ÖH D33-2 / defter OH-D32-04 — BEKÇİ ÇEVRİLDİ (fikstür düzeltildi,
        iddia korundu). Eski hâli delik sayısını YALNIZ
        ``injector_design.number_of_orifices`` alanında 41'e çekiyordu; oysa
        ölçüldü (aynı fikstür): o alan ``injector_design_detail.ox_circuit
        .n_orifices``in KOPYASIDIR (ikisi de 5) ve devre planının otoritesi
        devrenin kendisidir (ÖH Z5S / defter P9B2-01: STEP üreticisi
        ``_CIRCUIT_COUNT_FIELDS`` sırasında ``ox_circuit.n_orifices``i önce
        okur). Yalnız kopyayı değiştirmek, üründe hiç oluşmayan bir
        çelişki kurup çözüm sırasını sabitliyordu — ve STL/çizim ile STEP'in
        AYNI sırayı okumasını (bu kalemin çekirdeği) imkânsız kılıyordu.
        Artık iki alan da birlikte değişir; testin ölçtüğü şey değişmedi:
        mesh kırpması (16) çizime SIZMAMALI."""
        many = dict(motor)
        many['injector_design'] = dict(motor['injector_design'])
        many['injector_design']['number_of_orifices'] = 41
        many['injector_design_detail'] = dict(
            motor.get('injector_design_detail') or {})
        many['injector_design_detail']['ox_circuit'] = dict(
            many['injector_design_detail'].get('ox_circuit') or {})
        many['injector_design_detail']['ox_circuit']['n_orifices'] = 41
        drawings = MotorCADDesigner()._generate_technical_drawings(many)
        assert drawings['injector']['orifice_count'] == 41
        # V301 CAD-2 kalem 5: mesh sınırı 16 -> 512; 41 delik STL'de de 41.
        assert drawings['injector']['orifice_count_in_mesh'] == 41

    def test_injector_panel_result_wins(self, motor):
        """Kullanıcının enjektör paneli sonucu varsa export onu kullanır."""
        data = dict(motor)
        data['injector_results'] = {'n_holes': 50, 'hole_diameter': 0.94,
                                    'injector_type': 'showerhead'}
        spec = _injector_spec(data)
        assert spec['n_orifices'] == 50
        assert spec['source'].startswith('injector panel')

    def test_drawing_pdf_uses_solver_injector(self, motor, tmp_path):
        """PDF ölçü çizelgesi çözücünün enjektörünü ve cidarını basar.

        ÇEVRİLDİ — ÖH D15 birleşme etkileşimi (1 Eylül 2026)
        ----------------------------------------------------
        Eski hâli çizelgeyi SABİT SAYFA İNDEKSİNDE (``pages[2]``) arıyordu.
        İhracat kulvarının **a2** onarımları (P9B1-18 künye alanları, çan lüle
        çıkış açısı, lüle cidar/yoğunluk beyanları) çizelgeyi büyüttü; çizelge
        artık üç yaprağa bölünüyor ("DIMENSION & MATERIAL SCHEDULE (1/3)" ...)
        ve enjektör satırı 2. yaprağa (``pages[3]``) kaydı. ÖLÇÜLDÜ: aranan
        dize (``5 x d2.24 mm``) PDF'te AYNEN duruyor, yalnız sayfası değişmiş
        — iddia değil ÇAPA eskimişti.

        Yeni sözleşme sayfa numarasına bağlı değil ve DAHA DAR: her iki dize
        de çizelge yapraklarında (kapak/kesit sayfalarında değil) ve TAM BİR
        KEZ geçmeli.
        """
        pytest.importorskip('reportlab')
        pytest.importorskip('kaleido')
        pypdf = pytest.importorskip('pypdf')
        from hrma.export.drawing_generator import generate_drawing_pdf
        path = generate_drawing_pdf(dict(motor), str(tmp_path / 'dr.pdf'))
        sayfalar = [p.extract_text() for p in pypdf.PdfReader(path).pages]
        cizelge = [t for t in sayfalar
                   if 'DIMENSION & MATERIAL SCHEDULE' in t]
        assert cizelge, 'PDF ölçü/malzeme çizelgesi içermiyor'
        spec = _injector_spec(motor)
        wall_mm = motor['structural_analysis'][
            'chamber_analysis']['recommended_thickness']
        # Enjektör künyesi TEK KEZ geçmeli: tek doğruluk kaynağı iddiası
        # ikinci bir orifis satırını da yasaklar.
        enj = f"{spec['n_orifices']} x d{spec['orifice_diameter_mm']:.2f} mm"
        kac = sum(t.count(enj) for t in cizelge)
        assert kac == 1, (
            f'enjektör künyesi {enj!r} çizelgede {kac} kez geçiyor (tam 1 '
            f'olmalı) — {len(cizelge)} çizelge yaprağı tarandı')
        # Cidar kalınlığı yapısal çözümden gelir ve kaynağını YAZAR. (Değer
        # çizelgede iki kez görünüyor: satırın kendisi ve "Structural sizing
        # recommends" notu — ikisi de AYNI sayı, ölçüldü.)
        cidar = f'{wall_mm:.2f} mm'
        cidar_yapragi = [t for t in cizelge if cidar in t]
        assert len(cidar_yapragi) == 1, (
            f'cidar kalınlığı {cidar!r} {len(cidar_yapragi)} çizelge '
            'yaprağında geçiyor — tek yaprakta olmalı')
        assert 'Chamber wall thickness' in cidar_yapragi[0]
        assert 'structural analysis' in cidar_yapragi[0], (
            'cidar kalınlığı kaynak künyesi olmadan basılıyor')


class TestManufacturingSpecsAreReal:

    def test_wall_thickness_from_structural_analysis(self, motor):
        drawings = MotorCADDesigner()._generate_technical_drawings(motor)
        expected = motor['structural_analysis']['chamber_analysis']['recommended_thickness']
        assert drawings['chamber']['wall_thickness'] == pytest.approx(expected)
        assert drawings['chamber']['wall_thickness'] != 5.0
        assert drawings['chamber']['material'] != 'Steel 304'

    def test_missing_structural_data_is_labelled_not_invented(self):
        bare = {'chamber_diameter': 0.1, 'chamber_length': 0.4,
                'throat_diameter': 0.02, 'exit_diameter': 0.05}
        drawings = MotorCADDesigner()._generate_technical_drawings(bare)
        assert drawings['chamber']['wall_thickness'] == NOT_AVAILABLE_SPEC
        assert drawings['chamber']['material'] == NOT_AVAILABLE_SPEC
        assert drawings['injector']['orifice_count'] == NOT_AVAILABLE_SPEC

    def test_tolerances_declare_their_basis(self, motor):
        drawings = MotorCADDesigner()._generate_technical_drawings(motor)
        assert 'ISO 2768' in drawings['chamber']['tolerances']['basis']
        assert 'not computed' in drawings['chamber']['finish_basis']

    def test_solid_component_details_use_structural_safety_factor(self, motor):
        """Kasa özeti emniyet katsayısını VE cidarı analizden almalı.

        ÖH B-1/B16 (defter P14M1-04). Cidar iddiası eskiden
        ``!= '5mm'`` idi; ürün kalınlığı ``'%.2f mm'`` biçiminde yazdığı
        için o karşılaştırma HİÇBİR girdide yanlış olamazdı — kalıcı doğru
        bir bekçi. Mutasyonla ölçüldü: özetteki cidar 2× büyütüldüğünde
        bekçi yeşil kaldı. İddia artık DEĞER karşılaştırmasıdır ve ürünün
        kendi biçimiyle uyumludur.
        """
        details = DetailedCADGenerator()._get_solid_component_details(motor)
        expected = motor['structural_analysis']['safety_factor_total']
        assert details['case']['factor_of_safety'] == pytest.approx(expected)
        assert details['case']['factor_of_safety'] != 2.5

        chamber = motor['structural_analysis']['chamber_analysis']
        # Gerilmelerin ait olduğu kalınlık: doğrulama modunda kullanıcının
        # cidarı, boyutlandırma modunda yapısal önerinin kendisi.
        beklenen_mm = (chamber['wall_thickness_used_mm']
                       if chamber.get('design_mode') == 'verify'
                       else chamber['recommended_thickness'])
        eslesme = re.match(r'\s*([\d.]+)\s*mm\s*$', details['case']['thickness'])
        assert eslesme, (
            'kasa kalınlığı sayı+birim biçiminde değil: '
            f"{details['case']['thickness']!r}")
        okunan_mm = float(eslesme.group(1))
        assert okunan_mm == pytest.approx(beklenen_mm, abs=0.005), (
            f'kasa özeti {okunan_mm:.2f} mm diyor, yapısal analiz '
            f'{beklenen_mm:.4f} mm')
        assert details['case']['thickness_source'].startswith(
            'structural analysis')

    def test_liquid_component_details_have_no_fixed_defaults(self):
        """Veri yoksa 24 kanal / Inconel 718 sabitleri DÖNMEMELİ."""
        details = DetailedCADGenerator()._get_component_details({'thrust': 5000})
        assert details['cooling']['channel_count'] == NOT_AVAILABLE_SPEC
        assert details['injector']['hole_count'] == NOT_AVAILABLE_SPEC
        assert details['materials']['chamber'] == NOT_AVAILABLE_SPEC

    def test_liquid_component_details_read_solver_values(self):
        payload = {
            'thrust': 10000, 'isp': 300, 'chamber_pressure': 50,
            'cooling_type': 'regenerative', 'fuel_type': 'rp1',
            'cooling_system': {'cooling_channels': 80},
            'injector_design': {'injector_type': 'unlike_impinging',
                                'number_of_elements': 96,
                                'injection_pressure_drop_fuel_bar': 12.5},
        }
        details = DetailedCADGenerator()._get_component_details(payload)
        assert details['cooling']['channel_count'] == 80
        assert details['injector']['hole_count'] == 96
        assert '12.50 bar' == details['injector']['pressure_drop']


# ---------------------------------------------------------------------------
# (g) PDF "Minimum Safety Factor (verified stations)" satırı
# ---------------------------------------------------------------------------

#: Gerçek yapısal koşumun girdisi (Ø100 mm / 400 mm oda, Pc 40 bar,
#: Ø30 mm boğaz, 3 kN itki, steel_4130, tasarım SF hedefi 2,0).
#: İtki BİLEREK verilir: ``_check_buckling`` eksenel basma kuvvetini
#: oradan alır; kuvvet olmadan burkulma SF'si ``inf`` çıkar ve
#: P9B3-01'in kanalı hiç kurulmaz.
SF_MOTOR_GIRDISI = {
    'chamber_pressure': 40.0,      # bar
    'chamber_diameter': 0.100,     # m
    'chamber_length': 0.400,       # m
    'throat_diameter': 0.030,      # m
    'burn_time': 8.0,
    'nozzle_type': 'conical',
    'thrust': 3000.0,              # N
}

SF_SATIRI = 'Minimum Safety Factor (verified stations)'


def _yapisal_kosum(**kwargs):
    """Gerçek ``StructuralAnalyzer`` koşumu — elle yazılmış sözlük yok."""
    from hrma.analysis.structural_analysis import StructuralAnalyzer
    return _silent(StructuralAnalyzer().analyze_structure,
                   SF_MOTOR_GIRDISI, material='steel_4130',
                   design_safety_factor=2.0, **kwargs)


@pytest.fixture(scope='module')
def sf_kosumlari():
    """Üç tasarım tabanı, üçü de GERÇEK analiz koşumu.

    ÖH B-1/B14 (defter P14M1-12/-13). ``pdf_generator.py:838`` ve
    ``:841-845`` bugüne kadar bekçi kümesinde HİÇ ÇALIŞMIYORDU: 270 PDF
    testinin hiçbiri en az bir istasyonu doğrulanmış bir yapısal sonuç
    üretmiyordu. Bu fikstür o satırları çalıştıran girdileri kurar.

      * ``oda_dogrulandi``        -> kullanıcı GERÇEK oda cidarı verdi.
        Bu ÜRÜNÜN CANLI YOLUDUR (``app.py:7310`` ``actual_wall_thickness``):
        oda bloğunun iki istasyonu (hoop, von Mises) doğrulanır, lüle ve
        kapak hedefe boyutlandırılır.
      * ``istasyonlar_dogrulandi`` -> oda boyutlandırılır (bir blok, iki
        istasyon), lüle ve kapak gerçek kalınlıkla doğrulanır (iki
        istasyon). DÜRÜST NOT: ``analyze_structure`` bu iki argümanı
        (``actual_throat_thickness`` / ``actual_end_cap_thickness``)
        destekler ama bugün DEPODA HİÇBİR ÜRÜN ÇAĞRISI onları geçmiyor
        (``grep`` = 0). Yani bu taban modülün genel sözleşmesini sınar,
        bugünkü uç davranışını değil; kardeşi ``oda_dogrulandi`` canlı
        yolu kapsar.
      * ``hepsi_boyutlandirildi``  -> hiç doğrulama yok; rapor bu durumda
        SAYI YERİNE tasarım hedefini yazmalıdır.
    """
    return {
        'oda_dogrulandi': _yapisal_kosum(actual_wall_thickness=0.005),
        'istasyonlar_dogrulandi': _yapisal_kosum(
            actual_throat_thickness=0.0035, actual_end_cap_thickness=0.006),
        'hepsi_boyutlandirildi': _yapisal_kosum(),
    }


def _dogrulanmis_istasyonlar(structural_raw):
    """Kazanılmış (totolojik OLMAYAN) istasyon -> emniyet katsayısı.

    Türetim BAĞIMSIZDIR: rapor katmanının ``_structural_design_basis``
    çözümünü değil, analizörün istasyon başına yayımladığı
    ``safety_factor_is_tautological`` bayraklarını okur. İki yol aynı
    sayıda buluşmak zorundadır; buluşmuyorlarsa biri yanlıştır.
    """
    safety = structural_raw['safety_analysis']
    taut = safety['safety_factor_is_tautological']
    return {ad: float(sf) for ad, sf in safety['safety_factors'].items()
            if not taut.get(ad, True) and math.isfinite(float(sf))}


def _sf_pdf_metni(structural_raw):
    """Yapısal sonucu app.py'nin PDF besleyicisiyle AYNI biçimde geçirir."""
    safety = structural_raw['safety_analysis']
    chamber = structural_raw['chamber_analysis']
    motor_data = {
        'motor_name': 'SF_VERIFIED_MIN',
        'chamber_diameter': 100.0, 'chamber_length': 400.0,
        'throat_diameter': 30.0, 'exit_diameter': 90.0,
        'structural_analysis': structural_raw,
    }
    analysis_results = {'structural': {
        'safety_factor_pressure': chamber.get('hoop_safety_factor'),
        'safety_factor_total': chamber.get('von_mises_safety_factor'),
        'min_safety_factor': safety.get('minimum_safety_factor'),
        'von_mises_stress_MPa': chamber.get('von_mises_stress'),
        'hoop_stress_MPa': chamber.get('hoop_stress'),
        'status': safety.get('status'),
        'risk_level': safety.get('risk_level'),
    }}
    return TestPdfDimensions._pdf_text(motor_data, analysis_results)


class TestPdfVerifiedMinimumSafetyFactor:
    """``pdf_generator.py:838/841-845`` — doğrulanmış minimum SF satırı."""

    @pytest.mark.parametrize('taban', ['oda_dogrulandi',
                                       'istasyonlar_dogrulandi'])
    def test_verified_minimum_row_reports_the_minimum(self, sf_kosumlari,
                                                      taban):
        """Satır basılır ve basılan sayı doğrulanmış istasyonların MİNİMUMU.

        ÖH B-1/B14 (defter P14M1-12/-13). Mutasyonla ölçüldü: ``min`` ->
        ``max`` çevrildiğinde 0 test kırmızıya döndü (rapor "Minimum SF"
        satırına MAKSİMUMU yazıyordu) ve aynı değer 2× bozulduğunda 270 PDF
        testi yeşil kaldı — çünkü bekçi kümesinde bu satır hiç basılmıyordu.
        """
        ham = sf_kosumlari[taban]
        dogrulanmis = _dogrulanmis_istasyonlar(ham)
        assert len(dogrulanmis) >= 2, (
            f'fikstür {len(dogrulanmis)} doğrulanmış istasyon üretti — '
            'minimum ile maksimumu ayırmak için en az iki tane gerek')
        beklenen = min(dogrulanmis.values())
        en_buyuk = max(dogrulanmis.values())
        assert beklenen != pytest.approx(en_buyuk, rel=1e-3), (
            f'fikstür körü: doğrulanmış istasyonların hepsi {beklenen} — '
            'min/max mutasyonu bu girdiyle ölçülemez')

        # İkinci, bağımsız kanal: analizörün kendi kazanılmış-minimumu.
        assert ham['safety_analysis']['minimum_earned_safety_factor'] == \
            pytest.approx(beklenen, rel=1e-12)

        metin = _sf_pdf_metni(ham)
        assert SF_SATIRI in metin, (
            f'{taban}: rapor doğrulanmış minimum satırını hiç basmadı')
        basilan = TestPdfDimensions._value_after(metin, SF_SATIRI)
        assert basilan == f'{beklenen:.2f}', (
            f'{taban}: rapor {basilan!r} bastı; doğrulanmış istasyonların '
            f'minimumu {beklenen:.4f} (istasyonlar: '
            f'{sorted(dogrulanmis.items())})')
        # Maksimum yazılsaydı da "bir sayı" görünürdü — ayrımı burada kilitle.
        assert basilan != f'{en_buyuk:.2f}'

    def test_sized_stations_are_excluded_and_declared(self, sf_kosumlari):
        """Hedefe boyutlandırılmış istasyon minimuma GİRMEZ ve adı yazılır.

        ÖH B-1/B14. Boyutlandırma modunda istasyonun emniyet katsayısı
        kullanıcının kendi hedefinin geri okunmasıdır (2,00); minimuma
        karışırsa rapor "doğrulanmış minimum" adı altında bir GİRDİYİ
        yayımlar.
        """
        ham = sf_kosumlari['istasyonlar_dogrulandi']
        safety = ham['safety_analysis']
        taut = safety['safety_factor_is_tautological']
        boyutlandirilmis = {ad: float(sf)
                            for ad, sf in safety['safety_factors'].items()
                            if taut.get(ad, True) and math.isfinite(float(sf))}
        assert boyutlandirilmis, 'fikstür hiç boyutlandırılmış istasyon üretmedi'

        metin = _sf_pdf_metni(ham)
        basilan = TestPdfDimensions._value_after(metin, SF_SATIRI)
        for ad, sf in boyutlandirilmis.items():
            assert basilan != f'{sf:.2f}', (
                f'boyutlandırılmış istasyon {ad} ({sf:.2f}) doğrulanmış '
                'minimum diye basılmış')
        assert 'EXCLUDED from the minimum above' in metin
        assert 'Chamber wall' in metin, (
            'hangi istasyonun hedefe boyutlandırıldığı yazılmamış')

    # Z2 onarımı (2026-08-27): buckling 'kaynağı bilinmiyor -> doğrulanmış
    # say' dalı kapandı, istasyon-başına bayrak okunuyor -> im XPASS ile düştü.
    def test_buckling_is_not_reported_as_a_verified_minimum(self, sf_kosumlari):
        """Kazanılmış istasyon YOKSA doğrulanmış minimum satırı BASILMAZ."""
        ham = sf_kosumlari['hepsi_boyutlandirildi']
        assert _dogrulanmis_istasyonlar(ham) == {}, (
            'fikstür kurulumu bozuk: bu tabanda hiç kazanılmış istasyon olmamalı'
        )
        assert ham['safety_analysis']['minimum_earned_safety_factor'] is None

        metin = _sf_pdf_metni(ham)
        assert SF_SATIRI not in metin, (
            'ortada doğrulanmış emniyet payı yokken rapor bir "doğrulanmış '
            'minimum" sayısı bastı: '
            f'{TestPdfDimensions._value_after(metin, SF_SATIRI)!r} '
            f"(burkulma SF = {ham['safety_analysis']['safety_factors'].get('buckling_axial')})")

    # Z2 onarımı (2026-08-27): verified_min artık istasyon-başına bayrakla
    # kuruluyor -> SIZING-mode dürüstlük uyarısı gerçek motorlarda ERİŞİLİR
    # oldu (OH-B1-04 kapanışı) -> im XPASS ile düştü.
    def test_sizing_mode_declares_the_design_target_instead_of_a_number(
            self, sf_kosumlari):
        """Doğrulama yokken rapor tasarım HEDEFİNİ ve gerekçesini yazmalı."""
        metin = _sf_pdf_metni(sf_kosumlari['hepsi_boyutlandirildi'])
        assert 'SIZING mode' in metin
        assert 'no verified safety margin' in metin.lower()
