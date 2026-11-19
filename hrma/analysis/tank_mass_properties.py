"""3.0.7 TANK-GEOMETRİ — doluluğa göre sıvı kütle özellikleri (TANK §C).

Tasarım: ``docs/tasarim/v307/TANK_GEOMETRI_TASARIM.md`` §C (kulvar K3a,
KARTLAR K3 kalem 4). Sözleşme: ``hrma.analysis.slosh_tablo`` (doluluk
ızgarası, sebep kodları, profil nokta sınırı TEK YERDE oradadır; bu modül
yalnız içe aktarır).

Girdi: tank çerçevesinde (r, z) iç profili [m]. z tank simetri ekseni,
sıfır en alt iç nokta, yukarı (buruna doğru) pozitif (sözleşme §F.1).
Profil parçalı doğrusaldır; her parça bir kesik koni. İlk ve son nokta
eksen üzerindedir (r = 0); düz baş, eksene inen yatay bir parçadır.

Büyüklükler (h serbest yüzey yüksekliği, ρ sıvı yoğunluğu):

==============================  ==========================================  =====
Büyüklük                        İfade                                       Derece
==============================  ==========================================  =====
V(h)                            ∫₀ʰ π r(z)² dz                              2
z_km(h)                         (1/V) ∫₀ʰ π r² z dz                          3
I_km,donmuş(h) (enine)          ρ ∫₀ʰ π r² [ r²/4 + (z − z_km)² ] dz         4
I_eksenel,donmuş(h)             ρ ∫₀ʰ π r⁴/2 dz                             4
A_yüzey(h), R_yüzey(h)          π r(h)², r(h)                               —
==============================  ==========================================  =====

Enine eylemsizlik: dz kalınlıklı r yarıçaplı diskin kendi çapına göre
eylemsizliği (1/4) dm r² ile paralel eksen terimi dm (z − z_km)²'nin
toplamı. Eksenel: diskin kendi eksenine göre (1/2) dm r².

Kareleme: her parça 3 noktalı Gauss–Legendre ile alınır. r(z) parça içinde
doğrusal olduğundan integrandların derecesi ≤ 4'tür; n noktalı
Gauss–Legendre 2n − 1 = 5. dereceye kadar TAMDIR (Abramowitz & Stegun 1964,
§25.4.29–25.4.30, Tablo 25.4, n = 3). Bu yüzden sonuç, verilen parçalı
doğrusal profil için kareleme hatası taşımaz; kalan tek hata profilin
gerçek yüzeyi temsil hatasıdır (ağ inceltmesiyle ikinci mertebeden kapanır,
``tests/test_tank_mass_properties.py``).

Doluluk → h: V(h) = doluluk · V_iç denkleminin kökü. V(h) monoton artar;
kök, kökü içeren parçada ikiye bölmeyle bulunur, tolerans 10⁻¹² V_iç
(TANK §C).

Kesit yarıçapı r(h): h bir yatay parçanın (omuz, düz baş) tam üstüne
düşerse r(h) aşağıdan sınır değeridir (h'nin altındaki parçanın üst ucu).
"""

from __future__ import annotations

import math
import numbers

import numpy as np

from hrma.analysis.slosh_tablo import (
    DOLULUK_IZGARASI,
    OKUYUCU_HATA_KODLARI,
    PROFIL_NOKTA_SINIRI,
    SEBEP_KODLARI,
)

# ---------------------------------------------------------------------------
# Kareleme: 3 noktalı Gauss–Legendre, [-1, 1] üzerinde.
# Abramowitz & Stegun (1964) Tablo 25.4, n = 3: düğümler 0, ±√(3/5);
# ağırlıklar 8/9, 5/9. 2n − 1 = 5. dereceye kadar tam.
# ---------------------------------------------------------------------------
GAUSS_DUGUMLERI = np.array([-math.sqrt(3.0 / 5.0), 0.0,
                            math.sqrt(3.0 / 5.0)])
GAUSS_AGIRLIKLARI = np.array([5.0 / 9.0, 8.0 / 9.0, 5.0 / 9.0])

#: Doluluk → h kök bulmasının hacim toleransı, V_iç'e göre bağıl (TANK §C).
DOLULUK_KOK_BAGIL_TOL = 1e-12
#: İkiye bölme adım sınırı. 2⁻²⁰⁰ ≪ çift duyarlık; sınır yalnız sonsuz
#: döngüye karşı korumadır. HRMA seçimi.
DOLULUK_KOK_ADIM_SINIRI = 200


class ProfilHatasi(ValueError):
    """Profil kapısı reddi (TANK §B.4) — makine-okur ayrıntıyla.

    ``sebep``: ``slosh_tablo.SEBEP_KODLARI`` içinden bir kod (kapı reddi)
    ya da ``None``. ``okuma_kodu``: sözleşme okuyucusunun hata türü
    (``SloshTabloHatasi.kod`` sözlüğü: ``BOYUT_SINIRI``, ``DEGER_GECERSIZ``,
    ``TUR_HATASI``) ya da ``None``. İkisinden biri doludur.
    ``ayrinti``: alt neden (metin anahtarının son parçası).
    """

    def __init__(self, mesaj, *, ayrinti, sebep=None, okuma_kodu=None,
                 parametreler=None):
        super().__init__(mesaj)
        if (sebep is None) == (okuma_kodu is None):
            raise TypeError('ProfilHatasi: sebep ya da okuma_kodu, '
                            'yalnız biri verilir')
        if sebep is not None and sebep not in SEBEP_KODLARI:
            raise TypeError(f'ProfilHatasi: sözleşmede olmayan kod {sebep!r}')
        # v307-2 (K6): okuyucu hata türü sözleşmenin adlı sabitlerinden.
        if okuma_kodu is not None and okuma_kodu not in OKUYUCU_HATA_KODLARI:
            raise TypeError(f'ProfilHatasi: sözleşmede olmayan okuyucu hata '
                            f'türü {okuma_kodu!r}')
        self.sebep = sebep
        self.okuma_kodu = okuma_kodu
        self.ayrinti = ayrinti
        self.parametreler = dict(parametreler or {})


def _sayi_kapisi(deger, ad, *, pozitif=False):
    if isinstance(deger, (bool, np.bool_)) or not isinstance(deger,
                                                            numbers.Real):
        raise ValueError(f'{ad}: sayı bekleniyordu ({type(deger).__name__})')
    f = float(deger)
    if not math.isfinite(f):
        raise ValueError(f'{ad}: sonlu olmayan sayı')
    if pozitif and not f > 0.0:
        raise ValueError(f'{ad}: pozitif olmalı ({f!r})')
    return f


# ---------------------------------------------------------------------------
# Profil kapısı (TANK §B.4, (r, z) profil)
# ---------------------------------------------------------------------------
def profil_dogrula(profil):
    """(r, z) profilini denetler; geçerse (K, 2) float64 dizi döndürür.

    Kurallar (TANK §B.4):
      * en az 3, en çok ``slosh_tablo.PROFIL_NOKTA_SINIRI`` nokta; sonlu
        sayılar; r ≥ 0;
      * uçlar eksende: r[0] = r[-1] = 0 (düz baş, eksene inen yatay
        parçadır); değilse ``YUZEY_KAPALI_DEGIL``;
      * z azalmayan; azalırsa ``PROFIL_TEK_DEGERLI_DEGIL`` (aynı z'de iki iç
        yüzey);
      * iç düğüm eksende değil (r > 0): eksene değen iç düğüm hacmi iki
        parçaya böler;
      * kendini kesmez: z azalmayan bir çoklu çizgide kesişme yalnız aynı z
        düzeyindeki yatay koşuda geri dönüşle olur; yatay koşuda r kesin
        monoton olmalı, sıfır boylu parça olmamalı;
      * H_iç > 0.

    Uçlar dışında hiçbir nokta düzeltilmez, eklenmez, atılmaz.
    """
    try:
        p = np.asarray(profil, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ProfilHatasi(f'profil sayıya çevrilemedi: {exc}',
                           okuma_kodu='TUR_HATASI',
                           ayrinti='profil_sayi_degil') from None
    if p.ndim != 2 or p.shape[1] != 2:
        raise ProfilHatasi('profil (K, 2) biçiminde [r, z] çiftleri olmalı',
                           okuma_kodu='TUR_HATASI', ayrinti='profil_bicimi')
    k = p.shape[0]
    if k > PROFIL_NOKTA_SINIRI:
        raise ProfilHatasi(
            f'profil {k} nokta; sınır {PROFIL_NOKTA_SINIRI}',
            okuma_kodu='BOYUT_SINIRI', ayrinti='profil_nokta_siniri',
            parametreler={'nokta': int(k), 'sinir': PROFIL_NOKTA_SINIRI})
    if k < 3:
        raise ProfilHatasi('profil en az 3 nokta olmalı',
                           okuma_kodu='DEGER_GECERSIZ', ayrinti='profil_az_nokta',
                           parametreler={'nokta': int(k)})
    if not np.all(np.isfinite(p)):
        raise ProfilHatasi('profilde sonlu olmayan sayı var',
                           okuma_kodu='DEGER_GECERSIZ', ayrinti='sonlu_olmayan')
    r, z = p[:, 0], p[:, 1]
    if np.any(r < 0.0):
        i = int(np.argmax(r < 0.0))
        raise ProfilHatasi('profilde negatif yarıçap',
                           okuma_kodu='DEGER_GECERSIZ', ayrinti='negatif_yaricap',
                           parametreler={'satir': i})
    H = float(z[-1] - z[0])
    R_ref = float(r.max())
    if not (H > 0.0 and R_ref > 0.0):
        raise ProfilHatasi('profilin yüksekliği ya da yarıçapı sıfır',
                           okuma_kodu='DEGER_GECERSIZ', ayrinti='boyut_sifir',
                           parametreler={'H_m': H, 'R_ref_m': R_ref})
    if r[0] != 0.0 or r[-1] != 0.0:
        uc = 'alt' if r[0] != 0.0 else 'ust'
        raise ProfilHatasi('profil eksende başlayıp eksende bitmeli',
                           sebep='YUZEY_KAPALI_DEGIL', ayrinti='bas_kapanmiyor',
                           parametreler={'uc': uc})
    dz = np.diff(z)
    if np.any(dz < 0.0):
        i = int(np.argmax(dz < 0.0))
        raise ProfilHatasi('profilde z azalıyor (aynı z düzeyinde iki iç '
                           'yüzey)', sebep='PROFIL_TEK_DEGERLI_DEGIL',
                           ayrinti='z_monoton_degil',
                           parametreler={'satir': i + 1, 'z_m': float(z[i + 1])})
    if np.any(r[1:-1] == 0.0):
        i = 1 + int(np.argmax(r[1:-1] == 0.0))
        raise ProfilHatasi('profilin iç düğümü eksende',
                           sebep='PROFIL_TEK_DEGERLI_DEGIL',
                           ayrinti='ic_dugum_eksende',
                           parametreler={'satir': i, 'z_m': float(z[i])})
    dr = np.diff(r)
    yatay = dz == 0.0
    if np.any(yatay & (dr == 0.0)):
        i = int(np.argmax(yatay & (dr == 0.0)))
        raise ProfilHatasi('profilde sıfır boylu parça (yinelenen nokta)',
                           sebep='PROFIL_TEK_DEGERLI_DEGIL',
                           ayrinti='kendini_kesiyor',
                           parametreler={'satir': i + 1, 'z_m': float(z[i])})
    # Aynı yatay koşuda (ardışık dz == 0 parçaları) dr işareti değişirse
    # çizgi kendi üstüne geri döner.
    isaret = np.sign(dr)
    for i in range(1, len(dz)):
        if yatay[i] and yatay[i - 1] and isaret[i] != isaret[i - 1]:
            raise ProfilHatasi('profil yatay koşuda geri dönüyor (kendini '
                               'kesiyor)', sebep='PROFIL_TEK_DEGERLI_DEGIL',
                               ayrinti='kendini_kesiyor',
                               parametreler={'satir': i + 1,
                                             'z_m': float(z[i])})
    return p.copy()


# ---------------------------------------------------------------------------
# Parça integralleri
# ---------------------------------------------------------------------------
def _parca_karesi(r_a, z_a, r_b, z_b, z_ust):
    """[z_a, min(z_b, z_ust)] aralığında Gauss düğümleri, ağırlıkları ve r.

    Diziler parça boyuncadır (vektörel). Yatay parça (dz = 0) ve aralık
    dışı parça sıfır ağırlık alır.
    """
    dz = z_b - z_a
    z_e = np.minimum(z_b, z_ust)
    gecerli = (dz > 0.0) & (z_e > z_a)
    yarim = np.where(gecerli, 0.5 * (z_e - z_a), 0.0)
    orta = 0.5 * (z_e + z_a)
    zg = orta[:, None] + yarim[:, None] * GAUSS_DUGUMLERI[None, :]
    egim = np.where(dz > 0.0, (r_b - r_a) / np.where(dz > 0.0, dz, 1.0), 0.0)
    rg = r_a[:, None] + egim[:, None] * (zg - z_a[:, None])
    wg = yarim[:, None] * GAUSS_AGIRLIKLARI[None, :]
    return zg, rg, wg


def kesit_yaricapi(profil, h):
    """r(h): h yüksekliğindeki iç kesit yarıçapı (aşağıdan sınır)."""
    p = np.asarray(profil, dtype=float)
    r, z = p[:, 0], p[:, 1]
    dz = np.diff(z)
    adaylar = np.nonzero((dz > 0.0) & (z[:-1] < h) & (h <= z[1:]))[0]
    if adaylar.size == 0:
        raise ValueError(f'h = {h!r} profilin (0, H] aralığında değil')
    j = int(adaylar[-1])
    t = (h - z[j]) / dz[j]
    return float(r[j] + t * (r[j + 1] - r[j]))


def kesit_ozellikleri(profil, rho_kg_m3, h_m):
    """Verilen h için sıvı kütle özellikleri (donmuş sıvı)."""
    p = profil_dogrula(profil)
    rho = _sayi_kapisi(rho_kg_m3, 'rho_kg_m3', pozitif=True)
    h = _sayi_kapisi(h_m, 'h_m', pozitif=True)
    r, z = p[:, 0], p[:, 1]
    H = float(z[-1] - z[0])
    if z[0] != 0.0:
        raise ValueError('profil tank çerçevesinde değil: en alt nokta z = 0 '
                         'olmalı (sözleşme §F.1)')
    if h > H:
        raise ValueError(f'h = {h!r} > H_iç = {H!r}')
    zg, rg, wg = _parca_karesi(r[:-1], z[:-1], r[1:], z[1:], h)
    alan = math.pi * rg * rg
    V = float(np.sum(wg * alan))
    if not V > 0.0:
        raise ValueError(f'h = {h!r} yüksekliğinde sıvı hacmi sıfır')
    z_km = float(np.sum(wg * alan * zg)) / V
    I_km = rho * float(np.sum(wg * alan * (0.25 * rg * rg
                                            + (zg - z_km) ** 2)))
    I_eks = rho * float(np.sum(wg * alan * 0.5 * rg * rg))
    R_yuzey = kesit_yaricapi(p, h)
    return {
        'h_m': h,
        'V_sivi_m3': V,
        'm_sivi_kg': rho * V,
        'z_km_m': z_km,
        'I_km_donmus_kgm2': I_km,
        'I_eksenel_donmus_kgm2': I_eks,
        'A_yuzey_m2': math.pi * R_yuzey * R_yuzey,
        'R_yuzey_m': R_yuzey,
    }


def _birikimli_hacim(p):
    """Düğümlerdeki birikimli hacim V(z_k) (k = 0..K-1)."""
    r, z = p[:, 0], p[:, 1]
    zg, rg, wg = _parca_karesi(r[:-1], z[:-1], r[1:], z[1:], z[-1])
    parca = np.sum(wg * math.pi * rg * rg, axis=1)
    return np.concatenate(([0.0], np.cumsum(parca)))


def ic_hacim(profil):
    """V_iç: profilin eksen etrafında döndürülmesiyle elde edilen hacim."""
    p = profil_dogrula(profil)
    return float(_birikimli_hacim(p)[-1])


def doluluk_yuksekligi(profil, doluluk):
    """V(h) = doluluk · V_iç denkleminin kökü h [m] (ikiye bölme)."""
    p = profil_dogrula(profil)
    f = _sayi_kapisi(doluluk, 'doluluk')
    if not 0.0 < f < 1.0:
        raise ValueError(f'doluluk (0, 1) aralığında olmalı ({f!r})')
    return _kok(p, _birikimli_hacim(p), f)


def _kok(p, birikimli, f):
    r, z = p[:, 0], p[:, 1]
    V_ic = float(birikimli[-1])
    hedef = f * V_ic
    tol = DOLULUK_KOK_BAGIL_TOL * V_ic
    # Hedefi içeren ilk hacimli parça: birikimli[j] < hedef ≤ birikimli[j+1]
    j = int(np.searchsorted(birikimli, hedef, side='left')) - 1
    j = min(max(j, 0), len(z) - 2)
    while z[j + 1] - z[j] <= 0.0:       # yatay parça hacim taşımaz
        j += 1
    ra, za, rb, zb = r[j:j + 1], z[j:j + 1], r[j + 1:j + 2], z[j + 1:j + 2]
    taban = float(birikimli[j])

    def V(zz):
        zg, rg, wg = _parca_karesi(ra, za, rb, zb, zz)
        return taban + float(np.sum(wg * math.pi * rg * rg))

    lo, hi = float(za[0]), float(zb[0])
    for _ in range(DOLULUK_KOK_ADIM_SINIRI):
        orta = 0.5 * (lo + hi)
        v = V(orta)
        if abs(v - hedef) <= tol:
            return orta
        if v < hedef:
            lo = orta
        else:
            hi = orta
        if hi - lo <= 0.0:
            break
    orta = 0.5 * (lo + hi)
    if abs(V(orta) - hedef) <= tol:
        return orta
    raise ArithmeticError(
        f'doluluk {f!r} için h kökü {DOLULUK_KOK_ADIM_SINIRI} adımda '
        f'{DOLULUK_KOK_BAGIL_TOL:g} V_iç toleransına inmedi')


def kutle_ozellikleri(profil, rho_kg_m3, doluluklar):
    """Doluluk listesi için sıvı kütle özellikleri tablosu.

    Döndürür: ``{'geometri': {'R_ref_m', 'H_ic_m', 'V_ic_m3'},
    'satirlar': [{'doluluk', 'h_m', 'V_sivi_m3', 'm_sivi_kg', 'z_km_m',
    'I_km_donmus_kgm2', 'I_eksenel_donmus_kgm2', 'A_yuzey_m2',
    'R_yuzey_m'}, ...]}``. Alan adları sözleşmenin
    ``slosh_tablo.SATIR_GEOMETRI`` sütunlarıdır.
    """
    p = profil_dogrula(profil)
    rho = _sayi_kapisi(rho_kg_m3, 'rho_kg_m3', pozitif=True)
    if p[0, 1] != 0.0:
        raise ValueError('profil tank çerçevesinde değil: en alt nokta z = 0 '
                         'olmalı (sözleşme §F.1)')
    if isinstance(doluluklar, (str, bytes)) or not hasattr(doluluklar,
                                                          '__iter__'):
        raise ValueError('doluluklar bir sayı listesi olmalı')
    dl = [_sayi_kapisi(d, 'doluluk') for d in doluluklar]
    if not dl:
        raise ValueError('doluluk listesi boş')
    for d in dl:
        if not 0.0 < d < 1.0:
            raise ValueError(f'doluluk (0, 1) aralığında olmalı ({d!r})')
    birikimli = _birikimli_hacim(p)
    satirlar = []
    for d in dl:
        h = _kok(p, birikimli, d)
        satir = {'doluluk': d}
        satir.update(kesit_ozellikleri(p, rho, h))
        satirlar.append(satir)
    return {
        'geometri': {'R_ref_m': float(p[:, 0].max()),
                     'H_ic_m': float(p[-1, 1] - p[0, 1]),
                     'V_ic_m3': float(birikimli[-1])},
        'satirlar': satirlar,
    }


def kutle_ozellikleri_tablosu(profil, rho_kg_m3):
    """Sözleşmenin 29 noktalı doluluk ızgarasında kütle özellikleri."""
    return kutle_ozellikleri(profil, rho_kg_m3, DOLULUK_IZGARASI)
