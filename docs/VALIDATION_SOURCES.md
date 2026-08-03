# Doğrulama kaynakları kayıt defteri

**Oluşturma:** 3 Ağustos 2026 · **Veri kümesi:** `data/validation/`
**Biçim:** CLAUDE kural 14 (Claim / Evidence / Confidence / Date checked / What may change)

Bu defter, 2.6.27+ ile gelecek dört modülün (eksenel simetrik yapısal ve termal
FEA, yarı-1B lüle akışı, turbopompa boyutlandırma, akustik kararlılık)
dayanacağı **yayımlanmış** verinin künye kaydıdır. Yol haritasının kuralı
gereği her modül doğrulama kümesiyle gelir; bu belge o kümenin nereden
geldiğini ve **ne kadar güvenildiğini** tek yerde tutar.

Kayıtların makine-okur hâli `data/validation/*.json`; indirilen belgelerin
boyut ve SHA-256 künyesi `data/validation/sources/MANIFEST.md`.

## Nasıl okunur

| Alan | Anlamı |
|---|---|
| **Claim** | Veri kümesinin ne iddia ettiği |
| **Evidence** | Kaynak(lar). Birden fazla bağımsız kaynak varsa güven yükselir |
| **Confidence** | `high` = birincil kaynak veya kapalı form türetme · `medium` = ikincil ama çapraz tutarlı · `low` = tek kaynak, doğrulanmamış |
| **Date checked** | 2026-08-03 (tüm kayıtlar aynı turda çekildi) |
| **What may change** | Bu satırı geçersiz kılabilecek şey |

**Kural (CLAUDE 14):** Tek kaynaktan gelen ve bağımsız olarak doğrulanamayan
her değer `low` işaretlenir. Bu belgede `low` olan **bir** kayıt var ve neden
öyle olduğu açıkça yazılıdır.

---

## 1. Yapısal — kalın cidarlı silindir (Lamé)

**Claim.** Eksenel simetrik yapısal çözücü, iç basınç altındaki kalın cidarlı
silindirde radyal/teğetsel gerilmeyi ve radyal yer değiştirmeyi %0.5 içinde
üretmelidir. Dönen halka (merkezkaç) yüklemesi ayrıca sınanır.

**Evidence.**
- Ansys Mechanical APDL Verification Manual, **VM25 — Stresses in a Long
  Cylinder**, Durum 1 (iç basınç) ve Durum 2 (dönme). PyMAPDL doğrulama örneği
  olarak açık yayımlanmış: <https://examples.mapdl.docs.pyansys.com/verif-manual/vm-025.html>
- Bağıntıların klasik kaynağı: Lamé (1852); çağdaş sunum Timoshenko,
  *Strength of Materials, Part II*.

**Confidence: high.** Sebebi yalnız kaynağın itibarı değil: **altı gerilme
hedefinin altısı da** Lamé bağıntılarından bağımsız olarak yeniden hesaplandı
ve birebir tuttu (r=4 in: −30 000 / +50 000 psi; r=6 in: −7 777.78 / +27 777.78;
r=8 in: 0 / +20 000). Dönme durumunun dört hedefi de tuttu (sapma < %0.01).

**Date checked.** 2026-08-03

**What may change.** Ansys sürüm numarası değişebilir; hedef değerler
değişmez (analitiktir). **Asıl risk sürüm değil varsayım:** VM25'in yer
değiştirme hedefi 0.0078666 in yalnız **düzlem gerilme / açık uç**
(σ_z = 0) varsayımıyla çıkar. Düzlem şekil değiştirme 0.0076267 in, kapalı uç
0.0074667 in verir — yani %5'e varan fark. Çözücü hangi varsayımı kurduğunu
bilmeden bu vaka geçilirse doğrulama sahtedir; bu yüzden kayıtta
`inputs.stress_state` açıkça yazılıdır.

---

## 2. Termal — geçici iletim analitik vakaları

**Claim.** Geçici ısı çözücüsü, yarı-sonsuz katıda hem sabit yüzey sıcaklığı
(Dirichlet) hem sabit yüzey akısı (Neumann) sınır koşulunda analitik çözümü
%1 içinde üretmelidir.

**Evidence.** Carslaw & Jaeger, *Conduction of Heat in Solids*, 2. baskı,
Oxford, 1959, Bölüm 2 — yarı-sonsuz katı çözümleri (`erfc` ve `ierfc` formları).

**Confidence: high.** Çözümler kapalı formdur ve ders kitaplarında aynıdır;
beklenen değerler `math.erfc` ile 8 haneye hesaplandı. Sabit akı vakasının
yüzey değeri **iki bağımsız yoldan** doğrulandı: genel `ierfc` bağıntısı ve
kapalı yüzey formülü `2q₀√(αt/π)/k` — ikisi de 2378.832155 K verdi.

**Date checked.** 2026-08-03

**What may change.** Hiçbir şey — analitik çözüm eskimiyor. Tek dikkat:
sabit akı vakasındaki sıcaklık artışı gerçek bir malzemede erime demektir;
vaka **sayısal** doğrulama içindir, malzeme davranışı iddiası değildir.

---

## 3. Termal — Bartz katsayısı hata bandı

**Claim.** Bartz bağıntısı bir "doğru cevap" değil, bilinen bir hata bandına
sahip bir yaklaşımdır. HRMA'nın gaz tarafı ısı taşınım katsayısı bu bandın
**dışına** çıkarsa hata bizdedir; bandın içinde kalması Bartz'ın kendi
belirsizliğidir.

**Evidence.**
- Deneysel karşılaştırma: *A Comparison of Experimental Heat-Transfer
  Coefficients in a Nozzle With Analytical Predictions From Bartz's Methods…*,
  NASA/NC State, 1971, NTRS 19710011726. Katı yakıtlı motor (AP %83.3 +
  PBAA %14.4), ZTA grafit boğaz, Pc = 220 / 410 / 742 psia.
- Bağıntının kendisi: D. R. Bartz, *A Simple Equation for Rapid Estimation of
  Rocket Nozzle Convective Heat Transfer Coefficients*, Jet Propulsion 27(1),
  s. 49-51, 1957, doi:10.2514/8.12572.

**Ölçülen bantlar (kaynağın metninden):** korelasyon bağıntısı Pc 75-250 psia
aralığında ≈ **%50 yüksek**; boğazda **%45 yüksek** (Kolozsi hava verisi);
N₂O₄-hidrazin verisinde boğaz bölgesinde **%80 yüksek ile %45 düşük** arası.
Bu çalışmanın kendi bulgusu: yakınsak bölge ve boğazda ölçüm, Bartz'ın her iki
yönteminden de **tutarlı olarak düşük**.

**Confidence: high** (hata bandı için). Bantlar raporun **metninden** okundu.

**What may change.** Bartz bağıntısının **üs değerleri** 1957 makalesinden
teyit edilmedi — makale bu turda açılmadı, bağıntı biçimi ikincil kaynaklardan
bilinen standart formdur. Modül yazılmadan önce orijinal makaleyle
karşılaştırılmalıdır. Ayrıca raporun sayısal h_g değerleri yalnız **şekil**
olarak yayımlanmış; grafikten okuma **yapılmadı**, bu yüzden kayıtta sayısal
h_g yoktur (uydurma sayı üretmemek için).

---

## 4. Turbopompa — RL10

**Claim.** Turbopompa boyutlandırma zinciri (NPSH → Nss → N → Ns → çark çapı),
RL10'un yayımlanmış devir, debi, yükseklik, verim ve çark çapı değerlerini
üretebilmelidir.

**Evidence.**
- **Tasarım noktası:** *Design Report for RL10A-3-3 Rocket Engine*, PWA FR-1769,
  Pratt & Whitney, 1966, Tablo V-I — üç karışım oranında (4.4 / 5.0 / 5.6)
  yakıt pompası, oksitleyici pompası ve türbin değerleri.
  MR 5.0'da: LOX pompası 12 100 rpm / 183.7 gpm / 1123 ft / %63.2;
  yakıt pompası 30 250 rpm / 580.9 gpm / 32 740 ft (iki kademe) / %54.7.
  <https://www.nasa.gov/wp-content/uploads/2025/06/design-report-for-rl-10-a-3-3-1966.pdf>
- **Donanım geometrisi:** NASA TM-107318, Tablo 2.2.1 ve 2.3.1 — yakıt çarkı
  **7.07 in** (her iki kademe), LOX çarkı **4.20 in**, türbin ortalama çapı
  5.90 in. <https://ntrs.nasa.gov/api/citations/19970010379/downloads/19970010379.pdf>

**Confidence: high.** İkisi de birincil kaynak, sayılar metinden okundu.
Çark çapları depoda hâlihazırda bulunan
`hrma/data/validation_records/liquid/liq-rl10a33a-nominal-spec.json` kaydıyla
**tutarlıdır** (aynı 7.07 / 4.2 değerleri).

**Date checked.** 2026-08-03

**What may change.** Üç uyarı:
1. **Bunlar ölçüm değil.** FR-1769 tablosu *tasarım noktası tahminidir*;
   TM-107318 tablosu ise kaynağın kendi dipnotuyla *modelin öngördüğü* tipik
   çalışma noktasıdır. TM-107318'in head/debi/verim değerleriyle kıyaslama
   yapmak, HRMA'yı gerçeğe değil **başka bir modele** benzetmek olur — kayıtta
   bu blok `MODEL_PREDICTION_NOT_MEASUREMENT` etiketlidir.
2. **Varyant karışıklığı.** FR-1769 → RL10A-3-**3**; TM-107318 → RL10A-3-3**A**.
   Farklı motorlardır.
3. **NPSH yok.** İki belgede de NPSH ve emme özgül devri **yayımlanmamıştır**
   (FR-1769 yalnız "düşük net pozitif emme basıncında azami çalışma aralığı"
   diye nitel söz eder). C1'in NPSH marjı iddiası bu kümeyle doğrulanamaz.

---

## 5. Turbopompa — F-1

**Claim.** Aynı boyutlandırma zinciri, RL10'dan iki buçuk mertebe büyük debide
ve beş kat düşük devirde de çalışmalıdır (ölçek bağımsızlığı).

**Evidence.** Oefelein & Yang, *Comprehensive Review of Liquid-Propellant
Combustion Instabilities in F-1 Engines*, Journal of Propulsion and Power 9(5),
s. 657-677, 1993, doi:10.2514/3.23674, **Tablo 2**.
Ortak mil **5 500 rpm**, 40 MW (53 000 hp). Yakıt: 796 kg/s, 15 600 gpm,
giriş 310 kPa → çıkış 13 000 kPa, yükseklik 1575 m. Oksitleyici: 1804 kg/s,
25 000 gpm, giriş 450 kPa → çıkış 11 000 kPa, yükseklik 944 m.

**Confidence: high.** Tablo **üç bağımsız iç tutarlılık sınavından geçti**:
1. c\* = p_boğaz·A_t/ṁ = **1660.09 m/s**, tablonun yayımladığı 1660 m/s ile birebir.
2. Oksitleyici pompada basınç yükselişi 10 550 kPa, ρgH = 10 581 kPa (%0.3 sapma).
3. Yakıt pompasında 12 690 kPa'ya karşı 12 480 kPa (%1.7 sapma).

**Date checked.** 2026-08-03

**What may change.** İki kaynak-içi kusur kayda geçirildi:
- **ERRATUM:** Tablonun *"Developed head, m, in."* başlığındaki ikinci birim
  **yanlıştır** — 5168 ve 3097 sayıları **fittir**, inç değil
  (5168 ft = 1575.2 m; 3097 ft = 944.0 m, tablonun kendi metrik sütunuyla
  birebir). Bu sayılar okunurken ft varsayılmalıdır.
- Yakıt tahliye basıncı tabloda 13 000 kPa (1856 psia), aynı makalenin
  metninde 12.9 MPa (1870 psia) — **%1 tutarsızlık kaynağın kendisindedir**;
  kayda ikisi de yazıldı.
- NPSH ve çark çapı bu kaynakta da **yok**.

---

## 6. Turbopompa — Merlin 1D ve RD-180 (olumsuz kayıt)

**Claim.** Yol haritası C1 bu iki motoru da doğrulama kümesinde istiyor.
**Bu turda birincil kaynak bulunamadı.**

**Evidence.** Arama yapıldı, sonuç olumsuz:
- RD-180 için NTRS/AIAA taramasında yalnız mimari tarifi bulundu (iki yanma
  odasını besleyen tek turbopompa, oksitleyici-zengin kademeli yanma); sayısal
  mil devri yok. NPO Energomash birincil datasheet'i erişilemedi — depodaki
  `liq-rd180-atlas-spec.json` kaydı aynı erişim sorununu 2026-07-23'te
  kaydetmiş, **durum değişmedi**.
- Merlin 1D için SpaceX resmi sayfası yalnız itki yayımlıyor; turbopompa
  büyüklükleri hiç yayımlanmamış (depodaki `liq-merlin1d-thrust-spec.json`
  bu sınırı zaten belgeliyor).

**Confidence: not_applicable** (olumsuz sonuç kaydı).

**What may change.** Energomash veya SpaceX bir gün veri yayımlarsa.
**İkincil derlemelerden doldurulmamalıdır:** Astronautix/Wikipedia'da dolaşan
devir sayıları birbirini kopyalıyor ve birincil kaynağa bağlanamıyor.
Depo kuralı (`docs/STANDART_ATIFLARI.md`): *kaynaksız bırakmak, yanlış kaynak
göstermekten iyidir.* Ölçek aralığı RL10 (30 250 rpm) ve F-1 (5 500 rpm) ile
zaten kapsanıyor.

---

## 7. Lüle akışı — izentropik alan-Mach ve normal şok

**Claim.** Yarı-1B çözücü, verilen alan oranı için ses altı ve ses üstü Mach
köklerini ve ıraksak kesitteki normal şokun basınç sıçramasını üretmelidir.

**Evidence.** J. D. Anderson, Jr., *Modern Compressible Flow with Historical
Perspective*, Bölüm 3 ve 5. Bağıntılar standarttır (alan-Mach, izentropik
basınç oranı, Rankine-Hugoniot).

**Confidence: high.** Değerler Brent kök bulucuyla 10⁻¹⁵ toleransında
hesaplandı; A/A\*=2 için çıkan **0.305903834 / 2.197198122** ders kitaplarında
yaygın verilen 0.3059 / 2.1972 ile örtüşüyor — yani hesap bağımsız teyitli.
Şok kaydının M₁'i alan-Mach kaydıyla **aynı köktür**; iki vaka zincirleme
tutarlıdır.

**Date checked.** 2026-08-03

**What may change.** Hiçbir şey (analitik). **Hassasiyet notu:** değerler
9 haneye yazıldı çünkü bekçi 6 haneli sürümde A/A\*=4 ses altı kökünde
bağıl 1.5·10⁻⁶ sapma yakaladı. Kayıtlar kısaltılırsa bekçi kırmızıya döner —
bu istenen davranıştır.

---

## 8. Lüle akışı — ayrılma kriterleri

**Claim.** Aşırı genişlemiş lülede ayrılma için tek bir "doğru" kriter yoktur.
HRMA hangi kriteri kullandığını **beyan etmelidir**.

**Evidence.** Beş kriter, **orijinal** künyeleriyle (hepsi R. H. Stark,
*Flow Separation in Rocket Nozzles, a Simple Criteria*, AIAA 2005-3940, 2005
ekinden ve kaynakçasından alındı; <https://elib.dlr.de/49253/1/AIAA2005-3940.pdf>):

| Kriter | Bağıntı | Orijinal künye |
|---|---|---|
| Summerfield | p_sep/p_a = 0.35…0.40 | Summerfield, Foster, Swan, *Jet Propulsion* 24(9) 319-321, 1954 |
| Schilling | p_sep/p_a = 0.583 (p_c/p_a)^(−0.195) | Schilling, Y. Lisans Tezi, Univ. Buffalo, 1962 |
| Kalt & Badal | p_sep/p_a = (2/3)(p_c/p_a)^(−1/5) | *J. Spacecraft and Rockets* 2(3) 447-449, 1965 |
| Schmucker | p_sep/p_a = (1.88·Ma_sep − 1)^(−0.64) | Schmucker, Bericht TB-7, TU München, 1973 |
| Stark | p_sep/p_a = π/(3·Ma_sep) | AIAA 2005-3940, 2005 |

**Confidence: high.** Künye zinciri tam (ikinci elden aktarma değil,
kaynakçadan okundu).

**Schmucker parantezi — çözülen belirsizlik.** PDF metin çıkarımında parantez
konumu belirsizdi. İki olası okuma **sayısal olarak** sınandı:
`(1.88·Ma − 1)^(−0.64)` Ma = 2…4 için 0.52…0.30 veriyor (makalenin
şekillerindeki bantla birebir); `1.88·(Ma − 1)^(−0.64)` ise 1.88…0.93 veriyor,
yani p_sep > p_a — **fiziksel olarak imkânsız**. Birinci okuma kesinleştirildi
ve bekçiye "p_sep/p_a < 1" akıl sağlığı kontrolü olarak gömüldü.

**What may change.** **Kriterler birbiriyle uyuşmuyor ve bu bir hata değil.**
Ma_sep = 4.0'da Schmucker 0.301, Stark 0.262 veriyor — aralarında %15 fark.
HRMA tek bir sayıyı "ayrılma basıncı" diye kesin göstermemelidir.

---

## 9. Akustik — silindirik oda modları

**Claim.** Akustik modül, sert cidarlı silindirik odanın boyuna, teğetsel ve
radyal mod frekanslarını Bessel türev köklerinden üretmelidir.

**Evidence.** Harrje & Reardon (ed.), *Liquid Propellant Rocket Combustion
Instability*, NASA SP-194, 1972 (NTRS 19720026079) — silindirik oda akustiği
ve Bessel kökleri standart sunumu.

**Kökler (hesaplandı, hatırlanmadı):** 1T = 1.841184 · 2T = 3.054237 ·
1R = 3.831706 · 3T = 4.201189 · 1T1R = 5.331443 · 2R = 7.015587.

**Confidence: high.** Kökler `scipy.special.jnp_zeros` ile hesaplandı ve
literatürün 1.8412 / 3.8317 değerleriyle birebir tuttu.

**Date checked.** 2026-08-03

**What may change.** **Künye uyarısı:** SP-194 bağıntıların standart referansı
olarak verilmiştir; belge bu turda **açılmadı**, dolayısıyla sayfa/denklem
numarası **yoktur**. Bağıntılar klasik akustiktir ve bağımsız türetilebilir;
doğrulanması gereken tek şey SP-194'ün tam adı ve yılıdır — bu, arama
sonuçlarından teyit edildi (Harrje editör, Reardon yardımcı editör, 1972).

---

## 10. Akustik — F-1 birinci teğetsel modu

**Claim.** F-1'de geliştirme sırasında ölçülen 1T kararsızlık frekansları
**454-538 Hz** aralığındadır (karakteristik değer ~500 Hz).

**Evidence.** Oefelein & Yang 1993, **Tablo 4**: 5U düz yüzlü enjektör
(birim 005) **538 Hz**, 5U bölmeli (birim 076) **460 Hz**, çift sıra kümeli
(birim 067) **454 Hz** — dipnot: *first tangential mode*. PFRT konfigürasyonu
metinde **500 Hz**. Genlikler oda basıncının %65-400'ü.

**Confidence: high** (frekanslar için).

**Date checked.** 2026-08-03

**What may change — asıl mesele bu.** Bu kayıt "model doğru çıkıyor" vakası
**değildir**. Sert cidar formülü denge ses hızıyla (c\* = 1660 m/s, γ ≈ 1.22'den
a ≈ 1196 m/s) ve R ≈ 0.50 m ile **~700 Hz** veriyor; ölçülen 454-538 Hz.
Yani formül gerçek motorda **%30-55 yüksek** tahmin ediyor.

Sebep uydurma değil, bilinen fizik: enjektöre yakın bölgede yanma
tamamlanmamıştır, etkin ses hızı denge değerinin altındadır. **HRMA bu modu
hesaplarsa bu sapmayı beyan etmeli, 500 Hz'i tutturduğunu iddia etmemelidir.**

İki varsayım bu türetmeyi zayıflatıyor ve kayıtta `low` olarak işaretli:
(a) **oda yarıçapı bu kaynakta yayımlanmamıştır** — R = 0.50 m duyarlılık
taraması için kullanıldı, capa olarak değil; (b) **γ = 1.22 bizim
varsayımımızdır**, kaynakta yoktur. Ölçülen frekanslar `high`, türetilen
model açığı `low`.

---

## 11. İki-faz — tanecik yükü kaybı

**Claim.** Yoğuşmuş faz yükü c\* ve Isp'yi düşürür. Kayıt **ikiye ayrılmıştır**:
denge limiti (kapalı form) ve gecikme kaybı (görgül).

**Evidence.** Karışım termodinamiği bağıntıları — R_mix = (1−β)R_gas,
c_p,mix = (1−β)c_p,gas + βc_s, γ_mix = c_p,mix/c_v,mix. Yönlendirici künye:
Sutton & Biblarz, *Rocket Propulsion Elements*, 9. baskı, Wiley, 2016.

Hesaplanan örnek (R = 320 J/kg·K, c_p = 2000, c_s = 1400, T_c = 3500 K):
β = 0.10 → c\* kaybı **%4.66**; β = 0.30 → **%15.02**.

**Confidence: LOW — ve sebebi açık.** Karışım bağıntıları standart
termodinamiktir, burada bağımsız türetilip hesaplandı (bu kısım güvenilir).
**Ancak Sutton'ın kitabı bu turda açılamadı.** Sonuç:
(a) bölüm ve denklem numarası **verilmemiştir**;
(b) Sutton'ın kendi görgül tanecik gecikme bağıntısı **alınamamıştır**.
Yani bu kayıt Sutton'ın söylediğinin değil, **standart karışım
termodinamiğinin** kaydıdır; künye yönlendirme amaçlıdır.

**Date checked.** 2026-08-03

**What may change.** Modül yazılmadan **önce** kitabın ilgili bölümü açılıp
denklem numaraları ve gecikme bağıntısı eklenmelidir. Ayrıca:
- Denge limiti **alt sınırdır** — gerçek kayıp bundan **büyüktür** (hız ve
  ısıl gecikme ek kayıp getirir). Bu limit "iki-faz kaybı budur" diye
  sunulmamalıdır.
- Web özetinde görülen *"%5 alüminyum başına %1 Isp kaybı"* pratik kuralı
  **kayda yazılmadı**: birincil belge (DTIC AD/A-004 666) indirilemedi
  (bağlantı PDF yerine yönlendirme sayfası döndü). Doğrulanmadan
  kullanılmamalıdır.
- Örnek girdiler **temsilidir**, belirli bir yakıtın ölçülmüş özellikleri
  değildir.

---

## Özet tablo

| # | Veri kümesi | Confidence | En büyük risk |
|---|---|:-:|---|
| 1 | Lamé / ANSYS VM25 | high | Düzlem gerilme mi şekil değiştirme mi — varsayım kritik |
| 2 | Geçici iletim (Carslaw & Jaeger) | high | Yok (analitik) |
| 3 | Bartz hata bandı | high | Bağıntının üsleri 1957 makalesinden teyitsiz |
| 4 | RL10 turbopompa | high | Ölçüm değil, tasarım/model tahmini; NPSH yok |
| 5 | F-1 turbopompa | high | Kaynakta birim erratumu (ft/inç); NPSH yok |
| 6 | Merlin / RD-180 | n/a | **Veri yok** — ikincilden doldurulmamalı |
| 7 | İzentropik + şok | high | Yok (analitik); hane sayısı korunmalı |
| 8 | Ayrılma kriterleri | high | Kriterler %15 ayrışıyor — tek sayı gösterilmemeli |
| 9 | Oda akustik modları | high | SP-194 sayfa/denklem numarası yok |
| 10 | F-1 1T frekansı | high (ölçüm) / low (türetme) | Formül %30-55 yüksek; yarıçap ve γ varsayım |
| 11 | İki-faz tanecik yükü | **low** | Sutton açılamadı; gecikme bağıntısı **eksik** |

## Bakım

```bash
python3 data/validation/selfcheck.py                 # şema + yeniden türetme
bash    data/validation/sources/fetch_sources.sh     # belgeleri indir + SHA-256 doğrula
```

Bir belge özeti tutmazsa yayıncı onu değiştirmiş demektir; ilgili JSON kaydının
değerleri **yeniden kontrol edilmelidir**. Yeni bir doğrulama vakası eklerken
bu deftere önce satır girilir — künyesi olmayan veri kümesi eklenmez.
