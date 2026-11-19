"""3.0.7 TANK-GEOMETRİ — eksenel simetrik tankta sayısal çalkantı (TANK §D).

Tasarım: ``docs/tasarim/v307/TANK_GEOMETRI_TASARIM.md`` §D (problem,
ayrık denklemler, ağ, doluluk süpürmesi, yakınsama), §E (doğrulama), §F
(sözleşme; tek uygulaması ``hrma.analysis.slosh_tablo``). Kulvar K3b
(KARTLAR K3 kalemleri 5–7). Girdi profili K3a'nın içe aktarıcısından
(``hrma.importers.tank_geometry_import``) ya da kullanıcının (r, z)
profilinden gelir; kütle özellikleri ``hrma.analysis.tank_mass_properties``
ile hesaplanır. Bu modül alan adı, ızgara ya da sebep kodu TANIMLAMAZ;
hepsini sözleşmeden içe aktarır.

Problem (TANK §D.1)
-------------------
Doğrusal potansiyel akış, yüksek Bond sayısı. Yanal çalkantıda yalnız
cos θ modları net kuvvet/moment üretir (Dodge 2000 Bölüm 3 Ek, basılı
s. 61), φ = Φ(r, z) cos θ. Varyasyon ilkesi Dodge 2000 Ek Denk. (A.1)
(Lawrence, Wang, Reddy 1958):

    I(Φ) = ∬_Ω {Φ_r² + (Φ/r)² + Φ_z²} r dr dz − κ ∫_{Γ_f} Φ² r dr,
    κ = ω²/g_eff.

Islak çeper ve tabanda koşul doğal (Neumann sıfır); eksende Φ = 0 (m = 1
düzenliliği, Φ²/r² teriminin sonlu kalması). Serbest yüzeyde
∂Φ/∂z = κ Φ.

Ayrıklaştırma (TANK §D.2)
-------------------------
P2 (6 düğümlü) eş parametrik üçgen. Hacim karelemesi Dunavant (1985)
6 noktalı, derece 4 kural (Gauss noktaları eleman içinde, r > 0); yüzey
kenarı 3 noktalı Gauss–Legendre (Abramowitz & Stegun Tablo 25.4, n = 3;
``tank_mass_properties`` sabitleri). Serbest yüzey düğümlerine
yoğunlaştırma:

    S = K_ff − K_fi K_ii⁻¹ K_if,   S Φ_f = κ M_ff Φ_f   (scipy.linalg.eigh)

Eşdeğer mekanik model çıkarımı CALKANTI §A.1.4 Denk. (A-7)–(A-10),
meridyen biçimi (TANK §D.2):

    P = π ∫_{Γ_f} Φ r² dr,   N = π ∫_{Γ_f} Φ² r dr,
    G = π ∬ [z′(Φ_r + Φ/r) − r Φ_z] r dr dz,   z′ = z − h,
    m_n = ρ κ_n P_n²/N_n,  L_n = 1/κ_n,  z_n = h + G_n/(κ_n P_n),
    z_aski = z_n + L_n,   Γ_n = N_n/(κ_n P_n Φ_n(R_yüzey, h)),
    m0 = m_sıvı − m1,     z0 KM koşulundan (Dodge 2000 Denk. (3.2)).

Bütün çıkarılan büyüklükler modun işaretinden bağımsızdır (P ve G, P ve
Φ birlikte işaret değiştirir).

Ağ (TANK §D.3, tasarım düzeltmesi §D.3.1)
----------------------------------------
Sıvı bölgesi meridyen düzleminde dört kenarlı bir bölge sayılır: A eksenin
tabanı (0, 0), D ıslak çeper üzerinde bir nokta, C çeper–yüzey köşesi
(R_yüzey, h), B yüzey–eksen köşesi (0, h). Kenarlar: AD ve DC çeper (yay
uzunluğuyla parametreli çoklu çizgi), CB serbest yüzey, BA eksen. Birim
kareden bölgeye eşleme sonlu aralıklı aktarım (transfinite interpolation,
Gordon & Hall 1973). Serbest yüzeye doğru geometrik inceltme, oran
``SE_BUYUME_ORANI`` (TANK §D.3). P2 düğümleri eşlemenin yarım adımlarındaki
görüntüsüdür; çeper düğümleri (orta düğümler dahil) tam olarak profil
çoklu çizgisinin üstündedir. Kutup eleman üretmez: eksen bir kenardır
(A ve B köşe), üçgen çökmez. D seçimi: ıslak çeperde dönüş açısı
``SE_KOSE_DONUS_ESIGI_RAD`` üstündeki en keskin köşe (düz taban ⟷ çeper
köşesi ağ düğümü olur), yoksa ağ kalitesini en büyükleyen yay oranı.

Yakınsama (TANK §D.5)
---------------------
Üç düzey: (n_r, n_z), (2 n_r, 2 n_z), (4 n_r, 4 n_z); eşleme fonksiyonu üç
düzeyde aynıdır, yani parametre ızgaraları iç içedir. Gözlenen mertebe
p = log₂(|q₁ − q₂|/|q₂ − q₃|), Richardson q* ve hata |q₃ − q*|; tabloya en
ince düzeyin çözümü (q₃) yazılır, tani alanları satırın ``ek``
sözlüğündedir. Kabul ölçütü sağlanmazsa satır BEYANLI,
``AG_YAKINSAMA_ZAYIF``.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, field

import numpy as np
import scipy.linalg
import scipy.sparse
import scipy.sparse.linalg

from hrma.analysis import slosh_tablo as _tablo
from hrma.analysis.tank_mass_properties import (
    GAUSS_AGIRLIKLARI,
    GAUSS_DUGUMLERI,
    ProfilHatasi,
    kesit_yaricapi,
    kutle_ozellikleri_tablosu,
    profil_dogrula,
)
from hrma.fea.mesh_axisym import polyline_donus_acilari

# ---------------------------------------------------------------------------
# Sabitler (TEK YER). Kaynaklı ya da "HRMA seçimi" beyanlı.
# ---------------------------------------------------------------------------
#: Varsayılan ağ yoğunluğu (n_r, n_z): ξ (yüzey/taban yönü) ve η (eksen/
#: çeper yönü) hücre sayısı. TANK §D.5 "Varsayılan (8, 16)".
SE_VARSAYILAN_NR = 8
SE_VARSAYILAN_NZ = 16
#: Serbest yüzeye doğru geometrik inceltme: temel düzeyde ardışık iki
#: hücrenin boy oranı. TANK §D.3 (oran 1,15; mod e^{κ z′} ile yüzeyde
#: yoğunlaşır). HRMA seçimi.
SE_BUYUME_ORANI = 1.15
#: Yakınsama düzey sayısı ve inceltme katı (TANK §D.5).
SE_AG_DUZEY_SAYISI = 3
SE_INCELTME_KATI = 2
#: Kabul: κ1 ve m1 için bağıl hata, z1 için R_ref'e göre mutlak hata.
#: TANK §D.5 (HRMA seçimi; kaynakların kendi dağılımının en az 10 kat
#: altı).
SE_YAKINSAMA_BAGIL_TOL = 1e-3
SE_YAKINSAMA_Z_TOL_ORANI = 1e-3
#: Gözlenen mertebe bunun altındaysa BEYAN (TANK §D.5).
SE_MERTEBE_BEYAN_ESIGI = 1.5
#: Mertebe sınamasının çözünürlük alt sınırı (tasarım düzeltmesi, TANK
#: §D.5.1): üç düzey arasındaki farkların büyüğü kabul toleransının bu
#: katından küçükse mertebe sınanmaz; çözüm toleransın en az 10 kat
#: altında yakınsamış sayılır, hata kestirimi farkların büyüğüdür.
#: Gerekçe (ölçüldü, küre h/R = 0,05–1,8): 256 parçalı çokgen profilde
#: farklar 10⁻⁶–3,5·10⁻⁵ düzeyinde işaret değiştiriyor (çeper düğümleri
#: çokgen kırıklarına rastgele düşüyor); 8192 parçada aynı satırlar
#: 3,7–3,9 mertebesiyle yakınsıyor. m1 = κP²/N'deki ters işaretli hata
#: terimleri de kesişebilir (küre h/R = 1, 8192 parça, 4·10⁻⁷). HRMA
#: seçimi.
SE_MERTEBE_SINAMA_ALT_ORANI = 1e-1
#: Düzeyler arası fark bu değerin (büyüklüğün ölçeğine göre bağıl) altında
#: kalırsa fark yuvarlama düzeyindedir: mertebe tanimsız, çözüm yakınsamış
#: sayılır. Yoğunlaştırılmış özdeğer çözümünün ölçülen tekrarlanabilirliği
#: ~10⁻¹³ (aynı ağda iki çözüm); pay 100 kat. HRMA seçimi.
SE_YUVARLAMA_TABANI = 1e-11
#: Islak çeperde bu dönüş açısını aşan profil düğümü "köşe" sayılır ve
#: eşlemenin D köşesi olur (düz taban ⟷ dik çeper 90°). HRMA seçimi:
#: K3a'nın nokta bulutundan kurduğu pürüzsüz profillerde düğüm başına
#: dönüş ≤ π/40 = 4,5° (40 meridyen kutusu), keskin köşede ölçülen ~84°.
SE_KOSE_DONUS_ESIGI_RAD = math.radians(30.0)
#: Köşe yoksa D için denenen çeper yay uzunluğu oranları. HRMA seçimi.
SE_D_ADAY_ORANLARI = (0.3, 0.4, 0.5, 0.6, 0.7)
#: Dörtgen hücre en büyük iç açısı bunu aşarsa köşegen o köşeden geçer
#: (yaklaşık 180° açılı köşe yassı üçgen üretmesin). HRMA seçimi.
SE_KOSEGEN_ACI_ESIGI_RAD = math.radians(120.0)
#: Saldırgan girdi kapısı: temel düzey hücre sayısı aralıkları. En ince
#: düzey 4 kat; (32, 64) temelde en ince ağ 257 × 513 düğüm. HRMA seçimi.
SE_NR_ARALIGI = (2, 32)
SE_NZ_ARALIGI = (2, 64)
#: Islak çeper bir küre parçasıysa I0 = 0 (Dodge 2000 basılı s. 48:
#: kürenin kendi merkezi etrafında dönmesi ideal sıvıyı hareket ettirmez;
#: sabit kütle ve askı noktası merkezde). Küre tanima toleransı: çeper
#: düğümlerinin uydurulan küreye uzaklığı ≤ bu oran × R_ref. HRMA seçimi.
SE_KURE_TANIMA_BAGIL_TOL = 1e-6

I0_KAYNAK_KURE = ('Dodge 2000 basılı s. 48: küresel çeperde I0 = 0 (kürenin '
                  'merkezi etrafında dönmesi ideal sıvıyı hareket ettirmez)')
I0_KAYNAK_HESAPLANMADI = ('hesaplanmadı: dönme (Stokes–Zhukovsky) potansiyeli '
                          '3.0.7 sayısal çözümünde yok (TANK §D.2)')

# ---------------------------------------------------------------------------
# Kubbe sapması BEYANI (KARTLAR K3 kalem 7; CALKANTI §A.1.3 boşluğu).
# Kubbeli silindirde serbest yüzey silindirik bölgedeyken K1'in silindir
# kapalı biçimi eşdeğer derinlik h_eş = V/(πR²) ile kullanılır
# (``TANK_BASLARI_MODELLENMEDI``). Sapma bu modülün SE çözümüne göre
# ölçüldü: ``docs/scofield/raw/OH/V307/tank-se/kubbe_sapmasi.py`` (.json,
# .md). Ölçüm kümesi: yarım küre ve 2:1 elips başlı silindir, silindir boyu
# L/R = 1, 2, 4, sözleşme doluluk ızgarası, yüzey silindir bölgesinde (80
# satır). Fark = kapalı biçim − SE; konumlar serbest yüzeye göre.
# Ölçülen en büyük (yukarı yuvarlandı):
#   yarım küre başta f1 %0,29 → 0,3; m1 %0,86 → 0,9; z1 0,044 R → 0,045;
#     askı 0,048 R → 0,05;
#   2:1 elips başta f1 %3,41 → 3,5; m1 %7,24 → 7,3; z1 0,0445 R → 0,045;
#     askı 0,109 R → 0,11;
#   yüzey alt başın birleşim çizgisinden ≥ 1 R yukarıdayken (iki baş): f1
#     %0,089 → 0,1; m1 %0,18 → 0,2; z1 0,0112 R → 0,012; askı 0,0122 R →
#     0,013.
# En büyük fark yüzeyin alt başın hemen üstünde olduğu satırdadır.
#
# TASARIM DÜZELTMESİ (V307/K6, 4 Kas; ölçüm
# ``docs/scofield/raw/OH/V307/birlesik-giris/kubbe_sapmasi_birlesim.py``,
# .json): yukarıdaki ölçüm bölge kuralında baş hacmini ANALİTİK yarım
# elipsoidden aldı; ürünün kuralı (tek giriş, ``slosh_analysis.
# _silindir_bolumu`` + ``kubbe_bolgesi_degerlendir``) gerçek (çokgen)
# profilden alır. Çokgen başın hacmi küçük olduğundan yüzeyin TAM birleşim
# çizgisinde olduğu satır (2:1 elips L/R = 1 doluluk 0,10; yarım küre
# L/R = 2 doluluk 0,20) üründe "silindir bölgesi" (BEYANLI) sayılır ve
# sapma orada en büyüktür: sapma yüzey birleşim çizgisine indikçe artar,
# üst sınırı birleşim çizgisindeki değerdir (sıvı yalnız alt baştadır,
# L/R'den bağımsız). Ölçülen (birleşim çizgisi + ürün tablosunun bütün
# BEYANLI satırları, L/R = 1, 2, 4), 2 anlamlı basamağa yukarı:
#   yarım küre: f1 %0,3265 → 0,33; m1 %0,9930 → 1,0; z1 0,04706 R → 0,048;
#     askı 0,05126 R → 0,052;
#   2:1 elips: f1 %3,6341 → 3,7; m1 %7,7273 → 7,8; z1 0,04575 R → 0,046;
#     askı 0,11664 R → 0,12;
#   yüzey ≥ 1 R üstte: f1 %0,0892, m1 %0,179, z1 0,01124 R, askı
#     0,01222 R — eski beyan (0,1 / 0,2 / 0,012 / 0,013) geçerli.
# Konum sınırları baş biçimine göre ayrı yazılır (eski metin elips
# değerini iki baş için söylüyordu; yarım küre z1 0,047 R > 0,046 R).
# Ölçüm kümesi dışındaki baş biçimleri (torisferik, daha basık elips) için
# sapma ölçülmedi; metin bunu açıkça söyler. Metin anahtarı ve İngilizce
# yedek burada; TR karşılığı ve arayüz K5'in, kodun kullanımı K1'in.
# ---------------------------------------------------------------------------
TANK_BASLARI_BEYANI = {
    'kod': 'TANK_BASLARI_MODELLENMEDI',
    'anahtar': 'slosh.beyan.tank_baslari_modellenmedi',
    'parametreler': {
        'yarim_kure_f1_yuzde': 0.33, 'yarim_kure_m1_yuzde': 1.0,
        'yarim_kure_z1_R': 0.048, 'yarim_kure_aski_R': 0.052,
        'elips21_f1_yuzde': 3.7, 'elips21_m1_yuzde': 7.8,
        'elips21_z1_R': 0.046, 'elips21_aski_R': 0.12,
        'derin_f1_yuzde': 0.1, 'derin_m1_yuzde': 0.2,
        'derin_z1_R': 0.012, 'derin_aski_R': 0.013,
    },
    'en': ('Tank heads are not modelled: the cylinder formula is used with '
           'the equivalent depth V/(pi R^2). Compared with the numerical '
           'solution of the actual tank (free surface in the cylindrical '
           'section, cylinder length 1 to 4 R), the frequency differs by up '
           'to {yarim_kure_f1_yuzde} % and the slosh mass by up to '
           '{yarim_kure_m1_yuzde} % for hemispherical heads, and by up to '
           '{elips21_f1_yuzde} % and {elips21_m1_yuzde} % for 2:1 elliptical '
           'heads; the slosh-mass position differs by up to '
           '{yarim_kure_z1_R} R and {elips21_z1_R} R and the pendulum hinge '
           'by up to {yarim_kure_aski_R} R and {elips21_aski_R} R, '
           'respectively. The largest differences occur with the free '
           'surface at the bottom head junction; with the surface at least '
           '1 R above it they are below {derin_f1_yuzde} % (frequency) and '
           '{derin_m1_yuzde} % (slosh mass). Other head shapes were not '
           'measured.'),
    'olcum': 'docs/scofield/raw/OH/V307/birlesik-giris/'
             'kubbe_sapmasi_birlesim.json',
}

# Dunavant (1985), IJNME 21, 1129–1148, Tablo I, p = 4, ng = 6:
# ağırlıklar alana göre (toplam 1), noktalar barisentrik.
_DUNAVANT4_A = (0.445948490915965, 0.091576213509771)
_DUNAVANT4_W = (0.223381589678011, 0.109951743655322)


def _dunavant4():
    L, W = [], []
    for a, w in zip(_DUNAVANT4_A, _DUNAVANT4_W):
        b = 1.0 - 2.0 * a
        for p in ((b, a, a), (a, b, a), (a, a, b)):
            L.append(p)
            W.append(w)
    return np.array(L), np.array(W)


UCGEN_KARE_L, UCGEN_KARE_W = _dunavant4()


class SloshSEHatasi(ValueError):
    """Sayısal çalkantı çözümünün adlı reddi.

    ``kod``: ``PROFIL`` (profil kapısı; ``profil_hatasi`` özgün
    ``ProfilHatasi``), ``DEGER_GECERSIZ`` (girdi aralık dışı / sayı değil),
    ``AG_GECERSIZ`` (eşleme ters dönmüş eleman üretti; ``se_tablosu``'nda
    satır düzeyi RET ``AG_URETILEMEDI`` olur, v307-2), ``OZDEGER`` (özdeğer
    çözümü pozitif çalkantı modu vermedi).
    """

    def __init__(self, mesaj, kod, *, alan=None, profil_hatasi=None):
        super().__init__(mesaj)
        self.kod = kod
        self.alan = alan
        self.profil_hatasi = profil_hatasi


def _sayi(deger, ad, *, pozitif=False):
    if isinstance(deger, (bool, np.bool_)) or not isinstance(deger,
                                                            numbers.Real):
        raise SloshSEHatasi(f'{ad}: sayı bekleniyordu', 'DEGER_GECERSIZ',
                            alan=ad)
    f = float(deger)
    if not math.isfinite(f) or (pozitif and not f > 0.0):
        raise SloshSEHatasi(f'{ad}: pozitif sonlu sayı bekleniyordu ({f!r})',
                            'DEGER_GECERSIZ', alan=ad)
    return f


def _tamsayi(deger, ad, aralik):
    if isinstance(deger, (bool, np.bool_)) or not isinstance(
            deger, numbers.Integral):
        raise SloshSEHatasi(f'{ad}: tamsayı bekleniyordu', 'DEGER_GECERSIZ',
                            alan=ad)
    n = int(deger)
    if not aralik[0] <= n <= aralik[1]:
        raise SloshSEHatasi(f'{ad} = {n}; kabul aralığı {aralik}',
                            'DEGER_GECERSIZ', alan=ad)
    return n


def _profil(profil):
    try:
        p = profil_dogrula(profil)
    except ProfilHatasi as exc:
        raise SloshSEHatasi(f'profil reddedildi: {exc}', 'PROFIL',
                            alan='profil_rz_m', profil_hatasi=exc) from None
    if p[0, 1] != 0.0:
        raise SloshSEHatasi('profil tank çerçevesinde değil: en alt iç nokta '
                            'z = 0 olmalı (sözleşme §F.1)', 'DEGER_GECERSIZ',
                            alan='profil_rz_m')
    return p


# ---------------------------------------------------------------------------
# Islak çeper çoklu çizgisi
# ---------------------------------------------------------------------------
def islak_ceper(profil, h):
    """Tabandaki eksen noktası A = (0, 0)'dan çeper–yüzey köşesi
    C = (r(h), h)'ye kadar ıslak çeper çoklu çizgisi (K, 2) [r, z].

    r(h) ``tank_mass_properties.kesit_yaricapi`` ile (yatay parçada
    aşağıdan sınır). r(h) = 0 ise (üst kutup) serbest yüzey yoktur → ret.
    """
    p = np.asarray(profil, dtype=float)
    z = p[:, 1]
    H = float(z[-1])
    if not 0.0 < h <= H:
        raise SloshSEHatasi(f'h = {h!r}; (0, H_iç = {H!r}] aralığında olmalı',
                            'DEGER_GECERSIZ', alan='h_m')
    R_s = kesit_yaricapi(p, h)
    if not R_s > 0.0:
        raise SloshSEHatasi('h üst kapanışta: serbest yüzey yarıçapı sıfır',
                            'DEGER_GECERSIZ', alan='h_m')
    j = int(np.nonzero(z < h)[0][-1])        # son z < h düğümü
    ceper = np.vstack([p[:j + 1], [[R_s, h]]])
    # C, p[j]'nin kendisiyle çakışamaz (z[j] < h); ardışık özdeş nokta yok.
    return ceper


def _yay(ceper):
    d = np.hypot(np.diff(ceper[:, 0]), np.diff(ceper[:, 1]))
    return np.concatenate(([0.0], np.cumsum(d)))


def _ceper_noktasi(ceper, s_dugum, s):
    """Yay uzunluğu s'deki çeper noktaları (doğrusal parça içi)."""
    r = np.interp(s, s_dugum, ceper[:, 0])
    z = np.interp(s, s_dugum, ceper[:, 1])
    return r, z


# ---------------------------------------------------------------------------
# Ağ
# ---------------------------------------------------------------------------
@dataclass
class SiviAgi:
    """Meridyen düzleminde P2 sıvı ağı.

    ``dugum`` (N, 2) [r, z] m; ``eleman`` (M, 6) T6 bağlantısı (köşe 1-2-3
    saat yönünün tersine, sonra kenar orta düğümleri 1-2, 2-3, 3-1);
    ``eksen`` Φ = 0 düğümleri; ``yuzey`` serbest yüzey düğümleri r artan
    sırada (eksen düğümü dahil, ilk eleman); ``yuzey_kenar`` (k, 3) yüzey
    kenarları [uç, orta, uç]; ``kose_C`` çeper–yüzey köşesi düğümü.
    """

    dugum: np.ndarray
    eleman: np.ndarray
    eksen: np.ndarray
    yuzey: np.ndarray
    yuzey_kenar: np.ndarray
    kose_C: int
    h: float
    R_yuzey: float
    n_r: int
    n_z: int
    meta: dict = field(default_factory=dict)


def _eta_esleme(t, beta):
    """Serbest yüzeye (t = 1) doğru inceltilmiş η(t) = (1 − e^{−βt})/(1 − e^{−β})."""
    if beta <= 0.0:
        return np.asarray(t, dtype=float)
    return -np.expm1(-beta * t) / -math.expm1(-beta)


def _esleme_kur(s_dugum, koseler, s_D, n_r, n_z, beta):
    """Çeper kenarlarının parametre → yay uzunluğu eşlemesi (düğüm listesi).

    Alt kenar (A→D) ξ'de, sağ kenar (D→C) η = g(t)'de parça parça
    doğrusaldır. D dışındaki keskin köşeler (yay uzunluğu ``koseler``)
    TEMEL düzeyin en yakın ızgara düğümüne oturtulur; ızgaralar iç içe
    olduğundan bütün düzeylerde düğümdür. Aynı düğüme düşen ya da sırayı
    bozan köşe oturtulmaz (eğri kenarla kesilir; ``oturmayan`` sayısı).
    """
    S = float(s_dugum[-1])
    alt = [(0.0, 0.0)]
    sag = [(0.0, s_D)]
    oturmayan = 0
    g_taban = _eta_esleme(np.arange(n_z + 1) / n_z, beta)
    for s_c in sorted(koseler):
        if 0.0 < s_c < s_D:
            i = int(min(max(round(n_r * s_c / s_D), 1), n_r - 1))
            xi_c = i / n_r
            if xi_c > alt[-1][0] and s_c > alt[-1][1]:
                alt.append((xi_c, s_c))
            else:
                oturmayan += 1
        elif s_D < s_c < S:
            aday = s_D + g_taban[1:-1] * (S - s_D)
            k = 1 + int(np.argmin(np.abs(aday - s_c)))
            t_c = k / n_z
            if t_c > sag[-1][0] and s_c > sag[-1][1]:
                sag.append((t_c, s_c))
            else:
                oturmayan += 1
    alt.append((1.0, s_D))
    sag.append((1.0, S))
    return {'s_D': float(s_D), 'alt': tuple(alt), 'sag': tuple(sag),
            'oturmayan_kose': oturmayan}


def _tfi(ceper, s_dugum, esleme, R_s, h, xi, t, beta):
    """Birim kareden sıvı bölgesine sonlu aralıklı aktarım (Gordon–Hall).

    xi (n_a,), t (n_b,) düzgün parametreler; η = g(t) yüzeye doğru
    inceltilmiş. → r, z (n_b, n_a). Kenarlar tam olarak yerine oturtulur
    (eksen r = 0, yüzey z = h, çeper profil üstünde).
    """
    eta = _eta_esleme(t, beta)
    X, E = np.meshgrid(xi, eta)                        # (n_b, n_a)
    s_D = esleme['s_D']
    xa = np.array([k[0] for k in esleme['alt']])
    sa = np.array([k[1] for k in esleme['alt']])
    ga = _eta_esleme(np.array([k[0] for k in esleme['sag']]), beta)
    sg = np.array([k[1] for k in esleme['sag']])
    rb, zb = _ceper_noktasi(ceper, s_dugum, np.interp(xi, xa, sa))  # A→D
    rr, zr = _ceper_noktasi(ceper, s_dugum, np.interp(eta, ga, sg))  # D→C
    rt, zt = xi * R_s, np.full_like(xi, h)                       # üst: B→C
    rl, zl = np.zeros_like(eta), eta * h                         # sol: A→B
    rD, zD = _ceper_noktasi(ceper, s_dugum, np.array([s_D]))
    A = (0.0, 0.0)
    B = (0.0, h)
    C = (R_s, h)
    D = (float(rD[0]), float(zD[0]))

    def bilesen(b, t, l, rgt, k):
        return ((1 - E) * b[None, :] + E * t[None, :]
                + (1 - X) * l[:, None] + X * rgt[:, None]
                - ((1 - X) * (1 - E) * A[k] + X * (1 - E) * D[k]
                   + (1 - X) * E * B[k] + X * E * C[k]))

    r = bilesen(rb, rt, rl, rr, 0)
    z = bilesen(zb, zt, zl, zr, 1)
    # Kenarları kesin yerine koy (yuvarlama artığı kalmasın).
    r[:, 0] = 0.0
    z[:, 0] = zl
    r[-1, :] = rt
    z[-1, :] = h
    r[0, :] = rb
    z[0, :] = zb
    r[:, -1] = rr
    z[:, -1] = zr
    return r, z


def _hucre_acilari(r, z):
    """Köşe ızgarasındaki dörtgen hücrelerin dört iç açısı (n_b-1, n_a-1, 4)
    ve köşe ölçekli Jacobian'ı (işaretli sinüs)."""
    P = np.stack([r, z], axis=-1)
    k = [P[:-1, :-1], P[:-1, 1:], P[1:, 1:], P[1:, :-1]]   # SW SE NE NW (CCW)
    aci, sin = [], []
    for i in range(4):
        a = k[i - 1] - k[i]
        b = k[(i + 1) % 4] - k[i]
        cr = b[..., 0] * a[..., 1] - b[..., 1] * a[..., 0]
        dt = a[..., 0] * b[..., 0] + a[..., 1] * b[..., 1]
        n = np.hypot(a[..., 0], a[..., 1]) * np.hypot(b[..., 0], b[..., 1])
        aci.append(np.arctan2(cr, dt))
        sin.append(np.where(n > 0, cr / np.where(n > 0, n, 1.0), -1.0))
    return np.stack(aci, axis=-1), np.stack(sin, axis=-1)


def _ucgen_kalitesi(dugum, eleman):
    """Köşe (P1) üçgenlerinin en küçük köşe sinüsü 2A/(|e1||e2|) (işaretli;
    ≤ 0 ters dönmüş ya da dejenere üçgen)."""
    P = dugum[eleman[:, :3]]                       # (M, 3, 2)
    en_kucuk = np.inf
    for i in range(3):
        a = P[:, (i + 1) % 3] - P[:, i]
        b = P[:, (i + 2) % 3] - P[:, i]
        cr = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
        n = np.hypot(a[:, 0], a[:, 1]) * np.hypot(b[:, 0], b[:, 1])
        sin = np.where(n > 0, cr / np.where(n > 0, n, 1.0), -1.0)
        en_kucuk = min(en_kucuk, float(sin.min()))
    return en_kucuk


def _ag_kur(ceper, s_dugum, R_s, h, n_r, n_z, beta, esleme):
    """TFI düğümleri, hücre bölme, iç kenarların düzeltilmesi, kapılar."""
    na, nb = 2 * n_r + 1, 2 * n_z + 1
    xi = np.linspace(0.0, 1.0, na)
    r, z = _tfi(ceper, s_dugum, esleme, R_s, h, xi,
                np.linspace(0.0, 1.0, nb), beta)
    dugum = np.stack([r.ravel(), z.ravel()], axis=1)

    def no(a, b):
        return b * na + a

    aci, _ = _hucre_acilari(r[::2, ::2], z[::2, ::2])
    elemanlar = []
    for k in range(n_z):
        for i in range(n_r):
            a0, b0 = 2 * i, 2 * k
            SW, SE, NE, NW = (no(a0, b0), no(a0 + 2, b0),
                              no(a0 + 2, b0 + 2), no(a0, b0 + 2))
            mS, mE, mN, mW = (no(a0 + 1, b0), no(a0 + 2, b0 + 1),
                              no(a0 + 1, b0 + 2), no(a0, b0 + 1))
            M = no(a0 + 1, b0 + 1)
            ac = aci[k, i]
            j = int(np.argmax(ac))
            if ac[j] > SE_KOSEGEN_ACI_ESIGI_RAD and j in (1, 3):
                # SE–NW köşegeni (en büyük açı bu köşegenin ucunda)
                elemanlar.append((SW, SE, NW, mS, M, mW))
                elemanlar.append((SE, NE, NW, mE, mN, M))
            else:
                # SW–NE köşegeni (varsayılan)
                elemanlar.append((SW, SE, NE, mS, mE, M))
                elemanlar.append((SW, NE, NW, M, mN, mW))
    eleman = np.array(elemanlar, dtype=np.int64)
    kalite = _ucgen_kalitesi(dugum, eleman)
    if not kalite > 0.0:
        raise SloshSEHatasi('sıvı bölgesi eşlemesi ters dönmüş ya da dejenere '
                            f'üçgen üretti (h = {h!r} m)', 'AG_GECERSIZ',
                            alan='profil_rz_m')
    # Eğri kenar yalnız ıslak çeperde (orta düğüm profil üstünde). İç,
    # eksen ve yüzey kenarlarının orta düğümü kiriş ortasına konur
    # (alt-parametrik iç; çarpık hücrede merkez düğümün çeyrek nokta
    # konumuna kayıp Jacobian'ı sıfırlamasını önler).
    ceper_dugumu = np.zeros(dugum.shape[0], dtype=bool)
    ceper_dugumu[[no(a, 0) for a in range(na)]] = True
    ceper_dugumu[[no(na - 1, b) for b in range(nb)]] = True
    for (u, v, w) in ((0, 1, 3), (1, 2, 4), (2, 0, 5)):
        orta = eleman[:, w]
        duz = ~ceper_dugumu[orta]
        dugum[orta[duz]] = 0.5 * (dugum[eleman[duz, u]]
                                  + dugum[eleman[duz, v]])
    eksen = np.array([no(0, b) for b in range(nb)], dtype=np.int64)
    yuzey = np.array([no(a, nb - 1) for a in range(na)], dtype=np.int64)
    yuzey_kenar = np.array([[no(2 * i, nb - 1), no(2 * i + 1, nb - 1),
                             no(2 * i + 2, nb - 1)] for i in range(n_r)],
                           dtype=np.int64)
    ag = SiviAgi(dugum=dugum, eleman=eleman, eksen=eksen, yuzey=yuzey,
                 yuzey_kenar=yuzey_kenar, kose_C=int(no(na - 1, nb - 1)),
                 h=h, R_yuzey=R_s, n_r=n_r, n_z=n_z,
                 meta={'s_D_m': esleme['s_D'], 'beta': beta,
                       'oturmayan_kose': esleme['oturmayan_kose'],
                       'oturan_kose': len(esleme['alt']) + len(esleme['sag']) - 4,
                       'D_r_m': float(r[0, -1]), 'D_z_m': float(z[0, -1]),
                       'ucgen_kalitesi_min': kalite})
    _jacobian_kapisi(ag)
    return ag


def d_secimi(profil, h, n_r=SE_VARSAYILAN_NR, n_z=SE_VARSAYILAN_NZ,
             buyume=SE_BUYUME_ORANI):
    """Eşlemenin D köşesinin çeper yay uzunluğu ve seçim gerekçesi.

    Islak çeperde ``SE_KOSE_DONUS_ESIGI_RAD``'ı aşan en keskin köşe varsa
    ve ağı geçerliyse D odur; yoksa ``SE_D_ADAY_ORANLARI`` içinden üçgen
    kalitesini (en küçük köşe sinüsü) en büyükleyen yay oranı.
    """
    p = _profil(profil)
    ceper = islak_ceper(p, float(h))
    s_dugum = _yay(ceper)
    S = float(s_dugum[-1])
    R_s = float(ceper[-1, 0])
    beta = n_z * math.log(buyume)
    adaylar = []
    koseler = []
    if ceper.shape[0] >= 3:
        donus = polyline_donus_acilari(ceper)
        sira = np.argsort(-donus, kind='stable')
        koseler = [(float(s_dugum[i + 1]), float(donus[i])) for i in sira
                   if donus[i] >= SE_KOSE_DONUS_ESIGI_RAD]
        if koseler:
            adaylar.append(('kose', koseler[0][0], koseler[0][1]))
    for f in SE_D_ADAY_ORANLARI:
        adaylar.append(('oran', f * S, f))
    en_iyi = None
    for tur, s_D, deger in adaylar:
        esleme = _esleme_kur(s_dugum, [k[0] for k in koseler if k[0] != s_D],
                             s_D, n_r, n_z, beta)
        try:
            q = _ag_kur(ceper, s_dugum, R_s, float(h), n_r, n_z, beta,
                        esleme).meta['ucgen_kalitesi_min']
        except SloshSEHatasi as exc:
            if exc.kod != 'AG_GECERSIZ':
                raise
            continue
        aday = {'s_D': s_D, 'tur': tur, 'deger': deger, 'kalite': q,
                'esleme': esleme, 'kose_sayisi': len(koseler)}
        if tur == 'kose':
            return aday
        if en_iyi is None or q > en_iyi['kalite']:
            en_iyi = aday
    if en_iyi is None:
        raise SloshSEHatasi('sıvı bölgesi eşlemesi hiçbir D adayında geçerli '
                            f'ağ üretmedi (h = {h!r} m)', 'AG_GECERSIZ',
                            alan='profil_rz_m')
    return en_iyi


def build_liquid_mesh(profil, h, n_r=SE_VARSAYILAN_NR, n_z=SE_VARSAYILAN_NZ,
                      buyume=SE_BUYUME_ORANI, *, esleme=None, beta=None):
    """Doluluk yüksekliği h'ye kadar sıvı bölgesinin P2 ağı (TANK §D.3).

    ``buyume``: bu düzeyde ardışık hücre boy oranı. ``beta`` verilirse
    eşleme fonksiyonu doğrudan odur (yakınsama düzeyleri aynı β ile iç içe
    parametre ızgarası kullanır); verilmezse β = n_z ln(buyume).
    ``esleme``: çeper kenarlarının parametre eşlemesi (D köşesi ve
    oturtulan köşeler; verilmezse :func:`d_secimi`).
    """
    p = _profil(profil)
    h = _sayi(h, 'h_m', pozitif=True)
    n_r = _tamsayi(n_r, 'n_r', (SE_NR_ARALIGI[0],
                                SE_NR_ARALIGI[1] * SE_INCELTME_KATI
                                ** (SE_AG_DUZEY_SAYISI - 1)))
    n_z = _tamsayi(n_z, 'n_z', (SE_NZ_ARALIGI[0],
                                SE_NZ_ARALIGI[1] * SE_INCELTME_KATI
                                ** (SE_AG_DUZEY_SAYISI - 1)))
    buyume = _sayi(buyume, 'buyume', pozitif=True)
    if buyume < 1.0:
        raise SloshSEHatasi('buyume ≥ 1 olmalı (yüzeye doğru inceltme)',
                            'DEGER_GECERSIZ', alan='buyume')
    ceper = islak_ceper(p, h)
    s_dugum = _yay(ceper)
    R_s = float(ceper[-1, 0])
    if beta is None:
        beta = n_z * math.log(buyume)
    if esleme is None:
        esleme = d_secimi(p, h, n_r, n_z, math.exp(beta / n_z))['esleme']
    if not 0.0 < esleme['s_D'] < s_dugum[-1]:
        raise SloshSEHatasi('D köşesi çeperin içinde olmalı', 'DEGER_GECERSIZ',
                            alan='esleme')
    return _ag_kur(ceper, s_dugum, R_s, h, n_r, n_z, beta, esleme)


# ---------------------------------------------------------------------------
# P2 eş parametrik eleman
# ---------------------------------------------------------------------------
def _sekil(L):
    """T6 şekil fonksiyonları ve (ξ, η) türevleri; L (q, 3) barisentrik."""
    L1, L2, L3 = L[:, 0], L[:, 1], L[:, 2]
    N = np.stack([L1 * (2 * L1 - 1), L2 * (2 * L2 - 1), L3 * (2 * L3 - 1),
                  4 * L1 * L2, 4 * L2 * L3, 4 * L3 * L1], axis=1)
    # dL1 = (-1, -1), dL2 = (1, 0), dL3 = (0, 1)
    dxi = np.stack([-(4 * L1 - 1), 4 * L2 - 1, np.zeros_like(L1),
                    4 * (L1 - L2), 4 * L3, -4 * L3], axis=1)
    deta = np.stack([-(4 * L1 - 1), np.zeros_like(L1), 4 * L3 - 1,
                     -4 * L2, 4 * L2, 4 * (L1 - L3)], axis=1)
    return N, dxi, deta


_N_Q, _DXI_Q, _DETA_Q = _sekil(UCGEN_KARE_L)
_KOSE_L = np.array([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]])
_N_K, _DXI_K, _DETA_K = _sekil(_KOSE_L)


def _geometri(ag, dxi, deta, N):
    X = ag.dugum[ag.eleman]                         # (M, 6, 2)
    r_q = np.einsum('qa,ma->mq', N, X[:, :, 0])
    z_q = np.einsum('qa,ma->mq', N, X[:, :, 1])
    J11 = np.einsum('qa,ma->mq', dxi, X[:, :, 0])   # ∂r/∂ξ
    J12 = np.einsum('qa,ma->mq', dxi, X[:, :, 1])   # ∂z/∂ξ
    J21 = np.einsum('qa,ma->mq', deta, X[:, :, 0])  # ∂r/∂η
    J22 = np.einsum('qa,ma->mq', deta, X[:, :, 1])  # ∂z/∂η
    det = J11 * J22 - J12 * J21
    return r_q, z_q, J11, J12, J21, J22, det


def _jacobian_kapisi(ag):
    for dxi, deta, N in ((_DXI_Q, _DETA_Q, _N_Q), (_DXI_K, _DETA_K, _N_K)):
        r_q, _, _, _, _, _, det = _geometri(ag, dxi, deta, N)
        if not np.all(det > 0.0):
            raise SloshSEHatasi(
                f'{int(np.sum(np.any(det <= 0.0, axis=1)))} elemanda '
                'Jacobian ≤ 0', 'AG_GECERSIZ', alan='profil_rz_m')
    r_q = _geometri(ag, _DXI_Q, _DETA_Q, _N_Q)[0]
    if not np.all(r_q > 0.0):
        raise SloshSEHatasi('kareleme noktası eksende', 'AG_GECERSIZ',
                            alan='profil_rz_m')


def _birlestir(ag):
    """K (seyrek), G vektörü ve sıvı hacmi 2π∬ r dr dz."""
    r_q, z_q, J11, J12, J21, J22, det = _geometri(ag, _DXI_Q, _DETA_Q, _N_Q)
    # ∂N/∂r = ( J22 ∂N/∂ξ − J12 ∂N/∂η)/det ; ∂N/∂z = (−J21 ∂N/∂ξ + J11 ∂N/∂η)/det
    Nr = (J22[:, :, None] * _DXI_Q[None] - J12[:, :, None] * _DETA_Q[None]) \
        / det[:, :, None]
    Nz = (-J21[:, :, None] * _DXI_Q[None] + J11[:, :, None] * _DETA_Q[None]) \
        / det[:, :, None]
    w = 0.5 * UCGEN_KARE_W[None, :] * det           # alan ağırlığı (M, q)
    Nq = _N_Q[None, :, :]                           # (1, q, 6)
    rr = r_q[:, :, None, None]
    Ke = np.einsum('mq,mqab->mab', w,
                   (Nr[:, :, :, None] * Nr[:, :, None, :]
                    + Nz[:, :, :, None] * Nz[:, :, None, :]) * rr
                   + (Nq[:, :, :, None] * Nq[:, :, None, :]) / rr)
    E = ag.eleman
    satir = np.repeat(E, 6, axis=1).ravel()
    sutun = np.tile(E, (1, 6)).ravel()
    n = ag.dugum.shape[0]
    K = scipy.sparse.coo_matrix((Ke.ravel(), (satir, sutun)),
                                shape=(n, n)).tocsr()
    zp = z_q - ag.h
    ge = np.einsum('mq,mqa->ma', w * r_q,
                   zp[:, :, None] * (Nr + Nq / r_q[:, :, None])
                   - r_q[:, :, None] * Nz)
    g = math.pi * np.bincount(E.ravel(), weights=ge.ravel(), minlength=n)
    hacim = 2.0 * math.pi * float(np.sum(w * r_q))
    return K, g, hacim


def _yuzey_matrisleri(ag):
    """Serbest yüzeyde M_ab = ∫ N_a N_b r dr ve p_a = π ∫ N_a r² dr."""
    u = GAUSS_DUGUMLERI
    wu = GAUSS_AGIRLIKLARI
    N1 = np.stack([0.5 * u * (u - 1.0), 1.0 - u * u, 0.5 * u * (u + 1.0)],
                  axis=1)                           # (3q, 3)
    dN1 = np.stack([u - 0.5, -2.0 * u, u + 0.5], axis=1)
    yer = {int(d): i for i, d in enumerate(ag.yuzey)}
    m = len(ag.yuzey)
    M = np.zeros((m, m))
    pv = np.zeros(m)
    for ken in ag.yuzey_kenar:
        rk = ag.dugum[ken, 0]
        r_q = N1 @ rk
        jac = dN1 @ rk
        idx = [yer[int(d)] for d in ken]
        for q in range(len(u)):
            wq = wu[q] * jac[q]
            M[np.ix_(idx, idx)] += wq * r_q[q] * np.outer(N1[q], N1[q])
            pv[idx] += math.pi * wq * r_q[q] ** 2 * N1[q]
    return M, pv


# ---------------------------------------------------------------------------
# Özdeğer ve eşdeğer model çıkarımı
# ---------------------------------------------------------------------------
def coz(ag, n_mod=2):
    """Yoğunlaştırılmış genelleştirilmiş özdeğer problemi (TANK §D.2).

    Döner: ``{'kappa': (n_mod,), 'Phi': (n_mod, N), 'P', 'N', 'G',
    'Phi_C', 'hacim_m3'}``.
    """
    K, g, hacim = _birlestir(ag)
    M_s, p_s = _yuzey_matrisleri(ag)
    n = ag.dugum.shape[0]
    eksen = set(int(i) for i in ag.eksen)
    f = np.array([int(d) for d in ag.yuzey if int(d) not in eksen])
    f_yer = np.array([i for i, d in enumerate(ag.yuzey)
                      if int(d) not in eksen])
    serbest = np.ones(n, dtype=bool)
    serbest[list(eksen)] = False
    serbest[f] = False
    i_ = np.nonzero(serbest)[0]
    Kii = K[i_][:, i_].tocsc()
    Kif = K[i_][:, f].toarray()
    Kff = K[f][:, f].toarray()
    lu = scipy.sparse.linalg.splu(Kii)
    X = lu.solve(Kif)
    S = Kff - Kif.T @ X
    S = 0.5 * (S + S.T)
    Mff = M_s[np.ix_(f_yer, f_yer)]
    kappa, vec = scipy.linalg.eigh(S, Mff)
    if not (kappa.size >= n_mod and np.all(kappa[:n_mod] > 0.0)
            and np.all(np.isfinite(kappa[:n_mod]))):
        raise SloshSEHatasi('özdeğer çözümü pozitif çalkantı modu vermedi',
                            'OZDEGER')
    Phi = np.zeros((n_mod, n))
    P = np.zeros(n_mod)
    Nn = np.zeros(n_mod)
    G = np.zeros(n_mod)
    PhiC = np.zeros(n_mod)
    for k in range(n_mod):
        pf = vec[:, k]
        Phi[k, f] = pf
        Phi[k, i_] = -X @ pf
        P[k] = float(p_s[f_yer] @ pf)
        Nn[k] = math.pi * float(pf @ Mff @ pf)
        G[k] = float(g @ Phi[k])
        PhiC[k] = Phi[k, ag.kose_C]
    return {'kappa': kappa[:n_mod].copy(), 'Phi': Phi, 'P': P, 'N': Nn,
            'G': G, 'Phi_C': PhiC, 'hacim_m3': hacim,
            'n_serbestlik': int(n - len(eksen))}


def esdeger_model(cozum, h, V_sivi_m3):
    """(A-8)–(A-10): mod başına κ, m_n/m_sıvı, z_n, L_n, Γ_n."""
    out = []
    for k in range(len(cozum['kappa'])):
        kap = float(cozum['kappa'][k])
        P, N, G, PhiC = (float(cozum[a][k]) for a in ('P', 'N', 'G', 'Phi_C'))
        if P == 0.0 or N <= 0.0 or PhiC == 0.0:
            raise SloshSEHatasi('mod net yanal kuvvet üretmiyor (P = 0)',
                                'OZDEGER')
        out.append({'kappa_1m': kap,
                    'm_oran': kap * P * P / (N * V_sivi_m3),
                    'z_m': h + G / (kap * P),
                    'L_m': 1.0 / kap,
                    'Gamma': N / (kap * P * PhiC)})
    return out


def cozum_h(profil, h, V_sivi_m3, n_r=SE_VARSAYILAN_NR, n_z=SE_VARSAYILAN_NZ,
            buyume=SE_BUYUME_ORANI, *, esleme=None, beta=None):
    """Tek ağda h yüksekliği için iki modun eşdeğer modeli."""
    V = _sayi(V_sivi_m3, 'V_sivi_m3', pozitif=True)
    ag = build_liquid_mesh(profil, h, n_r, n_z, buyume, esleme=esleme,
                           beta=beta)
    c = coz(ag)
    modlar = esdeger_model(c, ag.h, V)
    return {'modlar': modlar, 'hacim_ag_m3': c['hacim_m3'],
            'n_serbestlik': c['n_serbestlik'], 'ag_meta': ag.meta}


# ---------------------------------------------------------------------------
# Yakınsama (TANK §D.5)
# ---------------------------------------------------------------------------
def gozlenen_mertebe(q1, q2, q3, olcek, tol):
    """Üç düzeyden mertebe, Richardson kestirimi, hata ve hüküm.

    ``olcek``: yuvarlama tabanının ölçeği; ``tol``: mutlak kabul sınırı.
    Döner ``{'p', 'q_star', 'hata', 'durum', 'kabul'}``; durum:
      * ``yuvarlama`` — son fark yuvarlama tabanında (mertebe tanımsız);
      * ``esik_alti`` — farkların büyüğü ≤ ``SE_MERTEBE_SINAMA_ALT_ORANI``
        × tol; mertebe sınanmaz, hata = farkların büyüğü;
      * ``yakinsadi`` — monoton, p ölçüldü, hata = |q₃ − q*|;
      * ``monoton_degil`` — farklar işaret değiştiriyor ya da büyüyor;
        hata = farkların büyüğü.
    ``kabul``: hata ≤ tol ve (durum yuvarlama/esik_alti ya da
    p ≥ ``SE_MERTEBE_BEYAN_ESIGI``).
    """
    d12, d23 = q1 - q2, q2 - q3
    fark = max(abs(d12), abs(d23))
    if abs(d23) <= SE_YUVARLAMA_TABANI * abs(olcek):
        return {'p': None, 'q_star': q3, 'hata': abs(d23),
                'durum': 'yuvarlama', 'kabul': True}
    if fark <= SE_MERTEBE_SINAMA_ALT_ORANI * tol:
        return {'p': None, 'q_star': None, 'hata': fark,
                'durum': 'esik_alti', 'kabul': True}
    if d12 * d23 > 0.0 and abs(d12) > abs(d23):
        p = math.log2(abs(d12) / abs(d23))
        q_star = q3 - d23 / (2.0 ** p - 1.0)
        hata = abs(q3 - q_star)
        return {'p': p, 'q_star': q_star, 'hata': hata, 'durum': 'yakinsadi',
                'kabul': hata <= tol and p >= SE_MERTEBE_BEYAN_ESIGI}
    return {'p': None, 'q_star': None, 'hata': fark,
            'durum': 'monoton_degil', 'kabul': False}


def yakinsama_cozumu(profil, h, V_sivi_m3, R_ref, n_r=SE_VARSAYILAN_NR,
                     n_z=SE_VARSAYILAN_NZ, buyume=SE_BUYUME_ORANI):
    """Üç düzeyde çözüm + yakınsama hükmü; tabloya en ince düzey yazılır."""
    p = _profil(profil)
    n_r = _tamsayi(n_r, 'n_r', SE_NR_ARALIGI)
    n_z = _tamsayi(n_z, 'n_z', SE_NZ_ARALIGI)
    buyume = _sayi(buyume, 'buyume', pozitif=True)
    R_ref = _sayi(R_ref, 'R_ref_m', pozitif=True)
    beta = n_z * math.log(buyume)
    D = d_secimi(p, h, n_r, n_z, buyume)
    duzeyler = []
    for ell in range(SE_AG_DUZEY_SAYISI):
        k = SE_INCELTME_KATI ** ell
        duzeyler.append(cozum_h(p, h, V_sivi_m3, n_r * k, n_z * k,
                                math.exp(beta / (n_z * k)), esleme=D['esleme'],
                                beta=beta))
    m = [d['modlar'][0] for d in duzeyler]
    tani = {}
    zayif = []
    for ad, anahtar, bagil in (('kappa1', 'kappa_1m', True),
                               ('m1', 'm_oran', True),
                               ('z1', 'z_m', False)):
        q = [x[anahtar] for x in m]
        if bagil:
            olcek = abs(q[2])
            tol = SE_YAKINSAMA_BAGIL_TOL * olcek
        else:
            olcek = R_ref
            tol = SE_YAKINSAMA_Z_TOL_ORANI * R_ref
        sonuc = gozlenen_mertebe(q[0], q[1], q[2], olcek, tol)
        tani[ad] = dict(sonuc, sinir=tol)
        if not sonuc['kabul']:
            if sonuc['hata'] > tol:
                zayif.append(f'{ad}:hata')
            elif sonuc['durum'] == 'monoton_degil':
                zayif.append(f'{ad}:monoton_degil')
            else:
                zayif.append(f'{ad}:mertebe')
    return {'duzeyler': duzeyler, 'ince': duzeyler[-1], 'yakinsama': tani,
            'zayif': zayif, 'D': D}


# ---------------------------------------------------------------------------
# I0 (TANK §D.2)
# ---------------------------------------------------------------------------
def islak_ceper_kure_mi(ceper, R_ref):
    """Islak çeper eksen üstünde merkezli bir kürenin parçası mı?

    Profil düğümleri (r, z) için r² + z² = 2 z_c z + c doğrusal en küçük
    kareler; en büyük |√(r² + (z − z_c)²) − R| ≤ tol·R_ref ise küre. Son
    nokta (serbest yüzeyde kesim noktası C) bir kirişin üstündedir, profil
    düğümü değildir; sınamaya girmez (çokgen sehimi 512 parçalı kürede
    4,7·10⁻⁶ R ölçüldü).
    """
    c = np.asarray(ceper, dtype=float)[:-1]
    if c.shape[0] < 4:
        return False
    A = np.stack([2.0 * c[:, 1], np.ones(c.shape[0])], axis=1)
    b = c[:, 0] ** 2 + c[:, 1] ** 2
    (z_c, cc), *_ = np.linalg.lstsq(A, b, rcond=None)
    R2 = cc + z_c * z_c
    if not R2 > 0.0:
        return False
    sapma = np.abs(np.hypot(c[:, 0], c[:, 1] - z_c) - math.sqrt(R2))
    return bool(sapma.max() <= SE_KURE_TANIMA_BAGIL_TOL * R_ref)


# ---------------------------------------------------------------------------
# Doluluk süpürmesi → sözleşme tablosu (TANK §D.4)
# ---------------------------------------------------------------------------
def _yuvarla_ek(d):
    return {k: (None if v is None else (float(v) if isinstance(
        v, (float, np.floating, int)) and not isinstance(v, bool) else v))
        for k, v in d.items()}


def se_satiri(p, kutle_satiri, geometri, rho, n_r=SE_VARSAYILAN_NR,
              n_z=SE_VARSAYILAN_NZ, buyume=SE_BUYUME_ORANI):
    """Kütle özellikleri satırına SE eşdeğer modelini ekler (sözlük)."""
    h = kutle_satiri['h_m']
    V = kutle_satiri['V_sivi_m3']
    R_ref = geometri['R_ref_m']
    yk = yakinsama_cozumu(p, h, V, R_ref, n_r, n_z, buyume)
    m1, m2 = yk['ince']['modlar']
    satir = dict(kutle_satiri)
    k1 = m1['kappa_1m']
    satir['kappa1_1m'] = k1
    satir['L1_m'] = 1.0 / k1
    satir['m1_oran'] = m1['m_oran']
    satir['z1_m'] = m1['z_m']
    satir['z_aski_m'] = m1['z_m'] + 1.0 / k1
    satir['m0_oran'] = 1.0 - m1['m_oran']
    satir['z0_m'] = ((kutle_satiri['z_km_m'] - m1['m_oran'] * m1['z_m'])
                     / (1.0 - m1['m_oran']))
    satir['Gamma1'] = m1['Gamma']
    satir['kappa2_1m'] = m2['kappa_1m']
    satir['m2_oran'] = m2['m_oran']
    satir['z2_m'] = m2['z_m']
    ceper = islak_ceper(p, h)
    if islak_ceper_kure_mi(ceper, R_ref):
        satir['I0_kgm2'] = 0.0
        satir['I0_kaynak'] = I0_KAYNAK_KURE
    else:
        satir['I0_kgm2'] = None
        satir['I0_kaynak'] = I0_KAYNAK_HESAPLANMADI
    sebep = ['AG_YAKINSAMA_ZAYIF'] if yk['zayif'] else []
    satir['sebep'] = sebep
    satir['durum'] = _tablo.durum_birlestir(sebep)
    y = yk['yakinsama']
    ince = yk['ince']
    ek = {
        'ag_nr_nz_temel': f'{n_r}x{n_z}',
        'ag_duzey': SE_AG_DUZEY_SAYISI,
        'ag_serbestlik_ince': ince['n_serbestlik'],
        'ag_hacim_bagil_fark': ince['hacim_ag_m3'] / V - 1.0,
        'D_secimi': yk['D']['tur'],
        'oturan_kose': ince['ag_meta']['oturan_kose'],
        'oturmayan_kose': ince['ag_meta']['oturmayan_kose'],
        'D_r_m': ince['ag_meta']['D_r_m'],
        'D_z_m': ince['ag_meta']['D_z_m'],
        'ucgen_kalitesi_min': ince['ag_meta']['ucgen_kalitesi_min'],
        'yakinsama_zayif': ','.join(yk['zayif']) if yk['zayif'] else None,
    }
    for ad in ('kappa1', 'm1', 'z1'):
        ek[f'p_{ad}'] = y[ad]['p']
        ek[f'hata_{ad}'] = y[ad]['hata']
        ek[f'q_star_{ad}'] = y[ad]['q_star']
        ek[f'yakinsama_{ad}'] = y[ad]['durum']
    satir['ek'] = _yuvarla_ek(ek)
    return satir


#: SE satırı kurulamadığında (``SloshSEHatasi`` kod ``AG_GECERSIZ``) satır
#: düzeyi sözleşme kodu (v307-2, K3b önerisi; K6). Öbür SE hataları (girdi,
#: profil, özdeğer) satıra indirgenmez, adlı istisna olarak yükselir.
SE_SATIR_RET_ESLEMESI = {'AG_GECERSIZ': 'AG_URETILEMEDI'}


def se_ret_satiri(kutle_satiri, hata):
    """Ağı kurulamayan doluluğun RET satırı (sözleşme v307-2).

    Geometri alanları kütle özelliklerinden (her satırda dolu, §F.2);
    model alanları ve I0 null; sebep ``SE_SATIR_RET_ESLEMESI``'nden; ``ek``
    SE hata kodunu ve iletisini taşır (tanı, sözleşme büyüklüğü değil).
    """
    kod = SE_SATIR_RET_ESLEMESI[hata.kod]
    satir = dict(kutle_satiri)
    for k in _tablo.SATIR_MODEL:
        satir[k] = None
    satir['I0_kgm2'] = None
    satir['I0_kaynak'] = None
    satir['sebep'] = [kod]
    satir['durum'] = _tablo.durum_birlestir([kod])
    satir['ek'] = {'se_hata_kodu': hata.kod,
                   'se_hata': str(hata)[:_tablo.METIN_BOY_SINIRI]}
    return satir


def se_tablosu(tank_id, profil, rho_kg_m3, sivi_adi, sigma_N_m=None,
               nu_m2_s=None, kaynak='kullanıcı girdisi',
               n_r=SE_VARSAYILAN_NR, n_z=SE_VARSAYILAN_NZ,
               buyume=SE_BUYUME_ORANI):
    """Eksenel simetrik profilli tankın sözleşme tablosu (TANK §D.4).

    ``yontem = sayisal:SE_meridyen_m1``; 29 doluluk satırı (sözleşme
    ızgarası), her satır ayrı ağ ve üç düzeyli yakınsama. Satırlar g'den
    bağımsızdır; Bond kapısı tüketicide g_eff ile uygulanır
    (``slosh_tablo.bond_degerlendir``). Dönüş doğrulanmış
    ``slosh_tablo.SloshTablo``.
    """
    p = _profil(profil)
    rho = _sayi(rho_kg_m3, 'rho_kg_m3', pozitif=True)
    kutle = kutle_ozellikleri_tablosu(p, rho)
    geo = kutle['geometri']
    satirlar = []
    for s in kutle['satirlar']:
        try:
            satirlar.append(se_satiri(p, s, geo, rho, n_r, n_z, buyume))
        except SloshSEHatasi as exc:
            if exc.kod not in SE_SATIR_RET_ESLEMESI:
                raise
            satirlar.append(se_ret_satiri(s, exc))
    n_ret = sum(1 for s in satirlar
                if 'AG_URETILEMEDI' in s['sebep'])
    kunye = [
        'Yöntem: sonlu eleman Ritz, m = 1 (cos θ) modu, Dodge 2000 Ek Denk. '
        '(A.1) varyasyon ilkesi (Lawrence, Wang, Reddy 1958)',
        'Eleman: P2 eş parametrik üçgen; kareleme Dunavant 1985 (6 nokta, '
        'derece 4), yüzey 3 noktalı Gauss–Legendre',
        'Ağ: sıvı bölgesinin sonlu aralıklı aktarım eşlemesi (Gordon–Hall '
        '1973); çeper düğümleri profil üstünde; yüzeye doğru inceltme '
        f'{SE_BUYUME_ORANI} (TANK §D.3)',
        'Eşdeğer model: CALKANTI §A.1.4 Denk. (A-7)–(A-10); m0, z0: Dodge 2000 '
        'Denk. (3.1), (3.2), birinci modla kesilmiş',
        f'Yakınsama: {SE_AG_DUZEY_SAYISI} düzey ({n_r}x{n_z} temel, ×2 '
        f'inceltme); kabul κ1, m1 bağıl ≤ {SE_YAKINSAMA_BAGIL_TOL:g}, z1 ≤ '
        f'{SE_YAKINSAMA_Z_TOL_ORANI:g} R_ref, mertebe ≥ '
        f'{SE_MERTEBE_BEYAN_ESIGI} (TANK §D.5); tabloda en ince düzey',
        'Kütle özellikleri: tank_mass_properties (TANK §C)',
        'I0: küresel ıslak çeperde 0 (Dodge 2000 s. 48); diğerlerinde '
        'hesaplanmadı (TANK §D.2)',
    ]
    if n_ret:
        kunye.append(f'AG_URETILEMEDI: {n_ret} dolulukta SE ağı kurulamadı; '
                     'bu satırlar RET, model alanları null (sözleşme v307-2)')
    geometri = {'tur': _tablo.GEOMETRI_PROFIL, 'R_ref_m': geo['R_ref_m'],
                'H_ic_m': geo['H_ic_m'], 'V_ic_m3': geo['V_ic_m3'],
                'kaynak': kaynak, 'profil_rz_m': p.tolist()}
    sivi = {'ad': sivi_adi, 'rho_kg_m3': rho, 'sigma_N_m': sigma_N_m,
            'nu_m2_s': nu_m2_s}
    return _tablo.tablo_olustur(tank_id, geometri, sivi,
                                _tablo.YONTEM_SAYISAL_SE, satirlar,
                                kunye=kunye)
