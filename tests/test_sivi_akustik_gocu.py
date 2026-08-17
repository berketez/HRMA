"""F2b-2 — sıvı akustiğinin merkeze GÖÇÜ: manifesto bekçisi (KARAR 8).

NE KORUR
--------
Sıvı motor, kamara akustiğini KENDİ İÇİNDE hesaplıyordu: 1L için ``a/(2L)``,
1T için elle yazılmış ``FIRST_TANGENTIAL_MODE_COEFF = 1.8412``. Hibrit ve katı
çözücüler aynı sayıları merkezî ``hrma.analysis.acoustic_modes``ten alıyordu.
Yani depoda akustiğin iki tanımı vardı ve üç motordan biri kendi kopyasını
kullanıyordu (tasarım belgesi §1.1-2, ÖLÇÜLDÜ).

Göç yapıldı. Tasarım belgesi §8.1 KARAR 8'in sözleşmesi şudur:

    "değişiklik serbest" DEĞİL, "AÇIKLANMIŞ değişiklik serbest".

Bu dosya o sözleşmeyi mekanik hâle getirir. Göç ÖNCESİ yayımlanan her sayı
``ESKI_YEREL`` tablosunda dondurulmuştur (göçten önce, ürün koduyla ölçüldü);
her test bugünkü merkezî değeri ölçer ve

    old_local -> new_central -> delta_absolute -> delta_relative -> reason

satırını üretir. Fark BEKLENEN model farkıyla (aşağıda ``reason``) uyuşmuyorsa
test KIRMIZI olur. Yani bu bekçi "sayı değişmesin" demez — "sayı, adı konmuş
bir sebep olmadan değişmesin" der.

ÖLÇÜLEN İKİ SINIF (17 Ağustos 2026)
-----------------------------------
1. **1L, ΔP/Pc oranı, tepki süresi: BİT-ÖZDEŞ.** Merkezî
   ``longitudinal_frequency(a, L, 1)`` ile eski ``a/(2L)`` aynı ifadedir ve
   girdiler de aynı kalmıştır (aynı geometri kaynağı, aynı ses hızı, mm->m
   dönüşümü YOK — ikisi de metre kullanıyordu). Bu bir varsayım değil,
   ``repr`` düzeyinde ölçümdür.
2. **1T: bağıl −8,80874e-06.** Tek sebep kökün nereden geldiğidir: eski yerel
   sabit 1,8412 (beş haneye yuvarlanmış), merkez ise J'_1'in ilk sıfırını
   ``scipy.special.jnp_zeros`` ile üretiyor (1,8411837813406593). Fark
   MOTORDAN BAĞIMSIZDIR ve üç vakada da aynı çıkar; testi bu değişmezlik
   üstüne kuruyoruz (vaka başına ayrı bir "yakınsa geçer" toleransı değil).

NİYE FIXTURE'LAR PAHALI DEĞİL: motorun tam çözümü ~3 s sürer; üç vaka modül
kapsamında BİR kez koşulur.
"""

import math
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.analysis.acoustic_modes import (          # noqa: E402
    longitudinal_frequency,
    transverse_frequency,
    transverse_root,
)
from hrma.engines.liquid_rocket_engine import LiquidRocketEngine  # noqa: E402

# ---------------------------------------------------------------------------
# Göç öncesi ANLIK GÖRÜNTÜ (KARAR 8). Bu sayılar 17 Ağustos 2026'da, göç
# yapılmadan ÖNCE, ürün kodunun kendisiyle ölçüldü (HEAD 9946c70). Elle
# yazılmadılar; çözücünün çıktısından alındılar.
#
# Vaka kurucuları da buradadır: fixture ile snapshot AYNI yerde durmalı,
# yoksa biri değişip diğeri kalır ve manifest sessizce anlamını yitirir.
# ---------------------------------------------------------------------------
ESKI_YEREL = {
    'rp1_lox_impinging': {
        'kurucu': dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
                       fuel_type='rp1', oxidizer_type='lox',
                       cooling_type='regenerative',
                       injector_type='impinging'),
        'first_longitudinal_hz': 6300.001106374788,
        'first_tangential_hz': 7292.72506500461,
        'acoustic_frequency': 6300.001106374788,
        'injector_dp_over_pc': 0.22,
        'combustion_response_time': 3.1761636471824786,
        'chug_rating': 'chug_margin_ok',
    },
    'ch4_lox_coaxial': {
        'kurucu': dict(thrust=25000, chamber_pressure=60, mixture_ratio=3.2,
                       fuel_type='methane', oxidizer_type='lox',
                       cooling_type='regenerative', injector_type='coaxial'),
        'first_longitudinal_hz': 6398.1396323450135,
        'first_tangential_hz': 3494.80642934932,
        'acoustic_frequency': 6398.1396323450135,
        'injector_dp_over_pc': 0.18,
        'combustion_response_time': 18.292131012133765,
        'chug_rating': 'chug_margin_marginal',
    },
    'rp1_lox_pintle': {
        'kurucu': dict(thrust=5000, chamber_pressure=40, mixture_ratio=2.3,
                       fuel_type='rp1', oxidizer_type='lox',
                       cooling_type='ablative', injector_type='pintle'),
        'first_longitudinal_hz': 6311.624758261385,
        'first_tangential_hz': 6221.687285694832,
        'acoustic_frequency': 6311.624758261385,
        'injector_dp_over_pc': 0.15,
        'combustion_response_time': 9.251204015280306,
        'chug_rating': 'chug_margin_marginal',
    },
}

#: Manifestte "bit-özdeş" beklenen yapraklar ve gerekçeleri.
BIT_OZDES = {
    'first_longitudinal_hz': (
        'same expression (q*a/(2L) with q=1), same inputs: the geometry '
        'source did not change and both sides already worked in metres'),
    'acoustic_frequency': (
        'legacy alias of first_longitudinal_hz; it must move with it'),
    'injector_dp_over_pc': (
        'the chug ratio never came from the acoustics module; only the '
        'threshold CONSTANTS were centralised, and their values are '
        'unchanged (0.20/0.15)'),
    'combustion_response_time': (
        'the sensitive time lag still comes from the injector atomisation '
        'solution; the migration did not touch it'),
}

#: 1T'nin BEKLENEN bağıl farkı: yuvarlanmış kök -> gerçek Bessel kökü.
ESKI_1T_KOKU = 1.8412
BEKLENEN_1T_DREL = (transverse_root(1, 0) - ESKI_1T_KOKU) / ESKI_1T_KOKU


def _koss(ad):
    kw = dict(ESKI_YEREL[ad]['kurucu'])
    eng = LiquidRocketEngine(**kw)
    res = eng.calculate_performance()
    return eng, res['combustion_analysis']['stability_analysis']


@pytest.fixture(scope='module')
def yeni_merkez():
    """Göç SONRASI yayımlanan kararlılık blokları (vaka -> blok)."""
    return {ad: _koss(ad)[1] for ad in ESKI_YEREL}


def manifest_satiri(ad, anahtar, eski, yeni):
    """old_local -> new_central -> Δabs -> Δrel (raporlanabilir tek satır)."""
    if isinstance(eski, (int, float)) and isinstance(yeni, (int, float)):
        d_abs = yeni - eski
        d_rel = d_abs / eski if eski else math.nan
        return (f'{ad}.{anahtar}: {eski!r} -> {yeni!r} | dabs={d_abs:.6g} | '
                f'drel={d_rel:.6g}')
    return f'{ad}.{anahtar}: {eski!r} -> {yeni!r} | (sayısal değil)'


# ===========================================================================
# 1) Bit-özdeş kalması GEREKEN yapraklar
# ===========================================================================
# Platform gürültü tabanı: ESKI_YEREL anlık görüntüsü arm64/Darwin'de ölçüldü
# (HEAD 9946c70); CI x86_64/Linux'ta aynı ifadeler libm/FMA/BLAS son-bit
# farkıyla değişik yuvarlanıyor. Ölçülen en büyük sapma 3,1e-13 bağıl
# (CI koşumu 32003781095: 6398,1396323450135 -> ...347029). Eşik o gürültünün
# ~3 katı, gerçek bir göç kaçağının (>=1e-6 sınıfı: çap kaynağı, ses hızı,
# formül değişimi) ise 6 dekad altındadır — bekçi ısırmaya devam eder
# (mutasyonla ölçüldü: 1,6e-5'lik oynama 2 testi kırmızı yakıyor).
# repr() tam eşitliği yalnız AYNI makinede anlamlıdır; platformlar arası
# sözleşme bu taban üzerinden kurulur.
PLATFORM_GURULTU_TABANI_REL = 1e-12


@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
@pytest.mark.parametrize('anahtar', sorted(BIT_OZDES))
def test_gocte_bit_ozdes_kalan_yapraklar(yeni_merkez, ad, anahtar):
    """Bu yapraklar DEĞİŞMEMELİ; değişirse sebebi manifestte yoktur.

    'Değişmedi' platformlar arası son-bit gürültü tabanına kadar tanımlıdır
    (PLATFORM_GURULTU_TABANI_REL); onun üstündeki her fark manifestte adı
    konmuş bir sebep ister.
    """
    eski = float(ESKI_YEREL[ad][anahtar])
    yeni = float(yeni_merkez[ad][anahtar])
    assert yeni == pytest.approx(eski, rel=PLATFORM_GURULTU_TABANI_REL), (
        'GÖÇ MANİFESTOSU İHLALİ (beklenmeyen fark)\n'
        + manifest_satiri(ad, anahtar, eski, yeni)
        + f'\nbeklenen sebep: {BIT_OZDES[anahtar]}\n'
        'Bu yaprağın değişmesi için manifeste ADI KONMUŞ bir sebep '
        'girilmelidir; sessiz sayı değişikliği yasaktır.')


@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
def test_chug_rating_gocte_degismedi(yeni_merkez, ad):
    """Oran kuralının HÜKMÜ göçten etkilenmemeli (eşik sayıları aynı)."""
    assert yeni_merkez[ad]['chug_rating'] == ESKI_YEREL[ad]['chug_rating']


# ===========================================================================
# 2) 1T: BEKLENEN fark — adı konmuş, motordan bağımsız
# ===========================================================================
@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
def test_1t_farki_yalnizca_bessel_kokunden(yeni_merkez, ad):
    """1T'nin bağıl farkı, kök yuvarlamasının farkına EŞİT olmalı.

    Bu, "yakın çıktı, geçer" testi değildir: fark tam olarak
    (jnp_zeros(1,1) − 1,8412)/1,8412 olmak zorundadır. Göçte başka bir şey de
    değişseydi (ör. çap kaynağı, ses hızı), bu eşitlik bozulurdu.
    """
    eski = ESKI_YEREL[ad]['first_tangential_hz']
    yeni = yeni_merkez[ad]['first_tangential_hz']
    d_rel = (yeni - eski) / eski
    # abs taban: yeni/eski'deki platform son-bit gürültüsü (<=3,1e-13 bağıl,
    # bkz. PLATFORM_GURULTU_TABANI_REL) d_rel'e ~1e-12 MUTLAK oynama taşır;
    # rel=1e-9 payı ise (BEKLENEN_1T_DREL ~ 8,8e-6 iken) 8,8e-15'te kalır ve
    # bunu örtmez. Gerçek bir kaçak d_rel'i >=1e-6 oynatır — bekçi ısırır.
    assert d_rel == pytest.approx(BEKLENEN_1T_DREL, rel=1e-9,
                                  abs=PLATFORM_GURULTU_TABANI_REL), (
        'GÖÇ MANİFESTOSU İHLALİ (fark beklenen sebeple açıklanmıyor)\n'
        + manifest_satiri(ad, 'first_tangential_hz', eski, yeni)
        + f'\nbeklenen drel={BEKLENEN_1T_DREL:.6g} '
        '(sebep: rounded 1.8412 -> scipy.special.jnp_zeros(1,1)[0])')


def test_1t_farki_motordan_bagimsiz(yeni_merkez):
    """Aynı bağıl fark ÜÇ vakada da aynı çıkmalı (sebep tek: kök).

    'Aynı' platform gürültü tabanına kadar: round(v, 12) kova sınırı motor
    başına ~1e-12'lik bağımsız son-bit gürültüsüyle iki motoru farklı kovaya
    düşürebilirdi (CI x86_64'te ölçülen sapma sınıfı); yayılım eşiği bu
    kırılganlığı taşımaz. Gerçek bir motor-bağımlı kaçak yayılımı >=1e-6
    sınıfına iter — bekçi ısırır.
    """
    farklar = {
        ad: (yeni_merkez[ad]['first_tangential_hz']
             - ESKI_YEREL[ad]['first_tangential_hz'])
        / ESKI_YEREL[ad]['first_tangential_hz']
        for ad in ESKI_YEREL}
    yayilim = max(farklar.values()) - min(farklar.values())
    assert yayilim <= 2 * PLATFORM_GURULTU_TABANI_REL, (
        f'1T farkı motora göre değişiyor -> sebep yalnız kök yuvarlaması '
        f'değil: {farklar} (yayılım {yayilim:.3g})')


def test_yuvarlanmis_kok_sabiti_geri_gelmesin():
    """1,8412 sıvı motorda BİR DAHA tanımlanmasın (kopya sabit öldü).

    Tarama AST üstünden yapılır, metin üstünden değil: docstring'ler ve
    yorumlar kökün TARİHÇESİNİ anlatmak zorundadır (ölçülen kusurun kaydı),
    ama KODDA sayısal sabit olarak geçemez. Dizge taraması bu ikisini
    ayıramaz ve tarihçeyi yazmayı cezalandırırdı.
    """
    import ast
    yol = os.path.join(REPO_ROOT, 'hrma', 'engines', 'liquid_rocket_engine.py')
    with open(yol, encoding='utf-8') as f:
        agac = ast.parse(f.read(), filename=yol)
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Constant) and isinstance(
                dugum.value, float) and abs(dugum.value - 1.8412) < 1e-9:
            pytest.fail(
                f'liquid_rocket_engine.py:{dugum.lineno} yuvarlanmış Bessel '
                f'kökünü ({dugum.value!r}) yeniden tanımlıyor. Kök merkezden '
                f'gelir (acoustic_modes.transverse_root).')
    assert not hasattr(
        sys.modules['hrma.engines.liquid_rocket_engine'],
        'FIRST_TANGENTIAL_MODE_COEFF'), (
        'FIRST_TANGENTIAL_MODE_COEFF geri gelmiş — kopya sabit yeniden '
        'doğdu.')


# ===========================================================================
# 3) Yeni değerler GERÇEKTEN merkezî modülden mi geliyor?
# ===========================================================================
@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
def test_yayimlanan_1l_1t_merkezin_kendi_fonksiyonlarindan(ad):
    """Yayımlanan sayılar merkezî fonksiyonlarla BİT-ÖZDEŞ yeniden üretilmeli.

    "Merkeze geçti" iddiası ancak böyle kanıtlanır: modülün kendi
    fonksiyonlarını aynı girdilerle çağırıp aynı bitleri alıyoruz.
    """
    _eng, blok = _koss(ad)
    # Kamara boyu/çapı bloğun kendi akustik girdisinden okunur (motorun
    # içindeki ara değişkenler değil): merkez modül girdilerini yankılar.
    geo = blok['acoustic_modes']['inputs']
    a = blok['acoustic_modes']['sound_speed_m_s']
    f_1l = longitudinal_frequency(a, geo['chamber_length'], 1)
    f_1t = transverse_frequency(a, geo['chamber_diameter'],
                                transverse_root(1, 0))
    assert repr(blok['first_longitudinal_hz']) == repr(f_1l)
    assert repr(blok['first_tangential_hz']) == repr(f_1t)
    assert blok['first_tangential_alpha'] == transverse_root(1, 0)


def test_mod_tablosu_yayimlaniyor(yeni_merkez):
    """Sıvı da artık TAM mod tablosu yayımlar (F2c'nin veri kaynağı)."""
    for ad, blok in yeni_merkez.items():
        am = blok['acoustic_modes']
        assert am['status'] == 'modelled', ad
        assert am['model'] == 'closed_closed_rigid_cylinder_acoustic_modes'
        etiketler = [m['label'] for m in am['modes']]
        assert '1L' in etiketler and '1T' in etiketler, (ad, etiketler)
        # Sıralama frekansa göre olmalı (merkez sözleşmesi).
        frekanslar = [m['frequency_hz'] for m in am['modes']]
        assert frekanslar == sorted(frekanslar), ad
        # Hüküm YASAK: akustik yolda verdict anahtarı olamaz (F2a karar 1).
        assert 'verdict' not in am
        assert 'not_modelled' in am and am['not_modelled']


def test_mod_kaynagi_ciktida_ADIYLA_yaziyor(yeni_merkez):
    """Beyan olmadan göç kanıtlanamaz: çıktı modülün adını söylemeli."""
    for ad, blok in yeni_merkez.items():
        kaynak = blok['mode_source']
        assert 'hrma.analysis.acoustic_modes' in kaynak, ad
        assert 'jnp_zeros' in kaynak, ad


# ===========================================================================
# 4) Manifest tablosunun kendisi (rapora giden çıktı)
# ===========================================================================
def test_manifest_tablosu_uretilebiliyor(yeni_merkez, capsys):
    """Manifest bir YAN ÜRÜN değil, üretilebilir bir tablodur.

    ``pytest -s`` ile koşulduğunda rapora yapıştırılacak tablo basılır.
    """
    satirlar = []
    for ad in sorted(ESKI_YEREL):
        for anahtar in sorted(BIT_OZDES) + ['first_tangential_hz']:
            eski = ESKI_YEREL[ad][anahtar]
            yeni = yeni_merkez[ad][anahtar]
            sebep = BIT_OZDES.get(anahtar, (
                'rounded 1.8412 -> scipy.special.jnp_zeros(1,1)[0] = '
                f'{transverse_root(1, 0)!r}'))
            satirlar.append(manifest_satiri(ad, anahtar, eski, yeni)
                            + f' | reason={sebep}')
    print('\n'.join(satirlar))
    assert len(satirlar) == len(ESKI_YEREL) * (len(BIT_OZDES) + 1)
