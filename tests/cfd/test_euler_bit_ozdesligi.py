# tests/cfd — Euler yolunun BİT-ÖZDEŞLİK regresyon sözleşmesi (viskoz §11.3)
"""
Viskoz kampanyanın (docs/mimari/cfd-viskoz-tasarimi.md §11.3) taşıyıcı
sözleşmesi: V0 başlamadan ÖNCE bugünkü çözücüyle DÖRT referans alan
donduruldu; her viskoz evre bu dosyalara karşı ``np.array_equal`` verir.
Böylece "Euler yolu hâlâ yeşil" ifadesi davranışsal değil BİT düzeyinde
ölçülür — kompozisyon ilkesinin (§5.1) ölçülebilir temeli budur.

Referanslar (data/cfd_referans/euler_*.npz; üreten: tools/cfd_referans_
dondur.py, vaka kurulumu conftest.EULER_REFERANS_VAKALARI):
    {60×12, 120×24} × {izantropik, şoklu}

Bekçiler:
  (1) Künye tamlığı: her .npz vaka kurulumunu (ızgara + çözücü ayarları)
      taşır ve conftest kayıtlarıyla BİREBİR aynıdır — kurulum kayarsa
      "bit-özdeş" iddiası anlamını yitirir, o yüzden künye de kilitlidir.
  (2) Bugünkü koşum ≡ referans (varsayılan arka uç): korunumlu durum
      dizisi + yayımlanan skalerler (iterasyon, debi, son kalıntı).
  (3) Aynı bekçi NumPy arka ucuna ZORLANARAK tekrarlanır (arka uç seçimi
      çalışma anında okunuyor: euler_core._directional_flux →
      kernels.NUMBA_AVAILABLE; test_performans.py'nin deseni).
  (4) Dondurulmuş durumun kalıntısı iki arka uçta bit-özdeş (ucuz katman:
      dört referansın dördü de, tek kalıntı çağrısı).

ÖLÇÜLDÜ (M4 Max, macOS 15 / arm64, numba 0.61.0, NumPy 1.26.4,
2026-08-18) — bu bekçinin dayandığı üç ölçüm:
  * numba ↔ NumPy TAM KOŞUM bit-özdeşliği: izantropik 60×12 ve şoklu
    60×12'de maks fark tam 0,0 VE iterasyon sayıları eşit (8874 / 24899).
    Yani arka uç seçimi yakınsanan alanı değiştirmiyor — akı düzeyindeki
    sözleşmenin (test_performans.test_numba_numpy_aki_bit_ozdes) koşum
    düzeyindeki karşılığı.
  * Aynı süreçte tekrar koşum bit-özdeş (çözücüde gizli rastgelelik yok).
  * Koşum maliyeti (numba / NumPy): izantropik 60×12 5,3 / 7,5 s;
    şoklu 60×12 13,5 / 19,4 s; izantropik 120×24 8,7 s; şoklu 120×24 19 s.
  * 120×24 ÇİFTİ DE NumPy tam koşumunda bit-özdeş: bütün dosya
    HRMA_CFD_DISABLE_NUMBA=1 ile koşuldu (varsayılan arka uç NumPy olur) →
    dört referansın dördü de yeşil (11 passed, 6 skipped, 94 s).

NumPy kolunun kapsamı ve GEREKÇESİ: 60×12 çifti her koşuda zorlanır
(ölçülen ek maliyet ~27 s). 120×24 çifti HER koşuda zorlanmaz — NumPy tam
koşumu bu çiftte ~75 s daha ekler ve hedefli süit disiplinini tek başına
ikiye katlar. Kapsam açığı DEĞİL maliyet kararıdır; iddia üç ayrı yoldan
ölçülüdür: (a) yukarıdaki HRMA_CFD_DISABLE_NUMBA=1 koşusu (bir kez, dört
vaka), (b) dondurulmuş durumun kalıntısı her koşuda iki arka uçta bit
karşılaştırılır — dört vakanın dördü (bekçi 4), (c) HRMA_CFD_BIT_TAM=1
tam koşum kolunu her dört vakada açar (toplama doğrulandı: 17 → 19 bekçi).

PLATFORM KAPSAMI (ÖH D31 / defter P13B1-03 ile YENİDEN KURULDU): sevk
edilen referansların BEŞİ de darwin/arm64'te donduruldu, yani sözleşmenin
KAPSAMI o platformdur. Kapsam içinde bit-özdeşlik ŞARTTIR (aşağıdaki
bekçiler). Kapsam dışında (CI ubuntu koşar) IEEE-754 aynı olsa da
kütüphane yolları (BLAS/SIMD/derleyici) son bitleri kaydırabilir ve bu
depoda ÖLÇÜLMEMİŞTİR.

Eskiden bu durumda ölçek-duyarlı 1e-12 bağıl tolerans GEÇİŞ ÖLÇÜTÜ olarak
assert ediliyordu. O sayı KAZANILMAMIŞTI — dosyanın kendi cümlesi bile
"ölçüme değil beyana dayanır" diyordu — ve CI'da her vakada dayatılıyordu
(ölçüldü: 5/5 referans o dala düşüyor, bant 3 assert'te ölçüt). Bant bu
yüzden EMEKLİYE AYRILDI: kapsam dışında saklı referansla karşılaştırma
hüküm VERMEZ, ``not_evaluated`` diye raporlanır ve sapma SAYIYLA kaydedilir
(PLATFORM_SAPMA_RAPORU; CI ürün olarak yükler, bant ileride VERİYLE
kazanılabilsin). Bekçi yine ATLAMAZ.

Kapsam dışında BAĞLAYICI sözleşme ÇÖZÜCÜ BELİRLENİMİDİR: aynı vaka iki
ayrı süreçte çözülüp bit karşılaştırılır (tools/cfd_ci_bit_ozdeslik.py,
``belirlenim_sozlesmesi`` fikstürü). Fail-closed: kapsam dışında o ölçüm
kurulmazsa dosyadaki hiçbir bekçi yeşil sayılmaz. NumPy sürümü kapıya
GİRMEZ: aynı makinede sürüm
yükseltmesi bit kaydırırsa bekçinin KIRMIZI olması istenir (sessiz
gevşetme yok — kernels.py'nin "eşik ancak yeniden ölçümle gevşetilir"
disiplini), sürüm yalnız hata mesajında teşhis için yankılanır.
"""

import hashlib
import json
import os
import pathlib
import platform
import sys
import warnings

import numpy as np
import pytest

from hrma.cfd import kernels
from hrma.cfd.euler_core import prim_to_cons_axisym, residual_axisym

from .conftest import (
    EULER_REFERANS_VAKALARI, euler_referans_coz, lule_gridi,
)

#: Referans dizini (depo kökü altında; testin konumundan türetilir).
REFERANS_DIZINI = (pathlib.Path(__file__).resolve().parents[2]
                   / 'data' / 'cfd_referans')

#: Künyeler — sıralı ve tek kaynaklı (conftest kayıtları).
KUNYELER = tuple(EULER_REFERANS_VAKALARI)

#: Kaba çift: NumPy arka ucu her koşuda bunlarda zorlanır (maliyet ölçüldü).
NUMPY_KOLU_VARSAYILAN = ('izantropik_60x12', 'sok_60x12')

#: HRMA_CFD_BIT_TAM=1 → NumPy kolu dört vakanın dördünde de tam koşumla.
NUMPY_KOLU_TAM = os.environ.get('HRMA_CFD_BIT_TAM', '') == '1'

#: EMEKLİYE AYRILAN BANT (ÖH defter P13B1-03; Berke karar dosyası §8
#: seçenek (b), onay sınıfı "ANA MODEL KARAR VEREBİLİR").
#:
#: Burada eskiden ``PLATFORM_DISI_BAGIL_TOL = 1e-12`` vardı ve farklı
#: platformda GEÇİŞ ÖLÇÜTÜ olarak assert ediliyordu. O sayı KAZANILMAMIŞTI:
#: dosyanın kendi beyanı "platformlar arası bit farkı bu depoda ÖLÇÜLMEDİ"
#: diyordu. Sevk edilen beş referansın BEŞİ de darwin/arm64'te donduruldu,
#: CI ubuntu koşuyor — yani bant CI'da her vakada dayatılıyor ve bir kez
#: bile ölçümle sınanmıyordu (ölçüldü, ÖH D31 fea-cfd a2 once.json:
#: 5/5 referans tolerans dalına düşüyor, bant 3 assert'te geçiş ölçütü).
#:
#: Doktrin: beyan edilen sayı kazanılmış olmalıdır. Bant bu yüzden geçiş
#: ölçütü olmaktan ÇIKARILDI. Yerine geçen sözleşme aşağıda.
#:
#: Bant SİLİNMEDİ, RAPOR EŞİĞİNE indirildi: ölçülen sapma bu sayının
#: altındaysa rapora "bant içinde" diye yazılır. Hüküm vermez; ileride
#: gerçek ikinci platform verisiyle bant KAZANILABİLSİN diye durur.
#: Tek kaynak: belirlenim aracının kendi beyanı.
from tools.cfd_ci_bit_ozdeslik import (                    # noqa: E402
    BEYAN_EDILEN_BANT as RAPOR_BANDI,
    VARSAYILAN_VAKALAR as BELIRLENIM_VAKALARI,
)

#: Saklı referansların PLATFORM KAPSAMI. Elle yazılmaz — künyeden okunur,
#: böylece envanter değişirse kapsam kendiliğinden kayar (tek kaynak).
#: Kapsam dışında saklı referansla bit karşılaştırması HÜKÜM VERMEZ.
KAPSAM_DISI_HUKUM = 'not_evaluated'

#: Kapsam dışı koşumda ölçülen sapmalar buraya yazılır ve oturum sonunda
#: JSON'a dökülür (CI bunu ürün olarak yükler; bant VERİYLE kazanılsın).
PLATFORM_SAPMA_RAPORU = {'hukum': KAPSAM_DISI_HUKUM, 'olcumler': {}}

#: Rapor yolu (CI iş akışı isterse yönlendirir).
SAPMA_RAPOR_YOLU = os.environ.get(
    'HRMA_CFD_PLATFORM_SAPMA_RAPORU', '') or None


def referans_platform_kapsami():
    """Sevk edilen referansların künyelerinden okunan kapsam kümesi."""
    kapsam = set()
    for kunye in KUNYELER:
        yol = _referans_yolu(kunye)
        if not yol.exists():
            continue
        with np.load(yol) as z:
            m = json.loads(str(z['meta_json']))
        kapsam.add(f"{m['platform']}/{m['machine']}")
    return kapsam


def _sapma_kaydet(etiket, kayit):
    """Kapsam dışı ölçümü rapora yazar (assert ETMEZ — hüküm vermez)."""
    kayit = dict(kayit)
    kayit['hukum'] = KAPSAM_DISI_HUKUM
    kayit['rapor_bandi'] = RAPOR_BANDI
    fark = kayit.get('max_bagil_fark')
    kayit['rapor_bandi_icinde'] = (
        bool(fark <= RAPOR_BANDI) if fark is not None else None)
    PLATFORM_SAPMA_RAPORU['olcumler'][etiket] = kayit


def _referans_yolu(kunye):
    return REFERANS_DIZINI / f'euler_{kunye}.npz'


def referans_yukle(kunye):
    """Dondurulmuş referansı (U, meta) olarak döndürür."""
    yol = _referans_yolu(kunye)
    assert yol.exists(), (
        f'Referans alan yok: {yol} — Euler bit-özdeşlik sözleşmesi '
        f'(viskoz tasarım §11.3) referanssız kurulamaz. Üretmek için: '
        f'python3 tools/cfd_referans_dondur.py')
    with np.load(yol) as z:
        U = z['U']
        meta = json.loads(str(z['meta_json']))
    return U, meta


def _ayni_platform(meta):
    """Dosya bu makinenin float ortamında mı üretildi?"""
    return (sys.platform == meta['platform']
            and platform.machine() == meta['machine'])


def _kosumdan_U(sonuc, gamma):
    """Çözücünün YAYIMLADIĞI alanlardan korunumlu durum dizisi.

    Referans dosyası da aynı dönüşümden geçirilerek yazıldı (dondurma
    betiği aynı fonksiyonu çağırır); iki taraf da çözücünün kendi
    prim_to_cons_axisym'ini kullandığı için karşılaştırma tek yolludur.
    """
    f = sonuc['fields']
    return prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                               f['pressure_Pa'], gamma)


def _skalerler(sonuc):
    """Bit karşılaştırılacak yayımlanan skalerler."""
    return {
        'iterations': int(sonuc['iterations']),
        # ÜÇ DURUMLU HÜKÜM (OH-D31-15): True / False / None AYNEN taşınır.
        # ``bool()`` burada 'değerlendirilmedi'yi 'yakınsamadı' yapardı ve
        # künye ile koşum arasındaki fark GÖRÜNMEZ olurdu.
        'converged': (None if sonuc['converged'] is None
                      else bool(sonuc['converged'])),
        # Kısmi (sentetik) sözlüklerde alan olmayabilir; yokluk
        # None'dır ve karşılaştırma o ayağı ATLAR (künyede de
        # yoksa). 'bilinmiyor' bir hüküm cinsi DEĞİLDİR.
        'convergence_status': sonuc.get('convergence_status'),
        'mass_flow_in_kg_s': float(sonuc['mass_flow_in_kg_s']),
        'mass_flow_out_kg_s': float(sonuc['mass_flow_out_kg_s']),
        'residual_last': float(np.asarray(sonuc['residual_history'])[-1]),
    }


def _alan_karsilastir(U_ref, U_yeni, meta, etiket):
    """Bit-özdeşlik (aynı platform) / 1e-12 bağıl (farklı platform)."""
    assert U_yeni.shape == U_ref.shape, (
        f'{etiket}: alan şekli {U_yeni.shape}, referans {U_ref.shape} — '
        f'ızgara kurulumu kaymış (künye: {meta["grid"]})')
    if _ayni_platform(meta):
        assert np.array_equal(U_yeni, U_ref), (
            f'{etiket}: Euler yolu BİT düzeyinde değişti — maks mutlak fark '
            f'{float(np.max(np.abs(U_yeni - U_ref))):.3e}, farklı hücre '
            f'{int(np.sum(U_yeni != U_ref))}/{U_ref.size}. Referans künyesi: '
            f'commit {meta["git_commit"]}, {meta["olusturma_tarihi_utc"]}, '
            f'NumPy {meta["numpy"]} (şimdi {np.__version__}), arka uç '
            f'{meta["kernel_backend"]}. Viskoz kampanyanın kompozisyon '
            f'ilkesi (§5.1) viskoz KAPALIYKEN Euler yolunun aynen kalmasını '
            f'ister; değişiklik bilerekse referans tools/cfd_referans_'
            f'dondur.py ile YENİDEN üretilir ve gerekçesi yazılır.')
        return
    # KAPSAM DIŞI (P13B1-03): saklı referans BAŞKA bir platformun float
    # ortamında donduruldu. Burada hüküm VERİLMEZ — ölçülür ve raporlanır.
    # Bu koşumun BAĞLAYICI sözleşmesi ``belirlenim_sozlesmesi`` fikstürüdür
    # (tools/cfd_ci_bit_ozdeslik.py: aynı vaka İKİ AYRI SÜREÇTE, bit).
    olcek = np.max(np.abs(U_ref), axis=(0, 1))          # bileşen başına
    olcek = np.where(olcek > 0.0, olcek, 1.0)
    fark = float(np.max(np.abs(U_yeni - U_ref) / olcek))
    _sapma_kaydet(etiket, {
        'tur': 'alan',
        'referans_kapsami': f'{meta["platform"]}/{meta["machine"]}',
        'kosum_kapsami': f'{sys.platform}/{platform.machine()}',
        'max_bagil_fark': fark,
        'max_mutlak_fark': float(np.max(np.abs(U_yeni - U_ref))),
        'farkli_hucre': int(np.sum(U_yeni != U_ref)),
    })
    warnings.warn(
        f'{etiket}: referans {meta["platform"]}/{meta["machine"]} üzerinde '
        f'üretildi, bu koşum {sys.platform}/{platform.machine()} — saklı '
        f'referansla bit karşılaştırması KAPSAM DIŞI, hüküm '
        f'{KAPSAM_DISI_HUKUM} (ölçülen bağıl sapma {fark:.3e}, rapora '
        f'yazıldı). Bağlayıcı sözleşme bu platformda ÇÖZÜCÜ BELİRLENİMİDİR '
        f'(tools/cfd_ci_bit_ozdeslik.py) ve o AYRICA koşulur.',
        RuntimeWarning)


def _skaler_karsilastir(meta, sonuc, etiket):
    """Yayımlanan skalerler: kapsam içinde BİT, kapsam dışında rapor.

    P13B1-03: saklı referans başka platformda donduysa hiçbir ayak
    (converged / iterasyon / debi / kalıntı) hüküm vermez — hepsi ÖLÇÜLÜR
    ve rapora yazılır. Uydurulmuş bir bandın altında kalmak "geçti"
    saymak, kazanılmamış sayıyı ölçüt yapmaktı.
    """
    yeni = _skalerler(sonuc)
    ref = meta['kosum']
    if not _ayni_platform(meta):
        _sapma_kaydet(f'{etiket}/skaler', {
            'tur': 'skaler',
            'referans_kapsami': f'{meta["platform"]}/{meta["machine"]}',
            'kosum_kapsami': f'{sys.platform}/{platform.machine()}',
            'converged_ref': ref['converged'],
            'converged_kosum': yeni['converged'],
            'iterations_ref': ref['iterations'],
            'iterations_kosum': yeni['iterations'],
            'max_bagil_fark': max(
                abs(yeni[ad] - ref[ad]) / (abs(ref[ad]) or 1.0)
                for ad in ('mass_flow_in_kg_s', 'mass_flow_out_kg_s',
                           'residual_last')),
        })
        return
    assert yeni['converged'] == ref['converged'], (
        f'{etiket}: hüküm değişti — converged {ref["converged"]} → '
        f'{yeni["converged"]}')
    # OH-D31-15: hükmün CİNSİ de kilitli. converged None iken durum
    # 'not_evaluated' olmalı; künyede durum yoksa (eski dosya) atlanır.
    if ref.get('convergence_status') is not None:
        assert yeni['convergence_status'] == ref['convergence_status'], (
            f'{etiket}: hükmün cinsi değişti — convergence_status '
            f'{ref["convergence_status"]} → {yeni["convergence_status"]}')
    assert yeni['iterations'] == ref['iterations'], (
        f'{etiket}: iterasyon sayısı {ref["iterations"]} → '
        f'{yeni["iterations"]} — yakınsama yolu değişti (alan bit-aynı olsa '
        f'bile sürücü davranışı kaymış)')
    for ad in ('mass_flow_in_kg_s', 'mass_flow_out_kg_s', 'residual_last'):
        assert yeni[ad] == ref[ad], (
            f'{etiket}: {ad} bit düzeyinde değişti: {ref[ad]!r} → '
            f'{yeni[ad]!r}')


# ---------------------------------------------------------------------------
# Bugünkü koşumlar (fikstürler): 120×24 çifti oturum fikstürlerinden gelir —
# aynı vaka iki kez çözülmez (süit disiplini), üstelik bekçi tam da diğer
# bekçilerin kullandığı koşumu kilitler.
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def bugunku_kosumlar(lule_cozumu, sok_cozumu):
    kosum = {
        'izantropik_120x24': lule_cozumu,
        'sok_120x24': sok_cozumu,
    }
    for kunye in KUNYELER:
        if kunye not in kosum:
            kosum[kunye] = euler_referans_coz(kunye)
    return kosum


@pytest.fixture(scope='module')
def numpy_kosumlari():
    """NumPy arka ucuna ZORLANMIŞ koşumlar (kapsam: NUMPY_KOLU_*)."""
    kunyeler = KUNYELER if NUMPY_KOLU_TAM else NUMPY_KOLU_VARSAYILAN
    onceki = kernels.NUMBA_AVAILABLE
    kernels.NUMBA_AVAILABLE = False           # seçici çalışma anında okur
    try:
        return {k: euler_referans_coz(k) for k in kunyeler}
    finally:
        kernels.NUMBA_AVAILABLE = onceki


# ---------------------------------------------------------------------------
# 1) Künye tamlığı ve kurulum kilidi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('kunye', KUNYELER)
def test_referans_kunyesi_kurulumu_kilitler(kunye):
    """Dondurulmuş dosya, conftest'teki vaka kurulumunun AYNISINI taşır."""
    U, meta = referans_yukle(kunye)
    vaka = EULER_REFERANS_VAKALARI[kunye]

    assert meta['kunye'] == kunye
    assert meta['grid'] == {'ni': vaka['ni'], 'nj': vaka['nj']}, (
        f'{kunye}: dondurulmuş ızgara {meta["grid"]} ≠ kayıt '
        f'{{"ni": {vaka["ni"]}, "nj": {vaka["nj"]}}}')
    assert meta['cozucu'] == vaka['cozucu'], (
        f'{kunye}: dondurulmuş çözücü ayarları kayıttan farklı — referans '
        f'başka bir vakanın alanı: {meta["cozucu"]} ≠ {vaka["cozucu"]}')
    assert U.shape == (vaka['ni'], vaka['nj'], 4)
    assert U.dtype == np.float64 and np.all(np.isfinite(U))
    # --- ÇEVRİLDİ (ÖH D32 / OH-D31-15) ----------------------------------
    #
    # ESKİ MANDAL: ``assert meta['kosum']['converged'] is True`` —
    # "yakınsamayan alan referans olamaz". Bu iddia, hükmün ÜÇ DEĞERLİ
    # olduğu (True / False / None) sözleşmeden ÖNCE yazılmıştı ve fiilen
    # KUSURU KORUYORDU: dört referansın üçü, öz-tutarlılık kapısının
    # KAPSAMI DIŞINDA hüküm alıyordu (şema kalıntısı yayımlanandan 44,29 /
    # 398,71 / 2,9030e+07 kat büyük — once.json K1) ve mandal tam da o
    # kazanılmamış ``True``nun yerinde durmasını ŞART koşuyordu. Sözleşme
    # üç duruma geçince (Berke kararı 15 Eyl 2026 §3 seç. A) mandalın
    # kendisi kırmızı üretirdi; kusuru kilitleyen bir bekçi onarımı
    # engelleyemez, yönü çevrilir.
    #
    # YENİ MANDAL — asıl korunacak şey neydi: bir referans, ÖLÇÜLMÜŞ bir
    # başarısızlığın alanı OLAMAZ. O yasak AYNEN duruyor: ``False`` ve
    # ıraksama/plato/duvar-basıncı cinsleri REDDEDİLİR. Yeni olarak
    # ``None`` + ``'not_evaluated'`` kabul edilir — ama BEDAVA değil:
    # künye hükmün neden yargılanmadığını YAZILI gerekçesiyle taşımak
    # zorundadır (``verdict_basis``), yoksa "hüküm yok" sessiz bir boşluğa
    # döner. Kök onarım (kapıyı açık yola genişletip referansları gerçekten
    # yeniden koşmak) 2.7'dedir; bu bekçi o güne kadar beyanın ADIYLA
    # durmasını sağlar.
    _hukum = meta['kosum']['converged']
    _durum = meta['kosum'].get('convergence_status')
    assert _hukum is not False, (
        f'{kunye}: ÖLÇÜLMÜŞ olarak yakınsamayan alan referans olamaz '
        f'(converged=False, convergence_status={_durum!r})')
    assert _hukum in (True, None), (
        f'{kunye}: künyedeki hüküm üç durumlu sözleşmenin dışında: '
        f'{_hukum!r} (True | False | None bekleniyordu)')
    assert _durum in ('converged', 'not_evaluated'), (
        f'{kunye}: künyedeki hüküm cinsi referans için uygun değil: '
        f'{_durum!r} — yalnız "converged" ya da "not_evaluated" kabul '
        f'edilir (OH-D31-15)')
    assert (_hukum is True) == (_durum == 'converged'), (
        f'{kunye}: hüküm ile cinsi çelişiyor — converged={_hukum!r}, '
        f'convergence_status={_durum!r}')
    if _hukum is None:
        assert meta['kosum'].get('verdict_basis', '').strip(), (
            f'{kunye}: hüküm YARGILANMAMIŞ (converged=None) ama künyede '
            f'gerekçe yok — "hüküm yok" ADIYLA yayımlanmak zorundadır '
            f'(OH-D31-15 / Berke kararı 15 Eyl 2026 §3).')
        yen = meta.get('kunye_yenileme') or {}
        assert yen.get('dizi_degisti_mi') is False, (
            f'{kunye}: künye yenilendi ama dizinin değişmediği künyede '
            f'BEYAN EDİLMEMİŞ — bit-özdeşlik sözleşmesi bu beyana dayanır')

    # Üretim künyesi: sahte/eksik künye sözleşmeyi izlenemez kılar.
    for alan in ('git_commit', 'olusturma_tarihi_utc', 'platform', 'machine',
                 'python', 'numpy', 'kernel_backend', 'dizi_beyani',
                 'uretici'):
        assert meta.get(alan), f'{kunye}: künye alanı boş/eksik: {alan}'
    assert len(meta['git_commit']) >= 7
    assert meta['uretici'] == 'tools/cfd_referans_dondur.py'

    # --- P10B4-14 (ÖH D31 fea-cfd a1): ÜRETİM AĞACININ TEMİZLİĞİ ---------
    #
    # ``tools/cfd_referans_dondur.py`` ÖH D19'da fail-closed bir kirlilik
    # kapısı kazandı (``kirlilik_kapisi``) ama SEVK EDİLEN dosyalara
    # uygulanmıyordu: bu bekçi yalnız alan doluluğunu ve
    # ``len(git_commit) >= 7``i sınıyordu, dosyada ``kirli``/``dirty``
    # dizesi HİÇ geçmiyordu. ÖLÇÜLDÜ (once_cfd.json K1, taban 9d70e9ed):
    # dört referansın DÖRDÜ de ``git_calisma_agaci_kirli = true``
    # (commit a8e03547) ve hiçbirinde ``git_durumu_olculebildi`` /
    # ``git_kirli_izin_gerekcesi`` alanı YOKTU — yani kapı kurulmadan
    # önce dondurulmuşlardı. "Kapı var, geçmiş denetlenmiyor" hâli.
    #
    # Kirli ağaçtan dondurulan referans YENİDEN ÜRETİLEMEZ: künyedeki
    # commit dosyanın kaynağını temsil etmez, çünkü çalışma ağacındaki
    # yamalar o commit'te yoktur. Bit-özdeşlik sözleşmesinin tamamı
    # "bu dosya ŞU kaynaktan çıktı" iddiasına dayandığı için bu bir
    # izlenebilirlik kusurudur, bir üslup tercihi değil.
    #
    # FAIL-CLOSED: temiz ağaç ŞARTTIR. Tek istisna, aracın kendi açık
    # izin yolu (``--kirli-agaca-izin-ver --gerekce``) ile künyeye YAZILMIŞ
    # bir gerekçedir; gerekçesiz kirlilik kabul edilmez ve "ölçülemedi"
    # temiz sayılmaz.
    assert meta.get('git_durumu_olculebildi') is True, (
        f'{kunye}: künyede git_durumu_olculebildi alanı yok/False — dosya '
        'kirlilik kapısı kurulmadan dondurulmuş ya da depo durumu '
        'ölçülemeden yazılmış; ölçemediğimiz ağaç temiz sayılmaz '
        '(P10B4-14). Yeniden üretmek için: '
        'python3 tools/cfd_referans_dondur.py --zorla')
    _kirli = meta.get('git_calisma_agaci_kirli')
    assert _kirli is not None, (
        f'{kunye}: künyede git_calisma_agaci_kirli alanı yok (P10B4-14)')
    if _kirli:
        assert meta.get('git_kirli_izin_gerekcesi', '').strip(), (
            f'{kunye}: KİRLİ çalışma ağacından dondurulmuş ve künyede '
            'gerekçe yok — bu referansın hangi kaynaktan çıktığı '
            'kanıtlanamaz (P10B4-14). Ağacı temizleyip yeniden dondurun '
            '(python3 tools/cfd_referans_dondur.py --zorla) ya da aracın '
            '--kirli-agaca-izin-ver --gerekce yolunu kullanın.')


def test_dort_referans_ve_kapsam():
    """Belge §11.3'ün istediği dört vaka mevcut ve dosyalar küçük."""
    assert set(KUNYELER) == {'izantropik_60x12', 'izantropik_120x24',
                             'sok_60x12', 'sok_120x24'}
    toplam = 0
    for kunye in KUNYELER:
        yol = _referans_yolu(kunye)
        assert yol.exists(), f'referans yok: {yol}'
        toplam += yol.stat().st_size
    # Depo şişmesin: dört dosya toplamı ölçüldü (2026-08-18) ~0,53 MB.
    assert toplam < 5 * 1024 * 1024, (
        f'referans dosyaları toplam {toplam / 1024 / 1024:.2f} MB — 5 MB '
        f'sınırı aşıldı; alan seçimi (yalnız korunumlu durum) bozulmuş '
        f'olabilir')


# ---------------------------------------------------------------------------
# 1b) Platform kapısının KENDİSİ (ikinci platform olmadan ölçülebilsin)
#
# Kapı dosya başında beyan edildi ama bu makinede hiç tetiklenmez: referans
# burada üretildi. Beyanı ölçülebilir kılmak için karşılaştırma fonksiyonu
# sahte künyeyle (yalnız platform/mimari alanları değiştirilmiş GERÇEK
# künye) sınanır — ürün verisi uydurulmaz, karşılaştırıcının davranışı
# ölçülür.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1a) BAĞLAYICI SÖZLEŞME (P13B1-03 / Berke karar dosyası §8-b)
#
# Saklı referanslar darwin/arm64 KAPSAMLIDIR. Kapsam içindeyken bağlayıcı
# sözleşme referansla BİT-ÖZDEŞLİKTİR (aşağıdaki bekçiler). Kapsam
# DIŞINDAYKEN referans hüküm veremez; o zaman bağlayıcı sözleşme
# ÇÖZÜCÜNÜN O PLATFORMDAKİ BELİRLENİMİDİR: aynı vaka iki AYRI SÜREÇTE
# (farklı PYTHONHASHSEED) çözülür ve korunumlu durumlar bit düzeyinde
# karşılaştırılır. Bu, bit-özdeşlik sözleşmesinin dayandığı önermedir.
#
# FAIL-CLOSED: kapsam dışında bu ölçüm koşmazsa ya da ayrışma çıkarsa
# dosyadaki HİÇBİR bekçi yeşil sayılmaz — "kapsam dışı" sessiz geçiş
# DEĞİLDİR. Kapsam içinde fikstür hiçbir iş yapmaz (maliyet sıfır).
# ---------------------------------------------------------------------------

def belirlenim_hukmunu_dogrula(hukum, burasi, kapsam):
    """Belirlenim hükmü: bit-aynı DEĞİLSE fail-closed.

    Fikstürden ayrı bir işlevdir; böylece bekçi kapının DAVRANIŞINI
    (sentetik 'AYRISTI' hükmüyle) ölçebilir — "gövdede assert var mı"
    biçimindeki yapısal ölçüm ``if False: assert ...`` ile kandırılabilir.
    """
    vakalar = hukum.get('vakalar') or {}
    assert vakalar, (
        f'{burasi}: belirlenim ölçümü HİÇ VAKA döndürmedi — kapsam dışı '
        f'koşumda bağlayıcı sözleşme kurulamadı (fail-closed)')
    kotu = [k for k, v in vakalar.items() if not v.get('bit_ayni')]
    assert not kotu, (
        f'{burasi}: saklı referanslar bu platformu KAPSAMIYOR '
        f'({sorted(kapsam)}), o yüzden bağlayıcı sözleşme çözücü '
        f'belirlenimidir — ve o KURULAMADI: {kotu}. Ayrıntı: '
        f'{json.dumps(vakalar, ensure_ascii=False)[:600]}')


@pytest.fixture(scope='session', autouse=True)
def belirlenim_sozlesmesi():
    """Kapsam dışı koşumda belirlenimi ÖLÇER ve ŞART koşar."""
    kapsam = referans_platform_kapsami()
    burasi = f'{sys.platform}/{platform.machine()}'
    PLATFORM_SAPMA_RAPORU['referans_kapsami'] = sorted(kapsam)
    PLATFORM_SAPMA_RAPORU['kosum_kapsami'] = burasi
    icerde = burasi in kapsam
    PLATFORM_SAPMA_RAPORU['kapsam_icinde'] = icerde
    if icerde:
        PLATFORM_SAPMA_RAPORU['baglayici_sozlesme'] = 'saklı_referans_bit'
        yield
    else:
        PLATFORM_SAPMA_RAPORU['baglayici_sozlesme'] = (
            'cozucu_belirlenimi (tools/cfd_ci_bit_ozdeslik.py)')
        from tools import cfd_ci_bit_ozdeslik as belirlenim
        hukum = belirlenim.kos(list(BELIRLENIM_VAKALARI))
        PLATFORM_SAPMA_RAPORU['belirlenim_hukmu'] = hukum
        belirlenim_hukmunu_dogrula(hukum, burasi, kapsam)
        yield
    if SAPMA_RAPOR_YOLU:
        pathlib.Path(SAPMA_RAPOR_YOLU).write_text(
            json.dumps(PLATFORM_SAPMA_RAPORU, ensure_ascii=False, indent=2)
            + chr(10), encoding='utf-8')


def _kunye_platformlu(meta, yerli):
    """Aynı künyenin platform alanları bu makineye/yabancıya ayarlanmışı."""
    if yerli:
        return dict(meta, platform=sys.platform, machine=platform.machine())
    return dict(meta, platform='hiçbir_platform', machine='hiçbir_mimari')


def test_platform_kapisi_ayni_platformda_tek_ulpu_bile_yakalar():
    U, meta = referans_yukle('izantropik_60x12')
    yerli = _kunye_platformlu(meta, yerli=True)
    _alan_karsilastir(U, U.copy(), yerli, 'sentetik-yerli')      # aynı → sessiz
    bozuk = U.copy()
    bozuk[0, 0, 0] = np.nextafter(bozuk[0, 0, 0], np.inf)        # 1 ULP
    with pytest.raises(AssertionError, match='BİT düzeyinde değişti'):
        _alan_karsilastir(U, bozuk, yerli, 'sentetik-yerli')


def test_platform_kapisi_yabanci_platformda_NOT_EVALUATED_raporlar():
    """Kapsam dışı: ATLAMA yok, UYDURMA BANT da yok — ölçülür, raporlanır.

    ÇEVRİLDİ (ÖH D31 fea-cfd a2, defter P13B1-03). Bu bekçinin eski hâli
    ``test_platform_kapisi_yabanci_platformda_gevser_ve_beyan_eder``
    kusuru KORUYORDU: kapsam dışında 1e-12 bağıl bandın GEÇİŞ ÖLÇÜTÜ
    olarak assert edilmesini ŞART koşuyordu. O bant ölçülmemişti (dosyanın
    kendi beyanı: "platformlar arası bit farkı bu depoda ÖLÇÜLMEDİ") ve
    CI'da (ubuntu) 5/5 referansta dayatılıyordu.

    Yeni iddia üç ayaklıdır ve eskisinden DAHA fazlasını ölçer:
      (1) kapsam dışı ölçüm hâlâ ATLAMAZ ve uyarır (eski ayak korundu),
      (2) hüküm ``not_evaluated``tır — kazanılmamış bir bant assert
          EDİLMEZ (yeni ayak: eski davranış geri gelirse kırmızı),
      (3) sapma SAYIYLA rapora yazılır — bandın ileride VERİYLE
          kazanılmasının yolu budur (yeni ayak).
    """
    U, meta = referans_yukle('izantropik_60x12')
    yabanci = _kunye_platformlu(meta, yerli=False)
    PLATFORM_SAPMA_RAPORU['olcumler'].pop('sentetik-yabancı', None)

    ulp_bozuk = U.copy()
    ulp_bozuk[0, 0, 0] = np.nextafter(ulp_bozuk[0, 0, 0], np.inf)
    with pytest.warns(RuntimeWarning, match='KAPSAM DIŞI'):
        _alan_karsilastir(U, ulp_bozuk, yabanci, 'sentetik-yabancı')
    kayit = PLATFORM_SAPMA_RAPORU['olcumler']['sentetik-yabancı']
    assert kayit['hukum'] == KAPSAM_DISI_HUKUM == 'not_evaluated'
    assert kayit['farkli_hucre'] == 1
    assert kayit['rapor_bandi_icinde'] is True, kayit

    # (2) 1e-6'lık DAVRANIŞ oynaması da artık hüküm VERMEZ — ölçülür.
    # Kazanılmamış bir bandı ölçüt yapmak yerine sayı rapora yazılır;
    # bağlayıcı sözleşme belirlenimdir (belirlenim_sozlesmesi fikstürü).
    davranis_bozuk = U.copy()
    davranis_bozuk[..., 0] *= 1.0 + 1e-6
    with pytest.warns(RuntimeWarning, match='KAPSAM DIŞI'):
        _alan_karsilastir(U, davranis_bozuk, yabanci, 'sentetik-yabancı')
    kayit = PLATFORM_SAPMA_RAPORU['olcumler']['sentetik-yabancı']
    assert kayit['hukum'] == 'not_evaluated'
    assert kayit['max_bagil_fark'] == pytest.approx(1e-6, rel=1e-3), kayit
    assert kayit['rapor_bandi_icinde'] is False, (
        'rapor bandı hüküm vermez ama SAYIYI sınıflandırır')
    PLATFORM_SAPMA_RAPORU['olcumler'].pop('sentetik-yabancı', None)


def test_uydurma_bant_GECIS_OLCUTU_olarak_KULLANILMIYOR():
    """P13B1-03: 1e-12 bir daha assert'te geçiş ölçütü olmasın.

    Ters yönlü bekçi: bandın adı dosyada DURABİLİR (rapor eşiği), ama
    ``assert`` ile hüküm veremez. Eski ad da geri gelemez.
    """
    import ast
    agac = ast.parse(pathlib.Path(__file__).read_text(encoding='utf-8'))

    # (a) Emekli ad KOD olarak geri gelmemiş. Yorumda/docstring'te ANILMASI
    #     serbesttir (gerekçe orada yazılı); ölçülen şey AST'tir.
    adlar = {d.id for d in ast.walk(agac) if isinstance(d, ast.Name)}
    adlar |= {d.attr for d in ast.walk(agac) if isinstance(d, ast.Attribute)}
    assert 'PLATFORM_DISI_BAGIL_TOL' not in adlar, (
        'emekliye ayrılan bant adı KOD olarak geri gelmiş')

    # (b) Rapor bandı hiçbir assert'in hüküm ifadesinde geçmiyor.
    #     Bu bekçinin KENDİ gövdesi hariç: oradaki assert ürün verisine
    #     değil, bandın TEK KAYNAKTAN geldiğine bakar.
    bu_bekci = next(
        d for d in ast.walk(agac)
        if isinstance(d, ast.FunctionDef)
        and d.name == 'test_uydurma_bant_GECIS_OLCUTU_olarak_KULLANILMIYOR')
    kendi = {id(x) for x in ast.walk(bu_bekci)}
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Assert) or id(dugum) in kendi:
            continue
        gecen = {d.id for d in ast.walk(dugum.test)
                 if isinstance(d, ast.Name)}
        if 'RAPOR_BANDI' in gecen:
            raise AssertionError(
                f'rapor bandı geçiş ölçütü olarak assert ediliyor '
                f'(satır {dugum.lineno})')
    # Kapsam dışı yolda hüküm adı tek kaynaktan gelir.
    assert KAPSAM_DISI_HUKUM == 'not_evaluated'
    assert RAPOR_BANDI == 1e-12, 'rapor eşiği aracın beyanından okunmalı'


# ---------------------------------------------------------------------------
# 2) Bit-özdeşlik — varsayılan arka uç (numba kuruluysa numba)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('kunye', KUNYELER)
def test_bugunku_kosum_referansla_bit_ozdes(kunye, bugunku_kosumlar):
    U_ref, meta = referans_yukle(kunye)
    _, sonuc = bugunku_kosumlar[kunye]
    U_yeni = _kosumdan_U(sonuc, EULER_REFERANS_VAKALARI[kunye]['cozucu']
                         ['gamma'])
    _alan_karsilastir(U_ref, U_yeni, meta,
                      f'{kunye} [{sonuc["kernel_backend"]}]')
    _skaler_karsilastir(meta, sonuc, f'{kunye} [{sonuc["kernel_backend"]}]')


# ---------------------------------------------------------------------------
# 3) Bit-özdeşlik — NumPy arka ucu zorlanarak
# ---------------------------------------------------------------------------

def _numpy_kolu_gerekcesi():
    """Kol neden koşmuyor? (Yalan gerekçe yasağı: üç durum ayrı ayrı.)"""
    if not kernels.NUMBA_AVAILABLE and kernels.NUMBA_DISABLED_BY_ENV:
        return ('HRMA_CFD_DISABLE_NUMBA=1 ile numba BİLEREK kapatılmış: '
                'varsayılan arka uç ZATEN NumPy, bu kol varsayılan kolun '
                'aynısı olurdu (aynı koşum ikinci kez koşulmaz)')
    if not kernels.NUMBA_AVAILABLE:
        return ('numba içe aktarılamıyor (isteğe bağlı bağımlılık): '
                'varsayılan arka uç ZATEN NumPy, bu kol varsayılan kolun '
                'aynısı olurdu')
    return None


NUMPY_KOLU_ATLAMA = _numpy_kolu_gerekcesi()


@pytest.mark.skipif(NUMPY_KOLU_ATLAMA is not None,
                    reason=NUMPY_KOLU_ATLAMA or '')
@pytest.mark.parametrize(
    'kunye', KUNYELER if NUMPY_KOLU_TAM else NUMPY_KOLU_VARSAYILAN)
def test_numpy_arka_uc_kosumu_referansla_bit_ozdes(kunye, numpy_kosumlari):
    """Referans numba ile donduruldu; NumPy yolu AYNI biti vermeli.

    (Ölçüldü: 60×12 çiftinde maks fark 0,0 ve iterasyon sayıları eşit.)
    """
    U_ref, meta = referans_yukle(kunye)
    _, sonuc = numpy_kosumlari[kunye]
    assert sonuc['kernel_backend'] == 'numpy', (
        'arka uç zorlaması tutmadı: çözücü hâlâ '
        f'{sonuc["kernel_backend"]} beyan ediyor')
    U_yeni = _kosumdan_U(sonuc, EULER_REFERANS_VAKALARI[kunye]['cozucu']
                         ['gamma'])
    _alan_karsilastir(U_ref, U_yeni, meta, f'{kunye} [numpy]')
    _skaler_karsilastir(meta, sonuc, f'{kunye} [numpy]')


# ---------------------------------------------------------------------------
# 4) Ucuz katman: dondurulmuş durumun kalıntısı iki arka uçta bit-özdeş
#    (dört vakanın dördü de; tek kalıntı çağrısı → milisaniye sınıfı).
#    Bu, 120×24 NumPy tam koşumu varsayılanda koşmasa da arka uç iddiasının
#    o vakalarda da ölçülmüş olmasını sağlar.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not kernels.NUMBA_AVAILABLE,
                    reason=(NUMPY_KOLU_ATLAMA
                            or 'numba yok — karşılaştırılacak ikinci arka '
                               'uç yok'))
@pytest.mark.parametrize('kunye', KUNYELER)
def test_dondurulmus_durumun_kalintisi_arka_uctan_bagimsiz(kunye):
    U_ref, _ = referans_yukle(kunye)
    vaka = EULER_REFERANS_VAKALARI[kunye]
    c = vaka['cozucu']
    grid = lule_gridi(vaka['ni'], vaka['nj'])

    dudt_numba, aux_numba = residual_axisym(
        U_ref, grid, c['gamma'], c['R'], c['P0'], c['T0'], Pb=c['Pb'])
    onceki = kernels.NUMBA_AVAILABLE
    kernels.NUMBA_AVAILABLE = False
    try:
        dudt_numpy, aux_numpy = residual_axisym(
            U_ref, grid, c['gamma'], c['R'], c['P0'], c['T0'], Pb=c['Pb'])
    finally:
        kernels.NUMBA_AVAILABLE = onceki

    assert np.array_equal(dudt_numba, dudt_numpy), (
        f'{kunye}: dondurulmuş durumun kalıntısı arka uca göre değişti — '
        f'maks fark {float(np.max(np.abs(dudt_numba - dudt_numpy))):.3e} '
        f'(kernels.py sözleşmesi: aynı işlem sırası, fastmath kapalı)')
    for ad in ('mass_flow_in_kg_s', 'mass_flow_out_kg_s',
               'energy_flux_in_W', 'energy_flux_out_W',
               'wall_mass_flux_kg_s'):
        assert aux_numba[ad] == aux_numpy[ad], (
            f'{kunye}: aux[{ad}] arka uca göre değişti: '
            f'{aux_numba[ad]!r} ≠ {aux_numpy[ad]!r}')


# ---------------------------------------------------------------------------
# 5) ÖH D18 / P6B1-02 — ``_outlet_state``in ``Pb is None`` DALI
#
# ÖLÇÜLEN KUSUR (taban 9071a64): yukarıdaki dört referansın DÖRDÜ de ``Pb``
# VERİLMİŞ koşumdur (conftest: ``Pb=LULE_PB`` / ``LULE_PB_SOK``). Oysa
# ``_outlet_state``in ``Pb is None`` dalı ürün ucunun (``/api/cfd/nozzle``)
# VARSAYILANIDIR ve ``euler_core.py`` "Euler yolunun bit-özdeşlik sözleşmesi
# (§11.3) bu dalın üstünde durur" diye BEYAN ediyordu. Ölçüm bunu çürüttü:
# dal bilerek bozulduğunda (hayalete 1e-6 bağıl basınç sıçraması yazıldı)
# bu dosyadaki bekçilerin HEPSİ bit-YEŞİL kaldı — kapsam beyanı yanlıştı.
#
# ÇÖZÜM ve MALİYETİ: yeni bir ÇÖZÜM dondurulmadı (dört yeni koşu dakika
# sınıfıdır). Zaten donmuş DÖRT durumun ``Pb=None`` ile alınan KALINTISI
# donduruldu (``data/cfd_referans/euler_pb_none_kalinti.npz``, üreteci
# ``tools/cfd_referans_dondur.py --pb-none``): tek kalıntı çağrısı
# (milisaniye sınıfı) ama kalıntı çıkış hayaletini ``_outlet_state``
# üzerinden kurduğu için dal GERÇEKTEN koşar ve aritmetiği bit düzeyinde
# kilitlenir.
#
# Kapsam sınırı BEYANLIDIR: bu bekçi ``Pb is None`` + varsayılan
# ``outlet_subsonic_anchor='extrapolate'`` dalını kilitler. ``core_pressure``
# çapası beyanlı opt-in'dir (kendi bekçileri ``test_lule_back.py``de) ve
# bu dondurmanın kapsamında DEĞİLDİR — P6B1-02 raporunun "beyanlı opt-in
# oldukları için bulgu değil" listesiyle aynı çizgi.
# ---------------------------------------------------------------------------

PB_NONE_YOLU = REFERANS_DIZINI / 'euler_pb_none_kalinti.npz'


def pb_none_referansi_yukle():
    """(dudt sözlüğü, meta) — ``Pb=None`` kalıntı referansı."""
    assert PB_NONE_YOLU.exists(), (
        f'Pb=None kalıntı referansı yok: {PB_NONE_YOLU} — ürün ucunun '
        f'VARSAYILAN çıkış dalı referanssız kilitlenemez. Üretmek için: '
        f'python3 tools/cfd_referans_dondur.py --pb-none')
    with np.load(PB_NONE_YOLU) as z:
        meta = json.loads(str(z['meta_json']))
        dudt = {k: np.array(z[f'dudt_{k}']) for k in KUNYELER}
    return dudt, meta


def test_pb_none_referansi_DORT_VAKAYI_da_kapsiyor():
    """Kapsam beyanının kendisi kilitli: dört vakanın dördü de dosyada."""
    dudt, meta = pb_none_referansi_yukle()
    assert set(dudt) == set(KUNYELER), (
        f'Pb=None referansı {sorted(dudt)} vakasını taşıyor, beklenen '
        f'{sorted(KUNYELER)} — kapsam sessizce daraldı')
    assert meta['Pb'] is None, (
        'Pb=None referansı Pb VERİLMİŞ koşumdan üretilmiş — P6B1-02 kusuru '
        'aynen geri gelmiş olur')
    # Kaynak dosyalar kaymadıysa türev geçerlidir; kaydıysa bekçi söyler.
    for kunye in KUNYELER:
        yol = _referans_yolu(kunye)
        simdi = hashlib.sha256(yol.read_bytes()).hexdigest()
        beklenen = meta['kaynak_referans_sha256'][kunye]
        assert simdi == beklenen, (
            f'{kunye}: Pb=None kalıntısı {beklenen[:12]}… durumundan '
            f'türetilmişti, dosya şimdi {simdi[:12]}… — kaynak referans '
            f'yenilendiyse türev de yenilenmeli '
            f'(tools/cfd_referans_dondur.py --pb-none --zorla)')


@pytest.mark.parametrize('kunye', KUNYELER)
def test_pb_none_dali_BIT_ozdes(kunye):
    """Ürün varsayılanı ``Pb=None``: kalıntı BİT düzeyinde dondurulmuş."""
    referans, meta = pb_none_referansi_yukle()
    U_ref, U_meta = referans_yukle(kunye)
    vaka = EULER_REFERANS_VAKALARI[kunye]
    c = vaka['cozucu']
    grid = lule_gridi(vaka['ni'], vaka['nj'])

    dudt, _ = residual_axisym(U_ref, grid, c['gamma'], c['R'], c['P0'],
                              c['T0'], Pb=None)
    beklenen = referans[kunye]
    assert dudt.shape == beklenen.shape, (
        f'{kunye}: Pb=None kalıntı şekli {dudt.shape}, referans '
        f'{beklenen.shape} — ızgara kurulumu kaymış')

    if _ayni_platform(meta):
        assert np.array_equal(dudt, beklenen), (
            f'{kunye}: _outlet_state Pb is None dalı BİT düzeyinde değişti — '
            f'maks mutlak fark {float(np.max(np.abs(dudt - beklenen))):.3e}, '
            f'farklı hücre {int(np.sum(dudt != beklenen))}/{beklenen.size}. '
            f'Bu dal ürün ucunun (/api/cfd/nozzle) VARSAYILANIDIR. '
            f'Referans künyesi: commit {meta["git_commit"]}, '
            f'{meta["olusturma_tarihi_utc"]}. Değişiklik bilerekse '
            f'tools/cfd_referans_dondur.py --pb-none --zorla ile yenilenir '
            f've gerekçesi parti kaydına yazılır.')
        return
    # KAPSAM DIŞI (P13B1-03): hüküm yok, ölçüm var.
    olcek = np.max(np.abs(beklenen), axis=(0, 1))
    olcek = np.where(olcek > 0.0, olcek, 1.0)
    fark = float(np.max(np.abs(dudt - beklenen) / olcek))
    _sapma_kaydet(f'{kunye}/pb_none', {
        'tur': 'pb_none_kalinti',
        'referans_kapsami': f'{meta["platform"]}/{meta["machine"]}',
        'kosum_kapsami': f'{sys.platform}/{platform.machine()}',
        'max_bagil_fark': fark,
        'max_mutlak_fark': float(np.max(np.abs(dudt - beklenen))),
    })
    warnings.warn(
        f'{kunye} [Pb=None]: referans {meta["platform"]}/{meta["machine"]} '
        f'üzerinde üretildi, bu koşum {sys.platform}/{platform.machine()} — '
        f'saklı referansla bit karşılaştırması KAPSAM DIŞI, hüküm '
        f'{KAPSAM_DISI_HUKUM} (ölçülen {fark:.3e}, rapora yazıldı).',
        RuntimeWarning)
    assert U_meta['grid'] == {'ni': vaka['ni'], 'nj': vaka['nj']}
