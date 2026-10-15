# tests/cfd — doğrulama merdiveni basamak 4-5: laminer boru (Poiseuille + Nu)
"""
Viskoz merdivenin İLK FİZİKSEL basamakları (tasarım belgesi
docs/mimari/cfd-viskoz-tasarimi.md §7):

  basamak 4  Hagen-Poiseuille  →  f·Re = 64, parabolik profil, u_maks/u_b = 2
  basamak 5  Isıl giriş/gelişim →  Nu = 3,657 (sabit duvar SICAKLIĞI)

ANALİTİK KÜNYELER
-----------------
* f·Re = 64 (çember kesitli boru, tam gelişmiş laminer): Hagen-Poiseuille
  yasasının Darcy sürtünme çarpanı biçimi; Shah, R. K. & London, A. L.,
  *Laminar Flow Forced Convection in Ducts*, Academic Press, 1978, Bölüm V
  (dairesel boru: f·Re = 64, Nu_T = 3,6568).
* Nu = 3,657 (sabit duvar sıcaklığı, tam gelişmiş): Graetz probleminin
  birinci özdeğerinden gelen asimptot (aynı kaynak). SABİT ÖZELLİK
  sonucudur — bu testin akışkanı da bilerek sabit özelliklidir.

SABİT q_w BASAMAĞI KAPSAM DIŞIDIR (beyan): Nu = 4,364 sabit ısı akısı
sınır koşulunu ister; V1 duvar ısıl kipleri ``isothermal`` ve
``adiabatic``tir (§5.4), sabit q_w BC'si YOKTUR. Uydurma bir üçüncü kip
eklemek yerine adyabatik kanat KURTARMA SICAKLIĞIYLA doğrulanır
(test_adiyabatik_duvar_kurtarma_sicakligini_olcer) ve 4,364 iddiası
KURULMAZ.

ZAMAN İLERLETME — NEDEN TESTİN İÇİNDE
-------------------------------------
``steady.solve_steady_axisym`` bu partide BAŞKA bir ajanın dosyasıdır ve
bugün viskoz kalıntı kancası YOKTUR. İki seçenek vardı: (a) steady.py'ye
dokunmak — YASAK, (b) merdiven basamağını testin kendi açık döngüsüyle
sürmek. (b) seçildi. Döngü 20 satırdır ve İÇİNDE FİZİK YOKTUR: kalıntı
tamamen ürün fonksiyonlarından gelir (``euler_core.residual_axisym`` +
``viscous.viscous_residual``), zaman adımı ürünün kendi sınırlarından
(``local_dt_axisym`` + ``viscous.viscous_local_dt_limit``). Yani burada
doğrulanan şey ÜRÜN kalıntısıdır; test yalnız onu köke sürer. Ürün
sürücüsü (§5.6 satır-örtük katman) geldiğinde bu döngü aynı köke
yakınsamalıdır — merdiven basamak 6 tam olarak bunu ölçecektir.

DOĞRULAMA AKIŞKANI (sabit özellikli, BEYANLI)
---------------------------------------------
μ ve k SABİTTİR (viskozite üssü 0): f·Re = 64 ve Nu = 3,657 sabit özellik
sonuçlarıdır, değişken özellikli bir akışkanla karşılaştırmak elmayla
armut olurdu. μ değeri Re ≈ 20 verecek biçimde SEÇİLMİŞTİR (doğrulama
vakası, gerçek bir gazın ölçümü değil — kaynağı 'verification_case' olarak
beyan edilir). Değişken özellikli yol (depodan ÖLÇÜLEN üs) h_g duyarlılık
koşusunda kullanılır ve orada gerçek V0 sarmalayıcısı
(``resolve_gas_transport``) çağrılır.

ÖLÇÜLDÜ (M4 Max, numba 0.61 arka ucu, 18 Ağustos 2026)
------------------------------------------------------
Basamak 4 — f·Re (duvar kayma gerilmesinden, pencere z/D ∈ [2, 5];
kalıntı eşiği 1e-7, koşum süreleri 9,5 / 22,2 / 43,1 s):

    nj (ni=6nj)   f·Re ort.   hata      u_maks/u_b   parabol sapması
     4  (24)      60,4387     −%5,57    1,9086       4,9e-04
     8  (48)      63,1687     −%1,30    1,9741       5,6e-04
    12  (72)      63,7042     −%0,46    1,9869       7,0e-04

  Gözlenen yakınsama mertebesi 2,10 (4→8) ve 2,55 (8→12) — ikinci
  mertebe sınıfı. Daha ince ızgarada (nj=16, derin yakınsama, ayrı
  koşum) f·Re = 63,71-63,95, yani hata −%0,45…−%0,08.
  Basınç düşümünden ölçülen f·Re sistematik olarak 0,2-0,45 YÜKSEK
  çıkar (nj=8'de 63,46 ↔ 63,29); fark ivme terimidir ve mertebesi
  γM² = 0,0036'dır (ölçülen bağıl fark 0,0027) — çelişki değil,
  sıkıştırılabilirliğin kendisi.

Basamak 5 — Nu (sönüm oranı yönteminden, pencere z/D ∈ [1, 5];
koşum süreleri 6,9 / 15,6 / 30,8 s):

    nj      Nu       3,657'ye göre    kaynak kayması C     R²
     4     3,9556       +%8,16          −3,33 K         0,99870
     8     3,7413       +%2,31          −3,40 K         0,99932
    12     3,6759       +%0,52          −3,21 K         0,99958

  PENCERE DUYARLILIĞI BEYANDIR (kiraz toplanmadı): aynı vakanın nj=4/8/16
  koşuları z/D ∈ [1,5; 5,5] penceresinde 3,778 / 3,628 / 3,568,
  z/D ∈ [2,0; 5,8] penceresinde 3,738 / 3,575 / 3,532 verir. Pencere
  seçimi ÖNDEN kuralla sabitlendi (aşağıdaki BORU_ISIL_PENCERESI: ısıl
  giriş uzunluğunun üstü, borunun son 1/6'sı hariç) — sonuca bakılarak
  seçilmedi. Bandın iki ucu iki farklı hatadır: pencerenin başı GİRİŞ
  etkisiyle Nu'yu YUKARI, sıkıştırılabilir kaynak kayması AŞAĞI çeker;
  ince ızgarada ikisi kısmen sadeleşir. Bu basamağın dürüst doğruluğu
  bu yüzden "%2 bandı"dır, "%0,5" DEĞİLDİR.

  YEREL tanım (Nu = q_w·D/(k(T_b−T_w))) aynı koşularda 4,13-4,66 verir ve
  YANILTICIDIR: sıkıştırılabilir kaynak (çekirdekte genleşme soğuması,
  duvarda viskoz yayılma ısınması) sürücü farkını sabit bir C kadar
  kaydırır. Model ṁ cp dT_b/dz = −π Nu k (T_b − T_w) + S iki parametreyle
  (λ, C) ÖLÇÜLÜR; uyum R² = 0,9993-0,99996'dır ve yerel tanımın sapması
  Nu_yerel = Nu·(1 − C/(T_b−T_w)) bağıntısıyla SAYISAL olarak açıklanır
  (bekçili). Kayma uydurulmadı, ölçüldü.

Ayna (wall_bc) etkisi — §5.1'in "varsayılmaz, ölçülür" maddesi. Ölçüm
İZOTERMAL vakada yapılır, çünkü adyabatik vakada q_w tanım gereği sıfırdır
(nj=8, z/D ∈ [1,5; 4,5], maksimum bağıl fark):
    f·Re   8,1e-04   (kaymaz 63,720 ↔ kayma 63,707)
    τ_w    3,0e-03   (1870,1 ↔ 1865,5 Pa)
    q_w    6,3e-03   (2,038e5 ↔ 2,031e5 W/m²; debi farkı 2,3e-03)
Yani bu vakada ayna seçimi q_w'yi binde 6 mertebesinde oynatır ve kaymaz
ayna f·Re'yi analitik değere BİR PARÇA yaklaştırır. Bu bir BORU ölçümüdür;
ince sınır tabakalı lülede etki daha büyük olabilir ve V3'te yeniden
ölçülecektir.

Düzeltmesiz yüz gradyanı (mutasyon ölçümü, nj=8): f·Re 63,02-63,30 yerine
60,39-60,87 (−%4,2) ve Re 19,61 yerine 20,35 — yani düzeltme kapatılınca
basamak 4 bandı KIRILIR.

VİSKOZ Δt SINIRI BU VAKADA BAĞLAYICI DEĞİL (ölçüldü, dolayısıyla C_visc
BURADA KALİBRE EDİLEMEZ — §5.6'nın "ölçmeden yazılmaz" maddesi):
    nj        4      8     16     48
    Δt_v/Δt_e 32,6   16,3   8,15   2,71
Yani viskoz sınır akustik sınırdan bir mertebe gevşek; oran Δr ile
yarılanıyor (Δt_v ∝ Δr², Δt_e ∝ Δr) ve duvar-çözümlü ızgarada bağlayıcı
hâle gelecek. Doğrudan kanıt: BORU_CVISC'i 0,2'den 3,0'a çıkarmak koşumu
HİÇ değiştirmedi (aynı iterasyon sayısı, aynı f·Re). Buradaki 0,4 bir
ihtiyat katsayısıdır, ÖLÇÜLMÜŞ bir kararlılık sınırı değildir; kalibrasyon
V2 ızgaralarının ve ürün sürücüsünün işidir.

h_g duyarlılık koşusunun DEBİ karışması (kapsam beyanı, ölçüldü, nj=4,
değişken özellikli akışkan): T_w = 0,3·T0 koşusu ṁ = 2,35e-2 kg/s,
T_w = 0,6·T0 koşusu ṁ = 1,63e-2 kg/s (oran 1,44) — boru sabit basınç
düşümüyle sürüldüğü için soğuk duvar debiyi büyütür. Lülede debi boğazdan
kilitlidir; bu karışma orada YOKTUR (V3).

MALİYET: bu dosya tam koşumda ~2,5-3 dakikadır (10 kararlı-hâl koşusu).
Merdivenin en pahalı basamağı ince ızgaralardır ve gerekçesi yakınsama
MERTEBESİ iddiasının üç noktaya ihtiyaç duymasıdır.
"""

import numpy as np
import pytest

from hrma.cfd.euler_core import (
    WALL_BC_NOSLIP, WALL_BC_SLIP, cons_to_prim_axisym,
    inlet_state_from_stagnation, local_dt_axisym, precompute_geometry,
    prim_to_cons_axisym, residual_axisym,
)
from hrma.cfd.gas_transport import resolve_gas_transport
from hrma.cfd.gradients import precompute_gradient_geometry
from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.viscous import (
    h_g_wall_temp_sensitivity, viscous_local_dt_limit, viscous_residual,
)

from .test_viskoz_aki import (
    VISK_CP, VISK_GAMMA, VISK_PRANDTL, VISK_R, transport as visk_transport,
)

# --- analitik referanslar (Shah & London 1978, dairesel boru) ---
POISEUILLE_F_RE = 64.0
GRAETZ_NU_SABIT_DUVAR_SICAKLIGI = 3.657

# --- vaka (BORU_ öneki: conftest'in LULE_ kuralıyla aynı disiplin) ---
BORU_D = 0.010                  # çap [m]
BORU_L = 0.060                  # uzunluk [m] (L/D = 6)
BORU_P0 = 1.0e6                 # rezervuar basıncı [Pa]
BORU_T0 = 3000.0                # rezervuar sıcaklığı [K] (roket ölçeği)
BORU_PB = 0.9628e6              # geri basınç [Pa] → Δp/p ≈ %3,7
BORU_MU = 0.03193               # doğrulama akışkanı viskozitesi [Pa·s]
BORU_U_TAHMINI = 55.0           # başlangıç tahmini [m/s] (cevap DEĞİL)
BORU_TW_ORANI = 0.95            # izotermal duvar: T_w = 0,95·T0

# --- sürücü ayarları ---
BORU_CFL = 0.5                  # Euler yerel-Δt katsayısı
#: Viskoz Δt sınırının ihtiyat katsayısı. ÖLÇÜLDÜ: bu vakada sınır HİÇ
#: bağlayıcı değil (dosya başındaki Δt_v/Δt_e tablosu), o yüzden bu sayı
#: bir kararlılık kalibrasyonu DEĞİLDİR ve öyle sunulmaz.
BORU_CVISC = 0.4

#: Durma ölçütü. ÖLÇÜLDÜ (nj=16, adyabatik): 3e-6'da f·Re = 64,011 ama
#: derin yakınsamada 63,83 — yani gevşek eşikte İTERASYON hatası ayrıklaştırma
#: hatasıyla aynı mertebeye çıkıyor ve "mükemmel" bir sonuç TESADÜFEN
#: doğuyor. 1e-7'de iterasyon hatası ayrıklaştırmanın onda birinin altında
#: (nj=12'de 63,704 ↔ derin 63,70). Yakınsama merdiveni ancak böyle
#: okunabilir; eşik ucuzluk için gevşetilmez.
BORU_TOL_RES = 1.0e-7
#: Bant/karşılaştırma koşuları (h_g) için gevşek eşik: orada MUTLAK değer
#: iddiası yok, iki koşunun ORANI okunuyor.
BORU_TOL_RES_KABA = 3.0e-6

#: Izgara merdiveni (yakınsama MERTEBESİ iddiası üç nokta ister).
BORU_MERDIVEN_NJ = (4, 8, 12)


def _iterasyon_tavani(nj):
    """Ölçülen ihtiyacın ~2 katı (nj=4: 6300, nj=8: 10750, nj=12: 15400)."""
    return 2000 * nj + 6000


# --- ölçüm pencereleri (a priori kural, sonuca göre seçilmedi) ---
#   alt sınır: ısıl/hidrodinamik giriş uzunluğunun (0,05·Re·D ≈ 1·D ve
#              0,05·Re·Pr·D ≈ 0,7·D) ÜSTÜ,
#   üst sınır: borunun son 1/6'sı ÇIKIŞ sınır koşulu etkisi diye dışarıda.
BORU_HIZ_PENCERESI = (2.0, 5.0)     # z/D — basamak 4
BORU_ISIL_PENCERESI = (1.0, 5.0)    # z/D — basamak 5


def boru_gridi(nj):
    """nj radyal hücre, ni = 6·nj eksenel hücre (en-boy oranı ≈ 2)."""
    ni = 6 * nj
    z = np.linspace(0.0, BORU_L, ni + 1)
    return build_grid_from_wall(z, np.full(ni + 1, 0.5 * BORU_D), nj)


def boru_tasinimi(mu_ref=BORU_MU):
    """Sabit özellikli doğrulama akışkanı (üs 0 → μ, k sabit)."""
    return visk_transport(exponent=0.0, mu_ref=mu_ref)


def boru_iletkenligi(mu_ref=BORU_MU):
    return VISK_CP * mu_ref / VISK_PRANDTL


def _baslangic(grid, u_tahmini, pb):
    """Başlangıç TAHMİNİ: düzgün hız + doğrusal basınç (parabol DEĞİL).

    Kararlı-hâl kökü başlangıç durumundan bağımsızdır; bu yalnız geçiş
    süresini kısaltır. Cevabı (parabolik profil) tohumlamamak bilinçlidir.
    """
    p = BORU_P0 + (pb - BORU_P0) * (grid.z_centers / np.max(grid.Z))
    rho = p / (VISK_R * BORU_T0)
    return prim_to_cons_axisym(rho, np.full_like(p, u_tahmini),
                               np.zeros_like(p), p, VISK_GAMMA)


def kosum(nj, *, wall_thermal, T_wall=None, wall_bc=WALL_BC_NOSLIP,
          corrected=True, mu_ref=BORU_MU, pb=BORU_PB, tasinim=None,
          u_tahmini=BORU_U_TAHMINI, tol=BORU_TOL_RES):
    """Açık SSP-RK2 + yerel Δt ile kararlı-hâle sürer (fizik ÜRÜNDEN).

    Kalıntı ölçütü: maks |R·Δt| / maks|U| (bileşen başına ölçekli); yani
    "bir adımda durumun bağıl olarak ne kadar değiştiği". Yakınsama HÜKÜM
    olarak döner (converged), eşiğe inilmezse test bunu görür.
    """
    grid = boru_gridi(nj)
    tr = tasinim if tasinim is not None else boru_tasinimi(mu_ref)
    geom = precompute_geometry(grid)
    grad_geom = precompute_gradient_geometry(grid)
    n_out = geom['n_out_hat']
    kw = dict(wall_thermal=wall_thermal, geom=geom, grad_geom=grad_geom,
              corrected=corrected)
    if wall_thermal == 'isothermal':
        kw.update(T_wall=T_wall, T_wall_source='verification_case')

    def kalinti(U):
        w = cons_to_prim_axisym(U, VISK_GAMMA)
        w_in = inlet_state_from_stagnation(w[0], VISK_GAMMA, VISK_R,
                                           BORU_P0, BORU_T0)
        w_out = np.array(w[-1], copy=True)
        a = np.sqrt(VISK_GAMMA * w[-1, :, 3] / w[-1, :, 0])
        un = w[-1, :, 1] * n_out[:, 0] + w[-1, :, 2] * n_out[:, 1]
        w_out[:, 3] = np.where(un / a < 1.0, pb, w_out[:, 3])
        du_e, aux_e = residual_axisym(U, grid, VISK_GAMMA, VISK_R, BORU_P0,
                                      BORU_T0, Pb=pb, geom=geom,
                                      wall_bc=wall_bc)
        du_v, aux_v = viscous_residual(grid, U, tr, R=VISK_R,
                                       inlet_face_primitives=w_in,
                                       outlet_face_primitives=w_out, **kw)
        return du_e + du_v, aux_e, aux_v

    U = _baslangic(grid, u_tahmini, pb)
    tavan = _iterasyon_tavani(nj)
    res = float('inf')
    it = 0
    for it in range(1, tavan + 1):
        dt = np.minimum(
            local_dt_axisym(U, grid, VISK_GAMMA, BORU_CFL, geom['area_i'],
                            geom['area_j']),
            BORU_CVISC * viscous_local_dt_limit(grid, U, tr, R=VISK_R,
                                                geom=geom))[..., None]
        r1, _, _ = kalinti(U)
        u1 = U + dt * r1
        r2, _, _ = kalinti(u1)
        U = 0.5 * (U + u1 + dt * r2)
        assert np.all(np.isfinite(U)), (
            f'nj={nj} {wall_thermal}: koşum {it}. adımda ıraksadı '
            f'(NaN/Inf) — açık yol kararlılık sınırını aşmış olabilir')
        if it % 50 == 0:
            olcek = np.max(np.abs(U), axis=(0, 1))
            res = float(np.max(np.abs(r1 * dt) / olcek))
            if res <= tol:
                break
    _, aux_e, aux_v = kalinti(U)
    return {'grid': grid, 'transport': tr, 'U': U, 'aux_euler': aux_e,
            'aux_visc': aux_v, 'iterations': it, 'residual': res,
            'converged': res <= tol, 'nj': nj, 'mu_ref': mu_ref,
            'wall_bc': wall_bc, 'wall_thermal': wall_thermal,
            'T_wall': T_wall, 'pb': pb}


def kesit_olcumleri(kosu):
    """Kesit ortalamaları ve duvar büyüklükleri (istasyon dizileri)."""
    grid, U = kosu['grid'], kosu['U']
    tr = kosu['transport']
    w = cons_to_prim_axisym(U, VISK_GAMMA)
    rho, uz, p = w[..., 0], w[..., 1], w[..., 3]
    T = p / (rho * VISK_R)
    wall = kosu['aux_visc']['wall']
    dz = grid.Z[1:, 0] - grid.Z[:-1, 0]
    dA = grid.volume / dz[:, None]                 # halka alanı 2π r dr
    alan = np.sum(dA, axis=1)
    rho_b = np.sum(rho * dA, axis=1) / alan
    mdot = np.sum(rho * uz * dA, axis=1)
    u_b = mdot / (rho_b * alan)
    T_b = np.sum(rho * uz * T * dA, axis=1) / mdot
    p_b = np.sum(p * dA, axis=1) / alan
    mu = tr.viscosity(T)
    mu_b = np.sum(mu * dA, axis=1) / alan
    Re = rho_b * u_b * BORU_D / mu_b
    c_f = wall.tau_wall_Pa / (0.5 * rho_b * u_b ** 2)
    return {'z_D': grid.z_centers[:, 0] / BORU_D, 'Re': Re, 'u_b': u_b,
            'rho_b': rho_b, 'T_b': T_b, 'p_b': p_b, 'mdot': mdot,
            'f_Re': 4.0 * c_f * Re, 'c_f': c_f, 'uz': uz, 'T': T,
            'mach': u_b / np.sqrt(VISK_GAMMA * p_b / rho_b),
            'tau_w': wall.tau_wall_Pa, 'q_w': wall.q_wall_W_m2,
            'T_wall': wall.T_wall_K, 'mu_b': mu_b}


def pencere(m, sinirlar):
    lo, hi = sinirlar
    return (m['z_D'] >= lo) & (m['z_D'] <= hi)


def parabol_uyumu(grid, uz_kesit):
    """u(r) = c0 + c2 r² en küçük kareler → (sapma, −c2R²/c0 oranı).

    Tam parabolik Poiseuille profilinde oran 1,0'dır (u = u_maks(1−r²/R²)).
    """
    r = grid.r_centers[0]
    A = np.stack([np.ones_like(r), r ** 2], axis=1)
    c, *_ = np.linalg.lstsq(A, uz_kesit, rcond=None)
    sapma = float(np.max(np.abs(uz_kesit - A @ c)) / np.max(np.abs(uz_kesit)))
    return sapma, float(-c[1] * (0.5 * BORU_D) ** 2 / c[0]), c


def nu_sonum_uyumu(m, mdot, k, mask):
    """Nu'yu SÖNÜM ORANINDAN ölçer (kaynak kaymalı üstel model).

        ṁ cp dT_b/dz = −π Nu k (T_b − T_w) + S

    Ayrık biçimde Δy = a·y + b doğrusal regresyonu (y = T_b − T_w):
        λ = −ln(1+a)/h,  Nu = λ ṁ cp/(π k),  C = −b/a = S/(π Nu k)

    C, sıkıştırılabilir kaynağın (çekirdekte genleşme soğuması ↔ duvarda
    viskoz yayılma ısınması) sürücü farkına bindirdiği KAYMADIR ve
    ölçülür — yerel Nu tanımının neden yanıltıcı olduğunun sayısal
    açıklamasıdır.
    """
    idx = np.flatnonzero(mask)
    assert idx.size >= 6, 'sönüm uyumu için pencerede yeterli istasyon yok'
    y = m['dT'][idx[:-1]]
    dy = m['dT'][idx[1:]] - m['dT'][idx[:-1]]
    h = m['z_m'][1] - m['z_m'][0]
    A = np.stack([y, np.ones_like(y)], axis=1)
    (a, b), *_ = np.linalg.lstsq(A, dy, rcond=None)
    tahmin = A @ np.array([a, b])
    r2 = 1.0 - np.sum((dy - tahmin) ** 2) / np.sum((dy - dy.mean()) ** 2)
    lam = -np.log1p(a) / h
    return {'Nu': lam * mdot * VISK_CP / (np.pi * k), 'C_K': -b / a,
            'lambda_1_m': lam, 'r2': r2}


# ===========================================================================
# Fikstürler — pahalı koşular BİR kez (süit disiplini)
# ===========================================================================

@pytest.fixture(scope='module')
def merdiven_adiabatik():
    """Basamak 4: adyabatik duvar (T sabit → ρ sabit → HP geçerli)."""
    return {nj: kosum(nj, wall_thermal='adiabatic')
            for nj in BORU_MERDIVEN_NJ}


@pytest.fixture(scope='module')
def merdiven_isil():
    """Basamak 5: izotermal duvar, T_w = 0,95·T0 (küçük ΔT → sabit özellik)."""
    return {nj: kosum(nj, wall_thermal='isothermal',
                      T_wall=BORU_TW_ORANI * BORU_T0)
            for nj in BORU_MERDIVEN_NJ}


@pytest.fixture(scope='module')
def ayna_kayma_kosumu():
    """Aynı vaka, MUSCL hayaleti kayma aynası (karşılaştırma koşusu)."""
    return kosum(BORU_MERDIVEN_NJ[1], wall_thermal='isothermal',
                 T_wall=BORU_TW_ORANI * BORU_T0, wall_bc=WALL_BC_SLIP)


@pytest.fixture(scope='module')
def duzeltmesiz_kosum():
    """Düzeltmesiz yüz gradyanı (mutasyon ölçümü, kaba ızgara)."""
    return kosum(BORU_MERDIVEN_NJ[0], wall_thermal='adiabatic',
                 corrected=False)


@pytest.fixture(scope='module')
def hg_tasinimi():
    """h_g duyarlılığı için DEĞİŞKEN özellikli akışkan.

    Gerçek V0 sarmalayıcısı çağrılır: μ_ref/cp/Pr çağırandan gelir, ama
    sıcaklık üssü DEPODAN ÖLÇÜLÜR (gas_transport.viscosity_exponent).
    Böylece bu koşu μ(T) değişimini gerçekten taşır.
    """
    return resolve_gas_transport(gamma=VISK_GAMMA, T_ref=BORU_T0,
                                 mu_ref=BORU_MU, cp=VISK_CP,
                                 prandtl=VISK_PRANDTL)


# ===========================================================================
# Basamak 4 — Hagen-Poiseuille
# ===========================================================================

def test_basamak4_kosumlar_yakinsadi(merdiven_adiabatik):
    """Hüküm önce: yakınsamamış koşudan fizik iddiası çıkarılmaz."""
    for nj, kosu in merdiven_adiabatik.items():
        assert kosu['converged'], (
            f'nj={nj}: kalıntı {kosu["residual"]:.2e} > {BORU_TOL_RES:g} '
            f'({kosu["iterations"]} iterasyon) — bu koşudan f·Re iddiası '
            f'kurulamaz')


def test_basamak4_vaka_rejimi_laminer_ve_dusuk_mach(merdiven_adiabatik):
    """Vakanın KENDİSİ ölçülür: Re ve M analitik referansın geçerlilik
    alanında mı (laminer, sıkıştırılamaz limite yakın)?"""
    for nj, kosu in merdiven_adiabatik.items():
        m = kesit_olcumleri(kosu)
        maske = pencere(m, BORU_HIZ_PENCERESI)
        assert 15.0 < float(np.min(m['Re'][maske])) < 25.0
        assert float(np.max(m['Re'])) < 2300.0, 'laminer bandın dışı'
        assert float(np.max(m['mach'])) < 0.10, (
            f'nj={nj}: M = {float(np.max(m["mach"])):.3f} — sıkıştırılabilir '
            f'düzeltme (γM²) f·Re bandını yer')


def test_basamak4_f_Re_64e_yakinsar_ve_mertebe_olculur(merdiven_adiabatik):
    """f·Re = 64: ızgara inceldikçe hata küçülür, MERTEBE ölçülür.

    Mertebeye ALT sınır konur (birinci mertebe sınıfı bir duvar gradyanı
    kusuru burada kırmızıya düşer), ÜST sınır konmaz: iki hata kaynağı
    (duvar gradyanı ve sıkıştırılabilirlik) kısmen sadeleşince gözlenen
    mertebe ikiyi aşabilir ve bu bir KUSUR değildir. Asıl teminat hata
    dizisinin tekdüze düşmesi ve en ince ızgaranın bandıdır.
    """
    kaba, orta, ince = BORU_MERDIVEN_NJ
    hata, olculen = {}, {}
    for nj, kosu in merdiven_adiabatik.items():
        m = kesit_olcumleri(kosu)
        maske = pencere(m, BORU_HIZ_PENCERESI)
        f_re = m['f_Re'][maske]
        # Pencere içi değişim sıkıştırılabilirlik mertebesinde kalmalı.
        assert (f_re.max() - f_re.min()) / f_re.mean() < 0.02
        olculen[nj] = float(np.mean(f_re))
        hata[nj] = abs(olculen[nj] - POISEUILLE_F_RE)

    assert hata[kaba] > hata[orta] > hata[ince], (
        f'f·Re hatası ızgarayla düşmüyor: {olculen} — yakınsama yok')
    assert hata[ince] / POISEUILLE_F_RE < 0.01, (
        f'en ince ızgarada f·Re = {olculen[ince]:.4f}, hata '
        f'%{100 * hata[ince] / POISEUILLE_F_RE:.2f} > %1')
    mertebe = (np.log(hata[kaba] / hata[orta]) / np.log(orta / kaba),
               np.log(hata[orta] / hata[ince]) / np.log(ince / orta))
    assert min(mertebe) > 1.5, (
        f'gözlenen yakınsama mertebesi {mertebe} — birinci mertebe sınıfı; '
        f'duvar yüz gradyanı tek yanlı kompakt farka bağlı olmalıydı '
        f'(ölçülen f·Re: {olculen})')


def test_basamak4_profil_paraboliktir(merdiven_adiabatik):
    """Parabolik profil + u_maks/u_b → 2 (ızgarayla iyileşerek)."""
    kaba, _, ince = BORU_MERDIVEN_NJ
    sapmalar, oranlar, tepe = {}, {}, {}
    for nj, kosu in merdiven_adiabatik.items():
        m = kesit_olcumleri(kosu)
        i = int(np.flatnonzero(pencere(m, BORU_HIZ_PENCERESI))[-2])
        sapma, oran, c = parabol_uyumu(kosu['grid'], m['uz'][i])
        sapmalar[nj], oranlar[nj] = sapma, oran
        # u_maks parabol UYUMUNDAN alınır (eksen hücresinin merkez değeri
        # değil — o r_c = Δr/2'de örneklenmiştir ve tepeyi eksik ölçer).
        tepe[nj] = float(c[0] / m['u_b'][i])
    assert max(sapmalar.values()) < 2e-3, (
        f'parabolden sapma bandı {sapmalar} — profil parabolik değil')
    assert all(abs(o - 1.0) < 0.02 for o in oranlar.values()), (
        f'parabol katsayı oranı {oranlar} (analitik 1,0)')
    assert abs(tepe[ince] - 2.0) < abs(tepe[kaba] - 2.0), (
        f'u_maks/u_b ızgarayla 2,0\'a yaklaşmıyor: {tepe}')
    assert abs(tepe[ince] - 2.0) < 0.02, (
        f'en ince ızgarada u_maks/u_b = {tepe[ince]:.4f} (analitik 2,0)')


def test_basamak4_basinctan_olculen_f_ivme_terimi_kadar_farkli(
        merdiven_adiabatik):
    """İki bağımsız f ölçümü: τ_w'den ve dp/dz'den. Fark ivme terimidir
    ve mertebesi γM²'dir — bu SAYIYLA gösterilir, varsayılmaz."""
    kosu = merdiven_adiabatik[BORU_MERDIVEN_NJ[1]]
    m = kesit_olcumleri(kosu)
    maske = pencere(m, BORU_HIZ_PENCERESI)
    z = kosu['grid'].z_centers[:, 0]
    dpdz = np.gradient(m['p_b'], z)
    f_p = -dpdz * BORU_D / (0.5 * m['rho_b'] * m['u_b'] ** 2)
    bagil = float(np.mean((f_p * m['Re'])[maske] - m['f_Re'][maske])
                  / np.mean(m['f_Re'][maske]))
    gm2 = VISK_GAMMA * float(np.mean(m['mach'][maske] ** 2))
    assert 0.0 < bagil < 3.0 * gm2, (
        f'dp/dz ve τ_w yollarının farkı {bagil:.3e}, γM² = {gm2:.3e} — '
        f'ivme terimiyle açıklanamıyor')


def test_basamak4_kutle_korunumu_ve_duvarda_sizma_yok(merdiven_adiabatik):
    for nj, kosu in merdiven_adiabatik.items():
        ae = kosu['aux_euler']
        bagil = abs(ae['mass_flow_in_kg_s'] - ae['mass_flow_out_kg_s']) \
            / abs(ae['mass_flow_in_kg_s'])
        assert bagil < 1e-3, f'nj={nj}: kütle bütçesi açığı {bagil:.2e}'
        assert ae['wall_mass_flux_kg_s'] == 0.0
        assert kosu['aux_visc']['max_abs_mass_residual'] == 0.0


def test_basamak4_adiyabatik_duvarda_isi_akisi_yoktur(merdiven_adiabatik):
    for kosu in merdiven_adiabatik.values():
        assert np.array_equal(kosu['aux_visc']['wall'].q_wall_W_m2,
                              np.zeros(kosu['grid'].ni))
        assert kosu['aux_visc']['wall_heat_W'] == 0.0


def test_adiyabatik_duvar_kurtarma_sicakligini_olcer(merdiven_adiabatik):
    """Adyabatik kanat: duvar sıcaklığı KURTARMA sıcaklığıdır (ölçülür).

    Düşük Mach borusunda T_aw ≈ T0'dır; sapma kinetik terim mertebesinde
    (u²/2cp) kalmalıdır. Bu, sabit-q_w basamağının yerine geçen kapsam
    beyanının ölçülen ayağıdır (§7 basamak 5 notu).
    """
    kosu = merdiven_adiabatik[BORU_MERDIVEN_NJ[1]]
    m = kesit_olcumleri(kosu)
    T_aw = kosu['aux_visc']['wall'].T_wall_K
    kinetik = float(np.max(m['u_b'] ** 2)) / (2.0 * VISK_CP)
    sapma = float(np.max(np.abs(T_aw - BORU_T0)))
    assert sapma < 5.0 * kinetik, (
        f'adyabatik duvar sıcaklığı T0\'dan {sapma:.2f} K sapıyor; kinetik '
        f'ölçek {kinetik:.2f} K')
    assert np.all(T_aw > 0.99 * BORU_T0)


# ===========================================================================
# Basamak 5 — Nusselt (sabit duvar sıcaklığı)
# ===========================================================================

def _nu_olcumu(kosu):
    m = kesit_olcumleri(kosu)
    m['dT'] = m['T_b'] - kosu['T_wall']
    m['z_m'] = m['z_D'] * BORU_D
    uyum = nu_sonum_uyumu(m, kosu['aux_euler']['mass_flow_in_kg_s'],
                          boru_iletkenligi(kosu['mu_ref']),
                          pencere(m, BORU_ISIL_PENCERESI))
    return m, uyum


def test_basamak5_kosumlar_yakinsadi(merdiven_isil):
    for nj, kosu in merdiven_isil.items():
        assert kosu['converged'], (
            f'nj={nj}: ısıl koşum yakınsamadı (kalıntı '
            f'{kosu["residual"]:.2e})')


def test_basamak5_Nu_3657ye_yakinsar(merdiven_isil):
    """Nu = 3,657: sönüm oranından ölçülür, ızgarayla yakınsar."""
    kaba, orta, ince = BORU_MERDIVEN_NJ
    hata, olculen = {}, {}
    for nj, kosu in merdiven_isil.items():
        m, uyum = _nu_olcumu(kosu)
        assert uyum['r2'] > 0.998, (
            f'nj={nj}: üstel sönüm modeli uymuyor (R² = {uyum["r2"]:.5f}) — '
            f'Nu bu yoldan okunamaz')
        olculen[nj] = (round(uyum['Nu'], 4), round(uyum['C_K'], 3))
        hata[nj] = abs(uyum['Nu'] - GRAETZ_NU_SABIT_DUVAR_SICAKLIGI)
    assert hata[kaba] > hata[orta] > hata[ince], (
        f'Nu hatası ızgarayla düşmüyor: (Nu, C) = {olculen}')
    bagil = hata[ince] / GRAETZ_NU_SABIT_DUVAR_SICAKLIGI
    assert bagil < 0.02, (
        f'en ince ızgarada Nu hatası %{100 * bagil:.2f} > %2 '
        f'(ölçülen (Nu, C) = {olculen})')


def test_basamak5_yerel_Nu_tanimindaki_sapma_kaynak_kaymasiyla_aciklanir(
        merdiven_isil):
    """Yerel tanım (q_w D/(k ΔT)) YANILTICIDIR ve bu SAYIYLA gösterilir:

        Nu_yerel = Nu · (1 − C/(T_b − T_w))

    C ölçülen kaynak kaymasıdır. Bu bekçi, "yerel Nu 4,3 çıktı, demek ki
    kod bozuk" ve "kod doğru, farkı görmezden gel" hatalarının İKİSİNİ de
    engeller.
    """
    kosu = merdiven_isil[BORU_MERDIVEN_NJ[-1]]
    m, uyum = _nu_olcumu(kosu)
    k = boru_iletkenligi(kosu['mu_ref'])
    maske = pencere(m, BORU_ISIL_PENCERESI)
    nu_yerel = m['q_w'] * BORU_D / (k * m['dT'])
    beklenen = uyum['Nu'] * (1.0 - uyum['C_K'] / m['dT'])
    # Sürücü farkı kaymanın en az üç katı olan istasyonlarda karşılaştır
    # (küçük ΔT'de her iki taraf da 0/0'a gider — orada iddia kurulmaz).
    guvenli = maske & (np.abs(m['dT']) > 3.0 * abs(uyum['C_K']))
    assert guvenli.sum() >= 5
    bagil = np.abs(nu_yerel[guvenli] - beklenen[guvenli]) / beklenen[guvenli]
    assert float(np.max(bagil)) < 0.10, (
        f'yerel Nu sapması kaynak kaymasıyla açıklanamıyor (maks bağıl '
        f'fark {float(np.max(bagil)):.3f})')
    assert float(np.max(nu_yerel[guvenli])) > 1.05 * uyum['Nu'], (
        'yerel tanım ile sönüm tanımı ayırt edilemiyor — bekçi kör')


def test_basamak5_enerji_butcesi_kapanir(merdiven_isil):
    """Duvara giden ısı = sınırlardan giren net enerji (Euler + viskoz)."""
    for nj, kosu in merdiven_isil.items():
        ae, av = kosu['aux_euler'], kosu['aux_visc']
        net = ((ae['energy_flux_in_W'] - ae['energy_flux_out_W'])
               - av['inlet_energy_flux_W'] + av['outlet_energy_flux_W'])
        bagil = abs(net - av['wall_heat_W']) / abs(av['wall_heat_W'])
        assert bagil < 5e-3, (
            f'nj={nj}: enerji bütçesi %{100 * bagil:.3f} açık — duvar ısı '
            f'akısı ile sınır akıları uyuşmuyor')


def test_basamak5_yerel_enerji_dengesi_duvar_akisini_dogrular(merdiven_isil):
    """İstasyon bazında ṁ cp dT_b/dz = −q_w·πD (duvar akısının ikinci
    bağımsız okunuşu: kesit sıcaklık türevinden)."""
    kosu = merdiven_isil[BORU_MERDIVEN_NJ[-1]]
    m, _ = _nu_olcumu(kosu)
    mdot = kosu['aux_euler']['mass_flow_in_kg_s']
    z = kosu['grid'].z_centers[:, 0]
    sol = mdot * VISK_CP * np.gradient(m['T_b'], z)
    sag = -m['q_w'] * np.pi * BORU_D
    maske = pencere(m, BORU_ISIL_PENCERESI)
    bagil = np.abs(sol[maske] - sag[maske]) / np.abs(sag[maske])
    assert float(np.max(bagil)) < 0.05, (
        f'yerel enerji dengesi kapanmıyor (maks bağıl fark '
        f'{float(np.max(bagil)):.3f})')


# ===========================================================================
# Ayna (wall_bc) etkisi — VARSAYILMAZ, ÖLÇÜLÜR (§5.1)
# ===========================================================================

def test_ayna_secimi_q_w_ve_c_f_uzerinde_olculur(merdiven_isil,
                                                 ayna_kayma_kosumu):
    """Kayma ↔ kaymaz MUSCL hayaleti: fark RAPORLANIR ve iki yönlü
    sınırlanır — ne sıfır (yani seçim etkisiz değil) ne de bandı yiyecek
    kadar büyük."""
    noslip = kesit_olcumleri(merdiven_isil[BORU_MERDIVEN_NJ[1]])
    slip = kesit_olcumleri(ayna_kayma_kosumu)
    maske = pencere(noslip, (1.5, 4.5))
    farklar = {}
    for ad in ('f_Re', 'tau_w', 'q_w'):
        farklar[ad] = float(np.max(
            np.abs(slip[ad][maske] - noslip[ad][maske])
            / np.abs(noslip[ad][maske])))
    assert farklar['q_w'] > 1e-4, (
        f'ayna seçimi q_w\'yi hiç oynatmadı ({farklar}) — hayalet dalı ölü '
        f'ya da ölçüm kör')
    assert farklar['q_w'] < 0.02 and farklar['tau_w'] < 0.02, (
        f'ayna seçimi bu vakada %2\'den fazla oynatıyor: {farklar} — '
        f'basamak 4-5 bandı ayna seçimine bağımlı hâle gelmiş')
    # Kaymaz ayna FİZİKSEL olan seçimdir: f·Re analitik değere daha yakın
    # olmalı (bu bir hüküm değil ölçüm — kırmızıya düşerse gerekçe aranır).
    assert abs(np.mean(noslip['f_Re'][maske]) - POISEUILLE_F_RE) <= \
        abs(np.mean(slip['f_Re'][maske]) - POISEUILLE_F_RE) + 0.2


def test_duzeltmesiz_gradyan_basamak4_bandini_kirar(merdiven_adiabatik,
                                                    duzeltmesiz_kosum):
    """Mutasyon ölçümü: yüz gradyanı düzeltmesi kapatılırsa f·Re ölçülebilir
    biçimde bozulur (bekçinin ısırığı sayıyla gösterilir)."""
    duz = kesit_olcumleri(merdiven_adiabatik[BORU_MERDIVEN_NJ[0]])
    ham = kesit_olcumleri(duzeltmesiz_kosum)
    maske = pencere(duz, BORU_HIZ_PENCERESI)
    f_duz = float(np.mean(duz['f_Re'][maske]))
    f_ham = float(np.mean(ham['f_Re'][maske]))
    assert abs(f_ham - POISEUILLE_F_RE) > abs(f_duz - POISEUILLE_F_RE), (
        f'düzeltmesiz gradyan f·Re\'yi kötüleştirmedi ({f_ham:.3f} ↔ '
        f'{f_duz:.3f}) — düzeltmenin gerekçesi ölçülemiyor')
    assert (f_duz - f_ham) / f_duz > 0.01


# ===========================================================================
# h_g duvar sıcaklığı duyarlılığı (§5.4) — GERÇEK koşumla
# ===========================================================================

def test_h_g_duvar_sicakligi_duyarliligi_olculur(merdiven_adiabatik,
                                                 hg_tasinimi):
    """İki T_w koşusundan h_g bandı ÖLÇÜLÜR (§5.4) — GERÇEK koşumla.

    KAPSAM BEYANI (ölçülen, prose değil): bu bir BORU ölçümüdür ve bandı
    lüle h_g bandı gibi okumak YANLIŞ olur. Sebep ölçülüyor: borunun debisi
    SABİT BASINÇ DÜŞÜMÜYLE sürülür, duvar soğudukça gaz yoğunlaşır ve debi
    BÜYÜR (ölçüldü: T_w = 0,3·T0 koşusu 0,6·T0 koşusundan ~1,4× daha çok
    debi taşır). Yani bant, film katsayısının T_w bağımlılığıyla DEBİ
    değişimini birlikte taşır. Lülede debi boğazdan kilitlidir ve bu
    karışma olmaz — o ölçüm V3'ün işidir. Aşağıdaki debi bekçisi, biri
    vakayı değiştirdiğinde bu beyanın da güncellenmesini zorlar.

    Kurtarma sıcaklığı UYDURULMAZ: adyabatik eş koşudan ÖLÇÜLÜR (düşük
    Mach borusunda T_aw ≈ T0 — bekçili).
    """
    T_aw = float(np.mean(
        merdiven_adiabatik[BORU_MERDIVEN_NJ[1]]['aux_visc']['wall'].T_wall_K))
    assert abs(T_aw - BORU_T0) / BORU_T0 < 0.01

    tr = hg_tasinimi
    assert tr.sources['viscosity'] == 'caller'
    assert tr.viscosity_exponent > 0.0, (
        'değişken özellik koşusu için depodan ÖLÇÜLEN üs gerekli')

    debiler = {}

    def kos(T_w):
        kosu = kosum(BORU_MERDIVEN_NJ[0], wall_thermal='isothermal',
                     T_wall=T_w, tasinim=tr, u_tahmini=30.0,
                     tol=BORU_TOL_RES_KABA)
        assert kosu['converged'], (
            f'h_g koşusu T_w={T_w:.0f} K yakınsamadı '
            f'(kalıntı {kosu["residual"]:.2e})')
        debiler[T_w] = kosu['aux_euler']['mass_flow_in_kg_s']
        return kosu['aux_visc']['wall']

    sonuc = h_g_wall_temp_sensitivity(kos, BORU_T0,
                                      recovery_temperature_K=T_aw)
    assert sonuc['wall_temperatures_K'] == (0.30 * BORU_T0, 0.60 * BORU_T0)
    for oran, kayit in sonuc['runs'].items():
        assert np.all(np.isfinite(kayit['h_g_W_m2K']))
        assert np.all(kayit['h_g_W_m2K'][:3] > 0.0), (
            f'oran {oran}: giriş bölgesinde h_g pozitif değil')

    # Kapsam beyanının BEKÇİSİ: debi karışması gerçekten var mı?
    oran_debi = debiler[0.30 * BORU_T0] / debiler[0.60 * BORU_T0]
    assert oran_debi > 1.2, (
        f'debi oranı {oran_debi:.3f} — kapsam beyanı "soğuk duvar debiyi '
        f'büyütür" artık geçerli değil; beyan güncellenmeli')

    giris = sonuc['h_g_relative_band'][:3]
    assert np.all(np.isfinite(giris))
    assert 0.0 < float(np.max(giris)) < 1.0, (
        f'giriş bölgesinde h_g bandı %{100 * float(np.max(giris)):.0f} — '
        f'ölçüm ya ölü ya da doğrusallaştırma bu vakada tamamen geçersiz')
