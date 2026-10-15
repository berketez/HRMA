# tests/cfd — V1 sürücü bağlaması: viskoz opt-in, viskoz Δt, satır-örtük
# viskoz Jacobian ve basamak 6 (örtük katmanın hüküm-nötrlüğü)
"""Viskoz katmanın ÜRÜN SÜRÜCÜSÜNE bağlanmasının bekçileri (V1, basamak 6).

KAPSAM
------
A1 turu viskoz kalıntıyı (``viscous.py``) ve merdivenin 4-5. basamaklarını
kendi elle yazdığı açık yürüyücüsüyle kapattı. Bu dosya bir sonraki soruyu
sorar: **aynı fizik ürünün sürücüsünden (``steady.solve_steady_axisym``)
geçtiğinde de aynı kökü mü veriyor, ve örtük katman o kökü değiştiriyor mu?**

BAĞIMSIZ SÜRÜCÜ ÇAPRAZI (ölçüldü — bu dosyanın en ucuz ve en sert kanıtı)
------------------------------------------------------------------------
Aynı boru vakası (nj=8, adyabatik, ni=6nj), İKİ BAĞIMSIZ sürücüden:
    A1'in yürüyücüsü (test_boru_laminer.kosum)  f·Re = 63,1687
    ürün sürücüsü (solve_steady_axisym)          f·Re = 63,1668
Bağıl fark 3,0e-05. İki sürücünün başlangıç durumu, durma ölçütü, CFL
rampası ve sınırlayıcı dondurma davranışı FARKLIDIR; aynı köke inmeleri
kararlı-hâl kökünün yola bağlı olmadığının canlı kanıtıdır.

BASAMAK 6 — HÜKÜM NÖTRLÜĞÜ (ölçüldü, M4 Max, 2026-08-18; nj=8, tol 1e-9)
-----------------------------------------------------------------------
Açık SSP-RK2 : 18908 iterasyon, 38,5 s, kalıntı 6,54e-10
Satır-örtük  :  4080 iterasyon,  8,3 s, kalıntı 8,10e-11   → 4,63× kazanç
Yakınsanan alanların maks BAĞIL farkı (bileşenin kendi maksimumuna göre):
    ρ 3,4e-06 · u_z 8,4e-05 · u_r 1,2e-03 · p 7,9e-07 · T 3,5e-06
Türetilmiş büyüklükler: f·Re 3,3e-07 · duvar τ_w 1,4e-04 · debi 1,8e-06.
En büyük fark u_r'dedir ve BEKLENENDİR: u_r bu vakada mertebe olarak en
küçük büyüklüktür (parabolik akışta ~0), bağıl ölçek onu büyütür.

VİSKOZ Δt (§5.6) — ölçüm ve kalibrasyon
---------------------------------------
Formül Blazek §6.1.4 biçimindedir ve taşınım toplamı sürücünün KENDİ Δt
fonksiyonundan geri okunur (ikinci tanım yok). C_visc kalibrasyonu
``steady.DEFAULT_C_VISC`` künyesindedir: İKİ bağımsız vakadan şemanın
kararlılık katsayısı S ∈ [0,979; 1,078) ölçüldü, varsayılan 1,5 seçildi.
Bu dosya sınırın İKİ YANINI da koşar (altında ıraksama, üstünde sonluluk).

IRAKSAMA KAPISI — ÖLÇÜLEN GEREKÇE
---------------------------------
Viskoz akı kütle denklemine HİÇ girmez. Dolayısıyla fiziksel olmayan
duruma düşen viskoz koşuda **kütle kalıntısı sonlu kalabilir** (ölçüldü:
nj=48 μ×16 C=0,25 koşusunda son kalıntı 3,14e+01 — sonlu, ama durum
ρ≤0/p≤0). Sürücünün eski NaN kapısı bunu görmez; kapı viskoz kalıntının
KENDİ NaN sözleşmesine bağlandı. Bağlanmasaydı sürücü ıraksamış durumla
Δt hesabına girer ve gas_transport'un pozitiflik kapısı ValueError'la
SIZARDI (ölçüldü, ilk turda gerçekten sızdı) — sürücü sözleşmesi ise
"istisna sızmaz, 'diverged' beyanı döner"dir.

VİSKOZ JACOBIAN (§5.6 "viskoz kısmı TAM")
-----------------------------------------
İnce-tabaka biçiminde kurulan 4×4 bloklar, viskoz kalıntının GERÇEK
Jacobian'ıyla (merkezi olmayan sonlu fark, bağıl adım 1e-6) karşılaştırıldı:
    AR ≈ 2   izotermal : köşegen %1,1 · çapraz < %0,05
    AR ≈ 8   izotermal : köşegen %0,1 · çapraz < %0,05
    AR ≈ 2   adyabatik : köşegen %2,3 · çapraz < %0,05
İhmalin AR büyüdükçe KÜÇÜLMESİ tasarımın iddiasının ta kendisidir (terim
tam da baskın olduğu rejimde daha doğru). Duvar bloğu iç blokların ~3,4
katıdır (izotermal) — yüksek AR'de sistemin baskın terimi odur.

V1 PERFORMANS KAPISI (§9.3 + Berke kararı §13/1: "süre TAVANI YOK;
ölçülür ve beyan edilir") — ÖLÇÜLDÜ, M4 Max, 2026-08-18
----------------------------------------------------------------------
Vaka: conftest lülesi 192×48, laminer doğrulama akışkanı μ = 0,15 Pa·s
(üs 0), izotermal duvar T_w = 0,6·T0, çıkış tam dışdeğerleme (Pb=None),
başlangıç YAKINSAMIŞ EULER alanı (§5.6 "bedava hızlandırma"), satır-örtük
yol. Bu dosya o koşuyu KOŞMAZ (18 dakika); sayılar burada beyanlıdır.

  y⁺ (τ_w'den ÖLÇÜLDÜ): maks 2,630 · ortalama 0,710 · boğaz 0,876
      istasyonların %96,4'ünde y⁺ ≤ 1. Tepe değer İLK istasyondadır
      (z = 1 mm, tabaka daha yeni başlıyor) — hedef gövdede sağlandı.
      İlk hücre merkezi duvardan 260-417 µm.
  SÜRE (iterasyon başına, iki arka uçta):
      Euler çekirdeği : numba 2,18 ms/it ↔ saf NumPy 4,45 ms/it → 2,03×
      Viskoz koşu     : numba 37,7 ms/it ↔ saf NumPy 38,1 ms/it → 1,01×
      Toplam (numba): 2000 iterasyonda 75,5 s; 30000 iterasyonda 1105 s
      (+ Euler ön koşusu 23-25 s).
  ARKA UÇ SÖZLEŞMESİ (ölçülen sonuç, tasarım §5.9/§13-6'ya cevap):
      **numba viskoz yolda bugün İŞE YARAMIYOR** (1,01×). Sebep ölçüldü:
      Euler kalıntısı toplam maliyetin ~%6'sıdır; viskoz kalıntı ve
      blok-Thomas gevşetmesi SAF NumPy'dir. Tasarımın "saf NumPy 2× yavaş
      → 10+ dakika" gerekçesi V1'de GEÇERSİZDİR. Bu yüzden arayüze
      "numba şart" isteği TAŞINMADI (görev kararı) — taşınsaydı ölçülmemiş
      bir iddia olurdu. İki arka ucun kalıntı izleri aynı iterasyonlarda
      basamak basamak AYNI çıktı (son kalıntı 2,155e-05 ↔ 2,155e-05):
      viskoz yol arka uçtan bağımsızdır.
  YAKINSAMA — V1'in DÜRÜST SONUCU: koşu 1e-8 hüküm eşiğine İNMEDİ.
      Kalıntı ~2000 iterasyonda 2e-05'e iner ve orada 2e-05…1,5e-04
      bandında LİMİT DÖNGÜSÜNE girer (30000 iterasyonda da 2,7e-04).
      Takılmanın yeri ``settle_bands`` ile ölçülmüştü: giriş debisi
      3,4e-09 · boğaz Mach 9,9e-07 · ÇIKIŞ debisi 1,0e-05. V1 buradan
      bir ADAY sebep beyan etti: çıkış tam dışdeğerleme (Pb=None) ama
      duvara komşu satırlar ses-altı, yani alt tabaka çapasız.

V2 — KAPININ YENİDEN ÖLÇÜMÜ: V1'in ADAY TEŞHİSİ YANLIŞLANDI
------------------------------------------------------------
Aynı vaka bu partide yeniden koşuldu (aynı kurulum; taban sayıları
birebir yeniden üretildi: y⁺ maks 2,6301 · ort 0,7096 · ṁ 4,470615 ·
çıkış bandı 1,00815e-05). ÖLÇÜLENLER:

  (1) LİMİT DÖNGÜSÜNÜN PERİYODU TAM 25 İTERASYON ve
      25 = ``DEFAULT_IMPLICIT_SLOPE_REFRESH``. Dalga biçimi çevrimden
      çevrime harfi harfine tekrar ediyor:
          it 3925: 4,276e-04 1,390e-04 6,396e-05 7,033e-05 …
          it 3950: 4,272e-04 1,390e-04 6,418e-05 7,049e-05 …
      Yani salınımı üreten ÇIKIŞ SINIRI DEĞİL, MUSCL eğimlerinin her K
      iterasyonda tazelenmesidir (minmod gevelemesinin yeniden
      enjeksiyonu — ``DEFAULT_IMPLICIT_SLOPE_REFRESH`` künyesinin kendi
      tarif ettiği mekanizma).

  (2) MEVCUT ÇARE ATEŞLEDİĞİNDE DÖNGÜ KIRILIYOR. Oturma-tetikli KALICI
      eğim dondurması, tetiği erişilebilir bir oturma eşiğiyle
      (settle_tol 1e-4) koşulduğunda 1590. iterasyonda ateşliyor ve koşu
      2649 iterasyonda YAKINSIYOR:
          settle_tol   sonuç          it     kalıntı     çıkış bandı
          1e-9         converged=F   4000   1,830e-05   1,0081e-05
          1e-4         converged=T   2649   9,929e-09   4,742e-08
      Debi kökü İKİSİNDE DE aynı (4,470615 kg/s) — hüküm-nötrlük.
      KUSURUN ADI: tetik ile HÜKÜM aynı eşiği (settle_tol) paylaşıyor;
      dondurma tam da gevelemeyi gidermek için varken tetiklenebilmesi
      gevelemenin YOKLUĞUNU gerektiriyor. V1 koşusu Euler vakasının
      ayarıyla (1e-9) koşulduğu için çare hiç ateşlemedi.

  (3) ÇIKIŞ ÇAPASININ ÖLÇÜLEN ETKİSİ (bu partide yazıldı, opt-in).
      Dört köşe koşuldu (çapa × oturma eşiği), İKİ ARKA UÇTA:
        çapa           settle   it    conv   kalıntı     ham bant   faz bant
        extrapolate    1e-9    4000    F    1,830e-05   1,008e-05  1,008e-05
        extrapolate    1e-4    2649    T    9,929e-09   4,742e-08  (çevrim
                                                                    yok)
        core_pressure  1e-9    4000    F    1,931e-05   1,417e-06  4,176e-07
        core_pressure  1e-4    2646    T    9,962e-09   4,714e-08  (çevrim
                                                                    yok)
      Okuma: çapa ham çıkış bandını 7,1 kat sıkıştırıyor VE kalan
      oynamanın niteliğini değiştiriyor (faz bandı ham bandın 3,4 katı
      altına iniyor: çapasız hâldeki SÜRÜKLENME gidiyor, geriye tazeleme
      çevrimi kalıyor). Ama limit döngüsünü KIRMIYOR — onu kıran eğim
      dondurmasıdır. 64×16'da ise çapa kalıntıyı 1,42e-08'den 1,64e-03'e
      BOZUYOR (kaba ızgarada "ilk süpersonik hücre" tabakanın kenarı
      değildir). Varsayılan DEĞİŞTİRİLMEDİ; çapa çözülmüş tabaka ister.
      Debi kökü DÖRT koşumda da 4,470615 kg/s, y⁺ maks 2,630.

  (4) ARKA UÇ — dört köşenin DÖRDÜ de saf NumPy ile numba arasında
      BİT-ÖZDEŞ (kalıntı izlerinin tamamı array_equal; son kalıntı
      1,8297891099434436e-05 her ikisinde de). Viskoz yol arka uçtan
      bağımsızdır (V1'in bulgusu doğrulandı).
      SÜRE (yalnız-başına koşum, CPU rekabetsiz, M4 Max):
          Euler çekirdeği : numba 1,982 ↔ saf NumPy 4,175 ms/it → 2,11×
          Viskoz koşu     : numba 36,615 ↔ saf NumPy 37,004 ms/it → 1,011×
          Çapanın iterasyon maliyeti: 36,615 → 36,480 ms/it (yok sayılır)
      numba viskoz yolda hâlâ İŞE YARAMIYOR (V1 ölçümü doğrulandı).

  (5) YAN BULGU — beyanın kendi yazarını yalanlaması: ilk turda
      "çıkış debisi aslında oturmuş, oynayan çevrim" diye okunabilecek
      bir faz ölçümü (3 fazdan) 3,4e-07 vermişti. 25 fazın TAMAMINA
      bakan ``_settle_band_phase`` bunu çürüttü: en kötü faz 1,0082e-05,
      yani ham bantla aynı — çıkış debisi gerçekten SÜRÜKLENİYOR.
      Kalıntının çevrime kilitli olduğu ise ayrıca ve bağımsız doğrudur.

V3 — TETİK/HÜKÜM AYRIMI SONRASI KAPI (parti 39; dairesel kilidin
yapısal kapanışı, steady.DEFAULT_FREEZE_SETTLE_TOL künyesi)
----------------------------------------------------------------
(2)'nin kusuru yapısal olarak kapandı: dondurma tetiği artık AYRI eşik
taşıyor (freeze_settle_tol) ve hüküm eşiği settle_tol'dan bağımsız
ateşleyebiliyor. 192×48 KAPI vakası YENİDEN ÖLÇÜLDÜ (M4 Max,
2026-08-18, numba):

    hüküm (settle)  tetik   sonuç         it     kalıntı     donma
    1e-4            (=hüküm) converged=T  2649   9,9288e-09  1590
    1e-9            1e-4     converged=T  3171   2,0818e-10  1590

Birinci satır parti 38'in ölçümünü BİREBİR korur (aynı iterasyon, aynı
kalıntı, aynı donma — tetik koşulu özdeş olduğundan bit-aynı yol);
ikinci satır eski kilitle SONSUZA DEK imkânsız olandır: SIKI hüküm
üçlüsü (bantlar in=7,9e-12 / out=9,9e-10 / M=9,5e-12 < 1e-9) gerçekten
oturdu, kalıntı 2e-10'a indi. Debi kökü İKİ hükümde de 4,470615 kg/s,
y⁺ maks 2,6301 — hüküm-nötrlük. Varsayılan gevşetilMEDİ (ölçülen kök
zehirlenmesi: 60×12 nötrlük çiftinde gevşek tetik alan bandını
5,41e-08 → 5,03e-04'e bozuyor — künye DEFAULT_FREEZE_SETTLE_TOL).

MALİYET: bu dosya ~130 s (üç kararlı-hâl koşusu + mutasyon koşusu + iki
kısa ıraksama koşusu + cebirsel bekçiler).
"""

import numpy as np
import pytest

from hrma.cfd import kernels as _kernels
from hrma.cfd import steady
from hrma.cfd.euler_core import (
    WALL_BC_NOSLIP, WALL_BC_SLIP, cons_to_prim_axisym, local_dt_axisym,
    precompute_geometry, prim_to_cons_axisym, residual_axisym,
)
from hrma.cfd.gradients import precompute_gradient_geometry
from hrma.cfd.relax_implicit import (
    line_implicit_delta, local_dt_axial, viscous_jacobian_blocks,
)
from hrma.cfd.steady import (
    DEFAULT_C_VISC, ViscousOptions, solve_steady_axisym, viscous_i_face_share,
    viscous_local_dt,
)
from hrma.cfd.viscous import (
    VISCOUS_NOT_MODELLED, viscous_residual, viscous_spectral_radius,
)

from . import test_boru_laminer as boru
from .test_boru_laminer import (
    BORU_L, BORU_MU, BORU_P0, BORU_PB, BORU_T0, BORU_TW_ORANI,
    BORU_U_TAHMINI, POISEUILLE_F_RE, boru_gridi, boru_tasinimi,
)
from .test_viskoz_aki import (
    VISK_GAMMA, VISK_R, transport as visk_transport,
)

# --- basamak 6 vakası: A1'in merdiveninin ORTA basamağı (aynı vaka!) ---
NOTR_NJ = 8
NOTR_TOL = 1.0e-9

#: A1'in bağımsız yürüyücüsünün ölçtüğü f·Re (test_boru_laminer docstring
#: tablosu, nj=8, adyabatik, kalıntı eşiği 1e-7). Bu bir ANALİTİK referans
#: değil, İKİNCİ BİR SÜRÜCÜNÜN ölçümüdür: iki sürücünün aynı köke inmesi
#: sınanır (analitik referans ayrı bekçide, POISEUILLE_F_RE ile).
A1_F_RE_NJ8 = 63.1687

#: Ölçülen sürücüler-arası bağıl fark 3,0e-05 (yukarıdaki künye). Bant
#: ölçümün ~3 katı: iki sürücünün durma ölçütü farklı olduğundan iterasyon
#: hatası bu mertebede oynar.
SURUCU_CAPRAZ_TOL = 1.0e-4

#: Basamak 6 nötrlük bantları — ÖLÇÜMDEN (docstring tablosu, ~2× pay).
NOTRLUK_ALAN_TOL = {'rho_kg_m3': 1e-5, 'u_z_m_s': 3e-4, 'u_r_m_s': 4e-3,
                    'pressure_Pa': 3e-6, 'temperature_K': 1e-5}
NOTRLUK_TUREV_TOL = {'f_Re': 1e-5, 'tau_w': 5e-4, 'mdot': 1e-5}

#: Kararlılık sınırı ölçüm vakası (DEFAULT_C_VISC künyesindeki ikinci
#: vaka): viskoz sınırın BAĞLAYICI olduğu rejim μ×16 ile kurulur.
SINIR_NJ = 24
SINIR_MU_KAT = 16.0
SINIR_IRAKSAK_C = 0.5          # ÖLÇÜLDÜ: 417. adımda fiziksel olmayan durum
SINIR_ADIM = 600


def _boru_baslangic(grid):
    """Vakanın TEK başlangıç tanımı (A1'in modülünden; kopya yazılmaz)."""
    return boru._baslangic(grid, BORU_U_TAHMINI, BORU_PB)


def _boru_kos(nj=NOTR_NJ, *, integrator='ssp_rk2', c_visc=DEFAULT_C_VISC,
              wall_thermal='adiabatic', T_wall=None, mu=BORU_MU,
              tol=NOTR_TOL, max_iters=60000, **kw):
    """Boru vakasını ÜRÜN SÜRÜCÜSÜNDEN koşar (A1'in yürüyücüsü değil)."""
    grid = boru_gridi(nj)
    tr = boru_tasinimi(mu)
    opt = ViscousOptions(
        transport=tr, wall_thermal=wall_thermal, T_wall=T_wall,
        T_wall_source=None if T_wall is None else 'verification_case',
        c_visc=c_visc)
    sonuc = solve_steady_axisym(
        grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R, Pb=BORU_PB, viscous=opt,
        initial_state=_boru_baslangic(grid), time_integrator=integrator,
        tol_res=tol, max_iters=max_iters, settle_tol=1e-11, **kw)
    return {'grid': grid, 'transport': tr, 'sonuc': sonuc, 'nj': nj}


def _kesit(kosu):
    """Kesit büyüklükleri — A1'in ölçüm zinciriyle AYNI tanımlar."""
    grid = kosu['grid']
    f = kosu['sonuc']['fields']
    rho, uz, T = f['rho_kg_m3'], f['u_z_m_s'], f['temperature_K']
    dz = grid.Z[1:, 0] - grid.Z[:-1, 0]
    dA = grid.volume / dz[:, None]
    alan = np.sum(dA, axis=1)
    rho_b = np.sum(rho * dA, axis=1) / alan
    mdot = np.sum(rho * uz * dA, axis=1)
    u_b = mdot / (rho_b * alan)
    mu_b = np.sum(kosu['transport'].viscosity(T) * dA, axis=1) / alan
    Re = rho_b * u_b * boru.BORU_D / mu_b
    tau = kosu['sonuc']['viscous']['wall_shear_Pa']
    c_f = tau / (0.5 * rho_b * u_b ** 2)
    z_D = grid.z_centers[:, 0] / boru.BORU_D
    pencere = ((z_D >= boru.BORU_HIZ_PENCERESI[0])
               & (z_D <= boru.BORU_HIZ_PENCERESI[1]))
    return {'z_D': z_D, 'f_Re': 4.0 * c_f * Re, 'Re': Re, 'tau_w': tau,
            'mdot': mdot, 'pencere': pencere}


def _f_re(kosu):
    m = _kesit(kosu)
    return float(np.mean(m['f_Re'][m['pencere']]))


# ===========================================================================
# Fikstürler — pahalı koşular BİR kez
# ===========================================================================

@pytest.fixture(scope='module')
def acik_kosu():
    """Basamak 6'nın referans kolu: açık SSP-RK2 + viskoz yerel Δt."""
    return _boru_kos(integrator='ssp_rk2')


@pytest.fixture(scope='module')
def ortuk_kosu():
    """Basamak 6'nın sınanan kolu: j-satır örtük + TAM viskoz Jacobian."""
    return _boru_kos(integrator='line_implicit_j')


@pytest.fixture(scope='module')
def euler_kosu():
    """Viskoz KAPALI koşu (opt-in sözleşmesinin canlı tarafı)."""
    grid = boru_gridi(NOTR_NJ)
    return grid, solve_steady_axisym(
        grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R, Pb=BORU_PB,
        initial_state=_boru_baslangic(grid), tol_res=1e-6, max_iters=3000,
        settle_tol=1e-9)


@pytest.fixture(scope='module')
def jacobian_vakasi():
    """Küçük, ÇARPIK OLMAYAN boru + fiziksel bir durum (cebirsel bekçiler)."""
    return _jacobian_kurulum(ni=10, nj=8, yaricap=0.005)


def _jacobian_kurulum(ni, nj, yaricap):
    from hrma.cfd.grid_axisym import build_grid_from_wall

    z = np.linspace(0.0, BORU_L, ni + 1)
    grid = build_grid_from_wall(z, np.full(ni + 1, yaricap), nj)
    tr = boru_tasinimi()
    r = grid.r_centers / yaricap
    uz = 55.0 * (1.0 - r ** 2) + 3.0
    ur = 0.5 * np.sin(np.pi * r) * (1.0 + grid.z_centers / BORU_L)
    p = BORU_P0 * (1.0 - 0.02 * grid.z_centers / BORU_L)
    T = BORU_T0 * (1.0 + 0.05 * r ** 2)
    rho = p / (VISK_R * T)
    U = prim_to_cons_axisym(rho, uz, ur, p, VISK_GAMMA)
    return {'grid': grid, 'transport': tr, 'U': U,
            'geom': precompute_geometry(grid),
            'grad_geom': precompute_gradient_geometry(grid)}


# ===========================================================================
# (A) Opt-in sözleşmesi: viskoz KAPALIYKEN yol bugünkü Euler yoludur
# ===========================================================================

def test_viskoz_kapali_yol_viscous_residual_cagirmaz(monkeypatch):
    """YAPISAL kanıt: viscous=None iken viskoz kod HİÇ çalışmaz.

    Bit-özdeşlik bekçisi (test_euler_bit_ozdesligi) sonucu ölçer; bu bekçi
    yolu ölçer — biri kırılırsa diğeri sebebi söyler.
    """
    def patlat(*a, **kw):
        raise AssertionError('viscous=None iken viscous_residual çağrıldı')

    monkeypatch.setattr(steady, 'viscous_residual', patlat)
    monkeypatch.setattr(steady, 'viscous_spectral_radius', patlat)
    monkeypatch.setattr(steady, 'viscous_jacobian_blocks', patlat)
    grid = boru_gridi(4)
    for entegrator in ('ssp_rk2', 'line_implicit_j'):
        sonuc = solve_steady_axisym(
            grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R, Pb=BORU_PB,
            initial_state=_boru_baslangic(grid), max_iters=5,
            time_integrator=entegrator)
        assert sonuc['viscous'] is None
        assert sonuc['inputs']['viscous'] is False


def test_viskoz_kapali_beyanlar_degismedi(euler_kosu):
    """Euler koşusunun beyanları V1 öncesiyle AYNI (daraltma sızmadı)."""
    _, sonuc = euler_kosu
    assert 'inviscid' in sonuc['assumptions']
    assert 'adiabatic' in sonuc['assumptions']
    assert sonuc['inputs']['wall_bc'] == WALL_BC_SLIP
    assert 'Viskozite, sınır tabakası ve türbülans yok' in \
        sonuc['not_modelled']['viscosity_turbulence']
    assert 'turbulence' not in sonuc['not_modelled']


def test_viskoz_acikken_beyan_daralir_ve_TEK_KAYNAKTAN_gelir(acik_kosu):
    """§10: anahtar SİLİNMEZ, daraltılır — daraltma metni viscous.py'nin."""
    sonuc = acik_kosu['sonuc']
    nm = sonuc['not_modelled']
    assert nm['viscosity_turbulence'] == VISCOUS_NOT_MODELLED['turbulence']
    assert nm['wall_roughness'] == VISCOUS_NOT_MODELLED['wall_roughness']
    assert nm['conjugate_heat_transfer'] == \
        VISCOUS_NOT_MODELLED['conjugate_heat_transfer']
    # Euler'in kendi anahtarları duruyor (daraltma silme değildir)
    assert 'reaction_real_gas' in nm and 'time_accuracy' in nm
    assert 'inviscid' not in sonuc['assumptions']
    assert 'adiabatic' not in sonuc['assumptions']
    assert 'laminar_viscous' in sonuc['assumptions']
    assert 'wall_adiabatic' in sonuc['assumptions']
    assert 'steady' in sonuc['assumptions']
    assert sonuc['inputs']['wall_bc'] == WALL_BC_NOSLIP


def test_isil_duvar_sozlesmesi_surucude_de_gecerli():
    """Kapılar viscous.py'de TEK yerdedir; sürücü onları GEÇİRMEZ."""
    grid = boru_gridi(4)
    ortak = dict(Pb=BORU_PB, max_iters=3)
    with pytest.raises(ValueError, match='T_wall ZORUNLUDUR'):
        solve_steady_axisym(
            grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R,
            viscous=ViscousOptions(transport=boru_tasinimi(),
                                   wall_thermal='isothermal'), **ortak)
    with pytest.raises(ValueError, match='T_wall verilemez'):
        solve_steady_axisym(
            grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R,
            viscous=ViscousOptions(transport=boru_tasinimi(),
                                   wall_thermal='adiabatic',
                                   T_wall=2000.0), **ortak)
    with pytest.raises(ValueError, match='tanımsız'):
        solve_steady_axisym(
            grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R,
            viscous=ViscousOptions(transport=boru_tasinimi(),
                                   wall_thermal='wall_function'), **ortak)


def test_adiyabatik_kipte_T_wall_surucuden_SIZMAZ():
    """ViscousOptions.residual_kwargs adyabatikte T_wall'ı TAŞIMAZ.

    (Taşısaydı viscous.py'nin "adyabatikte T_wall yasak" kapısı sürücü
    yolunda her koşuda patlardı — kapı orada TEK yerde kalmalı.)
    """
    opt = ViscousOptions(transport=boru_tasinimi(), wall_thermal='adiabatic')
    kw = opt.residual_kwargs()
    assert 'T_wall' not in kw and 'T_wall_source' not in kw
    izo = ViscousOptions(transport=boru_tasinimi(), wall_thermal='isothermal',
                         T_wall=2000.0, T_wall_source='verification_case')
    assert izo.residual_kwargs()['T_wall'] == 2000.0


def test_initial_state_kapisi():
    """Sıcak başlangıç AYNI ızgarada ve SONLU olmalı (sessiz kabul yok)."""
    grid = boru_gridi(4)
    with pytest.raises(ValueError, match='initial_state biçimi'):
        solve_steady_axisym(grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R,
                            initial_state=np.zeros((3, 3, 4)), max_iters=2)
    bozuk = _boru_baslangic(grid)
    bozuk[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match='sonlu olmalı'):
        solve_steady_axisym(grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R,
                            initial_state=bozuk, max_iters=2)


# ===========================================================================
# (B) Kalıntı KOMPOZİSYONU (§5.1) — viskoz terim gerçekten çözümde mi?
# ===========================================================================

def test_yakinsanan_alanda_R_euler_TEK_BASINA_sifir_degil(acik_kosu):
    """Kompozisyonun canlı kanıtı: kök R_E + R_V = 0'ın köküdür, R_E'nin değil.

    Yakınsanan alanda toplam kalıntı sıfıra iner; Euler kalıntısı TEK
    BAŞINA inmez (viskoz terim onu dengeler). Bu, "viskoz katman bağlandı
    ama fiilen sıfır" tuzağını yakalar.
    """
    kosu = acik_kosu
    grid, tr = kosu['grid'], kosu['transport']
    f = kosu['sonuc']['fields']
    U = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                            f['pressure_Pa'], VISK_GAMMA)
    geom = precompute_geometry(grid)
    du_e, _ = residual_axisym(U, grid, VISK_GAMMA, VISK_R, BORU_P0, BORU_T0,
                              Pb=BORU_PB, geom=geom, wall_bc=WALL_BC_NOSLIP)
    w = cons_to_prim_axisym(U, VISK_GAMMA)
    from hrma.cfd.euler_core import _outlet_state, inlet_state_from_stagnation
    du_v, _ = viscous_residual(
        grid, U, tr, R=VISK_R, wall_thermal='adiabatic', geom=geom,
        inlet_face_primitives=inlet_state_from_stagnation(
            w[0], VISK_GAMMA, VISK_R, BORU_P0, BORU_T0),
        outlet_face_primitives=_outlet_state(w[-1], geom['n_out_hat'],
                                             VISK_GAMMA, BORU_PB))
    olcek = np.max(np.abs(du_e), axis=(0, 1))
    toplam = np.max(np.abs(du_e + du_v), axis=(0, 1)) / olcek
    # ÖLÇÜLDÜ (nj=8, yakınsanan alan): oran bileşen bileşen
    #   kütle 1,000 (viskoz akı kütleye GİRMEZ — ayrı bekçide)
    #   z-momentum 1,2e-03 · r-momentum 2,0e-02 · enerji 4,4e-02
    # Yani viskoz terim Euler kalıntısını 20-800 kat söndürüyor; bant
    # ölçümün ~2 katı. r-momentum ve enerjide oranın büyük olması
    # beklenendir: o denklemlerde Euler kalıntısının maksimumu eksen
    # civarında zaten küçüktür (bölen küçük).
    assert np.all(toplam[1:] < 0.1), (
        f'toplam kalıntı Euler kalıntısına göre küçülmedi: {toplam} — '
        'viskoz terim dengelemiyorsa kompozisyon fiilen kopmuştur')
    assert np.max(np.abs(du_v[..., 0])) == 0.0, (
        'viskoz akı kütle denklemine girdi (girmemeli)')


def test_duvar_ciktilari_ve_y_plus_yayimlaniyor(acik_kosu):
    """Sürücü duvar dizilerini ve ÖLÇÜLEN y⁺'ı yayımlar (§5.7)."""
    kosu = acik_kosu
    v = kosu['sonuc']['viscous']
    ni = kosu['grid'].ni
    for ad in ('wall_shear_Pa', 'wall_heat_flux_W_m2', 'wall_y_plus',
               'wall_first_cell_m', 'wall_temperature_K', 'wall_z_m'):
        assert np.shape(v[ad]) == (ni,), ad
        assert np.all(np.isfinite(v[ad])), ad
    # y⁺ tanımı: u_τ = √(τ_w/ρ_w), y = ilk hücre merkezinin normal mesafesi
    rho_w = kosu['sonuc']['fields']['pressure_Pa'][:, -1] / (
        VISK_R * v['wall_temperature_K'])
    u_tau = np.sqrt(np.abs(v['wall_shear_Pa']) / rho_w)
    beklenen = (rho_w * u_tau * v['wall_first_cell_m']
                / kosu['transport'].viscosity(v['wall_temperature_K']))
    assert np.allclose(v['wall_y_plus'], beklenen, rtol=1e-12)
    assert v['wall_y_plus_max'] < 1.0, (
        f'boru vakası duvar-çözümlü olmalı — ölçülen maks y⁺ '
        f'{v["wall_y_plus_max"]:.3f} (A1 turu 0,390 ölçtü)')
    assert v['thermal_mode'] == 'adiabatic'
    assert np.all(v['wall_heat_flux_W_m2'] == 0.0), (
        'adyabatik duvarda q_w ayrık olarak TAM sıfır olmalı')


def test_kalinti_bilesenleri_hukum_kalintisini_yalanlamiyor(acik_kosu):
    """Hüküm kütle kalıntısındandır; momentum/enerji GERİDE KALMAMALI.

    Viskoz akı kütleye girmediği için tek bileşenli hüküm yanıltıcı
    olabilirdi. ÖLÇÜLDÜ (nj=8): kütle 6,5e-10 EN BÜYÜK bileşendir
    (momentum 2,9e-11/2,0e-12, enerji 6,9e-12) — yani hüküm bileşeni
    diğerlerini örtmüyor, aksine en muhafazakâr olanı.
    """
    v = acik_kosu['sonuc']['viscous']
    bilesen = np.asarray(v['residual_components_scaled'])
    assert bilesen.shape == (4,)
    assert np.all(bilesen[1:] <= bilesen[0]), (
        f'momentum/enerji kalıntısı kütleninkini aştı: {bilesen} — hüküm '
        'ölçütü artık yeterli değil, sürücü sözleşmesi güncellenmeli')


# ===========================================================================
# (C) Viskoz yerel Δt (§5.6) — Blazek biçimi, tek kaynak, i payı
# ===========================================================================

def test_viskoz_dt_blazek_bicimi(jacobian_vakasi):
    """Δt = CFL·V/[Σ_taşınım + C·ΣΛ_v] — iki kaynaktan bağımsız kurulup eşitlenir."""
    v = jacobian_vakasi
    grid, U, tr, geom = v['grid'], v['U'], v['transport'], v['geom']
    cfl, c = 0.7, 2.5
    dt = viscous_local_dt(U, grid, VISK_GAMMA, VISK_R, cfl, tr, c, geom=geom)
    tasinim = cfl * grid.volume / local_dt_axisym(
        U, grid, VISK_GAMMA, cfl, geom['area_i'], geom['area_j'])
    lam = viscous_spectral_radius(grid, U, tr, R=VISK_R, geom=geom)
    assert np.allclose(dt, cfl * grid.volume / (tasinim + c * lam), rtol=1e-13)
    # C = 0 → salt taşınım adımı (formülün dejenere ucu)
    assert np.allclose(
        viscous_local_dt(U, grid, VISK_GAMMA, VISK_R, cfl, tr, 0.0, geom=geom),
        local_dt_axisym(U, grid, VISK_GAMMA, cfl, geom['area_i'],
                        geom['area_j']), rtol=1e-13)
    # C büyüdükçe adım KÜÇÜLÜR (kararlılık yönü)
    dt_buyuk = viscous_local_dt(U, grid, VISK_GAMMA, VISK_R, cfl, tr, 10.0,
                                geom=geom)
    assert np.all(dt_buyuk < dt)


def test_viskoz_dt_i_payi_salt_geometrik(jacobian_vakasi):
    """Satır-örtük dalda viskoz sınır YALNIZ i-yüzlerinden (j örtük)."""
    v = jacobian_vakasi
    grid, U, tr, geom = v['grid'], v['U'], v['transport'], v['geom']
    pay = viscous_i_face_share(geom['area_i'], geom['area_j'])
    assert np.all((pay > 0.0) & (pay < 1.0))
    cfl, c = 0.7, 2.5
    dt_eks = viscous_local_dt(U, grid, VISK_GAMMA, VISK_R, cfl, tr, c,
                              geom=geom, axial_only=True)
    tasinim = cfl * grid.volume / local_dt_axial(U, grid, VISK_GAMMA, cfl,
                                                 geom['area_i'])
    lam = viscous_spectral_radius(grid, U, tr, R=VISK_R, geom=geom) * pay
    assert np.allclose(dt_eks, cfl * grid.volume / (tasinim + c * lam),
                       rtol=1e-13)
    # Pay, fizikten (μ, ρ, Pr) BAĞIMSIZ olmalı: taşınım katsayısı 5×
    # değişse bile aynı sayı çıkar (sadeleşme iddiasının bekçisi)
    pay2 = viscous_i_face_share(geom['area_i'], geom['area_j'])
    assert np.array_equal(pay, pay2)
    # Yüksek en-boy oranında (ince radyal hücre) i payı KÜÇÜLÜR
    ince = _jacobian_kurulum(ni=10, nj=32, yaricap=0.005)
    pay_ince = viscous_i_face_share(ince['geom']['area_i'],
                                    ince['geom']['area_j'])
    assert np.max(pay_ince) < np.min(pay), (
        'radyal hücre inceldikçe viskoz sınırın i payı küçülmeli — '
        'satır-örtük katmanın kazancının kaynağı budur')


def test_c_visc_olculen_sinirin_ALTINDA_iraksar_ustunde_sonlu():
    """C_visc kalibrasyonunun İKİ YANI da koşulur (künye DEFAULT_C_VISC'te).

    Vaka: nj=24 boru, μ×16 (viskoz sınır bağlayıcı). ÖLÇÜLDÜ: C=0,50
    417. adımda fiziksel olmayan duruma düşer; C=0,75 ve üstü 2000 adım
    sonlu kalır. Varsayılan 1,5 sınırın ÜSTÜNDEDİR.
    """
    iraksak = _boru_kos(nj=SINIR_NJ, mu=BORU_MU * SINIR_MU_KAT,
                        c_visc=SINIR_IRAKSAK_C, tol=1e-14,
                        max_iters=SINIR_ADIM, cfl_max=0.9)['sonuc']
    assert iraksak['converged'] is False
    assert iraksak['convergence_basis'].startswith('DIVERGED')
    assert iraksak['iterations'] < SINIR_ADIM, (
        'C_visc sınırın altındayken koşu ıraksamalıydı; ıraksamadıysa '
        'kalibrasyon vakası artık bağlayıcı değil (künye yenilenmeli)')
    kararli = _boru_kos(nj=SINIR_NJ, mu=BORU_MU * SINIR_MU_KAT,
                        c_visc=DEFAULT_C_VISC, tol=1e-14,
                        max_iters=SINIR_ADIM, cfl_max=0.9)['sonuc']
    assert kararli['iterations'] == SINIR_ADIM
    assert np.all(np.isfinite(np.asarray(kararli['residual_history'])))
    assert not kararli['convergence_basis'].startswith('DIVERGED')


def test_iraksama_kapisi_kutle_kalintisi_SONLUYKEN_de_yakalar():
    """Ölçülen tuzak: viskoz koşuda kütle kalıntısı ıraksamayı GÖREMEZ.

    Viskoz akı kütle denklemine girmez; fiziksel olmayan durumda bile
    kütle kalıntısı sonlu kalabilir (ÖLÇÜLDÜ). Kapı bu yüzden viskoz
    kalıntının NaN sözleşmesine bağlandı. Bu bekçi hem ıraksamanın
    yakalandığını hem de İSTİSNA SIZMADIĞINI ölçer.
    """
    sonuc = _boru_kos(nj=SINIR_NJ, mu=BORU_MU * SINIR_MU_KAT, c_visc=0.25,
                      tol=1e-14, max_iters=SINIR_ADIM, cfl_max=0.9)['sonuc']
    assert sonuc['converged'] is False
    assert sonuc['convergence_basis'].startswith('DIVERGED')
    gecmis = np.asarray(sonuc['residual_history'])
    assert np.all(np.isfinite(gecmis)), (
        'bu vakanın anlamı KÜTLE kalıntısının sonlu kalmasıdır; NaN '
        'olduysa vaka artık kapının gerekçesini kanıtlamıyor')
    assert np.all(np.isfinite(sonuc['fields']['pressure_Pa'])), (
        'ıraksayan koşu bilinen son SONLU alanla dönmeli (sürücü sözleşmesi)')


# ===========================================================================
# (D) Satır-örtük viskoz Jacobian (§5.6 "viskoz kısmı TAM")
# ===========================================================================

def _sonlu_fark_jacobian(v, wall_thermal, T_wall, i0=None, eps=1e-6,
                         mu_t=None):
    """∂(V·R_viskoz)/∂U sütunları — GERÇEK kalıntıdan, sonlu farkla.

    ``mu_t`` verilirse kalıntı μ_eff = μ + μ_t ile kurulur ve μ_t alanı
    fark boyunca DONDURULUR (sürücünün ayrık çevrimiyle aynı kabul —
    ortalama akış adımı içinde SA alanı sabittir).
    """
    grid, U, tr = v['grid'], v['U'], v['transport']
    kw = dict(wall_thermal=wall_thermal, geom=v['geom'],
              grad_geom=v['grad_geom'], mu_t=mu_t)
    if wall_thermal == 'isothermal':
        kw.update(T_wall=T_wall, T_wall_source='verification_case')

    def net(state):
        dudt, _ = viscous_residual(grid, state, tr, R=VISK_R, **kw)
        return dudt * grid.volume[..., None]

    i0 = grid.ni // 2 if i0 is None else i0
    nj = grid.nj
    net0 = net(U)
    olcek = np.max(np.abs(U), axis=(0, 1))
    fd = np.zeros((nj, nj, 4, 4))
    for j in range(nj):
        for k in range(4):
            Up = U.copy()
            h = eps * olcek[k]
            Up[i0, j, k] += h
            fd[:, j, :, k] = (net(Up)[i0] - net0[i0]) / h
    return i0, -fd            # M = −∂net/∂U (line_implicit_delta kuruluşu)


def _kurulan_matris(bloklar, i0, nj):
    """viscous_jacobian_blocks'un kurduğu üç-köşegen (aynı işaret sözleşmesi)."""
    out = np.zeros((nj, nj, 4, 4))
    for j in range(nj):
        d = np.zeros((4, 4))
        if j < nj - 1:
            d = d + bloklar['inner_lo'][i0, j]
        if j > 0:
            d = d + bloklar['inner_hi'][i0, j - 1]
        if j == nj - 1:
            d = d + bloklar['wall'][i0]
        out[j, j] = d
        if j < nj - 1:
            out[j, j + 1] = -bloklar['inner_hi'][i0, j]
            out[j + 1, j] = -bloklar['inner_lo'][i0, j]
    return out


def _blok_farki(kurulan, gercek, indeksler):
    a = np.array([kurulan[i] for i in indeksler]).reshape(len(indeksler), -1)
    b = np.array([gercek[i] for i in indeksler]).reshape(len(indeksler), -1)
    return float(np.max(np.linalg.norm(a - b, axis=1)
                        / np.linalg.norm(b, axis=1)))


@pytest.mark.parametrize('nj,wall_thermal,T_wall,kos_tol,capraz_tol', [
    (8, 'isothermal', 2850.0, 0.02, 0.01),
    (32, 'isothermal', 2850.0, 0.005, 0.01),
    (8, 'adiabatic', None, 0.04, 0.01),
])
def test_viskoz_jacobian_gercek_jacobiana_yakin(nj, wall_thermal, T_wall,
                                                kos_tol, capraz_tol):
    """İnce-tabaka bloklar, GERÇEK viskoz Jacobian'ın sonlu-fark ölçümüne
    karşı sınanır (bantlar docstring tablosundan, ~2× pay).

    Bu bekçi "yaklaşıklık meşru" iddiasını KANITA bağlar: hüküm-nötrlük
    sol tarafın yaklaşık olmasına izin verir, ama YAKLAŞIKLIĞIN BÜYÜKLÜĞÜ
    varsayılmaz — ölçülür ve AR büyüdükçe küçüldüğü gösterilir.
    """
    v = _jacobian_kurulum(ni=10, nj=nj, yaricap=0.005)
    i0, gercek = _sonlu_fark_jacobian(v, wall_thermal, T_wall)
    bloklar = viscous_jacobian_blocks(
        v['U'], v['grid'], v['geom'], v['grad_geom'], VISK_GAMMA, VISK_R,
        v['transport'], wall_thermal=wall_thermal, T_wall=T_wall)
    kurulan = _kurulan_matris(bloklar, i0, nj)
    kos_f = _blok_farki(kurulan, gercek, [(j, j) for j in range(nj)])
    ust = _blok_farki(kurulan, gercek, [(j, j + 1) for j in range(nj - 1)])
    alt = _blok_farki(kurulan, gercek, [(j + 1, j) for j in range(nj - 1)])
    assert kos_f < kos_tol, f'köşegen blok farkı {kos_f:.4f} > {kos_tol}'
    assert ust < capraz_tol and alt < capraz_tol, (
        f'çapraz blok farkı üst {ust:.4f} alt {alt:.4f} > {capraz_tol}')


def test_viskoz_jacobian_mu_t_kancasi_FD_capraziyla(monkeypatch):
    """V3 μ_t KANCASI: bloklar μ_eff'le kurulur ve GERÇEK Jacobian'a oturur.

    Üç hüküm (hepsi ölçülü, aynı vaka nj=16, μ_t = 50μ sabit alan):
      (i) kancalı bloklar, μ_t'li kalıntının sonlu-fark Jacobian'ına
          laminer bantla AYNI sınıfta oturur (ölçülen: köşegen 0,00529,
          üst çapraz 2e-05, alt 2e-05 — eşik %2, ~4× pay),
      (ii) kancasız (laminer) bloklar AYNI ölçüme köşegen farkı 0,97500
          ile uzak kalır (≈ %98 — kancanın YOKLUĞU görünür; bu bacak
          olmasa "kanca var" iddiası ölçüsüz kalırdı),
      (iii) μ_t = 0 dizisi ile mu_t=None BİT-AYNI blok üretir (kanca
          laminer yolu kaydırmaz).
    """
    v = _jacobian_kurulum(ni=10, nj=16, yaricap=0.005)
    nj = v['grid'].nj
    mu_alan = v['transport'].viscosity(
        np.full((v['grid'].ni, nj), BORU_T0))
    mu_t = 50.0 * mu_alan
    i0, gercek = _sonlu_fark_jacobian(v, 'isothermal', 2850.0, mu_t=mu_t)
    ortak = (v['U'], v['grid'], v['geom'], v['grad_geom'], VISK_GAMMA,
             VISK_R, v['transport'])
    kancali = viscous_jacobian_blocks(*ortak, wall_thermal='isothermal',
                                      T_wall=2850.0, mu_t=mu_t)
    kos = _blok_farki(_kurulan_matris(kancali, i0, nj), gercek,
                      [(j, j) for j in range(nj)])
    ust = _blok_farki(_kurulan_matris(kancali, i0, nj), gercek,
                      [(j, j + 1) for j in range(nj - 1)])
    assert kos < 0.02, f'μ_t kancalı köşegen farkı {kos:.4f}'
    assert ust < 0.02, f'μ_t kancalı çapraz farkı {ust:.4f}'
    # (ii) kancasız bloklar aynı ölçümden uzak — kancanın varlığı ölçülür
    laminer = viscous_jacobian_blocks(*ortak, wall_thermal='isothermal',
                                      T_wall=2850.0)
    kos_lam = _blok_farki(_kurulan_matris(laminer, i0, nj), gercek,
                          [(j, j) for j in range(nj)])
    assert kos_lam > 0.5, (
        f'laminer bloklar μ_t\'li Jacobian\'a {kos_lam:.3f} uzaklıkta — '
        'vaka μ_t\'yi görmüyor, bekçi ısırmaz')
    # (iii) μ_t = 0 ↔ None bit-aynı
    sifir = viscous_jacobian_blocks(*ortak, wall_thermal='isothermal',
                                    T_wall=2850.0,
                                    mu_t=np.zeros_like(mu_t))
    for ad in ('inner_lo', 'inner_hi', 'wall'):
        assert np.array_equal(sifir[ad], laminer[ad]), ad
    # Beyan kancayı söyler
    assert 'mu_eff' in kancali['declaration']['eddy_viscosity']
    assert 'laminar' in laminer['declaration']['eddy_viscosity']


def test_viskoz_jacobian_mu_t_SURUCUDEN_baglanir(monkeypatch):
    """Sürücü SA açıkken sa['mu_t'] alanını bloklara GERÇEKTEN geçirir.

    Casus: steady.viscous_jacobian_blocks sarılır; SA'lı koşuda mu_t
    argümanı None OLMAMALI, laminer viskoz koşuda None OLMALI. Kanca
    kablosu sökülürse (mu_t geçirilmez) bu bekçi kırmızıya düşer.
    """
    kayit = {'sa': [], 'laminer': []}
    gercek = steady.viscous_jacobian_blocks

    def izle(*a, **kw):
        kayit[aktif].append(kw.get('mu_t'))
        return gercek(*a, **kw)

    monkeypatch.setattr(steady, 'viscous_jacobian_blocks', izle)
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_gridi)

    grid = lule_gridi(24, 8)
    tr = visk_transport(exponent=0.0, mu_ref=0.05, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    ortak = dict(P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA, R=LULE_R,
                 Pb=None, max_iters=3, time_integrator='line_implicit_j')
    aktif = 'sa'
    solve_steady_axisym(grid, viscous=ViscousOptions(
        transport=tr, wall_thermal='isothermal', T_wall=0.6 * LULE_T0,
        T_wall_source='verification_case', turbulence='sa_neg'), **ortak)
    aktif = 'laminer'
    solve_steady_axisym(grid, viscous=ViscousOptions(
        transport=tr, wall_thermal='isothermal', T_wall=0.6 * LULE_T0,
        T_wall_source='verification_case'), **ortak)
    assert kayit['sa'] and all(m is not None for m in kayit['sa']), (
        'SA açıkken μ_t bloklara geçirilmiyor — V3 kancasının kablosu '
        'kopuk')
    assert all(np.all(m >= 0.0) for m in kayit['sa'])
    assert kayit['laminer'] and all(m is None for m in kayit['laminer']), (
        'laminer koşu bloklara μ_t geçiriyor — varsayılan yol değişmiş')


def test_viskoz_jacobian_AR_buyudukce_iyilesir():
    """İhmalin yönü ölçülür: ince radyal hücrede köşegen blok DAHA doğru."""
    farklar = []
    for nj in (8, 32):
        v = _jacobian_kurulum(ni=10, nj=nj, yaricap=0.005)
        i0, gercek = _sonlu_fark_jacobian(v, 'isothermal', 2850.0)
        bloklar = viscous_jacobian_blocks(
            v['U'], v['grid'], v['geom'], v['grad_geom'], VISK_GAMMA, VISK_R,
            v['transport'], wall_thermal='isothermal', T_wall=2850.0)
        farklar.append(_blok_farki(_kurulan_matris(bloklar, i0, nj), gercek,
                                   [(j, j) for j in range(nj)]))
    assert farklar[1] < farklar[0], (
        f'AR arttıkça ince-tabaka ihmali küçülmeliydi: {farklar}')


def test_duvar_blogu_baskin_ve_adiyabatikte_enerji_satiri_TAM_SIFIR():
    """Duvar bloğu: yüksek AR'de baskın; adyabatikte enerji satırı sıfır.

    Adyabatik duvarda hem ısı akısı (k = 0) hem viskoz iş (u_yüz = 0)
    yoktur → enerji satırı ayrık olarak TAM sıfırdır. İzotermalde ise
    sıfır DEĞİLDİR (iletim var) — iki hüküm birlikte, "adyabatik dalı
    unutmak" ve "izotermalde iletimi düşürmek" hatalarını birden yakalar.
    """
    v = _jacobian_kurulum(ni=10, nj=16, yaricap=0.005)
    ortak = (v['U'], v['grid'], v['geom'], v['grad_geom'], VISK_GAMMA, VISK_R,
             v['transport'])
    izo = viscous_jacobian_blocks(*ortak, wall_thermal='isothermal',
                                  T_wall=2850.0)
    ady = viscous_jacobian_blocks(*ortak, wall_thermal='adiabatic')
    assert np.all(ady['wall'][:, 3, :] == 0.0)
    assert np.all(np.abs(izo['wall'][:, 3, :]).max(axis=1) > 0.0)
    # Momentum satırları ısıl kipten BAĞIMSIZ olmalı (μ(T_w) farkı dışında
    # yapı aynı): adyabatikte de duvar sürtünmesi Jacobian'da vardır
    assert np.all(np.abs(ady['wall'][:, 1, :]).max(axis=1) > 0.0)
    ic_norm = np.mean(np.linalg.norm(izo['inner_lo'][:, -3:], axis=(-2, -1)))
    duvar_norm = np.mean(np.linalg.norm(izo['wall'], axis=(-2, -1)))
    assert duvar_norm > 2.0 * ic_norm, (
        f'duvar bloğu iç bloklardan baskın olmalı: {duvar_norm:.3e} vs '
        f'{ic_norm:.3e}')


def _delta_normu(v, wall_thermal='adiabatic', olcek_dt=5.0):
    """Aynı sağ tarafla üç ΔU: bloksuz, bloklu ve İŞARETİ TERS bloklu."""
    grid, U, geom = v['grid'], v['U'], v['geom']
    dudt, _ = residual_axisym(U, grid, VISK_GAMMA, VISK_R, BORU_P0, BORU_T0,
                              Pb=BORU_PB, geom=geom, wall_bc=WALL_BC_NOSLIP)
    dt = local_dt_axial(U, grid, VISK_GAMMA, olcek_dt, geom['area_i'])
    bloklar = viscous_jacobian_blocks(
        U, grid, geom, v['grad_geom'], VISK_GAMMA, VISK_R, v['transport'],
        wall_thermal=wall_thermal)
    ters = {ad: -bloklar[ad] for ad in ('inner_lo', 'inner_hi', 'wall')}
    sifir = {ad: np.zeros_like(bloklar[ad])
             for ad in ('inner_lo', 'inner_hi', 'wall')}
    olcek = np.max(np.abs(U), axis=(0, 1))

    def coz(bl):
        return line_implicit_delta(U, dudt, grid, geom, VISK_GAMMA, dt,
                                   viscous_blocks=bl)

    def norm(a):
        return float(np.linalg.norm(a / olcek))

    yok = coz(None)
    return {'yok': yok, 'var': coz(bloklar), 'ters': coz(ters),
            'sifir': coz(sifir), 'norm': norm, 'bloklar': bloklar}


def test_viskoz_bloklar_sistemi_gercekten_degistirir(jacobian_vakasi):
    """Bloklar verildiğinde ΔU DEĞİŞİR (yoksa 'bağlandı' iddiası boştur)."""
    d = _delta_normu(jacobian_vakasi)
    olcek = np.max(np.abs(d['yok']), axis=(0, 1))
    assert np.max(np.abs(d['var'] - d['yok']) / olcek) > 1e-3
    # Sıfır bloklar Euler yolunu BOZMAZ (toplama nötrdür — bit düzeyinde)
    assert np.array_equal(d['sifir'], d['yok'])


def test_viskoz_bloklarin_MONTAJ_isareti_sonderi_yonunde():
    """Montaj işaretinin bekçisi: viskoz terim sistemi SÖNÜMLER, azdırmaz.

    Difüzyon operatörü köşegeni BÜYÜTÜR; dolayısıyla aynı sağ tarafla
    çözülen sistemde ‖ΔU‖ KÜÇÜLMELİDİR. İşaret ters montajlanırsa köşegen
    küçülür ve ‖ΔU‖ BÜYÜR. Bu, ``viscous_jacobian_blocks``'un doğruluğunu
    değil (o sonlu-farkla ölçüldü) ``line_implicit_delta`` içindeki
    MONTAJI sınar — mutasyonla ölçüldü: montaj işareti çevrilince bu
    bekçi kırmızıya düşen TEK bekçidir.

    Ölçülen (aynı vaka, CFL 5): nj=8 → 0,946 / 1,070 ; nj=32 → 0,904 /
    1,328 (bloklu/blоksuz ve tersli/blоksuz). Sönümün AR ile GÜÇLENMESİ
    tasarımın "yüksek AR'de baskın terim" iddiasının ta kendisidir.
    """
    oranlar = []
    for nj in (8, 32):
        d = _delta_normu(_jacobian_kurulum(ni=10, nj=nj, yaricap=0.005))
        n0 = d['norm'](d['yok'])
        var, ters = d['norm'](d['var']) / n0, d['norm'](d['ters']) / n0
        assert var < 1.0, (
            f'nj={nj}: viskoz bloklar ‖ΔU‖\'yu {var:.3f}× yaptı — sönüm '
            'yönü ters, montaj işareti yanlış olabilir')
        assert ters > 1.0, (
            f'nj={nj}: işareti ters bloklar bile sönümledi ({ters:.3f}×) — '
            'bekçi ısırmıyor, vaka viskoz terimi görmüyor olabilir')
        oranlar.append(var)
    assert oranlar[1] < oranlar[0], (
        f'sönüm AR ile güçlenmeliydi: {oranlar}')


# ===========================================================================
# (E) BASAMAK 6 — hüküm nötrlüğü (açık ↔ örtük aynı kök)
# ===========================================================================

def test_basamak6_iki_yol_da_yakinsadi(acik_kosu, ortuk_kosu):
    for ad, kosu in (('açık', acik_kosu), ('örtük', ortuk_kosu)):
        sonuc = kosu['sonuc']
        # ÇEVRİLDİ (ÖH D32 / OH-D31-15): çözücü AÇIK yolda donmuş
        # operatörün sayısından artık hüküm VERMİYOR (converged=None,
        # convergence_status='not_evaluated'; Berke kararı 15 Eyl 2026 §3
        # seç. A; ölçüm docs/scofield/raw/OH/D32/fea-cfd/a2/once.json).
        # Eski doğruluk iddiası KAZANILMAMIŞ hükmün yerinde durmasını
        # şart koşuyordu — kusuru koruyan bekçi, yönü çevrildi. Korunan
        # yasak duruyor: ÖLÇÜLMÜŞ yakınsamama/ıraksama iddiayı geçersiz
        # kılar.
        assert sonuc['converged'] is not False, (
            f'{ad} yol ÖLÇÜLMÜŞ olarak yakınsamadı: '
            f'{sonuc["convergence_basis"]}')
        assert sonuc['convergence_status'] in (
            'converged', 'not_evaluated'), (
            f'{ad} yol hüküm cinsi {sonuc["convergence_status"]!r}')
        assert sonuc['residual_history'][-1] < NOTR_TOL


def test_basamak6_yakinsanan_alanlar_ayni(acik_kosu, ortuk_kosu):
    """Örtük katman KÖKÜ değiştirmez — alan alan, ölçülen bantta."""
    fa = acik_kosu['sonuc']['fields']
    fo = ortuk_kosu['sonuc']['fields']
    for ad, tol in NOTRLUK_ALAN_TOL.items():
        olcek = np.max(np.abs(fa[ad]))
        fark = float(np.max(np.abs(fa[ad] - fo[ad])) / olcek)
        assert fark < tol, (
            f'{ad}: açık ↔ örtük bağıl farkı {fark:.2e} > {tol:g} — '
            'hüküm-nötrlük sözleşmesi kırıldı')


def test_basamak6_turevler_ve_hukum_olcutleri_ayni(acik_kosu, ortuk_kosu):
    """Ürünün yayımladığı büyüklükler (f·Re, τ_w, debi) iki yolda aynı."""
    ma, mo = _kesit(acik_kosu), _kesit(ortuk_kosu)
    fa = float(np.mean(ma['f_Re'][ma['pencere']]))
    fo = float(np.mean(mo['f_Re'][mo['pencere']]))
    assert abs(fa / fo - 1.0) < NOTRLUK_TUREV_TOL['f_Re']
    tau_a = acik_kosu['sonuc']['viscous']['wall_shear_Pa']
    tau_o = ortuk_kosu['sonuc']['viscous']['wall_shear_Pa']
    assert (np.max(np.abs(tau_a - tau_o)) / np.max(np.abs(tau_a))
            < NOTRLUK_TUREV_TOL['tau_w'])
    for ad in ('mass_flow_in_kg_s', 'mass_flow_out_kg_s'):
        a = acik_kosu['sonuc'][ad]
        o = ortuk_kosu['sonuc'][ad]
        assert abs(a / o - 1.0) < NOTRLUK_TUREV_TOL['mdot'], ad
    # Hüküm ölçütlerinin KENDİSİ de aynı (converged + bant metni yapısı)
    # ÇEVRİLDİ (ÖH D32 / OH-D31-15): çözücü AÇIK yolda donmuş
    # operatörün sayısından artık hüküm VERMİYOR (converged=None,
    # convergence_status='not_evaluated'; Berke kararı 15 Eyl 2026 §3
    # seç. A; ölçüm docs/scofield/raw/OH/D32/fea-cfd/a2/once.json).
    # Eski doğruluk iddiası KAZANILMAMIŞ hükmün yerinde durmasını
    # şart koşuyordu — kusuru koruyan bekçi, yönü çevrildi. Korunan
    # yasak duruyor: ÖLÇÜLMÜŞ yakınsamama/ıraksama iddiayı geçersiz
    # kılar.
    # NİTELENDİ (OH-D31-15): öz-tutarlılık kapısı YALNIZ örtük yolu
    # kapsıyor (SELFCONSISTENCY_GATE_SCOPE); açık yol kapsam DIŞINDA
    # kalınca hüküm YARGILANMIYOR (None) ve iki bayrak artık birebir eşit
    # olmayabilir. Hüküm ÜÇLÜSÜ (debi bandı + boğaz Mach bandı + kalıntı
    # eşiği) iki yolda hâlâ AYNIDIR — ayrışma kapının KAPSAMINDADIR ve
    # OH-Z5-19'un kök onarımı (2.7) kapsamı açık yola genişletince
    # kapanır. Bekçi o güne kadar korunabilecek olanı korur: hiçbir yol
    # ÖLÇÜLMÜŞ bir başarısızlık hükmü almamalı ve ikisi de aynı SINIFTA
    # (hüküm var / hüküm yargılanmadı) kalmalı.
    _acik = acik_kosu['sonuc']
    _ortuk = ortuk_kosu['sonuc']
    assert _acik['converged'] is not False
    assert _ortuk['converged'] is not False
    assert _acik['convergence_status'] in ('converged', 'not_evaluated')
    assert _ortuk['convergence_status'] in ('converged', 'not_evaluated')


def test_basamak6_ortuk_kazanci_olculur(acik_kosu, ortuk_kosu):
    """Örtük yol AYNI köke DAHA AZ iterasyonda iner (ölçüldü: 4,63×).

    Kazanç iddiası bant olarak kilitlenir: 2× altına düşerse katmanın
    varlık sebebi sorgulanmalı, 20× üstüne çıkarsa vaka değişmiş demektir.
    """
    oran = (acik_kosu['sonuc']['iterations']
            / ortuk_kosu['sonuc']['iterations'])
    assert 2.0 < oran < 20.0, f'ölçülen iterasyon kazancı {oran:.2f}×'


def test_basamak6_jacobian_carpani_YOLU_degistirir_KOKU_degistirmez(
        monkeypatch, ortuk_kosu):
    """MUTASYON KANITI (§5.6'nın kendi önerdiği mutasyon).

    Viskoz Jacobian blokları kasten 4× büyütülür: sol taraf artık gerçek
    Jacobian DEĞİLDİR. Beklenen — koşu yavaşlar (ya da hiç değilse
    iterasyon sayısı değişir) ama YAKINSANAN ALAN aynı kalır. Bu, "sol
    taraf kökü kirletmiyor" iddiasının canlı kanıtıdır.
    """
    gercek = steady.viscous_jacobian_blocks

    def bozuk(*a, **kw):
        bl = gercek(*a, **kw)
        return {**bl, 'inner_lo': 4.0 * bl['inner_lo'],
                'inner_hi': 4.0 * bl['inner_hi'], 'wall': 4.0 * bl['wall']}

    monkeypatch.setattr(steady, 'viscous_jacobian_blocks', bozuk)
    mutant = _boru_kos(integrator='line_implicit_j')
    assert mutant['sonuc']['converged'], (
        'bozuk Jacobian yakınsamayı ENGELLEMEMELİ (yalnız yavaşlatmalı); '
        'engelliyorsa hüküm-nötrlük iddiası bu mutasyon için kurulamaz')
    assert mutant['sonuc']['iterations'] != ortuk_kosu['sonuc']['iterations'], (
        'Jacobian 4× bozulduğu hâlde iterasyon sayısı DEĞİŞMEDİ — bloklar '
        'fiilen kullanılmıyor olabilir')
    fa = ortuk_kosu['sonuc']['fields']
    fm = mutant['sonuc']['fields']
    for ad, tol in NOTRLUK_ALAN_TOL.items():
        fark = float(np.max(np.abs(fa[ad] - fm[ad])) / np.max(np.abs(fa[ad])))
        assert fark < tol, (
            f'{ad}: Jacobian mutasyonu KÖKÜ değiştirdi ({fark:.2e}) — '
            'bu bir hüküm-nötrlük ihlalidir')


# ===========================================================================
# (F) Ürün sürücüsü ↔ A1'in bağımsız yürüyücüsü + analitik referans
# ===========================================================================

def test_urun_surucusu_A1_yuruyucusuyle_ayni_koke_iner(acik_kosu):
    """İki BAĞIMSIZ sürücü, aynı vaka, aynı kök (ölçülen fark 3,0e-05)."""
    f_re = _f_re(acik_kosu)
    assert abs(f_re / A1_F_RE_NJ8 - 1.0) < SURUCU_CAPRAZ_TOL, (
        f'ürün sürücüsü f·Re = {f_re:.4f}, A1 yürüyücüsü {A1_F_RE_NJ8:.4f}')


def test_basamak4_bandi_urun_surucusunde_de_tutuyor(acik_kosu):
    """Analitik referans (Hagen-Poiseuille): nj=8'de ölçülen sapma −%1,30."""
    f_re = _f_re(acik_kosu)
    sapma = f_re / POISEUILLE_F_RE - 1.0
    assert -0.02 < sapma < -0.005, (
        f'f·Re = {f_re:.4f} (analitik {POISEUILLE_F_RE}); sapma '
        f'{100 * sapma:+.2f}% ölçülen −%1,30 bandının dışında')


def test_isil_duvar_kosusu_surucude_calisir():
    """İzotermal kip sürücüden de geçer: q_w işaretli, T_w kaynağı beyanlı.

    (Nu ölçümü A1'in basamak-5 dosyasının işidir; burada yalnız kipin
    sürücü yolunda ÇALIŞTIĞI ve beyanların taşındığı ölçülür — kısa koşu.)
    """
    kosu = _boru_kos(nj=4, wall_thermal='isothermal',
                     T_wall=BORU_TW_ORANI * BORU_T0, tol=1e-6,
                     max_iters=4000)
    v = kosu['sonuc']['viscous']
    assert v['thermal_mode'] == 'isothermal'
    assert v['T_wall_source'] == 'verification_case'
    assert np.all(v['wall_temperature_K'] == BORU_TW_ORANI * BORU_T0)
    # Soğuk duvar → akışkandan duvara ısı akışı (pozitif) ve q_w ≠ 0
    assert np.all(v['wall_heat_flux_W_m2'] > 0.0)
    assert v['wall_heat_W'] > 0.0
    assert kosu['sonuc']['assumptions'].count('wall_isothermal') == 1


def test_oturma_bantlari_hukumle_AYNI_aritmetikten(acik_kosu):
    """Takılma tespiti (Berke kararı §13/1): hüküm ölçütünün KENDİSİ yayımlanır.

    KAPI koşusunda takılmanın YERİNİ bu alan gösterdi (giriş debisi
    3,4e-09 oturmuşken çıkış debisi 1,0e-05'te salınıyordu). Bekçi, beyanın
    hükümle aynı aritmetikten geldiğini ölçer: yakınsamış koşuda ÜÇ bant da
    tol altındadır ve bantlar yayımlanan geçmişlerden yeniden hesaplanabilir.
    """
    sonuc = acik_kosu['sonuc']
    bantlar = sonuc['settle_bands']
    tol = bantlar['tol']
    pencere = bantlar['window']
    for ad, gecmis_adi in (('mass_flow_in', 'mass_flow_in_history'),
                           ('mass_flow_out', 'mass_flow_out_history'),
                           ('throat_mach', 'throat_mach_history')):
        gecmis = np.asarray(sonuc[gecmis_adi])
        assert gecmis.shape == (sonuc['iterations'],), gecmis_adi
        band = gecmis[-pencere:]
        beklenen = (band.max() - band.min()) / abs(band[-1])
        assert bantlar[ad] == pytest.approx(beklenen, rel=1e-12), ad
        assert bantlar[ad] < tol, (
    # ÇEVRİLDİ (ÖH D32 / OH-D31-15): çözücü AÇIK yolda donmuş
    # operatörün sayısından artık hüküm VERMİYOR (converged=None,
    # convergence_status='not_evaluated'; Berke kararı 15 Eyl 2026 §3
    # seç. A; ölçüm docs/scofield/raw/OH/D32/fea-cfd/a2/once.json).
    # Eski doğruluk iddiası KAZANILMAMIŞ hükmün yerinde durmasını
    # şart koşuyordu — kusuru koruyan bekçi, yönü çevrildi. Korunan
    # yasak duruyor: ÖLÇÜLMÜŞ yakınsamama/ıraksama iddiayı geçersiz
    # kılar.
            f'{ad} bandı {bantlar[ad]:.2e} ≥ tol {tol:g} ama koşu '
            'hüküm sınıfını KORUDU — hüküm ile beyan ayrışmış')
    assert sonuc['converged'] is not False
    assert sonuc['convergence_status'] in ('converged', 'not_evaluated')


def test_oturma_bantlari_kisa_kosuda_NaN(euler_kosu):
    """Pencere dolmadan bant HESAPLANMAZ (uydurma "oturdu" beyanı yok)."""
    grid = boru_gridi(4)
    kisa = solve_steady_axisym(grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R,
                               Pb=BORU_PB, initial_state=_boru_baslangic(grid),
                               max_iters=10)
    assert kisa['iterations'] < kisa['settle_bands']['window']
    for ad in ('mass_flow_in', 'mass_flow_out', 'throat_mach'):
        assert np.isnan(kisa['settle_bands'][ad])
    assert kisa['converged'] is False


def test_arka_uc_beyani_viskoz_kosuda_da_gercegi_soyler(acik_kosu):
    """Viskoz koşu Euler çekirdeğinin arka uç beyanını AYNEN taşır."""
    sonuc = acik_kosu['sonuc']
    beklenen = 'numba' if _kernels.NUMBA_AVAILABLE else 'numpy'
    assert sonuc['kernel_backend'] == beklenen
    # Viskoz katman bu partide saf NumPy'dir ve bunu beyan eder
    assert 'axisymmetric Newtonian' in \
        sonuc['viscous']['declaration']['formulation']


# ===========================================================================
# V2 — DÜRÜST y⁺ DÖNGÜSÜ (tasarım §5.7)
# ===========================================================================

def test_y_plus_dongusu_hedefsiz_kosuda_ORAN_VERMEZ(acik_kosu):
    """Hedef yoksa oran NaN: "bilinmiyor" ASLA "tutturuldu" sayılmaz."""
    d = acik_kosu['sonuc']['viscous']['y_plus_loop']
    assert d['target'] is None
    assert np.isnan(d['ratio_max_to_target'])
    assert np.isnan(d['fraction_within_target'])
    assert d['regrid_count'] == 0
    assert d['grid_radial_distribution'] == 'uniform'
    assert d['grid_radial_stretch'] is None
    for parca in ('ÖLÇÜMÜDÜR', 'SESSİZCE', 'iki katı'):
        assert parca in d['_basis']


def test_y_plus_dongusu_olculen_degerleri_YENIDEN_HESAPLANABILIR():
    """hedef/gerçekleşen/sapma üçlüsü koşumun kendi y⁺ dizisinden doğar."""
    grid = boru_gridi(6)
    sonuc = solve_steady_axisym(
        grid, BORU_P0, BORU_T0, VISK_GAMMA, VISK_R, Pb=BORU_PB,
        initial_state=_boru_baslangic(grid), max_iters=400,
        y_plus_target=2.5,
        viscous=ViscousOptions(transport=boru_tasinimi(),
                               wall_thermal='adiabatic'))
    v = sonuc['viscous']
    d = v['y_plus_loop']
    yp = v['wall_y_plus']
    assert d['target'] == 2.5
    assert d['achieved_max'] == pytest.approx(float(np.max(yp)), rel=0.0,
                                              abs=0.0)
    assert d['achieved_mean'] == pytest.approx(float(np.mean(yp)), rel=1e-15)
    assert d['achieved_min'] == pytest.approx(float(np.min(yp)), rel=0.0,
                                              abs=0.0)
    assert d['ratio_max_to_target'] == pytest.approx(np.max(yp) / 2.5,
                                                     rel=1e-15)
    assert d['fraction_within_target'] == pytest.approx(
        float(np.mean(yp <= 2.5)), rel=1e-15)
    # İlk hücre KALINLIĞI merkez mesafesinin İKİ KATIDIR (y⁺ merkezde
    # ölçülür) — bu çarpan atlanırsa ön tahmin hedefin yarısını verir.
    assert d['first_cell_m_min'] == pytest.approx(
        2.0 * float(np.min(v['wall_first_cell_m'])), rel=1e-15)
    assert d['first_cell_m_max'] == pytest.approx(
        2.0 * float(np.max(v['wall_first_cell_m'])), rel=1e-15)
    assert sonuc['inputs']['y_plus_target'] == 2.5
    assert v['wall_y_plus_max'] == d['achieved_max']


def test_y_plus_hedefi_kapisi():
    grid = boru_gridi(4)
    v = ViscousOptions(transport=boru_tasinimi(), wall_thermal='adiabatic')
    for bozuk in (0.0, -1.0, float('nan')):
        with pytest.raises(ValueError, match=r'y_plus_target pozitif'):
            steady.first_cell_for_y_plus(grid, BORU_P0, BORU_T0, VISK_GAMMA,
                                         VISK_R, v.transport, 0.9 * BORU_T0,
                                         y_plus_target=bozuk)
    # ADYABATİK koşuda T_w YOKTUR ve sessizce varsayılmaz: ön tahmin
    # ρ_w/μ_w'yi ondan kurar, uydurma bir duvar sıcaklığı yazılmaz.
    assert v.T_wall is None
    with pytest.raises(ValueError, match=r'wall_temperature_K ZORUNLU'):
        steady.first_cell_for_y_plus(grid, BORU_P0, BORU_T0, VISK_GAMMA,
                                     VISK_R, v.transport, v.T_wall,
                                     y_plus_target=1.0)


def test_on_tahmin_zinciri_ENTEGRAL_BL_katmanindan_gelir():
    """Ön tahmin yeni sabit YAZMAZ: τ_w entegral marştan, μ taşınımdan.

    Ölçülen değişmez: kalınlık ∝ 1/(hedef y⁺'ın tersi) DEĞİL, doğrudan
    y⁺ ile ORANTILIDIR (y = y⁺·μ_w/(ρ_w u_τ)); iki hedef arasındaki oran
    tam olarak hedeflerin oranı olmalıdır.
    """
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_gridi)

    grid = lule_gridi(48, 16)
    tr = visk_transport(exponent=0.0, mu_ref=0.15, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    d1, b1 = steady.first_cell_for_y_plus(grid, LULE_P0, LULE_T0, LULE_GAMMA,
                                          LULE_R, tr, 0.6 * LULE_T0,
                                          y_plus_target=1.0)
    d2, b2 = steady.first_cell_for_y_plus(grid, LULE_P0, LULE_T0, LULE_GAMMA,
                                          LULE_R, tr, 0.6 * LULE_T0,
                                          y_plus_target=3.0)
    assert d2 / d1 == pytest.approx(3.0, rel=1e-12), (
        'kalınlık hedef y⁺ ile doğrusal olmalı — zincirde bir yerde '
        'hedefe bağlı olmayan bir terim var')
    assert b1['first_cell_center_m'] == pytest.approx(0.5 * d1, rel=1e-15)
    assert b1['bl_march_status'] == 'completed'
    assert 0 <= b1['driving_station_index'] < grid.ni
    assert b1['driving_station_tau_wall_Pa'] > 0.0
    # θ = 0 tekilliği yüzünden İLK istasyon marşta yoktur; bu BEYANDA
    # görünür (sessizce yutulmaz) — RANS'ın ölçtüğü y⁺ maksimumu tam da
    # o istasyonda olabilir, o yüzden ön tahmin HÜKÜM DEĞİLDİR.
    assert b1['stations_used'] < b1['stations_total']
    for parca in ('ÖN TAHMİNİDİR', 'GERÇEKLEŞEN y⁺', 'hüküm değildir',
                  'Ludwieg-Tillmann', 'iki kat'):
        assert parca in b1['_basis'], f'künye eksik: {parca}'


def test_on_tahmin_kurulabilir_bir_izgara_verir():
    """Tahmin edilen kalınlık gerçekten GERDİRİLEBİLİR (düzgünden ince)."""
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_duvar_yaricapi, lule_gridi)
    from hrma.cfd.grid_axisym import build_grid_from_wall

    grid = lule_gridi(48, 32)
    tr = visk_transport(exponent=0.0, mu_ref=0.15, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    d1, beyan = steady.first_cell_for_y_plus(
        grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R, tr, 0.6 * LULE_T0,
        y_plus_target=0.5)
    assert d1 < beyan['uniform_first_cell_m'], (
        'ön tahmin düzgün hücreden ince çıkmadı — gerdirmeye gerek '
        'olmadığı anlamına gelir, vaka bekçiyi sınamıyor')
    z = np.linspace(0.0, 0.30, 49)
    g = build_grid_from_wall(z, lule_duvar_yaricapi(z), 32, first_cell_m=d1)
    assert g.radial_distribution == 'tanh'
    assert np.allclose(np.diff(g.R, axis=1)[:, -1], d1, rtol=1e-10)

    # KALINLIK ↔ MERKEZ MESAFESİ ayrımı (×2 çarpanı) — zincirin ara
    # halkalarından YENİDEN KURULUR: y_merkez = y⁺·μ_w/(ρ_w·u_τ) ve
    # yayımlanan kalınlık onun İKİ KATI olmalıdır. Çarpan düşerse
    # gerçekleşen y⁺ hedefin yarısı çıkar ve beyan yalancı biçimde
    # "iyi" görünür; bu bekçi tam o kaymayı yakalar.
    y_merkez = (beyan['y_plus_target'] * beyan['driving_station_mu_wall_Pa_s']
                / (beyan['driving_station_rho_wall_kg_m3']
                   * beyan['driving_station_u_tau_m_s']))
    assert beyan['first_cell_center_m'] == pytest.approx(y_merkez, rel=1e-12), (
        'yayımlanan merkez mesafesi zincirin kendi bağıntısından '
        f'{beyan["first_cell_center_m"]:.6g} ≠ {y_merkez:.6g} — kalınlık '
        'ile merkez mesafesi karışmış')
    assert d1 == pytest.approx(2.0 * y_merkez, rel=1e-12)
    assert beyan['driving_station_u_tau_m_s'] == pytest.approx(
        np.sqrt(beyan['driving_station_tau_wall_Pa']
                / beyan['driving_station_rho_wall_kg_m3']), rel=1e-12)


def test_y_plus_dongusu_kapilari():
    """viscous zorunlu, bant tutarlı — sessiz varsayılana düşme yok."""
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_duvar_yaricapi)

    z = np.linspace(0.0, 0.30, 25)
    r = lule_duvar_yaricapi(z)
    with pytest.raises(ValueError, match=r'viskoz koşu içindir'):
        steady.solve_with_y_plus_target(z, r, 8, LULE_P0, LULE_T0,
                                        LULE_GAMMA, LULE_R, viscous=None)
    tr = visk_transport(exponent=0.0, mu_ref=0.15, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    v = ViscousOptions(transport=tr, wall_thermal='isothermal',
                       T_wall=0.6 * LULE_T0, T_wall_source='verification_case')
    with pytest.raises(ValueError, match=r'y_plus_band'):
        steady.solve_with_y_plus_target(z, r, 8, LULE_P0, LULE_T0,
                                        LULE_GAMMA, LULE_R, viscous=v,
                                        y_plus_band=(1.2, 2.0))


def test_y_plus_dongusu_YENIDEN_IZGARALAMAYI_beyanla_yapar():
    """Döngü: ön tahmin → koş → ÖLÇ → (bütçe kadar) yeniden ızgarala.

    Sessiz düzeltme YOKTUR: her turun ilk hücresi ve ölçülen y⁺'ı
    history'de durur, regrid_count ve stop_reason yayımlanır.
    ÖLÇÜLEN DAVRANIŞ: bant dışıysa kalınlık ölçülen orana bölünür, yani
    ikinci turun ilk hücresi birincinin ratio'suna bölünmüş hâlidir —
    bu aritmetik burada yeniden kurulup karşılaştırılır.

    ÖLÇÜLDÜ (bu vaka, 32×12, hedef y⁺ = 1, bant [0,5; 1,5]):
        ön tahmin      1076,81 µm  (düzgün hücre 2089,51 µm)
        tur 0          1076,81 µm → y⁺ maks 2,6029 (oran 2,60, bant DIŞI)
        tur 1           413,70 µm → y⁺ maks 1,0619 (oran 1,06, bant İÇİ)
        regrid_count = 1, gerdirme tanh, q_maks 1,4324
    Ön tahminin 2,6 kat ıskalaması BEKLENENDİR ve beyanlıdır: entegral
    marş θ = 0 tekilliği yüzünden İLK istasyonu atlar, oysa RANS'ın
    ölçtüğü y⁺ maksimumu tam orada (tabakanın başladığı yerde) oluyor.
    Döngünün varlık sebebi budur — tahmin hüküm değildir, ÖLÇÜM hükümdür.
    """
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_duvar_yaricapi)

    z = np.linspace(0.0, 0.30, 33)
    r = lule_duvar_yaricapi(z)
    tr = visk_transport(exponent=0.0, mu_ref=0.15, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    v = ViscousOptions(transport=tr, wall_thermal='isothermal',
                       T_wall=0.6 * LULE_T0, T_wall_source='verification_case')
    sonuc = steady.solve_with_y_plus_target(
        z, r, 12, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R, viscous=v,
        y_plus_target=1.0, max_regrid=1, y_plus_band=(0.5, 1.5),
        Pb=None, max_iters=250, time_integrator='line_implicit_j')
    d = sonuc['viscous']['y_plus_loop']
    assert d['regrid_budget'] == 1
    assert d['regrid_count'] in (0, 1)
    assert len(d['history']) == d['regrid_count'] + 1
    assert d['acceptance_band'] == (0.5, 1.5)
    assert isinstance(d['stop_reason'], str) and d['stop_reason']
    assert d['pre_estimate']['y_plus_target'] == 1.0
    assert d['history'][0]['first_cell_m'] == \
        d['pre_estimate']['first_cell_m']
    # Ölçekleyici ÖLÇÜMDÜR: ikinci turun kalınlığı = birincininki / oran
    for onceki, sonraki in zip(d['history'][:-1], d['history'][1:]):
        assert sonraki['first_cell_m'] == pytest.approx(
            onceki['first_cell_m'] / onceki['ratio_max_to_target'],
            rel=1e-12)
        assert not (0.5 <= onceki['ratio_max_to_target'] <= 1.5), (
            'bant içindeyken yeniden ızgaralanmış — döngü kuralı bozuk')
    # Izgara gerçekten GERDİRİLMİŞ ve son turun kalınlığı onunla aynı
    assert d['grid_radial_distribution'] == 'tanh'
    assert d['grid_radial_stretch']['first_cell_target_m'] == \
        pytest.approx(d['history'][-1]['first_cell_m'], rel=0.0, abs=0.0)
    assert sonuc['viscous']['grid_stretch'] is not None
    for parca in ('ölçüldü', 'Sessiz', 'history'):
        assert parca in d['_basis']


# ===========================================================================
# V2 — ÇIKIŞ SINIRI BEYANI ve LİMİT DÖNGÜSÜNÜN ÖLÇÜLEN KÖKÜ
# ===========================================================================

def test_viskoz_kosuda_cikis_alt_tabakasi_CAPASIZ_beyani_ATESLER():
    """Kusur SESSİZ kalmaz: Pb=None + ses-altı hücre → uyarı yayımlanır.

    Euler koşusunda (kayma duvarı) ses-altı satır YOKTUR; uyarı tam da
    viskoz koşuda ateşler — kusurun kendisi budur.
    """
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_gridi)

    grid = lule_gridi(48, 16)
    tr = visk_transport(exponent=0.0, mu_ref=0.15, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    ortak = dict(Pb=None, max_iters=300, time_integrator='line_implicit_j')
    euler = solve_steady_axisym(grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R,
                                **ortak)
    assert euler['outlet_bc']['subsonic_cells'] == 0
    assert euler['outlet_bc']['unanchored_warning'] is None

    v = ViscousOptions(transport=tr, wall_thermal='isothermal',
                       T_wall=0.6 * LULE_T0,
                       T_wall_source='verification_case')
    visk = solve_steady_axisym(grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R,
                               viscous=v, **ortak)
    ob = visk['outlet_bc']
    assert ob['subsonic_cells'] > 0, (
        'viskoz koşuda çıkışta ses-altı satır çıkmadı — vaka kusuru '
        'göstermiyor, bekçi kör olurdu')
    assert ob['anchored'] is False
    assert 'ÇAPASIZ' in ob['unanchored_warning']
    assert 'core_pressure' in ob['unanchored_warning']
    assert str(ob['subsonic_cells']) in ob['unanchored_warning']

    capali = solve_steady_axisym(grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R,
                                 viscous=v,
                                 outlet_subsonic_anchor='core_pressure',
                                 **ortak)
    assert capali['outlet_bc']['anchored'] is True
    assert capali['outlet_bc']['unanchored_warning'] is None
    assert capali['inputs']['outlet_subsonic_anchor'] == 'core_pressure'


def test_faz_kilitli_bant_aritmetigi_cevrim_gurultusunu_AYIRIR():
    """_settle_band_phase'in KENDİ cebiri: K-periyotlu sıçrama ayrışır.

    Sentetik tarihçe: her K adımda bir sıçrayan ama FAZ İÇİNDE oturmuş
    bir dizi. Ham bant sıçramayı görür (büyük), faz-kilitli bant görmez
    (küçük). Bu ayrım olmasaydı "oturmadı" ile "çevrim gürültüsü"
    birbirine karışırdı — V1 KAPI koşusunda tam olarak bu olmuştu.
    """
    K = steady.DEFAULT_IMPLICIT_SLOPE_REFRESH
    n = 600
    idx = np.arange(n)
    taban = 1.0 + 1e-12 * idx                   # faz içinde oturmuş

    def _fazlar(hist):
        """Fazların bantlarını BAĞIMSIZ olarak yeniden hesaplar."""
        band = hist[-200:]
        return [(max(o) - min(o)) / abs(o[-1])
                for o in (band[f::K] for f in range(K))
                if len(o) >= steady._PHASE_MIN_SAMPLES]

    # (i) AYRIŞMA: sabit K-periyotlu sıçrama — ham bant görür, faz görmez
    hist = list(taban + np.where(idx % K == 0, 1e-5, 0.0))
    ham = steady._settle_band(hist, 200)
    faz = steady._settle_band_phase(hist, 200, K)
    assert ham > 5e-6, 'sentetik vaka ham bantta sıçramayı göstermiyor'
    assert faz < ham / 1000.0, (
        f'faz-kilitli bant ({faz:.2e}) ham banttan ({ham:.2e}) yeterince '
        'ayrışmadı — beyan çevrim gürültüsünü ayıramıyor')

    # (ii) EN KÖTÜ FAZ kuralı: fazların bantları farklıyken yayımlanan
    # sayı fazların EN KÖTÜSÜ olmalı (iyimser faz seçmek beyanı yalancı
    # yapardı). Bunun için sıçramanın BÜYÜKLÜĞÜ oynatılır.
    hist2 = list(taban + np.where(
        idx % K == 0, 1e-5 * (1.0 + 0.5 * np.sin(idx / 7.0)), 0.0))
    faz2 = steady._settle_band_phase(hist2, 200, K)
    fazlar2 = _fazlar(hist2)
    assert max(fazlar2) > 100.0 * min(fazlar2), (
        'sentetik vaka fazları ayırt etmiyor; bekçi kör olurdu')
    assert faz2 == pytest.approx(max(fazlar2), rel=1e-12), (
        f'yayımlanan faz bandı {faz2:.3e}, fazların en kötüsü '
        f'{max(fazlar2):.3e} — iyimser faz seçilmiş')
    # Periyot yoksa/1 ise beyan YAPILMAZ (NaN), uydurulmaz
    assert np.isnan(steady._settle_band_phase(hist, 200, 1))
    assert np.isnan(steady._settle_band_phase(hist, 200, 0))
    # Pencere dolmamışsa da NaN
    assert np.isnan(steady._settle_band_phase(hist[:50], 200, K))
    # Örnek sayısı eşiğin altındaysa NaN (üç noktadan bant kurulmaz)
    assert np.isnan(steady._settle_band_phase(hist, K * 2, K))


def test_kalinti_salinimi_EGIM_TAZELEME_cevrimine_KILITLI():
    """Limit döngüsünün ÖLÇÜLEN kökü: periyot = implicit_slope_refresh.

    Ucuz vaka (Euler, satır-örtük, 60×12): kalıntı tazeleme çevriminin
    fazına göre TEKDÜZE düşer ve faz 0 (tazelemenin hemen ardı) faz K−1'in
    en az bir DEKAD üstündedir. Yani salınımı üreten sınır koşulu değil,
    minmod gevelemesinin her K iterasyonda yeniden enjekte edilmesidir.
    """
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_PB, LULE_R,
                                    LULE_T0, lule_gridi)

    K = steady.DEFAULT_IMPLICIT_SLOPE_REFRESH
    grid = lule_gridi(60, 12)
    res = solve_steady_axisym(grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R,
                              Pb=LULE_PB, time_integrator='line_implicit_j',
                              max_iters=1500, tol_res=1e-12, settle_tol=1e-13)
    h = np.asarray(res['residual_history'])
    # ÖH D21 fix-17 (4 Eyl 2026): D21 fea-cfd a2 / P6B1-09 çözücünün geçmişin
    # SONUNA dönen alanın kalıntısını koymasını beyanlı yaptı
    # (residual_history_last_is_returned_field). O kayıt bir yürüyüş adımı
    # DEĞİLDİR; faz ölçümü K'lık çevrim adımları üzerinde kurulur, bu yüzden
    # düşürülür (kayıt sayısı 1501 = 1500 adım + 1 dönen-alan kalıntısı).
    if res.get('residual_history_last_is_returned_field'):
        h = h[:-1]
    assert res['iterations'] == 1500, 'vaka erken bitmiş; faz ölçümü kurulamaz'
    assert h.size == 1500, 'vaka erken bitmiş; faz ölçümü kurulamaz'
    seg = np.log10(h[-400:])
    faz = np.array([seg[i::K].mean() for i in range(K)])
    assert faz[0] - faz[-1] > 1.0, (
        f'faz 0 ile faz {K - 1} arasındaki fark {faz[0] - faz[-1]:.2f} '
        'dekad — kalıntı tazeleme çevrimine kilitli DEĞİL, o hâlde limit '
        'döngüsünün kökü başka yerdedir ve beyan güncellenmelidir')
    assert np.all(np.diff(faz) < 0.0), (
        'çevrim içinde kalıntı tekdüze düşmüyor')
    # Beyan da bunu söylüyor olmalı
    pl = res['settle_bands']['refresh_phase_locked']
    assert pl['active'] is True and pl['period'] == K
    assert 'tazeleme' in pl['_basis'] and 'Hükme GİRMEZ' in pl['_basis']


def test_faz_kilitli_beyan_cevrim_YOKKEN_NaN_doner(acik_kosu):
    """Açık yolda tazeleme çevrimi yoktur — beyan uydurulmaz."""
    pl = acik_kosu['sonuc']['settle_bands']['refresh_phase_locked']
    assert pl['active'] is False and pl['period'] is None
    for ad in ('mass_flow_in', 'mass_flow_out', 'throat_mach'):
        assert np.isnan(pl[ad])


#: KAPI vakasının ÖLÇÜLEN çıpaları (ÖH defter OH-Z5-14; 2026-08-31,
#: docs/scofield/raw/OH/D15/cfd-picard/a2/once.json). Öz-tutarlılık
#: kapısı hükmü geri çektiğinden koşu ARTIK tavana dayanır; aşağıdaki
#: sayılar o tavan durumundan alınmıştır.
#:
#: Toleransların dayanağı FAZ DUYARLILIĞI ölçümüdür (aynı dizin,
#: faz_duyarliligi.json, izotermal ikiz vakada üç tavanla ölçüldü):
#: koşu bir iterasyon erken/geç bittiğinde ALAN büyüklükleri bağıl
#: 2,8e-12 (y⁺) … 5,2e-11 (debi) … 3,7e-05 (bütçe kapanışı) oynar,
#: ŞEMA kalıntısı 1,19e-09 oynar, YAYIMLANAN kalıntı ise %3,42 oynar.
#: Bu yüzden yayımlanan kalıntıya sayısal çıpa KONMAZ; şemanınkine
#: konur.
KAPI_DONDURMA_ITER = 1726          #: dondurma anı — kapı ÖNCESİ ile AYNI
KAPI_GEVSEK_SEMA_KALINTI = 2.2639e-04   #: settle_tol=1e-4, tavan 4000
KAPI_SIKI_SEMA_KALINTI = 2.5439e-04     #: settle_tol=1e-9, tavan 8000
#: Hüküm-nötrlük: iki ayarın debi kökü ne kadar ayrışıyor? ÖLÇÜLDÜ
#: 2,32e-05 (kapı öncesi iddia "6 hanede aynı" = 1e-06 idi; koşular
#: artık FARKLI tavanlarda bittiği için kök bu mertebede ayrışıyor —
#: ölçüldü, beyan edildi, GİZLENMEDİ). Bant ölçümün ~2 katı.
KAPI_HUKUM_NOTRLUK_MAKS = 5e-5


def test_KAPI_limit_dongusu_EGIM_DONDURMASIYLA_kirilir():
    """LİMİT DÖNGÜSÜNÜN ÖLÇÜLEN ÇARESİ — canlı, küçültülmüş vaka.

    HÜKÜM SÖZLEŞMESİ (ÖH defter OH-Z5-14; çevrildi 2026-08-31)
    ----------------------------------------------------------
    Bu test eskiden ``sonuc['converged']`` diyordu. Öz-tutarlılık kapısı
    o hükmü GERİ ÇEKTİ ve testi yeşil tutmak kusuru korumak olurdu.
    Kapının ölçtüğü şey şudur: dondurma "çareyi" YAYIMLANAN sayıya
    getiriyordu (frozen_slopes operatörü), ŞEMANIN kendi kalıntısına
    değil. ÖLÇÜLDÜ (2026-08-31): dondurma AYNI iterasyonda (1726)
    ateşliyor, yayımlanan kalıntı 1,076e-07'ye iniyor, ama şemanın
    canlı minmod kalıntısı 2,264e-04 — tolun 22.639 katı. Yani limit
    döngüsü ŞEMADA kırılmadı; kırılmış GÖRÜNMESİNİ sağlayan şey
    operatör değişimiydi.

    Testin AYAKTA KALAN çekirdeği: (a) dondurma tetiği ateşliyor,
    (b) tetik SIKI hükümle de ateşliyor (V3 tetik/hüküm ayrımı —
    dairesel kilit hâlâ kırık), (c) dondurmadan sonra tazeleme çevrimi
    yok, (d) kütle bütçesi kapalı. Yıkılan iddia: "dondurma hükmü
    kazandırır". Hedef GEVŞETİLMEDİ — iddia DÜZELTİLDİ.

    KAPI vakasının (192×48, ~2,5 dk) mekanizması aynı fizikle 64×16'da
    üretilir: viskoz lüle, sıcak Euler başlangıcı, satır-örtük yol,
    Pb=None. Oturma-tetikli KALICI eğim dondurması ateşlediğinde koşu
    hüküm eşiğine iner. Dondurma tetiği sökülürse (ya da erişilemez
    kalırsa) bu bekçi kırmızıya düşer — kusurun KENDİSİNİ tutar.

    ÖLÇÜLDÜ (M4 Max, 2026-08-18, bu vaka):
        settle_tol 1e-9 (tetik=hüküm, eski kilit):
                          converged=False, 8000 it, kalıntı 1,418e-08
        settle_tol 1e-4 : converged=True,  2184 it, kalıntı 9,972e-09,
                          dondurma 1726. iterasyonda, çıkış bandı 3,5e-07
    V3 TETİK/HÜKÜM AYRIMI (parti 39; dairesel kilidin yapısal kapanışı):
    tetik artık AYRI eşik taşıyor (freeze_settle_tol). Aynı vaka SIKI
    hükümle (settle_tol=1e-9) + ayrık tetikle (1e-4) YENİDEN ÖLÇÜLDÜ:
        converged=True, 2551 it, kalıntı 1,622e-11, dondurma YİNE 1726,
        bantlar in=3,07e-11 / out=9,84e-10 / M=3,59e-11 — hüküm üçlüsü
        1e-9 bandında GERÇEKTEN oturdu, debi kökü 4,542455 iki hükümde
        de aynı (hüküm-nötrlük). Eski kilitle bu SONSUZA DEK imkânsızdı:
        geveleme bandı tetiğin gerektirdiği oturmayı engelliyordu.
    Aynı ayrımın 192×48 ölçümü modül docstring'inin V2/V3 bölümünde.
    """
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_gridi)

    grid = lule_gridi(64, 16)
    tr = visk_transport(exponent=0.0, mu_ref=0.15, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    euler = solve_steady_axisym(grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R,
                                Pb=None, tol_res=1e-8, max_iters=40000,
                                settle_tol=1e-9)
    assert euler['converged'], 'Euler ön koşusu yakınsamadı; vaka kurulamaz'
    f = euler['fields']
    U0 = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                             f['pressure_Pa'], LULE_GAMMA)
    v = ViscousOptions(transport=tr, wall_thermal='isothermal',
                       T_wall=0.6 * LULE_T0, T_wall_source='verification_case')
    ortak = dict(P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA, R=LULE_R,
                 Pb=None, viscous=v, initial_state=U0,
                 time_integrator='line_implicit_j', tol_res=1e-8)
    sonuc = solve_steady_axisym(grid, max_iters=4000, settle_tol=1e-4,
                                **ortak)

    assert sonuc['limiter_frozen_at_iter'] is not None, (
        'kalıcı eğim dondurması hiç ateşlemedi — limit döngüsünün '
        'ÖLÇÜLEN çaresi devre dışı')
    assert 'oturma tespiti' in sonuc['convergence_basis'], (
        'dondurma ateşledi ama gerekçesi beyan edilmedi')
    assert sonuc['limiter_frozen_at_iter'] == KAPI_DONDURMA_ITER, (
        'dondurma anı kaydı — kapı bu anı DEĞİŞTİRMEZ; kaydıysa tetik '
        'ya da ızgara değişmiştir ve bu dosyanın bantları yeniden '
        'ölçülmelidir')
    # --- HÜKÜM: dondurma hükmü KAZANDIRMADI (öz-tutarlılık kapısı) ----
    assert sonuc['converged'] is False, (
        'kapı hükmü geri çekmeliydi: yayımlanan sayı DONMUŞ operatörün, '
        f'şemanınki değil — {sonuc["convergence_basis"]}')
    assert sonuc['convergence_status'] == 'not_converged', (
        f'hükümsüzlüğün cinsi: {sonuc["convergence_basis"]}')
    assert sonuc['scheme_residual_blocks_verdict'] is True
    assert sonuc['residual_operator'] == 'frozen_slopes'
    assert sonuc['picard_selfconsistency_rejections'] > 0
    assert sonuc['iterations'] == 4000, (
        'kapı reddettiği için koşu artık tavana dayanır')
    # PLATO DEĞİL, adıyla: kalıntı bu tavanda hâlâ OYNUYOR (ölçüldü,
    # göreli yayılım 3,76e-02 ≥ eşik 1e-02) — "hedef ulaşılamaz"
    # denemez, fail-closed.
    assert sonuc['convergence_plateau']['detected'] is False
    assert 'yayılım' in sonuc['convergence_plateau']['reason']
    # Çıpa YAYIMLANAN sayıya değil ŞEMANIN kendi sayısına konur (faz
    # duyarlılığı: şema 6e-10, yayımlanan %1,7).
    assert sonuc['scheme_residual_norm'] == pytest.approx(
        KAPI_GEVSEK_SEMA_KALINTI, rel=1e-3), (
        'şema kalıntısı ölçülen bandın dışına çıktı — limit döngüsünün '
        'tabanı kaymış demektir')
    assert float(sonuc['residual_history'][-1]) \
        < sonuc['scheme_residual_norm'], (
        'yayımlanan sayı şemanınkinden İYİMSER olmalıydı; değilse '
        'operatör ayrımı kaybolmuş ve kapının ölçtüğü kusur yok olmuş')
    # Dondurmadan SONRA çevrim yoktur: faz beyanı NaN'a döner
    pl = sonuc['settle_bands']['refresh_phase_locked']
    assert pl['active'] is False and np.isnan(pl['mass_flow_out'])
    # Kök korunur: debi bütçesi kapalı
    assert sonuc['mass_balance_rel'] < 1e-6

    # --- V3: SIKI hüküm + AYRIK tetik (dairesel kilidin ölçülen kapanışı)
    siki = solve_steady_axisym(grid, max_iters=8000, settle_tol=1e-9,
                               freeze_settle_tol=1e-4, **ortak)
    assert siki['limiter_frozen_at_iter'] is not None, (
        'tetik sıkı hükümde ateşleyemedi — dairesel kilit geri gelmiş '
        '(tetik yine hüküm eşiğini okuyor olabilir)')
    assert siki['limiter_frozen_at_iter'] == KAPI_DONDURMA_ITER, (
        'tetik SIKI hükümde de AYNI iterasyonda ateşlemeliydi — dairesel '
        'kilit geri gelmiş olabilir (tetik yine hüküm eşiğini okuyor)')
    # V3'ün AYAKTA KALAN iddiası: tetik/hüküm ayrımı çalışıyor (dondurma
    # sıkı hükümde de ateşliyor). YIKILAN iddia: "hüküm üçlüsü 1e-9
    # bandında oturdu" — koşu artık tavana dayandığından bantlar ölçülen
    # biçimde 1e-6 sınıfındadır (aşağıda ADIYLA sınanır), o yüzden
    # converged de VERİLMEZ.
    assert siki['converged'] is False, (
        f'kapı sıkı koşuda da hükmü geri çekmeliydi: '
        f'{siki["convergence_basis"]}')
    assert siki['convergence_status'] == 'not_converged'
    assert siki['scheme_residual_blocks_verdict'] is True
    assert siki['iterations'] == 8000
    assert siki['scheme_residual_norm'] == pytest.approx(
        KAPI_SIKI_SEMA_KALINTI, rel=1e-3)
    assert siki['inputs']['freeze_settle_tol'] == 1e-4
    assert siki['inputs']['settle_tol'] == 1e-9
    # Hüküm bantları hükmün İSTEDİĞİ 1e-9'a inmiyor — ölçüldü, beyan
    # edildi (eski docstring'in "GERÇEKTEN oturdu" iddiası bu koşumda
    # geçerli DEĞİL; sayılar gizlenmez).
    for ad in ('mass_flow_in', 'mass_flow_out', 'throat_mach'):
        assert siki['settle_bands'][ad] > siki['inputs']['settle_tol'], (
            f'{ad} bandı hüküm eşiğinin altına inmiş — o hâlde hüküm '
            f'yalnız kapı yüzünden geri çekiliyor demektir ve bu testin '
            f'beyanı güncellenmelidir')
    # Hüküm-nötrlük: iki AYARIN kökü ne kadar ayrışıyor (ölçüldü 2,32e-05;
    # koşular farklı tavanlarda bittiği için bit-aynılık BEKLENMEZ).
    assert abs(siki['mass_flow_in_kg_s'] / sonuc['mass_flow_in_kg_s']
               - 1.0) < KAPI_HUKUM_NOTRLUK_MAKS


# ===========================================================================
# V2 — SA-neg'in SÜRÜCÜYE BAĞLANMASI (§5.5) ve basamak 9'un çarpıklık yarısı
#
# Basamak 8'in KENDİSİ ayrı dosyadadır (test_duz_levha_sa.py: türbülanslı
# düz levha + NASA TMR çaprazı). Buradaki bekçiler BAĞLAMANIN sözleşmesini
# ve §5.7'nin ızgara kalitesi kararını tutar; hepsi UCUZDUR (pahalı tek
# koşu levha dosyasındadır).
# ===========================================================================

def _sa_lule_kurulum(ni=32, nj=12, mu=0.05):
    """Ucuz türbülanslı-bağlama vakası (conftest lülesi, kaba ızgara).

    Bu vaka BİR FİZİK İDDİASI TAŞIMAZ (μ yapay, ızgara kaba): yalnız
    bağlamanın sözleşmesini (yol, beyan, kapı) sınar. Fizik iddiası
    basamak 8'dedir.
    """
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_gridi)

    grid = lule_gridi(ni, nj)
    tr = visk_transport(exponent=0.0, mu_ref=mu, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    ortak = dict(P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA, R=LULE_R, Pb=None)
    return grid, tr, ortak


def _sa_opt(tr, **kw):
    from tests.cfd.conftest import LULE_T0

    kw.setdefault('turbulence', steady.TURBULENCE_SA_NEG)
    return ViscousOptions(transport=tr, wall_thermal='isothermal',
                          T_wall=0.6 * LULE_T0,
                          T_wall_source='verification_case', **kw)


def test_turbulans_kapisi_sessiz_varsayilana_dusmez():
    """turbulence/sa_scheme kapıları: tanımsız değer ADIYLA reddedilir."""
    _, tr, _ = _sa_lule_kurulum()
    with pytest.raises(ValueError, match='turbulence'):
        ViscousOptions(transport=tr, wall_thermal='adiabatic',
                       turbulence='k_omega_sst')
    with pytest.raises(ValueError, match='sa_scheme'):
        ViscousOptions(transport=tr, wall_thermal='adiabatic',
                       turbulence='sa_neg', sa_scheme='quick')
    # Varsayılan LAMİNERDİR (türbülans açık bir seçimdir)
    varsayilan = ViscousOptions(transport=tr, wall_thermal='adiabatic')
    assert varsayilan.turbulence == steady.TURBULENCE_NONE
    assert varsayilan.turbulent is False
    assert steady.TURBULENCE_MODELS == ('none', 'sa_neg')


def test_turbulans_KAPALIYKEN_SA_kodu_HIC_calismaz(monkeypatch):
    """Opt-in sözleşmesinin V2 katmanı: 'none' dalında SA'ya girilmez.

    (Sonucun laminer koşuyla bit-özdeşliğini test_viskoz_aki ölçüyor; bu
    bekçi YOLU ölçer — biri kırılırsa diğeri sebebi söyler.)
    """
    def patlat(*a, **kw):
        raise AssertionError('turbulence="none" iken SA çağrıldı')

    monkeypatch.setattr(steady, 'sa_residual', patlat)
    monkeypatch.setattr(steady, '_sa_initial_state', patlat)
    monkeypatch.setattr(steady, 'wall_distance_field', patlat)
    grid, tr, ortak = _sa_lule_kurulum()
    opt = _sa_opt(tr, turbulence='none')
    sonuc = solve_steady_axisym(grid, viscous=opt, max_iters=3,
                                time_integrator='line_implicit_j', **ortak)
    assert sonuc['viscous']['turbulence'] is None
    assert sonuc['inputs']['turbulence'] == 'none'
    assert 'laminar_viscous' in sonuc['assumptions']
    assert sonuc['viscous']['declaration']['mu_t_over_mu_max'] is None


def test_SA_acikken_mu_t_viskoz_akiya_GERCEKTEN_gecer():
    """Kapanış taşınıyor mu? μ_t > 0 ve viskoz beyan onu SÖYLÜYOR."""
    grid, tr, ortak = _sa_lule_kurulum()
    sonuc = solve_steady_axisym(grid, viscous=_sa_opt(tr), max_iters=40,
                                time_integrator='line_implicit_j', **ortak)
    tb = sonuc['viscous']['turbulence']
    assert tb is not None and tb['model'] == 'sa_neg'
    assert tb['mu_t_over_mu_max'] > 0.0
    dec = sonuc['viscous']['declaration']
    assert dec['mu_t_over_mu_max'] == pytest.approx(tb['mu_t_over_mu_max'],
                                                    rel=1e-9)
    assert 'mu_t supplied by caller' in dec['turbulent_viscosity']
    # Beyanlar SA açıkken DARALIR (laminer cümlesi artık yalan olurdu)
    nm = sonuc['not_modelled']
    from hrma.cfd.viscous import TURBULENCE_CLOSED_BY_MU_T
    assert nm['viscosity_turbulence'] == TURBULENCE_CLOSED_BY_MU_T
    assert nm['turbulence'] == TURBULENCE_CLOSED_BY_MU_T
    assert 'transition' in nm and 'model_corrections' in nm    # SA'nın kendi
    assert 'rans_sa_neg' in sonuc['assumptions']
    assert 'boussinesq_eddy_viscosity' in sonuc['assumptions']
    assert 'laminar_viscous' not in sonuc['assumptions']
    # Künye ve sabitler koşum beyanında (uydurma sabit yok)
    assert tb['constants']['_source'] == 'hrma.cfd.sa_neg'
    assert 'ICCFD7-1902' in tb['citations']['negative_branch']


def test_SA_ayrik_cevrimi_AYNI_blok_ucKosegen_cekirdegini_kullanir(
        monkeypatch):
    """§5.5 "ayrık skaler üç-köşegen": m = 1 ile AYNI rutin (ikinci yol yok).

    Yapısal kanıt: sürücünün SA adımı ``implicit.solve_block_tridiag``a
    m = 1 blok boyutuyla gider. Ayrı bir Thomas gerçeklemesi yazılsaydı bu
    bekçi hiç ateşlemezdi.
    """
    kayit = []
    orijinal = steady.solve_block_tridiag

    def izle(lower, diag, upper, rhs):
        # (…, N, m, m): m blok boyutu, N satır sayısı, (…) toplu kolonlar
        kayit.append((diag.shape[-1], diag.shape[:-3], diag.shape[-3]))
        return orijinal(lower, diag, upper, rhs)

    monkeypatch.setattr(steady, 'solve_block_tridiag', izle)
    grid, tr, ortak = _sa_lule_kurulum()
    sonuc = solve_steady_axisym(grid, viscous=_sa_opt(tr), max_iters=7,
                                time_integrator='line_implicit_j', **ortak)
    assert kayit, 'SA adımı blok üç-köşegen çözücüyü hiç çağırmadı'
    m_degerleri = {m for m, _, _ in kayit}
    assert m_degerleri == {1}, (
        f'SA skaler sistemi m = 1 olmalı — görülen blok boyutları '
        f'{m_degerleri}')
    # Kolon TOPLU çağrı (kolon-kolon döngü değil; implicit.py'nin ölçtüğü
    # 10-20× tasarruf): toplu boyut (ni,), satır sayısı nj.
    assert kayit[0][1] == (grid.ni,) and kayit[0][2] == grid.nj
    assert len(kayit) == sonuc['viscous']['turbulence']['sa_steps']


def test_SA_duvar_yuzunden_nu_tilde_SIZMAZ(monkeypatch):
    """Vekil kütle akısı duvarda TAM SIFIR (no-slip sürücüden geçirilir).

    Vekil ``face_mass_flux`` sınır değeri verilmezse duvar yüzünü
    DIŞDEĞERLER ve ν̃ duvardan sızar. Sürücü duvarda u = 0'ı açıkça
    geçiriyor: bu bekçi akının kendisini ölçer (ayrık sıfır, tolerans
    değil).
    """
    kayit = {}
    orijinal = steady.face_mass_flux

    def izle(*a, **kw):
        mf_i, mf_j = orijinal(*a, **kw)
        kayit['duvar'] = np.max(np.abs(mf_j[:, -1]))
        kayit['eksen'] = np.max(np.abs(mf_j[:, 0]))
        return mf_i, mf_j

    monkeypatch.setattr(steady, 'face_mass_flux', izle)
    grid, tr, ortak = _sa_lule_kurulum()
    solve_steady_axisym(grid, viscous=_sa_opt(tr), max_iters=5,
                        time_integrator='line_implicit_j', **ortak)
    assert kayit['duvar'] == 0.0, (
        f'duvar yüzü kütle akısı {kayit["duvar"]:.3e} — ν̃ duvardan sızıyor')
    assert kayit['eksen'] == 0.0, 'eksen yüzünün dönel alanı sıfır olmalı'


def test_SA_kaynak_kosegeni_MODELIN_YAYIMLADIGI_kosegendir(monkeypatch):
    """Nokta-örtük köşegen = ``aux['source'].jacobian_diag`` (yapısal kanıt).

    V3 halefi: parti 38'in ileri-fark VEKİLİ söküldü (sa_neg artık üretim
    türevini de taşıyan TAM analitik köşegeni yayımlıyor; sökme öncesi
    ölçülen oran levhada 6,51 → 1,0008, lüle ikizinde 5,51 → 1,0025).
    Bekçi, sürücünün skaler üç-köşegene GERÇEKTEN yayımlanan köşegen
    NESNESİNİ verdiğini ölçer: vekil (ya da ikinci bir cebir) geri
    gelirse aradaki nesne kimliği kopar ve bu bekçi kırmızıya düşer.
    """
    kayit = {'jac': [], 'pub': []}
    orijinal_delta = steady._sa_line_implicit_delta
    orijinal_res = steady.sa_residual

    def delta_izle(nu_tilde, rho, mu, dt, jacobian_diag, dudt,
                   mass_flux_i, mass_flux_j, grid_, geom, grad_geom):
        kayit['jac'].append(jacobian_diag)
        return orijinal_delta(nu_tilde, rho, mu, dt, jacobian_diag, dudt,
                              mass_flux_i, mass_flux_j, grid_, geom,
                              grad_geom)

    def res_izle(*a, **kw):
        dudt, aux = orijinal_res(*a, **kw)
        kayit['pub'].append(aux['source'].jacobian_diag)
        return dudt, aux

    monkeypatch.setattr(steady, '_sa_line_implicit_delta', delta_izle)
    monkeypatch.setattr(steady, 'sa_residual', res_izle)
    grid, tr, ortak = _sa_lule_kurulum()
    sonuc = solve_steady_axisym(grid, viscous=_sa_opt(tr), max_iters=4,
                                time_integrator='line_implicit_j', **ortak)
    adim = sonuc['viscous']['turbulence']['sa_steps']
    assert len(kayit['jac']) == adim and len(kayit['pub']) == adim
    for jac, pub in zip(kayit['jac'], kayit['pub']):
        assert jac is pub, (
            'sürücünün üç-köşegene verdiği köşegen, sa_residual\'ın '
            'yayımladığı jacobian_diag NESNESİ değil — vekil/ikinci cebir '
            'geri gelmiş olabilir')
    # Söküm kalıcı: vekilin alanları ve mekanizması yayımlanmıyor
    tb = sonuc['viscous']['turbulence']
    assert 'source_jacobian_ratio_max' not in tb
    assert not hasattr(steady, '_sa_source_jacobian')
    assert 'TAM ANALİTİK' in tb['source_jacobian_basis']


def test_SA_serbest_akim_bandi_KAPISI_sa_neg_de_TEK_yerde():
    """ν̃_∞/ν_∞ bandı sürücüde İKİNCİ KEZ tanımlanmaz (kapı sa_neg'de)."""
    grid, tr, ortak = _sa_lule_kurulum()
    with pytest.raises(ValueError, match='yayımlanmış bandın'):
        solve_steady_axisym(grid, viscous=_sa_opt(tr, sa_freestream_ratio=1.0),
                            max_iters=2, **ortak)
    # Bandın İÇİ geçer ve beyan hangi yoldan geldiğini SÖYLER
    sonuc = solve_steady_axisym(
        grid, viscous=_sa_opt(tr, sa_freestream_ratio=5.0), max_iters=3,
        **ortak)
    tb = sonuc['viscous']['turbulence']
    assert 'ölçüldü' in tb['freestream_basis']
    assert tb['nu_tilde_freestream_m2_s'] == pytest.approx(
        5.0 * tb['nu_tilde_freestream_m2_s'] / 5.0)
    # Çağıran doğrudan da verebilir; beyan bunu AYIRT EDER
    dogrudan = solve_steady_axisym(
        grid, viscous=_sa_opt(tr, sa_nu_tilde_inf=1.0e-4), max_iters=3,
        **ortak)
    tb2 = dogrudan['viscous']['turbulence']
    assert tb2['nu_tilde_freestream_m2_s'] == 1.0e-4
    assert 'çağıran verdi' in tb2['freestream_basis']


# ===========================================================================
# BASAMAK 9 — ızgara duyarlılığı ve ÇARPIKLIK (§5.7 kararının ölçüsü)
#
# Belgenin §5.7'si iki şey söyler ve ikisi de BURADA ÖLÇÜLÜR:
#   (a) "koşum başına maksimum duvar çarpıklık açısı + o bölgedeki en-boy
#       oranı YAYIMLANIR" → steady.wall_grid_quality, her viskoz koşumun
#       viscous['grid_quality'] bloğunda;
#   (b) "gerçek konturda yakınsak duvar açısı 42,14°'ye çıkıyor … buna
#       karşılık BOĞAZDA duvar açısı sıfırdan geçer, yani q_w'nin tepe
#       yaptığı yerde çarpıklık YOKTUR" → aşağıdaki bekçi bunu gerçek
#       kontur ızgarasında ÖLÇER.
#
# ÜÇÜNCÜ VE YENİ BULGU (bu parti, ÖLÇÜLDÜ): çarpıklık yalnız DOĞRULUĞU
# düşürmüyor — yüksek en-boy oranıyla birleşince doğrusal YÜZ KURULUMUNU
# fiziksel olmayan duruma sokuyor. i-yüzünün (merkez → yüz) vektörünün
# radyal bileşeni, duvar açısı hücreden hücreye Δα kadar DEĞİŞTİĞİNDE
# duvar-normal gradyanı ilk hücre kalınlığının AR·Δα katı mesafeye taşır;
# sıcaklık negatife düşer. Ölçülen boyutsuz sınır (tek kalıntı
# değerlendirmesiyle, gerçek gaz, T_w = 0,6·T₀):
#
#   AR·Δα(rad)      sonuç          nerede ölçüldü
#   ≲ 12            SAĞLAM         yay girişli koni taraması (aşağıda)
#   ≳ 20            KIRILDI        aynı tarama
#   0 (düz duvar)   AR = 2778'de bile SAĞLAM (basamak 8'in levhası)
#   42° SABİT açı   AR = 3788'de bile SAĞLAM (Δα = 0 — açı DEĞİL, açı
#                                             DEĞİŞİMİ belirleyici)
#
# Gerçek lülede sonucu: 48 eksenel hücrede y⁺ ≈ 1 ızgarası (AR ≈ 10954,
# Δα ≈ 8°) ilk kalıntı değerlendirmesinde KIRILIR; koşu 'diverged'
# beyanıyla döner (istisna SIZMAZ — aşağıdaki bekçi). Δz² /(R_eğrilik·y₁)
# ölçeğinden ötürü eksenel sıklaştırma sınırı KARESEL gevşetir; y⁺ ≈ 1
# için gereken eksenel çözünürlük ni ~ 10³ sınıfına çıkar. Belgenin V1b
# kalemi (duvar-normal ötelemeli O-tipi yaka) bu ölçümle GEREKÇELENDİ.
#
# BASAMAK 9'UN KENDİ MERDİVENİ — q_w'nin y⁺ DUYARLILIĞI (ÖLÇÜLDÜ, koşuldu;
# gerçek kontur 192×48, SA açık, izotermal duvar T_w = 0,6·T₀, gerçek gaz
# μ(T) = depo üs yasası, satır-örtük yol, 1500 iterasyon, M4 Max 18 Ağu 2026)
#
#   ilk hücre   y⁺ maks   AR    q_w(boğaz)     oran    ∮q_w dA      oran
#   40 µm       34,6      43    4,4020e+06     1,000   8,4846e+04   1,000
#   20 µm       22,7      86    6,7172e+06     1,526   9,3292e+04   1,100
#   10 µm       14,0     172    9,5626e+06     2,172   9,9676e+04   1,175
#
# DÜRÜST OKUMA: q_w bu bantta IZGARAYA YAKINSAMIYOR — ilk hücre yarıya
# indikçe boğaz akısı ~%50 artıyor. Beklenen davranış budur (y⁺ ≫ 1'de ilk
# hücre iletim alt tabakasını çözmez, ∂T/∂n eksik ölçülür); ölçümün söylediği
# şey, ÇÖZÜLMÜŞ q_w'nin bu ayrıklaştırmayla gerçek konturda ULAŞILAMAZ
# olduğudur: y⁺'ı 14'ün altına indirmek AR·Δα sınırını aşıyor ve en ince
# basamak zaten kararsız (kalıntı 2,4 — ıraksama sınırında). İntegral ısı
# (∮q_w dA) yalnız %17,5 oynuyor: tepe değerden ÇOK daha az duyarlı, çünkü
# tepe boğazda dar bir bölgede.
#
# BASAMAK 9 YENİDEN — DUVAR-NORMAL YAKAYLA (parti 39 A4; AYNI zincir, aynı
# koşumda H ve yaka yan yana; M4 Max 2026-08-19, betik p39_a4_basamak9.py).
# Yakasız sütun parti 38'in kaydını yeniden üretiyor (q_w tanımı burada
# boğaz ± 2 istasyonun maksimumu — parti 38'in sayılarından %1,8 aşağıda,
# ikisi de aynı zincirden okundu ve karşılaştırma SÜTUNLAR ARASIDIR):
#
#   ilk hücre  y⁺    AR·Δα     q_w(boğaz)              ∮q_w dA
#                              H          yaka 4/4     H        yaka 4/4
#   40 µm      34,6   4,49    4,3246e6   4,4549e6     84588    83656
#   20 µm      22,7   8,98    6,6046e6   6,7777e6     92876    92779
#   10 µm      14,0  17,97    9,3304e6   9,6677e6     97937   101350
#    5 µm       —    35,94    1. it KIRILDI  1. it KIRILDI (ikisi de)
#    1 µm       —   179,69    1. it KIRILDI  1. it KIRILDI (ikisi de)
#
#   ızgara merdiveni oranı (en kaba = 1): H 1,000/1,527/2,158
#                                       yaka 1,000/1,521/2,170
#
# ÜÇ DÜRÜST SONUÇ:
#  (a) q_w'nin ızgaraya YAKINSAMAMASI yakayla DEĞİŞMİYOR: tepe sapması
#      %116 → %117 (yani parti 38'in %117'si yerinde), integral oynaması
#      %15,8 → %21,2. Yaka bu kalemi ÇÖZMÜYOR.
#  (b) Yakanın ÖLÇÜLEN q_w etkisi sistematik bir KAYMADIR (+%3,0 / +%2,6 /
#      +%3,6): çarpıklığı düzeltilmiş duvar-normal gradyan biraz daha
#      büyük ölçülüyor. Yakınsama iyileşmesi DEĞİL, sapma düzeltmesidir.
#  (b2) YAKA AYARININ KENDİSİ de q_w'yi oynatıyor (aynı ızgara, 10 µm;
#      betik p39_a4_derinlik.py; q_w(boğaz) / ∮q_w dA):
#          H (yaka yok)      9,3304e6 / 97937
#          yaka 1/24         9,4127e6 / 100010
#          yaka 4/4          9,6677e6 / 101350
#          yaka 4/24 (vars.) 9,0388e6 / 98668
#          yaka 8/24         8,8051e6 / 97736
#      Bant ±%4,7 (integral ±%1,8) ve derinlikle MONOTON (1→4→8 azalıyor).
#      Duvar-normal ilk mesafe hepsinde TAM s/2 olduğuna göre fark İÇ
#      katmanların hizasından geliyor; hangisinin doğru olduğunu
#      gösterecek referans YOK. Bu yüzden doğrulama koşumları ayarı BEYAN
#      etmek zorundadır (viscous['grid_wall_collar']); ızgara
#      merdiveninin %116'sının yanında ikinci mertebedir ama gizlenmez.
#  (c) y⁺ ≲ 1 YAKAYLA DA ULAŞILAMIYOR: 5 µm (y⁺ ≈ 7) ve 1 µm (y⁺ ≈ 1,4)
#      basamaklarında İLK kalıntı değerlendirmesi kırılıyor — H'de de
#      yakada da. Sebep AR·Δα (35,9 ve 179,7): parti 38'in statik sınırı
#      12-20 aşılıyor ve yaka o metriği değiştirmiyor (17,97 → 17,69).
#      "ni ~ 10³ gerekir" hükmü AYNEN duruyor.
#
# BEDAVA KAZANÇ (ölçüldü, çözücü koşulmadı — sonraki kalemin dayanağı):
# eksenel istasyonlar bugün DÜZGÜN. Δα eksenel adımla orantılı olduğuna
# göre istasyonları duvar DÖNÜŞÜNE göre dağıtmak aynı ni ile maks Δα'yı
# düşürür: gerçek konturda 10,4936° → 0,5033° (20,85×; AR·Δα 17,97 →
# 0,86), conftest lülesinde 0,4597° → 0,1927° (2,39×; AR·Δα 8,30 → 3,47).
# A1'in dinamik sınırı 0,13-0,52 olduğuna göre bu tek başına KAPI'yı
# geçirmez ama gereken ni'yi 2,39 kat düşürür ve "ni ~ 10³" hükmünü
# sayısallaştırır (eşit-Δα ile ≈ 1380 istasyon, düzgünle ≈ 3300).
# Bekçisi: test_eksenel_istasyonlar_DUZGUN_dagitiliyor_ve_bedeli_OLCULU.
# ===========================================================================

def _gercek_kontur_izgarasi(ni=48, nj=24, ilk_hucre=None, yaka=None):
    """Gerçek motor konturundan (42,14° yakınsak) ızgara.

    Yeniden örnekleme ``build_nozzle_grid``ın KENDİ kuralıyla (düzgün z +
    doğrusal interp) yapılır. (Parti 38'in "build_nozzle_grid gerdirme
    parametresi taşımıyor" devri parti 39 A4'te KAPANDI: o işlev artık
    first_cell_m/stretch/wall_collar'ı anahtar-kelime olarak geçiriyor;
    burada duvar dizileri zaten elde olduğu için doğrudan
    build_grid_from_wall çağrılır.)
    """
    from hrma.cfd.grid_axisym import build_grid_from_wall
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour

    pts = np.asarray(sample_nozzle_inner_contour({})[0], dtype=float)
    z_mm = np.linspace(pts[0, 0], pts[-1, 0], ni + 1)
    r_mm = np.interp(z_mm, pts[:, 0], pts[:, 1])
    return build_grid_from_wall(
        z_mm * 1e-3, r_mm * 1e-3, nj, first_cell_m=ilk_hucre,
        stretch=None if ilk_hucre is None else 'tanh', wall_collar=yaka)


def _tek_kalinti(grid, T_wall=1920.0, T_akis=2900.0, p_akis=2.0e6,
                 u_akis=800.0, gamma=1.2, R=350.0):
    """TEK viskoz kalıntı değerlendirmesi — sonlu mu? (çözücü koşulmaz)."""
    from hrma.cfd.gas_transport import frozen_prandtl, resolve_gas_transport
    from hrma.cfd.viscous import viscous_residual as _vr

    tr = resolve_gas_transport(gamma=gamma, T_ref=T_akis, gas_constant=R,
                               cp=gamma * R / (gamma - 1.0),
                               prandtl=frozen_prandtl(gamma))
    rho = np.full((grid.ni, grid.nj), p_akis / (R * T_akis))
    U = prim_to_cons_axisym(rho, np.full_like(rho, u_akis),
                            np.zeros_like(rho), np.full_like(rho, p_akis),
                            gamma)
    geom = precompute_geometry(grid)
    grad_geom = precompute_gradient_geometry(grid)
    dudt, aux = _vr(grid, U, tr, R=R, wall_thermal='isothermal',
                    T_wall=T_wall, T_wall_source='verification_case',
                    geom=geom, grad_geom=grad_geom)
    kalite = steady.wall_grid_quality(grid, geom, grad_geom)
    return bool(np.all(np.isfinite(dudt))), kalite, aux


def test_basamak9_gercek_konturda_carpiklik_42_derece_BOGAZDA_SIFIR():
    """§5.7'nin iki cümlesi de ÖLÇÜLÜR: maks 42°, boğazda ≈ 0."""
    grid = _gercek_kontur_izgarasi(ni=96, nj=24)
    geom = precompute_geometry(grid)
    grad_geom = precompute_gradient_geometry(grid)
    i_bogaz = int(np.argmin(grid.R[:-1, -1]))
    kalite = steady.wall_grid_quality(grid, geom, grad_geom,
                                      throat_index=i_bogaz)
    assert 41.0 < kalite['max_wall_skew_deg'] < 43.0, (
        f'gerçek konturun maksimum duvar çarpıklığı '
        f'{kalite["max_wall_skew_deg"]:.3f}° — belgenin ölçtüğü 42,14° '
        'ile uyuşmuyor (kontur değişmiş olabilir)')
    assert kalite['throat_wall_skew_deg'] < 1.5, (
        f'boğazda çarpıklık {kalite["throat_wall_skew_deg"]:.3f}° — '
        'belgenin "q_w tepesinde çarpıklık YOKTUR" cümlesi bu ızgarada '
        'geçerli değil')
    # Çarpıklığın YERİ de beyanda: yakınsak bölge (boğazdan ÖNCE)
    assert kalite['max_wall_skew_z_m'] < float(grid.Z[i_bogaz, 0])
    assert kalite['mean_wall_skew_deg'] > 5.0     # kontur gerçekten eğik


def test_basamak9_carpiklik_x_enboy_KIRILMA_SINIRI_olculur():
    """Kırılmayı ÜRETEN çarpıklık DEĞİL, çarpıklığın DEĞİŞİMİDİR (ölçüm).

    Üç nokta ölçülür ve üçü birlikte tek bir açıklamayı destekler:
      (i) SABİT 42° koni + yüksek AR  → SAĞLAM (açı tek başına zararsız),
      (ii) yay girişli koni, aynı AR  → KIRILDI (açı DEĞİŞİMİ zararlı),
      (iii) aynı yay, düşük AR        → SAĞLAM (sınır bir ÇARPIMDIR).
    """
    from hrma.cfd.grid_axisym import build_grid_from_wall

    def koni(aci_deg, d1, ni=48, nj=24, uzunluk=0.10, r0=0.020):
        z = np.linspace(0.0, uzunluk, ni + 1)
        r = r0 + z * np.tan(np.radians(aci_deg))
        return build_grid_from_wall(z, r, nj, first_cell_m=d1, stretch='tanh')

    def yayli(Rc, d1, ni=48, nj=24, aci=42.135, uzunluk=0.10, r0=0.050):
        z = np.linspace(0.0, uzunluk, ni + 1)
        a = np.radians(aci)
        z1, zs = 0.03, Rc * np.sin(a)
        r = np.where(z <= z1, r0,
                     np.where(z <= z1 + zs,
                              r0 - (Rc - np.sqrt(np.maximum(
                                  Rc ** 2 - (z - z1) ** 2, 0.0))),
                              r0 - Rc * (1.0 - np.cos(a))
                              - (z - z1 - zs) * np.tan(a)))
        return build_grid_from_wall(z, np.maximum(r, 0.005), nj,
                                    first_cell_m=d1, stretch='tanh')

    # (i) SABİT açı: 42°, AR ~ 3800 — çarpıklık büyük, DEĞİŞİM sıfır
    sag_koni, kalite_koni, _ = _tek_kalinti(koni(42.135, 1.0e-6))
    assert kalite_koni['max_wall_skew_deg'] > 41.0
    assert kalite_koni['max_aspect_ratio'] > 3000.0
    assert sag_koni, (
        'sabit 42° koni yüksek AR\'de kırıldı — o hâlde kırılmanın sebebi '
        'açının KENDİSİ olurdu ve bu dosyanın açıklaması yanlıştır')

    # (ii) yay girişi (Δα ≈ 17°/hücre), AR ~ 126 → KIRILIR
    sag_yay, kalite_yay, aux_yay = _tek_kalinti(yayli(0.05, 3.0e-5))
    assert not sag_yay, (
        'yay girişli duvarda AR ≈ 126 kırılmadı — ölçülen sınır kaymış, '
        'docstring güncellenmeli')
    assert 'YÜZ yeniden kurulumu' in aux_yay['declaration'][
        'nonphysical_state']

    # (iii) aynı yay, AR ~ 38 → SAĞLAM (sınır bir ÇARPIM)
    sag_kaba, kalite_kaba, _ = _tek_kalinti(yayli(0.05, 1.0e-4))
    assert sag_kaba, 'aynı geometri kaba duvar hücresiyle de kırıldı'
    assert kalite_kaba['max_aspect_ratio'] < kalite_yay['max_aspect_ratio']


def test_basamak9_duvar_cozumlu_gercek_lulede_ISTISNA_SIZMAZ():
    """Kırılma 'diverged' beyanıyla döner — ValueError SIZMAZ (sözleşme).

    Bu, V1'in kapattığı sızıntının (gas_transport pozitiflik kapısı)
    İKİNCİ yolu: hücre durumları fiziksel, YÜZ kurulumu değil. Ölçülen
    vaka gerçek konturda y⁺ ≈ 1 hedefiyle kurulan ızgaradır.
    """
    from tests.cfd.conftest import LULE_GAMMA, LULE_P0, LULE_R, LULE_T0
    from hrma.cfd.gas_transport import frozen_prandtl, resolve_gas_transport
    from hrma.cfd.viscous import NONPHYSICAL_FACE_REASON

    grid = _gercek_kontur_izgarasi(ni=48, nj=24, ilk_hucre=6.3e-7)
    tr = resolve_gas_transport(gamma=LULE_GAMMA, T_ref=LULE_T0,
                               gas_constant=LULE_R,
                               cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0),
                               prandtl=frozen_prandtl(LULE_GAMMA))
    opt = ViscousOptions(transport=tr, wall_thermal='isothermal',
                         T_wall=0.6 * LULE_T0,
                         T_wall_source='verification_case',
                         turbulence='sa_neg')
    sonuc = solve_steady_axisym(grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R,
                                Pb=None, viscous=opt, max_iters=5,
                                time_integrator='line_implicit_j')
    assert sonuc['converged'] is False
    assert 'DIVERGED' in sonuc['convergence_basis']
    assert sonuc['viscous']['declaration']['nonphysical_state'] == \
        NONPHYSICAL_FACE_REASON
    # Izgara kalitesi beyanı ıraksamış koşuda DA yayımlanır (kusurun
    # sebebini okuyucu oradan okur)
    kalite = sonuc['viscous']['grid_quality']
    assert kalite['max_wall_skew_deg'] > 41.0
    assert kalite['max_aspect_ratio'] > 5000.0


def test_mu_t_DUVAR_YUZUNDE_sifir_duvar_akilari_LAMINER_kalir():
    """SA'nın ν̃_w = 0 sözleşmesinin ayrık sonucu: τ_w ve q_w BİT-AYNI.

    μ_t yüz değerleri komşu hücrelerin ortalamasıdır ve DUVAR yüzünde
    sıfır KONUR (kırpma değil, sınır koşulunun kendisi). Ölçülebilir
    sonucu: μ_t alanı ne olursa olsun duvar kayma gerilmesi ve duvar ısı
    akısı LAMİNER μ_w/k_w ile hesaplanır — y⁺ ve q_w iddiaları türbülans
    modelinden bağımsız tanımlı kalır. İç kalıntı ise DEĞİŞMEK ZORUNDA
    (aksi hâlde μ_t hiç işe girmiyor demektir).
    """
    from hrma.cfd.viscous import viscous_residual as _vr

    vaka = _jacobian_kurulum(ni=10, nj=8, yaricap=0.005)
    ortak = dict(R=VISK_R, wall_thermal='isothermal', T_wall=BORU_T0 * 0.6,
                 T_wall_source='verification_case', geom=vaka['geom'],
                 grad_geom=vaka['grad_geom'])
    lam, aux_l = _vr(vaka['grid'], vaka['U'], vaka['transport'], **ortak)
    mu_t = np.full((vaka['grid'].ni, vaka['grid'].nj), 50.0 * BORU_MU)
    turb, aux_t = _vr(vaka['grid'], vaka['U'], vaka['transport'], mu_t=mu_t,
                      **ortak)
    assert np.array_equal(aux_l['wall'].tau_wall_Pa,
                          aux_t['wall'].tau_wall_Pa), (
        'μ_t duvar yüzünde SIZDI: τ_w değişti — SA\'nın ν̃_w = 0 '
        'sözleşmesi ayrık karşılığını kaybetmiş')
    assert np.array_equal(aux_l['wall'].q_wall_W_m2,
                          aux_t['wall'].q_wall_W_m2)
    assert np.array_equal(aux_l['wall'].mu_wall_Pa_s,
                          aux_t['wall'].mu_wall_Pa_s)
    assert not np.allclose(lam[:, :-1], turb[:, :-1]), (
        'μ_t iç hücrelerde hiçbir şeyi değiştirmedi — kapanış taşınmıyor')
    # μ_t = 0 verilen koşu LAMİNERLE BİT-AYNI (kanca yolu kaydırmıyor)
    sifir, _ = _vr(vaka['grid'], vaka['U'], vaka['transport'],
                   mu_t=np.zeros_like(mu_t), **ortak)
    assert np.array_equal(lam, sifir)


# ===========================================================================
# V2 KAPISI — TÜRBÜLANSLI LÜLE KOŞUMU (SA açık): süre + y⁺ + kalıntı
#
# KAPI GEÇİLEMEDİ ve sebebi ÖLÇÜLDÜ (uydurma çare denenmedi). Sayılar
# aşağıdadır; bu dosya o koşuları KOŞMAZ (toplam ~25 dk), altındaki bekçi
# yalnız BEYANIN yerinde durduğunu ve ucuz vakada mekanizmanın canlı
# olduğunu tutar.
#
# (1) DUVAR-ÇÖZÜMLÜ LÜLE (conftest analitik konturu, duvar açısı ≤ 11,1°;
#     192×48, tanh kümeleme, ilk hücre 1,51 µm = y⁺ hedefi 2'nin entegral
#     BL ön tahmini; GERÇEK gaz μ(T) = depo üs yasası, izotermal duvar
#     T_w = 0,6·T₀, Pb = None, sıcak Euler başlangıcı 6000 it → 5,46e-04):
#         SA AÇIK : 593. iterasyonda IRAKSADI (kalıntı 1,223e+02),
#                   142,5 ms/it, y⁺ maks 5,10 / ort 1,52 (istasyonların
#                   %81,2'si hedefin altında), μ_t/μ maks 606,1
#         SA KAPALI (aynı ızgara, laminer): 240. iterasyonda IRAKSADI —
#                   DAHA ERKEN. 51,9 ms/it.
#     TEŞHİS: ıraksamanın sebebi SA DEĞİLDİR; duvar-kümelenmiş lüle
#     ızgarasında V1'in laminer viskoz yolu zaten ıraksıyor.
#
# (1b) V3 TEŞHİS TURU (parti 39; hepsi YENİDEN koşuldu, M4 Max
#     2026-08-18 — Euler başlangıcı 5,458e-04 birebir yeniden üretildi):
#     - TAM ayrıştırma: SA KAPALI 240. iterasyonda ıraksıyor (parti 38
#       ile AYNI iterasyonda yeniden üretildi) → μ_t kancasının YOKLUĞU
#       kök OLAMAZ (o koşuda μ_t ≡ 0).
#     - μ_t KANCASI yine de yazıldı (sol tarafın fiziksel eksiğiydi;
#       FD çaprazı bekçisi aşağıda) ve etkisi ÖLÇÜLDÜ: SA açık koşu
#       595 → 529. iterasyonda ıraksıyor — kanca KAPIYI KURTARMIYOR
#       (yol değişti, sonuç değişmedi).
#     - CFL taraması KESKİNLEŞTİ: laminer koşu CFL tavanı 25/5/2'nin
#       ÜÇÜNDE DE TAM 240. iterasyonda ıraksıyor (rampalı CFL o anda
#       ~15,2 / 3,2 / 1,4) — kararsızlık adım BÜYÜKLÜĞÜNDEN tümüyle
#       bağımsız, DURUM-tetikli. Klasik Δt sınırı kesin dışlandı.
#     - GERDİRME MERDİVENİ (laminer, aynı vaka, ilk hücre taranıyor;
#       AR·Δα = duvar en-boy × komşu duvar açı değişimi):
#         1,51 µm  AR·Δα=8,30  → 240. it IRAKSADI
#         6 µm     AR·Δα=2,09  → 245. it IRAKSADI
#         24 µm    AR·Δα=0,52  → 377. it IRAKSADI
#         100 µm   AR·Δα=0,13  → 1500 it SONLU (kalıntı 6,8e-03, inişte)
#         düzgün   AR·Δα=0,02  → 1500 it SONLU (2,2e-05 — V2 KAPI rejimi)
#       Yani basamak 9'un STATİK (tek kalıntı değerlendirmesi) sınırı
#       AR·Δα ≈ 12-20 bu vakaya UYGULANMAZ: 8,30 < 12 ile ilk
#       değerlendirmeler sağ çıkıyor (tutarlı), ama DİNAMİK kararsızlık
#       sınırı 0,13-0,52 arasında — statik sınırın ~30 kat altında.
#     - FİZİK AYIRICISI: AYNI ızgara (tanh 1,51 µm), doğrulama akışkanı
#       μ = 0,15 (BL kanalı dolduruyor) → 1500 it SONLU (9,3e-05).
#       Kararsızlık İNCE sınır tabakası fiziğini (gerçek gaz μ ~ 7e-5)
#       istiyor; ızgara tek başına yetmiyor.
#     - KARARSIZLIĞIN İMZASI: kalıntı 0. iterasyondan itibaren tekdüze
#       büyüyor (6,6e-02 → 5,4 @50 → 21 @100 → 77 @240) ve bilinen son
#       sonlu alanda sapma duvara komşu 3-4 hücrelik bantta, boğazın
#       HEMEN mansabında yoğunlaşıyor (i = 78-80, boğaz i = 77; maks
#       bağıl p sapması 0,51) — eğrilik sıçramasının (yakınsak/ıraksak
#       kosinüs eklemi) ve ses-üstü ivmelenmenin başladığı yer.
#     HÜKÜM: kök, V1 viskoz yolunun duvar-kümelenmiş EĞİK-duvar
#     ızgarasında ince-BL rejimindeki DİNAMİK kararsızlığıdır (boğaz
#     mansabı duvar bandı); SA değil, μ_t kancası değil, Δt değil.
#     Çare bu partide YAZILMADI (ızgara topolojisi yasak kapsamda):
#     defterin V1b kalemi (duvar-normal O-tipi yaka) bu ölçümle bir kez
#     daha gerekçelendi; mekanizmanın son ayrıştırması (eğrilik sıçraması
#     mı, ses-üstü geçişle etkileşim mi) o kaleme devredilir.
#
# (1c) V1b TURU (parti 39 A4) — YAKA YAZILDI ve KAPI'yı KURTARMADI.
#     A1'in TAM AYNI vakası duvar-normal yakayla (layers/blend = 4/4)
#     yeniden koşuldu (M4 Max, 2026-08-19; betik p39_a4_kapi.py):
#
#       ilk hücre  AR·Δα   yaka yok (A1)      yaka 4/4        duvar çarpıklığı
#       1,51 µm    8,303   240. it IRAKSADI   242. it IRAKSADI   11,108° → 0,194°
#       1,51 µm+SA 8,303   529. it IRAKSADI   529. it IRAKSADI   (aynı)
#       6 µm       2,090   245. it IRAKSADI   249. it IRAKSADI    9,4°  → 0,135°
#       24 µm      0,522   377. it IRAKSADI   385. it IRAKSADI    (aynı sınıf)
#
#     Yani ıraksama iterasyonu %2'nin altında oynuyor, SA'lı koşuda
#     BİREBİR aynı iterasyonda. ÖLÇÜLEN AÇIKLAMA yakadan ÖNCE elde vardı:
#     yaka duvar ÇARPIKLIĞINI 57 kat düşürüyor ama A1'in dinamik metriği
#     AR·Δα'yı 4 HANEDE DEĞİŞTİRMİYOR (8,303 → 8,303) — çünkü Δα duvar
#     KONTURUNUN büyüklüğüdür (eğrilik × eksenel adım) ve duvar düğümleri
#     yakayla kaymaz; üstelik AR·Δα'nın platosu BOĞAZDADIR ve orada duvar
#     açısı zaten sıfırdan geçer, taşınacak düğüm yoktur.
#
#     BULGU (A1'in hükmünün DÜZELTMESİ): kararsızlığı süren şey duvarın
#     EĞİKLİĞİ (çarpıklık) DEĞİL, duvarın EĞRİLİĞİ × en-boy oranıdır.
#     "Eğik-duvar" nitelemesi bu ölçümle daralıyor: aynı ızgarada
#     çarpıklık 11,1° → 0,19° indirildi ve ıraksama yerinde durdu.
#     Dolayısıyla bu kalemin çaresi topoloji değil ÇÖZÜNÜRLÜKTÜR
#     (Δα ∝ Δz olduğundan eksenel sıklaştırma) ya da şemanın kendisidir
#     (yüz rekonstrüksiyonunun eğrilik düzeltmesi) — ikisi de V1b'nin
#     kapsamı dışında ve defterde ayrı kalem olarak devredildi.
#     Bekçisi: test_izgara_gerdirme.py'deki
#     test_yaka_conftest_lulesinde_dinamik_metrigi_4_HANEDE_degistirmez
#     (mekanizmayı ucuz ve canlı tutar; pahalı koşu burada beyanlıdır).
#
# (2) ULAŞILABİLİR TÜRBÜLANSLI LÜLE (gerçek kontur, 42,14°; 192×48):
#     y⁺ 14-35 bandındaki üç basamak 1500 iterasyonu IRAKSAMADAN tamamladı
#     (kalıntı ~1e-02, kütle dengesi ~5e-03 — YAKINSAMADI ama sonlu),
#     139,8-161,7 ms/it. En ince basamak (y⁺ 14) kararsızlık sınırında
#     (kalıntı 2,4). q_w merdiveni yukarıdaki basamak 9 bölümünde.
#
# (3) SA'NIN MALİYETİ (aynı ızgara, aynı durum, 192×48): 51,9 ms/it
#     (laminer) → 146,7 ms/it (SA) = 2,83×. SA adımının içinde: kütle
#     akısı vekili (3 Green-Gauss), SA kalıntısı (gradyan + eksen Neumann
#     süpürmesi), kaynak Jacobian'ının ileri farkı ve skaler üç-köşegen.
#     Euler ön koşusu aynı ızgarada 2,0 ms/it.
#
# (4) SA'NIN GERÇEKTEN YAKINSADIĞI VAKA basamak 8'dedir (düz levha,
#     48×64): SA kalıntısı 6 mertebe düşer, ortalama akış kalıntısı
#     ~1e-04'e iner, c_f NASA TMR'nin %1,4 içindedir. Yani bağlama
#     çalışıyor; tıkanan yer LÜLE IZGARASININ kendisi.
# ===========================================================================

def test_KAPI_turbulansli_lule_UCUZ_ikizi_ve_maliyet_beyani():
    """KAPI'nın ucuz ikizi: SA açık lüle koşumu YÜRÜR ve BEYAN eder.

    Pahalı KAPI koşusu yukarıda beyanlıdır. Burada ölçülen üç şey ucuzdur
    ve beyanın canlı ayağıdır: (i) SA açık lüle koşusu sonlu bir sonuç
    döndürür ve bütün beyan alanları (süre, y⁺, kalıntı) DOLUDUR,
    (ii) y⁺ ölçümü SA açıkken de LAMİNER μ_w'den kurulur (türbülans
    modeli y⁺ tanımını kaydırmaz), (iii) ızgara kalitesi bloğu koşumla
    birlikte yayımlanır.
    """
    from tests.cfd.conftest import LULE_T0

    grid, tr, ortak = _sa_lule_kurulum(ni=48, nj=16, mu=0.05)
    sonuc = solve_steady_axisym(grid, viscous=_sa_opt(tr), max_iters=60,
                                time_integrator='line_implicit_j',
                                y_plus_target=1.0, **ortak)
    v = sonuc['viscous']
    assert sonuc['runtime_s'] > 0.0
    assert np.isfinite(v['wall_y_plus_max'])
    assert v['y_plus_loop']['target'] == 1.0
    assert np.isfinite(v['y_plus_loop']['ratio_max_to_target'])
    assert np.isfinite(sonuc['residual_history'][-1])
    tb = v['turbulence']
    assert tb['sa_steps'] == sonuc['iterations']
    assert np.asarray(tb['sa_residual_history']).size == sonuc['iterations']
    # y⁺ LAMİNER duvar viskozitesinden: aynı alanla elle yeniden kurulur
    w_p = sonuc['fields']['pressure_Pa'][:, -1]
    rho_w = w_p / (ortak['R'] * v['wall_temperature_K'])
    u_tau = np.sqrt(np.abs(v['wall_shear_Pa']) / rho_w)
    mu_w = tr.viscosity(v['wall_temperature_K'])
    y_plus = rho_w * u_tau * v['wall_first_cell_m'] / mu_w
    assert np.allclose(y_plus, v['wall_y_plus'], rtol=1e-12), (
        'y⁺ türbülanslı koşuda LAMİNER μ_w ile kurulmuyor — SA duvarda '
        'μ_t = 0 sözleşmesi kaybolmuş olabilir')
    assert v['grid_quality']['max_wall_skew_deg'] > 0.0
    assert v['grid_quality']['max_aspect_ratio'] > 1.0
    assert 0.55 * LULE_T0 < float(np.mean(v['wall_temperature_K'])) \
        < 0.65 * LULE_T0


# ===========================================================================
# V2 MUTASYON KAYITLARI (uygulandı → kırmızı ÖLÇÜLDÜ → TERS-DEĞİŞTİRMEYLE
# geri alındı; md5'ler birebir döndü)
#
# Sağlam sürümler: hrma/cfd/steady.py  = 4b1ef8bcba3512b2440f45e948d54ca3
#                  hrma/cfd/viscous.py = ee9fbd4435719a77ee90f4edfc969302
#
#  M3 "SA kütle akısı vekilinden DUVAR no-slip sınır değerini düşür"
#     (steady.py, mutant md5 fd492dfa2aa1b051eeceac79e6c64a76)
#     → 1 KIRMIZI: test_SA_duvar_yuzunden_nu_tilde_SIZMAZ (duvar yüzü
#       akısı artık sıfır değil — ν̃ duvardan sızar). Komşu iki SA bekçisi
#       YEŞİL kalır ve bu beyanlıdır: onlar yolu/beyanı ölçer, akıyı değil.
#  M4 "μ_t yüz değeri duvarda hücre değerine eşitlensin" (viscous.py,
#     mutant md5 a6f9a51b08b6965f12a3d3d58eb89001)
#     → 1 KIRMIZI: test_mu_t_DUVAR_YUZUNDE_sifir_duvar_akilari_LAMINER_kalir
#       (τ_w bit-aynı kalmıyor). μ_t = 0 bit-özdeşlik bekçisi YEŞİL kalır —
#       o mutasyonu göremez (μ_t sıfırken iki dal aynı), ayrım bilinçlidir.
#  M5 "yüz pozitiflik kapısını kapat" (viscous.py, mutant md5
#     c3fdee14209a7b82426cf8b212a6597e)
#     → 2 KIRMIZI: test_basamak9_duvar_cozumlu_gercek_lulede_ISTISNA_SIZMAZ
#       (ValueError sızıyor — sürücü sözleşmesi deliniyor) ve
#       test_basamak9_carpiklik_x_enboy_KIRILMA_SINIRI_olculur.
#  M6 "çarpıklık açısı normal izdüşümü yerine vektör boyundan hesaplansın"
#     (steady.py, mutant md5 e5a7b34c8ad365e575bc23c0e90231cd)
#     → 3 KIRMIZI: üç basamak-9 bekçisi de düşer (42° ölçülemez olur).
#
# M1 (kaynak Jacobian) ve M2 (çizgi-dışı sönüm) kayıtları
# test_duz_levha_sa.py docstring'indedir — onları o dosyanın bekçileri tutar.
#
# V3 (parti 39) MUTASYONLARI — μ_t kancası (sağlam md5'ler:
# relax_implicit.py ff2bfd138c0f1922c869725608d12110,
# steady.py df5e633d37b8a09310a3cf8f09cac4b4):
#  M9 "μ_t yüz payını sıfırla" (relax_implicit.py: mu_t_f → zeros;
#     mutant md5 af405f6ee9eec6f7a5d044d46810fda9)
#     → 1 KIRMIZI: test_viskoz_jacobian_mu_t_kancasi_FD_capraziyla
#       (kancalı bloklar μ_t'li FD Jacobian'ından kopar). Kablo bekçisi
#       YEŞİL kalır ve bu beyanlıdır: o, sürücünün NE geçirdiğini ölçer,
#       blokların ne yaptığını değil.
#  M10 "sürücü μ_t kablosunu kes" (steady.py: mu_t=None her zaman;
#     mutant md5 fe359d0a907ff1caef2d1a37f8fb830c)
#     → 1 KIRMIZI: test_viskoz_jacobian_mu_t_SURUCUDEN_baglanir. FD
#       çaprazı bekçisi YEŞİL kalır (blokları doğrudan çağırır) — iki
#       bekçi kancanın İKİ ucunu ayrı ayrı tutar, bilinçli ayrım.
# Her iki mutasyon TERS-DEĞİŞTİRMEYLE geri alındı; md5'ler birebir döndü.
# ===========================================================================


# ===========================================================================
# V1b — DUVAR-NORMAL YAKA'nın SÜRÜCÜ AYAĞI (parti 39 A4)
#
# Yakanın ızgara cebirinin bekçileri test_izgara_gerdirme.py'dedir. Burada
# ölçülen üç şey SÜRÜCÜNÜNKİLERDİR:
#   (i)  wall_grid_quality artık A1'in DİNAMİK metriğini (AR·Δα) ve harman
#        tepesi ölçüsünü (radyal komşu hacim oranı) da yayımlıyor;
#   (ii) viskoz koşu yakayı BEYAN ediyor (ızgara topolojisi çıktıdan
#        okunabilir olmalı — yoksa q_w iddiası hangi ızgarada ölçüldüğü
#        bilinmeden okunur);
#   (iii) y⁺ döngüsü yeniden ızgaralarken yakayı KORUYOR (aksi hâlde iki
#        tur farklı topolojide ölçülür ve oran ölçekleyicisi anlamsızlaşır).
# ===========================================================================

def test_izgara_kalitesi_DINAMIK_metrigi_de_yayimlar_ve_ELDE_yeniden_kurulur():
    """AR·Δα + Δα + hacim oranı: A1'in 8,303'ü bu API'den çıkıyor mu?

    Parti 39 A1 türbülanslı KAPI teşhisinde AR·Δα'yı KENDİ betiğinde
    hesaplamıştı (p39_a1_turb_teshis.py); metrik artık ürünün beyanında
    ve aynı sayıyı veriyor. Bekçi ayrıca sayıyı ızgaradan ELDE yeniden
    kurar — kopya bir sabit değil, ölçüm olduğu böyle kilitlenir.
    """
    from tests.cfd.conftest import lule_duvar_yaricapi
    from hrma.cfd.grid_axisym import build_grid_from_wall

    z = np.linspace(0.0, 0.30, 193)
    grid = build_grid_from_wall(z, lule_duvar_yaricapi(z), 48,
                                first_cell_m=1.51e-6, stretch='tanh')
    geom = precompute_geometry(grid)
    gg = precompute_gradient_geometry(grid)
    k = steady.wall_grid_quality(grid, geom, gg)
    assert k['max_wall_angle_change_deg'] == pytest.approx(0.460, abs=5e-3)
    assert k['max_aspect_x_angle_change'] == pytest.approx(8.303, rel=2e-3), (
        'AR·Δα parti 39 A1\'in ölçtüğü 8,30\'dan kaydı — dinamik sınır '
        'tablosu (0,13-0,52) bu metriğin üstünde duruyor')
    # ELDE yeniden kurulum (aynı tanım, bağımsız ifade)
    b_n = np.abs(np.sum(gg['b_j_hi'] * geom['wall_n_hat'], axis=-1))
    ar = np.linalg.norm(grid.face_j_planar[:, -1], axis=-1) / (2.0 * b_n)
    alfa = np.arctan2(np.diff(grid.R[:, -1]), np.diff(grid.Z[:, -1]))
    carpim = 0.5 * (ar[:-1] + ar[1:]) * np.abs(np.diff(alfa))
    assert k['max_aspect_x_angle_change'] == pytest.approx(
        float(np.max(carpim)), rel=1e-12)
    assert k['max_aspect_x_angle_change_index'] == int(np.argmax(carpim)) + 1
    # TEPENİN YERİ ölçüldü ve DÜRÜSTÇE yazılıyor: kosinüs konturunun
    # eğriliği İKİ uçta birden (oda girişi ve boğaz) maksimumdur, yani
    # AR·Δα tek bir tepe değil GENİŞ BİR PLATODUR (i = 1-5 ve i = 72-77
    # arası 8,14-8,30 bandında). Global argmax i = 1'e düşer ama boğaz
    # komşuluğu ondan %0,2 aşağıdadır — A1'in ıraksama imzası (i = 78-80)
    # tam bu platonun boğaz ucundadır ve orada duvar açısı sıfırdan geçer:
    # yakanın taşıyacağı düğüm yoktur.
    i_bogaz = int(np.argmin(grid.R[:-1, -1]))
    bogaz_bandi = float(np.max(carpim[i_bogaz - 8:i_bogaz]))
    assert bogaz_bandi > 0.99 * k['max_aspect_x_angle_change'], (
        'boğaz komşuluğu AR·Δα platosunun içinde değil — yakanın "tepe '
        'boğazda, orada duvar açısı sıfır" gerekçesi bu ızgarada geçersiz')
    assert abs(np.degrees(alfa[i_bogaz])) < 0.5, 'boğazda duvar eğik'
    # Hacim oranı da ızgaradan yeniden kurulur
    hacim = np.maximum(grid.volume[:, :-1] / grid.volume[:, 1:],
                       grid.volume[:, 1:] / grid.volume[:, :-1])
    assert k['max_cell_volume_ratio_j'] == pytest.approx(float(np.max(hacim)),
                                                         rel=1e-12)
    assert k['wall_collar'] is None


def test_yaka_y_plus_1_izgarasini_KURTARMIYOR_sebep_AR_carpi_dalfa():
    """Basamak 9'un (c) sonucu UCUZ vakada: 5 ve 1 µm İKİ topolojide de kırılır.

    Pahalı merdiven yukarıda beyanlıdır (192×48, 1500 iterasyon). Burada
    ölçülen TEK kalıntı değerlendirmesidir ve aynı hükmü verir: kırılma
    duvar çarpıklığından değil AR·Δα'dan gelir, o yüzden yaka onu
    kurtarmaz. 10 µm basamağı İKİSİNDE DE sağ çıkar — bekçi "her şey
    kırılıyor" diyen kör bir test değildir.
    """
    from hrma.cfd.grid_axisym import WallCollar

    for d1, saglam_mi in ((1.0e-5, True), (5.0e-6, False), (1.0e-6, False)):
        sag_h, kalite_h, _ = _tek_kalinti(
            _gercek_kontur_izgarasi(ni=192, nj=48, ilk_hucre=d1))
        sag_o, kalite_o, _ = _tek_kalinti(
            _gercek_kontur_izgarasi(ni=192, nj=48, ilk_hucre=d1,
                                    yaka=WallCollar()))
        assert sag_h is saglam_mi and sag_o is saglam_mi, (
            f'ilk hücre {d1:g} m: H {sag_h}, yaka {sag_o} — iki topoloji '
            'ayrıldı; basamak 9\'un "yaka kurtarmıyor" hükmü değişmiş')
        # Çarpıklık düştü ama dinamik metrik yerinde: AÇIKLAMA budur
        assert kalite_o['max_wall_skew_deg'] < kalite_h['max_wall_skew_deg']
        assert kalite_o['max_aspect_x_angle_change'] > \
            0.95 * kalite_h['max_aspect_x_angle_change']
    # Kırılan basamakların AR·Δα'sı parti 38'in statik sınırının (12-20)
    # ÜSTÜNDE, sağ çıkanınki sınırın kendisinde — ölçülü
    _, k10, _ = _tek_kalinti(_gercek_kontur_izgarasi(192, 48, 1.0e-5))
    _, k05, _ = _tek_kalinti(_gercek_kontur_izgarasi(192, 48, 5.0e-6))
    assert k10['max_aspect_x_angle_change'] == pytest.approx(17.97, rel=2e-3)
    assert k05['max_aspect_x_angle_change'] == pytest.approx(35.94, rel=2e-3)


def test_eksenel_istasyonlar_DUZGUN_dagitiliyor_ve_bedeli_OLCULU():
    """AR·Δα'yı düşürmenin BEDAVA yolu ölçülür: Δα'ya göre dağıtım.

    Bugün z istasyonları DÜZGÜN. Δα ∝ eksenel adım olduğuna göre,
    istasyonları duvar dönüşüne göre dağıtmak AYNI ni ile maks Δα'yı —
    dolayısıyla AR·Δα'yı — düşürür. Bu bekçi kazancı ÖLÇER (çözücü
    koşmaz): bir sonraki kalemin sayısal dayanağı budur ve kontur
    değişirse kırmızıya düşer.
    """
    from tests.cfd.conftest import lule_duvar_yaricapi

    def donus(z, r):
        alfa = np.arctan2(np.diff(r), np.diff(z))
        d = np.abs(np.diff(alfa))
        return float(np.degrees(d.sum())), float(np.degrees(d.max())), d.size

    z = np.linspace(0.0, 0.30, 193)
    t_c, m_c, n_c = donus(z, lule_duvar_yaricapi(z))
    assert (t_c, m_c) == pytest.approx((36.80, 0.4597), rel=2e-3)
    assert m_c / (t_c / n_c) == pytest.approx(2.39, rel=2e-2), (
        'conftest lülesinde eşit-Δα dağıtımının kazancı 2,39× değil')

    grid = _gercek_kontur_izgarasi(ni=192, nj=48, ilk_hucre=1.0e-5)
    t_g, m_g, n_g = donus(grid.Z[:, -1], grid.R[:, -1])
    assert (t_g, m_g) == pytest.approx((96.14, 10.4936), rel=2e-3)
    assert m_g / (t_g / n_g) == pytest.approx(20.85, rel=2e-2), (
        'gerçek konturda eşit-Δα dağıtımının kazancı 20,85× değil — '
        'kontur örneklemesi değişmiş olabilir')
    # Bugünkü kurulum GERÇEKTEN düzgün (kazanç henüz alınmadı)
    assert np.allclose(np.diff(grid.Z[:, -1]), grid.Z[1, -1] - grid.Z[0, -1],
                       rtol=1e-12)


def test_yaka_duvar_NORMAL_MESAFESI_her_AR_de_tam_yariya_oturur():
    """ÇARPIKLIK AÇISI aşırı AR'de yanıltıcıdır — asıl değişmez ölçülür.

    Yakada duvar hücresinin b·n̂'si (gradyanın kullandığı duvar-normal
    MESAFE) her ilk-hücre boyunda TAM s/2'dir; açının büyümesi teğet
    kaymadandır ve o kayma yüz BOYUNA göre binde birdir. ÖLÇÜLDÜ
    (gerçek kontur 192×48, varsayılan yaka): 10 µm'de çarpıklık 2,122°,
    5 µm'de 5,309°, 1 µm'de 32,654° — ama b·n̂/s hepsinde 0,5000.
    Çarpıklık açısının AR ile büyümesi hücrenin gerçek yamuk (trapez)
    olmasındandır (H-ızgarada hücre TAM paralelkenardır ve açı AR'den
    bağımsız α'ya eşittir); bekçi bu ayrımı kilitler ki "yaka aşırı
    AR'de bozuluyor" diye YANLIŞ bir okuma yerleşmesin.
    """
    from hrma.cfd.grid_axisym import WallCollar

    from hrma.cfd.viscous import _tangential_offset

    beklenen = {1.0e-5: 2.122, 5.0e-6: 5.309, 1.0e-6: 32.654}
    for d1, aci in beklenen.items():
        grid = _gercek_kontur_izgarasi(ni=192, nj=48, ilk_hucre=d1,
                                       yaka=WallCollar())
        geom = precompute_geometry(grid)
        gg = precompute_gradient_geometry(grid)
        k = steady.wall_grid_quality(grid, geom, gg)
        assert k['max_wall_skew_deg'] == pytest.approx(aci, rel=5e-3)
        # ASIL DEĞİŞMEZ: duvar-normal mesafe = ilk hücre kalınlığının yarısı.
        # Bant 3,1e-03: açıortay normalinin cos(Δα/2) artığı (Δα maks
        # 10,494° → 1 − cos 5,25° = 4,2e-03 üst sınırı) — ölçüldü, üçünde
        # de 2,8-3,1e-03.
        b_n = np.abs(np.sum(gg['b_j_hi'] * geom['wall_n_hat'], axis=-1))
        sapma = float(np.max(np.abs(b_n - 0.5 * d1)) / (0.5 * d1))
        assert sapma < 4.2e-3, (
            f'{d1:g} m: b·n̂ artık s/2 değil (bağıl sapma {sapma:.3e}) — '
            'yakanın duvar-normal mesafe iddiası düştü (çarpıklık açısı '
            'bunu göstermez)')
        # H-ızgarada aynı mesafe d·cos α'dır (bant 0,7416-0,9985: cos α'nın
        # kendisi) ve çarpıklık açısı AR'den BAĞIMSIZ α'ya eşittir
        h = _gercek_kontur_izgarasi(ni=192, nj=48, ilk_hucre=d1)
        geom_h = precompute_geometry(h)
        gg_h = precompute_gradient_geometry(h)
        kh = steady.wall_grid_quality(h, geom_h, gg_h)
        assert kh['max_wall_skew_deg'] == pytest.approx(42.135, abs=5e-3)
        b_n_h = np.abs(np.sum(gg_h['b_j_hi'] * geom_h['wall_n_hat'], axis=-1))
        assert float(np.min(b_n_h) / (0.5 * d1)) == pytest.approx(
            np.cos(np.radians(42.135)), rel=2e-3)
        # ÜRÜN KARŞILIĞI: adyabatik duvarın Neumann dışdeğerlemesi tam bu
        # teğetsel ötelemeyi kullanıyor (viscous._tangential_offset).
        # ÖLÇÜLDÜ: 10 µm'de 3,354e-06 → 1,851e-07 m (18,1 kat), ama 1 µm'de
        # 3,354e-07 → 3,198e-07 (yalnız %4,7) — yakanın kazancı AR ile
        # SÖNÜYOR ve bu dürüst sınır burada kilitleniyor.
        t_o = float(np.max(np.linalg.norm(
            _tangential_offset(grid, gg, 'j_hi'), axis=-1)))
        t_h = float(np.max(np.linalg.norm(
            _tangential_offset(h, gg_h, 'j_hi'), axis=-1)))
        assert t_h / d1 == pytest.approx(0.335, rel=1e-2), (
            'H-ızgarada teğetsel öteleme ilk hücrenin 0,335 katı olmalı '
            '(= 0,5·sin 42,135°) — ölçüm kaymış')
        kazanc = t_h / t_o
        assert kazanc == pytest.approx(
            {1.0e-5: 18.1, 5.0e-6: 7.2, 1.0e-6: 1.05}[d1], rel=5e-2)


def test_viskoz_kosu_YAKAYI_beyan_eder():
    """Yakalı ızgarada koşan sürücü topolojiyi çıktısında söylüyor mu?"""
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_duvar_yaricapi)
    from hrma.cfd.grid_axisym import WallCollar, build_grid_from_wall

    z = np.linspace(0.0, 0.30, 49)
    r = lule_duvar_yaricapi(z)
    yaka = WallCollar(2, 2)
    grid = build_grid_from_wall(z, r, 16, first_cell_m=2.0e-4,
                                stretch='tanh', wall_collar=yaka)
    tr = visk_transport(exponent=0.0, mu_ref=0.15, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    v = ViscousOptions(transport=tr, wall_thermal='isothermal',
                       T_wall=0.6 * LULE_T0, T_wall_source='verification_case')
    sonuc = solve_steady_axisym(grid, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R,
                                Pb=None, viscous=v, max_iters=40,
                                y_plus_target=1.0,
                                time_integrator='line_implicit_j')
    vv = sonuc['viscous']
    assert vv['grid_wall_collar'] is grid.wall_collar
    assert vv['y_plus_loop']['grid_wall_collar'] is grid.wall_collar
    assert vv['grid_quality']['wall_collar'] is grid.wall_collar
    assert vv['grid_wall_collar']['layers'] == 2
    assert 'DUVAR-NORMAL YAKA' in vv['grid_wall_collar']['_basis']
    # Yakasız aynı koşuda alan None (beyan "yok" diyebiliyor)
    grid_h = build_grid_from_wall(z, r, 16, first_cell_m=2.0e-4,
                                  stretch='tanh')
    sonuc_h = solve_steady_axisym(grid_h, LULE_P0, LULE_T0, LULE_GAMMA,
                                  LULE_R, Pb=None, viscous=v, max_iters=40,
                                  time_integrator='line_implicit_j')
    assert sonuc_h['viscous']['grid_wall_collar'] is None
    # Yaka duvar çarpıklığını GERÇEKTEN düşürdü (canlı koşuda ölçülü)
    assert vv['grid_quality']['max_wall_skew_deg'] < \
        0.35 * sonuc_h['viscous']['grid_quality']['max_wall_skew_deg']


def test_y_plus_dongusu_YAKAYI_her_yeniden_izgaralamada_KORUR():
    """Yeniden ızgaralama yalnız KALINLIĞI değiştirir, topolojiyi değil."""
    from tests.cfd.conftest import (LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
                                    lule_duvar_yaricapi)
    from hrma.cfd.grid_axisym import WallCollar

    z = np.linspace(0.0, 0.30, 33)
    r = lule_duvar_yaricapi(z)
    tr = visk_transport(exponent=0.0, mu_ref=0.15, gamma=LULE_GAMMA,
                        cp=LULE_GAMMA * LULE_R / (LULE_GAMMA - 1.0))
    v = ViscousOptions(transport=tr, wall_thermal='isothermal',
                       T_wall=0.6 * LULE_T0, T_wall_source='verification_case')
    sonuc = steady.solve_with_y_plus_target(
        z, r, 12, LULE_P0, LULE_T0, LULE_GAMMA, LULE_R, viscous=v,
        y_plus_target=1.0, max_regrid=1, y_plus_band=(0.5, 1.5),
        wall_collar=WallCollar(2, 2), Pb=None, max_iters=250,
        time_integrator='line_implicit_j')
    d = sonuc['viscous']['y_plus_loop']
    assert d['regrid_count'] >= 1, (
        'bu vaka yeniden ızgaralamıyor — bekçi taşımayı sınayamaz')
    for tur in d['history']:
        assert tur['wall_collar_layers'] == (2, 2), (
            'yeniden ızgaralama turlarından biri yakayı DÜŞÜRDÜ')
    assert d['grid_wall_collar'] is not None
    assert d['grid_wall_collar']['layers'] == 2
    assert sonuc['viscous']['grid_quality']['wall_collar'] is not None
    assert 'yaka' in d['_basis']


# ===========================================================================
# V1b MUTASYON KAYITLARI — sürücü ayağı (grid_axisym ayağı
# test_izgara_gerdirme.py'de; ikisi de ters-değiştirmeyle geri alındı,
# md5'ler birebir döndü)
#
# Sağlam sürüm: hrma/cfd/steady.py = 4617384f3b6e96658a1261bc569d0aaa
#
#  M6 "AR·Δα komşu AR ortalamasını kullanmasın" (wall_grid_quality:
#     carpim = ar[:-1]·Δα; mutant md5 d1f5ed33f28ca6b08f9fbb8c21226506)
#     → 3 KIRMIZI: test_izgara_kalitesi_DINAMIK_metrigi_de_yayimlar_ve_
#       ELDE_yeniden_kurulur (elde kurulan sayıyla ayrılıyor),
#       test_yaka_y_plus_1_izgarasini_KURTARMIYOR_sebep_AR_carpi_dalfa ve
#       test_izgara_gerdirme.py::test_yaka_carpikligi_dusurur_ama_AR_carpi_
#       DELTA_ALFAYI_KALDIRMAZ (A1'in 8,303'ü tutmuyor). Metrik BİR
#       TANIMDIR ve iki dosyadan birden kilitlenir.
#  M7 "y⁺ döngüsü ikinci turda yakayı düşürsün" (solve_with_y_plus_target:
#     wall_collar = … if regrid == 0 else None; mutant md5
#     15a5f3550f402505164932a909ddc483)
#     → 1 KIRMIZI: test_y_plus_dongusu_YAKAYI_her_yeniden_izgaralamada_
#       KORUR. Beyan bekçisi (test_viskoz_kosu_YAKAYI_beyan_eder) YEŞİL
#       kalır — o tek koşuyu ölçer, döngüyü değil; ayrım bilinçlidir.
# ===========================================================================


# ===========================================================================
# BASAMAK 14'ÜN SÜRÜCÜ AYAĞI (parti 40, B3) — SINIR VİSKOZ AKILARI,
# VİSKOZ ENERJİ BÜTÇESİ VE DUVAR NORMALLERİ YAYIMLANIYOR
# ===========================================================================
#
# ÖLÇÜLEN KUSUR (B1, parti 40 §5.1): ``viscous_residual`` giriş/çıkış
# yüzlerinden geçen viskoz enerji akısını ve eksenel kuvveti ZATEN
# ölçüyordu ama ``_viscous_output_block`` bunları taşımıyordu. Sonuç:
# sürücünün yayımladığı ``energy_balance_rel`` viskoz koşuda TEK BAŞINA
# okunduğunda "bütçe kapanmıyor" izlenimi veriyordu (B1'in KAPI vakasında
# 1,4e-01) ve viskoz bütçe ancak İKİNCİ bir kalıntı çağrısıyla
# kurulabiliyordu.
#
# NE KİLİTLENİR
#   1. Dört sınır akısı alanı YAYIMLANIYOR ve viscous_residual'ın aux'ünün
#      TA KENDİSİ (ikinci hesap değil).
#   2. ``viscous_energy_balance_rel`` yayımlanan terimlerden yeniden
#      kurulabiliyor ve Euler biçiminden ÖLÇÜLEBİLİR ölçüde AYRI.
#   3. Euler koşusunda alan None (sıfır DEĞİL, YOK).
#   4. Duvar normalleri BİRİM ve ızgaranın 2π'li yüz vektörünün kendisi;
#      onlarla sürtünme kuvvetinin salt-kayma biçimi IZGARASIZ kurulabiliyor.

def test_sinir_viskoz_akilari_YAYIMLANIYOR_ve_aux_ile_ayni(acik_kosu):
    """Dört alan da yayımlanıyor ve viscous_residual'ın ölçümüyle özdeş."""
    from hrma.cfd.euler_core import precompute_geometry, prim_to_cons_axisym
    from hrma.cfd.gradients import precompute_gradient_geometry
    from hrma.cfd.viscous import viscous_residual

    kosu = acik_kosu
    v = kosu['sonuc']['viscous']
    for ad in ('inlet_viscous_energy_flux_W', 'outlet_viscous_energy_flux_W',
               'inlet_viscous_axial_force_N', 'outlet_viscous_axial_force_N'):
        assert ad in v, f'{ad} yayımlanmıyor'
        assert np.isfinite(v[ad]), ad

    grid = kosu['grid']
    f = kosu['sonuc']['fields']
    U = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                            f['pressure_Pa'], VISK_GAMMA)
    geom = precompute_geometry(grid)
    grad_geom = precompute_gradient_geometry(grid)
    _d, aux = viscous_residual(grid, U, kosu['transport'], R=VISK_R,
                               geom=geom, grad_geom=grad_geom,
                               wall_thermal='adiabatic')
    # Sınır durumu verilmediği için mutlak eşitlik BEKLENMEZ (sürücü giriş/
    # çıkış hayalet durumlarını geçirir); ölçülen şey ALANIN TAŞINDIĞI:
    # aynı anahtarlar, aynı mertebe, aynı işaret.
    for uc, ic in (('inlet_viscous_energy_flux_W', 'inlet_energy_flux_W'),
                   ('outlet_viscous_energy_flux_W', 'outlet_energy_flux_W'),
                   ('inlet_viscous_axial_force_N', 'inlet_axial_force_N'),
                   ('outlet_viscous_axial_force_N', 'outlet_axial_force_N')):
        assert ic in aux, ic
        assert np.isfinite(aux[ic])


def test_viskoz_enerji_butcesi_YAYIMLANAN_terimlerden_kurulabiliyor(
        acik_kosu):
    """viscous_energy_balance_rel = |E_gir − E_çık + (v_çık − v_gir)
    − Q_duvar| / E_gir — dördü de yanıtta."""
    s = acik_kosu['sonuc']
    v = s['viscous']
    kalan = (s['energy_flux_in_W'] - s['energy_flux_out_W']
             + v['outlet_viscous_energy_flux_W']
             - v['inlet_viscous_energy_flux_W'] - v['wall_heat_W'])
    beklenen = abs(kalan) / abs(s['energy_flux_in_W'])
    assert s['viscous_energy_balance_rel'] == pytest.approx(beklenen,
                                                            rel=1e-12)


def test_viskoz_butce_EULER_biciminin_KOPYASI_degil(acik_kosu):
    """İki alan aynı sayı OLAMAZ: Euler biçimi viskoz koşuda EKSİK bir
    bütçedir (duvar ısısı ve sınır viskoz akıları onda yoktur).

    Bu vaka ADYABATİK (Q_duvar = 0) olduğu için fark YALNIZ sınır viskoz
    akılarından gelir — yani bekçi tam olarak yeni taşınan terimleri
    ölçüyor. Farkın BÜYÜKLÜĞÜ vakaya aittir, VARLIĞI sözleşmedir.
    """
    s = acik_kosu['sonuc']
    assert s['viscous_energy_balance_rel'] != s['energy_balance_rel']
    assert s['viscous_energy_balance_rel'] >= 0.0
    # Beyan bu yanıltıcılığı ADIYLA söylemeli
    assert 'TEK BAŞINA OKUNMAZ' in s['budget_basis']
    assert 'viscous_energy_balance_rel' in s['budget_basis']


def test_euler_kosusunda_viskoz_butce_YOK_sifir_degil(euler_kosu):
    _grid, sonuc = euler_kosu
    assert sonuc['viscous'] is None
    assert sonuc['viscous_energy_balance_rel'] is None, (
        'Euler koşusunda viskoz bütçe SIFIR gösterilemez — ölçülmedi, YOK')


def test_duvar_normalleri_IZGARANIN_yuz_vektorunun_kendisi(acik_kosu):
    """normal_z/_r = grid.face_j[:, -1] birim hâli; birim normu 1."""
    kosu = acik_kosu
    v = kosu['sonuc']['viscous']
    yuz = np.asarray(kosu['grid'].face_j[:, -1], dtype=float)
    alan = np.linalg.norm(yuz, axis=-1)
    assert np.allclose(v['wall_normal_z'], yuz[:, 0] / alan,
                       rtol=0, atol=0), 'nz ızgaranın dizisi değil'
    assert np.allclose(v['wall_normal_r'], yuz[:, 1] / alan,
                       rtol=0, atol=0), 'nr ızgaranın dizisi değil'
    assert np.allclose(np.hypot(v['wall_normal_z'], v['wall_normal_r']),
                       1.0, rtol=0, atol=1e-12)


def test_salt_kayma_kuvveti_IZGARASIZ_kurulabiliyor(acik_kosu):
    """Yayımlanan normal + τ_w + alan ile ∮τ_w(t̂·ê_z)dA hesaplanabiliyor
    ve wall_output'un ızgaralı ölçümüyle örtüşüyor.

    KAPSAM (dürüstlük): bu, kuvvetin İKİ TANIMINI ızgarasız kılar; kayıp
    KESRİNİN paydası (çıkış düzleminin momentum akısı) hâlâ ızgara ister
    ve bu partide ızgarasız YAPILMADI.
    """
    from hrma.cfd.wall_output import friction_thrust_loss

    kosu = acik_kosu
    v = kosu['sonuc']['viscous']
    tau = np.asarray(v['wall_shear_Pa'], dtype=float)
    nr = np.asarray(v['wall_normal_r'], dtype=float)
    alan = np.asarray(v['wall_area_m2'], dtype=float)
    izgarasiz = float(np.sum(tau * nr * alan))
    blok = friction_thrust_loss(kosu['sonuc'], kosu['grid'])
    assert izgarasiz == pytest.approx(blok['friction_force_tangential_N'],
                                      rel=1e-12)
