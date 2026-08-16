# v3 CFD Aşama 2 tasarımı — viskoz / türbülanslı lüle içi akışı

**Tarih:** 16 Ağustos 2026 · **Karar sahibi:** Berke (FINAL kapsamı) · **Tasarım turu:** CFD uzmanı
**Bağlam:** Berke'nin bugünkü kararı — FINAL sürümü "Euler + beyan" ile DEĞİL, **tamamen çalışır
viskoz/türbülanslı** lüle CFD'siyle çıkar. Bu belge o kararın sayısal ve doğrulama tasarımıdır.
Aşama 1 (Euler) belgesi `docs/mimari/cfd-tasarimi.md` BAĞLAYICI kalır; buradaki hiçbir karar onun
şema kararlarını geçersiz kılmaz, üstüne bindirir.

**İşaretleme sözleşmesi (F2 tasarım belgesiyle aynı disiplin):**
- **[ÖLÇÜLDÜ]** — bu turda depo gerçeğinden okundu (dosya + satır) ya da depodaki bağıntılar/çözücü
  fiilen koşturularak hesaplandı (girdi ve yol cümlede belirtilir). Doğrulanabilir.
- **[ÖNERİ]** — tasarım kararı, tahmin ya da gelecekte ölçülecek hedef. Kanıt DEĞİLDİR.

---

## 1. Karar özeti (önce sonuç)

**[ÖNERİ] Seçilen mimari: (a) tam eksenel simetrik RANS — sıkıştırılabilir Navier-Stokes +
Spalart-Allmaras (negatif-SA varyantı), duvar-çözümlü (y⁺ ≲ 1), zorunlu ön koşulu j-yönü
satır-örtük (blok üç-köşegen) gevşetme katmanı olan bir çözücü.** Entegral sınır tabakası (seçenek
b) ürünün viskoz cevabı DEĞİL, (i) doğrulama merdiveninin bağımsız ölçüm aracı ve (ii) yarı-1B
katmanın (`analysis/nozzle_flow_1d.py`) uydurma 1,5 % sürtünme sabitini kaldıran hızlı katman
olarak kurulur. İkisi aynı merdivende doğrulanır, aralarındaki fark ölçülüp BEYAN edilir.

**[ÖNERİ] Gerekçenin bir cümlesi:** Berke'nin "tamamen çalışır" tanımının üç bileşeni (duvar ısı
akısı, sürtünme kaybı, ayrılmanın viskoz temeli) yalnızca (b) ile karşılanmaz — çünkü (b) ısı
akısını yine korelasyon sınıfı bir kapanışa bağlar ve ayrılmayı τ_w = 0 noktasından ÖLÇEMEZ;
(a) üçünü de doğrudan çözer, ve bu turda ölçülen tek gerçek engeli (duvar-çözümlü ızgarada
yerel-Δt çöküşü, §4.1) bilinen ve test edilebilir bir katmanla (satır-örtük gevşetme, §5.6)
kaldırılabilir.

**[ÖNERİ] Ama evreli:** (a) tek partide inmez. Aşağıdaki V0→V5 evrelemesi, her evrenin kendi
analitik doğrulama basamağıyla bittiği ve **V1 sonunda ÖLÇÜLEN bir performans kapısı** olan bir
sıradır. Kapı geçilmezse çare belgede yazılıdır (§9.3) — sürpriz bırakılmaz.

---

## 2. Zemin: bugün depoda ne var, ne yok (ölçüm)

### 2.1 Euler çekirdeği — sağlam ve dokunulmayacak

- **[ÖLÇÜLDÜ]** `hrma/cfd/` beş çekirdek modül taşıyor: `riemann.py` (HLLC), `euler_core.py`
  (1B/2B FVM, MUSCL+minmod, SSP-RK2), `grid_axisym.py` (H-tipi ızgara, tam dönel metrikler),
  `steady.py` (yerel-Δt sürücü), `kernels.py` (isteğe bağlı numba). Ek olarak `separation.py`
  (duvar basıncı → Summerfield köprüsü).
- **[ÖLÇÜLDÜ]** `tests/cfd` **69 bekçi** topluyor (`pytest --collect-only`, 16 Ağu 2026).
- **[ÖLÇÜLDÜ]** Ölçülen maliyet (M4 Max, numba 0.61.0 kurulu): `residual_axisym` tek çağrı
  120×24'te **0,405 ms**, 256×64'te **1,804 ms**; `local_dt_axisym` sırasıyla 0,066 / 0,292 ms.
  SSP-RK2 iterasyonu iki kalıntı + bir Δt çağrısıdır → 256×64'te ≈ 3,9 ms/iter, ki
  `tests/cfd/test_performans.py` dosya başındaki 4,09 ms/iter ölçümüyle tutarlı.
- **[ÖLÇÜLDÜ]** Maliyet dağılımı (cProfile, 200 kalıntı çağrısı, 256×64): `minmod` **%26**,
  `limited_slopes` kümülatif **%32**, `directional_hllc` (numba) kümülatif **%23**. Yani sıcak
  nokta Riemann çözücüsü DEĞİL, MUSCL yeniden kurulumudur — viskoz terimlerin bu tabana ne
  eklediği §9'da bu ölçüme dayandırılır.
- **[ÖLÇÜLDÜ]** `AxisymGrid` `face_i_planar` / `face_j_planar` / `area_planar` alanlarını ZATEN
  yayımlıyor; `grep` ile bakıldığında `face_*_planar` çözücüde HİÇ kullanılmıyor, yalnız
  `tests/cfd/test_grid.py:74-76` kapanış özdeşliği bekçisinde kullanılıyor. Viskoz katmanın
  ihtiyaç duyduğu düzlemsel gradyan operatörünün gereksinimi tam olarak budur (§5.2) — yeni
  geometri üretilmeyecek.
- **[ÖLÇÜLDÜ]** Eksen sağlığı: `grid.r_centers` minimumu nj = 192'de 6,511e-5 m, nj = 12'de
  1,042e-3 m — **her zaman kesin pozitif**. Eksenel simetrik viskoz gerilmenin çember (hoop)
  bileşeninde görünen u_r/r terimi bu yüzden hücre merkezinde tanımlıdır; 0/0 muamelesi
  gerekmez (§5.3).

### 2.2 Yarı-1B ve ısı transferi tarafı — viskozitenin bugünkü vekilleri

- **[ÖLÇÜLDÜ]** Sürtünme kaybı bugün bir SABİTTİR: `hrma/analysis/nozzle_flow_1d.py:240`,
  `friction_loss_fraction: float = 0.015`; modül docstring'i (satır 51-55) bunu açıkça
  "*this is NOT a boundary-layer solution, only a bookkeeping estimate*" diye beyan ediyor.
  Kullanıcı 0-0,2 bandında ayarlayabiliyor, ama değer fizikten GELMİYOR.
- **[ÖLÇÜLDÜ]** Gaz tarafı ısı akısı Bartz korelasyonuna bağlı:
  `hrma/analysis/heat_transfer_analysis.py:542` `_bartz_coefficient` (Sutton & Biblarz 9. baskı
  Denk. 8-22, SI biçim; σ sınır tabakası özellik düzeltmesiyle), `analysis/nozzle_flow_1d.py`
  onu İTHAL ediyor (kopya yok, satır 811).
- **[ÖLÇÜLDÜ]** Taşınım özelliklerinin TEK kaynağı `_get_gas_properties`
  (`heat_transfer_analysis.py:155-241`): Pr = 4γ/(9γ−5) (donmuş, Sutton Denk. 8-23),
  cp = γR/(γ−1), μ = 1,184e-7·MW^0,5·T^0,6 (Bartz 1957 korelasyonu, satır 207),
  k = cp·μ/Pr. **Depoda Sutherland yasası HİÇ YOK** (`grep -ri sutherland` boş döndü) — yani
  viskoz CFD kendi viskozite yasasını UYDURMAYACAK, bu tek kaynağı kullanacak (§5.8).
- **[ÖLÇÜLDÜ]** Termal FEA köprüsünün sözleşmesi `hrma/fea/bridge.py:746`:
  `axial_profile` = (`x_mm`, `h_g` [W/m²K], `T_recovery` [K]), üçü eş uzunlukta, x kesin artan;
  eksik olursa **red** (`BRIDGE_STATUS_NOT_MODELLED`, "boğaz skalerinden profil uydurulmaz").
  Bu, viskoz CFD çıktısının ürüne bağlanacağı hazır ve dürüstlük kapılı arayüzdür (§8.1).
- **[ÖLÇÜLDÜ]** Ayrılma tarafı: `hrma/flow/separation.py` üç ölçüt taşıyor (Summerfield,
  Schmucker, Kalt-Badal) ve `SEPARATION_NOT_MODELLED['boundary_layer_state']` aynen şunu beyan
  ediyor: "*Sınır tabaka çözülmez: laminer/türbülanslı durum, kalınlık ve ayrılma sonrası duvar
  basıncı dağılımı modellenmedi.*" `hrma/cfd/separation.py` (parti 25) duvar basıncını 2B Euler
  çözümünden ölçüyor ama ölçüt hâlâ ampirik.
- **[ÖLÇÜLDÜ]** `hrma/cfd/__init__.py:32` `CFD_NOT_MODELLED['viscosity_turbulence']` zaten bu
  aşamanın adresini veriyor: "*cidar kayma gerilmesi, ısı taşınımı ve şok-sınır tabaka etkileşimi
  modellenmedi (Aşama 2: RANS-SA ya da entegral BL kararı)*". Bu belge o kararı verir.

### 2.3 Geometri gerçeği

- **[ÖLÇÜLDÜ]** Gerçek kontur örnekleyicisi (`sample_nozzle_inner_contour`, temsilî motor:
  D_ch = 100 mm, d_t = 20 mm, d_e = 80 mm, θ_n = 30°, konik) **yakınsak bölgede duvar açısını
  42,14°'ye, ıraksakta 15,00°'ye** çıkarıyor; boğaz istasyonunda açı sıfırdan geçiyor. Bu sayı
  ızgara çarpıklığı (skew) kararının girdisidir (§5.7).
- **[ÖLÇÜLDÜ]** `tests/cfd/conftest.py` analitik vakası daha yumuşaktır (kosinüs geçiş,
  |açı| ≲ 11°), yani doğrulama vakası gerçek geometrinin çarpıklık zorluğunu TAŞIMAZ — bu
  belgede ayrı bir bekçi olarak ele alınır (§7 basamak 9).

---

## 3. "Tamamen çalışır" ne demek: üç ürün eksiği

**[ÖLÇÜLDÜ] Bugün ürünün viskozite yüzünden veremediği üç şey:**

| # | Eksik | Bugünkü vekil | Vekilin beyanı |
|---|---|---|---|
| 1 | Duvar ısı akısı q_w(z) | Bartz korelasyonu (h_g) | Korelasyon; boğaz eğriliği ve hızlanma etkileri σ düzeltmesiyle vekâleten |
| 2 | Sürtünme kaynaklı itki kaybı | Sabit %1,5 | "NOT a boundary-layer solution, only a bookkeeping estimate" |
| 3 | Ayrılma başlangıcı | Üç ampirik ölçüt (uyuşmuyorlar) | "Sınır tabaka çözülmez" |

**[ÖNERİ] Viskoz çözücünün karşılığı:** (1) q_w = k_eff·∂T/∂n duvarda doğrudan ölçülür ve
Bartz'la ÇAPRAZLANIR (biri diğerini geçersiz kılmaz; ikisi bir band olur). (2) İtki kaybı
∮τ_w·ê_z dA integralinden gelir — sabit kaybolur. (3) Ayrılma başlangıcı τ_w işaret
değiştirmesinden ÖLÇÜLÜR ve üç ampirik ölçütün yanına dördüncü, hesaplanmış üye olarak konur;
uyuşmazlık alanın gerçek belirsizliğidir ve depo kültürü zaten bunu yan yana raporlamaktır.

---

## 4. Mimari eksen: (a) RANS / (b) entegral BL / (c) evreli — ölçülen kısıtlarla

### 4.1 ÖLÇÜM: duvar-çözümlü ızgaranın yerel-Δt bedeli

Bu, tasarımın en belirleyici ölçümüdür. Mevcut sürücü **açık** SSP-RK2 + yerel Δt kullanıyor;
Δt_c = CFL·V_c / Σ_yüzey (|u·n̂| + a)|S| (`euler_core.local_dt_axisym`). Radyal hücre inceldikçe
Δt küçülür. Ne kadar?

**[ÖLÇÜLDÜ]** (`conftest` lülesi, ni = 120, tam süpersonik vaka, CFL = 0,5; ızgara ve Δt doğrudan
ürün fonksiyonlarından):

| nj | hücre | min Δt [s] | maks Δt [s] | Δr (boğazda) |
|---|---|---|---|---|
| 12 | 1 440 | 1,5535e-7 | 2,7182e-7 | 2,08 mm |
| 24 | 2 880 | 1,1882e-7 | 1,9738e-7 | 1,04 mm |
| 48 | 5 760 | 7,9303e-8 | 1,2753e-7 | 0,52 mm |
| 96 | 11 520 | 4,7255e-8 | 7,4674e-8 | 0,26 mm |
| 192 | 23 040 | 2,5577e-8 | 4,3449e-8 | 0,13 mm |

**[ÖLÇÜLDÜ]** nj 96 → 192 arasında Δt oranı **1,847** — yani asimptotik olarak Δt ∝ Δy (radyal
yön Δt'yi ele geçirmiş). Aynı vakada gerçek yakınsama (tol_res = 1e-8, `solve_steady_axisym`):

| nj | iterasyon | süre [s] | ms/iter | ṁ_giriş [kg/s] |
|---|---|---|---|---|
| 12 | 8 376 | 6,2 | 0,75 | 4,810669 |
| 24 | 7 474 | 7,2 | 0,96 | 4,811103 |
| 48 | 9 798 | 14,6 | 1,49 | 4,811165 |
| 96 | 16 801 | 41,4 | 2,47 | 4,811576 |

**[ÖLÇÜLDÜ] Kritik gözlem:** nj 48 → 96 geçişinde iterasyon oranı **1,715**, aynı geçişte
min Δt oranı **1,678**. İkisi neredeyse birebir — yani radyal inceltme rejime girdiğinde
**iterasyon sayısı 1/Δt_min ile orantılı** büyüyor. (nj 12 → 24 arasında iterasyon DÜŞÜYOR:
orada Δt'yi hâlâ eksenel yön belirliyor, radyal inceltme bedava.)

**[ÖLÇÜLDÜ] Duvar-çözümlü ızgara ne ister?** Depo korelasyonlarıyla (μ = 1,184e-7·MW^0,5·T^0,6,
Pr = 4γ/(9γ−5), düz levha c_f = 0,0592·Re_x^−0,2, duvar özellikleri T_w = 0,5·T₀'da) hesaplanan
y⁺ = 1 mesafesi:

| Vaka | Boğazda Re_D | y(y⁺=1) [µm] | y⁺=1 için nj (büyüme 1,20) | y⁺=30 için nj |
|---|---|---|---|---|
| `conftest` lülesi (γ=1,2, 40 bar, 3200 K, r_t=25 mm) | 1,77e6 | 0,358 | ≈ 49 | ≈ 30 |
| Küçük motor (d_t = 20 mm, 20 bar) | 4,16e5 | 0,585 | ≈ 41 | ≈ 22 |
| Büyük motor (d_t = 100 mm, 100 bar) | 7,94e6 | 0,172 | ≈ 56 | ≈ 38 |

**Hücre sayısı sorun değil** (nj ≈ 48-64 yeter). Sorun Δt'dir:

**[ÖNERİ] Dışkestirim (mertebe iddiası, tam sayı değil):** y⁺ = 1 ilk hücre kalınlığı ≈ 0,72 µm,
nj = 96'nın düzgün hücresinden **≈ 363×** ince. Ölçülen Δt ∝ Δy_min ve iterasyon ∝ 1/Δt_min
orantılarından: Δt_min ≈ 1,3e-10 s, iterasyon ≈ 6e6, süre ≈ **4 saat mertebesi** (aynı hücre
sayısıyla, viskoz terimlerin maliyeti HARİÇ). **Açık, yerel-Δt'li kararlı-hâl sürücüsüyle
duvar-çözümlü RANS bu üründe koşmaz.** Bu, tasarımın kapı taşıdır.

### 4.2 Kapının anahtarı: j-yönü satır-örtük gevşetme

**[ÖNERİ]** Yüksek en-boy oranlı (AR ≫ 1) ızgarada standart çare, Δt'yi kısıtlayan yönü **örtük**
almaktır. Burada o yön j (radyal/duvar-normal) yönüdür: her i-kolonu için nj bloktan oluşan
**blok üç-köşegen** sistem çözülür (Thomas/blok-eleme). Sonuç: Δt artık yalnız eksenel yönle
sınırlıdır, yani ölçülen 1,5e-7 s sınıfına geri döner ve iterasyon sayısı Euler koşularının
mertebesine (≈ 2e4) iner.

**[ÖNERİ] Neden bu katman "hüküm-nötr" (ve bu neden çok önemli):** kararlı-hâl çözümü
`kalıntı = 0` denklemiyle tanımlıdır. Örtük katman yalnız o köke GİDİŞ YOLUNU değiştirir; Jacobi
matrisi yaklaşık olsa bile (ki olacak — spektral yarıçap tabanlı yaklaşık akı Jacobi'si + tam
viskoz katkı önerilir) **yakınsanan cevap değişmez**. Bu, doğrulama açısından altın değerindedir:
hızlandırma katmanı fiziksel iddiaları kirletmez. Bekçisi doğrudan yazılabilir — küçük bir vakada
açık yolla örtük yolun yakınsadığı alanlar verilen toleransta AYNI çıkmalıdır (§7 basamak 6).

### 4.3 Duvar fonksiyonu neden REDDEDİLDİ

**[ÖNERİ]** y⁺ ≈ 30-100 hedefiyle duvar fonksiyonu kullanmak ızgarayı ucuzlatır (yukarıdaki
tabloda nj ≈ 22-38, Δt cezası ≈ 12× yerine 363×). Reddediliyor, çünkü:
1. Ürünün BİRİNCİ çıktısı **duvar ısı akısı**dır ve duvar fonksiyonları tam da lülenin fizik
   koşullarında (kuvvetli elverişli basınç gradyanı + kuvvetli duvar soğutması) en zayıf oldukları
   yerdedir; log-yasası varsayımı hızlanan ve şiddetle soğutulan tabakada geçerliliğini yitirir.
2. **[ÖLÇÜLDÜ]** Back-Massier-Gier raporunun kendi özeti bu rejimi işaret ediyor: "*the reduction
   in the heat-transfer coefficient below that typical of a turbulent boundary layer*" (NTRS
   19650026963 tam metni, §7'de künyesi) — yani lüle sınır tabakası standart türbülanslı davranıştan
   ÖLÇÜLEBİLİR biçimde sapıyor. Duvar fonksiyonu bu sapmayı tanım gereği göremez.
3. Duvar fonksiyonlu bir sonucun "viskoz CFD yaptık" iddiası, HRMA'nın beyan kültüründe savunulması
   zor bir iddia olurdu.

**[ÖNERİ] Ama y⁺ gizlenmez:** koşum başına ulaşılan y⁺ dağılımı ÖLÇÜLÜR ve **y⁺ rozeti** olarak
yayımlanır (FEA'nın mesh kalite haritası deseni). Hedef sağlanmadıysa hüküm buna göre beyanlanır.

### 4.4 (b) entegral BL neden ürünün cevabı değil — ve neden yine de yazılacak

**[ÖNERİ] Neden tek başına yetmiyor:** entegral yöntem δ*, θ, H taşır ve ısı akısını Reynolds
analojisiyle (St = c_f/2·Pr^(−2/3)) kapatır; yani q_w yine bir KAPANIŞ varsayımına bağlıdır ve
Bartz'a göre kazanımı "başka bir korelasyon" düzeyindedir. Ayrıca ayrılmayı τ_w = 0'dan değil,
şekil faktörü eşiğinden (H ≈ 2,2-2,4) hükmeder — yine ampirik.

**[ÖNERİ] Neden yine de yazılacak (üç sağlam sebep):**
1. **Bağımsız ölçüm aracı:** RANS'ın c_f(z), θ(z), q_w(z) çıktıları entegral yöntemin aynı
   büyüklükleriyle karşılaştırılır. İkisi bağımsız kapanışlardır; uyum, RANS gerçeklemesinin
   sağlığına dair güçlü bir kanıttır (ve uyumsuzluk erken alarmdır).
2. **Ürün eksiği #2'yi hemen kapatır:** yarı-1B katmandaki uydurma %1,5 sabiti, RANS'ı beklemeden
   fizikten gelen bir sayıyla değişebilir (maliyeti milisaniye).
3. **Hız katmanı:** Analiz Merkezi'nde "hızlı tarama" için saniyenin altında viskoz tahmin
   verilebilir; RANS "yüksek doğruluk" sekmesidir. Fidelity katmanı dili depoda ZATEN var
   (**[ÖLÇÜLDÜ]** `nozzle_flow_1d.py` docstring satır 4-9: "Fast Screening / Engineering fidelity
   levels").

### 4.5 KARAR

**[ÖNERİ]** (c) evreli yol seçilir, ama "önce b, sonra belki a" biçiminde DEĞİL:
**hedef (a)'dır, (b) onun doğrulama ve hız kanadıdır, ikisi de FINAL kapsamındadır.** Evreleme
§11'de; V1 sonundaki ölçülen performans kapısı §9.3'te.

---

## 5. Sayısal tasarım

### 5.1 Temel ilke: KOMPOZİSYON, müdahale değil

**[ÖNERİ]** Viskoz katman Euler çekirdeğinin İÇİNE yazılmaz; ayrı bir kalıntı olarak hesaplanıp
EKLENİR:

```
dU/dt = R_Euler(U)  +  R_viskoz(U, ν̃)          (akı ıraksaması flux-split'te doğrusaldır)
```

**[ÖNERİ] Bu seçimin üç somut kazancı:**
1. **Regresyon sözleşmesi tanım gereği sağlanır:** viskoz kapalıyken `residual_axisym` çağrısı
   birebir bugünkü koddur; 69 bekçi bit-yeşil kalır — "umulur ki" değil, yapısal olarak.
2. **[ÖLÇÜLDÜ] Duvar akısı formülü değişmiyor:** `euler_core.residual_axisym` kayma duvarında
   akıyı analitik olarak `[0, p*·n̂·|S|, 0]` kuruyor (satır 443-456). Kaymaz (no-slip) duvarda da
   u·n̂ = 0 olduğundan taşınım akısı yine sıfır kütle/enerji + salt basınçtır. Yani no-slip'e
   geçmek çekirdeğin duvar akısını GEÇERSİZ KILMAZ; viskoz katman oraya yalnızca
   `[0, τ_wz·|S|, τ_wr·|S|, −q_w·|S|]` ekler (duvarda u = 0 olduğu için τ·u iş terimi düşer).
3. Sıcak yol ayrık kalır: numba çekirdeği ayrı yazılır, mevcut HLLC çekirdeğinin bit-özdeşlik
   sözleşmesi bozulmaz.

**[ÖNERİ] Tek istisna — MUSCL hayalet durumu:** duvara komşu hücrede eğim, kayma aynasıyla
(`_mirror_wall`) hesaplanıyor; viskoz koşuda tanjant hız duvarda sıfıra gittiğinden bu ayna
taşınım yeniden kurulumunu duvara yakın bozar. Çare: `euler_core`'a `wall_bc='slip'|'noslip'`
parametresi (varsayılan `'slip'` → dal tıpatıp bugünkü kod → bit-özdeşlik korunur). Etkisi
VARSAYILMAZ, ölçülür: aynı viskoz koşu iki ayna seçimiyle koşulup q_w ve c_f farkı raporlanır.

### 5.2 Gradyan operatörü — mevcut geometriyle, yeni metrik üretmeden

**[ÖNERİ]** Hücre gradyanları düzlemsel Green-Gauss ile:

```
∇φ|_c  =  (1 / A_düzlem,c) · Σ_yüz  φ_yüz · S_düzlem,yüz
```

**[ÖLÇÜLDÜ] Neden düzlemsel:** eksenel simetrik gerilme tensörünün (z, r) bileşenleri düzlemsel
türevlerdir; çember bileşeni ayrı ve cebirseldir (§5.3). Gerekli iki büyüklük — `face_i_planar`,
`face_j_planar` — `AxisymGrid`'de zaten var ve çözücüde kullanılmıyor.

**[ÖLÇÜLDÜ] Serbest akım korunumu bedava geliyor:** `tests/cfd/test_grid.py:74-76` kapalı hücre
çevresinde Σ S_düzlem ≈ 0 özdeşliğini zaten bekçiliyor. Sabit bir alan için Green-Gauss gradyanı
φ·ΣS/A = 0 verir — yani **viskoz operatörün düzgün akışta tam olarak sıfır olması, ÖNCEDEN
kanıtlanmış geometrik özdeşliğin doğrudan sonucudur.** Bekçi bunun sayısal yankısıdır (§7
basamak 2).

**[ÖNERİ] Yüz gradyanı:** komşu hücre gradyanlarının ortalaması + kenar-yönü düzeltmesi
(Blazek, *CFD: Principles and Applications*, §5.3.2 "corrected average"):

```
∇φ|_yüz = avg(∇φ_L, ∇φ_R) − [ avg(∇φ)·t̂_LR − (φ_R − φ_L)/|LR| ] · t̂_LR
```

Düzeltme terimi olmadan yüksek en-boy oranlı ızgarada çift-tek (odd-even) ayrışması görülür; bu
bir "iyileştirme" değil, gereklilik. **[ÖNERİ]** Alternatif "ince tabaka (thin-layer)" yaklaşımı
(eksenel viskoz türevleri atmak) uygulanmayacak ama BEKÇİ olarak hesaplanacak: iki formun farkı
ölçülüp beyan edilir (ihmal edilenin büyüklüğünü varsaymak yerine bilmek).

### 5.3 Viskoz akı + eksenel simetrik çember (hoop) terimi — r → 0'da tekillik yok

**[ÖNERİ]** Stokes hipotezli Newton gerilmesi (λ = −2/3 μ_eff):

```
τ_zz = 2μ ∂u_z/∂z − (2/3)μ Θ ,   τ_rr = 2μ ∂u_r/∂r − (2/3)μ Θ
τ_zr = μ (∂u_z/∂r + ∂u_r/∂z) ,   τ_θθ = 2μ (u_r/r) − (2/3)μ Θ
Θ = ∂u_z/∂z + ∂u_r/∂r + u_r/r          (eksenel simetrik ıraksama)
q  = −k_eff ∇T ,  μ_eff = μ + μ_t ,  k_eff = cp(μ/Pr + μ_t/Pr_t)
```

**[ÖNERİ] Eksenel simetrik kaynak terimi — mevcut satırın tam kardeşi.** `euler_core` bugün
r-momentumuna basınç kaynağını şöyle ekliyor (**[ÖLÇÜLDÜ]** satır 460):

```python
net[..., 2] += w[..., 3] * _TWO_PI * grid.area_planar        # + p · 2π · A_düzlem
```

Viskoz karşılığı tam olarak aynı biçimdedir:

```python
net[..., 2] -= tau_theta_theta * _TWO_PI * grid.area_planar  # − τ_θθ · 2π · A_düzlem
```

çünkü dönel hacim üstündeki kaynak integrali ∫(p − τ_θθ)/r · dV = 2π∫(p − τ_θθ) dA_düzlem'dir;
1/r hacim elemanının r'siyle **tam olarak** sadeleşir. Geriye kalan tek "tehlikeli" ifade
τ_θθ içindeki u_r/r'dir ve o hücre merkezinde değerlendirilir — **[ÖLÇÜLDÜ]** r_center her zaman
pozitif (min 6,5e-5 m). Seri açılım, epsilon, kırpma YOK: grid_axisym'in "geometrik gerçek"
felsefesi korunur.

**[ÖNERİ] Bekçi (ucuz ve keskin):** Stokes gerilmesinin izi sıfırdır —
tr(τ) = τ_zz + τ_rr + τ_θθ = 2μΘ − 3·(2/3)μΘ = 0. Bu, "τ_θθ'yi unutmak" ya da ıraksamaya u_r/r
terimini katmamak gibi klasik hataların İKİSİNİ birden yakalar ve bir satırlık testtir. Aynı
özdeşlik Lean adayıdır (§12).

### 5.4 Duvar sınır koşulları

**[ÖNERİ] Hız:** no-slip, hayalet hücrede tam yansıma (`u_hayalet = −u_iç`, iki bileşen birden).
**[ÖNERİ] Isıl:** iki seçenek, **uydurma varsayılan YOK** — çağıran seçer ve beyan edilir:
- `wall_thermal='isothermal'` + T_w [K] (kaynağı beyanlı: termal FEA / regen çözücü / kullanıcı),
- `wall_thermal='adiabatic'` (∂T/∂n = 0) — kurtarma toplam sıcaklığını ölçmek için de kullanılır.

T_w verilmeden izotermal istenirse **red** (`ValueError`) — köprü deseninin aynısı.

**[ÖNERİ] q_w duyarlılığı ölçülür, varsayılmaz:** h_g'nin T_w'ye zayıf bağımlılığı iddia edilecekse
KANITLANMALI. İki koşu (T_w = 0,3·T₀ ve 0,6·T₀) ile h_g bandı ÖLÇÜLÜR ve çıktıda
`h_g_wall_temp_sensitivity` olarak yayımlanır. Bu, termal FEA köprüsünün (h_g, T_rec)
doğrusallaştırmasının geçerlilik beyanıdır.

### 5.5 Türbülans modeli: negatif-SA (SA-neg)

**[ÖNERİ] Seçim: Spalart-Allmaras, negatif-ν̃ varyantıyla.** Gerekçe, SST k-ω ile karşılaştırmalı:

| Ölçüt | SA (neg) | SST k-ω |
|---|---|---|
| Denklem sayısı | 1 | 2 |
| Duvar sınır koşulu | ν̃_w = 0 — ızgaradan bağımsız, sağlam | ω_w = 60ν/(β₁d²) — ilk hücre boyuna duyarlı |
| Kaynak sertliği | Tek yok-etme terimi; nokta-örtük yeterli | İki denklem + karışım fonksiyonları, daha sert |
| Duvara bağlı hızlanan akış | Rejimin klasik doğrulama alanı | Aynı, ek olarak ters gradyanda daha iyi |
| Sağlamlık (negatif değer) | SA-neg ν̃ < 0'da bile iyi tanımlı | k, ω pozitiflik kelepçeleri gerekir |
| Gerçekleme riski | Düşük | Orta-yüksek |

**[ÖNERİ]** İlk model SA-neg'dir; SST k-ω **2.8+ için isteğe bağlı ikinci model** olarak aynı
arayüzün arkasına konabilir ve o zaman ürün tek sayı yerine **model bandı** yayımlayabilir (üç
ayrılma ölçütünü yan yana raporlama kültürünün türbülans karşılığı). FINAL için tek model yeter;
"iki model" Berke'ye açık soru olarak §13'te.

**[ÖNERİ] Taşınım denklemi** (sıkıştırılabilir, korunumlu, ρν̃ değişkeniyle) standart biçimde;
`f_t2` trip terimi kullanılmaz (SA-noft2), tam türbülanslı kabul edilir. Ayrık tasarım:
- Taşınım: birinci mertebe yukarı-akış (upwind) başlangıçta, ikinci mertebe MUSCL sonra
  (mertebe farkı ÖLÇÜLÜR — ν̃'de ikinci mertebenin akı üstündeki etkisi rapor edilir);
- Difüzyon: (1/σ)∇·((μ + ρν̃)∇ν̃) + (c_b2/σ)ρ|∇ν̃|² — gradyan operatörü §5.2 ile ortak;
- Kaynak: üretim açık, **yok etme nokta-örtük** (Jacobi'nin negatif kısmı köşegene) — duvara
  komşu hücrede d ≈ 0,4 µm iken ν̃/d² terimi çok serttir, açık alınamaz;
- Ayrık çözüm: ortalama akış 4×4 blok üç-köşegen; ν̃ **ayrık (segregated)** skaler üç-köşegen.
  Segregasyon yakınsama yolunu etkiler, kökü değil (§4.2 argümanı).

**[ÖNERİ] Duvar mesafesi d:** kontur polilinesine **tam** en yakın nokta mesafesi (nokta-parça
geometrisi). Uyarı: yakınsak bölgede duvar 42° eğimli olduğundan `d = r_duvar(z) − r` YANLIŞTIR
(kosinüs kadar sapar). Bekçi: konik duvara analitik mesafeyle karşılaştırma (kapalı form var).

### 5.6 Zaman ilerletme: yerel Δt + j-satır örtük gevşetme

**[ÖNERİ] Yerel Δt** viskoz spektral yarıçapla genişletilir:

```
Δt_c = CFL · V_c / [ Σ (|u·n̂| + a)|S|  +  C_visc · Σ (max(4/3ρ, γ/ρ) · μ_eff/Pr_eff) · |S|²/V ]
```

(Blazek §6.1.4 biçimi.) **[ÖNERİ]** C_visc **ölçümle** sabitlenir (Blazek'te ~4 kullanılır);
ölçmeden yazılmaz.

**[ÖNERİ] j-yönü blok üç-köşegen gevşetme (tasarımın kilit taşı):** her i-kolonu için
(I/Δt + ∂R/∂U)ΔU = R sisteminin j-yönü üç-köşegen parçası çözülür. Jacobi:
- taşınım kısmı: spektral yarıçap tabanlı yaklaşık (basit, sağlam);
- viskoz kısmı: **tam** (yüksek AR'de baskın terim odur, yaklaşıklık burada pahalıya patlar).

**[ÖNERİ] Neden bu, doğruluk iddialarını kirletmez:** §4.2. Bekçisi: küçük, açık yolun
karşılayabildiği bir vakada (örn. laminer boru, orta AR) açık ve örtük yollar aynı kalıntı
seviyesine yakınsatılır ve alanlar sıkı toleransta eşitlenir. Mutasyon: Jacobi'ye kasıtlı çarpan
koymak koşuyu YAVAŞLATMALI ama cevabı DEĞİŞTİRMEMELİ — bu, "hüküm-nötrlük" iddiasının canlı kanıtı
olur.

**[ÖNERİ] Blok-Thomas'ın kendi bekçisi cebirseldir:** rastgele blok üç-köşegen sistem kurulur,
çözücü `np.linalg.solve` ile karşılaştırılır (makine hassasiyeti). Bu bekçi fizikten bağımsızdır
ve asla "kusuru koruyan" bir teste dönüşemez.

**[ÖNERİ] Başlangıç durumu — bedava hızlandırma:** viskoz koşu, izantropik tahminden değil
**yakınsamış Euler alanından** başlatılır (dış akış zaten doğrudur; yalnız sınır tabakasının
gelişmesi gerekir). Mevcut `_isentropic_initial_state` beyanı ("yalnız BAŞLANGIÇ tahminidir")
bu deseni zaten meşrulaştırıyor. Kazanç ÖLÇÜLECEK, varsayılmayacak.

### 5.7 Izgara: duvar kümeleme, y⁺ rozeti, çarpıklık

**[ÖNERİ] Kümeleme:** `build_grid_from_wall`'daki `eta = np.linspace(...)` (yani düzgün radyal
dağılım) **varsayılan olarak korunur** — Euler yolunun bit-özdeşliği için. Yanına isteğe bağlı
gerdirme (tanh/Vinokur ya da geometrik) eklenir; parametre **oran değil, birinci hücre kalınlığı**
(fiziksel büyüklük) olur, çünkü hedef y⁺'tır.

**[ÖNERİ] y⁺ döngüsü dürüst:** ilk hücre kalınlığı bir ÖN TAHMİNDEN (§4.1 tablosundaki korelasyon
zinciri) seçilir; koşum sonrası **gerçekleşen y⁺ ÖLÇÜLÜR** ve yayımlanır. Hedeften sapma varsa iki
seçenek beyanla sunulur: (i) sonucu y⁺ rozetiyle birlikte ver, (ii) bir kez yeniden ızgaralayıp
koş (`regrid_count` beyanlı). Sessiz düzeltme yok.

**[ÖLÇÜLDÜ] Çarpıklık gerçeği:** H-tipi ızgarada j çizgileri radyaldir, duvar normali değil.
Gerçek konturda yakınsak duvar açısı **42,14°**'ye çıkıyor → o bölgede hücre duvara göre 42°
çarpık ve en-boy oranı ~10³ olacak; gradyan doğruluğu düşer. Buna karşılık **boğazda duvar açısı
sıfırdan geçer** (dr/dz = 0) — yani q_w'nin tepe yaptığı yerde çarpıklık YOKTUR.

**[ÖNERİ] Karar: V1'de H-ızgara + radyal kümeleme; çarpıklık ÖLÇÜLÜP yayımlanır** (koşum başına
maksimum duvar çarpıklık açısı + o bölgedeki en-boy oranı). Duvar-normal ötelemeli tabaka (O-tipi
yaka) ancak Back karşılaştırmasındaki hata çarpıklıkla ilişkilendirilirse V1b olarak açılır.

**[ÖLÇÜLDÜ] Bu ertelemenin ders temeli depoda var:** 2.6.27 parti 24, `mesh_axisym` dış yüzey
kuruluşunda normal ötelemenin **boğaz vadisinde eğrilik yarıçapını çökerttiğini** ölçtü ve
yuvarlanan-top morfolojik kapamasıyla düzeltti (commit `622f25c`). Lüle iç yüzeyinde normal
öteleme aynı tuzağı taşır (iç bükey boğaz yayında normaller Rn ≈ 0,382·r_t mesafesinde kesişir).
V1b açılırsa bu ders (eğrilik yarıçapı tavanı + kapama) tasarıma ÖNDEN girer.

### 5.8 Gaz taşınım özellikleri: tek kaynak, yeni sabit yok

**[ÖNERİ]** `hrma/cfd/gas_transport.py` yalnız bir SARMALAYICI olur:
- Çağıran Cantera/CEA'dan μ_ref, cp, Pr verdiyse → **μ(T) = μ_ref·(T/T_ref)^0,6**
  (çağıranın değeri T_ref'te korunur, sıcaklık değişimi depodaki üs yasasıyla),
- vermediyse → doğrudan `_get_gas_properties` zinciri (μ = 1,184e-7·MW^0,5·T^0,6),
- her iki durumda k_eff = cp(μ/Pr + μ_t/Pr_t), Pr = 4γ/(9γ−5) (donmuş, depo tanımı).

**[ÖLÇÜLDÜ]** Bu, parametre tutarlılığı kuralının gereğidir: viskozite bağıntısı depoda tek yerde
(`heat_transfer_analysis.py:207`) ve Sutherland yok; ikinci bir yasa yazmak aynı kavramın ikinci
tanımı olurdu. **[ÖNERİ]** Tek yeni model sabiti **Pr_t** olacaktır (türbülanslı Prandtl); künyeli,
tek kaynakta, koşum beyanında görünür.

### 5.9 numba ve bit-özdeşlik sözleşmesi

**[ÖNERİ]** Mevcut sözleşme (`kernels.py`): numba isteğe bağlı, saf NumPy yolu bit-özdeş, arka uç
beyanlı. Viskoz katmanda bu sözleşme **ikiye ayrılır ve ikisi de açıkça yazılır**:
- **Akı çekirdekleri** (viskoz gerilme, SA difüzyonu): bit-özdeşlik HEDEFTİR ve ölçülür (aynı
  işlem sırası, `fastmath=False`) — mevcut disiplin aynen sürer.
- **Gevşetme katmanı** (blok-Thomas): pivotsuz, sabit sıralı eleme yazılırsa bit-özdeşlik
  ulaşılabilir; ulaşılamazsa **iddia edilmez** — onun yerine "yakınsanan alan toleransta aynı"
  bekçisi konur. Ölçülmeyen bit-özdeşlik iddiası yazılmaz.

### 5.10 Sınır koşullarının geri kalanı

**[ÖNERİ]** Giriş (rezervuar) ve çıkış (Pb) koşulları aynen kalır; SA için giriş ν̃ değeri
serbest-akım standardı (ν̃_∞ = 3ν_∞ … 5ν_∞ bandı, künyeli) olarak beyanla verilir ve çıkışta
dışdeğerlenir. Duvarda ν̃ = 0. Eksen: ν̃ çift (simetri).

---

## 6. Entegral sınır tabakası katmanı (hızlı katman + bağımsız ölçüm)

**[UYGULANDI — V5, 16 Ağu 2026]** Uygulama `hrma/flow/boundary_layer.py`'de (bu belgenin
önerdiği `hrma/cfd/` yolundan bilinçli sapma, V5 raporu: girdisi RANS değil yarı-1B çözüm,
`hrma/flow` "saf fizik" sözleşmesi; RANS geldiğinde `hrma/cfd` bunu İTHAL eder, ikinci
uygulama yazılmaz). 77 bekçi + 4 mutasyon; Blasius %0,9-1,75, türbülanslı levha
Schultz-Grunow'a −%2,6…−3,9. Kenar durumundan beslenen sıkıştırılabilir
momentum-integral marşı:

```
dθ/dz + (2 + H − M_e²)·(θ/u_e)·du_e/dz  =  c_f/2                (von Kármán, sıkıştırılabilir)
```

kapanışlar:
- c_f: **referans sıcaklık / referans entalpi** yöntemi (Eckert) ile sıkıştırılabilirlik
  düzeltmesi; türbülanslı taban korelasyonu + van Driest II dönüşümü,
- St = (c_f/2)·Pr^(−2/3) (Reynolds-Colburn analojisi) → q_w = ρ_e u_e cp St (T_aw − T_w),
- T_aw = T_e(1 + r(γ−1)/2·M_e²), r = Pr^(1/3) (türbülanslı) / Pr^(1/2) (laminer) —
  **[ÖLÇÜLDÜ]** aynı kurtarma tanımı depoda zaten var:
  `heat_transfer_analysis._adiabatic_wall_temperature` (satır 585-598), oradan İTHAL edilir.

**[ÖNERİ] Üç ürün çıktısı:** (i) δ*(z) → etkin alan daralması (isteğe bağlı zayıf viskoz-viskozsuz
çiftleme: duvarı δ* kadar içeri alıp Euler'i 2-3 dış iterasyon yeniden koşmak), (ii) ∮τ_w dA →
itki kaybı, (iii) q_w(z) → Bartz'a bağımsız ikinci ölçüm.

**[ÖNERİ] Hızlanma / yeniden laminerleşme UYARISI (modellenmez ama ÖLÇÜLÜR):** hızlanma parametresi
K = (ν/u_e²)·du_e/dz hesaplanır; K, literatürdeki eşiğin (≈ 3e-6) üstüne çıktığı istasyonlar
BEYAN edilir ("bu bölgede türbülanslı kabul iyimser olabilir"). Modellenmeyeni ölçüp göstermek,
HRMA'nın "sessizce yanılmaktansa açıkça uyar" çizgisidir. **[ÖNERİ]** Eşiğin künyesi
doğrulanacak (Moretti & Kays 1965 / Jones & Launder 1972 sınıfı).

---

## 7. Doğrulama merdiveni (test-first; basamak başına bekçi + mutasyon)

**[ÖNERİ] Kural aynı:** basamak yazılmadan kod yazılmaz; her basamak kendi analitik/deneysel
referansına karşı ölçülür; her basamakta en az bir **mutasyon kanıtı** (md5'li) verilir.

| # | Basamak | Referans | Ne kanıtlar | Not |
|---|---|---|---|---|
| 1 | Gerilme tensörü izi | tr(τ) = 0 özdeşliği | τ_θθ ve eksenel simetrik ıraksamanın doğruluğu | Cebirsel, ızgarasız |
| 2 | Serbest akım korunumu | Düzgün alanda R_viskoz ≡ 0 (makine sıfırı) | Gradyan operatörü + kapanış özdeşliği | Mevcut Σ S = 0 bekçisinin uzantısı |
| 3 | Gradyan tamlığı | Doğrusal alanda ∇φ tam | Green-Gauss + yüz düzeltmesi | Çarpık hücrede de sınanır |
| 4 | Laminer boru (Hagen-Poiseuille) | f = 64/Re, parabolik profil | Viskoz akı + no-slip + eksen | Sabit yarıçaplı duvar; yeni geometri kodu GEREKMEZ |
| 5 | Laminer boru ısı transferi | Nu = 3,657 (sabit T_w) / 4,364 (sabit q_w) | Enerji denklemi + ısıl duvar BC | Tam gelişmiş bölgede |
| 6 | Örtük katman hüküm-nötrlüğü | Açık yol çözümü | Gevşetmenin cevabı değiştirmediği | Blok-Thomas cebirsel bekçisiyle birlikte |
| 7 | Laminer düz levha (Blasius sınıfı) | c_f = 0,664/√Re_x, δ* = 1,7208√(νx/u) | Gelişen tabaka doğruluğu | Büyük yarıçaplı boru; enine eğrilik parametresi δ/R ÖLÇÜLÜP beyan edilir |
| 8 | Türbülanslı düz levha (SA) | c_f korelasyon bandı + log-yasası (u⁺ = ln y⁺/0,41 + ~5,0) | SA gerçeklemesi + duvar mesafesi | NASA TMR doğrulama vakası çaprazı |
| 9 | Izgara duyarlılığı ve çarpıklık | Kendi kendine (merdiven) | y⁺ ve çarpıklığın q_w'ye etkisi | Gerçek konturun 42° yakınsak açısıyla |
| 10 | Lüle duvar ısı akısı — DENEY | Back-Massier-Gier | Ürünün birinci iddiası | Künye ve erişim §7.1'de ÖLÇÜLDÜ |
| 11 | Bartz çaprazı | `_bartz_coefficient` | İki bağımsız yolun bandı | Band bir kez ÖLÇÜLÜP kilitlenir |
| 12 | Sürtünme kaybı | Sutton bandı %0,5-2 + entegral BL | Ürün eksiği #2'nin kapanışı | %1,5 sabitiyle karşılaştırma raporlanır |
| 13 | Ayrılma | τ_w = 0 istasyonu ↔ Summerfield/Schmucker/Kalt-Badal | Ürün eksiği #3 | Dördüncü, hesaplanmış üye |
| 14 | Korunum bütçesi (viskoz) | Kütle/enerji kapalı bütçe | Viskoz akıların korunumluluğu | Duvarda kütle akısı ayrık olarak tam sıfır kalmalı |

### 7.1 Deneysel referansın künyesi ve erişimi (ÖLÇÜLDÜ)

- **[ÖLÇÜLDÜ]** Back, L. H., Massier, P. F., Gier, H. L., "Convective heat transfer in a
  convergent-divergent nozzle", *International Journal of Heat and Mass Transfer*, **7**(5), 1964,
  s. 549-568, DOI 10.1016/0017-9310(64)90052-3 (Crossref sorgusu, 16 Ağu 2026).
- **[ÖLÇÜLDÜ] Kamuya açık sürüm VAR:** NASA NTRS kayıtları **19650026963** (1963) ve
  **19650010083** (1965), ikisi de `distribution: PUBLIC` ve PDF/tam metin indirilebilir
  (NTRS API sorgusu, 16 Ağu 2026). 19650010083 tam metninde tablo başlıkları ve Stanton/Reynolds
  sütunları görülüyor (18 "Reynolds", 10 "Stanton" geçişi).
- **[ÖLÇÜLDÜ] Uyarı:** metin katmanı 1960'ların taramasıdır, OCR kalitesi düşüktür (ilk sayfa
  çıktısı kelime düzeyinde bozuk). Sayısal tablo PDF'ten **elle çıkarılmalı** ve
  `data/validation/` altına künyeli JSON olarak konmalıdır — bu, yarım partilik ayrı bir iştir
  ve Berke onayı gerektirir (§13, soru 3).
- **[ÖLÇÜLDÜ] İkinci aday (sınır tabakası ölçümü de içeriyor):** Back, L. H., Cuffel, R. F.,
  "Turbulent Boundary Layer and Heat Transfer Measurements Along a Convergent-Divergent Nozzle",
  *Journal of Heat Transfer*, **93**(4), 1971, s. 397-407, DOI 10.1115/1.3449837. Bu makale
  doğrudan θ, δ* ve c_f ölçümleri içerdiğinden entegral BL katmanının da referansıdır;
  **[ÖNERİ]** açık erişim durumu doğrulanacak (ASME, muhtemelen kapalı).

### 7.2 Diğer künyeler (Crossref ile doğrulandı)

- **[ÖLÇÜLDÜ]** Spalart, P., Allmaras, S., "A one-equation turbulence model for aerodynamic flows",
  30th Aerospace Sciences Meeting, AIAA-92-0439, 1992, DOI 10.2514/6.1992-439.
- **[ÖNERİ]** Negatif-SA: Allmaras, Johnson & Spalart, "Modifications and Clarifications for the
  Implementation of the Spalart-Allmaras Turbulence Model", ICCFD7-1902, 2012 — Crossref bu
  bildiriyi indekslemiyor; **künye NASA Turbulence Modeling Resource sayfasından
  doğrulanacak** (bu turda sayfa alınamadı, JS yönlendirmesi).
- **[ÖLÇÜLDÜ]** Eckert, E. R. G., "Engineering Relations for Heat Transfer and Friction in
  High-Velocity Laminar and Turbulent Boundary-Layer Flow Over Surfaces With Constant Pressure and
  Temperature", *Trans. ASME / J. Fluids Eng.* **78**(6), 1956, s. 1273-1283,
  DOI 10.1115/1.4014011. (Sık atıf yapılan 1955 *J. Aeronautical Sciences* 22(8):585-587 sürümü
  aynı yöntemdir; **[ÖNERİ]** hangisinin künye olarak yazılacağı uygulama anında seçilir.)
- **[ÖNERİ]** van Driest, E. R., "Turbulent Boundary Layer in Compressible Fluids",
  *J. Aeronautical Sciences* **18**(3), 1951, s. 145-160 — Crossref sorgusu bu turda başarısız
  oldu, **künye doğrulanacak**.
- **[ÖLÇÜLDÜ]** Venkatakrishnan, V., *J. Comput. Phys.* **118**(1), 1995, s. 120-130,
  DOI 10.1006/jcph.1995.1084 — Aşama 1'in sınırlayıcı dondurma gerekçesi; künye doğru.

---

## 8. Ürün köprüleri (viskoz sonucun ürüne dokunduğu üç yer)

### 8.1 Termal FEA köprüsü — hazır sözleşmeye takılır

**[ÖLÇÜLDÜ]** `hrma/fea/bridge.py` `axial_profile` = (`x_mm`, `h_g`, `T_recovery`) istiyor ve
eksende kontur uyuşmasını denetliyor (satır 808-830: profil ekseni konturla uyuşmazsa RED).
**[ÖNERİ]** Viskoz CFD bu üçlüyü doğrudan üretir:
- `h_g(z) = q_w(z) / (T_aw(z) − T_w(z))` — q_w çözümden ÖLÇÜLÜR,
- `T_recovery(z) = T_aw(z)` — kurtarma faktörü tanımıyla ya da adyabatik eş koşudan (hangisi
  kullanıldıysa beyanlı),
- eksen zaten `sample_nozzle_inner_contour` konturudur → uyuşma tanım gereği sağlanır.

**[ÖNERİ] Kazanç:** bugün termal FEA'nın sınır koşulu **Bartz korelasyonudur**; viskoz CFD'den
sonra aynı arayüzden **çözülmüş** bir profil gelebilir. İkisi arasında geçiş, kullanıcıya
"kaynak: Bartz | CFD" olarak beyanlanır ve ikisinin farkı gösterilir (birini sessizce diğeriyle
değiştirmek yasak).

### 8.2 İtki kaybı — uydurma sabitin sonu

**[ÖNERİ]** `F_sürtünme = ∮ τ_w · ê_z dA` (dönel yüzey integrali; ızgara zaten 2π'li yüzey
vektörleri taşıyor). Ürün, `friction_loss_fraction` sabitini "ölçülen" değerle yan yana
raporlar. **[ÖNERİ] Sabiti sessizce değiştirmek geriye uyumu bozar** — karar Berke'nin (§13,
soru 5).

### 8.3 Ayrılma — dördüncü, hesaplanmış üye

**[ÖNERİ]** Viskoz çözümde ayrılma başlangıcı τ_w'nin işaret değiştirdiği istasyondur (tanım
gereği, ampirik eşik değil). `hrma/cfd/separation.py` köprüsü genişletilir: aynı çıktıda
Summerfield / Schmucker / Kalt-Badal / **CFD-τ_w** dört üye ve aralarındaki fark. Şok-sınır tabaka
etkileşimi RANS'ta çözülür ama **güvenilirliği model bağımlıdır** — iddia bandı beyanlı olur
(§13, soru 7).

---

## 9. Performans bütçesi

### 9.1 Ölçülen taban

**[ÖLÇÜLDÜ]** 256×64, numba: kalıntı 1,804 ms, iterasyon ≈ 3,9 ms, tam yakınsama (21 173 iter)
86,6 s. 120×24: kalıntı 0,405 ms; izantropik derin yakınsama ~15 s.

### 9.2 Viskoz maliyetin tahmini

**[ÖNERİ]** Ölçülen dağılıma (MUSCL %32, HLLC %23) dayanarak:
- Viskoz akı (hücre gradyanları + yüz düzeltmesi + gerilme + ısı akısı): ≈ +%60-80 kalıntı
  maliyeti (bir MUSCL geçişi sınıfı iş),
- SA (taşınım + difüzyon + kaynak): ≈ +%30,
- j-satır blok-Thomas (4×4, nj sıralı adım, i üstünde vektörize): ≈ kalıntı maliyetinin yarısı,
→ **iterasyon başına ≈ 3-4× Euler**, yani 256×64'te ≈ 12-16 ms/iter.

**[ÖNERİ] Hedef koşum süreleri:**
| Katman | Izgara | Hedef süre | Dayanak |
|---|---|---|---|
| Entegral BL (Euler üstüne) | — | < 0,1 s | ~256 istasyonluk ODE marşı |
| RANS "standart" | 192×48 | ≈ 1-3 dk | 3-4× iterasyon maliyeti + Euler'den başlatma |
| RANS "ince" | 256×64 | ≈ 3-8 dk | Aynı, ölçek |
| Euler (bugünkü) | 256×64 | 87 s | **[ÖLÇÜLDÜ]** |

**[ÖNERİ] Bu satırlar TAHMİNDİR** ve V1 kapısında ölçülecektir. Viskoz koşuların sınır tabakasının
oturması için Euler'den daha çok iterasyon istemesi olağandır (3-10× literatürde tipiktir); bu
yüzden kapı ölçütü aşağıda serttir.

### 9.3 V1 performans KAPISI (ölçülür, geçilmezse çare belgede)

**[ÖNERİ] Ölçüt:** laminer boru + laminer lüle vakasında (192×48, y⁺ ≲ 1) yakınsama **≤ 5 dakika**
(M4 Max, numba). Geçilmezse sırayla:
1. **Izgara sıralaması (grid sequencing):** kaba ızgarada yakınsa, ince ızgaraya aktar (ucuz,
   düşük risk, ~2-3× beklenir).
2. **Yerel-Δt yerine tam örtük i-yönü de** (ADI/yaklaşık çarpanlama) — orta risk.
3. **FAS çok-ızgara (multigrid)** — yüksek kazanç, yüksek risk; ancak 1 ve 2 yetmezse.
4. **y⁺ hedefini gevşetme** (son çare, çünkü §4.3'teki reddi zayıflatır) — yapılırsa q_w iddiası
   band olarak yeniden beyanlanır.

**[ÖNERİ] numba durumu değişiyor:** Euler'de numba "isteğe bağlı hızlandırma"ydı (**[ÖLÇÜLDÜ]**
1,98×, `kernels.py` sözleşmesi). Viskoz + SA yolunda saf NumPy koşusu 2× yavaş demek 10+ dakika
demektir. Sözleşmenin ne olacağı Berke'ye açık soru (§13, soru 6); tasarımın önerisi: **saf NumPy
yolu doğruluk bekçisi olarak KORUNUR (küçük ızgarada koşar), ama yüksek doğruluk katmanı numba
ister ve bunu ARAYÜZDE söyler.**

---

## 10. NOT_MODELLED — viskoz aşamadan sonra dürüst liste

**[ÖNERİ]** Aşama 2 bittiğinde `CFD_NOT_MODELLED` şu hâle gelir (kaldırılanlar üstü çizili gibi
düşünülmeli; `viscosity_turbulence` anahtarı SİLİNMEZ, **daraltılır**):

| Anahtar | Beyan |
|---|---|
| `turbulence_model_uncertainty` | Türbülans ÇÖZÜLMÜYOR, MODELLENİYOR (SA-neg). Ayrılma, şok-sınır tabaka etkileşimi ve yeniden yapışma model bağımlıdır; band beyanlıdır |
| `transition_relaminarization` | Geçiş modeli yok: akış tam türbülanslı kabul edilir. Hızlanma parametresi K ölçülür ve eşiği aşan bölge UYARILIR, ama yeniden laminerleşme modellenmez |
| `reaction_real_gas` | Tepkime, ayrışma/yeniden birleşme, gerçek gaz yok (kalorik mükemmel, donmuş kompozisyon) |
| `radiation` | Gaz ışıması CFD'de yok (`heat_transfer_analysis` Leckner modeli ayrı katmandır; toplam akı iddiası ikisinin toplamı olarak beyanlanmalı) |
| `wall_roughness` | Duvar pürüzlülüğü modellenmedi (hidrolik pürüzsüz duvar) |
| `time_accuracy` | Kararlı hâl; ateşleme/söndürme geçişleri yok |
| `three_dimensional` | 3B etkiler yok: dönme (swirl), enjektör deseni, film soğutma jetleri, yanal yükler |
| `two_phase` | Yoğuşma/parçacık (Al₂O₃) yükü ve iki fazlı sürükleme yok |
| `conjugate_heat_transfer` | Cidar iletimi CFD içinde çözülmez; T_w bir sınır koşuludur (FEA ile çevrim §13 soru 2) |

---

## 11. Aşamalandırma, dosya düzeni, bekçi tahminleri

### 11.1 Dosya düzeni (yeni)

```
hrma/cfd/gas_transport.py     # μ(T), k(T), cp, Pr, Pr_t — TEK kaynağa sarmalayıcı
hrma/cfd/gradients.py         # düzlemsel Green-Gauss + yüz gradyanı düzeltmesi
hrma/cfd/viscous.py           # gerilme tensörü, viskoz akı, hoop kaynağı, duvar τ_w / q_w
hrma/cfd/wall_distance.py     # kontur polilinesine tam en yakın mesafe
hrma/cfd/turbulence_sa.py     # SA-neg taşınım + kaynaklar (nokta-örtük)
hrma/cfd/implicit.py          # j-yönü blok üç-köşegen gevşetme (Thomas)
hrma/flow/boundary_layer.py   # entegral BL — V5'te UYGULANDI (yol sapması §6'da gerekçeli)
hrma/cfd/wall_output.py       # q_w/h_g/T_rec/c_f → FEA köprüsü + itki kaybı sözleşmesi
tests/cfd/test_viskoz_*.py    # merdiven basamakları (basamak başına dosya)
```

**[ÖNERİ] Değişecek mevcut dosyalar (asgari):**
- `grid_axisym.py`: isteğe bağlı duvar kümeleme (varsayılan `linspace` → **bit-özdeş**),
- `euler_core.py`: `wall_bc='slip'|'noslip'` parametresi (varsayılan dal bugünkü kod),
- `steady.py`: viskoz/örtük sürücü seçenekleri + yeni beyan alanları,
- `__init__.py`: `CFD_NOT_MODELLED` daraltması + yeni dışa vermeler.

### 11.2 Evreler

| Evre | İçerik | Yeni bekçi (tahmin) | Kapı |
|---|---|---|---|
| **V0** | `gas_transport` + `gradients` + geometri hazırlığı | ~12 | Basamak 1-3 yeşil |
| **V1** | Laminer viskoz akı + no-slip/ısıl duvar + `implicit` | ~30 | Basamak 4-7 yeşil **+ performans kapısı §9.3** |
| **V2** | SA-neg + duvar mesafesi + duvar kümeleme + y⁺ rozeti | ~25 | Basamak 8-9 yeşil |
| **V3** | Lüle doğrulaması: Back verisi + Bartz çaprazı | ~15 | Basamak 10-11 yeşil |
| **V4** | Ürün köprüleri: FEA termal, itki kaybı, ayrılma, uç + panel | ~20 | Basamak 12-14 yeşil |
| **V5** | Entegral BL katmanı + yarı-1B'nin %1,5 sabitinin kapanışı | ~18 | RANS ↔ BL karşılaştırma bandı ölçüldü |

**[ÖNERİ] Toplam ≈ 120 hedefli bekçi + evre başına ≥ 3 mutasyon kanıtı (≈ 18).**
**[ÖNERİ] Efor tahmini: 8-10 parti** (2.6.27 kampanyasının parti ölçeğiyle; V1 ve V2 en ağır
ikisi). Bu bir tahmindir, V1 kapısının sonucuna göre revize edilir.

### 11.3 Regresyon sözleşmesi (Euler yolunun bit-özdeşliği)

**[ÖNERİ] Somut ve uygulanabilir:** V0 başlamadan ÖNCE, bugünkü çözücüyle iki referans alan
(60×12 ve 120×24, izantropik + şoklu) `.npz` olarak dondurulur ve depoya konur. Her evrenin
bekçisi bu dosyalara karşı **`np.array_equal`** ister. Böylece "69 bekçi hâlâ yeşil" ifadesi
davranışsal değil **bit düzeyinde** bir sözleşme olur. Mutasyon kanıtı: viskoz kapalıyken herhangi
bir aritmetik yeniden sıralama bu bekçiyi kırmızıya düşürmeli.

---

## 12. Lean biçimsel ayak (daraltılmış, pratik adaylar)

**[ÖLÇÜLDÜ] Emsal depoda zaten var:** `formal/LeanLab/HRMACfdReferans.lean` (Euler aşamasının
biçimsel ayağı, bu turda dosya olarak mevcut) aynı felsefeyi kuruyor — "*sayısal çözücüyü
İSPATLAMAZ; kilitlenen şey TESTLERİN karşılaştırdığı analitik referans formüllerin matematiksel
tutarlılığıdır*". Aşağıdaki adaylar o dosyanın viskoz devamıdır (izantropik / normal şok / HLLC /
boğulmuş debi kulvarlarının yanına beşinci kulvar).

**[ÖNERİ]** Sayısal çözücü ispatlanmaz (ayrıklaştırma testle doğrulanır); ispat, **testlerin
karşılaştırdığı kapalı-form referansları ve ayrık cebirsel özdeşlikleri** kilitler. Aday sıralaması
(fayda/emek):

1. **Gerilme izinin sıfırlığı (eksenel simetrik):** tr(τ) = 0, τ_θθ ve Θ = ∂u_z/∂z + ∂u_r/∂r + u_r/r
   tanımlarıyla. Klasik iki hatayı (hoop bileşenini unutmak, ıraksamaya u_r/r'yi katmamak) birden
   yakalar. **En yüksek fayda/emek.**
2. **Blok üç-köşegen (Thomas) doğruluğu:** ileri eleme + geri yerine koymanın, köşegen blokların
   tersinirliği varsayımıyla sistemin TAM çözümünü verdiği. Yeni örtük katmanın kalbi ve saf cebir.
3. **Kurtarma sıcaklığı sınırı:** r ≤ 1 için T_aw ≤ T₀ (ve T_aw ≥ T_e). Kurtarma faktörü/üs
   hatalarını yakalar; termal köprünün girdisi olduğu için ürün etkisi doğrudan.
4. **Referans sıcaklık sınırlılığı (Eckert):** T* = T_e + 0,5(T_w − T_e) + 0,22·r·(T_aw − T_e)
   ifadesinin, verilen hipotezler altında {T_e, T_w, T_aw} kümesinin min-maks aralığında kaldığı.
   Absürt (negatif/aşırı) referans durumunu imkânsız kılar.
5. **Viskoz operatörün serbest akım korunumu:** Σ S_düzlem = 0 (zaten bekçili) verildiğinde,
   düzgün hız/sıcaklık alanında ayrık viskoz akı toplamının özdeş sıfır olduğu.
6. **Entegral momentum özdeşliği:** sıkıştırılabilir von Kármán biçiminin M_e → 0 limitinde
   klasik biçime indirgendiği (cebirsel eşdeğerlik).

**[ÖNERİ] Kapsam dışı bırakılanlar:** Blasius benzerlik ODE'sinin varlık/teklik özellikleri,
türbülans modeli sabitlerinin türetimi, ayrıklaştırmanın yakınsaklık ispatı. Bunlar bu ürünün
kaldıramayacağı emek sınıfındadır ve testler zaten sayısal karşılığını veriyor.

---

## 13. Berke'ye açık sorular

1. **Koşum süresi bütçesi.** "Yüksek doğruluk" viskoz koşusu için üst sınır nedir? 5 dakika kabul
   mü, yoksa 60 saniye mi hedef? (Bu tek cevap y⁺ hedefini, ızgara boyutunu ve §9.3 kapısındaki
   çare sırasını doğrudan belirliyor.)
   **→ KARAR (Berke, 16 Ağu 2026): süre TAVANI YOK — "detaylı analizler uzun sürer", doğruluk
   süreye kurban edilmez. Şart olan TAKILMA TESPİTİ: kalıntı durgunluk/ıraksama algısı + gerçek
   ilerleme beyanı (Analiz Merkezi kural 3'ün SSE/poll yolu; sahte yüzde yasak). §9.3 kapısı
   "geçilmezse çare" olmaktan çıkar, "ölçülür ve beyan edilir"e döner; y⁺ ≲ 1 hedefi kesinleşti.**
2. **Duvar sıcaklığı ve çevrim.** T_w nereden gelsin: (a) kullanıcı verir, (b) termal FEA'dan tek
   yönlü aktarılır, (c) CFD ↔ FEA kapalı çevrim (2-3 dış iterasyon)? (c) FINAL kapsamında mı, yoksa
   2.8'e mi?
3. **Back verisinin sayısallaştırılması.** NTRS'teki tarama PDF'ten ısı akısı tablolarını elle
   çıkarıp `data/validation/` altına künyeli JSON yapmak ≈ yarım parti emek. Onay veriyor musun,
   yoksa doğrulama korelasyon bandıyla mı yetinsin (o zaman "deneyle doğrulandı" iddiası
   KURULAMAZ)?
   **→ KARAR (Berke, 16 Ağu 2026): ONAYLI — elle çıkarım yapılacak. EK GÖREV: 1964 sonrası
   modern lüle duvar ısı akısı deney verisi de aranıp bulunacak ve Back'le ÇAPRAZ teyit
   edilecek (aday havuz: DLR/ONERA alt-ölçek lüle kampanyaları, üniversite yayınları;
   uygulama partisinde ayrı araştırma kalemi — kaynak hiyerarşisi kuralıyla, birincil
   kaynak + kamuya açıklık şartı).**
4. **İki türbülans modeli.** FINAL tek modelle mi çıksın (SA-neg), yoksa SST k-ω da eklenip sonuç
   **model bandı** olarak mı sunulsun? (İkincisi ≈ +2 parti, ama ürünün dürüstlük çizgisine çok
   yakışıyor.)
5. **%1,5 sürtünme sabiti.** Viskoz sonuç geldiğinde yarı-1B katmanın varsayılanı DEĞİŞSİN mi
   (çıktılar değişir, geriye uyum kırılır), yoksa iki sayı yan yana mı raporlansın?
   **→ KARAR (Berke, 16 Ağu 2026): "doğrusu neyse o olsun" — varsayılan ÖLÇÜLEN entegral-BL
   değerine geçer (V5 verisi: 8/8 vakada %1,02-1,38, sabit kötümserdi). Geçiş F2 karar-8
   politikasıyla: göç manifestosu (old→new→Δ→reason, tests/flow/test_surtunme_gocu.py) +
   friction_source beyanı ('integral_bl_measured' | 'user' | 'legacy_constant') + model
   doğrulama bandı basis'te. 0,015 sabiti yalnız YEDEK (şok rejimi / BL kapalı). V6
   partisinde uygulandı.**
6. **numba sözleşmesi.** Viskoz katmanda numba fiilen zorunlu hâle geliyor. "İsteğe bağlı
   bağımlılık" sözleşmesi (saf NumPy yolu bekçili) korunsun ama arayüz yavaşlığı beyan etsin mi;
   yoksa yüksek doğruluk katmanı numba şart mı koşsun?
7. **Ayrılmış akış iddiası.** RANS ayrılmış bölgeyi çözer ama güvenilirliği model bağımlıdır.
   FINAL'de "ayrılma sonrası alan" gösterilsin mi (beyanla), yoksa yalnız ayrılma BAŞLANGICI mı
   iddia edilsin?
8. **Kapsam sırası.** V5 (entegral BL) aslında en ucuz ve en hızlı ürün kazancı (%1,5 sabitinin
   kapanışı). V0'dan ÖNCE mi yapılsın (erken kazanç, RANS'a doğrulama aracı hazır olur), yoksa
   planlandığı gibi sona mı kalsın?
   **→ KARAR (Berke, 16 Ağu 2026): ÖNE ALINDI — V5 entegral BL, V0 RANS altyapısından ÖNCE
   kendi partisinde yapılır: yarı-1B katmandaki uydurma %1,5 sürtünme sabiti
   (`nozzle_flow_1d.py:240`) gerçek momentum-integral hesabıyla değişir, RANS geldiğinde
   çapraz ölçüm aracı hazır olur. Varsayılanın değişip değişmeyeceği (soru 5) hâlâ açık —
   V5 partisi iki sayıyı da ölçüp fark raporuyla gelecek, karar o ölçümle verilecek.**

---

## 14. Bu belgenin özeti (bir paragraf)

**[ÖNERİ]** FINAL'in viskoz CFD'si, mevcut Euler çekirdeğinin ÜSTÜNE kompozisyonla kurulan,
duvar-çözümlü (y⁺ ≲ 1), Spalart-Allmaras (negatif varyant) türbülans modelli, tam eksenel simetrik
RANS çözücüsüdür; tek gerçek engeli olan yerel-Δt çöküşü (nj merdiveninde ÖLÇÜLDÜ: iterasyon
1/Δt_min ile orantılı büyüyor, duvar-çözümlü ızgarada saat mertebesi) j-yönü satır-örtük gevşetme
katmanıyla kaldırılır ve o katmanın hüküm-nötrlüğü ayrı bir bekçiyle kanıtlanır. Entegral sınır
tabakası aynı kulvarda, ürünün hızlı katmanı ve RANS'ın bağımsız çapraz ölçümü olarak yazılır.
Doğrulama merdiveni 14 basamaktır ve tepesinde kamuya açık (NTRS) Back-Massier-Gier lüle ısı akışı
deneyi vardır. Euler yolu viskoz kapalıyken **bit-özdeş** kalır ve bu, dondurulmuş referans
alanlara karşı bir regresyon sözleşmesiyle mekanik olarak korunur.
