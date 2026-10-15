"""ÖH Dalga-23 · ihracat · aşama 2/2 — bekçiler.

Her sınıf tek bir defter kalemine bağlıdır; her iddia ters-mutasyonla
kırmızıya çevrildiği ölçülerek yazılmıştır
(``docs/scofield/raw/OH/D23/ihracat/a2/mutasyon.json``).
"""
import json
import math

import pytest

from hrma.export.motor_geometry import solid_results_to_motor_geometry
from hrma.export.openrocket_integration import OpenRocketExporter
from hrma.export.pdf_generator import (
    IDENTITY_NOT_SUPPLIED, PDFReportGenerator, SOLVER_IDENTITY_ALIASES,
    resolve_report_identity)
from tests.bagimlilik_kapisi import kurulu_mu

#: STEP üreten düğümlerin kapısı. CI'ın ana ``pytest`` işi build123d'yi
#: BİLEREK kurmaz; bu düğümler orada atlanır, ``step-export`` işinde koşar.
#: Kurulum sorusu find_spec ile sorulur (``tests/bagimlilik_kapisi.py``):
#: ``step_export.BUILD123D_AVAILABLE`` ``except Exception`` ile kurulduğu
#: için "kurulu değil" gerekçesine dayanak olamaz
#: (``test_ci_kapsam_kapisi.py::TestAtlamaGerekcesiDurust``).
_STEP_GEREKLI = pytest.mark.skipif(
    not kurulu_mu('build123d'),
    reason='build123d kurulu değil (STEP üretimi atlanır)')


# Katı çözücünün GERÇEKTEN yayımladığı şekilde bir sonuç (mm tabanlı,
# zaman-çözümlü eğriyle). Sayılar bu dosyada TEK yerde durur.
KATI_SONUC = {
    'motor_name': 'D23TEST',
    'chamber_diameter': 100.0, 'chamber_length': 500.0,
    'throat_diameter': 20.0, 'exit_diameter': 60.0,
    'grain_length': 450.0, 'core_diameter': 30.0,
    'burn_time': 2.5, 'average_thrust': 800.0,
    'total_impulse': 2000.0, 'specific_impulse': 180.0,
    'chamber_pressure': 40.0, 'expansion_ratio': 9.0,
    'propellant_mass': 1.2,
    'design_summary': {'masses': {'propellant_mass_kg': 1.2}},
    'thrust_curve': {'time': [0.0, 0.5, 1.0, 1.8, 2.5],
                     'thrust': [900.0, 880.0, 820.0, 640.0, 0.0]},
}


# ===========================================================================
# P15B4-06 — dönüştürücü ÜRETEÇ VARSAYILANI ÜRETMEZ
# ===========================================================================
class TestP15B4_06_UydurmaYok:
    """Çözücü hiçbir şey yayımlamadıysa geometri sözlüğü de sayı yayımlamaz.

    ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json``):
    ``solid_results_to_motor_geometry({})`` -> 18 anahtar, **14 sayı**
    (kamara Ø100 mm, çekirdek Ø30 mm, boğaz Ø20 mm, çıkış Ø60 mm, tane
    500 mm, genleşme 9,0, basınç 40 bar), künye alanı **0**. Bu sayılar
    ``step_export``in fail-closed kapısından ÖNCE enjekte edildiği için kapı
    ('refusing to emit a manufacturing STEP built from generator defaults')
    hiç ateşlenemiyordu.
    """

    def test_bos_sozluk_hicbir_olcu_uretmez(self):
        g = solid_results_to_motor_geometry({})
        sayilar = {k: v for k, v in g.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)}
        assert sayilar == {}, (
            'çözücü hiçbir şey yayımlamadığı hâlde geometri sözlüğü sayı '
            f'üretti: {sayilar}')

    def test_cozulemeyen_alan_ADIYLA_beyan_edilir(self):
        g = solid_results_to_motor_geometry({})
        beyan = g.get('geometry_unresolved')
        assert isinstance(beyan, dict) and beyan, (
            'çözülemeyen alanlar için künye yok — tüketici "alan yoktu" ile '
            '"uydurulmadı" arasını ayıramaz')
        for alan in ('chamber_diameter', 'chamber_length', 'throat_diameter',
                     'exit_diameter', 'grain_length',
                     'port_diameter_initial'):
            assert alan in beyan, f'{alan} çözülemedi ama künyede yok'
            assert 'looked at' in beyan[alan], (
                f'{alan} künyesi NEREYE bakıldığını söylemiyor: '
                f'{beyan[alan]!r}')

    @_STEP_GEREKLI
    def test_imalat_kapisi_artik_atesleniyor(self):
        """step_export'un kendi kapısı 'çözülemedi' hâlini GÖRÜR."""
        from hrma.export import step_export  # düz ithal (P13B1-05: depo-içi importorskip yasak; build123d yoksa modül yine yüklenir, kapı RuntimeError'ı kendi verir)
        g = solid_results_to_motor_geometry({})
        with pytest.raises(step_export.StepExportDataError) as hata:
            step_export.generate_step_assembly(g, motor_type='solid')
        assert 'could not be resolved' in str(hata.value), str(hata.value)

    def test_cozulen_olcu_AYNEN_tasinir(self):
        """Fail-closed, "her şeyi düşür" demek değildir."""
        g = solid_results_to_motor_geometry(KATI_SONUC)
        assert g['chamber_diameter'] == pytest.approx(0.100)
        assert g['chamber_length'] == pytest.approx(0.500)
        assert g['throat_diameter'] == pytest.approx(0.020)
        assert g['exit_diameter'] == pytest.approx(0.060)
        assert g['propellant_mass_total'] == pytest.approx(1.2)
        assert 'geometry_unresolved' not in g


# ===========================================================================
# P15B4-14 — dönüştürülmüş geometri AYNI koşumun bilgisini kaybetmez
# ===========================================================================
class TestP15B4_14_EngSadakati:
    """Aynı motorun ``.eng``i, ham sözlükten de dönüştürülmüşten de aynı
    ÇÖZÜM ZENGİNLİĞİNİ taşımalı.

    ÖLÇÜLDÜ (taban ``ef527ae``): ham sözlük -> zaman-çözümlü eğri
    (``thrust_curve``, 5 nokta); AYNI sözlüğün dönüştürülmüş hâli ->
    ``constant`` (sabit-itki yaklaşımı, 4 nokta). Ayrıca çözücü kamara boyunu
    500 mm derken dönüştürülmüş sözlük 529,4 mm taşıyordu (üst seviye
    ``chamber_length`` kaynak listesinde HİÇ yoktu, değer
    ``grain_length / 0,85`` türetmesinden geliyordu).
    """

    @pytest.fixture(scope='class')
    def ihracatci(self):
        return OpenRocketExporter()

    def test_zaman_cozumlu_egri_donusumden_SAG_cikar(self, ihracatci):
        g = solid_results_to_motor_geometry(KATI_SONUC)
        ham_nokta, ham_kaynak = ihracatci.resolve_thrust_curve(KATI_SONUC)
        don_nokta, don_kaynak = ihracatci.resolve_thrust_curve(g)
        assert ham_kaynak == 'thrust_curve', ham_kaynak
        assert don_kaynak == ham_kaynak, (
            f'ham sözlük {ham_kaynak!r} eğrisi veriyor, dönüştürülmüş sözlük '
            f'{don_kaynak!r}: aynı koşumun "komple paket"i daha az bilgi '
            'taşıyor')
        assert len(don_nokta) == len(ham_nokta) == 5

    def test_kamara_boyu_TURETILMEZ_cozucununki_kullanilir(self):
        g = solid_results_to_motor_geometry(KATI_SONUC)
        assert g['chamber_length'] == pytest.approx(0.500), (
            'çözücü 500 mm yayımlarken dönüştürücü başka bir sayı taşıyor '
            f"({g['chamber_length'] * 1000:.1f} mm)")

    def test_itici_kutlesi_iki_yolda_da_ayni(self, ihracatci):
        g = solid_results_to_motor_geometry(KATI_SONUC)
        assert (ihracatci.resolve_propellant_mass(KATI_SONUC)[0]
                == ihracatci.resolve_propellant_mass(g)[0]
                == pytest.approx(1.2))


# ===========================================================================
# OH-D17-01 — uyarı kaydının KENDİ cümlesi rapora geçer
# ===========================================================================
class TestOHD17_01_UyariFallback:
    """Sözlükte karşılığı olmayan kod, raporda ham anahtar olarak KALMAZ.

    ÖLÇÜLDÜ (taban ``ef527ae``): ``warn.input.solver_owned_output_name``
    kaydı ``fallback`` alanında ölçülmüş cümlesini taşırken PDF satırı yalnız
    kodu + ``field=...; submitted=...; used=None`` dizesini basıyordu.
    """

    KAYIT = {'input_warnings': [{
        'code': 'warn.input.solver_owned_output_name',
        'severity': 'warning',
        'params': {'field': 'exit_velocity', 'submitted': 1200.0,
                   'used': None},
        'fallback': ('exit_velocity is an OUTPUT of the solver; the value '
                     'you submitted was not used.'),
        'source': 'inputs_not_used'}]}

    def test_fallback_cumlesi_satira_girer(self):
        satirlar = PDFReportGenerator._collect_solver_warnings(self.KAYIT, {})
        assert len(satirlar) == 1
        assert len(satirlar[0]) == 5, (
            'uyarı satırı hâlâ 4 alanlı — kaydın cümlesi için yer yok')
        assert 'OUTPUT of the solver' in satirlar[0][4], satirlar[0]

    def test_kanonik_kod_KALIR(self):
        """Cümle koda EK'tir, onun yerine geçmez."""
        satirlar = PDFReportGenerator._collect_solver_warnings(self.KAYIT, {})
        assert satirlar[0][2] == 'warn.input.solver_owned_output_name'

    def test_cumle_UYDURULMAZ(self):
        """``fallback`` yoksa boş kalır; rapor kendi cümlesini yazmaz."""
        yalin = {'input_warnings': [{'code': 'warn.x', 'severity': 'info'}]}
        satirlar = PDFReportGenerator._collect_solver_warnings(yalin, {})
        assert satirlar[0][4] == '', satirlar[0]

    def test_bolum_metninde_cumle_gorunur(self):
        g = PDFReportGenerator()
        parcalar = []
        for eleman in g._create_solver_warnings_section(self.KAYIT,
                                                        self.KAYIT):
            veri = getattr(eleman, '_cellvalues', None) or []
            for satir in veri:
                for hucre in satir:
                    parcalar.append(hucre if isinstance(hucre, str)
                                    else getattr(hucre, 'text', ''))
        assert 'OUTPUT of the solver' in ' '.join(parcalar)


# ===========================================================================
# P17B3-04 — rapor kimliği AYNI koşumun yükünden çözülür
# ===========================================================================
class TestP17B3_04_RaporKimligi:
    """PDF, ürünün BİLDİĞİ itici ve motor kimliğini 'Unknown/N/A' yazmaz.

    ÖLÇÜLDÜ (taban ``ef527ae``): hibrit koşumda kapak
    "**Unknown** Motor Analysis Report", künye "Motor Type: **Unknown**",
    yapılandırma tablosunda oksitleyici/yakıt satırları HİÇ yok — oysa
    ``analysis_results`` ``motor_type='hybrid'``,
    ``inputs.fuel_type='htpb'``, ``inputs.oxidizer_type='N2O'`` taşıyor.
    """

    MOTOR_DATA = {'motor_name': 'HRMA_Motor', 'chamber_pressure': 30.0}
    SONUC = {'motor_type': 'hybrid',
             'inputs': {'fuel_type': 'htpb', 'oxidizer_type': 'N2O'}}

    def _tablo(self, motor_data, sonuc):
        g = PDFReportGenerator()
        metin = []
        for eleman in g._create_motor_configuration(motor_data, sonuc):
            for satir in (getattr(eleman, '_cellvalues', None) or []):
                metin.append([h if isinstance(h, str)
                              else getattr(h, 'text', repr(h))
                              for h in satir])
        return metin

    def test_kimlik_sonuctan_cozulur(self):
        kimlik = resolve_report_identity(self.MOTOR_DATA, self.SONUC)
        assert kimlik['motor_type'][0] == 'hybrid'
        assert kimlik['oxidizer_type'] == ('N2O', 'analysis_results.inputs'
                                                  '.oxidizer_type')
        assert kimlik['fuel_type'][0] == 'htpb'

    def test_kullanici_girdisi_HER_ZAMAN_oncelikli(self):
        kimlik = resolve_report_identity(
            dict(self.MOTOR_DATA, oxidizer_type='LOX'), self.SONUC)
        assert kimlik['oxidizer_type'] == ('LOX', 'motor_data.oxidizer_type')

    def test_kapak_Unknown_YAZMAZ(self):
        g = PDFReportGenerator()
        metin = ' | '.join(
            t for t in (getattr(e, 'text', None)
                        for e in g._create_title_page(
                            self.MOTOR_DATA, 'summary', self.SONUC))
            if isinstance(t, str))
        assert 'Unknown' not in metin, metin[:200]
        assert 'Hybrid Motor Analysis Report' in metin, metin[:200]

    def test_tabloda_oksitleyici_ve_yakit_yazar(self):
        duz = json.dumps(self._tablo(self.MOTOR_DATA, self.SONUC))
        assert 'N2O' in duz and 'htpb' in duz, duz
        assert '"Motor Type", "hybrid"' in duz.replace(', ', ', '), duz

    def test_KIMLIK_YOKSA_uydurulmaz(self):
        """Fail-closed: yükte kimlik yoksa bir motor tipi İDDİA EDİLMEZ."""
        duz = json.dumps(self._tablo({'motor_name': 'X'}, {}))
        assert IDENTITY_NOT_SUPPLIED in duz, duz
        assert 'hybrid' not in duz and 'solid' not in duz, duz

    def test_sayi_kimlik_alanina_SIZMAZ(self):
        """``motor_type: 3`` bir kimlik değildir."""
        kimlik = resolve_report_identity({'motor_type': 3, 'fuel_type': ''},
                                         {'oxidizer_type': 'Unknown'})
        assert kimlik == {}, kimlik

    def test_alias_tablosu_TEK_kaynaktir(self):
        assert set(SOLVER_IDENTITY_ALIASES) == {
            'motor_type', 'propellant_type', 'oxidizer_type', 'fuel_type',
            'grain_type'}


# ===========================================================================
# P14M2-11 — p_cr_external MUTLAK çapaya bağlanır (bant değil)
# ===========================================================================
class TestP14M2_11_KritikDisBasincCapasi:
    """``critical_external_pressure_bar`` için DEĞER çapası.

    ÖLÇÜLDÜ (P14 mutasyon kampanyası, M2-11): ``p_cr_external``i **1000×**
    büyüten mutasyon yakalanmadı, çünkü tek bekçi
    (``test_structural_validation.py:230``) yalnız ``> 0.0`` ve
    ``isfinite`` sınıyordu — 1000× büyük bir sayı da pozitif ve sonludur.

    Bu bekçi sayıyı TEKRAR ETMEZ (CLAUDE.md kural 11): beklenen değer,
    deponun KENDİ malzeme tablosundaki E ve ν'den, ince kabuk dış basınç
    burkulması kapalı formülüyle bağımsız hesaplanır:

        p_cr = E / (4 (1 - ν²)) · (t / r)³

    (Timoshenko & Gere, *Theory of Elastic Stability*, 2. baskı, uzun
    silindirik kabuk; ``structural_analysis._check_buckling`` içindeki
    bağıntının kendisi.)
    """

    @pytest.fixture(scope='class')
    def analiz(self):
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        return StructuralAnalyzer()

    @pytest.mark.parametrize('t_m', (0.001, 0.005, 0.02))
    def test_yayimlanan_deger_kapali_formulle_ORTUSUR(self, analiz, t_m):
        mat = analiz.materials['steel_4130']
        yaricap, boy = 0.5, 2.0
        cikti = analiz._check_buckling(5e5, yaricap, t_m, boy, mat)
        yayimlanan = float(cikti['critical_external_pressure_bar'])

        E = float(mat['elastic_modulus'])
        nu = float(mat.get('poisson_ratio', 0.3))
        beklenen_bar = E / (4.0 * (1.0 - nu ** 2)) * (t_m / yaricap) ** 3 / 1e5

        assert math.isfinite(yayimlanan)
        assert yayimlanan == pytest.approx(beklenen_bar, rel=1e-9), (
            f'yayımlanan {yayimlanan:.6g} bar, malzeme tablosundan '
            f'bağımsız hesaplanan {beklenen_bar:.6g} bar ile örtüşmüyor '
            f'(oran {yayimlanan / beklenen_bar:.4g}×)')

    def test_capa_OLCEK_degisimine_duyarli(self, analiz):
        """Çapanın ×1000'i gördüğünün kanıtı: kübik ölçekleme."""
        mat = analiz.materials['steel_4130']
        ince = analiz._check_buckling(
            5e5, 0.5, 0.001, 2.0, mat)['critical_external_pressure_bar']
        kalin = analiz._check_buckling(
            5e5, 0.5, 0.002, 2.0, mat)['critical_external_pressure_bar']
        assert kalin / ince == pytest.approx(8.0, rel=1e-9), (
            f'kalınlık 2× iken kritik basınç {kalin / ince:.4g}× — kapalı '
            'form kübik olmasını gerektirir')
