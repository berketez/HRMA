"""3.0.7 TANK-GEOMETRİ — tank iç geometrisi girdisi ve geometri kapıları.

Tasarım: ``docs/tasarim/v307/TANK_GEOMETRI_TASARIM.md`` §0, §1, §A, §B
(kulvar K3a, KARTLAR K3 kalemleri 1–3). Sözleşme (sebep kodları, profil
nokta sınırı, okuyucu hata türleri): ``hrma.analysis.slosh_tablo`` — TEK
YER; burada yalnız içe aktarılır.

Biçimler (beyaz liste, dosya uzantısından):

* ``.csv``  — başlık ``x,y,z`` (3B nokta bulutu) ya da ``r,z`` (iç profil,
  alt kutuptan üst kutba); başlıktan hemen sonra isteğe bağlı birim satırı
  (``mm,mm,mm``). Ondalık nokta; boş satır ve sonlu olmayan sayı RET.
* ``.xyz``  — boşlukla ayrılmış tam 3 sütun; birim ayrı alandan zorunlu.
* ``.ply``  — ASCII ya da ikili little-endian; ``vertex`` (x, y, z) ve
  isteğe bağlı ``face`` (3–16 köşeli çokgen, yelpaze üçgenlemesi).
* ``.stl``  — ASCII ya da ikili; ikili başlıktaki üçgen sayısı dosya
  boyutuyla birebir tutmalı.
* ``.step`` / ``.stp`` — B-rep kati; ``step_import`` modülünün build123d/OCP
  yükleyicisiyle okunur, OCCT ``BRepMesh_IncrementalMesh`` ile mozaiklenir,
  sonra STL yoluna girer. Mozaikleyici yoksa RET ``STEP_MOZAIK_YOK``.
  Paket ölçümü: ``docs/scofield/raw/OH/V307/tank-geometri/RAPOR.md`` §1.

Birim zorunludur ({m, mm, in}); tahmin yapılmaz (``BIRIM_YOK``).

Kapılar (sırayla; ilk başarısız kapı RET olur):

* **B.1 okuma** — boyut/sayı sınırları, biçim, sonlu sayı, birim, en az
  nokta. Okuyucu hataları sözleşmenin okuyucu hata türleriyle adlanır
  (``SloshTabloHatasi.kod``: ``BOYUT_SINIRI``, ``BICIM_HATASI``,
  ``DEGER_GECERSIZ``, ``ALAN_EKSIK``); ayrıştırıcı istisnası da adlı
  ``BICIM_HATASI`` olur, sızmaz.
* **B.2 kapalılık** — yüzlü girdide kenar/yönelim/Euler/işaretli hacim;
  yüzsüz bulutta kapsama (``EKSIK_BOLGE``).
* **B.4a tek yüzey** — meridyen yönünde iki yüzey (``PROFIL_TEK_DEGERLI_DEGIL``).
  Uç kapanmasından ve B.3'ten önce koşar: toroid kapalı bir yüzeydir ama
  eksene inmez, artık tabanlı simetri ölçüsü de yön başına tek yüzey
  varsayar; iki yüzeyli tank aksi hâlde yanlış nedenle reddedilirdi.
* **B.2 uç kapanması** (yüzsüz) — meridyenin iki uç kutusu eksene ulaşmalı.
* **B.3 eksenel simetri** — eksen uydurma, ε_rms, ε_max, gürültü kestirimi.
* **B.4 profil** — z azalmaması, profil kapısı
  (``tank_mass_properties.profil_dogrula``), yüzlü girdide hacim tutarlılığı.

Meridyen kestirimi (tasarım düzeltmesi, RAPOR §3): z kutularıyla yarıçap
medyanı düz başta ve kutup çevresinde tanımsızdır (aynı z'de 0..R arası
noktalar). Bu modül meridyeni eksen üzerindeki orta noktadan kutupsal
açıyla (φ) eşit sayılı kutulara böler; her kutunun düğümü (medyan φ,
medyan s) çiftidir; kutup düğümleri uç kutudaki noktalara z = a + bρ²
uydurmasının a'sıdır. Artık, noktanın (ρ, z) meridyen çoklu çizgisine
işaretli dik uzaklığıdır (düz başta ve kubbede de tanımlı). Kapsam:
orta noktadan yıldız biçimli meridyen (dışbükey tanklar: silindir +
kubbe, küre, elipsoid, koni). Derin boğumlu tek değerli profil bu yolla
çıkarılamaz, adlı RET alır; o tank (r, z) profil CSV'siyle girilir.

Kullanıcı metni: her RET bir metin anahtarı (``tank_geometry.<kod>.<ayrinti>``),
parametreleri ve İngilizce yedek cümle taşır; TR/EN sözlük girdileri
arayüz kulvarında (K5) eklenir.
"""

from __future__ import annotations

import hashlib
import math
import numbers
import os
import re

import numpy as np

from hrma.analysis.slosh_tablo import (
    DURUM_RET,
    OKUYUCU_HATA_KODLARI,
    PROFIL_NOKTA_SINIRI,
    SEBEP_KODLARI,
    SloshTabloHatasi,
    durum_birlestir,
)
from hrma.analysis.tank_mass_properties import (
    ProfilHatasi,
    ic_hacim,
    profil_dogrula,
)
from hrma.constants import IN_M

# ---------------------------------------------------------------------------
# Sınırlar ve eşikler — TEK YER. Kaynaklı olmayanların hepsi HRMA seçimidir.
# ---------------------------------------------------------------------------
#: Girdi dosyası boyut sınırı [bayt] (STEP dışı). 1e6 noktalık ASCII bulut
#: (~30 MB) ve 1e6 üçgenlik ikili STL (~50 MB) sığar. HRMA seçimi.
TANK_DOSYA_BOYUT_SINIRI = 64 * 1024 * 1024
#: STEP dosyası boyut sınırı [bayt]. OCCT okuma + mozaikleme süresi dosya
#: boyutuyla büyür; tank katisı için 16 MB geniş paydır. HRMA seçimi.
TANK_STEP_BOYUT_SINIRI = 16 * 1024 * 1024
#: Nokta bulutu nokta sayısı sınırı. Ölçülen süre RAPOR §2. HRMA seçimi.
TANK_NOKTA_SINIRI = 1_000_000
#: Üçgen sayısı sınırı (STL / PLY yüzleri / mozaiklenmiş STEP). HRMA seçimi.
TANK_UCGEN_SINIRI = 1_000_000
#: PLY yüz çokgeninin en çok köşe sayısı (yelpaze üçgenlemesi). HRMA seçimi.
TANK_PLY_KOSE_SINIRI = 16

#: Simetri eşiği ε_max (TANK §B.3.4). HRMA seçimi; gerekçe TANK §B.3.5.
TANK_SIMETRI_ESIGI = 0.01
#: Simetri eşiği ε_rms (TANK §B.3.4). HRMA seçimi.
TANK_SIMETRI_RMS_ESIGI = 0.005
#: σ̂_n/R_ref bu değeri aşarsa BEYAN: gürültü simetri eşiğiyle
#: kıyaslanabilir (TANK §B.3.4). HRMA seçimi.
TANK_GURULTU_BEYAN_ESIGI = 0.005
#: MAD → σ çevrimi (normal dağılım için 1/Φ⁻¹(3/4); Rousseeuw & Croux 1993,
#: JASA 88(424), s. 1273, Denk. (1.2)'nin katsayısı).
MAD_SIGMA_KATSAYISI = 1.4826

#: Azimut dilimi sayısı n_θ (TANK §B.1, §B.3).
TANK_AZIMUT_DILIMI = 12
#: Kapsama denetiminin meridyen kutusu sayısı n_z (TANK §B.1 varsayılanı);
#: kutular meridyen boyunca eşit sayılıdır (RAPOR §3 tasarım düzeltmesi).
TANK_Z_KUTUSU = 40
#: Kapsama: hücre başına en az nokta (TANK §B.2).
TANK_HUCRE_EN_AZ_NOKTA = 3
#: Uç kapanması: tankın alt ve üst yarısında eksene bu oran · R_ref (ya da
#: TANK_UC_ARALIK_KATI · ℓ, hangisi büyükse) mesafeden yakın en az
#: TANK_HUCRE_EN_AZ_NOKTA nokta bulunmalı (TANK §B.4'ün %5 oranı). Tasarım düzeltmesi (RAPOR §3): §B.4'ün z kutusu ölçütü içe
#: dönük ortak perdede ve toroidde "baş kapanmıyor" diye yanlış nedenle
#: reddediyordu (en üst z kutusunda yalnız çeper vardır); 20 alt kutudan
#: 19'u ölçütü ρ ile orantılı nokta yoğunluğunda eksen yanındaki alt
#: kutuları boş bırakabiliyordu.
TANK_UC_KUBBE_ORANI = 0.05
#: Uç kapanma yarıçapı en az bu kat · ℓ (ℓ = √(A/N) ortalama nokta aralığı;
#: A meridyenden döndürülmüş yüzey alanı). Seyrek bulutta %5 R_ref'lik
#: kutup kapağına beklenen nokta sayısı 3'ün altına düşebilir (ölçüldü:
#: kubbeli silindir, 12 000 nokta, ~4 nokta); 3ℓ yarıçapında beklenen
#: ~28'dir. ℓ'den küçük delik bu yoğunlukta zaten ayırt edilemez.
#: HRMA seçimi.
TANK_UC_ARALIK_KATI = 3.0
#: Yüzlü girdide ağ hacmi ⟷ profil hacmi bağıl farkı sınırı (TANK §B.4).
TANK_HACIM_TUTARLILIK_ESIGI = 0.005

#: PCA: üç öz değerin bağıl yayılımı bu değerin altındaysa (küreye yakın)
#: PCA ekseni anlamsız sayılır, kullanıcının üst yönü alınır (TANK §B.3.1).
TANK_PCA_KURE_ESIGI = 0.02
#: Eksen inceltme: en çok tur ve durma ölçütü (R_ref'e göre) (TANK §B.3.2).
TANK_EKSEN_TUR_SINIRI = 20
TANK_EKSEN_DURMA_ORANI = 1e-6
#: Eksen uydurmasında kullanılan en çok nokta (belirlenimli eşit aralıklı alt
#: örnek; ölçütler yine BÜTÜN noktalarda hesaplanır). HRMA seçimi.
TANK_EKSEN_ALT_ORNEK = 20_000
#: soft-L1 kaybının geçiş ölçeği, R_ref'e göre. HRMA seçimi.
TANK_SOFT_L1_ORANI = 1e-3
#: Meridyen kutupsal kutu başına hedef nokta ve kutu sayısı sınırları.
#: HRMA seçimi (medyanın kararlılığı için ≥ 50 nokta).
TANK_MERIDYEN_KUTU_NOKTA = 50
TANK_MERIDYEN_KUTU_EN_AZ = 40
TANK_MERIDYEN_KUTU_EN_COK = 400
#: Tek yüzey denetimi: bir φ kutusunda sıralı s değerlerinde bu açıklıktan
#: (R_ref'e göre) büyük bir boşluk ve iki yanda en az bu pay varsa iki iç
#: yüzey vardır. HRMA seçimi.
TANK_IKI_YUZEY_ACIKLIK_ORANI = 0.05
TANK_IKI_YUZEY_PAY = 0.10
#: Meridyende z azalmasının payı: 3 σ̂_n + eksen kestirim payı. Uydurulan
#: eksenin kalan eğimi δθ düz başta düğüm z'lerini R·δθ kadar oynatır.
#: Ölçüldü (gürültüsüz düz başlı silindir, 60 000 nokta, iki tohum): δθ
#: 0,9–1,25·10⁻⁶ rad, en büyük z geri dönüşü 2,0·10⁻⁶ R; SciPy toleransı
#: 10⁻¹²'ye sıkılınca değişmedi (kestirim sınırı, çözücü değil). Pay
#: 10⁻⁵ R (ölçülenin 5 katı). İçe dönük perde 0,6 R derinlikle bunun çok
#: üstündedir. HRMA seçimi.
TANK_Z_MONOTON_SIGMA_KATI = 3.0
TANK_DUGUM_KURULUM_PAYI_ORANI = 1e-5
#: Eksen inceltmesinde tur başına soft-L1 maliyetinin bağıl değişimi bu
#: değerin altına inerse durulur. Gerekçe (ölçüldü, küre 60 000 nokta):
#: yön dejenere olduğundan konum 2. turda yakınsarken yön her turda ~10⁻³
#: rad gezinir ve maliyet tur başına < %1 değişir; konum ölçütü tek başına
#: 20 tura gider. Dejenere olmayan tankta ilk turlarda maliyet katlarca
#: düşer (kubbeli silindir: 7,8·10⁻⁴ → 3,3·10⁻⁶), %1 orada durdurmaz.
#: HRMA seçimi.
TANK_EKSEN_MALIYET_DURMA = 1e-2
#: Kullanıcının üst yönü ile uydurulan eksen arasındaki |cos| alt sınırı
#: (60°). Daha dik açıda hangi başın buruna baktığı belirsizdir. HRMA seçimi.
TANK_UST_YON_COS_ESIGI = 0.5
#: Yüzlü girdide yüzey örnekleme hedefi (alan düzgün, belirlenimli üçgen
#: kafesi). HRMA seçimi.
TANK_AG_ORNEK_HEDEF = 200_000
TANK_AG_ORNEK_KAFES_SINIRI = 64
#: STEP mozaikleme: doğrusal sapma (sınır kutusu köşegenine göre) ve açısal
#: sapma [rad]. Ölçüm RAPOR §1. HRMA seçimi.
TANK_STEP_SAPMA_ORANI = 1e-4
TANK_STEP_ACI_RAD = 0.1

#: Birim çarpanları [m / birim]. inç = 0,0254 m tam tanımdır
#: (``hrma.constants.IN_M``).
BIRIM_CARPANLARI = {'m': 1.0, 'mm': 1e-3, 'in': IN_M}
#: STEP başlığından okunan birim adının bu modüldeki karşılığı.
_STEP_BIRIM_ESLEME = {'m': 'm', 'mm': 'mm', 'inch': 'in'}

#: Biçim beyaz listesi: uzantı -> okuyucu.
UZANTI_BICIMLERI = {'.csv': 'csv', '.xyz': 'xyz', '.ply': 'ply',
                    '.stl': 'stl', '.step': 'step', '.stp': 'step'}

_METIN_ONEKI = 'tank_geometry'

#: Ret/beyan metinlerinin İngilizce yedekleri: (kod, ayrinti) -> şablon.
#: TR ve EN sözlük girdileri K5'te ``tank_geometry.<kod küçük>.<ayrinti>``
#: anahtarıyla eklenir (anahtar listesi RAPOR §5).
YEDEK_METINLER = {
    ('BOYUT_SINIRI', 'dosya_boyutu'):
        'The file is {bayt} bytes; the limit for this format is {sinir} bytes.',
    ('BOYUT_SINIRI', 'nokta_siniri'):
        'The file has {nokta} points; the limit is {sinir}.',
    ('BOYUT_SINIRI', 'ucgen_siniri'):
        'The file has {ucgen} triangles; the limit is {sinir}.',
    ('BOYUT_SINIRI', 'profil_nokta_siniri'):
        'The profile has {nokta} points; the limit is {sinir}.',
    ('BICIM_HATASI', 'bicim_desteklenmiyor'):
        'Unsupported file type "{uzanti}". Accepted: CSV, XYZ, PLY, STL, '
        'STEP.',
    ('BICIM_HATASI', 'bos_dosya'): 'The file is empty.',
    ('BICIM_HATASI', 'metin_degil'):
        'The file is not readable UTF-8/ASCII text.',
    ('BICIM_HATASI', 'csv_baslik'):
        'The CSV header must be "x,y,z" (point cloud) or "r,z" (profile).',
    ('BICIM_HATASI', 'sutun_sayisi'):
        'Line {satir} has {sutun} columns; {beklenen} were expected.',
    ('BICIM_HATASI', 'sayi_degil'):
        'Line {satir} contains a value that is not a number.',
    ('BICIM_HATASI', 'ply_baslik'):
        'The PLY header is invalid ({neden}).',
    ('BICIM_HATASI', 'ply_buyuk_endian'):
        'Big-endian binary PLY is not supported; export ASCII or binary '
        'little-endian PLY.',
    ('BICIM_HATASI', 'ply_yuz_kose'):
        'A PLY face has {kose} corners; 3 to {sinir} are accepted.',
    ('BICIM_HATASI', 'yuz_indeksi_gecersiz'):
        'A face refers to a vertex that does not exist.',
    ('BICIM_HATASI', 'ikili_boyut_tutarsiz'):
        'The binary file declares {beyan} records but its size ({bayt} '
        'bytes) does not match; the file is truncated or corrupt.',
    ('BICIM_HATASI', 'stl_ascii_yapi'):
        'The ASCII STL structure is inconsistent ({neden}).',
    ('BICIM_HATASI', 'step_baslik'):
        'Not a STEP file (missing ISO-10303-21 header).',
    ('BICIM_HATASI', 'step_okunamadi'):
        'The STEP file could not be read by the geometry kernel.',
    ('BICIM_HATASI', 'step_govde_sayisi'):
        'The STEP file contains {govde} solids; exactly one solid (the tank '
        'interior volume) is required.',
    ('BICIM_HATASI', 'step_ucgen_yok'):
        'The STEP solid produced no triangles.',
    ('BICIM_HATASI', 'ayristirici_hatasi'):
        'The file could not be parsed ({tur}).',
    ('DEGER_GECERSIZ', 'sonlu_olmayan'):
        'The file contains NaN or infinite values.',
    ('DEGER_GECERSIZ', 'bos_satir'):
        'Line {satir} is empty; empty lines are not accepted.',
    ('DEGER_GECERSIZ', 'nokta_az'):
        'The point cloud has {nokta} points; at least {en_az} are required '
        '({n_theta} azimuth sectors x {n_z} axial bins x 3).',
    ('DEGER_GECERSIZ', 'ust_yon_gecersiz'):
        'The "up" (nose) direction must be a non-zero 3-vector.',
    ('DEGER_GECERSIZ', 'ust_yon_eksene_dik'):
        'The "up" (nose) direction is {aci_deg} degrees from the tank axis; '
        'it must point along the axis (within 60 degrees).',
    ('DEGER_GECERSIZ', 'eksen_gecersiz'):
        'The axis must be given as a point and a non-zero direction.',
    ('DEGER_GECERSIZ', 'sigma_gecersiz'):
        'The measurement noise must be a non-negative finite number.',
    ('DEGER_GECERSIZ', 'profil_az_nokta'):
        'The profile has {nokta} points; at least 3 are required.',
    ('DEGER_GECERSIZ', 'negatif_yaricap'):
        'Profile row {satir} has a negative radius.',
    ('DEGER_GECERSIZ', 'boyut_sifir'):
        'The profile has zero height or zero radius.',
    ('TUR_HATASI', 'profil_sayi_degil'):
        'The profile contains values that are not numbers.',
    ('TUR_HATASI', 'profil_bicimi'):
        'The profile must be a list of [r, z] pairs.',
    ('ALAN_EKSIK', 'ust_yon_yok'):
        'The "up" (nose) direction of the tank is required for 3D input; '
        'which end faces the nose cannot be derived from the geometry.',
    ('BIRIM_YOK', 'yok'):
        'No length unit was given. Choose m, mm or in.',
    ('BIRIM_YOK', 'desteklenmiyor'):
        'Unit "{birim}" is not accepted. Choose m, mm or in.',
    ('BIRIM_YOK', 'celiskili'):
        'The unit given ({verilen}) contradicts the unit declared in the '
        'file ({dosya}).',
    ('BIRIM_YOK', 'step_basliginda_yok'):
        'The STEP file does not declare a single length unit.',
    ('STEP_MOZAIK_YOK', 'mozaikleyici_yok'):
        'STEP cannot be converted to a mesh in this installation; export '
        'the tank as STL instead.',
    ('YUZEY_KAPALI_DEGIL', 'dejenere_ucgen'):
        'The mesh has {adet} degenerate triangles (zero area or repeated '
        'vertex).',
    ('YUZEY_KAPALI_DEGIL', 'acik_kenar'):
        'The surface is not closed: {adet} open edges. Holes are not filled '
        'automatically.',
    ('YUZEY_KAPALI_DEGIL', 'manifold_degil'):
        'The surface has {adet} edges shared by more than two triangles.',
    ('YUZEY_KAPALI_DEGIL', 'yonelim_tutarsiz'):
        'Triangle orientation is inconsistent at {adet} edges.',
    ('YUZEY_KAPALI_DEGIL', 'euler'):
        'The closed surface is not a single tank-shaped body (Euler '
        'characteristic {chi}, expected 2).',
    ('YUZEY_KAPALI_DEGIL', 'ters_yonelim'):
        'The surface normals point inward (signed volume {hacim_m3} m3).',
    ('YUZEY_KAPALI_DEGIL', 'bas_kapanmiyor'):
        'The {uc} end of the tank does not close.',
    ('EKSIK_BOLGE', 'kapsama'):
        'The point cloud has missing regions: {adet} cells between '
        'z = {z_min_m} and {z_max_m} m, azimuth sectors {dilimler}. Missing '
        'regions are not filled by estimation.',
    ('PROFIL_TEK_DEGERLI_DEGIL', 'iki_yuzey'):
        'Two inner surfaces were found in the same direction near z = {z_m} '
        'm; the profile is not single-valued.',
    ('PROFIL_TEK_DEGERLI_DEGIL', 'z_monoton_degil'):
        'The profile turns back in z near z = {z_m} m (two inner surfaces '
        'at the same height).',
    ('PROFIL_TEK_DEGERLI_DEGIL', 'ic_dugum_eksende'):
        'The profile touches the axis at z = {z_m} m before its end.',
    ('PROFIL_TEK_DEGERLI_DEGIL', 'kendini_kesiyor'):
        'The profile intersects itself near z = {z_m} m.',
    ('EKSENEL_SIMETRIK_DEGIL', 'esik'):
        'A non-axisymmetric tank is not solved in this version '
        '(eps_max {eps_max}, limit {esik_eps_max}; eps_rms {eps_rms}, limit '
        '{esik_eps_rms}; worst at z = {z_m} m).',
    ('PROFIL_AG_HACIM_TUTARSIZ', 'hacim'):
        'The profile volume ({V_profil_m3} m3) differs from the mesh volume '
        '({V_ag_m3} m3) by {fark_yuzde} %; the limit is {sinir_yuzde} %.',
    ('BEYAN', 'gurultu_esikle_kiyaslanabilir'):
        'Measurement noise (sigma/R = {sigma_oran}) is comparable to the '
        'symmetry threshold.',
}


class _Ret(Exception):
    """İç akış: ilk başarısız kapı. Dışarı sızmaz."""

    def __init__(self, kapi, ayrinti, *, sebep=None, okuma_kodu=None,
                 alan=None, parametreler=None):
        super().__init__(ayrinti)
        self.kapi = kapi
        self.ayrinti = ayrinti
        self.sebep = sebep
        self.okuma_kodu = okuma_kodu
        self.alan = alan
        self.parametreler = dict(parametreler or {})


def _okuma(ayrinti, kod, alan=None, kapi='B.1', **parametreler):
    # v307-2 (K6): okuyucu hata türleri sözleşmenin adlı sabitlerinden
    # (slosh_tablo.OKUYUCU_HATA_KODLARI); listede olmayan tür üretilmez.
    if kod not in OKUYUCU_HATA_KODLARI:
        raise AssertionError(f'sözleşmede olmayan okuyucu hata türü {kod!r}')
    raise _Ret(kapi, ayrinti, okuma_kodu=kod, alan=alan,
               parametreler=parametreler)


def _kapi(kapi, sebep, ayrinti, **parametreler):
    if sebep not in SEBEP_KODLARI:     # sözleşme dışı kod üretilmez
        raise AssertionError(f'sözleşmede olmayan sebep kodu {sebep!r}')
    raise _Ret(kapi, ayrinti, sebep=sebep, parametreler=parametreler)


def _metin(kod, ayrinti, parametreler):
    sablon = YEDEK_METINLER.get((kod, ayrinti))
    if sablon is None:
        return kod
    try:
        return sablon.format(**parametreler)
    except (KeyError, IndexError, ValueError):
        return sablon


def _ret_sonucu(ret, kunye):
    kod = ret.sebep or ret.okuma_kodu
    out = {
        'durum': DURUM_RET,
        'kapi': ret.kapi,
        'sebep': [ret.sebep] if ret.sebep else [],
        'okuma_hatasi': (None if ret.sebep else
                         SloshTabloHatasi(_metin(kod, ret.ayrinti,
                                                 ret.parametreler),
                                          kod=ret.okuma_kodu,
                                          alan=ret.alan).kunye()),
        'ayrinti': ret.ayrinti,
        'mesaj_anahtari': f'{_METIN_ONEKI}.{kod.lower()}.{ret.ayrinti}',
        'mesaj_parametreleri': ret.parametreler,
        'mesaj_en': _metin(kod, ret.ayrinti, ret.parametreler),
        'kunye': kunye,
    }
    return out


# ---------------------------------------------------------------------------
# Küçük kapılar
# ---------------------------------------------------------------------------
def _vektor3(deger, ayrinti, alan):
    if isinstance(deger, np.ndarray) and deger.dtype == bool:
        _okuma(ayrinti, 'DEGER_GECERSIZ', alan)
    if isinstance(deger, (list, tuple)) and any(
            isinstance(x, (bool, np.bool_)) for x in deger):
        _okuma(ayrinti, 'DEGER_GECERSIZ', alan)
    try:
        v = np.asarray(deger, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        _okuma(ayrinti, 'DEGER_GECERSIZ', alan)
    if (v.shape != (3,) or not np.all(np.isfinite(v))
            or not np.linalg.norm(v) > 0.0):
        _okuma(ayrinti, 'DEGER_GECERSIZ', alan)
    return v


def _birim_coz(verilen, dosyadaki):
    """Birim çözümü: verilen ve dosyadaki birim; tahmin yok."""
    if verilen is not None:
        if not isinstance(verilen, str) or verilen not in BIRIM_CARPANLARI:
            _kapi('B.1', 'BIRIM_YOK', 'desteklenmiyor', birim=str(verilen)[:32])
    if dosyadaki is not None and dosyadaki not in BIRIM_CARPANLARI:
        _kapi('B.1', 'BIRIM_YOK', 'desteklenmiyor', birim=str(dosyadaki)[:32])
    if verilen is None and dosyadaki is None:
        _kapi('B.1', 'BIRIM_YOK', 'yok')
    if verilen is not None and dosyadaki is not None and verilen != dosyadaki:
        _kapi('B.1', 'BIRIM_YOK', 'celiskili', verilen=verilen,
              dosya=dosyadaki)
    return verilen if verilen is not None else dosyadaki


def _sonlu(dizi):
    if not np.all(np.isfinite(dizi)):
        _okuma('sonlu_olmayan', 'DEGER_GECERSIZ')


# ---------------------------------------------------------------------------
# Okuyucular — her biri (noktalar, ucgenler | None, profil | None,
# dosyadaki_birim | None) döndürür. Koordinatlar dosya biriminde.
# ---------------------------------------------------------------------------
_SAYI_RE = re.compile(r'^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$')
_SONLU_DISI_RE = re.compile(r'^[+-]?(?:nan|inf|infinity)$', re.IGNORECASE)


def _hucre_sayi(hucre, satir):
    h = hucre.strip()
    if _SAYI_RE.match(h):
        return float(h)
    if _SONLU_DISI_RE.match(h):
        _okuma('sonlu_olmayan', 'DEGER_GECERSIZ', satir=satir)
    _okuma('sayi_degil', 'BICIM_HATASI', satir=satir)


def _metin_coz(veri):
    try:
        metin = veri.decode('utf-8-sig')
    except UnicodeDecodeError:
        _okuma('metin_degil', 'BICIM_HATASI')
    if '\x00' in metin:
        _okuma('metin_degil', 'BICIM_HATASI')
    return metin


def _satirlar(metin):
    """(satır_no, içerik) — yorum satırları atlanır, iç boş satır RET."""
    govde = metin.rstrip()
    out = []
    for i, satir in enumerate(govde.split('\n'), start=1):
        s = satir.rstrip('\r')
        if s.lstrip().startswith('#'):
            continue
        if not s.strip():
            _okuma('bos_satir', 'DEGER_GECERSIZ', satir=i)
        out.append((i, s))
    return out


def _csv_oku(veri):
    satirlar = _satirlar(_metin_coz(veri))
    if not satirlar:
        _okuma('bos_dosya', 'BICIM_HATASI')
    baslik = [h.strip().lower() for h in satirlar[0][1].split(',')]
    if baslik == ['x', 'y', 'z']:
        tur, n_sut, sinir = 'bulut', 3, TANK_NOKTA_SINIRI
    elif baslik == ['r', 'z']:
        tur, n_sut, sinir = 'profil', 2, PROFIL_NOKTA_SINIRI
    else:
        _okuma('csv_baslik', 'BICIM_HATASI')
    govde = satirlar[1:]
    dosya_birimi = None
    if govde:
        ilk = [h.strip() for h in govde[0][1].split(',')]
        if all(h and not _SAYI_RE.match(h) and not _SONLU_DISI_RE.match(h)
               and h.isalpha() for h in ilk):
            if len(ilk) != n_sut:
                _okuma('sutun_sayisi', 'BICIM_HATASI', satir=govde[0][0],
                       sutun=len(ilk), beklenen=n_sut)
            if len(set(ilk)) != 1:
                _kapi('B.1', 'BIRIM_YOK', 'celiskili', verilen=ilk[0],
                      dosya=','.join(ilk))
            dosya_birimi = ilk[0]
            if dosya_birimi not in BIRIM_CARPANLARI:
                _kapi('B.1', 'BIRIM_YOK', 'desteklenmiyor', birim=dosya_birimi)
            govde = govde[1:]
    if len(govde) > sinir:
        _okuma('profil_nokta_siniri' if tur == 'profil' else 'nokta_siniri',
               'BOYUT_SINIRI', nokta=len(govde), sinir=sinir)
    dizi = np.empty((len(govde), n_sut), dtype=float)
    for k, (i, s) in enumerate(govde):
        hucreler = s.split(',')
        if len(hucreler) != n_sut:
            _okuma('sutun_sayisi', 'BICIM_HATASI', satir=i,
                   sutun=len(hucreler), beklenen=n_sut)
        for j, h in enumerate(hucreler):
            dizi[k, j] = _hucre_sayi(h, i)
    if tur == 'profil':
        return None, None, dizi, dosya_birimi
    return dizi, None, None, dosya_birimi


def _xyz_oku(veri):
    satirlar = _satirlar(_metin_coz(veri))
    if not satirlar:
        _okuma('bos_dosya', 'BICIM_HATASI')
    if len(satirlar) > TANK_NOKTA_SINIRI:
        _okuma('nokta_siniri', 'BOYUT_SINIRI', nokta=len(satirlar),
               sinir=TANK_NOKTA_SINIRI)
    dizi = np.empty((len(satirlar), 3), dtype=float)
    for k, (i, s) in enumerate(satirlar):
        hucreler = s.split()
        if len(hucreler) != 3:
            _okuma('sutun_sayisi', 'BICIM_HATASI', satir=i,
                   sutun=len(hucreler), beklenen=3)
        for j, h in enumerate(hucreler):
            dizi[k, j] = _hucre_sayi(h, i)
    return dizi, None, None, None


_PLY_TURLERI = {
    'char': 'i1', 'int8': 'i1', 'uchar': 'u1', 'uint8': 'u1',
    'short': 'i2', 'int16': 'i2', 'ushort': 'u2', 'uint16': 'u2',
    'int': 'i4', 'int32': 'i4', 'uint': 'u4', 'uint32': 'u4',
    'float': 'f4', 'float32': 'f4', 'double': 'f8', 'float64': 'f8',
}
_PLY_BASLIK_SINIRI = 64 * 1024


def _ply_baslik(veri):
    son = veri.find(b'end_header', 0, _PLY_BASLIK_SINIRI)
    if not veri.startswith(b'ply') or son < 0:
        _okuma('ply_baslik', 'BICIM_HATASI', neden='ply/end_header')
    satir_sonu = veri.find(b'\n', son)
    if satir_sonu < 0:
        _okuma('ply_baslik', 'BICIM_HATASI', neden='end_header')
    try:
        baslik = veri[:son].decode('ascii')
    except UnicodeDecodeError:
        _okuma('ply_baslik', 'BICIM_HATASI', neden='ascii')
    bicim = None
    ogeler = []          # [ad, sayi, [ozellikler]]
    for satir in baslik.splitlines()[1:]:
        t = satir.split()
        if not t or t[0] in ('comment', 'obj_info'):
            continue
        if t[0] == 'format':
            if len(t) != 3 or t[2] != '1.0':
                _okuma('ply_baslik', 'BICIM_HATASI', neden='format')
            bicim = t[1]
        elif t[0] == 'element':
            if len(t) != 3 or not t[2].isdigit():
                _okuma('ply_baslik', 'BICIM_HATASI', neden='element')
            ogeler.append([t[1], int(t[2]), []])
        elif t[0] == 'property':
            if not ogeler:
                _okuma('ply_baslik', 'BICIM_HATASI', neden='property')
            if t[1] == 'list':
                if (len(t) != 5 or t[2] not in _PLY_TURLERI
                        or t[3] not in _PLY_TURLERI):
                    _okuma('ply_baslik', 'BICIM_HATASI', neden='property list')
                ogeler[-1][2].append(('list', t[4], t[2], t[3]))
            else:
                if len(t) != 3 or t[1] not in _PLY_TURLERI:
                    _okuma('ply_baslik', 'BICIM_HATASI', neden='property')
                ogeler[-1][2].append(('skaler', t[2], t[1]))
        else:
            _okuma('ply_baslik', 'BICIM_HATASI', neden=t[0][:32])
    if bicim == 'binary_big_endian':
        _okuma('ply_buyuk_endian', 'BICIM_HATASI')
    if bicim not in ('ascii', 'binary_little_endian'):
        _okuma('ply_baslik', 'BICIM_HATASI', neden='format')
    adlar = [o[0] for o in ogeler]
    if adlar not in (['vertex'], ['vertex', 'face']):
        _okuma('ply_baslik', 'BICIM_HATASI',
               neden='elements ' + ','.join(adlar)[:64])
    v_ozellik = ogeler[0][2]
    if any(o[0] == 'list' for o in v_ozellik):
        _okuma('ply_baslik', 'BICIM_HATASI', neden='vertex list')
    v_adlar = [o[1] for o in v_ozellik]
    if not all(a in v_adlar for a in ('x', 'y', 'z')) or len(set(v_adlar)) != len(v_adlar):
        _okuma('ply_baslik', 'BICIM_HATASI', neden='vertex x y z')
    n_v = ogeler[0][1]
    if n_v > TANK_NOKTA_SINIRI:
        _okuma('nokta_siniri', 'BOYUT_SINIRI', nokta=n_v,
               sinir=TANK_NOKTA_SINIRI)
    yuz = None
    if len(ogeler) == 2:
        f_oz = ogeler[1][2]
        if (len(f_oz) != 1 or f_oz[0][0] != 'list'
                or f_oz[0][1] not in ('vertex_indices', 'vertex_index')):
            _okuma('ply_baslik', 'BICIM_HATASI', neden='face')
        if ogeler[1][1] > TANK_UCGEN_SINIRI:
            _okuma('ucgen_siniri', 'BOYUT_SINIRI', ucgen=ogeler[1][1],
                   sinir=TANK_UCGEN_SINIRI)
        yuz = (ogeler[1][1], f_oz[0][2], f_oz[0][3])
    return bicim, satir_sonu + 1, v_ozellik, n_v, yuz


def _yelpaze(cokgenler):
    """Çokgen listesini yelpaze üçgenlerine böler (n ≤ sınır)."""
    ucgen = []
    for c in cokgenler:
        for j in range(1, len(c) - 1):
            ucgen.append((c[0], c[j], c[j + 1]))
    return np.asarray(ucgen, dtype=np.int64).reshape(-1, 3)


def _ply_oku(veri):
    bicim, govde_bas, v_oz, n_v, yuz = _ply_baslik(veri)
    v_adlar = [o[1] for o in v_oz]
    ix = [v_adlar.index(a) for a in ('x', 'y', 'z')]
    if bicim == 'ascii':
        try:
            metin = veri[govde_bas:].decode('ascii')
        except UnicodeDecodeError:
            _okuma('metin_degil', 'BICIM_HATASI')
        satirlar = metin.split('\n')
        satirlar = [s for s in (x.strip() for x in satirlar) if s]
        n_f = yuz[0] if yuz else 0
        if len(satirlar) != n_v + n_f:
            _okuma('ikili_boyut_tutarsiz', 'BICIM_HATASI', beyan=n_v + n_f,
                   bayt=len(veri))
        noktalar = np.empty((n_v, 3), dtype=float)
        for k in range(n_v):
            t = satirlar[k].split()
            if len(t) != len(v_oz):
                _okuma('sutun_sayisi', 'BICIM_HATASI', satir=k + 1,
                       sutun=len(t), beklenen=len(v_oz))
            for j, i in enumerate(ix):
                noktalar[k, j] = _hucre_sayi(t[i], k + 1)
        cokgenler = []
        for k in range(n_f):
            t = satirlar[n_v + k].split()
            if not t[0].isdigit():
                _okuma('sayi_degil', 'BICIM_HATASI', satir=n_v + k + 1)
            n = int(t[0])
            if not 3 <= n <= TANK_PLY_KOSE_SINIRI:
                _okuma('ply_yuz_kose', 'BICIM_HATASI', kose=n,
                       sinir=TANK_PLY_KOSE_SINIRI)
            if len(t) != n + 1 or not all(x.isdigit() for x in t[1:]):
                _okuma('sutun_sayisi', 'BICIM_HATASI', satir=n_v + k + 1,
                       sutun=len(t), beklenen=n + 1)
            cokgenler.append([int(x) for x in t[1:]])
        ucgenler = _yelpaze(cokgenler) if yuz else None
    else:
        dt = np.dtype([(o[1], '<' + _PLY_TURLERI[o[2]]) for o in v_oz])
        v_bayt = n_v * dt.itemsize
        if govde_bas + v_bayt > len(veri):
            _okuma('ikili_boyut_tutarsiz', 'BICIM_HATASI', beyan=n_v,
                   bayt=len(veri))
        v = np.frombuffer(veri, dtype=dt, count=n_v, offset=govde_bas)
        noktalar = np.stack([v['x'], v['y'], v['z']], axis=1).astype(float)
        konum = govde_bas + v_bayt
        ucgenler = None
        if yuz is None:
            if konum != len(veri):
                _okuma('ikili_boyut_tutarsiz', 'BICIM_HATASI', beyan=n_v,
                       bayt=len(veri))
        else:
            n_f, sayac_t, indeks_t = yuz
            st = np.dtype('<' + _PLY_TURLERI[sayac_t])
            it = np.dtype('<' + _PLY_TURLERI[indeks_t])
            kalan = len(veri) - konum
            # Hızlı yol: bütün yüzler üçgen (sabit kayıt boyu).
            sabit = np.dtype([('n', st), ('i', it, (3,))])
            if n_f * sabit.itemsize == kalan:
                f = np.frombuffer(veri, dtype=sabit, count=n_f, offset=konum)
                if not np.all(f['n'] == 3):
                    _okuma('ply_yuz_kose', 'BICIM_HATASI',
                           kose=int(f['n'][f['n'] != 3][0]),
                           sinir=TANK_PLY_KOSE_SINIRI)
                ucgenler = f['i'].astype(np.int64)
            else:
                cokgenler = []
                for _ in range(n_f):
                    if konum + st.itemsize > len(veri):
                        _okuma('ikili_boyut_tutarsiz', 'BICIM_HATASI',
                               beyan=n_f, bayt=len(veri))
                    n = int(np.frombuffer(veri, dtype=st, count=1,
                                          offset=konum)[0])
                    konum += st.itemsize
                    if not 3 <= n <= TANK_PLY_KOSE_SINIRI:
                        _okuma('ply_yuz_kose', 'BICIM_HATASI', kose=n,
                               sinir=TANK_PLY_KOSE_SINIRI)
                    if konum + n * it.itemsize > len(veri):
                        _okuma('ikili_boyut_tutarsiz', 'BICIM_HATASI',
                               beyan=n_f, bayt=len(veri))
                    cokgenler.append(np.frombuffer(
                        veri, dtype=it, count=n, offset=konum).astype(np.int64))
                    konum += n * it.itemsize
                if konum != len(veri):
                    _okuma('ikili_boyut_tutarsiz', 'BICIM_HATASI', beyan=n_f,
                           bayt=len(veri))
                ucgenler = _yelpaze(cokgenler)
    if ucgenler is not None:
        if ucgenler.shape[0] > TANK_UCGEN_SINIRI:
            _okuma('ucgen_siniri', 'BOYUT_SINIRI', ucgen=ucgenler.shape[0],
                   sinir=TANK_UCGEN_SINIRI)
        if ucgenler.size and (ucgenler.min() < 0 or ucgenler.max() >= n_v):
            _okuma('yuz_indeksi_gecersiz', 'BICIM_HATASI')
    return noktalar, ucgenler, None, None


_STL_IKILI_DT = np.dtype([('n', '<f4', (3,)), ('v', '<f4', (3, 3)),
                          ('a', '<u2')])
_STL_VERTEX_RE = re.compile(
    rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)')


def _stl_oku(veri):
    n_beyan = None
    if len(veri) >= 84:
        n_beyan = int(np.frombuffer(veri, dtype='<u4', count=1, offset=80)[0])
        if 84 + 50 * n_beyan == len(veri):
            if n_beyan > TANK_UCGEN_SINIRI:
                _okuma('ucgen_siniri', 'BOYUT_SINIRI', ucgen=n_beyan,
                       sinir=TANK_UCGEN_SINIRI)
            kayit = np.frombuffer(veri, dtype=_STL_IKILI_DT, count=n_beyan,
                                  offset=84)
            koseler = kayit['v'].astype(float).reshape(-1, 3)
            return _kaynakla(koseler) + (None, None)
    if veri.lstrip()[:5].lower() != b'solid':
        _okuma('ikili_boyut_tutarsiz', 'BICIM_HATASI',
               beyan=-1 if n_beyan is None else n_beyan, bayt=len(veri))
    metin = _metin_coz(veri).lower()
    n_facet = len(re.findall(r'\bfacet\s+normal\b', metin))
    n_end = len(re.findall(r'\bendfacet\b', metin))
    n_loop = len(re.findall(r'\bouter\s+loop\b', metin))
    if 'endsolid' not in metin:
        # Başı "solid" olan ama ikili boyutu tutmayan dosya da buraya düşer.
        _okuma('ikili_boyut_tutarsiz' if n_facet == 0 else 'stl_ascii_yapi',
               'BICIM_HATASI', beyan=-1 if n_beyan is None else n_beyan,
               bayt=len(veri), neden='endsolid')
    if n_facet > TANK_UCGEN_SINIRI:
        _okuma('ucgen_siniri', 'BOYUT_SINIRI', ucgen=n_facet,
               sinir=TANK_UCGEN_SINIRI)
    tepe = _STL_VERTEX_RE.findall(metin.encode('ascii', 'replace'))
    if not (n_facet == n_end == n_loop and len(tepe) == 3 * n_facet
            and n_facet > 0):
        _okuma('stl_ascii_yapi', 'BICIM_HATASI',
               neden=f'facet {n_facet}, endfacet {n_end}, loop {n_loop}, '
                     f'vertex {len(tepe)}')
    koseler = np.empty((len(tepe), 3), dtype=float)
    for k, (a, b, c) in enumerate(tepe):
        for j, h in enumerate((a, b, c)):
            koseler[k, j] = _hucre_sayi(h.decode('ascii', 'replace'), k + 1)
    return _kaynakla(koseler) + (None, None)


def _kaynakla(koseler):
    """Üçgen başına köşe dizisini (3F, 3) birebir eşit koordinatla kaynaklar.

    Tolerans KULLANILMAZ: aynı köşe her üçgende aynı bitlerle yazılır
    (STL ve BRepMesh paylaşılan kenar düğümü); toleranslı birleştirme ayrı
    noktaları sessizce birleştirebilirdi.
    """
    _sonlu(koseler)
    tekil, ters = np.unique(koseler, axis=0, return_inverse=True)
    return tekil, ters.reshape(-1, 3).astype(np.int64)


def _step_oku(yol, veri):
    from hrma.importers import step_import as si
    deps, _hata = si._load_deps()
    try:
        if deps is None:
            raise ImportError(_hata)
        from OCP.BRep import BRep_Tool
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.TopLoc import TopLoc_Location
    except Exception:  # noqa: BLE001 — eksik paket / dinamik yükleme hatası
        _kapi('B.1', 'STEP_MOZAIK_YOK', 'mozaikleyici_yok')
    if b'ISO-10303-21' not in veri[:4096]:
        _okuma('step_baslik', 'BICIM_HATASI')
    birim, _ham = si._detect_declared_unit(yol)
    if birim is None or birim not in _STEP_BIRIM_ESLEME:
        # Çekirdek tanımadığı birimi mm sayar; burada tahmin yürütülmez.
        if birim is None:
            _kapi('B.1', 'BIRIM_YOK', 'step_basliginda_yok')
        _kapi('B.1', 'BIRIM_YOK', 'desteklenmiyor', birim=str(birim))
    deps['STEPControl_Controller'].Init_s()
    deps['Interface_Static'].SetCVal_s('xstep.cascade.unit', 'MM')
    try:
        sekil = deps['import_step'](yol)
    except Exception:  # noqa: BLE001 — çekirdek ayrıştırıcı hatası
        _okuma('step_okunamadi', 'BICIM_HATASI')
    govdeler = si._collect_solids(sekil, deps)
    if len(govdeler) != 1:
        _okuma('step_govde_sayisi', 'BICIM_HATASI', govde=len(govdeler))
    kati = govdeler[0][1].wrapped
    bb = govdeler[0][1].bounding_box()
    kosegen = math.sqrt(bb.size.X ** 2 + bb.size.Y ** 2 + bb.size.Z ** 2)
    mesh = BRepMesh_IncrementalMesh(kati, TANK_STEP_SAPMA_ORANI * kosegen,
                                    False, TANK_STEP_ACI_RAD, True)
    mesh.Perform()
    koseler = []
    gezgin = deps['TopExp_Explorer'](kati, deps['TopAbs_FACE'])
    while gezgin.More():
        yuz = deps['TopoDS'].Face_s(gezgin.Current())
        konum = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(yuz, konum)
        if tri is not None:
            trsf = konum.Transformation()
            ters = yuz.Orientation() == deps['TopAbs_REVERSED']
            dugum = np.array([[p.X(), p.Y(), p.Z()] for p in
                              (tri.Node(i).Transformed(trsf)
                               for i in range(1, tri.NbNodes() + 1))])
            uc = np.array([tri.Triangle(i).Get()
                           for i in range(1, tri.NbTriangles() + 1)],
                          dtype=np.int64) - 1
            if ters:
                uc = uc[:, [0, 2, 1]]
            koseler.append(dugum[uc].reshape(-1, 3))
            if sum(len(k) for k in koseler) > 3 * TANK_UCGEN_SINIRI:
                _okuma('ucgen_siniri', 'BOYUT_SINIRI',
                       ucgen=sum(len(k) for k in koseler) // 3,
                       sinir=TANK_UCGEN_SINIRI)
        gezgin.Next()
    if not koseler:
        _okuma('step_ucgen_yok', 'BICIM_HATASI')
    noktalar, ucgenler = _kaynakla(np.concatenate(koseler))
    # OCCT, kürenin kutbundaki dejenere kenarda iki köşesi aynı düğüm olan
    # üçgen üretir (ölçüldü: kubbeli silindir STEP'inde 2 adet). Bu üçgenin
    # iki kenarı birbirinin tersidir, bir kenarı da kendine döner; atılması
    # kenar eşleşmesini değiştirmez. Yalnız TEKRAR EDEN İNDEKSLİ üçgen atılır
    # ve sayısı künyeye yazılır; üç ayrı köşeli sıfır alanlı üçgen B.2'de RET.
    tekrar = ((ucgenler[:, 0] == ucgenler[:, 1])
              | (ucgenler[:, 1] == ucgenler[:, 2])
              | (ucgenler[:, 0] == ucgenler[:, 2]))
    ucgenler = ucgenler[~tekrar]
    # Çekirdek oturum birimi mm: koordinatlar mm; dosyanın beyanı ayrıca
    # kullanıcının birimiyle karşılaştırılır.
    return (noktalar, ucgenler, None, _STEP_BIRIM_ESLEME[birim], 'mm',
            int(tekrar.sum()))


# ---------------------------------------------------------------------------
# Yüzlü girdi: B.2 kapalılık ve yüzey örnekleme
# ---------------------------------------------------------------------------
def ag_kapalilik(noktalar, ucgenler):
    """B.2 (yüzlü): kenar, yönelim, Euler, işaretli hacim. Hacmi döndürür."""
    P = np.asarray(noktalar, dtype=float)
    T = np.asarray(ucgenler, dtype=np.int64)
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    capraz = np.cross(b - a, c - a)
    alan2 = np.linalg.norm(capraz, axis=1)
    dejenere = ((T[:, 0] == T[:, 1]) | (T[:, 1] == T[:, 2])
                | (T[:, 0] == T[:, 2]) | (alan2 == 0.0))
    if np.any(dejenere):
        _kapi('B.2', 'YUZEY_KAPALI_DEGIL', 'dejenere_ucgen',
              adet=int(dejenere.sum()))
    n_v = int(P.shape[0])
    yonlu = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    yk = yonlu[:, 0] * n_v + yonlu[:, 1]
    yonsuz = np.sort(yonlu, axis=1)
    uk = yonsuz[:, 0] * n_v + yonsuz[:, 1]
    u_tekil, u_sayi = np.unique(uk, return_counts=True)
    acik = u_tekil[u_sayi == 1]
    if acik.size:
        orta = 0.5 * (P[acik // n_v] + P[acik % n_v])
        _kapi('B.2', 'YUZEY_KAPALI_DEGIL', 'acik_kenar', adet=int(acik.size),
              konumlar_m=np.round(orta[:10], 9).tolist())
    if np.any(u_sayi > 2):
        _kapi('B.2', 'YUZEY_KAPALI_DEGIL', 'manifold_degil',
              adet=int(np.sum(u_sayi > 2)))
    _yt, y_sayi = np.unique(yk, return_counts=True)
    if np.any(y_sayi > 1):
        _kapi('B.2', 'YUZEY_KAPALI_DEGIL', 'yonelim_tutarsiz',
              adet=int(np.sum(y_sayi > 1)))
    kullanilan = np.unique(T).size
    chi = kullanilan - u_tekil.size + T.shape[0]
    if chi != 2:
        _kapi('B.2', 'YUZEY_KAPALI_DEGIL', 'euler', chi=int(chi))
    hacim = float(np.sum(np.einsum('ij,ij->i', a, np.cross(b, c)))) / 6.0
    if not hacim > 0.0:
        _kapi('B.2', 'YUZEY_KAPALI_DEGIL', 'ters_yonelim', hacim_m3=hacim)
    return hacim


def _yuzey_ornekle(P, T):
    """Alan düzgün, belirlenimli yüzey örneklemesi (üçgen kafes merkezleri).

    Üçgen k² alt üçgene bölünür (k = ⌈√(alan / a0)⌉, a0 = toplam alan /
    hedef); her alt üçgenin ağırlık merkezi bir örnektir. Rastgelelik yok.
    """
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    alan = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    a0 = alan.sum() / TANK_AG_ORNEK_HEDEF
    k = np.clip(np.ceil(np.sqrt(alan / a0)), 1,
                TANK_AG_ORNEK_KAFES_SINIRI).astype(int)
    parcalar = []
    for kk in np.unique(k):
        sec = k == kk
        bary = []
        for i in range(kk):
            for j in range(kk - i):
                bary.append(((i + 1.0 / 3.0) / kk, (j + 1.0 / 3.0) / kk))
                if i + j <= kk - 2:
                    bary.append(((i + 2.0 / 3.0) / kk, (j + 2.0 / 3.0) / kk))
        B = np.asarray(bary)
        u, v = B[:, 0], B[:, 1]
        w = 1.0 - u - v
        pts = (w[None, :, None] * a[sec][:, None, :]
               + u[None, :, None] * b[sec][:, None, :]
               + v[None, :, None] * c[sec][:, None, :])
        parcalar.append(pts.reshape(-1, 3))
    return np.concatenate(parcalar)


# ---------------------------------------------------------------------------
# Eksen ve meridyen
# ---------------------------------------------------------------------------
#: Azimut referansı: girdi çerçevesinin +x ekseninin eksene dik izdüşümü;
#: eksen x'e çok yakınsa (|d·x| ≥ 0,9) +y. Kararlı ve kullanıcının
#: çerçevesinde okunur (θ = 0 → +x). HRMA seçimi.
_AZIMUT_REFERANS_COS = 0.9


def _ortonormal(d):
    e = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(e, d))) >= _AZIMUT_REFERANS_COS:
        e = np.array([0.0, 1.0, 0.0])
    e1 = e - np.dot(e, d) * d
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(d, e1)


def _izdusum(P, c, d):
    q = P - c
    z = q @ d
    rad = q - np.outer(z, d)
    return np.linalg.norm(rad, axis=1), z, rad


def _meridyen_kur(rho, z, n_kutu):
    """Kutupsal eşit sayılı kutularla meridyen çoklu çizgisi."""
    z_c = 0.5 * (float(z.min()) + float(z.max()))
    phi = np.arctan2(z - z_c, rho)
    s = np.hypot(rho, z - z_c)
    sira = np.argsort(phi, kind='stable')
    n = phi.size
    sinir = np.linspace(0, n, n_kutu + 1).astype(int)
    phi_k, s_k, kutular = [], [], []
    for j in range(n_kutu):
        idx = sira[sinir[j]:sinir[j + 1]]
        if idx.size == 0:
            continue
        kutular.append(idx)
        phi_k.append(float(np.median(phi[idx])))
        s_k.append(float(np.median(s[idx])))

    def kutup(idx):
        # Uç kutunun eksene yakın yarısında z = a + b ρ² uydurması.
        r_i = rho[idx]
        yakin = idx[r_i <= np.median(r_i)]
        A = np.stack([np.ones(yakin.size), rho[yakin] ** 2], axis=1)
        coz = np.linalg.lstsq(A, z[yakin], rcond=None)[0]
        return float(coz[0])

    z_alt = kutup(kutular[0])
    z_ust = kutup(kutular[-1])
    r_n = [0.0] + [sk * math.cos(pk) for pk, sk in zip(phi_k, s_k)] + [0.0]
    z_n = ([z_alt] + [z_c + sk * math.sin(pk) for pk, sk in zip(phi_k, s_k)]
           + [z_ust])
    phi_n = ([-0.5 * math.pi] + phi_k + [0.5 * math.pi])
    return {'r': np.asarray(r_n), 'z': np.asarray(z_n),
            'phi': np.asarray(phi_n), 'z_c': z_c, 'kutular': kutular,
            'phi_noktalar': phi, 's_noktalar': s}


def _meridyen_artik(rho, z, mer):
    """(ρ, z) noktalarının meridyen çoklu çizgisine işaretli dik uzaklığı."""
    rn, zn, pn = mer['r'], mer['z'], mer['phi']
    zc = mer['z_c']
    phi = np.arctan2(z - zc, rho)
    s = np.hypot(rho, z - zc)
    K = rn.size
    k = np.clip(np.searchsorted(pn, phi), 1, K - 1)
    en_iyi = np.full(rho.shape, np.inf)
    for off in (-2, -1, 0):
        j = np.clip(k + off, 0, K - 2)
        ax, az = rn[j], zn[j]
        bx, bz = rn[j + 1], zn[j + 1]
        vx, vz = bx - ax, bz - az
        L2 = vx * vx + vz * vz
        t = np.where(L2 > 0, ((rho - ax) * vx + (z - az) * vz)
                     / np.where(L2 > 0, L2, 1.0), 0.0)
        t = np.clip(t, 0.0, 1.0)
        dx = rho - (ax + t * vx)
        dz = z - (az + t * vz)
        en_iyi = np.minimum(en_iyi, np.hypot(dx, dz))
    s_n = np.hypot(rn, zn - zc)
    s_hat = np.interp(phi, pn, s_n)
    return np.where(s >= s_hat, 1.0, -1.0) * en_iyi


def _kutu_sayisi(n):
    return int(np.clip(n // TANK_MERIDYEN_KUTU_NOKTA,
                       TANK_MERIDYEN_KUTU_EN_AZ, TANK_MERIDYEN_KUTU_EN_COK))


def _eksen_uydur(P, c0, d0):
    """Eksen inceltme (TANK §B.3.2): soft-L1, dönüşümlü profil güncellemesi."""
    from scipy.optimize import least_squares

    idx = np.unique(np.linspace(0, P.shape[0] - 1,
                                min(P.shape[0], TANK_EKSEN_ALT_ORNEK))
                    .astype(int))
    Q = P[idx]
    c, d = np.asarray(c0, float).copy(), np.asarray(d0, float).copy()
    d /= np.linalg.norm(d)
    rho, z, _ = _izdusum(Q, c, d)
    R_s = float(np.max(rho)) if np.max(rho) > 0 else 1.0
    tur = 0
    onceki = None
    for tur in range(1, TANK_EKSEN_TUR_SINIRI + 1):
        rho, z, _ = _izdusum(Q, c, d)
        mer = _meridyen_kur(rho, z, _kutu_sayisi(Q.shape[0]))
        e1, e2 = _ortonormal(d)

        def eksen(x, c=c, d=d, e1=e1, e2=e2):
            dd = d + x[0] * e1 + x[1] * e2
            dd = dd / np.linalg.norm(dd)
            return c + R_s * (x[2] * e1 + x[3] * e2), dd

        def artik(x):
            cc, dd = eksen(x)
            r_, z_, _ = _izdusum(Q, cc, dd)
            return _meridyen_artik(r_, z_, mer)

        coz = least_squares(artik, np.zeros(4), loss='soft_l1',
                            f_scale=TANK_SOFT_L1_ORANI * R_s, max_nfev=50)
        c_yeni, d_yeni = eksen(coz.x)
        degisim = (np.linalg.norm(d_yeni - d) * R_s
                   + np.linalg.norm(c_yeni - c - np.dot(c_yeni - c, d_yeni)
                                    * d_yeni))
        c, d = c_yeni, d_yeni
        if degisim < TANK_EKSEN_DURMA_ORANI * R_s:
            break
        if (onceki is not None and abs(onceki - coz.cost)
                <= TANK_EKSEN_MALIYET_DURMA * max(onceki, 1e-300)):
            break
        onceki = coz.cost
    return c, d, tur


def _baslangic_ekseni(P, kullanici_ekseni, ust):
    if kullanici_ekseni is not None:
        return kullanici_ekseni[0], kullanici_ekseni[1], 'kullanici'
    c = P.mean(axis=0)
    cov = np.cov((P - c).T)
    w, V = np.linalg.eigh(cov)          # artan
    if (w[2] - w[0]) <= TANK_PCA_KURE_ESIGI * w[2]:
        return c, ust / np.linalg.norm(ust), 'ust_yon(kureye_yakin)'
    i = 0 if (w[1] - w[0]) > (w[2] - w[1]) else 2
    return c, V[:, i], 'pca'


# ---------------------------------------------------------------------------
# Ana giriş noktaları
# ---------------------------------------------------------------------------
def tank_geometrisi_oku(yol, birim=None, *, ust_yon=None, eksen=None,
                        sigma_n=None):
    """Tank iç geometrisi dosyasını okur, kapılardan geçirir.

    Parameters
    ----------
    yol : str
        Dosya yolu; biçim uzantıdan (``UZANTI_BICIMLERI``).
    birim : {'m', 'mm', 'in'} | None
        Dosyanın uzunluk birimi. CSV birim satırı ya da STEP başlığı birim
        taşıyorsa verilmeyebilir; ikisi de varsa aynı olmalıdır.
    ust_yon : 3-vektör | None
        Burun yönü (3B girdide ZORUNLU; profil girdisinde kullanılmaz).
    eksen : (nokta, yön) | None
        Kullanıcının tank ekseni (dosya biriminde nokta). Verilmezse PCA ile
        başlanır; her durumda §B.3.2 inceltmesi uygulanır.
    sigma_n : float | None
        Ölçüm gürültüsü (dosya biriminde). Verilirse σ̂_n kestirimi yerine
        kullanılır.

    Returns
    -------
    dict
        ``durum`` ∈ {GECERLI, BEYANLI, RET}. RET'te ``kapi``, ``sebep``
        (sözleşme kodu) ya da ``okuma_hatasi`` (sözleşme okuyucu hata türü),
        ``mesaj_anahtari``/``mesaj_parametreleri``/``mesaj_en``. Kabulde
        ``profil_rz_m`` (tank çerçevesi), ``geometri`` (R_ref_m, H_ic_m,
        V_ic_m3), ``olcumler``, ``beyanlar``, ``kunye``; ``sebep`` kabulde
        beyanların BEYAN sınıfı sözleşme kodlarıdır (v307-2:
        ``GURULTU_ESIKLE_KIYASLANABILIR``), durum onlardan türetilir.
        İstisna sızdırmaz.
    """
    kunye = {'dosya_adi': None, 'sha256': None, 'bicim': None,
             'birim': None}
    try:
        if not isinstance(yol, (str, os.PathLike)):
            _okuma('bos_dosya', 'BICIM_HATASI')
        yol = os.fspath(yol)
        kunye['dosya_adi'] = os.path.basename(yol)
        uzanti = os.path.splitext(yol)[1].lower()
        bicim = UZANTI_BICIMLERI.get(uzanti)
        if bicim is None:
            _okuma('bicim_desteklenmiyor', 'BICIM_HATASI',
                   uzanti=uzanti[:16])
        kunye['bicim'] = bicim
        if not os.path.isfile(yol):
            _okuma('bos_dosya', 'BICIM_HATASI')
        bayt = os.path.getsize(yol)
        sinir = (TANK_STEP_BOYUT_SINIRI if bicim == 'step'
                 else TANK_DOSYA_BOYUT_SINIRI)
        if bayt > sinir:
            _okuma('dosya_boyutu', 'BOYUT_SINIRI', bayt=bayt, sinir=sinir)
        if bayt == 0:
            _okuma('bos_dosya', 'BICIM_HATASI')
        with open(yol, 'rb') as fh:
            veri = fh.read(sinir + 1)
        if len(veri) > sinir:
            _okuma('dosya_boyutu', 'BOYUT_SINIRI', bayt=len(veri), sinir=sinir)
        kunye['sha256'] = hashlib.sha256(veri).hexdigest()
        koord_birimi = None
        try:
            if bicim == 'csv':
                P, T, prof, dosya_birimi = _csv_oku(veri)
            elif bicim == 'xyz':
                P, T, prof, dosya_birimi = _xyz_oku(veri)
            elif bicim == 'ply':
                P, T, prof, dosya_birimi = _ply_oku(veri)
            elif bicim == 'stl':
                P, T, prof, dosya_birimi = _stl_oku(veri)
            else:
                (P, T, prof, dosya_birimi, koord_birimi,
                 atilan) = _step_oku(yol, veri)
                kunye['step_mozaik'] = {
                    'sapma_orani': TANK_STEP_SAPMA_ORANI,
                    'aci_rad': TANK_STEP_ACI_RAD,
                    'tekrar_eden_dugumlu_ucgen_atildi': atilan}
        except (_Ret, SloshTabloHatasi):
            raise
        except MemoryError:
            _okuma('dosya_boyutu', 'BOYUT_SINIRI', bayt=bayt, sinir=sinir)
        except Exception as exc:  # noqa: BLE001 — ayrıştırıcı istisnası sızmaz
            _okuma('ayristirici_hatasi', 'BICIM_HATASI',
                   tur=type(exc).__name__)
        b = _birim_coz(birim, dosya_birimi)
        kunye['birim'] = b
        olcek = BIRIM_CARPANLARI[koord_birimi or b]
        if prof is not None:
            return _profil_sonucu(prof * olcek, kunye)
        return _bulut_ya_da_ag(P * olcek, T, kunye, b, ust_yon=ust_yon,
                               eksen=eksen, sigma_n=sigma_n)
    except _Ret as ret:
        return _ret_sonucu(ret, kunye)
    except Exception as exc:  # noqa: BLE001 — hiçbir istisna sızdırılmaz
        return _ret_sonucu(_Ret('B.1', 'ayristirici_hatasi',
                                okuma_kodu='BICIM_HATASI',
                                parametreler={'tur': type(exc).__name__}),
                           kunye)


def profil_girdisi_isle(profil_rz_m, kunye=None):
    """(r, z) profil [m] girdisini B.4 profil kapılarından geçirir.

    z alt kutuptan üst kutba azalmayan; ilk ve son nokta eksende. Tank
    çerçevesine (en alt nokta z = 0) kaydırılır.
    """
    try:
        return _profil_sonucu(np.asarray(profil_rz_m, dtype=float),
                              dict(kunye or {}))
    except _Ret as ret:
        return _ret_sonucu(ret, dict(kunye or {}))
    except (TypeError, ValueError):
        return _ret_sonucu(_Ret('B.4', 'profil_sayi_degil',
                                okuma_kodu='TUR_HATASI'), dict(kunye or {}))


def _profil_hatasini_cevir(exc, kapi='B.4'):
    if exc.sebep is not None:
        _kapi(kapi, exc.sebep, exc.ayrinti, **exc.parametreler)
    _okuma(exc.ayrinti, exc.okuma_kodu, kapi=kapi, **exc.parametreler)


def _profil_sonucu(prof, kunye):
    _sonlu(prof)
    kunye.setdefault('nokta_sayisi', int(prof.shape[0]))
    try:
        p = profil_dogrula(prof)
    except ProfilHatasi as exc:
        _profil_hatasini_cevir(exc)
    p[:, 1] = p[:, 1] - p[0, 1]
    return _kabul(p, kunye, olcumler={}, beyanlar=[])


def _kabul(p, kunye, olcumler, beyanlar):
    V = ic_hacim(p)
    # v307-2 (K6): her beyan sözleşmenin BEYAN sınıfı bir sebep kodunu
    # taşır; durum kodlardan türetilir (slosh_tablo.durum_birlestir).
    sebep = [b['sebep'] for b in beyanlar]
    durum = durum_birlestir(sebep)
    return {
        'durum': durum,
        'kapi': None,
        'sebep': sebep,
        'okuma_hatasi': None,
        'profil_rz_m': p.tolist(),
        'geometri': {'R_ref_m': float(p[:, 0].max()),
                     'H_ic_m': float(p[-1, 1] - p[0, 1]),
                     'V_ic_m3': V},
        'olcumler': olcumler,
        'beyanlar': beyanlar,
        'kunye': kunye,
    }


def nokta_bulutu_isle(noktalar_m, *, ust_yon, ucgenler=None, eksen=None,
                      sigma_n_m=None, kunye=None):
    """Bellekteki 3B nokta bulutu / üçgen ağını [m] B.2–B.4'ten geçirir."""
    kunye = dict(kunye or {})
    try:
        P = np.asarray(noktalar_m, dtype=float)
        if P.ndim != 2 or P.shape[1] != 3:
            _okuma('sutun_sayisi', 'BICIM_HATASI', satir=0,
                   sutun=int(P.shape[-1]) if P.ndim else 0, beklenen=3)
        T = None if ucgenler is None else np.asarray(ucgenler, dtype=np.int64)
        return _bulut_ya_da_ag(P, T, kunye, 'm', ust_yon=ust_yon,
                               eksen=eksen, sigma_n=sigma_n_m)
    except _Ret as ret:
        return _ret_sonucu(ret, kunye)


def _bulut_ya_da_ag(P, T, kunye, birim, *, ust_yon, eksen, sigma_n):
    olcek = BIRIM_CARPANLARI[birim]
    _sonlu(P)
    if P.shape[0] > TANK_NOKTA_SINIRI and T is None:
        _okuma('nokta_siniri', 'BOYUT_SINIRI', nokta=int(P.shape[0]),
               sinir=TANK_NOKTA_SINIRI)
    if ust_yon is None:
        _okuma('ust_yon_yok', 'ALAN_EKSIK', alan='ust_yon')
    ust = _vektor3(ust_yon, 'ust_yon_gecersiz', 'ust_yon')
    ust = ust / np.linalg.norm(ust)
    kullanici_ekseni = None
    if eksen is not None:
        try:
            nokta, yon = eksen
        except (TypeError, ValueError):
            _okuma('eksen_gecersiz', 'DEGER_GECERSIZ', alan='eksen')
        nk = np.asarray(nokta, dtype=float).reshape(-1)
        if nk.shape != (3,) or not np.all(np.isfinite(nk)):
            _okuma('eksen_gecersiz', 'DEGER_GECERSIZ', alan='eksen')
        y = _vektor3(yon, 'eksen_gecersiz', 'eksen')
        kullanici_ekseni = (nk * olcek, y / np.linalg.norm(y))
    sig = None
    if sigma_n is not None:
        if (isinstance(sigma_n, (bool, np.bool_))
                or not isinstance(sigma_n, numbers.Real)
                or not math.isfinite(float(sigma_n)) or float(sigma_n) < 0):
            _okuma('sigma_gecersiz', 'DEGER_GECERSIZ', alan='sigma_n')
        sig = float(sigma_n) * olcek

    V_ag = None
    if T is not None:
        if T.ndim != 2 or T.shape[1] != 3:
            _okuma('yuz_indeksi_gecersiz', 'BICIM_HATASI')
        if T.shape[0] > TANK_UCGEN_SINIRI:
            _okuma('ucgen_siniri', 'BOYUT_SINIRI', ucgen=int(T.shape[0]),
                   sinir=TANK_UCGEN_SINIRI)
        if T.size == 0 or T.min() < 0 or T.max() >= P.shape[0]:
            _okuma('yuz_indeksi_gecersiz', 'BICIM_HATASI')
        kunye.setdefault('ucgen_sayisi', int(T.shape[0]))
        kunye.setdefault('nokta_sayisi', int(P.shape[0]))
        V_ag = ag_kapalilik(P, T)                       # B.2 (yüzlü)
        Ps = _yuzey_ornekle(P, T)
        kunye['yuzey_ornek_sayisi'] = int(Ps.shape[0])
    else:
        kunye.setdefault('nokta_sayisi', int(P.shape[0]))
        en_az = TANK_AZIMUT_DILIMI * TANK_Z_KUTUSU * TANK_HUCRE_EN_AZ_NOKTA
        if P.shape[0] < en_az:
            _okuma('nokta_az', 'DEGER_GECERSIZ', nokta=int(P.shape[0]),
                   en_az=en_az, n_theta=TANK_AZIMUT_DILIMI, n_z=TANK_Z_KUTUSU)
        Ps = P

    # --- eksen (B.3.1–B.3.2) ---------------------------------------------
    c0, d0, kaynak = _baslangic_ekseni(Ps, kullanici_ekseni, ust)
    c, d, tur = _eksen_uydur(Ps, c0, d0)
    cosu = float(np.dot(d, ust))
    if abs(cosu) < TANK_UST_YON_COS_ESIGI:
        _okuma('ust_yon_eksene_dik', 'DEGER_GECERSIZ', alan='ust_yon',
               aci_deg=round(math.degrees(math.acos(min(1.0, abs(cosu)))), 1))
    if cosu < 0:
        d = -d
    rho, z, rad = _izdusum(Ps, c, d)
    R_ref = float(np.max(rho))
    e1, e2 = _ortonormal(d)
    theta = np.mod(np.arctan2(rad @ e2, rad @ e1), 2.0 * math.pi)
    dilim = np.minimum((theta / (2.0 * math.pi) * TANK_AZIMUT_DILIMI)
                       .astype(int), TANK_AZIMUT_DILIMI - 1)
    z_min, z_max = float(z.min()), float(z.max())

    # --- B.2 (yüzsüz): kapsama ve uç kapanması ---------------------------
    if T is None:
        # Kapsama kutuları meridyen boyunca EŞİT SAYILI: eksen üzerindeki
        # orta noktadan kutupsal açı φ'nin sıra düzeyiyle n_z kutu.
        # Tasarım düzeltmesi (RAPOR §3), ölçülerek:
        #  * eşit genişlikli z kutusunda sivri koni ucunun son kutusu çok
        #    küçük alan taşır (60 000 noktada dilim başına ~2,8 nokta) ve
        #    sağlam tank "eksik bölge" diye reddedilirdi;
        #  * z'ye göre eşit sayılı kutu düz başı böler: uydurulan eksenin
        #    10⁻⁶ rad'lık kalan eğimi düz yüzdeki noktaları z sırasında
        #    azimuta göre dizer ve her kutu bir azimut dilimine düşerdi.
        #  φ kutusu düz başı halkalara, duvarı z şeritlerine böler.
        z_c = 0.5 * (z_min + z_max)
        phi_k = np.arctan2(z - z_c, rho)
        sira = np.argsort(phi_k, kind='stable')
        zk = np.empty(z.size, dtype=np.int64)
        zk[sira] = np.arange(z.size) * TANK_Z_KUTUSU // z.size
        kutu_z_min = np.full(TANK_Z_KUTUSU, np.inf)
        kutu_z_max = np.full(TANK_Z_KUTUSU, -np.inf)
        np.minimum.at(kutu_z_min, zk, z)
        np.maximum.at(kutu_z_max, zk, z)
        sayim = np.bincount(zk * TANK_AZIMUT_DILIMI + dilim,
                            minlength=TANK_Z_KUTUSU * TANK_AZIMUT_DILIMI)
        eksik = np.nonzero(sayim < TANK_HUCRE_EN_AZ_NOKTA)[0]
        if eksik.size:
            ej, es = eksik // TANK_AZIMUT_DILIMI, eksik % TANK_AZIMUT_DILIMI
            w = 360.0 / TANK_AZIMUT_DILIMI
            _kapi('B.2', 'EKSIK_BOLGE', 'kapsama', adet=int(eksik.size),
                  z_min_m=round(float(kutu_z_min[ej].min() - z_min), 9),
                  z_max_m=round(float(kutu_z_max[ej].max() - z_min), 9),
                  dilimler=[[round(float(s * w), 3), round(float((s + 1) * w),
                                                           3)]
                            for s in np.unique(es)],
                  azimut_referansi=np.round(e1, 9).tolist(),
                  hucreler=[{'z_m': [round(float(kutu_z_min[j] - z_min), 9),
                                     round(float(kutu_z_max[j] - z_min), 9)],
                             'theta_deg': [round(float(s * w), 3),
                                           round(float((s + 1) * w), 3)]}
                            for j, s in zip(ej[:20], es[:20])])
    # --- meridyen ve tek yüzey (B.4a) --------------------------------------
    mer = _meridyen_kur(rho, z, _kutu_sayisi(rho.size))
    s_n = mer['s_noktalar']
    for idx in mer['kutular']:
        ss = np.sort(s_n[idx])
        if ss.size < 2:
            continue
        bosluk = np.diff(ss)
        i = int(np.argmax(bosluk))
        pay = min(i + 1, ss.size - i - 1) / ss.size
        if (bosluk[i] > TANK_IKI_YUZEY_ACIKLIK_ORANI * R_ref
                and pay >= TANK_IKI_YUZEY_PAY):
            zz = float(np.median(z[idx]) - z_min)
            _kapi('B.4', 'PROFIL_TEK_DEGERLI_DEGIL', 'iki_yuzey',
                  z_m=round(zz, 9))

    # --- B.2 uç kapanması (yüzsüz) -------------------------------------------
    # Orta noktanın altında ve üstünde, eksene r_k = max(%5 R_ref, 3ℓ)
    # mesafeden yakın en az TANK_HUCRE_EN_AZ_NOKTA nokta olmalı: düz baş da
    # kubbe de eksene ulaşır; açık uçlu borunun ucunda eksen yanı boştur.
    if T is None:
        rn_, zn_ = mer['r'], mer['z']
        A = float(np.sum(math.pi * (rn_[:-1] + rn_[1:])
                         * np.hypot(np.diff(rn_), np.diff(zn_))))
        aralik = math.sqrt(A / rho.size)
        r_k = max(TANK_UC_KUBBE_ORANI * R_ref, TANK_UC_ARALIK_KATI * aralik)
        for uc, taraf in (('alt', z < mer['z_c']), ('ust', z > mer['z_c'])):
            yakin = int(np.sum(taraf & (rho <= r_k)))
            if yakin < TANK_HUCRE_EN_AZ_NOKTA:
                _kapi('B.2', 'YUZEY_KAPALI_DEGIL', 'bas_kapanmiyor', uc=uc,
                      eksene_yakin_nokta=yakin, yaricap_m=round(r_k, 9))

    # --- B.3 simetri ---------------------------------------------------------
    n_art = _meridyen_artik(rho, z, mer)
    kutu_no = np.empty(rho.size, dtype=np.int64)
    for j, idx in enumerate(mer['kutular']):
        kutu_no[idx] = j
    hucre = kutu_no * TANK_AZIMUT_DILIMI + dilim
    n_h = len(mer['kutular']) * TANK_AZIMUT_DILIMI
    say = np.bincount(hucre, minlength=n_h)
    top = np.bincount(hucre, weights=n_art, minlength=n_h)
    ort = np.where(say > 0, top / np.maximum(say, 1), np.nan)
    ort2 = ort.reshape(-1, TANK_AZIMUT_DILIMI)
    say2 = say.reshape(-1, TANK_AZIMUT_DILIMI)
    gecerli = say2 >= TANK_HUCRE_EN_AZ_NOKTA
    hi = np.where(gecerli, ort2, -np.inf).max(axis=1)
    lo = np.where(gecerli, ort2, np.inf).min(axis=1)
    delta = np.where(gecerli.sum(axis=1) >= 2, (hi - lo) / R_ref, 0.0)
    j_kotu = int(np.argmax(delta))
    eps_max = float(delta[j_kotu])
    eps_rms = float(math.sqrt(float(np.mean(n_art ** 2)))) / R_ref
    hucre_ici = n_art - np.where(say[hucre] > 0, ort[hucre], 0.0)
    sigma_hat = MAD_SIGMA_KATSAYISI * float(
        np.median(np.abs(hucre_ici - np.median(hucre_ici))))
    sigma = sig if sig is not None else sigma_hat
    esik_max = TANK_SIMETRI_ESIGI + 3.0 * sigma / R_ref
    esik_rms = TANK_SIMETRI_RMS_ESIGI + sigma / R_ref
    z_kotu = float(np.median(z[mer['kutular'][j_kotu]]) - z_min)
    olcumler = {
        'eps_max': eps_max, 'eps_rms': eps_rms,
        'esik_eps_max': esik_max, 'esik_eps_rms': esik_rms,
        'sigma_n_m': sigma, 'sigma_n_kaynak': ('kullanici' if sig is not None
                                               else 'kestirim_MAD_hucre_ici'),
        'sigma_n_kestirim_m': sigma_hat,
        'en_kotu_z_m': z_kotu,
        'eksen_baslangic': kaynak, 'eksen_tur': int(tur),
        'meridyen_kutu': len(mer['kutular']),
    }
    if eps_max > esik_max or eps_rms > esik_rms:
        _kapi('B.3', 'EKSENEL_SIMETRIK_DEGIL', 'esik',
              eps_max=round(eps_max, 6), esik_eps_max=round(esik_max, 6),
              eps_rms=round(eps_rms, 6), esik_eps_rms=round(esik_rms, 6),
              z_m=round(z_kotu, 9))
    beyanlar = []
    if sigma / R_ref > TANK_GURULTU_BEYAN_ESIGI:
        beyanlar.append({
            'kod': 'gurultu_esikle_kiyaslanabilir',
            'sebep': 'GURULTU_ESIKLE_KIYASLANABILIR',
            'mesaj_anahtari': f'{_METIN_ONEKI}.beyan.'
                              'gurultu_esikle_kiyaslanabilir',
            'mesaj_parametreleri': {'sigma_oran': round(sigma / R_ref, 6)},
            'mesaj_en': _metin('BEYAN', 'gurultu_esikle_kiyaslanabilir',
                               {'sigma_oran': round(sigma / R_ref, 6)})})

    # --- B.4 profil ----------------------------------------------------------
    rn, zn = mer['r'].copy(), mer['z'].copy()
    tol = (TANK_Z_MONOTON_SIGMA_KATI * sigma
           + TANK_DUGUM_KURULUM_PAYI_ORANI * R_ref)
    geri = np.diff(zn)
    if np.any(geri < -tol):
        i = int(np.argmax(geri < -tol))
        _kapi('B.4', 'PROFIL_TEK_DEGERLI_DEGIL', 'z_monoton_degil',
              z_m=round(float(zn[i + 1] - z_min), 9))
    zd = np.maximum.accumulate(zn)
    olcumler['gurultu_payinda_duzlestirilen_dugum'] = int(np.sum(zd != zn))
    prof = np.stack([rn, zd - zd[0]], axis=1)
    try:
        p = profil_dogrula(prof)
    except ProfilHatasi as exc:
        _profil_hatasini_cevir(exc)
    if V_ag is not None:
        V_p = ic_hacim(p)
        fark = abs(V_p - V_ag) / V_ag
        olcumler['V_ag_m3'] = V_ag
        olcumler['hacim_bagil_fark'] = fark
        if fark > TANK_HACIM_TUTARLILIK_ESIGI:
            _kapi('B.4', 'PROFIL_AG_HACIM_TUTARSIZ', 'hacim',
                  V_profil_m3=V_p, V_ag_m3=V_ag,
                  fark_yuzde=round(100.0 * fark, 4),
                  sinir_yuzde=100.0 * TANK_HACIM_TUTARLILIK_ESIGI)
    alt_kutup = c + float(mer['z'][0]) * d
    kunye['eksen'] = {'alt_kutup_m': (alt_kutup).tolist(),
                      'yon': d.tolist(), 'kaynak': kaynak}
    return _kabul(p, kunye, olcumler, beyanlar)
