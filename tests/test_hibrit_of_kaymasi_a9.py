"""A9 — hibritte O/F kayması: bekçi testleri (v2.6.27, yol haritası Kulvar A).

NEDEN VAR
---------
Hibrit motorda yakıt regresyon hızı r = a·G_ox^n olduğundan port çapı
büyüdükçe G_ox düşer, yakıt debisi değişir ve O/F YANMA BOYUNCA KAYAR — katı
ve sıvı motorda karşılığı olmayan, hibridin en karakteristik davranışı.
Çözücü O/F(t), c*(t) ve Isp(t) serilerini zaten üretiyordu; eksik olan üç şey
vardı ve üçü de bu dosyada kilitlenir:

1. **Tasarım noktası ile gerçekleşen ortalama arasındaki fark hesaplanmıyordu.**
   Kullanıcı manşette "tasarım Isp'si"ni görüyor, yanma boyunca gerçekleşen
   ortalamayı hiç görmüyordu. ÖLÇÜLDÜ (bu depo, 2026-08-05, varsayılan
   girdiler): ortalama Isp tasarım Isp'sinden +%0,66 farklı; regresyon üssü
   n = 0,75'e çıkarıldığında fark +%7,9'a çıkıyor.

2. **Blowdown beslemesinin ṁ_ox(t)'si O/F'ye hiç bağlanmamıştı.** ``A1``
   bloğu tank basıncının düşüşünü ve ṁ_ox(t)'yi zaten çözüyordu ama O/F(t)
   dışarı çıkmıyordu; O/F kayması yalnız regüleli (sabit ṁ_ox) durumda
   görülüyordu. ÖLÇÜLDÜ: aynı motorda regüleli besleme O/F'yi +%3,83
   YUKARI, blowdown beslemesi -%7,22 AŞAĞI sürüklüyor — yani iki besleme
   birbirinin ters yönünde kayıyor ve tek durumu göstermek yanıltıcıydı.

3. **c*(O/F) tablosu en yakın düğüme YUVARLANIYORDU ve hatası beyansızdı.**
   ÖLÇÜLDÜ: yuvarlama c*'ta ±%0,26'ya varan sıçrama üretiyordu (Isp(t)
   eğrisinde ızgara geçişlerinde basamak); doğrusal ara değerleme AYNI düğüm
   sayısıyla hatayı %0,004 mertebesine indiriyor.

BEKÇİ İLKESİ
------------
Bu dosyadaki hiçbir sınama sabit bir sayıya bağlanmaz: eşikler ve hata
sınırları motor modülünden İÇE AKTARILIR, yönler fizik bağıntısından
(ṁ_f ∝ D^(1−2n)) türetilir, özdeşlikler (I = Isp·m·g0) çözücünün kendi
sayılarıyla kapatılır. Bir kalem gerçekten modellenince sayı değişebilir;
bekçi kusuru kilitlemez.
"""

import json
import warnings

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import (
    OF_PERF_GRID_STEP,
    OF_PERF_INTERP_ERROR_BOUND_PCT,
    OF_SHIFT_WARN_FRACTION,
    HybridRocketEngine,
)

UYARI_KODU = 'warn.hybrid.of_shift_large'
G0 = 9.80665


def _kos(**degisiklik):
    """Koşulmuş hibrit motor + sonuç sözlüğü."""
    ayarlar = dict(thrust=1000, burn_time=10, of_ratio=2.5,
                   chamber_pressure=20.0, flux_mode='ox')
    ayarlar.update(degisiklik)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(**ayarlar)
        sonuc = motor.calculate()
    return motor, sonuc


@pytest.fixture(scope='module')
def varsayilan():
    """HTPB varsayılanı: n = 0,555 > 0,5, yani O/F yanma boyunca ARTAR."""
    return _kos()


@pytest.fixture(scope='module')
def ussu_yuksek():
    """n = 0,75: kayma eşiği aşacak kadar büyük (ölçüldü: +%37,6)."""
    return _kos(regression_n=0.75, regression_a=3.68e-5)


@pytest.fixture(scope='module')
def ussu_dusuk():
    """n = 0,30 < 0,5: ṁ_f ∝ D^(1−2n) arttığından O/F AZALIR (ters yön)."""
    return _kos(regression_n=0.30, regression_a=3.68e-5)


# ---------------------------------------------------------------------------
# 1. Blok gerçek hesaptan geliyor
# ---------------------------------------------------------------------------

def test_of_kaymasi_blogu_yayimlaniyor(varsayilan):
    _, sonuc = varsayilan
    assert 'of_shift' in sonuc, 'A9 bloğu sonuç şemasında yok'
    blok = sonuc['of_shift']
    assert blok['status'] == 'modelled'
    assert blok['basis'], 'blok gerekçe beyanı taşımalı'
    for alan in ('design_point', 'regulated', 'blowdown', 'interpolation'):
        assert alan in blok, f'{alan} alanı eksik'


def test_tasarim_noktasi_cozucunun_kendi_degerleri(varsayilan):
    """design_point manşet sayılarının AYNISI olmalı (ikinci gerçeklik yok)."""
    motor, sonuc = varsayilan
    tasarim = sonuc['of_shift']['design_point']
    assert tasarim['of_ratio'] == pytest.approx(motor.OF)
    assert tasarim['isp_s'] == pytest.approx(sonuc['isp'])
    assert tasarim['c_star_m_s'] == pytest.approx(sonuc['c_star'])
    assert tasarim['total_impulse_Ns'] == pytest.approx(
        sonuc['thrust'] * sonuc['burn_time'])


def test_seriler_zaman_adimli_cozumun_kendisi(varsayilan):
    """Yayımlanan özet, motorun iç zaman serileriyle birebir aynı koşudan."""
    motor, sonuc = varsayilan
    reg = sonuc['of_shift']['regulated']
    assert reg['samples'] == len(motor._of_history)
    assert reg['of_ratio_initial'] == pytest.approx(motor._of_history[0])
    assert reg['of_ratio_final'] == pytest.approx(motor._of_history[-1])
    assert reg['of_ratio_min'] == pytest.approx(min(motor._of_history))
    assert reg['of_ratio_max'] == pytest.approx(max(motor._of_history))


# ---------------------------------------------------------------------------
# 2. O/F(t) yönü port büyümesiyle tutarlı
# ---------------------------------------------------------------------------

def test_port_yanma_boyunca_buyuyor(varsayilan):
    """Kaymanın SEBEBİ: port büyüyor, dolayısıyla G_ox düşüyor."""
    motor, sonuc = varsayilan
    assert motor.D_port_final > motor.D_port_initial
    assert sonuc['g_ox_final'] < sonuc['g_ox_initial']


@pytest.mark.parametrize('fixture_adi', ['varsayilan', 'ussu_yuksek',
                                         'ussu_dusuk'])
def test_of_kaymasi_yonu_regresyon_ussuyle_tutarli(fixture_adi, request):
    """ṁ_f ∝ D^(1−2n) ⇒ O/F ∝ D^(2n−1): n>0,5 artar, n<0,5 azalır.

    Sabit bir sayı değil, FİZİK BAĞINTISININ İŞARETİ kilitlenir. Regresyon
    katsayısı ya da yakıt değişse bile bekçi doğru kalır.
    """
    motor, sonuc = request.getfixturevalue(fixture_adi)
    of = np.asarray(sonuc['of_shift_performance']['of_ratio'], dtype=float)
    fark = np.diff(of)
    beklenen_isaret = np.sign(2.0 * motor.n - 1.0)
    assert beklenen_isaret != 0, 'bu bekçi n = 0,5 için ayrım yapamaz'
    if beklenen_isaret > 0:
        assert np.all(fark >= -1e-12), (
            f'n = {motor.n} > 0,5 iken O/F artmalı (ṁ_f ∝ D^(1−2n) azalır)')
        assert of[-1] > of[0]
    else:
        assert np.all(fark <= 1e-12), (
            f'n = {motor.n} < 0,5 iken O/F azalmalı (ṁ_f ∝ D^(1−2n) artar)')
        assert of[-1] < of[0]


def test_anlik_of_debilerin_orani(varsayilan):
    """O/F(t) = ṁ_ox / ṁ_f(t) — regüleli beslemede ṁ_ox sabit."""
    motor, _ = varsayilan
    of = np.asarray(motor._of_history, dtype=float)
    mdot_f = np.asarray(motor._mdot_f_history, dtype=float)
    assert len(of) == len(mdot_f)
    assert np.allclose(of * mdot_f, motor.mdot_ox, rtol=1e-12)


# ---------------------------------------------------------------------------
# 3. Blowdown bağlıyken ṁ_ox AYNI kaynaktan
# ---------------------------------------------------------------------------

def test_blowdown_durumu_yayimlaniyor(varsayilan):
    _, sonuc = varsayilan
    # Önkoşul gerçek: bu koşuda blowdown bloğu gerçekten çözülüyor
    assert sonuc['tank_blowdown']['status'] == 'modelled'
    bd = sonuc['of_shift']['blowdown']
    assert bd.get('status') != 'NOT_MODELLED'
    assert bd['source_block'] == 'tank_blowdown'


def test_blowdown_mdot_ox_ayni_kaynaktan(varsayilan):
    """İki blokta iki farklı ṁ_ox dolaşamaz: diziler BİREBİR aynı olmalı."""
    _, sonuc = varsayilan
    bd = sonuc['of_shift']['blowdown']
    tank = sonuc['tank_blowdown']
    assert bd['mdot_ox_kg_s'] == tank['mdot_ox_kg_s']
    assert bd['mdot_fuel_kg_s'] == tank['mdot_fuel_kg_s']
    assert bd['of_ratio'] == tank['of_ratio']
    assert bd['time_s'] == tank['time_s']


def test_blowdown_of_orani_kendi_debilerinden(varsayilan):
    """O/F(t) = ṁ_ox(t)/ṁ_f(t): blowdown'da ṁ_ox da DEĞİŞİR."""
    _, sonuc = varsayilan
    bd = sonuc['of_shift']['blowdown']
    of = np.asarray(bd['of_ratio'], dtype=float)
    mo = np.asarray(bd['mdot_ox_kg_s'], dtype=float)
    mf = np.asarray(bd['mdot_fuel_kg_s'], dtype=float)
    assert np.allclose(of, mo / mf, rtol=1e-12)
    # Blowdown'un ayırt edici özelliği: oksitleyici debisi düşer
    assert mo[-1] < mo[0], 'blowdown beslemesinde ṁ_ox düşmeli'


def test_blowdown_ve_reguleli_ayri_kayma_veriyor(varsayilan):
    """İki besleme aynı motorda farklı O/F kayması üretir (tek durum yetmez)."""
    _, sonuc = varsayilan
    blok = sonuc['of_shift']
    reg_son = blok['regulated']['of_ratio_final']
    bd_son = blok['blowdown']['of_ratio_final']
    tasarim = blok['design_point']['of_ratio']
    assert reg_son != pytest.approx(bd_son, rel=1e-6)
    # Ölçülen davranış: regüleli yukarı, blowdown aşağı (n = 0,555 ve düşen
    # ṁ_ox). Yönler sayı değil, işaret olarak kilitlenir.
    assert (reg_son - tasarim) * (bd_son - tasarim) < 0


def test_blowdown_yoksa_egri_uydurulmuyor():
    """N2O dışı oksitleyicide blowdown modeli yok — durum gerekçeyle boş."""
    _, sonuc = _kos(oxidizer_type='lox', of_ratio=2.0)
    assert sonuc['tank_blowdown']['status'] == 'NOT_MODELLED'
    bd = sonuc['of_shift']['blowdown']
    assert bd['status'] == 'NOT_MODELLED'
    assert bd['reason'], 'gerekçe taşımalı'
    # Sayı yok: uydurma eğri, eğrisizlikten kötüdür
    assert 'of_ratio' not in bd and 'mdot_ox_kg_s' not in bd
    # Regüleli durum yine de çözülür
    assert sonuc['of_shift']['regulated']['of_ratio_final'] is not None


# ---------------------------------------------------------------------------
# 4. Ara değerleme: yöntem ve ÖLÇÜLEN hata
# ---------------------------------------------------------------------------

def test_ara_degerleme_teshisi_olculmus(varsayilan):
    _, sonuc = varsayilan
    tani = sonuc['of_shift']['interpolation']
    assert tani['status'] == 'modelled'
    assert tani['grid_step_of'] == OF_PERF_GRID_STEP, 'ızgara TEK kaynaktan'
    assert tani['error_bound_pct'] == OF_PERF_INTERP_ERROR_BOUND_PCT
    assert tani['error_probe_count'] > 0, 'hata gerçekten ölçülmüş olmalı'
    assert tani['grid_nodes_solved'] > 0
    lo, hi = tani['of_range_traversed']
    assert lo < hi, 'katedilen O/F aralığı yayımlanmalı'


def test_ara_degerleme_hatasi_beyan_edilen_sinirin_altinda(varsayilan):
    _, sonuc = varsayilan
    tani = sonuc['of_shift']['interpolation']
    assert tani['error_max_pct'] <= tani['error_bound_pct'], (
        'ölçülen ara değerleme hatası beyan edilen sınırı aşıyor — ya ızgara '
        'sıklaştırılmalı ya da beyan edilen sınır düzeltilmeli')
    assert tani['within_declared_bound'] is True
    assert tani['error_status'] == 'within_declared_bound'
    assert tani['error_mean_pct'] <= tani['error_max_pct']
    assert not tani['equilibrium_solver_fallback_used'], (
        'denge çözücüsü bir düğümde çöktüyse c* tasarım değerine düşmüştür')


def test_ara_degerleme_hatasi_bagimsiz_dogrulandi(varsayilan):
    """Bloğun kendi raporuna GÜVENİLMEZ: hata bağımsız ölçülür.

    Izgara aralığının tam ortası doğrusal ara değerlemenin en kötü konumudur;
    orada tam denge çözümüyle karşılaştırılır.
    """
    motor, sonuc = varsayilan
    lo, hi = sonuc['of_shift']['interpolation']['of_range_traversed']
    dugum = int(np.floor(0.5 * (lo + hi) / OF_PERF_GRID_STEP))
    of_orta = (dugum + 0.5) * OF_PERF_GRID_STEP
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        tam = motor.combustion_analyzer.analyze_combustion(
            {motor.fuel_type: 100.0}, motor.oxidizer_type, of_orta,
            motor.P_c, None)['performance']['c_star']
        yaklasik, _ = motor._instantaneous_performance(of_orta)
    hata_pct = abs(yaklasik / tam - 1.0) * 100.0
    assert hata_pct <= OF_PERF_INTERP_ERROR_BOUND_PCT, (
        f'bağımsız ölçüm {hata_pct:.4f}% hata veriyor, beyan edilen sınır '
        f'{OF_PERF_INTERP_ERROR_BOUND_PCT}%')


def test_yuvarlama_degil_ara_degerleme_yapiliyor(varsayilan):
    """Düğümler arası bir O/F, düğüm değerlerinden BİRİNE eşit olamaz.

    Eski davranış (en yakın düğüme yuvarlama) tam olarak bunu yapıyordu ve
    Isp(t) eğrisine basamak koyuyordu; bekçi geri dönüşü yakalar.
    """
    motor, sonuc = varsayilan
    lo, hi = sonuc['of_shift']['interpolation']['of_range_traversed']
    dugum = int(np.floor(0.5 * (lo + hi) / OF_PERF_GRID_STEP))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        c_alt, _ = motor._instantaneous_performance(
            dugum * OF_PERF_GRID_STEP)
        c_ust, _ = motor._instantaneous_performance(
            (dugum + 1) * OF_PERF_GRID_STEP)
        c_orta, _ = motor._instantaneous_performance(
            (dugum + 0.5) * OF_PERF_GRID_STEP)
    assert c_alt != pytest.approx(c_ust, rel=1e-9), (
        'bu aralıkta c* değişmiyor; sınama ayrım yapamaz')
    assert min(c_alt, c_ust) < c_orta < max(c_alt, c_ust), (
        'ara değer iki düğümün ARASINDA olmalı (yuvarlanmış değil)')
    assert c_orta == pytest.approx(0.5 * (c_alt + c_ust), rel=1e-9)


# ---------------------------------------------------------------------------
# 5. Zaman ortalamalı performans ve tasarım noktasıyla FARK
# ---------------------------------------------------------------------------

def test_toplam_impuls_ozdesligi(varsayilan):
    """I = Isp_ort · m_harcanan · g0 — özdeşlik tam kapanmalı.

    Kütle başka bir yerden getirilirse (ör. tasarım noktası kütlesi) özdeşlik
    bozulur ve iki farklı gerçeklik dolaşmaya başlar.
    """
    _, sonuc = varsayilan
    reg = sonuc['of_shift']['regulated']
    assert reg['total_impulse_Ns'] == pytest.approx(
        reg['isp_mass_avg_s'] * reg['propellant_consumed_kg'] * G0, rel=1e-9)


def test_farklar_tasarim_noktasina_gore_hesaplaniyor(varsayilan):
    """Kullanıcı farkı çıkarmak zorunda kalmamalı: yüzde farklar yayımlanır."""
    _, sonuc = varsayilan
    blok = sonuc['of_shift']
    tasarim = blok['design_point']
    reg = blok['regulated']
    assert reg['isp_delta_vs_design_pct'] == pytest.approx(
        (reg['isp_mass_avg_s'] / tasarim['isp_s'] - 1.0) * 100.0, rel=1e-9)
    assert reg['c_star_delta_vs_design_pct'] == pytest.approx(
        (reg['c_star_time_avg_m_s'] / tasarim['c_star_m_s'] - 1.0) * 100.0,
        rel=1e-9)
    assert reg['total_impulse_delta_vs_design_pct'] == pytest.approx(
        (reg['total_impulse_Ns'] / tasarim['total_impulse_Ns'] - 1.0) * 100.0,
        rel=1e-9)


def test_ortalama_isp_tasarim_ispsinden_beklenen_yonde_farkli(varsayilan):
    """Farkın İŞARETİ, kayma yönünün c* üzerindeki etkisiyle uyuşmalı.

    Sabit bir yüzde kilitlenmez: motorun KENDİ c*(O/F) tablosundan, kayılan
    O/F'nin tasarım O/F'sine göre c*'ı artırıp artırmadığı okunur ve
    gerçekleşen ortalamanın işareti onunla karşılaştırılır.
    """
    motor, sonuc = varsayilan
    blok = sonuc['of_shift']
    reg = blok['regulated']
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        c_tasarim, _ = motor._instantaneous_performance(
            blok['design_point']['of_ratio'])
        c_son, _ = motor._instantaneous_performance(reg['of_ratio_final'])
    beklenen = np.sign(c_son - c_tasarim)
    assert beklenen != 0, 'kayma c*'"'"'ı hiç değiştirmiyor; sınama ayrım yapamaz'
    assert np.sign(reg['isp_delta_vs_design_pct']) == beklenen
    assert np.sign(reg['c_star_delta_vs_design_pct']) == beklenen
    # Ortalama, anlık serinin bandı içinde kalmalı (dışına taşarsa ortalama
    # başka bir şeyden hesaplanıyordur)
    isp_seri = sonuc['of_shift_performance']['isp']
    assert min(isp_seri) <= reg['isp_time_avg_s'] <= max(isp_seri)


def test_buyuk_kaymada_fark_buyuyor(varsayilan, ussu_yuksek):
    """Kayma büyüdükçe tasarım-gerçek farkı da büyümeli (fizik tutarlılığı)."""
    _, kucuk = varsayilan
    _, buyuk = ussu_yuksek
    k = kucuk['of_shift']['regulated']
    b = buyuk['of_shift']['regulated']
    assert b['of_shift_fraction'] > k['of_shift_fraction']
    assert abs(b['isp_delta_vs_design_pct']) > abs(k['isp_delta_vs_design_pct'])


def test_eski_blok_geriye_uyumlu_ve_farklari_tasiyor(varsayilan):
    """motor_viz3d.js of_shift_performance okuyor: diziler yerinde kalmalı."""
    _, sonuc = varsayilan
    perf = sonuc['of_shift_performance']
    for alan in ('time', 'of_ratio', 'c_star', 'isp'):
        assert isinstance(perf[alan], list) and perf[alan]
    assert perf['summary_block'] == 'of_shift'
    reg = sonuc['of_shift']['regulated']
    assert perf['isp_delta_vs_design_pct'] == reg['isp_delta_vs_design_pct']
    assert perf['total_impulse_Ns'] == reg['total_impulse_Ns']


def test_izleme_kapaliyken_sayi_uydurulmuyor():
    """track_performance kapalıyken regüleli durum SAYI ÜRETMEZ, gerekçe verir."""
    _, sonuc = _kos(track_performance=False)
    blok = sonuc['of_shift']
    reg = blok['regulated']
    assert reg['status'] == 'NOT_MODELLED'
    assert reg['reason']
    assert 'isp_mass_avg_s' not in reg and 'total_impulse_Ns' not in reg
    # Blowdown durumu bağımsız çözüldüğü için yine yayımlanır (var olan bir
    # hesabı saklamak da bir tür sessizliktir)
    assert blok['blowdown'].get('status') != 'NOT_MODELLED'
    assert blok['status'] == 'modelled'


# ---------------------------------------------------------------------------
# 6. Uyarı: eşik TEK yerde, aşılınca çıkar, altında çıkmaz
# ---------------------------------------------------------------------------

def _uyarilar(sonuc):
    return [k for k in sonuc['design_warnings'] if k.get('code') == UYARI_KODU]


def test_uyari_esik_ustunde_cikiyor(ussu_yuksek):
    motor, sonuc = ussu_yuksek
    blok = sonuc['of_shift']
    # Önkoşul gerçek: bu motor gerçekten eşiği aşıyor
    assert blok['regulated']['of_shift_fraction'] > OF_SHIFT_WARN_FRACTION
    kayitlar = _uyarilar(sonuc)
    assert len(kayitlar) == 1, 'tek bir O/F kayması uyarısı beklenir'
    kayit = kayitlar[0]
    assert kayit['severity'] == 'warning'
    p = kayit['params']
    # Eşik TEK kaynaktan yayımlanır (kopya eşik yasak)
    assert p['threshold_pct'] == pytest.approx(OF_SHIFT_WARN_FRACTION * 100.0)
    # Değerler bloğun kendi sayılarından gelir, uydurulmaz
    assert p['of_design'] == pytest.approx(motor.OF, abs=0.005)
    assert p['shift_pct'] == pytest.approx(
        blok['regulated']['of_shift_fraction'] * 100.0, abs=0.05)
    assert p['of_max'] == pytest.approx(
        blok['regulated']['of_ratio_max'], abs=0.005)
    assert p['isp_delta_pct'] == pytest.approx(
        blok['regulated']['isp_delta_vs_design_pct'], abs=0.005)
    assert p['feed_mode'] in ('regulated', 'blowdown')


def test_uyari_esik_altinda_cikmiyor(varsayilan):
    _, sonuc = varsayilan
    blok = sonuc['of_shift']
    # Önkoşul gerçek: hem regüleli hem blowdown eşiğin altında
    assert blok['regulated']['of_shift_fraction'] <= OF_SHIFT_WARN_FRACTION
    assert blok['blowdown']['of_shift_fraction'] <= OF_SHIFT_WARN_FRACTION
    assert not _uyarilar(sonuc), 'eşiğin altındaki motor uyarı almamalı'


def test_uyari_kodu_warn_onekli_ve_sozlesmeye_uygun(ussu_yuksek):
    """Kod ``warn.`` önekli ve {code, params, severity} sözleşmesinde."""
    _, sonuc = ussu_yuksek
    kayit = _uyarilar(sonuc)[0]
    assert kayit['code'].startswith('warn.hybrid.')
    assert set(kayit) == {'code', 'params', 'severity'}
    assert set(kayit['params']) == {
        'feed_mode', 'of_design', 'of_min', 'of_max', 'shift_pct',
        'threshold_pct', 'isp_delta_pct'}
    # Yer tutucuya girecek her değer basılabilir olmalı (ekranda "None" yasak)
    assert all(v is not None for v in kayit['params'].values())


def test_uyari_tekrar_derlemede_cogalmiyor(ussu_yuksek):
    """_compile_results birden çok kez çağrılabilir; uyarı iki kez eklenmez."""
    motor, _ = ussu_yuksek
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        tekrar = motor._compile_results()
    assert len(_uyarilar(tekrar)) == 1


# ---------------------------------------------------------------------------
# 7. A10 beyanları: O/F kayması artık modelleniyor
# ---------------------------------------------------------------------------

def test_beyanlar_of_kaymasini_modellenmiyor_ilan_etmiyor(varsayilan):
    """Çürümüş beyan taşınmaz: O/F kayması hesaplanan bir kalem.

    A9 öncesi hibrit beyan listesinde O/F kaymasına dair bir NOT_MODELLED
    kalemi YOKTU (2026-08-05 taraması), yani düşürülecek beyan çıkmadı. Bekçi
    bunun geri gelmemesini sağlar: ileride "O/F shift not modelled" gibi bir
    beyan eklenirse bu sınama düşer.
    """
    _, sonuc = varsayilan
    for ad, metin in sonuc['not_modelled'].items():
        dusuk = metin.lower()
        assert not ('o/f' in dusuk and 'shift' in dusuk), (
            f'"{ad}" beyanı O/F kaymasının modellenmediğini söylüyor, oysa '
            f'of_shift bloğu onu hesaplıyor')
    assert sonuc['of_shift']['status'] == 'modelled'


def test_yeni_alanlar_json_serilestirilebilir(varsayilan):
    """Yeni bloklar yanıt sözleşmesini bozmaz (Flask jsonify yolu)."""
    _, sonuc = varsayilan
    json.dumps({'of_shift': sonuc['of_shift'],
                'of_shift_performance': sonuc['of_shift_performance'],
                'tank_blowdown': sonuc['tank_blowdown'],
                'design_warnings': sonuc['design_warnings']})
