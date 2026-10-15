"""ÖH Dalga-21 · sıvı kulvarı a1 — mutasyon kanıtlı bekçiler.

Ölçüm: ``docs/scofield/raw/OH/D21/sivi/a1/once.json`` ⟷ ``sonra.json``
(betik ``olcum.py``); ters mutasyonlar ``mutasyon.py`` / ``mutasyon.json``.

**OH-D20-02** — çan sapma verimi λ tek sabitti: ``bell_80`` (çıkış 8,5°,
%80 uzunluk) ile ``bell_60`` (çıkış 12,0°, %60 uzunluk) AYNI 0,985'i
alıyor ve teslim Isp'leri birebir aynı (333,2237 s) çıkıyordu. λ artık
kontura bağlı: referans %80 çan yayımlanan değeri AYNEN alır, öteki çanlar
Huzel & Huang SP-125 Böl. 1 eşdeğer-koni ORANIyla taşınır (bell_60 →
0,9730507, Isp 329,1813 s).

**OH-D20-08** — ``_tank_pressure_from_npsh`` per-pompa ``except Exception:
continue`` SESSİZDİ. Ölçüldü: LOX buhar basıncı çözülemediğinde defter iki
pompadan bire düşüyor, tank basıncı 4,3900 → 2,3691 bar'a (-%46,0)
iniyor ve blok hâlâ ``status='sized'`` diyordu. Artık fail-closed:
sayı yayımlanmaz, düşen pompa ve istisnası ``excluded_pumps``ta.

**OH-D20-09** — NPSH ÇİFT MARJ. SP-8109 §3.2.1.2 hız-yükü kuralı zaten
marjlı bir kabul tabanıdır; üstüne SP-8107'nin 1,25 oranı biniyordu
(16,8865 m taban → 21,1081 m yayımlanan; tank 2,8895 → 3,3619 bar).
Tek marj sözleşmesi: ``NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE = 1,0``.

**P3B3-10** — basınç beslemeli çevrimde (pompa/türbin YOK, kartlar
``None``) pompa uyarısı kullanıcıya gidiyordu: ölçüldü, 5 uyarıdan biri
``warn.liquid.pump_speed_capped``.

**P3B3-12** — hat pürüzlülüğünün kökeni beyan edilmiyordu; modül künyeye
"UNDECLARED provenance" yazıyor, motorun kendi docstring'i ise sayıyı
"ölçüyle verir" diye anlatıyordu. Sayı bir EL KİTABI tablosu değeridir.

**P3B4-04** — çevrim yolunda ``power_output`` çözücünün mil başına
kapanışlarının TOPLAMINDAN gelirken ``power_output_basis`` hâlâ "türbin
mil gücü = TOPLAM POMPA mil gücü" diyordu.

**P3B4-10** — ``npsh_margin`` paydası ``max(abs(NPSH_req), 1e-9)`` ile
korunuyordu; oran tanımsızken bu koruma SAYI üretiyordu (savcı ölçümü
-64757,02 %).

**P3B4-11** — ``eta_c_star`` künyesi anahtarın VARLIĞINDAN kuruluyordu:
bant dışı (reddedilen) ``combustion_efficiency=300`` girdisinde sayı
1,000'e düşerken künye "user input (combustion efficiency)" diyordu.

**P15B1-07** — ``efficiency_breakdown``ın altı ``_loss`` sonekli anahtarı
VERİM taşıyordu (``divergence_loss = 98,50``). Doğru adlı ikinci döküm
(``efficiency_by_mechanism``) + makine-okur takma ad haritası eklendi.

**P15B2-07** — ``calculate_injector_design`` merkezî ΔP/Pc tablosunun beş
satır-içi kopyasını kullanıyordu; künye "tek tanım yeri" diyordu.
"""

import contextlib
import io
import json
import os

import numpy as np
import pytest

from hrma.constants import LAMBDA_BELL, PA_PER_BAR, G_0, lambda_conical
from hrma.analysis import turbopump_sizing as tp
from hrma.analysis.valve_feedline import ROUGHNESS_PROVENANCE_UNDECLARED
import hrma.engines.liquid_rocket_engine as lre
from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D21', 'sivi', 'a1')

#: Ağ yok — motora BOŞ ama VAR olan itici kaydı verilir
#: (test_sivi_npsh_tek_kaynak ile aynı çevrimdışı desen).
CEVRIMDISI = {'rp1': {}, 'lox': {}}


def _motor(**kw):
    ctor = dict(thrust=250000.0, chamber_pressure=150.0, mixture_ratio=2.6,
                fuel_type='rp1', oxidizer_type='lox',
                propellant_data=CEVRIMDISI)
    ovr = dict(expansion_ratio=25.0, burn_time=100.0)
    for a, b in kw.items():
        (ctor if a in ctor or a in ('cooling_type', 'injector_type',
                                    'feed_system_type') else ovr)[a] = b
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            m = LiquidRocketEngine(overrides=ovr, **ctor)
            m.calculate_nozzle_geometry()
    return m


@pytest.fixture(scope='module')
def kaynak():
    return open(lre.__file__, encoding='utf-8').read()


# ===========================================================================
# OH-D20-02 — çan λ'sı kontura BAĞLI
# ===========================================================================
class TestOHD2002CanLambdaKontura:

    def test_bell60_ile_bell80_ayni_lambdayi_almaz(self):
        l80, _ = _motor(nozzle_type='bell_80')._divergence_efficiency()
        l60, _ = _motor(nozzle_type='bell_60')._divergence_efficiency()
        assert l80 != l60, (
            'bell_80 (çıkış 8,5°) ile bell_60 (çıkış 12,0°) aynı sapma '
            'verimini alamaz; kısa çan daha çok sapma kaybeder')
        assert l60 < l80, 'kısa çanın λ\'sı büyük olamaz'

    def test_referans_kontur_yayimlanan_degeri_aynen_alir(self):
        """%80 çan = kanonik Rao konturu → LAMBDA_BELL değişmez."""
        lam, _ = _motor(
            nozzle_type=lre.LAMBDA_BELL_REFERENCE_CONTOUR
        )._divergence_efficiency()
        assert lam == pytest.approx(float(LAMBDA_BELL), rel=1e-12)

    def test_oran_esdeger_koni_ile_kurulur_sayi_uydurulmaz(self):
        """λ(kontur) = LAMBDA_BELL · λ_koni(ᾱ_kontur)/λ_koni(ᾱ_ref)."""
        g60 = lre.NOZZLE_TYPE_GEOMETRY['bell_60']
        gref = lre.NOZZLE_TYPE_GEOMETRY[lre.LAMBDA_BELL_REFERENCE_CONTOUR]
        beklenen = float(LAMBDA_BELL) * (
            float(lambda_conical(0.5 * (g60['half_angle']
                                        + g60['exit_angle'])))
            / float(lambda_conical(0.5 * (gref['half_angle']
                                          + gref['exit_angle']))))
        lam, src = _motor(nozzle_type='bell_60')._divergence_efficiency()
        assert lam == pytest.approx(beklenen, rel=1e-12)
        assert lam == pytest.approx(0.9730507506639047, rel=1e-9)
        assert 'equivalent-cone' in src
        assert 'LAMBDA_BELL' in src

    def test_teslim_isp_konturu_gorur(self):
        """Ölçüldü (once.json): iki kontur da 333,2237 s veriyordu."""
        i80 = float(_motor(nozzle_type='bell_80').isp_vac)
        i60 = float(_motor(nozzle_type='bell_60').isp_vac)
        assert i80 != i60
        assert i60 < i80
        assert i80 - i60 > 1.0, 'fark ölçüm gürültüsü olamaz (ölçüldü 4,04 s)'


# ===========================================================================
# OH-D20-08 — per-pompa istisnası SESSİZ değil, fail-closed
# ===========================================================================
class TestOHD2008SessizPompaDusmesi:

    @staticmethod
    def _lox_patlatilmis_motor():
        m = _motor()
        orj = m._npsh_vapor_pressure

        def _patlat(itici):
            if str(itici) == 'lox':
                raise RuntimeError('bekçi: lox buhar basıncı çözülemedi')
            return orj(itici)

        m._npsh_vapor_pressure = _patlat
        m._npsh_tank_cache = None
        return m

    def test_saglam_motorda_iki_pompa_da_defterde(self):
        rapor = _motor()._npsh_tank_sizing_report()
        assert rapor['status'] == 'sized'
        assert set(rapor['per_pump']) == {'oxidizer_pump', 'fuel_pump'}

    def test_bir_pompa_dusunce_sayi_YAYIMLANMAZ(self):
        rapor = self._lox_patlatilmis_motor()._npsh_tank_sizing_report()
        assert rapor['status'] == 'not_solved', (
            'eksik pompa kümesiyle "boyutlandırıldı" hükmü verilemez: '
            'türetim iki pompanın İSTEDİĞİ basıncın BÜYÜĞÜdür')
        assert 'bar' not in rapor
        assert 'governing_pump' not in rapor

    def test_dusen_pompa_ADIYLA_ve_istisnasiyla_beyan_edilir(self):
        rapor = self._lox_patlatilmis_motor()._npsh_tank_sizing_report()
        dusen = rapor['excluded_pumps']
        assert 'oxidizer_pump' in dusen
        assert 'RuntimeError' in dusen['oxidizer_pump']
        assert 'fail_closed_basis' in rapor
        # Sağ kalan pompanın sayısı KAYBOLMAZ, ama "tank basıncı" diye
        # yayımlanmaz — ayrı adla durur.
        assert 'fuel_pump' in rapor['solved_pumps_bar']

    def test_sag_kalanin_sayisi_tank_basinci_diye_gecmez(self):
        """Ölçüldü: sessiz düşmede 4,3900 → 2,3691 bar (-%46,0)."""
        m = self._lox_patlatilmis_motor()
        rapor = m._npsh_tank_sizing_report()
        assert rapor.get('bar') is None
        assert rapor['solved_pumps_bar']['fuel_pump'] < 3.0


# ===========================================================================
# OH-D20-09 — TEK MARJ SÖZLEŞMESİ
# ===========================================================================
class TestOHD2009TekMarj:

    def test_hiz_yuku_kuralinin_ustune_oran_binmez(self):
        assert tp.NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE == 1.0
        assert 'SINGLE-MARGIN CONTRACT' in tp.NPSH_SINGLE_MARGIN_CONTRACT

    def test_yayimlanan_gereksinim_kural_tabanidir(self):
        """Ölçüldü (once.json): 16,8865 m kural → 21,1081 m yayımlanıyordu."""
        rapor = _motor()._npsh_tank_sizing_report()
        assert rapor['margin_factor'] == pytest.approx(1.0, rel=1e-12)
        for ad, blok in rapor['per_pump'].items():
            beklenen = tp.npsh_required_velocity_head_m(
                blok['inlet_velocity_m_s'], blok['velocity_head_factor'])
            assert blok['npsh_required_m'] == pytest.approx(beklenen,
                                                            rel=1e-12), ad

    def test_tank_basinci_tek_marjla_kapanir(self):
        m = _motor()
        rapor = m._npsh_tank_sizing_report()
        for ad, blok in rapor['per_pump'].items():
            p = tp.tank_pressure_from_npsh_Pa(
                blok['vapor_pressure_Pa'],
                (m.rho_ox if ad == 'oxidizer_pump' else m.rho_fuel),
                blok['npsh_required_m'],
                blok['suction_loss_bar'] * PA_PER_BAR,
                tp.NPSH_STATIC_HEAD_DEFAULT_M,
                tp.NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE)
            assert blok['required_tank_pressure_bar'] == pytest.approx(
                p / PA_PER_BAR, rel=1e-9), ad

    def test_pompa_karti_da_tek_marji_yayimlar(self):
        m = _motor()
        with contextlib.redirect_stdout(io.StringIO()):
            sonuc = m.calculate_performance()
        ta = sonuc['detailed_feed_system']['turbopump_analysis']
        for ad in ('oxidizer_pump', 'fuel_pump'):
            kart = ta[ad]
            assert kart['npsh_margin_factor'] == pytest.approx(1.0, rel=1e-12)
            assert 'SINGLE-MARGIN CONTRACT' in kart['npsh_margin_factor_basis']

    def test_cift_marj_geri_gelirse_tank_basinci_yukselir(self):
        """Sözleşmenin SAYISAL büyüklüğü: k=1,25 tank basıncını yükseltir."""
        kural = tp.npsh_required_velocity_head_m(
            12.0, tp.NPSH_VELOCITY_HEAD_FACTORS['cryogenic_ox'])
        tek = tp.tank_pressure_from_npsh_Pa(
            1.0e5, 1141.0, kural, 0.0, 0.0,
            tp.NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE)
        cift = tp.tank_pressure_from_npsh_Pa(
            1.0e5, 1141.0, kural, 0.0, 0.0, tp.NPSH_MARGIN_FACTOR_DEFAULT)
        assert tek / 1e5 == pytest.approx(2.889496, rel=1e-6)
        assert cift / 1e5 == pytest.approx(3.361870, rel=1e-6)


# ===========================================================================
# P3B3-10 — basınç beslemede pompa/türbin uyarısı yayımlanmaz
# ===========================================================================
class TestP3B310BasincBeslemeUyarilari:

    @staticmethod
    def _kosum(cycle):
        m = _motor(thrust=5000.0, chamber_pressure=20.0, mixture_ratio=2.2,
                   expansion_ratio=8.0, engine_cycle=cycle)
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                return m, m.calculate_performance()

    def test_basinc_beslemede_pompa_uyarisi_yok(self):
        m, sonuc = self._kosum('pressure_fed')
        kodlar = {w['code'] for w in m.design_warnings}
        assert not (kodlar & LiquidRocketEngine.PUMP_ONLY_WARNING_CODES), (
            'basınç beslemeli motorda pompa/türbin YOKTUR '
            '(turbopump_analysis.applicable=False); olmayan donanım için '
            'uyarı üretilemez')

    def test_bastirma_BEYAN_edilir_sessiz_degil(self):
        m, sonuc = self._kosum('pressure_fed')
        ta = sonuc['detailed_feed_system']['turbopump_analysis']
        assert ta['applicable'] is False
        assert isinstance(ta['suppressed_pump_warnings'], list)
        assert 'warn.liquid.pump_speed_capped' in ta[
            'suppressed_pump_warnings'], (
            'ölçüldü (once.json P3B3-10): basınç beslemeli koşumda tam bu '
            'kod kullanıcıya gidiyordu')
        assert 'pressure-fed cycle' in ta['suppressed_pump_warnings_basis']

    def test_turbopompali_cevrimde_kanal_ACIK_kalir(self):
        """Bastırma kapsam hükmüdür; uyarı kanalını topyekûn kapatmaz."""
        m, sonuc = self._kosum('gas_generator')
        ta = sonuc['detailed_feed_system']['turbopump_analysis']
        assert ta['applicable'] is True
        assert ta['suppressed_pump_warnings'] is None
        m2 = _motor()
        m2.engine_cycle = 'gas_generator'
        m2._warn('warn.liquid.pump_speed_capped', 'info')
        assert any(w['code'] == 'warn.liquid.pump_speed_capped'
                   for w in m2.design_warnings)


# ===========================================================================
# P3B3-12 — hat pürüzlülüğünün KÖKENİ beyan edilir
# ===========================================================================
class TestP3B312PuruzlulukKokeni:

    @pytest.fixture(scope='class')
    def hat(self):
        m = _motor()
        with contextlib.redirect_stdout(io.StringIO()):
            sonuc = m.calculate_performance()
        return sonuc['detailed_feed_system']['valve_feedline']

    def test_koken_el_kitabi_tablosu_olarak_beyan_edilir(self, hat):
        for ad in ('oxidizer_line', 'fuel_line'):
            girdi = hat[ad]['line']['inputs']
            assert girdi['roughness_provenance'] == 'handbook_table', ad
            assert girdi['roughness_source'] != (
                ROUGHNESS_PROVENANCE_UNDECLARED), ad
            assert 'HANDBOOK' in girdi['roughness_source'], ad
            assert girdi['roughness_m'] == pytest.approx(
                lre.FEED_LINE_ROUGHNESS_M, rel=1e-12)

    def test_kunye_olcum_iddia_etmez(self, hat, kaynak):
        for ad in ('oxidizer_line', 'fuel_line'):
            src = hat[ad]['line']['inputs']['roughness_source']
            assert 'MEASURED' not in src, ad
        assert 'ölçüyle (``FEED_LINE_ROUGHNESS_M``) verir' not in kaynak, (
            'motorun kendi docstring\'i el kitabı değerini "ölçü" diye '
            'anlatamaz')


# ===========================================================================
# P3B4-04 — türbin kartının künyesi sayının kaynağıyla birlikte tazelenir
# ===========================================================================
class TestP3B404TurbinKunyesi:

    def test_cevrim_yolunda_power_output_basis_cevrimi_anlatir(self):
        m = _motor(engine_cycle='staged_combustion')
        with contextlib.redirect_stdout(io.StringIO()):
            sonuc = m.calculate_performance()
        dfs = sonuc['detailed_feed_system']
        kart = dfs['turbopump_analysis']['turbine']
        cyc = dfs['engine_cycle_solution']
        assert cyc['status'] == 'converged'
        assert kart['power_output'] == pytest.approx(
            cyc['turbine_power_total_W'] / 1e3, rel=1e-9)
        basis = kart['power_output_basis']
        assert 'turbine_power_total_W' in basis, (
            'sayı çözücünün mil başına kapanışlarının TOPLAMIndan geliyor; '
            'künye hâlâ "toplam pompa mil gücü" diyemez')
        assert 'shaft(s)' in basis
        assert 'equals the total pump shaft power' not in basis

    def test_geometri_cozulmediginde_type_kunyesi_kartin_kendisini_soyler(self):
        kart = {'type': 'Single-stage axial'}
        LiquidRocketEngine._reconcile_turbine_geometry(kart, None)
        assert kart['geometry_source'] == 'not_sized'
        assert "this card's own single-stage assumption" in kart['type_source']

    def test_geometri_cozuldugunde_type_kunyesi_module_gecer(self):
        kart = {'type': 'Single-stage axial'}
        LiquidRocketEngine._reconcile_turbine_geometry(kart, {
            'status': 'modelled', 'pitch_speed_m_s': 300.0,
            'stage_count': 3, 'mean_diameter_m': 0.2,
            'arrangement': 'pressure_compounded_impulse_equal_work'})
        assert kart['type'].startswith('3-stage axial impulse')
        assert 'turbopump_sizing' in kart['type_source']


# ===========================================================================
# P3B4-10 — dejenere paydayla 'marj' üretilmez
# ===========================================================================
class TestP3B410DejenereMarj:

    @staticmethod
    def _marjlar(ox_req, fuel_req=30.0):
        m = _motor()
        drops = m._calculate_feed_system_pressure_drops()
        ox = {'npsh_required': ox_req, 'npsh_available': 6.0}
        fuel = {'npsh_required': fuel_req, 'npsh_available': 35.0}
        return m._feed_performance_margins(drops, ox, fuel, {}, False)

    def test_sifir_npsh_gereksiniminde_sayi_uretilmez(self):
        """Ölçüldü (savcı): payda koruması -64757,02 % üretiyordu."""
        marj = self._marjlar(0.0)
        assert marj['npsh_margin'] is None
        assert 'oxidizer_pump' in marj['npsh_margin_undefined_pumps']
        assert 'NOT published' in marj['npsh_margin_basis']

    def test_nan_gereksinimde_de_sayi_uretilmez(self):
        marj = self._marjlar(float('nan'))
        assert marj['npsh_margin'] is None
        assert 'oxidizer_pump' in marj['npsh_margin_undefined_pumps']

    def test_saglam_pompalarda_marj_yayimlanir(self):
        # ox: (6,0-5,0)/5,0 = %20; fuel: (35,0-30,0)/30,0 = %16,667 →
        # bağlayıcı (kötü) pompa fuel_pump.
        marj = self._marjlar(5.0)
        assert marj['npsh_margin'] == pytest.approx(50.0 / 3.0, rel=1e-9)
        assert marj['npsh_margin_undefined_pumps'] is None
        assert 'binding (worst) pump' in marj['npsh_margin_basis']

    def test_urun_kosumunda_marj_makul_bantta(self):
        m = _motor()
        with contextlib.redirect_stdout(io.StringIO()):
            sonuc = m.calculate_performance()
        marj = sonuc['detailed_feed_system']['performance_margins']
        assert marj['npsh_margin'] is not None
        assert -100.0 < marj['npsh_margin'] < 1000.0


# ===========================================================================
# P3B4-11 — reddedilen η_c* girdisi 'kullanıcı girdisi' diye etiketlenmez
# ===========================================================================
class TestP3B411ReddedilenYanmaVerimi:

    def test_bant_disi_girdi_reddedilir_ve_kunye_bunu_soyler(self):
        m = _motor(combustion_efficiency=300.0)
        assert float(m.eta_c_star) == pytest.approx(1.0, rel=1e-12)
        assert 'not supplied' in m.eta_c_star_source
        assert 'not supplied' in (m._delivered_eff or {})['eta_c_star_source']
        assert any(w['code'] == 'warn.liquid.input_out_of_range'
                   for w in m.design_warnings)

    def test_kabul_edilen_girdi_kullanici_girdisi_der(self):
        m = _motor(combustion_efficiency=90.0)
        assert float(m.eta_c_star) == pytest.approx(0.90, rel=1e-12)
        assert m.eta_c_star_source == 'user input (combustion efficiency)'
        assert (m._delivered_eff or {})['eta_c_star_source'] == (
            'user input (combustion efficiency)')

    def test_uc_kunye_de_TEK_kaynaktan(self):
        m = _motor(combustion_efficiency=300.0)
        with contextlib.redirect_stdout(io.StringIO()):
            sonuc = m.calculate_performance()
        inj = sonuc['injection_system']['combustion_efficiency_source']
        ca = sonuc['combustion_analysis']['combustion_analysis'][
            'combustion_efficiency_source']
        eff = sonuc['efficiency_breakdown']['loss_sources'][
            'combustion_incomplete']
        assert inj == ca == m.eta_c_star_source
        assert 'not supplied' in eff


# ===========================================================================
# P15B1-07 — verim dökümünde ad↔anlam
# ===========================================================================
class TestP15B107AdAnlam:

    @pytest.fixture(scope='class')
    def eb(self):
        m = _motor()
        with contextlib.redirect_stdout(io.StringIO()):
            sonuc = m.calculate_performance()
        return sonuc['efficiency_breakdown']

    def test_dogru_adli_dokum_yayimlanir(self, eb):
        blok = eb['efficiency_by_mechanism']
        assert isinstance(blok, dict) and blok
        assert not any(a.endswith('_loss') for a in blok), (
            'VERİM taşıyan bir alan "_loss" soneki taşıyamaz')
        assert 'divergence_efficiency' in blok

    def test_takma_ad_haritasi_iki_dokumu_ortusturur(self, eb):
        harita = eb['efficiency_breakdown_aliases']
        assert harita == lre.EFFICIENCY_MECHANISM_NAMES
        assert set(harita) == set(eb['efficiency_breakdown'])
        for tarihsel, yeni in harita.items():
            assert eb['efficiency_by_mechanism'][yeni] == pytest.approx(
                eb['efficiency_breakdown'][tarihsel], rel=1e-12), tarihsel

    def test_verim_ve_kayip_ayni_mekanizmada_100_yapar(self, eb):
        for tarihsel, yeni in eb['efficiency_breakdown_aliases'].items():
            kayip_ad = yeni.replace('_efficiency', '_loss')
            assert (eb['efficiency_by_mechanism'][yeni]
                    + eb['loss_by_mechanism'][kayip_ad]) == pytest.approx(
                        100.0, abs=1e-9), yeni

    def test_birim_beyanlari_ayrik(self, eb):
        assert 'EFFICIENCY' in eb['efficiency_by_mechanism_unit']
        assert 'LOSS' in eb['loss_by_mechanism_unit']


# ===========================================================================
# P15B2-07 — enjektör ΔP/Pc tek tanım yerinden
# ===========================================================================
class TestP15B207EnjektorDPTekKaynak:

    def test_satir_ici_kopya_kalmadi(self, kaynak):
        kopya = [s.strip() for s in kaynak.splitlines()
                 if 'pressure_drop_factor = 0.' in s]
        assert kopya == [], (
            'ölçüldü (once.json P15B2-07): beş satır-içi kopya vardı '
            '(0,22 / 0,18 / 0,28 / 0,15 / 0,20)')

    @pytest.mark.parametrize('tip', ['impinging', 'coaxial', 'showerhead',
                                     'pintle', 'unlike_impinging'])
    def test_yayimlanan_dp_tablodan_gelir(self, tip):
        m = _motor(injector_type=tip)
        with contextlib.redirect_stdout(io.StringIO()):
            inj = m.calculate_injector_design()
        beklenen = lre.INJECTOR_TYPE_DP_FRACTION.get(
            tip, lre.INJECTOR_TYPE_DP_FRACTION_DEFAULT)
        assert inj['ox_pressure_drop'] / float(m.P_c) == pytest.approx(
            beklenen, rel=1e-12)
        assert m._injector_dp_fraction() == pytest.approx(beklenen, rel=1e-12)

    def test_tablo_degisince_yayimlanan_dp_DE_degisir(self, monkeypatch):
        """Kusur GİZİLDİ: bugün 5/5 eşit. Bekçi kopyayı davranışla arar."""
        monkeypatch.setitem(lre.INJECTOR_TYPE_DP_FRACTION, 'impinging', 0.33)
        m = _motor(injector_type='impinging')
        with contextlib.redirect_stdout(io.StringIO()):
            inj = m.calculate_injector_design()
        assert inj['ox_pressure_drop'] / float(m.P_c) == pytest.approx(
            0.33, rel=1e-12), (
            'satır-içi kopya geri gelirse bu düğüm 0,22\'de takılır')


# ===========================================================================
# Kanıt hijyeni
# ===========================================================================
def test_olcum_kanitlari_diskte():
    for ad in ('once.json', 'sonra.json', 'mutasyon.json'):
        yol = os.path.join(KANIT, ad)
        assert os.path.exists(kanit_gerekli(yol)), yol
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            assert json.load(f)
