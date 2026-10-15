# -*- coding: utf-8 -*-
"""ÖH Dalga-16 · kulvar hibrit · aşama 1 — mutasyon kanıtlı bekçiler.

Her sınıf, P01 hibrit-çekirdek raporunun bir kalemini kilitler. Bekçilerin
tamamı ters-mutasyonla sınandı: onarım baytları geçici olarak eski hâline
çevrildiğinde ilgili test KIRMIZI olur (kanıt:
``docs/scofield/raw/OH/D16/hibrit/a1/mutasyon.json``).
"""
import math

import pytest

from hrma.engines import cea_bridge as cb
from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.injector_design import design_injector
from hrma.engines.nozzle_design import NozzleDesigner

HTPB = {'htpb': 100.0}


def _analiz(**kw):
    an = CombustionAnalyzer()
    return an.analyze_combustion(HTPB, 'N2O', 6.0, **kw)


# ---------------------------------------------------------------- B3-08
class TestB308OdaGirdiKapisi:
    """chamber_pressure / chamber_temperature girdi kapısı (fail-closed).

    Taban ölçümü (6fde52b): Pc=-20 -> TAM sonuç, boğaz basıncı
    -11,118412 bar (negatif MUTLAK basınç), oda yoğunluğu -2,969325;
    Pc=0 -> ham ZeroDivisionError; Pc=nan/inf -> her yaprak nan/inf;
    T_c=-500 -> boğaz sıcaklığı -429,1845 K.
    """

    @pytest.mark.parametrize('pc', [-20.0, 0.0, float('nan'), float('inf')])
    def test_gecersiz_oda_basinci_sonuc_yayimlamaz(self, pc):
        with pytest.raises(ValueError) as exc:
            _analiz(chamber_pressure=pc)
        assert 'chamber_pressure' in str(exc.value)

    @pytest.mark.parametrize('tc', [-500.0, 0.0, float('nan'), float('inf')])
    def test_gecersiz_oda_sicakligi_sonuc_yayimlamaz(self, tc):
        with pytest.raises(ValueError) as exc:
            _analiz(chamber_pressure=20.0, chamber_temperature=tc)
        assert 'chamber_temperature' in str(exc.value)

    def test_okunamayan_deger_de_reddedilir(self):
        with pytest.raises(ValueError):
            _analiz(chamber_pressure='yirmi')

    def test_gecerli_girdi_hala_calisir(self):
        r = _analiz(chamber_pressure=20.0)
        assert r['conditions']['throat']['P'] > 0.0
        assert r['conditions']['chamber']['T'] > 0.0


# ---------------------------------------------------------------- B3-06
class TestB306TekOdaGammasi:
    """Cantera kapalıyken aynı yanıtta iki oda gamma'sı olamaz.

    Taban ölçümü: compositions.chamber.gamma = gamma_avg = 1,195914 iken
    boğaz basıncından geri çözülen gamma 1,250000 (fark %4,5226).
    """

    @staticmethod
    def _gamma_geri_coz(pc, pt):
        def f(g):
            return pc / (((g + 1.0) / 2.0) ** (g / (g - 1.0))) - pt
        lo, hi = 1.01, 1.90
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if f(lo) * f(mid) <= 0:
                hi = mid
            else:
                lo = mid
        return 0.5 * (lo + hi)

    def test_bogaz_istasyonu_yayimlanan_gamma_ile_tutarli(self):
        an = CombustionAnalyzer()
        an.cantera_available = False
        an.gas = None
        r = an.analyze_combustion(HTPB, 'N2O', 6.0, chamber_pressure=20.0,
                                  expansion_ratio=4.0)
        g_yayim = r['compositions']['chamber']['gamma']
        assert g_yayim is not None
        pc = r['conditions']['chamber']['P']
        pt = r['conditions']['throat']['P']
        tc = r['conditions']['chamber']['T']
        tt = r['conditions']['throat']['T']
        g_p = self._gamma_geri_coz(pc, pt)
        g_t = 2.0 * tc / tt - 1.0
        assert g_p == pytest.approx(g_yayim, rel=1e-6)
        assert g_t == pytest.approx(g_yayim, rel=1e-6)
        assert r['performance']['gamma_avg'] == pytest.approx(g_yayim,
                                                              rel=1e-9)


# ---------------------------------------------------------------- B3-09
class TestB309OptimumBantKenari:
    """Bant kenarına dayanan nokta 'optimum' diye yayımlanamaz.

    Taban ölçümü: htpb/hava Pc=20 bar -> optimum_of_ratio = 9,999929
    (bandın üst kenarı), maximum_isp = 172,93944 s; gerçek optimum
    14,035275 / 180,48780 s (bant 5-40 referansı).
    """

    def test_hava_kenara_dayanmiyor_ve_dayanak_yayimlaniyor(self):
        an = CombustionAnalyzer()
        r = an.find_optimum_of_ratio(HTPB, 'air', 20.0)
        assert 'of_range_basis' in r
        assert 'of_range_searched' in r
        # Kenar noktası (9,99993) ARTIK yayımlanmıyor.
        assert r['optimum_of_ratio'] > 10.5
        # Gerçek optimuma (geniş bant referansı) yakın.
        assert r['optimum_of_ratio'] == pytest.approx(14.035, rel=5e-3)
        assert r['maximum_isp'] == pytest.approx(180.488, rel=5e-3)
        assert 'widened' in r['of_range_basis']

    def test_ic_optimum_dayanagi_dogru_soyluyor(self):
        an = CombustionAnalyzer()
        r = an.find_optimum_of_ratio(HTPB, 'n2o', 20.0)
        assert r['of_range_basis'].startswith('interior optimum')
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K
        # doymuş SIVI giriş entalpisi. Kâhin: CEA kök denetimi
        # (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) +
        # önce/sonra (p1a rapor §12). Tolerans DEĞİŞMEDİ.
        #   optimum O/F 6,8452 -> 7,0551 (ölçülen 7,055120388715818)
        assert r['optimum_of_ratio'] == pytest.approx(7.0551, rel=1e-3)


# ---------------------------------------------------------------- B3-07
class TestB307EpsNicemlemesi:
    """cea_bridge alan oranı önbellek anahtarı BAĞIL çözünürlükte olmalı.

    Taban ölçümü: _EPS_ROUND = 1 (MUTLAK 0,1) -> bağıl adım ε=1,6'da
    %6,250; ε 1,6499 ile 1,6501 ayrı hücrelere düşüp isp_vac'ta
    +3,265278 s (+%1,2600) basamak doğuruyordu.
    """

    def test_mutlak_ondalik_nicemleme_kalkti(self):
        assert not hasattr(cb, '_EPS_ROUND')
        assert cb._EPS_SIG_DIGITS == cb._PC_SIG_DIGITS

    @pytest.mark.parametrize('eps', [1.6, 2.0, 4.0, 16.0])
    def test_bagil_adim_pc_ile_ayni_mertebede(self, eps):
        adim = abs(eps) * 10.0 ** (1 - cb._EPS_SIG_DIGITS)
        assert adim / eps < 1.0e-4   # taban: 0,0625 (ε=1,6)

    def test_yakin_epslar_ayni_hucreye_dusmuyor(self):
        a = cb._round_significant(1.6499, cb._EPS_SIG_DIGITS)
        b = cb._round_significant(1.6501, cb._EPS_SIG_DIGITS)
        assert a != b
        assert a == pytest.approx(1.6499, rel=1e-9)

    # -------- ÖH D18 (Fable-D16 ŞART) — KULLANIM YERİ bekçisi --------
    # D16 onarımı sabiti ve yardımcıyı sınıyordu; `get_combustion_properties`
    # içindeki eps_key satırının (cea_bridge.py:681) o yardımcıyı FİİLEN
    # çağırdığı bekçisizdi — satır `round(x, 1)`'e geri çevrilse yukarıdaki
    # üç test de YEŞİL kalıyordu (ölçüm:
    # docs/scofield/raw/OH/D18/hibrit/a1/once_b307.json).
    @staticmethod
    def _cagri_yerinden_gecen_eps(monkeypatch, eps_degeri):
        """`_compute_rocketcea`'ya FİİLEN geçen ε anahtarını döndür."""
        kayit = {}

        def sahte_compute(fuel_card, ox_card, pc_bar, mr, eps, ambient_bar,
                          fac_cr=None):
            kayit['eps'] = eps
            return {'c_star_m_s': 1800.0, 'tc_k': 3500.0,
                    'gamma_chamber': 1.2, 'gamma_throat': 1.19,
                    'mw_g_mol': 22.0, 'isp_vac_s': 300.0,
                    'isp_vac_frozen_s': None, 'isp_sl_s': 280.0,
                    'cp_chamber': 2000.0, 'mole_fractions': None}

        monkeypatch.setattr(cb, 'is_rocketcea_available', lambda: True)
        monkeypatch.setattr(cb, 'map_propellants', lambda f, o: ('X', 'Y'))
        monkeypatch.setattr(cb, '_compute_rocketcea', sahte_compute)
        r = cb.get_combustion_properties('f', 'o', 100.0, 2.56,
                                         expansion_ratio=eps_degeri)
        assert r['source'] == 'rocketcea'   # sahte yol gerçekten koşmalı
        assert 'eps' in kayit
        return kayit['eps']

    def test_cagri_yeri_bagil_nicemlemeyi_kullaniyor(self, monkeypatch):
        """ε 1,6499 ve 1,6501 çağrı yerinden AYRI ve BAĞIL geçmeli."""
        a = self._cagri_yerinden_gecen_eps(monkeypatch, 1.6499)
        b = self._cagri_yerinden_gecen_eps(monkeypatch, 1.6501)
        # 1) ayrı hücreler
        assert a != b
        # 2) BAĞIL nicemleme: tam olarak _round_significant(·, 6)
        assert a == cb._round_significant(1.6499, cb._EPS_SIG_DIGITS)
        assert b == cb._round_significant(1.6501, cb._EPS_SIG_DIGITS)
        assert a == pytest.approx(1.6499, rel=1e-12)
        assert b == pytest.approx(1.6501, rel=1e-12)
        # 3) eski MUTLAK yazım (round(x, 1)) bu iddiaları düşürürdü:
        #    (1,6 ; 1,7) — ayrı ama BAĞIL değil.
        assert (a, b) != (round(1.6499, 1), round(1.6501, 1))

    def test_cagri_yeri_gurultuyu_hala_tek_hucreye_topluyor(self, monkeypatch):
        """Önbelleğin asıl işi korunmalı: 1e-13 gürültü aynı anahtara."""
        a = self._cagri_yerinden_gecen_eps(monkeypatch, 16.0)
        b = self._cagri_yerinden_gecen_eps(monkeypatch, 16.0 + 1e-13)
        assert a == b == 16.0

    def test_cagri_yeri_eps_yoksa_anahtar_none(self, monkeypatch):
        assert self._cagri_yerinden_gecen_eps(monkeypatch, None) is None


# ---------------------------------------------------------------- B3-10
class TestB310FallbackEpsCapasi:
    """Statik tablo ε=200 çapasındadır; başka ε'da Isp yayımlanamaz.

    Taban ölçümü: ε = 1,6 / 4,0 / 16,0 / 200,0 / 1000,0 isteklerinin
    HEPSİ isp_vac_s = 380,4 s döndürüyordu, validity'de ε bayrağı yoktu.
    Sessiz hata ε=1,6'da +%46,79, ε=4'te +%27,03, ε=16'da +%12,08.
    """

    FB = {'c_star_m_s': 1800.0, 'tc_k': 3500.0, 'gamma_chamber': 1.2,
          'gamma_throat': 1.19, 'mw_g_mol': 22.0, 'isp_vac_s': 380.4}

    @pytest.mark.parametrize('eps', [1.6, 4.0, 16.0, 1000.0])
    def test_capa_disi_eps_icin_isp_geri_cekilir(self, eps):
        r = cb._from_fallback(dict(self.FB), 100.0, eps)
        assert r['validity']['eps_anchor_ok'] is False
        assert r['validity']['eps_requested'] == pytest.approx(eps)
        assert r['isp_vac_s'] is None
        assert r['isp_sl_s'] is None
        # ε'dan BAĞIMSIZ yapraklar korunur.
        assert r['c_star_m_s'] == pytest.approx(1800.0)
        assert r['tc_k'] == pytest.approx(3500.0)

    def test_capadaki_eps_icin_isp_korunur(self):
        r = cb._from_fallback(dict(self.FB), 100.0, cb.FALLBACK_EPS_ANCHOR)
        assert r['validity']['eps_anchor_ok'] is True
        assert r['isp_vac_s'] == pytest.approx(380.4)

    def test_cagiran_kendi_capasini_bildirebilir(self):
        fb = dict(self.FB)
        fb['isp_vac_eps'] = 4.0
        r = cb._from_fallback(fb, 100.0, 4.0)
        assert r['validity']['eps_anchor'] == pytest.approx(4.0)
        assert r['validity']['eps_anchor_ok'] is True
        assert r['isp_vac_s'] == pytest.approx(380.4)


# ---------------------------------------------------------------- B4-04
def _ox_spec(fluid):
    return {'motor_type': 'hybrid', 'mdot_ox': 2.0, 'Pc_bar': 30.0,
            'fluid_ox': fluid, 'T_ox_K': 293.15, 'rho_ox': 784.88,
            'p_feed_bar': 50.543}


class TestB404OksitleyiciHarfDuzeni:
    """'N2O' ile 'n2o' aynı fiziği vermeli.

    Taban ölçümü: 'N2O' SPI dalına düşüyordu — P_v 50,543358 -> 0,050000
    bar (1010,9 kat), alan 59,677780 -> 45,153023 mm² (-%24,3),
    hydraulic_flip_risk True -> False (güvenlik yönünde YANLIŞ taraf).
    """

    @pytest.mark.parametrize('ad', ['N2O', 'N2o', 'n2O'])
    def test_buyuk_harf_kucuk_harfle_ayni_sonucu_verir(self, ad):
        kucuk = design_injector(_ox_spec('n2o'))['ox_circuit']
        buyuk = design_injector(_ox_spec(ad))['ox_circuit']
        assert buyuk['flow_model'] == kucuk['flow_model'] == 'NHNE'
        assert buyuk['vapor_pressure_bar'] == pytest.approx(
            kucuk['vapor_pressure_bar'], rel=1e-12)
        assert buyuk['total_area_mm2'] == pytest.approx(
            kucuk['total_area_mm2'], rel=1e-12)
        assert buyuk['n_orifices'] == kucuk['n_orifices']

    def test_jenerik_varsayilan_hala_jenerik(self):
        """Harf normalleştirmesi sessiz bir 'n2o' varsayılanı AÇMAZ."""
        spec = _ox_spec('n2o')
        spec.pop('fluid_ox')
        ox = design_injector(spec)['ox_circuit']
        assert ox['flow_model'] == 'SPI'


# ---------------------------------------------------------------- B4-05
class TestB405KazanilmamisFlipHukmu:
    """L/D modül varsayılanıysa hidrolik-flip hükmü yayımlanamaz.

    Taban ölçümü: plaka verilmeden L/D = 4,000 (modül varsayılanı) ve
    hydraulic_flip_risk = True (üç hibrit koşusunda 3/3); plaka 2 mm ->
    L/D 0,824808 / False, plaka 15 mm -> L/D 6,186057 / False.
    """

    def test_plaka_yokken_hukum_yayimlanmaz(self):
        ox = design_injector(_ox_spec('n2o'))['ox_circuit']
        assert ox['l_over_d_basis'].startswith('module default')
        assert ox['hydraulic_flip_risk'] is None
        assert 'NOT DECIDED' in ox['hydraulic_flip_risk_basis']

    def test_plaka_yokken_flip_uyarisi_da_basilmaz(self):
        r = design_injector(_ox_spec('n2o'))
        kodlar = [w.get('code') for w in (r.get('warnings') or [])]
        assert 'warn.injector.hydraulic_flip_risk_ox' not in kodlar

    @pytest.mark.parametrize('t_m,beklenen_ld', [(0.002, 0.8248),
                                                 (0.015, 6.1861)])
    def test_plaka_verilince_hukum_kazanilir(self, t_m, beklenen_ld):
        spec = _ox_spec('n2o')
        spec['orifice_length_m'] = t_m
        ox = design_injector(spec)['ox_circuit']
        assert ox['l_over_d'] == pytest.approx(beklenen_ld, rel=1e-3)
        assert ox['hydraulic_flip_risk'] is False
        assert ox['hydraulic_flip_risk_basis'].startswith('Nurick criterion')


# ---------------------------------------------------------------- B4-06/07
def _lule(tip):
    nd = NozzleDesigner()
    at = math.pi * 0.030 ** 2
    return nd.design_nozzle(at, 8.0, 40.0, 1.01325, nozzle_type=tip,
                            gamma=1.20, R_specific=350.0, T_chamber=3400.0)


class TestB406LuleHacmi:
    """geometry.volume iki bölümün (konverjan + diverjan) toplamı olmalı.

    Taban ölçümü (r_t=30 mm, ε=8): yayımlanan/gerçek oranı bell 1,117744,
    conical 1,098295, parabolic 1,114310 — yani boy konverjanı içerirken
    yarıçaplar yalnız diverjanındı.
    """

    @pytest.mark.parametrize('tip', ['bell', 'conical', 'parabolic'])
    def test_hacim_kesik_koni_toplamina_esit(self, tip):
        r = _lule(tip)
        c, g = r['contour'], r['geometry']
        rt = 0.030
        re = rt * math.sqrt(8.0)
        rc = c['convergent']['chamber_radius'] / 1000.0
        lc = c['convergent']['length'] / 1000.0
        ld = c['divergent']['length'] / 1000.0
        beklenen = (math.pi * lc * (rc * rc + rc * rt + rt * rt) / 3.0
                    + math.pi * ld * (rt * rt + rt * re + re * re) / 3.0)
        assert g['volume'] / 1e9 == pytest.approx(beklenen, rel=1e-12)

    @pytest.mark.parametrize('tip', ['bell', 'conical', 'parabolic'])
    def test_hacim_yalniz_diverjandan_buyuk(self, tip):
        """Konverjan gerçekten sayılıyor (yalnız-diverjan yazımı da kusurdu)."""
        r = _lule(tip)
        c, g = r['contour'], r['geometry']
        rt = 0.030
        re = rt * math.sqrt(8.0)
        ld = c['divergent']['length'] / 1000.0
        yalniz_div = math.pi * ld * (rt * rt + rt * re + re * re) / 3.0
        assert g['volume'] / 1e9 > yalniz_div * 1.02


class TestB407ParabolikCikisAcisi:
    """Parabolik dal açısını YAYIMLAMALI; performans ile çizim aynı açıyı görmeli.

    Taban ölçümü: divergent anahtarları ['curvature_parameter','length',
    'type'] (açı yok); λ = 0,99240388'den geri çözülen θ_e = 10,000000°
    (performans varsayılanı) iken sample_nozzle_inner_contour 8,0°
    varsayılanını kullanıyordu — aynı kontur iki geometri.
    """

    def test_parabolik_aci_yayimliyor(self):
        div = _lule('parabolic')['contour']['divergent']
        assert 'exit_angle' in div
        assert 'throat_angle' in div
        assert 'angle_basis' in div

    def test_lambda_yayimlanan_aciyi_izliyor(self):
        r = _lule('parabolic')
        theta_e = r['contour']['divergent']['exit_angle']
        lam = r['performance']['divergence_efficiency']
        assert lam == pytest.approx(
            0.5 * (1.0 + math.cos(math.radians(theta_e))), rel=1e-12)

    def test_ornekleyici_ile_performans_ayni_aciyi_goruyor(self):
        """Çizim/ihracat yolu artık kendi 8,0° varsayılanına düşmüyor.

        ÖH D21 bekci-cevirisi a1 (OH-D17-08) — İDDİA ARTIK SINANIYOR.
        ESKİ hâl (ölçüldü, ``once_statik.json`` ``OH-D17-08``):
        ``sample_nozzle_inner_contour`` **0 kez çağrılıyordu**; gövdenin
        tamamı ``div['exit_angle'] != 8.0`` + ``… is not None`` idi, yani
        docstring'in iddiası (ÇİZİM yolu 8,0°'ye düşmüyor) hiç
        ölçülmüyordu — örnekleyici tamamen sökülse bile bekçi yeşildi.

        Ürün kaçış yolu KODDA duruyor (``hrma/engines/nozzle_design.py``,
        ``theta_e = _num(div.get('exit_angle'), 8.0)``): yayımlanan açı
        gelmezse örnekleyici kendi 8,0°'sini kullanır. Bekçi bu kanalı
        üç koşumla ölçer (ölçüldü, ``once_dinamik.json``: yayımlanan açı
        14,0°, künye ``rao80_clamped_low``, 67 örnek nokta):
          1. yayımlanan konturla örneklenen kontur, açı SÖKÜLMÜŞ
             konturdan FARKLI olmalı (kanal canlı);
          2. açı sökülünce çıkan kontur, açı AÇIKÇA 8,0° verilenle
             BİT-AYNI olmalı (kaçış yolunun 8,0° olduğu kanıtı);
          3. yayımlanan açı 8,0° olmamalı (performans ile çizim aynı
             açıyı görüyor).
        """
        import copy
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        r = _lule('parabolic')
        div = r['contour']['divergent']
        assert div['exit_angle'] != 8.0
        assert div.get('angle_basis'), 'açı künyesiz yayımlanıyor'

        md = {'nozzle_contour': copy.deepcopy(r['contour'])}
        yayimli, meta = sample_nozzle_inner_contour(md)
        assert meta['noz_type'] == 'parabolic'
        assert len(yayimli) > 10

        kirpik = copy.deepcopy(md)
        kirpik['nozzle_contour']['divergent'].pop('exit_angle', None)
        kacis, _ = sample_nozzle_inner_contour(kirpik)
        assert list(yayimli) != list(kacis), (
            'yayımlanan çıkış açısı sökülünce örneklenen kontur '
            'DEĞİŞMİYOR — çizim yolu açıyı tüketmiyor, yani kendi '
            'varsayılanıyla çiziyor olabilir')

        sekiz = copy.deepcopy(md)
        sekiz['nozzle_contour']['divergent']['exit_angle'] = 8.0
        assert list(sample_nozzle_inner_contour(sekiz)[0]) == list(kacis), (
            'açı sökülmüş kontur ile açı 8,0° verilmiş kontur aynı '
            'değil — kaçış yolunun 8,0° olduğu varsayımı artık geçersiz, '
            'bekçinin gerekçesi güncellenmeli')

    def test_parabolik_ve_bell_ayni_rao_kaynagini_kullaniyor(self):
        p = _lule('parabolic')['contour']['divergent']
        b = _lule('bell')['contour']['divergent']
        assert p['exit_angle'] == pytest.approx(b['exit_angle'], rel=1e-12)
        assert p['angle_basis'] == b['angle_basis']
