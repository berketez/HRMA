"""3.0.7 ÇALKANTI-6DOF bağlama (KARTLAR K2; CALKANTI_6DOF_TASARIM.md §B, §C).

Tank başına yunuslama ve sapma düzleminde birinci mod çalkantı durumu
(η_k ∈ ℝ², η̇_k ∈ ℝ²) 6-DOF rijit gövde denklemlerine bağlanır. Model
"kızakta yay-kütle"dir (§B.2): çalkantı kütlesi m1 kendi istasyonunda
eksenel bir kızak üstünde yanal hareket eder, yay sabiti her an uçuşun
eksenel özgül kuvvetinden kurulur (ω1² = f_x/L1 = κ1 f_x; Dodge 2000 Denk.
(1.40), Tablo 3.2; sarkaç eşdeğerliği Green 2024 Tablo 5-1, 5-2, 5-4).

Denklemler (bileşik nominal KM O'ya göre; §B.3.2):
  (B-1) m â − [S]× ω̇ + Σ m1 E η̈ = Cᵀ F_dış − ω×(ω×S) − 2 Σ m1 ω×(E η̇)
  (B-2) [S]× â + I_O ω̇ + Σ m1 [ρ]× E η̈ = M_O − ω×(I_O ω)
                                         − 2 Σ m1 ρ×(ω×E η̇) + S×(Cᵀ g)
  (B-3) Eᵀ â − Eᵀ[ρ]× ω̇ + η̈ = Eᵀ Cᵀ g − Eᵀ[ω×(ω×ρ) + 2 ω×E η̇]
                                − ω1² η − 2 ζ ω1 η̇
Çözüm PERTÜRBASYON biçimindedir (§B.3.4): bugünkü rijit çözüm x0 = (â0, ω̇0)
aynen hesaplanır, düzeltme Δx = (A0 + A1)⁻¹ (r1 − A1 x0); A1 ve r1'in her
terimi m1 ile orantılıdır, m1 = 0'da Δx = 0 TAM OLARAK (gövde türevleri
bugünküyle bit düzeyinde aynı; §C-b).

Kararlılık (§B.5): dört anda (kalkış, ray çıkışı, yanma içindeki en büyük q̄,
yanma sonu) dondurulmuş katsayılı yunuslama düzlemi modeli
  (B-5) −m u α̇ − m u̇ α + m u q + Σ m1 η̈ = N_α α
  (B-6) I q̇ + Σ m1 ξ η̈ = M_α α + M_q q + Σ m1 f_x η
  (B-7) −u α̇ − u̇ α + u q + ξ q̇ + η̈ + 2ζω1 η̇ + ω1² η = 0
özdeğerleri, mod tanımı, Hurwitz çapraz denetimi (SP-106 Denk. (7.32)–(7.35)),
gereken en küçük ortak çalkantı sönümü ζ_min ve tek durumlu hüküm.

3.0.7 V307/ÇALKANTI-KARARLILIK (karar 16 Kas): dört an raporlama içindir;
GENEL hüküm yanma boyunca taramadan verilir (``yanma_taramasi``): aynı
donmuş model bağlaşık çözümün HER yanma içi örneğinde çözülür, ardışık
kararsız örnekler PENCERE olur (kenarı ikiye bölmeyle inceltilir), her
pencere için en büyük Re(λ), mod, yakınlık oranı, ζ_min (pencerenin bütün
örneklerinde doğrulanmış) ve büyüme üssü ∫Re dt yayımlanır. Dört an bu
pencereleri kaçırabiliyordu (örnek sıvı araçta pencere 4,3–21,9 s, en büyük
q 22,2 s). Kararsızlık modelin denklemlerinde doğrudur: aerodinamik normal
kuvvet tutumu izleyen bir yanal kuvvettir ve sarkaçla dolaşımlı bağlaşım
kurar (Bauer, SP-106 Bölüm 7, tehlike bölgesi / frekans birleşmesi;
sınamalar ``tests/test_six_dof_slosh_tarama.py`` ve RAPOR). Ayrıca: zaman
alanı genliğinin doğrusal kuram sınırını aşması adıyla işaretlenir
(``dogrusal_sinir_ozeti``), pencereleri kapatan halka bafl dizisi önerilir
ve öneriyle tarama yinelenir (``bafl_dizisi_onerisi``), tank sıvı yoğunluğu
zaman serisi olarak verilebilir (``rho_t``).

Kapsam dışı (karar 56): kontrol döngüsü (TVC/otopilot), esnek gövde, doğrusal
olmayan büyük genlik, dönen çalkantı, f_x ≤ 0 rejimi (SP-8009 §2.5).
Tankın etkin ataleti I0 uygulanmaz: sıvının bugünkü (donmuş) atalet modeli
korunur (§B.3.1, §E açık soru 2) — beyan kodu ``I0_UYGULANMADI``.

Bu modül ``six_dof_trajectory``'yi YALNIZ işlev içinde (geç) içe aktarır;
``six_dof_trajectory`` bu modülü üst düzeyde içe aktarır (döngü yok).
"""

from __future__ import annotations

import copy
import inspect
import math
import numbers

import numpy as np

from hrma.analysis import slosh_analysis as _sa
from hrma.analysis import slosh_tablo as _tablo
# NumPy 2 köprüsü (tek kaynak, ÖH D26 · OH-D25-14): ``np.trapz`` adı ürün
# kodunda yazılmaz; NumPy 1.x altında bu ad ``np.trapz``ın kendisidir.
from hrma.utils.numeric_compat import trapezoid as _trapezoid

# ---------------------------------------------------------------------------
# Sabitler — TEK TANIM YERİ. Kaynaklı olmayanlar "HRMA seçimi" diye beyanlı
# (CALKANTI §E açık soru 4; onay ya da değişiklik ana model/Berke kararı).
# ---------------------------------------------------------------------------
#: Rayda sıvının statik eğimi β = atan(|Eᵀ f_O|/f_x) için geçerlilik sınırı
#: [°] (§B.3.5). HRMA seçimi: küçük açı yaklaşımında sin β ≈ β hatası 15°'de
#: %1,2; eşik kuramın %1 mertebesinde kaldığı sınırdır. Aşılırsa çalkantı
#: itki ekseninde denge konumundan (η = 0) başlatılır ve beyan düşülür.
RAY_STATIK_EGIM_SINIRI_DEG = 15.0

#: Yarı-durağanlık göstergesi eşiği (§B.3.7). HRMA seçimi: |d ln m1/dt|/ω1
#: ya da |d ln L1/dt|/ω1 bu değeri aşan zaman aralığı işaretlenir
#: (parametreler bir çalkantı periyodunun ~1/60'ında %10'dan az değişmeli).
YARI_DURAGANLIK_ESIGI = 0.1

#: Dondurulmuş katsayı analizinin geçerlilik ölçütü ω_g·τ_q ≥ 2π (§B.5).
#: ω_g = √(|M_α|/I) aerodinamik yay frekansı, τ_q = q̄/|dq̄/dt|. HRMA seçimi
#: (q̄ bir salınım periyodu içinde e kat değişmemeli; dondurulmuş katsayı
#: analizinin standart ön koşulu, sayısal eşik kaynaklı değil).
DONDURULMUS_KATSAYI_ESIGI = 2.0 * math.pi

#: ζ_min aramasının üst sınırı ve ikiye bölme adım sayısı (§B.5). HRMA
#: seçimi: 0,5'in üstündeki sönüm tek bafl ile sağlanamaz; 50 adım
#: 0,5·2⁻⁵⁰ çözünürlük verir.
ZETA_MIN_UST = 0.5
ZETA_MIN_BOLME_ADIMI = 50

#: Kullanıcı/motor tarafından verilen ek sönüm oranının (bafl vb.) kabul
#: aralığı [0, 1). HRMA seçimi: doğrusal eşdeğer model alt-kritik sönümlü
#: salınıcıdır; ζ ≥ 1 salınımsız (aperiyodik) olur ve modelin dışıdır.
EK_SONUM_UST = 1.0

#: Kütle serisi (m_t) en çok nokta sayısı — saldırgan girdiye boyut sınırı
#: (HRMA seçimi; `slosh_tablo.PROFIL_NOKTA_SINIRI` ile aynı mertebe).
KUTLE_SERISI_NOKTA_SINIRI = _tablo.PROFIL_NOKTA_SINIRI

#: Frekans yakınlık bandı (§B.5): yeni sayı icat edilmez, çalkantı
#: analizinin TEK tanım yerinden (``CylindricalTankSlosh.analyze`` imzasındaki
#: ``coincidence_margin`` varsayılanı; üst sınır ``COINCIDENCE_MARGIN_MAX``)
#: okunur. DEVİR (K1): varsayılan adlı bir sabite taşınmalı.
YAKINLIK_BANDI = float(inspect.signature(
    _sa.CylindricalTankSlosh.analyze).parameters['coincidence_margin'].default)
assert 0.0 < YAKINLIK_BANDI <= _sa.COINCIDENCE_MARGIN_MAX

#: Yanma sonu anı t_burn − ε: ε, t_burn'den küçük en yakın kayan nokta
#: sayısına (``np.nextafter``) gidilerek alınır; itki ve çalkantı açık kalır.

# --- Yanma boyunca tarama (3.0.7, V307/ÇALKANTI-KARARLILIK) ----------------
#: Pencere kenarı inceltmesinin zaman toleransı [s]. HRMA seçimi (sayısal
#: çözünürlük): tarama çözümün KENDİ örneklerinde yapılır; kararlı ⟷ kararsız
#: geçişi iki komşu örnek arasında, durum doğrusal aradeğerlenerek ikiye
#: bölmeyle bu toleransa indirilir (örnek aralığı ~0,02 s, tolerans 1 ms).
TARAMA_KENAR_TOL_S = 1.0e-3

#: Taramada "kararsız" sayılma eşiği: max Re(λ) > eşik · max|λ|. HRMA seçimi
#: (sayısal çözünürlük, fizik değil): sönümsüz (ζ = 0) bir tankta nötr kök
#: yuvarlamayla ±10⁻¹³ mertebesinde gerçel kısım alır; eşik bu gürültünün
#: dört basamak üstündedir ve hiçbir fiziksel büyüme hızını gizlemez
#: (20 rad/s'de 2·10⁻⁸ 1/s; e-katlanma süresi 1,6 yıl).
TARAMA_RE_ESIGI_BAGIL = 1.0e-9

#: Pencerenin ζ_min'i: önce pencerenin eşit aralıklı bu kadar örneğinde (ve
#: en büyük Re örneğinde) ζ_min hesaplanır, sonra pencerenin BÜTÜN örnekleri
#: bu sönümle denetlenir; ihlal eden örnek varsa onun ζ_min'i alınır ve
#: denetim yinelenir (en çok tur sayısı kadar). HRMA seçimi (yalnız maliyet;
#: sonuç bütün örneklerde doğrulanmış değerdir).
ZETA_PENCERE_ALT_ORNEK = 24
ZETA_PENCERE_DOGRULAMA_TURU = 12

#: Doğrusal kuram genlik sınırının künyesi (sınırın kendisi
#: ``slosh_tablo.GENLIK_DOGRUSAL_SINIR_ORANI``; tek tanım yeri).
DOGRUSAL_SINIR_KAYNAGI = (
    'Dodge 2000 (SwRI, "The New Dynamic Behavior of Liquids in Moving '
    'Containers") p. 33: the wave departs markedly from linear behaviour '
    'once its amplitude exceeds about 10 % of the tank diameter; 0.2 R is '
    'the largest reasonable design amplitude.')
#: Sınır aşıldıktan sonraki sayıların işareti (kod; TR/EN metni K5).
DOGRUSAL_GECERLILIK_DISI = 'DOGRUSAL_MODEL_GECERLILIGI_DISINDA'
#: Sınır aşımından etkilenen çıktı alanları (aşımdan SONRAKİ örnekler).
DOGRUSAL_SINIRDAN_ETKILENEN = (
    'slosh_eta', 'slosh_angle_deg', 'slosh_wall_amplitude_ratio',
    'slosh_force_body', 'slosh_moment_body', 'slosh_rigid_comparison',
    'apogee', 'max_alpha_deg', 'alpha_deg', 'flight_verdict')

#: Gövde çerçevesinde yanal izdüşüm E = [e_y e_z] (3×2).
E = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])

#: Kapsam dışı künyesi (§1, §B.6) — kod; TR/EN metni arayüz sözlüğündedir
#: (K5). API alanı ``kapsam_disi`` bu kodu ve İngilizce gerekçeyi taşır.
KAPSAM_DISI_KODU = 'KONTROL_DONGUSU_MODELLENMEDI'
KAPSAM_DISI_GEREKCE = (
    'Control loop not modelled; for a guided vehicle this coupling is the '
    'main risk, and the hand-off table is meant for the vehicle team\'s GNC '
    'tool.')

# ---------------------------------------------------------------------------
# Makine-okur kodlar (K2). Sınıf: KAPANMA (o anda tankın çalkantısı kapalı,
# m1 = 0), BAGLANMADI (tank hiç bağlanmadı), BEYAN (bağlı, varsayım beyanlı).
# Tablo kodları (slosh_tablo.SEBEP_KODLARI) aynen taşınır.
# ---------------------------------------------------------------------------
SINIF_KAPANMA = 'KAPANMA'
SINIF_BAGLANMADI = 'BAGLANMADI'
SINIF_BEYAN = 'BEYAN'
K2_KODLARI = {
    'TANK_KUTLESI_VERILMEDI': (
        SINIF_BAGLANMADI, 'tank sıvı kütlesi (m_t) verilmedi; yüklenen kütle '
        'bilinmeden doluluk kurulamaz, tank bağlanmadı'),
    'TANK_TUKETIMI_ITKIYLE_ORANTILI': (
        SINIF_BEYAN, 'tank tüketimi itkiyle orantılı varsayıldı (O/F sabit); '
        'yalnız yüklenen kütle verildi (CALKANTI §A.2)'),
    'TANK_KUTLE_SERISI_DISI': (
        SINIF_KAPANMA, 'zaman, verilen tank kütle serisinin sonundan sonra; '
        'dışdeğerleme yapılmaz'),
    'FX_POZITIF_DEGIL': (
        SINIF_KAPANMA, 'eksenel özgül kuvvet f_x ≤ 0; sarkaç geri getirici '
        'kuvveti yok (SP-8009 §2.5 kapsam dışı, CALKANTI §B.3.6)'),
    'YANMA_BITTI': (
        SINIF_KAPANMA, 'yanma sonrası çalkantı modellenmedi; kalan sıvı rijit '
        'kabul edildi (CALKANTI §B.3.6)'),
    'SATIR_RET': (
        SINIF_KAPANMA, 'eşdeğer model tablosu bu dolulukta RET (sebep tablo '
        'kodlarında)'),
    'RAY_STATIK_EGIM_SINIR_DISI': (
        SINIF_BEYAN, 'ray üstünde sıvı statik eğimi doğrusal sınırı aşıyor; '
        'çalkantı itki ekseninde denge konumundan başlatıldı (§B.3.5)'),
    'CEPER_SONUMU_HESAPLANAMADI': (
        SINIF_BEYAN, 'düz çeper viskoz sönümü hesaplanamadı (ν yok ya da tank '
        'düz tabanlı dik silindir değil); çeper sönümü 0 alındı (tutucu)'),
    'I0_UYGULANMADI': (
        SINIF_BEYAN, 'sıvının etkin ataleti I0 uygulanmadı; bugünkü donmuş '
        'atalet modeli korundu (CALKANTI §B.3.1, §E-2)'),
    'YARI_DURAGAN_DEGIL': (
        SINIF_BEYAN, 'parametre değişimi hızlı: |d ln m1/dt|/ω1 ya da '
        '|d ln L1/dt|/ω1 > 0,1 (§B.3.7)'),
    'SONUM_TOPLANABILIRLIGI': (
        SINIF_BEYAN, 'çeper ve ek (bafl) sönümü toplandı; toplanabilirlik '
        'SP-8009 §4.5\'e göre kesin doğrulanmadı'),
    # --- 3.0.7 V307/ÇALKANTI-KARARLILIK --------------------------------
    'TANK_YOGUNLUK_SERISI_DISI': (
        SINIF_KAPANMA, 'zaman, verilen sıvı yoğunluğu serisinin sonundan '
        'sonra; dışdeğerleme yapılmaz'),
    'TANK_YOGUNLUGU_SERIDEN': (
        SINIF_BEYAN, 'sıvı yoğunluğu verilen zaman serisinden alındı; '
        'doluluk = m(t)/(ρ(t)·V_iç)'),
    'TARAMA_KISMI_KAPSAM': (
        SINIF_BEYAN, 'yanma süresinin bir kısmında donmuş katsayılı hüküm '
        'verilemedi (rayda, donmuş katsayı ölçütü sağlanmıyor ya da çalkantı '
        'kapalı); aralıklar ve sebepleri tarama kapsamında'),
    'ZETA_MIN_DOGRULANAMADI': (
        SINIF_BEYAN, 'pencerenin ζ_min değeri bütün örneklerde '
        'doğrulanamadı (ortak sönümle kararlılık tekdüze değil)'),
    'DONMUS_MODELDE_YERCEKIMI_KINEMATIGI_YOK': (
        SINIF_BEYAN, 'donmuş katsayılı model uçuş yolunun yerçekimiyle '
        'dönmesini içermez (CALKANTI §B.3.2); bağımsız doğrusal olmayan '
        'benzetimle ölçülen etkisi |ΔRe| ≤ 0,012 1/s (üç örnek vaka, altı '
        'nokta; kararsız noktalarda donmuş model büyüme hızını FAZLA verir)'),
    # --- 3.0.7 ONARIM-ÇALK (M7-CALK-15) ----------------------------------
    'HUKUM_YALNIZ_BAGLANAN_TANKLAR': (
        SINIF_BEYAN, 'en az bir tank 6-DOF\'a bağlanmadı; hüküm yalnız bağlanan '
        'tankları kapsar, bağlanmayan tankın modu modelde yoktur '
        '(KARARLI hükmü verilmez)'),
}

# Tarama örneği sınıfları (her çözüm örneği tek sınıf alır).
TARAMA_KARARLI = 'KARARLI'
TARAMA_CALKANTI_KARARSIZ = 'CALKANTI_KARARSIZ'
TARAMA_RIJIT_KARARSIZ = 'RIJIT_KARARSIZ'
TARAMA_GECERSIZ = 'DONDURULMUS_KATSAYI_GECERSIZ'
TARAMA_KAPALI = 'CALKANTI_KAPALI'
TARAMA_RAYDA = 'RAYDA'
TARAMA_SINIFLARI = (TARAMA_KARARLI, TARAMA_CALKANTI_KARARSIZ,
                    TARAMA_RIJIT_KARARSIZ, TARAMA_GECERSIZ, TARAMA_KAPALI,
                    TARAMA_RAYDA)
#: Pencere kenarının türü: gerçek kararlı ⟷ kararsız geçişi (ikiye bölmeyle
#: inceltilmiş) ya da hüküm verilebilen bölgenin sınırı (komşu örnek
#: değerlendirilemiyor; kenar o örneğin anıdır).
KENAR_ISARET_DEGISIMI = 'ISARET_DEGISIMI'
KENAR_DEGERLENDIRME_SINIRI = 'DEGERLENDIRME_SINIRI'

#: Genel hükmün gerekçe kodları (tek kod; hükümle birlikte okunur).
GEREKCE_PENCERE = 'YANMA_ICI_CALKANTI_KARARSIZLIK_PENCERESI'
GEREKCE_RIJIT = 'YANMA_ICI_RIJIT_GOVDE_KARARSIZ'
GEREKCE_KARARLI = 'TARAMADA_KARARSIZLIK_YOK'
GEREKCE_DEGERLENDIRILEMEDI = 'TARAMA_DEGERLENDIRILEMEDI'
#: V307/UÇUŞ-GÖVDE (kalem 5): hükmü taşıyan bütün pencereler doğrusal sınırın
#: ilk aşımından SONRAKİ örneklerden geliyorsa (o örneklerin uçuş durumu
#: geçerlilik dışı koşudandır) gerekçe kodu bunu söyler.
GEREKCE_PENCERE_SINIR_SONRASI = 'YANMA_ICI_PENCERE_YALNIZ_SINIR_ASIMINDAN_SONRA'
#: 3.0.7 ONARIM-ÇALK (M7-CALK-15) — kısmi bağlama: bağlanmayan tank varken
#: KARARLI hükmünün yerine geçen gerekçe ve sebep kodu. Tarama yalnız bağlanan
#: tankları kapsar; bağlanmayan tankın modu modelde yoktur (ölçüldü: örnek sıvı
#: motorda kararsızlığı yapan mod tam da oksitleyici tankınınki), o yüzden
#: "kararlı" denemez. Beyan kodu bağlanmayan tank varken her hükmün yanında
#: taşınır (:func:`kismi_baglama_hukmu`).
GEREKCE_KISMI_BAGLAMA = 'BAGLANMAYAN_TANK_VAR'
SEBEP_KISMI_BAGLAMA = 'TANK_KISMEN_BAGLANMADI'
BEYAN_KISMI_BAGLAMA = 'HUKUM_YALNIZ_BAGLANAN_TANKLAR'
GEREKCE_KODLARI = (
    GEREKCE_PENCERE, GEREKCE_PENCERE_SINIR_SONRASI, GEREKCE_RIJIT,
    GEREKCE_KARARLI, GEREKCE_DEGERLENDIRILEMEDI, 'SAYISAL_TUTARSIZLIK',
    'COZUM_YAKINSAMADI', 'UCUS_APOJEYE_VARMADI', 'TANK_YOK', 'TANK_BAGLANMADI',
    GEREKCE_KISMI_BAGLAMA)

#: Pencerenin doğrusal sınırın ilk aşımına göre yeri (``pencereler[i].
#: sinir_asimi_konumu``). ``SONRA``: pencerenin bütün örnekleri ilk aşımdan
#: sonradır; ``KAPSIYOR``: pencere aşımdan önce başlar, sonra da sürer.
SINIR_KONUM_ASILMADI = 'SINIR_ASILMADI'
SINIR_KONUM_ONCE = 'ASIMDAN_ONCE'
SINIR_KONUM_KAPSIYOR = 'ASIMI_KAPSIYOR'
SINIR_KONUM_SONRA = 'ASIMDAN_SONRA'
SINIR_KONUMLARI = (SINIR_KONUM_ASILMADI, SINIR_KONUM_ONCE,
                   SINIR_KONUM_KAPSIYOR, SINIR_KONUM_SONRA)

#: Hükmün kapsam künyesi (çıktıda ``hukum_kapsami``): hüküm doğrusal
#: taramanın bulgusudur, uçuşun neden sona erdiğinin açıklaması değildir;
#: büyüme üssü donmuş katsayılı yaklaşık modal büyüme üssüdür.
HUKUM_KAPSAMI_KODU = 'DOGRUSAL_TARAMA_BULGUSU'
HUKUM_KAPSAMI_GEREKCE = (
    'The verdict is the finding of the frozen-coefficient linear scan over '
    'the burn. It does not say why the flight ended: a window found by the '
    'scan is not a statement that slosh caused a tumble or a ground impact. '
    'The growth exponent of a window is the frozen-coefficient approximate '
    'modal growth exponent (the time integral of the largest Re(lambda)); '
    'for a system whose coefficients change in time it is not a guaranteed '
    'amplitude gain, and the absence of a window is not by itself a proof '
    'of stability.')

# Hüküm kodları (tek durumlu; §B.5 hüküm kuralları).
HUKUM_UYGULANMAZ = 'UYGULANMAZ'
HUKUM_YOK = 'HUKUM_YOK'
HUKUM_RIJIT_KARARSIZ = 'RIJIT_GOVDE_KARARSIZ'
HUKUM_CALKANTI_KARARSIZ = 'CALKANTI_KAYNAKLI_KARARSIZLIK'
HUKUM_KARARLI = 'KARARLI'
HUKUMLER = (HUKUM_UYGULANMAZ, HUKUM_YOK, HUKUM_RIJIT_KARARSIZ,
            HUKUM_CALKANTI_KARARSIZ, HUKUM_KARARLI)

#: Hüküm sebep kodları (yalnız HUKUM_YOK / UYGULANMAZ ile).
HUKUM_SEBEPLERI = (
    'TANK_YOK', 'TANK_BAGLANMADI', 'COZUM_YAKINSAMADI', 'UCUS_APOJEYE_VARMADI',
    'AN_ULASILMADI', 'KALKIS_ANI_ALFA_TANIMSIZ', 'CALKANTI_KAPALI',
    'DONDURULMUS_KATSAYI_GECERSIZ', 'SAYISAL_TUTARSIZLIK',
    SEBEP_KISMI_BAGLAMA)

ANLAR = ('kalkis', 'ray_cikisi', 'en_buyuk_q', 'yanma_sonu')

_TANK_ALANLARI = ('tank_id', 'x_tank_taban_m', 'tablo', 'm_t', 'zeta_ek')
#: İsteğe bağlı tank alanları (3.0.7 V307/ÇALKANTI-KARARLILIK): ``rho_t`` sıvı
#: yoğunluğu zaman serisi ``{"t": [...], "rho": [...]}`` [s], [kg/m³].
_TANK_SECMELI_ALANLAR = ('rho_t',)


class SloshBaglamaHatasi(ValueError):
    """Çalkantı bağlama girdisi reddedildi — ``kod`` ve ``alan`` adlı."""

    def __init__(self, mesaj, kod, alan=None):
        super().__init__(mesaj)
        self.kod = kod
        self.alan = alan


def _ret(kod, alan, mesaj):
    raise SloshBaglamaHatasi(f'{alan}: {mesaj}', kod, alan)


def _sonlu(deger, alan):
    if isinstance(deger, (bool, np.bool_)) or not isinstance(
            deger, numbers.Real) or not math.isfinite(float(deger)):
        _ret('SAYI_DEGIL', alan, f'sonlu bir sayı olmalı ({deger!r})')
    return float(deger)


def _capraz(a):
    """[a]× çapraz çarpım matrisi."""
    return np.array([[0.0, -a[2], a[1]],
                     [a[2], 0.0, -a[0]],
                     [-a[1], a[0], 0.0]])


# ---------------------------------------------------------------------------
# Girdi normalleştirme
# ---------------------------------------------------------------------------
class SloshBaglama:
    """Doğrulanmış tank listesi + RHS parçaları (``SixDOFTrajectory`` sahibi).

    ``slosh_tanks`` sözleşmesi (KARTLAR K2, K4 ile sabit):
    ``[{"tank_id", "x_tank_taban_m", "tablo": SloshTablo,
        "m_t": {"t": [...], "m": [...]} | None, "zeta_ek": float | None}]``

    - ``m_t``: tankın sıvı kütlesi zaman serisi [s], [kg]. Tek noktalı seri
      ``{"t": [t0], "m": [m0]}`` yalnız yüklenen kütleyi verir; tüketim
      itkiyle orantılı türetilir (BEYANLI ``TANK_TUKETIMI_ITKIYLE_ORANTILI``).
      ``None``: yüklenen kütle bilinmiyor → tank BAĞLANMAZ
      (``TANK_KUTLESI_VERILMEDI``; uydurma kütle yok). Tasarım düzeltmesi:
      KARTLAR'daki "None ise impulsla orantılı türetilir" m_k,0 olmadan
      uygulanamaz (CALKANTI §B.1 notu).
    - ``zeta_ek``: çeper sönümüne eklenen sönüm oranı (bafl), [0, 1).
    - ``rho_t`` (isteğe bağlı; 3.0.7 V307/ÇALKANTI-KARARLILIK): sıvı yoğunluğu
      zaman serisi ``{"t": [...], "rho": [...]}`` [s], [kg/m³]. Verilirse
      doluluk = m(t)/(ρ(t)·V_iç) (kendinden basınçlı N₂O tankında sıvı
      soğudukça yoğunlaşır); verilmezse tablonun sıvı yoğunluğu sabit
      kullanılır. İlk noktadan önce ilk değer; son noktadan sonra
      dışdeğerleme yok (``TANK_YOGUNLUK_SERISI_DISI``, kapanma). Çalkantı
      kütlesi m1 = (m1/m_sıvı)(doluluk)·m(t) kütleden kurulur; yoğunluk
      yalnız doluluğu (ve Bond sayısını) değiştirir.
    """

    def __init__(self, slosh_tanks, cozucu):
        if not isinstance(slosh_tanks, (list, tuple)):
            _ret('TIP', 'slosh_tanks', 'liste olmalı')
        if len(slosh_tanks) > len(_tablo.TANK_KIMLIKLERI):
            _ret('TANK_SAYISI', 'slosh_tanks',
                 f'en çok {len(_tablo.TANK_KIMLIKLERI)} tank')
        self.t_burn = float(cozucu.t_burn)
        self.m_prop = float(cozucu.m_prop)
        L = float(cozucu.aero.L)
        tanklar, kimlikler = [], set()
        self.baglanmayan = []
        for i, g in enumerate(slosh_tanks):
            alan = f'slosh_tanks[{i}]'
            if not isinstance(g, dict):
                _ret('TIP', alan, 'sözlük olmalı')
            bilinmeyen = set(g) - set(_TANK_ALANLARI) - set(
                _TANK_SECMELI_ALANLAR)
            eksik = set(_TANK_ALANLARI) - set(g)
            if bilinmeyen:
                _ret('ALAN_BILINMEYEN', alan, f'bilinmeyen alan {sorted(bilinmeyen)}')
            if eksik:
                _ret('ALAN_EKSIK', alan, f'eksik alan {sorted(eksik)}')
            tid = g['tank_id']
            if tid not in _tablo.TANK_KIMLIKLERI:
                _ret('TANK_KIMLIGI', alan + '.tank_id', f'{tid!r} tanınmıyor')
            if tid in kimlikler:
                _ret('TANK_KIMLIGI_TEKRAR', alan + '.tank_id', f'{tid!r} iki kez')
            kimlikler.add(tid)
            tablo = g['tablo']
            if not isinstance(tablo, _tablo.SloshTablo):
                _ret('TIP', alan + '.tablo', 'slosh_tablo.SloshTablo olmalı')
            if tablo.tank_id != tid:
                _ret('TANK_KIMLIGI_TABLO', alan + '.tablo',
                     f'tablo {tablo.tank_id!r}, tank {tid!r}')
            geo, sivi = tablo.geometri, tablo.sivi
            x_taban = _sonlu(g['x_tank_taban_m'], alan + '.x_tank_taban_m')
            # Tank araç boyunun içinde olmalı: taban (kıç) ≤ L, tepe ≥ 0.
            if not (x_taban <= L and x_taban - geo['H_ic_m'] >= 0.0):
                _ret('TANK_KONUMU_ARAC_DISI', alan + '.x_tank_taban_m',
                     f'tank [{x_taban - geo["H_ic_m"]:g}, {x_taban:g}] m '
                     f'araç boyu [0, {L:g}] m dışında')
            zeta_ek = g['zeta_ek']
            if zeta_ek is not None:
                zeta_ek = _sonlu(zeta_ek, alan + '.zeta_ek')
                if not (0.0 <= zeta_ek < EK_SONUM_UST):
                    _ret('ARALIK', alan + '.zeta_ek',
                         f'[0, {EK_SONUM_UST:g}) dışında ({zeta_ek!r})')
            beyan = ['I0_UYGULANMADI']
            m_t = g['m_t']
            if m_t is None:
                self.baglanmayan.append({'tank_id': tid,
                                         'sebep': ['TANK_KUTLESI_VERILMEDI']})
                continue
            if not isinstance(m_t, dict) or set(m_t) != {'t', 'm'}:
                _ret('TIP', alan + '.m_t', "{'t': [...], 'm': [...]} olmalı")
            ts, ms = m_t['t'], m_t['m']
            if not isinstance(ts, (list, tuple, np.ndarray)) or \
                    not isinstance(ms, (list, tuple, np.ndarray)):
                _ret('TIP', alan + '.m_t', 't ve m liste olmalı')
            if not (1 <= len(ts) == len(ms) <= KUTLE_SERISI_NOKTA_SINIRI):
                _ret('BOYUT', alan + '.m_t',
                     f'1..{KUTLE_SERISI_NOKTA_SINIRI} eşit uzunlukta nokta')
            t_arr = np.array([_sonlu(x, alan + '.m_t.t') for x in ts])
            m_arr = np.array([_sonlu(x, alan + '.m_t.m') for x in ms])
            if np.any(m_arr < 0.0):
                _ret('ARALIK', alan + '.m_t.m', 'negatif kütle')
            if t_arr.size > 1 and np.any(np.diff(t_arr) <= 0.0):
                _ret('SIRA', alan + '.m_t.t', 'kesin artan olmalı')
            if t_arr[0] < 0.0:
                _ret('ARALIK', alan + '.m_t.t', 'negatif zaman')
            m_toplam = float(cozucu.m_dry + cozucu.m_prop)
            if m_arr.max() >= m_toplam:
                _ret('KUTLE_TUTARSIZ', alan + '.m_t.m',
                     f'tank kütlesi {m_arr.max():g} kg araç kütlesi '
                     f'{m_toplam:g} kg\'dan küçük olmalı')
            if t_arr.size == 1:
                beyan.append('TANK_TUKETIMI_ITKIYLE_ORANTILI')
            t_rho = rho_rho = None
            rho_t = g.get('rho_t')
            if rho_t is not None:
                if not isinstance(rho_t, dict) or set(rho_t) != {'t', 'rho'}:
                    _ret('TIP', alan + '.rho_t',
                         "{'t': [...], 'rho': [...]} olmalı")
                tr, rr = rho_t['t'], rho_t['rho']
                if not isinstance(tr, (list, tuple, np.ndarray)) or \
                        not isinstance(rr, (list, tuple, np.ndarray)):
                    _ret('TIP', alan + '.rho_t', 't ve rho liste olmalı')
                if not (1 <= len(tr) == len(rr) <= KUTLE_SERISI_NOKTA_SINIRI):
                    _ret('BOYUT', alan + '.rho_t',
                         f'1..{KUTLE_SERISI_NOKTA_SINIRI} eşit uzunlukta nokta')
                t_rho = np.array([_sonlu(x, alan + '.rho_t.t') for x in tr])
                rho_rho = np.array([_sonlu(x, alan + '.rho_t.rho') for x in rr])
                if np.any(rho_rho <= 0.0):
                    _ret('ARALIK', alan + '.rho_t.rho',
                         'yoğunluk pozitif olmalı')
                if t_rho.size > 1 and np.any(np.diff(t_rho) <= 0.0):
                    _ret('SIRA', alan + '.rho_t.t', 'kesin artan olmalı')
                if t_rho[0] < 0.0:
                    _ret('ARALIK', alan + '.rho_t.t', 'negatif zaman')
                beyan.append('TANK_YOGUNLUGU_SERIDEN')
            nu = sivi['nu_m2_s']
            silindir = geo['tur'] == _tablo.GEOMETRI_DIK_SILINDIR
            if nu is None or not silindir:
                beyan.append('CEPER_SONUMU_HESAPLANAMADI')
            if zeta_ek and (nu is not None and silindir):
                beyan.append('SONUM_TOPLANABILIRLIGI')
            tanklar.append({
                'tank_id': tid, 'x_taban': x_taban, 'tablo': tablo,
                'rho': float(sivi['rho_kg_m3']), 'sigma': sivi['sigma_N_m'],
                'nu': nu, 'silindir': silindir,
                'R': float(geo['R_ref_m']), 'V_ic': float(geo['V_ic_m3']),
                't_m': t_arr, 'm_m': m_arr,
                't_rho': t_rho, 'rho_rho': rho_rho,
                'zeta_ek': 0.0 if zeta_ek is None else zeta_ek,
                'beyan': beyan,
            })
        self.tanklar = tanklar
        self.n = len(tanklar)
        self.durum_boyu = 4 * self.n
        #: Ayrıntı kaydı: None iken RHS yan etkisizdir. Doğrusallaştırma ve
        #: çıktı türetimi sözlük atayıp ``_derivatives``'i bir kez çağırır.
        self.kayit = None
        self._cozucu_m_dry = float(cozucu.m_dry)
        self._cozucu = cozucu
        self._atalet_denetimi(cozucu)

    # -- tank kütlesi ve parametreler --------------------------------------
    def sivi_kutlesi(self, k, t):
        """m_k(t) [kg] ya da (None, kod). Dışdeğerleme yok."""
        tk = self.tanklar[k]
        t_m, m_m = tk['t_m'], tk['m_m']
        if t_m.size == 1:
            # Yüklenen kütle × kalan itici kesri (itkiyle orantılı tüketim;
            # 6-DOF'un kendi _mass_at'i ile aynı birikmiş impuls).
            if self.m_prop <= 0.0:
                return float(m_m[0]), None
            kesir = (self._cozucu._mass_at(t) - self._cozucu_m_dry) / self.m_prop
            return float(m_m[0]) * kesir, None
        if t > t_m[-1]:
            return None, 'TANK_KUTLE_SERISI_DISI'
        if t <= t_m[0]:
            return float(m_m[0]), None      # ateşlemeden önce tank dolu
        return float(np.interp(t, t_m, m_m)), None

    def sivi_yogunlugu(self, k, t):
        """ρ_k(t) [kg/m³] ya da (None, kod). Seri verilmediyse tablonun
        sabit yoğunluğu; seri varsa aradeğer, dışdeğerleme yok."""
        tk = self.tanklar[k]
        t_r, r_r = tk['t_rho'], tk['rho_rho']
        if t_r is None:
            return tk['rho'], None
        if t > t_r[-1]:
            return None, 'TANK_YOGUNLUK_SERISI_DISI'
        if t <= t_r[0]:
            return float(r_r[0]), None
        return float(np.interp(t, t_r, r_r)), None

    def parametreler(self, t, x_cg, f_x, bond_kapisi=True):
        """Tank başına o anki eşdeğer model parametreleri (§B.3.1, §B.3.6).

        Döner: liste; her öğe ``acik`` (bool), ``m1`` [kg] (kapalıda 0),
        ``xi`` [m] (x_cg − x1, buruna +), ``w1sq`` [1/s²], ``c`` = 2ζω1 [1/s],
        ``zeta``, ``L1``, ``kappa1``, ``m_sivi``, ``doluluk``, ``Gamma1``,
        ``x1``, ``kod`` (kapanma/beyan kodları).
        """
        out = []
        for k, tk in enumerate(self.tanklar):
            p = {'acik': False, 'm1': 0.0, 'xi': 0.0, 'w1sq': 0.0, 'c': 0.0,
                 'zeta': None, 'L1': None, 'kappa1': None, 'm_sivi': None,
                 'doluluk': None, 'Gamma1': None, 'x1': None, 'kod': [],
                 'rho': None, 'h': None}
            out.append(p)
            if t >= self.t_burn:
                p['kod'].append('YANMA_BITTI')
                continue
            m_k, kod = self.sivi_kutlesi(k, t)
            if m_k is None:
                p['kod'].append(kod)
                continue
            rho_k, kod = self.sivi_yogunlugu(k, t)
            if rho_k is None:
                p['kod'].append(kod)
                continue
            d = m_k / (rho_k * tk['V_ic'])
            p['m_sivi'], p['doluluk'], p['rho'] = m_k, d, rho_k
            s = tk['tablo'].ara(d)
            p['kod'].extend(s['sebep'])
            if s['durum'] == _tablo.DURUM_RET:
                p['kod'].append('SATIR_RET')
                continue
            p['L1'], p['kappa1'], p['Gamma1'] = s['L1_m'], s['kappa1_1m'], s['Gamma1']
            p['x1'] = tk['x_taban'] - s['z1_m']
            if not f_x > 0.0:
                p['kod'].append('FX_POZITIF_DEGIL')
                continue
            if bond_kapisi:
                b = _tablo.bond_degerlendir(rho_k, f_x, tk['R'], tk['sigma'])
                p['kod'].extend(c for c in b['sebep'] if c not in p['kod'])
                if b['durum'] == _tablo.DURUM_RET:
                    p['kod'].append('SATIR_RET')
                    continue
            zeta = tk['zeta_ek']
            if tk['nu'] is not None and tk['silindir']:
                zeta = zeta + _sa.duz_ceper_sonumu(tk['R'], s['h_m'], tk['nu'], f_x)
            w1sq = s['kappa1_1m'] * f_x
            p.update(acik=True, m1=s['m1_oran'] * m_k, xi=x_cg - p['x1'],
                     w1sq=w1sq, c=2.0 * zeta * math.sqrt(w1sq), zeta=zeta,
                     h=s['h_m'])
        return out

    def _atalet_denetimi(self, cozucu):
        """Kinetik enerji pozitifliği (§C-a (a0) notu): rijit kısmın merkezsel
        enine ataleti I_t − Σ m1 ξ² − (Σ m1 ξ)²/(m − Σ m1) > 0 olmalı. Yanma
        boyunca ızgarada denetlenir; ihlal araç atalet modeliyle tank
        modelinin çeliştiğini gösterir → adlı ret (fail-closed)."""
        if self.n == 0:
            return
        ts = np.unique(np.concatenate([
            np.linspace(0.0, self.t_burn, 201)[:-1],
            np.asarray(cozucu._t_thrust)[np.asarray(cozucu._t_thrust) < self.t_burn]]))
        for t in ts:
            m = cozucu._mass_at(t)
            x_cg = cozucu._cg_at(t)
            _, I_t = cozucu._inertia(m, x_cg)
            # f_x yalnız ω1 içindir; Bond kapısı atalet denetimini ilgilendirmez
            prm = self.parametreler(t, x_cg, 1.0, bond_kapisi=False)
            m1s = sum(p['m1'] for p in prm if p['acik'])
            m1xi = sum(p['m1'] * p['xi'] for p in prm if p['acik'])
            m1xi2 = sum(p['m1'] * p['xi'] ** 2 for p in prm if p['acik'])
            if m1s <= 0.0:
                continue
            if not (m - m1s > 0.0 and I_t - m1xi2 - m1xi ** 2 / (m - m1s) > 0.0):
                _ret('ATALET_TUTARSIZ', 'slosh_tanks',
                     f't = {t:g} s: çalkantı kütlesi (Σm1 = {m1s:g} kg) aracın '
                     f'enine ataletiyle (I_t = {I_t:g} kg·m²) tutarlı değil; '
                     f'rijit kısmın merkezsel ataleti pozitif olmalı')

    # -- durum vektörü ------------------------------------------------------
    def ayir(self, y):
        """(η (n,2), η̇ (n,2)) — durum vektörünün 13'ten sonraki kısmı."""
        z = y[13:13 + self.durum_boyu]
        return z[:2 * self.n].reshape(self.n, 2), z[2 * self.n:].reshape(self.n, 2)

    def baslangic_durumu(self, C_bi, g):
        """t = 0'da statik denge η = −Eᵀ f_O/ω1², η̇ = 0 (§B.3.5).

        Ateşlemeden önce araç rampada durur: f_O = −Cᵀ g_i. Statik eğim
        β = atan(|Eᵀ f_O|/f_x) > RAY_STATIK_EGIM_SINIRI_DEG ise ya da f_x ≤ 0
        ise η = 0 (beyanlı). Döner: (durum dizisi, beyan listesi).
        """
        g_b = C_bi.T @ np.array([0.0, 0.0, -g])
        f_O = -g_b
        f_x = float(f_O[0])
        eta = np.zeros((self.n, 2))
        beyan = []
        if self.n:
            yanal = E.T @ f_O
            egim = math.degrees(math.atan2(float(np.hypot(*yanal)), f_x))
            if f_x > 0.0 and egim <= RAY_STATIK_EGIM_SINIRI_DEG:
                prm = self.parametreler(0.0, self._cozucu._cg_at(0.0), f_x)
                for k, p in enumerate(prm):
                    if p['acik']:
                        eta[k] = -yanal / p['w1sq']
            else:
                beyan.append('RAY_STATIK_EGIM_SINIR_DISI')
        return np.concatenate([eta.ravel(), np.zeros(2 * self.n)]), beyan

    # -- RHS parçaları -------------------------------------------------------
    def ray_turevi(self, t, y, C_bi, a_i, g, x_cg):
        """Ray fazı (§B.3.5): ω = ω̇ = 0, â = Cᵀ a_i (izdüşürülmüş).

        η̈ = Eᵀ(Cᵀ g_i − â) − ω1² η − 2ζω1 η̇ = −Eᵀ f_O − ω1²η − 2ζω1η̇.
        Gövde denklemleri DEĞİŞMEZ (ray yanal tepkileri sönümler).
        """
        eta, etad = self.ayir(y)
        g_b = C_bi.T @ np.array([0.0, 0.0, -g])
        f_O = C_bi.T @ a_i - g_b
        prm = self.parametreler(t, x_cg, float(f_O[0]))
        deta = np.zeros((self.n, 2))
        detad = np.zeros((self.n, 2))
        yanal = E.T @ f_O
        for k, p in enumerate(prm):
            if p['acik']:
                deta[k] = etad[k]
                detad[k] = -yanal - p['w1sq'] * eta[k] - p['c'] * etad[k]
        if self.kayit is not None:
            self.kayit.update(f_O=f_O, prm=prm, ray=True, eta_dd=detad.copy())
        return np.concatenate([deta.ravel(), detad.ravel()])

    def serbest_ucus(self, t, y, C_bi, F_i, M_b, w_b, I3, m, g, x_cg,
                     a_i0, w_dot0):
        """Serbest uçuş (§B.3.4): (a_i, ω̇, durum türevi) döner.

        a_i0 ve w_dot0 bugünkü rijit kodun değerleridir (Coriolis'ten önce);
        düzeltme pertürbasyon biçiminde eklenir. m1 = 0 (bütün tanklar) iken
        Δ = 0 tam olarak: a_i0 + 0 = a_i0, ω̇0 + 0 = ω̇0 (bit düzeyinde).
        """
        eta, etad = self.ayir(y)
        g_i = np.array([0.0, 0.0, -g])
        g_b = C_bi.T @ g_i
        f_O = C_bi.T @ (F_i - m * g_i) / m        # yerçekimsiz dış kuvvet / m
        prm = self.parametreler(t, x_cg, float(f_O[0]))
        m1 = np.array([p['m1'] for p in prm])
        xi = np.array([p['xi'] for p in prm])
        w1sq = np.array([p['w1sq'] for p in prm])
        cc = np.array([p['c'] for p in prm])
        dx_a, dx_w, eta_dd = govde_duzeltmesi(
            m, I3, g_b, C_bi.T @ a_i0, w_dot0, w_b, m1, xi, w1sq, cc, eta, etad)
        a_i = a_i0 + C_bi @ dx_a
        w_dot = w_dot0 + dx_w
        acik = np.array([p['acik'] for p in prm], dtype=bool)
        deta = np.where(acik[:, None], etad, 0.0)
        detad = np.where(acik[:, None], eta_dd, 0.0)
        if self.kayit is not None:
            self.kayit.update(f_O=f_O, prm=prm, ray=False, eta_dd=detad.copy(),
                              dx_a=dx_a, dx_w=dx_w)
        return a_i, w_dot, np.concatenate([deta.ravel(), detad.ravel()])


def govde_duzeltmesi(m, I3, g_b, a_b0, w_dot0, w, m1, xi, w1sq, cc, eta, etad):
    """(B-1)–(B-3)'ün pertürbasyon çözümü (§B.3.4) — saf işlev.

    Girdi: m [kg]; I3 = (I_x, I_t, I_t) bugünkü atalet (η = 0'da I_O);
    g_b = Cᵀ g_i; a_b0 = Cᵀ a_i0 = Cᵀ F_dış/m; w_dot0 bugünkü ω̇; w = ω;
    tank dizileri m1, ξ (x_cg − x1), ω1², c = 2ζω1; η, η̇ (n,2).
    Çıktı: (Δâ (gövde), Δω̇, η̈ (n,2)). Kapalı tankta m1 = 0 verilir; onun η̈'sı
    çağıranca 0'a çekilir.

    A0 = diag(m𝟙, I3), r0 bugünkü sağ taraf; A1, r1 her terimi m1 ya da S
    içerir (S = Σ m1 E η; I_O − I3 = Σ m1[(|ρ|²𝟙 − ρρᵀ) − (|ρ0|²𝟙 − ρ0ρ0ᵀ)]).
    Δx = (A0 + A1)⁻¹ (r1 − A1 x0); m1 = 0'da A1 = r1 = 0 ⇒ Δx = 0 tam.
    """
    n = len(m1)
    S = np.zeros(3)
    A1 = np.zeros((6, 6))
    r1 = np.zeros(6)
    b = np.zeros((n, 2))
    rho = np.zeros((n, 3))
    dIO = np.zeros((3, 3))
    EEt = E @ E.T
    for k in range(n):
        if m1[k] == 0.0:
            continue
        rho0 = np.array([xi[k], 0.0, 0.0])
        rk = rho0 + E @ eta[k]
        rho[k] = rk
        Ev = E @ etad[k]
        S += m1[k] * (E @ eta[k])
        # b_k: (B-3) sağ tarafı
        b[k] = (E.T @ g_b
                - E.T @ (np.cross(w, np.cross(w, rk)) + 2.0 * np.cross(w, Ev))
                - w1sq[k] * eta[k] - cc[k] * etad[k])
        Rx = _capraz(rk)
        A1[0:3, 0:3] -= m1[k] * EEt
        A1[0:3, 3:6] += m1[k] * (EEt @ Rx)
        A1[3:6, 0:3] -= m1[k] * (Rx @ EEt)
        A1[3:6, 3:6] += m1[k] * (Rx @ EEt @ Rx)
        dIO += m1[k] * ((rk @ rk) * np.eye(3) - np.outer(rk, rk)
                        - (rho0 @ rho0) * np.eye(3) + np.outer(rho0, rho0))
        r1[0:3] += -2.0 * m1[k] * np.cross(w, Ev) - m1[k] * (E @ b[k])
        r1[3:6] += (-2.0 * m1[k] * np.cross(rk, np.cross(w, Ev))
                    - m1[k] * (Rx @ (E @ b[k])))
    Sx = _capraz(S)
    A1[0:3, 3:6] -= Sx
    A1[3:6, 0:3] += Sx
    A1[3:6, 3:6] += dIO
    r1[0:3] += -np.cross(w, np.cross(w, S))
    r1[3:6] += -np.cross(w, dIO @ w) + np.cross(S, g_b)
    x0 = np.concatenate([a_b0, w_dot0])
    A = np.diag(np.array([m, m, m, I3[0], I3[1], I3[2]], dtype=float)) + A1
    dx = np.linalg.solve(A, r1 - A1 @ x0)
    a_b = a_b0 + dx[0:3]
    w_dot = w_dot0 + dx[3:6]
    eta_dd = np.zeros((n, 2))
    for k in range(n):
        if m1[k] == 0.0:
            continue
        eta_dd[k] = b[k] - E.T @ a_b + E.T @ np.cross(rho[k], w_dot)
    return dx[0:3], dx[3:6], eta_dd


# ---------------------------------------------------------------------------
# Doğrusal yunuslama düzlemi modeli (§B.5)
# ---------------------------------------------------------------------------
def dogrusal_model(m, I, u, ud, Na, Ma, Mq, f, tanklar):
    """(B-5)–(B-7): M ẋ = K x, x = [α, q, η_1..η_n, η̇_1..η̇_n].

    ``tanklar``: [(m1, ξ, ω1², ζ)]. A = M⁻¹K döner (u > 0 gerekir).
    """
    n = len(tanklar)
    N = 2 + 2 * n
    M = np.zeros((N, N))
    K = np.zeros((N, N))
    M[0, 0] = -m * u
    K[0, 0] = Na + m * ud
    K[0, 1] = -m * u
    M[1, 1] = I
    K[1, 0] = Ma
    K[1, 1] = Mq
    for k, (m1, xi, w1sq, zeta) in enumerate(tanklar):
        ie, idd = 2 + k, 2 + n + k
        M[0, idd] = m1
        M[1, idd] = m1 * xi
        K[1, ie] = m1 * f
        M[ie, ie] = 1.0
        K[ie, idd] = 1.0
        M[idd, 0] = -u
        M[idd, 1] = xi
        M[idd, idd] = 1.0
        K[idd, 0] = ud
        K[idd, 1] = -u
        K[idd, ie] = -w1sq
        K[idd, idd] = -2.0 * zeta * math.sqrt(w1sq)
    return np.linalg.solve(M, K)


def bosluk_modeli(m, I, f, tanklar):
    """Aerodinamiksiz, u = 0 (kalkış anı) model: x = [q, η.., η̇..].

    T: m ẇ + Σ m1 η̈ = 0 ile ẇ yok edilir; (B-6), (B-7) u = 0. Tek tankta
    sıfırdan farklı kökler ±iΩ_c, Ω_c² = ω1²(I + m1 L1 ξ)/(I(1−μ) − m1 ξ²)
    (§C-a (a1)).
    """
    n = len(tanklar)
    N = 1 + 2 * n
    M = np.zeros((N, N))
    K = np.zeros((N, N))
    M[0, 0] = I
    mu = [t[0] / m for t in tanklar]
    for k, (m1, xi, w1sq, zeta) in enumerate(tanklar):
        ie, idd = 1 + k, 1 + n + k
        M[0, idd] = m1 * xi
        K[0, ie] = m1 * f
        M[ie, ie] = 1.0
        K[ie, idd] = 1.0
        M[idd, 0] = xi
        for j in range(n):
            M[idd, 1 + n + j] = (1.0 if j == k else 0.0) - mu[j]
        K[idd, ie] = -w1sq
        K[idd, idd] = -2.0 * zeta * math.sqrt(w1sq)
    return np.linalg.solve(M, K)


def omega_c_kapali(m, I, m1, L1, xi, f):
    """(a1) kapalı biçim Ω_c [rad/s] (§C-a; betik v2 §D)."""
    w1sq = f / L1
    return math.sqrt(w1sq * (I + m1 * L1 * xi) / (I * (1.0 - m1 / m) - m1 * xi * xi))


def a0_kokleri(m, I, m1, L1, xi, f, Na, Ma):
    """(a0) u → ∞, sönümsüz: A s⁴ + B s² + C = 0 kökleri (§C-a)."""
    mu = m1 / m
    w1sq = f / L1
    A = I * (1.0 - mu) - m1 * xi * xi
    B = I * w1sq - Ma * (1.0 - mu) - mu * xi * Na + m1 * f * xi
    C = -Ma * w1sq + mu * f * Na
    s2 = np.roots([A, B, C]).astype(complex)
    return np.concatenate([np.sqrt(s2), -np.sqrt(s2)]), (A, B, C)


def karakteristik_polinom(A):
    """det(sI − A) katsayıları ÖZDEĞERSİZ (Faddeev–LeVerrier yinelemesi).

    Hurwitz çapraz denetimi özdeğer hesabından bağımsız olsun diye
    (``np.poly`` özdeğer kullanır). Sayısal ölçek için σ = s/r, r = |det A|^(1/n)
    (özdeğer büyüklüklerinin geometrik ortalaması); det 0 ise r = ‖A‖₂.
    Yineleme: M_1 = 𝟙, c_{k} = −tr(B M_k)/k, M_{k+1} = B M_k + c_k 𝟙 (B = A/r).
    Döner: (σ polinomunun katsayıları, yüksekten düşüğe, baş 1; r).
    """
    n = A.shape[0]
    d = abs(float(np.linalg.det(A)))
    r = d ** (1.0 / n) if d > 0.0 else float(np.linalg.norm(A, 2))
    if not (r > 0.0 and math.isfinite(r)):
        r = 1.0
    B = A / r
    c = [1.0]
    Mk = np.eye(n)
    for k in range(1, n + 1):
        BM = B @ Mk
        ck = -float(np.trace(BM)) / k
        c.append(ck)
        Mk = BM + ck * np.eye(n)
    return np.array(c), r


def hurwitz_kararli(katsayi):
    """Hurwitz ölçütü (SP-106 Denk. (7.32)–(7.35)): a_λ > 0 ve Hᵥ > 0.

    ``katsayi`` yüksekten düşüğe, a0 > 0. Döner: (kararlı mı, determinantlar).
    """
    a = np.asarray(katsayi, dtype=float)
    if a[0] < 0:
        a = -a
    n = a.size - 1
    H = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            k = 2 * (j + 1) - (i + 1)
            if 0 <= k <= n:
                H[i, j] = a[k]
    det = [float(np.linalg.det(H[:i, :i])) for i in range(1, n + 1)]
    return bool(np.all(a > 0.0) and all(dv > 0.0 for dv in det)), det


def mod_katilimi(ozvektor, I, tanklar):
    """Her özvektör için normalleştirilmiş enerji payları (§B.5): gövde
    I|q|² (dönme), çalkantı k m1_k |η̇_k|². α bileşeni kullanılmaz: hızlı
    araçta α ≈ θ dönmesini izler, öteleme enerjisi değildir."""
    n = len(tanklar)
    out = []
    for j in range(ozvektor.shape[1]):
        v = ozvektor[:, j]
        pay = {'govde': I * abs(v[1]) ** 2}
        for k, t in enumerate(tanklar):
            pay[f'calkanti:{k}'] = t[0] * abs(v[2 + n + k]) ** 2
        top = sum(pay.values())
        out.append({k: (x / top if top > 0.0 else 0.0) for k, x in pay.items()})
    return out


def mod_tanimi(ozdeger, ozvektor, I, tanklar):
    """Mod etiketleri: salınımlı çiftler (Im > 0) gövde + her tank için TEK
    etiket alacak biçimde, katılım payları toplamını en büyükleyen eşlemeyle
    atanır (güçlü karışmış modlarda argmax iki modu aynı etikete verebilir).
    Salınımlı çift sayısı etiket sayısına eşit değilse (ör. gövde modu aşırı
    sönümlü, iki gerçek kök) her köke argmax etiketi verilir. Döner:
    (etiketler, katılım payları)."""
    import itertools
    kat = mod_katilimi(ozvektor, I, tanklar)
    etiket = [max(k, key=k.get) for k in kat]
    adlar = list(kat[0].keys()) if kat else []
    ust = [j for j, z in enumerate(ozdeger) if z.imag > 0.0]
    if len(ust) == len(adlar) and len(adlar) <= 6:
        en_iyi = max(itertools.permutations(adlar),
                     key=lambda p: sum(kat[j][a] for j, a in zip(ust, p)))
        for j, a in zip(ust, en_iyi):
            etiket[j] = a
            # eşlenik kök aynı etiketi alır
            jj = int(np.argmin(np.abs(np.asarray(ozdeger) - np.conj(ozdeger[j]))))
            etiket[jj] = a
    return etiket, kat


def zeta_min_ara(m, I, u, ud, Na, Ma, Mq, f, tanklar):
    """Bütün köklerin Re < 0 olduğu en küçük ORTAK çalkantı sönümü (§B.5).

    0'da kararlıysa 0,0; ZETA_MIN_UST'te de kararsızsa None (üst sınırın
    üstünde). İkiye bölme ZETA_MIN_BOLME_ADIMI adım.
    """
    def kararli(z):
        tt = [(m1, xi, w1sq, z) for (m1, xi, w1sq, _z) in tanklar]
        A = dogrusal_model(m, I, u, ud, Na, Ma, Mq, f, tt)
        return bool(np.all(np.linalg.eigvals(A).real < 0.0))
    if kararli(0.0):
        return 0.0
    if not kararli(ZETA_MIN_UST):
        return None
    lo, hi = 0.0, ZETA_MIN_UST
    for _ in range(ZETA_MIN_BOLME_ADIMI):
        mid = 0.5 * (lo + hi)
        if kararli(mid):
            hi = mid
        else:
            lo = mid
    return hi


def _kok_listesi(ozdeger):
    return [[float(z.real), float(z.imag)] for z in ozdeger]


def _mod_ozeti(ozdeger, etiket, katilim=None):
    """Im ≥ 0 köklerin frekans/sönüm özeti (çiftin bir eşi)."""
    out = []
    for j, (z, e) in enumerate(zip(ozdeger, etiket)):
        if z.imag < 0.0:
            continue
        wn = abs(z)
        out.append({'mod': e, 're': float(z.real), 'im': float(z.imag),
                    'katilim': (None if katilim is None else
                                {k: float(x) for k, x in katilim[j].items()}),
                    'omega_n_rad_s': float(wn), 'f_hz': float(wn / (2 * math.pi)),
                    'zeta': (float(-z.real / wn) if wn > 0.0 else None)})
    return out


def an_analizi(m, I, u, ud, Na, Ma, Mq, f, tanklar, zeta_gercek):
    """Bir andaki bağlaşık + rijit özdeğerler, Hurwitz, ζ_min, yakınlık.

    ``tanklar``: açık tanklar [(m1, ξ, ω1², ζ)] (en az bir tank).
    """
    A = dogrusal_model(m, I, u, ud, Na, Ma, Mq, f, tanklar)
    lam, V = np.linalg.eig(A)
    etiket, katilim = mod_tanimi(lam, V, I, tanklar)
    kararli_oz = bool(np.all(lam.real < 0.0))
    kats, r = karakteristik_polinom(A)
    kararli_hw, hw_det = hurwitz_kararli(kats)
    # Rijit (m1 = 0): gövde satırları η'dan bağımsızdır, M blok alt üçgendir;
    # rijit gövde kökleri A_r'nin sol üst 2×2 bloğunun özdeğerleridir.
    rij = [(0.0, xi, w1sq, z) for (_m1, xi, w1sq, z) in tanklar]
    Ar = dogrusal_model(m, I, u, ud, Na, Ma, Mq, f, rij)
    lam_r = np.linalg.eigvals(Ar[:2, :2])
    et_r = ['govde'] * lam_r.size
    rijit_kararli = bool(np.all(lam_r.real < 0.0))
    zmin = zeta_min_ara(m, I, u, ud, Na, Ma, Mq, f, tanklar)
    modlar = _mod_ozeti(lam, etiket, katilim)
    w_govde = [x['omega_n_rad_s'] for x in modlar if x['mod'] == 'govde']
    yakinlik = []
    for x in modlar:
        if x['mod'].startswith('calkanti') and w_govde and w_govde[0] > 0.0:
            oran = x['omega_n_rad_s'] / w_govde[0]
            yakinlik.append({'mod': x['mod'], 'oran': oran,
                             'uyari': bool(abs(oran - 1.0) <= YAKINLIK_BANDI)})
    return {
        'ozdegerler': _kok_listesi(lam),
        'modlar': modlar,
        'rijit_ozdegerler': _kok_listesi(lam_r),
        'rijit_modlar': _mod_ozeti(lam_r, et_r),
        'kararli_ozdeger': kararli_oz,
        'kararli_hurwitz': kararli_hw,
        'hurwitz_determinantlari': hw_det,
        'karakteristik_polinom_olcek': r,
        'rijit_kararli': rijit_kararli,
        'zeta_min': zmin,
        'zeta_gercek': zeta_gercek,
        'sonum_payi': (None if zmin is None or zmin == 0.0 or zeta_gercek is None
                       else zeta_gercek / zmin),
        'yakinlik': yakinlik,
        'yakinlik_bandi': YAKINLIK_BANDI,
    }


# ---------------------------------------------------------------------------
# Dondurulmuş katsayılar (§B.5) — çözücünün kendi işlevleriyle
# ---------------------------------------------------------------------------
def dondurulmus_katsayilar(cozucu, t, y):
    """t*'da (B-5)–(B-7) katsayıları. ``_derivatives`` ile aynı atmosfer,
    itki, kütle, atalet ve aerodinamik işlevleri kullanılır; f_x ve tank
    parametreleri RHS'nin KENDİSİNDEN (ayrıntı kaydı) okunur, u̇ = e_x·Cᵀ a_i
    RHS'nin ivmesidir. Formüller §B.5: N_α = q̄ S C_Nα, M_α = −(x_cp − x_cg)
    N_α, M_q = −q̄ S C_Nα (x_cp − x_cg)²/u − ṁ (L − x_cg)²."""
    from hrma.analysis import six_dof_trajectory as sdt
    bag = cozucu._slosh
    bag.kayit = {}
    try:
        dy = cozucu._derivatives(t, y)
        kayit = dict(bag.kayit)
    finally:
        bag.kayit = None
    q = y[6:10] / np.linalg.norm(y[6:10])
    C = sdt._quat_to_dcm(q)
    m = cozucu._mass_at(t)
    x_cg = cozucu._cg_at(t)
    _, I_t = cozucu._inertia(m, x_cg)
    h_agl = max(float(y[2]), 0.0)
    h_msl = cozucu.launch_altitude + h_agl
    rho, a_snd = sdt._atmosphere(h_msl)
    u_i = y[3:6] - cozucu._wind_i
    u = float(np.linalg.norm(u_i))
    qbar = 0.5 * rho * u * u
    mach = u / a_snd
    S = cozucu.aero.S_ref
    cn, x_cp = cozucu.aero.at_mach(mach)
    arm = x_cp - x_cg
    Na = qbar * S * cn
    Ma = -arm * Na
    mdot = cozucu._mdot_at(t)
    Mq = (-qbar * S * cn * arm * arm / u if u > 0.0 else 0.0) \
        - mdot * (cozucu.aero.L - x_cg) ** 2
    ud = float(C[:, 0] @ dy[3:6])
    # dq̄/dt = ½ ρ'(h) ḣ u² + ρ u·a (rüzgâr sabit). ρ' merkezi fark, 1 m.
    r_p, _ = sdt._atmosphere(h_msl + 1.0)
    r_m, _ = sdt._atmosphere(max(h_msl - 1.0, 0.0))
    drho = (r_p - r_m) / ((h_msl + 1.0) - max(h_msl - 1.0, 0.0))
    dqbar = 0.5 * drho * float(y[5]) * u * u + rho * float(u_i @ dy[3:6])
    return {
        't': float(t), 'm': float(m), 'I': float(I_t), 'x_cg': float(x_cg),
        'u': u, 'u_dot': ud, 'rho': float(rho), 'qbar': float(qbar),
        'mach': float(mach), 'cn_alpha': float(cn), 'x_cp': float(x_cp),
        'N_alpha': float(Na), 'M_alpha': float(Ma), 'M_q': float(Mq),
        'f_x': float(kayit['f_O'][0]), 'dqbar_dt': float(dqbar),
        'prm': kayit['prm'], 'ray': kayit['ray'],
        'altitude_m': h_agl,
    }


def _dondurulmus_gecerli(k):
    """ω_g τ_q ≥ 2π (§B.5). q̄ = 0 ya da M_α = 0 ise geçersiz."""
    if not (k['qbar'] > 0.0 and k['M_alpha'] != 0.0):
        return False, 0.0
    w_g = math.sqrt(abs(k['M_alpha']) / k['I'])
    if k['dqbar_dt'] == 0.0:
        return True, math.inf
    tau = k['qbar'] / abs(k['dqbar_dt'])
    return bool(w_g * tau >= DONDURULMUS_KATSAYI_ESIGI), w_g * tau


# ---------------------------------------------------------------------------
# solve() çıktıları
# ---------------------------------------------------------------------------
def _an_zamanlari(cozucu, t, out):
    """Dört anın zamanı (ya da None) ve gerekçesi (§B.5)."""
    tb = float(cozucu.t_burn)
    an = {}
    # kalkış: itki > ağırlık (sahada, ilk kesişim). İtki eğrisi düğümlerinde
    # tarama + doğrusal parça içinde kesin kök (F ve m parça içinde doğrusal
    # değil; ikiye bölme, 60 adım).
    from hrma.analysis import six_dof_trajectory as sdt
    g0 = float(cozucu.g_surface)
    p_saha = sdt._pressure_at(cozucu.launch_altitude)

    def fark(tt):
        return (cozucu._thrust_at_altitude(tt, p_saha)
                - cozucu._mass_at(tt) * g0)
    if fark(0.0) > 0.0:
        an['kalkis'] = 0.0
    else:
        tn = [float(x) for x in cozucu._t_thrust if 0.0 < x < tb]
        tn.append(np.nextafter(tb, -np.inf))
        onceki = 0.0
        an['kalkis'] = None
        for x in tn:
            if fark(x) > 0.0:
                lo, hi = onceki, x
                for _ in range(60):
                    mid = 0.5 * (lo + hi)
                    if fark(mid) > 0.0:
                        hi = mid
                    else:
                        lo = mid
                an['kalkis'] = hi
                break
            onceki = x
    # ray çıkışı: konum normu ray boyunu ilk aştığı örnek (çözüm örneği).
    r = out['position']      # satır sırası normu etkilemez
    dist = np.linalg.norm(r, axis=0)
    i_ray = np.nonzero(dist >= cozucu.rail_length)[0]
    an['ray_cikisi'] = (float(t[i_ray[0]]) if i_ray.size and t[i_ray[0]] < tb
                        else None)
    # en büyük q̄ — yanma içinde (t < t_burn)
    qa = out['dynamic_pressure']
    yanma = t < tb
    an['en_buyuk_q'] = (float(t[yanma][int(np.argmax(qa[yanma]))])
                        if yanma.any() else None)
    an['yanma_sonu'] = float(np.nextafter(tb, -np.inf)) if t.size and \
        t[-1] >= tb else None
    return an


def _durum_an(t, sol_t, sol_y, tb):
    """t*'daki durum: çözüm örneği (en yakın, yanma sonunda t_burn örneği)."""
    if t is None:
        return None
    i = int(np.argmin(np.abs(sol_t - t)))
    return sol_y[:, i]


# ---------------------------------------------------------------------------
# Yanma boyunca tarama (3.0.7 V307/ÇALKANTI-KARARLILIK; CALKANTI §B.5)
# ---------------------------------------------------------------------------
def ornek_siniflandir(cozucu, t, y, k=None):
    """Bir çözüm örneğinin donmuş katsayılı sınıfı (tarama birimi).

    Döner: (kayıt, k). ``kayıt['sinif']`` ∈ TARAMA_SINIFLARI; hüküm
    verilebilen örnekte (KARARLI / CALKANTI_KARARSIZ / RIJIT_KARARSIZ)
    ``max_re``, ``rijit_max_re``, ``kat`` (model katsayıları), ``tank_t``
    ((m1, ξ, ω1², ζ) açık tanklar) ve ``acik_k`` (açık tank dizinleri) dolu.
    Sınıf kuralı dört an değerlendiricisiyle aynıdır (rayda gövde kilitli;
    çalkantı kapalı; ω_g τ_q < 2π geçersiz; rijit kararsız; bağlaşık
    kararsız), yalnız "kararsız" eşiği sayısal çözünürlük payı taşır
    (``TARAMA_RE_ESIGI_BAGIL``).
    """
    if k is None:
        k = dondurulmus_katsayilar(cozucu, t, y)
    o = {'t': float(t), 'sinif': None, 'max_re': None, 'rijit_max_re': None,
         'olcut': None, 'kat': None, 'tank_t': None, 'acik_k': None,
         'prm': k['prm']}
    acik_k = [i for i, p in enumerate(k['prm']) if p['acik']]
    if k['ray']:
        o['sinif'] = TARAMA_RAYDA
        return o, k
    if not acik_k:
        o['sinif'] = TARAMA_KAPALI
        return o, k
    if not k['u'] > 0.0:
        o['sinif'] = TARAMA_GECERSIZ
        return o, k
    gecerli, olcut = _dondurulmus_gecerli(k)
    o['olcut'] = olcut
    if not gecerli:
        o['sinif'] = TARAMA_GECERSIZ
        return o, k
    kat = (k['m'], k['I'], k['u'], k['u_dot'], k['N_alpha'], k['M_alpha'],
           k['M_q'], k['f_x'])
    tank_t = [(k['prm'][i]['m1'], k['prm'][i]['xi'], k['prm'][i]['w1sq'],
               k['prm'][i]['zeta']) for i in acik_k]
    o.update(kat=kat, tank_t=tank_t, acik_k=acik_k)
    _siniflandir(o)
    return o, k


def _siniflandir(o, tank_t=None):
    """``o['kat']`` ve tank listesinden max Re, rijit max Re ve sınıf.
    ``tank_t`` verilirse (ör. bafl sönümüyle) kayıt DEĞİŞMEZ, yalnız
    (sınıf, max Re) döner."""
    tt = o['tank_t'] if tank_t is None else tank_t
    lam = np.linalg.eigvals(dogrusal_model(*o['kat'], tt))
    rij = [(0.0, xi, w1sq, z) for (_m1, xi, w1sq, z) in tt]
    lam_r = np.linalg.eigvals(dogrusal_model(*o['kat'], rij)[:2, :2])
    esik = TARAMA_RE_ESIGI_BAGIL * float(np.max(np.abs(lam)))
    max_re = float(np.max(lam.real))
    rij_re = float(np.max(lam_r.real))
    if rij_re > esik:
        sinif = TARAMA_RIJIT_KARARSIZ
    elif max_re > esik:
        sinif = TARAMA_CALKANTI_KARARSIZ
    else:
        sinif = TARAMA_KARARLI
    if tank_t is None:
        o.update(sinif=sinif, max_re=max_re, rijit_max_re=rij_re)
    return sinif, max_re


def _kenar_incelt(cozucu, o_ic, y_ic, o_dis, y_dis):
    """Pencere kenarı: içteki (kararsız) ve dıştaki (kararlı) komşu örnek
    arasında, durum doğrusal aradeğerlenerek ikiye bölme. Döner: (t_kenar,
    tür). Aradaki bir noktada hüküm verilemiyorsa (sınıf KARARLI ya da
    CALKANTI_KARARSIZ değil) kenar içteki örneğin anıdır."""
    t_ic, t_dis = o_ic['t'], o_dis['t']
    for _ in range(60):
        if abs(t_dis - t_ic) <= TARAMA_KENAR_TOL_S:
            break
        tm = 0.5 * (t_ic + t_dis)
        s = (tm - o_ic['t']) / (o_dis['t'] - o_ic['t'])
        ym = y_ic + s * (y_dis - y_ic)
        om, _ = ornek_siniflandir(cozucu, tm, ym)
        if om['sinif'] == TARAMA_CALKANTI_KARARSIZ:
            t_ic = tm
        elif om['sinif'] == TARAMA_KARARLI:
            t_dis = tm
        else:
            return o_ic['t'], KENAR_DEGERLENDIRME_SINIRI
    return 0.5 * (t_ic + t_dis), KENAR_ISARET_DEGISIMI


def _pencere_zeta_min(ornekler):
    """Pencerenin BÜTÜN örneklerini kararlı kılan en küçük ortak çalkantı
    sönümü. Döner: (ζ_min | None, t, doğrulandı mı). None: bir örnekte
    ``ZETA_MIN_UST``'te bile kararsız."""
    n = len(ornekler)
    en_kotu = max(range(n), key=lambda i: ornekler[i]['max_re'])
    alt = sorted(set(int(round(x)) for x in np.linspace(
        0, n - 1, min(n, ZETA_PENCERE_ALT_ORNEK))) | {en_kotu})
    z, tz = 0.0, ornekler[en_kotu]['t']
    for i in alt:
        zi = zeta_min_ara(*ornekler[i]['kat'], ornekler[i]['tank_t'])
        if zi is None:
            return None, ornekler[i]['t'], True
        if zi > z:
            z, tz = zi, ornekler[i]['t']

    def re_z(o, zz):
        tt = [(m1, xi, w1sq, zz) for (m1, xi, w1sq, _z) in o['tank_t']]
        return float(np.max(np.linalg.eigvals(
            dogrusal_model(*o['kat'], tt)).real))
    for _ in range(ZETA_PENCERE_DOGRULAMA_TURU):
        kotu, re_kotu = None, 0.0
        for o in ornekler:
            r = re_z(o, z)
            if r >= re_kotu:       # zeta_min_ara kuralı: kararlı ⇔ Re < 0
                kotu, re_kotu = o, r
        if kotu is None:
            return z, tz, True
        zi = zeta_min_ara(*kotu['kat'], kotu['tank_t'])
        if zi is None:
            return None, kotu['t'], True
        if not zi > z:
            return z, tz, False
        z, tz = zi, kotu['t']
    return z, tz, False


def yanma_taramasi(cozucu, sol_t, sol_y, siniflar=None):
    """Yanma boyunca donmuş katsayılı tarama (CALKANTI §B.5; karar 16 Kas).

    Tarama çözümün KENDİ örneklerinde (t < t_burn) ve yanma sonunda
    (t_burn⁻, durum t_burn örneği) yapılır: örnek aralığı entegratörün
    adımıdır (en çok ``max_step``), durum aradeğersizdir. Ardışık
    CALKANTI_KARARSIZ örnekler bir PENCERE oluşturur; kenarı komşu örnek
    KARARLI ise ikiye bölmeyle inceltilir (``TARAMA_KENAR_TOL_S``), komşu
    örnekte hüküm verilemiyorsa kenar "değerlendirme sınırı"dır.

    ``siniflar``: önceden sınıflandırılmış örnek kayıtları (``solve``
    çıktısı aynı RHS çağrısını paylaşsın diye); None ise burada kurulur.
    Döner: sözlük (``ornekler``, ``pencereler``, ``rijit_pencereler``,
    ``kapsam``). Her pencere iç kullanım için ``_i`` = (ilk, son) örnek
    dizinini taşır; ``cozum_ciktilari`` yayımlamadan önce çıkarır.
    """
    tb = float(cozucu.t_burn)
    bag = cozucu._slosh
    if siniflar is None:
        siniflar = []
        for j in np.flatnonzero(sol_t < tb):
            o, _ = ornek_siniflandir(cozucu, float(sol_t[j]), sol_y[:, j])
            o['j'] = int(j)
            siniflar.append(o)
    ornekler = list(siniflar)
    j_tb = np.flatnonzero(sol_t >= tb)
    if j_tb.size and sol_t[j_tb[0]] == tb:
        t_son = float(np.nextafter(tb, -np.inf))
        if not ornekler or ornekler[-1]['t'] < t_son:
            o, _ = ornek_siniflandir(cozucu, t_son, sol_y[:, j_tb[0]])
            o['j'] = int(j_tb[0])
            ornekler.append(o)
    n = len(ornekler)
    sinif = [o['sinif'] for o in ornekler]

    def kosular(hedef):
        out, i = [], 0
        while i < n:
            if sinif[i] == hedef:
                a = i
                while i + 1 < n and sinif[i + 1] == hedef:
                    i += 1
                out.append((a, i))
            i += 1
        return out

    pencereler = []
    for a, b in kosular(TARAMA_CALKANTI_KARARSIZ):
        w = ornekler[a:b + 1]
        kenar = []
        for ic, dis in ((a, a - 1), (b, b + 1)):
            if 0 <= dis < n and sinif[dis] == TARAMA_KARARLI:
                kenar.append(_kenar_incelt(
                    cozucu, ornekler[ic], sol_y[:, ornekler[ic]['j']],
                    ornekler[dis], sol_y[:, ornekler[dis]['j']]))
            else:
                kenar.append((ornekler[ic]['t'], KENAR_DEGERLENDIRME_SINIRI))
        (t1, k1), (t2, k2) = kenar
        en = max(w, key=lambda o: o['max_re'])
        an = an_analizi(*en['kat'], en['tank_t'],
                        min(x[3] for x in en['tank_t']))
        mod = max(an['modlar'], key=lambda x: x['re'])
        tank_id, yakinlik = None, None
        if mod['mod'].startswith('calkanti:'):
            kk = en['acik_k'][int(mod['mod'].split(':')[1])]
            tank_id = bag.tanklar[kk]['tank_id']
        for x in an['yakinlik']:
            if x['mod'] == mod['mod']:
                yakinlik = x['oran']
        if yakinlik is None and an['yakinlik']:
            # kararsız mod gövde etiketliyse: frekansça en yakın çalkantı modu
            yakinlik = min((x['oran'] for x in an['yakinlik']),
                           key=lambda r: abs(r - 1.0))
        zmin, t_z, dogrulandi = _pencere_zeta_min(w)
        tt = np.array([t1] + [o['t'] for o in w] + [t2])
        rr = np.array([0.0] + [o['max_re'] for o in w] + [0.0])
        if k1 != KENAR_ISARET_DEGISIMI:
            rr[0] = w[0]['max_re']
        if k2 != KENAR_ISARET_DEGISIMI:
            rr[-1] = w[-1]['max_re']
        dol = {}
        for kk, tk in enumerate(bag.tanklar):
            hs = [(o['prm'][kk]['doluluk'], o['prm'][kk]['h']) for o in w
                  if o['prm'][kk]['acik']]
            if hs:
                dol[tk['tank_id']] = {
                    'doluluk': [max(x[0] for x in hs), min(x[0] for x in hs)],
                    'h_m': [max(x[1] for x in hs), min(x[1] for x in hs)]}
        pencereler.append({
            't1': float(t1), 't2': float(t2),
            't1_kenar': k1, 't2_kenar': k2,
            'max_re': en['max_re'], 't_max_re': en['t'],
            'mod': 'calkanti' if tank_id is not None else 'govde',
            'tank_id': tank_id,
            'mod_frekansi_rad_s': mod['im'],
            'yakinlik_orani': yakinlik,
            'yakinlik_uyarisi': bool(yakinlik is not None and abs(
                yakinlik - 1.0) <= YAKINLIK_BANDI),
            'zeta_min': zmin, 't_zeta_min': t_z,
            'zeta_min_dogrulandi': bool(dogrulandi),
            'zeta_gercek': min(x[3] for x in en['tank_t']),
            'buyume_ussu': float(_trapezoid(rr, tt)),
            'ornek_sayisi': len(w),
            # q̄ tam sabitken ölçüt sonsuzdur (τ_q = ∞): JSON'a null gider
            'dondurulmus_olcut_min': (
                lambda v: v if math.isfinite(v) else None)(
                    min(o['olcut'] for o in w)),
            'sayisal_tutarli': bool(
                an['kararli_ozdeger'] == an['kararli_hurwitz']),
            'tank_araligi': dol,
            'modlar_en_kotu_an': an['modlar'],
            'rijit_modlar_en_kotu_an': an['rijit_modlar'],
            '_i': (a, b),
        })
    rijit = [{'t1': ornekler[a]['t'], 't2': ornekler[b]['t'],
              'max_re': max(o['rijit_max_re'] for o in ornekler[a:b + 1])}
             for a, b in kosular(TARAMA_RIJIT_KARARSIZ)]
    # --- kapsam: hüküm verilebilen süre ve verilemeyen aralıklar -----------
    hukumlu = (TARAMA_KARARLI, TARAMA_CALKANTI_KARARSIZ, TARAMA_RIJIT_KARARSIZ)
    sure = 0.0
    for i in range(n - 1):
        if sinif[i] in hukumlu and sinif[i + 1] in hukumlu:
            sure += ornekler[i + 1]['t'] - ornekler[i]['t']
    bos = []
    for hedef in (TARAMA_RAYDA, TARAMA_GECERSIZ, TARAMA_KAPALI):
        for a, b in kosular(hedef):
            kodlar = []
            if hedef == TARAMA_KAPALI:
                kodlar = sorted({c for o in ornekler[a:b + 1]
                                 for p in o['prm'] for c in p['kod']
                                 if c in K2_KODLARI
                                 and K2_KODLARI[c][0] == SINIF_KAPANMA})
            bos.append({'t1': ornekler[a]['t'], 't2': ornekler[b]['t'],
                        'sebep': hedef, 'kodlar': kodlar})
    bos.sort(key=lambda x: x['t1'])
    kapsam = {
        'yanma_suresi_s': tb,
        'ornek_sayisi': n,
        'sinif_sayilari': {s: sinif.count(s) for s in TARAMA_SINIFLARI},
        'hukum_verilen_sure_s': float(sure),
        'hukum_verilen_oran': float(sure / tb) if tb > 0.0 else 0.0,
        'hukum_verilemeyen': bos,
        'kenar_toleransi_s': TARAMA_KENAR_TOL_S,
        'en_buyuk_ornek_araligi_s': (float(max(
            ornekler[i + 1]['t'] - ornekler[i]['t'] for i in range(n - 1)))
            if n > 1 else None),
    }
    return {'ornekler': ornekler, 'pencereler': pencereler,
            'rijit_pencereler': rijit, 'kapsam': kapsam}


def _bafl_taramasi(bag, ornekler, tasarim, carpan):
    """Bafl dizisinin sönümü eklenince taramanın yinelenmesi (donmuş
    katsayılı model; hüküm verilebilen BÜTÜN örnekler). ``tasarim``:
    {tank dizini: (genişlik oranı, halka yükseklikleri, genlik oranı)};
    ``carpan``: Miles sönümünün çarpanı (1 nominal, 1/bant alt bant)."""
    kararsiz, max_re, kalan, acik_p = 0, -math.inf, [], None
    for o in ornekler:
        if o['kat'] is None:
            acik_p = None
            continue
        tt = []
        for (m1, xi, w1sq, z), kk in zip(o['tank_t'], o['acik_k']):
            if kk in tasarim:
                w, zs, eta = tasarim[kk]
                z = z + carpan * _sa.halka_bafl_dizisi_sonumu(
                    bag.tanklar[kk]['R'], o['prm'][kk]['h'], zs, w, eta)
            tt.append((m1, xi, w1sq, z))
        sinif, re = _siniflandir(o, tt)
        max_re = max(max_re, re)
        if sinif == TARAMA_CALKANTI_KARARSIZ:
            kararsiz += 1
            if acik_p is None:
                acik_p = {'t1': o['t'], 't2': o['t'], 'max_re': re,
                          'buyume_ussu': 0.0, '_t': o['t'], '_re': re}
                kalan.append(acik_p)
            else:
                acik_p['buyume_ussu'] += 0.5 * (re + acik_p['_re']) * (
                    o['t'] - acik_p['_t'])
                acik_p.update(t2=o['t'], max_re=max(acik_p['max_re'], re),
                              _t=o['t'], _re=re)
        else:
            acik_p = None
    for p in kalan:
        del p['_t'], p['_re']
    return {'kararsiz_ornek_sayisi': kararsiz, 'pencere_sayisi': len(kalan),
            'max_re': (max_re if math.isfinite(max_re) else None),
            'pencere_kapandi': kararsiz == 0,
            'kalan_pencereler': kalan}


def bafl_dizisi_onerisi(bag, tarama):
    """Pencerelerin gerektirdiği sönümü sağlayan halka bafl dizisi (A.5;
    Dodge 2000 (2.16), Miles 1958) ve öneriyle taramanın yinelenmesi.

    Hedef = pencerelerin en büyük ζ_min'i. Düz tabanlı dik silindir tankta
    halka genişliği ve aralığı ``slosh_analysis.halka_bafl_dizisi``'nden
    (aralık: en az toplam halka alanı; HRMA seçimi), halkalar pencerelerde
    yüzeyin gezdiği yükseklik aralığına dizilir. Öneri iki düzeyde verilir:
    ``nominal`` (Miles nominal değeri hedefi sağlar) ve ``tutucu`` (bandın
    ALT ucu hedefi sağlar: tasarım hedefi × bant çarpanı). Her biri için
    tarama bafl sönümüyle yinelenir (nominal ve alt bant). Pencere yoksa
    None.
    """
    pencereler = tarama['pencereler']
    if not pencereler:
        return None
    if any(p['zeta_min'] is None for p in pencereler):
        return {'oneri': None, 'sebep': 'ZETA_MIN_UST_SINIR_USTU',
                'zeta_min_ust': ZETA_MIN_UST}
    hedef = max(p['zeta_min'] for p in pencereler)
    if not hedef > 0.0:
        return {'oneri': None, 'sebep': 'SONUM_GEREKSINIMI_YOK'}
    taban = _sa.halka_bafl_dizisi(hedef)
    bant = taban['band_factor']
    eta = taban['amplitude_ratio']

    def duzey(zeta_tasarim):
        d = _sa.halka_bafl_dizisi(zeta_tasarim, eta)
        tanklar, tasarim = [], {}
        for kk, tk in enumerate(bag.tanklar):
            hs = [p['tank_araligi'][tk['tank_id']]['h_m'] for p in pencereler
                  if tk['tank_id'] in p['tank_araligi']]
            if not hs:
                continue
            if not tk['silindir']:
                tanklar.append({'tank_id': tk['tank_id'], 'oneri': None,
                                'sebep': 'GEOMETRI_SILINDIR_DEGIL'})
                continue
            if not d['achievable']:
                tanklar.append({'tank_id': tk['tank_id'], 'oneri': None,
                                'sebep': 'HEDEF_HALKA_DIZISIYLE_SAGLANAMIYOR'})
                continue
            h_ust = max(x[0] for x in hs)
            h_alt = min(x[1] for x in hs)
            s = d['spacing_ratio'] * tk['R']
            adet = max(1, int(math.ceil((h_ust - h_alt) / s)))
            zs = [h_ust - j * s for j in range(1, adet + 1)]
            dusen = [z for z in zs if not z > 0.0]
            zs = [z for z in zs if z > 0.0]
            tasarim[kk] = (d['width_ratio'], zs, eta)
            tanklar.append({'tank_id': tk['tank_id'], 'sebep': None, 'oneri': {
                'width_ratio': d['width_ratio'],
                'width_m': d['width_ratio'] * tk['R'],
                'spacing_ratio': d['spacing_ratio'],
                'spacing_m': s,
                'blocked_area_ratio': d['blocked_area_ratio'],
                'halka_sayisi': len(zs),
                'halka_yukseklikleri_m': zs,
                'yuzey_araligi_m': [h_ust, h_alt],
                'taban_altina_dusen_halka': len(dusen)}})
        return {
            'zeta_tasarim': zeta_tasarim, 'tanklar': tanklar,
            'yeniden_tarama': {
                'nominal': _bafl_taramasi(bag, tarama['ornekler'], tasarim, 1.0),
                'alt_bant': _bafl_taramasi(bag, tarama['ornekler'], tasarim,
                                           1.0 / bant)}}
    nominal = duzey(hedef)
    tutucu = duzey(hedef * bant)
    return {
        'zeta_hedef': hedef,
        'hedef_kaynagi': 'pencerelerin en büyük zeta_min değeri',
        'genlik_orani': eta, 'bant_carpani': bant,
        'aralik_orani': taban['spacing_ratio'],
        'nominal': nominal, 'tutucu': tutucu,
        'pencere_kapaniyor': nominal['yeniden_tarama']['nominal'][
            'pencere_kapandi'],
        'pencere_kapaniyor_alt_bantta': tutucu['yeniden_tarama']['alt_bant'][
            'pencere_kapandi'],
        'beyanlar': ['SONUM_TOPLANABILIRLIGI', 'BAFL_GECERLILIK_DISI'],
        'kaynak': (
            'Ring-baffle damping: Miles (1958) as given in Dodge 2000 Eq. '
            '(2.16); design wave amplitude eta/R = %g (HRMA choice); ring '
            'spacing s/R = 3/(2*4.6) minimises the total ring area per unit '
            'tank length for a given target (HRMA choice); the +/- factor-%g '
            'band is an HRMA choice (scatter of Dodge 2000 Fig. 2.7). Ring '
            'depths smaller than the wave amplitude and fill ratios h/R <= 2 '
            'are outside the stated range of the correlation (declared). '
            'The re-scan repeats the frozen-coefficient burn scan with the '
            'baffle damping added to the wall damping.' % (eta, bant)),
    }


def dogrusal_sinir_ozeti(sol_t, ceper_orani, tank_ids):
    """Zaman alanı çeper genliği ⟷ doğrusal kuram sınırı (Dodge s. 33).

    Döner: (özet sözlüğü, geçerlilik maskesi (N,)). Maske ilk aşım anından
    (herhangi bir tank) SONRA False'tur: o andan sonra bağlaşık çözümün
    genlik, kuvvet, moment ve yörünge sayıları doğrusal modelin geçerlilik
    alanının dışındadır ve gerçek değer gibi sunulmaz (kod
    ``DOGRUSAL_GECERLILIK_DISI``)."""
    sinir = _tablo.GENLIK_DOGRUSAL_SINIR_ORANI
    N = sol_t.size
    tanklar, t_ilk, tid_ilk = [], None, None
    for k, tid in enumerate(tank_ids):
        o = ceper_orani[k]
        ok = np.isfinite(o)
        asim = np.flatnonzero(ok & (np.where(ok, o, 0.0) > sinir))
        kayit = {'tank_id': tid, 'asildi': bool(asim.size),
                 't_ilk_asim_s': float(sol_t[asim[0]]) if asim.size else None,
                 'max_eta_R': (float(np.max(o[ok])) if ok.any() else None),
                 't_max_eta_R_s': (float(sol_t[ok][int(np.argmax(o[ok]))])
                                   if ok.any() else None)}
        tanklar.append(kayit)
        if asim.size and (t_ilk is None or kayit['t_ilk_asim_s'] < t_ilk):
            t_ilk, tid_ilk = kayit['t_ilk_asim_s'], tid
    gecerli = np.ones(N, dtype=bool) if t_ilk is None else (sol_t < t_ilk)
    deger = [x['max_eta_R'] for x in tanklar if x['max_eta_R'] is not None]
    once = None
    if deger:
        m = ceper_orani[:, gecerli]
        m = m[np.isfinite(m)]
        once = float(np.max(m)) if m.size else None
    ozet = {
        'asildi': t_ilk is not None,
        'sinir': sinir,
        'kaynak': DOGRUSAL_SINIR_KAYNAGI,
        'max_eta_R': max(deger) if deger else None,
        'max_eta_R_gecerlilik': (DOGRUSAL_GECERLILIK_DISI if t_ilk is not None
                                 else 'GECERLI'),
        'max_eta_R_sinir_oncesi': once,
        't_ilk_asim_s': t_ilk, 'tank_id_ilk_asim': tid_ilk,
        'tanklar': tanklar,
        'asim_sonrasi_kod': (DOGRUSAL_GECERLILIK_DISI if t_ilk is not None
                             else None),
        'etkilenen_alanlar': (list(DOGRUSAL_SINIRDAN_ETKILENEN)
                              if t_ilk is not None else []),
    }
    return ozet, gecerli


def cozum_ciktilari(cozucu, sol_t, sol_y, out, t_max, max_step):
    """``solve()`` çıktısına çalkantı alanları (§B.3.3, §B.5)."""
    bag = cozucu._slosh
    n = bag.n
    if n == 0:
        # Liste verildi ama hiçbir tank bağlanamadı (ör. m_t yok): uydurma
        # çalkantı yok, gerekçe adıyla.
        u = uygulanmaz_ciktisi('TANK_BAGLANMADI')
        u['tanks_not_coupled'] = list(bag.baglanmayan)
        return {'slosh_stability': u}
    N = sol_t.size
    # --- zaman alanı: her çözüm örneğinde RHS ayrıntısı -------------------
    eta = np.full((n, 2, N), np.nan)
    kuvvet = np.full((n, 2, N), np.nan)
    moment = np.full((n, 2, N), np.nan)
    aci = np.full((n, N), np.nan)
    ceper_orani = np.full((n, N), np.nan)
    acik = np.zeros((n, N), dtype=bool)
    m1_s = np.full((n, N), np.nan)
    L1_s = np.full((n, N), np.nan)
    w1_s = np.full((n, N), np.nan)
    zeta_s = np.full((n, N), np.nan)
    dol_s = np.full((n, N), np.nan)
    x1_s = np.full((n, N), np.nan)
    f_x = np.full(N, np.nan)
    rho_s = np.full((n, N), np.nan)
    kodlar = [set() for _ in range(n)]
    tb = float(cozucu.t_burn)
    siniflar = []          # yanma içi örneklerin tarama sınıfları
    for j in range(N):
        if sol_t[j] < tb:
            # Yanma içi örnek: tarama sınıfı ve zaman alanı ayrıntısı AYNI
            # RHS çağrısından (dondurulmus_katsayilar → ayrıntı kaydı).
            o, kk = ornek_siniflandir(cozucu, float(sol_t[j]), sol_y[:, j])
            o['j'] = j
            siniflar.append(o)
            kay = {'f_O': (kk['f_x'],), 'prm': kk['prm']}
        else:
            bag.kayit = {}
            try:
                cozucu._derivatives(float(sol_t[j]), sol_y[:, j])
                kay = bag.kayit
            finally:
                bag.kayit = None
        f_x[j] = float(kay['f_O'][0])
        et, etd = bag.ayir(sol_y[:, j])
        for k, p in enumerate(kay['prm']):
            kodlar[k].update(p['kod'])
            if not p['acik']:
                continue
            acik[k, j] = True
            eta[k, :, j] = et[k]
            F = p['m1'] * (p['w1sq'] * et[k] + p['c'] * etd[k])
            kuvvet[k, :, j] = F
            # O'ya göre moment, gövde (y, z) bileşenleri: ξ e_x × F +
            # (ρ_k × (−m1 f_x e_x)); düzlemsel (B-4) R satırıyla aynı kural.
            moment[k, 0, j] = -(p['xi'] * F[1] + p['m1'] * f_x[j] * et[k][1])
            moment[k, 1, j] = p['xi'] * F[0] + p['m1'] * f_x[j] * et[k][0]
            aci[k, j] = math.degrees(float(np.hypot(*et[k])) / p['L1'])
            R = bag.tanklar[k]['R']
            ceper_orani[k, j] = float(np.hypot(*et[k])) / p['Gamma1'] / R
            m1_s[k, j], L1_s[k, j] = p['m1'], p['L1']
            w1_s[k, j], zeta_s[k, j] = math.sqrt(p['w1sq']), p['zeta']
            dol_s[k, j], x1_s[k, j] = p['doluluk'], p['x1']
            rho_s[k, j] = p['rho']
    # yarı-durağanlık göstergesi (§B.3.7) — koşu verisinden sonlu fark
    yari = np.full((n, N), np.nan)
    for k in range(n):
        ok = acik[k]
        if ok.sum() >= 3:
            tt = sol_t[ok]
            dlm = np.abs(np.gradient(np.log(m1_s[k, ok]), tt))
            dll = np.abs(np.gradient(np.log(L1_s[k, ok]), tt))
            yari[k, ok] = np.maximum(dlm, dll) / w1_s[k, ok]
            if np.any(yari[k, ok] > YARI_DURAGANLIK_ESIGI):
                kodlar[k].add('YARI_DURAGAN_DEGIL')
        if np.any(ceper_orani[k][acik[k]] > _tablo.GENLIK_DOGRUSAL_SINIR_ORANI):
            kodlar[k].add('GENLIK_DOGRUSAL_SINIR_DISI')
    # --- rijit karşılaştırma koşusu (§B.5 "tutuma etki") ------------------
    rij = copy.copy(cozucu)
    rij._slosh = None
    rout = rij.solve(t_max=t_max, max_step=max_step)
    q_c = sol_y[6:10]
    q_r = rout['quaternion']
    tr = rout['time']
    ex_c = _govde_x(q_c)
    ex_r = np.vstack([np.interp(sol_t, tr, _govde_x(q_r)[i]) for i in range(3)])
    kapsar = (sol_t >= tr[0]) & (sol_t <= tr[-1])
    dtheta = np.full(N, np.nan)
    cosang = np.clip(np.sum(ex_c * ex_r, axis=0)
                     / np.linalg.norm(ex_r, axis=0), -1.0, 1.0)
    dtheta[kapsar] = np.degrees(np.arccos(cosang[kapsar]))
    dalpha = np.full(N, np.nan)
    dalpha[kapsar] = (out['alpha_deg'][kapsar]
                      - np.interp(sol_t[kapsar], tr, rout['alpha_deg']))
    # --- dört an ----------------------------------------------------------
    an_t = _an_zamanlari(cozucu, sol_t, out)
    ucus = out['flight_verdict']['flight']
    analizler = {}
    for ad in ANLAR:
        analizler[ad] = _an_degerlendir(cozucu, ad, an_t[ad], sol_t, sol_y,
                                        out, ucus)
    # --- yanma boyunca tarama + genel hüküm (3.0.7; karar 16 Kas) ---------
    # Dört an raporlama içindir; GENEL hüküm taramanın en kötü penceresinden.
    yakinsadi = bool(out.get('converged', False))
    tarama = yanma_taramasi(cozucu, sol_t, sol_y, siniflar) if yakinsadi \
        else {'ornekler': [], 'pencereler': [], 'rijit_pencereler': [],
              'kapsam': None}
    for p in tarama['pencereler']:
        a, b = p.pop('_i')
        p['_ornek_araligi'] = (a, b)
        js = [tarama['ornekler'][i]['j'] for i in range(a, b + 1)]
        g = yari[:, js]
        g = g[np.isfinite(g)]
        p['yari_duraganlik_gostergesi_max'] = float(g.max()) if g.size else None
        p['beyanlar'] = (['YARI_DURAGAN_DEGIL'] if g.size and g.max()
                         > YARI_DURAGANLIK_ESIGI else [])
        if not p['zeta_min_dogrulandi']:
            p['beyanlar'].append('ZETA_MIN_DOGRULANAMADI')
    # V307/UÇUŞ-GÖVDE (kalem 5): doğrusal sınırın ilk aşımı pencerelere
    # işlenir (aşımdan sonraki örneklerin uçuş durumu geçerlilik dışı
    # koşudandır) ve hüküm o işaretlerle verilir.
    tank_ids = [tk['tank_id'] for tk in bag.tanklar]
    dogrusal, gecerli_maske = dogrusal_sinir_ozeti(sol_t, ceper_orani, tank_ids)
    _pencere_sinir_isaretleri(tarama, dogrusal['t_ilk_asim_s'])
    hukum, gerekce, sebep = _tarama_hukmu(tarama, out, ucus)
    orn = tarama['ornekler']
    tarama_araligi = ({'t_bas_s': orn[0]['t'], 't_son_s': orn[-1]['t']}
                      if orn else None)
    ucus_sonu = {
        'ucus': ucus, 'apojeye_vardi': bool(ucus == 'apogee'),
        't_son_s': out['flight_verdict'].get('t_end_s'),
        'yanma_suresi_s': out['flight_verdict'].get('burn_time_s'),
    }
    dort_an = []
    for ad in ANLAR:
        a = analizler[ad]
        t_a = a.get('t')
        dort_an.append({
            'an': ad, 't': t_a, 'hukum': a['hukum'], 'sebep': a.get('sebep'),
            'max_re': (max(m['re'] for m in a['modlar'])
                       if a.get('modlar') else None),
            'zeta_min': a.get('zeta_min'),
            'pencere_icinde': bool(t_a is not None and any(
                p['t1'] <= t_a <= p['t2'] for p in tarama['pencereler']))})
    bafl = bafl_dizisi_onerisi(bag, tarama)      # pencere yoksa None
    beyanlar = ['DONMUS_MODELDE_YERCEKIMI_KINEMATIGI_YOK']
    kapsam = tarama['kapsam']
    if kapsam is not None and kapsam['hukum_verilemeyen']:
        beyanlar.append('TARAMA_KISMI_KAPSAM')
    if dogrusal['asildi']:
        beyanlar.append('GENLIK_DOGRUSAL_SINIR_DISI')
    for p in tarama['pencereler']:
        for c in p['beyanlar']:
            if c not in beyanlar:
                beyanlar.append(c)
    beyan_kodlari = {c for c, v in K2_KODLARI.items() if v[0] == SINIF_BEYAN}
    for k, tk in enumerate(bag.tanklar):
        for c in sorted((kodlar[k] | set(tk['beyan'])) & beyan_kodlari):
            if c not in beyanlar:
                beyanlar.append(c)
    tarama_serisi = {
        't': [o['t'] for o in orn],
        'sinif': [o['sinif'] for o in orn],
        'max_re': [o['max_re'] for o in orn],
        'rijit_max_re': [o['rijit_max_re'] for o in orn],
    }
    tank_ozet = []
    for k, tk in enumerate(bag.tanklar):
        tank_ozet.append({
            'tank_id': tk['tank_id'], 'x_tank_taban_m': tk['x_taban'],
            'yontem': tk['tablo'].yontem,
            'kutle_kaynagi': ('itkiyle_orantili' if tk['t_m'].size == 1
                              else 'verilen_seri'),
            'zeta_ek': tk['zeta_ek'],
            'kodlar': sorted(kodlar[k] | set(tk['beyan'])),
        })
    return {
        'slosh_tank_ids': [tk['tank_id'] for tk in bag.tanklar],
        'slosh_tanks_not_coupled': list(bag.baglanmayan),
        'slosh_eta': eta,
        'slosh_active': acik,
        'slosh_angle_deg': aci,
        'slosh_wall_amplitude_ratio': ceper_orani,
        'slosh_force_body': kuvvet,
        'slosh_moment_body': moment,
        'slosh_quasi_steady_indicator': yari,
        'slosh_params_t': {
            'doluluk': dol_s, 'm1_kg': m1_s, 'L1_m': L1_s,
            'omega1_rad_s': w1_s, 'zeta': zeta_s, 'x1_m': x1_s,
            'rho_kg_m3': rho_s},
        'slosh_linear_valid': gecerli_maske,
        'g_eff': f_x,
        'slosh_rigid_comparison': {
            'delta_theta_deg': dtheta, 'delta_alpha_deg': dalpha,
            'apogee': rout['apogee'], 'max_alpha_deg': rout['max_alpha_deg'],
            'flight_verdict': rout['flight_verdict'],
            # V307/UÇUŞ-GÖVDE (kalem 6): sınır aşılınca bağlaşık koşunun
            # tüm-uçuş sayıları yayımlanmaz; rijit koşu "çalkantısız referans
            # koşu" olarak aynı alanlarla yanında durur.
            'apogee_time': rout.get('apogee_time'),
            'max_speed': rout.get('max_speed'),
            'max_mach': rout.get('max_mach'),
            'lateral_drift_at_end': rout.get('lateral_drift_at_end'),
            # ONARIM-ÇALK (ONARIM-UÇUŞ DEVİR, M7-UCUS-16): çözücü apojeyi
            # yayımlamadığında nedeni (ör. negatif statik marj) referans
            # koşuyla birlikte taşınır; alan yoksa None.
            'apogee_withheld_because': rout.get('apogee_withheld_because'),
        },
        'slosh_stability': {
            # --- hüküm sözleşmesi (3.0.7; arayüz bunu tüketir) -------------
            'genel_hukum': hukum, 'gerekce_kodu': gerekce,
            # V307/UÇUŞ-GÖVDE (kalem 5): hükmün kapsamı, uçuşun nasıl ve ne
            # zaman bittiği (hükümden AYRI bilgi) ve taramanın aralığı.
            'hukum_kapsami': {'kod': HUKUM_KAPSAMI_KODU,
                              'gerekce': HUKUM_KAPSAMI_GEREKCE},
            'ucus_sonu': ucus_sonu,
            'pencereler': tarama['pencereler'],
            'rijit_pencereler': tarama['rijit_pencereler'],
            'dort_an': dort_an,
            'dogrusal_sinir': dogrusal,
            'bafl_onerisi': bafl,
            'beyanlar': beyanlar,
            'tarama': {'kapsam': kapsam, 'seri': tarama_serisi,
                       're_esigi_bagil': TARAMA_RE_ESIGI_BAGIL,
                       'aralik': tarama_araligi},
            # --- K2 alanları (korundu; 'hukum' artık genel_hukum ile aynı) -
            'hukum': hukum, 'sebep': sebep, 'anlar': analizler,
            'tanklar': tank_ozet,
            'kapsam_disi': {'kod': KAPSAM_DISI_KODU,
                            'gerekce': KAPSAM_DISI_GEREKCE},
            'esikler': {
                'ray_statik_egim_siniri_deg': RAY_STATIK_EGIM_SINIRI_DEG,
                'yari_duraganlik_esigi': YARI_DURAGANLIK_ESIGI,
                'dondurulmus_katsayi_esigi': DONDURULMUS_KATSAYI_ESIGI,
                'zeta_min_ust': ZETA_MIN_UST,
                'yakinlik_bandi': YAKINLIK_BANDI,
                'genlik_dogrusal_sinir_orani': _tablo.GENLIK_DOGRUSAL_SINIR_ORANI,
            },
            'basis': (
                'Linearised pitch-plane model (B-5)-(B-7) with frozen '
                'coefficients, evaluated at every sample of the coupled '
                'solution during the burn; the overall verdict is that of '
                'the worst window of the scan (consecutive samples whose '
                'coupled roots are unstable while the rigid body is stable), '
                'window edges refined by bisection between neighbouring '
                'samples. The four instants (lift-off, rail exit, peak '
                'dynamic pressure during the burn, burnout) are reported '
                'for reference. The yaw plane is identical by axial symmetry '
                'and is not repeated; roll is not modelled. Eigenvalues are '
                'cross-checked with the Hurwitz determinants (NASA SP-106 '
                'Eqs. 7.32-7.35) at the four instants and at the worst '
                'sample of each window; zeta_min is the smallest common '
                'slosh damping ratio that places all roots in the left '
                'half-plane (per window: at every sample of the window). '
                'The mechanism is the danger-zone / frequency-coalescence '
                'instability of a vehicle whose lateral force follows its '
                'attitude (Bauer, NASA SP-106 Ch. 7, Eqs. 7.42-7.45 and '
                'Fig. 7.13, with the aerodynamic normal force in the role '
                'of the attitude-control force).'),
        },
    }


def _govde_x(q):
    q = np.atleast_2d(q)
    nrm = np.linalg.norm(q, axis=0)
    w, x, y, z = q / nrm
    return np.vstack([1 - 2 * (y * y + z * z), 2 * (x * y + w * z),
                      2 * (x * z - w * y)])


def _an_degerlendir(cozucu, ad, t_an, sol_t, sol_y, out, ucus):
    """Bir anın analizi ve tek durumlu hükmü (§B.5 hüküm kuralları)."""
    if not out.get('converged', False):
        return {'t': t_an, 'hukum': HUKUM_YOK, 'sebep': 'COZUM_YAKINSAMADI'}
    if t_an is None or t_an > float(sol_t[-1]):
        return {'t': t_an, 'hukum': HUKUM_YOK, 'sebep': 'AN_ULASILMADI'}
    # ad, kalkış dışındaki anlarda yalnız etiket; analiz biçimi u'ya bağlı
    y = _durum_an(t_an, sol_t, sol_y, cozucu.t_burn)
    k = dondurulmus_katsayilar(cozucu, t_an, y)
    acik = [p for p in k['prm'] if p['acik']]
    kayit = {'t': float(t_an), 'katsayilar': {
        x: k[x] for x in ('m', 'I', 'x_cg', 'u', 'u_dot', 'rho', 'qbar', 'mach',
                          'cn_alpha', 'x_cp', 'N_alpha', 'M_alpha', 'M_q', 'f_x',
                          'dqbar_dt', 'altitude_m')},
        'tanklar': [{'acik': p['acik'], 'm1_kg': p['m1'], 'xi_m': p['xi'],
                     'omega1_rad_s': (math.sqrt(p['w1sq']) if p['acik'] else None),
                     'zeta': p['zeta'], 'L1_m': p['L1'], 'doluluk': p['doluluk'],
                     'kodlar': list(p['kod'])} for p in k['prm']]}
    if not acik:
        kayit.update(hukum=HUKUM_YOK, sebep='CALKANTI_KAPALI')
        return kayit
    tank_t = [(p['m1'], p['xi'], p['w1sq'], p['zeta']) for p in acik]
    zeta_g = min(p['zeta'] for p in acik)
    if ad == 'kalkis' or k['u'] <= 0.0:
        A = bosluk_modeli(k['m'], k['I'], k['f_x'], tank_t)
        lam = np.linalg.eigvals(A)
        kayit['bosluk_ozdegerleri'] = _kok_listesi(lam)
        kayit['omega_c_rad_s'] = sorted(
            float(abs(z.imag)) for z in lam if z.imag > 0.0)
        kayit.update(hukum=HUKUM_YOK, sebep='KALKIS_ANI_ALFA_TANIMSIZ')
        return kayit
    an = an_analizi(k['m'], k['I'], k['u'], k['u_dot'], k['N_alpha'],
                    k['M_alpha'], k['M_q'], k['f_x'], tank_t, zeta_g)
    kayit.update(an)
    gecerli, olcut = _dondurulmus_gecerli(k)
    kayit['dondurulmus_olcut'] = olcut
    if ucus != 'apogee':
        kayit.update(hukum=HUKUM_YOK, sebep='UCUS_APOJEYE_VARMADI',
                     ucus=ucus)
        return kayit
    if not gecerli:
        kayit.update(hukum=HUKUM_YOK, sebep='DONDURULMUS_KATSAYI_GECERSIZ')
        return kayit
    if an['kararli_ozdeger'] != an['kararli_hurwitz']:
        kayit.update(hukum=HUKUM_YOK, sebep='SAYISAL_TUTARSIZLIK')
        return kayit
    if not an['rijit_kararli']:
        kayit.update(hukum=HUKUM_RIJIT_KARARSIZ, sebep=None)
    elif not an['kararli_ozdeger']:
        kayit.update(hukum=HUKUM_CALKANTI_KARARSIZ, sebep=None)
        kayit['bafl_onerisi'] = _bafl_onerisi(cozucu, k, an['zeta_min'])
    else:
        kayit.update(hukum=HUKUM_KARARLI, sebep=None)
    return kayit


def _bafl_onerisi(cozucu, k, zmin):
    """ζ_min'i hedef sönüm alan bafl önerisi (A.5; Dodge (2.16a)) — yalnız
    düz tabanlı dik silindirde; değilse gerekçeli None."""
    if zmin is None:
        return {'oneri': None, 'sebep': 'ZETA_MIN_UST_SINIR_USTU'}
    out = []
    for tk, p in zip(cozucu._slosh.tanklar, k['prm']):
        if not p['acik']:
            continue
        if not tk['silindir']:
            out.append({'tank_id': tk['tank_id'], 'oneri': None,
                        'sebep': 'GEOMETRI_SILINDIR_DEGIL'})
            continue
        h = p['doluluk'] * tk['V_ic'] / (math.pi * tk['R'] ** 2)
        ts = _sa.CylindricalTankSlosh(tk['R'], h, g_eff=k['f_x'])
        out.append({'tank_id': tk['tank_id'],
                    'oneri': ts.recommend_baffle(target_damping=zmin)})
    return out


def _pencere_sinir_isaretleri(tarama, t_asim):
    """Pencereleri doğrusal sınırın ilk aşımına göre işaretle (yerinde).

    Her pencereye: ``sinir_asimi_konumu`` (:data:`SINIR_KONUMLARI`),
    ``ornek_sayisi_sinir_oncesi`` (ilk aşımdan önceki örnek sayısı) ve
    ``buyume_ussu_sinir_oncesi`` (büyüme üssünün ilk aşımdan önceki örneklere
    kadar olan kısmı; pencerenin tamamı aşımdan sonraysa None). İlk aşımdan
    SONRAKİ örneklerin uçuş durumu (hız, dinamik basınç, tutum) doğrusal
    modelin geçerlilik alanı dışındaki bağlaşık koşudan gelir; o örneklerin
    penceresi aynı kanıt ağırlığını taşımaz."""
    orn = tarama['ornekler']
    for p in tarama['pencereler']:
        a, b = p.pop('_ornek_araligi')
        w = orn[a:b + 1]
        if t_asim is None:
            p.update(sinir_asimi_konumu=SINIR_KONUM_ASILMADI,
                     ornek_sayisi_sinir_oncesi=len(w),
                     buyume_ussu_sinir_oncesi=p['buyume_ussu'])
            continue
        once = [o for o in w if o['t'] < t_asim]
        if len(once) == len(w):
            p.update(sinir_asimi_konumu=SINIR_KONUM_ONCE,
                     ornek_sayisi_sinir_oncesi=len(w),
                     buyume_ussu_sinir_oncesi=p['buyume_ussu'])
        elif not once:
            p.update(sinir_asimi_konumu=SINIR_KONUM_SONRA,
                     ornek_sayisi_sinir_oncesi=0,
                     buyume_ussu_sinir_oncesi=None)
        else:
            # Pencerenin başından son geçerli örneğe kadar (aynı yamuk
            # kuralı; baş kenarı pencere kaydındaki gibi).
            tt = np.array([p['t1']] + [o['t'] for o in once])
            rr = np.array([0.0 if p['t1_kenar'] == KENAR_ISARET_DEGISIMI
                           else once[0]['max_re']]
                          + [o['max_re'] for o in once])
            p.update(sinir_asimi_konumu=SINIR_KONUM_KAPSIYOR,
                     ornek_sayisi_sinir_oncesi=len(once),
                     buyume_ussu_sinir_oncesi=float(_trapezoid(rr, tt)))


def _tarama_hukmu(tarama, out, ucus):
    """GENEL hüküm (tek durum) — yanma boyunca taramanın en kötü
    penceresinden (3.0.7; karar 16 Kas). Döner: (hüküm, gerekçe kodu,
    sebep listesi).

    Öncelik K2 ile aynı: ÇALKANTI KAYNAKLI KARARSIZLIK > RİJİT GÖVDE KARARSIZ
    > KARARLI. Çözüm yakınsamadıysa hüküm yok. En kötü örnekte özdeğer ile
    Hurwitz tutarsızsa hüküm yok. Hüküm verilebilen hiç örnek yoksa hüküm
    yok; sebep, verilemeyen aralıkların sınıflarıdır.

    V307/UÇUŞ-GÖVDE (kalem 5; ÇALKANTI-KARARLILIK KARAR 4 → (b)): uçuşun
    apojeye varmaması YALNIZ ``KARARLI`` hükmünü engeller. Tarama pencere
    bulduysa hüküm verilir: kararsızlık aracı takla attıracak kadar büyüdüğü
    durumda yazılım susmaz. Hüküm doğrusal taramanın bulgusudur; uçuşun neden
    sona erdiğini söylemez (``ucus_sonu`` ayrı alandır). Hükmü taşıyan bütün
    pencereler doğrusal sınırın ilk aşımından sonraki örneklerden geliyorsa
    gerekçe kodu ``GEREKCE_PENCERE_SINIR_SONRASI`` olur."""
    if not out.get('converged', False):
        return HUKUM_YOK, 'COZUM_YAKINSAMADI', ['COZUM_YAKINSAMADI']
    pencereler = tarama['pencereler']
    if pencereler:
        if not all(p['sayisal_tutarli'] for p in pencereler):
            return HUKUM_YOK, 'SAYISAL_TUTARSIZLIK', ['SAYISAL_TUTARSIZLIK']
        if all(p.get('sinir_asimi_konumu') == SINIR_KONUM_SONRA
               for p in pencereler):
            return HUKUM_CALKANTI_KARARSIZ, GEREKCE_PENCERE_SINIR_SONRASI, []
        return HUKUM_CALKANTI_KARARSIZ, GEREKCE_PENCERE, []
    if tarama['rijit_pencereler']:
        return HUKUM_RIJIT_KARARSIZ, GEREKCE_RIJIT, []
    if ucus != 'apogee':
        return HUKUM_YOK, 'UCUS_APOJEYE_VARMADI', ['UCUS_APOJEYE_VARMADI']
    sayi = tarama['kapsam']['sinif_sayilari']
    if sayi[TARAMA_KARARLI] > 0:
        return HUKUM_KARARLI, GEREKCE_KARARLI, []
    return (HUKUM_YOK, GEREKCE_DEGERLENDIRILEMEDI,
            sorted(s for s in (TARAMA_RAYDA, TARAMA_GECERSIZ, TARAMA_KAPALI)
                   if sayi[s] > 0))


def uygulanmaz_ciktisi(sebep):
    """Tank yok (katı motor) ya da hiçbir tank bağlanmadı."""
    return {'hukum': HUKUM_UYGULANMAZ, 'sebep': [sebep],
            # hüküm sözleşmesi (3.0.7): aynı alanlar, boş içerik
            'genel_hukum': HUKUM_UYGULANMAZ, 'gerekce_kodu': sebep,
            'pencereler': [], 'rijit_pencereler': [], 'dort_an': [],
            'dogrusal_sinir': None, 'bafl_onerisi': None, 'beyanlar': [],
            'tarama': None, 'ucus_sonu': None,
            'hukum_kapsami': {'kod': HUKUM_KAPSAMI_KODU,
                              'gerekce': HUKUM_KAPSAMI_GEREKCE},
            'kapsam_disi': {'kod': KAPSAM_DISI_KODU,
                            'gerekce': KAPSAM_DISI_GEREKCE}}


# --- Kısmi bağlama (3.0.7 ONARIM-ÇALK, M7-CALK-15) -------------------------


def kismi_baglama_hukmu(st, baglanmayan):
    """Bağlanmayan tank varken hükmü sınırlar (YERİNDE; döner: ``st``).

    ``baglanmayan``: 6-DOF'a bağlanmayan tankların kimlikleri (K4 raporunda
    ``durum != BAGLANDI`` olanlar ve çözücünün kendi bağlamadığı tanklar).
    Boşsa hüküm değişmez. Doluysa:

    - ``baglanmayan_tanklar`` alanı kimlikleri adıyla taşır ve beyanlara
      :data:`BEYAN_KISMI_BAGLAMA` eklenir (hüküm hangi tankları kapsıyor);
    - ``KARARLI`` hükmü verilmez → ``HUKUM_YOK``, gerekçe
      :data:`GEREKCE_KISMI_BAGLAMA` (bağlanmayan tankın modu modelde yok);
    - kararsızlık hükümleri (çalkantı ya da rijit gövde) KALIR: bağlanan
      tanklarla bulunan kararsızlık, eksik tankla ortadan kalkmış sayılmaz;
    - hiçbir tank bağlanmadıysa (``UYGULANMAZ``) dokunulmaz.
    """
    ids = [str(t) for t in (baglanmayan or [])]
    # Hiçbir tank bağlanmadıysa (UYGULANMAZ) "kısmi" değildir: uçuş rijittir
    # ve ekran bunu zaten söyler; dokunulmaz.
    if not ids or not isinstance(st, dict) or \
            st.get('genel_hukum') == HUKUM_UYGULANMAZ:
        return st
    st['baglanmayan_tanklar'] = ids
    beyanlar = st.get('beyanlar')
    if isinstance(beyanlar, list) and BEYAN_KISMI_BAGLAMA not in beyanlar:
        beyanlar.append(BEYAN_KISMI_BAGLAMA)
    if st.get('genel_hukum') == HUKUM_KARARLI:
        st['genel_hukum'] = st['hukum'] = HUKUM_YOK
        st['gerekce_kodu'] = GEREKCE_KISMI_BAGLAMA
        st['sebep'] = [SEBEP_KISMI_BAGLAMA]
    return st
