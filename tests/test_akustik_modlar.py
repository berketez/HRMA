"""Yanma odası akustik mod modülü (acoustic_modes) doğrulama testleri.

Bekçi çapaları:

(a) Boyuna mod analitik round-trip: f_qL = q*a/(2L) — a=1000 m/s, L=0.5 m
    için 1L = 1000 Hz (tam); frekanstan L geri kurtarılır.
(b) Bessel türev kökleri literatürle: 1T alpha_11 = 1.8412 (NASA SP-194;
    Abramowitz & Stegun, "Handbook of Mathematical Functions", Tablo 9.5),
    ayrıca 2T = 3.0542, 1R = 3.8317, 2R = 7.0156, 1T1R = 5.3314.
(c) Boyut analizi / ölçekleme yasaları: a ~ sqrt(T) -> tüm frekanslar
    sqrt(T) ile; L iki katına -> boyuna frekans yarıya, enine değişmez;
    D iki katına -> enine frekans yarıya, boyuna değişmez; karma mod
    f = sqrt(f_T^2 + f_L^2).
(d) F-1 sınıfı büyük kamara mertebe kontrolü: Oefelein & Yang,
    "Comprehensive Review of Liquid-Propellant Combustion Instabilities in
    F-1 Engines", J. Propulsion and Power 9(5), 1993, s. 657-677 —
    kamara yüz çapı 100 cm; gözlenen 1T "spinning" kararsızlığı 440-540 Hz
    (5U-flatface ~540 Hz, 5U-baffled ~440 Hz, double-row cluster ~450 Hz).
    Düzgün-sıcak-gaz rijit silindir kestirimi ölçüm bandının biraz ÜSTÜNDE
    çıkar (enjektör yüzü yakınındaki gaz daha soğuk); bu yüzden birebir
    eşitlik DEĞİL, yayımlanmış bandın x2 mertebesi içinde kalma test edilir.
"""

import math
import re

import pytest

from hrma.analysis.acoustic_modes import (
    AcousticModeAnalyzer,
    sound_speed,
    longitudinal_frequency,
    transverse_root,
    transverse_frequency,
    combined_frequency,
    analyze_from_engine_result,
    CHUG_DP_RATIO_RECOMMENDED,
    CHUG_DP_RATIO_MINIMUM,
    FREQ_BAND_CHUG_MAX_HZ,
    FREQ_BAND_BUZZ_MAX_HZ,
    NOT_MODELLED,
    R_UNIVERSAL_J_KMOL_K,
)


#: YAYIMLANMIŞ chug tasarım bandı (dP_inj / P_c). Kaynak: Sutton & Biblarz,
#: "Rocket Propulsion Elements", 9. baskı, Böl. 8 (enjektör tasarımı) —
#: enjektör basınç düşümü klasik olarak oda basıncının %15-25'i seçilir.
#: BURADA yazılıdır; ürünün sabitlerinden TÜRETİLMEZ (defter P4B4-16'nın
#: kusuru zaten "ürün kendi bandını aşan tasarıma temiz OK veriyor"dur,
#: dolayısıyla eşik üründen okunursa bekçi kusuru göremez).
CHUG_BANDI_YAYIMLANMIS = (0.15, 0.25)


def _analyze(**overrides):
    """Tipik hibrit kamara girdileriyle tam analiz (testlerde ortak)."""
    args = dict(chamber_temperature=3000.0, gamma=1.2, gas_constant=360.0,
                chamber_diameter=0.10, chamber_length=0.40, n_modes=10)
    args.update(overrides)
    return AcousticModeAnalyzer().analyze(**args)


def _mode(result, label):
    for m in result['modes']:
        if m['label'] == label:
            return m
    raise AssertionError(
        f"mode {label!r} not in table: "
        f"{[m['label'] for m in result['modes']]}")


# ===========================================================================
# Ses hızı
# ===========================================================================
class TestSoundSpeed:
    def test_hand_calc(self):
        """a = sqrt(gamma*R*T): sqrt(1.2*360*3000) = sqrt(1.296e6) (tam)."""
        assert sound_speed(1.2, 360.0, 3000.0) == pytest.approx(
            math.sqrt(1.2 * 360.0 * 3000.0), rel=1e-12)

    def test_rejects_invalid(self):
        """gamma <= 1, R <= 0, T <= 0 ve NaN reddedilir."""
        for bad in ((1.0, 360.0, 3000.0),    # gamma tam 1 -> geçersiz
                    (0.9, 360.0, 3000.0),
                    (1.2, 0.0, 3000.0),
                    (1.2, 360.0, 0.0),
                    (1.2, 360.0, -5.0),
                    (float('nan'), 360.0, 3000.0)):
            with pytest.raises(ValueError):
                sound_speed(*bad)


# ===========================================================================
# (a) Boyuna mod analitik round-trip
# ===========================================================================
class TestLongitudinalRoundTrip:
    def test_exact_hand_calc(self):
        """a=1000, L=0.5 -> 1L=1000 Hz, 2L=2000 Hz, 3L=3000 Hz (tam)."""
        for q in (1, 2, 3):
            assert longitudinal_frequency(1000.0, 0.5, q) == pytest.approx(
                q * 1000.0, rel=1e-12)

    def test_round_trip_recovers_length(self):
        """f = q*a/(2L) -> L = q*a/(2f) round-trip (her q için tam)."""
        a, L = 1180.7, 0.437
        for q in (1, 2, 5):
            f = longitudinal_frequency(a, L, q)
            assert q * a / (2.0 * f) == pytest.approx(L, rel=1e-12)

    def test_rejects_invalid(self):
        with pytest.raises(ValueError):
            longitudinal_frequency(1000.0, 0.5, 0)      # q >= 1
        with pytest.raises(ValueError):
            longitudinal_frequency(1000.0, -0.5, 1)
        with pytest.raises(ValueError):
            longitudinal_frequency(0.0, 0.5, 1)


# ===========================================================================
# (b) Bessel türev kökleri literatür çapaları
# ===========================================================================
class TestBesselRoots:
    """NASA SP-194 / Abramowitz & Stegun Tablo 9.5 değerleri."""

    def test_1t_root_is_1_8412(self):
        """1T: J'_1'in ilk kökü alpha_11 = 1.8412 (literatür)."""
        assert transverse_root(1, 0) == pytest.approx(1.8412, abs=5e-4)

    def test_other_literature_roots(self):
        """2T=3.0542, 3T=4.2012, 1R=3.8317, 2R=7.0156, 1T1R=5.3314."""
        assert transverse_root(2, 0) == pytest.approx(3.0542, abs=5e-4)
        assert transverse_root(3, 0) == pytest.approx(4.2012, abs=5e-4)
        assert transverse_root(0, 1) == pytest.approx(3.8317, abs=5e-4)
        assert transverse_root(0, 2) == pytest.approx(7.0156, abs=5e-4)
        assert transverse_root(1, 1) == pytest.approx(5.3314, abs=5e-4)

    def test_dc_mode_rejected(self):
        """(m, n) = (0, 0) enine bileşen değildir -> ValueError."""
        with pytest.raises(ValueError):
            transverse_root(0, 0)
        with pytest.raises(ValueError):
            transverse_root(-1, 0)

    def test_transverse_frequency_formula(self):
        """f = a*alpha/(pi*D) birim tutarlılığı (tam el hesabı)."""
        assert transverse_frequency(1000.0, 0.5, 1.8412) == pytest.approx(
            1000.0 * 1.8412 / (math.pi * 0.5), rel=1e-12)


# ===========================================================================
# (c) Boyut analizi / ölçekleme yasaları
# ===========================================================================
class TestScalingLaws:
    def test_temperature_scaling_sqrt(self):
        """T -> 4T: a ve TÜM mod frekansları tam 2 katına çıkar."""
        base = _analyze(chamber_temperature=3000.0)
        hot = _analyze(chamber_temperature=12000.0)
        assert hot['sound_speed_m_s'] == pytest.approx(
            2.0 * base['sound_speed_m_s'], rel=1e-12)
        base_f = {m['label']: m['frequency_hz'] for m in base['modes']}
        hot_f = {m['label']: m['frequency_hz'] for m in hot['modes']}
        assert set(base_f) == set(hot_f)  # sıralama değişmez (tekdüze ölçek)
        for label, f in base_f.items():
            assert hot_f[label] == pytest.approx(2.0 * f, rel=1e-12)

    def test_length_scaling_only_longitudinal(self):
        """L -> 2L: boyuna frekans yarıya iner, enine değişmez."""
        base = _analyze()
        stretched = _analyze(chamber_length=0.80)
        assert _mode(stretched, '1L')['frequency_hz'] == pytest.approx(
            _mode(base, '1L')['frequency_hz'] / 2.0, rel=1e-12)
        assert _mode(stretched, '1T')['frequency_hz'] == pytest.approx(
            _mode(base, '1T')['frequency_hz'], rel=1e-12)

    def test_diameter_scaling_only_transverse(self):
        """D -> 2D: enine frekans yarıya iner, boyuna değişmez."""
        base = _analyze()
        widened = _analyze(chamber_diameter=0.20)
        assert _mode(widened, '1T')['frequency_hz'] == pytest.approx(
            _mode(base, '1T')['frequency_hz'] / 2.0, rel=1e-12)
        assert _mode(widened, '1L')['frequency_hz'] == pytest.approx(
            _mode(base, '1L')['frequency_hz'], rel=1e-12)

    def test_combined_mode_pythagoras(self):
        """1T1L = sqrt(1T^2 + 1L^2) — dik bileşenlerin kareleri toplamı."""
        res = _analyze(n_modes=59)  # tüm havuz -> 1T1L kesin tabloda
        f_1t = _mode(res, '1T')['frequency_hz']
        f_1l = _mode(res, '1L')['frequency_hz']
        f_1t1l = _mode(res, '1T1L')['frequency_hz']
        assert f_1t1l == pytest.approx(math.hypot(f_1t, f_1l), rel=1e-12)
        # Saf fonksiyon da aynı sonucu vermeli
        assert combined_frequency(f_1t, f_1l) == pytest.approx(
            f_1t1l, rel=1e-12)


# ===========================================================================
# (d) F-1 sınıfı büyük kamara mertebe kontrolü
# ===========================================================================
class TestF1ClassChamber:
    """Oefelein & Yang (1993), J. Propulsion and Power 9(5), 657-677.

    Makale: F-1 kamara yüz çapı ("wall-to-wall face diameter") 100 cm;
    gözlenen baskın kararsızlık 1T "spinning" modu, enjektöre göre
    440-540 Hz bandında. Rijit silindir + düzgün sıcak gaz kestirimi
    (LOX/RP-1 denge kamara gazı: T_c ~3570 K, gamma ~1.22, MW ~23.3 g/mol)
    ölçümden YÜKSEK çıkar; bu bilinen model sınırıdır (not_modelled.
    mean_flow_and_gradients). Test birebir eşitlik değil, yayımlanmış
    bandın x2 mertebesi içinde kalmayı doğrular (hardcode kıyas değeri
    banttır, model çıktısı değildir).
    """

    F1_OBSERVED_1T_BAND_HZ = (440.0, 540.0)  # Oefelein & Yang 1993

    #: MODELİN BANDA GÖRE ÖLÇÜLEN SAPMASI (27 Ağustos 2026, bu depo):
    #: 1T = 730,63 Hz, yayımlanmış bandın ortası 490 Hz -> 1,4911 kat.
    #: Bu bir BORÇ ÇAPASIDIR (ÖH defter P13B3-02): modülün TEK gerçek
    #: deney yüzleşmesi budur ve sapma %49'dur. Eski bekçi ±2 kat pencere
    #: kullanıyordu (220-1080 Hz), yani ürün bugünkü hâlinden %47,8 DAHA
    #: bozulsa bile yeşil kalıyordu. Pencere ölçülmüş sapmaya çapalandı:
    #: model değişirse burası kırmızı olur ve sapmanın yeni değerinin
    #: deftere yazılmasını zorlar (eşik üründen türetilmez, dondurulur).
    F1_1T_OLCULEN_HZ = 730.63
    F1_1T_SAPMA_OLCULEN = 1.4911          # ölçülen / band ortası

    def test_1t_frequency_same_order_as_published(self):
        gas_constant = R_UNIVERSAL_J_KMOL_K / 23.3  # LOX/RP-1 ~23.3 g/mol
        res = AcousticModeAnalyzer().analyze(
            chamber_temperature=3570.0, gamma=1.22,
            gas_constant=gas_constant,
            chamber_diameter=1.00,   # F-1 yüz çapı 100 cm (makale)
            chamber_length=1.00, n_modes=20)
        f_1t = _mode(res, '1T')['frequency_hz']
        lo, hi = self.F1_OBSERVED_1T_BAND_HZ
        # (1) Bilinen model yanlılığının YÖNÜ: düzgün-sıcak-gaz kestirimi
        #     ölçümün ALTINA inmemeli (enjektör yüzü gazı daha soğuk).
        assert f_1t >= lo, (
            f"1T = {f_1t:.1f} Hz, yayımlanmış bandın ({lo:.0f}-{hi:.0f} Hz) "
            "altına indi — modelin bilinen yanlılığı ters döndü")
        # (2) Sapmanın KENDİSİ ölçülmüş bir sayıdır ve dondurulmuştur.
        orta = 0.5 * (lo + hi)
        sapma = f_1t / orta
        assert f_1t == pytest.approx(self.F1_1T_OLCULEN_HZ, rel=2e-3), (
            f"1T = {f_1t:.2f} Hz; ölçülmüş çapa "
            f"{self.F1_1T_OLCULEN_HZ:.2f} Hz. Model değiştiyse yeni sapma "
            f"({sapma:.4f} kat) deftere yazılıp çapa güncellenmeli "
            '(ÖH defter P13B3-02)')
        assert sapma == pytest.approx(self.F1_1T_SAPMA_OLCULEN, rel=2e-3), (
            f'yayımlanmış banda göre sapma {sapma:.4f} kat (çapa '
            f'{self.F1_1T_SAPMA_OLCULEN:.4f}) — bu, modülün tek gerçek '
            'deney yüzleşmesindeki BORCUN sayısıdır')

    def test_1t_is_sub_khz_for_f1_scale(self):
        """F-1 ölçeğinde 1T, screech bandı sınırı ~1 kHz'in ALTINDA kalır —
        'büyük motorlarda akustik modlar 1 kHz altına iner' iddiasının
        sayısal doğrulaması (band sınıflandırması gösterge niteliğinde)."""
        gas_constant = R_UNIVERSAL_J_KMOL_K / 23.3
        res = AcousticModeAnalyzer().analyze(
            chamber_temperature=3570.0, gamma=1.22,
            gas_constant=gas_constant,
            chamber_diameter=1.00, chamber_length=1.00, n_modes=20)
        assert _mode(res, '1T')['frequency_hz'] < FREQ_BAND_BUZZ_MAX_HZ


# ===========================================================================
# Mod tablosu sözleşmesi
# ===========================================================================
#: KATI MOTOR ORANTISI (uzun/ince kavite) — bekçilerin bugüne kadar HİÇ
#: koşturmadığı geometri (defter P4B4-14 notu: "bekçiler L/D≈4 kamarayla
#: koşuyor, katı motor proporsiyonunu koşturan yok"). D=0.20 m, L=2.5 m,
#: T=2000 K, gamma=1.2, R=300 J/(kg·K) -> a = 848,53 m/s.
KATI_MOTOR_KAVITESI = dict(chamber_temperature=2000.0, gamma=1.2,
                           gas_constant=300.0, chamber_diameter=0.20,
                           chamber_length=2.5)


def _eksik_boyuna_modlar(res, a, L):
    """Tablonun KENDİ en yüksek frekansının altında kalan ama tabloda
    BULUNMAYAN gerçek boyuna modlar.

    Boyuna mod dizisi f_qL = q*a/(2L) ile kapalı formdur (testin içinde
    kurulur, üründen türetilmez).

    ÖH D26 / P4B4-14 — ÖLÇÜM TABANI DEĞİŞTİ (bilerek, gerekçeli): eski
    sürüm ``ust_indeks`` alıp "q > ust_indeks olan her mod eksiktir" diye
    VARSAYIYORDU. Bu varsayım yalnız havuz SABİT tavanla kırpılırken
    doğruydu; havuz kesim frekansına göre büyütülünce aynı satır, tabloda
    FİİLEN BULUNAN modları "eksik" ilan etmeye başlıyordu — yani bekçi
    kusuru değil, kusurun eski uygulamasını ölçüyordu. Yeni sürüm ÜYELİK
    sorar (tabloda var mı?), dolayısıyla uygulamadan bağımsızdır ve daha
    GENİŞTİR: yalnız tavanın üstündeki değil, HERHANGİ bir sebeple düşen
    modu görür. Kusurlu kodda birebir aynı sonucu verdiği ölçüldü
    (docs/scofield/raw/OH/D26/termo-ucus/a1/once.json, K3: katı orantısı
    n=10 -> 7L..14L, sekiz mod).
    """
    fmax = max(m['frequency_hz'] for m in res['modes'])
    listede = {m['label'] for m in res['modes']}
    eksik = []
    q = 1
    while True:
        f = longitudinal_frequency(a, L, q)
        if f > fmax * (1.0 + 1e-12):
            break
        if f'{q}L' not in listede:
            eksik.append((f'{q}L', f))
        q += 1
        if q > 20000:                      # güvenlik: sonsuz döngü olmasın
            break
    return fmax, eksik


class TestModeTable:
    def test_sorted_ascending_and_n_modes(self):
        """Tablo sıralı, istenen sayıda VE kendi bandında eksiksiz.

        ÖH Faz B (defter P4B4-14). Eski hâli iki şey soruyordu: uzunluk 10
        mu, sıralı mı. İkisi de mod havuzunun KIRPILMASINDAN bağımsızdır;
        bu yüzden "en düşük N mod" listesinden gerçek modların düşmesini
        göremezdi. Buraya EKSİKSİZLİK iddiası eklenir: listenin kendi en
        yüksek frekansının altında, listeye girmemiş gerçek bir mod
        olmamalıdır.

        ÖLÇÜLDÜ (27 Ağustos 2026): bu fikstürde (L/D = 4, n=10) tablo
        gerçekten eksiksizdir — yani bu bekçinin BUGÜNKÜ fikstürü kusuru
        göremez. Kırpmanın gerçek modları düşürdüğü katı motor orantısı
        aşağıdaki xfail imli bekçidedir; bu test onun negatif kontrolüdür.
        """
        res = _analyze(n_modes=10)
        freqs = [m['frequency_hz'] for m in res['modes']]
        assert len(freqs) == 10
        assert freqs == sorted(freqs)
        # Eksiksizlik: kapalı form testin içinde kurulur.
        a = sound_speed(1.2, 360.0, 3000.0)
        fmax, eksik = _eksik_boyuna_modlar(res, a, 0.40)
        assert not eksik, (
            f'tablo kendi bandında ({fmax:.1f} Hz altı) eksik: {eksik}')

    @pytest.mark.parametrize('n_modes', [10, 59, 200])
    def test_havuz_kirpmasi_kati_motor_orantisinda_gercek_mod_dusuruyor(
            self, n_modes):
        """Uzun/ince kavitede tablo kendi bandında eksiksiz olmalı.

        ÖH D26 / P4B4-14 — BORÇ İMİ KALKTI. Kusur (ölçülen, once.json K3):
        havuz ``MAX_LONGITUDINAL_INDEX = 6`` ile SABİT kırpılıyordu; katı
        motor orantısında (D=0,20 m, L=2,5 m, a=848,53 m/s, n=10) tablonun
        kendi en yüksek frekansı 2538,06 Hz iken 7L..14L (1187,9-2375,9 Hz)
        SEKİZ gerçek boyuna mod listeye giremiyordu ve n_modes=200 istense
        bile havuz 83 adayda tükeniyordu (kayıp 84 moda çıkıyordu).
        Onarımdan sonra havuz kesim frekansına göre büyütülüyor; üç talepte
        de eksik mod YOK (sonra.json K3).
        """
        res = AcousticModeAnalyzer().analyze(n_modes=n_modes,
                                             **KATI_MOTOR_KAVITESI)
        a = sound_speed(KATI_MOTOR_KAVITESI['gamma'],
                        KATI_MOTOR_KAVITESI['gas_constant'],
                        KATI_MOTOR_KAVITESI['chamber_temperature'])
        fmax, eksik = _eksik_boyuna_modlar(
            res, a, KATI_MOTOR_KAVITESI['chamber_length'])
        assert len(res['modes']) == n_modes
        assert not eksik, (
            f'{fmax:.1f} Hz altında kalan {len(eksik)} gerçek boyuna mod '
            f'tabloya giremedi: {[(k, round(v, 1)) for k, v in eksik]} — '
            'havuz kırpması modu fizikten değil sabitten düşürüyor')
        # Havuz künyesi eksiksizliği BEYAN etmeli (kırpma sessiz kalamaz).
        havuz = res['mode_pool']
        assert havuz['truncated'] is False
        assert havuz['complete_below_hz'] == pytest.approx(fmax, rel=1e-12)
        # Büyütme gerçekten oldu: tohum tavanı q<=6 idi.
        assert havuz['longitudinal_max_q'] > havuz['seed_bounds'][
            'longitudinal_max_q']

    def test_screech_hukmu_kirpmayi_beyan_ediyor(self):
        """Screech hükmü EKSİKSİZ havuzdan türer ve bunu beyan eder.

        ÖH D26 / P4B4-14 — BORÇ İMİ KALKTI. Kusur (ölçülen): katı motor
        orantısında (n=10) ``modes_in_screech_band`` =
        ['6L','1T','1T1L','1T2L','1T3L'] iken 1000 Hz üstündeki 7L..14L
        sekiz gerçek mod ne listedeydi ne de note alanında kırpmadan söz
        ediliyordu — kullanıcı listeyi eksiksiz sanıyordu.

        Bekçi ÜÇ yönde birden kilitler ve hiçbiri "not cümlesine kelime
        eklemekle" geçilemez:
          1. Bandın içinde tablodan DÜŞEN gerçek mod kalmaz.
          2. Yayımlanan screech listesi, tablonun screech üyeleriyle
             BİREBİR aynıdır (liste hükmü tablodan sapamaz).
          3. Hükmün yanında havuzun eksiksizlik SINIRI sayıyla durur ve
             tablonun en yüksek frekansını kapsar.
        """
        res = AcousticModeAnalyzer().analyze(n_modes=10,
                                             **KATI_MOTOR_KAVITESI)
        a = sound_speed(KATI_MOTOR_KAVITESI['gamma'],
                        KATI_MOTOR_KAVITESI['gas_constant'],
                        KATI_MOTOR_KAVITESI['chamber_temperature'])
        fmax, eksik = _eksik_boyuna_modlar(
            res, a, KATI_MOTOR_KAVITESI['chamber_length'])
        hf = res['stability_report']['high_frequency']
        bantta_eksik = [k for k, f in eksik if f >= FREQ_BAND_BUZZ_MAX_HZ]
        assert not bantta_eksik, (
            f'screech hükmü {len(bantta_eksik)} gerçek modu '
            f'({bantta_eksik[:4]}...) listelemiyor — hüküm eksik havuzdan '
            'türüyor')
        tablodaki = {m['label'] for m in res['modes']
                     if m['band'] == 'screech_range'}
        assert set(hf['modes_in_screech_band']) == tablodaki
        assert hf['mode_pool_truncated'] is False
        assert hf['mode_pool_complete_below_hz'] == pytest.approx(
            fmax, rel=1e-12)
        # Kusur vakası: 7L..14L artık GERÇEKTEN listede.
        assert {f'{q}L' for q in range(7, 11)} <= set(
            hf['modes_in_screech_band'])

    def test_labels_unique_and_expected_present(self):
        res = _analyze(n_modes=10)
        labels = [m['label'] for m in res['modes']]
        assert len(labels) == len(set(labels))
        # L/D = 4 kamarada ilk modlar boyuna ağırlıklıdır; 1L kesin öndedir.
        assert '1L' in labels

    def test_pure_longitudinal_alpha_is_none(self):
        """Saf boyuna modda enine kök YOKTUR -> alpha None (0 uydurulmaz)."""
        res = _analyze()
        m = _mode(res, '1L')
        assert m['alpha'] is None
        assert m['type'] == 'longitudinal'
        assert m['indices'] == {'tangential_m': 0, 'radial_n': 0,
                                'longitudinal_q': 1}

    def test_tangential_mode_metadata(self):
        res = _analyze(n_modes=59)
        m = _mode(res, '1T')
        assert m['type'] == 'tangential'
        assert m['alpha'] == pytest.approx(1.8412, abs=5e-4)
        assert m['indices'] == {'tangential_m': 1, 'radial_n': 0,
                                'longitudinal_q': 0}

    def test_band_classification_matches_constants(self):
        res = _analyze(n_modes=59)
        for m in res['modes']:
            f = m['frequency_hz']
            if f < FREQ_BAND_CHUG_MAX_HZ:
                assert m['band'] == 'chug_range'
            elif f < FREQ_BAND_BUZZ_MAX_HZ:
                assert m['band'] == 'buzz_range'
            else:
                assert m['band'] == 'screech_range'

    def test_basis_fields_present(self):
        """Her yeni çıktı alanına dayanak beyanı kuralı: _basis alanları."""
        res = _analyze()
        assert 'sound_speed_basis' in res and 'ideal gas' in res['sound_speed_basis']
        assert 'mode_table_basis' in res and 'jnp_zeros' in res['mode_table_basis']

    def test_rejects_bad_inputs(self):
        with pytest.raises(ValueError):
            _analyze(chamber_diameter=0.0)
        with pytest.raises(ValueError):
            _analyze(chamber_length=float('inf'))
        with pytest.raises(ValueError):
            _analyze(n_modes=0)


# ===========================================================================
# Kararlılık marjı raporu (chug + yüksek frekans)
# ===========================================================================
class TestStabilityReport:
    def test_chug_ok_above_recommended(self):
        res = _analyze(chamber_pressure=20.0, injector_pressure_drop_bar=5.0)
        chug = res['stability_report']['chug']
        assert chug['evaluated'] is True
        assert chug['injector_dp_ratio'] == pytest.approx(0.25, rel=1e-12)
        assert chug['ratio_source'] == 'delta_p_over_pc'
        assert chug['status'] == AcousticModeAnalyzer.STATUS_OK

    def test_chug_marginal_band(self):
        res = _analyze(injector_dp_ratio=0.17)
        chug = res['stability_report']['chug']
        assert chug['status'] == AcousticModeAnalyzer.STATUS_MARGINAL
        assert chug['ratio_source'] == 'user_supplied_ratio'

    def test_chug_at_risk_below_minimum(self):
        res = _analyze(injector_dp_ratio=0.10)
        chug = res['stability_report']['chug']
        assert chug['status'] == AcousticModeAnalyzer.STATUS_AT_RISK

    def test_chug_boundaries_use_module_constants(self):
        """Eşikler tek yerden gelir; sınır değerlerde hüküm doğru döner.

        ÖH Faz B (defter P4B4-16). Eski hâli yalnız ALT eşikleri sınıyordu
        (0,20 -> OK, 0,15 -> MARGINAL) ve künyeyi iki anahtar kelimeyle
        yokluyordu. Eklenen bağlaşım: modülün iki sabiti, künyesinin İLAN
        ETTİĞİ bandın içinde olmalıdır. Band literatürden gelir ve BURADA
        yazılıdır (üründen türetilmez): Sutton & Biblarz, "Rocket
        Propulsion Elements", 9. baskı, Böl. 8 — enjektör basınç düşümü
        klasik olarak oda basıncının %15-25'i seçilir.
        """
        assert (_analyze(injector_dp_ratio=CHUG_DP_RATIO_RECOMMENDED)
                ['stability_report']['chug']['status']
                == AcousticModeAnalyzer.STATUS_OK)
        assert (_analyze(injector_dp_ratio=CHUG_DP_RATIO_MINIMUM)
                ['stability_report']['chug']['status']
                == AcousticModeAnalyzer.STATUS_MARGINAL)
        chug = _analyze(injector_dp_ratio=0.5)['stability_report']['chug']
        assert chug['recommended_min_ratio'] == CHUG_DP_RATIO_RECOMMENDED
        assert chug['hard_min_ratio'] == CHUG_DP_RATIO_MINIMUM
        assert 'Sutton' in chug['threshold_source']
        assert 'SP-194' in chug['threshold_source']
        # Bağlaşım: iki sabit de yayımlanmış bandın İÇİNDE olmalı ve
        # künye aynı bandı ilan etmeli (iki kaynak, tek sayı ailesi).
        alt, ust = CHUG_BANDI_YAYIMLANMIS
        assert alt <= CHUG_DP_RATIO_MINIMUM <= ust
        assert alt <= CHUG_DP_RATIO_RECOMMENDED <= ust
        assert re.search(r'15\s*-\s*25\s*%', chug['threshold_source']), (
            'künye artık %15-25 bandını ilan etmiyor — sabitlerin dayanağı '
            f"değişmiş olabilir: {chug['threshold_source'][:120]}")

    @pytest.mark.parametrize('oran', [0.30, 0.5, 1.0, 1.527, 12.0])
    def test_chug_oraninin_ust_siniri_var(self, oran):
        """İlan edilen bandın katındaki tasarım temiz OK alamaz.

        ÖH D26 / P4B4-16 — BORÇ İMİ KALKTI. Kusur (ölçülen, once.json K4):
        0,30 / 0,50 / 1,00 / 1,527 (gerçek hibrit koşumunda ölçülen oran) ve
        12,0 — BEŞİ de "... meets the recommended >= 0.20 design rule"
        cümlesiyle TEMİZ ``STATUS_OK`` alıyordu; modülün kendi künyesi bandı
        %15-25 ilan ederken üst uçta hiçbir kademe yoktu.

        Hüküm AYRIMI korunur: chug MEKANİZMASI bakımından yüksek oran iyidir,
        bu yüzden ``status`` OK kalır (uydurma risk hükmü üretilmez); kalkan
        şey, bandın aşıldığının SÖYLENMEMESİDİR. Üst uç ayrıca ALAN olarak
        yayımlanır, yoksa hiçbir tüketici (panel, rapor) onu göremez.
        """
        chug = _analyze(injector_dp_ratio=oran)['stability_report']['chug']
        _, ust = CHUG_BANDI_YAYIMLANMIS
        assert chug['injector_dp_ratio'] == pytest.approx(oran, rel=1e-12)
        assert oran > ust                       # ön koşul: band aşılıyor
        temiz_ok = (chug['status'] == AcousticModeAnalyzer.STATUS_OK
                    and 'meets the recommended' in chug['note']
                    and not re.search(r'exceed|above the|upper', chug['note'],
                                      re.IGNORECASE))
        assert not temiz_ok, (
            f"oran {oran:g}, ilan edilen bandın üst ucunun ({ust:g}) "
            f"{oran / ust:.1f} katı olduğu hâlde hüküm "
            f"{chug['status']} ve not bandın aşıldığını söylemiyor: "
            f"{chug['note'][:120]}")
        # Üst uç YAYIMLANIYOR ve ilan edilen bandla aynı sayı.
        assert chug['design_band_max_ratio'] == pytest.approx(ust, rel=1e-12)
        assert chug['design_band_min_ratio'] == pytest.approx(
            CHUG_BANDI_YAYIMLANMIS[0], rel=1e-12)
        assert chug['above_design_band'] is True
        assert chug['design_band_excess_factor'] == pytest.approx(
            oran / ust, rel=1e-12)

    @pytest.mark.parametrize('oran', [0.15, 0.20, 0.25])
    def test_band_ICINDEKI_oran_ust_sinir_uyarisi_ALMAZ(self, oran):
        """Üst sınır uyarısı bandın İÇİNDE tetiklenmez (yanlış alarm yok)."""
        chug = _analyze(injector_dp_ratio=oran)['stability_report']['chug']
        assert chug['above_design_band'] is False
        assert chug['design_band_excess_factor'] is None
        assert not re.search(r'EXCEEDS the upper bound', chug['note'])

    def test_chug_not_evaluated_without_inputs(self):
        """Girdisiz hüküm UYDURULMAZ: NOT_EVALUATED + None oran."""
        chug = _analyze()['stability_report']['chug']
        assert chug['evaluated'] is False
        assert chug['injector_dp_ratio'] is None
        assert chug['status'] == AcousticModeAnalyzer.STATUS_NOT_EVALUATED

    def test_chug_rejects_invalid_ratio(self):
        with pytest.raises(ValueError):
            _analyze(injector_dp_ratio=-0.1)
        with pytest.raises(ValueError):
            _analyze(chamber_pressure=0.0, injector_pressure_drop_bar=5.0)

    def test_high_frequency_report(self):
        res = _analyze(n_modes=59)
        hf = res['stability_report']['high_frequency']
        assert hf['screech_band_min_hz'] == FREQ_BAND_BUZZ_MAX_HZ
        # D=0.10 m sıcak kamarada 1T ~ 6 kHz -> screech bandındadır
        assert '1T' in hf['modes_in_screech_band']
        assert 'SP-194' in hf['band_source'] or 'Sutton' in hf['band_source']


# ===========================================================================
# NOT_MODELLED beyanı
# ===========================================================================
class TestNotModelled:
    def test_declared_in_output(self):
        res = _analyze()
        nm = res['not_modelled']
        assert set(nm) == set(NOT_MODELLED)
        assert 'combustion_response' in nm
        assert 'Rayleigh' in nm['combustion_response']
        assert 'damping' in nm
        for kw in ('baffle', 'resonator', 'nozzle'):
            assert kw.lower() in nm['damping'].lower()
        assert 'mean_flow_and_gradients' in nm

    def test_output_copy_is_isolated(self):
        """Çıktıdaki sözlük modül sabitinin KOPYASIdır (mutasyon sızmaz)."""
        res = _analyze()
        res['not_modelled']['combustion_response'] = 'tampered'
        assert NOT_MODELLED['combustion_response'] != 'tampered'


# ===========================================================================
# Motor sonucu adaptörü (hibrit şema uyumu)
# ===========================================================================
class TestEngineResultAdapter:
    ENGINE_RESULT = {
        # hybrid_rocket_engine.calculate() üst seviye alan adları
        'chamber_temperature': 3200.0,   # K
        'gamma': 1.24,
        'molecular_weight': 24.0,        # g/mol
        'chamber_diameter': 0.08,        # m
        'chamber_length': 0.35,          # m
        'chamber_pressure': 20.0,        # bar
    }

    def test_adapter_matches_direct_call(self):
        via_adapter = analyze_from_engine_result(dict(self.ENGINE_RESULT))
        direct = AcousticModeAnalyzer().analyze(
            chamber_temperature=3200.0, gamma=1.24,
            gas_constant=R_UNIVERSAL_J_KMOL_K / 24.0,
            chamber_diameter=0.08, chamber_length=0.35,
            chamber_pressure=20.0)
        assert via_adapter['sound_speed_m_s'] == pytest.approx(
            direct['sound_speed_m_s'], rel=1e-12)
        assert (via_adapter['inputs']['gas_constant']
                == pytest.approx(R_UNIVERSAL_J_KMOL_K / 24.0, rel=1e-12))

    def test_missing_field_raises_not_fabricates(self):
        """Eksik alan için varsayılan UYDURULMAZ -> ValueError."""
        for key in ('chamber_temperature', 'gamma', 'molecular_weight',
                    'chamber_diameter', 'chamber_length'):
            broken = dict(self.ENGINE_RESULT)
            del broken[key]
            with pytest.raises(ValueError, match=key):
                analyze_from_engine_result(broken)

    def test_zero_field_treated_as_missing(self):
        broken = dict(self.ENGINE_RESULT, chamber_length=0.0)
        with pytest.raises(ValueError, match='chamber_length'):
            analyze_from_engine_result(broken)

    def test_chug_passthrough(self):
        res = analyze_from_engine_result(
            dict(self.ENGINE_RESULT), injector_pressure_drop_bar=4.0)
        chug = res['stability_report']['chug']
        assert chug['injector_dp_ratio'] == pytest.approx(0.20, rel=1e-12)
        assert chug['status'] == AcousticModeAnalyzer.STATUS_OK

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError):
            analyze_from_engine_result([1, 2, 3])
