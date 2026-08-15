# Yol haritası — ölçülmüş bugün, planlanan yarın

**Son güncelleme:** 2026-08-15
**Kapsam:** Nerede olduğumuz (ölçülerek), nereye gittiğimiz (plan
dosyalarından derlenerek), neyin açık borç kaldığı. Bu belge mevcut plan
dosyalarının **yerine geçmez**, onları birleştirir ve güncel ölçümle
karşılaştırır. Kaynaklar § 7'de, aralarındaki çelişkiler § 8'de.

**Ölçüm tabanı:** `2e2375d`, 14 Ağustos 2026.

> **Tarih uyarısı:** Bu belgede hiçbir hedef tarih uydurulmamıştır. Plan
> dosyalarında geçen tarihler *karar* tarihleridir, teslim tarihi değil.
> Teslim tarihi hiçbir kaynakta yoktur → **tarih belirlenmedi.**

---

## 1. Ölçülen mevcut durum

| Ölçüm | Değer |
|---|---|
| `hrma/__init__.py::__version__` | **2.6.26** |
| Son etiketli iş | 2.6.27 kampanyasının dokuz partisi (`b4c21ef` … `30fa5fa`) + Windows penceresi (`2e2375d`) |
| Python kaynağı | 108 dosya / 104 836 satır |
| Flask uçları | 91 |
| Analiz modülü | 33 |
| Analiz paneli (istemci) | 14 |
| Toplanan test | 6 503 |
| `NOT_MODELLED` geçen satır | 209 |
| `_basis` / `_source` / `_status` | 593 / 510 / 139 |

Sürüm dizesinin `2.6.26`'da kalması bilinçli değil, **kaydedilmemiş bir
adımdır** → [teknik-borc.md](teknik-borc.md) § 6.

---

## 2. Kulvar kulvar ölçülmüş durum

Kulvar adları `docs/YOL_HARITASI_2.7_VE_SONRASI.md` (3 Ağustos 2026) ile
aynıdır. **Durum sütunu o belgeden değil, bugünkü koddan ölçülmüştür.**

### Kulvar A — motor tipleri arasında derinlik eşitleme

| ID | İş | Ölçülen durum |
|---|---|---|
| A1 | `tank_blowdown` → hibrit | **Bağlı** (`transient_ballistics` üzerinden `N2OTankBlowdown`) |
| A2 | `slosh_analysis` → hibrit + sıvı | **Bağlı** (hibrit 2, sıvı 4 çağrı) |
| A3 | `pressure_vessel` → hibrit + sıvı | **Bağlı** (hibrit 1, sıvı 3, katı 2) |
| A4 | `bolted_joint` → hibrit + sıvı | **Bağlı** (üç motorda da 2 çağrı) |
| A5 | `thermal_protection` → hibrit | **Bağlı** (üç motorda da 2 çağrı) |
| A6 | `water_hammer` → besleme hattı | Sıvıda **bağlı** (8 çağrı); hibritte `_feed_water_hammer_block` üzerinden |
| A7 | `uncertainty` → hibrit + sıvı | **Bağlı ama uç katmanından**: `uq_adapters` üç motor fabrikası da sunuyor (`make_hybrid_factory`, `make_solid_factory`, `make_liquid_factory`), `/api/uncertainty-analysis` sürüyor |
| A8 | `launch_site` → hibrit | **Bağlı** (2 çağrı) |
| A9 | Hibritte O/F kayması | **Bağlı** (`11c5715`); ölçülen blowdown etkisi O/F 2,50 → 2,32 (%7,2), zaman ortalamalı Isp tasarımdan %0,27 sapıyor |
| A10 | Hibritte beyan taraması | **Bitti.** Ölçülen: hibrit `NOT_MODELLED` geçen satır sayısı **81** (3 Ağustos'ta 4 idi) |
| A11 | Tank tek-geometri | **AÇIK** — en büyük tekil borç (L ölçeği) |

### Kulvar B — CAD ve görselleştirme

| ID | İş | Ölçülen durum |
|---|---|---|
| B1 | Soğutma kanalı geometrisi | **Çizilyor** — `motor_viz3d.js` `cooling_channels` bloğundan `n_channels`, `channel_width_m`, `channel_height_m` okuyor |
| B2 | Enjektör delik deseni | **Çiziliyor** (gerçek delik yerleşimi) |
| B3 | Lüle konturu gerçek profilden | **Bitti** — üç motor da `sample_nozzle_inner_contour` kullanıyor, bekçi `tests/test_motor_geometri_yayimi.py` |
| B4 | Kaynağa göre renklendirme | **Bitti** — `SOURCE_COLORS` tablosu; hesaplanan / kullanıcı / varsayım / modellenmemiş yüzeyler ayrı renk |
| B5 | Katı tane yanma animasyonu | Kısmen (viz3d belgesinde "yanma animasyonu" yazılı; kapsamı ayrıca ölçülmedi) |
| B6 | Kesit (cutaway) görünümü | **Bitti** — `buildSolid(..., cutaway)`, `CUT_PHI_START/LENGTH` |
| B7 | Fotogerçekçi render | Açık |

### Kulvar C — yeni bileşen modülleri

| ID | İş | Ölçülen durum |
|---|---|---|
| C1 | Turbopompa boyutlandırma | **Modül + bağlama var** (`turbopump_sizing`, sıvıda 2 çağrı). Yalnız turbopompalı çevrimde bağlanır; RL10 + F-1'e karşı 44 test |
| C2 | Vana ve besleme hattı | **Modül + bağlama var** (`valve_feedline`, sıvıda 2 çağrı) |
| C3 | Gimbal ve itki montajı | **Modül var, HİÇBİR YERE BAĞLI DEĞİL** — `analyze_gimbal_mount` yalnız `tests/test_c_kulvari_bilesenler.py` içinden çağrılıyor. Tek gerçek yetim modül |
| C4 | Ateşleyici | **Modül + bağlama var** (`igniter_sizing`; katıda 5, hibritte 1 çağrı) |
| C5 | Tank basınçlandırma | Bağlı (`pressurant_sizing`, sıvıda 2 çağrı). Gerçek-gaz borcu KAPANDI (15 Ağu, `9e1410b`): ölçülen hata 300 bar'da ~%14'tü, Z düzeltmesi mutasyon-denetimli bekçilerle girdi |

### Kulvar D — v2.7 analiz modülü (mesh + termal + yapısal)

| ID | İş | Ölçülen durum |
|---|---|---|
| D1 | Eksenel simetrik yapısal çözücü | **Var** — `fea/structural_axisym.py` (692 satır) + `mesh_axisym.py` (278). Doğrulama: Lamé %0,64, O(h²) yakınsama, ANSYS VM25 vakası %0,032. Q4 elemanda gerilme süperyakınsaklık noktası sorunu Zienkiewicz-Zhu SPR ile çözüldü |
| D2 | Eksenel simetrik ısı çözücü | **Var** — `fea/thermal_axisym.py` (833 satır), geri Euler geçici iletim, Bartz + ışıma sınır koşulu; erfc / sabit-akı analitik vakalarına ≤ %0,22, enerji bütçesi 1e-13 |
| D3 | Doğrulama kümesi | **Var** (D1 + D2 doğrulama vakaları yukarıda) |
| D4 | CAD → mesh köprüsü | **Var** — `fea/bridge.py` (1 171 satır). Fiziksel sağlama: maks von Mises 31,2 MPa ≈ hoop 30,3 MPa |
| D5 | Sonuç görselleştirme | **Var** — `/api/fea/structural`, `/api/fea/thermal` + `fea_panel.js` (1 023 satır): kontur haritası, tel kafes, eleman kalite haritası (en-boy oranı + ölçekli Jacobian), yakınsama geçmişi |
| — | Katı tane için 2B **düzlemsel** kip (V2.7 Aşama C) | **Yok** — `fea/__init__.py` içinde "[V2.7 Aşama C — henüz yok]" diye yazılı |

### Kulvar E — arayüz ve pano

| ID | İş | Ölçülen durum |
|---|---|---|
| E1 | Sekme → ızgara yerleşim | **Var** |
| E2 | Bağlı güncelleme + "ne değişti" şeridi | **Var** (`analysis_dock.js` `diff` katmanı) |
| E3 | Grafiklerde kaynak renklendirme | **Var** (`source` katmanı) |
| E4 | İki tasarımı karşılaştırma | **Var** (`comparative_panel.js`, 570 satır) |
| E5 | Duyarlılık grafiği | Belirsizlik panelinde tornado var; ayrı duyarlılık taraması açık |

### Kulvar F — v3 ve sonrası

| ID | İş | Ölçülen durum |
|---|---|---|
| F1 | CFD (lüle iç akışı, ayrılma, şok) | **Yarı-1B karşılığı var**: `flow/quasi1d.py` + `flow/separation.py`, katı ve hibritte bağlı (101 test). **Gerçek CFD yok** — planlı v3 |
| F2 | Yanma kararsızlığı | **Akustik mod çekirdeği var** (`acoustic_modes.py`, hibrit 2 / katı 3 çağrı, 36 test). Yanma tepkisi modeli açık |
| F3 | Test verisi korelasyonu | Altyapı var (`validation/correlation_runner.py`, `experiment_db.py`, `validation_records/`, `correlation_panel.js`). **Dış kullanıcı verisiyle kapanmış döngü YOK** |
| F4 | Çok fazlı akış / tanecik yükü | **İki-faz kaybı var** (`two_phase_loss.py`, katıda 3 çağrı, 37 test) |

**Toplu okuma:** 3 Ağustos yol haritasının v2.7 / v2.8 / v3'e dağıttığı
işlerin büyük bölümü **2.6.27 kampanyasında** yapıldı. Kalan boşluklar
dağınık değil, adı konabilir durumda: C3 bağlaması, C5 gerçek gaz, A11 tank
geometrisi, katı tanesi için düzlemsel FEA kipi, gerçek CFD, F3 korelasyon
döngüsünün kapanması.

---

## 3. 2.7 kapısı — geçiş ölçütleri

Sürüme **sayıyla değil ölçütle** geçilir. Aşağıdaki dört madde
2.6.27 kampanya kaydında Berke ile mutabık kalınmış hâliyle, ilk kez bu
belgeye yazılmıştır.

| # | Ölçüt | Bugünkü durum |
|---|---|---|
| 1 | D2-D5 kullanıcıya görünür: mesh üstünde gerilme **ve** sıcaklık konturu ekranda | Yapısal ve termal uçlar + `fea_panel.js` var. Uçtan uca ürün turu ile teyit edilmeli |
| 2 | Çekirdek-yetim modül **sıfır** (F1/F2/F4/C1/blowdown hepsi panele bağlı) | **SAĞLANDI (15 Ağu):** C3 gimbal `/api/gimbal-mount` + sayfa paneliyle bağlandı; yetim modül kalmadı |
| 3 | En az bir dış kullanıcının **gerçek test verisiyle** kapanmış korelasyon döngüsü (F3) | Açık. Ayberk'in toplu testine bağlanmış durumda |
| 4 | Yayın kapısı 8/8 + iskele görsel turu yeşil + tank tek-geometri (A11) kapalı | Kapı ve tur yeşil ölçüldü (4 Ağustos: 3/3 sayfa); **A11 açık** |

---

## 4. Yayın stratejisi

**Karar (Berke, 14 Ağustos 2026):** yapısal (FEA) ve CFD analiz kulvarları
başlı başına iştir. **Kamuya sürüm bunlar bitene kadar yapılmaz**; tek büyük
"FINAL" yayını yapılır, sonrası bakım modudur (hata düzeltme + performans).

Operasyonel sonuçları:

* **İç derleme/etiket hattı çalışır kalır.** Windows doğrulaması, test
  kullanıcısı geri dönütü ve F3 korelasyon döngüsü buna muhtaçtır. "Yayın
  turu" = iç sürüm üretimi, vitrin değil.
* § 3'teki 2.7 kapı ölçütleri **FINAL'in ön şartı olarak aynen geçerlidir**;
  yalnız kamuya duyuru FINAL'e ertelenmiştir.
* **Performans optimizasyonu ayrı bir final aşaması değildir**: CFD ile
  birlikte ölçüm güdümlü yürür — profil ölç → numba/Cython → gerekirse
  pybind11 ile C++ çekirdek.

---

## 5. Mimari kararlar (yol haritasını bağlayan)

| Karar | Gerekçe |
|---|---|
| **2B eksenel simetrik yeterli** | Kamara ve lüle dönel simetriktir; 3B sıfır yeni bilgi + 100-1000× maliyet getirir. ANSYS'in kendisi de eksenel simetrik eleman sunar. 3B'nin gerçekten gerektiği yerler ayrı ve dar: tane kesitleri (düzlemsel 2B), flanş/cıvata yerel gerilmeleri, gimbal yan yükleri |
| **Katı tanesi ayrı kip ister** | Star / finocyl / slotted geometriler eksenel simetrik **değildir**; 2B düzlemsel kesit gerekir. Baştan planlanır, sonradan eklenmeye çalışılmaz |
| **C/C++ şimdilik gereksiz** | `scipy.sparse` zaten C/Fortran çekirdeklidir; 2B'de serbestlik derecesi küçük (D1 test süiti 3,4 s). Darboğaz sayısal döngü değil CEA/Cantera'dır (ikisi de zaten C++). Derlenmiş çekirdek = iki platformda ayrı derleme zinciri + imza + paket boyutu; uygulamanın hâlihazırda bu iki sorunu var |
| **Mesh ayarı gizli, mesh'in kendisi görünür** | Kullanıcı mesh yoğunluğu/çözücü ayarı görmez; ama tel kafesi, eleman kalitesini ve yakınsama grafiğini görür. "Optimal mesh" iddiası ancak yakınsama raporlanırsa dürüsttür |
| **Doğrulanmamış FEA yayımlanmaz** | Doğrulanmamış bir FEA analitik formülden **kötüdür**: renkli kontur üretir ve otoriter görünür. Kanıtlanmamış mesh görüntüsü süstür |
| **CFD v3/v3.5** | v2.7 kapsamında yoktur; yerine yarı-1B akış + ayrılma ölçütü konmuştur |

---

## 6. Açık kuyruk

Öncelik sırası değil, **açık kalemler listesi**. Ölçülmüş ya da plan
dosyalarında/kampanya kaydında açıkça yazılı olanlar:

| Kalem | Ölçek | Not |
|---|---|---|
| **A11** tank tek-geometri | L | En büyük tekil borç; 2.7 kapı ölçütü |
| ~~**C3** gimbal bağlaması~~ KAPANDI (15 Ağu, on üçüncü parti) | S | uç deseniyle bağlandı, 17 bekçi |
| ~~**C5** gerçek-gaz düzeltmesi~~ KAPANDI (15 Ağu, `9e1410b`) | M | ölçülen gerçek hata ~%14'tü; Z uygulandı, mutasyon-denetimli bekçili |
| **F3** korelasyon döngüsünün kapanması | L | Dış kullanıcı verisi gerekiyor |
| Katı tanesi için **2B düzlemsel FEA kipi** | L | V2.7 Aşama C; `fea/__init__.py`'de "henüz yok" diye yazılı |
| **Gerçek CFD** | XL | v3/v3.5; performans kulvarıyla birlikte |
| Yanma tepkisi modeli (F2 tamamlanması) | XL | Akustik modlar hazır, tepki fonksiyonu yok |
| Windows arayüz kalemleri | S | Windows'ta doğrulanmadı, fotoğrafla teyit bekliyor |
| Isp / ısı-akısı adlandırma tutarlılığı | S | |
| Sıvı arayüz form alanları (cıvata / vana / hat girdileri) | M | API'de var, formda yok — Katman A kusuru sınıfı |
| ~~`STEFAN_BOLTZMANN` merkezîleştirme~~ KAPANDI (15 Ağu, `01d0c9d`) | S | tek tanım `hrma/constants.py`; literal bekçisi `test_sabit_tek_kaynak.py` |
| B5 tam yanma animasyonu, B7 fotogerçekçi render, E5 duyarlılık taraması | M | |

Teknik borçların ayrıntısı ve **neden bekletildiği**
→ [teknik-borc.md](teknik-borc.md).

---

## 7. Kaynak plan dosyaları

| Dosya | Tarihi | Kapsamı | Bugünkü geçerliliği |
|---|---|---|---|
| `docs/YOL_HARITASI_2.7_VE_SONRASI.md` | 3 Ağu 2026, taban `9d3728e` | A-F kulvarları, iş kırılımı, efor ölçekleri | **Kulvar tanımları geçerli, durum tabloları eskimiş** (§ 8.1) |
| `docs/V2.7_ANALIZ_MODULU.md` | Karar 1 Ağu 2026 | 2B eksenel simetrik FEA'nın gerekçesi, mesh politikası, doğrulama vakaları, dil kararı | **Gerekçeler geçerli**, "yapılacak" durumu D1-D5 ile aşıldı; Aşama C hâlâ açık |
| `docs/ANALIZ_PLATFORM_PLANI.md` | 14 Tem 2026 | Dalga 0-4, analiz güvertesi mimarisi, panel kalıbı, sahte CFD/kinetik teşhisi | Dalga 0-4 uygulandı; **"Açık kararlar" bölümü artık kapalı** (§ 8.3) |
| `docs/GUVEN_SURUMU_PLANI.md` | 17 Tem 2026 | UQ mimarisi, deney veri küratörlüğü, korelasyon altyapısı, G1-G4 | G1-G4 kodda görünüyor; **"Berke onayı bekliyor" başlığı eskimiş** (§ 8.4) |
| `docs/SPACE_CAPABILITY.md` | 12 Tem 2026 | Kármán sınıfı hibrit için yetenek matrisi ve kapsam dışı listesi | Yargı geçerli; **sayılar eskimiş** (§ 8.5) |

Ayrıca sürüm planları (`V2.6.26_PLAN.md`, `V2.6.26_BITIRME_PLANI.md`,
`V2.6.2_PLAN.md`, `v2.5.2_plan.md`) tamamlanmış sürümlerin kayıtlarıdır;
tarihsel belge olarak korunurlar, yol göstermezler.

---

## 8. Plan dosyaları arasındaki çelişkiler ve eskimeler

Aşağıdakiler **ölçülerek** bulunmuştur. Kaynak dosyalara dokunulmamıştır;
bu bölüm onları okuyan kişiyi uyarmak içindir.

### 8.1 `YOL_HARITASI_2.7_VE_SONRASI.md` § 0 tabloları artık yanlış

Belge kendi tabanını dürüstçe ilan ediyor (`9d3728e`, 3 Ağustos), ama o
tarihten sonra dokuz parti iş girdi. Ölçülen fark:

| İddia (3 Ağu) | Ölçüm (14 Ağu) |
|---|---|
| `NOT_MODELLED` beyanı — sıvı **47** / hibrit **4** / katı **23** | sıvı **74** / hibrit **81** / katı **38** |
| "Hibrit, on bir modülün **hiçbirine** bağlı değil" | Hibrit en az 8 modüle bağlı: `thermal_protection`, `launch_site`, `slosh_analysis`, `pressure_vessel`, `bolted_joint`, `acoustic_modes`, `transient_ballistics`, `igniter_sizing` |
| "`tank_blowdown.py` hiçbir yere bağlı değil" | `transient_ballistics` üzerinden bağlı |
| Sıvı 7 766 / hibrit 2 657 / katı 7 232 satır | 9 674 / 5 786 / 9 374 |
| C1 turbopompa "v2.8 / v3" | 2.6.27'de yapıldı |
| D1-D5 "v2.7" | 2.6.27'de yapıldı |

**Sonuç:** o belgenin **kulvar tanımları ve değişmez kuralları** hâlâ
referanstır; **durum tabloları ve sürüm evrelemesi** okunmamalıdır. Bu
belgenin § 2'si onların yerine geçer.

### 8.2 Sürüm evrelemesi ile fiilî gidişat çelişiyor

`YOL_HARITASI` işleri v2.7 / v2.8 / v3'e dağıtıyor. Kampanya kararı ise
"2.6.27 = en büyük ekleme sürümü; yol haritasının tamamı + v3 temelleri"
biçiminde ilerledi ve C1-C4, D1-D5, F1/F2/F4 tek sürüme sığdı. İki belge
okunduğunda farklı bir gelecek resmi çıkar. **Bu belgedeki § 2 + § 3
geçerlidir:** artık sürüm numarası değil, § 3'teki dört ölçüt yol gösterir.

### 8.3 `ANALIZ_PLATFORM_PLANI.md` sonundaki "Açık kararlar" kapanmıştır

Belge iki soruyu Berke'ye açık bırakıyor: (1) CFD + kinetik yeniden yazılsın
mı yoksa gerçekçi hızlı modellerle değiştirilsin mi, (2) başlangıç kapsamı.
Kod bunu çoktan cevaplamış: `nozzle_flow_1d` + `kinetic_efficiency` yazıldı,
`/api/cfd-analysis`, `/api/kinetic-analysis` ve `/api/professional-analysis`
**HTTP 501** ile halef uca yönlendiriyor. Karar "değiştirme" yönünde
uygulanmıştır; belge güncellenmemiştir.

### 8.4 `GUVEN_SURUMU_PLANI.md` durumu "onay bekliyor" diyor, iş bitmiş

Belge 17 Temmuz'da "plan Berke onayı bekliyor" diyor ve yedi açık karar
sıralıyor. Ölçüm: `analysis/uncertainty.py` (881 satır) + `uq_adapters.py`
(384) + `/api/uncertainty-analysis` + `uncertainty_panel.js` (541) +
`validation/experiment_db.py` + `validation_records/` + `correlation_runner.py`
+ `correlation_panel.js` hepsi depoda. G1-G4 dalgaları uygulanmıştır.
Belgenin **teknik içeriği** (dağılım künyeleri, kabul bantları, döngüsellik
korumaları) hâlâ referanstır; **durum satırı** yanıltıcıdır.

### 8.5 `SPACE_CAPABILITY.md` test sayısı eskimiş

Belge "1,000+ automated tests" diyor (12 Temmuz). Ölçüm: **6 503 test
toplanıyor.** Yetenek matrisindeki mühendislik yargıları geçerlidir; sayı
güncellenmelidir.

### 8.6 Küçük ama tekrarlayan tür: "yazıldı, bağlanmadı"

Yol haritası 3 Ağustos'ta `tank_blowdown` için bunu söylüyordu ("yazılmış,
duruyor, kullanılmıyor"). O kapandı; ama aynı desen **C3 gimbal** ile geri
geldi. Bu, kalem bazlı değil **sınıf** bazlı bir risktir: modül + test
yazmak bağlamaktan kolaydır, ve bağlanmamış modül kullanıcıya sıfır değer
üretir. Bu yüzden § 3'ün 2. ölçütü ("çekirdek-yetim modül sıfır") sürüm
kapısında durur.

---

## 9. Her kalem için değişmez kural

Kulvarı ne olursa olsun, yeni bir iş şunları taşımadan tamamlanmış sayılmaz:

* Girdi ve çıktı **beyanlıdır**: `_basis` / `_source` / `_status` /
  `NOT_MODELLED`.
* Beyanı **okuyan bir kapı** vardır. Faz 4'ün en pahalı dersi:
  `_defaults_used` 14 yerde yazılıyor, 0 yerde okunuyordu.
* Çizilen hiçbir yüzey ve gösterilen hiçbir sayı **hesaplanmamış** değildir.
  Hesaplanmayan çizilmez; yerine "modellenmedi" beyanı konur.
* Yeni fizik modülü **doğrulama kümesiyle** gelir (analitik çözüm, yayımlanmış
  motor verisi ya da korunum kontrolü). Doğrulaması olmayan modül yayımlanmaz.
* Modül yazmak işin yarısıdır; **bağlanmamış modül bitmemiş iştir.**
