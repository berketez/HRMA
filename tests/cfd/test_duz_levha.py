# tests/cfd — basamak 7: laminer düz levha (Blasius sınıfı) sınır tabakası
"""Gelişen laminer sınır tabakasının Blasius'a karşı ölçümü (merdiven 7).

VAKA — "büyük yarıçaplı boru" düz-levha yaklaşımı (tasarım belgesi §7)
---------------------------------------------------------------------
Basamak 4 borusu TAM GELİŞMİŞ akışı sınar; basamak 7 GELİŞEN tabakayı
sınar. Yeni geometri kodu gerekmez: yarıçapı sınır tabakasına göre büyük
(δ/R ≪ 1) düz bir boru, iç yüzeyinde düz levha gibi davranır. ENİNE
EĞRİLİK bir hata kaynağıdır ve VARSAYILMAZ — δ*/R ölçülüp beyan edilir
(aşağıda).

    R = 50 mm, L = 80 mm, u_e ≈ 148 m/s, T0 = 3000 K, μ = 5,7e-04 Pa·s
    (sabit özellikli doğrulama akışkanı, üs 0), adyabatik duvar,
    Re_x = 6,3e3 … 2,1e4 (laminer; geçiş ~5e5), M_e = 0,137.

Sürüş: giriş rezervuar (P0, T0) + çıkışta Pb; u_e bu ikisinin izantropik
farkından DOĞAR, dayatılmaz — ölçülen u_e Re_x'te kullanılır.

REFERANSLAR (kapalı form, Blasius benzerlik çözümü)
---------------------------------------------------
    c_f = 0,664/√Re_x        δ* = 1,7208·√(νx/u_e)        H = δ*/θ = 2,59
Künye: Schlichting & Gersten, *Boundary-Layer Theory*, 9. baskı, §6.5
(Blasius 1908 çözümünün standart katsayıları).

ÖLÇÜLEN MERDİVEN (M4 Max, 2026-08-18; ni = 40, pencere x ∈ [20, 70] mm)
-----------------------------------------------------------------------
| nj  | yol    | süre    | c_f/Blasius (ort) | δ*/Blasius (ort) | H     |
|-----|--------|---------|-------------------|------------------|-------|
| 48  | açık   | 145,4 s | 1,547             | —(*)             | —(*)  |
| 96  | örtük  | 130,9 s | 1,122             | 0,952            | 2,944 |
| 192 | örtük  | 268,6 s | 1,057             | 0,945            | 2,832 |
(*) 48 basamağı δ* ölçümü, duvar noktası integrale KATILMADAN alınmıştı ve
    3× küçük çıkıyordu; hata bulundu (hücre merkezli ızgarada ilk veri
    noktası y = Δr/2'dedir, y = 0'daki u = 0 ayrıca eklenmelidir) ve 96/192
    basamakları düzeltilmiş integralle ölçüldü. Eski sayı raporlanmaz.

c_f fazlalığı ızgarayla TEKDÜZE küçülüyor (1,547 → 1,122 → 1,057): kalan
%5,7 iki bilinen ve ÖLÇÜLEN paydan gelir —
  (1) ENİNE EĞRİLİK / yerdeğiştirme: δ*/R = 1,63e-02 (192 basamağı) →
      çekirdek 2δ*/R ≈ %3,3 hızlanır (iç akışta yerdeğiştirme kesiti
      daraltır). Bu ELVERİŞLİ basınç gradyanıdır ve c_f'yi ARTIRIR —
      ölçülen fazlalığın işareti bu payla aynı yöndedir.
  (2) Duvar çözünürlüğü: nj = 192'de sınır tabakasında ≈ 8,5 hücre var
      (Δr = R/nj = 260 µm, δ ≈ 2,2 mm). DÜZGÜN radyal dağılımla daha
      fazlası pahalıdır; duvar kümeleme V2'nin işidir (§5.7) ve bu tablo
      onun ölçülmüş gerekçesidir.

δ99 KULLANILMADI (ölçülen sebep): boruda çekirdek hızı yarıçap boyunca
yerdeğiştirme yüzünden ~%1 değişir; "u = 0,99·u_eksen" ölçütü bu yüzden
tabaka kenarını değil çekirdek değişimini bulur (ölçüldü: δ99/R = 0,24,
δ*/R = 0,016 ile tutarsız). Kalınlık ölçütü olarak δ* (tanımı integral,
çekirdek değişimine duyarsız) ve ondan türetilen δ ≈ δ*/0,344 kullanılır.

BU DOSYANIN KOŞTUĞU: 40×192 örtük (≈270 s, 9582 iterasyon, kalıntı
6,9e-11). 48 ve 96 basamakları yukarıdaki tabloda ÖLÇÜMDÜR ve burada
tekrarlanmaz (süit disiplini); hükümler en ince basamağa bağlanmıştır,
çünkü kaba basamak Blasius yasasının ÜSSÜNÜ bile geri getirmiyor
(n = −0,77 ↔ −0,506) — kaba ızgaraya bağlanmış bir bant, kusuru
koruyan bir bekçi olurdu.
"""

import numpy as np
import pytest

from hrma.cfd.euler_core import prim_to_cons_axisym
from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.steady import ViscousOptions, solve_steady_axisym

from .test_viskoz_aki import (
    VISK_CP, VISK_GAMMA, VISK_R, transport as visk_transport,
)
from hrma.utils.numeric_compat import trapezoid

# --- vaka (LEVHA_ öneki: conftest'in LULE_ / A1'in BORU_ kuralıyla aynı) ---
LEVHA_R = 0.050                 # boru yarıçapı [m] (levha = iç yüzey)
LEVHA_L = 0.080                 # levha uzunluğu [m]
LEVHA_P0 = 1.0e6                # rezervuar basıncı [Pa]
LEVHA_T0 = 3000.0               # rezervuar sıcaklığı [K]
LEVHA_MU = 5.7e-4               # doğrulama akışkanı viskozitesi [Pa·s]
LEVHA_U_HEDEF = 150.0           # arka basıncı KURAN hız [m/s] (cevap değil)

LEVHA_NI = 40
LEVHA_NJ = 192
LEVHA_TOL = 1.0e-8
LEVHA_MAX_ITERS = 30000

#: Ölçüm penceresi (a priori kural, sonuca göre seçilmedi): ön kenarın
#: (eliptik/başlangıç bölgesi) ve çıkış sınırının etkisi dışarıda.
LEVHA_PENCERE_M = (0.020, 0.070)

# --- Blasius benzerlik çözümünün katsayıları (Schlichting §6.5) ---
BLASIUS_CF = 0.664
BLASIUS_DELTA_STAR = 1.7208
BLASIUS_H = 2.59
#: δ*/δ99 = 1,7208/5,0 — δ99 boruda ölçülemediği için (docstring) eğrilik
#: parametresi δ/R bu orandan TÜRETİLİR ve türetildiği beyan edilir.
BLASIUS_DSTAR_OVER_DELTA = BLASIUS_DELTA_STAR / 5.0

#: ÖLÇÜLEN bantlar (40×192 koşusu, docstring tablosu; bantlar ölçümün
#: ~%5 çevresi). Daha dar bant ızgara/çözücü gürültüsüne takılır, daha
#: geniş bant basamağı anlamsızlaştırır.
CF_ORAN_BANDI = (1.02, 1.12)          # ölçülen ortalama 1,057
DSTAR_ORAN_BANDI = (0.90, 1.00)       # ölçülen ortalama 0,945
H_BANDI = (2.6, 3.1)                  # ölçülen ortalama 2,832
#: c_f ∝ Re_x^n — Blasius n = −0,5; ÖLÇÜLDÜ n = −0,506 (40×192).
#: Bu hüküm MUTLAK seviyeden bağımsızdır: tabaka Blasius gibi BÜYÜYOR mu?
#: Izgara duyarlılığı ölçüldü: 40×96'da n = −0,768 (kaba ızgara ön kenarda
#: c_f'yi şişirir), 40×192'de −0,506 — yasa çözünürlükle geri geliyor.
CF_USTU_BANDI = (-0.55, -0.46)


def levha_gridi(ni=LEVHA_NI, nj=LEVHA_NJ):
    z = np.linspace(0.0, LEVHA_L, ni + 1)
    return build_grid_from_wall(z, np.full(ni + 1, LEVHA_R), nj)


def levha_tasinimi():
    """Sabit özellikli doğrulama akışkanı (üs 0 → μ, k sıcaklıktan bağımsız)."""
    return visk_transport(exponent=0.0, mu_ref=LEVHA_MU)


def _arka_basinc(u):
    """İzantropik: u hızını veren statik basınç (vakanın SÜRÜŞ tanımı)."""
    return LEVHA_P0 * (1.0 - u ** 2 / (2.0 * VISK_CP * LEVHA_T0)) ** (
        VISK_GAMMA / (VISK_GAMMA - 1.0))


def _baslangic(grid, pb):
    """Düzgün hız + sabit basınç TAHMİNİ (Blasius profili tohumlanmaz)."""
    p = np.full_like(grid.z_centers, pb)
    T = LEVHA_T0 * (pb / LEVHA_P0) ** ((VISK_GAMMA - 1.0) / VISK_GAMMA)
    rho = p / (VISK_R * T)
    return prim_to_cons_axisym(rho, np.full_like(p, LEVHA_U_HEDEF),
                               np.zeros_like(p), p, VISK_GAMMA)


def kosum(ni=LEVHA_NI, nj=LEVHA_NJ, integrator='line_implicit_j',
          tol=LEVHA_TOL, max_iters=LEVHA_MAX_ITERS):
    """Vakayı ÜRÜN SÜRÜCÜSÜNDEN koşar (viskoz opt-in + satır-örtük)."""
    grid = levha_gridi(ni, nj)
    pb = _arka_basinc(LEVHA_U_HEDEF)
    opt = ViscousOptions(transport=levha_tasinimi(),
                         wall_thermal='adiabatic')
    sonuc = solve_steady_axisym(
        grid, LEVHA_P0, LEVHA_T0, VISK_GAMMA, VISK_R, Pb=pb, viscous=opt,
        initial_state=_baslangic(grid, pb), time_integrator=integrator,
        tol_res=tol, max_iters=max_iters, settle_tol=1e-10)
    return {'grid': grid, 'sonuc': sonuc}


def olcumler(kosu):
    """İstasyon başına c_f, δ*, θ ve Blasius karşılıkları.

    δ* ve θ integrallerinde DUVAR NOKTASI (y = 0, u = 0) açıkça eklenir:
    hücre merkezli ızgarada ilk veri noktası y = Δr/2'dedir ve duvar
    noktası atlanırsa δ* sistematik olarak küçük çıkar. Hatanın boyu
    ızgaraya bağlıdır ve ÖLÇÜLDÜ: 40×48'de ~3×, 40×96'da %37, 40×192'de
    (bu dosyanın koştuğu) yaklaşık %20-25 — hepsi kabul bandının dışında
    (bekçisi aşağıda).
    """
    grid = kosu['grid']
    f = kosu['sonuc']['fields']
    rho, uz, p = f['rho_kg_m3'], f['u_z_m_s'], f['pressure_Pa']
    z = grid.z_centers[:, 0]
    ue = uz[:, 0]                            # eksen = potansiyel çekirdek
    rho_e = rho[:, 0]
    Re_x = rho_e * ue * z / LEVHA_MU
    tau = kosu['sonuc']['viscous']['wall_shear_Pa']
    c_f = tau / (0.5 * rho_e * ue ** 2)

    # Duvardan eksene doğru sıralı profil + duvar noktası
    y = np.concatenate([[0.0], (LEVHA_R - grid.r_centers[0])[::-1]])
    uz_p = np.concatenate([np.zeros((len(z), 1)), uz[:, ::-1]], axis=1)
    rho_p = np.concatenate([rho[:, :1], rho[:, ::-1]], axis=1)
    akı = (rho_p * uz_p) / (rho_e * ue)[:, None]
    d_star = np.array([trapezoid(1.0 - akı[i], y) for i in range(len(z))])
    theta = np.array([trapezoid(akı[i] * (1.0 - uz_p[i] / ue[i]), y)
                      for i in range(len(z))])
    return {
        'z': z, 'Re_x': Re_x, 'ue': ue, 'rho_e': rho_e, 'c_f': c_f,
        'd_star': d_star, 'theta': theta, 'H': d_star / theta,
        'c_f_blasius': BLASIUS_CF / np.sqrt(Re_x),
        'd_star_blasius': BLASIUS_DELTA_STAR * np.sqrt(
            LEVHA_MU * z / (rho_e * ue)),
        'mach': ue / np.sqrt(VISK_GAMMA * p[:, 0] / rho_e),
        'pencere': (z >= LEVHA_PENCERE_M[0]) & (z <= LEVHA_PENCERE_M[1]),
    }


@pytest.fixture(scope='module')
def levha():
    kosu = kosum()
    return kosu, olcumler(kosu)


# ===========================================================================
# Vakanın rejimi ÖNCE doğrulanır (referansın geçerlilik şartları)
# ===========================================================================

def test_vaka_laminer_ve_dusuk_mach(levha):
    """Blasius'un şartları: laminer Re_x, düşük Mach, gelişmemiş çekirdek."""
    _, m = levha
    p = m['pencere']
    assert p.sum() >= 20, 'ölçüm penceresinde yeterli istasyon yok'
    assert 1e3 < m['Re_x'][p].min() and m['Re_x'][p].max() < 1e5, (
        f'Re_x {m["Re_x"][p].min():.0f}-{m["Re_x"][p].max():.0f} laminer '
        'bandın dışına çıktı (geçiş ~5e5)')
    assert m['mach'].max() < 0.2, (
        f'M = {m["mach"].max():.3f}: sıkıştırılabilirlik düzeltmesi '
        'gerekirdi, referans sıkıştırılamaz Blasius')
    # Çekirdek hızı sürüşten DOĞDU (dayatılmadı) ve hedefe yakın
    assert 0.9 * LEVHA_U_HEDEF < m['ue'].mean() < 1.05 * LEVHA_U_HEDEF


def test_kosum_yakinsadi(levha):
    kosu, _ = levha
    sonuc = kosu['sonuc']
    assert sonuc['converged'], sonuc['convergence_basis']
    assert sonuc['residual_history'][-1] < LEVHA_TOL
    bilesen = np.asarray(sonuc['viscous']['residual_components_scaled'])
    assert np.all(bilesen < 1e-8), f'bileşen kalıntıları: {bilesen}'


def test_enine_egrilik_olculdu_ve_ince(levha):
    """δ/R ÖLÇÜLÜR ve beyan edilir (§7'nin kendi şartı) — varsayılmaz."""
    _, m = levha
    p = m['pencere']
    d_star_R = float(m['d_star'][p].max() / LEVHA_R)
    delta_R = d_star_R / BLASIUS_DSTAR_OVER_DELTA
    assert d_star_R < 0.03, f'δ*/R = {d_star_R:.4f} — düz levha yaklaşımı zorlanıyor'
    assert delta_R < 0.10, f'δ/R = {delta_R:.4f} (δ* üstünden türetildi)'
    # Yerdeğiştirmenin çekirdeği hızlandırması ÖLÇÜLÜR (işaret kanıtı):
    # iç akışta kesit daralır → u_e artar → c_f fazlalığının payı budur.
    ilk, son = m['ue'][p][0], m['ue'][p][-1]
    assert son > ilk, (
        f'çekirdek hızı boyunca artmalıydı (yerdeğiştirme): {ilk:.2f} → '
        f'{son:.2f} m/s')
    assert (son / ilk - 1.0) < 0.05


def test_basamak7_c_f_blasius_bandinda(levha):
    """c_f = 0,664/√Re_x — ölçülen bant (40×96: ort 1,122)."""
    _, m = levha
    p = m['pencere']
    oran = m['c_f'][p] / m['c_f_blasius'][p]
    ort = float(np.mean(oran))
    lo, hi = CF_ORAN_BANDI
    assert lo < ort < hi, (
        f'c_f/Blasius ortalaması {ort:.3f}, bant [{lo}, {hi}] dışında; '
        f'istasyon bandı [{oran.min():.3f}, {oran.max():.3f}], '
        f'Re_x {m["Re_x"][p].min():.0f}-{m["Re_x"][p].max():.0f}')
    # c_f'nin x^(-1/2) YASASINA uyması: log-log eğim −0,5 (±0,05).
    # Bu, mutlak seviyeden bağımsız ve ızgara hatasına daha az duyarlı
    # ikinci bir hükümdür (tabaka gerçekten Blasius gibi BÜYÜYOR mu?).
    egim = np.polyfit(np.log(m['Re_x'][p]), np.log(m['c_f'][p]), 1)[0]
    lo_u, hi_u = CF_USTU_BANDI
    assert lo_u < egim < hi_u, (
        f'c_f ∝ Re_x^{egim:.3f} (Blasius −0,5; 40×192 ölçümü −0,506). '
        'Bu hüküm çözünürlüğe DUYARLIDIR: kaba ızgarada üs −0,77\'ye '
        'kadar dikleşiyor (docstring tablosu).')


def test_basamak7_delta_star_blasius_bandinda(levha):
    """δ* = 1,7208√(νx/u_e) — ölçülen bant (40×96: ort 0,952)."""
    _, m = levha
    p = m['pencere']
    oran = m['d_star'][p] / m['d_star_blasius'][p]
    ort = float(np.mean(oran))
    lo, hi = DSTAR_ORAN_BANDI
    assert lo < ort < hi, (
        f'δ*/Blasius ortalaması {ort:.3f}, bant [{lo}, {hi}] dışında; '
        f'istasyon bandı [{oran.min():.3f}, {oran.max():.3f}]')
    # δ*'ın HAM üssü 0,5 DEĞİLDİR (ÖLÇÜLDÜ: 0,415): çekirdek hızı
    # yerdeğiştirmeyle arttığı için δ* ∝ √(νx/u_e(x)) yavaşlar. Doğru
    # hüküm, u_e'yi zaten içeren ORANIN düzlüğüdür.
    assert float(np.max(oran) / np.min(oran)) < 1.15, (
        f'δ*/Blasius oranı x boyunca düz olmalı: bant '
        f'[{oran.min():.3f}, {oran.max():.3f}]')


def test_basamak7_bicim_faktoru(levha):
    """H = δ*/θ — Blasius 2,59; ölçülen 2,94 (40×96), bant beyanlı."""
    _, m = levha
    H = float(np.mean(m['H'][m['pencere']]))
    lo, hi = H_BANDI
    assert lo < H < hi, f'H = {H:.3f}, bant [{lo}, {hi}] dışında'


def test_duvar_noktasi_integrale_dahil_yoksa_delta_star_carpik_cikar(levha):
    """ÖLÇÜLEN HATANIN bekçisi: duvar noktası atlanırsa δ* 3× küçülür.

    Bu bekçi kodun bir dalını değil, ÖLÇÜM YÖNTEMİNİN kendisini korur:
    biri integrali "profil dizisinden" yeniden yazarsa (duvar noktası
    olmadan) sonuç sessizce yanlışlaşır. Burada iki biçim de hesaplanıp
    farkın GERÇEKTEN büyük olduğu ölçülür.
    """
    kosu, m = levha
    grid = kosu['grid']
    f = kosu['sonuc']['fields']
    rho, uz = f['rho_kg_m3'], f['u_z_m_s']
    y_sade = (LEVHA_R - grid.r_centers[0])[::-1]
    aki = ((rho * uz) / (rho[:, 0] * uz[:, 0])[:, None])[:, ::-1]
    d_star_sade = np.array([trapezoid(1.0 - aki[i], y_sade)
                            for i in range(grid.ni)])
    p = m['pencere']
    oran = float(np.mean(d_star_sade[p] / m['d_star'][p]))
    lo, hi = DSTAR_ORAN_BANDI
    kabul = float(np.mean(d_star_sade[p] / m['d_star_blasius'][p]))
    assert not (lo < kabul < hi), (
        f'duvar noktası atlanmış δ* ({kabul:.3f}) KABUL BANDININ '
        f'[{lo}, {hi}] içine düşüyor — bu vaka artık o yöntem hatasını '
        f'yakalamıyor (ham küçülme {1 - oran:.1%})')
    assert oran < 0.90, (
        f'duvarsız integral δ*\'ı yalnız {1 - oran:.1%} küçülttü')


def test_duvar_kayma_gerilmesi_akis_yonunde_ve_ayrilma_yok(levha):
    """Bağlı laminer tabakada τ_w > 0 (ayrılma ölçütünün işaret sözleşmesi)."""
    kosu, m = levha
    tau = kosu['sonuc']['viscous']['wall_shear_Pa']
    assert np.all(tau[m['pencere']] > 0.0)
    # Duvarda kütle sızıntısı yok (ayrık hava geçirmezlik)
    assert abs(kosu['sonuc']['wall_mass_flux_kg_s']) < 1e-12
    # Adyabatik duvar: q_w ayrık olarak TAM sıfır
    assert np.all(kosu['sonuc']['viscous']['wall_heat_flux_W_m2'] == 0.0)


def test_kutle_butcesi_kapanir(levha):
    kosu, _ = levha
    assert kosu['sonuc']['mass_balance_rel'] < 1e-4, (
        f'kütle bütçesi {kosu["sonuc"]["mass_balance_rel"]:.2e}')
