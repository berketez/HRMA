# -*- coding: utf-8 -*-
"""ÖH Dalga-20 · fizik kulvarı · aşama 1 — bekçiler.

Kalemler:
  * P2B1-01 — katı motorda aynı yanıtta iki egzoz hızı: nozul paneli hızı
    kaydın TEK FAZLI ideal c*'ından, itki zinciri TESLİM EDİLEN c*'tan
    türüyordu. Onarımdan sonra ikisinin arasında YALNIZ nozul verimi kalır.
  * B1-12 — hibrit motorda manşet C_F yalnız diverjans verimini uygularken
    lüle paneli sürtünme/iki-faz/kinetik verimleri de uyguluyordu; aynı
    lülenin iki C_F'i ve iki Isp'si yayımlanıyordu, manşet daima iyimser.
"""
import math

import pytest

from hrma.engines.solid_rocket_engine import (
    SolidRocketEngine, _condensed_mass_fraction, _ideal_single_phase_c_star)


KATI_YAKITLAR = ('apcp', 'double_base', 'knsu', 'sugar', 'kndx', 'knsb',
                 'black_powder')


def _kati(yakit):
    m = SolidRocketEngine(propellant_type=yakit, grain_type='bates',
                          chamber_pressure=40.0, chamber_diameter=100.0,
                          grain_length=500.0, core_diameter=30.0)
    return m, m.calculate_performance()


class TestP2B101EgzozHiziTekKaynak:
    """Katı motorun yayımladığı egzoz hızı, itki zincirinin c*'ına bağlıdır."""

    @pytest.mark.parametrize('yakit', KATI_YAKITLAR)
    def test_panel_hizi_ile_irtifa_hizi_arasinda_yalniz_nozul_verimi_kalir(
            self, yakit):
        m, res = _kati(yakit)
        panel = (res['nozzle_design']['performance'])
        v_panel = panel['exit_velocity']
        v_irtifa = res['altitude_performance'][0]['exit_velocity']
        assert v_panel is not None and v_irtifa is not None
        eta = float(m.nozzle_efficiency)
        # Beklenen oran TAM OLARAK 1/eta_nozzle; kaydın kendi c* sapması
        # (|<=0,006 %|) dışında başka bir çarpan kalmamalıdır.
        oran = v_panel / v_irtifa
        assert oran == pytest.approx(1.0 / eta, rel=2e-4), (
            f'{yakit}: panel/irtifa = {oran:.6f}, 1/eta = {1.0 / eta:.6f}')

    # D31 kati a1 (OH-D19-22): kndx/knsb termokimyası knsu/sugar ile aynı
    # CEA tabanına taşındı, bu iki kayıt artık ölçülen iki-faz açığını
    # (-%5,93 / -%5,75) taşıyor. Bu yüzden aşağıdaki DAHA SIKI bekçinin
    # listesine EKLENDİLER; sıradaki (tek-faz) bekçiden çıkarıldılar.
    # Gevşetme değil sıkılaştırma: oran < 0,95 ve hız < gaz-faz hızı.
    @pytest.mark.parametrize('yakit', ('knsu', 'sugar', 'black_powder',
                                       'kndx', 'knsb'))
    def test_iki_faz_acigi_beyan_eden_kayitta_hiz_duzeltilir(self, yakit):
        """c*'ı tek fazlı idealin ALTINDA olan kayıtta hız o açıyı taşır."""
        m, res = _kati(yakit)
        panel = res['nozzle_design']['performance']
        ayr = panel['exit_velocity_two_phase_decomposition']
        oran = ayr['c_star_ratio_delivered_over_ideal']
        assert oran is not None and oran < 0.95, (
            f'{yakit}: bu kayıt iki-faz açığı beyan ediyor, oran {oran}')
        # Yayımlanan hız gaz-fazı hızının TAM OLARAK bu oran katıdır.
        assert panel['exit_velocity'] == pytest.approx(
            ayr['gas_phase_exit_velocity_ms'] * oran, rel=1e-12)
        # ve gaz-fazı hızından KÜÇÜKTÜR (kusur tam tersini yapıyordu).
        assert panel['exit_velocity'] < ayr['gas_phase_exit_velocity_ms']

    # D31 kati a1: kndx/knsb buradan ÇIKARILDI — artık tek-fazlı idealin
    # üstünde oturan kayıt değiller (OH-D19-22, yukarıdaki not).
    @pytest.mark.parametrize('yakit', ('apcp', 'double_base'))
    def test_tek_faz_tutarli_kayitta_sayi_degismez(self, yakit):
        """c*'ı kendi idealinde olan kayıtta düzeltme fiilen birimdir.

        ÖH KİTAP p1b (B11, §28-36 Ş-3) — KURULUŞ YENİDEN SEÇİLDİ ('apcp').
        Eski kuruluş 'apcp' kaydını tek fazlı sayıyordu; o, geri çözülmüş
        dörtlünün (c* = ideal, sapma −%0,0001) varsayımıydı. Kayıt artık
        CEA denge dörtlüsünü taşır ve kâhine göre iki fazlıdır (sapma
        −%0,0535): önkoşul bozuldu. Testin niyeti (c* kendi tek fazlı
        idealine EŞİT olan termokimyada düzeltme birimdir) APCP'nin kendi
        dörtlüsü üstünde korunur: c* kâhinin tek fazlı ideal c*'ına
        (CEA_DENGE_IDEAL_TEK_FAZ_CSTAR_M_S, Eş. 3-32) ezilir; γ, T_c, M
        kaydınkidir. Beklenen (1,0 ± 1e-4) DEĞİŞMEDİ.
        """
        if yakit == 'apcp':
            from tests.test_kitap_p1b import CEA_DENGE_IDEAL_TEK_FAZ_CSTAR_M_S
            m = SolidRocketEngine(
                propellant_type=yakit, grain_type='bates',
                chamber_pressure=40.0, chamber_diameter=100.0,
                grain_length=500.0, core_diameter=30.0,
                overrides={'char_velocity': CEA_DENGE_IDEAL_TEK_FAZ_CSTAR_M_S})
            res = m.calculate_performance()
        else:
            m, res = _kati(yakit)
        ayr = (res['nozzle_design']['performance']
               ['exit_velocity_two_phase_decomposition'])
        assert ayr['c_star_ratio_delivered_over_ideal'] == pytest.approx(
            1.0, abs=1e-4)

    @pytest.mark.parametrize('yakit', KATI_YAKITLAR)
    def test_ayrisim_kaydi_kendi_icinde_tutarli(self, yakit):
        m, res = _kati(yakit)
        ayr = (res['nozzle_design']['performance']
               ['exit_velocity_two_phase_decomposition'])
        c_teslim = ayr['c_star_delivered_m_s']
        c_ideal = ayr['c_star_single_phase_ideal_m_s']
        assert c_teslim == pytest.approx(float(m.c_star), rel=1e-12)
        beklenen_ideal = _ideal_single_phase_c_star(
            m.gamma, m.T_c, getattr(m, 'mw_exhaust', 26.0))
        assert c_ideal == pytest.approx(beklenen_ideal, rel=1e-12)
        assert ayr['c_star_ratio_delivered_over_ideal'] == pytest.approx(
            c_teslim / c_ideal, rel=1e-12)
        x_p, kaynak, _ = _condensed_mass_fraction(yakit)
        assert ayr['condensed_mass_fraction'] == (
            None if x_p is None else pytest.approx(float(x_p)))
        assert ayr['condensed_mass_fraction_source'] == kaynak

    @pytest.mark.parametrize('yakit', KATI_YAKITLAR)
    def test_kunye_tek_fazli_gaz_hizi_iddiasini_tasimaz(self, yakit):
        """Eski künye 'izentropik tek fazlı gaz hızı' diyordu; artık hızın
        hangi c*'tan geldiğini söyler."""
        m, res = _kati(yakit)
        kunye = res['nozzle_design']['performance']['exit_velocity_basis']
        assert isinstance(kunye, str) and kunye
        assert 'c*_delivered' in kunye
        assert 'No nozzle efficiency is applied' in kunye

    def test_c_star_cozulemezse_hiz_yayimlanmaz(self, monkeypatch):
        """FAIL-CLOSED: oran kurulamıyorsa sayı uydurulmaz."""
        m = SolidRocketEngine(propellant_type='knsu', grain_type='bates',
                              chamber_pressure=40.0, chamber_diameter=100.0,
                              grain_length=500.0, core_diameter=30.0)
        monkeypatch.setattr(
            'hrma.engines.solid_rocket_engine._ideal_single_phase_c_star',
            lambda *a, **k: None)
        durum = m._nozzle_exit_state()
        assert durum['exit_velocity_ms'] is None
        assert 'not published' in durum['exit_velocity_basis']
        # gaz-fazı hızı yine de ölçülebilir bir teşhis olarak durur
        assert durum['gas_phase_exit_velocity_ms'] > 0.0


# ---------------------------------------------------------------- B1-12
from hrma.engines.hybrid_rocket_engine import (  # noqa: E402
    HybridRocketEngine, HYBRID_CF_CROSS_CHECK_TOL_PCT)
from hrma.engines.nozzle_design import (  # noqa: E402
    NOZZLE_FRICTION_EFFICIENCY_DEFAULT)


def _hibrit(**ek):
    kw = dict(thrust=3000, burn_time=10, of_ratio=6.0, chamber_pressure=30.0,
              fuel_type='htpb', oxidizer_type='n2o', uq_mode=True)
    kw.update(ek)
    m = HybridRocketEngine(**kw)
    return m, m.calculate()


class TestB112TekKayipKumesi:
    """Manşet C_F ile lüle panelinin C_F'i aynı kayıp kümesini uygular."""

    @pytest.mark.parametrize('eps', (6.5, 12.0, 40.0, None))
    def test_kayip_kumesi_iki_tarafta_ozdes(self, eps):
        m, res = _hibrit(**({} if eps is None else {'expansion_ratio': eps}))
        cc = m.thrust_coefficient_cross_check
        assert cc['loss_sets_identical'] is True, cc
        assert cc['loss_set_headline'] == pytest.approx(
            cc['loss_set_panel'], rel=1e-12)

    @pytest.mark.parametrize('eps', (6.5, 12.0, 40.0, None))
    def test_manset_artik_iyimser_taraf_degil(self, eps):
        """Kusur 'manşet DAİMA iyimser'di; artık kötümser ya da eşit."""
        m, res = _hibrit(**({} if eps is None else {'expansion_ratio': eps}))
        cc = m.thrust_coefficient_cross_check
        assert cc['relative_gap_percent'] < 0.01, cc['relative_gap_percent']

    @pytest.mark.parametrize('eps', (6.5, 12.0, 40.0, None))
    def test_manset_cf_kayip_kumesinin_carpimidir(self, eps):
        m, res = _hibrit(**({} if eps is None else {'expansion_ratio': eps}))
        k = m.headline_loss_set
        assert k['converged'] is True and k['passes'] >= 1
        assert k['friction_efficiency'] == pytest.approx(
            NOZZLE_FRICTION_EFFICIENCY_DEFAULT, rel=1e-12)
        assert m.CF == pytest.approx(
            k['thrust_coefficient_lossless'] * k['loss_product'], rel=1e-12)
        assert k['loss_product'] < 1.0

    @pytest.mark.parametrize('eps', (6.5, 12.0, 40.0))
    def test_kinetik_verim_tek_kaynak(self, eps):
        """Panel, manşetin yinelemede çözdüğü kinetik verimin AYNISINI alır."""
        m, res = _hibrit(expansion_ratio=eps)
        panel = res['nozzle_design']['performance']
        assert panel['kinetic_efficiency'] == pytest.approx(
            m.kinetic_efficiency_headline, rel=1e-15)
        assert panel['friction_efficiency'] == pytest.approx(
            NOZZLE_FRICTION_EFFICIENCY_DEFAULT, rel=1e-15)

    def test_yineleme_bogaz_capina_yakinsar(self):
        m, res = _hibrit(expansion_ratio=12.0)
        k = m.headline_loss_set
        assert k['throat_diameter_m'] == pytest.approx(m.d_t, rel=1e-9)
        assert 1 <= k['passes'] <= 12

    def test_kullanici_cf_verirse_kayip_kumesi_ikinci_kez_uygulanmaz(self):
        m, res = _hibrit(thrust_coefficient=1.45)
        assert m.CF == pytest.approx(1.45, rel=1e-12)
        k = m.headline_loss_set
        assert k['loss_product'] is None and k['passes'] == 0

    @pytest.mark.parametrize('eps', (6.5, 12.0, 40.0, None))
    def test_kalan_fark_adiyla_yayimlanir(self, eps):
        """Kalan fark gizlenmez: kökleri adlandırılır, band beyanlıdır."""
        m, res = _hibrit(**({} if eps is None else {'expansion_ratio': eps}))
        cc = m.thrust_coefficient_cross_check
        assert cc['tolerance_percent'] == HYBRID_CF_CROSS_CHECK_TOL_PCT
        # ÖH D21 / P15B1-04 — ÇEVRİLDİ: kök SAYISI değil İÇERİĞİ kilitlenir.
        # "λ'nın iki kaynağı" kökü D21'de kapatıldı (manşet artık panelin
        # kontur geometrisini okuyor); sayıyı 3'te tutmak kapanan kusuru
        # künyede yaşatmayı zorunlu kılıyordu.
        #
        # ÖH D23 / P15B1-04 — İKİNCİ KEZ ÇEVRİLDİ. Satır Eş. 3-34 kökünün
        # ``remaining_causes``ta BULUNMASINI şart koşuyordu; o kök D23'te
        # kapatıldı (λ artık lüle panelinde de yalnız momentum itkisine
        # uygulanıyor, ölçülen fark -%0,0458…+%0,5793 -> 0). Kapanan kökü
        # "kalan" diye yayımlamak yalan olurdu; bekçi artık kökün KAPANAN
        # listede olmasını ve KALAN listede OLMAMASINI kilitler. Testin
        # amacı (fark gizlenmez, kökleri adıyla yayımlanır) değişmedi.
        assert any('Eq. 3-34' in c for c in cc['closed_causes'])
        assert not any('Eq. 3-34' in c for c in cc['remaining_causes'])
        assert not any('catalogue constant' in c
                       for c in cc['remaining_causes'])
        assert cc['divergence_efficiencies_identical'] is True
        assert cc['status'] in ('pass', 'out_of_band')
        if abs(cc['relative_gap_percent']) > HYBRID_CF_CROSS_CHECK_TOL_PCT:
            assert cc['status'] == 'out_of_band'

    def test_manset_isp_kayip_kumesiyle_dusuruldu(self):
        """Sayısal çapa: kayıpsız Isp ile yayımlanan Isp arasında tam olarak
        kayıp çarpımı kadar fark olur (~%2)."""
        m, res = _hibrit(expansion_ratio=12.0)
        k = m.headline_loss_set
        isp_kayipsiz = (k['thrust_coefficient_lossless'] * m.C_star / m.g0)
        assert m.Isp == pytest.approx(isp_kayipsiz * k['loss_product'],
                                      rel=1e-12)
        # ÖH D22 / hibrit-a1 — BANT YENİLENDİ (bekçi çevrildi, gerekçe).
        # D20'de ölçülen kayıp %1,83…%2,20 idi ve alt sınır 0,015 oraya
        # göre konmuştu. OH-D21-03 kinetik verimin girdisini düzeltti:
        # eskiden İSTENEN L* okunuyordu (varsayılan 1,0 m), oysa hibritte
        # port hacmi o hacmi tek başına aşar ve GERÇEKLEŞEN L* 3,54 m'dir.
        # Kalış süresi büyüyünce rekombinasyon kaybı küçülür: eta_kinetik
        # 0,9862201 -> 0,9922190, dolayısıyla toplam kayıp %2,20 -> %1,21.
        # Sayı DÜŞTÜ çünkü eski sayı ULAŞILAMAYAN bir L*'tan geliyordu.
        # Testin koruduğu sözleşme (yukarıdaki tam özdeşlik) değişmedi;
        # yalnız sayısal çapa güncel ölçüme çekildi. Alt sınır hâlâ
        # "kayıp kümesi kaldırıldı" (fark = 0) mutasyonunu yakalar.
        assert 0.008 < (1.0 - m.Isp / isp_kayipsiz) < 0.030
