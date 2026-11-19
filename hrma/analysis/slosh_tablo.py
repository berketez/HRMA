"""3.0.7 sözleşmesi — doluluğa göre çalkantı eşdeğer model tablosu.

Şema adı ``calkanti_esdeger_model_tablosu``, sürüm ``v307-2`` (değişiklik
günlüğü :data:`SEMA_DEGISIKLIK_GUNLUGU`; okuyucu ``v307-1`` tablolarını da
kabul eder).

Tasarım kaynağı (bağlayıcı, iki belgede aynı metin):
``docs/tasarim/v307/CALKANTI_6DOF_TASARIM.md`` §2 ve
``docs/tasarim/v307/TANK_GEOMETRI_TASARIM.md`` §F.

Bu modül sözleşmenin TEK uygulamasıdır (KARTLAR K1). Üreticiler
(K1 kapalı biçim silindir: ``slosh_analysis.silindir_tablosu``; K3 sayısal
SE çözümü: ``slosh_fem_axisym``) tabloyu :func:`tablo_olustur` ile kurar;
tüketiciler (K2 6-DOF, K4 motor aktarımı, K5 arayüz/dışa aktarım) yalnız
bu modülü içe aktarır. Alan adı, sebep kodu ya da ızgara burada değişir;
başka dosyada kopyası yazılmaz.

Eksen ve işaret kuralı (§2.1)
------------------------------
- Tank çerçevesi: z tank simetri ekseni, sıfır tankın en alt iç noktası
  (itki altında etkin yerçekiminin gösterdiği uç, araçta kıç tarafı),
  z yukarı (buruna doğru) pozitif. Bütün konumlar metre.
- Araç istasyonu: x burundan, kıça doğru pozitif; x = x_tank_taban − z.
- Tabloda frekans yerine κ1 = ω1²/g_eff [1/m] tutulur, L1 = 1/κ1.
  Tüketici ω1 = √(κ1 g_eff) hesaplar (:func:`omega1`). m1, L1 ve
  konumlar g_eff'ten bağımsızdır (Dodge 2000 Denk. (1.40), Tablo 3.2;
  yüksek Bond sayısı varsayımı).

Model tanımı (tek modlu eşdeğer model)
--------------------------------------
- ``m0_oran = 1 − m1_oran`` ve ``m0 z0 + m1 z1 = m_sıvı z_km`` (Dodge 2000
  Denk. (3.1), (3.2), birinci modla kesilmiş). İkinci mod alanları
  (``kappa2_1m``, ``m2_oran``, ``z2_m``) yalnız bilgi amaçlıdır, m0'a girmez
  (CALKANTI §A.1: 3.0.7'de 6-DOF'a yalnız birinci mod bağlanır).
- ``z_aski_m = z1_m + L1_m`` (sarkaç askı noktası).

Ara değer (§2.3)
----------------
Doluluk ekseninde monoton kübik Hermite (PCHIP, Fritsch–Carlson; SciPy
``PchipInterpolator``), log(doluluk) ekseninde. Bütün değerleri pozitif
alan log ölçekte (log-log), sıfır ya da negatif değer içeren alan
doğrusal ölçekte aranır (:func:`_ara_kur`; tasarım düzeltmesi, ölçüm
gerekçesi orada). L1, z_aski, m0_oran, z0 ve A_yuzey aranmaz; aranan alanlardan
yukarıdaki özdeşliklerle kurulur (tek büyüklük, tek sayı). Izgara
dışına dışdeğerleme yapılmaz: sonuç ``RET`` / ``IZGARA_DISI``.

Durum kuralı
------------
``GECERLI`` satırda sebep yoktur. ``BEYANLI`` satırda en az bir BEYAN
sınıfı kod vardır, RET sınıfı kod yoktur. ``RET`` satırda en az bir RET
sınıfı kod vardır; model alanları ``null`` olabilir, geometri alanları
(h, V, m, z_km, ataletler, yüzey) her satırda doludur.

Okuyucu kapıları
----------------
Boyut sınırı, UTF-8 zorunluluğu, JSON'da NaN/Infinity reddi, bilinmeyen
alan reddi, sayı alanında yalnız sonlu sayı. ``eval``/``pickle`` yok.
Her ret :class:`SloshTabloHatasi` ile adlı (``kod``, ``alan``) gelir.
"""

from __future__ import annotations

import csv
import io
import json
import math
import numbers

import numpy as np
from scipy.interpolate import PchipInterpolator

# ---------------------------------------------------------------------------
# Şema kimliği
# ---------------------------------------------------------------------------
SEMA_ADI = 'calkanti_esdeger_model_tablosu'
#: Yazıcının ürettiği sürüm.
SEMA_SURUMU = 'v307-2'
#: Şema değişiklik günlüğü (sürüm → değişiklik), eskiden yeniye. Alan adı
#: hiçbir sürümde değişmez; yalnız ekleme yapılır. Okuyucu buradaki her
#: sürümü kabul eder ve tablonun kendi sürümünü korur (bir v307-1 tablosu
#: okunup yazılınca yine v307-1'dir).
SEMA_DEGISIKLIK_GUNLUGU = {
    'v307-1': 'ilk sürüm (K1, 4 Kas 2026): şema, 29 noktalı ızgara, sebep '
              'kodları, sema/kunye/I0_kaynak/ek alanları, '
              'TANK_BASLARI_MODELLENMEDI',
    'v307-2': 'K6 (4 Kas 2026): sebep kodu AG_URETILEMEDI (RET; SE ağı '
              'kurulamayan satır) ve GURULTU_ESIKLE_KIYASLANABILIR (BEYAN; '
              'geometri girdisinin gürültü beyanı); okuyucu hata türleri '
              'adlı sabit (HATA_KODLARI); alan adı değişmedi',
}
DESTEKLENEN_SEMA_SURUMLERI = tuple(SEMA_DEGISIKLIK_GUNLUGU)
#: v307-1'den sonra eklenen sebep kodlarının eklendiği sürüm. Eski sürümlü
#: tabloda bu kodlar bulunamaz (``SEBEP_BILINMEYEN``).
SEBEP_KODU_EKLENDIGI_SURUM = {
    'AG_URETILEMEDI': 'v307-2',
    'GURULTU_ESIKLE_KIYASLANABILIR': 'v307-2',
}

# ---------------------------------------------------------------------------
# Doluluk ızgarası (§2.3) — hacim kesri V_sıvı/V_iç, uçlarda sık.
# 8 (alt uç) + 13 (0,20…0,80, 0,05 adım) + 8 (üst uç) = 29 nokta.
# Sabit tanım; TEK YER burasıdır.
# ---------------------------------------------------------------------------
DOLULUK_IZGARASI = (
    0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15,
    0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70,
    0.75, 0.80,
    0.85, 0.90, 0.925, 0.95, 0.97, 0.98, 0.99, 0.995,
)

# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
TANK_KIMLIKLERI = ('oksitleyici', 'yakit', 'n2o')

GEOMETRI_DIK_SILINDIR = 'dik_silindir_duz_taban'
GEOMETRI_PROFIL = 'eksenel_simetrik_profil'
GEOMETRI_TURLERI = (GEOMETRI_DIK_SILINDIR, GEOMETRI_PROFIL)

YONTEM_KAPALI_BICIM = 'kapali_bicim:Dodge2000_Tablo3.2+SP-8009_TabloI'
YONTEM_SAYISAL_SE = 'sayisal:SE_meridyen_m1'
YONTEMLER = (YONTEM_KAPALI_BICIM, YONTEM_SAYISAL_SE)

DURUM_GECERLI = 'GECERLI'
DURUM_BEYANLI = 'BEYANLI'
DURUM_RET = 'RET'
SATIR_DURUMLARI = (DURUM_GECERLI, DURUM_BEYANLI, DURUM_RET)

SINIF_RET = 'RET'
SINIF_BEYAN = 'BEYAN'

#: Makine-okur sebep kodları (§2.4 / §F.4): kod -> (sınıf, anlam).
#: ``TANK_BASLARI_MODELLENMEDI`` sözleşmeye v307-1'de eklendi (CALKANTI
#: §A.1.3'ün "eşdeğer derinlik h_eş ile BEYANLI" yolunun kodu; tasarım
#: belgesindeki tabloda eksikti).
SEBEP_KODLARI = {
    # Bond sayısı Bo = rho g_eff R^2 / sigma (Dodge 2000 Denk. (2.5)
    # çevresi; NASA SP-8009 §2.3 eşikleri, bkz. BOND_RET_ESIGI).
    'BOND_DUSUK_RET': (SINIF_RET, 'Bo < 10: yüzey gerilimi baskın, '
                       'yerçekimi dalgası modeli geçersiz'),
    'BOND_BEYAN': (SINIF_BEYAN, '10 <= Bo < 100: düşük yerçekimi '
                   'etkileri önemli olabilir'),
    'BOND_HESAPLANAMADI': (SINIF_BEYAN, 'yüzey gerilimi verilmedi; Bond '
                           'sayısı hesaplanamadı'),
    'IZGARA_DISI': (SINIF_RET, 'doluluk ızgaranın dışında; '
                    'dışdeğerleme yapılmaz'),
    'KUBBE_BOLGESI_SILINDIR_FORMULU_YOK': (
        SINIF_RET, 'serbest yüzey tank başı (kubbe) bölgesinde; silindir '
        'formülü uygulanmaz (CALKANTI §A.1.3)'),
    'TANK_BASLARI_MODELLENMEDI': (
        SINIF_BEYAN, 'silindir formülü eşdeğer derinlik h_eş = V/(πR²) '
        'ile kullanıldı; tank başlarının etkisi modellenmedi '
        '(CALKANTI §A.1.3)'),
    'EKSENEL_SIMETRIK_DEGIL': (SINIF_RET, 'tank eksenel simetrik değil'),
    'YUZEY_KAPALI_DEGIL': (SINIF_RET, 'tank yüzeyi kapalı değil'),
    'BAFL_GECERLILIK_DISI': (SINIF_BEYAN, 'bafl sönümü bağıntısının '
                             'geçerlilik aralığı dışında'),
    'GENLIK_DOGRUSAL_SINIR_DISI': (SINIF_BEYAN, 'dalga genliği doğrusal '
                                   'kuram sınırının (δ/R > 0,2) dışında'),
    # Tank geometrisi kapıları (TANK_GEOMETRI_TASARIM §B, §D.4).
    'EKSIK_BOLGE': (SINIF_RET, 'geometride eksik bölge'),
    'PROFIL_TEK_DEGERLI_DEGIL': (SINIF_RET, 'profil r(z) tek değerli '
                                 'değil'),
    'PROFIL_AG_HACIM_TUTARSIZ': (SINIF_RET, 'profil hacmi ile ağ hacmi '
                                 'tutarsız'),
    'AG_YAKINSAMA_ZAYIF': (SINIF_BEYAN, 'ağ inceltme yakınsaması kabul '
                           'ölçütünü sağlamadı'),
    'BIRIM_YOK': (SINIF_RET, 'girdi biriminin verilmesi zorunlu'),
    'STEP_MOZAIK_YOK': (SINIF_RET, 'STEP mozaikleyicisi yok'),
    # v307-2 (K6). K3b önerisi: SE sıvı ağı bu dolulukta kurulamadı
    # (eşleme ters dönmüş ya da dejenere eleman üretti; slosh_fem_axisym
    # SloshSEHatasi kod AG_GECERSIZ). Satırın model alanları null.
    'AG_URETILEMEDI': (SINIF_RET, 'bu dolulukta sayısal çözüm ağı '
                       'kurulamadı; model hesaplanmadı'),
    # v307-2 (K6). K3a: ölçüm gürültüsü σ_n/R simetri eşiğiyle
    # kıyaslanabilir (TANK §B.3.4, tank_geometry_import
    # TANK_GURULTU_BEYAN_ESIGI); simetri hükmü gürültü payıyla verildi.
    'GURULTU_ESIKLE_KIYASLANABILIR': (
        SINIF_BEYAN, 'geometri girdisinin ölçüm gürültüsü eksenel simetri '
        'eşiğiyle kıyaslanabilir; simetri hükmü gürültü payıyla verildi'),
}

# ---------------------------------------------------------------------------
# Hata türleri (SloshTabloHatasi.kod) — adlı sabitler, TEK YER (v307-2).
# Okuyucular (bu modülün JSON/CSV okuyucuları, tank_geometry_import,
# tank_mass_properties.ProfilHatasi) bu adları içe aktarır.
# ---------------------------------------------------------------------------
HATA_BOYUT_SINIRI = 'BOYUT_SINIRI'
HATA_BICIM_HATASI = 'BICIM_HATASI'
HATA_ALAN_EKSIK = 'ALAN_EKSIK'
HATA_ALAN_BILINMEYEN = 'ALAN_BILINMEYEN'
HATA_TUR_HATASI = 'TUR_HATASI'
HATA_DEGER_GECERSIZ = 'DEGER_GECERSIZ'
HATA_SURUM_UYUSMAZ = 'SURUM_UYUSMAZ'
HATA_IZGARA_UYUSMAZ = 'IZGARA_UYUSMAZ'
HATA_DEGISMEZ_IHLALI = 'DEGISMEZ_IHLALI'
HATA_DURUM_SEBEP_TUTARSIZ = 'DURUM_SEBEP_TUTARSIZ'
HATA_SEBEP_BILINMEYEN = 'SEBEP_BILINMEYEN'
HATA_GEFF_POZITIF_DEGIL = 'GEFF_POZITIF_DEGIL'
#: Hata türü → anlam. :class:`SloshTabloHatasi` yalnız bu kodlarla kurulur.
HATA_KODLARI = {
    HATA_BOYUT_SINIRI: 'dosya, liste ya da metin boyut sınırını aşıyor',
    HATA_BICIM_HATASI: 'dosya biçimi okunamadı (ayrıştırıcı hatası dahil)',
    HATA_ALAN_EKSIK: 'zorunlu alan yok',
    HATA_ALAN_BILINMEYEN: 'sözleşmede olmayan alan',
    HATA_TUR_HATASI: 'alanın türü yanlış (sayı, metin, liste, nesne)',
    HATA_DEGER_GECERSIZ: 'değer geçersiz (sonlu olmayan, aralık dışı, boş)',
    HATA_SURUM_UYUSMAZ: 'şema adı ya da sürümü desteklenmiyor',
    HATA_IZGARA_UYUSMAZ: 'satırlar doluluk ızgarasıyla uyuşmuyor',
    HATA_DEGISMEZ_IHLALI: 'özdeşlik ihlali (L1 = 1/κ1, m = ρV, ...)',
    HATA_DURUM_SEBEP_TUTARSIZ: 'satır durumu sebep kodlarıyla uyuşmuyor',
    HATA_SEBEP_BILINMEYEN: 'sebep kodu bu şema sürümünde yok',
    HATA_GEFF_POZITIF_DEGIL: 'etkin ivme pozitif ve sonlu değil',
}
#: Geometri ve profil okuyucularının kullandığı alt küme (K3a: içe
#: aktarıcının ``okuma_hatasi.kod`` alanı, ProfilHatasi.okuma_kodu).
OKUYUCU_HATA_KODLARI = (HATA_BOYUT_SINIRI, HATA_BICIM_HATASI,
                        HATA_DEGER_GECERSIZ, HATA_ALAN_EKSIK,
                        HATA_TUR_HATASI)

# ---------------------------------------------------------------------------
# Bond sayısı eşikleri — NASA SP-8009 (1968) §2.3: "Bond numbers as low as
# 100 would indicate that low-gravity effects may be of some significance,
# and Bond numbers as low as 10 would require consideration".
# TEK TANIM YERİ; slosh_analysis.SLOSH_BOND_NUMBER_LOWER_LIMIT buradan okur.
# ---------------------------------------------------------------------------
BOND_RET_ESIGI = 10.0
BOND_BEYAN_ESIGI = 100.0

# ---------------------------------------------------------------------------
# Model eşikleri (K1 kalem 4-7). TEK TANIM YERİ; slosh_analysis (K1),
# six_dof_slosh (K2) ve arayüz (K5) buradan okur.
# ---------------------------------------------------------------------------
#: Doğrusal kuram genlik sınırı δ/R (çeperdeki dalga genliği / yarıçap).
#: Dodge 2000 s. 33: dalga, genlik çapın yaklaşık %10'unu aşınca belirgin
#: biçimde doğrusal olmaktan çıkar; makul en büyük tasarım genliği 0,2 R.
GENLIK_DOGRUSAL_SINIR_ORANI = 0.2
#: Halka bafl (Miles) bağıntısının derinlik varsayımı: Dodge 2000 Denk.
#: (2.15) "h/R > 2 için" kurulur; h/R ≤ 2'de sonuç BEYANLI.
BAFL_HR_ALT_SINIRI = 2.0
#: Bafl serbest yüzeyin ÜSTÜNDEYKEN sönüm, h_s = 0 değerinden doğrusal
#: azalır ve bafl yüzeyin 0,8 δ üstündeyken sıfır olur (Dodge 2000 s. 33:
#: "say, conservatively 0.8 times the slosh amplitude δ").
BAFL_YUZEY_USTU_SIFIR_ORANI = 0.8
#: Yüzey baflda ya da biraz üstündeyken çalkantı frekansı çıplak tank
#: değerinden %15'e kadar yüksek olabilir (Dodge 2000 s. 33, Silveira vd.
#: 1961). Frekansa UYGULANMAZ; beyan olarak yazılır (CALKANTI §A.5).
BAFL_FREKANS_KAYMASI_UST = 0.15
#: I0 (SP-106 Tablo 6.1 son satırı, yaklaşık) yalnız Dodge 2000 Şekil 3.3
#: karşılaştırmasının kapsadığı h/d aralığında yayımlanır (betik v1 §5:
#: sayısallaştırılmış uçlar 0,251 ve 4,503; fark ≤ 0,063). Dışında I0 null,
#: gerekçesi I0_kaynak'ta. HRMA seçimi.
I0_HD_ARALIGI = (0.251, 4.503)

# ---------------------------------------------------------------------------
# Okuyucu ve doğrulayıcı sınırları (HRMA seçimi)
# ---------------------------------------------------------------------------
#: Tablo dosyasının (JSON/CSV) en büyük boyutu [bayt]. 29 satır + en çok
#: PROFIL_NOKTA_SINIRI profil noktası rahatça sığar; ötesi saldırgan girdi
#: sayılır. HRMA seçimi.
TABLO_DOSYA_BOYUT_SINIRI = 8 * 1024 * 1024
#: (r, z) profil noktası üst sınırı. HRMA seçimi.
PROFIL_NOKTA_SINIRI = 50_000
#: Metin alanlarının (ad, kaynak, I0_kaynak, künye satırı) en büyük boyu.
#: HRMA seçimi.
METIN_BOY_SINIRI = 2000
#: Künye satırı sayısı üst sınırı. HRMA seçimi.
KUNYE_SATIR_SINIRI = 200
#: Satır ``ek`` sözlüğündeki anahtar sayısı üst sınırı. HRMA seçimi.
EK_ANAHTAR_SINIRI = 64
#: Özdeşlik denetimlerinin bağıl toleransı (L1 = 1/κ1, V = doluluk·V_iç,
#: m = ρV, A = πR², z_aski = z1 + L1, m0 z0 + m1 z1 = z_km). Değerler
#: double hesapla kurulduğundan 1e-9 yuvarlama payının çok üstündedir;
#: bir alanın yanlış formülle doldurulmasını yakalar. HRMA seçimi.
DEGISMEZ_BAGIL_TOL = 1e-9
#: Izgara değeri eşleşmesinin mutlak toleransı. HRMA seçimi.
IZGARA_TOL = 1e-12

# ---------------------------------------------------------------------------
# Alan listeleri (sütun sırası = CSV sütun sırası)
# ---------------------------------------------------------------------------
UST_ZORUNLU = ('sema', 'sema_surumu', 'tank_id', 'geometri', 'sivi',
               'yontem', 'satirlar')
UST_ISTEGE_BAGLI = ('kunye',)

GEOMETRI_ZORUNLU = ('tur', 'R_ref_m', 'H_ic_m', 'V_ic_m3', 'kaynak')
GEOMETRI_ISTEGE_BAGLI = ('profil_rz_m',)

SIVI_ZORUNLU = ('ad', 'rho_kg_m3', 'sigma_N_m', 'nu_m2_s')

#: Her satırda dolu olan geometri alanları (RET satırında da).
SATIR_GEOMETRI = ('doluluk', 'h_m', 'V_sivi_m3', 'm_sivi_kg', 'z_km_m',
                  'I_km_donmus_kgm2', 'I_eksenel_donmus_kgm2',
                  'A_yuzey_m2', 'R_yuzey_m')
#: Model alanları: RET satırında null olabilir, öbür satırlarda dolu.
SATIR_MODEL = ('kappa1_1m', 'L1_m', 'm1_oran', 'z1_m', 'z_aski_m',
               'm0_oran', 'z0_m', 'Gamma1')
#: Her satırda bulunur, null olabilir.
SATIR_I0 = ('I0_kgm2', 'I0_kaynak')
#: İkinci mod: hepsi birlikte var ya da hiçbiri yok (bilgi amaçlı).
SATIR_MOD2 = ('kappa2_1m', 'm2_oran', 'z2_m')
SATIR_DURUM = ('durum', 'sebep')
#: Üreticiye özgü tanı alanları (ör. SE yakınsama mertebesi). Sözlük:
#: anahtar metin, değer sonlu sayı / metin / bool / null.
SATIR_EK = 'ek'

SATIR_SUTUNLARI = (SATIR_GEOMETRI + SATIR_MODEL + SATIR_I0 + SATIR_MOD2
                   + SATIR_DURUM + (SATIR_EK,))


# ---------------------------------------------------------------------------
# Hata
# ---------------------------------------------------------------------------
class SloshTabloHatasi(ValueError):
    """Sözleşme ihlali ya da okuma reddi — makine-okur ``kod`` ve ``alan``.

    Kodlar (:data:`HATA_KODLARI`, adlı sabitler ``HATA_*``):
    ``BOYUT_SINIRI``, ``BICIM_HATASI``, ``ALAN_EKSIK``,
    ``ALAN_BILINMEYEN``, ``TUR_HATASI``, ``DEGER_GECERSIZ``,
    ``SURUM_UYUSMAZ``, ``IZGARA_UYUSMAZ``, ``DEGISMEZ_IHLALI``,
    ``DURUM_SEBEP_TUTARSIZ``, ``SEBEP_BILINMEYEN``,
    ``GEFF_POZITIF_DEGIL``. Listede olmayan kodla kurulamaz.
    """

    def __init__(self, mesaj, kod, alan=None):
        if kod not in HATA_KODLARI:     # sözleşme dışı hata türü üretilmez
            raise TypeError(f'SloshTabloHatasi: sözleşmede olmayan hata '
                            f'türü {kod!r}')
        super().__init__(mesaj)
        self.kod = kod
        self.alan = alan

    def kunye(self):
        return {'kod': self.kod, 'alan': self.alan, 'mesaj': str(self)}


def _hata(kod, alan, mesaj):
    raise SloshTabloHatasi(f'{alan}: {mesaj}' if alan else mesaj,
                           kod=kod, alan=alan)


# ---------------------------------------------------------------------------
# Küçük kapılar
# ---------------------------------------------------------------------------
def _sayi(deger, alan, *, pozitif=False, negatif_degil=False):
    if isinstance(deger, (bool, np.bool_)) or not isinstance(deger,
                                                            numbers.Real):
        _hata('TUR_HATASI', alan, f'sayı bekleniyordu ({type(deger).__name__})')
    f = float(deger)
    if not math.isfinite(f):
        _hata('DEGER_GECERSIZ', alan, 'sonlu olmayan sayı')
    if pozitif and not f > 0.0:
        _hata('DEGER_GECERSIZ', alan, f'pozitif olmalı ({f!r})')
    if negatif_degil and f < 0.0:
        _hata('DEGER_GECERSIZ', alan, f'negatif olamaz ({f!r})')
    return f


def _sayi_ya_da_null(deger, alan, **kw):
    if deger is None:
        return None
    return _sayi(deger, alan, **kw)


def _metin(deger, alan, *, bos_olabilir=False):
    if not isinstance(deger, str):
        _hata('TUR_HATASI', alan, 'metin bekleniyordu')
    if not bos_olabilir and not deger.strip():
        _hata('DEGER_GECERSIZ', alan, 'boş metin')
    if len(deger) > METIN_BOY_SINIRI:
        _hata('BOYUT_SINIRI', alan, f'metin {METIN_BOY_SINIRI} karakteri '
              'aşıyor')
    return deger


def _sozluk(deger, alan, zorunlu, istege_bagli=()):
    if not isinstance(deger, dict):
        _hata('TUR_HATASI', alan, 'nesne (sözlük) bekleniyordu')
    for k in deger:
        if k not in zorunlu and k not in istege_bagli:
            _hata('ALAN_BILINMEYEN', f'{alan}.{k}' if alan else str(k),
                  'sözleşmede olmayan alan')
    for k in zorunlu:
        if k not in deger:
            _hata('ALAN_EKSIK', f'{alan}.{k}' if alan else k,
                  'zorunlu alan yok')
    return deger


def _yakin(a, b, olcek):
    return abs(a - b) <= DEGISMEZ_BAGIL_TOL * max(abs(olcek), 1e-300)


def _degismez(kosul, alan, mesaj):
    if not kosul:
        _hata('DEGISMEZ_IHLALI', alan, mesaj)


# ---------------------------------------------------------------------------
# Bond sayısı ve ω1 (tüketici yardımcıları)
# ---------------------------------------------------------------------------
def bond_sayisi(rho_kg_m3, g_eff, R_m, sigma_N_m):
    """Bo = ρ g_eff R²/σ (Dodge 2000 Denk. (2.5) çevresi; SP-8009 §2.3).

    σ ``None`` ise ``None`` döner (hesaplanamadı). R tankın en büyük iç
    yarıçapıdır (``geometri.R_ref_m``).
    """
    if sigma_N_m is None:
        return None
    rho = _sayi(rho_kg_m3, 'rho_kg_m3', pozitif=True)
    g = _sayi(g_eff, 'g_eff', pozitif=True)
    R = _sayi(R_m, 'R_m', pozitif=True)
    s = _sayi(sigma_N_m, 'sigma_N_m', pozitif=True)
    return rho * g * R * R / s


def bond_degerlendir(rho_kg_m3, g_eff, R_m, sigma_N_m):
    """Bond kapısı: ``{'Bo', 'durum', 'sebep'}``.

    Bo < 10 → RET ``BOND_DUSUK_RET``; 10 ≤ Bo < 100 → BEYANLI
    ``BOND_BEYAN``; σ yok → BEYANLI ``BOND_HESAPLANAMADI``; aksi GECERLI.
    """
    bo = bond_sayisi(rho_kg_m3, g_eff, R_m, sigma_N_m)
    if bo is None:
        return {'Bo': None, 'durum': DURUM_BEYANLI,
                'sebep': ['BOND_HESAPLANAMADI']}
    if bo < BOND_RET_ESIGI:
        return {'Bo': bo, 'durum': DURUM_RET, 'sebep': ['BOND_DUSUK_RET']}
    if bo < BOND_BEYAN_ESIGI:
        return {'Bo': bo, 'durum': DURUM_BEYANLI, 'sebep': ['BOND_BEYAN']}
    return {'Bo': bo, 'durum': DURUM_GECERLI, 'sebep': []}


def omega1(kappa1_1m, g_eff):
    """ω1 = √(κ1 g_eff) [rad/s] (§2.1). g_eff ≤ 0'da model geçersizdir
    (CALKANTI §A.1.5): ``GEFF_POZITIF_DEGIL`` ile reddedilir."""
    k = _sayi(kappa1_1m, 'kappa1_1m', pozitif=True)
    if isinstance(g_eff, (bool, np.bool_)) \
            or not isinstance(g_eff, numbers.Real) \
            or not math.isfinite(float(g_eff)) or not float(g_eff) > 0.0:
        _hata('GEFF_POZITIF_DEGIL', 'g_eff', 'etkin ivme pozitif ve sonlu '
              'olmalı; f_x ≤ 0 iken çalkantı modeli geçersizdir')
    return math.sqrt(k * float(g_eff))


def durum_birlestir(sebepler):
    """Sebep kodu listesinden durum: RET > BEYANLI > GECERLI."""
    siniflar = set()
    for s in sebepler:
        if s not in SEBEP_KODLARI:
            _hata('SEBEP_BILINMEYEN', 'sebep', f'bilinmeyen kod {s!r}')
        siniflar.add(SEBEP_KODLARI[s][0])
    if SINIF_RET in siniflar:
        return DURUM_RET
    if SINIF_BEYAN in siniflar:
        return DURUM_BEYANLI
    return DURUM_GECERLI


def _sebep_sirala(sebepler):
    """Kodları SEBEP_KODLARI sırasıyla, tekrarsız döndürür."""
    kume = set(sebepler)
    return [k for k in SEBEP_KODLARI if k in kume]


# ---------------------------------------------------------------------------
# Doğrulayıcı
# ---------------------------------------------------------------------------
def _dogrula_geometri(g):
    _sozluk(g, 'geometri', GEOMETRI_ZORUNLU, GEOMETRI_ISTEGE_BAGLI)
    tur = g['tur']
    if tur not in GEOMETRI_TURLERI:
        _hata('DEGER_GECERSIZ', 'geometri.tur', f'bilinmeyen tür {tur!r}')
    out = {'tur': tur,
           'R_ref_m': _sayi(g['R_ref_m'], 'geometri.R_ref_m', pozitif=True),
           'H_ic_m': _sayi(g['H_ic_m'], 'geometri.H_ic_m', pozitif=True),
           'V_ic_m3': _sayi(g['V_ic_m3'], 'geometri.V_ic_m3', pozitif=True),
           'kaynak': _metin(g['kaynak'], 'geometri.kaynak')}
    R, H, V = out['R_ref_m'], out['H_ic_m'], out['V_ic_m3']
    if tur == GEOMETRI_DIK_SILINDIR:
        if 'profil_rz_m' in g:
            _hata('ALAN_BILINMEYEN', 'geometri.profil_rz_m',
                  'dik silindir türünde profil verilmez')
        _degismez(_yakin(V, math.pi * R * R * H, V), 'geometri.V_ic_m3',
                  'dik silindirde V_iç = πR²H olmalı')
    else:
        if 'profil_rz_m' not in g:
            _hata('ALAN_EKSIK', 'geometri.profil_rz_m',
                  'profil türünde (r, z) profil zorunlu')
        p = g['profil_rz_m']
        if not isinstance(p, list):
            _hata('TUR_HATASI', 'geometri.profil_rz_m', 'liste bekleniyordu')
        if len(p) > PROFIL_NOKTA_SINIRI:
            _hata('BOYUT_SINIRI', 'geometri.profil_rz_m',
                  f'{PROFIL_NOKTA_SINIRI} noktayı aşıyor')
        if len(p) < 2:
            _hata('DEGER_GECERSIZ', 'geometri.profil_rz_m',
                  'en az iki nokta gerekli')
        prof = []
        for i, nokta in enumerate(p):
            a = f'geometri.profil_rz_m[{i}]'
            if not isinstance(nokta, (list, tuple)) or len(nokta) != 2:
                _hata('TUR_HATASI', a, '[r, z] çifti bekleniyordu')
            prof.append([_sayi(nokta[0], a + '.r', negatif_degil=True),
                         _sayi(nokta[1], a + '.z')])
        rs = [q[0] for q in prof]
        zs = [q[1] for q in prof]
        _degismez(_yakin(max(rs), R, R), 'geometri.R_ref_m',
                  'R_ref profilin en büyük yarıçapı olmalı')
        _degismez(abs(min(zs)) <= DEGISMEZ_BAGIL_TOL * H, 'geometri.profil_rz_m',
                  'tank çerçevesinde en alt iç nokta z = 0 olmalı (§2.1)')
        _degismez(_yakin(max(zs), H, H), 'geometri.H_ic_m',
                  'H_iç profilin en üst noktası olmalı')
        out['profil_rz_m'] = prof
    return out


def _dogrula_sivi(s):
    _sozluk(s, 'sivi', SIVI_ZORUNLU)
    return {'ad': _metin(s['ad'], 'sivi.ad'),
            'rho_kg_m3': _sayi(s['rho_kg_m3'], 'sivi.rho_kg_m3',
                               pozitif=True),
            'sigma_N_m': _sayi_ya_da_null(s['sigma_N_m'], 'sivi.sigma_N_m',
                                          pozitif=True),
            'nu_m2_s': _sayi_ya_da_null(s['nu_m2_s'], 'sivi.nu_m2_s',
                                        pozitif=True)}


def _dogrula_ek(ek, alan):
    if not isinstance(ek, dict):
        _hata('TUR_HATASI', alan, 'nesne (sözlük) bekleniyordu')
    if len(ek) > EK_ANAHTAR_SINIRI:
        _hata('BOYUT_SINIRI', alan, f'{EK_ANAHTAR_SINIRI} anahtarı aşıyor')
    out = {}
    for k, v in ek.items():
        _metin(k, f'{alan} anahtarı')
        if v is None or isinstance(v, bool):
            out[k] = v
        elif isinstance(v, str):
            out[k] = _metin(v, f'{alan}.{k}', bos_olabilir=True)
        else:
            out[k] = _sayi(v, f'{alan}.{k}')
    return out


def _surumde_var(kod, surum):
    """Sebep kodu ``surum`` şemasında tanımlı mı (SEBEP_KODU_EKLENDIGI_SURUM)."""
    eklendigi = SEBEP_KODU_EKLENDIGI_SURUM.get(kod)
    if eklendigi is None:
        return True
    return (DESTEKLENEN_SEMA_SURUMLERI.index(surum)
            >= DESTEKLENEN_SEMA_SURUMLERI.index(eklendigi))


def _dogrula_satir(i, s, geo, sivi, yontem, surum=SEMA_SURUMU):
    a = f'satirlar[{i}]'
    zorunlu = SATIR_GEOMETRI + SATIR_MODEL + SATIR_I0 + SATIR_DURUM
    _sozluk(s, a, zorunlu, SATIR_MOD2 + (SATIR_EK,))
    out = {}
    for k in SATIR_GEOMETRI:
        out[k] = _sayi(s[k], f'{a}.{k}', negatif_degil=True)
    durum = s['durum']
    if durum not in SATIR_DURUMLARI:
        _hata('DEGER_GECERSIZ', f'{a}.durum', f'bilinmeyen durum {durum!r}')
    sebep = s['sebep']
    if not isinstance(sebep, list):
        _hata('TUR_HATASI', f'{a}.sebep', 'liste bekleniyordu')
    for kod in sebep:
        if not isinstance(kod, str) or kod not in SEBEP_KODLARI:
            _hata('SEBEP_BILINMEYEN', f'{a}.sebep', f'bilinmeyen kod {kod!r}')
        if not _surumde_var(kod, surum):
            _hata('SEBEP_BILINMEYEN', f'{a}.sebep',
                  f'{kod!r} {surum} şemasında yok '
                  f'({SEBEP_KODU_EKLENDIGI_SURUM[kod]} ile eklendi)')
    if len(set(sebep)) != len(sebep):
        _hata('DEGER_GECERSIZ', f'{a}.sebep', 'tekrarlanan kod')
    beklenen = durum_birlestir(sebep)
    if beklenen != durum:
        _hata('DURUM_SEBEP_TUTARSIZ', f'{a}.durum',
              f'sebep kodları {sebep!r} durumu {beklenen} gerektirir, '
              f'satırda {durum}')
    out['durum'] = durum
    out['sebep'] = list(sebep)

    ret = durum == DURUM_RET
    for k in SATIR_MODEL:
        if s[k] is None:
            if not ret:
                _hata('DEGER_GECERSIZ', f'{a}.{k}',
                      'yalnız RET satırında null olabilir')
            out[k] = None
        else:
            out[k] = _sayi(s[k], f'{a}.{k}')
    out['I0_kgm2'] = _sayi_ya_da_null(s['I0_kgm2'], f'{a}.I0_kgm2',
                                      negatif_degil=True)
    if s['I0_kaynak'] is None:
        if out['I0_kgm2'] is not None:
            _hata('ALAN_EKSIK', f'{a}.I0_kaynak',
                  'I0 verildiğinde kaynağı zorunlu')
        out['I0_kaynak'] = None
    else:
        out['I0_kaynak'] = _metin(s['I0_kaynak'], f'{a}.I0_kaynak')
    var = [k for k in SATIR_MOD2 if k in s]
    if var:
        if len(var) != len(SATIR_MOD2):
            _hata('ALAN_EKSIK', a, 'ikinci mod alanları birlikte verilir: '
                  + ', '.join(SATIR_MOD2))
        for k in SATIR_MOD2:
            out[k] = _sayi(s[k], f'{a}.{k}')
    if SATIR_EK in s:
        out[SATIR_EK] = _dogrula_ek(s[SATIR_EK], f'{a}.ek')

    # --- geometri özdeşlikleri (her satır) ---------------------------------
    d = out['doluluk']
    _degismez(d > 0.0, f'{a}.doluluk', 'pozitif olmalı')
    V_ic, R, H = geo['V_ic_m3'], geo['R_ref_m'], geo['H_ic_m']
    _degismez(_yakin(out['V_sivi_m3'], d * V_ic, V_ic), f'{a}.V_sivi_m3',
              'V_sıvı = doluluk · V_iç olmalı')
    _degismez(_yakin(out['m_sivi_kg'], sivi['rho_kg_m3'] * out['V_sivi_m3'],
                     out['m_sivi_kg']), f'{a}.m_sivi_kg',
              'm_sıvı = ρ V_sıvı olmalı')
    h = out['h_m']
    _degismez(0.0 < h <= H * (1.0 + DEGISMEZ_BAGIL_TOL), f'{a}.h_m',
              '0 < h ≤ H_iç olmalı')
    _degismez(0.0 < out['z_km_m'] < h * (1.0 + DEGISMEZ_BAGIL_TOL),
              f'{a}.z_km_m', '0 < z_km < h olmalı')
    _degismez(out['R_yuzey_m'] <= R * (1.0 + DEGISMEZ_BAGIL_TOL),
              f'{a}.R_yuzey_m', 'R_yüzey ≤ R_ref olmalı')
    _degismez(_yakin(out['A_yuzey_m2'], math.pi * out['R_yuzey_m'] ** 2,
                     math.pi * R * R), f'{a}.A_yuzey_m2',
              'A_yüzey = π R_yüzey² olmalı')
    if geo['tur'] == GEOMETRI_DIK_SILINDIR:
        m = out['m_sivi_kg']
        _degismez(_yakin(h, out['V_sivi_m3'] / (math.pi * R * R), H),
                  f'{a}.h_m', 'dik silindirde h = V/(πR²) olmalı')
        _degismez(_yakin(out['z_km_m'], 0.5 * h, H), f'{a}.z_km_m',
                  'dik silindirde z_km = h/2 olmalı')
        _degismez(_yakin(out['R_yuzey_m'], R, R), f'{a}.R_yuzey_m',
                  'dik silindirde R_yüzey = R olmalı')
        _degismez(_yakin(out['I_km_donmus_kgm2'],
                         m * (R * R / 4.0 + h * h / 12.0),
                         m * (R * R + H * H)), f'{a}.I_km_donmus_kgm2',
                  'dik silindirde I_km = m (R²/4 + h²/12) olmalı')
        _degismez(_yakin(out['I_eksenel_donmus_kgm2'], 0.5 * m * R * R,
                         m * R * R), f'{a}.I_eksenel_donmus_kgm2',
                  'dik silindirde I_eksenel = m R²/2 olmalı')

    # --- model özdeşlikleri (RET olmayan satır) ----------------------------
    if not ret:
        k1 = out['kappa1_1m']
        _degismez(k1 > 0.0, f'{a}.kappa1_1m', 'pozitif olmalı')
        _degismez(_yakin(out['L1_m'], 1.0 / k1, 1.0 / k1), f'{a}.L1_m',
                  'L1 = 1/κ1 olmalı')
        m1 = out['m1_oran']
        _degismez(0.0 < m1 < 1.0, f'{a}.m1_oran', '0 < m1/m_sıvı < 1 olmalı')
        _degismez(abs(out['m0_oran'] - (1.0 - m1)) <= DEGISMEZ_BAGIL_TOL,
                  f'{a}.m0_oran', 'm0_oran = 1 − m1_oran olmalı (tek modlu '
                  'model)')
        olcek = max(H, out['L1_m'])
        _degismez(_yakin(out['z_aski_m'], out['z1_m'] + out['L1_m'], olcek),
                  f'{a}.z_aski_m', 'z_aski = z1 + L1 olmalı')
        _degismez(_yakin(out['m0_oran'] * out['z0_m'] + m1 * out['z1_m'],
                         out['z_km_m'], H), f'{a}.z0_m',
                  'm0 z0 + m1 z1 = z_km olmalı (Dodge (3.2))')
        _degismez(out['Gamma1'] > 0.0, f'{a}.Gamma1', 'pozitif olmalı')
        if 'kappa2_1m' in out:
            _degismez(out['kappa2_1m'] > k1, f'{a}.kappa2_1m',
                      'κ2 > κ1 olmalı')
            _degismez(0.0 < out['m2_oran'] < 1.0 - m1, f'{a}.m2_oran',
                      '0 < m2_oran < 1 − m1_oran olmalı')
        if (yontem == YONTEM_KAPALI_BICIM and geo['tur'] == GEOMETRI_PROFIL
                and 'TANK_BASLARI_MODELLENMEDI' not in out['sebep']):
            _hata('DURUM_SEBEP_TUTARSIZ', f'{a}.sebep',
                  'profilli tankta kapalı biçim silindir formülü yalnız '
                  'TANK_BASLARI_MODELLENMEDI beyanıyla kullanılır '
                  '(CALKANTI §A.1.3)')
    return out


def dogrula(veri):
    """Sözlüğü sözleşmeye göre denetler; normalleştirilmiş derin kopya döner.

    Sayılar ``float``'a çevrilir; bilinmeyen alan, eksik alan, sonlu olmayan
    sayı, ızgara uyuşmazlığı ya da özdeşlik ihlali
    :class:`SloshTabloHatasi` ile reddedilir.
    """
    _sozluk(veri, '', UST_ZORUNLU, UST_ISTEGE_BAGLI)
    if veri['sema'] != SEMA_ADI:
        _hata('SURUM_UYUSMAZ', 'sema', f'{SEMA_ADI!r} bekleniyordu')
    surum = veri['sema_surumu']
    if not isinstance(surum, str) or surum not in DESTEKLENEN_SEMA_SURUMLERI:
        _hata('SURUM_UYUSMAZ', 'sema_surumu',
              f'desteklenen sürümler {DESTEKLENEN_SEMA_SURUMLERI!r}')
    if veri['tank_id'] not in TANK_KIMLIKLERI:
        _hata('DEGER_GECERSIZ', 'tank_id', f'bilinmeyen tank {veri["tank_id"]!r}')
    if veri['yontem'] not in YONTEMLER:
        _hata('DEGER_GECERSIZ', 'yontem', f'bilinmeyen yöntem '
              f'{veri["yontem"]!r}')
    geo = _dogrula_geometri(veri['geometri'])
    sivi = _dogrula_sivi(veri['sivi'])
    out = {'sema': SEMA_ADI, 'sema_surumu': surum,
           'tank_id': veri['tank_id'], 'geometri': geo, 'sivi': sivi,
           'yontem': veri['yontem']}
    if 'kunye' in veri:
        k = veri['kunye']
        if not isinstance(k, list):
            _hata('TUR_HATASI', 'kunye', 'metin listesi bekleniyordu')
        if len(k) > KUNYE_SATIR_SINIRI:
            _hata('BOYUT_SINIRI', 'kunye', f'{KUNYE_SATIR_SINIRI} satırı aşıyor')
        out['kunye'] = [_metin(x, f'kunye[{j}]') for j, x in enumerate(k)]
    satirlar = veri['satirlar']
    if not isinstance(satirlar, list):
        _hata('TUR_HATASI', 'satirlar', 'liste bekleniyordu')
    if len(satirlar) != len(DOLULUK_IZGARASI):
        _hata('IZGARA_UYUSMAZ', 'satirlar', f'{len(DOLULUK_IZGARASI)} satır '
              f'bekleniyordu, {len(satirlar)} geldi')
    norm = []
    for i, s in enumerate(satirlar):
        if not isinstance(s, dict):
            _hata('TUR_HATASI', f'satirlar[{i}]', 'nesne bekleniyordu')
        d = s.get('doluluk')
        if (isinstance(d, (bool, np.bool_)) or not isinstance(d, numbers.Real)
                or not abs(float(d) - DOLULUK_IZGARASI[i]) <= IZGARA_TOL):
            _hata('IZGARA_UYUSMAZ', f'satirlar[{i}].doluluk',
                  f'ızgara değeri {DOLULUK_IZGARASI[i]!r} bekleniyordu')
        norm.append(_dogrula_satir(i, s, geo, sivi, veri['yontem'], surum))
    for i in range(1, len(norm)):
        _degismez(norm[i]['h_m'] > norm[i - 1]['h_m'], f'satirlar[{i}].h_m',
                  'h dolulukla kesin artmalı')
    out['satirlar'] = norm
    return out


# ---------------------------------------------------------------------------
# Ara değer kuralı (§2.3, K1 tasarım düzeltmesi 4 Kas)
# ---------------------------------------------------------------------------
def _ara_kur(x, y):
    """PCHIP, log(doluluk) ekseninde; değerlerin hepsi > 0 ise log ölçekte
    (log-log), değilse doğrusal ölçekte. Tek değişkenli çağrılabilir döner.

    Gerekçe (ölçüldü, ``docs/scofield/raw/OH/V307/calkanti-model/
    ara_deger_olcum.py``): dik silindirde sığ uçta κ1 ∝ h, z1 ∝ h³,
    Γ1 ∝ 1/h, kürede h ∝ doluluk^(1/2) — kuvvet yasaları log-log'da
    doğrudur. Tasarımın ilk metnindeki "κ1 log, doluluk doğrusal" seçimi
    sığ uçta %2,3 hata verdi; log-log silindirde (H/R 0,25–10) κ1 için
    ≤ 1,8·10⁻³, z1 için ≤ 2,2·10⁻³ bağıl hata verir.
    """
    lx = np.log(np.asarray(x, dtype=float))
    yv = np.asarray(y, dtype=float)
    if np.all(yv > 0.0):
        f = PchipInterpolator(lx, np.log(yv), extrapolate=False)
        return lambda d: math.exp(float(f(math.log(d))))
    f = PchipInterpolator(lx, yv, extrapolate=False)
    return lambda d: float(f(math.log(d)))


# ---------------------------------------------------------------------------
# Tablo nesnesi
# ---------------------------------------------------------------------------
class SloshTablo:
    """Doğrulanmış sözleşme tablosu. Yalnız :func:`tablo_olustur`,
    :meth:`sozlukten`, :func:`json_oku`, :func:`csv_oku` ile kurulur."""

    def __init__(self, dogrulanmis):
        self._v = dogrulanmis
        self._x = np.array([s['doluluk'] for s in dogrulanmis['satirlar']])
        self._geo_ara = {}
        for k in ('h_m', 'z_km_m', 'I_km_donmus_kgm2',
                  'I_eksenel_donmus_kgm2', 'R_yuzey_m'):
            self._geo_ara[k] = _ara_kur(
                self._x, [s[k] for s in dogrulanmis['satirlar']])
        self._kosular = self._model_kosulari()

    # -- kurucular ---------------------------------------------------------
    @classmethod
    def sozlukten(cls, veri):
        return cls(dogrula(veri))

    # -- erişim ------------------------------------------------------------
    @property
    def tank_id(self):
        return self._v['tank_id']

    @property
    def yontem(self):
        return self._v['yontem']

    @property
    def geometri(self):
        return json.loads(json.dumps(self._v['geometri']))

    @property
    def sivi(self):
        return dict(self._v['sivi'])

    @property
    def satirlar(self):
        return json.loads(json.dumps(self._v['satirlar']))

    def sozluk(self):
        """Derin kopya (JSON'a hazır)."""
        return json.loads(json.dumps(self._v))

    def doluluk_kutleden(self, m_sivi_kg):
        """doluluk = m/(ρ V_iç) (CALKANTI §A.2)."""
        m = _sayi(m_sivi_kg, 'm_sivi_kg', negatif_degil=True)
        return m / (self._v['sivi']['rho_kg_m3'] * self._v['geometri']['V_ic_m3'])

    # -- ara değer ---------------------------------------------------------
    def _model_kosulari(self):
        """RET olmayan ardışık satır kümeleri ve her birinin PCHIP'leri."""
        sat = self._v['satirlar']
        kosular, bas = [], None
        for i, s in enumerate(sat + [None]):
            iyi = s is not None and s['durum'] != DURUM_RET
            if iyi and bas is None:
                bas = i
            if not iyi and bas is not None:
                kosular.append((bas, i - 1))
                bas = None
        out = []
        for i0, i1 in kosular:
            x = self._x[i0:i1 + 1]
            parca = sat[i0:i1 + 1]
            k = {'i0': i0, 'i1': i1, 'ara': {}}
            if len(x) >= 2:
                for alan in ('kappa1_1m', 'm1_oran', 'z1_m', 'Gamma1'):
                    k['ara'][alan] = _ara_kur(x, [s[alan] for s in parca])
                if all(s['I0_kgm2'] is not None for s in parca):
                    k['ara']['I0_kgm2'] = _ara_kur(
                        x, [s['I0_kgm2'] for s in parca])
                if all('kappa2_1m' in s for s in parca):
                    for alan in SATIR_MOD2:
                        k['ara'][alan] = _ara_kur(x, [s[alan] for s in parca])
            out.append(k)
        return out

    def ara(self, doluluk):
        """Verilen dolulukta eşdeğer model (§2.3).

        Dönen sözlüğün alanları satır alanlarıyla aynıdır. Izgara dışında
        bütün sayılar ``None``, durum ``RET``/``IZGARA_DISI``. Bir RET
        satırına dokunan aralıkta model alanları ``None``, durum RET, sebep
        komşu satırların birleşimi. Düğümde satırın kendi değerleri döner.
        """
        d = _sayi(doluluk, 'doluluk')
        sat = self._v['satirlar']
        bos = {k: None for k in SATIR_GEOMETRI + SATIR_MODEL + SATIR_I0}
        if d < DOLULUK_IZGARASI[0] or d > DOLULUK_IZGARASI[-1]:
            bos.update(doluluk=d, durum=DURUM_RET, sebep=['IZGARA_DISI'])
            return bos
        # Düğüm mü?
        for i, s in enumerate(sat):
            if d == s['doluluk']:
                return {k: v for k, v in json.loads(json.dumps(s)).items()
                        if k != SATIR_EK}
        i = int(np.searchsorted(self._x, d)) - 1   # x[i] < d < x[i+1]
        komsu = (sat[i], sat[i + 1])
        sebep = _sebep_sirala(komsu[0]['sebep'] + komsu[1]['sebep'])
        durum = durum_birlestir(sebep)
        geo = self._v['geometri']
        V = d * geo['V_ic_m3']
        out = dict(bos)
        out['doluluk'] = d
        out['V_sivi_m3'] = V
        out['m_sivi_kg'] = self._v['sivi']['rho_kg_m3'] * V
        for k, f in self._geo_ara.items():
            out[k] = f(d)
        out['A_yuzey_m2'] = math.pi * out['R_yuzey_m'] ** 2
        out['durum'] = durum
        out['sebep'] = sebep
        if durum == DURUM_RET:
            return out
        kosu = next(k for k in self._kosular if k['i0'] <= i < k['i1'])
        a = kosu['ara']
        k1 = a['kappa1_1m'](d)
        m1 = a['m1_oran'](d)
        z1 = a['z1_m'](d)
        out['kappa1_1m'] = k1
        out['L1_m'] = 1.0 / k1
        out['m1_oran'] = m1
        out['m0_oran'] = 1.0 - m1
        out['z1_m'] = z1
        out['z_aski_m'] = z1 + 1.0 / k1
        out['z0_m'] = (out['z_km_m'] - m1 * z1) / (1.0 - m1)
        out['Gamma1'] = a['Gamma1'](d)
        if 'I0_kgm2' in a:
            out['I0_kgm2'] = a['I0_kgm2'](d)
            kaynaklar = {sat[i]['I0_kaynak'], sat[i + 1]['I0_kaynak']}
            out['I0_kaynak'] = ' | '.join(sorted(kaynaklar))
        if 'kappa2_1m' in a:
            for alan in SATIR_MOD2:
                out[alan] = a[alan](d)
        return out


def tablo_olustur(tank_id, geometri, sivi, yontem, satirlar, kunye=None):
    """Üretici yardımcısı: alanlardan tabloyu kurar ve doğrular."""
    veri = {'sema': SEMA_ADI, 'sema_surumu': SEMA_SURUMU, 'tank_id': tank_id,
            'geometri': geometri, 'sivi': sivi, 'yontem': yontem,
            'satirlar': satirlar}
    if kunye is not None:
        veri['kunye'] = kunye
    return SloshTablo.sozlukten(veri)


def satirlara_sebep_ekle(tablo, kodlar, kunye_satiri=None):
    """Tablo düzeyindeki bir kodu (ör. geometri girdisinin gürültü beyanı)
    bütün satırlara ekler; satır durumu kodlardan yeniden türetilir (RET >
    BEYANLI > GECERLI). Yeni doğrulanmış :class:`SloshTablo` döner; girdi
    tablo değişmez.

    Yalnız BEYAN sınıfı kod kabul edilir: RET sınıfı kod bütün satırları
    RET yapardı ve RET satırının model alanlarını üretici boşaltır, bu
    yardımcı değil (``SEBEP_BILINMEYEN`` / ``DEGER_GECERSIZ`` ile ret).
    """
    if not isinstance(tablo, SloshTablo):
        _hata('TUR_HATASI', 'tablo', 'SloshTablo bekleniyordu')
    if isinstance(kodlar, str) or not isinstance(kodlar, (list, tuple)):
        _hata('TUR_HATASI', 'kodlar', 'kod listesi bekleniyordu')
    for kod in kodlar:
        if not isinstance(kod, str) or kod not in SEBEP_KODLARI:
            _hata('SEBEP_BILINMEYEN', 'kodlar', f'bilinmeyen kod {kod!r}')
        if SEBEP_KODLARI[kod][0] != SINIF_BEYAN:
            _hata('DEGER_GECERSIZ', 'kodlar', f'{kod!r} BEYAN sınıfı değil')
    v = tablo.sozluk()
    for s in v['satirlar']:
        s['sebep'] = _sebep_sirala(list(s['sebep']) + list(kodlar))
        s['durum'] = durum_birlestir(s['sebep'])
    if kunye_satiri is not None:
        v['kunye'] = list(v.get('kunye', [])) + [kunye_satiri]
    return SloshTablo.sozlukten(v)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------
def _sabit_reddet(ad):
    raise SloshTabloHatasi(f'JSON içinde sayı olmayan sabit {ad!r}',
                           kod='DEGER_GECERSIZ', alan=None)


def json_yaz(tablo):
    """Tabloyu UTF-8 JSON metnine çevirir (NaN/Infinity yazılmaz)."""
    return json.dumps(tablo.sozluk(), ensure_ascii=False, allow_nan=False,
                      indent=1)


def json_oku(metin_ya_da_bayt):
    """JSON metninden (str ya da bytes) doğrulanmış :class:`SloshTablo`."""
    metin = _boyut_ve_kod(metin_ya_da_bayt)
    try:
        veri = json.loads(metin, parse_constant=_sabit_reddet)
    except SloshTabloHatasi:
        raise
    except (ValueError, RecursionError) as e:
        raise SloshTabloHatasi(f'JSON ayrıştırılamadı: {e}',
                               kod='BICIM_HATASI') from None
    if not isinstance(veri, dict):
        raise SloshTabloHatasi('JSON kökü nesne olmalı', kod='BICIM_HATASI')
    return SloshTablo.sozlukten(veri)


def _boyut_ve_kod(girdi):
    if isinstance(girdi, (bytes, bytearray)):
        if len(girdi) > TABLO_DOSYA_BOYUT_SINIRI:
            raise SloshTabloHatasi('dosya boyut sınırını aşıyor',
                                   kod='BOYUT_SINIRI')
        try:
            return bytes(girdi).decode('utf-8')
        except UnicodeDecodeError:
            raise SloshTabloHatasi('dosya UTF-8 değil',
                                   kod='BICIM_HATASI') from None
    if not isinstance(girdi, str):
        raise SloshTabloHatasi('metin ya da bayt bekleniyordu',
                               kod='TUR_HATASI')
    if len(girdi.encode('utf-8')) > TABLO_DOSYA_BOYUT_SINIRI:
        raise SloshTabloHatasi('dosya boyut sınırını aşıyor',
                               kod='BOYUT_SINIRI')
    return girdi


# ---------------------------------------------------------------------------
# CSV — ondalık nokta, UTF-8; ilk satır şema kimliği, ikinci satır
# '# meta: {json}' (tablo düzeyi alanlar), sonra başlık (SATIR_SUTUNLARI)
# ve 29 satır. null = boş hücre; sebep ';' ile birleşik; ek = JSON nesnesi.
# ---------------------------------------------------------------------------
CSV_KIMLIK_SATIRI = f'# {SEMA_ADI} {SEMA_SURUMU}'
CSV_META_ONEKI = '# meta: '
_CSV_METIN_ALANLARI = ('I0_kaynak', 'durum')
#: Okuyucunun kabul ettiği kimlik satırları (sürüm → satır).
_CSV_KIMLIK_SATIRLARI = {f'# {SEMA_ADI} {s}': s
                         for s in DESTEKLENEN_SEMA_SURUMLERI}


def csv_yaz(tablo):
    v = tablo.sozluk()
    meta = {k: v[k] for k in v if k != 'satirlar'}
    tampon = io.StringIO()
    tampon.write(f'# {SEMA_ADI} {v["sema_surumu"]}\n')
    tampon.write(CSV_META_ONEKI + json.dumps(meta, ensure_ascii=False,
                                             allow_nan=False) + '\n')
    w = csv.writer(tampon, lineterminator='\n')
    w.writerow(SATIR_SUTUNLARI)
    for s in v['satirlar']:
        satir = []
        for k in SATIR_SUTUNLARI:
            deger = s.get(k)
            if deger is None:
                satir.append('')
            elif k == 'sebep':
                satir.append(';'.join(deger))
            elif k == SATIR_EK:
                satir.append(json.dumps(deger, ensure_ascii=False,
                                        allow_nan=False))
            elif k in _CSV_METIN_ALANLARI:
                satir.append(deger)
            else:
                satir.append(repr(float(deger)))
        w.writerow(satir)
    return tampon.getvalue()


def csv_oku(metin_ya_da_bayt):
    metin = _boyut_ve_kod(metin_ya_da_bayt)
    satirlar = metin.split('\n')
    kimlik_surumu = (_CSV_KIMLIK_SATIRLARI.get(satirlar[0].rstrip('\r'))
                     if len(satirlar) >= 3 else None)
    if kimlik_surumu is None:
        raise SloshTabloHatasi(f'ilk satır {CSV_KIMLIK_SATIRI!r} (ya da '
                               f'desteklenen eski sürümü) olmalı',
                               kod='SURUM_UYUSMAZ')
    ms = satirlar[1].rstrip('\r')
    if not ms.startswith(CSV_META_ONEKI):
        raise SloshTabloHatasi('ikinci satır meta satırı olmalı',
                               kod='BICIM_HATASI')
    try:
        meta = json.loads(ms[len(CSV_META_ONEKI):],
                          parse_constant=_sabit_reddet)
    except SloshTabloHatasi:
        raise
    except (ValueError, RecursionError) as e:
        raise SloshTabloHatasi(f'meta satırı ayrıştırılamadı: {e}',
                               kod='BICIM_HATASI') from None
    if not isinstance(meta, dict) or 'satirlar' in meta:
        raise SloshTabloHatasi('meta satırı nesne olmalı ve satır içermemeli',
                               kod='BICIM_HATASI')
    if meta.get('sema_surumu') != kimlik_surumu:
        raise SloshTabloHatasi('meta satırının sürümü kimlik satırıyla '
                               'aynı olmalı', kod='SURUM_UYUSMAZ',
                               alan='sema_surumu')
    try:
        okuyucu = list(csv.reader(io.StringIO('\n'.join(satirlar[2:]))))
    except csv.Error as e:
        raise SloshTabloHatasi(f'CSV ayrıştırılamadı: {e}',
                               kod='BICIM_HATASI') from None
    okuyucu = [r for r in okuyucu if r]
    if not okuyucu or tuple(okuyucu[0]) != SATIR_SUTUNLARI:
        raise SloshTabloHatasi('başlık satırı sözleşme sütunlarıyla aynı '
                               'olmalı', kod='BICIM_HATASI')
    veri_satirlari = []
    for j, r in enumerate(okuyucu[1:]):
        if len(r) != len(SATIR_SUTUNLARI):
            raise SloshTabloHatasi(f'satır {j}: sütun sayısı yanlış',
                                   kod='BICIM_HATASI')
        s = {}
        for k, hucre in zip(SATIR_SUTUNLARI, r):
            if k == 'sebep':
                s[k] = [x for x in hucre.split(';') if x] if hucre else []
            elif k == SATIR_EK:
                if hucre:
                    try:
                        s[k] = json.loads(hucre, parse_constant=_sabit_reddet)
                    except SloshTabloHatasi:
                        raise
                    except (ValueError, RecursionError):
                        raise SloshTabloHatasi(f'satır {j}: ek JSON değil',
                                               kod='BICIM_HATASI') from None
            elif k in SATIR_MOD2:
                if hucre:
                    s[k] = _csv_sayi(hucre, j, k)
            elif k in _CSV_METIN_ALANLARI:
                s[k] = hucre if hucre else None
            else:
                s[k] = _csv_sayi(hucre, j, k) if hucre else None
        veri_satirlari.append(s)
    veri = dict(meta)
    veri['satirlar'] = veri_satirlari
    return SloshTablo.sozlukten(veri)


def _csv_sayi(hucre, j, k):
    try:
        f = float(hucre)
    except ValueError:
        raise SloshTabloHatasi(f'satır {j}: {k} sayı değil',
                               kod='TUR_HATASI', alan=k) from None
    if not math.isfinite(f):
        raise SloshTabloHatasi(f'satır {j}: {k} sonlu değil',
                               kod='DEGER_GECERSIZ', alan=k)
    return f
