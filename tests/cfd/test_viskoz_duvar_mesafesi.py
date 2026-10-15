# tests/cfd — duvar poliçizgisine tam en yakın mesafe bekçileri (SA d alanı hazırlığı)
"""
``hrma.cfd.wall_distance`` doğrulama merdiveni.

Tasarım belgesi (docs/mimari/cfd-viskoz-tasarimi.md §5.5): SA'nın duvar
mesafesi d, kontur poliçizgisine TAM en yakın nokta mesafesidir;
``d = r_duvar(z) − r`` YANLIŞTIR (eğik duvarda kosinüs kadar sapar) ve
yalnız-düğüm yaklaşımı YASAKTIR. Merdiven:

(a) Analitik vakalar: düz duvar (d = |Δr|), 45° eğik duvar
    (d = |Δ|/√2), tek köşe noktası (iki komşu parçanın izdüşümü de parça
    dışında → mesafe köşe düğümüne).
(b) Kaba yolların hatası ÖLÇÜLEREK gösterilir: yalnız-düğüm yaklaşımı
    (uzun parça, ortaya yakın nokta → hata parça yarı-boyu sınıfı) ve
    dikey ``r_w − r`` yaklaşımı (45° duvarda tam √2 çarpanı).
(c) Gerçek ``AxisymGrid`` (conftest analitik lüle konturu): duvara komşu
    hücre sırasının mesafesi, hücre yarı-yüksekliği × yerel duvar açısı
    kosinüsüyle tutarlı — bant ÖLÇÜLEREK kilitli.
(d) **[V2 EKİ]** SA'nın gerçekten ihtiyaç duyduğu iki kapalı form:
    gerçek konturun 42,14° KONİK duvarına analitik mesafe ve BOĞAZ
    YAYINA (daireye) analitik mesafe. Konik bekçi, yasak radyal
    yaklaşımın (d = r_duvar(z) − r) hatasını 1/cos α = 1,3486 (yani
    %34,86) olarak ÖLÇER; yay bekçisi, ızgara poliçizgisinin yaydan
    sapmasının SEHİM (sagitta) olduğunu kapalı formla gösterir ve
    ``wall_distance_field(grid, wall_polyline=...)`` seçeneğinin bu
    sapmayı ızgara çözünürlüğünden AYIRDIĞINI ölçer.

EŞİKLER ÖLÇÜMDEN (M4 Max, 2026-08-16, ölçüm betiği scratchpad'de):
  - Düz duvar maks mutlak hata: 0,0; 45° duvar maks göreli hata:
    2,19e-16; köşe vakası fark: 0,0 → analitik eşik 1e-13 (~450× pay,
    platform/BLAS değişkenliği; mertebe değişemez).
  - Uzun parça kurgusu analitik: kesin d = 1, yalnız-düğüm √26 ≈ 5,099 —
    oran 5,099 (kurgunun kapalı formu; ölçümle birebir doğrulandı).
  - Gerçek ızgara (120×24, kosinüs kontur, |duvar açısı| ≤ 11°):
    d/(yarı-yükseklik) − cos θ bandı [+2,66e-9, +1,97e-5] ölçüldü →
    bekçi: oran ≥ cos θ − 1e-6 ve oran ≤ 1 + 1e-9 (pozitif sapma iç
    bükey kontur eğriliğinden; pay ~50×). Küresel bant: min oran
    0,981308 (cos θ_min = 0,981289 ile uyumlu), maks 0,999996.
  - Duvar sırası / eksen sırası ayrımı: maks(duvar sırası d) = 8,33e-4 m
    < min(eksen sırası d) = 2,45e-2 m (30× ayrık).

MUTASYON KANITI (elle uygulandı, kırmızı ÖLÇÜLDÜ, geri alındı; md5'ler
hrma/cfd/wall_distance.py dosyasına ait — sağlam sürüm
12f920820b0354712703f5185e46f8d5):
  M1 "izdüşüm terimini düşür": ``np.clip(t, 0.0, 1.0, out=t)`` →
     ``np.clip(t, 0.0, 0.0, out=t)`` (t ≡ 0: her parçanın yalnız
     BAŞLANGIÇ düğümü aday — yalnız-düğüm yaklaşımına çökme)
     (mutant md5 8ad53457e59420bf1e5e1e14902ab432)
     → 5 test KIRMIZI, 3 yeşil (ÖLÇÜLDÜ): test_duz_duvar_analitik,
       test_45_derece_duvar_analitik, test_yalniz_dugum_yaklasimi_hatali
       (kesin yol artık √26 veriyor), test_dikey_mesafe_yaklasimi_hatali,
       test_gercek_izgara_duvar_sirasi_bandi (oran ≈ 1,76-1,80'e
       fırlıyor). YEŞİL kalanlar beyanlı: test_kose_noktasi (en yakın
       nokta zaten düğüm — köşe vakası izdüşüm mutasyonunu tanım gereği
       yakalayamaz, analitik parça-içi vakalar yakalar),
       test_gercek_izgara_saglik (pozitiflik/tekdüzelik kaba yolda da
       sağlanır), test_girdi_denetimleri.
  Mutasyondan sonra dosya md5 12f920820b0354712703f5185e46f8d5 değerine
  bit-özdeş geri kondu (cp + md5 doğrulaması).

V2 EKİNİN ÖLÇÜMLERİ (M4 Max, 2026-08-18)
----------------------------------------
  - Konik duvar (gerçek konturun ölçülen 42,14° yakınsak açısı): kesin
    nokta-parça mesafesi analitik doğru mesafesiyle 2,09e-14 bağıl farkta;
    YASAK radyal yaklaşımın oranı TAM 1/cos(42,14°) = 1,348603819 →
    %34,86 hata (belge §5.5 uyarısının sayısal hâli).
  - Boğaz yayı (R_c = 0,382·r_t = 9,55 mm): poliçizgi mesafesinin analitik
    daire mesafesinden sapması SEHMİN kendisidir —
    s = R_c(1 − cos(Δθ/2)); ölçülen oran 17/33/65/129 düğümde 1,000.
    Sapma Δθ² ile küçülür (mertebe 2,00 ölçüldü).
  - Gerçek lüle (120×24): ızgara poliçizgisi ile 80001 noktalı gerçek
    kontur arasında 4,0133e-06 m fark — duvar sırası d ORTALAMASININ
    (6,7281e-04 m) %0,597'si, EN KÜÇÜK d'sinin (5,2091e-04 m) %0,770'i
    (ÖH defter P6B2-05: yüzde ile payda eşleştirildi). Aynı
    ızgarada 1001 noktalı kontur 5,777e-08 m'ye iner (69× daha iyi,
    bedava): d hatası AKIŞ ızgarasından ayrışır. Izgarayı sıklaştırmak
    da işe yarar ama pahalıdır (ni = 120/240/480 → 4,01e-6/1,00e-6/
    2,51e-7; mertebe 2).

V2 EKİNİN MUTASYONLARI (ters-değiştirmeyle geri alındı, md5 birebir
döndü; sağlam hrma/cfd/wall_distance.py md5 =
8d9197407bdb6c8d7233150e8b712da8)
  M8 ``wall_distance_field`` RADYAL farka döndürüldü — belgenin YASAK
     dediği yaklaşım (mutant md5 3cf33f1edb68e37be9fd7b1d422c1a28)
     → 3 KIRMIZI: test_gercek_izgara_duvar_sirasi_bandi,
     test_konik_IZGARADA_alan_analitikle_ayni,
     test_gercek_kontur_secenegi_izgaradan_ayrisir.
     Saf geometri bekçileri YEŞİL kalır ve bu BEYANLIDIR: mutasyon alan
     sarmalayıcısındadır, ``point_polyline_distance``ta değil — konik
     bekçinin ızgara kanadı tam bu boşluk için yazılmıştır.
  M9 izdüşüm kelepçesi kapatıldı (yalnız-düğüm yaklaşımına çöküş; mutant
     md5 dd159f4885622a84505b916b62b38201) → 9 KIRMIZI (eski 5 bekçi +
     yeni konik/konik-ızgara/yay/gerçek-kontur bekçilerinin dördü).
"""

import numpy as np
import pytest

from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.wall_distance import point_polyline_distance, wall_distance_field

from .conftest import (
    LULE_L_CONV, LULE_L_DIV, LULE_NI, LULE_NJ, LULE_R_THROAT,
    lule_duvar_yaricapi,
)

# Ölçümden kilitlenen eşikler (docstring'de gerekçeleri)
ANALITIK_ESIK = 1e-13
ORAN_COS_ALT_PAY = 1e-6
ORAN_UST = 1.0 + 1e-9


@pytest.fixture(scope='module')
def lule_izgarasi():
    """Conftest analitik lüle konturundan ızgara (çözücü KOŞULMAZ — ucuz)."""
    z_nodes = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, LULE_NI + 1)
    return build_grid_from_wall(z_nodes, lule_duvar_yaricapi(z_nodes),
                                LULE_NJ)


# ---------------------------------------------------------------- (a) analitik

def test_duz_duvar_analitik():
    """Yatay duvar: d = |r_duvar − r| (izdüşüm parça içinde)."""
    poly_z = np.linspace(0.0, 1.0, 11)
    poly_r = np.full(11, 0.05)
    rng = np.random.default_rng(3)
    p_z = rng.uniform(0.05, 0.95, 200)
    p_r = rng.uniform(0.0, 0.049, 200)
    d = point_polyline_distance(p_z, p_r, poly_z, poly_r)
    assert np.max(np.abs(d - (0.05 - p_r))) < ANALITIK_ESIK


def test_45_derece_duvar_analitik():
    """45° duvar (r = z): d = (z_p − r_p)/√2 — dik izdüşüm bileşeni.

    Dikey yaklaşımın (r_w − r = z_p − r_p) tam √2 katı — belge §5.5
    uyarısının analitik hâli; ayrı testte ölçülüyor.
    """
    poly_z = np.linspace(0.0, 1.0, 9)
    poly_r = poly_z.copy()
    rng = np.random.default_rng(4)
    p_z = rng.uniform(0.2, 0.8, 200)
    p_r = p_z - rng.uniform(0.01, 0.15, 200)     # duvarın altında
    d = point_polyline_distance(p_z, p_r, poly_z, poly_r)
    beklenen = (p_z - p_r) / np.sqrt(2.0)
    assert np.max(np.abs(d - beklenen) / beklenen) < ANALITIK_ESIK


def test_kose_noktasi():
    """İki parçanın izdüşümü de dışarıda → mesafe köşe düğümüne.

    Poliçizgi (0,1)-(1,1)-(1,2), nokta (2,0): her iki parçada da kelepçe
    ortak uca (1,1) çeker → d = √2. Kelepçenin köşe durumunu ayrı dal
    olmadan kapsadığının kanıtı.
    """
    d = point_polyline_distance(np.array([2.0]), np.array([0.0]),
                                np.array([0.0, 1.0, 1.0]),
                                np.array([1.0, 1.0, 2.0]))
    assert abs(d[0] - np.sqrt(2.0)) < ANALITIK_ESIK


# ---------------------------------------------------------------- (b) kaba yollar hatalı

def test_yalniz_dugum_yaklasimi_hatali():
    """Uzun parça, ortaya yakın nokta: yalnız-düğüm yolu 5× hatalı.

    Parça (0,0)-(10,0), nokta (5,1): kesin d = 1 (dik izdüşüm parça
    içinde). Yalnız-düğüm adayları √26 ≈ 5,099 verir — kaba yolun hatası
    parça yarı-boyu sınıfında. Kaba değer testin İÇİNDE hesaplanır ve
    fark ÖLÇÜLÜR (görev şartı: kaba yaklaşım yasak, farkı GÖSTER).
    """
    poly_z = np.array([0.0, 10.0])
    poly_r = np.array([0.0, 0.0])
    p_z, p_r = np.array([5.0]), np.array([1.0])
    kesin = point_polyline_distance(p_z, p_r, poly_z, poly_r)[0]
    assert abs(kesin - 1.0) < ANALITIK_ESIK
    kaba = np.min(np.hypot(poly_z - p_z[0], poly_r - p_r[0]))
    assert abs(kaba - np.sqrt(26.0)) < ANALITIK_ESIK   # kurgunun kapalı formu
    assert kaba / kesin > 5.0                          # kaba yol 5× sapıyor


def test_dikey_mesafe_yaklasimi_hatali():
    """Yasak ``d = r_w(z) − r`` yaklaşımı 45° duvarda tam √2 kat şişer.

    Belge §5.5: eğik duvarda dikey mesafe kosinüs kadar sapar; 45°'de
    çarpan √2'dir (kapalı form). Yaklaşım testin içinde kurulur, oran
    makine hassasiyetinde √2 ölçülür.
    """
    poly_z = np.linspace(0.0, 1.0, 9)
    poly_r = poly_z.copy()
    p_z = np.array([0.5, 0.6, 0.7])
    p_r = p_z - np.array([0.05, 0.10, 0.02])
    kesin = point_polyline_distance(p_z, p_r, poly_z, poly_r)
    dikey = p_z - p_r                                  # r_w(z_p) − r_p, duvar r=z
    assert np.max(np.abs(dikey / kesin - np.sqrt(2.0))) < ANALITIK_ESIK


# ---------------------------------------------------------------- (c) gerçek ızgara

def test_gercek_izgara_duvar_sirasi_bandi(lule_izgarasi):
    """Duvara komşu sıranın d'si = yarı-yükseklik × cos θ sınıfında (bant ölçüldü).

    Düzgün radyal dağılımda duvara komşu hücrenin radyal yüksekliği
    r_w/nj; merkezden duvara dik mesafe ≈ (r_w/(2nj))·cos θ (θ yerel
    duvar eğim açısı). ÖLÇÜLDÜ (120×24): oran − cos θ ∈ [+2,7e-9,
    +2,0e-5] (pozitif sapma iç bükey eğrilikten) → bant bekçisi.
    """
    grid = lule_izgarasi
    d_alan = wall_distance_field(grid)
    r_w_orta = 0.5 * (grid.R[:-1, -1] + grid.R[1:, -1])
    yari_yukseklik = r_w_orta / (2.0 * LULE_NJ)
    oran = d_alan[:, -1] / yari_yukseklik
    dz_w = np.diff(grid.Z[:, -1])
    dr_w = np.diff(grid.R[:, -1])
    cos_theta = dz_w / np.hypot(dz_w, dr_w)
    assert np.all(oran >= cos_theta - ORAN_COS_ALT_PAY)
    assert np.all(oran <= ORAN_UST)
    # Küresel bant (ölçülen min 0,981308 — cos θ_min 0,981289 ile uyumlu)
    assert oran.min() > 0.98
    # Dikey (yasak) yaklaşım üst sınırdır: hücre merkezinin tam üstündeki
    # duvar noktası poliçizgi ÜSTÜNDE olduğundan kesin en yakın mesafe
    # ondan büyük olamaz (geometrik gerçek; ÖLÇÜLDÜ: en dar boşluk
    # 2,1e-9 m mutlak / 4,1e-6 göreli — ulp kılpayı değil, pay gerekmez)
    dikey = (np.interp(grid.z_centers[:, -1], grid.Z[:, -1], grid.R[:, -1])
             - grid.r_centers[:, -1])
    assert np.all(d_alan[:, -1] <= dikey)


def test_gercek_izgara_saglik(lule_izgarasi):
    """Alan biçimi, pozitiflik ve duvar/eksen sırası ayrımı (ölçülen)."""
    grid = lule_izgarasi
    d_alan = wall_distance_field(grid)
    assert d_alan.shape == (LULE_NI, LULE_NJ)
    assert np.all(d_alan > 0.0)
    assert np.all(np.isfinite(d_alan))
    # ÖLÇÜLDÜ: maks duvar sırası 8,33e-4 m, min eksen sırası 2,45e-2 m
    assert d_alan[:, -1].max() < d_alan[:, 0].min()
    # j arttıkça (duvara yaklaştıkça) d azalır — H-tipi radyal sütunlarda
    # tekdüzelik beklenir (duvar tek taraflı sınır)
    assert np.all(np.diff(d_alan, axis=1) < 0.0)


# ------------------------------------------- (d) V2: konik + boğaz yayı kapalı formu

#: Gerçek konturun ÖLÇÜLEN maksimum yakınsak duvar açısı (tasarım belgesi
#: §5.7: "yakınsak duvar açısı 42,14°'ye çıkıyor"). SA'nın d alanı tam
#: burada radyal yaklaşımdan en çok ayrılır.
KONIK_ACI_DERECE = 42.14
#: Klasik boğaz yayı yarıçapı R_c = 0,382·r_t (belge §5.7'nin kendi sayısı).
BOGAZ_YAY_ORANI = 0.382


def test_konik_duvar_analitik_kapali_form():
    """42,14° konik duvara mesafe: analitik doğru mesafesiyle makine eşit.

    Kapalı form: p noktasının a'dan geçen ve birim yönü (cos α, sin α)
    olan doğruya uzaklığı |(p − a) × yön| = |Δz sin α − Δr cos α|.
    Ayrıca YASAK radyal yaklaşımın oranı 1/cos α'dır — ölçülür.
    """
    alfa = np.deg2rad(KONIK_ACI_DERECE)
    z0, r0 = 0.0, 0.10
    poly_z = np.linspace(0.0, 0.2, 25)
    poly_r = r0 + np.tan(alfa) * (poly_z - z0)
    p_z = np.linspace(0.03, 0.17, 401)
    dikey = np.linspace(0.001, 0.02, 401)          # duvarın ALTINDA
    p_r = (r0 + np.tan(alfa) * (p_z - z0)) - dikey

    d = point_polyline_distance(p_z, p_r, poly_z, poly_r)
    analitik = np.abs((p_z - z0) * np.sin(alfa)
                      - (p_r - r0) * np.cos(alfa))
    assert np.max(np.abs(d - analitik) / analitik) < ANALITIK_ESIK

    # YASAK yol (d = r_duvar(z) − r) TAM 1/cos α kadar şişer
    oran = dikey / d
    assert np.max(np.abs(oran - 1.0 / np.cos(alfa))) < ANALITIK_ESIK
    assert abs(float(np.mean(oran)) - 1.348603819) < 1e-9
    assert float(np.mean(oran)) - 1.0 > 0.34        # %34'ten fazla hata


def test_konik_IZGARADA_alan_analitikle_ayni():
    """Aynı kapalı form ``wall_distance_field`` ALANI üstünde (uçtan uca).

    Önceki bekçi saf geometriyi ölçer; bu bekçi SA'nın gerçekten
    kullandığı yolu (ızgara → alan) ölçer ve mesafenin radyal farka
    dönmesi mutasyonunu YAKALAR. Kapsam duvara komşu sıradır: daha
    derin sıralarda en yakın nokta SONLU duvar parçasının UCU olur
    (geometrik gerçek, kusur değil) ve sonsuz doğru formülü orada
    geçerliliğini yitirir — ölçüldü: j = nj−1'de bağıl fark 3,9e-15,
    j = nj−2'de 1,5e-02.
    """
    alfa = np.deg2rad(KONIK_ACI_DERECE)
    L, r0 = 0.10, 0.02
    z = np.linspace(0.0, L, 41)
    grid = build_grid_from_wall(z, r0 + np.tan(alfa) * z, 10)
    d = wall_distance_field(grid)
    analitik = np.abs(grid.z_centers * np.sin(alfa)
                      - (grid.r_centers - r0) * np.cos(alfa))
    assert np.max(np.abs(d[:, -1] - analitik[:, -1])
                  / analitik[:, -1]) < 1e-13
    # Radyal (YASAK) yaklaşımın oranı ALANDA da tam 1/cos α
    radyal = (np.interp(grid.z_centers, z, r0 + np.tan(alfa) * z)
              - grid.r_centers)
    oran = (radyal / d)[:, -1]
    assert np.max(np.abs(oran - 1.0 / np.cos(alfa))) < 1e-12
    # Eksene yakın sıralarda oran DÜŞER (ölçüldü: en küçük 1,058) — çünkü
    # orada kesin mesafe artık dik ayak değil, parça UCU üstündendir.
    assert float((radyal / d)[:, 0].min()) < 1.10
    # Duvara komşu sırada mutlak sapma: SA'nın d²'sinde %82 hata demektir
    assert (1.0 / np.cos(alfa)) ** 2 - 1.0 > 0.8


def test_bogaz_yayi_sapmasi_sehim_kadar():
    """Poliçizgi ↔ analitik daire: fark SEHİMDİR, R_c(1 − cos(Δθ/2)).

    Boğaz yayı iç bükeydir; hücre merkezleri dairenin İÇİNDEDİR ve
    daireye mesafe |R_c − |p − merkez|| kapalı formundadır. Kirişlerin
    yaydan sapması sehimdir; bekçi hem oranı (≈1) hem de mertebeyi
    (Δθ² ⇒ düğüm sayısı iki katına çıkınca dörtte bir) kilitler.
    """
    r_t = LULE_R_THROAT
    R_c = BOGAZ_YAY_ORANI * r_t
    merkez = (0.0, r_t + R_c)
    ofset = 1.0e-5                                  # duvardan içeri [m]
    farklar = []
    for n in (17, 33, 65, 129):
        th = np.linspace(-0.5, 0.5, n)
        w_z = merkez[0] + R_c * np.sin(th)
        w_r = merkez[1] - R_c * np.cos(th)
        tq = np.linspace(-0.35, 0.35, 73)
        q_z = merkez[0] + (R_c - ofset) * np.sin(tq)
        q_r = merkez[1] - (R_c - ofset) * np.cos(tq)
        d = point_polyline_distance(q_z, q_r, w_z, w_r)
        analitik = np.abs(R_c - np.hypot(q_z - merkez[0], q_r - merkez[1]))
        assert np.allclose(analitik, ofset, rtol=1e-12)   # kurgunun kontrolü
        sehim = R_c * (1.0 - np.cos(0.5 * (th[1] - th[0])))
        fark = float(np.max(np.abs(d - analitik)))
        assert abs(fark / sehim - 1.0) < 0.02, (
            f'n={n}: fark {fark!r}, sehim {sehim!r}')
        farklar.append(fark)
    mertebe = [np.log2(farklar[i] / farklar[i + 1])
               for i in range(len(farklar) - 1)]
    assert all(1.9 < m < 2.1 for m in mertebe), f'sehim mertebesi {mertebe}'
    # Sapma, duvar-çözümlü ızgaranın ilk hücresi sınıfındadır: 17 düğümde
    # sehim ofsetin %46'sı (yani d %46 yanlış olurdu)
    assert farklar[0] / ofset > 0.4


def test_gercek_kontur_secenegi_izgaradan_ayrisir(lule_izgarasi):
    """``wall_polyline`` seçeneği d hatasını AKIŞ ızgarasından ayırır.

    Izgaranın duvar çizgisi konturun kirişleridir; SA'nın d'si için
    çağıran gerçek konturu (istediği sıklıkta) verebilmelidir. Bekçi
    üçünü birden ölçer: (i) ince örneklemeye yakınsama mertebesi 2,
    (ii) ızgara poliçizgisinin ÖLÇÜLEN sapması, (iii) 1001 noktalı
    konturun aynı ızgarada 60×'ten iyi olması.
    """
    grid = lule_izgarasi
    uzunluk = LULE_L_CONV + LULE_L_DIV

    def kontur(n):
        zz = np.linspace(0.0, uzunluk, n)
        return zz, lule_duvar_yaricapi(zz)

    referans = wall_distance_field(grid, kontur(80001))

    sapma = [float(np.max(np.abs(wall_distance_field(grid, kontur(n))
                                 - referans)))
             for n in (1001, 5001, 20001)]
    assert sapma[0] < 1.0e-7
    mertebe = [np.log(sapma[i] / sapma[i + 1]) / np.log(5.0 if i == 0 else 4.0)
               for i in range(len(sapma) - 1)]
    assert all(1.9 < m < 2.1 for m in mertebe), f'örnekleme mertebesi {mertebe}'

    izgara = wall_distance_field(grid)
    izgara_sapmasi = float(np.max(np.abs(izgara - referans)))
    assert 3.5e-6 < izgara_sapmasi < 4.5e-6          # ÖLÇÜLDÜ: 4,013e-06
    assert izgara_sapmasi / izgara[:, -1].mean() > 0.005
    assert izgara_sapmasi / sapma[0] > 60.0
    # Varsayılan davranış DEĞİŞMEDİ: argümansız çağrı ızgara duvarıdır
    assert np.array_equal(izgara, point_polyline_distance(
        grid.z_centers, grid.r_centers, grid.Z[:, -1], grid.R[:, -1]))


# ---------------------------------------------------------------- girdi denetimleri

def test_girdi_denetimleri():
    """Sözleşme ihlalleri gerekçeli ValueError ile reddedilir."""
    iyi_z = np.array([0.0, 1.0, 2.0])
    iyi_r = np.array([1.0, 1.0, 1.0])
    p = np.array([0.5])
    with pytest.raises(ValueError, match='aynı biçimde'):
        point_polyline_distance(p, np.array([0.1, 0.2]), iyi_z, iyi_r)
    with pytest.raises(ValueError, match='1B dizi'):
        point_polyline_distance(p, p, iyi_z, iyi_r[:2])
    with pytest.raises(ValueError, match='en az 2'):
        point_polyline_distance(p, p, iyi_z[:1], iyi_r[:1])
    with pytest.raises(ValueError, match='sonlu'):
        point_polyline_distance(p, np.array([np.nan]), iyi_z, iyi_r)
    with pytest.raises(ValueError, match='sıfır uzunluklu'):
        point_polyline_distance(p, p, np.array([0.0, 1.0, 1.0]),
                                np.array([1.0, 1.0, 1.0]))
