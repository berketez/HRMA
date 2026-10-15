# tests/cfd — basamak 8: TÜRBÜLANSLI düz levha (SA-neg) + NASA TMR çaprazı
"""Merdiven basamağı 8: SA-neg'in c_f, log-yasası ve TMR doğrulama çaprazı.

VAKA — basamak 7'nin (laminer Blasius) türbülanslı ikizi
--------------------------------------------------------
Aynı "büyük yarıçaplı boru = düz levha" kurgusu (yeni geometri kodu yok),
yalnız Reynolds sayısı türbülanslı banda taşındı ve duvar ÇÖZÜLDÜ (y⁺ ≈ 1,
tanh gerdirmeli radyal dağılım — §5.7'nin V2 kalemi):

    R = 100 mm, L = 600 mm, u_e ≈ 219 m/s (M_e ≈ 0,20), T0 = 3000 K,
    P0 = 1 MPa, μ = 2,075e-05 Pa·s (sabit özellikli doğrulama akışkanı,
    üs 0), ADYABATİK duvar, Re_x = 7,4e4 … 6,8e6 (ölçüm penceresi
    2,4e6 … 6,6e6), ν̃_∞ = 3ν_∞.

Sürüş basamak 7'deki gibidir: giriş rezervuar (P0, T0) + çıkışta Pb; u_e
ikisinin izantropik farkından DOĞAR, dayatılmaz.

REFERANSLAR — üçü de KÜNYELİ, ikisi İNDİRİLDİ (18 Ağu 2026)
-----------------------------------------------------------
1. **NASA TMR doğrulama vakası (BİRİNCİL ÇAPRAZ).** "2D Zero Pressure
   Gradient Flat Plate Verification Case", NASA Turbulence Modeling
   Resource; SA sonuçları CFL3D (hücre-merkezli yapısal) ve FUN3D
   (düğüm-merkezli) ile, 5 ızgaralı seri, en ince 545×385. Vaka M = 0,2,
   birim uzunluk başına Re = 5e6, adyabatik duvar. TMR'nin larc.nasa.gov
   adresi bu tarihte NASA'nın tanıtım sayfasına yönlendiriyor; içerik
   GitHub Pages'e taşınmış: https://tmbwg.github.io/turbmodels/
   (flatplate.html, flatplate_sa.html ve ham veri dosyaları
   FlatPlate/SA/cf_convergence.dat + FlatPlate/SA/cf_plate.dat).
   Aşağıdaki referans sayıları O DOSYALARDAN alınmıştır (uydurma yok;
   iki dosya birbirini doğruluyor: cf_plate.dat'ın Re_x = 4,8504e6'daki
   ara değeri 2,705622e-03, cf_convergence.dat'ın aynı istasyondaki
   en ince ızgara değeriyle BİREBİR aynı).
2. **Korelasyon bandı.** c_f = 0,0592·Re_x^(−0,2) (1/7 kuvvet yasası;
   Schlichting & Gersten, *Boundary-Layer Theory*, 9. baskı, §18.2.5 —
   depoda ikinci bir tanımı YOKTUR, bu dosyada yalnız REFERANS olarak
   yazılır, çözücü zincirinde kullanılmaz). Bu korelasyonun KENDİSİ
   TMR'den sapar (aşağıda ölçüldü) — bu yüzden hüküm TMR'ye bağlandı,
   korelasyon bandı ikincil kanıttır.
3. **Log yasası.** u⁺ = ln(y⁺)/κ + B, κ = 0,41, B = 5,0 (White, F. M.,
   *Viscous Fluid Flow*, McGraw-Hill, 1974, s. 472 — TMR'nin kendi
   sayfasında kullandığı künye). κ SA'nın kendi sabitidir
   (``sa_neg.SA_KAPPA``) ve bu dosyada İKİNCİ KEZ YAZILMAZ: modülden
   ithal edilir.

TMR REFERANS SAYILARI (CFL3D, en ince 545×385 ızgara; cf_plate.dat)
-------------------------------------------------------------------
    Re_x        c_f (TMR)      0,0592·Re^−0,2   korelasyon/TMR
    2,50e6      2,978224e-03   3,109809e-03     1,0442
    3,00e6      2,899512e-03   2,998454e-03     1,0341
    4,00e6      2,781094e-03   2,830803e-03     1,0179
    4,850420e6  2,705622e-03   2,723741e-03     1,0067
    5,00e6      2,694030e-03   2,707246e-03     1,0049
    6,00e6      2,625716e-03   2,610306e-03     0,9941
    6,80e6      2,580304e-03   2,545774e-03     0,9866
TMR'nin bu bandındaki YEREL üssü −0,14417 (log-log eğim, 145 nokta) —
yani 1/7 korelasyonunun −0,2 üssü bu Reynolds bandında GEÇERLİ DEĞİLDİR.
Bizim ölçtüğümüz üs −0,1459: TMR'ye %1,2 yakın, korelasyona değil.

ÖLÇÜLEN IZGARA MERDİVENİ (M4 Max, 2026-08-18; 1500 iterasyon, satır-örtük)
--------------------------------------------------------------------------
| ni×nj | ilk hücre | y⁺ maks | c_f/TMR @4,85e6 | u⁺ sapması | κ_ölç | süre  |
|-------|-----------|---------|-----------------|------------|-------|-------|
| 48×48 |  4,5 µm   |  1,302  | 1,0170          | −0,127     | 0,3996| 119 s |
| 48×64 |  4,5 µm   |  1,299  | 1,0140          | −0,056     | 0,3987|  54 s |
| 64×96 |  4,5 µm   |  1,335  | 1,0119          | −0,003     | 0,3991| 177 s |
| 48×64 |  9,0 µm   |  2,627  | 1,0338          | −0,381     | 0,4001|  67 s |
(Süreler CPU rekabetine duyarlıdır — aynı kurulum yalnız-başına 54 s,
başka koşumla birlikte 119 s ölçüldü; iterasyon sayıları özdeş.)

İKİ EKSEN DE TEKDÜZE ve doğru yönde: ızgara inceldikçe TMR'ye yaklaşıyor
(1,0170 → 1,0140 → 1,0119) ve log-yasası sapması sıfıra iniyor
(−0,127 → −0,056 → −0,003); ilk hücreyi ikiye katlamak (y⁺ 1,3 → 2,6)
c_f'yi %2 yukarı, u⁺ sapmasını 7 kat kötüye götürüyor — yani hüküm
GERÇEKTEN duvar çözünürlüğüne bağlı ve bant kaza eseri tutmuyor.

Bu dosya YALNIZ 48×64 basamağını koşar (süit disiplini); diğer basamaklar
ÖLÇÜMDÜR ve burada beyanlıdır.

YAKINSAMA — DÜRÜST BEYAN
------------------------
Koşu 1e-8 kalıntı eşiğine İNMEZ (converged=False) ve bu bilerek böyledir:
ön kenar (z = 0) tekil bir noktadır — TMR'nin kendi sayfası da c_f'nin
orada tekilleştiğini yazar — ve kaba eksenel çözünürlükte kalıntının
tabanı oraya kilitlenir. HÜKÜM BÜYÜKLÜĞÜ olan c_f ölçüm penceresinde
OTURMUŞTUR: iterasyon 1500 ↔ 2500 arasında c_f/TMR oranı 1,0140 ↔ 1,0141
(4. hanede oynama), ortalama kalıntı 1500'de ~1e-04 sınıfına, SA kalıntısı
2,4e-04'e (başlangıcının 6 mertebe altına) iner. Bekçiler bu iki büyüklüğe
bağlıdır; "converged=True" İDDİA EDİLMEZ.

SA'NIN NOKTA-ÖRTÜK KÖŞEGENİ — KUSUR KAPANDI (V3, parti 39)
-----------------------------------------------------------
Parti 38'de bu vaka bir kusuru ÖLÇEREK ortaya çıkarmıştı:
``sa_source_terms``ın yayımladığı ``jacobian_diag`` yalnız DONMUŞ yok
etme türevini taşıyordu; tampon tabakada (y⁺ ≈ 3-10) f_v2(χ) < 0 iken
üretimin ν̃ türevi de büyük-negatiftir ve eksik köşegenle çevrim Δt'den
bağımsız PERİYOT-2 salınıma kilitleniyordu (CFL 25/5/1 üçünde de aynı
genlik %37; ν̃[24,60] 5,4606e-05 ↔ 7,4740e-05). Ölçülen etki:

    köşegen           SA kalıntısı (1500 it)   c_f/TMR   u⁺ sapması
    yalnız yok etme   4,78e+00 (salınım)       1,0271    −0,275
    tam               2,36e-04 (inişte)        1,0140    −0,056

V3 KAPANIŞI: ``sa_neg.sa_source_terms`` artık TAM ANALİTİK ∂(P−D)/∂(ρν̃)
türevinin negatif kısmını yayımlıyor (zincir: f_v1′, f_v2′, Denklem 12
yama dalı, r kelepçesi, f_w(g(r)); FD çaprazı 20 000 rastgele durumda
maks bağıl 1,8e-08 — tests/cfd/test_sa_neg.py) ve sürücünün ileri-fark
VEKİLİ SÖKÜLDÜ. Sökümden önce ölçülen vekil/yayımlanan oranı bu vakada
(300 it) 6,51 → 1,0008, lüle ikizinde 5,51 → 1,0025'e indi. Bu koşunun
hüküm sayıları söküm sonrası YENİDEN ölçüldü (aşağıdaki bantlar o
ölçümün sayılarıdır); periyot-2'nin ölümünü SA kalıntısının 4 mertebe
düşüşü + log-yasası bandı + test_sa_neg'in tampon-kökü bekçisi tutar.

MUTASYON KANITLARI (uygulandı, kırmızı ÖLÇÜLDÜ, TERS-DEĞİŞTİRMEYLE geri
alındı; M1-M2 PARTİ 38 kayıtlarıdır — o turun sağlam ``steady.py`` md5'i
= 4b1ef8bcba3512b2440f45e948d54ca3. M1'in V3 halefi M8'dir: aynı kusur
artık ``sa_neg.py``de üretilerek ölçülür ve bu dosyada AYNI iki bekçiyi
kırar — kayıt test_sa_neg.py docstring'inde, mutant md5'iyle)
-----------------------------------------------------------------------------
  M1 "kaynak Jacobian'ını modelin yayımladığı (yalnız yok etme) köşegene
     düşür" (mutant md5 eeb99a0ad6ebafebb68f2dbf9aad9310)
     → 2 KIRMIZI: ``test_kosum_hukum_buyuklugunde_oturdu`` (SA kalıntısı
       dört mertebe düşemiyor — periyot-2 salınım) ve
       ``test_basamak8_log_yasasi`` (u⁺ sapması −0,275, bant ±0,15).
       İLK TURDA log-yasası bandı ±0,5'ti ve kusuru GEÇİRİYORDU; bant
       ölçümle (2,7 kat pay) daraltıldı — bekçi kusuru artık FİZİKLE de
       yakalıyor, yalnız yakınsama izinden değil.
       TMR çaprazı YEŞİL kalıyor ve bu BEYANLIDIR: kusurlu çözümün
       c_f/TMR oranı 1,0271, kabul bandı [0,99; 1,04] — bant ızgara
       merdivenini (1,0119…1,0338) kapsayacak genişlikte seçildiği için
       o kusuru ayırt edemiyor. Bandı daraltmak merdiveni yalanlardı.
  M2 "çizgi-dışı (i) sönüm payını sıfırla" (mutant md5
     58377337c934bf70bfa9967562bec3c4) → 9 KIRMIZI (SA alanı patlıyor;
     dosyanın neredeyse tamamı düşüyor). Bu, satır-örtük SA sisteminin
     DPLR payına gerçekten muhtaç olduğunun canlı kanıtıdır.
Diğer dört mutasyon (duvar kütle akısı, μ_t duvar yüzü, yüz pozitiflik
kapısı, çarpıklık açısı tanımı) ``test_viskoz_entegrasyon.py``nin
bekçilerini kırar; kayıtları o dosyadadır.
"""

import numpy as np
import pytest

from hrma.cfd.euler_core import prim_to_cons_axisym
from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.sa_neg import SA_KAPPA
from hrma.cfd.steady import ViscousOptions, solve_steady_axisym

from .test_viskoz_aki import (
    VISK_CP, VISK_GAMMA, VISK_R, transport as visk_transport,
)

# --- vaka (LEVHAT_ öneki: türbülanslı levha; laminer LEVHA_ ile karışmasın)
LEVHAT_R = 0.100                # boru yarıçapı [m] (levha = iç yüzey)
LEVHAT_L = 0.600                # levha uzunluğu [m]
LEVHAT_P0 = 1.0e6               # rezervuar basıncı [Pa]
LEVHAT_T0 = 3000.0              # rezervuar sıcaklığı [K]
LEVHAT_MU = 2.075e-5            # doğrulama akışkanı viskozitesi [Pa·s]
LEVHAT_U_HEDEF = 218.7          # arka basıncı KURAN hız [m/s] (M ≈ 0,2)

LEVHAT_NI = 48
LEVHAT_NJ = 64
#: İlk hücre KALINLIĞI [m] — y⁺ ≈ 1 ön tahmininden (u_τ = u_e√(c_f/2),
#: c_f TMR'nin bu banttaki değeri): 2·y⁺·μ/(ρ_w u_τ) ≈ 4,5 µm. Gerçekleşen
#: y⁺ koşumdan ÖLÇÜLÜR (aşağıdaki bekçi) — tahmin hüküm değildir.
LEVHAT_ILK_HUCRE_M = 4.5e-6
LEVHAT_ITER = 1500
LEVHAT_TOL = 1.0e-8

#: Ölçüm penceresi [m] (a priori kural, sonuca göre seçilmedi): ön kenarın
#: tekil bölgesi ve çıkış sınırının etkisi dışarıda.
LEVHAT_PENCERE_M = (0.20, 0.55)

# --- NASA TMR SA referansı (docstring künyesi; CFL3D 545×385) ---
#: (Re_x, c_f) çiftleri — FlatPlate/SA/cf_plate.dat'tan okundu.
TMR_CF_TABLOSU = (
    (2.50e6, 2.978224e-03),
    (3.00e6, 2.899512e-03),
    (4.00e6, 2.781094e-03),
    (4.850420355e6, 2.705622e-03),
    (5.00e6, 2.694030e-03),
    (6.00e6, 2.625716e-03),
    (6.80e6, 2.580304e-03),
)
#: cf_convergence.dat'ın kendi istasyonu (x = 0,970084071 → Re_x = 4,8504e6)
#: ve en ince ızgara değerleri — İKİ BAĞIMSIZ KODUN sonucu.
TMR_ISTASYON_RE_X = 4.850420355e6
TMR_CF_CFL3D = 0.270562153e-2
TMR_CF_FUN3D = 0.270540472596778e-2
#: TMR'nin bu banttaki YEREL log-log üssü (145 nokta, Re_x ∈ [2e6, 7e6]).
TMR_YEREL_US = -0.14417

# --- Log yasası (White 1974, s. 472; κ SA'nın kendi sabiti) ---
LOG_B = 5.0
LOG_PENCERE_Y_PLUS = (30.0, 400.0)

# --- ÖLÇÜLEN bantlar (48×64 koşusu; docstring tablosu) ---
#: c_f/TMR ölçülen 1,0140 (pencere ortalaması 1,0142). Bant ölçümün ~%2,5
#: çevresi: daha dar bant ızgara gürültüsüne takılır, daha geniş bant
#: basamağı anlamsızlaştırır (kaba ızgara 48×48'de 1,03 sınıfına çıkıyor —
#: IZGARA MERDİVENİ).
TMR_ORAN_BANDI = (0.99, 1.04)
#: c_f/korelasyon ölçülen ortalama 1,0010 (bant [0,9713; 1,0241]).
KOR_ORAN_BANDI = (0.97, 1.04)
#: Yerel üs ölçülen −0,1459 (TMR −0,14417). Bant TMR'nin ±%10'u.
US_BANDI = (-0.160, -0.130)
#: u⁺ − (ln y⁺/κ + B) ölçülen ortalama −0,056, bant [−0,102; +0,113].
#: Kabul bandı ±0,15 u⁺ birimi (ölçümün ~2,7 katı; ızgara merdiveninin en
#: kaba basamağı bile −0,127 ile içeride). Bant BİLEREK dar: SA kaynak
#: Jacobian'ı eksik bırakıldığında (mutasyon M1) sapma −0,275'e çıkıyor ve
#: bu bekçi kırmızıya düşüyor — yani kusur yalnız YAKINSAMA bekçisiyle
#: değil FİZİKLE de yakalanıyor. Daha geniş bant (±0,5) o kusuru geçiriyordu:
#: ÖLÇÜLDÜ, daraltıldı.
LOG_SAPMA_BANDI = 0.15
#: μ_t/μ ölçülen maks 285,6 — akış GERÇEKTEN türbülanslı (laminer koşuda 0).
MU_T_ORAN_ALT = 100.0


def levhat_gridi(ni=LEVHAT_NI, nj=LEVHAT_NJ, ilk_hucre=LEVHAT_ILK_HUCRE_M):
    """Duvara kümelenmiş (tanh) ızgara — §5.7'nin gerdirme kalemi."""
    z = np.linspace(0.0, LEVHAT_L, ni + 1)
    return build_grid_from_wall(z, np.full(ni + 1, LEVHAT_R), nj,
                                first_cell_m=ilk_hucre, stretch='tanh')


def levhat_tasinimi():
    """Sabit özellikli doğrulama akışkanı (üs 0 → μ, k sıcaklıktan bağımsız)."""
    return visk_transport(exponent=0.0, mu_ref=LEVHAT_MU)


def _arka_basinc(u):
    """İzantropik: u hızını veren statik basınç (vakanın SÜRÜŞ tanımı)."""
    return LEVHAT_P0 * (1.0 - u ** 2 / (2.0 * VISK_CP * LEVHAT_T0)) ** (
        VISK_GAMMA / (VISK_GAMMA - 1.0))


def _baslangic(grid, pb):
    """Düzgün hız + sabit basınç TAHMİNİ (profil tohumlanmaz)."""
    p = np.full_like(grid.z_centers, pb)
    T = LEVHAT_T0 * (pb / LEVHAT_P0) ** ((VISK_GAMMA - 1.0) / VISK_GAMMA)
    rho = p / (VISK_R * T)
    return prim_to_cons_axisym(rho, np.full_like(p, LEVHAT_U_HEDEF),
                               np.zeros_like(p), p, VISK_GAMMA)


def kosum(ni=LEVHAT_NI, nj=LEVHAT_NJ, ilk_hucre=LEVHAT_ILK_HUCRE_M,
          max_iters=LEVHAT_ITER, turbulence='sa_neg', **kw):
    """Vakayı ÜRÜN SÜRÜCÜSÜNDEN koşar (viskoz + SA opt-in, satır-örtük)."""
    grid = levhat_gridi(ni, nj, ilk_hucre)
    pb = _arka_basinc(LEVHAT_U_HEDEF)
    opt = ViscousOptions(transport=levhat_tasinimi(),
                         wall_thermal='adiabatic', turbulence=turbulence)
    sonuc = solve_steady_axisym(
        grid, LEVHAT_P0, LEVHAT_T0, VISK_GAMMA, VISK_R, Pb=pb, viscous=opt,
        initial_state=_baslangic(grid, pb),
        time_integrator='line_implicit_j', tol_res=LEVHAT_TOL,
        max_iters=max_iters, settle_tol=1e-10, y_plus_target=1.0, **kw)
    return {'grid': grid, 'sonuc': sonuc}


def olcumler(kosu):
    """İstasyon başına c_f, Re_x ve TMR/korelasyon karşılıkları."""
    grid = kosu['grid']
    f = kosu['sonuc']['fields']
    rho, uz, p = f['rho_kg_m3'], f['u_z_m_s'], f['pressure_Pa']
    z = grid.z_centers[:, 0]
    ue = uz[:, 0]                            # eksen = potansiyel çekirdek
    rho_e = rho[:, 0]
    Re_x = rho_e * ue * z / LEVHAT_MU
    tau = kosu['sonuc']['viscous']['wall_shear_Pa']
    c_f = tau / (0.5 * rho_e * ue ** 2)
    tmr_re = np.array([r for r, _ in TMR_CF_TABLOSU])
    tmr_cf = np.array([c for _, c in TMR_CF_TABLOSU])
    return {
        'z': z, 'Re_x': Re_x, 'ue': ue, 'rho_e': rho_e, 'c_f': c_f,
        'c_f_korelasyon': 0.0592 * Re_x ** -0.2,
        # TMR eğrisi istasyonlarımıza taşınır (TMR'nin KENDİ noktaları
        # arasında doğrusal): karşılaştırma nokta-nokta yapılır, tek
        # çapaya indirgenmez.
        'c_f_tmr': np.interp(Re_x, tmr_re, tmr_cf, left=np.nan,
                             right=np.nan),
        'mach': ue / np.sqrt(VISK_GAMMA * p[:, 0] / rho_e),
        'pencere': (z >= LEVHAT_PENCERE_M[0]) & (z <= LEVHAT_PENCERE_M[1]),
    }


def duvar_birimleri(kosu, i):
    """i. istasyonun (y⁺, u⁺) profili + u_τ — ÖLÇÜLEN büyüklüklerden.

    u_τ = √(|τ_w|/ρ_w); ρ_w duvar sıcaklığından ve komşu hücre
    basıncından (sınır tabakası boyunca p sabit kabulü, viscous.py'nin
    kendi beyanı); μ_w LAMİNER viskozitedir — SA duvarda ν̃ = 0 verdiği
    için μ_t orada TAM SIFIRDIR ve duvar birimleri türbülans modelinden
    BAĞIMSIZ tanımlıdır.
    """
    grid = kosu['grid']
    v = kosu['sonuc']['viscous']
    f = kosu['sonuc']['fields']
    y = LEVHAT_R - grid.r_centers[i]
    T_w = v['wall_temperature_K'][i]
    rho_w = f['pressure_Pa'][i, -1] / (VISK_R * T_w)
    # μ_w = LEVHAT_MU: doğrulama akışkanının üssü SIFIRDIR (μ sıcaklıktan
    # bağımsız), yani duvar viskozitesi vakanın kendi sabitidir — ikinci
    # bir μ(T) değerlendirmesi yazılmaz.
    u_tau = np.sqrt(abs(v['wall_shear_Pa'][i]) / rho_w)
    y_plus = rho_w * u_tau * y / LEVHAT_MU
    return y_plus[::-1], (f['u_z_m_s'][i] / u_tau)[::-1], u_tau


@pytest.fixture(scope='module')
def levhat():
    kosu = kosum()
    return kosu, olcumler(kosu)


# ===========================================================================
# Vakanın rejimi ÖNCE doğrulanır (referansların geçerlilik şartları)
# ===========================================================================

def test_vaka_turbulansli_ve_dusuk_mach(levhat):
    """TMR'nin şartları: türbülanslı Re_x, M ≈ 0,2, çözülmüş duvar."""
    kosu, m = levhat
    p = m['pencere']
    assert p.sum() >= 20, 'ölçüm penceresinde yeterli istasyon yok'
    assert m['Re_x'][p].min() > 2.0e6, (
        f'Re_x {m["Re_x"][p].min():.2e} — TMR referans bandının altında')
    assert m['Re_x'][p].max() < 7.0e6, (
        f'Re_x {m["Re_x"][p].max():.2e} — TMR tablosunun dışına çıktı')
    assert m['mach'].max() < 0.3, (
        f'M = {m["mach"].max():.3f}: TMR vakası M = 0,2 (sıkıştırılabilirlik '
        'düzeltmesi gerekmesin)')
    # Çekirdek hızı sürüşten DOĞDU (dayatılmadı)
    assert 0.9 * LEVHAT_U_HEDEF < m['ue'].mean() < 1.05 * LEVHAT_U_HEDEF
    # AKIŞ GERÇEKTEN TÜRBÜLANSLI: μ_t/μ ölçüldü (laminer koşuda 0 olurdu)
    tb = kosu['sonuc']['viscous']['turbulence']
    assert tb['mu_t_over_mu_max'] > MU_T_ORAN_ALT, (
        f'μ_t/μ maks {tb["mu_t_over_mu_max"]:.1f} — akış türbülanslı '
        'değil, SA vakayı laminerde bırakmış')
    assert tb['model'] == 'sa_neg'
    assert kosu['sonuc']['inputs']['turbulence'] == 'sa_neg'


def test_duvar_cozunurlugu_y_plus_bandinda(levhat):
    """y⁺ ≈ 1 ızgarası GERÇEKLEŞTİ mi? (§5.7 dürüst döngüsü)."""
    kosu, _ = levhat
    dongu = kosu['sonuc']['viscous']['y_plus_loop']
    assert dongu['target'] == 1.0
    assert dongu['achieved_max'] < 2.0, (
        f'y⁺ maks {dongu["achieved_max"]:.3f} — duvar çözünmemiş, log '
        'yasası bekçisi anlamını yitirir')
    assert 0.8 < dongu['achieved_mean'] < 1.3, (
        f'y⁺ ortalaması {dongu["achieved_mean"]:.3f} hedeften uzak')
    # Izgara GERÇEKTEN gerdirilmiş (düzgün dağılımla y⁺ ≈ 1 imkânsızdır)
    assert dongu['grid_radial_distribution'] == 'tanh'
    gerdirme = kosu['grid'].radial_stretch
    assert gerdirme['first_cell_target_m'] == LEVHAT_ILK_HUCRE_M
    assert gerdirme['first_cell_rel_error_max'] < 1e-9, (
        'gerdirme hedeflenen ilk hücreyi tutturmadı — y⁺ ölçümü ile '
        'ön tahmin arasındaki bağ kopar')
    # Büyüme oranı beyanı (§5.7 kalite ölçütü): bu ızgarada ölçülen bant
    assert 1.1 < gerdirme['growth_ratio_max'] < 1.6


def test_kosum_hukum_buyuklugunde_oturdu(levhat):
    """DÜRÜST YAKINSAMA BEYANI: kalıntı eşiği tutmaz, c_f oturur.

    Bekçi "converged" İDDİA ETMEZ (docstring'de gerekçesi): ön kenar
    tekilliği kalıntı tabanını belirler. Ölçülen üç şey sınanır —
    (i) ortalama akış kalıntısı başlangıç geçişinin ~2 mertebe altına
    indi, (ii) SA kalıntısı EN AZ 4 mertebe düştü (periyot-2 salınım
    hâlinde bu İMKÂNSIZDIR — kusur bekçisi), (iii) hüküm bantları 1e-4
    sınıfında.
    """
    kosu, _ = levhat
    sonuc = kosu['sonuc']
    h = np.asarray(sonuc['residual_history'])
    sa_h = np.asarray(sonuc['viscous']['turbulence']['sa_residual_history'])
    assert h[-1] < 1e-3, f'ortalama akış kalıntısı {h[-1]:.3e}'
    assert h[-1] < np.max(h[10:100]) / 100.0, (
        'kalıntı geçiş rejiminin iki mertebe altına inmedi')
    assert sa_h.size == sonuc['iterations']
    assert sa_h[-1] < sa_h[0] * 1e-4, (
        f'SA kalıntısı {sa_h[0]:.3e} → {sa_h[-1]:.3e}: dört mertebe '
        'düşmedi. Nokta-örtük köşegen eksikse çevrim periyot-2 salınıma '
        'kilitlenir ve bu bekçi kırmızıya düşer (docstring: ölçülen kusur).')
    for ad in ('mass_flow_in', 'mass_flow_out', 'throat_mach'):
        assert sonuc['settle_bands'][ad] < 1e-3, (
            f'{ad} bandı {sonuc["settle_bands"][ad]:.2e}')


# ===========================================================================
# BASAMAK 8 — c_f: TMR çaprazı (birincil) + korelasyon bandı (ikincil)
# ===========================================================================

def test_basamak8_c_f_NASA_TMR_egrisiyle_capraz(levhat):
    """c_f(Re_x) ↔ TMR SA (CFL3D 545×385) — NOKTA NOKTA, tek çapa değil."""
    _, m = levhat
    p = m['pencere'] & np.isfinite(m['c_f_tmr'])
    assert p.sum() >= 15, 'TMR tablosunun kapsadığı istasyon sayısı yetersiz'
    oran = m['c_f'][p] / m['c_f_tmr'][p]
    ort = float(np.mean(oran))
    lo, hi = TMR_ORAN_BANDI
    assert lo < ort < hi, (
        f'c_f/TMR ortalaması {ort:.4f}, bant [{lo}, {hi}] dışında; '
        f'istasyon bandı [{oran.min():.4f}, {oran.max():.4f}], '
        f'Re_x {m["Re_x"][p].min():.2e}-{m["Re_x"][p].max():.2e}')
    assert float(np.max(oran) / np.min(oran)) < 1.06, (
        f'c_f/TMR oranı x boyunca DÜZ olmalı — bant '
        f'[{oran.min():.4f}, {oran.max():.4f}]: eğim varsa tabakanın '
        'büyüme yasası TMR ile uyuşmuyordur')


def test_basamak8_TMR_istasyon_capraz_iki_kod(levhat):
    """x = 0,970084071 istasyonu: İKİ BAĞIMSIZ KODUN yayımlanmış değeri.

    CFL3D ve FUN3D en ince ızgarada 4. haneye kadar aynı (2,7056e-03 ↔
    2,7054e-03) — bu, referansın ızgaradan bağımsızlığının TMR'nin KENDİ
    kanıtıdır. Bizim değerimiz o iki sayıya karşı ölçülür.
    """
    _, m = levhat
    cf = float(np.interp(TMR_ISTASYON_RE_X, m['Re_x'], m['c_f']))
    lo, hi = TMR_ORAN_BANDI
    for ad, ref in (('CFL3D', TMR_CF_CFL3D), ('FUN3D', TMR_CF_FUN3D)):
        assert lo < cf / ref < hi, (
            f'c_f({TMR_ISTASYON_RE_X:.4e}) = {cf:.6e}; {ad} referansı '
            f'{ref:.6e}, oran {cf / ref:.4f} bant [{lo}, {hi}] dışında')
    # İki referansın KENDİ aralarındaki fark, bandımızın çok altında
    # olmalı (aksi hâlde bant referans belirsizliğini ölçüyor olurdu).
    assert abs(TMR_CF_CFL3D - TMR_CF_FUN3D) / TMR_CF_CFL3D < 1e-3


def test_basamak8_yerel_us_TMR_ile_ayni_korelasyonla_DEGIL(levhat):
    """c_f ∝ Re_x^n: ölçülen n TMR'ye yakın, korelasyonun −0,2'sine DEĞİL.

    Bu bekçi mutlak seviyeden BAĞIMSIZDIR (tabaka doğru büyüyor mu?) ve
    ayrıca bir okuma hatasını kapatır: 1/7 korelasyonunun −0,2 üssü bu
    Reynolds bandında TMR'nin kendi verisiyle uyuşmuyor (TMR yerel üssü
    −0,14417, 145 nokta). Referans olarak korelasyonu tek başına almak
    bizi yanlış yöne çekerdi.
    """
    _, m = levhat
    p = m['pencere']
    us = float(np.polyfit(np.log(m['Re_x'][p]), np.log(m['c_f'][p]), 1)[0])
    lo, hi = US_BANDI
    assert lo < us < hi, (
        f'c_f ∝ Re_x^{us:.4f}; TMR yerel üssü {TMR_YEREL_US:.5f}, kabul '
        f'bandı [{lo}, {hi}]')
    assert abs(us - TMR_YEREL_US) < abs(us - (-0.2)), (
        f'ölçülen üs {us:.4f} TMR\'nin yerel üssünden ({TMR_YEREL_US}) '
        'ÇOK korelasyonun −0,2\'sine yakın — vaka TMR ile uyuşmuyor')


def test_basamak8_korelasyon_bandi_IKINCIL_kanit(levhat):
    """c_f = 0,0592·Re_x^(−0,2) bandı (ikincil; sapması TMR'den ÖLÇÜLÜ)."""
    _, m = levhat
    p = m['pencere']
    oran = m['c_f'][p] / m['c_f_korelasyon'][p]
    ort = float(np.mean(oran))
    lo, hi = KOR_ORAN_BANDI
    assert lo < ort < hi, (
        f'c_f/korelasyon ortalaması {ort:.4f}, bant [{lo}, {hi}] dışında; '
        f'istasyon bandı [{oran.min():.4f}, {oran.max():.4f}]')
    # Korelasyonun KENDİSİ TMR'den sapıyor: bu dosyada iddia edilen
    # "korelasyon bandı" bu yüzden İKİNCİLDİR. Sapma ölçülüp kayda geçer.
    tmr_re = np.array([r for r, _ in TMR_CF_TABLOSU])
    tmr_cf = np.array([c for _, c in TMR_CF_TABLOSU])
    kor_tmr = (0.0592 * tmr_re ** -0.2) / tmr_cf
    assert kor_tmr.max() > 1.03 and kor_tmr.min() < 1.0, (
        'korelasyon ile TMR arasındaki ÖLÇÜLEN sapma (1,044 → 0,987) '
        'kayboldu — tablo ya da korelasyon değişmiş, docstring güncellenmeli')


# ===========================================================================
# BASAMAK 8 — duvar yasası: log katmanı ve viskoz alt tabaka
# ===========================================================================

def test_basamak8_log_yasasi(levhat):
    """u⁺ = ln(y⁺)/κ + B — κ SA'nın KENDİ sabitinden ithal edilir."""
    kosu, m = levhat
    i = int(np.argmin(np.abs(m['Re_x'] - TMR_ISTASYON_RE_X)))
    y_plus, u_plus, u_tau = duvar_birimleri(kosu, i)
    lo, hi = LOG_PENCERE_Y_PLUS
    log_p = (y_plus > lo) & (y_plus < hi)
    assert log_p.sum() >= 10, (
        f'log penceresinde {log_p.sum()} nokta var — ızgara log katmanını '
        'çözmüyor, bekçi kör olurdu')
    teori = np.log(y_plus) / SA_KAPPA + LOG_B
    sapma = u_plus[log_p] - teori[log_p]
    assert np.max(np.abs(sapma)) < LOG_SAPMA_BANDI, (
        f'u⁺ − (ln y⁺/{SA_KAPPA} + {LOG_B}): ortalama {sapma.mean():+.4f}, '
        f'bant [{sapma.min():+.4f}, {sapma.max():+.4f}] — '
        f'±{LOG_SAPMA_BANDI} dışına çıktı (istasyon z = '
        f'{m["z"][i] * 1000:.1f} mm, u_τ = {u_tau:.3f} m/s)')
    # κ ve B'nin KENDİLERİ de ölçülür (log katmanı gerçekten kuruldu mu?)
    egim, kesme = np.polyfit(np.log(y_plus[log_p]), u_plus[log_p], 1)
    kappa_olculen = 1.0 / egim
    assert abs(kappa_olculen - SA_KAPPA) < 0.05, (
        f'ölçülen κ = {kappa_olculen:.4f}, SA sabiti {SA_KAPPA}')
    assert abs(kesme - LOG_B) < 1.0, f'ölçülen B = {kesme:.4f}'


def test_basamak8_viskoz_alt_tabaka(levhat):
    """y⁺ < 5'te u⁺ = y⁺ — duvar birimlerinin kendi tutarlılık sınavı."""
    kosu, m = levhat
    i = int(np.argmin(np.abs(m['Re_x'] - TMR_ISTASYON_RE_X)))
    y_plus, u_plus, _ = duvar_birimleri(kosu, i)
    alt = y_plus < 5.0
    assert alt.sum() >= 2, 'alt tabakada nokta yok (y⁺ ızgarası kaba)'
    bagil = np.max(np.abs(u_plus[alt] - y_plus[alt]) / y_plus[alt])
    assert bagil < 0.05, (
        f'viskoz alt tabakada u⁺ ≠ y⁺ (maks bağıl fark {bagil:.4f}): '
        'ya duvar kayma gerilmesi ya da y⁺ tanımı tutarsız')
    # Duvara komşu hücrede μ_t GERÇEKTEN küçük (alt tabaka laminer)
    tb = kosu['sonuc']['viscous']['turbulence']
    assert tb['mu_t_over_mu_wall_max'] < 5.0, (
        f'duvar hücresinde μ_t/μ = {tb["mu_t_over_mu_wall_max"]:.2f} — '
        'alt tabaka türbülansla dolmuş, y⁺ ≈ 1 iddiası şüpheli')


# ===========================================================================
# SA'nın sürücüye bağlanmasının KENDİ bekçileri (bu vaka üstünde)
# ===========================================================================

def test_kaynak_jacobian_KUSURU_KAPANDI_kosegen_analitik(levhat):
    """Devir kaleminin HALEFİ: kusur sa_neg'de kapandı, vekil söküldü.

    Eski bekçi, sürücünün ileri-fark vekili ile modelin yayımladığı
    (yalnız yok etme) köşegeni arasındaki oranı ~2'de tutuyordu. V3'te
    ``sa_neg.sa_source_terms`` üretim türevini de taşıyan TAM analitik
    köşegeni yayımlıyor; SÖKÜMDEN ÖNCE ölçülen oran bu vakada (300 it)
    6,51 → 1,0008'e indi ve vekil söküldü. Bekçi artık kapanışı tutar:
    ratio alanları yayımlanmıyor, beyan analitik köşegeni söylüyor,
    periyot-2'nin ölümünü SA kalıntısının 4 mertebe düşüşü
    (test_kosum_hukum_buyuklugunde_oturdu) ve log-yasası bandı ölçüyor.
    """
    kosu, _ = levhat
    tb = kosu['sonuc']['viscous']['turbulence']
    assert 'source_jacobian_ratio_max' not in tb, (
        'vekilin oran alanı geri gelmiş — söküm sözleşmesi bozuldu')
    assert 'source_jacobian_extra_max_1_s' not in tb
    assert 'TAM ANALİTİK' in tb['source_jacobian_basis'], (
        'köşegenin nereden geldiği BEYAN edilmeli (modelin yayımladığı '
        'tam analitik köşegen) — beyan silinirse okuyucu vekilin hâlâ '
        'yaşadığını sanır')
    assert '6,51' in tb['source_jacobian_basis'], (
        'söküm öncesi ölçülen oran beyandan silinmiş — kapanışın kanıtı '
        'okunamaz')


def test_duvarda_mu_t_sifir_ve_akilar_laminer(levhat):
    """SA'nın duvar sözleşmesi: ν̃_w = 0 → μ_t duvar YÜZÜNDE tam sıfır.

    Sonucu ölçülebilir: adyabatik duvarda q_w ayrık olarak TAM sıfır
    kalır (μ_t sızsaydı k_eff değişir, q_w yine sıfır kalırdı — bu yüzden
    asıl kanıt duvar hücresindeki μ_t/μ oranı ve τ_w'nin laminer μ_w ile
    tutarlılığıdır: y⁺/u⁺ bekçileri onu ölçüyor).
    """
    kosu, m = levhat
    v = kosu['sonuc']['viscous']
    assert np.all(v['wall_heat_flux_W_m2'] == 0.0), (
        'adyabatik duvarda q_w tam sıfır olmalı')
    assert abs(kosu['sonuc']['wall_mass_flux_kg_s']) < 1e-12, (
        'duvarda kütle sızıntısı')
    # τ_w akış yönünde (ayrılma yok) ve SA alanı sağlıklı
    assert np.all(v['wall_shear_Pa'][m['pencere']] > 0.0)
    tb = v['turbulence']
    assert tb['nu_tilde_min_m2_s'] > -1e-12, (
        f'ν̃ negatif dala düştü (min {tb["nu_tilde_min_m2_s"]:.3e}); '
        'SA-neg bunu taşır ama bu vakada BEKLENMEZ — beyan güncellenmeli')
    assert tb['negative_cell_count'] == 0
    assert tb['nu_tilde_freestream_m2_s'] == pytest.approx(
        3.0 * LEVHAT_MU / m['rho_e'][0], rel=0.05), (
        'ν̃_∞ giriş kolonundan ölçülen ν ile 3 kat oranında olmalı')


def test_kutle_butcesi_ve_izgara_kalitesi_beyani(levhat):
    """Kütle bütçesi + §5.7 ızgara kalitesi beyanı (dik ızgarada θ ≈ 0)."""
    kosu, _ = levhat
    sonuc = kosu['sonuc']
    assert sonuc['mass_balance_rel'] < 1e-4, (
        f'kütle bütçesi {sonuc["mass_balance_rel"]:.2e}')
    gq = sonuc['viscous']['grid_quality']
    # Düz levhada duvar normali j çizgileriyle ÇAKIŞIR → çarpıklık ≈ 0.
    # (Gerçek lüle konturunda 42°'ye çıkıyor — basamak 9, ayrı dosyada.)
    assert gq['max_wall_skew_deg'] < 0.01, (
        f'düz duvarda çarpıklık {gq["max_wall_skew_deg"]:.4f}° — ızgara '
        'kurulumu bozuk')
    # y⁺ ≈ 1 ızgarasının bedeli: en-boy oranı 10³ sınıfı. §5.7 kararı bu
    # sayının HER KOŞUMDA yayımlanmasıdır.
    assert gq['max_aspect_ratio'] > 1000.0
    assert gq['first_cell_thickness_m_min'] == pytest.approx(
        LEVHAT_ILK_HUCRE_M, rel=1e-6)
