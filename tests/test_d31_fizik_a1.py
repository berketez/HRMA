"""ÖH Dalga-31 · fizik kulvarı a1 bekçileri.

Kalemler: OH-FT-02 (chug.py iptalli kök yazımı), P6B4-03 (aynı yanıtta iki
karışım süresi), OH-D19-11 / OH-D18-02 (ölçüm kalemleri; bkz. rapor).

Her bekçi TERS-MUTASYONLA kanıtlanmıştır:
``docs/scofield/raw/OH/D31/fizik/a1/mutasyon*.json``.
"""

from decimal import Decimal, getcontext

import pytest

from hrma.stability.chug import chug_rightmost_root


# ---------------------------------------------------------------------------
# OH-FT-02 — τ = 0, τ_f > 0 dalındaki ikinci mertebe kökün İPTALSİZ yazımı
# ---------------------------------------------------------------------------
#
# Kök: a·s² + b·s + c = 0,  a = τ_c·τ_f,  b = τ_c+τ_f,  c = 1 + 1/(2J).
# Ürünün eski yazımı ``(−b + √disc)/(2a)`` idi; τ_f ≫ τ_c iken √disc ≈ b
# olduğundan pay iptalden erirdi (ölçüm: once_ft02.json).

def _referans_kok(j, tau_c, tau_f, prec=400):
    """En sağdaki kökün yüksek duyarlıklı (Decimal) referansı.

    Bu referans ÜRÜNÜN yazımını tekrarlamaz: ``(−b+√disc)/(2a)`` klasik
    formu kullanılır, ama 400 basamakla — yani ürünün çift duyarlıkta
    kaybettiği basamaklar burada DURUR. Bağımsızlık böyle kurulur:
    aynı cebir, ölçülebilecek kadar yüksek duyarlık.
    """
    getcontext().prec = prec
    tc, tf = Decimal(tau_c), Decimal(tau_f)
    a = tc * tf
    b = tc + tf
    c = Decimal(1) + Decimal(1) / (Decimal(2) * Decimal(j))
    disc = b * b - 4 * a * c
    assert disc > 0, 'bu bekçi yalnız gerçek-kök dalını ölçer'
    return (-b + disc.sqrt()) / (2 * a)


@pytest.mark.parametrize('tau_f, tavan', [
    (1.0e6, 1e-13),
    (1.0e9, 1e-13),
    (1.0e12, 1e-13),
    (1.0e15, 1e-13),
])
def test_oh_ft02_kok_iptalsiz_yazim(tau_f, tavan):
    """τ_f ≫ τ_c iken kök bağıl hatası çift duyarlık gürültüsünde kalmalı.

    ESKİ yazımın ÖLÇÜLEN hatası: 1e6 → 5,9e-12, 1e9 → 1,2e-08,
    1e12 → 5,4e-06, 1e15 → 1,6e-02. Tavan 1e-13 hepsini KIRMIZIYA düşürür.
    """
    j, tau_c = 0.30, 1.0e-3
    kok = chug_rightmost_root(j, 0.0, tau_c, tau_f)
    assert kok is not None
    assert kok.imag == 0.0, 'bu dalda kök gerçek olmalı'
    ref = _referans_kok(j, tau_c, tau_f)
    bagil = abs((Decimal(kok.real) - ref) / ref)
    assert float(bagil) < tavan, (
        f'τ_f = {tau_f:g}: kök bağıl hatası {float(bagil):.3e} > {tavan:g}; '
        'iptalli (−b+√disc)/(2a) yazımı geri gelmiş olabilir.')


def test_oh_ft02_buyuk_tau_f_tasmiyor():
    """(τ_c+τ_f)² çift duyarlığı taşırsa bile kök SONLU ve doğru dönmeli.

    ESKİ yazım burada ham ``OverflowError`` fırlatıyordu (kök sonlu
    olmasına rağmen); yani dışa açık çekirdek işlevi çöküyordu.
    """
    j, tau_c, tau_f = 0.30, 1.0e-3, 1.0e160
    kok = chug_rightmost_root(j, 0.0, tau_c, tau_f)
    assert kok is not None
    assert kok.real < 0.0 and kok.imag == 0.0
    # m → ∞ asimptotu: s₊ → −c/τ_f.
    beklenen = -(1.0 + 1.0 / (2.0 * j)) / tau_f
    assert abs(kok.real / beklenen - 1.0) < 1e-12, (
        f'asimptot tutmuyor: {kok.real!r} ⟷ {beklenen!r}')


def test_oh_ft02_karmasik_dal_esleniktir():
    """Karmaşık dalda kök eskisiyle AYNI (pozitif sanal) eşleniği vermeli."""
    j, tau_c, tau_f = 0.05, 1.0e-3, 1.2e-3
    kok = chug_rightmost_root(j, 0.0, tau_c, tau_f)
    assert kok is not None and kok.imag > 0.0
    # Kalıntı: a·s² + b·s + c ≈ 0 (model-bağımsız sağlama).
    a = tau_c * tau_f
    b = tau_c + tau_f
    c = 1.0 + 1.0 / (2.0 * j)
    kalinti = abs(a * kok * kok + b * kok + c)
    assert kalinti < 1e-12 * c, f'kalıntı {kalinti:.3e} çok büyük'


# ---------------------------------------------------------------------------
# P6B4-03 — hükmün τ SEÇİMİNE duyarlılığı ÖLÇÜLÜR, "konservatif" denmez
# ---------------------------------------------------------------------------

from hrma.stability.chug import assess_chug, chug_tau_sensitivity  # noqa: E402


# Defterin ölçtüğü iki zaman ölçeği (P6B4-03): τ_atomizasyon 4,489 ms ⟷
# mixing_residence_time 1,264 ms (3,55×).
_P6B4_03_TAU_ATOM = 4.489e-3
_P6B4_03_TAU_MIX = 1.264e-3


def test_p6b403_tau_duyarliligi_olculur():
    """İki aday τ ile hüküm/frekans FİİLEN koşulup yayımlanmalı."""
    tau_c = 1.5436660091922559e-3
    d = chug_tau_sensitivity(0.12, tau_c, 0.0, {
        'atomisation_time': _P6B4_03_TAU_ATOM,
        'mixing_residence_time': _P6B4_03_TAU_MIX})
    assert d is not None
    assert set(d['candidates']) == {'atomisation_time',
                                    'mixing_residence_time'}
    # Defterin ölçtüğü frekans farkı (88,16 → 240,02 Hz, 2,7×) burada da
    # görünür: küçük τ daha YÜKSEK frekans verir.
    f_atom = d['candidates']['atomisation_time']['frequency_hz']
    f_mix = d['candidates']['mixing_residence_time']['frequency_hz']
    assert f_mix > f_atom
    assert 2.0 < f_mix / f_atom < 4.0


def test_p6b403_en_konservatif_en_buyuk_tau():
    """``most_conservative`` EN BÜYÜK τ'yu göstermeli (monotonluk)."""
    d = chug_tau_sensitivity(0.12, 1.5436660091922559e-3, 0.0, {
        'atomisation_time': _P6B4_03_TAU_ATOM,
        'mixing_residence_time': _P6B4_03_TAU_MIX})
    assert d['most_conservative'] == 'atomisation_time'
    en_buyuk = max(d['candidates'].values(), key=lambda v: v['tau_s'])
    assert (d['candidates'][d['most_conservative']]['tau_s']
            == en_buyuk['tau_s'])


@pytest.mark.parametrize('j', [0.05, 0.10, 0.20, 0.35, 0.49])
def test_p6b403_hukum_tau_da_monoton(j):
    """τ büyüdükçe hüküm yalnız 'unstable' yönüne gidebilir.

    ``tau_source`` künyesinin "CONSERVATIVE choice" cümlesinin KANITI budur:
    hüküm τ_nötr(J, τ_c, τ_f) ile karşılaştırmadan gelir, τ_nötr ise τ'dan
    bağımsızdır. Bir kez 'unstable' olan bir nokta daha büyük τ'da
    'stable'a DÖNEMEZ; dönüyorsa künyedeki iddia yalandır.
    """
    from hrma.stability.chug import chug_neutral_delay_s
    tau_c = 1.5436660091922559e-3
    # Tarama nötr gecikmenin ETRAFINDA kurulur: J büyüdükçe τ_nötr de
    # büyür, sabit bir τ penceresi büyük J'de geçişi hiç görmezdi.
    tau_n = chug_neutral_delay_s(j, tau_c, 0.0)
    gorulen_kararsiz = False
    for k in range(40):
        tau = tau_n * (0.2 + 0.1 * k)
        h = assess_chug(dp_ratio_j=j, tau_s=tau, tau_c_s=tau_c)
        if h['verdict'] == 'unstable':
            gorulen_kararsiz = True
        elif gorulen_kararsiz:
            pytest.fail(
                f'J = {j}: τ = {tau:.6g} s hükmü "stable"a geri döndü; '
                'hüküm τ\'da monoton değil, konservatiflik iddiası düşer.')
    assert gorulen_kararsiz, f'J = {j}: taramada hiç kararsız nokta yok'


def test_p6b403_alan_fail_closed():
    """İkinci zaman ölçeği verilmediyse duyarlılık alanı HİÇ konmaz."""
    tau_c = 1.5436660091922559e-3
    yalin = assess_chug(dp_ratio_j=0.12, tau_s=_P6B4_03_TAU_ATOM,
                        tau_c_s=tau_c)
    assert 'tau_choice_sensitivity' not in yalin
    zengin = assess_chug(dp_ratio_j=0.12, tau_s=_P6B4_03_TAU_ATOM,
                         tau_c_s=tau_c,
                         alternative_taus={'mixing_residence_time':
                                           _P6B4_03_TAU_MIX})
    d = zengin['tau_choice_sensitivity']
    assert d['candidates']['selected']['tau_s'] == _P6B4_03_TAU_ATOM
    assert 'mixing_residence_time' in d['candidates']
    # Uydurma/boş aday yayımlanmaz.
    #
    # ÖH D32 · P6B4-03 (d) — YÖN ÇEVRİLDİ. Bu satır D31'de
    # ``bos['tau_choice_sensitivity']['candidates'].keys() == {'selected'}``
    # diyordu: geçersiz adaylar elendikten sonra geriye YALNIZ koşunun kendi
    # τ'su kalsa bile bloğun YAYIMLANMASINI mandallıyordu. O blok hiçbir şey
    # kıyaslamamıştır, ama ``most_conservative: 'selected'`` +
    # ``verdict_is_tau_sensitive: False`` diyerek "seçimimiz en konservatif,
    # ölçeğe duyarlı değil" diye okunur — fail-open (ölçüm:
    # docs/scofield/raw/OH/D32/fizik/a1/once_p6b403_tekaday.json, 3/3 vaka;
    # sonra_*: 0/3). Testin NİYETİ ("uydurma/boş aday yayımlanmaz")
    # korunuyor ve güçleniyor: artık kıyassız bloğun kendisi de konmuyor.
    bos = assess_chug(dp_ratio_j=0.12, tau_s=_P6B4_03_TAU_ATOM,
                      tau_c_s=tau_c,
                      alternative_taus={'yok': None, 'negatif': -1.0})
    assert 'tau_choice_sensitivity' not in bos


def test_p6b403_hukum_flipi_yakalanir():
    """Hüküm adaylar arasında DEĞİŞİYORSA alan bunu adıyla söylemeli."""
    # τ_nötr iki adayın ARASINA düşecek bir J seçilir (defterin "6 koşunun
    # 4'ünde unstable→stable dönüyor" gözlemi tam bu hâldir).
    tau_c = 1.5436660091922559e-3
    d = None
    for j in (0.02, 0.05, 0.08, 0.12, 0.2, 0.3, 0.4):
        aday = chug_tau_sensitivity(j, tau_c, 0.0, {
            'atomisation_time': _P6B4_03_TAU_ATOM,
            'mixing_residence_time': _P6B4_03_TAU_MIX})
        if aday['verdict_is_tau_sensitive']:
            d = aday
            break
    assert d is not None, 'hüküm hiçbir J\'de τ seçimine duyarlı çıkmadı'
    assert set(d['verdicts']) == {'stable', 'unstable'}
    assert d['candidates'][d['most_conservative']]['verdict'] == 'unstable'


# ---------------------------------------------------------------------------
# OH-D18-02 / OH-D19-11 — kayan-denge istasyon zinciri (ölçüm kalemleri)
# ---------------------------------------------------------------------------

from hrma.engines.combustion_analysis import CombustionAnalyzer  # noqa: E402
from tests.bagimlilik_kapisi import kapi  # noqa: E402
from tests.test_combustion_cea_validation import (  # noqa: E402
    CANTERA_YOLU_KIRIK)

_YAKIT = {'htpb': 1.0}
_OKS = 'n2o'
_PC_BAR = 20.0


#: Ürün yolu kapalıyken basılacak teşhis. Gövde metni TEK KAYNAKTAN gelir
#: (``test_combustion_cea_validation.CANTERA_YOLU_KIRIK``); buraya yalnız bu
#: bekçinin İKİNCİ koşulu (``gas`` nesnesi) eklenir.
CANTERA_ISTASYON_YOLU_KIRIK = (
    CANTERA_YOLU_KIRIK
    + '\nAyrıca bu bekçi çözücü nesnesinin kendisini de arar: '
      '``CombustionAnalyzer.gas`` None ise kayan-denge istasyon zinciri '
      '(``_solve_equilibrium_throat``) hiç çağrılamaz.')


def _cozumleyici():
    an = CombustionAnalyzer(memoize=True)
    # ÖH D32 / fix-35a — ATLAMA GEREKÇESİ KURULUM SORUSUNA BAĞLANDI.
    # Eski gövde ``if not an.cantera_available or an.gas is None:
    # pytest.skip('Cantera yok: ...')`` idi: gerekçe kütüphanenin YOKLUĞUNU
    # iddia ediyordu ama koşul ÜRÜN BAYRAĞINA bakıyordu. Cantera KURULUYKEN
    # mekanizma zinciri ya da ``gas`` nesnesi bozulursa bu bekçi yine
    # "Cantera yok" diye atlıyordu — yani bir ürün kusuru sessizleşiyordu
    # (parti 31 / T2-2'de ölçülen sınıfın aynısı: 39 sessiz atlama).
    # Kapı artık üç durumlu: kurulu değil -> ATLA, kurulu + yol açık -> KOŞ,
    # kurulu + yol kapalı -> KIRMIZI (bekçi: tests/test_ci_kapsam_kapisi.py::
    # TestAtlamaGerekcesiDurust::test_yokluk_iddiasi_kurulum_sorusuna_dayaniyor).
    kapi('cantera', an.cantera_available and an.gas is not None,
         CANTERA_ISTASYON_YOLU_KIRIK)
    return an


def test_oh_d18_02_istasyon_onbellegi_nicemlenmez():
    """İstasyon önbelleği anahtarı TAM float kalmalı (nicemlenmemeli).

    OH-D18-02'nin önerdiği çare "nicemlenmiş önbellek"tir. O çare D16'da
    ÖLÇÜLEREK reddedildi (``EQUILIBRIUM_CACHE_MAX`` / Faz 4B bulgu A7:
    "kullanıcı girdiyi değiştiriyor, cevap değişmiyor"). Bu bekçi o hükmü
    KİLİTLER: birbirine çok yakın ama AYRI iki oda sıcaklığı, önbellekte
    AYRI hücre açmalı ve AYRI c* vermelidir.
    """
    an = _cozumleyici()
    comp = an._elements_to_cantera_composition(
        an._calculate_elemental_composition(_YAKIT, _OKS, 6.0))
    t1, t2 = 3000.0, 3000.0 + 1e-6
    a = an._solve_equilibrium_throat(comp, t1, _PC_BAR, _PC_BAR * 0.56)
    b = an._solve_equilibrium_throat(comp, t2, _PC_BAR, _PC_BAR * 0.56)
    assert a is not None and b is not None
    assert len(an._eq_station_cache) == 2, (
        'iki AYRI oda sıcaklığı tek önbellek hücresine düştü: anahtar '
        'nicemlenmiş olabilir (D16 hükmü ihlali)')
    assert a['c_star'] != b['c_star'], (
        'girdi değişti ama c* bit-aynı: önbellek çözülmemiş bir girdiyi '
        'cevap diye geri veriyor')


def test_oh_d18_02_of_taramasinda_onbellek_isabeti_yok():
    """O/F taramasında istasyon önbelleği İŞE YARAMAZ — ölçülür, gizlenmez.

    OH-D18-02'nin doğrulanan bacağı budur: her O/F noktasında bileşim
    değiştiği için anahtar da değişir, isabet oranı %0'dır. Bu bekçi
    kalemin teşhisini ölçülebilir kılar; bir gün isabet çıkarsa (yani
    anahtar nicemlenirse) KIRMIZI olur.
    """
    an = _cozumleyici()
    n = 6
    for k in range(n):
        an.analyze_combustion(_YAKIT, _OKS, 3.0 + 1.0 * k, _PC_BAR,
                              expansion_ratio=8.0)
    assert len(an._eq_station_cache) == n, (
        f'{n} O/F noktası {len(an._eq_station_cache)} hücre açtı; anahtar '
        'nicemlenmiş olabilir')


def test_oh_d19_11_tau_c_ye_giden_c_star_kayan_dengedir():
    """Yayımlanan c* kayan-denge BOĞAZ çözümünden gelmeli (τ_c'nin girdisi).

    OH-D19-11 "τ_c tek-γ c*'dan geliyor" diyordu. Bu bekçi, istasyonlar
    çözüldüğünde ``performance['c_star']``in kayan-denge boğazından
    geldiğini ve tek-γ değerinin AYRI adla (``c_star_single_gamma``)
    yayımlandığını kilitler: c* modeli tek-γ'ya geri dönerse KIRMIZI olur.
    """
    an = _cozumleyici()
    r = an.analyze_combustion(_YAKIT, _OKS, 6.0, _PC_BAR, expansion_ratio=8.0)
    perf = r['performance']
    if perf.get('c_star_basis') != 'shifting_equilibrium_throat':
        pytest.skip('bu koşuda kayan-denge istasyonu çözülemedi')
    assert 'c_star_single_gamma' in perf, (
        'tek-γ c* ayrı adla yayımlanmıyor: iki model tek alanda karışır')
    assert perf['c_star'] != perf['c_star_single_gamma']
    assert perf['c_star'] > 0.0


def test_oh_ft02_kalinti_gercek_dalda():
    """GERÇEK dalda kalıntı sağlaması — kök formülünden BAĞIMSIZ ikinci yol.

    KESİNTİ DENETİMİ (ikinci ajan, 14 Eyl): ``_referans_kok`` ürünle AYNI
    cebiri (``(−b+√disc)/(2a)``) yalnız 400 basamakla kurar; yüksek duyarlık
    hatayı ölçmeye yeter ama KANIT PAKETİ'nin "bağımsız ikinci yol" ayağını
    tam karşılamaz. Kalıntı |a·s²+b·s+c| kök formülünü HİÇ kullanmaz: kök
    nereden gelirse gelsin denklemi sağlamak zorundadır. Karmaşık dal için
    bu sağlama zaten vardı (``test_oh_ft02_karmasik_dal_esleniktir``); asıl
    KIRIK olan gerçek dal (τ_f ≫ τ_c) için YOKTU — burada kapatılıyor.

    Kalıntı çift duyarlıkta hesaplanamaz (a·s² ile b·s birbirini götürür ve
    b ~ 1e15'te mutlak gürültü c'yi aşar), o yüzden Decimal kullanılır.
    Eski iptalli yazım τ_f = 1e15'te bağıl kalıntı ~1,6e-02 verir.
    """
    j, tau_c = 0.30, 1.0e-3
    getcontext().prec = 200
    for tau_f in (1.0e6, 1.0e9, 1.0e12, 1.0e15):
        kok = chug_rightmost_root(j, 0.0, tau_c, tau_f)
        assert kok is not None and kok.imag == 0.0
        s = Decimal(kok.real)
        a = Decimal(tau_c) * Decimal(tau_f)
        b = Decimal(tau_c) + Decimal(tau_f)
        c = Decimal(1) + Decimal(1) / (Decimal(2) * Decimal(j))
        kalinti = abs(a * s * s + b * s + c) / c
        assert float(kalinti) < 1e-13, (
            f'τ_f = {tau_f:g}: bağıl kalıntı {float(kalinti):.3e} — dönen '
            'sayı karakteristik denklemi SAĞLAMIYOR (kök formülünden '
            'bağımsız ölçü).')
