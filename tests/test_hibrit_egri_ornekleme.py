"""Hibrit yayın eğrilerinin tepeyi koruyan seyreltmesi (B2-4) — bekçiler.

Ölçülen kusur (14 Ağustos 2026): port 5 mm + t_b 50 s girdisinde
``thrust_curve`` 17 317 nokta / 1,29 MB, ``of_shift_performance`` 17 317
nokta / 1,28 MB — yanıtın %94'ü iki dizi. Katı motor aynı kusuru B2-3'te
çözmüştü; algoritma hrma.analysis.curve_sampling ortak modülüne taşındı
ve hibrit AYNI koddan seyreltir (parametre tutarlılığı kuralı: iki motor
iki kopya taşıyamaz).

Uygulama sonrası ölçüm (bu dosyadaki eşiklerin kaynağı):
yayımlanan 400 / hesaplanan 17 317, impuls sapması %0,0007, tepe itki ve
O/F-Isp uçları birebir korunuyor, iki blok toplamı 62 KB.

ÖH FAZ B (27 Ağustos 2026) — TAŞINAN BEKÇİLER
---------------------------------------------
Kampanya bu dosyanın iki düğümünü "kusuru koruyan bekçi" saydı; ikisi de
modülün KENDİ beyanından daha gevşek bir şey kilitliyordu:

  * ``P5B4-31`` — ``points_published`` beyan edilen ``max_points`` tavanını
    aşabiliyor (ölçüldü: 402-408) ve aşım aynı sözlükte YAN YANA dururken
    kullanıcıya hiç söylenmiyor. Buradaki bekçi aşımı +24 payla tolere
    ediyordu; pay kaldırıldı (bugünkü hibrit uç koşusu tam 400 yayımlıyor,
    yani iddia gevşemeden sıkılaştı) ve tavanın gerçekten tavan olduğu ayrı
    bir bekçiyle sınanıyor.
  * ``P5B4-33`` — ``curve_sampling`` modülü trapez impuls hatasını "‰1'in
    altında tutar" diye KAYITSIZ ŞARTSIZ ilan ediyor ve kanıt olarak bu
    dosyayı gösteriyor; oysa buradaki bekçi ‰5 kilitliyordu (iddianın 5
    katı). Eşik iddianın kendisine çekildi; iddianın kapsamı ayrı bir
    bekçiyle ölçülüyor.

Bugün kırmızı düşen taşımalar ``xfail(strict=True)`` + defter kimliğiyle
durur (açık borç işareti); onarım dalgası imi kaldırır.
"""

import pathlib
import re
import warnings
from pathlib import Path

import numpy as np
import pytest

from hrma.analysis.curve_sampling import TRAPEZOID_PERMIL_LIMIT
from hrma.utils.numeric_compat import trapezoid

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def uc_kosu():
    """Uç girdi çözümü (bir kez çözülür, tüm testler paylaşır)."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        e = HybridRocketEngine(thrust=1000.0, burn_time=50.0, of_ratio=7.0,
                               chamber_pressure=30.0, fuel_type='htpb',
                               oxidizer_type='n2o',
                               initial_port_diameter=0.005)
        r = e.calculate()
    return e, r


@pytest.fixture(scope='module')
def normal_kosu():
    """Kısa yanma: dizi zaten tavanın altında, seyreltme YAPILMAMALI."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        e = HybridRocketEngine(thrust=1000.0, burn_time=3.0, of_ratio=7.0,
                               chamber_pressure=30.0, fuel_type='htpb',
                               oxidizer_type='n2o')
        r = e.calculate()
    return e, r


def test_uc_girdide_yayin_tavana_iner(uc_kosu):
    """17 bin noktalı yanıt şişkinliği kapandı: yayın ≤ BLOĞUN KENDİ tavanı.

    ÖH FAZ B (P5B4-31): eski hâli ``<= THRUST_CURVE_MAX_POINTS + 24``
    diyordu — tavanın %6'lık bir payla aşılmasını sözleşme hâline
    getiriyordu. Ölçüldü (27 Ağustos 2026, bu fikstür): yayımlanan tam 400,
    beyan edilen tavan 400. Pay kaldırıldı ve karşılaştırma bloğun KENDİ
    ``max_points`` alanına bağlandı (iki sayı aynı sözlükte yan yana durur;
    tavan değişirse iddia da onunla değişir).
    """
    e, r = uc_kosu
    tc = r['thrust_curve']
    s = tc['sampling']
    assert s['points_computed'] > 5000, (
        'uç girdi artık uç değil — test senaryosu gözden geçirilmeli')
    assert len(tc['time']) == s['points_published']
    assert len(tc['time']) <= s['max_points'], (
        f"yayımlanan {len(tc['time'])} örnek, beyan edilen tavan "
        f"{s['max_points']} — tavan aşıldı ve kullanıcıya söylenmiyor")
    assert s['decimated'] is True
    assert len(tc['time']) == len(tc['thrust']) == len(tc['pressure']) == \
        len(tc['mass_flow'])


def test_tavan_asimi_beyansiz_kalamaz():
    """Tavan ya tavandır ya da aşım BEYAN EDİLİR — üçüncü seçenek yok.

    ONARILDI (ÖH D26 / P5B4-31): BORÇ İMİ KALDIRILDI. ÖLÇÜLEN kusur (D26
    tabanı 7751531, n=5000 sentetik eğri, sabit tohum): kova algoritması
    ``max_points // 2`` kova açıp her kovadan iki örnek alıyor, ZORUNLU
    örnekleri bunun ÜSTÜNE ekliyordu -> olaysız 402, altı olayla 408
    (tavan 400) ve ``sampling_block`` aşımı hiçbir alanda söylemiyordu.
    Kova bütçesi artık zorunlu örneklerden SONRA açılıyor.

    Bu bekçi iki dalı da koşar:

    * NORMAL dal — bütçe yeterliyse tavan TUTAR (aşım yok, beyan yok),
    * TAŞMA dalı — beyan edilen olaylar tek başına tavanı aşarsa örnek
      ATILMAZ ama aşım ADIYLA beyan edilir.
    """
    from hrma.analysis.curve_sampling import (decimate_curve_indices,
                                              sampling_block,
                                              THRUST_CURVE_MAX_POINTS)
    rng = np.random.default_rng(20260827)
    n = 5000
    F = 1000.0 + 50.0 * np.sin(np.linspace(0.0, 75.0, n)) \
        + rng.normal(0.0, 5.0, n)
    P = 30.0 + np.cos(np.linspace(0.0, 50.0, n))
    olaylar = (137, 999, 1500, 2718, 3141, 4242)   # beyan edilen olay anları

    # --- NORMAL dal: tavan TUTAR --------------------------------------
    for ad, keep in (('olaysız', ()), ('olaylı', olaylar)):
        idx = decimate_curve_indices(F, pressure=P, keep=keep)
        blok = sampling_block(len(idx), n, 0.005,
                              ['burnout'], ['total impulse'])
        assert blok['points_published'] == len(idx)
        assert len(idx) <= blok['max_points'], (
            f'{ad} koşum: yayımlanan {len(idx)} örnek, beyan edilen tavan '
            f"{blok['max_points']} (varsayılan {THRUST_CURVE_MAX_POINTS}) "
            '— tavan aşıldı')
        assert blok['cap_exceeded'] is False
        assert 'cap_note' not in blok

    # --- TAŞMA dalı: olaylar tek başına tavanı aşıyor ------------------
    cok_olay = tuple(range(0, n, 7))          # ~715 zorunlu olay örneği
    idx = decimate_curve_indices(F, pressure=P, keep=cok_olay)
    blok = sampling_block(len(idx), n, 0.005, ['burnout'],
                          ['total impulse'])
    assert len(idx) > blok['max_points'], (
        'taşma senaryosu artık taşmıyor — bekçi gözden geçirilmeli')
    assert blok['cap_exceeded'] is True
    beyan = ' '.join(str(v) for v in blok.values()).lower()
    assert ('exceed' in beyan or 'overshoot' in beyan
            or 'above the cap' in beyan), (
        f"aşım ({len(idx)} > {blok['max_points']}) sözlükte hiçbir alanda "
        'söylenmiyor')
    # Beyan edilen olayların HİÇBİRİ atılmamış olmalı (aşımın gerekçesi bu).
    assert set(cok_olay) <= set(int(i) for i in idx)


def test_impuls_seyreltmeden_etkilenmez(uc_kosu):
    """Yayımlanan eğriden trapezle hesaplanan impuls MODÜLÜN KENDİ sınırının
    (‰1) altında sapar.

    (Türetilmiş sayılar zaten TAM çözünürlükten gelir; bu test, grafiği
    okuyan bir mühendisin eğriden çıkaracağı alanın da dürüst kaldığını
    kilitler.)

    ÖH FAZ B (P5B4-33): eski eşik ‰5 idi — ``curve_sampling`` modülünün
    kendi ilan ettiği sınırın (‰1) BEŞ KATI; üstelik modül kanıt olarak tam
    da bu dosyayı gösteriyor. Eşik iddianın kendisine çekildi. Ölçüldü
    (27 Ağustos 2026, bu fikstür): gerçek sapma +0,00714 ‰, yani sınırın
    140 katı altında — sıkılaştırma bugünkü yeşili kırmıyor, iddiayı
    kanıtla hizalıyor.
    """
    e, r = uc_kosu
    tc = r['thrust_curve']
    I_tam = float(trapezoid(np.asarray(e._thrust_history),
                           np.asarray(e._time_history)))
    I_yayin = float(trapezoid(np.asarray(tc['thrust']),
                             np.asarray(tc['time'])))
    sapma_permil = 1000.0 * abs(I_yayin - I_tam) / I_tam
    assert sapma_permil <= TRAPEZOID_PERMIL_LIMIT, (
        f'trapez impuls sapması {sapma_permil:.5f} ‰ — modül '
        f'{TRAPEZOID_PERMIL_LIMIT} ‰ sınırını GERÇEK HRMA eğrileri için '
        'ilan ediyor (curve_sampling.TRAPEZOID_PERMIL_SCOPE) ve kanıt '
        'olarak bu testi gösteriyor')


def test_permil1_iddiasinin_KAPSAMI_yazili_ve_olculebilir():
    """ONARILDI (ÖH D26 / P5B4-33): iddia artık kapsamıyla yazılı.

    BORÇ İMİ KALDIRILDI. ÖLÇÜLEN kusur (D26 tabanı 7751531): modül trapez
    impuls hatasını ``‰1``in altında tutmayı KAYITSIZ ŞARTSIZ ilan ediyor
    ve kanıt olarak bu dosyayı gösteriyordu; kapsam hiçbir yerde yazılı
    değildi. Aynı seyrelticiye verilen üç patolojik eğride (n=20 000)::

        ateşleme tepesi           +5,9942 ‰
        tek örneklik iğne       +120,9846 ‰
        %5 görev döngülü darbe +4452,7264 ‰

    ONARIM YOLU (bekçinin kendi eski docstring'inde ikinci seçenek olarak
    yazılıydı): sınır her eğri için tutmuyor ve alan-koruyan bir
    örnekleyiciye geçmek zarf/tepe garantisini bozardı; bu yüzden BEYAN
    kapsamıyla yazıldı ve sapma ÖLÇÜLEBİLİR hâle getirildi
    (``curve_sampling.trapezoid_error_permil``).

    Bu bekçi üç şeyi birden ister:

    1. modül artık KAYITSIZ ŞARTSIZ iddia etmemeli — kapsam metni durmalı
       ve patolojik sınıfları ADIYLA anmalı,
    2. kapsamın DIŞI ölçülmüş sayılarla mandallanmalı (cümle sessizce
       yeniden genişletilirse burası kırmızı düşer),
    3. ölçüm yardımcısı, elle kurulan trapez hesabıyla BİREBİR aynı sayıyı
       vermeli (yardımcı iddianın yerine geçtiği için doğruluğu kilitlenir).
    """
    from hrma.analysis import curve_sampling as cs

    # (1) Kapsam metni yazılı ve patolojik sınıfları anıyor.
    kapsam = cs.TRAPEZOID_PERMIL_SCOPE
    assert 'NOT a guarantee' in kapsam, kapsam
    for imza in ('ignition spike', 'needle', 'pulse train'):
        assert imza in kapsam, (imza, kapsam)
    kaynak = (pathlib.Path(cs.__file__)).read_text(encoding='utf-8')
    assert 'trapezoid_error_permil' in kaynak

    # (2) Kapsamın DIŞI: ölçülmüş sayılar mandallanır.
    n = 20000
    t = np.linspace(0.0, 50.0, n)

    atesleme = np.ones(n) * 1000.0
    atesleme[:20] = np.linspace(0.0, 4000.0, 20)

    igne = np.ones(n) * 1000.0
    igne[n // 2] = 50000.0

    darbe = np.zeros(n)
    for bas in range(0, n, 200):
        darbe[bas:bas + 10] = 1000.0

    # ÖNCE (D26 tabanı 7751531) -> SONRA (P5B4-31 kova bütçesi onarımı
    # zorunlu örnekleri hesaba kattığı için kova sayısı 200 -> 198 düştü;
    # sapmalar bu yüzden bir miktar KAYDI, mertebe aynı kaldı):
    #     ateşleme tepesi           5,9942 ‰ ->    6,0691 ‰
    #     tek örneklik iğne       120,9846 ‰ ->  123,4288 ‰
    #     %5 görev döngülü darbe 4452,7264 ‰ -> 4052,0260 ‰
    OLCULEN = {
        'ateşleme tepesi': 6.0691,
        'tek örneklik iğne': 123.4288,
        '%5 görev döngülü darbe': 4052.0260,
    }
    for ad, F in (('ateşleme tepesi', atesleme), ('tek örneklik iğne', igne),
                  ('%5 görev döngülü darbe', darbe)):
        idx = cs.decimate_curve_indices(F)
        I_tam = float(trapezoid(F, t))
        I_yayin = float(trapezoid(F[idx], t[idx]))
        elle = 1000.0 * (I_yayin - I_tam) / I_tam
        assert elle == pytest.approx(OLCULEN[ad], abs=0.05), (
            f'{ad}: kapsam dışı sapma {elle:.4f} ‰, ölçülen '
            f'{OLCULEN[ad]} ‰ — seyreltici değişmiş, kapsam metni de '
            'yeniden ölçülmeli')
        assert abs(elle) > cs.TRAPEZOID_PERMIL_LIMIT, (
            f'{ad} artık sınırın içinde ({elle:.4f} ‰) — kapsam metni '
            'bu sınıfı hâlâ "dışarıda" diye anlatıyorsa GÜNCELLENMELİ')

        # (3) Yardımcı elle hesapla BİREBİR aynı.
        assert cs.trapezoid_error_permil(t, F, idx) == elle

    # Yardımcı fail-closed: oran kurulamıyorsa sayı UYDURULMAZ.
    assert cs.trapezoid_error_permil(t, np.zeros(n), [0, 1]) is None
    assert cs.trapezoid_error_permil([0.0], [1.0], [0]) is None


def test_kritik_ornekler_zorunlu_taSInir(uc_kosu):
    """Tepe itki, tepe basınç ve O/F-Isp uçları yayında BİREBİR var."""
    e, r = uc_kosu
    tc = r['thrust_curve']
    ofp = r['of_shift_performance']
    assert max(tc['thrust']) == float(np.max(e._thrust_history))
    assert max(tc['pressure']) == float(np.max(e._pc_history))
    assert max(ofp['of_ratio']) == float(np.max(e._of_history))
    assert min(ofp['of_ratio']) == float(np.min(e._of_history))
    assert max(ofp['isp']) == float(np.max(e._isp_history))
    assert min(ofp['isp']) == float(np.min(e._isp_history))


def test_iki_seri_ayni_zaman_tabaninda(uc_kosu):
    """thrust_curve ile of_shift_performance zaman dizileri BİREBİR aynı.

    Seri tutarsızlığı kusuru (biri 19,9 s'de biri 20,0 s'de biten seriler)
    8. partide kapatılmıştı; seyreltme onu yeniden açamaz — tek indeks
    kümesi iki bloğa birden uygulanır.
    """
    _, r = uc_kosu
    assert r['thrust_curve']['time'] == r['of_shift_performance']['time']


def test_ilk_ve_son_ornek_korunur(uc_kosu):
    """Yanma penceresinin uçları eğriden okunabilmeli."""
    e, r = uc_kosu
    tc = r['thrust_curve']
    assert tc['time'][0] == float(e._time_history[0])
    assert tc['time'][-1] == float(e._time_history[-1])


def test_ortalamalar_tam_cozunurlukten(uc_kosu):
    """Zaman-ortalamaları seyreltilmiş diziden DEĞİL tam geçmişten gelir."""
    e, r = uc_kosu
    ofp = r['of_shift_performance']
    assert ofp['c_star_time_avg'] == pytest.approx(
        float(np.mean(e._cstar_history)), rel=1e-12)
    assert ofp['isp_time_avg'] == pytest.approx(
        float(np.mean(e._isp_history)), rel=1e-12)


def test_beyan_iki_blokta_da_var(uc_kosu):
    """sampling beyanı: yayın ≠ çözüm çözünürlüğü olduğu açıkça yazılır."""
    _, r = uc_kosu
    for blok in (r['thrust_curve'], r['of_shift_performance']):
        s = blok['sampling']
        assert s['points_computed'] > s['points_published']
        assert s['decimated'] is True
        assert 'UNCHANGED' in s['basis']
        assert s['solver_time_step_s'] is not None


def test_normal_girdide_seyreltme_yok(normal_kosu):
    """Kısa yanmada dizi olduğu gibi yayımlanır; beyan bunu da söyler."""
    e, r = normal_kosu
    tc = r['thrust_curve']
    s = tc['sampling']
    assert s['decimated'] is False
    assert len(tc['time']) == s['points_computed'] == len(e._time_history)


def test_kati_ortak_modulden_okuyor():
    """Katı motorun yerel kopyası SİLİNDİ; iki motor tek kaynaktan okur.

    B2'nin bıraktığı yarım devir tamamlandı: solid_rocket_engine'deki
    _decimate_curve_indices artık kova döngüsü İÇERMEZ, ortak fonksiyona
    delege eder. Kopya geri gelirse (iki algoritmanın sessizce ayrışma
    riski) bu test kırılır. Davranış bit-aynı doğrulandı (sha karşılaştı).
    """
    src = (ROOT / 'hrma' / 'engines' / 'solid_rocket_engine.py').read_text(
        encoding='utf-8')
    govde = src[src.index('def _decimate_curve_indices'):]
    govde = govde[:govde.index('def _published_thrust_curve')]
    assert '_ortak_seyreltme_indeksleri(' in govde
    assert 'linspace' not in govde, 'katıda yerel kova döngüsü geri gelmiş'
    hy = (ROOT / 'hrma' / 'engines' / 'hybrid_rocket_engine.py').read_text(
        encoding='utf-8')
    assert 'from hrma.analysis.curve_sampling import' in hy
    assert '_ortak_seyreltme_indeksleri(' in hy


def test_port_gecmisi_zaten_seyrek():
    """port_history'nin kendi ~200 noktalık seyreltmesi bozulmadı (mevcut
    desen; curve_sampling docstring'i onu emsal gösteriyor)."""
    hy = (ROOT / 'hrma' / 'engines' / 'hybrid_rocket_engine.py').read_text(
        encoding='utf-8')
    assert re.search(r"stride = max\(1, len\(pt\) // 200\)", hy)
