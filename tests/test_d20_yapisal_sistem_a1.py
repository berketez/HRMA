"""ÖH Dalga-20 / yapisal-sistem aşama 1 — bekçiler.

Ölçüm betiği: ``docs/scofield/raw/OH/D20/yapisal-sistem/a1/olcum.py``
(çıktılar ``once.json`` / ``sonra.json``, taban 14acd1d).
Ters mutasyon kanıtı: aynı dizinde ``mutasyon.json``.

Kapsanan kalemler:
  P5B4-04  regresyon eğrisi: yanma süresi işaret/sonluluk kapısı
  P5B4-05  regresyon eğrisi: a, n, rho_f, D_port, L kapısı
  P5B3-13  su koçu bağlaması VANA giriş basıncını alır (hat çıkışı)
  P5B3-14  Crane (L/D)_eş yerel kaybı laminer rejimde ALT SINIR olarak beyan
  P5B3-15  hat girdi kapısı: |dz| <= L, p_v < p_giriş, mutlak basınç >= 0
  P5B3-16  autogenous boşaltma verimi geçerlilik bandı
  P5B2-18  SAFETY_MODEL künyesinin sayıları ÖLÇÜMLE aynı kalır (senkron)
  P5B3-10  D18 pürüzlülük-köken onarımı bu tabanda hâlâ duruyor
  OH-D20-09 NPSH çift marjı ÖLÇÜLDÜ (onarım kardeş dalda — engel bekçisi)
"""
import ast
import json
import math
import pathlib
import re

import pytest

from hrma.analysis.pressurant_sizing import (EXPULSION_EFFICIENCY_DEFAULT,
                                             EXPULSION_EFFICIENCY_VALID,
                                             autogenous_pressurant,
                                             regulated_pressurant)
from hrma.analysis.regression_analysis import (
    NonPhysicalOxidizerFlux,
    NonPhysicalRegressionInput,
    REGRESSION_EXPONENT_BAND_INCLUSIVE,
    REGRESSION_EXPONENT_VALID,
    RegressionAnalyzer)
from hrma.analysis.valve_feedline import (analyze_valve_feedline,
                                          line_pressure_drop)
from tests.support.kanit import kanit_gerekli


# ===========================================================================
# Ortak sabitler — ölçüm betiğiyle BİREBİR aynı çalışma noktaları
# ===========================================================================
REG_TABAN = {'fuel_type': 'htpb', 'burn_time': 10.0, 'mdot_ox': 1.0,
             'port_diameter_initial': 0.03, 'grain_length': 0.5}

HAT_TABAN = dict(mass_flow_kg_s=2.0, density_kg_m3=1000.0,
                 viscosity_Pa_s=1.0e-3, line_id_m=0.02, line_length_m=25.0,
                 inlet_pressure_Pa=30.0e5,
                 fittings={'elbow_90_long_radius': 6})

TAM_TABAN = dict(HAT_TABAN, valve_pressure_drop_Pa=2.0e5,
                 wall_thickness_m=0.002, fluid='water',
                 fittings={'elbow_90_long_radius': 6,
                           'ball_valve_full_bore': 1})


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _reg_uc(istemci, **degis):
    r = istemci.post('/api/regression-analysis',
                     json={'motor_data': dict(REG_TABAN, **degis)})
    return r.status_code, r.get_json()


# ===========================================================================
# P5B4-04 — yanma süresi kapısı
# ===========================================================================
class TestP5B404YanmaSuresiKapisi:
    """ÖLÇÜLDÜ (``once.json`` P5B4-04, çözümleyici yüzü):

    ==================  ===========================  ==============
    ``burn_time``       ``port_diameter[-1]`` [mm]   ``time[-1]``
    ==================  ===========================  ==============
    10 s (sağlıklı)     57,265776718966              10,0
    **-5 s**            **-83,716894591446**         **-5,0**
    **0 s**             30,0 (eğri DONUK, dt = 0)    0,0
    **1e6 s**           **43 006,671996626**         1e6
    ==================  ===========================  ==============

    Dördünde de ``warnings`` BOŞtu. ``inf`` ve ``nan`` reddediliyordu ama
    YANLIŞ ALAN ADIYLA ("oxidizer mass flux ... got 0.0").
    """

    @pytest.mark.parametrize('deger', [-5.0, 0.0, float('inf'),
                                       float('nan'), -1e-12])
    def test_fizik_disi_yanma_suresi_adiyla_reddedilir(self, deger):
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer().analyze_regression_vs_time(
                dict(REG_TABAN, burn_time=deger))
        assert ex.value.field == 'burn_time'

    # --- ÖH D26 / P5B4-04 (Fable-D20 ŞART maddesi 3) ------------------
    # D20 kapısı yalnız İŞARET + SONLULUK kapatıyordu; ARALIK açıktı.
    # ÖLÇÜLDÜ (D26 tabanı 7751531, ``once.json`` P5B4-04, aynı REG_TABAN):
    #     burn_time =     300 s   -> port_diameter[-1] =    250 495,774 mm
    #     burn_time = 300,001 s   -> port_diameter[-1] =    250 496,166 mm
    #     burn_time =     1e6 s   -> port_diameter[-1] = 19 377 584,490 mm
    # Üçünde de ``warnings`` BOŞ. Aşağıdaki üç düğüm SEÇİLEN davranışı
    # mandallar: üst uç kanonik tablodan (motor_validator.limits) gelir,
    # alt uç BİLEREK açıktır.

    @pytest.mark.parametrize('deger', [300.001, 1e6, 1e12])
    def test_kanonik_ust_sinirin_ustu_adiyla_reddedilir(self, deger):
        """Üst uç kapandı — ve reddin gerekçesi TEK KAYNAĞI adıyla anıyor."""
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer().analyze_regression_vs_time(
                dict(REG_TABAN, burn_time=deger))
        assert ex.value.field == 'burn_time'
        assert 'out_of_range' in str(ex.value)
        assert 'motor_validator.limits' in str(ex.value)

    def test_ust_sinirin_kendisi_hala_kabul(self):
        """Bant KAPALI aralıktır: tam üst uç (300 s) reddedilmez."""
        from hrma.validation.motor_validation import motor_validator
        ust = float(motor_validator.limits['burn_time']['max'])
        r = RegressionAnalyzer().analyze_regression_vs_time(
            dict(REG_TABAN, burn_time=ust))
        assert r['time'][-1] == pytest.approx(ust)

    def test_alt_sinir_EKLENMEDI(self):
        """Onarım YENİ bir alt-sınır reddi doğurmaz — bilerek.

        Kanonik tablonun ``min``i 0,1 s'tir; kütüphane yüzü onu DAYATMAZ
        (``app.py::_kanonik_ust_sinirlar`` sözleşmesi: "Aralığın altı 0.0
        verilir"). 0,05 s tabanda kabul ediliyordu (ölçüldü: port
        30 205,504 mm) ve kabul edilmeye devam eder; bu düğüm kapının
        sessizce iki taraflı olmasını engeller.
        """
        from hrma.validation.motor_validation import motor_validator
        alt = float(motor_validator.limits['burn_time']['min'])
        r = RegressionAnalyzer().analyze_regression_vs_time(
            dict(REG_TABAN, burn_time=alt / 2.0))
        assert r['time'][-1] == pytest.approx(alt / 2.0)

    def test_kanonik_band_KOPYALANMADI(self):
        """Sayı ikinci kez yazılmadı: modül tabloyu OKUR (Doktrin 4)."""
        kaynak = (pathlib.Path(__file__).resolve().parents[1] / 'hrma'
                  / 'analysis' / 'regression_analysis.py').read_text(
                      encoding='utf-8')
        assert 'motor_validator.limits' in kaynak
        # 300 sayısı KOD olarak modüle YAZILMAMIŞ olmalı (künye metninde
        # ölçüm tablosu olarak geçebilir; sayan taraf AST'dir, metin değil).
        agac = ast.parse(kaynak)
        sabitler = {float(d.value) for d in ast.walk(agac)
                    if isinstance(d, ast.Constant)
                    and isinstance(d.value, (int, float))
                    and not isinstance(d.value, bool)}
        assert 300.0 not in sabitler, (
            'kanonik üst sınır (300 s) modüle KOPYALANMIŞ — tek kaynak '
            'motor_validator.limits olmalı')

    def test_sonsuz_sure_artik_dogru_alani_gosteriyor(self):
        """Taban ``inf``i ``NonPhysicalOxidizerFlux`` ile reddediyordu:
        kullanıcı ``mdot_ox``u düzeltmeye çalışıyordu, oysa hatalı alan
        ``burn_time``dı."""
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer().analyze_regression_vs_time(
                dict(REG_TABAN, burn_time=float('inf')))
        assert 'burn_time' in str(ex.value)
        assert 'oxidizer mass flux' not in str(ex.value)

    def test_saglikli_egri_BIT_AYNI(self):
        """ÖH D23 / P5B4-12 ile ÇEVRİLDİ — gerekçe aşağıda.

        Bu bekçi D20'de sağlıklı kolun sayısını çiviliyordu ve çivilediği
        değer (57,265776718965974 mm) AÇIK EULER şemasının kesme hatasını
        içeriyordu: 'ox' kipinde ODE'nin kapalı çözümü vardır
        (dr/dt = a (mdot/pi)^n r^(-2n) => r(t) = [r0^(2n+1) +
        (2n+1) a (mdot/pi)^n t]^(1/(2n+1))) ve aynı çalışma noktasında
        57,192468010394364 mm verir; eski sayının bağıl hatası **+%0,128**
        idi ve daima yukarı yönlüydü. Yani bekçi kusuru KORUYORDU.

        Şema RK4'e çıkarıldığı için sayı DEĞİŞTİ. Bekçi artık sihirli sayı
        yerine gerçek değişmezi çiviliyor: yayımlanan son çap, kapalı
        çözümle 1e-9 bağıl mertebede ÖRTÜŞMELİ. r_dot[0] başlangıç
        yarıçapında değerlendirildiği için şemadan bağımsızdır ve
        DEĞİŞMEMİŞTİR (regresyon koruması olarak aynen bırakıldı).
        """
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(REG_TABAN))
        assert d['port_diameter'][-1] == 57.19246801281036
        assert d['regression_rate'][0] == 2.062853288584799
        assert d['time'][-1] == 10.0
        assert d['integration_scheme'] == 'runge_kutta_4'
        # Kapalı çözüm — sayı burada YENİDEN TANIMLANMAZ, katsayılar
        # merkezi tablodan okunur.
        from hrma.data.propellant_database import (
            HYBRID_REGRESSION_COEFFICIENTS as _C)
        _a = _C['htpb']['a']
        _n = _C['htpb']['n']
        _k = 2.0 * _n + 1.0
        _r0 = REG_TABAN['port_diameter_initial'] / 2.0
        _tam = 2000.0 * ((_r0 ** _k
                          + _k * _a * (REG_TABAN['mdot_ox'] / math.pi) ** _n
                          * REG_TABAN['burn_time']) ** (1.0 / _k))
        assert abs(d['port_diameter'][-1] - _tam) / _tam < 1e-9, (
            'RK4 şeması kapalı çözümden ayrıştı: '
            f"{d['port_diameter'][-1]} != {_tam}")


# ===========================================================================
# P5B4-05 — fit katsayıları ve geometri kapısı
# ===========================================================================
class TestP5B405KatsayiVeGeometriKapisi:
    """ÖLÇÜLDÜ (``once.json`` P5B4-05):

    ============================  =====================================
    girdi                          yayımlanan (uyarı sayısı 0)
    ============================  =====================================
    ``regression_a = -3,68e-5``    r[0] = **-2,062853288585 mm/s**,
                                   D_son = **-40,876497473031 mm**
    ``regression_a = 0``           r ≡ 0, port hiç büyümüyor
    ``regression_n = -0,555``      r[0] = 0,000656488761 mm/s
    ``regression_n = 12``          D_son = **4,778085645664e+35 mm**
    ``port_diameter_initial<0``    D[0] = **-30 mm** -> +40,876497 mm
    ``port_diameter_initial=0``    ham ``ZeroDivisionError``
    ``fuel_density = -920``        'total' kipinde G_fuel = -27,829291,
                                   mdot_f = **-0,039343 kg/s**
    ``grain_length = -0,5``        SESSİZCE kamara boyu yaklaşımına
                                   düşülüyor (eğri sağlıklıyla bit-aynı)
    ============================  =====================================
    """

    @pytest.mark.parametrize('alan,deger', [
        ('regression_a', -3.68e-5),
        ('regression_a', 0.0),
        ('regression_a', float('inf')),
        ('port_diameter_initial', -0.03),
        ('port_diameter_initial', 0.0),
        ('fuel_density', -920.0),
        ('fuel_density', 0.0),
        ('grain_length', -0.5),
    ])
    def test_tanim_geregi_pozitif_alanlar_adiyla_reddedilir(self, alan,
                                                            deger):
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer().analyze_regression_vs_time(
                dict(REG_TABAN, **{alan: deger}))
        assert ex.value.field == alan

    # ÖH D26 / OH-D25-15 — BEKÇİ ÇEVRİLDİ (n = 1,0 dışarıdan İÇERİ alındı).
    # Eski liste ``1.0``ı RET tarafında sayıyordu. Ölçüm (once.json/
    # OH-D25-15; a = 3,68e-5, G = 350 kg/m²s): n = 0,999999 KABUL,
    # r_dot = 0,012879924550041959 m/s;  n = 1,000000 -> 422. Girdideki 1e-6
    # bağıl adım, sayısal olarak ayırt edilemeyen iki cevaptan birini
    # yayımlayıp diğerini reddediyordu. Bandın kendi gerekçesi "regresyonun
    # akıdan HIZLI büyümesi"ni reddeder; türetimle o koşul n > 1'dir
    # (d(r/G)/dG = a(n-1)G^(n-2), n = 1'de TAM SIFIR). Sıkılaşma DEĞİL,
    # sınırın doğru yere konması: n = 1'in hemen üstü (1,0000001) hâlâ
    # reddedilir ve aşağıdaki liste bunu ADIYLA sayar.
    @pytest.mark.parametrize('n', [-0.555, 0.0, 1.0000001, 1.05, 12.0,
                                   float('nan'), float('inf')])
    def test_us_bandi_disi_adiyla_reddedilir(self, n):
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer().analyze_regression_vs_time(
                dict(REG_TABAN, regression_n=n))
        assert ex.value.field == 'regression_n'

    @pytest.mark.parametrize('n', [0.498, 0.555, 0.62, 0.8, 0.999, 1.0, 1e-6])
    def test_us_bandinin_ICI_gecmeye_devam_eder(self, n):
        """Bant bir UYGULAMA eşiği değildir: modülün kendi tablosu
        (0,498-0,620), ötesi ve ÜST UÇ (n = 1,0 kapsayıcı) geçer."""
        d = RegressionAnalyzer().analyze_regression_vs_time(
            dict(REG_TABAN, regression_n=n))
        assert d['port_diameter'][-1] > 0.0

    def test_band_modulun_kendi_tablosunu_KAPSAR(self):
        """TEK KAYNAK mandalı: bant, ürünün kullandığı her (a, n)
        çiftini içermek ZORUNDA — yoksa sağlıklı yakıt reddedilirdi."""
        lo, hi = REGRESSION_EXPONENT_VALID
        # ÖH D26 / OH-D25-15: uç kapsayıcılığı da ÜRÜNDEN okunur; bekçi
        # kendi kopyasını tutmaz (bant asimetriktir: alt dışlayıcı, üst
        # kapsayıcı).
        alt_kaps, ust_kaps = REGRESSION_EXPONENT_BAND_INCLUSIVE
        for ad, ozel in RegressionAnalyzer().fuel_properties.items():
            n = ozel['n']
            assert (n >= lo) if alt_kaps else (n > lo), ad
            assert (n <= hi) if ust_kaps else (n < hi), ad
            assert ozel['a'] > 0.0 and math.isfinite(ozel['a']), ad

    def test_total_kipinde_negatif_yakit_debisi_uretilemez(self):
        """Taban ``rho_f = -920`` ile ``mdot_f = -0,039343 kg/s`` ve
        ``G_total`` (322,171) < ``G_ox`` (350,0) yayımlıyordu."""
        with pytest.raises(NonPhysicalRegressionInput) as ex:
            RegressionAnalyzer.regression_rate(
                3.68e-5, 0.555, 350.0, rho_f=-920.0, port_diameter=0.03,
                grain_length=0.5, flux_mode='total')
        assert ex.value.field == 'fuel_density'

    def test_mdot_ox_SOZLESMESI_D15_te_KALIR(self):
        """Aynı alan için iki ret sınıfı doğmaz: ``mdot_ox``un sahibi
        D15 / P5B4-03'tür."""
        with pytest.raises(NonPhysicalOxidizerFlux):
            RegressionAnalyzer().analyze_regression_vs_time(
                dict(REG_TABAN, mdot_ox=-1.0))

    def test_uc_negatif_usu_artik_adiyla_reddediyor(self, istemci):
        """ÖLÇÜLDÜ (``once.json`` UC_regression): bu yol tabanda HTTP
        **200** veriyordu, ``regression_rate[0] = 0,000656488761 mm/s``."""
        kod, j = _reg_uc(istemci, regression_n=-0.555)
        assert kod == 422, j
        assert j['error'] == 'non_physical_regression_input'
        kayit = j['invalid_fields'][0]
        assert kayit['field'] == 'regression_n'
        assert kayit['reason'] == 'not_physical'

    def test_uc_saglikli_kolu_BIT_AYNI(self, istemci):
        # ÖH D23 / P5B4-12 ile ÇEVRİLDİ: kardeş bekçinin
        # (``test_saglikli_egri_BIT_AYNI``) gerekçesi aynen geçerli —
        # çivilenmiş 57,265776718965974 mm açık Euler kesme hatasıydı
        # (+%0,128), şema RK4 olduğu için kapalı çözüme oturdu.
        kod, j = _reg_uc(istemci)
        assert kod == 200
        rd = j['regression_data']
        assert rd['port_diameter'][-1] == 57.19246801281036
        assert rd['regression_rate'][0] == 2.062853288584799


# ===========================================================================
# P5B3-13 — su koçu bağlaması VANANIN basıncını alır
# ===========================================================================
class TestP5B313SuKocuVananinBasincini:
    """ÖLÇÜLDÜ (``once.json`` P5B3-13; su, D 20 mm, mdot 2 kg/s, giriş
    30 bar, 6 dirsek + 1 küresel vana):

    ==========  ===============  =================================
    hat boyu    hat çıkışı [bar]  bağlamaya giden ``working`` [bar]
    ==========  ===============  =================================
    1 m          29,217050985     **30,0**  (+%2,679)
    25 m         25,000994732     **30,0**  (+%19,996)
    200 m        **-5,741082113**  **30,0** (bağlama yine ÜRETİLDİ)
    ==========  ===============  =================================

    Oysa fonksiyonun kendi docstring'i "Vana, hattın SONUNDA kabul
    edilir" der ve ``size_valve`` gerçekten hat çıkışını kullanır.
    """

    def test_calisma_basinci_hat_cikisidir(self):
        r = analyze_valve_feedline(**TAM_TABAN)
        cikis = r['line']['total']['outlet_pressure_Pa']
        assert cikis == pytest.approx(2500099.4732176596, rel=1e-12)
        assert r['water_hammer']['analyzer_kwargs'][
            'working_pressure_bar'] == pytest.approx(cikis / 1e5, rel=1e-12)

    def test_kisa_hatta_da_giris_degil_cikis(self):
        r = analyze_valve_feedline(**dict(TAM_TABAN, line_length_m=1.0))
        assert r['water_hammer']['analyzer_kwargs'][
            'working_pressure_bar'] == pytest.approx(29.217050985266784,
                                                     rel=1e-12)

    def test_cikis_kazanilmamissa_baglama_URETILMEZ(self):
        """Vana ayağı zaten boyutlandırma yapmıyordu; su koçu bağlaması
        ise üretiliyordu (``hammer_var = True``, 30,0 bar)."""
        r = analyze_valve_feedline(**dict(TAM_TABAN, line_length_m=200.0))
        assert r['valve'] is None
        assert r['water_hammer'] is None
        alanlar = {v['field'] for v in r['validity']}
        assert 'water_hammer_inputs' in alanlar
        assert 'valve' in alanlar


# ===========================================================================
# P5B3-14 — Crane (L/D)_eş yöntemi tam türbülans ister
# ===========================================================================
class TestP5B314CraneLaminerBeyani:
    """ÖLÇÜLDÜ (``once.json`` P5B3-14; aynı hat, viskozite süpürmesi):
    Re = 12,73 / 127,32 / 1273,24 / 6366,20 / 127 323,95'in HEPSİNDE
    ``crane_ft = 0,024364282122``, ``k_total = 2,923713854647`` ve
    ``dp_minor = 59 246,829676857 Pa`` — BİT-AYNI. Laminer kayıtlarda
    ``validity`` BOŞ, ``warnings`` sayısı 0 idi; oysa aynı modül geçiş
    bandında SÜRTÜNME faktörü için ``out_of_validity`` yazıyor.
    """

    @pytest.mark.parametrize('mu,beklenen_rejim', [
        (1.0e-1, 'laminar'), (1.0, 'laminar'), (10.0, 'laminar'),
        (4.0e-2, 'transitional')])
    def test_tam_turbulans_altinda_gecerlilik_beyani_var(self, mu,
                                                         beklenen_rejim):
        r = line_pressure_drop(**dict(HAT_TABAN, viscosity_Pa_s=mu))
        assert r['flow']['regime'] == beklenen_rejim
        kayit = [v for v in r['validity'] if v['field'] == 'minor_losses']
        assert len(kayit) == 1, r['validity']
        assert kayit[0]['status'] == 'out_of_validity'
        assert 'LOWER BOUND' in kayit[0]['message']
        assert any('lower bound' in w for w in r['warnings'])

    def test_tam_turbulansta_beyan_YOK(self):
        """Yanlış pozitif olmaz: sağlıklı türbülanslı hatta ek kayıt
        çıkmaz, gövde bit-aynı kalır."""
        r = line_pressure_drop(**HAT_TABAN)
        assert r['flow']['reynolds'] == pytest.approx(127323.95447351623,
                                                      rel=1e-12)
        assert [v for v in r['validity'] if v['field'] == 'minor_losses'] == []
        assert r['minor_losses']['dp_Pa'] == pytest.approx(
            59246.82967685738, rel=1e-12)

    def test_sabit_K_kalemleri_crane_beyanini_TETIKLEMEZ(self):
        """Beyan yalnız (L/D)_eş yöntemiyle çözülen kalemler için doğar;
        sabit-K girişleri Crane f_T'ye bağlı değildir."""
        r = line_pressure_drop(**dict(HAT_TABAN, viscosity_Pa_s=1.0,
                                      fittings={'entrance_sharp': 1}))
        assert r['flow']['regime'] == 'laminar'
        assert [v for v in r['validity'] if v['field'] == 'minor_losses'] == []


# ===========================================================================
# P5B3-15 — hat girdi kapısı
# ===========================================================================
class TestP5B315HatGirdiKapisi:
    """ÖLÇÜLDÜ (``once.json`` P5B3-15; 25 m hat, giriş 30 bar):

    ==============================  ==================================
    girdi                            yayımlanan (uyarı sayısı 0 ya da 1)
    ==============================  ==================================
    ``elevation_gain_m = -1e9``      dp_static **-9,80665e+12 Pa**,
                                     çıkış **+9,806653e+12 Pa**, uyarı 0
    ``elevation_gain_m = +1e9``      dp_total **+9,80665e+12 Pa**
    ``extra_loss_coefficient=1e9``   çıkış **-2,0264234e+13 Pa**
    ``elbow_90_long_radius: 1e6``    çıkış **-9,8719108e+09 Pa**
    ``vapor_pressure_Pa = 100 bar``  sağlıklı çağrıyla BİT-AYNI kabul
    ``vapor_pressure_Pa = 1e12``     sağlıklı çağrıyla BİT-AYNI kabul
    ==============================  ==================================
    """

    @pytest.mark.parametrize('dz', [-1.0e9, 1.0e9, 1000.0, -25.000001,
                                    25.000001])
    def test_kot_farki_hat_boyunu_asamaz(self, dz):
        with pytest.raises(ValueError, match='exceeds the line length'):
            line_pressure_drop(**dict(HAT_TABAN, elevation_gain_m=dz))

    @pytest.mark.parametrize('dz', [0.0, 25.0, -25.0, 12.5, -3.0])
    def test_geometrik_olarak_MUMKUN_kot_farki_gecer(self, dz):
        r = line_pressure_drop(**dict(HAT_TABAN, elevation_gain_m=dz))
        assert r['static_head']['dp_Pa'] == pytest.approx(
            1000.0 * 9.80665 * dz, abs=1e-6)

    @pytest.mark.parametrize('pv', [30.0e5, 100.0e5, 1.0e12])
    def test_buhar_basinci_girisi_asamaz(self, pv):
        with pytest.raises(ValueError, match='already boiling'):
            line_pressure_drop(**dict(HAT_TABAN, vapor_pressure_Pa=pv))

    def test_girisin_ALTINDAKI_buhar_basinci_gecer(self):
        r = line_pressure_drop(**dict(HAT_TABAN, vapor_pressure_Pa=2339.0))
        assert r['line_cavitation']['status'] == 'subcooled'

    @pytest.mark.parametrize('degis', [
        {'extra_loss_coefficient': 1.0e9},
        {'fittings': {'elbow_90_long_radius': 1.0e6}},
        {'viscosity_Pa_s': 10.0},
    ])
    def test_negatif_mutlak_basinc_YAYIMLANMAZ(self, degis):
        r = line_pressure_drop(**dict(HAT_TABAN, **degis))
        assert r['total']['outlet_pressure_Pa'] is None
        kayit = [v for v in r['validity']
                 if v['field'] == 'outlet_pressure_Pa']
        assert len(kayit) == 1 and kayit[0]['status'] == 'not_evaluated'

    def test_negatif_mutlak_basincta_kavitasyon_HUKMU_de_geri_cekilir(self):
        """Taban, negatif mutlak basınçtan ``status: 'cavitating'`` ve
        negatif ``margin_Pa`` üretiyordu."""
        r = line_pressure_drop(**dict(HAT_TABAN,
                                      extra_loss_coefficient=1.0e9,
                                      vapor_pressure_Pa=2339.0))
        assert r['line_cavitation'] is None

    def test_saglikli_hat_BIT_AYNI(self):
        r = line_pressure_drop(**HAT_TABAN)
        assert r['total']['dp_Pa'] == pytest.approx(498419.35604041885,
                                                    rel=1e-12)
        assert r['total']['outlet_pressure_Pa'] == pytest.approx(
            2501580.643959581, rel=1e-12)


# ===========================================================================
# P5B3-16 — autogenous boşaltma verimi bandı
# ===========================================================================
class TestP5B316BosaltmaVerimiBandi:
    """ÖLÇÜLDÜ (``once.json`` P5B3-16; LOX, V_p 0,5 m3, tank 30 bar):

    ==========  ====================  ==============================
    η           ``gas_mass_kg``       not
    ==========  ====================  ==============================
    0,95        24,310198128115       modül varsayılanı
    1,00        23,094688221709       üst fiziksel sınır
    **1,50**    **15,396458814473**   KABUL — gaz kütlesi **-%33,3**
    **10,0**     **2,309468822171**   KABUL — 10 kat azaltma
    **0,01**  **2309,468822170901**   KABUL — **100 kat** büyütme
    **inf**        **0,0**            KABUL — "gaz gerekmiyor"
    **nan**        **nan**            KABUL — yanıtta ham NaN
    ==========  ====================  ==============================
    """

    _TABAN = dict(propellant_volume=0.5, tank_pressure=30.0e5,
                  propellant='lox')

    @pytest.mark.parametrize('eta', [1.5, 10.0, 0.01, 0.4999,
                                     float('inf'), float('nan')])
    def test_band_disi_adiyla_reddedilir(self, eta):
        r = autogenous_pressurant(**dict(self._TABAN,
                                         expulsion_efficiency=eta))
        assert r['status'] == 'error'
        assert 'expulsion_efficiency' in r['reason']
        assert 'gas_mass_kg' not in r

    @pytest.mark.parametrize('eta', [0.50, 0.90, 0.95, 0.99, 1.00])
    def test_bandin_ICI_gecer(self, eta):
        r = autogenous_pressurant(**dict(self._TABAN,
                                         expulsion_efficiency=eta))
        assert r['status'] == 'ok'
        assert r['gas_mass_kg'] > 0.0

    def test_ust_uc_KESRIN_TANIMINDAN_gelir(self):
        assert EXPULSION_EFFICIENCY_VALID[1] == 1.00

    def test_modul_varsayilani_bandin_ICINDE(self):
        """TEK KAYNAK mandalı: imzadaki varsayılan bandın dışına
        kayarsa sağlıklı çağrı reddedilirdi."""
        import inspect
        varsayilan = inspect.signature(
            autogenous_pressurant).parameters[
                'expulsion_efficiency'].default
        lo, hi = EXPULSION_EFFICIENCY_VALID
        assert lo <= varsayilan <= hi

    def test_varsayilan_govde_BIT_AYNI(self):
        r = autogenous_pressurant(**self._TABAN)
        assert r['gas_mass_kg'] == pytest.approx(24.310198128114745,
                                                 rel=1e-12)

    # --- ÖH D26 / P5B3-16 REGÜLE AYAĞI (Fable-D20 ŞART, (a) şıkkı) -----
    # ÖLÇÜLDÜ (D26 tabanı 7751531, ``once.json`` P5B3-16; helyum,
    # V_p = 0,5 m3, tank 30 bar, depo varsayılan):
    #     regulated_pressurant(..., expulsion_efficiency=<herhangi>)
    #         -> TypeError: unexpected keyword argument
    #     varsayılan gövde: iso 2,4632561940010134 kg /
    #         adia 5,261057881774493 kg /
    #         teslim 3,149732040049564 kg /
    #         şişe 0,16394736645480523 m3 / 4 şişe
    # Yani aynı fiziksel büyüklük bir dalda bantlıydı, öbür dalda hiç ifade
    # edilemiyordu.
    #
    # DÜZELTME — ÖH D27 / P5B3-16 (hüküm-15): D26'da varsayılan 1,0
    # bırakılmış, gerekçe "varsayılan gövde bit-aynı kalsın" idi. Hüküm-15
    # bunu REDDETTİ: bit-aynılık ürün gereği değil onarımın rahatlığıydı;
    # 1,0 kesrin fiziksel TAVANIDIR ve onu varsayılan yapmak ölçülen
    # %5,263'lük EKSİK gaz envanterini korumaktı. Varsayılan artık iki
    # dalın ORTAK sabiti ``EXPULSION_EFFICIENCY_DEFAULT`` = 0,95'tir
    # (literatür künyesi: Huzel & Huang Böl. 5, uygulama bandı 0,90-0,99).
    # Yukarıdaki dört sayı TARİHİ ÇIPADIR (eta = 1,0 gövdesi); aşağıdaki
    # bekçi onları sabite BÖLEREK saklar, yani sapmanın TAM OLARAK 1/eta
    # olduğunu ve başka hiçbir şeyin oynamadığını mandallar.
    _REG_TABAN = dict(propellant_volume=0.5, tank_pressure=30.0e5,
                      gas='helium')

    def test_regule_dalinda_da_eta_var(self):
        import inspect
        par = inspect.signature(regulated_pressurant).parameters
        assert 'expulsion_efficiency' in par, (
            'regüle dalı boşaltma verimini hâlâ ifade edemiyor')
        assert (par['expulsion_efficiency'].default
                is EXPULSION_EFFICIENCY_DEFAULT), (
            'regüle dalı ortak varsayılanı okumuyor (Doktrin 4)')

    @pytest.mark.parametrize('deger', [1.5, 1.0000001, 0.01, 0.4999,
                                       float('nan'), float('inf'), 0.0,
                                       -0.5])
    def test_regule_dalinda_band_disi_REDDEDILIR(self, deger):
        """Kardeş dalla AYNI band, AYNI tek kaynak."""
        with pytest.raises(ValueError) as ex:
            regulated_pressurant(expulsion_efficiency=deger,
                                 **self._REG_TABAN)
        assert 'expulsion_efficiency' in str(ex.value)
        lo, hi = EXPULSION_EFFICIENCY_VALID
        assert f'[{lo}, {hi}]' in str(ex.value)

    def test_regule_bandin_ucu_KABUL(self):
        for deger in EXPULSION_EFFICIENCY_VALID:
            r = regulated_pressurant(expulsion_efficiency=deger,
                                     **self._REG_TABAN)
            assert r['expulsion_efficiency'] == pytest.approx(deger)

    #: D26 çıpası: eta = 1,0 ile ölçülmüş varsayılan gövde (taban 7751531).
    #: ÖH D27'den beri varsayılan eta = EXPULSION_EFFICIENCY_DEFAULT
    #: olduğu için gövde bu çıpanın TAM OLARAK 1/eta katıdır.
    _D26_CIPASI = {
        'isothermal': 2.4632561940010134,
        'adiabatic': 5.261057881774493,
        'delivered': 3.149732040049564,
        'bottle_m3': 0.16394736645480523,
    }

    def test_regule_VARSAYILAN_GOVDE_BIT_AYNI(self):
        """Varsayılan gövde D26 çıpasından SADECE 1/eta kadar sapar.

        ÖH D27 / P5B3-16 (hüküm-15): dört sayı SİLİNMEDİ, ortak sabite
        BÖLÜNEREK türetildi. Bekçinin işi değişmedi — hâlâ "onarım
        gövdeyi kıl payı oynatmaz" diyor, yalnız çıpa artık
        ``D26 gövdesi / EXPULSION_EFFICIENCY_DEFAULT``. Sabit elle
        oynatılırsa (ya da bir dal sabitten kopartılırsa) bu düğüm
        kırmızı olur.
        """
        r = regulated_pressurant(**self._REG_TABAN)
        assert r['expulsion_efficiency'] == EXPULSION_EFFICIENCY_DEFAULT
        eta = EXPULSION_EFFICIENCY_DEFAULT
        assert r['swept_volume_m3'] == pytest.approx(
            self._REG_TABAN['propellant_volume'] / eta, rel=1e-12)
        assert r['isothermal']['gas_mass_kg'] == pytest.approx(
            self._D26_CIPASI['isothermal'] / eta, rel=1e-12)
        assert r['adiabatic']['gas_mass_kg'] == pytest.approx(
            self._D26_CIPASI['adiabatic'] / eta, rel=1e-12)
        assert r['recommended_delivered_mass_kg'] == pytest.approx(
            self._D26_CIPASI['delivered'] / eta, rel=1e-12)
        assert r['storage']['bottle_water_volume_m3'] == pytest.approx(
            self._D26_CIPASI['bottle_m3'] / eta, rel=1e-12)

    def test_regule_TURETIM_ILISKISI_eta1_govdesinden(self):
        """Türetim SAYIYA değil İLİŞKİYE bağlıdır (D26 dersi 8).

        eta = 1,0 AÇIKÇA verildiğinde çıkan gövde D26 çıpasının ta
        kendisidir; varsayılan gövde ise onun 1/eta katıdır. Bu düğüm
        çıpa sayıları bir gün yeniden ölçülse bile ayakta kalır.
        """
        eta1 = regulated_pressurant(expulsion_efficiency=1.0,
                                    **self._REG_TABAN)
        vars_ = regulated_pressurant(**self._REG_TABAN)
        assert eta1['isothermal']['gas_mass_kg'] == pytest.approx(
            self._D26_CIPASI['isothermal'], rel=1e-12)
        oran = 1.0 / EXPULSION_EFFICIENCY_DEFAULT
        for yol in (('isothermal', 'gas_mass_kg'),
                    ('adiabatic', 'gas_mass_kg'),
                    ('storage', 'bottle_water_volume_m3')):
            t = eta1[yol[0]][yol[1]]
            v = vars_[yol[0]][yol[1]]
            assert v == pytest.approx(oran * t, rel=1e-12), (yol, t, v)
        assert vars_['recommended_delivered_mass_kg'] == pytest.approx(
            oran * eta1['recommended_delivered_mass_kg'], rel=1e-12)

    def test_regule_eta_envanteri_GERCEKTEN_oynatiyor(self):
        """Parametre süs DEĞİL: eta gaz envanterini 1/eta katına çıkarır.

        Kardeş dalın (``autogenous_pressurant``) biçimiyle birebir aynı:
        süpürülen hacim V_p/eta'dır. Bu düğüm olmasaydı eta imzaya
        eklenip hiçbir şeye bağlanmadan durabilirdi.
        """
        taban = regulated_pressurant(**self._REG_TABAN)
        dusuk = regulated_pressurant(expulsion_efficiency=0.5,
                                     **self._REG_TABAN)
        assert dusuk['swept_volume_m3'] == pytest.approx(
            self._REG_TABAN['propellant_volume'] / 0.5, rel=1e-12)
        # ÖH D27: taban artık eta = EXPULSION_EFFICIENCY_DEFAULT, o yüzden
        # oran 2,0 değil eta_varsayılan/0,5 (= 1,9). Sayı YAZILMAZ, türetilir.
        oran = EXPULSION_EFFICIENCY_DEFAULT / 0.5
        for yol in (('isothermal', 'gas_mass_kg'),
                    ('adiabatic', 'gas_mass_kg')):
            t = taban[yol[0]][yol[1]]
            d = dusuk[yol[0]][yol[1]]
            assert d == pytest.approx(oran * t, rel=1e-12), (yol, t, d)
        assert dusuk['storage']['bottle_water_volume_m3'] == pytest.approx(
            oran * taban['storage']['bottle_water_volume_m3'], rel=1e-12)
        assert 'eta_ex' in dusuk['model_note']

    def test_band_sabiti_KOPYALANMADI(self):
        """İki dal AYNI sabiti okur — sayı ikinci kez yazılmaz (Doktrin 4)."""
        kaynak = (pathlib.Path(__file__).resolve().parents[1] / 'hrma'
                  / 'analysis' / 'pressurant_sizing.py').read_text(
                      encoding='utf-8')
        assert kaynak.count('EXPULSION_EFFICIENCY_VALID = ') == 1
        assert kaynak.count('EXPULSION_EFFICIENCY_VALID') >= 3


# ===========================================================================
# P5B2-18 — künye ölçümle SENKRON kalır (D18 onarımının devri)
# ===========================================================================
def _safety_blok_disi_sayim():
    """SAFETY_MODEL bloğu DIŞINDAKİ sayısal değişmezler (AST)."""
    import hrma.analysis.safety_analysis as _sa
    kaynak = open(_sa.__file__, encoding='utf-8').read()
    agac = ast.parse(kaynak)
    aralik = None
    for d in agac.body:
        if (isinstance(d, ast.Assign) and d.targets
                and isinstance(d.targets[0], ast.Name)
                and d.targets[0].id == 'SAFETY_MODEL'):
            aralik = (d.lineno, d.end_lineno)
    assert aralik is not None
    sayilar = [float(n.value) for n in ast.walk(agac)
               if isinstance(n, ast.Constant)
               and isinstance(n.value, (int, float))
               and not isinstance(n.value, bool)
               and not (aralik[0] <= n.lineno <= aralik[1])]
    return kaynak, len(sayilar), len(set(sayilar))


class TestP5B218KunyeOlcumleSenkron:
    """D18 (00e142f) yanlış mutlak iddiayı kaldırıp ÖLÇÜLEN sayıları
    (252 değişmez / 58 farklı değer) künyeye yazdı ve bir TAVAN mandalı
    kurdu. Tavan yalnız YUKARI yönü kapatır: sayım düşerse künye sessizce
    BAYATLAR. Bu bekçi künyenin metnini ölçümle karşılaştırır.

    ÖLÇÜLDÜ (taban 14acd1d, ``once.json`` P5B2-18): 252 / 58 — künyedeki
    sayılarla birebir. Kalem başlığındaki "135 değişmez, 48 farklı değer"
    bu ağaçta ÜRETİLEMEZ (başlık P05 partisi dönemindendir).
    """

    def test_kunyedeki_sayilar_OLCUMLE_ayni(self):
        kaynak, degismez, farkli = _safety_blok_disi_sayim()
        onsoz = kaynak.split('SAFETY_MODEL = {')[0]
        assert f'{degismez} sayısal değişmez' in onsoz, (
            f'künye bayatladı: ölçüm {degismez} diyor')
        assert f'{farkli} farklı' in onsoz, (
            f'künye bayatladı: ölçüm {farkli} farklı değer diyor')

    def test_D18_onarimi_hala_duruyor(self):
        kaynak, _, _ = _safety_blok_disi_sayim()
        assert '# Bu blok dışında sayısal sabit yazılmaz' not in kaynak
        assert 'KALİBRASYON sabitlerinin' in kaynak


# ===========================================================================
# P5B3-10 — D18 pürüzlülük-köken onarımı bu tabanda duruyor
# ===========================================================================
class TestP5B310KokenOnarimiDuruyor:
    """D18 (00e142f) modül ayağını onardı: köken beyan edilmediğinde
    künye "ölçüldü" DEMEZ. Çağrı ayağı (``liquid_rocket_engine``in el
    kitabı sabitini beyansız geçirmesi) kardeş dalın (sivi) aktif
    sahasındadır ve D20'de de açılamaz.
    """

    def test_beyansiz_koken_olculdu_DEMEZ(self):
        r = line_pressure_drop(**dict(HAT_TABAN, roughness_m=4.5e-5))
        assert r['inputs']['roughness_provenance'] is None
        assert 'UNDECLARED provenance' in r['inputs']['roughness_source']
        assert 'MEASURED' not in r['inputs']['roughness_source']

    def test_el_kitabi_beyani_kunyeye_gecer(self):
        r = line_pressure_drop(**dict(HAT_TABAN, roughness_m=4.5e-5,
                                      roughness_provenance='handbook_table'))
        assert r['inputs']['roughness_provenance'] == 'handbook_table'
        assert 'HANDBOOK' in r['inputs']['roughness_source']

    def test_taninmayan_koken_adiyla_reddedilir(self):
        with pytest.raises(ValueError, match='unknown roughness_provenance'):
            line_pressure_drop(**dict(HAT_TABAN, roughness_m=4.5e-5,
                                      roughness_provenance='bogus'))


# ===========================================================================
# OH-D20-09 — NPSH çift marjı ÖLÇÜLDÜ (onarım kardeş dalda: ENGEL bekçisi)
# ===========================================================================
class TestOHD2009NpshCiftMarjiOlculdu:
    """ÖH D21 NOTU: kusur D21'de ONARILDI (sıvı kulvarı a1); aşağıdaki
    ikinci düğüm çevrildi ve kapanış bekçisi oldu. Bu docstring'in kalanı
    D20'nin ölçüm kaydıdır ve tarihsel olarak korunur.

    Kusur bu dalgada ONARILAMADI: tek-marj sözleşmesinin uygulanacağı
    yer ``hrma/engines/liquid_rocket_engine.py`` (satır 7350-7381 ve
    9422-9724) ve o dosya D20'de ``dalga20/sivi``nın aktif sahasındadır.

    Bu sınıf kusurun BÜYÜKLÜĞÜNÜ mandallar: onarım geldiğinde bu düğüm
    kırmızıya döner ve kalem yeniden okunur.

    ÖLÇÜLDÜ (``once.json`` OH-D20-09; LOX, c_m = 12 m/s, k_v = 2,3,
    rho 1141 kg/m3, p_v 1 bar):
      SP-8109 §3.2.1.2 kural tabanı  = 16,886500486914 m
      ürünün "gerekli NPSH" diye
      yayımladığı                    = 21,108125608643 m  (= 1,25 x)
      p_tank (k = 1,25)              = 3,361870 bar
      p_tank (k = 1,0)               = 2,889496 bar
    """

    def test_kural_tabani_zaten_marjlidir_ve_ustune_oran_biniyor(self):
        from hrma.analysis import turbopump_sizing as tp
        k_v = tp.NPSH_VELOCITY_HEAD_FACTORS['cryogenic_ox']
        kural = tp.npsh_required_velocity_head_m(12.0, k_v)
        assert kural == pytest.approx(16.886500486914493, rel=1e-12)
        p_marjli = tp.tank_pressure_from_npsh_Pa(1.0e5, 1141.0, kural)
        p_marjsiz = tp.tank_pressure_from_npsh_Pa(1.0e5, 1141.0, kural,
                                                  0.0, 0.0, 1.0)
        oran = (p_marjli - 1.0e5) / (p_marjsiz - 1.0e5)
        assert oran == pytest.approx(tp.NPSH_MARGIN_FACTOR_DEFAULT,
                                     rel=1e-12)

    def test_motor_ayagi_ARTIK_carpmiyor_KAPANIS_KAYDI(self):
        """ÇEVRİLDİ — ÖH D21 · OH-D20-09 onarımı geldi.

        D20'de bu düğüm bir ENGEL KAYDIydı: onarım yeri
        ``hrma/engines/liquid_rocket_engine.py`` kardeş dalın (``dalga20/
        sivi``) aktif sahasındaydı, bu yüzden yapısal-sistem kulvarı
        kusuru yalnız ölçüp mandallamış ve düğüme "onarım gelirse
        kırmızıya döner, kalem yeniden okunur" diye yazmıştı. D21'de kalem
        dosya sahibi olan sıvı kulvarına yeniden atandı ve onarıldı: tek
        marj sözleşmesi ``NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE = 1,0``
        (``hrma/analysis/turbopump_sizing.py``), motor ayağı artık SP-8107
        oranını SP-8109 kuralının üstüne koymuyor.

        Düğüm çevrildi ve KAPANIŞ BEKÇİSİ oldu: çarpım geri gelirse
        kırmızı olur. Onarımın kendi bekçisi
        tests/test_d21_sivi_a1.py ``TestOHD2009TekMarj``.
        """
        import hrma.engines.liquid_rocket_engine as lre
        from hrma.analysis import turbopump_sizing as tps
        kaynak = open(lre.__file__, encoding='utf-8').read()
        assert 'NPSH_MARGIN_FACTOR_DEFAULT) * npsh_req_vh' not in kaynak
        assert 'NPSH_MARGIN_FACTOR_DEFAULT' not in kaynak, (
            'motor ayağı SP-8107 oranını artık hiç okumamalı; hız-yükü '
            'kuralı zaten marjlı bir tabandır')
        assert 'NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE' in kaynak
        assert tps.NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE == 1.0


# ===========================================================================
# Ölçüm dosyaları gerçekten üretildi mi (kanıt hijyeni)
# ===========================================================================
def test_olcum_kanitlari_diskte():
    import os
    d = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))),
        'docs/scofield/raw/OH/D20/yapisal-sistem/a1')
    for ad in ('once.json', 'sonra.json', 'mutasyon.json'):
        yol = os.path.join(d, ad)
        assert os.path.exists(kanit_gerekli(yol)), yol
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            assert json.load(f)
