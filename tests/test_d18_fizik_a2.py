"""ÖH Dalga-18 · kulvar fizik · aşama a2 — bekçiler.

Kapsanan kalemler
=================
F2 ≡ **OH-D15-01** — sıvı model tabanları çelişiyordu: ``L_STAR_DEFAULT_M``
1,2 m ile ``CHAMBER_THROAT_DIAMETER_RATIO_DEFAULT`` 3,5 (ε_c = 12,25) aynı
anda sağlanamıyordu; konverjan koni tek başına L* = 12,088·d_t tuttuğu için
boğazı 99,3 mm'yi geçen her motorda taban L* ULAŞILAMAZ oluyordu.

F3 ≡ **OH-D15-06** + **P3B3-03** kalan yarısı — tank basıncı NPSH
gereksinimine göre boyutlandırılmıyordu (``PUMP_TANK_PRESSURE_DEFAULT_BAR``
= 3,0 bar sabiti), LOX pompasının NPSH_mevcut'u sistematik negatife
düşüyordu ve donanım uydurma 1000 Pa giriş yüküyle boyutlanıyordu.

Ölçüm dosyaları
===============
``docs/scofield/raw/OH/D18/fizik/a2/once_f2f3.json`` (taban e726048) ve
``sonra_f2f3.json`` (bu dal). Ters mutasyon: ``mutasyon.py`` / ``mutasyon.json``.

Literatür künyeleri
===================
* Huzel & Huang, NASA SP-125 (1971) Böl. IV Tablo 4-1 (L* çift tablosu),
  Tablo 1-3 (ε_c 1,3-6), Böl. VI eş. 6-8..6-11 (NPSH).
* NASA SP-8109 (1973) §3.2.1.2 — giriş hız-yükü kuralı k_v = 3,0 / 2,3 / 1,3.
* NASA SP-8107 (1974) Table II — uçuş motorlarının pompa giriş basınçları
  22-77 psia ve ölçülmüş NPSH_min/NPSH_crit = 1,1-1,6.
"""
import math

import pytest

from hrma.analysis.kinetic_efficiency import KineticEfficiency
from hrma.constants import G_0
from hrma.constants import L_STAR_DEFAULT_M as CONST_L_STAR
import hrma.engines.liquid_rocket_engine as L
from hrma.analysis.turbopump_sizing import (
    NPSH_MARGIN_FACTOR_DEFAULT, NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE,
    NPSH_STATIC_HEAD_DEFAULT_M,
    NPSH_VELOCITY_HEAD_FACTORS, npsh_required_velocity_head_m,
    tank_pressure_from_npsh_Pa)


# ---------------------------------------------------------------------------
# 1) BOYUT ANALİZİ — yeni bağıntıların SI temel-birim üsleri
# ---------------------------------------------------------------------------
class TestBoyutAnalizi:
    """Her yeni bağıntının SI boyutu elle cebirle sınanır (pint yok)."""

    def test_hiz_yuku_npsh_boyutu_uzunluk(self):
        """k_v·c_m²/(2g): (m/s)² / (m/s²) = m — saf uzunluk."""
        # Boyutları üs demetiyle temsil et: (m, kg, s)
        c_m = (1, 0, -1)            # m/s
        g = (1, 0, -2)              # m/s²
        pay = tuple(2 * u for u in c_m)                      # m²/s²
        sonuc = tuple(a - b for a, b in zip(pay, g))
        assert sonuc == (1, 0, 0), f'NPSH boyutu m olmalı, çıkan {sonuc}'
        # k_v boyutsuz olmalı
        for ad, k in NPSH_VELOCITY_HEAD_FACTORS.items():
            assert isinstance(k, float) and k > 0.0, ad

    def test_tank_basinci_bagintisi_basinc_boyutunda(self):
        """p_v + ρg(k·NPSH − z) + Δp: her terim Pa = kg/(m·s²)."""
        pa = (-1, 1, -2)
        rho = (-3, 1, 0)
        g = (1, 0, -2)
        uzunluk = (1, 0, 0)
        rho_g_h = tuple(a + b + c for a, b, c in zip(rho, g, uzunluk))
        assert rho_g_h == pa, f'ρgh basınç boyutunda olmalı, çıkan {rho_g_h}'

    def test_daralma_orani_kestirimi_boyutsuz(self):
        """ε_c = 8·D_t[cm]^-0,6 + 1,25 boyutsuzdur (katsayı birim taşır)."""
        eps, ham, _ = L.contraction_ratio_estimate(0.05)
        assert isinstance(eps, float) and isinstance(ham, float)
        # Alan oranı olduğu için d_c/d_t = sqrt(eps_c) özdeşliği tutmalı
        d_t = 0.05
        d_c = d_t * math.sqrt(eps)
        assert (d_c / d_t) ** 2 == pytest.approx(eps, rel=1e-12)

    def test_l_star_bantlari_metre_ve_sirali(self):
        """Tablo değerleri metre mertebesinde ve alt < üst."""
        for cift, (alt, ust) in L.L_STAR_BY_PAIR_M.items():
            assert 0.1 < alt < ust < 5.0, cift
        alt, ust = L.L_STAR_GENERIC_BAND_M
        assert 0.1 < alt < ust < 5.0

    def test_npsh_hiz_yuku_sayisal_ozdeslik(self):
        """Fonksiyon elle hesapla bit-yakın aynı sayıyı vermeli."""
        c_m, k_v = 7.5, 2.3
        beklenen = k_v * c_m * c_m / (2.0 * G_0)
        assert npsh_required_velocity_head_m(c_m, k_v) == pytest.approx(
            beklenen, rel=1e-15)

    def test_tank_basinci_tersi_npsh_i_geri_verir(self):
        """p_tank türetimi NPSH_a tanımıyla TERS işlemdir (kapanış sınaması).

        NPSH_a = (p_tank − Δp − p_v)/(ρg) olduğuna göre, p_tank'i
        k·NPSH_r'den kuran bağıntı geri konulduğunda NPSH_a = k·NPSH_r
        çıkmalıdır (z = 0'da).
        """
        rho, p_v, dp = 1141.0, 101325.0, 45000.0
        npsh_r = 3.7
        p_tank = tank_pressure_from_npsh_Pa(p_v, rho, npsh_r, dp,
                                            0.0, NPSH_MARGIN_FACTOR_DEFAULT)
        npsh_a = (p_tank - dp - p_v) / (rho * G_0)
        assert npsh_a == pytest.approx(NPSH_MARGIN_FACTOR_DEFAULT * npsh_r,
                                       rel=1e-12)


# ---------------------------------------------------------------------------
# 2) F2 — L* / daralma oranı
# ---------------------------------------------------------------------------
class TestF2LStarVeDaralmaOrani:
    """OH-D15-01: birbiriyle çelişen iki model tabanı."""

    def test_l_star_varsayilani_tek_kaynaktan(self):
        """1,2 ⟷ 1,0 çelişkisi bitti: iki modül AYNI sabiti okur.

        Ters mutasyon: ``kinetic_efficiency.DEFAULT_L_STAR_M = 1.0`` geri
        yazıldığında bu sınama KIRMIZI olur (mutasyon.json M1).
        """
        assert KineticEfficiency.DEFAULT_L_STAR_M == CONST_L_STAR
        assert L.L_STAR_DEFAULT_M == CONST_L_STAR

    def test_sabit_capa_orani_kaldirildi(self):
        """``CHAMBER_THROAT_DIAMETER_RATIO_DEFAULT`` artık YOK.

        Sabit 3,5 idi (ε_c = 12,25) ve Huzel & Huang Tablo 1-3 bandının
        (1,3-6) 2,04 katıydı. Adı hâlâ dursaydı ikinci bir tanım noktası
        olurdu — yerine bağıntı geçti.
        """
        assert not hasattr(L, 'CHAMBER_THROAT_DIAMETER_RATIO_DEFAULT')
        assert callable(L.contraction_ratio_estimate)

    @pytest.mark.parametrize('d_t_mm', [10.0, 30.0, 50.0, 100.0, 250.0,
                                        500.0, 900.0])
    def test_kestirim_HH_bandinda_kalir(self, d_t_mm):
        """Kestirim her boğaz çapında [1,3; 6] bandında kalır (kırpma)."""
        eps, _, _ = L.contraction_ratio_estimate(d_t_mm / 1000.0)
        alt, ust = L.CONTRACTION_RATIO_CORRELATION_BAND
        assert alt <= eps <= ust

    def test_kestirim_bogaz_capiyla_azalir(self):
        """Büyük boğaz daha küçük ε_c ister (D_t^-0,6 monoton azalan)."""
        degerler = [L.contraction_ratio_estimate(d)[1]
                    for d in (0.02, 0.05, 0.1, 0.3, 0.6, 1.0)]
        assert degerler == sorted(degerler, reverse=True)

    def test_koni_tek_basina_taban_l_stari_yutmuyor(self):
        """Onarımın ÇEKİRDEK sınaması: L*_koni < L*_taban her boğazda.

        Eski sabit oranla (3,5) koni tek başına L* = 12,088·d_t tutuyordu;
        d_t > 99,3 mm'de 1,2 m taban ulaşılamazdı. Kestirim bandıyla
        katsayı çok daha küçük olmalı.

        Ters mutasyon: ``_chamber_diameter`` içindeki
        ``d_t*sqrt(eps_c)`` yerine ``d_t*3.5`` geri yazıldığında bu
        sınamanın motor tarafı (aşağıdaki uçtan uca sınama) KIRMIZI olur.
        """
        yari = math.radians(L.CONVERGENT_HALF_ANGLE_DEG)
        for d_t in (0.02, 0.05, 0.1, 0.25, 0.5, 0.9):
            eps, _, _ = L.contraction_ratio_estimate(d_t)
            d_c = d_t * math.sqrt(eps)
            l_conv = (d_c - d_t) / (2.0 * math.tan(yari))
            r_c, r_t = d_c / 2.0, d_t / 2.0
            v_kon = (math.pi * l_conv / 3.0
                     * (r_c * r_c + r_c * r_t + r_t * r_t))
            a_t = math.pi * d_t ** 2 / 4.0
            l_star_koni = v_kon / a_t
            # SP-125 Tablo 4-1'in EN KISA satırı 0,56 m; koni onun bile
            # altında kalmalı ki hiçbir çiftte taban ulaşılamaz olmasın.
            assert l_star_koni < 0.56, (
                f'd_t={d_t*1000:.0f} mm: koni tek başına '
                f'L*={l_star_koni:.3f} m tutuyor')

    def test_l_star_tablosu_itici_ciftine_anahtarli(self):
        """SP-125 Tablo 4-1 satırları: bilinen çiftler ve genel yedek."""
        assert L.l_star_band_for_pair('rp1', 'lox') == (
            1.02, 1.27, 'sp125_table_4_1_pair')
        assert L.l_star_band_for_pair('lh2', 'lox') == (
            0.76, 1.02, 'sp125_table_4_1_pair')
        assert L.l_star_band_for_pair('mmh', 'n2o4') == (
            0.76, 0.89, 'sp125_table_4_1_pair')
        # Tabloda OLMAYAN çift: genel aralık + 'generic' etiketi
        alt, ust, kaynak = L.l_star_band_for_pair('methane', 'lox')
        assert kaynak == 'sp125_table_4_1_generic'
        assert (alt, ust) == L.L_STAR_GENERIC_BAND_M

    def test_korelasyon_kunyesi_kaynagin_belirsizligini_soyluyor(self):
        """ε_c bağıntısının birincil kaynağı doğrulanamadı — künye der ki."""
        metin = L.CONTRACTION_RATIO_CORRELATION_BASIS.lower()
        assert 'empirical' in metin
        assert 'primary source' in metin and 'unverified' in metin
        assert '1.3' in L.CONTRACTION_RATIO_CORRELATION_BASIS


# ---------------------------------------------------------------------------
# 3) F3 — NPSH / tank basıncı (saf yardımcılar)
# ---------------------------------------------------------------------------
class TestF3NPSHYardimcilari:

    def test_hiz_yuku_carpanlari_SP8109(self):
        """k_v: depolanabilir 3,0 · kriyojenik oksitleyici 2,3 · LH2 1,3."""
        assert NPSH_VELOCITY_HEAD_FACTORS['storable'] == 3.0
        assert NPSH_VELOCITY_HEAD_FACTORS['cryogenic_ox'] == 2.3
        assert NPSH_VELOCITY_HEAD_FACTORS['hydrogen'] == 1.3

    def test_marj_katsayisi_SP8107_bandinda(self):
        """k = 1,25, SP-8107 Table II'nin 1,1-1,6 bandının içi."""
        assert 1.1 <= NPSH_MARGIN_FACTOR_DEFAULT <= 1.6

    def test_statik_yuk_sifir_ve_beyanli(self):
        """z modellenmiyor; 0 KÖTÜMSER yöndür (pozitif z basıncı düşürürdü)."""
        assert NPSH_STATIC_HEAD_DEFAULT_M == 0.0
        rho, p_v, npsh_r = 1141.0, 101325.0, 3.0
        p0 = tank_pressure_from_npsh_Pa(p_v, rho, npsh_r, 0.0, 0.0)
        p1 = tank_pressure_from_npsh_Pa(p_v, rho, npsh_r, 0.0, 2.0)
        assert p1 < p0

    def test_itici_sinifi_addan_degil_depolama_sinifindan(self):
        E = L.LiquidRocketEngine
        assert E._npsh_velocity_head_factor('lox')[0] == 2.3
        assert E._npsh_velocity_head_factor('lh2')[0] == 1.3
        assert E._npsh_velocity_head_factor('rp1')[0] == 3.0
        assert E._npsh_velocity_head_factor('n2o4')[0] == 3.0
        assert E._npsh_velocity_head_factor(None)[0] == 3.0

    def test_gecersiz_girdi_sessiz_sayi_uretmez(self):
        with pytest.raises(ValueError):
            npsh_required_velocity_head_m(-1.0, 3.0)
        with pytest.raises(ValueError):
            npsh_required_velocity_head_m(5.0, 0.0)
        with pytest.raises(ValueError):
            tank_pressure_from_npsh_Pa(1e5, 0.0, 3.0)
        with pytest.raises(ValueError):
            tank_pressure_from_npsh_Pa(1e5, 1000.0, -1.0)


# ---------------------------------------------------------------------------
# 4) UÇTAN UCA — /calculate_liquid
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _kos(client, **ek):
    yuk = {'motor_name': 'D18-A2', 'thrust': 500000.0, 'burn_time': 150.0,
           'chamber_pressure': 70.0, 'mixture_ratio': 2.3,
           'fuel_type': 'rp1', 'oxidizer_type': 'lox',
           'expansion_ratio': 20.0}
    yuk.update(ek)
    r = client.post('/calculate_liquid', json=yuk)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    j = r.get_json()
    return j.get('results', j)


class TestUctanUcaF2:

    @pytest.mark.parametrize('thrust,pc,yakit,oks,ratio', [
        (5000.0, 30.0, 'rp1', 'lox', 2.2),
        (100000.0, 60.0, 'rp1', 'lox', 2.4),
        (500000.0, 70.0, 'rp1', 'lox', 2.3),
        (947000.0, 48.0, 'rp1', 'lox', 2.23),
        (100000.0, 50.0, 'lh2', 'lox', 5.5),
        (50000.0, 40.0, 'mmh', 'n2o4', 2.0),
    ])
    def test_daralma_orani_HH_bandinda(self, client, thrust, pc, yakit,
                                       oks, ratio):
        """ÖLÇÜLDÜ: taban ağacında altı koşumun ALTISI da ε_c = 12,25 idi.

        Ters mutasyon (M2): ``_chamber_diameter`` türev dalında
        ``d_t * np.sqrt(eps_c)`` yerine ``d_t * 3.5`` geri yazılırsa bu
        sınama KIRMIZI olur.
        """
        res = _kos(client, thrust=thrust, chamber_pressure=pc,
                   fuel_type=yakit, oxidizer_type=oks, mixture_ratio=ratio)
        cr = res['cooling_system']['contraction_ratio']
        alt, ust = L.CONTRACTION_RATIO_CORRELATION_BAND
        assert alt <= cr <= ust, f'ε_c = {cr:.3f} bandın dışında'

    @pytest.mark.parametrize('thrust,pc,yakit,oks,ratio,band', [
        (5000.0, 30.0, 'rp1', 'lox', 2.2, (1.02, 1.27)),
        (500000.0, 70.0, 'rp1', 'lox', 2.3, (1.02, 1.27)),
        (6770000.0, 70.0, 'rp1', 'lox', 2.27, (1.02, 1.27)),
        (100000.0, 50.0, 'lh2', 'lox', 5.5, (0.76, 1.02)),
        (50000.0, 40.0, 'mmh', 'n2o4', 2.0, (0.76, 0.89)),
    ])
    def test_yayimlanan_l_star_cift_bandinda(self, client, thrust, pc, yakit,
                                             oks, ratio, band):
        """Yayımlanan L* çiftin SP-125 bandında VE istenen değere eşit.

        ÖLÇÜLDÜ (taban): istenen 1,2 m iken yayımlanan 2,47 / 2,63 / 2,79 /
        4,15 / 6,19 / 12,05 m çıkıyordu — 'l_star_unreachable' kaçış yolu.
        Ters mutasyon (M2) bu sınamayı da kırmızıya çevirir.
        """
        res = _kos(client, thrust=thrust, chamber_pressure=pc,
                   fuel_type=yakit, oxidizer_type=oks, mixture_ratio=ratio)
        cool = res['cooling_system']
        alt, ust = band
        assert alt <= cool['l_star'] <= ust, cool['l_star']
        assert cool['l_star'] == pytest.approx(cool['l_star_requested'],
                                               rel=1e-9)
        assert list(cool['l_star_band_m']) == [alt, ust]
        assert cool['l_star_band_source'] == 'sp125_table_4_1_pair'

    def test_hazne_narinligi_yayimlanir_ve_bantta(self, client):
        """L_c/D_c yayımlanır; taban ağacında 0,115 (gözleme) idi."""
        res = _kos(client)
        cool = res['cooling_system']
        oran = cool['chamber_length_diameter_ratio']
        alt, ust = L.CHAMBER_LENGTH_DIAMETER_BAND
        assert cool['chamber_length_diameter_status'] == 'in_band'
        assert alt <= oran <= ust, oran
        # yayımlanan oran ÇİZİLEN geometriyle tutarlı olmalı
        assert oran == pytest.approx(
            cool['chamber_length'] / cool['chamber_diameter'], rel=1e-9)

    def test_kullanici_daralma_orani_kestirimi_ezer(self, client):
        """Kullanıcı hükmü kazanır ve künye bunu söyler (fail-open değil)."""
        res = _kos(client, contraction_ratio=2.0)
        cool = res['cooling_system']
        assert cool['contraction_ratio'] == pytest.approx(2.0, rel=1e-6)
        assert 'user input' in cool['contraction_ratio_source']

    def test_kullanici_l_stari_kazanir(self, client):
        res = _kos(client, characteristic_length=1.6)
        cool = res['cooling_system']
        assert cool['l_star_requested'] == pytest.approx(1.6, rel=1e-9)
        assert 'user input' in cool['l_star_source']


class TestUctanUcaF3:

    def test_tank_basinci_motora_gore_degisir(self, client):
        """ÖLÇÜLDÜ (taban): yedi koşumun YEDİSİ de 3,0 bar idi.

        Ters mutasyon (M3): ``_tank_pressure_bar`` turbopompa dalı sabite
        geri döndürülürse bu sınama KIRMIZI olur.
        """
        basinclar = []
        for thrust, pc in ((5000.0, 30.0), (100000.0, 60.0),
                           (500000.0, 70.0)):
            res = _kos(client, thrust=thrust, chamber_pressure=pc)
            basinclar.append(res['detailed_feed_system']['tank_pressure_bar'])
        assert len(set(round(b, 6) for b in basinclar)) == 3, basinclar
        assert all(b != L.PUMP_TANK_PRESSURE_DEFAULT_BAR for b in basinclar)

    def test_tank_basinci_npsh_gereksiniminden_turetilir(self, client):
        """Defter: hangi pompa yönetti, hangi k_v, hangi NPSH, hangi marj.

        ÖH D21 · OH-D20-09 ÇEVİRİSİ — ÇİFT MARJ. Bu satır
        ``margin_factor == NPSH_MARGIN_FACTOR_DEFAULT`` (1,25) istiyordu ve
        böylece ÇİFT MARJI kilitliyordu: SP-8109 §3.2.1.2'nin giriş
        hız-yükü kuralı ZATEN marjlı bir kabul tabanıdır (k_v = 3,0 / 2,3 /
        1,3 çarpanının kendisi imalat-ölçüm payıdır), SP-8107 Table II'nin
        NPSH_min/NPSH_kritik oranı ise AYNI payı ikinci kez uygular.
        ÖLÇÜLDÜ (docs/scofield/raw/OH/D21/sivi/a1/once.json OH-D20-09;
        LOX, c_m = 12 m/s, k_v = 2,3): kural tabanı 16,88650 m iken ürün
        "gerekli NPSH" diye 21,10813 m yayımlıyor, gereken tank basıncı
        2,88950 yerine 3,36187 bar (+%16,3) çıkıyordu.

        Tek marj sözleşmesi ``NPSH_SINGLE_MARGIN_CONTRACT``ta yazılıdır;
        katsayı ``NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE = 1,0``.
        ``NPSH_MARGIN_FACTOR_DEFAULT`` KALDIRILMADI: emme özgül hızı
        tersinden gelen (NPSH_kritik tabanlı) gereksinimlerde geçerlidir
        ve modül sınamaları onu sınamayı sürdürür.
        Bekçisi: tests/test_d21_sivi_a1.py ``TestOHD2009TekMarj``.
        """
        res = _kos(client)
        blok = res['detailed_feed_system']['npsh_tank_sizing']
        assert blok['status'] == 'sized'
        assert blok['margin_factor'] == (
            NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE)
        assert blok['governing_pump'] in ('oxidizer_pump', 'fuel_pump')
        # yöneten pompa GERÇEKTEN en yüksek basıncı isteyen olmalı
        istekler = {ad: v['required_tank_pressure_bar']
                    for ad, v in blok['per_pump'].items()}
        assert blok['governing_pump'] == max(istekler, key=istekler.get)
        assert blok['bar'] == pytest.approx(max(istekler.values()), rel=1e-12)
        # LOX kriyojenik oksitleyici sınıfında olmalı
        assert blok['per_pump']['oxidizer_pump'][
            'velocity_head_factor'] == 2.3
        assert blok['per_pump']['fuel_pump']['velocity_head_factor'] == 3.0

    def test_500kN_lox_pompasi_artik_gerceklenebilir(self, client):
        """P3B3-03'ün ÇEKİRDEĞİ: NPSH_a −2,354 m → pozitif, çark yayımlanır.

        Taban ağacında (e726048) 500 kN LOX/RP-1 koşumunda LOX pompası
        ``npsh_available = -2,354 m``, ``status = 'not_feasible'``,
        ``impeller_diameter = None`` idi ve donanım nominal 1000 Pa giriş
        yüküyle boyutlanıyordu.
        """
        res = _kos(client)
        pompa = res['detailed_feed_system']['turbopump_analysis'][
            'oxidizer_pump']
        assert pompa['npsh_available'] > 0.0
        assert pompa['suction_feasible'] is True
        assert pompa['hardware_feasible'] is True
        assert pompa['status'] == 'modelled'
        assert pompa['impeller_diameter'] is not None
        assert pompa['impeller_geometry_status'] == 'modelled'

    def test_hiz_yuku_kurali_canli_sinama(self, client):
        """SP-8109 §3.2.1.2 sınaması yayımlanır ve tutar.

        ÖH D21 · OH-D20-09 ÇEVİRİSİ: hüküm artık kuralın KENDİ tabanına
        karşı verilir (tek marj sözleşmesi; yukarıdaki gerekçe).
        """
        res = _kos(client)
        tp = res['detailed_feed_system']['turbopump_analysis']
        for ad in ('oxidizer_pump', 'fuel_pump'):
            p = tp[ad]
            assert p['npsh_velocity_head_status'] == 'met'
            gerekli = (NPSH_MARGIN_FACTOR_VELOCITY_HEAD_RULE
                       * p['npsh_required_velocity_head_m'])
            assert p['npsh_available'] >= gerekli * (1.0 - 1e-6)
            # yayımlanan gereksinim yayımlanan hızla tutarlı olmalı
            beklenen = npsh_required_velocity_head_m(
                p['npsh_inlet_velocity_m_s'], p['npsh_velocity_head_factor'])
            assert p['npsh_required_velocity_head_m'] == pytest.approx(
                beklenen, rel=1e-9)

    def test_devir_tabanli_marj_olu_sensor_oldugu_beyan_edilir(self, client):
        """Marj oranı tasarım gereği derate^(-4/3): künye bunu söylemeli."""
        res = _kos(client)
        p = res['detailed_feed_system']['turbopump_analysis'][
            'oxidizer_pump']
        oran = p['npsh_available'] / p['npsh_required']
        beklenen = L.SPEED_DERATE_DEFAULT ** (-4.0 / 3.0)
        assert oran == pytest.approx(beklenen, rel=1e-4)
        assert 'velocity-head' in p['npsh_velocity_head_basis'].lower() \
            or 'velocity head' in p['npsh_velocity_head_basis'].lower()

    def test_F1_sinifi_artik_400_dondurmuyor(self, client):
        """Yan bulgu: float(None) çarpması bütün isteği 400'e düşürüyordu."""
        res = _kos(client, thrust=6770000.0, chamber_pressure=70.0,
                   mixture_ratio=2.27, expansion_ratio=16.0)
        assert res['detailed_feed_system']['tank_pressure_bar'] > 0.0

    def test_H1_sinifi_SP8107_bandinda(self, client):
        """Literatür çapası: H-1 sınıfı tank basıncı Table II bandında."""
        res = _kos(client, thrust=947000.0, chamber_pressure=48.0,
                   mixture_ratio=2.23, expansion_ratio=8.0)
        blok = res['detailed_feed_system']['npsh_tank_sizing']
        assert blok['sp8107_band_status'] == 'in_band'
        alt, ust = L.SP8107_INLET_PRESSURE_BAND_BAR
        assert alt <= blok['bar'] <= ust

    def test_kunye_sabit_metni_degil_karari_tasir(self, client):
        """tank_pressure_source artık 'PUMP_TANK_PRESSURE_DEFAULT_BAR' demiyor."""
        res = _kos(client)
        dfs = res['detailed_feed_system']
        kunye = dfs['tank_pressure_source']
        assert 'NPSH requirement' in kunye
        assert 'PUMP_TANK_PRESSURE_DEFAULT_BAR' not in kunye
        pompa = dfs['turbopump_analysis']['oxidizer_pump']
        assert pompa['tank_pressure_source'] == kunye


class TestF3FailClosedVeNoneKorumasi:
    """NPSH_a > 0 ama SP-8109 gereksinimi KARŞILANMIYOR: fail-closed yol.

    Bu durum türetilmiş tank basıncında doğmaz (basınç zaten gereksinimden
    kurulur), o yüzden tank basıncı ELLE düşürülerek üretilir: 500 kN
    LOX/RP-1'de 3,5 bar, NPSH_a'yı pozitif (~2,1 m) ama gereksinimin
    (~5,48 m) altında bırakır.
    """

    @staticmethod
    def _motor(monkeypatch, tank_bar):
        E = L.LiquidRocketEngine
        monkeypatch.setattr(
            E, '_tank_pressure_bar',
            lambda self: (tank_bar, 'test fixture: forced tank pressure'))
        e = E(thrust=500000.0, chamber_pressure=70.0, mixture_ratio=2.3,
              fuel_type='rp1', oxidizer_type='lox',
              overrides={'expansion_ratio': 20.0, 'burn_time': 150.0})
        return e.calculate_performance()

    def test_dusuk_tank_basincinda_donanim_yayimlanmaz(self, monkeypatch):
        """Ters mutasyon (M5): None koruması kalkarsa TypeError -> istek 400.

        Ayrıca fail-closed hüküm: çark çapı YAYIMLANMAZ, 'not_feasible'
        durumu ve gerekçesi yayımlanır (sayı uydurulmaz).
        """
        res = self._motor(monkeypatch, 3.5)
        tp = res['detailed_feed_system']['turbopump_analysis']
        ox = tp['oxidizer_pump']
        assert ox['npsh_available'] > 0.0, 'kurgu bozuldu: NPSH_a pozitif olmalı'
        assert ox['npsh_velocity_head_status'] == 'not_met'
        assert ox['suction_feasible'] is True
        assert ox['hardware_feasible'] is False
        assert ox['status'] == 'not_feasible'
        assert ox['impeller_diameter'] is None
        assert ox['impeller_geometry_status'] == 'not_computed'
        # Kaybolmuyor: hız tabanının ima ettiği geometri AYRI adla duruyor
        assert ox['impeller_diameter_if_inlet_head_floor'] is not None
        # C1 modül bloğu da çökmeden üretilmiş olmalı (M5'in gördüğü yol)
        ts = res['detailed_feed_system']['turbopump_sizing']
        assert isinstance(ts, dict) and ts
        blok = ts.get('oxidizer_pump') or {}
        assert blok.get('impeller_diameter_euler_stodola_m') is None
        assert blok.get('impeller_diameter_ratio') is None

    def test_gerekcesi_SP8109_kuralini_adiyla_soyluyor(self, monkeypatch):
        res = self._motor(monkeypatch, 3.5)
        ox = res['detailed_feed_system']['turbopump_analysis'][
            'oxidizer_pump']
        assert 'SP-8109' in ox['status_basis']
        assert 'velocity-head' in ox['status_basis'] \
            or 'velocity head' in ox['status_basis']
