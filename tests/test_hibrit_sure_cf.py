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

ÖH Faz B-1 EKİ (2026-08-26) — HTPB kanalının ÇAPALARI. Dosyanın KALEM 2
bekçisi yanlılık beyanını ürün sabitinden ithal ediyordu; katsayı ve beyan
birlikte güncellenince SESSİZCE yeşil kalıyordu (P14S1-02). İthal kaldırıldı,
beklenti ölçülmüş vakalara çapalandı ve katsayının KENDİSİNE kasıtlı değer
bekçileri yazıldı (P14M2-14). KISIT: ``hrma/templates/advanced.html``in
regresyon ön-dolgusu/yuvarlaması ile bu dosyadaki HTPB_* literalleri AYNI
COMMIT'te güncellenmek zorundadır — ayrışırlarsa ürünün yanlılık uyarısı
sessizce susar. Ayrıntı ve kaynaklar için ÇAPA 1-3 bloğuna bak.
"""

import ast
import re
from pathlib import Path

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import (
    REGRESSION_COEFF_CATALOG_MATCH_RTOL,
    HybridRocketEngine,
)
from hrma.analysis.transient_ballistics import TransientBallistics
from hrma.data.propellant_database import HYBRID_REGRESSION_COEFFICIENTS
from hrma.flow.separation import SUMMERFIELD_FACTOR_DEFAULT
from hrma.utils.numeric_compat import trapezoid

G0 = 9.80665

DEPO = Path(__file__).resolve().parents[1]
ARAYUZ_SABLONU = DEPO / 'hrma' / 'templates' / 'advanced.html'

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
        # ÖH D15/P1B2-03 — BEKÇİ ÇEVRİLDİ (ÖK-05).
        # Eski satır ``sonuc['total_impulse'] == approx(motor.I_total)``
        # idi ve KUSURU SÖZLEŞMEYE ÇEVİRİYORDU: ``motor.I_total`` İSTENEN
        # impulstür, alan ise künyesinde birebir "total_impulse is the
        # DELIVERED impulse" diye beyanlıdır. Bekçi bu hâliyle "teslim
        # edilen alan istenen değeri taşısın" diye ısrar ediyordu.
        # Yeni kilit: alan HER KOŞUDA teslim edilen impulstür ve
        # istenen değer adıyla YANINDA durur.
        assert sonuc['total_impulse'] == pytest.approx(
            sonuc['total_impulse_delivered_Ns'], rel=0, abs=0)
        assert sonuc['total_impulse_requested_Ns'] == pytest.approx(
            motor.I_total)
        assert 'DELIVERED impulse of this run in EVERY case' in \
            sonuc['total_impulse_basis']
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
        beklenen = float(trapezoid(egri['thrust'], egri['time']))
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
# HTPB KANALI — ÖLÇÜLMÜŞ ÇAPALAR (ürün sabitinden BAĞIMSIZ)
#
# ÖH Faz B-1, ÖNCE-BEKÇİ-YAZ adım 10 (P14 savcı §3.1 + §3.2-d). Bu blok fizik
# dalgasının ÖN KOŞULUDUR: regresyon katsayısına dokunulmadan ÖNCE, katsayıyı
# ve onun yanlılık beyanını koruyan bekçilerin kusuru GERÇEKTEN görmesi gerekir.
# Kapattığı ölçülmüş kusurlar:
#
#   P14S1-02 (orta) — bu dosyanın yanlılık bekçisi (:197-198) ürün sabitlerini
#       İTHAL EDİYORDU (``HTPB_COEFF_DB_BIAS_PCT``, ``..._MEDAPE_PCT``;
#       hybrid_rocket_engine.py:325-326). İddia, koruduğu eşikten TÜRETİLMİŞTİ:
#       fizik dalgası katsayıyı düzeltip yanlılık sayısını da güncellerse bekçi
#       SESSİZCE YEŞİL kalır ve yeni sayının doğruluğu hiçbir yerde sınanmaz.
#       İthal KALDIRILDI; beklenti artık aşağıdaki literaller + BAĞIMSIZ ölçüm
#       bantlarıdır (``test_yanlilik_bekcisi_urun_sabitini_ithal_etmez`` bu
#       kararı mekanik olarak korur).
#   P14M2-14 (orta/yüksek) — HTPB ``a`` katsayısının %+20 bozulmasını yakalayan
#       iki bekçi de KAZA ESERİYDİ: biri arayüz yuvarlaması testi, biri belge
#       bayatlık testi. Katsayının KENDİSİNİ konu edinen kasıtlı bir değer
#       bekçisi yoktu; aşağıdaki üç bekçi (katalog kilidi, SI birim zinciri,
#       arayüz ön-dolgusu) o boşluğu kapatır.
#
# ÇAPA 1 — bugün ÜRÜNÜN kullandığı katsayı.
#   Kaynak: hrma/data/propellant_database.py:31-34
#           ``'htpb': {'a': 3.68e-5, 'n': 0.555}``, künye "Doran et al.,
#           AIAA 2007-5352; r[mm/s] = 0,132·G_ox[g/cm²·s]^0,555".
#   NOT: künyenin kendisi tartışmalıdır (birincil metin ücretli ve hiç
#   doğrulanamadı; docs/arastirma/fizik/A3-hibrit-regresyon.md:270-285). Bu
#   bekçiler künyenin DOĞRULUĞUNU değil, bugünkü sayının SESSİZCE değişmemesini
#   korur.
HTPB_KATALOG_A = 3.68e-5
HTPB_KATALOG_N = 0.555
#   Yayımlanmış korelasyonun kendi birimlerindeki hâli (a_mm: mm/s, G: g/cm²·s).
#   a_SI = a_mm·1e-3 · 10^(−n) özdeşliği
#   ``test_katalog_katsayisi_yayimlanmis_korelasyonun_si_karsiligidir``da
#   sınanır: birim zinciri kayarsa katsayı da kayar.
HTPB_YAYIMLANMIS_A_MM = 0.132
HTPB_YAYIMLANMIS_N = 0.555
#   Arayüzün geri gönderdiği yuvarlama: advanced.html:3248 katsayıyı
#   ``toExponential(3)`` ile yazıyor -> 4 anlamlı hane.
HTPB_ARAYUZ_YUVARLAMASI = 3.680e-05

# ÇAPA 2 — ürünün BUGÜN yayımladığı yanlılık beyanı (warn.hybrid.htpb_coeff_bias
#   yükünün ``bias_pct``/``medape_pct`` alanları). Sayının kendisi ürün kodunda
#   yaşıyor ama bu dosya onu İTHAL ETMEZ: literal olarak yazılıdır ki değişince
#   kırmızıya dönsün.
#   Kaynak (ölçüm 1, depo-içi): hrma/engines/hybrid_rocket_engine.py:314-326 —
#   "n=0,555 sabit tutulup DB'nin HTPB kayıtlarına (n=43 test; carmicino2013 +
#   rezaei2018) en iyi a arandığında a=6,24e-5 çıkıyor; koddaki 3,68e-5'in 1,70
#   KATI ... (bias −%39,5, medAPE %46,6)".
HTPB_BEYAN_BIAS_PCT = -39.5
HTPB_BEYAN_MEDAPE_PCT = 46.6

# ÇAPA 3 — ürün kodundan BAĞIMSIZ ölçüm (ölçüm 2, fizik araştırma programı):
#   docs/arastirma/fizik/A3-hibrit-regresyon.md, 2026-08-22.
#     :288-293  46 bağımsız saf-HTPB noktası, üç kampanya, G_ox 3,2-25,9
#               g/cm²·s (anomali bayraklı + metal/karbon yüklü grainler hariç):
#               HRMA (0,132/0,555) havuz  bias −%47,6 / medAPE %49,4
#               Rezaei (n=29) −%50,6 / %50,9 ; Carmicino (n=16) −%41,9 / %43,5
#     :187-192  kampanya bazında HRMA yanlılığı: Rezaei −%50,6,
#               Carmicino −%41,8, Heydari −%50,3
#     :173-175  akı bandına göre en ağır alt havuz: G_ox ≤ 6 g/cm²·s -> −%54,6
#   İki ölçüm AYNI KAYIT HAVUZUNU kullanmıyor (43 ⟷ 46 kayıt) ve ürün yolu
#   G_total kapanışıyla koşuyor (propellant_database.py:22-29: G_ox-fit katsayı
#   G_total ile kullanılınca regresyon sistematik +%10-18 yükselir). Bu yüzden
#   iki sayı birebir eşit BEKLENMEZ — ama işaret, mertebe ve gövde ortaktır.
HTPB_A3_HAVUZ_BIAS_PCT = -47.6
HTPB_A3_HAVUZ_MEDAPE_PCT = 49.4
#   Bağımsız ölçümlerin GÖVDESİ (yalnız A3; ürün beyanı bu bandın DIŞINDA —
#   aşağıdaki xfail bekçisi bunu görünür tutar).
HTPB_A3_KAMPANYA_BIAS_BANDI = (-50.6, -41.8)
HTPB_A3_KAMPANYA_MEDAPE_BANDI = (43.5, 50.9)
#   İki bağımsız ölçümün BİRLEŞİK gövdesi: alt uç A3'ün en ağır alt havuzu
#   (−%54,6, A3:173), üst uç deponun kendi 43 kayıtlı F019 ölçümü (−%39,5).
#   İki kenar da ÖLÇÜLEN sayıdır — pay uydurulmadı.
HTPB_BIRLESIK_BIAS_BANDI = (-54.6, -39.5)


def _guncelleme_protokolu(alan, beklenen, olculen):
    """Bilinçli-kilitleyen bekçinin hata metni (desen: test_field_wiring_layer_b.py:851).

    Bekçi "yanlış" demiyor; "sessizce değişmiş" diyor ve nasıl bilinçli
    güncelleneceğini yazıyor.
    """
    return (
        f'HTPB {alan}: ürün {olculen!r} yayımlıyor, bu bekçi {beklenen!r} '
        'bekliyor.\n'
        'Bu bekçi ürün sabitini BİLEREK İTHAL ETMEZ (P14S1-02: eşiği kendinden '
        'türeten bekçi, eşik değişince sessizce yeşil kalır). Sayı bilinçli '
        'güncellenir:\n'
        '  1) Yeni sayıyı ÖLÇEN kaydı yaz: hangi veri kümesi, kaç nokta, hangi '
        'kampanyalar, hangi akı kapanışı (G_ox mu G_total mı). Desen: '
        'docs/arastirma/fizik/A3-hibrit-regresyon.md §2.1.\n'
        '  2) Bu dosyadaki HTPB_* literalini ve ölçüm bandını AYNI commit\'te '
        'güncelle; kaynağı dosya+satır olarak yaz.\n'
        '  3) Katsayı da değiştiyse hrma/templates/advanced.html:1302 (ön-dolgu '
        '``value="0.0000368"``) ve :3064 (JS katalog ``a: 3.68e-5``) AYNI '
        'commit\'te güncellenmeli — yoksa arayüzün geri gönderdiği sayı '
        'katalogla eşleşmez, ürün bunu "kullanıcı kendi katsayısını girdi" '
        'sanar ve yanlılık uyarısı SUSAR (ölçüldü: P14M2-14).\n'
        'Sessizce eşiği yeni sayıya çekmek yasaktır: bu bekçinin tek işi o '
        'sessiz güncellemeyi kırmızıya çevirmektir.'
    )


def _htpb_yanlilik_uyarisi():
    """Ürünün KENDİ akışında yayımladığı yanlılık uyarısının yükü."""
    _, sonuc = kos(thrust=1000, burn_time=10)
    uyarilar = [u for u in sonuc['warnings']
                if isinstance(u, dict)
                and u['code'] == 'warn.hybrid.htpb_coeff_bias']
    assert uyarilar, 'yanlılık uyarısı hiç doğmuyor (kapı yine ölmüş olabilir)'
    return uyarilar[0]['params']


def _sablon_metni():
    assert ARAYUZ_SABLONU.is_file(), f'arayüz şablonu yok: {ARAYUZ_SABLONU}'
    return ARAYUZ_SABLONU.read_text(encoding='utf-8')


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
        # P14S1-02: bu iki satır eskiden ürün sabitlerini İTHAL EDİYORDU.
        # Literal + ölçülmüş bant çapası için ÇAPA 2/3 bloğuna bak.
        assert p['bias_pct'] == HTPB_BEYAN_BIAS_PCT, _guncelleme_protokolu(
            'yanlılık beyanı (bias_pct)', HTPB_BEYAN_BIAS_PCT, p['bias_pct'])
        assert p['medape_pct'] == HTPB_BEYAN_MEDAPE_PCT, _guncelleme_protokolu(
            'medAPE beyanı (medape_pct)', HTPB_BEYAN_MEDAPE_PCT,
            p['medape_pct'])

    def test_arayuzun_yuvarladigi_deger_de_katalog_sayilir(self):
        """advanced.html katsayıyı 3.680e-05 diye yuvarlayıp geri gönderiyor.

        KISIT (P14M2-14): bu testin kırmızısı KAZA ESERİDİR — konusu arayüz
        yuvarlamasıdır, katsayı doğruluğu değil. Katalog değişirse
        ``advanced.html`` yuvarlaması, bu testteki sayı ve aşağıdaki kasıtlı
        değer bekçileri AYNI COMMIT'te güncellenmelidir; aksi hâlde ürün
        arayüzün gönderdiği sayıyı "kullanıcı ezmesi" sanar ve yanlılık uyarısı
        susar.
        """
        _, sonuc = kos(thrust=1000, burn_time=10,
                       regression_a=HTPB_ARAYUZ_YUVARLAMASI,
                       regression_n=HTPB_KATALOG_N)
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
# ÖH Faz B-1 / adım 10 — HTPB kanalının KASITLI değer bekçileri
# (P14S1-02, P14M2-14; fizik dalgasının ön koşulu)
# ---------------------------------------------------------------------------

class TestHtpbCapalari:

    def test_yanlilik_bekcisi_urun_sabitini_ithal_etmez(self):
        """TERS BEKÇİ: onarımı geri alan hamleyi mekanik olarak yakalar.

        En kolay "düzeltme", beyan değişince literali silip ürün sabitini
        yeniden ithal etmektir — o an bekçi tekrar eşiği kendinden türetir
        (P14S1-02) ve bir daha hiçbir şey söylemez. Bu test onu kırmızıya
        çevirir. Metin araması DEĞİL, AST: yorumda/hata metninde sabit adının
        geçmesi serbesttir, ithal edilmesi yasaktır.
        """
        agac = ast.parse(Path(__file__).read_text(encoding='utf-8'))
        ithal = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.ImportFrom):
                ithal.update(ad.name for ad in dugum.names)
            elif isinstance(dugum, ast.Import):
                ithal.update(ad.name for ad in dugum.names)
        yasak = {'HTPB_COEFF_DB_BIAS_PCT', 'HTPB_COEFF_DB_MEDAPE_PCT'}
        assert not (ithal & yasak), (
            'Yanlılık bekçisi ürün sabitini yeniden ithal etmiş: '
            f'{sorted(ithal & yasak)}.\n'
            'Bir eşiği koruyan iddia o eşikten TÜRETİLMİŞ olamaz (P14 savcı '
            '§3.1 adım 9-10). Beklenen değer bu dosyada literal olarak durur '
            've kaynağı ÇAPA 2/3 bloğunda yazılıdır.')

    def test_yayimlanan_yanlilik_olculmus_bandin_icinde(self):
        """Beyan, ürün sabitinden değil ÖLÇÜMDEN doğrulanır.

        Bant iki BAĞIMSIZ ölçümün birleşik gövdesidir (ÇAPA 3): alt uç
        A3:173'ün en ağır alt havuzu (−%54,6), üst uç deponun kendi 43 kayıtlı
        F019 ölçümü (−%39,5). Fizik dalgası katsayıyı Ö1'e (Z&K Tablo 2
        geometrik ortalaması) taşırsa yanlılık −%5,1'e iner: bu bant o anda
        KIRMIZI verir ve yeni sayının ölçümünü ister.
        """
        p = _htpb_yanlilik_uyarisi()
        alt, ust = HTPB_BIRLESIK_BIAS_BANDI
        assert alt <= p['bias_pct'] <= ust, _guncelleme_protokolu(
            f'yanlılığı ölçülen bant {HTPB_BIRLESIK_BIAS_BANDI} dışında',
            f'{alt} ≤ bias ≤ {ust}', p['bias_pct'])
        # Yön, sayıdan bağımsız bir FİZİK iddiasıdır: model regresyonu DÜŞÜK
        # tahmin ediyor -> yakıt debisi düşük, O/F yüksek, grain ~%25 fazla
        # uzun (hybrid_rocket_engine.py:315-322). Güvenli olmayan yön budur.
        assert p['bias_pct'] < 0.0, (
            'Yanlılığın İŞARETİ döndü. Bu yalnız bir sayı değişikliği değil: '
            'sapmanın yönü emniyet argümanının kendisidir (düşük tahmin -> '
            'grain erken tükenir). Yeni ölçümü ve yönün gerekçesini yaz.')
        alt_m, ust_m = HTPB_A3_KAMPANYA_MEDAPE_BANDI
        assert alt_m <= p['medape_pct'] <= ust_m, _guncelleme_protokolu(
            f'medAPE ölçülen bant {HTPB_A3_KAMPANYA_MEDAPE_BANDI} dışında',
            f'{alt_m} ≤ medAPE ≤ {ust_m}', p['medape_pct'])

    @pytest.mark.xfail(
        strict=True,
        reason='ÖH defter P14S1-02-b (ölçülmüş, açık): ürünün yayımladığı '
               'yanlılık (−%39,5) bağımsız 46 noktalı ölçümün HTPB/N2O '
               'kampanya gövdesinin (−%50,6 … −%41,8) DIŞINDA — 2,3 puan. İki '
               'aday açıklama var ve hiçbiri ölçülmedi: (a) kayıt havuzları '
               'farklı (43 ⟷ 46), (b) ürün yolu G_total kapanışıyla koşuyor ve '
               'bu regresyonu +%10-18 kaldırıyor. Fizik dalgası katsayıya '
               'dokunmadan önce iki ölçümü UZLAŞTIRMALI; uzlaşınca bu xfail '
               'kaldırılır (strict=True: sessizce yeşile dönemez).\n'
               'ÖH D31 / OH-B1-05 — BORCUN YARISI ÖDENDİ, İM DURUYOR: ürün '
               'artık tek sayıyı TEK BAŞINA yayımlamıyor; aynı uyarıda üç '
               'bağımsız HTPB/N₂O kampanyası (Rezaei 2018 −%50,6 / '
               'Carmicino 2013 −%41,8 / Heydari 2017 −%50,3), 46 noktalı '
               'havuz (−%47,6) ve reconciled=False ADIYLA duruyor '
               '(tests/test_d31_hibrit_a1.py::TestOhB105YanlilikGovdesi). '
               'ÖDENMEYEN yarı: iki ölçümü UZLAŞTIRAN yeniden fit — hangi '
               'havuz (43 ⟷ 46) ve hangi akı kapanışı (G_ox ⟷ G_total) '
               'farkı açıklıyor. Katsayıya DOKUNULMADI; ASTRA uyarısı '
               '(14 Eyl 2026) uyarınca Z&K 2006 Tablo 2 OKSİJEN satırları '
               'N2O katsayısını çürütemez, kaynak eşleşmeden değiştirilmez.')
    def test_yayimlanan_yanlilik_bagimsiz_kampanya_govdesinde(self):
        """A3'ün üç HTPB/N₂O kampanyasının hiçbiri ürünün beyanı kadar hafif değil."""
        p = _htpb_yanlilik_uyarisi()
        alt, ust = HTPB_A3_KAMPANYA_BIAS_BANDI
        assert alt <= p['bias_pct'] <= ust, (
            f"ürün {p['bias_pct']} yayımlıyor; A3:187-192'nin kampanya gövdesi "
            f'{HTPB_A3_KAMPANYA_BIAS_BANDI} (havuz {HTPB_A3_HAVUZ_BIAS_PCT}, '
            f'A3:293)')

    def test_katalog_katsayisi_bugunku_deger(self):
        """KASITLI DEĞER BEKÇİSİ (P14M2-14).

        Ölçüldü: ``a``nın %+20 bozulması (3,68e-5 -> 4,416e-5) 373 testlik
        kümede tek bir kırmızı üretiyordu ve o da arayüz yuvarlaması testiydi;
        adı doğrulama olan dosyanın (test_hybrit_regression_validation.py) 16
        testinin 16'sı YEŞİL kalıyordu — çünkü o dosya kendi docstring'inde
        toleransını "±%20-30 saçılır" diye ilan ediyor. Katsayının KENDİSİNİ
        konu edinen bekçi buydu, yoktu.
        """
        katalog = HYBRID_REGRESSION_COEFFICIENTS['htpb']
        assert katalog['a'] == HTPB_KATALOG_A, _guncelleme_protokolu(
            'katalog a katsayısı', HTPB_KATALOG_A, katalog['a'])
        assert katalog['n'] == HTPB_KATALOG_N, _guncelleme_protokolu(
            'katalog n üssü', HTPB_KATALOG_N, katalog['n'])

    def test_katalog_katsayisi_yayimlanmis_korelasyonun_si_karsiligidir(self):
        """Birim zinciri: a_SI = a_mm·1e-3 · 10^(−n)  (G g/cm²·s -> kg/m²·s).

        Katsayı yalnız "bugünkü sayı" değil, YAYIMLANMIŞ bir korelasyonun birim
        dönüşümüdür. Zincir kayarsa (ör. 10^(−n) çarpanı düşerse katsayı 3,6
        kat büyür) bu bekçi kırmızı verir. Tolerans uydurma değil: katalog
        değeri 3 ondalıklı mantise yuvarlanmıştır, yarım-birim = 0,005/3,68 =
        1,4e-3.
        """
        beklenen = HTPB_YAYIMLANMIS_A_MM * 1e-3 * 10.0 ** (-HTPB_YAYIMLANMIS_N)
        assert HYBRID_REGRESSION_COEFFICIENTS['htpb']['a'] == pytest.approx(
            beklenen, rel=1.5e-3), _guncelleme_protokolu(
            f'a_SI birim zinciri (a_mm={HTPB_YAYIMLANMIS_A_MM}, '
            f'n={HTPB_YAYIMLANMIS_N} -> {beklenen:.4e})',
            beklenen, HYBRID_REGRESSION_COEFFICIENTS['htpb']['a'])
        assert HYBRID_REGRESSION_COEFFICIENTS['htpb']['n'] == pytest.approx(
            HTPB_YAYIMLANMIS_N, rel=1e-12)

    def test_arayuz_on_dolgusu_katalogla_ayni_sayidir(self):
        """(iii) kolu: advanced.html ile katalog AYNI COMMIT'te güncellenir.

        Ürünün yanlılık kapısı "kullanıcının gönderdiği a/n katalogla eşit mi"
        sorusuna dayanıyor (hybrid_rocket_engine.py:1005-1018). Arayüz ön-dolgu
        sayısı katalogdan ayrılırsa kapı "kullanıcı kendi katsayısını girdi"
        der ve uyarı SUSAR — kusur ürün tarafında, sessizce.
        """
        metin = _sablon_metni()
        alan = re.search(r'id="regression_a"\s+value="([0-9.eE+-]+)"', metin)
        ussu = re.search(r'id="regression_n"\s+value="([0-9.eE+-]+)"', metin)
        js = re.search(r"'htpb':\s*\{[^}]*?\ba:\s*([0-9.eE+-]+)\s*,"
                       r"\s*n:\s*([0-9.eE+-]+)", metin)
        assert alan and ussu and js, (
            'advanced.html regresyon alanları/JS kataloğu bulunamadı — şablon '
            'yeniden düzenlendiyse bu bekçinin deseni de güncellenmeli')
        katalog = HYBRID_REGRESSION_COEFFICIENTS['htpb']
        for ad, ham in (('input value (:1302)', alan.group(1)),
                        ('JS katalog a (:3064)', js.group(1))):
            assert float(ham) == pytest.approx(katalog['a'], rel=1e-12), (
                _guncelleme_protokolu(f'advanced.html {ad}', katalog['a'],
                                      float(ham)))
        for ad, ham in (('input value (:1313)', ussu.group(1)),
                        ('JS katalog n (:3064)', js.group(2))):
            assert float(ham) == pytest.approx(katalog['n'], rel=1e-12), (
                _guncelleme_protokolu(f'advanced.html {ad}', katalog['n'],
                                      float(ham)))

    def test_arayuz_yuvarlamasi_urunun_eslestirme_kapisini_gecer(self):
        """Yuvarlama TÜRETİLİR, sayı KİLİTLENİR — ikisi ayrı iddia.

        advanced.html:3248 katsayıyı ``toExponential(3)`` ile geri yazıyor (4
        anlamlı hane). Bu bekçi (a) yuvarlamanın ürünün eşleştirme kapısından
        geçtiğini KATALOGDAN TÜRETEREK sınar — katalog değişse de doğru kalır;
        (b) yukarıdaki testte kullanılan 3.680e-05 literalinin bugünkü
        katalogla tutarlı olduğunu doğrular — katalog değişirse o literal de
        AYNI commit'te güncellenmelidir.
        """
        katalog_a = HYBRID_REGRESSION_COEFFICIENTS['htpb']['a']
        yuvarlanmis = float(f'{katalog_a:.3e}')  # JS toExponential(3) karşılığı
        bagil = abs(yuvarlanmis - katalog_a) / katalog_a
        # 4 anlamlı haneye yuvarlamanın matematiksel üst sınırı 5e-4.
        assert bagil <= 5e-4, f'yuvarlama hatası beklenenden büyük: {bagil}'
        assert bagil < REGRESSION_COEFF_CATALOG_MATCH_RTOL, (
            'Ürünün katalog-eşleştirme kapısı (REGRESSION_COEFF_CATALOG_MATCH_'
            f'RTOL = {REGRESSION_COEFF_CATALOG_MATCH_RTOL}) arayüzün kendi '
            f'yuvarlamasından ({bagil}) daha dar. Bu hâlde ürün, KENDİ formunun '
            'geri gönderdiği sayıyı "kullanıcı ezmesi" sayar ve yanlılık '
            'uyarısı susar.')
        assert yuvarlanmis == HTPB_ARAYUZ_YUVARLAMASI, _guncelleme_protokolu(
            'arayüz yuvarlaması (HTPB_ARAYUZ_YUVARLAMASI)',
            yuvarlanmis, HTPB_ARAYUZ_YUVARLAMASI)


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
        """ε ≤ ε_sep ise taban UYGULANMAZ; eski aritmetikle bit-özdeş.

        ÖH D22 / hibrit-a1 — BEKÇİ ÇEVRİLDİ (gerekçe). Bu test
        ``motor.CF == ekran['cf_attached_flow']`` diye kilitliyordu ve bu
        eşitlik D20/B1-12'den (kayıp kümesi manşete taşındı) beri KUSURUN
        KENDİSİDİR: manşet C_F artık kayıpsız değeri η_sürtünme × η_iki-faz
        × η_kinetik ile çarpar, ekran ise KAYIPSIZ ayrılma hükmünü yayımlar.
        Ölçülen (ε=4, 1000 N, 20 bar): manşet/ekran farkı −%1,1758 =
        kayıp çarpımının kendisi. Testin AMACI değişmedi — ayrılma tabanının
        uygulanmadığı bant hâlâ kilitli; kıyas artık DOĞRU iki büyüklük
        arasında yapılıyor (kayıpsız ⟷ kayıpsız) ve manşetin kayıp kümesini
        taşıdığı ayrıca ölçülüyor.
        """
        motor, sonuc = kos(thrust=1000, burn_time=10, expansion_ratio=4)
        ekran = sonuc['nozzle_expansion_screen']
        assert ekran['separation_predicted'] is False
        assert ekran['cf_used'] == pytest.approx(ekran['cf_attached_flow'],
                                                 rel=1e-12)
        # Ekran kayıpsız hükmü yayımlar; manşetin kayıpsız tarafı odur.
        assert motor.CF_lossless == pytest.approx(ekran['cf_attached_flow'],
                                                  rel=1e-12)
        # Manşet ise AYNI değerin kayıp kümesiyle çarpılmışıdır.
        carpim = motor.headline_loss_set['loss_product']
        assert motor.CF == pytest.approx(ekran['cf_used'] * carpim, rel=1e-12)
        assert carpim < 1.0

    def test_ayrilma_ustunde_taban_uygulanir_ve_uyarilir(self):
        """ÖH D22 / hibrit-a1 — BEKÇİ ÇEVRİLDİ; gerekçe yukarıdaki testte.

        ``motor.CF == ekran['cf_at_separation_limit']`` eşitliği de kayıp
        kümesi manşete taşındıktan sonra kusuru koruyordu. Ayrılma tabanının
        UYGULANDIĞI iddiası değişmedi; kıyas kayıpsız tarafa taşındı.
        """
        motor, sonuc = kos(thrust=1000, burn_time=10, expansion_ratio=30)
        ekran = sonuc['nozzle_expansion_screen']
        assert ekran['separation_predicted'] is True
        assert ekran['floor_applied'] is True
        assert ekran['cf_used'] > ekran['cf_attached_flow']
        assert motor.CF_lossless == pytest.approx(
            ekran['cf_at_separation_limit'])
        carpim = motor.headline_loss_set['loss_product']
        assert motor.CF == pytest.approx(ekran['cf_used'] * carpim, rel=1e-12)
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

        ÖH D15/hibrit-a1 (31 Ağu 2026) — BEKÇİ ÇEVRİLDİ, KAPSAMI GENİŞLETİLDİ.
        Bu vaka (Pc = 1 bar < Pa = 3 bar) artık DAHA ERKEN ve daha temel bir
        kapıdan dönüyor: Pc/Pa = 0,333 iken boğaz TIKANMIYOR
        (gerekli oran ((γ+1)/2)^(γ/(γ−1)) ≈ 1,73), yani ortada
        boyutlandırılabilir bir süpersonik lüle YOKTUR — aşırı genişleme
        hükmü bu rejimde zaten tanımsız bir geometriye veriliyordu
        (P1B1-04, hrma/engines/hybrid_rocket_engine.py:_gate_choked_throat).
        Testin AMACI değişmedi: fiziksel olmayan tasarım, sorunu ADIYLA
        söyleyen bir ValueError ile reddedilir ve mesajda 'NaN' geçmez.
        Eski aşırı-genişleme metni ayrıca sınanır (aşağıdaki doğrudan
        _gate_finite_cf çağrısı) ki o kapı sessizce ölmesin.
        """
        with pytest.raises(ValueError) as hata:
            kos(thrust=1000, burn_time=10, chamber_pressure=1,
                atmospheric_pressure=3.0, expansion_ratio=20)
        metin = str(hata.value)
        assert 'not choked' in metin
        assert 'chamber_pressure' in metin
        assert 'atmospheric_pressure' in metin
        assert 'pressure ratio' in metin
        assert 'NaN' not in metin

    def test_asiri_genlesme_kapisi_hala_kendi_metnini_veriyor(self):
        """C_F sonluluk kapısı (over-expanded) kendi mesajını korur.

        Tıkanma kapısı yukarı akışta durduğu için bu kapıya ürün yolundan
        ulaşmak zorlaştı; bekçi kapıyı DOĞRUDAN çağırarak metnin ölmediğini
        kanıtlar (kapının sessizce ölmesi = kusuru koruyan bekçi).
        """
        ekran = {'expansion_ratio': 20.0, 'exit_pressure_bar': 0.02,
                 'ambient_pressure_bar': 3.0,
                 'separation_limit_expansion_ratio': 4.0}
        with pytest.raises(ValueError) as hata:
            HybridRocketEngine._gate_finite_cf(-0.5, ekran)
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
            pytest.approx(float(trapezoid(egri['thrust'], egri['time'])),
                          rel=1e-9))
