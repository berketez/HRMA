"""v2.6.27 B1 — hibrit motorda yanma süresi dürüstlüğü ve C_F sınırlılığı.

Kilitlenen dört kusur (hepsi bu depoda ÖLÇÜLDÜ, tahmin değil):

KALEM 1A — aşırı belirlenmiş girdi. ``{thrust: 500, burn_time: 20,
    total_impulse: 7500}`` gönderildiğinde motor süreyi 15 s'e çözüyor ve
    kullanıcının 20 s'i SESSİZCE yok oluyordu: uyarı yok, ``defaults_used``
    boş, sonuçta hiçbir iz yok.
KALEM 1B — yakıt web'i erken tükendiğinde çözücü GERÇEK süreyi hesaplıyor
    ama manşete bağlamıyordu: aynı yanıtta ``burn_time = 20`` ve
    ``total_impulse = 100000 Ns`` yazarken ``of_shift.regulated
    .burn_time_effective_s = 14,3`` duruyordu.
KALEM 2 — HTPB katsayı sapması uyarısı ÜRÜNDE ölüydü: kapı ``a/n is None``
    istiyordu, oysa advanced.html bu alanları ön-dolduruyor ve her istekte
    gönderiyor. Flask istemcisiyle ölçüldü (2026-08-11): a/n gönderilmeden
    uyarı VAR, gönderilerek YOK.
KALEM 3 — ekli-akış C_F'i hiç sınırlanmıyordu. Pc = 20 bar deniz
    seviyesinde ε=35 -> Isp 7,6 s (HTTP 200), ε=36 -> 1,1 s, ε=40 -> C_F
    NEGATİF. Transient tarafında Pc düştükçe C_F −23'e kadar iniyordu.
KALEM 4 — itki serisi son adımın BAŞINDA bitiyordu: aynı koşunun itki
    eğrisi 19,9 s, port eğrisi 20,0 s diyordu.
"""

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import (
    HTPB_COEFF_DB_BIAS_PCT,
    HTPB_COEFF_DB_MEDAPE_PCT,
    HybridRocketEngine,
)
from hrma.analysis.transient_ballistics import TransientBallistics
from hrma.data.propellant_database import HYBRID_REGRESSION_COEFFICIENTS
from hrma.flow.separation import SUMMERFIELD_FACTOR_DEFAULT

G0 = 9.80665

TEMEL = dict(of_ratio=2.5, chamber_pressure=20, atmospheric_pressure=1.0,
             fuel_type='htpb', oxidizer_type='n2o')


def kos(**kw):
    ayar = dict(TEMEL)
    ayar.update(kw)
    motor = HybridRocketEngine(**ayar)
    return motor, motor.calculate()


def kodlar(sonuc):
    return [u['code'] for u in (sonuc.get('warnings') or [])
            if isinstance(u, dict)]


@pytest.fixture(scope='module')
def varsayilan():
    return kos(thrust=1000, burn_time=20)


@pytest.fixture(scope='module')
def kirpilan():
    """Web'i erken tükenen motor: istenen 30 s, grain bunu tutturamıyor."""
    motor, sonuc = kos(thrust=5000, burn_time=30, chamber_diameter_input=150)
    assert motor.t_burn_effective < 30.0, (
        'sınama kurgusu bozulmuş: bu tasarımda web erken tükenmiyor')
    return motor, sonuc


# ---------------------------------------------------------------------------
# KALEM 1A — itki / süre / toplam impuls önceliği YAZILI ve BEYANLI
# ---------------------------------------------------------------------------

class TestImpulsGirdiCozumu:

    def test_uc_girdi_birden_verilince_ezme_beyan_edilir(self):
        motor, sonuc = kos(thrust=500, burn_time=20, total_impulse=7500)
        # Sayı değişmiyor: 7500/500 = 15 s hâlâ doğru cevap.
        assert motor.t_b == pytest.approx(15.0)
        cozum = sonuc['impulse_input_resolution']
        assert set(cozum['supplied']) == {'thrust', 'burn_time',
                                          'total_impulse'}
        assert cozum['derived_quantity'] == 'burn_time'
        assert cozum['independent_inputs'] == ['total_impulse', 'thrust']
        ezilen = cozum['overridden']
        assert ezilen['field'] == 'burn_time'
        assert ezilen['submitted_s'] == pytest.approx(20.0)
        assert ezilen['used_s'] == pytest.approx(15.0)
        assert 'warn.hybrid.burn_time_overridden_by_impulse' in kodlar(sonuc)

    def test_cakismayan_uc_girdi_uyari_uretmez(self):
        """F·t_b = I tutuyorsa ezme YOKTUR; gürültü çıkarılmaz."""
        _, sonuc = kos(thrust=500, burn_time=15, total_impulse=7500)
        assert 'overridden' not in sonuc['impulse_input_resolution']
        assert ('warn.hybrid.burn_time_overridden_by_impulse'
                not in kodlar(sonuc))

    def test_toplam_impuls_yoksa_sure_kullanicinindir(self):
        motor, sonuc = kos(thrust=500, burn_time=20)
        assert motor.t_b == pytest.approx(20.0)
        cozum = sonuc['impulse_input_resolution']
        assert cozum['derived_quantity'] == 'total_impulse'
        assert 'overridden' not in cozum

    def test_itki_yoksa_sure_bagimsiz_kalir(self):
        motor, sonuc = kos(burn_time=20, total_impulse=10000)
        assert motor.t_b == pytest.approx(20.0)
        assert motor.F == pytest.approx(500.0)
        cozum = sonuc['impulse_input_resolution']
        assert cozum['derived_quantity'] == 'thrust'

    def test_oncelik_gerekcesi_yayimlanir(self, varsayilan):
        _, sonuc = varsayilan
        temel = sonuc['impulse_input_resolution']['priority_basis']
        assert 'one equation in three quantities' in temel


# ---------------------------------------------------------------------------
# KALEM 1B — gerçek süre ve teslim edilen impuls MANŞETE bağlı
# ---------------------------------------------------------------------------

class TestGercekSureMansete:

    def test_kirpilmayan_kosuda_hicbir_sayi_degismez(self, varsayilan):
        motor, sonuc = varsayilan
        assert sonuc['burn_time'] == pytest.approx(motor.t_b)
        assert sonuc['total_impulse'] == pytest.approx(motor.I_total)
        assert sonuc['burn_time_clipped'] is False
        assert sonuc['burn_time_effective_s'] == pytest.approx(motor.t_b)

    def test_kirpilan_kosuda_manset_teslim_edileni_gosterir(self, kirpilan):
        motor, sonuc = kirpilan
        t_etkin = float(motor.t_burn_effective)
        assert sonuc['burn_time_clipped'] is True
        assert sonuc['burn_time'] == pytest.approx(t_etkin)
        assert sonuc['burn_time'] < sonuc['burn_time_requested_s']
        # İstenen değer KAYBOLMAZ, yanında durur.
        assert sonuc['burn_time_requested_s'] == pytest.approx(motor.t_b)
        assert sonuc['burn_time_effective_s'] == pytest.approx(t_etkin)

    def test_kirpilan_kosuda_impuls_egrinin_kendi_impulsudur(self, kirpilan):
        _, sonuc = kirpilan
        egri = sonuc['thrust_curve']
        beklenen = float(np.trapz(egri['thrust'], egri['time']))
        assert sonuc['total_impulse'] == pytest.approx(beklenen, rel=1e-9)
        assert sonuc['total_impulse_delivered_Ns'] == pytest.approx(beklenen,
                                                                   rel=1e-9)
        assert sonuc['total_impulse'] < sonuc['total_impulse_requested_Ns']

    def test_manset_ile_of_shift_ayni_sureyi_soyler(self, kirpilan):
        """İki blok aynı koşuda İKİ FARKLI süre söyleyemez."""
        _, sonuc = kirpilan
        assert sonuc['burn_time_effective_s'] == pytest.approx(
            sonuc['of_shift']['regulated']['burn_time_effective_s'])

    def test_oksitleyici_butcesi_kapanir(self, kirpilan):
        motor, sonuc = kirpilan
        yuklenen = sonuc['oxidizer_mass']
        harcanan = sonuc['oxidizer_mass_consumed_kg']
        artik = sonuc['oxidizer_mass_residual_kg']
        assert yuklenen == pytest.approx(harcanan + artik, rel=1e-9)
        # Tank İSTENEN süreye göre yüklenir (donanım kararı), grain'e göre
        # değil: kırpılan yanmada artık oksitleyici KALIR ve bu görünür.
        assert harcanan == pytest.approx(
            motor.mdot_ox * motor.t_burn_effective, rel=1e-9)
        assert artik > 0.0
        assert 'LOADED mass' in sonuc['oxidizer_mass_basis']

    def test_kirpilma_uyariyla_beyan_edilir(self, kirpilan):
        _, sonuc = kirpilan
        assert 'warn.hybrid.web_exhausted_early' in kodlar(sonuc)


# ---------------------------------------------------------------------------
# KALEM 2 — HTPB katsayı sapması ÜRÜNÜN kendi akışında da duyulur
# ---------------------------------------------------------------------------

class TestRegresyonKatsayiGorunurlugu:

    def test_katsayi_verilmediginde_sapma_bildirilir(self):
        _, sonuc = kos(thrust=1000, burn_time=10)
        assert 'warn.hybrid.htpb_coeff_bias' in kodlar(sonuc)

    def test_katalog_degeri_geri_gonderilince_de_bildirilir(self):
        """ÜRÜNÜN GERÇEK AKIŞI: advanced.html alanları ön-doldurup gönderiyor.

        Kullanıcı hiçbir şey seçmemiş olmasına rağmen a/n dolu geliyordu ve
        kapı kapanıyordu. Katalog değerinin kendisi gönderildiğinde kullanıcı
        fiilen yerleşik katsayıyı kullanıyordur — sapma bildirilmelidir.
        """
        katalog = HYBRID_REGRESSION_COEFFICIENTS['htpb']
        _, sonuc = kos(thrust=1000, burn_time=10,
                       regression_a=katalog['a'], regression_n=katalog['n'])
        uyarilar = [u for u in sonuc['warnings']
                    if isinstance(u, dict)
                    and u['code'] == 'warn.hybrid.htpb_coeff_bias']
        assert uyarilar, 'katalog değeri gönderildiğinde uyarı susuyor'
        p = uyarilar[0]['params']
        assert p['bias_pct'] == HTPB_COEFF_DB_BIAS_PCT
        assert p['medape_pct'] == HTPB_COEFF_DB_MEDAPE_PCT

    def test_arayuzun_yuvarladigi_deger_de_katalog_sayilir(self):
        """advanced.html katsayıyı 3.680e-05 diye yuvarlayıp geri gönderiyor."""
        _, sonuc = kos(thrust=1000, burn_time=10,
                       regression_a=3.680e-05, regression_n=0.555)
        assert 'warn.hybrid.htpb_coeff_bias' in kodlar(sonuc)

    def test_gercek_ezmede_sapma_yuzdesi_bildirilir(self):
        katalog = HYBRID_REGRESSION_COEFFICIENTS['htpb']
        _, sonuc = kos(thrust=1000, burn_time=10,
                       regression_a=1.5e-4, regression_n=0.4)
        # Yerleşik katsayı ARTIK KULLANILMIYOR -> yanlılık uyarısı susar.
        assert 'warn.hybrid.htpb_coeff_bias' not in kodlar(sonuc)
        uyarilar = [u for u in sonuc['warnings']
                    if isinstance(u, dict)
                    and u['code'] == 'warn.hybrid.regression_coeff_user_override']
        assert uyarilar, 'kullanıcının ezmesi hiç bildirilmiyor'
        p = uyarilar[0]['params']
        assert p['a_pct'] == pytest.approx(
            (1.5e-4 / katalog['a'] - 1.0) * 100.0, abs=0.05)
        assert p['n_pct'] == pytest.approx(
            (0.4 / katalog['n'] - 1.0) * 100.0, abs=0.05)


# ---------------------------------------------------------------------------
# KALEM 3 — C_F geçerlilik aralığı: ayrılma taraması + fiziksel alt sınır
# ---------------------------------------------------------------------------

class TestItkiKatsayisiSinirlari:

    EPS_TARAMA = (2, 4, 6, 8, 10, 16, 20, 25, 30, 35, 36, 40, 60, 100, 150)

    def test_hicbir_genisleme_oraninda_sacma_deger_uretilmez(self):
        """ÖLÇÜLEN eski davranış: ε=35 -> Isp 7,6 s ; ε=40 -> C_F negatif."""
        for eps in self.EPS_TARAMA:
            motor, _ = kos(thrust=1000, burn_time=10, expansion_ratio=eps)
            assert np.isfinite(motor.CF) and motor.CF > 0.0, (
                f'ε={eps}: C_F = {motor.CF}')
            # Katı yakıtlı/hibrit sınıfında 50 s altı Isp fiziksel değil.
            assert motor.Isp > 50.0, f'ε={eps}: Isp = {motor.Isp} s'

    def test_ayrilma_esigi_altinda_sayilar_degismez(self):
        """ε ≤ ε_sep ise taban UYGULANMAZ; eski aritmetikle bit-özdeş."""
        motor, sonuc = kos(thrust=1000, burn_time=10, expansion_ratio=4)
        ekran = sonuc['nozzle_expansion_screen']
        assert ekran['separation_predicted'] is False
        assert ekran['cf_used'] == pytest.approx(ekran['cf_attached_flow'],
                                                 rel=1e-12)
        assert motor.CF == pytest.approx(ekran['cf_attached_flow'], rel=1e-12)

    def test_ayrilma_ustunde_taban_uygulanir_ve_uyarilir(self):
        motor, sonuc = kos(thrust=1000, burn_time=10, expansion_ratio=30)
        ekran = sonuc['nozzle_expansion_screen']
        assert ekran['separation_predicted'] is True
        assert ekran['floor_applied'] is True
        assert ekran['cf_used'] > ekran['cf_attached_flow']
        assert motor.CF == pytest.approx(ekran['cf_at_separation_limit'])
        assert 'warn.hybrid.nozzle_flow_separation' in kodlar(sonuc)

    def test_ayrilma_esigi_summerfield_sabitinden_gelir(self):
        """Eşik KOPYALANMAZ: hrma/flow/separation.py tek tanım noktasıdır."""
        _, sonuc = kos(thrust=1000, burn_time=10, expansion_ratio=30)
        ekran = sonuc['nozzle_expansion_screen']
        assert ekran['summerfield_factor'] == SUMMERFIELD_FACTOR_DEFAULT
        assert ekran['separation_pressure_bar'] == pytest.approx(
            SUMMERFIELD_FACTOR_DEFAULT * 1.0)

    def test_vakumda_olcut_uygulanmaz(self):
        _, sonuc = kos(thrust=1000, burn_time=10, expansion_ratio=60,
                       atmospheric_pressure=0.0)
        ekran = sonuc['nozzle_expansion_screen']
        assert ekran['separation_predicted'] is False
        assert 'vacuum' in ekran['not_applicable_reason']

    def test_fiziksel_olmayan_tasarim_ANLAMLI_hatayla_reddedilir(self):
        """Ortam basıncı hazne basıncının üstündeyse lüle geriye iter.

        Eskiden bu koşu ilerideki bir ``int(NaN)`` çağrısında ölüyordu ve
        kullanıcıya giden mesaj sorunun ne olduğu hakkında hiçbir şey
        söylemiyordu.
        """
        with pytest.raises(ValueError) as hata:
            kos(thrust=1000, burn_time=10, chamber_pressure=1,
                atmospheric_pressure=3.0, expansion_ratio=20)
        metin = str(hata.value)
        assert 'over-expanded' in metin
        assert 'expansion ratio' in metin
        assert 'ambient pressure' in metin
        assert 'NaN' not in metin

    def test_transient_cf_basinc_dustukce_negatife_gecmez(self, varsayilan):
        """ÖLÇÜLEN eski davranış (ε=25, P_a=1 bar): Pc=1 bar -> C_F = −23,2."""
        motor, _ = varsayilan
        tb = TransientBallistics(motor, feed_mode='regulated')
        for pc_bar in (20, 10, 5, 2, 1, 0.5, 0.1):
            cf = tb._thrust_coefficient(pc_bar * 1e5)
            assert np.isfinite(cf), f'Pc={pc_bar} bar: C_F = {cf}'
            assert cf >= 0.0, f'Pc={pc_bar} bar: C_F = {cf} (negatif itki)'

    def test_transient_ortamin_ustunde_kalan_basincta_taban_pozitif(
            self, varsayilan):
        """P_c > P_a olduğu sürece ayrılma tabanı C_F'i POZİTİF tutar."""
        motor, _ = varsayilan
        tb = TransientBallistics(motor, feed_mode='regulated')
        for pc_bar in (20, 10, 5, 3):
            cf = tb._thrust_coefficient(pc_bar * 1e5)
            assert cf > 0.0, f'Pc={pc_bar} bar: C_F = {cf}'

    def test_transient_sifir_basincta_cokmez(self, varsayilan):
        motor, _ = varsayilan
        tb = TransientBallistics(motor, feed_mode='regulated')
        assert tb._thrust_coefficient(0.0) == 0.0
        assert tb._thrust_coefficient(float('nan')) == 0.0

    def test_transient_sifira_kirpma_sessiz_degildir(self, varsayilan):
        """Negatif C_F sıfıra kırpılıyorsa adım SAYILIR (sessiz yedek yasak)."""
        motor, _ = varsayilan
        tb = TransientBallistics(motor, feed_mode='regulated')
        assert tb._negative_cf_steps == 0
        tb._thrust_coefficient(0.1 * 1e5)
        assert tb._negative_cf_steps == 1

    def test_transient_ayrilma_beyani_sonucta_durur(self, varsayilan):
        motor, _ = varsayilan
        sonuc = TransientBallistics(motor, feed_mode='regulated').solve()
        blok = sonuc['flow_separation']
        assert blok['criterion'] == 'summerfield'
        assert blok['factor'] == SUMMERFIELD_FACTOR_DEFAULT
        assert blok['steps_total'] == len(sonuc['time'])
        assert 0 <= blok['steps_floored'] <= blok['steps_total']


# ---------------------------------------------------------------------------
# KALEM 4 — iki seri aynı yanma süresini söyler
# ---------------------------------------------------------------------------

class TestSeriSuresi:

    def test_itki_ve_port_serileri_ayni_anda_biter(self, varsayilan):
        motor, sonuc = varsayilan
        itki = sonuc['thrust_curve']['time']
        port = sonuc['port_history']['time']
        assert itki[-1] == pytest.approx(port[-1], rel=1e-12)
        assert itki[-1] == pytest.approx(motor.t_burn_effective, rel=1e-12)

    def test_seriler_sifirdan_baslar_ve_esit_uzunluktadir(self, varsayilan):
        _, sonuc = varsayilan
        egri = sonuc['thrust_curve']
        assert egri['time'][0] == pytest.approx(0.0)
        assert len(egri['time']) == len(egri['thrust']) == len(
            egri['pressure']) == len(egri['mass_flow'])

    def test_kirpilan_kosuda_da_seriler_ayni_anda_biter(self, kirpilan):
        motor, sonuc = kirpilan
        itki = sonuc['thrust_curve']['time']
        port = sonuc['port_history']['time']
        assert itki[-1] == pytest.approx(port[-1], rel=1e-12)
        assert itki[-1] == pytest.approx(motor.t_burn_effective, rel=1e-12)

    def test_impuls_ozdesligi_trapez_altinda_da_kapanir(self, varsayilan):
        """I = Isp_ort · m_harcanan · g0 — integratör değişti, özdeşlik duruyor."""
        _, sonuc = varsayilan
        reg = sonuc['of_shift']['regulated']
        assert reg['total_impulse_Ns'] == pytest.approx(
            reg['isp_mass_avg_s'] * reg['propellant_consumed_kg'] * G0,
            rel=1e-9)

    def test_of_shift_impulsu_yayimlanan_egriden_hesaplanir(self, varsayilan):
        _, sonuc = varsayilan
        egri = sonuc['thrust_curve']
        assert sonuc['of_shift']['regulated']['total_impulse_Ns'] == (
            pytest.approx(float(np.trapz(egri['thrust'], egri['time'])),
                          rel=1e-9))
