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
"""

import numpy as np
import pytest

from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.wall_distance import point_polyline_distance, wall_distance_field

from .conftest import LULE_L_CONV, LULE_L_DIV, LULE_NI, LULE_NJ, lule_duvar_yaricapi

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
