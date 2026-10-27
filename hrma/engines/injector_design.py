# -*- coding: utf-8 -*-
"""Enjektör tasarım modülü — hibrit (yalnız oksitleyici) ve sıvı (çift yakıt).

TEK gerçek kaynak: docs/10_Enjektor_ARGE.md (2026-07-13 ARGE + API sözleşmesi).
Bu modül saf hesaptır: Flask/HTTP içermez; `design_injector(spec)` sözlük alır,
sözlük döner (şema: spec Bölüm B.2).

Ana fizik:
- Orifis akışı: ṁ = Cd·A·√(2ρΔP) (SPI; Sutton & Biblarz 9. baskı Böl. 8,
  NASA SP-8089).
- Kendinden basınçlı N₂O: Dyer NHNE — ṁ = (κ·ṁ_SPI + ṁ_HEM)/(1+κ),
  κ = √((P₁−P₂)/(P_v−P₂)) (Dyer/Doran/Dunn/Zilliac AIAA 2007-5702;
  deneysel doğrulama ±%15). Doyma özellikleri tank_blowdown.N2OSaturation
  ile paylaşılır; izentropik HEM için doyma entropisi bu modülde tablo olarak
  tutulur (CoolProp/Span-Wagner'dan üretildi, 2026-07-13).
- Atomizasyon SMD: Elkotb 1982 (düz orifis), Lefebvre (basınç-swirl),
  We^(−1/3) eğilimli impinging (C_imp=2.6, kalibre edilebilir).
  Ortam yoğunluğu HER ZAMAN oda gazı yoğunluğudur.
- Kararlılık: ΔP/Pc ≥ 0.15-0.20 chug kuralı (SP-8089); Nurick kavitasyon
  sayısıyla hydraulic-flip bayrağı; N₂O besleme kuplajı notu (NTRS 20190001326).
"""

from typing import Dict

import numpy as np

from hrma.constants import (R_UNIVERSAL, PA_PER_BAR, ORIFICE_D_BAND_MM,
                            ORIFICE_D_BAND_SOURCE)
from hrma.analysis.tank_blowdown import N2OSaturation, N2O_T_CRIT
# Chug ΔP/Pc eşiği: TEK SAYISAL TANIM acoustic_modes'tadır (künye hükmü
# CHUG_THRESHOLD_SOURCE içinde). Bu modül sayıyı TEKRAR YAZMAZ, ithal eder.
from hrma.analysis.acoustic_modes import (
    CHUG_DP_RATIO_MINIMUM,
    CHUG_DP_RATIO_RECOMMENDED,
)


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: sabit metin YERİNE ``{code, params, severity}``.

    Dil tamamen frontend'e taşınır; ``TF(code, params)`` metni kurar.
    ``severity`` ∈ {"critical", "warning", "info"} — uyarılar
    "warning"/"critical", varsayımlar (assumptions) "info". Kod kataloğu:
    ``docs/v262_specs/D_codes_injector.md``.
    """
    return {"code": code, "params": params, "severity": severity}


# Devre/akım etiketleri — YALNIZ ValueError metinleri için (hata kanalı hâlâ
# metin döndürür; uyarı/varsayım kanalı {code} kullanır).
_CIRCUIT_LABEL = {'ox': 'oxidizer', 'fuel': 'fuel'}
_GAS_POST_LABEL = {'ox': 'oxidizer post', 'fuel': 'fuel post'}

# ---------------------------------------------------------------------------
# Modül sabitleri (ARGE raporu A.2-A.9)
# ---------------------------------------------------------------------------

# ÖH KU H-8 (KU-27, 6 Eki 2026) — UZUN KESKİN ORİFİS SATIRI: YALNIZ BEYAN.
# Satır L/D > 5 için 0,84 verir ve eski açıklaması "sürtünme artar" diyordu:
# sürtünme Cd'yi DÜŞÜRÜR, yani satır kendi gerekçesiyle çelişiyordu. NASA
# SP-8089 (Gill & Nurick 1976) Şekil 15, s. 43 (keskin kenarlı kısa tüp, tam
# dolu akış; ref. 72): Cd L/d 1'de ~0,75, 2'de ~0,81, 3'te ~0,825 platoya
# oturur; uzun tüpte sürtünme ancak düşürür → doğrusu ≤ 0,82 (SP-S1 A2).
# DEĞER DEĞİŞTİRİLMEDİ: 0,82'ye çekmek L/D > 5 yolunda delik çapını +%1,21,
# alanı +%2,44 değiştiriyor (ölçüldü, docs/scofield/raw/OH/KU/h-q5/
# ld5_fark.txt) ve mevcut bir sözleşme testinin ölçülmüş L/D beklentisini
# kırıyor (tests/test_d16_hibrit_a1.py::TestB405KazanilmamisFlipHukmu,
# plaka 15 mm → L/D 6,1861). Test kırma kuralı gereği devir listesinde; bu
# satırda yalnız açıklama çelişkiyi BEYAN eder (yayımlanan ``cd_basis``).

# Cd seçim tablosu: (giriş tipi, L/D bandı) → (Cd, gerekçe)  [SP-8089; Lefebvre
# & McDonell 2. baskı Böl. 5]
CD_TABLE = [
    # (inlet, l_over_d_min, l_over_d_max, cd, aciklama)
    ('sharp',    0.0,  1.0, 0.63, 'sharp inlet, short (L/D<1): vena contracta dominates'),
    ('sharp',    1.0,  5.0, 0.78, 'sharp inlet, reattaching (L/D 1-5)'),
    ('sharp',    5.0, 99.0, 0.84,
     'sharp inlet, long (L/D>5): table value 0.84 is ABOVE the full-flow '
     'plateau of NASA SP-8089 Fig. 15 (p. 43, about 0.82); wall friction can '
     'only lower Cd, so this value is optimistic by about 2.4% (correction '
     'pending)'),
    ('radiused', 0.0,  2.0, 0.90, 'radiused inlet (r/d >= 0.15), short'),
    ('radiused', 2.0, 99.0, 0.92, 'radiused inlet (r/d >= 0.15): stable Cd'),
]

# ÖH D25 / P16B1-45 — DEVRENİN KENDİ VARSAYILAN ORİFİS TANIMI ADLANDI.
# ``design_injector`` çağıran orifis geometrisi vermediğinde Cd'yi bu iki
# varsayımla ``CD_TABLE``den seçer; iki sayı bugüne kadar yalnız
# ``spec.get('inlet_ox', 'sharp')`` / ``spec.get('l_over_d', 4.0)``
# imzalarında literal olarak duruyordu. Ürünün BEYAN ettiği varsayılan Cd
# (advanced.html: ``placeholder="0.78"`` + "the solver default of 0.78")
# tam bu ikilinin tablodaki karşılığıdır — yani sayı ADI olmayan bir
# varsayımdan geliyordu. Adlandırılması, ikinci bir tüketicinin (enjektör
# plakası çözücüsü) aynı varsayımı ÜÇÜNCÜ kez yazmasını engeller.
DEFAULT_ORIFICE_INLET = 'sharp'
DEFAULT_ORIFICE_L_OVER_D = 4.0

# Sıvı/hibrit orifis devresinde chug (düşük frekans) eşikleri ΔP/Pc.
# v2.6.27 (parti 31): bu iki sayı BURADA YENİDEN TANIMLIYDU (F2b-2'de
# "devredilen kopya" olarak bilerek açık bırakılmıştı — o parti bu dosyaya
# sahip değildi). Artık merkezî tanımın TAKMA ADIDIR: sayı değişmedi
# (0,15 / 0,20), değişen tek şey ikinci bir tanım noktasının kalmamasıdır.
# Kimlik bekçisi (``is``, değer eşitliği YETMEZ):
# tests/test_enjektor_sozlesme_borclari.py::test_esik_kimlik_zinciri
CHUG_DP_PC_MIN = CHUG_DP_RATIO_MINIMUM
CHUG_DP_PC_RECOMMENDED = CHUG_DP_RATIO_RECOMMENDED
# ÖH KU (KU-K5, SP-S1 A1) — ``stability['chug_rule']`` dizesinin DOĞRU
# künyesi (yayımlanan yeni alan ``chug_rule_basis``). İki kaynak da yerel
# metinden doğrulandı (6 Eki 2026):
#   * Sutton & Biblarz 9. bs. §8.9 s. 337: enjektör ΔP'si genellikle P_c'nin
#     %15-25'i (atomizasyon, performans ve kararlı yanma için);
#   * NASA SP-8089 s. 35: chug'ı önlemek için gereken ΔP_inj/P_c eleman
#     türüne bağlı — eş eksenli ~%5, unlike-impinging %10-15, like-impinging
#     ~%15-25; genel en düşük %5-20.
# Eşik (0,15/0,20) DEĞİŞMEDİ; eleman türüne bağlı eşik bir ÖNEMLİ karardır
# (coax/unlike için chug_ok hükmü değişir) ve burada uygulanmaz.
CHUG_RULE_CITATION = (
    'Threshold 0.15-0.20 is the low end of the classical 15-25% injector '
    'pressure-drop range (Sutton & Biblarz, 9th ed., sec. 8.9, p. 337). '
    'NASA SP-8089 (1976) p. 35 gives NO universal value: the drop needed to '
    'prevent chug depends on element type - about 5% for concentric-tube, '
    '10-15% typical for unlike-impinging, about 15-25% for like-impinging '
    '(5-20% overall). A single element-independent threshold is applied '
    'here.')
# Kullanıcının GİRDİĞİ deşarj katsayısı için kabul bandı. Sıvı motorun
# _override_val('discharge_coefficient', 0.20, 1.0, ...) çağrısı bu bandı
# 2026-07'den beri kullanıyordu ve sayılar orada literal duruyordu; hibrit
# ayağı bağlanınca aynı band ÜÇÜNCÜ kez yazılacaktı. Tek tanım burasıdır
# (sıvı motor buradan ithal eder). Üst sınır fiziksel: Cd boyutsuzdur ve
# ideal (kayıpsız) orifisi aşamaz. Alt sınır mühendislik kabulüdür —
# 0,20'nin altındaki bir Cd tıkalı/kavitasyonlu bir devreyi tarif eder.
USER_CD_RANGE = (0.20, 1.0)
#: Kullanıcı Cd'si uygulandığında devre sözlüğüne yazılan gerekçe.
USER_CD_BASIS = 'user input (discharge coefficient)'
FLIP_KC_LIMIT = 1.5            # Nurick 1976: K_c < 1.5 + keskin giriş → flip riski
# ÖH KU H-8 — SP-8089'un flip'e DUYARLI L/D bandı (bilgi bayrağı; Nurick
# hükmünü DEĞİŞTİRMEZ). NASA SP-8089 §3.1.2, s. 84: "Intermediate values for
# L/D (e.g., 4 to 6) are particularly susceptible to hydraulic flip (ref.
# 101)". Nurick bandı (1-5) L/D 5-6 arasını kapsamıyor; varsayılan L/D 4,0
# ise bu duyarlı bandın İÇİNDE durur. Yeni alan: devre sözlüğünde
# ``hydraulic_flip_sensitive_band``.
FLIP_SENSITIVE_LD_BAND = (4.0, 6.0)
# ÖH KU H-8 — tıkanma alt sınırı: 0,015 in = 0,381 mm. NASA SP-8089 s. 43
# ("an absolute lower limit of approximately 0.015 in. has been decreed in
# some cases"; 0,020 in altı tıkanmaya özellikle açık) ve s. 85. Kısıt
# DEĞİLDİR (delik planını değiştirmez); devre sözlüğünde
# ``orifice_plugging_check`` bilgi alanıdır. Kısıtın kendisi (d_min) Berke
# kararıdır.
ORIFICE_D_PLUGGING_LIMIT_MM = 0.381
# ÖH KU H-8 — hipergolik unlike elemanda tepkimeli akım ayrılması
# (blowapart) eşiği: d > 0,03 in = 0,762 mm. NASA SP-8089 s. 21: büyük
# orifisler (d > 0.03 in.) tepkimeli akım ayrılmasına yol açar, küçüklerde
# etki az. Bilgi alanı: ``impingement['reactive_stream_separation']``.
HYPERGOLIC_BLOWAPART_D_MM = 0.762
MANIFOLD_V_RATIO_TARGET = 0.1  # manifold/orifis hız oranı hedefi (≤%2 sapma)
MANIFOLD_V_RATIO_MAX = 0.2     # kabul edilebilir üst sınır (uyarıyla)
# Künye (ÖH KU, SP-H1 K21): "Huzel & Huang Böl. 4 pratiği" diye anılıyordu;
# NASA SP-125 (1967) metninde bulunamadı. Kaynaksız tasarım pratiği olarak
# beyan edilir (1992 AIAA baskısı okunmadı, sayfa doğrulanmadı).
MANIFOLD_AREA_RATIO_MIN = 4.0
IMPINGE_HALF_ANGLE_DEG = 30.0  # tipik 2θ = 60° (SP-8089)
FREE_JET_LD = 6.0              # impingement mesafesi 5-7·d_j ortası
ELEMENT_SPACING_D = 3.0        # eleman merkez aralığı ≥ 3·d
MR_BAND = (0.7, 1.3)           # doublet momentum oranı / Rupe pratik bandı
C_IMP_SMD = 2.6                # impinging SMD sabiti (band 2-4; Ingebo TN 3265 eğilimi)
PINTLE_BF_BAND = (0.3, 0.74)   # BF bandı — kaynağı DOĞRULANMADI (V301/E1)
# Hedef tıkama katsayısı (BF) varsayılanı; tek yerde (v2.6.27 B3: üç kopya
# vardı). V301/E1 KÜNYE: BF bandı/hedefi, L_s/D_p, %50 pay ve t/D_p kuralı
# Dressler & Bauer AIAA 2000-3871'de YOK (tam metin s. 2-4 tarandı; makale
# tasarım değişkenlerini sayar, sayı vermez) → HRMA seçimi (PINTLE_RULE_BASIS).
PINTLE_BF_TARGET_DEFAULT = 0.58
PINTLE_SKIP_LS_DP = 1.0        # L_s/D_p varsayılanı — HRMA seçimi (kaynaksız)
# Hibrit (tek akışkan, ox-merkezli) pintle: oksitleyici alanının radyal
# deliklere giden payı (HRMA seçimi); kalanı anülüsten eksenel tabaka akar.
# 0.5 → radyal/anüler momentum oranı 1 (aynı akışkan, aynı ΔP) → θ ≈ 60°.
PINTLE_HYBRID_RADIAL_FRACTION = 0.5
PINTLE_ANNULUS_T_OVER_DP = 0.05  # D_p verilmezse t = k·D_p — HRMA seçimi
ANNULUS_GAP_MIN_MM = 0.3       # imalat alt sınırı — HRMA seçimi (kaynaksız)
RHO_GAS_DEFAULT = 5.0          # kg/m³ — T_c/MW verilmezse varsayılan oda gazı
# ÖH D37 A2 hibrit · F-10 (= CW-A5) — DELİK ÇAPI BANDI TEK KAYNAKTAN.
# Eskiden burada İKİ bant vardı: ``ORIFICE_D_PREF_MM = (0.5, 2.5)`` ("tercih
# edilen", kaynaksız) ve ``DEFAULT_CONSTRAINTS`` d_min/d_max = 0,3/3,0 ("sert
# kısıt", kaynaksız — 3,18 mm yalnız Sutton Tablo 8-2'nin C_d VERİ noktası,
# tasarım bandı değil). ÖLÇÜLDÜ (docs/scofield/raw/OH/A2/hibrit/a1/once/
# ozet.json K1, Ornek-H1): bu çözücü 3 × Ø2,1115 mm planını "bant içi" bulup
# uyarmıyor, aynı yanıtın utils yolu (app.py bandı 0,3-2,0) "outside the
# manufacturing band (0.30-2.00 mm)" yazıyordu — bir plaka, iki hüküm.
# Sayı YENİ DEĞİL (0,5-2,5 zaten buradaydı); kaynağı ``hrma/constants.py``
# ``ORIFICE_D_BAND_MM`` + ``ORIFICE_D_BAND_SOURCE`` (Sutton & Biblarz 9. bs.
# §8.9 s. 337; Mishra 2017 Böl. 10 s. 348; ikisi de birincil metinden
# doğrulandı). Takma ad KİMLİKTİR (bekçi ``is`` ile bakar), sözlük değerleri
# demetin KENDİ öğeleridir. Tek bantta d_lo/d_hi ≡ d_min/d_max olduğundan
# ``_plan_orifices`` içindeki ``fixed_n_outside_pref_band`` ve
# ``orifice_d_above_pref_band`` dalları varsayılan kısıtla ULAŞILAMAZ;
# ``orifice_d_below_pref_band`` ise 5. tura kadar ULAŞILIYORDU (d < d_min
# dalı, tek delikte d < 0,5 mm — ölçüldü: hibrit 16 N 1 × 0,4665 mm,
# denetim-4 7 Eki). 5. turdan beri o dal alt sınırın altındaki çapı ayrı
# sınıfla bildirir (aşağıda ``classify_orifice_d``); ``*_pref_band``
# anahtarları yalnız çağıran kendi (daha geniş) kısıtını verdiğinde yaşar.
# Kod ve i18n anahtarları ÖK-21 uç sözleşmesi gereği SİLİNMEZ.
ORIFICE_D_PREF_MM = ORIFICE_D_BAND_MM
DEFAULT_CONSTRAINTS = {'d_min_mm': ORIFICE_D_BAND_MM[0],
                       'd_max_mm': ORIFICE_D_BAND_MM[1], 'n_max': 120}

# ÖH D37 A2 hibrit · 5. tur Ş-4 (ana model kararı (i), Astra danışmalı,
# karar dosyası §28-18) — DELİK ÇAPI HÜKMÜ TEK SINIFLANDIRICIDAN.
# ÖLÇÜLDÜ (denetim-4, 7 Eki): küçük alan penceresinde aynı yanıtta devre
# yolu d = 0,47 mm için "imalat alt sınırına yakın" diyordu, plaka yolu
# (utils showerhead kanon planı) aynı çap için "imalat bandı dışı"; oysa
# d < 0,5 mm bandın ALTINDADIR. İki yol artık hükmü bu işlevden alır, eşik
# kopyalanmaz.
#
# Yakınlık eşiği HRMA'NIN KENDİ SEÇİMİDİR — KAYNAKSIZ: Sutton & Biblarz
# (s. 337) ve Mishra (s. 348) yalnız 0,5-2,5 mm bandını verir; "alt kenara
# yakın" için sayı vermez. %10 (0,5 mm bantta 0,50 ≤ d < 0,55 mm) bilgi
# amaçlı bir uyarı penceresidir; delik planını DEĞİŞTİRMEZ.
#
# ÖH D37 A2 hibrit · 7. tur (karar §28-25, Astra şartı): pencere yanıtta
# ve uyarı metninde "HRMA sezgisel uyarı eşiği" diye yayımlanır — imalat
# standardı ya da güvenlik sınırı DEĞİLDİR. Künye metni payı sabitin
# KENDİSİNDEN biçimlendirir (ikinci literal kopya yok) ve
# ``design_injector`` yanıtında ``orifice_band.near_lower_edge_basis``
# alanıyla yayımlanır.
ORIFICE_D_NEAR_LOWER_EDGE_FRAC = 0.10
ORIFICE_D_NEAR_LOWER_EDGE_BASIS = (
    f'HRMA choice (no literature value): HRMA heuristic warning threshold. '
    f'A plan inside the manufacturing band but less than '
    f'{ORIFICE_D_NEAR_LOWER_EDGE_FRAC:.0%} above its lower limit is flagged '
    f'as close to the minimum. The window is NOT a manufacturing standard '
    f'and NOT a safety limit, and it does not change the hole plan; the band '
    f'itself is sourced (ORIFICE_D_BAND_SOURCE).')
#: 7. tur Ş6-3 — yakınlık uyarısındaki çap ve bant kenarlarının EN AZ
#: ondalık sayısı (yayımlanan plan tabloları da çapı 4 ondalıkla verir).
#: Gösterim pencerenin üst kenarına yuvarlanıyorsa ondalık sayısı
#: ``ORIFICE_D_NEAR_WARNING_DECIMALS_MAX``e kadar artırılır
#: (``_near_warning_mm``).
ORIFICE_D_NEAR_WARNING_DECIMALS = 4
ORIFICE_D_NEAR_WARNING_DECIMALS_MAX = 15
#: ``classify_orifice_d`` sınıfları (sıra: bant altı → bant üstü).
ORIFICE_D_CLASS_BELOW = 'below_band'
ORIFICE_D_CLASS_NEAR_LOWER = 'near_lower_edge'
ORIFICE_D_CLASS_IN = 'in_band'
ORIFICE_D_CLASS_ABOVE = 'above_band'


def classify_orifice_d(d, d_lo, d_hi):
    """Delik çapını imalat bandına göre sınıflandır (birimden bağımsız).

    ``d``, ``d_lo``, ``d_hi`` AYNI birimde verilir (m ya da mm); bant
    kenarları bandın İÇİNDEDİR.

    * ``d < d_lo``                                  → ``below_band``
    * ``d_lo ≤ d < d_lo·(1 + NEAR_FRAC)`` ve d ≤ d_hi → ``near_lower_edge``
    * ``d_lo·(1 + NEAR_FRAC) ≤ d ≤ d_hi``            → ``in_band``
    * ``d > d_hi``                                  → ``above_band``

    Devre çözücüsü (``_plan_orifices``) ve utils plaka yolu
    (``InjectorDesigner._calculate_showerhead`` kanon planı) aynı işlevi
    çağırır; "bant dışı" ve "alt sınıra yakın" hükümleri yalnız buradan
    üretilir.
    """
    d = float(d)
    if d < d_lo:
        return ORIFICE_D_CLASS_BELOW
    if d > d_hi:
        return ORIFICE_D_CLASS_ABOVE
    if d < d_lo * (1.0 + ORIFICE_D_NEAR_LOWER_EDGE_FRAC):
        return ORIFICE_D_CLASS_NEAR_LOWER
    return ORIFICE_D_CLASS_IN


def _near_warning_mm(d, d_min, d_max):
    """Yakınlık uyarısının çap parametreleri [mm]: (d, d_min, d_max).

    ÖH D37 A2 hibrit · 7. tur Ş6-3 (yeniden denetim-6). ÖLÇÜLDÜ: eski
    gösterim çapı iki, bant kenarlarını bir ondalığa yuvarlıyordu. Pencerenin
    üst kenarına yakın planlarda (Ornek-H1 22 N 1 × 0,5469 mm;
    ``/api/injector-design`` ṁ 0,00557 kg/s 1 × 0,5486 mm) yayımlanan metin
    "d=0.55 mm ... less than 10 percent above its lower limit" diyordu; oysa
    0,55 alt sınırın TAM %10 üstüdür — metin kendi hükmüyle çelişiyordu
    (hüküm doğruydu: d < 0,55). Bir ondalıklı kenar da çağıranın iki
    ondalıklı bandını (ör. 0,35 mm) başka bir sayıya çeviriyordu.

    Üçü de en az ``ORIFICE_D_NEAR_WARNING_DECIMALS`` ondalıkla yayımlanır.
    Yuvarlanmış çap, yuvarlanmış alt kenardan türetilen pencere kenarına
    (alt kenar · (1 + pay)) ulaşıyorsa ondalık sayısı artırılır: gösterilen
    çap her zaman gösterilen alt kenarın İÇİNDE ve gösterilen pencerenin
    ALTINDA kalır (yuvarlama tekdüze olduğu için alt kenar koşulu kendiliğinden
    tutar). Hüküm ``classify_orifice_d``den gelir; bu işlev yalnız gösterimdir.
    """
    d_mm, lo_mm, hi_mm = float(d) * 1e3, float(d_min) * 1e3, float(d_max) * 1e3
    k = ORIFICE_D_NEAR_WARNING_DECIMALS
    while (k < ORIFICE_D_NEAR_WARNING_DECIMALS_MAX
           and round(d_mm, k) >= round(lo_mm, k) * (
               1.0 + ORIFICE_D_NEAR_LOWER_EDGE_FRAC)):
        k += 1
    return round(d_mm, k), round(lo_mm, k), round(hi_mm, k)


def _near_lower_edge_warning(d, d_min, d_max, warnings):
    """Plan bandın İÇİNDE ve alt kenara yakınsa bilgi uyarısı (Ş-4).

    7. tur: metin pencereyi "HRMA sezgisel uyarı eşiği" diye beyan eder
    (i18n anahtarı); çap ve bant kenarları ``_near_warning_mm`` gösterimiyle.
    """
    if classify_orifice_d(d, d_min, d_max) == ORIFICE_D_CLASS_NEAR_LOWER:
        d_mm, d_min_mm, d_max_mm = _near_warning_mm(d, d_min, d_max)
        warnings.append(_w(
            'warn.injector.orifice_d_near_manufacturing_min', 'warning',
            d_mm=d_mm, d_min_mm=d_min_mm, d_max_mm=d_max_mm,
            near_pct=int(round(ORIFICE_D_NEAR_LOWER_EDGE_FRAC * 100))))


# ---------------------------------------------------------------------------
# ÖH D37 A2 hibrit · 7. tur (karar §28-25, Astra şartı) — KIRPILMIŞ PLANA
# OLUMLU HÜKÜM YOK.
#
# ÖLÇÜLDÜ (denetim-4, 7 Eki; Sunum 2 F-10 dördüncü tablo): utils çarpışmalı
# yolunda çap imalat bandının alt kenarına kırpılınca çift sayısı
# max(2, ⌈A/(2a)⌉) ile yeniden çözülür ve TESLİM alanı gereken alanın üstüne
# çıkar (Ornek-H1 50 N, element_pairs 3: 2,08×). ΔP tasarım değerinde
# yayımlanmaya devam ettiği için o ΔP'de orifis bağıntısı
# ṁ_ΔP = C_d·A_teslim·√(2ρΔP) hedefin 2,08 katı debi verir. 5. tur Ş-5
# bunu metinle söyledi ("not verified at this pressure drop"); ama aynı
# yanıtta doğrulama özeti ``validation_passed: True`` basıyordu. Astra:
# "Hedefi karşılamayan kırpılmış plan başarı/uygunluk onayı almamalı."
#
# Sınıf: ``target_flow_not_met`` — kırpılmış planın yayımlanan ΔP'deki
# debisi hedeften ``CLAMPED_PLAN_TARGET_FLOW_REL_TOL``dan fazla sapıyorsa.
# Kayıt (severity ``critical``) bu modülde kurulur; utils plan yolu sınıfı
# ``target_flow_check`` alanıyla yayımlar ve /calculate doğrulama özetine
# geçirir (``hrma.utils.injector_design.withhold_validation_pass_for_
# target_flow``). Kırpılmayan ya da hedefi tolerans içinde tutan planda alan
# HİÇ konmaz (yanıt bit-aynı).
#
# Tolerans HRMA SEÇİMİDİR — KAYNAKSIZ (literatür değeri yok): kırpılmış
# planın ΔP'si yeniden çözülmediği için bu bir ön tasarım tutarlılık payıdır,
# imalat ya da kabul toleransı DEĞİLDİR. Değiştirmek yayımlanan hükmü
# değiştirir (ÖNEMLİ; Sunum 2 önce/sonra satırı ister).
CLAMPED_PLAN_TARGET_FLOW_REL_TOL = 0.05
CLAMPED_PLAN_TARGET_FLOW_TOL_BASIS = (
    f'HRMA choice (no literature value): a hole plan whose diameter was '
    f'clamped to the manufacturing band is accepted as delivering the target '
    f'flow only if the orifice-equation flow at the published pressure drop '
    f'is within {CLAMPED_PLAN_TARGET_FLOW_REL_TOL:.0%} of the target. The '
    f'pressure drop of a clamped plan is NOT re-solved, so this is a '
    f'pre-design consistency tolerance, not a manufacturing or acceptance '
    f'tolerance.')
#: ``target_flow_check.status`` — fail-closed sınıf (tek tanım).
TARGET_FLOW_NOT_MET = 'target_flow_not_met'


def clamped_plan_target_flow_record(check):
    """Kırpılmış planın hedef debi denetiminden doğrulama kaydı (7. tur).

    ``check`` utils plan yolunun ``target_flow_check`` sözlüğüdür; durum
    ``TARGET_FLOW_NOT_MET`` değilse (ya da sözlük yoksa) ``None`` döner —
    kayıt uydurulmaz. Önem ``critical``: plan yayımlanan ΔP'de hedef debiyi
    vermiyor, yani motorun yayımlanan O/F'si ve itkisi bu plana ait değil.
    """
    if not isinstance(check, dict) or check.get('status') != TARGET_FLOW_NOT_MET:
        return None
    return _w(
        'warn.injector.target_flow_not_met', 'critical',
        mdot_target=round(float(check['target_mdot_kg_s']), 6),
        mdot_dp=round(float(check['mdot_at_published_dp_kg_s']), 6),
        ratio=round(float(check['ratio']), 3),
        dp_bar=round(float(check['pressure_drop_bar']), 3),
        tol_pct=int(round(float(check['relative_tolerance']) * 100)))

# ---------------------------------------------------------------------------
# Sıvı özellikleri: yüzey gerilimi σ ve dinamik viskozite μ
#
# v2.6.2 DÜZELTMESİ (fizik denetimi F012/F040): σ ve μ varsayılanları
# AKIŞKANDAN BAĞIMSIZ sabitlerdi (σ=0.02 N/m, μ=2e-4 Pa·s). N₂O için ikisi de
# kaba yanlıştır: N₂O kritik noktaya (309.52 K) yakın çalıştığı için 293 K'de
# σ ≈ 1.75 mN/m (0.02'nin 1/11'i) ve μ ≈ 6.3e-5 Pa·s'dir (2e-4'ün 1/3.2'si).
# Elkotb SMD ∝ σ^0.737·ν^0.385 olduğundan hata birleşerek damlacık boyutunu
# ~9 KAT şişiriyordu. Frontend bu alanları HİÇ göndermediği için varsayılan
# her kullanıcı koşusunda devredeydi.
#
# Kaynak: NIST Chemistry WebBook SRD 69 doymuş sıvı sütunları (27.08.2026
# çekimi; N₂O hâl denklemi Lemmon & Span 2006, O₂ Schmidt & Wagner 1985,
# taşıma modeli Huber NISTIR 8209 2018 — NIST viskozite belirsizliğini ~%10
# olarak BEYAN EDER, bu yüzden μ değerleri σ kadar sağlam değildir).
#
# Z1 ÇAPA DÜZELTMESİ (2026-08-27, docs/arastirma/fizik/Z1-yogunluk-dogrulama.md
# §8.2). Eski çapalar ölçüldü ve ikisi de aynı yöne kayıyordu:
#   σ(n2o) 0.00175 → NIST 293,15 K değeri 2,0577e-3 (eski değer −%15;
#       SMD ∝ σ^0,25 olduğu için damlacık boyutunda ≈ −%4)
#   μ(n2o) 6.3e-5  → NIST 293,15 K değeri 6,817e-5 (eski değer −%7,6; NIST'in
#       kendi %10 belirsizliği içinde temizdi, tek kaynak disiplini için
#       yine de çekildi)
#   σ(lox) 0.013 ve μ(lox) 1.9e-4 yuvarlanmıştı → NKN (90,19 K) değerleri
#       1,3145e-2 N/m ve 1,9466e-4 Pa·s. Referans sıcaklık da 90,0 değil
#       90,19 K (NKN, NIST): σ'nın Guggenheim ölçeklemesi bu çapayı kullanır.
# Depo içi ikinci teyit: hrma/utils/injector_design.py::SIGMA_OX bu tablodan
# TÜRETİLİR (artık ikinci bir elle yazılmış kopya yoktur).
SIGMA_LIQUID_REF = {'n2o': (0.0020577, 293.15), 'lox': (0.013145, 90.19)}
MU_LIQUID_REF = {'n2o': (6.817e-5, 293.15), 'lox': (1.9466e-4, 90.19)}
# Bilinmeyen akışkan (ve yakıt devresi) için jenerik hidrokarbon değerleri:
# RP-1/etanol σ ≈ 0.022-0.023 N/m, μ ≈ 1.5e-3...2e-3 Pa·s @ 293 K. Burada
# muhafazakâr (eski davranışla aynı) değerler korunur ve VARSAYIM olarak
# raporlanır — akışkan bilinmediği için tablo değeri uydurulmaz.
SIGMA_GENERIC = 0.02
MU_GENERIC = 2e-4
# Buhar basıncı P_v [bar] referans noktaları (akışkan -> (P_v, T_ref)).
# Kaynak: NIST Chemistry WebBook doyma verileri.
#   LOX  : NBP 90,19 K'de 1 atm = 1,01325 bar (doymuş depolama)
#   RP-1 : ~0,002 bar @ 293 K (kerosen kesiti, düşük uçuculuk)
#   etanol: 0,059 bar @ 293 K;  IPA: 0,044 bar @ 293 K
#   su    : 0,0234 bar @ 293 K (soğutucu/hidrotest devreleri)
# N₂O bu tabloda YOKTUR: onun için modülün kendi doyma tablosu (_SAT.psat)
# sıcaklıkla çözülür, sabit değere düşülmez.
PV_LIQUID_REF = {
    'lox': (1.01325, 90.19),
    'lo2': (1.01325, 90.19),
    'rp1': (0.002, 293.15),
    'rp-1': (0.002, 293.15),
    'kerosene': (0.002, 293.15),
    'ethanol': (0.059, 293.15),
    'ipa': (0.044, 293.15),
    'isopropanol': (0.044, 293.15),
    'water': (0.0234, 293.15),
}
# Akışkan tanımlanmamışsa (çağıran ad göndermedi) korunan eski varsayım.
# Depolanabilir hidrokarbonlar için makul mertebe; VARSAYIM olarak bildirilir.
PV_GENERIC = 0.05
# Guggenheim (1945) karşılık-gelen-haller bağıntısı: σ ∝ (1−T/Tc)^(11/9).
# Poling, Prausnitz & O'Connell, "The Properties of Gases and Liquids"
# 5. baskı Böl. 12'de aynı üs kullanılır. N₂O 280-305 K arasında σ 3 KAT
# değiştiği için sabit değer yetersizdir; NIST referans noktasına
# çapalanmış bu ölçekleme kullanılır.
_GUGGENHEIM_EXP = 11.0 / 9.0

# ---------------------------------------------------------------------------
# Gaz-gaz (sıkıştırılabilir) enjeksiyon sabitleri — FFSC/staged combustion
# ana odaları (iki ön yakıcıdan ox-zengin + yakıt-zengin GAZ girer).
# Kaynaklar:
#  - J.D. Anderson, "Modern Compressible Flow" 3. baskı, Böl. 3
#    (izentropik orifis/lüle kütle debisi, kritik basınç oranı P*/P0).
#  - NASA SP-8089 (1976) — enjektör ΔP/Pc kararlılık ilkesi (SIVI içindir;
#    gaz-gaz bandı aşağıda MÜHENDİSLİK KILAVUZU olarak etiketlenmiştir).
#  - Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 8-9
#    (koaksiyel/shear enjektör, momentum-akı oranı).
#  - S. Pal, R.J. Santoro ve ark. (Penn State) GO2/GH2 tek-eleman shear-coax
#    yanma çalışmaları — momentum-akı oranının karışıma etkisi.
GAS_GAS_CD_DEFAULT = 0.85       # kontürlü gaz enjektör postu tipik Cd (band 0.8-0.9)
GAS_POST_D_PREF_MM = (2.0, 8.0) # iç post tercih çap bandı (gaz postu, imalat pratiği)
GAS_ELEMENT_N_MAX = 5000        # eleman sayısı üst sınırı (gaz-gaz)
GAS_POST_WALL_MIN_MM = 0.5      # post/anülüs ara duvarı imalat alt sınırı
GAS_POST_WALL_T_OVER_D = 0.1    # post et kalınlığı ≈ 0.1·d_post (min ile sınırlı)
GAS_ANNULUS_GAP_MIN_MM = 0.2    # anülüs boşluğu imalat alt sınırı
# Gaz-gaz ΔP/Pc kararlılık bandı — MÜHENDİSLİK KILAVUZU (etiketli, uydurma
# değil): SP-8089'un %15-20 sınırı SIVI enjektörler içindir (kavitasyon,
# hidrolik flip, damlacık atomizasyonu mekanizmaları). Gaz-gaz elemanlarda
# bu mekanizmalar yoktur; gaz enjektörler tipik olarak daha düşük ΔP/Pc ile
# çalışır (Sutton & Biblarz Böl. 8). Tek yetkili gaz-gaz standardı
# bulunmadığından muhafazakâr band kullanıldı ve varsayım raporlanır.
GAS_DP_PC_MIN = 0.08            # mutlak alt sınır (altında oda-besleme kuplaj riski artar)
GAS_DP_PC_RECOMMENDED = 0.10    # önerilen alt sınır
# Momentum-akı oranı J = (ρv²)_dış / (ρv²)_iç iyi karışım bandı — MÜHENDİSLİK
# KILAVUZU (koaksiyel momentum-akı çalışmaları, Pal & Santoro; Sutton &
# Biblarz Böl. 9). Kesin optimum eleman geometrisine bağlıdır.
GAS_GAS_J_GOOD = (1.0, 10.0)

# T47: aynı gerekçeyle bu liste de İngilizce sabitlendi (bkz. REFERENCES).
GAS_GAS_REFERENCES = [
    'J.D. Anderson, Modern Compressible Flow 3rd ed., Ch. 3 '
    '(isentropic orifice flow, critical pressure ratio)',
    'NASA SP-8089 (1976) — ΔP/Pc stability principle (liquid; the gas-gas '
    'band is labelled as engineering guidance)',
    'Sutton & Biblarz, Rocket Propulsion Elements 9th ed., Ch. 8-9 '
    '(coaxial injector, momentum-flux ratio)',
    'S. Pal, R.J. Santoro et al. (Penn State) GO2/GH2 shear-coax combustion '
    'studies — momentum-flux ratio and mixing',
]

# N₂O doyma ENTROPİSİ [J/(kg·K)]: T[K], s_l, s_v — CoolProp/Span-Wagner'dan
# üretildi (2026-07-13); tank_blowdown._SAT_TABLE ile aynı sıcaklık ızgarası.
# İzentropik HEM çıkış hâli (s₂=s₁) için gereklidir; ana doyma tablosunda
# entropi yoktur.
_N2O_ENTROPY_TABLE = np.array([
    (240.0, 461.5, 1711.4),
    (243.0, 484.5, 1698.2),
    (246.0, 507.5, 1685.1),
    (249.0, 530.4, 1672.2),
    (252.0, 553.3, 1659.3),
    (255.0, 576.1, 1646.4),
    (258.0, 598.9, 1633.6),
    (261.0, 621.7, 1620.7),
    (264.0, 644.6, 1607.6),
    (267.0, 667.5, 1594.5),
    (270.0, 690.5, 1581.1),
    (273.0, 713.7, 1567.4),
    (276.0, 737.1, 1553.3),
    (279.0, 760.7, 1538.8),
    (282.0, 784.7, 1523.7),
    (285.0, 809.2, 1507.8),
    (288.0, 834.2, 1490.9),
    (291.0, 860.0, 1472.8),
    (294.0, 886.8, 1452.9),
    (297.0, 915.1, 1430.8),
    (300.0, 945.6, 1405.2),
    (303.0, 979.8, 1374.1),
    (306.0, 1021.7, 1332.0),
])

_SAT = N2OSaturation(use_coolprop=False)  # tabloyla deterministik (test tekrarlanabilirliği)

# T47 (2026-08-03): bu künyelerin niteleyicileri Türkçeydi ('9. baskı',
# 'Böl.', '(manifold pratiği)' …) ve panel listeyi dilden bağımsız olarak
# olduğu gibi basıyordu — İngilizce modda Türkçe metin görünüyordu (ölçüldü:
# /liquid, dil seçicisine dokunulmadan). Kaynak künyeleri çeviri nesnesi
# DEĞİLDİR: yazar adı, dergi adı ve baskı bilgisi künyenin parçasıdır ve
# uluslararası biçimiyle yazılır. Bu yüzden künyeler İngilizce sabitlendi.
REFERENCES = [
    'NASA SP-8089 (1976) — Liquid Rocket Engine Injectors',
    'Sutton & Biblarz, Rocket Propulsion Elements 9th ed., Ch. 8-9',
    'Huzel & Huang, Ch. 4 (manifold practice)',
    'Lefebvre & McDonell, Atomization and Sprays 2nd ed.',
    'Dyer et al., AIAA 2007-5702 (NHNE)',
    'Nurick, ASME J. Fluids Eng. 1976 (cavitation/flip)',
    'Rupe, JPL 20-195 (1953) — mixing criterion',
    'Elkotb, PECS 1982 (SMD)',
    'Giffen & Muraszew (1953) — swirl theory',
    'Casiano/Hulka/Yang, JPP 26(5) 2010 + Cheng 2017 + AIAA 2000-3871 (pintle)',
    'NASA NTRS 20190001326 (N₂O injector isolation)',
]


# ---------------------------------------------------------------------------
# Saf yardımcı fonksiyonlar (dışa açık, test edilebilir)
# ---------------------------------------------------------------------------

def spi_mass_flow(cd, area_m2, rho, dp_pa):
    """Tek fazlı sıkıştırılamaz orifis debisi: ṁ = Cd·A·√(2ρΔP) [kg/s]."""
    if dp_pa <= 0:
        return 0.0
    return float(cd * area_m2 * np.sqrt(2.0 * rho * dp_pa))


def _n2o_s_l(T):
    T = float(np.clip(T, _N2O_ENTROPY_TABLE[0, 0], _N2O_ENTROPY_TABLE[-1, 0]))
    return float(np.interp(T, _N2O_ENTROPY_TABLE[:, 0], _N2O_ENTROPY_TABLE[:, 1]))


def _n2o_s_v(T):
    T = float(np.clip(T, _N2O_ENTROPY_TABLE[0, 0], _N2O_ENTROPY_TABLE[-1, 0]))
    return float(np.interp(T, _N2O_ENTROPY_TABLE[:, 0], _N2O_ENTROPY_TABLE[:, 2]))


def _n2o_tsat_grid():
    """Doyma eğrisi ızgarası (240-306 K, 0.5 K adım) — BİR KEZ kurulur.

    PERFORMANS DENETİMİ BULGUSU (2026-07-23): bu ızgara _n2o_tsat_from_p
    içinde HER ÇAĞRIDA yeniden kuruluyordu; 133 noktanın her biri için
    _SAT.psat() çalışıyordu. HEM/NHNE debisi boğulma taraması yaptığı için
    fonksiyon tek bir enjektör hesabında yüzlerce kez çağrılıyor. Izgarayı
    modül seviyesine almak fonksiyonu ~140 kat hızlandırır; ızgara girdiden
    BAĞIMSIZ olduğu için çıktı bit düzeyinde aynıdır (ölçülen fark 0.000 K).
    """
    global _N2O_TSAT_GRID
    if _N2O_TSAT_GRID is None:
        grid_T = np.arange(240.0, 306.5, 0.5)
        grid_P = np.array([_SAT.psat(t) for t in grid_T])
        _N2O_TSAT_GRID = (grid_T, grid_P)
    return _N2O_TSAT_GRID


_N2O_TSAT_GRID = None


def _n2o_tsat_from_p(p_pa):
    """Doyma sıcaklığı P'den (tablo ters interpolasyonu)."""
    grid_T, grid_P = _n2o_tsat_grid()
    p = float(np.clip(p_pa, grid_P[0], grid_P[-1]))
    return float(np.interp(p, grid_P, grid_T))


def hem_mass_flow(cd, area_m2, fluid_state):
    """Homojen denge modeli (HEM) debisi [kg/s] — izentropik çıkış, boğulma taramalı.

    ṁ = Cd·A·G,  G(P_t) = ρ₂(P_t)·√(2(h₁−h₂(P_t))),  s₂ = s₁.
    G, P_t ∈ [P₂, P₁] üzerinde taranır; maksimum P₂'den önce geliyorsa akış
    boğulmuştur ve G = G_maks alınır (Solomon 2011 uygulama deseni).

    fluid_state: {'T1_K', 'p1_pa', 'p2_pa'} — doymuş/az-soğutulmuş N₂O girişi.
    """
    T1 = float(fluid_state['T1_K'])
    p1 = float(fluid_state['p1_pa'])
    p2 = float(fluid_state['p2_pa'])
    p_v = _SAT.psat(T1)

    if p2 >= p_v:
        # Çıkışta flaşlama yok → tek fazlı sıvı: SPI ile özdeş
        return spi_mass_flow(cd, area_m2, _SAT.rho_l(T1), p1 - p2)

    # Boğulma taraması: P_t'yi P₂ → P₁ arasında tara, G maksimumunu bul.
    #
    # ÖH D21 / B4-14 — ÖLÜ DAL KALDIRILDI. Buradaki seçim şöyleydi:
    #     G = G_vals[0] if G_vals[i_max] <= G_vals[0] else G_vals[i_max]
    # ``i_max`` argmax olduğu için ``G_vals[i_max]`` dizinin maksimumudur;
    # ``G_vals[i_max] <= G_vals[0]`` ancak maksimum ZATEN 0. indiste iken
    # doğrudur ve o durumda ``G_vals[0] == G_vals[i_max]``. Yani iki kol her
    # girdide AYNI sayıyı veriyordu: koşul boğulmayı ayırt etmiyor, yalnız
    # ayırt ediyormuş gibi duruyordu. Ölçüldü (20 (T₁, P₂) noktası,
    # docs/scofield/raw/OH/D21/hibrit/a1/{once,sonra}.json): debi BİT-AYNI.
    #
    # Boğulma bilgisinin kendisi atılmaz — ``i_max > 0`` boğulmanın ta
    # kendisidir ve artık ``hem_flux_solution`` üzerinden okunabilir; bu
    # sarmalayıcı yalnız debiyi döndürür (imzası değişmedi).
    return float(cd * area_m2 * hem_flux_solution(fluid_state)['G'])


def hem_flux_solution(fluid_state):
    """HEM kütle akısı çözümünün TAM hâli (boğulma teşhisi dâhil).

    Döner: {'G', 'choked', 'throat_pressure_pa', 'quality_at_throat',
            'flashing'} — ``hem_mass_flow`` bunun yalnız ``G``'sini kullanır.
    ``choked`` = akı maksimumunun P₂'nin ÜSTÜNDE bir basınçta oluşması, yani
    arka basıncı daha da düşürmenin debiyi artırmaması (Solomon 2011).
    """
    T1 = float(fluid_state['T1_K'])
    p1 = float(fluid_state['p1_pa'])
    p2 = float(fluid_state['p2_pa'])
    p_v = _SAT.psat(T1)
    rho_l1 = _SAT.rho_l(T1)
    if p2 >= p_v:
        # Flaşlama yok: tek fazlı sıvı, boğulma tanımsız.
        return {'G': float(np.sqrt(2.0 * rho_l1 * max(p1 - p2, 0.0))),
                'choked': False, 'throat_pressure_pa': float(p2),
                'quality_at_throat': 0.0, 'flashing': False}
    h1 = _SAT.h_l(T1) + max(p1 - p_v, 0.0) / rho_l1
    s1 = _n2o_s_l(T1)

    def _G_at(pt_pa):
        Tt = _n2o_tsat_from_p(pt_pa)
        s_l, s_v = _n2o_s_l(Tt), _n2o_s_v(Tt)
        x = float(np.clip((s1 - s_l) / max(s_v - s_l, 1e-9), 0.0, 1.0))
        h2 = _SAT.h_l(Tt) + x * (_SAT.h_v(Tt) - _SAT.h_l(Tt))
        rho2 = 1.0 / ((1.0 - x) / _SAT.rho_l(Tt) + x / max(_SAT.rho_v(Tt), 1e-9))
        return rho2 * np.sqrt(2.0 * max(h1 - h2, 0.0)), x

    pts = np.linspace(p2, min(p1, p_v) * 0.999, 60)
    cozumler = [_G_at(pt) for pt in pts]
    G_vals = [g for g, _ in cozumler]
    i_max = int(np.argmax(G_vals))
    return {'G': float(G_vals[i_max]), 'choked': bool(i_max > 0),
            'throat_pressure_pa': float(pts[i_max]),
            'quality_at_throat': float(cozumler[i_max][1]), 'flashing': True}


def _hem_exit_quality(T1_K, p2_pa):
    """HEM çıkış kalitesi x₂ (arka basınçta) — rapor alanı için.

    ÖH D21 / B4-13 — ÖLÜ ``p1_pa`` PARAMETRESİ KALDIRILDI (imza daraldı).
    Ölçüldü (docs/scofield/raw/OH/D21/hibrit/a1/{once,sonra}.json): parametre
    gövdede hiç geçmiyordu, yani süper-şarjlı giriş kaliteyi değiştiremiyordu.
    Kalemin ikinci yarısı ("kalite p₁'i GÖRMELİ") TERMODİNAMİKLE ÇÜRÜTÜLDÜ:
    izentropik genleşmede x₂ = (s₁ − s_l(T_sat(p₂))) / s_fg(T_sat(p₂)) ve
    sıkıştırılamaz sıvının İZOTERMAL basınçlanması entropiyi değiştirmez
    (T·ds = dh − v·dp = v·dp − v·dp = 0), dolayısıyla s₁ = s_l(T₁) — p₁'den
    BAĞIMSIZ. p₁ ``hem_mass_flow``ta h₁'e (h_l + (p₁−p_v)/ρ_l) girer ve orada
    gerçekten kullanılır; buraya girmesi gereken bir yol yoktu. Parametre
    sahte bir bağımlılık ilan ediyordu, kaldırıldı.

    NOT (bu onarımın kapsamı DIŞINDA, ölçülüp kayda geçirilen bulgu):
    ``nhne_mass_flow``ın yayımladığı ``quality_out`` bu fonksiyondan gelir ve
    ARKA BASINÇTAKİ kaliteyi verir; oysa boğulmuş akışta debinin çözüldüğü
    istasyon boğulma basıncıdır (``hem_flux_solution``). Ölçülen ayrışma
    (T₁=290 K, p₂=10 bar): x@p₂ = 0,311945 ⟷ x@boğulma = 0,023582. İki
    büyüklük aynı ad altında değil, ayrı istasyonlardadır.
    """
    p_v = _SAT.psat(T1_K)
    if p2_pa >= p_v:
        return 0.0
    s1 = _n2o_s_l(T1_K)
    Tt = _n2o_tsat_from_p(p2_pa)
    x = (s1 - _n2o_s_l(Tt)) / max(_n2o_s_v(Tt) - _n2o_s_l(Tt), 1e-9)
    return float(np.clip(x, 0.0, 1.0))


def nhne_mass_flow(cd, area_m2, p1_bar, p2_bar, pv_bar, T1_K, rho_l=None):
    """Dyer NHNE debisi ve bileşenleri.

    κ = √((P₁−P₂)/(P_v−P₂));  ṁ = (κ·ṁ_SPI + ṁ_HEM)/(1+κ).
    P₂ ≥ P_v ise flaşlama yok → saf SPI (κ anlamsız, inf raporlanır).

    Döner: {'mdot_kg_s','kappa','mdot_spi_kg_s','mdot_hem_kg_s',
            'quality_out','quality_at_flow_station','choked',
            'flow_station_pressure_bar'}

    ÖH D22 / B4-13 (D21'in adlandırıp AÇMADIĞI ayak) — İKİ İSTASYON, İKİ AD.
    ``quality_out`` ARKA BASINÇTAKİ kaliteyi verir; oysa boğulmuş akışta
    debinin çözüldüğü istasyon boğulma basıncıdır. Ölçüldü (T₁=290 K,
    p₂=10 bar): x@p₂ = 0,311945 ⟷ x@boğulma = 0,023582 (13,2 kat). Tek bir
    ``quality_out`` alanı okuyucuya hangi istasyonun kalitesini gördüğünü
    söylemiyordu. İki sayı da yayımlanır, istasyonu adında ve
    ``flow_station_pressure_bar`` alanında yazar. HEM çözümü artık BİR KEZ
    koşar (eskiden debi için bir, kalite için bir daha).
    """
    p1, p2, pv = (p1_bar * PA_PER_BAR, p2_bar * PA_PER_BAR, pv_bar * PA_PER_BAR)
    if rho_l is None:
        rho_l = _SAT.rho_l(T1_K)
    m_spi = spi_mass_flow(cd, area_m2, rho_l, p1 - p2)

    if p2 >= pv:  # aşırı soğutulmuş / arka basınç doymanın üstünde: iki faz yok
        return {'mdot_kg_s': m_spi, 'kappa': float('inf'),
                'mdot_spi_kg_s': m_spi, 'mdot_hem_kg_s': m_spi,
                'quality_out': 0.0, 'quality_at_flow_station': 0.0,
                'choked': False, 'flow_station_pressure_bar': float(p2_bar)}

    hem = hem_flux_solution({'T1_K': T1_K, 'p1_pa': p1, 'p2_pa': p2})
    m_hem = float(cd * area_m2 * hem['G'])
    kappa = float(np.sqrt(max(p1 - p2, 0.0) / max(pv - p2, 1e-9)))
    m_nhne = (kappa * m_spi + m_hem) / (1.0 + kappa)
    return {'mdot_kg_s': float(m_nhne), 'kappa': kappa,
            'mdot_spi_kg_s': float(m_spi), 'mdot_hem_kg_s': float(m_hem),
            'quality_out': _hem_exit_quality(T1_K, p2),
            'quality_at_flow_station': float(hem['quality_at_throat']),
            'choked': bool(hem['choked']),
            'flow_station_pressure_bar': float(
                hem['throat_pressure_pa'] / PA_PER_BAR)}


def discharge_coefficient(inlet, l_over_d):
    """Cd seçimi + gerekçe (SP-8089 / Lefebvre tablosu). → (cd, gerekçe_str)."""
    inlet = str(inlet).lower()
    if inlet not in ('sharp', 'radiused'):
        raise ValueError(f"Invalid orifice inlet type: '{inlet}' "
                         "(expected: 'sharp' or 'radiused')")
    for tip, lo, hi, cd, why in CD_TABLE:
        if tip == inlet and lo <= l_over_d < hi:
            return cd, (f"{why}; L/D={l_over_d:g} -> Cd={cd} "
                        f"(SP-8089 / Lefebvre & McDonell Ch. 5)")
    # l_over_d bandların dışına taşarsa en yakın uç. ÖH KU H-8: uç değer
    # tablonun SON satırından okunur (eskiden 0,84 / 0,92 literal olarak
    # ikinci kez yazılıydı; tablo değişince uç değer ayrışabiliyordu).
    son = [row for row in CD_TABLE if row[0] == inlet][-1]
    cd = son[3]
    why = 'sharp inlet, long' if inlet == 'sharp' else 'radiused inlet, long'
    return cd, f"{why}; L/D={l_over_d:g} -> Cd={cd} (outside table, end value)"


def discharge_coefficient_regime(inlet, l_over_d):
    """Tablo Cd'sinin hangi akış rejimini temsil ettiği (BEYAN; sayı değil).

    ÖH KU (KC-11 / SP-S1 A3): 0,78 değeri ayrık (~0,61-0,65) ve tam dolu
    (~0,81-0,83) rejimlerin ARASINDA tek bir sayıdır; rejim yayımlanmıyordu.
    Kaynak: NASA SP-8089 Şekil 13 (s. 38), Şekil 15 (s. 43) ve s. 38 (Apollo SPS'te
    çapak/honlama farkıyla Cd'de %16'ya varan sapma).
    """
    inlet = str(inlet).lower()
    imalat = ('manufacturing scatter of up to 16% in Cd has been recorded '
              '(burrs/honing, Apollo SPS; NASA SP-8089 p. 38)')
    if inlet == 'radiused':
        return ('radiused inlet: no vena contracta separation; table value. '
                + imalat)
    if l_over_d < 1.0:
        return ('separated (vena contracta, no reattachment): Cd ~0.61-0.65 '
                'in this regime (graph reading of NASA SP-8089 Fig. 13, p. '
                '38). ' + imalat)
    if l_over_d < 5.0:
        return ('transitional/reattaching: the table value lies BETWEEN the '
                'separated (~0.61-0.65) and full-flow (~0.81-0.83) regimes '
                '(graph readings of NASA SP-8089 Fig. 13, p. 38 and Fig. 15, '
                'p. 43); the actual regime '
                'depends on inlet edge and cavitation number. ' + imalat)
    return ('full flow (reattached): NASA SP-8089 Fig. 15 (p. 43) plateau '
            'of about 0.82 is the upper bound for this regime (see cd_basis '
            'for the table value). ' + imalat)


def hydraulic_flip_sensitive_band(l_over_d, l_over_d_earned):
    """SP-8089 s. 84 flip-duyarlı L/D bandı bilgisi (Nurick hükmüne EK).

    Hüküm değil bilgi bayrağıdır. L/D çağıranın geometrisinden gelmediyse
    (modül varsayılanı) bayrak yayımlanmaz (None) — kazanılmamış hüküm
    yasağıyla aynı desen; gerekçe varsayılanın bandın içinde olduğunu söyler.
    """
    lo, hi = FLIP_SENSITIVE_LD_BAND
    ld = float(l_over_d)
    in_band = lo <= ld <= hi
    basis = (f'NASA SP-8089 sec. 3.1.2, p. 84: intermediate L/D (e.g. '
             f'{lo:g} to {hi:g}) is particularly susceptible to hydraulic '
             'flip (ref. 101). Information flag only; the hydraulic-flip '
             'verdict stays the Nurick criterion (L/D 1-5, K_c < '
             f'{FLIP_KC_LIMIT:g}).')
    if not l_over_d_earned:
        return {'in_band': None,
                'band_l_over_d': [lo, hi],
                'basis': (basis + f' NOT DECIDED: L/D is the module default '
                          f'({ld:g}), which itself lies '
                          f'{"inside" if in_band else "outside"} this band; '
                          'supply the orifice length / plate thickness.')}
    return {'in_band': bool(in_band), 'band_l_over_d': [lo, hi],
            'basis': basis}


def orifice_plugging_check(d_mm):
    """SP-8089 0,015 in (0,381 mm) tıkanma alt sınırı bilgisi (kısıt değil)."""
    d = float(d_mm)
    return {
        'below_limit': bool(d < ORIFICE_D_PLUGGING_LIMIT_MM),
        'limit_mm': ORIFICE_D_PLUGGING_LIMIT_MM,
        'basis': ('NASA SP-8089 p. 43 (orifices below about 0.020 in are '
                  'particularly subject to plugging; an absolute lower limit '
                  'of approximately 0.015 in = 0.381 mm has been decreed in '
                  'some cases) and p. 85. Information only: the orifice plan '
                  'is not changed by this check.'),
    }


def reactive_stream_separation_check(fluid_ox, fluid_fuel, d_ox_mm,
                                     d_fuel_mm):
    """Hipergolik unlike elemanda blowapart (SP-8089 s. 21) bilgi alanı.

    Hipergolluk kimyadan okunur: ``liquid_rocket_engine.LIQUID_HYPERGOLIC_PAIRS``
    (tek tanım; burada yeniden yazılmaz). O modül bu modülü ithal ettiği için
    ithal döngüsünü kırmak üzere içe aktarma burada, çağrı anında yapılır.
    """
    from hrma.engines.liquid_rocket_engine import LIQUID_HYPERGOLIC_PAIRS
    pair = (str(fluid_fuel).lower(), str(fluid_ox).lower())
    hypergolic = pair in LIQUID_HYPERGOLIC_PAIRS
    basis = ('NASA SP-8089 p. 13 (all unlike-impinging elements are subject '
             'to reactive stream separation with hypergolic propellants) and '
             'p. 21 (large orifices, d > 0.03 in = 0.762 mm, result in '
             'reactive stream separation; little effect for d < 0.03 in). '
             'Hypergolicity from the propellant pair (LIQUID_HYPERGOLIC_PAIRS). '
             'Screening flag only: blowapart is not modelled and does not '
             'change any solved number.')
    if not hypergolic:
        return {'applies': False, 'risk': None,
                'threshold_d_mm': HYPERGOLIC_BLOWAPART_D_MM,
                'basis': basis + ' Not applicable: pair is not hypergolic.'}
    d_max = max(float(d_ox_mm), float(d_fuel_mm))
    return {'applies': True,
            'risk': bool(d_max > HYPERGOLIC_BLOWAPART_D_MM),
            'largest_orifice_d_mm': d_max,
            'threshold_d_mm': HYPERGOLIC_BLOWAPART_D_MM,
            'basis': basis}


def default_discharge_coefficient():
    """Orifis geometrisi VERİLMEMİŞKEN devrenin kullandığı Cd → (cd, gerekçe).

    ÖH D25 / P16B1-45. Bu, ürünün kullanıcıya beyan ettiği "çözücü
    varsayılanı"nın TEK kaynağıdır: ``DEFAULT_ORIFICE_INLET`` +
    ``DEFAULT_ORIFICE_L_OVER_D`` ikilisinin ``CD_TABLE``deki karşılığı.
    Sayı burada YENİDEN YAZILMAZ — tablodan okunur, gerekçesiyle birlikte.
    """
    return discharge_coefficient(DEFAULT_ORIFICE_INLET,
                                 DEFAULT_ORIFICE_L_OVER_D)


def hydraulic_flip_risk(inlet, l_over_d, cavitation_number):
    """Nurick flip kuralı: keskin giriş + L/D 1-5 + K_c < 1.5 → riskli."""
    return bool(str(inlet).lower() == 'sharp'
                and 1.0 <= l_over_d <= 5.0
                and cavitation_number < FLIP_KC_LIMIT)


def smd_elkotb(nu_l_m2s, sigma_n_m, rho_l, rho_gas, dp_pa):
    """Elkotb (1982) düz orifis SMD [m]:
    SMD = 3.08·ν^0.385·(σρ_l)^0.737·ρ_A^0.06·ΔP^(−0.54)."""
    return float(3.08 * nu_l_m2s ** 0.385 * (sigma_n_m * rho_l) ** 0.737
                 * rho_gas ** 0.06 * dp_pa ** (-0.54))


def smd_lefebvre_swirl(sigma_n_m, mu_l_pas, mdot_l, dp_pa, rho_gas):
    """Lefebvre basınç-swirl SMD [m]:
    SMD = 2.25·σ^0.25·μ^0.25·ṁ^0.25·ΔP^(−0.5)·ρ_A^(−0.25)."""
    return float(2.25 * sigma_n_m ** 0.25 * mu_l_pas ** 0.25
                 * mdot_l ** 0.25 * dp_pa ** (-0.5) * rho_gas ** (-0.25))


def smd_impinging(d_jet_m, v_jet, rho_l, sigma_n_m, c_imp=C_IMP_SMD):
    """Impinging SMD [m]: D₃₂ = C_imp·d_j·We_j^(−1/3), We_j = ρ_l·v²·d_j/σ.
    C_imp=2.6 varsayılan (band 2-4; test verisiyle kalibre edilebilir)."""
    we = rho_l * v_jet ** 2 * d_jet_m / sigma_n_m
    return float(c_imp * d_jet_m * we ** (-1.0 / 3.0))


# Giffen–Muraszew geometrik katsayısı: K = (π/(4√2))·√((1−X)³/X²).
# v2.6.2 fizik denetimi, bulgu F001 (KRİTİK).
#
# v2.6.2 düzeltmesi: burada √(32/π²) = 1.80063 yazılıydı — doğrusunun TAM
# TERSİ (1.80063 × 0.55536 = 1.000000). Hata modülün kendi içinde çelişki
# yaratıyordu: aynı fonksiyondaki sinθ = (π/2)·Cd/(K(1+√X)) bağıntısı
# Lefebvre'in K = A_p/(D_s·d_o) tanımına aittir, dolayısıyla iki bağıntı
# 32/π² = 3.242 kat farklı K tanımı kullanıyordu.
#
# Fiziksel kanıt: ters katsayıyla ulaşılabilen EN BÜYÜK sprey yarı açısı
# 15.9° idi; gerçek basınçlı-swirl (simplex) atomizörler rutin olarak
# 30-60° yarı açı verir. Cd de 2.0-2.7 kat düşük çıkıyor ve doğrudan
# enjeksiyon alanına girdiği için (A = ṁ/(Cd·√(2ρΔP))) toplam delik alanı
# 1.7-2.7 KAT fazla boyutlanıyordu.
#
# Doğrulama: X=0.5 → K=0.3927, Cd=0.2887 (Lefebvre & McDonell, Atomization
# and Sprays 2. baskı, Böl. 6 simplex atomizör tablolarıyla uyumlu; tipik
# simplex Cd 0.25-0.45).
_SWIRL_GEOMETRIC_COEF = np.pi / (4.0 * np.sqrt(2.0))  # = √(π²/32) = 0.55536

# ÖH KU (KC-11 / RUS R2) — İDEAL TEORİ BEYANI (sayı değişmez).
# Giffen-Muraszew çözümü Abramovich ideal (viskoz kayıpsız) teorisiyle
# özdeştir (K = π/(4A); Cd ve 2θ dört ondalıkta aynı — RUS notu ölçümü).
# Bağımsız deneylerle iki yönlü sapma raporlanmış:
#   * Salich & Semkin 2013, Vestnik YuUrGU 13(1), Tablo 1 (13 N enjektör,
#     A = 16,72): bu çözüm Cd 0,0519 / 2θ 130,5° ⟷ deney 0,046 / 107°
#     (+%13 / +%22; RUS notunun ölçümü);
#   * Prokopenko & Gerasimenko 2024, Trudy MAI 134, Tablo 2: ideal teori
#     debiyi %8-17 DÜŞÜK veriyor (ters işaret).
# Sayfa düzeyinde bu ajan doğrulamadı (RUS notunun okuması). Sürtünme
# düzeltmesi (Klyachko/Bazarov) birincil metin bulunmadan EKLENMEZ.
SWIRL_IDEAL_THEORY_BASIS = (
    'Ideal (inviscid) swirl-atomizer theory: the Giffen-Muraszew solution '
    'used here is identical to Abramovich\'s ideal theory. Independent '
    'experiments scatter on both sides: Cd +13% and spray cone 2*theta +22% '
    'above test for a 13 N injector (Salich & Semkin 2013, Vestnik SUSU '
    '13(1), Table 1), while Prokopenko & Gerasimenko 2024 (Trudy MAI 134, '
    'Table 2) report the ideal theory under-predicting the flow by 8-17%. '
    'Treat Cd and cone angle as estimates of order +/-15-22%; a cold-flow '
    'measured Cd can be supplied through the user Cd input. No friction '
    'correction is applied.')


def swirl_solve(K):
    """Giffen–Muraszew çözümü: K → {'X','cd','theta_deg','film_t_ratio'}.

    K = (π/(4√2))·√((1−X)³/X²) bağıntısından X kök araması (0<X<1);
    Cd = √((1−X)³/(1+X));  sinθ = (π/2)·Cd/(K·(1+√X));
    film kalınlığı oranı t/r_o = 1−√X.

    K, Lefebvre tanımıyla atomizör sabitidir: K = A_p/(D_s·d_o)
    (A_p: teğetsel giriş kanalı toplam alanı, D_s: girdap odası çapı,
    d_o: çıkış orifis çapı).

    Kaynak: Giffen & Muraszew (1953); Lefebvre & McDonell, *Atomization and
    Sprays*, 2. baskı, Böl. 6.
    """
    if K <= 0:
        raise ValueError('Swirl atomizer constant K must be positive')
    coef = _SWIRL_GEOMETRIC_COEF

    def f(x):
        return coef * np.sqrt((1.0 - x) ** 3 / x ** 2) - K

    lo, hi = 1e-6, 1.0 - 1e-6
    for _ in range(200):  # bisection — f monoton azalan
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    X = 0.5 * (lo + hi)
    cd = float(np.sqrt((1.0 - X) ** 3 / (1.0 + X)))
    sin_theta = float(np.clip((np.pi / 2.0) * cd / (K * (1.0 + np.sqrt(X))),
                              -1.0, 1.0))
    return {'X': float(X), 'cd': cd,
            'theta_deg': float(np.degrees(np.arcsin(sin_theta))),
            'film_t_ratio': float(1.0 - np.sqrt(X))}


# swirl_K_from_theta'nın arama aralığı K ∈ [_SWIRL_K_MIN, _SWIRL_K_MAX] olup
# bu, çözülebilir yarı açı zarfını belirler (ölçüldü: K=20 → 3.67°,
# K=0.02 → 71.24°). Zarf dışı hedefler kırpılır ve kullanıcıya uyarı verilir.
_SWIRL_K_MIN, _SWIRL_K_MAX = 0.02, 20.0
_SWIRL_THETA_MIN_DEG, _SWIRL_THETA_MAX_DEG = 3.7, 71.2


def swirl_X_from_cd(cd):
    """Verilen deşarj katsayısından hava çekirdeği oranını çöz (ters çözüm).

    Cd = √((1−X)³/(1+X)) bağıntısı X'te monoton azalandır; bisection ile
    tersi alınır. Buradan K = (π/(4√2))·√((1−X)³/X²) ve
    sinθ = (π/2)·Cd/(K(1+√X)) türetilebilir — yani Cd bilinen bir simplex
    atomizörün girdap geometrisi ve sprey açısı KAPALI olarak belirlidir.

    Kaynak: Giffen & Muraszew (1953); Lefebvre & McDonell, *Atomization and
    Sprays*, 2. baskı, Böl. 6.
    """
    cd = float(cd)
    if not (0.0 < cd < 1.0):
        raise ValueError('Swirl atomizer Cd must satisfy 0 < Cd < 1 '
                         '(Cd -> 1 in the X -> 0 limit)')
    lo, hi = 1e-9, 1.0 - 1e-9   # f(X) = √((1−X)³/(1+X)) − Cd, X'te azalan
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if np.sqrt((1.0 - mid) ** 3 / (1.0 + mid)) > cd:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def swirl_K_from_theta(theta_target_deg):
    """Hedef sprey yarı açısından K çöz (iç içe kök araması, monoton)."""
    lo, hi = _SWIRL_K_MIN, _SWIRL_K_MAX
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        th = swirl_solve(mid)['theta_deg']
        if th > theta_target_deg:  # K büyüdükçe θ küçülür
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def liquid_surface_tension(fluid, T_K=None):
    """Sıvı yüzey gerilimi σ [N/m] — akışkan tablosundan, T verilirse ölçekli.

    N₂O için Guggenheim ölçeklemesi uygulanır:
        σ(T) = σ_ref·((1−T/Tc)/(1−T_ref/Tc))^(11/9),  Tc = 309.52 K.
    Bilinmeyen akışkanda jenerik değer döner.

    Döner: (sigma [N/m], basis) — basis ∈ {'table','table_T_scaled','generic'}.
    Kaynak: NIST WebBook (referans nokta); Guggenheim (1945) / Poling ve ark.
    5. baskı Böl. 12 (sıcaklık ölçeklemesi).
    """
    key = str(fluid or '').lower()
    if key not in SIGMA_LIQUID_REF:
        return SIGMA_GENERIC, 'generic'
    sigma_ref, t_ref = SIGMA_LIQUID_REF[key]
    if key != 'n2o' or T_K is None:
        return sigma_ref, 'table'
    # Kritik noktanın üstünde sıvı yoktur; 0.5 K güvenlik payıyla kırpılır.
    t = float(min(float(T_K), N2O_T_CRIT - 0.5))
    ratio = (1.0 - t / N2O_T_CRIT) / (1.0 - t_ref / N2O_T_CRIT)
    return float(sigma_ref * max(ratio, 1e-9) ** _GUGGENHEIM_EXP), 'table_T_scaled'


def liquid_viscosity(fluid, T_K=None):
    """Sıvı dinamik viskozitesi μ [Pa·s] — akışkan tablosundan (referans T).

    Sıcaklık bağımlılığı MODELLENMEZ (güvenilir tablo/korelasyon bu modülde
    yok); referans sıcaklık varsayım olarak raporlanır — uydurma korelasyon
    yazmak yerine sınır açıkça bildirilir.

    Döner: (mu [Pa·s], T_ref [K] veya None, basis).
    Kaynak: NIST WebBook — N₂O μ_l ≈ 6.3e-5 Pa·s @ 293 K; LOX ≈ 1.9e-4 @ 90 K.
    """
    key = str(fluid or '').lower()
    if key not in MU_LIQUID_REF:
        return MU_GENERIC, None, 'generic'
    mu_ref, t_ref = MU_LIQUID_REF[key]
    return float(mu_ref), float(t_ref), 'table'


def liquid_vapor_pressure(fluid, T_K=None):
    """Sıvı buhar basıncı P_v [bar] — akışkan tablosundan.

    v2.6.26 (kusur: p_v_bar akışkandan BAĞIMSIZ 0,05 bar sabitiydi). Bu değer
    Nurick kavitasyon sayısına doğrudan girer:
        K_c = (P₁ − P_v)/(P₁ − P₂)
    P_v'yi olduğundan küçük almak K_c'yi YUKARI çeker, yani kavitasyon /
    hidrolik flip riskini OLDUĞUNDAN DÜŞÜK gösterir — güvenlik yönünde
    yanlış taraf. LOX kendi doyma noktasında depolanır (NBP 90,19 K'de
    P_v = 1,01325 bar); 0,05 bar kullanmak 20 kat hatadır.

    Aynı modül σ ve μ için bu akışkan-bağımsızlık hatasını v2.6.2'de
    kapatmıştı (bkz. SIGMA_LIQUID_REF / MU_LIQUID_REF); bu, o düzeltmenin
    üçüncü büyüklüğüdür.

    Sıcaklık bağımlılığı MODELLENMEZ: bu modülde N₂O dışında güvenilir
    doyma eğrisi yoktur. Referans nokta ve sınır çıktıda beyan edilir —
    uydurma korelasyon yazmak yerine sınır açıkça bildirilir.

    Döner: (p_v [bar], basis)
    Kaynak: NIST Chemistry WebBook doyma verileri — O₂ NBP 90,19 K
    (1 atm); RP-1/kerosen ~0,002 bar ve etanol 0,059 bar @ 293 K
    (Antoine, NIST); IPA 0,044 bar @ 293 K.
    """
    key = str(fluid or '').lower()
    ref = PV_LIQUID_REF.get(key)
    if ref is None:
        return PV_GENERIC, ('generic assumption (fluid not identified by the '
                            'caller; no vapour-pressure table applied)')
    p_v, t_ref = ref
    if T_K is None or abs(float(T_K) - t_ref) < 0.5:
        return float(p_v), f'table value at {t_ref:.2f} K ({key})'
    return float(p_v), (f'table value at {t_ref:.2f} K ({key}); the '
                        f'temperature dependence is NOT modelled, requested '
                        f'{float(T_K):.2f} K')


def pintle_spray_angle(tmr):
    """Pintle sprey yarı açısı [deg]: θ = arccos(1/(1+TMR)) (Cheng 2017)."""
    if tmr < 0:
        raise ValueError('TMR cannot be negative')
    return float(np.degrees(np.arccos(1.0 / (1.0 + tmr))))


def pintle_tip_geometry(a_radial_m2, a_annulus_m2, d_pintle_m=None,
                        bf_target=PINTLE_BF_TARGET_DEFAULT):
    """Pintle ucu geometrisinin TEK KAYNAĞI: radyal delik dizisi + anülüs.

    v2.6.27 (B3) — depoda İKİ bağımsız enjektör modülü vardı ve radyal delik
    modeli YALNIZ bu modüldeydi. Ekrana çizilen model (``utils/injector_
    design.py::_calculate_pintle``) pintle'ı çıplak bir anülüs sanıyordu:
    kullanıcı "radyal delik üretilmiyor" derken haklıydı, ama sebep
    "Secondary Holes seçimi işlemiyor" değil, SAYFANIN RADYAL DELİĞİ OLAN
    MODELİ HİÇ GÖRMEMESİYDİ. Sentez burada tek yere alındı; her iki modül de
    (ve ``design_injector``'ın iki pintle dalı da) bu fonksiyonu çağırır, yani
    tabloda, 2B kesitte ve şema çiziminde AYNI geometri görünür.

    Girdi:
        a_radial_m2  : radyal deliklere ayrılan toplam akış alanı [m²]
        a_annulus_m2 : pintle gövdesi çevresindeki anülüs alanı [m²]
        d_pintle_m   : pintle mili çapı [m]; None ise anülüs boşluk/çap
                       kuralından (t = 0.05·D_p, HRMA seçimi) çözülür
        bf_target    : hedef tıkama katsayısı (blockage factor)

    Bağıntılar — geometrik tanımlar; sayısal kurallar HRMA seçimi (V301/E1:
    Dressler & Bauer AIAA 2000-3871 bu sayıları VERMEZ, bkz. PINTLE_RULE_BASIS):
        BF = n·d/(π·D_p)  ve  A_rad = n·(π/4)·d²  → d ve n birlikte çözülür
        A_ann = π·(D_p+t)·t  → t = (√(D_p² + 4·A_ann/π) − D_p)/2  (TAM ifade,
        ince-anülüs yaklaşımı değil)
        L_s/D_p = 1 (varsayılan skip distance; tanımı Dressler & Bauer s. 4)

    Döner: ``pintle_geometry`` sözleşmesinin geometrik alanları.
    """
    a_rad = max(float(a_radial_m2), 0.0)
    a_ann = max(float(a_annulus_m2), 0.0)
    bf_target = float(bf_target)
    if not (0.0 < bf_target < 1.0):
        raise ValueError('bf_target must be between 0 and 1')

    if d_pintle_m is None:
        # ÖH D20 / B4-11 — D_p ARTIK TAM İFADEDEN ÇÖZÜLÜYOR.
        # Eski satır ``D_p = sqrt(A_ann/(pi*k))`` idi; bu, A_ann ≈ pi*D_p*t
        # İNCE-ANÜLÜS yaklaşımının tersidir. Oysa aşağıdaki t, aynı
        # fonksiyonda TAM ifadeden (A_ann = pi*(D_p+t)*t) çözülüyor. İki
        # farklı model yan yana durunca fonksiyon kendi künyesiyle çelişiyordu
        # ("TAM ifade, ince-anülüs yaklaşımı değil") ve ÖLÇÜLDÜ (D20
        # a1/once.json ``B4_11``): yayımlanan t/D_p her alanda 0,047723 —
        # hedeflenen 0,05'ten %4,555 sapma, üstelik sapma A_ann'dan bağımsız
        # sabit bir yanlılık.
        # Tam ifade + t = k·D_p:  A_ann = pi*k*(1+k)*D_p^2
        #   -> D_p = sqrt(A_ann / (pi*k*(1+k)))
        # Böylece aşağıdaki t TAM çözümü tam olarak k·D_p verir; tek model.
        _k = PINTLE_ANNULUS_T_OVER_DP
        d_p_m = float(np.sqrt(a_ann / (np.pi * _k * (1.0 + _k))))
    else:
        d_p_m = float(d_pintle_m)
    if d_p_m <= 0:
        raise ValueError('Pintle diameter must be positive')

    # BF hedefi: n·d = BF·π·D_p ve n·(π/4)d² = A_rad → d, n çöz
    d_hole = (4.0 * a_rad / np.pi) / max(bf_target * np.pi * d_p_m, 1e-9)
    n_holes = max(4, int(round(bf_target * np.pi * d_p_m / max(d_hole, 1e-9))))
    d_hole = float(np.sqrt(4.0 * a_rad / (np.pi * n_holes)))
    bf = n_holes * d_hole / (np.pi * d_p_m)
    t_ann = float((np.sqrt(d_p_m ** 2 + 4.0 * a_ann / np.pi) - d_p_m) / 2.0)

    return {
        'd_pintle_mm': float(d_p_m * 1e3),
        'skip_distance_mm': float(PINTLE_SKIP_LS_DP * d_p_m * 1e3),
        'ls_over_dp': float(PINTLE_SKIP_LS_DP),
        'bf': float(bf),
        'annulus_gap_mm': float(t_ann * 1e3),
        'n_radial_holes': int(n_holes),
        'radial_hole_d_mm': float(d_hole * 1e3),
    }


# ---------------------------------------------------------------------------
# Sıkıştırılabilir (gaz) orifis akışı — gaz-gaz enjeksiyon
# ---------------------------------------------------------------------------

def critical_pressure_ratio(gamma):
    """Boğulma (kritik) basınç oranı P*/P0 = (2/(γ+1))^(γ/(γ−1)).

    Bu orandan (dahil) küçük arka-basınç oranlarında akış boğulur ve kütle
    debisi arka basınçtan bağımsız olur. Kaynak: Anderson, Modern
    Compressible Flow 3. baskı, Böl. 3 (izentropik lüle/orifis).
    """
    gamma = float(gamma)
    if gamma <= 1.0:
        raise ValueError('gamma must exceed 1 (compressible gas)')
    return float((2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0)))


def compressible_orifice_flow(cd, area_m2, p0_pa, t0_k, gamma, r_specific,
                              p_back_pa):
    """Sıkıştırılabilir orifis akışı — izentropik, boğulma (choked) ayrımlı.

    Kütle debisi (Anderson Böl. 3; NASA SP-8089 form):
      choked  (P_back/P0 ≤ P*/P0):
        ṁ = Cd·A·P0·√(γ/(R·T0))·(2/(γ+1))^((γ+1)/(2(γ−1)))
        → arka basınçtan BAĞIMSIZ (sabit).
      unchoked (P_back/P0 > P*/P0):
        ṁ = Cd·A·P0·√( (2γ/((γ−1)R·T0))·(Pr^(2/γ) − Pr^((γ+1)/γ)) ),  Pr=P_back/P0
        → arka basınca bağlı, Pr→1'de ṁ→0 (monoton).
    İki dal kritik oranda süreklidir (izentropik akı maksimumu boğulmadadır).

    Birimler SI: p [Pa], T [K], R [J/(kg·K)], A [m²] → ṁ [kg/s].
    R_specific = R_universal / MW; boyutsuz Cd akı katsayısıdır.

    Döner: {'mdot_kg_s','mass_flux','choked','mach','p_exit_pa','t_exit_k',
            'rho_exit','v_exit_m_s','pr_crit','pr'} — mass_flux = ṁ/A (Cd dahil).
    """
    gamma = float(gamma)
    r_specific = float(r_specific)
    if gamma <= 1.0:
        raise ValueError('gamma must exceed 1')
    if r_specific <= 0.0:
        raise ValueError('R (specific gas constant) must be positive')
    if p0_pa <= 0.0 or t0_k <= 0.0:
        raise ValueError('P0 and T0 must be positive')
    if p_back_pa < 0.0:
        raise ValueError('Back pressure cannot be negative')

    pr = p_back_pa / p0_pa
    pr_crit = critical_pressure_ratio(gamma)
    g1 = gamma - 1.0

    if pr <= pr_crit:  # boğulmuş
        flux = (p0_pa * np.sqrt(gamma / (r_specific * t0_k))
                * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * g1)))
        p_exit = p0_pa * pr_crit
        t_exit = t0_k * 2.0 / (gamma + 1.0)
        mach = 1.0
        v_exit = np.sqrt(gamma * r_specific * t_exit)
        choked = True
    else:              # subsonik
        term = max(pr ** (2.0 / gamma) - pr ** ((gamma + 1.0) / gamma), 0.0)
        flux = p0_pa * np.sqrt((2.0 * gamma / (g1 * r_specific * t0_k)) * term)
        p_exit = p_back_pa
        t_exit = t0_k * pr ** (g1 / gamma)
        mach = np.sqrt(max((2.0 / g1) * (pr ** (-g1 / gamma) - 1.0), 0.0))
        v_exit = mach * np.sqrt(gamma * r_specific * t_exit)
        choked = False

    mass_flux = float(cd * flux)
    return {
        'mdot_kg_s': float(mass_flux * area_m2),
        'mass_flux': mass_flux,                 # kg/(s·m²), Cd dahil
        'choked': bool(choked),
        'mach': float(mach),
        'p_exit_pa': float(p_exit),
        't_exit_k': float(t_exit),
        'rho_exit': float(p_exit / (r_specific * t_exit)),
        'v_exit_m_s': float(v_exit),
        'pr_crit': float(pr_crit),
        'pr': float(pr),
    }


def _gas_r_specific(gas, name):
    """Özgül gaz sabiti R [J/(kg·K)]: doğrudan 'R' veya 'MW'den (kg/kmol).

    Varsayılan YOK — ön yakıcı egzoz koşulu dışarıdan (çevrim çözücüsünden)
    gelmelidir. R verilmişse o kazanır (MW gölgede kalır).
    """
    r = gas.get('R')
    if r is not None:
        if float(r) <= 0.0:
            raise ValueError(f"{name}: R must be positive")
        return float(r)
    mw = gas.get('MW', gas.get('mw'))
    if mw is None:
        raise ValueError(
            f"{name}: either 'R' (J/kg-K) or 'MW' (kg/kmol) is required for "
            "the specific gas constant (preburner exhaust composition; no "
            "default is assumed)")
    if float(mw) <= 0.0:
        raise ValueError(f"{name}: MW must be positive (kg/kmol)")
    return R_UNIVERSAL / float(mw)


def _require_gas_stream(spec, key, name):
    """Gaz akım sözlüğünü doğrula: T0_K, P0_bar, gamma zorunlu (varsayılan yok)."""
    gas = spec.get(key)
    if not isinstance(gas, dict):
        raise ValueError(
            f"gas_gas_coaxial: the '{key}' block is required "
            "(T0_K, P0_bar, gamma, and either MW or R)")
    for k in ('T0_K', 'P0_bar', 'gamma'):
        if gas.get(k) is None:
            raise ValueError(
                f"{name}: '{k}' is required - the preburner exhaust state must "
                "be supplied; no default constant is assumed")
    if float(gas['P0_bar']) <= 0.0 or float(gas['T0_K']) <= 0.0:
        raise ValueError(f"{name}: P0_bar and T0_K must be positive")
    if float(gas['gamma']) <= 1.0:
        raise ValueError(f"{name}: gamma must exceed 1")
    return gas


def _plan_gas_elements(total_area_m2, warnings, stream,
                       pref_mm=GAS_POST_D_PREF_MM, n_max=GAS_ELEMENT_N_MAX):
    """Toplam iç-post alanını, post çapını tercih bandına (2-8 mm) oturtan
    n elemana böl. Bandın içindeki EN KÜÇÜK n (en büyük çap) seçilir; band
    tutturulamazsa sınır çözümü + uyarı.

    ``stream`` ∈ {'ox', 'fuel'} — iç postun hangi akımı taşıdığı (uyarı kodu
    bundan seçilir; dil frontend'de kurulur).
    """
    d_lo, d_hi = pref_mm[0] * 1e-3, pref_mm[1] * 1e-3
    if total_area_m2 <= 0:
        raise ValueError(
            f"{_GAS_POST_LABEL[stream]}: total post area must be positive")
    for n in range(1, n_max + 1):
        d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))
        if d <= d_hi:
            if d < d_lo:
                # 9. tur (Devir 35): gösterim hükümle çelişmez.
                d_g, lo_g, hi_g = _band_warning_mm(d, d_lo, d_hi)
                warnings.append(_w(
                    'warn.injector.gas_inner_post_below_pref_band_ox'
                    if stream == 'ox' else
                    'warn.injector.gas_inner_post_below_pref_band_fuel',
                    'warning',
                    d_mm=d_g, band_lo_mm=lo_g, band_hi_mm=hi_g))
            return int(n), float(d)
    # n_max ile bile post bandın üstünde: sınır çözümü
    n = n_max
    d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))
    warnings.append(_w(
        'warn.injector.gas_element_limit_post_above_pref_band_ox'
        if stream == 'ox' else
        'warn.injector.gas_element_limit_post_above_pref_band_fuel',
        'warning', n_max=int(n_max), d_mm=_band_warning_mm(d, d_lo, d_hi)[0]))
    return int(n), float(d)


# ---------------------------------------------------------------------------
# Delik planı ve manifold
# ---------------------------------------------------------------------------

def _plan_orifices(total_area_m2, constraints, warnings, n_fixed=None):
    """Toplam alanı, çapı ``ORIFICE_D_BAND_MM`` bandına oturtan n deliğe böl.

    n_fixed verilirse delik sayısı sabitlenir (yalnız çap çözülür) — kullanıcı
    plan kısıtı veya doğrulama senaryoları için.

    ÖH D37 A2 hibrit · F-10: ``constraints`` sözlüğü çağıran vermezse
    ``DEFAULT_CONSTRAINTS``tan gelir ve o artık tek kaynaklı bantla AYNI
    sayıdır (d_min ≡ d_lo, d_max ≡ d_hi). Varsayılan kısıtla ulaşılabilirlik
    (5. tur Ş-4, denetim-4 bulgusu üzerine düzeltildi — eski metin üç dalın
    da ULAŞILAMAZ olduğunu söylüyordu, ``d < d_min`` dalı için bu YANLIŞTI):

    * ``fixed_n_outside_pref_band`` ve ``orifice_d_above_pref_band``:
      ULAŞILAMAZ (d_min ≤ d ≤ d_max ⇔ d_lo ≤ d ≤ d_hi).
    * ``d < d_min`` dalı: ULAŞILIR. Tek delikte bile çap alt sınırın
      altındaysa (A < π·d_min²/4) n = 1 kalır ve d < d_min olur; ölçüldü:
      hibrit 16 N devresi 1 × 0,4665 mm, sıvı 100 N yakıt 1 × 0,4649 mm,
      ``/api/injector-design`` ṁ 0,004 kg/s 1 × 0,4649 mm. 5. turdan beri bu
      çap ``orifice_d_below_manufacturing_band`` ile bildirilir (eskiden
      "imalat alt sınırına yakın" diyen ``orifice_d_below_pref_band``).
    * ``orifice_d_below_pref_band``: varsayılan kısıtla artık ULAŞILAMAZ;
      yalnız çağıranın d_min'i d_lo'dan küçükse ve çap [d_min, d_lo)
      aralığına düşerse basılır.
    * ``orifice_d_near_manufacturing_min``: plan bandın İÇİNDE ve alt
      kenara yakınsa (``classify_orifice_d``) ULAŞILIR; varsayılan kısıtla
      tek delikte 0,50 ≤ d < 0,55 mm penceresi.

    Kod ve i18n anahtarları silinmez: kısıt sözlüğü bu işlevin genel
    arayüzüdür ve uç sözleşmesi (ÖK-21) anahtarların kalmasını ister.
    Bant dışı / alt kenara yakın hükmü YALNIZ ``classify_orifice_d``den
    gelir (utils plaka yolu da aynı işlevi çağırır).
    """
    # ÖH D37 A2 hibrit · denetçi Ş4: anahtar eksikse YEDEK de tek kaynaktan
    # gelir (``DEFAULT_CONSTRAINTS`` öğeleri ≡ ``ORIFICE_D_BAND_MM`` öğeleri).
    # Eski ``.get('d_min_mm', 0.3)`` / ``.get('d_max_mm', 3.0)`` literal
    # yedekleri kaynaksızdı ve F-10'un kapattığı ikinci bandı (0,3/3,0) KISMİ
    # kısıt sözlüğüyle çağırana geri veriyordu. Ürün yolunda sayı değişmez:
    # ``design_injector`` sözlüğü ``dict(DEFAULT_CONSTRAINTS)`` üstüne kurar,
    # anahtar hiç eksik gelmez (yedek yalnız doğrudan çağıranda yaşar).
    d_min = constraints.get('d_min_mm', DEFAULT_CONSTRAINTS['d_min_mm']) * 1e-3
    d_max = constraints.get('d_max_mm', DEFAULT_CONSTRAINTS['d_max_mm']) * 1e-3
    n_max = int(constraints.get('n_max', DEFAULT_CONSTRAINTS['n_max']))
    d_lo, d_hi = ORIFICE_D_PREF_MM[0] * 1e-3, ORIFICE_D_PREF_MM[1] * 1e-3

    if n_fixed is not None:
        n = int(n_fixed)
        if n < 1:
            raise ValueError('Hole count must be at least 1')
        d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))
        # 9. tur (Devir 35): çap ve kenar gösterimi ``_band_warning_mm``
        # (modülde ``_plan_orifices``ten sonra; gösterim hükümle çelişmez).
        if classify_orifice_d(d, d_min, d_max) in (ORIFICE_D_CLASS_BELOW,
                                                   ORIFICE_D_CLASS_ABOVE):
            d_g, lo_g, hi_g = _band_warning_mm(d, d_min, d_max)
            warnings.append(_w(
                'warn.injector.fixed_n_outside_manufacturing_band', 'warning',
                n=int(n), d_mm=d_g, d_min_mm=lo_g, d_max_mm=hi_g))
        elif not (d_lo <= d <= d_hi):
            d_g, lo_g, hi_g = _band_warning_mm(d, d_lo, d_hi)
            warnings.append(_w(
                'warn.injector.fixed_n_outside_pref_band', 'warning',
                n=int(n), d_mm=d_g, band_lo_mm=lo_g, band_hi_mm=hi_g))
        _near_lower_edge_warning(d, d_min, d_max, warnings)
        return n, float(d)

    best, _uyari_basi = None, len(warnings)
    for n in range(1, n_max + 1):
        d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))  # Lean çapası
        if max(d_lo, d_min) <= d <= min(d_hi, d_max):  # 10. tur: çağıranın bandı
            best = (n, d)   # bandın içindeki EN KÜÇÜK n (en büyük d) → dur
            break
    if best is None:
        # Band tutturulamadı: kısıt sınırında en yakın çözüm
        n = n_max
        d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))
        if classify_orifice_d(d, d_min, d_max) == ORIFICE_D_CLASS_ABOVE:
            d_g, _lo_g, hi_g = _band_warning_mm(d, d_min, d_max)
            warnings.append(_w(
                'warn.injector.orifice_plan_infeasible', 'warning',
                n_max=int(n_max), d_max_mm=hi_g, d_mm=d_g))
        elif d > d_hi:
            d_g, lo_g, hi_g = _band_warning_mm(d, d_lo, d_hi)
            warnings.append(_w(
                'warn.injector.orifice_d_above_pref_band', 'warning',
                d_mm=d_g, n_max=int(n_max),
                band_lo_mm=lo_g, band_hi_mm=hi_g))
        elif classify_orifice_d(d, d_min, d_max) == ORIFICE_D_CLASS_BELOW:
            n = max(1, int(np.floor(4.0 * total_area_m2 / (np.pi * d_min ** 2))))
            n = min(n, n_max)
            d = np.sqrt(4.0 * total_area_m2 / (np.pi * n))
            # ÖH D37 A2 hibrit · 5. tur Ş-4: son çapın hükmü
            # ``classify_orifice_d``den. n = 1'e düşüp çap hâlâ d_min'in
            # altındaysa plan imalat bandının DIŞINDADIR — eski
            # ``orifice_d_below_pref_band`` metni bu çapa "imalat alt sınırına
            # yakın" diyordu (yanlış hüküm, denetim-4). Çap d_min'e
            # oturduysa (yalnız çağıranın d_min'i d_lo'dan küçükken) bant
            # İÇİNDEDİR ama tercih bandının altındadır.
            # 9. tur (Devir 35): çap ve kenarlar ``_band_warning_mm``
            # gösterimiyle — gösterilen çap gösterilen alt kenara eşit
            # yuvarlanıp "bandın altında" hükmüyle çelişmez.
            if classify_orifice_d(d, d_min, d_max) == ORIFICE_D_CLASS_BELOW:
                d_g, lo_g, hi_g = _band_warning_mm(d, d_min, d_max)
                warnings.append(_w(
                    'warn.injector.orifice_d_below_manufacturing_band',
                    'warning',
                    d_mm=d_g, d_min_mm=lo_g, d_max_mm=hi_g))
            elif d < d_lo:
                # 10. tur (HB9 devir 46): yalnız çap GERÇEKTEN tercih bandının
                # altındaysa. Dar bir çağıran bandında yeniden çözülen çap
                # d_max'ı aşabilir; o hâli aşağıdaki son kapı adıyla söyler
                # (eski ``else`` ona da "tercih bandının altında" diyordu).
                d_g, lo_g, hi_g = _band_warning_mm(d, d_lo, d_hi)
                warnings.append(_w(
                    'warn.injector.orifice_d_below_pref_band', 'warning',
                    d_mm=d_g, band_lo_mm=lo_g, band_hi_mm=hi_g))
        elif d < d_lo:
            # ÖH D20 / B4-12 — SESSİZ GEÇEN DÖRDÜNCÜ HÂL.
            # Üstteki üç dal ``d > d_max`` / ``d > d_hi`` / ``d < d_min``
            # hâllerini kapatıyordu; geriye ``d_min <= d < d_lo`` kalıyordu ve
            # o aralık HİÇ uyarı üretmiyordu. Aynı çapı ``n_fixed`` yolundan
            # isteyen kullanıcı ``fixed_n_outside_pref_band`` uyarısını
            # ALIYOR, ``n_max`` yolundan gelen ALMIYORDU — aynı geometri için
            # iki farklı hüküm. ÖLÇÜLDÜ (D20 a1/once.json ``B4_12``,
            # ``dar_d_min_sondaji``): n=120, d=0,044731 mm; n_fixed yolu 1
            # uyarı, n_max yolu 0 uyarı.
            # NOT (dürüst kapsam): ürünün KENDİ ``DEFAULT_CONSTRAINTS``
            # değerleriyle bu aralık ULAŞILAMAZ. D20'de (o zamanki d_min
            # 0,3 mm, n_max 120) 4000 noktalık tarama 0 örnek bulmuştu; ÖH
            # D37 A2 hibrit F-10'dan beri d_min ≡ d_lo = 0,5 mm (tek kaynak
            # ``ORIFICE_D_BAND_MM``) olduğundan [d_min, d_lo) aralığı varsayılan
            # kısıtla BOŞ kümedir. Ulaşılabilirlik koşulu (yalnız çağıran kendi
            # kısıt sözlüğünü verirse) ``d_min_mm < d_lo/sqrt(n_max)`` =
            # 0,5/√120 = 0,04564 mm'dir. Kapı yine de kapatıldı: kısıt sözlüğü
            # bu fonksiyonun genel arayüzüdür.
            d_g, lo_g, hi_g = _band_warning_mm(d, d_lo, d_hi)
            warnings.append(_w(
                'warn.injector.orifice_d_below_pref_band', 'warning',
                d_mm=d_g, band_lo_mm=lo_g, band_hi_mm=hi_g))
        best = (n, d)
    n, d = best
    _caller_band_gate(n, d, d_min, d_max, n_max, warnings, _uyari_basi)
    _near_lower_edge_warning(d, d_min, d_max, warnings)
    return int(n), float(d)


# ---------------------------------------------------------------------------
# ÖH D37 A2 hibrit · 9. tur (7. tur Devir 35) — bant dışı uyarı gösterimi.
# Bu blok BİLEREK ``_plan_orifices``ten SONRA durur: yukarıdaki satır
# numaraları ``formal/registry.json`` Lean çapalarıdır (orificeCount).
# ---------------------------------------------------------------------------
#: Bant / tercih bandı DIŞI uyarılarında çapın ve bant kenarlarının EN AZ
#: ondalık sayısı (eski gösterimdeki çap ondalığı; bu ondalıkta çelişki
#: yoksa yayımlanan parametre bit-aynı kalır). Gösterim kenara yuvarlanıp
#: hükümle çelişirse ondalık sayısı ``ORIFICE_D_NEAR_WARNING_DECIMALS_MAX``e
#: kadar artırılır (``_band_warning_mm``).
ORIFICE_D_BAND_WARNING_DECIMALS = 2


def _band_warning_mm(d, d_lo, d_hi):
    """Bant (ya da tercih bandı) DIŞI uyarısının çap ve kenarları [mm].

    ÖH D37 A2 hibrit · 9. tur (7. tur Devir 35; Ş6-3'ün kardeşi). ÖLÇÜLDÜ
    (rapor 9. tur, ``olc9.py`` ``serbest_d0.4975``): çap iki, kenarlar bir
    ondalıkla yuvarlanıyordu; d ∈ [0,495; 0,5) mm'de yayımlanan metin
    "d=0.5 mm is outside the manufacturing band (0.5-2.5 mm), below its lower
    limit" diyordu — gösterilen çap gösterilen kenara EŞİT, metin kendi
    hükmüyle çelişiyordu (hüküm doğruydu: d < 0,5). İki ondalıklı çağıran
    bandı (0,35 mm) da kenarda 0,3'e dönüyordu.

    Girdi metre (``d``, ``d_lo``, ``d_hi`` aynı birimde). Üçü AYNI ondalıkla,
    en az ``ORIFICE_D_BAND_WARNING_DECIMALS`` ile yayımlanır; yuvarlanmış
    çapın yuvarlanmış kenarlara göre konumu (altında / içinde / üstünde)
    gerçek konumdan farklıysa ondalık sayısı artırılır. Yuvarlama tekdüze
    olduğu için içerideki çap içeride kalır. Hüküm çağıranın
    (``classify_orifice_d`` ya da tercih bandı karşılaştırması); bu işlev
    yalnız gösterimdir.
    """
    k = band_warning_decimals(d, d_lo, d_hi)
    return (round(float(d) * 1e3, k), round(float(d_lo) * 1e3, k),
            round(float(d_hi) * 1e3, k))


def band_warning_decimals(d, d_lo, d_hi):
    """``_band_warning_mm``in ondalık sayısı (metin üreten çağıranlar için).

    utils plaka yolu bant dışı çapı f-dizesiyle basar (çarpışmalı kırpma
    metinleri); aynı kural oradan bu işlevle uygulanır, eşik kopyalanmaz.
    Girdi metre; dönüş: en az ``ORIFICE_D_BAND_WARNING_DECIMALS``.
    """
    d, d_lo, d_hi = float(d), float(d_lo), float(d_hi)

    def _konum(x, a, b):
        return -1 if x < a else (1 if x > b else 0)

    gercek = _konum(d, d_lo, d_hi)
    d_mm, lo_mm, hi_mm = d * 1e3, d_lo * 1e3, d_hi * 1e3
    k = ORIFICE_D_BAND_WARNING_DECIMALS
    while (k < ORIFICE_D_NEAR_WARNING_DECIMALS_MAX
           and _konum(round(d_mm, k), round(lo_mm, k),
                      round(hi_mm, k)) != gercek):
        k += 1
    return k


def _manifold(mdot, rho, v_orifice, a_orifice_m2):
    """Manifold boyutlandırma: hedef hız oranından çap, sonra GERÇEKLENEN oran.

    v2.6.26 KUSUR DÜZELTMESİ — TOTOLOJİ. Eski sürüm hızı
    ``v_man = 0.1 * v_orifice`` ile KENDİSİ belirleyip hemen ardından
    ``v_ratio = v_man / v_orifice`` yayımlıyordu: sonuç cebirsel olarak
    DAİMA 0,1 idi. ``area_ratio`` ise hiç hesaplanmıyordu bile, doğrudan
    ``1 / 0.1 = 10`` yazılıyordu. İkisi de kullanıcıya "gerçeklenen oran"
    diye sunuluyor ama hiçbir şey ölçmüyordu. Üstelik ``MANIFOLD_V_RATIO_MAX``
    ve ``MANIFOLD_AREA_RATIO_MIN`` bekçi sabitleri depo genelinde YALNIZ
    tanımlandıkları satırda geçiyordu — hiçbir karşılaştırmaya girmeyen ölü
    sabitlerdi.

    Şimdi oranlar devrenin GERÇEKLENEN orifis akış alanına (``a_orifice_m2``
    = n · π/4 · d², delik planı çözüldükten sonraki alan) göre hesaplanır:

    * A_orifis ≡ ṁ/(ρ·v_orifis) özdeşliği geçerli olduğunda oran hedefe
      BİREBİR eşit çıkar. Bu bir ölçüm değil bir özdeşliktir ve
      ``v_ratio_is_tautological`` bayrağıyla açıkça öyle bildirilir
      (``structural_analysis.safety_factor_is_tautological`` deseni).
    * D15/P1B4-01 ÖNCESİ bu özdeşlik YALNIZ SPI devresinde geçerliydi: NHNE
      (N₂O) devresinde alan iki fazlı kütle akısından çözülüyor ama
      ``v_orifice`` tek fazlı SPI bağıntısından geliyordu, bu yüzden oran
      hedeften ayrılıyordu (ölçülmüştü: a_man/a_orifis ≈ 7,2-7,6, hedef 10).
      O ayrılma bir FİZİK bulgusu değil, çağıranın iki farklı akış modelinden
      okuduğu iki sayının artığıydı. ``_solve_circuit`` artık her devrede
      süreklilik hızını yayımladığı için özdeşlik İKİ dalda da geçerlidir ve
      bayrak iki dalda da ``True`` döner — manifold hedefe göre
      boyutlandırıldığından bu beklenen sonuçtur, gizlenmez.

    Her iki oran bekçi sınırlarıyla artık gerçekten KARŞILAŞTIRILIR ve sonuç
    ``*_within_limit`` bayraklarıyla yayımlanır.
    """
    v_man_target = MANIFOLD_V_RATIO_TARGET * v_orifice
    a_man = mdot / max(rho * v_man_target, 1e-12)
    d_man = np.sqrt(4.0 * a_man / np.pi)
    # Gerçeklenen kesitler: çap bir standart boru ölçüsüne yuvarlanırsa
    # (bugün yuvarlanmıyor) buradan geri hesap hedeften ayrılır.
    a_man_real = np.pi * d_man ** 2 / 4.0
    v_man_real = mdot / max(rho * a_man_real, 1e-12)
    a_orifice = max(float(a_orifice_m2), 1e-12)
    v_orifice_real = mdot / max(rho * a_orifice, 1e-12)
    v_ratio = float(v_man_real / max(v_orifice_real, 1e-9))
    area_ratio = float(a_man_real / a_orifice)
    tautological = bool(abs(v_ratio - MANIFOLD_V_RATIO_TARGET) < 1e-9)
    return {
        'd_mm': float(d_man * 1e3),
        'velocity_m_s': float(v_man_real),
        # GERÇEKLENEN oran: manifold kesitinden ve delik planının gerçek
        # alanından geri hesap.
        'v_ratio': v_ratio,
        'v_ratio_basis': (
            'achieved manifold/orifice velocity ratio, computed back from the '
            'sized manifold area and the realised orifice flow area '
            '(n*pi/4*d^2). The orifice velocity is published from continuity '
            '(mdot/(rho*A_orifice)) in every circuit, SPI and NHNE alike, so '
            'A_orifice = mdot/(rho*v_orifice) is an identity and the achieved '
            f'ratio reproduces the target {MANIFOLD_V_RATIO_TARGET:g} exactly '
            '- see v_ratio_is_tautological. '
            f'Acceptance limit {MANIFOLD_V_RATIO_MAX:g} '
            '(Huzel & Huang Ch. 4 manifold practice)'),
        'v_ratio_is_tautological': tautological,
        'v_ratio_within_limit': bool(v_ratio <= MANIFOLD_V_RATIO_MAX),
        'v_ratio_target': float(MANIFOLD_V_RATIO_TARGET),
        'v_ratio_target_is_target': True,
        'area_ratio': area_ratio,
        'area_ratio_basis': (
            'achieved manifold cross-section area divided by the realised '
            'orifice flow area; the reciprocal of the velocity ratio by '
            f'continuity, so the design target is 1/{MANIFOLD_V_RATIO_TARGET:g}'
            f' and the acceptance floor is {MANIFOLD_AREA_RATIO_MIN:g} '
            '(Huzel & Huang Ch. 4)'),
        'area_ratio_within_limit': bool(area_ratio >= MANIFOLD_AREA_RATIO_MIN),
    }


# ---------------------------------------------------------------------------
# Devre çözümü (ox veya fuel)
# ---------------------------------------------------------------------------

def _solve_circuit(circuit, mdot, rho, pc_bar, dp_ratio, p_feed_bar, fluid,
                   T_K, inlet, l_over_d, constraints, warnings,
                   assumptions, cd_override=None, cd_basis_override=None,
                   n_fixed=None, orifice_length_m=None,
                   l_over_d_supplied=False, cd_override_from_user=False):
    """Tek devre (ox/fuel) akış + delik planı + manifold + flip çözümü.

    ``circuit`` ∈ {'ox', 'fuel'} — dil-nötr devre kimliği. Uyarı kodu bundan
    seçilir; ValueError metinleri ``_CIRCUIT_LABEL`` etiketini kullanır.

    ``orifice_length_m``: orifis uzunluğu = enjektör plakası kalınlığı [m].
    Verilirse L/D geometriden çözülür (bkz. gövdedeki sabit-nokta notu);
    verilmezse ``l_over_d`` argümanı beyan edilen varsayım olarak kullanılır.
    """
    name = _CIRCUIT_LABEL[circuit]
    spec_p_feed_given = p_feed_bar is not None
    if p_feed_bar is None:
        p_feed_bar = pc_bar * (1.0 + dp_ratio)

    is_n2o = (fluid == 'n2o')
    p_sat_bar = None
    if is_n2o:
        if T_K is None:
            raise ValueError(
                "T_ox_K (saturation temperature) is required for the N2O circuit")
        p_sat_bar = _SAT.psat(T_K) / PA_PER_BAR
        # Kendinden basınçlı doymuş tank: p_feed verilmemişse P₁ = P_sat
        # (ARGE Ö2 örneğiyle tutarlı — ΔP burada tasarım değişkeni değil,
        # tank sıcaklığının sonucudur).
        #
        # v2.6.2 DÜZELTMESİ (F039): kullanıcı p_feed verdiğinde eski kod
        # P₁ = min(p_feed, P_sat) ile doymanın ÜSTÜNÜ yasaklıyordu. Helyum ile
        # süper-şarj edilmiş (aşırı soğutulmuş) N₂O tankı yaygın bir uçuş
        # konfigürasyonudur ve P₁ > P_sat tamamen geçerlidir; NHNE bunu zaten
        # doğru ele alır (κ = √((P₁−P₂)/(P_v−P₂)) büyür → SPI'ye yaklaşır).
        # Kelepçe, 70 bar süper-şarjda birim alan debisini %61 düşürüp
        # enjeksiyon alanını ~1.6 kat fazla boyutlandırıyordu.
        # Kaynak: Dyer ve ark. AIAA 2007-5702 (NHNE aşırı-soğutulmuş dalı);
        # Zilliac & Karabeyoglu AIAA 2005-3549 (süper-şarjlı N₂O beslemesi).
        if spec_p_feed_given:
            p1_bar = p_feed_bar
            if p1_bar > p_sat_bar:
                assumptions.append(_w(
                    'warn.injector.n2o_supercharged_feed', 'info',
                    p_feed_bar=round(float(p1_bar), 2),
                    p_sat_bar=round(float(p_sat_bar), 2),
                    T_K=round(float(T_K), 1)))
        else:
            p1_bar = p_sat_bar
        if rho is None:
            rho = _SAT.rho_l(T_K)
            assumptions.append(_w(
                'warn.injector.rho_ox_from_saturation_table', 'info',
                rho=round(float(rho), 0), T_K=round(float(T_K), 1)))
    else:
        p1_bar = p_feed_bar
        if rho is None:
            raise ValueError(
                f"Density (rho) is required for the {name} circuit")

    # ÖH D23 / P7B1-18 — YOĞUNLUK POZİTİF OLMAK ZORUNDA.
    #
    # ÖLÇÜLDÜ (``a4/once_a4.json`` ``P7B1-18``, taban 3c0a43e):
    # ``rho_ox = -5`` gövdesi HTTP **500** ve mesaj
    # *"float() argument must be a string or a real number, not 'complex'"*
    # veriyordu. Kök neden ilgisiz bir iç ayrıntıdır: alan boyutlandırması
    # ``A = mdot / (Cd . sqrt(2 . rho . dP))`` bağıntısını kullanır ve
    # negatif yoğunlukta karekök KARMAŞIK sayı döner; hata kullanıcının
    # yazdığı alandan (``rho_ox``) 400 satır uzakta, ``float()`` çağrısında
    # patlıyordu. Sunucu arızası değildir — istemcinin FİZİK hatasıdır ve
    # 500 bunu yanlış sınıflandırır (destek talebi doğurur, istemci
    # yeniden dener).
    #
    # Kapı burada, DEĞERİN OKUNDUĞU yerdedir: kütle yoğunluğu tanım gereği
    # pozitiftir (m/V, ikisi de pozitif). Yeni bant icat edilmedi; sıfır da
    # reddedilir çünkü sıfır yoğunlukta ``sqrt(2.rho.dP) = 0`` ve alan
    # bölmesi tanımsızdır. ``None`` bu noktaya gelemez (yukarıdaki iki kol
    # onu ya doldurur ya adıyla reddeder).
    try:
        rho = float(rho)
    except (TypeError, ValueError):
        raise ValueError(
            f"Density (rho) for the {name} circuit must be numeric "
            f"(got: {rho!r})")
    if not np.isfinite(rho) or rho <= 0.0:
        raise ValueError(
            f"Density (rho) for the {name} circuit must be a positive "
            f"finite number (got: {rho:g}); mass density is m/V and both "
            "are positive, and the orifice area follows "
            "A = mdot / (Cd . sqrt(2 . rho . dP)), which is undefined "
            "otherwise.")

    dp_bar = p1_bar - pc_bar
    if dp_bar <= 0:
        raise ValueError(
            f"dP <= 0 in the {name} circuit (P1={p1_bar:.1f} bar, "
            f"Pc={pc_bar:.1f} bar): feed pressure must exceed chamber pressure")
    dp_pa = dp_bar * PA_PER_BAR

    # v3.0.1 (kulvar T) — NHNE ALAN DENETİMİ. Dyer (AIAA 2007-5702) karışım
    # parametresi κ = √((P₁−P₂)/(P_v−P₂)) YALNIZ P₂ < P_v iken tanımlıdır.
    # ÖLÇÜLDÜ (rapor, kulvar T): T = 260 K (P_v = 21,93 bar), P_c = 30 bar,
    # P₁ = 50 bar → ``nhne_mass_flow`` debiyi doğru biçimde tek fazlı SPI
    # dalından çözüyordu (karekök hesaplanmıyor), ama devre ``flow_model``
    # 'NHNE' ve κ = inf yayımlıyordu: etiket hesabı söylemiyordu. Kendinden
    # basınçlı kipte bu alan ERİŞİLMEZ (P₁ = P_v ve ΔP > 0 ⇒ P₂ < P_v); yalnız
    # aşırı soğutulmuş (takviyeli) girişte P₂ ≥ P_v olabilir.
    nhne_alani = (not is_n2o) or (pc_bar < p_sat_bar)

    def _size(cd_value):
        """Verilen Cd ile toplam alan + delik planı (n, d) döndürür."""
        if is_n2o:
            probe = nhne_mass_flow(cd_value, 1.0, p1_bar, pc_bar, p_sat_bar,
                                   T_K, rho)
            g_unit = probe['mdot_kg_s']   # kg/s, birim alan başına (Cd dahil)
            model = 'NHNE' if nhne_alani else 'SPI'
        else:
            g_unit = spi_mass_flow(cd_value, 1.0, rho, dp_pa)
            model = 'SPI'
        area = mdot / max(g_unit, 1e-12)
        n_local, d_local = _plan_orifices(area, constraints, warnings,
                                          n_fixed=n_fixed)
        return n_local, d_local, model

    # --- Deşarj katsayısı --------------------------------------------------
    # v2.6.26: orifis uzunluğu (enjektör plakası kalınlığı) verilirse L/D
    # ARTIK GEOMETRİDEN çözülür. L/D = t_plaka / d_orifis olduğundan Cd ile
    # delik çapı birbirine bağlıdır: sabit-nokta yinelemesiyle kapatılır
    # (Cd -> alan -> delik planı -> L/D -> Cd). Tablonun kendisi bantlı
    # olduğu için iki-üç adımda kilitlenir; kilitlenmezse son adım kullanılır
    # ve ulaşılan L/D çıktıda beyan edilir.
    # Kaynak: NASA SP-8089 / Lefebvre & McDonell, "Atomization and Sprays"
    # Böl. 5 (düz orifis Cd — giriş geometrisi ve L/D bağımlılığı).
    # v2.6.26 — BEYAN GERCEGE BAGLI.
    # Bu metin kosulsuz 'caller-supplied' diyordu; oysa cagiran cogu
    # zaman L/D vermiyor ve deger modul varsayilani 4,0 oluyordu.
    # Kullanici 'bu tasarim icin 4 secildi' diye okuyor, kimse
    # secmemis. Yanlis beyan, beyansizliktan kotudur: ortada bir insan
    # karari varmis izlenimi verir.
    l_over_d_basis = ('caller-supplied L/D (declared assumption)'
                      if l_over_d_supplied else
                      'module default L/D (no orifice length or L/D '
                      'supplied by the caller)')
    # ÖH D16 (kalem B4-05): L/D'nin KAZANILMIŞ olup olmadığı ayrı taşınır —
    # hidrolik flip hükmü bu orana bakıyor ve modül varsayılanından hüküm
    # üretmek yasaktır (aşağıda 'hydraulic_flip_risk_basis').
    l_over_d_kazanildi = bool(l_over_d_supplied)
    if cd_override is not None:
        cd, cd_basis = cd_override, (cd_basis_override or 'type-specific Cd')
        n, d, flow_model = _size(cd)
        # Cd KULLANICIDAN geldiyse yineleme gerekmez (Cd zaten sabit), ama
        # plaka kalınlığı biliniyorsa L/D artık GEOMETRİKTİR ve tek adımda
        # çözülür. Bu yalnız rapor kalemi değildir: hidrolik flip ölçütü
        # (Nurick) L/D'yi okur — eski varsayılan 4,0 ile bırakmak, hükmü
        # kullanıcının plakasıyla ilgisi olmayan bir orana dayandırırdı.
        # Swirl dalı BİLEREK dışarıdadır: orada Cd de akış da girdap
        # odasının geometrisinden gelir, düz orifis L/D'si tanımlı değildir.
        if (cd_override_from_user and orifice_length_m
                and float(orifice_length_m) > 0.0):
            t_orifice = float(orifice_length_m)
            l_over_d = t_orifice / max(d, 1e-9)
            l_over_d_kazanildi = True
            l_over_d_basis = (
                f'L/D = orifice length {t_orifice * 1e3:.2f} mm / '
                f'solved orifice diameter {d * 1e3:.3f} mm (the diameter '
                'follows from the USER-supplied Cd, so no Cd iteration is '
                'run)')
    elif orifice_length_m and float(orifice_length_m) > 0.0:
        t_orifice = float(orifice_length_m)
        cd, cd_basis = discharge_coefficient(inlet, l_over_d)
        for _ in range(6):
            n, d, flow_model = _size(cd)
            ld_new = t_orifice / max(d, 1e-9)
            cd_new, basis_new = discharge_coefficient(inlet, ld_new)
            l_over_d = float(ld_new)
            if cd_new == cd:
                cd_basis = basis_new
                break
            cd, cd_basis = cd_new, basis_new
        n, d, flow_model = _size(cd)
        l_over_d = t_orifice / max(d, 1e-9)
        l_over_d_kazanildi = True
        l_over_d_basis = (f'L/D = orifice length {t_orifice * 1e3:.2f} mm / '
                          f'solved orifice diameter {d * 1e3:.3f} mm')
    else:
        cd, cd_basis = discharge_coefficient(inlet, l_over_d)
        n, d, flow_model = _size(cd)

    a_total = n * np.pi * d ** 2 / 4.0
    # Efektif enjeksiyon hızı — SÜREKLİLİKTEN, yani AYNI yanıtta yayımlanan
    # kütle debisi, sıvı yoğunluğu ve toplam orifis alanından.
    #
    # D15/P1B4-01 — HIZ İLE ALAN AYNI AKIŞ MODELİNDEN GELİR.
    # ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/hibrit/a1/once2.json; hibrit
    # 5 kN, Pc = 30 bar, O/F = 6, N2O 293,15 K): burada hız TEK FAZLI SPI
    # özdeşliğinden (cd·sqrt(2Δp/ρ)) hesaplanıyordu, oysa a_total
    # yukarıda İKİ FAZLI NHNE kütle akısından çözülmüştü. İki büyüklük
    # aynı yanıtta yayımlanıyor ve birbirini tutmuyordu:
    #     velocity_m_s        = 56,4263 m/s
    #     ṁ/(ρ·A_total)       = 42,6908 m/s      → oran 1,32174 (+%32,17)
    # SPI devresinde (LOX, aynı kurulum) oran TAM 1,000000 idi: özdeşlik
    # yalnız NHNE dalında kırılıyordu.
    #
    # Yön tehlikeli: hız SMD korelasyonlarına giriyor (:1694 v_ox) ve
    # SMD ∝ v^(−2/3) olduğundan damlacık çapı OLDUĞUNDAN KÜÇÜK
    # görünüyordu — atomizasyon ve yanma verimi iyimser okunuyordu.
    # Ayrıca momentum oranı/TMR (:1716, :1766, :1876) ve manifold oranı
    # (:1178) hep bu hızı okuyor.
    #
    # Süreklilik yazımı SPI dalında bir DEĞİŞİKLİK DEĞİLDİR, bir
    # genelleştirmedir: SPI'de A = ṁ/(cd·sqrt(2ρΔp)) olduğundan
    # ṁ/(ρ·A) ≡ cd·sqrt(2Δp/ρ) — ölçülen oran zaten 1,000000. NHNE'de ise
    # alan iki fazlı akıdan çözüldüğü için tek doğru sıvı giriş hızı
    # süreklilikten gelendir. Uyarı basıp iki sayıyı da yayımlamak beyandır,
    # çözüm değildir: yayımlanan hız yanlıştır.
    v_inj = float(mdot / (rho * a_total))

    nhne_block = None
    if is_n2o:
        full = nhne_mass_flow(cd, a_total, p1_bar, pc_bar, p_sat_bar, T_K, rho)
        nhne_block = {'kappa': full['kappa'],
                      'mdot_spi_kg_s': full['mdot_spi_kg_s'],
                      'mdot_hem_kg_s': full['mdot_hem_kg_s'],
                      'p_sat_bar': float(p_sat_bar),
                      'quality_out': full['quality_out'],
                      'quality_at_flow_station':
                          full['quality_at_flow_station'],
                      'choked': full['choked'],
                      'flow_station_pressure_bar':
                          full['flow_station_pressure_bar']}
        if not nhne_alani:
            # κ tanımsız: sonsuz sayı yayımlanmaz (JSON'da sayı değildir),
            # alanın neden boş olduğu adıyla söylenir.
            nhne_block['kappa'] = None
            nhne_block['domain'] = (
                f'not applicable: the back pressure P_2 = P_c = '
                f'{float(pc_bar):.4g} bar is at or above the vapour pressure '
                f'P_v = {float(p_sat_bar):.4g} bar, so no flashing occurs in '
                'the orifice and the Dyer NHNE mixing parameter '
                'kappa = sqrt((P_1-P_2)/(P_v-P_2)) is undefined; the flow is '
                'single-phase incompressible (SPI) with the inlet liquid '
                'density (Dyer et al., AIAA 2007-5702)')

    # Nurick kavitasyon sayısı: K_c = (P₁ − P_v)/(P₁ − P₂)
    if is_n2o:
        p_v_bar = p_sat_bar
        p_v_basis = 'n2o saturation table'
    else:
        p_v_bar, p_v_basis = liquid_vapor_pressure(fluid, T_K)
        # NOT: uyarı metninin parametre kümesi DEĞİŞTİRİLMEDİ (i18n sözlüğü
        # bu partinin dosyası değil). Buhar basıncının hangi akışkandan ve
        # hangi referans noktadan geldiği devre sözlüğündeki
        # 'vapor_pressure_basis' alanında taşınır.
        assumptions.append(_w(
            'warn.injector.vapor_pressure_assumed_ox' if circuit == 'ox' else
            'warn.injector.vapor_pressure_assumed_fuel', 'info',
            p_v_bar=float(p_v_bar)))
    k_c = (p1_bar - p_v_bar) / max(p1_bar - pc_bar, 1e-9)
    # ÖH D16 (kalem B4-05) — KAZANILMAMIŞ HÜKÜM YAYIMLANMAZ.
    # Nurick ölçütü L/D'yi okur. Çağıran ne orifis uzunluğu/plaka kalınlığı
    # ne de L/D verdiyse L/D modülün 4,0 varsayılanıdır ve bu değer flip
    # bandının (1,0 <= L/D <= 5,0) TAM ORTASINA düşer: hüküm o zaman
    # kullanıcının girmediği bir sayıdan doğar. ÖLÇÜLDÜ (1 Eylül 2026,
    # taban 6fde52b; ṁ_ox = 2 kg/s, Pc = 30 bar, N2O 293,15 K):
    #   plaka verilmedi -> L/D = 4,000000 (modül varsayılanı),
    #                      hydraulic_flip_risk = True,  A = 59,677780 mm²
    #   plaka  2,0 mm   -> L/D = 0,824808, flip = False, A = 73,886402 mm²
    #   plaka 15,0 mm   -> L/D = 6,186057, flip = False, A = 55,414802 mm²
    # yani hem güvenlik hükmü hem enjeksiyon alanı (-%7,1 … +%23,8)
    # girilmemiş bir plaka kalınlığından geliyordu; hibrit Python API
    # yolunda hüküm ÜÇ KOŞUDA DA True çıkıyordu (yanlış alarm).
    # Doymuş N2O'da ayrıca K_c = (p1 - p_v)/(p1 - pc) payı ÖZDEŞ SIFIRDIR
    # (ölçülen K_c = -1,745e-05), yani hüküm tamamen L/D + giriş kenarına
    # iniyor — L/D kazanılmamışsa geriye hüküm kalmaz.
    # Ürün (web) yolunda plaka kalınlığı GÖNDERİLİYOR (advanced.html), yani
    # orada hüküm kazanılmış kalır ve davranış DEĞİŞMEZ.
    flip_ham = hydraulic_flip_risk(inlet, l_over_d, k_c)
    if l_over_d_kazanildi:
        flip = flip_ham
        flip_basis = (
            f'Nurick criterion on the solved geometry: inlet={inlet}, '
            f'L/D={float(l_over_d):.4g}, cavitation number '
            f'K_c={float(k_c):.6g} (flip limit {float(FLIP_KC_LIMIT)}). '
            f'L/D basis: {l_over_d_basis}')
    else:
        flip = None
        flip_basis = (
            'NOT DECIDED: the hydraulic-flip criterion (Nurick) reads L/D, '
            'and the caller supplied neither an orifice length / plate '
            'thickness nor an L/D, so L/D is the module default '
            f'({float(l_over_d):.4g}) rather than this design\'s geometry. '
            'A safety verdict is not published from a number nobody chose; '
            'supply orifice_length_m (or plate_thickness_m) to obtain one. '
            f'For reference, the criterion applied to the default L/D would '
            f'read {flip_ham!r} at K_c={float(k_c):.6g}.')
    if flip:
        warnings.append(_w(
            'warn.injector.hydraulic_flip_risk_ox' if circuit == 'ox' else
            'warn.injector.hydraulic_flip_risk_fuel', 'warning',
            l_over_d=float(l_over_d), k_c=round(float(k_c), 2),
            limit=float(FLIP_KC_LIMIT)))

    return {
        'mdot_kg_s': float(mdot),
        'delta_p_bar': float(dp_bar),
        'dp_pc_ratio': float(dp_bar / pc_bar),
        'velocity_m_s': v_inj,
        'cd': float(cd), 'cd_basis': cd_basis,
        # v2.6.26: Cd'nin geometrik dayanağı çıktıda taşınır.
        'l_over_d': float(l_over_d),
        'l_over_d_basis': l_over_d_basis,
        'orifice_inlet': str(inlet),
        'vapor_pressure_bar': float(p_v_bar),
        'vapor_pressure_basis': p_v_basis,
        'n_orifices': int(n),
        'orifice_d_mm': float(d * 1e3),
        'total_area_mm2': float(a_total * 1e6),
        'flow_model': flow_model,
        'nhne': nhne_block,
        'cavitation_number': float(k_c),
        'hydraulic_flip_risk': flip,
        'hydraulic_flip_risk_basis': flip_basis,
        # ÖH KU H-8 / KC-11 — YENİ BİLGİ ALANLARI (hiçbir çözülen sayıyı
        # değiştirmez): Cd rejim etiketi, SP-8089 flip-duyarlı L/D bandı,
        # 0,015 in tıkanma alt sınırı. Uyarı KODU değil alandır: kod
        # eklemek i18n sözlüğünü ister ve o dosya bu kulvarın değil.
        'cd_regime': (discharge_coefficient_regime(inlet, l_over_d)
                      if cd_override is None else
                      f'not applicable: Cd is not from the orifice table '
                      f'({cd_basis})'),
        'hydraulic_flip_sensitive_band': hydraulic_flip_sensitive_band(
            l_over_d, l_over_d_kazanildi),
        'orifice_plugging_check': orifice_plugging_check(d * 1e3),
        # Manifold oranları GERÇEKLENEN orifis alanına göre çözülür (a_total),
        # yoksa oran kendi hedefinden geri hesaplanmış olur (bkz. _manifold).
        'manifold': _manifold(mdot, rho, v_inj, a_total),
        '_rho': float(rho),  # iç kullanım (tip geometrisi); çıktıda kalır, zararsız
    }


def n2o_vapor_pressure_bar(T_K):
    """Devrenin KULLANDIĞI N₂O buhar (doyma) basıncı P_v(T) [bar].

    v3.0.1 (Ayberk tur 1 · kulvar T): kendinden basınçlı kipte devre
    P₁ = P_v alır; kullanıcı tank basıncı kipinde ise P₁ = P_tank verilir ve
    doyma şartı (P_tank ≥ P_v) motor/uç kapısında denetlenir. Kapının
    karşılaştırdığı sayı bu devrenin NHNE'ye verdiği P_v ile BİREBİR aynı
    olmalıdır — aynı ``_SAT`` tablosu (tabloyla deterministik yol), ikinci
    bir doyma kaynağı açılmaz. Sıcaklık doyma zarfının dışındaysa
    ``N2OSaturation`` ValueError yükseltir (sayı uydurulmaz).

    Konum: ``_solve_circuit``ten SONRA — yukarıdaki satırlar
    ``formal/registry.json`` Lean çapasıdır (``_plan_orifices``, :1399).
    """
    return float(_SAT.psat(float(T_K)) / PA_PER_BAR)


# ---------------------------------------------------------------------------
# Ana giriş noktası
# ---------------------------------------------------------------------------

def _design_gas_gas_coaxial(spec, warnings, assumptions):
    """Gaz-gaz shear-coax enjektör (FFSC/staged combustion ana odası).

    İç jet (varsayılan ox-zengin gaz) + dış anülüs (yakıt-zengin gaz), her
    ikisi de sıkıştırılabilir orifis akışı. Girdi olarak HER İKİ akımın ön
    yakıcı egzoz koşulları (T0, P0, gamma, MW/R) dışarıdan gelir — varsayılan
    sabit yoktur. Karışım kriteri momentum-akı oranı J ve hız oranı VR.

    Atomizasyon/SMD gaz-gaz için ANLAMSIZDIR (damlacık yok) → None döner.
    """
    pc_bar = float(spec['Pc_bar'])
    pc_pa = pc_bar * PA_PER_BAR

    mdot_ox = spec.get('mdot_ox')
    mdot_fuel = spec.get('mdot_fuel')
    if not mdot_ox or mdot_ox <= 0:
        raise ValueError('gas_gas_coaxial: mdot_ox must be positive (kg/s)')
    if not mdot_fuel or mdot_fuel <= 0:
        raise ValueError(
            'gas_gas_coaxial: mdot_fuel is required (kg/s, > 0) - the main '
            'chamber is fed by two preburners')

    gas_ox = _require_gas_stream(spec, 'gas_ox', 'oxidiser gas')
    gas_fuel = _require_gas_stream(spec, 'gas_fuel', 'fuel gas')

    cd = spec.get('cd')
    if cd is None:
        cd = GAS_GAS_CD_DEFAULT
        assumptions.append(_w(
            'warn.injector.gas_post_cd_assumed', 'info',
            cd=float(GAS_GAS_CD_DEFAULT)))
    cd = float(cd)

    inner_stream = str(spec.get('inner_stream', 'ox')).lower()
    if inner_stream not in ('ox', 'fuel'):
        raise ValueError("inner_stream must be 'ox' or 'fuel'")
    if spec.get('inner_stream') is None:
        assumptions.append(_w('warn.injector.gas_inner_stream_assumed', 'info'))

    # Akım koşulları (birim alan → mass_flux; alan bağımsız)
    r_ox = _gas_r_specific(gas_ox, 'oxidiser gas')
    r_fuel = _gas_r_specific(gas_fuel, 'fuel gas')
    p0_ox = float(gas_ox['P0_bar']) * PA_PER_BAR
    p0_fuel = float(gas_fuel['P0_bar']) * PA_PER_BAR
    g_ox = float(gas_ox['gamma'])
    g_fuel = float(gas_fuel['gamma'])
    t0_ox = float(gas_ox['T0_K'])
    t0_fuel = float(gas_fuel['T0_K'])

    if p0_ox <= pc_pa:
        raise ValueError(
            f"oxidizer gas: P0={p0_ox/PA_PER_BAR:.1f} bar <= "
            f"Pc={pc_bar:.1f} bar - feed pressure must exceed chamber "
            "pressure (dP > 0)")
    if p0_fuel <= pc_pa:
        raise ValueError(
            f"fuel gas: P0={p0_fuel/PA_PER_BAR:.1f} bar <= "
            f"Pc={pc_bar:.1f} bar - feed pressure must exceed chamber "
            "pressure (dP > 0)")

    st_ox = compressible_orifice_flow(cd, 1.0, p0_ox, t0_ox, g_ox, r_ox, pc_pa)
    st_fuel = compressible_orifice_flow(cd, 1.0, p0_fuel, t0_fuel, g_fuel,
                                        r_fuel, pc_pa)

    a_ox = mdot_ox / max(st_ox['mass_flux'], 1e-12)      # m² toplam ox alanı
    a_fuel = mdot_fuel / max(st_fuel['mass_flux'], 1e-12)  # m² toplam yakıt alanı

    # Eleman sayısı iç akımın (post) alanından belirlenir
    if inner_stream == 'ox':
        inner_area = a_ox
        outer_area = a_fuel
    else:
        inner_area = a_fuel
        outer_area = a_ox
    n, d_inner = _plan_gas_elements(inner_area, warnings, inner_stream)

    a_ann_e = outer_area / n
    t_wall = max(GAS_POST_WALL_MIN_MM * 1e-3, GAS_POST_WALL_T_OVER_D * d_inner)
    d_post_outer = d_inner + 2.0 * t_wall                 # anülüs iç çapı
    gap = (np.sqrt(d_post_outer ** 2 + 4.0 * a_ann_e / np.pi)
           - d_post_outer) / 2.0
    d_elem_outer = d_post_outer + 2.0 * gap
    if gap * 1e3 < GAS_ANNULUS_GAP_MIN_MM:
        warnings.append(_w(
            'warn.injector.gas_annulus_gap_below_min', 'warning',
            gap_mm=round(float(gap) * 1e3, 2),
            min_mm=float(GAS_ANNULUS_GAP_MIN_MM)))

    # Momentum-akı oranı ve hız oranı (inner=post, outer=anülüs)
    if inner_stream == 'ox':
        rho_in, v_in = st_ox['rho_exit'], st_ox['v_exit_m_s']
        rho_out, v_out = st_fuel['rho_exit'], st_fuel['v_exit_m_s']
    else:
        rho_in, v_in = st_fuel['rho_exit'], st_fuel['v_exit_m_s']
        rho_out, v_out = st_ox['rho_exit'], st_ox['v_exit_m_s']
    j_mom = (rho_out * v_out ** 2) / max(rho_in * v_in ** 2, 1e-12)
    vr = v_out / max(v_in, 1e-9)
    j_ok = GAS_GAS_J_GOOD[0] <= j_mom <= GAS_GAS_J_GOOD[1]
    if not j_ok:
        warnings.append(_w(
            'warn.injector.gas_momentum_flux_out_of_band', 'warning',
            j=round(float(j_mom), 2),
            j_lo=round(float(GAS_GAS_J_GOOD[0]), 0),
            j_hi=round(float(GAS_GAS_J_GOOD[1]), 0)))

    def _circuit(name, mdot, p0_pa_, st, is_inner):
        dp_bar = (p0_pa_ - pc_pa) / PA_PER_BAR
        # --- D15/P1B4-02 — ``orifice_d_mm`` ARTIK BİR ÇAPTIR --------------
        # ESKİ: dış (anülüs) devrede bu alana ANÜLÜS BOŞLUĞU (``gap``)
        # yazılıyordu. ``n_orifices``, ``orifice_d_mm`` ve ``total_area_mm2``
        # üçlüsü ürün yüzünde AYNI TABLO SATIRINDA basılıyor
        # (``hrma/static/js/injector_panel.js``), yani kullanıcı sıvı dalda
        # doğru olan ``n·(π/4)·d² ≡ total_area`` özdeşliğini gaz-gaz dış
        # devrede aritmetik olarak İMKÂNSIZ görüyordu.
        # ÖLÇÜLDÜ (Pc = 300 bar, ṁ_ox = 100 kg/s, ṁ_f = 30 kg/s, iç akım ox):
        #   ox_circuit  (iç post)   63 × 7,9600 mm -> 3135,17 mm²  oran 1,0000
        #   fuel_circuit(anülüs)    63 × 0,6078 mm ->   18,28 mm²
        #                            ama total_area_mm2 = 1222,25  oran 66,8601
        # İç akım 'fuel' seçilince aynı kusur ox devresinde: oran 15,9810.
        # YENİ: anülüs devresinde yayımlanan çap, aynı akış alanını veren
        # ALAN-EŞDEĞER daire çapıdır (d_eq = √(4·A_eleman/π)), dolayısıyla
        # özdeşlik TANIM GEREĞİ sağlanır. Uydurma yoktur: d_eq yayımlanan
        # toplam alan ile eleman sayısından türetilir. Anülüsün GERÇEK
        # boşluğu kaybolmaz — kendi adıyla (``annulus_gap_mm``) aynı sözlükte
        # durur, ayrıca ``gas_gas_geometry`` bloğunda da yayımlanır.
        if is_inner:
            d_char = d_inner
            d_basis = 'post_diameter'
            elem_type = 'inner_post'
            gap_mm = None
        else:
            a_elem = outer_area / n                      # m², eleman başına
            d_char = float(np.sqrt(4.0 * a_elem / np.pi))
            d_basis = 'annulus_area_equivalent_diameter'
            elem_type = 'outer_annulus'
            gap_mm = float(gap * 1e3)
        return {
            'mdot_kg_s': float(mdot),
            'delta_p_bar': float(dp_bar),
            'dp_pc_ratio': float(dp_bar / pc_bar),
            'p0_bar': float(p0_pa_ / PA_PER_BAR),
            'velocity_m_s': float(st['v_exit_m_s']),
            'mach': float(st['mach']),
            'choked': bool(st['choked']),
            'exit_temp_K': float(st['t_exit_k']),
            'exit_pressure_bar': float(st['p_exit_pa'] / PA_PER_BAR),
            'exit_density_kg_m3': float(st['rho_exit']),
            'cd': float(cd),
            'cd_basis': 'gas post discharge coefficient (compressible orifice)',
            'n_orifices': int(n),
            'orifice_d_mm': float(d_char * 1e3),
            # D15/P1B4-02 dürüstlük alanları: çapın NE olduğu ve anülüsün
            # gerçek radyal boşluğu. ``element_type`` panelin doğru etiketi
            # basabilmesi için gereklidir (post ⟷ anülüs aynı şey değildir).
            'orifice_d_basis': d_basis,
            'element_type': elem_type,
            'annulus_gap_mm': gap_mm,
            'total_area_mm2': float((a_ox if name == 'oxidiser'
                                     else a_fuel) * 1e6),
            'flow_model': ('compressible-choked' if st['choked']
                           else 'compressible-unchoked'),
            'critical_pressure_ratio': float(st['pr_crit']),
            'pressure_ratio': float(st['pr']),
            'nhne': None,
            'cavitation_number': None,   # gaz akışında kavitasyon yok
            'hydraulic_flip_risk': False,
        }

    ox_circuit = _circuit('oxidiser', mdot_ox, p0_ox, st_ox,
                          is_inner=(inner_stream == 'ox'))
    fuel_circuit = _circuit('fuel', mdot_fuel, p0_fuel, st_fuel,
                            is_inner=(inner_stream == 'fuel'))

    # Kararlılık: gaz-gaz için ayrı (daha düşük) ΔP/Pc bandı
    dp_pc_ox = ox_circuit['dp_pc_ratio']
    dp_pc_f = fuel_circuit['dp_pc_ratio']
    worst = min(dp_pc_ox, dp_pc_f)
    chug_ok = worst >= GAS_DP_PC_MIN
    if not chug_ok:
        warnings.append(_w(
            'warn.injector.gas_dp_pc_below_min', 'warning',
            dp_pc=round(float(worst), 2), min=float(GAS_DP_PC_MIN)))
    elif worst < GAS_DP_PC_RECOMMENDED:
        warnings.append(_w(
            'warn.injector.gas_dp_pc_below_recommended', 'warning',
            dp_pc=round(float(worst), 2),
            recommended=float(GAS_DP_PC_RECOMMENDED)))
    assumptions.append(_w(
        'warn.injector.gas_dp_pc_band_is_guidance', 'info',
        min=float(GAS_DP_PC_MIN), recommended=float(GAS_DP_PC_RECOMMENDED)))

    stability = {
        'dp_pc_ratio_ox': float(dp_pc_ox),
        'dp_pc_ratio_fuel': float(dp_pc_f),
        'chug_ok': bool(chug_ok),
        'chug_rule': (f'dP/Pc >= {GAS_DP_PC_MIN}-{GAS_DP_PC_RECOMMENDED} '
                      '(gas-gas engineering guidance; SP-8089 is for liquids)'),
        'feed_coupling_note': None,
        'acoustic_note_tr': ('Yüksek frekans (akustik) analiz kapsam dışı; '
                             'gaz-gaz ana odalarda enine modlar birincil risk, '
                             'baffle/kavite literatürüne bakınız.'),
    }

    momentum = {
        'momentum_ratio': float(j_mom),   # J = (ρv²)_dış/(ρv²)_iç
        'velocity_ratio': float(vr),      # VR = v_dış/v_iç
        'rupe_factor': None,
        'tmr': None,
        'target': f"J∈[{GAS_GAS_J_GOOD[0]:.0f},{GAS_GAS_J_GOOD[1]:.0f}] "
                  "(good mixing, guidance)",
        'ok': bool(j_ok),
        'basis': 'momentum flux ratio (shear-coax mixing criterion)',
    }

    gas_gas_geometry = {
        'inner_stream': inner_stream,
        'n_elements': int(n),
        'inner_post_d_mm': float(d_inner * 1e3),
        'post_wall_mm': float(t_wall * 1e3),
        'annulus_gap_mm': float(gap * 1e3),
        'element_outer_d_mm': float(d_elem_outer * 1e3),
        'inner_velocity_m_s': float(v_in),
        'outer_velocity_m_s': float(v_out),
        'inner_density_kg_m3': float(rho_in),
        'outer_density_kg_m3': float(rho_out),
        'momentum_flux_ratio_J': float(j_mom),
        'velocity_ratio_VR': float(vr),
    }

    desc = (f"{n} gas-gas shear-coax elements "
            f"(inner {inner_stream} post d={d_inner*1e3:.2f} mm, annulus gap "
            f"{gap*1e3:.2f} mm, element D={d_elem_outer*1e3:.2f} mm); "
            f"J={j_mom:.2f}, VR={vr:.2f}")

    return {
        'status': 'success',
        'motor_type': spec.get('motor_type'),
        'injector_type': 'gas_gas_coaxial',
        'ox_circuit': ox_circuit,
        'fuel_circuit': fuel_circuit,
        'pattern': {
            # ÖH D30 / OH-D29-11 + P11B5-21 — YALAN '_tr' ALANI SÖKÜLDÜ.
            # T47'de içerik İngilizceye alınmış, ``description_tr`` anahtarı
            # ise "tüketici geçene kadar" bırakılmıştı: alan adı Türkçe
            # içerik VAAT EDİYOR, gövdesi ``description`` ile BİT-AYNI
            # İngilizce metin taşıyordu (ölçüldü, ``once.json`` ->
            # ``OH-D29-11+P11B5-21``: dört enjektör tipinin dördünde de
            # ``tr_ile_en_ayni: true``). Yalan künye yayımlanmaz (Doktrin 1:
            # beyan gerçeği söyler); tüketici (``injector_panel.js``) aynı
            # onarımda ``description``a geçirildi.
            'description': desc,
            'n_elements': int(n),
            'impingement': None,
        },
        'atomization': {
            # Gaz-gaz: damlacık yok → SMD anlamsız (sahte sayı DÖNMEZ)
            'smd_ox_um': None,
            'smd_fuel_um': None,
            'correlation': 'not_modelled',
            'spray_cone_half_angle_deg': None,
            'note_tr': ('Gaz-gaz enjeksiyonda sıvı damlacık yoktur; SMD '
                        'atomizasyon korelasyonları uygulanmaz. Karışım '
                        'türbülanslı shear ile momentum-akı oranından '
                        'değerlendirilir (J, VR).'),
        },
        'momentum': momentum,
        'pintle_geometry': None,
        'swirl_geometry': None,
        'gas_gas_geometry': gas_gas_geometry,
        'stability': stability,
        # v2.6.2 (D-track): dil-nötr {code, params, severity} kayıtları
        'warnings': warnings,
        'assumptions': assumptions,
        'references': REFERENCES + GAS_GAS_REFERENCES,
    }


_VALID_TYPES = ('showerhead', 'impinging_doublet', 'impinging_triplet',
                'like_impinging', 'pintle', 'coax_swirl', 'swirl',
                'gas_gas_coaxial')


def design_injector(spec):
    """Enjektör tasarımı — docs/10_Enjektor_ARGE.md B sözleşmesi.

    Girdi/çıktı şeması için ARGE raporuna bakınız. Doğrulama hatasında
    Türkçe mesajlı ValueError; fiziksel imkânsızlıkta
    {'status':'error','error': ...} döner.
    """
    if not isinstance(spec, dict):
        raise ValueError('spec must be a dictionary')

    motor_type = spec.get('motor_type')
    if motor_type not in ('hybrid', 'liquid'):
        raise ValueError("motor_type must be 'hybrid' or 'liquid'")

    inj_type = spec.get('injector_type') or \
        ('showerhead' if motor_type == 'hybrid' else 'impinging_doublet')
    if inj_type not in _VALID_TYPES:
        raise ValueError(f"Invalid injector_type: '{inj_type}' "
                         f"(valid: {', '.join(_VALID_TYPES)})")

    mdot_ox = spec.get('mdot_ox')
    if not mdot_ox or mdot_ox <= 0:
        raise ValueError('mdot_ox must be positive (kg/s)')
    pc_bar = spec.get('Pc_bar')
    if not pc_bar or pc_bar <= 0:
        raise ValueError('Pc_bar must be positive (bar)')

    # Gaz-gaz shear-coax (FFSC/staged combustion ana odası) — sıvı faz
    # devrelerinden tamamen ayrı sıkıştırılabilir akış dalı.
    if inj_type == 'gas_gas_coaxial':
        if motor_type != 'liquid':
            raise ValueError(
                "gas_gas_coaxial applies only to liquid engines (staged "
                "combustion / FFSC); the main chamber is fed with gas from the "
                "preburners")
        g_warnings, g_assumptions = [], []
        try:
            return _design_gas_gas_coaxial(spec, g_warnings, g_assumptions)
        except ValueError:
            raise
        except Exception as exc:  # sayısal çöküş
            return {'status': 'error',
                    'error': f'The gas-gas injector design could not be solved: {exc}'}

    mdot_fuel = spec.get('mdot_fuel')
    if motor_type == 'liquid':
        if not mdot_fuel or mdot_fuel <= 0:
            raise ValueError(
                'mdot_fuel is required for a liquid engine (kg/s, > 0)')
    else:
        mdot_fuel = None
        # Pintle hibritte MEŞRUDUR: oksitleyici-merkezli tek akışkan düzen
        # (merkez pintle gövdesi + anülüs ox akışı). Yakıt grain'den geldiği
        # için TMR/mdot_fuel gerekmez — BF, anülüs boşluğu ve skip distance
        # yine raporlanır (sayısal kurallar HRMA seçimi — PINTLE_RULE_BASIS).
        if inj_type in ('impinging_doublet', 'impinging_triplet', 'coax_swirl'):
            raise ValueError(
                f"'{inj_type}' is not supported for a hybrid (single liquid "
                "stream): use showerhead, swirl, pintle or like_impinging")

    warnings, assumptions = [], []
    constraints = dict(DEFAULT_CONSTRAINTS)
    constraints.update(spec.get('orifice_constraints') or {})

    # ÖH D27 / OH-D26-07 — ÇAĞRI VARSAYILANI TANIM NOKTASINDAN OKUNUR.
    # ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D27/sivi/a1/once.json``): bu iki
    # satır 0,20'yi SAYI olarak yeniden yazıyordu; aynı sayı bu dosyanın
    # başında zaten ``CHUG_DP_RATIO_RECOMMENDED`` adıyla ithal edilmişti
    # (``CHUG_DP_PC_RECOMMENDED`` takma adı). Spec'te oran verilmediğinde
    # düşülen değer klasik tasarım kuralının tavsiye ettiği orandır —
    # bağımsız bir varsayım değildir. Sayı DEĞİŞMEDİ (0,20); merkez kayarsa
    # bu iki dal artık geride kalmaz.
    dp_ox = spec.get('dp_ratio_ox', CHUG_DP_RATIO_RECOMMENDED)
    dp_f = spec.get('dp_ratio_fuel', CHUG_DP_RATIO_RECOMMENDED)
    # ÖH D16 (kalem B4-04) — HARF DÜZENİ NORMALLEŞTİRİLİYOR.
    # Kardeş satır (aşağıda) yakıt akışkanını `str(...).lower()` ile
    # normalleştiriyordu; oksitleyici akışkanı normalleştirilmiyordu. Uç
    # (/api/injector-design) spec'i kullanıcıdan OLDUĞU GİBİ aldığı için
    # 'N2O' (büyük harf) sessizce jenerik dala düşüyordu. ÖLÇÜLDÜ
    # (1 Eylül 2026, taban 6fde52b; ṁ_ox=2 kg/s, Pc=30 bar, T_ox=293,15 K,
    # rho_ox=784,88, p_feed=50,543 bar — aynı fiziksel nokta):
    #   'n2o' -> NHNE, P_v = 50,543358 bar, K_c = -1,745e-05,
    #            A = 59,677780 mm², 13 delik, hydraulic_flip_risk = True
    #   'N2O' -> SPI,  P_v =  0,050000 bar (1010,9 KAT sapma), K_c = 2,457918,
    #            A = 45,153023 mm² (-%24,3), hydraulic_flip_risk = False
    # Modülün kendi künyesi bu yönü "güvenlik yönünde yanlış taraf" diye
    # tarif ediyor: P_v'yi küçük almak kavitasyon/flip riskini OLDUĞUNDAN
    # DÜŞÜK gösterir. Varsayılan 'generic' KORUNUR — sessiz bir 'n2o'
    # varsayılanı açılmaz; yalnız harf düzeni normalleştirilir.
    fluid_ox = str(spec.get('fluid_ox') or 'generic').lower()
    inlet_ox = spec.get('inlet_ox', DEFAULT_ORIFICE_INLET)
    inlet_f = spec.get('inlet_fuel', DEFAULT_ORIFICE_INLET)
    l_over_d = spec.get('l_over_d', DEFAULT_ORIFICE_L_OVER_D)
    # Orifis uzunluğu = enjektör plakası kalınlığı [m]. Verilirse L/D
    # geometriden çözülür ve 'l_over_d' yalnız yineleme başlangıcı olur
    # (v2.6.26; ayrıntı _solve_circuit içindeki notta).
    orifice_length = spec.get('orifice_length_m') or spec.get('plate_thickness_m')
    # Yakıt devresi akışkan adı YALNIZ buhar basıncı tablosu için kullanılır;
    # 'n2o' burada anlamsızdır (hibritte yakıt katı, sıvıda oksitleyici) ve
    # NHNE dalını T_ox_K olmadan tetiklerdi — bilerek dışarıda bırakılır.
    fluid_f = str(spec.get('fluid_fuel') or 'generic').lower()
    if fluid_f == 'n2o':
        fluid_f = 'generic'

    # Swirl tiplerinde efektif Cd Giffen–Muraszew'den gelir (orifis Cd yerine)
    swirl_geom = None
    cd_override = None
    cd_basis_override = None
    if inj_type in ('swirl', 'coax_swirl'):
        sw_in = spec.get('swirl') or {}
        K = sw_in.get('K')
        theta_t = sw_in.get('theta_target_deg', 45.0)
        if K is None:
            # Çözücü zarfı: swirl_K_from_theta K ∈ [0.02, 20] aralığında arar,
            # bu da θ ∈ [3.7°, 71.2°] demektir. Bu aralıktaki her hedef tam
            # olarak çözülür (varsayılan 45° dahil).
            #
            # v2.6.2 öncesinde burada "θ > 16° çözülemez → K=1.0" yedeği vardı.
            # O sınır fiziksel değildi; _SWIRL_GEOMETRIC_COEF'in tersine
            # çevrilmiş olmasının SEMPTOMUYDU (ters katsayıyla ulaşılabilen en
            # büyük yarı açı 15.9°'ydi). Katsayı düzeltilince yedek hem
            # gereksiz hem zararlı hale geldi: varsayılan 45° hedefinde
            # tetiklenip kullanıcının hedefini sessizce 29.8°'ye eziyordu.
            if not (_SWIRL_THETA_MIN_DEG <= theta_t <= _SWIRL_THETA_MAX_DEG):
                warnings.append(_w(
                    'warn.injector.swirl_theta_target_unreachable', 'warning',
                    theta_target_deg=round(float(theta_t), 1),
                    theta_min_deg=_SWIRL_THETA_MIN_DEG,
                    theta_max_deg=_SWIRL_THETA_MAX_DEG))
                theta_t = float(np.clip(theta_t, _SWIRL_THETA_MIN_DEG,
                                        _SWIRL_THETA_MAX_DEG))
            K = swirl_K_from_theta(theta_t)
        sw = swirl_solve(K)
        cd_override = sw['cd']
        cd_basis_override = (f"Giffen-Muraszew swirl: K={K:.3f} -> X={sw['X']:.3f}"
                             f" -> Cd={sw['cd']:.3f} (being lower than a plain orifice"
                             " is physical)")
        swirl_geom = (K, sw)

    # --- KULLANICININ ÖLÇTÜĞÜ Cd (spec['cd']) ------------------------------
    # v2.6.27 parti 31 (defter: injector_design.discharge_coefficient AD
    # ÇAKIŞMASI). Kullanıcı Cd'si BUGÜNE KADAR yalnız gaz-gaz dalında
    # okunuyordu; sıvı/hibrit orifis devresinde Cd her koşuda giriş
    # geometrisi + L/D tablosundan geliyordu. Sonuç: kullanıcı 0,70 gönderip
    # yanıtta 0,78 görüyordu ve iki sayı AYNI ADI taşıyordu.
    #
    # Cd, devre çözücüsünün KENDİ cebrine girdi olarak verilir (post-hoc
    # ölçekleme DEĞİL): ṁ ∝ Cd hem SPI hem NHNE dalında tam doğrusaldır
    # (nhne_mass_flow: hem ṁ_SPI hem ṁ_HEM Cd ile çarpılır), bu yüzden
    # _size(cd) doğru alanı doğrudan çözer.
    #
    # SWIRL İSTİSNASI: basınç-swirl elemanında efektif Cd akış katsayısı
    # geometriden (Giffen–Muraszew K → X) gelir; düz orifis Cd'si DEĞİLDİR.
    # Orada kullanıcı değeri UYGULANMAZ ve bu sessiz kalmaz: aşağıdaki
    # 'user_cd' beyanı uygulanıp uygulanmadığını ADIYLA taşır.
    user_cd = spec.get('cd')
    user_cd_echo = None
    if user_cd is not None:
        try:
            user_cd = float(user_cd)
        except (TypeError, ValueError):
            raise ValueError(
                f"cd must be numeric (got: {spec.get('cd')!r})")
        lo, hi = USER_CD_RANGE
        if not (lo <= user_cd <= hi):
            raise ValueError(
                f'cd must lie in the {lo}-{hi} band (got: {user_cd:g}); the '
                'discharge coefficient is dimensionless and cannot exceed 1')
        if cd_override is None:
            cd_override = user_cd
            cd_basis_override = USER_CD_BASIS
            user_cd_echo = {'value': user_cd, 'applied': True,
                            'basis': USER_CD_BASIS}
        else:
            user_cd_echo = {
                'value': user_cd, 'applied': False,
                'basis': ('not applied: the effective discharge coefficient '
                          'of a pressure-swirl element is set by its own '
                          'geometry (Giffen-Muraszew K -> X), not by a '
                          'straight-orifice Cd; the entered value is '
                          'reported for comparison only')}

    try:
        ox = _solve_circuit(
            'ox', mdot_ox, spec.get('rho_ox'), pc_bar, dp_ox,
            spec.get('p_feed_bar'), fluid_ox, spec.get('T_ox_K'),
            inlet_ox, l_over_d, constraints, warnings, assumptions,
            cd_override=cd_override, cd_basis_override=cd_basis_override,
            cd_override_from_user=bool(user_cd_echo
                                       and user_cd_echo['applied']),
            n_fixed=spec.get('n_orifices_ox'),
            orifice_length_m=orifice_length,
            l_over_d_supplied=('l_over_d' in spec))
        fuel = None
        if mdot_fuel:
            fuel = _solve_circuit(
                'fuel', mdot_fuel, spec.get('rho_fuel'), pc_bar, dp_f,
                spec.get('p_feed_bar_fuel'), fluid_f, None,
                inlet_f, l_over_d, constraints, warnings, assumptions,
                # Kullanıcı Cd'si TEK enjektörün katsayısıdır: yakıt devresi
                # de aynı sayıyı alır. Yarısı kullanıcıdan yarısı tablodan
                # bir enjektör, kullanıcının ölçtüğü şey DEĞİLDİR.
                # (Swirl dalında cd_override zaten geometriden gelir ve
                # user_cd uygulanmaz — o yolda bu bayrak False'tur.)
                cd_override=(cd_override if (user_cd_echo
                                             and user_cd_echo['applied'])
                             else None),
                cd_basis_override=(cd_basis_override
                                   if (user_cd_echo
                                       and user_cd_echo['applied']) else None),
                cd_override_from_user=bool(user_cd_echo
                                           and user_cd_echo['applied']),
                n_fixed=spec.get('n_orifices_fuel'),
                orifice_length_m=orifice_length,
            l_over_d_supplied=('l_over_d' in spec))
    except ValueError:
        raise
    except Exception as exc:  # fiziksel imkânsızlık / sayısal çöküş
        return {'status': 'error', 'error': f'The injector design could not be solved: {exc}'}

    # ------------------------------------------------------------------
    # Ortam gazı yoğunluğu (atomizasyon)
    # ------------------------------------------------------------------
    T_c = spec.get('T_c_K')
    mw = spec.get('mw_gas')
    if T_c and mw:
        rho_gas = pc_bar * PA_PER_BAR / ((R_UNIVERSAL / mw) * T_c)
    else:
        rho_gas = RHO_GAS_DEFAULT
        assumptions.append(_w(
            'warn.injector.chamber_gas_density_assumed', 'info',
            rho_gas=float(RHO_GAS_DEFAULT)))

    # Sıvı özellikleri (σ, μ) — kullanıcı vermezse AKIŞKANA GÖRE tablodan
    # (v2.6.2 F012/F040). Eski davranış her akışkan için σ=0.02, μ=2e-4
    # kullanıyordu; N₂O'da bu σ'yı 11 kat, μ'yü 3.2 kat şişiriyor ve Elkotb
    # SMD'sini ~9 kat aşırı tahmin ettiriyordu.
    sigma_ox = spec.get('sigma_ox')
    if sigma_ox is None:
        sigma_ox, sig_basis = liquid_surface_tension(fluid_ox, spec.get('T_ox_K'))
        assumptions.append(_w(
            'warn.injector.liquid_props_assumed_ox', 'info',
            fluid=str(fluid_ox), sigma_n_m=float(round(sigma_ox, 6)),
            sigma_basis=sig_basis))
    sigma_f = spec.get('sigma_fuel')
    if sigma_f is None:
        sigma_f = SIGMA_GENERIC
    mu_ox = spec.get('mu_ox')
    if mu_ox is None:
        mu_ox, mu_t_ref, mu_basis = liquid_viscosity(fluid_ox)
        assumptions.append(_w(
            'warn.injector.liquid_viscosity_assumed_ox', 'info',
            fluid=str(fluid_ox), mu_pa_s=float(mu_ox),
            T_ref_K=(float(mu_t_ref) if mu_t_ref is not None else None),
            basis=mu_basis))
    mu_f = spec.get('mu_fuel')
    if mu_f is None:
        mu_f = MU_GENERIC
    if fuel is not None and (spec.get('sigma_fuel') is None
                             or spec.get('mu_fuel') is None):
        # Yakıt akışkanı spec'te tanımlı değil (fluid_fuel alanı yok) → jenerik
        # hidrokarbon değerleri kullanılır ve AÇIKÇA varsayım olarak bildirilir.
        assumptions.append(_w(
            'warn.injector.liquid_props_assumed_fuel', 'info',
            sigma_n_m=float(sigma_f), mu_pa_s=float(mu_f)))

    # ------------------------------------------------------------------
    # Tip özel geometri + momentum + atomizasyon
    # ------------------------------------------------------------------
    momentum = None
    pintle_geometry = None
    swirl_geometry = None
    impingement = None
    spray_half = None
    smd_fuel_um = None
    n_elements = ox['n_orifices']

    d_ox_m = ox['orifice_d_mm'] * 1e-3
    v_ox = ox['velocity_m_s']
    rho_ox_l = ox['_rho']

    if inj_type == 'showerhead':
        nu_ox = mu_ox / rho_ox_l
        smd_ox = smd_elkotb(nu_ox, sigma_ox, rho_ox_l, rho_gas,
                            ox['delta_p_bar'] * PA_PER_BAR)
        correlation = 'Elkotb-1982'
        if fuel is not None:
            nu_f = mu_f / fuel['_rho']
            smd_fuel_um = smd_elkotb(nu_f, sigma_f, fuel['_rho'], rho_gas,
                                     fuel['delta_p_bar'] * PA_PER_BAR) * 1e6
        desc = (f"{ox['n_orifices']}-orifice showerhead "
                f"(d={ox['orifice_d_mm']:.2f} mm, axial parallel jets)")

    elif inj_type in ('impinging_doublet', 'impinging_triplet', 'like_impinging'):
        smd_ox = smd_impinging(d_ox_m, v_ox, rho_ox_l, sigma_ox)
        correlation = 'impinging-We13'
        # V301/E2: açı istekten gelebilir (``spec['impingement']``); verilmezse
        # varsayılan ve künye metni eskisiyle bit-aynı (modül sonu).
        half, half_basis = _impingement_half_angle(spec)
        impingement = {
            'half_angle_deg': half,
            # v2.6.26 beyan: açı bir TASARIM SEÇİMİdir, akıştan çözülmez.
            'half_angle_deg_basis': half_basis,
            'free_jet_length_mm': float(FREE_JET_LD * d_ox_m * 1e3),
            'element_spacing_mm': float(ELEMENT_SPACING_D
                                        * max(d_ox_m, 1e-9) * 1e3),
        }
        if inj_type == 'impinging_doublet' and fuel is not None:
            d_f_m = fuel['orifice_d_mm'] * 1e-3
            v_f = fuel['velocity_m_s']
            rho_f_l = fuel['_rho']
            smd_fuel_um = smd_impinging(d_f_m, v_f, rho_f_l, sigma_f) * 1e6
            mr = (mdot_fuel * v_f) / (mdot_ox * v_ox)
            # Rupe kriteri (JPL Progress Report 20-195, 1953): ρv²d oranı.
            # UYGULAMA ZARFI UYARISI (v2.6.2 F041): her iki devre de
            # v = Cd·√(2ΔP/ρ) ile çözüldüğünden ρv² = 2·ΔP·Cd² olur; iki devre
            # AYNI ΔP ve AYNI Cd kullanıyorsa yoğunluk ve hız tamamen
            # sadeleşir ve kriter Rupe ≡ d_f/d_ox'a çöker — yani bağımsız bir
            # şey ölçmez. Formül doğrudur, ama kullanıcı "Rupe tamam" ibaresini
            # gerçek bir karışım teyidi sanmamalıdır. Devrelerin ΔP'si
            # (dp_ratio_ox / dp_ratio_fuel veya p_feed_bar_fuel) ayrı
            # seçildiğinde kriter bağımsızlaşır.
            rho_v2_ox = rho_ox_l * v_ox ** 2
            rho_v2_f = rho_f_l * v_f ** 2
            rupe = (rho_v2_f * d_f_m) / (rho_v2_ox * d_ox_m)
            if abs(rho_v2_f / max(rho_v2_ox, 1e-12) - 1.0) < 0.02:
                assumptions.append(_w(
                    'warn.injector.rupe_criterion_degenerate', 'info',
                    rupe=round(float(rupe), 3),
                    d_ratio=round(float(d_f_m / max(d_ox_m, 1e-12)), 3)))
            target = spec.get('target_velocity_ratio', 1.0)
            ok = MR_BAND[0] <= mr <= MR_BAND[1]
            momentum = {'momentum_ratio': float(mr), 'rupe_factor': float(rupe),
                        'tmr': None, 'target': float(target), 'ok': bool(ok),
                        # v2.6.26 beyan: hedef bir TASARIM SEÇİMİdir; ölçülen
                        # değer 'momentum_ratio' alanında ayrıca yayımlanır.
                        'target_basis': (
                            'balanced-doublet design target (momentum ratio '
                            '= 1) unless the caller supplies '
                            'target_velocity_ratio; the achieved value is '
                            'reported separately as momentum_ratio, and the '
                            f'acceptance band is {MR_BAND[0]:g}-{MR_BAND[1]:g}'
                            ' (Rupe, JPL PR 20-195)')}
            if not ok:
                warnings.append(_w(
                    'warn.injector.doublet_momentum_out_of_band', 'warning',
                    mr=round(float(mr), 2), band_lo=float(MR_BAND[0]),
                    band_hi=float(MR_BAND[1])))
            if not (MR_BAND[0] <= rupe <= MR_BAND[1]):
                warnings.append(_w(
                    'warn.injector.rupe_factor_off_optimum', 'warning',
                    rupe=round(float(rupe), 2), band_lo=float(MR_BAND[0]),
                    band_hi=float(MR_BAND[1])))
            n_elements = min(ox['n_orifices'], fuel['n_orifices'])
            desc = (f"{n_elements} unlike doublet pairs, 2θ={2*half:.0f}°, "
                    f"free jet {FREE_JET_LD:.0f}·d_j")
            # ÖH KU H-8: hipergolik unlike elemanda blowapart bilgi alanı.
            impingement['reactive_stream_separation'] = (
                reactive_stream_separation_check(
                    fluid_ox, fluid_f, ox['orifice_d_mm'],
                    fuel['orifice_d_mm']))
        elif inj_type == 'impinging_triplet' and fuel is not None:
            d_f_m = fuel['orifice_d_mm'] * 1e-3
            v_f = fuel['velocity_m_s']
            rho_f_l = fuel['_rho']
            smd_fuel_um = smd_impinging(d_f_m, v_f, rho_f_l, sigma_f) * 1e6
            # O-F-O: dış = oksitleyici (2 jet), orta = yakıt
            tmr = (2.0 * mdot_ox * v_ox * np.sin(np.radians(half))) \
                / max(mdot_fuel * v_f, 1e-12)
            ok = MR_BAND[0] <= tmr <= 2.0  # triplet doğal olarak O/F ile büyür
            momentum = {'momentum_ratio': None, 'rupe_factor': None,
                        'tmr': float(tmr), 'target': 1.0, 'ok': bool(ok),
                        'target_basis': (
                            'balanced O-F-O triplet design target (total '
                            'momentum ratio = 1); the achieved value is '
                            'reported separately as tmr')}
            n_elements = max(1, min(ox['n_orifices'] // 2, fuel['n_orifices']))
            desc = (f"{n_elements} O-F-O triplets (outer 2×ox., centre fuel), "
                    f"2θ={2*half:.0f}°")
            # ÖH KU H-8: triplet de unlike elemandır (SP-8089 s. 13).
            impingement['reactive_stream_separation'] = (
                reactive_stream_separation_check(
                    fluid_ox, fluid_f, ox['orifice_d_mm'],
                    fuel['orifice_d_mm']))
            if not ok:
                warnings.append(_w(
                    'warn.injector.triplet_tmr_out_of_band', 'warning',
                    tmr=float(tmr)))
        else:  # like_impinging (kendi içinde çarpışan çiftler)
            n_elements = max(1, ox['n_orifices'] // 2)
            desc = (f"{n_elements} like-doublets (same-fluid pairs), "
                    f"2θ={2*half:.0f}° — no blowapart risk")
            assumptions.append(_w(
                'warn.injector.like_impinging_no_mr', 'info'))

    elif inj_type == 'pintle' and fuel is None:
        # Hibrit (tek akışkan) pintle: yakıt grain'den geldiği için pintle
        # YALNIZ oksitleyiciyi taşır. Oksitleyici alanı ikiye bölünür:
        #   - radyal (ya da teğet) delikler — pintle ucunda tek çevresel sıra
        #   - anülüs (pintle mili çevresinde eksenel tabaka)
        # V301/E1: geometri TEK çözücüden gelir (``resolve_pintle_geometry``,
        # modül sonu). Kullanıcının sabitlediği ölçüler (``spec['pintle']``:
        # D_p, t, n, d, L_s, gövde dış çapı, ikincil delik kipi, teğet açı)
        # BURADA tutarlılık çözücüsünden geçer; ekran bloğu, tablo, 2B kesit
        # ve motor özeti bu sözlüğü TÜKETİR. Ölçü verilmeyen varsayılan yol
        # eski ``pintle_tip_geometry`` çağrısıyla BİT-AYNI sayı verir.
        pin = spec.get('pintle') or {}
        a_total = ox['total_area_mm2'] * 1e-6
        pintle_geometry = resolve_pintle_geometry(a_total, pin,
                                                  mdot_target_kg_s=mdot_ox)
        secim = pintle_geometry['secondary_holes']
        f_rad = pintle_geometry['radial_flow_fraction']
        d_p_m = pintle_geometry['d_pintle_mm'] * 1e-3
        d_hole = pintle_geometry['radial_hole_d_mm'] * 1e-3
        n_holes = pintle_geometry['n_radial_holes']
        bf = pintle_geometry['bf']
        t_ann = pintle_geometry['annulus_gap_mm'] * 1e-3
        if t_ann * 1e3 < ANNULUS_GAP_MIN_MM:
            warnings.append(_w(
                'warn.injector.pintle_annulus_below_min', 'warning',
                gap_mm=float(t_ann * 1e3), min_mm=ANNULUS_GAP_MIN_MM))
        if secim == 'none':
            # Uçta delik yok: eleman düz bir anüler enjektördür. TMR, sprey
            # konisi bağıntısı ve jet SMD korelasyonu UYGULANMAZ — sayı
            # uydurulmaz (beyan ``pintle_geometry.tmr_basis``te).
            momentum = None
            spray_half = None
            smd_ox = None
            correlation = 'not_modelled'
        else:
            tmr = pintle_geometry['tmr']
            theta = pintle_geometry['spray_half_angle_deg']
            momentum = {'momentum_ratio': None, 'rupe_factor': None,
                        'tmr': float(tmr), 'target': pin.get('tmr_target', 1.0),
                        'ok': bool(0.5 <= tmr <= 2.0),
                        'target_basis': (
                            'pintle total-momentum-ratio design target (TMR = 1 '
                            'unless the caller supplies tmr_target); the achieved '
                            'value is reported separately as tmr and it sets the '
                            'spray cone angle')}
            if not (PINTLE_BF_BAND[0] <= bf <= PINTLE_BF_BAND[1]):
                warnings.append(_w(
                    'warn.injector.pintle_bf_out_of_band', 'warning',
                    bf=float(bf), lo=PINTLE_BF_BAND[0], hi=PINTLE_BF_BAND[1]))
            smd_ox = smd_impinging(d_hole, v_ox, rho_ox_l, sigma_ox)
            correlation = 'impinging-We13'
            spray_half = theta
        assumptions.append(_w(
            'warn.injector.hybrid_pintle_single_fluid', 'info',
            radial_pct=float(f_rad * 100.0)))
        n_elements = 1
        if secim == 'none':
            desc = (f"Oxidizer-centred hybrid pintle without tip holes "
                    f"(annular element): D_p={d_p_m*1e3:.1f} mm, annulus "
                    f"{t_ann*1e3:.2f} mm")
        else:
            desc = (f"Oxidizer-centred hybrid pintle: D_p={d_p_m*1e3:.1f} mm, "
                    f"{n_holes}×{d_hole*1e3:.2f} mm "
                    f"{'tangential' if secim == 'tangential' else 'radial'} "
                    f"holes, annulus {t_ann*1e3:.2f} mm, TMR={tmr:.2f} → "
                    f"θ={theta:.0f}°")
    elif inj_type == 'pintle':
        # Yakıt merkezli TRW/Merlin düzeni: radyal iç jetler = yakıt,
        # anülüs dış akış = oksitleyici
        pin = spec.get('pintle') or {}
        bf_target = pin.get('bf_target', PINTLE_BF_TARGET_DEFAULT)
        d_f_m = fuel['orifice_d_mm'] * 1e-3
        v_f = fuel['velocity_m_s']
        rho_f_l = fuel['_rho']
        a_ann = ox['total_area_mm2'] * 1e-6      # anülüs = oks. toplam alanı
        a_rad = fuel['total_area_mm2'] * 1e-6    # radyal delikler = yakıt

        # Uç geometrisi TEK kaynaktan (hibrit dalıyla aynı fonksiyon).
        tip = pintle_tip_geometry(a_rad, a_ann,
                                  d_pintle_m=(pin['d_pintle_mm'] * 1e-3
                                              if pin.get('d_pintle_mm')
                                              is not None else None),
                                  bf_target=bf_target)
        d_p_m = tip['d_pintle_mm'] * 1e-3
        d_hole = tip['radial_hole_d_mm'] * 1e-3
        n_holes = tip['n_radial_holes']
        bf = tip['bf']
        t_ann = tip['annulus_gap_mm'] * 1e-3
        if t_ann * 1e3 < ANNULUS_GAP_MIN_MM:
            warnings.append(_w(
                'warn.injector.pintle_annulus_below_min', 'warning',
                gap_mm=float(t_ann * 1e3), min_mm=ANNULUS_GAP_MIN_MM))
        tmr = (mdot_fuel * v_f) / max(mdot_ox * v_ox, 1e-12)
        theta = pintle_spray_angle(tmr)
        momentum = {'momentum_ratio': None, 'rupe_factor': None,
                    'tmr': float(tmr), 'target': pin.get('tmr_target', 1.0),
                    'ok': bool(0.5 <= tmr <= 2.0),
                    'target_basis': (
                        'pintle total-momentum-ratio design target (TMR = 1 '
                        'unless the caller supplies tmr_target); the achieved '
                        'value is reported separately as tmr and it sets the '
                        'spray cone angle')}
        pintle_geometry = dict(tip)
        if not (PINTLE_BF_BAND[0] <= bf <= PINTLE_BF_BAND[1]):
            warnings.append(_w(
                'warn.injector.pintle_bf_out_of_band', 'warning',
                bf=float(bf), lo=PINTLE_BF_BAND[0], hi=PINTLE_BF_BAND[1]))
        smd_ox = smd_impinging(d_hole, np.hypot(v_ox, v_f), rho_f_l, sigma_f)
        smd_fuel_um = smd_ox * 1e6  # çarpışan tabaka ortak kırılımı
        correlation = 'impinging-We13'
        spray_half = theta
        n_elements = 1
        desc = (f"Fuel-centred pintle: D_p={d_p_m*1e3:.1f} mm, "
                f"{n_holes}×{d_hole*1e3:.2f} mm radial holes, TMR={tmr:.2f} "
                f"→ θ={theta:.0f}°")

    else:  # swirl / coax_swirl
        K, sw = swirl_geom
        r_o = d_ox_m / 2.0
        # V301/E2: girdap odası çapı ve teğet giriş sayısı istekten gelebilir
        # (``spec['swirl']``); verilmezse 2,5·r_o ve 3 (eski sayılar, modül
        # sonundaki ``SWIRL_CHAMBER_D_OVER_DO`` / ``..._INLETS_DEFAULT``).
        r_s, n_inlets, d_s_kaynak = _swirl_element_overrides(spec, r_o)
        # Teğet giriş toplam alanı (ELEMAN BAŞINA): atomizör sabitinin
        # tanımından K = A_p/(D_s·d_o) = A_p/(4·r_s·r_o) → A_p = 4·K·r_s·r_o.
        #
        # v2.6.2 DÜZELTMESİ (F014): burada 4 yerine π yazılıydı (a_p = K·π·r_s·r_o),
        # yani teğet port alanı π/4 = 0.785 kat, giriş çapı 0.886 kat kayıyordu.
        # Kaynak: Lefebvre & McDonell, Atomization and Sprays 2. baskı Böl. 6
        # (simplex atomizör sabiti tanımı).
        a_p = 4.0 * K * r_s * r_o
        d_inlet = np.sqrt(4.0 * a_p / (np.pi * n_inlets))
        swirl_geometry = {
            'K': float(K), 'X_air_core': sw['X'], 'cd_swirl': sw['cd'],
            # 'swirl_number' KALDIRILDI (F014): dönen büyüklük π·r_o·r_s/A_p =
            # 1/K idi; bu, standart girdap sayısı S (eksenel açısal momentum
            # akısı / (R × eksenel momentum akısı), Gupta-Lilley-Syred, Swirl
            # Flows 1984) DEĞİLDİR ve zaten K ile birebir aynı bilgiyi taşıyor.
            # Yerine gerçek geometrik büyüklük raporlanır.
            'tangential_inlet_area_mm2': float(a_p * 1e6),
            'film_thickness_mm': float(sw['film_t_ratio'] * r_o * 1e3),
            'tangential_inlets': n_inlets,
            'inlet_d_mm': float(d_inlet * 1e3),
            'exit_orifice_d_mm': float(d_ox_m * 1e3),
            'swirl_chamber_d_mm': float(2.0 * r_s * 1e3),
            # ÖH KU (KC-11 / RUS R2): ideal teori beyanı (yeni alan).
            'model_basis': SWIRL_IDEAL_THEORY_BASIS,
        }
        # V301/E2: istek girdap odası çapını verdiyse kaynağı adıyla durur
        # (verilmediyse anahtar konmaz: varsayılan yol bit-aynı).
        if d_s_kaynak is not None:
            swirl_geometry['swirl_chamber_d_source'] = d_s_kaynak
        spray_half = sw['theta_deg']
        # Lefebvre basınç-swirl korelasyonu TEK atomizöre kalibre edilmiştir:
        # ṁ_L = eleman başına sıvı debisi (v2.6.2 F013 düzeltmesi — eskiden
        # TOPLAM ox debisi geçiliyordu; SMD ∝ ṁ^0.25 olduğu için n=38 elemanlı
        # tipik tasarımda 38^0.25 = 2.48 KAT aşırı tahmin).
        # Kaynak: Lefebvre & McDonell, Atomization and Sprays 2. baskı Böl. 6.
        mdot_ox_per_element = mdot_ox / max(ox['n_orifices'], 1)
        smd_ox = smd_lefebvre_swirl(sigma_ox, mu_ox, mdot_ox_per_element,
                                    ox['delta_p_bar'] * PA_PER_BAR, rho_gas)
        correlation = 'Lefebvre-swirl'
        if d_s_kaynak is None:
            # Oda çapı istekten gelmediyse 2,5·r_o bir VARSAYIMDIR.
            assumptions.append(_w(
                'warn.injector.swirl_chamber_radius_assumed', 'info'))
        desc = (f"{'Coaxial ' if inj_type == 'coax_swirl' else ''}pressure-swirl: "
                f"K={K:.3f}, 2θ={2*sw['theta_deg']:.0f}°, "
                f"film {sw['film_t_ratio']*r_o*1e3:.2f} mm")
        if fuel is not None:
            nu_f = mu_f / fuel['_rho']
            smd_fuel_um = smd_elkotb(nu_f, sigma_f, fuel['_rho'], rho_gas,
                                     fuel['delta_p_bar'] * PA_PER_BAR) * 1e6
            assumptions.append(_w(
                'warn.injector.swirl_liquid_circuit', 'info'))

    # ------------------------------------------------------------------
    # Kararlılık
    # ------------------------------------------------------------------
    dp_pc_ox = ox['dp_pc_ratio']
    dp_pc_f = fuel['dp_pc_ratio'] if fuel else None
    chug_ok = dp_pc_ox >= CHUG_DP_PC_MIN and \
        (dp_pc_f is None or dp_pc_f >= CHUG_DP_PC_MIN)
    if not chug_ok:
        worst = min([r for r in (dp_pc_ox, dp_pc_f) if r is not None])
        warnings.append(_w('warn.injector.chug_risk', 'warning',
                           ratio=float(worst), min_ratio=CHUG_DP_PC_MIN))

    feed_note = None
    if fluid_ox == 'n2o':
        if dp_pc_ox < CHUG_DP_PC_RECOMMENDED:
            feed_note = _w('warn.injector.n2o_feed_coupling_risk', 'warning',
                           recommended=CHUG_DP_PC_RECOMMENDED,
                           ratio=float(dp_pc_ox))
            warnings.append(feed_note)
        else:
            feed_note = _w('warn.injector.n2o_choked_isolation', 'info')

    stability = {
        'dp_pc_ratio_ox': float(dp_pc_ox),
        'dp_pc_ratio_fuel': (float(dp_pc_f) if dp_pc_f is not None else None),
        'chug_ok': bool(chug_ok),
        # Metin SABİTLERDEN türetilir (gaz-gaz dalındaki ikizinin deseni):
        # eşik değişirse kullanıcıya gösterilen kural kendiliğinden değişir.
        # Biçim korunur (%.2f) — yayımlanmış dize bit-aynı kalır.
        'chug_rule': (f'dP/Pc >= {CHUG_DP_PC_MIN:.2f}-'
                      f'{CHUG_DP_PC_RECOMMENDED:.2f} (NASA SP-8089)'),
        # ÖH KU (KU-K5): yukarıdaki dizedeki "(NASA SP-8089)" atfı EKSİK —
        # SP-8089 evrensel bir 0,15-0,20 eşiği VERMEZ (s. 35: gereken
        # ΔP_inj/P_c eleman türüne bağlı). Dize bir sözleşme testinde bit
        # bit kilitli (tests/test_enjektor_sozlesme_borclari.py:424) ve bu
        # kulvar mevcut test beklentisini değiştiremez; doğru künye bu yeni
        # alanda yayımlanır, dizenin kendisi devir listesindedir.
        'chug_rule_basis': CHUG_RULE_CITATION,
        'feed_coupling_note': feed_note,
        'acoustic_note': _w('warn.injector.acoustic_out_of_scope', 'info'),
    }

    # İç kullanım alanını sözleşme dışı tutmak için temizle
    ox.pop('_rho', None)
    if fuel is not None:
        fuel.pop('_rho', None)

    return {
        'status': 'success',
        'motor_type': motor_type,
        'injector_type': inj_type,
        'ox_circuit': ox,
        'fuel_circuit': fuel,
        'pattern': {
            # ÖH D30 / OH-D29-11 + P11B5-21: bkz. gaz-gaz dalındaki aynı not
            # — yalan '_tr' alanı burada da söküldü.
            'description': desc,
            'n_elements': int(n_elements),
            'impingement': impingement,
        },
        'atomization': {
            # V301/E1: deliksiz (anüler) pintle'da jet SMD korelasyonu
            # uygulanmaz → None (diğer tiplerde smd_ox her zaman sayıdır).
            'smd_ox_um': (float(smd_ox * 1e6) if smd_ox is not None
                          else None),
            'smd_fuel_um': (float(smd_fuel_um) if smd_fuel_um is not None
                            else None),
            'correlation': correlation,
            'spray_cone_half_angle_deg': (float(spray_half)
                                          if spray_half is not None else None),
        },
        'momentum': momentum,
        'pintle_geometry': pintle_geometry,
        'swirl_geometry': swirl_geometry,
        # Kullanıcı Cd'si verilmediyse alan None'dur (uydurma beyan yok);
        # verildiyse UYGULANDI/UYGULANMADI bilgisini adıyla taşır.
        'user_cd': user_cd_echo,
        'stability': stability,
        'warnings': warnings,
        'assumptions': assumptions,
        'references': REFERENCES,
        # ÖH D37 A2 hibrit · F-10: planın çözüldüğü bant ve KAYNAĞI yanıtta
        # adıyla — tüketici (CAD/STEP künyesi, panel) bandı buradan okur,
        # ikinci kez yazmaz. Çağıran kendi kısıtını verdiyse kaynak odur.
        'orifice_band': {
            'd_min_mm': float(constraints['d_min_mm']),
            'd_max_mm': float(constraints['d_max_mm']),
            'source': (
                ORIFICE_D_BAND_SOURCE
                if (constraints['d_min_mm'], constraints['d_max_mm'])
                == ORIFICE_D_BAND_MM
                else 'caller-supplied orifice_constraints (request field)'),
            # 7. tur (karar §28-25, Astra şartı): "alt kenara yakın" uyarı
            # penceresi bantla birlikte YANITTA beyan edilir — HRMA sezgisel
            # uyarı eşiği; imalat standardı ya da güvenlik sınırı değil.
            'near_lower_edge_fraction': ORIFICE_D_NEAR_LOWER_EDGE_FRAC,
            'near_lower_edge_basis': ORIFICE_D_NEAR_LOWER_EDGE_BASIS,
        },
    }


# ---------------------------------------------------------------------------
# ÖH D37 A2 hibrit · 10. tur (HB9 devir 46) — çağıranın çap bandı SON KAPISI.
# Bu blok BİLEREK modül sonundadır: yukarıdaki satır numaraları
# ``formal/registry.json`` Lean çapalarıdır (orificeCount, satır 1399).
# ---------------------------------------------------------------------------
#: Çağıranın bandı dışındaki plan için ``_plan_orifices`` arama yolunun
#: ZATEN adıyla bildirdiği kodlar (bunlar varsa son kapı ikinci satır basmaz).
CALLER_BAND_WARNING_CODES = (
    'warn.injector.orifice_plan_infeasible',
    'warn.injector.orifice_d_below_manufacturing_band',
)


def _caller_band_gate(n, d, d_min, d_max, n_max, warnings, start):
    """Arama yolunun planı çağıranın ``[d_min, d_max]`` bandının dışındaysa
    ve bu çağrıda (``warnings[start:]``) o hâl henüz adıyla söylenmediyse
    ADLI uyarı ekler. Hüküm ``classify_orifice_d``den (tek kaynak).

    ÖLÇÜLDÜ (9. tur ``sart9/olc9_*.json`` ``bant035_d1.8003``, HB9 devir
    46): ``{'d_min_mm': 0.35, 'd_max_mm': 1.8, 'n_max': 1}`` ve tek delikte
    d = 1,8003 mm için arama yolu tercih bandını (0,5-2,5 mm) sınıyor,
    çağıranın d_max'ını YOK SAYIYORDU — uyarı listesi boştu (fail-open).
    Arama artık iki bandın kesişimini sınar; kesişimde çözüm yoksa geri
    dönüş dallarının bıraktığı çap burada çağıranın bandına karşı sınanır.
    Varsayılan kısıtla (d_min ≡ d_lo, d_max ≡ d_hi) kesişim tercih bandının
    kendisidir: ürün yolu bit-aynı.
    """
    sinif = classify_orifice_d(d, d_min, d_max)
    if sinif not in (ORIFICE_D_CLASS_BELOW, ORIFICE_D_CLASS_ABOVE):
        return
    if any(isinstance(w, dict) and w.get('code') in CALLER_BAND_WARNING_CODES
           for w in warnings[start:]):
        return
    d_g, lo_g, hi_g = _band_warning_mm(d, d_min, d_max)
    # Kod: hiçbir tam sayı delik adedi çapı çağıranın bandına oturtamadı.
    warnings.append(_w('warn.injector.orifice_d_outside_caller_band',
                       'warning', n=int(n), n_max=int(n_max), d_mm=d_g,
                       d_min_mm=lo_g, d_max_mm=hi_g))


# ---------------------------------------------------------------------------
# V301 / E1 (Ayberk tur 1) — PINTLE GEOMETRİSİNİN TEK ÇÖZÜCÜSÜ.
# Bu blok BİLEREK modül sonundadır: satır 1399 ``formal/registry.json`` Lean
# çapasıdır, yukarıdaki satır sayısı bu kulvarda DEĞİŞMEDİ.
#
# Ayberk: "pintle için outer diameter istiyor ama nerenin outer diameteri
# yazmıyor", "secondary holes girsek dahi ek input istemiyor", "Enjektör
# kısmı full hatalı". ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/ayberk1/
# enjektor-pintle/once.json``, 1 kN / Pc 20 bar / N2O-HTPB): aynı /calculate
# yanıtında İKİ pintle vardı — ekran bloğu sunucunun motordan bağımsız
# 25 mm yedeğiyle 437 × Ø0,104 mm delik ve 0,047 mm anülüs çiziyor, devre
# çözücüsü D_p 5,639 mm ile 16 × Ø0,646 mm ve 0,282 mm yayımlıyordu.
#
# Karar (ana model, Astra danışmalı): devre çözücüsünün geometrisi KANONDUR.
# Kullanıcının sabitlediği ölçüler BURAYA girer; ekran bloğu, tablo, 2B
# kesit ve motor özeti bu sözlüğü TÜKETİR, yeniden türetmez.
# ---------------------------------------------------------------------------
#: İkincil (uç) delik kipleri — arayüz seçimiyle aynı sözcükler.
PINTLE_SECONDARY_HOLE_MODES = ('none', 'radial', 'tangential')
PINTLE_SECONDARY_HOLES_DEFAULT = 'radial'
#: Teğet delik açısı = delik ekseni ile yerel yarıçap arasındaki açı. 0° saf
#: radyal, 90° saf teğettir; ikisi de "teğetsel delik" değildir → AÇIK
#: aralık (geometrik tanım; sayı seçimi değil).
PINTLE_TANGENTIAL_ANGLE_OPEN_RANGE_DEG = (0.0, 90.0)
#: Aşırı belirlenmiş geometrinin debi uyuşmazlığı toleransı. TEK KAYNAK:
#: kırpılmış plan toleransının KENDİSİ (kimlik takma adı, sayı kopyalanmaz).
PINTLE_FLOW_MATCH_REL_TOL = CLAMPED_PLAN_TARGET_FLOW_REL_TOL
PINTLE_FLOW_MATCH_TOL_BASIS = (
    f'HRMA choice (no literature value): a pintle geometry fixed by the '
    f'request is accepted only if its total flow area delivers the oxidizer '
    f'flow within {PINTLE_FLOW_MATCH_REL_TOL:.0%} at the design pressure '
    f'drop (same constant as the clamped-plan target-flow check). The design '
    f'pressure drop is NOT re-solved for the fixed geometry.')

#: İstek alanı adları (``/calculate``) ⟷ ``spec['pintle']`` anahtarları.
#: Uç bu tabloyla çevirir; ad ikinci kez yazılmaz.
PINTLE_REQUEST_FIELDS = {
    'secondary_holes': 'secondary_holes',
    'd_pintle_mm': 'pintle_diameter',
    'annulus_gap_mm': 'annular_gap',
    'n_radial_holes': 'pintle_radial_hole_count',
    'radial_hole_d_mm': 'pintle_radial_hole_diameter',
    'skip_distance_mm': 'skip_distance',
    'housing_outer_diameter_mm': 'outer_diameter',
    'tangential_angle_deg': 'pintle_tangential_angle',
}
#: Uzunluk girdileri (mm) — hepsi sonlu ve pozitif olmak zorunda.
_PINTLE_MM_KEYS = ('d_pintle_mm', 'annulus_gap_mm', 'radial_hole_d_mm',
                   'skip_distance_mm', 'housing_outer_diameter_mm')

#: Sayısal tasarım kurallarının künyesi (V301/E1 künye düzeltmesi). Dressler
#: & Bauer, "TRW Pintle Engine Heritage and Performance Characteristics",
#: AIAA 2000-3871 tam metni tarandı (s. 2-4 "Pintle Injector Design
#: Concept"): skip distance'ı TANIMLAR, pintle çapı / akım kalınlıkları /
#: hızlar / momentum oranlarını tasarım değişkeni olarak SAYAR, ama ne
#: t/D_p, ne BF, ne L_s/D_p, ne de radyal pay için sayı verir; "blockage"
#: sözcüğü metinde hiç geçmez. Sayılar DEĞİŞMEDİ, yalnız atıf düzeltildi.
PINTLE_RULE_BASIS = {
    'annulus_t_over_dp': (
        f'HRMA choice (no literature value): when neither the pintle '
        f'diameter nor the annular gap is given, D_p is sized from the '
        f'annulus flow area with t = {PINTLE_ANNULUS_T_OVER_DP:g}*D_p. '
        f'Dressler & Bauer (AIAA 2000-3871, pp. 2-4) list stream thickness '
        f'and pintle diameter as design variables but give no numerical '
        f'rule.'),
    'blockage_factor_target': (
        f'HRMA choice (no literature value): BF = n*d/(pi*D_p) = '
        f'{PINTLE_BF_TARGET_DEFAULT:g} sets the hole count when neither the '
        f'hole count nor the hole diameter is given.'),
    'blockage_factor_band': (
        f'BF band {PINTLE_BF_BAND[0]:g}-{PINTLE_BF_BAND[1]:g}: source NOT '
        f'verified. Its former attribution to Dressler & Bauer (AIAA '
        f'2000-3871) is withdrawn - that paper defines no blockage factor '
        f'and gives no band.'),
    'radial_flow_fraction': (
        f'HRMA choice (no literature value): {PINTLE_HYBRID_RADIAL_FRACTION:g}'
        f' of the oxidizer flow area goes to the tip holes unless the '
        f'request fixes the hole or annulus geometry.'),
    'skip_distance': (
        f'Definition: Dressler & Bauer (AIAA 2000-3871, p. 4) - distance '
        f'from the outer propellant\'s annular entrance into the chamber to '
        f'the point of contact with the central stream; here the axial '
        f'distance from the annulus exit (body face) to the axis of the '
        f'tip-hole row. Default L_s = {PINTLE_SKIP_LS_DP:g}*D_p is an HRMA '
        f'choice (no literature value). L_s enters no model: geometry and '
        f'drawing only.'),
    'annulus_gap_min': (
        f'HRMA manufacturing floor {ANNULUS_GAP_MIN_MM:g} mm for the annulus '
        f'gap (no literature value); a gap below it is reported, not '
        f'resized.'),
}

PINTLE_FLOW_SPLIT_BASIS = (
    'The tip holes and the annulus are fed from the same manifold state at '
    'the same design pressure drop and use the circuit\'s single discharge '
    'coefficient and its own mass-flux model (SPI, or Dyer NHNE for '
    'self-pressurised N2O): mdot_branch = Cd*A_branch*G, so the radial flow '
    'fraction is f_r = A_r/(A_r + A_a) and A_r + A_a must equal the circuit '
    'area that delivers the oxidizer flow. Separate branch discharge '
    'coefficients and internal branch losses are NOT modelled.')
PINTLE_SPRAY_ANGLE_BASIS = (
    'Cheng et al., "On the prediction of spray angle of liquid-liquid '
    'pintle injectors", Acta Astronautica 2017 (doi:10.1016/'
    'j.actaastro.2017.05.037), Eq. 16: cos(theta) = 1/(1+TMR), TMR = radial/'
    'axial momentum (incompressible, inviscid). Both streams of this '
    'single-fluid hybrid pintle share one velocity, so TMR = f_r/(1-f_r). '
    'Applying it to an oxidizer-only element and to flashing N2O is an '
    'inference, NOT a validated hybrid result.')
PINTLE_NONE_TMR_BASIS = (
    'NOT_APPLICABLE: no secondary holes, so there is no radial jet and the '
    'radial-to-annular momentum ratio is undefined. The injector '
    'degenerates to a plain annular element; the spray cone is set by the '
    'annular sheet, not by a pintle jet.')
PINTLE_TANGENTIAL_BASIS = (
    'NOT_MODELLED: the holes are drilled at an angle to the radius, so part '
    'of the jet momentum goes into swirl. Hole count, hole diameter and '
    'total area are solved as in the radial case (same area, same pressure '
    'drop), but the swirl component and the wider spray cone it produces '
    'are NOT modelled. The reported spray half-angle is the RADIAL-injection '
    'value and is therefore a lower bound. The tangential angle is a '
    'geometry/CAD input only.')
PINTLE_HOUSING_NOT_SIZED_BASIS = (
    'not sized: the injector body (housing) outer diameter needs structural '
    'and packaging inputs - housing material and allowable stress, the '
    'pressure across the housing wall (not the injector pressure drop) and '
    'the attachment details. For a thin wall t ~ dp*D_i/(2*sigma_allow); '
    'thick sections need thick-cylinder analysis (Philpot & Thomas, '
    'Mechanics of Materials 5th ed., Secs. 14.3, 14.5). There is no '
    'universal minimum pintle wall, so none is invented: only the annulus '
    'bore D_p + 2t is published and drawn.')
PINTLE_HOUSING_GIVEN_BASIS = (
    'request value. The housing wall is the geometric (OD - bore)/2 and is '
    'checked to be positive; a structural check of the housing is NOT '
    'performed (it needs housing material, allowable stress and the '
    'pressure across the wall).')
#: Motor özet bloğundaki (``injector_design``) delik sayısı/çapının pintle'da
#: ne olduğu — ÖLÇÜLDÜ (once.json): 1 kN varsayılanında ``number_of_orifices``
#: 3 yazıyor, pintle'ın kendisi 16 delik + anülüs; kullanıcı üç sayı görüyordu.
PINTLE_EQUIVALENT_ORIFICE_PLAN_BASIS = (
    'pintle: number_of_orifices / orifice_diameter_mm are the injector '
    'circuit\'s EQUIVALENT straight-orifice plan - it fixes the discharge '
    'coefficient (inlet + L/D table) and the total flow area that delivers '
    'the oxidizer flow. The pintle is NOT drilled this way: its tip holes, '
    'annulus, bore and skip distance are in pintle_geometry (the single '
    'canonical pintle geometry of this answer).')
PINTLE_NO_SKIP_BASIS = (
    'NOT_APPLICABLE: with no tip holes there is no central stream to meet, '
    'so the skip distance is undefined.')


class PintleGeometryInputError(ValueError):
    """Pintle girdisi geçersiz ya da sabitlenen geometri akışla tutarsız.

    ``invalid_fields`` uç sözleşmesinin (HTTP 422) alan listesidir; her
    kayıt ``field`` (istek alanı adı), ``spec_key``, ``reason`` ve
    ``message`` taşır.
    """

    def __init__(self, message, invalid_fields):
        super().__init__(message)
        self.invalid_fields = list(invalid_fields)


def _pintle_kaydi(anahtar, reason, message, **ek):
    kayit = {'field': PINTLE_REQUEST_FIELDS.get(anahtar, anahtar),
             'spec_key': f'pintle.{anahtar}', 'reason': reason,
             'message': message}
    kayit.update(ek)
    return kayit


def _pintle_sayi(value):
    """(sayı, None) ya da (None, neden). bool ve dize sayı DEĞİLDİR."""
    from hrma.utils.input_guard import is_bool
    if is_bool(value) or isinstance(value, str) or not isinstance(
            value, (int, float, np.integer, np.floating)):
        return None, 'not_a_number'
    v = float(value)
    if not np.isfinite(v):
        return None, 'not_finite'
    return v, None


def pintle_clean_inputs(pin):
    """``spec['pintle']`` kullanıcı ölçülerinin tel/aralık/çelişki kapısı.

    Döner: ``(temiz, hatalar)``. ``temiz`` yalnız VERİLEN alanları (mm,
    adet, derece) ve ``secondary_holes`` kipini taşır; ``hatalar`` 422
    kayıtlarıdır. Uç (``/calculate``) bu işlevi motoru çalıştırmadan ÖNCE
    çağırır; çözücü de doğrudan çağıranlar için aynı kapıdan geçer.
    """
    temiz, hatalar = {}, []
    if pin is None:
        pin = {}
    if not isinstance(pin, dict):
        return temiz, [_pintle_kaydi(
            'pintle', 'not_an_object',
            "the pintle specification must be an object of named fields")]
    ham = pin.get('secondary_holes')
    if ham is None or ham == '':
        secim = PINTLE_SECONDARY_HOLES_DEFAULT
        temiz['secondary_holes_supplied'] = False
    elif isinstance(ham, str) and ham.strip().lower() in \
            PINTLE_SECONDARY_HOLE_MODES:
        secim = ham.strip().lower()
        temiz['secondary_holes_supplied'] = True
    else:
        secim = None
        hatalar.append(_pintle_kaydi(
            'secondary_holes', 'invalid_choice',
            "'secondary_holes' must be one of: "
            + ', '.join(PINTLE_SECONDARY_HOLE_MODES)
            + '. The value was NOT mapped to a default.',
            submitted=str(ham)[:40],
            accepted=list(PINTLE_SECONDARY_HOLE_MODES)))
    temiz['secondary_holes'] = secim

    for anahtar in _PINTLE_MM_KEYS:
        v = pin.get(anahtar)
        if v is None or v == '':
            continue
        sayi, neden = _pintle_sayi(v)
        if sayi is not None and not sayi > 0.0:
            neden = 'not_positive'
        if neden:
            hatalar.append(_pintle_kaydi(
                anahtar, neden,
                f"'{PINTLE_REQUEST_FIELDS[anahtar]}' is a length in mm and "
                f'must be a finite positive JSON number.',
                submitted=str(v)[:40], unit='mm'))
            continue
        temiz[anahtar] = sayi

    v = pin.get('n_radial_holes')
    if v is not None and v != '':
        sayi, neden = _pintle_sayi(v)
        if sayi is not None and (sayi != int(sayi) or sayi < 1):
            neden = 'not_a_positive_whole_number'
        if neden:
            hatalar.append(_pintle_kaydi(
                'n_radial_holes', neden,
                "'pintle_radial_hole_count' is a count of holes and must be "
                'a whole number >= 1.', submitted=str(v)[:40],
                unit='count'))
        else:
            temiz['n_radial_holes'] = int(sayi)

    v = pin.get('tangential_angle_deg')
    if v is not None and v != '':
        lo, hi = PINTLE_TANGENTIAL_ANGLE_OPEN_RANGE_DEG
        sayi, neden = _pintle_sayi(v)
        if sayi is not None and not (lo < sayi < hi):
            neden = 'out_of_range'
        if neden:
            hatalar.append(_pintle_kaydi(
                'tangential_angle_deg', neden,
                "'pintle_tangential_angle' is the angle between each hole "
                'axis and the local radius; it must lie strictly between '
                f'{lo:g} deg (radial) and {hi:g} deg (tangent).',
                submitted=str(v)[:40], accepted_range=[lo, hi],
                unit='deg'))
        else:
            temiz['tangential_angle_deg'] = sayi

    if secim == 'none':
        for anahtar in ('n_radial_holes', 'radial_hole_d_mm',
                        'skip_distance_mm'):
            if anahtar in temiz:
                hatalar.append(_pintle_kaydi(
                    anahtar, 'conflicts_with_secondary_holes_none',
                    f"'{PINTLE_REQUEST_FIELDS[anahtar]}' describes the tip "
                    "holes, but 'secondary_holes' is 'none' (no tip holes). "
                    'Choose radial/tangential holes or drop the field.',
                    submitted=temiz[anahtar]))
    if 'tangential_angle_deg' in temiz and secim != 'tangential':
        hatalar.append(_pintle_kaydi(
            'tangential_angle_deg', 'applies_only_to_tangential_holes',
            "'pintle_tangential_angle' applies only when 'secondary_holes' "
            "is 'tangential'.", submitted=temiz['tangential_angle_deg']))
    return temiz, hatalar


def _pintle_hata(hatalar):
    return PintleGeometryInputError(
        'Pintle geometry rejected: ' + '; '.join(
            f"{h['field']} ({h['reason']})" for h in hatalar), hatalar)


def resolve_pintle_geometry(a_total_m2, pin=None, mdot_target_kg_s=None):
    """Hibrit (tek akışkan) pintle geometrisinin TEK çözücüsü (V301/E1).

    Sayısal taşma koruması (güvenlik + kararlılık ilkesi): kullanıcı ölçüsü
    float aralığını zorlarsa (ör. D_p = 1e300 mm) hesap ham OverflowError ile
    çökmez; sabitlenen alanlar ``not_computable`` nedeniyle 422 olur. Sonuçta
    sonlu olmayan bir sayı yayımlanmaz. Ayrıntılı kurallar:
    ``_resolve_pintle_geometry_core``.
    """
    pin = pin if isinstance(pin, dict) else {}
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            geo = _resolve_pintle_geometry_core(a_total_m2, pin,
                                                mdot_target_kg_s)
    except (OverflowError, FloatingPointError, ZeroDivisionError) as exc:
        temiz, _ = pintle_clean_inputs(pin)
        sabit = [a for a in PINTLE_REQUEST_FIELDS
                 if a in temiz and a != 'secondary_holes']
        if not sabit:
            raise ValueError(f'pintle geometry not computable: {exc}')
        raise _pintle_hata([_pintle_kaydi(
            a, 'not_computable',
            'The fixed pintle dimensions push the geometry outside the '
            'floating-point range; no geometry is published.',
            submitted=temiz[a]) for a in sabit])
    sayilar = [v for v in geo.values()
               if isinstance(v, float) and not isinstance(v, bool)]
    pozitif = [geo['d_pintle_mm'], geo['annulus_gap_mm']] + (
        [geo['radial_hole_d_mm']] if geo['n_radial_holes'] else [])
    if not (all(np.isfinite(v) for v in sayilar)
            and all(v > 0.0 for v in pozitif)):
        temiz, _ = pintle_clean_inputs(pin)
        sabit = [a for a in PINTLE_REQUEST_FIELDS
                 if a in temiz and a != 'secondary_holes']
        if not sabit:
            raise ValueError('pintle geometry produced a non-finite or '
                             'non-positive dimension')
        raise _pintle_hata([_pintle_kaydi(
            a, 'not_computable',
            'The fixed pintle dimensions leave a zero or non-finite pintle '
            'diameter, annular gap or hole diameter (floating-point range '
            'exhausted); no geometry is published.',
            submitted=temiz[a]) for a in sabit])
    return geo


def _resolve_pintle_geometry_core(a_total_m2, pin, mdot_target_kg_s):
    """``resolve_pintle_geometry``nin hesap gövdesi.

    Girdi:
        a_total_m2       : devrenin oksitleyici debisini tasarım ΔP'sinde
                           teslim eden TOPLAM akış alanı [m²] (Cd ve akış
                           modeli — SPI ya da NHNE — devreninkidir)
        pin              : ``spec['pintle']`` — isteğe bağlı kullanıcı
                           ölçüleri (``PINTLE_REQUEST_FIELDS`` anahtarları)
                           + ``bf_target`` / ``radial_fraction``
        mdot_target_kg_s : hedef oksitleyici debisi (uyuşmazlık kaydı için)

    Kurallar (boş alan = çözücü boyutlandırır, beyanlı):
      * Akış payı: f_r = A_r/(A_r + A_a) ve A_r + A_a = A_toplam
        (``PINTLE_FLOW_SPLIT_BASIS``). Delik geometrisi verilmezse
        A_r = f·A_toplam (f HRMA seçimi).
      * n ve d birlikte → A_r sabit; yalnız d → n = round(A_r/a_delik) ve A_r
        yeniden çözülür; yalnız n → d = √(4A_r/(πn)); ikisi de yoksa BF hedefi
        (``pintle_tip_geometry``).
      * D_p ve t birlikte → A_a sabit; yalnız D_p → t TAM ifadeden; yalnız t →
        D_p = A_a/(πt) − t; ikisi de yoksa t = k·D_p kuralı (HRMA seçimi).
      * Aşırı belirlenmiş geometri toplam alanı tutmuyorsa (tolerans
        ``PINTLE_FLOW_MATCH_REL_TOL``) ya da delik/anülüs alanı tek başına
        toplamı aşıyorsa, delikler çevreye sığmıyorsa (BF ≥ 1) ya da gövde
        kılıf deliğini sarmıyorsa ``PintleGeometryInputError`` (422).
      * Gövde dış çapı verilmezse BOYUTLANDIRILMAZ (``housing_sized`` False).

    Varsayılan yol (hiç ölçü verilmemiş) ``pintle_tip_geometry``nin eski
    çağrısıyla BİT-AYNI sayıları verir.
    """
    pin = pin if isinstance(pin, dict) else {}
    temiz, hatalar = pintle_clean_inputs(pin)
    if hatalar:
        raise _pintle_hata(hatalar)
    a_total = float(a_total_m2)
    if not (np.isfinite(a_total) and a_total > 0.0):
        raise ValueError('pintle total flow area must be finite and positive')
    secim = temiz['secondary_holes']
    bf_target = pin.get('bf_target', PINTLE_BF_TARGET_DEFAULT)
    f_def = float(np.clip(float(pin.get('radial_fraction',
                                        PINTLE_HYBRID_RADIAL_FRACTION)),
                          0.1, 0.9))
    k = PINTLE_ANNULUS_T_OVER_DP
    mm = 1e-3
    dp_u = temiz.get('d_pintle_mm')
    t_u = temiz.get('annulus_gap_mm')
    n_u = temiz.get('n_radial_holes')
    d_u = temiz.get('radial_hole_d_mm')
    ls_u = temiz.get('skip_distance_mm')
    od_u = temiz.get('housing_outer_diameter_mm')
    ang_u = temiz.get('tangential_angle_deg')
    kaynak = {}
    hatalar = []

    a_ann_sabit = None
    if dp_u is not None and t_u is not None:
        a_ann_sabit = float(np.pi * (dp_u * mm + t_u * mm) * (t_u * mm))

    # --- 1) Akış alanı paylaşımı ---------------------------------------
    n = 0
    d = 0.0
    if secim == 'none':
        a_rad = 0.0
        a_ann = a_ann_sabit if a_ann_sabit is not None else a_total
        kaynak['n_radial_holes'] = 'not_applicable_no_tip_holes'
        kaynak['radial_hole_d_mm'] = 'not_applicable_no_tip_holes'
    else:
        if n_u is not None and d_u is not None:
            a_rad = float(n_u * np.pi / 4.0 * (d_u * mm) ** 2)
        elif a_ann_sabit is not None:
            a_rad = a_total - a_ann_sabit
        else:
            a_rad = f_def * a_total
        if a_rad <= 0.0:
            hatalar.extend(_pintle_kaydi(
                a, 'annulus_alone_exceeds_flow_area',
                'The fixed pintle diameter and annular gap give an annulus '
                f'area of {a_ann_sabit * 1e6:.4g} mm2, at least the whole '
                f'{a_total * 1e6:.4g} mm2 that delivers the oxidizer flow at '
                'the design pressure drop, so no area is left for the tip '
                'holes.', annulus_area_mm2=a_ann_sabit * 1e6,
                flow_area_mm2=a_total * 1e6)
                for a in ('d_pintle_mm', 'annulus_gap_mm'))
            raise _pintle_hata(hatalar)
        if d_u is not None and n_u is None:
            a_delik = float(np.pi / 4.0 * (d_u * mm) ** 2)
            n = max(1, int(round(a_rad / a_delik)))
            a_rad = float(n * a_delik)
            kaynak['n_radial_holes'] = 'radial_area_and_hole_diameter'
            kaynak['radial_hole_d_mm'] = 'request'
        elif n_u is not None and d_u is None:
            n = int(n_u)
            d = float(np.sqrt(4.0 * a_rad / (np.pi * n)))
            kaynak['n_radial_holes'] = 'request'
            kaynak['radial_hole_d_mm'] = 'radial_area_and_hole_count'
        elif n_u is not None:
            n = int(n_u)
            kaynak['n_radial_holes'] = 'request'
            kaynak['radial_hole_d_mm'] = 'request'
        else:
            kaynak['n_radial_holes'] = 'blockage_factor_target'
            kaynak['radial_hole_d_mm'] = 'blockage_factor_target'
        if d_u is not None:
            d = float(d_u * mm)
        if a_ann_sabit is not None:
            a_ann = a_ann_sabit
        else:
            a_ann = a_total - a_rad
            if a_ann <= 0.0:
                sabit = [a for a in ('n_radial_holes', 'radial_hole_d_mm')
                         if a in temiz]
                hatalar.extend(_pintle_kaydi(
                    a, 'tip_holes_exceed_flow_area',
                    f'The fixed tip holes have {a_rad * 1e6:.4g} mm2 of flow '
                    f'area, at least the whole {a_total * 1e6:.4g} mm2 that '
                    'delivers the oxidizer flow at the design pressure '
                    'drop, so no area is left for the annulus.',
                    hole_area_mm2=a_rad * 1e6, flow_area_mm2=a_total * 1e6)
                    for a in sabit)
                raise _pintle_hata(hatalar)

    # --- 2) Anülüs: D_p ve t -------------------------------------------
    d_p = None
    t = None
    if a_ann_sabit is not None:
        d_p, t = dp_u * mm, t_u * mm
        kaynak['d_pintle_mm'] = kaynak['annulus_gap_mm'] = 'request'
    elif dp_u is not None:
        d_p = dp_u * mm
        kaynak['d_pintle_mm'] = 'request'
        kaynak['annulus_gap_mm'] = 'annulus_area_and_pintle_diameter'
    elif t_u is not None:
        t = t_u * mm
        d_p = a_ann / (np.pi * t) - t
        if not d_p > 0.0:
            raise _pintle_hata([_pintle_kaydi(
                'annulus_gap_mm', 'gap_too_large_for_annulus_area',
                f'An annulus of gap {t_u:g} mm needs at least '
                f'{np.pi * t * t * 1e6:.4g} mm2 even around a zero-diameter '
                f'post, but only {a_ann * 1e6:.4g} mm2 of flow area is left '
                'for the annulus at the design pressure drop.',
                submitted=t_u, unit='mm')])
        d_p = float(d_p)
        kaynak['annulus_gap_mm'] = 'request'
        kaynak['d_pintle_mm'] = 'annulus_area_and_gap'
    else:
        kaynak['d_pintle_mm'] = 'flow_sized_annulus_rule'
        kaynak['annulus_gap_mm'] = 'flow_sized_annulus_rule'

    if secim != 'none' and n_u is None and d_u is None:
        # Eski çağrının AYNISI (varsayılan yolda bit-aynı sayılar).
        tip = pintle_tip_geometry(a_rad, a_ann, d_pintle_m=d_p,
                                  bf_target=bf_target)
        d_p_tip = tip['d_pintle_mm'] * 1e-3
        n = tip['n_radial_holes']
        d = tip['radial_hole_d_mm'] * 1e-3
        bf = tip['bf']
        d_pintle_mm = tip['d_pintle_mm']
        gap_mm = (t_u if t_u is not None else tip['annulus_gap_mm'])
        if d_p is None:
            d_p = d_p_tip
    else:
        if d_p is None:
            d_p = float(np.sqrt(a_ann / (np.pi * k * (1.0 + k))))
        if t is None:
            t = float((np.sqrt(d_p ** 2 + 4.0 * a_ann / np.pi) - d_p) / 2.0)
        bf = float(n * d / (np.pi * d_p)) if secim != 'none' else 0.0
        d_pintle_mm = float(d_p * 1e3)
        gap_mm = float(t_u if t_u is not None else t * 1e3)
    if dp_u is not None:
        d_pintle_mm = float(dp_u)
    t_mm = float(gap_mm)

    if secim != 'none' and not bf < 1.0:
        sabit = [a for a in ('n_radial_holes', 'radial_hole_d_mm',
                             'd_pintle_mm') if a in temiz] or ['d_pintle_mm']
        raise _pintle_hata([_pintle_kaydi(
            a, 'tip_holes_do_not_fit_circumference',
            f'{n} holes of {d * 1e3:.4g} mm need {n * d * 1e3:.4g} mm of '
            f'circumference, but the pintle tip (D_p {d_p * 1e3:.4g} mm) has '
            f'only {np.pi * d_p * 1e3:.4g} mm (blockage factor '
            f'{bf:.3f} >= 1). Use fewer/smaller holes or a larger pintle '
            'diameter.', blockage_factor=bf) for a in sabit])

    # --- 3) Debi tutarlılığı (aşırı belirlenmiş geometri) ---------------
    a_toplam_geo = a_rad + a_ann
    oran = a_toplam_geo / a_total
    uyusmazlik = oran - 1.0
    asiri = (a_ann_sabit is not None and (
        secim == 'none' or d_u is not None)) or False
    debi = (float(mdot_target_kg_s) if mdot_target_kg_s is not None
            else None)
    if abs(uyusmazlik) > PINTLE_FLOW_MATCH_REL_TOL:
        sabit = [a for a in ('d_pintle_mm', 'annulus_gap_mm',
                             'n_radial_holes', 'radial_hole_d_mm')
                 if a in temiz]
        raise _pintle_hata([_pintle_kaydi(
            a, 'geometry_does_not_deliver_target_flow',
            'The fixed pintle dimensions are over-determined and their total '
            f'flow area ({a_toplam_geo * 1e6:.4g} mm2) differs by '
            f'{uyusmazlik:+.1%} from the {a_total * 1e6:.4g} mm2 that '
            'delivers the oxidizer flow at the design pressure drop. Leave '
            'one of them empty so the solver can close the flow balance.',
            requested_mdot_kg_s=debi,
            predicted_mdot_kg_s=(debi * oran if debi is not None else None),
            mismatch_rel=uyusmazlik,
            tolerance_rel=PINTLE_FLOW_MATCH_REL_TOL,
            tolerance_basis=PINTLE_FLOW_MATCH_TOL_BASIS) for a in sabit])

    # --- 4) L_s, kılıf deliği, gövde ------------------------------------
    d_p_m = d_pintle_mm * 1e-3
    if secim == 'none':
        ls_mm = None
        ls_dp = None
        kaynak['skip_distance_mm'] = 'not_applicable_no_tip_holes'
    elif ls_u is not None:
        ls_mm = float(ls_u)
        ls_dp = float(ls_u / d_pintle_mm)
        kaynak['skip_distance_mm'] = 'request'
    else:
        ls_mm = float(PINTLE_SKIP_LS_DP * d_p_m * 1e3)
        ls_dp = float(PINTLE_SKIP_LS_DP)
        kaynak['skip_distance_mm'] = 'ls_over_dp_default'
    bore_mm = float(d_pintle_mm + 2.0 * t_mm)
    if od_u is not None:
        if not od_u > bore_mm:
            raise _pintle_hata([_pintle_kaydi(
                'housing_outer_diameter_mm', 'housing_does_not_enclose_bore',
                f'The injector body outer diameter ({od_u:g} mm) does not '
                f'enclose the annulus bore D_p + 2t = {bore_mm:.4g} mm; the '
                'body wall would be zero or negative.',
                submitted=od_u, bore_diameter_mm=bore_mm, unit='mm')])
        govde_cidar = float((od_u - bore_mm) / 2.0)
        kaynak['housing_outer_diameter_mm'] = 'request'
    else:
        govde_cidar = None
        kaynak['housing_outer_diameter_mm'] = 'not_sized'

    # --- 5) Momentum ve sprey -------------------------------------------
    if secim == 'none':
        f_rad = 0.0
        tmr = None
        theta = None
    else:
        pay_geometriden = d_u is not None or a_ann_sabit is not None
        f_rad = (float(a_rad / a_toplam_geo) if pay_geometriden else f_def)
        tmr = f_rad / max(1.0 - f_rad, 1e-9)
        theta = pintle_spray_angle(tmr)
    kaynak['radial_flow_fraction'] = (
        'not_applicable_no_tip_holes' if secim == 'none' else
        ('geometry' if (d_u is not None or a_ann_sabit is not None)
         else 'design_default'))

    # Akıştan boyutlandırılmış karşılaştırma (hiç ölçü verilmeseydi).
    if secim == 'none':
        fs_dp = float(np.sqrt(a_total / (np.pi * k * (1.0 + k))) * 1e3)
        fs_n, fs_d = 0, 0.0
    else:
        fs = pintle_tip_geometry(f_def * a_total, a_total - f_def * a_total,
                                 d_pintle_m=None, bf_target=bf_target)
        fs_dp, fs_n, fs_d = (fs['d_pintle_mm'], fs['n_radial_holes'],
                             fs['radial_hole_d_mm'])

    kaynak_metni = {
        'request': 'user input (pintle_diameter)',
        'annulus_area_and_gap': ('solved from the annulus flow area and the '
                                 'requested annular gap'),
        'flow_sized_annulus_rule': (
            'flow-sized by the injector circuit (annulus rule t = '
            f'{k:g}*D_p, HRMA choice)'),
    }[kaynak['d_pintle_mm']]

    geo = {
        'd_pintle_mm': float(d_pintle_mm),
        'skip_distance_mm': ls_mm,
        'ls_over_dp': ls_dp,
        'bf': float(bf),
        'annulus_gap_mm': t_mm,
        'n_radial_holes': int(n),
        'radial_hole_d_mm': float(d * 1e3),
        'radial_flow_fraction': float(f_rad),
        'single_fluid': True,
        'secondary_holes': secim,
        'radial_hole_area_mm2': float(a_rad * 1e6),
        'annulus_area_mm2': float(a_ann * 1e6),
        'total_flow_area_mm2': float(a_toplam_geo * 1e6),
        'annulus_bore_diameter_mm': bore_mm,
        'housing_outer_diameter_mm': (float(od_u) if od_u is not None
                                      else None),
        'housing_wall_mm': govde_cidar,
        'housing_sized': od_u is not None,
        'housing_basis': (PINTLE_HOUSING_GIVEN_BASIS if od_u is not None
                          else PINTLE_HOUSING_NOT_SIZED_BASIS),
        'tmr': (float(tmr) if tmr is not None else None),
        'spray_half_angle_deg': (float(theta) if theta is not None
                                 else None),
        'spray_angle_basis': (PINTLE_SPRAY_ANGLE_BASIS if theta is not None
                              else PINTLE_NONE_TMR_BASIS),
        'flow_split_basis': PINTLE_FLOW_SPLIT_BASIS,
        'flow_match': {
            'over_determined': bool(asiri),
            'area_ratio': float(oran),
            'mismatch_rel': float(uyusmazlik),
            'requested_mdot_kg_s': debi,
            'predicted_mdot_kg_s': (debi * oran if debi is not None
                                    else None),
            'tolerance_rel': PINTLE_FLOW_MATCH_REL_TOL,
            'tolerance_basis': PINTLE_FLOW_MATCH_TOL_BASIS,
        },
        'sizing_sources': kaynak,
        'user_inputs': {PINTLE_REQUEST_FIELDS[a]: temiz[a]
                        for a in PINTLE_REQUEST_FIELDS
                        if a in temiz and a != 'secondary_holes'},
        'd_pintle_source': kaynak_metni,
        'flow_sized_d_pintle_mm': float(fs_dp),
        'flow_sized_n_radial_holes': int(fs_n),
        'flow_sized_radial_hole_d_mm': float(fs_d),
        'flow_sizing_basis': (
            'what the injector circuit sizes when no pintle dimension is '
            'given: ' + PINTLE_RULE_BASIS['annulus_t_over_dp'] + ' '
            + PINTLE_RULE_BASIS['blockage_factor_target']),
        'design_rule_basis': dict(PINTLE_RULE_BASIS),
    }
    if secim == 'none':
        geo['tmr_basis'] = PINTLE_NONE_TMR_BASIS
        geo['skip_distance_basis'] = PINTLE_NO_SKIP_BASIS
        geo['radial_hole_d_band_class'] = None
    else:
        geo['skip_distance_basis'] = PINTLE_RULE_BASIS['skip_distance']
        geo['radial_hole_d_band_class'] = classify_orifice_d(
            d * 1e3, ORIFICE_D_BAND_MM[0], ORIFICE_D_BAND_MM[1])
        geo['radial_hole_d_band_mm'] = list(ORIFICE_D_BAND_MM)
        geo['radial_hole_d_band_source'] = ORIFICE_D_BAND_SOURCE
    if secim == 'tangential':
        geo['tangential_angle_deg'] = ang_u
        geo['tangential_momentum_modelled'] = False
        geo['tangential_basis'] = PINTLE_TANGENTIAL_BASIS
    return geo


# ---------------------------------------------------------------------------
# V301/E2 (Ayberk tur 1) — PİNTLE DIŞI ELEMAN GİRDİLERİ KANON DEVREYE GİRER.
# Bu blok BİLEREK modül sonundadır: yukarıdaki satır numaraları
# ``formal/registry.json`` Lean çapalarıdır (orificeCount, satır 1399).
#
# ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ayberk1/enjektor-genel/once.json, 1 kN,
# Pc 20 bar, N₂O/HTPB): aynı /calculate yanıtında iki enjektör vardı.
#   * çarpışmalı: ekran bloğu 2 çift × Ø1,541 mm (A 7,456 mm², tek fazlı SPI),
#     devre 3 delik × Ø2,111 mm (A 10,495 mm², Dyer NHNE) — tek sayıda delik
#     benzer-akışkan çifti OLAMAZ ve ekranın alanı devrenin iki-fazlı kütle
#     akısında hedef debinin ~%71'ini teslim eder;
#   * swirl: ekran tek eleman d_o 5,40 mm, devre 7 eleman × d_o 2,42 mm;
#     form varsayılanında ekran K 0,052 / θ 64,4°, devre K 0,326 / θ 45°.
# Kullanıcının eleman girdileri (çift sayısı, delik çapı, çarpışma açısı,
# hedef sprey yarı açısı, girdap odası çapı, teğet giriş sayısı) yalnız ekran
# bloğuna gidiyordu; devre çözücüsü onları hiç görmüyordu. Artık TEK çözücü
# devredir (E1 pintle deseni): girdiler ``spec['impingement']`` /
# ``spec['swirl']`` ile devreye girer, ekran bloğu devrenin geometrisini
# TÜKETİR.
# ---------------------------------------------------------------------------

#: Çarpışma TAM açısı 2θ için geometrik açık aralık [derece]: 0° paralel
#: jetler (çarpışma yok), 180° karşı karşıya jetler. Sınırlar tanım
#: gereğidir; tasarım bandı DEĞİLDİR (bant uyarısı ekran bloğundadır).
IMPINGEMENT_FULL_ANGLE_OPEN_RANGE_DEG = (0.0, 180.0)
#: Benzer-akışkan çift planının hedef debi toleransı — kardeş kapıların
#: (kırpılmış plan, pintle aşırı belirlenmiş geometri) KİMLİK takma adı;
#: HRMA seçimi, literatür değeri yok (künye ``CLAMPED_PLAN_TARGET_FLOW_
#: TOL_BASIS``).
LIKE_DOUBLET_PLAN_REL_TOL = CLAMPED_PLAN_TARGET_FLOW_REL_TOL
#: Girdap odası çapı / çıkış orifis çapı varsayılan oranı (D_s = 2,5·d_o).
#: Kaynak: Lefebvre & McDonell, Atomization and Sprays 2. bs. Böl. 6 (tipik
#: simplex oranı). Swirl dalındaki ``r_s = 2.5 * r_o`` ile AYNI sayı; utils
#: ekran bloğu (``SWIRL_CHAMBER_D_RATIO``) buradan okur.
SWIRL_CHAMBER_D_OVER_DO = 2.5
#: Swirl dalının teğet giriş sayısı varsayılanı (eleman başına). Swirl
#: dalındaki ``n_inlets = 3`` ile AYNI sayı; HRMA seçimi (literatür değeri
#: yok). Hibrit /calculate yolu kendi beyanlı varsayılanını (``n_slots``)
#: AÇIKÇA gönderir.
SWIRL_TANGENTIAL_INLETS_DEFAULT = 3
#: Bir devredeki delik/giriş sayısı üst sınırı — planlayıcının kendi sınırı
#: (``DEFAULT_CONSTRAINTS['n_max']``); eleman girdileri için de aynı kapı.
ELEMENT_COUNT_MAX = int(DEFAULT_CONSTRAINTS['n_max'])

#: İstek alanı adları (/calculate) ⟷ ``spec['impingement']`` / ``spec['swirl']``
#: anahtarları. Uç bu tabloyla çevirir; ad ikinci kez yazılmaz.
ELEMENT_REQUEST_FIELDS = {
    # Duş başlığı: delik sayısı ve imalat bandı artık DEVRE planlayıcısına
    # gider (``n_orifices_ox`` / ``orifice_constraints``). ÖLÇÜLDÜ (V301/E2,
    # 1 kN N₂O): ``n_holes = 8`` ekran bloğunda 8 × Ø1,292 mm, devrede
    # 3 × Ø2,111 mm basıyordu; bant [1,0; 1,5] mm devreye hiç girmiyordu
    # (ekran yalnız "bant dışı" uyarısı basıyordu).
    'showerhead': {
        'n_holes': 'n_holes',
        'd_min_mm': 'hole_diameter_min',
        'd_max_mm': 'hole_diameter_max',
    },
    'impingement': {
        'pairs': 'element_pairs',
        'hole_d_mm': 'orifice_diameter',
        'full_angle_deg': 'impingement_angle',
    },
    'swirl': {
        'theta_target_deg': 'swirl_angle',
        'chamber_d_mm': 'swirl_chamber_diameter',
        'n_inlets': 'n_slots',
        'slot_w_mm': 'slot_width',
        'slot_h_mm': 'slot_height',
    },
}

LIKE_DOUBLET_PLAN_BASIS = (
    'Like-on-like doublet (single liquid stream): the holes come in '
    'same-fluid pairs, so the hole count is EVEN. The total flow area is the '
    'injector circuit\'s (discharge coefficient and mass-flux model - SPI, '
    'or Dyer NHNE for self-pressurised N2O - at the circuit pressure drop); '
    'with a fixed pair count the hole diameter is solved from that area.')
LIKE_DOUBLET_AUTO_EVEN_BASIS = (
    'auto plan: the circuit planner returned an odd hole count, which cannot '
    'form like-doublets; the plan uses the next even count and re-solves the '
    'diameter from the same flow area')


class ElementPlanInputError(ValueError):
    """Pintle dışı eleman girdisi geçersiz/tutarsız (uçta HTTP 422).

    ``invalid_fields`` E1 ``PintleGeometryInputError`` ile aynı biçimdedir:
    ``{field, reason, message, ...}`` (``field`` İSTEK alanı adıdır).
    """

    def __init__(self, message, invalid_fields):
        super().__init__(message)
        self.invalid_fields = list(invalid_fields)


def _eleman_kaydi(alan, reason, message, **ek):
    kayit = {'field': alan, 'reason': reason, 'message': message}
    kayit.update(ek)
    return kayit


def element_clean_inputs(kind, raw):
    """Eleman girdilerinin tel/aralık kapısı (``kind``: impingement | swirl).

    ``raw`` ``spec[kind]`` sözlüğüdür. Döner ``(temiz, hatalar)``; ``temiz``
    yalnız VERİLEN alanları taşır. ``None`` / ``''`` verilmedi demektir;
    ``0`` da bu alanlar için uçların BELGELİ "verilmedi, çözücü türetir"
    sentinelidir (``_CALCULATE_UC_VARSAYILANLARI``: ``element_pairs`` /
    ``swirl_*`` 0 → ``not_supplied_solver_derives``). Dize, ``bool``, NaN,
    sonsuz, negatif, kesirli adet ve aralık dışı açı adıyla reddedilir; sayı
    kırpılmaz, yerine varsayılan konmaz.
    """
    temiz, hatalar = {}, []
    adlar = ELEMENT_REQUEST_FIELDS.get(kind)
    if adlar is None:
        raise ValueError(f'unknown element kind: {kind!r}')
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return temiz, [_eleman_kaydi(
            kind, 'not_an_object',
            f"the '{kind}' specification must be an object of named fields")]
    bilinen = set(adlar)
    for anahtar in raw:
        if anahtar not in bilinen:
            hatalar.append(_eleman_kaydi(
                str(anahtar)[:40], 'unknown_field',
                f"'{kind}' accepts only: " + ', '.join(sorted(bilinen))
                + '. The field was not mapped to anything.'))
    for anahtar, alan in adlar.items():
        v = raw.get(anahtar)
        if v is None or v == '':
            continue
        sayi, neden = _pintle_sayi(v)
        if sayi is not None and sayi == 0.0:
            continue                       # belgeli "verilmedi" sentineli
        if neden is None and anahtar in ('pairs', 'n_inlets', 'n_holes'):
            if sayi != int(sayi) or sayi < 1:
                neden = 'not_a_positive_whole_number'
            else:
                ust = (ELEMENT_COUNT_MAX // 2 if anahtar == 'pairs'
                       else ELEMENT_COUNT_MAX)
                if sayi > ust:
                    neden = 'out_of_range'
        elif neden is None and anahtar in ('hole_d_mm', 'chamber_d_mm',
                                           'slot_w_mm', 'slot_h_mm',
                                           'd_min_mm', 'd_max_mm'):
            if not sayi > 0.0:
                neden = 'not_positive'
        elif neden is None and anahtar == 'full_angle_deg':
            lo, hi = IMPINGEMENT_FULL_ANGLE_OPEN_RANGE_DEG
            if not (lo < sayi < hi):
                neden = 'out_of_range'
        elif neden is None and anahtar == 'theta_target_deg':
            if not (_SWIRL_THETA_MIN_DEG <= sayi <= _SWIRL_THETA_MAX_DEG):
                neden = 'out_of_range'
        if neden:
            ek = {'submitted': str(v)[:40]}
            if anahtar == 'pairs':
                ek.update(unit='count',
                          accepted_range=[1, ELEMENT_COUNT_MAX // 2])
                metin = (f"'{alan}' is the number of like-doublet pairs (two "
                         f'holes each); it must be a whole number between 1 '
                         f'and {ELEMENT_COUNT_MAX // 2} (the circuit planner '
                         f'limit of {ELEMENT_COUNT_MAX} holes).')
            elif anahtar == 'n_holes':
                ek.update(unit='count', accepted_range=[1, ELEMENT_COUNT_MAX])
                metin = (f"'{alan}' is the number of showerhead orifices; it "
                         f'must be a whole number between 1 and '
                         f'{ELEMENT_COUNT_MAX} (the circuit planner limit).')
            elif anahtar == 'n_inlets':
                ek.update(unit='count', accepted_range=[1, ELEMENT_COUNT_MAX])
                metin = (f"'{alan}' is the number of tangential inlet slots "
                         f'per swirl element; it must be a whole number '
                         f'between 1 and {ELEMENT_COUNT_MAX}.')
            elif anahtar in ('hole_d_mm', 'chamber_d_mm', 'slot_w_mm',
                             'slot_h_mm', 'd_min_mm', 'd_max_mm'):
                ek.update(unit='mm')
                metin = (f"'{alan}' is a length in mm and must be a finite "
                         'positive JSON number.')
            elif anahtar == 'full_angle_deg':
                lo, hi = IMPINGEMENT_FULL_ANGLE_OPEN_RANGE_DEG
                ek.update(unit='deg', accepted_range=[lo, hi])
                metin = (f"'{alan}' is the FULL angle 2θ between the two "
                         f'jets of a doublet; it must lie strictly between '
                         f'{lo:g} deg (parallel jets, no impingement) and '
                         f'{hi:g} deg (head-on jets).')
            else:
                ek.update(unit='deg', accepted_range=[_SWIRL_THETA_MIN_DEG,
                                                      _SWIRL_THETA_MAX_DEG])
                metin = (f"'{alan}' is the TARGET spray half-angle; outside "
                         f'[{_SWIRL_THETA_MIN_DEG:.1f}, '
                         f'{_SWIRL_THETA_MAX_DEG:.1f}] deg the '
                         'Giffen-Muraszew solver cannot find a swirl geometry '
                         'that produces it, and it is NOT clamped.')
            hatalar.append(_eleman_kaydi(alan, neden, metin, **ek))
            continue
        temiz[anahtar] = (int(sayi) if anahtar in ('pairs', 'n_inlets',
                                                    'n_holes')
                          else float(sayi))
    if kind == 'showerhead':
        d_lo = temiz.get('d_min_mm', DEFAULT_CONSTRAINTS['d_min_mm'])
        d_hi = temiz.get('d_max_mm', DEFAULT_CONSTRAINTS['d_max_mm'])
        if ('d_min_mm' in temiz or 'd_max_mm' in temiz) and not d_lo < d_hi:
            hatalar.append(_eleman_kaydi(
                'hole_diameter_max' if 'd_max_mm' in temiz
                else 'hole_diameter_min', 'band_inverted',
                f'the hole diameter band must have min < max (got '
                f'{d_lo:g}-{d_hi:g} mm; a value left empty takes the '
                f'{DEFAULT_CONSTRAINTS["d_min_mm"]:g}-'
                f'{DEFAULT_CONSTRAINTS["d_max_mm"]:g} mm default).',
                submitted={'hole_diameter_min': temiz.get('d_min_mm'),
                           'hole_diameter_max': temiz.get('d_max_mm')},
                unit='mm'))
    return temiz, hatalar


def _impingement_half_angle(spec):
    """Çarpışma yarı açısı ve künyesi (``spec['impingement']``'tan).

    Alan verilmezse varsayılan ``IMPINGE_HALF_ANGLE_DEG`` ve künye metni
    swirl/çift dallarının eski metniyle BİT-AYNI (sıvı ve panel yolları
    değişmez).
    """
    imp = spec.get('impingement') if isinstance(spec, dict) else None
    tam = None
    if imp is not None:
        temiz, hatalar = element_clean_inputs('impingement', imp)
        plan = [a for a in ('pairs', 'hole_d_mm') if a in temiz]
        if plan:
            hatalar = hatalar + [_eleman_kaydi(
                ELEMENT_REQUEST_FIELDS['impingement'][a],
                'not_read_by_this_solver',
                'the pair count / hole diameter plan of a like-doublet is '
                'resolved by design_like_doublet (hybrid like-on-like '
                'doublet); design_injector does not read it and does not '
                'ignore it silently') for a in plan]
        if hatalar:
            raise ElementPlanInputError(
                'Impingement element inputs rejected: ' + '; '.join(
                    f"{h['field']} ({h['reason']})" for h in hatalar),
                hatalar)
        tam = temiz.get('full_angle_deg')
    if tam is None:
        return IMPINGE_HALF_ANGLE_DEG, (
            f'2*theta = {2 * IMPINGE_HALF_ANGLE_DEG:.0f} deg impinging '
            'doublet design choice; the half angle is a fixed element '
            'geometry choice (NASA SP-8089), NOT solved from the jet '
            'momentum or the spray field')
    tam = float(tam)
    return tam / 2.0, (
        f'2*theta = {tam:g} deg from the request (impingement_angle); an '
        'element geometry choice, NOT solved from the jet momentum or the '
        'spray field')


def _swirl_element_overrides(spec, r_o):
    """Swirl dalının girdap odası yarıçapı ve teğet giriş sayısı.

    Verilmezse ``r_s = SWIRL_CHAMBER_D_OVER_DO/2 · d_o`` ve
    ``SWIRL_TANGENTIAL_INLETS_DEFAULT`` (eski sayılarla bit-aynı).
    Döner ``(r_s [m], n_inlets, chamber_source)``; oda çapı istekten
    gelmediyse ``chamber_source`` ``None``dır (2,5·d_o varsayımı, dalın
    ``swirl_chamber_radius_assumed`` künyesi).
    """
    sw = spec.get('swirl') if isinstance(spec, dict) else None
    sw = sw if isinstance(sw, dict) else {}
    d_s = sw.get('chamber_d_mm')
    n_in = sw.get('n_inlets')
    if d_s not in (None, '', 0):
        r_s = float(d_s) * 0.5e-3
        kaynak = 'request (swirl_chamber_diameter)'
    else:
        r_s = SWIRL_CHAMBER_D_OVER_DO * r_o
        kaynak = None
    n_inlets = (int(n_in) if n_in not in (None, '', 0)
                else SWIRL_TANGENTIAL_INLETS_DEFAULT)
    return r_s, n_inlets, kaynak


def design_like_doublet(spec):
    """Hibrit benzer-akışkan çift planı: ÇİFT sayıda delik, kanon alan.

    ``spec['impingement']`` isteğe bağlı ``pairs`` (çift sayısı),
    ``hole_d_mm`` (delik çapı) ve ``full_angle_deg`` taşır (kapı
    ``element_clean_inputs``). Kurallar:

    * hiçbiri: devrenin otomatik planı; delik sayısı tekse bir sonraki çift
      sayıya geçilir ve çap AYNI akış alanından yeniden çözülür;
    * yalnız çift sayısı: n = 2·çift sabit, çap akış alanından;
    * çap (çift sayısı verilmiş ya da verilmemiş): çift sayısı en yakın tam
      sayıdır (ya da verilendir); 2·çift·(π d²/4) devrenin akış alanından
      ``LIKE_DOUBLET_PLAN_REL_TOL``'dan fazla saparsa ``ElementPlanInputError``
      (422, en yakın planlarla). Tolerans içindeyse yayımlanan çap o delik
      sayısında hedef debiyi TAM teslim eden çaptır; istenen çap ve sapma
      ``element_plan`` künyesinde durur.

    Döner: ``design_injector`` sözlüğü + ``element_plan`` künyesi.
    """
    if not isinstance(spec, dict):
        raise ValueError('spec must be a dictionary')
    imp = spec.get('impingement')
    temiz, hatalar = element_clean_inputs('impingement', imp)
    if hatalar:
        raise ElementPlanInputError(
            'Impingement element inputs rejected: ' + '; '.join(
                f"{h['field']} ({h['reason']})" for h in hatalar), hatalar)
    taban = {k: v for k, v in spec.items() if k != 'n_orifices_ox'}
    taban['injector_type'] = 'like_impinging'
    # Devre girdisi yalnız açıyı taşır; çift sayısı/çap planı burada kurulur.
    taban['impingement'] = ({'full_angle_deg': temiz['full_angle_deg']}
                            if 'full_angle_deg' in temiz else None)
    if taban['impingement'] is None:
        taban.pop('impingement')
    cift = temiz.get('pairs')
    cap = temiz.get('hole_d_mm')

    def _tasarla(n_delik):
        s = dict(taban)
        if n_delik is not None:
            s['n_orifices_ox'] = int(n_delik)
        return design_injector(s)

    plan = {'basis': LIKE_DOUBLET_PLAN_BASIS,
            'requested_pairs': cift, 'requested_hole_d_mm': cap}
    if cap is None:
        if cift is not None:
            det = _tasarla(2 * cift)
            plan['pair_count_source'] = 'request (element_pairs)'
        else:
            det = _tasarla(None)
            if det.get('status') == 'success':
                n0 = int(det['ox_circuit']['n_orifices'])
                if n0 % 2:
                    det = _tasarla(n0 + 1)
                    plan['pair_count_source'] = LIKE_DOUBLET_AUTO_EVEN_BASIS
                    plan['auto_plan_odd_hole_count'] = n0
                else:
                    plan['pair_count_source'] = ('auto plan (the circuit '
                                                 'planner count is even)')
    else:
        det0 = _tasarla(2 * cift if cift is not None else None)
        if det0.get('status') != 'success':
            return det0
        a_akis = float(det0['ox_circuit']['total_area_mm2'])
        a_delik = np.pi * cap ** 2 / 4.0
        p = cift if cift is not None else max(1, int(round(
            a_akis / (2.0 * a_delik))))
        oran = 2.0 * p * a_delik / a_akis
        if abs(oran - 1.0) > LIKE_DOUBLET_PLAN_REL_TOL:
            p_alt = max(1, int(np.floor(a_akis / (2.0 * a_delik))))
            p_ust = p_alt + 1
            yakin = [{'pairs': q,
                      'flow_area_ratio': float(2.0 * q * a_delik / a_akis),
                      'hole_d_mm_for_exact_flow': float(np.sqrt(
                          4.0 * a_akis / (np.pi * 2.0 * q)))}
                     for q in sorted({p_alt, p_ust, p})]
            alan = ('orifice_diameter' if cift is None else 'element_pairs')
            raise ElementPlanInputError(
                'Impingement plan does not deliver the target flow', [
                    _eleman_kaydi(
                        alan, 'flow_mismatch',
                        f'{p} pair(s) of {cap:g} mm holes give a flow area '
                        f'{oran:.3f} times the area the injector circuit '
                        f'needs for the target oxidizer flow at its '
                        f'pressure drop ({a_akis:.4g} mm^2); the tolerance '
                        f'is {LIKE_DOUBLET_PLAN_REL_TOL * 100:g}%. Choose '
                        'one of the listed plans, or leave the hole '
                        'diameter empty to let the circuit size it.',
                        submitted={'element_pairs': cift,
                                   'orifice_diameter': cap},
                        flow_area_ratio=float(oran),
                        required_flow_area_mm2=a_akis,
                        nearest_plans=yakin,
                        tolerance_rel=LIKE_DOUBLET_PLAN_REL_TOL,
                        tolerance_basis=CLAMPED_PLAN_TARGET_FLOW_TOL_BASIS)])
        det = _tasarla(2 * p)
        plan['pair_count_source'] = (
            'request (element_pairs)' if cift is not None else
            'nearest whole pair count for the requested hole diameter')
        plan['requested_flow_area_ratio'] = float(oran)
        plan['hole_d_basis'] = (
            'the published hole diameter delivers the target flow exactly '
            'with this hole count; the requested diameter gives the flow '
            'area ratio above (within the tolerance)')
    if det.get('status') == 'success':
        n = int(det['ox_circuit']['n_orifices'])
        plan['pairs'] = n // 2
        plan['hole_count'] = n
        plan['hole_d_mm'] = float(det['ox_circuit']['orifice_d_mm'])
        if cap is not None:
            plan['hole_d_deviation_rel'] = float(plan['hole_d_mm'] / cap - 1.0)
        plan['tolerance_rel'] = LIKE_DOUBLET_PLAN_REL_TOL
        det['element_plan'] = plan
        # Desen açıklaması çift sayısını devrenin planından yazar (eski
        # ``n // 2`` tek sayıda delikte bir deliği açıkta bırakıyordu).
    return det


#: Swirl yuva (slot) modunda K = A_p/(D_s·d_o(K)) ikiye bölmeyle çözülür.
#: Yineleme sayısı ve yayın denetimi toleransı SAYISAL çözüm ayarıdır
#: (fizik değil): 200 bölme K aralığını makine duyarlığına indirir; yayımlanan
#: giriş alanı istenen yuva alanından 1e-6'dan fazla saparsa sonuç
#: yayımlanmaz.
SWIRL_SLOT_BISECTION_ITER = 200
SWIRL_SLOT_AREA_CHECK_TOL = 1e-6

SWIRL_ELEMENT_PLAN_BASIS = (
    'Pressure-swirl elements: the injector circuit plans the element count '
    'and the exit orifice diameter from the oxidizer flow area (its mass-flux '
    'model - SPI, or Dyer NHNE for self-pressurised N2O - with the swirl '
    'discharge coefficient Cd(K)); the tangential inlet area of each element '
    'is A_p = K*D_s*d_o (Lefebvre & McDonell, Atomization and Sprays 2nd ed. '
    'Ch. 6).')


def _swirl_hata(hatalar):
    return ElementPlanInputError(
        'Swirl element inputs rejected: ' + '; '.join(
            f"{h['field']} ({h['reason']})" for h in hatalar), hatalar)


def design_swirl_element(spec):
    """Hibrit basınç-swirl elemanı — tek kanon (V301/E2).

    ``spec['swirl']`` isteğe bağlı: ``theta_target_deg`` (hedef sprey yarı
    açısı), ``chamber_d_mm`` (girdap odası çapı D_s), ``n_inlets`` (eleman
    başına teğet yuva sayısı), ``slot_w_mm`` / ``slot_h_mm`` (yuva genişliği /
    yüksekliği; İKİSİ BİRLİKTE). Kapı ``element_clean_inputs``.

    * Yuva ölçüsü yoksa: K hedef açıdan (verilmezse devrenin 45°'si) —
      ``design_injector`` ile birebir aynı çağrı.
    * Yuva ölçüsü varsa: K yuva alanından çözülür. Eleman sayısı devrenin
      planından alınır ve SABİTLENİR; sonra K = A_p/(D_s·d_o(K)) sabit-nokta
      denklemi ikiye bölmeyle çözülür (A_p = n_yuva·w·h eleman başına; D_s
      verilmezse ``SWIRL_CHAMBER_D_OVER_DO``·d_o). Çözüm Giffen-Muraszew
      zarfının (K ∈ [0.02, 20]) dışına düşerse ``ElementPlanInputError``
      (422) — K kırpılmaz. Yuvalar ile hedef açı
      birlikte verilirse K iki kez belirlenmiş olur: 422.

    Döner: ``design_injector`` sözlüğü + ``element_plan`` künyesi.
    """
    if not isinstance(spec, dict):
        raise ValueError('spec must be a dictionary')
    sw = spec.get('swirl')
    sw = dict(sw) if isinstance(sw, dict) else ({} if sw is None else sw)
    k_istek = sw.pop('K', None) if isinstance(sw, dict) else None
    temiz, hatalar = element_clean_inputs('swirl', sw)
    w = temiz.get('slot_w_mm')
    h = temiz.get('slot_h_mm')
    if (w is None) != (h is None):
        eksik = 'slot_height' if h is None else 'slot_width'
        hatalar.append(_eleman_kaydi(
            eksik, 'incomplete_pair',
            "the slot width and the slot height fix the tangential inlet "
            "area only together; give both or leave both empty (the circuit "
            "then sizes the slots from the target spray angle)"))
    if w is not None and h is not None and 'theta_target_deg' in temiz:
        hatalar.append(_eleman_kaydi(
            'swirl_angle', 'conflicts_with_slot_geometry',
            'the slot geometry already fixes the atomizer constant K and '
            'with it the spray angle; a target spray half-angle cannot also '
            'be imposed. Leave one of them empty.',
            submitted=temiz['theta_target_deg']))
    if k_istek is not None and (w is not None or 'theta_target_deg' in temiz):
        hatalar.append(_eleman_kaydi(
            'K', 'conflicts_with_swirl_inputs',
            'K, the slot geometry and the target spray half-angle each fix '
            'the atomizer constant; give only one of them.'))
    if hatalar:
        raise _swirl_hata(hatalar)
    devre_sw = {a: temiz[a] for a in ('theta_target_deg', 'chamber_d_mm',
                                      'n_inlets') if a in temiz}
    if k_istek is not None:
        devre_sw['K'] = k_istek
    taban = {k: v for k, v in spec.items() if k != 'swirl'}
    taban['injector_type'] = 'swirl'

    def _tasarla(ek_sw, n_delik=None):
        s = dict(taban)
        birlesik = dict(devre_sw)
        birlesik.update(ek_sw or {})
        if birlesik:
            s['swirl'] = birlesik
        if n_delik is not None:
            s['n_orifices_ox'] = int(n_delik)
        return design_injector(s)

    plan = {'basis': SWIRL_ELEMENT_PLAN_BASIS}
    if w is None:
        det = _tasarla(None)
        plan['k_source'] = ('request (K)' if k_istek is not None else
                            'target spray half-angle (request swirl_angle)'
                            if 'theta_target_deg' in temiz else
                            'circuit default target spray half-angle')
    else:
        det = _tasarla(None)
        if det.get('status') != 'success':
            return det
        oxc0 = det['ox_circuit']
        n_el = int(oxc0['n_orifices'])
        n_yuva = int(temiz.get('n_inlets') or SWIRL_TANGENTIAL_INLETS_DEFAULT)
        a_p = n_yuva * w * h * 1e-6                     # m², eleman başına
        # Devrenin kütle akısı G = ṁ/(Cd·A): SPI'de √(2ρΔP), NHNE'de
        # iki-fazlı akı; ikisinde de ṁ Cd·A ile DOĞRUSALDIR (nhne_mass_flow),
        # yani G Cd'den bağımsızdır. Eleman sayısı sabitken çıkış orifis
        # çapı d_o(K) = √(4ṁ/(π·n·Cd(K)·G)) olur ve A_p(K) = K·D_s·d_o
        # K'da monoton artar (eski ekran bloğu çözücüsünün aynı gerekçesi),
        # bu yüzden ikiye bölme yeterlidir.
        mdot = float(spec.get('mdot_ox'))
        g_akisi = mdot / (float(oxc0['cd'])
                          * float(oxc0['total_area_mm2']) * 1e-6)

        def _d_o(k_):
            return float(np.sqrt(4.0 * mdot / (
                np.pi * n_el * swirl_solve(k_)['cd'] * g_akisi)))

        def _a_p(k_):
            d_o_ = _d_o(k_)
            d_s_ = (temiz['chamber_d_mm'] * 1e-3 if 'chamber_d_mm' in temiz
                    else SWIRL_CHAMBER_D_OVER_DO * d_o_)
            return k_ * d_s_ * d_o_

        a_lo, a_hi = _a_p(_SWIRL_K_MIN), _a_p(_SWIRL_K_MAX)
        if not (a_lo <= a_p <= a_hi):
            raise _swirl_hata([_eleman_kaydi(
                'slot_width', 'outside_swirl_envelope',
                f'{n_yuva} slot(s) of {w:g} x {h:g} mm per element '
                f'({a_p * 1e6:.4g} mm^2) are outside what the Giffen-Muraszew '
                f'solution can produce with the {n_el}-element plan: the '
                f'atomizer constant K must lie in [{_SWIRL_K_MIN:g}, '
                f'{_SWIRL_K_MAX:g}], i.e. a tangential inlet area of '
                f'{a_lo * 1e6:.4g}-{a_hi * 1e6:.4g} mm^2 per element. K was '
                'NOT clamped. Change the slot size or count, or leave the '
                'slots empty to size them from the target spray angle.',
                submitted={'slot_width': w, 'slot_height': h,
                           'n_slots': n_yuva},
                accepted_inlet_area_mm2_per_element=[a_lo * 1e6,
                                                     a_hi * 1e6])])
        lo_k, hi_k = _SWIRL_K_MIN, _SWIRL_K_MAX
        for _ in range(SWIRL_SLOT_BISECTION_ITER):
            orta = 0.5 * (lo_k + hi_k)
            if _a_p(orta) < a_p:
                lo_k = orta
            else:
                hi_k = orta
        k = 0.5 * (lo_k + hi_k)
        det = _tasarla({'K': k}, n_delik=n_el)
        if det.get('status') != 'success':
            return det
        a_p_yayin = float((det.get('swirl_geometry') or {}).get(
            'tangential_inlet_area_mm2', float('nan'))) * 1e-6
        if not (abs(a_p_yayin / a_p - 1.0) <= SWIRL_SLOT_AREA_CHECK_TOL):
            raise _swirl_hata([_eleman_kaydi(
                'slot_width', 'not_solvable',
                'the slot geometry did not reproduce itself through the '
                f'circuit solution (published inlet area {a_p_yayin * 1e6:.6g}'
                f' mm^2 against {a_p * 1e6:.6g} mm^2); no geometry was '
                'published', submitted={'slot_width': w, 'slot_height': h})])
        plan['k_source'] = ('slot geometry (request slot_width x '
                            'slot_height x n_slots), K = A_p/(D_s*d_o) '
                            'solved with the element count held at the '
                            'circuit plan')
        plan['slot_w_mm'] = float(w)
        plan['slot_h_mm'] = float(h)
    if det.get('status') == 'success':
        g = det.get('swirl_geometry') or {}
        plan['elements'] = int(det['ox_circuit']['n_orifices'])
        plan['exit_orifice_d_mm'] = float(det['ox_circuit']['orifice_d_mm'])
        plan['atomizer_constant_K'] = g.get('K')
        plan['tangential_inlets_per_element'] = g.get('tangential_inlets')
        plan['tangential_inlet_area_mm2_per_element'] = g.get(
            'tangential_inlet_area_mm2')
        plan['swirl_chamber_d_mm'] = g.get('swirl_chamber_d_mm')
        det['element_plan'] = plan
    return det


#: V301/E2 (E1 devri madde 5) — hibrit pintle radyal akış payının kabul
#: bandı. ``_resolve_pintle_geometry_core`` payı bu banda ``np.clip`` ile
#: kırpar (E1 bölgesi, değiştirilmedi); ``/api/injector-design`` ucu bandın
#: dışını artık 422 ile adıyla reddeder, yani kırpma ürün yolunda sessizce
#: çalışmaz. Sayılar o kırpmanın sayılarıdır (bekçi
#: ``tests/test_v301_enjektor_genel_panel.py`` ikisini eşitler); HRMA
#: seçimi, literatür değeri yok (``PINTLE_RULE_BASIS['radial_flow_fraction']``).
PINTLE_RADIAL_FRACTION_BAND = (0.1, 0.9)


# ---------------------------------------------------------------------------
# v3.0.1 (V301/H2) — HİBRİT TEK AKIŞKANLI KOAKSİYEL ELEMAN (devre kanonu)
#
# ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/bilinen/hibrit/once.json, taban
# 6369bf037; E2 KARAR-7): devre modelinde tek akışkanlı koaksiyel eleman
# yoktu. Hibrit 'coaxial' isteği ``design_injector``da "Invalid
# injector_type" ile düşüyor, motor bloğu ``not_analyzed`` kalıyordu; plaka
# (ekran) bloğu kendi ΔP'siyle boyutlanıyordu (istekteki 4 bar = %20 P_c,
# kaynak "user override"). Kendinden basınçlı N₂O'da besleme gerçeği
# P_sat − P_c = 30,54 bar'dır; plaka P₁ = 24 bar < P_v = 50,54 bar ile var
# olmayan bir orifis için K_c = −6,64 basıyordu.
#
# Eleman artık devrenin kendisidir: TEK akışkan (oksitleyici), diğer
# tiplerle AYNI besleme (P_sat, kullanıcı tank basıncı ya da tasarım ΔP
# oranı), AYNI Cd tablosu ve AYNI kütle akısı modeli (SPI; kendinden
# basınçlı N₂O'da Dyer NHNE). İç jet ve dış anülüs aynı manifolddan, aynı
# ΔP ve aynı Cd ile beslenir: ṁ_dal = Cd·A_dal·G ve G dal başına aynıdır
# (``nhne_mass_flow`` delik geometrisi almaz) — toplam ölçüm alanı iç jete
# f, anülüse 1 − f oranında bölünür (pintle akış payıyla aynı gerekçe,
# ``PINTLE_FLOW_SPLIT_BASIS``). Dal başına ayrı Cd ve iç kayıplar
# MODELLENMEZ (beyan ``flow_split_basis``).
#
# Sabitler TEK yerde (bu modül); ekran bloğu (hrma/utils/injector_design.py)
# ve uç (app.py) bu adların KİMLİK takma adlarını okur (E2'nin
# ``SWIRL_CHAMBER_D_RATIO`` deseni). Sayılar DEĞİŞMEDİ.
# ---------------------------------------------------------------------------
#: Devrenin tek akışkanlı koaksiyel eleman sözcüğü (``model_injector_type``).
#: Sıvı motorun iki akışkanlı ``coax_swirl`` elemanından AYRI bir addır;
#: ``_VALID_TYPES`` listesine girmez (sıvı yolu ve onun hata metinleri
#: bit-aynı kalır), çağrı ``design_coaxial_element``ten geçer.
COAXIAL_SINGLE_FLUID_TYPE = 'coaxial_single_fluid'
#: İç jet debi payı varsayılanı ve kabul bandı — HRMA seçimi, literatür
#: değeri yok (V301/E2: bant dışı KIRPILMAZ, uçta 422).
COAX_INNER_FLOW_FRACTION = 0.6      # iç jet debi payı (kalan: dış anülüs)
COAX_INNER_FLOW_FRACTION_BAND = (0.1, 0.9)
COAX_INNER_FLOW_FRACTION_BASIS = (
    'HRMA choice (no literature value): default inner-jet share 0.6 of the '
    'oxidizer flow, accepted band 0.1-0.9; the single-fluid coaxial element '
    'splits ONE metering area between the inner jet and the outer annulus '
    'with the same discharge coefficient')
#: İç jet girintisi ≈ 1·d_iç ve iç boru et kalınlığı max(0,5 mm, 0,1·d_iç):
#: HRMA plaka modeli kuralları, literatür değeri yok (sayılar ekran
#: bloğunun v2.6.x değerleri; V301/H2'de yalnız TEK yere taşındı).
COAX_RECESS_LD = 1.0                # iç jet girintisi ≈ 1·d_inner
COAX_WALL_MIN_MM = 0.5              # iç boru et kalınlığı alt sınırı
COAX_WALL_T_OVER_D = 0.1            # iç boru et kalınlığı / d_inner
COAX_WALL_BASIS = (
    'HRMA plate-model rule (no literature value): inner post wall = '
    'max(0.5 mm, 0.1 x inner jet diameter)')
COAX_RECESS_BASIS = (
    'computed: recess = 1 x inner jet diameter (HRMA plate-model rule, no '
    'literature value)')
COAX_ELEMENT_COUNT_BASIS = (
    'ONE coaxial element carries the whole oxidizer flow (the plate model of '
    'v2.6.x, unchanged); multi-element coaxial arrays are not modelled')
COAXIAL_ELEMENT_PLAN_BASIS = (
    'Single-fluid coaxial element (hybrid: inner jet + outer annulus, both '
    'oxidizer). The total metering area is the injector circuit\'s (its '
    'discharge coefficient and mass-flux model - SPI, or Dyer NHNE for '
    'self-pressurised N2O - at the circuit pressure drop); the inner jet '
    'takes the share f of it, the annulus the rest.')
COAXIAL_FLOW_SPLIT_BASIS = (
    'both branches are fed from the same manifold at the same pressure drop '
    'with the circuit\'s single discharge coefficient and mass flux G, so '
    'mdot_branch = Cd*A_branch*G and the flow share equals the area share '
    '(the same basis as the pintle flow split); separate branch discharge '
    'coefficients and internal losses are NOT modelled')
COAXIAL_ATOMIZATION_BASIS = (
    'NOT MODELLED: no atomization correlation for a single-fluid coaxial '
    '(round jet + annular sheet) element is implemented, and the plain-'
    'orifice Elkotb correlation does not describe the annular sheet; no SMD '
    'or spray angle is published')
#: Motor özetindeki ``number_of_orifices`` / ``orifice_diameter_mm``
#: koaksiyelde devrenin EŞDEĞER düz orifis planıdır (Cd'nin L/D'si ve toplam
#: alan onunla çözülür) — pintle'ın ``PINTLE_EQUIVALENT_ORIFICE_PLAN_BASIS``
#: deseni.
COAXIAL_EQUIVALENT_ORIFICE_PLAN_BASIS = (
    'number_of_orifices / orifice_diameter_mm are the circuit\'s EQUIVALENT '
    'straight-orifice plan of the coaxial element (the total metering area '
    'and the discharge coefficient are solved with it); the element itself '
    'is ONE inner jet + annulus - see coaxial_geometry')


def coaxial_element_geometry(a_total_m2, f_inner, wall_thickness_m=None):
    """Tek akışkanlı koaksiyel elemanın geometrisi — TEK işlev.

    Devre (``design_coaxial_element``) ve ΔP açık ezmesindeki ekran bloğu
    aynı işlevi çağırır. Toplam ölçüm alanı A [m²] iç jete ``f_inner``,
    anülüse ``1 − f_inner`` oranında bölünür; iç boru et kalınlığı
    verilmezse max(``COAX_WALL_MIN_MM``, ``COAX_WALL_T_OVER_D``·d_iç).
    Anülüs iç çapı D_i = d_iç + 2t, dış çapı alanından çözülür:
    D_o = √(D_i² + 4·A_anülüs/π). Girinti ``COAX_RECESS_LD``·d_iç.
    Döner (SI, m / m²): ``d_inner, t_wall, D_i, gap, D_o, recess,
    A_inner, A_annulus``.
    """
    A_inner = f_inner * a_total_m2
    d_inner = 2 * np.sqrt(A_inner / np.pi)
    if wall_thickness_m is not None and wall_thickness_m > 0:
        t_wall = wall_thickness_m
    else:
        t_wall = max(COAX_WALL_MIN_MM / 1000, COAX_WALL_T_OVER_D * d_inner)
    A_ann = a_total_m2 - A_inner
    D_i = d_inner + 2 * t_wall
    gap = (np.sqrt(D_i ** 2 + 4 * A_ann / np.pi) - D_i) / 2
    D_o = D_i + 2 * gap
    recess = COAX_RECESS_LD * d_inner
    return {'d_inner': d_inner, 't_wall': t_wall, 'D_i': D_i, 'gap': gap,
            'D_o': D_o, 'recess': recess, 'A_inner': A_inner,
            'A_annulus': A_ann}


def coaxial_inner_fraction(raw):
    """İç jet debi payının değer kapısı → (f, None) ya da (None, kayıt).

    JSON sayısı (``bool``/dize sayı değildir), sonlu ve
    ``COAX_INNER_FLOW_FRACTION_BAND`` içinde olmalı; KIRPILMAZ.
    """
    from hrma.utils.input_guard import finite_number, is_bool
    lo, hi = COAX_INNER_FLOW_FRACTION_BAND
    f = None if (is_bool(raw) or isinstance(raw, str)) \
        else finite_number(raw)
    if f is None:
        return None, _eleman_kaydi(
            'coaxial_inner_flow_fraction', 'not_a_number',
            'the inner-jet share of the oxidizer flow must be a finite JSON '
            'number', submitted=str(raw)[:40])
    if not (lo <= f <= hi):
        return None, _eleman_kaydi(
            'coaxial_inner_flow_fraction', 'out_of_range',
            f'the inner-jet share of the oxidizer flow is {f:.4g}; it must '
            f'lie in [{lo:g}, {hi:g}] and it is NOT clamped',
            submitted=float(f), accepted_range=[lo, hi],
            unit='dimensionless', basis=COAX_INNER_FLOW_FRACTION_BASIS)
    return float(f), None


def design_coaxial_element(spec):
    """Hibrit tek akışkanlı koaksiyel eleman — tek kanon (V301/H2).

    ``spec['coaxial']`` isteğe bağlı: ``inner_flow_fraction`` (iç jet debi
    payı) ve ``inner_flow_fraction_source`` (künye). Verilmezse
    ``COAX_INNER_FLOW_FRACTION`` (beyanlı HRMA seçimi).

    Devre çözümü diğer tiplerle AYNI çağrıdır (``design_injector``, eşdeğer
    düz orifis planı): ΔP besleme gerçeğinden, Cd tablodan (plaka kalınlığı
    verildiyse L/D yinelemesi), kütle akısı SPI ya da Dyer NHNE. Toplam
    ölçüm alanı ``coaxial_element_geometry`` ile iç jet + anülüse bölünür.
    Atomizasyon korelasyonu yoktur (beyan; sayı yayımlanmaz).

    Döner: ``design_injector`` sözlüğü; ``injector_type`` =
    ``COAXIAL_SINGLE_FLUID_TYPE``, ``coaxial_geometry`` kanon sözlüğü,
    ``pattern`` ve ``atomization`` koaksiyelin kendisi.
    """
    if not isinstance(spec, dict):
        raise ValueError('spec must be a dictionary')
    if spec.get('motor_type') != 'hybrid':
        raise ValueError(
            "the single-fluid coaxial element applies to a hybrid (one "
            "liquid stream: the oxidizer); a liquid engine uses the "
            "two-fluid 'coax_swirl' element")
    koaks = spec.get('coaxial')
    koaks = koaks if isinstance(koaks, dict) else {}
    if koaks.get('inner_flow_fraction') is None:
        f = COAX_INNER_FLOW_FRACTION
        f_kaynak = 'module default ' + COAX_INNER_FLOW_FRACTION_BASIS
    else:
        f, hata = coaxial_inner_fraction(koaks['inner_flow_fraction'])
        if hata:
            raise ElementPlanInputError(
                'Coaxial element input rejected: '
                f"{hata['field']} ({hata['reason']})", [hata])
        f_kaynak = (koaks.get('inner_flow_fraction_source')
                    or 'caller-supplied inner_flow_fraction')
    taban = {k: v for k, v in spec.items() if k != 'coaxial'}
    taban['injector_type'] = 'showerhead'
    det = design_injector(taban)
    if det.get('status') != 'success':
        return det
    oxc = det['ox_circuit']
    a_total = float(oxc['total_area_mm2']) * 1e-6
    g = coaxial_element_geometry(a_total, f)
    det['injector_type'] = COAXIAL_SINGLE_FLUID_TYPE
    det['coaxial_geometry'] = {
        'element_count': 1,
        'element_count_basis': COAX_ELEMENT_COUNT_BASIS,
        'total_flow_area_mm2': float(oxc['total_area_mm2']),
        'inner_flow_fraction': float(f),
        'inner_flow_fraction_source': f_kaynak,
        'inner_jet_diameter_mm': float(g['d_inner'] * 1e3),
        'inner_jet_area_mm2': float(g['A_inner'] * 1e6),
        'post_wall_thickness_mm': float(g['t_wall'] * 1e3),
        'post_wall_thickness_basis': COAX_WALL_BASIS,
        'annulus_inner_diameter_mm': float(g['D_i'] * 1e3),
        'annulus_outer_diameter_mm': float(g['D_o'] * 1e3),
        'annulus_gap_mm': float(g['gap'] * 1e3),
        'annulus_area_mm2': float(g['A_annulus'] * 1e6),
        'recess_length_mm': float(g['recess'] * 1e3),
        'recess_length_basis': COAX_RECESS_BASIS,
        'mean_injection_velocity_m_s': float(oxc['velocity_m_s']),
        'discharge_coefficient': float(oxc['cd']),
        'flow_model': oxc.get('flow_model'),
        'pressure_drop_bar': float(oxc['delta_p_bar']),
        'flow_split_basis': COAXIAL_FLOW_SPLIT_BASIS,
        'basis': COAXIAL_ELEMENT_PLAN_BASIS,
    }
    det['pattern'] = {
        'description': (
            f'Single-fluid coaxial element (hybrid oxidizer): inner jet '
            f'{g["d_inner"] * 1e3:.2f} mm + annulus gap '
            f'{g["gap"] * 1e3:.3f} mm (share {f:.2f} / {1.0 - f:.2f})'),
        'n_elements': 1,
        'impingement': None,
    }
    det['atomization'] = {
        'smd_ox_um': None, 'smd_fuel_um': None,
        'correlation': 'not_modelled',
        'spray_cone_half_angle_deg': None,
        'basis': COAXIAL_ATOMIZATION_BASIS,
    }
    return det
