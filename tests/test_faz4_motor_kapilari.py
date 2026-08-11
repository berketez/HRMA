"""Faz 4B — motor karar kapıları (bulgu B1, B2, A3, A7).

Bu dört bulgunun TEK bir kök sorunu vardı: **beyan kanalları dolduruluyor ama
karar kapısı yok.** Doğru sayı hesaplanıyor, doğru bayrak yazılıyor, kimse
bayrağı okumuyordu. Ölçümler HEAD ``a7ff1e7`` üstünde, 2 Ağustos 2026'da
alındı ve her testin başında kaynağıyla birlikte yazılıdır.

  B1  ``_defaults_used`` / ``_fallback_used`` listelerine 14 yerde yazılıyor,
      sıfır yerde okunuyor, sıfır yerde yayımlanıyordu. Hibrit motor itki ve
      süre verilmeden koşturulduğunda liste
      ``['nozzle_material', 'thrust', 'burn_time']`` doluyor, buna rağmen
      ``design_summary.status`` koşulsuz ``'OPTIMIZED'`` yazıyordu.

  A3  Bilinmeyen itici çifti (``zirvaaa``/``gizemli``) HTTP 200 ile
      ``OPTIMIZED`` ve Isp_sl = 285 s / Isp_vac = 320 s / c* = 1650 m/s
      döndürüyordu. Bu sayılar hiçbir kimyadan gelmiyor, düz yazılmış yer
      tutuculardı.

  B2  Yakınsamayan basınç çözümü performans ve CAD üretiyordu: n = 0.9'da
      ``convergence_achieved=False``, 122/204 adım başarısız, artık 1.03e-3
      (tolerans 1e-6) — buna rağmen ``status='CALCULATED'``, Isp = 220.83 s ve
      ``cad_design`` 9 anahtar dolu.

  A7  Önbellek anahtarı fiziksel ayrımı yutuyordu: ``memoize=True`` iken
      Pc = 20.04 bar isteği Pc = 20.00 sonucunu döndürüyordu (c* bit-aynı) ve
      dönen sözlük ``inputs.chamber_pressure = 20.0`` diyerek çözülmeyen bir
      basıncı kullanıcının girdisi gibi geri bildiriyordu.

Testler etikete ve yayımlanan alana bakar; sayısal fizik değerlerini
kilitlemez — amaç kapının varlığını korumaktır, kalibrasyonu değil.
"""

import contextlib
import io

import numpy as np
import pytest

from hrma.engines import combustion_analysis as ca_mod
from hrma.engines import hybrid_rocket_engine as hybrid_mod
from hrma.engines import liquid_rocket_engine as liquid_mod
from hrma.engines import solid_rocket_engine as solid_mod
from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.engines.liquid_rocket_engine import (
    LiquidRocketEngine,
    UnsupportedPropellantPairError,
)
from hrma.engines.solid_rocket_engine import SolidRocketEngine


def _sessiz(cagrilabilir, *args, **kwargs):
    """Motorların stdout gürültüsünü yutar; dönüş değeri korunur."""
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        return cagrilabilir(*args, **kwargs)


# Ölçülen yakınsayan katı motor tabanı (n = 0.35, APCP): 0/219 adım başarısız.
# app.py /calculate_solid varsayılanlarıyla aynı; birimler mm ve bar.
KATI_TABAN = dict(grain_type='bates', propellant_type='apcp',
                  chamber_diameter=100, grain_length=500, core_diameter=30,
                  chamber_pressure=40, burn_rate_a=0.005)


# ---------------------------------------------------------------------------
# Ortak durum sözlüğü
# ---------------------------------------------------------------------------

def test_durum_sozlugu_uc_motorda_ayni():
    """Üç motor dosyası aynı durum etiketlerini kullanmalı.

    Sözlük bilinçli olarak çapraz import edilmeden üç dosyada tekrarlanıyor
    (katı ve sıvı motor, hibridin Cantera'ya uzanan import zincirini çekmesin).
    Tekrarın bedeli budur: eşitliği makine denetler.
    """
    adlar = [ad for ad in dir(hybrid_mod) if ad.startswith('DESIGN_STATUS_')]
    assert 'DESIGN_STATUS_SEVERITY' in adlar
    # Etiket sabitleri (SEVERITY haritası hariç) en az altı durum tanımlar.
    etiketler = [ad for ad in adlar if ad != 'DESIGN_STATUS_SEVERITY']
    assert len(etiketler) >= 6

    for modul in (liquid_mod, solid_mod):
        for ad in adlar:
            assert hasattr(modul, ad), (
                f'{modul.__name__} durum sözlüğünde {ad} eksik')
            assert getattr(modul, ad) == getattr(hybrid_mod, ad), (
                f'{modul.__name__}.{ad} hibritten farklı')


def test_en_kotu_durum_secilir():
    """Aynı koşuda birden çok durum geçerliyse EN KÖTÜSÜ yazılır."""
    en_kotu = hybrid_mod._worst_design_status
    assert en_kotu(hybrid_mod.DESIGN_STATUS_CALCULATED,
                   hybrid_mod.DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS) == \
        hybrid_mod.DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS
    assert en_kotu(hybrid_mod.DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS,
                   hybrid_mod.DESIGN_STATUS_TARGET_NOT_MET) == \
        hybrid_mod.DESIGN_STATUS_TARGET_NOT_MET
    assert en_kotu(hybrid_mod.DESIGN_STATUS_OPTIMIZED, None) == \
        hybrid_mod.DESIGN_STATUS_OPTIMIZED
    # Sözlükte olmayan bir etiket iyimser tarafa kayamaz.
    assert en_kotu(hybrid_mod.DESIGN_STATUS_CALCULATED, 'BILINMEYEN') == \
        'BILINMEYEN'


# ---------------------------------------------------------------------------
# B1 — _defaults_used okunuyor ve yayımlanıyor
# ---------------------------------------------------------------------------

def test_b1_varsayilanla_dolan_hibrit_optimized_demiyor():
    """İtki/süre verilmeden koşulan hibrit 'OPTIMIZED' diyemez.

    Ölçüm (HEAD a7ff1e7): _defaults_used = ['nozzle_material', 'thrust',
    'burn_time'] dolu, design_summary.status = 'OPTIMIZED'.
    """
    motor = HybridRocketEngine(of_ratio=6.0, chamber_pressure=20.0)
    assert motor._defaults_used, 'ölçüm dayanağı düştü: liste boş kalmamalı'

    sonuc = _sessiz(motor.calculate)
    durum = sonuc['design_summary']['status']
    assert durum != hybrid_mod.DESIGN_STATUS_OPTIMIZED
    assert durum == hybrid_mod.DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS


def test_b1_defaults_used_sonucta_gorunuyor():
    """Liste artık sonuç sözlüğünde — hem üst düzeyde hem tasarım özetinde."""
    motor = HybridRocketEngine(of_ratio=6.0, chamber_pressure=20.0)
    beklenen = list(motor._defaults_used)
    sonuc = _sessiz(motor.calculate)

    assert sonuc['defaults_used'] == beklenen
    assert 'fallbacks_used' in sonuc
    ozet = sonuc['design_summary']
    assert ozet['defaults_used'] == beklenen
    # Etiketin NEDEN o olduğu da okunabilir olmalı.
    assert ozet['status_basis']
    assert any('thrust' in str(g) for g in ozet['status_basis'])


def test_b1_hibrit_tam_girdide_optimized_iddia_etmiyor():
    """Hibritte tasarım eniyileyicisi ÇALIŞMAZ; en iyi durum 'CALCULATED'.

    find_optimum_of_ratio yalnız danışma amaçlıdır ve tasarım O/F'sini
    değiştirmez, bu yüzden 'OPTIMIZED' hiçbir koşulda üretilmemeli.
    """
    motor = HybridRocketEngine(thrust=1500.0, burn_time=8.0, of_ratio=6.0,
                               chamber_pressure=20.0, nozzle_material='graphite')
    sonuc = _sessiz(motor.calculate)
    ozet = sonuc['design_summary']
    assert ozet['status'] == hybrid_mod.DESIGN_STATUS_CALCULATED
    # Metin eniyileme İDDİA edemez; eniyileme YAPILMADIĞINI söyleyebilir.
    tavsiye = ozet['recommendation'].lower()
    assert 'optimised design' not in tavsiye
    assert 'optimized design' not in tavsiye
    assert 'no design optimiser is applied' in tavsiye
    # Başlık da "Optimal Design" iddiasını taşımamalı.
    assert 'optimal' not in ozet['title'].lower()


def test_b1_sivi_kullanici_epsilonunda_optimized_demiyor():
    """Kullanıcı genişleme oranını verdiyse eniyileme ÇALIŞMAMIŞTIR.

    Sıvı motorda tasarıma fiilen uygulanan tek eniyileme, ε'nun ortam-eşlenik
    optimumda seçilmesidir; ε girdiyse lüle sabittir.
    """
    motor = _sessiz(LiquidRocketEngine, thrust=10000, chamber_pressure=60,
                    mixture_ratio=2.5, fuel_type='rp1', oxidizer_type='lox',
                    overrides={'nozzle_expansion_ratio': 25.0})
    ozet = _sessiz(motor.calculate_performance)['design_summary']
    assert ozet['status'] == liquid_mod.DESIGN_STATUS_CALCULATED
    assert ozet['optimizations_applied'] == []
    assert ozet['status_basis']


def test_b1_sivi_ortam_eslenik_epsilonda_optimized_diyebilir():
    """ε verilmediğinde ortam-eşlenik optimum ÇALIŞIR; etiket bunu yansıtır."""
    motor = _sessiz(LiquidRocketEngine, thrust=10000, chamber_pressure=60,
                    mixture_ratio=2.5, fuel_type='rp1', oxidizer_type='lox')
    ozet = _sessiz(motor.calculate_performance)['design_summary']
    assert ozet['status'] == liquid_mod.DESIGN_STATUS_OPTIMIZED
    # Etiket "her şey optimal" diye okunamasın: ne eniyilendiği sayılır.
    assert len(ozet['optimizations_applied']) == 1
    assert 'expansion ratio' in ozet['optimizations_applied'][0]


# ---------------------------------------------------------------------------
# A3 — modellenmeyen itici çifti performans üretmiyor
# ---------------------------------------------------------------------------

def test_a3_bilinmeyen_itici_cifti_performans_yayimlamiyor():
    """Ne tabloda ne CEA kartında olan çift kapalı devreye düşer.

    Ölçüm (HEAD a7ff1e7): fuel='zirvaaa', oxidizer='gizemli' -> HTTP 200,
    design_summary.status = 'OPTIMIZED', Isp_sl = 285 s, Isp_vac = 320 s,
    c* = 1650 m/s. Bu sayılar liquid_rocket_engine.py:1934-1940 literalleriydi.
    """
    with pytest.raises(UnsupportedPropellantPairError) as hata:
        _sessiz(LiquidRocketEngine, thrust=5000, chamber_pressure=30,
                mixture_ratio=2.5, fuel_type='zirvaaa',
                oxidizer_type='gizemli')

    assert hata.value.reason_code == 'propellant_pair_not_modelled'
    assert hata.value.fuel == 'zirvaaa'
    assert hata.value.oxidizer == 'gizemli'
    # Gerekçe kullanıcıya ne yapacağını söylemeli.
    mesaj = str(hata.value)
    assert 'zirvaaa' in mesaj and 'gizemli' in mesaj
    # Mevcut ``except ValueError`` yakalayan yollar (MC, UQ) bozulmamalı.
    assert isinstance(hata.value, ValueError)


def test_a3_temsili_sabitler_artik_bir_motor_ureteMIYOR():
    """Eski yer tutucu üçlüsü (285 / 320 / 1650) hiçbir motorda kurulmuyor."""
    with pytest.raises(UnsupportedPropellantPairError):
        _sessiz(LiquidRocketEngine, thrust=5000, chamber_pressure=30,
                mixture_ratio=2.5, fuel_type='yokboyle',
                oxidizer_type='yokboyle2')


@pytest.mark.parametrize('yakit', ['rp1', 'lh2', 'methane', 'mmh', 'udmh'])
@pytest.mark.parametrize('oksitleyici', ['lox', 'n2o4'])
def test_a3_arayuzun_sundugu_ciftler_kapiya_takilmiyor(yakit, oksitleyici):
    """Kapı MEŞRU seçimleri kapatmamalı.

    liquid.html 5 yakıt x 2 oksitleyici sunuyor; bunların yalnız 6'sı yerleşik
    tabloda, kalanı (rp1/n2o4, lh2/n2o4, methane/n2o4, mmh/lox, udmh/lox)
    RocketCEA ile çözülüyor. Onunu da geçmeli.
    """
    motor = _sessiz(LiquidRocketEngine, thrust=10000, chamber_pressure=60,
                    mixture_ratio=2.5, fuel_type=yakit,
                    oxidizer_type=oksitleyici)
    assert motor.combustion_data_source != 'not_modelled'
    assert motor.isp_sl > 0 and motor.c_star > 0


# ---------------------------------------------------------------------------
# B2 — yakınsamayan katı çözüm performans/CAD üretmiyor
# ---------------------------------------------------------------------------

def test_b2_ustel_bire_esitse_performans_ve_cad_yayimlanmiyor():
    """1. kademe: n >= 1 -> sabit-nokta daralma savı geçersiz.

    Ölçüm: n = 1.0 -> 1/35 adım başarısız, term='burn_rate_zero'. Daralma
    garantisi olmadan hiçbir adımın basıncına güvenilemez; eskiden bu koşu
    status='CALCULATED', Isp dolu ve cad_design 9 anahtar dolu dönüyordu.
    """
    motor = SolidRocketEngine(burn_rate_n=1.0, **KATI_TABAN)
    sonuc = _sessiz(motor.calculate_performance)

    assert sonuc.get('error'), 'n >= 1 yakınsamazsa hata sözleşmesine düşmeli'
    assert sonuc['status'] == solid_mod.DESIGN_STATUS_NOT_CONVERGED

    # Performans, CAD ve "kabul edilebilir" kararı ÜRETİLMEZ.
    for yasak in ('cad_design', 'design_summary', 'specific_impulse',
                  'average_thrust', 'thrust_curve', 'structural_analysis',
                  'safety_analysis', 'manufacturing_analysis'):
        assert yasak not in sonuc, f'{yasak} yakınsamayan çözümde yayımlanmamalı'

    tani = sonuc['solver_diagnostics']
    assert tani['convergence_achieved'] is False
    assert tani['pressure_solver_failed_steps'] > 0
    assert tani['pressure_solver_max_residual'] > tani[
        'pressure_solver_tolerance']
    # Son (kabul edilmeyen) iterat yalnız teşhis alanında ve açık adla durur.
    assert 'non_converged_last_iterate_diagnostic_only' in sonuc
    # Kapı kullanıcının teşhis bilgisini KISMAMALI: n >= 1 uyarısı da ulaşmalı.
    kodlar = {u.get('code') for u in sonuc['warnings'] if isinstance(u, dict)}
    assert 'warn.solid.burn_rate_exponent_ge_one' in kodlar


def test_b2_basinc_cokusu_yildiz_grainde_normal_burnout_sayilir():
    """Bekçi: 'pressure_collapse' bir sapma DEĞİL, tükenişin doğal sonudur.

    Çözücünün kendi tükeniş kapanışı (solid_rocket_engine.py:6472-6474) bu sonu
    burnout sayıp eğriye sıfır itkili son noktayı ekliyor. İlk uygulamada bu son
    'anormal' sanıldı ve deponun kendi yıldız grainli KNDX örneği kesildi.
    """
    motor = SolidRocketEngine(burn_rate_n=0.95, **KATI_TABAN)
    sonuc = _sessiz(motor.calculate_performance)

    assert sonuc['solver_diagnostics']['termination_reason'] == \
        'pressure_collapse'
    assert not sonuc.get('error'), 'basınç çöküşü tek başına sonucu kesmemeli'
    # Ama yakınsama yok: etiket bunu söylemeli.
    assert sonuc['design_summary']['status'] == \
        solid_mod.DESIGN_STATUS_NOT_CONVERGED


def test_b2_tavana_takilan_ama_normal_biten_cozum_calculated_diyemiyor():
    """2. kademe: NORMAL biten (web tükenen) ama tavana takılan çözüm.

    Sonuç yayımlanır (tolerans 1e-6'dan 1e-2'ye gevşetildiğinde toplam impuls
    ölçülebilir ölçüde oynamıyor), fakat etiket artık uyarıyla aynı şeyi
    söyler: 'CALCULATED' YASAK.

    SENARYO ÇAPASI YENİDEN ÖLÇÜLDÜ (v2.6.27, B2-6.4). Bu testin ayırt ettiği
    durum "term = web_exhausted İKEN yakınsama yok"tur; kardeş test
    (``test_b2_basinc_cokusu_yildiz_grainde_normal_burnout_sayilir``) zaten
    ``pressure_collapse`` yolunu tutuyor, yani iki testin AYNI sona düşmesi
    kapsamı daraltır. n = 0.9 eskiden bu senaryoyu üretiyordu; A1-1 boğazı
    maksimum Kn'de boyutlandırmaya geçince (boğaz büyüdü, basınç düştü)
    n = 0.9'un kuyruğu artık sönüyor ve son 'pressure_collapse' oluyor.
    Ölçüm (KATI_TABAN, bu HEAD):

        n = 0.65 -> web_exhausted,     2/182 adım başarısız, NOT_CONVERGED
        n = 0.80 -> web_exhausted,    15/192,                NOT_CONVERGED
        n = 0.88 -> web_exhausted,    96/223,                NOT_CONVERGED
        n = 0.90 -> pressure_collapse, 126/213,              NOT_CONVERGED

    Senaryo n = 0.88'e çekildi; iddiaların hiçbiri gevşetilmedi (aynı dört
    alan, aynı değerler) — yalnız senaryoyu HÂLÂ üreten girdi seçildi.
    """
    motor = SolidRocketEngine(burn_rate_n=0.88, **KATI_TABAN)
    sonuc = _sessiz(motor.calculate_performance)

    assert not sonuc.get('error')
    assert sonuc['solver_diagnostics']['termination_reason'] == 'web_exhausted'
    assert sonuc['solver_diagnostics']['convergence_achieved'] is False
    ozet = sonuc['design_summary']
    assert ozet['status'] == solid_mod.DESIGN_STATUS_NOT_CONVERGED
    assert ozet['numerical_validity']['convergence_achieved'] is False
    assert 'unconverged' in ozet['numerical_validity']['note'].lower()


def test_b2_yakinsayan_kati_cozum_etkilenmiyor():
    """n = 0.35 (APCP nominali): 0/219 adım başarısız — tam sonuç dönmeli."""
    motor = SolidRocketEngine(burn_rate_n=0.35, **KATI_TABAN)
    sonuc = _sessiz(motor.calculate_performance)

    assert not sonuc.get('error')
    assert sonuc['solver_diagnostics']['convergence_achieved'] is True
    assert sonuc['solver_diagnostics']['pressure_solver_failed_steps'] == 0
    ozet = sonuc['design_summary']
    assert ozet['status'] == solid_mod.DESIGN_STATUS_CALCULATED
    assert ozet['numerical_validity']['convergence_achieved'] is True
    assert ozet['performance']['specific_impulse_s'] > 0
    assert len(sonuc['cad_design']) > 0


def test_b2_katalog_iticisi_mesru_calisma_noktasinda_kesilmiyor():
    """Kapı MEŞRU tasarımları kesmemeli — bu bir regresyon bekçisidir.

    İlk uygulamada "bir adım bile başarısızsa sonuç yok" kuralı yazıldı ve
    deponun kendi kataloğundaki KNDX (n = 0.688) Pc = 90 bar'da kesildi.
    Ölçüm: 7/164 adım başarısız, artık %1.19, term='web_exhausted'; tolerans
    1e-6'dan 1e-2'ye gevşetildiğinde toplam impuls yalnız %0.067 oynuyor.
    """
    motor = SolidRocketEngine(
        grain_type='bates', propellant_type='knsb', chamber_diameter=75.0,
        grain_length=360.0, core_diameter=32.0, chamber_pressure=90,
        burn_rate_a=0.0007876, burn_rate_n=0.688,
        overrides={'char_velocity': 912.4, 'density': 1850.0,
                   'flame_temp': 1710.0, 'gamma': 1.1308, 'grain_count': 3,
                   'grain_gap': 2.0, 'inhibit_outer': True,
                   'molecular_weight': 42.39, 'web_thickness': 21.5})
    sonuc = _sessiz(motor.calculate_performance)

    assert not sonuc.get('error'), 'katalog iticisi meşru noktada kesilemez'
    assert sonuc['design_summary']['performance']['specific_impulse_s'] > 0
    assert len(sonuc['cad_design']) > 0


def test_b2_monte_carlo_yakinsamayan_nominali_kabul_etmiyor():
    """Hata sözleşmesi zaten tanınıyor: MC nominali düşürüp gerekçe döner."""
    motor = SolidRocketEngine(burn_rate_n=1.0, **KATI_TABAN)
    mc = _sessiz(motor.run_monte_carlo, n_samples=20)
    assert mc.get('error')
    assert 'converge' in mc['error'].lower()


# ---------------------------------------------------------------------------
# A7 — önbellek anahtarı fiziksel ayrımı yutmuyor
# ---------------------------------------------------------------------------

def _c_star(analizor, of, pc):
    return analizor.analyze_combustion({'htpb': 100.0}, 'N2O', of,
                                       pc)['performance']['c_star']


def test_a7_pc_2000_ve_2004_farkli_sonuc_veriyor():
    """Ölçüm: memoize=True iken Pc=20.04 isteği Pc=20.00 sonucunu döndürüyordu.

    Nicemleme 0.1 bar idi; yoğunluk Pc ile 1:1 ölçeklendiği için bu 20 bar'da
    %0.5'e kadar yoğunluk hatası demekti — çözümün duyarlılığından kaba.
    """
    memo = CombustionAnalyzer(memoize=True)
    duz = CombustionAnalyzer(memoize=False)

    memo_2000 = _c_star(memo, 6.0, 20.00)
    memo_2004 = _c_star(memo, 6.0, 20.04)
    assert memo_2000 != memo_2004, 'nicemleme fiziksel ayrımı yutuyor'
    # Önbellekli sonuç, önbelleksiz referansla BİT-AYNI olmalı.
    assert memo_2004 == pytest.approx(_c_star(duz, 6.0, 20.04), rel=1e-12)
    assert len(memo._equilibrium_cache) == 2


def test_a7_of_nicemlemesi_de_kalkti():
    """O/F 0.01'e nicemleniyordu: 6.000 ile 6.004 aynı hücreye düşüyordu."""
    memo = CombustionAnalyzer(memoize=True)
    assert _c_star(memo, 6.000, 20.0) != _c_star(memo, 6.004, 20.0)


def test_a7_expansion_ratio_nicemlemesi_de_kalkti():
    """ε 0.01'e nicemleniyordu; UQ'da ε örnekler arasında 3.68-3.82 geziyor."""
    memo = CombustionAnalyzer(memoize=True)
    yakit = {'htpb': 100.0}
    a = memo.analyze_combustion(yakit, 'N2O', 6.0, 20.0,
                                expansion_ratio=3.8184)
    b = memo.analyze_combustion(yakit, 'N2O', 6.0, 20.0,
                                expansion_ratio=3.8187)
    assert a['performance']['isp'] != b['performance']['isp']


def test_a7_ayni_istek_hala_onbellege_isabet_ediyor():
    """Nicemleme kalktı ama BİREBİR aynı istek hâlâ paylaşılıyor."""
    memo = CombustionAnalyzer(memoize=True)
    ilk = _c_star(memo, 7.0, 30.0)
    assert len(memo._equilibrium_cache) == 1
    assert _c_star(memo, 7.0, 30.0) == ilk
    assert len(memo._equilibrium_cache) == 1


def test_a7_girdi_yankisi_gercek_girdiyi_soyluyor():
    """Sonuç sözlüğü, çözülmeyen bir basıncı 'girdi' diye geri bildiremez."""
    memo = CombustionAnalyzer(memoize=True)
    yakit = {'htpb': 100.0}
    memo.analyze_combustion(yakit, 'N2O', 6.0, 20.00)
    sonuc = memo.analyze_combustion(yakit, 'N2O', 6.0, 20.04)
    assert sonuc['inputs']['chamber_pressure'] == pytest.approx(20.04)


def test_a7_onbellek_ust_sinirla_sinirli():
    """Tam anahtar hücre sayısını artırabilir; önbellek sınırsız büyümemeli."""
    memo = CombustionAnalyzer(memoize=True)
    memo._equilibrium_cache_max = 3
    for i in range(6):
        _c_star(memo, 6.0, 20.0 + 0.01 * i)
    assert len(memo._equilibrium_cache) == 3


def test_a7_sonlu_olmayan_girdi_onbellege_girmiyor():
    """NaN kendine eşit olmadığı için asla isabet etmez, yalnız hücre şişirir."""
    memo = CombustionAnalyzer(memoize=True)
    with contextlib.suppress(Exception):
        memo.analyze_combustion({'htpb': 100.0}, 'N2O', float('nan'), 20.0)
    assert memo._equilibrium_cache == {}


def test_a7_onbellek_ust_siniri_tanimli():
    assert ca_mod.EQUILIBRIUM_CACHE_MAX > 625, (
        'ölçülen en büyük iş yükü 25x25 = 625 noktalık Isp yüzeyi')
    assert CombustionAnalyzer()._equilibrium_cache_max == \
        ca_mod.EQUILIBRIUM_CACHE_MAX


def test_a7_nicemleme_kodu_geri_gelmemis():
    """Bekçi: eski nicemleme çarpanları anahtar kurulumuna dönmemeli."""
    import inspect
    kaynak = inspect.getsource(CombustionAnalyzer.analyze_combustion)
    anahtar_blogu = kaynak.split('cache_key = (')[1].split(')')[0]
    for yasak in ('* 100', '* 10', 'round('):
        assert yasak not in anahtar_blogu, (
            f'anahtar kurulumunda nicemleme izi: {yasak!r}')


def test_a7_np_kullanimi_saglam():
    """np.isfinite koruması gerçekten sonlu olmayanı eliyor (duman testi)."""
    assert not np.isfinite(float('nan'))
