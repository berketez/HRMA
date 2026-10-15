# hrma/cfd — kararlı-hâl sürücüsü: yerel Δt, CFL rampası, hüküm beyanı
"""
2B eksenel simetrik Euler çözücüsünün kararlı-hâl sürücüsü (Aşama 1A).

YÖNTEM
------
- Yerel zaman adımı: Δt_c = CFL·V_c / Σ_yüzey (|u·n̂|+a)|S| (hücre başına;
  zaman doğruluğu YOK — kararlı hâle en dik iniş; not_modelled beyanında).
- CFL rampası: 0,5 → 0,9 (tasarım belgesi §2), ramp_iters boyunca doğrusal.
- Zaman entegrasyonu: SSP-RK2 (euler_core ile aynı kalıntı). Opt-in:
  time_integrator='line_implicit_j' → j-yönü satır-örtük gevşetme
  (relax_implicit.py; viskoz tasarım belgesi §4.2/§5.6). Hüküm-nötr:
  kararlı hâl kökü kalıntı=0 ile tanımlıdır, yol seçimi kökü değiştirmez
  (bekçi: tests/cfd/test_satir_ortuk.py).
- Başlangıç tahmini: kolon bazlı izantropik alan-Mach çözümü. Alan-Mach
  terslemesi hrma.flow.quasi1d.mach_from_area_ratio'dan ÇAĞRILIR (parametre
  tutarlılığı: aynı bağıntı ikinci kez yazılmaz). Bu yalnız BAŞLANGIÇ
  tahminidir; doğrulama bağımsızlığını bozmaz — hüküm, binlerce iterasyon
  sonra oturan duruma ve analitik referanslara karşıdır (tests/cfd).

HÜKÜM (converged) BEYANI — FEA kabul-ölçütü dersinin izdüşümü
-------------------------------------------------------------
Hüküm KULLANICI BÜYÜKLÜKLERİNDEN verilir; kalıntı ikincildir:
  (1) kütle debisi (giriş VE çıkış akısı) son `window` iterasyonda bağıl
      bant < settle_tol içinde OTURMUŞ,
  (2) boğaz kesit-ortalamalı Mach aynı bantta OTURMUŞ,
  (3) yoğunluk kalıntısının hacim-ağırlıklı L2 normu (ρ₀·a₀/L ölçeğiyle
      boyutsuzlaştırılmış) tol_res altına İNMİŞ.
Üçü birden sağlanmadan converged=True denmez. Yakınsamayan koşu sonuç +
converged=False + kalıntı geçmişiyle döner (FEA beyan deseni: sonuç
gizlenmez, hüküm de verilmez). Fiziksel olmayan duruma düşen koşu (NaN)
'diverged' beyanıyla, bilinen son sonlu alanla döner.

``converged`` ÜÇ DEĞERLİDİR (OH-D31-15; Berke kararı 15 Eyl 2026 seç. A):
  True  — hüküm hak edildi VE gerekli değerlendirme yapıldı,
  False — ÖLÇÜLMÜŞ bir engel (aşım / oturmama / ıraksama) hükmü engelledi,
  None  — hüküm için gerekli değerlendirme YAPILMADI (öz-tutarlılık kapısı
          bu koşumu KAPSAMIYOR ve şemanın kendi kalıntısı eşiğin üstünde);
          ``convergence_status='not_evaluated'``. "Yakınsamadı" DEĞİL,
          "yargılanmadı" demektir; sayılar aynen yayımlanır.
Tüketici üçünü AYIRMAK zorundadır: ``bool(converged)`` None'ı False yapar
(fail-closed, kabul edilebilir) ama 'değerlendirilmedi'yi 'yakınsamadı'
diye YAYIMLAMAK bir hüküm uydurmaktır.

Uydurma sabit YOK: γ ve R çağırandan gelir (motor çözücüsünün yayımladığı
değerler; köprü katmanı eksikse REDDEDER, burada varsayılan yazılmaz).
"""

import time
from dataclasses import dataclass

import numpy as np

from hrma.cfd import kernels as _kernels
from hrma.cfd.euler_core import (
    INLET_BC_BASIS,
    INLET_BC_NAME,
    OUTLET_ANCHOR_BASIS,
    OUTLET_ANCHOR_CORE_PRESSURE,
    OUTLET_ANCHOR_EXTRAPOLATE,
    OUTLET_ANCHOR_MODES,
    WALL_BC_NOSLIP,
    WALL_BC_SLIP,
    _outlet_state,
    cons_to_prim_axisym,
    inlet_state_from_stagnation,
    local_dt_axisym,
    outlet_subsonic_count,
    precompute_geometry,
    prim_to_cons_axisym,
    residual_axisym,
    shock_column_flag,
    wall_star_pressure,
)
from hrma.cfd import euler_core as _euler_core
from hrma.cfd.gradients import BoundaryFaceValues, precompute_gradient_geometry
from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.implicit import solve_block_tridiag
from hrma.cfd.relax_implicit import (
    line_implicit_delta,
    local_dt_axial,
    viscous_jacobian_blocks,
)
from hrma.cfd.sa_neg import (
    SA_CITATIONS,
    SA_CONVECTION_SCHEMES,
    SA_FREESTREAM_CHI_BAND,
    SA_NOT_MODELLED,
    SA_SIGMA,
    diffusion_coefficient,
    face_mass_flux,
    freestream_nu_tilde,
    sa_constants,
    sa_residual,
    turbulent_viscosity,
    vorticity_magnitude,
)
from hrma.cfd.viscous import (
    TURBULENCE_CLOSED_BY_MU_T,
    VISCOUS_NOT_MODELLED,
    nonphysical_state,
    viscous_residual,
    viscous_spectral_radius,
)
from hrma.cfd.wall_distance import wall_distance_field
from hrma.flow.quasi1d import isentropic_ratios, mach_from_area_ratio

__all__ = ['solve_steady_axisym', 'DEFAULT_CFL_START', 'DEFAULT_CFL_MAX',
           'DEFAULT_RAMP_ITERS', 'DEFAULT_MAX_ITERS', 'DEFAULT_TOL_RES',
           'DEFAULT_SETTLE_WINDOW', 'DEFAULT_SETTLE_TOL',
           'MIN_SETTLE_WINDOW',
           'MIN_MAX_ITERS', 'MIN_RAMP_ITERS',
           'DEFAULT_FREEZE_SETTLE_TOL',
           'DEFAULT_CFL_IMPLICIT_MAX', 'IMPLICIT_CALIBRATION',
           'TIME_INTEGRATORS',
           'DEFAULT_C_VISC', 'ViscousOptions', 'viscous_local_dt',
           'viscous_i_face_share', 'first_cell_for_y_plus',
           'solve_with_y_plus_target', 'TURBULENCE_MODELS',
           'TURBULENCE_NONE', 'TURBULENCE_SA_NEG', 'wall_grid_quality']

# Sürücü varsayılanları (tasarım belgesi §2: CFL 0,5→0,9). tol/settle
# değerleri tests/cfd ölçümleriyle sabitlendi (korunum artığı 1e-10 sınıfına
# bu eşiklerde iniliyor; rapor).
DEFAULT_CFL_START = 0.5
DEFAULT_CFL_MAX = 0.9
DEFAULT_RAMP_ITERS = 400
DEFAULT_MAX_ITERS = 20000
DEFAULT_TOL_RES = 1e-8
DEFAULT_SETTLE_WINDOW = 200
DEFAULT_SETTLE_TOL = 1e-9

#: Hüküm penceresinin ALT SINIRI [iterasyon] — ÖH defter P6B1-05.
#: ÖLÇÜLDÜ (taban 2426b4d, docs/scofield/raw/OH/D17/fea-cfd/a1/once.json):
#: pencere üstünde HİÇBİR kapı yoktu ve ölçüt kendini boş yere doğruluyordu.
#:   settle_window=1 → _settle_band = son TEK örneğin bandı = tam 0,0
#:       (max−min sıfır); "oturdu" hükmü ilk iterasyondan itibaren
#:       KAZANILMADAN veriliyor ve yayımlanan settle_bands.mass_flow_out
#:       da 0,0 basılıyordu — ölçülmemiş bir "kusursuz oturma" sayısı.
#:   settle_window=0 → ``hist[-0:]`` Python'da "pencere yok" DEĞİL, TÜM
#:       GEÇMİŞ demektir (ölçüldü: hist=[1,2,3,4,5] için bant 0,8 =
#:       (5−1)/5, yani 200'lük pencerenin NaN'ı yerine tüm geçmişin bandı);
#:       ``len(hist) < window`` koruması da 0'da hiç ateşlemiyordu.
#:   settle_window<0 → ham ``IndexError: list index out of range``
#:       sızıyordu (adsız çöküş; fail-closed değil).
#: 2 seçildi: bant (maks−min)/|son| bir YAYILIM ölçüsüdür ve iki ayrı
#: örnek görmeden yayılım TANIMSIZDIR. Alt sınır bir gevşetme değil,
#: ölçütün kendi tanımının asgarisidir; gerçek koşumların varsayılanı
#: DEFAULT_SETTLE_WINDOW = 200'dür ve DEĞİŞMEMİŞTİR (bit-özdeş).
MIN_SETTLE_WINDOW = 2

#: Sürücü döngüsünün ALT SINIRLARI [iterasyon] — ÖH defter P6B1-06.
#: ÖLÇÜLDÜ (taban 35aa279, docs/scofield/raw/OH/D21/fea-cfd/a2/once.json):
#:   max_iters=0 ve max_iters=-5 → ham ``IndexError: list index out of
#:       range`` (döngü hiç dönmez, res_hist boş kalır, ``res_hist[-1]``
#:       adsız çöker). Fail-closed DEĞİL: çağıran hangi alanı yanlış
#:       verdiğini yanıttan okuyamıyordu.
#:   ramp_iters=0 → ham ``ZeroDivisionError: float division by zero``
#:       (``it / float(ramp_iters)``).
#:   ramp_iters=-2 → SESSİZCE KABUL: ``it/float(-2)`` negatif olduğundan
#:       ``min(1.0, ·)`` negatif kalır ve CFL rampası GERİ İŞLER —
#:       cfl_start'ın ALTINA iner ve iterasyonla düşmeye devam eder.
#:       Belgelenen davranış ("CFL rampası 0,5 → 0,9") o koşuda YANLIŞTIR.
#: 1 seçildi: bunlar bir gevşetme değil, büyüklüklerin kendi TANIMININ
#: asgarisidir — "en az bir iterasyon" ve "en az bir iterasyonluk rampa".
#: Ürün varsayılanları (20000 / 400) DEĞİŞMEMİŞTİR (bit-özdeş).
MIN_MAX_ITERS = 1
MIN_RAMP_ITERS = 1

#: Satır-örtük yolda oturma-tetikli KALICI eğim dondurmasının TETİK eşiği
#: (V3 — tetik/hüküm ayrımı). Parti 38'in ölçtüğü DAİRESEL KİLİDİN
#: yapısal kapanışı: tetik ile hüküm aynı ``settle_tol``u paylaşıyordu;
#: dondurma tam da eğim-tazeleme gevelemesini gidermek için varken,
#: tetiklenmesi gevelemenin YOKLUĞUNU gerektiriyordu (KAPI vakası 192×48:
#: settle_tol 1e-9'da çıkış debisi bandı 1,008e-05 tabanında → tetik HİÇ
#: ateşlemedi, koşu 4000 iterasyonda 1,83e-05'te asılı kaldı). Artık
#: tetiğin eşiği AYRI parametredir ve hükümden bağımsız seçilebilir.
#:
#: VARSAYILAN ``None`` = tetik eşiği settle_tol'a eşit (tarihsel davranış,
#: bit-özdeş). Bu bir çekingenlik değil ÖLÇÜMÜN HÜKMÜDÜR (V3 turu,
#: 2026-08-18, M4 Max): gevşek bir varsayılan (1e-4) 60×12 MUSCL nötrlük
#: çiftinde tetiği 4253'ten 560. iterasyona çekti ve KÖKÜ ZEHİRLEDİ —
#: açık↔örtük alan bandı 5,41e-08 → 5,03e-04 (nötrlük bekçisinin 5e-6
#: bandının 100 katı), debi farkı 1,42e-11 → 1,48e-06. Yani gevşek tetik,
#: yavaş SÜRÜNEN (henüz oturmamış) koşuda erken dondurup bayat Picard
#: köküne iner; oysa geveleme TABANINA kilitlenen koşuda (KAPI) tam
#: ilaçtır. İkisini eşik tek başına ayırt EDEMEZ — o yüzden gevşetme
#: çağıranın vaka bilgisiyle verdiği BEYANLI karardır:
#:   - çevrim tabanı ölçülen vakada eşik tabanın ~10 katı seçilir (KAPI:
#:     taban 1,008e-05 → freeze_settle_tol=1e-4; ölçümler
#:     tests/cfd/test_viskoz_entegrasyon.py docstring + bekçileri),
#:   - kök hassasiyeti önde olan vakada None bırakılır (60×12 nötrlük
#:     çifti kalibrasyonu: donma 4253 / bant 5,41e-08 — bu varsayılanla
#:     bit-özdeş yeniden üretildi. İTERASYON SAYISI: kapı öncesi 4452,
#:     bugün 5512 — OH-B4-05, IMPLICIT_CALIBRATION).
#: Hüküm aritmetiği DEĞİŞMEDİ: bant tek yerde (_settle_band) hesaplanır,
#: tetik ve hüküm aynı sayıyı FARKLI eşiklerle okur; etkin tetik eşiği
#: koşum beyanında (inputs['freeze_settle_tol']) görünür.
DEFAULT_FREEZE_SETTLE_TOL = None

# Zaman ilerletme seçenekleri (viskoz tasarım belgesi §4.2/§5.6). Varsayılan
# AÇIK yol: mevcut 149 tests/cfd bekçisi Euler yolunun bit-özdeşliğini bu
# varsayılan üstünden korur; satır-örtük katman opt-in'dir (V0 kararı —
# örtük varsayılan yapılacaksa bit-özdeşlik sözleşmesi §11.3 dondurulmuş
# referans alanlarla yeniden kurulmalıdır; bu partide yapılmadı, beyanlı).
TIME_INTEGRATORS = ('ssp_rk2', 'line_implicit_j')

#: ÖZ-TUTARLILIK KAPISININ KAPSAMI — TEK KAYNAK (ÖH defter OH-Z5-19).
#:
#: Kapının hüküm ayağı (P6B1-08) BUGÜN yalnız örtük 2. mertebe yolda
#: etkindir. AÇIK yol (varsayılan ``ssp_rk2``) plato-dondurma yüzünden
#: AYNI bayat-operatör kusurunu üretir ama kapının DIŞINDADIR.
#:
#: Bu dize kapsamın kod içindeki TEK ADIDIR ve ``slope_state`` içinde
#: aynen yayımlanır: eskiden kapsam dışı koşumda ``selfconsistency_gate``
#: alanı ``None`` dönüyordu ve ``None`` iki AYRI hâli — "kapı yok" ile
#: "kapı bu koşumu KAPSAMIYOR" — birbirine karıştırıyordu.
SELFCONSISTENCY_GATE_SCOPE = 'line_implicit_j+second_order'

#: SATIR-ÖRTÜK YOLUN ÖLÇÜLEN KALİBRASYONU — TEK KAYNAK (OH-B4-05).
#:
#: OH-B4-05 (ÖH D26 / fea-cfd a3): buradaki sayılar V0 turunda (2026-08-17)
#: ölçülmüştü ve o gün hüküm ÖZ-TUTARLILIK KAPISI YOKTU — örtük yol
#: sınırlayıcıyı 4253'te dondurup 4452'de "yakınsadı" diyordu, oysa alanın
#: ŞEMA (canlı minmod) kalıntısı toleransın 86 katıydı (P6B1-03/-08 ölçümü,
#: Faz B-4). Kapı ÖH D15'te (OH-Z5-14) kondu; kapıdan sonra aynı koşu
#: 4452'de DURMUYOR. Yani yayımlanan kalibrasyon sayıları BAYATLAMIŞTI:
#: yorumda 4452/5727/8707 yazarken bugünkü kod 5512/9970/10762 üretiyor.
#: Kalibrasyonun KARARI (cfl_implicit_max = 25) ölçümle AYAKTA — 25 hâlâ
#: MUSCL minimumu — ama sayıların kendisi yenilendi ve bir daha sessizce
#: bayatlamasın diye BEKÇİYE bağlandı (tests/test_d26_fea_cfd_a3.py).
#:
#: YENİDEN ÖLÇÜLDÜ (2026-09-07, ÖH D26 fea-cfd a3, M4 Max; taban 7751531;
#: docs/scofield/raw/OH/D26/fea-cfd/a3/once_a3.json). Vaka: tests/cfd
#: conftest lülesi 60×12, ürün toleransı (tol_res 1e-8), K = 25,
#: max_iters = 30000; öz-tutarlılık kapısı AÇIK.
IMPLICIT_CALIBRATION = {
    'case': ('tests/cfd/conftest lülesi 60×12, ürün tol_res 1e-8, '
             'implicit_slope_refresh = 25, max_iters = 30000'),
    'gate': ('OH-Z5-14 öz-tutarlılık kapısı AÇIK: hüküm yalnız ŞEMANIN '
             'kendi (canlı minmod) kalıntısı da eşiğin altındayken verilir'),
    # YENİDEN ÖLÇÜLDÜ (2026-09-24, ÖH D37 A3a cfd-kok-a, M4 Max yüklü;
    # docs/scofield/raw/OH/A3a/cfd-kok-a/rapor.md §(e)): kayma duvarı akısı
    # TRRS yıldız basıncına geçince (F-05) ve dondurma tetiği değişince
    # iterasyon sayıları kaydı — 07 Eyl değerleri: 5512 / 9970 / 10762,
    # 1. mertebe 4031 / 1826. Kalibrasyonun KARARI (25) yine minimum.
    'measured_on': '2026-09-24 (ÖH D37 / A3a cfd-kok-a; önceki 2026-09-07)',
    'muscl_explicit_iters': 6897,
    'muscl_implicit_iters_by_cfl': {25.0: 5912, 50.0: 9354, 100.0: 10542},
    'first_order_explicit_iters': 2889,
    'first_order_implicit_iters': 1198,
    # KAZANCIN ÖLÇÜTÜ (Faz B-4'ün açtığı soru): "iterasyon kazancı" ancak
    # iki yolda AYNI hüküm ölçütü geçerliyken karşılaştırılabilir. Kapıdan
    # ÖNCE karşılaştırma dürüst değildi (örtük yol bayat/donmuş operatörün
    # kalıntısıyla erken duruyordu); kapıdan SONRA iki yol da şemanın
    # kalıntısını eşiğin altına indirdiği anda duruyor ve kazanç bu ORTAK
    # ölçüt altında ölçülüyor.
    'gain_basis': ('iterasyon kazancı ORTAK ölçüt altında ölçülür: her iki '
                   'yol da şemanın canlı-minmod kalıntısını tol_res altına '
                   'indirdiğinde durur (öz-tutarlılık kapısı). MUSCL: '
                   '5912 / 6897 = 0,857× (örtük LEHİNE, 1,17× hızlı); '
                   '1. mertebe: 1198 / 2889 = 0,415× (2,41×). Kazanç bir '
                   'PERFORMANS İDDİASI değil, bu vakada ölçülen sayıdır '
                   '(24 Eyl 2026 ölçümü; 7 Eyl: 0,799× / 0,453×).'),
    'stale_pre_gate': {
        'muscl_implicit_iters_by_cfl': {25.0: 4452, 50.0: 5727, 100.0: 8707},
        'basis': ('V0 turu, 2026-08-17 — öz-tutarlılık kapısı YOKKEN; '
                  'tarihsel kayıt olarak durur, KARŞILAŞTIRMADA '
                  'kullanılmaz'),
    },
}

# Satır-örtük yol CFL tavanı — ÖLÇÜMDEN (CFL, i-YALNIZ Δt üstündedir:
# relax_implicit.local_dt_axial — j kısıtı örtük katmanla kalkar, belge
# §4.2). Sayılar IMPLICIT_CALIBRATION'dadır (TEK KAYNAK):
#   1.mrt : cfl 2→1473, 5→1309, 10→1243, 25→1198, 50→1182, 100→1174 it
#           (V0 turu; tekdüze düşüş + ~25'te doyum — 1. mertebe yolda
#           eğim/dondurma makinesi YOKTUR, bu yüzden öz-tutarlılık kapısı
#           bu tabloyu oynatmaz; 25'teki ürün noktası bugün de ölçülüdür:
#           IMPLICIT_CALIBRATION['first_order_implicit_iters'] = 1826 —
#           tol/settle DERİN ayarla, tablodan farklı vaka)
#   MUSCL : cfl 25→5512, 50→9970, 100→10762 it (2026-09-07, kapı açık;
#           25 üstünde iterasyon ARTIYOR — oturma-donması yüksek CFL'de
#           geç ateşliyor)
# 25 seçildi: 1.mrt doyum noktası + MUSCL minimumu. Bu KARAR kapıdan sonra
# da geçerlidir (5512 < 9970 < 10762). Üstü/altı çağıranın bilinçli
# seçimidir; aşırı değerde fiziksel olmayan duruma giden koşu
# Δt-sonluluk kapısında 'diverged' beyanıyla döner (istisna sızmaz).
DEFAULT_CFL_IMPLICIT_MAX = 25.0

# Satır-örtük yolda MUSCL eğim TAZELEME aralığı [iterasyon] — ÖLÇÜMDEN
# (V0 turu, 60×12 MUSCL, tablolar test_satir_ortuk.py):
# canlı eğim (her adım) örtük büyük adımlarla limit döngüsüne kilitleniyor
# (60000 iterde kalıntı 0,66 — HİÇ yakınsamıyor); tek kalıcı dondurma ise
# bayat köke iniyor (analitik debiden %1,47 sapma ÖLÇÜLDÜ). Çare mevcut
# tazeleme fikrinin (steady docstring, Picard) periyodik hâli: eğimler her
# K iterasyonda güncel durumdan yeniden alınır; durum oturdukça tazeleme
# öz-tutarlılaşır ve GERÇEK MUSCL köküne iner (hüküm-nötrlük bekçisi bunu
# ölçer). K taraması (ürün tol, 60×12): K=2 limit döngüsü (kırmızı), K=5
# 1,5e-4'te asılı, K=10 12300 it, K=25 3605 it, K=100 12306 it, K=200+
# Picard bacağı israfı — optimum 25. (Bu K taraması V0 turundandır ve
# öz-tutarlılık kapısı AÇILMADAN önce ölçülmüştür — OH-B4-05: mutlak
# sayılar kapıdan sonra büyür, SIRALAMA/optimum yeniden ölçülmedi;
# bugünkü K=25 ürün noktası IMPLICIT_CALIBRATION'da yayımlanır.) 60×48 MUSCL: K=25 oturma-donmasıyla
# 4143 iterasyonda yeşil; K=100/200 40000'de geveleme tabanında asılı
# (2,9e-8/1,8e-8) — K=25 varsayılanı orada da ölçümle doğrulandı; K
# çağırana açıktır.
DEFAULT_IMPLICIT_SLOPE_REFRESH = 25

#: Viskoz yerel-Δt kararlılık katsayısı (tasarım belgesi §5.6'nın C_visc'i;
#: "Blazek'te ~4 kullanılır; ÖLÇMEDEN YAZILMAZ"). ÖLÇÜLDÜ.
#:
#: ÖLÇÜM VAKASI SEÇİMİ: A1'in basamak-4 borusunda viskoz sınır HİÇ
#: bağlayıcı değildi (Δt_v/Δt_e = 32,6 … 2,71; nj = 96'da bile 1,36) —
#: yani orada C_visc taransa "her değer geçer" çıkardı, bu bir kalibrasyon
#: OLMAZDI. Sınır ancak viskoz terim baskınken görünür: aynı vaka μ×16 ile
#: koşuldu (nj = 48, ni = 288, cfl_max = 0,9, açık SSP-RK2, 2000 adım,
#: M4 Max, 2026-08-18). O vakada maks(Δt_e/Δt_v) = 10,608 ÖLÇÜLDÜ.
#:     C_visc  0,00     0,25    0,50     0,75    1,00  1,50  2,00
#:     durum   NaN@5  NaN@26  NaN@276  NaN@1118  SONLU SONLU SONLU
#: Vaka sınırı C* ∈ (0,75; 1,00] (0,75 → 1118. adımda ıraksadı).
#:
#: C* VAKAYA BAĞLIDIR, o yüzden ondan ŞEMANIN sabiti çıkarılır:
#: 1/Δt = 1/Δt_e + C/(cfl·Δt_v) olduğundan kararlılık koşulu Δt ≤ S·Δt_v
#: biçimindedir ve S = 1/(Δt_v/Δt_e + C*/cfl). İki BAĞIMSIZ vaka:
#:     nj = 48, μ×16 : Δt_e/Δt_v = 10,608, C* ∈ (0,75; 1,00] → S ∈ [0,830; 1,078)
#:     nj = 24, μ×16 : Δt_e/Δt_v =  5,304, C* ∈ (0,50; 0,75] → S ∈ [0,979; 1,343)
#: Kesişim S ∈ [0,979; 1,078) — yani S ≈ 1: açık SSP-RK2 bu ayrıklaştırmada
#: kabaca Δt ≤ V/ΣΛ_v'yi taşıyor. İki vakanın aynı S'e çıkması, ölçülenin
#: vakaya değil ŞEMAYA ait olduğunun kanıtıdır.
#: Saf difüzyon limitinde (Δt_e → ∞) gereken katsayı C = cfl/S ≈ 0,9…0,92.
#: Seçilen 1,5 bunun ~1,6 katıdır (ölçülen vaka sınırlarının 1,5-2 katı).
#: Blazek'in ~4'ü daha kötümserdir (kararlı, ama viskoz-baskın hücrelerde
#: Δt'yi gereksiz küçültür). Ölçüm bekçisi:
#: tests/cfd/test_viskoz_entegrasyon.py (sınırın ALTINDA ıraksama, ÜSTÜNDE
#: sonluluk; ikisi de koşuluyor).
DEFAULT_C_VISC = 1.5

#: Türbülans kapanışı seçenekleri (viskoz tasarım belgesi §5.5). Varsayılan
#: 'none': V1'in LAMİNER viskoz yolu — o dalda SA kodu HİÇ çalışmaz ve
#: sonuç V1 ile bit-özdeştir (bekçisi tests/cfd/test_viskoz_entegrasyon.py).
#: Üçüncü model YOK: SST k-ω belgede 2.8+ için isteğe bağlı ikinci model
#: olarak beyanlıdır, bugün yazılmamıştır.
#: ŞEMA KALINTISININ ÖRNEKLEME PERİYODU [iterasyon] — PLATO TESPİTİ
#: (ÖH defter OH-Z5-14). Öz-tutarlılık kapısı hükmü geri çekebiliyor ama
#: koşan kişiye "biraz daha bütçe verirsen iner mi, yoksa DURDU mu?"
#: sorusunun cevabını vermiyordu; bütçeyi büyütmek tek çare olarak
#: kalıyordu. ÖLÇÜLDÜ (2026-08-28, viskoz aşırı-genişlemiş 64×16 lüle,
#: tol 1e-8; docs/scofield/raw/OH/Z5S/pk3/ayrilma_ulasilabilirlik.json):
#: 5.000/10.000/20.000 iterasyon tavanlarında şemanın kendi kalıntısı
#: 1,2204e-04 / 1,2168e-04 / 1,2206e-04 — dört katına çıkan bütçe sayıyı
#: BİNDE ÜÇ bile oynatmadı. Yani hedef o vaka sınıfında ULAŞILAMAZ ve bunu
#: ürünün ADIYLA söylemesi gerekir.
#:
#: Örnekleme, şemanın (canlı minmod) kalıntısını periyodik ölçer. Maliyet:
#: yürüyüş operatörü CANLI iken ölçüm zaten elde olduğundan EK HESAP YOK;
#: donmuş/bayat iken periyot başına BİR kalıntı değerlendirmesi eklenir —
#: 500'de bir, yani iterasyon başına ~%0,2. Örnekleme alanı DEĞİŞTİRMEZ
#: (U'ya geri beslenmez), bu yüzden §11.3 bit-özdeşlik sözleşmesi ve
#: iterasyon sayıları etkilenmez.
DEFAULT_SCHEME_PROBE_EVERY = 500

#: PLATO EŞİĞİ: son ``SCHEME_PLATEAU_MIN_SAMPLES`` örneğin GÖRELİ yayılımı
#: (maks−min)/min bunun altındaysa ve örneklerin hepsi hedefin (tol_res)
#: ÜSTÜNDEyse kalıntı DURMUŞ sayılır. %1: yukarıdaki ölçümde dört katına
#: çıkan bütçenin oynattığı ‰3'ün üç katı, yani gerçek inişi (yakınsayan
#: koşularda kalıntı pencere başına mertebe düşer) plato sanmaz.
DEFAULT_SCHEME_PLATEAU_REL_TOL = 0.01

#: PLATO için gereken en az örnek (üç pencere): iki örnek "durdu" demeye
#: yetmez — inişin yavaşladığı tek pencere de aynı görünür.
SCHEME_PLATEAU_MIN_SAMPLES = 3

#: AÇIK YOL PLATO-DONDURMA TETİĞİ — ÖLÇÜLMÜŞ SABİTLER (ÖH D37 A3a cfd-kok-a,
#: OH-DK-12 onarımı; kilit docs/scofield/raw/OH/A3a/cfd-kok-a/olcut_kulvar.json).
#:
#: KUSUR (DK kampanyası, 24 Eyl 2026): plato tespiti rampa biter bitmez
#: (it = ramp_iters + 2·300 = 1001) sabit 300'lük iki pencereyi kıyaslıyor
#: ve ince ağda BAŞLANGIÇ GEÇİCİSİNİ plato sanıyordu — C1 240×48'de
#: donma 1001. iterasyonda (kalıntı 0,886 → 0,52, yalnız 0,23 mertebe
#: inmişken), şema kalıntısı 2,9e-2'de kaldı, debi satır-örtük köke göre
#: +1,78e-4 saptı, Richardson mertebesi 2,07 → 0,58. Aynı desen C3 96×24
#: (donma 1562, 0,8 mertebe) ve C7 standard (donma 1284, 0,33 mertebe).
#: Ölçülen GERÇEK minmod platoları ise ≥ 2,5 mertebe inişten sonraydı
#: (C1 120×24: donma 4455, 0,504 → ~1,5e-3; kök satır-örtük yolla 1,1e-6
#: bağıl aynı — yani geç dondurma DOĞRU kökü veriyor).
#:
#: İKİ KAPI, ikisi de ağ boyundan bağımsız gerekçeli:
#:   1. İNİŞ KAPISI: dondurma ancak kalıntı, rampa sonu (it = ramp_iters)
#:      değerinin 10^PLATEAU_DESCENT_DECADES altına indikten SONRA
#:      tetiklenebilir. Mertebe cinsindendir: iterasyon sayısına değil
#:      kalıntı ORANINA bakar. 2,0 = ölçülen transient donmaları (≤ 0,8)
#:      ile ölçülen gerçek platolar (≥ 2,5) arasındaki boşluğun ortası.
#:   2. PENCERE ÖLÇEĞİ: iki kıyas penceresi max(PLATEAU_WINDOW_BASE,
#:      PLATEAU_WINDOW_PER_NI·ni) iterasyondur. Açık yerel-Δt yürüyüşünde
#:      bir bozuntunun alanı kat etme süresi ∝ ni/CFL iterasyon; 300'lük
#:      pencere 120×24'te ölçülerek seçilmişti (2,5·120 = 300, kalibrasyon
#:      aynen), 240×48'de 600, 384×96'da 960. Ölçeklenmezse ince ağda
#:      "yavaş ama sürekli iniş" plato sanılır (C1 240×48, it = 1001:
#:      recent/before = 1,018).
#: Tetik durumu koşum çıktısında ``limiter_freeze`` bloğunda SAYIYLA
#: yayımlanır (iniş mertebesi, pencere, kapı); GCI geçerlilik kapısı
#: (hrma/utils/gci.py) 'not_evaluated' seviyeyi bu bloktan okur.
PLATEAU_WINDOW_BASE = 300
PLATEAU_WINDOW_PER_NI = 2.5
PLATEAU_DESCENT_DECADES = 2.0
#: "Plato" = son pencerenin minimumu, önceki pencere minimumunun bu
#: oranından büyük (kalıntı pencere başına %10'dan az düşüyor). 2026-08
#: değeri AYNEN; ölçeklenen pencere ile birlikte okunur.
PLATEAU_STALL_RATIO = 0.9
#: KALICI STALL yolu (ÖH D37 A3a cfd-kok-a, ölçüldü — tests/cfd/test_giris_bc.py
#: hibrit CR 10 vakası, 120×24, Pb = 2 kPa, şok yok, sensör sessiz): canlı
#: minmod kalıntısı rampa sonundan yalnız 1,07 mertebe inip 0,08-0,14
#: bandında SALINIYOR (4000 → 20000 iterasyon: 7,9e-2, 7,7e-2, 1,2e-1,
#: 1,4e-1, 1,3e-1) — geniş, yavaş (M ≈ 0,06) kamarada minmod anahtarlaması.
#: Yalnız iniş kapısıyla (2 mertebe) bu koşu HİÇ donmuyor ve 20000
#: iterasyonda not_converged kalıyordu; oysa ESKİ tetik ~1000'de dondurup
#: 5,7e-10'a iniyor ve debi quasi-1B'ye %0,078 tutuyordu (testin ölçümü).
#: Geçici ile platoyu ayıran şey İNİŞ DERİNLİĞİ DEĞİL SÜREdir: geçici bir
#: tümsek TEK pencere sürer ve bir sonraki pencerede iniş sürer (C1 240×48
#: ÖNCE: it 1001 recent/before 1,018 → 1301'de 0,454; C3 96×24 → 0,59;
#: C7 standard 0,93 → 0,45), plato ise pencere pencere sürer. Bu yüzden
#: iki yol: (a) iniş kapısı + 2 pencere stall (yukarıdaki), (b) iniş
#: kapısından BAĞIMSIZ, PLATEAU_PERSIST_WINDOWS·pencere uzunluğunda iki
#: ardışık blokta stall (3 pencere = 900 it 120×24'te, 1800 it 240×48'de).
#: Hangi yolun ateşlediği ve o andaki iniş mertebesi limiter_freeze'de
#: yayımlanır; GCI geçerlilik kapısı iniş mertebesini okur (erken donma →
#: o seviyeden GCI yazılmaz — OH-DK-12 dersi korunur).
PLATEAU_PERSIST_WINDOWS = 3

TURBULENCE_MODELS = ('none', 'sa_neg')
TURBULENCE_NONE, TURBULENCE_SA_NEG = TURBULENCE_MODELS

_ASSUMPTIONS = (
    'steady',                    # kararlı hâl (yerel Δt, zaman doğru değil)
    'axisymmetric',              # 2B eksenel simetri, döngüsüz (swirl yok)
    'inviscid',                  # Euler: viskozite/sınır tabaka yok
    'adiabatic',                 # cidara ısı kaybı yok
    'calorically_perfect_gas',   # sabit gamma ve R
)

#: Viskoz koşunun varsayım listesi: 'inviscid' ve 'adiabatic' DÜŞER
#: (ikisinin yerine ne geldiği aşağıda), kalanlar aynen sürer.
_VISCOUS_ASSUMPTION_DROPS = ('inviscid', 'adiabatic')


@dataclass(frozen=True)
class ViscousOptions:
    """Viskoz koşu seçenekleri (viskoz tasarım belgesi §5.1, §5.4, §5.6).

    Sürücüye ``solve_steady_axisym(..., viscous=ViscousOptions(...))``
    olarak verilir; VERİLMEZSE (varsayılan ``None``) çözücü bugünkü Euler
    yoludur ve bit-özdeştir (§11.3 regresyon sözleşmesi).

    Alanlar:
        transport: ``gas_transport.GasTransport`` — μ(T), cp, Pr TEK
            kaynaktan (``resolve_gas_transport`` ile kurulur).
        wall_thermal: ``'isothermal'`` | ``'adiabatic'`` — VARSAYILAN YOK
            (viscous.py'nin sözleşmesi; çağıran seçer, beyan edilir).
        T_wall: izotermal duvar sıcaklığı [K], skaler ya da (ni,).
        T_wall_source: T_wall'ın kaynağının beyanı (izotermalde zorunlu).
        c_visc: viskoz Δt katsayısı (varsayılan ÖLÇÜLEN DEFAULT_C_VISC).
        corrected: yüz gradyanı düzeltmesi (Blazek §5.3.2); ``False``
            yalnız karşılaştırma/bekçi içindir.
        wall_bc: MUSCL hayalet aynası — viskoz koşunun doğrusu
            ``'noslip'``; ``'slip'`` yalnız ÖLÇÜM karşılaştırması içindir
            (fark A1 turunda ölçüldü, test_boru_laminer.py).
        skew_iters: gradyan çarpıklık süpürme sayısı (None → yakınsayana
            dek; gradients.py sözleşmesi).
        turbulence: ``'none'`` (VARSAYILAN — laminer V1 yolu, bit-özdeş) |
            ``'sa_neg'``. İkincisi SA-neg taşınım denklemini ortalama akış
            çevriminin YANINDA, AYRIK (segregated) skaler üç-köşegen olarak
            çözer (§5.5) ve kapanışı μ_t = ρν̃·f_v1 ile viskoz akıya taşır.
        sa_scheme: SA taşınım şeması (``sa_neg.SA_CONVECTION_SCHEMES``;
            varsayılan birinci mertebe yukarı-akış — §5.5).
        sa_freestream_ratio: ν̃_∞/ν_∞ oranı (ICCFD7-1902 Denklem 8 bandı
            [3, 5]; bant DIŞI değer ``sa_neg.freestream_nu_tilde``
            tarafından REDDEDİLİR — burada ikinci bir kapı yok).
        sa_nu_tilde_inf: ν̃_∞'ı doğrudan vermek için [m²/s] (None →
            başlangıç alanının GİRİŞ KOLONUNDAN ölçülen ν_∞ ile orandan
            kurulur; hangisi olduğu koşum beyanında görünür).
        sa_density_correction: ICCFD7-1902 Denklem 9'un ∇ρ terimi
            (varsayılan AÇIK; kapatmak SA'yı değiştirir — yalnız ölçüm).
    """

    transport: object
    wall_thermal: str
    T_wall: object = None
    T_wall_source: str = None
    c_visc: float = DEFAULT_C_VISC
    corrected: bool = True
    wall_bc: str = WALL_BC_NOSLIP
    skew_iters: int = None
    turbulence: str = TURBULENCE_NONE
    sa_scheme: str = SA_CONVECTION_SCHEMES[0]
    sa_freestream_ratio: float = SA_FREESTREAM_CHI_BAND[0]
    sa_nu_tilde_inf: float = None
    sa_density_correction: bool = True

    def __post_init__(self):
        """Kapsam kapıları: sessiz varsayılana düşme yok."""
        if self.turbulence not in TURBULENCE_MODELS:
            raise ValueError(
                f'turbulence {self.turbulence!r} tanımsız — geçerli kipler '
                f'{TURBULENCE_MODELS}. Varsayılan {TURBULENCE_NONE!r} '
                'LAMİNER koşudur (V1 yolu); türbülans açık bir seçimdir ve '
                'koşum beyanında görünür.')
        if self.sa_scheme not in SA_CONVECTION_SCHEMES:
            raise ValueError(
                f'sa_scheme {self.sa_scheme!r} tanımsız — geçerli şemalar '
                f'{SA_CONVECTION_SCHEMES} (sa_neg.py sözleşmesi).')

    @property
    def turbulent(self):
        """SA açık mı? (Beyan ve dallanma TEK ifadeden okunur.)"""
        return self.turbulence == TURBULENCE_SA_NEG

    def residual_kwargs(self):
        """viscous_residual'ın ısıl duvar sözleşmesine giden argümanlar."""
        kw = dict(wall_thermal=self.wall_thermal, corrected=self.corrected,
                  skew_iters=self.skew_iters)
        if self.wall_thermal != 'adiabatic' or self.T_wall is not None:
            # Kapının KENDİSİ viscous.py'dedir (tek yer). Adyabatik kipte
            # T_wall verilmemişse hiç geçirilmez; VERİLMİŞSE bilerek
            # geçirilir ki oradaki "adyabatikte T_wall yasak" kapısı
            # ateşlesin — çelişkili girdi sessizce YUTULMAZ.
            kw.update(T_wall=self.T_wall, T_wall_source=self.T_wall_source)
        return kw


def _column_wall_radius(grid):
    """Kolon başına duvar yarıçapı (hücre kolonunun iki düğümünün ortalaması)."""
    r_wall_nodes = grid.R[:, -1]
    return 0.5 * (r_wall_nodes[:-1] + r_wall_nodes[1:])


def _isentropic_initial_state(grid, P0, T0, gamma, R, Pb=None):
    """Kolon bazlı izantropik başlangıç alanı (yalnız tahmin; beyan üstte).

    IRAKSAK DAL SEÇİMİ (Aşama 1B, ölçülen gerekçe): varsayılan süpersonik
    dal. Pb verilmişse ve tam-süpersonik çözümün çıkış statik basıncından
    BÜYÜKSE ıraksak bölge SES-ALTI dalda başlatılır — aksi hâlde çıkış
    kolonu ses-üstü doğar, çıkış BC'si Pb'yi hiç uygulamaz (ses-üstü çıkış
    = tam dışdeğerleme) ve tam-süpersonik alan ayrık SABİT NOKTA olarak
    kalırdı: iç şok hiç oluşmaz (ölçüldü; arka-basınç vakası testinin
    varlık sebebi). Bu yalnız başlangıç TAHMİNİDİR: şokun yeri/varlığı
    çözücünün kendi dinamiğiyle oturur ve analitik 1B referansa karşı
    bağımsız test edilir (tests/cfd/test_normal_sok.py)."""
    g = float(gamma)
    r_w = _column_wall_radius(grid)
    area = np.pi * r_w ** 2
    i_throat = int(np.argmin(area))
    a_star = float(area[i_throat])
    ni, nj = grid.ni, grid.nj
    divergent_supersonic = True
    if Pb is not None:
        ratio_exit = max(float(area[-1] / a_star), 1.0)
        m_exit_sup = mach_from_area_ratio(ratio_exit, g, supersonic=True)
        _, p_ratio_exit, _ = isentropic_ratios(m_exit_sup, g)
        divergent_supersonic = bool(float(Pb) <= float(P0) * p_ratio_exit)
    w = np.empty((ni, nj, 4))
    for i in range(ni):
        ratio = max(float(area[i] / a_star), 1.0)
        mach = mach_from_area_ratio(
            ratio, g, supersonic=(divergent_supersonic and i > i_throat))
        t_ratio, p_ratio, _ = isentropic_ratios(mach, g)
        temp = float(T0) * t_ratio
        p = float(P0) * p_ratio
        rho = p / (float(R) * temp)
        w[i, :, 0] = rho
        w[i, :, 1] = mach * np.sqrt(g * float(R) * temp)
        w[i, :, 2] = 0.0
        w[i, :, 3] = p
    return prim_to_cons_axisym(w[..., 0], w[..., 1], w[..., 2], w[..., 3],
                               g), i_throat


def _section_averages(U, grid, gamma):
    """Kolon (kesit) ortalamaları — hacim ağırlıklı (beyan: kesit ortalaması
    hücre hacmi ağırlığıyla; ince kolonda alan ağırlığına eşdeğer)."""
    g = float(gamma)
    w = cons_to_prim_axisym(U, g)
    a = np.sqrt(g * w[..., 3] / w[..., 0])
    mach = np.sqrt(w[..., 1] ** 2 + w[..., 2] ** 2) / a
    vol = grid.volume
    wsum = np.sum(vol, axis=1)
    m_avg = np.sum(mach * vol, axis=1) / wsum
    p_avg = np.sum(w[..., 3] * vol, axis=1) / wsum
    z_avg = np.sum(grid.z_centers * vol, axis=1) / wsum
    return z_avg, m_avg, p_avg


def solve_steady_axisym(grid, P0, T0, gamma, R, Pb=None,
                        cfl_start=DEFAULT_CFL_START,
                        cfl_max=DEFAULT_CFL_MAX,
                        ramp_iters=DEFAULT_RAMP_ITERS,
                        max_iters=DEFAULT_MAX_ITERS,
                        tol_res=DEFAULT_TOL_RES,
                        settle_window=DEFAULT_SETTLE_WINDOW,
                        settle_tol=DEFAULT_SETTLE_TOL,
                        freeze_settle_tol=DEFAULT_FREEZE_SETTLE_TOL,
                        second_order=True,
                        time_integrator='ssp_rk2',
                        cfl_implicit_max=DEFAULT_CFL_IMPLICIT_MAX,
                        implicit_slope_refresh=DEFAULT_IMPLICIT_SLOPE_REFRESH,
                        viscous=None,
                        initial_state=None,
                        outlet_subsonic_anchor=OUTLET_ANCHOR_EXTRAPOLATE,
                        y_plus_target=None):
    """Lüle iç akışını kararlı hâle sürer; beyanlı sonuç sözlüğü döndürür.

    Args:
        grid: AxisymGrid (grid_axisym; kontur → sample_nozzle_inner_contour).
        P0, T0: rezervuar durma basıncı [Pa] ve sıcaklığı [K].
        gamma, R: kalorik mükemmel gaz sabitleri (motor çözücüsünden;
            varsayılan yok, eksikse çağıran reddetmeli).
        Pb: geri basınç [Pa]; None → çıkışta tam dışdeğerleme (süpersonik).
        time_integrator: 'ssp_rk2' (varsayılan — AÇIK yol, bugünkü kodla
            bit-özdeş) | 'line_implicit_j' (j-yönü satır-örtük gevşetme,
            relax_implicit.py; viskoz tasarım belgesi §4.2/§5.6).
            HÜKÜM-NÖTRLÜK SÖZLEŞMESİ: seçim yalnız köke gidiş YOLUNU
            değiştirir, yakınsanan çözümü ve hüküm ölçütlerini (aşağıdaki
            üçlü) DEĞİŞTİRMEZ — bekçisi tests/cfd/test_satir_ortuk.py.
        cfl_implicit_max: satır-örtük yol CFL rampası tavanı (yalnız
            time_integrator='line_implicit_j' iken kullanılır; varsayılan
            ölçümden, DEFAULT_CFL_IMPLICIT_MAX tanımı yanında).
        implicit_slope_refresh: satır-örtük yolda MUSCL eğimlerinin
            periyodik tazeleme aralığı [iterasyon] (yalnız örtük +
            second_order iken; gerekçe ve ölçüm
            DEFAULT_IMPLICIT_SLOPE_REFRESH tanımı yanında). Açık yolun
            plato-dondurma sezgisi örtük dalda KULLANILMAZ (ölçülen
            yanlış tetikleme: kalıntı 0,93'te donup kökü %1,47 saptırdı).
        freeze_settle_tol: satır-örtük yolda oturma-tetikli KALICI eğim
            dondurmasının TETİK eşiği (V3 tetik/hüküm ayrımı). Hüküm
            eşiği ``settle_tol`` AYRIDIR ve değişmemiştir; ikisi aynı
            bant aritmetiğini (_settle_band) farklı eşiklerle okur.
            ``None`` (varsayılan) → tetik eşiği settle_tol'a eşit
            (tarihsel davranış, bit-özdeş); gevşetme ölçülmüş bir vaka
            kararıdır — hangi vakada ne seçileceği ve gevşek varsayılanın
            neden REDDEDİLDİĞİ (ölçülen kök zehirlenmesi)
            DEFAULT_FREEZE_SETTLE_TOL tanımında. Etkin değer koşum
            beyanında (inputs['freeze_settle_tol']) görünür.
        viscous: ``ViscousOptions`` ya da None (VARSAYILAN). None →
            bugünkü Euler yolu, BİT-ÖZDEŞ (§11.3 sözleşmesi: viskoz
            kapalıyken tek bir aritmetik işlem bile eklenmez).
            Verilirse kalıntı KOMPOZİSYONDUR (§5.1):
            ``R = residual_axisym(...) + viscous_residual(...)``; yerel Δt
            viskoz spektral yarıçapla genişler (§5.6, Blazek §6.1.4
            biçimi, katsayı DEFAULT_C_VISC — ölçüldü) ve satır-örtük yolda
            j-yüzlerinin viskoz Jacobian'ı sisteme TAM blok girer.
            ``ViscousOptions(turbulence='sa_neg')`` ayrıca SA-neg taşınım
            denklemini AYRIK (segregated) skaler üç-köşegen olarak aynı
            j-satırlarında çözer (§5.5) ve kapanışı μ_t ile viskoz akıya
            taşır; ``'none'`` (varsayılan) LAMİNER yoldur ve SA kodu o
            dalda HİÇ çalışmaz.
        initial_state: (ni, nj, 4) başlangıç alanı ya da None. None →
            izantropik tahmin (bugünkü yol). Viskoz koşuyu YAKINSAMIŞ
            EULER alanından başlatmak belgenin "bedava hızlandırma"
            önerisidir (§5.6); kazanç VARSAYILMAZ, koşum çıktısındaki
            iterasyon/süre sayılarıyla ölçülür.
        outlet_subsonic_anchor: 'extrapolate' (VARSAYILAN — bugünkü
            davranış, Euler yolu bit-özdeş) | 'core_pressure'. İkincisi
            YALNIZ Pb=None çıkışında etkilidir ve ses-altı alt tabakanın
            basıncını çekirdeğe bağlar (viskoz devir kusuru #2; künye
            euler_core.OUTLET_ANCHOR_BASIS, KAPI ölçümü
            tests/cfd/test_viskoz_entegrasyon.py). Seçim NE OLURSA OLSUN
            çıkıştaki ses-altı hücre sayısı ölçülüp ``outlet_bc``
            bloğunda yayımlanır: çapa kapalıyken kusur SESSİZ kalmaz.
        y_plus_target: hedef y⁺ (ör. 1,0) ya da None. Yalnız BEYAN
            içindir: viskoz koşuda gerçekleşen y⁺ ölçülür ve hedefe göre
            sapması yayımlanır (``viscous['y_plus_loop']``). Sürücü
            ızgarayı KENDİLİĞİNDEN değiştirmez (sessiz düzeltme yok);
            yeniden ızgaralama çağıranın kararıdır ve ``regrid_count``
            ile beyan edilir (tasarım §5.7).
        Diğerleri: sürücü ayarları (modül sabitlerinde beyanlı).

    Returns:
        dict: converged, convergence_basis, inlet_bc + inlet_bc_basis
        (giriş sınır koşulunun adı ve künyesi), iterations, residual_history,
        korunum bütçesi (kütle/enerji akıları + bağıl artıklar), fields
        (ρ, u_z, u_r, p, T, M), section_average, throat, wall_pressure_Pa,
        not_modelled, assumptions, inputs, runtime_s. Yakınsamasa da sonuç
        döner (converged=False); NaN'da 'diverged' beyanı.
    """
    t_start = time.perf_counter()
    g = float(gamma)
    P0 = float(P0)
    T0 = float(T0)
    Rs = float(R)
    if P0 <= 0.0 or T0 <= 0.0 or Rs <= 0.0:
        raise ValueError('P0, T0 ve R pozitif olmalı (uydurma yedek yok).')
    if not (1.0 < g < 2.0):
        raise ValueError('gamma (1, 2) aralığında olmalı (mükemmel gaz).')
    if time_integrator not in TIME_INTEGRATORS:
        raise ValueError(f'time_integrator {TIME_INTEGRATORS} içinden '
                         f'olmalı; gelen: {time_integrator!r} (sessiz '
                         'varsayılana düşme yok).')
    if outlet_subsonic_anchor not in OUTLET_ANCHOR_MODES:
        raise ValueError(
            f'outlet_subsonic_anchor {OUTLET_ANCHOR_MODES} içinden olmalı; '
            f'gelen: {outlet_subsonic_anchor!r} (sessiz varsayılana düşme '
            'yok).')
    # --- SÜRÜCÜ AYARI KAPILARI (ÖH defter P6B1-06) ----------------------
    # Bu kapılar YOKTU. Ölçüldü (a2/once.json): altı ayarın üçü HAM
    # istisnayla (IndexError / ZeroDivisionError) ölüyor, üçü SESSİZCE
    # kabul edilip hükmü yanlış temele oturtuyordu. Ne ham çöküş ne sessiz
    # kabul fail-closed'dur: her ret ALANI ADIYLA söyler.
    def _tam_sayi_kapisi(deger, ad, alt_sinir, gerekce):
        if isinstance(deger, bool) or not isinstance(
                deger, (int, np.integer)):
            raise ValueError(
                f'{ad} TAM SAYI olmalı (iterasyon sayacı) — gelen '
                f'{deger!r}. Kesirli/bool sayaç döngü aritmetiğinde '
                'sessizce kırpılır.')
        deger = int(deger)
        if deger < alt_sinir:
            raise ValueError(
                f'{ad} >= {alt_sinir} olmalı — gelen {deger}. {gerekce} '
                '(Ölçüm ve gerekçe MIN_MAX_ITERS / MIN_RAMP_ITERS '
                'tanımında — sessiz varsayılana düşme yok.)')
        return deger

    max_iters = _tam_sayi_kapisi(
        max_iters, 'max_iters', MIN_MAX_ITERS,
        'Sıfır ya da negatif tavanda döngü HİÇ dönmez: kalıntı geçmişi '
        'boş kalır ve yayımlanacak hiçbir ölçüm ÜRETİLMEZ — eskiden bu '
        'yol ham IndexError ile çöküyordu.')
    ramp_iters = _tam_sayi_kapisi(
        ramp_iters, 'ramp_iters', MIN_RAMP_ITERS,
        'Rampa uzunluğu sıfırsa bölme tanımsızdır (eski hâli: ham '
        'ZeroDivisionError); negatifse rampa GERİ işler ve CFL '
        'cfl_start\'ın altına iner — belgelenen "cfl_start -> cfl_max" '
        'davranışının tersi.')

    # tol_res: hüküm eşiği. Pozitif değilse ``res_norm < tol_res`` HİÇBİR
    # zaman doğru olamaz (kalıntı normu tanım gereği >= 0) — yani hüküm
    # ULAŞILAMAZ hâle gelir ve koşu her defasında tavanı yakıp
    # converged=False döner. Ölçüldü: tol_res 0 ve -1 sessizce kabul
    # ediliyor, kullanıcı "yakınsamıyor" sanıyordu. Eşiğin ulaşılabilir
    # olması ölçütün TANIMIDIR, uydurma bir alt sınır değildir.
    tol_res = float(tol_res)
    if not np.isfinite(tol_res) or tol_res <= 0.0:
        raise ValueError(
            f'tol_res pozitif ve sonlu olmalı — gelen {tol_res!r}. '
            '(Yakınsama eşiği kalıntı NORMU ile karşılaştırılır; norm '
            'tanım gereği negatif olamaz, dolayısıyla pozitif olmayan '
            'eşik hükmü ULAŞILAMAZ kılar ve koşu sessizce tavanı yakar.)')

    # settle_tol: hüküm eşiği. Eski kapı bunu HİÇ denetlemiyordu; sadece
    # freeze_settle_tol=None yolundan türetilen tetik eşiği patlıyor ve
    # hata mesajı çağıranın HİÇ göndermediği ``freeze_settle_tol``
    # alanını suçluyordu (ölçüldü: settle_tol=0 ve -1e-3 için mesaj
    # "freeze_settle_tol pozitif ve sonlu olmalı" diyordu). Suçlanan alan
    # ADIYLA doğru olmalıdır.
    settle_tol = float(settle_tol)
    if not np.isfinite(settle_tol) or settle_tol <= 0.0:
        raise ValueError(
            f'settle_tol pozitif ve sonlu olmalı — gelen {settle_tol!r}. '
            '(Üç oturma bandının HÜKÜM eşiğidir; bant (maks−min)/|son| '
            'negatif olamayacağından pozitif olmayan eşikte "oturdu" '
            'hükmü kazanılamaz. Eğim-dondurma TETİĞİNİN eşiği '
            'freeze_settle_tol AYRI parametredir.)')

    # CFL rampası: işaret ve yön. Δt yerel CFL ile ÖLÇEKLENİR; negatif CFL
    # zamanı geri akıtır (fiziksel değil) ve cfl_max < cfl_start "rampa"yı
    # tersine çevirir — ikisi de sessizce kabul ediliyordu. Büyüklüğe ÜST
    # sınır KONMAZ: aşırı değerde koşu Δt-sonluluk kapısından
    # ``convergence_status='diverged'`` beyanıyla döner (ölçüldü:
    # cfl_max=1e6 -> 'diverged'), yani orada beyan ZATEN vardır ve
    # uydurma bir tavan eklenmez.
    cfl_start = float(cfl_start)
    cfl_max = float(cfl_max)
    for _ad, _v in (('cfl_start', cfl_start), ('cfl_max', cfl_max)):
        if not np.isfinite(_v) or _v <= 0.0:
            raise ValueError(
                f'{_ad} pozitif ve sonlu olmalı — gelen {_v!r}. (CFL yerel '
                'zaman adımının ÖLÇEĞİDİR; pozitif olmayan ölçek zaman '
                'adımını sıfırlar ya da geriye akıtır.)')
    if cfl_max < cfl_start:
        raise ValueError(
            f'cfl_max ({cfl_max:g}) >= cfl_start ({cfl_start:g}) olmalı: '
            'rampa cfl_start\'tan cfl_max\'a ÇIKAR (tasarım belgesi §2). '
            'Ters verilirse "rampa" iner ve yayımlanan davranış '
            'beyanıyla çelişir — sessiz kabul yok.')

    # --- HÜKÜM PENCERESİ KAPISI (ÖH defter P6B1-05) ---------------------
    # Bu kapı YOKTU: pencere hüküm ölçütünün (üç oturma bandı) TANIM
    # ALANIDIR ve 2'nin altında ölçüt kendini boş yere doğruluyordu —
    # ölçümü ve gerekçesi MIN_SETTLE_WINDOW tanımında. Kardeş kapı
    # (freeze_settle_tol) hemen aşağıda, aynı desende.
    if isinstance(settle_window, bool) or not isinstance(
            settle_window, (int, np.integer)):
        raise ValueError(
            'settle_window TAM SAYI olmalı (hüküm bandının iterasyon '
            f'penceresi) — gelen {settle_window!r}. Kesirli/bool pencere '
            'dilimlemede sessizce kırpılır ve hüküm kayar.')
    settle_window = int(settle_window)
    if settle_window < MIN_SETTLE_WINDOW:
        raise ValueError(
            f'settle_window >= {MIN_SETTLE_WINDOW} olmalı — gelen '
            f'{settle_window}. (Hüküm ölçütü SON settle_window iterasyonun '
            'bağıl bandıdır: bant (maks−min)/|son| bir YAYILIM ölçüsüdür ve '
            'iki ayrı örnek görmeden TANIMSIZDIR. 1 verilirse bant tam 0,0 '
            "çıkar ve 'oturdu' hükmü ilk iterasyondan itibaren KAZANILMADAN "
            'verilir; 0 verilirse hist[-0:] TÜM GEÇMİŞ demektir, "pencere '
            'yok" değil. Ölçüm ve gerekçe MIN_SETTLE_WINDOW tanımında — '
            'sessiz varsayılana düşme yok.)')
    if freeze_settle_tol is None:
        # Varsayılan: tetik eşiği hüküm eşiğine eşit (tarihsel davranış,
        # bit-özdeş — gevşetmenin neden varsayılan OLMADIĞI ölçümle
        # DEFAULT_FREEZE_SETTLE_TOL tanımında).
        freeze_settle_tol = float(settle_tol)
    else:
        freeze_settle_tol = float(freeze_settle_tol)
    if not np.isfinite(freeze_settle_tol) or freeze_settle_tol <= 0.0:
        raise ValueError(
            'freeze_settle_tol pozitif ve sonlu olmalı — gelen '
            f'{freeze_settle_tol!r}. (Eğim-dondurma TETİĞİNİN eşiğidir; '
            'hüküm eşiği settle_tol AYRI parametredir — V3 tetik/hüküm '
            'ayrımı, gerekçe DEFAULT_FREEZE_SETTLE_TOL tanımında.)')

    U, i_throat = _isentropic_initial_state(grid, P0, T0, g, Rs, Pb=Pb)
    if initial_state is not None:
        U0 = np.asarray(initial_state, dtype=float)
        if U0.shape != U.shape:
            raise ValueError(
                f'initial_state biçimi {U.shape} olmalı — gelen {U0.shape}. '
                '(Sıcak başlangıç ancak AYNI ızgarada meşrudur; ızgaralar '
                'arası aktarım ayrı bir katmandır, sessizce yapılmaz.)')
        if not np.all(np.isfinite(U0)):
            raise ValueError('initial_state sonlu olmalı (NaN/Inf yok).')
        U = U0.copy()
    # Izgara sabiti yüzey geometrisi BİR kez (hoist; bit-özdeşlik bekçili —
    # tests/cfd/test_performans.py). area_i/area_j aynı diziden dilimlenir.
    geom = precompute_geometry(grid)
    area_i = geom['area_i']
    area_j = geom['area_j']

    # ---- viskoz katman (opt-in; kapalıyken bu blok HİÇ çalışmaz) ----
    wall_bc = WALL_BC_SLIP
    grad_geom = None
    visk_kw = None
    visk_i_pay = None
    if viscous is not None:
        wall_bc = viscous.wall_bc
        grad_geom = precompute_gradient_geometry(grid)
        visk_kw = viscous.residual_kwargs()
        # Viskoz Δt'nin i-yüz payı (satır-örtük yolda kullanılır): viskoz
        # spektral yarıçap Σ_yüz Λ_v olduğundan ve Λ_v ∝ |S|² olduğundan
        # i payı SALT GEOMETRİKTİR — fizik kısmı (μ/Pr, 1/ρ) yüzler
        # arasında ortaktır ve sadeleşir. Böylece i-yalnız viskoz sınır,
        # viscous.py'nin formülünü İKİNCİ KEZ yazmadan elde edilir.
        visk_i_pay = viscous_i_face_share(area_i, area_j)

    # Kalıntı çağrılarının ORTAK sınır kipleri TEK sözlükte: yürüyüşteki
    # çağrılar, ara RK aşaması ve nihai bütçe çağrısı sessizce ayrışamaz
    # (çıkış çapası bir çağrıda unutulsaydı kalıntı ile hüküm farklı
    # sınır koşulundan doğardı — bekçisi test_giris_bc.py'de).
    bc_kw = dict(wall_bc=wall_bc,
                 outlet_subsonic_anchor=outlet_subsonic_anchor)

    # ---- SA-neg katmanı (türbülans opt-in; 'none' dalında HİÇ çalışmaz) ----
    sa = None
    if viscous is not None and viscous.turbulent:
        sa = _sa_initial_state(grid, U, g, Rs, viscous)

    def _sinir_primitifleri(state):
        """Giriş/çıkış yüzü primitifleri — euler_core'un KENDİ hayaleti."""
        wl = cons_to_prim_axisym(state, g)
        return (inlet_state_from_stagnation(wl[0], g, Rs, P0, T0),
                _outlet_state(wl[-1], geom['n_out_hat'], g, Pb,
                              subsonic_anchor=outlet_subsonic_anchor))

    def _viskoz_kalinti(state):
        """R_viskoz + aux (yalnız viskoz koşuda çağrılır).

        Sınır yüzü Dirichlet verisi euler_core'un KENDİ sınır durumu
        fonksiyonlarından alınır (inlet_state_from_stagnation, _outlet_
        state): viskoz katman giriş/çıkış sınır koşulunun İKİNCİ bir
        gerçeklemesini yazmaz — aynı hayalet durumu, aynı beyan.

        SA açıkken μ_t O ANKİ SA alanından geçirilir (Boussinesq kapanışı
        viscous.py'de TAŞINIR, orada çözülmez).
        """
        w_in, w_out = _sinir_primitifleri(state)
        return viscous_residual(
            grid, state, viscous.transport, R=Rs, geom=geom,
            grad_geom=grad_geom,
            mu_t=None if sa is None else sa['mu_t'],
            inlet_face_primitives=w_in, outlet_face_primitives=w_out,
            **visk_kw)

    def _viskoz_dt(state, cfl_now, eksenel):
        return viscous_local_dt(state, grid, g, Rs, cfl_now,
                                viscous.transport, viscous.c_visc,
                                geom=geom, area_i=area_i, area_j=area_j,
                                axial_only=eksenel, i_face_share=visk_i_pay,
                                mu_t=None if sa is None else sa['mu_t'])

    def _sa_adim(state, dt_now, gradyanlar):
        """SA-neg'in AYRIK (segregated) çevrimi — bir iterasyonluk adım.

        Sıra (§5.5'in "ortalama akış 4×4 çevriminin YANINA" maddesi):
        ortalama akış kalıntısı O ANKİ μ_t ile kurulur, SA aynı durumda ve
        o kalıntının KULLANDIĞI hız gradyanlarıyla (Ω) çözülür, μ_t
        güncellenir, sonra ortalama akış ilerletilir. Böylece bir adım
        içinde iki denklem AYNI durumu görür.

        Returns:
            ``True`` → adım sağlam; ``False`` → fiziksel olmayan/sonlu
            olmayan durum (sürücü 'diverged' beyanına düşer, İSTİSNA
            SIZMAZ — solve_block_tridiag'ın giriş kapısına NaN gitmez).
        """
        w_in, w_out = _sinir_primitifleri(state)
        return _sa_update(sa, state, dt_now, gradyanlar, grid, geom,
                          grad_geom, g, Rs, viscous, w_in, w_out)

    # Kalıntı ölçeği: ρ₀·a₀/L (boyutsuzlaştırma beyanı — docstring)
    rho0 = P0 / (Rs * T0)
    a0 = np.sqrt(g * Rs * T0)
    length = float(grid.Z[-1, 0] - grid.Z[0, 0])
    res_scale = rho0 * a0 / length
    vol = grid.volume
    vol_sum = float(np.sum(vol))
    if sa is not None:
        # SA kalıntısının ölçeği ORTALAMA AKIŞINKİNDEN TÜRETİLİR: ρν̃'nın
        # birimi ρ'nunkinin ν̃_∞ katıdır, yani aynı boyutsuzlaştırma
        # (ρ₀a₀/L) ν̃_∞ ile çarpılır. İkinci bir ölçek uydurulmaz.
        sa['res_scale'] = res_scale * sa['nu_tilde_inf']

    res_hist = []
    mdot_in_hist = []
    mdot_out_hist = []
    mach_throat_hist = []
    diverged = False
    U_last_finite = U.copy()

    # Sınırlayıcı dondurma (limiter freezing): minmod salınımı kararlı-hâl
    # kalıntısını platoda bırakır (ölçüldü: 120×24'te ~1e-4'te takılma).
    # Plato tespitinde eğimler DONDURULUR ve iterasyon derin yakınsamaya
    # sürülür — kararlı-hâl pratiğinde standart (Venkatakrishnan, AIAA J.
    # 33(5), 1995 gerekçesi). Dondurma anı çıktıda beyan edilir.
    #
    # "ŞEMA MINMOD KALIR" İDDİASININ SINIRI (ÖH defter P6B1-03; bu cümle
    # eskiden kayıtsız şartsız yazılıydı ve YAYIMLANAN SAYIYA da
    # uygulanıyormuş gibi okunuyordu): dondurma AYRIKLAŞTIRMANIN mertebesini
    # değiştirmez — 2. mertebe MUSCL/minmod yeniden kurulumu yerinde kalır
    # ve mertebe kanıtı tests/cfd/test_sod.py'de zaman-doğru koşumdadır.
    # DEĞİŞEN, eğimlerin HANGİ DURUMDAN alındığıdır: donduktan sonra
    # yürüyüşün kalıntısı ve nihai bütçesi DONMUŞ eğim sisteminindir,
    # şemanın o alandaki canlı kalıntısı DEĞİL (ölçüldü 2026-08-28: donan
    # koşularda 44 ile 2,9e7 kat fark). Yayımlanan sayının sahibi bu yüzden
    # ayrıca ve ADIYLA beyan edilir (residual_operator / slope_state) ve
    # şemanın kendi ölçümü yanında yayımlanır (scheme_residual_norm).
    #
    # TAZELEME (Aşama 1B, ölçülen gerekçe): iç şoklu vakada plato, şok daha
    # yerine OTURMADAN tetiklenebilir (ölçüldü, 120×24 arka-basınç vakası:
    # 1698. iterasyonda donan BAYAT eğimler kalıntıyı 6e-3 bandında salınıma
    # kilitledi). Donduktan sonra plato SÜRÜYORSA eğimler güncel durumdan
    # YENİDEN alınır (Picard tarzı tazeleme); durum oturunca tazeleme
    # kendiliğinden kendi-tutarlı hâle gelir ve kalıntı derine iner
    # (ölçüldü: aynı vaka 5,4e-11'e indi). İzantropik (şoksuz) vakada donma
    # sonrası kalıntı inişte olduğundan plato yeniden tetiklenmez — davranış
    # 1A ile aynı kalır (bekçiler: tests/cfd/test_izantropik_lule.py).
    # Son dondurma anı + tazeleme sayısı çıktıda beyan edilir.
    frozen_slopes = None
    frozen_at = None
    freeze_count = 0
    # Pencere ağ boyuyla ölçeklenir; iniş kapısı rampa sonu kalıntısına
    # bağlıdır (gerekçe ve ölçüm PLATEAU_* sabitlerinde).
    plateau_window = max(int(PLATEAU_WINDOW_BASE),
                         int(round(PLATEAU_WINDOW_PER_NI * grid.ni)))
    ramp_end_residual = None
    freeze_descent_decades = None
    freeze_trigger = None

    def _settled(hist):
        # Bandın ARİTMETİĞİ tek yerdedir (_settle_band): hüküm ile
        # yayımlanan beyan (settle_bands) aynı sayıdan doğar; iki ayrı
        # gerçekleme sessizce ayrışırdı. Bant tanımsızsa (pencere dolmadı
        # ya da ölçek sıfır) NaN döner ve karşılaştırma False'tur —
        # "bilinmiyor" ASLA "oturdu" sayılmaz.
        band = _settle_band(hist, settle_window)
        return bool(band < settle_tol)

    def _freeze_settled(hist):
        # Eğim-dondurma TETİĞİ (V3 — tetik/hüküm ayrımı): AYNI bant
        # aritmetiği (_settle_band), AYRI eşik (freeze_settle_tol).
        # Parti 38'in dairesel kilidi tam buradaydı: tetik hükümle aynı
        # settle_tol'u okuyunca, dondurmanın gidereceği geveleme tetiğin
        # kendisini kilitliyordu (gerekçe ve ölçüm
        # DEFAULT_FREEZE_SETTLE_TOL tanımında).
        band = _settle_band(hist, settle_window)
        return bool(band < freeze_settle_tol)

    # Satır-örtük yolun eğim durumu (periyodik Picard tazelemesi —
    # DEFAULT_IMPLICIT_SLOPE_REFRESH gerekçesi). Açık yolda kullanılmaz.
    #
    # OTURMA-TETİKLİ KALICI DONDURMA (ölçülen gerekçe, V0 turu 2026-08-17):
    # periyodik tazeleme minmod gevelemesini her K iterasyonda yeniden
    # enjekte eder; 60×48 MUSCL'de kalıntı bu geveleme tabanında (3e-8,
    # tol'ün hemen üstü) asılı kaldı — hüküm büyüklükleri (debi/Mach)
    # ÇOKTAN OTURMUŞKEN. Tedavi: üç oturma bandı TETİK eşiğinde
    # (freeze_settle_tol — V3 tetik/hüküm ayrımı) sağlanmış ama kalıntı
    # eşiği aşılamamışsa eğimler O OTURMUŞ durumdan KALICI dondurulur
    # (Picard'ın vardığı öz-tutarlı nokta; açık yolun plato-dondurmasının
    # hüküm-tabanlı kardeşi). V0-V2'de tetik hüküm eşiğinin (settle_tol)
    # kendisini okuyordu; parti 38 bunun DAİRESEL KİLİT olduğunu ölçtü
    # (geveleme, tetiğin gerektirdiği oturmayı engelliyor — KAPI vakası
    # 1e-9'da hiç ateşlemedi) ve V3 tetiğe AYRI, beyanlı eşik getirdi
    # (varsayılanın ölçümü DEFAULT_FREEZE_SETTLE_TOL tanımında). Erken
    # yanlış tetiklemeye karşı ölçü: bant < 1e-4, hüküm büyüklüklerinin
    # 200 iterasyonda < %0,01 oynaması demektir — geçiş rejiminin O(1)
    # salınımı bunu sağlamaz (açık yol plato sezgisinin örtük dalda
    # ölçülen yanlış tetiklemesi — kalıntı 0,93'te donma — bu tetikte
    # olamaz). Dondurma anı, sebebi ve tetik eşiği çıktıda beyanlıdır.
    implicit_slopes = None
    implicit_frozen = False
    refresh_every = max(1, int(implicit_slope_refresh))
    freeze_reason = 'plato tespiti'

    # ------------------------------------------------------------------
    # YAYIMLANAN SAYI KİMİN? (ÖH defter P6B1-01/-03/-04/-08, onarım
    # dalgası 2026-08-28)
    #
    # Yürüyüşün her iterasyonda kullandığı eğim sistemi ŞEMANIN kendi
    # (canlı minmod) sistemi OLMAYABİLİR: (a) açık yolda plato-dondurma,
    # (b) örtük yolda oturma-tetikli kalıcı dondurma, (c) örtük yolda
    # tazeleme penceresinin ORTASI (eğimler K iterasyon boyunca donuk
    # taşınır). O hâllerde ``res_norm`` DONMUŞ/BAYAT operatörün
    # kalıntısıdır ve hüküm ile beyan bunu ADIYLA söylemek zorundadır.
    # ``_egim_canli`` her iterasyonda o iterasyonun operatörünü işaretler;
    # tek yerde (aşağıdaki üç dalın kendi içinde) kurulur, ikinci bir
    # gerçekleme yazılmaz.
    #
    # ÖLÇÜLDÜ (2026-08-28, bu depo; alanın canlı-minmod kalıntısı ⟷
    # yayımlanan kalıntı, ŞEMA/tol):
    #   açık yol, dondurma YOK  (izantropik 60×12) : oran 1,000000× (sağlam)
    #   açık yol, donma 4455    (izantropik 120×24): 2,90e7× , ŞEMA/tol 2,1e6
    #   açık yol, donma 26663   (şoklu 60×12)      : 44,3×   , ŞEMA/tol 44,2
    #   açık yol, donma 20895   (şoklu 120×24)     : 399×    , ŞEMA/tol 276
    #   örtük yol, donma 4253   (60×12 MUSCL)      : 19.772× , ŞEMA/tol 86,4
    #   örtük yol, DONMA YOK, bayat pencere        : 98,7×   , ŞEMA/tol 97,3
    _egim_canli = True
    #: Örtük yolda hükmün ÖZ-TUTARLILIK kapısında reddedilme sayısı.
    picard_red_sayisi = 0
    #: ŞEMA (canlı minmod) kalıntısının (iterasyon, değer) örnekleri —
    #: PLATO TESPİTİNİN tek veri kaynağı (OH-Z5-14). Periyodik örnekleme
    #: DEFAULT_SCHEME_PROBE_EVERY ile; kapının kendi ölçümleri de buraya
    #: düşer (onlar zaten hesaplanmıştır, ikinci hesap yapılmaz).
    _sema_ornekleri = []
    _sema_periyodu = max(1, int(DEFAULT_SCHEME_PROBE_EVERY))

    def _sema_ornek_ekle(iterasyon, deger, zorla=False):
        """Aynı iterasyona İKİNCİ örnek yazılmaz (pencere sahte daralmaz).

        ``zorla``: koşum sonundaki NİHAİ ölçüm aynı iterasyondaki
        örneğin YERİNE geçer — o ölçüm nihai alandan alınmıştır ve
        kapının kullandığı sayının ta kendisidir.
        """
        if _sema_ornekleri and _sema_ornekleri[-1][0] == int(iterasyon):
            if not zorla:
                return
            _sema_ornekleri[-1] = (int(iterasyon), float(deger))
            return
        _sema_ornekleri.append((int(iterasyon), float(deger)))


    def _sema_kalinti_normu(r_sema):
        """``r_sema`` kalıntısının yoğunluk L2 normu (yayımla AYNI ölçek)."""
        return float(np.sqrt(np.sum(r_sema[..., 0] ** 2 * vol) / vol_sum)
                     / res_scale)

    def _sema_operatoru(state):
        """ŞEMANIN KENDİ operatörü: eğimler CANLI minmod'dan (slopes=None).

        Döner: (kalıntı normu, kalıntı dizisi, aux, canlı eğimler).
        Viskoz koşuda yürüyüşün kalıntısıyla aynı bileşim kullanılır
        (Euler + viskoz), yoksa iki sayı farklı büyüklükler olurdu.
        """
        r_s, aux_s, egim_s = residual_axisym(
            state, grid, g, Rs, P0, T0, Pb=Pb, second_order=second_order,
            return_slopes=True, geom=geom, **bc_kw)
        if viscous is not None:
            r_s = r_s + _viskoz_kalinti(state)[0]
        return _sema_kalinti_normu(r_s), r_s, aux_s, egim_s

    it = 0
    while it < max_iters:
        cfl = cfl_start + (cfl_max - cfl_start) * min(1.0,
                                                     it / float(ramp_iters))
        if time_integrator == 'line_implicit_j' and second_order:
            # Tazeleme anı: eğimler güncel durumdan (canlı) alınır ve K
            # iterasyon boyunca donuk taşınır — canlı eğim limit döngüsü
            # ile bayat-kök sapması arasındaki ölçülmüş orta yol. Kalıcı
            # dondurmadan sonra tazeleme durur (beyan yukarıda).
            if (not implicit_frozen) and it % refresh_every == 0:
                r1, aux, implicit_slopes = residual_axisym(
                    U, grid, g, Rs, P0, T0, Pb=Pb,
                    second_order=second_order, return_slopes=True,
                    geom=geom, **bc_kw)
                # Eğimler TAM BU durumdan alındı: operatör canlı.
                _egim_canli = True
            else:
                r1, aux = residual_axisym(U, grid, g, Rs, P0, T0, Pb=Pb,
                                          second_order=second_order,
                                          slopes=implicit_slopes,
                                          geom=geom, **bc_kw)
                # Taşınan eğim: 1. mertebede eğim YOKTUR (operatör canlı),
                # 2. mertebede pencere ortası ya da kalıcı donma → bayat.
                _egim_canli = (not second_order) or implicit_slopes is None
        else:
            r1, aux = residual_axisym(U, grid, g, Rs, P0, T0, Pb=Pb,
                                      second_order=second_order,
                                      slopes=frozen_slopes, geom=geom,
                                      **bc_kw)
            _egim_canli = (not second_order) or frozen_slopes is None
        visk_fiziksel_disi = False
        if viscous is not None:
            # KOMPOZİSYON (§5.1): Euler kalıntısının İÇİNE yazılmaz,
            # üstüne EKLENİR — akı ıraksaması toplamda doğrusaldır.
            dudt_v, aux_v = _viskoz_kalinti(U)
            r1 = r1 + dudt_v
            # Fiziksel olmayan durumun TESPİTİ viskoz kalıntının kendi
            # sözleşmesinden gelir (viscous.py: ρ≤0 / p≤0 → NaN döner,
            # istisna atmaz). Kütle kalıntısı bu durumda bile SONLU
            # kalabilir (viskoz akı kütleye girmez; HLLC'nin np.where
            # seçimleri de sonlu üretebilir) — yani aşağıdaki res_norm
            # kapısı tek başına yetmez, ÖLÇÜLDÜ. Bu kapı olmadan sürücü
            # ıraksamış durumla Δt hesaplamaya girerdi; V1'de o yol gaz
            # taşınım katmanının pozitiflik kapısından ValueError'la
            # SIZIYORDU. Sızıntı bugün viscous.py tarafında da kapalı
            # (nonphysical_state, V2 paralel kalemi) — bu kapı artık TEK
            # savunma değil, ama sürücü sözleşmesinin ("istisna sızmaz,
            # 'diverged' beyanı döner") kendi katmanındaki ifadesi olarak
            # DURUR: iki katman birbirinin yedeğidir, biri kaldırılırsa
            # diğeri hâlâ sözleşmeyi taşır.
            visk_fiziksel_disi = not bool(np.all(np.isfinite(dudt_v)))
        res_norm = float(np.sqrt(np.sum(r1[..., 0] ** 2 * vol) / vol_sum)
                         / res_scale)
        _, m_sec, _ = _section_averages(U, grid, g)
        res_hist.append(res_norm)
        mdot_in_hist.append(aux['mass_flow_in_kg_s'])
        mdot_out_hist.append(aux['mass_flow_out_kg_s'])
        mach_throat_hist.append(float(m_sec[i_throat]))
        it += 1

        if (not np.isfinite(res_norm)) or visk_fiziksel_disi:
            diverged = True
            break
        U_last_finite = U.copy()

        # PLATO ÖRNEKLEMESİ (OH-Z5-14): şemanın KENDİ kalıntısı periyodik
        # ölçülür. Yürüyüş operatörü canlıysa sayı ZATEN elde (`res_norm`)
        # ve ek hesap yapılmaz; donmuş/bayat ise periyot başına bir
        # kalıntı değerlendirmesi eklenir. Örnek U'ya geri BESLENMEZ —
        # alan, iterasyon sayısı ve §11.3 bit-özdeşliği etkilenmez.
        if it % _sema_periyodu == 0:
            if _egim_canli:
                _sema_ornek_ekle(it, res_norm)
            else:
                _sema_ornek_ekle(it, _sema_operatoru(U)[0])

        if (res_norm < tol_res and _settled(mdot_in_hist)
                and _settled(mdot_out_hist)
                and _settled(mach_throat_hist)):
            if _egim_canli or time_integrator != 'line_implicit_j':
                break
            # ÖZ-TUTARLILIK KAPISI (ÖH defter P6B1-03/-08, örtük yol).
            # Örtük yolun eğim makinesi KENDİ gerekçesinde "Picard'ın
            # vardığı ÖZ-TUTARLI nokta" iddiasındadır (tazeleme periyodu
            # ve oturma-tetikli kalıcı dondurma beyanları). Ölçüm o
            # iddiayı çürüttü: hüküm anında eğimler bayat/donmuşken
            # yayımlanan kalıntı şemanınkinden 98,7× (bayat pencere) ve
            # 19.772× (donma 4253) küçüktü. Kapı, iddiayı ÜRÜNE bağlar:
            # hüküm ancak eğimler O ANIN durumundan tazelendikten SONRA
            # da eşiğin altındaysa verilir. Öz-tutarlı noktada tazeleme
            # hiçbir şeyi değiştirmez ve koşu aynı iterasyonda durur;
            # değiştiriyorsa nokta öz-tutarlı DEĞİLDİR, tazelenmiş
            # eğimler yürüyüşe konur ve iniş sürer (Picard). Ulaşılamazsa
            # koşu max_iters'ta converged=False ile döner — fail-closed,
            # iyimser sayı yayımlanmaz.
            #
            # AÇIK YOL KAPSAM DIŞI (beyanlı, ölçümle): oradaki dondurma
            # minmod LİMİT DÖNGÜSÜNÜN tedavisidir (Venkatakrishnan) ve
            # öz-tutarlılık İDDİA ETMEZ; ayrıca §11.3 bit-özdeşlik
            # sözleşmesinin dört dondurulmuş referansından ÜÇÜ donduran
            # koşulardır (data/cfd_referans/*.npz — ölçüm ŞEMA/tol 44 ...
            # 2,1e6). Açık yolun hüküm ekseni o referansların yeniden
            # üretilmesini gerektirir; bu partide YAPILMADI, açık yol
            # yalnız ADIYLA beyan eder (residual_operator alanı).
            #
            # OH-Z5-19 (ÖH D30, fea-cfd a1) — KAPSAM KARARI ÖLÇÜLDÜ,
            # AÇILMADI. Dört referansın dördü de bugün converged=True
            # yayımlıyor; kapı açık yola genişletilseydi ÜÇÜNDE bayrak
            # True → False DÖNERDİ ve §11.3'ün bit karşılaştırdığı
            # skalerlerden biri (``converged``) kayardı. Ölçüldü
            # (docs/scofield/raw/OH/D30/fea-cfd/a1/once_z519.json):
            #   izantropik  60×12  op=scheme_live_minmod  ŞEMA/tol 0,9947
            #                      (kapsam içinde de GEÇERDİ, dönmez)
            #   şoklu       60×12  op=frozen_slopes  ŞEMA/yayım   44,29
            #   şoklu      120×24  op=frozen_slopes  ŞEMA/yayım  398,7
            #   izantropik 120×24  op=frozen_slopes  ŞEMA/yayım  2,903e7
            # Referansları YENİDEN DONDURMA YASAĞI (P10B4-14, Berke)
            # yürürlükte olduğu için kapsam bu dalgada GENİŞLETİLMEDİ;
            # karar Berke'nindir (ya referanslar yenilenir ya açık yol
            # hüküm eksenine alınmaz). Beyan kanalı bu arada susmaz:
            # scheme_residual_norm / scheme_residual_exceeds_tol /
            # residual_operator alanları sayıyı ADIYLA yayımlar.
            _sema_n, _r_s, _aux_s, _canli_egimler = _sema_operatoru(U)
            _sema_ornek_ekle(it, _sema_n)
            # Tazelenmiş eğimler yürüyüşe konur (kalıcı dondurma BOZULMAZ:
            # donma anı, sebebi ve sayacı olduğu gibi kalır — burada olan
            # bir Picard TAZELEMESİDİR, dondurmanın iptali değil; sayısı
            # picard_selfconsistency_rejections alanında yayımlanır).
            # Hüküm KABUL edilirse de kurulur: o zaman nihai bütçe de
            # hükmü kazandıran CANLI operatörden okunur.
            implicit_slopes = _canli_egimler
            if _sema_n < tol_res:
                break
            picard_red_sayisi += 1

        # Satır-örtük yol: oturma-tetikli KALICI dondurma (beyan döngü
        # öncesinde). Hüküm büyüklükleri TETİK eşiğinde (freeze_settle_
        # tol) oturmuş ama kalıntı eşiği minmod geveleme tabanında
        # aşılamıyorsa eğimler bu oturmuş durumdan dondurulur. Tetik,
        # hüküm bantlarının AYNI aritmetiğini AYRI eşikle okur (V3
        # tetik/hüküm ayrımı — parti 38'in dairesel kilidi: tetik hüküm
        # eşiğini paylaşınca KAPI vakasında hiç ateşleyemiyordu).
        if (time_integrator == 'line_implicit_j' and second_order
                and not implicit_frozen and res_norm >= tol_res
                and _freeze_settled(mdot_in_hist)
                and _freeze_settled(mdot_out_hist)
                and _freeze_settled(mach_throat_hist)):
            _, _, implicit_slopes = residual_axisym(
                U, grid, g, Rs, P0, T0, Pb=Pb,
                second_order=second_order, return_slopes=True, geom=geom,
                **bc_kw)
            implicit_frozen = True
            frozen_at = it
            freeze_count += 1
            freeze_reason = ('oturma tespiti: hüküm bantları tetik '
                             f'eşiğinde (freeze_settle_tol='
                             f'{freeze_settle_tol:g}) oturdu, kalıntı '
                             'geveleme tabanında')

        # Plato tespiti: rampa bitmiş + iki ardışık pencerede kalıntı
        # anlamlı düşmüyor → eğimleri dondur; donmuşken plato SÜRÜYORSA
        # güncel durumdan TAZELE (beyan yukarıda; şoklu vaka gerekçesi).
        #
        # YALNIZ AÇIK YOL (V0 ölçümü, 2026-08-17): dondurma sezgisi açık
        # yolun minmod stall'ı içindir ve eşiği açık inişin tarihçesine
        # göre ayarlıdır. Örtük yolun geçiş rejimi farklıdır — ÖLÇÜLDÜ
        # (60×12 MUSCL, CFL 25): sezgi 1001. iterasyonda kalıntı 0,93
        # iken tetiklendi, bayat eğim kökü debide analitikten %1,47
        # saptırdı (açık yol dondurmadan %0,066'ya iner). Örtük yol
        # dondurmasız derin yakınsıyor (ölçüm tabloları
        # tests/cfd/test_satir_ortuk.py); dondurma örtük dalda kapalı.
        #
        # ÖH D37 A3a cfd-kok-a (OH-DK-12): rampa sonu kalıntısı bir kez
        # kaydedilir; dondurma ancak (i) kalıntı ondan PLATEAU_DESCENT_
        # DECADES mertebe aşağı indikten sonra ve (ii) ağ boyuyla ölçekli
        # iki pencerede stall ölçülünce tetiklenir. İniş mertebesi
        # dondurma anında kaydedilir ve yayımlanır (limiter_freeze).
        if ramp_end_residual is None and it >= ramp_iters and res_hist:
            ramp_end_residual = float(res_hist[ramp_iters - 1])
        if (second_order and time_integrator == 'ssp_rk2'
                and it > ramp_iters + 2 * plateau_window
                and (frozen_at is None
                     or it >= frozen_at + 2 * plateau_window)):
            recent = min(res_hist[-plateau_window:])
            before = min(res_hist[-2 * plateau_window:-plateau_window])
            _inis = (float('nan') if not (ramp_end_residual
                                          and ramp_end_residual > 0.0
                                          and min(res_hist) > 0.0)
                     else float(np.log10(ramp_end_residual
                                         / min(res_hist))))
            # ŞOKLU AKIŞTA DONDURMA YOK (OH-DK-13, ölçüldü — ayrıştırma
            # deneyi docs/scofield/raw/OH/A3a/cfd-kok-a/ayristirma/, 120×24,
            # SOK_COZUCU tol 2e-6): hücre sensörü CANLI + dondurma KAPALI →
            # C2b converged 22157 it, son 2000 it ṁ bandı 1,0e-7; aynı kod
            # dondurma AÇIK → not_converged, 31 yeniden donma, bant 3,7e-5;
            # sensör KAPALI + dondurma açık → not_converged, bant %1,1;
            # birinci mertebe → converged 23569 it. Yani şoklu vakada
            # limit döngüsünün kaynağı dondur/tazele çevrimidir: şoka
            # komşu DONMUŞ eğimler şok profili oturdukça tutarsızlaşır,
            # donmuş operatörün kökü yoktur, kalıntı stall eder, 2·pencere
            # sonra yeniden donma operatörü adım gibi değiştirir (DK: 44-82
            # yeniden donma, ṁ yarı genliği %1). Sensör şok hücrelerinde
            # eğimi zaten sıfırlar; dondurma yalnız PÜRÜZSÜZ akışın minmod
            # stall'ı içindir ve yalnız sensör bayrağı BOŞKEN tetiklenir
            # (bayrak canlı sayımı o iterasyonun kalıntı çağrısından).
            _sok_var = int(aux.get('shock_sensor_cells', 0)) > 0
            _stall2 = bool(recent > PLATEAU_STALL_RATIO * before)
            # (b) KALICI stall: PLATEAU_PERSIST_WINDOWS·pencere uzunluğunda
            # iki ardışık blok (gerekçe PLATEAU_PERSIST_WINDOWS tanımında).
            _kw = int(PLATEAU_PERSIST_WINDOWS) * plateau_window
            _persist = False
            if (it > ramp_iters + 2 * _kw
                    and (frozen_at is None or it >= frozen_at + 2 * _kw)):
                _persist = bool(min(res_hist[-_kw:])
                                > PLATEAU_STALL_RATIO
                                * min(res_hist[-2 * _kw:-_kw]))
            _tetik = None
            if _stall2 and np.isfinite(_inis) and _inis >= PLATEAU_DESCENT_DECADES:
                _tetik = 'descent_gate'
            elif _persist:
                _tetik = 'persistent_stall'
            if _tetik is not None and not _sok_var:
                _, _, frozen_slopes = residual_axisym(
                    U, grid, g, Rs, P0, T0, Pb=Pb,
                    second_order=second_order, return_slopes=True,
                    geom=geom, **bc_kw)
                frozen_at = it
                freeze_count += 1
                if freeze_descent_decades is None:
                    freeze_descent_decades = (float(_inis) if np.isfinite(_inis)
                                              else None)
                    freeze_trigger = _tetik

        if time_integrator == 'line_implicit_j':
            # j-yönü satır-örtük gevşetme (relax_implicit.py; hüküm-nötr —
            # yalnız yol değişir). CFL rampası aynı biçim, tavan ölçülen
            # örtük tavandır: Δt'nin j-kısıtı örtük katmanla kalkar, açık
            # kararlılık sınırının üstüne çıkılır (tasarım belgesi §4.2).
            cfl_imp = cfl_start + (cfl_implicit_max - cfl_start) * min(
                1.0, it / float(ramp_iters))
            # Δt YALNIZ i-yüzlerinden: j yönü örtük olduğundan adımı
            # kısıtlamaz (belge §4.2; local_dt_axial docstring'inde
            # ölçülen gerekçe — tam toplam + büyük CFL nj merdiveninde
            # ıraksadı).
            if viscous is None:
                dt = local_dt_axial(U, grid, g, cfl_imp, area_i)
            else:
                dt = _viskoz_dt(U, cfl_imp, eksenel=True)
            # Fiziksel olmayan durum kapısı (ölçülen vaka: aşırı CFL'de
            # p<0 → a=NaN; kütle kalıntısı normu HLLC'nin np.where
            # seçimleriyle sonlu kalabildiğinden yukarıdaki res_norm
            # kapısı bunu her zaman yakalamaz — ölçüldü, CFL=100
            # taramasında implicit.py giriş kapısına düştü). Δt, ses hızı
            # üstünden aynı NaN sinyalini taşır: sonlu değilse koşu
            # 'diverged' beyanıyla döner (sürücü sözleşmesi; sessiz
            # yutma yok, hüküm de yok).
            if not np.all(np.isfinite(dt)):
                diverged = True
                break
            # SA ORTALAMA AKIŞTAN ÖNCE ilerletilir: iki denklem de AYNI
            # durumu (ve aynı hız gradyanlarını) görsün. Adım başarısızsa
            # koşu 'diverged' beyanıyla döner.
            if sa is not None and not _sa_adim(U, dt,
                                               aux_v['velocity_gradients']):
                diverged = True
                break
            visk_bloklar = None
            if viscous is not None:
                # j-yüzlerinin viskoz Jacobian'ı TAM blok (§5.6): yüksek
                # AR'de sistemin baskın terimi budur, yaklaşık alınmaz.
                # SA açıkken μ_t de sol tarafa taşınır (V3 kancası —
                # kalıntı μ_eff ile kuruluyorken sol tarafın laminer μ
                # ile kalması sönümü eksik bırakıyordu; ölçüm ve duvar
                # yüzü sözleşmesi viscous_jacobian_blocks docstring'inde).
                visk_bloklar = viscous_jacobian_blocks(
                    U, grid, geom, grad_geom, g, Rs, viscous.transport,
                    wall_thermal=viscous.wall_thermal,
                    T_wall=viscous.T_wall,
                    mu_t=None if sa is None else sa['mu_t'])
            U = U + line_implicit_delta(U, r1, grid, geom, g, dt,
                                        viscous_blocks=visk_bloklar)
        else:
            # SSP-RK2 (yerel Δt)
            if viscous is None:
                dt = local_dt_axisym(U, grid, g, cfl, area_i, area_j)
            else:
                dt = _viskoz_dt(U, cfl, eksenel=False)
            # (Δt sonluluk kapısı SA adımının KENDİ içindedir — açık yolun
            # Euler dalına yeni bir kapı EKLENMEZ, bit-özdeşlik yolu bir
            # işlem bile kazanmaz.)
            if sa is not None and not _sa_adim(U, dt,
                                               aux_v['velocity_gradients']):
                diverged = True
                break
            u1 = U + dt[..., None] * r1
            r2, _ = residual_axisym(u1, grid, g, Rs, P0, T0, Pb=Pb,
                                    second_order=second_order,
                                    slopes=frozen_slopes, geom=geom,
                                    **bc_kw)
            if viscous is not None:
                r2 = r2 + _viskoz_kalinti(u1)[0]
            U = 0.5 * (U + u1 + dt[..., None] * r2)
        if not np.all(np.isfinite(U)):
            diverged = True
            break

    if diverged:
        U = U_last_finite

    # Nihai durum bütçesi (son duruma ait akılar — geçmişin son kaydı
    # değil). Eğimler yürüyüşün bittiği sistemden: açık yolda frozen_slopes
    # (varsa), örtük yolda son taşınan implicit_slopes (dondurulmuşsa
    # donmuş, değilse son tazelenen; 1. mertebede ikisi de None).
    _son_egimler = (implicit_slopes if time_integrator == 'line_implicit_j'
                    else frozen_slopes)
    r_final, aux_final = residual_axisym(U, grid, g, Rs, P0, T0, Pb=Pb,
                                         second_order=second_order,
                                         slopes=_son_egimler, geom=geom,
                                         **bc_kw)
    aux_visc = None
    if viscous is not None:
        dudt_v, aux_visc = _viskoz_kalinti(U)
        r_final = r_final + dudt_v

    # --- SON KALINTI DÖNEN ALANIN OLMALI (ÖH defter P6B1-09) ------------
    # KUSUR (ölçüldü, a2/once.json): ``res_hist.append(res_norm)`` döngüde
    # U GÜNCELLENMEDEN ÖNCE çalışır. Yakınsama break'i de güncellemeden
    # önce olduğu için break yolunda iki sayı AYNIDIR; ama koşu tavanda
    # bittiğinde son iterasyon U'yu bir kez daha ilerletir ve yayımlanan
    # ``residual_history[-1]`` DÖNEN ALANIN DEĞİL, bir zaman adımı
    # GERİSİNİN kalıntısı olur. Ölçülen sapma (aynı operatör, aynı ölçek):
    #     açık yol, 60 iter tavan   : 5,1585e-01 <-> 4,8784e-01 (%5,74)
    #     açık yol, 140 iter tavan  : 3,3262e-01 <-> 3,2876e-01 (%1,17)
    #     örtük tazeleme, 60 iter   : 4,8304e-02 <-> 6,8660e-02 (1,42x)
    # ``r_final`` ZATEN dönen alanın, YÜRÜYÜŞÜN operatörüyle (aynı
    # ``_son_egimler``, viskoz katkı dahil) hesaplanmış kalıntısıdır;
    # normu ``res_norm`` ile BİREBİR aynı formül ve ölçektedir. Yeni bir
    # sayı ÜRETİLMEZ, var olan doğru sayı geçmişin sonuna KONUR.
    final_residual = _sema_kalinti_normu(r_final)
    # Iraksamış koşuda dönen alan U_last_finite'tir ve geçmişin son kaydı
    # (sonlu olmayan norm) IRAKSAMANIN KENDİ KANITIDIR — üstüne sonlu bir
    # sayı yazmak o kanıtı siler. Orada geçmiş DOKUNULMADAN bırakılır ve
    # ayrım makine-okur alanla beyan edilir (sessiz düzeltme yok).
    residual_history_last_is_returned_field = not diverged
    if residual_history_last_is_returned_field:
        if not res_hist or float(res_hist[-1]) != float(final_residual):
            res_hist.append(float(final_residual))
    mdot_in = aux_final['mass_flow_in_kg_s']
    mdot_out = aux_final['mass_flow_out_kg_s']
    e_in = aux_final['energy_flux_in_W']
    e_out = aux_final['energy_flux_out_W']
    mass_rel = abs(mdot_in - mdot_out) / max(abs(mdot_in), 1e-300)
    energy_rel = abs(e_in - e_out) / max(abs(e_in), 1e-300)
    # VİSKOZ BÜTÇE (basamak 14 — parti 40): ``energy_balance_rel`` YALNIZ
    # Euler yüzey akılarını karşılaştırır ve viskoz koşuda EKSİK bir
    # bütçedir (duvar ısısı ile giriş/çıkış yüzlerinin viskoz enerji akısı
    # onda YOKTUR). Ölçüldü (B1, KAPI vakası): aynı yakınsamış alanda
    # Euler biçimi 1,4e-01 gösterirken tam viskoz bütçe 2e-09'da kapanıyor.
    # Bu yüzden viskoz koşuda İKİNCİ bir bağıl artık yayımlanır ve tüketici
    # hangisini okuyacağını beyandan görür; Euler alanı DEĞİŞTİRİLMEDİ
    # (viskozsuz yol bit-özdeş kalsın diye).
    #     E_giriş − E_çıkış + (visk_çıkış − visk_giriş) − Q_duvar
    # özdeşliği ve terimlerin gerekliliği tests/cfd/test_korunum.py'de
    # ölçülüdür (terim düşünce artık 79 kat büyüyor).
    viscous_energy_rel = None
    if aux_visc is not None:
        _kalan = (e_in - e_out
                  + aux_visc['outlet_energy_flux_W']
                  - aux_visc['inlet_energy_flux_W']
                  - aux_visc['wall_heat_W'])
        viscous_energy_rel = abs(_kalan) / max(abs(e_in), 1e-300)

    # ------------------------------------------------------------------
    # ŞEMANIN KENDİ OPERATÖRÜ — çapraz ölçüm (ÖH defter P6B1-03/-04/-08)
    #
    # Yukarıdaki bütçe ve res_hist[-1], YÜRÜYÜŞÜN operatörünündür. Burada
    # AYNI son alan ŞEMANIN canlı minmod operatörüyle bir kez daha ölçülür
    # ve sayılar YAN YANA yayımlanır; hangisinin kimin olduğu künyede
    # ADIYLA yazılıdır. Operatör zaten canlıysa (eğim yok ya da eğimler
    # son durumdan) İKİNCİ ÇAĞRI YAPILMAZ — sayılar birebir aynı olurdu ve
    # varsayılan açık yolun maliyeti bir işlem bile artmaz (bit-özdeşlik
    # sözleşmesi §11.3'ün taşıyıcısı odur).
    _operator_canli = bool((not second_order) or _son_egimler is None)
    if _operator_canli:
        scheme_residual_norm = _sema_kalinti_normu(r_final)
        scheme_mass_rel = mass_rel
        scheme_energy_rel = energy_rel
    else:
        scheme_residual_norm, _r_sema, _aux_sema, _ = _sema_operatoru(U)
        _sm_in = _aux_sema['mass_flow_in_kg_s']
        _sm_out = _aux_sema['mass_flow_out_kg_s']
        _se_in = _aux_sema['energy_flux_in_W']
        _se_out = _aux_sema['energy_flux_out_W']
        scheme_mass_rel = abs(_sm_in - _sm_out) / max(abs(_sm_in), 1e-300)
        scheme_energy_rel = abs(_se_in - _se_out) / max(abs(_se_in), 1e-300)
    #: Yayımlanan kalıntı/bütçe HANGİ operatörden? Makine-okur tek alan.
    if _operator_canli:
        residual_operator = 'scheme_live_minmod'
    elif time_integrator == 'line_implicit_j':
        residual_operator = ('frozen_slopes' if implicit_frozen
                             else 'stale_refresh_window')
    else:
        residual_operator = 'frozen_slopes'
    scheme_residual_exceeds_tol = bool(
        np.isfinite(scheme_residual_norm)
        and scheme_residual_norm >= tol_res)

    # Faz-kilitli beyanın periyodu: eğim tazelemesi FİİLEN çalışıyorsa
    # tazeleme aralığı, aksi hâlde None (açık yol, 1. mertebe, ya da
    # kalıcı dondurma sonrası — o hâllerde çevrim YOKTUR ve uydurma bir
    # periyot beyan edilmez).
    _faz_periyodu = (refresh_every
                     if (time_integrator == 'line_implicit_j'
                         and second_order and not implicit_frozen
                         and refresh_every > 1)
                     else None)

    # BACAK BACAK OTURMA (ÖH defter P6B1-01): hüküm ÜÇ bandın VE'sidir ama
    # BEYAN her bacağı KENDİ bandından okur. Eskiden iki cümle de tek
    # değişkenden (settled_ok) yazılıyordu ve OTURMUŞ bacak da "OTURMADI"
    # ile suçlanıyordu (ölçüldü 2026-08-28: boğaz Mach bandı 5,369e-04 <
    # settle_tol 6,844e-04 iken cümle "boğaz Mach bandı OTURMADI" diyordu).
    debi_settled = bool(_settled(mdot_in_hist) and _settled(mdot_out_hist))
    mach_settled = bool(_settled(mach_throat_hist))
    settled_ok = bool(debi_settled and mach_settled)
    res_ok = bool(res_hist and np.isfinite(res_hist[-1])
                  and res_hist[-1] < tol_res)
    # ÖZ-TUTARLILIK KAPISININ HÜKÜM AYAĞI (ÖH defter P6B1-08; aynı onarım
    # dalgasının ikinci parçası).
    #
    # Döngü içindeki kapı (yukarıda) hükmü YALNIZ break yolunda koruyor;
    # koşu iterasyon TAVANINDA bittiğinde kapı hiç sorulmuyor ve hüküm
    # tek başına res_hist[-1]'den — yani BAYAT/DONMUŞ operatörün
    # sayısından — veriliyordu. Kapının kendi gerekçesi ("ulaşılamazsa
    # koşu max_iters'ta converged=False ile döner — fail-closed") kodda
    # KARŞILIKSIZDI.
    #
    # ÖLÇÜLDÜ (2026-08-28, bu depo, 60×12 MUSCL örtük yol, BAYAT_AYAR =
    # tol_res 1e-6 / settle_tol 1e-3 / freeze_settle_tol 1e-30; betik
    # docs/scofield/raw/OH/Z5S/pk3/olcum_tavan_deligi.py):
    #   max_iters=1800 : tavanda bitti, kapı 6 kez REDDETTİ, yayımlanan
    #                    9,6489e-07 < tol → eski ifade converged=TRUE;
    #                    şemanın kalıntısı 2,8399e-05 = tolun 28,4 katı
    #   max_iters=1900 : tavanda bitti, kapı 11 kez reddetti, yayımlanan
    #                    9,0183e-07 → eski ifade TRUE; şema 8,2155e-06 =
    #                    tolun 8,216 katı
    #   max_iters=20000: kapı KABUL etti (1962. iterasyonda), şema
    #                    9,8068e-07 = tolun 0,9807 katı → hüküm HAK EDİLDİ
    # Yani delik ölçülebilir ve tam kapının kapatmayı iddia ettiği yerde.
    #
    # Ayak, tavan yolunu da kapıya bağlar: örtük 2. mertebe yolda hüküm
    # ancak ŞEMANIN kendi kalıntısı da eşiğin altındaysa verilir. Sayı
    # SİLİNMEZ (residual_history, bütçe, alanlar aynen döner) — verilmeyen
    # şey HÜKÜMDÜR. Açık yol bu ayağın DIŞINDADIR (kapının kapsam beyanı
    # yukarıda; §11.3 bit-özdeşlik referansları oradan geçer).
    selfconsistency_gate_active = bool(
        time_integrator == 'line_implicit_j' and second_order)
    scheme_residual_blocks_verdict = bool(
        selfconsistency_gate_active and scheme_residual_exceeds_tol)
    # OH-Z5-19 — KAPSAM BEYANI KALICILAŞTIRILDI (ÖH D31 / fea-cfd a2).
    #
    # Kusur: AÇIK yolda (varsayılan ssp_rk2) plato-dondurma bayat
    # operatörün kalıntısını YAYIMLAR ve hüküm o sayıdan verilir; şemanın
    # kendi (canlı minmod) kalıntısı çok daha büyük olabilir. Kapının
    # hüküm ayağı bu yolu KAPSAMAZ.
    #
    # ÖLÇÜLDÜ — D30'da bulundu, D31 a2'de BUGÜNKÜ ağaçta yeniden üretildi
    # (betik docs/scofield/raw/OH/D31/fea-cfd/a2/olcum.py, sayılar
    # once.json; §11.3'ün dört referansında şema/yayım oranı):
    #   izantropik  60×12 :        1,00×  (operatör zaten CANLI — kusur yok)
    #   şoklu       60×12 :       44,29×  (tol 2e-6,  şema 8,8308e-05)
    #   şoklu      120×24 :      398,71×  (tol 2e-6,  şema 5,5102e-04)
    #   izantropik 120×24 : 2,9030e+07×   (tol 1e-10, şema 2,1183e-04)
    #
    # Kapsam açık yola GENİŞLETİLİRSE bu üçünde converged True→False döner
    # (ölçüldü) ve §11.3 bit-özdeşlik referanslarının yenilenmesini
    # gerektirir; P10B4-14 (Berke) referansların yeniden dondurulmasını
    # KİLİTLER. Kusur bu yüzden giderilmedi — kapsam, sessiz bir boşluk
    # olmaktan çıkarılıp ADIYLA ve SAYIYLA yayımlanır (aşağıdaki üç alan).
    # Oran, hükmün hangi operatörün sayısına dayandığını okuyanın kendi
    # gözüyle görmesi içindir; beyan kusuru gidermez, gizlemeyi bitirir.
    #
    # NÖBET DEĞİŞİMİ — ÖH D32 (OH-D31-15, Berke kararı 15 Eyl 2026 §3
    # seçenek A): yukarıdaki "beyan kusuru gidermez" cümlesi doğruydu ve
    # sonuçları çıkarıldı. Kapı hâlâ GENİŞLETİLMEDİ (kök onarım + dört
    # referansın gerçekten yeniden koşulması 2.7'de), ama kapsam dışında
    # verilen hüküm artık GERİ ÇEKİLİYOR: ``converged=None`` +
    # ``convergence_status='not_evaluated'`` (aşağıdaki üç durumlu
    # sözleşme). Dört referansın künyesi P10B4-14 deseniyle yenilendi —
    # DİZİLER BİT-AYNI, yalnız hüküm alanları değişti (kanıt
    # docs/scofield/raw/OH/D32/fea-cfd/a2/kunye_yenileme.json).
    scheme_over_published_ratio = None
    if (res_hist and np.isfinite(scheme_residual_norm)
            and np.isfinite(res_hist[-1]) and res_hist[-1] > 0.0):
        scheme_over_published_ratio = float(
            scheme_residual_norm / res_hist[-1])
    # PLATO HÜKMÜ (ÖH defter OH-Z5-14). Kapı hükmü geri çekince koşan
    # kişinin elinde tek bilgi "converged=False" kalıyordu; "bütçeyi
    # büyüt" ile "bu vaka sınıfında HEDEF ULAŞILAMAZ" birbirinden
    # ayrılamıyordu. Nihai ölçüm örnek dizisine YAZILIR (kapının
    # kullandığı sayının ta kendisi) ve plato hükmü o diziden okunur.
    if np.isfinite(scheme_residual_norm):
        _sema_ornek_ekle(it, scheme_residual_norm, zorla=True)
    scheme_plateau = _plateau_verdict(_sema_ornekleri, tol_res)
    # --- P6B1-10: KAYMA DUVARI YILDIZ BASINCI POZİTİFLİK KAPISI --------
    #
    # Kusur (defter P6B1-10, D23'te ölçüldü): duvar akısının yıldız
    # basıncı p* = p·(1 + γ·M_n) biçimini alır ve M_n < −1/γ'da NEGATİFE
    # geçer — duvar akışkanı itmek yerine EMER. Sayı SONLU olduğu için ne
    # ``residual_axisym``in NaN ölçütüne ne de ``viscous.nonphysical_
    # state``e takılır: fiziksel olmayan durum SESSİZCE yayımlanır.
    #
    # KAPI NEDEN BURADA (kalıntıda değil): "p* ≤ 0 → NaN" biçiminde bir
    # kalıntı kapısı D23'te yazıldı ve SAĞLAM koşumun BAŞLANGIÇ
    # GEÇİCİSİNİ kırdığı ölçülüp geri alındı — izantropik tahminden
    # yürüyen ilk adımlar eşiği geçici olarak aşabiliyor ve geçici bir
    # aşım ıraksama DEĞİLDİR. Doğru sınır YAYIM sınırıdır: geçici
    # serbesttir, ama YAKINSAMIŞ ilan edilen bir kararlı-hâl alanı emme
    # uygulayamaz. Kapı bu yüzden yalnız NİHAİ alanı yargılar ve hükmü
    # (converged) fail-closed geri çeker; sayılar SİLİNMEZ.
    #
    # DUVAR AKISININ SAYISI DEĞİŞMEDİ: pozitiflik KORUYAN duvar akısına
    # (iki-genişleme yıldız basıncı) geçmek §11.3'ün dondurulmuş
    # bit-özdeşlik referanslarını yeniden üretmeyi gerektirir ve fizik
    # dalgasının kalemidir; burada yalnız ölçüm + kapı vardır.
    #
    # ÖLÇÜLDÜ (docs/scofield/raw/OH/D31/fea-cfd/a1/once_cfd.json, K2):
    # dört dondurulmuş Euler referansında en negatif duvar M_n
    # −0,013563 (sok_60x12) ⟷ eşik −1/γ = −0,833333; uzaklık 61-124 kat,
    # negatif p* yüzü YOK. Yani kapı bugünkü ürün akışında HİÇ ateşlemez
    # ve hiçbir yayımlanan sayıyı değiştirmez — ama sessiz emmeyi
    # yakalayacak kanal artık VARDIR.
    try:
        _, _wall_p_star, _, wall_star = wall_star_pressure(U, grid, g,
                                                           geom=geom)
        wall_star_ok = (True if wall_star['pozitif_mi'] is None
                        else bool(wall_star['pozitif_mi']))
    except (ValueError, KeyError, IndexError, FloatingPointError) as _exc:
        # Ölçülemeyen kapı TEMİZ sayılmaz; hüküm fail-closed durur.
        wall_star = {'pozitif_mi': None, 'olculemedi': f'{type(_exc).__name__}',
                     '_basis': ('duvar yıldız basıncı ÖLÇÜLEMEDİ — hüküm '
                                'fail-closed geri çekilir (P6B1-10)')}
        wall_star_ok = False
    wall_star['kapi'] = bool(wall_star_ok)
    wall_star['hukmu_geri_cekti_mi'] = bool(not wall_star_ok)
    # HÜKMÜN KAZANILDIĞI ÜÇLÜ + KAPILAR. Bu ifade hükmün HAK EDİLİP
    # edilmediğini söyler; hükmün VERİLİP verilmeyeceği bir sonraki adımda,
    # gerekli değerlendirmenin yapılıp yapılmadığına bakılarak kararlaşır.
    verdict_earned = bool((not diverged) and settled_ok and res_ok
                          and (not scheme_residual_blocks_verdict)
                          and wall_star_ok
                          and it < max_iters + 1)
    # OH-Z5-19: hüküm kapının KAPSAMI DIŞINDA mı verildi? True ise
    # converged=True'nun arkasında öz-tutarlılık ayağı HİÇ koşmamıştır ve
    # şemanın kendi kalıntısı eşiğin üstündedir. Alan, kapsam boşluğunu
    # tüketiciye makine-okur biçimde taşır (cümle ayrıştırmadan).
    verdict_outside_gate_scope = bool(
        verdict_earned and (not selfconsistency_gate_active)
        and scheme_residual_exceeds_tol)
    # --- ÜÇ DURUMLU HÜKÜM SÖZLEŞMESİ (OH-D31-15) -----------------------
    #
    # KUSUR (ÖH defter OH-D31-15; D31 fea-cfd a2'de ÖLÇÜLDÜ, D32'de aynı
    # ağaçta yeniden üretildi — docs/scofield/raw/OH/D32/fea-cfd/a2/
    # once.json K1): kapsam DIŞINDA kalan koşularda hüküm yine de
    # ``converged=True`` olarak yayımlanıyordu. Yani öz-tutarlılık ayağı
    # HİÇ koşmamışken ürün "yakınsadı" diyordu; §11.3'ün dört referansının
    # ÜÇÜNDE şemanın kendi kalıntısı yayımlanandan 44,29 / 398,71 /
    # 2,9030e+07 kat büyükken bayrak True idi. Beyan (kapsam alanları)
    # kusuru ADLANDIRIYOR ama kapatmıyordu: tüketiciler bayrağı okuyordu,
    # beyanı değil — panel yeşil "CONVERGED" rozeti basıyor (cfd_panel.js
    # badgesHtml), ayrılma köprüsü judgment_confidence='firm' veriyordu
    # (separation.py) ve uç bayrağı bool'a çeviriyordu (app.py).
    #
    # SÖZLEŞME (Berke kararı 15 Eyl 2026, seçenek A; Astra (c) hükmü —
    # docs/scofield/raw/OH/D32/oturum-devri/berke_kararlari_2026-09-15.md
    # §3). ``converged`` ÜÇ DEĞERLİDİR ve okuyan taraf üçünü AYIRMAK
    # zorundadır:
    #   True  — hüküm HAK EDİLDİ ve gerekli değerlendirme YAPILDI
    #           (canlı operatör ya da kapsam içinde kapıdan geçmiş).
    #   False — ölçülmüş bir aşım/ıraksama/oturmama hükmü ENGELLEDİ
    #           (kapsam içi aşım scheme_residual_blocks_verdict ile).
    #   None  — hüküm için GEREKLİ DEĞERLENDİRME YAPILMADI: koşu kapının
    #           kapsamı dışında kaldı (açık yol) ve şemanın kendi kalıntısı
    #           eşiğin üstünde. Bu bir "yakınsamadı" hükmü DEĞİLDİR; hüküm
    #           yokluğudur ve öyle yayımlanır (convergence_status=
    #           'not_evaluated'). Sayılar SİLİNMEZ.
    #
    # NEDEN None, NEDEN False DEĞİL: açık yolda sınırlayıcı dondurma minmod
    # limit döngüsünün BEYANLI tedavisidir; canlı minmod kalıntısının eşiğin
    # üstünde kalması o tedavinin beklenen sonucudur ve tek başına
    # "yakınsamadı" demek DEĞİLDİR. Ölçülmemiş olan, hükmün kapıdan geçip
    # geçmeyeceğidir — kök onarım (kapsamı açık yola genişletmek + dört
    # referansı gerçekten yeniden koşmak) 2.7'ye bırakıldı (Berke, aynı
    # karar). Burada yapılan, KAZANILMAMIŞ hükmü yayımlamayı bırakmaktır.
    #
    # FAIL-CLOSED: None'ın bool'u False'tur; bayrağı yanlışlıkla bool'a
    # çeviren bir tüketici yeşil rozet basamaz, en fazla olumsuz tarafa
    # düşer. Dizge ('NOT_EVALUATED' gibi) KULLANILMAZ: bool('NOT_EVALUATED')
    # True olurdu ve kusur aynen sürerdi (Astra'nın adlandırdığı tuzak).
    converged = None if verdict_outside_gate_scope else verdict_earned
    # TEK ALANDA DURUM (makine-okur): tüketici 'converged=False'un
    # NEDENİNİ cümle ayrıştırmadan okur. 'plateau' = şema kalıntısı
    # ölçülen bir bantta DURDU, bütçe büyütmek geçmez (hüküm yine
    # KAZANILMAMIŞTIR — plato bir hüküm DEĞİL, hükümsüzlüğün cinsidir).
    if diverged:
        convergence_status = 'diverged'
    elif converged is None:
        # OH-D31-15: hüküm için gerekli değerlendirme YAPILMADI. Bu durum
        # 'not_converged'un bir çeşidi DEĞİLDİR; plato/oturmama gibi
        # ÖLÇÜLMÜŞ hükümsüzlük cinslerinin de önüne geçer, çünkü onlar
        # "hüküm verilmedi çünkü şu ölçüldü" der, bu ise "hüküm hiç
        # yargılanmadı" der.
        convergence_status = 'not_evaluated'
    elif converged:
        convergence_status = 'converged'
    elif not wall_star_ok:
        # P6B1-10: kök sebep ADIYLA; 'not_converged' bunu SÖYLEMEZ.
        convergence_status = 'wall_star_pressure_nonpositive'
    elif scheme_plateau['detected']:
        convergence_status = 'plateau'
    else:
        convergence_status = 'not_converged'
    if diverged:
        basis = (f'DIVERGED: iterasyon {it} içinde fiziksel olmayan durum '
                 f'(NaN/Inf) — bilinen son sonlu alan raporlandı, hüküm yok.')
    else:
        basis = (
            f'Hüküm kullanıcı büyüklüklerinden: debi bandı (giriş/çıkış, '
            f'son {settle_window} iter) '
            f'{"OTURDU" if debi_settled else "OTURMADI"}, boğaz Mach bandı '
            f'{"OTURDU" if mach_settled else "OTURMADI"} '
            f'(settle_tol={settle_tol:g}); yoğunluk L2 kalıntısı '
            f'{res_hist[-1]:.3e} '
            f'{"<" if res_ok else ">="} tol {tol_res:g} (ölçek ρ0·a0/L). '
            f'{it} iterasyon.'
            + (f' Sınırlayıcı son olarak {frozen_at}. iterasyonda '
               f'donduruldu ({freeze_reason}, {freeze_count} dondurma/'
               f'tazeleme).' if frozen_at is not None else '')
            # OPERATÖR ADIYLA (ÖH defter P6B1-03): bu cümle eskiden
            # dondurma dalında "şema minmod" diyordu — yayımlanan sayı
            # ise DONMUŞ operatörünkiydi. Artık sayının sahibi adıyla
            # yazılır ve şemanın KENDİ kalıntısı YANINDA durur; okuyucu
            # iyimser sayıyı şemanınki sanamaz.
            + (' Yayımlanan kalıntı ŞEMANIN canlı minmod operatörünündür '
               f'(residual_operator={residual_operator}).'
               if _operator_canli else
               f' UYARI — yayımlanan kalıntı ŞEMANIN DEĞİL, yürüyüşün '
               f'taşıdığı eğim sisteminindir '
               f'(residual_operator={residual_operator}); aynı alanın '
               f'şema (canlı minmod) kalıntısı '
               f'{scheme_residual_norm:.3e} = tolun '
               f'{scheme_residual_norm / tol_res:.4g} katı '
               f'(scheme_residual_norm).')
            # HÜKÜM NEDEN VERİLMEDİ (ÖH defter P6B1-08): öz-tutarlılık
            # kapısı reddettiği hâlde koşu iterasyon tavanında bittiyse,
            # yayımlanan sayı eşiğin altında OLSA BİLE hüküm verilmez ve
            # sebep ADIYLA yazılır. Sayılar silinmez, hüküm verilmez.
            + (f' HÜKÜM VERİLMEDİ (öz-tutarlılık kapısı): yayımlanan '
               f'kalıntı eşiğin altında olsa da şemanın kendi kalıntısı '
               f'{scheme_residual_norm:.3e} ≥ tol {tol_res:g}; kapı '
               f'{picard_red_sayisi} kez reddetti ve koşu {it} '
               f'iterasyonda tavana dayandı '
               f'(scheme_residual_blocks_verdict).'
               if scheme_residual_blocks_verdict else '')
            # HÜKÜM DEĞERLENDİRİLMEDİ (ÖH defter OH-D31-15): koşu kapının
            # kapsamı DIŞINDA kaldı ve şemanın kendi kalıntısı eşiğin
            # üstünde — hüküm HAK EDİLMİŞ görünse de YARGILANMAMIŞTIR.
            + (f' HÜKÜM DEĞERLENDİRİLMEDİ (converged=None, '
               f'convergence_status=not_evaluated): öz-tutarlılık kapısının '
               f'kapsamı {SELFCONSISTENCY_GATE_SCOPE}, bu koşu o kapsamın '
               f'DIŞINDA (time_integrator={time_integrator}, '
               f'second_order={bool(second_order)}); şemanın kendi '
               f'kalıntısı {scheme_residual_norm:.3e} = tolun '
               f'{scheme_residual_norm / tol_res:.4g} katı. Yayımlanan '
               f'sayılar aynen durur; verilmeyen şey HÜKÜMDÜR ve bu bir '
               f'"yakınsamadı" hükmü DEĞİLDİR.'
               if verdict_outside_gate_scope else '')
            # PLATO ADIYLA (ÖH defter OH-Z5-14): "daha çok iterasyon
            # ver" ile "bu vaka sınıfında hedef ULAŞILAMAZ" ayrı
            # şeylerdir; ikincisi ölçülmüşse öyle YAZILIR.
            + (f' PLATO: şemanın kalıntısı son '
               f'{scheme_plateau["min_samples"]} örnekte '
               f'{scheme_plateau["window_iterations"]} iterasyon boyunca '
               f'{scheme_plateau["relative_spread"]:.3e} göreli yayılımda '
               f'({scheme_plateau["plateau_residual"]:.4e}) DURDU ve hedef '
               f'{tol_res:g} bu vaka sınıfında ULAŞILAMAZ görünüyor — '
               f'iterasyon bütçesini büyütmek hükmü kazandırmaz '
               f'(convergence_status=plateau).'
               if scheme_plateau['detected'] else '')
            + f' Giriş sınır koşulu: {INLET_BC_NAME} (künye: '
              f'inlet_bc_basis).')

    w = cons_to_prim_axisym(U, g)
    temp = w[..., 3] / (Rs * w[..., 0])
    a_snd = np.sqrt(g * Rs * temp)
    mach = np.sqrt(w[..., 1] ** 2 + w[..., 2] ** 2) / a_snd
    z_sec, m_sec, p_sec = _section_averages(U, grid, g)
    r_w = _column_wall_radius(grid)

    # Aşama 1B köprüsü: separation.py'nin isteyeceği duvar basıncı beyanı —
    # duvara komşu hücre merkezinin basıncı (hücre-merkezli çözücüde duvar
    # değeri dışdeğerlenmemiş ham komşu değerdir; beyan).
    wall_pressure = w[:, -1, 3].copy()

    # Sensör beyan sayısı SON alandan doğrudan (donmuş eğimli bütçe
    # çağrısında sensör bloğu atlanır — aux_final'den alınsa şoklu vakada
    # yanlış 0 beyan edilirdi).
    # Sensör beyanı NİHAİ alanın CANLI ölçümüdür (donmuş çağrıda sensör
    # bloğu atlandığından oradan alınamaz): aynı residual_axisym çağrısının
    # aux'ından okunur — ikinci bir sensör gerçeklemesi yazılmaz.
    if second_order:
        _aux_sensor = _aux_sema if not _operator_canli else aux_final
        sensor_columns = int(_aux_sensor.get('shock_sensor_columns', 0))
        sensor_cells = int(_aux_sensor.get('shock_sensor_cells', 0))
    else:
        sensor_columns = 0
        sensor_cells = 0

    # ÇIKIŞ SINIRI BEYANI (viskoz devir kusuru #2). Çapa kipi ne olursa
    # olsun çıkıştaki ses-altı hücre sayısı SON alandan ölçülür: çapa
    # KAPALIYKEN kusur sessiz kalmasın diye. Sayı kolonun kendi normal
    # Mach'ından gelir (euler_core tek gerçekleme) — bu dosyada ikinci
    # bir ses-altı tanımı yazılmaz.
    n_subsonic_out = outlet_subsonic_count(w[-1], geom['n_out_hat'], g)
    _capasiz = (Pb is None and n_subsonic_out > 0
                and outlet_subsonic_anchor == OUTLET_ANCHOR_EXTRAPOLATE)
    outlet_bc = {
        'subsonic_anchor': outlet_subsonic_anchor,
        'Pb_Pa': None if Pb is None else float(Pb),
        'subsonic_cells': n_subsonic_out,
        'cells_total': int(grid.nj),
        'anchored': bool(Pb is not None
                         or outlet_subsonic_anchor
                         == OUTLET_ANCHOR_CORE_PRESSURE),
        'unanchored_warning': (
            f'ÇAPASIZ: çıkış kolonunda {n_subsonic_out}/{grid.nj} hücre '
            'ses-altı ve çıkış tam dışdeğerleme (Pb=None). O satırlarda '
            'giren karakteristiğe hiçbir bilgi verilmiyor; ölçülen '
            'sonucu kalıntının limit döngüsüne girmesidir. Çare '
            "outlet_subsonic_anchor='core_pressure'."
            if _capasiz else None),
        '_basis': OUTLET_ANCHOR_BASIS,
    }

    # NOT_MODELLED tek kaynağı paket köküdür; döngüsel içe aktarmayı önlemek
    # için çağrı anında alınır (fonksiyon çağrılırken paket tam yüklüdür).
    from hrma.cfd import CFD_NOT_MODELLED

    not_modelled = dict(CFD_NOT_MODELLED)
    assumptions = list(_ASSUMPTIONS)
    viscous_block = None
    if viscous is not None:
        # §10: 'viscosity_turbulence' anahtarı SİLİNMEZ, DARALTILIR —
        # daraltılmış metin viscous.py'nin TEK kaynağından alınır (bu
        # dosyada ikinci bir beyan yazılmaz).
        visk_nm = dict(VISCOUS_NOT_MODELLED)
        if sa is not None:
            # SA açıkken 'türbülans yok' cümlesi YALAN olurdu: metin
            # viscous.py'nin μ_t sözleşmesiyle DEĞİŞTİRİLİR (tek kaynak
            # sabiti) ve SA'nın KENDİ modellenmeyenleri eklenir.
            visk_nm['turbulence'] = TURBULENCE_CLOSED_BY_MU_T
            visk_nm.update(SA_NOT_MODELLED)
        not_modelled.update(visk_nm)
        not_modelled['viscosity_turbulence'] = visk_nm['turbulence']
        assumptions = [a for a in _ASSUMPTIONS
                       if a not in _VISCOUS_ASSUMPTION_DROPS]
        assumptions += [('rans_sa_neg' if sa is not None
                         else 'laminar_viscous'),
                        f'wall_{viscous.wall_thermal}']
        if sa is not None:
            assumptions += ['boussinesq_eddy_viscosity', 'fully_turbulent']
        viscous_block = _viscous_output_block(
            viscous, aux_visc, r_final, geom, grad_geom, w,
            Rs, rho0, a0, length, vol, vol_sum, grid, y_plus_target,
            sa=sa, throat_index=i_throat)

    return {
        'converged': converged,
        'convergence_basis': basis,
        # --- DURUM TEK ALANDA (ÖH defter OH-Z5-14) ---------------------
        # 'converged' | 'not_evaluated' | 'plateau' | 'not_converged' |
        # 'wall_star_pressure_nonpositive' | 'diverged'.
        # 'not_evaluated' (OH-D31-15): hüküm YARGILANMADI — converged None.
        # 'plateau': şemanın kendi kalıntısı ÖLÇÜLEN bir bantta durdu —
        # bütçeyi büyütmek kapıyı geçirmez. Hüküm yine YOKTUR (converged
        # False); plato hükmün cinsini söyler, hükmün yerine GEÇMEZ.
        'convergence_status': convergence_status,
        'convergence_plateau': scheme_plateau,
        # P6B1-10: kayma duvarı yıldız basıncının NİHAİ alandaki ölçümü
        # ve yayım kapısı. Sessiz emme artık bir hüküm kapısına bağlı.
        'wall_star_pressure': wall_star,
        'inlet_bc': INLET_BC_NAME,
        'inlet_bc_basis': INLET_BC_BASIS,
        'outlet_bc': outlet_bc,
        'time_integrator': time_integrator,
        'time_integrator_basis': (
            'Zaman ilerletme yolu beyanı: ssp_rk2 = açık SSP-RK2 + yerel '
            'Δt (varsayılan; Euler yolu bit-özdeşliğinin taşıyıcısı); '
            'line_implicit_j = j-yönü satır-örtük blok üç-köşegen gevşetme '
            '(relax_implicit.py; Jameson & Yoon 1987 spektral yarıçap '
            'bölmeli yaklaşık Jacobian + DPLR tarzı yön-dışı köşegen '
            'sönüm; MUSCL eğimleri periyodik Picard tazelemesiyle taşınır '
            've açık yolun plato-dondurması bu dalda kullanılmaz — '
            'gerekçeler DEFAULT_IMPLICIT_SLOPE_REFRESH tanımında, '
            'ölçümle). HÜKÜM-NÖTR: seçim yalnız köke gidiş yolunu '
            'değiştirir; hüküm üçlüsü (debi bandı + boğaz Mach bandı + '
            'kalıntı eşiği) iki yolda AYNIDIR ve yakınsanan alanların '
            'eşitliği bekçilidir (tests/cfd/test_satir_ortuk.py).'),
        'iterations': it,
        'limiter_frozen_at_iter': frozen_at,
        'limiter_freeze_count': freeze_count,
        # --- YAYIMLANAN SAYI KİMİN? (ÖH defter P6B1-03/-04/-08) --------
        # residual_history ve bütçe YÜRÜYÜŞÜN operatörünündür; şemanın
        # kendi (canlı minmod) ölçümü ayrı alanlarda, ADIYLA durur.
        'residual_operator': residual_operator,
        'scheme_residual_norm': scheme_residual_norm,
        'scheme_residual_exceeds_tol': scheme_residual_exceeds_tol,
        # Hüküm bu yüzden mi verilmedi? (ÖH defter P6B1-08 tavan ayağı.)
        # True ise converged=False'un sebebi öz-tutarlılık kapısıdır;
        # sayılar aynen döner, hüküm dönmez.
        'scheme_residual_blocks_verdict': scheme_residual_blocks_verdict,
        'picard_selfconsistency_rejections': int(picard_red_sayisi),
        'slope_state': {
            'published_operator': residual_operator,
            'walk_operator_is_scheme': bool(_operator_canli),
            'frozen_at_iter': frozen_at,
            'freeze_count': freeze_count,
            'refresh_period': (int(refresh_every)
                               if (time_integrator == 'line_implicit_j'
                                   and second_order) else None),
            'scheme_residual_norm': scheme_residual_norm,
            'scheme_mass_balance_rel': scheme_mass_rel,
            'scheme_energy_balance_rel': scheme_energy_rel,
            'tol_res': float(tol_res),
            'selfconsistency_gate': ('line_implicit_j'
                                     if selfconsistency_gate_active else None),
            # OH-Z5-19: kapsam ARTIK ADIYLA yayımlanır. 'selfconsistency_
            # gate' None dönünce eskiden "kapı yok" mu "kapı bu koşumu
            # kapsamıyor" mu ayırt edilemiyordu; bu üç alan ayırır.
            'selfconsistency_gate_scope': SELFCONSISTENCY_GATE_SCOPE,
            'in_gate_scope': bool(selfconsistency_gate_active),
            'verdict_outside_gate_scope': bool(verdict_outside_gate_scope),
            'scheme_over_published_ratio': scheme_over_published_ratio,
            'selfconsistency_rejections': int(picard_red_sayisi),
            'blocks_verdict': scheme_residual_blocks_verdict,
            '_basis': (
                'YAYIMLANAN KALINTI VE BÜTÇE HANGİ EĞİM SİSTEMİNDEN? '
                'MUSCL yeniden kurulumunun eğimleri her iterasyonda '
                'CANLI hesaplanmayabilir: açık yolda plato-dondurma, '
                'örtük yolda oturma-tetikli kalıcı dondurma ve tazeleme '
                'penceresinin ORTASI eğimleri DONUK taşır. O hâllerde '
                'nihai bütçe ile residual_history[-1] donmuş/bayat '
                'operatörün sayılarıdır — ölçüldü (2026-08-28): donan '
                'koşularda şema kalıntısı yayımlanandan 44 ile 2,9e7 kat '
                'BÜYÜK. Bu blok sayının sahibini adlandırır ve AYNI '
                'alanın şema (canlı minmod) ölçümünü yanına koyar; '
                'walk_operator_is_scheme True ise iki ölçüm zaten '
                'AYNI çağrıdır (ikinci hesap yapılmaz). '
                'selfconsistency_gate: örtük yolda hüküm, eğimler o anın '
                'durumundan TAZELENDİKTEN sonra da eşiğin altındaysa '
                'verilir (Picard öz-tutarlılığı; reddedilme sayısı '
                'picard_selfconsistency_rejections). Kapının İKİ ayağı '
                'vardır: döngü içindeki break ayağı ve TAVAN ayağı — koşu '
                'iterasyon tavanında biterse hüküm, yayımlanan sayı eşiğin '
                'altında olsa bile şemanın kendi kalıntısı eşiğin '
                'üstündeyse VERİLMEZ (blocks_verdict; ölçüldü 2026-08-28: '
                'tavan 1800 ve 1900 koşuları eski ifadeyle converged=True '
                'derken şema kalıntısı tolun 28,4 ve 8,216 katıydı). '
                'KAPININ ÖLÇÜLEN BEDELİ, DÜRÜSTÇE: şoklu/viskoz vakalarda '
                'canlı minmod bir LİMİT DÖNGÜSÜNDEDİR — dondurmanın varlık '
                'sebebi zaten budur — ve orada şema kalıntısı bütçe '
                'büyütülerek İNMEZ. ÖLÇÜLDÜ (2026-08-28, viskoz '
                'aşırı-genişlemiş 64×16 lüle, tol 1e-8): 5.000/10.000/'
                '20.000 iterasyonda şema kalıntısı 1,2204e-04 / 1,2168e-04 '
                '/ 1,2206e-04 — PLATO. O vaka sınıfında bu kapı hükmü '
                'KALICI olarak geri çeker (converged=False) ve koşu tavana '
                'kadar sürer (aynı vakada duvar saati ~10 s → ~100 s). '
                'Hüküm eksilir, VERİ EKSİLMEZ; ölçütün hangi kalıntı '
                'olacağı (şemanın mı, donmuş operatörün mü) bir DOKTRİN '
                'kararıdır ve burada ADIYLA beyan edilir. '
                'Açık yol bu kapının '
                'DIŞINDADIR: oradaki dondurma minmod limit döngüsünün '
                'beyanlı tedavisidir ve §11.3 bit-özdeşlik referansları '
                '(data/cfd_referans) o davranışla dondurulmuştur — açık '
                'yolun hüküm ekseni referans yenilemesi gerektirir, bu '
                'partide YAPILMADI ve burada ADIYLA beyan edilir.'),
        },
        'residual_history': np.asarray(res_hist),
        #: Yayımlanan son kalıntı DÖNEN ALANIN mı? (ÖH defter P6B1-09)
        #: True  → residual_history[-1] == final_residual_of_returned_field.
        #: False → koşu ıraksadı; dönen alan U_last_finite, geçmişin son
        #:         kaydı ise ıraksama anının (sonlu olmayan) kaydıdır ve
        #:         KANIT olarak korunur. Tüketici hangi hâlde olduğunu
        #:         cümle ayrıştırmadan okur.
        'residual_history_last_is_returned_field': bool(
            residual_history_last_is_returned_field),
        'final_residual_of_returned_field': float(final_residual),
        # Hüküm ÜÇLÜSÜNÜN diğer iki bacağının izi de yayımlanır: kalıntı
        # platoda takılırken kullanıcı büyüklüklerinin oturup oturmadığı
        # ancak böyle GÖRÜLEBİLİR (takılma tespiti; Berke kararı §13/1 —
        # "kalıntı durgunluk/ıraksama algısı + gerçek ilerleme beyanı").
        # Sahte yüzde yok: bunlar koşumun kendi ölçtüğü dizilerdir.
        'mass_flow_in_history': np.asarray(mdot_in_hist),
        'mass_flow_out_history': np.asarray(mdot_out_hist),
        'throat_mach_history': np.asarray(mach_throat_hist),
        'settle_bands': {
            'window': int(settle_window),
            'tol': float(settle_tol),
            'mass_flow_in': _settle_band(mdot_in_hist, settle_window),
            'mass_flow_out': _settle_band(mdot_out_hist, settle_window),
            'throat_mach': _settle_band(mach_throat_hist, settle_window),
            # Faz-kilitli bantlar YALNIZ BEYANDIR (hüküm ham banttır,
            # değişmedi). Eğim tazelemesi olmayan yollarda (açık yol ya
            # da kalıcı dondurma sonrası) NaN dönerler: "ölçülmedi" ile
            # "oturdu" karıştırılmaz. Gerekçe _settle_band_phase'te.
            'refresh_phase_locked': {
                'active': bool(_faz_periyodu is not None),
                'period': (None if _faz_periyodu is None
                           else int(_faz_periyodu)),
                'mass_flow_in': _settle_band_phase(
                    mdot_in_hist, settle_window, _faz_periyodu or 0),
                'mass_flow_out': _settle_band_phase(
                    mdot_out_hist, settle_window, _faz_periyodu or 0),
                'throat_mach': _settle_band_phase(
                    mach_throat_hist, settle_window, _faz_periyodu or 0),
                '_basis': (
                    'Aynı TAZELEME FAZINDA örneklenmiş bant (fazlar '
                    'üstünde EN KÖTÜSÜ). Satır-örtük yol MUSCL eğimlerini '
                    'her `period` iterasyonda tazeler ve minmod '
                    'gevelemesini yeniden enjekte eder; ham bant bunu '
                    '"oturmamışlık" gibi okuyabilir. OKUMA KURALI: ham ≫ '
                    'faz ise oynayan tazeleme çevrimidir; ham ≈ faz ise '
                    'büyüklük gerçekten SÜRÜKLENİYORDUR. (KAPI vakasında '
                    'ölçülen: çıkış debisi ham 1,0081e-05 ↔ faz '
                    '1,0082e-05 — sürüklenme; buna karşılık KALINTI aynı '
                    'koşumda çevrime harfi harfine kilitli.) Hükme '
                    'GİRMEZ.'),
            },
            '_basis': (
                'Son `window` iterasyondaki bağıl bant '
                '(maks−min)/|son|. Hüküm için ÜÇÜ de tol altında olmalı; '
                'hangisinin engellediği buradan OKUNUR (kalıntı platosu '
                'ile kullanıcı büyüklüklerinin oturması ayrı şeylerdir). '
                'refresh_phase_locked bu üçlünün tazeleme çevriminden '
                'arındırılmış ikizidir — beyan, hüküm değil.'),
        },
        'mass_flow_in_kg_s': mdot_in,
        'mass_flow_out_kg_s': mdot_out,
        'mass_balance_rel': mass_rel,
        'energy_flux_in_W': e_in,
        'energy_flux_out_W': e_out,
        'energy_balance_rel': energy_rel,
        'viscous_energy_balance_rel': viscous_energy_rel,
        # Aynı son alanın ŞEMA (canlı minmod) operatörüyle bütçesi —
        # yukarıdaki iki alanın sahibi yürüyüşün operatörüdür (künye
        # budget_basis + slope_state).
        'scheme_mass_balance_rel': scheme_mass_rel,
        'scheme_energy_balance_rel': scheme_energy_rel,
        'wall_mass_flux_kg_s': aux_final['wall_mass_flux_kg_s'],
        'budget_basis': (
            'Korunum bütçesi: giriş/çıkış yüzey akıları HLLC yüzey '
            'integrallerinden (2π dahil, gerçek birim); bağıl artıklar '
            '|giriş−çıkış|/giriş. Duvar kütle akısı kayma sınırında ayrık '
            'olarak tam sıfırdır (ayna durumda HLLC kütle akısı özdeş 0). '
            'OPERATÖR KÜNYESİ (ÖH defter P6B1-04): bu bütçe nihai alanın '
            'akılarından, YÜRÜYÜŞÜN son eğim sistemiyle ölçülür. Eğimler '
            'donmuşsa (limiter_frozen_at_iter) ya da tazeleme penceresinin '
            'ortasında bayatsa, sayı ŞEMANIN değil O operatörün bütçesidir '
            '— ölçüldü: donan koşuda yayımlanan kütle artığı şemanınkinden '
            '5 mertebeye kadar iyimser çıkabiliyor. Sayının sahibi '
            'slope_state.published_operator alanında ADIYLA, şemanın '
            'kendi ölçümü ise scheme_mass_balance_rel / '
            'scheme_energy_balance_rel alanlarında YANINDA yayımlanır; '
            'walk_operator_is_scheme True iken ikisi aynı çağrıdır. '
            'VİSKOZ KOŞUDA energy_balance_rel TEK BAŞINA OKUNMAZ: o alan '
            'yalnız Euler yüzey akılarını karşılaştırır, duvardan çıkan ısı '
            've giriş/çıkış yüzlerinin VİSKOZ enerji akısı onda yoktur — '
            'ölçüldü, aynı yakınsamış alanda Euler biçimi 1,4e-01 '
            'gösterirken tam bütçe 2e-09\'da kapanıyor. Viskoz koşunun '
            'bütçesi viscous_energy_balance_rel alanıdır: '
            '|E_giriş − E_çıkış + (visk_çıkış − visk_giriş) − Q_duvar| / '
            'E_giriş. Terimlerin dördü de viscous bloğunda AYRI AYRI '
            'yayımlanır (inlet/outlet_viscous_energy_flux_W, wall_heat_W); '
            'Euler koşusunda bu alan None\'dır — sıfır değil, YOK.'),
        'fields': {
            'rho_kg_m3': w[..., 0],
            'u_z_m_s': w[..., 1],
            'u_r_m_s': w[..., 2],
            'pressure_Pa': w[..., 3],
            'temperature_K': temp,
            'mach': mach,
        },
        'z_centers_m': grid.z_centers,
        'r_centers_m': grid.r_centers,
        'section_average': {
            'z_m': z_sec,
            'mach': m_sec,
            'pressure_Pa': p_sec,
            '_basis': 'Hacim ağırlıklı kolon ortalaması (beyan: '
                      '_section_averages docstring).',
        },
        'throat': {
            'i': i_throat,
            'z_m': float(z_sec[i_throat]),
            'radius_m': float(r_w[i_throat]),
            'area_m2': float(np.pi * r_w[i_throat] ** 2),
            'mach_section_avg': float(m_sec[i_throat]),
            # BOĞAZ İMZASI (ÖH defter P6B1-07) — bu alan YOKTU ve
            # "en küçük kolon" sessizce "boğaz" diye yayımlanıyordu.
            # ÖLÇÜLDÜ (taban 2426b4d, once.json): salt ıraksak konturda
            # (yarıçap girişten çıkışa tekdüze artan) kolon argmin UÇ
            # kolona (i=0) düşüyor, yayımlanan radius_m 0,031 m iken
            # konturun gerçek en küçük DÜĞÜM yarıçapı 0,030 m — yarıçapta
            # +%3,33, ALANDA +%6,78 (fark yarım hücredir, dolayısıyla
            # KABA ızgarada büyür: uç raporunda +%16,7 / +%36,1). Uç
            # kolon bir boğaz DEĞİL, alanın kenarıdır: orada minimum
            # olması akışın boğulduğunu değil, konturun o yönde
            # incelmediğini gösterir. Ayrılma köprüsü bu indisi devralıp
            # tüm alanı "ıraksak bölge" sayıyordu (separation.py'nin son
            # istasyon kapısının kardeşi giriş tarafında YOKTU).
            # Kapı GEVŞETİLMEZ ve sayı SİLİNMEZ: minimum olduğu gibi
            # yayımlanır, ama 'interior' alanı onun bir boğaz İDDİASI
            # taşıyıp taşımadığını söyler (bridge.py'deki P8B2-04
            # "boğaz imzası" deseninin aynısı — tek desen).
            'interior': bool(0 < i_throat < int(r_w.size) - 1),
            'interior_basis': (
                'Kolon alan minimumu İÇ kolonda (0 < i < ni−1): kontur '
                'bu alanda gerçekten daralıp genişliyor, minimum bir '
                'boğaz İDDİASIDIR.'
                if 0 < i_throat < int(r_w.size) - 1 else
                f'Kolon alan minimumu UÇ kolonda (i = {i_throat} / '
                f'{int(r_w.size) - 1}): kontur bu alanda tek yönlü, '
                'dolayısıyla minimum bir boğaz İDDİASI DEĞİL alanın '
                'kenarıdır. Yayımlanan radius_m bu KOLONUN duvar '
                'yarıçapıdır (kolonu sınırlayan iki düğüm yarıçapının '
                'ortalaması) ve konturun en küçük DÜĞÜM yarıçapından '
                'yarım hücre kadar büyüktür; ikisi birbirine YENİDEN '
                'YAZILMAZ. Boğaz konumu isteyen katman (ayrılma hükmü) '
                'bu indisi KULLANAMAZ.'),
        },
        'wall_pressure_Pa': wall_pressure,
        'wall_pressure_z_m': grid.z_centers[:, -1].copy(),
        'wall_pressure_basis': (
            'Duvara komşu hücre merkezi basıncı (hücre-merkezli FVM ham '
            'değeri); ekseni wall_pressure_z_m — duvara komşu hücre '
            'merkezlerinin z koordinatı [m], aynı uzunlukta (ni,). '
            'Aşama 1B: separation.py girdisi bu beyanla bağlanır.'),
        'shock_sensor_columns': sensor_columns,
        'shock_sensor_cells': sensor_cells,
        'shock_sensor_mode': _euler_core.SHOCK_SENSOR_MODE,
        'shock_sensor_threshold': float(_euler_core.SHOCK_SENSOR_THRESHOLD),
        'shock_sensor_basis': (
            'Şok sensörü (euler_core.shock_cell_flag; ÖH D37 A3a cfd-kok-a, '
            'OH-DK-14): HÜCRE bazlı Jameson-Schmidt-Turkel basınç anahtarı '
            'ν = |p₊ − 2p₀ + p₋|/(p₊ + 2p₀ + p₋), i ve j yönünde, yalnız '
            'SIKIŞMADA (akış yönünde basınç artarken) ve ν > eşik '
            f'({float(_euler_core.SHOCK_SENSOR_THRESHOLD):g}, ölçümden — DK ÖNCE '
            'alanlarında şoksuz sıkışma maks 0,0201 ⟷ en zayıf şok 0,2315); '
            'bayrak ±1 hücre genişletilir ve bayraklı HÜCREDE MUSCL eğimleri '
            'sıfırlanır (yerel birinci mertebe — şok stall tedavisi). '
            'Şoksuz genişlemede ateşlemez (eski kolon sensörü Back ıraksak '
            'konisini ve Rao boğazını bayraklıyordu). shock_sensor_columns '
            '= ≥1 bayraklı hücre içeren kolon sayısı (eski sözleşme adı), '
            'shock_sensor_cells = bayraklı hücre sayısı; ikisi de NİHAİ '
            'alanın canlı ölçümüdür.'),
        # --- AÇIK YOL PLATO-DONDURMA TETİĞİ (ÖH D37 A3a cfd-kok-a) ------
        # GCI geçerlilik kapısı (hrma/utils/gci.py) bu bloğu okur.
        'limiter_freeze': {
            'frozen_at_iter': frozen_at,
            'freeze_count': int(freeze_count),
            'window_iterations': int(plateau_window),
            'window_per_ni': float(PLATEAU_WINDOW_PER_NI),
            'stall_ratio': float(PLATEAU_STALL_RATIO),
            'descent_gate_decades': float(PLATEAU_DESCENT_DECADES),
            'descent_decades_at_freeze': freeze_descent_decades,
            'trigger': freeze_trigger,
            'persist_windows': int(PLATEAU_PERSIST_WINDOWS),
            'ramp_end_residual': ramp_end_residual,
            'applies_to': ('ssp_rk2 + second_order (açık yol) ve YALNIZ şok '
                           'sensörü bayrağı boşken (şoklu akışta dondurma '
                           'yok — OH-DK-13 ayrıştırma ölçümü); örtük yolun '
                           'kendi oturma-tetikli dondurması ayrıdır'),
            '_basis': (
                'Dondurma iki yoldan biriyle: trigger=descent_gate — (i) '
                'kalıntı rampa sonu değerinin 10^descent_gate_decades '
                'altına indikten ve (ii) window_iterations uzunluklu iki '
                'ardışık pencerede stall (recent > stall_ratio·before) '
                'ölçüldükten sonra; trigger=persistent_stall — iniş '
                'derinliğinden bağımsız, persist_windows·window '
                'uzunluğunda iki ardışık blokta stall (kalıcı plato). '
                'Şok sensörü bayrağı doluyken ikisi de kapalı. Pencere ağ '
                'boyuyla ölçeklidir (2,5·ni, taban 300). '
                'descent_decades_at_freeze = log10(rampa sonu kalıntısı / '
                'ilk dondurma anındaki kalıntı minimumu); None = hiç '
                'dondurulmadı. Gerekçe ve ölçüm PLATEAU_* sabitlerinde.'),
        },
        'kernel_backend': ('numba' if _kernels.NUMBA_AVAILABLE
                           else 'numpy'),
        'kernel_backend_basis': (
            'Yönlü HLLC akısının arka ucu (kernels.py): numba isteğe bağlı '
            'hızlandırmadır, kurulu değilse (ya da HRMA_CFD_DISABLE_NUMBA=1) '
            'saf NumPy yolu aynı sonucu üretir (eşdeğerlik bekçili; '
            'tests/cfd/test_performans.py).'),
        'not_modelled': not_modelled,
        'assumptions': assumptions,
        'viscous': viscous_block,
        'inputs': {
            'P0_Pa': P0, 'T0_K': T0, 'gamma': g, 'R_J_kgK': Rs,
            'Pb_Pa': None if Pb is None else float(Pb),
            'grid_ni': grid.ni, 'grid_nj': grid.nj,
            'cfl_start': float(cfl_start), 'cfl_max': float(cfl_max),
            'tol_res': float(tol_res), 'settle_tol': float(settle_tol),
            'freeze_settle_tol': freeze_settle_tol,
            'time_integrator': time_integrator,
            'cfl_implicit_max': float(cfl_implicit_max),
            'implicit_slope_refresh': int(implicit_slope_refresh),
            'viscous': viscous is not None,
            'turbulence': (None if viscous is None else viscous.turbulence),
            'wall_bc': wall_bc,
            'outlet_subsonic_anchor': outlet_subsonic_anchor,
            'y_plus_target': (None if y_plus_target is None
                              else float(y_plus_target)),
            'grid_radial_distribution': grid.radial_distribution,
            'initial_state': ('given' if initial_state is not None
                              else 'isentropic_guess'),
            '_basis': 'Çağıranın verdiği girdilerin yankısı (SI).',
        },
        'runtime_s': time.perf_counter() - t_start,
    }


def _settle_band(hist, window):
    """Son `window` iterasyondaki bağıl bant (hüküm ölçütünün KENDİ ifadesi).

    `_settled` ile AYNI aritmetik; ikisi ayrı yazılırsa hüküm ile beyan
    sessizce ayrılırdı (beyan, ölçütün kendisini raporlamalı).
    """
    # PENCERE TANIM ALANI (ÖH defter P6B1-05): 2'nin altında bant
    # TANIMSIZDIR ve "bilinmiyor" ASLA "oturdu" sayılmaz. window=0'da
    # ``hist[-0:]`` TÜM GEÇMİŞİ döndürür (Python dilimleme semantiği) ve
    # ``len(hist) < 0`` koruması hiç ateşlemez; window=1'de bant tek
    # örnekten tam 0,0 çıkar. İkisi de ölçüldü (MIN_SETTLE_WINDOW tanımı).
    # Sürücünün kendi kapısı bu değerleri zaten reddeder; burası
    # aritmetiğin KENDİ tanım alanı korumasıdır (helper doğrudan da
    # çağrılabiliyor) — sessizce sayı üretmez, NaN döner.
    if not hist or int(window) < MIN_SETTLE_WINDOW:
        return float('nan')
    window = int(window)
    band = hist[-window:]
    ref = abs(band[-1])
    if len(hist) < window or ref == 0.0:
        return float('nan')
    return float((max(band) - min(band)) / ref)


def _plateau_verdict(ornekler, tol_res,
                     rel_tol=DEFAULT_SCHEME_PLATEAU_REL_TOL,
                     min_samples=SCHEME_PLATEAU_MIN_SAMPLES,
                     min_span=DEFAULT_SCHEME_PROBE_EVERY):
    """ŞEMA kalıntısı DURDU mu? — plato hükmü (ÖH defter OH-Z5-14).

    ``ornekler``: (iterasyon, şema kalıntısı) çiftleri, artan iterasyonda.
    Son ``min_samples`` örnek alınır ve ÜÇ koşul birlikte aranır:
      1. pencere en az ``min_span`` iterasyon KAPSIYOR (iki ölçüm arka
         arkaya düşerse "N iterasyon boyunca durdu" denemez),
      2. örneklerin HEPSİ sonlu ve hedefin (``tol_res``) ÜSTÜNDE —
         hedefin altına inen bir dizi plato değil, YAKINSAMADIR,
      3. göreli yayılım (maks−min)/min < ``rel_tol``.

    Hüküm KAZANDIRMAZ, yalnız "daha çok bütçe İŞE YARAMAZ" bilgisini
    ölçülmüş biçimde taşır: koşan kişi tavanı büyütmekle kapıyı
    geçemeyeceğini buradan görür. Yetersiz örnekte ``detected`` False ve
    ``reason`` neyin eksik olduğunu ADIYLA söyler — "bilinmiyor" ASLA
    "plato" sayılmaz (fail-closed).
    """
    kayit = {
        'detected': False,
        'plateau_residual': None,
        'target_residual': float(tol_res),
        'relative_spread': None,
        'window_iterations': None,
        'samples': [],
        'rel_tol': float(rel_tol),
        'min_samples': int(min_samples),
        'probe_every': int(min_span),
        'reason': None,
    }
    pencere = list(ornekler)[-int(min_samples):]
    kayit['samples'] = [[int(i), float(v)] for i, v in pencere]
    if len(pencere) < int(min_samples):
        kayit['reason'] = (f'örnek yetersiz: {len(pencere)} < '
                           f'{int(min_samples)}')
        return kayit
    span = int(pencere[-1][0]) - int(pencere[0][0])
    kayit['window_iterations'] = span
    if span < int(min_span):
        kayit['reason'] = (f'pencere dar: {span} < {int(min_span)} '
                           f'iterasyon')
        return kayit
    degerler = [float(v) for _i, v in pencere]
    if not all(np.isfinite(v) for v in degerler):
        kayit['reason'] = 'örneklerde sonlu olmayan değer var'
        return kayit
    if min(degerler) <= 0.0:
        kayit['reason'] = 'sıfır/negatif kalıntı — göreli yayılım tanımsız'
        return kayit
    if not all(v >= float(tol_res) for v in degerler):
        kayit['reason'] = ('kalıntı hedefin altına indi — plato değil, '
                           'iniş')
        return kayit
    yayilim = (max(degerler) - min(degerler)) / min(degerler)
    kayit['relative_spread'] = float(yayilim)
    kayit['plateau_residual'] = float(degerler[-1])
    if yayilim >= float(rel_tol):
        kayit['reason'] = (f'yayılım {yayilim:.3e} ≥ eşik '
                           f'{float(rel_tol):g} — kalıntı hâlâ oynuyor')
        return kayit
    kayit['detected'] = True
    kayit['reason'] = (f'son {int(min_samples)} örnek {span} iterasyon '
                       f'boyunca {yayilim:.3e} göreli yayılımda ve hepsi '
                       f'hedefin ({float(tol_res):g}) üstünde')
    return kayit


#: Faz-kilitli bant için gereken en az örnek sayısı (bir bant iddiası
#: üç noktadan kurulmaz; dördüncüsü eğilimi görmek içindir).
_PHASE_MIN_SAMPLES = 4


def _settle_band_phase(hist, window, period):
    """Eğim TAZELEME çevriminin aynı fazından örneklenmiş bant (BEYAN).

    NEDEN VAR — ÖLÇÜLEN GEREKÇE (V2, 2026-08-18, KAPI vakası 192×48
    laminer lüle): satır-örtük yolda MUSCL eğimleri her K iterasyonda
    (DEFAULT_IMPLICIT_SLOPE_REFRESH) tazelenir ve tazeleme minmod
    gevelemesini YENİDEN ENJEKTE eder. KALINTI bu yüzden tam K periyotlu
    bir çevrime kilitlenir — ÖLÇÜLDÜ, K = 25 ve dalga biçimi çevrimden
    çevrime harfi harfine tekrar ediyor:
        it 3925: 4,276e-04 1,390e-04 6,396e-05 7,033e-05 …
        it 3950: 4,272e-04 1,390e-04 6,418e-05 7,049e-05 …
    Ham bant bu çevrimi "oturmamışlık" diye okur; oysa çevrim
    kararlı-hâl KÖKÜNÜN değil GİDİŞ YOLUNUN bir özelliğidir.

    Bu sayı HÜKME GİRMEZ (hüküm ham banttır, değişmedi); yayımlanır ki
    "kalıntı platosu" ile "büyüklüğün oturmaması" bir daha birbirine
    karıştırılmasın: ham bant ≫ faz-kilitli bant ise takılma tazeleme
    ÇEVRİMİNDEDİR, ham ≈ faz ise büyüklük gerçekten SÜRÜKLENİYORDUR.

    BU BEYAN KENDİ YAZARINI YALANLADI (ölçüm, iddia değil): KAPI
    koşusunda çıkış debisinin ham bandı 1,0081e-05, faz-kilitli (en kötü
    faz) bandı 1,0082e-05 — yani çıkış debisindeki oynama çevrim
    gürültüsü DEĞİL, gerçek bir sürüklenmedir. (Üç fazdan bakan bir ilk
    ölçüm 3,4e-07 gösterip "oturmuş" izlenimi vermişti; 25 fazın
    tamamına bakan bu işlev onu çürüttü. İyimser faz seçmemenin bedeli
    ve değeri budur.) Kalıntının çevrime kilitli olduğu ise ayrıca ve
    bağımsız olarak doğrudur — bekçisi test_viskoz_entegrasyon.py.

    Döndürülen değer fazlar üstündeki EN KÖTÜ banttır. NaN = ÖLÇÜLMEDİ
    (pencere ``MIN_SETTLE_WINDOW`` altında, periyot yok/1, geçmiş pencereyi
    doldurmuyor ya da hiçbir faz ``_PHASE_MIN_SAMPLES`` örneğe ulaşmıyor).
    TAM OTURMUŞ büyüklük NaN DEĞİL 0,0 döndürür — "en iyi ölçüm" ile
    "ölçüm yok" bir daha aynı sayıya düşmez (ÖH defter P6B1-11).
    """
    # PENCERE TANIM ALANI (ÖH defter OH-D19-16 — P6B1-05'in kardeşi):
    # kapı ``_settle_band``e konurken BURAYA konmamıştı. window=0'da
    # ``hist[-0:]`` TÜM GEÇMİŞİ döndürür ve ``len(hist) < 0`` koruması hiç
    # ateşlemez; ölçüldü (D23 once.json K3, sentetik tarihçe): window=0'da
    # ham bant NaN dönerken faz bandı 0,9998 YAYIMLIYORDU (defterin kendi
    # vakasında 0,9091) — yani aynı tanımsız girdide iki kardeş aritmetik
    # birbirinin ZITTINI söylüyordu. İki kapı
    # artık AYNI eşiktedir (MIN_SETTLE_WINDOW, tek kaynak).
    period = int(period)
    if not hist or int(window) < MIN_SETTLE_WINDOW or period <= 1:
        return float('nan')
    window = int(window)
    if len(hist) < window:
        return float('nan')
    band = list(hist[-window:])
    # ÖLÇÜLDÜ mü ÖLÇÜLMEDİ mi AYRI SAYILIR (ÖH defter P6B1-11): eskiden
    # dönüş ``en_kotu > 0.0`` koşuluna bağlıydı ve TAM OTURMUŞ bir
    # büyüklük (bütün fazların ham bandı tam 0,0) ile HİÇBİR fazın örnek
    # eşiğini dolduramaması AYNI NaN'ı üretiyordu. Oysa bu işlevin kendi
    # sözleşmesinde NaN "ölçülmedi" demektir; en iyi hâl (bant = 0,0)
    # "ölçülemedi" diye yayımlanınca okuma kuralı o köşede TERSİNE
    # dönüyordu. Ölçülen faz SAYILIR; sıfır bant artık 0,0 yayımlanır.
    en_kotu = 0.0
    olculen_faz = 0
    for faz in range(period):
        ornek = band[faz::period]
        if len(ornek) < _PHASE_MIN_SAMPLES:
            continue
        ref = abs(ornek[-1])
        if ref == 0.0:
            return float('nan')
        olculen_faz += 1
        en_kotu = max(en_kotu, (max(ornek) - min(ornek)) / ref)
    return float(en_kotu) if olculen_faz else float('nan')


def viscous_i_face_share(area_i, area_j):
    """Viskoz spektral yarıçapın i-yüzlerine düşen payı (salt geometrik).

    Λ_v = K·(ΣA²)/V biçiminde olduğundan (K = max(4/3ρ, γ/ρ)·μ_eff/Pr_eff,
    viscous.viscous_spectral_radius) ve K yüzler arasında ORTAK olduğundan,
    i payı yalnız alanların karelerinden gelir. Böylece "yalnız i-yüzleri"
    viskoz sınırı, viscous.py'nin formülü İKİNCİ KEZ yazılmadan elde edilir
    (parametre tutarlılığı kuralı: aynı bağıntının ikinci tanımı yok).
    """
    alan2_i = area_i[:-1] ** 2 + area_i[1:] ** 2
    alan2_j = area_j[:, :-1] ** 2 + area_j[:, 1:] ** 2
    return alan2_i / (alan2_i + alan2_j)


def viscous_local_dt(U, grid, gamma, R, cfl, transport, c_visc, *, geom=None,
                     area_i=None, area_j=None, axial_only=False,
                     i_face_share=None, mu_t=None):
    """Δt = CFL·V / [Σ_taşınım + C_visc·Σ Λ_v] (§5.6; Blazek §6.1.4 biçimi).

    Taşınım toplamı sürücünün KENDİ Δt fonksiyonundan GERİ OKUNUR
    (Σ = CFL·V/Δt_taşınım): spektral yarıçap formülü bu dosyada ikinci kez
    yazılmaz, kayma riski yapısal olarak kapalıdır.

    Args:
        axial_only: True → taşınım kısmı ``local_dt_axial`` (satır-örtük
            yol: j yönü örtük olduğu için adımı kısıtlamaz) ve viskoz kısım
            YALNIZ i-yüz payıyla alınır (j-viskoz terimleri Jacobian'a
            girer — relax_implicit.viscous_jacobian_blocks).
        i_face_share: ``viscous_i_face_share`` çıktısı (sürücü bir kez
            hesaplar); None ve axial_only=True ise burada hesaplanır.
        mu_t: türbülanslı viskozite alanı (SA açıkken); viskoz spektral
            yarıçap μ_L/Pr_L + μ_T/Pr_T ile büyür (Blazek §6.1.4'ün
            türbülanslı biçimi) — yani türbülanslı koşunun Δt sınırı
            laminerinkinden SIKIDIR ve bu sessizce atlanmaz.
    """
    if geom is None:
        geom = precompute_geometry(grid)
    if area_i is None:
        area_i = geom['area_i']
    if area_j is None:
        area_j = geom['area_j']
    if axial_only:
        dt_c = local_dt_axial(U, grid, gamma, cfl, area_i)
    else:
        dt_c = local_dt_axisym(U, grid, gamma, cfl, area_i, area_j)
    tasinim = cfl * grid.volume / dt_c
    lam_v = viscous_spectral_radius(grid, U, transport, R=R, geom=geom,
                                    mu_t=mu_t)
    if axial_only:
        if i_face_share is None:
            i_face_share = viscous_i_face_share(area_i, area_j)
        lam_v = lam_v * i_face_share
    return cfl * grid.volume / (tasinim + float(c_visc) * lam_v)


# ---------------------------------------------------------------------------
# SA-neg'in AYRIK (segregated) çevrimi — §5.5'in sürücü tarafı
#
# Ortalama akış 4×4 blok üç-köşegen çözülürken ν̃ AYNI j-satırları üstünde
# SKALER (m = 1) üç-köşegen çözülür. Cebir çekirdeği İKİNCİ KEZ YAZILMAZ:
# implicit.solve_block_tridiag blok boyutunu parametrik alır ve kendi
# docstring'inde m = 1'i "ayrık SA skaleri" olarak zaten beyan eder.
#
# Nokta-örtük köşegen MODELİN YAYIMLADIĞI ``jacobian_diag``dır (V3):
# parti 38'in ileri-fark VEKİLİ söküldü — sa_neg.sa_source_terms artık
# üretim türevini de taşıyan TAM analitik köşegeni yayımlıyor ve vekilin
# ölçtüğü oran 1'e indi (sökme öncesi ölçüm: levha 48×64'te 6,51 → 1,0008,
# lüle ikizi 48×16'da 5,51 → 1,0025; maks|FD−yayımlanan|/maks(yayımlanan)
# 1,19 → 1,8e-05). Kusurun kendisi ve kapanışı sa_neg.sa_source_terms
# docstring'inde; bekçileri tests/cfd/test_sa_neg.py (FD çaprazı +
# periyot-2) ve test_duz_levha_sa.py (levha hükmü).
# ---------------------------------------------------------------------------


def _sa_initial_state(grid, U, gamma, R, viscous):
    """SA alanının başlangıcı + değişmeyenleri (duvar mesafesi, ν̃_∞).

    ν̃ alanı serbest-akım değeriyle DOLDURULUR (standart SA başlangıcı):
    sınır tabakası üretim terimiyle kendiliğinden büyür. ν̃_∞ ya çağıranın
    verdiği sayıdır ya da başlangıç alanının GİRİŞ KOLONUNDAN ölçülen
    ν_∞ = <μ/ρ> ile bant oranından kurulur — hangisi olduğu beyandadır ve
    bant kapısı ``sa_neg.freestream_nu_tilde``ın kendisidir (ikinci kapı
    yazılmaz).
    """
    w = cons_to_prim_axisym(np.asarray(U, dtype=float), float(gamma))
    rho = w[..., 0]
    T = w[..., 3] / (rho * float(R))
    mu = viscous.transport.viscosity(T)
    nu_giris = float(np.mean(mu[0] / rho[0]))
    if viscous.sa_nu_tilde_inf is None:
        nu_tilde_inf = freestream_nu_tilde(nu_giris,
                                           viscous.sa_freestream_ratio)
        kaynak = (f'ölçüldü: ν_∞ = <μ/ρ>_(i=0) = {nu_giris:.6g} m²/s '
                  f'(başlangıç alanının giriş kolonu), ν̃_∞ = '
                  f'{float(viscous.sa_freestream_ratio):g}·ν_∞')
    else:
        nu_tilde_inf = float(viscous.sa_nu_tilde_inf)
        if not np.isfinite(nu_tilde_inf) or nu_tilde_inf <= 0.0:
            raise ValueError(
                'sa_nu_tilde_inf pozitif ve sonlu olmalı — gelen '
                f'{viscous.sa_nu_tilde_inf!r}.')
        kaynak = (f'çağıran verdi: ν̃_∞ = {nu_tilde_inf:.6g} m²/s '
                  f'(ölçülen giriş ν_∞ = {nu_giris:.6g} m²/s ile oranı '
                  f'{nu_tilde_inf / nu_giris:.4g})')
    nu_tilde = np.full((grid.ni, grid.nj), nu_tilde_inf)
    return {
        'nu_tilde': nu_tilde,
        'nu_tilde_inf': nu_tilde_inf,
        'nu_inlet_measured': nu_giris,
        'freestream_basis': kaynak,
        'd': wall_distance_field(grid),
        'mu_t': turbulent_viscosity(rho, nu_tilde, mu),
        'aux': None,
        'residual_norm': float('nan'),
        'residual_history': [],
        'res_scale': 1.0,
        'steps': 0,
    }


def _sa_line_implicit_delta(nu_tilde, rho, mu, dt, jacobian_diag, dudt,
                            mass_flux_i, mass_flux_j, grid, geom, grad_geom):
    """Δ(ρν̃) — j-yönü SKALER üç-köşegen (§5.5 "ayrık skaler üç-köşegen").

    Sistem, ortalama akışınkiyle AYNI kuruluş mantığındadır (M = V/Δt −
    ∂net/∂(ρν̃), yalnız j bağlaşımı):

    - **difüzyon** (yüz f, hücreler f−1|f):  c_f = Γ_f|S_f|/(σ d_n),
      Γ_f komşu hücre Γ'larının aritmetik ortalaması (SOL TARAF
      yaklaşıklığı — ``relax_implicit``in yüz μ kuralıyla aynı; kalıntının
      KENDİSİ ``sa_diffusive_residual``ın yeniden kurulmuş yüz değerlerini
      kullanır, hüküm-nötrlük gereği bu serbestlik meşrudur),
    - **duvar yüzü**: ν̃_w = 0 Dirichlet → yalnız KÖŞEGENE düşer
      (Γ_w = μ_w, çünkü ν̃ = 0'da Γ = μ),
    - **eksen yüzü**: dönel alan geometrik olarak sıfır → terim yok,
    - **taşınım**: birinci mertebe yukarı-akış bölmesi (ṁ⁺, ṁ⁻) —
      köşegene daima POZİTİF, çaprazlara negatif katkı,
    - **kaynak**: nokta-örtük köşegen V·J⁻ — ``sa_source_terms``ın
      yayımladığı ``jacobian_diag`` (V3'ten beri TAM analitik kaynak
      Jacobian'ının negatif kısmı; üretim KALINTIDA açık kalır, köşegene
      giden yalnız türevinin sönümleyici kısmıdır),
    - **i (çizgi-dışı) yüzleri**: bağlaşım blokları ATILIR, köşegene
      yalnız sönüm payı ½(|ṁ|_alt + |ṁ|_üst)/ρ + (c_i,alt + c_i,üst)/ρ
      eklenir — ortalama akışın DPLR deseninin (Wright, Candler & Bose,
      AIAA J. 36(9), 1998) skaler karşılığı. Bu pay OLMADAN satır-örtük
      yolun büyük Δt'si (CFL ~ 25) SA'yı ıraksatıyor: ÖLÇÜLDÜ — ilk
      gerçeklemede ν̃ 80 iterasyonda 10⁷ katına çıktı, pay eklenince
      koşu oturdu.

    ∂ν̃ = ∂(ρν̃)/ρ (ρ adım İÇİNDE dondurulur; kararlı hâlde ΔU → 0 olduğu
    için bu dondurma kökte iz bırakmaz).

    Köşegen baskınlık YAPISALDIR: Γ > 0 (SA-neg'in Denklem 20 garantisi),
    ṁ⁺ ≥ 0 ≥ ṁ⁻, J⁻ ≥ 0 ve V/Δt > 0 — yani blok-Thomas'ın pivotsuz
    sözleşmesinin şartı kurulumla sağlanır.

    Returns:
        (ni, nj) Δ(ρν̃) ya da girdi sonlu değilse ``None`` (istisna
        sızmaz — solve_block_tridiag'ın NaN kapısına gidilmez).
    """
    vol = grid.volume
    inv_rho = 1.0 / rho

    gam_c = diffusion_coefficient(rho, nu_tilde, mu)
    gam_f = 0.5 * (gam_c[:, :-1] + gam_c[:, 1:])          # (ni, nj−1)
    n_f = geom['n_hat_j'][:, 1:-1]
    s_f = geom['area_j'][:, 1:-1]
    d_vec = grad_geom['t_j'] * grad_geom['len_j'][..., None]
    d_n = np.abs(d_vec[..., 0] * n_f[..., 0] + d_vec[..., 1] * n_f[..., 1])
    c_f = gam_f * s_f / (SA_SIGMA * d_n)

    n_w = geom['wall_n_hat']
    b_w = grad_geom['b_j_hi']
    d_w = np.abs(b_w[..., 0] * n_w[..., 0] + b_w[..., 1] * n_w[..., 1])
    c_w = mu[:, -1] * geom['area_j'][:, -1] / (SA_SIGMA * d_w)

    c_alt = np.zeros_like(nu_tilde)
    c_alt[:, 1:] = c_f                    # hücre k'nin ALT yüzü (f = k)
    c_ust = np.zeros_like(nu_tilde)
    c_ust[:, :-1] = c_f                   # hücre k'nin ÜST yüzü (f = k+1)
    c_ust[:, -1] = c_w

    mf_arti = np.maximum(mass_flux_j, 0.0)
    mf_eksi = np.minimum(mass_flux_j, 0.0)

    # --- i (çizgi-dışı) yüzlerinin SÖNÜM payı: taşınım + difüzyon ---
    mf_i_mutlak = np.abs(mass_flux_i)
    n_i = geom['n_hat_i'][1:-1]
    s_i = geom['area_i'][1:-1]
    d_i_vec = grad_geom['t_i'] * grad_geom['len_i'][..., None]
    d_i = np.abs(d_i_vec[..., 0] * n_i[..., 0] + d_i_vec[..., 1] * n_i[..., 1])
    c_i = 0.5 * (gam_c[:-1] + gam_c[1:]) * s_i / (SA_SIGMA * d_i)
    c_i_alt = np.zeros_like(nu_tilde)
    c_i_alt[1:] = c_i
    c_i_ust = np.zeros_like(nu_tilde)
    c_i_ust[:-1] = c_i

    diag = (vol / dt + vol * jacobian_diag
            + inv_rho * (c_alt + c_ust + mf_arti[:, 1:] - mf_eksi[:, :-1]
                         + c_i_alt + c_i_ust
                         + 0.5 * (mf_i_mutlak[:-1] + mf_i_mutlak[1:])))
    upper = (mf_eksi[:, 1:-1] - c_f) * inv_rho[:, 1:]
    lower = (-mf_arti[:, 1:-1] - c_f) * inv_rho[:, :-1]
    rhs = vol * dudt

    for dizi in (diag, upper, lower, rhs):
        if not np.all(np.isfinite(dizi)):
            return None
    if np.any(diag <= 0.0):
        return None
    return solve_block_tridiag(lower[..., None, None], diag[..., None, None],
                               upper[..., None, None], rhs[..., None])[..., 0]


def _sa_update(sa, U, dt, gradients, grid, geom, grad_geom, gamma, R,
               viscous, w_in, w_out):
    """Bir SA iterasyonu: kalıntı → skaler üç-köşegen → ν̃, μ_t (yerinde).

    Ω (girdaplılık) ÇAĞIRANDAN gelir ve viskoz kalıntının KULLANDIĞI hız
    gradyanlarından kurulur (``viscous_residual`` aux'ünde yayımlanır):
    ikinci bir gradyan tanımı doğmasın diye — ``sa_neg.py``nin sözleşme
    maddesi budur.

    Kütle akısı ``sa_neg.face_mass_flux`` VEKİLİDİR (euler_core HLLC yüz
    akılarını yayımlamıyor; beyanda ``mass_flux_source`` ile görünür).
    Vekil, sürücünün KENDİ sınır durumlarıyla kurulur: duvarda u = 0
    verildiği için duvar yüzünden ν̃ sızıntısı ayrık olarak TAM SIFIRDIR
    (dışdeğerlemeyle bırakılsaydı sızardı — ölçülebilir kusur).

    Returns:
        ``True`` sağlam adım; ``False`` fiziksel/sonlu olmayan durum.
    """
    if not np.all(np.isfinite(dt)):
        return False
    w = cons_to_prim_axisym(U, float(gamma))
    if nonphysical_state(w):
        return False
    rho, uz, ur, p = w[..., 0], w[..., 1], w[..., 2], w[..., 3]
    T = p / (rho * float(R))
    mu = viscous.transport.viscosity(T)

    omega = vorticity_magnitude(gradients['u_z'], gradients['u_r'])
    if not np.all(np.isfinite(omega)):
        return False

    sifir = np.zeros(grid.ni)
    mf_i, mf_j = face_mass_flux(
        grid, rho, uz, ur, grad_geom=grad_geom,
        bc_rho=BoundaryFaceValues(i_lo=w_in[:, 0], i_hi=w_out[:, 0]),
        bc_uz=BoundaryFaceValues(i_lo=w_in[:, 1], i_hi=w_out[:, 1],
                                 j_hi=sifir),
        bc_ur=BoundaryFaceValues(i_lo=w_in[:, 2], i_hi=w_out[:, 2],
                                 j_lo=sifir, j_hi=sifir))

    dudt, aux = sa_residual(
        grid, U, viscous.transport, R=R, nu_tilde=sa['nu_tilde'],
        omega=omega, wall_distance=sa['d'], mass_flux=(mf_i, mf_j),
        inlet_nu_tilde=sa['nu_tilde_inf'], scheme=viscous.sa_scheme,
        grad_geom=grad_geom, skew_iters=viscous.skew_iters,
        corrected=viscous.corrected,
        density_correction=viscous.sa_density_correction)
    if not np.all(np.isfinite(dudt)):
        return False

    # Nokta-örtük köşegen MODELİN YAYIMLADIĞI tam analitik köşegendir
    # (sa_neg.sa_source_terms, V3 — ileri-fark vekili söküldü; oran
    # ölçümü modül altındaki blok yorumunda).
    jac = aux['source'].jacobian_diag
    if not np.all(np.isfinite(jac)):
        return False
    delta = _sa_line_implicit_delta(
        sa['nu_tilde'], rho, mu, dt, jac, dudt,
        mf_i, mf_j, grid, geom, grad_geom)
    if delta is None:
        return False

    nu_yeni = sa['nu_tilde'] + delta / rho
    if not np.all(np.isfinite(nu_yeni)):
        return False

    vol = grid.volume
    sa['nu_tilde'] = nu_yeni
    sa['mu_t'] = turbulent_viscosity(rho, nu_yeni, mu)
    sa['aux'] = aux
    sa['residual_norm'] = float(
        np.sqrt(np.sum(dudt ** 2 * vol) / np.sum(vol)) / sa['res_scale'])
    sa['residual_history'].append(sa['residual_norm'])
    sa['steps'] += 1
    return True


def wall_grid_quality(grid, geom, grad_geom, throat_index=None):
    """Duvar hücrelerinin ÇARPIKLIK AÇISI ve EN-BOY ORANI (§5.7 kararı).

    Tasarım belgesi §5.7: "V1'de H-ızgara + radyal kümeleme; çarpıklık
    ÖLÇÜLÜP yayımlanır (koşum başına maksimum duvar çarpıklık açısı + o
    bölgedeki en-boy oranı)". Bu işlev o beyanın kendisidir.

    Tanımlar (ölçülen büyüklükler, korelasyon değil):
      - **çarpıklık açısı** θ: ayrık duvar-normal türevin ALINDIĞI doğru
        (hücre merkezi → duvar yüzü orta noktası, ``b_j_hi``) ile duvar
        NORMALİ arasındaki açı. H-tipi ızgarada j çizgileri radyaldir,
        duvar normali değildir; eğik duvarda θ duvar eğim açısına eşittir
        (gerçek konturun yakınsak bölgesinde ~42°). θ = 0 dik ızgaradır.
      - **en-boy oranı** AR: duvar yüzünün DÜZLEMSEL uzunluğu ÷ ilk hücre
        kalınlığı (2·|b·n̂|). y⁺ ≈ 1 ızgarasında 10³ sınıfına çıkar.
      - **duvar açısı değişimi** Δα: komşu duvar SEGMENTLERİNİN eğim
        açıları arasındaki fark. Bu bir ızgara değil KONTUR büyüklüğüdür
        (eğrilik × eksenel adım): duvar düğümleri değişmedikçe topolojiden
        bağımsızdır — duvar-normal yaka (V1b) onu DEĞİŞTİRMEZ ve bu ayrım
        yakanın beyanında da yazılıdır.
      - **AR·Δα** (parti 39 A1'in DİNAMİK metriği): parti 38'in statik
        ölçümünde kırılma sınırı 12-20 çıkmıştı; A1'in gerdirme merdiveni
        DİNAMİK sınırın 0,13-0,52 arasında, yani ~30 kat aşağıda olduğunu
        ölçtü. Mekanizma: yüz orta noktasının hücre merkezlerini birleştiren
        doğrudan normal sapması ≈ L·Δα/4, ilk hücre kalınlığına göre
        AR·Δα mertebesindedir — duvar-normal gradyan o kadar uzağa taşınır.
        Her koşumda yayımlanır ki ıraksayan bir koşunun ızgara payı
        okunabilsin.
      - **komşu hücre hacim oranı** (j yönü): yaka harmanının "yeni bir
        değişim tepesi üretmediği" iddiasının ölçüsü. Gerdirilmiş ızgarada
        bu sayı gerdirmenin kendi büyüme oranını yansıtır; harman onu
        yükseltiyorsa harman bir tepe üretiyor demektir.

    Returns:
        dict — maksimum açı ve o istasyondaki AR, maksimum AR ve o
        istasyondaki açı, boğaz istasyonunun açısı (belgenin "boğazda
        duvar açısı sıfırdan geçer, yani q_w'nin tepe yaptığı yerde
        çarpıklık YOKTUR" cümlesinin ölçüsü), Δα ve AR·Δα maksimumları,
        radyal hacim oranı ve künye.
    """
    b_w = grad_geom['b_j_hi']
    n_w = geom['wall_n_hat']
    b_len = np.linalg.norm(b_w, axis=-1)
    b_n = np.abs(b_w[..., 0] * n_w[..., 0] + b_w[..., 1] * n_w[..., 1])
    cos_t = np.clip(b_n / b_len, 0.0, 1.0)
    aci = np.degrees(np.arccos(cos_t))
    kalinlik = 2.0 * b_n
    s_duvar = np.linalg.norm(grid.face_j_planar[:, -1], axis=-1)
    ar = s_duvar / kalinlik
    i_aci = int(np.argmax(aci))
    i_ar = int(np.argmax(ar))
    z_w = grad_geom['mid_j'][:, -1, 0]
    # Duvar SEGMENT açıları ve komşu farkları (kontur büyüklüğü — düğümler
    # değişmedikçe topolojiden bağımsız; yaka bunu değiştirmez).
    alfa = np.arctan2(np.diff(grid.R[:, -1]), np.diff(grid.Z[:, -1]))
    d_alfa = np.abs(np.diff(alfa))                       # (ni-1,)
    carpim = 0.5 * (ar[:-1] + ar[1:]) * d_alfa           # AR·Δα (birimsiz)
    i_carpim = int(np.argmax(carpim)) + 1 if carpim.size else 0
    # Radyal komşu hücre hacim oranı: harman tepesi ölçüsü
    hacim_oran = np.maximum(grid.volume[:, :-1] / grid.volume[:, 1:],
                            grid.volume[:, 1:] / grid.volume[:, :-1])
    i_hac, j_hac = np.unravel_index(int(np.argmax(hacim_oran)),
                                    hacim_oran.shape)
    cikti = {
        'max_wall_skew_deg': float(aci[i_aci]),
        'max_wall_skew_index': i_aci,
        'max_wall_skew_z_m': float(z_w[i_aci]),
        'aspect_ratio_at_max_skew': float(ar[i_aci]),
        'max_aspect_ratio': float(ar[i_ar]),
        'max_aspect_ratio_index': i_ar,
        'wall_skew_at_max_aspect_deg': float(aci[i_ar]),
        'mean_wall_skew_deg': float(np.mean(aci)),
        'first_cell_thickness_m_min': float(np.min(kalinlik)),
        'first_cell_thickness_m_max': float(np.max(kalinlik)),
        'max_wall_angle_change_deg': (float(np.degrees(np.max(d_alfa)))
                                      if d_alfa.size else 0.0),
        'max_aspect_x_angle_change': (float(np.max(carpim))
                                      if carpim.size else 0.0),
        'max_aspect_x_angle_change_index': i_carpim,
        'max_aspect_x_angle_change_z_m': (float(z_w[i_carpim])
                                          if carpim.size else float('nan')),
        'max_cell_volume_ratio_j': float(hacim_oran[i_hac, j_hac]),
        'max_cell_volume_ratio_j_index': (int(i_hac), int(j_hac)),
        'wall_collar': (None if getattr(grid, 'wall_collar', None) is None
                        else grid.wall_collar),
        '_basis': (
            'Duvar çarpıklık açısı = (hücre merkezi → duvar yüzü) vektörü '
            'ile duvar normali arasındaki açı [derece]; en-boy oranı = '
            'duvar yüzünün düzlemsel uzunluğu / ilk hücre kalınlığı. '
            'Belgenin §5.7 kararı gereği HER KOŞUMDA yayımlanır: gradyan '
            'doğruluğu çarpıklıkla düşer ve bu, q_w iddiasının okunma '
            'şartıdır. Boğazda duvar eğimi sıfırdan geçtiği için q_w '
            'tepesinin bulunduğu istasyonda çarpıklık yoktur — '
            'throat_wall_skew_deg bunun ölçüsüdür. '
            'max_aspect_x_angle_change = AR·Δα, parti 39 A1\'in DİNAMİK '
            'kararsızlık metriğidir (ölçülen dinamik sınır 0,13-0,52; '
            'parti 38\'in statik kırılma sınırı 12-20 — aynı ızgarada iki '
            'sınır ~30 kat ayrı). Δα duvar KONTURUNUN büyüklüğüdür: '
            'duvar-normal yaka (wall_collar) duvar düğümlerini '
            'kaydırmadığından Δα\'yı DEĞİŞTİRMEZ, yalnız çarpıklığı ve '
            'AR\'yi (1/cos α kadar) düşürür — yakanın neyi çözüp neyi '
            'çözmediği bu üç sayı yan yana okunarak görülür. '
            'max_cell_volume_ratio_j radyal komşu hücre hacim oranıdır ve '
            'yaka harmanının kendi başına bir metrik tepesi üretmediğinin '
            'ölçüsüdür (yakasız gerdirilmiş ızgarayla karşılaştırılır).'),
    }
    if throat_index is not None:
        cikti['throat_index'] = int(throat_index)
        cikti['throat_wall_skew_deg'] = float(aci[int(throat_index)])
        cikti['throat_aspect_ratio'] = float(ar[int(throat_index)])
    return cikti


def first_cell_for_y_plus(grid, P0, T0, gamma, R, transport,
                          wall_temperature_K, y_plus_target=1.0,
                          transition=None):
    """Hedef y⁺ için birinci hücre KALINLIĞI ön-tahmini [m] + beyan (§5.7).

    ZİNCİR (yeni sabit YOK — her halka deponun kendi katmanından):
      1. Kenar (çekirdek) durumu: sürücünün KENDİ izantropik tahmininden
         (``_isentropic_initial_state``) okunur — quasi-1B bağıntıları bu
         dosyada ikinci kez yazılmaz.
      2. τ_w(z): entegral sınır tabakası marşı
         (``hrma.flow.boundary_layer.solve_boundary_layer``; Eckert
         referans sıcaklığı + van Driest II + Ludwieg-Tillmann). Tasarım
         §4.4'ün "entegral katman RANS'ın HIZ kanadıdır" maddesinin
         doğrudan kullanımı: ızgara ön-tahmini onun işidir. Belgenin
         §4.1 tablosundaki düz levha korelasyonu (c_f = 0,0592·Re_x^−0,2)
         BİLEREK kullanılmadı — depoda tanımı yok, yazılsaydı aynı
         kavramın (türbülanslı sürtünme katsayısı) İKİNCİ tanımı olurdu
         (CLAUDE.md kural 11).
      3. μ_w, ρ_w: taşınım TEK kaynağından (``transport.viscosity``) ve
         duvar sıcaklığından; ρ_w = p_kenar/(R·T_w) — sınır tabakası
         boyunca basınç sabit kabulü (aynı yaklaşım çıkış çapasının da
         gerekçesidir, ``OUTLET_ANCHOR_BASIS``).
      4. y_merkez = y⁺·μ_w/(ρ_w·u_τ), u_τ = √(τ_w/ρ_w).
         Hücre KALINLIĞI = 2·y_merkez: y⁺ hücre MERKEZİNDE ölçülür
         (``_viscous_output_block``: y = merkez→duvar mesafesi), yani
         kalınlık merkez mesafesinin iki katıdır. Bu çarpan atlanırsa
         gerçekleşen y⁺ hedefin YARISI çıkar — beyan yalancı biçimde
         "iyi" görünürdü.
      5. Tek bir kalınlık tüm duvara uygulandığından EN SIKI istasyon
         (maks τ_w) belirleyicidir: min(y_merkez) alınır.

    Args:
        grid: AxisymGrid (kontur ve istasyonlar buradan).
        P0, T0, gamma, R: rezervuar ve gaz (sürücüyle aynı).
        transport: ``GasTransport`` (μ(T) tek kaynağı).
        wall_temperature_K: duvar sıcaklığı [K] (skaler ya da (ni,)).
        y_plus_target: hedef y⁺ (varsayılan 1,0 — duvar-çözümlü ızgara).
        transition: ``boundary_layer`` geçiş kipi; None → o modülün
            roket lülesi varsayılanı (turbulent_from_start).

    Returns:
        (first_cell_m, beyan): kalınlık [m] ve ölçüm künyesi.
    """
    from hrma.flow.boundary_layer import (
        TRANSITION_TURBULENT_FROM_START, solve_boundary_layer,
    )

    g = float(gamma)
    Rs = float(R)
    y_hedef = float(y_plus_target)
    if not np.isfinite(y_hedef) or y_hedef <= 0.0:
        raise ValueError('y_plus_target pozitif ve sonlu olmalı — gelen '
                         f'{y_plus_target!r}.')
    if wall_temperature_K is None:
        raise ValueError(
            'wall_temperature_K ZORUNLU: ön tahmin ρ_w = p/(R·T_w) ve '
            'μ_w = μ(T_w) üstünden kurulur, T_w olmadan y⁺ mesafesi '
            'tanımsızdır. ADYABATİK koşuda çağıran kurtarma sıcaklığını '
            '(hrma.flow.boundary_layer.recovery_temperature) hesaplayıp '
            'GEÇİRMELİDİR — burada sessizce bir duvar sıcaklığı '
            'varsayılmaz.')
    U_tahmin, i_throat = _isentropic_initial_state(grid, float(P0), float(T0),
                                                   g, Rs, Pb=None)
    w_e = cons_to_prim_axisym(U_tahmin, g)[:, 0, :]     # kolon içinde sabit
    p_e = w_e[..., 3]
    T_e = p_e / (Rs * w_e[..., 0])
    mach_e = w_e[..., 1] / np.sqrt(g * Rs * T_e)
    z_st = grid.z_centers[:, -1]
    r_st = _column_wall_radius(grid)
    T_w = np.broadcast_to(np.asarray(wall_temperature_K, dtype=float),
                          r_st.shape).astype(float)

    bl = solve_boundary_layer(
        z_st, r_st, mach_e, p_e, T_e, gamma=g, gas_constant_J_kgK=Rs,
        prandtl=transport.prandtl, viscosity_fn=transport.viscosity,
        wall_temperature_K=T_w, specific_heat_J_kgK=transport.cp,
        transition=(TRANSITION_TURBULENT_FROM_START if transition is None
                    else transition))
    tau_w = np.abs(np.asarray(bl['stations']['tau_wall_Pa'], dtype=float))
    rho_w = p_e / (Rs * T_w)
    mu_w = np.asarray(transport.viscosity(T_w), dtype=float)
    gecerli = np.isfinite(tau_w) & (tau_w > 0.0)
    if not np.any(gecerli):
        raise ValueError(
            'Sınır tabakası marşı hiçbir istasyonda sonlu τ_w vermedi — '
            f"marş durumu {bl['march']['status']!r}. Ön-tahmin uydurma bir "
            'değere düşmez; vakayı ya da duvar sıcaklığını gözden geçirin.')
    u_tau = np.sqrt(tau_w[gecerli] / rho_w[gecerli])
    y_merkez = y_hedef * mu_w[gecerli] / (rho_w[gecerli] * u_tau)
    i_yerel = int(np.argmin(y_merkez))
    i_siki = int(np.arange(r_st.size)[gecerli][i_yerel])
    kalinlik = 2.0 * float(np.min(y_merkez))
    beyan = {
        'y_plus_target': y_hedef,
        'first_cell_m': kalinlik,
        'first_cell_center_m': 0.5 * kalinlik,
        'driving_station_index': i_siki,
        'driving_station_z_m': float(z_st[i_siki]),
        'driving_station_tau_wall_Pa': float(tau_w[i_siki]),
        # Zincirin ARA HALKALARI da yayımlanır: çağıran (ve bekçi)
        # y_merkez = y⁺·μ_w/(ρ_w·u_τ) bağıntısını BURADAN yeniden kurup
        # yayımlanan kalınlıkla karşılaştırabilsin. Kalınlık ↔ merkez
        # mesafesi karışması (×2 çarpanı) ancak böyle yakalanır.
        'driving_station_u_tau_m_s': float(u_tau[i_yerel]),
        'driving_station_rho_wall_kg_m3': float(rho_w[i_siki]),
        'driving_station_mu_wall_Pa_s': float(mu_w[i_siki]),
        'throat_index': int(i_throat),
        'stations_used': int(np.sum(gecerli)),
        'stations_total': int(r_st.size),
        'bl_march_status': bl['march']['status'],
        'bl_transition_mode': bl['march']['transition_mode'],
        'uniform_first_cell_m': float(np.min(r_st) / grid.nj),
        '_basis': (
            'Birinci hücre kalınlığı ÖN TAHMİNİDİR (§5.7): kenar durumu '
            'sürücünün izantropik tahmininden, τ_w entegral sınır '
            'tabakası marşından (Eckert + van Driest II + '
            'Ludwieg-Tillmann; hrma.flow.boundary_layer), μ_w taşınımın '
            'tek kaynağından. Kalınlık = 2·y⁺·μ_w/(ρ_w·u_τ) — y⁺ hücre '
            'MERKEZİNDE ölçüldüğü için iki kat. Tüm duvara TEK kalınlık '
            'uygulandığından en sıkı istasyon (maks τ_w) belirler. '
            'TOPOLOJİ UYARISI: bu kalınlık duvar-NORMAL bir mesafedir; '
            'H-ızgarada ise RADYAL kalınlık olarak uygulanır, yani '
            'gerçekleşen duvar-normal kalınlık onun cos α katıdır (gerçek '
            'motor konturunda ölçüldü: 0,7416). Duvar-normal yaka '
            '(grid_axisym.WallCollar) açıkken ikisi çakışır ve tahmin '
            'anlamına tam oturur. '
            'GERÇEKLEŞEN y⁺ koşumdan sonra ayrıca ÖLÇÜLÜR ve bu tahminle '
            'karşılaştırılır (viscous["y_plus_loop"]); tahminin kendisi '
            'hüküm değildir.'),
    }
    return kalinlik, beyan


def solve_with_y_plus_target(z_nodes, r_wall, nj, P0, T0, gamma, R, *,
                             viscous, y_plus_target=1.0, max_regrid=1,
                             y_plus_band=(0.5, 1.5), stretch=None,
                             wall_collar=None, return_grid=False, **kw):
    """DÜRÜST y⁺ DÖNGÜSÜ (§5.7): ön-tahmin → koş → ÖLÇ → (bir kez) yeniden ızgarala.

    Tasarımın maddesi harfi harfine: ilk hücre bir ÖN TAHMİNDEN seçilir,
    koşum sonrası gerçekleşen y⁺ ÖLÇÜLÜR ve yayımlanır; hedeften sapma
    varsa iki seçenek BEYANLA sunulur — (i) sonucu y⁺ rozetiyle ver,
    (ii) bir kez yeniden ızgaralayıp koş (``regrid_count`` beyanlı).
    SESSİZ DÜZELTME YOK: her koşumun hedefi, gerçekleşeni ve sapması
    ``viscous['y_plus_loop']`` içinde durur; yeniden ızgaralama olduysa
    ÖNCEKİ koşumun ölçümü de ``history``de kalır.

    Yeniden ızgaralama ölçekleyicisi KORELASYON DEĞİL ÖLÇÜMDÜR: y⁺ sabit
    u_τ'da y ile doğrusal olduğundan yeni kalınlık = eski kalınlık ×
    (hedef / gerçekleşen_maks). u_τ ızgarayla zayıfça değiştiği için bu
    bir SABİT NOKTA yinelemesidir, garantili değil — bu yüzden bütçe
    ``max_regrid`` ile sınırlıdır ve sonuç yine ölçülüp beyan edilir.

    Args:
        z_nodes, r_wall, nj: ızgara kurulumu (build_grid_from_wall girdisi).
        P0, T0, gamma, R: rezervuar ve gaz.
        viscous: ``ViscousOptions`` (ZORUNLU — y⁺ viskoz koşuda ölçülür).
        y_plus_target: hedef y⁺.
        max_regrid: en fazla kaç yeniden ızgaralama (§5.7: "bir kez").
        y_plus_band: (alt, üst) kabul bandı — gerçekleşen/hedef oranı bu
            bandın içindeyse yeniden ızgaralanmaz. Bant bir HÜKÜM değil,
            döngünün durma ölçütüdür ve beyanda görünür.
        stretch: gerdirme ailesi (None → grid_axisym varsayılanı).
        wall_collar: ``WallCollar`` ya da None (varsayılan → yaka yok).
            DÖNGÜNÜN HER TURUNDA AYNEN taşınır: yeniden ızgaralama yalnız
            ilk hücre kalınlığını değiştirir, topolojiyi DEĞİŞTİRMEZ —
            aksi hâlde iki tur farklı ızgara ailesinde ölçülür ve oran
            ölçekleyicisi anlamını yitirirdi. Taşındığı her turda
            ``viscous['y_plus_loop']['grid_wall_collar']`` ile beyanlıdır.
        return_grid: False (VARSAYILAN, bugünkü imza) → yalnız sonuç
            sözlüğü döner. True → ``(sonuç, grid)`` ikilisi döner ve grid
            döngünün SON turunda GERÇEKTEN çözülen ``AxisymGrid``dir.
            ÖH D20 / OH-D16-04: çağıran (ör. ``/api/cfd/nozzle``) duvar
            büyüklüklerini kendi ızgarasıyla yeniden işliyorsa o ızgaranın
            çözümün ızgarasıyla AYNI nesne olması gerekir — kalınlığı
            beyandan okuyup ızgarayı yeniden kurmak sessiz bir kaymaya
            (``first_cell_m`` yuvarlaması, gerdirme ailesi farkı) açık
            olurdu. Nesne doğrudan verilir, türetilmez.
        **kw: ``solve_steady_axisym``a geçen diğer ayarlar.

    Returns:
        ``solve_steady_axisym`` sonucu; ``viscous['y_plus_loop']`` döngünün
        tam kaydını (hedef, her turun ilk hücresi ve ölçülen y⁺'ı,
        regrid_count, durma sebebi) taşır. ``return_grid=True`` ise
        ``(sonuç, grid)``.
    """
    from hrma.cfd.grid_axisym import DEFAULT_RADIAL_STRETCH

    if viscous is None:
        raise ValueError(
            'solve_with_y_plus_target viskoz koşu içindir: y⁺ duvar kayma '
            'gerilmesinden ÖLÇÜLÜR, Euler yolunda τ_w yoktur (kayma '
            'duvarı). viscous=ViscousOptions(...) verin.')
    alt, ust = (float(y_plus_band[0]), float(y_plus_band[1]))
    if not (0.0 < alt <= 1.0 <= ust):
        raise ValueError('y_plus_band 0 < alt ≤ 1 ≤ üst olmalı — gelen '
                         f'{y_plus_band!r}.')
    aile = DEFAULT_RADIAL_STRETCH if stretch is None else stretch
    z_nodes = np.asarray(z_nodes, dtype=float)
    r_wall = np.asarray(r_wall, dtype=float)

    # Ön tahmin DÜZGÜN ızgaradan yapılır (τ_w tahmini ızgaradan bağımsız
    # bir entegral marştır; ızgara yalnız istasyon eksenini verir).
    grid = build_grid_from_wall(z_nodes, r_wall, nj)
    kalinlik, on_tahmin = first_cell_for_y_plus(
        grid, P0, T0, gamma, R, viscous.transport, viscous.T_wall,
        y_plus_target=y_plus_target)

    gecmis = []
    regrid = 0
    durma = None
    sonuc = None
    while True:
        grid = build_grid_from_wall(z_nodes, r_wall, nj,
                                    first_cell_m=kalinlik, stretch=aile,
                                    wall_collar=wall_collar)
        sonuc = solve_steady_axisym(grid, P0, T0, gamma, R, viscous=viscous,
                                    y_plus_target=y_plus_target, **kw)
        olcum = sonuc['viscous']['y_plus_loop']
        gecmis.append({
            'regrid_index': regrid,
            'first_cell_m': kalinlik,
            # ETKİN harman katmanı (blend_layers=None → nj//2) yazılır:
            # isteğin kendisi değil, o turda GERÇEKTEN kurulan topoloji.
            'wall_collar_layers': (None if wall_collar is None
                                   else (wall_collar.layers,
                                         wall_collar.effective_blend(nj))),
            'y_plus_max': olcum['achieved_max'],
            'y_plus_mean': olcum['achieved_mean'],
            'ratio_max_to_target': olcum['ratio_max_to_target'],
            # OH-D31-15: üç durumlu hüküm AYNEN taşınır; bool'a
            # çevirmek 'değerlendirilmedi'yi 'yakınsamadı' yapardı.
            'converged': (None if sonuc['converged'] is None
                          else bool(sonuc['converged'])),
            'convergence_status': sonuc['convergence_status'],
            'iterations': int(sonuc['iterations']),
        })
        oran = olcum['ratio_max_to_target']
        if alt <= oran <= ust:
            durma = (f'gerçekleşen/hedef = {oran:.4g} kabul bandının '
                     f'[{alt:g}; {ust:g}] içinde')
            break
        if regrid >= int(max_regrid):
            durma = (f'yeniden ızgaralama bütçesi ({max_regrid}) doldu; '
                     f'gerçekleşen/hedef = {oran:.4g} bandın DIŞINDA — '
                     'sonuç y⁺ rozetiyle birlikte veriliyor (§5.7 seçenek i)')
            break
        if not np.isfinite(oran) or oran <= 0.0:
            durma = ('ölçülen y⁺ oranı sonlu/pozitif değil — yeniden '
                     'ızgaralama ölçekleyicisi tanımsız, döngü durdu')
            break
        kalinlik = kalinlik / oran
        regrid += 1

    dongu = dict(sonuc['viscous']['y_plus_loop'])
    dongu.update({
        'regrid_count': regrid,
        'regrid_budget': int(max_regrid),
        'acceptance_band': (alt, ust),
        'stop_reason': durma,
        'pre_estimate': on_tahmin,
        'history': gecmis,
        '_basis': dongu['_basis'] + (
            ' DÖNGÜ (solve_with_y_plus_target): ilk hücre ön tahminden '
            '(pre_estimate) seçildi, her turda gerçekleşen y⁺ ölçüldü ve '
            'bant dışındaysa kalınlık ÖLÇÜLEN orana bölünerek yeniden '
            'ızgaralandı; her turun kaydı history\'de durur. Sessiz '
            'düzeltme yoktur: son sonucun hedefe uyup uymadığı '
            'stop_reason ve ratio_max_to_target ile okunur. Duvar-normal '
            'yaka (V1b) verilmişse HER TURDA aynen taşınır — yeniden '
            'ızgaralama yalnız kalınlığı değiştirir, topolojiyi değil '
            '(history satırlarında wall_collar_layers ile beyanlı).'),
    })
    sonuc['viscous']['y_plus_loop'] = dongu
    if return_grid:
        return sonuc, grid
    return sonuc


def _viscous_output_block(viscous, aux_visc, r_final, geom, grad_geom,
                          w, Rs, rho0, a0, length, vol, vol_sum,
                          grid=None, y_plus_target=None, sa=None,
                          throat_index=None):
    """Viskoz koşunun yayımlanan bloğu: duvar dizileri, y⁺, kalıntı bileşenleri.

    HİÇBİR SAYI UYDURULMAZ: duvar büyüklükleri viscous.py'nin ÖLÇTÜĞÜ
    ``WallOutputs`` dizileridir, y⁺ τ_w'den hesaplanır (laminer koşuda
    duvar kayma gerilmesinin kendisi ölçüldüğü için y⁺ bir korelasyon
    TAHMİNİ değil ÖLÇÜMDÜR — §5.7'nin "gerçekleşen y⁺ ölçülür" maddesi).
    """
    wall = aux_visc['wall']
    # Duvar-normal ilk hücre mesafesi: merkez → duvar yüzü vektörünün
    # normal izdüşümü (çarpık hücrede de doğru olan büyüklük).
    b_w = grad_geom['b_j_hi']
    n_w = geom['wall_n_hat']
    y_wall = np.abs(b_w[..., 0] * n_w[..., 0] + b_w[..., 1] * n_w[..., 1])
    # Duvar yoğunluğu: komşu hücrenin basıncı + DUVAR sıcaklığı (basınç
    # sınır tabakası boyunca sabit kabul edilir — sınır tabakası
    # yaklaşımının kendisi, beyanlı).
    rho_wall = w[:, -1, 3] / (Rs * wall.T_wall_K)
    u_tau = np.sqrt(np.abs(wall.tau_wall_Pa) / rho_wall)
    y_plus = rho_wall * u_tau * y_wall / wall.mu_wall_Pa_s

    # Kalıntının BİLEŞEN normları (viskoz koşuda hüküm kalıntısı kütle
    # bileşenidir — viskoz akı kütleye HİÇ girmez; momentum/enerji
    # bileşenleri geride kalıyorsa hüküm yanıltıcı olurdu, o yüzden
    # ölçülür ve yayımlanır). Ölçekler ρ₀a₀/L, ρ₀a₀²/L, ρ₀a₀³/L.
    olcek = np.array([rho0 * a0, rho0 * a0 ** 2, rho0 * a0 ** 2,
                      rho0 * a0 ** 3]) / length
    bilesen = np.sqrt(np.sum(r_final ** 2 * vol[..., None], axis=(0, 1))
                      / vol_sum) / olcek

    # ---- y⁺ DÖNGÜSÜNÜN BEYANI (§5.7: hedef / gerçekleşen / sapma) ----
    # Hedef verilmediyse ORAN da verilmez (NaN): "bilinmiyor" ASLA
    # "tutturuldu" sayılmaz. Sürücü ızgarayı kendiliğinden değiştirmediği
    # için regrid_count burada 0'dır; döngüyü koşan solve_with_y_plus_
    # target bu alanı KENDİ sayısıyla değiştirir (tek yer, tek anlam).
    hedef = None if y_plus_target is None else float(y_plus_target)
    y_max = float(np.max(y_plus))
    y_ort = float(np.mean(y_plus))
    oran = float('nan') if hedef is None else y_max / hedef
    icinde = (float('nan') if hedef is None
              else float(np.mean(y_plus <= hedef)))
    y_plus_loop = {
        'target': hedef,
        'achieved_max': y_max,
        'achieved_mean': y_ort,
        'achieved_min': float(np.min(y_plus)),
        'ratio_max_to_target': oran,
        'fraction_within_target': icinde,
        'first_cell_m_min': float(np.min(y_wall)) * 2.0,
        'first_cell_m_max': float(np.max(y_wall)) * 2.0,
        'regrid_count': 0,
        'grid_radial_distribution': (None if grid is None
                                     else grid.radial_distribution),
        'grid_radial_stretch': (None if grid is None
                                else grid.radial_stretch),
        # Duvar-normal yaka (V1b) beyanı: y⁺ ölçümünün MESAFESİ yakayla
        # değişir (H-ızgarada duvar-normal ilk hücre radyal kalınlığın
        # cos α katıydı), o yüzden yaka bu blokta da görünür.
        'grid_wall_collar': (None if grid is None
                             else getattr(grid, 'wall_collar', None)),
        '_basis': (
            'y⁺ DÖNGÜSÜ (§5.7) dürüsttür: hedef (target) çağıranın '
            'seçimidir, gerçekleşen (achieved_*) koşumun ÖLÇÜMÜDÜR '
            '(τ_w\'den; korelasyon değil), sapma ikisinin oranıdır. '
            'first_cell_m_* duvar hücresinin KALINLIĞIDIR (merkez '
            'mesafesinin iki katı — y⁺ merkezde ölçülür). Hedef '
            'verilmediyse oran NaN kalır: "bilinmiyor" tutturulmuş '
            'sayılmaz. Sürücü hedefe uymak için ızgarayı SESSİZCE '
            'değiştirmez (regrid_count = 0); yeniden ızgaralama '
            'çağıranın kararıdır ve solve_with_y_plus_target ile '
            'yapıldığında bu blok döngünün tam kaydını taşır.'),
    }

    # ---- SA (türbülans) beyanı — HİÇBİR SAYI UYDURULMAZ ----
    turbulence_block = None
    if sa is not None:
        nu_t = sa['nu_tilde']
        mu_t = sa['mu_t']
        mu_lam = viscous.transport.viscosity(w[..., 3] / (Rs * w[..., 0]))
        sa_dec = None if sa['aux'] is None else sa['aux']['declaration']
        turbulence_block = {
            'model': TURBULENCE_SA_NEG,
            'nu_tilde_freestream_m2_s': sa['nu_tilde_inf'],
            'freestream_basis': sa['freestream_basis'],
            'nu_tilde_max_m2_s': float(np.max(nu_t)),
            'nu_tilde_min_m2_s': float(np.min(nu_t)),
            'negative_cell_count': int(np.count_nonzero(nu_t < 0.0)),
            'mu_t_over_mu_max': float(np.max(mu_t / mu_lam)),
            'mu_t_over_mu_wall_max': float(np.max(mu_t[:, -1]
                                                  / mu_lam[:, -1])),
            'mu_t_max_Pa_s': float(np.max(mu_t)),
            'wall_distance_min_m': float(np.min(sa['d'])),
            'wall_distance_max_m': float(np.max(sa['d'])),
            'sa_residual_scaled': sa['residual_norm'],
            'sa_residual_history': np.asarray(sa['residual_history']),
            'sa_steps': int(sa['steps']),
            'source_jacobian_basis': (
                'Nokta-örtük köşegen, sa_neg.sa_source_terms\'ün '
                'yayımladığı TAM ANALİTİK kaynak Jacobian\'ının negatif '
                'kısmıdır (üretim türevi dahil, donmuş katsayı yok — V3). '
                'Parti 38\'in ileri-fark vekili ve source_jacobian_ratio_'
                'max alanı SÖKÜLDÜ: sökme öncesi ölçülen oran levhada '
                '6,51 → 1,0008, lüle ikizinde 5,51 → 1,0025 '
                '(yayımlanan köşegen artık gerçeği taşıyor; FD çaprazı '
                'bekçisi tests/cfd/test_sa_neg.py).'),
            'convection_scheme': viscous.sa_scheme,
            'density_correction_term': bool(viscous.sa_density_correction),
            'constants': sa_constants(),
            'citations': dict(SA_CITATIONS),
            'not_modelled': dict(SA_NOT_MODELLED),
            'declaration': sa_dec,
            '_basis': (
                'SA-neg AYRIK (segregated) çözüldü (§5.5): ortalama akış '
                '4×4 blok üç-köşegen ilerlerken ν̃ AYNI j-satırlarında '
                'SKALER (m=1) üç-köşegen çözülür — cebir çekirdeği '
                'implicit.solve_block_tridiag, ikinci gerçekleme yok. '
                'Kapanış μ_t = ρν̃·f_v1(χ) ile viskoz akıya taşınır '
                '(μ_eff = μ + μ_t, k_eff = cp(μ/Pr + μ_t/Pr_t)); duvarda '
                'ν̃ = 0 olduğu için μ_t duvar yüzünde TAM SIFIRDIR ve y⁺ '
                'ile q_w LAMİNER μ_w ile ölçülür. Ω viskoz kalıntının '
                'KULLANDIĞI hız gradyanlarından gelir (ikinci gradyan '
                'tanımı yok). sa_residual_scaled, ρν̃ denkleminin '
                'ρ₀a₀ν̃_∞/L ile boyutsuzlaştırılmış L2 normudur ve HÜKME '
                'GİRMEZ: hüküm üçlüsü (debi/boğaz Mach/kalıntı) '
                'değiştirilmemiştir — SA yakınsaması buradan OKUNUR.'),
        }

    return {
        'turbulence': turbulence_block,
        'grid_quality': (None if grid is None else
                         wall_grid_quality(grid, geom, grad_geom,
                                           throat_index=throat_index)),
        'wall_z_m': wall.z_m, 'wall_r_m': wall.r_m,
        'wall_area_m2': wall.area_m2,
        'wall_shear_Pa': wall.tau_wall_Pa,
        'wall_heat_flux_W_m2': wall.q_wall_W_m2,
        'wall_temperature_K': wall.T_wall_K,
        'wall_cell_temperature_K': wall.T_cell_K,
        'wall_first_cell_m': y_wall,
        'wall_y_plus': y_plus,
        'wall_y_plus_max': y_max,
        'y_plus_loop': y_plus_loop,
        'grid_stretch': (None if grid is None else grid.radial_stretch),
        'grid_wall_collar': (None if grid is None
                             else getattr(grid, 'wall_collar', None)),
        'wall_heat_W': aux_visc['wall_heat_W'],
        'axial_friction_force_on_fluid_N':
            aux_visc['axial_friction_force_on_fluid_N'],
        # --- SINIR AKILARI (basamak 14, parti 40) --------------------------
        # viscous_residual bunları ZATEN ölçüyordu (aux) ama yayımlanmıyordu;
        # taşınmadıkları için viskoz enerji bütçesi ancak İKİNCİ bir kalıntı
        # çağrısıyla kurulabiliyordu. Diziler kopya DEĞİL, o çağrının kendi
        # sayılarıdır. İşaret: akının KENDİSİ (+i yönünde), alan kazancı
        # çıkış eksi giriş biçiminde kurulur (viscous.py sözleşmesi).
        'inlet_viscous_energy_flux_W': aux_visc['inlet_energy_flux_W'],
        'outlet_viscous_energy_flux_W': aux_visc['outlet_energy_flux_W'],
        'inlet_viscous_axial_force_N': aux_visc['inlet_axial_force_N'],
        'outlet_viscous_axial_force_N': aux_visc['outlet_axial_force_N'],
        # --- DUVAR YÜZÜ BİRİM NORMALLERİ ----------------------------------
        # geom['wall_n_hat'] KOŞUMUN KENDİ dizisidir (euler_core.
        # precompute_geometry, grid.face_j[:, -1]'den); burada yeniden
        # hesaplanmaz, dilimlenir. Yayımlanma sebebi ölçüldü: sürtünme
        # kuvvetinin İKİ tanımı (tam çekiş ↔ salt kayma) duvar normalinin
        # radyal bileşenini ister ve o bugüne dek yalnız IZGARADAN
        # okunabiliyordu — kaydedilmiş bir sonuçtan (JSON) hesaplanamıyordu.
        # SINIR (dürüstlük): bu iki alan kuvvet TANIMLARINI ızgarasız
        # kılar; kayıp KESRİNİN paydası (çıkış düzleminin momentum akısı)
        # hâlâ grid.face_i[-1] ister ve BU PARTİDE ızgarasız YAPILMADI.
        'wall_normal_z': n_w[..., 0].copy(),
        'wall_normal_r': n_w[..., 1].copy(),
        'residual_components_scaled': bilesen,
        'thermal_mode': wall.thermal_mode,
        'T_wall_source': wall.T_wall_source,
        'c_visc': float(viscous.c_visc),
        'declaration': aux_visc['declaration'],
        '_basis': (
            'Viskoz katman KOMPOZİSYONLA eklendi (tasarım §5.1): '
            'R = R_Euler + R_viskoz; Euler yolu viskoz kapalıyken '
            'bit-özdeştir (tests/cfd/test_euler_bit_ozdesligi.py). y⁺ '
            'duvar kayma gerilmesinden ÖLÇÜLDÜ: u_τ = √(|τ_w|/ρ_w), '
            'y = ilk hücre merkezinin duvar-normal mesafesi, ρ_w komşu '
            'hücre basıncı + duvar sıcaklığından. residual_components_'
            'scaled hüküm kalıntısının (kütle) yanında momentum/enerji '
            'bileşenlerini de yayımlar — viskoz akı kütleye girmediği '
            'için tek bileşenli hüküm yanıltıcı olabilir. '
            'inlet/outlet_viscous_* dörtlüsü giriş ve çıkış YÜZLERİNDEN '
            'geçen viskoz akılardır (viscous_residual\'ın kendi ölçümü, '
            'kopya değil): üst düzeydeki viscous_energy_balance_rel bu '
            'dördün ikisiyle + wall_heat_W ile kurulur. wall_normal_z/_r '
            'duvar yüzünün BİRİM normalidir (ızgaranın 2π\'li yüz '
            'vektöründen; koşumun kendi geom dizisi) ve sürtünme '
            'kuvvetinin iki tanımını kaydedilmiş bir sonuçtan '
            'hesaplanabilir kılar.'),
    }
