# -*- coding: utf-8 -*-
"""ÖH Dalga-19 · hibrit kulvarı · aşama 1 bekçileri.

Kapsanan kalemler:

  B3-12  Reaktan elemental kütlesi 1'e kapanmıyordu (HTPB +%0,1852) ve aynı
         dosyada HTPB için ÜÇ molekül ağırlığı yazılıydı (54,09 / 54,0 /
         54,0; formülün kendi atom kütleleriyle 54,092). Onarım: molekül
         ağırlığı _REACTANT_FORMULAS + _ATOMIC_MASS'tan TÜRETİLİYOR.

  B3-11  _calculate_thermodynamic_properties ve _calculate_performance_
         parameters içindeki beş ölü blok (ölçüldü: 0 çalışan satır, hem
         Cantera açık hem kapalı) uydurma sabitler ve ULAŞILAMAZ bir
         garanti taşıyordu. Onarım: ölü kollar silindi, yerlerine eksik
         alanı adıyla söyleyen fail-closed ret kondu.

  B2-08  (D18 onarımının artığı) _feed_water_hammer_block'un docstring'i ve
         'reason' metni, D18'de not_modelled beyanından kaldırılan
         "çözülen tek besleme öğesi enjektör orifis planıdır" cümlesinin
         bir kopyasını taşıyordu ve o kopya ürün yanıtına giriyordu.

  D18 DEVRİ (B1-13, B2-07, P15B2-09, OH-Z1-06): bu dalgada YENİ/açık
  görünen ama D18'de onarılıp tabana inen kalemlerin onarımının hâlâ
  yerinde durduğunu ölçen çapa bekçileri.

Ölçüm betiği ve ham sayılar:
    docs/scofield/raw/OH/D19/hibrit/a1/olcum.py, once.json, sonra.json
"""
import contextlib
import io
import math
import os
import sys

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from hrma.engines.combustion_analysis import (  # noqa: E402
    CombustionAnalyzer)

CA_YOL = os.path.join(KOK, 'hrma', 'engines', 'combustion_analysis.py')
HY_YOL = os.path.join(KOK, 'hrma', 'engines', 'hybrid_rocket_engine.py')

CA_REAKTAN_YAKITLARI_D19 = ['htpb', 'paraffin', 'pe', 'pmma', 'abs', 'pla', 'aluminum']
CA_REAKTAN_OKSITLERI_D19 = ['n2o', 'lox', 'h2o2', 'air']


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def analizci():
    return _sessiz(CombustionAnalyzer)


# ---------------------------------------------------------------- B3-12
class TestB312ElementalKutleKorunumu:
    """Elemental ayrıştırma kütleyi korumak ZORUNDA (Σ = 1)."""

    @pytest.mark.parametrize('yakit', CA_REAKTAN_YAKITLARI_D19)
    def test_saf_yakit_kutle_kesirleri_bire_kapaniyor(self, analizci, yakit):
        # of_ratio=0 -> yakıt kütle kesri 1,0, oksitleyici payı 0
        el = analizci._calculate_elemental_composition({yakit: 100.0},
                                                       'lox', 0.0)
        toplam = sum(el.values())
        # ÖNCE (taban 60cd341): htpb 1,001851851851852 / pe 1,000356506 /
        # paraffin 1,000293548 / pla 1,000138773 / pmma 1,000099880 /
        # abs 1,000096015. SONRA: hepsi 1,0.
        assert toplam == pytest.approx(1.0, abs=1e-12), (
            f'{yakit}: elemental kütle 1e kapanmıyor -> {toplam!r}')

    @pytest.mark.parametrize('oks', CA_REAKTAN_OKSITLERI_D19)
    def test_saf_oksitleyici_kutle_kesirleri_bire_kapaniyor(self, analizci,
                                                            oks):
        # Yakıt payını ihmal edilebilir kılmak için çok büyük O/F
        el = analizci._calculate_elemental_composition({'aluminum': 100.0},
                                                       oks, 1e9)
        toplam = sum(el.values())
        # ÖNCE: n2o 1,000227221 / h2o2 1,000294031 / air 1,000274402.
        assert toplam == pytest.approx(1.0, abs=1e-9), (
            f'{oks}: elemental kütle 1e kapanmıyor -> {toplam!r}')

    @pytest.mark.parametrize('yakit,oks', [
        ('htpb', 'n2o'), ('htpb', 'lox'), ('paraffin', 'n2o'),
        ('pla', 'lox'), ('pmma', 'h2o2'), ('abs', 'air'),
    ])
    def test_karisim_kutlesi_korunuyor(self, analizci, yakit, oks):
        el = analizci._calculate_elemental_composition({yakit: 100.0},
                                                       oks, 6.0)
        assert sum(el.values()) == pytest.approx(1.0, abs=1e-9)

    def test_kullanicinin_of_orani_dengeye_aynen_giriyor(self, analizci):
        """A7 sınıfı: girdi yankısı çözülen değeri söylemeli."""
        istenen = 6.0
        el = analizci._calculate_elemental_composition({'htpb': 100.0},
                                                       'n2o', istenen)
        yakit_payi = el['C'] + el['H']
        oks_payi = sum(el.values()) - yakit_payi
        efektif = oks_payi / yakit_payi
        # ÖNCE: 5,990270233491716 (−%0,1622). SONRA: 6,0.
        assert efektif == pytest.approx(istenen, rel=1e-12)

    def test_htpb_tek_molekul_agirligi(self, analizci):
        """Aynı dosyada HTPB için ÜÇ ağırlık yazılıydı; artık TEK."""
        turetilen = analizci._formula_molar_mass('htpb')
        assert turetilen == pytest.approx(
            4 * analizci._ATOMIC_MASS['C'] + 6 * analizci._ATOMIC_MASS['H'],
            rel=0, abs=0)
        assert analizci.propellant_specs['htpb']['molecular_weight'] == \
            turetilen
        assert analizci.species_data['HTPB']['MW'] == turetilen
        # ÖNCE üç ayrı değer vardı: 54,09 / 54,0 / 54,0
        assert turetilen == pytest.approx(54.092, abs=1e-9)

    def test_elle_yazili_bolenler_kaynakta_kalmadi(self):
        """Elemental/stokiyometri bölenleri artık türetiliyor."""
        kaynak = open(CA_YOL, encoding='utf-8').read()
        for elle in ["4 * 12.01 / 54.0", "6 * 1.01 / 54.0",
                     "12 * 12.01 / 170.33", "(5.5 * 32.0) / 54.0",
                     "(18.5 * 32.0) / 170.33", "2 * 14.01 / 44.01"]:
            assert elle not in kaynak, (
                f'elle yazılmış bölen hâlâ kaynakta: {elle}')

    def test_n2o_turetimi_yayimlanan_agirlikla_ayni(self, analizci):
        """Tablonun IUPAC tutarlılığı: türetilen N2O = 44,013 (spec değeri)."""
        assert analizci._formula_molar_mass('n2o') == pytest.approx(
            analizci.propellant_specs['n2o']['molecular_weight'], abs=1e-12)

    # Tam yanma stokiyometrisinin BAĞIMSIZ tablosu (kimya; üründen
    # okunmaz). CxHyOz + n_O2 O2 -> x CO2 + (y/2) H2O  =>  n_O2 = x+y/4-z/2.
    # Metalik alüminyum: 2 Al + 1,5 O2 -> Al2O3  =>  Al başına 0,75.
    _N_O2 = {'paraffin': 18.5, 'htpb': 5.5, 'abs': 10.0, 'pla': 3.0,
             'pe': 3.0, 'pmma': 6.0, 'aluminum': 0.75}

    def test_stokiyometrik_o2_katsayilari_formulden_turetiliyor(self,
                                                               analizci):
        """ÜRÜN fonksiyonu bağımsız stokiyometriyle birebir tutmalı.

        ÖH D25 (Fable-D19 ŞART, kalem B3-12): bu test TOTOLOJİKTİ — n_O2'yi
        ``_REACTANT_FORMULAS``'tan kendisi yeniden türetiyor, ürün
        fonksiyonunu HİÇ ÇAĞIRMIYORDU. Ölçüldü (a2/once.json K5, AST ile):
        ``urun_fonksiyonu_cagriliyor = false``; ürün kodunda n_O2'nin
        H/4 -> H/2 mutasyonunda test 1 passed veriyordu (kusuru yalnız
        başka dosyadaki F45 ER çapası görüyordu).

        Artık ölçülen şey ÜRÜNÜN ÇIKTISIDIR:
            _calculate_stoichiometric_of({yakıt: 100}, oks)
                == n_O2 · M_O2 / (M_yakıt · Y_O2,oks)
        Beklenen taraf tamamen bu dosyada kurulur: n_O2 yukarıdaki kimya
        tablosundan, molekül ağırlıkları ``_ATOMIC_MASS``'tan doğrudan
        (``_formula_molar_mass`` ÇAĞRILMAZ — o da denetlenen taraftadır).
        Oksitleyicinin kullanılabilir oksijen kütle kesri:
            lox/gox/o2  1,0                    (saf O2)
            n2o         M_O / M_N2O            (N2O -> N2 + 1/2 O2)
            h2o2        M_O2 / (2·M_H2O2)      (2 H2O2 -> 2 H2O + O2)
        """
        am = analizci._ATOMIC_MASS
        m_o2 = 2.0 * am['O']
        oksitleyiciler = {
            'lox': 1.0,
            'n2o': am['O'] / (2.0 * am['N'] + am['O']),
            'h2o2': m_o2 / (2.0 * (2.0 * am['H'] + 2.0 * am['O'])),
        }

        for yakit, n_o2 in self._N_O2.items():
            formul = analizci._REACTANT_FORMULAS[yakit]

            # (a) formül ⟷ bağımsız kimya tablosu (n_O2'nin kendisi)
            if formul.get('AL'):
                formulden = 0.75 * formul['AL']
            else:
                formulden = (formul.get('C', 0) + formul.get('H', 0) / 4.0
                             - formul.get('O', 0) / 2.0)
            assert formulden == pytest.approx(n_o2, abs=1e-12), yakit

            # (b) ÜRÜN ÇIKTISI ⟷ bağımsız kurulan beklenen O/F
            m_yakit = sum(am[el] * n for el, n in formul.items())
            for oks, y_o2 in oksitleyiciler.items():
                beklenen = n_o2 * m_o2 / (m_yakit * y_o2)
                gercek = float(analizci._calculate_stoichiometric_of(
                    {yakit: 100.0}, oks))
                assert gercek == pytest.approx(beklenen, abs=1e-12), (
                    f'{yakit}|{oks}: ürün {gercek!r} ⟷ beklenen {beklenen!r}')


# ---------------------------------------------------------------- B3-11
class TestB311OluKolYok:
    """Ölü fallback kollar ve ULAŞILAMAZ garanti kaynakta kalmadı."""

    def test_yanlis_garanti_cumlesi_kalkti(self):
        kaynak = open(CA_YOL, encoding='utf-8').read()
        # B3-06 bu garantiyi ölçümle çürütmüştü (1,195914 <-> 1,25)
        assert kaynak.count(
            "Böylece akış zincirindeki tüm fallback'ler TEK gamma "
            "kullanır") == 0

    def test_uydurma_termo_varsayilanlari_kalkti(self):
        kaynak = open(CA_YOL, encoding='utf-8').read()
        for uydurma in ['MW_fallback = 30.0', 'gamma_local = 1.25',
                        's0_molar.get(species, 200.0)',
                        'return 25.0  # Default MW',
                        'return 25.0  # Veri yoksa']:
            assert uydurma not in kaynak, (
                f'ölü kolun uydurma sabiti hâlâ kaynakta: {uydurma}')

    def test_olu_yardimci_silindi(self):
        kaynak = open(CA_YOL, encoding='utf-8').read()
        # Ad yalnız onarım künyesinde geçebilir; TANIM ve ÇAĞRI kalkmalı
        assert 'def _species_mass_fractions' not in kaynak
        assert '_species_mass_fractions(composition)' not in kaynak

    def test_entalpi_alani_yoksa_adiyla_reddediliyor(self, analizci):
        with pytest.raises(ValueError) as e:
            analizci._calculate_thermodynamic_properties(
                {'species': {}}, {'species': {}}, {'species': {}},
                3000.0, 2800.0, 1500.0, 20.0, 11.0, 1.0)
        assert 'enthalpy' in str(e.value)

    def test_termo_alani_yoksa_adiyla_reddediliyor(self, analizci):
        eksik = {'species': {'CO2': {'mass_fraction': 1.0}},
                 'enthalpy': -1.0e6, 'entropy': 8.0e3}
        with pytest.raises(ValueError) as e:
            analizci._calculate_thermodynamic_properties(
                eksik, eksik, eksik, 3000.0, 2800.0, 1500.0,
                20.0, 11.0, 1.0)
        metin = str(e.value)
        # Eksik alanlar ADIYLA sayılmalı; sayı uydurulmamalı
        for alan in ('cp', 'cv', 'gamma', 'molecular_weight'):
            assert alan in metin
        assert 'chamber' in metin

    def test_molekul_agirligi_yoksa_adiyla_reddediliyor(self, analizci):
        with pytest.raises(ValueError) as e:
            analizci._calculate_performance_parameters(
                {'species': {}}, {'species': {}}, {'species': {}},
                20.0, 11.0, 1.0, 3000.0, 2800.0, 1500.0)
        assert 'molecular_weight' in str(e.value)

    def test_urun_yolu_hala_calisiyor(self, analizci):
        """Ret kapısı gerçek çözümü kesmiyor (kollar ölçülmüş biçimde ölüydü)."""
        r = _sessiz(analizci.analyze_combustion, {'htpb': 100.0}, 'n2o',
                    6.0, 20.0, expansion_ratio=8.0)
        istasyon = (r['performance']['thermodynamic_properties']
                    ['stations']['chamber'])
        assert istasyon['gamma'] > 1.0
        assert istasyon['molecular_weight'] > 10.0
        # Emekli fallback'in uydurma değerleri yayımlanmıyor
        assert istasyon['gamma'] != pytest.approx(1.25, abs=1e-12)
        assert istasyon['molecular_weight'] != pytest.approx(30.0, abs=1e-12)


# ---------------------------------------------------------------- B2-08
class TestB208SuKocuBeyanArtigi:
    """D18'de kaldırılan yalan cümlenin kardeş blokta kalan kopyası."""

    def test_eski_cumle_dosyada_hic_kalmadi(self):
        kaynak = open(HY_YOL, encoding='utf-8').read()
        assert kaynak.count(
            'the only feed element solved is the injector') == 0

    def test_su_kocu_gerekcesi_cozuleni_adiyla_aniyor(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        m = _sessiz(HybridRocketEngine, thrust=3000, burn_time=10,
                    of_ratio=6.0, chamber_pressure=20.0, fuel_type='htpb',
                    oxidizer_type='n2o', feed_line_length_m=1.5,
                    feed_line_inner_diameter_mm=12.0)
        blok = m._feed_water_hammer_block()
        gerekce = blok['reason']
        assert 'lumped inertance' in gerekce
        assert 'chug loop' in gerekce
        # Kalan yokluk iddiası (HESAPLANAN hat geometrisi yok) korunuyor
        assert 'no wave speed' in gerekce
        assert blok['status'] == 'NOT_MODELLED'


# ------------------------------------------------------------ D18 DEVRİ
class TestD18OnarimlariYerindeDuruyor:
    """D18'de onarılıp tabana inen dört kalemin çapası."""

    def test_b1_13_kapi_yakit_adina_degil_katsayiya_bakiyor(self):
        kaynak = open(HY_YOL, encoding='utf-8').read()
        assert "fuel_key in ('htpb', 'abs')" not in kaynak
        assert 'htpb_katsayisi_yururlukte' in kaynak

    @pytest.mark.parametrize('yakit,bekleniyor', [
        ('htpb', True), ('abs', True), ('pla', False), ('pe', False)])
    def test_b1_13_uyari_katsayiyi_izliyor(self, yakit, bekleniyor):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        m = _sessiz(HybridRocketEngine, thrust=1000, burn_time=10,
                    of_ratio=6.0, chamber_pressure=20.0, fuel_type=yakit,
                    oxidizer_type='n2o')
        _sessiz(m.calculate)
        kodlar = [w.get('code') for w in m.design_warnings]
        assert ('warn.hybrid.htpb_coeff_bias' in kodlar) is bekleniyor

    @pytest.mark.parametrize('n_port', [1, 2, 4, 7])
    def test_b2_07_yanma_yuzeyi_port_sayisini_goruyor(self, n_port):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        m = _sessiz(HybridRocketEngine, thrust=3000, burn_time=10,
                    of_ratio=6.0, chamber_pressure=20.0, fuel_type='htpb',
                    oxidizer_type='n2o', port_count=n_port)
        r = _sessiz(m.calculate)
        blok = r['combustion_stability']['acoustic_response_threshold']
        fiziksel = n_port * math.pi * m.D_port_initial * m.L_grain
        assert blok['burning_surface_area_m2'] == pytest.approx(
            fiziksel, rel=1e-12)
        assert 'port_count' in blok['burning_surface_basis']

    def test_p15b2_09_kapak_birlesimi_tek_kaynaktan(self):
        from hrma.analysis.bolted_joint import CLOSURE_JOINT_DEFAULTS
        from hrma.engines.hybrid_rocket_engine import (
            CLOSURE_JOINT_DEFAULTS as HY)
        for anahtar, deger in CLOSURE_JOINT_DEFAULTS.items():
            assert HY[anahtar] == deger, anahtar

    def test_oh_z1_06_basinc_yogunluga_girmiyor(self):
        from hrma.data.external_data_fetcher import data_fetcher
        yog = set()
        for p in (1.0, 30.0, 60.0, 200.0, 1e6):
            pr = _sessiz(data_fetcher.fetch_nist_oxidizer_properties,
                         'n2o', temperature=293.15, pressure=p)
            yog.add(round(float(pr['density']), 9))
        assert len(yog) == 1, f'basınç yoğunluğu değiştiriyor: {yog}'
        kaynak = open(HY_YOL, encoding='utf-8').read()
        assert 'P_kunye_bar' in kaynak
        assert 'doygunluk basıncının üzerinde' not in kaynak
