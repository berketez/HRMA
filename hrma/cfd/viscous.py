# hrma/cfd — laminer viskoz kalıntı + duvar sınır koşulları (V1, basamak 4-5)
"""
Viskoz kalıntı R_viskoz(U): eksenel simetrik Newton akışkanı için ayrık
viskoz akı ıraksaması + çember (hoop) kaynağı + duvar τ_w / q_w çıktıları.

KOMPOZİSYON (tasarım belgesi cfd-viskoz-tasarimi.md §5.1 — BAĞLAYICI)
---------------------------------------------------------------------
Bu modül Euler çekirdeğinin İÇİNE yazılmaz; ayrı bir kalıntıdır:

    dU/dt = R_Euler(U) + R_viskoz(U)          (akı ıraksaması doğrusaldır)

``residual_axisym`` çağrısı viskoz katman kapalıyken BİREBİR bugünkü koddur;
Euler yolunun bit-özdeşliği yapısal olarak korunur (bekçi:
tests/cfd/test_euler_bit_ozdesligi.py). Bu dosya V0 teslimatlarını İTHAL
eder, kopyalamaz:
  * ``gas_transport``  — μ(T), cp, Pr, k_eff (depo bağıntısına sarmalayıcı),
  * ``gradients``      — düzlemsel Green-Gauss + düzeltmeli yüz gradyanı,
  * ``viscous_tensor`` — Stokes hipotezli gerilme cebiri + hoop kaynağı.

AYRIK BİÇİM (dönel hacim üstünde integral form, 2π çarpanları geometride)
------------------------------------------------------------------------
z-momentum ve r-momentum için viskoz kuvvet, ızgaranın DÖNEL yüzey
vektörleriyle (``grid.face_i``/``face_j``; 2π·r_orta içerirler) doğrudan
yazılır:

    F_z|yüz = τ_zz·S_z + τ_zr·S_r
    F_r|yüz = τ_zr·S_z + τ_rr·S_r
    F_E|yüz = (τ_zz u_z + τ_zr u_r)·S_z + (τ_zr u_z + τ_rr u_r)·S_r
              + k_eff·(∂T/∂z·S_z + ∂T/∂r·S_r)          [−q·S = +k∇T·S]

    R_viskoz = ( Σ_dışa F|yüz  +  [0, 0, −τ_θθ·2π·A_düzlem, 0] ) / V

Çember kaynağının türetimi ve euler_core'un basınç kaynağıyla kardeşliği
``viscous_tensor.hoop_momentum_source`` docstring'indedir. Kütle
bileşenine viskoz akı GİRMEZ (madde difüzyonu yok): ``R_viskoz[..., 0]``
her yerde TAM sıfırdır (bekçili).

EKSEN (r = 0): j = 0 yüzlerinin DÖNEL alanı geometrik olarak sıfırdır
(grid_axisym gerçeği). O yüzde viskoz akı hesaplanmaz, TAM sıfır konur —
böylece Θ içindeki u_r/r ifadesi r = 0'da hiç değerlendirilmez ve 0·∞
tuzağı doğmaz. i-yüzlerinin orta noktası her zaman r > 0'dadır (yüz
[r_j, r_{j+1}] aralığını kapsar, r_{j+1} > 0), hücre merkezleri de öyle;
epsilon, kırpma, seri açılım YOKTUR.

DUVAR SINIR KOŞULLARI (§5.4)
----------------------------
Hız: no-slip. Ayrık karşılığı iki yerdedir ve İKİSİ de gereklidir:
  (a) viskoz gradyanların duvar YÜZ değeri u_z = u_r = 0 (bu modül),
  (b) Euler MUSCL hayaletinin tam yansıması (``euler_core`` ``wall_bc=
      'noslip'``) — kayma aynası duvara komşu hücrede taşınım yeniden
      kurulumunu bozar. Ayna seçiminin q_w/c_f üstündeki etkisi
      VARSAYILMAZ, ölçülür (tests/cfd/test_boru_laminer.py).
Duvarda u = 0 olduğu için viskoz iş terimi (τ·u)·S TAM sıfırdır; duvar
yüzünün enerji akısı yalnız −q_w·|S|'dir (bekçili).

Isıl: UYDURMA VARSAYILAN YOKTUR.
  * ``wall_thermal='isothermal'`` → ``T_wall`` ZORUNLU ve ``T_wall_source``
    ZORUNLU (kaynağı beyanlı taşınır: termal FEA / regen çözücü /
    kullanıcı / doğrulama vakası). T_wall'suz izotermal ``ValueError``.
  * ``wall_thermal='adiabatic'`` → ∂T/∂n = 0; duvar ısı akısı TAM SIFIR
    konur (kırpma değil, sınır koşulunun kendisi), duvar yüz sıcaklığı
    teğetsel dışdeğerlemeyle kurulur (dik duvarda düzeltme tam sıfırdır —
    ölçülür, varsayılmaz).

DÜRÜSTLÜK: pozitiflik tabanı / kırpma YOKTUR. Fiziksel olmayan durum
(ρ ≤ 0, p ≤ 0, sonsuz) girerse kalıntı NaN döner — euler_core'un
sözleşmesiyle aynı: sürücü bunu ıraksama olarak raporlar (converged=False),
istisna atılmaz.

TÜRBÜLANS (V2'de KANCA AÇILDI): ``mu_t=None`` verilirse akı LAMİNERDİR ve
bu dosyanın V1 davranışı BİT-ÖZDEŞ korunur (laminer dal tek bir aritmetik
işlem bile kazanmadı — bekçisi tests/cfd/test_viskoz_entegrasyon.py).
``mu_t`` verilirse bu modül türbülans MODELİ ÇÖZMEZ; yalnız Boussinesq
kapanışını TAŞIR:

    μ_eff = μ(T) + μ_t,    k_eff = cp(μ/Pr + μ_t/Pr_t)

μ_t'yi ÜRETEN model ayrıdır (``sa_neg.py``; sürücü bağlaması ``steady.py``)
ve Pr_t ``gas_transport``ın TEK sabitidir — bu dosyada yeni sabit yoktur.
"""

from dataclasses import dataclass, replace

import numpy as np

from hrma.cfd.euler_core import cons_to_prim_axisym, precompute_geometry
from hrma.cfd.gas_transport import effective_conductivity
from hrma.cfd.gradients import (
    BoundaryFaceValues,
    face_gradients,
    green_gauss_gradient,
    interpolate_to_faces,
    precompute_gradient_geometry,
)
from hrma.cfd.viscous_tensor import hoop_momentum_source, stress_from_gradients

__all__ = [
    'GAS_CONSISTENCY_TOL',
    'NONPHYSICAL_FACE_REASON',
    'TURBULENCE_CLOSED_BY_MU_T',
    'VISCOUS_NOT_MODELLED',
    'WALL_TEMP_SENSITIVITY_RATIOS',
    'WALL_THERMAL_MODES',
    'WallOutputs',
    'h_g_wall_temp_sensitivity',
    'nonphysical_state',
    'viscous_local_dt_limit',
    'viscous_residual',
    'viscous_spectral_radius',
]

_TWO_PI = 2.0 * np.pi

#: Isıl duvar kipleri — üçüncüsü yok, varsayılan yok (§5.4).
WALL_THERMAL_MODES = ('isothermal', 'adiabatic')

#: cp = γR/(γ−1) özdeşliğinin bağıl uyum toleransı. İki gaz modeliyle
#: (biri Euler'in R'si, biri taşınımın cp'si) koşmak sessiz bir fizik
#: hatasıdır; özdeşlik bu tolerans dışına çıkarsa çağrı REDDEDİLİR.
#: Depo zincirinde cp doğrudan bu özdeşlikten üretildiği için fark
#: yuvarlama sınıfındadır (ÖLÇÜLDÜ: 0,0).
GAS_CONSISTENCY_TOL = 1.0e-9

#: h_g duyarlılık koşusunun iki duvar sıcaklığı oranı (§5.4'ün kendi
#: sayıları: "İki koşu (T_w = 0,3·T₀ ve 0,6·T₀) ile h_g bandı ÖLÇÜLÜR").
WALL_TEMP_SENSITIVITY_RATIOS = (0.30, 0.60)

#: Bu evrede modellenmeyenler (paket beyanına eklenir; §10'un V1 alt kümesi).
VISCOUS_NOT_MODELLED = {
    'turbulence': (
        'Türbülans YOK: bu koşu LAMİNER viskoz akıdır (μ_eff = μ). '
        'Spalart-Allmaras (SA-neg) kapanışı mu_t kancasıyla bağlanır '
        '(hrma.cfd.sa_neg + steady.ViscousOptions(turbulence="sa_neg")); '
        'bağlanmadığı koşuda türbülans modellenmemiştir.'),
    'wall_roughness': (
        'Duvar pürüzlülüğü modellenmedi (hidrolik pürüzsüz duvar).'),
    'conjugate_heat_transfer': (
        'Cidar iletimi çözülmez: T_w bir SINIR KOŞULUDUR ve kaynağı '
        'beyanla taşınır (isothermal kipinde T_wall_source zorunlu).'),
}

# ∂φ/∂n = 0 sınırlarının (eksen simetrisi, adyabatik duvar) yüz değeri
# gradyanın KENDİSİNE bağlıdır (teğetsel dışdeğerleme) → sabit nokta.
# DİK sınırda (merkez→yüz vektörü normale paralel) düzeltme yuvarlama
# sınıfına iner ve döngü ilk turda kırılır; ölçüt alanın temsil gürültüsü
# eps·max|φ|'dir (uydurma eşik değil: bundan küçük bir güncelleme alanın
# kendi float temsilinde görünmez).
_NEUMANN_MAX_PASSES = 2


#: eq=False bilinçli: alanlar NumPy dizisidir, üretilmiş __eq__ iki nesneyi
#: karşılaştırırken "ambiguous truth value" atardı. Eşitlik istenirse alan
#: alan np.array_equal ile ölçülür (bekçilerin yaptığı budur).
@dataclass(frozen=True, eq=False)
class WallOutputs:
    """Duvar istasyonu dizileri — V4 köprülerinin (FEA, itki, ayrılma) girdisi.

    Bütün diziler (ni,) uzunluğunda, duvar YÜZLERİ (j = nj) üstünde:
        z_m, r_m            : yüz orta noktası koordinatları [m]
        area_m2             : dönel yüz alanı |S| [m²] (2π dâhil)
        tau_wall_Pa         : akış-teğeti yönünde İŞARETLİ duvar kayma
                              gerilmesi (akışkanın DUVARA uyguladığı);
                              pozitif = akış yönü, NEGATİF = geri akış →
                              ayrılma ölçütü τ_w = 0 istasyonu (§8.3)
        traction_z_Pa       : akışkana etkiyen viskoz gerilme vektörü
        traction_r_Pa         (τ·n̂) bileşenleri — kalıntıya giren büyüklük
        q_wall_W_m2         : duvara giren ısı akısı q_w = −k_eff ∂T/∂n
                              (pozitif = akışkandan duvara); adyabatik
                              kipte TAM sıfır
        T_wall_K            : duvar yüz sıcaklığı (izotermal: verilen T_w,
                              adyabatik: ÖLÇÜLEN yüz sıcaklığı)
        T_cell_K            : duvara komşu hücre sıcaklığı (beyan için)
        mu_wall_Pa_s        : duvar yüzünde μ(T_wall)
        k_wall_W_mK         : duvar yüzünde k_eff
    """

    z_m: np.ndarray
    r_m: np.ndarray
    area_m2: np.ndarray
    tau_wall_Pa: np.ndarray
    traction_z_Pa: np.ndarray
    traction_r_Pa: np.ndarray
    q_wall_W_m2: np.ndarray
    T_wall_K: np.ndarray
    T_cell_K: np.ndarray
    mu_wall_Pa_s: np.ndarray
    k_wall_W_mK: np.ndarray
    thermal_mode: str
    T_wall_source: str

    def heat_rate_W(self):
        """∮ q_w dA — duvara giren toplam ısı [W] (pozitif = akışkandan)."""
        return float(np.sum(self.q_wall_W_m2 * self.area_m2))

    def axial_friction_force_on_fluid_N(self):
        """∮ (τ·n̂)_z dA — akışkana etkiyen eksenel viskoz kuvvet [N].

        Sürüklenme olduğunda NEGATİFTİR. İtki kaybı köprüsü (§8.2) işaret
        sözleşmesini burada değil KENDİ katmanında seçer; bu değer ham
        ölçümdür.
        """
        return float(np.sum(self.traction_z_Pa * self.area_m2))


# ---------------------------------------------------------------------------
# Girdi doğrulama (adlı; sessiz varsayım yok)
# ---------------------------------------------------------------------------

def _check_wall_thermal(wall_thermal, T_wall, T_wall_source, ni):
    """Isıl duvar kipini ve zorunlu eşlikçilerini doğrular (§5.4)."""
    if wall_thermal not in WALL_THERMAL_MODES:
        raise ValueError(
            f'wall_thermal {wall_thermal!r} tanımsız — geçerli kipler '
            f'{WALL_THERMAL_MODES}. VARSAYILAN YOKTUR: ısıl duvar koşulu '
            'çağıranın açık kararıdır ve koşum beyanında görünür.')

    if wall_thermal == 'adiabatic':
        if T_wall is not None:
            raise ValueError(
                'wall_thermal="adiabatic" ile T_wall verilemez: adyabatik '
                'duvarda sıcaklık bir SONUÇTUR (ÖLÇÜLÜR), sınır koşulu '
                'değildir. İzotermal duvar istiyorsanız '
                'wall_thermal="isothermal" seçin.')
        return None, 'adiabatic_wall_measured'

    if T_wall is None:
        raise ValueError(
            'wall_thermal="isothermal" için T_wall ZORUNLUDUR. Duvar '
            'sıcaklığı uydurulmaz (varsayılan yok): termal FEA, regen '
            'çözücü ya da kullanıcı verir ve kaynağı T_wall_source ile '
            'beyan edilir.')
    if not isinstance(T_wall_source, str) or not T_wall_source.strip():
        raise ValueError(
            'T_wall verildi ama T_wall_source beyan edilmedi. Kaynağı '
            'olmayan sınır koşulu yayımlanmaz (FEA köprüsü deseni): '
            'ör. "thermal_fea", "regen_solver", "user", '
            '"verification_case".')

    array = np.asarray(T_wall, dtype=float)
    if array.ndim == 0:
        array = np.full(ni, float(array))
    if array.shape != (ni,):
        raise ValueError(
            f'T_wall skaler ya da ({ni},) duvar istasyonu dizisi olmalı — '
            f'gelen biçim {array.shape}.')
    if not np.all(np.isfinite(array)) or np.any(array <= 0.0):
        raise ValueError('T_wall her istasyonda pozitif ve sonlu olmalı '
                         '(NaN/inf/sıfır/negatif sessizce geçmez).')
    return array, T_wall_source.strip()


def _check_gas_consistency(transport, R):
    """cp = γR/(γ−1) özdeşliği — iki gaz modeliyle koşmayı engeller."""
    R = float(R)
    if not np.isfinite(R) or R <= 0.0:
        raise ValueError(f'R pozitif ve sonlu olmalı — verilen: {R!r}.')
    gamma = float(transport.gamma)
    # γ KAPISI (ÖH defter P6B2-08): γ = 1,0 taşıyan bir GasTransport ile
    # cp = γR/(γ−1) SIFIRA BÖLÜM üretiyordu ve dışarıya ADSIZ bir
    # ZeroDivisionError sızıyordu (ölçüldü, D23 once.json K10) — oysa bu
    # modülün sözleşmesi "kusurlu girdi ValueError ile ADIYLA reddedilir".
    # γ = 1 izotermal sınır hâlidir: kalorik mükemmel gazda cp tanımsızdır.
    if not np.isfinite(gamma) or gamma <= 1.0:
        raise ValueError(
            f'γ > 1 olmalı — verilen: {transport.gamma!r}. Kalorik mükemmel '
            'gazda cp = γR/(γ−1) ancak γ > 1 için tanımlıdır; γ = 1 '
            'izotermal sınır hâlidir (cp → ∞) ve γ ≤ 1 fiziksel değildir. '
            'Bu bir GİRDİ kusurudur, sessizce kelepçelenmez.')
    cp_beklenen = gamma * R / (gamma - 1.0)
    fark = abs(transport.cp - cp_beklenen) / cp_beklenen
    if fark > GAS_CONSISTENCY_TOL:
        raise ValueError(
            f'Gaz modeli tutarsız: taşınım cp = {transport.cp!r} J/(kg·K) '
            f'ama çözücünün γ = {gamma!r} ve R = {R!r} değerleri '
            f'cp = γR/(γ−1) = {cp_beklenen!r} istiyor (bağıl fark '
            f'{fark:.3e} > {GAS_CONSISTENCY_TOL:g}). İki ayrı gaz modeliyle '
            'koşmak viskoz sıcaklık alanını Euler alanından sessizce '
            'ayırırdı; ya transport ya R düzeltilmeli.')
    return R, gamma


def nonphysical_state(w):
    """Fiziksel olmayan ortalama akış durumu mu? — TEK TANIM.

    Ölçüt: ρ > 0, p > 0 ve bütün primitifler sonlu. Bu fonksiyon viskoz
    katmanın SÖZLEŞME NOKTASIDIR; ölçütü kullanan her yol (kalıntı,
    spektral yarıçap, SA kalıntısı) AYNI durumda AYNI davranmak
    zorundadır: NaN döndürülür, istisna ATILMAZ (euler_core geleneği —
    sürücü ıraksamayı ``converged=False`` olarak raporlar, çökmez).

    SÖZLEŞME BİRLEŞİMİ (defter satırının kapanışı, parti 38): daha önce
    ``viscous_residual`` NaN döndürürken ``viscous_spectral_radius`` AYNI
    durumda ``gas_transport``ın pozitiflik kapısından ``ValueError``
    sızdırıyordu (parti 37'de A2 ölçtü, canlıda sürücüyü ilk turda
    çökertmişti). Ölçüt artık tek yerde tanımlıdır ve iki yol da buradan
    geçer; ayrışma ancak bu fonksiyon iki kez yazılırsa doğabilir —
    bekçisi ikisini AYNI durumla birlikte ölçer.

    Args:
        w: (..., 4) primitif dizi [ρ, u_z, u_r, p].

    Returns:
        ``True`` → durum fiziksel değil (NaN yolu).
    """
    w = np.asarray(w, dtype=float)
    return not (np.all(np.isfinite(w)) and np.all(w[..., 0] > 0.0)
                and np.all(w[..., 3] > 0.0))


#: μ_t verildiğinde 'turbulence' anahtarının yerine geçen metin (TEK
#: kaynak; steady.py'nin beyan bloğu da buradan okur — iki ayrı metin
#: sessizce ayrışırdı).
TURBULENCE_CLOSED_BY_MU_T = (
    'Türbülans DIŞARIDAN kapatıldı: μ_t çağıranın modelinden geldi. Bu '
    'modül kapanışı ÇÖZMEZ, yalnız TAŞIR — μ_eff = μ(T) + μ_t ve '
    'k_eff = cp(μ/Pr + μ_t/Pr_t) (Pr_t gas_transport.PRANDTL_TURBULENT). '
    'Boussinesq (doğrusal girdap viskozitesi) varsayımının kendisi '
    'MODELLENMEYENLER arasındadır: normal gerilme anizotropisi, eğrilik/'
    'dönme düzeltmesi ve gerilme-gecikmesi bu kapanışta yoktur.')


def _check_mu_t(mu_t, ni, nj):
    """Türbülanslı viskozite alanının kapısı (V2'de AÇIK, sözleşmeli).

    μ_t bir MODEL çıktısıdır; bu modül onu üretmez, taşır. Kapı üç şey
    ister ve üçü de sessiz kabul edilmez: doğru biçim, sonluluk ve
    NEGATİF OLMAMA. Negatif girdap viskozitesi ters difüzyondur (ayrık
    operatörü kararsızlaştırır) ve SA-neg'in kendi kuralı ν̃ < 0 bölgesinde
    μ_t = 0 vermektir (``sa_neg.turbulent_viscosity``) — yani negatif değer
    ancak çağıranın kusuruyla gelebilir. Kırpma YOK: reddedilir.
    """
    array = np.asarray(mu_t, dtype=float)
    if array.shape != (ni, nj):
        raise ValueError(
            f'mu_t biçimi ({ni}, {nj}) olmalı — gelen {array.shape}. '
            '(Türbülanslı viskozite hücre alanıdır; yüz değerleri bu '
            'modülde kurulur.)')
    if not np.all(np.isfinite(array)):
        raise ValueError('mu_t sonlu olmalı (NaN/inf sessizce geçmez).')
    if np.any(array < 0.0):
        raise ValueError(
            f'mu_t negatif değer içeriyor (min {float(np.min(array)):.6g} '
            'Pa·s). Negatif girdap viskozitesi ters difüzyondur; SA-neg '
            'ν̃ < 0 dalında μ_t = 0 verir, yani negatif değer çağıranın '
            'kusurudur. Sessizce kırpılmaz.')
    return array


def _face_eddy_viscosity(mu_t, ni, nj):
    """μ_t'nin YÜZ değerleri: komşu hücrelerin aritmetik ortalaması.

    NEDEN ORTALAMA (gradyanlı yeniden kurulum DEĞİL) — beyanlı seçim:
    ``interpolate_to_faces`` çarpıklık düzeltmeli yeniden kurulum yapar ve
    μ_t duvara komşu hücrede birkaç mertebe düştüğü için o kurulum yüz
    değerini NEGATİFE düşürebilir; negatif girdap viskozitesi fiziksel
    değildir ve sessiz kırpma bu depoda yasaktır. Aritmetik ortalama
    pozitifliği YAPISAL olarak korur (girdiler ≥ 0), düzgün alanda ikinci
    mertebedir ve ``relax_implicit``in yüz μ kuralıyla aynıdır.

    Sınırlar: duvar yüzünde μ_t = 0 (SA'nın ν̃_w = 0 Dirichlet'i — kırpma
    değil, sınır koşulunun kendisi), eksen yüzünde dönel alan sıfır
    olduğundan değer akıya GİRMEZ (komşu hücre değeri konur), giriş/çıkış
    yüzlerinde komşu hücre değeri (sıfırıncı mertebe uzatma; μ_t alanı
    eksenel yönde yavaş değişir).
    """
    face_i = np.empty((ni + 1, nj), dtype=float)
    face_i[1:-1] = 0.5 * (mu_t[:-1] + mu_t[1:])
    face_i[0] = mu_t[0]
    face_i[-1] = mu_t[-1]
    face_j = np.empty((ni, nj + 1), dtype=float)
    face_j[:, 1:-1] = 0.5 * (mu_t[:, :-1] + mu_t[:, 1:])
    face_j[:, 0] = mu_t[:, 0]
    face_j[:, -1] = 0.0
    return face_i, face_j


def _face_primitives(name, value, nj):
    """Sınır yüzü primitifleri (nj, 4) = [ρ, u_z, u_r, p] ya da None.

    GİRDİ KAPISI (ÖH defter P6B2-07): biçim denetleniyordu ama SONLULUK
    ve POZİTİFLİK denetlenmiyordu — ölçüldü (D23 once.json K9), NaN
    taşıyan bir sınır yüzü sessizce geçip kalıntıyı kirletiyordu ve
    ``nonphysical_state`` yalnız HÜCRE durumuna baktığı için yakalamıyordu.
    Sınır verisi ÇAĞIRANIN girdisidir; kusurlu girdi ADIYLA reddedilir
    (modülün sözleşmesi), sessiz yedek/kırpma yoktur.
    """
    if value is None:
        return None
    array = np.asarray(value, dtype=float)
    if array.shape != (nj, 4):
        raise ValueError(
            f'{name} biçimi ({nj}, 4) olmalı [ρ, u_z, u_r, p] — gelen '
            f'{array.shape}.')
    if not np.all(np.isfinite(array)):
        kirli = int(np.count_nonzero(~np.isfinite(array)))
        raise ValueError(
            f'{name} sonlu olmalı — {kirli} girdide NaN/inf var. Sınır '
            'yüzü primitifleri ÇAĞIRANIN verisidir; sonlu olmayan sınır '
            'değeri kalıntıyı sessizce kirletirdi (nonphysical_state '
            'yalnız HÜCRE durumuna bakar, sınır yüzüne bakmaz).')
    if not np.all(array[:, 0] > 0.0) or not np.all(array[:, 3] > 0.0):
        raise ValueError(
            f'{name} her yüzde ρ > 0 ve p > 0 taşımalı — gelen en küçük '
            f'ρ = {float(array[:, 0].min()):.6g} kg/m³, en küçük '
            f'p = {float(array[:, 3].min()):.6g} Pa. Sıfır/negatif sınır '
            'yoğunluğu ya da basıncı kırpılmaz, ADIYLA reddedilir.')
    return array


# ---------------------------------------------------------------------------
# Viskoz kalıntı
# ---------------------------------------------------------------------------

def viscous_residual(grid, U, transport, *, R, wall_thermal, T_wall=None,
                     T_wall_source=None, mu_t=None, geom=None, grad_geom=None,
                     inlet_face_primitives=None, outlet_face_primitives=None,
                     skew_iters=None, corrected=True):
    """Laminer viskoz kalıntı R_viskoz ve duvar çıktıları.

    Args:
        grid: ``AxisymGrid``.
        U: (ni, nj, 4) korunum durumu [ρ, ρu_z, ρu_r, E].
        transport: ``gas_transport.GasTransport`` — γ, cp, Pr ve μ(T) yasası
            TEK kaynaktan gelir; bu modül yeni bağıntı tanımlamaz.
        R: Özgül gaz sabiti [J/(kg·K)] — çözücünün (euler_core) kullandığı
            değer. cp = γR/(γ−1) özdeşliğine karşı ÇAPRAZLANIR.
        wall_thermal: ``'isothermal'`` | ``'adiabatic'`` (varsayılan YOK).
        T_wall: İzotermal duvar sıcaklığı [K] — skaler ya da (ni,) istasyon
            dizisi. İzotermal kipte ZORUNLU, adyabatik kipte YASAK.
        T_wall_source: T_wall'ın kaynağının beyanı (izotermal kipte zorunlu).
        mu_t: (ni, nj) türbülanslı (girdap) viskozite [Pa·s] ya da None.
            None → LAMİNER akı (V1 yolu, bit-özdeş). Verilirse μ_eff =
            μ(T) + μ_t ve k_eff = cp(μ/Pr + μ_t/Pr_t); alanı ÜRETEN model
            bu modülde DEĞİLDİR (``sa_neg.turbulent_viscosity``). Negatif
            ya da sonlu olmayan değer REDDEDİLİR (kırpma yok).
        geom: ``euler_core.precompute_geometry`` çıktısı (birim normaller,
            alanlar) — sürücü bir kez hesaplayıp geçirir.
        grad_geom: ``gradients.precompute_gradient_geometry`` çıktısı.
        inlet_face_primitives: (nj, 4) giriş yüzü primitifleri ya da None
            (None → bir-yanlı doğrusal uzatma; sabit nokta süpürmesi
            yavaşlar, gradients.py'nin ölçtüğü kip).
        outlet_face_primitives: (nj, 4) çıkış yüzü primitifleri ya da None.
        skew_iters: Çarpıklık süpürme sayısı (None → yakınsayana dek).
        corrected: Yüz gradyanı düzeltmesi (Blazek §5.3.2). ``False``
            YALNIZ karşılaştırma/bekçi içindir — düzeltmesiz biçim duvar
            gradyanını hücre gradyanına indirger ve τ_w/q_w'yi bozar
            (etkisi ölçülür: tests/cfd/test_boru_laminer.py).

    Returns:
        (dUdt, aux): dUdt (ni, nj, 4) [birim/s]; aux sözlüğü
        ``'wall'`` → ``WallOutputs``, bütçe skalerleri ve beyan taşır.

    Raises:
        ValueError: Isıl duvar sözleşmesi, gaz tutarlılığı, biçim ya da
            μ_t kapsamı bozulursa.
    """
    ni, nj = grid.ni, grid.nj
    U = np.asarray(U, dtype=float)
    if U.shape != (ni, nj, 4):
        raise ValueError(
            f'U biçimi ({ni}, {nj}, 4) olmalı — gelen {U.shape}.')
    mu_t_cell = None if mu_t is None else _check_mu_t(mu_t, ni, nj)

    R, gamma = _check_gas_consistency(transport, R)
    T_wall_arr, T_wall_source = _check_wall_thermal(
        wall_thermal, T_wall, T_wall_source, ni)
    if geom is None:
        geom = precompute_geometry(grid)
    if grad_geom is None:
        grad_geom = precompute_gradient_geometry(grid)

    w = cons_to_prim_axisym(U, gamma)
    rho, uz, ur, p = w[..., 0], w[..., 1], w[..., 2], w[..., 3]

    # Fiziksel olmayan durum: kırpma YOK, NaN döndürülür (euler_core
    # sözleşmesi). İstisna atmıyoruz çünkü sürücü ıraksamayı
    # converged=False olarak raporlamalı, çökmemeli. Ölçüt TEK yerde:
    # nonphysical_state (spektral yarıçap yolu da AYNI ölçütü kullanır).
    #
    # ÖH D24 / fix-22 — BU KAPI SINIR YÜZÜ KAPISININ ÖNÜNE ALINDI.
    # D23 (P6B2-07) sınır yüzü primitiflerine sonluluk/pozitiflik kapısı
    # koydu ve kapı bu satırların ÜSTÜNDEYDİ. Oysa sürücü (``steady.py::
    # _viskoz_kalinti``) o primitifleri ÇAĞIRANDAN almaz, O ANKİ ÇÖZÜMDEN
    # türetir (``_sinir_primitifleri`` -> euler_core'un kendi hayalet
    # durumu); ıraksayan bir koşuda sınır yüzü hücrelerle BİRLİKTE
    # fiziksel olmaktan çıkar. ÖLÇÜLDÜ (taban kaydı-7; boru vakası nj=24,
    # μ×16, C_visc=0,5): kapı ``outlet_face_primitives ... p = -498371 Pa``
    # diye ValueError atarken AYNI ANDA hücre durumu da fiziksel değildi
    # (``nonphysical_state(w) = True``, hücre p_min = -498371 Pa). Yani
    # istisna, modülün KENDİ NaN sözleşmesinin karşılayacağı bir durumda
    # sürücüye sızıyor ve 'DIVERGED' beyanı yerine çöküş üretiyordu —
    # ``test_iraksama_kapisi_kutle_kalintisi_SONLUYKEN_de_yakalar``
    # bekçisinin adıyla ölçtüğü sızıntı budur.
    #
    # Kapı GEVŞEMEDİ: P6B2-07'nin ölçtüğü vaka (hücreler SAĞLAM, çağıran
    # bozuk sınır verisi geçiriyor) aşağıda hâlâ ADIYLA reddedilir; yalnız
    # sıra düzeltildi. Sözleşme cümlesi: önce "bu koşu ıraksadı mı",
    # sonra "çağıranın sınır verisi geçerli mi".
    if nonphysical_state(w):
        return _nonphysical_result(
            grid, geom, grad_geom, wall_thermal, T_wall_source,
            transport=transport, corrected=corrected,
            boundary_mode_i=('dirichlet'
                             if (inlet_face_primitives is not None
                                 and outlet_face_primitives is not None)
                             else 'extrapolated'),
            turbulent=mu_t_cell is not None)

    # Çağıranın sınır yüzü verisi (P6B2-07 kapısı) — hücre durumu SAĞLAMKEN
    # değerlendirilir; kusurlu sınır verisi hâlâ ADIYLA reddedilir.
    w_in = _face_primitives('inlet_face_primitives', inlet_face_primitives, nj)
    w_out = _face_primitives('outlet_face_primitives', outlet_face_primitives,
                             nj)

    T = p / (rho * R)

    # ---- sınır yüz değerleri (gradyan operatörünün Dirichlet verisi) ----
    # EKSEN (j = 0) SİMETRİSİ: u_z ve T çift → ∂/∂n = 0 (Neumann); u_r tek
    # → yüz değeri TAM sıfır (Dirichlet). DUVAR (j = nj): no-slip → hız
    # Dirichlet sıfır; sıcaklık ısıl kipe göre.
    dx_t_eksen = _tangential_offset(grid, grad_geom, 'j_lo')
    sifir_duvar = np.zeros(ni)
    bc_uz = BoundaryFaceValues(
        i_lo=None if w_in is None else w_in[:, 1],
        i_hi=None if w_out is None else w_out[:, 1],
        j_lo=None, j_hi=sifir_duvar)
    bc_ur = BoundaryFaceValues(
        i_lo=None if w_in is None else w_in[:, 2],
        i_hi=None if w_out is None else w_out[:, 2],
        j_lo=np.zeros(ni), j_hi=sifir_duvar)
    T_in = None if w_in is None else w_in[:, 3] / (w_in[:, 0] * R)
    T_out = None if w_out is None else w_out[:, 3] / (w_out[:, 0] * R)
    bc_T = BoundaryFaceValues(i_lo=T_in, i_hi=T_out, j_lo=None,
                              j_hi=T_wall_arr)

    bc_uz, grad_uz, _ = _gradient_with_neumann(
        grid, uz, bc_uz, {'j_lo': dx_t_eksen}, grad_geom, skew_iters)
    grad_ur = green_gauss_gradient(grid, ur, bc=bc_ur, geom=grad_geom,
                                   skew_iters=skew_iters)
    neumann_T = {'j_lo': dx_t_eksen}
    if wall_thermal == 'adiabatic':
        neumann_T['j_hi'] = _tangential_offset(grid, grad_geom, 'j_hi')
    bc_T, grad_T, adyabatik_guncelleme = _gradient_with_neumann(
        grid, T, bc_T, neumann_T, grad_geom, skew_iters)
    T_wall_face = (np.array(T_wall_arr, dtype=float, copy=True)
                   if wall_thermal == 'isothermal'
                   else np.asarray(bc_T.j_hi, dtype=float))

    # ---- hücre gerilmesi (yalnız çember kaynağı için) ----
    # μ_eff hücre değeri: laminer dalda değer AYNEN korunur (bit-özdeşlik;
    # μ_t verilmemişse tek bir toplama bile yapılmaz).
    mu_cell = transport.viscosity(T)
    mu_cell_eff = mu_cell if mu_t_cell is None else mu_cell + mu_t_cell
    stress_cell = stress_from_gradients(grad_uz, grad_ur, ur, grid.r_centers,
                                        mu_cell_eff)
    hoop = hoop_momentum_source(stress_cell.tau_theta, grid)

    # ---- yüz değerleri ve yüz gradyanları ----
    uz_i, uz_j = interpolate_to_faces(grid, uz, grad_uz, bc=bc_uz,
                                      geom=grad_geom)
    ur_i, ur_j = interpolate_to_faces(grid, ur, grad_ur, bc=bc_ur,
                                      geom=grad_geom)
    T_i, T_j = interpolate_to_faces(grid, T, grad_T, bc=bc_T, geom=grad_geom)

    guz_i, guz_j = face_gradients(grid, uz, grad=grad_uz, bc=bc_uz,
                                  corrected=corrected, geom=grad_geom)
    gur_i, gur_j = face_gradients(grid, ur, grad=grad_ur, bc=bc_ur,
                                  corrected=corrected, geom=grad_geom)
    gT_i, gT_j = face_gradients(grid, T, grad=grad_T, bc=bc_T,
                                corrected=corrected, geom=grad_geom)

    r_i = 0.5 * (grid.R[:, :-1] + grid.R[:, 1:])          # (ni+1, nj) > 0
    r_j = 0.5 * (grid.R[:-1, :] + grid.R[1:, :])          # (ni, nj+1), j=0 → 0

    # YÜZ POZİTİFLİĞİ (V2'de ÖLÇÜLEREK eklendi — sözleşme boşluğu):
    # hücre durumları fiziksel olsa bile doğrusal yüz kurulumu T_yüz'ü
    # negatife düşürebilir (gerekçe ve ölçüm NONPHYSICAL_FACE_REASON'da).
    # Eskiden bu durum gas_transport'un pozitiflik kapısından ValueError
    # ile SIZIYORDU — sürücü sözleşmesi ("istisna sızmaz, 'diverged'
    # beyanı döner") delinmiş oluyordu; ölçüldü ve kapatıldı.
    if not (np.all(T_i > 0.0) and np.all(T_j > 0.0)):
        return _nonphysical_result(
            grid, geom, grad_geom, wall_thermal, T_wall_source,
            reason=NONPHYSICAL_FACE_REASON,
            transport=transport, corrected=corrected,
            boundary_mode_i=('dirichlet'
                             if (w_in is not None and w_out is not None)
                             else 'extrapolated'),
            turbulent=mu_t_cell is not None)
    mu_i = transport.viscosity(T_i)
    mu_j = transport.viscosity(T_j)
    if mu_t_cell is None:
        mu_eff_i, mu_eff_j = mu_i, mu_j
        k_i = effective_conductivity(transport.cp, mu_i, transport.prandtl)
        k_j = effective_conductivity(transport.cp, mu_j, transport.prandtl)
    else:
        mu_t_i, mu_t_j = _face_eddy_viscosity(mu_t_cell, ni, nj)
        mu_eff_i = mu_i + mu_t_i
        mu_eff_j = mu_j + mu_t_j
        # k_eff'in İKİ Prandtl'lı biçimi gas_transport'un TEK tanımıdır
        # (Pr_t orada künyeli sabittir; burada ikinci kez yazılmaz).
        k_i = effective_conductivity(transport.cp, mu_i, transport.prandtl,
                                     mu_t_i, transport.prandtl_turbulent)
        k_j = effective_conductivity(transport.cp, mu_j, transport.prandtl,
                                     mu_t_j, transport.prandtl_turbulent)

    flux_i = _face_viscous_flux(
        stress_from_gradients(guz_i, gur_i, ur_i, r_i, mu_eff_i),
        uz_i, ur_i, gT_i, k_i, grid.face_i)

    # Eksen yüzü (j = 0): dönel alan geometrik olarak sıfır → akı TAM sıfır;
    # u_r/r orada HİÇ değerlendirilmez (0·∞ tuzağı yok).
    flux_j = np.zeros((ni, nj + 1, 4), dtype=float)
    flux_j[:, 1:] = _face_viscous_flux(
        stress_from_gradients(guz_j[:, 1:], gur_j[:, 1:], ur_j[:, 1:],
                              r_j[:, 1:], mu_eff_j[:, 1:]),
        uz_j[:, 1:], ur_j[:, 1:], gT_j[:, 1:], k_j[:, 1:], grid.face_j[:, 1:])

    # ---- duvar: ısıl kip (adyabatikte q_w SINIR KOŞULU olarak tam sıfır) ----
    area_w = geom['area_j'][:, -1]
    n_hat_w = geom['wall_n_hat']
    isi_akisi_w = k_j[:, -1] * (gT_j[:, -1, 0] * grid.face_j[:, -1, 0]
                                + gT_j[:, -1, 1] * grid.face_j[:, -1, 1])
    if wall_thermal == 'adiabatic':
        # ∂T/∂n = 0 → q_w ≡ 0. Kırpma değil, sınır koşulunun KENDİSİ
        # (euler_core'un analitik kayma duvarı akısıyla aynı desen).
        flux_j[:, -1, 3] -= isi_akisi_w
        q_wall = np.zeros(ni)
    else:
        q_wall = -isi_akisi_w / area_w

    net = ((flux_i[1:] - flux_i[:-1]) + (flux_j[:, 1:] - flux_j[:, :-1]))
    net[..., 2] += hoop
    dudt = net / grid.volume[..., None]

    traction_z = flux_j[:, -1, 1] / area_w
    traction_r = flux_j[:, -1, 2] / area_w
    # Akış teğeti t̂ = (n_r, −n_z): dik ızgarada +z yönü. Yayımlanan τ_w
    # akışkanın DUVARA uyguladığı gerilmedir (çekiş vektörünün tersi), yani
    # bağlı akışta POZİTİF ve ayrılmada işaret değiştirir.
    tau_wall = -(traction_z * n_hat_w[..., 1]
                 - traction_r * n_hat_w[..., 0])
    mid_j = grad_geom['mid_j']

    wall = WallOutputs(
        z_m=mid_j[:, -1, 0], r_m=mid_j[:, -1, 1], area_m2=area_w,
        tau_wall_Pa=tau_wall, traction_z_Pa=traction_z,
        traction_r_Pa=traction_r, q_wall_W_m2=q_wall,
        T_wall_K=T_wall_face, T_cell_K=T[:, -1],
        mu_wall_Pa_s=mu_j[:, -1], k_wall_W_mK=k_j[:, -1],
        thermal_mode=wall_thermal, T_wall_source=T_wall_source)

    not_modelled = dict(VISCOUS_NOT_MODELLED)
    if mu_t_cell is None:
        turbulence_beyani = 'none (laminar V1)'
        mu_t_orani = None
    else:
        not_modelled['turbulence'] = TURBULENCE_CLOSED_BY_MU_T
        mu_t_orani = float(np.max(mu_t_cell / mu_cell))
        turbulence_beyani = (
            'mu_t supplied by caller (Boussinesq closure carried, not '
            f'solved): max(mu_t/mu) = {mu_t_orani:.4g}, face values are '
            'the arithmetic mean of the adjacent cells with mu_t = 0 '
            'imposed on the wall face')

    aux = {
        'wall': wall,
        # HIZ GRADYANLARI YAYIMLANIR (V2 bağlaması): SA'nın girdaplılığı
        # Ω viskoz kalıntının KULLANDIĞI gradyanlardan gelmelidir — yoksa
        # sürücü ikinci bir Green-Gauss çağrısı yazar ve aynı kavramın
        # ikinci tanımı doğar (sa_neg.py'nin sözleşme maddesi). Diziler
        # buradaki hesabın TA KENDİSİDİR (kopya değil).
        'velocity_gradients': {'u_z': grad_uz, 'u_r': grad_ur},
        'wall_heat_W': wall.heat_rate_W(),
        'axial_friction_force_on_fluid_N':
            wall.axial_friction_force_on_fluid_N(),
        'max_abs_mass_residual': float(np.max(np.abs(dudt[..., 0]))),
        # Ayrık bütçe beyanı (basamak 14'ün viskoz yarısı): hücre
        # toplamları teleskoplayınca yalnız SINIR akıları kalır.
        # İşaret: bunlar akının KENDİSİDİR (+i yönünde); alan kazancı
        # çıkış eksi giriş biçiminde kurulur.
        'inlet_energy_flux_W': float(np.sum(flux_i[0, :, 3])),
        'outlet_energy_flux_W': float(np.sum(flux_i[-1, :, 3])),
        'inlet_axial_force_N': float(np.sum(flux_i[0, :, 1])),
        'outlet_axial_force_N': float(np.sum(flux_i[-1, :, 1])),
        'declaration': {
            '_source': 'hrma.cfd.viscous.viscous_residual',
            'formulation': ('axisymmetric Newtonian, Stokes hypothesis '
                            '(lambda = -2/3 mu); planar Green-Gauss '
                            'gradients with corrected face values'),
            'wall_thermal': wall_thermal,
            'T_wall_source': T_wall_source,
            'face_gradient_corrected': bool(corrected),
            'boundary_mode_i': ('dirichlet' if w_in is not None
                                and w_out is not None else 'extrapolated'),
            'neumann_face_update_K': adyabatik_guncelleme,
            'turbulent_viscosity': turbulence_beyani,
            'mu_t_over_mu_max': mu_t_orani,
            'transport': transport.declaration(),
            'not_modelled': not_modelled,
        },
    }
    return dudt, aux


def _face_viscous_flux(stress, uz_f, ur_f, gradT_f, k_f, S):
    """Yüz viskoz akısı [0, F_z, F_r, F_E] — dönel yüzey vektörüyle."""
    sz = S[..., 0]
    sr = S[..., 1]
    fz = stress.tau_zz * sz + stress.tau_zr * sr
    fr = stress.tau_zr * sz + stress.tau_rr * sr
    # Viskoz iş + (−q·S) = +k∇T·S. Duvarda u = 0 olduğundan iş terimi
    # ORADA tam sıfırdır (yüz hız değerleri Dirichlet 0 ile kurulur).
    fe = (fz * uz_f + fr * ur_f
          + k_f * (gradT_f[..., 0] * sz + gradT_f[..., 1] * sr))
    return np.stack([np.zeros_like(fz), fz, fr, fe], axis=-1)


def _tangential_offset(grid, grad_geom, which):
    """(merkez → yüz) vektörünün TEĞETSEL bileşeni [m], (ni, 2).

    Normal, yüzün DÜZLEMSEL vektöründen alınır (dönel vektör eksende
    sıfırdır — orada yön bilgisi taşımaz; düzlemsel vektör her zaman
    dejenere değildir: eksen yüzü için (0, Δz)).
    """
    if which == 'j_lo':
        b, s = grad_geom['b_j_lo'], grid.face_j_planar[:, 0]
    else:
        b, s = grad_geom['b_j_hi'], grid.face_j_planar[:, -1]
    n_hat = s / np.linalg.norm(s, axis=-1)[:, None]
    bn = b[:, 0] * n_hat[:, 0] + b[:, 1] * n_hat[:, 1]
    return b - bn[:, None] * n_hat


def _gradient_with_neumann(grid, phi, bc, neumann, grad_geom, skew_iters):
    """∂φ/∂n = 0 sınırlarıyla Green-Gauss gradyanı (sabit nokta).

    Neumann yüz değeri TEĞETSEL dışdeğerlemedir:
    φ_yüz = φ_c + ∇φ_c·(b − (b·n̂)n̂). Gradyana bağlı olduğundan sabit nokta
    süpürülür; DİK sınırda teğetsel bileşen yuvarlama sınıfına iner ve
    döngü ilk turda kırılır (ölçüt eps·max|φ| — alanın kendi temsil
    gürültüsü, uydurma eşik değil).

    Args:
        neumann: {'j_lo' | 'j_hi': teğetsel öteleme (ni, 2)}.

    Returns:
        (bc, grad, son_guncelleme) — bc, kullanılan YÜZ değerlerini taşır
        (interpolate_to_faces / face_gradients aynısını kullanmalıdır).
    """
    if not neumann:
        return bc, green_gauss_gradient(grid, phi, bc=bc, geom=grad_geom,
                                        skew_iters=skew_iters), 0.0

    satir = {'j_lo': 0, 'j_hi': -1}
    yuz = {ad: np.array(phi[:, satir[ad]], dtype=float, copy=True)
           for ad in neumann}
    taban = np.finfo(float).eps * float(np.max(np.abs(phi)))
    bc = replace(bc, **yuz)
    grad = green_gauss_gradient(grid, phi, bc=bc, geom=grad_geom,
                                skew_iters=skew_iters)
    guncelleme = 0.0
    for _ in range(_NEUMANN_MAX_PASSES):
        guncelleme = 0.0
        for ad, dx_t in neumann.items():
            j = satir[ad]
            yeni = phi[:, j] + (grad[:, j, 0] * dx_t[:, 0]
                                + grad[:, j, 1] * dx_t[:, 1])
            guncelleme = max(guncelleme,
                             float(np.max(np.abs(yeni - yuz[ad]))))
            yuz[ad] = yeni
        bc = replace(bc, **yuz)
        if guncelleme <= taban:
            break
        grad = green_gauss_gradient(grid, phi, bc=bc, geom=grad_geom,
                                    skew_iters=skew_iters)
    return bc, grad, guncelleme


#: Yüz yeniden kurulumu fiziksel olmayan durum ürettiğinde beyan edilen
#: gerekçe (TEK kaynak; bekçiler bu metne bağlanır).
NONPHYSICAL_FACE_REASON = (
    'YÜZ yeniden kurulumu fiziksel olmayan durum üretti (T_yüz ≤ 0): '
    'hücre durumları fiziksel olduğu hâlde doğrusal yüz kurulumu '
    'T_yüz = T_c + ∇T·(x_yüz − x_c) taşıyor. ÖLÇÜLEN kök (V2, basamak 9): '
    'EĞİK duvarda (gerçek kontur 42,14°) i-yüzünün merkez→yüz vektörünün '
    'RADYAL bileşeni ilk hücre kalınlığının binlerce katıdır; duvar-normal '
    'gradyan o mesafeye uzatılınca sıcaklık negatife düşer. Bu bir '
    'IZGARA/AYRIKLAŞTIRMA sınırıdır (§5.7\'nin çarpıklık uyarısının '
    'sayısal hâli), kırpılarak gizlenmez: kalıntı NaN döner ve sürücü '
    'koşuyu "diverged" beyanıyla bitirir. Çare belgede V1b olarak '
    'duruyor (duvar-normal ötelemeli O-tipi yaka).')


def _nonphysical_result(grid, geom, grad_geom, wall_thermal, T_wall_source,
                        reason=None, *, transport=None, corrected=None,
                        boundary_mode_i=None, turbulent=None):
    """Fiziksel olmayan durum → NaN kalıntı (kırpma yok, istisna yok).

    BEYAN ANAHTAR KÜMESİ (ÖH defter P6B2-06): ``aux``ün KENDİ anahtarları
    zaten sağlam yolunkiyle aynıydı, ama BİR DÜZEY ALTINDA ayrışıyordu —
    ölçüldü (D23 once.json K8): ``declaration`` sağlam yolda 11 anahtar
    taşırken hata yolunda 4 anahtara düşüyordu ve düşenler arasında
    ``wall_output._prandtl``ın okuduğu ``transport`` da vardı. Bu yüzden
    hata yolundan gelen bir sonuç, künye üreten katmanda ADLI bir
    ValueError'a çarpıyordu (KeyError değil — o bacak çürütüldü).

    Kural: KOŞUMUN GİRDİSİ olan alanlar (taşınım künyesi, düzeltme kipi,
    sınır kipi, biçimlendirme, modellenmeyenler) hata yolunda da GERÇEK
    değerleriyle yayımlanır — bunlar ölçüm değil girdi yankısıdır.
    ÖLÇÜM olan alanlar (μ_t/μ oranı, Neumann yüz güncellemesi) ölçülemedi
    ve ``None`` kalır; sayı UYDURULMAZ (fail-closed).
    """
    ni, nj = grid.ni, grid.nj
    nan_ni = np.full(ni, np.nan)
    mid_j = grad_geom['mid_j']
    wall = WallOutputs(
        z_m=mid_j[:, -1, 0], r_m=mid_j[:, -1, 1],
        area_m2=geom['area_j'][:, -1],
        tau_wall_Pa=nan_ni, traction_z_Pa=nan_ni, traction_r_Pa=nan_ni,
        q_wall_W_m2=nan_ni, T_wall_K=nan_ni, T_cell_K=nan_ni,
        mu_wall_Pa_s=nan_ni, k_wall_W_mK=nan_ni,
        thermal_mode=wall_thermal, T_wall_source=T_wall_source)
    dudt = np.full((ni, nj, 4), np.nan)
    dudt[..., 0] = 0.0            # kütleye viskoz akı hiçbir hâlde girmez
    # Gradyan dizileri de NaN olarak YAYIMLANIR: sağlam yolun anahtar
    # kümesiyle aynı kalmalı (çağıran — SA bağlaması — hata yolunda ayrı
    # bir sözlük biçimiyle karşılaşmaz; KeyError sözleşmeyi delerdi).
    nan_grad = np.full((ni, nj, 2), np.nan)
    aux = {
        'wall': wall,
        'velocity_gradients': {'u_z': nan_grad, 'u_r': nan_grad.copy()},
        'wall_heat_W': float('nan'),
        'axial_friction_force_on_fluid_N': float('nan'),
        'max_abs_mass_residual': 0.0,
        'inlet_energy_flux_W': float('nan'),
        'outlet_energy_flux_W': float('nan'),
        'inlet_axial_force_N': float('nan'),
        'outlet_axial_force_N': float('nan'),
        'declaration': {
            '_source': 'hrma.cfd.viscous.viscous_residual',
            'nonphysical_state': reason or (
                'ρ ≤ 0, p ≤ 0 ya da sonsuz değer: kalıntı NaN döndürüldü '
                '(kırpma/pozitiflik tabanı YOK — euler_core sözleşmesi). '
                'Sürücü bunu ıraksama olarak raporlamalıdır.'),
            'formulation': ('axisymmetric Newtonian, Stokes hypothesis '
                            '(lambda = -2/3 mu); planar Green-Gauss '
                            'gradients with corrected face values'),
            'wall_thermal': wall_thermal,
            'T_wall_source': T_wall_source,
            'face_gradient_corrected': (None if corrected is None
                                        else bool(corrected)),
            'boundary_mode_i': boundary_mode_i,
            # ÖLÇÜM alanları: bu yolda ölçüm YAPILAMADI (durum fiziksel
            # değil), sayı uydurulmaz — None "ölçülmedi" demektir.
            'neumann_face_update_K': None,
            'turbulent_viscosity': (
                None if turbulent is None
                else ('mu_t supplied by caller (Boussinesq closure carried, '
                      'not solved); max(mu_t/mu) NOT measured on this path'
                      if turbulent else 'none (laminar V1)')),
            'mu_t_over_mu_max': None,
            'transport': (None if transport is None
                          else transport.declaration()),
            'not_modelled': dict(VISCOUS_NOT_MODELLED),
            '_declaration_parity': (
                'Bu sözlüğün ANAHTAR KÜMESİ sağlam yolunkiyle aynıdır '
                '(ÖH defter P6B2-06). Girdi yankısı olan alanlar gerçek '
                'değerlerini taşır; ÖLÇÜM olan alanlar (mu_t_over_mu_max, '
                'neumann_face_update_K) bu yolda ölçülemediği için None '
                'yayımlanır — None "ölçülmedi" demektir, sıfır değil.'),
        },
    }
    return dudt, aux


# ---------------------------------------------------------------------------
# Viskoz zaman adımı sınırı (§5.6 biçimi; C_visc ÇAĞIRANIN ölçtüğü sayıdır)
# ---------------------------------------------------------------------------

def viscous_spectral_radius(grid, U, transport, *, R, mu_t=None, geom=None):
    """Hücre başına viskoz spektral yarıçap toplamı Σ_yüz Λ_v [m³/s].

    Blazek, *CFD: Principles and Applications*, §6.1.4:

        Λ_v|yüz = max(4/(3ρ), γ/ρ) · (μ_eff/Pr_eff) · |S|² / V

    (Tasarım belgesi §5.6'nın yazımında ``max(4/3ρ, γ/ρ)`` görünüyor;
    boyut analizi 4/(3ρ) olduğunu söyler — ρ paydadır. Burada boyutlu
    doğru biçim kullanılır ve fark BEYAN edilir.)

    Δt_viskoz = V / Σ Λ_v; kararlılık katsayısı C_visc bu fonksiyonun
    DIŞINDA, çağıranın ÖLÇTÜĞÜ bir sayıdır — burada uydurulmaz.

    FİZİKSEL OLMAYAN DURUM: ``viscous_residual`` ile TEK SÖZLEŞME —
    ρ ≤ 0 / p ≤ 0 / sonsuz durumda dizinin TAMAMI NaN döner, istisna
    ATILMAZ (ölçüt: ``nonphysical_state``). Sürücü Δt sonluluk kapısında
    bunu 'diverged' olarak raporlar; eski davranış (gas_transport'un
    pozitiflik kapısından ValueError sızması) parti 38'de kapatıldı.
    """
    R, gamma = _check_gas_consistency(transport, R)
    mu_t_cell = (None if mu_t is None
                 else _check_mu_t(mu_t, grid.ni, grid.nj))
    if geom is None:
        geom = precompute_geometry(grid)
    w = cons_to_prim_axisym(np.asarray(U, dtype=float), gamma)
    if nonphysical_state(w):
        return np.full((grid.ni, grid.nj), np.nan)
    rho = w[..., 0]
    T = w[..., 3] / (rho * R)
    mu = transport.viscosity(T)
    katsayi = np.maximum(4.0 / (3.0 * rho), gamma / rho)
    if mu_t_cell is None:
        nu_eff = mu / transport.prandtl
    else:
        # Blazek §6.1.4'ün türbülanslı biçimi: μ_L/Pr_L + μ_T/Pr_T.
        # Bu toplam gas_transport'ta ZATEN tanımlıdır (k_eff/cp) —
        # ikinci kez yazmak yerine oradan alınır (tek kaynak).
        nu_eff = effective_conductivity(
            transport.cp, mu, transport.prandtl, mu_t_cell,
            transport.prandtl_turbulent) / transport.cp
    alan2 = (geom['area_i'][:-1] ** 2 + geom['area_i'][1:] ** 2
             + geom['area_j'][:, :-1] ** 2 + geom['area_j'][:, 1:] ** 2)
    return katsayi * nu_eff * alan2 / grid.volume


def viscous_local_dt_limit(grid, U, transport, *, R, mu_t=None, geom=None):
    """Δt_viskoz = V / Σ Λ_v [s] (güvenlik katsayısı UYGULANMAZ).

    Fiziksel olmayan durumda Λ_v NaN döndüğü için Δt de NaN'dır — sürücü
    sözleşmesinin beklediği sinyal budur (istisna değil).
    """
    return grid.volume / viscous_spectral_radius(
        grid, U, transport, R=R, mu_t=mu_t, geom=geom)


# ---------------------------------------------------------------------------
# h_g duyarlılığı: iki T_w koşusundan ÖLÇÜLEN bant (§5.4)
# ---------------------------------------------------------------------------

def h_g_wall_temp_sensitivity(run_at_wall_temperature, T0, *,
                              recovery_temperature_K,
                              ratios=WALL_TEMP_SENSITIVITY_RATIOS):
    """h_g = q_w/(T_aw − T_w) bandını İKİ koşudan ÖLÇER (varsaymaz).

    Tasarım belgesi §5.4: "h_g'nin T_w'ye zayıf bağımlılığı iddia
    edilecekse KANITLANMALI. İki koşu (T_w = 0,3·T₀ ve 0,6·T₀) ile h_g
    bandı ÖLÇÜLÜR". Bu, termal FEA köprüsünün (h_g, T_rec)
    doğrusallaştırmasının geçerlilik beyanıdır.

    Args:
        run_at_wall_temperature: ``T_w [K] → WallOutputs`` çağrılabiliri.
            Çağıran koşuyu nasıl sürdüğünü kendi bilir (bu modül sürücü
            değildir); dönen nesnenin ``q_wall_W_m2`` ve ``z_m`` alanları
            kullanılır.
        T0: Durma sıcaklığı [K] — iki duvar sıcaklığı bunun oranıdır.
        recovery_temperature_K: T_aw(z) [K] — istasyon dizisi ya da skaler.
            ZORUNLUDUR ve UYDURULMAZ: ya adyabatik eş koşudan ÖLÇÜLÜR ya da
            kurtarma faktörü tanımıyla çağıran verir; hangisi kullanıldıysa
            koşum beyanında görünmelidir.
        ratios: Duvar sıcaklığı oranları (varsayılan §5.4'ün kendi sayıları).

    Returns:
        dict — istasyon başına h_g dizileri, bağıl bant ve beyan.

    Raises:
        ValueError: T_aw ≤ T_w olan istasyon varsa (h_g tanımsız), oran
            bandı ya da dizi biçimleri bozuksa.
    """
    T0 = float(T0)
    if not np.isfinite(T0) or T0 <= 0.0:
        raise ValueError(f'T0 pozitif ve sonlu olmalı — verilen: {T0!r}.')
    oranlar = tuple(float(x) for x in ratios)
    if len(oranlar) != 2 or not all(0.0 < x < 1.0 for x in oranlar):
        raise ValueError(
            f'ratios (0, 1) aralığında İKİ oran olmalı — verilen: {ratios!r}.')

    kosum = {}
    for oran in oranlar:
        T_w = oran * T0
        wall = run_at_wall_temperature(T_w)
        T_aw = np.broadcast_to(
            np.asarray(recovery_temperature_K, dtype=float),
            np.shape(wall.q_wall_W_m2))
        fark = T_aw - np.asarray(wall.T_wall_K, dtype=float)
        if np.any(fark <= 0.0):
            raise ValueError(
                f'T_w = {T_w!r} K için T_aw − T_w ≤ 0 olan istasyon var: '
                'h_g = q_w/(T_aw − T_w) tanımsız. Kurtarma sıcaklığı '
                'kaynağı ya da duvar sıcaklığı oranı gözden geçirilmeli '
                '(sessiz NaN yayımlanmaz).')
        kosum[oran] = {
            'T_wall_K': np.asarray(wall.T_wall_K, dtype=float),
            'q_wall_W_m2': np.asarray(wall.q_wall_W_m2, dtype=float),
            'h_g_W_m2K': np.asarray(wall.q_wall_W_m2, dtype=float) / fark,
            'z_m': np.asarray(wall.z_m, dtype=float),
        }

    h1 = kosum[oranlar[0]]['h_g_W_m2K']
    h2 = kosum[oranlar[1]]['h_g_W_m2K']
    if h1.shape != h2.shape:
        raise ValueError('İki koşu farklı istasyon sayısı döndürdü — aynı '
                         'ızgarada koşulmalı.')
    ortalama = 0.5 * (h1 + h2)
    bagil = np.abs(h1 - h2) / np.abs(ortalama)
    return {
        '_source': 'hrma.cfd.viscous.h_g_wall_temp_sensitivity',
        'T0_K': T0,
        'wall_temperature_ratios': oranlar,
        'wall_temperatures_K': tuple(o * T0 for o in oranlar),
        'runs': kosum,
        'h_g_relative_band': bagil,
        'max_relative_band': float(np.max(bagil)),
        'mean_relative_band': float(np.mean(bagil)),
        'declaration': (
            'h_g = q_w/(T_aw − T_w); bant İKİ ayrı duvar sıcaklığıyla '
            'koşulup ÖLÇÜLDÜ (varsayılmadı). Termal FEA köprüsünün '
            '(h_g, T_rec) doğrusallaştırması bu bant kadar geçerlidir.'),
    }
