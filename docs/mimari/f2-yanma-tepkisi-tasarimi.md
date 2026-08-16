# F2 yanma tepkisi / yanma kararlılığı tasarımı

**Tarih:** 16 Ağustos 2026 · **Karar sahibi:** Berke (kapsam) + ana model (mimari/sayısal tasarım)
**Bağlam:** yol haritası F2 satırı: "*Akustik mod çekirdeği var (`acoustic_modes.py`, hibrit 2 /
katı 3 çağrı, 36 test). Yanma tepkisi modeli açık*". Analiz Merkezi matrisinde "Kamara akustiği —
F2 çekirdeği; görselleştirme F2 tepki modeliyle" satırı bu belgeyi bekliyor
(`analiz-merkezi-tasarimi.md` §2, §4). FINAL kapısındaki üç büyük kulvardan biri (FEA · CFD · F2).

**Bu belgenin okuma sözleşmesi:** her cümle iki sınıftan biridir.
**[ÖLÇÜLDÜ]** = bu tur dosya sisteminde/kaynakta doğrulandı, kanıtı dosya+satır ya da alıntı.
**[ÖNERİ]** = bu belgenin tasarım kararı; henüz kod değildir, uygulanınca bekçiyle kanıtlanacaktır.
Kod YAZILMADI; ürün dosyalarına dokunulmadı.

---

## 1. Bugünkü durumun ölçümü (F2'nin gerçekten nerede durduğu)

| Ne | Nerede | Ölçülen durum |
|---|---|---|
| Kamara akustik mod tablosu | `hrma/analysis/acoustic_modes.py` (572 satır) | **[ÖLÇÜLDÜ]** Rijit cidarlı kapalı-kapalı silindir öz-frekansları `f_mnq = (a/2π)·√((2α_mn/D)² + (qπ/L)²)`; α_mn kökleri `scipy.special.jnp_zeros` ile, elle yazılmamış. Chug marjı = ΔP_inj/P_c eşik hükmü. `NOT_MODELLED` sözlüğü tepki fonksiyonunun ve Rayleigh ölçütünün YOK olduğunu açıkça yazıyor (satır 134-153) |
| Bekçiler | `tests/test_akustik_modlar.py` (423 satır, 36 test) | **[ÖLÇÜLDÜ]** Analitik round-trip, literatür Bessel kökleri (1T=1,8412…), ölçekleme yasaları, F-1 mertebe çapası (440-540 Hz bandı, Oefelein & Yang 1993) |
| Hibrit bağlaması | `hybrid_rocket_engine.py:4432` `_acoustic_modes_block` | **[ÖLÇÜLDÜ]** Modülü GERÇEKTEN çağırıyor; chug oranı enjektör devresinin kendi ΔP'sinden (`injector_design.injection_pressure_drop_bar`), yoksa `NOT_EVALUATED` |
| Katı bağlaması | `solid_rocket_engine.py:4058` `_acoustic_mode_report` | **[ÖLÇÜLDÜ]** Eşdeğer silindir: gerçek kasa iç boyu + gerçek serbest gaz hacmi korunuyor (`D_eq = 2√(V/(πL))`); chug **yapısal olarak** uygulanamaz beyanı (`chug_applicability.applicable = False`) |
| Sıvı bağlaması | `liquid_rocket_engine.py:8482` `_stability_assessment` | **[ÖLÇÜLDÜ]** Modülü ÇAĞIRMIYOR — kendi içinde 1L (`a/2L`) ve 1T (`FIRST_TANGENTIAL_MODE_COEFF = 1.8412`, satır 458) hesaplıyor. `stability_rating: 'unknown'`, `acoustic_analysis: 'not_modelled'` dürüstçe beyanlı |
| Hibrit LFI beyanı | `hybrid_rocket_engine.py:4880` | **[ÖLÇÜLDÜ]** `hybrid_boundary_layer_instability: NOT_MODELLED` — "no combustion response function is solved anywhere in this solver, so no growth rate can be reported" |
| Katı L* beyanı | `solid_rocket_engine.py:4181` | **[ÖLÇÜLDÜ]** "The solid-motor low-frequency counterpart (L* / bulk-mode instability) is NOT modelled" |
| Literatür taraması | `docs/mimari/motor-analiz-katalogu.md` "Yanma kararlılığı ve akış analizleri" | **[ÖLÇÜLDÜ]** 26 kalem, künyeleri doğrulanmış (Crocco & Cheng AGARDograph 8; SP-194; Culick AG-AVT-039; CPIA 191 T-Burner Manual; Zinn AIAA 72-1050; SP-8113; Karabeyoglu JPP 21(6) 2005; Carmicino JPP 25(6) 2009; Waxman AIAA 2013-3636). Üründe sütunu F2 kalemlerinin **hepsinde "—"** |

### 1.1 Ölçülen kusurlar (F2 işinin parçası olarak kapanacak)

1. **Eşik üç yerde tanımlı** — aynı sayı, üç ayrı künye ile:
   `acoustic_modes.CHUG_DP_RATIO_RECOMMENDED = 0.20` / `_MINIMUM = 0.15` (künye: Sutton 9. baskı
   Böl. 8 + SP-194 Böl. 5-6) · `liquid_rocket_engine.CHUG_DP_PC_RECOMMENDED_LIQUID = 0.20` /
   `CHUG_DP_PC_MIN_LIQUID = 0.15` (künye: NASA SP-8089) · `transient_ballistics.DP_RATIO_WARN = 0.15`
   / `DP_RATIO_UNSTABLE = 0.05`. **[ÖLÇÜLDÜ]** Parametre tutarlılığı kuralının ihlali; ayrıca iki
   ayrı künye aynı sayıyı savunuyor.
2. **Sıvı, akustik çekirdeğin kopyasını taşıyor** — `FIRST_TANGENTIAL_MODE_COEFF = 1.8412` sabit
   yazılmış; `acoustic_modes` aynı sayıyı Bessel türev kökünden ÜRETİYOR. **[ÖLÇÜLDÜ]** İki motor
   modülden akustik tablo alırken üçüncüsü kendi iki modunu ayrı hesaplıyor.
3. **Hibritte yakıt termal özelliği yok** — `hybrid_rocket_engine._set_fuel_properties` (satır 779)
   tablosunda yalnız `density`, `combustion_temp`, `gas_constant` var. **[ÖLÇÜLDÜ]**
   `hrma/data/propellant_database.py` HTPB/parafin için `specific_heat` ve `thermal_conductivity`
   TAŞIYOR ama künyesi alan-başına değil, blok-başına ('NASA SP-8075', 'Stanford University
   Research'). Termal gecikme (κ/ṙ²) tabanlı bir model bu iki tablodan hangisini okuyacağına
   kendi başına karar VEREMEZ → kapı gerekir (§7 açık soru 4).
4. **Katıda yakıt termal iletkenliği/ısı sığası yok** — solid çözücüde yalnız yalıtım malzemesinin
   `thermal_conductivity_w_mk` değeri var (satır 288). **[ÖLÇÜLDÜ]** QSHOD tepki fonksiyonunun
   A/B parametreleri çözücü verisinden TÜRETİLEMEZ.
5. **Katalogda cümle kesik** — `motor-analiz-katalogu.md` "HRMA BAĞLAMINDA GERÇEKÇİ SIRALAMA"
   notu `#15 (hibrit LFI — geri çekilme hızı yasa` ifadesinde kesiliyor. **[ÖLÇÜLDÜ]** Bu belgenin
   sahibi değil; katalog sahibine devredilir.

---

## 2. Kapsam ve kapsam DIŞI

### 2.1 Kararsızlık sınıfı × motor tipi uygulanabilirlik matrisi **[ÖNERİ]**

| Sınıf | Hibrit | Katı | Sıvı | Neden |
|---|---|---|---|---|
| Mod tablosu (modlar NEREDE) | **var** | **var** | F2b'de bağlanır | Bugün sıvı kendi kopyasını hesaplıyor (§1.1-2) |
| Kamara doldurma/boşaltma zaman sabiti τ_c | **F2a** | **F2a** | **F2a** | `L*`, `c*`, `γ` üçünde de yayımlı |
| Chug (besleme kuplajlı alçak frekans) | **F2a** | **uygulanamaz** | **F2a** | Katıda enjektör/besleme fiziksel olarak yok (mevcut `chug_applicability` beyanı korunur) |
| L* / bulk mod (yığın modu) | **uygulanamaz** | **F2b** | chug'un içinde | Hibritte geri çekilme hızı P_c'nin ancak zayıf fonksiyonudur → kuplaj kapanmaz (Karabeyoglu, AA284a Ders 14, s. 15) |
| Hibrit LFI (termal-yanma kuplajlı, 2-100 Hz) | **F2b** | — | — | Hibridin imza kararsızlığı; ölçeklenme yasası kapalı formda (§3.4) |
| Akustik sönüm bütçesi (lüle + partikül + viskoz) | kısmi | **F2a/F2b** | kısmi | Partikül sönümü yalnız katıda veri var (β + d₄₃ ölçülü) |
| Yanma tepkisi (basınç kuplajlı R_p) | kapılı | kapılı | kapılı | Girdisi (T-burner/n) üründe YOK → §3.5 tersine çevirme |
| n-τ nötr kararlılık eğrisi | **F2b** | kapılı | **F2b** | Sıvıda τ zaten hesaplanıyor (§3.3); katıda τ yok |

### 2.2 NOT_MODELLED (beyanla çıktıya konur, sessizce yok sayılmaz) **[ÖNERİ]**

- **Ayrıntılı alev dinamiği / LES / hibrit RANS-LES** — alev transfer fonksiyonunun hesaplanması
  (katalog kalem "Yüksek sadakatli yanma kararsızlığı simülasyonu"): kapsam dışı, v3+ bile değil.
- **Doğrusal olmayan davranış:** tetikleme (triggering), limit çevrim genliği, DC kayması.
  Lineer analiz bu riski göremez; genlik HRMA'da HİÇBİR yerde tahmin edilmez.
- **Girdap dökülmesi–akustik kilitlenme (VSO/VSA/VSP).** Strouhal çakışma taraması ucuzdur ama
  girdap kaynağının konumu (inhibitör/adım/diyafram) üründe modellenmiyor → §7 açık soru 6.
- **POGO** — araç üstünden kapanan çevrim; motor tek başına tezgâhta kararlı olabilir. Araç
  yapısal modu HRMA'da yok.
- **Enjeksiyon kuplajlı YF (LOX post çeyrek dalga)** — enjektör elemanı post uzunluğu üretilmiyor
  (`injector_design` orifis çapı/hızı/eleman sayısı veriyor, post boyu vermiyor) **[ÖLÇÜLDÜ]**.
- **3B Helmholtz öz-değer çözümü / ortalama akışlı lineerleştirilmiş Euler** — mod tablosu
  analitik silindir idealleştirmesinde kalır; kademeli kavite/lüle yakınsak hacmi dahil değil
  (mevcut `equivalent_cavity` beyanı sürdürülür).
- **Baffle / akustik oyuk sönümleme VERİMİ** — boyutlandırma yardımcısı yapılabilir (§6 F2c),
  ama "şu baffle şu modu şu kadar söndürür" iddiası modellenmez (SP-8113 ampirik alanı).

---

## 3. Model kararları (kesin, gerekçeli, künyeli)

### 3.0 Temel karar — F2 HÜKÜM vermez, BÜTÇE ve EŞİK verir **[ÖNERİ]**

Yanma kararlılığı hükmü, yanma tepki fonksiyonunu bilmeyi gerektirir; tepki fonksiyonu
ölçülür (T-burner, dinamik basınç), türetilmez. HRMA'nın elinde bu ölçüm YOK. Bu yüzden:

1. **Sönüm tarafı hesaplanır** (lüle admitansı, partikül sönümü, gaz dinamiği kutbu) — girdileri
   çözücüde var.
2. **Kazanç tarafı ters çevrilir:** "bu mod nötr olsun diye yanma tepkisi NE KADAR olmalıydı?"
   → **kritik tepki eşiği** `R_crit` (basınç kuplajlı tepki fonksiyonunun gerçek kısmı cinsinden).
   Kullanıcıya literatür bandı (kompozit yakıtlarda tepe R_p tipik 1-3 mertebesi, CPIA 191 /
   Culick AG-AVT-039) YANINDA gösterilir — **kıyas**, hüküm değil.
3. **Hüküm YALNIZ çevrimi kapatabildiğimiz yerde verilir:** chug (§3.2) ve hibrit LFI (§3.4) —
   ikisinde de gecikme ve kazanç, çözücünün kendi büyüklüklerinden gelir.

Bu, CFD tasarımındaki "hüküm/doğrulama ayrımı" deseninin F2 karşılığıdır: yakınsamayan/eksik
girdili koşu sonucu gizlemez ama hüküm de vermez.

### 3.1 Merkezî büyüklük: kamara doldurma/boşaltma zaman sabiti τ_c **[ÖLÇÜLDÜ künye]**

İzotermal, konsantre-parametreli kamara kütle dengesi:

```
V/(R·T) · dP_c/dt = ṁ_üretim − P_c·A_t/c*        ⟺        dP_c/dt + P_c/τ_c = (R·T/V)·ṁ_üretim
τ_c ≡ L*/(c*·Γ²)        L* ≡ V/A_t        Γ² ≡ γ·(2/(γ+1))^((γ+1)/(γ-1))     [R·T = (c*·Γ)²]
```

Künye: Karabeyoglu, M.A., *AA284a Advanced Rocket Propulsion — Stability of Chemical Propulsion
Systems*, Stanford University, ders notu s. 5 (bu tur indirilip metni çıkarıldı; slaytta
`τ_c ≡ L*/(c*·f(γ))` yazımıyla). `Γ` vakum karakteristik hız fonksiyonudur; HRMA'da aynı büyüklük
lüle akış modülünde zaten kullanılır.

**Neden merkez:** chug, L* bulk modu ve hibrit gaz dinamiği kutbu — üçü de bu tek denklemin
farklı kapanışlarıdır. Üç motor tipinde de girdisi yayımlı: hibrit `l_star`/`l_star_achieved` +
`c_star`, katı `_case_free_volume()` + `c_star` + boğaz alanı, sıvı `l_star` + `c*` **[ÖLÇÜLDÜ]**.

### 3.2 Chug — oran kuralı yerine konsantre-parametreli çevrim **[ÖNERİ + türetim]**

Bugünkü chug hükmü "ΔP/P_c ≥ 0,20 → OK" biçiminde bir **eşik testidir**; gecikmeyi, kamara
hacmini ve L*'ı hiç görmez. Yerine klasik Summerfield çevrimi konur:

- Enjektör (sıkıştırılamaz orifis, besleme basıncı sabit): `ṁ ∝ √(P_f − P_c)`
  ⇒ `δṁ/ṁ = −(1/2)·δP_c/ΔP_inj`
- Yanma gecikmesi τ (duyarlı zaman gecikmesi): `δṁ_üretim(t) = δṁ_enjeksiyon(t − τ)`
- Kamara: §3.1 denklemi

Karakteristik denklem ve **nötr kararlılık eğrisi** (bu belgede türetildi; `J ≡ ΔP_inj/P_c`):

```
τ_c·s + 1 + (1/(2J))·e^(−sτ) = 0
nötr (s = iω):   cos(ωτ) = −2J ,   sin(ωτ) = 2J·ω·τ_c
⇒ ω = √(1 − 4J²)/(2J·τ_c)          (J < 1/2 zorunlu)
⇒ τ/τ_c = 2J·arccos(−2J)/√(1 − 4J²)
```

**Neden bu tasarımın omurgası:** klasik %15-25 kuralı bu eğrinin bir noktası olarak ÖLÇÜLEBİLİR
hâle gelir. Örnek sağlama (elle, bu belgede): `J = 0,20` ⇒ `τ/τ_c = 0,865`. Tipik sıvı motor
(`L* = 1 m`, `c* = 1800 m/s`, `γ = 1,2` ⇒ `Γ² = 0,4206`) için `τ_c = 1,32 ms`, yani nötr nokta
`τ ≈ 1,14 ms` — atomizasyon/buharlaşma zaman ölçeğinin (§3.3) tam bandında. Kural, modelin
özel hâli olarak geri geliyor; bu bir **test**tir, iddia değil (§5 basamak 3).

Künye (doğrulanacak — formülün birincil kaynaktaki yazımıyla çaprazlanacak):
Summerfield, M., "A Theory of Unstable Combustion in Liquid Propellant Rocket Systems",
*ARS Journal* 21(5), 1951, ss. 108-114 (doi:10.2514/8.4374); Harrje & Reardon (ed.), NASA SP-194,
1972, alçak frekans bölümü. Türetim yukarıda açıktır; **kaynağın kendi ifadesiyle bire bir
eşleştiği doğrulanmadan** `basis` alanında "Summerfield 1951'in formu" denmeyecek.

**Besleme endüktansı (inertance):** ikinci mertebeye çıkaran `L_f = ρ·ℓ/A_hat` terimi
opsiyoneldir, çünkü **[ÖLÇÜLDÜ]** hat uzunluğu çözülmüyor: `FEED_LINE_LENGTH_DEFAULT_M = 2.5`
ve kendi künyesi "*a layout assumption, NOT solved from a vehicle geometry*" diyor. Karar:
endüktans terimi yalnız kullanıcı gerçek hat uzunluğu verirse açılır; varsayılan hâlde
**direnç+kapasitans** formu koşar ve `inertance: not_included` beyanıyla döner (§7 açık soru 5).

### 3.3 Sıvı: n-τ ve τ'nun zaten hesaplanıyor olması **[ÖLÇÜLDÜ]**

`liquid_rocket_engine._atomisation_time` (satır 8293) ikincil parçalanma süresini
`t_b = T*·d_jet/v_bağıl·√(ρ_sıvı/ρ_gaz)` ile hesaplıyor (Pilch & Erdman 1987, *Int. J. Multiphase
Flow* 13(6); `T* ≈ 5`) ve sonucu `combustion_response_time` olarak Crocco-Cheng duyarlı zaman
gecikmesi τ diye yayımlıyor; yanında `pressure_interaction_index_n: 'not_modelled'` beyanı var.

**Karar [ÖNERİ]:** τ bu değerden gelir (yeni bir τ modeli üretilmez — tek kaynak), n ise
ÇÖZÜLMEZ. Çıktı, her akustik mod için **n-τ düzleminde nötr eğri** + motorun τ'sunun düştüğü
dikey çizgi + `n_crit` (o τ'da nötrlüğü sağlayacak n). Kullanıcı n'i verirse marj hükmü çıkar,
vermezse eşik gösterilir. Künye: Crocco, L. & Cheng, S.-I., *Theory of Combustion Instability in
Liquid Propellant Rocket Motors*, AGARDograph No. 8, Butterworths, 1956; SP-194 Böl. 4.
Eleştirel çerçeve zorunlu olarak `basis`e yazılır: Sirignano, W.A., "Driving Mechanisms for
Combustion Instability", *Combustion Science and Technology*, 2015 (n-τ sezgisel bir yaklaşımdır,
mutlak tahmin aracı değildir).

### 3.4 Hibrit LFI — kapalı form, birincil kaynaktan doğrulandı **[ÖLÇÜLDÜ]**

Karabeyoglu, M.A., De Zilwa, S., Cantwell, B., Zilliac, G., "Modeling of Hybrid Rocket Low
Frequency Instabilities", *Journal of Propulsion and Power* 21(6), 2005, ss. 1107-1116
(doi:10.2514/1.7792). Makalenin PDF'i bu tur indirilip metni çıkarıldı; denklem numaralarıyla:

```
(7)   f = 0,48/τ_bl2
(11)  τ_bl2 = c'·L·P_c/((G_o + G_t)·R·T_av)
(15)  f = 0,2341·(2 + 1/(O/F))·G_o·R·T_av/(L·P_c)        ← "universal scaling law"
      R·T_av = 6,38×10⁵ (m/s)²  GOX/LOX sistemleri
      R·T_av = 4,47×10⁵ (m/s)²  düşük enerjili oksitleyiciler (N₂O)
```

**[ÖLÇÜLDÜ — kaynak zincirinde çelişki]** Aynı yazarın Stanford ders notu (AA284a Ders 14, s. 29)
aynı yasayı `f = 0,119·(…)` katsayısıyla yazıyor; hakemli makale `0,2341` diyor (ve `0,48/c'` ile
tutarlı: `c' ≈ 2,05`, ders notundaki "c' = 2,01" ile uyumlu). Oran tam ~1,97. **Karar: hakemli
makalenin 0,2341'i kullanılır**, ders notu katsayısı kullanılmaz; bu çelişki `basis` alanında
adıyla beyan edilir (aksi hâlde ileride "kaynak şunu diyor" tartışması yeniden açılır).

**Girdilerin hepsi bugün yayımlanıyor [ÖLÇÜLDÜ]** (`hybrid_rocket_engine.py:5045-5080`):
`g_ox_initial` / `g_ox_final`, `grain_length`, `chamber_pressure`, `of_ratio` /
`of_ratio_final`, `oxidizer_type`. Yani F2b hibrit ayağı **yeni girdi istemeden** koşabilir.

**Kritik modelleme kararı:** `R·T_av` makalenin **kalibre edilmiş** port-ortalaması değeridir,
çözücünün denge kamara değeri DEĞİLDİR. Hibritin kendi `R·T_c`'si tipik olarak
`415 × 3200 ≈ 1,33×10⁶ (m/s)²`, yani makalenin GOX/LOX değerinin ~2 katı **[ÖLÇÜLDÜ, tipik HTPB
kaydından]**; çözücü değeri konursa frekans iki katına çıkar. Karar: **korelasyonun kendi sabiti
kullanılır** (oksitleyici ailesine göre kapılı: `lox`/`gox` → 6,38e5, `n2o` → 4,47e5, başka
oksitleyici → `NOT_EVALUATED`, uydurma yok) ve çözücünün `R·T_c`'si `diagnostic_ratio` olarak
YANINDA yayımlanır. Korelasyon sabitini motor değerine "iyileştirmek" kalibrasyonu bozar.

### 3.5 Katı: L* bulk modu ve tepki fonksiyonu kapısı **[ÖNERİ]**

§3.1 denklemine yarı-kararlı yanma hızı kuplajı (`ṙ = a·P^n` ⇒ `δṁ/ṁ = n·δP/P`) konursa:

```
τ_c·dδP/dt + (1 − n)·δP = 0        ⇒  gecikmesiz limitte kararsızlık ölçütü tam olarak n ≥ 1
```

**[ÖLÇÜLDÜ]** HRMA katı çözücüsünde bu ölçüt zaten var: `solid_rocket_engine.py:2715`
`if self.n >= 1.0` → `warn.solid.burn_rate_exponent_ge_one` (kritik uyarı), ayrıca `:8761`
yakınsama kapısında aynı koşul. Yani mevcut "n ≥ 1 basınç kaçağı" uyarısı, L* bulk
modunun **sıfır-gecikme özel hâlidir**. F2b'nin katı ayağı bunu genelleştirir: katı fazdaki termal
gecikme eklenince kararsızlık `n < 1` için de mümkün olur (klasik L*/chuffing modu, < 150 Hz).

Kapı: termal gecikme, yakıtın termal yayınırlığını (`κ = k/(ρ·c_p)`) ister; **[ÖLÇÜLDÜ]** katı
çözücüde yakıt `k` ve `c_p` YOK. Karar: gecikmeli form yalnız kullanıcı bu iki değeri verirse
koşar; vermezse **sıfır-gecikme ölçütü + τ_c** raporlanır ve `thermal_lag: not_supplied` beyan
edilir. QSHOD/Denison-Baum tepki fonksiyonu (A, B parametreleri) **hiçbir koşulda varsayılan
sayıyla** çalıştırılmaz; ya kullanıcıdan gelir ya da yalnız `R_crit` tersine çevirmesi (§3.0)
gösterilir. Künyeler (formül birincil kaynaktan pinlenecek — bu tur yalnız varlıkları doğrulandı):
Denison, M.R. & Baum, E., "A Simplified Model of Unstable Burning in Solid Propellants",
*ARS Journal* 31(8), 1961; Culick, F.E.C., *Unsteady Motions in Combustion Chambers for
Propulsion Systems*, RTO AGARDograph AG-AVT-039, NATO, 2006; *T-Burner Manual*, CPIA Publication
No. 191, 1969; Beckstead, M.W. & Price, E.W., "Nonacoustic Combustion Instability", *AIAA Journal*
5(11), 1967 (L* modu); NASA SP-8039, 1971.

### 3.6 Sönüm bütçesi (kazanç-kayıp, Rayleigh çerçevesi) **[ÖNERİ]**

Mod başına `α_net = α_yanma − Σα_kayıp`; HRMA yalnız kayıp tarafını hesaplar (§3.0).

| Terim | Girdi durumu | Karar |
|---|---|---|
| Lüle sönümü (yarı-kararlı kısa lüle admitansı) | `A_t`, `V`, `γ`, mod frekansı — hepsi var **[ÖLÇÜLDÜ]** | Hesaplanır; katsayı Zinn, B.T., "Review of Nozzle Damping in Solid Rocket Instabilities", AIAA 72-1050, 1972 + Culick AG-AVT-039'dan **pinlenecek** |
| Partikül sönümü | `condensed_mass_fraction` (β, yakıt ailesinden) + `particle_diameter_um` (d₄₃, Hermsen 1981) — katıda **[ÖLÇÜLDÜ]** `two_phase_loss` bloğunda yayımlı | Katıda hesaplanır (verilen frekansta optimum parçacık boyu davranışı dahil); hibrit/sıvıda `not_applicable` |
| Viskoz/cidar sönümü | sınır tabaka çözülmüyor | `NOT_MODELLED` (mertebe olarak küçük olduğu beyanıyla) |
| Yapısal/viskoelastik sönüm | tane viskoelastik modeli yok | `NOT_MODELLED` |

**Dürüstlük sonucu:** eksik kayıp terimleri `R_crit`'i **kötümser** (düşük) yapar; bu yön
`basis` alanında açıkça yazılır — kullanıcı marjın hangi yöne kaydığını bilir.

---

## 4. Girdi/çıktı sözleşmesi

### 4.1 Girdi (hepsi mevcut çözücü çıktısından; uydurma varsayılan yasak) **[ÖLÇÜLDÜ]**

| Büyüklük | Hibrit | Katı | Sıvı |
|---|---|---|---|
| T_c, γ, MW | `chamber_temperature`, `gamma`, `molecular_weight` | `self.T_c`, `self.gamma`, `mw_exhaust` | kamara kaydı |
| Kavite geometrisi | `chamber_diameter`, `chamber_length` | `_case_inner_length()`, `_case_free_volume()` | `chamber_diameter`, `chamber_length` (mm→m) |
| L*, c* | `l_star` / `l_star_achieved`, `c_star` | serbest hacim + boğaz alanı, `c_star` | `l_star`, c* |
| Enjektör ΔP | `injector_design.injection_pressure_drop_bar` | **yok (yapısal)** | `_injector_dp_fraction()` |
| Gecikme τ | `τ_bl2` (§3.4 Denk. 11) | kullanıcı (termal gecikme) | `combustion_response_time` (atomizasyon) |
| LFI girdileri | `g_ox_*`, `grain_length`, `of_ratio*`, `oxidizer_type` | — | — |
| Partikül | — | `two_phase_loss.particle_diameter_um`, β | — |
| Yanma hızı üsteli n | — | `burn_rate_exponent` | — |

**Kural:** eksik alan → o satır `NOT_EVALUATED` + `missing_inputs` listesi; mevcut modüldeki
`analyze_from_engine_result` deseninin aynısı (varsayılan üretmez, `ValueError` atar).

### 4.2 Çıktı şeması (JSON-güvenli) **[ÖNERİ]**

```jsonc
{
  "chamber_time_constant": {"tau_c_ms": 1.32, "l_star_m": 1.0, "c_star_m_s": 1800,
                            "gamma_function_sq": 0.4206, "basis": "..."},
  "modes": [ /* acoustic_modes çıktısı AYNEN — ikinci bir mod tablosu üretilmez */ ],
  "mode_budget": [                       // mod başına satır
    {"label": "1T", "frequency_hz": 4180,
     "damping": {"nozzle_1_s": 12.4, "particle_1_s": 31.0,
                 "viscous_1_s": null, "not_modelled": ["viscous", "structural"]},
     "critical_response": {"R_crit": 0.42,
                           "literature_band": {"low": 1.0, "high": 3.0, "source": "CPIA 191 / Culick AG-AVT-039"},
                           "interpretation": "threshold_not_verdict"},
     "verdict": "NOT_EVALUATED", "verdict_reason": "combustion response function not supplied"}
  ],
  "chug": {"model": "lumped_capacitance_resistance_delay",
           "dp_ratio_J": 0.20, "tau_ms": 1.1, "tau_over_tau_c": 0.83,
           "neutral_tau_over_tau_c": 0.865, "growth_rate_1_s": -18.2,
           "frequency_hz": 121.0, "verdict": "STABLE_LINEAR",
           "inertance_included": false, "inertance_basis": "feed line length is a layout assumption",
           "classical_rule_cross_check": {"rule_min": 0.15, "rule_recommended": 0.20,
                                          "model_neutral_J": 0.173}},
  "hybrid_lfi": {"frequency_hz": 14.6, "correlation": "Karabeyoglu et al. JPP 21(6) 2005, Eq. 15",
                 "RT_av_m2_s2": 638000, "RT_av_gate": "lox|gox",
                 "solver_RT_c_m2_s2": 1328000, "diagnostic_ratio": 2.08,
                 "acoustic_1L_hz": 372.0, "separation_decades": 1.4},
  "bulk_mode": {"n": 0.35, "zero_lag_criterion": "n < 1 -> no runaway",
                "thermal_lag": "not_supplied", "verdict": "PARTIAL"},
  "not_modelled": { /* §2.2 sözlüğü aynen */ },
  "inputs": { /* kullanılan her sayı + kaynağı */ }
}
```

**Hüküm/doğrulama ayrımının mekaniği [ÖNERİ]:** `verdict` alanı yalnız üç değer alabilir —
`STABLE_LINEAR`, `UNSTABLE_LINEAR`, `NOT_EVALUATED`. `R_crit` **hiçbir zaman** verdict üretmez;
onun alanı `critical_response.interpretation = "threshold_not_verdict"` ile mekanik olarak
işaretlenir ve bekçi bu alanın varlığını + verdict'in `NOT_EVALUATED` kaldığını kilitler
(kusuru koruyan bekçi dersi: eşik bir gün sessizce hükme dönüşmesin).

---

## 5. Doğrulama merdiveni (test-first; basamak başına bekçi + mutasyon kanıtı)

| # | Basamak | Referans | Bekçi (tah.) |
|---|---|---|---|
| 1 | **Mod tablosu (mevcut)** — analitik round-trip, Bessel kökleri, ölçekleme | var (36 bekçi) | mevcut + 4 (karma mod dikliği, sıvı bağlaması sonrası tek-kaynak) |
| 2 | **τ_c özdeşliği** — `L*/(c*Γ²)` ile `V·c*/(A_t·R·T)` bağımsız yollardan bit-özdeş; `R·T = (c*Γ)²` kimliği | §3.1 türetimi | 6 |
| 3 | **Chug nötr eğrisi** — kapalı form `τ/τ_c = 2J·arccos(−2J)/√(1−4J²)`; (a) elle hesap `J=0,2 ⇒ 0,865`; (b) `J → 1/2` tekilliği; (c) sayısal kök bulucunun karakteristik denklemi ile çakışması; (d) **klasik %15-25 bandının modelde nereye düştüğünün ÖLÇÜLMESİ** (eşik testi değil, kayıt) | §3.2 | 10 |
| 4 | **Sıfır-gecikme katı limiti** — bulk mod ölçütü tam olarak mevcut `n ≥ 1` kapısına indirgenmeli (`solid_rocket_engine.py:2715` ile çapraz) | §3.5 | 5 |
| 5 | **Hibrit LFI literatür vakası** — JPP 2005 makalesinin yayımlanmış test tablosundan 4-6 koşu (AMROC / HPDP / JIRAD / NASA Ames 4L-05, 4NF-04…): `L`, `P_c`, `G_o`, `O/F` girilir, ölçülen frekans makalenin kendi saçılım bandı içinde geri gelmeli | Denk. 15 | 8 |
| 6 | **Katsayı çelişkisi bekçisi** — sabitin `0,2341` olduğu ve ders notu `0,119`'un KULLANILMADIĞI kilitlenir; `basis` metninde çelişkinin adı geçer | §3.4 | 3 |
| 7 | **F-1 çapası (mevcut genişletilir)** — 1T 440-540 Hz bandı; sönüm bütçesi eklendiğinde `R_crit`'in mertebesi literatür bandıyla (1-3) kıyaslanabilir çıkmalı | Oefelein & Yang 1993 | 4 |
| 8 | **Kapı bekçileri** — eksik girdide `NOT_EVALUATED` + `missing_inputs`; hiçbir yolda varsayılan sayı üretilmediği (uydurma-yasağı mutasyonu: sabit enjekte edilirse kırmızı) | ürün felsefesi | 8 |
| 9 | **Tek kaynak bekçisi** — chug eşiklerinin ve 1,8412'nin depoda TEK tanımı; literal arama testi (`test_sabit_tek_kaynak.py` deseni) | §1.1-1, §1.1-2 | 4 |
| 10 | **Uygulanabilirlik matrisi bekçisi** — katıda chug, hibritte L* modu YAPISAL olarak `not_applicable`; veri eksikliğiyle karıştırılmadığı | §2.1 | 4 |

**Toplam hedef: ~56 yeni bekçi** (mevcut 36 akustik bekçisi korunur). Her basamak için en az bir
**mutasyon kanıtı** (md5'li): örn. §3.4 sabitini 0,119'a çevirmek basamak 5+6'yı kırmızıya
düşürmeli; `arccos(−2J)` işaretini bozmak basamak 3'ü; `n ≥ 1` limitini gevşetmek basamak 4'ü.

**Literatür verisinin kamuya açıklığı [ÖLÇÜLDÜ]:** Karabeyoglu 2005 makalesi test tablolarıyla
birlikte Stanford ders materyali sayfasından erişilebilir (bu tur indirildi); F-1 bandı yayımlı;
T-burner tepki fonksiyonu verisi ise dağınık ve büyük kısmı raporlarda — bu yüzden katı tepki
fonksiyonu doğrulaması **band kıyası** düzeyinde kalır, sayısal çapa olarak kullanılmaz.

---

## 6. Aşamalandırma ve dosya düzeni

```
hrma/stability/__init__.py        # sürüm + NOT_MODELLED çekirdeği + EŞİKLERİN TEK KAYNAĞI
hrma/stability/chamber.py         # tau_c, Gamma^2, R*T=(c* Gamma)^2 kimlikleri, bulk mod
hrma/stability/chug.py            # konsantre parametreli çevrim + nötr eğri + büyüme oranı
hrma/stability/damping.py         # lüle admitansı, partikül sönümü, bütçe toplayıcı
hrma/stability/response.py        # n-tau nötr eğrisi, R_crit tersine çevirme, (kapılı) QSHOD
hrma/stability/hybrid_lfi.py      # Karabeyoglu Denk. 15 + oksitleyici kapısı + tanı oranı
tests/stability/                  # basamak başına dosya (merdiven §5)
```

`hrma/analysis/acoustic_modes.py` **YERİNDE KALIR** — taşınmaz. Gerekçe **[ÖLÇÜLDÜ]**: 36 bekçi +
üç motor çağrısı ona bağlı; taşıma, F2'nin kendi riskine bedava kusur ekler. `hrma/stability/`
onu ithal eder. Paket biçimi `hrma/flow/` ve `hrma/cfd/` ile aynı desendir.

| Aşama | İçerik | Bekçi | Not |
|---|---|---|---|
| **F2a — çekirdek** | `chamber.py` + `chug.py` + `damping.py` (lüle) + `response.py` (n-τ eğrisi, R_crit); motor bağlaması YOK | ~30 | Doğrulama merdiveni basamak 1-4, 8-9. CFD 1A deseni: çekirdek önce merdiveni tırmanır |
| **F2b — motor bağlamaları** | hibrit: LFI + chug'un gerçek ΔP'siyle; katı: bulk mod + partikül sönümü + eşdeğer kavite; sıvı: `acoustic_modes` çağrısına geçiş (kopya sabitler ölür) + n-τ (τ mevcut atomizasyondan) | ~20 | Basamak 5-7, 10. Sıvı geçişi **bit-fark ölçümüyle**: yeni 1L/1T eski değerlerle aynı mı, değilse fark adıyla beyan |
| **F2c — Analiz Merkezi kiracısı** | Bileşen ağacında "Kamara akustiği" satırı canlanır: frekans ekseni üstünde mod haritası, mod başına sönüm bütçesi çubuğu, n-τ nötr eğrisi + motorun τ'su, chug kök yer eğrisi | ~10 + tur denetimi | **Sahte animasyon yasağı**: tüm çizimler gerçek çıktı alanlarından; veri yoksa panel gri + gerekçe. Görsel tur denetimi (koşum/çizim/rozet üçlüsü) eklenir |

**F2c'nin bağlanacağı yer ölçüldü (16 Ağu, dalga B sahada):** `hrma/static/js/analysis_center.js`
bileşen ağacında `chamber_acoustics` bileşeni ve `acoustic_modes` analiz satırı ZATEN var
(`MATRIX`, satır 221-225), `motorTypes: ['hybrid', 'solid']` — yani liste bugünkü bağlama
gerçeğini doğru yansıtıyor (sıvı yok, çünkü sıvı modülü çağırmıyor, §1.1-2). F2c yeni bir çerçeve
kurmaz: aynı satırın kiracısı olur; **F2b'nin sıvı geçişi tamamlanınca o satıra `liquid` eklenir**
ve bu ekleme kod kanıtıyla (sıvının modülü gerçekten çağırdığı) bekçilenir. Kararlılık bütçesi
için ikinci bir analiz satırı önerilir: `chamber_acoustics × combustion_stability`
(planlanan uç: `/api/analysis/combustion-stability`, `thermal-protection` ucunun desenli
ikizi — `mode` + zorunlu alan kapısı + 422/`missing_fields`).

**Sıralama önerisi:** F2a ile CFD dalga B paralel gidebilir (kesişen dosya yok); F2b sıvı ayağı
`liquid_rocket_engine.py`'ye dokunduğu için o dosyaya yazan başka bir partiyle **aynı anda
dispatch edilmez**.

---

## 7. Lean biçimsel ayağı (Berke'nin kalıcı talimatı)

`formal/LeanLab` altına F2'nin kapalı-form iskeleti; sayısal çözücü değil, **testlerin
karşılaştırdığı analitik referanslar** ispatlanır (CFD'deki aynı ilke).

| Aday teorem | İfade | Koruduğu kod |
|---|---|---|
| `HRMA.gammaFunction_pos` | γ>1 için `Γ² = γ(2/(γ+1))^((γ+1)/(γ-1)) ∈ (0,1)` | `chamber.py` τ_c paydası |
| `HRMA.tauC_identity` | `L*/(c*Γ²) = V·c*/(A_t·R·T)` — `R·T = (c*Γ)²` verildiğinde | τ_c'nin iki yolu (basamak 2) |
| `HRMA.tauC_strictMono` | τ_c, L*'ta kesin artan; c*'ta kesin azalan | fiziksel yön bekçisi |
| `HRMA.chug_neutral_requires_J_lt_half` | Nötr çözüm varsa `J < 1/2` | chug kök arayıcısının aralığı |
| `HRMA.chug_neutral_curve` | Nötr koşul ⟺ `τ/τ_c = 2J·arccos(−2J)/√(1−4J²)` | basamak 3'ün referans formülü |
| `HRMA.chug_neutral_strictAnti` | Nötr `τ/τ_c`, J'de kesin azalan (⇒ "ΔP artır" tavsiyesi teoremdir, sezgi değil) | tavsiye metni |
| `HRMA.bulkMode_zeroLag` | Gecikmesiz bulk modda büyüme ⟺ `n ≥ 1` | `solid_rocket_engine.py:2715` kapısı |
| `HRMA.modeSeparability` | `f² = f_T² + f_L²` (ayrışabilir Helmholtz) | mevcut `combined_frequency` |
| `HRMA.routhHurwitz_second_order` | İkinci mertebe polinomun tüm kökleri sol yarı düzlemde ⟺ katsayılar pozitif | endüktanslı chug hükmü |

`formal/registry.json` deseni aynen: her teorem `python_file` + `python_line` + `anchor` ile
kodun somut satırına bağlanır; satır kayarsa `formal/check.py` kırmızı verir.

---

## 8. Berke'ye açık sorular (karar gerektirenler)

1. **Hüküm politikası.** §3.0'daki "yalnız chug ve hibrit LFI'de hüküm, akustikte eşik" ayrımı
   kabul mü? Alternatif: hiçbir yerde hüküm verme, her şey eşik/marj olsun (daha muhafazakâr,
   kullanıcıya daha az yararlı).
2. **`R·T_av` seçimi.** Hibrit LFI'de korelasyonun kalibre sabiti mi (önerim), çözücünün kendi
   `R·T_c`'si mi? Ölçülen fark ~2× ve doğrudan frekansı 2× kaydırıyor. Önerim: sabit + tanı oranı
   yan yana.
3. **Katı tepki fonksiyonu.** QSHOD (A, B) yolu açılsın mı? Açılırsa parametreler nereden —
   (a) yalnız kullanıcı girdisi, (b) yakıt ailesi başına künyeli literatür bandı (bant olarak,
   tek sayı değil), (c) hiç açılmasın, katıda yalnız sönüm + `R_crit` gösterilsin?
4. **Yakıt termal özellikleri.** `propellant_database.py`'deki `specific_heat`/
   `thermal_conductivity` değerleri kullanılsın mı? Künyeleri alan-başına değil, blok-başına
   ('NASA SP-8075', 'Stanford University Research') — bu, HRMA'nın künye standardının altında.
   Seçenekler: (a) künyeli yeni tablo yazılsın, (b) mevcut değerler "zayıf künye" rozetiyle
   kullanılsın, (c) yalnız kullanıcı girdisi.
5. **Besleme hattı.** Chug'a endüktans terimi eklensin mi? Eklenirse sonuç `2,5 m` yerleşim
   varsayımına biner. Seçenekler: (a) sıvı formuna gerçek hat uzunluğu alanı eklensin (küçük UI
   işi), (b) endüktanssız (direnç+kapasitans) kalsın, (c) hat uzunluğu taraması gösterilsin.
6. **F2 kapsamının sınırı.** Girdap dökülmesi (Strouhal çakışma taraması) ve baffle/Helmholtz
   **boyutlandırma yardımcısı** F2'ye girsin mi, yoksa ayrı bir kaleme mi bırakılsın? Girerse
   F2c büyür; girmezse katalogdaki iki "önemli" kalem açık kalır.
7. **Sıralama.** F2a, CFD dalga B ile paralel mi gitsin (dosya kesişimi yok), yoksa CFD bitsin
   sonra mı? Scofield öncesi kalan takvim buna bağlı.
8. **Sıvı geçişinin görünürlüğü.** Sıvı `acoustic_modes`'a geçince yayımlanan 1L/1T sayıları
   değişebilir (aynı formül, farklı geometri kaynağı: mm→m dönüşümü ve kamara boyu tanımı).
   Fark ölçülüp beyan mı edilsin, yoksa geçiş fark ÇIKMAZSA mı yapılsın (bit-aynılık şartı)?

---

## 8.1 KARARLAR (Berke, 16 Ağu 2026 — GPT-5.6 çapraz danışmasıyla; sekiz karar + üç sıkılaştırma)

Berke sekiz öneri paketinin TAMAMINI onayladı (ikinci görüş: GPT-5.6, Karabeyoglu 2005'i
kendisi de okuyup Eq. 15'in RT_av sabitlerinin — GOX/LOX 6,38e5, N₂O 4,47e5 m²/s² —
43 motor testine karşı doğrulanmış korelasyonun PARÇASI olduğunu teyit etti). Üç maddede
sözleşme sıkılaştırması:

1. **EVET + HÜKÜM KAPSAM ETİKETİ (sıkılaştırma):** hüküm rozetinin yanında mekanizma
   kapsamı ZORUNLU — "STABLE — within modeled LFI mechanism" gibi; çıplak STABLE yasak
   (kullanıcı "tüm kararsızlık mekanizmalarına karşı stabil" okur). Bekçiye bağlanacak:
   hüküm alanı kapsam anahtarı olmadan yayımlanamaz.
2. **EVET — korelasyonun kendi kalibre sabiti.** Çıktı üçlüsü: `RT_corr` (kalibre değer),
   `RT_thermo` (çözücü), `ratio` + açık etiket "diagnostic only — not substituted into
   correlation". 2,08× farkın kökeni (ortalama sıcaklık tanımı mı, gaz sabiti mi,
   kompozisyon mu) ileride ayrı araştırma kalemi; F2a'yı BLOKLAMAZ.
3. **EVET (b) + GEÇERLİLİK ZARFI (sıkılaştırma):** "APCP bandı" gibi geniş sınıf YETMEZ —
   her bant şu metadata ile taşınır: formulation class + basınç aralığı + sıcaklık/test
   koşulları + kaynak. Kullanıcının çalışma noktası zarf DIŞINDAYSA bant yine gösterilir
   ama EXTRAPOLATED / LOW CONFIDENCE rozetiyle.
4. **EVET (a) — künyeli yeni tablo.** Ek şart: c_p/k sıcaklığa bağlı olabilir; tek sayı
   taşınacaksa referans sıcaklık veri kaydının PARÇASI.
5. **EVET (a) + duyarlılık kancası:** forma gerçek L (ve D/alan) alanı; kullanıcı girmezse
   ataletsiz model + açık beyan. Çözücü katmanında L-taraması altyapısı kurulur ama
   varsayılan ekrana DÖKÜLMEZ (ileride "L=0,5-5 m'de frekans nereye kayar" mimari
   değişiklik istemesin).
6. **HAYIR — deftere İKİ AYRI epik:** F2.8a "Hydrodynamic excitation screening" (girdap
   dökülmesi/Strouhal), F2.8b "Passive acoustic mitigation" (baffle/Helmholtz
   boyutlandırma). Tek özellik gibi bağlanmaz; 2.8 kuyruğu.
7. **EVET — paralel; ŞART: merkezî tip sözleşmesi önce dondurulur.** `hrma/stability/`
   çekirdek modülünün girdi/çıktı tipleri (thermo/akustik büyüklüklerin adları, birimleri,
   basis alanları) F2a'nın İLK işi olarak modül sözleşmesine yazılır — CFD kulvarıyla aynı
   temel tipleri farklı biçimde icat etme riski böyle kapanır.
8. **EVET — fark beyanı + GÖÇ MANİFESTOSU (sıkılaştırma):** sıvı geçişinden önce eski yerel
   sayılar anlık görüntüye (snapshot) alınır; göç testi her yayımlanan sayı için
   `old_local → new_central → Δabsolute → Δrelative → reason` kaydı üretir. Fark beklenen
   fizik/model farkından geliyorsa yeni merkezî değerler golden olur; BEKLENMEYEN fark
   varsa test KIRMIZI. Politika: "değişiklik serbest" değil, "açıklanmış değişiklik
   serbest".

**Hüküm: F2a uygulaması onaylı, CFD kulvarıyla paralel dalgaya girer.**
