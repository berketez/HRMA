# -*- coding: utf-8 -*-
"""ÖH D25 · hibrit · aşama-1 bekçisi — OH-Z5-02 (yedi sabit yaprak).

``test_field_wiring_layer_b::test_no_fabricated_constant_outputs`` tabanda
(cdf2106) 12 sabit yaprak sayıyordu ve 2 eşiğiyle KIRMIZIYDI. Yedisi bu
kulvarın sahasındaydı; hüküm-13 gereği her biri yaprak-başına ölçülüp
sınıflandırıldı ve altı dar imle beyaz listeye alındı.

İm eklemek, gerekçesi ölçülmediği sürece borcu GİZLEMEKTİR. Bu dosya
gerekçelerin ÖNCÜLLERİNİ kilitler: her imin dayandığı "şu sebeple sabit"
iddiası burada ayrı ayrı ölçülür. Öncül çürürse bu bekçi kırmızıya döner
ve im gerekçesiyle birlikte yeniden açılmak zorunda kalır — otuz ikinci
partinin τ_c oranında kurduğu disiplinin aynısı.

Her sınıf için İKİ şey ölçülür:
  1. sabitliğin SEBEBİ (özdeşlik / eşik / ızgara ucu / tablo referansı),
  2. aynı ailenin ölçülen KARDEŞİNİN hâlâ CANLI olduğu — çünkü im, ölü
     bir aileyi örtmek için değil, canlı bir ailenin beyan yaprağını
     sınıflandırmak için konmuştur.
"""

import math

import pytest


@pytest.fixture(scope='module')
def hibrit_yanit():
    """Gerçek /calculate hibrit yanıtı (sabit yaprakların yayım yeri).

    Yük, Katman B bekçisinin TEK KAYNAK taban motorundan alınır; ikinci
    bir sözlük kopyalamak iki çalışma noktası doğurur.
    """
    from tests.support import shake
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    from hrma.app import app
    istemci = app.test_client()
    yanit = istemci.post('/calculate', json=dict(HYBRID_BASE),
                         headers=shake.HEADERS)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:400]
    return yanit.get_json()


# ---------------------------------------------------------------------------
# 1) İSTASYON TABLOSUNUN İZENTROP ÖZDEŞLİĞİ
# ---------------------------------------------------------------------------
class TestIzentropikVerimOzdesligi:
    """eta_s = 1 bir ÖLÇÜM değil, istasyon kuruluşunun cebirsel sonucudur."""

    @pytest.fixture(scope='class')
    def analiz(self):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        return CombustionAnalyzer()

    @pytest.mark.parametrize('pc,eps', [(10.0, 4.0), (20.0, 10.0),
                                        (40.0, 25.0)])
    def test_ONCUL_cikis_entropisi_oda_entropisine_ESIT(self, analiz, pc, eps):
        """Öncül: s_e − s_c = 0, çözücü yakınsama artığına kadar.

        İmin TAMAMI bu özdeşliğe dayanır. Çıkış istasyonu bir gün oda
        izentropundan kayarsa (ör. donmuş bir kola düşülürse) fark
        sıfırdan ayrılır, ``isentropic_efficiency`` 1'in altına iner ve
        yaprak ARTIK meşru sabit olmaz — bu test o anda kırmızı verir.

        TOLERANS ÖLÇÜMDEN TÜREDİ, tahmin değil (once.json K1; Pc =
        10/20/40 bar × eps = 4/10/25, dokuz koşu): fark BİT-TAM sıfır
        DEĞİL, ``equilibrate('SP')`` yakınsama artığı kadar — ölçülen en
        büyük mutlak değer 5,51e-11 kJ/(kg·K), oda entropisine (~10
        kJ/(kg·K)) göre bağıl 5,5e-12. Eşik 1e-8'e konuldu: artığın ~200
        katı, ama GERÇEK bir entropi üretiminin (donmuş kola düşüş
        mertebe olarak 1e-1..1e0 kJ/(kg·K) verir) yedi mertebe altında.
        Yani bu bekçi solucan deliğinden geçmez, gerçek kaymayı görür.
        """
        # ÖH D25 fix-24 (birleşme etkileşimi): D24 fix aşaması P15B1-05 istasyon
        # alan adlarını birim taşır yaptı ('entropy' -> 'entropy_kJ_kg_K'); bu
        # bekçi cdf2106'da yazılmıştı. İddia ve tolerans DEĞİŞMEDİ, yalnız anahtar.
        r = analiz.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, pc,
                                      expansion_ratio=eps)
        tp = r['performance']['thermodynamic_properties']
        st = tp['stations']
        ds = st['exit']['entropy_kJ_kg_K'] - st['chamber']['entropy_kJ_kg_K']
        assert abs(ds) < 1e-8, (pc, eps, ds)
        # bağıl ölçü: oda entropisine göre artık gürültü mertebesinde
        assert abs(ds) < 1e-9 * abs(st['chamber']['entropy_kJ_kg_K']), (pc, eps, ds)
        # ve aynı özdeşlik yanıtta ham hâliyle de duruyor
        assert abs(tp['deltas']['entropy_change_kJ_kg_K']) < 1e-8

    def test_yaprak_KUNYESI_ozdesligi_ADIYLA_soyluyor(self, analiz):
        """Sabit yaprak, NEDEN sabit olduğunu yanıtta kendisi yazmalı.

        mass_flow_rel_diff'in dersi: künyesi "termokimya çapraz kontrolü"
        diyen bir yaprağı imlemek YANLIŞ BEYANI kilitler. Bu yaprak
        imlenebiliyorsa, künyesinin özdeşliği adıyla söylemesi şarttır.
        """
        r = analiz.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                      expansion_ratio=4.0)
        tp = r['performance']['thermodynamic_properties']
        kunye = tp.get('isentropic_efficiency_basis')
        assert isinstance(kunye, str) and kunye, tp.keys()
        dusuk = kunye.lower()
        assert 'identity' in dusuk, kunye
        assert 'chamber entropy' in dusuk, kunye
        # ve künye, bunun bir DONANIM verimi olmadığını söylemeli
        assert 'not a loss measurement' in dusuk, kunye
        assert 'hardware efficiency' in dusuk, kunye

    def test_deger_ozdeslikle_TUTARLI(self, analiz):
        r = analiz.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                      expansion_ratio=10.0)
        tp = r['performance']['thermodynamic_properties']
        assert math.isclose(tp['isentropic_efficiency'], 1.0, rel_tol=1e-6)

    def test_KARDES_isp_CANLI(self, analiz):
        """İm ölü bir aileyi örtmüyor: kardeş performans yaprağı oynuyor."""
        isp = []
        for eps in (4.0, 10.0, 25.0):
            r = analiz.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                          expansion_ratio=eps)
            isp.append(round(float(r['performance']['isp']), 6))
        assert len(set(isp)) == 3, isp


# ---------------------------------------------------------------------------
# 2) ARANAN O/F BANDI — TANIM KÜMESİ, SONUÇ DEĞİL
# ---------------------------------------------------------------------------
class TestOFBandiTanimKumesi:

    @pytest.fixture(scope='class')
    def analiz(self):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        return CombustionAnalyzer()

    def test_ONCUL_KELEPCE_ACILIYOR_band_sabit_YAZILI_degil(self, analiz):
        """Öncül: bant, aramanın tanım kümesidir ve gerektiğinde GENİŞLER.

        Sabit yazılmış bir sayı olsaydı hiçbir çağrıda kıpırdamazdı.
        ÖLÇÜLDÜ (once.json K2): of_range=(1,0, 3,0) verildiğinde optimum
        üst sınıra dayanıyor ve bant stokiyometrik orana (8,948054...)
        genişliyor.

        SIKILAŞTIRILDI — ters-mutasyon M7 ilk turda bu bekçiyi KIRAMADI:
        yaprak ``[1.0, 10.0]`` diye sabit yazıldığında ``band[1] > 3.0``
        iddiası hâlâ geçiyordu, yani bekçi "bant genişledi mi" değil
        "bant 3'ten büyük mü" diye soruyordu. Üst sınır artık ölçülen
        sayıya değil, KAYNAĞINA bağlanıyor: bandın stokiyometrik orana
        eşit olması şart (TEK KAYNAK — aynı modülün
        ``_calculate_stoichiometric_of``'u) ve varsayılan üst sınıra
        (10,0) eşit OLMAMASI şart. Mutasyon bundan sonra kırmızı verir.
        """
        r = analiz.find_optimum_of_ratio({'htpb': 100.0}, 'n2o', 20.0,
                                         of_range=(1.0, 3.0),
                                         expansion_ratio=4.0)
        band = r['of_range_searched']
        of_stok = float(analiz._calculate_stoichiometric_of({'htpb': 100.0},
                                                            'n2o'))
        assert band[0] == pytest.approx(1.0)
        assert band[1] > 3.0, band
        # bant, çağrılan üst sınıra DEĞİL stokiyometrik orana genişlemeli
        assert band[1] == pytest.approx(of_stok, rel=1e-9), (band, of_stok)
        # ve varsayılan bandın üst ucuna (10,0) çakışmamalı — sabit
        # yazılmış bir band tam oraya düşerdi
        assert band[1] != pytest.approx(10.0, rel=1e-6), band
        assert 'stoichiometric' in r['of_range_basis'].lower(), \
            r['of_range_basis']

    def test_yaprak_KUNYESI_bandi_ADIYLA_soyluyor(self, analiz):
        r = analiz.find_optimum_of_ratio({'htpb': 100.0}, 'n2o', 20.0,
                                         expansion_ratio=4.0)
        assert isinstance(r.get('of_range_basis'), str)
        assert r['of_range_basis'].strip(), r
        assert list(r['of_range_searched']) == [1.0, 10.0], r[
            'of_range_searched']

    def test_KARDES_optimum_ve_maks_isp_CANLI(self, analiz):
        noktalar = []
        for eps in (4.0, 16.0):
            r = analiz.find_optimum_of_ratio({'htpb': 100.0}, 'n2o', 20.0,
                                             expansion_ratio=eps)
            noktalar.append((round(r['optimum_of_ratio'], 6),
                             round(r['maximum_isp'], 6)))
        assert noktalar[0] != noktalar[1], noktalar


# ---------------------------------------------------------------------------
# 3) İRTİFA IZGARASININ TEPESİ — ÇAĞIRANIN IZGARASI
# ---------------------------------------------------------------------------
class TestIzgaraTepesi:

    @pytest.fixture(scope='class')
    def paket(self):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        ca = CombustionAnalyzer()
        r = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                  expansion_ratio=4.0)
        return ca, {'performance': r['performance'],
                    'conditions': r['conditions'],
                    'chamber_pressure': 20.0, 'burn_time': 10.0,
                    'mdot_total': 2.1}

    def test_ONCUL_tepe_CAGIRANIN_izgarasini_birebir_izliyor(self, paket):
        """Öncül: yaprak, ızgaranın son noktasıdır — hesabın sonucu değil.

        Üç farklı ızgarada üç farklı değer alıyorsa sayı sabit YAZILI
        değildir; ürünün /calculate ucunda sabit görünmesinin sebebi
        çağıranın ızgarasının sabit olmasıdır (20 km).
        """
        ca, md = paket
        for izgara in ([0, 5000, 10000], [0, 1000, 5000, 10000, 15000, 20000],
                       [0, 10000, 40000, 80000]):
            r = ca.calculate_thrust_at_altitudes(21000.0, dict(md), izgara)
            assert r['top_of_grid_altitude_m'] == izgara[-1], (izgara, r[
                'top_of_grid_altitude_m'])

    def test_KARDES_top_of_grid_thrust_CANLI(self, paket):
        ca, md = paket
        itki = []
        for izgara in ([0, 5000, 10000], [0, 1000, 5000, 10000, 15000, 20000],
                       [0, 10000, 40000, 80000]):
            r = ca.calculate_thrust_at_altitudes(21000.0, dict(md), izgara)
            itki.append(round(float(r['top_of_grid_thrust']), 6))
        assert len(set(itki)) == 3, itki

    def test_kunye_izgara_ucunu_ADIYLA_soyluyor(self, paket):
        ca, md = paket
        r = ca.calculate_thrust_at_altitudes(
            21000.0, dict(md), [0, 1000, 5000, 10000, 15000, 20000])
        assert 'sweep' in r['vacuum_thrust_basis'].lower()
        assert 'top_of_grid_thrust' in r['vacuum_thrust_basis']


# ---------------------------------------------------------------------------
# 4) ÇAPRAZ DENETİM KAPISININ TOLERANSI — EŞİK SABİTİ
# ---------------------------------------------------------------------------
class TestCFCaprazEsigi:

    def test_ONCUL_TEK_KAYNAK_modul_sabiti(self):
        """Öncül: eşik iki yerde yazılmaz, tek tanım noktası vardır."""
        from hrma.engines import hybrid_rocket_engine as hre
        assert isinstance(hre.HYBRID_CF_CROSS_CHECK_TOL_PCT, float)
        assert hre.HYBRID_CF_CROSS_CHECK_TOL_PCT > 0.0

    def test_yaprak_KUNYESI_esik_oldugunu_ADIYLA_soyluyor(self, hibrit_yanit):
        kapi = hibrit_yanit['motor'].get('thrust_coefficient_cross_check')
        assert isinstance(kapi, dict), list(hibrit_yanit['motor'])[:20]
        kunye = kapi.get('tolerance_percent_basis')
        assert isinstance(kunye, str) and kunye, kapi
        dusuk = kunye.lower()
        assert 'declared gate threshold' in dusuk, kunye
        assert 'not a computed result' in dusuk, kunye
        assert 'relative_gap_percent' in kunye, kunye

    def test_KARDES_olculen_buyukluk_yayimlaniyor(self, hibrit_yanit):
        """Kapının ÖLÇTÜĞÜ taraf yanıtta duruyor ve sayısaldır."""
        kapi = hibrit_yanit['motor']['thrust_coefficient_cross_check']
        assert isinstance(kapi.get('relative_gap_percent'), float)
        assert kapi.get('status') in ('pass', 'out_of_band')


# ---------------------------------------------------------------------------
# 5) CIVATA ASGARİ ADIM ÇARPANI — BEYAN EDİLEN FLANŞ PRATİĞİ
# ---------------------------------------------------------------------------
class TestCivataAdimCarpani:

    @pytest.fixture(scope='class')
    def yapisal(self):
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        return StructuralAnalyzer()

    @property
    def _mat(self):
        return {'yield_strength': 460e6, 'ultimate_strength': 731e6,
                'density': 7850, 'elastic_modulus': 205e9,
                'poisson_ratio': 0.29, 'thermal_conductivity': 42.0,
                'melting_point': 1700.0, 'name': 'steel_4130'}

    def test_ONCUL_esik_sabit_KARDES_oran_CANLI(self, yapisal):
        """Öncül: eşik donuk, hükmün verildiği ORAN canlı.

        ÖLÇÜLDÜ (once.json K5): dört (basınç, çap) çiftinde eşik 2,5'te
        sabit, bolt_pitch_ratio dördünde de farklı.
        """
        esikler, oranlar = set(), set()
        for p, d in ((20e5, 0.15), (60e5, 0.15), (20e5, 0.40), (90e5, 0.30)):
            r = yapisal._analyze_fasteners(p, d, dict(self._mat))
            esikler.add(r['bolt_min_pitch_factor'])
            oranlar.add(round(float(r['bolt_pitch_ratio']), 9))
        assert esikler == {2.5}, esikler
        assert len(oranlar) == 4, oranlar

    def test_yaprak_KUNYESI_beyan_oldugunu_ADIYLA_soyluyor(self, yapisal):
        r = yapisal._analyze_fasteners(20e5, 0.15, dict(self._mat))
        kunye = r['bolt_layout_basis']
        assert 'DECLARED flange practice' in kunye, kunye
        assert 'not a calibration constant' in kunye, kunye

    def test_esik_TEK_KAYNAKTAN_yayimlaniyor(self, yapisal):
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        r = yapisal._analyze_fasteners(20e5, 0.15, dict(self._mat))
        assert (r['bolt_min_pitch_factor']
                == StructuralAnalyzer._BOLT_MIN_PITCH_FACTOR)


# ---------------------------------------------------------------------------
# 6) DAYANIM DÜŞÜRME EĞRİSİNİN ALT UCU — TABLO REFERANSI
# ---------------------------------------------------------------------------
class TestDeratingZarfAltUcu:

    @pytest.fixture(scope='class')
    def malzemeler(self):
        import hrma.data.materials_db as mdb
        for ad in ('MATERIALS_DB', 'MATERIALS', 'MATERIALS_DATABASE'):
            db = getattr(mdb, ad, None)
            if isinstance(db, dict):
                break
        else:  # pragma: no cover
            pytest.skip('materials_db sozlugu bulunamadi')
        return {k: v for k, v in db.items()
                if isinstance(v, dict) and v.get('derating_curve')}

    def test_ONCUL_alt_uc_ORTAK_ust_uc_MALZEMEYE_OZGU(self, malzemeler):
        """Öncül: alt uç MMPDS oda-sıcaklığı referansı, üst uç canlı.

        Aynı yardımcının iki kardeş yaprağı: donan yalnız referans
        ucudur. ÖLÇÜLDÜ (once.json K6, dokuz malzeme): curve_min = 20 C
        hepsinde; curve_max 350/600/700/800/900 C.
        """
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        sa = StructuralAnalyzer()
        assert len(malzemeler) >= 4, list(malzemeler)
        altlar, ustler = set(), set()
        for mp in malzemeler.values():
            r = sa._derate_strength(dict(mp), 600.0)
            altlar.add(r['curve_min_temp_C'])
            ustler.add(r['curve_max_temp_C'])
        assert len(altlar) == 1, altlar
        assert len(ustler) >= 3, ustler

    def test_alt_uc_EGRININ_KENDI_ilk_noktasi(self, malzemeler):
        """Sabit YAZILI değil: eğrinin ilk anahtarından okunuyor."""
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        sa = StructuralAnalyzer()
        ad, mp = next(iter(malzemeler.items()))
        mp = dict(mp)
        egri = dict(mp['derating_curve'])
        # Eğriye daha düşük bir nokta eklenirse yaprak ONU göstermeli
        egri[-40.0] = max(egri.values())
        mp['derating_curve'] = egri
        r = sa._derate_strength(mp, 600.0)
        assert r['curve_min_temp_C'] == -40.0, (ad, r['curve_min_temp_C'])

    def test_KARDES_retention_CANLI(self, malzemeler):
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        sa = StructuralAnalyzer()
        mp = dict(next(iter(malzemeler.values())))
        degerler = {round(sa._derate_strength(dict(mp), T)[
            'strength_retention_factor'], 9) for T in (100.0, 300.0, 500.0)}
        assert len(degerler) == 3, degerler
