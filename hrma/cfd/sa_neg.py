# hrma/cfd — Spalart-Allmaras (SA-noft2 + negatif-ν̃ dalı) türbülans çekirdeği
"""
Tek denklemli SA türbülans modeli: taşınım (birinci mertebe upwind, isteğe
bağlı MUSCL), difüzyon (korunumlu biçim) ve kaynak (üretim AÇIK, yok etme
NOKTA-ÖRTÜK). Ortalama akış alanına dokunmaz — ``viscous.py`` gibi ayrı,
saf bir kalıntı üretir (tasarım belgesi §5.1 KOMPOZİSYON ilkesi).

KÜNYE (ölçüldü — kaynak metni indirilip okundu, 18 Ağu 2026)
------------------------------------------------------------
- **Birincil model:** Spalart, P. R. ve Allmaras, S. R., "A One-Equation
  Turbulence Model for Aerodynamic Flows", *Recherche Aérospatiale*,
  No. 1, 1994, s. 5-21. Konferans sürümü AIAA-92-0439 (DOI
  10.2514/6.1992-439, depo belgesi §7.2'de Crossref ile doğrulanmış).
  NASA Turbulence Modeling Resource (TMR) İKİ UYARI koyuyor ve ikisi de
  burada uygulanmıştır: (i) *dergi sürümü önceliklidir* — 1992 bildirisi
  c_t3 = 1,1 ve c_t4 = 2,0 kullanır, güncel değerler 1,2 ve 0,5'tir;
  (ii) dergi sürümünün EKİNDE c_w1 tanımında dizgi hatası vardır (paydada
  κ'nın karesi düşmüş). Bu modül c_w1'i LİTERAL YAZMAZ, bağıntıdan
  TÜRETİR (:data:`SA_C_W1`) — dizgi hatasının taşınması yapısal olarak
  imkânsızdır.
- **Negatif dal:** Allmaras, S. R., Johnson, F. T. ve Spalart, P. R.,
  "Modifications and Clarifications for the Implementation of the
  Spalart-Allmaras Turbulence Model", ICCFD7-1902, 7th International
  Conference on Computational Fluid Dynamics, Big Island, Hawaii,
  9-13 Temmuz 2012. Crossref bu bildiriyi İNDEKSLEMİYOR (belge §7.2'nin
  açık kalemi); künye doğrudan yayıncının PDF'inden doğrulandı:
  https://www.iccfd.org/iccfd7/assets/pdf/papers/ICCFD7-1902_paper.pdf
  (6 sayfa, başlık/yazar/oturum sayfa 1'de; denklem numaraları aşağıda
  ANILDIĞI YERDE bu PDF'e aittir).
- **Çapraz künye:** NASA TMR, https://turbmodels.larc.nasa.gov/spalart.html
  (SA, SA-neg, SA-noft2 bölümleri) — modelin adlandırma ve doğrulama
  otoritesi.

MODEL KARARI: SA-noft2 + SA-neg (ve bunun ÖLÇÜLEN bedeli)
---------------------------------------------------------
Tasarım belgesi §5.5 f_t2'siz (SA-noft2) biçimi seçiyor; bu evre negatif
dalı da istiyor. İkisinin birleşimi **bedelsiz değildir** ve bedel burada
uydurma değil ÖLÇÜLMÜŞTÜR:

- ICCFD7-1902 §3.2 (Denklem 15) negatif dalın ν̃ = 0'da C¹ sürekli olmasını
  f_t2'nin VARLIĞINA dayandırır: ∂P/∂ν̃|₀ = c_b1(1 − c_t3)S ancak
  f_t2(0) = c_t3 iken sağlanır. f_t2 kaldırılınca (c_t3 = 0 pozitif dalda)
  makalenin kendi ifadesiyle "either C¹ continuity must be given up or
  P_n < 0 must be allowed" — ikisinden biri seçilmek zorundadır.
- Bu modül **C¹'den vazgeçer**, enerji kararlılığını (Denklem 18) ve
  "negatif kararlı-hâl minimumu oluşamaz" koşulunu (Denklem 20) KORUR.
  Yani negatif dalın P_n − D_n ≥ 0 özelliği bozulmaz.
- NASA TMR bu seçimi kayda geçirmiştir: "SA-neg-noft2 uygulanamaz" cümlesi
  sayfadan KALDIRILMIŞ ve kaldırma gerekçesi kaynak HTML'de yorum olarak
  durmaktadır (18 Ağu 2026'da ölçüldü): *"The following was removed
  because many solvers use SA-neg-noft2 without any additional problems.
  It is true that -noft2 degrades smoothness of the SA-neg solution to C0
  at nutilde=0. However, if we expect the converged SA-neg solution to be
  positive, this degradation does not matter."*
- Kırığın BÜYÜKLÜĞÜ ölçülür ve bekçilenir: ν̃ = 0'da kaynağın sol/sağ
  türev farkı TAM olarak c_b1·c_t3·S'tir, yani pozitif taraftaki eğimin
  c_t3 = 1,2 katı (tests/cfd/test_sa_neg.py). Kaynak fonksiyonun KENDİSİ
  süreklidir (C⁰) — sıçrayan yalnız türevdir.

SIKIŞTIRILABİLİR BİÇİM: ρ TÜREVİN İÇİNE GİRMEZ (ölçülen sapma)
--------------------------------------------------------------
Tasarım belgesi §5.5 difüzyonu ``(1/σ)∇·((μ + ρν̃)∇ν̃) + (c_b2/σ)ρ|∇ν̃|²``
yazıyor. Bu biçim TMR'nin "Note 4" uyarısının tarif ettiği kusurdur:
yoğunluğu türevin içine almak SA'yı değiştirir ve etkisi süpersonik
akışta görünür (bizim vakamız tam olarak budur). ICCFD7-1902 Denklem 9,
korunumlu biçimin doğrusunu verir — SA ile kütle korunumunun birleşimi
bir terim DAHA doğurur:

    ∂(ρν̃)/∂t + ∇·(ρuν̃) = ρ(P − D)
        + (1/σ)∇·(ρ(ν + ν̃f_n)∇ν̃) + (c_b2/σ)ρ|∇ν̃|²
        − (1/σ)(ν + ν̃f_n) ∇ρ·∇ν̃                       ← §5.5'te YOK

Son terim ρ'yu türevin dışına taşımanın cebirsel bedelidir; onsuz çözülen
denklem SA DEĞİLDİR. Bu modül Denklem 9'u harfi harfine gerçekler, sapma
burada beyan edilir ve terimin BÜYÜKLÜĞÜ lüle sınıfı yoğunluk gradyanında
ölçülür (tests/cfd/test_sa_neg.py::test_yogunluk_gradyani_terimi_*).

AYRIK TASARIM (§5.5)
--------------------
- **Taşınım:** birinci mertebe yukarı-akış (varsayılan, ``'upwind1'``).
  İkinci mertebe MUSCL (``'muscl2'``) İSTEĞE BAĞLI olarak vardır ve
  sınırlayıcısı ``euler_core.minmod``'dur (ikinci bir sınırlayıcı tanımı
  YOK). Mertebe farkı ölçülür, varsayılmaz.
- **Difüzyon:** gradyan operatörü ``gradients.py`` (§5.2) — bu modülde
  ikinci bir Green-Gauss gerçeklemesi yoktur.
- **Kaynak:** üretim AÇIK, yok etme NOKTA-ÖRTÜK. Duvara komşu hücrede
  d ~ 10⁻⁶ m iken ν̃/d² mertebesi 10¹² 1/s sınıfına çıkar; açık alınırsa
  Δt bu terimle sınırlanır (ölçüm bekçide). Nokta-örtük köşegen, TAM
  analitik ∂(P−D)/∂(ρν̃) türevinin negatif kısmıdır (V3 — yalnız donmuş
  yok etme türevini taşıyan eski köşegen tampon tabakada periyot-2
  salınıma kilitleniyordu; ölçüm ``sa_source_terms`` docstring'inde).
- **Sınır koşulları:** duvarda ν̃ = 0 (Dirichlet), girişte serbest-akım
  bandı ν̃/ν ∈ [3, 5] (ICCFD7-1902 Denklem 8; bant DIŞI değer beyanla
  REDDEDİLİR), çıkışta dışdeğerleme, eksende çift (∂ν̃/∂n = 0).

SÖZLEŞME
--------
- Fiziksel olmayan ortalama akış durumu (ρ ≤ 0, p ≤ 0, sonsuz) →
  kalıntı NaN, İSTİSNA YOK: ölçüt ``viscous.nonphysical_state`` ile
  ORTAKTIR (tek tanım; euler_core geleneği).
- ν̃ < 0 fiziksel olmayan bir durum DEĞİLDİR — modelin kendi dalıdır.
- Ω (girdap büyüklüğü) ve d (duvar mesafesi) DIŞARIDAN gelir: hız
  gradyanları viskoz kalıntının kullandığı gradyanların TA KENDİSİ
  olmalıdır (ikinci bir gradyan tanımı doğmasın), duvar mesafesi
  ``wall_distance.wall_distance_field``ten.
"""

from collections import namedtuple

import numpy as np

from hrma.cfd.euler_core import cons_to_prim_axisym, minmod
from hrma.cfd.gradients import (
    BoundaryFaceValues,
    face_gradients,
    green_gauss_gradient,
    interpolate_to_faces,
    precompute_gradient_geometry,
)
from hrma.cfd.viscous import nonphysical_state
from hrma.cfd.wall_distance import wall_distance_field

__all__ = [
    'SA_CITATIONS',
    'SA_CONVECTION_SCHEMES',
    'SA_C_B1',
    'SA_C_B2',
    'SA_C_N1',
    'SA_C_T3',
    'SA_C_V1',
    'SA_C_V2',
    'SA_C_V3',
    'SA_C_W1',
    'SA_C_W2',
    'SA_C_W3',
    'SA_FREESTREAM_CHI_BAND',
    'SA_KAPPA',
    'SA_NOT_MODELLED',
    'SA_R_LIM',
    'SA_SIGMA',
    'SASource',
    'chi',
    'diffusion_coefficient',
    'f_n',
    'f_v1',
    'f_v2',
    'f_w',
    'face_mass_flux',
    'freestream_nu_tilde',
    'modified_vorticity',
    'sa_boundary_face_values',
    'sa_constants',
    'sa_convective_residual',
    'sa_diffusive_residual',
    'sa_point_implicit_delta',
    'sa_r',
    'sa_residual',
    'sa_source_terms',
    'turbulent_viscosity',
    'vorticity_magnitude',
]

# ---------------------------------------------------------------------------
# Model sabitleri — TEK KAYNAK (ICCFD7-1902 Denklem 5-8 ve 21-22)
#
# Her sayı yayımlanmış künyeden gelir; TÜRETİLEBİLEN hiçbir sayı literal
# yazılmaz (c_w1 buna örnektir: dergi ekindeki dizgi hatası ancak literal
# yazılırsa taşınabilirdi).
# ---------------------------------------------------------------------------

#: Üretim katsayısı c_b1 (SA 1994, ICCFD7-1902 Denklem 5-8 listesi).
SA_C_B1 = 0.1355
#: Difüzyon Prandtl'ı σ.
SA_SIGMA = 2.0 / 3.0
#: Gradyan-kare (difüzyon üretimi) katsayısı c_b2.
SA_C_B2 = 0.622
#: von Kármán sabiti κ (SA'nın KENDİ değeri; log-katman özdeşliği bunu ister).
SA_KAPPA = 0.41
#: Duvar fonksiyonu sabitleri.
SA_C_W2 = 0.3
SA_C_W3 = 2.0
#: f_v1 eşiği c_v1 (χ³/(χ³+c_v1³)).
SA_C_V1 = 7.1
#: Laminer bastırma sabiti c_t3 — POZİTİF dalda KULLANILMAZ (SA-noft2:
#: f_t2 ≡ 0), yalnız NEGATİF dalın üretim eğimindedir (Denklem 22).
#: c_t4 bilinçli olarak TANIMLANMAMIŞTIR: yalnız f_t2'nin içinde geçer,
#: f_t2 ≡ 0 olduğu için tanımlanan ama kullanılmayan sabit olurdu.
SA_C_T3 = 1.2
#: Değiştirilmiş girdaplılık yaması (Note 1(c) / Denklem 12) sabitleri.
SA_C_V2 = 0.7
SA_C_V3 = 0.9
#: r kelepçesi (Denklem 5): r = min(ν̃/(S̃κ²d²), r_lim).
SA_R_LIM = 10.0
#: Negatif dal difüzyon katsayısı sabiti c_n1 (Denklem 21).
SA_C_N1 = 16.0

#: TÜRETİLMİŞ sabit — literal DEĞİL (dergi ekindeki dizgi hatasına karşı
#: yapısal bağışıklık; ayrıca log-katman denge özdeşliğinin tam da bu
#: bağıntıyı gerektirdiği bekçide ölçülür).
SA_C_W1 = SA_C_B1 / SA_KAPPA ** 2 + (1.0 + SA_C_B2) / SA_SIGMA

#: Serbest-akım ν̃/ν bandı (ICCFD7-1902 Denklem 8: "ν̃/ν = 3-5",
#: karşılığı ν_t/ν ≈ 0,21-1,3). Bant DIŞI değer beyanla reddedilir.
SA_FREESTREAM_CHI_BAND = (3.0, 5.0)

#: Taşınım şemaları — üçüncüsü yok.
SA_CONVECTION_SCHEMES = ('upwind1', 'muscl2')

#: Künyeler (koşum beyanına aynen girer).
SA_CITATIONS = {
    'model': ('Spalart, P. R. & Allmaras, S. R., "A One-Equation Turbulence '
              'Model for Aerodynamic Flows", Recherche Aerospatiale, No. 1, '
              '1994, pp. 5-21 (conference version AIAA-92-0439, '
              'doi:10.2514/6.1992-439). Journal version takes precedence '
              '(NASA TMR): c_t3=1.2, c_t4=0.5; the c_w1 typo in the journal '
              'appendix is avoided by deriving c_w1 from its definition.'),
    'negative_branch': (
        'Allmaras, S. R., Johnson, F. T. & Spalart, P. R., "Modifications '
        'and Clarifications for the Implementation of the Spalart-Allmaras '
        'Turbulence Model", ICCFD7-1902, 7th Int. Conf. on Computational '
        'Fluid Dynamics, Big Island, Hawaii, 9-13 July 2012 (Eqs. 9, 12, '
        '21, 22). Not indexed by Crossref; verified from the publisher PDF '
        'https://www.iccfd.org/iccfd7/assets/pdf/papers/'
        'ICCFD7-1902_paper.pdf'),
    'resource': 'NASA TMR, https://turbmodels.larc.nasa.gov/spalart.html',
    'variant': ('SA-noft2 (f_t2 = 0) with the negative-nutilde branch '
                '(SA-neg). C1 continuity at nutilde=0 is deliberately given '
                'up (C0 kink of size c_b1*c_t3*S); energy stability '
                '(Eq. 18) and the no-negative-minimum condition (Eq. 20) '
                'are preserved and measured.'),
}

#: Bu evrede modellenmeyenler (paket beyanına eklenir).
SA_NOT_MODELLED = {
    'transition': (
        'Geçiş (transition) modellenmedi: tam türbülanslı kabul (SA-noft2, '
        'f_t2 ≡ 0) ve trip terimi f_t1 YOK — laminer/türbülanslı ayrımı '
        'çözümden çıkmaz, çağıranın kabulüdür.'),
    'model_corrections': (
        'SA düzeltmeleri (RC/R dönme-eğrilik, QCR, comp, LRe, rough) '
        'uygulanmadı: her biri ayrı künye ve ayrı doğrulama ister.'),
    'wall_roughness': (
        'Pürüzlülük (Aupoix-Spalart) modellenmedi — hidrolik pürüzsüz '
        'duvar (viscous.py ile aynı kapsam).'),
    'turbulent_prandtl': (
        'Türbülanslı ısı taşınımı Pr_t ile kapatılır ve Pr_t bu modülün '
        'DEĞİL gas_transport.py\'nin sabitidir (tek kaynak).'),
}

#: Kaynak terimi demeti — parçalar AYRI yayımlanır (bekçiler üretimi ve
#: yok etmeyi ayrı ayrı ölçebilsin; toplamda gizlenen işaret hatası
#: olmasın).
SASource = namedtuple(
    'SASource', ['production', 'destruction', 'source', 'jacobian_diag'])


def sa_constants():
    """Model sabitlerinin künyeli sözlüğü (koşum beyanı için).

    Sözlük SABİTLERİN KENDİSİNDEN kurulur — ikinci bir sayı listesi yok.
    """
    return {
        '_source': 'hrma.cfd.sa_neg',
        'c_b1': SA_C_B1, 'sigma': SA_SIGMA, 'c_b2': SA_C_B2,
        'kappa': SA_KAPPA, 'c_w1': SA_C_W1, 'c_w2': SA_C_W2,
        'c_w3': SA_C_W3, 'c_v1': SA_C_V1, 'c_t3': SA_C_T3,
        'c_v2': SA_C_V2, 'c_v3': SA_C_V3, 'c_n1': SA_C_N1,
        'r_lim': SA_R_LIM,
        'c_w1_derived_from': 'c_b1/kappa^2 + (1+c_b2)/sigma',
        'freestream_chi_band': SA_FREESTREAM_CHI_BAND,
        'citations': dict(SA_CITATIONS),
    }


# ---------------------------------------------------------------------------
# Kapanış fonksiyonları — saf cebir, ızgara bilmez
#
# GÜVENLİ MASKELEME KURALI: np.where İKİ dalı da hesaplar. f_v1'in χ = −c_v1
# kutbu ve f_n'in χ = c_n1^(1/3) kutbu KULLANILMAYAN dalda bile inf/NaN
# üretirdi (inf·0 = NaN). Bu yüzden her formül kendi geçerli yarı-ekseninde
# kelepçelenmiş χ ile değerlendirilir.
# ---------------------------------------------------------------------------

def chi(nu_tilde, nu):
    """χ = ν̃/ν — modelin biricik boyutsuz değişkeni."""
    return np.asarray(nu_tilde, dtype=float) / np.asarray(nu, dtype=float)


def f_v1(x):
    """f_v1 = χ³/(χ³ + c_v1³). Tanım aralığı χ ≥ 0 (χ = −c_v1'de kutup).

    Negatif dalda ν_t = 0 olduğundan model bu fonksiyonu χ < 0 için HİÇ
    çağırmaz; çağıran doğrudan kullanırsa kutup kendi sorumluluğundadır.
    """
    x = np.asarray(x, dtype=float)
    x3 = x ** 3
    return x3 / (x3 + SA_C_V1 ** 3)


def f_v2(x):
    """f_v2 = 1 − χ/(1 + χ f_v1) — χ ≥ 0 için (payda ≥ 1, tekil değil)."""
    x = np.asarray(x, dtype=float)
    return 1.0 - x / (1.0 + x * f_v1(x))


def _f_v1_prime(x):
    """df_v1/dχ = 3χ²c_v1³/(χ³ + c_v1³)² — f_v1 tanımının türevi.

    Kaynak Jacobian zinciri için (V3). DEĞER f_v1'in kendisinden gelir;
    burada yalnız türev cebiri yazılır (ikinci değer tanımı yok).
    """
    x = np.asarray(x, dtype=float)
    c3 = SA_C_V1 ** 3
    return 3.0 * x ** 2 * c3 / (x ** 3 + c3) ** 2


def _f_v2_prime(x):
    """df_v2/dχ = −(1 − χ²f_v1′)/(1 + χf_v1)² — f_v2 tanımının türevi.

    TAMPON TABAKANIN anahtarı: χ ≈ 1,5-4'te f_v2 + χf_v2′ büyük-negatiftir
    (χ·f_v2 orada azalır) ve üretim türevini negatife çeker — kaynak
    Jacobian'ının üretim payı tam buradan doğar (V3 kaleminin ölçtüğü
    periyot-2 kusurunun cebirsel kökü).
    """
    x = np.asarray(x, dtype=float)
    return -(1.0 - x ** 2 * _f_v1_prime(x)) / (1.0 + x * f_v1(x)) ** 2


def f_n(x):
    """Negatif dalın difüzyon katsayısı çarpanı (Denklem 21).

    f_n = (c_n1 + χ³)/(c_n1 − χ³) yalnız χ < 0 için tanımlıdır (χ =
    c_n1^(1/3) ≈ 2,52'de kutbu vardır); χ ≥ 0 dalında model f_n = 1 alır.
    Bu fonksiyon ALAN biçimindedir: χ ≥ 0 girdileri için 1,0 döner ve
    formül kelepçelenmiş (χ ≤ 0) değerle hesaplandığından kutup ASLA
    değerlendirilmez.
    """
    x = np.asarray(x, dtype=float)
    x_neg = np.minimum(x, 0.0)
    x3 = x_neg ** 3
    return np.where(x < 0.0, (SA_C_N1 + x3) / (SA_C_N1 - x3), 1.0)


def turbulent_viscosity(rho, nu_tilde, mu):
    """μ_t = ρ ν̃ f_v1(χ) — ν̃ < 0 olan yerde TAM SIFIR (SA-neg kuralı).

    Args:
        rho: Yoğunluk [kg/m³].
        nu_tilde: SA değişkeni ν̃ [m²/s] (negatif olabilir).
        mu: Moleküler dinamik viskozite μ [Pa·s].

    Returns:
        μ_t [Pa·s], girdi biçiminde.
    """
    rho = np.asarray(rho, dtype=float)
    nu_tilde = np.asarray(nu_tilde, dtype=float)
    mu = np.asarray(mu, dtype=float)
    x = rho * nu_tilde / mu                      # χ = ν̃/ν = ρν̃/μ
    x_pos = np.maximum(x, 0.0)                   # kutup (χ = −c_v1) yasak
    return np.where(x > 0.0, rho * nu_tilde * f_v1(x_pos), 0.0)


def vorticity_magnitude(grad_uz, grad_ur):
    """Ω = √(2 W_ij W_ij) — eksenel simetrik, çevresel hız YOK.

    Girdaplılığın tek bileşeni ω_θ = ∂u_r/∂z − ∂u_z/∂r olduğundan
    Ω = |∂u_z/∂r − ∂u_r/∂z| (cebirsel özdeşlik, bekçili).

    Args:
        grad_uz: (..., 2) ∇u_z — [..., 0] = ∂/∂z, [..., 1] = ∂/∂r
            (gradients.py bileşen sırası).
        grad_ur: (..., 2) ∇u_r.
    """
    grad_uz = np.asarray(grad_uz, dtype=float)
    grad_ur = np.asarray(grad_ur, dtype=float)
    return np.abs(grad_uz[..., 1] - grad_ur[..., 0])


def modified_vorticity(omega, nu_tilde, d, nu, return_derivative=False):
    """S̃ — Note 1(c) / ICCFD7-1902 Denklem 12 yaması ile (kırpma YOK).

    S̄ = ν̃ f_v2/(κ²d²) tanımlanır; S̄ ≥ −c_v2 Ω iken S̃ = Ω + S̄, aksi
    hâlde S̃ = Ω + Ω(c_v2²Ω + c_v3 S̄)/((c_v3 − 2c_v2)Ω − S̄). Yamanın
    ölçülebilir üç iddiası vardır (üçü de bekçili): yama noktasında
    S̃ = (1 − c_v2)Ω, asimptotta S̃ → (1 − c_v3)Ω, ve Ω > 0 olan her yerde
    S̃ > 0. Ω = 0 ise S̃ = 0 olabilir; r hesabı bunu ``sa_r`` içinde
    r = r_lim ile karşılar (TMR'nin kendi koruması).

    Negatif ν̃ dalı S̃ KULLANMAZ (üretim doğrudan Ω ile yazılır); burada
    χ ≥ 0'a kelepçelenmiş değerle hesaplanır ki f_v2'nin kutbu hiçbir
    hâlde değerlendirilmesin.

    ``return_derivative=True`` verilirse ``(S̃, dS̃/dν̃)`` döner (kaynak
    Jacobian zinciri, V3). Türev POZİTİF dal içindir (ν̃ < 0 kelepçe
    bölgesinde değeri kullanılmaz — negatif dalın kendi kapalı türevi
    ``sa_source_terms``ta); her iki S̃ dalının zinciri taşınır:
    dS̃/dS̄ yamasızda 1, yamada Denklem 12 ifadesinin kendi türevi.
    Varsayılan ``False`` yol bit-özdeştir (tek işlem eklenmez).
    """
    omega = np.asarray(omega, dtype=float)
    nu_tilde = np.asarray(nu_tilde, dtype=float)
    d = np.asarray(d, dtype=float)
    nu = np.asarray(nu, dtype=float)
    nu_pos = np.maximum(nu_tilde, 0.0)
    s_bar = nu_pos * f_v2(nu_pos / nu) / (SA_KAPPA ** 2 * d ** 2)
    yama = s_bar < -SA_C_V2 * omega
    # Yama dalının paydası: (c_v3 − 2c_v2)Ω − S̄. Dal koşulu S̄ < −c_v2Ω
    # olduğundan payda > (c_v3 − c_v2)Ω ≥ 0,2Ω > 0'dır (cebirsel gerçek);
    # yine de İKİ dalı da hesaplayan np.where için payda güvenli tarafa
    # kelepçelenir (kullanılmayan dalda 0'a bölme doğmasın).
    payda = np.where(yama, (SA_C_V3 - 2.0 * SA_C_V2) * omega - s_bar, 1.0)
    yamali = omega + omega * (SA_C_V2 ** 2 * omega + SA_C_V3 * s_bar) / payda
    s_tilde = np.where(yama, yamali, omega + s_bar)
    if not return_derivative:
        return s_tilde
    # dS̄/dν̃ = (f_v2 + χf_v2′)/(κ²d²) — S̄ = ν̃f_v2(χ) tanımının zinciri
    x = nu_pos / nu
    ds_bar = (f_v2(x) + x * _f_v2_prime(x)) / (SA_KAPPA ** 2 * d ** 2)
    # dS̃/dS̄: yamasız dal 1; yama dalında bölüm kuralı (payda yukarıdaki
    # kelepçeli dizi — yama dalında gerçek payda, diğerinde kullanılmaz).
    dst_dsbar = np.where(
        yama,
        omega * (SA_C_V3 * payda
                 + (SA_C_V2 ** 2 * omega + SA_C_V3 * s_bar)) / payda ** 2,
        1.0)
    return s_tilde, dst_dsbar * ds_bar


def sa_r(nu_tilde, s_tilde, d, ds_tilde=None):
    """r = min(ν̃/(S̃κ²d²), r_lim); S̃ = 0 ise r = r_lim (TMR koruması).

    ``ds_tilde`` (dS̃/dν̃) verilirse ``(r, dr/dν̃)`` döner (kaynak Jacobian
    zinciri, V3): kelepçenin İKİ kolunda da (payda ≤ 0 ya da ham ≥ r_lim)
    r sabittir ve türev SIFIRDIR — kelepçe kararı DEĞERLE AYNI maskeden
    okunur, ikinci bir kelepçe tanımı yazılmaz. Verilmezse yol bit-özdeş.
    """
    nu_tilde = np.asarray(nu_tilde, dtype=float)
    s_tilde = np.asarray(s_tilde, dtype=float)
    d = np.asarray(d, dtype=float)
    payda = s_tilde * SA_KAPPA ** 2 * d ** 2
    guvenli = np.where(payda > 0.0, payda, 1.0)
    ham = np.where(payda > 0.0, nu_tilde / guvenli, SA_R_LIM)
    r = np.minimum(ham, SA_R_LIM)
    if ds_tilde is None:
        return r
    serbest = (payda > 0.0) & (ham < SA_R_LIM)
    # dr/dν̃ = (S̃ − ν̃·dS̃/dν̃)/(S̃²κ²d²) — bölüm kuralı; kelepçedeyken 0.
    dr = np.where(
        serbest,
        (s_tilde - nu_tilde * np.asarray(ds_tilde, dtype=float))
        / np.where(serbest, s_tilde * payda, 1.0),
        0.0)
    return r, dr


def f_w(r, return_derivative=False):
    """f_w = g[(1 + c_w3⁶)/(g⁶ + c_w3⁶)]^(1/6), g = r + c_w2(r⁶ − r).

    ``return_derivative=True`` verilirse ``(f_w, df_w/dr)`` döner (kaynak
    Jacobian zinciri, V3): df_w/dg = h·c_w3⁶/(g⁶ + c_w3⁶) (h = f_w/g'nin
    kapalı formu; g = 0'da da sonlu) ve dg/dr = 1 + c_w2(6r⁵ − 1).
    Varsayılan ``False`` yol bit-özdeştir.
    """
    r = np.asarray(r, dtype=float)
    g = r + SA_C_W2 * (r ** 6 - r)
    h = ((1.0 + SA_C_W3 ** 6) / (g ** 6 + SA_C_W3 ** 6)) ** (1.0 / 6.0)
    if not return_derivative:
        return g * h
    dg = 1.0 + SA_C_W2 * (6.0 * r ** 5 - 1.0)
    return g * h, h * SA_C_W3 ** 6 / (g ** 6 + SA_C_W3 ** 6) * dg


def diffusion_coefficient(rho, nu_tilde, mu):
    """Γ = μ + ρ ν̃ f_n(χ) = ρ(ν + ν̃f_n) [Pa·s] — iki dal tek ifadede.

    ν̃ ≥ 0'da f_n = 1 (standart SA), ν̃ < 0'da Denklem 21. Katsayının
    HER YERDE pozitif kaldığı (Denklem 20) bekçide ölçülür: ölçülen alt
    sınır 0,00936·μ (χ ≈ −1,3744'te).
    """
    rho = np.asarray(rho, dtype=float)
    nu_tilde = np.asarray(nu_tilde, dtype=float)
    mu = np.asarray(mu, dtype=float)
    return mu + rho * nu_tilde * f_n(rho * nu_tilde / mu)


# ---------------------------------------------------------------------------
# Kaynak: üretim AÇIK, yok etme NOKTA-ÖRTÜK
# ---------------------------------------------------------------------------

def sa_source_terms(rho, nu_tilde, mu, omega, d):
    """SA kaynak terimleri ve nokta-örtük köşegen katkısı.

    Pozitif dal (SA-noft2, f_t2 ≡ 0):
        P = ρ c_b1 S̃ ν̃                 D = ρ c_w1 f_w (ν̃/d)²
    Negatif dal (ICCFD7-1902 Denklem 22):
        P = ρ c_b1(1 − c_t3) Ω ν̃        D = −ρ c_w1 (ν̃/d)²
    (ν̃ < 0 iken (1 − c_t3) < 0 olduğundan P ≥ 0'dır ve D'nin İŞARETİ
    pozitif dalın tersidir — makalenin açıkça uyardığı nokta.)

    Kaynak = P − D. Nokta-örtük köşegen ``jacobian_diag``, ∂(P−D)/∂(ρν̃)
    TAM ANALİTİK türevinin negatif kısmıdır (Jacobi'nin sönümleyici yarısı
    köşegene taşınır):
        pozitif dal : max(−[∂P − ∂D], 0), zincir TAM — S̃'nin ν̃ bağı
                      (f_v2, f_v2′, Denklem 12 yama dalı), r kelepçesi ve
                      f_w(g(r)) bağı dahil; hiçbir katsayı DONDURULMAZ.
        negatif dal : |c_b1(1−c_t3)Ω + 2c_w1 ν̃/d²|   (iki terim de
                      sönümleyici; bu dalın kapalı türevi zaten tamdı)

    ÖLÇÜLEN GEREKÇE (V3 kalemi; kusur parti 38'de türbülanslı düz levha
    48×64'te ölçüldü): eski köşegen yalnız DONMUŞ yok etme türevini
    (2c_w1f_wν̃/d²) taşıyordu. Tampon tabakada (χ ≈ 1,5-15) f_v2 < 0 ve
    ∂P/∂ν̃ = c_b1(S̃ + ν̃∂S̃/∂ν̃) büyük-NEGATİF olur; eksik köşegenle
    nokta-örtük çevrim Δt'den bağımsız PERİYOT-2 salınıma kilitlendi
    (ν̃[24,60]: 5,4606e-05 ↔ 7,4740e-05, genlik %37) ve çözümü kaydırdı
    (c_f/TMR 1,0271 ↔ 1,0140). Sürücünün ileri-fark vekiline karşı ölçüm:
    eski köşegenin oranı levhada 6,51'e, lüle ikizinde 5,51'e çıkıyordu;
    bu tam türev merkezî sonlu farka 20 000 rastgele durumda maks bağıl
    1,8e-08 ile oturur (bekçisi tests/cfd/test_sa_neg.py). Üretim,
    KALINTIDA açık kalır (§5.5) — köşegene giden yalnız türevinin
    sönümleyici (negatif) kısmıdır, kök değişmez (hüküm-nötrlük).

    Args:
        rho: (…,) yoğunluk [kg/m³].
        nu_tilde: (…,) ν̃ [m²/s] — negatif olabilir.
        mu: (…,) moleküler viskozite [Pa·s].
        omega: (…,) girdaplılık büyüklüğü Ω [1/s].
        d: (…,) duvar mesafesi [m], > 0.

    Returns:
        ``SASource`` — production, destruction, source, jacobian_diag
        (hepsi ρν̃ denkleminin biriminde: kg/(m·s²)).
    """
    rho = np.asarray(rho, dtype=float)
    nu_tilde = np.asarray(nu_tilde, dtype=float)
    mu = np.asarray(mu, dtype=float)
    omega = np.asarray(omega, dtype=float)
    d = np.asarray(d, dtype=float)
    if np.any(d <= 0.0):
        raise ValueError(
            'Duvar mesafesi d her hücrede pozitif olmalı (SA yok-etme '
            'terimi ν̃/d² ile ölçeklenir). Sıfır/negatif d bir GİRDİ '
            'kusurudur — sessizce kelepçelenmez.')
    # ρ ve μ KAPILARI (ÖH defter P6B2-07): d'nin kardeşleri eksikti —
    # ölçüldü (D23 once.json K9), ρ = 0 ve μ = 0 sıfıra bölümle NaN/inf
    # üretip RuntimeWarning'den başka iz bırakmadan geçiyordu (ν = μ/ρ ve
    # χ = ν̃/ν). Sonlu olmayan Ω da aynı sessiz yoldan giriyordu.
    if not np.all(np.isfinite(rho)) or np.any(rho <= 0.0):
        raise ValueError(
            'ρ her hücrede pozitif ve sonlu olmalı (ν = μ/ρ) — gelen en '
            f'küçük değer {float(np.min(rho)):.6g} kg/m³. Bu bir GİRDİ '
            'kusurudur, kelepçelenmez.')
    if not np.all(np.isfinite(mu)) or np.any(mu <= 0.0):
        raise ValueError(
            'μ her hücrede pozitif ve sonlu olmalı (χ = ν̃/ν, ν = μ/ρ) — '
            f'gelen en küçük değer {float(np.min(mu)):.6g} Pa·s. Sıfır '
            'viskozite SA kapalı-formunu tanımsız yapar; kelepçelenmez.')
    if not np.all(np.isfinite(omega)):
        raise ValueError(
            'Ω (girdaplılık büyüklüğü) her hücrede sonlu olmalı — '
            f'{int(np.count_nonzero(~np.isfinite(omega)))} hücrede NaN/inf '
            'var. Ω çağıranın hız gradyanlarından gelir; sonlu olmayan Ω '
            'üretim terimini sessizce kirletirdi.')
    if not np.all(np.isfinite(nu_tilde)):
        raise ValueError(
            'ν̃ her hücrede sonlu olmalı — '
            f'{int(np.count_nonzero(~np.isfinite(nu_tilde)))} hücrede '
            'NaN/inf var (ν̃ < 0 SERBESTTİR, modelin negatif dalıdır; '
            'sonlu olmaması ise bir GİRDİ kusurudur).')

    nu = mu / rho
    pozitif = nu_tilde >= 0.0
    nu_pos = np.maximum(nu_tilde, 0.0)
    nu_neg = np.minimum(nu_tilde, 0.0)

    s_tilde, ds_tilde = modified_vorticity(omega, nu_pos, d, nu,
                                           return_derivative=True)
    r, dr = sa_r(nu_pos, s_tilde, d, ds_tilde=ds_tilde)
    fw, dfw = f_w(r, return_derivative=True)
    inv_d2 = 1.0 / d ** 2

    uretim = np.where(
        pozitif,
        rho * SA_C_B1 * s_tilde * nu_pos,
        rho * SA_C_B1 * (1.0 - SA_C_T3) * omega * nu_neg)
    yok_etme = np.where(
        pozitif,
        rho * SA_C_W1 * fw * nu_pos ** 2 * inv_d2,
        -rho * SA_C_W1 * nu_neg ** 2 * inv_d2)
    kaynak = uretim - yok_etme

    # TAM analitik ∂(P−D)/∂(ρν̃) (birimi 1/s; ρ sabit tutulur, ∂/∂(ρν̃) =
    # (1/ρ)∂/∂ν̃ ve P, D ∝ ρ olduğundan ρ sadeleşir). Zincir docstring'de;
    # her halka kendi işlevinin return_derivative kolundan gelir (ikinci
    # değer tanımı yok, yalnız türev cebiri eklendi).
    d_uretim = SA_C_B1 * (s_tilde + nu_pos * ds_tilde)
    d_yok_etme = SA_C_W1 * (2.0 * fw * nu_pos
                            + nu_pos ** 2 * dfw * dr) * inv_d2
    turev = np.where(
        pozitif,
        d_uretim - d_yok_etme,
        SA_C_B1 * (1.0 - SA_C_T3) * omega + 2.0 * SA_C_W1 * nu_neg * inv_d2)
    return SASource(production=uretim, destruction=yok_etme, source=kaynak,
                    jacobian_diag=np.maximum(-turev, 0.0))


def sa_point_implicit_delta(dt, residual, jacobian_diag):
    """Δ(ρν̃) = Δt·R / (1 + Δt·J⁻) — yok etme nokta-örtük.

    (V/Δt + V·J⁻)Δ = V·R biçiminin hacimle sadeleşmiş hâli; ``residual``
    HACİM BAŞINA kalıntıdır (``sa_residual``ın döndürdüğü büyüklük).
    J⁻ = 0 verilirse ifade AÇIK Euler adımına iner — mutasyon bekçisi tam
    olarak bu farkı ölçer.
    """
    dt = np.asarray(dt, dtype=float)
    residual = np.asarray(residual, dtype=float)
    jacobian_diag = np.asarray(jacobian_diag, dtype=float)
    return dt * residual / (1.0 + dt * jacobian_diag)


# ---------------------------------------------------------------------------
# Sınır koşulları ve serbest-akım değeri
# ---------------------------------------------------------------------------

def freestream_nu_tilde(nu_inf, ratio=SA_FREESTREAM_CHI_BAND[0]):
    """Serbest-akım ν̃ = ratio·ν∞ — bant DIŞI oran REDDEDİLİR.

    ICCFD7-1902 Denklem 8: ν̃/ν = 3-5 (tam türbülanslı). Alt sınırın
    altına inmek f_t2'li modelde çözümü laminere düşürebilir; SA-noft2'de
    bu tuzak yoktur ama bandın kendisi standarttır ve KEYFÎ değer koşum
    beyanını yalanlar. Bu yüzden bant bir kapıdır, öneri değil.
    """
    nu_inf = float(nu_inf)
    ratio = float(ratio)
    if not np.isfinite(nu_inf) or nu_inf <= 0.0:
        raise ValueError(f'nu_inf pozitif ve sonlu olmalı — {nu_inf!r}.')
    alt, ust = SA_FREESTREAM_CHI_BAND
    if not (alt <= ratio <= ust):
        raise ValueError(
            f'Serbest-akım oranı ν̃/ν = {ratio!r} yayımlanmış bandın '
            f'[{alt}, {ust}] dışında (ICCFD7-1902 Denklem 8). Bant dışı '
            'değer koşum beyanını yalanlar; gerekiyorsa bant DEĞİŞTİRİLİP '
            'künyesi yazılmalıdır, sessizce aşılmaz.')
    return ratio * nu_inf


def sa_boundary_face_values(grid, *, inlet_nu_tilde=None, wall_nu_tilde=0.0):
    """ν̃'nin sınır YÜZ değerleri (§5.5 + §5.10).

    - duvar (j = nj): Dirichlet ν̃_w = 0 (varsayılan; ``wall_nu_tilde``
      yalnız bekçi/karşılaştırma için başka değer alabilir),
    - eksen (j = 0): ``None`` → ∂ν̃/∂n = 0 (çift) sabit-nokta süpürmesiyle
      ``sa_residual`` içinde kurulur,
    - giriş (i = 0): verilirse Dirichlet ν̃_∞, verilmezse dışdeğerleme,
    - çıkış (i = ni): daima dışdeğerleme (``None``).
    """
    duvar = np.full(grid.ni, float(wall_nu_tilde))
    giris = None
    if inlet_nu_tilde is not None:
        giris = np.broadcast_to(np.asarray(inlet_nu_tilde, dtype=float),
                                (grid.nj,)).astype(float, copy=True)
    return BoundaryFaceValues(i_lo=giris, i_hi=None, j_lo=None, j_hi=duvar)


# ---------------------------------------------------------------------------
# Taşınım
# ---------------------------------------------------------------------------

def face_mass_flux(grid, rho, uz, ur, *, grad_geom=None, bc_rho=None,
                   bc_uz=None, bc_ur=None):
    """Yüz kütle akısı ṁ = (ρ u)·S [kg/s] — SA taşınımının taşıyıcısı.

    BU BİR VEKİLDİR: sürücü kendi HLLC kütle akısını geçirebiliyorsa
    ONU geçirmelidir (o zaman SA taşınımı ortalama akışla TAM tutarlı
    olur ve düzgün alan korunumu makine sıfırındadır). Bu yardımcı,
    sürücüsüz bekçi/deney kurulumları içindir ve kullanıldığı koşum
    beyanında ``mass_flux_source`` alanıyla görünür.
    """
    if grad_geom is None:
        grad_geom = precompute_gradient_geometry(grid)
    grad_rho = green_gauss_gradient(grid, rho, bc=bc_rho, geom=grad_geom)
    grad_uz = green_gauss_gradient(grid, uz, bc=bc_uz, geom=grad_geom)
    grad_ur = green_gauss_gradient(grid, ur, bc=bc_ur, geom=grad_geom)
    rho_i, rho_j = interpolate_to_faces(grid, rho, grad_rho, bc=bc_rho,
                                        geom=grad_geom)
    uz_i, uz_j = interpolate_to_faces(grid, uz, grad_uz, bc=bc_uz,
                                      geom=grad_geom)
    ur_i, ur_j = interpolate_to_faces(grid, ur, grad_ur, bc=bc_ur,
                                      geom=grad_geom)
    mf_i = rho_i * (uz_i * grid.face_i[..., 0] + ur_i * grid.face_i[..., 1])
    mf_j = rho_j * (uz_j * grid.face_j[..., 0] + ur_j * grid.face_j[..., 1])
    return mf_i, mf_j


def _upwind_face_states(phi, bc_lo, bc_hi, axis):
    """Yüzlerin sol/sağ hücre değerleri (birinci mertebe).

    Sınır yüzünde dışarıdaki durum: BC verilmişse yüz değeri, verilmemişse
    komşu hücrenin kendisi (dışdeğerleme = sıfırıncı mertebe uzatma;
    çıkışta bu TAM DOĞRU olandır — akış dışarı gidiyorsa yukarı-akış
    zaten içeridir).
    """
    if axis == 0:
        dis_l = phi[0] if bc_lo is None else np.asarray(bc_lo, dtype=float)
        dis_r = phi[-1] if bc_hi is None else np.asarray(bc_hi, dtype=float)
        sol = np.concatenate([dis_l[None, :], phi], axis=0)
        sag = np.concatenate([phi, dis_r[None, :]], axis=0)
    else:
        dis_l = phi[:, 0] if bc_lo is None else np.asarray(bc_lo, dtype=float)
        dis_r = phi[:, -1] if bc_hi is None else np.asarray(bc_hi, dtype=float)
        sol = np.concatenate([dis_l[:, None], phi], axis=1)
        sag = np.concatenate([phi, dis_r[:, None]], axis=1)
    return sol, sag


def _muscl_face_states(phi, bc_lo, bc_hi, axis):
    """minmod sınırlı ikinci mertebe kenar durumları (sınır hücresi düz).

    Sınırlayıcı ``euler_core.minmod``tur (ikinci tanım YOK). Sınıra komşu
    hücrelerde eğim SIFIRDIR (tek yanlı fark için ikinci komşu yok):
    şema orada birinci mertebeye iner ve bu BEYANLIDIR — mertebe ölçümü
    iç bölgede yapılır.
    """
    sol, sag = _upwind_face_states(phi, bc_lo, bc_hi, axis)
    if phi.shape[axis] < 3:
        return sol, sag
    egim = np.zeros_like(phi)
    if axis == 0:
        fark = phi[1:] - phi[:-1]
        egim[1:-1] = minmod(fark[:-1], fark[1:])
        sol[1:] = phi + 0.5 * egim
        sag[:-1] = phi - 0.5 * egim
    else:
        fark = phi[:, 1:] - phi[:, :-1]
        egim[:, 1:-1] = minmod(fark[:, :-1], fark[:, 1:])
        sol[:, 1:] = phi + 0.5 * egim
        sag[:, :-1] = phi - 0.5 * egim
    return sol, sag


def sa_convective_residual(grid, nu_tilde, mass_flux_i, mass_flux_j, *,
                           bc=None, scheme='upwind1'):
    """−∮ ṁ ν̃ dS — ν̃'nin taşınım kalıntısı [kg/(m·s²)·m³ birimi hacimsiz].

    Args:
        grid: ``AxisymGrid``.
        nu_tilde: (ni, nj) ν̃ [m²/s].
        mass_flux_i: (ni+1, nj) yüz kütle akısı [kg/s], +i yönünde.
        mass_flux_j: (ni, nj+1) yüz kütle akısı [kg/s], +j yönünde.
        bc: ``BoundaryFaceValues`` — yalnız GİREN yüzlerde kullanılır.
        scheme: ``'upwind1'`` (varsayılan) | ``'muscl2'``.

    Returns:
        (ni, nj) — hücrenin HACİM İNTEGRALİ biçiminde taşınım katkısı
        [kg/(m·s²)·m³]: −Σ_dışa ṁ ν̃. İşaret kalıntıya EKLENECEK biçimdedir
        (``sa_residual`` bunu hacme böler).
    """
    if scheme not in SA_CONVECTION_SCHEMES:
        raise ValueError(
            f'scheme {scheme!r} tanımsız — geçerli şemalar '
            f'{SA_CONVECTION_SCHEMES}. Varsayılan birinci mertebedir '
            '(§5.5); ikinci mertebe İSTEĞE BAĞLIDIR ve koşum beyanında '
            'görünür.')
    nu_tilde = np.asarray(nu_tilde, dtype=float)
    if nu_tilde.shape != (grid.ni, grid.nj):
        raise ValueError(
            f'nu_tilde biçimi ({grid.ni}, {grid.nj}) olmalı — '
            f'gelen {nu_tilde.shape}.')
    mass_flux_i = np.asarray(mass_flux_i, dtype=float)
    mass_flux_j = np.asarray(mass_flux_j, dtype=float)
    if mass_flux_i.shape != (grid.ni + 1, grid.nj):
        raise ValueError(f'mass_flux_i biçimi ({grid.ni + 1}, {grid.nj}) '
                         f'olmalı — gelen {mass_flux_i.shape}.')
    if mass_flux_j.shape != (grid.ni, grid.nj + 1):
        raise ValueError(f'mass_flux_j biçimi ({grid.ni}, {grid.nj + 1}) '
                         f'olmalı — gelen {mass_flux_j.shape}.')
    if bc is None:
        bc = BoundaryFaceValues()

    durum = _muscl_face_states if scheme == 'muscl2' else _upwind_face_states
    sol_i, sag_i = durum(nu_tilde, bc.i_lo, bc.i_hi, 0)
    sol_j, sag_j = durum(nu_tilde, bc.j_lo, bc.j_hi, 1)

    aki_i = mass_flux_i * np.where(mass_flux_i >= 0.0, sol_i, sag_i)
    aki_j = mass_flux_j * np.where(mass_flux_j >= 0.0, sol_j, sag_j)
    return -((aki_i[1:] - aki_i[:-1]) + (aki_j[:, 1:] - aki_j[:, :-1]))


# ---------------------------------------------------------------------------
# Difüzyon (ICCFD7-1902 Denklem 9 — ρ türevin İÇİNE girmez)
# ---------------------------------------------------------------------------

def sa_diffusive_residual(grid, nu_tilde, rho, mu, *, bc=None, grad_geom=None,
                          grad=None, skew_iters=None, corrected=True,
                          density_correction=True):
    """SA difüzyonu + c_b2 gradyan-kare terimi + ∇ρ düzeltmesi.

    Denklem 9'un difüzyon bloğu:
        (1/σ)∇·(Γ∇ν̃) + (c_b2/σ)ρ|∇ν̃|² − (1/σ)(Γ/ρ)∇ρ·∇ν̃,   Γ = μ + ρν̃f_n

    Son terim ρ'nun türev dışına taşınmasının cebirsel bedelidir (TMR
    "Note 4"): olmadığı biçim SA değildir, çünkü yoğunluk gradyanı olan
    her yerde farklı bir denklem çözer. ``density_correction=False``
    YALNIZ bekçi/mutasyon içindir (terimin büyüklüğü ölçülür).

    Returns:
        (ni, nj) hacim İNTEGRALİ biçiminde kalıntı katkısı (akı toplamı +
        hücre kaynağı × V) — ``sa_residual`` bunu hacme böler.
    """
    if grad_geom is None:
        grad_geom = precompute_gradient_geometry(grid)
    if bc is None:
        bc = BoundaryFaceValues()
    if grad is None:
        grad = green_gauss_gradient(grid, nu_tilde, bc=bc, geom=grad_geom,
                                    skew_iters=skew_iters)

    # ρ ve μ'nün yüz değerleri: kendi (dışdeğerlemeli) gradyanlarıyla —
    # gradients.py'nin 'extrapolated' sınır kipi, beyanlı.
    grad_rho = green_gauss_gradient(grid, rho, geom=grad_geom,
                                    skew_iters=skew_iters)
    grad_mu = green_gauss_gradient(grid, mu, geom=grad_geom,
                                   skew_iters=skew_iters)
    rho_i, rho_j = interpolate_to_faces(grid, rho, grad_rho, geom=grad_geom)
    mu_i, mu_j = interpolate_to_faces(grid, mu, grad_mu, geom=grad_geom)
    nu_i, nu_j = interpolate_to_faces(grid, nu_tilde, grad, bc=bc,
                                      geom=grad_geom)

    g_i, g_j = face_gradients(grid, nu_tilde, grad=grad, bc=bc,
                              corrected=corrected, geom=grad_geom)

    gam_i = diffusion_coefficient(rho_i, nu_i, mu_i)
    gam_j = diffusion_coefficient(rho_j, nu_j, mu_j)
    aki_i = gam_i * (g_i[..., 0] * grid.face_i[..., 0]
                     + g_i[..., 1] * grid.face_i[..., 1]) / SA_SIGMA
    aki_j = np.zeros((grid.ni, grid.nj + 1), dtype=float)
    # Eksen yüzü (j = 0): dönel alan geometrik olarak SIFIR → akı tam
    # sıfır (viscous.py ile aynı desen; 0·sonlu tuzağı yok).
    aki_j[:, 1:] = gam_j[:, 1:] * (
        g_j[:, 1:, 0] * grid.face_j[:, 1:, 0]
        + g_j[:, 1:, 1] * grid.face_j[:, 1:, 1]) / SA_SIGMA

    net = (aki_i[1:] - aki_i[:-1]) + (aki_j[:, 1:] - aki_j[:, :-1])

    gam_c = diffusion_coefficient(rho, nu_tilde, mu)
    grad2 = grad[..., 0] ** 2 + grad[..., 1] ** 2
    hucre = SA_C_B2 * rho * grad2 / SA_SIGMA
    if density_correction:
        hucre = hucre - (gam_c / rho) * (
            grad_rho[..., 0] * grad[..., 0]
            + grad_rho[..., 1] * grad[..., 1]) / SA_SIGMA
    return net + hucre * grid.volume


# ---------------------------------------------------------------------------
# Toplam SA kalıntısı
# ---------------------------------------------------------------------------

def _nonphysical_sa_result(grid, gerekce, *, scheme=None,
                           density_correction=None, wall_distance_source=None,
                           mass_flux_source=None):
    """Fiziksel olmayan ortalama akış → NaN kalıntı (istisna YOK).

    aux'ün ANAHTAR KÜMESİ sağlam yoldakiyle aynıdır (yalnız değerler
    NaN): çağıran, hata yolunda ayrı bir sözlük biçimiyle karşılaşmaz.

    BİR DÜZEY ALTI DA AYNI (ÖH defter P6B2-06): ölçüldü (D23 once.json
    K8) ``declaration`` sağlam yolda 13, hata yolunda 2 anahtar
    taşıyordu — yani "anahtar kümesi aynı" iddiası ``aux``ün kendi
    düzeyinde doğru, beyanın içinde YANLIŞTI. Girdi yankısı olan alanlar
    (model, şema, sabitler, modellenmeyenler) burada da GERÇEK değerini
    taşır; ÖLÇÜM olan tek alan (``axis_neumann_update``) bu yolda
    ölçülemedi ve ``None`` kalır — sayı uydurulmaz.
    """
    def nan():
        return np.full((grid.ni, grid.nj), np.nan)

    aux = {
        'source': SASource(production=nan(), destruction=nan(), source=nan(),
                           jacobian_diag=nan()),
        'convective': nan(),
        'diffusive': nan(),
        'mu_t': nan(),
        'wall_distance_m': nan(),
        'negative_cell_count': 0,
        'declaration': {
            '_source': 'hrma.cfd.sa_neg.sa_residual',
            'nonphysical_state': gerekce,
            'model': 'SA-noft2 + negative branch (SA-neg)',
            'convection_scheme': scheme,
            'density_correction_term': (None if density_correction is None
                                        else bool(density_correction)),
            'destruction_treatment': (
                'point-implicit (diagonal = negative part of the FULL '
                'analytic d(P-D)/d(rho*nu_tilde); production derivative '
                'included, no frozen coefficients — V3)'),
            'production_treatment': 'explicit',
            'modified_vorticity_limiter': 'ICCFD7-1902 Eq. 12 (Note 1c)',
            'wall_distance_source': wall_distance_source,
            'mass_flux_source': mass_flux_source,
            'rho_mu_face_boundary_mode': 'extrapolated',
            # ÖLÇÜM: bu yolda gradyan operatörü hiç koşmadı.
            'axis_neumann_update': None,
            'constants': sa_constants(),
            'not_modelled': dict(SA_NOT_MODELLED),
            '_declaration_parity': (
                'Bu sözlüğün ANAHTAR KÜMESİ sağlam yolunkiyle aynıdır '
                '(ÖH defter P6B2-06); ölçüm olan alan (axis_neumann_update) '
                'None yayımlanır — None "ölçülmedi" demektir.'),
        },
    }
    return nan(), aux


def sa_residual(grid, U, transport, *, R, nu_tilde, omega, wall_distance=None,
                mass_flux=None, inlet_nu_tilde=None, scheme='upwind1',
                grad_geom=None, skew_iters=None, corrected=True,
                density_correction=True):
    """d(ρν̃)/dt — SA-neg kalıntısı (taşınım + difüzyon + kaynak).

    Args:
        grid: ``AxisymGrid``.
        U: (ni, nj, 4) ortalama akış korunum durumu.
        transport: ``gas_transport.GasTransport`` — μ(T) TEK kaynaktan.
        R: Özgül gaz sabiti [J/(kg·K)] (çözücünün değeri).
        nu_tilde: (ni, nj) ν̃ [m²/s] — NEGATİF OLABİLİR (modelin dalı).
        omega: (ni, nj) girdaplılık büyüklüğü Ω [1/s] — çağıran, viskoz
            kalıntının kullandığı hız gradyanlarından ``vorticity_magnitude``
            ile hesaplar. Bu modül hız gradyanını YENİDEN TANIMLAMAZ.
        wall_distance: (ni, nj) d [m]; None → ``wall_distance_field(grid)``
            (ızgaranın KENDİ duvar poliçizgisine tam mesafe).
        mass_flux: ``(ṁ_i, ṁ_j)`` demeti; None → ``face_mass_flux``
            vekiliyle kurulur ve beyanda öyle görünür.
        inlet_nu_tilde: Giriş yüzü ν̃ değeri (skaler ya da (nj,)); None →
            dışdeğerleme.
        scheme: taşınım şeması (``SA_CONVECTION_SCHEMES``).
        density_correction: Denklem 9'un ∇ρ terimi (varsayılan AÇIK;
            kapatmak SA'yı değiştirir — yalnız ölçüm/mutasyon için).

    Returns:
        (dudt, aux): dudt (ni, nj) = d(ρν̃)/dt [kg/(m·s²)]; aux sözlüğü
        kaynak parçalarını, μ_t alanını ve beyanı taşır.
    """
    ni, nj = grid.ni, grid.nj
    U = np.asarray(U, dtype=float)
    if U.shape != (ni, nj, 4):
        raise ValueError(f'U biçimi ({ni}, {nj}, 4) olmalı — {U.shape}.')
    nu_tilde = np.asarray(nu_tilde, dtype=float)
    if nu_tilde.shape != (ni, nj):
        raise ValueError(
            f'nu_tilde biçimi ({ni}, {nj}) olmalı — {nu_tilde.shape}.')
    omega = np.asarray(omega, dtype=float)
    if omega.shape != (ni, nj):
        raise ValueError(f'omega biçimi ({ni}, {nj}) olmalı — {omega.shape}.')

    gamma = float(transport.gamma)
    w = cons_to_prim_axisym(U, gamma)
    # Ω SONLULUĞU DA ÖLÇÜTE GİRER (ÖH defter P6B2-07): ν̃'nin sonluluğu
    # denetleniyordu, Ω'nınki denetlenmiyordu — ölçüldü (D23 once.json K9),
    # NaN taşıyan Ω biçim kapısından geçip kaynak terimini sessizce
    # kirletiyordu. Ω çağıranın verisidir ve ν̃ ile AYNI sınıftadır.
    if (nonphysical_state(w) or not np.all(np.isfinite(nu_tilde))
            or not np.all(np.isfinite(omega))):
        return _nonphysical_sa_result(
            grid,
            'ρ ≤ 0, p ≤ 0, sonsuz değer ya da sonlu olmayan ν̃/Ω: kalıntı '
            'NaN döndürüldü (kırpma YOK, istisna YOK — viscous.py ile ORTAK '
            'ölçüt: viscous.nonphysical_state). ν̃ < 0 bu ölçüte GİRMEZ, '
            'modelin kendi dalıdır. Sürücü bunu ıraksama olarak '
            'raporlamalıdır.',
            scheme=scheme, density_correction=density_correction,
            wall_distance_source=(
                'wall_distance.wall_distance_field(grid) — ızgara duvarı'
                if wall_distance is None else 'caller-supplied'),
            mass_flux_source=(
                'sa_neg.face_mass_flux (interpolated proxy)'
                if mass_flux is None
                else 'caller-supplied (mean-flow consistent)'))

    rho, uz, ur, p = w[..., 0], w[..., 1], w[..., 2], w[..., 3]
    T = p / (rho * float(R))
    mu = transport.viscosity(T)

    if wall_distance is None:
        d = wall_distance_field(grid)
        d_kaynak = 'wall_distance.wall_distance_field(grid) — ızgara duvarı'
    else:
        d = np.asarray(wall_distance, dtype=float)
        if d.shape != (ni, nj):
            raise ValueError(
                f'wall_distance biçimi ({ni}, {nj}) olmalı — {d.shape}.')
        d_kaynak = 'caller-supplied'

    if grad_geom is None:
        grad_geom = precompute_gradient_geometry(grid)

    bc = sa_boundary_face_values(grid, inlet_nu_tilde=inlet_nu_tilde)
    # Eksende ∂ν̃/∂n = 0 (çift): yüz değeri gradyanın KENDİSİNE bağlı
    # olduğundan sabit-nokta süpürmesi gerekir. Süpürme viscous.py'de TEK
    # kez gerçeklenmiştir (aynı Neumann yüzü, aynı teğetsel dışdeğerleme);
    # ikinci bir gerçekleme yazmak aynı sözleşmenin ikinci tanımı olurdu.
    from hrma.cfd.viscous import _gradient_with_neumann, _tangential_offset
    bc, grad, eksen_guncelleme = _gradient_with_neumann(
        grid, nu_tilde, bc, {'j_lo': _tangential_offset(grid, grad_geom,
                                                        'j_lo')},
        grad_geom, skew_iters)

    if mass_flux is None:
        mf_i, mf_j = face_mass_flux(grid, rho, uz, ur, grad_geom=grad_geom)
        mf_kaynak = 'sa_neg.face_mass_flux (interpolated proxy)'
    else:
        mf_i, mf_j = mass_flux
        mf_kaynak = 'caller-supplied (mean-flow consistent)'

    tasinim = sa_convective_residual(grid, nu_tilde, mf_i, mf_j, bc=bc,
                                     scheme=scheme)
    difuzyon = sa_diffusive_residual(
        grid, nu_tilde, rho, mu, bc=bc, grad_geom=grad_geom, grad=grad,
        skew_iters=skew_iters, corrected=corrected,
        density_correction=density_correction)
    kaynak = sa_source_terms(rho, nu_tilde, mu, omega, d)

    # Yayımlanan parçalar toplamı BİT olarak dudt'yi vermeli (aksi hâlde
    # beyan ile sayı ayrışır); bu yüzden bölme parça bazında yapılır.
    tasinim_v = tasinim / grid.volume
    difuzyon_v = difuzyon / grid.volume
    dudt = tasinim_v + difuzyon_v + kaynak.source

    aux = {
        'source': kaynak,
        'convective': tasinim_v,
        'diffusive': difuzyon_v,
        'mu_t': turbulent_viscosity(rho, nu_tilde, mu),
        'wall_distance_m': d,
        'negative_cell_count': int(np.count_nonzero(nu_tilde < 0.0)),
        'declaration': {
            '_source': 'hrma.cfd.sa_neg.sa_residual',
            'model': 'SA-noft2 + negative branch (SA-neg)',
            'convection_scheme': scheme,
            'density_correction_term': bool(density_correction),
            'destruction_treatment': (
                'point-implicit (diagonal = negative part of the FULL '
                'analytic d(P-D)/d(rho*nu_tilde); production derivative '
                'included, no frozen coefficients — V3)'),
            'production_treatment': 'explicit',
            'modified_vorticity_limiter': 'ICCFD7-1902 Eq. 12 (Note 1c)',
            'wall_distance_source': d_kaynak,
            'mass_flux_source': mf_kaynak,
            # ρ ve μ'nün YÜZ değerleri kendi gradyanlarından taşınır ve o
            # gradyanların sınır kipi dışdeğerlemedir (gradients.py'nin
            # 'extrapolated' kipi) — sessiz varsayım değil, beyan.
            'rho_mu_face_boundary_mode': 'extrapolated',
            'axis_neumann_update': eksen_guncelleme,
            'constants': sa_constants(),
            'not_modelled': dict(SA_NOT_MODELLED),
        },
    }
    return dudt, aux
