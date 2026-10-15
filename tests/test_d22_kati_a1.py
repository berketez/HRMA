"""ÖH Dalga-22 / kati aşama-1 bekçileri.

Üç kalem, üç kusur, üç bekçi:

* **P9B2-02** — katı rotasının ``structural_analysis`` bloğu
  ``end_cap_analysis`` YAYIMLAMIYORDU, bu yüzden imalata giden STEP'in baş
  kapağı üreteç sabiti 8,00 mm'de kilitliydi (Ø100/40 bar çelik, aynı motor
  6 mm cidarla ve alüminyum kasayla da 8,00 mm). Basınç sınırının cidarla
  eşit derecede kritik ikinci parçası hiçbir analizden gelmiyordu.
* **P12bB2-09** — tasarım noktası hedefi bir ORTALAMA itkidir; blok tepe
  itkiyi hiç yayımlamıyordu. Tepe/ortalama oranı tane ailesine göre 1,00 ile
  3,92 arasında değişiyor, yani "3000 N motor" isteyen kullanıcı wagon_wheel
  tanesinde ~11,8 kN tepe alıyor ve tasarım noktası bunu söylemiyordu.
* **P6B4-08** — ``hrma/stability/bands.py`` + ``hrma/stability/fuel_thermal.py``
  (915 satır künyeli tablo) ürün kodundan HİÇ çağrılmıyordu;
  ``combustion_response_band`` yalnız testlerden atanıyordu ve katı motorun
  QSHOD bloğu her koşuda ``NOT_EVALUATED`` dönüyordu.

Ölçüm kanıtı: ``docs/scofield/raw/OH/D22/kati/a1/{once,sonra}.json``.
"""

import io
import contextlib

import pytest

from hrma.engines.solid_rocket_engine import SolidRocketEngine


#: ``SolidRocketEngine.__init__`` imzasındaki alanlar — geri kalanı
#: ``overrides`` sözlüğüne gider (kullanıcı isteğinin taşındığı kanal).
_KURUCU_ALANLARI = ('grain_type', 'propellant_type', 'chamber_diameter',
                    'grain_length', 'core_diameter', 'chamber_pressure')


def _motor(**ov):
    """Ölçüm gövdesi: Ø100 / 500 / 30 mm, 40 bar, APCP (once.json ile aynı)."""
    kurucu = {k: ov.pop(k) for k in list(ov) if k in _KURUCU_ALANLARI}
    return SolidRocketEngine(overrides=dict(ov), **kurucu)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


# ---------------------------------------------------------------------------
# P9B2-02 — kapak analizden gelir
# ---------------------------------------------------------------------------
class TestP9B202KapakAnalizden:
    """Baş kapağı üreteç sabiti değil, yapısal analiz boyutlandırır."""

    def test_kati_structural_analysis_end_cap_analysis_yayimlar(self):
        """Anahtar VAR ve düz kapak kalınlığı taşıyor.

        Taban davranışı (once.json K2): ``structural_analysis`` üç anahtar
        taşıyordu — ``case_analysis``, ``grain_structural``,
        ``assembly_integrity``. ``end_cap_analysis`` yoktu.
        """
        sa = _sessiz(_motor()._calculate_structural_analysis)
        assert 'end_cap_analysis' in sa, sorted(sa)
        cap = sa['end_cap_analysis']
        assert cap['status'] == 'modelled', cap
        assert cap['flat_head_thickness'] > 0
        assert cap['head_thickness_used_mm'] > 0
        assert cap['recommended_type'] in ('flat', 'dished')
        assert cap['head_safety_factor'] > 0

    def test_kapak_kalinligi_basinca_duyarli(self):
        """Kapak basınçla ÖLÇEKLENİR — sabit bir sayı olamaz.

        Düz plaka eğilmesinde t ~ sqrt(P); 40 -> 160 bar'da kalınlık iki
        katına yaklaşmalıdır. Üreteç sabiti (8,00 mm) bu sınavı geçemez.
        """
        ince = _sessiz(_motor(chamber_pressure=40.0)
                       ._calculate_structural_analysis)['end_cap_analysis']
        kalin = _sessiz(_motor(chamber_pressure=160.0)
                        ._calculate_structural_analysis)['end_cap_analysis']
        assert kalin['flat_head_thickness'] > ince['flat_head_thickness']
        oran = kalin['flat_head_thickness'] / ince['flat_head_thickness']
        assert oran == pytest.approx(2.0, rel=0.02), oran

    def test_kapak_malzemeye_duyarli(self):
        """Kullanıcının kasa malzemesi kapağa DA işler.

        Taban davranışı: çelik ve alüminyum kasada çizilen kapak birebir
        8,00 mm'ydi.
        """
        celik = _sessiz(_motor()._calculate_structural_analysis
                        )['end_cap_analysis']
        alu = _sessiz(_motor(case_material='aluminum_6061')
                      ._calculate_structural_analysis)['end_cap_analysis']
        assert celik['flat_head_thickness'] != alu['flat_head_thickness']
        assert alu['poisson_ratio'] != celik['poisson_ratio']

    def test_poisson_yoksa_kapak_uydurulmaz(self):
        """FAIL-CLOSED: Poisson oranı olmayan malzemede kalınlık ÜRETİLMEZ."""
        cap = _sessiz(_motor(case_material='composite')
                      ._calculate_structural_analysis)['end_cap_analysis']
        assert cap['status'] == 'NOT_EVALUATED', cap
        assert 'flat_head_thickness' not in cap
        assert any('poisson' in m.lower() for m in cap['missing_inputs'])

    def test_ihrac_katmani_kapagi_artik_analizden_okuyor(self):
        """Zincirin ucu: ``_front_cap_design`` üreteç kuralına DÜŞMÜYOR.

        Taban (once.json K2): üç ayrı tasarımda da ``thickness_mm = 8.0``,
        ``from_analysis = False`` ve imalat kapısı (``require_analysis``)
        çıktıyı REDDEDİYORDU.
        """
        from hrma.export.cad_visualization import _front_cap_design

        motor = _motor()
        sonuc = _sessiz(motor.calculate_performance)
        kap = _front_cap_design(sonuc, wall_mm=2.4, bore_radius_mm=50.0)
        assert kap['from_analysis'] is True, kap['source']
        assert kap['thickness_mm'] == pytest.approx(
            sonuc['structural_analysis']['end_cap_analysis'][
                'flat_head_thickness'])
        assert kap['thickness_mm'] != pytest.approx(8.0)
        kapi = _front_cap_design(sonuc, wall_mm=2.4, bore_radius_mm=50.0,
                                 require_analysis=True)
        assert kapi['thickness_mm'] is not None


# ---------------------------------------------------------------------------
# P12bB2-09 — tasarım noktası tepe itkiyi söyler
# ---------------------------------------------------------------------------
class TestP12bB209TepeItki:
    """Ortalama hedefin yanında TEPE de yayımlanır."""

    def test_tasarim_noktasi_tepe_itki_yayimlar(self):
        motor = _motor(thrust=3000.0, burn_time=3.0)
        sonuc = _sessiz(motor.calculate_performance)
        dp = sonuc['design_point']
        assert dp['requested_average_thrust_N'] == pytest.approx(3000.0)
        assert dp['achieved_peak_thrust_N'] is not None
        assert dp['achieved_peak_thrust_N'] > 0
        assert dp['achieved_peak_to_average_ratio'] == pytest.approx(
            dp['achieved_peak_thrust_N'] / dp['achieved_average_thrust_N'])
        assert 'peak' in dp['peak_thrust_basis'].lower()

    def test_tasarim_noktasi_tepesi_yayimlanan_max_thrust_ile_ayni(self):
        """İki adres AYNI eğriden gelir; çelişemezler."""
        motor = _motor(thrust=3000.0, burn_time=3.0)
        sonuc = _sessiz(motor.calculate_performance)
        assert sonuc['design_point']['achieved_peak_thrust_N'] == \
            pytest.approx(sonuc['max_thrust'], rel=1e-12)

    @pytest.mark.parametrize('tane,alt_sinir', [
        ('end_burner', 1.0),
        ('star', 1.5),
        ('wagon_wheel', 2.5),
    ])
    def test_ozet_tepe_ortalama_orani_tane_ailesine_duyarli(self, tane,
                                                            alt_sinir):
        """Oran ADIYLA yayımlanır ve tane ailesiyle GERÇEKTEN değişir."""
        sonuc = _sessiz(_motor(grain_type=tane).calculate_performance)
        perf = sonuc['design_summary']['performance']
        oran = perf['peak_to_average_thrust_ratio']
        assert oran is not None
        assert oran >= alt_sinir, (tane, oran)
        assert oran == pytest.approx(
            perf['peak_thrust_N'] / perf['average_thrust_N'])

    def test_measure_curve_uc_deger_dondurur(self):
        """Boyutlandırma çevrimi tepeyi eğriden okur (ek koşum YOK)."""
        ort, sure, tepe = _sessiz(_motor()._measure_curve)
        assert tepe >= ort > 0
        assert sure > 0


# ---------------------------------------------------------------------------
# P6B4-08 — bant ve termal tablo ürüne bağlı
# ---------------------------------------------------------------------------
class TestP6B408BantTuketicisi:
    """915 satırlık künyeli tablonun ürün tüketicisi VAR."""

    def test_apcp_bandi_katalogdan_cozuluyor(self):
        band, kunye = _motor()._qshod_band_from_catalog()
        assert band is not None
        assert kunye['status'] == 'resolved'
        assert kunye['matched_key'] == 'apcp'
        assert kunye['record']['record_id'] == 'cy1990_worked_example'
        # Sınıf eşleşme beyanı kaybolmadan taşınır.
        assert 'NEAREST CLASS' in kunye['mapping_basis']

    def test_pban_bandi_sinif_uyusmazligi_beyaniyla_geliyor(self):
        band, kunye = _motor(propellant_type='pban')._qshod_band_from_catalog()
        assert band is not None
        assert kunye['record']['record_id'] == 'a13_ap_pban'
        assert 'CLASS MISMATCH' in kunye['mapping_basis']

    @pytest.mark.parametrize('yakit', ['kndx', 'knsu'])
    def test_kaynagi_olmayan_yakitta_bant_UYDURULMAZ(self, yakit):
        """FAIL-CLOSED: boş satır beyanıyla döner, sayı icat edilmez."""
        band, kunye = _motor(
            propellant_type=yakit)._qshod_band_from_catalog()
        assert band is None
        assert kunye['status'] == 'declared_empty'
        assert kunye['missing_record']['status'] == 'not_found'
        assert len(kunye['missing_record']['reason']) > 40

    def test_termal_yayinirlik_beyanli_eksik(self):
        """κ uydurulmaz; eksik alanın KENDİ gerekçesi yayımlanır."""
        kappa, kunye = _motor()._propellant_thermal_diffusivity()
        assert kappa is None
        assert kunye['status'] == 'declared_missing'
        assert set(kunye['missing_properties']) == {'specific_heat',
                                                    'thermal_conductivity'}
        assert kunye['record']['specific_heat']['status'] == 'not_found'

    def test_qshod_blogu_bant_kunyesini_urun_yuzune_tasiyor(self):
        """Ürün yanıtında bandın kaydı ve termal tablonun beyanı GÖRÜNÜR."""
        sonuc = _sessiz(_motor().calculate_performance)
        blok = sonuc['combustion_stability']['qshod_response_band']
        assert blok['status'] == 'NOT_EVALUATED'
        # Taban: iki anahtar da eksikti. Artık yalnız κ eksik.
        assert blok['missing_inputs'] == ['propellant_thermal_diffusivity_m2_s']
        assert blok['band_source']['status'] == 'resolved'
        assert blok['thermal_diffusivity_source']['status'] == \
            'declared_missing'

    def test_kappa_verilince_qshod_tam_degerlendiriliyor(self):
        """Bant artık ürün kodundan geldiği için tek anahtar yetiyor.

        Taban davranışı: bandı ürün kodu HİÇ atamadığı için yalnız κ vermek
        bloğu değerlendirmeye YETMİYORDU.
        """
        motor = _motor()
        motor.propellant_thermal_diffusivity_m2_s = 1.0e-7
        sonuc = _sessiz(motor.calculate_performance)
        blok = sonuc['combustion_stability']['qshod_response_band']
        assert blok['status'] == 'modelled', blok.get('missing_inputs')
        assert blok['band_source']['status'] == 'resolved'
        assert blok['thermal_diffusivity_source']['status'] == \
            'caller_supplied'
        assert len(blok['modes']) > 0
        for satir in blok['modes']:
            assert satir['response_real_min'] is not None
