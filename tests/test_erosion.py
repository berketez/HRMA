"""Boğaz erozyonu doğrulama testleri (Dalga 3).

Kapsam:
  1. ThroatErosionModel birim testleri — el hesabı çapaları:
       ṙ = a_ref·(Pc/70 bar)^0.8
     Grafit varsayılanı a_ref = 0.25 mm/s (bandın konservatif üst ucu;
     Geisler bandı 0.05-0.25 mm/s). 35 bar'da beklenen:
       0.25 · (35/70)^0.8 = 0.25 · 0.5743 = 0.14359 mm/s

     D19/P2B4-09 (2026-09-03): bu el hesapları 2026-09-03'e kadar 0.15
     mm/s ile yazılmıştı. 0.15 ATFEDİLMEMİŞ bir sayıydı — kaydın kendi
     künyesi (ve modül başlığı) bandı 0.05-0.25 diyordu, yani "bandın
     konservatif üst ucu" etiketi kaydın kendi kaynağına göre YANLIŞTI
     ve varsayılan erozyonu eksik tahmin ediyordu. Bant künyesine çekildi,
     varsayılan artık bandın üst ucundan TÜRETİLİYOR; el hesapları da
     ona göre yenilendi (formül ve üs DEĞİŞMEDİ).
  2. Transient kuplaj — erozyon AÇIK: d_t monoton artar, Pc ve F baseline'a
     göre düşer; daha agresif a_ref daha çok erozyon → daha düşük Pc.
  3. Geriye dönük uyum — erozyon KAPALI (varsayılan): boğaz çapı sabit,
     yarı-kararlı kimlik Pc·Cd·At_tasarım = ṁ·c* her adımda tutar,
     varsayılan çağrı ile erosion_enabled=False çağrısı bit-özdeş sonuç verir.
  4. SolidRocketEngine nozul tasarımı: eski sabit '0.001 mm/s' metni yerine
     ampirik modelden hesaplanan değer (40 bar varsayılanında el hesabı:
     0.15·(40/70)^0.8 = 0.15·0.63906 = 0.09586 mm/s).
"""

import math

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.engines.solid_rocket_engine import SolidRocketEngine
from hrma.analysis import transient_ballistics as tb
from hrma.analysis.transient_ballistics import (
    TransientBallistics, ThroatErosionModel, THROAT_EROSION_MATERIALS)
from hrma.data.materials_db import get_material


# ---------------------------------------------------------------------------
# Model birim testleri
# ---------------------------------------------------------------------------

class TestThroatErosionModel:
    def test_graphite_reference_rate_at_70_bar(self):
        """El hesabı: Pc = Pc_ref → ṙ = a_ref (yasa, sayı değil).

        ÖH D27/OH-D25-27: burada 0.25 mm/s ELLE yazılıydı; band
        literatüre çapalanınca (0.069-0.353, Geisler JANNAF 1978 / Thakre
        & Yang 2008 Tablo 8) bu literal ikinci bir tanım noktası olarak
        kırmızıya döndü. Sayının tek tanım noktası künyedir; bu bekçi
        artık YASAYI kilitliyor: referans basınçta hız katsayının kendisi
        olmalı. Bandın sayısal değerinin bağımsız transkripsiyonu
        tests/test_d19_kati_a1.py::TestGrafitBandiKunyesiyleCelismez'de.
        """
        m = ThroatErosionModel.for_material('graphite')
        assert m.rate_mm_s(m.pc_ref_bar) == pytest.approx(
            m.a_ref_mm_s, rel=1e-12)
        assert m.a_ref_mm_s == pytest.approx(
            THROAT_EROSION_MATERIALS['graphite']['a_ref_band_mm_s'][1],
            rel=1e-12)

    def test_pressure_scaling_exponent(self):
        """El hesabı: Pc_ref/2 → a_ref·(0.5)^n, n = künyeden okunan üs.

        ÇEVRİLDİ (ÖH D28 / OH-D27-15). Bu bekçi üssü '0.8' diye ELLE
        yazıyor ve gerekçesini "Bartz" diye veriyordu; tam da onarılan
        kusuru (erozyon yasasının üssünün ısı-transferi korelasyonuna
        atfedilmesini) KİLİTLİYORDU. Bekçi kaldırılmadı, YÖNÜ çevrildi:
        sayı artık künyeden gelir (``_exponent_from_citation`` ile
        BAĞIMSIZ olarak yeniden ayrıştırılır) ve yasanın gerçekten bir
        kuvvet yasası olduğu iki basınçtan geri çözülerek çakılır.
        """
        m = ThroatErosionModel.for_material('graphite')
        n_kunye, _ = tb._exponent_from_citation(
            tb.THROAT_EROSION_PRESSURE_EXPONENT_CITATION)
        assert n_kunye == pytest.approx(tb.THROAT_EROSION_PRESSURE_EXPONENT,
                                        rel=1e-12)
        yari = m.pc_ref_bar / 2.0
        assert m.rate_mm_s(yari) == pytest.approx(
            m.a_ref_mm_s * 0.5 ** n_kunye, rel=1e-12)
        # Üssün kendisi de bağımsız çakılır: iki basınç oranından geri
        # çözülen üs künyenin üssü olmalı (sayı katsayıdan bağımsız).
        us = math.log(m.rate_mm_s(yari) / m.rate_mm_s(m.pc_ref_bar)) \
            / math.log(0.5)
        assert us == pytest.approx(n_kunye, rel=1e-9)
        # MEKANİZMA BANDI (ilişki bekçisi): taşınım ucu 0,8 (Bartz/Chilton-
        # Colburn), kinetik ucu 1,0 (birinci mertebe, p_i = X_i·Pc). Üs bu
        # bandın dışına çıkarsa iki uçtan hiçbiriyle açıklanamaz.
        assert 0.8 <= n_kunye <= 1.0

    def test_unit_conversion_m_s(self):
        """rate_m_s(Pa) = rate_mm_s(bar)/1000 aynı basınçta."""
        m = ThroatErosionModel.for_material('graphite')
        assert m.rate_m_s(m.pc_ref_bar * 1e5) == pytest.approx(
            m.a_ref_mm_s * 1e-3, rel=1e-12)

    def test_zero_or_negative_pressure_gives_zero(self):
        m = ThroatErosionModel.for_material('graphite')
        assert m.rate_mm_s(0.0) == 0.0
        assert m.rate_mm_s(-5.0) == 0.0

    def test_default_is_conservative_band_upper_end(self):
        """Varsayılan a_ref bandın ÜST (konservatif) ucudur.

        D19/P2B4-09 NOTU: bu iddia artık YAPISAL olarak doğrudur
        (a_ref_default_mm_s elle yazılmıyor, bandın üst ucundan
        türetiliyor), yani bu test bir DEĞİŞMEZİ belgeliyor, kusur
        yakalamıyor. Kusuru yakalayan bekçi
        tests/test_d19_kati_a1.py::TestGrafitBandiKunyesiyleCelismez'dir
        (bandın kendi künyesindeki sayılarla çaprazı).

        ÖH D27/OH-D24-11 (b): kural GENELLEŞTİ — bandı olmayan ama
        atfedilmiş TEK ölçüm noktası olan malzemede (C-C) varsayılan o
        çapadan gelir. İki dal da burada çakılır.
        """
        for key, rec in THROAT_EROSION_MATERIALS.items():
            band = rec.get('a_ref_band_mm_s')
            capa = rec.get('a_ref_anchor_mm_s')
            if band:
                assert rec['a_ref_default_mm_s'] == band[1], key
            elif capa:
                assert rec['a_ref_default_mm_s'] == capa, key
            else:
                assert rec['a_ref_default_mm_s'] is None, key

    def test_carbon_carbon_katsayisi_atfedilmis_tek_noktadan_gelir(self):
        """C-C katsayısı ÖLÇÜME çapalıdır ve BAND yayımlamaz.

        ÖH D27/OH-D24-11 (b). Bu testin eski hâli
        (``test_carbon_carbon_lower_than_graphite``) "C-C bulk grafitten
        daha yavaş erozyona uğrar (Thakre & Yang)" iddiasını kilitliyordu.
        ÖLÇÜLDÜ (docs/arastirma/fizik/bogaz-erozyonu-grafit-cc-bandi.md
        §4): o iddiayı DESTEKLEYEN sayı yoktur — karşılaştırılabilir
        alüminyum yüklemesinde atfedilen tek C-C noktası (Borie ve ark.,
        6,9 MPa'ya taşınmış 0,183 mm/s) Geisler'in aynı Al sınıfındaki
        bulk grafitinden (0,069-0,124 mm/s) YÜKSEKTİR. İki farklı deneyin
        karşılaştırılması kesin bir çürütme değildir, ama kanıtsız bir
        sıralamayı bekçiyle KİLİTLEMEK de meşru değildir. Yeni bekçi
        gerçekten doğrulanabilir olanı çakar.
        """
        cc = ThroatErosionModel.for_material('carbon_carbon')
        rec = THROAT_EROSION_MATERIALS['carbon_carbon']
        # (1) Yayımlanmış BAND yok → bant-dışı denetiminin dayanağı yok.
        assert rec['a_ref_band_mm_s'] is None
        assert cc.a_ref_band_mm_s is None
        assert cc.band_attributed is False and cc.band_source is None
        # (2) Ama katsayı kaynaksız DEĞİL: tek ölçüm noktasına çapalı.
        assert cc.anchor_attributed is True
        assert cc.anchor_source and 'Borie' in cc.anchor_source
        # (3) Çapa künyeden okunur: sayı künyesinden ayrılamaz.
        assert cc.a_ref_mm_s == pytest.approx(
            rec['a_ref_anchor_mm_s'], rel=1e-12)

    def test_steel_and_copper_not_recommended(self):
        """Soğutmasız çelik/bakır: a_ref verilmeden model kurulamaz."""
        for mat in ('steel', 'copper'):
            with pytest.raises(ValueError, match='NOT RECOMMENDED'):
                ThroatErosionModel.for_material(mat)

    def test_steel_with_explicit_coefficient_carries_warning(self):
        """Test-verisi a_ref'iyle zorlanırsa model kurulur ama uyarı taşır."""
        m = ThroatErosionModel.for_material('steel', a_ref_mm_s=0.3)
        assert m.a_ref_mm_s == pytest.approx(0.3)
        assert any('NOT RECOMMENDED' in w for w in m.warnings)

    def test_material_aliases(self):
        assert ThroatErosionModel.for_material('C-C').material == 'carbon_carbon'
        with pytest.raises(ValueError, match='NOT RECOMMENDED'):
            ThroatErosionModel.for_material('ss_304')  # → steel

    def test_unknown_material_rejected(self):
        with pytest.raises(ValueError, match='No throat erosion data'):
            ThroatErosionModel.for_material('unobtainium')

    def test_invalid_coefficient_rejected(self):
        with pytest.raises(ValueError):
            ThroatErosionModel(a_ref_mm_s=0.0)
        with pytest.raises(ValueError):
            ThroatErosionModel(a_ref_mm_s=-1.0)

    def test_display_name_from_central_materials_db(self):
        """Görünen ad merkezi materials_db kaydından gelir (tek kaynak)."""
        m = ThroatErosionModel.for_material('graphite')
        assert m.material_display == get_material('graphite')['name']

    def test_describe_is_json_friendly(self):
        d = ThroatErosionModel.for_material('graphite').describe()
        for key in ('model', 'a_ref_mm_s', 'pc_ref_bar', 'exponent',
                    'material', 'a_ref_band_mm_s', 'source', 'warnings'):
            assert key in d
        assert d['source']  # kaynak atfı boş olamaz
        # ÇEVRİLDİ (ÖH D28 / OH-D27-15): üs elle '0.8' yazılıydı; tek tanım
        # noktası artık künyedir (n = 1,0, Thakre & Yang 2008). Bekçi sayıyı
        # değil ÜRÜNLE TEK TANIM NOKTASININ AYRIŞMAMASINI kilitler.
        assert d['exponent'] == pytest.approx(
            tb.THROAT_EROSION_PRESSURE_EXPONENT)
        # Üssün künyesi de yayımlanmalı (D28: eskiden hiç yoktu).
        assert d['exponent_attributed'] is True
        assert 'Thakre' in d['exponent_source']
        assert d['exponent_valid_pc_bar'] == [69.0, 450.0]


# ---------------------------------------------------------------------------
# Transient kuplaj testleri
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def engine():
    """3 kN N₂O/parafin, 20 bar (test_transient_ballistics ile aynı vaka)."""
    e = HybridRocketEngine(
        thrust=3000, burn_time=10, of_ratio=7.96,
        chamber_pressure=20, atmospheric_pressure=1.01325,
        fuel_type='paraffin', oxidizer_type='n2o',
        fuel_density=900, regression_a=1.17e-4, regression_n=0.62,
        l_star=1.0, expansion_ratio=0, nozzle_type='conical')
    e.calculate()
    return e


@pytest.fixture(scope='module')
def baseline(engine):
    """Erozyon KAPALI (varsayılan) referans çözüm."""
    return TransientBallistics(engine, feed_mode='regulated').solve()


@pytest.fixture(scope='module')
def eroded(engine):
    """Erozyon AÇIK (grafit, varsayılan konservatif a_ref) çözüm."""
    return TransientBallistics(
        engine, feed_mode='regulated',
        erosion_enabled=True, throat_material='graphite').solve()


class TestErosionCoupling:
    def test_throat_diameter_monotonically_increases(self, eroded):
        d = eroded['throat_diameter']
        assert len(d) > 10
        assert np.all(np.diff(d) > 0)

    def test_first_step_matches_baseline(self, baseline, eroded):
        """Erozyon kayıttan SONRA uygulanır → ilk adım baseline ile özdeş."""
        assert eroded['chamber_pressure'][0] == pytest.approx(
            baseline['chamber_pressure'][0], rel=1e-9)
        assert eroded['thrust'][0] == pytest.approx(
            baseline['thrust'][0], rel=1e-9)

    def test_pc_drops_below_baseline(self, baseline, eroded):
        """Büyüyen boğaz: Pc = ṁ·c*/(Cd·At) her adımda baseline'ın altında."""
        n = min(len(baseline['chamber_pressure']),
                len(eroded['chamber_pressure']))
        assert n > 20
        pcb = baseline['chamber_pressure'][10:n]
        pce = eroded['chamber_pressure'][10:n]
        assert np.all(pce < pcb)
        # Yanma sonunda fark belirgin olmalı (≈%5-7 alan büyümesi sınıfı)
        assert pce[-1] < 0.995 * pcb[-1]

    def test_thrust_drops_below_baseline(self, baseline, eroded):
        n = min(len(baseline['thrust']), len(eroded['thrust']))
        assert eroded['thrust'][n - 1] < baseline['thrust'][n - 1]

    def test_erosion_report_fields(self, eroded):
        ero = eroded['erosion']
        assert ero['enabled'] is True
        assert ero['total_recession_mm'] > 0.0
        assert (ero['final_throat_diameter_mm']
                > ero['initial_throat_diameter_mm'])
        assert ero['model']['material'] == 'graphite'
        # Kayıtlı diziyle tutarlılık: son ilerletme kayıttan sonra olabilir,
        # rapor edilen toplam gerileme dizidekinden küçük olamaz.
        d = eroded['throat_diameter']
        rec_from_array = (d[-1] - d[0]) / 2.0 * 1000.0
        assert ero['total_recession_mm'] >= rec_from_array - 1e-12

    def test_recession_magnitude_hand_check(self, eroded):
        """El hesabı bandı: ṙ(20 bar) = a_ref·(20/Pc_ref)^0.8.

        Pc yanma boyunca 20 bar civarından aşağı süründüğünden toplam
        gerileme ≈ ṙ·t_yanma'nın biraz altında kalmalı ama aynı mertebede
        olmalı. ÖH D27: katsayı burada ELLE yazılıydı (0.25); band
        literatüre çapalanınca üst sınır kaydı ve bekçi kırmızıya döndü.
        Artık aynı modelin katsayısından türetiliyor (tek tanım noktası).
        """
        _g = ThroatErosionModel.for_material('graphite')
        r_design = _g.a_ref_mm_s * (20.0 / _g.pc_ref_bar) ** _g.exponent
        t_burn = eroded['burn_duration']
        upper = r_design * t_burn                     # sabit-Pc üst sınırı
        rec = eroded['erosion']['total_recession_mm']
        assert 0.5 * upper < rec <= upper * 1.001

    def test_more_aggressive_model_erodes_more(self, engine, eroded):
        """Model-değiştirilebilir API: özel a_ref → daha düşük Pc sonu."""
        hot = TransientBallistics(
            engine, feed_mode='regulated',
            erosion_model=ThroatErosionModel(
                a_ref_mm_s=1.2 * ThroatErosionModel.for_material(
                    'graphite').a_ref_mm_s,
                material='custom_hot')).solve()
        assert hot['erosion']['enabled'] is True
        assert (hot['erosion']['total_recession_mm']
                > eroded['erosion']['total_recession_mm'])
        n = min(len(hot['chamber_pressure']), len(eroded['chamber_pressure']))
        assert (hot['chamber_pressure'][n - 1]
                < eroded['chamber_pressure'][n - 1])


class TestBackwardCompatibility:
    """Erozyon KAPALIYKEN eski davranış aynen korunmalı (424 test sözü)."""

    def test_disabled_by_default(self, baseline):
        assert baseline['erosion']['enabled'] is False
        assert baseline['erosion']['total_recession_mm'] == 0.0

    def test_throat_constant_and_equals_design(self, engine, baseline):
        d = baseline['throat_diameter']
        d_design = 2.0 * np.sqrt(float(engine.At) / np.pi)
        assert np.all(d == d[0])
        assert d[0] == pytest.approx(d_design, rel=1e-12)

    def test_quasi_steady_identity_with_design_throat(self, engine, baseline):
        """Pc·Cd·At_tasarım = ṁ·c* her adımda → At hiç sürüklenmemiş."""
        for i in range(0, len(baseline['time']), 40):
            mdot = baseline['mdot_ox'][i] + baseline['mdot_fuel'][i]
            cstar, _ = engine._instantaneous_performance(
                baseline['of_ratio'][i])
            lhs = baseline['chamber_pressure'][i] * 0.98 * engine.At
            assert lhs == pytest.approx(mdot * cstar, rel=0.02)

    def test_default_call_identical_to_explicit_false(self, engine, baseline):
        """Varsayılan çağrı ile erosion_enabled=False bit-özdeş olmalı."""
        res = TransientBallistics(
            engine, feed_mode='regulated', erosion_enabled=False).solve()
        assert np.array_equal(res['chamber_pressure'],
                              baseline['chamber_pressure'])
        assert np.array_equal(res['thrust'], baseline['thrust'])
        assert np.array_equal(res['port_diameter'],
                              baseline['port_diameter'])
        assert res['end_event'] == baseline['end_event']

    def test_design_point_anchor_preserved(self, engine, baseline):
        """t=0 tasarım noktası çapası (mevcut test paketiyle aynı tolerans)."""
        assert baseline['chamber_pressure'][0] == pytest.approx(
            engine.P_c * 1e5, rel=0.08)


# ---------------------------------------------------------------------------
# SolidRocketEngine nozul erozyon alanı
# ---------------------------------------------------------------------------

class TestSolidEngineErosionField:
    """Nozul tasarım bloğunun erozyon alanı — ÇÖZÜCÜYE BAĞLI mı? (ÖH B6)

    Defter P2B1-03 / P2B3-03: bu blok bir erozyon hızı YAYIMLIYOR ama
    hız çözücünün fiilen uyguladığı erozyondan değil, sabit bir grafit
    varsayımından geliyor (``solid_rocket_engine.py:6242``:
    ``ThroatErosionModel.for_material('graphite')``). Kullanıcının
    ``erosion_factor`` katsayısı ve ``nozzle_material`` seçimi bu sayıyı
    HİÇ kımıldatmıyor — hâlbuki aynı motorun kardeş bloğu
    (``_nozzle_erosion_reference``) kullanıcının malzemesini okuyor ve
    çözücü (``_throat_erosion_model``) kullanıcının katsayısını.

    Eski bekçi tam da bu kusuru kilitliyordu: ``est['material'] ==
    'graphite'`` iddiası, kullanıcı ne seçerse seçsin doğru kalır.
    """

    @staticmethod
    def _tahmin(**ov):
        eng = SolidRocketEngine(chamber_pressure=40, overrides=(ov or None))
        return eng, eng._design_nozzle_geometry()['performance']

    def test_placeholder_text_replaced(self):
        eng = SolidRocketEngine()  # varsayılan Pc = 40 bar
        perf = eng._design_nozzle_geometry()['performance']
        assert perf['erosion_rate'] != '0.001 mm/s'
        assert perf['erosion_rate'].endswith('mm/s')
        assert 'erosion_estimate' in perf

    def test_rate_hand_calculation_40_bar(self):
        """El hesabı: a_ref·(40/Pc_ref)^0.8 = a_ref·0.63910.

        Kapalı form ayrıca PAYLAŞILAN modelden de türetilir: yayımlanan
        sayı ile ``ThroatErosionModel``in aynı malzeme/basınçtaki değeri
        birbirinden ayrılamaz (tek tanım noktası — CLAUDE.md k.11).
        ÖH D27: sayısal çapa (0.15978) ELLE yazılıydı; band literatüre
        çapalanınca kırmızıya döndü. Ölçek çarpanı (0.63910) katsayıdan
        bağımsızdır, o yüzden BAĞIMSIZ el hesabı olarak korunuyor.
        """
        eng, perf = self._tahmin()
        est = perf['erosion_estimate']
        _g = ThroatErosionModel.for_material('graphite')
        # ÖH D28 / OH-D27-15: ölçek çarpanı elle '0.63910' ((40/70)^0,8)
        # yazılıydı ve üs künyesine bağlanınca bayatladı. Çarpan hâlâ
        # katsayıdan BAĞIMSIZ hesaplanır, ama üssü tek tanım noktasından
        # alır: (40/70)^1,0 = 0,571429.
        olcek_bagimsiz = (40.0 / _g.pc_ref_bar) ** (
            tb.THROAT_EROSION_PRESSURE_EXPONENT)
        assert est['rate_mm_s'] == pytest.approx(
            _g.a_ref_mm_s * olcek_bagimsiz, abs=2e-4)
        assert est['chamber_pressure_bar'] == pytest.approx(40.0)
        # Yayımlanan hız = paylaşılan modelin AYNI malzeme/basınçtaki hızı
        paylasilan = ThroatErosionModel.for_material(est['material'])
        assert est['rate_mm_s'] == pytest.approx(
            paylasilan.rate_mm_s(est['chamber_pressure_bar']), abs=1e-4)
        # Bant da modelin kendi bandından ölçeklenir (uydurma değil)
        olcek = (est['chamber_pressure_bar']
                 / paylasilan.pc_ref_bar) ** paylasilan.exponent
        assert est['band_mm_s'][0] == pytest.approx(
            paylasilan.a_ref_band_mm_s[0] * olcek, abs=1e-4)
        assert est['band_mm_s'][1] == pytest.approx(
            paylasilan.a_ref_band_mm_s[1] * olcek, abs=1e-4)
        # Varsayılan katsayı bandın üst ucu → tahmin bandın üst ucuna eşit
        assert est['rate_mm_s'] == pytest.approx(est['band_mm_s'][1], abs=1e-3)
        assert est['band_mm_s'][0] < est['band_mm_s'][1]

    # ÖH D26 a2 — BORÇ İMİ KALKTI (P2B3-03 onarıldı). Buradaki
    # xfail(strict) imi kusuru belgeliyordu; kusur giderildi:
    # ``_nozzle_erosion_estimate`` modeli kullanıcının malzemesinden
    # (``_nozzle_erosion_reference``) kurar. ÖLÇÜLDÜ
    # (docs/scofield/raw/OH/D26/kati/a2/{once_taban,sonra}.json):
    # ayırt edici yayımlanan malzeme 1 -> 5, kardeş blokla uyuşan satır
    # 1/3 -> 3/3.
    def test_tahmin_kullanicinin_lule_malzemesini_izler(self):
        """Seçilen lüle malzemesi yayımlanan erozyon tahminini belirlemeli."""
        eng, perf = self._tahmin(nozzle_material='carbon_carbon')
        est = perf['erosion_estimate']
        kardes = eng._nozzle_erosion_reference()
        assert kardes is not None and kardes.material == 'carbon_carbon'
        assert est['material'] == kardes.material, (
            f"kullanıcı '{kardes.material}' seçti, blok "
            f"'{est['material']}' yayımlıyor")
        assert est['rate_mm_s'] == pytest.approx(
            kardes.rate_mm_s(est['chamber_pressure_bar']), abs=1e-4)

    # ÖH D26 a2 — BORÇ İMİ KALKTI (P2B1-03 onarıldı). Yayımlanan tahmin
    # artık çözücünün taktığı modelin (``_throat_erosion_model``) aynı
    # a_ref'ini kullanır. ÖLÇÜLDÜ: erosion_factor yok / 0,001 / 0,05 / 0,15
    # için ayırt edici yayımlanan hız 1/4 -> 4/4; katsayıyı izleyen satır
    # 0/3 -> 3/3.
    @pytest.mark.parametrize('a_ref', (0.05, 0.10))
    def test_tahmin_kullanicinin_erozyon_katsayisini_izler(self, a_ref):
        """Katsayı değişince yayımlanan hız da değişmeli (ölü alan değil)."""
        eng, perf = self._tahmin(erosion_factor=a_ref)
        est = perf['erosion_estimate']
        model = eng._throat_erosion_model()
        assert model is not None and model.a_ref_mm_s == pytest.approx(a_ref)
        assert est['rate_mm_s'] == pytest.approx(
            model.rate_mm_s(est['chamber_pressure_bar']), abs=1e-4), (
            f'çözücü a_ref={a_ref} mm/s ile koşuyor, tasarım bloğu '
            f"{est['rate_mm_s']} mm/s yayımlıyor")

    def test_rate_scales_with_chamber_pressure(self):
        est_40 = SolidRocketEngine(chamber_pressure=40) \
            ._design_nozzle_geometry()['performance']['erosion_estimate']
        est_70 = SolidRocketEngine(chamber_pressure=70) \
            ._design_nozzle_geometry()['performance']['erosion_estimate']
        assert est_70['rate_mm_s'] > est_40['rate_mm_s']
        # ÖH D27: 0.25 literali kalktı — referans basınçta yayımlanan hız
        # modelin katsayısının KENDİSİDİR (tek tanım noktası künye).
        assert est_70['rate_mm_s'] == pytest.approx(
            ThroatErosionModel.for_material('graphite').a_ref_mm_s, abs=1e-3)

    def test_source_and_note_present(self):
        est = SolidRocketEngine() \
            ._design_nozzle_geometry()['performance']['erosion_estimate']
        assert est['source']
        assert 'approximate' in est['note'].lower() or \
               'Empirical' in est['note']


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
