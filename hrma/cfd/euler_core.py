# hrma/cfd — 1B / 2B eksenel simetrik FVM Euler güncelleme çekirdeği
"""
Hücre-merkezli sonlu hacim Euler çekirdeği (v3 CFD, Aşama 1A).

ŞEMA (tasarım belgesi docs/mimari/cfd-tasarimi.md §2 — kararlar kesin)
----------------------------------------------------------------------
- Akı: HLLC (hrma/cfd/riemann.py; Toro 3. baskı §10.4, Einfeldt/Roe
  dalga hızları).
- İkinci mertebe: MUSCL kenar dışdeğerlemesi PRİMİTİF değişkenlerde
  (ρ, u, p) + minmod sınırlayıcı (van Leer, "Towards the ultimate
  conservative difference scheme V", JCP 32, 1979; Toro §13.4). Primitif
  rekonstrüksiyon pozitifliği korunum değişkenlerine göre daha iyi korur ve
  beyan edilir. Eğim indeks uzayında alınır (yapısal ızgara; düzgün olmayan
  aralıkta biçimsel mertebe düz ızgarada ikincidir — Aşama 1 beyanı).
- Eksenel simetri: kaynak terimli korunum formu. Dönel hücre üstünde
  integral form (2π tam çarpanlarıyla):
      d(U·V)/dt = − Σ_yüzey F̂·S + [0, 0, p·2π·A_düzlem, 0]
  Tek kaynak r-momentumdaki basınç terimidir (∂p/∂r'nin silindirik hacim
  integralinden kalan parça); kütle ve enerjiye kaynak GİRMEZ. Yüzey
  vektörleri ve hacimler grid_axisym'den TAM dönel geometriyle gelir;
  Σ S_r = 2π·A_düzlem özdeşliği sayesinde düzgün basınç alanı + durgun gaz
  TAM korunur (serbest akım koruması, ayrık özdeşlik).
- Eksen r=0: j=0 yüzlerinin alanı geometrik olarak sıfır (akısız); MUSCL
  eğimi için eksen altına AYNA hücreleri (ρ, u_z, p çift; u_r tek) konur —
  simetri sınırı budur, 0/0 muamelesi yoktur.
- Zaman: SSP-RK2 (Heun/Shu-Osher; Gottlieb & Shu, Math. Comp. 67, 1998) —
  TVD-uyumlu iki aşama. 1B sürücü zaman-doğru (Sod); 2B kararlı-hâl
  sürücüsü (steady.py) yerel Δt ile aynı kalıntıyı kullanır.

SINIR KOŞULLARI (2B; tasarım belgesi §2)
----------------------------------------
- Giriş: rezervuar (P0, T0) + iç bölgeden RIEMANN DEĞİŞMEZİ dışdeğerlemesi
  (ses-altı karakteristik sayısı 1: tek bilgi içeriden, gerisi rezervuar
  izantropiğinden; eksenel akış yönü). Dışdeğerlenen büyüklük giden C⁻
  karakteristiğinin taşıdığı J⁻ = u − 2a/(γ−1)'dir; künye ve kırılan eski
  seçimin (statik basınç dışdeğerlemesi) ölçülen kusuru
  inlet_state_from_stagnation docstring'indedir.
- Duvar: kayma (Euler) — hayalet hücrede hız duvar normaline göre
  yansıtılır; HLLC ayna durumda kütle/enerji akısını TAM sıfır, momentum
  akısını salt basınç verir.
- Çıkış: yüzey-normal Mach >= 1 ise sıfırıncı mertebe dışdeğerleme;
  ses-altıysa ve Pb verildiyse statik basınç Pb'ye bağlanır, gerisi
  dışdeğerlenir (basit ses-altı karakteristik yaklaşımı — beyanlı).
  Pb=None (tam süpersonik çıkış) olan VİSKOZ koşuda duvara komşu satırlar
  ses-altıdır ve dışdeğerleme onları ÇAPASIZ bırakır — giren
  karakteristiğe hiçbir bilgi verilmez, yani sınır koşulu orada iyi
  konumlanmamıştır ve çıkış debisi SÜRÜKLENİR (ölçüldü). İsteğe bağlı
  'core_pressure' çapası bu satırların basıncını çekirdeğe bağlar; künye,
  ölçülen zarf ve neyi ÇÖZMEDİĞİ OUTLET_ANCHOR_BASIS'te.

DÜRÜSTLÜK: pozitiflik tabanı/kırpma YOKTUR. Fiziksel olmayan durum (negatif
ρ veya p) NaN üretir; sürücü bunu ıraksama olarak raporlar (converged=False).
KAPATILAN KUSUR (ÖH defter P6B1-10; D23'te ölçüldü, ÖH D37 A3a cfd-kok-a
F-05 ile onarıldı): kayma duvarının yıldız basıncı eskiden p·(1 + γ·M_n)
biçimini alıyor ve M_n < −1/γ'da negatife geçiyordu (duvar emme uygular,
SONLU olduğu için NaN ölçütlerine takılmazdı). Artık duvar akısı iki-
genişleme (TRRS) yıldız basıncıdır: p* = p·[1 + (γ−1)M_n/2]^(2γ/(γ−1)),
vakum sınırına kadar pozitif (wall_star_pressure_trrs; Lean
HRMA.wallStarTR_pos). Akustik biçim yalnız kıyas sütunu olarak yayımlanır.
"""

import numpy as np

from hrma.cfd import kernels as _kernels
from hrma.cfd.riemann import hllc_flux

__all__ = [
    'prim_to_cons_1d', 'cons_to_prim_1d', 'minmod', 'residual_1d',
    'run_1d_transient', 'prim_to_cons_axisym', 'cons_to_prim_axisym',
    'residual_axisym', 'local_dt_axisym', 'inlet_state_from_stagnation',
    'shock_cell_weight', 'wall_star_pressure_trrs', 'SHOCK_SENSOR_MODE',
    'SHOCK_SENSOR_THRESHOLD_LOW',
    'precompute_geometry', 'SHOCK_SENSOR_THRESHOLD', 'shock_column_flag',
    'INLET_BC_NAME', 'INLET_BC_BASIS',
    'WALL_BC_MODES', 'WALL_BC_NOSLIP', 'WALL_BC_SLIP',
    'OUTLET_ANCHOR_MODES', 'OUTLET_ANCHOR_EXTRAPOLATE',
    'OUTLET_ANCHOR_CORE_PRESSURE', 'OUTLET_ANCHOR_BASIS',
    'outlet_subsonic_count',
]

_TWO_PI = 2.0 * np.pi

#: Duvar hız sınır koşulu kipleri (viskoz tasarım §5.1'in tek istisnası).
#: VARSAYILAN 'slip'tir: Euler yolu bit-özdeş kalır (bekçi
#: tests/cfd/test_euler_bit_ozdesligi.py). 'noslip' YALNIZ MUSCL hayalet
#: aynasını değiştirir; duvarın analitik akı formülü aynıdır.
WALL_BC_SLIP = 'slip'
WALL_BC_NOSLIP = 'noslip'
WALL_BC_MODES = (WALL_BC_SLIP, WALL_BC_NOSLIP)

#: Çıkış sınırında SES-ALTI hücrelerin çapası (viskoz devir kusuru #2).
#:
#: KUSURUN KENDİSİ: tam süpersonik lülede çıkış sıfırıncı mertebe
#: dışdeğerlemedir (Pb=None) — çekirdek için DOĞRUDUR (çıkan karakteristik
#: sayısı 4, giren 0). Ama duvara komşu SINIR TABAKASI hücreleri
#: ses-altıdır: orada u_n − a < 0, yani bir karakteristik dışarıdan İÇERİ
#: girer ve tam dışdeğerleme o karakteristiğe HİÇBİR bilgi vermez. Sınır
#: koşulu o satırlarda iyi konumlanmamıştır. Bu bir İYİ KONUMLANMA
#: eksiğidir ve çapa onu kapatır.
#:
#: KAPSAM DÜZELTMESİ — V1'in "limit döngüsünün kökü budur" ADAY teşhisi
#: BU PARTİDE ÖLÇÜLDÜ VE YANLIŞLANDI (bekçiler
#: tests/cfd/test_viskoz_entegrasyon.py):
#:   (1) KAPI koşusundaki 2e-05 limit döngüsünün periyodu TAM 25
#:       iterasyondur ve 25 = DEFAULT_IMPLICIT_SLOPE_REFRESH; dalga
#:       biçimi çevrimden çevrime harfi harfine tekrar ediyor. Yani
#:       salınımı üreten MUSCL eğim tazelemesidir, çıkış sınırı DEĞİL.
#:   (2) Aynı vaka, oturma-tetikli KALICI eğim dondurmasının ateşleyeceği
#:       bir oturma eşiğiyle (settle_tol 1e-4) koşulduğunda: dondurma
#:       1590. iterasyonda ateşliyor, koşu 2649 iterasyonda kalıntı
#:       9,93e-09 ile YAKINSIYOR ve çıkış debisi bandı 1,01e-05 → 4,7e-08
#:       düşüyor. Debi kökü değişmiyor (4,470615 kg/s, iki koşumda da).
#: Çapanın ölçülen etkisi ayrı ve daha küçüktür (aşağıda).
#:
#: ÇAPANIN ÖLÇÜLEN ZARFI (192×48 ve 64×16, laminer lüle μ=0,15):
#:   192×48 (sınır tabakası ~10 hücreyle çözülü): ham çıkış oturma bandı
#:       1,0081e-05 → 1,417e-06 (7,1 kat SIKILAŞTI) ve KALAN oynamanın
#:       niteliği değişti — faz-kilitli bant 4,18e-07, yani ham bandın
#:       3,4 katı altında: çapasız hâldeki SÜRÜKLENME gitti, geriye
#:       tazeleme çevrimi kaldı. Yani çapa tam da iddia ettiği şeyi
#:       yapıyor. İterasyon başına maliyeti ÖLÇÜLDÜ ve yok sayılabilir
#:       (yalnız-başına koşumda 36,615 → 36,480 ms/it).
#:   64×16 (tabaka ~3 hücre): çapa kalıntıyı 1,42e-08'den 1,64e-03'e
#:       BOZUYOR ve oturmayı hiç bırakmıyor. Sebep ölçüldü: kaba ızgarada
#:       "ilk süpersonik hücre" tabakanın KENARI değildir, dolayısıyla
#:       dayatılan basınç yanlış bir değerdir.
#: Yani çapa ÇÖZÜLMÜŞ sınır tabakası ister. VARSAYILAN bu yüzden
#: değiştirilmedi: çağıran açar, koşum ``outlet_bc`` bloğunda hem kipi
#: hem ses-altı hücre sayısını beyan eder.
#:
#: 'extrapolate' (VARSAYILAN): bugünkü davranış, HARFİ HARFİNE.
#:
#: BİT-ÖZDEŞLİK KAPSAMI (ÖH D18 / P6B1-02 — eski beyan DÜZELTİLDİ). Burada
#: eskiden "Euler yolunun bit-özdeşlik sözleşmesi (§11.3) bu dalın üstünde
#: durur" yazıyordu; ÖLÇÜM bunu çürüttü: §11.3'ün dört referans vakasının
#: DÖRDÜ de ``Pb`` VERİLMİŞ koşumdur (tests/cfd/conftest.py), dolayısıyla
#: ``_outlet_state``in ``Pb is None`` dalı — yani ürün ucunun VARSAYILANI —
#: dondurmanın DIŞINDAYDI. Dal bilerek bozulduğunda (hayalete 1e-6 bağıl
#: basınç sıçraması) dört bekçi de bit-YEŞİL kalıyordu; kanıt
#: docs/scofield/raw/OH/D18/fea-cfd/a1/mutasyon_p6b1_02.json (mutasyonlu
#: eski bekçiler: 17 passed).
#: Kapsam D18'de KAPATILDI: donmuş dört durumun ``Pb=None`` ile alınan
#: kalıntısı ayrıca donduruldu
#: (``data/cfd_referans/euler_pb_none_kalinti.npz``, üreteci
#: ``tools/cfd_referans_dondur.py --pb-none``, bekçisi
#: ``test_euler_bit_ozdesligi.py::test_pb_none_dali_BIT_ozdes``). Aynı
#: mutasyon artık 4 vakada da KIRMIZI.
#: Hâlâ dondurmanın dışında kalan ve BEYANLI opt-in oldukları için bulgu
#: sayılmayan yollar: ``core_pressure`` çapası (aşağıda), ``wall_bc=
#: 'noslip'``, ``time_integrator='line_implicit_j'``, ``second_order=
#: False``, ``viscous is not None``, ``initial_state`` verilmiş koşu.
#:
#: 'core_pressure': ses-altı alt tabakanın statik basıncı, AYNI çıkış
#: kolonundaki en yakın SÜPERSONİK (çekirdek) hücrenin basıncına bağlanır
#: — yani sınır tabakası boyunca radyal basınç dengesi (∂p/∂n ≈ 0)
#: dayatılır. Ses-altı çıkışta imlenmesi gereken büyüklük sayısı tam
#: 1'dir (giren tek karakteristik u_n − a) ve o büyüklük STATİK BASINÇTIR;
#: geri kalan (ρ, u_z, u_r) dışdeğerlenir — standart ses-altı çıkış
#: sayımı. Çapanın DEĞERİ uydurulmaz: çözümün kendi çekirdeğinden gelir,
#: çekirdek ise yalnız yukarı akıştan belirlenir (süpersonik). Yeni
#: sabit YOKTUR.
#: Pb VERİLMİŞ ses-altı çıkışta hayaletin ρ,u'su karakteristik uyumlulukla
#: mı (True) yoksa iç değerin kopyası mı (False, 2026-08-15 biçimi)?
#: Ayrıştırma deneyi anahtarı (ÖH D37 A3a cfd-kok-a, OH-DK-13); varsayılan
#: ve gerekçesi ölçümle belirlenir (kulvar raporu §B2).
OUTLET_PB_CHARACTERISTIC = False

OUTLET_ANCHOR_EXTRAPOLATE = 'extrapolate'
OUTLET_ANCHOR_CORE_PRESSURE = 'core_pressure'
OUTLET_ANCHOR_MODES = (OUTLET_ANCHOR_EXTRAPOLATE, OUTLET_ANCHOR_CORE_PRESSURE)

#: Çapanın literatür gerekçesi (koşum çıktısında yayımlanır).
OUTLET_ANCHOR_BASIS = (
    'Ses-altı çıkış alt tabakası çapası. Prandtl sınır tabakası '
    'yaklaşımının BİRİNCİ sonucu, tabaka boyunca duvar-normal basınç '
    'gradyanının mertebe olarak ihmal edilebilir olmasıdır: ∂p/∂n = '
    'O(δ/R)·∂p/∂s (Schlichting & Gersten, "Boundary-Layer Theory", 9. '
    'baskı, sınır tabakası denklemlerinin kuruluşu; eksenel simetrik '
    'biçimde enine eğrilik düzeltmesi aynı mertebe tahminini korur). '
    'Yani sınır tabakası kendi içinde bir basınç farkı TAŞIYAMAZ; çıkış '
    'düzleminde ses-altı alt tabakanın statik basıncı, tabakanın '
    'KENARINDAKİ (ilk süpersonik hücre) basınçtır. Ses-altı çıkışta '
    'imlenmesi gereken büyüklük sayısı da tam 1\'dir (giren tek '
    'karakteristik u_n − a) ve o büyüklük statik basınçtır; ρ ve u ise '
    'giden dalgaların uyumluluk bağıntılarından türetilir (Blazek, '
    '"Computational Fluid Dynamics: Principles and Applications", 2. '
    'baskı, sınır koşulları bölümü, ses-altı çıkış). Çapa değeri '
    'ÇÖZÜMÜN KENDİSİNDEN okunur (çekirdek süpersoniktir, yani yalnız '
    'yukarı akıştan belirlenir) — uydurma sabit yoktur. Kapsam: yalnız '
    'Pb=None (tam dışdeğerleme) çıkışında anlamlıdır; Pb verildiğinde '
    'ses-altı hücreler zaten Pb\'ye bağlanır.')

# Şok sensörü — HÜCRE bazlı Jameson-Schmidt-Turkel basınç anahtarı
# (ÖH D37 A3a cfd-kok-a, OH-DK-14 onarımı; Jameson, Schmidt, Turkel, AIAA
# 81-1259 (1981) §4 "pressure switch"; Blazek 2. bs. §4.3.1):
#     ν_i = |p_{i+1} − 2p_i + p_{i−1}| / (p_{i+1} + 2p_i + p_{i−1})
# ve aynısı j yönünde. Bayrak YALNIZ SIKIŞMADA (akış yönünde basınç artıyor:
# sign(u)·(p_{+1} − p_{−1}) > 0) ve ν > eşik olan HÜCREDE kalkar; ±1 hücre
# genişletilir (i ve j). Eşik ÖLÇÜMDEN (DK kampanyası ÖNCE alanları, 17
# koşum; docs/scofield/raw/OH/A3a/cfd-kok-a/olcut_kulvar.json):
#   şoksuz sıkışma ν maks : 0,0201 (C7 240×48), 0,0024 (C7 standard),
#                           0,0003 (C1 240×48), 0,0000 (C3 384×96)
#   şok hücresi ν maks    : 0,2315 (C2b 30×6 — en zayıf), 0,38-0,51 (diğerleri)
# Boşluk 11,5 kat; eşik 0,08 = şoksuz maksimumun 4 katı, en zayıf şokun
# 2,9'da biri. ESKİ sensör (kolon bazlı, işaretsiz |Δp|/min p > 0,25) şoksuz
# GENİŞLEMEDE ateşliyordu — Back ıraksak konisi (0,33) ve motor lülesinin
# Rao boğazı (0,44-0,49) eşiğin ÜSTÜNDEYDİ, yani hiçbir eşik ayıramazdı;
# ikinci fark O(h²) ile normalize edilir ve işaret koşulu genişlemeyi
# tanım gereği dışlar (OH-DK-14: tetikleyen yüzlerin hepsi genişlemeydi).
SHOCK_SENSOR_THRESHOLD = 0.08

#: SÜREKLİ AĞIRLIK (ÖLÇÜLDÜ, ayrıştırma deneyi 120×24 C2 γ = 1,4 — docs/
#: scofield/raw/OH/A3a/cfd-kok-a/ayristirma/): ikili (aç/kapa) hücre bayrağı
#: şok yerine oturdukça eşik sınırındaki hücrelerde ANAHTARLANIYOR ve ṁ'yi
#: %5 bantlı limit döngüsüne kilitliyordu (T2: canlı ikili sensör,
#: dondurmasız → not_converged, bant 5,2e-2); birinci mertebe aynı vakada
#: 22544 iterasyonda yakınsıyor. Jameson'ın özgün anahtarı da SÜREKLİDİR
#: (ε₂ = κ₂·ν, katsayı ν ile doğrusal). Burada eğim çarpanı
#:     φ(ν) = clamp((θ − ν)/(θ − θ_alt), 0, 1),   θ_alt = θ/2
#: ν ≤ θ_alt'ta TAM 1 (çarpım bit-özdeş, sensörsüz yolla aynı), ν ≥ θ'da
#: 0 (birinci mertebe), arada doğrusal — durumsuz, anahtarlama yok. ν
#: komşuluk maksimumuyla alınır (3×3, "±1 hücre genişletme"nin sürekli
#: karşılığı). Şoksuz sıkışma maks 0,0201 < θ_alt = 0,04 (pay 2×) → şoksuz
#: alanlarda çarpan her yerde 1.
SHOCK_SENSOR_THRESHOLD_LOW = 0.04

#: Sensör kipi — TEK KAYNAK. 'cell' (varsayılan, yukarıdaki JST hücre
#: sensörü) | 'column' (2026-08-15 kolon sensörü; yalnız ayrıştırma
#: deneyleri ve kıyas ölçümü için durur, ürün yolu kullanmaz).
SHOCK_SENSOR_MODE = 'cell'
SHOCK_SENSOR_MODES = ('cell', 'column')


# --------------------------------------------------------------------------
# Durum dönüşümleri
# --------------------------------------------------------------------------

def prim_to_cons_1d(rho, u, p, gamma):
    """(ρ, u, p) → U = [ρ, ρu, E], E = p/(γ−1) + ρu²/2. Şekil: (n, 3)."""
    rho = np.asarray(rho, dtype=float)
    u = np.asarray(u, dtype=float)
    p = np.asarray(p, dtype=float)
    e = p / (float(gamma) - 1.0) + 0.5 * rho * u * u
    return np.stack([rho, rho * u, e], axis=-1)


def cons_to_prim_1d(U, gamma):
    """U = [ρ, ρu, E] → (ρ, u, p). Kırpma yok: bozuk durum NaN üretir."""
    rho = U[..., 0]
    u = U[..., 1] / rho
    p = (float(gamma) - 1.0) * (U[..., 2] - 0.5 * rho * u * u)
    return rho, u, p


def prim_to_cons_axisym(rho, uz, ur, p, gamma):
    """(ρ, u_z, u_r, p) → U = [ρ, ρu_z, ρu_r, E]."""
    rho = np.asarray(rho, dtype=float)
    uz = np.asarray(uz, dtype=float)
    ur = np.asarray(ur, dtype=float)
    p = np.asarray(p, dtype=float)
    e = p / (float(gamma) - 1.0) + 0.5 * rho * (uz * uz + ur * ur)
    return np.stack([rho, rho * uz, rho * ur, e], axis=-1)


def cons_to_prim_axisym(U, gamma):
    """U → W = [ρ, u_z, u_r, p] (aynı şekil, son eksen 4)."""
    rho = U[..., 0]
    uz = U[..., 1] / rho
    ur = U[..., 2] / rho
    p = (float(gamma) - 1.0) * (U[..., 3]
                                - 0.5 * rho * (uz * uz + ur * ur))
    return np.stack([rho, uz, ur, p], axis=-1)


def minmod(a, b):
    """minmod sınırlayıcı: işaretler aynıysa mutlakça küçüğü, değilse 0."""
    return 0.5 * (np.sign(a) + np.sign(b)) * np.minimum(np.abs(a),
                                                        np.abs(b))


def limited_slopes(w_ext):
    """2 hayalet katmanlı dizide minmod eğimleri (0. eksen boyunca).

    w_ext: (n+4, ..., nvar) → eğimler (n+2, ..., nvar) (ext hücre 1..n+2).
    """
    d = w_ext[1:] - w_ext[:-1]
    return minmod(d[:-1], d[1:])


def _edge_states(w_ext, slopes):
    """MUSCL kenar durumları; slopes=None → birinci mertebe.

    w_ext: (n+4, ..., nvar). Döner: (W_L, W_R), her biri (n+1, ..., nvar) —
    n+1 yüzün sol/sağ durumları.
    """
    if slopes is None:
        return w_ext[1:-2], w_ext[2:-1]
    return (w_ext[1:-2] + 0.5 * slopes[:-1],
            w_ext[2:-1] - 0.5 * slopes[1:])


# --------------------------------------------------------------------------
# 1B çekirdek (Sod merdiveni — basamak 1)
# --------------------------------------------------------------------------

def residual_1d(U, dx, gamma, second_order=True):
    """1B Euler dU/dt — geçirgen (transmissive) sınırlar, düzgün dx."""
    rho, u, p = cons_to_prim_1d(U, gamma)
    w = np.stack([rho, u, p], axis=-1)
    w_ext = np.concatenate([w[:1], w[:1], w, w[-1:], w[-1:]], axis=0)
    w_l, w_r = _edge_states(w_ext,
                            limited_slopes(w_ext) if second_order else None)
    zeros = np.zeros_like(w_l[..., 0])
    f_rho, f_mn, _, f_e = hllc_flux(
        w_l[..., 0], w_l[..., 1], zeros, w_l[..., 2],
        w_r[..., 0], w_r[..., 1], zeros, w_r[..., 2], gamma)
    flux = np.stack([f_rho, f_mn, f_e], axis=-1)      # (n+1, 3)
    return -(flux[1:] - flux[:-1]) / float(dx)


def run_1d_transient(U0, dx, gamma, t_end, cfl=0.8, second_order=True):
    """Zaman-doğru 1B koşum: SSP-RK2, global Δt (CFL), t_end'e tam varış."""
    U = np.array(U0, dtype=float, copy=True)
    g = float(gamma)
    t = 0.0
    t_end = float(t_end)
    while t < t_end:
        rho, u, p = cons_to_prim_1d(U, g)
        a = np.sqrt(g * p / rho)
        dt = float(cfl) * float(dx) / float(np.max(np.abs(u) + a))
        dt = min(dt, t_end - t)
        u1 = U + dt * residual_1d(U, dx, g, second_order)
        U = 0.5 * (U + u1 + dt * residual_1d(u1, dx, g, second_order))
        if not np.all(np.isfinite(U)):
            raise FloatingPointError(
                f'1B çekirdek t={t:.5f} adımında fiziksel olmayan duruma '
                f'düştü (NaN/Inf) — kırpma yok, dürüst hata.')
        t += dt
    return U


# --------------------------------------------------------------------------
# 2B eksenel simetrik sınır durumları
# --------------------------------------------------------------------------

#: Giriş sınır koşulunun künyeli yöntem beyanı (sonuç sözlüğüne taşınır).
INLET_BC_NAME = 'characteristic_reservoir'
INLET_BC_BASIS = (
    'Giriş: KARAKTERİSTİK (Riemann-değişmezi) ses-altı rezervuar sınır '
    'koşulu. Ses-altı girişte üç karakteristikten yalnız biri hesap '
    'alanından ÇIKAR (C⁻: dz/dt = u − a < 0); taşıdığı değişmez '
    'J⁻ = u − 2a/(γ−1) iç hücreden dışdeğerlenir, kalan iki koşul '
    'rezervuardan gelir (durma entalpisi h0 = a0²/(γ−1) ve entropi, yani '
    'p/ρ^γ = P0/ρ0^γ) — akış yönü eksenel (giriş yüzü z=sabit istasyonu '
    'olduğundan yüzey normali +z; u_r = 0 dayatılır). Künye: Blazek, '
    '"Computational Fluid Dynamics: Principles and Applications", 3. baskı '
    '§8.4 (ses-altı giriş, verilen durma büyüklükleri); özgün türetim '
    'Whitfield & Janus, AIAA-84-1552 (1984). ESKİ SEÇİMİN ÖLÇÜLEN KUSURU: '
    'iç hücreden STATİK BASINÇ dışdeğerlenip Mach izantropik p→M '
    'bağıntısından çözülüyordu; o eşlemenin türevi dM/d(p/P0) = −1/(γM) '
    'olduğundan M→0\'da dikleşir ve iç basınç gürültüsünü giriş debisine '
    '1/(γM²) kazancıyla yansıtır (ÖLÇÜLDÜ, γ=1,2 / M=0,061: kazanç −224; '
    'karakteristik biçimde −77). Sonuç: yüksek daralma oranlı gerçek motor '
    'konturlarında kalıntının ~%99\'u i=0,1,2 giriş kolonlarında toplanıp '
    'koşu oturmuyordu (ölçüm tablosu tests/cfd/test_giris_bc.py).')

#: Riemann değişmezinin FİZİKSEL bandı (uydurma sabit değil): rezervuar
#: izantropu üstünde J⁻ = u − 2a/(γ−1), gaz DURGUNken (u=0, a=a0)
#: −2a0/(γ−1) değerini, VAKUMA tam genleşmede (a=0, u=u_maks) ise
#: +a0·√(2/(γ−1)) değerini alır. Bant dışı bir J⁻, iç durumun rezervuardan
#: daha yüksek durma entalpisine sahip olması (ya da güçlü geri akış)
#: demektir; o hâlde ikinci derece denklemin diskriminantı da negatife
#: geçerdi. Bant, eski biçimdeki [p_sonik, P0) kırpmasının muadilidir ve
#: aynı ruhla BEYANLIDIR. Yakınsayan koşularda ETKİN OLMADIĞI ölçülür
#: (bekçi: tests/cfd/test_giris_bc.py::test_riemann_bandi_etkin_degil).


def inlet_state_from_stagnation(w_int, gamma, R, P0, T0):
    """Rezervuar giriş hayalet durumu — karakteristik biçim (INLET_BC_BASIS).

    Ses-altı girişte tek giden karakteristik C⁻'dir; onun değişmezi
    J⁻ = u − 2a/(γ−1) İÇERİDEN dışdeğerlenir. Rezervuardan gelen iki koşul
    (durma entalpisi + entropi) ile birleştirilince sınır ses hızı a_b
    ikinci derece bir denklemin pozitif kökü olur:

        h0 = a_b²/(γ−1) + u_b²/2,   u_b = J⁻ + 2a_b/(γ−1)
        ⇒ a_b = (γ−1)/(γ+1)·[ −J⁻ + √( (γ+1)/(γ−1)·a0² − (γ−1)/2·J⁻² ) ]

    (Blazek §8.4'ün akış açısı θ=0 hâli; burada giriş yüzü z=sabit
    istasyonu olduğundan θ=0 geometrik gerçektir, varsayım değildir.)
    Ardından T_b = a_b²/(γR), p_b = P0·(T_b/T0)^{γ/(γ−1)} (izantrop),
    ρ_b = p_b/(R·T_b), u_r = 0.

    Args:
        w_int: iç ilk hücre primitifleri (nj, 4) = [ρ, u_z, u_r, p].
        gamma, R: kalorik mükemmel gaz sabitleri.
        P0, T0: rezervuar durma basıncı [Pa] ve sıcaklığı [K].

    Returns:
        (nj, 4) hayalet primitif — eksenel akış, (P0, T0) izantropu üstünde.

    Not: J⁻ fiziksel banda kırpılır (bandın gerekçesi yukarıdaki blokta;
    durgun rezervuar ↔ vakuma genleşme uçları). Kırpma yakınsayan koşularda
    ETKİN DEĞİLDİR ve bu ölçülür; pozitiflik tabanı ya da uydurma yedek
    DEĞİLDİR (modül docstring'indeki dürüstlük çıtası korunur: sınır
    durumu her zaman rezervuar izantropu üstünde ve sonludur).
    """
    g = float(gamma)
    a0 = np.sqrt(g * float(R) * float(T0))          # rezervuar ses hızı
    k = 2.0 / (g - 1.0)
    a_int = np.sqrt(g * w_int[..., 3] / w_int[..., 0])
    j_minus = w_int[..., 1] - k * a_int             # giden C⁻ değişmezi
    j_min = -k * a0                                 # durgun rezervuar ucu
    j_max = a0 * np.sqrt(2.0 / (g - 1.0))           # vakuma genleşme ucu
    j_minus = np.clip(j_minus, j_min, j_max)
    disc = (g + 1.0) / (g - 1.0) * a0 * a0 - 0.5 * (g - 1.0) * j_minus ** 2
    a_b = (g - 1.0) / (g + 1.0) * (-j_minus + np.sqrt(disc))
    u_b = j_minus + k * a_b
    temp = a_b * a_b / (g * float(R))
    p = float(P0) * (temp / float(T0)) ** (g / (g - 1.0))
    out = np.empty_like(w_int)
    out[..., 0] = p / (float(R) * temp)
    out[..., 1] = u_b
    out[..., 2] = 0.0
    out[..., 3] = p
    return out


def _outlet_normal_mach(w_int, n_hat, gamma):
    """Çıkış yüzü normal Mach'ı (tek gerçekleme: çapa da beyan da bunu kullanır)."""
    a = np.sqrt(float(gamma) * w_int[..., 3] / w_int[..., 0])
    un = w_int[..., 1] * n_hat[..., 0] + w_int[..., 2] * n_hat[..., 1]
    return un / a


def outlet_subsonic_count(w_int, n_hat, gamma):
    """Çıkış kolonundaki ses-altı hücre sayısı (beyan için; hüküm değil).

    Kusurun VARLIĞINI ölçen sayıdır: Pb=None çıkışında bu sayı sıfırdan
    büyükse alt tabaka çapasızdır (OUTLET_ANCHOR_BASIS). Sürücü bunu
    yayımlar ki "sessizce yanlış" durum görünür olsun.
    """
    return int(np.sum(_outlet_normal_mach(w_int, n_hat, gamma) < 1.0))


def _outlet_state(w_int, n_hat, gamma, Pb,
                  subsonic_anchor=OUTLET_ANCHOR_EXTRAPOLATE):
    """Çıkış hayaleti: normal Mach >= 1 → dışdeğerleme; ses-altı ve Pb
    verildiyse statik basınç Pb (gerisi dışdeğer).

    ``subsonic_anchor='core_pressure'`` ve ``Pb is None`` iken ses-altı
    hücrelerin basıncı, AYNI kolonda eksene doğru en yakın süpersonik
    hücrenin basıncına bağlanır (radyal basınç dengesi; gerekçe ve künye
    OUTLET_ANCHOR_BASIS). Kolonda hiç süpersonik hücre yoksa çapa
    UYGULANMAZ (uydurma değer yerine bugünkü dışdeğerleme sürer; sürücü
    bunu beyan eder).
    """
    if subsonic_anchor not in OUTLET_ANCHOR_MODES:
        raise ValueError(
            f'subsonic_anchor {subsonic_anchor!r} tanımsız — geçerli kipler '
            f'{OUTLET_ANCHOR_MODES}. Varsayılan '
            f'{OUTLET_ANCHOR_EXTRAPOLATE!r} bugünkü (bit-özdeş) daldır.')
    out = np.array(w_int, copy=True)
    if Pb is None:
        if subsonic_anchor == OUTLET_ANCHOR_EXTRAPOLATE:
            return out                  # BUGÜNKÜ YOL — harfi harfine
        g = float(gamma)
        mach_n = _outlet_normal_mach(w_int, n_hat, g)
        subsonic = mach_n < 1.0
        # Tabaka KENARI: j ekseninde (eksen → duvar) "bu hücreye kadarki
        # SON süpersonik indis". Kolonun içindeki ses-altı cepler de
        # (varsa) kendilerine eksene doğru en yakın süpersonik komşunun
        # basıncını alır; hiç süpersonik yoksa indis −1 kalır ve çapa
        # uygulanmaz (aşağıdaki `gecerli` maskesi).
        idx = np.arange(w_int.shape[-2])
        son_sup = np.maximum.accumulate(
            np.where(~subsonic, idx, -1), axis=-1)
        uygula = subsonic & (son_sup >= 0)
        p_kenar = np.take_along_axis(
            w_int[..., 3], np.maximum(son_sup, 0), axis=-1)
        # KARAKTERİSTİK-TUTARLI ses-altı çıkış (Blazek, "Computational
        # Fluid Dynamics: Principles and Applications", 2. baskı, §8.4):
        # basınç imlenirken ρ ve u SERBEST BIRAKILMAZ, giden dalgaların
        # uyumluluk bağıntılarından türetilir —
        #     ρ_b = ρ_i + (p_b − p_i)/c_i²      (giden ENTROPİ dalgası)
        #     u_b = u_i + n̂·(p_i − p_b)/(ρ_i c_i)  (giden AKUSTİK dalga)
        # Yalnız p'yi değiştirip ρ,u'yu iç değerde bırakmak hayalete
        # sahte bir entropi/hız sıçraması yazar; ÖLÇÜLDÜ (64×16 viskoz
        # lüle, μ=0,15): tutarsız biçimde kalıntı 1,4e-08 → 4,8e-04'e
        # BOZULDU, tutarlı biçimde bozulma yok. Bu, uydurma bir düzeltme
        # değil sınır koşulunun doğru yazılmasıdır.
        c_i = np.sqrt(g * w_int[..., 3] / w_int[..., 0])
        dp = p_kenar - w_int[..., 3]
        rho_b = w_int[..., 0] + dp / (c_i * c_i)
        katsayi = -dp / (w_int[..., 0] * c_i)
        out[..., 0] = np.where(uygula, rho_b, out[..., 0])
        out[..., 1] = np.where(uygula,
                               w_int[..., 1] + katsayi * n_hat[..., 0],
                               out[..., 1])
        out[..., 2] = np.where(uygula,
                               w_int[..., 2] + katsayi * n_hat[..., 1],
                               out[..., 2])
        out[..., 3] = np.where(uygula, p_kenar, out[..., 3])
        return out
    g = float(gamma)
    a = np.sqrt(g * w_int[..., 3] / w_int[..., 0])
    un = w_int[..., 1] * n_hat[..., 0] + w_int[..., 2] * n_hat[..., 1]
    subsonic = un / a < 1.0
    if OUTLET_PB_CHARACTERISTIC:
        # KARAKTERİSTİK-TUTARLI Pb çıkışı (Blazek 2. bs. §8.4, ses-altı
        # çıkış): basınç imlenirken ρ ve u giden dalgaların uyumluluk
        # bağıntılarından —
        #     ρ_b = ρ_i + (p_b − p_i)/c_i²,  u_b = u_i + n̂·(p_i − p_b)/(ρ_i c_i)
        # (yukarıdaki Pb=None çapa dalıyla AYNI biçim). Ölçülen gerekçe
        # OUTLET_PB_CHARACTERISTIC tanımında.
        dp = float(Pb) - w_int[..., 3]
        rho_b = w_int[..., 0] + dp / (a * a)
        katsayi = -dp / (w_int[..., 0] * a)
        out[..., 0] = np.where(subsonic, rho_b, out[..., 0])
        out[..., 1] = np.where(subsonic, w_int[..., 1] + katsayi * n_hat[..., 0],
                               out[..., 1])
        out[..., 2] = np.where(subsonic, w_int[..., 2] + katsayi * n_hat[..., 1],
                               out[..., 2])
    out[..., 3] = np.where(subsonic, float(Pb), out[..., 3])
    return out


def _mirror_axis(w_cells):
    """Eksen aynası: ρ, u_z, p çift; u_r tek (işaret değiştirir)."""
    out = np.array(w_cells, copy=True)
    out[..., 2] = -out[..., 2]
    return out


def _mirror_wall(w_cells, n_hat, wall_bc=WALL_BC_SLIP):
    """Duvar aynası: kayma → normal bileşen, kaymaz → İKİ bileşen yansır.

    ``wall_bc='slip'`` (varsayılan) dalı bugünkü Euler kodudur: yalnız
    duvar-normal hız işaret değiştirir, teğet hız korunur. ``'noslip'``
    dalı viskoz koşunun MUSCL hayaletidir (viskoz tasarım §5.1'in tek
    istisnası): duvarda hız sıfıra gittiğinden hayalet TAM yansımadır
    (u_hayalet = −u_iç, iki bileşen birden), böylece duvar yüzüne
    rekonstrüksiyon teğet hızı sıfıra taşır.

    Duvarın ANALİTİK akısı bu seçimden bağımsızdır: kalıntı duvar yüzünde
    akıyı [0, p*·n̂·|S|, 0] olarak kurar ve p* yalnız (ρ, u_n, p) üçlüsüne
    bağlıdır — teğet hız HLLC'de pasif taşınır. Yani no-slip'e geçmek
    çekirdeğin duvar akı FORMÜLÜNÜ geçersiz kılmaz (§5.1, madde 2);
    değişen tek şey duvara komşu hücrelerin MUSCL eğimidir.
    """
    out = np.array(w_cells, copy=True)
    if wall_bc == WALL_BC_NOSLIP:
        out[..., 1] = -w_cells[..., 1]
        out[..., 2] = -w_cells[..., 2]
        return out
    vn = (w_cells[..., 1] * n_hat[..., 0]
          + w_cells[..., 2] * n_hat[..., 1])
    out[..., 1] = w_cells[..., 1] - 2.0 * vn * n_hat[..., 0]
    out[..., 2] = w_cells[..., 2] - 2.0 * vn * n_hat[..., 1]
    return out


def _unit_normals(face_vec):
    """Yüzey vektörlerinden (birim normal, alan) — sıfır alanlı yüz
    (eksen) güvenli: normal (0,1) atanır, akı zaten alanla çarpılıp
    sıfırlanır."""
    area = np.linalg.norm(face_vec, axis=-1)
    safe = np.where(area > 0.0, area, 1.0)[..., None]
    n_hat = face_vec / safe
    n_hat = np.where(area[..., None] > 0.0, n_hat,
                     np.array([0.0, 1.0]))
    return n_hat, area


def shock_column_flag(p_cells):
    """Şok sensörü kolon bayrağı: (ni, nj) basınç alanı → (ni,) bool | None.

    Eksenel yüzdeki bağıl sıçrama |Δp|/min(p) > SHOCK_SENSOR_THRESHOLD olan
    yüzün İKİ komşu kolonu + 1 kolon genişletme (dilatasyon). Hiçbir yüz
    tetiklenmezse None (pürüzsüz akış — çağıran hiçbir eğime dokunmaz,
    sonuç sensörsüz yolla bit-özdeş). Kolon-bazlılık ve eşik gerekçeleri
    residual_axisym docstring + SHOCK_SENSOR_THRESHOLD tanımı yanındadır.
    steady.py aynı fonksiyonla son alandan beyan sayısını üretir (donmuş
    eğimli bütçe çağrısında sensör bloğu atlandığından oradan alınamaz).
    """
    dp_rel = (np.abs(p_cells[1:] - p_cells[:-1])
              / np.minimum(p_cells[1:], p_cells[:-1]))      # (ni-1, nj)
    face_col = np.any(dp_rel > SHOCK_SENSOR_THRESHOLD, axis=1)  # (ni-1,)
    if not np.any(face_col):
        return None
    col = np.zeros(p_cells.shape[0], dtype=bool)
    col[:-1] |= face_col
    col[1:] |= face_col
    grown = col.copy()
    grown[:-1] |= col[1:]
    grown[1:] |= col[:-1]
    return grown


def shock_cell_weight(p_ext_i, p_ext_j, uz, ur, threshold=None,
                      threshold_low=None):
    """JST hücre sensörü — eğim ÇARPANI (ni, nj) ∈ [0, 1] | None (pürüzsüz).

    Args:
        p_ext_i: (ni+4, nj) basınç, i yönünde 2 hayalet katmanlı
            (residual_axisym'in ``w_ext_i[..., 3]``ü).
        p_ext_j: (nj+4, ni) basınç, j yönünde 2 hayalet katmanlı
            (``w_ext_j[..., 3]``; eksen 0 = j).
        uz, ur: (ni, nj) hücre hızları — sıkışma İŞARETİ için.
        threshold, threshold_low: None → SHOCK_SENSOR_THRESHOLD(_LOW).

    ν = |p₊ − 2p₀ + p₋| / (p₊ + 2p₀ + p₋) (Jameson-Schmidt-Turkel 1981), i
    ve j yönünde, yalnız SIKIŞMADA (aksi yönde 0); hücre değeri ikisinin
    büyüğü; sonra 3×3 komşuluk MAKSİMUMU (oturan şok azaltılmış bölgenin
    içinde kalsın; şok profilinin orta hücresinde ikinci fark küçüktür,
    komşular kapatır). Çarpan φ = clamp((θ − ν)/(θ − θ_alt), 0, 1). Her
    hücrede ν ≤ θ_alt ise None döner: çağıran eğime DOKUNMAZ (sensörsüz
    yolla bit-özdeş). Gerekçe ve ölçüm SHOCK_SENSOR_THRESHOLD(_LOW) yanında.
    """
    esik = SHOCK_SENSOR_THRESHOLD if threshold is None else float(threshold)
    alt = (SHOCK_SENSOR_THRESHOLD_LOW if threshold_low is None
           else float(threshold_low))
    if not (0.0 <= alt < esik):
        raise ValueError(f'0 ≤ θ_alt < θ olmalı; gelen {alt}, {esik}')
    pi_m, pi_0, pi_p = p_ext_i[1:-3], p_ext_i[2:-2], p_ext_i[3:-1]
    nu_i = np.abs(pi_p - 2.0 * pi_0 + pi_m) / (pi_p + 2.0 * pi_0 + pi_m)
    nu_i = np.where((pi_p - pi_m) * np.sign(uz) > 0.0, nu_i, 0.0)
    pj_m, pj_0, pj_p = p_ext_j[1:-3], p_ext_j[2:-2], p_ext_j[3:-1]
    nu_j = (np.abs(pj_p - 2.0 * pj_0 + pj_m)
            / (pj_p + 2.0 * pj_0 + pj_m)).T                    # (ni, nj)
    nu_j = np.where((pj_p - pj_m).T * np.sign(ur) > 0.0, nu_j, 0.0)
    nu = np.maximum(nu_i, nu_j)
    if not np.any(nu > alt):
        return None
    # 3×3 komşuluk maksimumu (kenarlarda kırpılmış)
    g = nu.copy()
    g[:-1] = np.maximum(g[:-1], nu[1:])
    g[1:] = np.maximum(g[1:], nu[:-1])
    nu = g.copy()
    g[:, :-1] = np.maximum(g[:, :-1], nu[:, 1:])
    g[:, 1:] = np.maximum(g[:, 1:], nu[:, :-1])
    return np.clip((esik - g) / (esik - alt), 0.0, 1.0)


def wall_star_pressure_trrs(p, M_n, gamma):
    """Kayma duvarı YILDIZ BASINCI — iki-genişleme (TRRS) kapalı biçimi.

    Aynalanmış Riemann probleminin (sol: (ρ, u_n, p), sağ: (ρ, −u_n, p))
    iki-genişleme yaklaşımı (Toro, 3. bs., §4.3.2, Eş. 4.46'nın simetrik
    hâli):
        p* = p · [1 + (γ−1)/2 · M_n]^(2γ/(γ−1)),   M_n = u_n / a
    Taban 1 + (γ−1)M_n/2 ≤ 0 (vakum sınırı, M_n ≤ −2/(γ−1)) → p* = 0;
    aksi hâlde kesin pozitif (Lean: HRMA.wallStarTR_pos). M_n → 0'da
    p·(1 + γM_n + O(M_n²)): akustik tahmin p·(1 + γM_n) ile birinci
    mertebe uyumlu (sympy bekçisi tests/cfd/test_d37_cfd_kok_a.py). Eski
    akustik biçim M_n < −1/γ'da NEGATİFE geçiyordu (P6B1-10); bu biçim
    vakuma kadar pozitif kalır ve NaN üretmez.
    """
    g = float(gamma)
    taban = 1.0 + 0.5 * (g - 1.0) * np.asarray(M_n, dtype=float)
    return np.asarray(p, dtype=float) * np.where(
        taban > 0.0, taban, 0.0) ** (2.0 * g / (g - 1.0))


def precompute_geometry(grid):
    """Izgara SABİTİ yüzey geometrisi (birim normaller + alanlar) — bir kez.

    residual_axisym bu büyüklükleri her çağrıda yeniden hesaplıyordu;
    ızgara koşu boyunca değişmez (ÖLÇÜLDÜ, 1A profili: _unit_normals
    tottime 9,1 s / 137,2 s — sıcak listede 4. sıra, ilk hoist adayı).
    Sürücü (steady.py) bunu bir kez hesaplayıp residual_axisym'e geçirir.

    Değerler çağrı-içi hesapla BİT-ÖZDEŞTİR: aynı _unit_normals aynı
    girdiyle çağrılır, dilimleme (çıkış kolonu, duvar sırası) elementer
    işlemlerin sırasını değiştirmez (bekçi: tests/cfd/test_performans.py).
    """
    n_hat_i, area_i = _unit_normals(grid.face_i)
    n_hat_j, area_j = _unit_normals(grid.face_j)
    return {
        'n_hat_i': n_hat_i, 'area_i': area_i,
        'n_hat_j': n_hat_j, 'area_j': area_j,
        'n_out_hat': n_hat_i[-1],          # çıkış yüzü kolonu
        'wall_n_hat': n_hat_j[:, -1],      # duvar yüzü sırası
    }


def _directional_flux(w_l, w_r, n_hat, area, gamma):
    """Yönlü akı — arka uç seçici (performans turu, Aşama 1B).

    numba kuruluysa ve HRMA_CFD_DISABLE_NUMBA=1 değilse derlenmiş çekirdek
    (kernels.directional_hllc; aynı işlem sırası, fastmath kapalı), aksi
    hâlde saf NumPy yolu. İki yolun eşdeğerliği bekçilidir
    (tests/cfd/test_performans.py); arka uç steady çıktısında beyanlıdır.
    """
    if _kernels.NUMBA_AVAILABLE:
        return _kernels.directional_hllc(w_l, w_r, n_hat, area, gamma)
    return _directional_flux_numpy(w_l, w_r, n_hat, area, gamma)


def _directional_flux_numpy(w_l, w_r, n_hat, area, gamma):
    """Yüzey-normal çerçevesine döndür, HLLC çağır, geri çevir, alanla çarp.

    Döner: (n_face..., 4) — [kütle, z-momentum, r-momentum, enerji] akıları
    (gerçek birim: kg/s, N, W; alan 2π'yi içerir).
    """
    nz = n_hat[..., 0]
    nr = n_hat[..., 1]
    un_l = w_l[..., 1] * nz + w_l[..., 2] * nr
    ut_l = -w_l[..., 1] * nr + w_l[..., 2] * nz
    un_r = w_r[..., 1] * nz + w_r[..., 2] * nr
    ut_r = -w_r[..., 1] * nr + w_r[..., 2] * nz
    f_rho, f_mn, f_mt, f_e = hllc_flux(
        w_l[..., 0], un_l, ut_l, w_l[..., 3],
        w_r[..., 0], un_r, ut_r, w_r[..., 3], gamma)
    fz = f_mn * nz - f_mt * nr
    fr = f_mn * nr + f_mt * nz
    return np.stack([f_rho, fz, fr, f_e], axis=-1) * area[..., None]


# --------------------------------------------------------------------------
# 2B eksenel simetrik kalıntı
# --------------------------------------------------------------------------

def residual_axisym(U, grid, gamma, R, P0, T0, Pb=None, second_order=True,
                    slopes=None, return_slopes=False, geom=None,
                    wall_bc=WALL_BC_SLIP,
                    outlet_subsonic_anchor=OUTLET_ANCHOR_EXTRAPOLATE):
    """dU/dt kalıntısı ve akı bütçesi.

    Args:
        U: (ni, nj, 4) korunum durumu [ρ, ρu_z, ρu_r, E].
        grid: AxisymGrid (grid_axisym).
        gamma, R: gaz modeli (kalorik mükemmel; çağıran motor çözücüsünden
            getirir, burada varsayılan YOK).
        P0, T0: rezervuar giriş koşulu [Pa, K].
        Pb: geri basınç [Pa] veya None (tam dışdeğerleme çıkışı).
        second_order: MUSCL açık/kapalı (mertebe testi bunu kanıtlar).
        slopes: None → minmod eğimleri hesaplanır; (s_i, s_j) → verilen
            DONMUŞ eğimler kullanılır (steady.py sınırlayıcı dondurması:
            minmod salınımı kararlı-hâl kalıntısını platoda bırakır; plato
            tespitinde eğimler dondurulur — kararlı-hâl pratiğinde standart,
            Venkatakrishnan, AIAA J. 33(5), 1995 gerekçesi. Dondurma anı
            sürücü çıktısında BEYAN edilir).
        return_slopes: True → (dUdt, aux, (s_i, s_j)) döndürür (dondurma
            anında sürücünün eğimleri alması için).
        geom: precompute_geometry(grid) çıktısı veya None (None → burada
            hesaplanır; ızgara sabiti olduğundan sürücü BİR kez hesaplayıp
            geçirir — performans hoist'i, bit-özdeşlik bekçili).
        wall_bc: 'slip' (varsayılan, bugünkü Euler kodu — bit-özdeş) veya
            'noslip' (viskoz koşu: MUSCL hayaleti TAM yansıma). Yalnız
            hayalet aynasını değiştirir; duvarın analitik akı formülü
            (aşağıdaki blok) her iki kipte AYNIDIR — gerekçe _mirror_wall
            docstring'inde, ölçüsü tests/cfd/test_boru_laminer.py'de.
        outlet_subsonic_anchor: 'extrapolate' (VARSAYILAN — bugünkü kod,
            bit-özdeş) veya 'core_pressure' (Pb=None çıkışında ses-altı
            alt tabakayı çekirdek basıncına bağlar; künye
            OUTLET_ANCHOR_BASIS, ölçüm tests/cfd/test_giris_bc.py ve
            tests/cfd/test_viskoz_entegrasyon.py).

    Returns:
        (dUdt, aux[, slopes]): dUdt (ni, nj, 4) [birim/s]; aux sözlüğü
        giriş/çıkış kütle ve enerji akıları (bütçe beyanı için).

    KAYMA DUVARI AKISI (ayrık hava geçirmezlik): duvar yüzünde sağ durum,
    sol REKONSTRÜKTE durumun duvar normaline göre aynasıdır (hayaletin ayrı
    rekonstrüksiyonu değil — ayna ile bileşen-bazlı minmod yer değiştirmez
    ve O(h²) kütle sızıntısı doğurur; ölçüldü). Simetrik Riemann probleminde
    S* = 0 ve kütle/enerji/teğet momentum akısı ANALİTİK olarak tam sıfırdır;
    ulp artıklarını da kapatmak için akı [0, p*·n̂·|S|, 0] olarak kurulur
    (Euler kayma duvarının fiziksel akısı budur; korunum bütçesi bekçisi
    tests/cfd/test_korunum.py bunu doğrular).
    """
    if wall_bc not in WALL_BC_MODES:
        raise ValueError(
            f'wall_bc {wall_bc!r} tanımsız — geçerli kipler {WALL_BC_MODES}. '
            'Varsayılan "slip" Euler yolunun bit-özdeş dalıdır.')
    g = float(gamma)
    w = cons_to_prim_axisym(U, g)
    s_i_given, s_j_given = slopes if slopes is not None else (None, None)
    if geom is None:
        geom = precompute_geometry(grid)

    # ---- hayalet katmanlar (i: giriş/çıkış; j: eksen/duvar aynaları) ----
    w_in = inlet_state_from_stagnation(w[0], g, R, P0, T0)      # (nj, 4)
    n_out_hat = geom['n_out_hat']                               # (nj, 2)
    w_out = _outlet_state(w[-1], n_out_hat, g, Pb,
                          subsonic_anchor=outlet_subsonic_anchor)
    w_ext_i = np.concatenate([w_in[None], w_in[None], w,
                              w_out[None], w_out[None]], axis=0)
    wall_n_hat = geom['wall_n_hat']                             # (ni, 2)
    w_axis1 = _mirror_axis(w[:, 0])
    w_axis2 = _mirror_axis(w[:, 1])
    w_wall1 = _mirror_wall(w[:, -1], wall_n_hat, wall_bc)
    w_wall2 = _mirror_wall(w[:, -2], wall_n_hat, wall_bc)
    w_ext_j = np.moveaxis(np.concatenate(
        [w_axis2[:, None], w_axis1[:, None], w,
         w_wall1[:, None], w_wall2[:, None]], axis=1), 1, 0)

    # ---- şok sensörü (ÖH D37 A3a cfd-kok-a — OH-DK-14 onarımı) ----
    # İç şoklu kararlı-hâl koşusunda MUSCL eğimleri şok hücrelerinde limit
    # döngüsü sürdürür (ölçüldü, 120×24 arka-basınç vakası: kalıntı 3e-3
    # bandında stall; eğim DONDURMA dahi yetmedi). Standart tedavi:
    # basınç-tabanlı sensörle şok hücrelerinde eğimleri SIFIRLA (yerel
    # birinci mertebe — süreksizlik üstünde biçimsel ikinci mertebe zaten
    # yoktur). Donmuş eğim verilmişse sensör etkisi eğimlerin içindedir
    # (dondurma anında uygulanmıştı), yeniden uygulanmaz.
    #
    # HÜCRE bazlı JST sensörü (varsayılan, SHOCK_SENSOR_MODE='cell'): ikinci
    # fark normalizasyonu + SIKIŞMA işareti. ESKİ kolon sensörü (2026-08-15,
    # |Δp|/min p > 0,25, işaretsiz) şoksuz GENİŞLEMEDE ateşliyordu — DK
    # kampanyası ölçtü (OH-DK-14): Back ıraksak konisi (96×24, 192×48) ve
    # motor lülesinin Rao boğazı (60×12…240×48) bayraklıydı, tetikleyen
    # yüzlerin HEPSİ genişlemeydi, bayraklı kolonlar 1. mertebeye düşüyordu.
    # Kolon sensörünün gerekçesi ("hücre bayrağı eğri şok cephesinde radyal
    # yönde titrer", 80×16 ölçümü) burada SÜREKLİ çarpanla karşılanır:
    # anahtar yok, φ(ν) θ_alt…θ arasında doğrusal (ölçüm SHOCK_SENSOR_
    # THRESHOLD_LOW yanında); şoklu akışta eğim dondurması KAPALIDIR
    # (steady.py, OH-DK-13 ayrıştırması). Kolon kipi yalnız kıyas için.
    # shock_w: (ni, nj) eğim ÇARPANI (1 = dokunma, 0 = birinci mertebe) ya da
    # None (pürüzsüz akış — eğimlere hiç dokunulmaz, bit-özdeş).
    shock_w = None
    if second_order and (s_i_given is None or s_j_given is None):
        if SHOCK_SENSOR_MODE == 'column':
            _kolon = shock_column_flag(w[..., 3])
            shock_w = (None if _kolon is None else np.where(
                np.broadcast_to(_kolon[:, None], w.shape[:2]), 0.0, 1.0))
        elif SHOCK_SENSOR_MODE == 'cell':
            shock_w = shock_cell_weight(w_ext_i[..., 3], w_ext_j[..., 3],
                                        w[..., 1], w[..., 2])
        else:
            raise ValueError(
                f'SHOCK_SENSOR_MODE {SHOCK_SENSOR_MODE!r} tanımsız — '
                f'geçerli kipler {SHOCK_SENSOR_MODES}.')

    # ---- i yönü (eksenel) ----
    if s_i_given is not None:
        s_i = s_i_given
    else:
        s_i = limited_slopes(w_ext_i) if second_order else None
        if s_i is not None and shock_w is not None:
            s_i[1:-1] *= shock_w[..., None]      # hücre (i,j) → s_i[i+1, j]
    w_l, w_r = _edge_states(w_ext_i, s_i)
    n_hat_i, area_i = geom['n_hat_i'], geom['area_i']
    flux_i = _directional_flux(w_l, w_r, n_hat_i, area_i, g)    # (ni+1,nj,4)

    # ---- j yönü (radyal) ----
    if s_j_given is not None:
        s_j = s_j_given
    else:
        s_j = limited_slopes(w_ext_j) if second_order else None
        if s_j is not None and shock_w is not None:
            s_j[1:-1] *= shock_w.T[..., None]    # s_j ekseni (j+1, i)
    w_l_j, w_r_j = _edge_states(w_ext_j, s_j)
    w_l_j = np.moveaxis(w_l_j, 0, 1)
    w_r_j = np.moveaxis(w_r_j, 0, 1)
    n_hat_j, area_j = geom['n_hat_j'], geom['area_j']
    flux_j = _directional_flux(w_l_j, w_r_j, n_hat_j, area_j, g)

    # ---- kayma duvarı: analitik hava geçirmez akı (docstring beyanı) ----
    # YILDIZ BASINCI — POZİTİFLİK KORUYAN biçim (ÖH D37 A3a cfd-kok-a, F-05;
    # ÖH defter P6B1-10 KAPATILDI). Eskiden duvar yüzünde sol rekonstrükte
    # durum ile aynası HLLC'ye veriliyor, dönen normal momentum akısı
    # akustik tahminin bağlayıcı olduğu yerde tam p·(1 + γ·M_n) çıkıyordu;
    # M_n < −1/γ'da NEGATİF (duvar emer), sonlu olduğu için hiçbir NaN
    # ölçütüne takılmıyordu (D23 ölçümü: γ = 1,2, M_n = −1,25/γ → −5,0e4 Pa
    # birebir). Kalıntıya "p* ≤ 0 → NaN" kapısı konmuştu ve sağlam koşumun
    # başlangıç geçicisini kırdığı için geri alınmıştı. Doğru çare, o
    # notun kendisinin yazdığı gibi, pozitiflik KORUYAN duvar akısıdır:
    # aynalanmış durumun iki-genişleme yıldız basıncı (Toro §4.3.2 TRRS)
    #     p* = p·[1 + (γ−1)/2·M_n]^(2γ/(γ−1)),  taban ≤ 0 → 0 (vakum)
    # vakum sınırına kadar pozitiftir; M_n → 0'da p(1 + γM_n + O(M_n²)) —
    # akustik biçimle birinci mertebe uyumlu, kararlı hâlde (M_n → 0) aynı
    # sayıya gider (fark O(M_n²); önce/sonra ölçümü kulvar raporunda).
    # §11.3 bit-özdeşlik referansları bu değişiklikle YENİDEN üretildi
    # (data/cfd_referans/README.md, kulvar raporu). Kütle/enerji/teğet
    # momentum akısı simetrik Riemann probleminde analitik olarak sıfırdır
    # ve öyle kurulur; korunum bekçisi tests/cfd/test_korunum.py.
    w_lw = w_l_j[:, -1, :]
    nz_w = wall_n_hat[..., 0]
    nr_w = wall_n_hat[..., 1]
    un_lw = w_lw[..., 1] * nz_w + w_lw[..., 2] * nr_w
    a_lw = np.sqrt(g * w_lw[..., 3] / w_lw[..., 0])
    p_star_w = wall_star_pressure_trrs(w_lw[..., 3], un_lw / a_lw, g)
    area_w = area_j[:, -1]
    flux_j[:, -1, 0] = 0.0
    flux_j[:, -1, 1] = p_star_w * nz_w * area_w
    flux_j[:, -1, 2] = p_star_w * nr_w * area_w
    flux_j[:, -1, 3] = 0.0

    # ---- toplama + eksenel simetri kaynak terimi ----
    net = -(flux_i[1:] - flux_i[:-1]) - (flux_j[:, 1:] - flux_j[:, :-1])
    net[..., 2] += w[..., 3] * _TWO_PI * grid.area_planar
    dudt = net / grid.volume[..., None]

    aux = {
        'mass_flow_in_kg_s': float(np.sum(flux_i[0, :, 0])),
        'mass_flow_out_kg_s': float(np.sum(flux_i[-1, :, 0])),
        'energy_flux_in_W': float(np.sum(flux_i[0, :, 3])),
        'energy_flux_out_W': float(np.sum(flux_i[-1, :, 3])),
        'wall_mass_flux_kg_s': float(np.sum(flux_j[:, -1, 0])),
        # Bayraklı KOLON sayısı (≥ 1 bayraklı hücre içeren kolon; eski
        # sözleşme adı korunur) + bayraklı HÜCRE sayısı (yeni, hücre sensörü).
        # Sensörün DOKUNDUĞU hücreler (çarpan < 1) ve onları içeren kolonlar.
        'shock_sensor_columns': (0 if shock_w is None
                                 else int(np.sum(np.any(shock_w < 1.0,
                                                        axis=1)))),
        'shock_sensor_cells': (0 if shock_w is None
                               else int(np.sum(shock_w < 1.0))),
    }
    if return_slopes:
        return dudt, aux, (s_i, s_j)
    return dudt, aux


def wall_star_pressure(U, grid, gamma, geom=None):
    """Kayma duvarı YILDIZ BASINCI ölçümü ve yayım kapısı (P6B1-10 KAPATILDI).

    Duvara komşu hücre satırında normal Mach ``M_n = (u·n̂)/a`` ve iki
    yıldız basıncı döndürür:

    * ``p*_akustik = p·(1 + γ·M_n)`` — ESKİ (2026-08…2026-09-24) aynalanmış
      HLLC duvar akısının akustik tahminin bağlayıcı olduğu yerdeki tam
      değeri. ``M_n < −1/γ``'da NEGATİFE geçer (duvar emer; ÖLÇÜLDÜ, ÖH
      D23: γ = 1,2 ve M_n = −1,25/γ için −5,0000e+04 Pa). Artık YALNIZ
      KIYAS sütunudur; duvar akısı bu sayıyı KULLANMAZ.
    * ``p*_TRRS = p·[1 + (γ−1)·M_n/2]^(2γ/(γ−1))`` — aynalanmış durumun
      iki-genişleme çözümü (Toro, 3. bs., §4.3.2; ``wall_star_pressure_
      trrs``). ÖH D37 A3a cfd-kok-a (F-05) itibarıyla ``residual_axisym``
      duvar akısının KENDİSİ budur; vakum sınırına (M_n ≤ −2/(γ−1)) kadar
      pozitif, sınırda sıfır (Lean: HRMA.wallStarTR_pos).

    Özet sözlüğü İŞLETİLEN (TRRS) basıncı yargılar: ``pozitif_mi`` /
    ``min_p_star_Pa`` / ``negatif_p_star_yuz_sayisi`` TRRS'ye aittir;
    akustik kıyas ``akustik_`` önekiyle yan yana durur. Kapı yayım
    sınırındadır (yakınsamış ilan edilen alan duvarda vakum taşıyamaz);
    geçici aşım serbesttir.

    Dönüş: ``M_n`` (ni,), ``p_star_acoustic`` (ni,),
    ``p_star_trrs`` (ni,) dizileri ve özet sözlüğü — dizi SIRASI eski
    çağıranlar için korunmuştur (2. eleman akustik, 3. eleman TRRS).
    """
    g = float(gamma)
    if geom is None:
        geom = precompute_geometry(grid)
    w = cons_to_prim_axisym(np.asarray(U, dtype=float), g)
    n_hat = geom['wall_n_hat']
    w_w = w[:, -1, :]
    un = w_w[..., 1] * n_hat[..., 0] + w_w[..., 2] * n_hat[..., 1]
    a = np.sqrt(g * w_w[..., 3] / w_w[..., 0])
    M_n = un / a
    p_star_ak = w_w[..., 3] * (1.0 + g * M_n)
    p_star = wall_star_pressure_trrs(w_w[..., 3], M_n, g)
    esik_ak = -1.0 / g
    esik_vakum = -2.0 / (g - 1.0)
    sonlu = np.isfinite(M_n) & np.isfinite(p_star)
    i_min = int(np.argmin(np.where(sonlu, M_n, np.inf))) if np.any(sonlu) \
        else 0
    ozet = {
        'gamma': g,
        'operator': 'trrs',
        'esik_M_n': float(esik_vakum),
        'esik_M_n_akustik': float(esik_ak),
        'min_M_n': float(M_n[i_min]) if np.any(sonlu) else None,
        'min_M_n_yuzu': i_min,
        'min_p_star_Pa': (float(np.min(p_star[sonlu]))
                          if np.any(sonlu) else None),
        'negatif_p_star_yuz_sayisi': int(np.sum(p_star[sonlu] <= 0.0))
        if np.any(sonlu) else None,
        'toplam_duvar_yuzu': int(M_n.size),
        'pozitif_mi': (bool(np.all(p_star[sonlu] > 0.0))
                       if np.any(sonlu) else None),
        'akustik_min_p_star_Pa': (float(np.min(p_star_ak[sonlu]))
                                  if np.any(sonlu) else None),
        'akustik_negatif_yuz_sayisi': int(np.sum(p_star_ak[sonlu] <= 0.0))
        if np.any(sonlu) else None,
        'akustik_pozitif_mi': (bool(np.all(p_star_ak[sonlu] > 0.0))
                               if np.any(sonlu) else None),
        'min_p_star_iki_genisleme_Pa': (float(np.min(p_star[sonlu]))
                                        if np.any(sonlu) else None),
        '_basis': (
            'İŞLETİLEN duvar yıldız basıncı p* = p·[1 + (γ−1)M_n/2]^'
            '(2γ/(γ−1)) — aynalanmış Riemann probleminin iki-genişleme '
            '(TRRS) çözümü (Toro 3. bs. §4.3.2); vakum sınırına M_n = '
            '−2/(γ−1) kadar pozitif, sınırda sıfır. ÖH D37 A3a cfd-kok-a '
            '(F-05) ile residual_axisym duvar akısı bu biçime geçti; eski '
            'akustik p·(1 + γ·M_n) (M_n < −1/γ\'da negatif, P6B1-10) '
            'yalnız KIYAS sütunu olarak yayımlanır (akustik_* alanları). '
            'Kapı NİHAİ alanı yargılar: p* ≤ 0 (duvarda vakum) ise hüküm '
            'geri çekilir; geçici aşım serbesttir.'),
    }
    return M_n, p_star_ak, p_star, ozet


def local_dt_axisym(U, grid, gamma, cfl, area_i=None, area_j=None):
    """Yerel zaman adımı: Δt_c = CFL·V / Σ_yüzey (|u·n̂| + a)·|S|.

    area_i/area_j önceden hesaplanmış yüzey alanları (sürücü döngüde bir
    kez hesaplayıp geçirir; None ise burada hesaplanır).
    """
    g = float(gamma)
    w = cons_to_prim_axisym(U, g)
    a = np.sqrt(g * w[..., 3] / w[..., 0])
    if area_i is None:
        area_i = np.linalg.norm(grid.face_i, axis=-1)
    if area_j is None:
        area_j = np.linalg.norm(grid.face_j, axis=-1)
    # |u·S| yüz vektörüyle, a·|S| alanla — hücre değerleri yüzlere atanır
    uz = w[..., 1]
    ur = w[..., 2]

    def face_speed(face_vec, face_area):
        return np.abs(uz * face_vec[..., 0] + ur * face_vec[..., 1]) \
            + a * face_area

    spectral = (face_speed(grid.face_i[:-1], area_i[:-1])
                + face_speed(grid.face_i[1:], area_i[1:])
                + face_speed(grid.face_j[:, :-1], area_j[:, :-1])
                + face_speed(grid.face_j[:, 1:], area_j[:, 1:]))
    return float(cfl) * grid.volume / spectral
