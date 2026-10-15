# -*- coding: utf-8 -*-
"""ÖH Dalga-25 · hibrit kulvarı · aşama 2 bekçileri.

Kapsanan kalem
--------------
B3-12 (Fable-D19 ŞART) — "pay tablodan, payda elle".

D19 bu kalemin PAYINI tek kaynağa bağlamıştı: stokiyometrik oksijen
katsayısı n_O2 ve yakıt molekül ağırlığı artık ``_REACTANT_FORMULAS`` +
``_ATOMIC_MASS`` tablosundan türetiliyor. Ama ``_calculate_stoichiometric_of``
içindeki OKSİTLEYİCİ böleni elle yazılı kalmıştı (N2O 0.3636, H2O2 0.4704),
yani aynı kusur küçülmüş biçimde sürüyordu. ÖLÇÜLDÜ (a2/once.json, taban
cdf2106):

    N2O  elle 0,3636 ⟷ M_O/M_N2O        = 0,3635062367936746  (+%0,0258)
    H2O2 elle 0,4704 ⟷ M_O2/(2·M_H2O2)  = 0,4703651437643323  (+%0,0074)
    14 yakıt×oksitleyici çiftinin 14'ü tablodan sapıyordu
    of_stoich(htpb/N2O) 8,948054274480175 -> 8,950362345633366
    yayımlanan ER       1,491342379080029 -> 1,491727057605561

Aynı fonksiyonda İKİNCİ bir kusur ölçüldü (K6): kabul kümesi kardeş
``_calculate_elemental_composition``'dan AYRIŞIYORDU — 7 anahtarda karar
farklı, 4'ünde fiziksel olmayan sayı yayımlanıyordu (yakıt 'n2o' için
of_stoich = −0,3635; 'kerosene' için 0; oksitleyici 'n2o4'/'' için lox ile
birebir aynı 3,2535). İki kol da adıyla reddedecek biçimde kapatıldı.

Bu dosya onarımın KENDİSİNİ değil ÖNCÜLLERİNİ kilitler: oranın tabloyu
gerçekten TAKİP ETTİĞİNİ (atom kütlesi oynatılınca sonucun oynadığını),
çapaların üründen türediğini, D19 bekçisinin totolojiye geri dönemeyeceğini
ve iki fonksiyonun tek kabul kümesini paylaştığını ölçer.

Ölçüm betiği ve ham sayılar:
    docs/scofield/raw/OH/D25/hibrit/a2/{olcum.py,once.json,sonra.json}
"""
import ast
import json
import os
import sys

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from hrma.engines.combustion_analysis import (  # noqa: E402
    SUPPORTED_HYBRID_FUEL_KEYS, CombustionAnalyzer)

CA_YOL = os.path.join(KOK, 'hrma', 'engines', 'combustion_analysis.py')
D19_YOL = os.path.join(KOK, 'tests', 'test_d19_hibrit_a1.py')
F45_YOL = os.path.join(KOK, 'tests', 'test_scofield_analiz.py')
YUK_YOL = os.path.join(KOK, 'tests', 'support', 'uc_yukleri.json')

#: Tam yanma stokiyometrisi — kimyadan, üründen DEĞİL.
N_O2 = {'paraffin': 18.5, 'htpb': 5.5, 'abs': 10.0, 'pla': 3.0,
        'pe': 3.0, 'pmma': 6.0, 'aluminum': 0.75}


@pytest.fixture(scope='module')
def analizci():
    return CombustionAnalyzer()


def _kaynak(yol):
    with open(yol, encoding='utf-8') as fh:
        return fh.read()


def _float_sabitler(yol):
    """Kaynaktaki ÇALIŞAN float sabitleri (yorumlar AST'e girmez)."""
    agac = ast.parse(_kaynak(yol))
    return [d.value for d in ast.walk(agac)
            if isinstance(d, ast.Constant) and isinstance(d.value, float)]


def _test_govdesi(yol, ad):
    for d in ast.walk(ast.parse(_kaynak(yol))):
        if isinstance(d, ast.FunctionDef) and d.name == ad:
            return d
    return None


# --------------------------------------------------------------- ŞART (1)
class TestB312OksitleyiciBoleniTuretiliyor:
    """Oksitleyicinin kullanılabilir oksijen kesri tablodan gelir."""

    def test_calisan_kodda_elle_bolen_kalmadi(self):
        """0.3636 / 0.4704 artık ÇALIŞAN kodda yok (künyede anılabilir).

        Ham dizgi taraması yetmez: onarım künyesi eski sayıyı KAYIT olarak
        anıyor. Ölçüm AST'ten yapılır.
        """
        sabitler = _float_sabitler(CA_YOL)
        assert 0.3636 not in sabitler, 'N2O böleni hâlâ elle yazılı'
        assert 0.4704 not in sabitler, 'H2O2 böleni hâlâ elle yazılı'

    def test_n2o_orani_tablodan_geliyor(self, analizci):
        """of(n2o)/of(lox) = M_N2O/M_O — yalnız türetilmişse birebir tutar."""
        am = analizci._ATOMIC_MASS
        beklenen = (2.0 * am['N'] + am['O']) / am['O']
        for yakit in N_O2:
            lox = float(analizci._calculate_stoichiometric_of(
                {yakit: 100.0}, 'lox'))
            n2o = float(analizci._calculate_stoichiometric_of(
                {yakit: 100.0}, 'n2o'))
            assert n2o / lox == pytest.approx(beklenen, rel=1e-14), yakit

    def test_h2o2_orani_tablodan_geliyor(self, analizci):
        """of(h2o2)/of(lox) = 2·M_H2O2/M_O2  (2 H2O2 -> 2 H2O + O2)."""
        am = analizci._ATOMIC_MASS
        beklenen = (2.0 * (2.0 * am['H'] + 2.0 * am['O'])) / (2.0 * am['O'])
        for yakit in N_O2:
            lox = float(analizci._calculate_stoichiometric_of(
                {yakit: 100.0}, 'lox'))
            h2o2 = float(analizci._calculate_stoichiometric_of(
                {yakit: 100.0}, 'h2o2'))
            assert h2o2 / lox == pytest.approx(beklenen, rel=1e-14), yakit

    def test_atom_kutlesi_degisince_oran_takip_ediyor(self, monkeypatch):
        """ÖNCÜL: sonuç tabloyu GERÇEKTEN takip ediyor mu?

        Elle yazılı bir bölen, atom kütlesi tablosu oynatıldığında
        KIMILDAMAZ. HTPB seçildi çünkü formülünde O yok — yakıt molekül
        ağırlığı sabit kalır, oynayan yalnız oksitleyici bölenidir.
        """
        an = CombustionAnalyzer()
        oncesi = float(an._calculate_stoichiometric_of({'htpb': 100.0}, 'n2o'))

        bozuk = dict(CombustionAnalyzer._ATOMIC_MASS)
        bozuk['O'] = bozuk['O'] * 1.10
        monkeypatch.setattr(CombustionAnalyzer, '_ATOMIC_MASS', bozuk)

        sonrasi = float(an._calculate_stoichiometric_of({'htpb': 100.0},
                                                        'n2o'))
        m_yakit = 4 * bozuk['C'] + 6 * bozuk['H']
        beklenen = (5.5 * (2.0 * bozuk['O'])
                    / (m_yakit * (bozuk['O'] / (2.0 * bozuk['N']
                                                + bozuk['O']))))
        assert sonrasi == pytest.approx(beklenen, rel=1e-14)
        # Elle yazılı bölen bu farkı üretemez.
        assert abs(sonrasi - oncesi) > 1e-6

    def test_yayimlanan_er_of_stoich_ile_tutarli(self, analizci):
        """ER = of_stoich / of — yayımlanan iki yaprak aynı sayıdan gelir."""
        sonuc = analizci.analyze_combustion({'htpb': 100.0}, 'N2O', 6.0, 20.0)
        of_stoich = float(analizci._calculate_stoichiometric_of(
            {'htpb': 100.0}, 'n2o'))
        assert sonuc['equivalence_ratio'] == pytest.approx(
            of_stoich / 6.0, rel=1e-12)

    def test_f45_capasi_turetilmis_deger_ve_tolerans_korundu(self, analizci):
        """Çapa yenilendi ama tolerans GEVŞETİLMEDİ (ÖK-22).

        İlk yazımda tolerans ``'rel=1e-5' in metin`` ile aranıyordu; dosyada
        BAŞKA testlerin de rel=1e-5'i olduğu için M7 mutasyonu (F45'in
        toleransını 1e-2 yapmak) bekçiyi YEŞİL bıraktı. Ölçüm artık AST'ten
        ve YALNIZ F45 iddiasından okunur.
        """
        of_stoich = float(analizci._calculate_stoichiometric_of(
            {'htpb': 100.0}, 'n2o'))
        turetilen = of_stoich / 6.0
        assert turetilen == pytest.approx(1.491727057605561, rel=1e-12)

        govde = _test_govdesi(F45_YOL, 'test_gecerli_of_bit_ozdes_kaldi')
        assert govde is not None, 'F45 çapası kaybolmuş'
        bulunan = []
        for dugum in ast.walk(govde):
            if not isinstance(dugum, ast.Call):
                continue
            hedef = getattr(dugum.func, 'attr', None)
            if hedef != 'approx' or not dugum.args:
                continue
            arg = dugum.args[0]
            if not (isinstance(arg, ast.Constant)
                    and isinstance(arg.value, float)):
                continue
            tol = {kw.arg: getattr(kw.value, 'value', None)
                   for kw in dugum.keywords}
            bulunan.append((arg.value, tol))

        assert bulunan, 'F45 iddiasında pytest.approx bulunamadı'
        capa, tolerans = bulunan[0]
        assert capa == pytest.approx(turetilen, rel=1e-12), (
            f'F45 çapası üründen türemiyor: {capa!r} ⟷ {turetilen!r}')
        assert tolerans.get('rel') == 1e-5, (
            f'F45 toleransı gevşetilmiş: {tolerans!r} (taban rel=1e-5)')
        assert '1.491342379080029' not in _kaynak(F45_YOL), \
            'bayat çapa hâlâ duruyor'

    def test_hasat_yuku_urun_ile_tutarli(self, analizci):
        """uc_yukleri.json'daki hasat yaprakları ürünle aynı sayıyı taşır."""
        with open(YUK_YOL, encoding='utf-8') as fh:
            yukler = json.load(fh)
        motor = yukler['/api/fea/structural']['motor_results']
        of_stoich = float(analizci._calculate_stoichiometric_of(
            {'htpb': 100.0}, 'n2o'))
        assert motor['stoichiometric_of'] == pytest.approx(of_stoich,
                                                           rel=1e-12)
        assert motor['equivalence_ratio'] == pytest.approx(of_stoich / 6.0,
                                                           rel=1e-12)


# --------------------------------------------------------------- ŞART (2)
class TestB312BekciTotolojisiKapandi:
    """D19 bekçisi ürün kodunu çağırmalı, tabloyu yeniden türetmemeli."""

    AD = 'test_stokiyometrik_o2_katsayilari_formulden_turetiliyor'

    def test_d19_bekcisi_urun_fonksiyonunu_cagiriyor(self):
        govde = _test_govdesi(D19_YOL, self.AD)
        assert govde is not None, 'D19 bekçisi kaybolmuş'
        nitelikler = {d.attr for d in ast.walk(govde)
                      if isinstance(d, ast.Attribute)}
        assert '_calculate_stoichiometric_of' in nitelikler, (
            'bekçi ÜRÜN fonksiyonunu çağırmıyor — totolojiye geri dönmüş')

    def test_d19_bekcisi_denetlenen_tarafa_yaslanmiyor(self):
        """Beklenen taraf ``_formula_molar_mass``'ı ÇAĞIRMAMALI."""
        govde = _test_govdesi(D19_YOL, self.AD)
        nitelikler = {d.attr for d in ast.walk(govde)
                      if isinstance(d, ast.Attribute)}
        assert '_formula_molar_mass' not in nitelikler, (
            'beklenen taraf denetlenen fonksiyona yaslanıyor')

    def test_d19_bekcisi_aluminyumu_kapsiyor(self):
        govde = _test_govdesi(D19_YOL, self.AD)
        metin = ast.unparse(govde)
        assert '_N_O2' in metin or 'aluminum' in metin


# ------------------------------------------------------- fail-closed (K6)
class TestB312KabulKumesiTek:
    """İki fonksiyon aynı kabul kümesini paylaşır; sessiz kol yok."""

    TANIMSIZ_YAKIT = ('n2o', 'o2', 'h2o2', 'kerosene')
    TANIMSIZ_OKS = ('nitrous', 'n2o4', '')

    def test_tanimsiz_yakit_adiyla_reddediliyor(self, analizci):
        for anahtar in self.TANIMSIZ_YAKIT:
            with pytest.raises(ValueError) as exc:
                analizci._calculate_stoichiometric_of({anahtar: 100.0}, 'lox')
            assert getattr(exc.value, 'field', None) == 'fuel_type', anahtar
            assert getattr(exc.value, 'reason', None) == \
                'unsupported_fuel_key', anahtar
            assert anahtar in str(exc.value) or anahtar == ''

    def test_tanimsiz_oksitleyici_adiyla_reddediliyor(self, analizci):
        for anahtar in self.TANIMSIZ_OKS:
            with pytest.raises(ValueError) as exc:
                analizci._calculate_stoichiometric_of({'htpb': 100.0},
                                                      anahtar)
            assert getattr(exc.value, 'field', None) == 'oxidizer_type', \
                anahtar
            assert getattr(exc.value, 'reason', None) == \
                'unsupported_oxidizer_key', anahtar

    def test_iki_fonksiyon_ayni_karari_veriyor(self, analizci):
        """Kabul kümesi kardeş fonksiyonla AYRIŞMAMALI (önce 7 ayrışma)."""
        for anahtar in self.TANIMSIZ_YAKIT + ('htpb', 'paraffin'):
            kararlar = []
            for cagri in (
                    lambda: analizci._calculate_stoichiometric_of(
                        {anahtar: 100.0}, 'lox'),
                    lambda: analizci._calculate_elemental_composition(
                        {anahtar: 100.0}, 'lox', 6.0)):
                try:
                    cagri()
                    kararlar.append('KABUL')
                except ValueError:
                    kararlar.append('RET')
            assert kararlar[0] == kararlar[1], (
                f'{anahtar}: stokiyometri {kararlar[0]}, '
                f'elemental {kararlar[1]}')

        for anahtar in self.TANIMSIZ_OKS + ('n2o', 'lox', 'h2o2', 'air'):
            kararlar = []
            for cagri in (
                    lambda: analizci._calculate_stoichiometric_of(
                        {'htpb': 100.0}, anahtar),
                    lambda: analizci._calculate_elemental_composition(
                        {'htpb': 100.0}, anahtar, 6.0)):
                try:
                    cagri()
                    kararlar.append('KABUL')
                except ValueError:
                    kararlar.append('RET')
            assert kararlar[0] == kararlar[1], (
                f'oks {anahtar!r}: stokiyometri {kararlar[0]}, '
                f'elemental {kararlar[1]}')

    def test_negatif_ya_da_sifir_of_yayimlanmiyor(self, analizci):
        """Önce 4 anahtar ≤0 O/F veriyordu (n2o −0,3635; kerosene 0)."""
        for yakit in SUPPORTED_HYBRID_FUEL_KEYS:
            for oks in ('lox', 'n2o', 'h2o2', 'air'):
                deger = float(analizci._calculate_stoichiometric_of(
                    {yakit: 100.0}, oks))
                assert deger > 0.0, f'{yakit}|{oks} -> {deger!r}'

    def test_desteklenen_yakitlar_hala_kabul(self, analizci):
        """Fail-closed AŞIRI reddetmemeli: sağlıklı envanter korunuyor."""
        assert set(SUPPORTED_HYBRID_FUEL_KEYS) == set(N_O2)
        for yakit in SUPPORTED_HYBRID_FUEL_KEYS:
            am = analizci._ATOMIC_MASS
            formul = analizci._REACTANT_FORMULAS[yakit]
            m_yakit = sum(am[el] * n for el, n in formul.items())
            beklenen = N_O2[yakit] * (2.0 * am['O']) / m_yakit
            assert float(analizci._calculate_stoichiometric_of(
                {yakit: 100.0}, 'lox')) == pytest.approx(beklenen, abs=1e-12)

    def test_karisim_yakit_hala_calisiyor(self, analizci):
        """Çok bileşenli yakıt (htpb + aluminum) reddedilmiyor."""
        deger = float(analizci._calculate_stoichiometric_of(
            {'htpb': 80.0, 'aluminum': 20.0}, 'n2o'))
        am = analizci._ATOMIC_MASS
        m_htpb = 4 * am['C'] + 6 * am['H']
        y_o2 = am['O'] / (2.0 * am['N'] + am['O'])
        beklenen = (0.8 * 5.5 * (2.0 * am['O']) / m_htpb
                    + 0.2 * 0.75 * (2.0 * am['O']) / am['AL']) / y_o2
        assert deger == pytest.approx(beklenen, abs=1e-12)
