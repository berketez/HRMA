# -*- coding: utf-8 -*-
"""ÖH Dalga-18 · kulvar hibrit · aşama 1 — mutasyon kanıtlı bekçiler.

Her sınıf bir defter kalemini kilitler. Bekçilerin tamamı ters-mutasyonla
sınandı: onarım baytları geçici olarak eski hâline çevrildiğinde ilgili test
KIRMIZI olur (kanıt: ``docs/scofield/raw/OH/D18/hibrit/a1/mutasyon.json``).

Ölçüm dosyaları: ``once.json`` (taban 9071a64) / ``sonra.json``.
"""
import io
import contextlib

import numpy as np
import pytest

from hrma.analysis import bolted_joint as bj
from hrma.data.propellant_database import HYBRID_REGRESSION_COEFFICIENTS
from hrma.engines.hybrid_rocket_engine import (
    CLOSURE_JOINT_DEFAULTS,
    HybridRocketEngine,
)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**kw):
    p = dict(thrust=3000.0, burn_time=10.0, of_ratio=6.0,
             chamber_pressure=25.0, fuel_type='htpb', oxidizer_type='n2o')
    p.update(kw)
    return _sessiz(HybridRocketEngine, **p)


def _uyari_kodlari(motor):
    return [w.get('code') for w in motor.design_warnings]


# ---------------------------------------------------------------- B1-13
class TestB113HtpbSapmaKapisi:
    """HTPB katsayısı FİİLEN kullanılıyorsa sapma uyarısı ateşlenmeli.

    Taban ölçümü (once.json, B1_13; 9071a64): kapı ``fuel_key in
    ('htpb','abs')`` elle yazılmış bir AD listesiydi; oysa tabloda karşılığı
    OLMAYAN her yakıt HTPB katsayısına düşüyor. `sorbitol` ve `wax_xyz`
    a=3,680e-05 / n=0,5550 ile — yani HTPB'nin birebir aynısıyla — koşup
    warn.hybrid.htpb_coeff_bias uyarısını ALMIYORDU (sessiz kalan yakıt
    sayısı 2). Ölçülen sapma −%39,5 aynı olduğu hâlde beyan farklıydı.
    """

    HTPB = HYBRID_REGRESSION_COEFFICIENTS['htpb']

    @staticmethod
    def _koş(yakit, **kw):
        m = _motor(fuel_type=yakit, **kw)
        _sessiz(m._set_fuel_properties)
        return m

    def _htpb_katsayisi_yururlukte(self, m):
        return (np.isclose(float(m.a), self.HTPB['a'], rtol=1e-9)
                and np.isclose(float(m.n), self.HTPB['n'], rtol=1e-9))

    @pytest.mark.parametrize('yakit', ['htpb', 'abs', 'sorbitol', 'wax_xyz'])
    def test_htpb_katsayisiyla_kosan_her_yakit_sapmayi_duyuruyor(self, yakit):
        m = self._koş(yakit)
        assert self._htpb_katsayisi_yururlukte(m), (
            f'{yakit} bu sürümde HTPB katsayısıyla koşmuyor; bekçinin '
            f'dayanağı değişmiş, kalem yeniden ölçülmeli')
        assert 'warn.hybrid.htpb_coeff_bias' in _uyari_kodlari(m)

    def test_tabloda_olmayan_yakitlar_ad_listesinde_DEGIL(self):
        """Kapının ad listesine değil, katsayıya baktığının kanıtı."""
        for yakit in ('sorbitol', 'wax_xyz'):
            assert yakit not in HYBRID_REGRESSION_COEFFICIENTS
            m = self._koş(yakit)
            # Düşüşün kendisi hâlâ beyanlı (eski onarım bozulmadı):
            assert 'warn.hybrid.fuel_regression_fallback' in _uyari_kodlari(m)
            assert any('regression_coefficients(' in d
                       for d in m._defaults_used)

    @pytest.mark.parametrize('yakit', ['pla', 'paraffin', 'pmma', 'pe'])
    def test_kendi_katsayisi_olan_yakitta_uyari_SUSUYOR(self, yakit):
        m = self._koş(yakit)
        assert not self._htpb_katsayisi_yururlukte(m)
        assert 'warn.hybrid.htpb_coeff_bias' not in _uyari_kodlari(m)

    def test_kullanici_gercekten_ezerse_bias_susar_sapma_bildirilir(self):
        m = self._koş('sorbitol', regression_a=1.0e-4, regression_n=0.50)
        kodlar = _uyari_kodlari(m)
        assert 'warn.hybrid.htpb_coeff_bias' not in kodlar
        # Tabloda karşılığı olmayan yakıtta da sapma GÖRÜNÜR olmalı:
        # eski kod ``and katalog_kat`` yüzünden bu dalı da düşürüyordu.
        assert 'warn.hybrid.regression_coeff_user_override' in kodlar

    def test_form_on_dolgusu_geri_gonderilirse_bias_yine_ateslenir(self):
        m = self._koş('sorbitol',
                      regression_a=self.HTPB['a'], regression_n=self.HTPB['n'])
        assert 'warn.hybrid.htpb_coeff_bias' in _uyari_kodlari(m)


# ---------------------------------------------------------------- B2-07
class TestB207AkustikYanmaYuzeyiPortSayisi:
    """Akustik eşik bloğunun S_b'si port sayısını görmeli.

    Taban ölçümü (once.json, B2_07; 9071a64, 3 kN N2O/HTPB): yayımlanan
    burning_surface_area_m2 tek port varsayıyordu; fiziksel N·π·D·L ile
    oranı N=1 1,0000 · N=2 2,0000 · N=4 4,0000 · N=7 7,0000 idi.
    surface_mach_M_b aynı çarpanla şişiyordu (N=7: 0,00236076 ⟷ doğru
    0,00033725). R_crit özdeşliği S_b'yi sadeleştirdiği için EŞİK
    etkilenmiyor; bozulan, bloğun kullanıcıyı çağırdığı varsayım denetimi.
    """

    @staticmethod
    def _esik(n):
        m = _motor(port_count=n)
        r = _sessiz(m.calculate)
        e = ((r.get('combustion_stability') or {})
             .get('acoustic_response_threshold') or {})
        return r, e

    @pytest.mark.parametrize('n', [1, 2, 4, 7])
    def test_yanma_yuzeyi_N_pi_D_L_ile_ozdes(self, n):
        r, e = self._esik(n)
        assert e.get('status') == 'modelled'
        fiziksel = (n * np.pi * float(r['port_diameter_initial'])
                    * float(r['grain_length']))
        assert e['burning_surface_area_m2'] == pytest.approx(fiziksel,
                                                             rel=1e-12)

    @pytest.mark.parametrize('n', [2, 4, 7])
    def test_tek_port_formulu_artik_kullanilmiyor(self, n):
        """Çok portlu geometride S_b, ESKİ π·D·L değerinden N kat BÜYÜK.

        (Bu tasarım ailesinde toplam yanma yüzeyi N'den bağımsız çıkıyor —
        D_port_initial N ile küçülüyor — o yüzden ölçüt "N ile büyüsün"
        DEĞİL, "eski tek-port formülünü kullanmasın"dır. Eski yayımlanan
        değerler: N=2 0,10533297 · N=4 0,05266648 · N=7 0,03009513 m².)
        """
        r, cok = self._esik(n)
        eski = np.pi * float(r['port_diameter_initial']) \
            * float(r['grain_length'])
        assert cok['burning_surface_area_m2'] > eski
        assert (cok['burning_surface_area_m2'] / eski) == pytest.approx(
            float(n), rel=1e-9)

    @pytest.mark.parametrize('n', [1, 4])
    def test_yuzey_mach_i_ayni_yuzeyden_turuyor(self, n):
        r, e = self._esik(n)
        rho = float(e['chamber_gas_density_kg_m3'])
        a = float(e['sound_speed_m_s'])
        beklenen = float(r['mdot_f']) / (rho * a
                                         * float(e['burning_surface_area_m2']))
        assert e['surface_mach_M_b'] == pytest.approx(beklenen, rel=1e-12)

    def test_kunye_port_sayisini_adiyla_aniyor(self):
        r, e = self._esik(4)
        kunye = e.get('burning_surface_basis') or ''
        assert 'port_count' in kunye
        assert str(int(r['port_count'])) in kunye


# ---------------------------------------------------------------- B2-08
class TestB208BeslemeBeyani:
    """Çözülmüş chug atalet hattı 'modellenmiyor' ilan edilemez.

    Taban ölçümü (once.json, B2_08; 9071a64): aynı yanıtta
    chug_loop.tau_f_s = 0,00286859921673454 s ve chug_loop.feed_line =
    {line_length_m: 1,5; line_inner_diameter_mm: 12,0; line_area_m2:
    1,1309733552923255e-4; mass_flow_kg_s: 1,1049407340402102;
    dp_injector_Pa: 2554335,85} çözülürken beyan "the only feed element
    solved is the injector orifice plan" diyordu.
    """

    YASAK = 'the only feed element solved is the injector orifice plan'

    @staticmethod
    def _kos():
        m = _motor(feed_line_length_m=1.5, feed_line_inner_diameter_mm=12.0)
        r = _sessiz(m.calculate)
        return m, r

    def test_hat_cozulurken_beyan_yalan_soylemiyor(self):
        m, r = self._kos()
        chug = ((r.get('combustion_stability') or {}).get('chug_loop') or {})
        # Önce çelişkinin İKİ ucunu da bu koşuda ölçelim:
        assert isinstance(chug.get('feed_line'), dict) and chug['feed_line']
        assert chug.get('tau_f_s') is not None
        metin = r['not_modelled']['feed_system']
        assert self.YASAK not in metin

    def test_beyan_cozulen_kalemi_adiyla_aniyor(self):
        _, r = self._kos()
        metin = r['not_modelled']['feed_system']
        assert 'chug' in metin.lower()
        assert 'feed_line_length_m' in metin
        assert 'feed_line_inner_diameter_mm' in metin

    def test_beyan_kalan_yokluklari_hala_ilan_ediyor(self):
        """Daralma, gerçek yokluğu SİLMEZ: donanım hâlâ modellenmiyor."""
        _, r = self._kos()
        metin = r['not_modelled']['feed_system']
        assert metin.startswith('NOT_MODELLED')
        for sozcuk in ('valves', 'regulator', 'instrumentation',
                       'water hammer'):
            assert sozcuk in metin

    def test_hat_verilmeyen_kosuda_da_beyan_tutarli(self):
        m = _motor()
        r = _sessiz(m.calculate)
        assert self.YASAK not in r['not_modelled']['feed_system']


# ---------------------------------------------------------------- OH-Z1-06
class TestOHZ106BasincYogunluguEtkilemiyor:
    """P_feed gerekçesi bayattı: basınç N2O yoğunluk çözümüne girmiyor.

    Taban ölçümü (once.json, OH_Z1_06; 9071a64, T=293,15 K): pressure =
    1 / 30 / 60 / 200 / 1e6 bar için yoğunluk BİREBİR 785,1039703874175
    kg/m³ (benzersiz değer 1). Yorum ise "doyma basıncının üzerinde besleme
    basıncı ver ki SIVI DAL çözülsün" diyordu — o dal Z1 onarımıyla
    (2026-08-27) kapandı.
    """

    def test_yogunluk_basinctan_bagimsiz(self):
        from hrma.data.external_data_fetcher import ExternalDataFetcher
        f = ExternalDataFetcher()
        degerler = set()
        for p in (1.0, 30.0, 60.0, 200.0, 1.0e6):
            r = _sessiz(f.fetch_nist_oxidizer_properties,
                        'n2o', temperature=293.15, pressure=p)
            assert r.get('status') == 'ok'
            degerler.add(r['density'])
        assert len(degerler) == 1, (
            'basınç yoğunluğa geri bağlanmış görünüyor; hibritteki '
            'P_kunye_bar gerekçesi yeniden türetilmeli')

    def test_bayat_gerekce_metni_kodda_kalmadi(self):
        """Yorumun kendisi bir iddiadır; yanlış iddia kodda duramaz."""
        import inspect

        from hrma.engines import hybrid_rocket_engine as hy
        kaynak = inspect.getsource(hy)
        assert 'sıvı dal çözülsün' not in kaynak
        assert 'P_kunye_bar' in kaynak


# ---------------------------------------------------------------- P15B2-09
class TestP15B209KapakBirlesimiTekKaynak:
    """Kapak birleşimi varsayılanları TEK tanım noktasından gelmeli.

    Taban ölçümü (once.json, P15B2_09; 9071a64): aynı sözleşme üç motor
    dosyasında üç kez yazılıydı (kopya sayısı 3), ortak üç alan bugün
    ayrışmıyordu (ayrışan 0) ama eşitliği sınayan bekçi YOKTU — sessiz
    ayrışma serbestti.
    """

    ORTAK = ('size', 'property_class', 'bolt_count_range')

    def test_hibrit_kopyasi_tek_kaynaktan_turuyor(self):
        for alan in self.ORTAK:
            assert CLOSURE_JOINT_DEFAULTS[alan] == \
                bj.CLOSURE_JOINT_DEFAULTS[alan]
        assert (CLOSURE_JOINT_DEFAULTS['member_material']
                == bj.CLOSURE_JOINT_MEMBER_MATERIAL_DEFAULT)

    def test_sivi_kopyasi_tek_kaynakla_ayni(self):
        from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
        kopya = LiquidRocketEngine.LIQUID_CLOSURE_JOINT_DEFAULTS
        for alan in self.ORTAK:
            assert kopya[alan] == bj.CLOSURE_JOINT_DEFAULTS[alan], (
                f'sıvı motorun {alan} varsayılanı tek kaynaktan AYRIŞTI')
        assert (kopya['member_material']
                == bj.CLOSURE_JOINT_MEMBER_MATERIAL_DEFAULT)

    def test_kati_kopyasi_tek_kaynakla_ayni(self):
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        kopya = SolidRocketEngine.SOLID_CLOSURE_JOINT_DEFAULTS
        for alan in self.ORTAK:
            assert kopya[alan] == bj.CLOSURE_JOINT_DEFAULTS[alan], (
                f'katı motorun {alan} varsayılanı tek kaynaktan AYRIŞTI')

    def test_kati_uye_malzemesini_BILEREK_tasimiyor(self):
        """D15/P2B2-12: katıda üye malzemesi kasadan türetilir."""
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        assert 'member_material' not in \
            SolidRocketEngine.SOLID_CLOSURE_JOINT_DEFAULTS

    def test_yayimlanan_birlesim_tek_kaynagi_yankiliyor(self):
        m = _motor(closure_bolt_count=8)
        r = _sessiz(m.calculate)
        b = r.get('closure_joint') or {}
        if b.get('status') == 'NOT_MODELLED' or not b:
            pytest.skip('birleşim bu koşuda boyutlandırılmadı')
        assert b.get('bolt_size') == bj.CLOSURE_JOINT_DEFAULTS['size']
        assert (b.get('property_class')
                == bj.CLOSURE_JOINT_DEFAULTS['property_class'])
