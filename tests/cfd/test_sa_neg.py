# tests/cfd — SA-neg türbülans çekirdeği bekçileri (V2, tasarım belgesi §5.5)
"""
``hrma.cfd.sa_neg`` doğrulama merdiveni. Bu dosyada KOŞUM YOKTUR: her
bekçi ya cebirsel bir özdeşliği ya da kapalı formu bilinen bir alanı
ölçer. SA'nın türbülanslı düz levha hükmü (belge basamak 8) ayrı partinin
işidir; burada MODELİN KENDİSİ ve ayrıklaştırması kilitlenir.

MERDİVEN
--------
(1) Künye ve sabitler: yayımlanmış SAYILARLA karşılaştırma (NASA TMR'nin
    kendi yazdığı ν_t/ν = 0,210438 ve 1,294234 değerleri; ICCFD7-1902'nin
    "negatif difüzyon katsayısı ilk c_n1 ≈ 16,46'da oluşur" iddiası).
(2) İç katman (log-katman) özdeşliği: ν̃ = κ u_τ d doğrusal profili
    kaynak + difüzyon dengesini SIFIRLAR. Bu, c_w1 = c_b1/κ² + (1+c_b2)/σ
    bağıntısının CEBİRSEL nedenidir ve bekçisi de odur.
(3) Negatif dal: enerji kararlılığı (ICCFD7-1902 Denklem 18), negatif
    kararlı-hâl minimumunun imkânsızlığı (Denklem 20), ν̃ = 0'da C⁰
    süreklilik ve KIRIĞIN ÖLÇÜLEN büyüklüğü.
(4) Değiştirilmiş girdaplılık yaması (Denklem 12): yama noktası,
    asimptot, pozitiflik, Ω = 0 koruması.
(5) Alan operatörleri: düzgün alan korunumu (BİT sıfır), doğrusal alanda
    analitik akı, taşınım mertebesi (upwind1 = 1, MUSCL kuadratikte TAM),
    ve ρ'nun türev İÇİNE alınmasının ölçülen bedeli.
(6) Sözleşme: fiziksel olmayan durumda NaN (viscous.py ile ORTAK ölçüt).
(7) Nokta-örtük yok etme: açık yol ıraksarken örtük yol AYNI köke
    yakınsar (kararlılık kazancı ölçülü, cevap değişmiyor).

ÖLÇÜLEN EŞİKLER (M4 Max, 2026-08-18; ölçüm betikleri scratchpad'de)
-------------------------------------------------------------------
- ν_t/ν(χ=3) = 0,21043825715555 ve ν_t/ν(χ=5) = 1,29423434131755 —
  TMR'nin yayımladığı 6 haneyle birebir → eşik 1e-6 (yayımlanan sayının
  kendi hane sayısı).
- min(1 + χ f_n) = 0,00935866 (χ = −1,3744); kritik c_n1 = 16,4578
  (makale: "≈16,46") → bekçi 16,45 < c_kritik < 16,47.
- Log-katman dengesi χ ile 1/χ gibi söner: χ=10³ → 1,4702e-3,
  10⁴ → 1,4753e-4, 10⁵ → 1,4757e-5, 10⁶ → 1,4758e-6 (mertebe 1,00).
  Katsayının KAPALI FORMU c_b1 + (1+5c_w2)(1 − 1/(1+c_w3⁶))c_w1κ² =
  1,4757757; ölçülen 1,4757713 (bağıl fark 3e-6).
- c_w1'i %1 büyütmek dengeyi 1,476e-6'dan −5,443e-3'e taşır (3688×).
- ν̃ = 0'da kaynak türevi sıçraması = c_b1·c_t3·Ω (ölçülen 162,604 ↔
  kapalı form 162,600; sonlu fark hatası %0,0025) ve sağ/sol türev oranı
  TAM −5 = 1/(1 − c_t3).
- Doğrusal ν̃ alanında difüzyon akısı analitik kapalı formla 1,08e-14
  bağıl farkta; düzgün alanda difüzyon ve taşınım BİT sıfır.
- Taşınım mertebesi (iç bölge, sınır hücreleri hariç): upwind1 1,00-1,05;
  MUSCL tekdüze kuadratikte MAKİNE hassasiyetinde tam (1e-14), sinüs
  profilinde 1,51-1,59 (minmod ekstremumu kırpar — beyanlı).
- ρ türevin İÇİNE alınırsa (belge §5.5'in yazımı): kalıntı ızgara
  inceltmesiyle YAKINSAMAZ, 3,48e-05'te oturur; ihmal edilen terim tam
  difüzyonun ortalama %85'i, en çok %146'sıdır. Doğru biçim (Denklem 9)
  analitiğe 1,97 mertebesinde yakınsar.
- Nokta-örtük köşegen (V3'te TAM ANALİTİK — üretim türevi dahil):
  d = 0,4 µm hücresinde J = 2,0833e7 1/s ve DENGE noktasında merkezî
  FD eğiminin ta kendisi (−2,083303e7; bağıl < 1e-6). Eski (donmuş yok
  etme) köşegen 7,2192e7 idi — o noktada 3,47 kat fazla sönüm. Açık yol
  0,05·(2/J)'de yaşar, 0,5·(2/J)'de ıraksar (geçiş rejimi daha dik:
  bandda maks J⁻ = 5,02e8); örtük yol 40×(2/J)'de bile AYNI köke
  (ν̃ = 6,5516e-06) yakınsar. FD taraması: 20 000 rastgele durumda
  (iki dal, χ ∈ [−3, 60]) köşegen ↔ merkezî FD maks bağıl 1,8e-08.
  Tampon kökü (χ* = 3, Ω = 2,8399e6): |gerçek eğim|/eski köşegen = 2,535
  → eski köşegenle nokta-örtük harita Δt'den bağımsız salınıma kilitli
  (genlik/kök 0,48-0,50, Δt dört mertebe taranıp ölçüldü), yeni
  köşegenle |Δ| makine sıfırı (Newton).

MUTASYON KANITI (elle uygulandı, kırmızı ÖLÇÜLDÜ, TERS-DEĞİŞTİRMEYLE geri
alındı — checkout YOK; her turdan sonra md5 birebir döndü).
M1-M7 kayıtları PARTİ 38 dosyasına aittir (o turun sağlam md5'i =
415d483fdef1b3c42189211d2035cf1f); M8, V3 (parti 39, tam analitik
köşegen) dosyasına karşı ölçüldü — V3 sağlam md5 =
18ab1fea14813cc32b070fd2a5c6b982:

  M1 c_b2 → −0,622            (96cd96ce…) → 6 kırmızı: c_w1 literali,
     c_n1 kritiği, c_b2 dengesi, ∇ρ büyüklüğü, nokta-örtük ısırığı,
     Jacobian köşegeni.
  M2 upwind YÖNÜ (>=0 → <0)   (50b5d8b2…) → 2 kırmızı: upwind yönü,
     MUSCL yönü. **İLK TURDA 0 KIRMIZI VERDİ** — bekçi doğrusal profille
     yazılmıştı ve doğrusal profilde iki yön AYNI sayıyı verir; bekçi
     basamak profiline taşındı (kusuru koruyan bekçi, ölçümle yakalandı).
  M2b MUSCL eğim yönü takası  (9588ea26…) → 1 kırmızı: MUSCL mertebesi.
  M3 nokta-örtük köşegen ≡ 0  (2632444e…) → 4 kırmızı: negatif dal
     köşegeni, kararlılık ısırığı, hüküm-nötrlük, Jacobian köşegeni.
  M4 ∇ρ düzeltmesi varsayılan olarak KAPALI (3fd9ca68…) → 1 kırmızı:
     terimin büyüklüğü. (Yakınsama bekçisi iki dalı da KENDİ çağırdığı
     için mutasyondan etkilenmez — bilinçli.)
  M5 c_n1 → 16,5              (29128a40…) → 1 kırmızı: kritik c_n1.
  M6 c_t3 → 0 (C¹'i geri alma denemesi) (7be54407…) → 2 kırmızı: negatif
     dal enerji kararlılığı, C⁰ kırığının büyüklüğü.
  M7 f_n ≡ 1 (SA-neg difüzyon dalı yok) (b1c7832c…) → 1 kırmızı:
     kritik c_n1 bekçisi.
  M8 (V3) pozitif dal köşegeni DONMUŞ yok etmeye geri düşürüldü
     (turev → −2c_w1f_wν̃/d²; mutant md5 a3716f2de85ff14bcffad759614374f1)
     → 6 KIRMIZI: bu dosyada 4 (kararlılık ısırığı — köşegen ≠ gerçek
     eğim; TAM analitik türev bekçisi; FD taraması; tampon periyot-2) +
     test_duz_levha_sa.py'de 2 (SA kalıntısı 4 mertebe düşemiyor;
     log-yasası sapması bandı ±0,15 aşılıyor) — parti 38'in M1 kanıtının
     V3 halefi. Geri alma: md5 birebir 18ab1fea… döndü.
"""

import numpy as np
import pytest

from hrma.cfd import sa_neg as sa
from hrma.cfd.euler_core import cons_to_prim_axisym, prim_to_cons_axisym
from hrma.cfd.gas_transport import GasTransport
from hrma.cfd.gradients import BoundaryFaceValues, precompute_gradient_geometry
from hrma.cfd.grid_axisym import build_grid_from_wall

# --- doğrulama akışkanı (sabit özellikli; test_viskoz_aki.py ile aynı desen)
SA_GAMMA = 1.4
SA_R = 287.0
SA_CP = SA_GAMMA * SA_R / (SA_GAMMA - 1.0)
SA_PRANDTL = 0.7
SA_MU = 1.0e-3
SA_T_REF = 300.0

# Ölçülen eşikler (docstring'de gerekçeleri)
YAYIMLANAN_HANE = 1.0e-6          # TMR'nin yazdığı ν_t/ν hane sayısı
MAKINE = 1.0e-13
LOG_KATMAN_KATSAYI_TOL = 1.0e-4


def transport(mu_ref=SA_MU, exponent=0.0):
    return GasTransport(
        gamma=SA_GAMMA, T_ref=SA_T_REF, mu_ref=mu_ref, cp=SA_CP,
        prandtl=SA_PRANDTL, prandtl_turbulent=0.9,
        viscosity_exponent=exponent,
        sources={'viscosity': 'verification_case', 'cp': 'gamma_R_identity',
                 'prandtl': 'verification_case'})


def pipe(ni=12, nj=8, length=0.05, radius=0.005):
    return build_grid_from_wall(np.linspace(0.0, length, ni + 1),
                                np.full(ni + 1, radius), nj)


def state(grid, uz, ur, T, p=1.0e5):
    p_arr = np.broadcast_to(np.asarray(p, dtype=float), uz.shape)
    rho = p_arr / (SA_R * T)
    return prim_to_cons_axisym(rho, uz, ur, p_arr, SA_GAMMA)


def sabit_alan(grid, uz=100.0, T=SA_T_REF, p=1.0e5):
    sh = (grid.ni, grid.nj)
    return state(grid, np.full(sh, uz), np.zeros(sh), np.full(sh, T), p)


def yuz_bc(grid, fonk):
    """Analitik alan için TAM sınır yüz değerleri (dört sınır da Dirichlet)."""
    def mid(z, r):
        return fonk(0.5 * (z[:-1] + z[1:]), 0.5 * (r[:-1] + r[1:]))

    return BoundaryFaceValues(
        i_lo=mid(grid.Z[0], grid.R[0]), i_hi=mid(grid.Z[-1], grid.R[-1]),
        j_lo=mid(grid.Z[:, 0], grid.R[:, 0]),
        j_hi=mid(grid.Z[:, -1], grid.R[:, -1]))


# ===========================================================================
# 1) Künye ve sabitler — yayımlanmış SAYILARLA
# ===========================================================================

def test_cw1_turetilmis_literal_degil():
    """c_w1 bağıntıdan türetilir; dergi ekindeki dizgi hatası taşınamaz.

    NASA TMR uyarısı: SA 1994 dergi sürümünün ekinde c_w1 tanımında
    κ'nın karesi düşmüştür ve bu hata başka raporlara YAYILMIŞTIR. Hatalı
    biçim (κ² yerine κ) 0,3306 + 2,433 = 2,763 verirdi; doğrusu 3,23907.
    """
    assert sa.SA_C_W1 == (sa.SA_C_B1 / sa.SA_KAPPA ** 2
                          + (1.0 + sa.SA_C_B2) / sa.SA_SIGMA)
    hatali = sa.SA_C_B1 / sa.SA_KAPPA + (1.0 + sa.SA_C_B2) / sa.SA_SIGMA
    assert abs(sa.SA_C_W1 - hatali) > 0.4          # iki biçim ayrık
    assert abs(sa.SA_C_W1 - 3.2390678167757287) < 1e-15
    # Kaynakta c_w1 için LİTERAL sayı yok (türetim yapısal olarak korunuyor)
    kaynak = open(sa.__file__, encoding='utf-8').read()
    assert '3.239' not in kaynak.split('MUTASYON')[0]


def test_serbest_akim_nut_orani_yayimlanan_sayilarla():
    """ν̃/ν = 3 ve 5 → ν_t/ν = 0,210438 ve 1,294234 (TMR'nin yazdığı sayı).

    Bu tek bekçi c_v1'i ve f_v1'in biçimini altı hanede kilitler: TMR bu
    iki sayıyı SA sayfasında serbest-akım koşulunun karşılığı olarak
    yayımlar.
    """
    for x, beklenen in ((3.0, 0.210438), (5.0, 1.294234)):
        olculen = float(x * sa.f_v1(np.array(x)))
        assert abs(olculen - beklenen) < YAYIMLANAN_HANE, (
            f'χ={x}: ν_t/ν {olculen!r}, yayımlanan {beklenen}')
    # Aynı sayı μ_t yolundan da çıkmalı (iki yol tek tanım)
    mu_t = sa.turbulent_viscosity(np.array(2.0), np.array(3.0 * 1.5e-5),
                                  np.array(2.0 * 1.5e-5))
    assert abs(float(mu_t) / (2.0 * 1.5e-5) - 0.210438) < YAYIMLANAN_HANE


def test_cn1_kritik_degeri_makalenin_iddiasiyla():
    """1 + χf_n > 0 (Denklem 20) ve kritik c_n1 ≈ 16,46 (makalenin sayısı).

    ICCFD7-1902: "The diffusion coefficient ν + ν̃f_n is everywhere
    positive... A negative diffusion coefficient first occurs with
    c_n1 ≈ 16.46, which limits the magnitude of this parameter."
    Bekçi hem iddiayı hem de c_n1 = 16 seçiminin PAYINI ölçer.
    """
    x = np.linspace(-60.0, -1e-9, 400001)
    h = 1.0 + x * sa.f_n(x)
    assert h.min() > 0.0
    assert abs(h.min() - 0.00935866) < 1e-7
    assert abs(x[h.argmin()] + 1.3744) < 1e-3

    def min_h(cn1, monkey):
        monkey.setattr(sa, 'SA_C_N1', cn1)
        xx = np.linspace(-10.0, -1e-9, 200001)
        return float((1.0 + xx * sa.f_n(xx)).min())

    mp = pytest.MonkeyPatch()
    try:
        alt, ust = 16.0, 17.0
        for _ in range(40):
            orta = 0.5 * (alt + ust)
            if min_h(orta, mp) > 0.0:
                alt = orta
            else:
                ust = orta
    finally:
        mp.undo()
    assert 16.45 < alt < 16.47, f'kritik c_n1 ölçüldü: {alt!r}'
    # Enerji kararlılığı koşulu (Denklem 18) DAHA GEVŞEKTİR — makale böyle
    # diyor, ölçüm doğruluyor (min 0,7375 > min 0,00936).
    h18 = 1.0 + x * (sa.f_n(x) - sa.SA_C_B2)
    assert h18.min() > h.min()
    assert abs(h18.min() - 0.73745525) < 1e-7


def test_serbest_akim_bandi_bir_kapidir():
    """ν̃/ν ∈ [3, 5] bandı (Denklem 8) — dışına çıkan değer REDDEDİLİR."""
    nu_inf = 1.5e-5
    assert sa.freestream_nu_tilde(nu_inf, 3.0) == 3.0 * nu_inf
    assert sa.freestream_nu_tilde(nu_inf, 5.0) == 5.0 * nu_inf
    for kotu in (0.6, 2.999, 5.001, 10.0):
        with pytest.raises(ValueError, match=r'yayımlanmış bandın'):
            sa.freestream_nu_tilde(nu_inf, kotu)
    with pytest.raises(ValueError, match=r'nu_inf pozitif'):
        sa.freestream_nu_tilde(-1.0, 3.0)
    assert sa.SA_FREESTREAM_CHI_BAND == (3.0, 5.0)


def test_kunye_beyanda_gorunur():
    """Sabit sözlüğü künyeyi ve c_w1 türetimini TAŞIR (koşum beyanı)."""
    k = sa.sa_constants()
    assert k['c_w1'] == sa.SA_C_W1
    assert k['c_w1_derived_from'] == 'c_b1/kappa^2 + (1+c_b2)/sigma'
    assert 'ICCFD7-1902' in k['citations']['negative_branch']
    assert 'Recherche Aerospatiale' in k['citations']['model']
    assert 'SA-noft2' in k['citations']['variant']
    # c_t4 BİLEREK tanımsız (yalnız f_t2'nin içinde geçer, f_t2 ≡ 0)
    assert not hasattr(sa, 'SA_C_T4')


# ===========================================================================
# 2) İç katman (log-katman) cebirsel özdeşliği
# ===========================================================================

def _log_katman_dengesi(chi_hedef, u_tau=1.0, d=1.0e-3):
    """ν̃ = κu_τd, Ω = u_τ/(κd) profilinde (üretim − yok etme + difüzyon).

    Difüzyon terimi bu profil için KAPALI FORMDUR:
        (1/σ)[d/dy((ν+ν̃)dν̃/dy) + c_b2(dν̃/dy)²] = (1+c_b2)(κu_τ)²/σ
    (ν̃ doğrusal olduğundan ikinci türev sıfırdır ve geriye ν̃'nin kendi
    eğiminin karesi kalır.) Kalan iki terim modülün KENDİ fonksiyonundan
    okunur — testin içinde ikinci bir SA gerçeklemesi yoktur.
    """
    nu_tilde = sa.SA_KAPPA * u_tau * d
    omega = u_tau / (sa.SA_KAPPA * d)
    nu = nu_tilde / chi_hedef
    rho = 1.0
    kaynak = sa.sa_source_terms(np.array(rho), np.array(nu_tilde),
                                np.array(rho * nu), np.array(omega),
                                np.array(d))
    difuzyon = (1.0 + sa.SA_C_B2) * (sa.SA_KAPPA * u_tau) ** 2 / sa.SA_SIGMA
    return float(kaynak.source) + difuzyon, kaynak


def test_log_katmani_kaynak_dengesi_sifira_gider():
    """ν̃ = κu_τd profili dengeyi sıfırlar: artık 1/χ gibi söner.

    Bu, c_w1 bağıntısının CEBİRSEL nedenidir. Artığın ilk mertebe
    katsayısı da kapalı formdur:
        c_b1 + (df_w/dr)|₁ · c_w1κ²,  (df_w/dr)|₁ = (1+5c_w2)(1 − 1/(1+c_w3⁶))
    """
    dengeler = [_log_katman_dengesi(x)[0] for x in (1e3, 1e4, 1e5, 1e6)]
    mertebe = [np.log10(dengeler[i] / dengeler[i + 1])
               for i in range(len(dengeler) - 1)]
    assert all(0.99 < m < 1.01 for m in mertebe), (
        f'artık 1/χ gibi sönmüyor: {mertebe}')
    katsayi = dengeler[-1] * 1e6
    dfw_dr = (1.0 + 5.0 * sa.SA_C_W2) * (1.0 - 1.0 / (1.0 + sa.SA_C_W3 ** 6))
    kapali = sa.SA_C_B1 + dfw_dr * sa.SA_C_W1 * sa.SA_KAPPA ** 2
    assert abs(katsayi - kapali) / kapali < LOG_KATMAN_KATSAYI_TOL, (
        f'ölçülen katsayı {katsayi!r}, kapalı form {kapali!r}')


def test_log_katmaninda_r_ve_fw_bire_gider():
    """İç katmanda r → 1 ve f_w → 1 (dengeyi kuran ikinci ayak)."""
    u_tau, d = 1.0, 1.0e-3
    nu_tilde = sa.SA_KAPPA * u_tau * d
    omega = u_tau / (sa.SA_KAPPA * d)
    nu = np.array(nu_tilde / 1e6)
    s_tilde = sa.modified_vorticity(np.array(omega), np.array(nu_tilde),
                                    np.array(d), nu)
    r = sa.sa_r(np.array(nu_tilde), s_tilde, np.array(d))
    assert abs(float(s_tilde) / omega - 1.0) < 1e-5
    assert abs(float(r) - 1.0) < 1e-5
    assert abs(float(sa.f_w(r)) - 1.0) < 1e-5


def test_cw1_bagintisi_dengeyi_kuruyor(monkeypatch):
    """c_w1 %1 kayarsa iç katman dengesi 3 mertebe bozulur (ölçülü)."""
    saglam, _ = _log_katman_dengesi(1e6)
    monkeypatch.setattr(sa, 'SA_C_W1', sa.SA_C_W1 * 1.01)
    bozuk, _ = _log_katman_dengesi(1e6)
    assert abs(bozuk) / abs(saglam) > 1000.0, (
        f'sağlam {saglam!r} ↔ bozuk {bozuk!r}')
    assert bozuk < 0.0                     # fazla yok etme → negatif denge


def test_cb2_isareti_dengeyi_kuruyor(monkeypatch):
    """c_b2 işareti dönerse iç katman dengesi kapanmaz (mutasyon bekçisi)."""
    saglam, _ = _log_katman_dengesi(1e6)
    monkeypatch.setattr(sa, 'SA_C_B2', -sa.SA_C_B2)
    bozuk, _ = _log_katman_dengesi(1e6)
    assert abs(bozuk) / abs(saglam) > 1000.0
    # c_b2 yalnız difüzyonda; işaret dönünce difüzyon ÜRETİMİ kaybolur
    assert bozuk < 0.0


# ===========================================================================
# 3) Negatif ν̃ dalı — enerji kararlılığı ve C⁰ kırığı
# ===========================================================================

def test_negatif_dal_kaynak_pozitif_enerji_azalir():
    """Denklem 18/20: P_n − D_n ≥ 0 ve ν̃·(P_n − D_n) ≤ 0 (enerji söner)."""
    nu_tilde = -np.logspace(-9.0, -1.0, 2000)
    bir = np.ones_like(nu_tilde)
    s = sa.sa_source_terms(bir, nu_tilde, 1.5e-5 * bir, 1000.0 * bir,
                           1.0e-3 * bir)
    assert np.all(np.isfinite(s.source))
    assert np.all(s.source >= 0.0), 'negatif dalda kaynak negatife düştü'
    assert np.all(nu_tilde * s.source <= 0.0), 'enerji kararlılığı bozuldu'
    # İki terim de AYRI AYRI sönümleyici (makalenin tercihi: P_n > 0, D_n < 0)
    assert np.all(s.production >= 0.0)
    assert np.all(s.destruction <= 0.0)
    # Nokta-örtük köşegen negatif dalda da pozitif (kararlılık payı)
    assert np.all(s.jacobian_diag > 0.0)


def test_negatif_dal_ct3_sifirlanirsa_enerji_kararliligi_kirilir(monkeypatch):
    """C¹'i geri almak için c_t3 = 0 denenirse Denklem 18 ÇÖKER.

    ICCFD7-1902: f_t2 kaldırılınca "either C¹ continuity must be given up
    or P_n < 0 must be allowed". Bu modül birinciyi seçer; ikincisinin
    bedeli burada ÖLÇÜLÜR — c_t3 = 0 ile üretim negatife döner ve enerji
    kararlılığı iddiası yalanlanır.
    """
    nu_tilde = -np.logspace(-9.0, -1.0, 500)
    bir = np.ones_like(nu_tilde)
    monkeypatch.setattr(sa, 'SA_C_T3', 0.0)
    s = sa.sa_source_terms(bir, nu_tilde, 1.5e-5 * bir, 1000.0 * bir,
                           1.0e-3 * bir)
    assert np.any(s.production < 0.0), 'c_t3=0 üretimi negatife çevirmeliydi'
    assert np.any(s.source < 0.0), 'Denklem 18 ihlali görünmedi'


def test_sifirda_C0_sureklilik_ve_kirigin_buyuklugu():
    """Kaynak ν̃ = 0'da SÜREKLİ; türev sıçraması TAM c_b1·c_t3·Ω.

    SA-noft2 + SA-neg birleşiminin ölçülen bedeli budur (TMR'nin sayfadan
    kaldırdığı uyarının gerçek içeriği). Sağ/sol türev oranı ayrıca
    1/(1 − c_t3) = −5 kapalı formundadır.
    """
    rho, mu, omega, d = 1.0, 1.5e-5, 1000.0, 1.0e-3

    def kaynak(x):
        return float(sa.sa_source_terms(
            np.array(rho), np.array(x), np.array(mu), np.array(omega),
            np.array(d)).source)
    # C⁰: iki taraf da sıfıra gider
    assert abs(kaynak(+1e-14)) < 1e-11 and abs(kaynak(-1e-14)) < 1e-11
    assert kaynak(0.0) == 0.0
    h = 1e-9
    sag = (kaynak(h) - kaynak(0.0)) / h
    sol = (kaynak(0.0) - kaynak(-h)) / h
    sicrama = sag - sol
    kapali = sa.SA_C_B1 * sa.SA_C_T3 * omega
    assert abs(sicrama - kapali) / kapali < 1e-4, (
        f'kırık {sicrama!r}, kapalı form {kapali!r}')
    assert abs(sag / sol + 5.0) < 1e-3      # 1/(1 − c_t3) = −5
    assert sag > 0.0 > sol                  # yön: iki dal ters eğimli


def test_negatifte_eddy_viskozitesi_sifir_ve_kutupta_NaN_yok():
    """ν̃ < 0 → μ_t = 0; f_v1'in χ = −c_v1 kutbu ASLA değerlendirilmez."""
    x = np.array([-2.0 * sa.SA_C_V1, -sa.SA_C_V1, -3.0, -1e-30, 0.0,
                  3.0, 5.0, 1e4])
    nu = 1.5e-5
    mu_t = sa.turbulent_viscosity(np.ones_like(x), x * nu,
                                  np.full_like(x, nu))
    assert np.all(np.isfinite(mu_t)), 'kutupta NaN/inf sızdı'
    assert np.all(mu_t[x <= 0.0] == 0.0)
    assert np.all(mu_t[x > 0.0] > 0.0)
    # f_n de aynı biçimde güvenli (χ = c_n1^(1/3) kutbu pozitif dalda)
    x2 = np.array([-5.0, -1.0, 0.0, sa.SA_C_N1 ** (1.0 / 3.0), 10.0])
    assert np.all(np.isfinite(sa.f_n(x2)))
    assert np.all(sa.f_n(x2[x2 >= 0.0]) == 1.0)


# ===========================================================================
# 4) Değiştirilmiş girdaplılık yaması (ICCFD7-1902 Denklem 12)
# ===========================================================================

#: Yama vakası: χ = 5'te f_v2 NEGATİFTİR (Note 1'in var oluş sebebi) →
#: S̄ < 0 doğal olarak doğar; yamayı Ω'yı değiştirerek yokluyoruz.
YAMA_NU = 1.5e-5
YAMA_D = 1.0e-3
YAMA_NU_TILDE = 5.0 * YAMA_NU


def _s_bar(nu_tilde, nu=YAMA_NU, d=YAMA_D):
    """S̄ = ν̃f_v2(χ)/(κ²d²) — f_v2 modülün KENDİ fonksiyonu."""
    return float(nu_tilde * sa.f_v2(np.array(nu_tilde / nu))
                 / (sa.SA_KAPPA ** 2 * d ** 2))


def _s_tilde(omega, nu_tilde=YAMA_NU_TILDE):
    return float(sa.modified_vorticity(np.array(omega), np.array(nu_tilde),
                                       np.array(YAMA_D), np.array(YAMA_NU)))


def test_fv2_negatif_olabiliyor_yamanin_var_olus_sebebi():
    """Note 1'in öncülü: f_v2 bir χ aralığında NEGATİFTİR (ölçülür).

    Yama olmasaydı S̃ = Ω + S̄ sıfıra/negatife düşebilirdi; bekçi hem
    öncülü (f_v2 < 0) hem işaret değişim noktasını kilitler.
    """
    x = np.logspace(-2, 3, 20001)
    fv2 = sa.f_v2(x)
    assert fv2.min() < -1.0, 'f_v2 hiç negatife düşmüyor — öncül yanlış'
    isaret_degisimi = x[np.argmax(fv2 < 0.0)]
    assert 1.0 < isaret_degisimi < 2.0, f'f_v2 işaret noktası {isaret_degisimi}'
    assert _s_bar(YAMA_NU_TILDE) < 0.0


def test_modified_vorticity_yama_noktasi_asimptot_ve_pozitiflik():
    """Yamanın üç yayımlanmış iddiası: S̃ > 0, yama = 0,3Ω, asimptot 0,1Ω."""
    s_bar = _s_bar(YAMA_NU_TILDE)
    assert s_bar < 0.0
    # Pozitiflik: Ω çok küçükten çok büyüğe — S̃ HİÇBİR yerde ≤ 0 olmaz
    omegalar = np.logspace(-6, 12, 20001)
    s_t = sa.modified_vorticity(omegalar, np.full_like(omegalar,
                                                       YAMA_NU_TILDE),
                                np.full_like(omegalar, YAMA_D),
                                np.full_like(omegalar, YAMA_NU))
    assert np.all(s_t > 0.0), 'S̃ pozitifliği kırıldı (Ω > 0)'
    # Yamasız biçim AYNI vakada sıfırın altına düşerdi (yamanın ısırığı)
    assert np.min(omegalar + s_bar) < 0.0
    # Yama noktası: S̄ = −c_v2Ω ⇒ S̃ = (1 − c_v2)Ω
    omega_yama = -s_bar / sa.SA_C_V2
    assert abs(_s_tilde(omega_yama) / omega_yama
               - (1.0 - sa.SA_C_V2)) < 1e-12
    # Asimptot: S̄/Ω → −∞ ⇒ S̃/Ω → (1 − c_v3)
    kucuk = omega_yama * 1e-9
    assert abs(_s_tilde(kucuk) / kucuk - (1.0 - sa.SA_C_V3)) < 1e-6
    # C¹: yama noktasında ν̃'ye göre tek yanlı türevler eşit (zincir kuralı
    # aynı çarpanı taşıdığından bu, S̄'ye göre C¹ ile denktir)
    h = 1e-6 * YAMA_NU_TILDE

    def tur(a, b):
        return (_s_tilde(omega_yama, b)
                - _s_tilde(omega_yama, a)) / h

    sol = tur(YAMA_NU_TILDE - 2 * h, YAMA_NU_TILDE - h)
    sag = tur(YAMA_NU_TILDE + h, YAMA_NU_TILDE + 2 * h)
    assert abs(sag - sol) / abs(sol) < 1e-4


def test_omega_sifirda_r_kelepcesi_ve_sonluluk():
    """Ω = 0 ⇒ S̃ = 0 ⇒ r = r_lim (TMR'nin sıfıra bölme koruması)."""
    d, nu = np.array(1.0e-3), np.array(1.5e-5)
    s_tilde = sa.modified_vorticity(np.array(0.0), np.array(0.0), d, nu)
    assert float(s_tilde) == 0.0
    r = sa.sa_r(np.array(0.0), s_tilde, d)
    assert float(r) == sa.SA_R_LIM
    assert np.isfinite(sa.f_w(r))
    # r kelepçesi ÜST sınırda da çalışır (çok büyük ν̃)
    r2 = sa.sa_r(np.array(1.0), np.array(1e-30), d)
    assert float(r2) == sa.SA_R_LIM


def test_girdaplilik_dogrusal_kaymada_analitik():
    """Ω = |∂u_z/∂r − ∂u_r/∂z| — doğrusal kaymada tam a."""
    a = 1234.5
    g_uz = np.zeros((3, 4, 2))
    g_uz[..., 1] = a
    g_ur = np.zeros((3, 4, 2))
    assert np.allclose(sa.vorticity_magnitude(g_uz, g_ur), a, rtol=0, atol=0)
    # Katı-cisim dönmesi benzeri: ∂u_r/∂z = a ⇒ işaret farkı ölçülür
    g_ur[..., 0] = a
    assert np.allclose(sa.vorticity_magnitude(g_uz, g_ur), 0.0)


# ===========================================================================
# 5) Alan operatörleri
# ===========================================================================

def test_duzgun_alan_bit_sifir():
    """Düzgün ν̃ + düzgün akış → difüzyon ve taşınım TAM sıfır (bit)."""
    g = pipe()
    gg = precompute_gradient_geometry(g)
    rho = np.full((g.ni, g.nj), 1.2)
    mu = np.full((g.ni, g.nj), SA_MU)
    nu_tilde = np.full((g.ni, g.nj), 4.0e-5)
    bc = BoundaryFaceValues(i_lo=np.full(g.nj, 4.0e-5),
                            i_hi=np.full(g.nj, 4.0e-5),
                            j_lo=np.full(g.ni, 4.0e-5),
                            j_hi=np.full(g.ni, 4.0e-5))
    difuzyon = sa.sa_diffusive_residual(g, nu_tilde, rho, mu, bc=bc,
                                        grad_geom=gg)
    assert np.array_equal(difuzyon, np.zeros((g.ni, g.nj)))
    uz = np.full((g.ni, g.nj), 100.0)
    mf_i, mf_j = sa.face_mass_flux(g, rho, uz, np.zeros_like(uz),
                                   grad_geom=gg)
    net_kutle = ((mf_i[1:] - mf_i[:-1]) + (mf_j[:, 1:] - mf_j[:, :-1]))
    assert np.max(np.abs(net_kutle)) == 0.0
    tasinim = sa.sa_convective_residual(g, nu_tilde, mf_i, mf_j, bc=bc)
    assert np.array_equal(tasinim, np.zeros((g.ni, g.nj)))


def test_difuzyon_dogrusal_alanda_analitik_akiyla_ayni():
    """ν̃ = a·r, ρ ve μ sabit → akı toplamı KAPALI FORMLA aynı.

    Boruda yalnız j-yüzleri katkı verir; kapalı form
        (2πaΔz/σ)[Γ(r_üst)r_üst − Γ(r_alt)r_alt] + (c_b2/σ)ρa²V,
    Γ(r) = μ + ρar. Bu bekçi yüz değeri, yüz gradyanı, Γ'nın yüzde
    kurulması ve dönel alanın 2πr çarpanını BİRLİKTE kilitler.
    """
    g = pipe(ni=10, nj=6)
    gg = precompute_gradient_geometry(g)
    a = 3.0
    rho0, mu0 = 1.2, SA_MU
    rho = np.full((g.ni, g.nj), rho0)
    mu = np.full((g.ni, g.nj), mu0)
    nu_tilde = a * g.r_centers
    bc = yuz_bc(g, lambda z, r: a * r)
    olculen = sa.sa_diffusive_residual(g, nu_tilde, rho, mu, bc=bc,
                                       grad_geom=gg)
    r_lo, r_hi = g.R[:-1, :-1], g.R[:-1, 1:]
    dz = g.Z[1:, :-1] - g.Z[:-1, :-1]

    def gam(r):
        return mu0 + rho0 * a * r

    analitik = ((2.0 * np.pi * a * dz / sa.SA_SIGMA)
                * (gam(r_hi) * r_hi - gam(r_lo) * r_lo)
                + (sa.SA_C_B2 / sa.SA_SIGMA) * rho * a ** 2 * g.volume)
    assert np.max(np.abs(olculen - analitik) / np.abs(analitik)) < 1e-12


def _yogunluk_vakasi(ni, nj=6, L=0.30, Rw=0.02):
    """Süpersonik sınıfı yoğunluk düşüşü + doğrusal ν̃ (kapalı formlu)."""
    g = build_grid_from_wall(np.linspace(0.0, L, ni + 1),
                             np.full(ni + 1, Rw), nj)
    a, nu0, mu0 = 3.3e-3, 1.0e-4, 8.0e-5
    z = g.z_centers
    rho = 5.0 * np.exp(-np.log(10.0) * z / L)      # 5 → 0,5 kg/m³
    mu = np.full_like(z, mu0)
    nu_tilde = a * z + nu0
    bc = yuz_bc(g, lambda zz, rr: a * zz + nu0)
    rho_p = -np.log(10.0) / L * rho
    # ρ × (korunumsuz SA difüzyonu) — ICCFD7-1902'nin standart biçimi
    analitik = (rho / sa.SA_SIGMA) * (a * a - a * mu0 * rho_p / rho ** 2) \
        + (sa.SA_C_B2 / sa.SA_SIGMA) * rho * a * a
    return g, rho, mu, nu_tilde, bc, analitik


def test_yogunluk_gradyani_terimi_olmadan_YAKINSAMAZ():
    """ρ'yu türev İÇİNE almak (belge §5.5 yazımı) MODEL hatasıdır.

    Doğru biçim (Denklem 9, ∇ρ düzeltmeli) analitiğe ikinci mertebeden
    yakınsar; düzeltmesiz biçim ızgara inceltmesiyle YAKINSAMAZ — hata
    3,5e-05'te oturur. Ayrıklaştırma hatası ile MODEL hatasını ayıran
    kanıt budur.
    """
    hata_tam, hata_eksik = [], []
    for ni in (40, 80, 160, 320):
        g, rho, mu, nu_tilde, bc, analitik = _yogunluk_vakasi(ni)
        ic = slice(2, -2)
        for bayrak, kova in ((True, hata_tam), (False, hata_eksik)):
            R = sa.sa_diffusive_residual(
                g, nu_tilde, rho, mu, bc=bc,
                density_correction=bayrak) / g.volume
            kova.append(float(np.sqrt(np.mean((R - analitik)[ic] ** 2))))
    mertebe = [np.log2(hata_tam[i] / hata_tam[i + 1])
               for i in range(len(hata_tam) - 1)]
    assert all(1.8 < m < 2.2 for m in mertebe), (
        f'doğru biçim ikinci mertebeden yakınsamıyor: {mertebe}')
    # Düzeltmesiz biçim OTURUR: en ince ızgarada hata en kaba ızgaranın
    # %90'ından fazla (yani inceltme derdi çözmüyor)
    assert hata_eksik[-1] > 0.9 * hata_eksik[0]
    assert hata_eksik[-1] / hata_tam[-1] > 1.0e4


def test_yogunluk_gradyani_teriminin_buyuklugu_olculur():
    """İhmal edilen terim küçük DEĞİL: tam difüzyonun %85'i (ölçüldü)."""
    g, rho, mu, nu_tilde, bc, _ = _yogunluk_vakasi(160)
    tam = sa.sa_diffusive_residual(g, nu_tilde, rho, mu, bc=bc) / g.volume
    eksik = sa.sa_diffusive_residual(g, nu_tilde, rho, mu, bc=bc,
                                     density_correction=False) / g.volume
    oran = np.abs(eksik - tam) / np.abs(tam)
    assert 0.7 < float(np.mean(oran)) < 1.0
    assert float(np.max(oran)) > 1.0        # yer yer terimin KENDİSİNDEN büyük


def _tasinim_hatasi(ni, scheme, fonk, turev, kes=2):
    g = build_grid_from_wall(np.linspace(0.0, 0.05, ni + 1),
                             np.full(ni + 1, 0.005), 4)
    rho = np.full((g.ni, g.nj), 1.2)
    uz = np.full((g.ni, g.nj), 100.0)
    mf_i, mf_j = sa.face_mass_flux(g, rho, uz, np.zeros_like(uz))
    phi = fonk(g.z_centers)
    bc = BoundaryFaceValues(i_lo=fonk(np.zeros(g.nj)),
                            i_hi=fonk(np.full(g.nj, 0.05)))
    R = sa.sa_convective_residual(g, phi, mf_i, mf_j, bc=bc,
                                  scheme=scheme) / g.volume
    analitik = -1.2 * 100.0 * turev(g.z_centers)
    return float(np.sqrt(np.mean(((R - analitik)[kes:-kes]) ** 2)))


def test_tasinim_mertebesi_upwind1_bir():
    """Birinci mertebe upwind gerçekten BİRİNCİ mertebe (iç bölge)."""
    L = 0.05

    def fonk(z):
        return 1e-5 * (2.0 + np.sin(2 * np.pi * z / L))

    def turev(z):
        return 1e-5 * (2 * np.pi / L) * np.cos(2 * np.pi * z / L)

    h = [_tasinim_hatasi(n, 'upwind1', fonk, turev) for n in (20, 40, 80, 160)]
    mertebe = [np.log2(h[i] / h[i + 1]) for i in range(len(h) - 1)]
    assert all(0.95 < m < 1.10 for m in mertebe), f'mertebe {mertebe}'


def test_muscl_ikinci_mertebe_kazanci_olculur():
    """MUSCL'ün kazancı ÖLÇÜLÜR: kuadratikte TAM, sinüste 1,5 mertebe.

    minmod pürüzsüz EKSTREMUMU kırpar; bu yüzden sinüs profilinde L2
    mertebesi 2 değil ~1,5'tir. Tekdüze kuadratik profilde ise yeniden
    kurma TAM olur (makine hassasiyeti) — ikinci mertebenin ν̃ akısı
    üstündeki etkisinin dürüst ölçüsü budur.
    """
    L = 0.05

    def kare(z):
        return 1e-5 * (1.0 + 2.0 * z / L) ** 2

    def kare_t(z):
        return 1e-5 * 2 * (1.0 + 2.0 * z / L) * (2.0 / L)

    for n in (20, 80):
        assert _tasinim_hatasi(n, 'muscl2', kare, kare_t) < 1e-12
        assert _tasinim_hatasi(n, 'upwind1', kare, kare_t) > 1e-4

    def sin(z):
        return 1e-5 * (2.0 + np.sin(2 * np.pi * z / L))

    def sin_t(z):
        return 1e-5 * (2 * np.pi / L) * np.cos(2 * np.pi * z / L)

    h = [_tasinim_hatasi(n, 'muscl2', sin, sin_t) for n in (20, 40, 80, 160)]
    mertebe = [np.log2(h[i] / h[i + 1]) for i in range(len(h) - 1)]
    assert all(1.40 < m < 1.75 for m in mertebe), f'mertebe {mertebe}'
    # Aynı ızgarada MUSCL upwind'den ölçülebilir biçimde iyi
    oran = (_tasinim_hatasi(160, 'upwind1', sin, sin_t)
            / _tasinim_hatasi(160, 'muscl2', sin, sin_t))
    assert oran > 5.0, f'MUSCL kazancı {oran!r}'


def test_upwind_yonu_yukari_akistan_alir():
    """Yukarı-akış YÖNÜ: BASAMAK profiliyle ölçülür (doğrusal profil KÖRDÜR).

    ÖNEMLİ (ölçülen tuzak): doğrusal ν̃ profilinde φ_i − φ_{i−1} =
    φ_{i+1} − φ_i olduğundan yukarı-akış yönünü ters çevirmek kalıntıyı
    DEĞİŞTİRMEZ — böyle bir bekçi mutasyonu göremez (ilk turda ölçüldü:
    yön mutasyonu 37 testin hiçbirini kırmadı). Basamak profilinde ise
    etkilenen hücre yönü SÖYLER: +z akışında kalıntı yalnız basamağın
    HEMEN ARDINDAKİ hücrede doğar.
    """
    g = pipe(ni=8, nj=4)
    i0 = 5
    basamak = np.zeros((g.ni, g.nj))
    basamak[i0:] = 1.0
    mf_i = np.ones((g.ni + 1, g.nj))
    mf_j = np.zeros((g.ni, g.nj + 1))

    ileri = sa.sa_convective_residual(g, basamak, mf_i, mf_j)
    sifir_disi = np.flatnonzero(np.any(np.abs(ileri) > 0.0, axis=1))
    assert sifir_disi.tolist() == [i0], (
        f'+z akışında etkilenen hücre {sifir_disi.tolist()}, beklenen [{i0}]')
    assert np.allclose(ileri[i0], -1.0)      # −ṁ(φ_i − φ_{i−1})

    geri = sa.sa_convective_residual(g, basamak, -mf_i, mf_j)
    sifir_disi_g = np.flatnonzero(np.any(np.abs(geri) > 0.0, axis=1))
    assert sifir_disi_g.tolist() == [i0 - 1], (
        f'−z akışında etkilenen hücre {sifir_disi_g.tolist()}, '
        f'beklenen [{i0 - 1}]')
    assert np.allclose(geri[i0 - 1], +1.0)

    # Tekdüzelik: birinci mertebe upwind YENİ ekstremum üretmez
    yeni = basamak + 0.4 * ileri
    assert yeni.min() >= basamak.min() - 1e-15
    assert yeni.max() <= basamak.max() + 1e-15


def test_muscl_yonu_de_yukari_akistan(monkeypatch):
    """MUSCL dalı da yukarı-akıştan kurar (aynı basamak ölçütü).

    İkinci mertebe kolunun yönü ayrı bekçilenir: sınırlayıcı basamağın
    iki yanında eğimi sıfırlar, bu yüzden etkilenen hücre kümesi birinci
    mertebeyle AYNI kalmalıdır. Yön mutasyonu bu kümeyi kaydırır.
    """
    g = pipe(ni=8, nj=4)
    i0 = 5
    basamak = np.zeros((g.ni, g.nj))
    basamak[i0:] = 1.0
    mf_i = np.ones((g.ni + 1, g.nj))
    mf_j = np.zeros((g.ni, g.nj + 1))
    R = sa.sa_convective_residual(g, basamak, mf_i, mf_j, scheme='muscl2')
    sifir_disi = np.flatnonzero(np.any(np.abs(R) > 1e-15, axis=1))
    assert sifir_disi.tolist() == [i0]
    assert np.allclose(R[i0], -1.0)


# ===========================================================================
# 6) Sınır koşulları ve sözleşme
# ===========================================================================

def test_sinir_kosullari_duvar_sifir_cikis_disdegerleme():
    """Duvarda ν̃ = 0 (Dirichlet), çıkışta dışdeğerleme, girişte bant."""
    g = pipe(ni=5, nj=4)
    bc = sa.sa_boundary_face_values(g, inlet_nu_tilde=4.5e-5)
    assert np.array_equal(bc.j_hi, np.zeros(g.ni))
    assert bc.j_lo is None                      # eksen: Neumann (çift)
    assert bc.i_hi is None                      # çıkış: dışdeğerleme
    assert np.array_equal(bc.i_lo, np.full(g.nj, 4.5e-5))
    bos = sa.sa_boundary_face_values(g)
    assert bos.i_lo is None


def test_eksen_ciftligi_ve_duvar_sifir_kalintida():
    """Tam kalıntıda: duvar yüz değeri sıfır, eksende ∂ν̃/∂n ≈ 0."""
    g = pipe(ni=10, nj=8)
    U = sabit_alan(g)
    nu_tilde = np.full((g.ni, g.nj), 3.0e-5)
    omega = np.zeros((g.ni, g.nj))
    dudt, aux = sa.sa_residual(g, U, transport(), R=SA_R, nu_tilde=nu_tilde,
                               omega=omega, inlet_nu_tilde=3.0e-5)
    assert np.all(np.isfinite(dudt))
    # Duvara komşu hücrede ν̃ = 0 yüzüne difüzyon SIZMASI olmalı (negatif
    # katkı: ν̃ duvara akıyor), eksende ise net sıfıra yakın olmalı.
    assert np.all(aux['diffusive'][:, -1] < 0.0)
    assert np.max(np.abs(aux['diffusive'][:, 0])) < 1e-6 * np.max(
        np.abs(aux['diffusive'][:, -1]))
    assert aux['declaration']['axis_neumann_update'] >= 0.0


def test_fiziksel_olmayan_durum_NaN_istisna_yok():
    """SA kalıntısı da NaN döndürür — viscous.py ile ORTAK ölçüt."""
    g = pipe()
    U = sabit_alan(g)
    U[3, 2, 0] = -1.0                       # negatif yoğunluk
    nu_tilde = np.full((g.ni, g.nj), 3.0e-5)
    dudt, aux = sa.sa_residual(g, U, transport(), R=SA_R, nu_tilde=nu_tilde,
                               omega=np.zeros((g.ni, g.nj)))
    assert np.all(np.isnan(dudt))
    assert 'nonphysical_state' in aux['declaration']
    # ν̃ sonlu değilse de aynı yol
    U2 = sabit_alan(g)
    kotu = np.full((g.ni, g.nj), 3.0e-5)
    kotu[1, 1] = np.nan
    dudt2, aux2 = sa.sa_residual(g, U2, transport(), R=SA_R, nu_tilde=kotu,
                                 omega=np.zeros((g.ni, g.nj)))
    assert np.all(np.isnan(dudt2))
    assert 'nonphysical_state' in aux2['declaration']
    # aux ANAHTAR KÜMESİ sağlam yolla aynı olmalı: çağıran hata yolunda
    # başka biçimli bir sözlükle karşılaşmaz (sessiz KeyError kaynağı)
    _, saglam = sa.sa_residual(g, sabit_alan(g), transport(), R=SA_R,
                               nu_tilde=np.full((g.ni, g.nj), 3.0e-5),
                               omega=np.zeros((g.ni, g.nj)))
    assert set(aux) == set(saglam)
    assert set(aux['source']._fields) == set(saglam['source']._fields)


def test_negatif_nu_tilde_fiziksel_olmayan_SAYILMAZ():
    """ν̃ < 0 modelin dalıdır: kalıntı SONLU döner, NaN değil."""
    g = pipe(ni=8, nj=6)
    U = sabit_alan(g)
    nu_tilde = np.full((g.ni, g.nj), 3.0e-5)
    nu_tilde[4, 2] = -1.0e-5
    dudt, aux = sa.sa_residual(g, U, transport(), R=SA_R, nu_tilde=nu_tilde,
                               omega=np.full((g.ni, g.nj), 100.0))
    assert np.all(np.isfinite(dudt))
    assert aux['negative_cell_count'] == 1
    assert aux['mu_t'][4, 2] == 0.0         # negatif hücrede μ_t = 0
    assert np.all(aux['mu_t'] >= 0.0)


def test_bicim_ve_sema_kapilari():
    """Sözleşme ihlalleri gerekçeli ValueError ile reddedilir."""
    g = pipe(ni=6, nj=4)
    U = sabit_alan(g)
    nu_tilde = np.full((g.ni, g.nj), 3.0e-5)
    omega = np.zeros((g.ni, g.nj))
    with pytest.raises(ValueError, match=r'scheme'):
        sa.sa_convective_residual(g, nu_tilde, np.zeros((g.ni + 1, g.nj)),
                                  np.zeros((g.ni, g.nj + 1)), scheme='qwerty')
    with pytest.raises(ValueError, match=r'mass_flux_i biçimi'):
        sa.sa_convective_residual(g, nu_tilde, np.zeros((g.ni, g.nj)),
                                  np.zeros((g.ni, g.nj + 1)))
    with pytest.raises(ValueError, match=r'nu_tilde biçimi'):
        sa.sa_residual(g, U, transport(), R=SA_R, nu_tilde=nu_tilde[:-1],
                       omega=omega)
    with pytest.raises(ValueError, match=r'omega biçimi'):
        sa.sa_residual(g, U, transport(), R=SA_R, nu_tilde=nu_tilde,
                       omega=omega[:-1])
    with pytest.raises(ValueError, match=r'U biçimi'):
        sa.sa_residual(g, U[:-1], transport(), R=SA_R, nu_tilde=nu_tilde,
                       omega=omega)
    with pytest.raises(ValueError, match=r'Duvar mesafesi d'):
        sa.sa_source_terms(np.array(1.0), np.array(1e-5), np.array(1e-5),
                           np.array(1.0), np.array(0.0))


def test_beyan_alanlari_kosumda_gorunur():
    """Beyan: şema, ∇ρ terimi, yok etme işlemi, künye, NOT_MODELLED."""
    g = pipe(ni=6, nj=4)
    _, aux = sa.sa_residual(g, sabit_alan(g), transport(), R=SA_R,
                            nu_tilde=np.full((g.ni, g.nj), 3.0e-5),
                            omega=np.zeros((g.ni, g.nj)))
    d = aux['declaration']
    assert d['convection_scheme'] == 'upwind1'
    assert d['density_correction_term'] is True
    assert d['destruction_treatment'].startswith('point-implicit')
    assert d['production_treatment'] == 'explicit'
    assert 'ICCFD7-1902' in d['modified_vorticity_limiter']
    assert 'transition' in d['not_modelled']
    assert d['constants']['c_w1'] == sa.SA_C_W1
    assert 'wall_distance_field' in d['wall_distance_source']


def test_kalinti_bilesenlerinin_toplami():
    """dudt = (taşınım + difüzyon)/V + kaynak — parçalar ayrı yayımlanıyor."""
    g = pipe(ni=8, nj=6)
    U = sabit_alan(g)
    nu_tilde = 3.0e-5 + 1.0e-5 * np.sin(6.0 * g.z_centers / 0.05)
    omega = np.full((g.ni, g.nj), 500.0)
    dudt, aux = sa.sa_residual(g, U, transport(), R=SA_R, nu_tilde=nu_tilde,
                               omega=omega, inlet_nu_tilde=3.0e-5)
    toplam = aux['convective'] + aux['diffusive'] + aux['source'].source
    assert np.allclose(dudt, toplam, rtol=0.0, atol=0.0)
    assert np.all(aux['wall_distance_m'] > 0.0)


# ===========================================================================
# 7) Nokta-örtük yok etme (§5.5 "yok etme nokta-örtük")
# ===========================================================================

def _duvar_dibi_hucre():
    """d = 0,4 µm duvar hücresi (belge §5.5'in kendi sayısı)."""
    rho, mu, d = np.array(0.5), np.array(7.0e-5), np.array(4.0e-7)
    u_tau = 30.0
    omega = np.array(u_tau / (sa.SA_KAPPA * float(d)))
    return rho, mu, d, omega, sa.SA_KAPPA * u_tau * float(d)


def _sifir_boyutlu_kos(dt, ortuk, adim=400, baslangic=3.0):
    rho, mu, d, omega, nu_denge = _duvar_dibi_hucre()
    q = np.array(rho * nu_denge * baslangic)
    with np.errstate(over='ignore', invalid='ignore'):
        for _ in range(adim):
            s = sa.sa_source_terms(rho, q / rho, mu, omega, d)
            kosegen = s.jacobian_diag if ortuk else np.zeros_like(
                s.jacobian_diag)
            q = q + sa.sa_point_implicit_delta(dt, s.source, kosegen)
            if not np.isfinite(q):
                return np.nan
    return float(q / rho)


def test_nokta_ortuk_yok_etme_kararlilik_isirigi():
    """Açık yol büyük Δt'de IRAKSAR; örtük yol 40×(2/J)'de bile yakınsar.

    V3 YENİDEN ÖLÇÜMÜ (tam analitik köşegen): J = 2,0833e7 1/s ve DENGE
    NOKTASINDA gerçek eğimin ta kendisidir (merkezî FD −2,083303e7 ↔ J,
    bağıl fark < 1e-6 — aşağıda ölçülür). Eski (yalnız donmuş yok etme)
    köşegen 7,2192e7 veriyordu: bu noktada üretim türevi POZİTİF olduğu
    için eski köşegen 3,47 kat FAZLA sönümdü. 2/J artık gerçek doğrusal
    sınırdır; ν̃ = 3ν̃* başlangıçlı geçiş rejimi daha dik olduğundan
    (bandda maks J⁻ = 5,02e8 ölçüldü) açık yol 0,5·(2/J)'de bile ıraksar,
    0,05·(2/J)'de yaşar (ölçüldü: 1,4e-8 s sonlu, 1,6e-8 s NaN).
    """
    rho, mu, d, omega, nu_denge = _duvar_dibi_hucre()
    s = sa.sa_source_terms(rho, np.array(nu_denge), mu, omega, d)
    jac = float(s.jacobian_diag)
    # ÖLÇÜLDÜ (V3): 2,0833e7 1/s. Eşik ölçümün yarısı — mertebe kilitli.
    assert jac > 1.0e7, f'duvar dibinde Jacobian ölçüsü {jac!r}'
    # Köşegen artık DENGE noktasındaki GERÇEK eğimdir (donmuş katsayı yok)
    h = 1e-6 * nu_denge
    fd = (float(sa.sa_source_terms(rho, np.array(nu_denge + h), mu, omega,
                                   d).source)
          - float(sa.sa_source_terms(rho, np.array(nu_denge - h), mu, omega,
                                     d).source)) / (2.0 * h * float(rho))
    assert abs(jac + fd) / jac < 1e-6, (
        f'köşegen {jac!r} gerçek eğimin (−{fd!r}) negatif kısmı değil')
    dt_sinir = 2.0 / jac
    # Açık: derin altında yaşıyor, yarısında/üstünde ölüyor (geçiş rejimi)
    assert np.isfinite(_sifir_boyutlu_kos(0.05 * dt_sinir, ortuk=False))
    assert not np.isfinite(_sifir_boyutlu_kos(0.5 * dt_sinir, ortuk=False))
    assert not np.isfinite(_sifir_boyutlu_kos(1.0 * dt_sinir, ortuk=False))
    assert not np.isfinite(_sifir_boyutlu_kos(40.0 * dt_sinir, ortuk=False))
    # Örtük: hepsinde sonlu VE aynı kök
    kokler = [_sifir_boyutlu_kos(k * dt_sinir, ortuk=True)
              for k in (0.5, 1.0, 4.0, 40.0)]
    assert all(np.isfinite(k) for k in kokler)
    assert max(kokler) - min(kokler) < 1e-9 * max(kokler), (
        f'örtük yol Δt ile CEVABI değiştiriyor: {kokler}')


def test_nokta_ortuk_cevabi_degistirmez():
    """Hüküm-nötrlük: açık (küçük Δt) ve örtük (büyük Δt) AYNI köke gider."""
    rho, mu, d, omega, nu_denge = _duvar_dibi_hucre()
    jac = float(sa.sa_source_terms(rho, np.array(nu_denge), mu, omega,
                                   d).jacobian_diag)
    acik = _sifir_boyutlu_kos(0.05 * 2.0 / jac, ortuk=False, adim=4000)
    ortuk = _sifir_boyutlu_kos(20.0 * 2.0 / jac, ortuk=True, adim=400)
    assert abs(acik - ortuk) / ortuk < 1e-6, f'{acik!r} ↔ {ortuk!r}'


def _donmus_yok_etme_kosegeni(rho, nu_tilde, mu, omega, d):
    """ESKİ köşegen (V3 öncesi): donmuş f_w'li yok etme türevi 2c_w1f_wν̃/d².

    Bu işlev, kapatılan kusurun ÖLÇÜSÜ olarak testte durur (modelin kendi
    f_w/S̃/r işlevlerinden kurulur — ikinci değer tanımı yok); üretimde
    kullanılmaz. Mutasyon M8 (köşegeni buna geri düşürmek) aşağıdaki iki
    bekçiyi kırmızıya düşürür.
    """
    nu_pos = np.maximum(np.asarray(nu_tilde, dtype=float), 0.0)
    nu = np.asarray(mu, dtype=float) / np.asarray(rho, dtype=float)
    s_tilde = sa.modified_vorticity(omega, nu_pos, d, nu)
    fw = sa.f_w(sa.sa_r(nu_pos, s_tilde, d))
    return 2.0 * sa.SA_C_W1 * fw * nu_pos / np.asarray(d, dtype=float) ** 2


def test_jacobian_kosegeni_TAM_analitik_turev():
    """Köşegen = TAM analitik ∂(P−D)/∂(ρν̃)'nın negatif kısmı (V3).

    Bekçi üç şeyi ölçer:
      (a) yayımlanan köşegen, kaynağın MERKEZÎ sonlu-fark türevinin
          negatif kısmıyla eşleşir (duvar dibi hücre; bağıl < 1e-6),
      (b) eski (donmuş yok etme) köşegenle FARK iki YÖNDE de ölçülüdür:
          duvar dibi hücrede (χ = 0,035, f_v2 > 0) üretim türevi POZİTİF
          → yeni köşegen eskisinden KÜÇÜK (ölçülen oran 0,2886); tampon
          hücrede (χ = 3, f_v2 < 0) üretim türevi NEGATİF → yeni köşegen
          eskisinden BÜYÜK (ölçülen oran 2,535). Tek yönlü bir bekçi
          "hep büyüt" mutasyonunu göremezdi,
      (c) köşegen negatif olamaz (max(−J, 0) kelepçesi).
    """
    rho, mu, d, omega, nu_denge = _duvar_dibi_hucre()
    q0 = float(rho) * nu_denge
    s0 = sa.sa_source_terms(rho, np.array(nu_denge), mu, omega, d)
    # (a) merkezî FD çaprazı
    h = 1e-6 * q0
    tam = (float(sa.sa_source_terms(rho, np.array((q0 + h) / rho), mu, omega,
                                    d).source)
           - float(sa.sa_source_terms(rho, np.array((q0 - h) / rho), mu,
                                      omega, d).source)) / (2.0 * h)
    beklenen = max(-tam, 0.0)
    assert beklenen > 0.0
    assert abs(float(s0.jacobian_diag) - beklenen) / beklenen < 1e-6, (
        f'köşegen {float(s0.jacobian_diag)!r} ↔ FD {beklenen!r}')
    assert float(s0.jacobian_diag) > 0.0
    # (b1) duvar dibi (χ = 0,035): üretim türevi pozitif → yeni < eski
    eski = float(_donmus_yok_etme_kosegeni(rho, np.array(nu_denge), mu,
                                           omega, d))
    oran_duvar = float(s0.jacobian_diag) / eski
    assert 0.2 < oran_duvar < 0.4, (
        f'duvar dibi yeni/eski = {oran_duvar!r} (ölçülen 0,2886) — üretim '
        'türevinin pozitif payı kayboldu ya da köşegen eskiye döndü')
    # (b2) tampon tabaka kökü (χ = 3; Ω, kaynak sıfırlanacak biçimde
    # ölçülüp yazıldı — betik p39_a1): üretim türevi NEGATİF ve baskın
    rho_t = np.array(1.0)
    mu_t = np.array(2.0e-5)
    d_t = np.array(2.0e-5)
    om_t = np.array(2.8399e6)
    nu_t = 3.0 * float(mu_t / rho_t)
    s_t = sa.sa_source_terms(rho_t, np.array(nu_t), mu_t, om_t, d_t)
    eski_t = float(_donmus_yok_etme_kosegeni(rho_t, np.array(nu_t), mu_t,
                                             om_t, d_t))
    oran_tampon = float(s_t.jacobian_diag) / eski_t
    assert 2.0 < oran_tampon < 3.2, (
        f'tampon yeni/eski = {oran_tampon!r} (ölçülen 2,535) — f_v2 < 0 '
        'bölgesinin üretim türevi köşegene taşınmıyor')


def test_jacobian_kosegeni_FD_taramasi_iki_dal():
    """Yayımlanan köşegen ↔ merkezî FD: 4000 rastgele durumda çapraz.

    Dal sınırlarının komşuluğu (ν̃ ≈ 0 kırığı, Denklem 12 yama anahtarı,
    r_lim kelepçesi) FD'nin kırığa basmaması için elenir — kalan her
    noktada tam eşleşme aranır. Kalibrasyon (20 000 nokta, betik
    p39_a1_jac_prototip): maks bağıl 1,8e-08, ortanca 2e-11 → eşik 1e-6
    (~50× pay). Mutasyon M8 (donmuş yok etmeye dönüş) burada kırmızı.
    """
    rng = np.random.default_rng(7)
    n = 4000
    rho = rng.uniform(0.05, 5.0, n)
    mu = rng.uniform(1e-5, 2e-4, n)
    nu = mu / rho
    chi = rng.uniform(-3.0, 60.0, n)
    nu_tilde = chi * nu
    omega = 10.0 ** rng.uniform(0.0, 8.0, n)
    d = 10.0 ** rng.uniform(-7.0, -2.0, n)

    s = sa.sa_source_terms(rho, nu_tilde, mu, omega, d)
    h = 1e-6 * (np.abs(nu_tilde) + nu)
    fd = (sa.sa_source_terms(rho, nu_tilde + h, mu, omega, d).source
          - sa.sa_source_terms(rho, nu_tilde - h, mu, omega, d).source) \
        / (2.0 * h * rho)

    nu_pos = np.maximum(nu_tilde, 0.0)
    kap2d2 = sa.SA_KAPPA ** 2 * d ** 2
    s_bar = nu_pos * sa.f_v2(np.maximum(chi, 0.0)) / kap2d2
    s_tilde = sa.modified_vorticity(omega, nu_pos, d, nu)
    with np.errstate(divide='ignore'):
        ham_r = np.where(s_tilde > 0.0, nu_pos / (s_tilde * kap2d2), np.inf)
    kenar = ((np.abs(nu_tilde) < 1e-4 * nu)
             | (np.abs(s_bar + sa.SA_C_V2 * omega) < 1e-3 * omega)
             | (np.abs(ham_r - sa.SA_R_LIM) < 1e-3 * sa.SA_R_LIM))
    ic = ~kenar
    assert ic.sum() > 3500, 'kenar eleği örneklemin çoğunu yuttu'
    beklenen = np.maximum(-fd, 0.0)
    olcek = np.abs(beklenen) + np.abs(s.jacobian_diag) + 1e-30
    rel = np.abs(s.jacobian_diag - beklenen) / olcek
    assert float(rel[ic].max()) < 1e-6, (
        f'köşegen FD çaprazından koptu: maks bağıl {rel[ic].max():.3e}')


def test_tampon_tabakada_periyot2_salinim_OLDU():
    """Kapatılan kusurun ÖLÇÜSÜ: eski köşegen periyot-2, yenisi Newton.

    Tampon tabaka kökünde (χ* = 3; Ω kaynak kökünü oraya koyacak biçimde
    ölçüldü) gerçek eğim |s′| eski köşegenin 2,54 KATIDIR → büyük Δt'de
    nokta-örtük harita 1 + s′/J < −1 ile salınır. ÖLÇÜLDÜ (üç Δt, dört
    mertebe aralık): eski köşegenle son adım genliği/kök ≈ 0,48-0,50 ve
    Δt'DEN BAĞIMSIZ (parti 38'in levhada ölçtüğü imzanın kendisi); yeni
    (tam analitik) köşegenle |Δ| makine sıfırına iner. Salınım geri
    gelirse (köşegen üretim türevini kaybederse) bu bekçi kırmızıdır.
    """
    rho = np.array(1.0)
    mu = np.array(2.0e-5)
    d = np.array(2.0e-5)
    om = np.array(2.8399e6)
    nu_koku = 3.0 * float(mu / rho)

    def kos(dt, yeni_mi, adim=200, baslangic=1.15):
        q = np.array(float(rho) * nu_koku * baslangic)
        son_farklar = []
        with np.errstate(over='ignore', invalid='ignore'):
            for _ in range(adim):
                s = sa.sa_source_terms(rho, q / rho, mu, om, d)
                j = (s.jacobian_diag if yeni_mi
                     else _donmus_yok_etme_kosegeni(rho, q / rho, mu, om, d))
                q_yeni = q + sa.sa_point_implicit_delta(dt, s.source, j)
                if not np.isfinite(q_yeni):
                    return np.nan, np.nan
                son_farklar.append(abs(float(q_yeni - q)))
                q = q_yeni
        return float(q / rho), son_farklar[-1] / float(q)

    genlikler = []
    for dt_kat in (1e2, 1e4, 1e6):
        dt = dt_kat / 1.0446e6          # ölçülen |s′| ölçeğine göre büyük
        kok_yeni, gen_yeni = kos(dt, yeni_mi=True)
        kok_eski, gen_eski = kos(dt, yeni_mi=False)
        assert np.isfinite(kok_yeni)
        assert gen_yeni < 1e-12, (
            f'yeni köşegenle çevrim ölmedi: dt={dt:.1e}, genlik/kök '
            f'{gen_yeni:.3e}')
        assert abs(kok_yeni / nu_koku - 1.0) < 1e-4, (
            f'yeni köşegen kökü kaydırdı: {kok_yeni!r} ↔ {nu_koku!r}')
        assert gen_eski > 0.3, (
            f'eski köşegen salınmıyor (genlik/kök {gen_eski:.3e}) — '
            'kusur ölçüsü kayboldu, vaka değişmiş olabilir')
        genlikler.append(gen_eski)
    # Δt'den bağımsızlık (parti 38 imzası): dört mertebe Δt aralığında
    # genlik bandı dar (ölçülen 0,48-0,50)
    assert max(genlikler) / min(genlikler) < 1.2, (
        f'eski-köşegen salınım genliği Δt ile değişti: {genlikler}')


# ===========================================================================
# 8) DEVİR KUSURU #1'İN KAPANIŞI — viskoz/SA/Δt yollarının TEK sözleşmesi
#
# Defter satırı (docs/BULGU_KAYIT_DEFTERI.md, parti 37 A2 ölçümü):
# "viscous_residual NaN döner, viscous_spectral_radius AYNI durumda
#  gas_transport pozitiflik kapısından ValueError SIZDIRIYOR".
# Kapanışın şartı: üç yolu AYNI fiziksel-olmayan durumla BİRLİKTE ölçen
# bekçi. Ayrı ayrı ölçen bekçiler bu kusuru 37 parti boyunca görmedi.
# ===========================================================================

def _fiziksel_olmayan_kurulum():
    g = pipe(ni=10, nj=6)
    U = sabit_alan(g)
    U[3, 2, 0] = -1.0                       # negatif yoğunluk
    return g, U, transport()


def test_sozlesme_birlesimi_uc_yol_da_NaN_dondurur():
    """Kalıntı, spektral yarıçap ve Δt sınırı AYNI durumda AYNI davranır."""
    from hrma.cfd import viscous

    g, U, tr = _fiziksel_olmayan_kurulum()
    dudt, aux = viscous.viscous_residual(
        g, U, tr, R=SA_R, wall_thermal='adiabatic')
    assert np.all(np.isnan(dudt[..., 1:]))
    assert 'nonphysical_state' in aux['declaration']

    # ESKİDEN BURASI ValueError ATIYORDU (defter satırının kendisi)
    lam = viscous.viscous_spectral_radius(g, U, tr, R=SA_R)
    assert lam.shape == (g.ni, g.nj)
    assert np.all(np.isnan(lam))

    dt = viscous.viscous_local_dt_limit(g, U, tr, R=SA_R)
    assert np.all(np.isnan(dt))             # sürücünün Δt kapısının sinyali

    # SA kalıntısı da AYNI ölçütü kullanır (ortak sözleşme zinciri)
    dsa, aux_sa = sa.sa_residual(g, U, tr, R=SA_R,
                                 nu_tilde=np.full((g.ni, g.nj), 3e-5),
                                 omega=np.zeros((g.ni, g.nj)))
    assert np.all(np.isnan(dsa))
    assert 'nonphysical_state' in aux_sa['declaration']


def test_sozlesme_olcutu_TEK_yerde_tanimli():
    """Yapısal kanıt: iki yol da ``nonphysical_state``i GERÇEKTEN çağırır.

    Ölçüt bir yolda yeniden satır içine yazılırsa (ayrışmanın doğuş
    biçimi) casus çağrılmaz ve bu bekçi kırmızıya döner. Sağlıklı
    durumda ölçüt sağlam alanda da çağrılır — yani kapı HER çağrıda
    işletiliyor, yalnız hata yolunda değil.
    """
    from hrma.cfd import viscous

    g = pipe(ni=6, nj=4)
    U = sabit_alan(g)
    tr = transport()
    sayac = {'n': 0}
    gercek = viscous.nonphysical_state

    def casus(w):
        sayac['n'] += 1
        return gercek(w)

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(viscous, 'nonphysical_state', casus)
        viscous.viscous_residual(g, U, tr, R=SA_R, wall_thermal='adiabatic')
        assert sayac['n'] == 1, 'viscous_residual ölçütü çağırmadı'
        viscous.viscous_spectral_radius(g, U, tr, R=SA_R)
        assert sayac['n'] == 2, 'viscous_spectral_radius ölçütü çağırmadı'
    finally:
        mp.undo()
    # Ölçütün kendisi: ρ ≤ 0, p ≤ 0 ve sonlu olmayan → True; sağlam → False
    w = cons_to_prim_axisym(U, SA_GAMMA)
    assert viscous.nonphysical_state(w) is False
    for indis, deger in ((0, -1.0), (0, 0.0), (3, -1.0), (3, np.nan),
                         (1, np.inf)):
        bozuk = np.array(w, copy=True)
        bozuk[2, 2, indis] = deger
        assert viscous.nonphysical_state(bozuk) is True, (
            f'bileşen {indis} = {deger} yakalanmadı')


def test_nokta_ortuk_delta_acik_dala_iner():
    """J⁻ = 0 verilirse ifade TAM açık Euler adımıdır (mutasyon kancası)."""
    dt = np.array(1e-6)
    R = np.array(2.5)
    assert float(sa.sa_point_implicit_delta(dt, R, np.array(0.0))) == \
        float(dt * R)
    # J⁻ > 0 adımı KÜÇÜLTÜR (sönüm), işaretini değiştirmez
    kucuk = float(sa.sa_point_implicit_delta(dt, R, np.array(1e7)))
    assert 0.0 < kucuk < float(dt * R)
